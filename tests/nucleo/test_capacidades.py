"""RF-09: detección de versión y tabla de capacidades (CA-09.x, S-4, RF-26)."""

import pytest

from proxlaunch.nucleo.capacidades import (
    TABLA,
    VERSION_MINIMA,
    Funcion,
    capacidades_para,
    es_rama_8,
    interpretar_version,
)
from proxlaunch.nucleo.modelos import Version

# --- interpretar_version ------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "mayor", "menor", "parche"),
    [
        pytest.param("8.2.4", 8, 2, 4, id="CA-09.1-8.2.4"),
        pytest.param("9.2", 9, 2, 0, id="CA-09.6-9.2"),
        pytest.param("8.4", 8, 4, 0, id="CA-09.6-8.4"),
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


def test_la_version_minima_es_8_4():
    """CA-D2.1: la mínima sube a 8.4 en 0.9.0."""
    assert VERSION_MINIMA == (8, 4)


# --- soporte mínimo -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "soportada"),
    [
        pytest.param("7.4-17", False, id="CA-09.2-7.4-bloquea"),
        pytest.param("7.99", False, id="CA-09.2-7.99-bloquea"),
        pytest.param("8.0", False, id="CA-D2.1-8.0-bloquea"),
        pytest.param("8.3.5", False, id="CA-D2.1-8.3-bloquea"),
        pytest.param("8.4", True, id="CA-D2.1-8.4-permite"),
        pytest.param("8.4.1", True, id="CA-D2.1-8.4.1-permite"),
        pytest.param("10.0", True, id="CA-09.3-version-mayor-permite"),
    ],
)
def test_es_soportada(texto, soportada):
    version, _ = interpretar_version(texto)
    assert capacidades_para(version, None).es_soportada() is soportada


# --- tabla (CA-09.6) ----------------------------------------------------------------

VERSIONES_CA_09_6 = [(8, 0), (8, 1), (8, 4), (9, 0), (9, 1), (9, 2)]


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
        pytest.param((8, 4), False, id="CA-09.4-8.4-oculta"),
        pytest.param((9, 0), False, id="CA-09.4-9.0-oculta"),
        pytest.param((9, 1), True, id="CA-09.6-9.1"),
        pytest.param((9, 2), True, id="CA-09.6-9.2"),
    ],
)
def test_ca09_4_funcion_desde_9_1(version, esperado):
    """CA-09.4: una función de 9.1 (``CLAVES_MS_2023``) se oculta antes de esa versión."""
    caps = capacidades_para(Version("x", version[0], version[1], 0), None)
    assert caps.requisito(Funcion.CLAVES_MS_2023) == (9, 1)
    assert caps.tiene(Funcion.CLAVES_MS_2023) is esperado


@pytest.mark.parametrize(
    ("funcion", "minima"),
    [
        (Funcion.MAPEO_DRIVER_KEEP, (9, 1)),
        (Funcion.CPU_PERSONALIZADA_POR_MAPPING, (9, 2)),
        (Funcion.CAPACIDADES_POR_ARCH, (9, 2)),
        (Funcion.HOST_ARCH_EN_RESOURCES, (9, 2)),
        (Funcion.NODO_ARM64, (9, 2)),
    ],
)
def test_ca_d0_3_las_funciones_nuevas_de_la_fase_d_tienen_su_version(funcion, minima):
    """RF-D0.3 / RF-D2.4: banderas nuevas con su versión mínima."""
    assert TABLA[funcion] == minima
    assert capacidades_para(Version("x", *minima, 0), None).tiene(funcion)
    anterior = (minima[0], minima[1] - 1) if minima[1] else (minima[0] - 1, 9)
    assert not capacidades_para(Version("x", *anterior, 0), None).tiene(funcion)


@pytest.mark.parametrize(
    "nombre",
    [
        "DESCARGAR_URL",
        "IMPORTAR_DISCO",
        "SUBIR_IMAGEN_DISCO",
        "TPM_CLON_COMPLETO",
        "ASISTENTE_PLANTILLA_IMAGEN",
        "SDN_INCLUIDO",
    ],
)
def test_ca_d2_4_las_banderas_retiradas_ya_no_existen(nombre):
    """RF-D2.4 / DT-D3: con la mínima 8.4 estas seis banderas siempre serían verdaderas."""
    assert not hasattr(Funcion, nombre)


def test_es_rama_8_distingue_la_rama():
    assert es_rama_8((8, 4)) and not es_rama_8((9, 0)) and not es_rama_8((7, 4))


def test_s4_version_mayor_que_la_ultima_conocida_tiene_todas_las_funciones():
    caps = capacidades_para(Version("10.0", 10, 0, 0), None)
    assert all(caps.tiene(f) for f in Funcion)


def test_la_comparacion_es_por_tupla_no_por_menor_aislado():
    """9.0 tiene menor 0 pero es posterior a 8.4: no se comparan solo los menores."""
    assert capacidades_para(Version("9.0", 9, 0, 0), None).tiene(Funcion.CLOUDINIT)
    assert not capacidades_para(Version("9.0", 9, 0, 0), None).tiene(Funcion.CLAVES_MS_2023)


# --- versión forzada (RF-26) --------------------------------------------------------


def test_ca26_2_version_forzada_manda_sobre_la_detectada():
    """CA-26.2."""
    caps = capacidades_para(Version("9.2", 9, 2, 0), (8, 4))
    assert caps.version == (8, 4)
    assert caps.forzada is True
    assert caps.tiene(Funcion.CLAVES_MS_2023) is False


def test_sin_forzar_la_version_es_la_detectada():
    caps = capacidades_para(Version("8.4.1", 8, 4, 1), None)
    assert caps.version == (8, 4)
    assert caps.forzada is False
