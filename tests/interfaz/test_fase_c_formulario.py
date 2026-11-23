"""Formulario de una máquina con la fase C (0.8.0): «Firewall de la máquina» y «Red de las copias»
dentro de ``FormularioVM`` (integración de las secciones; sus detalles los cubren
``test_fase_c_firewall.py`` y ``test_fase_c_red_clon.py``).

Derivadas de docs/requisitos/fase-c.md: CA-C0.1 y CA-C0.2 (sin opciones de C, nada nuevo en la
configuración), CA-C0.3.1 y CA-C0.3.2 (privilegio ausente o desconocido), CA-C0.4.1 (versión),
CA-C0.6.2 (el motivo de un control deshabilitado está a la vista), RF-C0.6 (texto introductorio y
«?» en cada sección nueva), RF-C3.1, RF-C4.1 (la red de las copias solo al clonar), V-C51, V-C32,
V-C36 y RF-C6.2 (los perfiles no tocan lo de C).
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtWidgets import QToolButton

from proxlaunch.interfaz.textos_c import texto_intro_firewall, texto_intro_red_clon
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import (
    FirewallMV,
    GrupoSeguridad,
    LecturaGrupos,
    ModoDhcp,
    Politica,
)
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.opciones.disponibilidad_c import disponibilidad_fase_c
from proxlaunch.nucleo.red.modelos import AccionTarjeta, ModoRedClon, RedClon, TarjetaClon
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_fase_b import textos_visibles
from .apoyo_mvp4 import VOLID_ISO, caps_origen, inv_origen, plantilla_pve, volumen

ROL = (
    "VM.Allocate", "VM.Audit", "VM.Config.Options", "VM.Config.HWType", "VM.Config.CPU",
    "VM.Config.Memory", "VM.Config.Network", "Datastore.AllocateSpace", "SDN.Use", "Sys.Audit",
    "VM.Config.Disk", "VM.Clone", "Datastore.AllocateTemplate", "Sys.AccessNetwork",
)  # fmt: skip
CAPS = Capacidades((9, 2), False)


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


def estados(permisos, caps=CAPS):
    from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos

    perm = None if permisos is None else PermisosEfectivos(rutas={"/": {p: 1 for p in permisos}})
    return disponibilidad_fase_c(perm, caps)


def rol_sin(*quitar: str) -> list[str]:
    return [p for p in ROL if p not in quitar]


# --- CA-C0.1 / CA-C0.2: sin opciones de C, nada nuevo en la configuración ---


def test_ca_c0_2_sin_ninguna_opcion_de_la_fase_c_la_configuracion_no_lleva_nada(formulario):
    cfg = formulario.configuracion()
    assert cfg.firewall is None and cfg.red_clon is None


def test_ca_c0_2_al_clonar_sin_tocar_nada_tampoco_hay_firewall_ni_red_del_clon(formulario):
    clonar(formulario)
    cfg = formulario.configuracion()
    assert cfg.firewall is None and cfg.red_clon is None


# --- RF-C3.1: firewall plegado y apagado, con cualquier origen ---


def test_rf_c3_1_la_seccion_del_firewall_existe_apagada_y_plegada_con_cualquier_origen(formulario):
    s = formulario.seccion_firewall
    for origen in OrigenSO:
        formulario.selector_origen.opciones[origen].setChecked(True)
        assert s.isVisibleTo(formulario), origen
        assert not s.chk_activar.isChecked()
        assert not s._cuerpo.isVisibleTo(s)  # plegada: el cuerpo no se ve hasta activarla


def test_rf_c3_1_activar_el_firewall_lo_lleva_a_la_configuracion_con_los_valores_por_defecto(
    formulario,
):
    formulario.seccion_firewall.chk_activar.setChecked(True)
    fw = formulario.configuracion().firewall
    assert fw == FirewallMV(
        activo=True,
        grupo=None,
        politica_entrada=Politica.BLOQUEAR,
        politica_salida=Politica.PERMITIR,
        dhcp=ModoDhcp.AUTO,
        acepto_aislada=False,
    )


def test_rf_c3_1_el_firewall_va_en_la_configuracion_aunque_no_se_clone(formulario):
    s = formulario.seccion_firewall
    for origen in (OrigenSO.ISO, OrigenSO.DISCO_VACIO):
        formulario.selector_origen.opciones[origen].setChecked(True)
        s.chk_activar.setChecked(True)
        assert formulario.configuracion().firewall.activo is True
        s.chk_activar.setChecked(False)
        assert formulario.configuracion().firewall is None


def test_rf_c3_1_activar_el_firewall_pide_los_grupos_una_vez(formulario, qtbot):
    with qtbot.waitSignal(formulario.pide_grupos_firewall, timeout=500):
        formulario.seccion_firewall.chk_activar.setChecked(True)


def test_rf_c3_2_elegir_un_grupo_de_la_lista_lo_lleva_a_la_configuracion(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    formulario.establecer_grupos_firewall(
        LecturaGrupos((GrupoSeguridad("web-01", "Web"), GrupoSeguridad("db-01")))
    )
    i = s.combo_grupo.findData("web-01")
    assert i > 0
    s.combo_grupo.setCurrentIndex(i)
    assert formulario.configuracion().firewall.grupo == "web-01"
    s.combo_grupo.setCurrentIndex(0)
    assert formulario.configuracion().firewall.grupo is None


def test_rf_c3_2_un_texto_escrito_que_no_es_un_grupo_de_la_lista_no_cuenta(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    formulario.establecer_grupos_firewall(LecturaGrupos((GrupoSeguridad("web-01"),)))
    s.combo_grupo.setEditText("inventado")
    assert formulario.configuracion().firewall.grupo is None


def test_v_c32_con_los_grupos_ilegibles_se_dice_en_llano_y_el_combo_se_bloquea(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    formulario.establecer_grupos_firewall(
        LecturaGrupos(None, ErrorProxLaunch(CodigoError.DESCONOCIDO))
    )
    assert not s.combo_grupo.isEnabled()
    visible = textos_visibles(s)
    assert "No pude leer los grupos de seguridad" in visible
    assert "V-C32" not in visible


def test_rf_c3_2_sin_grupos_en_el_servidor_se_explica(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    formulario.establecer_grupos_firewall(LecturaGrupos(()))
    assert "grupo" in textos_visibles(s).lower()
    assert formulario.configuracion().firewall.grupo is None


# --- V-C36: entrada Bloquear sin grupo: casilla de aislamiento ---


def test_v_c36_la_casilla_de_aislamiento_solo_se_ve_con_entrada_bloquear_y_sin_grupo(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    formulario.establecer_grupos_firewall(LecturaGrupos((GrupoSeguridad("web-01"),)))
    assert s.chk_aislada.isVisibleTo(s)
    s.chk_aislada.setChecked(True)
    assert formulario.configuracion().firewall.acepto_aislada is True
    s.combo_grupo.setCurrentIndex(s.combo_grupo.findData("web-01"))
    assert not s.chk_aislada.isVisibleTo(s)
    assert formulario.configuracion().firewall.acepto_aislada is False  # no se arrastra oculta
    s.combo_grupo.setCurrentIndex(0)
    s.combo_entrada.setCurrentIndex(s.combo_entrada.findData(Politica.PERMITIR))
    assert not s.chk_aislada.isVisibleTo(s)
    assert formulario.configuracion().firewall.acepto_aislada is False


def test_v_c36_el_riesgo_se_explica_con_la_entrada_en_bloquear_y_no_con_permitir(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    assert "Podrás usar la consola" in textos_visibles(s) or s._riesgo.isVisibleTo(s)
    s.combo_entrada.setCurrentIndex(s.combo_entrada.findData(Politica.PERMITIR))
    assert not s._riesgo.isVisibleTo(s)


# --- RF-C3.4: DHCP ---


def test_rf_c3_4_la_casilla_dhcp_se_marca_sola_si_hay_dhcp_y_deja_el_modo_automatico(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    s.establecer_hay_dhcp(True)
    assert s.chk_dhcp.isChecked()
    assert formulario.configuracion().firewall.dhcp == ModoDhcp.AUTO
    s.chk_dhcp.click()  # el usuario la desmarca: queda fijado
    assert formulario.configuracion().firewall.dhcp == ModoDhcp.NO
    s.chk_dhcp.click()
    assert formulario.configuracion().firewall.dhcp == ModoDhcp.SI


# --- RF-C4.1: la red de las copias solo al clonar ---


def test_rf_c4_1_la_seccion_de_red_de_las_copias_solo_se_muestra_al_clonar(formulario):
    s = formulario.seccion_red_clon
    assert not s.isVisibleTo(formulario)
    for origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO, OrigenSO.DISCO_VACIO):
        formulario.selector_origen.opciones[origen].setChecked(True)
        assert not s.isVisibleTo(formulario), origen
    clonar(formulario)
    assert s.isVisibleTo(formulario)
    formulario.selector_origen.opciones[OrigenSO.DISCO_VACIO].setChecked(True)
    assert not s.isVisibleTo(formulario)


def test_v_c51_sin_clonar_la_red_del_clon_no_llega_a_la_configuracion_aunque_estuviera_marcada(
    formulario,
):
    clonar(formulario)
    formulario.seccion_red_clon.radio_personalizar.setChecked(True)
    assert formulario.configuracion().red_clon.modo == ModoRedClon.PERSONALIZAR
    formulario.selector_origen.opciones[OrigenSO.DISCO_VACIO].setChecked(True)
    assert formulario.configuracion().red_clon is None


def test_rf_c4_1_como_la_plantilla_es_el_modo_por_defecto_y_no_envia_nada(formulario):
    clonar(formulario)
    s = formulario.seccion_red_clon
    assert s.radio_plantilla.isChecked() and not s.radio_personalizar.isChecked()
    assert formulario.configuracion().red_clon is None


# --- CA-C0.3.1 / CA-C0.6.2: privilegio ausente -> deshabilitado, con el motivo a la vista ---


def test_ca_c0_3_1_sin_vm_config_network_el_firewall_y_la_red_quedan_deshabilitados(formulario):
    clonar(formulario)
    formulario.establecer_disponibilidad_c(estados(rol_sin("VM.Config.Network")), CAPS)
    assert not formulario.seccion_firewall.chk_activar.isEnabled()
    assert not formulario.seccion_red_clon.radio_personalizar.isEnabled()
    # Se deshabilita, no se oculta (RF-C0.3).
    assert formulario.seccion_firewall.isVisibleTo(formulario)
    assert formulario.seccion_red_clon.isVisibleTo(formulario)


@pytest.mark.parametrize("seccion", ["seccion_firewall", "seccion_red_clon"])
def test_ca_c0_6_2_el_motivo_esta_visible_sin_pasar_el_raton_y_nombra_privilegio_y_ruta(
    formulario, seccion
):
    clonar(formulario)
    formulario.establecer_disponibilidad_c(estados(rol_sin("VM.Config.Network")), CAPS)
    visible = textos_visibles(getattr(formulario, seccion))
    assert "VM.Config.Network" in visible and "/vms" in visible


def test_ca_c0_3_1_el_resto_de_secciones_no_se_deshabilita(formulario):
    clonar(formulario)
    formulario.establecer_disponibilidad_c(estados(rol_sin("VM.Config.Network")), CAPS)
    assert formulario.seccion_cloudinit.isEnabled()
    assert formulario.tabla_redes.isEnabled()


def test_ca_c0_3_1_un_firewall_ya_activado_vuelve_a_apagado_con_aviso_al_perder_el_privilegio(
    formulario,
):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    formulario.establecer_disponibilidad_c(estados(rol_sin("VM.Config.Network")), CAPS)
    assert not s.chk_activar.isChecked()
    assert formulario.configuracion().firewall is None
    assert "Se restableció" in textos_visibles(s)


def test_ca_c0_3_1_una_red_personalizada_vuelve_a_como_la_plantilla_al_perder_el_privilegio(
    formulario,
):
    clonar(formulario)
    r = formulario.seccion_red_clon
    r.radio_personalizar.setChecked(True)
    formulario.establecer_disponibilidad_c(estados(rol_sin("VM.Config.Network")), CAPS)
    assert r.radio_plantilla.isChecked()
    assert formulario.configuracion().red_clon is None
    assert "Se restableció" in textos_visibles(r)


def test_ca_c0_3_2_con_permisos_desconocidos_los_controles_quedan_habilitados(formulario):
    clonar(formulario)
    formulario.establecer_disponibilidad_c(estados(None), CAPS)
    assert formulario.seccion_firewall.chk_activar.isEnabled()
    assert formulario.seccion_red_clon.radio_personalizar.isEnabled()


def test_ca_c0_3_1_con_el_rol_completo_todo_esta_habilitado_y_sin_motivo(formulario):
    clonar(formulario)
    formulario.establecer_disponibilidad_c(estados(ROL), CAPS)
    assert formulario.seccion_firewall.chk_activar.isEnabled()
    assert formulario.seccion_red_clon.radio_personalizar.isEnabled()
    assert "VM.Config.Network" not in textos_visibles(formulario.seccion_firewall)


def test_ca_c0_3_1_volver_a_tener_el_privilegio_rehabilita_los_controles(formulario):
    clonar(formulario)
    formulario.establecer_disponibilidad_c(estados(rol_sin("VM.Config.Network")), CAPS)
    formulario.establecer_disponibilidad_c(estados(ROL), CAPS)
    assert formulario.seccion_firewall.chk_activar.isEnabled()
    assert formulario.seccion_red_clon.radio_personalizar.isEnabled()


# --- CA-C0.4.1: versión ---


@pytest.mark.parametrize("version", [(8, 0), (9, 2)])
def test_ca_c0_4_1_con_8_0_y_9_2_las_secciones_estan_disponibles(formulario, version):
    clonar(formulario)
    caps = Capacidades(version, True)
    formulario.establecer_disponibilidad_c(estados(ROL, caps), caps)
    assert formulario.seccion_firewall.chk_activar.isEnabled()
    assert formulario.seccion_red_clon.radio_personalizar.isEnabled()


def test_ca_c0_4_1_en_una_version_sin_la_funcion_se_deshabilitan_con_la_version_minima(formulario):
    clonar(formulario)
    caps = Capacidades((7, 4), True)
    formulario.establecer_disponibilidad_c(estados(ROL, caps), caps)
    assert not formulario.seccion_firewall.chk_activar.isEnabled()
    assert "8.0" in textos_visibles(formulario.seccion_firewall)
    assert not formulario.seccion_red_clon.radio_personalizar.isEnabled()
    assert "8.0" in textos_visibles(formulario.seccion_red_clon)


def test_establecer_disponibilidad_c_es_idempotente_y_no_emite_cambios_de_mas(formulario, qtbot):
    e = estados(ROL)
    formulario.establecer_disponibilidad_c(e, CAPS)
    with qtbot.assertNotEmitted(formulario.cambiado):
        formulario.establecer_disponibilidad_c(e, CAPS)


# --- «Ver reglas» exige Sys.Audit en «/» (RF-C3.11) ---


def test_rf_c3_11_sin_sys_audit_ver_reglas_queda_deshabilitado_y_el_firewall_sigue_activable(
    formulario,
):
    s = formulario.seccion_firewall
    formulario.establecer_disponibilidad_c(estados(rol_sin("Sys.Audit")), CAPS)
    assert s.chk_activar.isEnabled()  # la creación no se bloquea
    s.chk_activar.setChecked(True)
    formulario.establecer_grupos_firewall(LecturaGrupos((GrupoSeguridad("web-01"),)))
    s.combo_grupo.setCurrentIndex(s.combo_grupo.findData("web-01"))
    assert not s.boton_reglas.isEnabled()
    assert "Sys.Audit" in textos_visibles(s)


# --- RF-C0.6: cada sección nueva lleva texto introductorio visible y un «?» ---


def test_rf_c0_6_cada_seccion_nueva_tiene_texto_introductorio_y_boton_de_ayuda(formulario):
    clonar(formulario)
    for seccion, intro in (
        (formulario.seccion_firewall, texto_intro_firewall()),
        (formulario.seccion_red_clon, texto_intro_red_clon()),
    ):
        assert intro in textos_visibles(seccion)
        botones = seccion.findChildren(QToolButton)
        assert botones and all(b.text() == "?" for b in botones)
        assert all(b.toolTip() for b in botones)


def test_rf_c0_6_los_botones_de_ayuda_del_firewall_explican_grupo_politicas_y_dhcp(formulario):
    ayudas = " ".join(b.toolTip() for b in formulario.seccion_firewall.findChildren(QToolButton))
    for palabra in ("firewall", "grupo de seguridad", "Bloquear", "DHCP"):
        assert palabra.lower() in ayudas.lower(), palabra


# --- Problemas junto a su sección: V-Cxx en español, sin códigos ---


def test_los_problemas_de_firewall_se_muestran_en_su_seccion_sin_el_codigo(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    formulario.aplicar_problemas(
        [
            Problema("firewall.grupo", "V-C30", Severidad.ERROR, {"grupo": "web-01"}),
            Problema("firewall", "V-C33", Severidad.AVISO, {}),
            Problema("firewall", "V-C50", Severidad.ERROR, {"version": "8.0"}),
        ]
    )
    visible = textos_visibles(s)
    assert "El grupo de seguridad «web-01» no existe" in visible
    assert "firewall general de Proxmox" in visible
    assert "8.0" in visible
    assert "V-C" not in visible


def test_los_problemas_de_la_red_del_clon_se_muestran_en_su_seccion_sin_el_codigo(formulario):
    clonar(formulario)
    r = formulario.seccion_red_clon
    r.radio_personalizar.setChecked(True)
    formulario.aplicar_problemas(
        [
            Problema("red_clon.tarjetas[0].vlan", "V-C15", Severidad.ERROR, {"tarjeta": "net0"}),
            Problema("red_clon", "V-C18", Severidad.AVISO, {}),
            Problema("redes", "V-C16", Severidad.ERROR, {"tarjeta": "1"}),
        ]
    )
    visible = textos_visibles(r)
    assert "entre 1 y 4094" in visible
    assert "sin tarjetas de red" in visible
    assert "V-C" not in visible


def test_los_problemas_de_una_seccion_no_aparecen_en_la_otra(formulario):
    clonar(formulario)
    formulario.seccion_firewall.chk_activar.setChecked(True)
    formulario.seccion_red_clon.radio_personalizar.setChecked(True)
    formulario.aplicar_problemas(
        [Problema("firewall.grupo", "V-C30", Severidad.ERROR, {"grupo": "x"})]
    )
    assert "no existe" not in textos_visibles(formulario.seccion_red_clon)


def test_sin_problemas_los_mensajes_de_las_secciones_se_limpian(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    formulario.aplicar_problemas(
        [Problema("firewall.grupo", "V-C30", Severidad.ERROR, {"grupo": "x"})]
    )
    assert "no existe" in textos_visibles(s)
    formulario.aplicar_problemas([])
    assert "no existe" not in textos_visibles(s)


# --- RF-C6.2: aplicar un perfil no toca lo de C; un lote guardado sí lo carga ---

FW = FirewallMV(activo=True, grupo="web-01", politica_entrada=Politica.PERMITIR)
RED = RedClon(ModoRedClon.PERSONALIZAR, (TarjetaClon(1, AccionTarjeta.QUITAR),))


def test_rf_c6_2_aplicar_un_perfil_conserva_el_firewall_del_formulario(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    cfg = formulario.configuracion()
    formulario.aplicar_hardware(
        dataclasses.replace(cfg, memoria_mib=4096, firewall=None, red_clon=None),
        conservar_fase_c=True,
    )
    assert s.chk_activar.isChecked()
    assert formulario.configuracion().firewall is not None


def test_rf_c6_2_aplicar_un_perfil_conserva_la_red_personalizada_del_formulario(formulario):
    clonar(formulario)
    r = formulario.seccion_red_clon
    r.radio_personalizar.setChecked(True)
    cfg = formulario.configuracion()
    formulario.aplicar_hardware(
        dataclasses.replace(cfg, firewall=None, red_clon=None), origen=False, conservar_fase_c=True
    )
    assert r.radio_personalizar.isChecked()


def test_rf_c6_1_cargar_un_lote_guardado_carga_su_firewall(formulario):
    cfg = dataclasses.replace(formulario.configuracion(), firewall=FW)
    formulario.aplicar_hardware(cfg)
    fw = formulario.configuracion().firewall
    assert fw is not None and fw.activo and fw.politica_entrada == Politica.PERMITIR
    assert fw.grupo == "web-01"  # se muestra aunque aún no se haya leído la lista de grupos


def test_rf_c6_1_cargar_un_lote_guardado_sin_firewall_apaga_el_del_formulario(formulario):
    formulario.seccion_firewall.chk_activar.setChecked(True)
    cfg = dataclasses.replace(formulario.configuracion(), firewall=None, red_clon=None)
    formulario.aplicar_hardware(cfg)
    assert formulario.configuracion().firewall is None


def test_rf_c6_1_el_ciclo_configuracion_aplicar_configuracion_conserva_el_firewall(formulario):
    s = formulario.seccion_firewall
    s.chk_activar.setChecked(True)
    s.combo_salida.setCurrentIndex(s.combo_salida.findData(Politica.BLOQUEAR))
    s.chk_aislada.setChecked(True)
    antes = formulario.configuracion().firewall
    formulario.aplicar_configuracion(dataclasses.replace(formulario.configuracion()))
    assert formulario.configuracion().firewall == antes


def test_rf_c6_1_un_lote_guardado_con_red_personalizada_la_deja_pendiente_hasta_leer_la_plantilla(
    formulario,
):
    clonar(formulario)
    cfg = dataclasses.replace(formulario.configuracion(), red_clon=RED)
    formulario.aplicar_hardware(cfg)
    assert formulario.seccion_red_clon.radio_personalizar.isChecked()
