"""Modelo de tabla de la vista previa de la importación CSV (RF-C06, RNF-M05, RNF-M06).

Una fila del archivo es una fila del modelo: 100 filas no son 100 widgets, se desplazan con
el teclado y se copian como texto. El estado lleva texto y símbolo, nunca solo color, y los
colores salen de los tokens del tema. Los textos de los problemas por celda también viven
aquí porque son los mismos que se escriben en el CSV de filas con error (RF-C12).
"""

from __future__ import annotations

from typing import TypeAlias

from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor

from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.interfaz.textos import (
    SIMBOLO_ESTADO,
    texto_estado_con_simbolo,
    texto_estado_fila,
    texto_linea_problema,
    tooltip_plano,
)
from proxlaunch.nucleo.csv_importacion.columnas import COLUMNAS_SECRETAS
from proxlaunch.nucleo.csv_importacion.modelos import (
    EstadoFila,
    FilaInterpretada,
    ResultadoImportacion,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.secreto import MASCARA
from proxlaunch.nucleo.validacion import Severidad

_Indice: TypeAlias = QModelIndex | QPersistentModelIndex

# Símbolo + texto del estado de cada fila (CA-C06.2).
_SIMBOLO_SEVERIDAD: dict[Severidad, str] = {
    Severidad.ERROR: SIMBOLO_ESTADO[EstadoFila.CON_ERROR],
    Severidad.AVISO: SIMBOLO_ESTADO[EstadoFila.CON_AVISO],
}
_TOKEN_ESTADO: dict[EstadoFila, str] = {
    EstadoFila.CORRECTA: "exito",
    EstadoFila.CON_AVISO: "aviso",
    EstadoFila.CON_ERROR: "error",
}


# --- Textos de los problemas ----------------------------------------------------------


# --- Valores interpretados ------------------------------------------------------------


def valor_original_visible(canonica: str, valor: str) -> str:
    """Valor del archivo tal como puede verse en pantalla: la columna de contraseñas siempre
    enmascarada (RF-B6.5). El núcleo ya la entrega enmascarada; esta es la segunda defensa."""
    return MASCARA if canonica in COLUMNAS_SECRETAS else valor


def texto_memoria(mib: int) -> str:
    """«4 GiB» o «512 MiB»."""
    return f"{mib // 1024} GiB" if mib % 1024 == 0 else f"{mib} MiB"


def _nucleos(cfg: ConfiguracionVM) -> str:
    if cfg.sockets == 1:
        return str(cfg.cores)
    return f"{cfg.sockets} × {cfg.cores}"


def _discos(cfg: ConfiguracionVM) -> str:
    if not cfg.con_disco or not cfg.discos:
        return QCoreApplication.translate("ModelosTablaCsv", "Sin disco")
    return " + ".join(f"{d.tamano_gib} GiB" for d in cfg.discos)


def _almacenamiento(cfg: ConfiguracionVM) -> str:
    if not cfg.con_disco or not cfg.discos:
        return "—"
    return cfg.discos[0].storage or "—"


def _red(cfg: ConfiguracionVM) -> str:
    if not cfg.redes:
        return "—"
    r = cfg.redes[0]
    base = r.bridge or "—"
    return f"{base} (VLAN {r.vlan})" if r.vlan is not None else base


# Columnas del modelo: (clave interna, columna canónica del CSV o None).
_COLUMNAS: tuple[tuple[str, str | None], ...] = (
    ("incluir", None),
    ("fila", None),
    ("nombre", "nombre"),
    ("perfil", "perfil"),
    ("vmid", "vmid"),
    ("nodo", "nodo"),
    ("nucleos", "cpu"),
    ("memoria", "memoria"),
    ("disco", "disco"),
    ("almacenamiento", "almacenamiento"),
    ("red", "red"),
    ("estado", None),
)
COLUMNA_INCLUIR = 0
COLUMNA_ESTADO = len(_COLUMNAS) - 1


class ModeloVistaPreviaCsv(QAbstractTableModel):
    """Una fila por fila del archivo; columna «Incluir» con casilla para las que no tienen error.

    Las filas con error no se pueden marcar (nunca entran al lote). ``seleccion_cambiada`` se
    emite cuando el usuario marca o desmarca una casilla.
    """

    seleccion_cambiada = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tokens: dict[str, str] = TOKENS_OSCURO
        self._resultado: ResultadoImportacion | None = None
        self._filas: tuple[FilaInterpretada, ...] = ()
        self._incluidas: set[int] = set()
        # número de fila -> {columna canónica: peor severidad} y textos para la sugerencia.
        self._por_columna: dict[int, dict[str, Severidad]] = {}

    # --- Datos -----------------------------------------------------------------------

    def establecer_resultado(self, resultado: ResultadoImportacion | None) -> None:
        """Carga un resultado nuevo: las filas sin error quedan marcadas."""
        self.beginResetModel()
        self._resultado = resultado
        self._filas = resultado.filas if resultado is not None else ()
        self._incluidas = set(resultado.numeros_validos) if resultado is not None else set()
        self._por_columna = {}
        if resultado is not None:
            inverso = {enc: canon for canon, enc in resultado.columnas.encabezados.items()}
            for f in self._filas:
                mapa: dict[str, Severidad] = {}
                for p in f.problemas:
                    canon = inverso.get(p.columna) if p.columna else None
                    if canon is None:
                        continue
                    if mapa.get(canon) != Severidad.ERROR:
                        mapa[canon] = p.severidad
                self._por_columna[f.numero] = mapa
        self.endResetModel()

    @property
    def resultado(self) -> ResultadoImportacion | None:
        return self._resultado

    def fila_en(self, fila: int) -> FilaInterpretada | None:
        return self._filas[fila] if 0 <= fila < len(self._filas) else None

    def es_problema(self, fila: int) -> bool:
        """Filas con aviso o con error: las que muestra el filtro «Mostrar solo problemas»."""
        f = self.fila_en(fila)
        return f is not None and f.estado != EstadoFila.CORRECTA

    def numeros_elegidos(self) -> tuple[int, ...]:
        """Números de fila marcados para importar, en el orden del archivo."""
        return tuple(f.numero for f in self._filas if f.numero in self._incluidas)

    def numeros_excluidos(self) -> tuple[FilaInterpretada, ...]:
        """Filas que NO entran: con error o desmarcadas por el usuario."""
        return tuple(f for f in self._filas if f.numero not in self._incluidas)

    def conteos(self) -> tuple[int, int, int]:
        """(correctas, con aviso, con error)."""
        correctas = sum(1 for f in self._filas if f.estado == EstadoFila.CORRECTA)
        avisos = sum(1 for f in self._filas if f.estado == EstadoFila.CON_AVISO)
        errores = sum(1 for f in self._filas if f.estado == EstadoFila.CON_ERROR)
        return correctas, avisos, errores

    def marcar_todas(self, marcar: bool) -> None:
        """Marca (las que no tienen error) o desmarca todas."""
        if self._resultado is None:
            return
        self._incluidas = set(self._resultado.numeros_validos) if marcar else set()
        if self._filas:
            self.dataChanged.emit(
                self.index(0, COLUMNA_INCLUIR), self.index(len(self._filas) - 1, COLUMNA_INCLUIR)
            )
        self.seleccion_cambiada.emit()

    def lineas_de_error(self) -> list[str]:
        """Un texto por problema de severidad error, para «Copiar errores» (CA-C05.10)."""
        if self._resultado is None:
            return []
        columnas = self._resultado.columnas
        return [
            texto_linea_problema(p, columnas)
            for f in self._filas
            for p in f.problemas
            if p.severidad == Severidad.ERROR
        ]

    def lineas_de_problema(self, fila: int) -> list[str]:
        """Todos los problemas de una fila (errores y avisos), con «y N más» al final."""
        f = self.fila_en(fila)
        if f is None or self._resultado is None:
            return []
        columnas = self._resultado.columnas
        lineas = [
            f"{_SIMBOLO_SEVERIDAD[p.severidad]} {texto_linea_problema(p, columnas)}"
            for p in f.problemas
        ]
        if f.problemas_omitidos:
            lineas.append(
                QCoreApplication.translate(
                    "ModelosTablaCsv", "y %n más", None, f.problemas_omitidos
                )
            )
        return lineas

    # --- Tema ------------------------------------------------------------------------

    def establecer_tema(self, tema: str) -> None:
        """Cambia los tokens de color (``"claro"`` u ``"oscuro"``) y repinta."""
        self._tokens = TOKENS_CLARO if tema == "claro" else TOKENS_OSCURO
        if self._filas:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._filas) - 1, self.columnCount() - 1)
            )

    def _color(self, token: str) -> QColor:
        return QColor(self._tokens[token])

    # --- Interfaz del modelo -----------------------------------------------------------

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._filas)

    def columnCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(_COLUMNAS)

    @staticmethod
    def cabeceras() -> tuple[str, ...]:
        return (
            QCoreApplication.translate("ModelosTablaCsv", "Incluir"),
            QCoreApplication.translate("ModelosTablaCsv", "Fila"),
            QCoreApplication.translate("ModelosTablaCsv", "Nombre"),
            QCoreApplication.translate("ModelosTablaCsv", "Perfil"),
            "VMID",
            QCoreApplication.translate("ModelosTablaCsv", "Nodo"),
            QCoreApplication.translate("ModelosTablaCsv", "Núcleos"),
            QCoreApplication.translate("ModelosTablaCsv", "Memoria"),
            QCoreApplication.translate("ModelosTablaCsv", "Disco"),
            QCoreApplication.translate("ModelosTablaCsv", "Almacenamiento"),
            QCoreApplication.translate("ModelosTablaCsv", "Red"),
            QCoreApplication.translate("ModelosTablaCsv", "Estado"),
        )

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            cabeceras = self.cabeceras()
            if 0 <= section < len(cabeceras):
                return cabeceras[section]
        return None

    def flags(self, index: _Indice) -> Qt.ItemFlag:
        base = super().flags(index)
        if index.isValid() and index.column() == COLUMNA_INCLUIR:
            f = self.fila_en(index.row())
            if f is not None and f.estado != EstadoFila.CON_ERROR:
                return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def setData(self, index: _Indice, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if (
            not index.isValid()
            or index.column() != COLUMNA_INCLUIR
            or role != Qt.ItemDataRole.CheckStateRole
        ):
            return False
        f = self.fila_en(index.row())
        if f is None or f.estado == EstadoFila.CON_ERROR:
            return False
        marcada = value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value, 2, True)
        if marcada:
            self._incluidas.add(f.numero)
        else:
            self._incluidas.discard(f.numero)
        self.dataChanged.emit(index, index)
        self.seleccion_cambiada.emit()
        return True

    def _valor(self, f: FilaInterpretada, clave: str) -> str:
        """Texto de una celda: valor interpretado o, si no hay configuración, el del archivo."""
        cfg = f.cfg
        original = f.originales
        if clave == "fila":
            return str(f.numero)
        if clave == "nombre":
            return f.nombre or "—"
        if clave == "perfil":
            return f.perfil or "—"
        if clave == "vmid":
            return (
                str(f.vmid)
                if f.vmid is not None
                else QCoreApplication.translate("ModelosTablaCsv", "auto")
            )
        if clave == "nodo":
            return f.nodo or QCoreApplication.translate("ModelosTablaCsv", "automático")
        if cfg is None:
            columna = dict(_COLUMNAS).get(clave) or clave
            return valor_original_visible(columna, original.get(columna, "—"))
        if clave == "nucleos":
            return _nucleos(cfg)
        if clave == "memoria":
            return texto_memoria(cfg.memoria_mib)
        if clave == "disco":
            return _discos(cfg)
        if clave == "almacenamiento":
            return _almacenamiento(cfg)
        if clave == "red":
            return _red(cfg)
        return ""

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        f = self.fila_en(index.row()) if index.isValid() else None
        if f is None:
            return None
        clave, canonica = _COLUMNAS[index.column()]
        col = index.column()
        if col == COLUMNA_INCLUIR:
            return self._data_incluir(f, role)
        if col == COLUMNA_ESTADO:
            return self._data_estado(f, index.row(), role)
        severidad = self._por_columna.get(f.numero, {}).get(canonica) if canonica else None
        if role == Qt.ItemDataRole.DisplayRole:
            texto = self._valor(f, clave)
            if severidad == Severidad.ERROR:
                return f"{SIMBOLO_ESTADO[EstadoFila.CON_ERROR]} {texto}"
            if severidad == Severidad.AVISO:
                return f"{SIMBOLO_ESTADO[EstadoFila.CON_AVISO]} {texto}"
            return texto
        if role == Qt.ItemDataRole.ForegroundRole and severidad is not None:
            return self._color("error" if severidad == Severidad.ERROR else "aviso")
        if role == Qt.ItemDataRole.ToolTipRole and severidad is not None:
            return tooltip_plano("\n".join(self._textos_columna(f, canonica)))
        if role == Qt.ItemDataRole.TextAlignmentRole and clave in ("fila", "vmid"):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return self._texto_accesible(f, clave)
        return None

    def _textos_columna(self, f: FilaInterpretada, canonica: str | None) -> list[str]:
        if self._resultado is None or canonica is None:
            return []
        columnas = self._resultado.columnas
        encabezado = columnas.encabezados.get(canonica)
        return [texto_linea_problema(p, columnas) for p in f.problemas if p.columna == encabezado]

    def _data_incluir(self, f: FilaInterpretada, role: int) -> object:
        if f.estado == EstadoFila.CON_ERROR:
            if role == Qt.ItemDataRole.DisplayRole:
                return "—"
            if role == Qt.ItemDataRole.ToolTipRole:
                return QCoreApplication.translate(
                    "ModelosTablaCsv",
                    "Una fila con error no se puede importar. Corrígela en el archivo.",
                )
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return QCoreApplication.translate(
                    "ModelosTablaCsv", "Incluir la fila {n}: no se puede, tiene un error"
                ).format(n=f.numero)
            return None
        if role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if f.numero in self._incluidas else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return (
                QCoreApplication.translate("ModelosTablaCsv", "Incluir la fila {n}").format(
                    n=f.numero
                )
                + ": "
                + (
                    QCoreApplication.translate("ModelosTablaCsv", "sí")
                    if f.numero in self._incluidas
                    else QCoreApplication.translate("ModelosTablaCsv", "no")
                )
            )
        return None

    def _data_estado(self, f: FilaInterpretada, fila: int, role: int) -> object:
        estado = f.estado
        if role == Qt.ItemDataRole.DisplayRole:
            return texto_estado_con_simbolo(estado)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._color(_TOKEN_ESTADO[estado])
        if role == Qt.ItemDataRole.ToolTipRole:
            lineas = self.lineas_de_problema(fila)
            return tooltip_plano("\n".join(lineas)) if lineas else None
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return QCoreApplication.translate("ModelosTablaCsv", "Fila {n}: {estado}").format(
                n=f.numero, estado=texto_estado_fila(estado)
            )
        return None

    def _texto_accesible(self, f: FilaInterpretada, clave: str) -> str:
        return QCoreApplication.translate("ModelosTablaCsv", "Fila {n}, {columna}: {valor}").format(
            n=f.numero,
            columna=self.cabeceras()[[c for c, _ in _COLUMNAS].index(clave)],
            valor=self._valor(f, clave),
        )


class FiltroProblemasCsv(QSortFilterProxyModel):
    """Filtro «Mostrar solo problemas» (CA-C06.2): filas con aviso o con error."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._solo_problemas = False

    @property
    def solo_problemas(self) -> bool:
        return self._solo_problemas

    def establecer_solo_problemas(self, activo: bool) -> None:
        if activo == self._solo_problemas:
            return
        self._solo_problemas = activo
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: _Indice) -> bool:
        if not self._solo_problemas:
            return True
        modelo = self.sourceModel()
        return isinstance(modelo, ModeloVistaPreviaCsv) and modelo.es_problema(source_row)
