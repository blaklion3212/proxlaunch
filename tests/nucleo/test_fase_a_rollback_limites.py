"""Fase A (0.6.0): Deshacer, casos límite y de error (complementa ``test_fase_a_rollback.py``).

Cubre CA-A1.5.3 y CA-A6.3.3 con permisos por máquina (CL-A5), cancelación y parada global durante
un Deshacer forzado, ``inspeccionar`` ante máquinas ilegibles, ajenas o bloqueadas (CA-A6.4.1,
CL-A3) y la elegibilidad de estados incompletos.
"""

from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.modelos import EstadoRollback, MotivoPausa
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ACCION_APAGADA, ACCION_DESPROTEGIDA, ServicioRollback
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos

from .apoyo_fase_a_p2 import (
    PERMISOS_COMPLETOS,
    encender_en_servidor,
    error_api,
    lote_creado,
    orden_de_llamadas,
    permisos,
    proteger_en_servidor,
)
from .apoyo_lote import envio_incierto


def _servicio(banco):
    return ServicioRollback(banco.sesion, banco.reloj)


def _deshacer(banco, libro, *, control=None, forzar=False, **kw):
    servicio = _servicio(banco)
    candidatos = servicio.elegibles(libro, etiquetado=True)
    # «forzar» = el usuario confirmó todas las máquinas del libro.
    todas = frozenset(c.entrada.elemento.vmid for c in candidatos) if forzar else frozenset()
    res = servicio.deshacer(
        candidatos,
        lambda r: None,
        control or ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
        forzar_apagado=todas,
        forzar_desproteccion=todas,
        **kw,
    )
    return {r.vmid: r for r in res}


# --- CL-A5: privilegios concedidos solo en la ruta de una máquina -----------------------------


def test_cl_a5_powermgmt_concedido_solo_en_una_maquina_apaga_solo_esa(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100, 101)
    p = permisos("VM.PowerMgmt", ruta="/vms/101")  # sin propagación a otras máquinas
    res = _deshacer(banco, libro, forzar=True, permisos=p)
    assert res[100].error.codigo == CodigoError.ROLLBACK_SIN_POWERMGMT
    assert res[101].estado == EstadoRollback.ELIMINADA
    assert orden_de_llamadas(banco, 100) == []


def test_cl_a5_privilegio_sin_propagacion_en_vms_no_alcanza_a_las_maquinas(banco):
    _, libro = lote_creado(banco, 1)
    proteger_en_servidor(banco, 100)
    sin_propagar = PermisosEfectivos({"/vms": {"VM.Config.Options": 0}})
    res = _deshacer(banco, libro, forzar=True, permisos=sin_propagar)
    assert res[100].error.codigo == CodigoError.ROLLBACK_SIN_OPCIONES


def test_cl_a5_privilegio_en_la_raiz_con_propagacion_cubre_todas(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    p = permisos("VM.PowerMgmt", "VM.Config.Options", ruta="/")
    res = _deshacer(banco, libro, forzar=True, permisos=p)
    assert all(r.estado == EstadoRollback.ELIMINADA for r in res.values())


# --- Cancelación y parada global --------------------------------------------------------------


def test_cancelado_antes_de_empezar_no_se_apaga_ni_desprotege_ni_borra(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100)
    proteger_en_servidor(banco, 101)
    control = ControlLote()
    control.cancelado.set()
    banco.cluster.reiniciar_llamadas()
    res = _deshacer(banco, libro, control=control, forzar=True, permisos=PERMISOS_COMPLETOS)
    assert all(r.estado == EstadoRollback.NO_ENVIADA for r in res.values())
    assert banco.cluster.total("POST") == 0
    assert banco.cluster.total("PUT") == 0
    assert banco.cluster.total("DELETE") == 0


def test_un_403_en_el_delete_tras_apagar_detiene_el_resto_y_conserva_lo_hecho(banco):
    """El 403 del DELETE es global (como en 0.5.1): las demás quedan sin enviar."""
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100)
    banco.cluster.regla("DELETE", r"/qemu/100$", error_api("403", CodigoError.PERMISO_INSUFICIENTE))
    control = ControlLote()
    res = _deshacer(banco, libro, control=control, forzar=True, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.FALLO
    assert res[100].acciones == (ACCION_APAGADA,)  # el informe dice lo que sí se hizo
    assert res[101].estado == res[102].estado == EstadoRollback.NO_ENVIADA
    assert control.motivo_pausa == MotivoPausa.ERROR_GLOBAL
    assert sorted(banco.cluster.deletes) == [100]


def test_un_fallo_de_apagado_no_para_las_demas_maquinas_del_mismo_nodo(banco):
    _, libro = lote_creado(banco, 3)
    encender_en_servidor(banco, 100, 101, 102)
    banco.cluster.exitstatus[100] = "falló"
    res = _deshacer(banco, libro, forzar=True, permisos=PERMISOS_COMPLETOS)
    assert res[100].estado == EstadoRollback.FALLO
    assert res[101].estado == res[102].estado == EstadoRollback.ELIMINADA


def test_dos_nodos_cada_maquina_se_apaga_en_su_nodo(fabrica_banco):
    banco = fabrica_banco(("pve1", "pve2"))
    _, libro = lote_creado(banco, 4)
    nodos = {v: d["nodo"] for v, d in banco.cluster.vms.items()}
    assert set(nodos.values()) == {"pve1", "pve2"}
    encender_en_servidor(banco, *banco.cluster.vms)
    res = _deshacer(banco, libro, forzar=True, permisos=PERMISOS_COMPLETOS)
    assert all(r.estado == EstadoRollback.ELIMINADA for r in res.values())
    for ll in banco.cluster.llamadas_a("POST", "status/stop"):
        vmid = int(ll.ruta.split("/")[-3])
        assert f"/nodes/{nodos[vmid]}/" in ll.ruta


# --- inspeccionar -----------------------------------------------------------------------------


def test_inspeccionar_ignora_las_maquinas_con_lock_ajenas_inexistentes_e_ilegibles(banco):
    _, libro = lote_creado(banco, 5)
    encender_en_servidor(banco, 100, 101, 102, 103, 104)
    proteger_en_servidor(banco, 100, 101, 102, 103, 104)
    banco.cluster.vms[100]["config"]["lock"] = "backup"  # lock: nunca se fuerza
    banco.cluster.vms[101]["config"]["name"] = "ajena"  # ajena
    del banco.cluster.vms[102]  # ya no existe
    banco.cluster.regla("GET", r"/qemu/103/config$", error_api("500 ilegible"))  # no se puede leer
    insp = _servicio(banco).inspeccionar(
        _servicio(banco).elegibles(libro, etiquetado=True),
        id_lote=libro.id_lote,
        etiquetado=True,
    )
    assert insp.encendidas == (104,)
    assert insp.protegidas == (104,)


def test_inspeccionar_solo_mira_los_candidatos_elegibles(banco):
    _, libro = lote_creado(banco, 2)
    encender_en_servidor(banco, 100, 101)
    servicio = _servicio(banco)
    candidatos = servicio.elegibles(libro, etiquetado=True)
    solo_uno = servicio.elegibles(libro, etiquetado=True, excluir_vmids=[100])
    assert len(candidatos) == 2 and len(solo_uno) == 1
    insp = servicio.inspeccionar(solo_uno, id_lote=libro.id_lote, etiquetado=True)
    assert insp.encendidas == (101,)


def test_inspeccionar_sin_candidatos_devuelve_vacio(banco):
    insp = _servicio(banco).inspeccionar([], id_lote="x", etiquetado=True)
    assert insp.encendidas == () and insp.protegidas == ()


def test_inspeccionar_maquina_con_protection_cero_no_cuenta_como_protegida(banco):
    _, libro = lote_creado(banco, 1)
    banco.cluster.vms[100]["config"]["protection"] = "0"
    insp = _servicio(banco).inspeccionar(
        _servicio(banco).elegibles(libro, etiquetado=True), id_lote=libro.id_lote, etiquetado=True
    )
    assert insp.protegidas == ()


def test_el_borrado_posterior_a_desproteger_se_pide_sin_purgar_discos(banco):
    """D-21 sigue vigente en el camino forzado: ``purge`` nunca se envía."""
    _, libro = lote_creado(banco, 1)
    proteger_en_servidor(banco, 100)
    _deshacer(banco, libro, forzar=True, permisos=PERMISOS_COMPLETOS)
    params = banco.cluster.params_delete[100]
    assert "purge" not in (params or {})


def test_desprotegida_queda_en_las_acciones_aunque_el_delete_sea_incierto(banco):
    _, libro = lote_creado(banco, 1)
    proteger_en_servidor(banco, 100)
    banco.cluster.regla("DELETE", r"/qemu/100$", envio_incierto())
    res = _deshacer(banco, libro, forzar=True, permisos=PERMISOS_COMPLETOS)
    assert res[100].acciones[0] == ACCION_DESPROTEGIDA
    assert res[100].estado == EstadoRollback.INCIERTA  # sigue existiendo: no se reintenta
    assert banco.cluster.deletes[100] == 1
