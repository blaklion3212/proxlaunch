"""Reglas de validación V-01..V-21 (RF-13 a RF-19).

Todas las funciones son puras y devuelven TODOS los problemas encontrados. Los
problemas llevan códigos y parámetros, nunca textos para el usuario.
"""

import ipaddress
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.modelos.conexion import PerfilConexion
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    Disco,
    Firmware,
    FormatoDisco,
    ModeloRed,
    OrigenSO,
)

# --- Constantes de las reglas -------------------------------------------------------

VMID_MIN = 100
VMID_MAX = 999_999_999
SOCKETS_MIN, SOCKETS_MAX = 1, 4
CORES_MIN, CORES_MAX = 1, 128
MEMORIA_MIN_MIB = 16
DISCO_MIN_GIB = 1
DISCO_MAX_GIB = 65536  # tope de interfaz (supuesto, V-08)
VLAN_MIN, VLAN_MAX = 1, 4094
PUERTO_MIN, PUERTO_MAX = 1, 65535

# V-07: máximo de dispositivos por bus.
MAX_DISPOSITIVOS: dict[Bus, int] = {Bus.SCSI: 31, Bus.VIRTIO: 16, Bus.SATA: 6, Bus.IDE: 4}

# V-09 / P-06: tipos de storage donde se puede elegir qcow2 (por defecto qcow2).
TIPOS_STORAGE_QCOW2 = frozenset({"dir", "nfs", "cifs"})

# V-13: buses con discard permitido. ide queda fuera hasta verificarlo.
# V-13: la API admite discard en los cuatro buses (investigación F1, aclaración A-2).
BUSES_CON_DISCARD = frozenset({Bus.SCSI, Bus.SATA, Bus.VIRTIO, Bus.IDE})
# V-12: buses con ssd permitido (CT-4: no en virtio).
BUSES_CON_SSD = frozenset({Bus.SCSI, Bus.SATA, Bus.IDE})

TIPOS_BRIDGE = frozenset({"bridge", "OVSBridge"})  # V-16 / D-08

_RE_ETIQUETA_DNS = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_RE_TOKEN = re.compile(r"^[^@!=\s]+@[^@!=\s]+![A-Za-z0-9._-]+=\S+$")
_RE_TOTP = re.compile(r"^[0-9]{6}$")
_GIB = 1024**3


class Severidad(StrEnum):
    ERROR = "error"
    AVISO = "aviso"  # no bloquea (thin, P-01)


@dataclass(frozen=True)
class Problema:
    """Un problema de validación: ruta del campo, código de regla y parámetros."""

    campo: str  # "nombre", "discos[1].ssd", "redes[0].vlan"
    codigo: str  # "V-12" o con subcódigo "V-14.thin"
    severidad: Severidad
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OpcionesDisco:
    """Qué opciones se pueden activar para un disco (CA-16.4)."""

    discard: bool
    ssd: bool
    iothread: bool


# --- Utilidades ---------------------------------------------------------------------


def _es_entero(valor: Any) -> bool:
    """Entero real de Python (los booleanos no cuentan)."""
    return isinstance(valor, int) and not isinstance(valor, bool)


def nombre_dns_valido(texto: Any) -> bool:
    """Nombre DNS según RFC 1123 (V-01 y V-19)."""
    if not isinstance(texto, str) or not texto or len(texto) > 253:
        return False
    return all(_RE_ETIQUETA_DNS.fullmatch(e) for e in texto.split("."))


def formatos_permitidos(tipo_storage: str) -> tuple[FormatoDisco, ...]:
    """Formatos elegibles según el backend (V-09, P-06). Nunca ``subvol``."""
    if tipo_storage in TIPOS_STORAGE_QCOW2:
        return (FormatoDisco.RAW, FormatoDisco.QCOW2)
    return (FormatoDisco.RAW,)


def opciones_permitidas(disco: Disco, ctrl: ControladorScsi) -> OpcionesDisco:
    """Opciones que se pueden activar para el disco con ese bus y controlador (V-11..V-13)."""
    iothread = disco.bus == Bus.VIRTIO or (
        disco.bus == Bus.SCSI and ctrl == ControladorScsi.VIRTIO_SINGLE
    )
    return OpcionesDisco(
        discard=disco.bus in BUSES_CON_DISCARD,
        ssd=disco.bus in BUSES_CON_SSD,
        iothread=iothread,
    )


def _buscar_storage(inv: Inventario, nodo: str, id_storage: str) -> Storage | None:
    for s in inv.storages.get(nodo, ()):
        if s.id == id_storage:
            return s
    return None


# --- Validación de la MV ------------------------------------------------------------


def validar_vm(cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades) -> list[Problema]:
    """Valida la configuración completa y devuelve todos los problemas.

    V-03 (VMID libre) necesita la API y la comprueba el servicio de creación.
    ``caps`` se recibe por la firma de la arquitectura; el MVP 1 no tiene reglas
    dependientes de versión.
    """
    p: list[Problema] = []

    def err(campo: str, codigo: str, **params: str) -> None:
        p.append(Problema(campo, codigo, Severidad.ERROR, dict(params)))

    # V-01 nombre
    if not nombre_dns_valido(cfg.nombre):
        err("nombre", "V-01")
    # V-02 VMID
    if not _es_entero(cfg.vmid) or not VMID_MIN <= cfg.vmid <= VMID_MAX:
        err("vmid", "V-02")
    # V-04 nodo
    nodo = next((n for n in inv.topologia.nodos if n.nombre == cfg.nodo), None)
    if nodo is None or not nodo.en_linea:
        err("nodo", "V-04", nodo=str(cfg.nodo))
    # V-05 sockets / cores
    if not _es_entero(cfg.sockets) or not SOCKETS_MIN <= cfg.sockets <= SOCKETS_MAX:
        err("sockets", "V-05")
    if not _es_entero(cfg.cores) or not CORES_MIN <= cfg.cores <= CORES_MAX:
        err("cores", "V-05")
    # V-06 memoria / balloon
    memoria_ok = _es_entero(cfg.memoria_mib) and cfg.memoria_mib >= MEMORIA_MIN_MIB
    if not memoria_ok:
        err("memoria_mib", "V-06")
    if cfg.ballooning is not None and cfg.ballooning.activo:
        minimo = cfg.ballooning.minimo_mib
        if (
            not _es_entero(minimo)
            or minimo < MEMORIA_MIN_MIB
            or (memoria_ok and minimo > cfg.memoria_mib)
        ):
            err("ballooning.minimo_mib", "V-06")
    # V-20 origen
    if cfg.origen != OrigenSO.DISCO_VACIO:
        err("origen", "V-20")
    # V-10 controlador scsi
    if cfg.controlador_scsi not in tuple(ControladorScsi):
        err("controlador_scsi", "V-10")

    discos = cfg.discos if cfg.con_disco else []
    _validar_discos(cfg, inv, discos, p)
    _validar_efi(cfg, inv, discos, p)
    _validar_redes(cfg, inv, p)
    return p


def _validar_discos(
    cfg: ConfiguracionVM, inv: Inventario, discos: list[Disco], p: list[Problema]
) -> None:
    def err(campo: str, codigo: str, **params: str) -> None:
        p.append(Problema(campo, codigo, Severidad.ERROR, dict(params)))

    vistos: Counter[Bus] = Counter()
    for i, d in enumerate(discos):
        ruta = f"discos[{i}]"
        bus_valido = d.bus in tuple(Bus)
        # V-07 bus y máximo de dispositivos
        if not bus_valido:
            err(f"{ruta}.bus", "V-07")
        else:
            vistos[d.bus] += 1
            if vistos[d.bus] > MAX_DISPOSITIVOS[d.bus]:
                err(f"{ruta}.bus", "V-07", bus=str(d.bus), maximo=str(MAX_DISPOSITIVOS[d.bus]))
        # V-08 tamaño
        if not _es_entero(d.tamano_gib) or not DISCO_MIN_GIB <= d.tamano_gib <= DISCO_MAX_GIB:
            err(f"{ruta}.tamano_gib", "V-08")
        # V-17 storage y V-09 formato
        st = _buscar_storage(inv, cfg.nodo, d.storage)
        if st is None or not st.activo or "images" not in st.contenido:
            err(f"{ruta}.storage", "V-17", storage=str(d.storage), nodo=cfg.nodo)
        elif d.formato not in (FormatoDisco.AUTO, *formatos_permitidos(st.tipo)):
            err(f"{ruta}.formato", "V-09", storage=st.id, tipo=st.tipo, formato=str(d.formato))
        if not bus_valido:
            continue
        op = opciones_permitidas(d, cfg.controlador_scsi)
        # V-11 iothread, V-12 ssd, V-13 discard
        if d.iothread and not op.iothread:
            err(f"{ruta}.iothread", "V-11", bus=str(d.bus))
        if d.ssd and not op.ssd:
            err(f"{ruta}.ssd", "V-12", bus=str(d.bus))
        if d.discard and not op.discard:
            err(f"{ruta}.discard", "V-13", bus=str(d.bus))

    # V-14 espacio: suma por storage frente al libre (aviso en thin, P-01)
    pedido: dict[str, int] = {}
    primero: dict[str, int] = {}
    for i, d in enumerate(discos):
        if _es_entero(d.tamano_gib) and d.tamano_gib > 0:
            pedido[d.storage] = pedido.get(d.storage, 0) + d.tamano_gib
            primero.setdefault(d.storage, i)
    for id_st, total in pedido.items():
        st = _buscar_storage(inv, cfg.nodo, id_st)
        if st is None or total * _GIB <= st.libre_bytes:
            continue
        params = {"storage": id_st, "pedido_gib": str(total), "libre_gib": str(st.libre_gib)}
        campo = f"discos[{primero[id_st]}].tamano_gib"
        if st.es_thin:
            p.append(Problema(campo, "V-14.thin", Severidad.AVISO, params))
        else:
            p.append(Problema(campo, "V-14", Severidad.ERROR, params))


def _validar_efi(
    cfg: ConfiguracionVM, inv: Inventario, discos: list[Disco], p: list[Problema]
) -> None:
    """CA-14.4: con OVMF debe haber un storage válido para ``efidisk0`` (código V-17)."""
    if cfg.firmware != Firmware.OVMF:
        return
    id_efi = storage_efi_efectivo(cfg, inv, discos)
    st = None if id_efi is None else _buscar_storage(inv, cfg.nodo, id_efi)
    if st is None or not st.activo or "images" not in st.contenido:
        p.append(
            Problema(
                "storage_efi",
                "V-17",
                Severidad.ERROR,
                {"storage": id_efi or "", "nodo": cfg.nodo},
            )
        )


def storage_efi_efectivo(
    cfg: ConfiguracionVM, inv: Inventario, discos: list[Disco] | None = None
) -> str | None:
    """Storage del ``efidisk0``: el indicado, el del primer disco o el primero con images."""
    if cfg.storage_efi:
        return cfg.storage_efi
    lista = (cfg.discos if cfg.con_disco else []) if discos is None else discos
    if lista:
        return lista[0].storage
    for s in inv.storages.get(cfg.nodo, ()):
        if s.activo and "images" in s.contenido:
            return s.id
    return None


def _validar_redes(cfg: ConfiguracionVM, inv: Inventario, p: list[Problema]) -> None:
    bridges = {b.nombre for b in inv.bridges.get(cfg.nodo, ()) if b.tipo in TIPOS_BRIDGE}
    for i, r in enumerate(cfg.redes):
        ruta = f"redes[{i}]"
        # V-15 VLAN
        if r.vlan is not None and (not _es_entero(r.vlan) or not VLAN_MIN <= r.vlan <= VLAN_MAX):
            p.append(Problema(f"{ruta}.vlan", "V-15", Severidad.ERROR, {}))
        # V-16 bridge
        if r.bridge not in bridges or "," in r.bridge or "=" in r.bridge:
            p.append(
                Problema(
                    f"{ruta}.bridge",
                    "V-16",
                    Severidad.ERROR,
                    {"bridge": str(r.bridge), "nodo": cfg.nodo},
                )
            )
        if r.modelo not in tuple(ModeloRed):
            p.append(Problema(f"{ruta}.modelo", "V-16", Severidad.ERROR, {}))


# --- Conexión -----------------------------------------------------------------------


def normalizar_host(texto: str) -> tuple[str, int | None]:
    """Quita esquema, ruta y puerto de lo que escribe el usuario (CA-07.8).

    ``"https://10.0.0.5:8006/"`` -> ``("10.0.0.5", 8006)``. Admite IPv6 entre corchetes.
    """
    t = texto.strip()
    if "://" in t:
        t = t.split("://", 1)[1]
    t = re.split(r"[/?#]", t, maxsplit=1)[0]
    if t.startswith("["):
        m = re.fullmatch(r"\[([^\]]*)\](?::(\d+))?", t)
        if m:
            return m.group(1), int(m.group(2)) if m.group(2) else None
        return t, None
    if t.count(":") == 1:
        host, _, puerto = t.partition(":")
        if puerto.isdigit():
            return host, int(puerto)
    return t, None


def _host_valido(host: str) -> bool:
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return nombre_dns_valido(host)
    return True


def validar_perfil(p: PerfilConexion) -> list[Problema]:
    """Valida host(s) y puerto del perfil (V-19). Los hosts deben venir ya normalizados."""
    problemas: list[Problema] = []
    if not p.hosts:
        problemas.append(Problema("hosts", "V-19", Severidad.ERROR, {}))
    for i, h in enumerate(p.hosts):
        if not _host_valido(h):
            problemas.append(Problema(f"hosts[{i}]", "V-19", Severidad.ERROR, {}))
    if not _es_entero(p.puerto) or not PUERTO_MIN <= p.puerto <= PUERTO_MAX:
        problemas.append(Problema("puerto", "V-19", Severidad.ERROR, {}))
    return problemas


def validar_token(texto: str) -> list[Problema]:
    """Valida el formato ``usuario@realm!nombre=secreto`` (V-18)."""
    if isinstance(texto, str) and _RE_TOKEN.fullmatch(texto):
        return []
    return [Problema("token", "V-18", Severidad.ERROR, {})]


def validar_codigo_totp(texto: str) -> list[Problema]:
    """Código TOTP de exactamente 6 dígitos (V-21). La clave de recuperación no pasa por aquí."""
    if isinstance(texto, str) and _RE_TOTP.fullmatch(texto):
        return []
    return [Problema("codigo", "V-21", Severidad.ERROR, {})]
