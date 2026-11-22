"""Disponibilidad de las opciones de la fase A según permisos, versión y pools (DT-A8). Puro.

La interfaz solo pinta el resultado; las reglas (privilegio y versión) viven aquí y en
``capacidades.py``.
"""

from __future__ import annotations

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, EstadoPools, OpcionA, PoolsServidor
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.origen.permisos import estado_privilegio

RUTA_VMS = "/vms"
RUTA_POOLS = "/pool"
PRIVILEGIO_ENCENDER = "VM.PowerMgmt"
PRIVILEGIO_OPCIONES = "VM.Config.Options"
PRIVILEGIO_RED = "VM.Config.Network"
PRIVILEGIO_POOLS = "Pool.Audit"

# opción -> privilegio exigido en ``/vms`` (POOL se decide por el estado de la lectura de pools).
PRIVILEGIO_DE: dict[OpcionA, str] = {
    OpcionA.ENCENDER: PRIVILEGIO_ENCENDER,
    OpcionA.ARRANQUE_AUTO: PRIVILEGIO_OPCIONES,
    OpcionA.ARRANQUE_ORDEN: PRIVILEGIO_OPCIONES,
    OpcionA.NOTAS: PRIVILEGIO_OPCIONES,
    OpcionA.ETIQUETAS: PRIVILEGIO_OPCIONES,
    OpcionA.PROTEGER: PRIVILEGIO_OPCIONES,
    OpcionA.MTU: PRIVILEGIO_RED,
    OpcionA.LIMITE_RED: PRIVILEGIO_RED,
}

# opción -> función con versión mínima (hoy solo las etiquetas dependen de la versión).
_FUNCION_DE: dict[OpcionA, Funcion] = {OpcionA.ETIQUETAS: Funcion.ETIQUETAS}


def _estado_pools(pools: PoolsServidor) -> EstadoOpcion:
    pool = OpcionA.POOL
    if pools.estado == EstadoPools.OK:
        if pools.ids:
            return EstadoOpcion(pool, Disponibilidad.SI)
        # Lista vacía con Pool.Audit: no hay pools; la lista solo ofrece «Ninguno».
        return EstadoOpcion(pool, Disponibilidad.CON_AVISO, None, {"motivo": "sin_pools"})
    if pools.estado == EstadoPools.SIN_PERMISO:
        return EstadoOpcion(
            pool,
            Disponibilidad.NO,
            CodigoError.POOLS_SIN_PERMISO,
            {"privilegio": PRIVILEGIO_POOLS, "ruta": RUTA_POOLS},
        )
    if pools.estado == EstadoPools.DESCONOCIDO:
        return EstadoOpcion(
            pool,
            Disponibilidad.CON_AVISO,
            CodigoError.POOLS_DESCONOCIDO,
            {"privilegio": PRIVILEGIO_POOLS, "ruta": RUTA_POOLS},
        )
    if pools.estado == EstadoPools.ERROR:
        return EstadoOpcion(pool, Disponibilidad.NO, CodigoError.POOLS_ERROR)
    return EstadoOpcion(pool, Disponibilidad.NO, None, {"motivo": "no_leido"})


def disponibilidad_opciones(
    permisos: PermisosEfectivos | None, caps: Capacidades, pools: PoolsServidor
) -> dict[OpcionA, EstadoOpcion]:
    """Estado de cada opción. Permisos desconocidos (``None``) = ``SI`` (INV-O10); la versión
    se evalúa antes que el privilegio."""
    estados: dict[OpcionA, EstadoOpcion] = {}
    for opcion in OpcionA:
        if opcion == OpcionA.POOL:
            estados[opcion] = _estado_pools(pools)
            continue
        funcion = _FUNCION_DE.get(opcion)
        if funcion is not None and not caps.tiene(funcion):
            minima = caps.requisito(funcion)
            estados[opcion] = EstadoOpcion(
                opcion,
                Disponibilidad.NO,
                CodigoError.OPCION_SIN_VERSION,
                {"opcion": opcion.value, "version": f"{minima[0]}.{minima[1]}"},
            )
            continue
        privilegio = PRIVILEGIO_DE[opcion]
        if estado_privilegio(permisos, privilegio, RUTA_VMS) is False:
            estados[opcion] = EstadoOpcion(
                opcion,
                Disponibilidad.NO,
                CodigoError.OPCION_SIN_PRIVILEGIO,
                {"opcion": opcion.value, "privilegio": privilegio, "ruta": RUTA_VMS},
            )
        else:
            estados[opcion] = EstadoOpcion(opcion, Disponibilidad.SI)
    return estados
