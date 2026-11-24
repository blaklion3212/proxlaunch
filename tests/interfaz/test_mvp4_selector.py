"""Selector «¿Cómo quieres crear la máquina?» (RF-O01, RF-O02, RF-O13, RF-O14, RF-O20, RF-O22).

Pruebas del widget aislado con capacidades calculadas por el núcleo real (sin red ni modales).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from proxlaunch.interfaz.dialogos.catalogo import FuenteCatalogo
from proxlaunch.interfaz.vistas.selector_origen import PeticionFuente, SelectorOrigen
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import (
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.origen.capacidades_origen import Via

from .apoyo_mvp4 import (
    ROL_10,
    VOLID_IMAGEN,
    VOLID_ISO,
    VOLID_VIRTIO,
    caps_origen,
    cfg_base,
    cfg_clon,
    cfg_import,
    cfg_iso,
    inv_origen,
    plantilla_pve,
    volumen,
)


@pytest.fixture
def selector(qtbot):
    s = SelectorOrigen()
    qtbot.addWidget(s)
    s.show()
    return s


@pytest.fixture
def con_caps(selector):
    """Selector con todas las vías disponibles (9.2, rol de 14 privilegios)."""
    selector.establecer_capacidades(caps_origen())
    return selector


def _motivo(selector: SelectorOrigen, origen: OrigenSO) -> str:
    etiqueta = selector.motivos[origen]
    return "" if etiqueta.isHidden() else etiqueta.text()


# --- CA-O01.1: cuatro opciones; el inicio es «Vacía» --------------------------------------------


def test_ca_o01_1_hay_cuatro_opciones_en_orden_y_el_inicio_es_vacia(selector):
    assert list(selector.opciones) == [
        OrigenSO.DISCO_VACIO,
        OrigenSO.ISO,
        OrigenSO.IMPORTAR_DISCO,
        OrigenSO.CLONAR_PLANTILLA,
    ]
    assert selector.origen == OrigenSO.DISCO_VACIO
    assert selector.opciones[OrigenSO.DISCO_VACIO].isChecked()
    textos = [r.text() for r in selector.opciones.values()]
    assert len(set(textos)) == 4 and all(textos)


def test_ca_o01_1_vacia_no_envia_origen_ni_so_en_la_configuracion(selector):
    cfg = selector.completar(cfg_base(tipo_so=TipoSO.LINUX, tpm=True, agente_qemu=True))
    assert cfg.origen == OrigenSO.DISCO_VACIO
    assert cfg.detalle_origen is None
    assert (cfg.tipo_so, cfg.tpm, cfg.agente_qemu) == (None, False, False)


def test_sin_servidor_solo_vacia_esta_habilitada_y_las_demas_dicen_por_que(selector):
    assert selector.opciones[OrigenSO.DISCO_VACIO].isEnabled()
    for origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO, OrigenSO.CLONAR_PLANTILLA):
        assert not selector.opciones[origen].isEnabled()
        assert "Conéctate" in _motivo(selector, origen)


# --- CA-O01.2 / RF-O02: opciones no disponibles, con el motivo escrito -------------------------


def test_ca_o02_1_con_todo_disponible_las_cuatro_opciones_estan_activas_sin_motivo(con_caps):
    for origen, radio in con_caps.opciones.items():
        assert radio.isEnabled()
        assert _motivo(con_caps, origen) == ""


def test_ca_o02_2_con_la_version_minima_8_4_importar_esta_habilitado_sin_motivo_de_version(
    selector,
):
    """DT-D3: la mínima 8.4 ya incluye importar; no queda motivo de versión."""
    selector.establecer_capacidades(caps_origen(inv_origen(version=(8, 4))))
    assert selector.opciones[OrigenSO.IMPORTAR_DISCO].isEnabled()
    assert _motivo(selector, OrigenSO.IMPORTAR_DISCO) == ""
    assert selector.opciones[OrigenSO.ISO].isEnabled()
    assert selector.opciones[OrigenSO.CLONAR_PLANTILLA].isEnabled()


def test_ca_o02_3_sin_storage_import_explica_la_ruta_exacta_en_proxmox(selector):
    inv = inv_origen(version=(8, 4), contenido_local="images,iso")
    selector.establecer_capacidades(caps_origen(inv))
    assert not selector.opciones[OrigenSO.IMPORTAR_DISCO].isEnabled()
    motivo = _motivo(selector, OrigenSO.IMPORTAR_DISCO)
    assert "Import" in motivo and "Datacenter" in motivo and "Contenido" in motivo


def test_ca_o01_2_sin_storage_iso_deshabilita_iso_y_explica_como_activarlo(selector):
    selector.establecer_capacidades(caps_origen(inv_origen(contenido_local="images")))
    assert not selector.opciones[OrigenSO.ISO].isEnabled()
    motivo = _motivo(selector, OrigenSO.ISO)
    assert "ISO" in motivo and "administrador" in motivo


def test_ca_o02_6_permisos_desconocidos_dejan_la_opcion_activa_con_aviso(selector):
    selector.establecer_capacidades(caps_origen(inv_origen(permisos_efectivos=None)))
    assert selector.opciones[OrigenSO.IMPORTAR_DISCO].isEnabled()
    assert "permisos" in _motivo(selector, OrigenSO.IMPORTAR_DISCO)


def test_ca_o01_2_la_explicacion_tambien_es_la_descripcion_accesible(selector):
    selector.establecer_capacidades(caps_origen(inv_origen(version=(8, 0))))
    radio = selector.opciones[OrigenSO.IMPORTAR_DISCO]
    assert radio.accessibleDescription() == _motivo(selector, OrigenSO.IMPORTAR_DISCO)
    assert radio.accessibleName() == radio.text()


def test_origen_marcado_que_deja_de_estar_disponible_vuelve_a_vacia(con_caps):
    con_caps.opciones[OrigenSO.IMPORTAR_DISCO].setChecked(True)
    assert con_caps.origen == OrigenSO.IMPORTAR_DISCO
    con_caps.establecer_capacidades(
        caps_origen(inv_origen(version=(8, 4), contenido_local="images,iso"))
    )
    assert con_caps.origen == OrigenSO.DISCO_VACIO
    assert con_caps.opciones[OrigenSO.DISCO_VACIO].isChecked()


def test_ca_o02_7_cambiar_las_capacidades_recalcula_las_opciones(selector):
    selector.establecer_capacidades(
        caps_origen(inv_origen(version=(8, 4), contenido_local="images,iso"))
    )
    assert not selector.opciones[OrigenSO.IMPORTAR_DISCO].isEnabled()
    selector.establecer_capacidades(caps_origen(inv_origen(version=(9, 2))))
    assert selector.opciones[OrigenSO.IMPORTAR_DISCO].isEnabled()
    assert _motivo(selector, OrigenSO.IMPORTAR_DISCO) == ""


def test_el_boton_por_que_no_puedo_abre_el_dialogo_de_capacidades(con_caps, qtbot):
    con_caps.boton_capacidades.click()
    dialogo = con_caps.dialogo_capacidades
    qtbot.addWidget(dialogo)
    assert dialogo.isVisible()
    dialogo.close()


# --- CA-O01.3: confirmación al cambiar de origen con datos elegidos ---------------------------


def test_ca_o01_3_cambiar_de_origen_con_iso_elegido_pide_confirmacion_y_cancelar_conserva(con_caps):
    preguntas: list[str] = []
    con_caps.confirmar_cambio = lambda que: preguntas.append(que) or False
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.establecer_catalogo([volumen(VOLID_ISO)], None, nodo="pve")
    assert con_caps.seleccionar_volid(FuenteCatalogo.ISO, VOLID_ISO)
    con_caps.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    assert preguntas == ["alpine.iso"]
    assert con_caps.origen == OrigenSO.ISO
    assert con_caps.opciones[OrigenSO.ISO].isChecked()
    assert "alpine.iso" in con_caps.valor_iso.text()


def test_ca_o01_3_confirmar_aplica_el_cambio(con_caps):
    con_caps.confirmar_cambio = lambda que: True
    con_caps.establecer_catalogo([volumen(VOLID_ISO)], None, nodo="pve")
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.seleccionar_volid(FuenteCatalogo.ISO, VOLID_ISO)
    con_caps.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    assert con_caps.origen == OrigenSO.CLONAR_PLANTILLA


def test_ca_o01_3_sin_datos_elegidos_cambiar_de_origen_no_pregunta(con_caps):
    con_caps.confirmar_cambio = lambda que: pytest.fail("no debía preguntar")
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.opciones[OrigenSO.IMPORTAR_DISCO].setChecked(True)
    assert con_caps.origen == OrigenSO.IMPORTAR_DISCO


def test_cambiar_de_origen_emite_origen_cambiado_y_seleccion_cambiada(con_caps, qtbot):
    with qtbot.waitSignals([con_caps.origen_cambiado, con_caps.seleccion_cambiada], timeout=500):
        con_caps.opciones[OrigenSO.ISO].setChecked(True)


# --- CA-O01.7: bloqueado durante un lote --------------------------------------------------------


def test_ca_o01_7_con_un_lote_en_ejecucion_el_selector_esta_deshabilitado(con_caps):
    con_caps.establecer_bloqueado(True)
    assert not con_caps.isEnabled()
    con_caps.establecer_bloqueado(False)
    assert con_caps.isEnabled()


# --- CA-O01.4 / O20.6: básico y avanzado ------------------------------------------------------


def test_ca_o01_4_en_basico_el_clon_solo_muestra_la_frase_del_modo_automatico(con_caps):
    con_caps.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    con_caps.establecer_modo(False)
    assert con_caps.etiqueta_modo.isVisible()
    assert not con_caps.fila_modo.isVisible()
    assert not con_caps.fila_storage_destino.isVisible()
    assert con_caps.modo_clon == ModoClon.AUTOMATICO
    # Núcleos, memoria y disco sí; sockets y tipo de CPU solo en avanzado.
    assert con_caps._filas_ajuste["cores"].isVisible()
    assert not con_caps._filas_ajuste["sockets"].isVisible()
    assert not con_caps._filas_ajuste["tipo_cpu"].isVisible()


def test_ca_o20_6_en_avanzado_el_clon_deja_elegir_el_tipo_de_copia_y_los_ajustes_tecnicos(con_caps):
    con_caps.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    con_caps.establecer_modo(True)
    assert con_caps.fila_modo.isVisible()
    assert not con_caps.etiqueta_modo.isVisible()
    assert con_caps._filas_ajuste["sockets"].isVisible()
    assert con_caps._filas_ajuste["tipo_cpu"].isVisible()
    # Almacenamiento de destino solo para la copia completa.
    assert not con_caps.fila_storage_destino.isVisible()
    con_caps.combo_modo.setCurrentIndex(con_caps.combo_modo.findData(ModoClon.COMPLETO.value))
    assert con_caps.fila_storage_destino.isVisible()


def test_ca_o01_4_en_basico_iso_muestra_fuente_y_so_pero_no_disco_compatible(con_caps):
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.WINDOWS_11.value))
    con_caps.establecer_modo(False)
    assert con_caps.paginas[OrigenSO.ISO].isVisible()
    assert con_caps.grupo_so.isVisible()
    assert not con_caps.casilla_disco_compatible.isVisible()
    con_caps.establecer_modo(True)
    assert con_caps.casilla_disco_compatible.isVisible()


def test_disco_compatible_no_aparece_con_linux_ni_en_avanzado(con_caps):
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.establecer_modo(True)
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.LINUX.value))
    assert not con_caps.casilla_disco_compatible.isVisible()


def test_vacia_oculta_el_grupo_de_sistema_operativo_y_los_drivers(con_caps):
    assert not con_caps.grupo_so.isVisible()
    assert not con_caps.grupo_drivers.isVisible()


# --- Asistente: se pide UNA vez al cambiar el SO ------------------------------------------------


def test_ca_o13_8_elegir_so_pide_una_sola_vez_el_asistente(con_caps):
    pedidos: list[tuple] = []
    con_caps.asistente_solicitado.connect(lambda t, b: pedidos.append((t, b)))
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    pedidos.clear()
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.WINDOWS_11.value))
    assert pedidos == [(TipoSO.WINDOWS_11, False)]


def test_el_asistente_no_se_pide_con_origen_vacia_o_clon(con_caps):
    pedidos: list[tuple] = []
    con_caps.asistente_solicitado.connect(lambda t, b: pedidos.append((t, b)))
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.LINUX.value))
    assert pedidos == []
    con_caps.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    assert pedidos == []


def test_disco_compatible_pide_solo_reescribir_el_bus(con_caps):
    pedidos: list[tuple] = []
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.establecer_modo(True)
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.WINDOWS_10.value))
    con_caps.asistente_solicitado.connect(lambda t, b: pedidos.append((t, b)))
    con_caps.casilla_disco_compatible.setChecked(True)
    assert pedidos == [(TipoSO.WINDOWS_10, True)]
    assert con_caps.disco_compatible


def test_la_lista_de_cambios_del_asistente_se_muestra_antes_a_despues(con_caps):
    from proxlaunch.nucleo.origen.asistente import aplicar_asistente

    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.WINDOWS_11.value))
    resultado = aplicar_asistente(cfg_base(), TipoSO.WINDOWS_11)
    con_caps.establecer_cambios(resultado.cambios)
    assert resultado.cambios
    assert con_caps.contenedor_cambios.isVisible()
    texto = con_caps.lista_cambios.text()
    assert texto.count("•") == len(resultado.cambios)
    assert "Windows 11" in con_caps.titulo_cambios.text()


def test_sin_cambios_que_hacer_lo_dice(con_caps):
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.LINUX.value))
    con_caps.establecer_cambios(())
    assert "no hace falta cambiar nada" in con_caps.titulo_cambios.text()
    assert not con_caps.contenedor_cambios.isVisible()


# --- completar(): la configuración respeta lo que el usuario dejó -----------------------------


def test_completar_iso_lleva_el_volid_el_so_y_los_drivers(con_caps):
    con_caps.establecer_catalogo([volumen(VOLID_ISO), volumen(VOLID_VIRTIO)], None, nodo="pve")
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.seleccionar_volid(FuenteCatalogo.ISO, VOLID_ISO)
    con_caps.seleccionar_volid(FuenteCatalogo.DRIVERS, VOLID_VIRTIO)
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.WINDOWS_11.value))
    cfg = con_caps.completar(cfg_base())
    assert cfg.origen == OrigenSO.ISO
    assert cfg.tipo_so == TipoSO.WINDOWS_11
    assert isinstance(cfg.detalle_origen, DetalleIso)
    assert cfg.detalle_origen.iso.volid == VOLID_ISO
    assert cfg.detalle_origen.drivers is not None
    assert cfg.detalle_origen.drivers.volid == VOLID_VIRTIO


def test_completar_importar_lleva_la_imagen_y_la_ampliacion(con_caps):
    con_caps.establecer_catalogo([volumen(VOLID_IMAGEN, Contenido.IMPORT)], None, nodo="pve")
    con_caps.opciones[OrigenSO.IMPORTAR_DISCO].setChecked(True)
    con_caps.seleccionar_volid(FuenteCatalogo.IMAGEN, VOLID_IMAGEN)
    con_caps.spin_ampliar.setValue(40)
    cfg = con_caps.completar(cfg_base())
    assert cfg.origen == OrigenSO.IMPORTAR_DISCO
    assert isinstance(cfg.detalle_origen, DetalleImportacion)
    assert cfg.detalle_origen.imagen.volid == VOLID_IMAGEN
    assert cfg.detalle_origen.ampliar_a_gib == 40


def test_completar_clon_no_envia_so_tpm_ni_agente_y_lleva_los_ajustes(con_caps):
    con_caps.establecer_catalogo([], [plantilla_pve()], nodo="pve")
    con_caps.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    con_caps.establecer_seleccion(FuenteCatalogo.PLANTILLA, plantilla_pve())
    con_caps.spin_cores.setValue(4)
    con_caps.spin_memoria.setValue(4096)
    cfg = con_caps.completar(cfg_base(tipo_so=TipoSO.LINUX, tpm=True, agente_qemu=True))
    assert (cfg.tipo_so, cfg.tpm, cfg.agente_qemu) == (None, False, False)
    assert isinstance(cfg.detalle_origen, DetalleClon)
    assert cfg.detalle_origen.plantilla.vmid == 9000
    assert cfg.detalle_origen.ajustes.cores == 4
    assert cfg.detalle_origen.ajustes.memoria_mib == 4096
    assert cfg.detalle_origen.ajustes.sockets is None  # 0 = igual que la plantilla


def test_completar_clon_en_basico_nunca_lleva_storage_de_destino(con_caps):
    con_caps.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    con_caps.establecer_storages_destino(["datos"])
    con_caps.combo_storage_destino.setCurrentIndex(1)
    cfg = con_caps.completar(cfg_base())
    assert cfg.detalle_origen.storage_destino is None


def test_completar_clon_completo_en_avanzado_lleva_el_storage_de_destino(con_caps):
    con_caps.establecer_modo(True)
    con_caps.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    con_caps.combo_modo.setCurrentIndex(con_caps.combo_modo.findData(ModoClon.COMPLETO.value))
    con_caps.establecer_storages_destino(["datos"])
    con_caps.combo_storage_destino.setCurrentIndex(1)
    cfg = con_caps.completar(cfg_base())
    assert cfg.detalle_origen.modo == ModoClon.COMPLETO
    assert cfg.detalle_origen.storage_destino == "datos"


@pytest.mark.parametrize(
    "cfg",
    [
        cfg_iso(drivers="local:iso/virtio-win-0.1.271.iso", tipo_so=TipoSO.WINDOWS_11),
        cfg_import(),
        cfg_clon(modo=ModoClon.COMPLETO),
    ],
    ids=["iso", "importar", "clon"],
)
def test_ca_o01_5_aplicar_y_completar_hacen_ida_y_vuelta(con_caps, cfg):
    con_caps.aplicar(cfg)
    assert con_caps.origen == cfg.origen
    vuelta = con_caps.completar(cfg_base())
    assert vuelta.origen == cfg.origen
    assert vuelta.detalle_origen == cfg.detalle_origen or (
        cfg.origen == OrigenSO.CLONAR_PLANTILLA
        and vuelta.detalle_origen.plantilla == cfg.detalle_origen.plantilla
        and vuelta.detalle_origen.modo == cfg.detalle_origen.modo
    )
    assert vuelta.tipo_so == cfg.tipo_so


def test_aplicar_una_configuracion_no_dispara_el_asistente_ni_muestra_cambios_inventados(con_caps):
    pedidos: list[tuple] = []
    con_caps.asistente_solicitado.connect(lambda t, b: pedidos.append((t, b)))
    con_caps.aplicar(cfg_iso(tipo_so=TipoSO.WINDOWS_11))
    assert pedidos == []
    assert not con_caps.contenedor_cambios.isVisible()


# --- RF-O14: drivers virtio-win -----------------------------------------------------------------


def _windows_con_iso(selector: SelectorOrigen) -> None:
    selector.opciones[OrigenSO.ISO].setChecked(True)
    selector.combo_so.setCurrentIndex(selector.combo_so.findData(TipoSO.WINDOWS_11.value))


def test_ca_o14_2_sin_virtio_en_el_servidor_ofrece_elegir_y_subir_pero_no_descargar(con_caps):
    _windows_con_iso(con_caps)
    assert con_caps.grupo_drivers.isVisible()
    assert "No hay ningún ISO de virtio-win" in con_caps.etiqueta_drivers.text()
    assert con_caps.boton_elegir_drivers.isVisible()
    assert con_caps.boton_subir_drivers.isVisible()
    # Decisión del orquestador: la vía «Descargarlo en el servidor» está oculta sin URL fija.
    assert not con_caps.boton_descargar_drivers.isVisible()


def test_ca_o14_2_con_url_fija_aparece_la_descarga_en_el_servidor(con_caps):
    _windows_con_iso(con_caps)
    con_caps.establecer_virtio_descargable(True)
    assert con_caps.boton_descargar_drivers.isVisible()
    assert con_caps.boton_descargar_drivers.isEnabled()


def test_ca_o14_1_si_el_servidor_ya_tiene_virtio_se_usa_sin_preguntar(con_caps):
    con_caps.establecer_catalogo([volumen(VOLID_VIRTIO)], None, nodo="pve")
    _windows_con_iso(con_caps)
    assert "virtio-win-0.1.271.iso" in con_caps.etiqueta_drivers.text()
    assert "ya está en el servidor" in con_caps.etiqueta_drivers.text()


def test_ca_o14_3_crear_sin_drivers_muestra_aviso_y_no_envia_drivers(con_caps):
    con_caps.establecer_catalogo([volumen(VOLID_ISO), volumen(VOLID_VIRTIO)], None, nodo="pve")
    _windows_con_iso(con_caps)
    con_caps.seleccionar_volid(FuenteCatalogo.ISO, VOLID_ISO)
    con_caps.seleccionar_volid(FuenteCatalogo.DRIVERS, VOLID_VIRTIO)
    con_caps.casilla_sin_drivers.setChecked(True)
    assert con_caps.aviso_sin_drivers.isVisible()
    assert not con_caps.boton_elegir_drivers.isEnabled()
    cfg = con_caps.completar(cfg_base())
    assert cfg.detalle_origen.sin_drivers is True
    assert cfg.detalle_origen.drivers is None


def test_los_drivers_no_se_ofrecen_con_linux(con_caps):
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.combo_so.setCurrentIndex(con_caps.combo_so.findData(TipoSO.LINUX.value))
    assert not con_caps.grupo_drivers.isVisible()


def test_subir_drivers_esta_deshabilitado_si_falta_el_permiso_de_subida(selector):
    selector.establecer_capacidades(caps_origen(inv_origen(privilegios=ROL_10)))
    _windows_con_iso(selector)
    assert not selector.boton_subir_drivers.isEnabled()


def test_pedir_subida_y_descarga_de_drivers_emite_la_peticion_de_fuente(con_caps):
    _windows_con_iso(con_caps)
    con_caps.establecer_virtio_descargable(True)
    subidas: list[PeticionFuente] = []
    bajadas: list[PeticionFuente] = []
    con_caps.pedir_subida.connect(subidas.append)
    con_caps.pedir_descarga.connect(bajadas.append)
    con_caps.boton_subir_drivers.click()
    con_caps.boton_descargar_drivers.click()
    assert [p.fuente for p in subidas] == [FuenteCatalogo.DRIVERS]
    assert [p.fuente for p in bajadas] == [FuenteCatalogo.DRIVERS]
    assert isinstance(subidas[0].padre, QWidget)


# --- Catálogo: abrir desde el selector ------------------------------------------------------------


def test_elegir_iso_abre_el_catalogo_y_pide_leerlo(con_caps, qtbot):
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    pedidas: list[FuenteCatalogo] = []
    con_caps.pedir_catalogo.connect(pedidas.append)
    con_caps.boton_elegir_iso.click()
    assert pedidas == [FuenteCatalogo.ISO]
    dialogo = con_caps.dialogo_catalogo
    assert dialogo is not None
    qtbot.addWidget(dialogo)
    assert dialogo.fuente == FuenteCatalogo.ISO
    dialogo.reject()
    assert con_caps.dialogo_catalogo is None


def test_los_botones_de_subir_y_descargar_del_catalogo_siguen_las_vias_del_selector(
    con_caps, qtbot
):
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.boton_elegir_iso.click()
    dialogo = con_caps.dialogo_catalogo
    qtbot.addWidget(dialogo)
    assert dialogo.boton_subir.isEnabled()
    con_caps.establecer_capacidades(caps_origen(inv_origen(privilegios=ROL_10)))
    assert not dialogo.boton_subir.isEnabled()
    assert dialogo.motivo_subir.text()
    dialogo.reject()


def test_elegir_una_fila_del_catalogo_deja_elegido_el_iso(con_caps, qtbot):
    con_caps.opciones[OrigenSO.ISO].setChecked(True)
    con_caps.establecer_catalogo([volumen(VOLID_ISO)], None, nodo="pve")
    con_caps.boton_elegir_iso.click()
    dialogo = con_caps.dialogo_catalogo
    qtbot.addWidget(dialogo)
    assert dialogo.seleccionar_volid(VOLID_ISO)
    dialogo.boton_elegir.click()
    assert con_caps.valor_iso.text() == "alpine.iso"
    assert con_caps.completar(cfg_base()).detalle_origen.iso.volid == VOLID_ISO


def test_las_vias_de_origen_de_cada_opcion_son_las_del_nucleo(con_caps):
    caps = caps_origen()
    assert (
        caps.disponible(Via.ISO) and caps.disponible(Via.IMPORTAR) and caps.disponible(Via.CLONAR)
    )
