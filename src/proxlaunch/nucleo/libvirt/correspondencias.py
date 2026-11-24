"""Correspondencias libvirt → formulario de ProxLaunch (RF-D1.5, DT-D13, tabla de INV-D §2.3).

``proponer`` convierte un ``DominioLibvirt`` en una ``PropuestaLibvirt``: la configuración que
rellena el formulario (origen «Importar disco») y una fila de vista previa por cada concepto,
con su estado en palabras y, si procede, el problema V-D asociado. Es puro: no abre archivos,
no consulta nada y nada de lo que lee del XML llega a una petición sin pasar por un valor
validado (los nombres de bridge solo se proponen si existen tal cual en el nodo).
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    arquitectura_de,
    arquitectura_efectiva,
)
from proxlaunch.nucleo.libvirt.modelos import (
    DiscoLibvirt,
    DominioLibvirt,
    TarjetaLibvirt,
    texto_saneado,
)
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.cpu import (
    TIPO_CPU_HOST,
    TIPOS_CPU_ARM,
    TIPOS_CPU_X86,
    tipo_cpu_por_defecto,
)
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, ImagenDisco, RefVolumen, TipoSO
from proxlaunch.nucleo.modelos.vm import (
    MTU_MAX,
    MTU_MIN,
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.red.redes_nodo import redes_de_nodo
from proxlaunch.nucleo.validacion import (
    BUSES_CON_SSD,
    CORES_MAX,
    CORES_MIN,
    MAX_DISPOSITIVOS,
    MEMORIA_MIN_MIB,
    SOCKETS_MAX,
    SOCKETS_MIN,
    Problema,
    Severidad,
)
from proxlaunch.nucleo.valores_defecto import TAMANO_DISCO_GIB

MEMORIA_MAX_MIB: Final = 4 * 1024 * 1024  # 4 TiB, el tope de Proxmox para una máquina
MAX_NOMBRE_DNS: Final = 63
NOMBRE_SIN_NOMBRE: Final = "migrada"
_MAX_LIMITE_MB: Final = 10**9


class EstadoFila(StrEnum):
    MIGRADO = "migrado"
    APROXIMADO = "aproximado"
    NO_SE_MIGRA = "no_se_migra"
    BLOQUEA = "bloquea"


@dataclass(frozen=True)
class FilaVistaPrevia:
    campo: str  # clave estable ("memoria", "disco[1]", "red[0].modelo"…)
    origen: str  # valor del XML saneado
    destino: str  # valor propuesto
    estado: EstadoFila
    problema: Problema | None = None  # V-D2x/3x/4x con params


@dataclass(frozen=True)
class PropuestaLibvirt:
    cfg: ConfiguracionVM
    filas: tuple[FilaVistaPrevia, ...]
    discos_no_migrables: tuple[int, ...]  # ``DiscoLibvirt.indice`` de los discos que no se traen

    def bloquea(self) -> bool:
        """¿Hay alguna fila «Bloquea»? (entonces «Rellenar el formulario» no se permite)."""
        return any(f.estado == EstadoFila.BLOQUEA for f in self.filas)


# Prefijos libosinfo (sin esquema, en minúsculas) → tipo de SO de la app. Se compara por
# segmentos: ``microsoft.com/win/10`` no casa con ``microsoft.com/win/1``. Windows anterior a 10
# y Solaris dan ``OTRO``; la lista de la app solo tiene Windows 10/11 (P-D14).
TABLA_SO: Final[Mapping[str, TipoSO]] = {
    "microsoft.com/win/11": TipoSO.WINDOWS_11,
    "microsoft.com/win/2k22": TipoSO.WINDOWS_SERVER_2022_2025,
    "microsoft.com/win/2k25": TipoSO.WINDOWS_SERVER_2022_2025,
    "microsoft.com/win/10": TipoSO.WINDOWS_10,
    "microsoft.com/win/2k16": TipoSO.WINDOWS_SERVER_2016_2019,
    "microsoft.com/win/2k19": TipoSO.WINDOWS_SERVER_2016_2019,
    **dict.fromkeys(
        (
            "microsoft.com/win/8.1", "microsoft.com/win/8", "microsoft.com/win/7",
            "microsoft.com/win/vista", "microsoft.com/win/xp", "microsoft.com/win/2k12r2",
            "microsoft.com/win/2k12", "microsoft.com/win/2k8r2", "microsoft.com/win/2k8",
            "microsoft.com/win/2k3r2", "microsoft.com/win/2k3", "microsoft.com/win/2k",
            "microsoft.com/win/me", "microsoft.com/win/98", "microsoft.com/win/95",
            "oracle.com/solaris", "openindiana.org/openindiana",
        ),
        TipoSO.OTRO,
    ),
    **dict.fromkeys(
        (
            "ubuntu.com/ubuntu", "debian.org/debian", "redhat.com/rhel", "fedoraproject.org/fedora",
            "centos.org/centos", "almalinux.org/almalinux", "rockylinux.org/rocky",
            "opensuse.org/opensuse", "suse.com/sles", "suse.com/sled", "archlinux.org/archlinux",
            "alpinelinux.org/alpinelinux", "linuxmint.com/linuxmint", "oracle.com/ol",
            "kernel.org/linux", "gentoo.org/gentoo", "freedesktop.org/linux",
        ),
        TipoSO.LINUX,
    ),
}  # fmt: skip

_TIPOS_WINDOWS: Final = frozenset(
    {
        TipoSO.WINDOWS_11,
        TipoSO.WINDOWS_SERVER_2022_2025,
        TipoSO.WINDOWS_10,
        TipoSO.WINDOWS_SERVER_2016_2019,
    }
)
_MODELOS_VIRTIO: Final = frozenset({"", "virtio", "virtio-transitional", "virtio-non-transitional"})
_MODELOS_E1000: Final = frozenset({"e1000", "e1000e", "82540em", "82545em"})
_MODELOS_SCSI_VIRTIO: Final = frozenset(
    {"", "auto", "virtio-scsi", "virtio-transitional", "virtio-non-transitional"}
)
_FUENTES_NO_MIGRABLES: Final = frozenset({"network", "dir", "nvme", "vhostuser", "vhostvdpa"})
_BUS_POR_NOMBRE: Final[dict[str, Bus]] = {
    "virtio": Bus.VIRTIO,
    "scsi": Bus.SCSI,
    "sata": Bus.SATA,
    "ide": Bus.IDE,
}
_BUS_POR_PREFIJO: Final[dict[str, Bus]] = {"vd": Bus.VIRTIO, "sd": Bus.SCSI, "hd": Bus.IDE}


def nombre_dns_de(nombre: str) -> str:
    """Limpia ``nombre`` a un nombre DNS válido de Proxmox (como el importador OVF).

    Espacios → ``-``, solo ``[A-Za-z0-9.-]``, etiquetas sin ``-`` en los extremos, ≤ 63
    caracteres; si no queda nada, ``migrada``.
    """
    texto = re.sub(r"\s+", "-", str(nombre))
    texto = re.sub(r"[^A-Za-z0-9.\-]", "", texto)
    etiquetas = [e.strip("-")[:MAX_NOMBRE_DNS] for e in texto.split(".")]
    resultado = ".".join(e for e in etiquetas if e)[:MAX_NOMBRE_DNS].strip(".-")
    return resultado or NOMBRE_SIN_NOMBRE


def _tipo_so_por_pista(pista: str) -> tuple[TipoSO | None, bool]:
    """``(tipo, es_windows)`` por prefijo de ``TABLA_SO``; ``tipo`` ``None`` si no se conoce."""
    norm = re.sub(r"^[a-z][a-z0-9+.-]*://", "", pista.strip().lower()).rstrip("/")
    mejor: str | None = None
    for prefijo in TABLA_SO:
        if (norm == prefijo or norm.startswith(prefijo + "/")) and (
            mejor is None or len(prefijo) > len(mejor)
        ):
            mejor = prefijo
    if mejor is not None:
        return TABLA_SO[mejor], mejor.startswith("microsoft.com/")
    return None, norm.startswith("microsoft.com/")


class _Constructor:
    """Acumula filas y problemas de una propuesta (estado local de ``proponer``)."""

    def __init__(self) -> None:
        self.filas: list[FilaVistaPrevia] = []

    def fila(
        self,
        campo: str,
        origen: object,
        destino: object,
        estado: EstadoFila,
        problema: Problema | None = None,
    ) -> None:
        self.filas.append(
            FilaVistaPrevia(
                campo,
                texto_saneado(str(origen), 256),
                texto_saneado(str(destino), 256),
                estado,
                problema,
            )
        )


def _aviso(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.AVISO, _limpios(params))


def _error(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.ERROR, _limpios(params))


def _limpios(params: dict[str, str]) -> dict[str, str]:
    return {k: texto_saneado(v, 256) for k, v in params.items()}


def _bus_destino(d: DiscoLibvirt, es_arm: bool) -> tuple[Bus, str | None]:
    """Bus del formulario y motivo del cambio: ``arm`` (V-D08), ``sin_equivalente`` (V-D36)."""
    bus = _BUS_POR_NOMBRE.get(d.bus)
    if bus is None and not d.bus:
        bus = _BUS_POR_PREFIJO.get(d.dev[:2])
    if bus is None:
        return Bus.SCSI, "sin_equivalente"
    if es_arm and bus in (Bus.SATA, Bus.IDE):
        return Bus.SCSI, "arm"
    return bus, None


def _cpu(
    d: DominioLibvirt, es_arm: bool, inv: Inventario | None, nodo: str | None
) -> tuple[str, EstadoFila, Problema | None]:
    """Tipo de CPU propuesto, estado de la fila y su aviso (V-D37)."""
    por_defecto = tipo_cpu_por_defecto("aarch64" if es_arm else "x86_64")
    if not d.modo_cpu:
        return por_defecto, EstadoFila.APROXIMADO, None
    if d.modo_cpu in ("host-passthrough", "maximum"):
        return TIPO_CPU_HOST, EstadoFila.APROXIMADO, None
    if d.modo_cpu == "host-model":
        return (
            por_defecto,
            EstadoFila.APROXIMADO,
            _aviso("tipo_cpu", "V-D37", origen="host-model", cpu=por_defecto),
        )
    conocidos = set(TIPOS_CPU_ARM if es_arm else TIPOS_CPU_X86)
    hardware = inv.catalogo.hardware if inv is not None and inv.catalogo is not None else None
    if hardware is not None and nodo is not None:
        conocidos.update(m.nombre for m in hardware.cpus.get(nodo, ()))
    if d.modelo_cpu and d.modelo_cpu in conocidos:
        return d.modelo_cpu, EstadoFila.MIGRADO, None
    origen = d.modelo_cpu or d.modo_cpu
    return (
        por_defecto,
        EstadoFila.APROXIMADO,
        _aviso("tipo_cpu", "V-D37", origen=origen, cpu=por_defecto),
    )


def _filas_arquitectura(
    c: _Constructor, d: DominioLibvirt, inv: Inventario | None, nodo: str | None
) -> bool:
    """Valida tipo y arquitectura (V-D23, V-D23b, V-D24, V-D04). Devuelve si el nodo es ARM."""
    if d.tipo_dominio == "kvm":
        c.fila("tipo_dominio", d.tipo_dominio, "kvm", EstadoFila.MIGRADO)
    elif d.tipo_dominio == "qemu":
        c.fila(
            "tipo_dominio", d.tipo_dominio, "kvm", EstadoFila.APROXIMADO,
            _aviso("tipo_dominio", "V-D23b"),
        )  # fmt: skip
    else:
        c.fila(
            "tipo_dominio", d.tipo_dominio, "", EstadoFila.BLOQUEA,
            _error("tipo_dominio", "V-D23", tipo=d.tipo_dominio or "?"),
        )  # fmt: skip
    if d.tipo_os != "hvm":
        c.fila(
            "tipo_os", d.tipo_os, "", EstadoFila.BLOQUEA,
            _error("tipo_dominio", "V-D23", tipo=d.tipo_os, motivo="os"),
        )  # fmt: skip

    con_nodo = inv is not None and nodo is not None
    arq_nodo: Arquitectura | None = None
    if inv is not None and nodo is not None:
        arq_nodo = arquitectura_efectiva(inv, nodo)
    arq_xml = d.arquitectura_original or d.arquitectura
    nodo_txt = nodo or ""
    if d.arquitectura == "otro":
        arq_n = arq_nodo.value if arq_nodo is not None else ""
        c.fila(
            "arquitectura", arq_xml, arq_n, EstadoFila.BLOQUEA,
            _error("arquitectura", "V-D24", arq_xml=arq_xml, nodo=nodo_txt, arq_nodo=arq_n),
        )  # fmt: skip
    elif not d.arquitectura:
        destino = arq_nodo.value if arq_nodo is not None else ""
        c.fila(
            "arquitectura", "", destino, EstadoFila.APROXIMADO,
            _aviso("arquitectura", "V-D24.supuesta", nodo=nodo_txt, arq_nodo=destino),
        )  # fmt: skip
    elif arq_nodo is not None and inv is not None and nodo is not None:
        efectiva = Arquitectura(d.arquitectura)
        if efectiva != arq_nodo:
            c.fila(
                "arquitectura", arq_xml, arq_nodo.value, EstadoFila.BLOQUEA,
                _error(
                    "arquitectura", "V-D24",
                    arq_xml=arq_xml, nodo=nodo_txt, arq_nodo=arq_nodo.value,
                ),
            )  # fmt: skip
        elif arquitectura_de(inv, nodo) == Arquitectura.DESCONOCIDA:
            c.fila(
                "arquitectura", arq_xml, arq_nodo.value, EstadoFila.APROXIMADO,
                _aviso("arquitectura", "V-D04", nodo=nodo_txt),
            )  # fmt: skip
        else:
            c.fila("arquitectura", arq_xml, arq_nodo.value, EstadoFila.MIGRADO)
    else:
        c.fila("arquitectura", arq_xml, arq_xml, EstadoFila.MIGRADO)
    if d.arquitectura == "x86_64" and arq_xml.lower() != "x86_64" and arq_xml.lower() != "amd64":
        # i386/i686: se acepta en un nodo x86_64 con aviso
        c.fila(
            "arquitectura.i686", arq_xml, "x86_64", EstadoFila.APROXIMADO,
            _aviso("arquitectura", "V-D24.i686", arq_xml=arq_xml, nodo=nodo_txt),
        )  # fmt: skip
    if con_nodo and arq_nodo is not None:
        return arq_nodo == Arquitectura.AARCH64
    return d.arquitectura == "aarch64"


def _filas_cpu_y_memoria(
    c: _Constructor,
    d: DominioLibvirt,
    cfg: ConfiguracionVM,
    es_arm: bool,
    inv: Inventario | None,
    nodo: str | None,
) -> None:
    # Memoria (V-D40)
    if d.memoria_mib is None or not MEMORIA_MIN_MIB <= d.memoria_mib <= MEMORIA_MAX_MIB:
        valor = "" if d.memoria_mib is None else f"{d.memoria_mib} MiB"
        c.fila(
            "memoria", valor, "", EstadoFila.BLOQUEA,
            _error("memoria_mib", "V-D40", memoria=valor, maximo=f"{MEMORIA_MAX_MIB} MiB"),
        )  # fmt: skip
    else:
        cfg.memoria_mib = d.memoria_mib
        c.fila("memoria", f"{d.memoria_mib} MiB", f"{d.memoria_mib} MiB", EstadoFila.MIGRADO)
        if d.memoria_actual_mib is not None and d.memoria_actual_mib < d.memoria_mib:
            c.fila("memoria.actual", f"{d.memoria_actual_mib} MiB", "", EstadoFila.NO_SE_MIGRA)

    # Sockets y núcleos
    sockets: int | None
    cores: int | None
    if d.sockets is not None and d.cores is not None:
        sockets, cores = d.sockets, d.cores * (d.threads or 1)
        origen = f"sockets={d.sockets} cores={d.cores} threads={d.threads or 1}"
    elif d.vcpus is not None:
        sockets, cores = 1, d.vcpus
        origen = f"vcpu={d.vcpus}"
    else:
        sockets = cores = None
        origen = ""
    if sockets is None or cores is None:
        c.fila("cpu.topologia", origen, f"sockets={cfg.sockets} cores={cfg.cores}",
               EstadoFila.APROXIMADO)  # fmt: skip
    else:
        destino = f"sockets={sockets} cores={cores}"
        if not SOCKETS_MIN <= sockets <= SOCKETS_MAX:
            c.fila(
                "cpu.topologia", origen, destino, EstadoFila.BLOQUEA,
                _error("sockets", "V-05", valor=str(sockets), maximo=str(SOCKETS_MAX)),
            )  # fmt: skip
        elif not CORES_MIN <= cores <= CORES_MAX:
            c.fila(
                "cpu.topologia", origen, destino, EstadoFila.BLOQUEA,
                _error("cores", "V-05", valor=str(cores), maximo=str(CORES_MAX)),
            )  # fmt: skip
        else:
            cfg.sockets, cfg.cores = sockets, cores
            c.fila("cpu.topologia", origen, destino, EstadoFila.MIGRADO)
    if d.threads is not None and d.threads > 1:
        c.fila("cpu.hilos", f"threads={d.threads}", "", EstadoFila.APROXIMADO)
    if d.vcpus_actuales is not None and d.vcpus is not None and d.vcpus_actuales != d.vcpus:
        c.fila("cpu.actual", f"current={d.vcpus_actuales}", "", EstadoFila.NO_SE_MIGRA)

    # Tipo de CPU (V-D37)
    tipo, estado, problema = _cpu(d, es_arm, inv, nodo)
    cfg.tipo_cpu = tipo
    c.fila("cpu", d.modelo_cpu or d.modo_cpu, tipo, estado, problema)
    if d.con_caracteristicas_cpu:
        c.fila("cpu.banderas", "", "", EstadoFila.NO_SE_MIGRA)


def _filas_firmware_y_so(
    c: _Constructor, d: DominioLibvirt, cfg: ConfiguracionVM, es_arm: bool
) -> None:
    # Tipo de SO (RF-D1.12): metadatos libosinfo y, sin ellos, la pista de Hyper-V
    tipo, windows = _tipo_so_por_pista(d.pista_so) if d.pista_so else (None, False)
    if tipo is None:
        if d.pista_so:
            motivo = "windows_antiguo" if windows else "desconocido"
            tipo, windows = TipoSO.OTRO, windows
        elif d.con_hyperv:
            tipo, windows, motivo = TipoSO.WINDOWS_10, True, "hyperv"
        else:
            tipo, motivo = TipoSO.OTRO, "sin_pista"
        c.fila(
            "tipo_so", d.pista_so, tipo.value, EstadoFila.APROXIMADO,
            _aviso("tipo_so", "V-D38", pista=d.pista_so, motivo=motivo),
        )  # fmt: skip
    elif tipo == TipoSO.OTRO:
        motivo = "windows_antiguo" if windows else "desconocido"
        c.fila(
            "tipo_so", d.pista_so, tipo.value, EstadoFila.APROXIMADO,
            _aviso("tipo_so", "V-D38", pista=d.pista_so, motivo=motivo),
        )  # fmt: skip
    else:
        c.fila("tipo_so", d.pista_so, tipo.value, EstadoFila.MIGRADO)
    cfg.tipo_so = tipo
    es_windows = tipo in _TIPOS_WINDOWS

    # Firmware, NVRAM y TPM
    cfg.firmware = Firmware.OVMF if (d.uefi or es_arm) else Firmware.SEABIOS
    if es_arm and not d.uefi:
        c.fila(
            "firmware", "BIOS", cfg.firmware.value, EstadoFila.APROXIMADO,
            _aviso("firmware", "V-D08", lista="firmware"),
        )  # fmt: skip
    else:
        c.fila("firmware", "UEFI" if d.uefi else "BIOS", cfg.firmware.value, EstadoFila.MIGRADO)
    if d.uefi and d.con_nvram:
        c.fila("nvram", "", "", EstadoFila.NO_SE_MIGRA, _aviso("nvram", "V-D30"))
    if d.uefi and d.secure_boot_inscrito and not es_windows:
        c.fila("firmware.claves", "secure-boot", "", EstadoFila.APROXIMADO)
    cfg.tpm = d.tpm
    if d.tpm:
        motivo_tpm = (
            "passthrough"
            if d.tpm_backend == "passthrough"
            else "v1.2"
            if d.tpm_version == "1.2"
            else "nuevo"
        )
        c.fila(
            "tpm", d.tpm_version or d.tpm_backend or "tpm", "v2.0", EstadoFila.APROXIMADO,
            _aviso("tpm", "V-D31", motivo=motivo_tpm, windows="si" if es_windows else "no"),
        )  # fmt: skip
    cfg.agente_qemu = d.agente_qemu
    if d.agente_qemu:
        c.fila("agente", "org.qemu.guest_agent.0", "agent=1", EstadoFila.MIGRADO)


def _imagen_ya_subida(inv: Inventario | None, nodo: str | None, archivo: str) -> RefVolumen | None:
    """Imagen del contenido ``import`` del nodo con ese nombre de archivo (CA-D1.7.5).

    Solo si el catálogo está leído y hay UNA coincidencia exacta; con dudas no se elige.
    """
    cat = inv.catalogo if inv is not None else None
    if cat is None or nodo is None or not archivo:
        return None
    halladas = cat.buscar_nombre(archivo, nodo, Contenido.IMPORT)
    if len(halladas) != 1:
        return None
    return RefVolumen(nombre=halladas[0].nombre, volid=halladas[0].volid)


def _filas_discos(
    c: _Constructor,
    d: DominioLibvirt,
    cfg: ConfiguracionVM,
    base: ConfiguracionVM,
    es_arm: bool,
    inv: Inventario | None = None,
    nodo: str | None = None,
) -> tuple[int, ...]:
    """Construye ``cfg.discos`` y las filas de discos; devuelve los índices no migrables."""
    for cd in (x for x in d.discos if x.dispositivo in ("cdrom", "floppy")):
        c.fila(f"cdrom[{cd.indice}]", f"{cd.dispositivo} {cd.archivo}", "", EstadoFila.NO_SE_MIGRA)

    candidatos = [x for x in d.discos if x.dispositivo == "disk"]
    con_orden = [x for x in candidatos if x.arranque is not None]
    sistema = (
        min(con_orden, key=lambda x: (x.arranque or 0, x.indice))
        if con_orden
        else (candidatos[0] if candidatos else None)
    )
    ordenados = ([sistema] if sistema is not None else []) + [
        x for x in d.discos if x.dispositivo in ("disk", "lun") and x is not sistema
    ]
    plantilla = base.discos[0] if base.discos else Disco(storage="", tamano_gib=TAMANO_DISCO_GIB)
    migrables: list[DiscoLibvirt] = []
    no_migrables: list[int] = []
    for x in ordenados:
        if x.dispositivo == "lun" or x.tipo_fuente in _FUENTES_NO_MIGRABLES:
            no_migrables.append(x.indice)
            nombre = x.dev or x.archivo
            origen = f"{x.dispositivo}/{x.tipo_fuente} {nombre}"
            if x is sistema:
                c.fila(
                    "disco[0]", origen, "", EstadoFila.BLOQUEA,
                    _error("discos[0]", "V-D29", disco=nombre, tipo=x.tipo_fuente, sistema="si"),
                )  # fmt: skip
            else:
                c.fila(
                    f"disco_origen[{x.indice}]", origen, "", EstadoFila.NO_SE_MIGRA,
                    _aviso("discos", "V-D29", disco=nombre, tipo=x.tipo_fuente, sistema="no"),
                )  # fmt: skip
        else:
            migrables.append(x)

    discos: list[Disco] = []
    for x in migrables:
        bus, motivo = _bus_destino(x, es_arm)
        i = len(discos)
        discos.append(
            Disco(
                storage=plantilla.storage,
                tamano_gib=plantilla.tamano_gib,
                bus=bus,
                formato=FormatoDisco.AUTO,
                discard=x.discard,
                ssd=plantilla.ssd and bus in BUSES_CON_SSD,
                iothread=x.iothread and bus in (Bus.SCSI, Bus.VIRTIO),
            )
        )
        nombre = x.dev or x.archivo
        origen = " ".join(t for t in (x.dev, x.archivo, x.formato) if t)
        c.fila(f"disco[{i}]", origen, bus.value, EstadoFila.MIGRADO)
        if motivo == "arm":
            c.fila(
                f"disco[{i}].bus", x.bus, bus.value, EstadoFila.APROXIMADO,
                _aviso(f"discos[{i}].bus", "V-D08", lista="bus"),
            )  # fmt: skip
        elif motivo == "sin_equivalente":
            c.fila(
                f"disco[{i}].bus", x.bus or x.dev, bus.value, EstadoFila.APROXIMADO,
                _aviso(f"discos[{i}].bus", "V-D36", modelo=x.bus or x.dev, nuevo=bus.value),
            )  # fmt: skip
        if x.con_backing_store:
            c.fila(
                f"disco[{i}].backing", nombre, "", EstadoFila.APROXIMADO,
                _aviso(f"discos[{i}]", "V-D25a", disco=nombre),
            )  # fmt: skip
        sin_migrar = [
            t
            for t, activo in (
                (f"cache={x.cache}", x.cache not in ("", "default")),
                ("readonly", x.solo_lectura),
                ("shareable", x.compartido),
            )
            if activo
        ]
        if sin_migrar:
            c.fila(f"disco[{i}].opciones", ", ".join(sin_migrar), "", EstadoFila.NO_SE_MIGRA)
    if discos:
        cfg.discos = discos
    elif not (sistema is not None and sistema.indice in no_migrables):
        c.fila(
            "disco[0]", "", "", EstadoFila.BLOQUEA,
            _error("discos", "V-D27", disco="0", motivo="sin_discos"),
        )  # fmt: skip
        cfg.discos = copy.deepcopy(base.discos)

    # V-D28: más discos de los que admite el bus (la V-07 de «Comprobar» es la misma regla)
    for bus, n in Counter(x.bus for x in discos).items():
        if n > MAX_DISPOSITIVOS[bus]:
            c.fila(
                f"discos.{bus.value}", str(n), str(MAX_DISPOSITIVOS[bus]), EstadoFila.BLOQUEA,
                _error(
                    "discos", "V-D28",
                    n=str(n), bus=bus.value, maximo=str(MAX_DISPOSITIVOS[bus]),
                ),
            )  # fmt: skip
    if d.modelo_scsi not in _MODELOS_SCSI_VIRTIO and any(x.bus == Bus.SCSI for x in discos):
        c.fila(
            "controlador", d.modelo_scsi, ControladorScsi.VIRTIO_SINGLE.value,
            EstadoFila.APROXIMADO,
            _aviso(
                "controlador_scsi", "V-D36",
                modelo=d.modelo_scsi, nuevo=ControladorScsi.VIRTIO_SINGLE.value,
            ),
        )  # fmt: skip
    cfg.controlador_scsi = ControladorScsi.VIRTIO_SINGLE
    # Imagen ya subida con el mismo nombre que el archivo original (CA-D1.7.5); si no, vacía.
    imagenes = [_imagen_ya_subida(inv, nodo, x.archivo) for x in migrables] if discos else []
    imagenes += [None] * (len(cfg.discos) - len(imagenes))
    for i, imagen in enumerate(imagenes):
        if imagen is not None:  # la cabecera de una imagen del servidor no se puede leer (V-D25c)
            c.fila(
                f"disco[{i}].imagen", imagen.nombre, imagen.volid or "", EstadoFila.APROXIMADO,
                _aviso(f"discos[{i}]", "V-D25c", archivo=imagen.nombre),
            )  # fmt: skip
    otras = tuple(ImagenDisco(indice=i, imagen=imagenes[i]) for i in range(1, len(cfg.discos)))
    cfg.detalle_origen = DetalleImportacion(imagen=imagenes[0] or RefVolumen(), otras=otras)
    return tuple(no_migrables)


def _red_destino(
    t: TarjetaLibvirt, inv: Inventario | None, nodo: str | None
) -> tuple[str, Problema | None]:
    """Bridge propuesto (solo uno que exista tal cual en el nodo) o el problema V-D35."""
    campo = f"redes[{t.indice}].bridge"
    base = {"tarjeta": str(t.indice), "origen": t.origen, "tipo": t.tipo}
    if t.tipo != "bridge":
        motivo = "nat" if t.tipo == "network" and t.origen == "default" else t.tipo
        return "", _error(campo, "V-D35", motivo=motivo or "?", **base)
    if inv is None or nodo is None:
        return "", _error(campo, "V-D35", motivo="sin_servidor", **base)
    if t.origen and t.origen_limpio and t.origen in redes_de_nodo(inv, nodo):
        return t.origen, None
    return "", _error(campo, "V-D35", motivo="bridge_inexistente", **base)


def _filas_redes(
    c: _Constructor,
    d: DominioLibvirt,
    cfg: ConfiguracionVM,
    es_arm: bool,
    inv: Inventario | None,
    nodo: str | None,
    conservar_mac: bool,
) -> None:
    redes: list[InterfazRed] = []
    for t in d.tarjetas:
        i = len(redes)
        bridge, problema = _red_destino(t, inv, nodo)
        modelo_xml = t.modelo.lower()
        if modelo_xml in _MODELOS_E1000 and not es_arm:
            modelo = ModeloRed.E1000
        else:
            modelo = ModeloRed.VIRTIO
        red = InterfazRed(bridge=bridge, modelo=modelo, vlan=t.vlan)
        origen_red = f"{t.tipo} {t.origen}".strip()
        if problema is None:
            c.fila(f"red[{i}]", origen_red, bridge, EstadoFila.APROXIMADO)
        else:
            c.fila(f"red[{i}]", origen_red, "", EstadoFila.NO_SE_MIGRA, problema)
        if t.openvswitch:
            c.fila(
                f"red[{i}].virtualport", "openvswitch", "", EstadoFila.APROXIMADO,
                _aviso(f"redes[{i}].bridge", "V-D35", motivo="openvswitch", tarjeta=str(i)),
            )  # fmt: skip
        # Modelo de tarjeta
        if modelo_xml in _MODELOS_VIRTIO:
            c.fila(f"red[{i}].modelo", t.modelo, modelo.value, EstadoFila.MIGRADO)
        elif modelo_xml in _MODELOS_E1000 and es_arm:
            c.fila(
                f"red[{i}].modelo", t.modelo, modelo.value, EstadoFila.APROXIMADO,
                _aviso(f"redes[{i}].modelo", "V-D08", lista="modelo_red"),
            )  # fmt: skip
        elif modelo_xml == "e1000":
            c.fila(f"red[{i}].modelo", t.modelo, modelo.value, EstadoFila.MIGRADO)
        else:
            c.fila(
                f"red[{i}].modelo", t.modelo, modelo.value, EstadoFila.APROXIMADO,
                _aviso(f"redes[{i}].modelo", "V-D36", modelo=t.modelo, nuevo=modelo.value),
            )  # fmt: skip
        if t.vlan is not None:
            c.fila(f"red[{i}].vlan", str(t.vlan), str(t.vlan), EstadoFila.MIGRADO)
        if t.mtu is not None:
            if modelo == ModeloRed.VIRTIO and MTU_MIN <= t.mtu <= MTU_MAX:
                red.mtu = t.mtu
                c.fila(f"red[{i}].mtu", str(t.mtu), str(t.mtu), EstadoFila.MIGRADO)
            else:
                c.fila(f"red[{i}].mtu", str(t.mtu), "", EstadoFila.NO_SE_MIGRA)
        if t.limite_kibs is not None and t.limite_kibs > 0:
            mb = -(-(t.limite_kibs * 1024) // 10**6)  # ⌈KiB/s · 1024 / 10⁶⌉ MB/s
            if mb <= _MAX_LIMITE_MB:
                red.limite_mb = float(mb)
                c.fila(
                    f"red[{i}].limite", f"{t.limite_kibs} KiB/s", f"{mb} MB/s",
                    EstadoFila.APROXIMADO,
                )  # fmt: skip
        if t.enlace_abajo or t.con_filtro:
            extra = ", ".join(
                n for n, a in (("link=down", t.enlace_abajo), ("filterref", t.con_filtro)) if a
            )
            c.fila(f"red[{i}].extra", extra, "", EstadoFila.NO_SE_MIGRA)
        if t.mac is not None:
            if conservar_mac:
                red.mac_conservada = t.mac
                c.fila(
                    f"red[{i}].mac", t.mac, t.mac, EstadoFila.MIGRADO,
                    _aviso(f"redes[{i}].mac_conservada", "V-D32", tarjeta=str(i)),
                )  # fmt: skip
            else:
                c.fila(f"red[{i}].mac", t.mac, "nueva", EstadoFila.APROXIMADO)
        redes.append(red)
    cfg.redes = redes


def _filas_sin_equivalente(c: _Constructor, d: DominioLibvirt) -> None:
    if d.sin_equivalente:
        recuento = Counter(d.sin_equivalente)
        lista = ", ".join(f"{n}×{k}" if n > 1 else k for k, n in sorted(recuento.items()))
        c.fila(
            "dispositivos", lista, "", EstadoFila.NO_SE_MIGRA,
            _aviso("dispositivos", "V-D41", lista=lista),
        )  # fmt: skip
    if d.con_spice:
        c.fila("pantalla", "spice", "", EstadoFila.NO_SE_MIGRA)
    if d.otros_no_migrados:
        c.fila("otros", ", ".join(sorted(set(d.otros_no_migrados))), "", EstadoFila.NO_SE_MIGRA)
    if d.desconocidos:
        lista = ", ".join(sorted(set(d.desconocidos)))
        c.fila(
            "desconocidos", lista, "", EstadoFila.NO_SE_MIGRA,
            _aviso("dispositivos", "V-D41.desconocidos", lista=lista),
        )  # fmt: skip
    if d.con_contrasenas:  # nunca se lee el valor de passwd
        c.fila("contrasenas", "", "", EstadoFila.NO_SE_MIGRA, _aviso("contrasenas", "V-D39"))


def proponer(
    dominio: DominioLibvirt,
    base: ConfiguracionVM,
    inv: Inventario | None,
    nodo: str | None,
    *,
    conservar_mac: bool = False,
) -> PropuestaLibvirt:
    """Propone la configuración del formulario y la vista previa para ``dominio``.

    Args:
        dominio: el dominio interpretado.
        base: configuración actual del formulario (no se modifica; se parte de una copia).
        inv: inventario de la conexión (nodos, redes y arquitectura); ``None`` = sin datos.
        nodo: servidor de destino elegido; sin él no se comprueban arquitectura ni redes.
        conservar_mac: conserva la MAC de todas las tarjetas que la traen (V-D32, DT-D15).

    V-D23/23b/24/25a/29/30/31/35/36/37/38/39/40/41 y V-D28 (vista previa). V-D35 es error de
    «Comprobar» pero su fila no bloquea «Rellenar» (CA-D1.11.2): las filas «Bloquea» son las de
    V-D23, V-D24, V-D27 (sin discos), V-D28, V-D29 del disco de sistema, V-D40 y los límites de
    CPU. Los discos «No migrar» no entran en ``cfg.discos``.
    """
    cfg = copy.deepcopy(base)
    cfg.origen = OrigenSO.IMPORTAR_DISCO
    c = _Constructor()

    nombre = nombre_dns_de(dominio.nombre)
    cfg.nombre = nombre
    c.fila(
        "nombre", dominio.nombre, nombre,
        EstadoFila.MIGRADO if nombre == dominio.nombre else EstadoFila.APROXIMADO,
    )  # fmt: skip

    es_arm = _filas_arquitectura(c, dominio, inv, nodo)
    _filas_cpu_y_memoria(c, dominio, cfg, es_arm, inv, nodo)
    _filas_firmware_y_so(c, dominio, cfg, es_arm)
    no_migrables = _filas_discos(c, dominio, cfg, base, es_arm, inv, nodo)
    _filas_redes(c, dominio, cfg, es_arm, inv, nodo, conservar_mac)
    _filas_sin_equivalente(c, dominio)
    return PropuestaLibvirt(cfg=cfg, filas=tuple(c.filas), discos_no_migrables=no_migrables)
