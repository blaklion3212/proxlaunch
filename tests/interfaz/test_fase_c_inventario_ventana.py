"""Ventana principal con «Lotes en el servidor» (fase C, C1): acción de menú, convivencia con el
lote de la sesión y cambio de servidor.

Requisitos: CA-C1.1.1, RF-C1.10 (CA-C1.10.1 a CA-C1.10.3), RF-C1.14 (CA-C1.14.1) y la
confirmación al cerrar con un borrado en curso. Cliente: el real sobre un clúster en memoria.
"""

from __future__ import annotations

import threading

import pytest
from shiboken6 import isValid

from nucleo.apoyo_fase_c_inventario import CODIGO, Mundo
from nucleo.apoyo_lote import NORMAL
from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.inventario_lotes import (
    DialogoConfirmarCodigoLote,
    DialogoInventarioLotes,
)
from proxlaunch.interfaz.textos_inventario import (
    texto_lote_abierto_en_sesion,
    texto_lote_en_deshacer_inventario,
    texto_sin_conexion_inventario,
    texto_sin_version_inventario,
)

from . import test_ventana_principal as _base
from .apoyo import perfil, sesion_falsa
from .apoyo_fase_a import ClienteDeshacerFalso, lote_creado
from .apoyo_ventana_lote import Confirmaciones

entorno = _base.entorno
conectar = _base.conectar


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Cierra sin bloquear ni preguntar (cada prueba cambia ``confirmar`` si lo necesita)."""


def _mundo(*vmids: int, codigo: str = CODIGO, nodos=("pve1",)) -> Mundo:
    m = Mundo(nodos)
    for vmid in vmids:
        m.cluster.agregar_mv(vmid, lote=codigo)
    return m


def _abrir(qtbot, v) -> DialogoInventarioLotes:
    v._accion_inventario.trigger()
    dialogo = v._dialogo_inventario
    assert dialogo is not None
    qtbot.waitUntil(lambda: not dialogo.boton_cancelar_lectura.isVisibleTo(dialogo), timeout=8000)
    return dialogo


def _elegir(qtbot, dialogo, codigo: str = CODIGO) -> None:
    tabla = dialogo.tabla_lotes
    fila = next(f for f in range(tabla.rowCount()) if tabla.item(f, 0).text() == codigo)
    tabla.selectRow(fila)
    qtbot.waitUntil(lambda: not dialogo.boton_cancelar_lectura.isVisibleTo(dialogo), timeout=8000)


def _cerrado(dialogo) -> bool:
    """El diálogo ya no se ve (o ya se destruyó con ``deleteLater``)."""
    return not isValid(dialogo) or not dialogo.isVisible()


def _borrar_con_codigo(qtbot, dialogo, codigo: str = CODIGO) -> None:
    dialogo.boton_deshacer.click()
    qtbot.waitUntil(lambda: bool(dialogo.findChildren(DialogoConfirmarCodigoLote)), timeout=8000)
    confirmar = dialogo.findChildren(DialogoConfirmarCodigoLote)[-1]
    confirmar.campo.setText(codigo)
    confirmar.boton_borrar.click()


# --- CA-C1.1.1: acción de menú ------------------------------------------------------------------


def test_ca_c1_1_1_sin_conexion_la_accion_esta_deshabilitada_con_el_motivo(entorno):
    v = entorno.ventana
    assert not v._accion_inventario.isEnabled()
    assert v._accion_inventario.toolTip() == texto_sin_conexion_inventario()
    assert v._accion_inventario.statusTip() == texto_sin_conexion_inventario()
    assert "Lotes en el servidor" in v._accion_inventario.text()


def test_ca_c1_1_1_con_conexion_la_accion_esta_habilitada_y_sin_ella_otra_vez_no(qtbot, entorno):
    v = entorno.ventana
    m = _mundo(101)
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    assert v._accion_inventario.isEnabled() and v._accion_inventario.statusTip() == ""
    assert v._accion_inventario.toolTip() != texto_sin_conexion_inventario()
    v._cerrar_sesion()
    assert not v._accion_inventario.isEnabled()
    assert v._accion_inventario.toolTip() == texto_sin_conexion_inventario()


def test_ca_c1_1_1_la_accion_cuelga_del_menu_archivo(entorno):
    v = entorno.ventana
    menus = {a.text().replace("&", ""): a.menu() for a in v.menuBar().actions() if a.menu()}
    archivo = next(m for t, m in menus.items() if t.startswith("Archivo"))
    assert v._accion_inventario in archivo.actions()


def test_ca_c1_1_1_con_una_version_anterior_a_8_0_se_deshabilita_con_la_version_minima(
    qtbot, entorno
):
    v = entorno.ventana
    m = _mundo(101)
    conectar(qtbot, entorno, sesion_falsa(version=(7, 4), cliente=m.sesion.cliente))
    assert not v._accion_inventario.isEnabled()
    assert v._accion_inventario.toolTip() == texto_sin_version_inventario("8.0")


def test_ca_c1_1_1_la_version_forzada_manda_sobre_la_detectada(qtbot, entorno):
    v = entorno.ventana
    m = _mundo(101)
    conectar(qtbot, entorno, sesion_falsa(version=(9, 2), forzada=True, cliente=m.sesion.cliente))
    assert v._accion_inventario.isEnabled()


def test_ca_c1_1_abrir_el_inventario_lee_la_lista_y_no_abre_dos_ventanas(qtbot, entorno):
    v = entorno.ventana
    m = _mundo(101, 102)
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    dialogo = _abrir(qtbot, v)
    assert dialogo.parent() is v and dialogo.tabla_lotes.rowCount() == 1
    v._accion_inventario.trigger()
    assert v._dialogo_inventario is dialogo
    assert len(v.findChildren(DialogoInventarioLotes)) == 1
    assert m.cluster.solo_lecturas
    dialogo.reject()
    qtbot.waitUntil(lambda: v._dialogo_inventario is None, timeout=4000)


# --- RF-C1.10: convivencia con el lote abierto en la sesión -------------------------------------


def test_ca_c1_10_1_el_lote_creado_en_la_sesion_se_avisa_y_no_se_puede_deshacer_desde_el_inventario(
    qtbot, entorno
):
    cliente = ClienteDeshacerFalso()
    v = lote_creado(qtbot, entorno, cliente)
    codigo = v._lote.plan.id_lote
    assert codigo in v._codigos_de_lotes_de_sesion()
    m = _mundo(101, 102, 103, codigo=codigo)
    v._sesion.cliente = m.sesion.cliente  # el inventario lee del servidor simulado
    dialogo = _abrir(qtbot, v)
    _elegir(qtbot, dialogo, codigo)
    assert "Abierto en esta sesión" in dialogo.tabla_lotes.item(0, 4).text()
    assert not dialogo.boton_deshacer.isEnabled()
    assert dialogo.boton_deshacer.toolTip() == texto_lote_abierto_en_sesion()
    assert dialogo.boton_exportar.isEnabled() and dialogo.boton_comprobar.isEnabled()
    dialogo.boton_deshacer.click()
    assert not dialogo.findChildren(DialogoConfirmarCodigoLote)
    assert m.cluster.escrituras == []


def test_ca_c1_10_3_si_el_libro_del_lote_se_cerro_el_inventario_permite_deshacer(qtbot, entorno):
    cliente = ClienteDeshacerFalso()
    v = lote_creado(qtbot, entorno, cliente)
    codigo = v._lote.plan.id_lote
    m = _mundo(101, 102, 103, codigo=codigo)
    v._sesion.cliente = m.sesion.cliente
    dialogo = _abrir(qtbot, v)
    _elegir(qtbot, dialogo, codigo)
    assert not dialogo.boton_deshacer.isEnabled()
    v._lote.cerrado = True  # el libro ya no está disponible en la sesión
    assert codigo not in v._codigos_de_lotes_de_sesion()
    dialogo.comprobar()
    qtbot.waitUntil(lambda: not dialogo.boton_cancelar_lectura.isVisibleTo(dialogo), timeout=8000)
    assert dialogo.boton_deshacer.isEnabled()


def test_ca_c1_10_1_un_lote_de_la_sesion_de_otro_servidor_no_cuenta(qtbot, entorno):
    """Los lotes de la sesión de otro perfil no bloquean al del servidor actual (CA-L18.14)."""
    cliente = ClienteDeshacerFalso()
    v = lote_creado(qtbot, entorno, cliente)
    codigo = v._lote.plan.id_lote
    v._perfil_id = "otro-perfil"
    assert codigo not in v._codigos_de_lotes_de_sesion()


def test_ca_c1_10_2_mientras_el_inventario_deshace_un_codigo_lote_deshacer_no_se_lanza(
    qtbot, entorno
):
    cliente = ClienteDeshacerFalso()
    v = lote_creado(qtbot, entorno, cliente)
    codigo = v._lote.plan.id_lote
    m = _mundo(101, codigo=codigo)
    v._sesion.cliente = m.sesion.cliente
    dialogo = _abrir(qtbot, v)
    dialogo.deshacer_empezado.emit(codigo)  # el mismo cable que usa el borrado real
    assert codigo in v._codigos_en_deshacer_inventario
    v._deshacer()
    assert not v.findChildren(DialogoDeshacer)  # ni siquiera se abre
    assert v.statusBar().currentMessage() == texto_lote_en_deshacer_inventario()
    dialogo.deshacer_terminado.emit(codigo)
    assert codigo not in v._codigos_en_deshacer_inventario
    v._deshacer()
    assert v.findChildren(DialogoDeshacer)  # ya puede lanzarse


def test_ca_c1_10_2_el_borrado_real_del_inventario_bloquea_y_desbloquea_el_codigo(qtbot, entorno):
    v = entorno.ventana
    m = _mundo(101, 102)
    puerta, dentro = threading.Event(), threading.Event()
    m.cluster.regla(
        "DELETE", r"/qemu/101$", lambda _ll: (dentro.set(), puerta.wait(5), NORMAL)[2], veces=1
    )
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    dialogo = _abrir(qtbot, v)
    _elegir(qtbot, dialogo)
    _borrar_con_codigo(qtbot, dialogo)
    try:
        qtbot.waitUntil(dentro.is_set, timeout=8000)
        assert v._codigos_en_deshacer_inventario == {CODIGO}
    finally:
        puerta.set()
    qtbot.waitUntil(lambda: not v._codigos_en_deshacer_inventario, timeout=8000)
    assert sorted(m.cluster.deletes.elements()) == [101, 102]


# --- RF-C1.14: servidor distinto y reconexión ---------------------------------------------------


def test_ca_c1_14_1_un_cambio_de_perfil_con_un_borrado_en_curso_no_envia_ningun_delete_al_nuevo(
    qtbot, entorno
):
    v = entorno.ventana
    viejo = _mundo(101, 102, 103)
    nuevo = _mundo(101, 102, 103)  # mismos VMIDs y códigos en el servidor nuevo
    puerta, dentro = threading.Event(), threading.Event()
    viejo.cluster.regla(
        "DELETE", r"/qemu/101$", lambda _ll: (dentro.set(), puerta.wait(5), NORMAL)[2], veces=1
    )
    conectar(qtbot, entorno, sesion_falsa(cliente=viejo.sesion.cliente))
    dialogo = _abrir(qtbot, v)
    _elegir(qtbot, dialogo)
    _borrar_con_codigo(qtbot, dialogo)
    qtbot.waitUntil(dentro.is_set, timeout=8000)
    otro = sesion_falsa(
        perfil("otro", "Otro servidor", ("10.0.0.9",)), cliente=nuevo.sesion.cliente
    )
    try:
        conectar(qtbot, entorno, otro)  # cambia el perfil con el borrado en vuelo
    finally:
        puerta.set()
    qtbot.waitUntil(lambda: not v._codigos_en_deshacer_inventario, timeout=8000)
    qtbot.waitUntil(lambda: v._dialogo_inventario is None, timeout=8000)
    assert nuevo.cluster.deletes.total() == 0 and nuevo.cluster.escrituras == []
    assert viejo.cluster.deletes.total() == 1  # solo la que ya estaba en vuelo
    assert {102, 103} <= set(viejo.cluster.vms)


def test_ca_c1_14_1_un_cambio_de_perfil_cierra_el_inventario_y_descarta_la_lectura_en_vuelo(
    qtbot, entorno
):
    v = entorno.ventana
    viejo = _mundo(101, 102)
    nuevo = _mundo(201)
    puerta, dentro = threading.Event(), threading.Event()
    viejo.cluster.regla(
        "GET", r"/qemu/\d+/config$", lambda _ll: (dentro.set(), puerta.wait(5), NORMAL)[2]
    )
    conectar(qtbot, entorno, sesion_falsa(cliente=viejo.sesion.cliente))
    dialogo = _abrir(qtbot, v)
    dialogo.tabla_lotes.selectRow(0)
    qtbot.waitUntil(dentro.is_set, timeout=8000)
    otro = sesion_falsa(perfil("otro", "Otro", ("10.0.0.9",)), cliente=nuevo.sesion.cliente)
    try:
        conectar(qtbot, entorno, otro)
    finally:
        puerta.set()
    qtbot.waitUntil(lambda: v._dialogo_inventario is None, timeout=8000)
    assert _cerrado(dialogo)
    assert nuevo.cluster.solo_lecturas  # nada del servidor viejo se ejecuta en el nuevo


def test_ca_c1_14_1_cerrar_la_sesion_cierra_el_inventario(qtbot, entorno):
    v = entorno.ventana
    m = _mundo(101)
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    dialogo = _abrir(qtbot, v)
    v._cerrar_sesion()
    qtbot.waitUntil(lambda: v._dialogo_inventario is None, timeout=8000)
    assert _cerrado(dialogo)


def test_ca_c1_14_1_reconectar_al_mismo_perfil_no_cierra_el_inventario(qtbot, entorno):
    v = entorno.ventana
    m = _mundo(101)
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    dialogo = _abrir(qtbot, v)
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    assert v._dialogo_inventario is dialogo and dialogo.isVisible()


# --- Cerrar la ventana con un borrado en curso --------------------------------------------------


def test_cerrar_la_ventana_con_un_borrado_en_curso_pregunta_y_si_se_dice_que_no_sigue_abierta(
    qtbot, entorno, monkeypatch
):
    v = entorno.ventana
    m = _mundo(101, 102)
    puerta, dentro = threading.Event(), threading.Event()
    m.cluster.regla(
        "DELETE", r"/qemu/101$", lambda _ll: (dentro.set(), puerta.wait(5), NORMAL)[2], veces=1
    )
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    dialogo = _abrir(qtbot, v)
    _elegir(qtbot, dialogo)
    _borrar_con_codigo(qtbot, dialogo)
    preguntas = Confirmaciones(False)
    monkeypatch.setattr(vp, "confirmar", preguntas)
    try:
        qtbot.waitUntil(dentro.is_set, timeout=8000)
        assert dialogo.hay_trabajo
        v.close()
        assert v.isVisible()  # «Seguir en ProxLaunch»
        assert preguntas.llamadas and "Deshacer" in preguntas.llamadas[0][0]
    finally:
        puerta.set()
    qtbot.waitUntil(lambda: not v._codigos_en_deshacer_inventario, timeout=8000)
