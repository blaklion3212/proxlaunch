"""Rollback del lote (RF-L18, INV-L4, D-20 (1)): elegibilidad, comprobaciones previas y DELETE.

El servidor simulado cuenta los métodos HTTP: el rollback solo puede borrar MVs del libro, con
``destroy-unreferenced-disks=0`` (sin ``purge``, D-21) en la consulta, y nunca a ciegas.
"""

import contextlib
import threading

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    CandidatoRollback,
    EstadoMV,
    EstadoRollback,
    MotivoNoEnviada,
    MotivoPausa,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import (
    MOTIVO_PROPIEDAD_NO_DEMOSTRADA,
    ServicioRollback,
)

from .apoyo_lote import (
    NORMAL,
    crear_banco,
    definicion,
    envio_incierto,
    nodo_caido,
    upid_de,
)


def _lote_creado(banco, cantidad=3, **kw):
    """Crea un lote de verdad con el motor y devuelve ``(plan, libro)``."""
    plan = banco.planificar(definicion(cantidad, vmid_inicial=100, **kw))
    libro = banco.ejecutar(plan)
    assert all(e.estado == EstadoMV.OK for e in libro.instantanea())
    return plan, libro


def _servicio(banco, **kw):
    return ServicioRollback(banco.sesion, banco.reloj, **kw)


def _deshacer(banco, libro, *, etiquetado=True, id_lote=None, control=None, candidatos=None):
    servicio = _servicio(banco)
    candidatos = (
        candidatos if candidatos is not None else servicio.elegibles(libro, etiquetado=etiquetado)
    )
    eventos = []
    resultados = servicio.deshacer(
        candidatos,
        eventos.append,
        control or ControlLote(),
        id_lote=id_lote or libro.id_lote,
        etiquetado=etiquetado,
    )
    return resultados, eventos


def _libro_con_estados(banco, estados, cantidad=None):
    """Libro de un plan cuyos estados se fijan a mano (``{vmid: EstadoMV}``)."""
    plan = banco.planificar(definicion(cantidad or len(estados), vmid_inicial=100))
    libro = Libro(plan)
    for vmid, estado in estados.items():
        if estado == EstadoMV.PENDIENTE:
            continue
        if estado == EstadoMV.NO_ENVIADA:
            libro.marcar_no_enviada(vmid, MotivoNoEnviada.CANCELADO)
            continue
        libro.iniciar(vmid, 0.0)
        libro.marcar_post_intentado(vmid, 0.0)
        libro.registrar_upid(vmid, upid_de("pve1", vmid))
        libro.finalizar(vmid, estado, t_fin=1.0)
    return plan, libro


# --- Elegibilidad (CA-L18.1, CA-L18.2) ------------------------------------------------------------


ELEGIBLES = {EstadoMV.OK, EstadoMV.CON_AVISOS, EstadoMV.PARCIAL}
FINALES = [
    EstadoMV.OK,
    EstadoMV.CON_AVISOS,
    EstadoMV.PARCIAL,
    EstadoMV.ERROR,
    EstadoMV.TIEMPO_AGOTADO,
    EstadoMV.CONEXION_PERDIDA,
    EstadoMV.NO_ENVIADA,
    EstadoMV.NO_CREADA_SEGURA,
    EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD,
    EstadoMV.PENDIENTE,
]


@pytest.mark.parametrize("estado", FINALES)
def test_ca_l18_1_y_l18_2_solo_ok_con_avisos_y_parcial_son_elegibles(banco, estado):
    _, libro = _libro_con_estados(banco, {100: estado}, cantidad=1)
    (c,) = _servicio(banco).elegibles(libro, etiquetado=True)
    assert c.elegible is (estado in ELEGIBLES)
    if estado not in ELEGIBLES:
        assert c.motivo == estado.value  # el motivo se muestra por fila
        assert not c.incompleta
    else:
        assert c.motivo is None


def test_ca_l18_1_hay_un_candidato_por_maquina_del_libro_en_el_orden_del_plan(banco):
    _, libro = _libro_con_estados(
        banco, {100: EstadoMV.OK, 101: EstadoMV.ERROR, 102: EstadoMV.PARCIAL}
    )
    cs = _servicio(banco).elegibles(libro, etiquetado=True)
    assert [c.entrada.elemento.vmid for c in cs] == [100, 101, 102]
    assert [c.elegible for c in cs] == [True, False, True]


def test_d_20_solo_incompletas_marca_parcial_y_con_avisos_pero_no_ok(banco):
    _, libro = _libro_con_estados(
        banco, {100: EstadoMV.OK, 101: EstadoMV.PARCIAL, 102: EstadoMV.CON_AVISOS}
    )
    cs = _servicio(banco).elegibles(libro, etiquetado=True)
    assert [c.incompleta for c in cs] == [False, True, True]


def test_ca_l15_5_una_maquina_rescatada_con_etiqueta_es_elegible_e_incompleta(banco):
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    libro = Libro(plan)
    libro.iniciar(100, 0.0)
    libro.marcar_post_intentado(100, 0.0)
    libro.finalizar(100, EstadoMV.OK, t_fin=1.0, avisos=("creada_tras_comprobar",))
    (c,) = _servicio(banco).elegibles(libro, etiquetado=True)
    assert c.elegible and c.incompleta


def test_ca_l24_3_sin_etiquetas_una_rescatada_sin_upid_no_demuestra_propiedad(banco):
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    libro = Libro(plan)
    libro.iniciar(100, 0.0)
    libro.marcar_post_intentado(100, 0.0)
    libro.finalizar(100, EstadoMV.OK, t_fin=1.0, avisos=("creada_tras_comprobar",))
    (c,) = _servicio(banco).elegibles(libro, etiquetado=False)
    assert not c.elegible
    assert c.motivo == MOTIVO_PROPIEDAD_NO_DEMOSTRADA


def test_ca_l24_3_sin_etiquetas_una_con_upid_propio_si_es_elegible(banco):
    _, libro = _libro_con_estados(banco, {100: EstadoMV.OK}, cantidad=1)
    (c,) = _servicio(banco).elegibles(libro, etiquetado=False)
    assert c.elegible


def test_ca_l18_13_con_cantidad_1_el_rollback_tambien_se_ofrece(banco):
    plan = banco.planificar(definicion(1, prefijo="", vmid_inicial=100))
    libro = banco.ejecutar(plan)
    (c,) = _servicio(banco).elegibles(libro, etiquetado=True)
    assert c.elegible


# --- Borrado: parámetros, comprobaciones previas y resultado (CA-L18.4, CA-L18.5) -----------------


def test_ca_l18_5_elimina_las_maquinas_del_libro_con_los_parametros_acordados(banco):
    _, libro = _lote_creado(banco, 3)
    resultados, eventos = _deshacer(banco, libro)
    assert [r.estado for r in resultados] == [EstadoRollback.ELIMINADA] * 3
    assert dict(banco.cluster.deletes) == {100: 1, 101: 1, 102: 1}
    assert banco.cluster.vms == {}
    for vmid in (100, 101, 102):
        assert banco.cluster.params_delete[vmid] == {"destroy-unreferenced-disks": 0}
    deletes = banco.cluster.llamadas_a("DELETE")
    assert all(c.datos is None for c in deletes)  # los parámetros van en la consulta
    assert all(r.upid and ":qmdestroy:" in r.upid for r in resultados)


def test_ca_l18_4_antes_de_cada_delete_se_lee_la_config_y_el_estado_actual(banco):
    _, libro = _lote_creado(banco, 2)
    banco.cluster.reiniciar_llamadas()
    _deshacer(banco, libro)
    for vmid in (100, 101):
        orden = [(c.metodo, c.ruta) for c in banco.cluster.llamadas if f"/qemu/{vmid}" in c.ruta]
        i_delete = orden.index(("DELETE", f"/nodes/pve1/qemu/{vmid}"))
        assert ("GET", f"/nodes/pve1/qemu/{vmid}/config") in orden[:i_delete]
        assert ("GET", f"/nodes/pve1/qemu/{vmid}/status/current") in orden[:i_delete]


def test_ca_l18_5_el_observador_ve_comprobando_eliminando_y_el_resultado_final(banco):
    _, libro = _lote_creado(banco, 1)
    resultados, eventos = _deshacer(banco, libro)
    assert [e.estado for e in eventos] == [
        EstadoRollback.COMPROBANDO,
        EstadoRollback.ELIMINANDO,
        EstadoRollback.ELIMINADA,
    ]
    assert resultados[0] == eventos[-1]


def test_ca_l18_5_la_tarea_de_borrado_se_sondea_hasta_que_termina(banco):
    _, libro = _lote_creado(banco, 1)
    banco.cluster.tareas_en_curso[100] = 4
    antes = banco.reloj.ahora()
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.ELIMINADA
    assert banco.reloj.ahora() - antes >= 4 * 1.5


def test_inv_l4_nunca_toca_maquinas_que_no_estan_en_el_libro(banco):
    _, libro = _lote_creado(banco, 2)
    banco.cluster.agregar_vm(500, "pve1", "ajena", tags="proxlaunch;lote-otro0000")
    banco.cluster.agregar_vm(101 + 100, "pve1", "otra")
    banco.cluster.reiniciar_llamadas()
    _deshacer(banco, libro)
    tocadas = {
        int(c.ruta.split("/qemu/")[1].split("/")[0])
        for c in banco.cluster.llamadas
        if "/qemu/" in c.ruta
    }
    assert tocadas == {100, 101}
    assert 500 in banco.cluster.vms and 201 in banco.cluster.vms


def test_inv_l4_solo_se_borran_las_elegibles_las_demas_ni_se_consultan(banco):
    plan, libro = _libro_con_estados(
        banco,
        {
            100: EstadoMV.OK,
            101: EstadoMV.ERROR,
            102: EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD,
            103: EstadoMV.CONEXION_PERDIDA,
            104: EstadoMV.NO_ENVIADA,
            105: EstadoMV.NO_CREADA_SEGURA,
            106: EstadoMV.PARCIAL,
        },
    )
    nombres = {e.vmid: e.nombre for e in plan.elementos}
    for vmid in (100, 102, 103, 106):
        banco.cluster.agregar_vm(
            vmid, "pve1", nombres[vmid], tags=f"proxlaunch;lote-{plan.id_lote}"
        )
    resultados, _ = _deshacer(banco, libro)
    assert sorted(banco.cluster.deletes) == [100, 106]
    assert {r.vmid for r in resultados} == {100, 106}
    assert {102, 103} <= set(banco.cluster.vms)  # existen pero no se pudo demostrar su propiedad
    consultadas = {
        int(c.ruta.split("/qemu/")[1].split("/")[0])
        for c in banco.cluster.llamadas
        if "/qemu/" in c.ruta
    }
    assert consultadas == {100, 106}


def test_inv_l4_un_candidato_armado_a_mano_con_estado_no_elegible_no_se_borra(banco):
    plan, libro = _libro_con_estados(banco, {100: EstadoMV.ERROR}, cantidad=1)
    banco.cluster.agregar_vm(100, "pve1", "web-01", tags=f"proxlaunch;lote-{plan.id_lote}")
    forzado = [CandidatoRollback(libro.entrada(100), True, None, False)]
    resultados, _ = _deshacer(banco, libro, candidatos=forzado)
    assert resultados == []
    assert banco.cluster.total("DELETE") == 0


def test_inv_l4_sin_candidatos_elegibles_no_se_hace_ninguna_peticion(banco):
    _, libro = _libro_con_estados(banco, {100: EstadoMV.ERROR, 101: EstadoMV.NO_ENVIADA})
    banco.cluster.reiniciar_llamadas()
    resultados, _ = _deshacer(banco, libro)
    assert resultados == []
    assert banco.cluster.llamadas == []


def test_ca_l18_2_una_maquina_de_otro_lote_no_se_elimina(banco):
    _, libro = _lote_creado(banco, 2)
    resultados, _ = _deshacer(banco, libro, id_lote="deadbeef")  # etiqueta de OTRO lote
    assert [r.estado for r in resultados] == [EstadoRollback.OMITIDA] * 2
    assert {r.error.codigo for r in resultados} == {CodigoError.ROLLBACK_NO_PROPIA}
    assert banco.cluster.total("DELETE") == 0


def test_ca_l18_4_etiqueta_ajena_o_ausente_en_el_servidor_no_se_elimina(banco):
    _, libro = _lote_creado(banco, 3)
    banco.cluster.vms[100]["config"]["tags"] = "otra;lote-0000aaaa"  # etiqueta ajena
    del banco.cluster.vms[101]["config"]["tags"]  # sin etiqueta
    resultados, _ = _deshacer(banco, libro)
    por_vmid = {r.vmid: r for r in resultados}
    assert por_vmid[100].estado == por_vmid[101].estado == EstadoRollback.OMITIDA
    assert (
        por_vmid[100].error.codigo == por_vmid[101].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    )
    assert por_vmid[102].estado == EstadoRollback.ELIMINADA
    assert sorted(banco.cluster.deletes) == [102]


def test_ca_l18_4_si_el_nombre_en_el_servidor_no_coincide_con_el_del_libro_no_se_elimina(banco):
    """Otro usuario pudo recrear el VMID con otra MV (VMID reutilizado)."""
    _, libro = _lote_creado(banco, 1)
    banco.cluster.vms[100]["config"]["name"] = "otra-maquina"
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.OMITIDA
    assert banco.cluster.total("DELETE") == 0


@pytest.mark.parametrize("proteccion", ["1", 1, True, "true"])
def test_ca_l18_4_una_maquina_con_proteccion_no_se_elimina(banco, proteccion):
    _, libro = _lote_creado(banco, 2)
    banco.cluster.vms[100]["config"]["protection"] = proteccion
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.OMITIDA
    assert resultados[0].error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    assert sorted(banco.cluster.deletes) == [101]  # las demás siguen


def test_ca_l18_4_proteccion_cero_no_bloquea(banco):
    _, libro = _lote_creado(banco, 1)
    banco.cluster.vms[100]["config"]["protection"] = "0"
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.ELIMINADA


def test_ca_l18_4_una_maquina_con_lock_no_se_elimina(banco):
    _, libro = _lote_creado(banco, 2)
    banco.cluster.vms[101]["config"]["lock"] = "backup"
    resultados, _ = _deshacer(banco, libro)
    omitida = next(r for r in resultados if r.vmid == 101)
    assert omitida.estado == EstadoRollback.OMITIDA
    assert omitida.error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    assert sorted(banco.cluster.deletes) == [100]


def test_ca_l18_4_una_maquina_encendida_no_se_elimina(banco):
    _, libro = _lote_creado(banco, 3)
    banco.cluster.vms[101]["status"] = "running"
    resultados, _ = _deshacer(banco, libro)
    omitida = next(r for r in resultados if r.vmid == 101)
    assert omitida.estado == EstadoRollback.OMITIDA
    assert omitida.error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    assert omitida.error.params["nombre"] == "web-02"
    assert sorted(banco.cluster.deletes) == [100, 102]


def test_ca_l18_4_una_maquina_que_ya_no_existe_se_informa_sin_enviar_delete(banco):
    _, libro = _lote_creado(banco, 2)
    del banco.cluster.vms[100]  # la borró otra persona
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.YA_NO_EXISTIA
    assert sorted(banco.cluster.deletes) == [101]


# --- Errores durante el borrado (CA-L18.6, CA-L18.8, CA-L18.9) ------------------------------------


def test_ca_l18_8_una_tarea_de_borrado_fallida_no_detiene_a_las_demas(banco):
    _, libro = _lote_creado(banco, 3)
    banco.cluster.exitstatus[101] = "unable to remove volume"
    resultados, _ = _deshacer(banco, libro)
    estados = {r.vmid: r.estado for r in resultados}
    assert estados == {
        100: EstadoRollback.ELIMINADA,
        101: EstadoRollback.FALLO,
        102: EstadoRollback.ELIMINADA,
    }
    fallo = next(r for r in resultados if r.vmid == 101)
    assert fallo.error.codigo == CodigoError.ROLLBACK_FALLO
    assert "unable to remove volume" in fallo.error.detalle_tecnico
    assert 101 in banco.cluster.vms  # queda sin borrar y el informe la lista


def test_ca_l18_9_un_403_al_borrar_detiene_el_rollback_y_deja_intactas_las_demas(banco):
    _, libro = _lote_creado(banco, 4)
    banco.cluster.regla(
        "DELETE",
        r"qemu/\d+$",
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "Permission check failed"),
    )
    control = ControlLote()
    resultados, _ = _deshacer(banco, libro, control=control)
    assert resultados[0].estado == EstadoRollback.FALLO
    assert resultados[0].error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert resultados[0].error.params["privilegio"] == "VM.Allocate"  # nombra el privilegio
    assert [r.estado for r in resultados[1:]] == [EstadoRollback.NO_ENVIADA] * 3
    assert control.motivo_pausa == MotivoPausa.ERROR_GLOBAL
    assert banco.cluster.deletes[100] == 1 and sum(banco.cluster.deletes.values()) == 1
    assert len(banco.cluster.vms) == 4


def test_ca_l18_9_un_403_al_leer_la_config_previa_tambien_detiene_el_rollback(banco):
    _, libro = _lote_creado(banco, 3)
    banco.cluster.regla(
        "GET", r"qemu/100/config$", ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE)
    )
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.FALLO
    assert banco.cluster.total("DELETE") == 0


def test_ca_l18_6_delete_incierto_con_la_maquina_ya_borrada_es_eliminada_sin_reintento(banco):
    _, libro = _lote_creado(banco, 1)

    def _entrega_y_falla(llamada):
        banco.cluster.vms.pop(100)  # el servidor sí borró
        raise envio_incierto()

    banco.cluster.regla("DELETE", r"qemu/100$", _entrega_y_falla)
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.ELIMINADA
    assert banco.cluster.deletes[100] == 1


def test_ca_l18_6_delete_incierto_con_la_maquina_presente_es_incierto_sin_reintento_a_ciegas(
    banco,
):
    _, libro = _lote_creado(banco, 1)
    banco.cluster.regla("DELETE", r"qemu/100$", envio_incierto())
    resultados, _ = _deshacer(banco, libro)
    (r,) = resultados
    assert r.estado == EstadoRollback.INCIERTA
    assert r.error.codigo == CodigoError.ROLLBACK_INCIERTO
    assert banco.cluster.deletes[100] == 1  # nunca un segundo DELETE
    assert 100 in banco.cluster.vms


def test_ca_l18_6_una_conexion_abortada_en_el_delete_tambien_es_incierta(banco):
    import requests

    _, libro = _lote_creado(banco, 1)
    banco.cluster.regla("DELETE", r"qemu/100$", requests.exceptions.ConnectionError("aborted"))
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.INCIERTA
    assert banco.cluster.deletes[100] == 1


def test_ca_l18_6_si_el_sondeo_de_la_tarea_de_borrado_pierde_la_red_se_verifica_con_la_config(
    banco,
):
    _, libro = _lote_creado(banco, 1)
    banco.cluster.regla(
        "GET", r"qmdestroy.*status$|tasks/.*qmdestroy.*status", nodo_caido("pve1", 596)
    )
    resultados, _ = _deshacer(banco, libro)
    # La tarea de borrado terminó en el servidor (la MV ya no existe) aunque no se pudo sondear.
    assert resultados[0].estado == EstadoRollback.ELIMINADA
    assert banco.cluster.deletes[100] == 1
    assert banco.reloj.ahora() >= 60.0  # se agotó la tolerancia de red antes de comprobar


def test_ca_l18_6_sin_poder_leer_la_config_previa_no_se_envia_el_delete(banco):
    _, libro = _lote_creado(banco, 1)
    banco.cluster.regla("GET", r"qemu/100/config$", nodo_caido("pve1", 596))
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.FALLO
    assert banco.cluster.total("DELETE") == 0


# --- Cancelación y concurrencia (CA-L18.10) -------------------------------------------------------


def test_ca_l18_10_cancelar_antes_de_empezar_no_hace_ninguna_peticion(banco):
    _, libro = _lote_creado(banco, 3)
    banco.cluster.reiniciar_llamadas()
    control = ControlLote()
    control.cancelar()
    resultados, _ = _deshacer(banco, libro, control=control)
    assert [r.estado for r in resultados] == [EstadoRollback.NO_ENVIADA] * 3
    assert banco.cluster.llamadas == []


def test_ca_l18_10_cancelar_durante_el_rollback_deja_el_resto_sin_borrar(banco):
    _, libro = _lote_creado(banco, 4)
    control = ControlLote()

    def _cancela_en_el_primero(llamada):
        control.cancelar()
        return NORMAL

    banco.cluster.regla("DELETE", r"qemu/\d+$", _cancela_en_el_primero, veces=1)
    resultados, _ = _deshacer(banco, libro, control=control)
    assert resultados[0].estado == EstadoRollback.ELIMINADA  # la que estaba en vuelo termina
    assert [r.estado for r in resultados[1:]] == [EstadoRollback.NO_ENVIADA] * 3
    assert sum(banco.cluster.deletes.values()) == 1


def test_ca_l18_10_como_maximo_un_delete_por_nodo_a_la_vez():
    banco = crear_banco(("pve1", "pve2"))
    _, libro = _lote_creado(banco, 6, algoritmo=Algoritmo.POR_TURNOS)
    activos = {"pve1": 0, "pve2": 0}
    maximos = {"pve1": 0, "pve2": 0}
    cerrojo = threading.Lock()
    barrera = threading.Barrier(2, timeout=5)
    primeros = set()

    def _mide(llamada):
        nodo_ = llamada.ruta.split("/")[2]
        with cerrojo:
            activos[nodo_] += 1
            maximos[nodo_] = max(maximos[nodo_], activos[nodo_])
            esperar = nodo_ not in primeros
            primeros.add(nodo_)
        try:
            if esperar:
                with contextlib.suppress(threading.BrokenBarrierError):
                    barrera.wait()
            return NORMAL
        finally:
            with cerrojo:
                activos[nodo_] -= 1

    banco.cluster.regla("DELETE", r"qemu/\d+$", _mide)
    resultados, _ = _deshacer(banco, libro)
    assert [r.estado for r in resultados] == [EstadoRollback.ELIMINADA] * 6
    assert maximos == {"pve1": 1, "pve2": 1}
    assert banco.cluster.vms == {}


def test_inv_l4_el_rollback_no_borra_volumenes_sueltos_ni_toca_el_almacenamiento(banco):
    """CA-L18.11: sin borrado de volúmenes huérfanos; solo ``DELETE`` de MVs del libro."""
    _, libro = _libro_con_estados(banco, {100: EstadoMV.ERROR, 101: EstadoMV.OK})
    plan_id = libro.id_lote
    banco.cluster.agregar_vm(101, "pve1", "web-02", tags=f"proxlaunch;lote-{plan_id}")
    _deshacer(banco, libro)
    assert all("/storage" not in c.ruta for c in banco.cluster.llamadas)
    assert {c.metodo for c in banco.cluster.llamadas} <= {"GET", "DELETE"}
    assert sorted(banco.cluster.deletes) == [101]


def _delete_que_no_borra(banco, vmid):
    """El DELETE devuelve un UPID pero la MV sigue en el servidor (tarea que no termina)."""
    banco.cluster.regla("DELETE", rf"qemu/{vmid}$", lambda ll: upid_de("pve1", vmid, "qmdestroy"))
    banco.cluster.tareas_en_curso[vmid] = 10**6


def test_ca_l18_6_si_la_tarea_de_borrado_no_termina_en_el_maximo_queda_incierta_sin_reintento(
    banco,
):
    _, libro = _lote_creado(banco, 1)
    _delete_que_no_borra(banco, 100)
    servicio = ServicioRollback(banco.sesion, banco.reloj, max_espera_s=30.0)
    (r,) = servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        lambda x: None,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
    )
    assert r.estado == EstadoRollback.INCIERTA
    assert r.error.codigo == CodigoError.ROLLBACK_INCIERTO
    assert banco.cluster.deletes[100] == 1
    assert banco.reloj.ahora() >= 30.0


def test_ca_l16_2_dejar_de_esperar_durante_el_rollback_no_reenvia_el_delete(banco):
    _, libro = _lote_creado(banco, 1)
    control = ControlLote()
    banco.cluster.regla(
        "DELETE",
        r"qemu/100$",
        lambda ll: (control.dejar_de_esperar(), upid_de("pve1", 100, "qmdestroy"))[1],
    )
    banco.cluster.tareas_en_curso[100] = 10**6
    resultados, _ = _deshacer(banco, libro, control=control)
    assert resultados[0].estado == EstadoRollback.INCIERTA  # la MV sigue ahí
    assert banco.cluster.deletes[100] == 1


def test_ca_l18_8_un_fallo_inesperado_al_comprobar_una_maquina_no_detiene_las_demas(banco):
    _, libro = _lote_creado(banco, 3)
    banco.cluster.regla("GET", r"qemu/100/config$", RuntimeError("fallo de programación"))
    resultados, _ = _deshacer(banco, libro)
    assert resultados[0].estado == EstadoRollback.FALLO
    assert [r.estado for r in resultados[1:]] == [EstadoRollback.ELIMINADA] * 2
    assert sorted(banco.cluster.deletes) == [101, 102]
