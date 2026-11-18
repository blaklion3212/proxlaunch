"""Iconos SVG del tema (flechas y palomita) generados con los colores del tema activo.

Qt no dibuja flechas en ``QComboBox``/``QSpinBox`` cuando la hoja de estilos redefine sus
subcontroles, así que se entregan como imágenes. Se escriben en la carpeta de caché de la app
con nombres deterministas (llevan el color): reescribir el mismo tema no acumula archivos.
Si no se puede escribir, ``generar_iconos`` devuelve ``{}`` y la app sigue sin iconos.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from pathlib import Path

from proxlaunch.nucleo.persistencia.rutas import crear_carpeta_privada

_log = logging.getLogger(__name__)

_CABECERA = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n}" height="{n}">'
)

# (token del marcador en la plantilla, nombre base, token de color, forma SVG con {c} = color)
_FLECHA_ABAJO = '<path d="M1 3 L9 3 L5 7.5 Z" fill="{c}"/>'
_FLECHA_ARRIBA = '<path d="M1 7 L9 7 L5 2.5 Z" fill="{c}"/>'
_PALOMITA = (
    '<path d="M3.2 7.4 L6 10.1 L10.8 4.1" fill="none" stroke="{c}" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
)

_DES = "texto_deshabilitado"
_ICONOS: tuple[tuple[str, str, str, int, str], ...] = (
    ("icono_flecha_abajo", "flecha_abajo", "texto_secundario", 10, _FLECHA_ABAJO),
    ("icono_flecha_arriba", "flecha_arriba", "texto_secundario", 10, _FLECHA_ARRIBA),
    ("icono_flecha_abajo_deshabilitada", "flecha_abajo", _DES, 10, _FLECHA_ABAJO),
    ("icono_flecha_arriba_deshabilitada", "flecha_arriba", _DES, 10, _FLECHA_ARRIBA),
    ("icono_palomita", "palomita", "acento_texto", 14, _PALOMITA),
    ("icono_palomita_deshabilitada", "palomita", _DES, 14, _PALOMITA),
)


def _svg(tamano: int, forma: str, color: str) -> str:
    return _CABECERA.format(n=tamano) + forma.format(c=color) + "</svg>\n"


def _escribir(ruta: Path, contenido: str) -> None:
    """Escribe de forma atómica; no toca el archivo si ya tiene el mismo contenido.

    El temporal lleva nombre único (dos instancias no se pisan) y se limpia siempre. Si el
    reemplazo falla pero el destino ya tiene el contenido esperado, se considera éxito.
    """
    esperado = contenido.encode("utf-8")
    try:
        # Se compara en bytes: un archivo corrupto (no UTF-8) no debe lanzar al decodificar.
        if ruta.read_bytes() == esperado:
            return
    except OSError:
        pass
    descriptor, nombre = tempfile.mkstemp(dir=ruta.parent, suffix=".tmp")
    temporal = Path(nombre)
    try:
        with os.fdopen(descriptor, "wb") as flujo:
            flujo.write(esperado)
        try:
            os.replace(temporal, ruta)
        except OSError:
            # En Windows el destino puede estar abierto por otra instancia con el mismo contenido.
            try:
                if ruta.read_bytes() == esperado:
                    return
            except OSError:
                pass
            raise
    finally:
        with contextlib.suppress(OSError):
            temporal.unlink()


def _ruta_apta_para_qss(carpeta: Path) -> bool:
    """False si la ruta tiene ``"``, ``\\`` o caracteres de control (romperían ``url("...")``)."""
    texto = carpeta.as_posix()
    return not any(c in '"\\' or ord(c) < 32 or 0x7F <= ord(c) <= 0x9F for c in texto)


def generar_iconos(tokens: dict[str, str], carpeta: Path) -> dict[str, str]:
    """Escribe los SVG del tema en ``carpeta`` y devuelve ``{marcador: ruta posix}``.

    Los iconos son decorativos: ante cualquier fallo (carpeta no escribible, archivo corrupto,
    ruta con caracteres que romperían la hoja de estilos...) registra un aviso y devuelve ``{}``
    para que la app arranque igualmente sin iconos.
    """
    try:
        if not _ruta_apta_para_qss(carpeta):
            _log.warning("La ruta de caché contiene caracteres no admitidos; sin iconos del tema")
            return {}
        crear_carpeta_privada(carpeta)
        rutas: dict[str, str] = {}
        for marcador, base, token_color, tamano, forma in _ICONOS:
            color = tokens[token_color]
            ruta = carpeta / f"{base}_{color.lstrip('#').lower()}.svg"
            _escribir(ruta, _svg(tamano, forma, color))
            if not _ruta_apta_para_qss(ruta):
                _log.warning("La ruta de un icono contiene caracteres no admitidos; sin iconos")
                return {}
            rutas[marcador] = ruta.as_posix()
        return rutas
    except Exception as exc:  # noqa: BLE001 - los iconos nunca deben impedir arrancar
        _log.warning("No se pudieron escribir los iconos del tema en %s: %s", carpeta, exc)
        return {}
