"""Correcciones de seguridad y QA de la fase A (0.6.0), segunda ronda: interfaz.

Cubre SEG-A-05 (tooltips escapados), SEG-A-08 (notas del resumen de lote), QA-A-04 (límite sin
notación científica) y los textos nuevos (V-A16 y V-A03 con permisos desconocidos).
"""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit

from proxlaunch.interfaz import textos
from proxlaunch.interfaz.vistas.campos import FilaCampo
from proxlaunch.interfaz.vistas.resumen_lote import texto_opciones_del_plan
from proxlaunch.interfaz.vistas.tabla_redes import texto_limite
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_lote import cfg_simple, definicion, planificar

HTML = "<b>negrita</b> <img src=x onerror=1>"


# --- SEG-A-05 ---


def test_seg_a_05_el_tooltip_del_error_se_escapa_y_no_se_lee_como_html(qtbot):
    campo = QLineEdit()
    fila = FilaCampo("Etiquetas", campo)
    qtbot.addWidget(fila)
    fila.marcar_tocado()
    fila.mostrar_error(HTML)
    tooltip = campo.toolTip()
    assert tooltip == textos.tooltip_plano(HTML)
    assert "<b>" not in tooltip and "<img" not in tooltip
    assert "&lt;b&gt;" in tooltip
    # La línea visible es texto plano: Qt no interpreta el HTML.
    assert fila._error.text() == HTML


def test_seg_a_05_el_aviso_tambien_lleva_tooltip_escapado_y_se_limpia(qtbot):
    campo = QLineEdit()
    fila = FilaCampo("Pool", campo)
    qtbot.addWidget(fila)
    fila.mostrar_aviso(HTML)
    assert "<b>" not in fila._aviso_extra.toolTip()
    assert "&lt;b&gt;" in fila._aviso_extra.toolTip()
    fila.mostrar_aviso(None)
    assert fila._aviso_extra.toolTip() == ""


# --- SEG-A-08 ---


def _lineas(inv, notas: str) -> list[str]:
    plan = planificar(inv, definicion(2, plantilla=cfg_simple(notas=notas)))
    return texto_opciones_del_plan(plan).splitlines()


def test_seg_a_08_el_resumen_del_lote_muestra_la_longitud_de_las_notas(inv_cluster):
    lineas = _lineas(inv_cluster, "x" * 100)
    (notas,) = [ln for ln in lineas if ln.startswith("Notas:")]
    assert "(100 caracteres)" in notas
    assert not any("enlaces" in ln for ln in lineas)


def test_seg_a_08_avisa_si_las_notas_traen_enlaces_o_html(inv_cluster):
    for notas in (
        "mira http://malo.example/x",
        "mira HTTPS://malo.example",
        "[clic](javascript:alert(1))",
        "texto <script>",
    ):
        lineas = _lineas(inv_cluster, notas)
        assert any("enlaces o código HTML" in ln for ln in lineas), notas


def test_seg_a_08_sin_notas_no_hay_linea_de_notas_ni_aviso(inv_cluster):
    lineas = _lineas(inv_cluster, "")
    assert not any(ln.startswith("Notas:") or "enlaces" in ln for ln in lineas)


# --- QA-A-04 ---


def test_qa_a_04_el_limite_del_campo_no_usa_notacion_cientifica():
    assert texto_limite(None) == ""
    assert texto_limite(100.0) == "100"
    assert texto_limite(12.5) == "12.5"
    assert texto_limite(1234567.0) == "1234567"
    assert texto_limite(0.00001) == "0.00001"
    assert texto_limite(float("inf")) == "inf"  # no es válido: V-A06 lo marca, sin romper


# --- Textos nuevos ---


def test_v_a16_tiene_mensaje_que_explica_el_formato():
    p = Problema("pool", "V-A16", Severidad.ERROR, {"pool": "a b"})
    texto = textos.texto_problema(p)
    assert "pool" in texto and "/" in texto


def test_qa_a_10_v_a03_con_permisos_desconocidos_aclara_que_es_un_aviso():
    prm = {"etiqueta": "web", "motivo": "no_permitida"}
    firme = textos.texto_problema(Problema("etiquetas", "V-A03", Severidad.ERROR, prm))
    dudoso = textos.texto_problema(
        Problema("etiquetas", "V-A03", Severidad.AVISO, {**prm, "incierto": "1"})
    )
    assert dudoso.startswith(firme)
    assert "permisos" in dudoso and dudoso != firme
