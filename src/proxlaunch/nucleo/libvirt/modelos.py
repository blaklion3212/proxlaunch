"""Modelo intermedio de un dominio de libvirt e interpretación tolerante del XML (RF-D1.4/5).

Todo el texto del XML es no confiable: antes de entrar en un modelo se sanea (sin control,
sin formato invisible ni ``<>&``) y se recorta. Nunca se lee el valor de ``passwd`` ni se abre
ninguna ruta del XML (``archivo`` es solo para mostrar). ``interpretar_dominio`` no lanza con
XML raro: lo que no entiende queda en ``sin_equivalente`` o en ``desconocidos`` (CL-D12).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from proxlaunch.nucleo.archivos.texto import es_formato_invisible
from proxlaunch.nucleo.libvirt.validacion import RE_MAC

MAX_TEXTO: Final = 256
MAX_DISCOS: Final = 256  # lectura defensiva: más allá no se interpretan
MAX_TARJETAS: Final = 64
MAX_ENTRADAS_LISTA: Final = 512

_NS_LIBOSINFO: Final = "http://libosinfo.org/xmlns/libvirt/domain/1.0"
_MULTIPLOS_BYTES: Final[dict[str, int]] = {
    "b": 1,
    "bytes": 1,
    "KB": 1000,
    "k": 1024,
    "KiB": 1024,
    "MB": 1000**2,
    "M": 1024**2,
    "MiB": 1024**2,
    "GB": 1000**3,
    "G": 1024**3,
    "GiB": 1024**3,
    "TB": 1000**4,
    "T": 1024**4,
    "TiB": 1024**4,
}
# Elementos de <devices> sin equivalente (los que no están aquí son «desconocidos»).
_DISPOSITIVOS_CONOCIDOS: Final = frozenset(
    {
        "lease", "filesystem", "input", "sound", "hostdev", "graphics", "video", "smartcard",
        "redirdev", "redirfilter", "hub", "parallel", "serial", "console", "channel", "rng",
        "memballoon", "watchdog", "panic", "shmem", "memory", "iommu", "vsock", "crypto",
        "audio", "nvram", "pstore",
    }
)  # fmt: skip
# Elementos de <domain> que se leen o que se informan como «No se migra» (P-D7).
_DOMINIO_LEIDOS: Final = frozenset({"name", "memory", "currentMemory", "vcpu", "os", "cpu"})
_DOMINIO_NO_MIGRADOS: Final = frozenset(
    {
        "uuid", "title", "description", "clock", "features", "on_poweroff", "on_reboot", "on_crash",
        "on_lockfailure", "pm", "iothreads", "iothreadids", "cputune", "numatune", "memoryBacking",
        "maxMemory", "resource", "sysinfo", "seclabel", "perf", "blkiotune", "memtune", "keywrap",
        "launchSecurity", "idmap", "genid", "vmcoreinfo", "vcpus", "bootloader", "bootloader_args",
        "throttlegroups", "hypervisor_features", "metadata", "devices",
    }
)  # fmt: skip
_RE_ARCH_X86: Final = re.compile(r"x86_64|amd64", re.IGNORECASE)
_RE_ARCH_I386: Final = re.compile(r"i[3-6]86", re.IGNORECASE)
_RE_ARCH_ARM: Final = re.compile(r"aarch64|arm64", re.IGNORECASE)
_CANAL_AGENTE: Final = "org.qemu.guest_agent.0"
_RE_LOADER_UEFI: Final = re.compile(r"ovmf|edk2|aavmf|uefi|qemu_efi", re.IGNORECASE)


def texto_saneado(valor: object, maximo: int = MAX_TEXTO) -> str:
    """Texto del XML apto para mostrar: sin control, formato invisible ni marcado, recortado."""
    if not isinstance(valor, str):
        return ""
    limpio = "".join(
        c
        for c in valor
        if c not in "<>&" and not es_formato_invisible(c) and (c.isprintable() or c == " ")
    )
    return limpio.strip()[:maximo].strip()


@dataclass(frozen=True)
class DiscoLibvirt:
    indice: int  # posición del <disk> en el XML (0..)
    dispositivo: str  # disk | cdrom | floppy | lun
    tipo_fuente: str  # file | block | network | dir | volume | nvme
    bus: str  # virtio | scsi | sata | ide | usb | ""
    archivo: str  # SOLO para mostrar (saneado ≤ 256, basename); nunca se abre
    formato: str  # driver type (qcow2/raw/…)
    con_backing_store: bool
    arranque: int | None
    # Ampliaciones de I3 (con valor por defecto; ver «11.I3»)
    dev: str = ""  # target dev ("vda"), solo informativo
    discard: bool = False  # driver discard='unmap'
    iothread: bool = False  # driver con iothread
    cache: str = ""  # driver cache (se informa; el formulario no la tiene)
    solo_lectura: bool = False
    compartido: bool = False


@dataclass(frozen=True)
class TarjetaLibvirt:
    indice: int
    tipo: str  # bridge | network | direct | user | …
    origen: str  # bridge/network/dev (saneado)
    modelo: str
    mac: str | None  # validada con regex o None
    # Ampliaciones de I3
    vlan: int | None = None
    mtu: int | None = None
    limite_kibs: int | None = None  # bandwidth/outbound@average (KiB/s)
    enlace_abajo: bool = False
    con_filtro: bool = False  # filterref
    openvswitch: bool = False  # virtualport openvswitch
    origen_limpio: bool = True  # el saneado no cambió el nombre (solo así se propone un bridge)


@dataclass(frozen=True)
class DominioLibvirt:
    nombre: str
    tipo_dominio: str  # kvm | qemu | xen | lxc …
    arquitectura: str  # os/type@arch normalizado: x86_64 | aarch64 | otro | "" (no declarada)
    maquina: str
    memoria_mib: int | None
    vcpus: int | None
    sockets: int | None
    cores: int | None
    modo_cpu: str  # host-passthrough | host-model | custom | maximum | ""
    modelo_cpu: str
    uefi: bool
    con_nvram: bool
    tpm: bool
    discos: tuple[DiscoLibvirt, ...]
    tarjetas: tuple[TarjetaLibvirt, ...]
    pista_so: str  # libosinfo id (saneado)
    con_contrasenas: bool  # hubo atributo passwd (su valor NO se lee)
    sin_equivalente: tuple[
        str, ...
    ]  # hostdev, sound, watchdog, … (V-D41); una entrada por elemento
    # Ampliaciones de I3 (con valor por defecto; ver «11.I3»)
    tipo_os: str = "hvm"  # os/type (``exe`` = contenedor)
    arquitectura_original: str = ""  # arch tal como venía (saneada): i686, ppc64le…
    memoria_actual_mib: int | None = None  # currentMemory
    vcpus_actuales: int | None = None  # vcpu@current
    threads: int | None = None
    con_caracteristicas_cpu: bool = False  # feature/maxphysaddr/kvm: no se envían
    secure_boot_inscrito: bool = False
    con_hyperv: bool = False
    agente_qemu: bool = False
    modelo_scsi: str = ""  # controller type=scsi model (el primero)
    tpm_version: str = ""
    tpm_backend: str = ""
    con_spice: bool = False
    otros_no_migrados: tuple[str, ...] = ()  # uuid, title, clock… (P-D7)
    desconocidos: tuple[str, ...] = ()  # elementos que no conozco (CA-D1.5.11)


# --- Utilidades ------------------------------------------------------------------------------


def _nombre_local(etiqueta: object) -> str:
    texto = str(etiqueta)
    return texto.rsplit("}", 1)[-1]


def _attr(elem: ET.Element | None, nombre: str, maximo: int = 64) -> str:
    if elem is None:
        return ""
    return texto_saneado(elem.get(nombre, ""), maximo)


def _entero(texto: object, digitos: int = 12) -> int | None:
    if not isinstance(texto, str):
        return None
    t = texto.strip()
    if re.fullmatch(rf"\d{{1,{digitos}}}", t) is None:
        return None
    return int(t)


def _hijo(elem: ET.Element | None, nombre: str) -> ET.Element | None:
    return None if elem is None else elem.find(nombre)


def _cantidad_mib(elem: ET.Element | None) -> int | None:
    """⌈valor · unidad / 2²⁰⌉ (unidad por defecto KiB); ``None`` si no se entiende."""
    if elem is None:
        return None
    valor = _entero(elem.text or "", 20)
    multiplo = _MULTIPLOS_BYTES.get(elem.get("unit", "KiB"))
    if valor is None or multiplo is None:
        return None
    return -(-(valor * multiplo) // (1 << 20))


def _arquitectura(texto: str) -> str:
    if not texto:
        return ""
    if _RE_ARCH_X86.fullmatch(texto) or _RE_ARCH_I386.fullmatch(texto):
        return "x86_64"
    if _RE_ARCH_ARM.fullmatch(texto):
        return "aarch64"
    return "otro"


_RE_USUARIO_URL: Final = re.compile(r"(?<=//)[^/@?#]*@")


def _nombre_base(ruta: str) -> str:
    """Último componente de una ruta (con ``/`` o ``\\``), solo para mostrar.

    En una URL (disco de red) se corta en ``?``/``#`` y se quita ``usuario:clave@``: la consulta
    y las credenciales nunca se muestran ni se guardan.
    """
    if "://" in ruta:
        ruta = _RE_USUARIO_URL.sub("", ruta.split("?", 1)[0].split("#", 1)[0])
    return ruta.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


# --- Discos y tarjetas ------------------------------------------------------------------------


def _interpretar_disco(indice: int, d: ET.Element) -> DiscoLibvirt:
    fuente = d.find("source")
    destino = d.find("target")
    controlador = d.find("driver")
    origen_texto = ""
    if fuente is not None:
        for clave in ("file", "dev", "name", "volume", "dir"):
            origen_texto = fuente.get(clave, "")
            if origen_texto:
                break
    almacenamiento = d.find("backingStore")
    orden = d.find("boot")
    arranque = _entero(orden.get("order", ""), 6) if orden is not None else None
    return DiscoLibvirt(
        indice=indice,
        dispositivo=_attr(d, "device", 16) or "disk",
        tipo_fuente=_attr(d, "type", 16) or "file",
        bus=_attr(destino, "bus", 16).lower(),
        archivo=texto_saneado(_nombre_base(origen_texto), MAX_TEXTO),
        formato=_attr(controlador, "type", 16).lower(),
        con_backing_store=almacenamiento is not None and len(almacenamiento) > 0,
        arranque=arranque,
        dev=_attr(destino, "dev", 16),
        discard=_attr(controlador, "discard", 16) == "unmap",
        iothread=controlador is not None and controlador.get("iothread") is not None,
        cache=_attr(controlador, "cache", 16),
        solo_lectura=d.find("readonly") is not None,
        compartido=d.find("shareable") is not None,
    )


def _interpretar_tarjeta(indice: int, t: ET.Element) -> TarjetaLibvirt:
    fuente = t.find("source")
    origen = ""
    if fuente is not None:
        for clave in ("bridge", "network", "dev"):
            origen = fuente.get(clave, "")
            if origen:
                break
    mac_elem = t.find("mac")
    mac_texto = mac_elem.get("address", "").strip().lower() if mac_elem is not None else ""
    mac = mac_texto if RE_MAC.fullmatch(mac_texto) is not None else None
    etiqueta_vlan = t.find("vlan/tag")
    salida = t.find("bandwidth/outbound")
    vlan = _entero(etiqueta_vlan.get("id", ""), 5) if etiqueta_vlan is not None else None
    puerto = t.find("virtualport")
    return TarjetaLibvirt(
        indice=indice,
        tipo=_attr(t, "type", 32).lower(),
        origen=texto_saneado(origen, MAX_TEXTO),
        modelo=_attr(t.find("model"), "type", 32),
        mac=mac,
        vlan=vlan if vlan is not None and 1 <= vlan <= 4094 else None,
        mtu=_entero(_attr(t.find("mtu"), "size", 8), 8),
        limite_kibs=_entero(_attr(salida, "average", 12), 12),
        enlace_abajo=_attr(t.find("link"), "state", 8) == "down",
        con_filtro=t.find("filterref") is not None,
        openvswitch=_attr(puerto, "type", 16) == "openvswitch",
        origen_limpio=texto_saneado(origen, MAX_TEXTO) == origen,
    )


def _pista_so(raiz: ET.Element) -> str:
    """``id`` del ``<libosinfo:os>`` de ``<metadata>`` (cualquier posición), saneado."""
    meta = raiz.find("metadata")
    if meta is None:
        return ""
    for elem in meta.iter(f"{{{_NS_LIBOSINFO}}}os"):
        return texto_saneado(elem.get("id", ""), MAX_TEXTO)
    return ""


def _con_contrasenas(raiz: ET.Element) -> bool:
    """¿Algún ``<graphics>`` trae ``passwd``? Solo se mira que el atributo exista, no su valor."""
    return any("passwd" in g.attrib for g in raiz.iter("graphics"))


def _limitado(valores: Iterator[str]) -> tuple[str, ...]:
    salida: list[str] = []
    for v in valores:
        if len(salida) >= MAX_ENTRADAS_LISTA:
            break
        salida.append(v)
    return tuple(salida)


def interpretar_dominio(raiz: ET.Element) -> DominioLibvirt:
    """Interpreta un ``<domain>`` ya leído con ``leer_xml``; tolerante, no lanza por XML raro."""
    so = raiz.find("os")
    tipo_os = so.find("type") if so is not None else None
    arch_original = _attr(tipo_os, "arch", 32)
    cpu = raiz.find("cpu")
    topologia = _hijo(cpu, "topology")
    vcpu = raiz.find("vcpu")
    cargador = _hijo(so, "loader")
    nvram = _hijo(so, "nvram")
    cargador_ruta = (cargador.text or "") if cargador is not None else ""
    plantilla = nvram.get("template", "") if nvram is not None else ""
    tipo_cargador = _attr(cargador, "type", 16)
    firmware_efi = _attr(so, "firmware", 16) == "efi"
    uefi = (
        firmware_efi
        or tipo_cargador == "pflash"
        or nvram is not None  # un <nvram> suelto solo existe con UEFI (RF-D1.9)
        or (cargador is not None and _RE_LOADER_UEFI.search(cargador_ruta) is not None)
    )
    sin_estado = _attr(cargador, "stateless", 8) == "yes"
    pistas_claves = f"{cargador_ruta} {plantilla}".lower()
    claves_inscritas = (
        _attr(cargador, "secure", 8) == "yes"
        and any(
            f.get("name") == "enrolled-keys" and f.get("enabled") == "yes"
            for f in raiz.iter("feature")
        )
    ) or (".secboot." in pistas_claves or ".ms." in pistas_claves)

    discos: list[DiscoLibvirt] = []
    tarjetas: list[TarjetaLibvirt] = []
    sin_equivalente: list[str] = []
    desconocidos: list[str] = []
    tpm = False
    tpm_version = ""
    tpm_backend = ""
    agente = False
    modelo_scsi = ""
    con_spice = False
    dispositivos = raiz.find("devices")
    if dispositivos is not None:
        n_disco = 0
        n_tarjeta = 0
        for d in dispositivos:
            etiqueta = _nombre_local(d.tag)
            if etiqueta == "disk":
                if len(discos) < MAX_DISCOS:
                    discos.append(_interpretar_disco(n_disco, d))
                else:
                    sin_equivalente.append("disk")
                n_disco += 1
            elif etiqueta == "interface":
                if len(tarjetas) < MAX_TARJETAS:
                    tarjetas.append(_interpretar_tarjeta(n_tarjeta, d))
                else:
                    sin_equivalente.append("interface")
                n_tarjeta += 1
            elif etiqueta == "tpm":
                tpm = True
                backend = d.find("backend")
                tpm_version = tpm_version or _attr(backend, "version", 8)
                tpm_backend = tpm_backend or _attr(backend, "type", 32)
            elif etiqueta == "controller":
                if _attr(d, "type", 16) == "scsi" and not modelo_scsi:
                    modelo_scsi = _attr(d, "model", 32)
            elif etiqueta == "channel" and _attr(d.find("target"), "name", 64) == _CANAL_AGENTE:
                agente = True
            elif etiqueta == "emulator":
                pass  # ruta del programa de QEMU: se ignora
            elif etiqueta in _DISPOSITIVOS_CONOCIDOS:
                sin_equivalente.append(etiqueta)
                if etiqueta == "graphics" and _attr(d, "type", 16) == "spice":
                    con_spice = True
                if etiqueta == "video" and _attr(d.find("model"), "type", 16) == "qxl":
                    con_spice = True
            else:
                desconocidos.append(texto_saneado(etiqueta, 40) or "?")

    otros: list[str] = []
    for hijo in raiz:
        etiqueta = _nombre_local(hijo.tag)
        if etiqueta in _DOMINIO_LEIDOS:
            continue
        if etiqueta in _DOMINIO_NO_MIGRADOS:
            if etiqueta not in ("metadata", "devices"):
                otros.append(etiqueta)
        else:
            desconocidos.append(texto_saneado(etiqueta, 40) or "?")

    pista = _pista_so(raiz)
    elem_modelo = _hijo(cpu, "model")
    modelo_cpu = texto_saneado(elem_modelo.text or "", 64) if elem_modelo is not None else ""
    return DominioLibvirt(
        nombre=texto_saneado(raiz.findtext("name") or "", MAX_TEXTO),
        tipo_dominio=_attr(raiz, "type", 32).lower(),
        arquitectura=_arquitectura(arch_original),
        maquina=_attr(tipo_os, "machine", 64),
        memoria_mib=_cantidad_mib(raiz.find("memory")),
        vcpus=_entero(vcpu.text or "", 6) if vcpu is not None else None,
        sockets=_entero(_attr(topologia, "sockets", 6), 6),
        cores=_entero(_attr(topologia, "cores", 6), 6),
        modo_cpu=_attr(cpu, "mode", 32).lower(),
        modelo_cpu=modelo_cpu,
        uefi=uefi,
        con_nvram=nvram is not None or (uefi and not sin_estado),
        tpm=tpm,
        discos=tuple(discos),
        tarjetas=tuple(tarjetas),
        pista_so=pista,
        con_contrasenas=_con_contrasenas(raiz),
        sin_equivalente=_limitado(iter(sin_equivalente)),
        tipo_os=texto_saneado((tipo_os.text or "") if tipo_os is not None else "hvm", 16) or "hvm",
        arquitectura_original=arch_original,
        memoria_actual_mib=_cantidad_mib(raiz.find("currentMemory")),
        vcpus_actuales=_entero(_attr(vcpu, "current", 6), 6),
        threads=_entero(_attr(topologia, "threads", 6), 6),
        con_caracteristicas_cpu=(
            cpu is not None
            and (cpu.find("feature") is not None or cpu.find("maxphysaddr") is not None)
        )
        or any(True for _ in raiz.iter("kvm")),
        secure_boot_inscrito=claves_inscritas,
        con_hyperv=raiz.find("features/hyperv") is not None,
        agente_qemu=agente,
        modelo_scsi=modelo_scsi,
        tpm_version=tpm_version,
        tpm_backend=tpm_backend,
        con_spice=con_spice,
        otros_no_migrados=_limitado(iter(otros)),
        desconocidos=_limitado(iter(desconocidos)),
    )
