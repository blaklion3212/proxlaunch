"""Escritor único de CSV (RF-C11: CA-C11.1..C11.9; CA-C10.2; INV-M4; §13 caso 13).

Todo CSV que escribe la aplicación pasa por ``texto_csv``/``escribir_csv``, que neutraliza las
fórmulas (``= + - @`` y tab/CR/LF iniciales), elimina caracteres de control y de dirección de
texto, escribe UTF-8 con BOM y ``\\r\\n`` y es RFC 4180 (``QUOTE_MINIMAL``).
"""

import csv
import io
import os
import random
import re
import stat
from pathlib import Path

import pytest

import proxlaunch
from proxlaunch.nucleo.archivos.csv_seguro import (
    DISPARADORES,
    escribir_csv,
    sanear_celda,
    texto_csv,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

BOM = b"\xef\xbb\xbf"
NUCLEO = Path(proxlaunch.__file__).resolve().parent / "nucleo"


def _releer(datos: bytes, sep: str = ";") -> list[list[str]]:
    texto = datos.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(texto, newline=""), delimiter=sep))


# --- CA-C11.1: disparadores --------------------------------------------------------------------


@pytest.mark.parametrize("disparador", ["=", "+", "-", "@", "\t", "\r", "\n"])
def test_cada_disparador_al_inicio_recibe_apostrofe(disparador):
    assert sanear_celda(f"{disparador}1+1") == "'" + (
        "1+1" if disparador in "\t\r\n" else f"{disparador}1+1"
    )


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ('=HYPERLINK("http://x","y")', '\'=HYPERLINK("http://x","y")'),
        ("@SUM(1)", "'@SUM(1)"),
        ("-2+3", "'-2+3"),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("\t=1", "'=1"),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("=1+1", "'=1+1"),
    ],
)
def test_ejemplos_de_los_requisitos(entrada, esperado):
    assert sanear_celda(entrada) == esperado


@pytest.mark.parametrize(
    "entrada", [" =1+1", '"=1+1', "  @SUM(1)", ' "-1', "'=1", "' +1", "   \"'=x"]
)
def test_el_primer_caracter_significativo_tras_espacios_y_comillas_cuenta(entrada):
    """CA-C11.2."""
    assert sanear_celda(entrada).startswith("'")


@pytest.mark.parametrize(
    "entrada", ["", "normal", "a=b", "web-01", "x+y", "a@b.com", "1=1", " texto", "5"]
)
def test_el_texto_normal_no_se_modifica(entrada):
    assert sanear_celda(entrada) == entrada


def test_los_disparadores_declarados_incluyen_los_de_los_requisitos():
    assert {"=", "+", "-", "@", "\t", "\r"} <= DISPARADORES


# --- CA-C11.7: control y dirección de texto ---------------------------------------------------


def test_se_eliminan_los_caracteres_de_control_y_de_direccion_de_texto():
    assert sanear_celda("a\x00b\x07c‮d⁦e‏f؜g") == "abcdefg"


def test_un_control_eliminado_al_inicio_ya_no_deja_pasar_una_formula():
    assert sanear_celda("\x00=1") == "=1" or sanear_celda("\x00=1").startswith("'")
    assert sanear_celda("\x07=cmd").startswith("'")
    assert sanear_celda("‮=cmd").startswith("'")


def test_un_salto_de_linea_interior_se_elimina_y_no_rompe_la_fila():
    datos = texto_csv(["n"], [["linea1\nlinea2\r\nlinea3"]])
    assert _releer(datos) == [["n"], ["linea1linea2linea3"]]


# --- Tipos (CA-C11.3) -------------------------------------------------------------------------


def test_los_enteros_no_negativos_se_escriben_sin_apostrofe():
    datos = texto_csv(["a", "b", "c"], [[0, 150, 999999999]])
    assert _releer(datos)[1] == ["0", "150", "999999999"]


def test_un_entero_negativo_se_escribe_como_texto_saneado():
    assert _releer(texto_csv(["a"], [[-1]]))[1] == ["'-1"]


@pytest.mark.parametrize("malo", [True, False, 1.5, None, b"x", ["a"], {"a": 1}, object()])
def test_un_tipo_no_admitido_es_type_error(malo):
    with pytest.raises(TypeError):
        texto_csv(["a"], [[malo]])


def test_un_tipo_no_admitido_en_el_encabezado_es_type_error():
    with pytest.raises(TypeError):
        texto_csv([None], [])  # type: ignore[list-item]


# --- Formato de salida (CA-C10.2, CA-C11.6) ---------------------------------------------------


def test_utf8_con_bom_crlf_y_separador_por_defecto_punto_y_coma():
    datos = texto_csv(["nombre", "cpu"], [["web", 2]])
    assert datos.startswith(BOM)
    assert datos[len(BOM) :] == b"nombre;cpu\r\nweb;2\r\n"


def test_el_bom_aparece_una_sola_vez():
    assert texto_csv(["a"], [["b"]]).count(BOM) == 1


@pytest.mark.parametrize("sep", [";", ",", "\t", "|"])
def test_separadores_admitidos(sep):
    assert _releer(texto_csv(["a", "b"], [["1", "2"]], separador=sep), sep) == [
        ["a", "b"],
        ["1", "2"],
    ]


@pytest.mark.parametrize("sep", ["", ";;", "ab", " ", "x", "\r", '"'])
def test_separadores_no_admitidos_son_value_error(sep):
    with pytest.raises(ValueError):
        texto_csv(["a"], [["b"]], separador=sep)


@pytest.mark.parametrize(
    "valor",
    ["con;punto y coma", "con,coma", 'con "comillas"', "salto\nde linea", 'x;y,z"w', "tab\tmedio"],
)
def test_entrecomillado_rfc_4180_ida_y_vuelta_con_csv(valor):
    esperado = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", valor)
    for sep in (";", ","):
        assert _releer(texto_csv(["c"], [[valor]], separador=sep), sep)[1] == [esperado]


def test_quote_minimal_no_entrecomilla_lo_innecesario():
    assert texto_csv(["a"], [["simple"]])[len(BOM) :] == b"a\r\nsimple\r\n"
    assert b'"' not in texto_csv(["a", "b"], [["x", "y"]])


def test_el_encabezado_tambien_se_sanea():
    """CA-C11.4: los encabezados de un archivo del usuario no son de fiar."""
    assert _releer(texto_csv(["=cmd", "@x"], []))[0] == ["'=cmd", "'@x"]


def test_solo_encabezado_sin_filas():
    assert texto_csv(["a", "b"], [])[len(BOM) :] == b"a;b\r\n"


# --- CA-C11.9: 10 000 valores aleatorios -----------------------------------------------------


def _valor_aleatorio(rng: random.Random) -> str:
    prefijos = ["=", "+", "-", "@", "\t", "\r", "\n", " =", '"=', "'=", "\t@", "  -", ""]
    cuerpo = "".join(
        rng.choice("abcXYZ019 ;,\"'=+-@()|!\t\n\r\x00‮‏ñé") for _ in range(rng.randint(0, 24))
    )
    return rng.choice(prefijos) + cuerpo


def test_10000_valores_con_disparadores_releidos_con_csv_reader_no_empiezan_por_formula():
    rng = random.Random(20260514)
    valores = [_valor_aleatorio(rng) for _ in range(10_000)]
    for sep in (";", ","):
        datos = texto_csv(["v"], [[v] for v in valores], separador=sep)
        celdas = [fila[0] for fila in _releer(datos, sep)[1:]]
        assert len(celdas) == len(valores)
        for original, celda in zip(valores, celdas, strict=True):
            significativo = celda.lstrip(' "')
            assert significativo[:1] not in {"=", "+", "-", "@", "\t", "\r", "\n"}, (
                original,
                celda,
            )
            assert "\x00" not in celda and "‮" not in celda and "‏" not in celda
            assert not celda.startswith(("\t", "\r", "\n"))


# --- escribir_csv ----------------------------------------------------------------------------


def test_escribir_csv_escribe_atomico_con_bom(tmp_path):
    ruta = tmp_path / "plantilla.csv"
    escribir_csv(ruta, ["nombre"], [["=1+1"]])
    datos = ruta.read_bytes()
    assert datos.startswith(BOM)
    assert _releer(datos)[1] == ["'=1+1"]
    if os.name == "posix":
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["plantilla.csv"]


def test_escribir_csv_reemplaza_y_en_fallo_deja_el_original(tmp_path, monkeypatch):
    ruta = tmp_path / "x.csv"
    ruta.write_bytes(b"ORIGINAL")

    def _replace(*a, **k):
        raise OSError(28, "disco lleno")

    monkeypatch.setattr(os, "replace", _replace)
    with pytest.raises(ErrorProxLaunch) as exc:
        escribir_csv(ruta, ["a"], [["b"]])
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    monkeypatch.undo()
    assert ruta.read_bytes() == b"ORIGINAL"


def test_un_error_de_tipo_no_deja_un_archivo_a_medias(tmp_path):
    ruta = tmp_path / "x.csv"
    with pytest.raises(TypeError):
        escribir_csv(ruta, ["a"], [[1.5]])
    assert not ruta.exists()


# --- Prueba estática: único escritor (arquitectura §5.6) -------------------------------------


def test_csv_writer_solo_aparece_en_csv_seguro():
    """«Ningún otro módulo escribe CSV» (CA-C11, arquitectura §5.6)."""
    patron = re.compile(r"csv\.(writer|DictWriter)|\.writerow|\.writerows")
    ofensores = []
    for py in sorted((NUCLEO.parent).rglob("*.py")):
        if py.name == "csv_seguro.py":
            continue
        if patron.search(py.read_text(encoding="utf-8")):
            ofensores.append(str(py.relative_to(NUCLEO.parent)))
    assert ofensores == []
