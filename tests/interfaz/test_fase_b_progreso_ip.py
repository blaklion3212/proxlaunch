"""Columna «IP» del libro, botones y resumen de la espera de IP en el progreso (fase B, 0.7.0).

Derivadas de docs/requisitos/fase-b.md y de docs/arquitectura/fase-b.md §15: RF-B3.3 a RF-B3.6,
CA-B3.5.3 (botón «Dejar de esperar la IP»), CA-B3.6.4 (sin B3 no hay «Exportar IPs…»), la columna
IP solo cuando alguna máquina espera IP (sin B3 quedan las 5 columnas de 0.6.0) y el resumen que
separa «esperando» de «sin IP».
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from proxlaunch.interfaz.modelos_tabla import ModeloLibro
from proxlaunch.interfaz.textos import tooltip_plano
from proxlaunch.interfaz.textos_b import (
    simbolo_estado_ip,
    texto_celda_ip,
    texto_detalle_ip,
    texto_esperando_ips,
    texto_estado_ip,
    texto_resumen_ips,
    token_color_ip,
)
from proxlaunch.interfaz.vistas.progreso import PanelProgreso
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, ProgresoLote
from proxlaunch.nucleo.agente.modelos import EstadoIp, ResultadoIp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.informe import resumen_ips
from proxlaunch.nucleo.lote.modelos import EstadoMV

from .apoyo_fase_b import con_ip, entrada_ip
from .apoyo_lote import definicion, elemento, entradas_de
from .test_lote_progreso import plan_vacio

EM = EstadoMV
CABECERAS_060 = ["Estado", "Nombre", "VMID", "Nodo", "Detalle"]


def cabeceras(modelo) -> list[str]:
    return [
        modelo.headerData(i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for i in range(modelo.columnCount())
    ]


def celda(modelo, fila: int, columna: int) -> str:
    return modelo.data(modelo.index(fila, columna), Qt.ItemDataRole.DisplayRole)


@pytest.fixture
def progreso(qtbot):
    p = ProgresoLote()
    qtbot.addWidget(p)
    p.show()
    return p


def poner(progreso: ProgresoLote, entradas, fase: FaseLote = FaseLote.TERMINADO) -> None:
    progreso.iniciar(plan_vacio(len(entradas)))
    progreso.actualizar(tuple(entradas))
    progreso.establecer_fase(fase)


# --- La columna IP solo existe si alguna máquina espera IP ---


def test_sin_b3_el_modelo_del_libro_conserva_las_cinco_columnas_de_0_6_0():
    m = ModeloLibro()
    m.establecer_entradas(entradas_de([EM.OK, EM.OK, EM.CREANDO]))
    assert m.columnCount() == 5
    assert cabeceras(m) == CABECERAS_060
    assert m.con_ip is False
    assert m.columna_ip is None
    assert m.columna_detalle == 4


def test_con_una_maquina_que_espera_ip_aparece_la_columna_ip_entre_nodo_y_detalle():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0, esperar=False), entrada_ip(1)))
    assert m.columnCount() == 6
    assert cabeceras(m) == ["Estado", "Nombre", "VMID", "Nodo", "IP", "Detalle"]
    assert m.con_ip is True
    assert (m.columna_ip, m.columna_detalle) == (4, 5)


def test_la_columna_detalle_sigue_mostrando_el_detalle_con_y_sin_columna_ip():
    sin = ModeloLibro()
    sin.establecer_entradas(entradas_de([EM.ERROR]))
    con = ModeloLibro()
    con.establecer_entradas((entrada_ip(0, EM.ERROR),))
    assert celda(sin, 0, sin.columna_detalle) == celda(con, 0, con.columna_detalle)


def test_la_columna_ip_aparece_y_desaparece_al_cambiar_las_entradas():
    m = ModeloLibro()
    m.establecer_entradas(entradas_de([EM.OK]))
    assert m.columnCount() == 5
    m.establecer_entradas((entrada_ip(0),))
    assert m.columnCount() == 6
    m.establecer_entradas(entradas_de([EM.OK]))
    assert m.columnCount() == 5


def test_el_modelo_vacio_no_tiene_columna_ip():
    m = ModeloLibro()
    assert m.columnCount() == 5 and m.rowCount() == 0


def test_las_cabeceras_de_las_columnas_de_nombre_vmid_y_nodo_no_se_mueven_con_ip():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0),))
    e = m.entrada(0)
    assert celda(m, 0, 1) == e.elemento.nombre
    assert celda(m, 0, 2) == str(e.elemento.vmid)
    assert celda(m, 0, 3) == e.elemento.nodo


# --- Contenido de la celda IP ---


def test_la_ip_obtenida_se_muestra_con_su_simbolo():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0, ip=con_ip("10.0.0.5")),))
    assert celda(m, 0, m.columna_ip) == "✓ 10.0.0.5"


def test_una_ip_a_revisar_lo_dice_con_texto_y_no_solo_con_color():
    m = ModeloLibro()
    e = entrada_ip(0, ip=con_ip("fe80::1", EstadoIp.OBTENIDA_PARCIAL))
    m.establecer_entradas((e,))
    assert "fe80::1" in celda(m, 0, m.columna_ip)
    assert "(a revisar)" in celda(m, 0, m.columna_ip)


def test_mientras_la_espera_esta_activa_una_maquina_lista_sin_ip_dice_esperando_la_ip():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0, EM.OK),))
    m.establecer_espera_activa(True)
    assert celda(m, 0, m.columna_ip) == "● Esperando la IP…"


def test_al_terminar_la_espera_sin_ip_la_celda_deja_de_decir_esperando():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0, EM.OK),))
    m.establecer_espera_activa(True)
    m.establecer_espera_activa(False)
    assert celda(m, 0, m.columna_ip) == "—"


def test_cambiar_el_estado_de_la_espera_repinta_solo_la_columna_ip(qtbot):
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0), entrada_ip(1)))
    with qtbot.waitSignal(m.dataChanged) as señal:
        m.establecer_espera_activa(True)
    arriba, abajo = señal.args[0], señal.args[1]
    assert (arriba.column(), abajo.column()) == (m.columna_ip, m.columna_ip)
    assert (arriba.row(), abajo.row()) == (0, 1)


def test_repetir_el_mismo_estado_de_espera_no_repinta(qtbot):
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0),))
    m.establecer_espera_activa(True)
    with qtbot.assertNotEmitted(m.dataChanged):
        m.establecer_espera_activa(True)


def test_una_maquina_en_curso_con_espera_de_ip_pendiente_dice_pendiente():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0, EM.CREANDO),))
    assert celda(m, 0, m.columna_ip) == "○ Pendiente"


def test_una_maquina_con_error_y_sin_ip_muestra_una_raya_no_esperando():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0, EM.ERROR),))
    m.establecer_espera_activa(True)
    assert celda(m, 0, m.columna_ip) == "—"


def test_una_maquina_que_no_pidio_ip_en_un_lote_con_otras_que_si_deja_la_celda_vacia():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0, esperar=False), entrada_ip(1)))
    assert celda(m, 0, m.columna_ip) == ""


@pytest.mark.parametrize("estado", list(EstadoIp))
def test_cada_estado_de_ip_tiene_simbolo_texto_y_color_y_nunca_el_codigo_crudo(estado):
    e = entrada_ip(0, ip=ResultadoIp(estado, principal="10.0.0.5"))
    texto = texto_celda_ip(e, espera_activa=True)
    assert texto and texto[0] == simbolo_estado_ip(estado)
    assert "_" not in texto  # ningún código en bruto, p. ej. «agente_no_responde»
    assert texto_estado_ip(estado)
    assert token_color_ip(e)


@pytest.mark.parametrize("estado", [e for e in EstadoIp if e is not EstadoIp.PENDIENTE])
def test_cada_estado_terminal_tiene_una_explicacion_en_lenguaje_llano(estado):
    texto = texto_detalle_ip(ResultadoIp(estado, principal="10.0.0.5"))
    assert texto
    assert "_" not in texto  # ningún código en bruto (agente_no_responde, sin_permiso…)
    assert "{" not in texto and "}" not in texto


def test_sin_permiso_nombra_el_privilegio_que_falta():
    error = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "VM.GuestAgent.Audit"})
    texto = texto_detalle_ip(ResultadoIp(EstadoIp.SIN_PERMISO, error=error))
    assert "VM.GuestAgent.Audit" in texto
    sin_nombre = texto_detalle_ip(ResultadoIp(EstadoIp.SIN_PERMISO))
    assert "VM.Monitor" in sin_nombre and "VM.GuestAgent.Audit" in sin_nombre


def test_una_ip_que_no_coincide_con_la_fija_lo_explica_con_la_ip_pedida():
    r = ResultadoIp(EstadoIp.OBTENIDA, principal="10.0.0.9", no_coincide=True)
    texto = texto_detalle_ip(r, ip_fija="10.0.0.5/24")
    assert "10.0.0.9" in texto and "10.0.0.5/24" in texto and "No coincide" in texto


def test_el_tooltip_de_la_celda_ip_es_la_explicacion_del_estado():
    m = ModeloLibro()
    r = ResultadoIp(EstadoIp.AGENTE_NO_RESPONDE)
    m.establecer_entradas((entrada_ip(0, ip=r),))
    tip = m.data(m.index(0, m.columna_ip), Qt.ItemDataRole.ToolTipRole)
    assert tip == tooltip_plano(texto_detalle_ip(r))  # escapado (M3)


def test_m3_un_nombre_de_interfaz_con_html_no_llega_al_tooltip_como_etiqueta():
    m = ModeloLibro()
    r = ResultadoIp(EstadoIp.SIN_IP, descartadas=("<b>eth0</b>", '<img src="http://x/a.png">'))
    m.establecer_entradas((entrada_ip(0, ip=r),))
    tip = m.data(m.index(0, m.columna_ip), Qt.ItemDataRole.ToolTipRole)
    assert "<b>" not in tip and "<img" not in tip
    assert "&lt;b&gt;eth0&lt;/b&gt;" in tip and "&lt;img" in tip
    assert tip.startswith("<qt>")  # texto enriquecido forzado: lo escapado se ve literal


def test_el_texto_accesible_de_la_fila_incluye_la_ip_cuando_hay_columna_ip():
    m = ModeloLibro()
    m.establecer_entradas((entrada_ip(0, ip=con_ip("10.0.0.5")),))
    accesible = m.data(m.index(0, 0), Qt.ItemDataRole.AccessibleTextRole)
    assert "IP: ✓ 10.0.0.5" in accesible
    sin = ModeloLibro()
    sin.establecer_entradas(entradas_de([EM.OK]))
    assert "IP:" not in sin.data(sin.index(0, 0), Qt.ItemDataRole.AccessibleTextRole)


# --- Resumen de IPs: «esperando» se separa de «sin IP» ---


def test_el_resumen_de_ips_cuenta_con_ip_sin_ip_y_no_aplicable():
    entradas = (
        entrada_ip(0, ip=con_ip("10.0.0.5")),
        entrada_ip(1, ip=ResultadoIp(EstadoIp.AGENTE_NO_RESPONDE)),
        entrada_ip(2, esperar=False),
    )
    assert texto_resumen_ips(resumen_ips(entradas)) == "1 con IP · 1 sin IP · 1 no aplicable"


def test_el_resumen_separa_las_que_esperan_de_las_que_no_tienen_ip():
    entradas = (
        entrada_ip(0, ip=con_ip("10.0.0.5")),
        entrada_ip(1),  # sigue esperando: sin resultado todavía
        entrada_ip(2, ip=ResultadoIp(EstadoIp.SIN_IP)),
    )
    texto = texto_resumen_ips(resumen_ips(entradas), esperando=1)
    assert texto == "1 con IP · 1 sin IP · 0 no aplicable · 1 esperando"


def test_mientras_esperan_todas_el_resumen_dice_cero_sin_ip():
    entradas = (entrada_ip(0), entrada_ip(1), entrada_ip(2))
    texto = texto_resumen_ips(resumen_ips(entradas), esperando=3)
    assert texto.startswith("0 con IP · 0 sin IP") and texto.endswith("3 esperando")


def test_el_resumen_nunca_da_numeros_negativos_si_esperando_supera_a_sin_ip():
    entradas = (entrada_ip(0),)
    texto = texto_resumen_ips(resumen_ips(entradas), esperando=5)
    assert "-" not in texto.replace("·", "")


def test_sin_nadie_esperando_el_resumen_no_menciona_esperando():
    assert "esperando" not in texto_resumen_ips(resumen_ips((entrada_ip(0),)), esperando=0)


def test_el_aviso_de_espera_concuerda_en_singular_y_plural():
    assert "1 máquina;" in texto_esperando_ips(1)
    assert "1 máquinas" not in texto_esperando_ips(1)
    assert "3 máquinas;" in texto_esperando_ips(3)


# --- ProgresoLote: botones y resumen ---


def test_ca_b3_6_4_sin_b3_no_se_muestra_la_fila_de_ips_ni_exportar_ips(progreso):
    poner(progreso, entradas_de([EM.OK, EM.OK]))
    assert not progreso.boton_exportar_ips.isVisibleTo(progreso)
    assert not progreso.boton_copiar_ips.isVisibleTo(progreso)
    assert not progreso.boton_dejar_ip.isVisibleTo(progreso)
    assert progreso.modelo.columnCount() == 5


def test_ca_b3_6_4_con_b3_el_boton_exportar_ips_se_muestra(progreso):
    poner(progreso, (entrada_ip(0, ip=con_ip("10.0.0.5")), entrada_ip(1)))
    assert progreso.boton_exportar_ips.isVisibleTo(progreso)
    assert progreso.boton_exportar_ips.text() == "Exportar IPs…"
    assert progreso.boton_copiar_ips.isVisibleTo(progreso)


def test_ca_b3_6_4_el_boton_exportar_emite_la_senal_y_no_escribe_nada(qtbot, progreso):
    poner(progreso, (entrada_ip(0, ip=con_ip("10.0.0.5")),))
    with qtbot.waitSignal(progreso.exportar_ips_solicitado, timeout=1000):
        progreso.boton_exportar_ips.click()


def test_dejar_de_esperar_la_ip_solo_se_ve_mientras_alguna_maquina_espera(progreso):
    poner(progreso, (entrada_ip(0), entrada_ip(1)))
    progreso.establecer_espera_ip(0)
    assert not progreso.boton_dejar_ip.isVisibleTo(progreso)
    progreso.establecer_espera_ip(2)
    assert progreso.boton_dejar_ip.isVisibleTo(progreso)
    assert progreso.esperando_ip is True
    progreso.establecer_espera_ip(0)
    assert not progreso.boton_dejar_ip.isVisibleTo(progreso)
    assert progreso.esperando_ip is False


def test_ca_b3_5_3_dejar_de_esperar_la_ip_emite_su_senal_y_no_cancela_el_lote(qtbot, progreso):
    poner(progreso, (entrada_ip(0), entrada_ip(1)))
    progreso.establecer_espera_ip(2)
    cancelar = []
    progreso.cancelar_solicitado.connect(lambda: cancelar.append(1))
    with qtbot.waitSignal(progreso.dejar_de_esperar_ip_solicitado, timeout=1000):
        progreso.boton_dejar_ip.click()
    assert cancelar == []
    assert progreso.boton_dejar_ip.text() == "Dejar de esperar la IP"
    assert progreso.boton_dejar_ip.text() != progreso.boton_cancelar.text()


def test_el_boton_dejar_de_esperar_la_ip_no_es_el_de_dejar_de_esperar_la_creacion(progreso):
    poner(progreso, (entrada_ip(0),), fase=FaseLote.CANCELANDO)
    assert progreso.boton_cancelar.text() == "Dejar de esperar"
    assert progreso.boton_dejar_ip.text() == "Dejar de esperar la IP"


def test_el_resumen_del_progreso_separa_esperando_de_sin_ip(progreso):
    poner(progreso, (entrada_ip(0, ip=con_ip("10.0.0.5")), entrada_ip(1), entrada_ip(2)))
    progreso.establecer_espera_ip(2)
    assert progreso.texto_resumen_de_ips == "1 con IP · 0 sin IP · 0 no aplicable · 2 esperando"
    progreso.establecer_espera_ip(0)
    assert progreso.texto_resumen_de_ips == "1 con IP · 2 sin IP · 0 no aplicable"


def test_el_aviso_la_creacion_termino_solo_sale_cuando_la_creacion_acabo(progreso):
    poner(progreso, (entrada_ip(0), entrada_ip(1)))
    progreso.establecer_espera_ip(2, creacion_terminada=False)
    assert "La creación terminó" not in textos(progreso)
    progreso.establecer_espera_ip(2, creacion_terminada=True)
    assert "La creación terminó" in textos(progreso)
    assert "2 máquinas" in textos(progreso)
    progreso.establecer_espera_ip(0)
    assert "La creación terminó" not in textos(progreso)


def textos(raiz) -> str:
    from PySide6.QtWidgets import QLabel

    return "\n".join(
        lbl.text() for lbl in raiz.findChildren(QLabel) if lbl.isVisibleTo(raiz) and lbl.text()
    )


def test_copiar_lista_de_ips_deja_nombre_tabulador_ip_solo_de_las_que_tienen_ip(progreso):
    poner(
        progreso,
        (
            entrada_ip(0, ip=con_ip("10.0.0.5")),
            entrada_ip(1),
            entrada_ip(2, ip=con_ip("10.0.0.7")),
        ),
    )
    progreso.boton_copiar_ips.click()
    assert QApplication.clipboard().text() == "web-01\t10.0.0.5\nweb-03\t10.0.0.7"


def test_copiar_lista_de_ips_esta_deshabilitado_mientras_ninguna_tiene_ip(progreso):
    poner(progreso, (entrada_ip(0), entrada_ip(1)))
    progreso.establecer_espera_ip(2)
    assert not progreso.boton_copiar_ips.isEnabled()
    progreso.actualizar((entrada_ip(0, ip=con_ip("10.0.0.5")), entrada_ip(1)))
    assert progreso.boton_copiar_ips.isEnabled()


def test_la_tabla_del_progreso_muestra_la_columna_ip_solo_con_b3(progreso):
    poner(progreso, entradas_de([EM.OK]))
    assert cabeceras(progreso.modelo) == CABECERAS_060
    poner(progreso, (entrada_ip(0, ip=con_ip("10.0.0.5")),))
    assert cabeceras(progreso.modelo)[4] == "IP"


def test_el_resumen_de_ips_y_los_botones_se_reinician_con_un_lote_nuevo(progreso):
    poner(progreso, (entrada_ip(0),))
    progreso.establecer_espera_ip(1)
    assert progreso.boton_dejar_ip.isVisibleTo(progreso)
    progreso.iniciar(plan_vacio(1))
    assert not progreso.esperando_ip
    progreso.actualizar(entradas_de([EM.PENDIENTE]))
    assert not progreso.boton_dejar_ip.isVisibleTo(progreso)


# --- PanelProgreso: una sola máquina ---


@pytest.fixture
def panel(qtbot):
    p = PanelProgreso()
    qtbot.addWidget(p)
    p.show()
    return p


def test_una_sola_maquina_ofrece_dejar_de_esperar_la_ip_mientras_espera(qtbot, panel):
    assert not panel.boton_dejar_ip.isVisibleTo(panel)
    panel.ofrecer_dejar_de_esperar_ip(True)
    assert panel.boton_dejar_ip.isVisibleTo(panel)
    assert panel.boton_dejar_ip.text() == "Dejar de esperar la IP"
    with qtbot.waitSignal(panel.dejar_de_esperar_ip_solicitado, timeout=1000):
        panel.boton_dejar_ip.click()
    panel.ofrecer_dejar_de_esperar_ip(False)
    assert not panel.boton_dejar_ip.isVisibleTo(panel)


def test_el_boton_de_dejar_de_esperar_la_ip_se_oculta_al_reiniciar_el_panel(panel):
    panel.ofrecer_dejar_de_esperar_ip(True)
    panel.reiniciar()
    assert not panel.boton_dejar_ip.isVisibleTo(panel)


def test_el_boton_de_una_maquina_tiene_ayuda_que_dice_que_la_maquina_no_se_toca(panel):
    assert "no se toca" in panel.boton_dejar_ip.toolTip()


# --- Piezas auxiliares usadas por los datos de prueba ---


def test_los_datos_de_prueba_construyen_entradas_coherentes():
    e = entrada_ip(2, nombre="db-01")
    assert e.elemento.nombre == "db-01" and e.elemento.vmid == 103
    assert e.elemento.cfg.esperar_ip is True
    assert definicion(1) is not None and elemento(0).vmid == 101


# --- Informe: sección «Direcciones IP» (RF-B3.6) ---


def test_el_informe_sin_b3_no_gana_la_seccion_de_direcciones_ip():
    from proxlaunch.interfaz.informe_lote import texto_informe

    from .apoyo_lote import informe_de

    texto = texto_informe(informe_de(entradas_de([EM.OK, EM.OK])))
    assert "Direcciones IP" not in texto


def test_el_informe_con_b3_lista_ip_estado_y_explicacion_de_las_que_no_la_tienen():
    from proxlaunch.interfaz.informe_lote import texto_informe

    from .apoyo_lote import informe_de

    entradas = (
        entrada_ip(0, ip=con_ip("10.0.0.5")),
        entrada_ip(1, ip=ResultadoIp(EstadoIp.AGENTE_NO_RESPONDE)),
        entrada_ip(2, esperar=False),
    )
    texto = texto_informe(informe_de(entradas))
    assert "Direcciones IP" in texto
    assert "1 con IP · 1 sin IP · 1 no aplicable" in texto
    assert "10.0.0.5" in texto
    assert "El agente invitado no respondió" in texto
    assert "agente_no_responde" not in texto
    assert "web-03" not in texto.split("Direcciones IP", 1)[1].split("•")[0]  # no pidió IP


def test_el_informe_con_b3_no_incluye_contrasenas_ni_cloudinit():
    from proxlaunch.interfaz.informe_lote import texto_informe

    from .apoyo_fase_b import CENTINELA
    from .apoyo_lote import informe_de

    texto = texto_informe(informe_de((entrada_ip(0, ip=con_ip("10.0.0.5")),)))
    assert CENTINELA not in texto
    assert "cipassword" not in texto
