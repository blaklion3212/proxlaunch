"""Carga de las fuentes incluidas (Open Sans y JetBrains Mono, licencia OFL)."""

from __future__ import annotations

import logging
from importlib import resources

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QFontDatabase

_log = logging.getLogger(__name__)

# Familias de respaldo del sistema si las fuentes incluidas no cargan.
FAMILIA_INTERFAZ_RESPALDO = "Sans Serif"
FAMILIA_MONO_RESPALDO = "Monospace"

_ARCHIVOS_INTERFAZ = "OpenSans-Variable.ttf"
_ARCHIVOS_MONO = "JetBrainsMono-Variable.ttf"


def _registrar(nombre_archivo: str) -> str | None:
    """Registra un TTF incluido y devuelve su familia, o ``None`` si falla."""
    try:
        recurso = resources.files("proxlaunch.recursos").joinpath("fuentes", nombre_archivo)
        datos = recurso.read_bytes()
    except (OSError, ModuleNotFoundError) as exc:
        _log.warning("No se pudo leer la fuente %s: %s", nombre_archivo, exc)
        return None
    ident = QFontDatabase.addApplicationFontFromData(QByteArray(datos))
    if ident < 0:
        _log.warning("Qt no pudo registrar la fuente %s", nombre_archivo)
        return None
    familias = QFontDatabase.applicationFontFamilies(ident)
    return familias[0] if familias else None


def cargar_fuentes() -> tuple[str, str]:
    """Registra las fuentes incluidas y devuelve ``(familia_interfaz, familia_mono)``.

    Si alguna no carga, usa una familia genérica del sistema sin lanzar excepciones.
    """
    interfaz = _registrar(_ARCHIVOS_INTERFAZ) or FAMILIA_INTERFAZ_RESPALDO
    mono = _registrar(_ARCHIVOS_MONO) or FAMILIA_MONO_RESPALDO
    _log.info("Fuentes: interfaz=%s, monoespaciada=%s", interfaz, mono)
    return interfaz, mono
