"""Modelos de la arquitectura de los nodos (D2, DT-D6). Sin Qt ni importaciones de la app."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # solo para anotaciones: ``Inventario`` importa este módulo
    from proxlaunch.nucleo.modelos.inventario import Inventario


class Arquitectura(StrEnum):
    X86_64 = "x86_64"
    AARCH64 = "aarch64"
    DESCONOCIDA = "desconocida"


class FuenteArquitectura(StrEnum):
    """De dónde salió la arquitectura de un nodo (orden de detección, DT-D6)."""

    RECURSOS = "recursos"  # host-arch de /cluster/resources (9.2)
    RECURSOS_AUSENTE = "recursos_ausente"  # fila del nodo en 9.2 sin host-arch: x86_64 (LAB-D-1)
    KERNEL = "kernel"  # current-kernel.machine
    KVERSION = "kversion"
    LISTA_CPU = "lista_cpu"  # heurística
    MANUAL = "manual"  # selector avanzado (en memoria, P-D3)
    NINGUNA = "ninguna"


@dataclass(frozen=True)
class ArquitecturaNodo:
    arquitectura: Arquitectura = Arquitectura.DESCONOCIDA
    fuente: FuenteArquitectura = FuenteArquitectura.NINGUNA
    motivo: str | None = None  # "sin_permiso" | "no_responde" | "formato" (V-D04)


def arquitectura_de(inv: Inventario, nodo: str) -> Arquitectura:
    """Arquitectura tal como se detectó (``DESCONOCIDA`` si el nodo no consta)."""
    info = inv.arquitecturas.get(nodo)
    return Arquitectura.DESCONOCIDA if info is None else info.arquitectura


def arquitectura_efectiva(inv: Inventario, nodo: str) -> Arquitectura:
    """Arquitectura para decidir: ``DESCONOCIDA`` cuenta como ``X86_64`` (P-D3)."""
    arq = arquitectura_de(inv, nodo)
    return Arquitectura.X86_64 if arq == Arquitectura.DESCONOCIDA else arq
