"""Integración de la captura de fallos con Qt: manejador de mensajes y línea de arranque."""

from __future__ import annotations

import getpass
import logging
import socket
import sys
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QtMsgType, qInstallMessageHandler, qWarning

from proxlaunch.interfaz import app
from proxlaunch.nucleo.registro import (
    ARCHIVO_LOG,
    cerrar_registro,
    configurar_registro,
    desinstalar_captura_de_fallos,
    instalar_captura_de_fallos,
)


@pytest.fixture
def carpeta(tmp_path):
    originales = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    desinstalar_captura_de_fallos()
    ruta = tmp_path / "log"
    configurar_registro(ruta)
    yield ruta
    desinstalar_captura_de_fallos()
    cerrar_registro()
    sys.excepthook, threading.excepthook, sys.unraisablehook = originales


def _log(carpeta: Path) -> str:
    return (carpeta / ARCHIVO_LOG).read_text(encoding="utf-8")


# --- R9 ---------------------------------------------------------------------------------


def test_r9_registrar_arranque_una_linea_info_con_versiones(carpeta, qapp):
    app.registrar_arranque()
    lineas = [ln for ln in _log(carpeta).splitlines() if "Arranque" in ln]
    assert len(lineas) == 1
    linea = lineas[0]
    assert " INFO " in linea
    assert app.__version__ in linea
    assert "Python" in linea
    assert "Qt " in linea
    assert "PySide6" in linea
    import platform

    assert platform.system() in linea


def test_r9_registrar_arranque_no_filtra_datos_personales(carpeta, qapp):
    app.registrar_arranque()
    texto = _log(carpeta)
    usuario = getpass.getuser()
    host = socket.gethostname()
    inicio = str(Path.home())
    # Se comprueba sobre la línea de arranque (la fecha/ruta temporal no aplica).
    linea = next(ln for ln in texto.splitlines() if "Arranque" in ln)
    if len(usuario) > 2:
        assert usuario not in linea
    assert inicio not in linea
    if len(host) > 2:
        assert host not in linea


# --- R10 --------------------------------------------------------------------------------


def test_r10_qwarning_llega_al_log_y_se_restaura_el_manejador(carpeta, qapp):
    recibidos = []

    def previo(tipo, contexto, mensaje):
        recibidos.append(mensaje)

    anterior = qInstallMessageHandler(previo)
    try:
        instalar_captura_de_fallos(carpeta, app.instalar_mensajes_qt)
        qWarning("aviso-desde-qt-prueba")
        texto = _log(carpeta)
        assert "WARNING proxlaunch.qt" in texto
        assert "aviso-desde-qt-prueba" in texto
        assert recibidos == []  # el manejador de la captura sustituyó al previo

        desinstalar_captura_de_fallos()
        qWarning("tras-restaurar")
        assert recibidos == ["tras-restaurar"]
        assert "tras-restaurar" not in _log(carpeta)
    finally:
        qInstallMessageHandler(anterior)


def test_r10_la_funcion_devuelta_revierte_el_manejador(qapp):
    recibidos = []
    anterior = qInstallMessageHandler(lambda t, c, m: recibidos.append(m))
    try:
        revertir = app.instalar_mensajes_qt(lambda nivel, cat, msg: None)
        qWarning("capturado")
        assert recibidos == []
        revertir()
        qWarning("restaurado")
        assert recibidos == ["restaurado"]
    finally:
        qInstallMessageHandler(anterior)


@pytest.mark.parametrize(
    ("tipo", "nivel"),
    [
        (QtMsgType.QtDebugMsg, logging.DEBUG),
        (QtMsgType.QtInfoMsg, logging.DEBUG),
        (QtMsgType.QtWarningMsg, logging.WARNING),
        (QtMsgType.QtCriticalMsg, logging.ERROR),
    ],
)
def test_r10_niveles_de_qt_mapeados(qapp, tipo, nivel):
    from PySide6.QtCore import qCritical, qDebug, qInfo

    emisor = {
        QtMsgType.QtDebugMsg: qDebug,
        QtMsgType.QtInfoMsg: qInfo,
        QtMsgType.QtWarningMsg: qWarning,
        QtMsgType.QtCriticalMsg: qCritical,
    }[tipo]
    vistos = []
    anterior = qInstallMessageHandler(None)
    qInstallMessageHandler(anterior)
    try:
        revertir = app.instalar_mensajes_qt(lambda n, c, m: vistos.append((n, m)))
        emisor("msg-nivel")
        revertir()
    finally:
        qInstallMessageHandler(anterior)
    assert (nivel, "msg-nivel") in vistos
