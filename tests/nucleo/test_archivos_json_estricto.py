"""JSON estricto de archivos de terceros (RF-X02: CA-X02.3; §13 caso 9 de los requisitos).

Rechaza UTF-8 inválido, NaN/Infinity, números fuera de rango, claves repetidas y anidamiento
excesivo (sin llegar a ``RecursionError``); tolera un BOM UTF-8 inicial (D-T7). Todo problema
es E-M04 sin datos del usuario en el error.
"""

import json
import sys
import time

import pytest

from proxlaunch.nucleo.archivos.constantes import PROFUNDIDAD_JSON_MAX
from proxlaunch.nucleo.archivos.json_estricto import cargar_json_estricto
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

from .apoyo_lote import volcar

BOM = b"\xef\xbb\xbf"


def _error(datos: bytes, **kw) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        cargar_json_estricto(datos, **kw)
    return exc.value


def test_un_json_valido_se_interpreta():
    assert cargar_json_estricto(b'{"a": [1, 2.5, "x", null, true]}') == {
        "a": [1, 2.5, "x", None, True]
    }


def test_un_bom_utf8_inicial_se_tolera():
    assert cargar_json_estricto(BOM + b'{"a": 1}') == {"a": 1}


def test_un_doble_bom_no_es_json_valido():
    assert _error(BOM + BOM + b"{}").codigo == CodigoError.ARCHIVO_DANADO


@pytest.mark.parametrize("datos", [b"", b"   ", b"{", b'{"a": }', b"[1, 2,", b"\x00", b"nul"])
def test_json_vacio_truncado_o_malformado_da_e_m04(datos):
    e = _error(datos)
    assert e.codigo == CodigoError.ARCHIVO_DANADO


def test_utf8_invalido_da_e_m04():
    e = _error(b'{"a": "\xff\xfe"}')
    assert e.codigo == CodigoError.ARCHIVO_DANADO
    assert e.params["detalle"] == "utf8"


@pytest.mark.parametrize(
    "literal", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999", "1E999", "[1e400]"]
)
def test_nan_infinity_y_numeros_fuera_de_rango_dan_e_m04(literal):
    datos = literal.encode() if literal.startswith("[") else b'{"x": ' + literal.encode() + b"}"
    assert _error(datos).codigo == CodigoError.ARCHIVO_DANADO


def test_un_entero_con_miles_de_digitos_da_e_m04_y_no_una_excepcion_cruda():
    datos = b'{"x": ' + b"9" * 6000 + b"}"
    assert _error(datos).codigo == CodigoError.ARCHIVO_DANADO


def test_claves_repetidas_dan_e_m04():
    e = _error(b'{"a": 1, "a": 2}')
    assert e.codigo == CodigoError.ARCHIVO_DANADO
    assert e.params["detalle"] == "claves_repetidas"


def test_claves_repetidas_en_un_objeto_anidado_dan_e_m04():
    assert _error(b'{"a": [{"b": 1, "b": 2}]}').params["detalle"] == "claves_repetidas"


def test_500_niveles_de_anidamiento_dan_e_m04_sin_recursion_error():
    for abre, cierra in ((b"[", b"]"), (b'{"a":', b"}")):
        datos = abre * 500 + b"1" + cierra * 500
        e = _error(datos)
        assert e.codigo == CodigoError.ARCHIVO_DANADO
        assert e.params["detalle"] == "profundidad"


def test_un_anidamiento_enorme_no_llega_al_analizador(monkeypatch):
    """El pre-escaneo corta antes de ``json.loads`` (imposible un ``RecursionError``)."""
    llamadas = []
    real = json.loads
    monkeypatch.setattr(json, "loads", lambda *a, **k: llamadas.append(1) or real(*a, **k))
    _error(b"[" * 200_000)
    assert llamadas == []


def test_la_profundidad_maxima_se_acepta_y_una_mas_se_rechaza():
    assert PROFUNDIDAD_JSON_MAX == 8
    dentro = b"[" * PROFUNDIDAD_JSON_MAX + b"]" * PROFUNDIDAD_JSON_MAX
    cargar_json_estricto(dentro)
    fuera = b"[" * (PROFUNDIDAD_JSON_MAX + 1) + b"]" * (PROFUNDIDAD_JSON_MAX + 1)
    assert _error(fuera).params["detalle"] == "profundidad"


def test_corchetes_dentro_de_cadenas_no_cuentan_como_profundidad():
    valor = "[" * 100 + "{" * 100
    assert cargar_json_estricto(json.dumps({"a": valor}).encode()) == {"a": valor}


def test_comillas_escapadas_no_rompen_el_conteo_de_profundidad():
    valor = '\\"' * 50 + "[" * 50
    datos = json.dumps({"a": valor}).encode()
    assert cargar_json_estricto(datos) == {"a": valor}


def test_profundidad_maxima_configurable():
    cargar_json_estricto(b"[[1]]", profundidad_max=2)
    assert _error(b"[[[1]]]", profundidad_max=2).params["detalle"] == "profundidad"


def test_una_cadena_de_10_mb_se_interpreta_rapido_sin_errores():
    """§13.9: cadena de 10 MB. El límite de tamaño lo impone el lector; aquí no explota."""
    datos = b'{"a": "' + b"x" * (10 * 1024 * 1024) + b'"}'
    inicio = time.process_time()
    resultado = cargar_json_estricto(datos)
    assert len(resultado["a"]) == 10 * 1024 * 1024  # type: ignore[index]
    assert time.process_time() - inicio < 5.0


def test_una_cadena_con_nulo_escapado_se_interpreta_pero_el_esquema_la_rechazara():
    """``\\u0000`` es JSON válido; la validez de la cadena la decide el esquema (V-M04)."""
    assert cargar_json_estricto(b'{"a": "x\\u0000y"}') == {"a": "x\x00y"}


def test_un_nulo_literal_en_el_texto_es_json_invalido():
    assert _error(b'{"a": "x\x00y"}').codigo == CodigoError.ARCHIVO_DANADO


def test_el_error_nunca_incluye_datos_del_archivo():
    secreto = "CENTINELA-SECRETO-json"
    e = _error((f'{{"password": "{secreto}", "a": ').encode())  # truncado
    assert secreto not in volcar(e)
    e = _error((f'{{"k": "{secreto}", "k": 1}}').encode())
    assert secreto not in volcar(e)


def test_el_limite_de_recursion_de_python_no_se_alcanza(monkeypatch):
    anterior = sys.getrecursionlimit()
    sys.setrecursionlimit(200)
    try:
        assert _error(b"[" * 5000 + b"]" * 5000).params["detalle"] == "profundidad"
    finally:
        sys.setrecursionlimit(anterior)
