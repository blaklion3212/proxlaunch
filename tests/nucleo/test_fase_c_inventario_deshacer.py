"""Inventario de lotes (fase C, C1): Deshacer con doble control (PC-1, RF-C1.8) y RF-C3.10.

Requisitos: CA-C1.8.1 a CA-C1.8.11, CA-C1.10.4, CA-C1.11.1, CA-C1.11.3, CA-C3.10.1, V-C06, V-C08,
V-C09, CL-C2, CL-C3, CL-C6 y RNF-C6.1 («borrar solo con todas las condiciones, releídas justo
antes; nunca por nombre solamente»). Se comprueba SIEMPRE qué ``DELETE`` llegó al doble.
"""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.textos import texto_error
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.inventario.modelos import MotivoNoDeshacible
from proxlaunch.nucleo.inventario.propiedad import (
    candidatos_inventario,
    codigo_confirmado,
    es_propia_inventario,
    problema_seleccion,
)
from proxlaunch.nucleo.lote.constantes import MAX_LOTE
from proxlaunch.nucleo.lote.modelos import (
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
    EstadoRollback,
    ResultadoRollback,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import es_propia
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM

from .apoyo_fase_c_inventario import (
    CODIGO,
    OTRO_CODIGO,
    Mundo,
    etiquetas_lote,
    nota_origen,
    permisos,
)
from .apoyo_lote import (
    TODOS_LOS_CENTINELAS,
    error_http,
    volcar,
)

NADA = frozenset()


def _borrar(m: Mundo, detalle, marcadas, *, apagar=NADA, desproteger=NADA, permisos_=None):
    """Ejecuta el Deshacer del inventario y devuelve ``{vmid: ResultadoRollback}`` (el último)."""
    vistos: list[ResultadoRollback] = []
    res = m.servicio.deshacer(
        detalle,
        marcadas,
        vistos.append,
        ControlLote(),
        forzar_apagado=frozenset(apagar),
        forzar_desproteccion=frozenset(desproteger),
        permisos=permisos_,
    )
    return {r.vmid: r for r in res}


def _deletes(m: Mundo) -> list[int]:
    return sorted(m.cluster.deletes.elements())


def _todas(detalle) -> set[int]:
    return {mv.recurso.vmid for mv in detalle.maquinas}


# --- CA-C1.8.1 / CA-C1.8.2: qué es borrable -----------------------------------------------------


def test_ca_c1_8_1_de_cuatro_mvs_tres_son_borrables_y_la_sin_nota_dice_por_que():
    m = Mundo()
    for vmid in (101, 102, 103):
        m.cluster.agregar_mv(vmid)
    m.cluster.agregar_mv(104, nota=False)
    detalle = m.detallar()
    deshacibles = {mv.recurso.vmid for mv in detalle.maquinas if mv.deshacible}
    assert deshacibles == {101, 102, 103}
    sin_nota = next(mv for mv in detalle.maquinas if mv.recurso.vmid == 104)
    assert sin_nota.motivos == (MotivoNoDeshacible.SIN_NOTA,)
    assert [c.entrada.elemento.vmid for c in candidatos_inventario(detalle, _todas(detalle))] == [
        101, 102, 103,
    ]  # fmt: skip


def test_ca_c1_8_2_nota_de_otro_lote_con_la_etiqueta_de_este_no_es_borrable_cl_c2():
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.agregar_mv(102, etiquetas=etiquetas_lote(CODIGO), nota=nota_origen(OTRO_CODIGO))
    detalle = m.detallar()
    mv = next(x for x in detalle.maquinas if x.recurso.vmid == 102)
    assert mv.motivos == (MotivoNoDeshacible.NOTA_OTRO_LOTE,) and not mv.deshacible
    assert [c.entrada.elemento.vmid for c in candidatos_inventario(detalle, {101, 102})] == [101]
    _borrar(m, detalle, {101, 102})
    assert _deletes(m) == [101]


# --- PC-1: nunca se borra sin las dos etiquetas + nota con el mismo lote (+ el resto) -----------


ESCENARIOS_NO_BORRABLES = {
    "sin_etiqueta_proxlaunch": {"etiquetas": f"lote-{CODIGO}"},
    "sin_etiqueta_de_lote": {"etiquetas": "proxlaunch"},
    "etiqueta_de_otro_lote": {"etiquetas": f"proxlaunch;lote-{OTRO_CODIGO}"},
    "sin_etiquetas": {"etiquetas": ""},
    "sin_nota": {"nota": False},
    "nota_de_otro_lote": {"nota": nota_origen(OTRO_CODIGO)},
    "nota_sin_lote": {"nota": "Creada con ProxLaunch 0.8.0\n\n- Fecha: 2026-11-20T10:00:00+00:00"},
    "nota_solo_nombra_el_lote_en_texto_libre": {
        "nota": f"del lote {CODIGO}, creada con ProxLaunch"
    },
    "nota_con_lote_en_mayusculas": {"nota": nota_origen(CODIGO.upper())},
    "plantilla": {"template": 1},
    "con_lock": {"lock": "backup"},
    "estado_desconocido": {"status": "unknown"},
}


@pytest.mark.parametrize("escenario", sorted(ESCENARIOS_NO_BORRABLES))
def test_pc1_una_mv_a_la_que_le_falta_cualquier_condicion_no_se_borra_aunque_este_marcada(
    escenario,
):
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.agregar_mv(102, "se-llama-igual-que-las-demas", **ESCENARIOS_NO_BORRABLES[escenario])
    detalle = m.detallar()
    # Sin la etiqueta del lote en la lista la MV ni siquiera forma parte del lote.
    mala = next((mv for mv in detalle.maquinas if mv.recurso.vmid == 102), None)
    assert mala is None or not mala.deshacible, escenario
    resultados = _borrar(m, detalle, _todas(detalle) | {102})
    assert 102 not in m.cluster.deletes, escenario
    assert 102 not in resultados
    assert m.cluster.deletes[101] == 1


@pytest.mark.parametrize("escenario", sorted(set(ESCENARIOS_NO_BORRABLES) - {"estado_desconocido"}))
def test_pc1_el_deshacer_nunca_confia_en_la_lista_y_relee_la_config_justo_antes(escenario):
    """La MV era perfecta al listar; cuando se borra ya incumple una condición (CL-C6, QA-A-07)."""
    modificaciones = ESCENARIOS_NO_BORRABLES[escenario]
    m = Mundo()
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    assert all(mv.deshacible for mv in detalle.maquinas)
    cfg = m.cluster.vms[102]["config"]
    if "etiquetas" in modificaciones:
        cfg["tags"] = modificaciones["etiquetas"]
    if modificaciones.get("nota") is False:
        del cfg["description"]
    elif "nota" in modificaciones:
        cfg["description"] = modificaciones["nota"]
    for clave in ("template", "lock"):
        if clave in modificaciones:
            cfg[clave] = modificaciones[clave]
    resultados = _borrar(m, detalle, {101, 102})
    assert 102 not in m.cluster.deletes, escenario
    assert resultados[102].estado == EstadoRollback.OMITIDA, escenario
    assert resultados[101].estado == EstadoRollback.ELIMINADA


def test_pc1_una_mv_cuyo_estado_pasa_a_desconocido_antes_del_borrado_se_omite():
    m = Mundo()
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    m.cluster.vms[102]["status"] = "unknown"
    _borrar(m, detalle, {101, 102})
    assert 102 not in m.cluster.deletes


def test_pc1_nunca_se_decide_por_el_nombre_solamente():
    """Una MV con el nombre idéntico al del plan pero sin etiquetas ni nota no se borra."""
    m = Mundo()
    m.cluster.agregar_mv(101, "web-01")
    m.cluster.agregar_mv(102, "web-02", etiquetas="", nota=False)
    detalle = m.detallar()
    m.cluster.vms[101]["config"]["tags"] = ""
    m.cluster.vms[101]["config"]["description"] = "web-01"
    _borrar(m, detalle, {101, 102})
    assert _deletes(m) == []


def test_pc1_es_propia_inventario_exige_etiquetas_nota_y_no_plantilla_sin_mirar_nombre():
    el = ElementoPlan(0, "x", 101, "pve1", ConfiguracionVM(vmid=101, nombre="x", nodo="pve1"))
    entrada = EntradaLibro(el, estado=EstadoMV.OK)
    buena = {"tags": etiquetas_lote(), "description": nota_origen(), "name": "otro-nombre"}
    assert es_propia_inventario(buena, entrada, CODIGO, True)
    assert es_propia_inventario(buena, entrada, CODIGO, False)  # «etiquetado» no la relaja
    for roto in (
        {**buena, "tags": f"lote-{CODIGO}"},
        {**buena, "tags": "proxlaunch"},
        {**buena, "tags": None},
        {**buena, "description": None},
        {**buena, "description": nota_origen(OTRO_CODIGO)},
        {**buena, "template": 1},
        {**buena, "template": "1"},
    ):
        assert not es_propia_inventario(roto, entrada, CODIGO, True), roto
    assert not es_propia_inventario(buena, entrada, "prueba", True)  # código no válido
    assert not es_propia_inventario(buena, entrada, OTRO_CODIGO, True)


def test_rf_c1_8_la_regla_por_defecto_del_rollback_de_sesion_no_cambia_rd_c2():
    """El Deshacer de la sesión sigue aceptando una MV con la etiqueta y el nombre del plan y
    sin nota; el del inventario, no (la regla propia solo se inyecta en el inventario)."""
    el = ElementoPlan(
        0, "web-01", 101, "pve1", ConfiguracionVM(vmid=101, nombre="web-01", nodo="pve1")
    )
    entrada = EntradaLibro(el, estado=EstadoMV.OK)
    sin_nota = {"name": "web-01", "tags": etiquetas_lote()}
    assert es_propia(sin_nota, entrada, CODIGO, True) is True
    assert es_propia_inventario(sin_nota, entrada, CODIGO, True) is False


# --- CA-C1.8.3: código de confirmación ----------------------------------------------------------


@pytest.mark.parametrize(
    "escrito",
    ["", " ", "ab12cd3", "ab12cd345", "ab12cd35", "otro", "ab12 cd34", "lote-ab12cd34", "AB12CD3"],
)
def test_ca_c1_8_3_un_codigo_incorrecto_o_vacio_no_confirma(escrito):
    assert codigo_confirmado(escrito, CODIGO) is False


@pytest.mark.parametrize(
    "escrito", ["ab12cd34", "AB12CD34", "Ab12Cd34", "  ab12cd34  ", "ab12cd34\n"]
)
def test_ca_c1_8_3_el_codigo_correcto_en_cualquier_caso_y_sin_espacios_confirma(escrito):
    assert codigo_confirmado(escrito, CODIGO) is True


def test_ca_c1_8_3_un_codigo_de_lote_vacio_nunca_se_confirma():
    assert codigo_confirmado("", "") is False
    assert codigo_confirmado("  ", "") is False


# --- CA-C1.8.4: desmarcadas no se tocan ---------------------------------------------------------


def test_ca_c1_8_4_una_mv_desmarcada_no_recibe_ninguna_peticion_ni_lectura_ni_delete():
    m = Mundo()
    for vmid in (101, 102, 103):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    m.cluster.llamadas.clear()
    _borrar(m, detalle, {101, 103})
    assert not [c for c in m.cluster.llamadas if "/qemu/102" in c.ruta]
    assert _deletes(m) == [101, 103] and 102 in m.cluster.vms


def test_ca_c1_8_4_con_ninguna_marcada_no_se_emite_nada():
    m = Mundo()
    m.cluster.agregar_mv(101)
    detalle = m.detallar()
    m.cluster.llamadas.clear()
    assert _borrar(m, detalle, set()) == {}
    assert m.cluster.llamadas == []


def test_ca_c1_8_4_un_vmid_marcado_que_no_esta_en_el_lote_se_ignora():
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.agregar_mv(500, lote=OTRO_CODIGO)  # de otro lote, jamás se borra desde este
    detalle = m.detallar()
    _borrar(m, detalle, {101, 500, 99999})
    assert _deletes(m) == [101] and 500 in m.cluster.vms


# --- CA-C1.8.5: encendidas y protegidas (forzado de la fase A) ----------------------------------


def test_ca_c1_8_5_la_inspeccion_lista_encendidas_y_protegidas_y_es_solo_lectura():
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    m.cluster.agregar_mv(102, protection=1)
    m.cluster.agregar_mv(103)
    detalle = m.detallar()
    m.cluster.llamadas.clear()
    insp = m.servicio.inspeccionar(detalle, _todas(detalle), None)
    assert insp.encendidas == (101,) and insp.protegidas == (102,)
    assert insp.hay_algo_que_avisar and not insp.ilegibles
    assert m.cluster.solo_lecturas and m.cluster.escrituras == []


def test_ca_c1_8_5_sin_forzar_una_encendida_y_una_protegida_se_omiten_sin_escribir():
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    m.cluster.agregar_mv(102, protection=1)
    detalle = m.detallar()
    m.cluster.llamadas.clear()
    resultados = _borrar(m, detalle, {101, 102})
    assert {r.estado for r in resultados.values()} == {EstadoRollback.OMITIDA}
    assert m.cluster.escrituras == [] and _deletes(m) == []


def test_ca_c1_8_5_cancelar_el_dialogo_forzado_equivale_a_no_escribir_nada():
    """«Cancelar» no llama a ``deshacer``: la inspección no dejó ninguna escritura."""
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    m.cluster.agregar_mv(102, protection=1)
    detalle = m.detallar()
    m.servicio.inspeccionar(detalle, {101, 102}, None)
    assert m.cluster.escrituras == []


def test_ca_c1_8_5_con_forzar_se_apaga_y_desprotege_solo_lo_visto_y_luego_se_borra():
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    m.cluster.agregar_mv(102, protection=1)
    m.cluster.agregar_mv(103)
    detalle = m.detallar()
    insp = m.servicio.inspeccionar(detalle, _todas(detalle), None)
    m.cluster.llamadas.clear()
    resultados = _borrar(
        m, detalle, _todas(detalle),
        apagar=frozenset(insp.encendidas), desproteger=frozenset(insp.protegidas),
    )  # fmt: skip
    assert all(r.estado == EstadoRollback.ELIMINADA for r in resultados.values())
    assert resultados[101].acciones == ("apagada", "borrada")
    assert resultados[102].acciones == ("desprotegida", "borrada")
    assert resultados[103].acciones == ("borrada",)
    escrituras = m.cluster.escrituras
    assert ("POST", "/nodes/pve1/qemu/101/status/stop") in escrituras
    assert ("PUT", "/nodes/pve1/qemu/102/config") in escrituras
    assert not [e for e in escrituras if "103" in e[1] and e[0] != "DELETE"]
    assert _deletes(m) == [101, 102, 103]


def test_ca_c1_8_5_una_mv_que_se_enciende_tras_el_dialogo_no_se_fuerza_cl_c6():
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    m.cluster.agregar_mv(102)
    detalle = m.detallar()
    insp = m.servicio.inspeccionar(detalle, {101, 102}, None)
    assert insp.encendidas == (101,)
    m.cluster.vms[102]["status"] = "running"  # se enciende mientras el usuario leía
    resultados = _borrar(m, detalle, {101, 102}, apagar=frozenset(insp.encendidas))
    assert resultados[101].estado == EstadoRollback.ELIMINADA
    assert resultados[102].estado == EstadoRollback.OMITIDA
    assert resultados[102].error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    assert 102 not in m.cluster.deletes
    assert not [e for e in m.cluster.escrituras if "/102" in e[1]]


def test_ca_c1_8_5_sin_los_privilegios_de_la_fase_a_las_forzadas_se_omiten_con_motivo():
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    detalle = m.detallar()
    sin = permisos({"/": {"VM.Audit": 1, "VM.Allocate": 1}})  # falta VM.PowerMgmt
    resultados = _borrar(m, detalle, {101}, apagar={101}, permisos_=sin)
    assert resultados[101].estado == EstadoRollback.OMITIDA
    assert resultados[101].error.codigo == CodigoError.ROLLBACK_SIN_POWERMGMT
    assert m.cluster.escrituras == []


# --- CA-C1.8.6: cambios entre la lista y el borrado ---------------------------------------------


def test_ca_c1_8_6_una_mv_que_pasa_a_plantilla_entre_la_lista_y_el_borrado_se_omite():
    m = Mundo()
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    m.cluster.vms[101]["config"]["template"] = 1
    resultados = _borrar(m, detalle, {101, 102})
    assert resultados[101].estado == EstadoRollback.OMITIDA
    assert resultados[101].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert _deletes(m) == [102]


def test_ca_c1_8_6_una_mv_que_cambia_de_etiqueta_se_omite_con_motivo_y_sin_delete():
    m = Mundo()
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    m.cluster.vms[102]["config"]["tags"] = "proxlaunch;lote-00000000"
    resultados = _borrar(m, detalle, {101, 102})
    assert resultados[102].estado == EstadoRollback.OMITIDA
    assert resultados[102].error is not None and resultados[102].error.codigo
    assert _deletes(m) == [101]


def test_ca_c1_8_6_una_mv_cuyo_nombre_cambia_pero_sigue_siendo_propia_si_se_borra():
    """El nombre no interviene en la propiedad del inventario (ni a favor ni en contra)."""
    m = Mundo()
    m.cluster.agregar_mv(101, "web-01")
    detalle = m.detallar()
    m.cluster.vms[101]["config"]["name"] = "renombrada-a-mano"
    assert _borrar(m, detalle, {101})[101].estado == EstadoRollback.ELIMINADA


# --- CA-C1.8.7 / RF-C3.10: el DELETE ------------------------------------------------------------


def test_ca_c1_8_7_el_delete_lleva_destroy_unreferenced_disks_0_y_no_lleva_purge(rsps):
    m = Mundo(rsps=rsps)
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    m.cluster.trazas.clear()
    resultados = _borrar(m, detalle, {101, 102})
    deletes = [(met, ruta, cons, cuerpo) for met, ruta, cons, cuerpo in m.cluster.trazas
               if met == "DELETE"]  # fmt: skip
    assert sorted(d[1] for d in deletes) == ["/nodes/pve1/qemu/101", "/nodes/pve1/qemu/102"]
    assert all(d[2] == "destroy-unreferenced-disks=0" for d in deletes)
    assert all("purge" not in d[2] and d[3] == b"" for d in deletes)
    assert all("purge" not in t[1] and "purge" not in t[2] for t in m.cluster.trazas)
    assert all(r.estado == EstadoRollback.ELIMINADA for r in resultados.values())


def test_ca_c1_8_7_solo_se_borran_mvs_nunca_discos_archivos_ni_snippets(rsps):
    m = Mundo(rsps=rsps)
    m.cluster.agregar_mv(101, ide2="local:cloudinit", cicustom="user=snip:snippets/a.yaml")
    detalle = m.detallar()
    m.cluster.trazas.clear()
    _borrar(m, detalle, {101})
    rutas_delete = [t[1] for t in m.cluster.trazas if t[0] == "DELETE"]
    assert rutas_delete == ["/nodes/pve1/qemu/101"]
    assert not [t for t in m.cluster.trazas if "storage" in t[1] or "snippets" in t[1]]


def test_ca_c3_10_1_el_delete_es_identico_con_o_sin_firewall_y_no_toca_grupos(rsps):
    m = Mundo(rsps=rsps)
    m.cluster.agregar_mv(101, net0="virtio=AA:BB:CC:DD:EE:01,bridge=vmbr0,firewall=1")
    m.cluster.agregar_mv(102, net0="virtio=AA:BB:CC:DD:EE:02,bridge=vmbr0")
    detalle = m.detallar()
    m.cluster.trazas.clear()
    _borrar(m, detalle, {101, 102})
    escrituras = [t for t in m.cluster.trazas if t[0] != "GET"]
    assert [(t[0], t[2]) for t in escrituras] == [("DELETE", "destroy-unreferenced-disks=0")] * 2
    assert not [t for t in m.cluster.trazas if "firewall" in t[1] or "/sdn" in t[1]]


def test_ca_c1_8_7_con_el_transporte_en_memoria_los_parametros_son_los_mismos_que_eliminar_vm():
    m = Mundo()
    m.cluster.agregar_mv(101)
    detalle = m.detallar()
    _borrar(m, detalle, {101})
    assert m.cluster.params_delete[101] == {"destroy-unreferenced-disks": 0}


# --- CA-C1.8.8: un 403 detiene el resto ---------------------------------------------------------


def test_ca_c1_8_8_un_403_en_el_primer_delete_deja_las_demas_no_enviadas_y_nombra_el_permiso():
    m = Mundo()
    for vmid in (101, 102, 103, 104):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    m.cluster.regla(
        "DELETE", r"/qemu/\d+$",
        error_http(403, "Permission check failed (/vms/101, VM.Allocate)"),
    )  # fmt: skip
    resultados = _borrar(m, detalle, _todas(detalle))
    assert resultados[101].estado == EstadoRollback.FALLO
    assert [resultados[v].estado for v in (102, 103, 104)] == [EstadoRollback.NO_ENVIADA] * 3
    assert m.cluster.deletes.total() == 1 and _deletes(m) == [101]
    error = resultados[101].error
    assert error is not None and error.codigo == CodigoError.PERMISO_INSUFICIENTE
    texto = texto_error(error)
    assert "VM.Allocate" in texto and "/vms/101" in texto


def test_ca_c1_8_8_un_403_con_el_cuerpo_sin_privilegio_se_infiere_vm_allocate_y_la_ruta():
    m = Mundo()
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    m.cluster.regla("DELETE", r"/qemu/\d+$", error_http(403, "Forbidden"))
    resultados = _borrar(m, detalle, {101, 102})
    texto = texto_error(resultados[101].error)
    assert "VM.Allocate" in texto and "/vms/101" in texto
    assert resultados[102].estado == EstadoRollback.NO_ENVIADA


# --- CA-C1.8.9: lock ----------------------------------------------------------------------------


@pytest.mark.parametrize("bloqueo", ["backup", "migrate", "clone", "create", "raro-nuevo"])
def test_ca_c1_8_9_una_mv_con_lock_nunca_entra_en_el_deshacer_ni_se_fuerza(bloqueo):
    m = Mundo()
    m.cluster.agregar_mv(101, lock=bloqueo, status="running", protection=1)
    m.cluster.agregar_mv(102)
    detalle = m.detallar()
    mv = next(x for x in detalle.maquinas if x.recurso.vmid == 101)
    assert MotivoNoDeshacible.BLOQUEADA in mv.motivos
    assert [c.entrada.elemento.vmid for c in candidatos_inventario(detalle, {101, 102})] == [102]
    m.cluster.llamadas.clear()
    insp = m.servicio.inspeccionar(detalle, {101, 102}, None)
    assert 101 not in insp.encendidas and 101 not in insp.protegidas
    _borrar(m, detalle, {101, 102}, apagar={101, 102}, desproteger={101, 102})
    assert not [e for e in m.cluster.escrituras if "/101" in e[1]]
    assert _deletes(m) == [102]


def test_ca_c1_8_9_un_lock_que_aparece_despues_de_listar_tampoco_se_fuerza_ni_se_borra():
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    detalle = m.detallar()
    m.cluster.vms[101]["config"]["lock"] = "backup"
    resultados = _borrar(m, detalle, {101}, apagar={101}, desproteger={101})
    assert resultados[101].estado == EstadoRollback.OMITIDA
    assert resultados[101].error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    assert m.cluster.escrituras == []


# --- CA-C1.8.10: tope de 100 --------------------------------------------------------------------


def test_ca_c1_8_10_mas_de_100_marcadas_es_v_c09_y_el_servicio_no_emite_nada():
    assert MAX_LOTE == 100
    assert problema_seleccion(101) == "V-C09" and problema_seleccion(1000) == "V-C09"
    assert problema_seleccion(100) is None and problema_seleccion(1) is None
    assert problema_seleccion(0) == "vacia" and problema_seleccion(-1) == "vacia"
    m = Mundo()
    for vmid in range(2000, 2101):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    m.cluster.llamadas.clear()
    with pytest.raises(ValueError, match="V-C09"):
        _borrar(m, detalle, _todas(detalle))
    assert m.cluster.llamadas == [] and m.cluster.deletes.total() == 0


def test_ca_c1_8_10_exactamente_100_marcadas_si_se_borran_y_los_duplicados_no_cuentan_dos_veces():
    m = Mundo()
    for vmid in range(2000, 2101):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    marcadas = sorted(_todas(detalle))[:100]
    resultados = _borrar(
        m, detalle, [*marcadas, marcadas[0], marcadas[1]]
    )  # 102 entradas, 100 únicas
    assert len(resultados) == 100 and m.cluster.deletes.total() == 100
    assert 2100 in m.cluster.vms


def test_cl_c3_un_lote_de_150_se_lista_entero_y_se_borra_de_100_en_100():
    m = Mundo()
    for vmid in range(3000, 3150):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    assert len(detalle.maquinas) == 150
    with pytest.raises(ValueError):
        _borrar(m, detalle, _todas(detalle))
    primeras = sorted(_todas(detalle))[:100]
    _borrar(m, detalle, primeras)
    assert m.cluster.deletes.total() == 100
    detalle2 = m.detallar()
    assert len(detalle2.maquinas) == 50
    _borrar(m, detalle2, _todas(detalle2))
    assert m.cluster.deletes.total() == 150 and not m.cluster.vms


# --- CA-C1.8.11 y RNF-C6.5: el informe no filtra ------------------------------------------------


def test_ca_c1_8_11_los_resultados_no_contienen_claves_contrasenas_ni_la_nota_completa():
    m = Mundo()
    m.cluster.agregar_mv(
        101,
        nota=nota_origen(CODIGO, extra="NOTA-PRIVADA-COMPLETA usuario=root password=hunter2"),
        cipassword="**********",
    )
    m.cluster.agregar_mv(102, nota=nota_origen(OTRO_CODIGO, extra="OTRA-NOTA-PRIVADA"))
    m.cluster.regla("DELETE", r"/qemu/101$", error_http(500, "fallo interno del servidor"))
    detalle = m.detallar()
    resultados = _borrar(m, detalle, {101, 102})
    volcado = volcar(list(resultados.values())) + volcar(detalle)
    for prohibido in (*TODOS_LOS_CENTINELAS, "NOTA-PRIVADA-COMPLETA", "OTRA-NOTA-PRIVADA",
                      "hunter2", "Creada con ProxLaunch", "cipassword"):  # fmt: skip
        assert prohibido not in volcado, prohibido
    from .apoyo_api import TOKEN_SECRETO

    assert TOKEN_SECRETO not in volcado
    assert all(TOKEN_SECRETO not in texto_error(r.error) for r in resultados.values() if r.error)


# --- CA-C1.10.4: ya borrada por otro medio ------------------------------------------------------


def test_ca_c1_10_4_una_mv_borrada_por_otro_medio_se_informa_ya_no_existia_sin_delete():
    m = Mundo()
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    del m.cluster.vms[101]  # otro usuario (o «Lote > Deshacer») la borró
    resultados = _borrar(m, detalle, {101, 102})
    assert resultados[101].estado == EstadoRollback.YA_NO_EXISTIA and resultados[101].error is None
    assert 101 not in m.cluster.deletes
    assert resultados[102].estado == EstadoRollback.ELIMINADA


def test_ca_c1_10_4_si_el_delete_responde_que_ya_no_existe_cuenta_como_ya_no_existia():
    """Carrera: existe al releer pero el DELETE llega tarde."""
    m = Mundo()
    m.cluster.agregar_mv(101)
    detalle = m.detallar()

    def borrar_justo_antes(_ll):
        m.cluster.vms.pop(101, None)
        from .apoyo_lote import NORMAL

        return NORMAL

    m.cluster.regla("DELETE", r"/qemu/101$", borrar_justo_antes, veces=1)
    assert _borrar(m, detalle, {101})[101].estado == EstadoRollback.YA_NO_EXISTIA


# --- CA-C1.11: clúster --------------------------------------------------------------------------


def test_ca_c1_11_1_cada_delete_va_al_nodo_de_su_entrada():
    m = Mundo(("pve1", "pve2", "pve3"))
    reparto = {101: "pve1", 102: "pve2", 103: "pve3", 104: "pve2"}
    for vmid, nodo in reparto.items():
        m.cluster.agregar_mv(vmid, nodo=nodo)
    detalle = m.detallar()
    m.cluster.llamadas.clear()
    resultados = _borrar(m, detalle, _todas(detalle))
    assert all(r.estado == EstadoRollback.ELIMINADA for r in resultados.values())
    deletes = {c.ruta for c in m.cluster.llamadas if c.metodo == "DELETE"}
    assert deletes == {f"/nodes/{n}/qemu/{v}" for v, n in reparto.items()}
    lecturas_previas = {c.ruta for c in m.cluster.llamadas if c.ruta.endswith("/config")}
    assert lecturas_previas == {f"/nodes/{n}/qemu/{v}/config" for v, n in reparto.items()}


def test_ca_c1_11_3_con_un_nodo_caido_el_resto_del_lote_si_se_borra():
    from .apoyo_lote import nodo_caido

    m = Mundo(("pve1", "pve2"))
    m.cluster.agregar_mv(101, nodo="pve1")
    m.cluster.agregar_mv(102, nodo="pve2")
    m.cluster.agregar_mv(103, nodo="pve1")
    m.cluster.regla("GET", r"/nodes/pve2/", nodo_caido("pve2"))
    detalle = m.detallar()
    assert not next(x for x in detalle.maquinas if x.recurso.vmid == 102).deshacible
    resultados = _borrar(m, detalle, _todas(detalle))
    assert set(resultados) == {101, 103}
    assert all(r.estado == EstadoRollback.ELIMINADA for r in resultados.values())
    assert 102 in m.cluster.vms and 102 not in m.cluster.deletes


# --- Propia lectura y detención cooperativa -----------------------------------------------------


def test_rf_c1_8_detener_el_borrado_deja_las_pendientes_sin_enviar():
    m = Mundo()
    for vmid in (101, 102, 103):
        m.cluster.agregar_mv(vmid)
    detalle = m.detallar()
    control = ControlLote()
    control.cancelar()
    res = m.servicio.deshacer(
        detalle, _todas(detalle), lambda _r: None, control,
        forzar_apagado=NADA, forzar_desproteccion=NADA, permisos=None,
    )  # fmt: skip
    assert {r.estado for r in res} == {EstadoRollback.NO_ENVIADA}
    assert m.cluster.deletes.total() == 0


def test_rf_c1_8_el_observador_ve_el_avance_de_cada_mv_y_un_fallo_suyo_no_rompe_el_borrado():
    m = Mundo()
    m.cluster.agregar_mv(101)
    detalle = m.detallar()
    visto: list[EstadoRollback] = []

    def observador(r):
        visto.append(r.estado)
        raise RuntimeError("el observador falla")

    res = m.servicio.deshacer(
        detalle, {101}, observador, ControlLote(),
        forzar_apagado=NADA, forzar_desproteccion=NADA, permisos=None,
    )  # fmt: skip
    assert res[0].estado == EstadoRollback.ELIMINADA
    assert EstadoRollback.COMPROBANDO in visto and EstadoRollback.ELIMINADA in visto


def test_rf_c1_8_el_borrado_con_hilos_no_envia_dos_delete_a_la_misma_mv():
    m = Mundo(("pve1", "pve2"))
    for i, vmid in enumerate(range(100, 140)):
        m.cluster.agregar_mv(vmid, nodo=("pve1", "pve2")[i % 2])
    detalle = m.detallar()
    _borrar(m, detalle, _todas(detalle))
    assert set(m.cluster.deletes.values()) == {1}


# --- RF-C1.8 paso 5: concurrencia de los DELETE -------------------------------------------------


def test_rf_c1_8_a_lo_sumo_un_delete_a_la_vez_por_nodo_y_cuatro_nodos_en_paralelo():
    import re
    import threading
    from collections import Counter

    nodos = tuple(f"pve{i}" for i in range(1, 7))
    m = Mundo(nodos)
    for i, nodo in enumerate(nodos):
        for k in range(3):
            m.cluster.agregar_mv(100 + i * 10 + k, nodo=nodo)
    detalle = m.detallar()
    cerrojo = threading.Lock()
    activos: Counter[str] = Counter()
    max_por_nodo = 0
    max_nodos = 0
    juntos = threading.Event()

    def medir(ll):
        nonlocal max_por_nodo, max_nodos
        nodo = re.search(r"/nodes/([^/]+)/", ll.ruta).group(1)
        with cerrojo:
            activos[nodo] += 1
            max_por_nodo = max(max_por_nodo, activos[nodo])
            max_nodos = max(max_nodos, sum(1 for v in activos.values() if v))
            if max_nodos >= 5:
                juntos.set()
        juntos.wait(0.01)
        with cerrojo:
            activos[nodo] -= 1
        from .apoyo_lote import NORMAL

        return NORMAL

    m.cluster.regla("DELETE", r"/qemu/\d+$", medir)
    resultados = _borrar(m, detalle, _todas(detalle))
    assert len(resultados) == 18 and m.cluster.deletes.total() == 18
    assert max_por_nodo == 1
    assert 1 < max_nodos <= 4
