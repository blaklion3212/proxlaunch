"""Interpretación de las tarjetas de red ``net0..net31`` de una config (C4). Puro, sin E/S.

Todo lo que viene de la config de Proxmox es texto no confiable (RNF-C6): una tarjeta con un
formato inesperado queda ``legible=False`` y nunca se reescribe (V-C20, RD-C4).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Final

from proxlaunch.nucleo.red.modelos import (
    MAX_TARJETAS,
    RE_NOMBRE_RED,
    AccionTarjeta,
    CampoRed,
    RedClon,
    TarjetaPlantilla,
    usa_red_clon,
)

_RE_NET: Final = re.compile(r"^net(0|[1-9][0-9]?)$")
_RE_IPCONFIG: Final = re.compile(r"^ipconfig(0|[1-9][0-9]?)$")
_RE_MAC: Final = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")
_RE_MODELO: Final = re.compile(r"^[A-Za-z0-9_]{1,32}$")
_RE_CLAVE: Final = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_RE_ENTERO: Final = re.compile(r"^[0-9]{1,5}$")
_RE_DECIMAL: Final = re.compile(r"^[0-9]{1,9}(?:\.[0-9]{1,6})?$")
# Opciones que la app gestiona: el resto se conserva tal cual en ``otras``.
_GESTIONADAS: Final = frozenset({"bridge", "tag", "firewall", "mtu", "rate"})


def _ilegible(indice: int) -> TarjetaPlantilla:
    return TarjetaPlantilla(indice=indice, legible=False)


def interpretar_tarjeta(indice: int, valor: object) -> TarjetaPlantilla:
    """Interpreta ``netN`` (``modelo=MAC,bridge=…,tag=…,firewall=1,mtu=…,rate=…,otras``).

    Nunca lanza: lo que no se entiende (texto no cadena, sin ``modelo=MAC``, claves repetidas o
    valores fuera de forma) devuelve ``legible=False``.
    """
    if not isinstance(valor, str) or not valor.strip():
        return _ilegible(indice)
    partes = [p.strip() for p in valor.split(",")]
    modelo, igual, mac = partes[0].partition("=")
    if not igual or _RE_MODELO.fullmatch(modelo) is None or _RE_MAC.fullmatch(mac) is None:
        return _ilegible(indice)
    bridge: str | None = None
    vlan: int | None = None
    firewall = False
    mtu: int | None = None
    limite: float | None = None
    otras: list[tuple[str, str]] = []
    vistas: set[str] = set()
    for parte in partes[1:]:
        clave, igual, v = parte.partition("=")
        if not igual or _RE_CLAVE.fullmatch(clave) is None or clave in vistas:
            return _ilegible(indice)
        vistas.add(clave)
        if clave == "bridge":
            if RE_NOMBRE_RED.fullmatch(v) is None:
                return _ilegible(indice)
            bridge = v
        elif clave == "tag":
            if _RE_ENTERO.fullmatch(v) is None:
                return _ilegible(indice)
            vlan = int(v)
        elif clave == "firewall":
            if v not in ("0", "1"):
                return _ilegible(indice)
            firewall = v == "1"
        elif clave == "mtu":
            if _RE_ENTERO.fullmatch(v) is None:
                return _ilegible(indice)
            mtu = int(v)
        elif clave == "rate":
            if _RE_DECIMAL.fullmatch(v) is None:
                return _ilegible(indice)
            limite = float(v)
        else:
            if not v or "," in v:
                return _ilegible(indice)
            otras.append((clave, v))
    return TarjetaPlantilla(
        indice=indice,
        legible=True,
        modelo=modelo,
        mac=mac,
        bridge=bridge,
        vlan=vlan,
        firewall=firewall,
        mtu=mtu,
        limite_mb=limite,
        otras=tuple(otras),
    )


def tarjetas_de_config(config: Mapping[str, object]) -> tuple[TarjetaPlantilla, ...]:
    """Las ``netN`` de la config, interpretadas y ordenadas por índice (``net0..net31``)."""
    encontradas: dict[int, TarjetaPlantilla] = {}
    for clave, valor in config.items():
        if not isinstance(clave, str):
            continue
        m = _RE_NET.fullmatch(clave)
        if m is None or int(m.group(1)) >= MAX_TARJETAS:
            continue
        indice = int(m.group(1))
        encontradas[indice] = interpretar_tarjeta(indice, valor)
    return tuple(encontradas[i] for i in sorted(encontradas))


def ipconfigs_de_config(config: Mapping[str, object]) -> frozenset[int]:
    """Índices ``N`` de los ``ipconfigN`` presentes en la config."""
    indices: set[int] = set()
    for clave in config:
        if not isinstance(clave, str):
            continue
        m = _RE_IPCONFIG.fullmatch(clave)
        if m is not None and int(m.group(1)) < MAX_TARJETAS:
            indices.add(int(m.group(1)))
    return frozenset(indices)


def bridges_finales(
    bridges: Sequence[str], tarjetas: Sequence[TarjetaPlantilla], red: RedClon | None
) -> tuple[str, ...]:
    """Bridges (o VNets) que tendrá el clon: los de la plantilla tras CAMBIAR/AÑADIR/QUITAR.

    Sin red personalizada son los de la plantilla. Con las tarjetas de la plantilla leídas se
    resuelve por índice (una tarjeta QUITAR no cuenta; CAMBIAR con bridge fijado usa el nuevo).
    Sin ellas (no leídas) se parte de ``bridges`` y se suman los pedidos. Sirve al reparto de
    clones, que exige los bridges finales en el nodo destino (QA-C-M2).
    """
    if red is None or not usa_red_clon(red):
        return tuple(bridges)
    finales: list[str] = []
    if tarjetas:
        for t in tarjetas:
            pedido = red.tarjeta(t.indice)
            if pedido is not None and pedido.accion == AccionTarjeta.QUITAR:
                continue
            if (
                pedido is not None
                and pedido.accion == AccionTarjeta.CAMBIAR
                and CampoRed.BRIDGE in pedido.fijados
            ):
                if pedido.bridge:
                    finales.append(pedido.bridge)
            elif t.bridge:
                finales.append(t.bridge)
    else:
        finales.extend(bridges)
        finales.extend(
            p.bridge
            for p in red.tarjetas
            if p.bridge
            and (
                p.accion == AccionTarjeta.CAMBIAR
                and CampoRed.BRIDGE in p.fijados
                or p.accion == AccionTarjeta.ANADIR
            )
        )
        return tuple(dict.fromkeys(finales))
    finales.extend(
        p.bridge
        for p in red.tarjetas
        if p.accion == AccionTarjeta.ANADIR
        and p.bridge
        and p.indice not in {t.indice for t in tarjetas}
    )
    return tuple(dict.fromkeys(finales))


def tarjetas_finales(actuales: Sequence[int], red: RedClon | None) -> tuple[int, ...]:
    """Índices de las tarjetas que tendrá el clon: las actuales, sin las QUITAR y con las AÑADIR.

    Sin red personalizada son las actuales. Sirve a B1 (``ipconfigN``) y a V-C17/V-C18.
    """
    finales = set(actuales)
    if red is not None and usa_red_clon(red):
        for t in red.tarjetas:
            if t.accion == AccionTarjeta.QUITAR:
                finales.discard(t.indice)
            elif t.accion == AccionTarjeta.ANADIR:
                finales.add(t.indice)
    return tuple(sorted(finales))


def indice_libre(ocupados: Collection[int]) -> int | None:
    """El índice libre más bajo de ``0..31``; ``None`` si están todos ocupados."""
    for i in range(MAX_TARJETAS):
        if i not in ocupados:
            return i
    return None
