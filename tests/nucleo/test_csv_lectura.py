"""Lectura del CSV: codificación, separador, RFC 4180 y límites (RF-C02, RF-C15; CA-C02.1..C02.12,
CA-C03.5, CA-C15.1..C15.3; INV-M3; §13 caso 10 de los requisitos).

Orden de detección: BOM UTF-8, BOM UTF-16, UTF-8 estricto, Windows-1252. Los límites nunca
recortan en silencio (E-M06 con el valor real) y la numeración de filas es la de Excel.
"""

import hashlib

import pytest

from proxlaunch.nucleo.archivos.constantes import (
    LINEAS_DETECCION,
    MAX_BYTES_CSV,
    MAX_COLUMNAS_CSV,
    MAX_LONG_CELDA,
)
from proxlaunch.nucleo.csv_importacion.decodificacion import decodificar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv, leer_tabla
from proxlaunch.nucleo.csv_importacion.modelos import Codificacion, OpcionesCsv
from proxlaunch.nucleo.csv_importacion.separador import detectar_separador
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote import constantes as constantes_lote

from .apoyo_mvp3 import DATOS_MVP3, csv_bytes, tabla_csv


def _error(datos: bytes, opciones: OpcionesCsv | None = None) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(datos) if opciones is None else leer_tabla(datos, opciones)
    return exc.value


# --- Codificación (CA-C02.1..C02.3) ---------------------------------------------------------------


def test_bom_utf8_se_detecta_y_se_descarta():
    texto, enc = decodificar(b"\xef\xbb\xbfnombre;cpu\r\nweb;2")
    assert enc == Codificacion.UTF8_BOM and texto == "nombre;cpu\r\nweb;2"


@pytest.mark.parametrize("bom_codec", ["utf-16-le", "utf-16-be"])
def test_bom_utf16_le_y_be_se_detectan(bom_codec):
    cuerpo = "nombre;cpu\r\nñandú;2"
    bom = b"\xff\xfe" if bom_codec.endswith("le") else b"\xfe\xff"
    texto, enc = decodificar(bom + cuerpo.encode(bom_codec))
    assert enc == Codificacion.UTF16 and texto == cuerpo


def test_utf8_estricto_sin_bom():
    texto, enc = decodificar("nombre\r\npeña".encode())
    assert enc == Codificacion.UTF8 and texto == "nombre\r\npeña"


def test_windows_1252_con_pena_y_nandu_se_lee_bien():
    """CA-C02.1: Excel en español en Windows."""
    texto, enc = decodificar("peña;Ñandú;€".encode("cp1252"))
    assert enc == Codificacion.WINDOWS_1252 and texto == "peña;Ñandú;€"


def test_el_archivo_de_ejemplo_de_excel_en_windows_1252():
    datos = (DATOS_MVP3 / "excel-windows1252.csv").read_bytes()
    tabla = leer_tabla(datos)
    assert tabla.codificacion == Codificacion.WINDOWS_1252 and tabla.deteccion.separador == ";"
    assert tabla.encabezado[-1] == "descripción"
    assert [f.celdas[-1] for f in tabla.filas] == ["peña", "Ñandú", "ración", "ñoño"]
    assert [f.numero for f in tabla.filas] == [2, 3, 4, 5]


@pytest.mark.parametrize("byte", [0x81, 0x8D, 0x8F, 0x90, 0x9D])
def test_bytes_no_definidos_en_windows_1252_dan_e_m07_con_la_fila_aproximada(byte):
    """CA-C02.2."""
    datos = b"nombre;cpu\r\nweb;2\r\nbad\xc3;" + bytes([byte]) + b"\r\notra;3"
    with pytest.raises(ErrorProxLaunch) as exc:
        decodificar(datos)
    assert exc.value.codigo == CodigoError.CSV_CODIFICACION
    assert exc.value.params == {"fila": "3", "motivo": "codificacion"}


def test_se_puede_elegir_otra_codificacion_a_mano_en_avanzado():
    datos = b"nombre\r\nweb\x81"
    assert decodificar(datos, Codificacion.ISO_8859_1)[1] == Codificacion.ISO_8859_1
    assert decodificar("ñ".encode(), Codificacion.UTF8)[0] == "ñ"
    with pytest.raises(ErrorProxLaunch):
        decodificar("ñ".encode("cp1252"), Codificacion.UTF8)


def test_iso_8859_1_nunca_se_elige_sola():
    _, enc = decodificar(b"a\xe9b")
    assert enc == Codificacion.WINDOWS_1252


def test_caracter_de_sustitucion_u_fffd_da_e_m07():
    """CA-C02.3."""
    with pytest.raises(ErrorProxLaunch) as exc:
        decodificar("nombre\r\nwe�b".encode())
    assert exc.value.params["motivo"] == "sustitucion" and exc.value.params["fila"] == "2"


@pytest.mark.parametrize(
    "datos",
    [
        b"nombre\r\nweb\x00",
        b"nombre\x00",
        "nombre;cpu".encode("utf-16-le"),
        b"\xef\xbb\xbfa\x00b",
    ],
    ids=["nulo_al_final", "nulo_solo", "utf16_sin_bom", "nulo_tras_bom"],
)
def test_un_byte_nulo_nunca_llega_al_analisis(datos):
    """CA-C02.3: UTF-16 sin BOM también acaba aquí (E-M07), no como texto basura."""
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(datos)
    assert exc.value.codigo == CodigoError.CSV_CODIFICACION
    assert exc.value.params["motivo"] in {"nulo", "codificacion"}


def test_el_error_de_codificacion_no_incluye_datos_del_archivo():
    secreto = b"CENTINELA-SECRETO-csv"
    with pytest.raises(ErrorProxLaunch) as exc:
        decodificar(b"nombre\r\n" + secreto + b"\x81")
    assert b"CENTINELA" not in repr(exc.value).encode()


# --- Separador (CA-C02.4..C02.6) ------------------------------------------------------------------


@pytest.mark.parametrize("sep", [";", ",", "\t"])
def test_detecta_cada_separador(sep):
    texto = f"nombre{sep}cpu{sep}memoria\r\nweb{sep}2{sep}4\r\ndb{sep}4{sep}8\r\n"
    d = detectar_separador(texto)
    assert (d.separador, d.ambiguo, d.linea_sep) == (sep, False, False)


def test_gana_el_separador_con_el_mismo_numero_de_columnas_en_mas_lineas():
    texto = "nombre;cpu;memoria\r\nweb;2;4\r\ndb;4;8\r\nx;1,5;2\r\n"
    assert detectar_separador(texto).separador == ";"


def test_comas_decimales_dentro_de_comillas_no_confunden_al_detector():
    """§13.10: ``"1,5"`` con ``,`` como separador."""
    texto = 'nombre,memoria\r\nweb,"1,5"\r\ndb,"2,5"\r\n'
    assert detectar_separador(texto).separador == ","


def test_empate_con_decimal_con_coma_gana_el_punto_y_coma():
    d = detectar_separador("a,b;c\r\n1,2;3\r\n")
    assert d.separador == ";" and not d.ambiguo


def test_empate_sin_decimal_con_coma_es_ambiguo_y_lista_los_candidatos():
    """CA-C02.6."""
    d = detectar_separador("a,b;c\r\nx,y;z\r\n")
    assert d.ambiguo and set(d.candidatos) == {";", ","} and d.separador in d.candidatos


def test_la_linea_sep_manda_y_se_omite():
    """CA-C02.4: ``sep=;`` de Excel."""
    d = detectar_separador("sep=;\r\nnombre,cpu\r\nweb,2\r\n")
    assert (d.separador, d.linea_sep, d.ambiguo) == (";", True, False)
    d2 = detectar_separador("SEP=|\r\na|b\r\n")
    assert d2.separador == "|" and d2.linea_sep


def test_con_linea_sep_la_tabla_no_la_incluye_y_la_numeracion_es_la_de_excel():
    tabla = leer_tabla(b"sep=;\r\nnombre;cpu\r\nweb;2\r\n")
    assert tabla.deteccion.linea_sep and tabla.encabezado == ("nombre", "cpu")
    assert [(f.numero, f.celdas) for f in tabla.filas] == [(2, ("web", "2"))]


def test_una_sola_columna_se_acepta_sin_ambiguedad():
    """CA-C02.5."""
    d = detectar_separador("nombre\r\nweb\r\ndb\r\n")
    assert (d.separador, d.ambiguo, d.candidatos) == (";", False, ())
    tabla = leer_tabla(b"nombre\r\nweb-01\r\ndb-01\r\n")
    assert tabla.encabezado == ("nombre",) and [f.celdas for f in tabla.filas] == [
        ("web-01",),
        ("db-01",),
    ]


def test_solo_se_inspeccionan_las_primeras_20_lineas():
    assert LINEAS_DETECCION == 20
    lineas = ["a;b"] * 20 + ["a,b,c,d,e,f"] * 200  # a partir de la 21 gana la coma, pero no cuenta
    assert detectar_separador("\r\n".join(lineas)).separador == ";"


def test_separador_manual_gana_a_la_deteccion():
    tabla = leer_tabla(b"a;b,c\r\n1;2,3\r\n", OpcionesCsv(separador=","))
    assert tabla.encabezado == ("a;b", "c") and tabla.deteccion.separador == ","


@pytest.mark.parametrize("malo", ["", ";;", '"', "\n", "\r"])
def test_un_separador_manual_invalido_es_value_error(malo):
    with pytest.raises(ValueError):
        leer_tabla(b"a;b\r\n1;2\r\n", OpcionesCsv(separador=malo))


def test_codificacion_manual_en_la_tabla():
    tabla = leer_tabla(b"nombre\r\nweb\x81\r\n", OpcionesCsv(codificacion=Codificacion.ISO_8859_1))
    assert tabla.codificacion == Codificacion.ISO_8859_1


# --- RFC 4180 y finales de línea (CA-C02.7) -------------------------------------------------------


@pytest.mark.parametrize("fin", ["\r\n", "\n", "\r"])
def test_acepta_crlf_lf_y_cr_solitario(fin):
    tabla = leer_tabla(csv_bytes(["nombre;cpu", "web;2", "db;4"], fin=fin))
    assert [f.celdas for f in tabla.filas] == [("web", "2"), ("db", "4")]
    assert [f.numero for f in tabla.filas] == [2, 3]


def test_comillas_dobles_escapadas_y_separador_dentro_de_comillas():
    tabla = leer_tabla('nombre;nota\r\nweb;"dice ""hola""; adiós"\r\n'.encode())
    assert tabla.filas[0].celdas == ("web", 'dice "hola"; adiós')


def test_saltos_de_linea_dentro_de_comillas_cuentan_como_una_sola_fila():
    tabla = leer_tabla(b'nombre;nota\r\nweb;"linea1\r\nlinea2"\r\ndb;x\r\n')
    assert [(f.numero, f.celdas[0]) for f in tabla.filas] == [(2, "web"), (3, "db")]  # como Excel
    assert "linea1" in tabla.filas[0].celdas[1] and "linea2" in tabla.filas[0].celdas[1]


@pytest.mark.parametrize(
    ("texto", "fila"),
    [
        ('nombre;nota\r\nweb;"sin cerrar\r\notra;fila\r\n', 2),
        ('nombre;nota\r\nweb;ok\r\ndb;"sin cerrar', 3),
        ('nombre;nota\r\nweb;"a"b\r\n', 2),
    ],
    ids=["abierta_en_fila_2", "abierta_en_fila_3_al_final", "texto_tras_cierre"],
)
def test_comillas_mal_formadas_dan_e_m07_con_la_fila_donde_empieza_el_registro(texto, fila):
    """CA-C02.10."""
    e = _error(texto.encode())
    assert e.codigo == CodigoError.CSV_CODIFICACION
    assert e.params == {"fila": str(fila), "motivo": "comillas"}


def test_lineas_en_blanco_intermedias_y_finales_se_ignoran_pero_la_numeracion_las_cuenta():
    """§13.10 / CA-C02.8."""
    tabla = leer_tabla(b"nombre;cpu\r\n\r\nweb;2\r\n\r\n\r\ndb;4\r\n\r\n\r\n")
    assert [(f.numero, f.celdas[0]) for f in tabla.filas] == [(3, "web"), (6, "db")]


def test_filas_de_solo_separadores_se_ignoran_y_no_cuentan_para_el_limite():
    lineas = ["nombre;cpu"] + [f"m{i};1" for i in range(100)] + [";;"] * 30 + ["  ;  "] * 5
    tabla = leer_tabla(csv_bytes(lineas))
    assert len(tabla.filas) == 100


def test_las_celdas_vacias_del_final_de_cada_fila_se_recortan():
    tabla = leer_tabla(b"nombre;cpu;;\r\nweb;2;;\r\ndb;;;\r\n")
    assert tabla.encabezado == ("nombre", "cpu")
    assert [f.celdas for f in tabla.filas] == [("web", "2"), ("db",)]


def test_el_bom_y_los_espacios_del_encabezado_se_descartan():
    """CA-C03.5."""
    tabla = leer_tabla("﻿  nombre  ;  cpu \r\nweb;2\r\n".encode())
    assert tabla.encabezado == ("nombre", "cpu")
    tabla2 = leer_tabla(b"\xef\xbb\xbf  nombre ;cpu\r\nweb;2\r\n")
    assert tabla2.encabezado == ("nombre", "cpu")


def test_utf16_le_completo_con_nombres_acentuados():
    datos = "﻿nombre;memoria\r\nñandú;4\r\n".encode("utf-16-le")
    datos = b"\xff\xfe" + "nombre;memoria\r\nñandú;4\r\n".encode("utf-16-le")
    tabla = leer_tabla(datos)
    assert tabla.codificacion == Codificacion.UTF16 and tabla.filas[0].celdas[0] == "ñandú"


def test_los_archivos_de_ejemplo_de_cada_formato_de_excel():
    for nombre, codificacion, separador in [
        ("excel-windows1252.csv", Codificacion.WINDOWS_1252, ";"),
        ("utf8-bom-comas.csv", Codificacion.UTF8_BOM, ","),
        ("utf16-le.csv", Codificacion.UTF16, ";"),
        ("sep-linea.csv", Codificacion.UTF8, ";"),
    ]:
        tabla = leer_tabla((DATOS_MVP3 / nombre).read_bytes())
        assert (tabla.codificacion, tabla.deteccion.separador) == (codificacion, separador), nombre
        assert tabla.encabezado[0] == "nombre" and len(tabla.filas) >= 2


# --- Límites (CA-C02.8, CA-C02.9, CA-C15.*) -------------------------------------------------------


def test_exactamente_100_filas_se_aceptan_y_101_dan_e_m06_sin_cargar_nada():
    """CA-C15.1 / §13.10."""
    assert len(tabla_csv(["nombre"] + [f"m{i}" for i in range(100)]).filas) == 100
    e = _error(csv_bytes(["nombre"] + [f"m{i}" for i in range(101)]))
    assert e.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert e.params == {"tipo": "filas", "filas": "101", "max": "100"}


def test_el_error_de_filas_lleva_el_valor_real_aunque_sean_miles():
    e = _error(csv_bytes(["nombre"] + [f"m{i}" for i in range(3000)]))
    assert e.params["filas"] == "3000"


def test_el_encabezado_y_las_filas_vacias_no_cuentan_para_el_limite():
    """CA-C15.3."""
    lineas = ["nombre"] + [f"m{i}" for i in range(100)] + [""] * 200
    assert len(tabla_csv(lineas).filas) == 100


def test_el_limite_de_filas_es_max_lote_de_m2(monkeypatch):
    """CA-C15.2: cambiar ``MAX_LOTE`` cambia el límite del CSV."""
    from proxlaunch.nucleo.csv_importacion import lectura

    assert lectura.MAX_LOTE is constantes_lote.MAX_LOTE
    monkeypatch.setattr(lectura, "MAX_LOTE", 3)
    assert len(tabla_csv(["nombre", "a", "b", "c"]).filas) == 3
    assert _error(csv_bytes(["nombre", "a", "b", "c", "d"])).params["max"] == "3"


def test_60_columnas_se_aceptan_y_61_dan_e_m06_con_el_valor_real():
    # DT-A11 (fase A): el tope sube de 40 a 60 por las columnas nuevas.
    assert MAX_COLUMNAS_CSV == 60
    cabecera = ";".join(f"c{i}" for i in range(60))
    assert len(tabla_csv([cabecera, ";".join(["x"] * 60)]).encabezado) == 60
    cabecera61 = ";".join(f"c{i}" for i in range(61))
    e = _error(csv_bytes([cabecera61, ";".join(["x"] * 61)]))
    assert e.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert (
        e.params["tipo"] == "columnas" and e.params["columnas"] == "61" and e.params["max"] == "60"
    )


def test_celda_de_256_caracteres_se_acepta_y_de_257_da_e_m06_con_el_valor_real():
    assert MAX_LONG_CELDA == 256
    assert len(tabla_csv(["nombre", "x" * 256]).filas[0].celdas[0]) == 256
    e = _error(csv_bytes(["nombre", "x" * 257]))
    assert e.params["tipo"] == "celda" and e.params["celda"] == "257" and e.params["fila"] == "2"


def test_una_celda_gigante_dentro_del_limite_de_bytes_tambien_se_reporta_con_su_valor_real():
    e = _error(csv_bytes(["nombre", "x" * 900_000]))
    assert e.params["tipo"] == "celda" and e.params["celda"] == "900000"


def test_mas_de_1_mib_da_e_m01_demasiado_grande():
    e = _error(b"nombre\r\n" + b"a" * MAX_BYTES_CSV)
    assert e.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert e.params["motivo"] == "demasiado_grande" and e.params["limite"] == str(MAX_BYTES_CSV)


@pytest.mark.parametrize("datos", [b"", b"\xef\xbb\xbf", b"\r\n\r\n", b"  \r\n", b";;;\r\n;;\r\n"])
def test_archivo_vacio_o_sin_contenido_da_e_m09(datos):
    """CA-C02.9."""
    assert _error(datos).codigo == CodigoError.CSV_VACIO


@pytest.mark.parametrize(
    "datos",
    [b"nombre;cpu\r\n", b"nombre;cpu", b"sep=;\r\nnombre;cpu\r\n", b"nombre;cpu\r\n\r\n;;\r\n"],
)
def test_solo_encabezado_da_e_m09(datos):
    assert _error(datos).codigo == CodigoError.CSV_VACIO


def test_el_encabezado_es_la_primera_fila_no_vacia():
    tabla = leer_tabla(b"\r\n\r\nnombre;cpu\r\nweb;2\r\n")
    assert tabla.encabezado == ("nombre", "cpu") and tabla.filas[0].numero == 4


def test_nombre_con_espacios_se_lee_como_texto_sin_alterarlo():
    """§13.10: una columna con espacios en el nombre (la regla V-01 lo juzgará después)."""
    tabla = leer_tabla(b"nombre\r\nmi servidor web\r\n")
    assert tabla.filas[0].celdas == ("mi servidor web",)


# --- Archivo en disco (INV-M3, CA-C02.12) ---------------------------------------------------------


def test_leer_archivo_csv_lee_solo_y_no_modifica_el_archivo(tmp_path):
    ruta = tmp_path / "mi lista.csv"
    ruta.write_bytes("nombre;memoria\r\nweb;4\r\n".encode("cp1252"))
    antes = (hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_mtime_ns)
    assert leer_archivo_csv(ruta).filas[0].celdas == ("web", "4")
    assert (hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_mtime_ns) == antes
    assert [p.name for p in tmp_path.iterdir()] == ["mi lista.csv"]


@pytest.mark.parametrize("contenido", [b"", b"\x81\x8d", b"nombre;cpu\r\n", b"a\x00b", b'a;"b'])
def test_un_csv_rechazado_tampoco_se_modifica(tmp_path, contenido):
    ruta = tmp_path / "malo.csv"
    ruta.write_bytes(contenido)
    antes = (hashlib.sha256(contenido).hexdigest(), ruta.stat().st_mtime_ns)
    with pytest.raises(ErrorProxLaunch):
        leer_archivo_csv(ruta)
    assert (hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_mtime_ns) == antes
    assert [p.name for p in tmp_path.iterdir()] == ["malo.csv"]


def test_leer_archivo_csv_rechaza_por_tamano_sin_leer_el_contenido(tmp_path):
    ruta = tmp_path / "grande.csv"
    ruta.write_bytes(b"nombre\r\n" + b"a\r\n" * (MAX_BYTES_CSV // 3 + 10))
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_csv(ruta)
    assert exc.value.params["motivo"] == "demasiado_grande"


def test_leer_archivo_csv_de_un_directorio_es_e_m01(tmp_path):
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_csv(tmp_path)
    assert exc.value.params["motivo"] == "no_regular"
