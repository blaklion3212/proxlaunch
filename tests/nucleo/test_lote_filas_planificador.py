"""Planificación de un lote por filas (RF-C08, RF-C09; CA-C08.1, CA-C08.3..C08.7, CA-C08.11,
CA-C09.3; V-L01, V-L06, V-L07, V-L11, V-L12, V-M10, V-03, E-L01; INV-L1; §4 y §14.1 de la
arquitectura).

El plan de un lote por filas tiene un elemento por fila, en el orden del archivo, cada uno con su
propia configuración. Los VMIDs explícitos nunca se reasignan; el reparto descuenta lo fijado;
si no cabe, el plan indica QUÉ filas no caben (no hay «Reducir a N»).
"""

import copy
import dataclasses
import random

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote import presupuesto
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, MAX_SALTO_VMID
from proxlaunch.nucleo.lote.filas import sin_filas
from proxlaunch.nucleo.lote.modelos import (
    COMPARTIDO,
    Algoritmo,
    ClavePresupuesto,
    MotivoReparto,
    PoliticaThin,
    Severidad,
)
from proxlaunch.nucleo.lote.planificador import Planificador, construir_plan
from proxlaunch.nucleo.modelos.inventario import Bridge, VMRemota
from proxlaunch.nucleo.modelos.vm import Disco, InterfazRed

from .apoyo_lote import GIB, NORMAL, crear_banco, inventario, nodo, storage
from .apoyo_mvp3 import cfg_hw, definicion_filas, fila, filas_heterogeneas


def _reglas(plan, regla):
    return [p for p in plan.problemas if p.regla == regla]


def _banco(nodos=("pve1",), **kw_inv):
    inv = inventario(tuple(nodo(n) for n in nodos), **kw_inv) if kw_inv else None
    return crear_banco(nodos, inv=inv)


def _sin_definicion(plan):
    return dataclasses.replace(plan, definicion=None)  # type: ignore[arg-type]


# --- CA-C08.1: N elementos, en orden, cada uno con su configuración -------------------------------


def test_el_plan_tiene_un_elemento_por_fila_en_el_orden_del_archivo_con_su_propia_configuracion():
    banco = _banco()
    filas = filas_heterogeneas()
    plan = banco.planificar(definicion_filas(filas))
    assert not plan.bloqueado, plan.problemas
    assert [e.indice for e in plan.elementos] == [0, 1, 2, 3]
    assert [e.nombre for e in plan.elementos] == ["pg-01", "pg-02", "pg-03", "pg-04"]
    assert [e.vmid for e in plan.elementos] == [100, 101, 102, 103]
    assert [(e.cfg.cores, e.cfg.memoria_mib) for e in plan.elementos] == [
        (1, 1024),
        (4, 8192),
        (2, 4096),
        (8, 16384),
    ]
    assert [[d.tamano_gib for d in e.cfg.discos] for e in plan.elementos] == [
        [8],
        [64, 16],
        [32],
        [128],
    ]
    assert all(
        e.cfg.nombre == e.nombre and e.cfg.vmid == e.vmid and e.cfg.nodo == e.nodo
        for e in plan.elementos
    )


def test_las_configuraciones_del_plan_son_copias_y_la_definicion_no_se_modifica():
    banco = _banco()
    d = definicion_filas([fila("a-01", etiquetas=("propia",)), fila("a-02")])
    original = copy.deepcopy(d)
    plan = banco.planificar(d)
    assert d == original
    assert plan.elementos[0].cfg is not d.filas[0].cfg
    plan.elementos[0].cfg.discos[0].tamano_gib = 999
    assert d.filas[0].cfg.discos[0].tamano_gib == 32


def test_vmid_nombre_nodo_y_etiquetas_de_la_configuracion_de_la_fila_se_ignoran():
    """La fila trae ``cfg.vmid/nombre/nodo`` de relleno: los fija el plan."""
    banco = _banco(("pve1", "pve2"))
    f = fila("el-nombre-bueno")
    cfg_sucia = dataclasses.replace(f.cfg, vmid=555, nombre="IGNORADO", nodo="pveX")
    d = definicion_filas([dataclasses.replace(f, cfg=cfg_sucia, vmid=None)])
    plan = banco.planificar(d)
    (e,) = plan.elementos
    assert (e.nombre, e.vmid) == ("el-nombre-bueno", 100) and e.nodo in {"pve1", "pve2"}
    assert (e.cfg.nombre, e.cfg.vmid, e.cfg.nodo) == ("el-nombre-bueno", 100, e.nodo)


def test_las_etiquetas_del_lote_se_anaden_a_las_de_la_fila_y_se_omiten_si_no_se_etiqueta():
    banco = _banco()
    plan = banco.planificar(definicion_filas([fila("a", etiquetas=("propia",)), fila("b")]))
    assert plan.elementos[0].cfg.etiquetas == ("propia", ETIQUETA_APP, "lote-abcd1234")
    assert plan.elementos[1].cfg.etiquetas == (ETIQUETA_APP, "lote-abcd1234")
    sin = _banco().planificar(
        definicion_filas([fila("a", etiquetas=("propia",)), fila("b")], etiquetar=False)
    )
    assert sin.elementos[0].cfg.etiquetas == ("propia",) and sin.elementos[1].cfg.etiquetas == ()


def test_la_plantilla_informativa_no_influye_en_ningun_calculo():
    """§13: plan con una plantilla absurda = plan con una sensata (INV: ``plantilla`` no se lee)."""
    filas = filas_heterogeneas()
    sensata = _banco(("pve1", "pve2")).planificar(definicion_filas(filas))
    absurda_cfg = cfg_hw(
        cores=999,
        sockets=77,
        memoria_mib=10**9,
        discos=[Disco("no-existe", 10**6)],
        redes=[InterfazRed("br-fantasma")],
        nombre="ABSURDA",
        nodo="nodo-fantasma",
        vmid=1,
    )
    absurda = _banco(("pve1", "pve2")).planificar(
        definicion_filas(filas, plantilla_base=absurda_cfg)
    )
    assert not sensata.bloqueado
    assert _sin_definicion(absurda) == _sin_definicion(sensata)


def test_planificar_es_determinista_y_no_comparte_estado_entre_llamadas():
    d = definicion_filas([fila("a", vmid=150), fila("b"), fila("c", nodo="pve2")])
    assert _sin_definicion(_banco(("pve1", "pve2")).planificar(d)) == _sin_definicion(
        _banco(("pve1", "pve2")).planificar(d)
    )


def test_un_lote_de_100_filas_distintas_se_planifica_completo():
    filas = [
        fila(
            f"m-{i:03d}",
            cores=1 + i % 4,
            memoria_mib=256 * (1 + i % 5),
            discos=[Disco("datos", 1 + i % 3)],
        )
        for i in range(100)
    ]
    plan = _banco(("pve1", "pve2", "pve3")).planificar(definicion_filas(filas))
    assert not plan.bloqueado and len(plan.elementos) == 100
    assert [e.vmid for e in plan.elementos] == list(range(100, 200))
    assert len({e.nodo for e in plan.elementos}) == 3


# --- CA-C08.3: VMIDs ------------------------------------------------------------------------------


def test_un_vmid_explicito_libre_se_conserva_y_los_automaticos_lo_saltan_sin_contarlo_como_saltado():  # noqa: E501
    banco = _banco()
    plan = banco.planificar(
        definicion_filas([fila("a"), fila("b", vmid=101), fila("c"), fila("d")], vmid_inicial=100)
    )
    assert [e.vmid for e in plan.elementos] == [100, 101, 102, 103]
    assert plan.vmids_saltados == ()
    consultados = {
        int(c.params["vmid"])
        for c in banco.cluster.llamadas_a("GET", r"nextid")
        if c.params and "vmid" in c.params
    }
    assert consultados == {100, 101, 102, 103}
    assert (
        sum(
            1
            for c in banco.cluster.llamadas_a("GET", r"nextid")
            if c.params and int(c.params.get("vmid", 0)) == 101
        )
        == 1
    )  # una sola vez


def test_los_vmids_automaticos_saltan_los_ocupados_del_servidor_y_avisan():
    banco = _banco()
    banco.cluster.ocupados.update({100, 102})
    plan = banco.planificar(
        definicion_filas([fila("a"), fila("b", vmid=101), fila("c"), fila("d")], vmid_inicial=100)
    )
    assert [e.vmid for e in plan.elementos] == [103, 101, 104, 105]
    assert plan.vmids_saltados == (
        100,
        102,
    )  # los ocupados del servidor; el 101 explícito no cuenta


def test_vmids_automaticos_exactos_con_ocupados_y_un_explicito_en_medio():
    banco = _banco()
    banco.cluster.ocupados.add(100)
    plan = banco.planificar(
        definicion_filas([fila("a"), fila("b", vmid=102), fila("c"), fila("d")], vmid_inicial=100)
    )
    assert [e.vmid for e in plan.elementos] == [101, 102, 103, 104]
    assert plan.vmids_saltados == (100,)


def test_si_todas_las_filas_traen_vmid_no_se_reserva_nada():
    banco = _banco()
    plan = banco.planificar(definicion_filas([fila("a", vmid=300), fila("b", vmid=200)]))
    assert [e.vmid for e in plan.elementos] == [300, 200] and plan.vmids_saltados == ()
    consultados = {int(c.params["vmid"]) for c in banco.cluster.llamadas_a("GET", r"nextid")}
    assert consultados == {200, 300}  # solo los explícitos


def test_un_vmid_explicito_ocupado_es_error_de_esa_fila_y_nunca_se_reasigna():
    """CA-C08.3 / CA-C09.3: «El número 105 ya lo usa otra máquina»."""
    banco = _banco()
    banco.cluster.ocupados.add(105)
    plan = banco.planificar(
        definicion_filas([fila("a"), fila("b", vmid=105), fila("c")], vmid_inicial=100)
    )
    (p,) = _reglas(plan, "V-03")
    assert (p.severidad, p.indice, p.campo, p.params) == (
        Severidad.ERROR,
        1,
        "vmid",
        {"vmid": "105"},
    )
    assert plan.bloqueado
    assert [e.vmid for e in plan.elementos] == [100, 105, 101]  # el 105 sigue siendo el de la fila
    assert banco.cluster.solo_lecturas and not banco.cluster.posts


def test_varios_vmids_explicitos_ocupados_se_marcan_cada_uno_en_su_fila():
    banco = _banco()
    banco.cluster.ocupados.update({150, 160})
    plan = banco.planificar(
        definicion_filas([fila("a", vmid=150), fila("b", vmid=155), fila("c", vmid=160)])
    )
    assert sorted((p.indice, p.params["vmid"]) for p in _reglas(plan, "V-03")) == [
        (0, "150"),
        (2, "160"),
    ]


def test_la_accion_asignar_automaticamente_resuelve_el_vmid_ocupado():
    """CA-C09.3: ``reemplazar_fila(…, vmid=None)`` y se vuelve a planificar."""
    from proxlaunch.nucleo.lote.filas import reemplazar_fila

    banco = _banco()
    banco.cluster.ocupados.add(105)
    d = definicion_filas([fila("a", vmid=105), fila("b")], vmid_inicial=100)
    assert banco.planificar(d).bloqueado
    d2 = reemplazar_fila(d, 0, dataclasses.replace(d.filas[0], vmid=None))
    plan = banco.planificar(d2)
    assert not plan.bloqueado and [e.vmid for e in plan.elementos] == [100, 101]


def test_vmids_explicitos_repetidos_no_consultan_al_servidor():
    """INV-L1: dos MVs con el mismo VMID nunca llegan a planificarse."""
    banco = _banco()
    plan = banco.planificar(definicion_filas([fila("a", vmid=150), fila("b", vmid=150)]))
    assert plan.bloqueado and plan.elementos == () and len(_reglas(plan, "V-M10")) == 2
    assert banco.cluster.llamadas == []


def test_un_vmid_explicito_fuera_de_rango_es_v_02_sin_consultar_al_servidor():
    banco = _banco()
    plan = banco.planificar(definicion_filas([fila("a", vmid=99)]))
    assert _reglas(plan, "V-02") and banco.cluster.llamadas == []


@pytest.mark.parametrize(
    "filas",
    [
        [fila("a"), fila("A")],  # nombres repetidos sin distinguir mayúsculas
        [fila("a"), fila("")],  # nombre vacío
        [fila("a", vmid=150), fila("b", vmid=150)],
    ],
)
def test_los_errores_de_la_definicion_no_consultan_al_servidor(filas):
    banco = _banco()
    plan = banco.planificar(definicion_filas(filas))
    assert plan.bloqueado and plan.elementos == () and banco.cluster.llamadas == []


def test_cantidad_distinta_de_las_filas_es_v_l01_sin_consultar_al_servidor():
    banco = _banco()
    plan = banco.planificar(
        dataclasses.replace(definicion_filas([fila("a"), fila("b")]), cantidad=5)
    )
    assert _reglas(plan, "V-L01") and banco.cluster.llamadas == []


def test_reservar_vmids_con_excluir_no_consulta_ni_cuenta_como_saltados_los_excluidos():
    banco = _banco()
    banco.cluster.ocupados.add(100)
    libres, saltados = Planificador(banco.sesion, banco.reloj).reservar_vmids(
        100, 3, excluir=frozenset({101, 102})
    )
    assert (libres, saltados) == ([103, 104, 105], [100])
    consultados = {int(c.params["vmid"]) for c in banco.cluster.llamadas_a("GET", r"nextid")}
    assert consultados == {100, 103, 104, 105}


def test_reservar_vmids_con_excluir_respeta_la_ventana_maxima():
    banco = _banco()
    excluir = frozenset(range(100, 100 + MAX_SALTO_VMID))
    with pytest.raises(ErrorProxLaunch) as exc:
        Planificador(banco.sesion, banco.reloj).reservar_vmids(100, 1, excluir=excluir)
    assert exc.value.codigo == CodigoError.LOTE_VMIDS_INSUFICIENTES


def test_comprobar_vmids_devuelve_libre_u_ocupado_de_cada_uno_solo_con_lecturas():
    banco = _banco()
    banco.cluster.ocupados.update({150})
    p = Planificador(banco.sesion, banco.reloj)
    assert p.comprobar_vmids([150, 151, 150, 152]) == {150: False, 151: True, 152: True}
    assert p.comprobar_vmids([]) == {}
    assert banco.cluster.solo_lecturas
    assert sum(1 for c in banco.cluster.llamadas_a("GET", r"nextid")) == 3  # los repetidos, una vez


def test_un_fallo_de_red_al_comprobar_los_vmids_aborta_sin_plan_parcial():
    banco = _banco()
    banco.cluster.regla(
        "GET",
        r"^/cluster/nextid$",
        ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "x"}),
    )
    with pytest.raises(ErrorProxLaunch) as exc:
        banco.planificar(definicion_filas([fila("a", vmid=150), fila("b")]))
    assert exc.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert not banco.cluster.posts


def test_un_vmid_explicito_nunca_se_da_por_libre_sin_confirmarlo():
    banco = _banco()
    banco.cluster.regla("GET", r"^/cluster/nextid$", lambda ll: NORMAL)
    plan = banco.planificar(definicion_filas([fila("a", vmid=777)]))
    assert any(
        int((c.params or {}).get("vmid", 0)) == 777
        for c in banco.cluster.llamadas_a("GET", r"nextid")
    )
    assert plan.elementos[0].vmid == 777


def test_construir_plan_con_vmids_repetidos_es_value_error():
    """Defensa de INV-L1 (arquitectura §14.1)."""
    inv = inventario((nodo("pve1"),))
    with pytest.raises(ValueError):
        construir_plan(
            definicion_filas([fila("a"), fila("b")]), inv, [100, 100], [], id_lote="abcd1234", ahora=0.0,  # noqa: E501
            version_validacion=(9, 2), vms_visibles=None,
        )  # fmt: skip


def test_construir_plan_con_un_numero_incorrecto_de_vmids_es_value_error():
    inv = inventario((nodo("pve1"),))
    with pytest.raises(ValueError):
        construir_plan(
            definicion_filas([fila("a"), fila("b")]), inv, [100], [], id_lote="abcd1234", ahora=0.0,
            version_validacion=(9, 2), vms_visibles=None,
        )  # fmt: skip


def test_construir_plan_por_filas_es_pura_y_no_necesita_servidor():
    inv = inventario((nodo("pve1"), nodo("pve2")))
    d = definicion_filas([fila("a"), fila("b", nodo="pve2")])
    p1 = construir_plan(
        d, inv, [100, 101], [], id_lote="x", ahora=1.0, version_validacion=(9, 2), vms_visibles=None
    )
    p2 = construir_plan(
        d, inv, [100, 101], [], id_lote="x", ahora=1.0, version_validacion=(9, 2), vms_visibles=None
    )
    assert p1 == p2 and [e.nodo for e in p1.elementos][1] == "pve2"


# --- CA-C08.4: reparto ----------------------------------------------------------------------------


def _inv_dos_nodos(mem1=64, mem2=64, libre1=500, libre2=500):
    return inventario(
        (nodo("pve1", mem1), nodo("pve2", mem2)),
        storages={
            "pve1": (storage("datos", libre_gib=libre1),),
            "pve2": (storage("datos", libre_gib=libre2),),
        },
    )


def test_una_fila_con_nodo_fijo_va_a_ese_nodo():
    banco = crear_banco(("pve1", "pve2"), inv=_inv_dos_nodos())
    plan = banco.planificar(
        definicion_filas([fila("a", nodo="pve2"), fila("b", nodo="pve2"), fila("c", nodo="pve1")])
    )
    assert [e.nodo for e in plan.elementos] == ["pve2", "pve2", "pve1"]
    assert plan.reparto == {"pve1": (1, "elegido_por_usuario"), "pve2": (2, "elegido_por_usuario")}


def test_lo_asignado_a_nodos_fijos_se_descuenta_de_la_memoria_antes_de_repartir_las_demas():
    """CA-C08.4: sin la fila fija, la automática iría a pve1 (más memoria libre)."""
    inv = _inv_dos_nodos(mem1=10, mem2=9)
    solo_auto = crear_banco(("pve1", "pve2"), inv=inv).planificar(
        definicion_filas([fila("auto", memoria_mib=1024)])
    )
    assert solo_auto.elementos[0].nodo == "pve1"
    con_fija = crear_banco(("pve1", "pve2"), inv=inv).planificar(
        definicion_filas(
            [fila("fija", nodo="pve1", memoria_mib=8 * 1024), fila("auto", memoria_mib=1024)]
        )
    )
    assert [e.nodo for e in con_fija.elementos] == ["pve1", "pve2"]
    assert (
        con_fija.reparto["pve1"] == (1, "elegido_por_usuario") and con_fija.reparto["pve2"][0] == 1
    )


def test_lo_asignado_a_nodos_fijos_se_descuenta_del_espacio_antes_de_repartir_las_demas():
    inv = _inv_dos_nodos(libre1=100, libre2=100)
    banco = crear_banco(("pve1", "pve2"), inv=inv)
    plan = banco.planificar(definicion_filas([
        fila("fija", nodo="pve1", discos=[Disco("datos", 90)]),
        fila("auto", discos=[Disco("datos", 40)]),
    ]))  # fmt: skip
    assert [e.nodo for e in plan.elementos] == ["pve1", "pve2"]  # en pve1 solo quedan 10 GiB


def test_por_turnos_las_filas_fijas_no_consumen_turno():
    banco = crear_banco(("pve1", "pve2"), inv=_inv_dos_nodos())
    d = definicion_filas(
        [fila("a"), fila("b", nodo="pve2"), fila("c"), fila("d"), fila("e")],
        algoritmo=Algoritmo.POR_TURNOS,
    )
    plan = banco.planificar(d)
    assert [e.nodo for e in plan.elementos] == [
        "pve1",
        "pve2",
        "pve2",
        "pve1",
        "pve2",
    ]  # autos: pve1, pve2, pve1, pve2
    assert all(e.cfg.nodo == e.nodo for e in plan.elementos)


def test_equilibrado_reparte_las_automaticas_por_memoria_restante():
    banco = crear_banco(("pve1", "pve2"), inv=_inv_dos_nodos(mem1=32, mem2=32))
    plan = banco.planificar(definicion_filas([fila(f"m-{i}", memoria_mib=8192) for i in range(4)]))
    assert sorted(e.nodo for e in plan.elementos) == ["pve1", "pve1", "pve2", "pve2"]
    assert plan.reparto["pve1"][1] == MotivoReparto.MAS_MEMORIA.value


def test_la_elegibilidad_se_evalua_por_fila_con_su_propio_storage_y_bridge():
    """CA-C08.4: la fila con «rapido» (solo en pve1) o «vmbr9» (solo en pve2) no puede ir a otro."""
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={"pve1": (storage("datos"), storage("rapido")), "pve2": (storage("datos"),)},
        bridges={
            "pve1": (Bridge("vmbr0", "bridge", False),),
            "pve2": (Bridge("vmbr0", "bridge", False), Bridge("vmbr9", "bridge", False)),
        },
    )
    banco = crear_banco(("pve1", "pve2"), inv=inv)
    filas = [
        fila("a", discos=[Disco("rapido", 5)]),
        fila("b", redes=[InterfazRed("vmbr9")]),
        fila("c"),
        fila("d", discos=[Disco("rapido", 5)]),
    ]
    plan = banco.planificar(definicion_filas(filas))
    assert not plan.bloqueado, plan.problemas
    assert plan.elementos[0].nodo == "pve1" and plan.elementos[3].nodo == "pve1"
    assert plan.elementos[1].nodo == "pve2"


def test_una_fila_fija_a_un_nodo_donde_no_es_elegible_es_error_de_esa_fila():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={"pve1": (storage("datos"), storage("rapido")), "pve2": (storage("datos"),)},
    )
    banco = crear_banco(("pve1", "pve2"), inv=inv)
    plan = banco.planificar(
        definicion_filas([fila("a"), fila("b", nodo="pve2", discos=[Disco("rapido", 5)])])
    )
    v = [p for p in _reglas(plan, "V-L11") if p.severidad == Severidad.ERROR]
    assert [(p.indice, p.params["nodo"], p.params["motivo"], p.params["storage"]) for p in v] == [
        (1, "pve2", "storage", "rapido")
    ]
    assert plan.bloqueado and plan.elementos == ()  # el plan sale bloqueado y sin elementos


@pytest.mark.parametrize(("fijo", "motivo"), [("fantasma", "no_existe"), ("pve3", "sin_conexion")])
def test_una_fila_fija_a_un_nodo_inexistente_o_sin_conexion_es_v_l11_con_el_indice(fijo, motivo):
    inv = inventario((nodo("pve1"), nodo("pve2"), nodo("pve3", en_linea=False)))
    plan = crear_banco(("pve1", "pve2", "pve3"), inv=inv).planificar(
        definicion_filas([fila("a"), fila("b", nodo=fijo), fila("c", nodo="pve1")])
    )
    (p,) = [p for p in _reglas(plan, "V-L11") if p.severidad == Severidad.ERROR]
    assert (p.indice, p.params["nodo"], p.params["motivo"], p.severidad) == (
        1,
        fijo,
        motivo,
        Severidad.ERROR,
    )
    assert plan.bloqueado and plan.elementos == ()


def test_e_l01_se_informa_por_fila_no_en_agregado():
    banco = _banco()
    plan = banco.planificar(
        definicion_filas(
            [
                fila("a"),
                fila("b", discos=[Disco("no-existe", 5)]),
                fila("c", redes=[InterfazRed("br-9")]),
                fila("d"),
            ]
        )
    )
    e_l01 = _reglas(plan, "E-L01")
    assert sorted(p.indice for p in e_l01) == [1, 2]
    assert all(p.params["motivo"] == "sin_nodo_elegible" for p in e_l01)
    assert plan.bloqueado and plan.elementos == ()


def test_un_nodo_sin_conexion_no_recibe_filas_automaticas():
    inv = inventario((nodo("pve1"), nodo("pve2", en_linea=False), nodo("pve3")))
    plan = crear_banco(("pve1", "pve2", "pve3"), inv=inv).planificar(
        definicion_filas([fila(f"m-{i}") for i in range(6)])
    )
    assert {e.nodo for e in plan.elementos} == {"pve1", "pve3"}


def test_en_por_filas_el_destino_siempre_es_automatico_aunque_se_pida_otro():
    from proxlaunch.nucleo.lote.modelos import Destino, ModoDestino

    d = dataclasses.replace(
        definicion_filas([fila("a")]), destino=Destino(ModoDestino.UN_NODO, ("pve1",))
    )
    banco = _banco()
    plan = banco.planificar(d)
    assert _reglas(plan, "V-L13") and plan.bloqueado and banco.cluster.llamadas == []


# --- CA-C08.5: espacio heterogéneo por clave y compartido -----------------------------------------


def test_el_presupuesto_suma_los_discos_de_cada_fila_por_clave():
    banco = _banco(("pve1",))
    plan = banco.planificar(
        definicion_filas(
            [
                fila("a", discos=[Disco("datos", 10)]),
                fila("b", discos=[Disco("datos", 20), Disco("datos", 5)]),
                fila("c", discos=[Disco("datos", 1)]),
            ]
        )
    )
    uso = plan.uso[ClavePresupuesto("pve1", "datos")]
    assert uso.pedido_bytes == 36 * GIB and uso.libre_bytes == 500 * GIB and uso.thin is False


def test_cada_fila_aporta_su_nodo_a_la_clave_del_storage_local():
    banco = crear_banco(("pve1", "pve2"), inv=_inv_dos_nodos())
    plan = banco.planificar(
        definicion_filas(
            [
                fila("a", nodo="pve1", discos=[Disco("datos", 10)]),
                fila("b", nodo="pve2", discos=[Disco("datos", 7)]),
                fila("c", nodo="pve2", discos=[Disco("datos", 3)]),
            ]
        )
    )
    assert plan.uso[ClavePresupuesto("pve1", "datos")].pedido_bytes == 10 * GIB
    assert plan.uso[ClavePresupuesto("pve2", "datos")].pedido_bytes == 10 * GIB


def test_un_storage_compartido_suma_las_filas_de_todos_los_nodos_en_una_sola_clave():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={n: (storage("nfs", "nfs", 100, compartido=True),) for n in ("pve1", "pve2")},
    )
    banco = crear_banco(("pve1", "pve2"), inv=inv)
    plan = banco.planificar(
        definicion_filas(
            [
                fila("a", nodo="pve1", discos=[Disco("nfs", 40)]),
                fila("b", nodo="pve2", discos=[Disco("nfs", 50)]),
                fila("c", nodo="pve2", discos=[Disco("nfs", 30)]),
            ]
        )
    )
    assert list(plan.uso) == [ClavePresupuesto(COMPARTIDO, "nfs")]
    assert plan.uso[ClavePresupuesto(COMPARTIDO, "nfs")].pedido_bytes == 120 * GIB
    assert _reglas(plan, "V-L09")  # 120 GiB > 100 GiB libres: el compartido cuenta una sola vez


def test_el_exceso_de_espacio_no_thin_es_error_v_l09():
    plan = _banco(("pve1",), libre_gib=50).planificar(
        definicion_filas(
            [fila("a", discos=[Disco("datos", 30)]), fila("b", discos=[Disco("datos", 30)])]
        )
    )
    (p,) = _reglas(plan, "V-L09")
    assert p.severidad == Severidad.ERROR and plan.bloqueado


@pytest.mark.parametrize(
    ("politica", "gib_pedidos", "regla", "severidad"),
    [
        (PoliticaThin.CONFIRMAR_CON_TOPE, 120, "V-L10", Severidad.AVISO_CONFIRMABLE),  # 1.2 × libre
        (PoliticaThin.CONFIRMAR_CON_TOPE, 301, "V-L10", Severidad.ERROR),  # > 3 × libre
        (PoliticaThin.BLOQUEAR, 120, "V-L10", Severidad.ERROR),
        (PoliticaThin.ADVERTIR, 301, None, None),
    ],
)
def test_la_politica_thin_se_aplica_igual_que_en_m2_con_las_filas_heterogeneas(
    politica, gib_pedidos, regla, severidad
):
    inv = inventario((nodo("pve1"),), storages={"pve1": (storage("lv", "lvmthin", 100),)})
    banco = crear_banco(("pve1",), inv=inv)
    mitad = gib_pedidos // 2
    plan = banco.planificar(
        definicion_filas(
            [
                fila("a", discos=[Disco("lv", mitad)]),
                fila("b", discos=[Disco("lv", gib_pedidos - mitad)]),
            ],
            politica_thin=politica,
        )
    )
    if regla is None:  # ADVERTIR: solo avisos, nunca error ni confirmación
        assert not [
            p
            for p in plan.problemas
            if p.regla in {"V-L09", "V-L10"} and p.severidad != Severidad.AVISO
        ]
        assert not plan.bloqueado and not plan.requiere_confirmacion_thin
        return
    (p,) = _reglas(plan, regla)
    assert p.severidad == severidad


# --- CA-C08.6: filas que no caben -----------------------------------------------------------------


def test_si_no_cabe_el_plan_indica_las_filas_excedentes_y_no_hay_reducir_a_n():
    banco = _banco(("pve1",), libre_gib=100)
    d = definicion_filas(
        [
            fila("a", discos=[Disco("datos", 60)]),
            fila("b", discos=[Disco("datos", 30)]),
            fila("c", discos=[Disco("datos", 50)]),
            fila("d", discos=[Disco("datos", 10)]),
        ]
    )
    plan = banco.planificar(d)
    assert plan.bloqueado and plan.capacidad_maxima is None
    assert plan.filas_excedentes == (2,)  # 60 + 30 + 50 > 100; la d (10) todavía cabe: 100
    assert len(plan.elementos) == 4  # el plan no se reorganiza solo
    assert plan.definicion is d


def test_quitar_las_filas_excedentes_y_replanificar_deja_el_lote_sin_exceso():
    banco = _banco(("pve1",), libre_gib=100)
    d = definicion_filas(
        [
            fila("a", discos=[Disco("datos", 60)]),
            fila("b", discos=[Disco("datos", 30)]),
            fila("c", discos=[Disco("datos", 50)]),
        ]
    )
    plan = banco.planificar(d)
    nueva = sin_filas(d, plan.filas_excedentes)
    plan2 = banco.planificar(nueva)
    assert (
        not plan2.bloqueado
        and plan2.filas_excedentes == ()
        and [e.nombre for e in plan2.elementos] == ["a", "b"]
    )


def test_propiedad_quitar_las_excedentes_siempre_deja_cabiendo_el_resto_con_un_solo_storage():
    rng = random.Random(20260514)
    for caso in range(60):
        libre = rng.randint(20, 200)
        politica = rng.choice(list(PoliticaThin))
        tipo = rng.choice(["dir", "lvmthin"])
        inv = inventario((nodo("pve1"),), storages={"pve1": (storage("s", tipo, libre),)})
        banco = crear_banco(("pve1",), inv=inv)
        tamanos = [rng.randint(1, 80) for _ in range(rng.randint(2, 9))]
        d = definicion_filas(
            [fila(f"m-{i}", discos=[Disco("s", t)]) for i, t in enumerate(tamanos)],
            politica_thin=politica,
        )
        plan = banco.planificar(d)
        exceden = set(plan.filas_excedentes)
        hubo_error_de_espacio = any(
            p.regla in {"V-L09", "V-L10"} and p.severidad == Severidad.ERROR for p in plan.problemas
        )
        assert bool(exceden) == hubo_error_de_espacio, (caso, tamanos, libre, tipo, politica)
        if exceden:
            resto = sin_filas(d, exceden)
            plan2 = banco.planificar(resto)
            assert not [
                p
                for p in plan2.problemas
                if p.regla in {"V-L09", "V-L10"} and p.severidad == Severidad.ERROR
            ], (caso, tamanos, libre, tipo, politica, exceden)
            assert not plan2.filas_excedentes


def test_filas_que_exceden_recorre_en_orden_y_no_suma_las_que_exceden():
    inv = inventario((nodo("pve1"),), storages={"pve1": (storage("s", "dir", 100),)})
    banco = crear_banco(("pve1",), inv=inv)
    plan = banco.planificar(
        definicion_filas(
            [
                fila("a", discos=[Disco("s", 70)]),
                fila("b", discos=[Disco("s", 50)]),
                fila("c", discos=[Disco("s", 30)]),
                fila("d", discos=[Disco("s", 1)]),
            ]
        )
    )
    assert presupuesto.filas_que_exceden(plan.elementos, inv, PoliticaThin.CONFIRMAR_CON_TOPE) == (
        1,
        3,
    )
    # «b» (50) no cabe tras «a»; «c» (30) sí (100); «d» ya no (101).


def test_filas_que_exceden_con_thin_y_las_tres_politicas():
    inv = inventario((nodo("pve1"),), storages={"pve1": (storage("lv", "lvmthin", 100),)})
    banco = crear_banco(("pve1",), inv=inv)
    plan = banco.planificar(
        definicion_filas(
            [
                fila("a", discos=[Disco("lv", 200)]),
                fila("b", discos=[Disco("lv", 90)]),
                fila("c", discos=[Disco("lv", 20)]),
            ],
            politica_thin=PoliticaThin.ADVERTIR,
        )
    )
    el = plan.elementos
    assert presupuesto.filas_que_exceden(el, inv, PoliticaThin.ADVERTIR) == ()
    assert presupuesto.filas_que_exceden(el, inv, PoliticaThin.CONFIRMAR_CON_TOPE) == (
        2,
    )  # 200 + 90 = 290 ≤ 300; +20 = 310
    assert presupuesto.filas_que_exceden(el, inv, PoliticaThin.BLOQUEAR) == (
        0,
        2,
    )  # «b» (90) cabe; «c» no


def test_por_turnos_sin_espacio_en_storages_no_thin_da_e_l01_por_fila_y_las_excedentes():
    inv = _inv_dos_nodos(libre1=50, libre2=50)
    banco = crear_banco(("pve1", "pve2"), inv=inv)
    d = definicion_filas(
        [fila(f"m-{i}", discos=[Disco("datos", 30)]) for i in range(4)],
        algoritmo=Algoritmo.POR_TURNOS,
    )
    plan = banco.planificar(d)
    sin_espacio = [p for p in _reglas(plan, "E-L01") if p.params.get("motivo") == "sin_espacio"]
    assert sorted(p.indice for p in sin_espacio) == [2, 3] and plan.filas_excedentes == (2, 3)
    assert plan.elementos == () and plan.bloqueado


# --- CA-C08.11: una fila = POST de M1 -------------------------------------------------------------


def test_el_post_de_un_lote_de_una_fila_es_el_de_una_maquina_de_m1_mas_las_etiquetas():
    from proxlaunch.nucleo.constructor_peticion import construir_parametros
    from proxlaunch.nucleo.lote.motor import ControlLote
    from proxlaunch.nucleo.modelos.vm import ConfiguracionVM

    cfg = cfg_hw(
        cores=3,
        memoria_mib=3072,
        discos=[Disco("datos", 20)],
        redes=[InterfazRed("vmbr0", vlan=30)],
    )
    banco = _banco()
    plan = banco.planificar(
        definicion_filas([dataclasses.replace(fila("unica"), cfg=cfg)], etiquetar=False)
    )
    banco.ejecutar(plan, ControlLote())
    m1 = ConfiguracionVM(
        vmid=100,
        nombre="unica",
        nodo="pve1",
        cores=3,
        memoria_mib=3072,
        discos=[Disco("datos", 20)],
        redes=[InterfazRed("vmbr0", vlan=30)],
    )
    assert banco.cluster.cuerpos_post[100] == construir_parametros(m1, banco.inv)


def test_con_etiquetas_el_post_solo_se_diferencia_en_tags():
    from proxlaunch.nucleo.constructor_peticion import construir_parametros
    from proxlaunch.nucleo.lote.motor import ControlLote

    banco = _banco()
    plan = banco.planificar(definicion_filas([fila("unica")]))
    banco.ejecutar(plan, ControlLote())
    cuerpo = dict(banco.cluster.cuerpos_post[100])
    tags = cuerpo.pop("tags")
    assert set(tags.split(";")) == {ETIQUETA_APP, "lote-abcd1234"}
    esperado = construir_parametros(
        dataclasses.replace(plan.elementos[0].cfg, etiquetas=()), banco.inv
    )
    assert cuerpo == esperado


# --- V-L12, M1 por elemento, V-L06, permisos ------------------------------------------------------


def test_v_l12_suma_la_memoria_de_cada_fila_por_nodo():
    inv = inventario((nodo("pve1", 10),))  # 10 GiB libres
    banco = crear_banco(("pve1",), inv=inv)
    ok = banco.planificar(
        definicion_filas([fila("a", memoria_mib=4096), fila("b", memoria_mib=4096)])
    )
    assert not _reglas(ok, "V-L12")
    mal = banco.planificar(
        definicion_filas(
            [fila("a", memoria_mib=4096), fila("b", memoria_mib=4096), fila("c", memoria_mib=4096)]
        )
    )
    (p,) = _reglas(mal, "V-L12")
    assert (
        p.severidad == Severidad.AVISO
        and p.params["pedido_mib"] == "12288"
        and p.params["libre_mib"] == str(10 * 1024)
    )


def test_los_problemas_de_m1_de_cada_fila_conservan_su_indice_y_no_se_agrupan():
    banco = _banco()
    plan = banco.planificar(
        definicion_filas(
            [fila("bien"), fila("mal-1", cores=0), fila("mal nombre"), fila("mal-3", cores=0)]
        )
    )
    v05 = _reglas(plan, "V-05")
    assert sorted(p.indice for p in v05) == [1, 3] and all("elementos" not in p.params for p in v05)
    assert [p.indice for p in _reglas(plan, "V-01")] == [2]
    assert plan.bloqueado


def test_un_nombre_que_ya_existe_en_el_servidor_es_aviso_v_l06_de_esa_fila():
    banco = _banco()
    banco.cluster.visibles_extra.append(
        {"vmid": 900, "name": "Existente", "node": "pve1", "type": "qemu"}
    )
    plan = banco.planificar(definicion_filas([fila("nuevo"), fila("existente")]))
    (p,) = _reglas(plan, "V-L06")
    assert (p.severidad, p.indice, p.params["vmid"]) == (Severidad.AVISO, 1, "900")
    assert not plan.bloqueado


def test_la_falta_de_permiso_vm_allocate_bloquea_la_creacion_como_en_m2():
    banco = _banco()
    banco.cluster.permisos = {"/": {"VM.Audit": 1, "Sys.Audit": 1}}
    plan = banco.planificar(definicion_filas([fila("a")]))
    (p,) = _reglas(plan, "V-L16")
    assert p.severidad == Severidad.ERROR and plan.bloqueado


def test_vms_visibles_se_comparan_sin_distinguir_mayusculas_y_solo_las_de_nombre_igual():
    inv = inventario((nodo("pve1"),))
    d = definicion_filas([fila("web"), fila("db")])
    visibles = [VMRemota(900, "WEB", "pve1", "qemu"), VMRemota(901, "otra", "pve1", "qemu")]
    plan = construir_plan(
        d,
        inv,
        [100, 101],
        [],
        id_lote="x",
        ahora=0.0,
        version_validacion=(9, 2),
        vms_visibles=visibles,
    )
    assert [(p.indice, p.params["vmid"]) for p in _reglas(plan, "V-L06")] == [(0, "900")]
