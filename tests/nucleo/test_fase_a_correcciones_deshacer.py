"""Correcciones de revisión de Deshacer forzado (0.6.0): SEG-A-01, QA-A-01, QA-A-06 y QA-A-07.

El forzado solo alcanza a las máquinas que el usuario vio en la confirmación (conjuntos
``forzar_apagado`` / ``forzar_desproteccion``); lo que cambia después se omite; ``inspeccionar``
ya no esconde las ilegibles y separa las que no se pueden forzar por falta de privilegio.
"""

from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.modelos import EstadoRollback
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import (
    ACCION_APAGADA,
    ACCION_BORRADA,
    ACCION_DESPROTEGIDA,
    ServicioRollback,
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
from .apoyo_lote import NORMAL


def _servicio(banco):
    return ServicioRollback(banco.sesion, banco.reloj)


def _inspeccionar(banco, libro, permisos=None):
    servicio = _servicio(banco)
    return servicio.inspeccionar(
        servicio.elegibles(libro, etiquetado=True),
        id_lote=libro.id_lote,
        etiquetado=True,
        permisos=permisos,
    )


def _deshacer(banco, libro, apagado=(), desproteccion=(), permisos=PERMISOS_COMPLETOS):
    servicio = _servicio(banco)
    res = servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        lambda r: None,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
        forzar_apagado=frozenset(apagado),
        forzar_desproteccion=frozenset(desproteccion),
        permisos=permisos,
    )
    return {r.vmid: r for r in res}


# --- SEG-A-01: el forzado se limita a lo confirmado -------------------------------------------


def test_seg_a_01_lo_que_cambia_durante_el_dialogo_queda_omitido(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100)
    insp = _inspeccionar(banco, libro)
    assert insp.encendidas == (100,) and insp.protegidas == ()
    # Con el diálogo abierto: alguien enciende la 101 y protege la 102.
    encender_en_servidor(banco, 101)
    proteger_en_servidor(banco, 102)
    res = _deshacer(banco, libro, insp.encendidas, insp.protegidas)
    assert res[100].estado == EstadoRollback.ELIMINADA
    assert res[100].acciones == (ACCION_APAGADA, ACCION_BORRADA)
    assert res[101].estado == EstadoRollback.OMITIDA
    assert res[101].error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    assert res[102].estado == EstadoRollback.OMITIDA
    assert res[102].error.codigo == CodigoError.ROLLBACK_PROTEGIDA
    assert orden_de_llamadas(banco, 101) == [] and orden_de_llamadas(banco, 102) == []
    assert 101 in banco.cluster.vms and 102 in banco.cluster.vms


def test_seg_a_01_sin_conjuntos_nada_se_fuerza(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    res = _deshacer(banco, libro)
    assert res[100].error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    assert res[101].error.codigo == CodigoError.ROLLBACK_PROTEGIDA
    assert banco.cluster.llamadas_a("POST", "status/stop") == []
    assert banco.cluster.llamadas_a("PUT", "config") == []


def test_seg_a_01_apagado_confirmado_sin_desproteccion_confirmada_omite_la_protegida(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)
    res = _deshacer(banco, libro, apagado={100}, desproteccion=())
    assert res[100].estado == EstadoRollback.OMITIDA
    assert res[100].error.codigo == CodigoError.ROLLBACK_PROTEGIDA
    assert orden_de_llamadas(banco, 100) == []


def test_seg_a_01_desproteccion_confirmada_sin_apagado_confirmado_omite_la_encendida(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)
    res = _deshacer(banco, libro, apagado=(), desproteccion={100})
    assert res[100].error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    assert orden_de_llamadas(banco, 100) == []


def test_seg_a_01_lo_confirmado_se_apaga_desprotege_y_borra(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100, 101)
    insp = _inspeccionar(banco, libro)
    res = _deshacer(banco, libro, insp.encendidas, insp.protegidas)
    assert res[100].acciones == (ACCION_APAGADA, ACCION_DESPROTEGIDA, ACCION_BORRADA)
    assert res[101].acciones == (ACCION_DESPROTEGIDA, ACCION_BORRADA)
    assert orden_de_llamadas(banco, 100) == ["stop", "put-config", "delete"]


# --- QA-A-01 / QA-A-06: ilegibles, nombres y falta de privilegio ------------------------------


def test_qa_a_01_las_ilegibles_se_listan_en_lugar_de_descartarse(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100, 101)
    banco.cluster.regla("GET", r"/qemu/101/config$", error_api("500 ilegible"))
    insp = _inspeccionar(banco, libro)
    assert insp.ilegibles == (101,)
    assert insp.encendidas == (100,)
    assert insp.hay_algo_que_avisar


def test_qa_a_01_una_ilegible_encendida_se_omite_al_deshacer(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 101)
    regla = banco.cluster.regla("GET", r"/qemu/101/config$", error_api("500"), veces=1)
    insp = _inspeccionar(banco, libro)
    assert regla.disparos == 1 and insp.ilegibles == (101,)
    res = _deshacer(banco, libro, insp.encendidas, insp.protegidas)
    assert res[101].error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    assert res[100].estado == EstadoRollback.ELIMINADA


def test_qa_a_06_la_inspeccion_trae_el_nombre_de_cada_maquina_mencionada(banco):
    plan, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    banco.cluster.regla("GET", r"/qemu/102/config$", error_api("500"))
    insp = _inspeccionar(banco, libro)
    nombres = {e.elemento.vmid: e.elemento.nombre for e in libro.instantanea()}
    assert set(insp.nombres) == {100, 101, 102}
    assert all(insp.nombres[v] == nombres[v] for v in insp.nombres)


def test_qa_a_06_sin_privilegio_se_separa_de_las_forzables(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    insp = _inspeccionar(banco, libro, SIN_POWERMGMT)
    assert (insp.encendidas, insp.encendidas_sin_privilegio) == ((), (100,))
    assert (insp.protegidas, insp.protegidas_sin_privilegio) == ((101,), ())
    insp = _inspeccionar(banco, libro, SIN_OPCIONES)
    assert (insp.encendidas, insp.protegidas_sin_privilegio) == ((100,), (101,))
    insp = _inspeccionar(banco, libro, SIN_NINGUNO)
    assert not insp.hay_forzables and insp.hay_algo_que_avisar


def test_qa_a_06_permisos_desconocidos_dejan_todo_como_forzable(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    insp = _inspeccionar(banco, libro, None)
    assert insp.encendidas == (100,) and insp.protegidas == (101,)
    assert insp.encendidas_sin_privilegio == () and insp.protegidas_sin_privilegio == ()


def test_qa_a_06_sin_nada_que_avisar_la_inspeccion_lo_dice(banco):
    _, libro = lote_creado(banco, 2)
    insp = _inspeccionar(banco, libro)
    assert not insp.hay_algo_que_avisar and not insp.hay_forzables


# --- QA-A-07: se revalida tras el stop y tras el PUT ------------------------------------------


def test_qa_a_07_propiedad_perdida_tras_el_stop_no_desprotege_ni_borra(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)

    def pierde_la_etiqueta(_ll):
        banco.cluster.vms[100]["config"]["tags"] = "otra-persona"
        banco.cluster.vms[100]["config"]["name"] = "ajena"
        return NORMAL

    banco.cluster.regla("POST", r"/100/status/stop$", pierde_la_etiqueta)
    res = _deshacer(banco, libro, {100}, {100})
    assert res[100].estado == EstadoRollback.OMITIDA
    assert res[100].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert res[100].acciones == (ACCION_APAGADA,)  # se apagó, y ahí quedó
    assert orden_de_llamadas(banco, 100) == ["stop"]


def test_qa_a_07_lock_tras_el_stop_omite_sin_desproteger(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)

    def aparece_lock(_ll):
        banco.cluster.vms[100]["config"]["lock"] = "backup"
        return NORMAL

    banco.cluster.regla("POST", r"/100/status/stop$", aparece_lock)
    res = _deshacer(banco, libro, {100}, {100})
    assert res[100].error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    assert res[100].acciones == (ACCION_APAGADA,)
    assert orden_de_llamadas(banco, 100) == ["stop"]


def test_qa_a_07_proteccion_nueva_tras_el_stop_sin_confirmar_omite(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)

    def se_protege(_ll):
        banco.cluster.vms[100]["config"]["protection"] = "1"
        return NORMAL

    banco.cluster.regla("POST", r"/100/status/stop$", se_protege)
    res = _deshacer(banco, libro, {100}, ())
    assert res[100].error.codigo == CodigoError.ROLLBACK_PROTEGIDA
    assert res[100].acciones == (ACCION_APAGADA,)
    assert orden_de_llamadas(banco, 100) == ["stop"]


def test_qa_a_07_proteccion_ya_quitada_tras_el_stop_evita_el_put(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 100)

    def alguien_desprotege(_ll):
        banco.cluster.vms[100]["config"]["protection"] = "0"
        return NORMAL

    banco.cluster.regla("POST", r"/100/status/stop$", alguien_desprotege)
    res = _deshacer(banco, libro, {100}, {100})
    assert res[100].estado == EstadoRollback.ELIMINADA
    assert orden_de_llamadas(banco, 100) == ["stop", "delete"]


def test_qa_a_07_propiedad_perdida_tras_el_put_no_borra(banco):
    _, libro = lote_creado(banco, 2)
    proteger_en_servidor(banco, 101)

    def cambia_dueno(_ll):
        banco.cluster.vms[101]["config"]["name"] = "ajena"
        banco.cluster.vms[101]["config"]["tags"] = ""
        return NORMAL

    banco.cluster.regla("PUT", r"/101/config$", cambia_dueno)
    res = _deshacer(banco, libro, (), {101})
    assert res[101].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert res[101].acciones == (ACCION_DESPROTEGIDA,)
    assert orden_de_llamadas(banco, 101) == ["put-config"]


def test_qa_a_07_si_desaparece_tras_el_stop_queda_como_ya_no_existia(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)

    def desaparece(_ll):
        banco.cluster.vms.pop(100)
        return "UPID:pve1:0000:0000:0000:qmstop:100:root@pam:"

    banco.cluster.regla("POST", r"/100/status/stop$", desaparece)
    res = _deshacer(banco, libro, {100}, ())
    assert res[100].estado == EstadoRollback.YA_NO_EXISTIA
    assert orden_de_llamadas(banco, 100) == ["stop"]
