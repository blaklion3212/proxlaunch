"""Reescritura de las tarjetas de red del clon (C4) y ``firewall=1`` en ellas (C3). Puro.

La petición se calcula SIEMPRE sobre la config DEL CLON releída justo antes (DT-C6): el clon ya
tiene MAC nueva y se reenvía la MAC leída, así que nunca se envía un ``netN`` sin MAC salvo que
el usuario pida ``mac_nueva`` (o la tarjeta sea nueva). El cálculo es idempotente (DT-C9).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from proxlaunch.nucleo.constructor_peticion import formato_limite
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import usa_firewall
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, ModeloRed, OrigenSO
from proxlaunch.nucleo.red.modelos import (
    AccionTarjeta,
    CampoRed,
    PeticionRed,
    TarjetaClon,
    TarjetaFinal,
    TarjetaPlantilla,
    usa_red_clon,
)

_VIRTIO = ModeloRed.VIRTIO.value


def requiere_paso_red(cfg: ConfiguracionVM) -> bool:
    """``True`` si el clon necesita el paso de red: red personalizada o firewall activo."""
    return cfg.origen == OrigenSO.CLONAR_PLANTILLA and (
        usa_red_clon(cfg.red_clon) or usa_firewall(cfg.firewall)
    )


def _valor(t: TarjetaPlantilla, *, con_mac: bool) -> str:
    """Texto de ``netN`` en orden fijo: ``modelo[=MAC],bridge,tag,mtu,rate,firewall,otras``."""
    modelo = t.modelo or _VIRTIO
    valor = f"{modelo}={t.mac}" if con_mac and t.mac else modelo
    if t.bridge is not None:
        valor += f",bridge={t.bridge}"
    if t.vlan is not None:
        valor += f",tag={t.vlan}"
    if t.mtu is not None:
        valor += f",mtu={t.mtu}"
    if t.limite_mb is not None:
        valor += f",rate={formato_limite(t.limite_mb)}"
    if t.firewall:
        valor += ",firewall=1"
    for clave, v in t.otras:
        valor += f",{clave}={v}"
    return valor


def _aplicar_cambios(
    actual: TarjetaPlantilla, pedido: TarjetaClon, avisos: list[str]
) -> TarjetaPlantilla:
    """CAMBIAR: aplica solo los campos fijados; los demás se conservan (``None`` quita)."""
    f = pedido.fijados
    campos: dict[str, Any] = {}
    if CampoRed.BRIDGE in f:
        campos["bridge"] = pedido.bridge
    if CampoRed.MODELO in f and pedido.modelo is not None:
        campos["modelo"] = pedido.modelo
    if CampoRed.VLAN in f:
        campos["vlan"] = pedido.vlan
    if CampoRed.MTU in f:
        campos["mtu"] = pedido.mtu
    if CampoRed.LIMITE in f:
        campos["limite_mb"] = pedido.limite_mb
    nueva = dataclasses.replace(actual, **campos)
    return _sin_mtu_si_no_virtio(nueva, indice=actual.indice, avisos=avisos)


def _sin_mtu_si_no_virtio(
    t: TarjetaPlantilla, *, indice: int, avisos: list[str]
) -> TarjetaPlantilla:
    """``mtu`` solo lo admite VirtIO: con otro modelo se omite y se avisa (RF-C4.1)."""
    if t.mtu is not None and t.modelo != _VIRTIO:
        avisos.append(f"red_mtu_ignorada:net{indice}")
        return dataclasses.replace(t, mtu=None)
    return t


def _tarjeta_nueva(pedido: TarjetaClon, avisos: list[str]) -> TarjetaPlantilla:
    """AÑADIR: se usan todos los valores pedidos; sin MAC (la genera Proxmox)."""
    nueva = TarjetaPlantilla(
        indice=pedido.indice,
        legible=True,
        modelo=pedido.modelo or _VIRTIO,
        mac=None,
        bridge=pedido.bridge,
        vlan=pedido.vlan,
        mtu=pedido.mtu,
        limite_mb=pedido.limite_mb,
    )
    return _sin_mtu_si_no_virtio(nueva, indice=pedido.indice, avisos=avisos)


def _misma_red(a: TarjetaPlantilla, bridge: str | None, vlan: int | None) -> bool:
    return a.bridge == bridge and a.vlan == vlan


def construir_peticion_red(
    cfg: ConfiguracionVM,
    actuales: Sequence[TarjetaPlantilla],
    ipconfigs: frozenset[int],
    digest: str | None,
    macs_originales: Mapping[int, str] | None = None,
) -> PeticionRed | None:
    """Calcula el ``PUT config`` de red del clon; ``None`` si no hay nada que cambiar.

    ``actuales`` e ``ipconfigs`` salen de la config del clon releída. Con firewall activo todas
    las tarjetas legibles que queden llevan ``firewall=1``; las ilegibles no se tocan (V-C20).
    ``macs_originales`` son las MAC que el clon tenía al leerlo por primera vez, por índice: si la
    MAC actual de una tarjeta difiere de la original, «MAC nueva» ya se aplicó en un intento
    anterior y no se repite (sin un cambio de red que lo delate no hay otra forma, RF-C4.8).

    Raises:
        ErrorProxLaunch: ``RED_PLANTILLA_CAMBIADA`` si un AÑADIR encuentra su índice ocupado
            por otra red (no se pisa nada).
    """
    if cfg.origen != OrigenSO.CLONAR_PLANTILLA:
        return None
    red = cfg.red_clon if usa_red_clon(cfg.red_clon) else None
    con_firewall = usa_firewall(cfg.firewall)
    if red is None and not con_firewall:
        return None

    parametros: dict[str, str] = {}
    borrar: list[str] = []
    avisos: list[str] = []
    finales: list[TarjetaFinal] = []
    por_indice = {t.indice: t for t in actuales}

    def final(t: TarjetaPlantilla, accion: AccionTarjeta, *, mac_conservada: bool) -> TarjetaFinal:
        return TarjetaFinal(
            indice=t.indice,
            accion=accion,
            modelo=t.modelo,
            red=t.bridge,
            vlan=t.vlan,
            mac_conservada=mac_conservada,
            firewall=t.firewall,
        )

    for actual in sorted(actuales, key=lambda x: x.indice):
        i = actual.indice
        pedido = red.tarjeta(i) if red is not None else None
        accion = pedido.accion if pedido is not None else AccionTarjeta.CONSERVAR
        if not actual.legible:
            # Lo que no se entiende no se reescribe (V-C20); se avisa si se iba a tocar.
            if con_firewall or accion != AccionTarjeta.CONSERVAR:
                avisos.append(f"red_tarjeta_ilegible:net{i}")
            continue
        if accion == AccionTarjeta.QUITAR:
            borrar.append(f"net{i}")
            if i in ipconfigs:
                borrar.append(f"ipconfig{i}")
            finales.append(
                TarjetaFinal(i, AccionTarjeta.QUITAR, actual.modelo, None, None, False, False)
            )
            continue
        nueva = actual
        mac_nueva = False
        if accion == AccionTarjeta.CAMBIAR and pedido is not None:
            nueva = _aplicar_cambios(actual, pedido, avisos)
            # Reintento (RD-C5): si la red pedida ya está puesta no se regenera la MAC.
            original = (macs_originales or {}).get(i)
            ya_aplicada = (
                original is not None and actual.mac is not None and actual.mac != original
            ) or (
                CampoRed.BRIDGE in pedido.fijados and _misma_red(actual, nueva.bridge, nueva.vlan)
            )
            mac_nueva = pedido.mac_nueva and not ya_aplicada
            if mac_nueva:
                avisos.append(f"red_mac_nueva:net{i}")
        elif (
            accion == AccionTarjeta.ANADIR
            and pedido is not None
            and not _misma_red(actual, pedido.bridge, pedido.vlan)
        ):
            # Si ya estaba añadida con la misma red cuenta como hecha (DT-C9); si no, no se pisa.
            raise ErrorProxLaunch(CodigoError.RED_PLANTILLA_CAMBIADA, {"tarjeta": f"net{i}"})
        if con_firewall:
            nueva = dataclasses.replace(nueva, firewall=True)
        valor_nuevo = _valor(nueva, con_mac=not mac_nueva)
        if valor_nuevo != _valor(actual, con_mac=True):
            parametros[f"net{i}"] = valor_nuevo
        finales.append(final(nueva, accion, mac_conservada=not mac_nueva))

    # AÑADIR en índices libres (los ocupados se resolvieron arriba).
    if red is not None:
        for pedido in red.tarjetas:
            if pedido.accion != AccionTarjeta.ANADIR or pedido.indice in por_indice:
                continue
            nueva = _tarjeta_nueva(pedido, avisos)
            if con_firewall:
                nueva = dataclasses.replace(nueva, firewall=True)
            parametros[f"net{pedido.indice}"] = _valor(nueva, con_mac=False)
            finales.append(final(nueva, AccionTarjeta.ANADIR, mac_conservada=False))

    if borrar:
        parametros["delete"] = ",".join(borrar)
    if not parametros:
        return None
    if digest:
        parametros["digest"] = digest
    finales.sort(key=lambda f: f.indice)
    return PeticionRed(parametros=parametros, finales=tuple(finales), avisos=tuple(avisos))
