"""Progreso, resumen, barra superior, detalles técnicos y piezas de campos (RF-19, RF-20, RF-21)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit

from proxlaunch.interfaz.vistas.barra_superior import (
    BarraSuperior,
    cargar_svg,
    nombre_logotipo,
    nombre_simbolo,
)
from proxlaunch.interfaz.vistas.campos import (
    EnlaceLabel,
    FilaCampo,
    boton_ayuda,
    etiqueta,
    mensaje,
    poner_mensaje,
    poner_propiedad,
)
from proxlaunch.interfaz.vistas.detalles_tecnicos import DetallesTecnicos, texto_detalles
from proxlaunch.interfaz.vistas.progreso import ETAPAS, PanelProgreso
from proxlaunch.interfaz.vistas.resumen import (
    ResumenVM,
    nombre_campo,
    opciones_avanzadas_no_predeterminadas,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Nodo, Topologia
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    Bus,
    ControladorScsi,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
)
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo import UPID, resultado

# --- PanelProgreso -------------------------------------------------------------------------


@pytest.fixture
def panel(qtbot):
    p = PanelProgreso()
    qtbot.addWidget(p)
    p.show()
    return p


def _botones(p):
    return {
        "otra": p.boton_crear_otra.isVisible(),
        "seguir": p.boton_seguir.isVisible(),
        "comprobar": p.boton_comprobar.isVisible(),
        "volver": p.boton_volver.isVisible(),
    }


def test_estado_inicial_sin_tareas_ni_botones(panel):
    assert "Sin tareas" in panel.barra.format()
    assert panel.barra.value() == 0
    assert not any(_botones(panel).values())
    assert panel.texto_upid == ""


def test_las_etapas_son_las_del_cuadro_ca_20_2():
    assert ETAPAS == (
        Etapa.VALIDANDO,
        Etapa.ENVIANDO,
        Etapa.CREANDO,
        Etapa.COMPROBANDO,
        Etapa.LISTO,
    )


def test_etapas_avanzan_sin_porcentaje_falso(panel):
    panel.iniciar()
    valores = []
    for etapa in ETAPAS:
        panel.establecer_etapa(etapa)
        valores.append(panel.barra.value())
        assert panel.barra.format() != ""
        assert "%" not in panel.barra.format()
    assert valores == sorted(valores)
    assert valores[-1] == panel.barra.maximum()


def test_etapa_actual_marcada_y_previas_con_visto(panel):
    panel.establecer_etapa(Etapa.CREANDO)
    lbl = panel._lbl_etapas
    assert lbl[Etapa.VALIDANDO].text().startswith("✓")
    assert lbl[Etapa.ENVIANDO].text().startswith("✓")
    assert lbl[Etapa.CREANDO].text().startswith("●")
    assert not lbl[Etapa.LISTO].text().startswith(("✓", "●"))


def test_etapa_listo_marca_todas_como_hechas(panel):
    panel.establecer_etapa(Etapa.LISTO)
    assert all(label.text().startswith("✓") for label in panel._lbl_etapas.values())


def test_upid_se_muestra_al_recibirlo_y_es_monoespaciado(panel):
    panel.establecer_upid(UPID)
    assert panel.texto_upid == UPID
    assert panel._upid.isVisible()
    assert panel._upid.property("mono") is True  # CA-20.9
    assert panel._upid.isReadOnly()


def test_upid_vacio_lo_oculta(panel):
    panel.establecer_upid(UPID)
    panel.establecer_upid(None)
    assert not panel._upid.isVisible()


def test_copiar_upid_al_portapapeles(panel):
    panel.establecer_upid(UPID)
    panel._copiar.click()
    assert QApplication.clipboard().text() == UPID


def test_ok_muestra_crear_otra_y_marca_exito(panel):
    panel.mostrar_resultado("Creada", Desenlace.OK, UPID)
    assert _botones(panel) == {"otra": True, "seguir": False, "comprobar": False, "volver": False}
    assert panel._mensaje.property("exito") is True
    assert panel.texto_mensaje == "Creada"


def test_con_avisos_ofrece_crear_otra_y_estilo_de_aviso(panel):
    panel.mostrar_resultado("Creada con avisos", Desenlace.CON_AVISOS, UPID)
    assert _botones(panel)["otra"] and not _botones(panel)["volver"]
    assert panel._mensaje.property("aviso") is True
    assert not panel._mensaje.property("error")


def test_error_ofrece_volver_y_estilo_de_error(panel):
    panel.mostrar_resultado("falló", Desenlace.ERROR, None)
    assert _botones(panel) == {"otra": False, "seguir": False, "comprobar": False, "volver": True}
    assert panel._mensaje.property("error") is True


def test_parcial_se_trata_como_error(panel):
    panel.mostrar_resultado("parcial", Desenlace.PARCIAL, UPID)
    assert panel._mensaje.property("error") is True
    assert _botones(panel)["volver"]


def test_tiempo_agotado_ofrece_seguir_comprobar_y_volver(panel):
    panel.mostrar_resultado("sigue", Desenlace.TIEMPO_AGOTADO, UPID)
    assert _botones(panel) == {"otra": False, "seguir": True, "comprobar": True, "volver": True}
    assert panel._mensaje.property("aviso") is True  # CA-20.6: no es un error


def test_conexion_perdida_ofrece_comprobar_y_volver_sin_seguir(panel):
    panel.mostrar_resultado("sin red", Desenlace.CONEXION_PERDIDA, UPID)
    assert _botones(panel) == {"otra": False, "seguir": False, "comprobar": True, "volver": True}
    assert panel._mensaje.property("aviso") is True


def test_cancelado_es_neutral_sin_color_de_exito_ni_error(panel):
    panel.mostrar_resultado("Cancelado", Desenlace.CANCELADO, None)
    for propiedad in ("exito", "aviso", "error"):
        assert not panel._mensaje.property(propiedad)
    assert _botones(panel)["volver"]


def test_botones_emiten_las_senales_correspondientes(qtbot, panel):
    panel.mostrar_resultado("sigue", Desenlace.TIEMPO_AGOTADO, UPID)
    with qtbot.waitSignal(panel.seguir_esperando, timeout=500):
        panel.boton_seguir.click()
    with qtbot.waitSignal(panel.comprobar_ahora, timeout=500):
        panel.boton_comprobar.click()
    with qtbot.waitSignal(panel.volver, timeout=500):
        panel.boton_volver.click()
    panel.mostrar_resultado("ok", Desenlace.OK, UPID)
    with qtbot.waitSignal(panel.crear_otra, timeout=500):
        panel.boton_crear_otra.click()


def test_mensaje_intermedio_oculta_los_botones(panel):
    panel.mostrar_resultado("sigue", Desenlace.TIEMPO_AGOTADO, UPID)
    panel.mostrar_progreso_mensaje("Comprobando...")
    assert not any(_botones(panel).values())
    assert panel.texto_mensaje == "Comprobando..."
    assert not panel._mensaje.property("aviso")


def test_reiniciar_limpia_todo(panel):
    panel.mostrar_resultado("ok", Desenlace.OK, UPID)
    panel.reiniciar()
    assert panel.texto_upid == ""
    assert not panel._mensaje.isVisible()
    assert not any(_botones(panel).values())


# --- DetallesTecnicos ----------------------------------------------------------------------


def test_texto_detalles_incluye_codigo_params_original_y_log():
    err = ErrorProxLaunch(
        CodigoError.SIN_ESPACIO, {"storage": "local-lvm"}, "unable to create VM 100"
    )
    res = resultado(Desenlace.ERROR, err, log=["linea 1", "linea 2"])
    texto = texto_detalles(err, res)
    for esperado in (
        "sin_espacio",
        "storage: local-lvm",
        "unable to create VM 100",
        UPID,
        "VMID: 101",
        "pve1",
        "linea 1",
        "linea 2",
    ):
        assert esperado in texto


def test_texto_detalles_vacio_sin_error_ni_resultado():
    assert texto_detalles(None) == ""


def test_texto_detalles_sin_upid_no_lo_menciona():
    assert "UPID" not in texto_detalles(None, resultado(upid=None))


def test_widget_de_detalles_se_oculta_si_no_hay_texto(qtbot):
    w = DetallesTecnicos()
    qtbot.addWidget(w)
    w.show()
    w.establecer("")
    assert not w.isVisible()
    w.establecer("algo")
    assert w.isVisible() and w.texto == "algo"
    assert "Ver" in w._boton.text()
    w._boton.setChecked(True)
    assert "Ocultar" in w._boton.text() and w._texto.isVisible()
    w.limpiar()
    assert w.texto == "" and not w.isVisible()


def test_detalles_desplegados_por_peticion(qtbot):
    w = DetallesTecnicos()
    qtbot.addWidget(w)
    w.show()
    w.establecer("x", desplegar=True)
    assert w._texto.isVisible()


# --- ResumenVM -----------------------------------------------------------------------------


@pytest.fixture
def resumen(qtbot):
    r = ResumenVM()
    qtbot.addWidget(r)
    r.show()
    return r


def _actualizar(
    r,
    cfg,
    problemas=(),
    *,
    avanzado=False,
    bloqueo=None,
    ocupado=False,
    nodo=None,
    motivo="",
    etiquetas=("scsi0",),
):
    r.actualizar(
        cfg,
        list(etiquetas),
        list(problemas),
        avanzado=avanzado,
        motivo_nodo=motivo,
        bloqueo=bloqueo,
        ocupado=ocupado,
        nodo=nodo,
    )


def test_resumen_en_lenguaje_llano(resumen, hacer_cfg_ui):
    """CA-19.1."""
    cfg = hacer_cfg_ui()
    _actualizar(resumen, cfg, etiquetas=("virtio0", "sata0"))
    html = resumen.texto_html
    for esperado in (
        "srv-web-01",
        "150",
        "pve1",
        "4 GiB",
        "virtio0: 20 GiB en local-lvm",
        "VLAN 120",
        "net0",
        "8 procesadores",
    ):
        assert esperado in html


def test_resumen_escapa_html_del_nombre(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(nombre="<b>x</b>"))
    assert "<b>x</b>" not in resumen.texto_html
    assert "&lt;b&gt;" in resumen.texto_html


def test_resumen_sin_disco_ni_red(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(con_disco=False, redes=[]))
    assert "Sin disco" in resumen.texto_html and "Sin red" in resumen.texto_html


def test_resumen_muestra_motivo_del_nodo(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(), motivo="más memoria y espacio libres")
    assert "más memoria" in resumen.texto_html


def test_sin_errores_el_boton_crear_se_habilita(resumen, hacer_cfg_ui):
    """CA-19.1."""
    _actualizar(resumen, hacer_cfg_ui())
    assert resumen.boton_crear.isEnabled()
    assert resumen.texto_pendientes == ""


def test_con_errores_el_boton_se_bloquea_y_lista_lo_pendiente(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(), [Problema("nombre", "V-01", Severidad.ERROR)])
    assert not resumen.boton_crear.isEnabled()
    assert "Nombre" in resumen.texto_pendientes
    assert resumen.boton_crear.toolTip()


def test_un_aviso_no_bloquea_y_se_muestra(resumen, hacer_cfg_ui):
    p = Problema(
        "discos[0].tamano_gib",
        "V-14.thin",
        Severidad.AVISO,
        {"storage": "x", "pedido_gib": "9", "libre_gib": "1"},
    )
    _actualizar(resumen, hacer_cfg_ui(), [p])
    assert resumen.boton_crear.isEnabled()
    assert not resumen._avisos.isHidden()


def test_bloqueo_por_permiso_deshabilita_y_explica(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(), bloqueo="falta VM.Allocate")
    assert not resumen.boton_crear.isEnabled()
    assert resumen._motivo.text() == "falta VM.Allocate"


def test_ocupado_deshabilita_el_boton(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(), ocupado=True)
    assert not resumen.boton_crear.isEnabled()


def test_doble_clic_emite_una_sola_solicitud(qtbot, resumen, hacer_cfg_ui):
    # CA-19.6
    _actualizar(resumen, hacer_cfg_ui())
    recibidas = []
    resumen.crear_solicitado.connect(lambda: recibidas.append(1))
    resumen.boton_crear.click()
    resumen.boton_crear.click()
    resumen._al_pulsar()  # incluso saltándose el estado visual del botón
    assert recibidas == [1]
    assert not resumen.boton_crear.isEnabled()


def test_liberar_permite_un_nuevo_envio(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui())
    resumen.boton_crear.click()
    resumen.liberar()
    _actualizar(resumen, hacer_cfg_ui())
    assert resumen.boton_crear.isEnabled()


def test_boton_deshabilitado_no_emite(qtbot, resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(), [Problema("nombre", "V-01", Severidad.ERROR)])
    with qtbot.assertNotEmitted(resumen.crear_solicitado):
        resumen._al_pulsar()


def test_avisos_de_recursos_del_nodo_no_bloquean(resumen, hacer_cfg_ui):
    nodo = Nodo("pve1", True, 1024, 2)
    _actualizar(resumen, hacer_cfg_ui(), nodo=nodo)  # pide 8 CPU y 4 GiB
    texto = resumen._avisos.text()
    assert "núcleos" in texto and "memoria" in texto
    assert resumen.boton_crear.isEnabled()


def test_sin_datos_del_nodo_no_hay_aviso_de_recursos(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(), nodo=Nodo("pve1", True, None, None))
    assert resumen._avisos.isHidden()


def test_modo_basico_lista_opciones_avanzadas_no_predeterminadas(resumen, hacer_cfg_ui):
    # CA-24.5
    """CA-24.2."""
    _actualizar(resumen, hacer_cfg_ui(), avanzado=False, etiquetas=("virtio0", "sata0"))
    assert "Opciones avanzadas" in resumen.texto_html
    assert "x86-64-v3" in resumen.texto_html


def test_modo_avanzado_no_repite_la_lista_de_opciones(resumen, hacer_cfg_ui):
    _actualizar(resumen, hacer_cfg_ui(), avanzado=True)
    assert "Opciones avanzadas" not in resumen.texto_html


def test_configuracion_por_defecto_no_tiene_opciones_avanzadas(hacer_cfg_ui):
    from proxlaunch.nucleo.valores_defecto import configuracion_por_defecto

    cfg = configuracion_por_defecto(100, "x", "n", "local-lvm", "vmbr0")
    assert opciones_avanzadas_no_predeterminadas(cfg) == []


def test_todas_las_opciones_avanzadas_se_enumeran(hacer_cfg_ui):
    cfg = hacer_cfg_ui(
        firmware=Firmware.OVMF,
        storage_efi="local",
        controlador_scsi=ControladorScsi.VIRTIO_PCI,
        ballooning=Ballooning(False, 0),
        discos=[
            Disco("local", 5, Bus.IDE, FormatoDisco.QCOW2, discard=False, ssd=False, iothread=False)
        ],
        redes=[InterfazRed("vmbr0", ModeloRed.E1000)],
    )
    texto = "\n".join(opciones_avanzadas_no_predeterminadas(cfg))
    for esperado in (
        "Ballooning desactivado",
        "virtio-scsi-pci",
        "UEFI se guarda en: local",
        "conexión IDE",
        "formato qcow2",
        "sin discard",
        "e1000",
    ):
        assert esperado in texto


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [
        ("nombre", "Nombre"),
        ("discos[1].bus", "Disco"),
        ("redes[0].vlan", "Red"),
        ("ballooning.minimo_mib", "Ballooning"),
        # Enmienda aprobada (orquestador, MVP 4): nunca se muestra un identificador crudo;
        # un campo sin mapear da "".
        ("raro", ""),
    ],
)
def test_nombre_corto_del_campo(campo, esperado):
    assert nombre_campo(campo) == esperado


# --- BarraSuperior -------------------------------------------------------------------------


@pytest.fixture
def barra(qtbot):
    b = BarraSuperior()
    qtbot.addWidget(b)
    b.show()
    return b


def test_barra_sin_conexion(barra):
    assert barra._perfil.text() == "Sin conexión"
    assert barra.texto_version == "" and barra.texto_ssl == ""


def test_barra_muestra_perfil_version_y_usuario(barra):
    barra.establecer_conexion("Lab", "9.2", False, False, "ana@pve!lab")
    assert barra._perfil.text() == "Lab · ana@pve!lab"
    assert barra.texto_version == "Proxmox VE 9.2"
    assert barra.texto_ssl == ""


def test_barra_version_forzada_y_ssl_sin_verificar(barra):
    """CA-26.2."""
    barra.establecer_conexion("Lab", "8.1", True, True)
    assert "(forzada)" in barra.texto_version
    assert "sin verificar" in barra.texto_ssl
    assert barra._perfil.text() == "Lab"


def test_barra_topologia_cluster_individual_y_degradada(barra, inv_cluster, inv_individual):
    barra.establecer_topologia(inv_cluster.topologia)
    assert "lab" in barra.texto_topologia and "3" in barra.texto_topologia
    barra.establecer_topologia(inv_individual.topologia)
    assert barra.texto_topologia == "Servidor individual"
    barra.establecer_topologia(inv_cluster.topologia, degradada=True)
    assert "desconocida" in barra.texto_topologia
    barra.establecer_topologia(None)
    assert barra._topologia.isHidden()


def test_barra_limpiar_restablece(barra):
    barra.establecer_conexion("Lab", "9.2", True, True)
    barra.limpiar()
    assert barra.texto_version == "" and barra.texto_ssl == ""


def test_topologia_sin_nombre_de_cluster_no_revienta(barra):
    barra.establecer_topologia(Topologia(True, None, (Nodo("a", True, 1, 1),)))
    assert "1" in barra.texto_topologia


@pytest.mark.parametrize("tema", ["claro", "oscuro"])
def test_logos_por_tema_cargan_un_pixmap_valido(qtbot, tema):
    from PySide6.QtCore import QSize

    assert not cargar_svg(nombre_logotipo(tema), QSize(100, 60)).isNull()
    assert not cargar_svg(nombre_simbolo(tema), QSize(32, 32), 2.0).isNull()


def test_actualizar_logo_de_la_barra(barra):
    barra.actualizar_logo("claro")
    assert not barra._logo.pixmap().isNull()


# --- campos --------------------------------------------------------------------------------


def test_poner_propiedad_solo_repinta_si_cambia(qtbot):
    w = QLineEdit()
    qtbot.addWidget(w)
    poner_propiedad(w, "invalido", True)
    assert w.property("invalido") is True
    poner_propiedad(w, "invalido", False)
    assert w.property("invalido") is False


def test_mensaje_oculto_y_poner_mensaje(qtbot):
    m = mensaje(error=True)
    qtbot.addWidget(m)
    m.show()
    assert m.property("error") is True
    poner_mensaje(m, "algo")
    assert m.isVisible() and m.text() == "algo"
    poner_mensaje(m, None)
    assert not m.isVisible() and m.text() == ""
    poner_mensaje(m, "ojo", aviso=True)
    assert m.property("aviso") is True and not m.property("error")


def test_etiqueta_con_propiedades(qtbot):
    e = etiqueta("x", secundario=True, mono=True)
    qtbot.addWidget(e)
    assert e.property("secundario") is True and e.property("mono") is True
    assert e.wordWrap()


def test_enlace_emite_clicked_con_clic_y_teclado(qtbot):
    from PySide6.QtCore import Qt

    e = EnlaceLabel("ver")
    qtbot.addWidget(e)
    e.show()
    with qtbot.waitSignal(e.clicked, timeout=500):
        qtbot.mouseClick(e, Qt.MouseButton.LeftButton)
    with qtbot.waitSignal(e.clicked, timeout=500):
        qtbot.keyClick(e, Qt.Key.Key_Return)
    with qtbot.assertNotEmitted(e.clicked):
        qtbot.keyClick(e, Qt.Key.Key_A)
        qtbot.mouseClick(e, Qt.MouseButton.RightButton)


def test_boton_ayuda_lleva_el_texto_como_sugerencia(qtbot):
    b = boton_ayuda("vmid")
    qtbot.addWidget(b)
    assert b.toolTip() and b.accessibleDescription() == b.toolTip()
    b.click()  # muestra la sugerencia sin bloquear


def test_fila_campo_no_muestra_error_hasta_tocar(qtbot):
    campo = QLineEdit()
    fila = FilaCampo("Nombre", campo, "vmid")
    qtbot.addWidget(fila)
    fila.show()
    fila.mostrar_error("mal")
    assert not fila.hay_error and not campo.property("invalido")
    fila.marcar_tocado()
    fila.mostrar_error("mal")
    assert fila.hay_error and campo.property("invalido") is True
    assert campo.toolTip() == "<qt>mal</qt>"  # SEG-A-05: el tooltip va escapado
    fila.mostrar_error(None)
    assert not fila.hay_error and campo.toolTip() == ""
    fila.mostrar_aviso("ojo")
    assert not fila._aviso_extra.isHidden()
    assert isinstance(fila._etiqueta, QLabel)
