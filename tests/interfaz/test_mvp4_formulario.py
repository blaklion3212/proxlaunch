"""FormularioVM con el origen del SO: qué se oculta o bloquea por origen y cómo actúa el asistente
de sistema operativo (RF-O01, RF-O13, RF-O15, RF-O20, RF-O22; CA-O13.8, CA-O13.9)."""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.dialogos.catalogo import FuenteCatalogo
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import TipoSO
from proxlaunch.nucleo.modelos.vm import Bus, ControladorScsi, Firmware, ModeloRed, OrigenSO
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_mvp4 import (
    VOLID_IMAGEN,
    VOLID_ISO,
    caps_origen,
    cfg_import,
    cfg_iso,
    inv_origen,
    plantilla_pve,
    volumen,
)


@pytest.fixture
def inv():
    return inv_origen()


@pytest.fixture
def formulario(qtbot, inv):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    f.selector_origen.establecer_capacidades(caps_origen(inv))
    f.selector_origen.establecer_catalogo(
        [volumen(VOLID_ISO), volumen(VOLID_IMAGEN, Contenido.IMPORT)],
        [plantilla_pve()],
        nodo="pve",
    )
    return f


def elegir_so(f: FormularioVM, tipo: TipoSO) -> None:
    combo = f.selector_origen.combo_so
    combo.setCurrentIndex(combo.findData(tipo.value))


def marcar(f: FormularioVM, origen: OrigenSO) -> None:
    f.selector_origen.opciones[origen].setChecked(True)


# --- Origen vacío: el formulario es el de M1-M3 -


def test_ca_o03_1_con_origen_vacia_la_configuracion_no_lleva_nada_del_origen(formulario):
    cfg = formulario.configuracion()
    assert cfg.origen == OrigenSO.DISCO_VACIO
    assert cfg.detalle_origen is None
    assert (cfg.tipo_so, cfg.tpm, cfg.agente_qemu) == (None, False, False)
    assert formulario._caja_firmware.isVisible()
    assert formulario._caja_computo.isVisible()
    assert formulario._caja_discos.isVisible()
    assert formulario._caja_red.isVisible()


# --- Plantilla: el hardware es el de la plantilla (CA-O20) -------------------------------------


def test_ca_o20_1_con_plantilla_se_ocultan_firmware_computo_discos_y_red(formulario):
    marcar(formulario, OrigenSO.CLONAR_PLANTILLA)
    assert not formulario._caja_firmware.isVisible()
    assert not formulario._caja_computo.isVisible()
    assert not formulario._caja_discos.isVisible()
    assert not formulario._caja_red.isVisible()
    assert formulario._nota_clon.isVisible()
    # General (nombre, VMID, nodo) sigue visible: eso lo elige siempre el usuario.
    assert formulario._caja_general.isVisible()


def test_ca_o20_1_al_volver_a_vacia_reaparecen_las_cajas_ocultas(formulario):
    marcar(formulario, OrigenSO.CLONAR_PLANTILLA)
    marcar(formulario, OrigenSO.DISCO_VACIO)
    assert formulario._caja_firmware.isVisible()
    assert formulario._caja_discos.isVisible()
    assert not formulario._nota_clon.isVisible()


# --- Importar: el primer disco es la imagen (CA-O15.4, CA-O17.1) ------------------------------


def test_ca_o17_1_importar_bloquea_el_tamano_del_primer_disco_y_explica_por_que(formulario):
    marcar(formulario, OrigenSO.IMPORTAR_DISCO)
    f0 = formulario.tabla_discos._filas[0]
    assert not f0.tamano.isEnabled()
    assert "imagen" in f0.tamano.toolTip()
    assert formulario._nota_importar.isVisible()


def test_ca_o17_1_importar_solo_bloquea_el_tamano_del_primero_no_el_de_los_demas(formulario):
    formulario.tabla_discos.agregar_disco()
    marcar(formulario, OrigenSO.IMPORTAR_DISCO)
    filas = formulario.tabla_discos._filas
    assert not filas[0].tamano.isEnabled()
    assert filas[1].tamano.isEnabled()


def test_ca_o15_4_importar_desmarca_y_desactiva_sin_disco(formulario):
    formulario.chk_sin_disco.setChecked(True)
    assert formulario.chk_sin_disco.isChecked()
    marcar(formulario, OrigenSO.IMPORTAR_DISCO)
    assert not formulario.chk_sin_disco.isChecked()
    assert not formulario.chk_sin_disco.isEnabled()
    assert formulario.configuracion().con_disco is True


def test_al_salir_de_importar_se_reactivan_sin_disco_y_el_tamano(formulario):
    marcar(formulario, OrigenSO.IMPORTAR_DISCO)
    marcar(formulario, OrigenSO.DISCO_VACIO)
    assert formulario.chk_sin_disco.isEnabled()
    assert formulario.tabla_discos._filas[0].tamano.isEnabled()
    assert not formulario._nota_importar.isVisible()


# --- Asistente de SO (CA-O13.x) ------------------------------------------------------------------


def test_ca_o13_1_windows_11_escribe_uefi_tpm_agente_y_virtio_en_los_widgets(formulario):
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    assert formulario.combo_firmware.currentData() == Firmware.OVMF
    assert formulario.chk_tpm.isChecked()
    assert formulario.chk_agente.isChecked()
    assert formulario.combo_ctrl.currentData() == ControladorScsi.VIRTIO_SINGLE
    cfg = formulario.configuracion()
    assert cfg.tipo_so == TipoSO.WINDOWS_11
    assert cfg.firmware == Firmware.OVMF and cfg.tpm and cfg.agente_qemu
    assert cfg.discos[0].bus == Bus.SCSI
    assert all(r.modelo == ModeloRed.VIRTIO for r in cfg.redes)


def test_ca_o13_2_windows_10_no_lleva_tpm(formulario):
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    elegir_so(formulario, TipoSO.WINDOWS_10)
    cfg = formulario.configuracion()
    assert cfg.tipo_so == TipoSO.WINDOWS_10
    assert cfg.tpm is False
    assert cfg.agente_qemu is True


def test_ca_o13_3_linux_no_lleva_tpm_y_no_cambia_el_firmware_del_perfil(formulario):
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.LINUX)
    cfg = formulario.configuracion()
    assert cfg.tipo_so == TipoSO.LINUX
    assert cfg.tpm is False
    assert cfg.firmware == Firmware.SEABIOS


def test_ca_o13_11_el_agente_de_qemu_no_se_envia_con_otro(formulario):
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.OTRO)
    cfg = formulario.configuracion()
    assert cfg.tipo_so == TipoSO.OTRO
    assert cfg.agente_qemu is False and cfg.tpm is False


def test_ca_o13_8_el_avanzado_puede_cambiar_tpm_y_agente_y_la_configuracion_lo_respeta(formulario):
    formulario.establecer_modo(True)
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    assert formulario.fila_tpm.isVisible() and formulario.fila_agente.isVisible()
    formulario.chk_tpm.setChecked(False)
    formulario.chk_agente.setChecked(False)
    cfg = formulario.configuracion()
    assert cfg.tpm is False and cfg.agente_qemu is False
    assert cfg.tipo_so == TipoSO.WINDOWS_11  # el SO se conserva; no se reaplica el asistente


def test_ca_o13_8_el_avanzado_puede_dejar_seabios_y_la_configuracion_lo_respeta(formulario):
    formulario.establecer_modo(True)
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    formulario.combo_firmware.setCurrentIndex(formulario.combo_firmware.findData(Firmware.SEABIOS))
    assert formulario.configuracion().firmware == Firmware.SEABIOS


def test_ca_o13_8_en_basico_las_casillas_tpm_y_agente_no_se_ven(formulario):
    formulario.establecer_modo(False)
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    assert not formulario.fila_tpm.isVisible()
    assert not formulario.fila_agente.isVisible()
    assert formulario.configuracion().tpm is True  # pero su valor es el que se envía


def test_ca_o13_8_el_asistente_se_aplica_una_sola_vez_al_cambiar_el_so(formulario):
    """Después de aplicarlo, un cambio posterior del usuario en un widget no lo pisa el resumen."""
    formulario.establecer_modo(True)
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    formulario.chk_tpm.setChecked(False)
    formulario.cambiado.emit()
    formulario.selector_origen.seleccion_cambiada.emit()
    assert formulario.chk_tpm.isChecked() is False
    assert formulario.configuracion().tpm is False


def test_ca_o13_9_el_asistente_no_toca_nucleos_memoria_ni_tamano_de_disco(formulario):
    formulario.cores.setText("6")
    formulario.memoria.setText("8")
    formulario.tabla_discos._filas[0].tamano.setText("77")
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    cfg = formulario.configuracion()
    assert cfg.cores == 6
    assert cfg.memoria_mib == 8 * 1024
    assert cfg.discos[0].tamano_gib == 77


def test_la_lista_de_cambios_del_selector_refleja_lo_que_el_asistente_escribio(formulario):
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    cambios = formulario.selector_origen.cambios_asistente
    assert cambios
    assert formulario.selector_origen.contenedor_cambios.isVisible()


def test_disco_compatible_reescribe_solo_el_bus_del_primer_disco(formulario):
    formulario.establecer_modo(True)
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_10)
    formulario.chk_tpm.setChecked(True)  # el usuario deja un valor propio
    formulario.selector_origen.casilla_disco_compatible.setChecked(True)
    cfg = formulario.configuracion()
    assert cfg.discos[0].bus == Bus.SATA
    assert cfg.tpm is True  # no se reaplicó todo el asistente


def test_volver_a_vacia_no_envia_so_tpm_ni_agente_aunque_se_haya_aplicado_el_asistente(formulario):
    marcar(formulario, OrigenSO.ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    marcar(formulario, OrigenSO.DISCO_VACIO)
    cfg = formulario.configuracion()
    assert (cfg.tipo_so, cfg.tpm, cfg.agente_qemu) == (None, False, False)


def test_ca_o13_12_windows_11_con_seabios_o_sin_tpm_da_error_v_o05(formulario, inv):
    formulario.establecer_modo(True)
    marcar(formulario, OrigenSO.ISO)
    formulario.selector_origen.seleccionar_volid(FuenteCatalogo.ISO, VOLID_ISO)
    elegir_so(formulario, TipoSO.WINDOWS_11)
    formulario.chk_tpm.setChecked(False)
    cfg = formulario.configuracion()
    cfg.vmid, cfg.nombre = 150, "w11"
    problemas = validar_vm(cfg, inv, capacidades_para(inv.version, None))
    assert any(p.codigo == "V-O05" and p.severidad == Severidad.ERROR for p in problemas)


# --- Perfil / lote guardado con origen -


def test_aplicar_hardware_con_origen_carga_el_selector_sin_pedir_el_asistente(formulario):
    formulario.aplicar_hardware(cfg_iso(tipo_so=TipoSO.WINDOWS_11, tpm=True))
    assert formulario.selector_origen.origen == OrigenSO.ISO
    assert formulario.selector_origen.tipo_so == TipoSO.WINDOWS_11
    assert formulario.chk_tpm.isChecked()


def test_ca_o13_8_aplicar_hardware_de_un_perfil_con_so_aplica_el_asistente_una_vez(formulario):
    perfil = cfg_iso(tipo_so=TipoSO.WINDOWS_11)  # tpm=False, SeaBIOS: el asistente lo corrige
    formulario.aplicar_hardware(perfil, asistente=True)
    assert formulario.combo_firmware.currentData() == Firmware.OVMF
    assert formulario.chk_tpm.isChecked()


def test_aplicar_hardware_sin_origen_deja_el_origen_actual(formulario):
    marcar(formulario, OrigenSO.CLONAR_PLANTILLA)
    formulario.aplicar_hardware(cfg_import(), origen=False)
    assert formulario.selector_origen.origen == OrigenSO.CLONAR_PLANTILLA


def test_ca_o01_5_la_configuracion_de_un_origen_cargado_hace_ida_y_vuelta(formulario):
    formulario.aplicar_hardware(cfg_import())
    cfg = formulario.configuracion()
    assert cfg.origen == OrigenSO.IMPORTAR_DISCO
    assert cfg.detalle_origen.imagen.volid == VOLID_IMAGEN
    assert cfg.con_disco is True
    assert formulario.chk_sin_disco.isEnabled() is False


# --- Storage de discos recordado (RF-O05) --------------------------------------------------------


def test_ca_o05_3_el_storage_recordado_es_el_de_partida_de_los_discos(qtbot):
    inv = inv_origen(extra_images=True)
    f = FormularioVM()
    qtbot.addWidget(f)
    f.establecer_storage_recordado("local")
    f.establecer_inventario(inv)
    assert f.configuracion().discos[0].storage == "local"


def test_ca_o05_5_usar_storage_mv_cambia_los_discos_que_usaban_el_de_partida(qtbot):
    inv = inv_origen(extra_images=True)
    f = FormularioVM()
    qtbot.addWidget(f)
    f.establecer_inventario(inv)
    # Sin recordado, el de más espacio libre (MVP 1): «datos» con 400 GiB.
    assert f.configuracion().discos[0].storage == "datos"
    f.usar_storage_mv("local-lvm")
    assert f.configuracion().discos[0].storage == "local-lvm"
