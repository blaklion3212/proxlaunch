"""Asistente de sistema operativo y hardware recomendado (RF-O13, DT-O5/O6/O9). Puro.

``TABLA_SO`` fija por tipo de SO el ``ostype``, el firmware, el TPM, el CD de drivers y el
agente. ``aplicar_asistente`` aplica la tabla a una configuración **sin tocar** núcleos,
memoria ni tamaños (CA-O13.9) y lista cada campo que cambió. ``avisos_so`` calcula los avisos
no bloqueantes (mínimos de Windows V-O07 y RHEL 10 / x86-64-v3).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from proxlaunch.nucleo.modelos.origen import DetalleIso, TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    Firmware,
    ModeloRed,
)
from proxlaunch.nucleo.validacion import Problema, Severidad


@dataclass(frozen=True)
class MinimosSO:
    """Mínimos de Microsoft (V-O07)."""

    cores: int
    memoria_mib: int
    disco_gib: int


@dataclass(frozen=True)
class PerfilSO:
    """Hardware recomendado para un tipo de SO.

    ``firmware`` ``None`` = el del perfil o formulario (no se toca). ``agente`` = el asistente
    activa el agente QEMU (Windows); en Linux lo decide el usuario.
    """

    ostype: str
    firmware: Firmware | None
    tpm: bool
    tpm_obligatorio: bool
    drivers: bool
    agente: bool
    es_windows: bool
    minimos: MinimosSO | None


_MIN_W11 = MinimosSO(cores=2, memoria_mib=4096, disco_gib=64)
_MIN_W10 = MinimosSO(cores=1, memoria_mib=2048, disco_gib=32)

TABLA_SO: Mapping[TipoSO, PerfilSO] = {
    TipoSO.LINUX: PerfilSO("l26", None, False, False, False, False, False, None),
    TipoSO.WINDOWS_11: PerfilSO("win11", Firmware.OVMF, True, True, True, True, True, _MIN_W11),
    TipoSO.WINDOWS_SERVER_2022_2025: PerfilSO(
        "win11", Firmware.OVMF, True, False, True, True, True, _MIN_W10
    ),
    TipoSO.WINDOWS_10: PerfilSO("win10", Firmware.OVMF, False, False, True, True, True, _MIN_W10),
    TipoSO.WINDOWS_SERVER_2016_2019: PerfilSO(
        "win10", Firmware.OVMF, False, False, True, True, True, _MIN_W10
    ),
    TipoSO.OTRO: PerfilSO("other", None, False, False, False, False, False, None),
}

# Tipos de CPU que ya cumplen x86-64-v3 (o lo exponen todo): no necesitan el aviso de RHEL 10.
_CPU_V3 = frozenset({"x86-64-v3", "x86-64-v4", "host"})
_RE_RHEL10 = re.compile(r"(rhel|rocky|alma(linux)?|centos)[-_ .]*(stream[-_ .]*)?10", re.IGNORECASE)


class CampoAsistente(StrEnum):
    FIRMWARE = "firmware"
    TPM = "tpm"
    CONTROLADOR = "controlador"
    MODELO_RED = "modelo_red"
    BUS_DISCO = "bus_disco"
    AGENTE = "agente"


@dataclass(frozen=True)
class CambioAsistente:
    """Un campo que el asistente cambió. Los booleanos se expresan como ``si``/``no``."""

    campo: CampoAsistente
    antes: str
    despues: str


@dataclass(frozen=True)
class ResultadoAsistente:
    cfg: ConfiguracionVM
    cambios: tuple[CambioAsistente, ...]


def _sn(valor: bool) -> str:
    return "si" if valor else "no"


def aplicar_asistente(
    cfg: ConfiguracionVM, tipo_so: TipoSO, *, disco_compatible: bool = False
) -> ResultadoAsistente:
    """Copia de ``cfg`` con el hardware de la tabla para ``tipo_so`` y la lista de cambios.

    - Todos los tipos fijan ``tipo_so`` (y con él el ``ostype``). ``otro`` no cambia nada más.
    - Linux y Windows fijan controlador ``virtio-scsi-single`` y red ``virtio``; el firmware y
      el TPM de la tabla (Windows: OVMF; TPM según el SO); Windows además el bus del primer
      disco (``scsi``, o ``sata`` con ``disco_compatible``, DT-O9) y el agente QEMU.
    - No se tocan núcleos, memoria ni tamaños de disco (CA-O13.9).
    """
    perfil = TABLA_SO[tipo_so]
    nueva = copy.deepcopy(cfg)
    nueva.tipo_so = tipo_so
    cambios: list[CambioAsistente] = []
    if tipo_so == TipoSO.OTRO:
        return ResultadoAsistente(nueva, ())

    if perfil.firmware is not None and nueva.firmware != perfil.firmware:
        cambios.append(
            CambioAsistente(CampoAsistente.FIRMWARE, str(nueva.firmware), str(perfil.firmware))
        )
        nueva.firmware = perfil.firmware
    if nueva.tpm != perfil.tpm:
        cambios.append(CambioAsistente(CampoAsistente.TPM, _sn(nueva.tpm), _sn(perfil.tpm)))
        nueva.tpm = perfil.tpm
    if nueva.controlador_scsi != ControladorScsi.VIRTIO_SINGLE:
        cambios.append(
            CambioAsistente(
                CampoAsistente.CONTROLADOR,
                str(nueva.controlador_scsi),
                str(ControladorScsi.VIRTIO_SINGLE),
            )
        )
        nueva.controlador_scsi = ControladorScsi.VIRTIO_SINGLE
    otros_modelos = sorted({str(r.modelo) for r in nueva.redes if r.modelo != ModeloRed.VIRTIO})
    if otros_modelos:
        cambios.append(
            CambioAsistente(
                CampoAsistente.MODELO_RED, ",".join(otros_modelos), str(ModeloRed.VIRTIO)
            )
        )
        for r in nueva.redes:
            r.modelo = ModeloRed.VIRTIO
    if perfil.es_windows and nueva.con_disco and nueva.discos:
        bus = Bus.SATA if disco_compatible else Bus.SCSI
        primero = nueva.discos[0]
        if primero.bus != bus:
            cambios.append(CambioAsistente(CampoAsistente.BUS_DISCO, str(primero.bus), str(bus)))
            primero.bus = bus
            if bus == Bus.SATA:
                primero.iothread = False  # SATA no admite IO Thread (V-11)
    if perfil.agente and not nueva.agente_qemu:
        cambios.append(CambioAsistente(CampoAsistente.AGENTE, "no", "si"))
        nueva.agente_qemu = True
    return ResultadoAsistente(nueva, tuple(cambios))


def _nombre_iso(cfg: ConfiguracionVM) -> str:
    detalle = cfg.detalle_origen
    if isinstance(detalle, DetalleIso):
        return detalle.iso.nombre or detalle.iso.volid or ""
    return ""


def avisos_so(cfg: ConfiguracionVM) -> list[Problema]:
    """Avisos no bloqueantes del asistente: ``V-O07`` (mínimos) y ``V-O05.rhel10``.

    - ``V-O07``: un problema por cada valor por debajo del mínimo de Microsoft (``cores`` es
      sockets × núcleos); los ``params`` llevan los tres mínimos del SO para armar el mensaje.
    - ``V-O05.rhel10``: solo con ``linux``, CPU inferior a x86-64-v3 y un ISO cuyo nombre parece
      RHEL/Rocky/Alma 10 (D-25.6, [A] hasta LAB-M4-05); sin coincidencia no hay aviso.
    """
    avisos: list[Problema] = []
    if cfg.tipo_so is None:
        return avisos
    perfil = TABLA_SO[cfg.tipo_so]
    minimos = perfil.minimos
    if minimos is not None:
        params = {
            "tipo_so": str(cfg.tipo_so),
            "minimo_cores": str(minimos.cores),
            "minimo_memoria_mib": str(minimos.memoria_mib),
            "minimo_disco_gib": str(minimos.disco_gib),
        }
        if cfg.sockets * cfg.cores < minimos.cores:
            avisos.append(Problema("cores", "V-O07", Severidad.AVISO, dict(params)))
        if cfg.memoria_mib < minimos.memoria_mib:
            avisos.append(Problema("memoria_mib", "V-O07", Severidad.AVISO, dict(params)))
        if cfg.con_disco and cfg.discos and cfg.discos[0].tamano_gib < minimos.disco_gib:
            avisos.append(Problema("discos[0].tamano_gib", "V-O07", Severidad.AVISO, dict(params)))
    if (
        cfg.tipo_so == TipoSO.LINUX
        and cfg.tipo_cpu not in _CPU_V3
        and _RE_RHEL10.search(_nombre_iso(cfg)) is not None
    ):
        coincide = True
        avisos.append(
            Problema(
                "tipo_cpu",
                "V-O05.rhel10",
                Severidad.AVISO,
                {"tipo_cpu": cfg.tipo_cpu, "coincide_iso": "1" if coincide else "0"},
            )
        )
    return avisos
