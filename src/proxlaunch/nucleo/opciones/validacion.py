"""Reglas V-A01..V-A15 de las opciones de la fase A. Puro.

``validar_opciones`` lo llama ``nucleo.validacion.validar_vm`` al final, de modo que una MV
individual y un lote validan igual. Lo que necesita datos del servidor (pools, política de
etiquetas, descripción de la plantilla, permisos) sale del catálogo ``inv.catalogo``; sin catálogo
esas reglas no se evalúan.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.modelos.catalogo import DetallePlantilla
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import (
    MAX_LIMITE_MB,
    MTU_IGUAL_BRIDGE,
    MTU_MAX,
    MTU_MIN,
    ConfiguracionVM,
    DetalleClon,
    ModeloRed,
    OrigenSO,
    pool_valido,
)
from proxlaunch.nucleo.opciones.disponibilidad import (
    PRIVILEGIO_DE,
    RUTA_VMS,
    disponibilidad_opciones,
)
from proxlaunch.nucleo.opciones.etiquetas import etiquetas_finales, rechazadas_por_politica
from proxlaunch.nucleo.opciones.modelos import ContextoNotas, EstadoPools, OpcionA, PoolsServidor
from proxlaunch.nucleo.opciones.notas import (
    AVISO_DESCRIPCION,
    LEIDA_NO,
    LIMITE_DESCRIPCION,
    componer_descripcion,
    limpiar_texto_libre,
)
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.validacion import _RE_ETIQUETA_PVE, Problema, Severidad

ENTERO_MAX = 2**31 - 1  # tope de ``order`` y ``up`` de ``startup``
MAX_LONG_ETIQUETA = 128

# Contexto de notas de estimación (cuando la descripción aún no está calculada): lote de 8 hex
# y sin perfil ni usuario; el valor exacto lo calcula ``preparar_elemento`` al planificar.
_CTX_ESTIMADO = ContextoNotas(
    version_app="0.0.0",
    fecha=datetime(2000, 1, 1, tzinfo=UTC),
    id_lote="00000000",
    perfil=None,
    usuario=None,
)


def _es_entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _es_numero(valor: object) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _detalle_de_plantilla(cfg: ConfiguracionVM, inv: Inventario) -> DetallePlantilla | None:
    """Detalle de la plantilla del clon según el catálogo; ``None`` si no se conoce."""
    detalle = cfg.detalle_origen
    if inv.catalogo is None or not isinstance(detalle, DetalleClon):
        return None
    ref = detalle.plantilla
    for p in inv.catalogo.plantillas or ():
        if (ref.vmid is not None and p.vmid == ref.vmid) or (
            ref.vmid is None and p.nombre == ref.nombre
        ):
            return p.detalle
    return None


def _descripcion_estimada(cfg: ConfiguracionVM, inv: Inventario) -> str | None:
    """Descripción ya calculada o, si no, una estimación con la plantilla del catálogo."""
    if cfg.descripcion is not None:
        return cfg.descripcion
    previa: str | None = None
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        detalle = _detalle_de_plantilla(cfg, inv)
        if detalle is not None:
            previa = detalle.descripcion if detalle.descripcion_legible else LEIDA_NO
    return componer_descripcion(cfg, _CTX_ESTIMADO, previa, None)


def _opciones_fijadas(cfg: ConfiguracionVM) -> set[OpcionA]:
    """Opciones que el usuario fijó (distintas del valor por defecto de 0.5.1)."""
    fijadas: set[OpcionA] = set()
    if cfg.encender:
        fijadas.add(OpcionA.ENCENDER)
    if cfg.arranque_auto:
        fijadas.add(OpcionA.ARRANQUE_AUTO)
    if cfg.arranque_orden is not None or cfg.arranque_espera is not None:
        fijadas.add(OpcionA.ARRANQUE_ORDEN)
    if cfg.notas_origen or cfg.notas.strip():
        fijadas.add(OpcionA.NOTAS)
    if cfg.etiquetas_usuario:
        fijadas.add(OpcionA.ETIQUETAS)
    if cfg.pool is not None:
        fijadas.add(OpcionA.POOL)
    if any(r.mtu is not None for r in cfg.redes):
        fijadas.add(OpcionA.MTU)
    if any(r.limite_mb is not None for r in cfg.redes):
        fijadas.add(OpcionA.LIMITE_RED)
    if cfg.proteger:
        fijadas.add(OpcionA.PROTEGER)
    return fijadas


def validar_opciones(cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades) -> list[Problema]:
    """Reglas V-A01..V-A15 (arquitectura de la fase A, §4). Devuelve todos los problemas."""
    p: list[Problema] = []
    es_clon = cfg.origen == OrigenSO.CLONAR_PLANTILLA
    catalogo = inv.catalogo

    def error(campo: str, codigo: str, **params: str) -> None:
        p.append(Problema(campo, codigo, Severidad.ERROR, dict(params)))

    def aviso(campo: str, codigo: str, **params: str) -> None:
        p.append(Problema(campo, codigo, Severidad.AVISO, dict(params)))

    # V-A01 orden y espera de arranque
    for campo, valor in (
        ("arranque_orden", cfg.arranque_orden),
        ("arranque_espera", cfg.arranque_espera),
    ):
        if valor is not None and (not _es_entero(valor) or not 0 <= valor <= ENTERO_MAX):
            error(campo, "V-A01", valor=str(valor))

    # V-A02 etiquetas del usuario
    for i, etiqueta in enumerate(cfg.etiquetas_usuario):
        if (
            not isinstance(etiqueta, str)
            or len(etiqueta) > MAX_LONG_ETIQUETA
            or not _RE_ETIQUETA_PVE.fullmatch(etiqueta)
        ):
            error(f"etiquetas_usuario[{i}]", "V-A02", etiqueta=str(etiqueta))

    # V-A03 / V-A09 política de etiquetas del centro de datos
    if catalogo is not None:
        if catalogo.politica_etiquetas is None:
            # Se avisa si la lectura falló y se va a enviar alguna etiqueta (también solo las fijas,
            # RF-A3.5); una política aún no leída (catálogos armados a mano) no avisa.
            if catalogo.politica_etiquetas_fallida and etiquetas_finales(cfg):
                aviso("etiquetas", "V-A09")
        else:
            finales = etiquetas_finales(cfg)
            if es_clon:
                # S-1: un clon hereda las etiquetas de su plantilla; solo se evalúan las añadidas.
                plantilla = _detalle_de_plantilla(cfg, inv)
                if plantilla is not None:
                    finales = tuple(e for e in finales if e not in plantilla.etiquetas)
            sys_modify = estado_privilegio(catalogo.permisos, "Sys.Modify", "/")
            sin_audit = estado_privilegio(catalogo.permisos, "Sys.Audit", "/") is False
            if sin_audit and sys_modify is not True and catalogo.politica_etiquetas.acceso_ausente:
                # LAB-C-1: sin Sys.Audit en «/», /cluster/options llega parcial (sin
                # user-tag-access) y no se sabe la política: aviso confirmable por etiqueta.
                # Si la clave sí vino, la política es real y se evalúa como en 0.8.0.
                for etiqueta in finales:
                    campo = (
                        f"etiquetas_usuario[{cfg.etiquetas_usuario.index(etiqueta)}]"
                        if etiqueta in cfg.etiquetas_usuario
                        else "etiquetas"
                    )
                    aviso(campo, "V-A03", etiqueta=etiqueta, motivo="sin_sys_audit")
                finales = ()
            for etiqueta, motivo in rechazadas_por_politica(
                finales, catalogo.politica_etiquetas, sys_modify
            ):
                campo = (
                    f"etiquetas_usuario[{cfg.etiquetas_usuario.index(etiqueta)}]"
                    if etiqueta in cfg.etiquetas_usuario
                    else "etiquetas"
                )
                if sys_modify is None:
                    # QA-A-10: sin saber si el usuario tiene Sys.Modify el rechazo no es seguro
                    # (mismo código V-A03, con severidad de aviso).
                    aviso(campo, "V-A03", etiqueta=etiqueta, motivo=motivo, incierto="1")
                else:
                    error(campo, "V-A03", etiqueta=etiqueta, motivo=motivo)

    # V-A04 / V-A05 / V-A06 MTU y límite por tarjeta (un clon hereda sus redes: V-O29)
    if not es_clon:
        for i, red in enumerate(cfg.redes):
            ruta = f"redes[{i}]"
            if red.mtu is not None:
                if not _es_entero(red.mtu) or not (
                    red.mtu == MTU_IGUAL_BRIDGE or MTU_MIN <= red.mtu <= MTU_MAX
                ):
                    error(f"{ruta}.mtu", "V-A04", valor=str(red.mtu), tarjeta=str(i + 1))
                if red.modelo != ModeloRed.VIRTIO:
                    error(f"{ruta}.mtu", "V-A05", modelo=str(red.modelo), tarjeta=str(i + 1))
            if red.limite_mb is not None and (
                not _es_numero(red.limite_mb)
                or not math.isfinite(red.limite_mb)
                or not 0 < red.limite_mb <= MAX_LIMITE_MB
            ):
                error(f"{ruta}.limite_mb", "V-A06", valor=str(red.limite_mb), tarjeta=str(i + 1))

    # V-A16 formato del pool (capa 1; admite pools anidados «a/b/c»). «» = sin pool.
    pool_invalido = bool(cfg.pool) and not pool_valido(cfg.pool)
    if pool_invalido:
        error("pool", "V-A16", pool=str(cfg.pool))

    # V-A14 caracteres de control en el texto libre
    if limpiar_texto_libre(cfg.notas)[1]:
        aviso("notas", "V-A14")

    # V-A07 / V-A08 longitud total de la descripción
    descripcion = _descripcion_estimada(cfg, inv)
    if descripcion is not None:
        total = len(descripcion)
        if total > LIMITE_DESCRIPCION:
            error(
                "notas",
                "V-A07",
                total=str(total),
                limite=str(LIMITE_DESCRIPCION),
                sobran=str(total - LIMITE_DESCRIPCION),
            )
        elif total >= AVISO_DESCRIPCION:
            aviso("notas", "V-A08", total=str(total), limite=str(LIMITE_DESCRIPCION))

    if catalogo is None:
        return p

    # V-A13 clon con notas y descripción de la plantilla ilegible (no se envía ``description``)
    if es_clon and (cfg.notas_origen or cfg.notas.strip()):
        detalle = _detalle_de_plantilla(cfg, inv)
        if detalle is not None and not detalle.descripcion_legible:
            aviso("notas", "V-A13")

    # V-A10 / V-A11 / V-A15 pool fijado
    if cfg.pool is not None and not pool_invalido:
        pools: PoolsServidor = catalogo.pools
        if pools.estado == EstadoPools.OK:
            if cfg.pool not in pools.ids:
                # Con Pool.Audit parcial (o desconocido) la lista puede estar incompleta: aviso.
                if estado_privilegio(catalogo.permisos, "Pool.Audit", "/pool") is True:
                    error("pool", "V-A10", pool=cfg.pool)
                else:
                    aviso("pool", "V-A11", pool=cfg.pool, estado=str(pools.estado))
        else:
            aviso("pool", "V-A11", pool=cfg.pool, estado=str(pools.estado))
        en_vms = estado_privilegio(catalogo.permisos, "VM.Allocate", RUTA_VMS)
        en_pool = estado_privilegio(catalogo.permisos, "VM.Allocate", f"/pool/{cfg.pool}")
        if en_vms is False and en_pool is False:
            error("pool", "V-A15", pool=cfg.pool, ruta=RUTA_VMS, ruta_pool=f"/pool/{cfg.pool}")

    # V-A12 opción fijada sin privilegio o sin versión (POOL se rige por V-A10/V-A11/V-A15).
    # Un clon envía ``description`` en el POST de clone (sin VM.Config.Options) y no admite red.
    estados = disponibilidad_opciones(catalogo.permisos, caps, catalogo.pools)
    omitidas = {OpcionA.POOL}
    if es_clon:
        omitidas |= {OpcionA.NOTAS, OpcionA.MTU, OpcionA.LIMITE_RED}
    for opcion in sorted(_opciones_fijadas(cfg) - omitidas):
        estado = estados[opcion]
        if estado.disponibilidad == Disponibilidad.NO:
            params = dict(estado.params)
            params.setdefault("privilegio", PRIVILEGIO_DE.get(opcion, ""))
            params["opcion"] = opcion.value
            if estado.codigo is not None:
                params["motivo"] = str(estado.codigo)
            p.append(Problema(opcion.value, "V-A12", Severidad.ERROR, params))
    return p
