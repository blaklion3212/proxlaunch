"""Informe estructurado del lote (RF-L19). Solo datos y códigos: sin textos de usuario.

La interfaz lo convierte en texto con una única función. Nunca incluye host, IP ni usuario
(CA-L19.3): los ``MetadatosInforme`` solo llevan el nombre del perfil.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from proxlaunch.nucleo.lote.constantes import LINEAS_LOG_TAREA
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    EntradaLibro,
    EstadoMV,
    InformeLote,
    MetadatosInforme,
    Plan,
    ResultadoRollback,
)
from proxlaunch.nucleo.reloj import Reloj

_CON_PROBLEMA = frozenset({EstadoMV.CON_AVISOS, EstadoMV.ERROR, EstadoMV.PARCIAL})


def _recortada(entrada: EntradaLibro) -> EntradaLibro:
    """Conserva el log de la tarea (últimas ``LINEAS_LOG_TAREA`` líneas) solo si la MV
    tiene avisos o error."""
    con_problema = (
        entrada.error is not None or bool(entrada.avisos) or entrada.estado in _CON_PROBLEMA
    )
    if not con_problema:
        return dataclasses.replace(entrada, log_tarea=())
    return dataclasses.replace(entrada, log_tarea=entrada.log_tarea[-LINEAS_LOG_TAREA:])


def construir_informe(
    plan: Plan,
    libro: Libro,
    metadatos: MetadatosInforme,
    *,
    rollback: Sequence[ResultadoRollback] = (),
    reloj: Reloj,
) -> InformeLote:
    """Construye el informe a partir del libro (única fuente de verdad, CA-L12.10).

    ``duraciones_s`` incluye las MVs terminadas (``t_fin - t_inicio``) y, en un informe
    parcial (cierre de la aplicación), las que siguen en curso medidas hasta ``reloj.ahora()``.
    """
    entradas = tuple(_recortada(e) for e in libro.instantanea())
    contadores = {estado.value: 0 for estado in EstadoMV}
    for entrada in entradas:
        contadores[entrada.estado.value] += 1
    ahora = reloj.ahora()
    duraciones: dict[int, float] = {}
    for entrada in entradas:
        if entrada.t_inicio is None:
            continue
        fin = entrada.t_fin if entrada.t_fin is not None else ahora
        duraciones[entrada.elemento.vmid] = max(0.0, fin - entrada.t_inicio)
    return InformeLote(
        metadatos=metadatos,
        id_lote=plan.id_lote,
        es_simulacion=plan.es_simulacion,
        pedidas=len(plan.elementos),
        contadores=contadores,
        entradas=entradas,
        duraciones_s=duraciones,
        plantilla=plan.definicion.plantilla,
        rollback=tuple(rollback),
        problemas_plan=plan.problemas,
    )
