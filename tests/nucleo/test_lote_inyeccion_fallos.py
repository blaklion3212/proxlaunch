"""Inyección de fallos exhaustiva de INV-L1 (CA-L12.1, RNF-L08).

Un fallo en cada punto del flujo de creación de cada MV de un lote de 3 (primera, intermedia y
última) y, en cada caso, como máximo UN ``POST /nodes/{n}/qemu`` por VMID, antes y después de
las acciones de reanudación (``comprobar_dudosas`` y ``ejecutar_pendientes``).

Dos niveles: el cliente real sobre el clúster simulado (``Transporte`` falso) y el
``TransporteHttp`` real con respuestas HTTP simuladas (``responses``).
"""

import pytest
import requests

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote

from .apoyo_lote import (
    NORMAL,
    ControlAutomatico,
    Http,
    crear_banco,
    crear_banco_http,
    definicion,
    envio_incierto,
    nodo_caido,
)

OBJETIVOS = [100, 101, 102]  # primera, intermedia y última de un lote de 3

# Fallos que significan "el POST pudo haber llegado": nunca terminan como error "nada creado".
# 595/596/597 como ``NODO_NO_DISPONIBLE``: en un GET es lo que produce el transporte real; en un
# POST el transporte real los convierte en envío incierto (ver el nivel 2), así que aquí solo se
# exige INV-L1, no el estado final.
NODO_CAIDO = {
    "596": nodo_caido("pve1", 596),
    "595": nodo_caido("pve1", 595),
    "597": nodo_caido("pve1", 597),
}
INCIERTOS = {
    "sin_respuesta": ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "x"}, "timeout"),
    "envio_incierto": envio_incierto(),
    "read_timeout": requests.exceptions.ReadTimeout("read timed out"),
    "conexion_abortada": requests.exceptions.ConnectionError("Connection aborted"),
    "ssl": requests.exceptions.SSLError("handshake"),
    "excepcion_inesperada": RuntimeError("boom"),
}
DEFINITIVOS = {
    "401": ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "HTTP 401"),
    "403": ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "HTTP 403"),
    "500": ErrorProxLaunch(CodigoError.DESCONOCIDO, {"estado_http": "500"}, "HTTP 500"),
    "json_invalido": ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "la respuesta no es JSON"),
}
TODOS = {**NODO_CAIDO, **INCIERTOS, **DEFINITIVOS}

ESTADOS_CON_POSIBLE_CREACION = {
    EstadoMV.CONEXION_PERDIDA,
    EstadoMV.NO_CREADA_SEGURA,
    EstadoMV.OK,
    EstadoMV.CON_AVISOS,
    EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD,
    EstadoMV.PARCIAL,
    EstadoMV.TIEMPO_AGOTADO,
}


def _regla_en(banco, metodo, patron, vmid, que):
    """Inyecta ``que`` (excepción o función) solo en las peticiones de ``vmid``."""

    def _accion(llamada):
        sobre = (llamada.datos or {}).get("vmid") or (llamada.params or {}).get("vmid")
        if sobre is None:
            import re

            m = re.search(r"/(?:qemu|tasks/UPID:[^/]*:qmcreate):?(\d+)", llamada.ruta)
            sobre = m.group(1) if m else None
        if sobre is not None and int(sobre) != vmid:
            return NORMAL
        if isinstance(que, BaseException):
            raise que
        return que(llamada)

    return banco.cluster.regla(metodo, patron, _accion)


def _verificar_inv_l1(banco, libro, objetivo=None):
    posts = banco.cluster.posts
    assert all(n <= 1 for n in posts.values()), dict(posts)  # INV-L1
    assert sum(posts.values()) <= len(libro.instantanea())
    assert banco.cluster.total("DELETE") == 0  # INV-L4: el motor no borra
    for e in libro.instantanea():
        vmid = e.elemento.vmid
        if e.estado == EstadoMV.NO_ENVIADA:
            assert posts.get(vmid, 0) == 0 and not e.post_intentado, vmid
        if posts.get(vmid, 0) >= 1:
            assert e.post_intentado, vmid  # ENVIANDO siempre precede al POST
            assert e.estado != EstadoMV.NO_ENVIADA
        if e.post_intentado:
            assert posts.get(vmid, 0) <= 1


def _ejecutar(banco, objetivo, plan=None):
    """Ejecuta, comprueba dudosas y ejecuta pendientes; devuelve el libro y verifica INV-L1."""
    plan = plan or banco.planificar(definicion(3, vmid_inicial=100))
    visto = {}

    def _al_post(vmid):
        e = banco.ultimo[vmid]
        visto[vmid] = (e.estado, e.post_intentado)

    banco.cluster.al_post = _al_post
    return plan, visto


def _etapas_correctas(visto):
    return all(v == (EstadoMV.ENVIANDO, True) for v in visto.values())


# --- Nivel 1: cliente real sobre el clúster simulado ----------------------------------------------


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", sorted(TODOS))
def test_inv_l1_fallo_en_el_post_de_cada_maquina(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, visto = _ejecutar(banco, objetivo)
    _regla_en(banco, "POST", r"/qemu$", objetivo, TODOS[fallo])
    control = ControlAutomatico("continuar")
    libro = banco.ejecutar(plan, control)
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1  # llegó a intentarse, una sola vez
    assert _etapas_correctas(visto)
    e = libro.entrada(objetivo)
    if fallo in INCIERTOS:
        assert e.estado in ESTADOS_CON_POSIBLE_CREACION, e.estado  # nunca "error: nada creado"
    # Las demás MVs se procesan igualmente (el fallo de una no detiene al resto).
    otras = [x for x in libro.instantanea() if x.elemento.vmid != objetivo]
    assert all(x.estado != EstadoMV.PENDIENTE for x in otras)

    # Reanudar no puede reenviar nada.
    motor = banco.motor()
    motor.comprobar_dudosas(libro, banco.observador, ControlLote())
    motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", sorted(TODOS))
def test_inv_l1_fallo_en_la_reconsulta_del_vmid_antes_de_enviar(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, visto = _ejecutar(banco, objetivo)  # el plan ya se hizo: la reconsulta es posterior
    _regla_en(banco, "GET", r"^/cluster/nextid$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts.get(objetivo, 0) == 0  # sin reconsulta no hay envío
    e = libro.entrada(objetivo)
    assert not e.post_intentado
    assert e.estado in (EstadoMV.ERROR, EstadoMV.NO_ENVIADA)  # nada que reconciliar
    assert e.estado != EstadoMV.CONEXION_PERDIDA
    assert _etapas_correctas(visto)
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", sorted(TODOS))
def test_inv_l1_fallo_en_el_sondeo_de_la_tarea_despues_del_upid(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, visto = _ejecutar(banco, objetivo)
    _regla_en(banco, "GET", r"/tasks/.*/status$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1
    e = libro.entrada(objetivo)
    assert e.upid  # el UPID se guardó antes del sondeo
    assert e.estado in ESTADOS_CON_POSIBLE_CREACION  # tras el UPID nunca es "no se creó"
    assert e.estado != EstadoMV.NO_CREADA_SEGURA  # con UPID no se concluye por existencia
    motor = banco.motor()
    motor.comprobar_dudosas(libro, banco.observador, ControlLote())
    motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", ["596", "sin_respuesta", "500", "401", "excepcion_inesperada"])
def test_inv_l1_fallo_en_la_comprobacion_final_de_la_config(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, visto = _ejecutar(banco, objetivo)
    _regla_en(banco, "GET", r"/qemu/\d+/config$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1
    assert libro.entrada(objetivo).estado != EstadoMV.NO_ENVIADA
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", ["596", "sin_respuesta", "500", "excepcion_inesperada"])
def test_inv_l1_fallo_al_leer_el_log_de_una_tarea_con_avisos_o_error(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, visto = _ejecutar(banco, objetivo)
    banco.cluster.exitstatus[objetivo] = "WARNINGS: 1"
    _regla_en(banco, "GET", r"/tasks/.*/log$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("valor", [None, "", "no-es-un-upid", 42, {"data": "x"}], ids=repr)
def test_inv_l1_respuesta_del_post_sin_upid_valido(valor, objetivo):
    banco = crear_banco(("pve1",))
    plan, visto = _ejecutar(banco, objetivo)
    _regla_en(banco, "POST", r"/qemu$", objetivo, lambda ll: valor)
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("valor", [None, "basura"], ids=repr)
def test_rf_l15_una_respuesta_sin_upid_no_se_declara_como_nada_creado(valor):
    """RF-L15: el POST llegó al servidor y no se sabe si creó la MV; no puede ser ``error``.

    Declararla ``error`` ("nada creado") la haría elegible para «Reintentar» (RF-L21 solo
    admite ``error`` con nada creado) aunque Proxmox pudo haberla creado.
    """
    banco = crear_banco(("pve1",))
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    banco.cluster.regla("POST", r"/qemu$", lambda ll: valor)
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert libro.entrada(100).estado != EstadoMV.ERROR


@pytest.mark.parametrize("fallo", ["json_invalido", "sin_data"])
def test_rf_l15_http_200_con_cuerpo_invalido_no_se_declara_como_nada_creado(rsps, fallo):
    banco = crear_banco_http(rsps)
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    _regla_en(banco, "POST", r"/qemu$", 100, FALLOS_HTTP[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert libro.entrada(100).estado != EstadoMV.ERROR


def test_inv_l1_fallo_en_todas_las_maquinas_a_la_vez_en_el_post():
    banco = crear_banco(("pve1",))
    plan, visto = _ejecutar(banco, None)
    banco.cluster.regla("POST", r"/qemu$", INCIERTOS["envio_incierto"])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro)
    assert dict(banco.cluster.posts) == {100: 1, 101: 1, 102: 1}


def test_inv_l1_fallos_distintos_en_cada_punto_de_cada_maquina_a_la_vez():
    banco = crear_banco(("pve1",))
    plan, visto = _ejecutar(banco, None)
    _regla_en(banco, "GET", r"^/cluster/nextid$", 100, TODOS["500"])
    _regla_en(banco, "POST", r"/qemu$", 101, INCIERTOS["envio_incierto"])
    _regla_en(banco, "GET", r"/tasks/.*/status$", 102, TODOS["sin_respuesta"])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro)
    motor = banco.motor()
    for _ in range(2):  # repetir las acciones de reanudación tampoco reenvía
        motor.comprobar_dudosas(libro, banco.observador, ControlLote())
        motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro)


@pytest.mark.parametrize("nodos", [("pve1", "pve2"), ("pve1", "pve2", "pve3", "pve4", "pve5")])
def test_inv_l1_con_varios_nodos_y_fallos_inciertos_en_paralelo(nodos):
    from proxlaunch.nucleo.lote.modelos import Algoritmo

    banco = crear_banco(nodos)
    plan = banco.planificar(definicion(10, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    for vmid in (100, 103, 107):
        _regla_en(banco, "POST", r"/qemu$", vmid, INCIERTOS["envio_incierto"])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro)
    assert sum(banco.cluster.posts.values()) == 10


def test_inv_l1_cancelar_en_cada_punto_no_duplica_envios():
    """Cancelar justo antes, durante y después del POST de cada MV nunca reenvía."""
    for objetivo in OBJETIVOS:
        banco = crear_banco(("pve1",))
        plan, visto = _ejecutar(banco, objetivo)
        control = ControlLote()

        def _al_post(vmid, control=control, objetivo=objetivo):
            if vmid == objetivo:
                control.cancelar()

        banco.cluster.al_post = _al_post
        libro = banco.ejecutar(plan, control)
        _verificar_inv_l1(banco, libro, objetivo)
        banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
        _verificar_inv_l1(banco, libro, objetivo)


# --- Nivel 2: TransporteHttp real con respuestas HTTP simuladas -----------------------------------

FALLOS_HTTP = {
    "http_595": lambda ll: Http(595, "No route to host"),
    "http_596": lambda ll: Http(596, "Connection timed out"),
    "http_597": lambda ll: Http(597, "Broken pipe"),
    "read_timeout": requests.exceptions.ReadTimeout("read timed out"),
    "conexion_abortada": requests.exceptions.ConnectionError("Connection aborted"),
    "ssl": requests.exceptions.SSLError("EOF occurred in violation of protocol"),
    "http_401": lambda ll: Http(401, "No ticket"),
    "http_403": lambda ll: Http(
        403,
        "Permission check failed (/vms/100, VM.Allocate)",
        {"data": None, "message": "Permission check failed (/vms/100, VM.Allocate)"},
    ),
    "http_500": lambda ll: Http(500, "internal error"),
    "json_invalido": lambda ll: Http(200, "ok", "esto no es JSON"),
    "sin_data": lambda ll: Http(200, "ok", {"data": None}),
}
INCIERTOS_HTTP = {"http_595", "http_596", "http_597", "read_timeout", "conexion_abortada", "ssl"}


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", sorted(FALLOS_HTTP))
def test_inv_l1_http_real_fallo_en_el_post(rsps, fallo, objetivo):
    banco = crear_banco_http(rsps)
    plan, visto = _ejecutar(banco, objetivo)
    _regla_en(banco, "POST", r"/qemu$", objetivo, FALLOS_HTTP[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1
    posts_reales = [c for c in rsps.calls if c.request.method == "POST"]
    assert len(posts_reales) == 3  # una petición real por MV: ningún reintento del transporte
    e = libro.entrada(objetivo)
    if fallo in INCIERTOS_HTTP:
        assert e.estado in ESTADOS_CON_POSIBLE_CREACION, e.estado
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", ["http_596", "read_timeout", "http_500", "conexion_abortada"])
def test_inv_l1_http_real_fallo_en_el_sondeo(rsps, fallo, objetivo):
    banco = crear_banco_http(rsps)
    plan, visto = _ejecutar(banco, objetivo)
    _regla_en(banco, "GET", r"/tasks/.*/status$", objetivo, FALLOS_HTTP[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert libro.entrada(objetivo).upid
    assert libro.entrada(objetivo).estado != EstadoMV.NO_CREADA_SEGURA
