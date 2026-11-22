"""Valores por defecto de la sección 5 de los requisitos (usuarios sin experiencia)."""

from collections.abc import Sequence

from proxlaunch.nucleo.modelos.inventario import Bridge, Storage
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
)

PUERTO = 8006
REALM = "pam"
SOCKETS = 1
CORES = 2
TIPO_CPU = "x86-64-v2-AES"
MEMORIA_MIB = 2048
TAMANO_DISCO_GIB = 32
BRIDGE_PREFERIDO = "vmbr0"
TIMEOUT_TAREA_S = 600  # P-05: 10 minutos


def disco_por_defecto(storage: str) -> Disco:
    """Disco por defecto: scsi, 32 GiB, formato automático, discard/ssd/iothread activos."""
    return Disco(
        storage=storage,
        tamano_gib=TAMANO_DISCO_GIB,
        bus=Bus.SCSI,
        formato=FormatoDisco.AUTO,
        discard=True,
        ssd=True,
        iothread=True,
    )


def bridge_por_defecto(bridges: Sequence[Bridge]) -> str | None:
    """``vmbr0`` si existe; si no, el primer bridge; ``None`` si no hay (CA-17.1)."""
    nombres = [b.nombre for b in bridges]
    if BRIDGE_PREFERIDO in nombres:
        return BRIDGE_PREFERIDO
    return nombres[0] if nombres else None


def red_por_defecto(bridge: str) -> InterfazRed:
    """Interfaz virtio en el bridge indicado, sin VLAN."""
    return InterfazRed(bridge=bridge, modelo=ModeloRed.VIRTIO, vlan=None)


def storage_por_defecto(storages: Sequence[Storage]) -> str | None:
    """Storage activo con ``images`` y mayor espacio libre; ``None`` si no hay."""
    candidatos = [s for s in storages if s.activo and "images" in s.contenido]
    if not candidatos:
        return None
    return max(candidatos, key=lambda s: s.libre_bytes).id


def storage_disco_por_defecto(storages: Sequence[Storage], recordado: str | None) -> str | None:
    """Storage inicial de un disco (CA-O05.5): el recordado del servidor si sigue vigente; si no,
    el de mayor espacio libre (MVP 1). La pista del perfil de MV y el valor de un lote o CSV
    se aplican por encima, en ese orden.

    Un recordado que ya no sirve no se sustituye en silencio en el resto de flujos (INV-O11): aquí
    solo se propone un valor de partida y el aviso E-O04 lo da ``origen.storages.decidir_storage``.
    """
    if recordado is not None and any(
        s.id == recordado and s.activo and "images" in s.contenido for s in storages
    ):
        return recordado
    return storage_por_defecto(storages)


def configuracion_por_defecto(
    vmid: int,
    nombre: str,
    nodo: str,
    storage: str | None,
    bridge: str | None,
) -> ConfiguracionVM:
    """Configuración inicial del formulario (sección 5).

    Con ``storage=None`` no se añade disco; con ``bridge=None`` no se añade red.
    """
    return ConfiguracionVM(
        vmid=vmid,
        nombre=nombre,
        nodo=nodo,
        firmware=Firmware.SEABIOS,
        sockets=SOCKETS,
        cores=CORES,
        tipo_cpu=TIPO_CPU,
        memoria_mib=MEMORIA_MIB,
        ballooning=None,
        con_disco=True,
        discos=[disco_por_defecto(storage)] if storage is not None else [],
        controlador_scsi=ControladorScsi.VIRTIO_SINGLE,
        redes=[red_por_defecto(bridge)] if bridge is not None else [],
        # Fase A: el formulario parte con las notas de origen marcadas (el dataclass, no).
        notas_origen=True,
    )
