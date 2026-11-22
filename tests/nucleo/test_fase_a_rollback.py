"""Fase A (0.6.0): Deshacer con máquinas encendidas y protegidas del propio lote.

Cubre RF-A1.5 (CA-A1.5.1 a A1.5.8), RF-A6.3, RF-A6.4 (núcleo), CL-A3, CL-A4 y RNF-A2.
La confirmación expresa (diálogo) es de la interfaz: aquí «confirmar» = ``forzar=True``.
"""

import logging

import pytest

from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.modelos import EstadoRollback
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import (
    ACCION_APAGADA,
    ACCION_BORRADA,
    ACCION_DESPROTEGIDA,
    ServicioRollback,
    es_propia,
)

from .apoyo_fase_a_p2 import (
    PERMISOS_COMPLETOS,
    SIN_NINGUNO,
    SIN_OPCIONES,
    SIN_POWERMGMT,
    encender_en_servidor,
    error_api,
    lote_creado,
    orden_de_llamadas,
    proteger_en_servidor,
)
from .apoyo_lote import definicion, plantilla


def _servicio(banco, **kw):
    return ServicioRollback(banco.sesion, banco.reloj, **kw)


def _deshacer(banco, libro, *, forzar=True, permisos=None, etiquetado=True):
    servicio = _servicio(banco)
    candidatos = servicio.elegibles(libro, etiquetado=etiquetado)
    eventos = []
    # «forzar» = el usuario confirmó todas las máquinas del libro (equivale a la inspección).
    todas = frozenset(c.entrada.elemento.vmid for c in candidatos) if forzar else frozenset()
    res = servicio.deshacer(
        candidatos,
        eventos.append,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=etiquetado,
        forzar_apagado=todas,
        forzar_desproteccion=todas,
        permisos=permisos,
    )
    return {r.vmid: r for r in res}


def _inspeccionar(banco, libro, etiquetado=True):
    servicio = _servicio(banco)
    return servicio.inspeccionar(
        servicio.elegibles(libro, etiquetado=etiquetado),
        id_lote=libro.id_lote,
        etiquetado=etiquetado,
    )


# --- RF-A1.5: encendidas ------------------------------------------------------------------------


def test_ca_a1_5_1_encendidas_stop_espera_y_delete_la_apagada_solo_delete(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100, 102)
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert orden_de_llamadas(banco, 100) == ["stop", "delete"]
    assert orden_de_llamadas(banco, 102) == ["stop", "delete"]
    assert orden_de_llamadas(banco, 101) == ["delete"]
    assert all(r.estado == EstadoRollback.ELIMINADA for r in res.values())
    assert res[100].acciones == (ACCION_APAGADA, ACCION_BORRADA)
    assert res[101].acciones == (ACCION_BORRADA,)
    # se esperó la tarea de stop antes del DELETE: hubo al menos una consulta de estado de tarea
    assert banco.cluster.llamadas_a("GET", r"tasks/.*qmstop")


def test_ca_a1_5_1_inspeccionar_cuenta_las_encendidas_y_solo_lee(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100, 102)
    banco.cluster.reiniciar_llamadas()
    insp = _inspeccionar(banco, libro)
    assert sorted(insp.encendidas) == [100, 102]
    assert insp.protegidas == ()
    assert banco.cluster.solo_lecturas


def test_ca_a1_5_2_sin_confirmar_no_hay_escrituras_ni_con_inspeccion(banco):
    """Cancelar el diálogo = no llamar a ``deshacer``: la inspección previa no escribe."""
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100, 102)
    proteger_en_servidor(banco, 101)
    banco.cluster.reiniciar_llamadas()
    _inspeccionar(banco, libro)
    assert banco.cluster.total("POST") == 0
    assert banco.cluster.total("PUT") == 0
    assert banco.cluster.total("DELETE") == 0


def test_ca_a1_5_2_sin_forzar_no_apaga_ni_desprotege_y_omite_con_su_motivo(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    banco.cluster.reiniciar_llamadas()
    res = _deshacer(banco, libro, forzar=False)
    assert banco.cluster.total("POST") == 0
    assert banco.cluster.total("PUT") == 0
    assert res[100].estado == EstadoRollback.OMITIDA
    assert res[100].error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    assert res[101].estado == EstadoRollback.OMITIDA
    assert res[101].error.codigo == CodigoError.ROLLBACK_PROTEGIDA
    assert res[102].estado == EstadoRollback.ELIMINADA


def test_ca_a1_5_3_sin_powermgmt_las_encendidas_se_omiten_sin_intentar_stop(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100, 102)
    res = _deshacer(banco, libro, permisos=SIN_POWERMGMT)
    for v in (100, 102):
        assert res[v].estado == EstadoRollback.OMITIDA
        assert res[v].error.codigo == CodigoError.ROLLBACK_SIN_POWERMGMT
        assert res[v].error.codigo != CodigoError.ROLLBACK_ENCENDIDA
    assert res[101].estado == EstadoRollback.ELIMINADA
    assert banco.cluster.llamadas_a("POST", "status/stop") == []
    assert sorted(banco.cluster.deletes) == [101]


def test_ca_a1_5_3_permisos_desconocidos_se_intenta(banco):
    """RF-A0.3.2 / INV-O10: ``permisos=None`` no bloquea; se intenta el stop."""
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    res = _deshacer(banco, libro, permisos=None)
    assert res[100].estado == EstadoRollback.ELIMINADA
    assert res[100].acciones == (ACCION_APAGADA, ACCION_BORRADA)


def test_ca_a1_5_3_un_403_en_el_stop_omite_esa_maquina_y_sigue_con_las_demas(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100, 101)
    banco.cluster.regla(
        "POST", r"/qemu/100/status/stop", error_api("403", CodigoError.PERMISO_INSUFICIENTE)
    )
    res = _deshacer(banco, libro, permisos=None)
    assert res[100].estado == EstadoRollback.OMITIDA
    assert res[100].error.codigo == CodigoError.ROLLBACK_SIN_POWERMGMT
    assert res[101].estado == EstadoRollback.ELIMINADA
    assert res[102].estado == EstadoRollback.ELIMINADA
    assert 100 not in banco.cluster.deletes


def test_ca_a1_5_4_encendida_ajena_nunca_se_apaga_ni_se_borra(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    banco.cluster.vms[100]["config"]["name"] = "de-otra-persona"
    for permisos in (None, PERMISOS_COMPLETOS, SIN_NINGUNO):
        res = _deshacer(banco, libro, forzar=True, permisos=permisos)
        assert res[100].estado == EstadoRollback.OMITIDA
        assert res[100].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert banco.cluster.llamadas_a("POST", "status/stop") == []
    assert 100 not in banco.cluster.deletes


def test_ca_a1_5_4_sin_etiqueta_ni_nombre_del_libro_no_es_propia(banco):
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    banco.cluster.vms[100]["config"]["tags"] = "otra-etiqueta"
    banco.cluster.vms[100]["config"]["name"] = "ajena"
    res = _deshacer(banco, libro, forzar=True, permisos=PERMISOS_COMPLETOS)
    assert res[100].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert banco.cluster.llamadas_a("POST", "status/stop") == []


@pytest.mark.parametrize("como", ["tarea_con_error", "tiempo_agotado"])
def test_ca_a1_5_5_si_el_stop_falla_no_se_borra_y_se_continua(banco, como):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100, 101)
    if como == "tarea_con_error":
        banco.cluster.exitstatus[100] = "command 'qm stop 100' failed"
    else:
        banco.cluster.tareas_en_curso[100] = 10**9  # la tarea no termina nunca
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado in (EstadoRollback.FALLO, EstadoRollback.INCIERTA)
    assert res[100].error is not None
    if como == "tarea_con_error":
        assert res[100].error.codigo == CodigoError.ROLLBACK_APAGADO_FALLIDO
    assert 100 not in banco.cluster.deletes
    assert res[101].estado == EstadoRollback.ELIMINADA  # Deshacer continúa con las demás
    assert res[102].estado == EstadoRollback.ELIMINADA


def test_ca_a1_5_5_el_stop_que_lanza_error_no_borra(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    banco.cluster.regla("POST", r"/qemu/100/status/stop", error_api("500 internal error"))
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.FALLO
    assert res[100].error.codigo == CodigoError.ROLLBACK_APAGADO_FALLIDO
    assert 100 not in banco.cluster.deletes
    assert res[101].estado == EstadoRollback.ELIMINADA


def test_ca_a1_5_6_encendida_con_lock_se_omite_por_bloqueo_sin_forzarla(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    banco.cluster.vms[100]["config"]["lock"] = "backup"
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.OMITIDA
    assert res[100].error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    assert orden_de_llamadas(banco, 100) == []


@pytest.mark.parametrize("detalle", ["VM 100 not running", "VM 100 not running (race)"])
def test_ca_a1_5_8_stop_sobre_una_maquina_ya_parada_no_es_fallo_en_la_peticion(banco, detalle):
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    banco.cluster.regla("POST", r"/qemu/100/status/stop", error_api(detalle))
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.ELIMINADA
    assert 100 in banco.cluster.deletes


def test_ca_a1_5_8_stop_cuya_tarea_termina_con_not_running_tampoco_es_fallo(banco):
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    banco.cluster.exitstatus[100] = "OK"
    # La tarea de stop informa «not running»; el DELETE posterior sigue normal.
    originales = banco.cluster._tarea

    def tarea(upid, que):
        if "qmstop" in upid and que == "status":
            return {"status": "stopped", "exitstatus": "VM 100 not running"}
        return originales(upid, que)

    banco.cluster._tarea = tarea
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.ELIMINADA


# --- RF-A6.3: protegidas ------------------------------------------------------------------------


def test_ca_a6_3_1_protegidas_put_protection_0_y_luego_delete(banco):
    _, libro = lote_creado(banco, 2)
    proteger_en_servidor(banco, 100, 101)
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    for v in (100, 101):
        assert orden_de_llamadas(banco, v) == ["put-config", "delete"]
        assert res[v].estado == EstadoRollback.ELIMINADA
        assert res[v].acciones == (ACCION_DESPROTEGIDA, ACCION_BORRADA)
    puts = banco.cluster.llamadas_a("PUT", "/config")
    assert all(str(p.datos.get("protection")) == "0" for p in puts)


def test_ca_a6_3_2_sin_confirmar_ninguna_escritura(banco):
    _, libro = lote_creado(banco, 2)
    proteger_en_servidor(banco, 100, 101)
    banco.cluster.reiniciar_llamadas()
    insp = _inspeccionar(banco, libro)
    assert sorted(insp.protegidas) == [100, 101]
    assert banco.cluster.solo_lecturas


def test_ca_a6_3_3_sin_config_options_las_protegidas_se_omiten_y_las_demas_se_borran(banco):
    _, libro = lote_creado(banco, 3)
    proteger_en_servidor(banco, 100, 101)
    res = _deshacer(banco, libro, permisos=SIN_OPCIONES)
    for v in (100, 101):
        assert res[v].estado == EstadoRollback.OMITIDA
        assert res[v].error.codigo == CodigoError.ROLLBACK_SIN_OPCIONES
    assert res[102].estado == EstadoRollback.ELIMINADA
    assert banco.cluster.total("PUT") == 0
    assert sorted(banco.cluster.deletes) == [102]


def test_ca_a6_3_3_un_403_en_el_put_omite_esa_maquina(banco):
    _, libro = lote_creado(banco, 2)
    proteger_en_servidor(banco, 100)
    banco.cluster.regla(
        "PUT", r"/qemu/100/config", error_api("403", CodigoError.PERMISO_INSUFICIENTE)
    )
    res = _deshacer(banco, libro, permisos=None)
    assert res[100].estado == EstadoRollback.OMITIDA
    assert res[100].error.codigo == CodigoError.ROLLBACK_SIN_OPCIONES
    assert res[101].estado == EstadoRollback.ELIMINADA
    assert 100 not in banco.cluster.deletes


def test_ca_a6_3_4_protegida_ajena_nunca_se_desprotege_ni_se_borra(banco):
    _, libro = lote_creado(banco, 2)
    proteger_en_servidor(banco, 100)
    banco.cluster.vms[100]["config"]["name"] = "ajena"
    for forzar in (False, True):
        res = _deshacer(banco, libro, forzar=forzar, permisos=PERMISOS_COMPLETOS)
        assert res[100].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert banco.cluster.total("PUT") == 0
    assert 100 not in banco.cluster.deletes


def test_ca_a6_3_5_protegida_y_encendida_ambas_acciones_antes_del_delete(banco):
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    orden = orden_de_llamadas(banco, 100)
    assert orden[-1] == "delete"
    assert sorted(orden[:-1]) == ["put-config", "stop"]
    assert res[100].estado == EstadoRollback.ELIMINADA
    assert set(res[100].acciones) == {ACCION_APAGADA, ACCION_DESPROTEGIDA, ACCION_BORRADA}
    assert res[100].acciones[-1] == ACCION_BORRADA


def test_ca_a6_3_5_orden_del_diseno_apagar_antes_de_desproteger(banco):
    """DT-A6: stop → PUT protection=0 → DELETE (un fallo nunca deja desprotegida y encendida)."""
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)
    _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert orden_de_llamadas(banco, 100) == ["stop", "put-config", "delete"]


@pytest.mark.parametrize(
    ("permisos", "esperado", "tambien"),
    [
        (SIN_POWERMGMT, CodigoError.ROLLBACK_SIN_POWERMGMT, None),
        (SIN_OPCIONES, CodigoError.ROLLBACK_SIN_OPCIONES, None),
        (SIN_NINGUNO, CodigoError.ROLLBACK_SIN_POWERMGMT, CodigoError.ROLLBACK_SIN_OPCIONES),
    ],
)
def test_ca_a6_3_5_falta_un_privilegio_se_omite_con_el_motivo_o_con_ambos(
    banco, permisos, esperado, tambien
):
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)
    res = _deshacer(banco, libro, permisos=permisos)
    assert res[100].estado == EstadoRollback.OMITIDA
    assert res[100].error.codigo == esperado
    assert res[100].error.params.get("tambien") == (str(tambien) if tambien else None)
    assert orden_de_llamadas(banco, 100) == []


def test_ca_a6_3_6_si_put_protection_falla_no_se_borra(banco):
    _, libro = lote_creado(banco, 2)
    proteger_en_servidor(banco, 100)
    banco.cluster.regla("PUT", r"/qemu/100/config", error_api("500 error"))
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.FALLO
    assert res[100].error.codigo == CodigoError.ROLLBACK_DESPROTECCION_FALLIDA
    assert 100 not in banco.cluster.deletes
    assert res[101].estado == EstadoRollback.ELIMINADA


def test_ca_a6_3_6_fallo_del_put_tras_apagar_informa_lo_hecho(banco):
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)
    banco.cluster.regla("PUT", r"/qemu/100/config", error_api("500 error"))
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].acciones == (ACCION_APAGADA,)
    assert 100 not in banco.cluster.deletes


def test_ca_a6_3_7_protegida_con_lock_se_omite_por_lock(banco):
    _, libro = lote_creado(banco, 2)
    proteger_en_servidor(banco, 100)
    banco.cluster.vms[100]["config"]["lock"] = "migrate"
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    assert orden_de_llamadas(banco, 100) == []


def test_ca_a6_3_8_deshacer_por_defecto_nunca_apaga_ni_desprotege(banco):
    """P-20: sin confirmación (forzar por defecto False) no hay stop ni protection=0."""
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    servicio = _servicio(banco)
    servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        lambda r: None,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
    )
    assert banco.cluster.llamadas_a("POST", "status/stop") == []
    assert banco.cluster.total("PUT") == 0
    assert banco.cluster.deletes == {}


# --- RF-A6.4: confirmación única e informe -------------------------------------------------------


def test_ca_a6_4_1_sin_encendidas_ni_protegidas_no_hay_nada_que_confirmar(banco):
    _, libro = lote_creado(banco, 3)
    insp = _inspeccionar(banco, libro)
    assert insp.encendidas == ()
    assert insp.protegidas == ()
    res = _deshacer(banco, libro, forzar=False)
    assert all(r.estado == EstadoRollback.ELIMINADA for r in res.values())
    assert banco.cluster.llamadas_a("POST", "status/stop") == []


def test_ca_a6_4_2_inspeccion_con_ambas_situaciones_da_los_dos_recuentos(banco):
    _, libro = lote_creado(banco, 4)
    encender_en_servidor(banco, 100, 101)
    proteger_en_servidor(banco, 101, 102)
    insp = _inspeccionar(banco, libro)
    assert sorted(insp.encendidas) == [100, 101]
    assert sorted(insp.protegidas) == [101, 102]


def test_ca_a6_4_3_informe_lista_acciones_por_maquina_y_omitidas_con_motivo(banco):
    _, libro = lote_creado(banco, 4)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    banco.cluster.vms[102]["config"]["lock"] = "backup"
    eventos = []
    servicio = _servicio(banco)
    res = servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        eventos.append,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
        forzar_apagado=frozenset({100, 101, 102, 103}),
        forzar_desproteccion=frozenset({100, 101, 102, 103}),
        permisos=PERMISOS_COMPLETOS,
    )
    por = {r.vmid: r for r in res}
    assert por[100].acciones == (ACCION_APAGADA, ACCION_BORRADA)
    assert por[101].acciones == (ACCION_DESPROTEGIDA, ACCION_BORRADA)
    assert por[103].acciones == (ACCION_BORRADA,)
    assert por[102].estado == EstadoRollback.OMITIDA
    assert por[102].acciones == ()
    assert por[102].error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    # el observador recibió el resultado final de cada máquina
    finales = {e.vmid: e for e in eventos if e.estado == EstadoRollback.ELIMINADA}
    assert finales[100].acciones == por[100].acciones


def test_ca_a6_4_4_es_propia_no_se_amplia_etiqueta_y_nombre_del_libro(banco):
    _, libro = lote_creado(banco, 1)
    entrada = libro.instantanea()[0]
    cfg = dict(banco.cluster.vms[100]["config"])
    assert es_propia(cfg, entrada, libro.id_lote, True)
    # etiqueta de OTRO lote y nombre distinto: ajena
    ajena = {"name": "otro", "tags": "proxlaunch;lote-zzzz9999"}
    assert not es_propia(ajena, entrada, libro.id_lote, True)
    # nombre igual pero sin etiqueta del lote (con etiquetado): sigue sin ser propia
    sin_etiqueta = {"name": cfg["name"], "tags": "otra"}
    assert not es_propia(sin_etiqueta, entrada, libro.id_lote, True)
    # protegida/encendida no cambian la definición
    assert es_propia({**cfg, "protection": "1"}, entrada, libro.id_lote, True)


def test_ca_a6_4_4_un_informe_de_otro_lote_no_amplia_la_propiedad(banco):
    """Una MV con etiqueta de un lote anterior no es propia del actual aunque el nombre coincida
    en parte: no se toca."""
    _, libro = lote_creado(banco, 2)
    banco.cluster.vms[100]["config"]["tags"] = banco.cluster.etiquetas_del_lote("viejo0001")
    banco.cluster.vms[100]["config"]["name"] = "otro-nombre"
    encender_en_servidor(banco, 100)
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert banco.cluster.llamadas_a("POST", "status/stop") == []


# --- Casos límite -----------------------------------------------------------


def test_cl_a3_propias_y_ajenas_encendidas_y_protegidas_mezcladas(banco):
    _, libro = lote_creado(banco, 4)
    encender_en_servidor(banco, 100, 101, 102)
    proteger_en_servidor(banco, 101, 103)
    # 101: el VMID fue reutilizado por otra persona; 103: ajena protegida
    banco.cluster.vms[101]["config"]["name"] = "reutilizado"
    banco.cluster.vms[103]["config"]["name"] = "a-mano"
    banco.cluster.vms[103]["config"]["tags"] = banco.cluster.etiquetas_del_lote(libro.id_lote)
    insp = _inspeccionar(banco, libro)
    assert sorted(insp.encendidas) == [100, 102]
    assert insp.protegidas == ()
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    for v in (101, 103):
        assert res[v].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
        assert orden_de_llamadas(banco, v) == []
    assert res[100].estado == res[102].estado == EstadoRollback.ELIMINADA
    assert sorted(banco.cluster.deletes) == [100, 102]


def test_cl_a3_ajena_con_la_misma_etiqueta_y_otro_nombre_no_se_toca(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 101)
    proteger_en_servidor(banco, 101)
    banco.cluster.vms[101]["config"]["name"] = "creada-a-mano"  # misma etiqueta del lote
    insp = _inspeccionar(banco, libro)
    assert insp.encendidas == () and insp.protegidas == ()
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[101].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert orden_de_llamadas(banco, 101) == []


def test_cl_a4_encendido_fallido_la_maquina_figura_apagada_y_se_borra_sin_apagar(banco):
    _, libro = lote_creado(banco, 1)
    # el encendido falló: la MV quedó creada y apagada
    assert banco.cluster.vms[100]["status"] == "stopped"
    insp = _inspeccionar(banco, libro)
    assert insp.encendidas == ()
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].acciones == (ACCION_BORRADA,)
    assert banco.cluster.llamadas_a("POST", "status/stop") == []


def test_cl_a4_lote_real_con_encender_y_arranque_fallido_se_deshace_sin_stop(banco):
    banco.cluster.regla(
        "POST", r"/status/start", error_api("403", CodigoError.PERMISO_INSUFICIENTE)
    )
    plan = banco.planificar(definicion(1, vmid_inicial=100, plantilla_vm=plantilla(encender=True)))
    libro = banco.ejecutar(plan)
    assert banco.cluster.vms[100]["status"] == "stopped"
    res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.ELIMINADA
    assert banco.cluster.llamadas_a("POST", "status/stop") == []


# --- RNF-A2: secretos y log ---------------------------------------------------------


def test_rnf_a2_el_detalle_de_un_fallo_de_stop_no_filtra_credenciales(banco, caplog):
    _, libro = lote_creado(banco, 1)
    encender_en_servidor(banco, 100)
    secreto = "SECRETO-ROLLBACK-7788"
    banco.cluster.exitstatus[100] = f"fallo password={secreto}"
    with caplog.at_level(logging.DEBUG, logger="proxlaunch"):
        res = _deshacer(banco, libro, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.FALLO
    assert secreto not in (res[100].error.detalle_tecnico or "")
    assert secreto not in str(res[100].error.params)
    for rec in caplog.records:
        assert secreto not in rec.getMessage()
