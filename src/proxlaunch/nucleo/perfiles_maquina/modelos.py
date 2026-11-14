"""Modelos de los perfiles de máquina (docs/arquitectura/mvp3.md §3.2).

Todos son inmutables. Un perfil guarda solo hardware: no existen campos para ``vmid``,
nombre de MV, nodo ni etiquetas (CA-P01.1, CA-P06.8). Las pistas de storage/bridge son
solo sugerencias (RF-P06).
"""

from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.modelos.origen import AjustesClon, ModoClon, TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ControladorScsi,
    Firmware,
    FormatoDisco,
    ModeloRed,
    OrigenSO,
)


class OrigenPerfil(StrEnum):
    FABRICA = "fabrica"
    USUARIO = "usuario"


PREFIJO_FABRICA = "fabrica."
ID_PREDETERMINADO = "fabrica.servidor-pequeno"


@dataclass(frozen=True)
class DiscoPerfil:
    tamano_gib: int
    bus: Bus = Bus.SCSI
    formato: FormatoDisco = FormatoDisco.AUTO
    discard: bool = True
    ssd: bool = True
    iothread: bool = True
    storage_preferido: str | None = None  # pista (RF-P06)


@dataclass(frozen=True)
class RedPerfil:
    modelo: ModeloRed = ModeloRed.VIRTIO
    vlan: int | None = None
    bridge_preferido: str | None = None  # pista


@dataclass(frozen=True)
class BallooningPerfil:
    activo: bool
    minimo_mib: int


@dataclass(frozen=True)
class PistaOrigen:
    """«Origen sugerido» de un perfil (RF-O26): solo nombres, nunca volids de otro servidor.

    ``nombre_fuente`` es el ISO, la imagen o la plantilla (``""`` = sin fuente). Se resuelve
    contra el servidor al aplicar el perfil. Nunca URL, ruta local ni checksum (INV-O6).
    """

    nombre_fuente: str = ""
    storage_preferido: str | None = None  # ISO/imagen: pista del storage
    drivers: str | None = None  # nombre del ISO de virtio-win; None = detectar
    sin_drivers: bool = False
    modo_clon: ModoClon = ModoClon.AUTOMATICO
    ajustes: AjustesClon = field(default_factory=AjustesClon)
    ampliar_a_gib: int | None = None


@dataclass(frozen=True)
class ConfigPerfil:
    """Lista blanca de campos de hardware de un perfil (§2 de los requisitos)."""

    firmware: Firmware = Firmware.SEABIOS
    sockets: int = 1
    cores: int = 2
    tipo_cpu: str = "x86-64-v2-AES"
    memoria_mib: int = 2048
    ballooning: BallooningPerfil | None = None
    con_disco: bool = True
    discos: tuple[DiscoPerfil, ...] = ()
    storage_efi_preferido: str | None = None
    controlador_scsi: ControladorScsi = ControladorScsi.VIRTIO_SINGLE
    redes: tuple[RedPerfil, ...] = ()
    origen: OrigenSO = OrigenSO.DISCO_VACIO
    # MVP 4 (al final y con valor por defecto)
    tipo_so: TipoSO | None = None
    tpm: bool = False
    agente_qemu: bool = False
    pista_origen: PistaOrigen | None = None


@dataclass(frozen=True)
class PerfilMaquina:
    id: str  # uuid4().hex (usuario) o "fabrica.<clave>"
    nombre: str  # fábrica: el traducido que pasa la interfaz (el núcleo no tiene textos)
    descripcion: str
    origen: OrigenPerfil
    config: ConfigPerfil
