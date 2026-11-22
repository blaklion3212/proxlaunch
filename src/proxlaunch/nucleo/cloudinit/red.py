"""Red de cloud-init (RF-B1.7, RF-B1.8): IPv4/CIDR, puerta de enlace, DNS y dominio. Puro.

Las reglas son estrictas a propósito: Proxmox no valida todo y un valor ambiguo (ceros a la
izquierda, prefijo fuera de 8–30) acabaría en la MV sin aviso.
"""

from __future__ import annotations

import ipaddress
import re
from enum import StrEnum
from typing import Final

from proxlaunch.nucleo.cloudinit.modelos import ModoTarjeta, TarjetaCloudInit

PREFIJO_MIN: Final = 8
PREFIJO_MAX: Final = 30
MAX_DOMINIO: Final = 253

_RE_OCTETO = re.compile(r"[0-9]{1,3}")
_RE_PREFIJO = re.compile(r"[0-9]{1,2}")
_RE_ETIQUETA_DNS = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


class MotivoRed(StrEnum):
    SIN_PREFIJO = "sin_prefijo"
    PREFIJO = "prefijo"
    OCTETO = "octeto"
    CEROS = "ceros"
    RESERVADA = "reservada"
    RED_O_DIFUSION = "red_o_difusion"
    FUERA_DE_RED = "fuera_de_red"
    IGUAL_A_IP = "igual_a_ip"
    NO_IP = "no_ip"


def _analizar_ipv4(texto: str) -> tuple[ipaddress.IPv4Address | None, MotivoRed | None]:
    """IPv4 estricta: cuatro octetos decimales de 1–3 dígitos, sin ceros a la izquierda."""
    partes = texto.split(".")
    if len(partes) != 4 or not all(_RE_OCTETO.fullmatch(p) for p in partes):
        return None, MotivoRed.OCTETO
    if any(len(p) > 1 and p.startswith("0") for p in partes):
        return None, MotivoRed.CEROS
    if any(int(p) > 255 for p in partes):
        return None, MotivoRed.OCTETO
    return ipaddress.IPv4Address(texto), None


def _reservada(a: ipaddress.IPv4Address) -> bool:
    """0.0.0.0/8, loopback, multicast, link-local y 240.0.0.0/4 (incluida 255.255.255.255)."""
    return a.packed[0] == 0 or a.is_loopback or a.is_multicast or a.is_link_local or a.is_reserved


def _interfaz(texto: str) -> tuple[ipaddress.IPv4Interface | None, MotivoRed | None]:
    """Analiza ``a.b.c.d/n`` hasta comprobar el prefijo y las direcciones reservadas."""
    if not isinstance(texto, str) or not texto:
        return None, MotivoRed.NO_IP
    direccion, barra, prefijo = texto.partition("/")
    if not barra:
        return None, MotivoRed.SIN_PREFIJO
    if (
        not _RE_PREFIJO.fullmatch(prefijo)
        or (len(prefijo) > 1 and prefijo.startswith("0"))
        or not PREFIJO_MIN <= int(prefijo) <= PREFIJO_MAX
    ):
        return None, MotivoRed.PREFIJO
    ip, motivo = _analizar_ipv4(direccion)
    if ip is None:
        return None, motivo
    if _reservada(ip):
        return None, MotivoRed.RESERVADA
    return ipaddress.IPv4Interface(f"{ip}/{prefijo}"), None


def motivo_cidr(texto: str) -> MotivoRed | None:
    """Por qué ``texto`` no es una IP fija válida (V-B26/V-B27); ``None`` si lo es."""
    interfaz, motivo = _interfaz(texto)
    if interfaz is None:
        return motivo
    red = interfaz.network
    if interfaz.ip in (red.network_address, red.broadcast_address):
        return MotivoRed.RED_O_DIFUSION
    return None


def motivo_puerta(cidr: str, puerta: str) -> MotivoRed | None:
    """Por qué ``puerta`` no sirve con la IP ``cidr`` (V-B28); ``None`` si sirve.

    Debe ser IPv4, distinta de la IP, estar en su red y no ser la dirección de red ni la de
    difusión. Si ``cidr`` no es analizable devuelve ``NO_IP`` (la IP tiene su propio error).
    """
    interfaz, _ = _interfaz(cidr)
    if interfaz is None:
        return MotivoRed.NO_IP
    if not isinstance(puerta, str):
        return MotivoRed.NO_IP
    gw, motivo = _analizar_ipv4(puerta)
    if gw is None:
        return MotivoRed.NO_IP if motivo is None else motivo
    if gw == interfaz.ip:
        return MotivoRed.IGUAL_A_IP
    red = interfaz.network
    if gw not in red:
        return MotivoRed.FUERA_DE_RED
    if gw in (red.network_address, red.broadcast_address):
        return MotivoRed.RED_O_DIFUSION
    return None


def _ip_dns_valida(texto: str) -> bool:
    if "%" in texto:  # id de zona IPv6: no vale como servidor DNS
        return False
    try:
        ipaddress.ip_address(texto)
    except ValueError:
        return False
    return True


def normalizar_dns(texto: str) -> tuple[tuple[str, ...], MotivoRed | None]:
    """Servidores DNS separados por espacio o coma (RF-B1.8); sin repetidos y en orden.

    Devuelve ``(direcciones, motivo)``. Un elemento que no es una IPv4/IPv6 (``8.8.8``,
    ``dns.local``, o texto con ``;``) da ``((), NO_IP)``. Vacío = ``((), None)``.
    """
    if not isinstance(texto, str):
        return (), MotivoRed.NO_IP
    resultado: list[str] = []
    for token in re.split(r"[\s,]+", texto.strip()):
        if not token:
            continue
        if not _ip_dns_valida(token):
            return (), MotivoRed.NO_IP
        normal = str(ipaddress.ip_address(token))
        if normal not in resultado:
            resultado.append(normal)
    return tuple(resultado), None


def dominio_valido(texto: str) -> bool:
    """Dominio de búsqueda según RFC 1123, de hasta 253 caracteres, sin ``_`` ni ``..``."""
    if not isinstance(texto, str) or not 0 < len(texto) <= MAX_DOMINIO:
        return False
    return all(_RE_ETIQUETA_DNS.fullmatch(e) for e in texto.split("."))


def valor_ipconfig(t: TarjetaCloudInit) -> str | None:
    """Valor de ``ipconfigN``: ``ip=dhcp``, ``ip=a/n[,gw=g]`` o ``None`` (sin configurar)."""
    if t.modo == ModoTarjeta.DHCP:
        return "ip=dhcp"
    if t.modo == ModoTarjeta.FIJA and t.ip:
        return f"ip={t.ip}" + (f",gw={t.puerta}" if t.puerta else "")
    return None


def ip_desplazada(cidr: str, k: int) -> str | None:
    """``cidr`` con la IP sumada ``k``; ``None`` si sale de los hosts útiles de su red."""
    interfaz, _ = _interfaz(cidr)
    if interfaz is None:
        return None
    red = interfaz.network
    try:
        nueva = interfaz.ip + k
    except (ipaddress.AddressValueError, ValueError):
        return None
    if not red.network_address < nueva < red.broadcast_address:
        return None
    return f"{nueva}/{red.prefixlen}"


def ip_desplazada_sin_limite(cidr: str, k: int) -> str | None:
    """Como ``ip_desplazada`` pero sin exigir que sea un host útil (para que ``expandir_serie``
    deje ver la dirección que desborda); ``None`` solo si ``cidr`` no se puede analizar."""
    interfaz, _ = _interfaz(cidr)
    if interfaz is None:
        return None
    try:
        nueva = interfaz.ip + k
    except (ipaddress.AddressValueError, ValueError):
        return None
    return f"{nueva}/{interfaz.network.prefixlen}"
