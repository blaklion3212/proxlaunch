"""Disponibilidad de las opciones de la fase D según permisos y versión (RF-D5.1, RF-D0.3). Puro.

Mismo patrón que ``disponibilidad_c``: permisos desconocidos (``None``) = ``CON_AVISO``. La
interfaz solo pinta el resultado.

``params`` de cada estado: ``opcion`` y, según el caso, ``privilegio``, ``ruta``, ``version`` y
``motivo`` (``permisos_desconocidos``). Sin privilegio en ninguna ruta de mapeo, ``NO`` con
``OPCION_SIN_PRIVILEGIO`` (V-D63).
"""

from __future__ import annotations

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, OpcionD
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.origen.permisos import (
    PRIVILEGIO_MAPEO_USAR,
    RUTA_MAPEO_CPU,
    RUTA_MAPEO_PCI,
    estado_algun_mapeo,
    estado_cpu_personalizada,
    estado_privilegio,
)


def _desconocido(opcion: OpcionD) -> EstadoOpcion:
    return EstadoOpcion(
        opcion,
        Disponibilidad.CON_AVISO,
        None,
        {"opcion": opcion.value, "motivo": "permisos_desconocidos"},
    )


def _sin_privilegio(opcion: OpcionD, privilegio: str, ruta: str) -> EstadoOpcion:
    return EstadoOpcion(
        opcion,
        Disponibilidad.NO,
        CodigoError.OPCION_SIN_PRIVILEGIO,  # V-D63
        {"opcion": opcion.value, "privilegio": privilegio, "ruta": ruta},
    )


def disponibilidad_fase_d(
    caps: Capacidades | None,
    permisos: PermisosEfectivos | None,
    inv: Inventario | None,
) -> dict[OpcionD, EstadoOpcion]:
    """Estado de cada opción de la fase D.

    - ``MAPEOS``: ``Mapping.Use`` en alguna ruta de mapeo PCI o USB (sin privilegio en ninguna
      → ``NO`` con V-D63). La disponibilidad por mapeo concreto la da ``estado_mapeo``.
    - ``CPU_PERSONALIZADA``: ``estado_cpu_personalizada`` genérico (9.2: ``Mapping.Use`` en
      ``/mapping/cpu``; antes, ``VM.Config.CPU`` y ``Sys.Audit``). Sin ``caps`` se toma la
      regla de 8.4–9.1.
    - ``CONSERVAR_MAC``: siempre ``SI`` (validación local, sin permisos ni versión).

    ``inv`` se acepta para que la interfaz use una sola firma con las demás fases; hoy no hace
    falta leerlo.
    """
    estados: dict[OpcionD, EstadoOpcion] = {}
    for opcion in OpcionD:
        if opcion == OpcionD.MAPEOS:
            uso = estado_algun_mapeo(permisos)
            if uso is None:
                estados[opcion] = _desconocido(opcion)
            elif uso:
                estados[opcion] = EstadoOpcion(opcion, Disponibilidad.SI)
            else:
                estados[opcion] = _sin_privilegio(opcion, PRIVILEGIO_MAPEO_USAR, RUTA_MAPEO_PCI)
        elif opcion == OpcionD.CPU_PERSONALIZADA:
            efectivas = caps if caps is not None else Capacidades(version=(8, 4), forzada=False)
            uso = estado_cpu_personalizada(permisos, efectivas)
            if uso is None:
                estados[opcion] = _desconocido(opcion)
            elif uso:
                estados[opcion] = EstadoOpcion(opcion, Disponibilidad.SI)
            elif efectivas.tiene(Funcion.CPU_PERSONALIZADA_POR_MAPPING):
                estados[opcion] = _sin_privilegio(opcion, PRIVILEGIO_MAPEO_USAR, RUTA_MAPEO_CPU)
            else:
                falta = (
                    "Sys.Audit"
                    if not estado_privilegio(permisos, "Sys.Audit", "/nodes")
                    else "VM.Config.CPU"
                )
                ruta = "/nodes" if falta == "Sys.Audit" else "/vms"
                estados[opcion] = _sin_privilegio(opcion, falta, ruta)
        else:  # CONSERVAR_MAC
            estados[opcion] = EstadoOpcion(opcion, Disponibilidad.SI)
    return estados
