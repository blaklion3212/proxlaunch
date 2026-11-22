"""Formulario de una máquina con la fase B (0.7.0): sección de cloud-init solo al clonar, casilla
«Esperar la IP», avisos del agente, cambio de servidor y propiedad de la contraseña.

Derivadas de docs/requisitos/fase-b.md: CA-B0.1.3, CA-B1.2.3, CA-B3.8.1, CA-B3.8.2, CA-B8.1.1,
RF-B3.1, V-B60, V-B63 y CL-B20; y de docs/arquitectura/fase-b.md §14 (cesión del ``Secreto``).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QToolButton

from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.nucleo.agente.validacion import validar_espera_ip
from proxlaunch.nucleo.modelos.origen import DetalleClon, RefPlantilla
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_fase_a import caps_de
from .apoyo_fase_b import (
    CENTINELA,
    disponibilidad,
    info_plantilla,
    textos_visibles,
)
from .apoyo_mvp4 import VOLID_ISO, caps_origen, inv_origen, plantilla_pve, volumen
from .test_fase_b_seccion_cloudinit import permisos_sin


@pytest.fixture
def formulario(qtbot):
    inv = inv_origen()
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    f.selector_origen.establecer_capacidades(caps_origen(inv))
    f.selector_origen.establecer_catalogo(
        [volumen(VOLID_ISO)], [plantilla_pve(nombre="plantilla-ubuntu-2404")], nodo="pve"
    )
    f.establecer_modo(True)
    return f


def clonar(f: FormularioVM) -> None:
    f.selector_origen.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    f.establecer_info_cloudinit(info_plantilla(), disponibilidad())


def escribir(campo, texto: str) -> None:
    campo.setText(texto)
    campo.textEdited.emit(texto)


# --- CA-B1.2.3: la sección solo existe al clonar ---


def test_ca_b1_2_3_la_seccion_de_cloudinit_solo_se_muestra_al_clonar_una_plantilla(formulario):
    seccion = formulario.seccion_cloudinit
    assert not seccion.isVisibleTo(formulario)
    for origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO, OrigenSO.DISCO_VACIO):
        formulario.selector_origen.opciones[origen].setChecked(True)
        assert not seccion.isVisibleTo(formulario), origen
    formulario.selector_origen.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    assert seccion.isVisibleTo(formulario)
    formulario.selector_origen.opciones[OrigenSO.DISCO_VACIO].setChecked(True)
    assert not seccion.isVisibleTo(formulario)


def test_ca_b1_2_3_sin_clonar_no_se_pide_cloudinit_aunque_haya_algo_escrito(formulario):
    clonar(formulario)
    escribir(formulario.seccion_cloudinit.txt_usuario, "deploy")
    assert formulario.configuracion().cloudinit is not None
    formulario.selector_origen.opciones[OrigenSO.DISCO_VACIO].setChecked(True)
    assert formulario.configuracion().cloudinit is None


# --- CA-B0.1.3: sin opciones de la fase B, nada nuevo en la configuración ---


def test_ca_b0_1_3_sin_ninguna_opcion_de_la_fase_b_la_configuracion_no_lleva_nada(formulario):
    clonar(formulario)
    cfg = formulario.configuracion()
    assert cfg.cloudinit is None
    assert cfg.esperar_ip is False


def test_ca_b0_1_3_sin_clonar_la_configuracion_tampoco_gana_cloudinit(formulario):
    cfg = formulario.configuracion()
    assert (cfg.cloudinit, cfg.esperar_ip) == (None, False)


def test_la_configuracion_recoge_lo_escrito_en_cloudinit_y_la_espera_de_ip(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    escribir(s.txt_usuario, "deploy")
    formulario.chk_encender.setChecked(True)
    formulario.chk_esperar_ip.setChecked(True)
    escribir(formulario.txt_plazo_ip, "90")
    cfg = formulario.configuracion()
    assert cfg.cloudinit.usuario == "deploy"
    assert (cfg.esperar_ip, cfg.plazo_ip_s) == (True, 90)


def test_la_contrasena_escrita_llega_a_la_configuracion_como_secreto_y_no_en_el_repr(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    escribir(s.txt_contrasena, CENTINELA)
    escribir(s.txt_repeticion, CENTINELA)
    cfg = formulario.configuracion()
    assert cfg.cloudinit.contrasena.revelar() == CENTINELA
    assert CENTINELA not in repr(cfg)
    assert CENTINELA not in str(cfg.cloudinit)


# --- RF-B3.1 / V-B60 / V-B63: la casilla «Esperar la IP» ---


def test_esperar_ip_sin_encender_esta_deshabilitada_y_el_motivo_se_ve(formulario):
    clonar(formulario)
    assert not formulario.chk_encender.isChecked()
    assert not formulario.chk_esperar_ip.isEnabled()
    assert not formulario.txt_plazo_ip.isEnabled()
    assert "encendida" in textos_visibles(formulario.fila_esperar_ip)
    assert "Encender al terminar" in formulario.chk_esperar_ip.accessibleDescription()


def test_al_encender_la_casilla_de_esperar_ip_se_habilita_y_el_plazo_sigue_a_la_casilla(
    formulario,
):
    clonar(formulario)
    formulario.chk_encender.setChecked(True)
    assert formulario.chk_esperar_ip.isEnabled()
    assert not formulario.txt_plazo_ip.isEnabled()
    formulario.chk_esperar_ip.setChecked(True)
    assert formulario.txt_plazo_ip.isEnabled()
    formulario.chk_esperar_ip.setChecked(False)
    assert not formulario.txt_plazo_ip.isEnabled()


def test_desmarcar_encender_desmarca_esperar_ip_y_avisa_de_que_se_restablecio(formulario):
    clonar(formulario)
    formulario.chk_encender.setChecked(True)
    formulario.chk_esperar_ip.setChecked(True)
    cambios = []
    formulario.cambiado.connect(lambda: cambios.append(1))
    formulario.chk_encender.setChecked(False)
    assert not formulario.chk_esperar_ip.isChecked()
    assert formulario.configuracion().esperar_ip is False
    assert "restableci" in textos_visibles(formulario.fila_esperar_ip)
    assert cambios


def test_v_b63_sin_el_privilegio_del_agente_la_casilla_se_deshabilita_y_nombra_el_privilegio(
    formulario,
):
    clonar(formulario)
    formulario.chk_encender.setChecked(True)
    permisos = permisos_sin("VM.GuestAgent.Audit")
    formulario.establecer_info_cloudinit(
        info_plantilla(), disponibilidad(permisos=permisos, version=(9, 2))
    )
    assert not formulario.chk_esperar_ip.isEnabled()
    assert "VM.GuestAgent.Audit" in textos_visibles(formulario.fila_esperar_ip)


def test_v_b63_con_proxmox_8_4_el_privilegio_del_agente_es_vm_monitor(formulario):
    clonar(formulario)
    formulario.chk_encender.setChecked(True)
    permisos = permisos_sin("VM.Monitor")
    # El rol base no trae VM.Monitor: se parte de uno que sí tiene lo demás.
    formulario.establecer_info_cloudinit(
        info_plantilla(), disponibilidad(permisos=permisos, version=(8, 4))
    )
    assert not formulario.chk_esperar_ip.isEnabled()
    assert "VM.Monitor" in textos_visibles(formulario.fila_esperar_ip)
    assert "VM.GuestAgent" not in textos_visibles(formulario.fila_esperar_ip)


def test_v_b63_con_proxmox_8_4_y_vm_monitor_concedido_la_casilla_se_habilita(formulario):
    from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
    from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH

    clonar(formulario)
    formulario.chk_encender.setChecked(True)
    privilegios = (*ROL_PROXLAUNCH, "VM.Config.Cloudinit", "VM.Monitor")
    permisos = PermisosEfectivos(rutas={"/": dict.fromkeys(privilegios, 1)})
    formulario.establecer_info_cloudinit(
        info_plantilla(), disponibilidad(permisos=permisos, version=(8, 4))
    )
    assert formulario.chk_esperar_ip.isEnabled()
    formulario.chk_esperar_ip.setChecked(True)
    assert formulario.configuracion().esperar_ip is True


def test_la_casilla_del_agente_solo_aparece_con_esperar_ip_y_una_plantilla_sin_agente(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    assert not s.fila_agente.isVisibleTo(s)
    formulario.chk_encender.setChecked(True)
    formulario.chk_esperar_ip.setChecked(True)
    assert s.fila_agente.isVisibleTo(s)
    info = info_plantilla(agente=True)
    formulario.establecer_info_cloudinit(info, disponibilidad(info))
    assert not s.fila_agente.isVisibleTo(s)  # la plantilla ya lo tiene activado


def test_marcar_activar_agente_llega_a_la_configuracion_y_se_pierde_al_quitar_esperar_ip(
    formulario,
):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    formulario.chk_encender.setChecked(True)
    formulario.chk_esperar_ip.setChecked(True)
    s.chk_agente.setChecked(True)
    assert formulario.configuracion().cloudinit.activar_agente is True
    formulario.chk_esperar_ip.setChecked(False)
    assert not s.chk_agente.isChecked()
    assert formulario.configuracion().cloudinit is None


# --- CA-B3.8.1 / CA-B3.8.2: aviso previo sobre el agente ---


def _cfg_con_espera(formulario: FormularioVM, nombre_plantilla: str, info):
    formulario.chk_encender.setChecked(True)
    formulario.chk_esperar_ip.setChecked(True)
    cfg = formulario.configuracion()
    cfg.detalle_origen = DetalleClon(plantilla=RefPlantilla(nombre_plantilla, 9000, "pve"))
    cfg.info_cloudinit = info
    return cfg


def test_ca_b3_8_1_plantilla_ubuntu_sin_agente_muestra_v_b62_y_v_b64_junto_a_esperar_ip(
    formulario,
):
    clonar(formulario)
    info = info_plantilla(agente=False)
    cfg = _cfg_con_espera(formulario, "plantilla-ubuntu-2404", info)
    problemas = validar_espera_ip(cfg, caps_de((9, 2)))
    assert {p.codigo for p in problemas} == {"V-B62", "V-B64"}
    assert all(p.severidad == Severidad.AVISO for p in problemas)  # nunca bloquea

    formulario.aplicar_problemas(problemas)

    visible = textos_visibles(formulario.fila_esperar_ip)
    assert "no tiene activado el agente invitado" in visible
    assert "Ubuntu y Debian no traen el agente" in visible
    assert not formulario.fila_esperar_ip.hay_error


def test_ca_b3_8_2_plantilla_con_agente_solo_muestra_v_b64_si_el_nombre_sugiere_ubuntu(
    formulario,
):
    clonar(formulario)
    info = info_plantilla(agente=True)
    cfg = _cfg_con_espera(formulario, "plantilla-ubuntu-2404", info)
    problemas = validar_espera_ip(cfg, caps_de((9, 2)))
    assert [p.codigo for p in problemas] == ["V-B64"]

    formulario.aplicar_problemas(problemas)

    visible = textos_visibles(formulario.fila_esperar_ip)
    assert "Ubuntu y Debian no traen el agente" in visible
    assert "no tiene activado el agente invitado" not in visible


def test_ca_b3_8_2_plantilla_con_agente_y_nombre_neutro_no_muestra_ningun_aviso(formulario):
    clonar(formulario)
    info = info_plantilla(agente=True)
    cfg = _cfg_con_espera(formulario, "base-rocky", info)
    assert validar_espera_ip(cfg, caps_de((9, 2))) == []
    formulario.aplicar_problemas([])
    assert "agente" not in textos_visibles(formulario.fila_esperar_ip)


def test_activar_el_agente_en_cloudinit_quita_el_aviso_v_b62(formulario):
    clonar(formulario)
    info = info_plantilla(agente=False)
    cfg = _cfg_con_espera(formulario, "base-rocky", info)
    formulario.seccion_cloudinit.chk_agente.setChecked(True)
    cfg.cloudinit = formulario.configuracion().cloudinit
    assert [p.codigo for p in validar_espera_ip(cfg, caps_de((9, 2)))] == []


# --- CA-B8.1.1: texto introductorio visible y «?» ---


def test_ca_b8_1_1_esperar_ip_tiene_texto_visible_y_un_boton_de_ayuda(formulario):
    clonar(formulario)
    fila = formulario.fila_esperar_ip
    assert fila.isVisibleTo(formulario)
    assert [b for b in fila.findChildren(QToolButton) if b.text() == "?" and b.toolTip()]
    assert fila._etiqueta.text() == "Esperar la IP"
    assert formulario.chk_esperar_ip.text()  # la casilla dice qué hace


# --- CL-B20: cambio de servidor ---


def test_cl_b20_al_reiniciar_con_otro_servidor_la_contrasena_se_borra_y_se_olvida(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    escribir(s.txt_contrasena, CENTINELA)
    escribir(s.txt_repeticion, CENTINELA)
    secreto = formulario.configuracion().cloudinit.contrasena

    formulario.establecer_inventario(inv_origen(), reiniciar=True)

    assert s.txt_contrasena.text() == "" and s.txt_repeticion.text() == ""
    assert not secreto.definido


def test_cl_b20_al_actualizar_el_inventario_sin_reiniciar_la_contrasena_se_conserva(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    escribir(s.txt_contrasena, CENTINELA)
    escribir(s.txt_repeticion, CENTINELA)
    formulario.establecer_inventario(inv_origen())
    assert s.txt_contrasena.text() == CENTINELA


def test_cl_b20_un_servidor_sin_privilegio_del_agente_desmarca_esperar_ip_con_aviso(formulario):
    clonar(formulario)
    formulario.chk_encender.setChecked(True)
    formulario.chk_esperar_ip.setChecked(True)
    formulario.establecer_info_cloudinit(
        info_plantilla(), disponibilidad(permisos=permisos_sin("VM.GuestAgent.Audit"))
    )
    assert not formulario.chk_esperar_ip.isChecked()
    assert "restableci" in textos_visibles(formulario.fila_esperar_ip)


def test_cl_b20_una_plantilla_nueva_sin_unidad_restablece_cloudinit_con_aviso(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    escribir(s.txt_usuario, "deploy")
    sin_unidad = info_plantilla(unidad=False)
    formulario.establecer_info_cloudinit(sin_unidad, disponibilidad(sin_unidad))
    assert s.txt_usuario.text() == ""
    assert "restableci" in textos_visibles(s)
    assert formulario.configuracion().cloudinit is None


def test_cl_b20_un_script_elegido_que_el_servidor_nuevo_no_ofrece_se_restablece(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    s.selectores_snippet["vendor"].establecer_valor("local:snippets/agente.yaml")
    assert formulario.configuracion().cloudinit.snippets.vendor == "local:snippets/agente.yaml"
    # El servidor nuevo no tiene almacenamiento de scripts.
    formulario.establecer_info_cloudinit(info_plantilla(), disponibilidad(snippets=False))
    assert s.selectores_snippet["vendor"].valor() is None
    assert "restableci" in textos_visibles(s)


# --- Cesión del Secreto al lote (§14) ---


def test_ceder_secreto_del_formulario_no_olvida_el_secreto_y_vacia_los_campos(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    escribir(s.txt_contrasena, CENTINELA)
    escribir(s.txt_repeticion, CENTINELA)
    secreto = formulario.configuracion().cloudinit.contrasena

    formulario.ceder_secreto()

    assert secreto.definido
    assert s.txt_contrasena.text() == ""


def test_limpiar_secretos_del_formulario_olvida_solo_lo_que_posee(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    escribir(s.txt_contrasena, CENTINELA)
    escribir(s.txt_repeticion, CENTINELA)
    cedido = formulario.configuracion().cloudinit.contrasena
    formulario.ceder_secreto()
    escribir(s.txt_contrasena, "Segunda-clave-99")
    escribir(s.txt_repeticion, "Segunda-clave-99")
    propio = formulario.configuracion().cloudinit.contrasena

    formulario.limpiar_secretos()

    assert cedido.definido
    assert not propio.definido


def test_preparar_otra_no_arrastra_la_contrasena(formulario):
    clonar(formulario)
    s = formulario.seccion_cloudinit
    escribir(s.txt_contrasena, CENTINELA)
    escribir(s.txt_repeticion, CENTINELA)
    formulario.preparar_otra()
    assert s.txt_contrasena.text() == ""
    cfg = formulario.configuracion()
    assert cfg.cloudinit is None or cfg.cloudinit.contrasena is None
