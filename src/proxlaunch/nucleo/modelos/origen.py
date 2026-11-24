"""Modelos del origen del sistema operativo (MVP 4, docs/arquitectura/mvp4.md §3.1).

Solo datos: sin lógica de negocio ni serialización a archivos (esa vive en
``archivos/esquema_config.py``). Todos los modelos son inmutables.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias


class TipoSO(StrEnum):
    """Sistema operativo invitado para el asistente (RF-O13)."""

    LINUX = "linux"
    WINDOWS_11 = "windows_11"
    WINDOWS_SERVER_2022_2025 = "windows_server_2022_2025"
    WINDOWS_10 = "windows_10"
    WINDOWS_SERVER_2016_2019 = "windows_server_2016_2019"
    OTRO = "otro"


class ModoClon(StrEnum):
    """Modo de clonado de una plantilla."""

    AUTOMATICO = "automatico"
    ENLAZADO = "enlazado"
    COMPLETO = "completo"


@dataclass(frozen=True)
class RefVolumen:
    """Fuente de archivo del servidor (ISO o imagen de disco)."""

    nombre: str = ""  # nombre de archivo sin storage ("alpine.iso"); "" = sin elegir
    volid: str | None = None  # "local:iso/alpine.iso" cuando está resuelto o lo escribió el usuario


@dataclass(frozen=True)
class RefPlantilla:
    """Referencia a una plantilla de MV."""

    nombre: str = ""  # referencia en archivos y CSV (DT-O13)
    vmid: int | None = None  # pista (lote guardado) o resuelto (plan)
    nodo: str | None = None  # resuelto por el plan; nunca se guarda


@dataclass(frozen=True)
class AjustesClon:
    """Ajustes sobre la plantilla; ``None`` = «igual que la plantilla» (CA-O22.1)."""

    sockets: int | None = None
    cores: int | None = None
    tipo_cpu: str | None = None
    memoria_mib: int | None = None
    disco_gib: int | None = None  # tamaño ABSOLUTO del disco principal


@dataclass(frozen=True)
class DetalleIso:
    """Origen ISO: imagen de instalación y, en Windows, drivers virtio-win."""

    iso: RefVolumen = field(default_factory=RefVolumen)
    drivers: RefVolumen | None = None  # None = detectar virtio-win (solo Windows, CA-O14.1)
    sin_drivers: bool = False  # «Crear sin los drivers» confirmado (CA-O14.3)


@dataclass(frozen=True)
class ImagenDisco:
    """Imagen de un disco adicional (índice ≥ 1) del origen «importar disco» (DT-D14)."""

    indice: int  # índice en cfg.discos (≥ 1)
    imagen: RefVolumen | None = None  # None + crear_vacio=False -> pendiente (V-D27)
    crear_vacio: bool = False
    tamano_virtual_bytes: int | None = None  # sesión; NUNCA se escribe en archivos


@dataclass(frozen=True)
class DetalleImportacion:
    """Origen «importar disco»: imagen del contenido ``import`` del servidor."""

    imagen: RefVolumen = field(default_factory=RefVolumen)
    ampliar_a_gib: int | None = None  # CA-O18.4; None = tamaño de la imagen
    tamano_virtual_bytes: int | None = None  # sesión o API; NUNCA se escribe en archivos
    # Fase D (0.9): imágenes de los discos 1.. (el disco 0 usa ``imagen``); () = como 0.8.0
    otras: tuple[ImagenDisco, ...] = ()


@dataclass(frozen=True)
class DetalleClon:
    """Origen «clonar plantilla»."""

    plantilla: RefPlantilla = field(default_factory=RefPlantilla)
    modo: ModoClon = ModoClon.AUTOMATICO
    ajustes: AjustesClon = field(default_factory=AjustesClon)
    storage_destino: str | None = None  # solo completo (avanzado); None = el de la plantilla
    modo_efectivo: ModoClon | None = None  # ENLAZADO/COMPLETO, lo fija el plan; no se guarda


DetalleOrigen: TypeAlias = DetalleIso | DetalleImportacion | DetalleClon
