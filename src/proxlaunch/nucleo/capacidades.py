"""Tabla de capacidades por versión de Proxmox (RF-09).

Es el ÚNICO lugar donde se comparan versiones: el resto del código pregunta
``caps.tiene(Funcion.X)`` y nunca escribe condiciones de versión (CA-09.6).
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from proxlaunch.nucleo.modelos.inventario import Version

VERSION_MINIMA: tuple[int, int] = (8, 4)
# Última versión probada; una mayor se permite con aviso informativo (CA-09.3, S-4).
ULTIMA_VERSION_CONOCIDA: tuple[int, int] = (9, 2)
# Versiones conocidas, de la mínima a la última (selector de versión forzada, RF-26).
VERSIONES_CONOCIDAS: tuple[tuple[int, int], ...] = (
    (8, 4),
    (9, 0),
    (9, 1),
    (9, 2),
)

_PATRON_VERSION = re.compile(r"^\s*(\d+)\.(\d+)(?:[.-](\d+))?")


class Funcion(StrEnum):
    """Funciones cuya disponibilidad depende de la versión."""

    CLAVES_MS_2023 = "claves_ms_2023"  # claves Microsoft 2023 en efidisk0 (9.1)
    ETIQUETAS = "etiquetas"  # parámetro ``tags`` al crear (RF-L24)
    # Fase B (0.7)
    CLOUDINIT = "cloudinit"  # B1: parámetros ``ci*`` e ``ipconfigN``
    SNIPPETS_CICUSTOM = "snippets_cicustom"  # B4: ``cicustom`` con snippets
    AGENTE_IP = "agente_ip"  # B3: ``agent/network-get-interfaces``
    # Marcadores de cambio de privilegio (se comparan solo aquí; fáciles de mover, R-B8)
    PRIVILEGIOS_GUEST_AGENT = "privilegios_guest_agent"  # VM.Monitor -> VM.GuestAgent.* (9.0)
    CLOUDINIT_PRIVILEGIO_INCIERTO = "cloudinit_privilegio_incierto"  # zona 9.0–9.1 (aviso)
    CLOUDINIT_PRIVILEGIO_PROPIO = "cloudinit_privilegio_propio"  # solo VM.Config.Cloudinit (9.2)
    CICUSTOM_CON_ALLOCATESPACE = "cicustom_con_allocatespace"  # Datastore.Allocate -> AllocateSpace
    # Fase C (0.8)
    INVENTARIO_LOTES = "inventario_lotes"  # C1: lotes del servidor (etiquetas y notas)
    VNETS_SDN = "vnets_sdn"  # C2: VNets de SDN con ``type=any_bridge``
    FIREWALL_GRUPO = "firewall_grupo"  # C3: grupos de seguridad del firewall
    REESCRIBIR_RED_CLON = "reescribir_red_clon"  # C4: reescribir ``netN`` del clon
    # Fase D (0.9)
    MAPEO_DRIVER_KEEP = "mapeo_driver_keep"  # D3: ``driver=keep`` en ``hostpciN`` (9.1)
    CPU_PERSONALIZADA_POR_MAPPING = "cpu_personalizada_por_mapping"  # D3: ``/mapping/cpu`` (9.2)
    CAPACIDADES_POR_ARCH = "capacidades_por_arch"  # D3: ``capabilities/qemu/cpu?arch=`` (9.2)
    HOST_ARCH_EN_RESOURCES = (
        "host_arch_en_resources"  # D2: ``host-arch`` en ``/cluster/resources`` (9.2)
    )
    NODO_ARM64 = "nodo_arm64"  # D2: nodos arm64 (9.2); solo elige la variante del texto V-D05


# Única tabla: función -> (mayor, menor) desde la que está disponible.
TABLA: dict[Funcion, tuple[int, int]] = {
    Funcion.CLAVES_MS_2023: (9, 1),
    Funcion.ETIQUETAS: (7, 3),  # todas las versiones soportadas (>= 8.0) la admiten
    Funcion.CLOUDINIT: (8, 0),
    Funcion.SNIPPETS_CICUSTOM: (8, 0),
    Funcion.AGENTE_IP: (8, 0),
    Funcion.PRIVILEGIOS_GUEST_AGENT: (9, 0),
    Funcion.CLOUDINIT_PRIVILEGIO_INCIERTO: (9, 0),
    Funcion.CLOUDINIT_PRIVILEGIO_PROPIO: (9, 2),
    Funcion.CICUSTOM_CON_ALLOCATESPACE: (9, 0),
    Funcion.INVENTARIO_LOTES: (8, 0),
    Funcion.VNETS_SDN: (8, 0),
    Funcion.FIREWALL_GRUPO: (8, 0),
    Funcion.REESCRIBIR_RED_CLON: (8, 0),
    Funcion.MAPEO_DRIVER_KEEP: (9, 1),
    Funcion.CPU_PERSONALIZADA_POR_MAPPING: (9, 2),
    Funcion.CAPACIDADES_POR_ARCH: (9, 2),
    Funcion.HOST_ARCH_EN_RESOURCES: (9, 2),
    Funcion.NODO_ARM64: (9, 2),
}


@dataclass(frozen=True)
class Capacidades:
    """Capacidades efectivas para una versión (real o forzada)."""

    version: tuple[int, int]
    forzada: bool

    def tiene(self, funcion: Funcion) -> bool:
        """Indica si la función está disponible en esta versión."""
        return self.version >= TABLA[funcion]

    def requisito(self, funcion: Funcion) -> tuple[int, int]:
        """Versión mínima de la función (para mostrar «Requiere 8.2...»)."""
        return TABLA[funcion]

    def es_soportada(self) -> bool:
        """Indica si la versión cumple la mínima del programa (CA-09.2)."""
        return self.version >= VERSION_MINIMA


def admite_etiquetas(version: tuple[int, int]) -> bool:
    """Indica si la versión admite ``tags`` al crear una MV (desde 7.3)."""
    return version >= TABLA[Funcion.ETIQUETAS]


def asistente_plantilla_disponible(caps: Capacidades | None) -> bool:
    """B2 (RF-B0.4): con la mínima 8.4 el asistente está disponible con cualquier sesión (DT-D3)."""
    return caps is not None


def es_rama_8(version: tuple[int, int]) -> bool:
    """Indica si la versión pertenece a la rama 8.x (aviso V-D02, sin soporte tras 9.x)."""
    return version[0] == 8


def interpretar_version(texto: str) -> tuple[Version, bool]:
    """Interpreta el texto de ``/version`` ("8.2.4", "9.2", "7.4-17").

    Devuelve ``(version, advertencia)``. Con un formato inesperado se usa la versión
    mínima y ``advertencia`` es ``True`` para que quien llame lo registre (CA-09.5).
    """
    coincidencia = _PATRON_VERSION.match(texto) if isinstance(texto, str) else None
    if coincidencia is None:
        mayor, menor = VERSION_MINIMA
        return Version(str(texto), mayor, menor, 0), True
    mayor = int(coincidencia.group(1))
    menor = int(coincidencia.group(2))
    parche = int(coincidencia.group(3) or 0)
    return Version(texto, mayor, menor, parche), False


def capacidades_para(version: Version, forzada: tuple[int, int] | None) -> Capacidades:
    """Capacidades para la versión detectada o, si se indica, la forzada (RF-26)."""
    if forzada is not None:
        return Capacidades(version=forzada, forzada=True)
    return Capacidades(version=(version.mayor, version.menor), forzada=False)
