"""Espacio acumulado del lote y storages local/compartido/thin (RF-L06, RF-L07, RF-L08).

Pruebas sobre funciones puras (``construir_plan``, ``evaluar_espacio``, ``capacidad_maxima``):
no hay red ni reloj.
"""

import pytest

from proxlaunch.nucleo.lote.constantes import FACTOR_THIN_MAX, TAM_EFIDISK_MIB
from proxlaunch.nucleo.lote.modelos import (
    COMPARTIDO,
    ClavePresupuesto,
    ModoDestino,
    PoliticaThin,
    Severidad,
    UsoStorage,
)
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.lote.presupuesto import (
    capacidad_maxima,
    evaluar_espacio,
    libre_de_clave,
    pedido_vm,
)
from proxlaunch.nucleo.modelos import Disco, Firmware, InterfazRed

from .apoyo_lote import (
    GIB,
    MIB,
    definicion,
    inventario,
    nodo,
    plantilla,
    storage,
)

VERSION = (9, 2)


def _plan(d, inv, **kw):
    n = d.cantidad
    return construir_plan(
        d,
        inv,
        list(range(100, 100 + n)),
        [],
        id_lote="abcd1234",
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
        **kw,
    )


def _inv_un_nodo(libre_gib, tipo="dir", **kw):
    return inventario(
        (nodo("pve1", 64),),
        storages={"pve1": (storage("datos", tipo, libre_gib),)},
        **kw,
    )


def _def_un_nodo(cantidad, disco_gib=32, **kw):
    return definicion(
        cantidad,
        modo=ModoDestino.UN_NODO,
        nodos=("pve1",),
        plantilla_vm=plantilla(discos=[Disco("datos", disco_gib)]),
        **kw,
    )


def _reglas(plan, regla):
    return [p for p in plan.problemas if p.regla == regla]


# --- RF-L07: espacio acumulado (V-L09) ----------------------------------------------------------


def test_ca_l07_1_cinco_maquinas_de_32_gib_no_caben_en_150_no_thin():
    plan = _plan(_def_un_nodo(5), _inv_un_nodo(150))
    (v_l09,) = _reglas(plan, "V-L09")
    assert v_l09.severidad == Severidad.ERROR
    assert plan.bloqueado
    assert v_l09.params["pedido_gib"] == "160"
    assert v_l09.params["libre_gib"] == "150"
    assert v_l09.params["storage"] == "datos"
    assert v_l09.params["n"] == "5"


def test_ca_l07_2_cuatro_maquinas_caben():
    plan = _plan(_def_un_nodo(4), _inv_un_nodo(150))
    assert not _reglas(plan, "V-L09")
    assert not plan.bloqueado


def test_ca_l07_3_el_espacio_exacto_pasa_y_un_gib_menos_no():
    # 3 discos de 50 GiB = 150 GiB justos (la comparación es <=, en bytes).
    assert not _plan(_def_un_nodo(3, 50), _inv_un_nodo(150)).bloqueado
    assert _plan(_def_un_nodo(3, 50), _inv_un_nodo(149)).bloqueado


def test_la_comparacion_es_en_bytes_no_en_gib_redondeados():
    inv = inventario(
        (nodo("pve1"),),
        storages={"pve1": (storage("datos", "dir", 150),)},
    )
    # Un byte menos de lo necesario: bloquea aunque el redondeo a GiB parezca igual.
    from dataclasses import replace

    s = inv.storages["pve1"][0]
    inv.storages["pve1"] = (replace(s, libre_bytes=150 * GIB - 1),)
    assert _plan(_def_un_nodo(3, 50), inv).bloqueado


def test_ca_l07_4_con_dos_discos_cada_storage_se_suma_por_separado():
    d = definicion(
        2,
        modo=ModoDestino.UN_NODO,
        nodos=("pve1",),
        plantilla_vm=plantilla(discos=[Disco("a", 100), Disco("b", 100)]),
    )
    inv = inventario(
        (nodo("pve1"),),
        storages={"pve1": (storage("a", "dir", 250), storage("b", "dir", 150))},
    )
    plan = _plan(d, inv)
    errores = _reglas(plan, "V-L09")
    assert [e.params["storage"] for e in errores] == ["b"]  # a: 200 <= 250; b: 200 > 150


def test_ca_l07_5_el_mensaje_de_un_storage_local_nombra_el_nodo():
    plan = _plan(_def_un_nodo(5), _inv_un_nodo(150))
    (v_l09,) = _reglas(plan, "V-L09")
    assert v_l09.params["ambito"] == "pve1"


def test_ca_l07_5_dos_nodos_con_storage_local_no_suman_su_espacio():
    """Cada nodo tiene 100 GiB propios: 2 MVs de 60 caben (una en cada uno); 3 no."""
    inv = inventario(
        (nodo("pve1", 64), nodo("pve2", 64)),
        storages={"pve1": (storage("datos", "dir", 100),), "pve2": (storage("datos", "dir", 100),)},
    )
    plantilla_60 = plantilla(discos=[Disco("datos", 60)])
    plan2 = _plan(definicion(2, plantilla_vm=plantilla_60), inv)
    assert not plan2.bloqueado
    assert sorted(e.nodo for e in plan2.elementos) == ["pve1", "pve2"]
    assert set(plan2.uso) == {ClavePresupuesto("pve1", "datos"), ClavePresupuesto("pve2", "datos")}

    plan3 = _plan(definicion(3, plantilla_vm=plantilla_60), inv)
    assert plan3.bloqueado  # ningún nodo tiene sitio para la tercera
    assert plan3.capacidad_maxima == 2


def test_ca_l06_1_150_gib_de_un_nodo_no_se_suman_a_los_de_otro():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={
            "pve1": (storage("local-lvm", "lvmthin", 150),),
            "pve2": (storage("local-lvm", "lvmthin", 90),),
        },
    )
    claves = {ClavePresupuesto("pve1", "local-lvm"), ClavePresupuesto("pve2", "local-lvm")}
    assert libre_de_clave(inv, ClavePresupuesto("pve1", "local-lvm")) == (150 * GIB, True)
    assert libre_de_clave(inv, ClavePresupuesto("pve2", "local-lvm")) == (90 * GIB, True)
    plan = _plan(
        definicion(
            2,
            plantilla_vm=plantilla(discos=[Disco("local-lvm", 10)]),
            modo=ModoDestino.NODOS_ELEGIDOS,
            nodos=("pve1", "pve2"),
        ),
        inv,
    )
    assert set(plan.uso) <= claves
    assert {k.ambito for k in plan.uso} <= {"pve1", "pve2"}


def _inv_compartido(libres, tipo="nfs"):
    nodos = tuple(nodo(f"pve{i}", 64) for i in range(1, len(libres) + 1))
    return inventario(
        nodos,
        storages={
            n.nombre: (storage("nfs1", tipo, libre, compartido=True),)
            for n, libre in zip(nodos, libres, strict=True)
        },
    )


def test_ca_l06_2_y_l07_6_el_storage_compartido_se_cuenta_una_vez_como_una_sola_clave():
    inv = _inv_compartido([500, 500, 500])
    d = definicion(5, plantilla_vm=plantilla(discos=[Disco("nfs1", 100)]))
    plan = _plan(d, inv)
    assert not plan.bloqueado  # 5 x 100 = 500 <= 500 una sola vez
    assert list(plan.uso) == [ClavePresupuesto(COMPARTIDO, "nfs1")]
    assert plan.uso[ClavePresupuesto(COMPARTIDO, "nfs1")].pedido_bytes == 500 * GIB
    assert len({e.nodo for e in plan.elementos}) > 1  # y están repartidas en varios nodos


def test_ca_l06_2_seis_no_caben_en_un_compartido_de_500_aunque_cada_nodo_lo_vea():
    inv = _inv_compartido([500, 500, 500])
    d = definicion(6, plantilla_vm=plantilla(discos=[Disco("nfs1", 100)]))
    plan = _plan(d, inv)
    assert plan.bloqueado
    assert plan.capacidad_maxima == 5


def test_ca_l06_7_si_el_libre_compartido_difiere_se_usa_el_menor():
    inv = _inv_compartido([500, 480, 520])
    assert libre_de_clave(inv, ClavePresupuesto(COMPARTIDO, "nfs1"))[0] == 480 * GIB


def test_ca_l06_6_compartido_inactivo_en_un_nodo_cuenta_una_vez_para_los_demas():
    nodos = (nodo("pve1"), nodo("pve2"), nodo("pve3"))
    inv = inventario(
        nodos,
        storages={
            "pve1": (storage("nfs1", "nfs", 500, compartido=True),),
            "pve2": (storage("nfs1", "nfs", 500, compartido=True, activo=False),),
            "pve3": (storage("nfs1", "nfs", 500, compartido=True),),
        },
    )
    d = definicion(4, plantilla_vm=plantilla(discos=[Disco("nfs1", 100)]))
    plan = _plan(d, inv)
    assert not plan.bloqueado
    assert "pve2" not in {e.nodo for e in plan.elementos}  # no es elegible (V-17)
    assert list(plan.uso) == [ClavePresupuesto(COMPARTIDO, "nfs1")]
    assert plan.uso[ClavePresupuesto(COMPARTIDO, "nfs1")].libre_bytes == 500 * GIB


# --- RF-L06: tamaño contable del efidisk ----------------------------------------------------------


def test_ca_l06_8_el_efidisk_de_ovmf_cuenta_4_mib_en_el_presupuesto():
    inv = _inv_un_nodo(500)
    cfg = plantilla(firmware=Firmware.OVMF, discos=[Disco("datos", 32)])
    cfg.nodo = "pve1"
    pedido = pedido_vm(cfg, inv)
    assert pedido == {ClavePresupuesto("pve1", "datos"): 32 * GIB + TAM_EFIDISK_MIB * MIB}
    assert TAM_EFIDISK_MIB == 4


def test_ca_l06_8_el_storage_del_efidisk_participa_en_el_presupuesto_por_separado():
    inv = inventario(
        (nodo("pve1"),),
        storages={"pve1": (storage("datos", "dir", 500), storage("efi", "dir", 1))},
    )
    cfg = plantilla(firmware=Firmware.OVMF, storage_efi="efi", discos=[Disco("datos", 32)])
    cfg.nodo = "pve1"
    pedido = pedido_vm(cfg, inv)
    assert pedido[ClavePresupuesto("pve1", "efi")] == 4 * MIB
    assert pedido[ClavePresupuesto("pve1", "datos")] == 32 * GIB


def test_sin_ovmf_no_se_cuenta_efidisk():
    cfg = plantilla(discos=[Disco("datos", 8)])
    cfg.nodo = "pve1"
    assert pedido_vm(cfg, _inv_un_nodo(500)) == {ClavePresupuesto("pve1", "datos"): 8 * GIB}


# --- RF-L08: thin (V-L10) -------------------------------------------------------------------------


def _uso_thin(pedido_gib, libre_gib=150):
    return {
        ClavePresupuesto("pve1", "local-lvm"): UsoStorage(
            int(pedido_gib * GIB), int(libre_gib * GIB), True
        )
    }


def test_ca_l08_1_thin_con_suma_menor_o_igual_al_libre_no_avisa():
    assert evaluar_espacio(_uso_thin(150), PoliticaThin.CONFIRMAR_CON_TOPE) == []
    assert evaluar_espacio(_uso_thin(10), PoliticaThin.CONFIRMAR_CON_TOPE) == []


def test_ca_l08_2_thin_entre_libre_y_3_veces_es_aviso_confirmable():
    (p,) = evaluar_espacio(_uso_thin(300), PoliticaThin.CONFIRMAR_CON_TOPE)
    assert (p.regla, p.severidad) == ("V-L10", Severidad.AVISO_CONFIRMABLE)
    assert (p.params["pedido_gib"], p.params["libre_gib"]) == ("300", "150")


def test_ca_l08_2_justo_en_el_tope_de_3_veces_sigue_siendo_confirmable():
    (p,) = evaluar_espacio(_uso_thin(150 * FACTOR_THIN_MAX), PoliticaThin.CONFIRMAR_CON_TOPE)
    assert p.severidad == Severidad.AVISO_CONFIRMABLE


def test_ca_l08_3_thin_por_encima_de_3_veces_bloquea():
    (p,) = evaluar_espacio(_uso_thin(480), PoliticaThin.CONFIRMAR_CON_TOPE)
    assert (p.regla, p.severidad) == ("V-L10", Severidad.ERROR)


def test_el_factor_thin_es_3():
    assert FACTOR_THIN_MAX == 3


def test_ca_l08_4_en_un_lote_mixto_cada_storage_usa_su_regla():
    uso = {
        ClavePresupuesto("pve1", "dir1"): UsoStorage(160 * GIB, 150 * GIB, False),
        ClavePresupuesto("pve1", "lvm1"): UsoStorage(300 * GIB, 150 * GIB, True),
    }
    problemas = {
        p.params["storage"]: p for p in evaluar_espacio(uso, PoliticaThin.CONFIRMAR_CON_TOPE)
    }
    assert (problemas["dir1"].regla, problemas["dir1"].severidad) == ("V-L09", Severidad.ERROR)
    assert (problemas["lvm1"].regla, problemas["lvm1"].severidad) == (
        "V-L10",
        Severidad.AVISO_CONFIRMABLE,
    )


@pytest.mark.parametrize(
    ("politica", "pedido", "esperado"),
    [
        (PoliticaThin.BLOQUEAR, 151, Severidad.ERROR),
        (PoliticaThin.BLOQUEAR, 300, Severidad.ERROR),
        (PoliticaThin.ADVERTIR, 151, Severidad.AVISO),
        (PoliticaThin.ADVERTIR, 1500, Severidad.AVISO),  # solo advertir: sin tope
        (PoliticaThin.CONFIRMAR_CON_TOPE, 300, Severidad.AVISO_CONFIRMABLE),
        (PoliticaThin.CONFIRMAR_CON_TOPE, 1500, Severidad.ERROR),
    ],
)
def test_ca_l08_7_las_tres_politicas_solo_cambian_la_severidad(politica, pedido, esperado):
    (p,) = evaluar_espacio(_uso_thin(pedido), politica)
    assert p.severidad == esperado


def test_plan_thin_con_un_nodo_pide_confirmacion():
    """Un lote thin que sobreasigna (2x) sale con aviso confirmable, no bloqueado."""
    plan = _plan(_def_un_nodo(3, 100), _inv_un_nodo(150, "lvmthin"))
    assert not plan.bloqueado
    assert plan.requiere_confirmacion_thin
    assert _reglas(plan, "V-L10")[0].severidad == Severidad.AVISO_CONFIRMABLE


def test_plan_thin_con_mas_de_3_veces_el_libre_queda_bloqueado():
    plan = _plan(_def_un_nodo(5, 100), _inv_un_nodo(150, "lvmthin"))  # 500 > 450
    assert plan.bloqueado
    assert _reglas(plan, "V-L10")[0].severidad == Severidad.ERROR


@pytest.mark.parametrize("tipo", ["lvmthin", "zfspool", "rbd"])
def test_los_tres_backends_thin_se_tratan_como_thin(tipo):
    plan = _plan(_def_un_nodo(3, 100), _inv_un_nodo(150, tipo))
    assert plan.requiere_confirmacion_thin


@pytest.mark.parametrize("tipo", ["dir", "nfs", "lvm", "cifs"])
def test_los_backends_no_thin_bloquean(tipo):
    plan = _plan(_def_un_nodo(3, 100), _inv_un_nodo(150, tipo))
    assert plan.bloqueado
    assert not plan.requiere_confirmacion_thin


def test_ca_l08_2_thin_en_modo_automatico_tambien_sobreasigna_con_confirmacion():
    """Con destino Automático (el predeterminado) el thin debe poder sobreasignar con casilla.

    RF-L08 no limita la política al modo «Un nodo»: en un clúster de un solo nodo elegible,
    300 GiB sobre 150 libres thin es aviso confirmable, no un error de reparto.
    """
    inv = _inv_un_nodo(150, "lvmthin")
    d = definicion(3, plantilla_vm=plantilla(discos=[Disco("datos", 100)]))  # AUTOMATICO
    plan = _plan(d, inv)
    assert plan.requiere_confirmacion_thin
    assert not plan.bloqueado


# --- capacidad_maxima (CA-L07.7) ----------------------------------------------------------------


@pytest.mark.parametrize(("libre", "esperado"), [(150, 4), (160, 5), (31, 0), (32, 1)])
def test_ca_l07_7_capacidad_maxima_cuantas_caben(libre, esperado):
    assert capacidad_maxima(_def_un_nodo(10), _inv_un_nodo(libre)) == esperado


def test_ca_l07_7_el_plan_que_no_cabe_ofrece_reducir_a_n_y_n_es_valido():
    d = _def_un_nodo(10)
    inv = _inv_un_nodo(150)
    plan = _plan(d, inv)
    assert plan.bloqueado
    assert plan.capacidad_maxima == 4
    reducido = _plan(_def_un_nodo(plan.capacidad_maxima), inv)
    assert not reducido.bloqueado  # "Reducir a N" lleva a un plan válido


def test_ca_l07_7_si_ni_una_cabe_la_capacidad_es_cero():
    plan = _plan(_def_un_nodo(3), _inv_un_nodo(10))
    assert plan.bloqueado
    assert plan.capacidad_maxima == 0


def test_capacidad_maxima_nunca_supera_la_cantidad_pedida():
    assert capacidad_maxima(_def_un_nodo(2), _inv_un_nodo(10_000)) == 2


def test_ca_l07_7_capacidad_con_dos_nodos_suma_los_dos_storages_locales():
    inv = inventario(
        (nodo("pve1", 64), nodo("pve2", 64)),
        storages={"pve1": (storage("datos", "dir", 100),), "pve2": (storage("datos", "dir", 70),)},
    )
    d = definicion(10, plantilla_vm=plantilla(discos=[Disco("datos", 30)]))
    assert capacidad_maxima(d, inv) == 5  # 3 en pve1 + 2 en pve2


def test_ca_l07_9_propiedad_un_plan_aceptado_nunca_excede_el_libre_en_no_thin():
    """Para muchas combinaciones: si el plan no está bloqueado, Σ pedido <= libre por clave."""
    revisados = 0
    for libre in (40, 99, 100, 150, 321):
        for disco in (1, 10, 32, 50):
            for cantidad in (1, 2, 5, 9):
                for modo, nodos in (
                    (ModoDestino.UN_NODO, ("pve1",)),
                    (ModoDestino.AUTOMATICO, ()),
                ):
                    inv = inventario(
                        (nodo("pve1", 64), nodo("pve2", 32)),
                        storages={
                            "pve1": (storage("datos", "dir", libre),),
                            "pve2": (storage("datos", "dir", libre // 2),),
                        },
                    )
                    d = definicion(
                        cantidad,
                        modo=modo,
                        nodos=nodos,
                        plantilla_vm=plantilla(discos=[Disco("datos", disco)]),
                    )
                    plan = _plan(d, inv)
                    if plan.bloqueado:
                        continue
                    revisados += 1
                    for uso in plan.uso.values():
                        assert uso.pedido_bytes <= uso.libre_bytes
    assert revisados > 30


def test_redes_de_la_plantilla_no_afectan_al_presupuesto():
    cfg = plantilla(redes=[InterfazRed("vmbr0"), InterfazRed("vmbr0")])
    cfg.nodo = "pve1"
    assert set(pedido_vm(cfg, _inv_un_nodo(100))) == {ClavePresupuesto("pve1", "datos")}


def test_ca_l08_2_thin_con_reparto_por_turnos_tambien_sobreasigna_con_confirmacion():
    """RF-L08 aplica igual con «Por turnos»: no debe convertirse en un error de reparto."""
    from proxlaunch.nucleo.lote.modelos import Algoritmo

    inv = _inv_un_nodo(150, "lvmthin")
    d = definicion(
        3,
        algoritmo=Algoritmo.POR_TURNOS,
        plantilla_vm=plantilla(discos=[Disco("datos", 100)]),
    )
    plan = _plan(d, inv)
    assert plan.requiere_confirmacion_thin
    assert not plan.bloqueado
