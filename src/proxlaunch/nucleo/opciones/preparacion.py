"""Preparación de un elemento del plan: aplica las opciones de lote y calcula la descripción
final. Puro; lo usan ``construir_plan`` y ``_plan_de_uno``."""

from __future__ import annotations

from dataclasses import replace

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
    """Copia de ``cfg`` con ``descripcion`` calculada.

    En un clon la descripción de la plantilla sale de ``detalle_plantilla``; si no se conoce o no
    se pudo leer se trata como ilegible (no se pisan las notas de la plantilla, P-10).
    """
    previa: str | None = None
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        if detalle_plantilla is None or not detalle_plantilla.descripcion_legible:
            previa = LEIDA_NO
        else:
            previa = detalle_plantilla.descripcion
    return replace(cfg, descripcion=componer_descripcion(cfg, ctx, previa, version))


def aplicar_opciones_lote(
    cfg: ConfiguracionVM, base: OpcionesLote, fila: OpcionesParciales | None
) -> ConfiguracionVM:
    """Copia de ``cfg`` con las opciones del lote y, encima, las de la fila (``None`` = hereda).

    ``pool`` de la fila: ``""`` = sin pool explícito (anula el del lote).
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
    )
