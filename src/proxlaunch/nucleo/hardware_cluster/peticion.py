"""Claves ``hostpciN``/``usbN`` (y las que arrastran) de la petición (D3, DT-D11). Todo es puro.

Solo se emiten ``mapping=<id>`` con identificadores validados: nunca ``host=``, ``romfile``,
``legacy-igd``, ``mdev`` ni ``vendor-id``/``device-id`` (solo root o fuera de alcance, CA-D3.2.8).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from proxlaunch.nucleo.hardware_cluster.modelos import (
    MAX_INDICE_USB,
    MAX_PCI,
    MAX_USB,
    RE_ID_MAPEO,
    AsignacionPCI,
    AsignacionUSB,
    HardwareCluster,
)

# Máquina que exige ``pcie=1`` (q35) y pantalla que deja ``x-vga=1`` (ninguna).
MAQUINA_PCIE = "q35"
VGA_SIN_PANTALLA = "none"


def _id_valido(id_mapeo: str) -> str:
    """El id si cumple ``RE_ID_MAPEO``; si no, ``ValueError`` (defensa: nunca llega a la API)."""
    if not isinstance(id_mapeo, str) or RE_ID_MAPEO.fullmatch(id_mapeo) is None:
        raise ValueError("identificador de mapeo no válido")
    return id_mapeo


def valor_hostpci(a: AsignacionPCI) -> str:
    """``mapping=<id>[,pcie=1][,x-vga=1][,rombar=0][,driver=keep]`` (CA-D3.2.1)."""
    partes = [f"mapping={_id_valido(a.mapeo)}"]
    if a.pcie:
        partes.append("pcie=1")
    if a.x_vga:
        partes.append("x-vga=1")
    if not a.rombar:
        partes.append("rombar=0")
    if a.driver_keep:
        partes.append("driver=keep")
    return ",".join(partes)


def valor_usb(a: AsignacionUSB) -> str:
    """``mapping=<id>[,usb3=1]`` (CA-D3.2.2)."""
    partes = [f"mapping={_id_valido(a.mapeo)}"]
    if a.usb3:
        partes.append("usb3=1")
    return ",".join(partes)


def _es_q35(maquina: str | None) -> bool:
    """``q35`` o ``pc-q35-X.Y`` (lo que una plantilla puede traer en ``machine``)."""
    if maquina is None:
        return False
    base = maquina.split(",")[0].strip()
    return base == "q35" or base.startswith(("q35+", "pc-q35-"))


def _indices(
    libres: Sequence[int] | None,
    tope: int,
    cantidad: int,
    clave: str,
    tope_indice: int | None = None,
) -> list[int]:
    """Primeros ``cantidad`` índices libres (por defecto desde 0); ``ValueError`` si no hay.

    ``tope_indice`` (por defecto ``tope``) acota los índices admitidos de ``libres``.
    """
    limite = tope if tope_indice is None else tope_indice
    candidatos = list(range(tope)) if libres is None else [i for i in libres if 0 <= i < limite]
    if cantidad > len(candidatos):
        raise ValueError(f"no hay índices libres suficientes para {clave}")
    return candidatos[:cantidad]


def parametros_hardware(
    hw: HardwareCluster | None,
    claves_presentes: Collection[str],
    *,
    libres_pci: Sequence[int] | None = None,
    libres_usb: Sequence[int] | None = None,
    maquina_actual: str | None = None,
) -> dict[str, str]:
    """Claves de hardware del clúster, en el orden de DT-D11; ``{}`` si ``hw`` es ``None``/vacío.

    Orden: ``machine=q35`` (solo con alguna PCI ``pcie`` y si ``machine`` aún no está en
    ``claves_presentes`` ni ``maquina_actual`` ya es q35), ``vga=none`` (con ``x_vga``; sustituye
    a una ``vga`` previa, quien une los diccionarios debe dejar que esta clave gane), ``hostpci0..``
    y ``usb0..``. Crear: ``libres_*`` ausentes = índices desde 0. Clon: los índices libres de la
    plantilla. ``ValueError`` si un id no cumple ``RE_ID_MAPEO`` o no hay índices libres.
    """
    if hw is None or hw.vacio:
        return {}
    salida: dict[str, str] = {}
    necesita_q35 = any(a.pcie for a in hw.pci)
    if necesita_q35 and "machine" not in claves_presentes and not _es_q35(maquina_actual):
        salida["machine"] = MAQUINA_PCIE
    if any(a.x_vga for a in hw.pci):
        salida["vga"] = VGA_SIN_PANTALLA
    for n, a in zip(_indices(libres_pci, MAX_PCI, len(hw.pci), "hostpci"), hw.pci, strict=True):
        salida[f"hostpci{n}"] = valor_hostpci(a)
    for n, u in zip(
        _indices(libres_usb, MAX_USB, len(hw.usb), "usb", MAX_INDICE_USB), hw.usb, strict=True
    ):
        salida[f"usb{n}"] = valor_usb(u)
    return salida
