"""«Crear sin etiquetas» para una sola máquina cuando el servidor rechaza la etiqueta.

Con ``user-tag-access`` restringido la tarea falla con ETIQUETA_RECHAZADA y la MV no se crea.
El botón desmarca «Etiquetar las máquinas» para UNA sola creación: la siguiente petición va sin
etiquetas y después la casilla vuelve a marcarse.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QPushButton

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.persistencia.preferencias import Modo

from . import test_ventana_principal as _base
from .apoyo import ClienteLoteFalso, CreacionFalsa, resultado, sesion_falsa
from .test_ventana_principal import conectar, crear_y_esperar, poner_nombre
from .test_ventana_principal_f7 import _incierto

entorno = _base.entorno


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Todas las pruebas de este módulo cierran sin bloquear."""


def rechazo(desenlace=Desenlace.ERROR, codigo=CodigoError.ETIQUETA_RECHAZADA):
    return resultado(desenlace, ErrorProxLaunch(codigo), upid=None)


def preparar(qtbot, entorno, res=None, *, avanzado=True, sesion=None):
    """Conecta, deja la plantilla con nombre y devuelve la ventana lista para pulsar «Crear»."""
    v = entorno.ventana
    entorno.cliente = ClienteLoteFalso()
    entorno.creacion = CreacionFalsa(res if res is not None else rechazo())
    conectar(qtbot, entorno, sesion or sesion_falsa(cliente=entorno.cliente))
    if avanzado:
        v.establecer_modo(Modo.AVANZADO)
    poner_nombre(qtbot, v)
    return v


def crear_de_nuevo(qtbot, v):
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)


def tras_sin_etiquetas(qtbot, entorno, v):
    """Pulsa el botón y espera a que el formulario esté otra vez listo para crear."""
    v.progreso.boton_sin_etiquetas.click()
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)


# --- Cuándo aparece el botón --------------------------------------------------------------------


def test_con_una_maquina_y_etiqueta_rechazada_aparece_el_boton_y_el_aviso(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    assert v.progreso.boton_sin_etiquetas.isVisible()
    assert v.progreso.boton_sin_etiquetas.text() == "Crear sin etiquetas"
    assert "sin etiquetas" in v.progreso.texto_mensaje
    assert "Deshacer" in v.progreso.texto_mensaje


def test_el_boton_tambien_aparece_en_modo_basico(qtbot, entorno):
    v = preparar(qtbot, entorno, avanzado=False)
    crear_y_esperar(qtbot, v)
    assert v.progreso.boton_sin_etiquetas.isVisible()


@pytest.mark.parametrize(
    "codigo",
    [CodigoError.SIN_ESPACIO, CodigoError.DESCONOCIDO, CodigoError.PERMISO_INSUFICIENTE],
)
def test_otros_errores_no_ofrecen_crear_sin_etiquetas(qtbot, entorno, codigo):
    v = preparar(qtbot, entorno, rechazo(codigo=codigo))
    crear_y_esperar(qtbot, v)
    assert not v.progreso.boton_sin_etiquetas.isVisible()


def test_un_envio_incierto_no_ofrece_crear_sin_etiquetas(qtbot, entorno):
    v = preparar(qtbot, entorno, _incierto())
    crear_y_esperar(qtbot, v)
    assert not v.progreso.boton_sin_etiquetas.isVisible()


def test_si_la_casilla_ya_estaba_desmarcada_no_se_ofrece(qtbot, entorno):
    v = preparar(qtbot, entorno)
    v.bloque_lote.chk_etiquetar.setChecked(False)
    crear_y_esperar(qtbot, v)
    assert not v.progreso.boton_sin_etiquetas.isVisible()


def test_etiqueta_rechazada_con_otro_desenlace_no_ofrece_el_boton(qtbot, entorno):
    v = preparar(qtbot, entorno, rechazo(desenlace=Desenlace.CON_AVISOS))
    crear_y_esperar(qtbot, v)
    assert not v.progreso.boton_sin_etiquetas.isVisible()


def test_en_un_lote_de_varias_maquinas_no_aparece(qtbot, entorno):
    v = preparar(qtbot, entorno)
    b = v.bloque_lote
    b.cantidad.setText("2")
    b.cantidad.textEdited.emit("2")
    b.prefijo.setText("web")
    b.prefijo.textEdited.emit("web")
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()  # abre el resumen del lote; no crea nada por sí solo
    assert not v.progreso.boton_sin_etiquetas.isVisible()
    assert entorno.creacion.llamadas_crear == 0


def test_el_boton_se_oculta_al_reiniciar_el_panel(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    v.progreso.reiniciar()
    assert not v.progreso.boton_sin_etiquetas.isVisible()


# --- Pulsarlo -----------------------------------------------------------------------------------


def test_pulsarlo_desmarca_la_casilla_y_no_envia_nada(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    assert v.bloque_lote.chk_etiquetar.isChecked()
    enviados = entorno.creacion.llamadas_crear
    descubrimientos = entorno.llamadas.count(("descubrir",))
    tras_sin_etiquetas(qtbot, entorno, v)
    assert not v.bloque_lote.chk_etiquetar.isChecked()
    assert entorno.creacion.llamadas_crear == enviados  # solo prepara; no crea
    assert not v._creando
    assert v.formulario.isEnabled() and v.bloque_lote.isEnabled()
    assert not v.progreso.boton_sin_etiquetas.isVisible()
    assert entorno.llamadas.count(("descubrir",)) == descubrimientos + 1  # datos frescos
    assert "Etiquetas desactivadas" in v.statusBar().currentMessage()


def test_la_siguiente_creacion_va_sin_etiquetas_con_validacion_normal(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    assert entorno.creacion.cfgs_recibidas[0].etiquetas != ()  # la primera sí llevaba tags
    entorno.creacion.resultado = resultado(Desenlace.OK)
    tras_sin_etiquetas(qtbot, entorno, v)
    crear_de_nuevo(qtbot, v)
    assert entorno.creacion.llamadas_crear == 2
    assert entorno.creacion.cfgs_recibidas[1].etiquetas == ()
    assert v._ultimo_resultado.desenlace == Desenlace.OK


def test_sin_etiquetas_no_se_salta_la_validacion_del_formulario(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    tras_sin_etiquetas(qtbot, entorno, v)
    v.formulario.nombre.setText("")
    v.formulario.nombre.textEdited.emit("")
    qtbot.waitUntil(lambda: not v._timer_validar.isActive(), timeout=2000)
    assert not v.resumen.boton_crear.isEnabled()
    assert entorno.creacion.llamadas_crear == 1


# --- Un solo uso --------------------------------------------------------------------------------


def test_tras_terminar_esa_creacion_la_casilla_vuelve_a_marcarse(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    entorno.creacion.resultado = resultado(Desenlace.OK)
    tras_sin_etiquetas(qtbot, entorno, v)
    crear_de_nuevo(qtbot, v)
    assert v.bloque_lote.chk_etiquetar.isChecked()
    assert not v._sin_etiquetas_forzado


def test_la_creacion_posterior_vuelve_a_llevar_etiquetas(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    entorno.creacion.resultado = resultado(Desenlace.OK)
    tras_sin_etiquetas(qtbot, entorno, v)
    crear_de_nuevo(qtbot, v)
    v.progreso.boton_crear_otra.click()
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    poner_nombre(qtbot, v, "srv-web-02")
    crear_de_nuevo(qtbot, v)
    assert entorno.creacion.cfgs_recibidas[2].etiquetas != ()


def test_si_la_creacion_sin_etiquetas_falla_la_casilla_tambien_se_restaura(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    tras_sin_etiquetas(qtbot, entorno, v)  # el resultado sigue siendo el rechazo
    crear_de_nuevo(qtbot, v)
    assert v.bloque_lote.chk_etiquetar.isChecked()
    assert not v.progreso.boton_sin_etiquetas.isVisible()  # etiquetar ya era False al enviar


def test_volver_al_formulario_restaura_la_casilla(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    tras_sin_etiquetas(qtbot, entorno, v)
    assert not v.bloque_lote.chk_etiquetar.isChecked()
    v._volver_al_formulario()
    assert v.bloque_lote.chk_etiquetar.isChecked()
    assert not v._sin_etiquetas_forzado


def test_crear_otra_restaura_la_casilla(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    tras_sin_etiquetas(qtbot, entorno, v)
    v._crear_otra()
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    assert v.bloque_lote.chk_etiquetar.isChecked()
    assert not v._sin_etiquetas_forzado


def test_conectar_con_otro_perfil_restaura_la_casilla(qtbot, entorno):
    from .apoyo import perfil

    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    tras_sin_etiquetas(qtbot, entorno, v)
    conectar(qtbot, entorno, sesion_falsa(perfil("otro", "Otro", ("10.0.0.9",))))
    assert v.bloque_lote.chk_etiquetar.isChecked()
    assert not v._sin_etiquetas_forzado


def test_desconectar_restaura_la_casilla(qtbot, entorno):
    v = preparar(qtbot, entorno)
    crear_y_esperar(qtbot, v)
    tras_sin_etiquetas(qtbot, entorno, v)
    v._cerrar_sesion()
    assert v.bloque_lote.chk_etiquetar.isChecked()
    assert not v._sin_etiquetas_forzado


def test_una_casilla_desmarcada_a_mano_no_se_remarca_sola(qtbot, entorno):
    v = preparar(qtbot, entorno, resultado(Desenlace.OK))
    v.bloque_lote.chk_etiquetar.setChecked(False)
    crear_y_esperar(qtbot, v)
    v._crear_otra()
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    assert not v.bloque_lote.chk_etiquetar.isChecked()


def test_el_boton_es_un_qpushbutton_con_texto_traducible(qtbot, entorno):
    v = preparar(qtbot, entorno)
    boton = v.progreso.boton_sin_etiquetas
    assert isinstance(boton, QPushButton)
    assert not boton.isVisible()  # oculto de inicio
