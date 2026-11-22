"""Simulación de solo lectura (RF-L11, INV-L5, INV-O12).

Ejecuta el MISMO ``Planificador`` que la creación real, pero sobre un cliente cuyo
transporte rechaza todo método distinto de GET/HEAD, y construye las peticiones exactas
que se enviarían sin enviarlas. Con los orígenes del MVP 4 una MV puede enviar varias
peticiones (``POST``/``clone`` + ``PUT config`` + ``PUT resize``): todas salen en
``peticiones_detalle`` construidas con las mismas funciones puras que la ejecución.
"""

from dataclasses import replace

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    AccionPeticion,
    DefinicionLote,
    ElementoPlan,
    PeticionSimulada,
    ResultadoSimulacion,
)
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.modelos.catalogo import DetallePlantilla
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.opciones.modelos import ContextoNotas
from proxlaunch.nucleo.origen.clon import (
    construir_peticion_clon,
    parametros_ampliacion,
)
from proxlaunch.nucleo.reloj import Reloj, RelojCalendario
from proxlaunch.nucleo.servicios.catalogo import con_catalogo
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.servicios.creacion import (
    ajustes_de_clon,
    ampliacion_importacion,
    disco_seguro,
)


def _peticiones_de_clon(
    e: ElementoPlan, inv: Inventario
) -> tuple[dict[str, str], tuple[PeticionSimulada, ...]]:
    """Clon + ``PUT config`` + ``PUT resize`` de un elemento (lanza ``ErrorProxLaunch``)."""
    peticion = construir_peticion_clon(e.cfg, inv)
    detalle = [
        PeticionSimulada(AccionPeticion.CLONAR, peticion.nodo_plantilla, peticion.parametros)
    ]
    plantilla = _detalle_plantilla(inv, peticion.vmid_plantilla)
    if plantilla is not None:
        ajustes, _ = ajustes_de_clon(e.cfg, inv, plantilla)
        if ajustes.config:
            detalle.append(PeticionSimulada(AccionPeticion.CONFIGURAR, e.nodo, ajustes.config))
        if ajustes.disco is not None:
            clave, gib = ajustes.disco
            detalle.append(
                PeticionSimulada(AccionPeticion.AMPLIAR, e.nodo, parametros_ampliacion(clave, gib))
            )
    return peticion.parametros, tuple(detalle)


def _detalle_plantilla(inv: Inventario, vmid_plantilla: int) -> DetallePlantilla | None:
    """Detalle (config leída al planificar) de la plantilla del clon; ``None`` si no consta."""
    if inv.catalogo is None:
        return None
    for p in inv.catalogo.plantillas or ():
        if p.vmid == vmid_plantilla and p.detalle is not None:
            return p.detalle
    return None


def _peticiones_de_post(
    e: ElementoPlan, inv: Inventario, version: tuple[int, int]
) -> tuple[dict[str, str], tuple[PeticionSimulada, ...]]:
    """``POST /qemu`` (+ ``PUT resize`` si se amplía un disco importado) de un elemento."""
    parametros = construir_parametros(e.cfg, inv, version)
    detalle = [PeticionSimulada(AccionPeticion.CREAR, e.nodo, parametros)]
    ampliacion = ampliacion_importacion(e.cfg, inv)
    # Sin certeza de permisos el resize no se envía (INV-O10), tampoco en la simulación.
    if ampliacion is not None and disco_seguro(e.cfg, inv):
        clave, gib = ampliacion
        detalle.append(
            PeticionSimulada(AccionPeticion.AMPLIAR, e.nodo, parametros_ampliacion(clave, gib))
        )
    return parametros, tuple(detalle)


def simular(
    sesion: Sesion,
    definicion: DefinicionLote,
    inv: Inventario,
    *,
    version_forzada: tuple[int, int] | None = None,
    reloj: Reloj,
    contexto_notas: ContextoNotas | None = None,
    reloj_calendario: RelojCalendario | None = None,
) -> ResultadoSimulacion:
    """Planifica y construye las peticiones de cada MV sin escribir nada.

    Las lecturas (VMIDs, nombres existentes, permisos, catálogo) son las reales del servidor
    conectado (CA-L11.4). Un elemento cuya petición no pueda construirse se omite de
    ``peticiones`` (su problema ya consta en el plan). ``peticiones[vmid]`` es la petición
    de creación (``POST`` o ``clone``) y ``peticiones_detalle[vmid]`` todas las que se enviarían,
    con ``ENCENDER`` al final si la MV pide encenderse (fase A). ``contexto_notas`` y
    ``reloj_calendario`` se pasan al planificador: la descripción simulada es la que se enviará.
    """
    sesion_ro = replace(sesion, cliente=sesion.cliente.solo_lectura())
    # Solo se pasa si se aporta: así la firma de ``planificar`` que usa el resto no cambia.
    extra = {} if contexto_notas is None else {"contexto_notas": contexto_notas}
    plan = replace(
        Planificador(sesion_ro, reloj, reloj_calendario=reloj_calendario).planificar(
            definicion, inv, version_forzada=version_forzada, **extra
        ),
        es_simulacion=True,
    )
    inv_plan = con_catalogo(inv, plan.catalogo) if plan.catalogo is not None else inv
    peticiones: dict[int, dict[str, str]] = {}
    detalle: dict[int, tuple[PeticionSimulada, ...]] = {}
    for e in plan.elementos:
        try:
            if e.cfg.origen == OrigenSO.CLONAR_PLANTILLA:
                peticiones[e.vmid], detalle[e.vmid] = _peticiones_de_clon(e, inv_plan)
            else:
                peticiones[e.vmid], detalle[e.vmid] = _peticiones_de_post(
                    e, inv_plan, plan.version_validacion
                )
        except ErrorProxLaunch:
            continue
        if e.cfg.encender:
            # Sin parámetros: ``POST …/status/start`` (tras los ajustes, si quedan completos).
            detalle[e.vmid] = (
                *detalle[e.vmid],
                PeticionSimulada(AccionPeticion.ENCENDER, e.nodo, {}),
            )
    return ResultadoSimulacion(
        plan=plan,
        peticiones=peticiones,
        version_detectada=(inv.version.mayor, inv.version.menor),
        version_forzada=version_forzada,
        peticiones_detalle=detalle,
    )
