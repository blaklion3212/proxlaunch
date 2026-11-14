"""Privilegios que exigen las vías del origen del SO (RF-O24, arquitectura §9). Puro.

``PERMISOS_ORIGEN`` va aparte de ``PERMISOS_POR_RUTA`` de M1 (no lo toca): los cuatro
privilegios nuevos se evalúan **por vía**, de modo que el rol de 10 privilegios del MVP 3 sigue
creando MVs vacías sin avisos nuevos (CA-O24.4).
"""

from __future__ import annotations

from collections.abc import Mapping

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
