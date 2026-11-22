"""Capturas de pantalla de la guía de usuario (``docs/img/NN-nombre.png``).

Se ejecutan con ``.venv/bin/pytest -m capturas -p no:cacheprovider tests/interfaz/capturas_guia``.
Cada prueba deja un estado de la aplicación real (con servicios falsos y datos inventados) y
guarda una imagen. Nada toca la red, el llavero ni carpetas reales.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter, QPixmap, QTextCursor
from PySide6.QtWidgets import QGroupBox, QMessageBox, QScrollArea

from proxlaunch.interfaz import controlador_origen
from proxlaunch.interfaz.dialogos import plantilla_imagen as plantilla_imagen_modulo
from proxlaunch.interfaz.dialogos.acerca_de import DialogoAcercaDe
from proxlaunch.interfaz.dialogos.capacidades import DialogoCapacidades
from proxlaunch.interfaz.dialogos.catalogo import DialogoCatalogo, FuenteCatalogo
from proxlaunch.interfaz.dialogos.conexion import DialogoConexion
from proxlaunch.interfaz.dialogos.confirmar_deshacer import DialogoConfirmarDeshacerForzado
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.dos_factores import DialogoDosFactores
from proxlaunch.interfaz.dialogos.elegir_storage import DialogoElegirStorage
from proxlaunch.interfaz.dialogos.guardar_lote import DialogoGuardarLote
from proxlaunch.interfaz.dialogos.guardar_perfil import DialogoGuardarPerfil
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.dialogos.huella import DialogoHuella
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv, leer_e_interpretar
from proxlaunch.interfaz.dialogos.importar_perfiles import DialogoImportarPerfiles
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.dialogos.pausa_lote import DialogoPausaLote
from proxlaunch.interfaz.dialogos.perfiles_maquina import DialogoPerfilesMaquina, _DialogoExportar
from proxlaunch.interfaz.dialogos.plantilla_imagen import DialogoPlantillaImagen
from proxlaunch.interfaz.dialogos.transferencia import DialogoDescarga, DialogoSubida
from proxlaunch.interfaz.dialogos.transferencias_sesion import DialogoTransferenciasSesion
from proxlaunch.interfaz.tema import ModoTema
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.interfaz.ventana_principal import VentanaPrincipal
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, ProgresoLote
from proxlaunch.nucleo.agente.modelos import EstadoIp, ResultadoIp
from proxlaunch.nucleo.api.cliente import MetadatosUrl
from proxlaunch.nucleo.cloudinit.modelos import (
    ConfigCloudInit,
    InfoCloudInitPlantilla,
    ModoTarjeta,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.csv_importacion.modelos import OpcionesCsv
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    CandidatoRollback,
    MetadatosInforme,
    MotivoPausa,
)
from proxlaunch.nucleo.lote.modelos import EstadoMV as EM
from proxlaunch.nucleo.lote.rollback import InspeccionRollback
from proxlaunch.nucleo.modelos.catalogo import (
    CatalogoServidor,
    Contenido,
    ListadoStorage,
    PermisosEfectivos,
)
from proxlaunch.nucleo.modelos.origen import ModoClon, TipoSO
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    Bus,
    Disco,
    Firmware,
    InterfazRed,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.opciones.modelos import EstadoPools, PoliticaEtiquetas, PoolsServidor
from proxlaunch.nucleo.origen.capacidades_origen import Via
from proxlaunch.nucleo.perfiles_maquina.aplicar import config_desde_configuracion
from proxlaunch.nucleo.perfiles_maquina.formato import leer_perfiles, perfiles_a_bytes
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO
from proxlaunch.nucleo.persistencia.preferencias import Modo
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.servicios.conexion import DesafioTFA, EstadoHuella
from proxlaunch.nucleo.transferencias.archivo_local import DESPLAZAMIENTO_ISO9660
from proxlaunch.nucleo.transferencias.modelos import (
    EstadoTransferencia,
    RegistroTransferencia,
    TipoTransferencia,
)
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion

from ..apoyo import (
    GIB,
    ClienteLoteFalso,
    CreacionPorVmid,
    _VistaSoloLectura,
    info_huella,
    perfil,
    resultado,
    sesion_falsa,
    upid_de,
)
from ..apoyo_fase_a import inventario_con, permisos_fase_a
from ..apoyo_fase_b import entrada_ip
from ..apoyo_lote import entrada, informe_de, upid_con_usuario
from ..apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from ..apoyo_mvp3 import definicion_homogenea, escribir_lote_guardado, importar_csv_por_menu
from ..apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from ..apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from ..apoyo_mvp4 import (
    ROL_10,
    ROL_14,
    ControladorFalso,
    ServicioTransferenciasFalso,
    caps_origen,
    cfg_clon,
    cfg_import,
    cfg_iso,
    comprobacion,
    detalle_plantilla,
    plantilla_pve,
)
from ..apoyo_ventana_lote import (
    crear_lote,
    escribir,
    esperar_fin,
    preparar_lote,
    ver_resumen,
)
from ..test_fase_b_plantilla_imagen import ClienteB2, FabricaCreacionFalsa
from ..test_lote_progreso import plan_vacio
from ..test_mvp3_textos_accesibilidad import almacen_en, perfiles_de_fabrica
from ..test_mvp4_ventana import preguntas as preguntas  # noqa: F401  (fixture)
from ..test_ventana_principal import conectar, esperar_validacion, poner_nombre
from ..test_ventana_principal import entorno as entorno  # noqa: F401  (fixture)
from .conftest import guardar_imagen
from .escenario import (
    CLAVE_SSH_FALSA,
    CSV_CLOUDINIT,
    CSV_CON_ERRORES,
    CSV_MIXTAS,
    HOST,
    TOKEN,
    UPID,
    USUARIO,
    VOLID_DEBIAN_QCOW2,
    VOLID_UBUNTU,
    VOLID_VIRTIO,
    VOLID_WINDOWS,
    CreacionConSecuenciaCompleta,
    configuracion_guia,
    escribir_csv_guia,
    imagenes_import,
    inventario_guia_cluster,
    inventario_guia_individual,
    plantillas_del_escenario,
    volumenes_iso,
)

pytestmark = pytest.mark.capturas

# La pregunta «¿Guardar el lote?» real: la fixture común de las pruebas la sustituye al empezar.
_PREGUNTA_REAL = VentanaPrincipal._preguntar_guardar_cambios

ANCHO_VENTANA, ALTO_VENTANA = 1240, 820
PERFIL = ("p1", "Oficina", (HOST,))


# --- Ayudantes -----------------------------------------------------------------------------


def preparar(qtbot, v, alto=ALTO_VENTANA, ancho=ANCHO_VENTANA):
    """Tamaño de la guía para la ventana principal, sin la esquina de redimensionar.

    Con ``alto`` mayor que el de la pantalla virtual se levanta el límite de ``AjusteDesplazable``
    para enseñar el formulario entero (en la aplicación real se desplaza con una barra).
    """
    v.statusBar().setSizeGripEnabled(False)
    if alto > ALTO_VENTANA:
        v.ajuste_pantalla.alto_disponible = alto + 200
        v.ajuste_pantalla.reajustar()
    v.resize(ancho, alto)
    v.show()
    qtbot.waitExposed(v)


def conectado(qtbot, entorno, inv, alto=ALTO_VENTANA, ancho=ANCHO_VENTANA, **kw):
    """Conecta la ventana con el escenario ficticio y la deja con el tamaño de la guía."""
    entorno.inv = inv
    conectar(qtbot, entorno, sesion_falsa(perfil(*PERFIL), **kw))
    preparar(qtbot, entorno.ventana, alto, ancho)
    return entorno.ventana


def mostrar(qtbot, dialogo):
    """Muestra un diálogo con su tamaño natural y espera a que esté dibujado."""
    qtbot.addWidget(dialogo)
    dialogo.show()
    qtbot.waitExposed(dialogo)
    return dialogo


def captura_menu(qapp, qtbot, v, indice, nombre, guardar, *, extra=None):
    """Captura la barra de menús con el menú ``indice`` desplegado (y sus submenús).

    Se compone la imagen con ``grab()`` de la ventana y de cada menú emergente (que es una
    ventana propia) en vez de fotografiar la pantalla: así no entra nada ajeno a la aplicación
    y el resultado es idéntico en cada ejecución.
    """
    v.move(0, 0)
    barra = v.menuBar()
    accion = barra.actions()[indice]
    menu = accion.menu()
    geo = barra.actionGeometry(accion)
    menu.popup(barra.mapToGlobal(geo.bottomLeft()))
    qtbot.waitExposed(menu)
    menus = [menu, *(extra(menu) if extra is not None else [])]
    origen = v.mapToGlobal(QPoint(0, 0))
    derecha = max(m.geometry().right() for m in menus) + 12
    abajo = max(m.geometry().bottom() for m in menus) + 8
    qapp.processEvents()
    lienzo = QPixmap(derecha - origen.x(), abajo - origen.y())
    lienzo.fill(Qt.GlobalColor.white)
    pintor = QPainter(lienzo)
    pintor.drawPixmap(0, 0, v.grab())
    for m in menus:
        pintor.drawPixmap(m.geometry().topLeft() - origen, m.grab())
    pintor.end()
    guardar_imagen(lienzo, nombre)
    for m in reversed(menus):
        m.hide()


# --- 1. Arranque y menús --------------------------------------------------------------------


def test_01_bienvenida(qtbot, entorno, guardar):  # noqa: F811
    preparar(qtbot, entorno.ventana)
    guardar(entorno.ventana, "01-bienvenida")


def test_02_menu_lote(qtbot, qapp, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_cluster())
    captura_menu(qapp, qtbot, v, 1, "02-menu-lote", guardar)


def test_03_menu_ajustes(qtbot, qapp, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_cluster())

    def submenus(menu):
        # Cada submenú se despliega a la derecha del anterior para que no se tapen.
        salida = []
        x = menu.geometry().right() + 1
        for sub in (a.menu() for a in menu.actions() if a.menu() is not None):
            accion = sub.menuAction()
            y = menu.geometry().top() + menu.actionGeometry(accion).top()
            sub.popup(QPoint(x, y))
            x = sub.geometry().right() + 4
            salida.append(sub)
        return salida

    captura_menu(qapp, qtbot, v, 3, "03-menu-ajustes", guardar, extra=submenus)


# --- 2. Conexión ------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _lecturas_del_servidor(monkeypatch):
    """El catálogo que «lee» la aplicación es el del escenario (ISOs, imágenes y plantillas)."""

    def leer(sesion, reloj, inv, nodo, contenido):
        vols = volumenes_iso() if contenido == Contenido.ISO else imagenes_import()
        return (ListadoStorage(nodo, "local", contenido, tuple(vols)),)

    def plantillas(sesion, reloj):
        return (
            plantilla_pve(9000, "plantilla-debian12", "pve1"),
            plantilla_pve(9001, "plantilla-ubuntu", "pve1"),
        )

    def catalogo_para(sesion, reloj, inv, necesidades, nodos):
        listados = tuple(
            ListadoStorage(
                nodo,
                "local",
                contenido,
                tuple(volumenes_iso() if contenido == Contenido.ISO else imagenes_import()),
            )
            for contenido in sorted(necesidades.contenidos, key=lambda c: c.value)
            for nodo in sorted(nodos)
        )
        permisos = inv.catalogo.permisos if inv.catalogo is not None else None
        return CatalogoServidor(
            permisos=permisos,
            listados=listados,
            plantillas=plantillas(sesion, reloj) if necesidades.plantillas else None,
            # Los pools y la política de etiquetas son los del inventario (los lee el servidor
            # falso): sin esto el lote avisaría de lecturas fallidas que en la guía no ocurren.
            pools=inv.catalogo.pools if inv.catalogo is not None else PoolsServidor(),
            politica_etiquetas=(
                inv.catalogo.politica_etiquetas if inv.catalogo is not None else None
            ),
            politica_etiquetas_fallida=False,
        )

    monkeypatch.setattr(controlador_origen, "leer_catalogo_para", catalogo_para)
    monkeypatch.setattr(controlador_origen, "leer_listados", leer)
    monkeypatch.setattr(controlador_origen, "leer_plantillas", plantillas)


@pytest.fixture
def lanzador(qtbot):
    lz = Lanzador()
    yield lz
    lz.esperar(2000)


@pytest.fixture
def conexion(deps, lanzador):
    """Fábrica del diálogo de conexión con servicios y repositorios falsos."""

    def _crear(avanzado=False, **kw):
        return DialogoConexion(
            deps.servicio_conexion,
            deps.perfiles,
            deps.huellas,
            deps.secretos,
            lanzador,
            avanzado=avanzado,
            **kw,
        )

    return _crear


def test_04_conexion_token(qtbot, conexion, guardar):
    d = conexion()
    d.nombre.setText("Oficina")
    d.hosts.setPlainText(HOST)
    d.token.setText(TOKEN)
    guardar(mostrar(qtbot, d), "04-conexion-token")


def test_05_conexion_contrasena_root(qtbot, conexion, guardar):
    d = conexion()
    d.nombre.setText("Oficina")
    d.hosts.setPlainText(HOST)
    d.radio_clave.setChecked(True)
    d.usuario.setText("root")
    d.contrasena.setText("contrasena-ficticia")
    guardar(mostrar(qtbot, d), "05-conexion-contrasena-root")


def test_06_conexion_avanzado(qtbot, deps, conexion, guardar):
    deps.perfiles.guardar(
        perfil("p1", "Oficina", (HOST,), storage_mv="local-lvm", storage_iso="local")
    )
    d = conexion(
        True,
        perfil_id="p1",
        candidatos_storage={
            Contenido.IMAGENES: ("local-lvm", "datos"),
            Contenido.ISO: ("local",),
            Contenido.IMPORT: ("local",),
        },
    )
    d.chk_ignorar.setChecked(True)
    guardar(mostrar(qtbot, d), "06-conexion-avanzado")


def test_07_conexion_validacion(qtbot, deps, conexion, guardar):
    deps.perfiles.guardar(perfil("p1", "Oficina", (HOST,)))
    d = conexion()
    d.combo_perfiles.setCurrentIndex(0)  # «(Perfil nuevo)»
    d.nombre.setText("Oficina")
    d.hosts.setPlainText("host con espacios")
    d.token.setText("abc")
    d.token.textEdited.emit("abc")
    mostrar(qtbot, d)
    d.btn_conectar.click()
    # Los avisos aparecen con la ventana ya abierta: se agranda hasta que no haga falta desplazar.
    d.resize(d.width(), 665)
    guardar(d, "07-conexion-validacion")


def test_08_huella_primera_vez(qtbot, guardar):
    d = mostrar(qtbot, DialogoHuella(info_huella(EstadoHuella.NUEVA, host=HOST), avanzado=False))
    guardar(d, "08-huella-primera-vez")


def test_09_huella_cambiada(qtbot, guardar):
    d = mostrar(qtbot, DialogoHuella(info_huella(EstadoHuella.CAMBIADA, host=HOST), avanzado=True))
    guardar(d, "09-huella-cambiada")


def test_10_2fa_codigo(qtbot, guardar):
    d = mostrar(qtbot, DialogoDosFactores(DesafioTFA("ana@pve", "ticket", True, True)))
    d._campo.setText("123456")
    guardar(d, "10-2fa-codigo")


def test_11_guia_token(qtbot, guardar):
    d = mostrar(qtbot, DialogoGuiaToken())
    d.resize(d.width(), 1020)  # con holgura se ve la guía entera sin desplazar
    qtbot.wait(100)
    guardar(d, "11-guia-token")


def test_12_acerca_de(qtbot, guardar):
    d = mostrar(qtbot, DialogoAcercaDe("claro"))
    guardar(d, "12-acerca-de")


# --- 3. Ventana de trabajo básica ----------------------------------------------------------


def test_13_trabajo_individual_basico(qtbot, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_individual(), 1400)
    poner_nombre(qtbot, v, "srv-web-01")
    guardar(v, "13-trabajo-individual-basico")


def test_14_trabajo_cluster_nodo(qtbot, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_cluster(), 1500)
    poner_nombre(qtbot, v, "srv-web-01")
    guardar(v, "14-trabajo-cluster-nodo")


def test_15_nodo_caido_reintentar(qtbot, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_cluster(pve3_caido=True), 1000)
    v.formulario._radio_manual.setChecked(True)
    poner_nombre(qtbot, v, "srv-web-01")
    guardar(v, "15-nodo-caido-reintentar")


def test_16_formulario_errores(qtbot, entorno, guardar):  # noqa: F811
    entorno.vmid_ocupados[150] = "151"
    v = conectado(qtbot, entorno, inventario_guia_cluster(), 1500)
    poner_nombre(qtbot, v, "Srv_web")
    f = v.formulario
    f.vmid.setText("150")
    f.vmid.textEdited.emit("150")
    f.vmid.editingFinished.emit()
    qtbot.waitUntil(lambda: f.fila_vmid.hay_error, timeout=3000)
    f.memoria.setText("abc")
    f.memoria.textEdited.emit("abc")
    esperar_validacion(qtbot, v)
    guardar(v, "16-formulario-errores")


def _crear_con(qtbot, entorno, resultado_final, ancho=ANCHO_VENTANA):
    """Clúster conectado y nombre válido, con una creación que espera a que se la libere.

    Así la barra de etapas se dibuja como en un uso real (el servicio falso termina al instante
    y la ventana solo llegaría a ver la primera etapa).
    """
    puerta = threading.Event()
    creacion = CreacionConSecuenciaCompleta({101: resultado_final}, {101: puerta})
    entorno.creacion = creacion
    v = conectado(qtbot, entorno, inventario_guia_cluster(), 1000, ancho)
    poner_nombre(qtbot, v, "srv-web-01")
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)
    qtbot.wait(300)
    return v, puerta


def _terminar(qtbot, v, puerta):
    puerta.set()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    qtbot.wait(300)


def _resultado(desenlace=Desenlace.OK, **kw):
    return resultado(desenlace, upid=UPID, vmid=101, nodo="pve1", **kw)


def test_17_progreso_en_curso(qtbot, entorno, guardar):  # noqa: F811
    v, puerta = _crear_con(qtbot, entorno, _resultado())
    try:
        guardar(v, "17-progreso-en-curso")
    finally:
        _terminar(qtbot, v, puerta)


def test_18_progreso_ok(qtbot, entorno, guardar):  # noqa: F811
    v, puerta = _crear_con(qtbot, entorno, _resultado())
    _terminar(qtbot, v, puerta)
    guardar(v, "18-progreso-ok")


def test_19_progreso_error_detalles(qtbot, entorno, guardar):  # noqa: F811
    error = ErrorProxLaunch(
        CodigoError.SIN_ESPACIO,
        {"storage": "local-lvm"},
        "storage 'local-lvm' has not enough free space",
    )
    res = _resultado(Desenlace.ERROR, error=error, log=["TASK ERROR: no hay espacio libre"])
    v, puerta = _crear_con(qtbot, entorno, res)
    _terminar(qtbot, v, puerta)
    detalles = v.progreso.detalles
    if not detalles._texto.isVisible():
        detalles._boton.click()
    guardar(v, "19-progreso-error-detalles")


def test_20_progreso_tiempo_agotado(qtbot, entorno, guardar):  # noqa: F811
    v, puerta = _crear_con(qtbot, entorno, _resultado(Desenlace.TIEMPO_AGOTADO))
    _terminar(qtbot, v, puerta)
    guardar(v, "20-progreso-tiempo-agotado")


# --- 4. Modo avanzado ------------------------------------------------------------------------


def test_21_avanzado_formulario(qtbot, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_individual(), 1750)
    v.establecer_modo(Modo.AVANZADO)
    cfg = configuracion_guia(
        nodo="pve",
        firmware=Firmware.OVMF,
        tpm=True,
        agente_qemu=True,
        sockets=2,
        cores=4,
        tipo_cpu="x86-64-v3",
        memoria_mib=8192,
        ballooning=Ballooning(True, 2048),
    )
    v.formulario.aplicar_configuracion(cfg)
    poner_nombre(qtbot, v, "srv-web-01")
    qtbot.wait(300)  # la fila «Esperar la IP» cambia el alto: se espera a que se acomode
    guardar(v, "21-avanzado-formulario")


def test_22_avanzado_discos(qtbot, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_individual(), 1900)
    v.establecer_modo(Modo.AVANZADO)
    cfg = configuracion_guia(
        nodo="pve",
        discos=[
            Disco("local-lvm", 32, Bus.VIRTIO, ssd=False),
            Disco("datos", 100, Bus.SATA, iothread=False),
        ],
    )
    v.formulario.aplicar_configuracion(cfg)
    qtbot.wait(50)
    guardar(v.formulario.tabla_discos, "22-avanzado-discos")


def test_23_avanzado_red(qtbot, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_individual(), 1900)
    v.establecer_modo(Modo.AVANZADO)
    v.formulario.aplicar_configuracion(configuracion_guia(nodo="pve"))
    qtbot.wait(50)
    guardar(v.formulario.tabla_redes, "23-avanzado-red")


def test_24_tema_oscuro(qtbot, entorno, deps, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, inventario_guia_individual(), 1400)
    poner_nombre(qtbot, v, "srv-web-01")
    v.establecer_tema(ModoTema.OSCURO)
    qtbot.wait(50)
    try:
        guardar(v, "24-tema-oscuro")
    finally:
        v.establecer_tema(ModoTema.CLARO)


# --- 5. Origen del sistema operativo ----------------------------------------------------------


def _con_origen(qtbot, entorno, inv, alto=1500, ancho=ANCHO_VENTANA):
    v = conectado(qtbot, entorno, inv, alto, ancho)
    poner_nombre(qtbot, v, "srv-web-01")
    return v


def _grupo(widget):
    """El cuadro con título («Origen del sistema») que contiene al selector."""
    while widget is not None and not isinstance(widget, QGroupBox):
        widget = widget.parentWidget()
    return widget


def _marcar(v, origen):
    v.formulario.selector_origen.opciones[origen].setChecked(True)


def test_25_origen_selector_capacidades(qtbot, entorno, preguntas, guardar):  # noqa: F811
    v = _con_origen(qtbot, entorno, inventario_guia_individual(ROL_10))
    sel = v.formulario.selector_origen
    # Las plantillas se leen al elegir «Copiar una plantilla»; con ellas se ve que falta VM.Clone
    # y el origen vuelve solo a «Vacía».
    _marcar(v, OrigenSO.CLONAR_PLANTILLA)
    qtbot.waitUntil(lambda: not sel.opciones[OrigenSO.CLONAR_PLANTILLA].isEnabled(), timeout=4000)
    qtbot.wait(100)
    guardar(_grupo(sel), "25-origen-selector-capacidades")


def test_26_origen_iso_linux(qtbot, entorno, preguntas, guardar):  # noqa: F811
    v = _con_origen(qtbot, entorno, inventario_guia_individual())
    sel = v.formulario.selector_origen
    _marcar(v, OrigenSO.ISO)
    sel.aplicar(cfg_iso(VOLID_UBUNTU, None, nodo="pve"))
    sel.combo_so.setCurrentIndex(sel.combo_so.findData(TipoSO.LINUX.value))
    qtbot.wait(100)
    guardar(_grupo(sel), "26-origen-iso-linux")


def test_27_origen_iso_windows_drivers(qtbot, entorno, preguntas, guardar):  # noqa: F811
    v = _con_origen(qtbot, entorno, inventario_guia_individual())
    v.establecer_modo(Modo.AVANZADO)
    sel = v.formulario.selector_origen
    _marcar(v, OrigenSO.ISO)
    sel.aplicar(cfg_iso(VOLID_WINDOWS, None, drivers=VOLID_VIRTIO, nodo="pve"))
    sel.combo_so.setCurrentIndex(sel.combo_so.findData(TipoSO.WINDOWS_11.value))
    qtbot.wait(200)
    guardar(_grupo(sel), "27-origen-iso-windows-drivers")


def test_28_origen_importar(qtbot, entorno, preguntas, guardar):  # noqa: F811
    v = _con_origen(qtbot, entorno, inventario_guia_individual())
    sel = v.formulario.selector_origen
    _marcar(v, OrigenSO.IMPORTAR_DISCO)
    sel.aplicar(cfg_import(VOLID_DEBIAN_QCOW2, nodo="pve"))
    sel.spin_ampliar.setValue(60)
    qtbot.wait(100)
    guardar(_grupo(sel), "28-origen-importar")


def test_29_origen_clonar_basico(qtbot, entorno, preguntas, guardar):  # noqa: F811
    v = _con_origen(qtbot, entorno, inventario_guia_individual())
    sel = v.formulario.selector_origen
    _marcar(v, OrigenSO.CLONAR_PLANTILLA)
    sel.aplicar(cfg_clon("plantilla-debian12", 9000, nodo="pve"))
    sel.establecer_detalle_plantilla(detalle_plantilla(2, 2048))
    qtbot.wait(100)
    guardar(_grupo(sel), "29-origen-clonar-basico")


def test_30_origen_clonar_avanzado(qtbot, entorno, preguntas, guardar):  # noqa: F811
    v = _con_origen(qtbot, entorno, inventario_guia_individual())
    v.establecer_modo(Modo.AVANZADO)
    sel = v.formulario.selector_origen
    _marcar(v, OrigenSO.CLONAR_PLANTILLA)
    sel.establecer_storages_destino(["local-lvm", "datos"])
    sel.aplicar(cfg_clon("plantilla-debian12", 9000, modo=ModoClon.COMPLETO, nodo="pve"))
    sel.establecer_detalle_plantilla(detalle_plantilla(2, 2048))
    qtbot.wait(100)
    guardar(_grupo(sel), "30-origen-clonar-avanzado")


# --- 6. Catálogos y transferencias --------------------------------------------------------------


@pytest.fixture
def servidor(qtbot):
    """Controlador de transferencias falso sobre el servidor individual de la guía."""
    return ControladorFalso(inventario_guia_individual())


def _catalogo_iso(qtbot):
    caps = caps_origen(inventario_guia_individual())
    d = DialogoCatalogo(
        FuenteCatalogo.ISO,
        estado_subir=caps.estado(Via.SUBIR_ISO),
        estado_descargar=caps.estado(Via.DESCARGAR_URL),
        tema="claro",
    )
    d.establecer_volumenes(volumenes_iso(), nodo="pve")
    return d


def test_31_catalogo_iso(qtbot, guardar):
    d = mostrar(qtbot, _catalogo_iso(qtbot))
    guardar(d, "31-catalogo-iso")


def test_32_catalogo_plantillas(qtbot, guardar):
    d = DialogoCatalogo(FuenteCatalogo.PLANTILLA, tema="claro")
    base = tuple(p for p in ROL_14 if p != "VM.Clone")
    # Solo la plantilla 9000 tiene VM.Clone concedido: la otra se ve, pero no se puede elegir.
    permisos_guia = PermisosEfectivos(
        rutas={"/": {p: 1 for p in base}, "/vms/9000": {"VM.Clone": 1}}
    )
    d.establecer_plantillas(
        [
            plantilla_pve(9000, "plantilla-debian12"),
            plantilla_pve(9001, "plantilla-ubuntu"),
        ],
        permisos_guia,
    )
    guardar(mostrar(qtbot, d), "32-catalogo-plantillas")


def _iso_ficticio(tmp_path, nombre="ubuntu-24.04-server.iso", tamano=int(2.6 * GIB)):
    """Archivo disperso (no ocupa disco) con el tamaño del ISO de ejemplo."""
    ruta = tmp_path / nombre
    with ruta.open("wb") as f:
        f.seek(DESPLAZAMIENTO_ISO9660)
        f.write(
            b"CD001"
        )  # firma de un ISO 9660 real, para que no salga el aviso de «no parece ISO»
        f.truncate(tamano)
    return ruta


def _esperar_listo(qtbot, d):
    qtbot.waitUntil(lambda: d.boton_accion.isEnabled(), timeout=5000)
    qtbot.wait(100)


def test_33_subida_iso_lista(qtbot, servidor, tmp_path, guardar):
    d = mostrar(qtbot, DialogoSubida(servidor, Contenido.ISO, "pve", ruta=_iso_ficticio(tmp_path)))
    _esperar_listo(qtbot, d)
    guardar(d, "33-subida-iso-lista")


def test_34_subida_ya_existe(qtbot, tmp_path, guardar):
    servidor = ControladorFalso(
        inventario_guia_individual(),
        ServicioTransferenciasFalso(comprobacion=comprobacion(existente=VOLID_UBUNTU)),
    )
    d = mostrar(qtbot, DialogoSubida(servidor, Contenido.ISO, "pve", ruta=_iso_ficticio(tmp_path)))
    qtbot.waitUntil(lambda: d.fila_existente.isVisible(), timeout=5000)
    qtbot.wait(100)
    guardar(d, "34-subida-ya-existe")


def test_35_descarga_url(qtbot, servidor, guardar):
    servidor.modo_avanzado = True
    servidor.servicio_transferencias.metadatos = MetadatosUrl("debian-12.iso", 628 * 1024**2, None)
    d = mostrar(qtbot, DialogoDescarga(servidor, Contenido.ISO, "pve"))
    d.campo_url.setText("https://deb.example.com/debian-12.iso")
    d.comprobar_url()
    qtbot.wait(300)
    guardar(d, "35-descarga-url")


def test_36_elegir_storage(qtbot, guardar):
    inv = inventario_guia_individual()
    d = mostrar(qtbot, DialogoElegirStorage(Contenido.IMAGENES, inv.storages["pve"]))
    guardar(d, "36-elegir-storage")


def test_37_capacidades_servidor(qtbot, guardar):
    caps = caps_origen(inventario_guia_individual(ROL_10))
    d = mostrar(qtbot, DialogoCapacidades(caps, tema="claro"))
    d.resize(1000, 880)  # con holgura se ven las nueve vías sin desplazar la tabla
    qtbot.wait(100)
    guardar(d, "37-capacidades-servidor")


def test_38_archivos_subidos_sesion(qtbot, guardar):
    registro = RegistroSesion()
    for hora, tipo, nombre, tamano in (
        ("10:42", TipoTransferencia.SUBIDA, "ubuntu-24.04-server.iso", int(2.6 * GIB)),
        ("11:05", TipoTransferencia.DESCARGA, "debian-12.iso", int(0.6 * GIB)),
    ):
        registro.agregar(
            RegistroTransferencia(
                tipo,
                nombre,
                "local",
                "pve",
                tamano,
                hora,
                EstadoTransferencia.TERMINADA,
                f"local:iso/{nombre}",
            )
        )
    guardar(mostrar(qtbot, DialogoTransferenciasSesion(registro)), "38-archivos-subidos-sesion")


# --- 7. Perfiles de máquina ---------------------------------------------------------------------


@pytest.fixture
def ventana3(qtbot, entorno3):
    """Ventana conectada al clúster de la guía, con diálogos y archivos controlados."""
    return conectado(qtbot, entorno3, inventario_guia_cluster(), 1400)


def _elegir_perfil(v, id_perfil):
    combo = v.selector_perfil.combo
    indice = combo.findData(id_perfil)
    combo.setCurrentIndex(indice)
    combo.activated.emit(indice)


def _perfil_de_usuario(v, nombre, descripcion="", **cambios):
    """Perfil propio con el hardware del formulario (más ``cambios`` sobre su configuración)."""
    config = config_desde_configuracion(v.formulario.configuracion(), con_pistas=True)
    perfil = v._almacen_perfiles.crear(nombre, descripcion, replace(config, **cambios))
    v._recargar_selector(perfil.id)
    return perfil


def test_39_selector_perfil(qtbot, ventana3, guardar):
    v = ventana3
    _elegir_perfil(v, "fabrica.servidor-mediano")
    qtbot.wait(100)
    guardar(v.selector_perfil, "39-selector-perfil")


def test_40_selector_perfil_modificado(qtbot, ventana3, guardar):
    v = ventana3
    base = config_desde_configuracion(v.formulario.configuracion(), con_pistas=True)
    pista_mala = replace(base.discos[0], storage_preferido="almacen-viejo")
    perfil = v._almacen_perfiles.crear(
        "Servidor web de la oficina",
        "Servidor web con 4 núcleos y 4 GiB.",
        replace(base, cores=4, memoria_mib=4096, discos=(pista_mala,)),
    )
    v._recargar_selector(None)
    _elegir_perfil(v, perfil.id)
    escribir(v.formulario.cores, "6")
    escribir(v.formulario.memoria, "abc")
    esperar_validacion(qtbot, v)
    qtbot.wait(100)
    guardar(v.selector_perfil, "40-selector-perfil-modificado")


def _almacen(tmp_path):
    """Almacén de perfiles en la carpeta temporal, con un perfil propio de ejemplo."""
    almacen = almacen_en(tmp_path)
    cfg = configuracion_guia(nodo="pve")
    config = config_desde_configuracion(cfg, con_pistas=False)
    almacen.crear(
        "Servidor web de la oficina",
        "Servidor web con 4 núcleos, 4 GiB y 32 GiB de disco.",
        replace(config, cores=4, memoria_mib=4096, discos=config.discos[:1]),
    )
    return almacen


def test_41_guardar_perfil(qtbot, tmp_path, guardar):
    cfg = configuracion_guia(nodo="pve", firmware=Firmware.OVMF, cores=4, memoria_mib=4096)
    d = DialogoGuardarPerfil(
        almacen_en(tmp_path), cfg, avanzado=True, nombre_sugerido="Servidor web"
    )
    guardar(mostrar(qtbot, d), "41-guardar-perfil")


def test_42_administrar_perfiles(qtbot, tmp_path, lanzador, guardar):
    almacen = _almacen(tmp_path)
    d = DialogoPerfilesMaquina(almacen, lanzador, app_version="0.5.0", tema="claro")
    mostrar(qtbot, d)
    d.tabla.selectRow(len(almacen.todos()) - 1)
    qtbot.wait(100)
    guardar(d, "42-administrar-perfiles")


def test_43_exportar_perfiles(qtbot, tmp_path, guardar):
    almacen = _almacen(tmp_path)
    d = _DialogoExportar([almacen.todos()[-1]])
    guardar(mostrar(qtbot, d), "43-exportar-perfiles")


def test_44_importar_perfiles(qtbot, tmp_path, guardar):
    almacen = _almacen(tmp_path)
    propio = almacen.todos()[-1]
    otros = [
        replace(propio, nombre="Servidor de bases de datos"),
        propio,  # mismo nombre que el que ya existe: conflicto
        replace(propio, nombre="Servidor de pruebas"),
    ]
    datos = json.loads(perfiles_a_bytes(otros, con_pistas=False, app_version="0.5.0"))
    datos["perfiles"][2]["config"]["cores"] = 9999  # fuera de rango: no válido
    archivo = leer_perfiles(json.dumps(datos).encode("utf-8"))
    d = DialogoImportarPerfiles(archivo, almacen.todos(), tema="claro")
    mostrar(qtbot, d)
    d.tabla.selectRow(1)
    qtbot.wait(100)
    guardar(d, "44-importar-perfiles")


# --- 8. Lotes -----------------------------------------------------------------------------------


def _lote(
    qtbot, entorno, inv, *, cantidad=5, avanzado=False, nodo="pve1", alto=1500, ancho=1240, **kw
):
    """Ventana con el lote escrito en el bloque «Lote» (cliente de Proxmox falso)."""
    entorno.inv = inv
    cliente = preparar_lote(
        qtbot,
        entorno,
        cantidad=cantidad,
        prefijo="srv-web",
        nodo=nodo,
        avanzado=avanzado,
        perfil_=perfil(*PERFIL),
        **kw,
    )
    v = entorno.ventana
    preparar(qtbot, v, alto, ancho)
    return v, cliente


def test_45_lote_bloque_basico(qtbot, entorno, guardar):  # noqa: F811
    v, _ = _lote(qtbot, entorno, inventario_guia_cluster(), nodo=None)
    guardar(v.bloque_lote, "45-lote-bloque-basico")


def test_46_lote_bloque_avanzado_cluster(qtbot, entorno, guardar):  # noqa: F811
    v, _ = _lote(qtbot, entorno, inventario_guia_cluster(), avanzado=True, nodo=None)
    v.bloque_lote._radio_elegidos.setChecked(True)
    qtbot.wait(100)
    guardar(v.bloque_lote, "46-lote-bloque-avanzado-cluster")


def test_47_lote_resumen(qtbot, entorno, guardar):  # noqa: F811
    v, _ = _lote(qtbot, entorno, inventario_guia_cluster(), nodo=None, alto=640, ancho=1900)
    ver_resumen(qtbot, v)
    qtbot.wait(100)
    guardar(v.resumen_lote, "47-lote-resumen")


def test_48_lote_resumen_no_caben(qtbot, entorno, guardar):  # noqa: F811
    # 40 máquinas de 32 GiB en un solo servidor superan el espacio libre de «datos».
    v, _ = _lote(
        qtbot, entorno, inventario_guia_individual(), cantidad=40, nodo=None, alto=640, ancho=1900
    )
    ver_resumen(qtbot, v)
    guardar(v.resumen_lote, "48-lote-resumen-no-caben")


def test_49_lote_simulacion(qtbot, entorno, guardar):  # noqa: F811
    v, _ = _lote(qtbot, entorno, inventario_guia_cluster(), nodo=None, alto=1000, ancho=1900)
    ver_resumen(qtbot, v)
    r = v.resumen_lote
    r.boton_simular.click()
    qtbot.waitUntil(lambda: r.es_simulacion and not v._planificando, timeout=4000)
    if not r.detalles_peticiones._texto.isVisible():
        r.detalles_peticiones._boton.click()
    qtbot.wait(100)
    guardar(r, "49-lote-simulacion")


def _plan_de(v):
    return v.resumen_lote.plan


def _lote_en_marcha(qtbot, entorno, resultados, gated):
    """Clúster con 12 máquinas: ``resultados`` fija desenlaces y ``gated`` retiene algunas."""
    creacion = CreacionPorVmid()
    v, cliente = _lote(
        qtbot,
        entorno,
        inventario_guia_cluster(),
        cantidad=12,
        nodo=None,
        alto=900,
        ancho=1500,
        creacion=creacion,
    )
    ver_resumen(qtbot, v)
    elementos = _plan_de(v).elementos
    for posicion, res in resultados.items():
        e = elementos[posicion]
        creacion.por_vmid[e.vmid] = res(e)
    puertas = {}
    for posicion in gated:
        puertas[elementos[posicion].vmid] = threading.Event()
    creacion.puertas.update(puertas)
    crear_lote(qtbot, v)
    return v, creacion, puertas


def _fallo(codigo, **params):
    """Desenlace «error» de la tarea (con su UPID del usuario ficticio) para una máquina."""

    def _res(e):
        error = ErrorProxLaunch(codigo, dict(params), "detalle original del servidor")
        return resultado(
            Desenlace.ERROR,
            error=error,
            upid=upid_de(e.vmid, e.nodo, USUARIO),
            vmid=e.vmid,
            nodo=e.nodo,
        )

    return _res


def _dudosa(e):
    """La tarea siguió en marcha y no se pudo confirmar el resultado a tiempo (queda «dudosa»)."""
    return resultado(
        Desenlace.TIEMPO_AGOTADO,
        upid=upid_de(e.vmid, e.nodo, USUARIO),
        vmid=e.vmid,
        nodo=e.nodo,
    )


def test_50_lote_progreso_en_curso(qtbot, entorno, limpieza, guardar):  # noqa: F811
    v, creacion, puertas = _lote_en_marcha(
        qtbot, entorno, {3: _fallo(CodigoError.SIN_ESPACIO, storage="datos")}, (6, 7)
    )
    for vmid in puertas:
        qtbot.waitUntil(lambda vmid=vmid: creacion.entro(vmid).is_set(), timeout=5000)
    qtbot.wait(400)
    guardar(v.progreso_lote, "50-lote-progreso-en-curso")


def test_52_lote_progreso_terminado(qtbot, entorno, limpieza, guardar):  # noqa: F811
    v, creacion, _ = _lote_en_marcha(
        qtbot, entorno, {3: _fallo(CodigoError.SIN_ESPACIO, storage="datos"), 7: _dudosa}, ()
    )
    esperar_fin(qtbot, v)
    qtbot.wait(400)
    guardar(v.progreso_lote, "52-lote-progreso-terminado")


def _entradas_srv(estados):
    """Entradas del libro con los nombres y nodos del escenario (UPID del usuario ficticio)."""
    return tuple(
        entrada(
            i,
            estado,
            nombre=f"srv-web-{i + 1:02d}",
            nodo=("pve1", "pve2")[i % 2],
            upid=upid_con_usuario(101 + i),
        )
        for i, estado in enumerate(estados)
    )


def test_51_lote_pausa(qtbot, guardar):
    d = DialogoPausaLote(MotivoPausa.ERROR_GLOBAL, ErrorProxLaunch(CodigoError.ETIQUETA_RECHAZADA))
    guardar(mostrar(qtbot, d), "51-lote-pausa")


def test_53_lote_deshacer(qtbot, guardar):
    entradas = _entradas_srv([EM.OK, EM.OK, EM.OK, EM.OK, EM.ERROR, EM.NO_ENVIADA])
    candidatos = [CandidatoRollback(e, True, None, False) for e in entradas[:4]]
    candidatos[3] = CandidatoRollback(entradas[3], True, None, True)  # incompleta
    candidatos.append(CandidatoRollback(entradas[4], False, "error", False))
    candidatos.append(CandidatoRollback(entradas[5], False, "no_enviada", False))
    guardar(mostrar(qtbot, DialogoDeshacer(candidatos)), "53-lote-deshacer")


def test_54_lote_informe(qtbot, tmp_path, guardar):
    entradas = _entradas_srv([EM.OK, EM.OK, EM.OK, EM.ERROR, EM.TIEMPO_AGOTADO])
    base = informe_de(entradas, id_lote="a1b2c3d4")
    informe = replace(
        base,
        metadatos=MetadatosInforme(
            nombre_perfil="Oficina",
            version_proxmox="9.2",
            es_cluster=True,
            nombre_cluster="demo",
            fecha_hora_local="2025-03-10T12:00:00+00:00",
        ),
    )
    d = mostrar(qtbot, DialogoInforme(informe, tmp_path))
    d.resize(1100, 560)  # más ancho para ver la tabla entera, incluido el UPID
    qtbot.wait(100)
    guardar(d, "54-lote-informe")


# --- 9. Guardar y abrir lotes, CSV y lote por filas ---------------------------------------------


def test_55_guardar_lote(qtbot, guardar):
    d = DialogoGuardarLote(
        nombre_sugerido="Servidores web de prueba",
        hay_problemas=True,
        archivo_origen="lote-web.proxlaunch-lote.json",
    )
    guardar(mostrar(qtbot, d), "55-guardar-lote")


def _abrir_lote(qtbot, entorno3, archivos, modales, tmp_path, definicion):
    """Abre desde el menú un lote guardado (el diálogo de archivos del sistema se simula)."""
    v = conectado(qtbot, entorno3, inventario_guia_cluster(), 1400)
    ruta = escribir_lote_guardado(tmp_path / "lote-web.proxlaunch-lote.json", definicion, "Web")
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    esperar_validacion(qtbot, v)
    qtbot.wait(200)
    return v


def test_56_lote_no_encaja(qtbot, entorno3, archivos, modales, tmp_path, guardar):
    definicion = definicion_homogenea(5, "srv-web", storage="viejo", nodo="pve9")
    v = _abrir_lote(qtbot, entorno3, archivos, modales, tmp_path, definicion)
    guardar(v.panel_no_encaja, "56-lote-no-encaja")


def _importar_csv(
    qtbot, entorno3, archivos, modales, tmp_path, nombre, texto, alto=820, ancho=1560
):
    v = conectado(qtbot, entorno3, inventario_guia_cluster(), alto, ancho)
    ruta = escribir_csv_guia(tmp_path, nombre, texto)
    importar_csv_por_menu(qtbot, entorno3, modales, archivos, ruta)
    return v


def _dialogo_csv(qtbot, tmp_path, lanzador, nombre, texto, *, avanzado, inv):
    ruta = escribir_csv_guia(tmp_path, nombre, texto)
    perfiles = perfiles_de_fabrica()
    base = next(p for p in perfiles if p.id == ID_PREDETERMINADO)
    tabla, res = leer_e_interpretar(ruta, OpcionesCsv(), base, perfiles, inv, None, None)
    d = DialogoImportarCsv(
        None,
        perfiles=perfiles,
        perfil_base_id=ID_PREDETERMINADO,
        inv=inv,
        nodo_referencia=None,
        lanzador=lanzador,
        avanzado=avanzado,
        tema="claro",
    )
    d.mostrar_resultado(tabla, res, nombre)
    return d


def test_57_csv_vista_previa_ok(qtbot, tmp_path, lanzador, guardar):
    d = _dialogo_csv(
        qtbot,
        tmp_path,
        lanzador,
        "mvs-mixtas.csv",
        CSV_MIXTAS,
        avanzado=False,
        inv=inventario_guia_cluster(),
    )
    mostrar(qtbot, d)
    d.resize(1500, 680)  # más ancho para ver todas las columnas, incluidas Red y Estado
    d.tabla.selectRow(0)
    qtbot.wait(100)
    guardar(d, "57-csv-vista-previa-ok")


def test_58_csv_vista_previa_errores(qtbot, tmp_path, lanzador, guardar):
    d = _dialogo_csv(
        qtbot,
        tmp_path,
        lanzador,
        "mvs-con-errores.csv",
        CSV_CON_ERRORES,
        avanzado=True,
        inv=inventario_guia_cluster(),
    )
    mostrar(qtbot, d)
    d.resize(1500, 680)
    d.casilla_problemas.setChecked(True)
    d.tabla.selectRow(0)
    qtbot.wait(100)
    guardar(d, "58-csv-vista-previa-errores")


def test_59_lote_por_filas(qtbot, entorno3, archivos, modales, tmp_path, guardar):
    v = _importar_csv(qtbot, entorno3, archivos, modales, tmp_path, "mvs-mixtas.csv", CSV_MIXTAS)
    guardar(v, "59-lote-por-filas")


def test_60_cambios_sin_guardar(
    qtbot,
    entorno3,
    archivos,
    modales,
    tmp_path,
    monkeypatch,
    guardar,
):
    v = _importar_csv(qtbot, entorno3, archivos, modales, tmp_path, "mvs-mixtas.csv", CSV_MIXTAS)
    # Se restaura la pregunta real (la fixture común la sustituye por «No guardar»).
    monkeypatch.setattr(VentanaPrincipal, "_preguntar_guardar_cambios", _PREGUNTA_REAL)
    modales.responder(
        QMessageBox, lambda caja: (caja.show(), guardar(caja, "60-cambios-sin-guardar"))
    )
    archivos.abrir.append(None)
    v._accion_abrir_lote.trigger()
    # Se vuelve a «No guardar» para que cerrar la ventana al terminar no pregunte otra vez.
    monkeypatch.setattr(VentanaPrincipal, "_preguntar_guardar_cambios", lambda self: "descartar")


# --- 9. Opciones de la fase A (0.6.0) -------------------------------------------------------

POOLS_GUIA = PoolsServidor(EstadoPools.OK, ("produccion", "pruebas"))


def _inventario_fase_a(
    inv,
    *,
    opcionales=("VM.PowerMgmt", "Pool.Audit", "VM.GuestAgent.Audit", "VM.Monitor"),
    pools=POOLS_GUIA,
):
    """Inventario con los permisos del rol más los opcionales dados y los pools del servidor."""
    inv2 = inventario_con(inv, permisos_fase_a(anadir=opcionales), pools)
    inv2.catalogo = replace(inv2.catalogo, politica_etiquetas=PoliticaEtiquetas(permiso="free"))
    return inv2


def _cfg_opciones(**cambios):
    """Configuración de la guía con todas las opciones de la fase A rellenas (datos ficticios)."""
    base = {
        "nodo": "pve",
        "encender": True,
        "arranque_auto": True,
        "arranque_orden": 2,
        "arranque_espera": 30,
        "notas_origen": True,
        "notas_usuario": True,
        "notas": "Servidor web del equipo de ejemplo",
        "etiquetas_usuario": ("web", "produccion"),
        "pool": "produccion",
        "proteger": True,
        "redes": [
            InterfazRed("vmbr0", ModeloRed.VIRTIO, None, mtu=1500, limite_mb=100.0),
            InterfazRed("vmbr1", ModeloRed.VIRTIO, None, mtu=1, limite_mb=12.5),
        ],
    }
    base.update(cambios)
    return configuracion_guia(**base)


def _formulario_con_opciones(qtbot, entorno, alto, **kw):
    inv = _inventario_fase_a(inventario_guia_individual(), **kw)
    v = conectado(qtbot, entorno, inv, alto)
    esperar_validacion(qtbot, v)
    return v


def test_61_opciones_general(qtbot, entorno, guardar):  # noqa: F811
    v = _formulario_con_opciones(qtbot, entorno, 1900)
    v.formulario.aplicar_configuracion(_cfg_opciones())
    poner_nombre(qtbot, v, "srv-web-01")
    qtbot.wait(100)
    guardar(v, "61-opciones-general")


def test_62_opciones_avanzadas(qtbot, entorno, guardar):  # noqa: F811
    v = _formulario_con_opciones(qtbot, entorno, 2100)
    v.establecer_modo(Modo.AVANZADO)
    v.formulario.aplicar_configuracion(_cfg_opciones())
    poner_nombre(qtbot, v, "srv-web-01")
    qtbot.wait(100)
    guardar(v, "62-opciones-avanzadas")


def test_63_opciones_deshabilitadas(qtbot, entorno, guardar):  # noqa: F811
    v = _formulario_con_opciones(
        qtbot, entorno, 1900, opcionales=(), pools=PoolsServidor(EstadoPools.SIN_PERMISO)
    )
    poner_nombre(qtbot, v, "srv-web-01")
    qtbot.wait(100)
    guardar(v, "63-opciones-deshabilitadas")


class _VistaGuiaSoloLectura(_VistaSoloLectura):
    """Vista de solo lectura que deja pasar también las dos lecturas de la fase A."""

    _LECTURAS = _VistaSoloLectura._LECTURAS | {
        "pools",
        "opciones_cluster",
        "plantillas_visibles",
        "storages",
        "contenido_storage",
    }


class ClienteGuiaFalso(ClienteLoteFalso):
    """Cliente falso que, además, sirve los pools y la política de etiquetas del servidor.

    También las plantillas del escenario con su configuración (unidad cloud-init y agente), que
    el lote lee al planificar un clon.
    """

    def __init__(self):
        super().__init__()
        for vmid in (9000, 9001):
            self.configs[vmid] = {
                "template": 1,
                "name": "plantilla-debian12" if vmid == 9000 else "plantilla-ubuntu",
                "ostype": "l26",
                "cores": 2,
                "memory": 2048,
                "agent": "1",
                "scsi0": f"local-lvm:base-{vmid}-disk-0,size=8G",
                "ide2": f"local-lvm:vm-{vmid}-cloudinit,media=cdrom",
                "net0": "virtio=BC:24:11:00:00:01,bridge=vmbr0",
            }

    def pools(self):
        return [{"poolid": p} for p in POOLS_GUIA.ids]

    def opciones_cluster(self):
        return {"user-tag-access": {"user-allow": "free"}}

    def plantillas_visibles(self):
        return list(plantillas_del_escenario("pve1"))

    def storages(self, nodo, con_formatos=False):
        return []  # los formatos no se sondean en la guía: vale la tabla fija

    def contenido_storage(self, nodo, storage, contenido):
        return []

    def solo_lectura(self):
        self.pidio_solo_lectura += 1
        return _VistaGuiaSoloLectura(self)


def _lote_con_opciones(qtbot, entorno, alto=1000):
    entorno.inv = _inventario_fase_a(inventario_guia_cluster())
    preparar_lote(
        qtbot,
        entorno,
        cantidad=5,
        prefijo="srv-web",
        nodo=None,
        cliente=ClienteGuiaFalso(),
        perfil_=perfil(*PERFIL),
    )
    v = entorno.ventana
    preparar(qtbot, v, alto, 1900)
    cfg = _cfg_opciones(nodo="pve1", redes=[InterfazRed("vmbr0")])
    v.formulario.aplicar_configuracion(cfg)
    esperar_validacion(qtbot, v)
    ver_resumen(qtbot, v)
    return v


def test_64_lote_resumen_opciones(qtbot, entorno, guardar):  # noqa: F811
    v = _lote_con_opciones(qtbot, entorno, 700)
    qtbot.wait(100)
    guardar(v.resumen_lote, "64-lote-resumen-opciones")


def test_65_simulacion_encender(qtbot, entorno, guardar):  # noqa: F811
    v = _lote_con_opciones(qtbot, entorno)
    r = v.resumen_lote
    r.boton_simular.click()
    qtbot.waitUntil(lambda: r.es_simulacion and not v._planificando, timeout=4000)
    if not r.detalles_peticiones._texto.isVisible():
        r.detalles_peticiones._boton.click()
    qtbot.wait(100)
    # Se baja el texto técnico hasta la petición que enciende la primera máquina.
    texto = r.detalles_peticiones._texto
    texto.moveCursor(QTextCursor.MoveOperation.Start)
    texto.find("status/start")
    cursor = texto.textCursor()
    cursor.clearSelection()
    texto.setTextCursor(cursor)
    texto.ensureCursorVisible()
    qtbot.wait(100)
    guardar(r, "65-simulacion-encender")


def test_66_deshacer_confirmacion_forzada(qtbot, guardar):
    inspeccion = InspeccionRollback(
        encendidas=(101, 102),
        protegidas=(102, 103),
        encendidas_sin_privilegio=(104,),
        nombres={101: "srv-web-01", 102: "srv-web-02", 103: "srv-web-03", 104: "srv-web-04"},
    )
    guardar(
        mostrar(qtbot, DialogoConfirmarDeshacerForzado(inspeccion)),
        "66-deshacer-confirmacion-forzada",
    )


def test_67_guia_privilegios_opcionales(qtbot, guardar):
    d = DialogoGuiaToken()
    d.resize(760, 1100)
    mostrar(qtbot, d)
    # Se baja la lista hasta «Privilegios opcionales».
    barra = d.findChild(QScrollArea).verticalScrollBar()
    barra.setValue(barra.maximum())
    qtbot.wait(100)
    guardar(d, "67-guia-privilegios-opcionales")


# --- 10. Fase B (0.7.0): cloud-init, espera de IP y asistente de plantilla -------------------

INFO_PLANTILLA_CI = InfoCloudInitPlantilla(
    unidad=True, clave_unidad="ide2", ostype="l26", agente=True, tarjetas=(0,)
)


@pytest.fixture
def plantillas_cloudinit(monkeypatch):
    """Las plantillas del escenario traen unidad cloud-init, una tarjeta y el agente activo."""

    def con_info(plantillas):
        return tuple(
            replace(p, detalle=replace(p.detalle, cloudinit=INFO_PLANTILLA_CI)) for p in plantillas
        )

    original_catalogo = controlador_origen.leer_catalogo_para
    original_plantillas = controlador_origen.leer_plantillas

    def catalogo(*args, **kw):
        cat = original_catalogo(*args, **kw)
        if cat.plantillas is None:
            return cat
        return replace(cat, plantillas=con_info(cat.plantillas))

    def plantillas(*args, **kw):
        return con_info(original_plantillas(*args, **kw))

    monkeypatch.setattr(controlador_origen, "leer_catalogo_para", catalogo)
    monkeypatch.setattr(controlador_origen, "leer_plantillas", plantillas)


def _ci_guia(**cambios):
    """Cloud-init de la guía: usuario, una clave falsa, net0 con IP fija y DNS (sin contraseña)."""
    base = {
        "usuario": "ana",
        "claves": (CLAVE_SSH_FALSA,),
        "tarjetas": (
            TarjetaCloudInit(
                0, ModoTarjeta.FIJA, ip="192.0.2.50/24", puerta="192.0.2.1", serie=False
            ),
        ),
        "dns": ("192.0.2.2", "192.0.2.3"),
        "dominio": "demo.example.com",
    }
    base.update(cambios)
    return ConfigCloudInit(**base)


def _inventario_fase_b(inv, *, quitar=()):
    """Inventario con los privilegios opcionales de la fase B (cloud-init y agente) concedidos."""
    permisos = permisos_fase_a(
        anadir=("VM.PowerMgmt", "Pool.Audit", "VM.Config.Cloudinit", "VM.GuestAgent.Audit"),
        quitar=quitar,
    )
    return _inventario_fase_a_con(inv, permisos)


def _inventario_fase_a_con(inv, permisos):
    inv2 = inventario_con(inv, permisos, POOLS_GUIA)
    inv2.catalogo = replace(inv2.catalogo, politica_etiquetas=PoliticaEtiquetas(permiso="free"))
    return inv2


def _clonando(qtbot, entorno, alto, *, inv=None, **cfg):
    """Ventana en modo avanzado con «Copiar una plantilla» elegida y cloud-init visible."""
    v = conectado(qtbot, entorno, inv or _inventario_fase_b(inventario_guia_cluster()), alto)
    v.establecer_modo(Modo.AVANZADO)
    poner_nombre(qtbot, v, "srv-web-01")
    sel = v.formulario.selector_origen
    _marcar(v, OrigenSO.CLONAR_PLANTILLA)
    sel.aplicar(cfg_clon("plantilla-debian12", 9000, nodo="pve", **cfg))
    qtbot.waitUntil(lambda: v.formulario.seccion_cloudinit.isVisibleTo(v.formulario), timeout=4000)
    esperar_validacion(qtbot, v)
    return v


def _apilar(widgets, separacion=14):
    """Imagen con las capturas de varios cuadros una debajo de otra (fondo blanco)."""
    imagenes = [w.grab() for w in widgets]
    ancho = max(i.width() for i in imagenes)
    alto = sum(i.height() for i in imagenes) + separacion * (len(imagenes) - 1)
    lienzo = QPixmap(ancho, alto)
    lienzo.fill(Qt.GlobalColor.white)
    pintor = QPainter(lienzo)
    y = 0
    for i in imagenes:
        pintor.drawPixmap(0, y, i)
        y += i.height() + separacion
    pintor.end()
    return lienzo


def test_68_seccion_cloudinit(qtbot, entorno, preguntas, plantillas_cloudinit, guardar):  # noqa: F811
    v = _clonando(qtbot, entorno, 2500)
    v.formulario.seccion_cloudinit.aplicar(_ci_guia())
    esperar_validacion(qtbot, v)
    qtbot.wait(300)  # el formulario se acomoda al aplicar los valores
    # Ventana completa: origen «Copiar una plantilla» y, debajo, la sección ya rellena.
    guardar(v, "68-seccion-cloudinit")


def _lote_cloudinit(qtbot, entorno, alto=1000, **cfg):
    """Lote de 4 máquinas que clonan la plantilla, con cloud-init e IP en serie desde .50."""
    entorno.inv = _inventario_fase_b(inventario_guia_cluster())
    preparar_lote(
        qtbot,
        entorno,
        cantidad=4,
        prefijo="srv-web",
        nodo="pve1",
        cliente=ClienteGuiaFalso(),
        perfil_=perfil(*PERFIL),
    )
    v = entorno.ventana
    preparar(qtbot, v, alto, 1900)
    v.establecer_modo(Modo.AVANZADO)
    _marcar(v, OrigenSO.CLONAR_PLANTILLA)
    v.formulario.selector_origen.aplicar(cfg_clon("plantilla-debian12", 9000, nodo="pve1"))
    qtbot.waitUntil(lambda: v.formulario.seccion_cloudinit.isVisibleTo(v.formulario), timeout=4000)
    ci = _ci_guia(
        tarjetas=(
            TarjetaCloudInit(
                0, ModoTarjeta.FIJA, ip="192.0.2.50/24", puerta="192.0.2.1", serie=True
            ),
        )
    )
    v.formulario.seccion_cloudinit.aplicar(ci)
    for clave, valor in cfg.items():
        getattr(v.formulario, clave)(valor)
    esperar_validacion(qtbot, v)
    return v


def test_69_cloudinit_ip_en_serie(qtbot, entorno, plantillas_cloudinit, guardar):  # noqa: F811
    v = _lote_cloudinit(qtbot, entorno)
    ver_resumen(qtbot, v)
    qtbot.wait(100)
    v.resumen_lote.setMinimumWidth(760)
    qtbot.wait(100)
    guardar(v.resumen_lote, "69-cloudinit-ip-en-serie")


def test_70_esperar_ip(qtbot, entorno, preguntas, plantillas_cloudinit, guardar):  # noqa: F811
    v = _clonando(qtbot, entorno, 2000)
    f = v.formulario
    f.chk_encender.setChecked(True)
    f.chk_esperar_ip.setChecked(True)
    esperar_validacion(qtbot, v)
    qtbot.wait(100)
    guardar(_grupo(f.chk_esperar_ip), "70-esperar-ip")


def test_71_progreso_con_ip(qtbot, guardar):
    p = ProgresoLote()
    qtbot.addWidget(p)
    entradas = (
        entrada_ip(
            0,
            nombre="srv-web-01",
            plazo_s=120,
            ip=ResultadoIp(EstadoIp.OBTENIDA, principal="192.0.2.50"),
        ),
        entrada_ip(
            1,
            nombre="srv-web-02",
            ip=ResultadoIp(EstadoIp.AGENTE_NO_RESPONDE),
        ),
        entrada_ip(2, nombre="srv-web-03"),
    )
    p.resize(1000, 480)
    p.show()
    p.iniciar(plan_vacio(3))
    p.actualizar(entradas)
    p.establecer_fase(FaseLote.TERMINADO)
    p.establecer_espera_ip(1)  # una máquina sigue esperando su IP
    qtbot.waitExposed(p)
    qtbot.wait(100)
    guardar(p, "71-progreso-con-ip")


# --- Asistente «Crear plantilla desde imagen cloud» ------------------------------------------

NOMBRE_PLANTILLA = "plantilla-ubuntu-cloud"
VMID_PLANTILLA = 9100


class ClienteAsistente(ClienteB2):
    """Cliente del asistente que ofrece las imágenes del escenario y registra las escrituras."""

    def __init__(self):
        super().__init__()
        self.config = {
            "name": NOMBRE_PLANTILLA,
            "template": 0,
            "ide2": f"datos:vm-{VMID_PLANTILLA}-cloudinit,media=cdrom",
        }

    def contenido_storage(self, nodo, storage, contenido):
        if contenido == Contenido.IMPORT and storage == "local":
            return imagenes_import()
        return []


def _asistente(qtbot, cliente, fabrica=None, ancho=760, alto=900):
    """Asistente (Proxmox 9.2, modo avanzado) con la imagen del servidor y los datos de la guía."""
    inv = _inventario_fase_b(inventario_guia_individual())
    d = DialogoPlantillaImagen(
        sesion=sesion_falsa(cliente=cliente, version=(9, 2)),
        reloj=RelojSimulado(),
        lanzador=Lanzador(),
        transferencias=ServicioTransferenciasFalso(),
        inv=inv,
        avanzado=True,
        nodo="pve",
        fabrica_creacion=fabrica or FabricaCreacionFalsa(),
    )
    qtbot.addWidget(d)
    d.resize(ancho, alto)
    d.show()
    qtbot.waitExposed(d)
    d.radio_importada.setChecked(True)
    d.boton_actualizar_importadas.click()
    qtbot.waitUntil(lambda: d.combo_importadas.count() > 0, timeout=3000)
    d.combo_importadas.setCurrentIndex(
        d.combo_importadas.findText("ubuntu-24.04-cloudimg.qcow2", Qt.MatchFlag.MatchContains)
    )
    d.campo_nombre.setText(NOMBRE_PLANTILLA)
    d.spin_vmid.setValue(VMID_PLANTILLA)
    return d


def _desplazar(d, arriba: bool):
    barra = d.findChild(QScrollArea).verticalScrollBar()
    barra.setValue(0 if arriba else barra.maximum())


def test_72_asistente_plantilla_imagen(qtbot, guardar):
    d = _asistente(qtbot, ClienteAsistente())
    _desplazar(d, True)
    qtbot.wait(150)
    guardar(d, "72-asistente-plantilla-imagen")


def test_73_asistente_plantilla_confirmar(qtbot, guardar):
    d = _asistente(qtbot, ClienteAsistente())
    d.grupo_cloudinit.setChecked(True)
    d.campo_usuario.setText("ana")
    d.campo_claves.setPlainText(CLAVE_SSH_FALSA)
    d.campo_dns.setText("192.0.2.2 192.0.2.3")
    d.casilla_irreversible.setChecked(True)
    qtbot.waitUntil(lambda: d.boton_crear.isEnabled(), timeout=3000)
    qtbot.wait(300)  # el aviso final cambia el alto del contenido: se espera a que se acomode
    _desplazar(d, False)
    qtbot.wait(150)
    guardar(d, "73-asistente-plantilla-confirmar")


class ClienteAsistenteConFallo(ClienteAsistente):
    """Proxmox rechaza (403) guardar los valores de cloud-init: el paso 4 falla."""

    def configurar_vm(self, nodo, vmid, parametros):
        if any(k in parametros for k in ("ciuser", "sshkeys", "ipconfig0", "nameserver")):
            raise ErrorProxLaunch(
                CodigoError.PERMISO_INSUFICIENTE, {"ajuste": "cloudinit"}, "403 Forbidden"
            )
        super().configurar_vm(nodo, vmid, parametros)


def test_74_asistente_plantilla_fallo(qtbot, monkeypatch, guardar):
    monkeypatch.setattr(plantilla_imagen_modulo, "confirmar", lambda *a, **k: True)
    d = _asistente(qtbot, ClienteAsistenteConFallo(), alto=1000)
    d.grupo_cloudinit.setChecked(True)
    d.campo_usuario.setText("ana")
    d.campo_claves.setPlainText(CLAVE_SSH_FALSA)
    d.casilla_irreversible.setChecked(True)
    qtbot.waitUntil(lambda: d.boton_crear.isEnabled(), timeout=3000)
    d.boton_crear.click()
    qtbot.waitUntil(lambda: d.fase == "detenido", timeout=5000)
    qtbot.waitUntil(lambda: d.boton_borrar.isVisibleTo(d), timeout=3000)
    qtbot.wait(300)
    _desplazar(d, True)
    qtbot.wait(150)
    guardar(d, "74-asistente-plantilla-fallo")


def test_75_importar_csv_cloudinit(qtbot, tmp_path, lanzador, guardar):
    d = _dialogo_csv(
        qtbot,
        tmp_path,
        lanzador,
        "mvs-cloudinit.csv",
        CSV_CLOUDINIT,
        avanzado=True,
        inv=_inventario_fase_b(inventario_guia_cluster()),
    )
    mostrar(qtbot, d)
    d.resize(1500, 800)
    d.detalle.setMaximumHeight(16777215)
    d.detalle.setMinimumHeight(330)  # el detalle de la fila enseña las columnas de cloud-init
    d.tabla.selectRow(1)
    qtbot.wait(100)
    guardar(d, "75-importar-csv-cloudinit")


def test_76_menu_archivo_plantilla(qtbot, qapp, entorno, guardar):  # noqa: F811
    v = conectado(qtbot, entorno, _inventario_fase_b(inventario_guia_cluster()))
    captura_menu(qapp, qtbot, v, 0, "76-menu-archivo-plantilla", guardar)
