"""RF-09: detección de versión y tabla de capacidades (CA-09.x, S-4, RF-26)."""

import pytest

from proxlaunch.nucleo.capacidades import (
    TABLA,
    VERSION_MINIMA,
    Funcion,
    capacidades_para,
    interpretar_version,
)
from proxlaunch.nucleo.modelos import Version

# --- interpretar_version ------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "mayor", "menor", "parche"),
    [
        pytest.param("8.2.4", 8, 2, 4, id="CA-09.1-8.2.4"),
        pytest.param("9.2", 9, 2, 0, id="CA-09.6-9.2"),
        pytest.param("8.0", 8, 0, 0, id="CA-09.6-8.0"),
        pytest.param("7.4-17", 7, 4, 17, id="CA-09.2-7.4-17"),
        pytest.param("10.0", 10, 0, 0, id="CA-09.3-10.0"),
    ],
)
def test_interpretar_version_reconocida(texto, mayor, menor, parche):
    version, advertencia = interpretar_version(texto)
    assert (version.mayor, version.menor, version.parche) == (mayor, menor, parche)
    assert version.texto == texto
    assert advertencia is False


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("", id="CA-09.5-vacio"),
        pytest.param("abc", id="CA-09.5-texto"),
        pytest.param("x.y", id="CA-09.5-no-numerico"),
        pytest.param(None, id="CA-09.5-None"),
        pytest.param("   ", id="CA-09.5-espacios"),
    ],
)
def test_ca09_5_formato_inesperado_usa_la_capacidad_minima(texto):
    version, advertencia = interpretar_version(texto)
    assert advertencia is True
    assert (version.mayor, version.menor) == VERSION_MINIMA
    assert capacidades_para(version, None).es_soportada()


def test_la_version_minima_es_8_0():
    assert VERSION_MINIMA == (8, 0)


# --- soporte mínimo -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "soportada"),
    [
        pytest.param("7.4-17", False, id="CA-09.2-7.4-bloquea"),
        pytest.param("7.99", False, id="CA-09.2-7.99-bloquea"),
        pytest.param("8.0", True, id="CA-09.2-8.0-permite"),
        pytest.param("8.2.4", True, id="CA-09.2-8.2.4-permite"),
        pytest.param("10.0", True, id="CA-09.3-version-mayor-permite"),
    ],
)
def test_es_soportada(texto, soportada):
    version, _ = interpretar_version(texto)
    assert capacidades_para(version, None).es_soportada() is soportada


# --- tabla (CA-09.6) ----------------------------------------------------------------

VERSIONES_CA_09_6 = [(8, 0), (8, 1), (8, 4), (9, 0), (9, 2)]


def test_ca09_6_la_tabla_cubre_todas_las_funciones():
    assert set(TABLA) == set(Funcion)


@pytest.mark.parametrize("funcion", list(Funcion), ids=lambda f: f"CA-09.6-{f.value}")
@pytest.mark.parametrize("version", VERSIONES_CA_09_6, ids=lambda v: f"v{v[0]}.{v[1]}")
def test_ca09_6_tabla_recorrida_para_cada_version(funcion, version):
    mayor, menor = version
    caps = capacidades_para(Version(f"{mayor}.{menor}", mayor, menor, 0), None)
    assert caps.tiene(funcion) is (version >= caps.requisito(funcion))


@pytest.mark.parametrize(
    ("version", "esperado"),
    [
        pytest.param((8, 0), False, id="CA-09.4-8.0-oculta"),
        pytest.param((8, 1), False, id="CA-09.4-8.1-oculta"),
        pytest.param((8, 2), True, id="CA-09.4-8.2-disponible"),
        pytest.param((8, 4), True, id="CA-09.6-8.4"),
        pytest.param((9, 0), True, id="CA-09.6-9.0"),
        pytest.param((9, 2), True, id="CA-09.6-9.2"),
    ],
)
def test_ca09_4_funcion_desde_8_2(version, esperado):
    """CA-09.4: la función de ejemplo 'desde 8.2' aparece o no según la versión."""
    caps = capacidades_para(Version("x", version[0], version[1], 0), None)
    assert caps.requisito(Funcion.IMPORTAR_DISCO) == (8, 2)
    assert caps.tiene(Funcion.IMPORTAR_DISCO) is esperado


def test_s4_version_mayor_que_la_ultima_conocida_tiene_todas_las_funciones():
    caps = capacidades_para(Version("10.0", 10, 0, 0), None)
    assert all(caps.tiene(f) for f in Funcion)


def test_la_comparacion_es_por_tupla_no_por_menor_aislado():
    """9.0 tiene menor 0 pero es posterior a 8.2: no se comparan solo los menores."""
    assert capacidades_para(Version("9.0", 9, 0, 0), None).tiene(Funcion.IMPORTAR_DISCO)


# --- versión forzada (RF-26) --------------------------------------------------------


def test_ca26_2_version_forzada_manda_sobre_la_detectada():
    """CA-26.2."""
    caps = capacidades_para(Version("9.2", 9, 2, 0), (8, 0))
    assert caps.version == (8, 0)
    assert caps.forzada is True
    assert caps.tiene(Funcion.IMPORTAR_DISCO) is False


def test_sin_forzar_la_version_es_la_detectada():
    caps = capacidades_para(Version("8.4.1", 8, 4, 1), None)
    assert caps.version == (8, 4)
    assert caps.forzada is False
