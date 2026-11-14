"""Reintentar los ajustes pendientes de un lote (RF-O22, CA-O22.6; Debería).

Una MV ``PARCIAL`` con avisos ``ajuste_pendiente:*`` está creada pero le falta alguna etiqueta,
parámetro de CPU/memoria o ampliación de disco. Esta función reenvía SOLO los ``PUT``
(idempotentes, valores absolutos) que aún no coinciden: nunca un ``POST`` de creación ni nada
sobre una MV que no esté en el libro (INV-L1, INV-L4).
"""

from __future__ import annotations

import logging
from collections.abc import Collection

from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import EntradaLibro, EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote, FabricaCreacion, Observador
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.catalogo import con_catalogo
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.servicios.creacion import AVISO_AJUSTE_PENDIENTE, ServicioCreacion

_log = logging.getLogger("proxlaunch.lote.ajustes")

# Marca que sustituye los avisos de ajuste pendiente cuando el reintento los resuelve
# (``Libro.resolver`` conserva los avisos previos si los nuevos vienen vacíos).
AVISO_AJUSTES_REINTENTADOS = "ajustes_reintentados"

_ESTADO_POR_DESENLACE = {
    Desenlace.OK: EstadoMV.OK,
    Desenlace.CON_AVISOS: EstadoMV.CON_AVISOS,
    Desenlace.PARCIAL: EstadoMV.PARCIAL,
}


def tiene_ajustes_pendientes(entrada: EntradaLibro) -> bool:
    """``True`` si la MV es ``PARCIAL``, se envió su creación y consta un ajuste pendiente."""
    return (
        entrada.estado == EstadoMV.PARCIAL
        and entrada.post_intentado
        and entrada.upid is not None
        and any(a.startswith(f"{AVISO_AJUSTE_PENDIENTE}:") for a in entrada.avisos)
    )


def reintentar_ajustes(
    libro: Libro,
    vmids: Collection[int],
    sesion: Sesion,
    reloj: Reloj,
    inv: Inventario,
    observador: Observador,
    control: ControlLote,
    *,
    fabrica_creacion: FabricaCreacion = ServicioCreacion,
) -> None:
    """Reintenta los ajustes de las MVs de ``vmids`` que lo necesiten. Bloqueante.

    Las que no estén en el libro, no sean ``PARCIAL`` con ajustes pendientes o no tengan UPID
    propio se ignoran. Cada resultado se aplica al libro con ``Libro.resolver``: ``OK`` si todo
    quedó aplicado, ``PARCIAL`` (con los ajustes que faltan) si algo vuelve a fallar. Un
    fallo de red o un error de la comprobación deja la MV como estaba. Se detiene si el
    control se cancela o suspende.
    """
    if libro.plan.catalogo is not None:
        inv = con_catalogo(inv, libro.plan.catalogo)
    servicio = fabrica_creacion(sesion, reloj)
    pedidos = set(vmids)
    for entrada in libro.instantanea():
        if control.cancelado.is_set() or control.suspendido:
            return
        vmid = entrada.elemento.vmid
        if vmid not in pedidos or not tiene_ajustes_pendientes(entrada):
            continue
        try:
            res = servicio.reintentar_ajustes(entrada.elemento.cfg, inv, control.evento_abandono)
        except Exception:
            _log.exception("Fallo inesperado al reintentar los ajustes (vmid=%s)", vmid)
            continue
        estado = _ESTADO_POR_DESENLACE.get(res.desenlace)
        if estado is None:  # error, cancelación o red: la MV queda como estaba
            _log.info("Reintento de ajustes sin resolver (vmid=%s, %s)", vmid, res.desenlace)
            continue
        avisos = tuple(res.avisos) or (AVISO_AJUSTES_REINTENTADOS,)
        nueva = libro.resolver(
            vmid,
            estado,
            t_fin=reloj.ahora(),
            error=res.error,
            avisos=avisos,
        )
        try:
            observador(nueva)
        except Exception:
            _log.exception("El observador del lote falló (vmid=%s)", vmid)
