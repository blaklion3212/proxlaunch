"""Lectura de los errores de SDN y de red del servidor (C2, C4). Puro, sin E/S.

``traductor_errores`` no cambia (DT-C20): un 403 sigue siendo ``PERMISO_INSUFICIENTE`` con
``ruta``/``privilegio``. Estas funciones lo anotan con lo que sabe el paso que lo recibió para que
el texto diga qué tarjeta, qué red y de qué lado (plantilla, antigua o nueva) falló.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.red.modelos import RE_NOMBRE_RED

# «/sdn/zones/<zona>/<red>[/<vlan>]»: la ruta del 403 de ``SDN.Use`` (INV-C §2.3).
_RE_RUTA_SDN: Final = re.compile(
    r"^/sdn/zones/(?P<zona>[A-Za-z0-9_.-]{1,40})/(?P<red>[A-Za-z0-9_.-]{1,40})"
    r"(?:/(?P<vlan>[0-9]{1,4}))?$"
)
_RE_IPAM: Final = re.compile(
    r"can't find any free ip(?: in zone\s+(?P<zona>[A-Za-z0-9_.-]{1,40}))?", re.IGNORECASE
)
_PASOS: Final = frozenset({"clon", "red", "crear"})


def _tarjeta_de(red: str, por_indice: Mapping[int, str]) -> str | None:
    """``netN`` de la tarjeta (la de menor índice) que usa esa red, si la hay."""
    indices = sorted(i for i, nombre in por_indice.items() if nombre == red)
    return f"net{indices[0]}" if indices else None


def anotar_error_red(
    error: ErrorProxLaunch, *, paso: str, antiguas: Mapping[int, str], nuevas: Mapping[int, str]
) -> ErrorProxLaunch:
    """Anota un error de red con lo que sabe el paso que lo recibió.

    ``paso``: ``"clon"`` (el 403 es por la red de la PLANTILLA), ``"red"`` (el ``PUT`` de red: la
    red puede ser la antigua o la nueva) o ``"crear"`` (``POST`` de la MV). ``antiguas`` y
    ``nuevas`` asocian el índice de tarjeta con su bridge/VNet. Un 403 de ``SDN.Use`` gana
    ``zona``, ``red``, ``vlan`` (si la ruta la trae), ``lado`` (``plantilla|antigua|nueva``) y
    ``tarjeta`` (``"netN"``, si se identifica). Un texto de IPAM agotado pasa a
    ``RED_SIN_DIRECCIONES``. Cualquier otro error se devuelve igual.
    """
    if paso not in _PASOS:
        return error
    if error.codigo == CodigoError.PERMISO_INSUFICIENTE:
        m = _RE_RUTA_SDN.fullmatch(error.params.get("ruta", ""))
        if m is None or RE_NOMBRE_RED.fullmatch(m.group("red")) is None:
            return error
        red = m.group("red")
        params = dict(error.params)
        params["zona"] = m.group("zona")
        params["red"] = red
        if m.group("vlan") is not None:
            params["vlan"] = m.group("vlan")
        if paso == "clon":
            params["lado"] = "plantilla"
            tarjeta = _tarjeta_de(red, antiguas)
        elif paso == "crear":
            params["lado"] = "nueva"
            tarjeta = _tarjeta_de(red, nuevas)
        else:
            tarjeta = _tarjeta_de(red, nuevas)
            if tarjeta is not None:
                params["lado"] = "nueva"
            else:
                tarjeta = _tarjeta_de(red, antiguas)
                params["lado"] = "antigua"
        if tarjeta is not None:
            params["tarjeta"] = tarjeta
        return ErrorProxLaunch(error.codigo, params, error.detalle_tecnico)
    m_ipam = _RE_IPAM.search(error.detalle_tecnico)
    if m_ipam is not None:
        params = {}
        if m_ipam.group("zona"):
            params["zona"] = m_ipam.group("zona")
        return ErrorProxLaunch(CodigoError.RED_SIN_DIRECCIONES, params, error.detalle_tecnico)
    return error


def es_error_digest(error: ErrorProxLaunch) -> bool:
    """``True`` si el error es por ``digest`` caducado (la config cambió entre la lectura y el
    ``PUT``): el código HTTP exacto es [LAB], así que se reconoce por el texto (§0)."""
    texto = error.detalle_tecnico.lower()
    return "digest" in texto or "modified configuration" in texto
