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
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence, QResizeEvent
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHeaderView, QTableView, QWidget

from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.interfaz.textos import (
    simbolo_estado_mv,
    simbolo_estado_rollback,
    texto_aviso_origen,
    texto_detalle_rollback,
    texto_error,
    texto_estado_mv,
    texto_estado_rollback,
    texto_origen_corto,
    texto_resumen_origen,
    texto_vmid_ocupado_en_lote,
    tooltip_plano,
)
from proxlaunch.interfaz.textos_b import (
    texto_aviso_b,
    texto_celda_ip,
    texto_detalle_ip,
    token_color_ip,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    ESTADOS_EN_CURSO,
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
    EstadoRollback,
    FilaLote,
    Plan,
    ResultadoRollback,
)
from proxlaunch.nucleo.modelos.origen import DetalleClon
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO

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
    EstadoMV.AJUSTANDO: "acento_enlace",
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


def _es_clon(cfg: ConfiguracionVM) -> bool:
    """Un clon hereda los discos de la plantilla: los del formulario no se usan (INV-O3)."""
    return cfg.origen == OrigenSO.CLONAR_PLANTILLA


def _almacenamiento_principal(e: ElementoPlan) -> str:
    cfg = e.cfg
    if _es_clon(cfg):
        det = cfg.detalle_origen
        # Solo hay almacenamiento propio en un clon completo hacia otro almacenamiento.
        return (det.storage_destino or "—") if isinstance(det, DetalleClon) else "—"
    if not cfg.con_disco or not cfg.discos:
        return "—"
    return cfg.discos[0].storage or "—"


def _total_discos_gib(e: ElementoPlan) -> str:
    cfg = e.cfg
    if _es_clon(cfg):
        det = cfg.detalle_origen
        # Sin ampliación el tamaño es el de la plantilla, que esta tabla no conoce.
        if isinstance(det, DetalleClon) and det.ajustes.disco_gib is not None:
            return str(det.ajustes.disco_gib)
        return "—"
    return str(sum(d.tamano_gib for d in cfg.discos) if cfg.con_disco else 0)


def _celdas_clon(cfg: ConfiguracionVM) -> tuple[str, str, str, str]:
    """(discos, almacenamiento, procesadores, memoria) de un clon antes de planificar."""
    det = cfg.detalle_origen
    if not isinstance(det, DetalleClon):
        return "—", "—", "—", "—"
    a = det.ajustes
    disco = "—" if a.disco_gib is None else str(a.disco_gib)
    procesadores = (
        str((a.sockets or 1) * (a.cores or 1))
        if a.sockets is not None or a.cores is not None
        else "—"
    )
    memoria = "—" if a.memoria_mib is None else f"{a.memoria_mib / 1024:g}"
    return disco, det.storage_destino or "—", procesadores, memoria


def _hay_origen(cfgs: Iterable[ConfiguracionVM]) -> bool:
    """¿Alguna máquina tiene un origen distinto del disco vacío? Entonces se añade la columna."""
    return any(c.origen != OrigenSO.DISCO_VACIO for c in cfgs)


def _texto_origen_celda(cfg: ConfiguracionVM) -> str:
    """«ISO: local:iso/alpine.iso (Linux)»; «Disco vacío» si no hay sistema de origen."""
    return texto_resumen_origen(cfg) or texto_origen_corto(cfg.origen)


def _vcpus(cfg: ConfiguracionVM) -> int:
    return cfg.sockets * cfg.cores


def _gib_memoria(cfg: ConfiguracionVM) -> str:
    return f"{cfg.memoria_mib / 1024:g}"


class ModeloPlan(_ModeloBase):
    """Una fila por máquina del plan: número, nombre, VMID, nodo, almacenamiento y discos.

    En un lote por filas (CSV) añade los procesadores y la memoria de cada máquina (CA-C08.7) y
    la primera columna es el número de fila del archivo.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._elementos: tuple[ElementoPlan, ...] = ()
        self._origenes: tuple[int | None, ...] = ()  # nº de fila del archivo (solo por filas)
        self._por_filas = False
        self._con_origen = False  # MVP 4: columna «Origen» si alguna máquina no es disco vacío

    @property
    def por_filas(self) -> bool:
        return self._por_filas

    def _cabeceras(self) -> tuple[str, ...]:
        base: tuple[str, ...] = (
            QCoreApplication.translate("ModelosTabla", "Fila")
            if self._por_filas
            else QCoreApplication.translate("ModelosTabla", "N.º"),
            QCoreApplication.translate("ModelosTabla", "Nombre"),
            "VMID",
            QCoreApplication.translate("ModelosTabla", "Nodo"),
            QCoreApplication.translate("ModelosTabla", "Almacenamiento"),
            QCoreApplication.translate("ModelosTabla", "Discos (GiB)"),
        )
        if self._por_filas:
            base = (
                *base,
                QCoreApplication.translate("ModelosTabla", "Procesadores"),
                QCoreApplication.translate("ModelosTabla", "Memoria (GiB)"),
            )
        if self._con_origen:
            base = (*base, QCoreApplication.translate("ModelosTabla", "Sistema operativo"))
        return base

    def etiqueta_fila(self, e: ElementoPlan) -> str:
        """Número con el que se nombra la máquina: el de la fila del archivo, o su posición."""
        return self.etiqueta_fila_de(e.indice)

    def etiqueta_fila_de(self, indice: int) -> str:
        """Lo mismo, a partir de la posición (0..N-1) de la fila en el lote."""
        if self._por_filas and 0 <= indice < len(self._origenes):
            origen = self._origenes[indice]
            if origen is not None:
                return str(origen)
        return str(indice + 1)

    def establecer_plan(self, plan: Plan | None) -> None:
        self.beginResetModel()
        self._elementos = plan.elementos if plan is not None else ()
        self._por_filas = plan is not None and plan.definicion.es_por_filas
        self._con_origen = _hay_origen(x.cfg for x in self._elementos)
        self._origenes = (
            tuple(f.origen for f in plan.definicion.filas)
            if plan is not None and self._por_filas
            else ()
        )
        self.endResetModel()

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._elementos)

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._elementos):
            return None
        e = self._elementos[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            celdas: tuple[str, ...] = (
                self.etiqueta_fila(e),
                e.nombre,
                str(e.vmid),
                e.nodo,
                _almacenamiento_principal(e),
                _total_discos_gib(e),
            )
            if self._por_filas:
                celdas = (*celdas, str(_vcpus(e.cfg)), _gib_memoria(e.cfg))
            if self._con_origen:
                celdas = (*celdas, _texto_origen_celda(e.cfg))
            return celdas[col]
        if role == Qt.ItemDataRole.ToolTipRole and self._con_origen:
            if col == (8 if self._por_filas else 6):
                return tooltip_plano(_texto_origen_celda(e.cfg))  # el texto completo, escapado (M3)
            return None
        numericas = (0, 2, 5, 6, 7) if self._por_filas else (0, 2, 5)
        if role == Qt.ItemDataRole.TextAlignmentRole and col in numericas:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            if self._por_filas:
                texto = QCoreApplication.translate(
                    "ModelosTabla",
                    "Fila {n}: {nombre}, número {vmid}, nodo {nodo}, {v} procesadores "
                    "virtuales, {m} GiB de memoria",
                ).format(
                    n=self.etiqueta_fila(e),
                    nombre=e.nombre,
                    vmid=e.vmid,
                    nodo=e.nodo,
                    v=_vcpus(e.cfg),
                    m=_gib_memoria(e.cfg),
                )
            else:
                texto = QCoreApplication.translate(
                    "ModelosTabla", "Máquina {n}: {nombre}, número {vmid}, nodo {nodo}"
                ).format(n=e.indice + 1, nombre=e.nombre, vmid=e.vmid, nodo=e.nodo)
            origen = texto_resumen_origen(e.cfg)
            return f"{texto}. {origen}" if origen else texto
        return None


class ModeloFilasLote(_ModeloBase):
    """Filas de un lote por filas antes de planificar (``PanelLoteFilas``, solo lectura).

    Una fila por máquina con su configuración: número de fila del archivo, nombre, VMID y nodo
    (o «Automático»), procesadores, memoria, discos y red. Es una tabla de modelo: 100 filas no
    son 100 widgets y se desplaza con el teclado.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filas: tuple[FilaLote, ...] = ()
        self._con_origen = False  # MVP 4: columna «Sistema operativo» si alguna fila lo trae

    def _cabeceras(self) -> tuple[str, ...]:
        base: tuple[str, ...] = (
            QCoreApplication.translate("ModelosTabla", "Fila"),
            QCoreApplication.translate("ModelosTabla", "Nombre"),
            "VMID",
            QCoreApplication.translate("ModelosTabla", "Nodo"),
            QCoreApplication.translate("ModelosTabla", "Procesadores"),
            QCoreApplication.translate("ModelosTabla", "Memoria (GiB)"),
            QCoreApplication.translate("ModelosTabla", "Discos (GiB)"),
            QCoreApplication.translate("ModelosTabla", "Almacenamiento"),
            QCoreApplication.translate("ModelosTabla", "Red"),
        )
        if self._con_origen:
            base = (*base, QCoreApplication.translate("ModelosTabla", "Sistema operativo"))
        return base

    def establecer_filas(self, filas: Sequence[FilaLote]) -> None:
        self.beginResetModel()
        self._filas = tuple(filas)
        self._con_origen = _hay_origen(f.cfg for f in self._filas)
        self.endResetModel()

    @property
    def filas(self) -> tuple[FilaLote, ...]:
        return self._filas

    def etiqueta_fila(self, i: int) -> str:
        origen = self._filas[i].origen if 0 <= i < len(self._filas) else None
        return str(origen if origen is not None else i + 1)

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._filas)

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._filas):
            return None
        i = index.row()
        fila = self._filas[i]
        cfg = fila.cfg
        col = index.column()
        auto = QCoreApplication.translate("ModelosTabla", "Automático")
        if role == Qt.ItemDataRole.DisplayRole:
            discos = str(sum(d.tamano_gib for d in cfg.discos) if cfg.con_disco else 0)
            storage = (cfg.discos[0].storage or "—") if cfg.con_disco and cfg.discos else "—"
            red = ", ".join(r.bridge or "—" for r in cfg.redes) or "—"
            procesadores, memoria = str(_vcpus(cfg)), _gib_memoria(cfg)
            if _es_clon(cfg):
                # Un clon hereda de la plantilla: solo se muestra lo que se pidió ajustar.
                discos, storage, procesadores, memoria = _celdas_clon(cfg)
            celdas: tuple[str, ...] = (
                self.etiqueta_fila(i),
                fila.nombre,
                str(fila.vmid) if fila.vmid is not None else auto,
                fila.nodo or auto,
                procesadores,
                memoria,
                discos,
                storage,
                red,
            )
            if self._con_origen:
                celdas = (*celdas, _texto_origen_celda(cfg))
            return celdas[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (0, 2, 4, 5, 6):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            origen = texto_resumen_origen(cfg)
            if _es_clon(cfg):
                return QCoreApplication.translate(
                    "ModelosTabla", "Fila {n}: {nombre}. {origen}"
                ).format(n=self.etiqueta_fila(i), nombre=fila.nombre, origen=origen)
            texto = QCoreApplication.translate(
                "ModelosTabla",
                "Fila {n}: {nombre}, {v} procesadores virtuales, {m} GiB de memoria",
            ).format(
                n=self.etiqueta_fila(i), nombre=fila.nombre, v=_vcpus(cfg), m=_gib_memoria(cfg)
            )
            return f"{texto}. {origen}" if origen else texto
        return None


# --- Libro --------------------------------------------------------------------------


def texto_aviso_entrada(codigo: str) -> str:
    """Texto de un código de aviso de una entrada del libro (vacío si no se conoce)."""
    if codigo == "creada_tras_comprobar":
        return QCoreApplication.translate(
            "ModelosTabla", "Se creó aunque Proxmox tardó en responder."
        )
    texto_b = texto_aviso_b(codigo)  # fase B: cloud-init, contraseña e IP
    if texto_b:
        return texto_b
    return texto_aviso_origen(codigo)  # MVP 4: ajustes pendientes u omitidos, discos sueltos


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
        avisos = " ".join(t for t in (texto_aviso_entrada(a) for a in entrada.avisos) if t)
        if any(a.startswith("ajuste_pendiente:") for a in entrada.avisos):
            # Clon creado al que le faltan ajustes: se puede reintentar o deshacer (E-O24).
            return texto_error(error) if error is not None else avisos
        base = QCoreApplication.translate(
            "ModelosTabla", "Quedó a medias; elimínala con «Deshacer…» o desde Proxmox."
        )
        return f"{base} {avisos}" if avisos else base
    if estado == EstadoMV.CONEXION_PERDIDA and error is None:
        return texto_error(
            ErrorProxLaunch(
                CodigoError.LOTE_ENVIO_INCIERTO,
                {"nombre": nombre, "vmid": str(entrada.elemento.vmid)},
            )
        )
    avisos_extra = " ".join(t for t in (texto_aviso_entrada(a) for a in entrada.avisos) if t)
    if error is not None:
        if error.codigo == CodigoError.VMID_OCUPADO:
            return texto_vmid_ocupado_en_lote(error.params.get("vmid", "?"))
        base = texto_error(error)
        return f"{base} {avisos_extra}" if avisos_extra else base
    return avisos_extra


class ModeloLibro(_ModeloBase):
    """Estado de cada máquina del lote en ejecución; se refresca con instantáneas.

    Fase B: si alguna máquina pidió esperar su IP, aparece la columna «IP» entre «Nodo» y
    «Detalle». Sin esa opción el modelo es el de 0.6.0 (cinco columnas).
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entradas: tuple[EntradaLibro, ...] = ()
        self._con_ip = False
        self._espera_activa = False

    @property
    def con_ip(self) -> bool:
        """Hay columna «IP» (alguna máquina pidió esperar su IP)."""
        return self._con_ip

    @property
    def columna_detalle(self) -> int:
        return 5 if self._con_ip else 4

    @property
    def columna_ip(self) -> int | None:
        return 4 if self._con_ip else None

    def _cabeceras(self) -> tuple[str, ...]:
        base: tuple[str, ...] = (
            QCoreApplication.translate("ModelosTabla", "Estado"),
            QCoreApplication.translate("ModelosTabla", "Nombre"),
            "VMID",
            QCoreApplication.translate("ModelosTabla", "Nodo"),
        )
        if self._con_ip:
            base = (*base, QCoreApplication.translate("ModelosTabla", "IP"))
        return (*base, QCoreApplication.translate("ModelosTabla", "Detalle"))

    @staticmethod
    def _pide_ip(entradas: Sequence[EntradaLibro]) -> bool:
        return any(e.elemento.cfg.esperar_ip or e.ip is not None for e in entradas)

    def establecer_espera_activa(self, activa: bool) -> None:
        """Indica si la espera de IP sigue en marcha (cambia «Esperando…» por «—»)."""
        if activa == self._espera_activa:
            return
        self._espera_activa = activa
        if self._con_ip and self._entradas:
            col = self.columna_ip or 0
            self.dataChanged.emit(self.index(0, col), self.index(len(self._entradas) - 1, col))

    def establecer_entradas(self, entradas: Sequence[EntradaLibro]) -> None:
        """Refresca con una instantánea; solo se repintan las filas que cambiaron."""
        nuevas = tuple(entradas)
        con_ip = self._pide_ip(nuevas)
        if len(nuevas) != len(self._entradas) or not self._entradas or con_ip != self._con_ip:
            self.beginResetModel()
            self._entradas = nuevas
            self._con_ip = con_ip
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
        es_ip = self._con_ip and col == 4
        es_detalle = col == self.columna_detalle
        if role == Qt.ItemDataRole.DisplayRole:
            celdas: tuple[str, ...] = (
                self.texto_estado(e),
                el.nombre,
                str(el.vmid),
                el.nodo,
            )
            if self._con_ip:
                celdas = (*celdas, texto_celda_ip(e, espera_activa=self._espera_activa))
            return (*celdas, detalle_entrada(e))[col]
        if role == Qt.ItemDataRole.ForegroundRole and col == 0:
            return self._color(_TOKEN_ESTADO.get(e.estado, "texto"))
        if role == Qt.ItemDataRole.ForegroundRole and es_ip:
            return self._color(token_color_ip(e))
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 2:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and es_detalle:
            return tooltip_plano(detalle_entrada(e)) if detalle_entrada(e) else None
        if role == Qt.ItemDataRole.ToolTipRole and es_ip:
            return tooltip_plano(texto_detalle_ip(e.ip)) if e.ip is not None else None
        if role == Qt.ItemDataRole.AccessibleTextRole:
            texto = QCoreApplication.translate(
                "ModelosTabla", "{nombre}, número {vmid}, nodo {nodo}: {estado}"
            ).format(nombre=el.nombre, vmid=el.vmid, nodo=el.nodo, estado=texto_estado_mv(e.estado))
            if self._con_ip:
                ip = texto_celda_ip(e, espera_activa=self._espera_activa)
                if ip:
                    texto += ". " + QCoreApplication.translate("ModelosTabla", "IP: {ip}").format(
                        ip=ip
                    )
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
    return texto_detalle_rollback(r.acciones, r.error)


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


_ANCHO_MIN_ULTIMA = 48  # píxeles mínimos de la columna que elide (origen del SO)


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
        self._elidir_ultima = False

    def elidir_ultima_columna(self, elidir: bool) -> None:
        """La última columna se encoge con «…» en vez de ensanchar la tabla (y el panel)."""
        self._elidir_ultima = elidir
        self._ajustar_columnas()

    def setModel(self, model: QAbstractItemModel | None) -> None:
        super().setModel(model)
        if model is not None:
            self._ajustar_columnas()
            # El plan de un lote por filas tiene más columnas que el homogéneo.
            model.modelReset.connect(self._ajustar_columnas)

    def _ajustar_columnas(self) -> None:
        modelo = self.model()
        if modelo is None:
            return
        cabecera = self.horizontalHeader()
        for c in range(modelo.columnCount()):
            cabecera.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        if self._elidir_ultima and modelo.columnCount() > 0:
            # La última columna ocupa lo que sobra (con un mínimo) y elide el texto largo.
            cabecera.setStretchLastSection(False)
            cabecera.setTextElideMode(Qt.TextElideMode.ElideRight)
            cabecera.setSectionResizeMode(
                modelo.columnCount() - 1, QHeaderView.ResizeMode.Interactive
            )
            self._repartir_ultima()
            return
        cabecera.setStretchLastSection(True)

    def _repartir_ultima(self) -> None:
        """Da a la última columna el ancho que sobra, con un mínimo."""
        modelo = self.model()
        if not self._elidir_ultima or modelo is None or modelo.columnCount() == 0:
            return
        cabecera = self.horizontalHeader()
        ultima = modelo.columnCount() - 1
        resto = self.viewport().width() - sum(cabecera.sectionSize(c) for c in range(ultima))
        cabecera.resizeSection(ultima, max(resto, _ANCHO_MIN_ULTIMA))

    def resizeEvent(self, ev: QResizeEvent) -> None:
        super().resizeEvent(ev)
        self._repartir_ultima()

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
