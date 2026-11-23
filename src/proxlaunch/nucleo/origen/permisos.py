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
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos

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
