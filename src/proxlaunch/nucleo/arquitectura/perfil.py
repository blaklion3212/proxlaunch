"""Perfil de hardware aarch64: valores x86 adaptados (RF-D2.6, RF-D2.10, DT-D8). Sin Qt.

``adaptar_a_arquitectura`` es la fuente única de qué valores x86 se cambian al apuntar a un
nodo ARM; la usan el planificador (crear y simular) y el formulario. No toca el origen: el
archivo guardado no se modifica.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.hardware_cluster.modelos import ModeloCpu
from proxlaunch.nucleo.modelos.cpu import (
    PREFIJO_CPU_PERSONALIZADA,
    TIPO_CPU_ARM_DEFECTO,
    es_cpu_solo_x86,
)
from proxlaunch.nucleo.modelos.vm import Bus, ConfiguracionVM, Disco, Firmware, ModeloRed

# Buses que no existen en aarch64 (no hay controlador IDE y no arranca desde SATA, INV-D §1.3).
BUSES_SOLO_X86 = frozenset({Bus.IDE, Bus.SATA})
PREFIJO_RANURA_CDROM = "scsi"


@dataclass(frozen=True)
class CambioArquitectura:
    campo: str  # "firmware" | "discos[i].bus" | "tipo_cpu" | "redes[i].modelo"
    antes: str
    despues: str


def _cpu_adaptada(tipo: str, cpus_nodo: Sequence[ModeloCpu] | None) -> str | None:
    """Tipo de CPU para ARM, o ``None`` si el actual vale tal cual."""
    if es_cpu_solo_x86(tipo):
        return TIPO_CPU_ARM_DEFECTO
    # CL-D6: un personalizado que el nodo ARM no tiene (solo si su lista se leyó)
    if (
        tipo.startswith(PREFIJO_CPU_PERSONALIZADA)
        and cpus_nodo is not None
        and tipo not in {m.nombre for m in cpus_nodo}
    ):
        return TIPO_CPU_ARM_DEFECTO
    return None


def adaptar_a_arquitectura(
    cfg: ConfiguracionVM, arq: Arquitectura, *, cpus_nodo: Sequence[ModeloCpu] | None = None
) -> tuple[ConfiguracionVM, tuple[CambioArquitectura, ...]]:
    """Configuración adaptada a ``arq`` y la lista de cambios (V-D08).

    ``X86_64`` y ``DESCONOCIDA`` devuelven ``(cfg, ())`` sin copiar. Con ``AARCH64``: firmware
    → OVMF, buses IDE/SATA → SCSI, CPU solo x86 → ``host``, modelo de red → ``virtio`` y un
    ``custom-*`` que el nodo no tiene (si se leyó su lista) → ``host``. Un clon no se adapta
    (hereda de la plantilla). ``cfg`` no se modifica.
    """
    if arq != Arquitectura.AARCH64:
        return cfg, ()
    cambios: list[CambioArquitectura] = []
    nuevo = cfg

    if cfg.firmware != Firmware.OVMF:
        cambios.append(CambioArquitectura("firmware", cfg.firmware.value, Firmware.OVMF.value))
        nuevo = dataclasses.replace(nuevo, firmware=Firmware.OVMF)

    discos: list[Disco] = []
    for i, d in enumerate(cfg.discos):
        if d.bus in BUSES_SOLO_X86:
            cambios.append(CambioArquitectura(f"discos[{i}].bus", d.bus.value, Bus.SCSI.value))
            d = dataclasses.replace(d, bus=Bus.SCSI)
        discos.append(d)
    if any(a is not b for a, b in zip(discos, cfg.discos, strict=True)):
        nuevo = dataclasses.replace(nuevo, discos=discos)

    cpu = _cpu_adaptada(cfg.tipo_cpu, cpus_nodo)
    if cpu is not None:
        cambios.append(CambioArquitectura("tipo_cpu", cfg.tipo_cpu, cpu))
        nuevo = dataclasses.replace(nuevo, tipo_cpu=cpu)

    redes = []
    for i, r in enumerate(cfg.redes):
        if r.modelo != ModeloRed.VIRTIO:
            cambios.append(
                CambioArquitectura(f"redes[{i}].modelo", r.modelo.value, ModeloRed.VIRTIO.value)
            )
            r = dataclasses.replace(r, modelo=ModeloRed.VIRTIO)
        redes.append(r)
    if any(a is not b for a, b in zip(redes, cfg.redes, strict=True)):
        nuevo = dataclasses.replace(nuevo, redes=redes)
    return nuevo, tuple(cambios)


def ranura_cdrom_aarch64(cfg: ConfiguracionVM, ocupadas: Collection[str]) -> str:
    """Primera ``scsiN`` libre para un CD-ROM en aarch64 (RF-D2.6: nunca ``ideN``).

    ``ocupadas`` son las claves ya usadas por los discos (y por otros CD-ROM). ``cfg`` se
    recibe por la firma de la arquitectura; la elección solo depende de ``ocupadas``.
    """
    n = 0
    while f"{PREFIJO_RANURA_CDROM}{n}" in ocupadas:
        n += 1
    return f"{PREFIJO_RANURA_CDROM}{n}"
