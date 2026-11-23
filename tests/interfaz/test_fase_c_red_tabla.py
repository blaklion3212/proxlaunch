"""Tabla de redes con VNets de SDN (fase C, 0.8.0): grupos del desplegable, alias, VLAN solo en
VNets «vlanaware», mensajes sin VNets por versión e intersección de nodos.

Derivadas de docs/requisitos/fase-c.md: CA-C2.1.1, CA-C2.1.2, CA-C2.1.3, CA-C2.1.4, CA-C2.1.5,
CA-C2.1.6, CA-C2.2.1, CA-C2.2.2, CA-C2.2.5, CA-C2.3.1, CA-C2.3.3, CA-C2.3.4, CA-C2.4.1 a CA-C2.4.4,
V-C10, V-C11, V-C12 y CL-C11. Todo sin red: solo widgets y datos del núcleo.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from proxlaunch.interfaz.textos_c import (
    texto_nodos_sin_leer,
    texto_redes_ocultas,
    texto_sin_vnets,
    texto_vlan_no_vlanaware,
    texto_vnet_con_alias,
)
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.interfaz.vistas.tabla_redes import TablaRedes, llenar_combo_red
from proxlaunch.nucleo.capacidades import Funcion, capacidades_para
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.inventario import Bridge, RedVirtual, Version
from proxlaunch.nucleo.modelos.vm import InterfazRed
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, OpcionC
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_mvp4 import inv_origen


def bridge(nombre: str, *, vlan_aware: bool = False) -> Bridge:
    return Bridge(nombre, "bridge", vlan_aware)


def vnet(nombre: str, *, vlan_aware: bool = False, alias: str | None = None) -> RedVirtual:
    return RedVirtual(nombre, alias, vlan_aware)


BRIDGES = (bridge("vmbr0", vlan_aware=True), bridge("vmbr1"))
VNETS = (vnet("prod", vlan_aware=True, alias="Producción"), vnet("lab"), vnet("plana"))


@pytest.fixture
def tabla(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.show()
    t.establecer_bridges(BRIDGES, VNETS, sdn_leido=True)
    t.establecer_redes([InterfazRed("vmbr0")])
    return t


def fila(t: TablaRedes, i: int = 0):
    return t._filas[i]


def elegir(t: TablaRedes, nombre: str, i: int = 0) -> None:
    f = fila(t, i)
    f.bridge.setCurrentIndex(f.bridge.findData(nombre))


def items(combo) -> list[tuple[str, object, bool]]:
    return [
        (combo.itemText(i), combo.itemData(i), combo.model().item(i).isEnabled())
        for i in range(combo.count())
    ]


def textos(raiz) -> str:
    return "\n".join(
        lbl.text() for lbl in raiz.findChildren(QLabel) if lbl.isVisibleTo(raiz) and lbl.text()
    )


# --- RF-C2.1: dos grupos en el desplegable ------------------------------------------------------


def test_ca_c2_1_1_el_desplegable_lista_los_bridges_en_un_grupo_y_las_vnets_en_otro_con_alias(
    tabla,
):
    lista = items(fila(tabla).bridge)
    textos_item = [t for t, _d, _e in lista]
    assert textos_item == [
        "Bridges del servidor",
        "vmbr0",
        "vmbr1",
        "Redes virtuales (SDN)",
        "prod — Producción",
        "lab",
        "plana",
    ]
    # Los títulos de grupo no se pueden elegir y no llevan dato.
    cabeceras = [(t, d, e) for t, d, e in lista if d is None]
    assert [t for t, _d, _e in cabeceras] == ["Bridges del servidor", "Redes virtuales (SDN)"]
    assert all(not e for _t, _d, e in cabeceras)
    assert all(e for _t, d, e in lista if d is not None)


def test_ca_c2_1_1_el_alias_es_visible_pero_el_dato_del_item_es_solo_el_nombre(tabla):
    combo = fila(tabla).bridge
    pos = combo.findText("prod — Producción")
    assert combo.itemData(pos) == "prod"


def test_ca_c2_1_2_elegir_la_vnet_prod_deja_bridge_prod_en_la_interfaz(tabla):
    elegir(tabla, "prod")
    assert [r.bridge for r in tabla.redes()] == ["prod"]


def test_ca_c2_1_4_un_bridge_y_una_vnet_con_el_mismo_nombre_se_distinguen_por_su_grupo(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.establecer_bridges((bridge("x"),), (vnet("x", alias="red x"),), sdn_leido=True)
    t.establecer_redes([InterfazRed("x")])
    lista = items(fila(t).bridge)
    assert [(txt, d) for txt, d, _e in lista if d is not None] == [("x", "x"), ("x — red x", "x")]
    assert t.redes()[0].bridge == "x"
    # El núcleo valida el nombre como bridge: no es una VNet a efectos de VLAN.
    assert t.vnet_de("x") is None


def test_ca_c2_1_sin_vnets_la_lista_es_plana_como_en_0_7_0(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.establecer_bridges(BRIDGES)
    t.establecer_redes([InterfazRed("vmbr0")])
    assert [(txt, d) for txt, d, _e in items(fila(t).bridge)] == [
        ("vmbr0", "vmbr0"),
        ("vmbr1", "vmbr1"),
    ]
    assert not t._sin_vnets.isVisibleTo(t)


def test_ca_c2_1_3_si_la_lectura_de_vnets_fallo_la_tabla_funciona_con_los_bridges(qtbot):
    """El formulario llama sin VNets y con ``sdn_leido=False``: ni lista rara ni error."""
    t = TablaRedes()
    qtbot.addWidget(t)
    t.show()
    perdidas = t.establecer_bridges(BRIDGES, (), sdn_leido=False)
    t.establecer_redes([InterfazRed("vmbr1")])
    assert perdidas == []
    assert t.hay_bridges()
    assert t.redes()[0].bridge == "vmbr1"
    assert "no tiene redes" not in textos(t)
    t.agregar_red()
    assert len(t.redes()) == 2


def test_ca_c2_1_6_una_vnet_pendiente_de_aplicar_no_se_ofrece_y_el_texto_pide_aplicar_sdn(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.show()
    t.establecer_bridges(BRIDGES, (), sdn_leido=True, sdn_incluido=True)
    assert "aplique la configuración de SDN" in texto_sin_vnets(True)
    assert "aplique la configuración de SDN" in textos(t)


def test_ca_c2_1_5_el_alias_con_marcado_se_muestra_literal_y_sin_interpretar(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.establecer_bridges(BRIDGES, (vnet("prod", alias="<b>x</b> & <script>"),), sdn_leido=True)
    t.establecer_redes([InterfazRed("vmbr0")])
    combo = fila(t).bridge
    assert combo.itemText(combo.findData("prod")) == "prod — <b>x</b> & <script>"
    assert combo.itemData(combo.findData("prod")) == "prod"  # lo que viaja es solo el nombre


def test_ca_c2_1_texto_vnet_con_alias_sin_alias_es_solo_el_nombre():
    assert texto_vnet_con_alias("prod", None) == "prod"
    assert texto_vnet_con_alias("prod", "") == "prod"


def test_ca_c2_1_llenar_combo_marca_como_ausente_la_red_que_el_nodo_no_tiene(qtbot):
    from PySide6.QtWidgets import QComboBox

    combo = QComboBox()
    qtbot.addWidget(combo)
    llenar_combo_red(combo, BRIDGES, VNETS, ausente="fantasma")
    ultimo = items(combo)[-1]
    assert ultimo == ("fantasma (no existe)", "fantasma", False)
    llenar_combo_red(QComboBox(), BRIDGES, VNETS, ausente="prod")  # existente: no se duplica


def test_v_c12_una_red_cargada_de_un_lote_que_el_nodo_no_tiene_se_muestra_como_no_existe(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.establecer_bridges(BRIDGES, VNETS, sdn_leido=True)
    t.establecer_redes([InterfazRed("recien-creada")], conservar_ausentes=True)
    assert t.valores_ausentes() == ["recien-creada"]
    assert "recien-creada (no existe)" in [t_ for t_, _d, _e in items(fila(t).bridge)]


def test_ca_c2_1_una_vnet_cargada_que_el_nodo_si_tiene_no_es_ausente(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.establecer_bridges(BRIDGES, VNETS, sdn_leido=True)
    t.establecer_redes([InterfazRed("lab")], conservar_ausentes=True)
    assert t.valores_ausentes() == []
    assert t.redes()[0].bridge == "lab"


def test_ca_c2_1_al_cambiar_de_nodo_la_vnet_elegida_que_ya_no_existe_se_informa_como_perdida(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.establecer_bridges(BRIDGES, VNETS, sdn_leido=True)
    t.establecer_redes([InterfazRed("prod"), InterfazRed("vmbr0")])
    perdidas = t.establecer_bridges(BRIDGES, (vnet("lab"),), sdn_leido=True)
    assert perdidas == ["prod"]
    assert [r.bridge for r in t.redes()] == ["", "vmbr0"]


# --- RF-C2.2: VLAN solo con VNets «vlanaware» ----------------------------------------------------


def test_ca_c2_2_1_con_una_vnet_no_vlanaware_la_vlan_queda_deshabilitada_con_el_motivo(tabla):
    elegir(tabla, "plana")
    f = fila(tabla)
    assert not f.vlan.isEnabled()
    assert f.vlan.toolTip() == texto_vlan_no_vlanaware()
    assert f.vlan.accessibleDescription() == texto_vlan_no_vlanaware()
    assert "no es «vlanaware»" in textos(tabla)  # el motivo se ve sin pasar el ratón
    assert tabla.redes()[0].vlan is None  # no se envía ``tag``


def test_ca_c2_2_1_al_elegir_una_vnet_no_vlanaware_se_borra_la_vlan_ya_escrita(tabla):
    f = fila(tabla)
    f.vlan.setText("100")
    assert tabla.redes()[0].vlan == 100
    elegir(tabla, "lab")
    assert f.vlan.text() == ""
    assert tabla.redes()[0].vlan is None


def test_ca_c2_2_2_con_una_vnet_vlanaware_la_vlan_se_habilita_y_viaja(tabla):
    elegir(tabla, "prod")
    f = fila(tabla)
    assert f.vlan.isEnabled()
    f.vlan.setText("100")
    f.vlan.textEdited.emit("100")
    assert tabla.redes()[0].bridge == "prod" and tabla.redes()[0].vlan == 100
    assert "no es «vlanaware»" not in textos(tabla)


def test_ca_c2_2_5_con_un_bridge_la_vlan_funciona_como_en_0_7_0_aunque_no_sea_vlanaware(tabla):
    elegir(tabla, "vmbr1")  # bridge sin vlan_aware
    f = fila(tabla)
    assert f.vlan.isEnabled()
    assert f.vlan.toolTip() == ""
    f.vlan.setText("20")
    assert tabla.redes()[0].vlan == 20


def test_ca_c2_2_volver_de_una_vnet_no_vlanaware_a_un_bridge_rehabilita_la_vlan(tabla):
    elegir(tabla, "plana")
    assert not fila(tabla).vlan.isEnabled()
    elegir(tabla, "vmbr0")
    assert fila(tabla).vlan.isEnabled()
    assert "no es «vlanaware»" not in textos(tabla)


def test_ca_c2_2_cada_fila_tiene_su_propio_estado_de_vlan(tabla):
    tabla.agregar_red(InterfazRed("plana"))
    assert fila(tabla, 0).vlan.isEnabled()  # vmbr0
    assert not fila(tabla, 1).vlan.isEnabled()  # plana
    motivo = textos(tabla)
    assert "net1:" in motivo and "net0:" not in motivo


def test_ca_c2_2_la_vlan_no_numerica_se_convierte_en_0_y_la_regla_la_rechaza(tabla):
    f = fila(tabla)
    f.vlan.setText("abc")
    assert tabla.redes()[0].vlan == 0
    assert tabla.vlan_no_numericas() == ["net0"]


# --- Errores V-C10 / V-C11 junto a la fila -------------------------------------------------------


def test_ca_c2_2_3_el_error_v_c10_se_muestra_junto_a_la_fila_con_la_vnet(tabla):
    tabla.aplicar_problemas(
        [Problema("redes[0].vlan", "V-C10", Severidad.ERROR, {"vnet": "plana", "tarjeta": "net0"})]
    )
    visible = textos(tabla)
    assert "net0:" in visible and "«plana»" in visible and "vlanaware" in visible
    assert fila(tabla).vlan.property("invalido") is True


def test_ca_c2_3_2_el_error_v_c11_nombra_la_vnet_y_el_nodo(tabla):
    tabla.aplicar_problemas(
        [
            Problema(
                "redes[0].bridge",
                "V-C11",
                Severidad.ERROR,
                {"vnet": "plana", "nodo": "pve2", "tarjeta": "net0"},
            )
        ]
    )
    visible = textos(tabla)
    assert "«plana»" in visible and "pve2" in visible


def test_ca_c2_2_un_aviso_no_se_muestra_como_error_de_la_tabla(tabla):
    tabla.aplicar_problemas(
        [Problema("redes[0].mtu", "V-C14", Severidad.AVISO, {"mtu": "9000", "mtu_red": "1500"})]
    )
    assert "9000" not in textos(tabla)


# --- RF-C2.3: intersección en lotes con varios nodos ---------------------------------------------


def test_ca_c2_3_1_el_aviso_de_redes_ocultas_cuenta_cuantas_son(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.show()
    t.establecer_bridges(BRIDGES, (vnet("b"),), sdn_leido=True, ocultas=2)
    assert texto_redes_ocultas(2) in textos(t)
    assert "2 redes no se muestran porque no existen en todos los nodos elegidos" in textos(t)


def test_ca_c2_3_1_con_una_sola_red_oculta_el_texto_va_en_singular():
    assert (
        texto_redes_ocultas(1)
        == "1 red no se muestra porque no existe en todos los nodos elegidos."
    )


def test_ca_c2_3_3_con_un_solo_nodo_no_hay_aviso_de_ocultas(tabla):
    assert "no se muestran" not in textos(tabla)
    assert "no pude leer" not in textos(tabla).lower()


def test_ca_c2_3_4_un_nodo_sin_lectura_se_avisa_con_su_nombre(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.show()
    t.establecer_bridges(BRIDGES, (vnet("b"),), sdn_leido=False, sin_leer=["pve3", "pve4"])
    visible = textos(t)
    assert texto_nodos_sin_leer(["pve3", "pve4"]) in visible
    assert "pve3, pve4" in visible


def test_ca_c2_3_el_aviso_desaparece_al_volver_a_un_solo_nodo(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.show()
    t.establecer_bridges(BRIDGES, (vnet("b"),), sdn_leido=True, ocultas=3, sin_leer=["pve2"])
    t.establecer_bridges(BRIDGES, (vnet("b"),), sdn_leido=True)
    assert "no se muestran" not in textos(t) and "pve2" not in textos(t)


# --- RF-C2.4: mensajes sin VNets según la versión -----------------------------------------------


def _tabla_sin_vnets(qtbot, *, incluido: bool) -> TablaRedes:
    t = TablaRedes()
    qtbot.addWidget(t)
    t.show()
    t.establecer_bridges(BRIDGES, (), sdn_leido=True, sdn_incluido=incluido)
    return t


def test_ca_c2_4_1_en_8_0_sin_vnets_el_texto_menciona_libpve_network_perl(qtbot):
    t = _tabla_sin_vnets(qtbot, incluido=False)
    visible = textos(t)
    assert "libpve-network-perl" in visible and "8.0" in visible
    assert "SDN.Use" not in visible


def test_ca_c2_4_2_en_8_1_o_posterior_el_texto_nombra_sdn_use_y_la_ruta_de_la_zona(qtbot):
    t = _tabla_sin_vnets(qtbot, incluido=True)
    visible = textos(t)
    assert "SDN.Use" in visible and "/sdn/zones/<zona>" in visible
    assert "libpve-network-perl" not in visible


def test_ca_c2_4_los_dos_textos_cubren_sin_permiso_y_sin_vnets_el_de_8_1_o_posterior():
    texto = texto_sin_vnets(True)
    assert "no haya ninguna" in texto and "no tenga permiso" in texto


def test_ca_c2_4_3_sin_vnets_los_bridges_siguen_siendo_utilizables(qtbot):
    t = _tabla_sin_vnets(qtbot, incluido=True)
    t.establecer_redes([InterfazRed("vmbr1")])
    assert t.hay_bridges() and t.redes()[0].bridge == "vmbr1"
    t.agregar_red()
    assert len(t.redes()) == 2 and t.redes()[1].bridge == "vmbr0"


def test_ca_c2_4_4_el_mensaje_es_texto_visible_y_no_solo_una_sugerencia(qtbot):
    t = _tabla_sin_vnets(qtbot, incluido=True)
    lbl = t._sin_vnets
    assert lbl.isVisibleTo(t) and lbl.text() == texto_sin_vnets(True)
    assert lbl.toolTip() == ""  # no depende de pasar el ratón


def test_ca_c2_4_el_mensaje_desaparece_cuando_hay_vnets_o_no_se_leyeron(qtbot):
    t = _tabla_sin_vnets(qtbot, incluido=True)
    t.establecer_bridges(BRIDGES, VNETS, sdn_leido=True)
    assert not t._sin_vnets.isVisibleTo(t)
    t.establecer_bridges(BRIDGES, (), sdn_leido=False)
    assert not t._sin_vnets.isVisibleTo(t)


def test_ca_c2_4_la_cabecera_pasa_a_red_cuando_hay_vnets(qtbot):
    t = TablaRedes()
    qtbot.addWidget(t)
    t.establecer_bridges(BRIDGES, ())
    assert t._cabeceras[1].text() == "Red (bridge)"
    t.establecer_bridges(BRIDGES, VNETS, sdn_leido=True)
    assert t._cabeceras[1].text() == "Red"


@pytest.mark.parametrize(
    ("version", "incluido"),
    [((8, 0), False), ((8, 1), True), ((8, 4), True), ((9, 0), True), ((9, 2), True)],
)
def test_ca_c2_4_la_version_decide_el_texto_8_0_frente_a_8_1_o_posterior(version, incluido):
    caps = capacidades_para(Version(f"{version[0]}.{version[1]}", *version, 0), None)
    assert caps.tiene(Funcion.SDN_INCLUIDO) is incluido
    assert caps.tiene(Funcion.VNETS_SDN)  # desde 8.0 hay VNets (si el servidor tiene SDN)


def _estados_c(caps) -> dict[OpcionC, EstadoOpcion]:
    return {o: EstadoOpcion(o, Disponibilidad.SI) for o in OpcionC}


@pytest.mark.parametrize(
    ("version", "esperado"),
    [((8, 0), "libpve-network-perl"), ((9, 2), "/sdn/zones/<zona>")],
)
def test_ca_c2_4_el_formulario_elige_el_texto_por_la_version_de_las_capacidades(
    qtbot, version, esperado
):
    """Integración: ``FormularioVM`` pasa ``sdn_incluido`` según ``Funcion.SDN_INCLUIDO``."""
    inv = inv_origen(version=version)
    inv.redes_sdn = {"pve": ()}
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    caps = capacidades_para(inv.version, None)
    f.establecer_disponibilidad_c(_estados_c(caps), caps)
    f.establecer_inventario(inv)
    visible = textos(f.tabla_redes)
    assert esperado in visible


def test_ca_c2_4_el_formulario_no_muestra_el_mensaje_de_vnets_si_hay_vnets(qtbot):
    inv = inv_origen()
    inv.redes_sdn = {"pve": (vnet("prod"),)}
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    caps = capacidades_para(inv.version, None)
    f.establecer_disponibilidad_c(_estados_c(caps), caps)
    f.establecer_inventario(inv)
    assert "No ves ninguna red virtual" not in textos(f.tabla_redes)
    assert "prod" in [d for _t, d, _e in items(f.tabla_redes._filas[0].bridge)]


def test_ca_c2_1_3_el_formulario_con_el_fallo_de_lectura_de_sdn_no_muestra_error_ni_rompe(qtbot):
    from proxlaunch.nucleo.errores import ErrorProxLaunch

    inv = inv_origen()
    inv.redes_sdn = {}
    inv.errores_sdn = {"pve": ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {})}
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    assert f.tabla_redes.hay_bridges()
    visible = textos(f.tabla_redes)
    assert "No ves ninguna red virtual" not in visible and "libpve" not in visible
    assert f.tabla_redes.redes()[0].bridge == "vmbr0"
