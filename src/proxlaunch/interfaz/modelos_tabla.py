"""Modelos de tabla del lote: plan, libro y rollback (RNF-L05, CA-L10.5).

Cada tabla es un ``QAbstractTableModel``: 100 filas no son 100 widgets, se desplazan con
teclado y se copian como texto. El estado de cada máquina lleva texto y símbolo, nunca solo
color (RNF-L04); los colores salen de los tokens del tema, sin literales.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeAlias

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHeaderView, QTableView, QWidget

from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.interfaz.textos import (
    simbolo_estado_mv,
    simbolo_estado_rollback,
    texto_error,
    texto_estado_mv,
    texto_estado_rollback,
    texto_vmid_ocupado_en_lote,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    ESTADOS_EN_CURSO,
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
    EstadoRollback,
    Plan,
    ResultadoRollback,
)

_Indice: TypeAlias = QModelIndex | QPersistentModelIndex

# Estados que se consideran «problema» en el filtro «Mostrar solo problemas» (CA-L13.4).
ESTADOS_PROBLEMA = frozenset(
    {
        EstadoMV.CON_AVISOS,
        EstadoMV.ERROR,
        EstadoMV.PARCIAL,
        EstadoMV.TIEMPO_AGOTADO,
        EstadoMV.CONEXION_PERDIDA,
        EstadoMV.NO_ENVIADA,
        EstadoMV.NO_CREADA_SEGURA,
        EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD,
    }
)
# Estados que cuentan como «con error» en la barra global.
ESTADOS_CON_ERROR = frozenset({EstadoMV.ERROR, EstadoMV.PARCIAL})
# Estados sin confirmar: pueden existir en Proxmox aunque no lo sepamos.
ESTADOS_SIN_CONFIRMAR = frozenset(
    {
        EstadoMV.TIEMPO_AGOTADO,
        EstadoMV.CONEXION_PERDIDA,
        EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD,
    }
)

# Token de color del texto de estado.
_TOKEN_ESTADO: dict[EstadoMV, str] = {
    EstadoMV.PENDIENTE: "texto_secundario",
    EstadoMV.VALIDANDO: "acento_enlace",
    EstadoMV.ENVIANDO: "acento_enlace",
    EstadoMV.CREANDO: "acento_enlace",
    EstadoMV.COMPROBANDO: "acento_enlace",
    EstadoMV.OK: "exito",
    EstadoMV.CON_AVISOS: "aviso",
    EstadoMV.ERROR: "error",
    EstadoMV.PARCIAL: "error",
    EstadoMV.TIEMPO_AGOTADO: "aviso",
    EstadoMV.CONEXION_PERDIDA: "aviso",
    EstadoMV.NO_ENVIADA: "aviso",
    EstadoMV.NO_CREADA_SEGURA: "texto_secundario",
    EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD: "aviso",
}
_TOKEN_ROLLBACK: dict[EstadoRollback, str] = {
    EstadoRollback.PENDIENTE: "texto_secundario",
    EstadoRollback.COMPROBANDO: "acento_enlace",
    EstadoRollback.ELIMINANDO: "acento_enlace",
    EstadoRollback.ELIMINADA: "exito",
    EstadoRollback.YA_NO_EXISTIA: "exito",
    EstadoRollback.FALLO: "error",
    EstadoRollback.OMITIDA: "aviso",
    EstadoRollback.INCIERTA: "aviso",
    EstadoRollback.NO_ENVIADA: "texto_secundario",
}


class _ModeloBase(QAbstractTableModel):
    """Base común: tema para los colores y utilidades de lectura."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tokens: dict[str, str] = TOKENS_OSCURO

    def establecer_tema(self, tema: str) -> None:
        """Cambia los tokens de color (``"claro"`` u ``"oscuro"``) y repinta."""
        self._tokens = TOKENS_CLARO if tema == "claro" else TOKENS_OSCURO
        n = self.rowCount()
        if n:
            self.dataChanged.emit(self.index(0, 0), self.index(n - 1, self.columnCount() - 1))

    def _color(self, token: str) -> QColor:
        return QColor(self._tokens[token])

    def columnCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._cabeceras())

    def _cabeceras(self) -> tuple[str, ...]:
        raise NotImplementedError

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            cabeceras = self._cabeceras()
            if 0 <= section < len(cabeceras):
                return cabeceras[section]
        return None


# --- Plan ---------------------------------------------------------------------------


def _almacenamiento_principal(e: ElementoPlan) -> str:
    cfg = e.cfg
    if not cfg.con_disco or not cfg.discos:
        return "—"
    return cfg.discos[0].storage or "—"


def _total_discos_gib(e: ElementoPlan) -> int:
    cfg = e.cfg
    return sum(d.tamano_gib for d in cfg.discos) if cfg.con_disco else 0


class ModeloPlan(_ModeloBase):
    """Una fila por máquina del plan: número, nombre, VMID, nodo, almacenamiento y discos."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._elementos: tuple[ElementoPlan, ...] = ()

    def _cabeceras(self) -> tuple[str, ...]:
        return (
            QCoreApplication.translate("ModelosTabla", "N.º"),
            QCoreApplication.translate("ModelosTabla", "Nombre"),
            "VMID",
            QCoreApplication.translate("ModelosTabla", "Nodo"),
            QCoreApplication.translate("ModelosTabla", "Almacenamiento"),
            QCoreApplication.translate("ModelosTabla", "Discos (GiB)"),
        )

    def establecer_plan(self, plan: Plan | None) -> None:
        self.beginResetModel()
        self._elementos = plan.elementos if plan is not None else ()
        self.endResetModel()

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._elementos)

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._elementos):
            return None
        e = self._elementos[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                str(e.indice + 1),
                e.nombre,
                str(e.vmid),
                e.nodo,
                _almacenamiento_principal(e),
                str(_total_discos_gib(e)),
            )[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (0, 2, 5):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return QCoreApplication.translate(
                "ModelosTabla", "Máquina {n}: {nombre}, número {vmid}, nodo {nodo}"
            ).format(n=e.indice + 1, nombre=e.nombre, vmid=e.vmid, nodo=e.nodo)
        return None


# --- Libro --------------------------------------------------------------------------


def texto_aviso_entrada(codigo: str) -> str:
    """Texto de un código de aviso de una entrada del libro (vacío si no se conoce)."""
    if codigo == "creada_tras_comprobar":
        return QCoreApplication.translate(
            "ModelosTabla", "Se creó aunque Proxmox tardó en responder."
        )
    return ""


def detalle_entrada(entrada: EntradaLibro) -> str:
    """Mensaje en lenguaje llano de una máquina del lote (columna «Detalle»)."""
    estado = entrada.estado
    nombre = entrada.elemento.nombre
    error = entrada.error
    if estado in ESTADOS_EN_CURSO:
        return ""
    if estado == EstadoMV.OK:
        # Una máquina rescatada por la comprobación se creó, pero se avisa de ello (CA-L15.2).
        return " ".join(t for t in (texto_aviso_entrada(a) for a in entrada.avisos) if t)
    if estado == EstadoMV.CON_AVISOS:
        partes = [texto_aviso_entrada(a) for a in entrada.avisos]
        if error is not None:
            partes.append(texto_error(error))
        return " ".join(p for p in partes if p) or QCoreApplication.translate(
            "ModelosTabla", "Se creó, pero hay avisos."
        )
    if estado == EstadoMV.NO_ENVIADA:
        return texto_error(
            ErrorProxLaunch(
                CodigoError.LOTE_NO_ENVIADA,
                {"nombre": nombre, "motivo": str(entrada.motivo_no_enviada or "")},
            )
        )
    if estado == EstadoMV.NO_CREADA_SEGURA:
        return QCoreApplication.translate(
            "ModelosTabla", "Se comprobó y no existe en Proxmox. Puedes reintentarla."
        )
    if estado == EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD:
        return QCoreApplication.translate(
            "ModelosTabla",
            "Existe en Proxmox, pero no podemos asegurar que la creó este lote. No se eliminará.",
        )
    if estado == EstadoMV.PARCIAL:
        return QCoreApplication.translate(
            "ModelosTabla", "Quedó a medias; elimínala con «Deshacer…» o desde Proxmox."
        )
    if estado == EstadoMV.CONEXION_PERDIDA and error is None:
        return texto_error(
            ErrorProxLaunch(
                CodigoError.LOTE_ENVIO_INCIERTO,
                {"nombre": nombre, "vmid": str(entrada.elemento.vmid)},
            )
        )
    if error is not None:
        if error.codigo == CodigoError.VMID_OCUPADO:
            return texto_vmid_ocupado_en_lote(error.params.get("vmid", "?"))
        return texto_error(error)
    return ""


class ModeloLibro(_ModeloBase):
    """Estado de cada máquina del lote en ejecución; se refresca con instantáneas."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entradas: tuple[EntradaLibro, ...] = ()

    def _cabeceras(self) -> tuple[str, ...]:
        return (
            QCoreApplication.translate("ModelosTabla", "Estado"),
            QCoreApplication.translate("ModelosTabla", "Nombre"),
            "VMID",
            QCoreApplication.translate("ModelosTabla", "Nodo"),
            QCoreApplication.translate("ModelosTabla", "Detalle"),
        )

    def establecer_entradas(self, entradas: Sequence[EntradaLibro]) -> None:
        """Refresca con una instantánea; solo se repintan las filas que cambiaron."""
        nuevas = tuple(entradas)
        if len(nuevas) != len(self._entradas) or not self._entradas:
            self.beginResetModel()
            self._entradas = nuevas
            self.endResetModel()
            return
        previas = self._entradas
        self._entradas = nuevas
        ultima = self.columnCount() - 1
        for i, (a, b) in enumerate(zip(previas, nuevas, strict=True)):
            if a is not b and a != b:
                self.dataChanged.emit(self.index(i, 0), self.index(i, ultima))

    @property
    def entradas(self) -> tuple[EntradaLibro, ...]:
        return self._entradas

    def entrada(self, fila: int) -> EntradaLibro | None:
        return self._entradas[fila] if 0 <= fila < len(self._entradas) else None

    def es_problema(self, fila: int) -> bool:
        e = self.entrada(fila)
        return e is not None and e.estado in ESTADOS_PROBLEMA

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._entradas)

    @staticmethod
    def texto_estado(entrada: EntradaLibro) -> str:
        """Símbolo y nombre del estado: «✓ Lista»."""
        return f"{simbolo_estado_mv(entrada.estado)} {texto_estado_mv(entrada.estado)}"

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        e = self.entrada(index.row()) if index.isValid() else None
        if e is None:
            return None
        col = index.column()
        el = e.elemento
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                self.texto_estado(e),
                el.nombre,
                str(el.vmid),
                el.nodo,
                detalle_entrada(e),
            )[col]
        if role == Qt.ItemDataRole.ForegroundRole and col == 0:
            return self._color(_TOKEN_ESTADO.get(e.estado, "texto"))
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 2:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and col == 4:
            return detalle_entrada(e) or None
        if role == Qt.ItemDataRole.AccessibleTextRole:
            texto = QCoreApplication.translate(
                "ModelosTabla", "{nombre}, número {vmid}, nodo {nodo}: {estado}"
            ).format(nombre=el.nombre, vmid=el.vmid, nodo=el.nodo, estado=texto_estado_mv(e.estado))
            detalle = detalle_entrada(e)
            return f"{texto}. {detalle}" if detalle else texto
        return None


class FiltroProblemas(QSortFilterProxyModel):
    """Con el filtro activo solo deja pasar las máquinas con problemas (CA-L13.4)."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._solo_problemas = False

    @property
    def solo_problemas(self) -> bool:
        return self._solo_problemas

    def establecer_solo_problemas(self, activo: bool) -> None:
        if activo != self._solo_problemas:
            self._solo_problemas = activo
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: _Indice) -> bool:
        if not self._solo_problemas:
            return True
        modelo = self.sourceModel()
        return isinstance(modelo, ModeloLibro) and modelo.es_problema(source_row)

    def refrescar(self) -> None:
        """Reaplica el filtro tras un cambio de estados (el estado de una fila pudo cambiar)."""
        if self._solo_problemas:
            self.invalidateFilter()


# --- Rollback -----------------------------------------------------------------------


def detalle_rollback(r: ResultadoRollback) -> str:
    if r.error is not None:
        return texto_error(r.error)
    return ""


class ModeloRollback(_ModeloBase):
    """Progreso de «Deshacer»: una fila por máquina que se va a eliminar."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filas: list[ResultadoRollback] = []

    def _cabeceras(self) -> tuple[str, ...]:
        return (
            QCoreApplication.translate("ModelosTabla", "Estado"),
            QCoreApplication.translate("ModelosTabla", "Nombre"),
            "VMID",
            QCoreApplication.translate("ModelosTabla", "Nodo"),
            QCoreApplication.translate("ModelosTabla", "Detalle"),
        )

    def iniciar(self, previstas: Iterable[tuple[str, int, str]]) -> None:
        """Prepara las filas ``(nombre, vmid, nodo)`` en estado pendiente."""
        self.beginResetModel()
        self._filas = [
            ResultadoRollback(vmid=v, nodo=n, nombre=nombre, estado=EstadoRollback.PENDIENTE)
            for nombre, v, n in previstas
        ]
        self.endResetModel()

    def registrar(self, resultado: ResultadoRollback) -> None:
        for i, f in enumerate(self._filas):
            if f.vmid == resultado.vmid:
                self._filas[i] = resultado
                self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount() - 1))
                return
        pos = len(self._filas)
        self.beginInsertRows(QModelIndex(), pos, pos)
        self._filas.append(resultado)
        self.endInsertRows()

    def registrar_todos(self, resultados: Iterable[ResultadoRollback]) -> None:
        for r in resultados:
            self.registrar(r)

    @property
    def filas(self) -> tuple[ResultadoRollback, ...]:
        return tuple(self._filas)

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._filas)

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._filas):
            return None
        r = self._filas[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            estado = f"{simbolo_estado_rollback(r.estado)} {texto_estado_rollback(r.estado)}"
            return (estado, r.nombre, str(r.vmid), r.nodo, detalle_rollback(r))[col]
        if role == Qt.ItemDataRole.ForegroundRole and col == 0:
            return self._color(_TOKEN_ROLLBACK.get(r.estado, "texto"))
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 2:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return QCoreApplication.translate(
                "ModelosTabla", "{nombre}, número {vmid}: {estado}"
            ).format(nombre=r.nombre, vmid=r.vmid, estado=texto_estado_rollback(r.estado))
        return None


# --- Vista copiable -----------------------------------------------------------------


class TablaCopiable(QTableView):
    """Tabla de solo lectura, navegable con teclado y copiable como texto (CA-L10.5)."""

    def __init__(self, nombre_accesible: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(nombre_accesible)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setHighlightSections(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def setModel(self, model: QAbstractItemModel | None) -> None:
        super().setModel(model)
        if model is not None:
            cabecera = self.horizontalHeader()
            for c in range(model.columnCount()):
                cabecera.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
            cabecera.setStretchLastSection(True)

    def texto(self, *, solo_seleccion: bool) -> str:
        """Texto tabulado de la selección (o de toda la tabla), con la cabecera."""
        modelo = self.model()
        if modelo is None:
            return ""
        columnas = range(modelo.columnCount())
        if solo_seleccion:
            filas = sorted({i.row() for i in self.selectionModel().selectedIndexes()})
        else:
            filas = list(range(modelo.rowCount()))
        lineas = [
            "\t".join(str(modelo.headerData(c, Qt.Orientation.Horizontal) or "") for c in columnas)
        ]
        for f in filas:
            lineas.append("\t".join(str(modelo.data(modelo.index(f, c)) or "") for c in columnas))
        return "\n".join(lineas)

    def copiar(self) -> None:
        seleccion = bool(self.selectionModel() and self.selectionModel().hasSelection())
        QApplication.clipboard().setText(self.texto(solo_seleccion=seleccion))

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.matches(QKeySequence.StandardKey.Copy):
            self.copiar()
            return
        super().keyPressEvent(ev)
