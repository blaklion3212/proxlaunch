"""Sección «Hardware del clúster» del formulario (RF-D3.1, RF-D3.2, RF-D0.3 y RNF-D4).

Derivadas de docs/requisitos/fase-d.md: CA-D3.1.1 a CA-D3.1.3 y CA-D3.1.7 (qué se lista, mensajes
V-D50 y que solo se lee al abrir la sección), CA-D3.2.1 a CA-D3.2.3, CA-D3.2.5 y CA-D3.2.6 (las
opciones por dispositivo, los máximos y ``driver=keep``), CA-D0.3.1 y CA-D0.3.2 (permiso ausente
= opción deshabilitada con su explicación) y CA-D2.7.4 (sin ``pcie`` en ARM64). Las lecturas las
hace el controlador; aquí se entrega ``InfoHardwareCluster`` ya hecha. Sin red.
"""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.interfaz.vistas.seccion_hardware_cluster import SeccionHardwareCluster
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import (
    MAX_PCI,
    MAX_USB,
    AsignacionPCI,
    AsignacionUSB,
    EntradaMapeo,
    HardwareCluster,
    InfoHardwareCluster,
    Mapeo,
    TipoMapeo,
)
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.disponibilidad_d import disponibilidad_fase_d
from proxlaunch.nucleo.opciones.modelos import OpcionD
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_fase_b import textos_visibles
from .apoyo_mvp4 import inv_origen

GPU = Mapeo(
    TipoMapeo.PCI,
    "gpu-a2",
    "Tarjeta de la sala 2",
    (EntradaMapeo("pve1"), EntradaMapeo("pve2")),
    migrable_en_vivo=False,
)
HASP = Mapeo(TipoMapeo.USB, "llave-hasp", "Llave de licencias", (EntradaMapeo("pve1"),))
INFO = InfoHardwareCluster(mapeos=(GPU, HASP))


@pytest.fixture
def seccion(qtbot):
    s = SeccionHardwareCluster()
    qtbot.addWidget(s)
    s.show()
    return s


def _combo_textos(fila) -> list[str]:
    return [fila.combo.itemText(i) for i in range(fila.combo.count())]


def _activar(seccion, info=INFO, permisos=None):
    """Abre la sección y entrega la lectura (como la ventana: primero pide, luego responde)."""
    seccion.chk_activar.setChecked(True)
    seccion.establecer_info(info, permisos)
    return seccion


def _permisos(*rutas: tuple[str, str]) -> PermisosEfectivos:
    d: dict[str, dict[str, int]] = {}
    for ruta, priv in rutas:
        d.setdefault(ruta, {})[priv] = 1
    return PermisosEfectivos(rutas=d)


# --- RNF-D4 y CA-D3.1.7: solo se lee al abrir la sección ------------------------------------------


def test_ca_d3_1_7_sin_abrir_la_seccion_no_se_pide_ninguna_lectura(qtbot, seccion):
    veces: list[int] = []
    seccion.pide_mapeos.connect(lambda: veces.append(1))
    seccion.establecer_info(None, None)
    seccion.establecer_arquitectura(Arquitectura.AARCH64)
    seccion.establecer_driver_keep(True)
    assert veces == [] and not seccion.chk_activar.isChecked()


def test_ca_d3_1_7_al_activarla_se_pide_una_sola_vez_aunque_se_apague_y_se_encienda(qtbot, seccion):
    veces: list[int] = []
    seccion.pide_mapeos.connect(lambda: veces.append(1))
    seccion.chk_activar.setChecked(True)
    seccion.chk_activar.setChecked(False)
    seccion.chk_activar.setChecked(True)
    assert veces == [1]


def test_ca_d3_1_7_releer_pide_otra_lectura_y_vuelve_a_decir_que_lee(qtbot, seccion):
    veces: list[int] = []
    seccion.pide_mapeos.connect(lambda: veces.append(1))
    _activar(seccion)
    seccion.boton_releer.click()
    assert len(veces) == 2
    assert "Leyendo" in textos_visibles(seccion)  # tras «Releer» sí lo dice


def test_el_boton_releer_solo_se_habilita_tras_la_primera_lectura_pedida(qtbot, seccion):
    assert not seccion.boton_releer.isEnabled()
    _activar(seccion)
    assert seccion.boton_releer.isEnabled()


def test_al_activarla_se_crea_una_primera_fila_pci_vacia_que_no_genera_clave(qtbot, seccion):
    seccion.chk_activar.setChecked(True)
    assert len(seccion._filas) == 1 and seccion._filas[0].tipo == TipoMapeo.PCI
    assert seccion.valor() is None  # «Un mapeo sin selección no genera ninguna clave»


# --- CA-D3.1.1: qué se lista ----------------------------------------------------------------------


def test_ca_d3_1_1_la_lista_trae_ambos_mapeos_con_su_descripcion_y_sus_nodos(qtbot, seccion):
    _activar(seccion)
    seccion.boton_anadir_usb.click()
    pci = _combo_textos(seccion._filas[0])
    usb = _combo_textos(seccion._filas[1])
    assert any("gpu-a2" in t and "Tarjeta de la sala 2" in t and "pve1, pve2" in t for t in pci)
    assert not any("llave-hasp" in t for t in pci)  # los USB no salen en la lista de PCI
    assert any("llave-hasp" in t and "Llave de licencias" in t and "pve1" in t for t in usb)
    assert pci[0] == "Elige un mapeo"


def test_ca_d3_1_5_la_descripcion_con_marcado_se_muestra_como_texto_plano(qtbot, seccion):
    sucio = Mapeo(TipoMapeo.PCI, "x", "<b>negrita</b>&amp;", (EntradaMapeo("pve1"),))
    _activar(seccion, InfoHardwareCluster(mapeos=(sucio,)))
    texto = _combo_textos(seccion._filas[0])[1]
    assert "<b>negrita</b>" in texto  # el combo no interpreta HTML: se ve literal, sin formato


def test_ca_d3_1_1_un_mapeo_migrable_lo_dice(qtbot, seccion):
    m = Mapeo(TipoMapeo.PCI, "vf", "", (EntradaMapeo("pve1"),), migrable_en_vivo=True)
    _activar(seccion, InfoHardwareCluster(mapeos=(m,)))
    assert "migración en vivo" in _combo_textos(seccion._filas[0])[1]


# --- CA-D3.1.2 y CA-D3.1.3: sin mapeos o sin poder leerlos ----------------------------------------


def test_ca_d3_1_2_sin_mapeos_visibles_sale_v_d50_con_el_texto_para_el_administrador(
    qtbot, seccion
):
    _activar(seccion, InfoHardwareCluster(mapeos=()))
    texto = textos_visibles(seccion)
    assert "Pide al administrador" in texto and "Mapping.Use" in texto
    assert seccion.chk_activar.isEnabled()  # sigue usable
    assert not seccion._cuerpo.isHidden()


def test_ca_d3_1_2_sin_mapeos_de_un_solo_tipo_lo_dice_solo_de_ese_tipo(qtbot, seccion):
    _activar(seccion, InfoHardwareCluster(mapeos=(GPU,)))
    texto = seccion._estado.text()
    assert "USB" in texto and "PCI" not in texto


def test_ca_d3_1_3_si_no_se_pudo_leer_el_texto_es_distinto_y_no_hay_excepcion(qtbot, seccion):
    err = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {})
    _activar(seccion, InfoHardwareCluster(mapeos=None, error_mapeos=err))
    texto = seccion._estado.text()
    assert "No pude leer" in texto
    assert "Pide al administrador" not in texto


def test_ca_d3_1_3_mostrar_error_de_lectura_deja_la_seccion_usable(qtbot, seccion):
    seccion.chk_activar.setChecked(True)
    seccion.mostrar_error_lectura(ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}))
    assert "No pude leer" in seccion._estado.text()
    assert seccion.boton_anadir_pci.isEnabled() and seccion.chk_activar.isEnabled()
    seccion.mostrar_error_lectura(None)  # None no hace nada


def test_antes_de_abrir_la_seccion_dice_que_la_abras_para_leer(qtbot, seccion):
    seccion.chk_activar.setChecked(True)
    seccion.chk_activar.setChecked(False)
    assert "Abre esta sección" in seccion._estado.text() or seccion._cuerpo.isHidden()


def test_mientras_se_leen_los_mapeos_la_seccion_dice_que_esta_leyendo(qtbot, seccion):
    seccion.chk_activar.setChecked(True)  # pide la lectura; aún no hay respuesta
    assert "Leyendo" in seccion._estado.text()


def test_al_cargar_un_lote_con_mapeos_la_seccion_dice_que_esta_leyendo(qtbot, seccion):
    seccion.establecer_valor(HardwareCluster(pci=(AsignacionPCI("gpu-a2"),)))
    assert "Leyendo" in seccion._estado.text()


# --- CA-D0.3.1 y CA-D0.3.2: privilegio ausente ----------------------------------------------------


def test_ca_d0_3_1_un_mapeo_sin_mapping_use_sale_deshabilitado_con_el_privilegio_y_la_ruta(
    qtbot, seccion
):
    permisos = _permisos(("/mapping/pci/otro", "Mapping.Use"), ("/", "VM.Audit"))
    _activar(seccion, permisos=permisos)
    fila = seccion._filas[0]
    indice = fila.combo.findData("gpu-a2")
    assert indice > 0
    assert not fila.combo.model().item(indice).isEnabled()
    assert "Falta el permiso Mapping.Use en /mapping/pci/gpu-a2" in fila.combo.itemText(indice)
    assert "Falta el permiso Mapping.Use en /mapping/pci/gpu-a2" in fila.combo.itemData(
        indice, 3
    )  # tooltip


def test_ca_d0_3_1_el_mapeo_con_permiso_en_su_ruta_queda_habilitado(qtbot, seccion):
    permisos = _permisos(("/mapping/pci/gpu-a2", "Mapping.Use"))
    _activar(seccion, permisos=permisos)
    fila = seccion._filas[0]
    assert fila.combo.model().item(fila.combo.findData("gpu-a2")).isEnabled()


def test_ca_d0_3_1_el_permiso_en_toda_la_rama_de_mapeos_vale_para_cada_mapeo(qtbot, seccion):
    _activar(seccion, permisos=_permisos(("/mapping", "Mapping.Use")))
    fila = seccion._filas[0]
    assert fila.combo.model().item(fila.combo.findData("gpu-a2")).isEnabled()


def test_ca_d0_3_2_con_permisos_desconocidos_los_mapeos_quedan_habilitados(qtbot, seccion):
    _activar(seccion, permisos=None)
    fila = seccion._filas[0]
    assert fila.combo.model().item(fila.combo.findData("gpu-a2")).isEnabled()


def test_ca_d0_3_1_sin_mapping_use_en_ninguna_ruta_la_seccion_se_deshabilita_con_v_d63(
    qtbot, seccion
):
    estados = disponibilidad_fase_d(None, _permisos(("/", "VM.Audit")), None)
    seccion.establecer_disponibilidad(estados[OpcionD.MAPEOS])
    assert not seccion.chk_activar.isEnabled()
    assert "Mapping.Use" in seccion._motivo.text() and not seccion._motivo.isHidden()


def test_ca_d0_3_1_la_seccion_deshabilitada_no_aporta_hardware_aunque_hubiera_filas(qtbot, seccion):
    seccion.establecer_info(INFO, None)
    seccion.chk_activar.setChecked(True)
    seccion._filas[0].combo.setCurrentIndex(seccion._filas[0].combo.findData("gpu-a2"))
    assert seccion.valor() is not None
    estados = disponibilidad_fase_d(None, _permisos(("/", "VM.Audit")), None)
    seccion.establecer_disponibilidad(estados[OpcionD.MAPEOS])
    assert seccion.valor() is None and not seccion.chk_activar.isChecked()
    assert "Mapping.Use" in seccion._motivo.text()  # se avisa de que se restableció


def test_ca_d0_3_2_permisos_desconocidos_dejan_la_seccion_utilizable(qtbot, seccion):
    estados = disponibilidad_fase_d(None, None, None)
    seccion.establecer_disponibilidad(estados[OpcionD.MAPEOS])
    assert seccion.chk_activar.isEnabled()


# --- CA-D3.2.x: opciones por dispositivo ----------------------------------------------------------


def _elegir(fila, mapeo: str) -> None:
    fila.combo.setCurrentIndex(fila.combo.findData(mapeo))


def test_ca_d3_2_1_pci_con_pcie_y_pantalla_principal(qtbot, seccion):
    _activar(seccion)
    fila = seccion._filas[0]
    _elegir(fila, "gpu-a2")
    fila.chk_pcie.setChecked(True)
    fila.chk_x_vga.setChecked(True)
    assert seccion.valor().pci == (AsignacionPCI("gpu-a2", pcie=True, x_vga=True, rombar=True),)


def test_ca_d3_2_1_desmarcar_mostrar_la_rom_la_quita(qtbot, seccion):
    _activar(seccion)
    fila = seccion._filas[0]
    _elegir(fila, "gpu-a2")
    fila.chk_rombar.setChecked(False)
    assert seccion.valor().pci[0].rombar is False


def test_ca_d3_2_2_usb_con_usb3(qtbot, seccion):
    _activar(seccion)
    seccion.boton_anadir_usb.click()
    fila = seccion._filas[1]
    _elegir(fila, "llave-hasp")
    fila.chk_usb3.setChecked(True)
    assert seccion.valor().usb == (AsignacionUSB("llave-hasp", usb3=True),)


def test_ca_d3_2_3_tres_pci_y_dos_usb_conservan_el_orden(qtbot, seccion):
    mapeos = tuple(
        Mapeo(TipoMapeo.PCI, f"p{i}", "", (EntradaMapeo("pve1"),)) for i in range(3)
    ) + tuple(Mapeo(TipoMapeo.USB, f"u{i}", "", (EntradaMapeo("pve1"),)) for i in range(2))
    _activar(seccion, InfoHardwareCluster(mapeos=mapeos))
    for _ in range(2):
        seccion.boton_anadir_pci.click()
    for _ in range(2):
        seccion.boton_anadir_usb.click()
    pci = [f for f in seccion._filas if f.tipo == TipoMapeo.PCI]
    usb = [f for f in seccion._filas if f.tipo == TipoMapeo.USB]
    for i, f in enumerate(pci):
        _elegir(f, f"p{i}")
    for i, f in enumerate(usb):
        _elegir(f, f"u{i}")
    hw = seccion.valor()
    assert [a.mapeo for a in hw.pci] == ["p0", "p1", "p2"]
    assert [a.mapeo for a in hw.usb] == ["u0", "u1"]


def test_ca_d3_2_x_una_fila_sin_mapeo_elegido_no_genera_asignacion(qtbot, seccion):
    _activar(seccion)
    seccion.boton_anadir_pci.click()
    _elegir(seccion._filas[1], "gpu-a2")
    assert [a.mapeo for a in seccion.valor().pci] == ["gpu-a2"]


def test_ca_d3_2_5_los_botones_de_anadir_se_deshabilitan_en_el_maximo_con_el_motivo(qtbot, seccion):
    _activar(seccion)
    for _ in range(MAX_PCI - 1):
        seccion.boton_anadir_pci.click()
    assert sum(1 for f in seccion._filas if f.tipo == TipoMapeo.PCI) == MAX_PCI == 16
    assert not seccion.boton_anadir_pci.isEnabled()
    assert "16" in seccion.boton_anadir_pci.toolTip()
    for _ in range(MAX_USB):
        seccion.boton_anadir_usb.click()
    assert not seccion.boton_anadir_usb.isEnabled() and MAX_USB == 5
    assert "5" in seccion.boton_anadir_usb.toolTip()
    seccion._filas[0].boton_quitar.click()
    assert seccion.boton_anadir_pci.isEnabled()


def test_quitar_una_fila_la_elimina_y_avisa_del_cambio(qtbot, seccion):
    _activar(seccion)
    veces: list[int] = []
    seccion.cambiado.connect(lambda: veces.append(1))
    seccion.boton_anadir_usb.click()
    n = len(seccion._filas)
    seccion._filas[-1].boton_quitar.click()
    assert len(seccion._filas) == n - 1 and veces


def test_ca_d3_2_6_driver_keep_solo_se_ofrece_con_9_1_o_posterior(qtbot, seccion):
    _activar(seccion)
    fila = seccion._filas[0]
    assert fila.chk_driver.isHidden()
    seccion.establecer_driver_keep(True)
    assert not fila.chk_driver.isHidden()
    _elegir(fila, "gpu-a2")
    fila.chk_driver.setChecked(True)
    assert seccion.valor().pci[0].driver_keep is True
    seccion.establecer_driver_keep(False)  # p. ej. se fuerza 9.0
    assert fila.chk_driver.isHidden() and not fila.chk_driver.isChecked()
    assert seccion.valor().pci[0].driver_keep is False


def test_ca_d3_2_6_driver_keep_oculto_no_sale_aunque_la_casilla_estuviera_marcada(qtbot, seccion):
    _activar(seccion)
    fila = seccion._filas[0]
    _elegir(fila, "gpu-a2")
    fila.chk_driver.setChecked(True)  # la casilla existe pero oculta
    assert seccion.valor().pci[0].driver_keep is False


# --- CA-D2.7.4: ARM64 -----------------------------------------------------------------------------


def test_ca_d2_7_4_en_arm_pcie_y_pantalla_principal_se_deshabilitan_con_el_motivo(qtbot, seccion):
    _activar(seccion)
    fila = seccion._filas[0]
    _elegir(fila, "gpu-a2")
    fila.chk_pcie.setChecked(True)
    seccion.establecer_arquitectura(Arquitectura.AARCH64)
    assert not fila.chk_pcie.isEnabled() and not fila.chk_x_vga.isEnabled()
    assert "ARM64" in fila.chk_pcie.toolTip() and "q35" in fila.chk_pcie.toolTip()
    assert not fila.chk_pcie.isChecked()
    assert "ARM64" in seccion._nota_arm.text()
    assert seccion.valor().pci[0].pcie is False


def test_ca_d2_7_4_al_volver_a_x86_se_pueden_marcar_de_nuevo(qtbot, seccion):
    _activar(seccion)
    seccion.establecer_arquitectura(Arquitectura.AARCH64)
    seccion.establecer_arquitectura(Arquitectura.X86_64)
    assert seccion._filas[0].chk_pcie.isEnabled() and seccion._nota_arm.isHidden()


def test_ca_d2_7_4_el_usb_no_se_ve_afectado_por_arm(qtbot, seccion):
    _activar(seccion)
    seccion.boton_anadir_usb.click()
    seccion.establecer_arquitectura(Arquitectura.AARCH64)
    assert seccion._filas[1].chk_usb3.isEnabled()


# --- Carga de un lote guardado y reinicio ---------------------------------------------------------


def test_un_mapeo_de_un_lote_guardado_que_ya_no_existe_se_muestra_como_no_existe_y_no_se_pierde(
    qtbot, seccion
):
    hw = HardwareCluster(pci=(AsignacionPCI("borrado", pcie=True),))
    seccion.establecer_info(INFO, None)
    seccion.establecer_valor(hw)
    fila = seccion._filas[0]
    assert fila.mapeo() == "borrado"
    assert any("borrado (no existe)" in t for t in _combo_textos(fila))
    assert seccion.valor().pci[0] == AsignacionPCI("borrado", pcie=True)


def test_establecer_valor_carga_las_opciones_de_cada_dispositivo(qtbot, seccion):
    hw = HardwareCluster(
        pci=(AsignacionPCI("gpu-a2", pcie=True, x_vga=True, rombar=False),),
        usb=(AsignacionUSB("llave-hasp", usb3=True),),
    )
    seccion.establecer_info(INFO, None)
    seccion.establecer_valor(hw)
    assert seccion.chk_activar.isChecked()
    assert seccion.valor() == hw


def test_establecer_valor_none_apaga_y_vacia_la_seccion(qtbot, seccion):
    _activar(seccion)
    seccion.establecer_valor(None)
    assert not seccion.chk_activar.isChecked() and seccion._filas == []
    assert seccion.valor() is None


def test_reiniciar_olvida_los_mapeos_leidos_y_permite_pedirlos_de_nuevo(qtbot, seccion):
    veces: list[int] = []
    seccion.pide_mapeos.connect(lambda: veces.append(1))
    _activar(seccion)
    seccion.reiniciar()
    assert seccion._info is None and not seccion.boton_releer.isEnabled()
    seccion.chk_activar.setChecked(False)
    seccion.chk_activar.setChecked(True)
    assert len(veces) == 2


# --- Problemas junto a la sección -----------------------------------------------------------------


def test_los_errores_y_avisos_de_hardware_salen_junto_a_la_seccion_y_los_ajenos_no(qtbot, seccion):
    _activar(seccion)
    seccion.mostrar_problemas(
        [
            Problema(
                "hardware_cluster.pci[0]",
                "V-D52",
                Severidad.ERROR,
                {"mapeo": "gpu-a2", "nodos": "pve2"},
            ),
            Problema("hardware_cluster.pci[0]", "V-D57", Severidad.AVISO, {}),
            Problema("nombre", "V-01", Severidad.ERROR, {}),
        ]
    )
    assert "gpu-a2" in seccion._errores.text() and "pve2" in seccion._errores.text()
    assert "migrar" in seccion._avisos.text()
    assert "nombre" not in seccion._errores.text().lower()
    seccion.mostrar_problemas([])
    assert seccion._errores.isHidden() and seccion._avisos.isHidden()


def test_los_problemas_repetidos_salen_una_sola_vez(qtbot, seccion):
    _activar(seccion)
    p = Problema("hardware_cluster.pci[0]", "V-D57", Severidad.AVISO, {})
    seccion.mostrar_problemas([p, p, p])
    assert seccion._avisos.text().count("migrar") == 1


# --- Integración con el formulario ----------------------------------------------------------------


@pytest.fixture
def formulario(qtbot):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv_origen())
    f.establecer_modo(True)
    return f


def test_el_formulario_sin_tocar_la_seccion_no_lleva_hardware_ni_pide_lecturas(qtbot, formulario):
    pedidos: list[int] = []
    formulario.pide_mapeos.connect(lambda: pedidos.append(1))
    assert formulario.configuracion().hardware_cluster is None
    assert pedidos == []


def test_el_formulario_entrega_el_hardware_elegido_en_la_configuracion(qtbot, formulario):
    pedidos: list[int] = []
    formulario.pide_mapeos.connect(lambda: pedidos.append(1))
    sec = formulario.seccion_hardware
    sec.chk_activar.setChecked(True)
    assert pedidos == [1]
    formulario.establecer_hardware(INFO)
    _elegir(sec._filas[0], "gpu-a2")
    assert formulario.configuracion().hardware_cluster == HardwareCluster(
        pci=(AsignacionPCI("gpu-a2"),)
    )


def test_el_formulario_traslada_los_permisos_del_catalogo_a_la_seccion(qtbot, formulario):
    inv = formulario._inv
    inv.catalogo = (
        type(inv.catalogo)(**{**inv.catalogo.__dict__, "permisos": _permisos(("/", "VM.Audit"))})
        if inv.catalogo
        else None
    )
    formulario.establecer_hardware(INFO)
    sec = formulario.seccion_hardware
    sec.chk_activar.setChecked(True)
    formulario.establecer_hardware(INFO)
    fila = sec._filas[0]
    assert not fila.combo.model().item(fila.combo.findData("gpu-a2")).isEnabled()


def test_el_formulario_muestra_sin_marcadores_el_texto_de_la_seccion(qtbot, formulario):
    texto = textos_visibles(formulario.seccion_hardware)
    assert (
        "Hardware del clúster" in texto
        or formulario.seccion_hardware.title() == "Hardware del clúster"
    )
    assert "{" not in texto and "un dato" not in texto
