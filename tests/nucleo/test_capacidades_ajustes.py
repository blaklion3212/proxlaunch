"""Lista de versiones conocidas (RF-09, RF-26)."""

from proxlaunch.nucleo.capacidades import (
    ULTIMA_VERSION_CONOCIDA,
    VERSION_MINIMA,
    VERSIONES_CONOCIDAS,
)


def test_versiones_conocidas_son_exactamente_las_especificadas():
    assert VERSIONES_CONOCIDAS == (
        (8, 4),
        (9, 0),
        (9, 1),
        (9, 2),
    )


def test_versiones_conocidas_estan_ordenadas_y_sin_repetidos():
    assert list(VERSIONES_CONOCIDAS) == sorted(set(VERSIONES_CONOCIDAS))


def test_el_ultimo_elemento_es_la_ultima_version_conocida():
    assert VERSIONES_CONOCIDAS[-1] == ULTIMA_VERSION_CONOCIDA == (9, 2)


def test_el_primer_elemento_es_la_version_minima():
    assert VERSIONES_CONOCIDAS[0] == VERSION_MINIMA
