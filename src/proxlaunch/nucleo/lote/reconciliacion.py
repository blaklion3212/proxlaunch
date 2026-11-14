"""Reconciliación de un envío incierto sin UPID (RF-L15, CA-L15.2 y CA-L15.5).

Solo lee (``config_vm``); nunca envía un POST. Se invoca cuando el POST de creación pudo
salir pero no se conoce el resultado (596/597, conexión abortada, excepción inesperada).
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Protocol

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import (
    COMPROBACIONES_EXISTENCIA_S,
    PREFIJO_ETIQUETA_LOTE,
)
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.modelos.origen import DetalleClon
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.reloj import Reloj

_log = logging.getLogger("proxlaunch.lote.reconciliacion")

AVISO_CREADA_TRAS_COMPROBAR = "creada_tras_comprobar"
# Mientras Proxmox crea la MV la config trae ``lock: create``; un clon en curso, ``lock: clone``
# (MVP 4, I4-§D). En ambos casos la propiedad aún no se puede decidir.
LOCKS_EN_CREACION = frozenset({"create", "clone"})
_PASO_CANCELACION_S = 1.0  # las esperas largas se parten para atender la cancelación
_SEPARADOR_ETIQUETAS = re.compile(r"[;, ]+")


class _ServicioExistencia(Protocol):
    def existe_vm(self, cfg: ConfiguracionVM) -> bool | None: ...


class _ClienteConfig(Protocol):
    def config_vm(self, nodo: str, vmid: int) -> dict[str, object] | None: ...


def etiqueta_del_lote(id_lote: str) -> str:
    return f"{PREFIJO_ETIQUETA_LOTE}{id_lote}"


def etiquetas_de_config(config: dict[str, object] | None) -> frozenset[str]:
    """Etiquetas de la configuración de Proxmox (``tags``, separadas por ``;``, sin orden)."""
    if not config:
        return frozenset()
    bruto = config.get("tags")
    if not isinstance(bruto, str):
        return frozenset()
    return frozenset(t for t in _SEPARADOR_ETIQUETAS.split(bruto.strip().lower()) if t)


def config_en_creacion(config: dict[str, object] | None) -> bool:
    """``True`` si la config aún es parcial: ``lock: create`` o ``lock: clone`` (D2).

    Mientras Proxmox crea o clona la MV la config solo trae ese bloqueo; leer entonces las
    etiquetas no demuestra nada, así que la propiedad todavía no se puede decidir.
    """
    if not config:
        return False
    return config.get("lock") in LOCKS_EN_CREACION


def tiene_etiqueta_del_lote(config: dict[str, object] | None, id_lote: str) -> bool:
    return etiqueta_del_lote(id_lote) in etiquetas_de_config(config)


def _esperar(reloj: Reloj, segundos: float, cancelado: threading.Event) -> bool:
    """Espera ``segundos`` en tramos cortos. Devuelve ``False`` si se canceló."""
    restante = segundos
    while restante > 0:
        if cancelado.is_set():
            return False
        paso = min(_PASO_CANCELACION_S, restante)
        reloj.dormir(paso)
        restante -= paso
    return not cancelado.is_set()


def reconciliar_incierta(
    servicio_creacion: _ServicioExistencia,
    cfg: ConfiguracionVM,
    reloj: Reloj,
    cancelado: threading.Event,
    *,
    id_lote: str,
    etiquetar: bool,
    cliente: _ClienteConfig,
) -> tuple[EstadoMV, str | None, ErrorProxLaunch | None]:
    """Averigua si una MV de envío incierto llegó a crearse.

    Hace hasta ``len(COMPROBACIONES_EXISTENCIA_S)`` comprobaciones con ``existe_vm`` en los
    instantes (acumulados) de ``COMPROBACIONES_EXISTENCIA_S``. Devuelve
    ``(estado, aviso, error)``:

    - existe y (``etiquetar`` es falso o lleva la etiqueta del lote) y su config ya no está en
      creación -> ``OK`` con el aviso ``creada_tras_comprobar``;
    - existe pero sin la etiqueta del lote (o sin poder leerla) ->
      ``EXISTE_SIN_CONFIRMAR_PROPIEDAD`` (no elegible para rollback);
    - existe pero su config sigue en creación (``lock: create``) -> se relee en la comprobación
      siguiente (con o sin etiquetas); si al final sigue así, ``CONEXION_PERDIDA``;
    - no existe en todas las comprobaciones -> ``NO_CREADA_SEGURA``;
    - no se pudo saber, o se canceló la espera -> ``CONEXION_PERDIDA`` con
      ``LOTE_EXISTENCIA_INDETERMINADA`` / ``LOTE_ENVIO_INCIERTO``.
    """
    params = {"nombre": cfg.nombre, "vmid": str(cfg.vmid)}
    anterior = 0.0
    en_creacion = False
    for objetivo in COMPROBACIONES_EXISTENCIA_S:
        if not _esperar(reloj, objetivo - anterior, cancelado):
            return (
                EstadoMV.CONEXION_PERDIDA,
                None,
                ErrorProxLaunch(CodigoError.LOTE_ENVIO_INCIERTO, params),
            )
        anterior = objetivo
        existe = servicio_creacion.existe_vm(cfg)
        if existe is None:
            return (
                EstadoMV.CONEXION_PERDIDA,
                None,
                ErrorProxLaunch(CodigoError.LOTE_EXISTENCIA_INDETERMINADA, params),
            )
        if existe:
            decision = _propiedad(cfg, id_lote, etiquetar, cliente)
            if decision is not None:
                return decision
            en_creacion = True  # config parcial: se vuelve a leer en la comprobación siguiente
    if en_creacion:
        # Seguía en creación tras todas las comprobaciones: dudosa, nunca OK sin etiqueta propia.
        return (
            EstadoMV.CONEXION_PERDIDA,
            None,
            ErrorProxLaunch(CodigoError.LOTE_EXISTENCIA_INDETERMINADA, params),
        )
    return EstadoMV.NO_CREADA_SEGURA, None, None


def _nodo_de_plantilla(cfg: ConfiguracionVM) -> str | None:
    """Nodo de la plantilla si la MV es un clon (durante un clon con ``target`` la config vive
    todavía en el nodo de la plantilla)."""
    detalle = cfg.detalle_origen
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA and isinstance(detalle, DetalleClon):
        return detalle.plantilla.nodo
    return None


def _config_de(cliente: _ClienteConfig, cfg: ConfiguracionVM) -> dict[str, object] | None:
    """Config de la MV en su nodo y, para un clon que aún no llegó a él, en el de la plantilla."""
    config = cliente.config_vm(cfg.nodo, cfg.vmid)
    if config is None:
        otro = _nodo_de_plantilla(cfg)
        if otro is not None and otro != cfg.nodo:
            config = cliente.config_vm(otro, cfg.vmid)
    return config


def _propiedad(
    cfg: ConfiguracionVM, id_lote: str, etiquetar: bool, cliente: _ClienteConfig
) -> tuple[EstadoMV, str | None, ErrorProxLaunch | None] | None:
    """La MV existe: comprueba que es de este lote (CA-L15.5).

    Devuelve ``None`` si la config aún está en creación (``lock: create``): no se decide.
    """
    try:
        config = _config_de(cliente, cfg)
    except Exception:
        if not etiquetar:
            # Sin etiquetas no hay nada que verificar: existe y basta (como antes).
            return EstadoMV.OK, AVISO_CREADA_TRAS_COMPROBAR, None
        # No se pudo leer: la propiedad no está demostrada, así que no es elegible.
        _log.warning("No se pudo leer la config para verificar la etiqueta (vmid=%s)", cfg.vmid)
        return EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD, None, None
    if config_en_creacion(config):
        # Aún se está creando (también sin etiquetas): no se declara OK todavía.
        return None
    if not etiquetar:
        return EstadoMV.OK, AVISO_CREADA_TRAS_COMPROBAR, None
    if tiene_etiqueta_del_lote(config, id_lote):
        return EstadoMV.OK, AVISO_CREADA_TRAS_COMPROBAR, None
    return EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD, None, None
