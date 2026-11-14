"""Modelos de los lotes guardados (docs/arquitectura/mvp3.md §3.4)."""

from dataclasses import dataclass

from proxlaunch.nucleo.archivos.esquema import AvisoArchivo
from proxlaunch.nucleo.lote.modelos import DefinicionLote


@dataclass(frozen=True)
class LoteGuardado:
    """Definición reutilizable de un lote. Sin plan, VMIDs reservados, libro, host ni usuario."""

    nombre: str  # V-M01 sin unicidad
    definicion: DefinicionLote  # ``politica_thin`` no se guarda: al leer, valor por defecto
    version_proxmox: str | None = None  # informativo (CA-G04.6); nunca host ni perfil


@dataclass(frozen=True)
class ArchivoLote:
    lote: LoteGuardado
    version_original: int
    avisos: tuple[AvisoArchivo, ...] = ()
