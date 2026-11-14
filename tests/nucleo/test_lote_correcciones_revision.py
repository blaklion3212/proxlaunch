"""Correcciones de la revisión QA y la auditoría de seguridad del MVP 2 (núcleo).

Cada prueba cita el hallazgo que cubre (A1, A3, B3, B4, B7, M1, M2, M5...). Se derivan del
comportamiento pedido, no de la implementación: cuántos POST/DELETE salen, qué estado queda en
el libro y qué recibe el servidor simulado.
"""

from __future__ import annotations

import contextlib
import http.client

import pytest
import requests
import urllib3

from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.transporte import TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    EstadoMV,
    EstadoRollback,
    MotivoNoEnviada,
    MotivoPausa,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.reconciliacion import AVISO_CREADA_TRAS_COMPROBAR
from proxlaunch.nucleo.lote.rollback import MOTIVO_PROPIEDAD_NO_DEMOSTRADA, ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.conexion import Ticket

from .apoyo_api import HUELLA_A, crear_sesion, url
from .apoyo_lote import (
    NORMAL,
    Banco,
    Cluster,
    ControlAutomatico,
    Http,
    RelojSeguro,
    TransporteCluster,
    crear_banco,
    crear_banco_http,
    definicion,
    inventario,
    nodo,
    upid_de,
)

A = "10.0.0.1"
MIN = 60.0


def _estados(libro):
    return [e.estado for e in libro.instantanea()]


def _lote(banco, cantidad, **kw):
    return banco.planificar(definicion(cantidad, vmid_inicial=100, **kw))


def _cluster_que_dispara_en_la_primera_validacion(banco, accion):
    """Regla GET que ejecuta ``accion`` una sola vez cuando la MV 100 está validando.

    La validación consulta ``/cluster/nextid?vmid=100`` antes de enviar; es el instante en el
    que una cancelación o una pausa externa debe impedir el envío (A1).
    """

    def _regla(llamada):
        if llamada.params and llamada.params.get("vmid") == 100:
            accion()
        return NORMAL

    banco.cluster.regla("GET", r"^/cluster/nextid$", _regla, veces=1)


# --- A1: cancelar o pausar durante la validación impide el envío --------------------------------


def test_a1_cancelar_mientras_una_maquina_valida_no_la_envia(banco):
    plan = _lote(banco, 3)
    control = ControlLote()
    _cluster_que_dispara_en_la_primera_validacion(banco, control.cancelar)
    libro = banco.ejecutar(plan, control)
    assert _estados(libro) == [EstadoMV.NO_ENVIADA] * 3
    assert libro.entrada(100).motivo_no_enviada == MotivoNoEnviada.CANCELADO
    assert banco.cluster.total("POST") == 0
    assert dict(banco.cluster.posts) == {}


def test_a1_una_pausa_por_error_global_mientras_valida_no_envia_esa_maquina(banco):
    plan = _lote(banco, 3)
    control = ControlAutomatico("suspender")
    error = ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "ticket caducado")
    # Otro nodo del lote pausó el lote con un error global justo mientras esta MV validaba.
    _cluster_que_dispara_en_la_primera_validacion(
        banco, lambda: control.pausar(MotivoPausa.ERROR_GLOBAL, error)
    )
    libro = banco.ejecutar(plan, control)
    assert libro.entrada(100).estado == EstadoMV.NO_ENVIADA
    assert libro.entrada(100).motivo_no_enviada == MotivoNoEnviada.PAUSA
    assert banco.cluster.total("POST") == 0
    # Las demás quedan PENDIENTE (el lote se suspendió): nunca se enviaron.
    assert _estados(libro)[1:] == [EstadoMV.PENDIENTE] * 2


def test_a1_sin_cancelar_ni_pausar_la_misma_maquina_si_se_envia(banco):
    libro = banco.ejecutar(_lote(banco, 2), ControlLote())
    assert _estados(libro) == [EstadoMV.OK, EstadoMV.OK]
    assert dict(banco.cluster.posts) == {100: 1, 101: 1}


# --- A3: nodo caído por sondeo de /nodes/{n}/status (transporte real) ---------------------------


def test_a3_con_pve2_caido_no_sale_ningun_post_a_pve2_y_sus_maquinas_quedan_no_enviadas(rsps):
    banco = crear_banco_http(rsps, ("pve1", "pve2"))
    plan = _lote(banco, 6, algoritmo=Algoritmo.POR_TURNOS)
    de_pve2 = {e.vmid for e in plan.elementos if e.nodo == "pve2"}
    assert len(de_pve2) == 3
    banco.cluster.regla("GET", r"^/nodes/pve2/status$", lambda ll: Http(595, "no route to host"))
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(plan, control)
    for e in libro.instantanea():
        if e.elemento.vmid in de_pve2:
            assert e.estado == EstadoMV.NO_ENVIADA
            assert e.motivo_no_enviada == MotivoNoEnviada.NODO_CAIDO
        else:
            assert e.estado == EstadoMV.OK
    assert not set(banco.cluster.posts) & de_pve2
    assert "pve2" not in set(banco.cluster.nodos_post.values())
    assert control.pausas == []  # un nodo caído no pausa el lote entero
    sondeos = banco.cluster.llamadas_a("GET", r"^/nodes/pve2/status$")
    assert len(sondeos) >= 1


def test_a3_el_sondeo_de_un_nodo_sano_no_impide_crear_en_el_y_se_hace_antes_del_primer_post(banco):
    plan = _lote(banco, 2)
    libro = banco.ejecutar(plan)
    assert _estados(libro) == [EstadoMV.OK, EstadoMV.OK]
    rutas = [(c.metodo, c.ruta) for c in banco.cluster.llamadas]
    primer_post = rutas.index(("POST", "/nodes/pve1/qemu"))
    assert ("GET", "/nodes/pve1/status") in rutas[:primer_post]


def test_a3_un_fallo_dudoso_vuelve_a_sondear_el_nodo_y_si_cayo_vacia_su_cola(banco):
    # La MV 100 sale y se pierde la conexión (envío incierto); el sondeo posterior ya no responde.
    plan = _lote(banco, 3)
    estado = {"cayo": False}

    def _post_corta(llamada):
        estado["cayo"] = True
        raise ErrorProxLaunch(
            CodigoError.SERVIDOR_NO_RESPONDE,
            {"host": A, "motivos": f"{A}=596", "incierto": "1"},
            "HTTP 596",
        )

    def _status(llamada):
        if estado["cayo"]:
            raise ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve1"}, "HTTP 596")
        return NORMAL

    banco.cluster.regla("POST", r"/qemu$", _post_corta)
    banco.cluster.regla("GET", r"^/nodes/pve1/status$", _status)
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert banco.cluster.posts[100] == 1
    assert libro.entrada(100).estado in (EstadoMV.CONEXION_PERDIDA, EstadoMV.NO_CREADA_SEGURA)
    assert [e.estado for e in libro.instantanea()[1:]] == [EstadoMV.NO_ENVIADA] * 2
    assert {e.motivo_no_enviada for e in libro.instantanea()[1:]} == {MotivoNoEnviada.NODO_CAIDO}
    assert 101 not in banco.cluster.posts and 102 not in banco.cluster.posts


def test_a3_un_error_de_permisos_en_el_sondeo_no_prueba_que_el_nodo_este_caido(banco):
    banco.cluster.regla(
        "GET",
        r"^/nodes/pve1/status$",
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "Sys.Audit"}, "403"),
    )
    libro = banco.ejecutar(_lote(banco, 2), ControlAutomatico("continuar"))
    assert _estados(libro) == [EstadoMV.OK, EstadoMV.OK]


# --- M1 QA: cuerpo cortado o mal decodificado tras iniciar el envío -----------------------------


def _http_un_host():
    return TransporteHttp([A], 8006, huellas={A: HUELLA_A})


@pytest.mark.parametrize(
    "fallo",
    [
        pytest.param(requests.exceptions.ChunkedEncodingError("cortado"), id="chunked"),
        pytest.param(requests.exceptions.ContentDecodingError("gzip roto"), id="decodificacion"),
    ],
)
@pytest.mark.parametrize("metodo", ["POST", "DELETE"])
def test_m1_un_cuerpo_cortado_en_una_escritura_es_un_envio_incierto(rsps, fallo, metodo):
    ruta = "/nodes/pve1/qemu" if metodo == "POST" else "/nodes/pve1/qemu/100"
    getattr(rsps, metodo.lower())(url(A, ruta), body=fallo)
    with pytest.raises(ErrorProxLaunch) as exc:
        _http_un_host().peticion(metodo, ruta, datos={"vmid": "100"} if metodo == "POST" else None)
    assert exc.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert exc.value.params.get("incierto") == "1"
    assert len(rsps.calls) == 1  # nunca se reenvía una escritura


def test_m1_el_post_cortado_se_reconcilia_y_no_se_reenvia(rsps):
    banco = crear_banco_http(rsps, ("pve1",))
    plan = _lote(banco, 2)

    def _crea_y_corta(llamada):
        banco.cluster._normal(llamada)  # Proxmox sí recibió y creó la máquina
        raise requests.exceptions.ChunkedEncodingError("conexión cortada a mitad del cuerpo")

    banco.cluster.regla(
        "POST", r"/qemu$", lambda ll: _crea_y_corta(ll) if ll.datos["vmid"] == "100" else NORMAL
    )
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    entrada = libro.entrada(100)
    assert entrada.estado == EstadoMV.OK  # reconciliada: existe y lleva la etiqueta del lote
    assert AVISO_CREADA_TRAS_COMPROBAR in entrada.avisos
    assert banco.cluster.posts[100] == 1
    assert libro.entrada(101).estado == EstadoMV.OK


def test_m1_el_post_cortado_sin_que_llegue_queda_no_creada_segura(rsps):
    banco = crear_banco_http(rsps, ("pve1",))
    plan = _lote(banco, 1)
    banco.cluster.regla("POST", r"/qemu$", requests.exceptions.ChunkedEncodingError("cortado"))
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert libro.entrada(100).estado == EstadoMV.NO_CREADA_SEGURA
    assert banco.cluster.posts[100] == 1


def test_m1_el_delete_cortado_queda_incierto_y_se_resuelve_leyendo(rsps):
    banco = crear_banco_http(rsps, ("pve1",))
    libro = banco.ejecutar(_lote(banco, 1))
    banco.cluster.regla("DELETE", r"/qemu/100$", requests.exceptions.ChunkedEncodingError("x"))
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    candidatos = servicio.elegibles(libro, etiquetado=True)
    (r,) = servicio.deshacer(
        candidatos, lambda _r: None, ControlLote(), id_lote=libro.id_lote, etiquetado=True
    )
    assert r.estado == EstadoRollback.INCIERTA  # la MV sigue ahí: no se sabe si se borrará
    assert banco.cluster.deletes[100] == 1  # nunca se reenvía el DELETE


def test_m1_un_error_local_de_requests_no_se_trata_como_envio_incierto(rsps):
    rsps.post(url(A, "/nodes/pve1/qemu"), body=requests.exceptions.InvalidHeader("cabecera"))
    with pytest.raises(ErrorProxLaunch) as exc:
        _http_un_host().peticion("POST", "/nodes/pve1/qemu", datos={"vmid": "100"})
    assert exc.value.params.get("incierto") != "1"


# --- B7: reintento único de GET, solo si parece una conexión reutilizada cerrada ----------------


def _reintento(rsps, fallo):
    """Registra ``fallo`` y luego una respuesta correcta; devuelve (resultado, llamadas)."""
    rsps.get(url(A, "/version"), body=fallo)
    rsps.get(url(A, "/version"), json={"data": {"version": "9.2.1"}})
    try:
        resultado = _http_un_host().peticion("GET", "/version")
    except ErrorProxLaunch as e:
        resultado = e
    return resultado, len(rsps.calls)


def test_b7_get_con_protocolerror_se_reintenta_una_vez(rsps):
    fallo = requests.exceptions.ConnectionError(
        urllib3.exceptions.ProtocolError("Connection aborted.", ConnectionResetError(104))
    )
    resultado, llamadas = _reintento(rsps, fallo)
    assert resultado == {"version": "9.2.1"}
    assert llamadas == 2


def test_b7_get_con_remotedisconnected_se_reintenta_una_vez(rsps):
    fallo = requests.exceptions.ConnectionError(
        urllib3.exceptions.ProtocolError(
            "Connection aborted.", http.client.RemoteDisconnected("cerrada sin respuesta")
        )
    )
    resultado, llamadas = _reintento(rsps, fallo)
    assert resultado == {"version": "9.2.1"}
    assert llamadas == 2


def test_b7_get_con_connectionreseterror_se_reintenta_una_vez(rsps):
    fallo = requests.exceptions.ConnectionError(ConnectionResetError(104, "reset"))
    resultado, llamadas = _reintento(rsps, fallo)
    assert resultado == {"version": "9.2.1"}
    assert llamadas == 2


def test_b7_el_reintento_es_unico_si_vuelve_a_fallar_no_hay_un_tercer_intento(rsps):
    fallo = requests.exceptions.ConnectionError(
        urllib3.exceptions.ProtocolError("Connection aborted.", ConnectionResetError(104))
    )
    rsps.get(url(A, "/version"), body=fallo)
    rsps.get(url(A, "/version"), body=fallo)
    rsps.get(url(A, "/version"), json={"data": {"version": "9.2.1"}})
    with pytest.raises(ErrorProxLaunch):
        _http_un_host().peticion("GET", "/version")
    assert len(rsps.calls) == 2


@pytest.mark.parametrize(
    "fallo",
    [
        pytest.param(
            requests.exceptions.ConnectionError(
                urllib3.exceptions.NewConnectionError(None, "conexión rechazada")
            ),
            id="conexion-rechazada",
        ),
        pytest.param(requests.exceptions.ReadTimeout("lento"), id="read-timeout"),
        pytest.param(requests.exceptions.ConnectTimeout("lento"), id="connect-timeout"),
    ],
)
def test_b7_get_no_se_reintenta_ante_conexion_rechazada_ni_timeouts(rsps, fallo):
    resultado, llamadas = _reintento(rsps, fallo)
    assert isinstance(resultado, ErrorProxLaunch)
    assert llamadas == 1


@pytest.mark.parametrize("metodo", ["POST", "DELETE"])
def test_b7_nunca_se_reintenta_un_post_ni_un_delete(rsps, metodo):
    fallo = requests.exceptions.ConnectionError(
        urllib3.exceptions.ProtocolError("Connection aborted.", ConnectionResetError(104))
    )
    ruta = "/nodes/pve1/qemu" if metodo == "POST" else "/nodes/pve1/qemu/100"
    getattr(rsps, metodo.lower())(url(A, ruta), body=fallo)
    getattr(rsps, metodo.lower())(url(A, ruta), json={"data": upid_de("pve1", 100)})
    with pytest.raises(ErrorProxLaunch):
        _http_un_host().peticion(metodo, ruta, datos={"vmid": "100"} if metodo == "POST" else None)
    assert len(rsps.calls) == 1


# --- M2 QA / B4 seg: la simulación renueva el ticket y no escribe nada más ----------------------


class _TransporteConTicket(TransporteCluster):
    """Clúster simulado que además atiende ``POST /access/ticket`` y cuenta las renovaciones."""

    def __init__(self, cluster):
        super().__init__(cluster)
        self.renovaciones = 0

    def peticion(self, metodo, ruta, *, params=None, datos=None):
        if metodo.upper() == "POST" and ruta == "/access/ticket":
            self.renovaciones += 1
            return {
                "ticket": "PVE:ana@pve:NUEVO::c2ln",
                "CSRFPreventionToken": "NUEVO:Y3NyZg",
                "username": "ana@pve",
            }
        return super().peticion(metodo, ruta, params=params, datos=datos)


def _banco_con_ticket(emitido=0.0):
    reloj = RelojSeguro()
    cluster = Cluster(("pve1",))
    transporte = _TransporteConTicket(cluster)
    auth = AutenticadorTicket(
        Ticket("PVE:ana@pve:VIEJO::s", "VIEJO:csrf", "ana@pve", emitido), reloj
    )
    sesion = crear_sesion(transporte, auth=auth, reloj=reloj)  # type: ignore[arg-type]
    banco = Banco(cluster, sesion, reloj, inventario((nodo("pve1"),)))
    return banco, transporte, auth


def test_m2_la_simulacion_con_el_ticket_por_renovar_renueva_una_sola_vez_y_no_falla():
    banco, transporte, auth = _banco_con_ticket()
    banco.reloj.avanzar(110 * MIN)  # pasado el margen de renovación
    assert auth.necesita_renovar()
    res = simular(banco.sesion, definicion(3, vmid_inicial=100), banco.inv, reloj=banco.reloj)
    assert res.plan.es_simulacion is True
    assert transporte.renovaciones == 1
    assert auth.ticket.ticket == "PVE:ana@pve:NUEVO::c2ln"
    # Ningún otro método de escritura salió: solo lecturas.
    assert banco.cluster.solo_lecturas
    assert banco.cluster.total("POST") == banco.cluster.total("DELETE") == 0


def test_m2_el_cliente_de_solo_lectura_sigue_sin_poder_crear_ni_eliminar_con_ticket_por_renovar():
    banco, transporte, _ = _banco_con_ticket()
    banco.reloj.avanzar(110 * MIN)
    ro = banco.sesion.cliente.solo_lectura()
    with pytest.raises(ErrorProxLaunch) as e1:
        ro.crear_vm("pve1", {"vmid": "100", "name": "x"})
    with pytest.raises(ErrorProxLaunch) as e2:
        ro.eliminar_vm("pve1", 100)
    assert e1.value.codigo == e2.value.codigo == CodigoError.ESCRITURA_EN_SIMULACION
    assert banco.cluster.total("POST") == banco.cluster.total("DELETE") == 0


def test_b4_seg_cerrar_el_cliente_de_solo_lectura_no_suelta_la_credencial_compartida():
    banco, _, auth = _banco_con_ticket()
    ro = banco.sesion.cliente.solo_lectura()
    ro.cerrar()
    assert auth.ticket.ticket == "PVE:ana@pve:VIEJO::s"  # sigue en memoria
    assert banco.sesion.cliente.vmid_libre(150) is True  # y el cliente principal sigue vivo


def test_b4_seg_cerrar_el_cliente_principal_si_suelta_la_credencial():
    banco, _, auth = _banco_con_ticket()
    banco.sesion.cliente.cerrar()
    assert auth.ticket.ticket == ""


def test_b1_qa_tras_cerrar_la_sesion_una_peticion_tardia_no_pide_un_ticket_nuevo():
    # Un hilo que sigue vivo tras cerrar la sesión no debe enviar POST /access/ticket con una
    # credencial vacía (el cierre suelta el ticket; el reloj ya pasó el margen de renovación).
    banco, transporte, _ = _banco_con_ticket()
    banco.reloj.avanzar(110 * MIN)
    banco.sesion.cliente.cerrar()
    with contextlib.suppress(ErrorProxLaunch):
        banco.sesion.cliente.vmid_libre(150)
    assert transporte.renovaciones == 0


def test_m2_el_cliente_de_solo_lectura_comparte_sesion_con_el_principal():
    banco, _, _ = _banco_con_ticket()
    ro = banco.sesion.cliente.solo_lectura()
    assert isinstance(ro, ClienteProxmox)
    assert ro.vmid_libre(150) is True


# --- M5: elegibilidad del rollback sin etiquetas y VMIDs ya eliminados --------------------------


def _libro_a_mano(banco, estados, *, etiquetar=True, con_upid=True, avisos=()):
    plan = banco.planificar(definicion(len(estados), vmid_inicial=100, etiquetar=etiquetar))
    libro = Libro(plan)
    for vmid, estado in estados.items():
        libro.iniciar(vmid, 0.0)
        libro.marcar_post_intentado(vmid, 0.0)
        if con_upid:
            libro.registrar_upid(vmid, upid_de("pve1", vmid))
        libro.finalizar(vmid, estado, t_fin=1.0, avisos=avisos)
    return plan, libro


def test_m5_elegibles_excluye_los_vmids_ya_eliminados(banco):
    _, libro = _libro_a_mano(banco, {100: EstadoMV.OK, 101: EstadoMV.OK, 102: EstadoMV.OK})
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    cs = servicio.elegibles(libro, etiquetado=True, excluir_vmids={100, 102})
    assert [c.entrada.elemento.vmid for c in cs] == [101]


def test_m5_sin_etiquetas_una_maquina_sin_upid_propio_no_es_elegible(banco):
    _, libro = _libro_a_mano(banco, {100: EstadoMV.OK}, etiquetar=False, con_upid=False)
    (c,) = ServicioRollback(banco.sesion, banco.reloj).elegibles(libro, etiquetado=False)
    assert not c.elegible
    assert c.motivo == MOTIVO_PROPIEDAD_NO_DEMOSTRADA


def test_m5_sin_etiquetas_una_maquina_rescatada_aunque_tenga_upid_no_es_elegible(banco):
    _, libro = _libro_a_mano(
        banco, {100: EstadoMV.OK}, etiquetar=False, avisos=(AVISO_CREADA_TRAS_COMPROBAR,)
    )
    (c,) = ServicioRollback(banco.sesion, banco.reloj).elegibles(libro, etiquetado=False)
    assert not c.elegible
    assert c.motivo == MOTIVO_PROPIEDAD_NO_DEMOSTRADA


def test_m5_con_etiquetas_una_maquina_sin_upid_propio_sigue_siendo_elegible(banco):
    _, libro = _libro_a_mano(banco, {100: EstadoMV.OK}, con_upid=False)
    (c,) = ServicioRollback(banco.sesion, banco.reloj).elegibles(libro, etiquetado=True)
    assert c.elegible


def _deshacer_sin_etiquetas(banco, libro):
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    candidatos = servicio.elegibles(libro, etiquetado=False)
    return servicio.deshacer(
        candidatos, lambda _r: None, ControlLote(), id_lote=libro.id_lote, etiquetado=False
    )


@pytest.mark.parametrize(
    ("config", "estado", "codigo"),
    [
        pytest.param({"name": "web-01"}, EstadoRollback.ELIMINADA, None, id="mismo-nombre"),
        pytest.param(
            {"name": "otra"},
            EstadoRollback.OMITIDA,
            CodigoError.ROLLBACK_NO_PROPIA,
            id="otro-nombre",
        ),
        pytest.param({}, EstadoRollback.OMITIDA, CodigoError.ROLLBACK_NO_PROPIA, id="sin-nombre"),
        pytest.param(
            {"name": 100},
            EstadoRollback.OMITIDA,
            CodigoError.ROLLBACK_NO_PROPIA,
            id="nombre-no-str",
        ),
        pytest.param(
            {"name": ""},
            EstadoRollback.OMITIDA,
            CodigoError.ROLLBACK_NO_PROPIA,
            id="nombre-vacio",
        ),
    ],
)
def test_m5_sin_etiquetas_solo_se_borra_si_el_nombre_es_str_e_igual_al_del_plan(
    banco, config, estado, codigo
):
    plan = banco.planificar(definicion(1, vmid_inicial=100, etiquetar=False))
    libro = banco.ejecutar(plan)
    assert libro.entrada(100).estado == EstadoMV.OK
    assert plan.elementos[0].nombre == "web-01"
    vm = banco.cluster.vms[100]
    vm["config"] = {"digest": "d", **config}
    (r,) = _deshacer_sin_etiquetas(banco, libro)
    assert r.estado == estado
    if codigo is None:
        assert banco.cluster.deletes[100] == 1
    else:
        assert r.error.codigo == codigo
        assert banco.cluster.deletes[100] == 0
        assert 100 in banco.cluster.vms


def test_m5_deshacer_el_lote_a_no_borra_la_maquina_del_lote_b_que_reutiliza_vmid_y_nombre(
    banco,
):
    plan_a = banco.planificar(definicion(2, vmid_inicial=100, etiquetar=False))
    libro_a = banco.ejecutar(plan_a)
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    resultados_a = servicio.deshacer(
        servicio.elegibles(libro_a, etiquetado=False),
        lambda _r: None,
        ControlLote(),
        id_lote=libro_a.id_lote,
        etiquetado=False,
    )
    assert [r.estado for r in resultados_a] == [EstadoRollback.ELIMINADA] * 2
    # El lote B reutiliza los mismos VMIDs y nombres (los quedó libres el lote A).
    plan_b = banco.planificar(definicion(2, vmid_inicial=100, etiquetar=False))
    libro_b = banco.ejecutar(plan_b)
    assert [e.estado for e in libro_b.instantanea()] == [EstadoMV.OK, EstadoMV.OK]
    assert set(banco.cluster.vms) == {100, 101}
    # La interfaz excluye lo que ya eliminó: el segundo «Deshacer» del lote A no ofrece nada.
    vistos = {r.vmid for r in resultados_a if r.estado == EstadoRollback.ELIMINADA}
    candidatos = servicio.elegibles(libro_a, etiquetado=False, excluir_vmids=vistos)
    assert candidatos == []
    antes = dict(banco.cluster.deletes)
    servicio.deshacer(
        candidatos,
        lambda _r: None,
        ControlLote(),
        id_lote=libro_a.id_lote,
        etiquetado=False,
    )
    assert dict(banco.cluster.deletes) == antes  # ni un DELETE más
    assert set(banco.cluster.vms) == {100, 101}  # las del lote B siguen ahí


# --- B3 QA: un error global detiene a los demás nodos y grupos del deshacer ---------------------


def test_b3_un_error_global_en_un_nodo_detiene_los_demas_nodos_del_rollback():
    banco = crear_banco(("pve1", "pve2"))
    plan = banco.planificar(definicion(4, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    libro = banco.ejecutar(plan)
    assert all(e.estado == EstadoMV.OK for e in libro.instantanea())
    banco.cluster.reiniciar_llamadas()
    banco.cluster.regla(
        "DELETE",
        r"^/nodes/pve1/qemu/",
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403 VM.Allocate"),
    )
    servicio = ServicioRollback(banco.sesion, banco.reloj, max_nodos=1)  # un nodo tras otro
    control = ControlLote()
    resultados = servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        lambda _r: None,
        control,
        id_lote=libro.id_lote,
        etiquetado=True,
    )
    assert control.motivo_pausa == MotivoPausa.ERROR_GLOBAL
    por_nodo = {}
    for r in resultados:
        nodo_ = libro.entrada(r.vmid).elemento.nodo
        por_nodo.setdefault(nodo_, []).append(r.estado)
    assert por_nodo["pve1"][0] == EstadoRollback.FALLO
    assert set(por_nodo["pve2"]) == {EstadoRollback.NO_ENVIADA}
    assert not banco.cluster.deletes.get(102) and not banco.cluster.deletes.get(103)


def test_b3_con_el_control_ya_pausado_otro_grupo_no_elimina_nada(banco):
    # Es lo que ocurre con el segundo lote de «Deshacer»: comparte el control del primero.
    _, libro = _libro_a_mano(banco, {100: EstadoMV.OK, 101: EstadoMV.OK})
    for vmid in (100, 101):
        banco.cluster.agregar_vm(
            vmid,
            "pve1",
            f"web-{vmid - 99:02d}",
            tags=banco.cluster.etiquetas_del_lote(libro.id_lote),
        )
    control = ControlLote()
    control.pausar(MotivoPausa.ERROR_GLOBAL, ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "x"))
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    resultados = servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        lambda _r: None,
        control,
        id_lote=libro.id_lote,
        etiquetado=True,
    )
    assert {r.estado for r in resultados} == {EstadoRollback.NO_ENVIADA}
    assert banco.cluster.total("DELETE") == 0


# --- B4 QA: RECURSO_INEXISTENTE en el DELETE ----------------------------------------------------


def test_b4_qa_un_recurso_inexistente_en_el_delete_es_ya_no_existia(banco):
    libro = banco.ejecutar(_lote(banco, 1))
    # La MV desapareció entre la comprobación previa y el DELETE.
    banco.cluster.regla(
        "DELETE", r"/qemu/100$", ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "no such VM")
    )
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    (r,) = servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        lambda _r: None,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
    )
    assert r.estado == EstadoRollback.YA_NO_EXISTIA
    assert r.error is None


def test_b4_qa_el_recurso_inexistente_no_pausa_ni_detiene_el_rollback(banco):
    libro = banco.ejecutar(_lote(banco, 2))
    banco.cluster.regla(
        "DELETE",
        r"/qemu/100$",
        ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "no such VM"),
    )
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    control = ControlLote()
    resultados = servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        lambda _r: None,
        control,
        id_lote=libro.id_lote,
        etiquetado=True,
    )
    assert [r.estado for r in resultados] == [
        EstadoRollback.YA_NO_EXISTIA,
        EstadoRollback.ELIMINADA,
    ]
    assert control.motivo_pausa is None
