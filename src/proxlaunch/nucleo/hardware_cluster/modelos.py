"""Modelos del hardware del clúster (D3, 0.9): mapeos PCI/USB y modelos de CPU. Sin Qt.

Los datos del servidor no son confiables: quien los lee los sanea (identificadores con
``RE_ID_MAPEO``, textos sin control ni invisibles) antes de construir estos objetos.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from proxlaunch.nucleo.errores import ErrorProxLaunch

RE_ID_MAPEO: Final = re.compile(r"[A-Za-z0-9._-]{1,64}")  # se usa con fullmatch
MAX_PCI: Final = 16
MAX_USB: Final = 5  # P-D17 (tope de dispositivos propios)
MAX_INDICE_USB: Final = 14  # Proxmox admite usb0..usb13: los índices libres miran los 14


class TipoMapeo(StrEnum):
    PCI = "pci"
    USB = "usb"


@dataclass(frozen=True)
class AsignacionPCI:
    mapeo: str
    pcie: bool = False
    x_vga: bool = False
    rombar: bool = True  # False -> rombar=0
    driver_keep: bool = False  # driver=keep (9.1, V-D60)


@dataclass(frozen=True)
class AsignacionUSB:
    mapeo: str
    usb3: bool = False


@dataclass(frozen=True)
class HardwareCluster:
    pci: tuple[AsignacionPCI, ...] = ()
    usb: tuple[AsignacionUSB, ...] = ()

    @property
    def vacio(self) -> bool:
        return not self.pci and not self.usb


@dataclass(frozen=True)
class EntradaMapeo:
    """Una línea ``map[]`` de un mapeo (saneada)."""

    nodo: str
    descripcion: str = ""  # ≤ 256, sin control


@dataclass(frozen=True)
class Mapeo:
    tipo: TipoMapeo
    id: str  # validado con RE_ID_MAPEO; los inválidos se descartan al leer
    descripcion: str  # saneada ≤ 256
    entradas: tuple[EntradaMapeo, ...]
    mdev: bool = False
    migrable_en_vivo: bool = False  # live-migration-capable

    def nodos(self) -> frozenset[str]:
        """Nodos en los que el mapeo tiene al menos un dispositivo."""
        return frozenset(e.nodo for e in self.entradas)

    def dispositivos_en(self, nodo: str) -> int:
        """Cantidad de dispositivos del mapeo en ese nodo."""
        return sum(1 for e in self.entradas if e.nodo == nodo)


@dataclass(frozen=True)
class ModeloCpu:
    nombre: str  # p. ej. "custom-gamer"
    personalizado: bool
    fabricante: str = ""


@dataclass(frozen=True)
class ComprobacionNodo:
    """Respuesta de ``?check-node=``."""

    mapeo: str
    nodo: str
    errores: tuple[str, ...]  # mensajes saneados ≤ 256
    tipo: TipoMapeo = TipoMapeo.PCI  # un mismo id puede existir como PCI y como USB


@dataclass(frozen=True)
class InfoHardwareCluster:
    mapeos: tuple[Mapeo, ...] | None = None  # None = no leídos
    error_mapeos: ErrorProxLaunch | None = None  # V-D50 «no pude leer»
    comprobaciones: tuple[ComprobacionNodo, ...] = ()
    errores_comprobacion: tuple[tuple[str, str, str], ...] = ()  # (tipo, mapeo, nodo) fallidos
    cpus: Mapping[str, tuple[ModeloCpu, ...]] = field(default_factory=dict)  # por nodo leído
    errores_cpu: Mapping[str, ErrorProxLaunch] = field(default_factory=dict)  # V-D62
