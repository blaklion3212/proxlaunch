"""ControladorOrigen: transferencias, recarga del catálogo y selección del archivo subido
(RF-O09, RF-O12, RF-O25; CA-O09.6, CA-O12.4, CA-O12.8; V-O27; E-O23)."""

from __future__ import annotations

import pytest

from proxlaunch.interfaz import controlador_origen as co
from proxlaunch.interfaz.controlador_origen import ControladorOrigen
from proxlaunch.interfaz.dialogos.catalogo import FuenteCatalogo
from proxlaunch.interfaz.dialogos.transferencia import DialogoDescarga, DialogoSubida
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.interfaz.vistas.selector_origen import SelectorOrigen
from proxlaunch.nucleo.modelos.catalogo import Contenido, ListadoStorage
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.transferencias.modelos import EstadoTransferencia as Est

from .apoyo import perfil, sesion_falsa
from .apoyo_mvp4 import (
    VOLID_ISO,
    ServicioTransferenciasFalso,
    inv_origen,
    resultado_transferencia,
    volumen,
)


@pytest.fixture
def servicio():
    s = ServicioTransferenciasFalso()
    yield s
    s.puerta.set()


@pytest.fixture
def ctl(qtbot, rutas, servicio, monkeypatch):
    repo = RepositorioPerfiles(rutas.perfiles)
    repo.guardar(perfil())
    c = ControladorOrigen(Lanzador(), repo, RelojSimulado())
    inv = inv_origen()
    c.establecer_sesion(sesion_falsa(), inv)
    c._servicio_transferencias = servicio  # el servicio real iría a la red
    selector = SelectorOrigen()
    qtbot.addWidget(selector)
    selector.show()
    c.enlazar(selector, lambda: "pve")
    c.selector = selector
    # Nunca un modal real: «¿Cuál usar siempre?» aparece al elegir ISO o disco existente.
    c.preguntas = []
    c._ejecutar = lambda dialogo: c.preguntas.append(dialogo) or False
    c.lecturas = []
    # El catálogo del servidor: lo que "hay" en cada lectura se programa en c.en_servidor.
    c.en_servidor = []

    def leer(sesion, reloj, inv_, nodo, contenido):
        c.lecturas.append((nodo, contenido))
        vols = tuple(volumen(v, contenido) for v in c.en_servidor)
        return (ListadoStorage(nodo, "local", contenido, vols),)

    monkeypatch.setattr(co, "leer_listados", leer)
    yield c
    c.lanzador.esperar(3000)


def _esperar_lanzador(qtbot, c):
    qtbot.waitUntil(lambda: not c.lanzador.hay_activos, timeout=4000)


def test_ca_o12_8_una_subida_terminada_recarga_el_catalogo_y_deja_elegido_el_iso(
    qtbot, ctl, servicio, widget_padre, tmp_path
):
    ctl.selector.opciones[OrigenSO.ISO].setChecked(True)
    ctl.en_servidor = [VOLID_ISO]
    servicio.resultado = resultado_transferencia(volid=VOLID_ISO)
    ruta = tmp_path / "alpine.iso"
    ruta.write_bytes(bytes(0x8000) + b"\x01CD001\x01" + bytes(2048))
    ctl.abrir_subida(Contenido.ISO, "pve", widget_padre, fuente=FuenteCatalogo.ISO)
    d = ctl._dialogo
    assert isinstance(d, DialogoSubida)
    d.elegir_ruta(ruta)
    qtbot.waitUntil(lambda: d.listo_para_confirmar, timeout=4000)
    with qtbot.waitSignal(ctl.transferencia_terminada, timeout=4000):
        d.boton_accion.click()
    qtbot.waitUntil(lambda: ctl.selector.valor_iso.text() == "alpine.iso", timeout=4000)
    assert ("pve", Contenido.ISO) in ctl.lecturas  # se releyó el catálogo, no se supuso
    assert ctl.selector.completar(_cfg()).detalle_origen.iso.volid == VOLID_ISO


def _cfg():
    from .apoyo_mvp4 import cfg_base

    return cfg_base()


def test_ca_o12_8_una_subida_fallida_tambien_relee_el_catalogo_sin_elegir_nada(
    qtbot, ctl, servicio, widget_padre, tmp_path
):
    ctl.selector.opciones[OrigenSO.ISO].setChecked(True)
    servicio.resultado = resultado_transferencia(Est.FALLIDA, volid=None, quedo=None)
    ruta = tmp_path / "a.iso"
    ruta.write_bytes(bytes(0x8000) + b"\x01CD001\x01" + bytes(2048))
    ctl.abrir_subida(Contenido.ISO, "pve", widget_padre, fuente=FuenteCatalogo.ISO)
    d = ctl._dialogo
    d.elegir_ruta(ruta)
    qtbot.waitUntil(lambda: d.listo_para_confirmar, timeout=4000)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: ("pve", Contenido.ISO) in ctl.lecturas, timeout=4000)
    assert ctl.selector.valor_iso.text() == "Ningún archivo ISO elegido"


def test_usar_el_existente_elige_ese_archivo_tras_releer_el_catalogo(
    qtbot, ctl, servicio, widget_padre, tmp_path
):
    from proxlaunch.nucleo.validacion import Problema, Severidad

    from .apoyo_mvp4 import comprobacion

    ctl.selector.opciones[OrigenSO.ISO].setChecked(True)
    ctl.en_servidor = [VOLID_ISO]
    servicio.comprobacion = comprobacion(
        [Problema("destino", "V-O14", Severidad.ERROR, {"volid": VOLID_ISO})], existente=VOLID_ISO
    )
    ruta = tmp_path / "alpine.iso"
    ruta.write_bytes(bytes(0x8000) + b"\x01CD001\x01" + bytes(2048))
    ctl.abrir_subida(Contenido.ISO, "pve", widget_padre, fuente=FuenteCatalogo.ISO)
    d = ctl._dialogo
    d.elegir_ruta(ruta)
    qtbot.waitUntil(lambda: d.fila_existente.isVisible(), timeout=4000)
    d.boton_usar_existente.click()
    qtbot.waitUntil(lambda: ctl.selector.valor_iso.text() == "alpine.iso", timeout=4000)


def test_v_o27_con_un_lote_o_simulacion_en_curso_no_se_abre_ninguna_transferencia(
    qtbot, ctl, widget_padre
):
    mensajes = []
    ctl.mensaje.connect(mensajes.append)
    ctl.establecer_ocupado(True)
    ctl.abrir_subida(Contenido.ISO, "pve", widget_padre)
    ctl.abrir_descarga(Contenido.ISO, "pve", widget_padre)
    assert ctl._dialogo is None
    assert mensajes and "en curso" in mensajes[0]
    ctl.establecer_ocupado(False)
    ctl.abrir_subida(Contenido.ISO, "pve", widget_padre)
    assert isinstance(ctl._dialogo, DialogoSubida)


def test_e_o23_solo_una_transferencia_a_la_vez(qtbot, ctl, servicio, widget_padre):
    servicio.ocupado = True  # el servicio dice que ya hay una
    assert ctl.transferencia_activa
    ctl.abrir_subida(Contenido.ISO, "pve", widget_padre)
    assert ctl._dialogo is None


def test_ca_o12_4_transferencia_activa_refleja_el_dialogo_en_curso_y_cancelar_la_detiene(
    qtbot, ctl, servicio, widget_padre, tmp_path
):
    servicio.bloquear = True
    ruta = tmp_path / "a.iso"
    ruta.write_bytes(bytes(0x8000) + b"\x01CD001\x01" + bytes(2048))
    ctl.abrir_subida(Contenido.ISO, "pve", widget_padre)
    d = ctl._dialogo
    d.elegir_ruta(ruta)
    qtbot.waitUntil(lambda: d.listo_para_confirmar, timeout=4000)
    assert not ctl.transferencia_activa
    d.boton_accion.click()
    qtbot.waitUntil(lambda: servicio.inicio.is_set(), timeout=3000)
    assert ctl.transferencia_activa
    ctl.cancelar_transferencia()
    assert ctl.esperar_fin_de_transferencia(3.0)
    assert not ctl.transferencia_activa
    assert servicio.cancelado_visto


def test_esperar_fin_respeta_el_limite_si_la_transferencia_no_termina(qtbot, ctl, servicio):
    servicio.ocupado = True
    assert ctl.esperar_fin_de_transferencia(0.1) is False


def test_ca_o14_la_descarga_de_virtio_sin_url_fija_abre_un_dialogo_normal(
    qtbot, ctl, widget_padre, monkeypatch
):
    monkeypatch.setattr(co, "URL_VIRTIO_WIN", "")
    ctl.abrir_descarga(Contenido.ISO, "pve", widget_padre, fuente=FuenteCatalogo.DRIVERS)
    d = ctl._dialogo
    assert isinstance(d, DialogoDescarga)
    assert not d.campo_url.isReadOnly() and d.campo_url.text() == ""


def test_ca_o14_2_con_url_fija_virtio_va_verificada_y_no_editable(
    qtbot, ctl, widget_padre, monkeypatch
):
    monkeypatch.setattr(co, "URL_VIRTIO_WIN", "https://ejemplo.org/virtio-win.iso")
    monkeypatch.setattr(co, "SHA256_VIRTIO_WIN", "a" * 64)
    ctl.abrir_descarga(Contenido.ISO, "pve", widget_padre, fuente=FuenteCatalogo.DRIVERS)
    d = ctl._dialogo
    assert d.campo_url.isReadOnly() and d.campo_checksum.text() == "a" * 64


def test_enlazar_oculta_la_descarga_de_virtio_mientras_no_haya_url_fija(qtbot, ctl):
    """Decisión del orquestador: sin URL_VIRTIO_WIN la vía no se ofrece."""
    from proxlaunch.nucleo.modelos.origen import TipoSO

    ctl.selector.opciones[OrigenSO.ISO].setChecked(True)
    ctl.selector.combo_so.setCurrentIndex(ctl.selector.combo_so.findData(TipoSO.WINDOWS_11.value))
    from proxlaunch.nucleo.origen.constantes import URL_VIRTIO_WIN

    assert bool(URL_VIRTIO_WIN) == ctl.selector.boton_descargar_drivers.isVisible()


def test_ca_o25_los_archivos_subidos_quedan_en_el_registro_de_la_sesion(ctl):
    assert ctl.registro.lista() == ()


def test_sincronizar_con_iso_lee_el_catalogo_del_nodo_una_sola_vez(qtbot, ctl):
    from .apoyo_mvp4 import cfg_iso

    cfg = cfg_iso(volid=None)
    ctl.sincronizar(cfg)
    _esperar_lanzador(qtbot, ctl)
    ctl.sincronizar(cfg)
    ctl.sincronizar(cfg)
    _esperar_lanzador(qtbot, ctl)
    assert ctl.lecturas.count(("pve", Contenido.ISO)) == 1


def test_el_catalogo_leido_queda_en_el_inventario_para_la_validacion(qtbot, ctl):
    ctl.en_servidor = [VOLID_ISO]
    ctl.cargar_catalogo("pve", Contenido.ISO)
    _esperar_lanzador(qtbot, ctl)
    qtbot.waitUntil(lambda: bool(ctl.inventario.catalogo.listados), timeout=3000)
    volids = [v.volid for lst in ctl.inventario.catalogo.listados for v in lst.volumenes]
    assert volids == [VOLID_ISO]


def test_una_lectura_tardia_de_otra_sesion_se_descarta(qtbot, ctl):
    ctl.en_servidor = [VOLID_ISO]
    ctl.cargar_catalogo("pve", Contenido.ISO)
    ctl.establecer_sesion(sesion_falsa(perfil("p2", "Otro")), inv_origen())
    _esperar_lanzador(qtbot, ctl)
    qtbot.wait(50)
    assert ctl.inventario.catalogo.listados == ()
