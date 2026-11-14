"""Aplicar un perfil a una configuración (RF-P05, RF-P06). Puro: sin E/S de red (INV-M1).

El perfil copia SOLO hardware; ``vmid``, ``nombre``, ``nodo`` y ``etiquetas`` se conservan de la
configuración actual. Las pistas de storage y bridge se resuelven contra el inventario del
nodo efectivo (``actual.nodo``) y nunca se inventa un valor (CA-P06.7).
"""

from __future__ import annotations

from dataclasses import dataclass

from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    BallooningPerfil,
    ConfigPerfil,
    DiscoPerfil,
    PerfilMaquina,
    RedPerfil,
)
from proxlaunch.nucleo.validacion import CARACTERES_PROHIBIDOS_ID, TIPOS_BRIDGE
from proxlaunch.nucleo.valores_defecto import bridge_por_defecto, storage_por_defecto


@dataclass(frozen=True)
class AvisoPista:
    """Una pista que no sirvió. ``recurso``: ``storage``, ``storage_efi`` o ``bridge``.

    ``usado`` es el valor que se puso en su lugar (``None`` si no había ninguno apto).
    """

    recurso: str
    pedido: str
    usado: str | None
    nodo: str


@dataclass(frozen=True)
class ResultadoAplicacion:
    cfg: ConfiguracionVM
    avisos: tuple[AvisoPista, ...] = ()


@dataclass(frozen=True)
class ResumenPerfil:
    vcpus: int
    memoria_mib: int
    discos_gib: tuple[int, ...]
    redes: int


def _usable(valor: str) -> bool:
    return not any(c in valor for c in CARACTERES_PROHIBIDOS_ID)


def aplicar_config(
    config: ConfigPerfil, actual: ConfiguracionVM, inv: Inventario | None
) -> ResultadoAplicacion:
    """Hardware de ``config`` sobre ``actual``; pistas resueltas en ``actual.nodo``.

    Con ``inv=None`` las pistas quedan como valor (CSV sin conexión) y no hay avisos.
    """
    nodo = actual.nodo
    avisos: list[AvisoPista] = []
    vistos: set[tuple[str, str]] = set()

    def avisar(recurso: str, pedido: str, usado: str | None) -> None:
        if (recurso, pedido) not in vistos:
            vistos.add((recurso, pedido))
            avisos.append(AvisoPista(recurso, pedido, usado, nodo))

    if inv is not None:
        storages = inv.storages.get(nodo, ())
        aptos = {s.id for s in storages if s.activo and "images" in s.contenido and _usable(s.id)}
        st_defecto = storage_por_defecto(storages)
        bridges = tuple(b for b in inv.bridges.get(nodo, ()) if b.tipo in TIPOS_BRIDGE)
        nombres_bridge = {b.nombre for b in bridges if _usable(b.nombre)}
        br_defecto = bridge_por_defecto(bridges)

    def resolver_storage(pista: str | None, recurso: str) -> str | None:
        if inv is None:
            return pista
        if pista is None:
            return st_defecto
        if pista in aptos:
            return pista
        avisar(recurso, pista, st_defecto)
        return st_defecto

    discos: list[Disco] = []
    if config.con_disco:
        for d in config.discos:
            storage = resolver_storage(d.storage_preferido, "storage")
            discos.append(
                Disco(storage or "", d.tamano_gib, d.bus, d.formato, d.discard, d.ssd, d.iothread)
            )

    storage_efi: str | None = None
    if config.firmware == Firmware.OVMF and config.storage_efi_preferido is not None:
        pista = config.storage_efi_preferido
        if inv is None or pista in aptos:
            storage_efi = pista
        else:  # None = el del primer disco (CA-14.2)
            avisar("storage_efi", pista, discos[0].storage if discos else None)

    redes: list[InterfazRed] = []
    for r in config.redes:
        if inv is None:
            bridge: str | None = r.bridge_preferido
        elif r.bridge_preferido is None:
            bridge = br_defecto
        elif r.bridge_preferido in nombres_bridge:
            bridge = r.bridge_preferido
        else:
            avisar("bridge", r.bridge_preferido, br_defecto)
            bridge = br_defecto
        redes.append(InterfazRed(bridge or "", r.modelo, r.vlan))

    cfg = ConfiguracionVM(
        vmid=actual.vmid,
        nombre=actual.nombre,
        nodo=actual.nodo,
        firmware=config.firmware,
        storage_efi=storage_efi,
        sockets=config.sockets,
        cores=config.cores,
        tipo_cpu=config.tipo_cpu,
        memoria_mib=config.memoria_mib,
        ballooning=(
            None
            if config.ballooning is None
            else Ballooning(config.ballooning.activo, config.ballooning.minimo_mib)
        ),
        con_disco=config.con_disco,
        discos=discos,
        controlador_scsi=config.controlador_scsi,
        redes=redes,
        origen=config.origen,
        etiquetas=actual.etiquetas,
    )
    return ResultadoAplicacion(cfg, tuple(avisos))


def aplicar_perfil(
    perfil: PerfilMaquina, actual: ConfiguracionVM, inv: Inventario
) -> ResultadoAplicacion:
    """Aplica un perfil (RF-P05). Sin sesión ni cliente: no hay E/S de red."""
    return aplicar_config(perfil.config, actual, inv)


def config_desde_configuracion(cfg: ConfiguracionVM, *, con_pistas: bool) -> ConfigPerfil:
    """Perfil a partir del formulario (sin vmid, nombre, nodo ni etiquetas)."""

    def pista(valor: str | None) -> str | None:
        return valor if con_pistas and valor else None

    return ConfigPerfil(
        firmware=cfg.firmware,
        sockets=cfg.sockets,
        cores=cfg.cores,
        tipo_cpu=cfg.tipo_cpu,
        memoria_mib=cfg.memoria_mib,
        ballooning=(
            None
            if cfg.ballooning is None
            else BallooningPerfil(cfg.ballooning.activo, cfg.ballooning.minimo_mib)
        ),
        con_disco=cfg.con_disco,
        discos=tuple(
            DiscoPerfil(
                d.tamano_gib, d.bus, d.formato, d.discard, d.ssd, d.iothread, pista(d.storage)
            )
            for d in cfg.discos
        ),
        storage_efi_preferido=pista(cfg.storage_efi),
        controlador_scsi=cfg.controlador_scsi,
        redes=tuple(RedPerfil(r.modelo, r.vlan, pista(r.bridge)) for r in cfg.redes),
        origen=cfg.origen,
    )


def _huella(cfg: ConfiguracionVM) -> tuple[object, ...]:
    return (
        cfg.firmware,
        cfg.storage_efi,
        cfg.sockets,
        cfg.cores,
        cfg.tipo_cpu,
        cfg.memoria_mib,
        None if cfg.ballooning is None else (cfg.ballooning.activo, cfg.ballooning.minimo_mib),
        cfg.con_disco,
        tuple(
            (d.storage, d.tamano_gib, d.bus, d.formato, d.discard, d.ssd, d.iothread)
            for d in cfg.discos
        ),
        cfg.controlador_scsi,
        tuple((r.bridge, r.modelo, r.vlan) for r in cfg.redes),
        cfg.origen,
    )


def hardware_igual(a: ConfiguracionVM, b: ConfiguracionVM) -> bool:
    """Igualdad de hardware ignorando vmid, nombre, nodo y etiquetas (¿hubo cambios manuales?)."""
    return _huella(a) == _huella(b)


def resumen_perfil(config: ConfigPerfil) -> ResumenPerfil:
    """Cifras para el resumen en lenguaje llano del selector (RF-P11)."""
    return ResumenPerfil(
        vcpus=config.sockets * config.cores,
        memoria_mib=config.memoria_mib,
        discos_gib=tuple(d.tamano_gib for d in config.discos) if config.con_disco else (),
        redes=len(config.redes),
    )
