"""``main()`` y la captura de fallos (C4) y línea de arranque con ``platform.version()`` (C13).

``main`` no se puede ejecutar de verdad sin abrir ventanas: se sustituyen ``Rutas``, el registro,
la captura y ``QApplication`` por dobles que anotan el orden de las llamadas y detienen el
arranque justo después de crear la aplicación.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

import pytest

from proxlaunch.interfaz import app as app_mod
from proxlaunch.nucleo.persistencia.rutas import Rutas
from proxlaunch.nucleo.registro import (
    ARCHIVO_LOG,
    cerrar_registro,
    configurar_registro,
    desinstalar_captura_de_fallos,
)


class _ArranqueDetenido(Exception):
    """Señal de que ``main`` llegó a crear ``QApplication`` (y no se sigue adelante)."""


@pytest.fixture
def hooks_intactos():
    """Restaura hooks y captura al terminar, pase lo que pase dentro de la prueba."""
    originales = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    desinstalar_captura_de_fallos()
    yield originales
    desinstalar_captura_de_fallos()
    cerrar_registro()
    sys.excepthook, threading.excepthook, sys.unraisablehook = originales


@pytest.fixture
def arranque(monkeypatch, tmp_path, hooks_intactos):
    """Dobles de ``main``: anotan el orden de llamadas y cortan al crear ``QApplication``."""
    llamadas: list[str] = []
    rutas = Rutas(tmp_path / "datos")

    monkeypatch.setattr(app_mod, "Rutas", lambda *a, **k: rutas)
    configurar_real = app_mod.configurar_registro

    def configurar(directorio, *a, **k):
        llamadas.append("configurar_registro")
        return configurar_real(directorio, *a, **k)

    monkeypatch.setattr(app_mod, "configurar_registro", configurar)

    class FalsaQGui:
        @staticmethod
        def setHighDpiScaleFactorRoundingPolicy(*_a):
            llamadas.append("QGuiApplication.setHighDpi")

    class FalsaQApplication:
        @staticmethod
        def instance():
            llamadas.append("QApplication.instance")
            return None

        def __new__(cls, *_a, **_k):
            llamadas.append("QApplication()")
            raise _ArranqueDetenido

    monkeypatch.setattr(app_mod, "QGuiApplication", FalsaQGui)
    monkeypatch.setattr(app_mod, "QApplication", FalsaQApplication)

    class Contexto:
        pass

    ctx = Contexto()
    ctx.llamadas = llamadas
    ctx.rutas = rutas
    ctx.monkeypatch = monkeypatch
    return ctx


def _espiar_captura(ctx, *, lanza: Exception | None = None):
    from proxlaunch.nucleo import registro

    real = registro.instalar_captura_de_fallos
    recibido: dict = {}

    def instalar(directorio, instalar_qt=None):
        ctx.llamadas.append("instalar_captura_de_fallos")
        recibido["directorio"] = Path(directorio)
        recibido["instalador"] = instalar_qt
        if lanza is not None:
            raise lanza
        return real(directorio, instalar_qt)

    ctx.monkeypatch.setattr(app_mod, "instalar_captura_de_fallos", instalar)
    return recibido


# --- C4 ------------------------------------------------------------------------------------


def test_c4_el_registro_y_la_captura_se_instalan_antes_de_crear_qapplication(arranque):
    recibido = _espiar_captura(arranque)
    with pytest.raises(_ArranqueDetenido):
        app_mod.main(["proxlaunch"])
    llamadas = arranque.llamadas
    assert llamadas.index("configurar_registro") < llamadas.index("instalar_captura_de_fallos")
    assert llamadas.index("instalar_captura_de_fallos") < llamadas.index("QApplication()")
    assert llamadas.index("instalar_captura_de_fallos") < llamadas.index("QApplication.instance")
    assert recibido["directorio"] == arranque.rutas.directorio_log
    assert recibido["instalador"] is app_mod.instalar_mensajes_qt


def test_c4_la_captura_queda_instalada_cuando_se_crea_qapplication(arranque):
    _espiar_captura(arranque)
    estado: dict = {}
    from proxlaunch.nucleo import registro

    fabrica = app_mod.QApplication

    class Observadora(fabrica):
        def __new__(cls, *a, **k):
            estado["hook_instalado"] = sys.excepthook is getattr(registro._estado, "hook_sys", None)
            return super().__new__(cls, *a, **k)

    arranque.monkeypatch.setattr(app_mod, "QApplication", Observadora)
    with pytest.raises(_ArranqueDetenido):
        app_mod.main(["proxlaunch"])
    assert estado["hook_instalado"] is True


def test_c4_si_instalar_la_captura_lanza_main_continua_y_avisa(arranque):
    _espiar_captura(arranque, lanza=RuntimeError("captura-rota"))
    with pytest.raises(_ArranqueDetenido):  # llegó a crear QApplication: no abortó antes
        app_mod.main(["proxlaunch"])
    assert "QApplication()" in arranque.llamadas
    registro_texto = (arranque.rutas.directorio_log / ARCHIVO_LOG).read_text("utf-8")
    assert "No se pudo instalar la captura de fallos" in registro_texto
    assert "captura-rota" in registro_texto


def test_c4_la_prueba_de_humo_no_instala_la_captura(arranque, monkeypatch):
    from proxlaunch.interfaz import humo

    _espiar_captura(arranque)
    monkeypatch.setattr(humo, "ejecutar_prueba_de_humo", lambda *a, **k: 0)
    antes = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    assert app_mod.main(["proxlaunch", "--prueba-de-humo"]) == 0
    assert (sys.excepthook, threading.excepthook, sys.unraisablehook) == antes
    assert "instalar_captura_de_fallos" not in arranque.llamadas
    assert "configurar_registro" not in arranque.llamadas
    assert "QApplication()" not in arranque.llamadas


def test_c4_version_tampoco_instala_la_captura(arranque, capsys):
    _espiar_captura(arranque)
    antes = sys.excepthook
    assert app_mod.main(["proxlaunch", "--version"]) == 0
    assert sys.excepthook is antes
    assert arranque.llamadas == []


# --- C13 -----------------------------------------------------------------------------------


@pytest.fixture
def log_arranque(tmp_path, hooks_intactos):
    carpeta = tmp_path / "log"
    configurar_registro(carpeta)
    yield carpeta


def test_c13_registrar_arranque_incluye_platform_version(log_arranque, qapp, monkeypatch):
    monkeypatch.setattr(app_mod.platform, "version", lambda: "VERSION-DEL-SO-c13")
    app_mod.registrar_arranque()
    lineas = [
        ln
        for ln in (log_arranque / ARCHIVO_LOG).read_text("utf-8").splitlines()
        if "Arranque" in ln
    ]
    assert len(lineas) == 1
    assert "VERSION-DEL-SO-c13" in lineas[0]
    assert " INFO " in lineas[0]


def test_c13_la_version_real_del_so_aparece_en_la_linea(log_arranque, qapp):
    import platform

    app_mod.registrar_arranque()
    linea = next(
        ln
        for ln in (log_arranque / ARCHIVO_LOG).read_text("utf-8").splitlines()
        if "Arranque" in ln
    )
    assert platform.version() in linea
    assert platform.release() in linea
    assert logging.getLevelName(logging.INFO) in linea
