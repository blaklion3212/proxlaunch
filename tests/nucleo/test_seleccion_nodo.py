"""P-07 / CA-13.5: nodo «Automático»."""

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos import Inventario, Nodo, Topologia, Version
from proxlaunch.nucleo.seleccion_nodo import MotivoNodo, elegir_nodo

from .conftest import storage


def _inventario(nodos, storages):
    return Inventario(
        version=Version("9.2", 9, 2, 0),
        topologia=Topologia(True, "lab", tuple(nodos)),
        proximo_vmid=100,
        storages=storages,
        bridges={},
        errores_por_nodo={},
    )


def _img(libre_gib, **kw):
    return (storage("s", "lvm", "images", libre_gib, **kw),)


def test_elige_el_nodo_con_mas_memoria_libre():
    inv = _inventario(
        [Nodo("a", True, 4096, 4), Nodo("b", True, 16384, 8)],
        {"a": _img(100), "b": _img(100)},
    )
    assert elegir_nodo(inv, 32) == ("b", MotivoNodo.MAS_MEMORIA_LIBRE)


def test_empate_de_memoria_se_resuelve_por_espacio_libre():
    inv = _inventario(
        [Nodo("a", True, 8192, 4), Nodo("b", True, 8192, 4)],
        {"a": _img(100), "b": _img(300)},
    )
    assert elegir_nodo(inv, 32) == ("b", MotivoNodo.DESEMPATE_ESPACIO_LIBRE)


def test_nodo_sin_conexion_nunca_se_elige():
    inv = _inventario(
        [Nodo("a", False, 99999, 64), Nodo("b", True, 1024, 2)],
        {"a": _img(1000), "b": _img(100)},
    )
    assert elegir_nodo(inv, 32) == ("b", MotivoNodo.UNICO_CANDIDATO)


def test_nodo_sin_espacio_suficiente_se_descarta_aunque_tenga_mas_memoria():
    inv = _inventario(
        [Nodo("a", True, 99999, 64), Nodo("b", True, 1024, 2)],
        {"a": _img(10), "b": _img(100)},
    )
    assert elegir_nodo(inv, 32) == ("b", MotivoNodo.UNICO_CANDIDATO)


def test_espacio_justo_es_suficiente():
    inv = _inventario([Nodo("a", True, 1024, 2)], {"a": _img(32)})
    assert elegir_nodo(inv, 32) == ("a", MotivoNodo.UNICO_CANDIDATO)


@pytest.mark.parametrize(
    "stor",
    [
        pytest.param((storage("s", "lvm", "images", 500, activo=False),), id="storage-inactivo"),
        pytest.param((storage("s", "dir", "iso,backup", 500),), id="storage-sin-images"),
        pytest.param((), id="sin-storages"),
    ],
)
def test_storage_no_apto_no_cuenta_como_espacio(stor):
    inv = _inventario([Nodo("a", True, 1024, 2)], {"a": stor})
    with pytest.raises(ErrorProxLaunch) as e:
        elegir_nodo(inv, 10)
    assert e.value.codigo == CodigoError.SIN_ESPACIO


def test_ningun_nodo_en_linea_lanza_nodo_no_disponible():
    inv = _inventario([Nodo("a", False, None, None)], {"a": _img(100)})
    with pytest.raises(ErrorProxLaunch) as e:
        elegir_nodo(inv, 10)
    assert e.value.codigo == CodigoError.NODO_NO_DISPONIBLE


def test_ningun_nodo_con_espacio_suficiente_lanza_sin_espacio():
    inv = _inventario(
        [Nodo("a", True, 1024, 2), Nodo("b", True, 2048, 2)], {"a": _img(10), "b": _img(20)}
    )
    with pytest.raises(ErrorProxLaunch) as e:
        elegir_nodo(inv, 50)
    assert e.value.codigo == CodigoError.SIN_ESPACIO


def test_el_resultado_es_determinista_con_empate_total():
    inv = _inventario(
        [Nodo("b", True, 8192, 4), Nodo("a", True, 8192, 4)],
        {"a": _img(100), "b": _img(100)},
    )
    assert {elegir_nodo(inv, 10)[0] for _ in range(5)} == {elegir_nodo(inv, 10)[0]}
