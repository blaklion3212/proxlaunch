"""«Reintentar ajustes» tras un clon PARCIAL (E-O24, RF-O21, CA-O21.x): solo con PARCIAL, UPID
propio y aviso ``ajuste_pendiente``; nunca ofrece crear otra máquina."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QPushButton

from proxlaunch.interfaz.modelos_tabla import texto_aviso_entrada
from proxlaunch.interfaz.vistas.progreso import PanelProgreso
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, ProgresoLote
from proxlaunch.nucleo.lote.ajustes import tiene_ajustes_pendientes
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.modelos.tarea import Desenlace

from .apoyo import UPID
from .apoyo_lote import entrada
from .test_lote_progreso import plan_vacio

EM = EstadoMV
AVISO = ("ajuste_pendiente:cpu_memoria,disco",)


@pytest.fixture
def panel(qtbot):
    p = PanelProgreso()
    qtbot.addWidget(p)
    p.show()
    return p


@pytest.fixture
def lote(qtbot):
    p = ProgresoLote()
    qtbot.addWidget(p)
    p.show()
    return p


# --- Una máquina ---------------------------------------------------------------------------------


def test_e_o24_el_boton_no_existe_a_la_vista_hasta_que_se_ofrece(panel):
    assert not panel.boton_reintentar_ajustes.isVisible()


def test_e_o24_ofrecerlo_lo_muestra_con_su_texto_y_emite_la_senal(panel, qtbot):
    panel.mostrar_resultado("Clon creado, faltan ajustes", Desenlace.PARCIAL, UPID)
    panel.ofrecer_reintentar_ajustes(True)
    assert panel.boton_reintentar_ajustes.isVisible()
    assert panel.boton_reintentar_ajustes.text() == "Reintentar ajustes"
    assert panel.boton_reintentar_ajustes.toolTip()
    with qtbot.waitSignal(panel.reintentar_ajustes_solicitado, timeout=500):
        panel.boton_reintentar_ajustes.click()


def test_e_o24_reiniciar_el_panel_oculta_el_boton(panel):
    panel.ofrecer_reintentar_ajustes(True)
    panel.reiniciar()
    assert not panel.boton_reintentar_ajustes.isVisible()


def test_e_o24_ofrecer_false_lo_oculta(panel):
    panel.ofrecer_reintentar_ajustes(True)
    panel.ofrecer_reintentar_ajustes(False)
    assert not panel.boton_reintentar_ajustes.isVisible()


def test_e_o24_con_el_resultado_parcial_sigue_estando_el_deshacer(panel):
    panel.mostrar_resultado("Faltan ajustes", Desenlace.PARCIAL, UPID)
    assert panel.boton_deshacer.isVisible()


# --- Regla de núcleo que decide cuándo se ofrece -----------------------------------------------


def test_solo_un_parcial_enviado_con_upid_y_aviso_tiene_ajustes_pendientes():
    assert tiene_ajustes_pendientes(entrada(0, EM.PARCIAL, upid=UPID, avisos=AVISO))
    assert not tiene_ajustes_pendientes(entrada(0, EM.PARCIAL, upid=UPID))  # sin aviso
    assert not tiene_ajustes_pendientes(entrada(0, EM.OK, upid=UPID, avisos=AVISO))
    assert not tiene_ajustes_pendientes(entrada(0, EM.ERROR, upid=UPID, avisos=AVISO))
    assert not tiene_ajustes_pendientes(entrada(0, EM.PARCIAL, avisos=AVISO))  # sin UPID


# --- Lote ----------------------------------------------------------------------------------------


def _poner(lote, entradas):
    lote.iniciar(plan_vacio(len(entradas)))
    lote.actualizar(tuple(entradas))


def test_e_o24_el_lote_ofrece_reintentar_solo_con_clones_con_ajustes_pendientes(lote):
    _poner(
        lote,
        [
            entrada(0, EM.OK, upid=UPID),
            entrada(1, EM.PARCIAL, upid=UPID, avisos=AVISO),
            entrada(2, EM.PARCIAL, upid=UPID),
        ],
    )
    assert lote.vmids_con_ajustes_pendientes() == (102,)
    lote.establecer_fase(FaseLote.TERMINADO, con_ajustes=1)
    assert lote.boton_reintentar_ajustes.isVisible()
    assert lote.boton_reintentar_ajustes.text()


def test_e_o24_sin_ajustes_pendientes_el_lote_no_muestra_el_boton(lote):
    _poner(lote, [entrada(0, EM.OK, upid=UPID), entrada(1, EM.ERROR)])
    assert lote.vmids_con_ajustes_pendientes() == ()
    lote.establecer_fase(FaseLote.TERMINADO, con_ajustes=0)
    assert not lote.boton_reintentar_ajustes.isVisible()


def test_e_o24_el_boton_del_lote_no_aparece_mientras_el_lote_corre(lote):
    _poner(lote, [entrada(0, EM.PARCIAL, upid=UPID, avisos=AVISO)])
    lote.establecer_fase(FaseLote.EJECUTANDO, con_ajustes=1)
    assert not lote.boton_reintentar_ajustes.isVisible()


def test_e_o24_el_boton_del_lote_emite_la_senal(lote, qtbot):
    _poner(lote, [entrada(0, EM.PARCIAL, upid=UPID, avisos=AVISO)])
    lote.establecer_fase(FaseLote.TERMINADO, con_ajustes=1)
    with qtbot.waitSignal(lote.reintentar_ajustes_solicitado, timeout=500):
        lote.boton_reintentar_ajustes.click()


def test_e_o24_reintentar_ajustes_es_un_boton_distinto_de_reintentar_las_fallidas(lote):
    _poner(lote, [entrada(0, EM.PARCIAL, upid=UPID, avisos=AVISO)])
    lote.establecer_fase(FaseLote.TERMINADO, reintentables=0, con_ajustes=1)
    assert lote.boton_reintentar_ajustes is not lote.boton_reintentar
    assert not lote.boton_reintentar.isVisible()
    assert lote.boton_reintentar_ajustes.isVisible()
    botones = [b.text() for b in lote.findChildren(QPushButton) if b.isVisible()]
    assert botones.count("Reintentar ajustes") == 1


def test_e_o24_el_aviso_de_ajuste_pendiente_se_explica_sin_codigo_crudo():
    e = entrada(0, EM.PARCIAL, upid=UPID, avisos=AVISO)
    textos = [texto_aviso_entrada(a) for a in e.avisos]
    assert textos and all(t.strip() for t in textos)
    assert not any("ajuste_pendiente" in t or "cpu_memoria" in t for t in textos)
