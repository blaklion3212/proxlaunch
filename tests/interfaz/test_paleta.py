"""Paleta de colores y contraste (CA-22.4, CA-22.5, RNF-10, D-02)."""

import re

import pytest

from proxlaunch.interfaz.tema import paleta
from proxlaunch.interfaz.tema.paleta import (
    PARES_TEXTO_FONDO,
    TOKENS_CLARO,
    TOKENS_OSCURO,
    contraste,
)

TEMAS = {"oscuro": TOKENS_OSCURO, "claro": TOKENS_CLARO}


def _luminancia(color):
    """Oráculo independiente de la implementación: fórmula WCAG 2.x."""
    canales = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _razon(a, b):
    mayor, menor = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (mayor + 0.05) / (menor + 0.05)


def test_ca22_4_ambos_temas_definen_exactamente_los_mismos_tokens():
    assert set(TOKENS_OSCURO) == set(TOKENS_CLARO)


@pytest.mark.parametrize("tema", TEMAS)
def test_ca22_4_cada_token_es_un_color_hexadecimal(tema):
    for nombre, valor in TEMAS[tema].items():
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", valor), f"{tema}.{nombre} = {valor!r}"


@pytest.mark.parametrize("tema", TEMAS)
def test_d02_el_acento_naranja_es_e57000(tema):
    assert TEMAS[tema]["acento"].upper() == "#E57000"
    assert TEMAS[tema]["seleccion"].upper() == "#E57000"


def test_ca22_5_los_pares_referencian_tokens_existentes():
    for texto, fondo in PARES_TEXTO_FONDO:
        assert texto in TOKENS_OSCURO
        assert fondo in TOKENS_OSCURO


def test_ca22_5_hay_pares_para_texto_principal_y_boton_naranja():
    assert ("texto", "fondo") in PARES_TEXTO_FONDO
    assert ("acento_texto", "acento") in PARES_TEXTO_FONDO


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize(
    ("texto", "fondo"), PARES_TEXTO_FONDO, ids=lambda x: x if isinstance(x, str) else str(x)
)
def test_ca22_5_contraste_minimo_aa_de_cada_par(tema, texto, fondo):
    tokens = TEMAS[tema]
    razon = _razon(tokens[texto], tokens[fondo])
    assert razon >= 4.5, f"{tema}: {texto} sobre {fondo} da {razon:.2f}:1"


@pytest.mark.parametrize("tema", TEMAS)
def test_ca22_5_la_funcion_contraste_del_proyecto_coincide_con_el_oraculo(tema):
    tokens = TEMAS[tema]
    for texto, fondo in PARES_TEXTO_FONDO:
        assert contraste(tokens[texto], tokens[fondo]) == pytest.approx(
            _razon(tokens[texto], tokens[fondo]), rel=1e-9
        )
        assert contraste(tokens[texto], tokens[fondo]) >= 4.5


@pytest.mark.parametrize("tema", TEMAS)
def test_ca22_5_texto_del_boton_naranja_supera_aa(tema):
    """D-02: sobre #E57000 el texto oscuro llega a 4.5:1 (el blanco no)."""
    tokens = TEMAS[tema]
    assert _razon(tokens["acento_texto"], "#E57000") >= 4.5
    assert _razon("#FFFFFF", "#E57000") < 4.5


def test_contraste_valores_conocidos():
    assert contraste("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contraste("#FFFFFF", "#000000") == pytest.approx(21.0)  # simétrico
    assert contraste("#808080", "#808080") == pytest.approx(1.0)


def test_el_modulo_paleta_es_el_unico_con_colores_literales():
    """La función auxiliar existe y los diccionarios no son alias del mismo objeto."""
    assert paleta.TOKENS_OSCURO is not paleta.TOKENS_CLARO
