"""Reglas de red de la fase C: VNets (V-C10, V-C11, V-C14) y red del clon (V-C15..V-C20, V-C50,
V-C51). Puro, sin E/S.

``validar_vm`` las llama; V-15 y V-16 del POST siguen en ``validacion._validar_redes`` (V-C12 es
esa V-16 ampliada a VNets, §0). Los ``params`` llevan solo nombres ya validados, nunca texto largo
del servidor. ``tarjeta`` es ``"netN"`` salvo en V-C16 (``"N"``, como V-B34).
"""

from __future__ import annotations

import math

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.cloudinit.modelos import ModoTarjeta
from proxlaunch.nucleo.modelos.catalogo import DetallePlantilla
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import (
    MAX_LIMITE_MB,
    MTU_IGUAL_BRIDGE,
    MTU_MAX,
    MTU_MIN,
    ConfiguracionVM,
    DetalleClon,
    OrigenSO,
)
from proxlaunch.nucleo.origen.permisos import estado_privilegio, ruta_sdn
from proxlaunch.nucleo.red.modelos import (
    MAX_TARJETAS,
    RE_NOMBRE_RED,
    AccionTarjeta,
    CampoRed,
    TarjetaClon,
    usa_red_clon,
)
from proxlaunch.nucleo.red.redes_nodo import mtu_de_red, redes_de_nodo, vnet_de_nodo
from proxlaunch.nucleo.red.reescritura import requiere_paso_red
from proxlaunch.nucleo.red.tarjetas import tarjetas_finales
from proxlaunch.nucleo.validacion import (
    TIPOS_BRIDGE,
    VLAN_MAX,
    VLAN_MIN,
    Problema,
    Severidad,
)

_MODELO_VIRTIO = "virtio"
ZONA_LOCAL = "localnetwork"


def _error(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.ERROR, dict(params))


def _aviso(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.AVISO, dict(params))


def _es_entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _version(caps: Capacidades, funcion: Funcion) -> str:
    minima = caps.requisito(funcion)
    return f"{minima[0]}.{minima[1]}"


def _es_bridge(inv: Inventario, nodo: str, nombre: str) -> bool:
    return any(b.nombre == nombre and b.tipo in TIPOS_BRIDGE for b in inv.bridges.get(nodo, ()))


def _vnet_en_otro_nodo(inv: Inventario, nodo: str, nombre: str) -> str | None:
    """Un nodo (distinto de ``nodo``) donde ``nombre`` es una VNet, si lo hay."""
    for otro in sorted(inv.redes_sdn):
        if otro != nodo and vnet_de_nodo(inv, otro, nombre) is not None:
            return otro
    return None


def vnet_solo_en_otro_nodo(inv: Inventario, nodo: str, nombre: str) -> bool:
    """``True`` si ``nombre`` no existe en ``nodo`` pero sí como VNet en otro (V-C11)."""
    return (
        nombre not in redes_de_nodo(inv, nodo) and _vnet_en_otro_nodo(inv, nodo, nombre) is not None
    )


def _problemas_de_red(
    inv: Inventario,
    nodo: str,
    bridge: str | None,
    vlan: int | None,
    mtu: int | None,
    campo: str,
    tarjeta: str,
    p: list[Problema],
) -> None:
    """V-C10, V-C11 y V-C14 de una tarjeta con la red efectiva ``bridge`` en ``nodo``."""
    if bridge is None:
        return
    if vnet_solo_en_otro_nodo(inv, nodo, bridge):
        p.append(_error(f"{campo}.bridge", "V-C11", vnet=bridge, nodo=nodo, tarjeta=tarjeta))
        return
    vnet = None if _es_bridge(inv, nodo, bridge) else vnet_de_nodo(inv, nodo, bridge)
    if vnet is not None and vlan is not None and not vnet.vlan_aware:
        p.append(_error(f"{campo}.vlan", "V-C10", vnet=bridge, tarjeta=tarjeta))
    if mtu is not None and mtu != MTU_IGUAL_BRIDGE:
        conocida = mtu_de_red(inv, nodo, bridge)
        if conocida is not None and mtu > conocida:
            p.append(
                _aviso(
                    f"{campo}.mtu",
                    "V-C14",
                    mtu=str(mtu),
                    mtu_red=str(conocida),
                    red=bridge,
                    tarjeta=tarjeta,
                )
            )


def validar_redes_c(cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades) -> list[Problema]:
    """Tarjetas del POST: V-C10, V-C11 y V-C14 (V-15 y V-16 siguen en ``_validar_redes``)."""
    p: list[Problema] = []
    usa_vnet = False
    for i, r in enumerate(cfg.redes):
        if not isinstance(r.bridge, str):
            continue
        if vnet_de_nodo(inv, cfg.nodo, r.bridge) is not None and not _es_bridge(
            inv, cfg.nodo, r.bridge
        ):
            usa_vnet = True
        vlan = r.vlan if _es_entero(r.vlan) else None
        mtu = r.mtu if _es_entero(r.mtu) and r.modelo.value == _MODELO_VIRTIO else None
        _problemas_de_red(inv, cfg.nodo, r.bridge, vlan, mtu, f"redes[{i}]", f"net{i}", p)
    if usa_vnet and not caps.tiene(Funcion.VNETS_SDN):
        p.append(_error("redes", "V-C50", version=_version(caps, Funcion.VNETS_SDN)))
    return p


def _detalle_de_plantilla(
    cfg: ConfiguracionVM, inv: Inventario
) -> tuple[str, DetallePlantilla | None]:
    """Nombre y detalle de la plantilla del clon según el catálogo (``("", None)`` si no)."""
    detalle = cfg.detalle_origen
    if inv.catalogo is None or not isinstance(detalle, DetalleClon):
        return "", None
    ref = detalle.plantilla
    for pl in inv.catalogo.plantillas or ():
        if (ref.vmid is not None and pl.vmid == ref.vmid) or (
            ref.vmid is None and pl.nombre == ref.nombre
        ):
            return pl.nombre, pl.detalle
    return ref.nombre, None


def detalle_de_plantilla(cfg: ConfiguracionVM, inv: Inventario) -> DetallePlantilla | None:
    """Detalle de la plantilla del clon en el catálogo; ``None`` si no se conoce."""
    return _detalle_de_plantilla(cfg, inv)[1]


def _valor_pedido(t: TarjetaClon, campo: CampoRed) -> object:
    return {
        CampoRed.BRIDGE: t.bridge,
        CampoRed.MODELO: t.modelo,
        CampoRed.VLAN: t.vlan,
        CampoRed.MTU: t.mtu,
        CampoRed.LIMITE: t.limite_mb,
    }[campo]


def _aplica(t: TarjetaClon, campo: CampoRed) -> bool:
    """¿La petición fija ``campo``? (CAMBIAR: solo los fijados; AÑADIR: todos los presentes)."""
    if t.accion == AccionTarjeta.CAMBIAR:
        return campo in t.fijados
    return t.accion == AccionTarjeta.ANADIR and _valor_pedido(t, campo) is not None


def _problemas_de_valores(t: TarjetaClon, campo: str, tarjeta: str, p: list[Problema]) -> None:
    """V-C15 (VLAN) y reglas de MTU/límite de la fase A para una tarjeta pedida."""
    vlan, mtu, lim = t.vlan, t.mtu, t.limite_mb
    if (
        _aplica(t, CampoRed.VLAN)
        and vlan is not None
        and (not _es_entero(vlan) or not VLAN_MIN <= vlan <= VLAN_MAX)
    ):
        p.append(_error(f"{campo}.vlan", "V-C15", tarjeta=tarjeta))
    if (
        _aplica(t, CampoRed.MTU)
        and mtu is not None
        and (not _es_entero(mtu) or not (mtu == MTU_IGUAL_BRIDGE or MTU_MIN <= mtu <= MTU_MAX))
    ):
        p.append(_error(f"{campo}.mtu", "V-A04", valor=str(mtu), tarjeta=tarjeta))
    if (
        _aplica(t, CampoRed.LIMITE)
        and lim is not None
        and (
            not isinstance(lim, int | float)
            or not math.isfinite(lim)
            or not 0 < lim <= MAX_LIMITE_MB
        )
    ):
        p.append(_error(f"{campo}.limite_mb", "V-A06", valor=str(lim), tarjeta=tarjeta))


def validar_red_clon(
    cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades, detalle: DetallePlantilla | None
) -> list[Problema]:
    """V-C10, V-C11, V-16, V-C14..V-C20, V-C50 y V-C51 de la red del clon.

    ``detalle`` es la plantilla leída (``None`` = desconocida: se omiten las reglas que la
    necesitan). V-C19 se evalúa con red personalizada o con firewall activo (hay ``PUT`` de red).
    """
    p: list[Problema] = []
    red = cfg.red_clon
    if not usa_red_clon(red):
        if requiere_paso_red(cfg):
            _validar_permiso_plantilla(cfg, inv, detalle, p)
        return p
    assert red is not None
    if cfg.origen != OrigenSO.CLONAR_PLANTILLA:
        p.append(_error("red_clon", "V-C51"))
        return p
    if not caps.tiene(Funcion.REESCRIBIR_RED_CLON):
        p.append(_error("red_clon", "V-C50", version=_version(caps, Funcion.REESCRIBIR_RED_CLON)))

    actuales = {t.indice: t for t in detalle.tarjetas} if detalle is not None else {}
    nodo_leido = cfg.nodo in inv.bridges and cfg.nodo not in inv.errores_por_nodo
    ya_ci = {
        t.indice
        for t in (cfg.cloudinit.tarjetas if cfg.cloudinit is not None else ())
        if t.modo != ModoTarjeta.SIN_CONFIGURAR
    }
    for i, t in enumerate(red.tarjetas):
        campo = f"red_clon.tarjetas[{i}]"
        tarjeta = f"net{t.indice}"
        if not _es_entero(t.indice) or not 0 <= t.indice < MAX_TARJETAS:
            p.append(_error(f"{campo}.indice", "V-C17", maximo=str(MAX_TARJETAS)))
            continue
        if t.accion == AccionTarjeta.QUITAR:
            if t.indice in ya_ci:
                p.append(_error(campo, "V-C16", tarjeta=str(t.indice)))
            continue
        if t.accion == AccionTarjeta.CONSERVAR:
            continue
        _problemas_de_valores(t, campo, tarjeta, p)
        previa = actuales.get(t.indice)
        # Red efectiva: la pedida o, si no se cambia, la que ya tiene la tarjeta.
        if _aplica(t, CampoRed.BRIDGE):
            bridge = t.bridge
            if bridge is not None and RE_NOMBRE_RED.fullmatch(bridge) is None:
                p.append(_error(f"{campo}.bridge", "V-16", bridge=str(bridge), nodo=cfg.nodo))
                continue
        else:
            bridge = previa.bridge if previa is not None and previa.legible else None
        vlan = t.vlan if _aplica(t, CampoRed.VLAN) else (previa.vlan if previa else None)
        mtu = t.mtu if _aplica(t, CampoRed.MTU) else (previa.mtu if previa else None)
        modelo = (
            t.modelo
            if _aplica(t, CampoRed.MODELO) and t.modelo
            else (previa.modelo if previa is not None else None)
        )
        if t.accion == AccionTarjeta.ANADIR:
            modelo = t.modelo or _MODELO_VIRTIO
        if (
            _aplica(t, CampoRed.BRIDGE)
            and bridge is not None
            and nodo_leido
            and bridge not in redes_de_nodo(inv, cfg.nodo)
            and not vnet_solo_en_otro_nodo(inv, cfg.nodo, bridge)
        ):
            p.append(_error(f"{campo}.bridge", "V-16", bridge=bridge, nodo=cfg.nodo))
        elif any(_aplica(t, c) for c in (CampoRed.BRIDGE, CampoRed.VLAN, CampoRed.MTU)):
            mtu_comprobable = mtu if modelo in (None, _MODELO_VIRTIO) else None
            _problemas_de_red(
                inv,
                cfg.nodo,
                bridge,
                vlan if _es_entero(vlan) else None,
                mtu_comprobable if _es_entero(mtu_comprobable) else None,
                campo,
                tarjeta,
                p,
            )
        if (
            mtu is not None
            and modelo is not None
            and modelo != _MODELO_VIRTIO
            and _aplica(t, CampoRed.MTU)
        ):
            # Solo VirtIO admite MTU: se omite al reescribir y se avisa (CA-C4.6.3).
            p.append(_aviso(f"{campo}.mtu", "V-A05", modelo=modelo, tarjeta=tarjeta))

    if detalle is not None:
        ocupadas = [i for i in actuales if i in tarjetas_finales(list(actuales), red)]
        anadidas = [t for t in red.tarjetas if t.accion == AccionTarjeta.ANADIR]
        if len(anadidas) > MAX_TARJETAS - len(ocupadas):
            p.append(_error("red_clon", "V-C17", maximo=str(MAX_TARJETAS)))
        if any(t.accion == AccionTarjeta.QUITAR for t in red.tarjetas) and not tarjetas_finales(
            list(actuales), red
        ):
            p.append(_aviso("red_clon", "V-C18"))
        for tp in detalle.tarjetas:
            if not tp.legible:
                p.append(_aviso("red_clon", "V-C20", tarjeta=f"net{tp.indice}"))
    _validar_permiso_plantilla(cfg, inv, detalle, p)
    return p


def _validar_permiso_plantilla(
    cfg: ConfiguracionVM, inv: Inventario, detalle: DetallePlantilla | None, p: list[Problema]
) -> None:
    """V-C19: bridges locales de la plantilla sin ``SDN.Use`` conocido (con ``plantilla`` en
    ``params`` para agrupar por plantilla)."""
    if detalle is None or inv.catalogo is None:
        return
    permisos = inv.catalogo.permisos
    nombre, _ = _detalle_de_plantilla(cfg, inv)
    vnets = {v.nombre for vs in inv.redes_sdn.values() for v in vs}
    for bridge in dict.fromkeys(detalle.bridges):
        if bridge in vnets:
            continue  # la zona de una VNet no se conoce de antemano (§0)
        if estado_privilegio(permisos, "SDN.Use", ruta_sdn(ZONA_LOCAL, bridge)) is False:
            p.append(_aviso("red_clon", "V-C19", red=bridge, plantilla=nombre))
