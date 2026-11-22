"""Interpretación de ``network-get-interfaces`` y elección de la IP (RF-B3.4). Puro.

La respuesta es texto no confiable: ``interpretar_interfaces`` nunca lanza y descarta lo que
no tiene la forma esperada.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from proxlaunch.nucleo.agente.modelos import InterfazAgente

MAX_INTERFACES = 64
MAX_DIRECCIONES = 32
MAX_NOMBRE = 64
_RE_MAC = re.compile(r"[0-9a-f]{12}")
# Lista blanca del nombre de interfaz: lo demás (controles, Cf, bidi, espacios...) se quita (M3).
_RE_NO_PERMITIDO = re.compile(r"[^A-Za-z0-9._:@-]")
# Interfaces de contenedores y puentes ajenos a la MV (RF-B3.4).
_PREFIJOS_DESCARTADOS = ("docker", "br-", "veth", "virbr")
_MAC_NULA = "0" * 12


def _normalizar_mac(valor: object) -> str | None:
    """12 dígitos hexadecimales en minúsculas, sin separadores; ``None`` si no es una MAC."""
    if not isinstance(valor, str):
        return None
    limpia = re.sub(r"[:\-.\s]", "", valor).lower()
    return limpia if _RE_MAC.fullmatch(limpia) else None


def _formatear_mac(plana: str) -> str:
    return ":".join(plana[i : i + 2] for i in range(0, 12, 2))


def _direccion(valor: object) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not isinstance(valor, str) or "%" in valor or len(valor) > 64:
        return None
    try:
        return ipaddress.ip_address(valor.strip())
    except ValueError:
        return None


def interpretar_interfaces(respuesta: Any) -> tuple[InterfazAgente, ...]:
    """Convierte la respuesta del agente en interfaces saneadas. Nunca lanza.

    Acepta ``{"result": [...]}`` o la lista directamente. Se ignora todo campo ausente o de
    tipo inesperado; los límites acotan el trabajo ante una respuesta enorme.
    """
    try:
        lista = respuesta.get("result") if isinstance(respuesta, dict) else respuesta
        if not isinstance(lista, list):
            return ()
        interfaces: list[InterfazAgente] = []
        for entrada in lista[:MAX_INTERFACES]:
            if not isinstance(entrada, dict):
                continue
            nombre = entrada.get("name")
            if not isinstance(nombre, str) or not nombre:
                continue
            nombre = _RE_NO_PERMITIDO.sub("", nombre)[:MAX_NOMBRE]
            if not nombre:
                continue
            mac = _normalizar_mac(entrada.get("hardware-address"))
            direcciones = entrada.get("ip-addresses")
            ipv4: list[str] = []
            ipv6: list[str] = []
            for d in direcciones[:MAX_DIRECCIONES] if isinstance(direcciones, list) else ():
                a = _direccion(d.get("ip-address") if isinstance(d, dict) else None)
                if isinstance(a, ipaddress.IPv4Address) and str(a) not in ipv4:
                    ipv4.append(str(a))
                elif isinstance(a, ipaddress.IPv6Address) and str(a) not in ipv6:
                    ipv6.append(str(a))
            interfaces.append(
                InterfazAgente(
                    nombre=nombre,
                    mac=None if mac is None else _formatear_mac(mac),
                    ipv4=tuple(ipv4),
                    ipv6=tuple(ipv6),
                )
            )
        return tuple(interfaces)
    except Exception:  # noqa: BLE001 - texto no confiable: nunca debe lanzar
        return ()


@dataclass(frozen=True)
class Eleccion:
    principal: str
    parcial: bool
    otras: tuple[str, ...]
    descartadas: tuple[str, ...]


def _descartada(i: InterfazAgente) -> bool:
    nombre = i.nombre.lower()
    if nombre == "lo" or nombre.startswith(_PREFIJOS_DESCARTADOS):
        return True
    plana = _normalizar_mac(i.mac)
    return plana is None or plana == _MAC_NULA


def _ipv4_util(texto: str) -> bool:
    a = ipaddress.IPv4Address(texto)
    return not (a.is_loopback or a.is_link_local or a.is_unspecified or a.is_multicast)


def _ipv6_global(texto: str) -> bool:
    a = ipaddress.IPv6Address(texto)
    return not (a.is_loopback or a.is_link_local or a.is_unspecified or a.is_multicast)


def elegir_ip(
    interfaces: Sequence[InterfazAgente], mac_net0: str | None, *, final: bool
) -> Eleccion | None:
    """Elige la IP principal (RF-B3.4).

    Prioridad: 1) IPv4 de la interfaz con la MAC de ``net0`` (sin distinguir mayúsculas ni
    separadores); solo con ``final=True``: 2) IPv4 de otra interfaz y 3) IPv6 global, ambas
    ``parcial``. Se descartan ``lo``, ``docker*``, ``br-*``, ``veth*``, ``virbr*``, las
    interfaces sin MAC o con MAC nula y las direcciones loopback, link-local y no
    especificadas. ``otras`` son el resto de IP válidas; ``descartadas``, los nombres de las
    interfaces descartadas. ``None`` = todavía no hay elección.
    """
    descartadas = tuple(dict.fromkeys(i.nombre for i in interfaces if _descartada(i)))
    validas = [i for i in interfaces if not _descartada(i)]
    v4 = [(i, ip) for i in validas for ip in i.ipv4 if _ipv4_util(ip)]
    v6 = [(i, ip) for i in validas for ip in i.ipv6 if _ipv6_global(ip)]
    objetivo = _normalizar_mac(mac_net0)

    principal: str | None = None
    parcial = False
    if objetivo is not None:
        propia = next((ip for i, ip in v4 if _normalizar_mac(i.mac) == objetivo), None)
        if propia is not None:
            principal = propia
    if principal is None and final:
        if v4:
            principal, parcial = v4[0][1], True
        elif v6:
            principal, parcial = v6[0][1], True
    if principal is None:
        return None
    otras = tuple(dict.fromkeys(ip for _, ip in (*v4, *v6) if ip != principal))
    return Eleccion(principal=principal, parcial=parcial, otras=otras, descartadas=descartadas)
