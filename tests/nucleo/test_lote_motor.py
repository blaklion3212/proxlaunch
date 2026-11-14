"""Motor del lote: ejecución, errores por MV, pausas, cancelación, concurrencia y reanudación
(RF-L12 a RF-L17, INV-L1 a INV-L4). Cliente real sobre un clúster simulado y reloj simulado.

Las inyecciones de fallo exhaustivas de INV-L1 están en ``test_lote_inyeccion_fallos.py``.
"""

import threading
from dataclasses import replace

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import (
    MAX_NODOS_PARALELOS,
    MAX_PETICIONES_SIMULTANEAS,
    UMBRAL_PAUSA_ERRORES,
)
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    EstadoMV,
    MotivoNoEnviada,
    MotivoPausa,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.modelos import Bridge
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_lote import (
    NORMAL,
    ControlAutomatico,
    ControlConEspera,
    crear_banco,
    definicion,
    envio_incierto,
    nodo_caido,
    plantilla,
)

SIN_ESPACIO = (
    "lvcreate 'pve/vm-{vmid}-disk-0' error: Volume group \"pve\" has insufficient free space "
    "(1 extents): 8192 required."
)


def _estados(libro):
    return [e.estado for e in libro.instantanea()]


def _vmid_de(llamada):
    return int(llamada.datos["vmid"])


def _en_vmid(*vmids, accion):
    """Regla para un POST: ``accion`` solo si el VMID es uno de ``vmids``; si no, sigue normal."""

    def _regla(llamada):
        return accion(llamada) if _vmid_de(llamada) in vmids else NORMAL

    return _regla


def _falla_post(*vmids, error):
    def _acc(llamada):
        raise error

    return _en_vmid(*vmids, accion=_acc)


def _lote(banco, cantidad, **kw):
    return banco.planificar(definicion(cantidad, vmid_inicial=100, **kw))


# --- Camino feliz y estados (CA-L12.7) ------------------------------------------------------------


def test_camino_feliz_crea_todas_con_un_post_por_vmid(banco):
    plan = _lote(banco, 5)
    libro = banco.ejecutar(plan)
    assert _estados(libro) == [EstadoMV.OK] * 5
    assert dict(banco.cluster.posts) == {100: 1, 101: 1, 102: 1, 103: 1, 104: 1}
    assert libro.terminado()
    assert libro.id_lote == plan.id_lote


def test_ca_l12_7_cada_maquina_recorre_los_estados_en_orden(banco):
    banco.ejecutar(_lote(banco, 2))
    esperado = ["validando", "enviando", "creando", "comprobando", "ok"]
    for vmid in (100, 101):
        secuencia = []
        for e in banco.eventos:
            if e.elemento.vmid == vmid and (not secuencia or secuencia[-1] != e.estado.value):
                secuencia.append(e.estado.value)
        assert secuencia == esperado, secuencia


def test_inv_l1_el_estado_enviando_se_registra_siempre_antes_del_post(banco):
    visto = {}

    def _al_post(vmid):
        e = banco.ultimo[vmid]
        visto[vmid] = (e.estado, e.post_intentado)

    banco.cluster.al_post = _al_post
    banco.ejecutar(_lote(banco, 4))
    assert visto == {v: (EstadoMV.ENVIANDO, True) for v in range(100, 104)}


def test_el_upid_queda_en_el_libro_y_en_el_observador(banco):
    libro = banco.ejecutar(_lote(banco, 2))
    for e in libro.instantanea():
        assert e.upid and f":qmcreate:{e.elemento.vmid}:" in e.upid
        assert e.t_inicio is not None and e.t_fin is not None


def test_ca_l12_1_el_post_lleva_la_etiqueta_del_lote_y_el_nombre_del_plan(banco):
    plan = _lote(banco, 3)
    banco.ejecutar(plan)
    for e in plan.elementos:
        cuerpo = banco.cluster.cuerpos_post[e.vmid]
        assert cuerpo["name"] == e.nombre
        assert cuerpo["tags"] == f"proxlaunch;lote-{plan.id_lote}"
        assert banco.cluster.nodos_post[e.vmid] == e.nodo


def test_ca_l12_4_inv_l2_antes_de_cada_post_se_reconsulta_el_vmid(banco):
    banco.ejecutar(_lote(banco, 3))
    orden = [
        (c.metodo, c.ruta, (c.datos or {}).get("vmid"), (c.params or {}).get("vmid"))
        for c in banco.cluster.llamadas
    ]
    for vmid in (100, 101, 102):
        i_post = next(i for i, c in enumerate(orden) if c[0] == "POST" and c[2] == str(vmid))
        previas = [c for c in orden[:i_post] if c[1] == "/cluster/nextid" and c[3] == vmid]
        assert len(previas) >= 2  # una al planificar y otra justo antes del POST


def test_ca_rnf_l05_cien_maquinas_con_mock_instantaneo_en_menos_de_60_s_simulados():
    banco = crear_banco(("pve1", "pve2", "pve3", "pve4"))
    plan = banco.planificar(definicion(100, vmid_inicial=1000))
    libro = banco.ejecutar(plan)
    assert _estados(libro) == [EstadoMV.OK] * 100
    assert banco.reloj.ahora() <= 60.0
    assert max(banco.cluster.posts.values()) == 1
    assert banco.cluster.max_nodos_con_post <= MAX_NODOS_PARALELOS


def test_el_lote_de_una_maquina_pasa_por_el_motor_como_en_m1(banco):
    plan = banco.planificar(definicion(1, prefijo="", plantilla_vm=plantilla(nombre="srv")))
    libro = banco.ejecutar(plan)
    (e,) = libro.instantanea()
    assert e.estado == EstadoMV.OK and e.error is None
    assert banco.cluster.posts[100] == 1


# --- Errores por MV que no detienen el lote (RF-L14) ----------------------------------------------


def test_ca_l14_1_una_maquina_que_falla_por_espacio_no_detiene_a_las_demas(banco):
    banco.cluster.exitstatus[101] = SIN_ESPACIO.format(vmid=101)
    libro = banco.ejecutar(_lote(banco, 5))
    assert _estados(libro) == [
        EstadoMV.OK,
        EstadoMV.ERROR,
        EstadoMV.OK,
        EstadoMV.OK,
        EstadoMV.OK,
    ]
    assert libro.entrada(101).error.codigo == CodigoError.SIN_ESPACIO
    assert libro.contadores() == {EstadoMV.OK: 4, EstadoMV.ERROR: 1}
    assert all(banco.cluster.posts[v] == 1 for v in range(100, 105))


def test_ca_l14_1_una_tarea_fallida_con_config_a_medias_es_parcial(banco):
    banco.cluster.exitstatus[101] = "unexpected failure"
    banco.cluster.parciales = {101}
    banco.cluster.regla("GET", r"qemu/101/config$", lambda ll: {"name": "web-02"})
    libro = banco.ejecutar(_lote(banco, 3))
    assert libro.entrada(101).estado == EstadoMV.PARCIAL
    assert libro.entrada(102).estado == EstadoMV.OK


def test_ca_l14_6_el_texto_original_de_proxmox_se_conserva_en_el_error(banco):
    banco.cluster.exitstatus[100] = SIN_ESPACIO.format(vmid=100)
    libro = banco.ejecutar(_lote(banco, 1))
    assert "insufficient free space" in libro.entrada(100).error.detalle_tecnico


def test_ca_l14_7_un_error_de_validacion_imprevisto_falla_esa_maquina_y_las_demas_siguen():
    banco = crear_banco(("pve1", "pve2"))
    d = definicion(4, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS)  # pve1, pve2, pve1, pve2
    plan = banco.planificar(d)
    assert [e.nodo for e in plan.elementos] == ["pve1", "pve2", "pve1", "pve2"]
    # El bridge de pve2 desaparece después de planificar.
    banco.inv.bridges["pve2"] = (Bridge("vmbr9", "bridge", False),)
    libro = banco.ejecutar(plan)
    assert _estados(libro) == [EstadoMV.OK, EstadoMV.ERROR, EstadoMV.OK, EstadoMV.ERROR]
    assert banco.cluster.posts[101] == banco.cluster.posts[103] == 0  # nada se envió
    assert libro.entrada(101).error.codigo == CodigoError.PARAMETRO_INVALIDO


def test_ca_l03_8_vmid_ocupado_por_otro_entre_el_resumen_y_el_envio_falla_solo_esa_maquina(banco):
    plan = _lote(banco, 3)
    banco.cluster.ocupados = {101}  # otro usuario lo toma después del resumen
    libro = banco.ejecutar(plan)
    assert _estados(libro) == [EstadoMV.OK, EstadoMV.ERROR, EstadoMV.OK]
    assert libro.entrada(101).error.codigo == CodigoError.VMID_OCUPADO
    assert banco.cluster.posts[101] == 0
    assert 101 not in banco.cluster.vms  # no se reasigna ni se crea con otro número


def test_ca_l03_8_vmid_ocupado_detectado_por_el_propio_post_tambien_falla_esa_maquina(banco):
    banco.cluster.regla(
        "POST",
        r"/qemu$",
        _falla_post(
            101,
            error=ErrorProxLaunch(
                CodigoError.VMID_OCUPADO, {"vmid": "101"}, "VM 101 already exists on node 'pve1'"
            ),
        ),
    )
    libro = banco.ejecutar(_lote(banco, 3))
    assert _estados(libro) == [EstadoMV.OK, EstadoMV.ERROR, EstadoMV.OK]
    assert banco.cluster.posts[101] == 1  # un solo intento: no se reintenta con otro VMID


def test_ca_l12_8_una_excepcion_inesperada_antes_del_post_marca_error_y_no_aborta_el_lote(banco):
    class _Servicio(ServicioCreacion):
        def crear(self, cfg, inv, al_cambiar_etapa, cancelado, *, al_enviar=None):
            if cfg.vmid == 101:
                raise RuntimeError("fallo de programación")
            return super().crear(cfg, inv, al_cambiar_etapa, cancelado, al_enviar=al_enviar)

    libro = banco.ejecutar(_lote(banco, 3), motor=banco.motor(fabrica_creacion=_Servicio))
    assert _estados(libro) == [EstadoMV.OK, EstadoMV.ERROR, EstadoMV.OK]
    assert libro.entrada(101).error.codigo == CodigoError.DESCONOCIDO
    assert banco.cluster.posts[101] == 0


def test_ca_l12_8_una_excepcion_tras_enviar_deja_la_maquina_incierta_sin_reenviar(banco):
    class _Servicio(ServicioCreacion):
        def crear(self, cfg, inv, al_cambiar_etapa, cancelado, *, al_enviar=None):
            if cfg.vmid == 101:
                al_cambiar_etapa(ServicioCreacion_ENVIANDO)
                banco.cluster.atender(
                    "POST", f"/nodes/{cfg.nodo}/qemu", None, {"vmid": "101", "name": cfg.nombre}
                )
                raise RuntimeError("fallo tras enviar")
            return super().crear(cfg, inv, al_cambiar_etapa, cancelado, al_enviar=al_enviar)

    from proxlaunch.nucleo.modelos.tarea import Etapa

    ServicioCreacion_ENVIANDO = Etapa.ENVIANDO
    # La config no se puede leer: no se sabe si existe.
    banco.cluster.regla("GET", r"qemu/101/config$", nodo_caido("pve1", 596))
    libro = banco.ejecutar(_lote(banco, 3), motor=banco.motor(fabrica_creacion=_Servicio))
    e = libro.entrada(101)
    assert e.estado == EstadoMV.CONEXION_PERDIDA
    assert e.post_intentado
    assert banco.cluster.posts[101] == 1
    assert libro.entrada(102).estado == EstadoMV.OK


def test_rnf_l11_un_fallo_del_observador_no_detiene_el_motor(banco):
    def _observador_roto(entrada):
        raise RuntimeError("la interfaz falló")

    libro = banco.motor().ejecutar(_lote(banco, 3), banco.inv, _observador_roto, ControlLote())
    assert _estados(libro) == [EstadoMV.OK] * 3


# --- Pausa por error global y por errores repetidos (RF-L14) --------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "HTTP 401"),
        ErrorProxLaunch(CodigoError.HUELLA_CAMBIADA, {"host": "10.0.0.1"}, "fingerprint"),
        ErrorProxLaunch(CodigoError.ETIQUETA_RECHAZADA, {}, "Sys.Modify for modifying tag"),
        ErrorProxLaunch(
            CodigoError.PERMISO_INSUFICIENTE,
            {"privilegio": "VM.Allocate", "ruta": "/vms/100"},
            "Permission check failed (/vms/100, VM.Allocate)",
        ),
    ],
    ids=["sesion", "huella", "etiqueta", "permiso"],
)
def test_ca_l14_2_un_error_global_pausa_tras_el_primer_caso_y_no_envia_mas(banco, error):
    banco.cluster.regla("POST", r"/qemu$", _falla_post(100, error=error))
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 5), control)
    assert control.pausas[0][0] == MotivoPausa.ERROR_GLOBAL
    assert control.pausas[0][1].codigo == error.codigo
    assert _estados(libro) == [EstadoMV.ERROR] + [EstadoMV.PENDIENTE] * 4
    assert dict(banco.cluster.posts) == {100: 1}  # el resto "fallaría igual": no se envía


def test_ca_l14_2_un_403_real_al_crear_infiere_vm_allocate(banco):
    banco.cluster.regla(
        "POST", r"/qemu$", _falla_post(100, error=ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE))
    )
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 3), control)
    assert control.pausas[0][0] == MotivoPausa.ERROR_GLOBAL
    assert libro.entrada(100).error.params["privilegio"] == "VM.Allocate"


def test_ca_l14_2_la_sesion_expirada_antes_del_post_tambien_pausa(banco):
    banco.cluster.regla(
        "GET", r"^/cluster/nextid$", ErrorProxLaunch(CodigoError.SESION_EXPIRADA), veces=None
    )
    plan_rule_off = banco.cluster.reglas[-1]
    plan_rule_off.veces = 0  # permite planificar
    plan = _lote(banco, 3)
    plan_rule_off.veces = None
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(plan, control)
    assert control.pausas[0][0] == MotivoPausa.ERROR_GLOBAL
    assert banco.cluster.total("POST") == 0
    assert libro.entrada(100).estado == EstadoMV.ERROR


def test_ca_l14_2_el_motor_espera_la_decision_y_detener_deja_las_pendientes_no_enviadas(banco):
    banco.cluster.regla(
        "POST", r"/qemu$", _falla_post(100, error=ErrorProxLaunch(CodigoError.SESION_EXPIRADA))
    )
    control = ControlConEspera()
    resultado = {}
    hilo = threading.Thread(
        target=lambda: resultado.update(libro=banco.ejecutar(_lote(banco, 4), control))
    )
    hilo.start()
    assert control.esperando.wait(5), "el motor debió quedarse esperando la decisión del usuario"
    assert control.motivo_pausa == MotivoPausa.ERROR_GLOBAL
    assert banco.cluster.total("POST") == 1  # sigue en pausa: nada más sale
    control.cancelar()  # "Detener": se comporta como cancelación
    hilo.join(5)
    assert not hilo.is_alive()
    libro = resultado["libro"]
    assert [e.estado for e in libro.instantanea()[1:]] == [EstadoMV.NO_ENVIADA] * 3
    assert {e.motivo_no_enviada for e in libro.instantanea()[1:]} == {MotivoNoEnviada.PAUSA}
    assert banco.cluster.total("POST") == 1


def test_ca_l14_4_continuar_reanuda_y_no_vuelve_a_preguntar_por_esa_causa(banco):
    error = ErrorProxLaunch(CodigoError.ETIQUETA_RECHAZADA, {}, "Sys.Modify for modifying tag")
    banco.cluster.regla("POST", r"/qemu$", _falla_post(100, 101, 102, 103, error=error))
    control = ControlConEspera()
    resultado = {}
    hilo = threading.Thread(
        target=lambda: resultado.update(libro=banco.ejecutar(_lote(banco, 4), control))
    )
    hilo.start()
    assert control.esperando.wait(5)
    control.reanudar(ignorar_causa=True)  # "Continuar"
    hilo.join(5)
    assert not hilo.is_alive()
    libro = resultado["libro"]
    assert _estados(libro) == [EstadoMV.ERROR] * 4  # las 4 se intentaron, cada una una vez
    assert dict(banco.cluster.posts) == {100: 1, 101: 1, 102: 1, 103: 1}
    assert control.motivo_pausa is None  # no hubo una segunda pausa por la misma causa


def test_ca_l14_3_tres_fallos_seguidos_con_la_misma_causa_pausan_el_lote(banco):
    for vmid in (100, 101, 102):
        banco.cluster.exitstatus[vmid] = SIN_ESPACIO.format(vmid=vmid)
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 6), control)
    assert UMBRAL_PAUSA_ERRORES == 3
    assert control.pausas[0][0] == MotivoPausa.REPETIDO
    assert control.pausas[0][1].codigo == CodigoError.SIN_ESPACIO
    assert _estados(libro) == [EstadoMV.ERROR] * 3 + [EstadoMV.PENDIENTE] * 3
    assert sorted(banco.cluster.posts) == [100, 101, 102]


def test_ca_l14_3_dos_fallos_seguidos_no_pausan(banco):
    for vmid in (100, 101):
        banco.cluster.exitstatus[vmid] = SIN_ESPACIO.format(vmid=vmid)
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 5), control)
    assert control.pausas == []
    assert _estados(libro) == [EstadoMV.ERROR] * 2 + [EstadoMV.OK] * 3


def test_ca_l14_3_fallos_no_consecutivos_no_pausan(banco):
    for vmid in (100, 102, 104):
        banco.cluster.exitstatus[vmid] = SIN_ESPACIO.format(vmid=vmid)
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 6), control)
    assert control.pausas == []
    assert libro.contadores() == {EstadoMV.ERROR: 3, EstadoMV.OK: 3}


def test_ca_l14_5_un_nodo_que_no_responde_solo_detiene_a_sus_maquinas():
    banco = crear_banco(("pve1", "pve2"))
    plan = banco.planificar(definicion(6, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    de_pve2 = {e.vmid for e in plan.elementos if e.nodo == "pve2"}
    assert len(de_pve2) == 3

    def _nodo_caido(llamada):
        if llamada.params and llamada.params.get("vmid") in de_pve2:
            raise nodo_caido("pve2", 596)
        return NORMAL

    banco.cluster.regla("GET", r"^/cluster/nextid$", _nodo_caido)
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(plan, control)
    for e in libro.instantanea():
        if e.elemento.nodo == "pve1":
            assert e.estado == EstadoMV.OK
    pve2 = [e for e in libro.instantanea() if e.elemento.nodo == "pve2"]
    assert pve2[0].estado == EstadoMV.ERROR
    assert pve2[0].error.codigo == CodigoError.NODO_NO_DISPONIBLE
    assert [e.estado for e in pve2[1:]] == [EstadoMV.NO_ENVIADA] * 2
    assert {e.motivo_no_enviada for e in pve2[1:]} == {MotivoNoEnviada.NODO_CAIDO}
    assert not set(banco.cluster.posts) & de_pve2
    assert control.pausas == []  # un nodo caído no pausa el lote entero


# --- Cancelación (RF-L16) -------------------------------------------------------------------------


def test_ca_l16_1_cancelar_antes_del_primer_envio_no_envia_nada(banco):
    plan = _lote(banco, 4)
    banco.cluster.reiniciar_llamadas()
    control = ControlLote()
    control.cancelar()
    libro = banco.ejecutar(plan, control)
    assert _estados(libro) == [EstadoMV.NO_ENVIADA] * 4
    assert {e.motivo_no_enviada for e in libro.instantanea()} == {MotivoNoEnviada.CANCELADO}
    assert banco.cluster.llamadas == []
    assert banco.cluster.total("POST") == 0


def test_ca_l16_1_y_l16_4_cancelar_en_pleno_post_la_maquina_en_vuelo_sigue_y_las_demas_no_salen(
    banco,
):
    control = ControlLote()
    banco.cluster.al_post = lambda vmid: control.cancelar() if vmid == 101 else None
    libro = banco.ejecutar(_lote(banco, 5), control)
    estados = _estados(libro)
    assert estados[0] == EstadoMV.OK
    assert estados[1] == EstadoMV.OK  # la que estaba en pleno POST nunca es "no enviada"
    assert estados[2:] == [EstadoMV.NO_ENVIADA] * 3
    assert sorted(banco.cluster.posts) == [100, 101]
    assert {e.motivo_no_enviada for e in libro.instantanea()[2:]} == {MotivoNoEnviada.CANCELADO}


def test_ca_l16_2_tras_cancelar_se_sigue_esperando_el_desenlace_de_la_tarea_enviada(banco):
    banco.cluster.tareas_en_curso[100] = 4  # 4 sondeos "running" antes de terminar
    control = ControlLote()
    banco.cluster.al_post = lambda vmid: control.cancelar()
    libro = banco.ejecutar(_lote(banco, 3), control)
    e = libro.entrada(100)
    assert e.estado == EstadoMV.OK  # se esperó hasta el final para informar con certeza
    assert banco.reloj.ahora() >= 4 * 1.5
    assert [x.estado for x in libro.instantanea()[1:]] == [EstadoMV.NO_ENVIADA] * 2


def test_ca_l16_2_dejar_de_esperar_deja_la_tarea_en_conexion_perdida_con_su_upid(banco):
    banco.cluster.tareas_en_curso[100] = 10_000  # la tarea nunca termina
    control = ControlLote()
    banco.cluster.al_post = lambda vmid: control.dejar_de_esperar()
    libro = banco.ejecutar(_lote(banco, 3), control)
    e = libro.entrada(100)
    assert e.estado == EstadoMV.CONEXION_PERDIDA
    assert e.upid and ":qmcreate:100:" in e.upid
    assert [x.estado for x in libro.instantanea()[1:]] == [EstadoMV.NO_ENVIADA] * 2
    assert banco.cluster.total("DELETE") == 0  # no se detiene ninguna tarea en Proxmox
    assert dict(banco.cluster.posts) == {100: 1}


def test_ca_l16_5_cancelar_tras_el_ultimo_envio_no_cambia_nada(banco):
    control = ControlLote()
    libro = banco.ejecutar(_lote(banco, 3), control)
    antes = libro.instantanea()
    control.cancelar()
    assert libro.instantanea() == antes
    assert _estados(libro) == [EstadoMV.OK] * 3


def test_ca_l16_1_cancelar_vacia_las_colas_de_todos_los_nodos():
    banco = crear_banco(("pve1", "pve2"))
    plan = banco.planificar(definicion(8, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    control = ControlLote()
    banco.cluster.al_post = lambda vmid: control.cancelar()
    libro = banco.ejecutar(plan, control)
    enviadas = set(banco.cluster.posts)
    assert 1 <= len(enviadas) <= 2  # a lo sumo la primera de cada nodo
    for e in libro.instantanea():
        assert (e.estado == EstadoMV.NO_ENVIADA) is (e.elemento.vmid not in enviadas)


def test_un_control_cancelado_no_se_rearma():
    control = ControlLote()
    control.cancelar()
    control.reanudar()
    assert control.cancelado.is_set()


# --- Concurrencia (CA-L12.3, CA-L12.4) ------------------------------------------------------------


def _banco_de_nodos(n):
    return crear_banco(tuple(f"pve{i}" for i in range(1, n + 1)))


def test_ca_l12_3_como_maximo_4_nodos_a_la_vez_y_una_creacion_por_nodo():
    banco = _banco_de_nodos(6)
    banco.cluster.barrera = threading.Barrier(MAX_NODOS_PARALELOS, timeout=5)
    plan = banco.planificar(definicion(12, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    libro = banco.ejecutar(plan)
    assert _estados(libro) == [EstadoMV.OK] * 12
    assert banco.cluster.max_nodos_con_post == MAX_NODOS_PARALELOS  # se usa el paralelismo
    assert banco.cluster.max_post_por_nodo == 1
    assert banco.cluster.max_post_total <= MAX_NODOS_PARALELOS


def test_ca_l12_4_el_total_de_peticiones_simultaneas_no_pasa_de_8():
    banco = _banco_de_nodos(6)
    banco.cluster.barrera = threading.Barrier(MAX_NODOS_PARALELOS, timeout=5)
    plan = banco.planificar(definicion(18, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    banco.cluster.max_peticiones = 0
    banco.ejecutar(plan)
    assert 1 < banco.cluster.max_peticiones <= MAX_PETICIONES_SIMULTANEAS


def test_ca_l12_3_las_maquinas_de_un_nodo_salen_en_el_orden_del_plan():
    banco = _banco_de_nodos(2)
    orden = []
    banco.cluster.al_post = orden.append
    plan = banco.planificar(definicion(10, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    banco.ejecutar(plan)
    for nodo_ in ("pve1", "pve2"):
        del_plan = [e.vmid for e in plan.elementos if e.nodo == nodo_]
        assert [v for v in orden if v in del_plan] == del_plan


def test_ca_l12_3_en_modo_secuencial_el_orden_global_es_el_del_plan():
    banco = _banco_de_nodos(3)
    orden = []
    banco.cluster.al_post = orden.append
    plan = banco.planificar(definicion(9, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    banco.ejecutar(plan, motor=banco.motor(max_nodos=1))
    assert orden == [e.vmid for e in plan.elementos]
    assert banco.cluster.max_nodos_con_post == 1
    assert banco.cluster.max_post_total == 1


def test_ca_l12_3_un_nodo_con_muchas_maquinas_nunca_tiene_dos_creaciones_a_la_vez():
    banco = _banco_de_nodos(2)
    banco.cluster.barrera = threading.Barrier(2, timeout=5)
    plan = banco.planificar(definicion(10, vmid_inicial=100, algoritmo=Algoritmo.POR_TURNOS))
    banco.ejecutar(plan)
    assert banco.cluster.max_post_por_nodo == 1
    assert banco.cluster.max_nodos_con_post == 2


# --- Envío incierto y reconciliación integrada (RF-L15) -------------------------------------------


def _post_incierto(banco, *vmids, creada=True, con_etiqueta=True):
    """Los POST de ``vmids`` fallan con 596 después de (o sin) llegar al servidor."""

    def _acc(llamada):
        vmid = _vmid_de(llamada)
        if creada:
            tags = llamada.datos.get("tags") if con_etiqueta else None
            banco.cluster.agregar_vm(vmid, "pve1", llamada.datos["name"], tags=tags)
        raise envio_incierto()

    banco.cluster.regla("POST", r"/qemu$", _en_vmid(*vmids, accion=_acc))


def test_ca_l15_1_un_596_en_el_post_no_reenvia_y_el_lote_continua(banco):
    _post_incierto(banco, 100, creada=False)
    libro = banco.ejecutar(_lote(banco, 3))
    assert banco.cluster.posts[100] == 1
    assert libro.entrada(100).estado in (EstadoMV.NO_CREADA_SEGURA, EstadoMV.CONEXION_PERDIDA)
    assert libro.entrada(101).estado == libro.entrada(102).estado == EstadoMV.OK
    assert dict(banco.cluster.posts) == {100: 1, 101: 1, 102: 1}


def test_ca_l15_2_596_con_entrega_real_y_etiqueta_propia_termina_ok_con_aviso(banco):
    _post_incierto(banco, 101, creada=True, con_etiqueta=True)
    libro = banco.ejecutar(_lote(banco, 3))
    e = libro.entrada(101)
    assert e.estado == EstadoMV.OK
    assert "creada_tras_comprobar" in e.avisos
    assert banco.cluster.posts[101] == 1


def test_ca_l15_2_no_existe_en_las_tres_comprobaciones_es_no_creada_segura_a_los_15_s(banco):
    _post_incierto(banco, 100, creada=False)
    libro = banco.ejecutar(_lote(banco, 1))
    e = libro.entrada(100)
    assert e.estado == EstadoMV.NO_CREADA_SEGURA
    assert banco.reloj.ahora() >= 15.0  # t = 0, +5, +15 con el reloj simulado
    assert len(banco.cluster.llamadas_a("GET", r"qemu/100/config$")) == 3
    assert banco.cluster.posts[100] == 1  # nunca se reenvía sola (CA-L15.4)


def test_ca_l15_5_existe_sin_la_etiqueta_del_lote_no_se_confirma_la_propiedad(banco):
    _post_incierto(banco, 100, creada=True, con_etiqueta=False)
    libro = banco.ejecutar(_lote(banco, 1))
    assert libro.entrada(100).estado == EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD
    assert banco.cluster.posts[100] == 1


def test_ca_l15_2_si_no_se_puede_comprobar_la_existencia_sigue_conexion_perdida(banco):
    _post_incierto(banco, 100, creada=False)
    banco.cluster.regla("GET", r"qemu/100/config$", nodo_caido("pve1", 596))
    libro = banco.ejecutar(_lote(banco, 2))
    e = libro.entrada(100)
    assert e.estado == EstadoMV.CONEXION_PERDIDA
    assert e.error.codigo == CodigoError.LOTE_EXISTENCIA_INDETERMINADA
    assert libro.entrada(101).estado == EstadoMV.OK


@pytest.mark.parametrize("posicion", ["primera", "ultima", "todas"])
def test_caso_limite_596_en_la_primera_en_la_ultima_y_en_todas(banco, posicion):
    vmids = {"primera": (100,), "ultima": (104,), "todas": tuple(range(100, 105))}[posicion]
    _post_incierto(banco, *vmids, creada=True)
    libro = banco.ejecutar(_lote(banco, 5))
    assert all(banco.cluster.posts[v] == 1 for v in range(100, 105))
    assert _estados(libro) == [EstadoMV.OK] * 5  # todas se crearon de verdad y se reconocieron


def test_ca_l15_1_596_en_todas_sin_que_existan_no_reenvia_y_termina(banco):
    _post_incierto(banco, *range(100, 104), creada=False)
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 4), control)
    assert set(banco.cluster.posts.values()) == {1}
    assert all(e.post_intentado for e in libro.instantanea() if e.estado != EstadoMV.PENDIENTE)


# --- Sondeo, pérdida de conexión y reanudación (RF-L17) -------------------------------------------


def test_ca_l17_1_una_perdida_de_red_corta_en_el_sondeo_se_recupera_sin_pausa(banco):
    banco.cluster.regla("GET", r"/tasks/.*/status$", nodo_caido("pve1", 596), veces=10)
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 3), control)
    assert _estados(libro) == [EstadoMV.OK] * 3
    assert control.pausas == []


def test_ca_l17_2_una_perdida_sostenida_pausa_por_conexion_y_no_envia_mas(banco):
    banco.cluster.regla("GET", r"/tasks/.*/status$", nodo_caido("pve1", 596), veces=None)
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 4), control)
    e = libro.entrada(100)
    assert e.estado == EstadoMV.CONEXION_PERDIDA and e.upid
    assert control.pausas[0][0] == MotivoPausa.CONEXION
    assert [x.estado for x in libro.instantanea()[1:]] == [EstadoMV.PENDIENTE] * 3
    assert dict(banco.cluster.posts) == {100: 1}
    assert (
        banco.cluster.llamadas_a("GET", r"qemu/100/config$") == []
    )  # con UPID no se usa existe_vm


def test_ca_l17_3_comprobar_y_continuar_resuelve_la_enviada_y_manda_solo_las_pendientes(banco):
    regla = banco.cluster.regla("GET", r"/tasks/.*/status$", nodo_caido("pve1", 596))
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 4), control)
    assert dict(banco.cluster.posts) == {100: 1}

    banco.cluster.reglas.remove(regla)  # la red vuelve
    motor = banco.motor()
    motor.comprobar_dudosas(libro, banco.observador, ControlLote())
    assert libro.entrada(100).estado == EstadoMV.OK
    motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    assert _estados(libro) == [EstadoMV.OK] * 4
    assert dict(banco.cluster.posts) == {100: 1, 101: 1, 102: 1, 103: 1}  # ninguna dos veces


def test_ca_l12_6_la_espera_maxima_de_10_minutos_se_aplica_por_maquina(banco):
    banco.cluster.tareas_en_curso[100] = 10**6
    banco.cluster.tareas_en_curso[101] = 10**6
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 3), control)
    assert [e.estado for e in libro.instantanea()] == [
        EstadoMV.TIEMPO_AGOTADO,
        EstadoMV.TIEMPO_AGOTADO,
        EstadoMV.OK,
    ]
    assert banco.reloj.ahora() >= 1200.0  # 600 s por cada una


def test_ca_l15_3_comprobar_ahora_con_upid_resuelve_una_tarea_que_ya_termino(banco):
    banco.cluster.tareas_en_curso[100] = 10**6
    libro = banco.ejecutar(_lote(banco, 1))
    assert libro.entrada(100).estado == EstadoMV.TIEMPO_AGOTADO
    banco.cluster.tareas_en_curso[100] = 0  # la tarea acabó mientras tanto
    posts = banco.cluster.total("POST")
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote())
    assert libro.entrada(100).estado == EstadoMV.OK
    assert banco.cluster.total("POST") == posts  # CA-L15.7: comprobar nunca envía un POST


def test_ca_l15_7_comprobar_dudosas_solo_hace_get_aunque_haya_dudas_sin_upid(banco):
    _post_incierto(banco, 100, 101, creada=False)
    regla = banco.cluster.regla("GET", r"qemu/10[01]/config$", nodo_caido("pve1", 596))
    libro = banco.ejecutar(_lote(banco, 3))
    assert {libro.entrada(100).estado, libro.entrada(101).estado} == {EstadoMV.CONEXION_PERDIDA}
    banco.cluster.reglas.remove(regla)
    antes = dict(banco.cluster.metodos)
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote())
    despues = banco.cluster.metodos
    assert despues["POST"] == antes["POST"]
    assert despues["DELETE"] == antes.get("DELETE", 0) == 0
    assert despues["GET"] > antes["GET"]
    assert libro.entrada(100).estado == libro.entrada(101).estado == EstadoMV.NO_CREADA_SEGURA


def test_ca_l15_7_comprobar_dudosas_reconoce_una_creada_que_aparecio(banco):
    _post_incierto(banco, 100, creada=False)
    regla = banco.cluster.regla("GET", r"qemu/100/config$", nodo_caido("pve1", 596))
    libro = banco.ejecutar(_lote(banco, 1))
    assert libro.entrada(100).estado == EstadoMV.CONEXION_PERDIDA
    banco.cluster.reglas.remove(regla)
    banco.cluster.agregar_vm(100, "pve1", "web-01", tags=f"proxlaunch;lote-{libro.id_lote}")
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote())
    assert libro.entrada(100).estado == EstadoMV.OK


def test_comprobar_dudosas_sin_dudosas_no_hace_ninguna_peticion(banco):
    libro = banco.ejecutar(_lote(banco, 2))
    banco.cluster.reiniciar_llamadas()
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote())
    assert banco.cluster.llamadas == []


# --- ejecutar_pendientes (CA-L17.3, INV-L1, INV-L3) -----------------------------------------------


def test_ejecutar_pendientes_solo_toma_las_pendientes_nunca_las_ya_intentadas(banco):
    banco.cluster.regla(
        "POST", r"/qemu$", _falla_post(101, error=ErrorProxLaunch(CodigoError.SESION_EXPIRADA))
    )
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 5), control)
    assert _estados(libro) == [
        EstadoMV.OK,
        EstadoMV.ERROR,
        EstadoMV.PENDIENTE,
        EstadoMV.PENDIENTE,
        EstadoMV.PENDIENTE,
    ]
    # Se reconecta (el fallo desaparece) y se continúa.
    banco.cluster.reglas.clear()
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    assert _estados(libro) == [EstadoMV.OK, EstadoMV.ERROR] + [EstadoMV.OK] * 3
    assert dict(banco.cluster.posts) == {100: 1, 101: 1, 102: 1, 103: 1, 104: 1}


def test_ejecutar_pendientes_no_reenvia_la_incierta(banco):
    _post_incierto(banco, 100, creada=False)
    banco.cluster.regla("GET", r"qemu/100/config$", nodo_caido("pve1", 596))
    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(_lote(banco, 3), control)
    assert libro.entrada(100).estado == EstadoMV.CONEXION_PERDIDA
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    assert banco.cluster.posts[100] == 1
    assert libro.entrada(100).estado == EstadoMV.CONEXION_PERDIDA


def test_ejecutar_pendientes_no_toma_las_no_enviadas_por_cancelacion(banco):
    control = ControlLote()
    banco.cluster.al_post = lambda vmid: control.cancelar() if vmid == 100 else None
    libro = banco.ejecutar(_lote(banco, 3), control)
    assert [e.estado for e in libro.instantanea()[1:]] == [EstadoMV.NO_ENVIADA] * 2
    banco.cluster.reiniciar_llamadas()
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    assert banco.cluster.total("POST") == 0  # reintentarlas exige un plan nuevo (RF-L21)
    assert [e.estado for e in libro.instantanea()[1:]] == [EstadoMV.NO_ENVIADA] * 2


def test_ejecutar_pendientes_sin_pendientes_no_hace_nada(banco):
    libro = banco.ejecutar(_lote(banco, 2))
    banco.cluster.reiniciar_llamadas()
    banco.motor().ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    assert banco.cluster.llamadas == []


def test_ejecutar_pendientes_con_una_sola_vez_no_duplica_ni_con_dos_llamadas_seguidas(banco):
    banco.cluster.regla(
        "POST", r"/qemu$", _falla_post(100, error=ErrorProxLaunch(CodigoError.SESION_EXPIRADA))
    )
    libro = banco.ejecutar(_lote(banco, 3), ControlAutomatico("suspender"))
    banco.cluster.reglas.clear()
    motor = banco.motor()
    motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    motor.ejecutar_pendientes(libro, banco.inv, banco.observador, ControlLote())
    assert dict(banco.cluster.posts) == {100: 1, 101: 1, 102: 1}


# --- INV-L4: el motor no escribe nada que no sea el POST del plan ---------------------------------


def test_inv_l4_el_motor_solo_escribe_post_de_creacion_de_maquinas_del_plan(banco):
    plan = _lote(banco, 4)
    banco.cluster.exitstatus[101] = SIN_ESPACIO.format(vmid=101)
    banco.ejecutar(plan)
    escrituras = [c for c in banco.cluster.llamadas if c.metodo != "GET"]
    assert {c.metodo for c in escrituras} == {"POST"}
    assert all(c.ruta == "/nodes/pve1/qemu" for c in escrituras)
    assert {_vmid_de(c) for c in escrituras} == {e.vmid for e in plan.elementos}


def test_el_motor_no_borra_nada_al_fallar_ni_al_cancelar(banco):
    banco.cluster.exitstatus[101] = "unexpected failure"
    banco.cluster.parciales = {101}
    banco.cluster.regla("GET", r"qemu/101/config$", lambda ll: {"name": "x"})
    control = ControlLote()
    banco.cluster.al_post = lambda vmid: control.cancelar() if vmid == 102 else None
    banco.ejecutar(_lote(banco, 5), control)
    assert banco.cluster.total("DELETE") == 0


def test_ca_l12_9_el_observador_recibe_instantaneas_inmutables_en_orden_por_maquina(banco):
    banco.ejecutar(_lote(banco, 3))
    for vmid in (100, 101, 102):
        etapas = [e.estado.value for e in banco.eventos if e.elemento.vmid == vmid]
        assert etapas[-1] == "ok"
        assert etapas.index("enviando") < etapas.index("creando") < etapas.index("comprobando")
    with pytest.raises(AttributeError):
        banco.eventos[0].estado = EstadoMV.OK  # type: ignore[misc]


def test_ca_l16_6_el_control_pausado_no_bloquea_si_se_cancela(banco):
    control = ControlLote()
    control.pausar(MotivoPausa.ERROR_GLOBAL, ErrorProxLaunch(CodigoError.SESION_EXPIRADA))
    control.cancelar()
    libro = banco.ejecutar(_lote(banco, 2), control)  # no debe quedarse esperando
    assert _estados(libro) == [EstadoMV.NO_ENVIADA] * 2
    assert banco.cluster.total("POST") == 0


def test_el_modelo_de_la_definicion_y_el_plan_son_inmutables(banco):
    plan = _lote(banco, 1)
    with pytest.raises(AttributeError):
        plan.id_lote = "otro"  # type: ignore[misc]
    assert replace(plan, id_lote="otro").id_lote == "otro"


# --- Tiempos por máquina (CA-L12.5, CA-L12.6) -----------------------------------------------------


def test_ca_l12_5_el_sondeo_de_cada_tarea_es_cada_1_5_segundos(banco):
    banco.cluster.tareas_en_curso[100] = 3  # 3 sondeos "running" y el 4.º termina
    banco.ejecutar(_lote(banco, 1))
    consultas = banco.cluster.llamadas_a("GET", r"/tasks/.*/status$")
    assert len(consultas) == 4
    assert banco.reloj.ahora() == pytest.approx(3 * 1.5)


def test_ca_l12_6_la_tolerancia_de_red_de_60_s_se_aplica_por_maquina(banco):
    banco.cluster.regla("GET", r"/tasks/.*/status$", nodo_caido("pve1", 596))
    control = ControlAutomatico("continuar")
    libro = banco.ejecutar(_lote(banco, 2), control)
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.CONEXION_PERDIDA] * 2
    assert banco.reloj.ahora() >= 2 * 60.0  # 60 s de tolerancia para cada una
