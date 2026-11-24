"""VentanaPrincipal con el origen del SO: capacidades, pregunta «¿Cuál usar siempre?», bloqueos
V-O26/V-O27, origen bloqueado durante un lote, cambios sin guardar y cierre con transferencia
(RF-O01, RF-O05, RF-O06, RF-O12; CA-O01.7, CA-O12.4; RF-G08).

Sin red ni modales reales: las lecturas del catálogo y los diálogos de storage se sustituyen.
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtGui import QCloseEvent

from proxlaunch.interfaz import controlador_origen as co
from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.controlador_origen import ControladorOrigen
from proxlaunch.nucleo.modelos.catalogo import Contenido, ListadoStorage
from proxlaunch.nucleo.modelos.origen import TipoSO
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.persistencia.preferencias import Modo

from . import test_ventana_principal as _base
from .apoyo import perfil, sesion_falsa
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import definicion_homogenea, escribir_lote_guardado
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .apoyo_mvp4 import VOLID_ISO, caps_origen, inv_origen, plantilla_pve, volumen
from .test_ventana_principal import conectar, esperar_validacion, poner_nombre

entorno = _base.entorno  # fixture base de la ventana


@pytest.fixture
def lecturas(monkeypatch):
    """Catálogo del servidor falso: lo que ``en_servidor`` diga (ISO) y una plantilla."""

    class Servidor:
        isos = [VOLID_ISO]
        pedidos: list = []

    s = Servidor()
    s.pedidos = []

    def leer(sesion, reloj, inv, nodo, contenido):
        s.pedidos.append((nodo, contenido))
        vols = tuple(volumen(v, contenido) for v in s.isos) if contenido == Contenido.ISO else ()
        return (ListadoStorage(nodo, "local", contenido, vols),)

    monkeypatch.setattr(co, "leer_listados", leer)
    monkeypatch.setattr(co, "leer_plantillas", lambda sesion, reloj: (plantilla_pve(),))
    return s


@pytest.fixture
def preguntas(monkeypatch):
    """Sustituye el diálogo «¿Cuál usar siempre?»: registra y acepta lo preseleccionado."""
    registro: list = []

    def _ejecutar(dialogo):
        registro.append(dialogo)
        dialogo.boton_aceptar.click()
        return True

    monkeypatch.setattr(ControladorOrigen, "_ejecutar", staticmethod(_ejecutar))
    return registro


def _conectar_origen(qtbot, entorno, inv=None, **perfil_kw):
    entorno.inv = inv if inv is not None else inv_origen()
    s = sesion_falsa(perfil(**perfil_kw)) if perfil_kw else sesion_falsa()
    conectar(qtbot, entorno, s)
    esperar_validacion(qtbot, entorno.ventana)
    return entorno.ventana


def _marcar(v, origen):
    v.formulario.selector_origen.opciones[origen].setChecked(True)


def _esperar_lecturas(qtbot, v):
    qtbot.waitUntil(lambda: not v._lanzador.hay_activos, timeout=4000)
    esperar_validacion(qtbot, v)


# --- Capacidades al conectar ---------------------------------------------------------------------


def test_al_conectar_el_selector_tiene_las_cuatro_opciones_y_no_pregunta_nada(
    qtbot, entorno, lecturas, preguntas
):
    v = _conectar_origen(qtbot, entorno)
    sel = v.formulario.selector_origen
    assert all(r.isEnabled() for r in sel.opciones.values())
    assert sel.origen == OrigenSO.DISCO_VACIO
    assert preguntas == []  # nunca al conectar


def test_ca_o02_7_forzar_la_version_minima_8_4_deja_importar_habilitado_en_el_selector(
    qtbot, entorno, lecturas, preguntas
):
    entorno.inv = inv_origen()
    conectar(qtbot, entorno, sesion_falsa(version=(8, 4), forzada=True))
    esperar_validacion(qtbot, entorno.ventana)
    sel = entorno.ventana.formulario.selector_origen
    assert sel.opciones[OrigenSO.IMPORTAR_DISCO].isEnabled()
    assert sel.motivos[OrigenSO.IMPORTAR_DISCO].text() == ""


# --- «¿Cuál usar siempre?» del storage de discos -------------------------------------------------


def test_el_dialogo_de_storage_aparece_al_elegir_iso_con_varios_candidatos(
    qtbot, entorno, lecturas, preguntas
):
    v = _conectar_origen(qtbot, entorno)
    _marcar(v, OrigenSO.ISO)
    qtbot.waitUntil(lambda: len(preguntas) == 1, timeout=3000)
    assert preguntas[0].contenido == Contenido.IMAGENES
    # Los discos usan lo elegido y queda recordado en el perfil de conexión.
    elegido = v.formulario.configuracion().discos[0].storage
    assert elegido == "local-lvm"  # 150 GiB libres frente a 50 de «local»
    assert v.origen.recordado(Contenido.IMAGENES) == "local-lvm"


def test_el_dialogo_de_storage_aparece_al_elegir_disco_existente(
    qtbot, entorno, lecturas, preguntas
):
    v = _conectar_origen(qtbot, entorno)
    _marcar(v, OrigenSO.IMPORTAR_DISCO)
    qtbot.waitUntil(lambda: len(preguntas) == 1, timeout=3000)


def test_el_dialogo_de_storage_nunca_aparece_con_disco_vacio(qtbot, entorno, lecturas, preguntas):
    v = _conectar_origen(qtbot, entorno)
    _marcar(v, OrigenSO.ISO)
    qtbot.waitUntil(lambda: len(preguntas) == 1, timeout=3000)
    preguntas.clear()
    _marcar(v, OrigenSO.DISCO_VACIO)
    qtbot.wait(100)
    assert preguntas == []


def test_con_un_storage_recordado_vigente_no_se_vuelve_a_preguntar(
    qtbot, entorno, lecturas, preguntas
):
    v = _conectar_origen(qtbot, entorno, storage_mv="local")
    _marcar(v, OrigenSO.ISO)
    qtbot.wait(150)
    assert preguntas == []
    assert v.formulario.configuracion().discos[0].storage == "local"


# --- Resumen y botón Crear con ISO ---------------------------------------------------------------


def test_ca_o01_6_con_iso_sin_archivo_elegido_no_se_puede_crear_hasta_elegirlo(
    qtbot, entorno, lecturas, preguntas
):
    v = _conectar_origen(qtbot, entorno)
    poner_nombre(qtbot, v)
    _marcar(v, OrigenSO.ISO)
    qtbot.waitUntil(lambda: len(preguntas) == 1, timeout=3000)
    _esperar_lecturas(qtbot, v)
    assert not v.resumen.boton_crear.isEnabled()
    sel = v.formulario.selector_origen
    sel.boton_elegir_iso.click()  # abre el catálogo, que recibe lo leído
    qtbot.waitUntil(lambda: sel.dialogo_catalogo is not None, timeout=2000)
    _esperar_lecturas(qtbot, v)
    assert sel.dialogo_catalogo.seleccionar_volid(VOLID_ISO)
    sel.dialogo_catalogo.boton_elegir.click()
    sel.combo_so.setCurrentIndex(sel.combo_so.findData(TipoSO.LINUX.value))
    _esperar_lecturas(qtbot, v)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=3000)
    assert "Montará el ISO «alpine.iso» como CD" in v.resumen.texto_html


def test_v_o26_un_storage_recordado_que_ya_no_existe_bloquea_iso_pero_no_disco_vacio(
    qtbot, entorno, lecturas, preguntas
):
    v = _conectar_origen(qtbot, entorno, storage_mv="fantasma")
    poner_nombre(qtbot, v)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=3000)  # vacía: solo aviso
    _marcar(v, OrigenSO.ISO)
    _esperar_lecturas(qtbot, v)
    assert not v.resumen.boton_crear.isEnabled()
    assert "fantasma" in v.resumen.texto_pendientes
    assert "fantasma" not in v.formulario.selector_origen.valor_iso.text()


def test_v_o27_con_una_transferencia_activa_no_se_puede_crear(
    qtbot, entorno, lecturas, preguntas, monkeypatch
):
    v = _conectar_origen(qtbot, entorno)
    poner_nombre(qtbot, v)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=3000)
    with monkeypatch.context() as m:
        m.setattr(ControladorOrigen, "transferencia_activa", property(lambda s: True))
        v._timer_validar.start()
        esperar_validacion(qtbot, v)
        assert not v.resumen.boton_crear.isEnabled()
        assert "en curso" in v.resumen.texto_pendientes.lower()
    v._timer_validar.start()
    esperar_validacion(qtbot, v)
    assert v.resumen.boton_crear.isEnabled()  # al terminar la transferencia se libera


# --- Origen bloqueado durante un lote (CA-O01.7) -


def test_ca_o01_7_bloquear_la_edicion_deshabilita_el_selector_y_liberar_lo_habilita(
    qtbot, entorno, lecturas
):
    v = _conectar_origen(qtbot, entorno)
    sel = v.formulario.selector_origen
    v._bloquear_edicion(True)
    assert not sel.isEnabled() and not v.formulario.isEnabled()
    v._bloquear_edicion(False)
    assert sel.isEnabled()


def test_v_o27_un_lote_en_curso_impide_abrir_transferencias(qtbot, entorno, lecturas, widget_padre):
    v = _conectar_origen(qtbot, entorno)
    v.origen.establecer_ocupado(True)
    v.origen.abrir_subida(Contenido.ISO, "pve", widget_padre)
    assert v.origen._dialogo is None


# --- Cambios sin guardar: el origen cuenta (RF-G08) -


def test_rf_g08_cambiar_el_origen_de_un_lote_abierto_cuenta_como_cambio_sin_guardar(
    qtbot, entorno3, archivos, lecturas, preguntas, tmp_path
):
    inv = entorno3.inv
    inv.storages_todos = dict(inv.storages)  # ISO en «local» de pve1
    conectar(qtbot, entorno3, sesion_falsa())
    esperar_validacion(qtbot, entorno3.ventana)
    v = entorno3.ventana
    ruta = escribir_lote_guardado(tmp_path / "o.proxlaunch-lote.json", definicion_homogenea())
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == ruta, timeout=4000)
    esperar_validacion(qtbot, v)
    assert not v._hay_cambios_sin_guardar()
    _marcar(v, OrigenSO.CLONAR_PLANTILLA)
    esperar_validacion(qtbot, v)
    assert v._hay_cambios_sin_guardar()
    _marcar(v, OrigenSO.DISCO_VACIO)
    esperar_validacion(qtbot, v)
    assert not v._hay_cambios_sin_guardar()


# --- Cierre con transferencia activa (CA-O12.4) -


class _Confirma:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.llamadas = []

    def __call__(self, parent, titulo, texto, aceptar, cancelar):
        self.llamadas.append((titulo, texto, aceptar, cancelar))
        return self.respuesta


@pytest.fixture
def transferencia_activa(monkeypatch):
    estado = {"activa": True, "canceladas": 0, "esperas": 0}
    monkeypatch.setattr(
        ControladorOrigen, "transferencia_activa", property(lambda s: estado["activa"])
    )

    def cancelar(self):
        estado["canceladas"] += 1
        estado["activa"] = False

    def esperar(self, limite_s=3.0):
        estado["esperas"] += 1
        return True

    monkeypatch.setattr(ControladorOrigen, "cancelar_transferencia", cancelar)
    monkeypatch.setattr(ControladorOrigen, "esperar_fin_de_transferencia", esperar)
    return estado


def test_ca_o12_4_cerrar_con_transferencia_pregunta_y_si_se_sigue_no_cancela_nada(
    qtbot, entorno, lecturas, transferencia_activa, monkeypatch
):
    v = _conectar_origen(qtbot, entorno)
    c = _Confirma(False)
    monkeypatch.setattr(vp, "confirmar", c)
    ev = QCloseEvent()
    v.closeEvent(ev)
    assert not ev.isAccepted()
    assert len(c.llamadas) == 1
    titulo, texto, aceptar, cancelar = c.llamadas[0]
    assert "transferencia" in titulo.lower()
    assert "se cancelará" in texto and "incompleto" in texto
    assert aceptar != cancelar and cancelar == "Seguir en ProxLaunch"
    assert transferencia_activa["canceladas"] == 0


def test_ca_o12_4_cerrar_y_confirmar_cancela_y_espera_antes_de_cerrar(
    qtbot, entorno, lecturas, transferencia_activa, monkeypatch
):
    v = _conectar_origen(qtbot, entorno)
    monkeypatch.setattr(vp, "confirmar", _Confirma(True))
    ev = QCloseEvent()
    v.closeEvent(ev)
    assert ev.isAccepted()
    assert transferencia_activa["canceladas"] == 1
    assert transferencia_activa["esperas"] == 1


def test_ca_o12_4_sin_transferencia_cerrar_no_pregunta_por_transferencias(
    qtbot, entorno, lecturas, monkeypatch
):
    v = _conectar_origen(qtbot, entorno)
    c = _Confirma(False)
    monkeypatch.setattr(vp, "confirmar", c)
    ev = QCloseEvent()
    v.closeEvent(ev)
    assert ev.isAccepted()
    assert not any("transferencia" in ll[0].lower() for ll in c.llamadas)


def test_ca_o12_4_la_pregunta_real_tiene_el_foco_en_cancelar(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from proxlaunch.interfaz.dialogos.confirmar import confirmar

    capturada = {}

    def _exec(self):
        capturada["default"] = self.defaultButton().text()
        capturada["escape"] = self.escapeButton().text()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", _exec)
    confirmar(None, "t", "x", "Cancelar la transferencia y cerrar", "Seguir en ProxLaunch")
    assert capturada == {"default": "Seguir en ProxLaunch", "escape": "Seguir en ProxLaunch"}


# --- Modo avanzado llega al selector -


def test_el_cambio_de_modo_llega_al_selector_y_al_controlador(qtbot, entorno, lecturas):
    v = _conectar_origen(qtbot, entorno)
    v.establecer_modo(Modo.AVANZADO)
    assert v.origen.modo_avanzado is True
    assert v.formulario.selector_origen.fila_modo is not None
    v.establecer_modo(Modo.BASICO)
    assert v.origen.modo_avanzado is False


def test_las_capacidades_de_origen_usan_el_nucleo_real():
    assert dataclasses.is_dataclass(caps_origen())
