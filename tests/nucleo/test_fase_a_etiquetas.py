"""A3: normalización de etiquetas y evaluación de la política del centro de datos.

Requisitos: CA-A3.2.3, CA-A3.2.4, CA-A3.4.1..A3.4.9, CL-A10, CL-A11 (regla de mayúsculas).
Funciones puras: ``normalizar_etiquetas``, ``etiquetas_finales``, ``rechazadas_por_politica`` y
``PoliticaEtiquetas.desde_opciones``.
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.opciones.etiquetas import (
    etiquetas_finales,
    normalizar_etiquetas,
    rechazadas_por_politica,
)
from proxlaunch.nucleo.opciones.modelos import PoliticaEtiquetas

from .apoyo_fase_a import cfg_vm

# --- Normalización (CA-A3.2.3, CA-A3.2.4, P-5) ---------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("a,,b, c ,", ("a", "b", "c")),  # CA-A3.2.3
        ("a,a", ("a",)),  # CA-A3.2.4
        ("web, prod", ("web", "prod")),
        ("a;b", ("a", "b")),  # P-5: el ';' también separa
        ("a; b, c;d", ("a", "b", "c", "d")),
        ("", ()),
        (" , ,, ; ", ()),
        ("  solo  ", ("solo",)),
        ("b,a,b,c,a", ("b", "a", "c")),  # respeta el orden de aparición
    ],
)
def test_normalizar_etiquetas(texto, esperado):
    assert normalizar_etiquetas(texto) == esperado


def test_a3_2_normalizar_no_corrige_mayusculas_ni_espacios_internos():
    """CA-A3.2.1: ``Web`` y ``a b`` no se «arreglan» en silencio: los rechaza la validación."""
    assert normalizar_etiquetas("Web, a b") == ("Web", "a b")


def test_ca_a3_1_4_etiquetas_finales_fijas_primero_y_sin_duplicados():
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"), etiquetas_usuario=("lote-x", "web", "web"))
    assert etiquetas_finales(cfg) == ("proxlaunch", "lote-x", "web")


def test_etiquetas_finales_sin_nada():
    assert etiquetas_finales(cfg_vm()) == ()


# --- rechazadas_por_politica ---------------------------------------------------------------------


def _r(etiquetas, politica, sys_modify=False):
    return rechazadas_por_politica(etiquetas, politica, sys_modify)


def test_con_sys_modify_todo_pasa_sea_cual_sea_la_politica():
    pol = PoliticaEtiquetas("none", registradas=("a", "b"))
    assert _r(["a", "b", "c"], pol, sys_modify=True) == []


def test_ca_a3_4_1_none_rechaza_todas_con_el_motivo_ninguna_permitida():
    assert _r(["a", "b"], PoliticaEtiquetas("none")) == [
        ("a", "ninguna_permitida"),
        ("b", "ninguna_permitida"),
    ]


def test_ca_a3_4_2_list_acepta_solo_las_de_user_allow_list():
    pol = PoliticaEtiquetas("list", lista_usuario=("a",))
    assert _r(["a", "b"], pol) == [("b", "no_permitida")]


def test_ca_a3_4_3_existing_acepta_las_de_allowed_tags():
    pol = PoliticaEtiquetas("existing", existentes=("a",))
    assert _r(["a", "b"], pol) == [("b", "no_permitida")]


def test_a3_4_list_tambien_acepta_las_existentes():
    """Arq. §4: con ``list`` valen las de la lista del usuario y las existentes."""
    pol = PoliticaEtiquetas("list", lista_usuario=("a",), existentes=("b",))
    assert _r(["a", "b", "c"], pol) == [("c", "no_permitida")]


def test_ca_a3_4_4_free_no_restringe():
    assert _r(["a", "b"], PoliticaEtiquetas("free")) == []


def test_ca_a3_4_5_registrada_se_rechaza_sin_sys_modify_y_gana_a_la_politica():
    """La etiqueta registrada se rechaza como «registrada» aunque ``free`` la dejaría pasar."""
    pol = PoliticaEtiquetas("free", registradas=("prod",))
    assert _r(["prod", "otra"], pol) == [("prod", "registrada")]
    assert _r(["prod"], PoliticaEtiquetas("none", registradas=("prod",))) == [
        ("prod", "registrada")
    ]


def test_a3_4_permisos_desconocidos_no_afirman_que_una_registrada_se_rechaza():
    """``puede_sys_modify=None`` (permisos desconocidos): no se rechaza por «registrada»."""
    pol = PoliticaEtiquetas("free", registradas=("prod",))
    assert rechazadas_por_politica(["prod"], pol, None) == []
    # Pero sí se aplica ``none``: no depende de Sys.Modify conocido.
    assert rechazadas_por_politica(["x"], PoliticaEtiquetas("none"), None) == [
        ("x", "ninguna_permitida")
    ]


@pytest.mark.parametrize("distingue", [False, True])
def test_ca_a3_4_7_mayusculas_comparacion_exacta_decision_s1(distingue):
    """Decisión S-1 (fase A §15): la comparación es exacta, con o sin ``case-sensitive``."""
    pol = PoliticaEtiquetas("list", ("Web",), distingue_mayusculas=distingue)
    assert _r(["web"], pol) == [("web", "no_permitida")]
    assert _r(["Web"], pol) == []


@pytest.mark.parametrize("distingue", [False, True])
def test_cl_a10_registradas_comparadas_de_forma_exacta_decision_s1(distingue):
    pol = PoliticaEtiquetas("free", registradas=("PROD",), distingue_mayusculas=distingue)
    assert _r(["prod"], pol) == []
    assert _r(["PROD"], pol) == [("PROD", "registrada")]


def test_cl_a11_etiqueta_repetida_se_evalua_una_vez():
    pol = PoliticaEtiquetas("none")
    assert _r(["a", "a", "a"], pol) == [("a", "ninguna_permitida")]


def test_a3_4_sin_etiquetas_no_hay_nada_que_rechazar():
    assert _r([], PoliticaEtiquetas("none")) == []


# --- PoliticaEtiquetas.desde_opciones (cuerpo de GET /cluster/options) ----------------------------


def test_ca_a3_4_8_cuerpo_vacio_o_sin_user_tag_access_es_free():
    for cuerpo in ({}, {"keyboard": "es"}, {"user-tag-access": None}):
        pol = PoliticaEtiquetas.desde_opciones(cuerpo)
        assert pol == PoliticaEtiquetas()
        assert pol.permiso == "free" and pol.distingue_mayusculas is False


def test_desde_opciones_objeto_con_listas():
    pol = PoliticaEtiquetas.desde_opciones(
        {
            "user-tag-access": {"user-allow": "list", "user-allow-list": ["a", "b"]},
            "registered-tags": ["prod"],
            "allowed-tags": ["x", "y"],
            "tag-style": {"case-sensitive": 1},
        }
    )
    assert pol.permiso == "list"
    assert pol.lista_usuario == ("a", "b") and pol.registradas == ("prod",)
    assert pol.existentes == ("x", "y") and pol.distingue_mayusculas is True


def test_desde_opciones_cadenas_de_propiedad_como_las_devuelve_proxmox():
    """Propiedades compuestas como ``clave=valor,clave=valor`` y listas con ``;``."""
    pol = PoliticaEtiquetas.desde_opciones(
        {
            "user-tag-access": "user-allow=list,user-allow-list=a;b",
            "registered-tags": "prod;qa",
            "tag-style": "case-sensitive=1,ordering=config",
        }
    )
    assert pol.permiso == "list" and pol.lista_usuario == ("a", "b")
    assert pol.registradas == ("prod", "qa") and pol.distingue_mayusculas is True


@pytest.mark.parametrize("permiso", ["none", "list", "existing", "free"])
def test_desde_opciones_los_cuatro_modos(permiso):
    assert (
        PoliticaEtiquetas.desde_opciones({"user-tag-access": {"user-allow": permiso}}).permiso
        == permiso
    )


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"user-tag-access": {"user-allow": "todo"}},
        {"user-tag-access": {"user-allow": 3}},
        {"user-tag-access": 5},
        {"user-tag-access": "sin-igual"},
        {"tag-style": {"case-sensitive": "quizá"}},
        {"tag-style": {"case-sensitive": 7}},
        {"registered-tags": 5},
        {"registered-tags": [1, 2]},
        {"allowed-tags": {"a": 1}},
        [],
        "texto",
        None,
    ],
)
def test_ca_a3_4_9_cuerpo_inesperado_lanza_value_error(cuerpo):
    """CA-A3.4.9: un cuerpo inesperado se señala con ``ValueError`` (el catálogo avisa y no
    bloquea).
    """
    with pytest.raises(ValueError):
        PoliticaEtiquetas.desde_opciones(cuerpo)


def test_desde_opciones_acepta_booleanos_y_trozos_vacios_en_la_cadena():
    """Robustez del intérprete de ``/cluster/options``: ``True`` cuenta como 1 y las comas sobrantes
    se ignoran.
    """
    pol = PoliticaEtiquetas.desde_opciones(
        {"tag-style": {"case-sensitive": True}, "user-tag-access": "user-allow=none,,"}
    )
    assert pol.distingue_mayusculas is True and pol.permiso == "none"
    assert (
        PoliticaEtiquetas.desde_opciones({"tag-style": {"case-sensitive": "0"}})
        == PoliticaEtiquetas()
    )
