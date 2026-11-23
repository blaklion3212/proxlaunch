"""Lecturas del firewall para «Comprobar» y para el formulario (C3). Solo GET.

Ninguna función lanza ``ErrorProxLaunch``: un fallo se anota en el resultado y la validación lo
traduce en un aviso o en el bloqueo del control (V-C32, V-C34, V-C35, V-C38). Sin los privilegios
que Proxmox exige (``Sys.Audit`` en ``/``) no se hace la petición, para no provocar un 403.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Sequence
from typing import Any

from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import (
    RE_GRUPO,
    FirewallPlantilla,
    InfoFirewall,
    LecturaGrupos,
    ReglaFirewall,
)
from proxlaunch.nucleo.firewall.reglas import permite_entrada
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos, Plantilla
from proxlaunch.nucleo.origen.permisos import estado_privilegio

_log = logging.getLogger("proxlaunch.firewall.lectura")


def _activo(opciones: dict[str, Any]) -> bool:
    """``enable`` de unas opciones de firewall (ausente = apagado; Proxmox lo devuelve 0/1)."""
    valor = opciones.get("enable")
    if isinstance(valor, str):
        return valor.strip() == "1"
    return valor is True or (isinstance(valor, int) and valor >= 1)


def leer_grupos(cliente: ClienteProxmox) -> LecturaGrupos:
    """Grupos de seguridad del clúster (``GET /cluster/firewall/groups``, sin privilegio).

    Un fallo da ``grupos=None`` con el error: el formulario deja el control deshabilitado (V-C32).
    """
    try:
        return LecturaGrupos(tuple(cliente.grupos_firewall()))
    except ErrorProxLaunch as e:
        _log.info("Grupos de seguridad no disponibles: %s", e.codigo)
        return LecturaGrupos(None, e)


def leer_reglas_grupo(
    cliente: ClienteProxmox, grupo: str
) -> tuple[tuple[ReglaFirewall, ...] | None, ErrorProxLaunch | None]:
    """Reglas de un grupo (``GET /cluster/firewall/groups/{g}``, exige ``Sys.Audit`` en ``/``).

    ``(None, error)`` si no se pudo leer o el nombre no cumple ``RE_GRUPO`` (no se envía nada).
    """
    if not RE_GRUPO.fullmatch(grupo):
        return None, ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "firewall.grupo"})
    try:
        return tuple(cliente.reglas_grupo_firewall(grupo)), None
    except ErrorProxLaunch as e:
        _log.info("Reglas del grupo no disponibles: %s", e.codigo)
        return None, e


def _firewall_general(cliente: ClienteProxmox, auditor: bool | None) -> bool | None:
    """Si el firewall del centro de datos está encendido; ``None`` = no se pudo saber."""
    if auditor is False:
        return None
    try:
        return _activo(cliente.opciones_firewall_cluster())
    except ErrorProxLaunch as e:
        _log.info("Firewall general no disponible: %s", e.codigo)
        return None


def _leer_plantilla(cliente: ClienteProxmox, plantilla: Plantilla) -> FirewallPlantilla:
    """Opciones y reglas del firewall de una plantilla (``VM.Audit``); un fallo la deja ilegible."""
    try:
        opciones = cliente.opciones_firewall_vm(plantilla.nodo, plantilla.vmid)
        reglas = cliente.reglas_firewall_vm(plantilla.nodo, plantilla.vmid)
    except ErrorProxLaunch as e:
        _log.info("Firewall de la plantilla no disponible: %s", e.codigo)
        return FirewallPlantilla(legible=False)
    return FirewallPlantilla(
        legible=True,
        activo=_activo(opciones),
        grupos=frozenset(r.accion for r in reglas if r.tipo == "group" and r.activa),
        con_reglas=bool(reglas),
    )


def leer_info_firewall(
    cliente: ClienteProxmox,
    permisos: PermisosEfectivos | None,
    grupos: Collection[str],
    plantillas: Sequence[Plantilla],
) -> InfoFirewall:
    """Todas las lecturas de firewall de un «Comprobar» (DT-C11), una vez cada una.

    Lee la lista de grupos, ``GET /cluster/firewall/options``, el contenido de cada grupo
    elegido que exista (ambos solo si ``Sys.Audit`` en ``/`` no es ``False``) y, por plantilla
    distinta (por VMID), sus opciones y reglas.
    """
    lectura = leer_grupos(cliente)
    auditor = estado_privilegio(permisos, "Sys.Audit", "/")
    existentes = None if lectura.grupos is None else {g.nombre for g in lectura.grupos}
    entrada: dict[str, bool | None] = {}
    for g in sorted(set(grupos)):
        if existentes is not None and g not in existentes:
            continue  # «no existe» lo da V-C30; no se pide el contenido de un grupo inexistente
        if auditor is False:
            entrada[g] = None
            continue
        reglas, _ = leer_reglas_grupo(cliente, g)
        entrada[g] = None if reglas is None else permite_entrada(reglas)
    por_vmid: dict[int, FirewallPlantilla] = {}
    for p in plantillas:
        if p.vmid not in por_vmid:
            por_vmid[p.vmid] = _leer_plantilla(cliente, p)
    return InfoFirewall(
        grupos=lectura.grupos,
        error_grupos=lectura.error,
        general_activo=_firewall_general(cliente, auditor),
        entrada_por_grupo=entrada,
        plantillas=por_vmid,
    )
