"""Perfiles de fábrica (RF-P02, docs/requisitos/mvp3.md §8). Solo lectura (INV-M7).

El núcleo fija ids y hardware; los nombres y descripciones los aporta la interfaz ya traducidos.
Los seis primeros describen hardware con disco vacío (CA-P02.6); los tres últimos (MVP 4)
sugieren el origen ISO sin fuente: nunca llevan un ISO.
"""

from __future__ import annotations

from collections.abc import Mapping

from proxlaunch.nucleo.modelos.origen import TipoSO
from proxlaunch.nucleo.modelos.vm import Bus, Firmware, ModeloRed, OrigenSO
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    PREFIJO_FABRICA,
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)


def _config(
    cores: int,
    memoria_mib: int,
    disco_gib: int,
    *,
    bus: Bus = Bus.SCSI,
    modelo_red: ModeloRed = ModeloRed.VIRTIO,
    firmware: Firmware = Firmware.SEABIOS,
    iothread: bool = True,
    tipo_so: TipoSO | None = None,
    tpm: bool = False,
    agente_qemu: bool = False,
) -> ConfigPerfil:
    return ConfigPerfil(
        firmware=firmware,
        sockets=1,
        cores=cores,
        memoria_mib=memoria_mib,
        discos=(DiscoPerfil(tamano_gib=disco_gib, bus=bus, iothread=iothread),),
        redes=(RedPerfil(modelo=modelo_red),),
        # Los perfiles con SO (MVP 4) sugieren «instalar desde ISO» sin fuente (RF-O31).
        origen=OrigenSO.ISO if tipo_so is not None else OrigenSO.DISCO_VACIO,
        tipo_so=tipo_so,
        tpm=tpm,
        agente_qemu=agente_qemu,
    )


# Clave → hardware, en el orden en que se ofrecen al usuario.
_CONFIGS: dict[str, ConfigPerfil] = {
    "servidor-pequeno": _config(2, 2048, 32),
    "servidor-mediano": _config(4, 4096, 64),
    "base-de-datos": _config(4, 8192, 100),
    "servidor-grande": _config(8, 16384, 128),
    # UEFI (OVMF) con q35 lo añade el constructor de la petición; confirmado en LAB-M3-01 (PVE 9.2).
    "escritorio-compatible": _config(
        4,
        4096,
        80,
        bus=Bus.SATA,
        modelo_red=ModeloRed.E1000,
        firmware=Firmware.OVMF,
        iothread=False,
    ),
    "minimo": _config(1, 512, 8),
    # MVP 4 (D-25.2): solo hardware, sin ISO. El aviso RHEL 10 / x86-64-v3 lo da el asistente.
    "windows-11": _config(
        4, 8192, 64, firmware=Firmware.OVMF, tipo_so=TipoSO.WINDOWS_11, tpm=True, agente_qemu=True
    ),
    "windows-server": _config(
        4,
        8192,
        80,
        firmware=Firmware.OVMF,
        tipo_so=TipoSO.WINDOWS_SERVER_2022_2025,
        tpm=True,
        agente_qemu=True,
    ),
    "linux-red-hat": _config(2, 4096, 40, tipo_so=TipoSO.LINUX),
}

CLAVES_FABRICA: tuple[str, ...] = tuple(_CONFIGS)


def perfiles_fabrica(
    textos: Mapping[str, tuple[str, str]] | None = None,
) -> tuple[PerfilMaquina, ...]:
    """Los perfiles de fábrica, inmutables.

    ``textos`` mapea el id completo (``"fabrica.minimo"``) o la clave (``"minimo"``) a
    ``(nombre, descripcion)`` traducidos. Sin textos, el nombre es la clave y la descripción
    queda vacía (pruebas sin Qt).
    """
    textos = textos or {}
    perfiles: list[PerfilMaquina] = []
    for clave, config in _CONFIGS.items():
        id_perfil = PREFIJO_FABRICA + clave
        nombre, descripcion = textos.get(id_perfil) or textos.get(clave) or (clave, "")
        perfiles.append(
            PerfilMaquina(
                id=id_perfil,
                nombre=nombre,
                descripcion=descripcion,
                origen=OrigenPerfil.FABRICA,
                config=config,
            )
        )
    return tuple(perfiles)
