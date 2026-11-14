"""Simulación de solo lectura (RF-L11, INV-L5).

Ejecuta el MISMO ``Planificador`` que la creación real, pero sobre un cliente cuyo
transporte rechaza todo método distinto de GET/HEAD, y construye las peticiones exactas
que se enviarían sin enviarlas.
"""

from dataclasses import replace

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, ResultadoSimulacion
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion


def simular(
    sesion: Sesion,
    definicion: DefinicionLote,
    inv: Inventario,
    *,
    version_forzada: tuple[int, int] | None = None,
    reloj: Reloj,
) -> ResultadoSimulacion:
    """Planifica y construye las peticiones POST de cada MV sin escribir nada.

    Las lecturas (VMIDs, nombres existentes, permisos) son las reales del servidor
    conectado (CA-L11.4). Un elemento cuya petición no pueda construirse se omite de
    ``peticiones`` (su problema ya consta en el plan).
    """
    sesion_ro = replace(sesion, cliente=sesion.cliente.solo_lectura())
    plan = replace(
        Planificador(sesion_ro, reloj).planificar(definicion, inv, version_forzada=version_forzada),
        es_simulacion=True,
    )
    peticiones: dict[int, dict[str, str]] = {}
    for e in plan.elementos:
        try:
            peticiones[e.vmid] = construir_parametros(e.cfg, inv, plan.version_validacion)
        except ErrorProxLaunch:
            continue
    return ResultadoSimulacion(
        plan=plan,
        peticiones=peticiones,
        version_detectada=(inv.version.mayor, inv.version.menor),
        version_forzada=version_forzada,
    )
