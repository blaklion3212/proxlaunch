"""Sección «Red de las copias» (fase C, 0.8.0): reescribir la red al clonar desde el formulario.

Derivadas de docs/requisitos/fase-c.md: RF-C4.1 (CA-C4.1.1, CA-C4.1.4), RF-C4.2 (CA-C4.2.3,
CA-C4.2.4), RF-C4.3 (CA-C4.3.2), RF-C4.4 (CA-C4.4.3, CA-C4.4.4), RF-C4.7 (CA-C4.7.1, CA-C4.7.2),
RF-C4.8 (CA-C4.8.2), RF-C0.3, V-C16, V-C17, CL-C13 y CL-C21. Sin red: solo widgets.
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtWidgets import QLabel

from proxlaunch.interfaz.textos_c import lineas_red_final, texto_problema_c
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.interfaz.vistas.seccion_red_clon import SeccionRedClon
from proxlaunch.interfaz.vistas.selector_origen import FuenteCatalogo
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.cloudinit.modelos import ModoTarjeta
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.inventario import Bridge, RedVirtual
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, OpcionC
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.red.modelos import (
    AccionTarjeta,
    CampoRed,
    ModoRedClon,
    RedClon,
    TarjetaClon,
    TarjetaFinal,
    red_clon_a_dict,
)
from proxlaunch.nucleo.red.tarjetas import tarjetas_de_config
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_fase_b import disponibilidad, info_plantilla
from .apoyo_mvp4 import (
    VOLID_ISO,
    caps_origen,
    detalle_plantilla,
    inv_origen,
    plantilla_pve,
    volumen,
)

MAC0, MAC1, MAC2 = "BC:24:11:00:00:00", "BC:24:11:00:00:01", "BC:24:11:00:00:02"
BRIDGES = (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "bridge", True))
VNETS = (RedVirtual("prod", "Producción", True), RedVirtual("plana", None, False))
CONFIG = {
    "net0": f"virtio={MAC0},bridge=vmbr0",
    "net1": f"virtio={MAC1},bridge=vmbr0,tag=20,mtu=1400,rate=5",
}


@pytest.fixture
def seccion(qtbot):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_modo_avanzado(True)
    s.establecer_redes(BRIDGES, VNETS)
    s.establecer_tarjetas(tarjetas_de_config(CONFIG))
    return s


def personalizar(s: SeccionRedClon) -> None:
    s.radio_personalizar.setChecked(True)


def fila(s: SeccionRedClon, indice: int):
    return next(f for f in s._filas if f.indice == indice)


def elegir(s: SeccionRedClon, indice: int, red: str) -> None:
    f = fila(s, indice)
    f.red.setCurrentIndex(f.red.findData(red))


def escribir(campo, texto: str) -> None:
    campo.setText(texto)
    campo.textEdited.emit(texto)


def visibles(raiz) -> str:
    return "\n".join(
        lbl.text() for lbl in raiz.findChildren(QLabel) if lbl.isVisibleTo(raiz) and lbl.text()
    )


# --- RF-C4.1: modo por defecto y modo personalizar -----------------------------------------------


def test_ca_c4_1_1_por_defecto_es_como_la_plantilla_y_no_se_pide_nada(seccion):
    assert not seccion.personaliza
    assert seccion.radio_plantilla.isChecked()
    assert seccion.red_clon() is None
    assert not seccion._cuerpo.isVisibleTo(seccion)


def test_ca_c4_1_2_personalizar_sin_tocar_nada_pide_una_red_sin_tarjetas_cambiadas(seccion):
    personalizar(seccion)
    red = seccion.red_clon()
    assert red == RedClon(ModoRedClon.PERSONALIZAR, ())
    assert seccion._cuerpo.isVisibleTo(seccion)


def test_ca_c4_1_2_volver_a_como_la_plantilla_descarta_la_peticion(seccion):
    personalizar(seccion)
    elegir(seccion, 0, "vmbr1")
    assert seccion.red_clon() is not None
    seccion.radio_plantilla.setChecked(True)
    assert seccion.red_clon() is None


def test_ca_c4_1_2_cambiar_la_red_de_una_tarjeta_fija_solo_ese_campo(seccion):
    personalizar(seccion)
    elegir(seccion, 0, "vmbr1")
    (t,) = seccion.red_clon().tarjetas
    assert (t.indice, t.accion, t.bridge) == (0, AccionTarjeta.CAMBIAR, "vmbr1")
    assert t.fijados == frozenset({CampoRed.BRIDGE})
    assert t.mac_nueva is False


def test_ca_c4_1_2_elegir_una_vnet_del_segundo_grupo_se_pide_por_su_nombre(seccion):
    personalizar(seccion)
    elegir(seccion, 1, "prod")
    (t,) = seccion.red_clon().tarjetas
    assert (t.indice, t.bridge) == (1, "prod")


def test_cl_c21_las_celdas_sin_tocar_conservan_el_valor_de_la_tarjeta(seccion):
    """Solo se fija lo que el usuario cambió; MTU, límite y VLAN de net1 quedan como están."""
    personalizar(seccion)
    elegir(seccion, 1, "vmbr1")
    (t,) = seccion.red_clon().tarjetas
    assert t.fijados == frozenset({CampoRed.BRIDGE})


def test_ca_c4_3_vaciar_una_celda_pide_quitar_ese_valor_y_no_conservarlo(seccion):
    personalizar(seccion)
    escribir(fila(seccion, 1).vlan, "")
    (t,) = seccion.red_clon().tarjetas
    assert t.fijados == frozenset({CampoRed.VLAN}) and t.vlan is None


def test_ca_c4_1_los_valores_de_la_plantilla_se_muestran_en_las_filas(seccion):
    f = fila(seccion, 1)
    assert f.vlan.text() == "20" and f.mtu.text() == "1400" and f.limite.text() == "5"
    assert f.red.currentData() == "vmbr0"
    assert f.modelo.currentData() == "virtio"


def test_ca_c4_1_mtu_y_limite_son_avanzados_y_se_ocultan_en_modo_basico(seccion):
    personalizar(seccion)
    assert fila(seccion, 0).mtu.isVisibleTo(seccion)
    seccion.establecer_modo_avanzado(False)
    assert not fila(seccion, 0).mtu.isVisibleTo(seccion)
    assert not fila(seccion, 0).limite.isVisibleTo(seccion)


def test_ca_c4_6_3_una_tarjeta_e1000_de_la_plantilla_muestra_la_mtu_deshabilitada(qtbot):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_modo_avanzado(True)
    s.establecer_redes(BRIDGES, VNETS)
    s.establecer_tarjetas(tarjetas_de_config({"net0": f"e1000={MAC0},bridge=vmbr0"}))
    personalizar(s)
    assert not fila(s, 0).mtu.isEnabled()


def test_ca_c4_6_3_la_mtu_se_deshabilita_al_cambiar_una_tarjeta_a_e1000(seccion):
    personalizar(seccion)
    f = fila(seccion, 0)
    assert f.mtu.isEnabled()
    f.modelo.setCurrentIndex(f.modelo.findData("e1000"))
    assert not f.mtu.isEnabled()


# --- RF-C2.2 en la red del clon ----------------------------------------------------------------


def test_ca_c2_2_1_una_vnet_no_vlanaware_deshabilita_la_vlan_con_el_motivo_y_la_borra(seccion):
    personalizar(seccion)
    assert fila(seccion, 1).vlan.text() == "20"
    elegir(seccion, 1, "plana")
    f = fila(seccion, 1)
    assert not f.vlan.isEnabled() and f.vlan.text() == ""
    assert "no admite VLAN" in f.vlan.toolTip()
    assert "no admite VLAN" in visibles(seccion)
    (t,) = seccion.red_clon().tarjetas
    assert t.bridge == "plana" and t.vlan is None
    assert t.fijados == frozenset({CampoRed.BRIDGE, CampoRed.VLAN})  # la VLAN se quita


def test_ca_c2_2_2_una_vnet_vlanaware_admite_vlan(seccion):
    personalizar(seccion)
    elegir(seccion, 0, "prod")
    f = fila(seccion, 0)
    assert f.vlan.isEnabled()
    escribir(f.vlan, "100")
    (t,) = seccion.red_clon().tarjetas
    assert (t.bridge, t.vlan) == ("prod", 100)


def test_ca_c2_2_5_un_bridge_admite_vlan_aunque_no_sea_vlanaware(seccion):
    personalizar(seccion)
    elegir(seccion, 0, "vmbr0")
    assert fila(seccion, 0).vlan.isEnabled()


def test_ca_c4_6_1_una_vlan_no_numerica_se_pide_como_0_y_la_regla_la_rechaza(seccion):
    personalizar(seccion)
    escribir(fila(seccion, 0).vlan, "abc")
    (t,) = seccion.red_clon().tarjetas
    assert t.vlan == 0


# --- RF-C4.3: MAC ---------------------------------------------------------------------------


def test_ca_c4_3_2_la_casilla_generar_mac_nueva_empieza_desmarcada_y_pide_mac_nueva(seccion):
    personalizar(seccion)
    f = fila(seccion, 0)
    assert not f.mac.isChecked()
    f.mac.setChecked(True)
    (t,) = seccion.red_clon().tarjetas
    assert t.mac_nueva is True and t.fijados == frozenset()
    f.mac.setChecked(False)
    assert seccion.red_clon().tarjetas == ()


def test_ca_c4_3_2_una_tarjeta_nueva_no_tiene_la_casilla_de_mac(seccion):
    personalizar(seccion)
    seccion._agregar.click()
    nueva = fila(seccion, 2)
    assert not nueva.mac.isVisibleTo(seccion)


# --- RF-C4.4: quitar y añadir --------------------------------------------------------------------


def test_ca_c4_4_1_quitar_marca_la_tarjeta_y_volver_a_pulsar_la_conserva(seccion):
    personalizar(seccion)
    f = fila(seccion, 1)
    f.boton.click()
    assert f.quitada
    assert seccion.red_clon().tarjetas == (TarjetaClon(1, AccionTarjeta.QUITAR),)
    assert f.boton.text() == "Conservar"
    assert "se quitará" in visibles(seccion)
    assert not f.red.isEnabled()
    f.boton.click()
    assert not f.quitada and seccion.red_clon().tarjetas == ()


def test_ca_c4_4_3_con_net0_y_net2_la_tarjeta_nueva_toma_net1(qtbot):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_redes(BRIDGES, VNETS)
    s.establecer_tarjetas(
        tarjetas_de_config(
            {"net0": f"virtio={MAC0},bridge=vmbr0", "net2": f"virtio={MAC2},bridge=vmbr0"}
        )
    )
    personalizar(s)
    s._agregar.click()
    t = [x for x in s.red_clon().tarjetas if x.accion == AccionTarjeta.ANADIR]
    assert [x.indice for x in t] == [1]
    # La nueva fila queda entre net0 y net2 en la rejilla.
    assert [f.indice for f in s._filas] == [0, 1, 2]


def test_ca_c4_4_una_tarjeta_nueva_pide_todos_sus_valores_y_se_puede_descartar(seccion):
    personalizar(seccion)
    seccion._agregar.click()
    nueva = fila(seccion, 2)
    assert nueva.red.currentData() == "vmbr0"  # la primera red disponible
    elegir(seccion, 2, "prod")
    escribir(nueva.vlan, "7")
    (t,) = [x for x in seccion.red_clon().tarjetas if x.accion == AccionTarjeta.ANADIR]
    assert (t.indice, t.bridge, t.vlan, t.modelo) == (2, "prod", 7, "virtio")
    nueva.boton.click()  # «Quitar» en una fila nueva la descarta
    assert [f.indice for f in seccion._filas] == [0, 1]
    assert seccion.red_clon().tarjetas == ()


def test_ca_c4_4_4_con_32_tarjetas_ya_presentes_anadir_da_v_c17_y_no_crea_fila(qtbot):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_redes(BRIDGES, VNETS)
    s.establecer_tarjetas(
        tarjetas_de_config(
            {f"net{i}": f"virtio=BC:24:11:00:01:{i:02X},bridge=vmbr0" for i in range(32)}
        )
    )
    personalizar(s)
    s._agregar.click()
    assert len(s._filas) == 32
    assert "32 tarjetas" in visibles(s)


def test_ca_c4_4_se_puede_anadir_hasta_el_indice_31_y_luego_no_mas(qtbot):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_redes(BRIDGES, VNETS)
    s.establecer_tarjetas(
        tarjetas_de_config(
            {f"net{i}": f"virtio=BC:24:11:00:01:{i:02X},bridge=vmbr0" for i in range(31)}
        )
    )
    personalizar(s)
    s._agregar.click()
    assert [f.indice for f in s._filas][-1] == 31
    s._agregar.click()
    assert len(s._filas) == 32


def test_ca_c4_2_4_una_plantilla_sin_tarjetas_lo_dice_y_permite_anadir(qtbot):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_redes(BRIDGES, VNETS)
    s.establecer_tarjetas(())
    personalizar(s)
    assert "no tiene tarjetas de red" in visibles(s)
    s._agregar.click()
    (t,) = s.red_clon().tarjetas
    assert (t.indice, t.accion) == (0, AccionTarjeta.ANADIR)
    assert "no tiene tarjetas de red" not in visibles(s)


def test_ca_c4_2_la_plantilla_sin_leer_lo_explica_y_no_deja_anadir(qtbot):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_redes(BRIDGES, VNETS)
    personalizar(s)
    assert not s._agregar.isEnabled()
    assert visibles(s) != ""  # texto de «sin leer» a la vista
    s.establecer_tarjetas(tarjetas_de_config(CONFIG))
    assert s._agregar.isEnabled()


# --- RF-C4.2: tarjeta ilegible ------------------------------------------------------------------


def test_ca_c4_2_3_una_tarjeta_ilegible_se_muestra_en_solo_lectura_y_no_se_pide(qtbot):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_redes(BRIDGES, VNETS)
    s.establecer_tarjetas(
        tarjetas_de_config({"net0": f"virtio={MAC0},bridge=vmbr0", "net1": "esto no se entiende"})
    )
    personalizar(s)
    f = fila(s, 1)
    assert not any(w.isEnabled() for w in (f.red, f.modelo, f.vlan, f.boton, f.mac))
    assert "No entendí la tarjeta" in visibles(s)
    elegir(s, 0, "vmbr1")
    assert [t.indice for t in s.red_clon().tarjetas] == [0]
    f.boton.click()  # deshabilitado: aun así no puede quitarla
    assert [t.indice for t in s.red_clon().tarjetas] == [0]


# --- Plantilla distinta, carga de lotes y disponibilidad ----------------------------------------


def test_ca_c4_1_cambiar_de_plantilla_descarta_lo_elegido_porque_era_de_otra(seccion):
    personalizar(seccion)
    elegir(seccion, 0, "vmbr1")
    seccion.establecer_tarjetas(tarjetas_de_config({"net0": f"virtio={MAC0},bridge=vmbr1"}))
    assert seccion.red_clon().tarjetas == ()
    assert [f.indice for f in seccion._filas] == [0]


def test_ca_c4_1_la_misma_plantilla_releida_no_pierde_lo_elegido(seccion):
    personalizar(seccion)
    elegir(seccion, 0, "vmbr1")
    seccion.establecer_tarjetas(tarjetas_de_config(CONFIG))  # mismas tarjetas
    assert [t.bridge for t in seccion.red_clon().tarjetas] == ["vmbr1"]


def test_ca_c4_1_cambiar_las_redes_del_nodo_conserva_la_eleccion_si_sigue_existiendo(seccion):
    personalizar(seccion)
    elegir(seccion, 0, "vmbr1")
    seccion.establecer_redes(BRIDGES, ())
    assert fila(seccion, 0).red.currentData() == "vmbr1"


def test_ca_c4_1_aplicar_y_leer_son_inversas_para_cambiar_quitar_y_anadir(seccion):
    red = RedClon(
        ModoRedClon.PERSONALIZAR,
        (
            TarjetaClon(
                0,
                AccionTarjeta.CAMBIAR,
                bridge="prod",
                vlan=50,
                fijados=frozenset({CampoRed.BRIDGE, CampoRed.VLAN}),
                mac_nueva=True,
            ),
            TarjetaClon(1, AccionTarjeta.QUITAR),
            TarjetaClon(2, AccionTarjeta.ANADIR, bridge="vmbr1", modelo="e1000", vlan=9),
        ),
    )
    seccion.aplicar(red)
    assert seccion.personaliza
    assert red_clon_a_dict(seccion.red_clon()) == red_clon_a_dict(red)


def test_ca_c4_1_aplicar_un_lote_antes_de_conocer_las_tarjetas_se_aplica_al_llegar_la_plantilla(
    qtbot,
):
    s = SeccionRedClon()
    qtbot.addWidget(s)
    s.show()
    s.establecer_redes(BRIDGES, VNETS)
    red = RedClon(
        ModoRedClon.PERSONALIZAR,
        (
            TarjetaClon(
                1, AccionTarjeta.CAMBIAR, bridge="prod", fijados=frozenset({CampoRed.BRIDGE})
            ),
        ),
    )
    s.aplicar(red)
    assert s.personaliza
    s.establecer_tarjetas(tarjetas_de_config(CONFIG))
    assert red_clon_a_dict(s.red_clon()) == red_clon_a_dict(red)


def test_ca_c4_1_aplicar_none_vuelve_a_como_la_plantilla(seccion):
    personalizar(seccion)
    elegir(seccion, 0, "vmbr1")
    seccion.aplicar(None)
    assert not seccion.personaliza and seccion.red_clon() is None
    seccion.aplicar(RedClon())  # modo plantilla
    assert seccion.red_clon() is None


def test_ca_c4_1_aplicar_ignora_acciones_sobre_tarjetas_que_la_plantilla_no_tiene(seccion):
    red = RedClon(
        ModoRedClon.PERSONALIZAR,
        (
            TarjetaClon(7, AccionTarjeta.QUITAR),
            TarjetaClon(0, AccionTarjeta.ANADIR, bridge="vmbr0"),  # índice ocupado
            TarjetaClon(40, AccionTarjeta.ANADIR, bridge="vmbr0"),  # fuera de rango
        ),
    )
    seccion.aplicar(red)
    assert seccion.red_clon().tarjetas == ()


def test_rf_c0_3_sin_privilegio_personalizar_se_deshabilita_con_el_motivo_y_se_restablece(seccion):
    personalizar(seccion)
    estado = EstadoOpcion(
        OpcionC.RED_CLON,
        Disponibilidad.NO,
        CodigoError.OPCION_SIN_PRIVILEGIO,
        {"privilegio": "VM.Config.Network", "ruta": "/vms/<vmid>"},
    )
    seccion.establecer_disponibilidad(estado)
    assert not seccion.radio_personalizar.isEnabled()
    assert seccion.radio_plantilla.isChecked() and seccion.red_clon() is None
    assert "VM.Config.Network" in visibles(seccion)
    seccion.establecer_disponibilidad(None)
    assert seccion.radio_personalizar.isEnabled()
    assert "VM.Config.Network" not in visibles(seccion)


def test_cambiado_se_emite_ante_cada_edicion(seccion, qtbot):
    personalizar(seccion)
    with qtbot.waitSignal(seccion.cambiado, timeout=500):
        elegir(seccion, 0, "vmbr1")
    with qtbot.waitSignal(seccion.cambiado, timeout=500):
        fila(seccion, 1).boton.click()
    with qtbot.waitSignal(seccion.cambiado, timeout=500):
        escribir(fila(seccion, 0).vlan, "5")


def test_ca_c4_1_indices_actuales_son_los_de_la_plantilla(seccion):
    assert seccion.indices_actuales() == (0, 1)


# --- Errores y avisos junto a la sección --------------------------------------------------------


def test_v_c10_a_v_c20_la_seccion_muestra_errores_y_avisos_de_la_red_del_clon(seccion):
    personalizar(seccion)
    seccion.mostrar_problemas(
        [
            Problema("red_clon.tarjetas[0].vlan", "V-C10", Severidad.ERROR, {"vnet": "plana"}),
            Problema("red_clon", "V-C18", Severidad.AVISO, {}),
            Problema("red_clon", "V-C20", Severidad.AVISO, {"tarjeta": "net1"}),
            Problema("red_clon", "V-C17", Severidad.ERROR, {}),
            Problema("nombre", "V-01", Severidad.ERROR, {}),  # no es de la red del clon
        ]
    )
    visible = visibles(seccion)
    assert "«plana»" in visible and "no admite VLAN" in visible
    assert "sin tarjetas de red" in visible and "No entendí la tarjeta net1" in visible
    assert "32 tarjetas" in visible
    assert "nombre solo puede" not in visible
    seccion.mostrar_problemas([])
    assert visibles(seccion).count("«plana»") == 0


def test_v_c16_la_seccion_tambien_muestra_el_error_de_cloudinit_de_una_tarjeta_quitada(seccion):
    personalizar(seccion)
    seccion.mostrar_problemas([Problema("cloudinit", "V-C16", Severidad.ERROR, {"tarjeta": "1"})])
    assert "tarjeta 1" in visibles(seccion) and "la vas a quitar" in visibles(seccion)


def test_v_c21_texto_de_la_config_del_clon_ilegible_explica_que_no_se_cambio_la_red():
    t = texto_problema_c(Problema("red_clon", "V-C21", Severidad.ERROR, {}))
    assert "no cambié su red para no perder su MAC" in t and "Reintentar ajustes" in t


# --- RF-C4.8: el informe lista las tarjetas finales -----------------------------------------------


def test_ca_c4_8_2_el_informe_muestra_las_tarjetas_finales_y_las_acciones():
    finales = (
        TarjetaFinal(0, AccionTarjeta.CAMBIAR, "virtio", "prod", 100, True, False),
        TarjetaFinal(1, AccionTarjeta.QUITAR, "virtio", None, None, False, False),
        TarjetaFinal(2, AccionTarjeta.ANADIR, "e1000", "vmbr1", None, False, False),
    )
    lineas = lineas_red_final(finales)
    assert lineas[0].startswith("net0:") and "prod" in lineas[0] and "100" in lineas[0]
    assert "quitada net1" in lineas
    assert "añadida net2" in lineas
    assert any(linea.startswith("net2:") and "vmbr1" in linea for linea in lineas)
    assert not any(linea.startswith("net1:") for linea in lineas)


def test_ca_c4_8_2_la_mac_no_conservada_se_dice_en_el_informe():
    nueva = TarjetaFinal(0, AccionTarjeta.CAMBIAR, "virtio", "vmbr1", None, False, False)
    igual = TarjetaFinal(0, AccionTarjeta.CAMBIAR, "virtio", "vmbr1", None, True, False)
    assert lineas_red_final([nueva]) != lineas_red_final([igual])
    assert "MAC" in " ".join(lineas_red_final([nueva]))


# --- Formulario: la sección solo existe al clonar y alimenta a cloud-init (B1) -------------------


def _plantilla_con_tarjetas(config: dict[str, str]):
    detalle = dataclasses.replace(
        detalle_plantilla(),
        tarjetas=tarjetas_de_config(config),
        bridges=("vmbr0",),
        cloudinit=info_plantilla(tarjetas=(0, 1)),
    )
    return dataclasses.replace(plantilla_pve(nombre="base"), detalle=detalle)


@pytest.fixture
def formulario(qtbot):
    inv = inv_origen(plantillas=(_plantilla_con_tarjetas(CONFIG),))
    inv.redes_sdn = {"pve": VNETS}
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    caps = capacidades_para(inv.version, None)
    f.establecer_disponibilidad_c({o: EstadoOpcion(o, Disponibilidad.SI) for o in OpcionC}, caps)
    f.establecer_inventario(inv)
    f.selector_origen.establecer_capacidades(caps_origen(inv))
    f.selector_origen.establecer_catalogo(
        [volumen(VOLID_ISO)], list(inv.catalogo.plantillas), nodo="pve"
    )
    f.establecer_modo(True)
    return f


def clonar(f: FormularioVM) -> None:
    f.selector_origen.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    f.selector_origen.establecer_seleccion(FuenteCatalogo.PLANTILLA, f._inv.catalogo.plantillas[0])
    f.establecer_info_cloudinit(info_plantilla(tarjetas=(0, 1)), disponibilidad())


def test_ca_c4_1_4_con_un_origen_que_no_es_clon_la_seccion_no_se_ofrece_y_no_viaja(formulario):
    assert not formulario.seccion_red_clon.isVisibleTo(formulario)
    assert formulario.configuracion().red_clon is None


def test_ca_c4_1_4_al_clonar_la_seccion_aparece_con_las_tarjetas_de_la_plantilla(formulario):
    clonar(formulario)
    s = formulario.seccion_red_clon
    assert s.isVisibleTo(formulario)
    assert s.indices_actuales() == (0, 1)
    assert formulario.configuracion().red_clon is None  # «Como la plantilla» por defecto


def test_ca_c4_1_4_al_volver_a_un_origen_que_no_clona_la_red_del_clon_deja_de_viajar(
    formulario, monkeypatch
):
    # El cambio de origen con una plantilla elegida pide confirmación: se acepta sin diálogo.
    monkeypatch.setattr(
        "proxlaunch.interfaz.vistas.selector_origen.confirmar", lambda *a, **k: True
    )
    clonar(formulario)
    formulario.seccion_red_clon.radio_personalizar.setChecked(True)
    assert formulario.configuracion().red_clon is not None
    formulario.selector_origen.opciones[OrigenSO.DISCO_VACIO].setChecked(True)
    assert formulario.configuracion().red_clon is None
    assert not formulario.seccion_red_clon.isVisibleTo(formulario)


def test_ca_c4_1_2_el_formulario_entrega_la_red_pedida_en_la_configuracion(formulario):
    clonar(formulario)
    s = formulario.seccion_red_clon
    s.radio_personalizar.setChecked(True)
    elegir(s, 0, "prod")
    escribir(fila(s, 0).vlan, "100")
    red = formulario.configuracion().red_clon
    (t,) = red.tarjetas
    assert (t.indice, t.accion, t.bridge, t.vlan) == (0, AccionTarjeta.CAMBIAR, "prod", 100)


def test_ca_c4_7_1_con_la_segunda_tarjeta_quitada_cloudinit_solo_ofrece_la_tarjeta_0(formulario):
    clonar(formulario)
    assert sorted(formulario.seccion_cloudinit._tarjetas) == [0, 1]
    s = formulario.seccion_red_clon
    s.radio_personalizar.setChecked(True)
    fila(s, 1).boton.click()
    assert sorted(formulario.seccion_cloudinit._tarjetas) == [0]
    fila(s, 1).boton.click()  # conservarla de nuevo devuelve la fila
    assert sorted(formulario.seccion_cloudinit._tarjetas) == [0, 1]


def test_ca_c4_7_2_una_tarjeta_anadida_aparece_en_cloudinit_sin_configurar(formulario):
    clonar(formulario)
    s = formulario.seccion_red_clon
    s.radio_personalizar.setChecked(True)
    s._agregar.click()
    assert sorted(formulario.seccion_cloudinit._tarjetas) == [0, 1, 2]
    ci = formulario.configuracion().cloudinit
    configuradas = (
        []
        if ci is None
        else [t.indice for t in ci.tarjetas if t.modo != ModoTarjeta.SIN_CONFIGURAR]
    )
    assert 2 not in configuradas


def test_ca_c4_7_volver_a_como_la_plantilla_restituye_las_tarjetas_de_cloudinit(formulario):
    clonar(formulario)
    s = formulario.seccion_red_clon
    s.radio_personalizar.setChecked(True)
    fila(s, 1).boton.click()
    s.radio_plantilla.setChecked(True)
    assert sorted(formulario.seccion_cloudinit._tarjetas) == [0, 1]
