"""Ejecución de un lote en la ventana: errores por máquina, pausas, cancelación, comprobación,
deshacer, reintento, informe y cierre (RF-L14 a RF-L23)."""

from __future__ import annotations

import threading
from collections import Counter

import pytest

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.pausa_lote import AccionPausa, DialogoPausaLote
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV, MotivoPausa

from . import test_ventana_principal as _base
from .apoyo import ClienteLoteFalso, CreacionPorVmid, sesion_falsa, upid_de
from .apoyo_lote import error_nodo_caido, res_error, res_perdida
from .apoyo_ventana_lote import (
    crear_lote,
    esperar_fin,
    esperar_pausa,
    estados,
    preparar_lote,
    ver_resumen,
)
from .test_ventana_principal import conectar

entorno = _base.entorno
EM = EstadoMV


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Todas las pruebas de este módulo cierran sin bloquear."""


def err(codigo, **params):
    return ErrorProxLaunch(codigo, {k: str(v) for k, v in params.items()}, "texto original")


def fallo(vmid, codigo=CodigoError.SIN_ESPACIO, **params):
    return res_error(vmid, codigo, **{k: str(v) for k, v in params.items()})


def conexion_perdida(vmid):
    return res_perdida(vmid)


def lanzar(qtbot, entorno, *, esperar=True, **kw):
    cliente = preparar_lote(qtbot, entorno, **kw)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    if esperar:
        esperar_fin(qtbot, v)
    return cliente


def dialogo_pausa(v) -> DialogoPausaLote:
    return v._lote.dialogo_pausa


# --- Errores que no detienen el lote (RF-L14) -----------------------------------------------


def test_ca_l14_1_un_fallo_en_la_segunda_no_detiene_a_las_demas(qtbot, entorno):
    creacion = CreacionPorVmid({102: fallo(102, storage="local-lvm")})
    lanzar(qtbot, entorno, cantidad=5, creacion=creacion)
    v = entorno.ventana
    assert estados(v) == ["ok", "error", "ok", "ok", "ok"]
    assert creacion.llamadas_crear == 5
    p = v.progreso_lote
    assert p.texto_resumen_barra == "5 de 5 terminadas · 1 con error"
    fila = [p.modelo.data(p.modelo.index(1, c)) for c in range(5)]
    assert fila[0] == "✕ Con error" and "No hay espacio suficiente" in fila[4]
    assert v._lote.dialogo_pausa is None  # un solo fallo no pausa


def test_ca_l14_6_el_mensaje_llano_y_el_original_conviven_en_los_detalles(qtbot, entorno):
    creacion = CreacionPorVmid({102: fallo(102, storage="local-lvm")})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion)
    p = entorno.ventana.progreso_lote
    p.tabla.selectRow(1)
    assert "texto original" in p.detalles.texto and "sin_espacio" in p.detalles.texto
    assert upid_de(102) in p.detalles.texto


def test_ca_l14_5_un_nodo_caido_deja_sin_enviar_solo_las_de_ese_nodo(qtbot, entorno):
    # El nodo caído lo decide el sondeo de su estado (595/596), antes de su primera máquina.
    cliente = ClienteLoteFalso()
    cliente.nodos_caidos["pve3"] = error_nodo_caido("pve3", 596)
    creacion = CreacionPorVmid()
    lanzar(qtbot, entorno, cantidad=6, nodo=None, creacion=creacion, cliente=cliente)
    v = entorno.ventana
    snap = v._lote.libro.instantanea()
    en_pve3 = [e for e in snap if e.elemento.nodo == "pve3"]
    en_pve1 = [e for e in snap if e.elemento.nodo == "pve1"]
    assert len(en_pve3) >= 2 and en_pve1
    assert all(e.estado == EM.OK for e in en_pve1)  # las de los demás nodos continúan
    assert all(e.estado == EM.NO_ENVIADA for e in en_pve3)
    assert all(e.vmid not in creacion.vmids_creados for e in (x.elemento for x in en_pve3))
    p = v.progreso_lote
    assert "el nodo no respondió" in p.modelo.data(p.modelo.index(snap.index(en_pve3[-1]), 4))


# --- Pausa por error global (CA-L14.2) -------------------------------------------------------


def test_ca_l14_2_un_error_global_pausa_tras_el_primero_y_muestra_el_dialogo(qtbot, entorno):
    creacion = CreacionPorVmid({101: fallo(101, CodigoError.SESION_EXPIRADA)})
    lanzar(qtbot, entorno, cantidad=4, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    d = dialogo_pausa(v)
    assert isinstance(d, DialogoPausaLote) and d.motivo == MotivoPausa.ERROR_GLOBAL
    assert AccionPausa.RECONECTAR in d.botones
    assert v.progreso_lote.fase == FaseLote.PAUSADO
    assert v.progreso_lote.boton_decidir.isVisible()
    assert creacion.llamadas_crear == 1  # no se envía ninguna más
    assert (
        "Tu sesión expiró"
        in d.findChildren(__import__("PySide6.QtWidgets").QtWidgets.QLabel)[1].text()
    )


def test_ca_l14_2_detener_tras_la_pausa_deja_el_resto_sin_enviar(qtbot, entorno):
    creacion = CreacionPorVmid({101: fallo(101, CodigoError.SESION_EXPIRADA)})
    lanzar(qtbot, entorno, cantidad=4, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    dialogo_pausa(v).botones[AccionPausa.DETENER].click()
    esperar_fin(qtbot, v)
    assert estados(v) == ["error", "no_enviada", "no_enviada", "no_enviada"]
    assert creacion.llamadas_crear == 1
    assert v.progreso_lote.fase == FaseLote.TERMINADO
    assert "se detuvo" in v.progreso_lote.modelo.data(v.progreso_lote.modelo.index(1, 4))


def test_ca_l14_4_reintentar_tras_la_pausa_reanuda_el_envio_de_las_demas(qtbot, entorno):
    creacion = CreacionPorVmid({101: fallo(101, CodigoError.SESION_EXPIRADA)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    dialogo_pausa(v).botones[AccionPausa.REINTENTAR].click()
    esperar_fin(qtbot, v)
    assert estados(v) == ["error", "ok", "ok"]
    assert Counter(creacion.vmids_creados) == {101: 1, 102: 1, 103: 1}  # INV-L1


def test_cerrar_el_dialogo_sin_decidir_deja_el_lote_pausado_y_decidir_lo_retoma(qtbot, entorno):
    creacion = CreacionPorVmid({101: fallo(101, CodigoError.SESION_EXPIRADA)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    dialogo_pausa(v).reject()
    qtbot.waitUntil(lambda: v._lote.dialogo_pausa is None, timeout=2000)
    assert v.progreso_lote.fase == FaseLote.PAUSADO and creacion.llamadas_crear == 1
    v.progreso_lote.boton_decidir.click()
    assert v._lote.dialogo_pausa is not None  # «Decidir qué hacer…» vuelve a abrirlo


def test_ca_l24_4_etiqueta_rechazada_ofrece_seguir_sin_etiquetas_y_arma_un_lote_nuevo(
    qtbot, entorno, confirmaciones
):
    creacion = CreacionPorVmid({101: fallo(101, CodigoError.ETIQUETA_RECHAZADA)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    d = dialogo_pausa(v)
    assert AccionPausa.SIN_ETIQUETAS in d.botones
    viejo = v.resumen_lote.plan
    d.botones[AccionPausa.SIN_ETIQUETAS].click()
    # Pide confirmar y explica la consecuencia para «Deshacer».
    qtbot.waitUntil(lambda: bool(confirmaciones.llamadas), timeout=2000)
    assert confirmaciones.llamadas[0][0] == "Seguir sin etiquetas"
    assert (
        "«Deshacer» solo podrá eliminar las máquinas que ProxLaunch confirme"
        in (confirmaciones.llamadas[0][1])
    )
    # No se crea nada hasta ver el resumen del lote nuevo, sin etiquetas.
    qtbot.waitUntil(
        lambda: v.resumen_lote.plan is not None and v.resumen_lote.plan is not viejo,
        timeout=5000,
    )
    plan = v.resumen_lote.plan
    assert plan.definicion.etiquetar is False
    assert all(not e.cfg.etiquetas for e in plan.elementos)
    assert [e.nombre for e in plan.elementos] == ["web-01", "web-02", "web-03"]
    assert creacion.llamadas_crear == 1  # solo la que falló; el resto espera al resumen


def test_sin_etiquetas_pero_sin_confirmar_no_cambia_nada(qtbot, entorno, confirmaciones):
    confirmaciones.respuesta = False
    creacion = CreacionPorVmid({101: fallo(101, CodigoError.ETIQUETA_RECHAZADA)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    dialogo_pausa(v).botones[AccionPausa.SIN_ETIQUETAS].click()
    qtbot.waitUntil(lambda: bool(confirmaciones.llamadas), timeout=2000)
    assert v._lote.control.cancelado.is_set() is False
    assert v.resumen_lote.plan is not None and v._pila_derecha.currentIndex() == 2


# --- Pausa por errores repetidos (CA-L14.3, CA-L14.4) -----------------------------------------


def test_ca_l14_3_tres_fallos_seguidos_por_la_misma_causa_pausan_con_pregunta(qtbot, entorno):
    creacion = CreacionPorVmid({vm: fallo(vm) for vm in (101, 102, 103)})
    lanzar(qtbot, entorno, cantidad=6, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    d = dialogo_pausa(v)
    assert d.motivo == MotivoPausa.REPETIDO
    assert set(d.botones) == {AccionPausa.CONTINUAR, AccionPausa.DETENER}
    assert creacion.llamadas_crear == 3


def test_ca_l14_4_continuar_reanuda_y_no_vuelve_a_preguntar_por_esa_causa(
    qtbot, entorno, monkeypatch
):
    creaciones = []
    original = vp.DialogoPausaLote

    class Espia(original):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            creaciones.append(self)

    monkeypatch.setattr(vp, "DialogoPausaLote", Espia)
    creacion = CreacionPorVmid({vm: fallo(vm) for vm in (101, 102, 103, 104, 105)})
    lanzar(qtbot, entorno, cantidad=6, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    dialogo_pausa(v).botones[AccionPausa.CONTINUAR].click()
    esperar_fin(qtbot, v)
    assert len(creaciones) == 1  # una sola pregunta aunque siguieron fallando por lo mismo
    assert estados(v) == ["error"] * 5 + ["ok"]


def test_ca_l14_4_detener_en_pausa_repetida_se_comporta_como_cancelar(qtbot, entorno):
    creacion = CreacionPorVmid({vm: fallo(vm) for vm in (101, 102, 103)})
    lanzar(qtbot, entorno, cantidad=6, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    dialogo_pausa(v).botones[AccionPausa.DETENER].click()
    esperar_fin(qtbot, v)
    assert estados(v) == ["error"] * 3 + ["no_enviada"] * 3
    assert creacion.llamadas_crear == 3


# --- Pausa por conexión y continuación (RF-L17) -----------------------------------------------


def test_ca_l17_2_una_perdida_de_conexion_pausa_y_dice_cuantas_estan_sin_confirmar(qtbot, entorno):
    creacion = CreacionPorVmid({101: conexion_perdida(101)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    d = dialogo_pausa(v)
    assert d.motivo == MotivoPausa.CONEXION
    assert set(d.botones) == {AccionPausa.COMPROBAR_Y_CONTINUAR, AccionPausa.DETENER}
    cuerpo = "\n".join(
        w.text() for w in d.findChildren(__import__("PySide6.QtWidgets").QtWidgets.QLabel)
    )
    assert "Se perdió la conexión. Hay 1 máquina sin confirmar." in cuerpo


def test_ca_l17_3_comprobar_y_continuar_comprueba_la_dudosa_y_envia_solo_las_pendientes(
    qtbot, entorno
):
    cliente = ClienteLoteFalso()
    creacion = CreacionPorVmid({101: conexion_perdida(101)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, cliente=cliente, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    cliente.configs[101] = {"name": "web-01", "tags": ""}  # la 1.ª sí llegó a crearse
    dialogo_pausa(v).botones[AccionPausa.COMPROBAR_Y_CONTINUAR].click()
    qtbot.waitUntil(lambda: v._lote.terminado and estados(v) == ["ok", "ok", "ok"], timeout=8000)
    # La 101 nunca se reenvió (INV-L1/INV-L3); la 102 y la 103 salieron una vez, por el motor.
    assert [int(p["vmid"]) for _, p in cliente.creados] == [102, 103]
    assert creacion.vmids_creados == [101]
    assert v.progreso_lote.fase == FaseLote.TERMINADO


def test_ca_l17_3_si_la_dudosa_no_se_resuelve_sigue_dudosa_y_no_se_reenvia(qtbot, entorno):
    from proxlaunch.nucleo.modelos.tarea import EstadoTarea

    cliente = ClienteLoteFalso()
    creacion = CreacionPorVmid({101: conexion_perdida(101)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, cliente=cliente, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    # La tarea sigue sin terminar: «comprobar_ahora» la deja como tiempo agotado (dudosa).
    cliente.estado_tarea = lambda nodo, upid: (
        EstadoTarea("running") if ":101:" in upid else EstadoTarea("stopped", "OK")
    )
    dialogo_pausa(v).botones[AccionPausa.COMPROBAR_Y_CONTINUAR].click()
    qtbot.waitUntil(lambda: v._lote.terminado and estados(v)[1:] == ["ok", "ok"], timeout=8000)
    assert estados(v)[0] in ("tiempo_agotado", "conexion_perdida")
    assert creacion.vmids_creados == [101]  # la dudosa jamás se reenvía
    assert [int(p["vmid"]) for _, p in cliente.creados] == [102, 103]  # las pendientes, una vez
    assert v.progreso_lote.boton_comprobar.isVisible()


def test_ca_l17_4_reconectar_al_mismo_perfil_continua_con_las_pendientes(
    qtbot, entorno, monkeypatch
):
    cliente = ClienteLoteFalso()
    creacion = CreacionPorVmid({101: fallo(101, CodigoError.SESION_EXPIRADA)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, cliente=cliente, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    pedidos = []

    def abrir(motivo=None):
        pedidos.append(motivo)
        v._dialogo_conexion = object()  # un diálogo «abierto» para el ciclo de reconexión

    monkeypatch.setattr(v, "abrir_conexion", abrir)
    dialogo_pausa(v).botones[AccionPausa.RECONECTAR].click()
    qtbot.waitUntil(lambda: bool(pedidos), timeout=5000)
    assert "Reconecta para continuar con el lote." in pedidos[0]
    assert v._lote.esperando_reconexion
    assert "Reconecta para continuar" in v.progreso_lote._aviso.text()
    # Reconecta (mismo perfil): se envían solo las dos pendientes; la fallida no se repite.
    v._dialogo_conexion = None
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente))
    qtbot.waitUntil(lambda: v._lote.terminado and estados(v)[1:] == ["ok", "ok"], timeout=8000)
    assert estados(v)[0] == "error"
    assert [int(p["vmid"]) for _, p in cliente.creados] == [102, 103]


def test_ca_l17_4_cerrar_el_dialogo_de_conexion_sin_reconectar_deja_el_lote_detenido(
    qtbot, entorno, monkeypatch
):
    creacion = CreacionPorVmid({101: fallo(101, CodigoError.SESION_EXPIRADA)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    monkeypatch.setattr(
        v, "abrir_conexion", lambda motivo=None: setattr(v, "_dialogo_conexion", object())
    )
    dialogo_pausa(v).botones[AccionPausa.RECONECTAR].click()
    qtbot.waitUntil(lambda: v._lote.esperando_reconexion, timeout=5000)

    class Cerrado:
        def deleteLater(self):
            pass

    v._dialogo_cerrado(Cerrado())
    assert not v._lote.esperando_reconexion and v._lote.terminado
    assert v.progreso_lote.fase == FaseLote.TERMINADO


def test_ca_l17_4_con_otro_perfil_el_lote_anterior_queda_cerrado_y_sin_acciones(qtbot, entorno):
    from .apoyo import perfil

    lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    assert v._lote is not None and v._accion_ultimo_lote.isEnabled()
    conectar(qtbot, entorno, sesion_falsa(perfil("otro", "Otro", ("10.0.0.9",))))
    assert v._lote is None and not v._accion_ultimo_lote.isEnabled()
    assert v._pila_derecha.currentIndex() == 0
    v._deshacer()  # CA-L18.14: contra el servidor nuevo no hay nada que deshacer
    assert not v.findChildren(DialogoDeshacer)


# --- Cancelación (RF-L16) -------------------------------------------------------------------


def en_vuelo(qtbot, entorno, cantidad=4, **kw):
    """Lote con la 101 «en vuelo» (UPID anunciado, sin terminar) hasta liberar su puerta."""
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    lanzar(qtbot, entorno, cantidad=cantidad, creacion=creacion, esperar=False, **kw)
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)
    qtbot.waitUntil(
        lambda: entorno.ventana._lote.puente.instantanea()[0].upid is not None, timeout=2000
    )
    # El panel se refresca con el temporizador de 100 ms: se espera a que ya vea la enviada.
    qtbot.waitUntil(lambda: entorno.ventana.progreso_lote.hay_enviadas(), timeout=2000)
    return creacion, puerta


def test_ca_l16_1_cancelar_con_una_enviada_pide_confirmar_y_las_pendientes_no_se_envian(
    qtbot, entorno, confirmaciones
):
    creacion, puerta = en_vuelo(qtbot, entorno)
    v = entorno.ventana
    v.progreso_lote.boton_cancelar.click()
    assert len(confirmaciones.llamadas) == 1
    titulo, texto, aceptar, cancelar = confirmaciones.llamadas[0]
    assert (aceptar, cancelar) == ("Cancelar el lote", "Seguir creando")
    assert "seguirán creándose en Proxmox" in texto
    assert v.progreso_lote.fase == FaseLote.CANCELANDO
    assert v.progreso_lote.boton_cancelar.text() == "Dejar de esperar"  # CA-L16.2
    puerta.set()
    esperar_fin(qtbot, v)
    assert estados(v) == ["ok", "no_enviada", "no_enviada", "no_enviada"]
    assert creacion.vmids_creados == [101]  # nada más salió


def test_ca_l16_3_tras_cancelar_se_ofrece_deshacer_lo_ya_creado(qtbot, entorno, confirmaciones):
    creacion, puerta = en_vuelo(qtbot, entorno)
    v = entorno.ventana
    v.progreso_lote.boton_cancelar.click()
    puerta.set()
    esperar_fin(qtbot, v)
    assert v.progreso_lote.boton_deshacer.isVisible() and v.progreso_lote.boton_deshacer.isEnabled()
    assert v.progreso_lote.boton_reintentar.isVisible()  # las 3 sin enviar se pueden reintentar


def test_ca_l16_1_seguir_creando_no_cancela_nada(qtbot, entorno, confirmaciones):
    confirmaciones.respuesta = False
    creacion, puerta = en_vuelo(qtbot, entorno)
    v = entorno.ventana
    v.progreso_lote.boton_cancelar.click()
    assert v.progreso_lote.fase == FaseLote.EJECUTANDO
    assert not v._lote.control.cancelado.is_set() and not v._lote.cancelando
    puerta.set()
    esperar_fin(qtbot, v)
    assert estados(v) == ["ok"] * 4


def test_ca_l16_2_dejar_de_esperar_deja_la_enviada_como_dudosa_con_su_upid(
    qtbot, entorno, confirmaciones
):
    creacion, puerta = en_vuelo(qtbot, entorno)
    v = entorno.ventana
    v.progreso_lote.boton_cancelar.click()  # cancelar
    v.progreso_lote.boton_cancelar.click()  # ahora es «Dejar de esperar»
    esperar_fin(qtbot, v)
    primera = v._lote.libro.instantanea()[0]
    assert primera.estado == EM.CONEXION_PERDIDA and primera.upid == upid_de(101)
    assert estados(v)[1:] == ["no_enviada"] * 3
    assert v.progreso_lote.boton_comprobar.isVisible()
    assert v.progreso_lote.boton_comprobar.text() == "Comprobar la dudosa"
    # No se detiene ninguna tarea en Proxmox: el cliente nunca recibió un DELETE.
    assert entorno.cliente.eliminados == []


def test_doble_clic_en_cancelar_pregunta_una_sola_vez(qtbot, entorno, confirmaciones):
    creacion, puerta = en_vuelo(qtbot, entorno)
    v = entorno.ventana
    v._cancelar_lote()
    v._cancelar_lote()  # ya está cancelando: no vuelve a preguntar ni a cancelar
    assert len(confirmaciones.llamadas) == 1
    puerta.set()


def test_ca_l16_4_cancelar_a_mitad_del_envio_nunca_marca_la_maquina_como_no_enviada(
    qtbot, entorno, confirmaciones
):
    """La que ya salió hacia Proxmox es incierta o creada, jamás «no enviada» (INV-L1)."""
    creacion, puerta = en_vuelo(qtbot, entorno)
    v = entorno.ventana
    v.progreso_lote.boton_cancelar.click()
    v.progreso_lote.boton_cancelar.click()
    esperar_fin(qtbot, v)
    primera = v._lote.libro.instantanea()[0]
    assert primera.post_intentado and primera.estado != EM.NO_ENVIADA


# --- Cancelar en la reconciliación sin UPID (decisión d) ------------------------------------------


def test_d_cancelar_durante_la_reconciliacion_sin_upid_corta_la_espera(
    qtbot, entorno, confirmaciones
):
    """Envío incierto sin UPID: el motor comprueba a +5 s y +15 s. «Cancelar» no espera."""
    from .apoyo_lote import RelojBloqueable

    reloj = RelojBloqueable()
    entorno.deps.reloj = reloj
    incierto = res_perdida(101, incierto=True)
    creacion = CreacionPorVmid({101: incierto})
    creacion.respuesta_existe_vm = False  # no existe: seguiría comprobando a +5 s y +15 s
    preparar_lote(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    reloj.bloquear = True
    crear_lote(qtbot, v)
    assert reloj.dentro.wait(5)  # el motor está esperando los +5 s (sin dormir de verdad)
    assert len(creacion.llamadas_existe_vm) == 1
    v._cancelar_lote()
    assert v._lote.control.evento_abandono.is_set()  # se corta la espera
    reloj.bloquear = False
    reloj.liberar.set()
    esperar_fin(qtbot, v)
    primera = v._lote.libro.instantanea()[0]
    assert primera.estado == EM.CONEXION_PERDIDA and primera.upid is None
    assert len(creacion.llamadas_existe_vm) == 1  # no hubo comprobaciones a +5 s ni a +15 s
    assert creacion.vmids_creados == [101]  # y nunca se reenvió
    assert estados(v)[1:] == ["no_enviada", "no_enviada"]
    assert v.progreso_lote.boton_comprobar.isVisible()


def test_la_reconciliacion_de_un_lote_comprueba_a_0_5_y_15_segundos_simulados(qtbot, entorno):
    from .apoyo_lote import RelojBloqueable

    reloj = RelojBloqueable()  # sin bloquear: dormir solo avanza el reloj simulado
    entorno.deps.reloj = reloj
    incierto = res_perdida(101, incierto=True)
    creacion = CreacionPorVmid({101: incierto})
    creacion.respuesta_existe_vm = False
    lanzar(qtbot, entorno, cantidad=2, creacion=creacion)
    v = entorno.ventana
    assert len(creacion.llamadas_existe_vm) == 3
    assert sum(reloj.dormidas) == pytest.approx(15.0)
    assert estados(v) == ["no_creada_segura", "ok"]  # (b) no se creó; el resto siguió
    assert creacion.vmids_creados == [101, 102]
    p = v.progreso_lote
    assert "Puedes reintentarla" in p.modelo.data(p.modelo.index(0, 4))
    assert p.boton_reintentar.isVisible()


def test_e_l06_si_no_se_puede_saber_si_existe_la_maquina_sigue_dudosa(qtbot, entorno):
    incierto = res_perdida(101, incierto=True)
    creacion = CreacionPorVmid({101: incierto})
    creacion.respuesta_existe_vm = None
    lanzar(qtbot, entorno, cantidad=2, creacion=creacion)
    p = entorno.ventana.progreso_lote
    assert estados(entorno.ventana)[0] == "conexion_perdida"
    assert "No pudimos comprobar si «web-01» existe" in p.modelo.data(p.modelo.index(0, 4))
    assert len(creacion.llamadas_existe_vm) == 1


def test_ca_l15_5_existe_sin_la_etiqueta_del_lote_no_es_elegible_para_deshacer(qtbot, entorno):
    cliente = ClienteLoteFalso()
    incierto = res_perdida(101, incierto=True)
    creacion = CreacionPorVmid({101: incierto})
    creacion.respuesta_existe_vm = True
    preparar_lote(qtbot, entorno, cantidad=2, creacion=creacion, cliente=cliente)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    # Tras planificar aparece una MV con ese VMID, pero sin la etiqueta de este lote.
    cliente.configs[101] = {"name": "web-01", "tags": "otra-persona"}
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert estados(v)[0] == "existe_sin_confirmar_propiedad"
    p = v.progreso_lote
    assert "no podemos asegurar que la creó este lote" in p.modelo.data(p.modelo.index(0, 4))
    v._deshacer()
    d = v.findChildren(DialogoDeshacer)[0]
    assert [c.entrada.elemento.vmid for c in d.elegidos()] == [102]  # la 101 nunca se borra
    d.reject()


def test_ca_l15_2_si_existe_con_la_etiqueta_del_lote_es_ok_con_aviso(qtbot, entorno):
    cliente = ClienteLoteFalso()
    incierto = res_perdida(101, incierto=True)
    creacion = CreacionPorVmid({101: incierto})
    creacion.respuesta_existe_vm = True
    preparar_lote(qtbot, entorno, cantidad=2, creacion=creacion, cliente=cliente)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    id_lote = v.resumen_lote.plan.id_lote
    cliente.configs[101] = {"name": "web-01", "tags": f"proxlaunch;lote-{id_lote}"}
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    primera = v._lote.libro.instantanea()[0]
    assert primera.estado == EM.OK and "creada_tras_comprobar" in primera.avisos
    p = v.progreso_lote
    assert "Se creó aunque Proxmox tardó en responder" in p.modelo.data(p.modelo.index(0, 4))
    assert creacion.vmids_creados == [101, 102]  # nunca se reenvió la 101
    v._deshacer()
    d = v.findChildren(DialogoDeshacer)[0]
    assert [c.entrada.elemento.vmid for c in d.elegidos()] == [101, 102]
    d.reject()


def test_ca_l15_7_comprobar_las_dudosas_nunca_envia_un_post(qtbot, entorno):
    cliente = ClienteLoteFalso()
    creacion = CreacionPorVmid({101: conexion_perdida(101)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, cliente=cliente, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    dialogo_pausa(v).botones[AccionPausa.DETENER].click()
    esperar_fin(qtbot, v)
    cliente.configs[101] = {"name": "web-01", "tags": ""}
    assert v.progreso_lote.boton_comprobar.text() == "Comprobar la dudosa"
    v.progreso_lote.boton_comprobar.click()
    qtbot.waitUntil(lambda: v._lote.terminado and estados(v)[0] == "ok", timeout=8000)
    assert cliente.creados == []  # ninguna escritura: solo lecturas (CA-L15.7)
    assert creacion.vmids_creados == [101]
    assert estados(v)[1:] == ["no_enviada", "no_enviada"]
