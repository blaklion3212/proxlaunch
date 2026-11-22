"""Modelos de tabla del origen del SO: volúmenes (ISO e imágenes) y plantillas (MVP 4, RF-O07/O19).

Las filas que no se pueden elegir quedan **deshabilitadas con el motivo escrito** (CA-O07.2,
CA-O19.2, CA-O19.5): nunca se ocultan. El estado no depende solo del color: el motivo va en
una columna de texto. Los nombres, volids y notas vienen del servidor (texto no confiable): se
muestran como texto plano. Los colores salen de los tokens del tema, sin literales.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor

from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.interfaz.textos import (
    texto_estado_via,
    texto_tamano_bytes,
    tooltip_plano,
)
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import (
    Contenido,
    ListadoStorage,
    PermisosEfectivos,
    Plantilla,
    Volumen,
)
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, EstadoVia
from proxlaunch.nucleo.origen.nombres import EXTENSIONES, es_virtio_win, validar_volid

_Indice: TypeAlias = QModelIndex | QPersistentModelIndex

# Rol con el objeto de la fila (``FilaVolumen`` o ``FilaPlantilla``) para quien consume el modelo.
ROL_FILA = int(Qt.ItemDataRole.UserRole) + 1
# Rol booleano: la fila se puede elegir.
ROL_ELEGIBLE = int(Qt.ItemDataRole.UserRole) + 2
# Rol de texto para el filtro (nombre sin acentos ni mayúsculas, más el volid).
ROL_FILTRO = int(Qt.ItemDataRole.UserRole) + 3


def formatear_bytes(valor: int | None) -> str:
    """Tamaño legible (GiB/MiB) con el formato de ``textos``; ``«—»`` si se desconoce."""
    if valor is None:
        return "—"
    return texto_tamano_bytes(valor)


def formatear_fecha(epoch: int | None) -> str:
    """Fecha local ``AAAA-MM-DD`` de un ``ctime``; ``«—»`` si no viene."""
    if not epoch:
        return "—"
    try:
        return datetime.fromtimestamp(int(epoch)).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return "—"


# --- Filas ------------------------------------------------------------------------------


@dataclass(frozen=True)
class FilaVolumen:
    """Un volumen del catálogo con el nodo donde se listó y el motivo de deshabilitado."""

    volumen: Volumen
    nodo: str
    motivo: str  # "" = se puede elegir

    @property
    def elegible(self) -> bool:
        return not self.motivo

    @property
    def es_virtio_win(self) -> bool:
        return self.volumen.contenido == Contenido.ISO and es_virtio_win(self.volumen.nombre)


@dataclass(frozen=True)
class FilaPlantilla:
    """Una plantilla del catálogo con el motivo de deshabilitado (``""`` = elegible)."""

    plantilla: Plantilla
    motivo: str

    @property
    def elegible(self) -> bool:
        return not self.motivo


def motivo_volumen_no_admitido(volumen: Volumen) -> str:
    """Motivo (traducido) por el que un volumen no se puede elegir; ``""`` si se puede."""
    if volumen.admitido:
        return ""
    razon = validar_volid(volumen.volid, volumen.contenido)
    if razon == "extension":
        extensiones = ", ".join(sorted(EXTENSIONES.get(volumen.contenido, frozenset())))
        return QCoreApplication.translate(
            "ModeloCatalogoVolumenes", "Extensión no admitida (solo {extensiones})"
        ).format(extensiones=extensiones)
    if razon == "ruta_absoluta":
        return QCoreApplication.translate(
            "ModeloCatalogoVolumenes",
            "Una ruta del servidor no se puede usar: elige un archivo de la lista",
        )
    return QCoreApplication.translate(
        "ModeloCatalogoVolumenes",
        "Nombre no admitido: solo letras, números, punto, guion y guion bajo",
    )


def motivo_plantilla_no_clonable(plantilla: Plantilla, permisos: PermisosEfectivos | None) -> str:
    """Motivo (traducido) por el que una plantilla no se puede clonar; ``""`` si se puede.

    Con permisos desconocidos (``None``) no se deshabilita: se ofrece con el aviso de la vía.
    """
    if plantilla.bloqueo:
        return QCoreApplication.translate(
            "ModeloPlantillas",
            "Bloqueada ({bloqueo}): espera a que termine lo que Proxmox está haciendo con ella",
        ).format(bloqueo=plantilla.bloqueo)
    if permisos is not None and not permisos.tiene("VM.Clone", f"/vms/{plantilla.vmid}"):
        return QCoreApplication.translate("ModeloPlantillas", "Falta el permiso VM.Clone")
    return ""


# --- Modelos ----------------------------------------------------------------------------


class _ModeloOrigenBase(QAbstractTableModel):
    """Base común: tema para los colores y datos genéricos de las filas."""

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

    def _cabeceras(self) -> tuple[str, ...]:
        raise NotImplementedError

    def columnCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._cabeceras())

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

    def _elegible(self, fila: int) -> bool:
        raise NotImplementedError

    def flags(self, index: _Indice) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if self._elegible(index.row()):
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return Qt.ItemFlag.NoItemFlags  # deshabilitada: se ve, no se elige


class ModeloCatalogoVolumenes(_ModeloOrigenBase):
    """Volúmenes de un contenido (``iso`` o ``import``) en uno o varios storages del nodo.

    Columnas: Nombre, Almacenamiento, Nodo, Tamaño, Fecha y Nota (virtio-win o el motivo por el
    que la fila está deshabilitada).
    """

    COL_NOMBRE = 0
    COL_STORAGE = 1
    COL_NODO = 2
    COL_TAMANO = 3
    COL_FECHA = 4
    COL_NOTA = 5

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filas: list[FilaVolumen] = []

    def _cabeceras(self) -> tuple[str, ...]:
        return (
            QCoreApplication.translate("ModeloCatalogoVolumenes", "Nombre"),
            QCoreApplication.translate("ModeloCatalogoVolumenes", "Almacenamiento"),
            QCoreApplication.translate("ModeloCatalogoVolumenes", "Nodo"),
            QCoreApplication.translate("ModeloCatalogoVolumenes", "Tamaño"),
            QCoreApplication.translate("ModeloCatalogoVolumenes", "Fecha"),
            QCoreApplication.translate("ModeloCatalogoVolumenes", "Nota"),
        )

    def establecer_volumenes(self, volumenes: Iterable[Volumen], nodo: str = "") -> None:
        """Sustituye las filas por ``volumenes`` (todos del mismo ``nodo``)."""
        self._cargar([(v, nodo) for v in volumenes])

    def establecer_listados(self, listados: Iterable[ListadoStorage]) -> None:
        """Sustituye las filas por los volúmenes de cada listado, con su nodo."""
        self._cargar([(v, lst.nodo) for lst in listados for v in lst.volumenes])

    def _cargar(self, pares: Sequence[tuple[Volumen, str]]) -> None:
        filas = [FilaVolumen(v, nodo, motivo_volumen_no_admitido(v)) for v, nodo in pares]
        filas.sort(key=lambda f: (f.volumen.nombre.casefold(), f.volumen.storage, f.nodo))
        self.beginResetModel()
        self._filas = filas
        self.endResetModel()

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._filas)

    def fila(self, indice: int) -> FilaVolumen | None:
        """Fila de origen número ``indice``; ``None`` si está fuera de rango."""
        return self._filas[indice] if 0 <= indice < len(self._filas) else None

    def buscar_volid(self, volid: str) -> int:
        """Posición de la fila con ese volid, o ``-1``."""
        for i, f in enumerate(self._filas):
            if f.volumen.volid == volid:
                return i
        return -1

    def _elegible(self, fila: int) -> bool:
        return 0 <= fila < len(self._filas) and self._filas[fila].elegible

    def _nota(self, f: FilaVolumen) -> str:
        if f.motivo:
            return f.motivo
        if f.es_virtio_win:
            return QCoreApplication.translate(
                "ModeloCatalogoVolumenes", "Drivers virtio-win para Windows"
            )
        return ""

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._filas):
            return None
        f = self._filas[index.row()]
        v = f.volumen
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                v.nombre,
                v.storage,
                f.nodo or "—",
                formatear_bytes(v.tamano_bytes),
                formatear_fecha(v.creado),
                self._nota(f),
            )[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col == self.COL_TAMANO:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return tooltip_plano(f"{v.volid}\n{f.motivo}" if f.motivo else v.volid)
        if role == Qt.ItemDataRole.ForegroundRole:
            if not f.elegible:
                return self._color("texto_deshabilitado")
            if f.es_virtio_win and col == self.COL_NOTA:
                return self._color("secundario_texto")
            return None
        if role == Qt.ItemDataRole.AccessibleTextRole:
            partes = [v.nombre, v.storage, formatear_bytes(v.tamano_bytes)]
            if self._nota(f):
                partes.append(self._nota(f))
            return ", ".join(partes)
        if role == ROL_FILA:
            return f
        if role == ROL_ELEGIBLE:
            return f.elegible
        if role == ROL_FILTRO:
            return f"{v.nombre} {v.volid}"
        return None


class ModeloPlantillas(_ModeloOrigenBase):
    """Plantillas de Proxmox visibles (RF-O19): nombre, VMID, nodo, discos y nota/motivo."""

    COL_NOMBRE = 0
    COL_VMID = 1
    COL_NODO = 2
    COL_DISCOS = 3
    COL_NOTA = 4

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filas: list[FilaPlantilla] = []

    def _cabeceras(self) -> tuple[str, ...]:
        return (
            QCoreApplication.translate("ModeloPlantillas", "Nombre"),
            QCoreApplication.translate("ModeloPlantillas", "VMID"),
            QCoreApplication.translate("ModeloPlantillas", "Nodo"),
            QCoreApplication.translate("ModeloPlantillas", "Tamaño de los discos"),
            QCoreApplication.translate("ModeloPlantillas", "Nota"),
        )

    def establecer_plantillas(
        self, plantillas: Iterable[Plantilla], permisos: PermisosEfectivos | None = None
    ) -> None:
        """Sustituye las filas. Dos plantillas con el mismo nombre se distinguen por nodo y VMID
        (CA-O19.3) porque ambas columnas se muestran siempre."""
        filas = [FilaPlantilla(p, motivo_plantilla_no_clonable(p, permisos)) for p in plantillas]
        filas.sort(
            key=lambda f: (f.plantilla.nombre.casefold(), f.plantilla.nodo, f.plantilla.vmid)
        )
        self.beginResetModel()
        self._filas = filas
        self.endResetModel()

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._filas)

    def fila(self, indice: int) -> FilaPlantilla | None:
        return self._filas[indice] if 0 <= indice < len(self._filas) else None

    def buscar_vmid(self, vmid: int) -> int:
        """Posición de la plantilla con ese VMID, o ``-1``."""
        for i, f in enumerate(self._filas):
            if f.plantilla.vmid == vmid:
                return i
        return -1

    def _elegible(self, fila: int) -> bool:
        return 0 <= fila < len(self._filas) and self._filas[fila].elegible

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._filas):
            return None
        f = self._filas[index.row()]
        p = f.plantilla
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                p.nombre,
                str(p.vmid),
                p.nodo,
                formatear_bytes(p.disco_total_bytes),
                f.motivo,
            )[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (self.COL_VMID, self.COL_DISCOS):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and f.motivo:
            return tooltip_plano(f.motivo)
        if role == Qt.ItemDataRole.ForegroundRole and not f.elegible:
            return self._color("texto_deshabilitado")
        if role == Qt.ItemDataRole.AccessibleTextRole:
            texto = f"{p.nombre}, VMID {p.vmid}, {p.nodo}"
            return f"{texto}, {f.motivo}" if f.motivo else texto
        if role == ROL_FILA:
            return f
        if role == ROL_ELEGIBLE:
            return f.elegible
        if role == ROL_FILTRO:
            return f"{p.nombre} {p.vmid}"
        return None


class FiltroPorNombre(QSortFilterProxyModel):
    """Filtro por nombre sin distinguir mayúsculas ni acentos (``ROL_FILTRO``)."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._texto = ""
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortRole(Qt.ItemDataRole.DisplayRole)

    @staticmethod
    def _normalizar(texto: str) -> str:
        base = unicodedata.normalize("NFKD", texto)
        return "".join(c for c in base if not unicodedata.combining(c)).casefold()

    def establecer_texto(self, texto: str) -> None:
        """Fija el texto a buscar (vacío = todo) y refiltra."""
        self._texto = self._normalizar(texto.strip())
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: _Indice) -> bool:
        if not self._texto:
            return True
        modelo = self.sourceModel()
        valor = modelo.data(modelo.index(source_row, 0, source_parent), ROL_FILTRO)
        return self._texto in self._normalizar(str(valor or ""))


# --- Textos y formatos compartidos por las piezas del origen ---------------------------------
# Los nombres de las enumeraciones del núcleo (vías, SO, modos, estados) los pone ``textos.py``.


def simbolo_disponibilidad(disponibilidad: Disponibilidad) -> str:
    """Símbolo que refuerza el texto del estado (no se depende solo del color, RNF-O08)."""
    if disponibilidad == Disponibilidad.SI:
        return "✔"
    if disponibilidad == Disponibilidad.CON_AVISO:
        return "!"
    return "✖"


def texto_explicacion_via(estado: EstadoVia) -> str:
    """Motivo de una vía que no está (del todo) disponible; ``""`` si lo está.

    Parte de ``textos.texto_estado_via`` (versión, permiso, falta de almacenamiento) y añade la
    ruta exacta de Proxmox para pedirle al administrador que active el contenido que falta
    (CA-O15.6).
    """
    if estado.disponibilidad == Disponibilidad.SI:
        return ""
    texto = texto_estado_via(estado)
    contenido = ""
    if estado.codigo == CodigoError.IMPORTAR_SIN_STORAGE_IMPORT:
        contenido = "Import"
    elif estado.params.get("motivo") == "sin_storage_iso":
        contenido = "ISO image"
    if contenido:
        texto += " " + QCoreApplication.translate(
            "VistaCapacidades",
            "En Proxmox se activa en Datacenter → Almacenamiento → (el almacenamiento) → "
            "Editar → Contenido → {contenido}.",
        ).format(contenido=contenido)
    return texto


def texto_tiempo(segundos: float | None) -> str:
    """Duración legible: «45 s», «3 min 10 s» o «1 h 5 min»; ``«—»`` si no se conoce."""
    if segundos is None or segundos < 0:
        return "—"
    total = round(segundos)
    if total < 60:
        return f"{total} s"
    if total < 3600:
        return f"{total // 60} min {total % 60} s"
    return f"{total // 3600} h {(total % 3600) // 60} min"
