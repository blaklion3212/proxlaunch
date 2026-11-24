"""Privilegios que exigen las vías del origen del SO (RF-O24, arquitectura §9). Puro.

``PERMISOS_ORIGEN`` va aparte de ``PERMISOS_POR_RUTA`` de M1 (no lo toca): los cuatro
privilegios nuevos se evalúan **por vía**, de modo que el rol de 10 privilegios del MVP 3 sigue
creando MVs vacías sin avisos nuevos (CA-O24.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.hardware_cluster.modelos import TipoMapeo
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.cpu import PREFIJO_CPU_PERSONALIZADA

# privilegio -> (plantilla de ruta, vía principal). ``VM.Config.Disk`` sirve además a la vía
# «ampliar_disco» (resize); ``Sys.Modify`` en ``/`` solo se reconoce (administrador): nunca se pide.
PERMISOS_ORIGEN: Mapping[str, tuple[str, str]] = {
    "VM.Config.Disk": ("/vms/{vmid}", "orden_arranque"),
    "VM.Clone": ("/vms/{vmid}", "clonar"),
    "Datastore.AllocateTemplate": ("/storage/{storage}", "subir_iso"),
    "Sys.AccessNetwork": ("/nodes/{nodo}", "descargar_url"),
    "Sys.Modify": ("/", "descargar_url"),
}

# Rol ProxLaunchCreador ampliado: los 10 de M1 y los 4 de este MVP (RF-O24).
ROL_PROXLAUNCH: tuple[str, ...] = (
    "VM.Allocate",
    "VM.Audit",
    "VM.Config.Options",
    "VM.Config.HWType",
    "VM.Config.CPU",
    "VM.Config.Memory",
    "VM.Config.Network",
    "Datastore.AllocateSpace",
    "SDN.Use",
    "Sys.Audit",
    "VM.Config.Disk",
    "VM.Clone",
    "Datastore.AllocateTemplate",
    "Sys.AccessNetwork",
)

# Fase A (0.6): privilegios opcionales (no forman parte del rol; solo habilitan opciones). Aparte
# de ``ROL_PROXLAUNCH``, que sigue con 14. (privilegio, ruta)
PRIVILEGIOS_OPCIONALES: tuple[tuple[str, str], ...] = (
    ("VM.PowerMgmt", "/vms"),
    ("Pool.Audit", "/pool"),
)


@dataclass(frozen=True)
class PrivilegioOpcional:
    """Privilegio opcional de la guía de permisos. ``no_verificado``: hecho inferido, sin probar."""

    privilegio: str
    ruta: str
    no_verificado: bool = False


# Fase C (0.8): SDN. La zona de una VNet no se conoce de antemano (solo por el texto de un 403),
# así que la guía usa la ruta genérica con un marcador y los privilegios van como no verificados.
ZONA_LOCAL: Final = "localnetwork"
RUTA_ZONA_GENERICA: Final = "/sdn/zones/<zona>"
# ``PRIVILEGIOS_OPCIONALES`` conserva su forma de la fase A (pares); estos dos se suman en
# ``privilegios_opcionales`` cuando se conocen las capacidades.
PRIVILEGIOS_SDN_OPCIONALES: tuple[PrivilegioOpcional, ...] = (
    PrivilegioOpcional("SDN.Use", RUTA_ZONA_GENERICA, no_verificado=True),
    PrivilegioOpcional("SDN.Audit", RUTA_ZONA_GENERICA, no_verificado=True),
)

# Fase D (0.9): mapeos del clúster (DT-D17). No forman parte del rol (sigue con 14): solo habilitan
# opciones. Todos son hechos inferidos de la documentación, aún sin probar en un servidor.
RUTA_MAPEO_PCI: Final = "/mapping/pci"
RUTA_MAPEO_USB: Final = "/mapping/usb"
RUTA_MAPEO_CPU: Final = "/mapping/cpu"
PRIVILEGIO_MAPEO_USAR: Final = "Mapping.Use"
PRIVILEGIOS_D_OPCIONALES: tuple[PrivilegioOpcional, ...] = (
    PrivilegioOpcional(PRIVILEGIO_MAPEO_USAR, RUTA_MAPEO_PCI, no_verificado=True),
    PrivilegioOpcional(PRIVILEGIO_MAPEO_USAR, RUTA_MAPEO_USB, no_verificado=True),
    PrivilegioOpcional(PRIVILEGIO_MAPEO_USAR, RUTA_MAPEO_CPU, no_verificado=True),
)

# Ruta que se muestra cuando se desconoce el almacén de snippets (la guía lo indica con texto).
RUTA_STORAGE_SNIPPETS_DESCONOCIDO = "/storage/<almacén de snippets>"


def ruta_almacen_snippets(almacen: str | None) -> str:
    """``/storage/<almacén>`` del almacén de snippets, o la ruta genérica si no se conoce."""
    return f"/storage/{almacen}" if almacen else RUTA_STORAGE_SNIPPETS_DESCONOCIDO


def privilegios_snippets_8x(almacen: str | None) -> tuple[PrivilegioOpcional, ...]:
    """Privilegios que se proponen en 8.x para usar snippets (B3), solo sobre el almacén de
    snippets (nunca sobre todo ``/storage``): ``Datastore.AllocateSpace`` primero y
    ``Datastore.Allocate`` como alternativa no verificada."""
    ruta = ruta_almacen_snippets(almacen)
    return (
        PrivilegioOpcional("Datastore.AllocateSpace", ruta),
        PrivilegioOpcional("Datastore.Allocate", ruta, no_verificado=True),
    )


def privilegios_opcionales(
    caps: Capacidades | None, almacen_snippets: str | None = None
) -> tuple[PrivilegioOpcional, ...]:
    """Opcionales que existen en la versión (RF-B5.1): los de la fase A y los de la fase B.

    ``caps`` ``None`` = solo los de la fase A. Nunca incluye un privilegio que no existe en la
    versión: ``VM.Monitor`` solo antes de 9.0, ``VM.GuestAgent.Audit`` desde 9.0 y los de
    snippets de 8.x (``privilegios_snippets_8x``: ``AllocateSpace`` y, no verificado,
    ``Allocate``) solo antes de 9.0, sobre ``/storage/<almacén de snippets>`` (``almacen_snippets``
    si se conoce). ``PRIVILEGIOS_OPCIONALES`` y ``ROL_PROXLAUNCH`` no cambian.
    """
    lista = [PrivilegioOpcional(p, r) for p, r in PRIVILEGIOS_OPCIONALES]
    if caps is None:
        return tuple(lista)
    lista.append(PrivilegioOpcional("VM.Config.Cloudinit", "/vms"))
    lista.extend(PRIVILEGIOS_SDN_OPCIONALES)
    # Fase D: mapeos PCI/USB siempre; ``/mapping/cpu`` solo si la versión lo usa (9.2).
    for d in PRIVILEGIOS_D_OPCIONALES:
        if d.ruta != RUTA_MAPEO_CPU or caps.tiene(Funcion.CPU_PERSONALIZADA_POR_MAPPING):
            lista.append(d)
    if caps.tiene(Funcion.PRIVILEGIOS_GUEST_AGENT):
        lista.append(PrivilegioOpcional("VM.GuestAgent.Audit", "/vms"))
    else:
        lista.append(PrivilegioOpcional("VM.Monitor", "/vms"))
    if not caps.tiene(Funcion.CICUSTOM_CON_ALLOCATESPACE):
        lista.extend(privilegios_snippets_8x(almacen_snippets))
    return tuple(lista)


def ruta_sdn(zona: str, red: str | None = None, vlan: int | None = None) -> str:
    """Ruta de ACL de SDN: ``/sdn/zones/<zona>[/<red>[/<vlan>]]`` (la VLAN solo cuenta con red)."""
    ruta = f"/sdn/zones/{zona}"
    if red is not None:
        ruta += f"/{red}"
        if vlan is not None:
            ruta += f"/{vlan}"
    return ruta


def estado_sdn_fuera_de_local(permisos: PermisosEfectivos | None) -> bool | None:
    """¿Tiene ``SDN.Use`` para alguna zona distinta de ``localnetwork``? (DT-C19).

    ``True`` si lo hay en ``/sdn/zones/<z>[/…]`` con ``z`` ≠ ``localnetwork`` o heredado de ``/``,
    ``/sdn`` o ``/sdn/zones`` con propagate; ``None`` si los permisos se desconocen.
    """
    if permisos is None:
        return None
    prefijo = "/sdn/zones/"
    for ruta, privs in permisos.rutas.items():
        if "SDN.Use" not in privs:
            continue
        if ruta.rstrip("/") in ("", "/sdn", "/sdn/zones"):
            if privs["SDN.Use"]:
                return True
        elif ruta.startswith(prefijo):
            zona = ruta[len(prefijo) :].split("/", 1)[0]
            if zona and zona != ZONA_LOCAL:
                return True
    return False


def ruta_mapeo(tipo: TipoMapeo, id_mapeo: str) -> str:
    """Ruta de ACL de un mapeo concreto: ``/mapping/<tipo>/<id>``."""
    return f"{RUTA_MAPEO_PCI if tipo == TipoMapeo.PCI else RUTA_MAPEO_USB}/{id_mapeo}"


def estado_mapeo(permisos: PermisosEfectivos | None, tipo: TipoMapeo, id_mapeo: str) -> bool | None:
    """¿Tiene ``Mapping.Use`` sobre ese mapeo? ``None`` = permisos desconocidos (CA-D5.1.3)."""
    return estado_privilegio(permisos, PRIVILEGIO_MAPEO_USAR, ruta_mapeo(tipo, id_mapeo))


def _uso_bajo(permisos: PermisosEfectivos, privilegio: str, ruta: str) -> bool:
    """``True`` si el privilegio rige en ``ruta`` o en alguna ruta concreta por debajo de ella."""
    if tiene_privilegio(permisos.rutas, ruta, privilegio):
        return True
    return any(
        privilegio in privs and p.startswith(ruta + "/") for p, privs in permisos.rutas.items()
    )


def estado_algun_mapeo(permisos: PermisosEfectivos | None) -> bool | None:
    """¿Hay ``Mapping.Use`` en alguna ruta de mapeo PCI o USB (general o de un id)?"""
    if permisos is None:
        return None
    return any(
        _uso_bajo(permisos, PRIVILEGIO_MAPEO_USAR, r) for r in (RUTA_MAPEO_PCI, RUTA_MAPEO_USB)
    )


def estado_cpu_personalizada(
    permisos: PermisosEfectivos | None, caps: Capacidades, nombre: str | None = None
) -> bool | None:
    """¿Puede usar un modelo de CPU personalizado? (DT-D17).

    9.2: ``Mapping.Use`` en ``/mapping/cpu/<nombre sin "custom-">``; con ``nombre`` ``None`` basta
    en cualquier modelo. 8.4–9.1: ``VM.Config.CPU`` en ``/vms`` y ``Sys.Audit`` en ``/nodes``.
    ``None`` = permisos desconocidos.
    """
    if permisos is None:
        return None
    if caps.tiene(Funcion.CPU_PERSONALIZADA_POR_MAPPING):
        if nombre is None:
            return _uso_bajo(permisos, PRIVILEGIO_MAPEO_USAR, RUTA_MAPEO_CPU)
        simple = nombre.removeprefix(PREFIJO_CPU_PERSONALIZADA)
        return tiene_privilegio(permisos.rutas, f"{RUTA_MAPEO_CPU}/{simple}", PRIVILEGIO_MAPEO_USAR)
    return tiene_privilegio(permisos.rutas, "/vms", "VM.Config.CPU") and tiene_privilegio(
        permisos.rutas, "/nodes", "Sys.Audit"
    )


def privilegios_agente(caps: Capacidades) -> tuple[str, ...]:
    """Privilegios que permiten sondear el agente (basta uno): según la versión."""
    if caps.tiene(Funcion.PRIVILEGIOS_GUEST_AGENT):
        return ("VM.GuestAgent.Audit", "VM.GuestAgent.Unrestricted")
    return ("VM.Monitor",)


def privilegios_cloudinit(caps: Capacidades) -> tuple[str, ...]:
    """Privilegios aceptables para aplicar cloud-init (basta uno), de más a menos propio.

    Hasta 9.1 vale también ``VM.Config.Network`` (en 9.0–9.1 con aviso: versión incierta); desde
    9.2 solo ``VM.Config.Cloudinit``.
    """
    if caps.tiene(Funcion.CLOUDINIT_PRIVILEGIO_PROPIO):
        return ("VM.Config.Cloudinit",)
    return ("VM.Config.Cloudinit", "VM.Config.Network")


_CREAR = frozenset(
    {
        "VM.Allocate",
        "VM.Config.CPU",
        "VM.Config.Memory",
        "VM.Config.Network",
        "VM.Config.HWType",
        "VM.Config.Options",
        "Datastore.AllocateSpace",
        "SDN.Use",
    }
)
_PETICIONES: Mapping[str, frozenset[str]] = {
    "upload": frozenset({"Datastore.AllocateTemplate"}),
    "download-url": frozenset({"Datastore.AllocateTemplate", "Sys.AccessNetwork"}),
    "crear_iso": _CREAR,
    "crear_import": _CREAR,
    "clone": frozenset({"VM.Clone", "VM.Allocate", "Datastore.AllocateSpace", "SDN.Use"}),
    "config": frozenset({"VM.Config.CPU", "VM.Config.Memory", "VM.Config.Options"}),
    "resize": frozenset({"VM.Config.Disk"}),
}


def tiene_privilegio(permisos: Mapping[str, Mapping[str, int]], ruta: str, privilegio: str) -> bool:
    """Semántica de ``/access/permissions``: ``{ruta: {privilegio: propagate}}``.

    ``1`` = concedido y heredado por las subrutas; ``0`` = solo en esa ruta exacta. Cuenta el
    privilegio en la propia ruta o en un ancestro con propagate=1. En ``/storage`` también se
    acepta en un ``/storage/<id>`` concreto (la lista de storages se filtra por id).
    """
    for p, privs in permisos.items():
        if privilegio not in privs:
            continue
        propaga = bool(privs[privilegio])
        if p == ruta:
            return True
        if propaga and (p == "/" or ruta.startswith(p.rstrip("/") + "/")):
            return True
        if ruta == "/storage" and p.startswith("/storage/"):
            return True
    return False


def estado_privilegio(
    permisos: PermisosEfectivos | None, privilegio: str, ruta: str
) -> bool | None:
    """``True``/``False`` si se conocen los permisos; ``None`` = desconocido (INV-O10)."""
    if permisos is None:
        return None
    return tiene_privilegio(permisos.rutas, ruta, privilegio)


def privilegios_de_peticion(accion: str) -> frozenset[str]:
    """Privilegios que exige cada escritura del MVP 4 (prueba de contrato CA-O24.8).

    ``accion``: ``upload``, ``download-url``, ``crear_iso``, ``crear_import``, ``clone``,
    ``config`` o ``resize``. Todos están dentro de ``ROL_PROXLAUNCH``.
    """
    try:
        return _PETICIONES[accion]
    except KeyError:
        raise ValueError(f"acción desconocida: {accion}") from None
