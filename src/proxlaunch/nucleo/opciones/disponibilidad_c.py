"""Disponibilidad de las opciones de la fase C según permisos y versión (RF-C5.2). Puro.

Mismo patrón que ``opciones.disponibilidad`` y ``cloudinit.disponibilidad``: la versión se mira
antes que el privilegio; permisos desconocidos (``None``) = ``CON_AVISO``. La interfaz solo pinta
el resultado.

``params`` de cada estado: ``opcion`` y, según el caso, ``privilegio``, ``ruta``, ``version`` y
``motivo`` (``permisos_desconocidos``).
"""

from __future__ import annotations

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.cloudinit.disponibilidad import estado_permisos_agente
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, OpcionC
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.origen.permisos import (
    RUTA_ZONA_GENERICA,
    estado_privilegio,
    estado_sdn_fuera_de_local,
)

RUTA_VMS = "/vms"
RUTA_RAIZ = "/"
PRIVILEGIO_AUDITAR_VMS = "VM.Audit"
PRIVILEGIO_RED = "VM.Config.Network"
PRIVILEGIO_AUDITAR_SISTEMA = "Sys.Audit"
PRIVILEGIO_SDN = "SDN.Use"

# opción -> función con versión mínima (V-C50). ``IP_INVENTARIO`` y ``FIREWALL_GENERAL`` no
# dependen de una función propia de la fase C.
_FUNCION_DE: dict[OpcionC, Funcion] = {
    OpcionC.INVENTARIO: Funcion.INVENTARIO_LOTES,
    OpcionC.VNETS: Funcion.VNETS_SDN,
    OpcionC.FIREWALL: Funcion.FIREWALL_GRUPO,
    OpcionC.RED_CLON: Funcion.REESCRIBIR_RED_CLON,
}


def _si(opcion: OpcionC) -> EstadoOpcion:
    return EstadoOpcion(opcion, Disponibilidad.SI)


def _desconocido(opcion: OpcionC) -> EstadoOpcion:
    return EstadoOpcion(
        opcion,
        Disponibilidad.CON_AVISO,
        None,
        {"opcion": opcion.value, "motivo": "permisos_desconocidos"},
    )


def _sin_privilegio(opcion: OpcionC, privilegio: str, ruta: str) -> EstadoOpcion:
    return EstadoOpcion(
        opcion,
        Disponibilidad.NO,
        CodigoError.OPCION_SIN_PRIVILEGIO,  # V-C40
        {"opcion": opcion.value, "privilegio": privilegio, "ruta": ruta},
    )


def _con_privilegio(
    opcion: OpcionC, permisos: PermisosEfectivos | None, privilegio: str, ruta: str
) -> EstadoOpcion:
    estado = estado_privilegio(permisos, privilegio, ruta)
    if estado is None:
        return _desconocido(opcion)
    return _si(opcion) if estado else _sin_privilegio(opcion, privilegio, ruta)


def disponibilidad_fase_c(
    permisos: PermisosEfectivos | None, caps: Capacidades
) -> dict[OpcionC, EstadoOpcion]:
    """Estado de cada opción de la fase C.

    ``FIREWALL`` y ``RED_CLON``: ``VM.Config.Network`` en ``/vms``. ``FIREWALL_GENERAL``:
    ``Sys.Audit`` en ``/`` (si falta, ``CON_AVISO``, nunca ``NO``). ``IP_INVENTARIO``: el
    privilegio del agente según la versión (como la fase B). ``INVENTARIO``: ``VM.Audit``.
    ``VNETS``: ``SDN.Use`` fuera de ``localnetwork``. Una versión sin la función da ``NO`` con
    ``OPCION_SIN_VERSION`` (V-C50).
    """
    estados: dict[OpcionC, EstadoOpcion] = {}
    for opcion in OpcionC:
        funcion = _FUNCION_DE.get(opcion)
        if funcion is not None and not caps.tiene(funcion):
            minima = caps.requisito(funcion)
            estados[opcion] = EstadoOpcion(
                opcion,
                Disponibilidad.NO,
                CodigoError.OPCION_SIN_VERSION,  # V-C50
                {"opcion": opcion.value, "version": f"{minima[0]}.{minima[1]}"},
            )
            continue
        if opcion == OpcionC.INVENTARIO:
            estados[opcion] = _con_privilegio(opcion, permisos, PRIVILEGIO_AUDITAR_VMS, RUTA_VMS)
        elif opcion == OpcionC.VNETS:
            fuera = estado_sdn_fuera_de_local(permisos)
            if fuera is None:
                estados[opcion] = _desconocido(opcion)
            else:
                estados[opcion] = (
                    _si(opcion)
                    if fuera
                    else _sin_privilegio(opcion, PRIVILEGIO_SDN, RUTA_ZONA_GENERICA)
                )
        elif opcion in (OpcionC.FIREWALL, OpcionC.RED_CLON):
            estados[opcion] = _con_privilegio(opcion, permisos, PRIVILEGIO_RED, RUTA_VMS)
        elif opcion == OpcionC.FIREWALL_GENERAL:
            base = _con_privilegio(opcion, permisos, PRIVILEGIO_AUDITAR_SISTEMA, RUTA_RAIZ)
            if base.disponibilidad == Disponibilidad.NO:  # sin Sys.Audit: solo se pierde un aviso
                base = EstadoOpcion(opcion, Disponibilidad.CON_AVISO, base.codigo, base.params)
            estados[opcion] = base
        else:  # IP_INVENTARIO
            agente = estado_permisos_agente(permisos, caps)
            params = dict(agente.params)
            params["opcion"] = opcion.value
            estados[opcion] = EstadoOpcion(opcion, agente.disponibilidad, agente.codigo, params)
    return estados
