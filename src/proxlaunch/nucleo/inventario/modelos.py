"""Modelos del inventario de lotes (RF-C1.2..RF-C1.9). Datos inmutables, sin E/S."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final

from proxlaunch.nucleo.modelos.inventario import RecursoVM

# Lecturas ``GET config`` simultáneas como máximo en todo el inventario (RF-C1.12).
MAX_LECTURAS_INVENTARIO: Final = 4
# Un código de lote de ProxLaunch son 8 caracteres hexadecimales en minúsculas (S-C4).
RE_CODIGO_LOTE: Final = re.compile(r"^[0-9a-f]{8}\Z")


class MotivoNoDeshacible(StrEnum):
    """Por qué una MV no se puede deshacer desde el inventario (RF-C1.9)."""

    CODIGO_INVALIDO = "codigo_invalido"  # V-C02
    FALTA_ETIQUETA = "falta_etiqueta"  # V-C03 (params["falta"])
    SIN_NOTA = "sin_nota"  # V-C04
    NOTA_OTRO_LOTE = "nota_otro_lote"  # V-C04 (params["otro"])
    PLANTILLA = "plantilla"  # V-C05
    BLOQUEADA = "bloqueada"  # V-C05 (params["bloqueo"])
    ESTADO_DESCONOCIDO = "estado_desconocido"  # V-C05
    CONFIG_ILEGIBLE = "config_ilegible"  # V-C05
    NODO_SIN_RESPUESTA = "nodo_sin_respuesta"  # V-C05 (params["nodo"])
    YA_NO_EXISTE = "ya_no_existe"  # V-C05
    SIN_PERMISO_BORRAR = "sin_permiso_borrar"  # V-C08
    SIN_DETALLE = "sin_detalle"  # aún no leída (o lectura cancelada)


class EstadoNota(StrEnum):
    COINCIDE = "coincide"
    FALTA = "falta"
    OTRO_LOTE = "otro_lote"


@dataclass(frozen=True)
class NotaOrigen:
    """Lo único que se conserva de la nota de la MV: nunca el texto completo (CA-C1.3.5)."""

    estado: EstadoNota
    lote: str | None = None
    fecha: datetime | None = None


@dataclass(frozen=True)
class LoteServidor:
    codigo: str  # en minúsculas
    valido: bool  # cumple RE_CODIGO_LOTE
    de_proxlaunch: bool  # alguna MV lleva también la etiqueta "proxlaunch"
    recursos: tuple[RecursoVM, ...]  # solo tipo qemu, ordenados por vmid


@dataclass(frozen=True)
class ListaLotes:
    lotes: tuple[LoteServidor, ...]  # ordenados por código
    total_visibles: int  # MVs qemu visibles (0 -> V-C01)


@dataclass(frozen=True)
class MVInventario:
    recurso: RecursoVM
    protegida: bool | None
    nota: NotaOrigen | None  # None = no leída
    motivos: tuple[MotivoNoDeshacible, ...]
    params: Mapping[str, str] = field(default_factory=dict)

    @property
    def deshacible(self) -> bool:
        return not self.motivos


@dataclass(frozen=True)
class DetalleLote:
    lote: LoteServidor
    maquinas: tuple[MVInventario, ...]
    fecha: datetime | None  # la más antigua de las notas que coinciden
    completo: bool  # False si se canceló a mitad


class EstadoIpInventario(StrEnum):
    OK = "ok"
    APAGADA = "apagada"
    SIN_AGENTE = "sin_agente"
    SIN_RESPUESTA = "sin_respuesta"
    SIN_PERMISO = "sin_permiso"
    SIN_IP = "sin_ip"


@dataclass(frozen=True)
class IpInventario:
    estado: EstadoIpInventario
    ip: str | None = None
