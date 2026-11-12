"""GestorTema: Automático/Oscuro/Claro y respaldo oscuro (CA-22.1, 22.2, 22.3, 22.6, P-14)."""

import logging

import pytest
from PySide6.QtCore import Qt

from proxlaunch.interfaz.tema.gestor_tema import (
    GestorTema,
    ModoTema,
    generar_qss,
    leer_plantilla,
)
from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.nucleo.persistencia.preferencias import Tema

NOMBRE_LOGGER = "proxlaunch.interfaz.tema.gestor_tema"


class _SenalFalsa:
    """Imita `colorSchemeChanged`: guarda las funciones conectadas."""

    def __init__(self):
        self.conectados = []

    def connect(self, funcion):
        self.conectados.append(funcion)

    def emitir(self, esquema):
        for funcion in self.conectados:
            funcion(esquema)


class _EstiloFalso:
    def __init__(self, esquema):
        self.esquema = esquema
        self.colorSchemeChanged = _SenalFalsa()  # noqa: N815 (nombre de la API de Qt)

    def colorScheme(self):  # noqa: N802
        if isinstance(self.esquema, Exception):
            raise self.esquema
        return self.esquema


class AppFalsa:
    """QApplication simulada: esquema del sistema controlable y hoja de estilos visible."""

    def __init__(self, esquema):
        self.estilo = _EstiloFalso(esquema)
        self.hoja = ""

    def styleHints(self):  # noqa: N802
        return self.estilo

    def setStyleSheet(self, hoja):  # noqa: N802
        self.hoja = hoja

    def cambiar_sistema(self, esquema):
        """Simula que el usuario cambia el tema del sistema con la app abierta."""
        self.estilo.esquema = esquema
        self.estilo.colorSchemeChanged.emitir(esquema)


@pytest.fixture
def plantilla():
    return leer_plantilla()


def _gestor(qapp, esquema, modo=ModoTema.AUTOMATICO):
    app = AppFalsa(esquema)
    return app, GestorTema(app, modo)


# --- CA-22.1 / CA-22.3 --------------------------------------------------------------


def test_ca22_3_el_modo_inicial_es_automatico(qapp):
    app, gestor = _gestor(qapp, Qt.ColorScheme.Dark)
    assert gestor.modo == ModoTema.AUTOMATICO


@pytest.mark.parametrize(
    ("esquema", "esperado", "tokens"),
    [
        pytest.param(Qt.ColorScheme.Dark, "oscuro", TOKENS_OSCURO, id="CA-22.1-sistema-oscuro"),
        pytest.param(Qt.ColorScheme.Light, "claro", TOKENS_CLARO, id="CA-22.1-sistema-claro"),
    ],
)
def test_ca22_1_automatico_sigue_al_sistema(qapp, plantilla, esquema, esperado, tokens):
    app, gestor = _gestor(qapp, esquema)
    assert gestor.aplicar() == esperado
    assert gestor.tema_actual == esperado
    assert app.hoja == generar_qss(plantilla, tokens)


@pytest.mark.parametrize("esquema", [Qt.ColorScheme.Dark, Qt.ColorScheme.Light])
def test_ca22_3_oscuro_ignora_el_tema_del_sistema(qapp, esquema):
    _, gestor = _gestor(qapp, esquema, ModoTema.OSCURO)
    assert gestor.aplicar() == "oscuro"


@pytest.mark.parametrize("esquema", [Qt.ColorScheme.Dark, Qt.ColorScheme.Light])
def test_ca22_3_claro_ignora_el_tema_del_sistema(qapp, esquema):
    _, gestor = _gestor(qapp, esquema, ModoTema.CLARO)
    assert gestor.aplicar() == "claro"


def test_ca22_3_los_modos_coinciden_con_los_valores_que_se_persisten():
    assert {m.value for m in ModoTema} == {t.value for t in Tema}


def test_ca22_3_establecer_modo_reaplica_el_tema(qapp, plantilla):
    app, gestor = _gestor(qapp, Qt.ColorScheme.Dark)
    gestor.aplicar()
    gestor.establecer_modo(ModoTema.CLARO)
    assert gestor.modo == ModoTema.CLARO
    assert gestor.tema_actual == "claro"
    assert app.hoja == generar_qss(plantilla, TOKENS_CLARO)


def test_ca22_3_modo_recibido_como_texto_se_acepta(qapp):
    _, gestor = _gestor(qapp, Qt.ColorScheme.Dark, "claro")
    assert gestor.modo is ModoTema.CLARO


# --- CA-22.2: cambio en vivo --------------------------------------------------------


def test_ca22_2_automatico_cambia_en_vivo_con_la_senal_del_sistema(qapp, qtbot):
    app, gestor = _gestor(qapp, Qt.ColorScheme.Dark)
    gestor.aplicar()
    with qtbot.waitSignal(gestor.tema_cambiado, timeout=1000) as espera:
        app.cambiar_sistema(Qt.ColorScheme.Light)
    assert espera.args == ["claro"]
    assert gestor.tema_actual == "claro"


@pytest.mark.parametrize("modo", [ModoTema.OSCURO, ModoTema.CLARO])
def test_ca22_2_en_modo_fijo_el_cambio_del_sistema_se_ignora(qapp, qtbot, modo):
    app, gestor = _gestor(qapp, Qt.ColorScheme.Dark, modo)
    gestor.aplicar()
    antes = gestor.tema_actual
    emisiones = []
    gestor.tema_cambiado.connect(emisiones.append)
    app.cambiar_sistema(Qt.ColorScheme.Light if antes == "oscuro" else Qt.ColorScheme.Dark)
    assert emisiones == []
    assert gestor.tema_actual == antes


def test_aplicar_emite_tema_cambiado_con_el_tema_efectivo(qapp, qtbot):
    _, gestor = _gestor(qapp, Qt.ColorScheme.Light)
    with qtbot.waitSignal(gestor.tema_cambiado, timeout=1000) as espera:
        gestor.aplicar()
    assert espera.args == ["claro"]


# --- CA-22.6 / P-14: respaldo oscuro ------------------------------------------------


def test_ca22_6_esquema_desconocido_usa_oscuro_y_lo_registra(qapp, caplog):
    _, gestor = _gestor(qapp, Qt.ColorScheme.Unknown)
    with caplog.at_level(logging.WARNING, logger=NOMBRE_LOGGER):
        assert gestor.aplicar() == "oscuro"
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_ca22_6_si_la_deteccion_lanza_una_excepcion_usa_oscuro_y_lo_registra(qapp, caplog):
    _, gestor = _gestor(qapp, RuntimeError("sin portal de escritorio"))
    with caplog.at_level(logging.WARNING, logger=NOMBRE_LOGGER):
        assert gestor.aplicar() == "oscuro"
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_ca22_6_tras_el_respaldo_el_selector_sigue_funcionando(qapp, plantilla):
    app, gestor = _gestor(qapp, Qt.ColorScheme.Unknown)
    gestor.aplicar()
    gestor.establecer_modo(ModoTema.CLARO)
    assert gestor.tema_actual == "claro"
    assert app.hoja == generar_qss(plantilla, TOKENS_CLARO)
    gestor.establecer_modo(ModoTema.OSCURO)
    assert gestor.tema_actual == "oscuro"


def test_ca22_6_el_esquema_desconocido_se_recupera_cuando_el_sistema_responde(qapp, qtbot):
    app, gestor = _gestor(qapp, Qt.ColorScheme.Unknown)
    gestor.aplicar()
    app.cambiar_sistema(Qt.ColorScheme.Light)
    assert gestor.tema_actual == "claro"


# --- Con una QApplication real ------------------------------------------------------


def test_aplicar_sobre_la_qapplication_real_instala_la_hoja(qapp):
    anterior = qapp.styleSheet()
    try:
        gestor = GestorTema(qapp, ModoTema.CLARO)
        gestor.aplicar()
        assert qapp.styleSheet() == generar_qss(leer_plantilla(), TOKENS_CLARO)
        gestor.establecer_modo(ModoTema.OSCURO)
        assert qapp.styleSheet() == generar_qss(leer_plantilla(), TOKENS_OSCURO)
    finally:
        qapp.setStyleSheet(anterior)


def test_con_qapplication_real_y_esquema_del_sistema_resuelve_un_tema_valido(qapp):
    gestor = GestorTema(qapp, ModoTema.AUTOMATICO)
    try:
        assert gestor.aplicar() in {"oscuro", "claro"}
    finally:
        qapp.setStyleSheet("")
