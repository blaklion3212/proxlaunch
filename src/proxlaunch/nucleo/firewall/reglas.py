"""Parámetros de las peticiones de firewall y lectura de reglas (C3). Puro, sin E/S.

La regla que se añade a cada máquina es siempre de tipo ``group`` y sin ``iface``: aplica a todas
las tarjetas (P-C5). Las políticas se envían siempre explícitas para no depender de los valores
por defecto de cada versión de Proxmox (RF-C3.3).
"""

from __future__ import annotations

from collections.abc import Sequence

from proxlaunch.nucleo.cloudinit.modelos import ModoTarjeta
from proxlaunch.nucleo.firewall.modelos import (
    COMENTARIO_REGLA,
    RE_GRUPO,
    VALOR_POLITICA,
    FirewallMV,
    ModoDhcp,
    ReglaFirewall,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM


def hay_dhcp_cloudinit(cfg: ConfiguracionVM) -> bool:
    """``True`` si alguna tarjeta usa DHCP por cloud-init (``ipconfigN=ip=dhcp``)."""
    ci = cfg.cloudinit
    return ci is not None and any(t.modo == ModoTarjeta.DHCP for t in ci.tarjetas)


def dhcp_efectivo(fw: FirewallMV, cfg: ConfiguracionVM) -> bool:
    """Si las opciones llevan ``dhcp=1``: ``SI``/``NO`` mandan y ``AUTO`` mira cloud-init."""
    if fw.dhcp == ModoDhcp.SI:
        return True
    if fw.dhcp == ModoDhcp.NO:
        return False
    return hay_dhcp_cloudinit(cfg)


def parametros_opciones(fw: FirewallMV, cfg: ConfiguracionVM) -> dict[str, str]:
    """Cuerpo de ``PUT …/firewall/options``: ``enable`` y las dos políticas, y ``dhcp=1`` solo si
    procede. Con «Permitir DHCP» en NO explícito se envía ``dhcp=0`` (no se hereda el ``dhcp=1``
    de la plantilla); con AUTO sin DHCP no se envía la clave."""
    parametros = {
        "enable": "1",
        "policy_in": VALOR_POLITICA[fw.politica_entrada],
        "policy_out": VALOR_POLITICA[fw.politica_salida],
    }
    if dhcp_efectivo(fw, cfg):
        parametros["dhcp"] = "1"
    elif fw.dhcp == ModoDhcp.NO:
        parametros["dhcp"] = "0"
    return parametros


def parametros_regla(grupo: str) -> dict[str, str]:
    """Cuerpo de ``POST …/firewall/rules`` para el grupo de seguridad (sin ``iface``).

    Raises:
        ValueError: si ``grupo`` no cumple ``RE_GRUPO`` (nunca se envía un nombre dudoso).
    """
    if not RE_GRUPO.fullmatch(grupo):
        raise ValueError("nombre de grupo de seguridad no válido")
    return {"type": "group", "action": grupo, "enable": "1", "comment": COMENTARIO_REGLA}


def regla_ya_existe(reglas: Sequence[ReglaFirewall], grupo: str) -> bool:
    """``True`` si ya hay una regla ``type=group`` ACTIVA de ese grupo (no se duplica, P-C8).

    Una regla de grupo deshabilitada (``enable=0``) no cuenta: se añade otra activa.
    """
    return any(r.tipo == "group" and r.accion == grupo and r.activa for r in reglas)


def permite_entrada(reglas: Sequence[ReglaFirewall]) -> bool:
    """``True`` si alguna regla de entrada ``ACCEPT`` está activa (V-C38)."""
    return any(r.tipo == "in" and r.accion.upper() == "ACCEPT" and r.activa for r in reglas)
