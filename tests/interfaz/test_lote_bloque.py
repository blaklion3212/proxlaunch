"""Bloque «Lote» del formulario: cantidad, nombres, destino y modo básico/avanzado.

Cubre RF-L01, RF-L02, RF-L05 (interfaz), RF-L22 y las reglas V-L01..V-L04, V-L07, V-L13
tal como se muestran junto al campo (CA-L01.x, CA-L02.x, CA-L22.x, CA-L05.7/.8).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from proxlaunch.interfaz import textos
from proxlaunch.interfaz.ayuda import CAMPOS_AYUDA_LOTE, ayuda
from proxlaunch.interfaz.vistas.bloque_lote import BloqueLote
from proxlaunch.nucleo.lote.constantes import MAX_LOTE
from proxlaunch.nucleo.lote.modelos import Algoritmo, ModoDestino, Severidad

from .apoyo_lote import cfg_simple


@pytest.fixture
def bloque(qtbot, inv_cluster):
    b = BloqueLote()
    qtbot.addWidget(b)
    b.establecer_inventario(inv_cluster)
    b.show()
    return b


@pytest.fixture
def bloque_individual(qtbot, inv_individual):
    b = BloqueLote()
    qtbot.addWidget(b)
    b.establecer_inventario(inv_individual)
    b.show()
    return b


def escribir(campo, texto):
    """Simula que el usuario escribe (señal textEdited, como en la ventana)."""
    campo.setText(texto)
    campo.textEdited.emit(texto)


def poner_lote(bloque, cantidad, prefijo="web"):
    escribir(bloque.cantidad, str(cantidad))
    escribir(bloque.prefijo, prefijo)
    # La ventana revalida en cada ``cambiado`` y es quien refresca la vista previa.
    bloque.aplicar_problemas(bloque.problemas(cfg_simple()))


def errores_de(bloque):
    """Reglas con severidad de error que reporta el bloque para la plantilla actual."""
    return [p for p in bloque.problemas(cfg_simple()) if p.severidad == Severidad.ERROR]


def aplicar(bloque):
    bloque.aplicar_problemas(bloque.problemas(cfg_simple()))


# --- RF-L01: cantidad ----------------------------------------------------------------------


def test_ca_l01_1_recien_abierto_la_cantidad_es_uno_y_es_el_flujo_de_m1(bloque):
    assert bloque.cantidad.text() == "1"
    assert not bloque.es_lote
    # Con una máquina solo se ve la cantidad: ni prefijo, ni vista previa ni destino.
    assert bloque.cantidad.isVisible()
    assert not bloque.prefijo.isVisible()
    assert not bloque.fila_destino.isVisible()
    assert bloque.texto_vista_previa == ""
    assert errores_de(bloque) == []


@pytest.mark.parametrize("texto", ["0", "-1", "1.5", "abc", "", "  ", "1e1"])
def test_ca_l01_2_cantidad_invalida_bloquea_con_v_l01_junto_al_campo(bloque, texto):
    escribir(bloque.cantidad, texto)
    reglas = [p.regla for p in errores_de(bloque)]
    assert "V-L01" in reglas
    aplicar(bloque)
    fila = bloque._filas["cantidad"]
    assert fila.hay_error  # el error sale junto al campo (no en un diálogo)
    assert f"{MAX_LOTE}" in fila._error.text()


def test_ca_l01_3_mas_del_maximo_bloquea_y_nunca_se_recorta_en_silencio(bloque):
    escribir(bloque.cantidad, str(MAX_LOTE + 1))
    assert "V-L01" in [p.regla for p in errores_de(bloque)]
    aplicar(bloque)
    assert bloque.cantidad.text() == str(MAX_LOTE + 1)  # el valor escrito no se toca
    assert str(MAX_LOTE) in bloque._filas["cantidad"]._error.text()


def test_ca_l01_3_el_mensaje_literal_del_requisito_para_el_maximo(bloque):
    """CA-L01.3: «El máximo por lote es 100 máquinas. Divide el trabajo en varios lotes.»"""
    escribir(bloque.cantidad, str(MAX_LOTE + 1))
    aplicar(bloque)
    texto = bloque._filas["cantidad"]._error.text()
    assert "El máximo por lote es 100 máquinas" in texto
    assert "Divide el trabajo en varios lotes" in texto


@pytest.mark.parametrize("n", [1, 2, MAX_LOTE])
def test_limites_validos_de_la_cantidad_no_dan_v_l01(bloque, n):
    poner_lote(bloque, n)
    assert "V-L01" not in [p.regla for p in errores_de(bloque)]


def test_ca_l01_4_el_limite_del_texto_sale_de_la_constante_unica(monkeypatch):
    monkeypatch.setattr(textos, "MAX_LOTE", 50)
    from proxlaunch.nucleo.lote.modelos import Problema

    texto = textos.texto_problema_lote(Problema("V-L01", Severidad.ERROR, "cantidad", {}))
    assert "50" in texto and "100" not in texto


def test_ca_l01_5_formas_plurales_en_la_cantidad(qtbot):
    from proxlaunch.interfaz.vistas.resumen_lote import texto_boton_crear, texto_total_maquinas

    assert texto_total_maquinas(1) == "Vas a crear una máquina"
    assert texto_total_maquinas(12) == "Vas a crear 12 máquinas"
    assert texto_boton_crear(1, simulado=False) == "Crear 1 máquina"
    assert texto_boton_crear(12, simulado=False) == "Crear 12 máquinas"


# --- RF-L02: nombres -----------------------------------------------------------------------


def test_ca_l02_6_vista_previa_de_los_tres_primeros_y_el_ultimo(bloque):
    # El ejemplo del requisito (120) supera MAX_LOTE=100; con 100 el relleno efectivo es 3.
    poner_lote(bloque, 100)
    assert bloque.texto_vista_previa == "Se llamarán: web-001, web-002, web-003 … web-100"
    assert bloque.nombres_previstos()[0] == "web-001"
    assert bloque.nombres_previstos()[-1] == "web-100"
    assert len({len(n) for n in bloque.nombres_previstos()}) == 1  # misma longitud (CA-L02.2)


def test_ca_l02_1_vista_previa_con_tres_nombres_completos(bloque):
    poner_lote(bloque, 3)
    assert bloque.texto_vista_previa == "Se llamarán: web-01, web-02, web-03"


def test_vista_previa_con_cuatro_muestra_todos_sin_puntos_suspensivos(bloque):
    poner_lote(bloque, 4)
    assert bloque.texto_vista_previa == "Se llamarán: web-01, web-02, web-03, web-04"


def test_ca_l02_3_inicio_diez_sin_relleno_ni_separador(bloque):
    bloque.establecer_modo(True)
    poner_lote(bloque, 3)
    escribir(bloque.inicio, "10")
    escribir(bloque.relleno, "0")
    bloque.combo_separador.setCurrentIndex(bloque.combo_separador.findData(""))
    aplicar(bloque)
    assert bloque.nombres_previstos() == ["web10", "web11", "web12"]
    assert bloque.texto_vista_previa == "Se llamarán: web10, web11, web12"


@pytest.mark.parametrize(
    "prefijo", ["web 1", "web_1", "wéb", "web/1", "web,1", "web=1", "web&1", "web;1", "web\n1"]
)
def test_ca_l02_4_prefijos_con_caracteres_prohibidos_bloquean_junto_al_campo(bloque, prefijo):
    """Espacio, guion bajo, acento, ``/``; y (RNF-L08) ``, = & ;`` y saltos de línea."""
    poner_lote(bloque, 3, prefijo)
    assert [p for p in errores_de(bloque) if p.campo and "prefijo" in p.campo], prefijo
    aplicar(bloque)
    assert bloque._filas["prefijo"].hay_error
    assert bloque.nombres_previstos() == []
    assert bloque.texto_vista_previa == ""  # sin vista previa de un nombre inválido


def test_ca_l02_4_el_mensaje_nombra_el_primer_nombre_invalido_y_la_causa(bloque):
    poner_lote(bloque, 3, "web_")
    aplicar(bloque)
    texto = bloque._filas["prefijo"]._error.text()
    assert "web_01" in texto and "_" in texto


def test_ca_l02_4_nombre_de_mas_de_63_caracteres_bloquea(bloque):
    poner_lote(bloque, 3, "a" * 62)  # con «-01» pasa de 63
    assert errores_de(bloque)
    aplicar(bloque)
    assert bloque._filas["prefijo"].hay_error


def test_prefijo_de_60_caracteres_es_valido(bloque):
    poner_lote(bloque, 3, "a" * 59)  # 59 + «-01» = 62
    assert errores_de(bloque) == []


def test_prefijo_vacio_en_un_lote_pide_escribirlo(bloque):
    escribir(bloque.cantidad, "3")
    aplicar(bloque)
    assert bloque._filas["prefijo"].hay_error
    assert "prefijo" in bloque._filas["prefijo"]._error.text().lower()


def test_ca_l02_8_numeracion_fuera_de_rango_bloquea(bloque):
    bloque.establecer_modo(True)
    poner_lote(bloque, 5)
    escribir(bloque.inicio, "999999")
    assert errores_de(bloque)
    aplicar(bloque)
    assert bloque._filas["inicio"].hay_error or bloque._filas["prefijo"].hay_error


def test_relleno_fuera_de_rango_bloquea_junto_al_campo(bloque):
    bloque.establecer_modo(True)
    poner_lote(bloque, 3)
    escribir(bloque.relleno, "9")
    aplicar(bloque)
    assert bloque._filas["relleno"].hay_error


def test_un_error_no_se_muestra_antes_de_que_el_usuario_toque_el_campo(qtbot, inv_cluster):
    b = BloqueLote()
    qtbot.addWidget(b)
    b.establecer_inventario(inv_cluster)
    b.cantidad.setText("500")  # sin textEdited: el usuario aún no ha interactuado
    b.aplicar_problemas(b.problemas(cfg_simple()))
    assert not b._filas["cantidad"].hay_error


# --- RF-L03/V-L07: VMID inicial ------------------------------------------------------------


@pytest.mark.parametrize("texto", ["99", "1000000000", "abc"])
def test_v_l07_vmid_inicial_fuera_de_rango_bloquea(bloque, texto):
    bloque.establecer_modo(True)
    poner_lote(bloque, 3)
    escribir(bloque.vmid_inicial, texto)
    assert "V-L07" in [p.regla for p in errores_de(bloque)]
    aplicar(bloque)
    assert bloque._filas["vmid_inicial"].hay_error


def test_ca_l03_5_el_ultimo_vmid_del_plan_no_puede_pasar_del_maximo(bloque):
    bloque.establecer_modo(True)
    poner_lote(bloque, 10)
    escribir(bloque.vmid_inicial, "999999995")
    assert "V-L07" in [p.regla for p in errores_de(bloque)]


def test_vmid_inicial_vacio_significa_automatico(bloque):
    bloque.establecer_modo(True)
    poner_lote(bloque, 3)
    assert bloque.definicion(cfg_simple()).vmid_inicial is None
    escribir(bloque.vmid_inicial, "200")
    assert bloque.definicion(cfg_simple()).vmid_inicial == 200


# --- RF-L22: modo básico y avanzado -------------------------------------------------------


AVANZADOS = ("combo_separador", "inicio", "relleno", "vmid_inicial", "chk_etiquetar")


def test_ca_l22_1_modo_basico_solo_muestra_cantidad_prefijo_y_destino(bloque):
    poner_lote(bloque, 3)
    bloque.establecer_modo(False)
    assert bloque.cantidad.isVisible() and bloque.prefijo.isVisible()
    assert bloque.fila_destino.isVisible()
    for nombre in AVANZADOS:
        assert not getattr(bloque, nombre).isVisible(), nombre
    assert not bloque.fila_algoritmo.isVisible()
    assert not bloque._radio_elegidos.isVisible()  # «Nodos elegidos» es avanzado


def test_ca_l22_2_modo_avanzado_anade_separador_inicio_relleno_vmid_algoritmo_y_etiquetas(bloque):
    poner_lote(bloque, 3)
    bloque.establecer_modo(True)
    for nombre in AVANZADOS:
        assert getattr(bloque, nombre).isVisible(), nombre
    assert bloque._radio_elegidos.isVisible()
    assert bloque.fila_algoritmo.isVisible()


def test_ca_l22_3_cambiar_de_modo_conserva_lo_escrito_y_los_valores_ocultos_cuentan(bloque):
    bloque.establecer_modo(True)
    poner_lote(bloque, 3)
    escribir(bloque.inicio, "10")
    escribir(bloque.relleno, "3")
    bloque.combo_separador.setCurrentIndex(bloque.combo_separador.findData(""))
    bloque.chk_etiquetar.setChecked(False)
    bloque.establecer_modo(False)
    assert bloque.prefijo.text() == "web" and bloque.inicio.text() == "10"
    assert bloque.relleno.text() == "3" and not bloque.chk_etiquetar.isChecked()
    # Los valores ocultos se conservan y siguen aplicándose a la definición (M1 CA-24.5).
    d = bloque.definicion(cfg_simple())
    assert (d.patron.inicio, d.patron.relleno, d.patron.separador) == (10, 3, "")
    assert d.etiquetar is False
    assert bloque.nombres_previstos() == ["web010", "web011", "web012"]
    bloque.establecer_modo(True)
    assert bloque.inicio.text() == "10"


def test_etiquetar_viene_marcado_por_defecto(bloque):
    assert bloque.definicion(cfg_simple()).etiquetar is True


def test_con_cantidad_uno_el_modo_avanzado_tampoco_muestra_campos_de_lote(bloque):
    bloque.establecer_modo(True)
    for nombre in AVANZADOS:
        assert not getattr(bloque, nombre).isVisible(), nombre


def test_ca_22_4_cada_campo_nuevo_tiene_un_boton_de_ayuda_con_su_texto(bloque):
    poner_lote(bloque, 3)
    bloque.establecer_modo(True)
    esperados = {ayuda(c) for c in ("lote_cantidad", "lote_prefijo", "lote_destino")}
    tooltips = {w.toolTip() for w in bloque.findChildren(QWidget) if w.toolTip()}
    assert esperados <= tooltips
    assert all(ayuda(c) for c in CAMPOS_AYUDA_LOTE)


# --- RF-L05: destino ----------------------------------------------------------------------


def test_automatico_es_el_destino_predeterminado_en_un_cluster(bloque):
    poner_lote(bloque, 3)
    d = bloque.definicion(cfg_simple()).destino
    assert d.modo == ModoDestino.AUTOMATICO and d.algoritmo == Algoritmo.EQUILIBRADO
    assert bloque.fila_destino.isVisible()


def test_servidor_individual_no_muestra_selector_de_destino_ni_algoritmo(bloque_individual):
    b = bloque_individual
    poner_lote(b, 3)
    b.establecer_modo(True)
    assert not b.fila_destino.isVisible() and not b.fila_algoritmo.isVisible()


def test_un_nodo_usa_el_nodo_elegido_y_emite_destino_cambiado(qtbot, bloque):
    poner_lote(bloque, 3)
    with qtbot.waitSignal(bloque.destino_cambiado, timeout=1000):
        bloque._radio_un_nodo.setChecked(True)
    assert bloque.modo_destino == ModoDestino.UN_NODO
    assert bloque.nodo_elegido == "pve1"
    bloque.combo_nodo.setCurrentIndex(bloque.combo_nodo.findData("pve3"))
    assert bloque.definicion(cfg_simple()).destino.nodos == ("pve3",)


def test_ca_l05_7_el_nodo_caido_aparece_sin_conexion_y_no_se_puede_elegir(bloque):
    poner_lote(bloque, 3)
    bloque.establecer_modo(True)
    i = bloque.combo_nodo.findData("pve2")
    assert "Sin conexión" in bloque.combo_nodo.itemText(i)
    assert not bloque.combo_nodo.model().item(i).isEnabled()
    check = bloque._checks_nodos["pve2"]
    assert "Sin conexión" in check.text() and not check.isEnabled() and not check.isChecked()


def test_nodos_elegidos_por_defecto_marca_todos_los_que_estan_en_linea(bloque):
    poner_lote(bloque, 3)
    bloque.establecer_modo(True)
    bloque._radio_elegidos.setChecked(True)
    d = bloque.definicion(cfg_simple()).destino
    assert d.modo == ModoDestino.NODOS_ELEGIDOS
    assert set(d.nodos) == {"pve1", "pve3"}


def test_ca_l05_8_nodos_elegidos_sin_ninguno_bloquea_con_v_l13(bloque):
    poner_lote(bloque, 3)
    bloque.establecer_modo(True)
    bloque._radio_elegidos.setChecked(True)
    for c in bloque._checks_nodos.values():
        c.setChecked(False)
    assert "V-L13" in [p.regla for p in errores_de(bloque)]
    aplicar(bloque)
    assert bloque._filas["destino"].hay_error


def test_algoritmo_por_turnos_se_refleja_en_la_definicion(bloque):
    poner_lote(bloque, 3)
    bloque.establecer_modo(True)
    bloque.combo_algoritmo.setCurrentIndex(bloque.combo_algoritmo.findData(Algoritmo.POR_TURNOS))
    assert bloque.definicion(cfg_simple()).destino.algoritmo == Algoritmo.POR_TURNOS


def test_actualizar_el_inventario_conserva_la_eleccion_si_el_nodo_sigue_existiendo(
    bloque, inv_cluster
):
    poner_lote(bloque, 3)
    bloque._radio_un_nodo.setChecked(True)
    bloque.combo_nodo.setCurrentIndex(bloque.combo_nodo.findData("pve3"))
    bloque.establecer_inventario(inv_cluster)
    assert bloque.nodo_elegido == "pve3"


# --- Señales y bloqueo --------------------------------------------------------------------


def test_cada_edicion_emite_cambiado_para_revalidar(qtbot, bloque):
    with qtbot.waitSignal(bloque.cambiado, timeout=1000):
        escribir(bloque.cantidad, "3")
    with qtbot.waitSignal(bloque.cambiado, timeout=1000):
        escribir(bloque.prefijo, "web")


def test_establecer_cantidad_por_codigo_emite_cambiado_y_muestra_el_lote(qtbot, bloque):
    with qtbot.waitSignal(bloque.cambiado, timeout=1000):
        bloque.establecer_cantidad(5)
    assert bloque.cantidad.text() == "5" and bloque.es_lote and bloque.prefijo.isVisible()


def test_ca_l10_9_bloquear_deshabilita_el_bloque_entero(bloque):
    bloque.bloquear(True)
    assert not bloque.isEnabled()
    bloque.bloquear(False)
    assert bloque.isEnabled()


def test_accesibilidad_los_campos_tienen_nombre_accesible(bloque):
    poner_lote(bloque, 3)
    assert bloque.cantidad.accessibleName()
    assert bloque.prefijo.accessibleName()
    assert bloque.combo_nodo.accessibleName()
    assert bloque.combo_algoritmo.accessibleName()
