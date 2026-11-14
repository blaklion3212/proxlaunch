"""INV-L1 repetida sobre un lote por filas heterogéneo (CA-C08.2; arquitectura §13 y §14.1).

Es la suite de ``test_lote_inyeccion_fallos.py`` (fallo en cada punto del flujo de creación,
primera, intermedia y última MV, ≤ 1 POST por VMID antes y después de reanudar) aplicada a un plan
por filas: cuatro MVs distintas, una con VMID explícito, más pausa, cancelación, reanudación,
concurrencia por nodo y el cuerpo exacto de cada POST (cada MV con SU configuración).

Reutiliza, sin modificarlos, los catálogos de fallos y las verificaciones de la suite de M2.
"""

import threading

import pytest

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import MAX_NODOS_PARALELOS
from proxlaunch.nucleo.lote.modelos import Algoritmo, EstadoMV, MotivoNoEnviada, MotivoPausa
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.modelos.vm import Disco

from .apoyo_lote import ControlAutomatico, crear_banco, crear_banco_http
from .apoyo_mvp3 import definicion_filas, fila
from .test_lote_inyeccion_fallos import (
    ESTADOS_CON_POSIBLE_CREACION,
    FALLOS_HTTP,
    INCIERTOS,
    INCIERTOS_HTTP,
    TODOS,
    _etapas_correctas,
    _regla_en,
    _verificar_inv_l1,
)

# Plan: VMIDs [100, 105, 101, 102]. 105 es explícito; el resto salen de ``vmid_inicial=100``.
OBJETIVOS = [100, 105, 102]  # primera, intermedia (la de VMID explícito) y última


def _definicion(**kw):
    return definicion_filas(
        [
            fila("pf-01", cores=1, memoria_mib=1024, discos=[Disco("datos", 8)]),
            fila(
                "pf-02",
                vmid=105,
                cores=4,
                memoria_mib=8192,
                discos=[Disco("datos", 64), Disco("datos", 16)],
            ),
            fila("pf-03", cores=2, memoria_mib=4096),
            fila("pf-04", cores=8, memoria_mib=16384, discos=[Disco("datos", 128)]),
        ],
        vmid_inicial=100,
        **kw,
    )


def _preparar(banco):
    """Planifica ANTES de inyectar fallos y observa el estado en el instante de cada POST."""
    plan = banco.planificar(_definicion())
    assert not plan.bloqueado, plan.problemas
    assert [e.vmid for e in plan.elementos] == [100, 105, 101, 102]
    visto = {}

    def _al_post(vmid):
        e = banco.ultimo[vmid]
        visto[vmid] = (e.estado, e.post_intentado)

    banco.cluster.al_post = _al_post
    return plan, visto


def _verificar_cuerpos(banco, plan):
    """Cada POST que salió lleva exactamente la configuración de SU fila (no la de otra)."""
    por_vmid = {e.vmid: e for e in plan.elementos}
    for vmid, cuerpo in banco.cluster.cuerpos_post.items():
        esperado = construir_parametros(por_vmid[vmid].cfg, banco.inv, plan.version_validacion)
        assert cuerpo == esperado, vmid
        assert banco.cluster.nodos_post[vmid] == por_vmid[vmid].nodo


# --- Camino feliz --------------------------------------------------------------------------------


def test_camino_feliz_un_post_por_vmid_con_la_configuracion_de_cada_fila():
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK] * 4
    assert dict(banco.cluster.posts) == {100: 1, 105: 1, 101: 1, 102: 1}
    _verificar_cuerpos(banco, plan)
    cuerpos = banco.cluster.cuerpos_post
    assert [cuerpos[v]["cores"] for v in (100, 105, 101, 102)] == ["1", "4", "2", "8"]
    assert [cuerpos[v]["memory"] for v in (100, 105, 101, 102)] == ["1024", "8192", "4096", "16384"]
    assert (
        "scsi1" in cuerpos[105] and "scsi1" not in cuerpos[100]
    )  # solo la fila 2 tiene dos discos
    assert [cuerpos[v]["name"] for v in (100, 105, 101, 102)] == [
        "pf-01",
        "pf-02",
        "pf-03",
        "pf-04",
    ]
    _verificar_inv_l1(banco, libro)


def test_las_etiquetas_del_lote_viajan_en_cada_post_y_la_reconsulta_precede_a_cada_envio():
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    for e in plan.elementos:
        assert set(banco.cluster.cuerpos_post[e.vmid]["tags"].split(";")) == {
            "proxlaunch",
            f"lote-{plan.id_lote}",
        }
    assert all(x.estado == EstadoMV.OK for x in libro.instantanea())


# --- Nivel 1: cliente real sobre el clúster simulado ----------------------------------------------


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", sorted(TODOS))
def test_inv_l1_por_filas_fallo_en_el_post_de_cada_maquina(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, visto = _preparar(banco)
    _regla_en(banco, "POST", r"/qemu$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1
    assert _etapas_correctas(visto)
    e = libro.entrada(objetivo)
    if fallo in INCIERTOS:
        assert e.estado in ESTADOS_CON_POSIBLE_CREACION, e.estado
    otras = [x for x in libro.instantanea() if x.elemento.vmid != objetivo]
    assert all(x.estado != EstadoMV.PENDIENTE for x in otras)
    _verificar_cuerpos(banco, plan)
    motor = banco.motor()
    motor.comprobar_dudosas(libro, banco.observador, ControlLote())
    motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", sorted(TODOS))
def test_inv_l1_por_filas_fallo_en_la_reconsulta_del_vmid_antes_de_enviar(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, visto = _preparar(banco)
    _regla_en(banco, "GET", r"^/cluster/nextid$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts.get(objetivo, 0) == 0  # sin reconsulta no hay envío
    e = libro.entrada(objetivo)
    assert not e.post_intentado and e.estado in (EstadoMV.ERROR, EstadoMV.NO_ENVIADA)
    assert _etapas_correctas(visto)
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", sorted(TODOS))
def test_inv_l1_por_filas_fallo_en_el_sondeo_de_la_tarea_despues_del_upid(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    _regla_en(banco, "GET", r"/tasks/.*/status$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1
    e = libro.entrada(objetivo)
    assert e.upid and e.estado in ESTADOS_CON_POSIBLE_CREACION
    assert e.estado != EstadoMV.NO_CREADA_SEGURA
    motor = banco.motor()
    motor.comprobar_dudosas(libro, banco.observador, ControlLote())
    motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", ["596", "sin_respuesta", "500", "401", "excepcion_inesperada"])
def test_inv_l1_por_filas_fallo_en_la_comprobacion_final_de_la_config(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    _regla_en(banco, "GET", r"/qemu/\d+/config$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert (
        banco.cluster.posts[objetivo] == 1 and libro.entrada(objetivo).estado != EstadoMV.NO_ENVIADA
    )
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", ["596", "sin_respuesta", "500", "excepcion_inesperada"])
def test_inv_l1_por_filas_fallo_al_leer_el_log_de_una_tarea_con_avisos(fallo, objetivo):
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    banco.cluster.exitstatus[objetivo] = "WARNINGS: 1"
    _regla_en(banco, "GET", r"/tasks/.*/log$", objetivo, TODOS[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("valor", [None, "", "no-es-un-upid", 42, {"data": "x"}], ids=repr)
def test_inv_l1_por_filas_respuesta_del_post_sin_upid_valido(valor, objetivo):
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    _regla_en(banco, "POST", r"/qemu$", objetivo, lambda ll: valor)
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1
    assert (
        libro.entrada(objetivo).estado != EstadoMV.ERROR
    )  # RF-L15: el POST llegó, no es «nada creado»
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


def test_inv_l1_por_filas_fallo_inciertos_en_todas_las_maquinas_a_la_vez():
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    banco.cluster.regla("POST", r"/qemu$", INCIERTOS["envio_incierto"])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro)
    assert dict(banco.cluster.posts) == {100: 1, 105: 1, 101: 1, 102: 1}


def test_inv_l1_por_filas_fallos_distintos_en_cada_punto_de_cada_maquina_a_la_vez():
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    _regla_en(banco, "GET", r"^/cluster/nextid$", 100, TODOS["500"])
    _regla_en(banco, "POST", r"/qemu$", 105, INCIERTOS["envio_incierto"])
    _regla_en(banco, "GET", r"/tasks/.*/status$", 102, TODOS["sin_respuesta"])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro)
    motor = banco.motor()
    for _ in range(2):
        motor.comprobar_dudosas(libro, banco.observador, ControlLote())
        motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro)


@pytest.mark.parametrize("nodos", [("pve1", "pve2"), ("pve1", "pve2", "pve3", "pve4", "pve5")])
def test_inv_l1_por_filas_con_varios_nodos_y_fallos_inciertos_en_paralelo(nodos):
    banco = crear_banco(nodos)
    filas = [
        fila(
            f"pf-{i:02d}",
            cores=1 + i % 4,
            memoria_mib=512 * (1 + i % 3),
            nodo="pve2" if i == 4 else None,
            vmid=150 if i == 7 else None,
        )
        for i in range(10)
    ]
    plan = banco.planificar(
        definicion_filas(filas, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS)
    )
    assert not plan.bloqueado
    for e in plan.elementos[::3]:
        _regla_en(banco, "POST", r"/qemu$", e.vmid, INCIERTOS["envio_incierto"])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro)
    assert sum(banco.cluster.posts.values()) == 10
    _verificar_cuerpos(banco, plan)
    assert banco.cluster.max_post_por_nodo <= 1  # una creación por nodo a la vez


def test_inv_l1_por_filas_cancelar_en_cada_punto_no_duplica_envios():
    for objetivo in OBJETIVOS:
        banco = crear_banco(("pve1",))
        plan, _ = _preparar(banco)
        control = ControlLote()
        previo = banco.cluster.al_post

        def _al_post(vmid, control=control, objetivo=objetivo, previo=previo):
            previo(vmid)
            if vmid == objetivo:
                control.cancelar()

        banco.cluster.al_post = _al_post
        libro = banco.ejecutar(plan, control)
        _verificar_inv_l1(banco, libro, objetivo)
        no_enviadas = [e for e in libro.instantanea() if e.estado == EstadoMV.NO_ENVIADA]
        assert all(e.motivo_no_enviada == MotivoNoEnviada.CANCELADO for e in no_enviadas)
        banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
        _verificar_inv_l1(banco, libro, objetivo)
        assert banco.cluster.posts.get(objetivo, 0) == 1  # la que estaba en vuelo sigue siendo una


def test_cancelar_antes_del_primer_envio_no_envia_nada_en_por_filas():
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    banco.cluster.reiniciar_llamadas()
    control = ControlLote()
    control.cancelar()
    libro = banco.ejecutar(plan, control)
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.NO_ENVIADA] * 4
    assert banco.cluster.llamadas == []


# --- Pausa y reanudación (CA-L14.2/L14.3 sobre filas) ---------------------------------------------


def test_un_error_global_pausa_el_lote_por_filas_y_al_continuar_cada_fila_sale_una_sola_vez():
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    error = ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "HTTP 401")
    regla = banco.cluster.regla("POST", r"/qemu$", error, veces=1)  # falla solo el primer POST
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(plan, control)
    assert control.pausas and control.pausas[0][0] == MotivoPausa.ERROR_GLOBAL
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.ERROR] + [EstadoMV.PENDIENTE] * 3
    assert dict(banco.cluster.posts) == {100: 1}
    assert regla.disparos == 1
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.ERROR] + [EstadoMV.OK] * 3
    assert dict(banco.cluster.posts) == {100: 1, 105: 1, 101: 1, 102: 1}  # la 100 no se reenvía
    _verificar_cuerpos(banco, plan)
    _verificar_inv_l1(banco, libro)


def test_tres_fallos_seguidos_con_la_misma_causa_pausan_y_quedan_las_pendientes():
    banco = crear_banco(("pve1",))
    sin_espacio = "lvcreate error: Volume group has insufficient free space"
    for vmid in (100, 105, 101):
        banco.cluster.exitstatus[vmid] = sin_espacio
    plan, _ = _preparar(banco)
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(plan, control)
    assert control.pausas[0][0] == MotivoPausa.REPETIDO
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.ERROR] * 3 + [EstadoMV.PENDIENTE]
    assert sorted(banco.cluster.posts) == [100, 101, 105]


def test_detener_tras_la_pausa_deja_las_filas_pendientes_no_enviadas():
    banco = crear_banco(("pve1",))
    plan, _ = _preparar(banco)
    banco.cluster.regla("POST", r"/qemu$", ErrorProxLaunch(CodigoError.SESION_EXPIRADA), veces=1)
    libro = banco.ejecutar(plan, ControlAutomatico("cancelar"))
    estados = [e.estado for e in libro.instantanea()]
    assert estados == [EstadoMV.ERROR] + [EstadoMV.NO_ENVIADA] * 3
    assert dict(banco.cluster.posts) == {100: 1}


# --- Concurrencia ---------------------------------------------------------------------------------


def test_como_maximo_4_nodos_a_la_vez_y_una_creacion_por_nodo_con_filas_distintas():
    banco = crear_banco(("pve1", "pve2", "pve3", "pve4", "pve5", "pve6"))
    banco.cluster.barrera = threading.Barrier(MAX_NODOS_PARALELOS, timeout=5)
    filas = [fila(f"pf-{i:02d}", cores=1 + i % 3, memoria_mib=512 * (1 + i % 4)) for i in range(12)]
    plan = banco.planificar(
        definicion_filas(filas, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS)
    )
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert all(e.estado == EstadoMV.OK for e in libro.instantanea())
    assert banco.cluster.max_nodos_con_post == MAX_NODOS_PARALELOS
    assert banco.cluster.max_post_por_nodo == 1
    _verificar_cuerpos(banco, plan)
    _verificar_inv_l1(banco, libro)


# --- Nivel 2: TransporteHttp real con respuestas HTTP simuladas -----------------------------------


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", sorted(FALLOS_HTTP))
def test_inv_l1_por_filas_http_real_fallo_en_el_post(rsps, fallo, objetivo):
    banco = crear_banco_http(rsps)
    plan, _ = _preparar(banco)
    _regla_en(banco, "POST", r"/qemu$", objetivo, FALLOS_HTTP[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert banco.cluster.posts[objetivo] == 1
    posts_reales = [c for c in rsps.calls if c.request.method == "POST"]
    assert len(posts_reales) == 4  # una petición real por fila: el transporte no reintenta
    if fallo in INCIERTOS_HTTP:
        assert libro.entrada(objetivo).estado in ESTADOS_CON_POSIBLE_CREACION
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    _verificar_inv_l1(banco, libro, objetivo)


@pytest.mark.parametrize("objetivo", OBJETIVOS)
@pytest.mark.parametrize("fallo", ["http_596", "read_timeout", "http_500", "conexion_abortada"])
def test_inv_l1_por_filas_http_real_fallo_en_el_sondeo(rsps, fallo, objetivo):
    banco = crear_banco_http(rsps)
    plan, _ = _preparar(banco)
    _regla_en(banco, "GET", r"/tasks/.*/status$", objetivo, FALLOS_HTTP[fallo])
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    _verificar_inv_l1(banco, libro, objetivo)
    assert (
        libro.entrada(objetivo).upid and libro.entrada(objetivo).estado != EstadoMV.NO_CREADA_SEGURA
    )
