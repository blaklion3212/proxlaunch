"""Aplicar un perfil a una configuración (RF-P05, RF-P06). Puro: sin E/S de red (INV-M1).

El perfil copia SOLO hardware; ``vmid``, ``nombre``, ``nodo`` y ``etiquetas`` se conservan de la
configuración actual (fase A: también las opciones de notas, etiquetas, pool y protección; el
perfil solo fija «Arrancar con el servidor» y «Encender al terminar» vuelve a su valor por
defecto, CA-A1.4.1). Las pistas de storage y bridge se resuelven contra el inventario del
nodo efectivo (``actual.nodo``) y nunca se inventa un valor (CA-P06.7).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import (
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    DetalleOrigen,
    RefPlantilla,
    RefVolumen,
)
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
    OrigenSO,
)
from proxlaunch.nucleo.origen.nombres import partes_volid
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    BallooningPerfil,
    ConfigPerfil,
    DiscoPerfil,
    PerfilMaquina,
    PistaOrigen,
    RedPerfil,
)
from proxlaunch.nucleo.validacion import CARACTERES_PROHIBIDOS_ID, TIPOS_BRIDGE
from proxlaunch.nucleo.valores_defecto import bridge_por_defecto, storage_por_defecto


@dataclass(frozen=True)
class AvisoPista:
    """Una pista que no sirvió. ``recurso``: ``storage``, ``storage_efi``, ``bridge`` o ``fuente``.

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


def _ref_pista(
    inv: Inventario | None,
    nodo: str,
    nombre: str,
    storage_preferido: str | None,
    contenido: Contenido,
    avisar: Callable[[str, str, str | None], None],
) -> RefVolumen:
    """Resuelve el nombre de una pista contra el catálogo del nodo (RF-O26, CA-O26.2).

    Existe → ``RefVolumen`` con volid; catálogo no leído o ambiguo → solo el nombre; catálogo
    leído y no existe → solo el nombre y aviso ``fuente`` (nunca cambia a «Vacía» en silencio).
    """
    if not nombre:
        return RefVolumen()
    cat = None if inv is None else inv.catalogo
    if cat is None or not any(
        lst.nodo == nodo and lst.contenido == contenido for lst in cat.listados
    ):
        return RefVolumen(nombre=nombre)
    coincidentes = [v for v in cat.buscar_nombre(nombre, nodo, contenido) if v.admitido]
    if storage_preferido:
        preferidas = [v for v in coincidentes if v.storage == storage_preferido]
        coincidentes = preferidas or coincidentes
    if len(coincidentes) == 1:
        return RefVolumen(nombre=nombre, volid=coincidentes[0].volid)
    if not coincidentes:
        avisar("fuente", nombre, None)
    return RefVolumen(nombre=nombre)


def _detalle_desde_pista(
    config: ConfigPerfil,
    inv: Inventario | None,
    nodo: str,
    avisar: Callable[[str, str, str | None], None],
) -> DetalleOrigen | None:
    pista = config.pista_origen or PistaOrigen()
    if config.origen == OrigenSO.ISO:
        iso = _ref_pista(
            inv, nodo, pista.nombre_fuente, pista.storage_preferido, Contenido.ISO, avisar
        )
        drivers = (
            None
            if pista.drivers is None
            else _ref_pista(inv, nodo, pista.drivers, None, Contenido.ISO, avisar)
        )
        return DetalleIso(iso=iso, drivers=drivers, sin_drivers=pista.sin_drivers)
    if config.origen == OrigenSO.IMPORTAR_DISCO:
        imagen = _ref_pista(
            inv, nodo, pista.nombre_fuente, pista.storage_preferido, Contenido.IMPORT, avisar
        )
        return DetalleImportacion(imagen=imagen, ampliar_a_gib=pista.ampliar_a_gib)
    if config.origen == OrigenSO.CLONAR_PLANTILLA:
        ref = RefPlantilla(nombre=pista.nombre_fuente)
        cat = None if inv is None else inv.catalogo
        if pista.nombre_fuente and cat is not None and cat.plantillas is not None:
            halladas = cat.plantillas_por_nombre(pista.nombre_fuente)
            if not halladas:
                avisar("fuente", pista.nombre_fuente, None)
            elif len({p.vmid for p in halladas}) == 1:
                ref = RefPlantilla(nombre=pista.nombre_fuente, vmid=halladas[0].vmid)
        return DetalleClon(plantilla=ref, modo=pista.modo_clon, ajustes=pista.ajustes)
    return None


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
        redes.append(InterfazRed(bridge or "", r.modelo, r.vlan, r.mtu, r.limite_mb))

    detalle = _detalle_desde_pista(config, inv, nodo, avisar)
    if config.origen == OrigenSO.CLONAR_PLANTILLA:
        # Un clon hereda hardware de la plantilla: cómputo y discos del perfil no la pisan
        # (CA-O26.5); solo cuentan los ajustes guardados.
        clon = replace(
            actual,
            origen=config.origen,
            etiquetas=actual.etiquetas,
            tipo_so=None,
            tpm=False,
            agente_qemu=False,
            detalle_origen=detalle,
            encender=False,  # CA-A1.4.1: «Encender al terminar» vuelve a su valor por defecto
            arranque_auto=config.arranque_auto,
        )
        return ResultadoAplicacion(clon, tuple(avisos))
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
        tipo_so=config.tipo_so,
        tpm=config.tpm,
        agente_qemu=config.agente_qemu,
        detalle_origen=detalle,
        # Fase A: el perfil fija «Arrancar con el servidor»; «Encender al terminar» vuelve a su
        # valor por defecto (CA-A1.4.1) y el resto de opciones de fase A es del formulario.
        encender=False,
        arranque_auto=config.arranque_auto,
        arranque_orden=actual.arranque_orden,
        arranque_espera=actual.arranque_espera,
        notas_origen=actual.notas_origen,
        notas_usuario=actual.notas_usuario,
        notas=actual.notas,
        etiquetas_usuario=actual.etiquetas_usuario,
        pool=actual.pool,
        proteger=actual.proteger,
        # Fase B: cloud-init y espera de IP son del formulario, no del perfil (como en el clon).
        cloudinit=actual.cloudinit,
        esperar_ip=actual.esperar_ip,
        plazo_ip_s=actual.plazo_ip_s,
        # Fase C: la red del clon y el firewall tampoco son del perfil (RF-C6.2).
        red_clon=actual.red_clon,
        firewall=actual.firewall,
    )
    return ResultadoAplicacion(cfg, tuple(avisos))


def aplicar_perfil(
    perfil: PerfilMaquina, actual: ConfiguracionVM, inv: Inventario
) -> ResultadoAplicacion:
    """Aplica un perfil (RF-P05). Sin sesión ni cliente: no hay E/S de red."""
    return aplicar_config(perfil.config, actual, inv)


def _nombre_de(ref: RefVolumen) -> str:
    if ref.nombre:
        return ref.nombre
    partes = partes_volid(ref.volid) if ref.volid else None
    return partes[2] if partes else ""


def _storage_de(ref: RefVolumen) -> str | None:
    partes = partes_volid(ref.volid) if ref.volid else None
    return partes[0] if partes else None


def _pista_desde_detalle(cfg: ConfiguracionVM) -> PistaOrigen | None:
    """Origen sugerido a partir del formulario: solo nombres, nunca volids (RF-O26)."""
    det = cfg.detalle_origen
    if isinstance(det, DetalleIso):
        return PistaOrigen(
            nombre_fuente=_nombre_de(det.iso),
            storage_preferido=_storage_de(det.iso),
            drivers=None if det.drivers is None else _nombre_de(det.drivers) or None,
            sin_drivers=det.sin_drivers,
        )
    if isinstance(det, DetalleImportacion):
        return PistaOrigen(
            nombre_fuente=_nombre_de(det.imagen),
            storage_preferido=_storage_de(det.imagen),
            ampliar_a_gib=det.ampliar_a_gib,
        )
    if isinstance(det, DetalleClon):
        return PistaOrigen(
            nombre_fuente=det.plantilla.nombre, modo_clon=det.modo, ajustes=det.ajustes
        )
    return None


def config_desde_configuracion(cfg: ConfiguracionVM, *, con_pistas: bool) -> ConfigPerfil:
    """Perfil a partir del formulario (sin vmid, nombre, nodo ni etiquetas)."""

    def pista(valor: str | None) -> str | None:
        return valor if con_pistas and valor else None

    # Sin la casilla de pistas el origen se guarda como «disco vacío» explícito (CA-O26.4).
    origen = cfg.origen if con_pistas else OrigenSO.DISCO_VACIO
    pista_origen = _pista_desde_detalle(cfg) if con_pistas else None
    es_clon = origen == OrigenSO.CLONAR_PLANTILLA
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
        redes=tuple(
            RedPerfil(r.modelo, r.vlan, pista(r.bridge), r.mtu, r.limite_mb) for r in cfg.redes
        ),
        origen=origen,
        tipo_so=None if es_clon or origen == OrigenSO.DISCO_VACIO else cfg.tipo_so,
        tpm=False if es_clon or origen == OrigenSO.DISCO_VACIO else cfg.tpm,
        agente_qemu=False if es_clon or origen == OrigenSO.DISCO_VACIO else cfg.agente_qemu,
        pista_origen=pista_origen,
        arranque_auto=cfg.arranque_auto,
    )


def _detalle_estable(det: DetalleOrigen | None) -> DetalleOrigen | None:
    """Detalle sin los datos que fija el plan o la sesión (no son cambios del usuario)."""
    if isinstance(det, DetalleImportacion):
        return replace(det, tamano_virtual_bytes=None)
    if isinstance(det, DetalleClon):
        return replace(det, plantilla=replace(det.plantilla, nodo=None), modo_efectivo=None)
    return det


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
        tuple((r.bridge, r.modelo, r.vlan, r.mtu, r.limite_mb) for r in cfg.redes),
        cfg.arranque_auto,
        cfg.origen,
        cfg.tipo_so,
        cfg.tpm,
        cfg.agente_qemu,
        _detalle_estable(cfg.detalle_origen),
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
