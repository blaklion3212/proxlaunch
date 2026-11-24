"""Formulario con un servidor ARM64 (RF-D2.7, RF-D2.10 y RF-D2.12): opciones ocultas, valores
adaptados con V-D08 y la marca «experimental».

Derivadas de docs/requisitos/fase-d.md: CA-D2.7.1, CA-D2.7.5, CA-D2.12.1 y CA-D2.12.2, y de
docs/arquitectura/fase-d.md §11.I7a (la ventana oculta IDE/SATA y E1000 en las tablas) y §11.I7b
(el formulario adapta con V-D08 y expone ``arquitectura_actual`` y ``cambios_arquitectura``).
Sin red ni modales.
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtWidgets import QListView

from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    ArquitecturaNodo,
    FuenteArquitectura,
)
from proxlaunch.nucleo.modelos.vm import Bus, Disco, Firmware, InterfazRed, ModeloRed, OrigenSO

from . import test_ventana_principal as _base
from .apoyo import sesion_falsa
from .apoyo_fase_b import textos_visibles
from .apoyo_mvp4 import caps_origen, inv_origen, plantilla_pve
from .test_ventana_principal import conectar, esperar_validacion

entorno = _base.entorno  # fixture base de la ventana

ARM = ArquitecturaNodo(Arquitectura.AARCH64, FuenteArquitectura.KERNEL)
X86 = ArquitecturaNodo(Arquitectura.X86_64, FuenteArquitectura.KERNEL)


def _inv_arm(nodo: str = "pve", arq: ArquitecturaNodo = ARM):
    inv = inv_origen()
    inv.arquitecturas = {nodo: arq}
    return inv


@pytest.fixture
def formulario(qtbot):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv_origen())
    f.establecer_modo(True)
    return f


def _filas_ocultas(combo) -> dict[str, bool]:
    vista: QListView = combo.view()
    return {combo.itemText(i): vista.isRowHidden(i) for i in range(combo.count())}


def _items_habilitados(combo) -> list[str]:
    modelo = combo.model()
    return [combo.itemText(i) for i in range(combo.count()) if modelo.item(i).isEnabled()]


def _a_arm(f: FormularioVM, nodo: str = "pve") -> None:
    inv = _inv_arm(nodo)
    f.establecer_arquitecturas(inv)


# --- Estado inicial x86: nada de ARM --------------------------------------------------------------


def test_ca_d2_12_2_en_un_nodo_x86_no_aparece_la_palabra_experimental(formulario):
    assert formulario.arquitectura_actual == Arquitectura.X86_64
    assert formulario.cambios_arquitectura == ()
    assert "experimental" not in textos_visibles(formulario).lower()


def test_en_x86_se_ofrecen_todas_las_opciones(formulario):
    assert _items_habilitados(formulario.combo_firmware) == ["SeaBIOS (clásico)", "UEFI (OVMF)"]
    tipos = [formulario.combo_cpu.itemText(i) for i in range(formulario.combo_cpu.count())]
    assert "x86-64-v2-AES" in tipos and "kvm64" in tipos


# --- CA-D2.7.1: nodo aarch64 único ----------------------------------------------------------------


def test_ca_d2_7_1_en_aarch64_seabios_no_es_elegible_y_el_firmware_queda_en_uefi(formulario):
    _a_arm(formulario)
    assert formulario.arquitectura_actual == Arquitectura.AARCH64
    assert _items_habilitados(formulario.combo_firmware) == ["UEFI (OVMF)"]
    assert formulario.configuracion().firmware == Firmware.OVMF


def test_ca_d2_7_1_en_aarch64_el_combo_de_cpu_solo_ofrece_host_y_max(formulario):
    _a_arm(formulario)
    tipos = [formulario.combo_cpu.itemText(i) for i in range(formulario.combo_cpu.count())]
    assert tipos[:2] == ["host", "max"]
    for x86 in ("x86-64-v2-AES", "x86-64-v2", "x86-64-v3", "x86-64-v4", "kvm64"):
        assert x86 not in tipos


def test_ca_d2_7_1_el_tipo_de_cpu_x86_elegido_se_adapta_a_host(formulario):
    formulario.combo_cpu.setCurrentIndex(formulario.combo_cpu.findText("x86-64-v3"))
    assert formulario.configuracion().tipo_cpu == "x86-64-v3"
    _a_arm(formulario)
    assert formulario.configuracion().tipo_cpu == "host"


def test_ca_d2_7_5_pasar_de_x86_a_arm_adapta_los_valores_con_v_d08_y_los_lista(formulario):
    formulario.combo_firmware.setCurrentIndex(formulario.combo_firmware.findData(Firmware.SEABIOS))
    _a_arm(formulario)
    cambios = {c.campo: (c.antes, c.despues) for c in formulario.cambios_arquitectura}
    assert cambios["firmware"] == ("seabios", "ovmf")
    assert cambios["tipo_cpu"][1] == "host"
    texto = textos_visibles(formulario)
    assert "ARM64" in texto and "Cambié estos valores" in texto
    assert "{" not in texto


def test_ca_d2_7_5_el_formulario_no_se_corrompe_y_vuelve_a_x86_sin_perder_el_resto(formulario):
    formulario.nombre.setText("web-01")
    antes = formulario.configuracion()
    _a_arm(formulario)
    formulario.establecer_arquitecturas(
        dataclasses.replace(inv_origen(), arquitecturas={"pve": X86})
    )
    despues = formulario.configuracion()
    assert despues.nombre == antes.nombre and despues.memoria_mib == antes.memoria_mib
    assert formulario.arquitectura_actual == Arquitectura.X86_64
    assert formulario.cambios_arquitectura == ()
    assert _items_habilitados(formulario.combo_firmware) == ["SeaBIOS (clásico)", "UEFI (OVMF)"]


def test_ca_d2_7_5_los_discos_sata_e_ide_pasan_a_scsi_y_el_modelo_e1000_a_virtio(formulario):
    formulario.tabla_discos.establecer_discos(
        [
            Disco("local-lvm", 8, Bus.SATA),
            Disco("local-lvm", 8, Bus.IDE),
            Disco("local-lvm", 8, Bus.VIRTIO),
        ]
    )
    formulario.tabla_redes.establecer_redes([InterfazRed("vmbr0", ModeloRed.E1000)])
    _a_arm(formulario)
    cfg = formulario.configuracion()
    assert [d.bus for d in cfg.discos] == [Bus.SCSI, Bus.SCSI, Bus.VIRTIO]
    assert [r.modelo for r in cfg.redes] == [ModeloRed.VIRTIO]
    campos = {c.campo for c in formulario.cambios_arquitectura}
    assert {"discos[0].bus", "discos[1].bus", "redes[0].modelo"} <= campos


def test_ca_d2_7_5_un_clon_no_se_adapta_porque_hereda_de_la_plantilla(qtbot):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    inv = inv_origen(plantillas=None)
    f.establecer_inventario(inv)
    f.selector_origen.establecer_capacidades(caps_origen(inv))
    f.selector_origen.establecer_catalogo([], [plantilla_pve(nombre="base")], nodo="pve")
    f.selector_origen.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    _a_arm(f)
    assert f.cambios_arquitectura == ()


# --- CA-D2.12.1: marca «experimental» -------------------------------------------------------------


def test_ca_d2_12_1_el_aviso_permanente_de_arm64_esta_a_la_vista(formulario):
    _a_arm(formulario)
    assert not formulario._aviso_arq.isHidden()
    assert "experimental" in formulario._aviso_arq.text()
    assert "ARM64" in formulario._aviso_arq.text()


def test_ca_d2_12_1_el_nodo_aarch64_se_muestra_con_arm64_experimental_en_el_selector(formulario):
    _a_arm(formulario)
    assert formulario._nombre_nodo("pve") == "pve (ARM64, experimental)"
    textos = [formulario.combo_nodo.itemText(i) for i in range(formulario.combo_nodo.count())]
    assert any("ARM64, experimental" in t for t in textos) or "ARM64" in textos_visibles(formulario)


def test_ca_d2_12_1_el_combo_de_arquitectura_manual_ofrece_detectar_x86_y_arm_con_marca(formulario):
    textos = [
        formulario.combo_arquitectura.itemText(i)
        for i in range(formulario.combo_arquitectura.count())
    ]
    assert textos[0].startswith("Detectarla")
    assert any("x86" in t for t in textos)
    assert any("ARM64" in t and "experimental" in t for t in textos)


def test_el_selector_manual_de_arquitectura_emite_el_nodo_y_la_eleccion(qtbot, formulario):
    idx = formulario.combo_arquitectura.findData(Arquitectura.AARCH64)
    with qtbot.waitSignal(formulario.arquitectura_forzada, timeout=500) as señal:
        formulario.combo_arquitectura.setCurrentIndex(idx)
    assert señal.args == ["pve", Arquitectura.AARCH64]


def test_el_selector_manual_en_detectar_emite_none(qtbot, formulario):
    formulario.combo_arquitectura.setCurrentIndex(1)  # fuerza un cambio de índice
    with qtbot.waitSignal(formulario.arquitectura_forzada, timeout=500) as señal:
        formulario.combo_arquitectura.setCurrentIndex(0)
    assert señal.args == ["pve", None]


def test_forzar_arm64_a_mano_en_la_ventana_deja_el_nodo_como_aarch64_manual(qtbot, entorno):
    conectar(qtbot, entorno, sesion_falsa())
    v = entorno.ventana
    esperar_validacion(qtbot, v)
    nodo = v.formulario.nodo_efectivo()
    combo = v.formulario.combo_arquitectura
    combo.setCurrentIndex(combo.findData(Arquitectura.AARCH64))
    info = v._inv.arquitecturas.get(nodo)
    assert info is not None and info.arquitectura == Arquitectura.AARCH64
    assert info.fuente == FuenteArquitectura.MANUAL


def test_la_arquitectura_forzada_a_mano_se_dice_como_tal(formulario):
    inv = _inv_arm()
    inv.arquitecturas = {"pve": ArquitecturaNodo(Arquitectura.AARCH64, FuenteArquitectura.MANUAL)}
    formulario.establecer_arquitecturas(inv)
    assert formulario.combo_arquitectura.currentData() == Arquitectura.AARCH64
    assert "ARM64" in formulario._texto_arq.text()


def test_un_nodo_de_arquitectura_ilegible_se_trata_como_x86_sin_aviso_de_arm(formulario):
    inv = inv_origen()
    inv.arquitecturas = {
        "pve": ArquitecturaNodo(Arquitectura.DESCONOCIDA, FuenteArquitectura.NINGUNA, "sin_permiso")
    }
    formulario.establecer_arquitecturas(inv)
    assert formulario.arquitectura_actual == Arquitectura.X86_64
    assert "experimental" not in formulario._aviso_arq.text()
    assert formulario.cambios_arquitectura == ()


# --- La ventana oculta IDE/SATA y E1000 en las tablas (I7a) ---------------------------------------


def _ventana_con_arm(qtbot, entorno, arq=ARM):
    inv = entorno.inv
    inv.arquitecturas = {"pve1": arq, "pve3": arq}
    conectar(qtbot, entorno, sesion_falsa())
    esperar_validacion(qtbot, entorno.ventana)
    return entorno.ventana


def test_ca_d2_7_1_la_ventana_oculta_sata_e_ide_en_el_bus_de_los_discos_en_arm64(qtbot, entorno):
    v = _ventana_con_arm(qtbot, entorno)
    fila = v.formulario.tabla_discos._filas[0]
    ocultas = _filas_ocultas(fila.bus)
    assert ocultas["SATA"] is True and ocultas["IDE"] is True
    assert ocultas["SCSI"] is False and ocultas["VirtIO"] is False
    assert _items_habilitados(fila.bus) == ["SCSI", "VirtIO"]


def test_ca_d2_7_1_la_ventana_oculta_el_modelo_e1000_en_arm64(qtbot, entorno):
    v = _ventana_con_arm(qtbot, entorno)
    fila = v.formulario.tabla_redes._filas[0]
    assert _filas_ocultas(fila.modelo) == {"VirtIO": False, "Intel E1000": True}


def test_ca_d2_7_1_en_x86_las_cuatro_conexiones_y_las_dos_tarjetas_estan_a_la_vista(qtbot, entorno):
    v = _ventana_con_arm(qtbot, entorno, arq=X86)
    assert not any(_filas_ocultas(v.formulario.tabla_discos._filas[0].bus).values())
    assert not any(_filas_ocultas(v.formulario.tabla_redes._filas[0].modelo).values())


def test_ca_d2_7_1_un_disco_nuevo_agregado_en_arm_tambien_oculta_sata_e_ide(qtbot, entorno):
    v = _ventana_con_arm(qtbot, entorno)
    v.formulario.tabla_discos.agregar_disco()
    for fila in v.formulario.tabla_discos._filas:
        assert _filas_ocultas(fila.bus)["SATA"] is True


def test_ca_d2_7_1_ocultar_no_borra_el_valor_de_un_disco_cargado_con_sata(qtbot, entorno):
    """Un disco SATA de un lote guardado no se pierde en silencio al ocultar la opción: el
    formulario lo adapta con V-D08 (que se avisa), no la tabla."""
    v = _ventana_con_arm(qtbot, entorno)
    tabla = v.formulario.tabla_discos
    tabla._arm = False  # simula que el disco se cargó antes de conocer la arquitectura
    tabla.establecer_discos([Disco("local-lvm", 8, Bus.SATA)])
    tabla.establecer_arquitectura(Arquitectura.X86_64)
    tabla.establecer_arquitectura(Arquitectura.AARCH64)
    assert tabla.discos()[0].bus == Bus.SATA  # la tabla no cambia valores
    assert _filas_ocultas(tabla._filas[0].bus)["SATA"] is True


def test_ca_d2_12_1_el_nodo_arm_sale_con_la_marca_en_el_selector_de_nodos_de_la_ventana(
    qtbot, entorno
):
    v = _ventana_con_arm(qtbot, entorno)
    textos = [v.formulario.combo_nodo.itemText(i) for i in range(v.formulario.combo_nodo.count())]
    assert any("pve1" in t and "ARM64, experimental" in t for t in textos)
    assert not any("pve2" in t and "experimental" in t for t in textos)


def test_ca_d2_12_1_el_resumen_de_la_ventana_dice_arm64_experimental(qtbot, entorno):
    v = _ventana_con_arm(qtbot, entorno)
    assert "ARM64: experimental, sin probar en un servidor arm64" in v.resumen.texto_html
    assert "pve1 (ARM64, experimental)" in v.resumen.texto_html


def test_ca_d2_12_2_con_nodos_x86_el_resumen_no_dice_experimental(qtbot, entorno):
    v = _ventana_con_arm(qtbot, entorno, arq=X86)
    assert "experimental" not in v.resumen.texto_html.lower()
