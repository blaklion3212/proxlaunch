"""Elegibilidad de nodos y reparto del lote (RF-L05, RF-L06): funciones puras y deterministas."""

from dataclasses import replace

import pytest

from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    Destino,
    ModoDestino,
    MotivoReparto,
    Severidad,
)
from proxlaunch.nucleo.lote.planificador import construir_plan, validar_definicion
from proxlaunch.nucleo.lote.reparto import nodos_elegibles, repartir
from proxlaunch.nucleo.modelos import Bridge, Disco, Firmware, InterfazRed
from proxlaunch.nucleo.seleccion_nodo import elegir_nodo

from .apoyo_lote import definicion, inventario, nodo, plantilla, storage

VERSION = (9, 2)


def _plan(d, inv, saltados=()):
    return construir_plan(
        d,
        inv,
        list(range(100, 100 + d.cantidad)),
        list(saltados),
        id_lote="abcd1234",
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )


def _nodos(plan):
    return [e.nodo for e in plan.elementos]


def _reglas(problemas, regla):
    return [p for p in problemas if p.regla == regla]


# --- Equilibrado (CA-L05.2, CA-L05.4) -------------------------------------------------------------


def test_ca_l05_4_reparto_equilibrado_64_32_32_con_seis_maquinas_de_8_gib():
    inv = inventario()  # pve1 64 GiB, pve2 32, pve3 32; mismo storage con espacio de sobra
    plan = _plan(definicion(6), inv)
    assert _nodos(plan) == ["pve1", "pve1", "pve1", "pve1", "pve1", "pve2"]
    assert {n: c for n, (c, _) in plan.reparto.items()} == {"pve1": 5, "pve2": 1}
    assert not plan.bloqueado


def test_ca_l05_4_el_total_por_nodo_nunca_supera_la_capacidad_de_su_storage():
    plan = _plan(definicion(6), inventario(libre_gib=500))
    for clave, uso in plan.uso.items():
        assert uso.pedido_bytes <= uso.libre_bytes, clave


def test_ca_l05_2_equilibrado_es_determinista():
    inv = inventario()
    d = definicion(7)
    assert _nodos(_plan(d, inv)) == _nodos(_plan(d, inv))


def test_ca_l05_2_el_desempate_por_memoria_se_resuelve_por_el_mayor_espacio_libre():
    inv = inventario(
        (nodo("pve1", 32), nodo("pve2", 32)),
        storages={"pve1": (storage("datos", "dir", 100),), "pve2": (storage("datos", "dir", 300),)},
    )
    nodos, _, _ = repartir(definicion(1), inv, 1)
    assert nodos == ["pve2"]


def test_ca_l05_2_el_desempate_final_es_el_nombre_ascendente():
    inv = inventario((nodo("pve2", 32), nodo("pve1", 32)))  # declarados en orden inverso
    nodos, _, _ = repartir(definicion(1), inv, 1)
    assert nodos == ["pve1"]


def test_ca_l05_2_descuenta_la_memoria_ya_asignada_de_cada_nodo():
    """Con 2 nodos de 16 GiB y MVs de 8 GiB el reparto alterna, no llena uno solo."""
    inv = inventario((nodo("pve1", 16), nodo("pve2", 16)))
    nodos, _, _ = repartir(definicion(4), inv, 4)
    assert nodos == ["pve1", "pve2", "pve1", "pve2"]


def test_ca_l05_2_un_nodo_sin_espacio_para_la_siguiente_no_la_recibe():
    inv = inventario(
        (nodo("pve1", 64), nodo("pve2", 16)),
        storages={"pve1": (storage("datos", "dir", 40),), "pve2": (storage("datos", "dir", 500),)},
    )
    # pve1 tiene más memoria pero solo cabe 1 disco de 32 GiB; la 2.ª y siguientes van a pve2.
    nodos, _, problemas = repartir(definicion(3), inv, 3)
    assert nodos == ["pve1", "pve2", "pve2"]
    assert not [p for p in problemas if p.severidad == Severidad.ERROR]


def test_ca_l05_9_el_reparto_informa_cuantas_recibe_cada_nodo_y_el_motivo():
    plan = _plan(definicion(6), inventario())
    assert plan.reparto["pve1"] == (5, MotivoReparto.MAS_MEMORIA.value)
    assert plan.reparto["pve2"][0] == 1


def test_ca_l05_3_con_cantidad_1_automatico_coincide_con_elegir_nodo_de_m1():
    escenarios = [
        inventario(),
        inventario((nodo("pve1", 8), nodo("pve2", 64), nodo("pve3", 16))),
        inventario(
            (nodo("pve1", 32), nodo("pve2", 32)),
            storages={
                "pve1": (storage("datos", "dir", 100),),
                "pve2": (storage("datos", "dir", 400),),
            },
        ),
        inventario((nodo("pve1", None), nodo("pve2", 4))),
    ]
    for inv in escenarios:
        esperado, _ = elegir_nodo(inv, 32)
        nodos, _, _ = repartir(definicion(1), inv, 1)
        assert nodos == [esperado], inv.topologia


def test_ca_l05_6_memoria_desconocida_cuenta_como_la_peor_y_se_avisa():
    inv = inventario((nodo("pve1", None), nodo("pve2", 4)))
    nodos, reparto, problemas = repartir(definicion(2), inv, 2)
    assert nodos[0] == "pve2"  # -1 pierde frente a 4 GiB
    desconocida = _reglas(problemas, "V-L12.desconocida")
    assert len(desconocida) == 1
    assert desconocida[0].severidad == Severidad.AVISO
    assert desconocida[0].params["nodos"] == "pve1"


def test_ca_l05_6_con_toda_la_memoria_desconocida_se_reparte_por_espacio_y_nombre():
    inv = inventario(
        (nodo("pve1", None), nodo("pve2", None)),
        storages={"pve1": (storage("datos", "dir", 100),), "pve2": (storage("datos", "dir", 300),)},
    )
    nodos, reparto, problemas = repartir(definicion(1), inv, 1)
    assert nodos == ["pve2"]
    assert reparto["pve2"][1] == MotivoReparto.MAS_ESPACIO
    assert _reglas(problemas, "V-L12.desconocida")


# --- Por turnos (CA-L05.5) ------------------------------------------------------------------------


def test_ca_l05_5_por_turnos_alterna_en_orden_alfabetico():
    inv = inventario((nodo("pve3"), nodo("pve1"), nodo("pve2")))
    d = definicion(5, algoritmo=Algoritmo.POR_TURNOS)
    nodos, reparto, _ = repartir(d, inv, 5)
    assert nodos == ["pve1", "pve2", "pve3", "pve1", "pve2"]
    assert reparto["pve1"][1] == MotivoReparto.POR_TURNOS


def test_ca_l05_5_por_turnos_con_nodos_elegidos_solo_usa_esos():
    d = definicion(
        4, modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve3", "pve1"), algoritmo=Algoritmo.POR_TURNOS
    )
    nodos, _, _ = repartir(d, inventario(), 4)
    assert nodos == ["pve1", "pve3", "pve1", "pve3"]


def test_ca_l05_5_por_turnos_salta_el_nodo_que_no_puede_alojar_la_maquina():
    inv = inventario(
        (nodo("pve1"), nodo("pve2"), nodo("pve3")),
        storages={
            "pve1": (storage("datos", "dir", 500),),
            "pve2": (storage("datos", "dir", 10),),  # no cabe ni una de 32 GiB
            "pve3": (storage("datos", "dir", 500),),
        },
    )
    d = definicion(4, algoritmo=Algoritmo.POR_TURNOS)
    nodos, _, problemas = repartir(d, inv, 4)
    assert "pve2" not in nodos
    # MV i -> nodo (i mod 3): la 1.ª va a pve2, que no cabe, y se salta a pve3.
    assert nodos == ["pve1", "pve3", "pve3", "pve1"]
    assert not [p for p in problemas if p.severidad == Severidad.ERROR]


def test_ca_l05_5_por_turnos_si_ningun_nodo_puede_falla_ese_elemento_con_e_l01():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={"pve1": (storage("datos", "dir", 40),), "pve2": (storage("datos", "dir", 40),)},
    )
    d = definicion(3, algoritmo=Algoritmo.POR_TURNOS)  # 3 x 32 = 96 > 80; caben 2
    nodos, _, problemas = repartir(d, inv, 3)
    assert nodos == ["pve1", "pve2", ""]
    (e_l01,) = _reglas(problemas, "E-L01")
    assert e_l01.severidad == Severidad.ERROR
    assert e_l01.indice == 2


# --- Destino (CA-L05.1, L05.7, L05.8, V-L13) ------------------------------------------------------


def test_ca_l05_1_un_nodo_envia_todas_a_ese_nodo():
    d = definicion(4, modo=ModoDestino.UN_NODO, nodos=("pve3",))
    plan = _plan(d, inventario())
    assert set(_nodos(plan)) == {"pve3"}
    assert plan.reparto["pve3"][1] == MotivoReparto.ELEGIDO_POR_USUARIO.value


def test_ca_l05_1_un_nodo_sin_espacio_falla_y_no_las_reparte_solas_a_otro():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={"pve1": (storage("datos", "dir", 40),), "pve2": (storage("datos", "dir", 900),)},
    )
    d = definicion(3, modo=ModoDestino.UN_NODO, nodos=("pve1",))  # 96 > 40
    plan = _plan(d, inv)
    assert plan.bloqueado
    assert _reglas(plan.problemas, "V-L09")
    assert "pve2" not in plan.reparto


def test_ca_l05_7_un_nodo_fuera_de_linea_no_recibe_maquinas():
    inv = inventario((nodo("pve1", 8), nodo("pve2", 64, en_linea=False), nodo("pve3", 4)))
    plan = _plan(definicion(6), inv)
    assert "pve2" not in _nodos(plan)  # aunque sea el de más memoria


def test_ca_l05_7_nodo_fuera_de_linea_elegido_a_mano_no_es_elegible():
    inv = inventario((nodo("pve1"), nodo("pve2", en_linea=False)))
    d = definicion(2, modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve1", "pve2"))
    elegibles, motivos = nodos_elegibles(d.plantilla, inv, d.destino)
    assert elegibles == ["pve1"]
    assert motivos["pve2"][0].params["motivo"] == "sin_conexion"


def test_ca_l05_8_nodos_elegidos_vacio_bloquea_con_v_l13():
    d = definicion(2, modo=ModoDestino.NODOS_ELEGIDOS, nodos=())
    assert _reglas(validar_definicion(d, inventario(), VERSION), "V-L13")


def test_v_l13_nodos_elegidos_todos_fuera_de_linea_bloquea():
    inv = inventario((nodo("pve1", en_linea=False), nodo("pve2")))
    d = definicion(2, modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve1",))
    assert _reglas(validar_definicion(d, inv, VERSION), "V-L13")


def test_v_l13_un_nodo_debe_estar_en_linea_y_ser_uno_solo():
    inv = inventario((nodo("pve1", en_linea=False), nodo("pve2")))
    fuera = definicion(2, modo=ModoDestino.UN_NODO, nodos=("pve1",))
    assert _reglas(validar_definicion(fuera, inv, VERSION), "V-L13")
    dos = definicion(2, modo=ModoDestino.UN_NODO, nodos=("pve2", "pve1"))
    assert _reglas(validar_definicion(dos, inv, VERSION), "V-L13")
    ninguno = definicion(2, modo=ModoDestino.UN_NODO, nodos=())
    assert _reglas(validar_definicion(ninguno, inv, VERSION), "V-L13")
    inexistente = definicion(2, modo=ModoDestino.UN_NODO, nodos=("pve9",))
    assert _reglas(validar_definicion(inexistente, inv, VERSION), "V-L13")
    ok = definicion(2, modo=ModoDestino.UN_NODO, nodos=("pve2",))
    assert not _reglas(validar_definicion(ok, inv, VERSION), "V-L13")


# --- Elegibilidad (RF-L06) ------------------------------------------------------------------------


def test_ca_l06_3_nodo_sin_el_storage_de_la_plantilla_no_es_elegible_y_dice_por_que():
    inv = inventario(
        (nodo("pve1"), nodo("pve3")),
        storages={"pve1": (storage("datos", "dir", 500),), "pve3": (storage("otro", "dir", 500),)},
    )
    elegibles, motivos = nodos_elegibles(plantilla(), inv, Destino())
    assert elegibles == ["pve1"]
    (m,) = motivos["pve3"]
    assert m.regla == "V-L11"
    assert (m.params["motivo"], m.params["storage"]) == ("storage", "datos")


@pytest.mark.parametrize(
    ("storages", "motivo"),
    [
        ((storage("datos", "dir", 500, activo=False),), "storage"),  # inactivo
        ((storage("datos", "dir", 500, contenido="iso,backup"),), "storage"),  # sin images
    ],
)
def test_ca_l06_3_storage_inactivo_o_sin_images_no_es_apto(storages, motivo):
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={"pve1": (storage("datos", "dir", 500),), "pve2": storages},
    )
    elegibles, motivos = nodos_elegibles(plantilla(), inv, Destino())
    assert elegibles == ["pve1"]
    assert motivos["pve2"][0].params["motivo"] == motivo


def test_ca_l06_4_nodo_sin_el_bridge_de_la_plantilla_no_es_elegible():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        bridges={
            "pve1": (Bridge("vmbr0", "bridge", False),),
            "pve2": (Bridge("vmbr9", "bridge", False),),
        },
    )
    elegibles, motivos = nodos_elegibles(plantilla(), inv, Destino())
    assert elegibles == ["pve1"]
    assert (motivos["pve2"][0].params["motivo"], motivos["pve2"][0].params["bridge"]) == (
        "bridge",
        "vmbr0",
    )


def test_ca_l06_4_una_interfaz_que_no_es_bridge_no_cuenta():
    inv = inventario(
        (nodo("pve1"),),
        bridges={"pve1": (Bridge("vmbr0", "eth", False),)},
    )
    elegibles, _ = nodos_elegibles(plantilla(), inv, Destino())
    assert elegibles == []


def test_ca_l06_8_el_storage_del_efidisk_participa_en_la_elegibilidad():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={
            "pve1": (storage("datos", "dir", 500), storage("efi", "dir", 5)),
            "pve2": (storage("datos", "dir", 500),),  # no tiene "efi"
        },
    )
    cfg = plantilla(firmware=Firmware.OVMF, storage_efi="efi")
    elegibles, motivos = nodos_elegibles(cfg, inv, Destino())
    assert elegibles == ["pve1"]
    assert motivos["pve2"][0].params["motivo"] == "efidisk"


def test_ca_l06_5_ningun_nodo_elegible_da_e_l01_y_no_deja_elementos():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={"pve1": (storage("x", "dir", 500),), "pve2": (storage("y", "dir", 500),)},
    )
    plan = _plan(definicion(3), inv)
    assert plan.bloqueado
    assert plan.elementos == ()
    assert _reglas(plan.problemas, "E-L01")


def test_ca_l06_3_el_motivo_por_nodo_queda_en_el_plan_cuando_otros_si_son_elegibles():
    inv = inventario(
        (nodo("pve1"), nodo("pve3")),
        storages={"pve1": (storage("datos", "dir", 500),), "pve3": (storage("otro", "dir", 500),)},
    )
    plan = _plan(definicion(2), inv)
    assert not plan.bloqueado
    motivos = _reglas(plan.problemas, "V-L11")
    assert [m.params["nodo"] for m in motivos] == ["pve3"]
    assert motivos[0].severidad == Severidad.AVISO  # queda al menos un nodo elegible


def test_nodo_elegido_a_mano_que_no_existe_no_es_elegible():
    d = definicion(1, modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve1", "fantasma"))
    elegibles, motivos = nodos_elegibles(d.plantilla, inventario(), d.destino)
    assert elegibles == ["pve1"]
    assert motivos["fantasma"][0].params["motivo"] == "no_existe"


def test_un_nodo_con_el_storage_pero_otra_plantilla_de_discos_multiples():
    """Cada storage distinto de la plantilla debe existir en el nodo (varios discos)."""
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={
            "pve1": (storage("datos", "dir", 500), storage("rapido", "dir", 500)),
            "pve2": (storage("datos", "dir", 500),),
        },
    )
    cfg = plantilla(discos=[Disco("datos", 8), Disco("rapido", 8)], redes=[InterfazRed("vmbr0")])
    elegibles, _ = nodos_elegibles(cfg, inv, Destino())
    assert elegibles == ["pve1"]


# --- Propiedades de determinismo (RNF-L09) --------------------------------------------------------


def test_rnf_l09_mismo_inventario_y_vmids_dan_el_mismo_plan_sin_depender_del_orden_de_nodos():
    a = inventario((nodo("pve1", 64), nodo("pve2", 32), nodo("pve3", 32)))
    b = inventario((nodo("pve3", 32), nodo("pve1", 64), nodo("pve2", 32)))
    d = definicion(9)
    pa, pb = _plan(d, a), _plan(d, b)
    assert [(e.nombre, e.vmid, e.nodo) for e in pa.elementos] == [
        (e.nombre, e.vmid, e.nodo) for e in pb.elementos
    ]
    assert pa.problemas == pb.problemas
    assert replace(pa, id_lote="x") == replace(pb, id_lote="x")


def test_rnf_l09_el_plan_es_repetible_con_el_mismo_id():
    inv = inventario()
    d = definicion(10)
    assert _plan(d, inv) == _plan(d, inv)
