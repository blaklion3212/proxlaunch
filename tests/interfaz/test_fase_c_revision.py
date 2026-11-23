"""Correcciones de la revisión F6 de la fase C (0.8.0): pruebas de regresión de la interfaz.

Derivadas de docs/investigacion/fase-c-revision-f6.md (QA-C-B1, QA-C-B4, QA-C-B5 y SEG-C-M1 en los
tooltips del diálogo del inventario). Cliente: el real sobre un clúster en memoria; las lecturas
tardías se simulan con una puerta (``threading.Event``) en el servidor simulado.
"""

from __future__ import annotations

import html
import threading

import pytest
from PySide6.QtGui import QTextDocument

from nucleo.apoyo_fase_c_inventario import CODIGO, OTRO_CODIGO, Mundo
from nucleo.apoyo_lote import NORMAL
from proxlaunch.interfaz.dialogos import inventario_lotes as modulo_inventario
from proxlaunch.interfaz.dialogos.inventario_lotes import _tooltip_plano
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import LecturaGrupos

from . import test_ventana_principal as _base
from .apoyo import perfil, sesion_falsa
from .test_fase_c_inventario import COL_L_CODIGO, COL_NOMBRE, COL_VMID, Banco
from .test_fase_c_inventario_ventana import _abrir, _borrar_con_codigo, _elegir, _mundo

entorno = _base.entorno
conectar = _base.conectar

PREFIJO_TOOLTIP = "<p style='white-space:pre-wrap'>"


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Cierra sin bloquear ni preguntar."""


def _mundo_dos_lotes() -> Mundo:
    m = Mundo()
    m.cluster.agregar_mv(101, lote=CODIGO)
    m.cluster.agregar_mv(201, lote=OTRO_CODIGO)
    return m


# --- QA-C-B1: el fallo tardío del detalle de un lote anterior es obsoleto ---


def test_qa_c_b1_el_fallo_tardio_del_detalle_de_un_lote_anterior_no_afecta_al_actual(
    qtbot, monkeypatch
):
    m = _mundo_dos_lotes()
    original = modulo_inventario.detallar_lote_servidor
    puerta, dentro = threading.Event(), threading.Event()

    def detallar(sesion, reloj, lote, permisos, **kw):
        if lote.codigo != CODIGO:
            return original(sesion, reloj, lote, permisos, **kw)
        dentro.set()
        puerta.wait(5)  # la lectura del lote anterior sigue en vuelo y acaba mal
        raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "FALLO-TARDIO-A")

    monkeypatch.setattr(modulo_inventario, "detallar_lote_servidor", detallar)
    b = Banco(qtbot, m).abrir()
    fallos: list[tuple] = []
    fallo_real = b.d._fallo
    b.d._fallo = lambda *a, **k: (fallos.append(a), fallo_real(*a, **k))[1]
    tabla = b.d.tabla_lotes
    fila = {tabla.item(f, COL_L_CODIGO).text(): f for f in range(tabla.rowCount())}
    tabla.selectRow(fila[CODIGO])
    qtbot.waitUntil(dentro.is_set, timeout=4000)
    tabla.selectRow(fila[OTRO_CODIGO])  # se cambia de lote con la lectura anterior en vuelo
    qtbot.waitUntil(lambda: b.d.tabla_detalle.rowCount() == 1, timeout=8000)
    estado_actual = b.d.estado.text()
    assert b.d.tabla_detalle.item(0, COL_VMID).text() == "201"
    try:
        # Mientras otra operación está ocupando el diálogo, el fallo obsoleto no la toca.
        b.d._ocupado = True
        b.d._refrescar_botones()
        assert not b.d.boton_comprobar.isEnabled()
        puerta.set()
        qtbot.waitUntil(lambda: not b.lanzador.hay_activos, timeout=8000)
        assert fallos, "el fallo tardío debía llegar al diálogo para que la prueba tenga sentido"
        assert b.d._ocupado is True  # sigue ocupado: el fallo del lote anterior no lo liberó
        assert not b.d.boton_comprobar.isEnabled()
    finally:
        puerta.set()
        b.d._ocupado = False
    assert "FALLO-TARDIO-A" not in b.d.estado.text()
    assert b.d.estado.text() == estado_actual
    assert b.d.tabla_detalle.rowCount() == 1  # el detalle del lote actual sigue pintado
    assert b.d.codigo_seleccionado == OTRO_CODIGO


def test_qa_c_b1_el_fallo_del_detalle_del_lote_actual_si_se_muestra(qtbot, monkeypatch):
    """Control: un fallo no obsoleto sigue informándose."""
    m = _mundo_dos_lotes()

    def detallar(sesion, reloj, lote, permisos, **kw):
        raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "FALLO-ACTUAL")

    monkeypatch.setattr(modulo_inventario, "detallar_lote_servidor", detallar)
    b = Banco(qtbot, m).abrir()
    b.d.tabla_lotes.selectRow(0)
    qtbot.waitUntil(lambda: not b.lanzador.hay_activos, timeout=8000)
    assert b.d.boton_comprobar.isEnabled()
    assert b.d.estado.text() != ""


# --- SEG-C-M1: los tooltips del diálogo no interpretan HTML ---

HOSTIL = "<b>negrita</b> <img src=x onerror=alert(1)> &amp; fin"


def test_seg_c_m1_el_tooltip_plano_escapa_el_marcado_y_se_ve_como_texto_literal():
    tip = _tooltip_plano(HOSTIL)
    interior = tip.removeprefix(PREFIJO_TOOLTIP).removesuffix("</p>")
    assert "<" not in interior and ">" not in interior
    assert html.unescape(interior) == HOSTIL
    # Como lo interpretaría Qt: el texto mostrado es el literal, sin etiquetas aplicadas.
    doc = QTextDocument()
    doc.setHtml(tip)
    assert doc.toPlainText() == HOSTIL


def test_seg_c_m1_el_tooltip_plano_vacio_no_lleva_marcado():
    assert _tooltip_plano("") == ""


def test_seg_c_m1_todos_los_tooltips_de_las_tablas_del_dialogo_van_escapados(qtbot):
    m = Mundo(("pve1",))
    m.cluster.agregar_mv(101, nombre="srv<b>x</b>&y")
    m.cluster.fila_lista[101] = {"name": HOSTIL, "node": "pve1"}
    b = Banco(qtbot, m).abrir().elegir()
    celdas = 0
    for tabla in (b.d.tabla_lotes, b.d.tabla_detalle):
        for f in range(tabla.rowCount()):
            for c in range(tabla.columnCount()):
                item = tabla.item(f, c)
                if item is None or not item.toolTip():
                    continue
                celdas += 1
                interior = item.toolTip().removeprefix(PREFIJO_TOOLTIP).removesuffix("</p>")
                assert "<" not in interior and ">" not in interior, (f, c, item.toolTip())
    assert celdas > 0
    assert b.d.tabla_detalle.item(0, COL_NOMBRE).text()  # el nombre sigue siendo texto plano


# --- QA-C-B4: resultados de firewall de una sesión anterior se descartan ---


def _cluster_con_grupo_en_puerta(m: Mundo, puerta: threading.Event, dentro: threading.Event):
    def grupos(_ll):
        dentro.set()
        puerta.wait(5)
        return [{"group": "web", "comment": ""}]

    def reglas(_ll):
        dentro.set()
        puerta.wait(5)
        return [{"type": "in", "action": "ACCEPT", "enable": 1}]

    m.cluster.regla("GET", r"^/cluster/firewall/groups$", grupos)
    m.cluster.regla("GET", r"^/cluster/firewall/groups/web$", reglas)


def test_qa_c_b4_la_lista_de_grupos_de_una_sesion_anterior_se_descarta(qtbot, entorno, monkeypatch):
    v = entorno.ventana
    viejo, nuevo = _mundo(101), _mundo(201)
    puerta, dentro = threading.Event(), threading.Event()
    _cluster_con_grupo_en_puerta(viejo, puerta, dentro)
    conectar(qtbot, entorno, sesion_falsa(cliente=viejo.sesion.cliente))
    recibidas: list[LecturaGrupos] = []
    monkeypatch.setattr(v.formulario, "establecer_grupos_firewall", recibidas.append)
    v.formulario.pide_grupos_firewall.emit()
    qtbot.waitUntil(dentro.is_set, timeout=4000)
    otro = sesion_falsa(perfil("otro", "Otro", ("10.0.0.9",)), cliente=nuevo.sesion.cliente)
    try:
        conectar(qtbot, entorno, otro)  # se cambia de servidor con la lectura en vuelo
    finally:
        puerta.set()
    qtbot.waitUntil(lambda: not v._lanzador.hay_activos, timeout=8000)
    assert recibidas == []


def test_qa_c_b4_las_reglas_de_un_grupo_de_una_sesion_anterior_se_descartan(
    qtbot, entorno, monkeypatch
):
    v = entorno.ventana
    viejo, nuevo = _mundo(101), _mundo(201)
    puerta, dentro = threading.Event(), threading.Event()
    _cluster_con_grupo_en_puerta(viejo, puerta, dentro)
    conectar(qtbot, entorno, sesion_falsa(cliente=viejo.sesion.cliente))
    recibidas: list[tuple] = []
    monkeypatch.setattr(v.formulario, "establecer_reglas_grupo", lambda *a: recibidas.append(a))
    v.formulario.pide_reglas_grupo.emit("web")
    qtbot.waitUntil(dentro.is_set, timeout=4000)
    otro = sesion_falsa(perfil("otro", "Otro", ("10.0.0.9",)), cliente=nuevo.sesion.cliente)
    try:
        conectar(qtbot, entorno, otro)
    finally:
        puerta.set()
    qtbot.waitUntil(lambda: not v._lanzador.hay_activos, timeout=8000)
    assert recibidas == []


def test_qa_c_b4_control_en_la_misma_sesion_los_resultados_si_llegan(qtbot, entorno, monkeypatch):
    v = entorno.ventana
    m = _mundo(101)
    puerta, dentro = threading.Event(), threading.Event()
    puerta.set()
    _cluster_con_grupo_en_puerta(m, puerta, dentro)
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    grupos: list[LecturaGrupos] = []
    reglas: list[tuple] = []
    monkeypatch.setattr(v.formulario, "establecer_grupos_firewall", grupos.append)
    monkeypatch.setattr(v.formulario, "establecer_reglas_grupo", lambda *a: reglas.append(a))
    v.formulario.pide_grupos_firewall.emit()
    v.formulario.pide_reglas_grupo.emit("web")
    qtbot.waitUntil(lambda: len(grupos) == 1 and len(reglas) == 1, timeout=8000)


# --- QA-C-B5: al terminar un borrado tras cambiar de servidor no se relanza el descubrimiento ---


def _espiar_descubrir(v, monkeypatch) -> list[int]:
    llamadas: list[int] = []
    monkeypatch.setattr(v, "_descubrir", lambda: llamadas.append(1))
    return llamadas


def test_qa_c_b5_el_borrado_que_termina_tras_cambiar_de_servidor_no_relanza_el_descubrimiento(
    qtbot, entorno, monkeypatch
):
    v = entorno.ventana
    viejo, nuevo = _mundo(101, 102), _mundo(201)
    puerta, dentro = threading.Event(), threading.Event()
    viejo.cluster.regla(
        "DELETE", r"/qemu/101$", lambda _ll: (dentro.set(), puerta.wait(5), NORMAL)[2], veces=1
    )
    conectar(qtbot, entorno, sesion_falsa(cliente=viejo.sesion.cliente))
    dialogo = _abrir(qtbot, v)
    _elegir(qtbot, dialogo)
    _borrar_con_codigo(qtbot, dialogo)
    qtbot.waitUntil(dentro.is_set, timeout=8000)
    otro = sesion_falsa(perfil("otro", "Otro", ("10.0.0.9",)), cliente=nuevo.sesion.cliente)
    try:
        conectar(qtbot, entorno, otro)
        llamadas = _espiar_descubrir(v, monkeypatch)  # solo cuenta lo posterior al cambio
    finally:
        puerta.set()
    qtbot.waitUntil(lambda: not v._codigos_en_deshacer_inventario, timeout=8000)
    qtbot.waitUntil(lambda: v._dialogo_inventario is None, timeout=8000)
    assert llamadas == []
    assert nuevo.cluster.escrituras == []


def test_qa_c_b5_control_en_el_mismo_servidor_el_borrado_si_relanza_el_descubrimiento(
    qtbot, entorno, monkeypatch
):
    v = entorno.ventana
    m = _mundo(101, 102)
    conectar(qtbot, entorno, sesion_falsa(cliente=m.sesion.cliente))
    llamadas = _espiar_descubrir(v, monkeypatch)
    dialogo = _abrir(qtbot, v)
    _elegir(qtbot, dialogo)
    _borrar_con_codigo(qtbot, dialogo)
    qtbot.waitUntil(lambda: not v._codigos_en_deshacer_inventario, timeout=8000)
    assert m.cluster.deletes.total() == 2
    assert llamadas == [1]
