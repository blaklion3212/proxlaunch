"""Correcciones S1, S2, S3 y S5 de la fase 6 del MVP 3 (RF-X02, RF-C11, RNF-M02).

S1: la comprobación de profundidad del JSON es lineal. S2/S3: el escritor CSV neutraliza los
disparadores de fórmula al inicio de cada segmento y quita los caracteres de formato invisibles;
todas las celdas van entrecomilladas (``QUOTE_ALL``). S5: el registro no admite saltos de línea
inyectados por datos externos.
"""

import csv
import io
import logging
import time

import pytest

from proxlaunch.nucleo.archivos.constantes import PROFUNDIDAD_JSON_MAX
from proxlaunch.nucleo.archivos.csv_seguro import sanear_celda, texto_csv
from proxlaunch.nucleo.archivos.json_estricto import cargar_json_estricto
from proxlaunch.nucleo.csv_importacion.errores_csv import escribir_filas_con_error
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_tabla
from proxlaunch.nucleo.csv_importacion.plantilla import escribir_plantilla
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.registro import ARCHIVO_LOG, FiltroSecretos, configurar_registro

from .apoyo_mvp3 import csv_bytes, perfil_base

BOM = b"\xef\xbb\xbf"
MAX = PROFUNDIDAD_JSON_MAX


def _releer(datos: bytes, sep: str = ";") -> list[list[str]]:
    return list(csv.reader(io.StringIO(datos.decode("utf-8-sig"), newline=""), delimiter=sep))


def _detalle(datos: bytes) -> str:
    with pytest.raises(ErrorProxLaunch) as exc:
        cargar_json_estricto(datos)
    assert exc.value.codigo == CodigoError.ARCHIVO_DANADO
    return exc.value.params["detalle"]


# --- S1: JSON de profundidad lineal --------------------------------------------------------------


def test_s1_un_mebibyte_de_comillas_escapadas_en_cadena_sin_cerrar_es_rapido_y_e_m04():
    datos = b'"' + b'\\"' * (512 * 1024)
    inicio = time.process_time()
    detalle = _detalle(datos)
    assert time.process_time() - inicio < 1.0
    assert detalle == "json"


def test_s1_muchas_barras_invertidas_seguidas_tambien_es_lineal():
    datos = b'["' + b"\\\\" * (512 * 1024)
    inicio = time.process_time()
    _detalle(datos)
    assert time.process_time() - inicio < 1.0


def test_s1_un_corchete_mas_que_el_maximo_es_profundidad():
    assert _detalle(b"[" * (MAX + 1)) == "profundidad"


def test_s1_llaves_anidadas_mas_que_el_maximo_son_profundidad():
    assert _detalle(b'{"a":' * (MAX + 1) + b"1" + b"}" * (MAX + 1)) == "profundidad"


def test_s1_profundidad_igual_al_maximo_se_carga():
    assert cargar_json_estricto(b"[" * MAX + b"]" * MAX) is not None


def test_s1_corchetes_dentro_de_cadenas_con_comillas_escapadas_no_cuentan():
    interior = '\\"' + "[" * (MAX * 3) + '\\"' + "{" * (MAX * 3)
    assert cargar_json_estricto(f'["{interior}"]'.encode()) == [
        f'"{"[" * (MAX * 3)}"{"{" * (MAX * 3)}'
    ]


def test_s1_la_barra_final_escapada_no_escapa_la_comilla_de_cierre():
    # La cadena "\\" termina; los corchetes posteriores sí cuentan.
    assert _detalle(b'["\\\\"' + b"[" * (MAX + 1)) == "profundidad"


def test_s1_profundidad_maxima_configurable():
    with pytest.raises(ErrorProxLaunch):
        cargar_json_estricto(b"[[[1]]]", profundidad_max=2)
    assert cargar_json_estricto(b"[[[1]]]", profundidad_max=3) == [[[1]]]


# --- S2: neutralización por segmento -------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("a;=1+1", "a;'=1+1"),
        ("x|@y", "x|'@y"),
        ("a,+b", "a,'+b"),
        ("a;  -2", "a;'  -2"),
        ('a;"=b', "a;'\"=b"),
        ("a\t=b", "a'=b"),
        ("a\n=b", "a'=b"),
        ("a\r\n@b", "a'@b"),
        ("a\t  =b", "a'  =b"),
        ("a;b;=c|@d", "a;b;'=c|'@d"),
        ("=a;=b", "'=a;'=b"),
    ],
)
def test_s2_se_neutraliza_cada_segmento_peligroso(entrada, esperado):
    assert sanear_celda(entrada) == esperado


@pytest.mark.parametrize("entrada", ["1-2", "a@b.c", "ok, fine", "a=b", "x+y", "a;b", "a - b"])
def test_s2_lo_que_no_empieza_segmento_con_disparador_queda_igual(entrada):
    assert sanear_celda(entrada) == entrada


def test_s2_todas_las_celdas_van_entrecomilladas_incluido_el_encabezado_y_los_enteros():
    cuerpo = texto_csv(["a", "b"], [["x", 7], ["", "y"]])[len(BOM) :]
    assert cuerpo == b'"a";"b"\r\n"x";"7"\r\n"";"y"\r\n'


@pytest.mark.parametrize("sep", [",", ";", "|", "\t"])
def test_s2_ida_y_vuelta_con_csv_reader_y_ningun_segmento_empieza_por_formula(sep):
    valores = ["a;=1+1", "x|@y", "a\t=b", "1-2", "ok, fine", "=cmd", "q,+w", "z\n-1"]
    datos = texto_csv(["=h", "v"], [["n", v] for v in valores], separador=sep)
    filas = _releer(datos, sep)
    assert filas[0] == ["'=h", "v"]
    esperadas = [sanear_celda(v) for v in valores]
    assert [f[1] for f in filas[1:]] == esperadas
    for celda in esperadas:
        for segmento in celda.replace("|", ";").replace(",", ";").split(";"):
            # Un segmento seguro empieza por apóstrofe o no empieza por disparador.
            assert not segmento.lstrip(" ").startswith(("=", "+", "-", "@"))


def test_s2_la_plantilla_se_reimporta_sin_perder_filas(tmp_path):
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta)
    datos = ruta.read_bytes()
    assert datos.startswith(BOM) and datos.count(b'"') > 0
    tabla = leer_tabla(datos)
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    assert len(resultado.filas) == 2
    assert tabla.encabezado[0] == "nombre"


def test_s2_el_csv_de_errores_entrecomillado_es_reimportable(tmp_path):
    tabla = leer_tabla(csv_bytes(["nombre;cpu", "=cmd;0", "a;=1+1;"]))
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(ruta, tabla, resultado, lambda p: f"{p.columna}: {p.regla}")
    datos = ruta.read_bytes()
    assert datos.startswith(BOM) and b'"nombre"' in datos
    tabla2 = leer_tabla(datos)
    assert tabla2.encabezado[-3:] == ("fila_original", "columna", "problema")
    assert len(tabla2.filas) >= 1


# --- S3: caracteres de formato invisibles --------------------------------------------------------


@pytest.mark.parametrize("invisible", ["​", "﻿", "⁠", "‌", "‍", "‮"])
def test_s3_el_invisible_antes_del_disparador_no_lo_oculta(invisible):
    assert sanear_celda(f"{invisible}=1+1") == "'=1+1"
    assert sanear_celda(f"a;{invisible}@x") == "a;'@x"
    assert sanear_celda(f"  {invisible}-3") == "'  -3"


def test_s3_el_invisible_se_elimina_del_texto():
    assert sanear_celda("a​b﻿c⁠d") == "abcd"


def test_s3_el_invisible_sale_del_csv_escrito():
    cuerpo = texto_csv(["​=h"], [["﻿+x"]])[len(BOM) :]
    assert cuerpo == b'"\'=h"\r\n"\'+x"\r\n'


# --- S5: el log no admite líneas inyectadas ------------------------------------------------------


@pytest.fixture
def logger_real():
    yield logging.getLogger("proxlaunch")
    logger = logging.getLogger("proxlaunch")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def test_s5_el_mensaje_con_saltos_sale_en_una_sola_linea_con_escapes(tmp_path, logger_real):
    log = configurar_registro(tmp_path / "log")
    log.warning("archivo=%s", "a\nFALSO\r")
    log.warning("siguiente")
    texto = (tmp_path / "log" / ARCHIVO_LOG).read_bytes().decode("utf-8")
    lineas = texto.split("\n")
    assert lineas[-1] == "" and len(lineas) == 3
    assert "\r" not in texto
    assert lineas[0].endswith("archivo=a\\x0aFALSO\\x0d")
    assert lineas[1].endswith("siguiente")


def test_s5_otros_controles_tambien_se_escapan(tmp_path, logger_real):
    log = configurar_registro(tmp_path)
    log.warning("x\x00y\x1bz\x7f\x85w")
    texto = (tmp_path / ARCHIVO_LOG).read_text(encoding="utf-8")
    assert "x\\x00y\\x1bz\\x7f\\x85w" in texto


def test_s5_las_trazas_de_excepcion_conservan_sus_saltos_de_linea():
    try:
        raise ValueError("fallo")
    except ValueError:
        import sys

        registro = logging.LogRecord("p", logging.ERROR, "f", 1, "m\n", None, sys.exc_info())
    registro.stack_info = "pila\nlinea2"
    FiltroSecretos().filter(registro)
    assert registro.msg == "m\\x0a"
    assert "\n" in registro.exc_text and "ValueError" in registro.exc_text
    assert registro.stack_info == "pila\nlinea2"
