"""Plantilla QSS: tokens existentes y colores solo en paleta.py (CA-22.4)."""

import ast
import re
from pathlib import Path

import pytest

import proxlaunch.interfaz as paquete_interfaz
from proxlaunch.interfaz.tema.gestor_tema import generar_qss, leer_plantilla
from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO

TEMAS = {"oscuro": TOKENS_OSCURO, "claro": TOKENS_CLARO}
RAIZ_INTERFAZ = Path(paquete_interfaz.__file__).parent

RE_MARCADOR = re.compile(r"\{\{(\w+)\}\}")
# Colores literales: hexadecimales y funciones de color.
RE_COLOR_LITERAL = re.compile(r"#[0-9A-Fa-f]{3,8}\b|\b(?:rgba?|hsla?|hsv)\s*\(", re.IGNORECASE)
NOMBRES_DE_COLOR = r"white|black|red|green|blue|orange|gray|grey|yellow|purple|cyan|magenta|teal"
RE_NOMBRE_EN_PROPIEDAD = re.compile(
    rf"(?:color|background|border[\w-]*|outline)\s*:[^;{{}}]*\b(?:{NOMBRES_DE_COLOR})\b",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def plantilla():
    return leer_plantilla()


def test_la_plantilla_no_esta_vacia_y_tiene_marcadores(plantilla):
    assert len(plantilla) > 100
    assert RE_MARCADOR.search(plantilla)


@pytest.mark.parametrize("tema", TEMAS)
def test_ca22_4_generar_qss_no_usa_tokens_inexistentes(plantilla, tema):
    qss = generar_qss(plantilla, TEMAS[tema])  # KeyError si falta algún token
    assert "{{" not in qss
    assert "}}" not in qss


def test_ca22_4_todos_los_tokens_usados_existen_en_ambos_temas(plantilla):
    usados = set(RE_MARCADOR.findall(plantilla))
    assert usados
    assert usados <= set(TOKENS_OSCURO)
    assert usados <= set(TOKENS_CLARO)


@pytest.mark.parametrize("tema", TEMAS)
def test_los_colores_del_tema_llegan_al_qss(plantilla, tema):
    qss = generar_qss(plantilla, TEMAS[tema])
    for nombre in set(RE_MARCADOR.findall(plantilla)):
        assert TEMAS[tema][nombre] in qss


def test_los_dos_temas_producen_hojas_distintas(plantilla):
    assert generar_qss(plantilla, TOKENS_OSCURO) != generar_qss(plantilla, TOKENS_CLARO)


def test_generar_qss_con_token_inexistente_lanza_keyerror():
    with pytest.raises(KeyError):
        generar_qss("QWidget { color: {{no_existe}}; }", TOKENS_OSCURO)


def test_generar_qss_sustituye_cada_aparicion():
    qss = generar_qss("a {{texto}} b {{texto}}", TOKENS_OSCURO)
    assert qss == f"a {TOKENS_OSCURO['texto']} b {TOKENS_OSCURO['texto']}"


def test_ca22_4_la_plantilla_no_tiene_colores_literales(plantilla):
    sin_marcadores = RE_MARCADOR.sub("", plantilla)
    assert RE_COLOR_LITERAL.findall(sin_marcadores) == []
    assert RE_NOMBRE_EN_PROPIEDAD.findall(sin_marcadores) == []


def _cadenas_de_codigo(ruta):
    """Literales de texto del archivo, sin docstrings (que pueden citar colores)."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    docstrings = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            primero = nodo.body[0] if nodo.body else None
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                docstrings.add(id(primero.value))
    for nodo in ast.walk(arbol):
        es_cadena = isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)
        if es_cadena and id(nodo) not in docstrings:
            yield nodo.lineno, nodo.value


def _archivos_de_interfaz_salvo_paleta():
    return sorted(p for p in RAIZ_INTERFAZ.rglob("*.py") if p.name != "paleta.py")


def test_ca22_4_hay_archivos_de_interfaz_que_revisar():
    assert _archivos_de_interfaz_salvo_paleta()


@pytest.mark.parametrize(
    "archivo",
    _archivos_de_interfaz_salvo_paleta(),
    ids=lambda p: str(p.relative_to(RAIZ_INTERFAZ)),
)
def test_ca22_4_no_hay_colores_literales_fuera_de_paleta(archivo):
    ofensores = [
        (linea, texto)
        for linea, texto in _cadenas_de_codigo(archivo)
        if RE_COLOR_LITERAL.search(texto) or RE_NOMBRE_EN_PROPIEDAD.search(texto)
    ]
    assert not ofensores, f"colores literales en {archivo.name}: {ofensores}"
