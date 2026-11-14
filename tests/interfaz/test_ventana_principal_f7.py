"""VentanaPrincipal (ronda F7): envío incierto, reanudación con la sesión actual, excepciones
inesperadas, botones de red durante el trabajo, cierre de sesión y avisos de archivos dañados."""

from __future__ import annotations

import json
import threading

import pytest
from PySide6.QtWidgets import QMessageBox

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace

from . import test_ventana_principal as _base
from .apoyo import UPID, CreacionFalsa, perfil, resultado, sesion_falsa
from .test_ventana_principal import _textos_avisos, conectar, crear_y_esperar, poner_nombre

# Se reutiliza el fixture de ensamblado de la ventana (con sus dobles) sin copiarlo.
entorno = _base.entorno


def _incierto():
    """Resultado de un envío del que no sabemos si llegó: sin UPID."""
    return resultado(
        Desenlace.CONEXION_PERDIDA,
        error=ErrorProxLaunch(
            CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.5", "incierto": "1"}, "ReadTimeout"
        ),
        upid=None,
    )


def _crear_incierto(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion = CreacionFalsa(_incierto(), enviar_upid=False)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    return v


def _comprobar_y_esperar(qtbot, v):
    v.progreso.boton_comprobar.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)


# --- 9. Envío incierto -------------------------------------------------------------------------


def test_envio_incierto_explica_que_no_se_sabe_si_proxmox_recibio_la_orden(qtbot, entorno):
    v = _crear_incierto(qtbot, entorno)
    # El motor reconcilia con existe_vm (0/+5/+15 s); si no puede saberlo, muestra E-L06.
    assert "No pudimos comprobar si «srv-web-01» existe" in v.progreso.texto_mensaje
    assert "antes de crearla otra vez" in v.progreso.texto_mensaje
    assert v.progreso.texto_upid == ""
    assert v.progreso.boton_comprobar.isVisible()
    assert v.progreso.boton_comprobar.text() == "Comprobar"
    assert not v.formulario.isEnabled()


def test_comprobar_con_envio_incierto_y_maquina_existente_es_ok_con_aviso_y_crear_otra(
    qtbot, entorno
):
    v = _crear_incierto(qtbot, entorno)
    antes = len(entorno.creacion.llamadas_existe_vm)  # las de la reconciliación del motor
    entorno.creacion.respuesta_existe_vm = True
    _comprobar_y_esperar(qtbot, v)
    assert len(entorno.creacion.llamadas_existe_vm) == antes + 1
    assert v._ultimo_resultado.desenlace == Desenlace.OK
    assert "sí se creó" in v.progreso.texto_mensaje
    assert "Verifica" in v.progreso.texto_mensaje
    assert v.progreso.boton_crear_otra.isVisible()


def test_comprobar_con_envio_incierto_y_maquina_inexistente_desbloquea_el_formulario(
    qtbot, entorno
):
    v = _crear_incierto(qtbot, entorno)
    entorno.creacion.respuesta_existe_vm = False
    _comprobar_y_esperar(qtbot, v)
    assert "No se creó" in v.progreso.texto_mensaje
    assert v.formulario.isEnabled()
    assert v._ultimo_resultado.desenlace == Desenlace.CANCELADO


def test_comprobar_con_envio_incierto_sin_poder_saber_mantiene_el_estado_y_avisa(qtbot, entorno):
    v = _crear_incierto(qtbot, entorno)
    entorno.creacion.respuesta_existe_vm = None
    _comprobar_y_esperar(qtbot, v)
    assert "No se pudo comprobar" in v.progreso.texto_mensaje
    assert not v.formulario.isEnabled()
    assert v._ultimo_resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert v.progreso.boton_comprobar.isVisible()


def test_comprobar_con_envio_incierto_nunca_vuelve_a_crear_ni_sigue_una_tarea(qtbot, entorno):
    v = _crear_incierto(qtbot, entorno)
    antes = len(entorno.creacion.llamadas_existe_vm)  # las de la reconciliación del motor
    entorno.creacion.respuesta_existe_vm = None
    _comprobar_y_esperar(qtbot, v)
    _comprobar_y_esperar(qtbot, v)
    assert entorno.creacion.llamadas_crear == 1
    assert entorno.creacion.llamadas_reanudar == []
    assert len(entorno.creacion.llamadas_existe_vm) == antes + 2


def test_excepcion_al_comprobar_la_existencia_no_desbloquea(qtbot, entorno):
    v = _crear_incierto(qtbot, entorno)
    entorno.creacion.respuesta_existe_vm = RuntimeError("fallo")
    _comprobar_y_esperar(qtbot, v)
    assert not v.formulario.isEnabled()
    assert v._ultimo_resultado.desenlace == Desenlace.CONEXION_PERDIDA


@pytest.mark.parametrize("desenlace", [Desenlace.CONEXION_PERDIDA, Desenlace.TIEMPO_AGOTADO])
def test_volver_al_formulario_pide_confirmacion_con_no_por_defecto(
    qtbot, entorno, monkeypatch, desenlace
):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(desenlace)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    llamadas = []

    def pregunta(padre, titulo, texto, botones=None, por_defecto=None):
        llamadas.append(por_defecto)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", pregunta)
    v.progreso.boton_volver.click()
    assert llamadas == [QMessageBox.StandardButton.No]
    assert not v.formulario.isEnabled()  # respondió «No»: sigue bloqueado


def test_volver_al_formulario_confirmado_desbloquea(qtbot, entorno, monkeypatch):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.CONEXION_PERDIDA)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    v.progreso.boton_volver.click()
    assert v.formulario.isEnabled()


def test_volver_al_formulario_tras_un_error_no_pide_confirmacion(qtbot, entorno, monkeypatch):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(
        Desenlace.ERROR, error=ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO)
    )
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("no debe preguntar"))
    v._volver_al_formulario()
    assert v.formulario.isEnabled()


# --- 10. Sesión actual al reanudar; limpieza al cambiar de perfil ------------------------------


def test_reanudar_usa_la_sesion_actual_y_no_la_de_la_creacion(qtbot, entorno):
    v = entorno.ventana
    sesiones = []

    def fabrica(sesion):
        sesiones.append(sesion)
        return entorno.creacion

    entorno.deps.fabrica_creacion = fabrica
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    entorno.creacion.respuestas_reanudar = [resultado(Desenlace.TIEMPO_AGOTADO)]
    primera = conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    nueva = sesion_falsa()  # reconexión del mismo perfil: sesión distinta
    conectar(qtbot, entorno, nueva)
    v.progreso.boton_comprobar.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert sesiones[0] is primera
    assert sesiones[-1] is nueva and nueva is not primera


def test_reanudar_pasa_el_inventario_al_servicio(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    entorno.creacion.respuestas_reanudar = [resultado(Desenlace.TIEMPO_AGOTADO)] * 2
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    v.progreso.boton_comprobar.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    v.progreso.boton_seguir.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert entorno.creacion.inventarios_reanudar == [entorno.inv, entorno.inv]


def test_cambiar_de_perfil_limpia_el_resultado_previo(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert v._ultimo_resultado is not None
    conectar(qtbot, entorno, sesion_falsa(perfil("otro", "Otro", ("10.0.0.9",))))
    assert v._ultimo_resultado is None
    assert v.progreso.texto_mensaje == ""
    assert v.progreso.texto_upid == ""
    assert not v.progreso.boton_seguir.isVisible()
    assert v.formulario.isEnabled()
    v._reanudar(una_vez=True)  # nada que retomar de otro servidor
    assert entorno.creacion.llamadas_reanudar == []


def test_reconectar_el_mismo_perfil_conserva_el_resultado_pendiente(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    conectar(qtbot, entorno)
    assert v._ultimo_resultado.desenlace == Desenlace.TIEMPO_AGOTADO


# --- 11. Excepción inesperada del servicio al crear --------------------------------------------


def test_excepcion_inesperada_tras_recibir_el_upid_conserva_upid_y_no_desbloquea(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion = CreacionFalsa(RuntimeError("boom"), enviar_upid=True)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert v._ultimo_resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert v._ultimo_resultado.upid == UPID
    assert v.progreso.texto_upid == UPID
    assert not v.formulario.isEnabled()
    assert v.progreso.boton_comprobar.isVisible()


def test_excepcion_inesperada_sin_upid_tampoco_desbloquea(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion = CreacionFalsa(RuntimeError("boom"), enviar_upid=False)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert v._ultimo_resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert v._ultimo_resultado.upid is None
    assert not v.formulario.isEnabled()


# --- 12. «Actualizar» y «Reintentar» durante el trabajo ----------------------------------------


class _CreacionBloqueada(CreacionFalsa):
    """Creación que espera a que la prueba la libere (sin dormir)."""

    def crear(self, cfg, inv, al_cambiar_etapa, cancelado, *, al_enviar=None):
        self.entro = threading.Event()
        self.entro.set()
        assert self.liberar.wait(5)
        return super().crear(cfg, inv, al_cambiar_etapa, cancelado, al_enviar=al_enviar)


def test_actualizar_y_reintentar_estan_deshabilitados_mientras_se_crea(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion = _CreacionBloqueada(resultado(Desenlace.OK))
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    assert v.boton_actualizar.isEnabled()
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: v._creando, timeout=2000)
    assert not v.boton_actualizar.isEnabled()
    assert not v.boton_reintentar.isEnabled()
    entorno.creacion.liberar.set()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert v.boton_actualizar.isEnabled()
    assert v.boton_reintentar.isEnabled()


def test_actualizar_y_reintentar_estan_deshabilitados_mientras_se_descubre(
    qtbot, entorno, monkeypatch
):
    v = entorno.ventana
    conectar(qtbot, entorno)
    liberar = threading.Event()

    def lento(sesion):
        assert liberar.wait(5)
        return entorno.inv, None

    monkeypatch.setattr(vp, "descubrir_y_comprobar_permisos", lento)
    v.boton_actualizar.click()
    qtbot.waitUntil(lambda: v._descubriendo, timeout=2000)
    assert not v.boton_actualizar.isEnabled()
    assert not v.boton_reintentar.isEnabled()
    liberar.set()
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    assert v.boton_actualizar.isEnabled()


# --- 14. Cerrar sesión y cierre de la ventana ---------------------------------------------------


def test_cerrar_sesion_llama_al_servicio_con_la_sesion_actual(qtbot, entorno, servicio_falso):
    v = entorno.ventana
    sesion = conectar(qtbot, entorno)
    v._cerrar_sesion()
    assert ("cerrar_sesion", sesion) in servicio_falso.llamadas
    assert v._sesion is None


def test_cerrar_sesion_sigue_adelante_si_el_servicio_falla_con_error_de_proxlaunch(
    qtbot, entorno, servicio_falso
):
    servicio_falso.error_cerrar_sesion = ErrorProxLaunch(CodigoError.DESCONOCIDO)
    v = entorno.ventana
    conectar(qtbot, entorno)
    v._cerrar_sesion()
    assert v._sesion is None
    assert v._paginas.currentIndex() == 0


def test_closeevent_cierra_la_sesion_del_servicio(qtbot, entorno, servicio_falso):
    sesion = conectar(qtbot, entorno)
    assert entorno.ventana.close() is True
    assert ("cerrar_sesion", sesion) in servicio_falso.llamadas


def test_closeevent_no_falla_aunque_cerrar_sesion_lance(qtbot, entorno, servicio_falso):
    servicio_falso.error_cerrar_sesion = RuntimeError("el transporte ya estaba roto")
    conectar(qtbot, entorno)
    assert entorno.ventana.close() is True


def test_closeevent_sin_sesion_no_llama_a_cerrar_sesion(qtbot, entorno, servicio_falso):
    assert entorno.ventana.close() is True
    assert not any(ll[0] == "cerrar_sesion" for ll in servicio_falso.llamadas)


# --- 13. Avisos de archivos de huellas ----------------------------------------------------------

HUELLA = ":".join(["AB"] * 32)


def test_aviso_de_huellas_recuperadas_cuenta_los_servidores(qtbot, entorno, rutas):
    rutas.huellas.parent.mkdir(parents=True, exist_ok=True)
    rutas.huellas.write_text(f'{{"huellas": {{"10.0.0.1:8006": "{HUELLA}", "x', encoding="utf-8")
    entorno.deps.huellas.obtener("10.0.0.1", 8006)  # la lectura detecta el daño y recupera
    conectar(qtbot, entorno)
    textos = _textos_avisos(entorno.ventana)
    assert any("archivo de huellas" in t and "recuperaron 1" in t for t in textos)


def test_aviso_de_error_de_lectura_del_archivo_de_huellas(qtbot, entorno, rutas):
    rutas.huellas.mkdir(parents=True)  # una carpeta en lugar del archivo: no se puede leer
    entorno.deps.huellas.obtener("10.0.0.1", 8006)
    conectar(qtbot, entorno)
    textos = _textos_avisos(entorno.ventana)
    assert any("No se pudo leer el archivo de huellas" in t for t in textos)
    assert not any("recuperaron" in t for t in textos)


def test_sin_dano_en_las_huellas_no_hay_aviso(qtbot, entorno):
    conectar(qtbot, entorno)
    assert not any("huellas" in t for t in _textos_avisos(entorno.ventana))


def test_json_del_archivo_de_huellas_sano_no_marca_dano(qtbot, entorno, rutas):
    rutas.huellas.parent.mkdir(parents=True, exist_ok=True)
    rutas.huellas.write_text(json.dumps({"huellas": {"10.0.0.1:8006": HUELLA}}), encoding="utf-8")
    entorno.deps.huellas.obtener("10.0.0.1", 8006)
    conectar(qtbot, entorno)
    assert not any("huellas" in t for t in _textos_avisos(entorno.ventana))
