"""Redes utilizables de un nodo: bridges y VNets de SDN (C2). Puro, sin E/S.

Una VNet es, para Proxmox, un nombre de bridge (DT-C4): todas las comprobaciones de «la red
existe» usan ``redes_de_nodo``. Los nombres vienen del servidor y no son confiables.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Bridge, Inventario, RedVirtual
from proxlaunch.nucleo.validacion import TIPOS_BRIDGE


@dataclass(frozen=True)
class RedesNodo:
    """Resultado de leer las VNets de un nodo (``error`` si la lectura falló)."""

    vnets: tuple[RedVirtual, ...]
    error: ErrorProxLaunch | None = None


@dataclass(frozen=True)
class InterseccionRedes:
    """Redes comunes a varios nodos destino (CA-C2.3)."""

    bridges: tuple[Bridge, ...]
    vnets: tuple[RedVirtual, ...]
    ocultas: int  # redes presentes en algún nodo pero no en todos los leídos
    sin_leer: tuple[str, ...]  # nodos sin lectura de red o de SDN (CA-C2.3.4)


def _bridges_de(inv: Inventario, nodo: str) -> tuple[Bridge, ...]:
    return tuple(b for b in inv.bridges.get(nodo, ()) if b.tipo in TIPOS_BRIDGE)


def redes_de_nodo(inv: Inventario, nodo: str) -> frozenset[str]:
    """Nombres de bridges (``TIPOS_BRIDGE``) y de VNets utilizables en el nodo."""
    nombres = {b.nombre for b in _bridges_de(inv, nodo)}
    nombres.update(v.nombre for v in inv.redes_sdn.get(nodo, ()))
    return frozenset(nombres)


def vnet_de_nodo(inv: Inventario, nodo: str, nombre: str) -> RedVirtual | None:
    """La VNet ``nombre`` del nodo, o ``None`` si no es una VNet de ese nodo."""
    for v in inv.redes_sdn.get(nodo, ()):
        if v.nombre == nombre:
            return v
    return None


def mtu_de_red(inv: Inventario, nodo: str, nombre: str) -> int | None:
    """MTU conocida de un bridge del nodo; ``None`` si se desconoce (las VNets no la informan)."""
    for b in _bridges_de(inv, nodo):
        if b.nombre == nombre:
            return b.mtu
    return None


def interseccion_redes(inv: Inventario, nodos: Sequence[str]) -> InterseccionRedes:
    """Bridges y VNets presentes en TODOS los nodos con lectura (CA-C2.3.1).

    Un nodo sin lectura de red (``errores_por_nodo``) o de SDN (``errores_sdn`` o sin entrada
    en ``redes_sdn``) no entra en la intersección de esa clase y se informa en ``sin_leer``.
    """
    sin_leer: list[str] = []
    con_red: list[str] = []
    con_sdn: list[str] = []
    for n in nodos:
        red_ok = n not in inv.errores_por_nodo and n in inv.bridges
        sdn_ok = n not in inv.errores_sdn and n in inv.redes_sdn
        if not (red_ok and sdn_ok):
            sin_leer.append(n)
        if red_ok:
            con_red.append(n)
        if sdn_ok:
            con_sdn.append(n)

    bridges: list[Bridge] = []
    ocultas = 0
    if con_red:
        por_nodo = [{b.nombre: b for b in _bridges_de(inv, n)} for n in con_red]
        union = {nombre for d in por_nodo for nombre in d}
        for nombre in sorted(union):
            if all(nombre in d for d in por_nodo):
                # VLAN-aware solo si lo es en todos los nodos (lo prudente).
                todos = [d[nombre] for d in por_nodo]
                bridges.append(
                    dataclasses.replace(todos[0], vlan_aware=all(b.vlan_aware for b in todos))
                )
            else:
                ocultas += 1
    vnets: list[RedVirtual] = []
    if con_sdn:
        por_nodo_v = [{v.nombre: v for v in inv.redes_sdn[n]} for n in con_sdn]
        union_v = {nombre for d in por_nodo_v for nombre in d}
        for nombre in sorted(union_v):
            if all(nombre in d for d in por_nodo_v):
                todos_v = [d[nombre] for d in por_nodo_v]
                vnets.append(
                    dataclasses.replace(todos_v[0], vlan_aware=all(v.vlan_aware for v in todos_v))
                )
            else:
                ocultas += 1
    return InterseccionRedes(tuple(bridges), tuple(vnets), ocultas, tuple(sin_leer))


def filtrar_vnets(
    entradas: Sequence[RedVirtual], interfaces: Collection[str]
) -> tuple[RedVirtual, ...]:
    """Deja solo las VNets: las que declaran ``type=vnet`` y, sin ``type``, las que NO están en
    la lista normal de interfaces del nodo (supuesto [A]: esas serían bridges ya conocidos)."""
    vistas: set[str] = set()
    resultado: list[RedVirtual] = []
    for v in entradas:
        if v.nombre in vistas:
            continue
        if not v.tipo_declarado and v.nombre in interfaces:
            continue
        vistas.add(v.nombre)
        resultado.append(v)
    return tuple(resultado)
