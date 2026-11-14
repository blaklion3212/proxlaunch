"""Una sola máquina: ahora pasa por el motor de lotes y conserva el comportamiento de M1.

Cubre las decisiones del orquestador sobre el envío incierto de una máquina: reconciliación con
``existe_vm`` (0, +5 y +15 s), «No se creó; puedes intentarlo de nuevo.», el caso «existe sin
confirmar propiedad», la cancelación de la espera y la sincronización del libro tras «Comprobar».
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from proxlaunch.interfaz.textos import texto_existe_sin_confirmar
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.modelos.tarea import Desenlace

from . import test_ventana_principal as _base
from .apoyo import ClienteLoteFalso, CreacionFalsa, resultado, sesion_falsa
from .apoyo_lote import RelojBloqueable
from .test_ventana_principal import conectar, crear_y_esperar, poner_nombre
from .test_ventana_principal_f7 import _comprobar_y_esperar, _incierto

entorno = _base.entorno
EM = EstadoMV


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Todas las pruebas de este módulo cierran sin bloquear."""


def crear_incierto(qtbot, entorno, *, existe=None, cliente=None):
    """Una máquina con envío incierto (sin UPID); ``existe`` es lo que dirá ``existe_vm``."""
    v = entorno.ventana
    cliente = cliente or ClienteLoteFalso()
    entorno.cliente = cliente
    entorno.creacion = CreacionFalsa(_incierto(), enviar_upid=False)
    entorno.creacion.respuesta_existe_vm = existe
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente))
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    return v


def entrada_unica(v):
    return v._lote.libro.instantanea()[0]


# --- Una máquina por el motor (CA-L04.1, CA-L18.13, CA-L24.1) ---------------------------------


def test_una_maquina_usa_el_motor_con_etiquetas_y_deja_su_libro(qtbot, entorno):
    v = entorno.ventana
    cliente = ClienteLoteFalso()
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente))
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert v._lote.modo_uno and v._lote.libro is not None
    assert v._pila_derecha.currentIndex() == 0  # la vista de una máquina es la de M1
    cfg = entorno.creacion.cfgs_recibidas[0]
    assert cfg.etiquetas == ("proxlaunch", f"lote-{v._lote.plan.id_lote}")
    assert entrada_unica(v).estado == EM.OK
    assert v._accion_ultimo_lote.isEnabled()


def test_ca_l04_1_la_peticion_de_una_maquina_es_la_del_formulario_salvo_las_etiquetas(
    qtbot, entorno
):
    import dataclasses

    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    esperado = v.formulario.configuracion()
    crear_y_esperar(qtbot, v)
    enviada = entorno.creacion.cfgs_recibidas[0]
    assert dataclasses.replace(enviada, etiquetas=()).a_dict() == esperado.a_dict()


def test_ca_l24_5_una_maquina_sin_etiquetar_no_envia_etiquetas(qtbot, entorno):
    from proxlaunch.nucleo.persistencia.preferencias import Modo

    v = entorno.ventana
    conectar(qtbot, entorno)
    v.establecer_modo(Modo.AVANZADO)
    v.bloque_lote.chk_etiquetar.setChecked(False)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert entorno.creacion.cfgs_recibidas[0].etiquetas == ()


def test_con_una_maquina_el_boton_principal_no_pasa_por_el_resumen(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    assert v.resumen.boton_crear.text() == "Crear máquina"
    v.resumen.boton_crear.click()
    assert v.resumen_lote.plan is None


# --- (a) Envío incierto: el motor reconcilia con existe_vm ----------------------------------------


def test_a_la_reconciliacion_consulta_existe_vm_una_vez_y_si_no_sabe_muestra_e_l06(qtbot, entorno):
    v = crear_incierto(qtbot, entorno, existe=None)
    assert len(entorno.creacion.llamadas_existe_vm) == 1  # t = 0; con None no sigue esperando
    assert "No pudimos comprobar si «srv-web-01» existe" in v.progreso.texto_mensaje
    assert entorno.creacion.llamadas_crear == 1
    assert v.progreso.boton_comprobar.isVisible() and not v.formulario.isEnabled()
    assert entrada_unica(v).estado == EM.CONEXION_PERDIDA


# --- (b) NO_CREADA_SEGURA -------------------------------------------------------------------------


def test_b_si_no_existe_en_tres_comprobaciones_se_dice_que_no_se_creo_y_se_puede_reintentar(
    qtbot, entorno
):
    reloj = RelojBloqueable()
    entorno.deps.reloj = reloj
    v = crear_incierto(qtbot, entorno, existe=False)
    assert len(entorno.creacion.llamadas_existe_vm) == 3  # t = 0, +5 s y +15 s
    assert sum(reloj.dormidas) == pytest.approx(15.0)  # tiempo simulado: nada se durmió de verdad
    assert v.progreso.texto_mensaje == "No se creó; puedes intentarlo de nuevo."
    assert not v.progreso._mensaje.property("error")
    assert v.formulario.isEnabled() and v.bloque_lote.isEnabled()
    assert v._ultimo_resultado.desenlace == Desenlace.CANCELADO
    assert entrada_unica(v).estado == EM.NO_CREADA_SEGURA
    assert entorno.creacion.llamadas_crear == 1  # nunca se reenvía sola
    assert v.progreso.boton_volver.isVisible() and not v.progreso.boton_comprobar.isVisible()


def test_b_tras_no_creada_segura_se_puede_volver_a_crear_con_una_nueva_peticion(qtbot, entorno):
    v = crear_incierto(qtbot, entorno, existe=False)
    entorno.creacion = CreacionFalsa(resultado(Desenlace.OK))
    v.progreso.boton_volver.click()
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert entorno.creacion.llamadas_crear == 1  # la 2.ª petición es una acción explícita
    assert entrada_unica(v).estado == EM.OK


# --- Existe_vm True/False en la reconciliación ----------------------------------------------------


def existe_con_etiqueta_del_lote(qtbot, entorno):
    """Envío incierto tras el cual la MV existe y lleva las etiquetas que se le pidieron."""
    v = entorno.ventana
    cliente = ClienteLoteFalso()
    entorno.cliente = cliente
    entorno.creacion = CreacionFalsa(_incierto(), enviar_upid=False)
    entorno.creacion.respuesta_existe_vm = True
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente))
    poner_nombre(qtbot, v)
    original = entorno.creacion.crear

    def crear_y_etiquetar(
        cfg, inv, al_cambiar_etapa, cancelado, *, al_enviar=None, puede_enviar=None
    ):
        # Proxmox sí recibió la orden: la MV existe con la etiqueta del lote.
        cliente.configs[cfg.vmid] = {"name": cfg.nombre, "tags": ";".join(cfg.etiquetas)}
        return original(
            cfg, inv, al_cambiar_etapa, cancelado, al_enviar=al_enviar, puede_enviar=puede_enviar
        )

    entorno.creacion.crear = crear_y_etiquetar
    crear_y_esperar(qtbot, v)
    return v


def test_si_la_maquina_existe_con_la_etiqueta_del_lote_se_da_por_creada(qtbot, entorno):
    v = existe_con_etiqueta_del_lote(qtbot, entorno)
    assert v._ultimo_resultado.desenlace == Desenlace.OK
    assert entrada_unica(v).estado == EM.OK and "creada_tras_comprobar" in entrada_unica(v).avisos
    assert len(entorno.creacion.llamadas_existe_vm) == 1
    assert entorno.creacion.llamadas_crear == 1
    assert v.progreso.boton_crear_otra.isVisible() and v.progreso.boton_deshacer.isVisible()


def test_ca_l15_2_si_existe_se_avisa_de_que_proxmox_tardo_en_responder(qtbot, entorno):
    """«existe → ok con aviso "se creó aunque Proxmox tardó en responder"» (también con una)."""
    v = existe_con_etiqueta_del_lote(qtbot, entorno)
    assert "tardó en responder" in v.progreso.texto_mensaje


# --- (c) EXISTE_SIN_CONFIRMAR_PROPIEDAD -----------------------------------------------------------


def test_c_si_existe_pero_no_se_puede_demostrar_que_es_nuestra_solo_se_ofrece_volver(
    qtbot, entorno
):
    cliente = ClienteLoteFalso()
    cliente.configs[101] = {"name": "srv-web-01", "tags": "de-otra-persona"}
    v = crear_incierto(qtbot, entorno, existe=True, cliente=cliente)
    assert entrada_unica(v).estado == EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD
    assert v.progreso.texto_mensaje == texto_existe_sin_confirmar()
    p = v.progreso
    assert p.boton_volver.isVisible()
    assert not p.boton_comprobar.isVisible() and not p.boton_crear_otra.isVisible()
    assert not p.boton_seguir.isVisible() and not p.boton_deshacer.isVisible()
    assert not v.formulario.isEnabled()
    assert entorno.creacion.llamadas_crear == 1


def test_c_una_maquina_existe_sin_confirmar_no_es_elegible_para_deshacer(qtbot, entorno):
    cliente = ClienteLoteFalso()
    cliente.configs[101] = {"name": "srv-web-01", "tags": "de-otra-persona"}
    v = crear_incierto(qtbot, entorno, existe=True, cliente=cliente)
    candidatos = ServicioRollback(v._sesion, v._deps.reloj).elegibles(
        v._lote.libro, etiquetado=True
    )
    assert [c.elegible for c in candidatos] == [False]


def test_c_con_la_config_ilegible_tampoco_se_da_por_propia(qtbot, entorno):
    v = crear_incierto(qtbot, entorno, existe=True, cliente=None)
    # El cliente falso devuelve ``None`` para un VMID desconocido: la MV «existe» según
    # existe_vm pero su etiqueta no puede leerse, así que la propiedad no está demostrada.
    assert entrada_unica(v).estado == EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD


# --- (d) Cancelar corta la espera de la reconciliación --------------------------------------------


def test_d_cerrar_la_aplicacion_durante_la_reconciliacion_sin_upid_corta_la_espera(
    qtbot, entorno, monkeypatch
):
    reloj = RelojBloqueable()
    entorno.deps.reloj = reloj
    reloj.bloquear = True
    v = entorno.ventana
    entorno.creacion = CreacionFalsa(_incierto(), enviar_upid=False)
    entorno.creacion.respuesta_existe_vm = False  # seguiría comprobando a +5 s y +15 s
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    assert reloj.dentro.wait(5)  # esperando los +5 s (tiempo simulado retenido)
    assert len(entorno.creacion.llamadas_existe_vm) == 1

    def pregunta(*a, **k):
        reloj.bloquear = False
        reloj.liberar.set()  # la espera retenida termina; ya hay orden de abandonar
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", pregunta)
    assert v.close() is True
    assert len(entorno.creacion.llamadas_existe_vm) == 1  # no hubo +5 s ni +15 s
    assert entorno.creacion.llamadas_crear == 1  # y nunca se reenvió


# --- (e) El libro se sincroniza tras «Comprobar» --------------------------------------------------


def test_e_comprobar_con_existe_true_pasa_la_entrada_del_libro_a_ok(qtbot, entorno):
    v = crear_incierto(qtbot, entorno, existe=None)
    assert entrada_unica(v).estado == EM.CONEXION_PERDIDA
    # La MV existe y lleva la etiqueta de este lote (propiedad demostrada).
    entorno.cliente.configs[101] = {
        "name": "srv-web-01",
        "tags": f"proxlaunch;lote-{v._lote.plan.id_lote}",
    }
    entorno.creacion.respuesta_existe_vm = True
    _comprobar_y_esperar(qtbot, v)
    assert entrada_unica(v).estado == EM.OK
    informe = v._informe_actual()
    assert informe.contadores["ok"] == 1 and informe.contadores["conexion_perdida"] == 0
    assert v.progreso.boton_deshacer.isVisible()
    assert [c.elegible for c in ServicioRollback(v._sesion, v._deps.reloj).elegibles(
        v._lote.libro, etiquetado=True)] == [True]  # fmt: skip


def test_e_comprobar_con_existe_false_pasa_la_entrada_a_no_creada_segura(qtbot, entorno):
    v = crear_incierto(qtbot, entorno, existe=None)
    entorno.creacion.respuesta_existe_vm = False
    _comprobar_y_esperar(qtbot, v)
    assert entrada_unica(v).estado == EM.NO_CREADA_SEGURA
    informe = v._informe_actual()
    assert informe.contadores["no_creada_segura"] == 1
    assert v._lote.puente.instantanea()[0].estado == EM.NO_CREADA_SEGURA
    assert "No se creó; puedes intentarlo de nuevo." in v.progreso.texto_mensaje


def test_e_comprobar_sin_poder_saber_deja_la_entrada_dudosa(qtbot, entorno):
    v = crear_incierto(qtbot, entorno, existe=None)
    _comprobar_y_esperar(qtbot, v)
    assert entrada_unica(v).estado == EM.CONEXION_PERDIDA
    assert v._informe_actual().contadores["conexion_perdida"] == 1


def test_ca_l15_5_comprobar_con_una_maquina_ajena_no_la_da_por_propia(qtbot, entorno):
    """Si «Comprobar» halla una MV con ese VMID pero sin la etiqueta del lote, no es elegible
    para deshacer (podría ser de otra persona que ganó la carrera por ese número)."""
    cliente = ClienteLoteFalso()
    v = crear_incierto(qtbot, entorno, existe=None, cliente=cliente)
    cliente.configs[101] = {"name": "srv-web-01", "tags": "de-otra-persona"}
    entorno.creacion.respuesta_existe_vm = True
    _comprobar_y_esperar(qtbot, v)
    assert entrada_unica(v).estado == EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD
    assert not v.progreso.boton_deshacer.isVisible()


def test_e_tras_comprobar_se_puede_informar_con_el_estado_actualizado(qtbot, entorno):
    from proxlaunch.interfaz.informe_lote import texto_informe

    v = crear_incierto(qtbot, entorno, existe=None)
    antes = texto_informe(v._informe_actual())
    assert "Sin confirmar (no sabemos si se crearon): 1" in antes
    entorno.creacion.respuesta_existe_vm = False
    _comprobar_y_esperar(qtbot, v)
    despues = texto_informe(v._informe_actual())
    assert "Sin confirmar (no sabemos si se crearon): 0" in despues
    assert "No enviadas: 1" in despues  # «no se creó» cuenta junto a las no enviadas


# --- Resultados normales de una máquina (equivalencia con M1) -------------------------------------


def test_un_error_de_la_tarea_desbloquea_el_formulario_como_en_m1(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion = CreacionFalsa(
        resultado(
            Desenlace.ERROR,
            error=ErrorProxLaunch(CodigoError.SIN_ESPACIO, {"storage": "local-lvm"}),
        )
    )
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert "No hay espacio suficiente" in v.progreso.texto_mensaje
    assert v.formulario.isEnabled()
    assert entrada_unica(v).estado == EM.ERROR and entorno.creacion.llamadas_crear == 1


def test_una_maquina_con_conexion_perdida_y_upid_se_comprueba_con_la_tarea_no_con_existe_vm(
    qtbot, entorno
):
    v = entorno.ventana
    entorno.creacion = CreacionFalsa(resultado(Desenlace.CONEXION_PERDIDA))
    entorno.creacion.respuestas_reanudar = [resultado(Desenlace.OK)]
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert entorno.creacion.llamadas_existe_vm == []  # con UPID no se reconcilia por existencia
    v.progreso.boton_comprobar.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert entorno.creacion.llamadas_reanudar == ["comprobar"]
    assert entrada_unica(v).estado == EM.OK  # el libro se sincronizó también aquí
