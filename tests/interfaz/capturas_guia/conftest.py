"""Configuración del generador de capturas de la guía de usuario.

Todo lo de este directorio solo corre con ``-m capturas`` (se descarta de la recolección en
cualquier otro caso, incluida la suite normal ``-m "not integracion"``).

Las capturas deben parecerse a la aplicación real, así que aquí se repite lo que hace
``interfaz/app.py``: fuentes propias, texto de 13 px, tema CLARO, icono y traductor, sobre una
pantalla virtual de 1920x1080 a 96 DPI (la de ``offscreen`` por defecto mide 800x800 y
recortaría las ventanas).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QImage
from PySide6.QtWidgets import QApplication, QWidget

from proxlaunch.interfaz.app import cargar_traductor, crear_icono
from proxlaunch.interfaz.fuentes import cargar_fuentes
from proxlaunch.interfaz.tema import GestorTema, ModoTema
from proxlaunch.interfaz.ventana_principal import Dependencias
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.persistencia.preferencias import RepositorioPreferencias
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.reloj import RelojSimulado

RAIZ = Path(__file__).resolve().parents[3]
CARPETA_IMAGENES = RAIZ / "docs" / "img"
PANTALLA = {
    "screens": [
        {
            "name": "guia",
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "logicalDpi": 96,
            "logicalBaseDpi": 96,
            "dpr": 1,
            "physicalSize": [508, 286],
        }
    ]
}


def _seleccionado_por_marca(config) -> bool:
    """¿La expresión ``-m`` elige las capturas y no las elegiría sin la marca?"""
    expresion = (config.option.markexpr or "").strip()
    if not expresion:
        return False
    from _pytest.mark.expression import Expression

    compilada = Expression.compile(expresion)
    return compilada.evaluate(lambda nombre, **_: nombre == "capturas") and not (
        compilada.evaluate(lambda nombre, **_: False)
    )


def pytest_collection_modifyitems(config, items):
    """Las capturas solo se recolectan con ``-m capturas``; en cualquier otro caso se descartan."""
    if _seleccionado_por_marca(config):
        return
    propios = [i for i in items if "capturas_guia" in Path(str(i.fspath)).parts]
    if not propios:
        return
    config.hook.pytest_deselected(items=propios)
    items[:] = [i for i in items if i not in propios]


@pytest.fixture(scope="session")
def qapp(qapp_args, pytestconfig):
    """QApplication sobre la pantalla virtual de 1920x1080 (sustituye la de pytest-qt)."""
    existente = QApplication.instance()
    if existente is not None:
        return existente
    carpeta = Path(tempfile.mkdtemp(prefix="proxlaunch-pantalla-"))
    config = carpeta / "pantalla.json"
    config.write_text(json.dumps(PANTALLA), encoding="utf-8")
    os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={config}"
    os.environ["QT_SCALE_FACTOR"] = "1"
    # Zona horaria fija: las fechas visibles no dependen de la máquina que genera las imágenes.
    os.environ["TZ"] = "UTC"
    time.tzset()
    app = QApplication(list(qapp_args))
    app.setApplicationName("ProxLaunch")
    return app


@pytest.fixture(scope="session")
def apariencia(qapp, tmp_path_factory):
    """Fuentes, tamaño de texto, icono, traductor y tema claro, como en ``app.py``."""
    qapp.setWindowIcon(crear_icono())
    familia, _mono = cargar_fuentes()
    fuente = QFont(familia)
    fuente.setPixelSize(13)
    qapp.setFont(fuente)
    cargar_traductor(qapp)
    gestor = GestorTema(qapp, ModoTema.CLARO, directorio_iconos=tmp_path_factory.mktemp("iconos"))
    gestor.aplicar()
    return gestor


class RelojCalendarioFijo:
    """Calendario fijo (10 de marzo de 2025, 12:00 UTC) para las notas de origen."""

    def ahora(self) -> datetime:
        return datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def deps(qapp, apariencia, rutas, llavero, servicio_falso):
    """Dependencias de las pruebas, pero con el tema claro ya aplicado y reloj simulado."""
    return Dependencias(
        servicio_conexion=servicio_falso,  # type: ignore[arg-type]
        perfiles=RepositorioPerfiles(rutas.perfiles),
        huellas=RepositorioHuellas(rutas.huellas),
        secretos=AlmacenSecretos(backend=llavero),
        preferencias=RepositorioPreferencias(rutas.preferencias),
        reloj=RelojSimulado(),
        reloj_calendario=RelojCalendarioFijo(),
        gestor_tema=apariencia,
        directorio_informes=rutas.directorio_datos / "informes",
        directorio_lotes=rutas.lotes,
    )


def guardar_imagen(imagen, nombre: str) -> Path:
    """Escribe un PNG en ``docs/img`` sin canal alfa y con la máxima compresión."""
    CARPETA_IMAGENES.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA_IMAGENES / f"{nombre}.png"
    plana = imagen.toImage().convertToFormat(QImage.Format.Format_RGB888)
    if not plana.save(str(ruta), "PNG", 0):
        raise AssertionError(f"No se pudo escribir {ruta}")
    return ruta


@pytest.fixture
def guardar(qapp, apariencia) -> Callable[..., Path]:
    """Guarda ``widget.grab()`` en ``docs/img/<nombre>.png`` y devuelve la ruta."""

    def _guardar(widget: QWidget, nombre: str) -> Path:
        qapp.processEvents()
        return guardar_imagen(widget.grab(), nombre)

    return _guardar


@pytest.fixture(autouse=True)
def _identificadores_fijos(monkeypatch):
    """El identificador de lote (4 bytes aleatorios) sale en etiquetas e informes: se fija."""
    import secrets

    original = secrets.token_hex
    monkeypatch.setattr(secrets, "token_hex", lambda n=None: "a1b2c3d4" if n == 4 else original(n))
