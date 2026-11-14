"""Modelos del inventario descubierto: versión, nodos, storages, bridges y topología."""

import math
from dataclasses import dataclass

from proxlaunch.nucleo.errores import ErrorProxLaunch

_GIB = 1024**3
# Backends donde el espacio se puede sobreasignar (CT-5, P-01).
TIPOS_STORAGE_THIN = frozenset({"lvmthin", "zfspool", "rbd"})


@dataclass(frozen=True)
class Version:
    """Versión de Proxmox VE."""

    texto: str
    mayor: int
    menor: int
    parche: int


@dataclass(frozen=True)
class Nodo:
    """Nodo del clúster (o servidor individual)."""

    nombre: str
    en_linea: bool
    mem_libre_mib: int | None
    cpus: int | None


@dataclass(frozen=True)
class Storage:
    """Almacenamiento visible desde un nodo."""

    id: str
    tipo: str
    contenido: frozenset[str]
    compartido: bool
    activo: bool
    total_bytes: int
    libre_bytes: int

    @property
    def es_thin(self) -> bool:
        """Indica si el backend admite sobreasignación (lvmthin, zfspool, rbd)."""
        return self.tipo in TIPOS_STORAGE_THIN

    @property
    def libre_gib(self) -> float:
        """Espacio libre en GiB, redondeado hacia abajo a 1 decimal."""
        return math.floor(self.libre_bytes / _GIB * 10) / 10


@dataclass(frozen=True)
class Bridge:
    """Red puente (bridge) de un nodo."""

    nombre: str
    tipo: str
    vlan_aware: bool


@dataclass(frozen=True)
class Topologia:
    """Forma del servidor: individual o clúster."""

    es_cluster: bool
    nombre_cluster: str | None
    nodos: tuple[Nodo, ...]


@dataclass(frozen=True)
class VMRemota:
    """Máquina o contenedor visible en ``/cluster/resources?type=vm`` (aviso V-L06)."""

    vmid: int
    nombre: str
    nodo: str
    tipo: str  # "qemu" o "lxc"


@dataclass
class Inventario:
    """Todo lo descubierto en la conexión."""

    version: Version
    topologia: Topologia
    proximo_vmid: int
    storages: dict[str, tuple[Storage, ...]]  # por nodo
    bridges: dict[str, tuple[Bridge, ...]]  # por nodo
    errores_por_nodo: dict[str, ErrorProxLaunch]
