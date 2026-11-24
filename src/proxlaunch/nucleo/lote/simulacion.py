"""Simulación de solo lectura (RF-L11, INV-L5, INV-O12).

Ejecuta el MISMO ``Planificador`` que la creación real, pero sobre un cliente cuyo
transporte rechaza todo método distinto de GET/HEAD, y construye las peticiones exactas
que se enviarían sin enviarlas. Con los orígenes del MVP 4 una MV puede enviar varias
peticiones (``POST``/``clone`` + ``PUT config`` + ``PUT resize``): todas salen en
``peticiones_detalle`` construidas con las mismas funciones puras que la ejecución.
"""

import contextlib
from dataclasses import replace

from proxlaunch.nucleo.cloudinit.modelos import INFO_DESCONOCIDA
from proxlaunch.nucleo.cloudinit.peticion import (
    PARAMETROS_CONTRASENA_SIMULADOS,
    construir_put_cloudinit,
    parametros_simulados,
)
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import FirewallPlantilla, usa_firewall
from proxlaunch.nucleo.firewall.reglas import parametros_opciones, parametros_regla
from proxlaunch.nucleo.lote.informe import AnunciosFaseD, anuncios_fase_d
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
from proxlaunch.nucleo.red.modelos import MAC_SIMULADA
from proxlaunch.nucleo.red.reescritura import construir_peticion_red, requiere_paso_red
from proxlaunch.nucleo.reloj import Reloj, RelojCalendario
from proxlaunch.nucleo.servicios.catalogo import con_catalogo
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.servicios.creacion import (
    ajustes_de_clon,
    ampliacion_importacion,
    avisos_firewall_planeados,
    avisos_red_planeados,
    disco_seguro,
    firewall_de_plantilla,
    hardware_de_clon,
    ipconfigs_de_plantilla,
)


def _peticiones_de_clon(
    e: ElementoPlan, inv: Inventario
) -> tuple[dict[str, str], tuple[PeticionSimulada, ...]]:
    """Clon + ``PUT config`` + [``PUT`` de hardware del clúster] + [leer config + ``PUT`` de red] +
    cloud-init + contraseña + [firewall] + ``PUT resize`` de un elemento (lanza
    ``ErrorProxLaunch``). El orden es el de
    ``ServicioCreacion`` (DT-B7, DT-C7). La contraseña va siempre enmascarada y las claves SSH
    como ``[n]``: nunca se simula un secreto."""
    peticion = construir_peticion_clon(e.cfg, inv)
    detalle = [
        PeticionSimulada(AccionPeticion.CLONAR, peticion.nodo_plantilla, peticion.parametros)
    ]
    plantilla = _detalle_plantilla(inv, peticion.vmid_plantilla)
    if plantilla is not None:
        ajustes, _ = ajustes_de_clon(e.cfg, inv, plantilla)
        if ajustes.config:
            detalle.append(PeticionSimulada(AccionPeticion.CONFIGURAR, e.nodo, ajustes.config))
        detalle.extend(_peticiones_de_hardware(e, plantilla))
        detalle.extend(_peticiones_de_red(e, plantilla))
        ci = e.cfg.cloudinit
        if ci is not None and ajustes.cloudinit:
            detalle.append(
                PeticionSimulada(
                    AccionPeticion.CLOUDINIT, e.nodo, parametros_simulados(ajustes.cloudinit, ci)
                )
            )
        if ajustes.contrasena is not None and ajustes.contrasena.definido:
            detalle.append(
                PeticionSimulada(
                    AccionPeticion.CONTRASENA, e.nodo, dict(PARAMETROS_CONTRASENA_SIMULADOS)
                )
            )
        detalle.extend(_peticiones_de_firewall(e, firewall_de_plantilla(e.cfg, inv)))
        if ajustes.disco is not None:
            clave, gib = ajustes.disco
            detalle.append(
                PeticionSimulada(AccionPeticion.AMPLIAR, e.nodo, parametros_ampliacion(clave, gib))
            )
    else:
        # Sin la config de la plantilla se simula con lo que se sabe (cloud-init sin heredados y
        # sin tarjetas de la plantilla).
        detalle.extend(_peticiones_de_red(e, None))
        ci = e.cfg.cloudinit
        if ci is not None and not ci.vacia:
            put = construir_put_cloudinit(ci, INFO_DESCONOCIDA)
            if put:
                detalle.append(
                    PeticionSimulada(
                        AccionPeticion.CLOUDINIT, e.nodo, parametros_simulados(put, ci)
                    )
                )
            if ci.contrasena is not None and ci.contrasena.definido:
                detalle.append(
                    PeticionSimulada(
                        AccionPeticion.CONTRASENA, e.nodo, dict(PARAMETROS_CONTRASENA_SIMULADOS)
                    )
                )
        detalle.extend(_peticiones_de_firewall(e, firewall_de_plantilla(e.cfg, inv)))
    return peticion.parametros, tuple(detalle)


def _peticiones_de_hardware(e: ElementoPlan, plantilla: DetallePlantilla) -> list[PeticionSimulada]:
    """``PUT config`` de hardware del clúster de un clon (DT-D11), sobre los índices libres de la
    plantilla. Sin hardware no hay petición. Si no caben los índices, la ejecución dejará el
    paso pendiente (``ajuste_pendiente:hardware``): la simulación no lo inventa."""
    try:
        cuerpo = hardware_de_clon(e.cfg, plantilla)
    except ErrorProxLaunch:
        return []
    if not cuerpo:
        return []
    return [PeticionSimulada(AccionPeticion.CONFIGURAR, e.nodo, cuerpo)]


def _peticiones_de_red(
    e: ElementoPlan, plantilla: DetallePlantilla | None
) -> list[PeticionSimulada]:
    """``GET`` de la config del clon y ``PUT`` de red (C4/C3) sobre las tarjetas de la plantilla.

    La MAC real la genera Proxmox al clonar: se simula con ``MAC_SIMULADA`` (DT-C6) y sin
    ``digest``. Sin nada que cambiar, la lectura se muestra igual pero no hay ``PUT``.
    """
    if not requiere_paso_red(e.cfg):
        return []
    pasos = [PeticionSimulada(AccionPeticion.LEER_CONFIG, e.nodo, {})]
    tarjetas = tuple(
        replace(t, mac=MAC_SIMULADA) if t.legible else t
        for t in (plantilla.tarjetas if plantilla is not None else ())
    )
    try:
        red = construir_peticion_red(e.cfg, tarjetas, ipconfigs_de_plantilla(plantilla), None)
    except ErrorProxLaunch:
        red = None  # índice ocupado: la ejecución lo marcará PARCIAL (RED_PLANTILLA_CAMBIADA)
    if red is not None:
        pasos.append(PeticionSimulada(AccionPeticion.RED, e.nodo, dict(red.parametros)))
    return pasos


def _peticiones_de_firewall(
    e: ElementoPlan, plantilla_fw: FirewallPlantilla | None
) -> list[PeticionSimulada]:
    """``PUT …/firewall/options`` y ``POST …/firewall/rules`` de la MV (C3).

    La regla no se simula si la plantilla ya traía la de ese grupo (CA-C3.6.2, no se enviará).
    """
    fw = e.cfg.firewall
    if fw is None or not usa_firewall(fw):
        return []
    pasos = [
        PeticionSimulada(AccionPeticion.FIREWALL_OPCIONES, e.nodo, parametros_opciones(fw, e.cfg))
    ]
    ya_estaba = (
        plantilla_fw is not None
        and plantilla_fw.legible
        and fw.grupo is not None
        and fw.grupo in plantilla_fw.grupos
    )
    if fw.grupo and not ya_estaba:
        # Un nombre de grupo no válido no se simula: V-C31 ya lo señala en el plan.
        with contextlib.suppress(ValueError):
            cuerpo = parametros_regla(fw.grupo)
            pasos.append(PeticionSimulada(AccionPeticion.FIREWALL_REGLA, e.nodo, cuerpo))
    return pasos


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
    detalle.extend(_peticiones_de_firewall(e, None))
    ampliacion = ampliacion_importacion(e.cfg, inv)
    # Sin certeza de permisos el resize no se envía (INV-O10), tampoco en la simulación.
    if ampliacion is not None and disco_seguro(e.cfg, inv):
        clave, gib = ampliacion
        detalle.append(
            PeticionSimulada(AccionPeticion.AMPLIAR, e.nodo, parametros_ampliacion(clave, gib))
        )
    return parametros, tuple(detalle)


def anuncios_de_simulacion(resultado: ResultadoSimulacion) -> AnunciosFaseD:
    """Lo que la fase D anuncia en la simulación: adaptación ARM (V-D08), nodos ARM64
    (etiqueta «experimental»), hardware del clúster, MAC conservada e imágenes adicionales.
    Vacío con un lote x86 sin opciones de D (la simulación no gana nada)."""
    return anuncios_fase_d(resultado.plan.problemas, resultado.plan.elementos)


def avisos_de_simulacion(
    resultado: ResultadoSimulacion, inv: Inventario, vmid: int
) -> tuple[str, ...]:
    """Avisos de la fase C que dará la MV ``vmid`` y que la simulación no puede mostrar como
    petición: ``red_tarjeta_ilegible:netN`` (tarjeta de la plantilla que no se entiende y quedará
    sin tocar, p. ej. sin ``firewall=1``), ``red_mtu_ignorada:netN``, ``red_mac_nueva:netN``,
    ``firewall_heredado`` y ``firewall_grupo_ya_estaba:<g>`` (arquitectura §9). Vacío sin C."""
    elemento = next((e for e in resultado.plan.elementos if e.vmid == vmid), None)
    if elemento is None or elemento.cfg.origen != OrigenSO.CLONAR_PLANTILLA:
        return ()
    plan = resultado.plan
    inv_plan = con_catalogo(inv, plan.catalogo) if plan.catalogo is not None else inv
    try:
        peticion = construir_peticion_clon(elemento.cfg, inv_plan)
    except ErrorProxLaunch:
        return ()
    plantilla = _detalle_plantilla(inv_plan, peticion.vmid_plantilla)
    avisos = (
        *avisos_red_planeados(
            elemento.cfg,
            plantilla.tarjetas if plantilla is not None else (),
            ipconfigs_de_plantilla(plantilla),
        ),
        *avisos_firewall_planeados(elemento.cfg, inv_plan),
    )
    return tuple(dict.fromkeys(avisos))


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
            if e.cfg.esperar_ip:  # fase B: sondeo de la IP con el agente, tras encender
                detalle[e.vmid] = (
                    *detalle[e.vmid],
                    PeticionSimulada(
                        AccionPeticion.SONDEAR_IP, e.nodo, {"plazo_s": str(e.cfg.plazo_ip_s)}
                    ),
                )
    return ResultadoSimulacion(
        plan=plan,
        peticiones=peticiones,
        version_detectada=(inv.version.mayor, inv.version.menor),
        version_forzada=version_forzada,
        peticiones_detalle=detalle,
    )
