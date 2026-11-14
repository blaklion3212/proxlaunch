"""Perfiles de fábrica (RF-P02, docs/requisitos/mvp3.md §8). Solo lectura (INV-M7).

El núcleo fija ids y hardware; los nombres y descripciones los aporta la interfaz ya traducidos.
Describen solo hardware con disco vacío: ninguno instala un sistema operativo (CA-P02.6).
"""

from __future__ import annotations

from collections.abc import Mapping

from proxlaunch.nucleo.modelos.vm import Bus, Firmware, ModeloRed
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
) -> ConfigPerfil:
    return ConfigPerfil(
        firmware=firmware,
        sockets=1,
        cores=cores,
        memoria_mib=memoria_mib,
        discos=(DiscoPerfil(tamano_gib=disco_gib, bus=bus, iothread=iothread),),
        redes=(RedPerfil(modelo=modelo_red),),
    )


# Clave → hardware, en el orden en que se ofrecen al usuario.
_CONFIGS: dict[str, ConfigPerfil] = {
    "servidor-pequeno": _config(2, 2048, 32),
    "servidor-mediano": _config(4, 4096, 64),
    "base-de-datos": _config(4, 8192, 100),
    "servidor-grande": _config(8, 16384, 128),
    # UEFI (OVMF) con q35 lo añade el constructor de la petición; pendiente de LAB-M3-01.
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
