"""Nombres del lote (RF-L02, V-L02..V-L05, V-L01 y RNF-L08): funciones puras.

Derivadas de docs/requisitos/mvp2.md; no dependen de cómo se implementan por dentro.
"""

import re
from pathlib import Path

import pytest

from proxlaunch.nucleo.lote import constantes
from proxlaunch.nucleo.lote.constantes import MAX_LOTE
from proxlaunch.nucleo.lote.modelos import PatronNombres, Severidad
from proxlaunch.nucleo.lote.nombres import generar_nombres, validar_patron
from proxlaunch.nucleo.lote.planificador import validar_definicion

from .apoyo_lote import definicion, inventario


def _reglas(problemas):
    return [p.regla for p in problemas]


def _de(problemas, regla):
    return [p for p in problemas if p.regla == regla]


# --- Generación de nombres (CA-L02.1 a CA-L02.3) ------------------------------------------------


def test_ca_l02_1_tres_nombres_con_relleno_de_dos():
    assert generar_nombres(PatronNombres("web", "-", 1, 2), 3) == ["web-01", "web-02", "web-03"]


def test_ca_l02_2_el_relleno_efectivo_crece_para_todos_los_nombres():
    nombres = generar_nombres(PatronNombres("web", "-", 1, 2), 120)
    assert nombres[0] == "web-001"
    assert nombres[-1] == "web-120"
    assert len({len(n) for n in nombres}) == 1  # misma longitud siempre


@pytest.mark.parametrize(
    ("cantidad", "relleno", "primero", "ultimo"),
    [
        (9, 1, "web-1", "web-9"),  # 9 cabe en 1 dígito
        (10, 1, "web-01", "web-10"),  # cruza 9 -> 10: el relleno efectivo pasa a 2
        (99, 2, "web-01", "web-99"),
        (100, 2, "web-001", "web-100"),  # cruza 99 -> 100: pasa a 3
    ],
)
def test_caso_limite_relleno_efectivo_al_cruzar_decenas_y_centenas(
    cantidad, relleno, primero, ultimo
):
    nombres = generar_nombres(PatronNombres("web", "-", 1, relleno), cantidad)
    assert (nombres[0], nombres[-1]) == (primero, ultimo)
    assert len({len(n) for n in nombres}) == 1


def test_ca_l02_3_inicio_10_sin_relleno_ni_separador():
    assert generar_nombres(PatronNombres("web", "", 10, 0), 3) == ["web10", "web11", "web12"]


def test_el_relleno_efectivo_usa_el_mayor_numero_no_la_cantidad():
    # Inicio 98 y 3 nombres: llegan a 100 (3 dígitos) aunque la cantidad sea 3.
    nombres = generar_nombres(PatronNombres("a", "-", 98, 2), 3)
    assert nombres == ["a-098", "a-099", "a-100"]


@pytest.mark.parametrize("cantidad", [0, -1])
def test_sin_cantidad_positiva_no_hay_nombres(cantidad):
    assert generar_nombres(PatronNombres("web"), cantidad) == []


def test_ca_l02_5_nombres_distintos_y_de_igual_longitud_en_muchos_patrones():
    """Propiedad: cualquier patrón válido da nombres únicos y de la misma longitud."""
    revisados = 0
    for prefijo in ("a", "web", "srv.web", "x1-y2"):
        for separador in ("", "-"):
            for inicio in (0, 1, 7, 95, 999, 99_900):
                for relleno in (0, 1, 2, 5, 8):
                    for cantidad in (1, 2, 9, 10, 11, 57, 100):
                        patron = PatronNombres(prefijo, separador, inicio, relleno)
                        if validar_patron(patron, cantidad):
                            continue
                        nombres = generar_nombres(patron, cantidad)
                        assert len(nombres) == cantidad
                        assert len(set(nombres)) == cantidad, patron
                        assert len({len(n) for n in nombres}) == 1, patron
                        revisados += 1
    assert revisados > 500  # la propiedad se probó de verdad, no sobre cuatro casos


# --- Validación del patrón (V-L02, V-L03, V-L04) --------------------------------------------------


@pytest.mark.parametrize("prefijo", ["web", "srv-web", "a.b", "W3b"])
def test_prefijos_validos_no_dan_problemas(prefijo):
    assert validar_patron(PatronNombres(prefijo), 3) == []


@pytest.mark.parametrize(
    "prefijo",
    ["", "web 1", "web_", "wéb", "web/", "a,b", "a=b", "a&b", "a;b", "web\n", "web\r", "ñ"],
)
def test_v_l02_prefijo_con_caracteres_prohibidos_o_vacio(prefijo):
    problemas = validar_patron(PatronNombres(prefijo), 3)
    assert "V-L02" in _reglas(problemas)
    assert all(p.severidad == Severidad.ERROR for p in problemas)


@pytest.mark.parametrize(
    ("prefijo", "caracter"),
    [("web_", "_"), ("web ", " "), ("wéb", "é"), ("web/", "/")],
)
def test_ca_l02_4_v_l04_indica_el_primer_nombre_invalido_y_la_causa(prefijo, caracter):
    problemas = validar_patron(PatronNombres(prefijo, "", 1, 2), 3)
    (v_l04,) = _de(problemas, "V-L04")
    assert v_l04.params["nombre"] == f"{prefijo}01"
    assert v_l04.params["causa"] == "caracter"
    assert v_l04.params["caracter"] == caracter


def test_ca_l02_4_prefijo_demasiado_largo_con_el_numero_supera_63():
    problemas = validar_patron(PatronNombres("a" * 62, "-", 1, 2), 3)  # 62 + "-01" = 65
    (v_l04,) = _de(problemas, "V-L04")
    assert v_l04.params["causa"] == "longitud"
    assert v_l04.params["nombre"] == "a" * 62 + "-01"


@pytest.mark.parametrize(
    ("largo", "valido"),
    [(60, True), (61, False), (63, False)],  # 60 + "-01" = 63 cabe; 61 + "-01" = 64 no
)
def test_caso_limite_prefijo_de_60_y_63_caracteres(largo, valido):
    problemas = validar_patron(PatronNombres("a" * largo, "-", 1, 2), 3)
    assert (not problemas) is valido


def test_el_ultimo_nombre_tambien_cuenta_para_la_longitud():
    # 60 + "-" + "100" = 64: solo el último nombre (100) cruza el límite.
    problemas = validar_patron(PatronNombres("a" * 60, "-", 1, 2), 100)
    assert _de(problemas, "V-L04")


@pytest.mark.parametrize("prefijo", ["web.", "-web", "web-"])
def test_v_l04_nombre_con_guion_o_punto_al_borde_de_una_etiqueta(prefijo):
    # "web." + "-01" -> "web.-01": la etiqueta empieza por guion. "-web-01" empieza por guion.
    # "web-" + "" + "01" ("web-01") es válido: el guion queda en medio.
    problemas = validar_patron(PatronNombres(prefijo, "-" if prefijo != "web-" else "", 1, 2), 3)
    if prefijo == "web-":
        assert not problemas
    else:
        assert _de(problemas, "V-L04")


@pytest.mark.parametrize("separador", ["_", "--", " ", "x", "."])
def test_v_l03_separador_solo_guion_o_vacio(separador):
    assert "V-L03" in _reglas(validar_patron(PatronNombres("web", separador), 3))


@pytest.mark.parametrize("separador", ["", "-"])
def test_v_l03_separadores_validos(separador):
    assert validar_patron(PatronNombres("web", separador), 3) == []


@pytest.mark.parametrize(
    ("inicio", "cantidad"),
    [
        (-1, 3),  # inicio negativo
        (1_000_000, 1),  # inicio fuera de 0..999999
        (999_999, 5),  # CA-L02.8: se sale del rango al generar
        (999_998, 3),
    ],
)
def test_ca_l02_8_numero_fuera_de_0_999999(inicio, cantidad):
    problemas = validar_patron(PatronNombres("web", "-", inicio, 2), cantidad)
    assert "V-L04" in _reglas(problemas)


def test_el_limite_exacto_999999_es_valido():
    assert validar_patron(PatronNombres("web", "-", 999_999, 2), 1) == []
    assert validar_patron(PatronNombres("web", "-", 999_995, 2), 5) == []


@pytest.mark.parametrize("relleno", [-1, 9, 100])
def test_v_l04_relleno_fuera_de_0_8(relleno):
    assert "V-L04" in _reglas(validar_patron(PatronNombres("web", "-", 1, relleno), 3))


@pytest.mark.parametrize("relleno", [0, 8])
def test_v_l04_relleno_en_los_extremos_validos(relleno):
    assert validar_patron(PatronNombres("web", "-", 1, relleno), 3) == []


@pytest.mark.parametrize("inicio", [1.5, "1", None, True])
def test_v_l04_inicio_que_no_es_entero(inicio):
    assert "V-L04" in _reglas(validar_patron(PatronNombres("web", "-", inicio, 2), 3))


def test_rnf_l08_un_prefijo_con_separadores_de_parametros_se_rechaza_antes_de_construir():
    inv = inventario()
    for prefijo in ("a,b", "a=b", "a&b", "a;b", "a\nb"):
        problemas = validar_definicion(definicion(3, prefijo=prefijo), inv, (9, 2))
        assert "V-L02" in _reglas(problemas), prefijo


# --- Cantidad (V-L01, RF-L01) --------------------------------------------------------------------


@pytest.mark.parametrize("cantidad", [0, -1, 1.5, "abc", "", None, True, MAX_LOTE + 1, 101])
def test_ca_l01_2_y_l01_3_v_l01_rechaza_cantidades_invalidas(cantidad):
    problemas = validar_definicion(definicion(cantidad), inventario(), (9, 2))
    v_l01 = _de(problemas, "V-L01")
    assert len(v_l01) == 1
    assert v_l01[0].severidad == Severidad.ERROR
    assert v_l01[0].params["max"] == str(MAX_LOTE)  # nunca se recorta en silencio


@pytest.mark.parametrize("cantidad", [1, 2, 99, MAX_LOTE])
def test_v_l01_acepta_los_limites_validos(cantidad):
    assert not _de(validar_definicion(definicion(cantidad), inventario(), (9, 2)), "V-L01")


def test_el_limite_de_la_cantidad_es_el_de_la_constante_publica():
    """La frontera de V-L01 es ``MAX_LOTE`` tal cual (100, D-20), y vale 100."""
    inv = inventario()
    assert MAX_LOTE == 100
    assert not _de(validar_definicion(definicion(constantes.MAX_LOTE), inv, (9, 2)), "V-L01")
    assert _de(validar_definicion(definicion(constantes.MAX_LOTE + 1), inv, (9, 2)), "V-L01")


def test_ca_l01_4_max_lote_es_una_constante_nombrada_unica():
    """El valor de MAX_LOTE se define una sola vez en el código fuente (núcleo e interfaz)."""
    raiz = Path(__file__).resolve().parents[2] / "src" / "proxlaunch"
    definiciones = [
        str(ruta.relative_to(raiz))
        for ruta in raiz.rglob("*.py")
        if re.search(r"^MAX_LOTE\s*(?::[^=]+)?=", ruta.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert definiciones == ["nucleo/lote/constantes.py"]


def test_ca_l01_1_la_definicion_por_defecto_es_de_una_maquina():
    from proxlaunch.nucleo.lote.modelos import DefinicionLote, PoliticaThin

    d = DefinicionLote(plantilla=definicion().plantilla, cantidad=1, patron=PatronNombres("x"))
    assert d.cantidad == 1
    assert d.etiquetar is True  # D-20 (3)
    assert d.politica_thin == PoliticaThin.CONFIRMAR_CON_TOPE  # D-20 (1)
