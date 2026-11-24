"""Reintentar los ajustes pendientes de un lote (RF-O22, CA-O22.6; Debería).

Una MV ``PARCIAL`` con avisos ``ajuste_pendiente:*`` está creada pero le falta alguna etiqueta,
parámetro de CPU/memoria o ampliación de disco. Esta función reenvía SOLO los ``PUT``
(idempotentes, valores absolutos) que aún no coinciden: nunca un ``POST`` de creación ni nada
sobre una MV que no esté en el libro (INV-L1, INV-L4).
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any

from proxlaunch.nucleo.firewall.modelos import usa_firewall
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import EntradaLibro, EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote, FabricaCreacion, Observador
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.red.modelos import usa_red_clon
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


def ajustes_pendientes(entrada: EntradaLibro) -> frozenset[str]:
    """Nombres de ajuste de los avisos ``ajuste_pendiente:*`` de la entrada (``cloudinit``…)."""
    prefijo = f"{AVISO_AJUSTE_PENDIENTE}:"
    return frozenset(a.removeprefix(prefijo) for a in entrada.avisos if a.startswith(prefijo))


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

    Fase C: lo mismo si la MV usa red del clon o firewall: los pasos ``red``, ``firewall_opciones``
    y ``firewall_regla`` se repiten solo si constan como pendientes (la red se recalcula sobre la
    config actual del clon; la regla no se duplica).

    Fase D: el paso ``hardware`` (mapeos PCI/USB de un clon) se repite solo si consta como
    pendiente y solo con los dispositivos que la MV aún no tiene asignados.

    Fase B: si la MV lleva cloud-init, solo se reenvían los pasos que constan como pendientes
    (``cloudinit``, ``contrasena``…); la contraseña únicamente si el ``Secreto`` del plan sigue
    definido (si no, la MV sigue ``PARCIAL`` con ``CONTRASENA_OLVIDADA``). Sin cloud-init el
    reintento es el de 0.6.0.
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
            cfg = entrada.elemento.cfg
            # Sin fase B, C ni D el reintento es exactamente el de 0.6.0.
            hw = cfg.hardware_cluster
            if (
                cfg.cloudinit is None
                and not usa_red_clon(cfg.red_clon)
                and not usa_firewall(cfg.firewall)
                and (hw is None or hw.vacio)
            ):
                res = servicio.reintentar_ajustes(cfg, inv, control.evento_abandono)
            else:
                extra_c: dict[str, Any] = {}
                if usa_red_clon(cfg.red_clon):
                    extra_c = {
                        "macs_originales": dict(entrada.macs_originales),
                        "al_leer_macs": lambda m, v=vmid: libro.registrar_macs_originales(v, m),
                    }
                res = servicio.reintentar_ajustes(
                    cfg,
                    inv,
                    control.evento_abandono,
                    pendientes=ajustes_pendientes(entrada),
                    **extra_c,
                )
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
            red_final=res.red_final,
        )
        try:
            observador(nueva)
        except Exception:
            _log.exception("El observador del lote falló (vmid=%s)", vmid)
