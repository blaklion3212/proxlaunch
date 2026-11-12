"""FormularioVM, TablaDiscos y TablaRedes: valores por defecto, validaciones visibles,
límites por bus, nodo automático/manual y modo básico/avanzado (RF-13 a RF-17, RF-24)."""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM, gib_a_mib, mib_a_texto_gib
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ControladorScsi,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
)
from proxlaunch.nucleo.seleccion_nodo import MotivoNodo
from proxlaunch.nucleo.validacion import Severidad, validar_vm

CAPS = capacidades_para(Version("9.2", 9, 2, 0), None)


@pytest.fixture
def formulario(qtbot, inv_cluster):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv_cluster)
    return f


@pytest.fixture
def individual(qtbot, inv_individual):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv_individual)
    return f


def _validar(f, inv):
    cfg = f.configuracion()
    return validar_vm(cfg, inv, CAPS) + f.problemas_extra()


# --- Conversores ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("2", 2048),
        ("0,5", 512),
        ("0.5", 512),
        (" 4 ", 4096),
        ("abc", 0),
        ("", 0),
        ("nan", 0),
        ("inf", 0),
    ],
)
def test_gib_a_mib(texto, esperado):
    assert gib_a_mib(texto) == esperado


@pytest.mark.parametrize(("mib", "texto"), [(2048, "2"), (512, "0.5"), (1536, "1.5")])
def test_mib_a_texto_gib(mib, texto):
    assert mib_a_texto_gib(mib) == texto


# --- Valores por defecto (sección 5, CA-16.1, CA-17.1) -----------------------------------


def test_valores_por_defecto_del_formulario(formulario, inv_cluster):
    cfg = formulario.configuracion()
    assert cfg.vmid == inv_cluster.proximo_vmid
    assert cfg.nombre == ""
    assert (cfg.sockets, cfg.cores, cfg.memoria_mib) == (1, 2, 2048)
    assert cfg.firmware == Firmware.SEABIOS
    assert cfg.con_disco is True
    assert len(cfg.discos) == 1
    d = cfg.discos[0]
    assert (d.bus, d.tamano_gib, d.discard, d.ssd, d.iothread) == (Bus.SCSI, 32, True, True, True)
    assert d.storage == "local-lvm"  # el de mayor espacio libre
    assert cfg.redes == [InterfazRed("vmbr0", ModeloRed.VIRTIO, None)]
    assert cfg.ballooning is None


def test_formulario_recien_abierto_no_muestra_errores_en_rojo(formulario, inv_cluster):
    formulario.aplicar_problemas(_validar(formulario, inv_cluster))
    assert not formulario.fila_nombre.hay_error  # nombre vacío pero aún no tocado


def test_etiquetas_de_discos_por_defecto(formulario):
    assert formulario.etiquetas_discos() == ["scsi0"]


# --- Validaciones visibles (V-01, V-02, V-05, V-06) ----------------------------------------


def test_nombre_invalido_muestra_error_junto_al_campo_tras_editar(qtbot, formulario, inv_cluster):
    formulario.nombre.setText("mal nombre!")
    formulario.nombre.textEdited.emit("mal nombre!")
    formulario.aplicar_problemas(_validar(formulario, inv_cluster))
    assert formulario.fila_nombre.hay_error
    assert formulario.nombre.property("invalido") is True


def test_nombre_valido_quita_el_error(formulario, inv_cluster):
    formulario.nombre.setText("%%")
    formulario.nombre.textEdited.emit("%%")
    formulario.aplicar_problemas(_validar(formulario, inv_cluster))
    formulario.nombre.setText("srv-web-01")
    formulario.nombre.textEdited.emit("srv-web-01")
    formulario.aplicar_problemas(_validar(formulario, inv_cluster))
    assert not formulario.fila_nombre.hay_error


@pytest.mark.parametrize("texto", ["99", "abc", "", "1000000000"])
def test_vmid_fuera_de_rango_o_no_numerico_es_error(formulario, inv_cluster, texto):
    formulario.vmid.setText(texto)
    formulario.vmid.textEdited.emit(texto)
    problemas = _validar(formulario, inv_cluster)
    assert any(p.codigo == "V-02" for p in problemas)
    formulario.aplicar_problemas(problemas)
    assert formulario.fila_vmid.hay_error


@pytest.mark.parametrize("texto", ["0", "129", "x"])
def test_nucleos_invalidos_son_error(formulario, inv_cluster, texto):
    formulario.cores.setText(texto)
    formulario.cores.textEdited.emit(texto)
    problemas = _validar(formulario, inv_cluster)
    assert any(p.codigo == "V-05" and p.campo == "cores" for p in problemas)
    formulario.aplicar_problemas(problemas)
    assert formulario.fila_cores.hay_error


def test_total_de_cpu_se_actualiza(formulario):
    formulario.cores.setText("4")
    formulario.cores.textEdited.emit("4")
    formulario.combo_sockets.setCurrentIndex(1)  # 2 sockets
    assert "8" in formulario._total_cpu.text()
    formulario.cores.setText("")
    formulario.cores.textEdited.emit("")
    assert formulario._total_cpu.isHidden()


def test_memoria_menor_a_16_mib_es_error(formulario, inv_cluster):
    formulario.memoria.setText("0.01")
    formulario.memoria.textEdited.emit("0.01")
    problemas = _validar(formulario, inv_cluster)
    assert any(p.codigo == "V-06" for p in problemas)
    formulario.aplicar_problemas(problemas)
    assert formulario.fila_memoria.hay_error


def test_cambiar_cualquier_campo_emite_cambiado(qtbot, formulario):
    with qtbot.waitSignal(formulario.cambiado, timeout=1000):
        formulario.nombre.textEdited.emit("a")


def test_terminar_de_editar_vmid_distinto_emite_vmid_confirmado(qtbot, formulario):
    formulario.vmid.setText("250")
    with qtbot.waitSignal(formulario.vmid_confirmado, timeout=1000) as senal:
        formulario.vmid.editingFinished.emit()
    assert senal.args == [250]


def test_vmid_igual_al_sugerido_no_se_vuelve_a_comprobar(qtbot, formulario, inv_cluster):
    with qtbot.assertNotEmitted(formulario.vmid_confirmado):
        formulario.vmid.setText(str(inv_cluster.proximo_vmid))
        formulario.vmid.editingFinished.emit()


def test_vmid_no_numerico_no_emite_confirmacion(qtbot, formulario):
    with qtbot.assertNotEmitted(formulario.vmid_confirmado):
        formulario.vmid.setText("abc")
        formulario.vmid.editingFinished.emit()


def test_vmid_ocupado_agrega_problema_v03_con_siguiente(formulario):
    formulario.vmid.setText("100")
    formulario.marcar_vmid_ocupado(100, "105")
    extra = [p for p in formulario.problemas_extra() if p.codigo == "V-03"]
    assert extra and extra[0].params["siguiente"] == "105"
    formulario.aplicar_problemas(extra)
    assert formulario.fila_vmid.hay_error


def test_vmid_ocupado_deja_de_aplicar_si_el_usuario_cambia_el_numero(formulario):
    formulario.marcar_vmid_ocupado(100, "105")
    formulario.vmid.setText("200")
    assert not [p for p in formulario.problemas_extra() if p.codigo == "V-03"]


def test_limpiar_vmid_ocupado_y_sugerir(formulario):
    formulario.marcar_vmid_ocupado(100, "105")
    formulario.sugerir_vmid(105)
    assert formulario.vmid.text() == "105"
    assert not [p for p in formulario.problemas_extra() if p.codigo == "V-03"]
    formulario.limpiar_vmid_ocupado()  # idempotente


# --- Nodo: automático / manual / individual (CA-13.5, CA-13.6) ------------------------------


def test_cluster_muestra_selector_de_nodo_y_automatico_por_defecto(formulario):
    assert not formulario.fila_nodo.isHidden()
    assert formulario.es_automatico
    assert not formulario.combo_nodo.isEnabled()
    assert formulario.nodo_efectivo() == "pve1"  # más RAM libre
    assert formulario.motivo_nodo == MotivoNodo.MAS_MEMORIA_LIBRE
    assert "pve1" in formulario._texto_motivo.text()


def test_servidor_individual_no_muestra_selector_de_nodo(individual):
    assert individual.fila_nodo.isHidden()
    assert individual.nodo_efectivo() == "pve"


def test_nodo_caido_aparece_deshabilitado_en_el_combo(formulario):
    combo = formulario.combo_nodo
    i = combo.findData("pve2")
    assert "Sin conexión" in combo.itemText(i)
    assert not combo.model().item(i).isEnabled()


def test_pasar_a_manual_habilita_combo_y_emite_nodo_elegido(qtbot, formulario):
    with qtbot.waitSignal(formulario.nodo_elegido, timeout=1000) as senal:
        formulario._radio_manual.setChecked(True)
    assert senal.args == ["pve1"]
    assert formulario.combo_nodo.isEnabled()
    assert not formulario.es_automatico


def test_elegir_otro_nodo_manual_recarga_sus_recursos(qtbot, formulario):
    formulario._radio_manual.setChecked(True)
    with qtbot.waitSignal(formulario.nodo_elegido, timeout=1000) as senal:
        formulario.combo_nodo.setCurrentIndex(formulario.combo_nodo.findData("pve3"))
    assert senal.args == ["pve3"]
    assert formulario.nodo_efectivo() == "pve3"
    assert formulario.configuracion().nodo == "pve3"


def test_automatico_sin_nodo_con_espacio_muestra_error_en_lugar_de_nodo(formulario):
    formulario.tabla_discos.establecer_discos([Disco("local-lvm", 5000)])
    assert formulario.nodo_efectivo() == ""
    assert formulario.error_nodo is not None
    assert "5000" in formulario._texto_motivo.text()


def test_actualizar_recursos_del_nodo_efectivo_refresca_los_storages(qtbot, formulario):
    from .apoyo import storage

    nuevos = [storage("nuevo", "dir", "images", 10)]
    with qtbot.waitSignal(formulario.cambiado, timeout=1000):
        formulario.actualizar_recursos_nodo("pve1", nuevos, [])
    assert formulario.tabla_discos.discos()[0].storage == ""  # el anterior ya no existe
    assert not formulario.tabla_discos._aviso_nodo.isHidden()
    assert not formulario.tabla_redes.hay_bridges()
    assert any(p.codigo == "V-16.sinredes" for p in formulario.problemas_extra())


def test_actualizar_recursos_de_otro_nodo_no_toca_la_vista(formulario):
    antes = formulario.tabla_discos.discos()
    formulario.actualizar_recursos_nodo("pve3", [], [])
    assert formulario.tabla_discos.discos() == antes


def test_sin_almacenamiento_avisa_y_permite_sin_disco(qtbot, inv_individual):
    inv_individual.storages["pve"] = ()
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv_individual)
    assert not f._sin_storage.isHidden()
    assert f.configuracion().con_disco is False


# --- Sin disco (CA-16.3) -------------------------------------------------------------------


def test_sin_disco_oculta_la_tabla_y_no_envia_discos(formulario, inv_cluster):
    formulario.chk_sin_disco.setChecked(True)
    assert formulario.tabla_discos.isHidden()
    assert formulario.configuracion().con_disco is False
    assert not any(p.campo.startswith("discos") for p in _validar(formulario, inv_cluster))
    formulario.chk_sin_disco.setChecked(False)
    assert not formulario.tabla_discos.isHidden()


# --- Discos: agregar, quitar, índices, límites por bus ---------------------------------------


def test_agregar_disco_usa_el_mejor_storage(formulario):
    formulario.tabla_discos.agregar_disco()
    discos = formulario.configuracion().discos
    assert len(discos) == 2
    assert discos[1].storage == "local-lvm"
    assert discos[1].tamano_gib == 32


def test_no_se_puede_quitar_el_unico_disco(formulario):
    t = formulario.tabla_discos
    assert not t._filas[0].quitar.isEnabled()
    t._al_quitar(t._filas[0])
    assert len(t.discos()) == 1


def test_quitar_disco_renumera_y_emite_cambiado(qtbot, formulario):
    t = formulario.tabla_discos
    t.agregar_disco()
    t.agregar_disco()
    assert formulario.etiquetas_discos() == ["scsi0", "scsi1", "scsi2"]
    with qtbot.waitSignal(t.cambiado, timeout=1000):
        t._filas[1].quitar.click()
    assert formulario.etiquetas_discos() == ["scsi0", "scsi1"]
    assert len(t.discos()) == 2


def test_indices_por_bus_dos_scsi_y_un_virtio(formulario):
    # CA-16.2
    formulario.tabla_discos.establecer_discos(
        [
            Disco("local-lvm", 10, Bus.SCSI),
            Disco("local-lvm", 10, Bus.SCSI),
            Disco("local-lvm", 10, Bus.VIRTIO),
        ]
    )
    assert formulario.etiquetas_discos() == ["scsi0", "scsi1", "virtio0"]


def test_cambiar_bus_de_un_disco_renumera(formulario):
    t = formulario.tabla_discos
    t.agregar_disco()
    t._filas[1].bus.setCurrentIndex(t._filas[1].bus.findData(Bus.VIRTIO))
    assert formulario.etiquetas_discos() == ["scsi0", "virtio0"]


@pytest.mark.parametrize(
    ("bus", "maximo"), [(Bus.IDE, 4), (Bus.SATA, 6), (Bus.VIRTIO, 16), (Bus.SCSI, 31)]
)
def test_limite_de_discos_por_bus_v07(formulario, inv_cluster, bus, maximo):
    formulario.tabla_discos.establecer_discos([Disco("local-lvm", 1, bus)] * maximo)
    assert not [p for p in _validar(formulario, inv_cluster) if p.codigo == "V-07"]
    formulario.tabla_discos.agregar_disco(Disco("local-lvm", 1, bus))
    v07 = [p for p in _validar(formulario, inv_cluster) if p.codigo == "V-07"]
    assert len(v07) == 1
    assert v07[0].params["maximo"] == str(maximo)
    formulario.aplicar_problemas(v07)
    texto = formulario.tabla_discos._errores.text()
    assert str(maximo) in texto and bus.value in texto  # etiqueta del disco sobrante


def test_virtio_deshabilita_ssd_y_scsi_deja_las_tres_opciones(formulario):
    t = formulario.tabla_discos
    fila = t._filas[0]
    fila.bus.setCurrentIndex(fila.bus.findData(Bus.VIRTIO))
    assert not fila.ssd.isEnabled() and not fila.ssd.isChecked()  # V-12
    assert fila.iothread.isEnabled()
    fila.bus.setCurrentIndex(fila.bus.findData(Bus.SCSI))
    assert fila.ssd.isEnabled() and fila.ssd.isChecked()  # recupera la preferencia


def test_sata_deshabilita_iothread_con_explicacion(formulario):
    fila = formulario.tabla_discos._filas[0]
    fila.bus.setCurrentIndex(fila.bus.findData(Bus.SATA))
    assert not fila.iothread.isEnabled() and not fila.iothread.isChecked()
    assert fila.iothread.toolTip()  # V-11 explicado


def test_controlador_pci_deshabilita_iothread_en_scsi(formulario):
    formulario.combo_ctrl.setCurrentIndex(
        formulario.combo_ctrl.findData(ControladorScsi.VIRTIO_PCI)
    )
    assert not formulario.tabla_discos._filas[0].iothread.isEnabled()
    formulario.combo_ctrl.setCurrentIndex(
        formulario.combo_ctrl.findData(ControladorScsi.VIRTIO_SINGLE)
    )
    assert formulario.tabla_discos._filas[0].iothread.isEnabled()


def test_la_preferencia_del_usuario_sobrevive_a_un_bus_que_la_deshabilita(formulario):
    fila = formulario.tabla_discos._filas[0]
    fila.ssd.setChecked(False)  # el usuario lo desmarca
    fila.bus.setCurrentIndex(fila.bus.findData(Bus.VIRTIO))
    fila.bus.setCurrentIndex(fila.bus.findData(Bus.SCSI))
    assert not fila.ssd.isChecked()


# --- Tamaño, formato y espacio -------------------------------------------------------------


@pytest.mark.parametrize("texto", ["0", "-5", "1.5", "abc", ""])
def test_tamano_de_disco_invalido_v08_marca_el_campo(formulario, inv_cluster, texto):
    fila = formulario.tabla_discos._filas[0]
    fila.tamano.setText(texto)
    fila.tamano.textEdited.emit(texto)
    problemas = _validar(formulario, inv_cluster)
    assert any(p.codigo == "V-08" for p in problemas)
    formulario.aplicar_problemas(problemas)
    assert fila.tamano.property("invalido") is True
    assert formulario.tabla_discos._errores.text().startswith("scsi0:")


def test_corregir_el_tamano_quita_la_marca(formulario, inv_cluster):
    fila = formulario.tabla_discos._filas[0]
    fila.tamano.setText("0")
    formulario.aplicar_problemas(_validar(formulario, inv_cluster))
    fila.tamano.setText("10")
    formulario.aplicar_problemas(_validar(formulario, inv_cluster))
    assert not fila.tamano.property("invalido")
    assert formulario.tabla_discos._errores.isHidden()


def test_formato_automatico_en_lvmthin_y_elegible_en_directorio(formulario):
    fila = formulario.tabla_discos._filas[0]
    assert not fila.formato.isEnabled()  # CA-16.5: lvmthin solo raw
    fila.storage.setCurrentIndex(fila.storage.findData("local"))
    assert fila.formato.isEnabled()
    assert [fila.formato.itemData(i) for i in range(fila.formato.count())] == [
        FormatoDisco.AUTO,
        FormatoDisco.RAW,
        FormatoDisco.QCOW2,
    ]
    fila.storage.setCurrentIndex(fila.storage.findData("local-lvm"))
    assert not fila.formato.isEnabled()


def test_nunca_se_ofrece_subvol(formulario):
    fila = formulario.tabla_discos._filas[0]
    fila.storage.setCurrentIndex(fila.storage.findData("local"))
    datos = [str(fila.formato.itemData(i)) for i in range(fila.formato.count())]
    assert "subvol" not in datos  # CA-16.8


def test_espacio_insuficiente_en_storage_no_thin_es_error_v14(formulario, inv_cluster):
    formulario.tabla_discos.establecer_discos([Disco("local", 60)])  # local: 50 GiB, dir
    problemas = _validar(formulario, inv_cluster)
    v14 = [p for p in problemas if p.codigo == "V-14"]
    assert v14 and v14[0].severidad == Severidad.ERROR
    formulario.aplicar_problemas(problemas)
    assert "60" in formulario.tabla_discos._errores.text()


def test_espacio_insuficiente_en_thin_es_solo_aviso(formulario, inv_cluster):
    formulario._radio_manual.setChecked(True)  # en Automático ningún nodo tendría 200 GiB
    formulario.tabla_discos.establecer_discos([Disco("local-lvm", 200)])
    problemas = _validar(formulario, inv_cluster)
    assert [p.severidad for p in problemas if p.codigo.startswith("V-14")] == [Severidad.AVISO]
    formulario.aplicar_problemas(problemas)
    assert not formulario.tabla_discos._avisos.isHidden()
    assert formulario.tabla_discos._errores.isHidden()


def test_storage_inactivo_aparece_deshabilitado(formulario):
    fila = formulario.tabla_discos._filas[0]
    i = fila.storage.findData("inactivo")
    assert "Inactivo" in fila.storage.itemText(i)
    assert not fila.storage.model().item(i).isEnabled()


def test_cambio_de_nodo_avisa_de_storage_inexistente(formulario):
    formulario.tabla_discos.establecer_discos([Disco("local", 10)])
    formulario.actualizar_recursos_nodo("pve1", [], list(formulario._inv.bridges["pve1"]))
    assert "local" in formulario.tabla_discos._aviso_nodo.text()


# --- Redes ---------------------------------------------------------------------------------


def test_agregar_y_quitar_interfaces(qtbot, formulario):
    t = formulario.tabla_redes
    t.agregar_red()
    assert [r.bridge for r in t.redes()] == ["vmbr0", "vmbr0"]
    assert [f.indice.text() for f in t._filas] == ["net0", "net1"]
    with qtbot.waitSignal(t.cambiado, timeout=1000):
        t._filas[0].quitar.click()
    assert [f.indice.text() for f in t._filas] == ["net0"]
    assert len(t.redes()) == 1


def test_vlan_vacia_es_sin_etiqueta_y_valida_en_rango(formulario, inv_cluster):
    t = formulario.tabla_redes
    assert t.redes()[0].vlan is None
    t._filas[0].vlan.setText("120")
    assert t.redes()[0].vlan == 120
    assert not [p for p in _validar(formulario, inv_cluster) if p.codigo == "V-15"]


@pytest.mark.parametrize("texto", ["0", "4095", "abc"])
def test_vlan_invalida_v15_marca_el_campo(formulario, inv_cluster, texto):
    fila = formulario.tabla_redes._filas[0]
    fila.vlan.setText(texto)
    problemas = _validar(formulario, inv_cluster)
    assert any(p.codigo == "V-15" for p in problemas)
    formulario.aplicar_problemas(problemas)
    assert fila.vlan.property("invalido") is True
    assert formulario.tabla_redes._errores.text().startswith("net0:")


def test_bridge_inexistente_en_el_nodo_nuevo_se_avisa_y_bloquea(formulario, inv_cluster):
    # CA-11.7: la selección previa que no existe en el nodo nuevo se vacía con un aviso.
    formulario.tabla_redes.establecer_redes([InterfazRed("vmbr1")])
    formulario._radio_manual.setChecked(True)
    formulario.combo_nodo.setCurrentIndex(formulario.combo_nodo.findData("pve3"))
    assert "vmbr1" in formulario.tabla_redes._aviso_nodo.text()
    assert formulario.tabla_redes.redes()[0].bridge == ""
    assert any(p.codigo == "V-16" for p in _validar(formulario, inv_cluster))


def test_aviso_de_bridge_perdido_sobrevive_a_la_recarga_del_nodo(formulario, inv_cluster):
    formulario.tabla_redes.establecer_redes([InterfazRed("vmbr1")])
    formulario._radio_manual.setChecked(True)
    formulario.combo_nodo.setCurrentIndex(formulario.combo_nodo.findData("pve3"))
    # La ventana principal relee el nodo en segundo plano y llama a esto con lo leído.
    formulario.actualizar_recursos_nodo(
        "pve3", list(inv_cluster.storages["pve3"]), list(inv_cluster.bridges["pve3"])
    )
    assert "vmbr1" in formulario.tabla_redes._aviso_nodo.text()


def test_aviso_de_storage_perdido_sobrevive_a_la_recarga_del_nodo(formulario, inv_cluster):
    formulario.tabla_discos.establecer_discos([Disco("local", 10)])  # no existe en pve3
    formulario._radio_manual.setChecked(True)
    formulario.combo_nodo.setCurrentIndex(formulario.combo_nodo.findData("pve3"))
    formulario.actualizar_recursos_nodo(
        "pve3", list(inv_cluster.storages["pve3"]), list(inv_cluster.bridges["pve3"])
    )
    assert "local" in formulario.tabla_discos._aviso_nodo.text()


def test_nodo_sin_bridges_deshabilita_agregar_y_muestra_mensaje(formulario):
    formulario.actualizar_recursos_nodo("pve1", list(formulario._inv.storages["pve1"]), [])
    t = formulario.tabla_redes
    assert not t._agregar.isEnabled()
    assert not t._sin_redes.isHidden()


# --- Modo básico / avanzado (RF-24) --------------------------------------------------------


def test_modo_basico_oculta_los_campos_avanzados(formulario):
    assert formulario.fila_cpu.isHidden()
    assert formulario.fila_balloon.isHidden()
    assert formulario.fila_ctrl.isHidden()
    assert all(w.isHidden() for w in formulario.tabla_discos.widgets_avanzados)
    assert all(w.isHidden() for w in formulario.tabla_redes.widgets_avanzados)


def test_modo_avanzado_muestra_campos_sin_perder_valores(formulario):
    formulario.nombre.setText("mi-vm")
    formulario.memoria.setText("4")
    formulario.establecer_modo(True)
    assert not formulario.fila_cpu.isHidden()
    assert not formulario.fila_balloon.isHidden()
    assert all(not w.isHidden() for w in formulario.tabla_discos.widgets_avanzados)
    formulario.establecer_modo(False)
    assert formulario.nombre.text() == "mi-vm" and formulario.memoria.text() == "4"


def test_ballooning_activado_muestra_minimo_y_valida_v06(formulario, inv_cluster):
    formulario.establecer_modo(True)
    assert formulario.fila_balloon_min.isHidden()
    formulario.combo_balloon.setCurrentIndex(1)  # Activado
    assert not formulario.fila_balloon_min.isHidden()
    formulario.balloon_min.setText("8")  # mayor que los 2 GiB de memoria
    formulario.balloon_min.textEdited.emit("8")
    problemas = _validar(formulario, inv_cluster)
    assert any(p.codigo == "V-06" and p.campo.startswith("ballooning") for p in problemas)
    formulario.aplicar_problemas(problemas)
    assert formulario.fila_balloon_min.hay_error


def test_ballooning_desactivado_se_envia_como_inactivo(formulario):
    formulario.combo_balloon.setCurrentIndex(2)
    b = formulario.configuracion().ballooning
    assert b is not None and b.activo is False


def test_cpu_host_muestra_su_aviso_solo_en_avanzado(formulario):
    formulario.establecer_modo(True)
    assert formulario._aviso_cpu.isHidden()
    formulario.combo_cpu.setCurrentIndex(formulario.combo_cpu.findData("host"))
    assert not formulario._aviso_cpu.isHidden()


def test_uefi_muestra_almacenamiento_efi_en_avanzado(formulario):
    formulario.establecer_modo(True)
    assert formulario.fila_efi.isHidden()
    formulario.combo_firmware.setCurrentIndex(1)
    assert not formulario.fila_efi.isHidden()
    assert formulario.configuracion().firmware == Firmware.OVMF
    assert formulario.configuracion().storage_efi is None  # automático (CA-14.2)
    formulario.combo_efi.setCurrentIndex(formulario.combo_efi.findData("local"))
    assert formulario.configuracion().storage_efi == "local"


# --- Inventario actualizado, "crear otra" y bloqueo -----------------------------------------


def test_actualizar_inventario_conserva_lo_escrito(formulario, inv_cluster):
    formulario.nombre.setText("conservar")
    formulario.nombre.textEdited.emit("conservar")
    formulario.vmid.setText("300")
    formulario.vmid.textEdited.emit("300")
    inv_cluster.proximo_vmid = 555
    formulario.establecer_inventario(inv_cluster)
    assert formulario.nombre.text() == "conservar"
    assert formulario.vmid.text() == "300"  # CA-03.3: el usuario ya lo tocó


def test_actualizar_inventario_sin_tocar_vmid_toma_el_nuevo(formulario, inv_cluster):
    inv_cluster.proximo_vmid = 555
    formulario.establecer_inventario(inv_cluster)
    assert formulario.vmid.text() == "555"


def test_reiniciar_inventario_restablece_los_valores(formulario, inv_cluster):
    formulario.nombre.setText("temporal")
    formulario.establecer_inventario(inv_cluster, reiniciar=True)
    assert formulario.nombre.text() == ""


def test_preparar_otra_vacia_nombre_y_conserva_el_resto(formulario):
    formulario.nombre.setText("primera")
    formulario.memoria.setText("8")
    formulario.marcar_vmid_ocupado(101, "102")
    formulario.preparar_otra()
    assert formulario.nombre.text() == ""
    assert formulario.memoria.text() == "8"
    assert not formulario.fila_nombre.tocado
    assert not [p for p in formulario.problemas_extra() if p.codigo == "V-03"]


def test_bloquear_deshabilita_el_formulario(formulario):
    formulario.bloquear(True)
    assert not formulario.isEnabled()
    formulario.bloquear(False)
    assert formulario.isEnabled()


def test_aplicar_configuracion_ida_y_vuelta(formulario, hacer_cfg_ui):
    cfg = hacer_cfg_ui()
    formulario.aplicar_configuracion(cfg)
    otra = formulario.configuracion()
    assert otra.nombre == cfg.nombre
    assert otra.discos == cfg.discos
    assert otra.redes == cfg.redes
    assert otra.ballooning == cfg.ballooning
    assert otra.tipo_cpu == cfg.tipo_cpu
