"""Reparto y presupuesto por filas (arquitectura §4.4, §4.5, Anexo A; CA-C08.4, CA-C08.5).

``repartir_filas`` es pura: asigna un nodo a cada fila (las fijas primero, luego las automáticas con
lo ya descontado) y ``uso_de_filas``/``uso_de_nodos`` suman los discos de cada fila por clave.
"""

import dataclasses

from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    ClavePresupuesto,
    Destino,
    FilaLote,
    ModoDestino,
    MotivoReparto,
    Severidad,
)
from proxlaunch.nucleo.lote.presupuesto import capacidad_maxima, uso_de_filas, uso_de_nodos
from proxlaunch.nucleo.lote.reparto import repartir, repartir_filas
from proxlaunch.nucleo.modelos.vm import Disco

from .apoyo_lote import GIB, definicion, inventario, nodo, plantilla, storage
from .apoyo_mvp3 import fila

AUTO = Destino()


def _inv(**kw):
    return inventario((nodo("pve1", 64), nodo("pve2", 32), nodo("pve3", 32)), **kw)


def test_sin_filas_no_hay_nodos_ni_problemas():
    assert repartir_filas([], AUTO, _inv(), por_filas=True) == ([], {}, [])
    assert repartir_filas([], AUTO, _inv()) == ([], {}, [])


def test_filas_iguales_dan_lo_mismo_que_repartir_del_homogeneo():
    """Equivalencia (arquitectura §4.6): ``repartir`` delega en ``repartir_filas``."""
    inv = _inv()
    d = definicion(7, algoritmo=Algoritmo.POR_TURNOS)
    filas = [FilaLote("", d.plantilla)] * 7
    assert repartir(d, inv, 7) == repartir_filas(filas, d.destino, inv)
    d2 = definicion(5)
    assert repartir(d2, inv, 5) == repartir_filas([FilaLote("", d2.plantilla)] * 5, d2.destino, inv)


def test_un_nodo_solo_aplica_al_homogeneo_y_en_por_filas_se_trata_como_automatico():
    inv = _inv()
    filas = [fila("a"), fila("b")]
    destino = Destino(ModoDestino.UN_NODO, ("pve2",))
    nodos_h, _, _ = repartir_filas(filas, destino, inv)
    assert nodos_h == ["pve2", "pve2"]
    nodos_f, _, _ = repartir_filas(filas, destino, inv, por_filas=True)
    assert set(nodos_f) <= {"pve1", "pve2", "pve3"} and nodos_f != ["pve2", "pve2"]


def test_los_problemas_de_por_filas_llevan_el_indice_de_la_fila():
    inv = _inv()
    filas = [fila("a"), fila("b", nodo="fantasma"), fila("c", discos=[Disco("no-existe", 1)])]
    nodos, _, problemas = repartir_filas(filas, AUTO, inv, por_filas=True)
    assert nodos[1] == "" and nodos[2] == ""
    errores = [(p.regla, p.indice) for p in problemas if p.severidad == Severidad.ERROR]
    assert ("V-L11", 1) in errores and ("E-L01", 2) in errores


def test_el_desempate_del_equilibrado_es_por_memoria_restante_espacio_inicial_y_nombre():
    inv = inventario(
        (nodo("pve2", 32), nodo("pve1", 32)),
        storages={
            "pve1": (storage("datos", libre_gib=100),),
            "pve2": (storage("datos", libre_gib=300),),
        },
    )
    # Misma memoria: gana el de mayor espacio libre inicial del storage (pve2).
    nodos, _, _ = repartir_filas([fila("a", discos=[Disco("datos", 1)])], AUTO, inv, por_filas=True)
    assert nodos == ["pve2"]
    # Misma memoria y espacio: gana el nombre ascendente.
    inv2 = inventario((nodo("pve2", 32), nodo("pve1", 32)))
    assert repartir_filas([fila("a")], AUTO, inv2, por_filas=True)[0] == ["pve1"]


def test_memoria_desconocida_avisa_y_se_cuenta_como_la_menor():
    inv = inventario((nodo("pve1", None), nodo("pve2", 8)))
    nodos, _, problemas = repartir_filas([fila("a")], AUTO, inv, por_filas=True)
    assert nodos == ["pve2"]
    assert [p.regla for p in problemas if p.regla == "V-L12.desconocida"] == ["V-L12.desconocida"]


def test_el_motivo_del_reparto_es_elegido_si_todas_las_del_nodo_eran_fijas():
    inv = _inv()
    filas = [fila("a", nodo="pve1"), fila("b", nodo="pve1"), fila("c")]
    nodos, reparto, _ = repartir_filas(filas, AUTO, inv, por_filas=True)
    assert reparto["pve1"][1] in {MotivoReparto.ELEGIDO_POR_USUARIO, MotivoReparto.MAS_MEMORIA}
    solo_fijas = repartir_filas(
        [fila("a", nodo="pve1"), fila("b", nodo="pve2")], AUTO, inv, por_filas=True
    )[1]
    assert solo_fijas == {
        "pve1": (1, MotivoReparto.ELEGIDO_POR_USUARIO),
        "pve2": (1, MotivoReparto.ELEGIDO_POR_USUARIO),
    }
    assert nodos[0] == "pve1" and nodos[1] == "pve1"


def test_un_unico_nodo_elegible_da_el_motivo_unico_nodo():
    inv = inventario((nodo("pve1"),), es_cluster=False)
    _, reparto, _ = repartir_filas([fila("a"), fila("b")], AUTO, inv, por_filas=True)
    assert reparto == {"pve1": (2, MotivoReparto.UNICO_NODO)}


def test_el_reparto_no_modifica_las_filas_ni_el_inventario():
    inv = _inv()
    filas = [fila("a", nodo="pve1"), fila("b")]
    antes = [dataclasses.replace(f, cfg=dataclasses.replace(f.cfg)) for f in filas]
    repartir_filas(filas, AUTO, inv, por_filas=True)
    assert [f.nodo for f in filas] == ["pve1", None] and [f.cfg for f in filas] == [
        f.cfg for f in antes
    ]


# --- Presupuesto -------------------------------------------------------------------------------------------  # noqa: E501


def test_uso_de_filas_suma_los_discos_de_cada_fila_en_su_nodo_y_omite_las_sin_nodo():
    inv = _inv()
    filas = [
        fila("a", discos=[Disco("datos", 10)]),
        fila("b", discos=[Disco("datos", 5), Disco("datos", 1)]),
        fila("c"),
    ]
    uso = uso_de_filas(filas, ["pve1", "pve2", ""], inv)
    assert uso[ClavePresupuesto("pve1", "datos")].pedido_bytes == 10 * GIB
    assert uso[ClavePresupuesto("pve2", "datos")].pedido_bytes == 6 * GIB
    assert len(uso) == 2


def test_uso_de_nodos_es_uso_de_filas_con_la_misma_plantilla():
    inv = _inv()
    p = plantilla(discos=[Disco("datos", 7)])
    nodos = ["pve1", "pve1", "pve2"]
    assert uso_de_nodos(p, nodos, inv) == uso_de_filas([FilaLote("", p)] * 3, nodos, inv)


def test_capacidad_maxima_sigue_siendo_la_del_homogeneo():
    inv = inventario((nodo("pve1"),), storages={"pve1": (storage("datos", "dir", 100),)})
    d = definicion(10, plantilla_vm=plantilla(discos=[Disco("datos", 30)]))
    assert capacidad_maxima(d, inv) == 3


def test_filas_distintas_se_evaluan_con_su_propia_firma_de_recursos():
    """Dos firmas (storage distinto) en el mismo lote: cada fila solo ve los nodos que le sirven."""
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={"pve1": (storage("datos"), storage("solo1")), "pve2": (storage("datos"),)},
    )
    nodos, _, problemas = repartir_filas(
        [fila("a", discos=[Disco("solo1", 1)]), fila("b"), fila("c", discos=[Disco("solo1", 1)])],
        AUTO,
        inv,
        por_filas=True,
    )
    assert nodos[0] == "pve1" and nodos[2] == "pve1"
    assert not [p for p in problemas if p.severidad == Severidad.ERROR]
