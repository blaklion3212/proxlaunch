"""Preparación de un elemento del plan: aplica las opciones de lote y calcula la descripción
final. Puro; lo usan ``construir_plan`` y ``_plan_de_uno``."""

from __future__ import annotations

from dataclasses import replace

from proxlaunch.nucleo.cloudinit.modelos import INFO_DESCONOCIDA, combinar
from proxlaunch.nucleo.firewall.modelos import FirewallMV, FirewallParcial
from proxlaunch.nucleo.modelos.catalogo import DetallePlantilla
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.opciones.modelos import ContextoNotas, OpcionesLote, OpcionesParciales
from proxlaunch.nucleo.opciones.notas import LEIDA_NO, componer_descripcion


def preparar_elemento(
    cfg: ConfiguracionVM,
    ctx: ContextoNotas,
    detalle_plantilla: DetallePlantilla | None,
    version: tuple[int, int] | None,
) -> ConfiguracionVM:
    """Copia de ``cfg`` con ``descripcion`` e ``info_cloudinit`` calculadas.

    En un clon la descripción de la plantilla sale de ``detalle_plantilla``; si no se conoce o no
    se pudo leer se trata como ilegible (no se pisan las notas de la plantilla, P-10). Lo mismo
    para cloud-init: sin detalle, ``INFO_DESCONOCIDA`` (V-B20 avisa «no se pudo comprobar»).
    En otros orígenes ``info_cloudinit`` no se toca.
    """
    previa: str | None = None
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        if detalle_plantilla is None or not detalle_plantilla.descripcion_legible:
            previa = LEIDA_NO
        else:
            previa = detalle_plantilla.descripcion
    descripcion = componer_descripcion(cfg, ctx, previa, version)
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        info = None if detalle_plantilla is None else detalle_plantilla.cloudinit
        return replace(
            cfg,
            descripcion=descripcion,
            info_cloudinit=INFO_DESCONOCIDA if info is None else info,
        )
    return replace(cfg, descripcion=descripcion)


def combinar_firewall(base: FirewallMV | None, fila: FirewallParcial | None) -> FirewallMV | None:
    """Firewall efectivo de una fila: cada celda fijada gana sobre el firewall del lote y una
    celda vacía (``None``) lo hereda (RF-C0.5).

    Sin celdas fijadas devuelve ``base`` tal cual. Si el lote no tiene firewall, parte del
    defecto (apagado): una fila con solo ``grupo`` queda con grupo y firewall apagado, que es el
    error V-C52 que debe ver «Comprobar» (CA-C6.3.9) en vez de ignorarse en silencio.
    """
    if fila is None or fila == FirewallParcial():
        return base
    previo = base if base is not None else FirewallMV()
    if fila.activo is False:
        # «cortafuegos=no» apaga el de la fila: el grupo y las políticas del formulario no se
        # heredan (solo cuenta lo que la propia fila fije; si fija grupo, V-C52 sigue avisando).
        defecto = FirewallMV()
        return replace(
            previo,
            activo=False,
            grupo=fila.grupo,
            politica_entrada=(
                defecto.politica_entrada if fila.politica_entrada is None else fila.politica_entrada
            ),
            politica_salida=(
                defecto.politica_salida if fila.politica_salida is None else fila.politica_salida
            ),
        )
    return replace(
        previo,
        activo=previo.activo if fila.activo is None else fila.activo,
        grupo=previo.grupo if fila.grupo is None else fila.grupo,
        politica_entrada=(
            previo.politica_entrada if fila.politica_entrada is None else fila.politica_entrada
        ),
        politica_salida=(
            previo.politica_salida if fila.politica_salida is None else fila.politica_salida
        ),
    )


def aplicar_opciones_lote(
    cfg: ConfiguracionVM, base: OpcionesLote, fila: OpcionesParciales | None
) -> ConfiguracionVM:
    """Copia de ``cfg`` con las opciones del lote y, encima, las de la fila (``None`` = hereda).

    ``pool`` de la fila: ``""`` = sin pool explícito (anula el del lote). Fase B: ``cloudinit``
    se combina con ``combinar`` (celda vacía hereda) y ``esperar_ip`` de la fila gana sobre el lote.
    Fase C: ``firewall`` se combina con ``combinar_firewall`` y la ``red_clon`` de la fila, si la
    fija, sustituye a la del lote.
    """
    f = fila or OpcionesParciales()
    pool = base.pool if f.pool is None else (f.pool or None)
    return replace(
        cfg,
        encender=base.encender if f.encender is None else f.encender,
        arranque_auto=base.arranque_auto if f.arranque_auto is None else f.arranque_auto,
        notas=base.notas if f.notas is None else f.notas,
        etiquetas_usuario=(
            base.etiquetas_usuario if f.etiquetas_usuario is None else f.etiquetas_usuario
        ),
        pool=pool,
        proteger=base.proteger if f.proteger is None else f.proteger,
        notas_origen=base.notas_origen,
        notas_usuario=base.notas_usuario,
        cloudinit=combinar(base.cloudinit, f.cloudinit),
        esperar_ip=base.esperar_ip if f.esperar_ip is None else f.esperar_ip,
        plazo_ip_s=base.plazo_ip_s,
        firewall=combinar_firewall(base.firewall, f.firewall),
        red_clon=f.red_clon if f.red_clon is not None else base.red_clon,
    )
