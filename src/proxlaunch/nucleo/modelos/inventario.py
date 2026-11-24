"""Modelos del inventario descubierto: versión, nodos, storages, bridges y topología."""

import math
from dataclasses import dataclass, field

from proxlaunch.nucleo.arquitectura.modelos import ArquitecturaNodo
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor

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
    formatos: frozenset[str] | None = None  # de ?format=1 si se pidió (CA-O04.6)

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
    mtu: int | None = None  # fase C: de "mtu" de GET …/network; None = desconocida


@dataclass(frozen=True)
class RedVirtual:
    """VNet de SDN visible en un nodo (``GET …/network?type=any_bridge``). Texto no confiable."""

    nombre: str  # iface validado con RE_NOMBRE_RED
    alias: str | None  # comments saneado (≤ 64, sin control ni marcado)
    vlan_aware: bool
    ipam: str | None = None
    tipo_declarado: bool = True  # False = la entrada no traía type (supuesto [A]); la filtra I3
    zona: str | None = None  # reservado (RF-C2.6); en 0.8.0 siempre None


@dataclass(frozen=True)
class RecursoVM:
    """Una fila de ``GET /cluster/resources?type=vm``, ya interpretada con tolerancia (RF-C1.4)."""

    vmid: int
    nombre: str | None  # None = aún sin nombre
    nodo: str | None
    tipo: str  # "qemu" | "lxc" | otro
    estado: str | None  # running | stopped | unknown | None
    bloqueo: str | None
    plantilla: bool | None  # None = aún no informado
    etiquetas: tuple[str, ...]  # en minúsculas, separadas por [;, ]+ ; () si tags no es str


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
    # MVP 4 (al final y con valor por defecto)
    storages_todos: dict[str, tuple[Storage, ...]] = field(default_factory=dict)  # todo contenido
    catalogo: CatalogoServidor | None = None
    # Fase C (0.8): VNets de SDN por nodo y el error de su lectura (no rompe nada, CA-C2.1.3)
    redes_sdn: dict[str, tuple[RedVirtual, ...]] = field(default_factory=dict)
    errores_sdn: dict[str, ErrorProxLaunch] = field(default_factory=dict)
    # Fase D (0.9): arquitectura por nodo; un nodo ausente = ``DESCONOCIDA`` (DT-D6)
    arquitecturas: dict[str, ArquitecturaNodo] = field(default_factory=dict)
    # ``/cluster/resources`` de la conexión ({nodo: host-arch | None}); ``None`` si no se leyó.
    # Sirve para volver a detectar un nodo con el mismo criterio que el descubrimiento.
    recursos_arquitectura: dict[str, str | None] | None = None
