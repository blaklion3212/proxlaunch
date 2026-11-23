"""Fase A (0.6.0): límites de lectura del CSV, columna ``notas`` y plantilla descargable.

Cubre CA-A2.6.1, CA-A7.3.6, CA-A7.3.7, CA-A7.3.10, CL-A9 y RNF-A4 (lectura). Es independiente de la
interpretación (``test_fase_a_csv.py``).
"""

import time

import pytest

from proxlaunch.nucleo.archivos.constantes import (
    MAX_BYTES_CSV,
    MAX_COLUMNAS_CSV,
    MAX_LONG_CELDA,
    MAX_LONG_NOTAS,
)
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo as Aviso
from proxlaunch.nucleo.csv_importacion.columnas import COLUMNAS, resolver_columnas
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv, leer_tabla
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila
from proxlaunch.nucleo.csv_importacion.plantilla import (
    ENCABEZADO_PLANTILLA,
    SEPARADORES_PLANTILLA,
    escribir_plantilla,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica

from .apoyo_mvp3 import csv_bytes, importar_csv, perfil_base


def _error(datos: bytes, **kw) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(datos, **kw)
    return exc.value


# --- CA-A7.3.6: tope de columnas --------------------------------------------------------------


def test_ca_a7_3_6_el_tope_de_columnas_es_70():
    assert MAX_COLUMNAS_CSV == 70  # P-C4 (fase C): sube de 60 a 70


def test_ca_a7_3_6_todas_las_columnas_conocidas_caben_en_el_tope():
    assert len(COLUMNAS) <= MAX_COLUMNAS_CSV
    encabezado = [c.canonica for c in COLUMNAS]
    fila = ["x"] * len(encabezado)
    tabla = leer_tabla(csv_bytes([";".join(encabezado), ";".join(fila)]))
    assert len(tabla.encabezado) == len(COLUMNAS)
    mapa, _ = resolver_columnas(tabla.encabezado)
    assert set(mapa.posiciones) == {c.canonica for c in COLUMNAS}


@pytest.mark.parametrize("n", [40, 41, 50, 70])
def test_ca_a7_3_6_un_csv_valido_con_mas_de_40_columnas_no_se_rechaza(n):
    encabezado = ["nombre"] + [f"extra{i}" for i in range(n - 1)]
    tabla = leer_tabla(csv_bytes([";".join(encabezado), ";".join(["a"] * n)]))
    assert len(tabla.encabezado) == n


def test_ca_a7_3_6_con_71_columnas_el_error_lleva_el_valor_real_y_el_tope():
    encabezado = ["nombre"] + [f"extra{i}" for i in range(70)]
    e = _error(csv_bytes([";".join(encabezado), ";".join(["a"] * 71)]))
    assert e.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert e.params["tipo"] == "columnas"
    assert e.params["columnas"] == "71"
    assert e.params["max"] == "70"


def test_ca_a7_3_6_un_csv_con_todas_las_columnas_nuevas_y_los_antiguos_se_interpreta():
    nuevas = ["encender", "arranque_auto", "notas", "etiquetas", "pool", "proteger", "mtu"]
    r = importar_csv(
        [
            ";".join(["nombre", "cpu", "memoria", *nuevas, "limite_red"]),
            ";".join(["a", "2", "4 GiB", "si", "si", "hola", "web", "p1", "no", "1500", "50"]),
        ]  # fmt: skip
    )
    f = r.filas[0]
    assert f.estado == EstadoFila.CORRECTA
    assert f.opciones.pool == "p1" and f.cfg.redes[0].limite_mb == 50.0


# --- CA-A7.3.7 / CA-A2.6.1: límite de celda por columna ---------------------------------------


def test_ca_a7_3_7_notas_de_300_caracteres_se_aceptan_aunque_superen_la_celda_normal():
    assert MAX_LONG_CELDA == 256 and MAX_LONG_NOTAS == 8192
    tabla = leer_tabla(csv_bytes(["nombre;notas", f"a;{'n' * 300}"]))
    assert len(tabla.filas[0].celdas[1]) == 300


@pytest.mark.parametrize("largo", [256, 257, 1000, 7500, 8191, 8192])
def test_ca_a7_3_7_notas_acepta_hasta_8192(largo):
    tabla = leer_tabla(csv_bytes(["nombre;notas", f"a;{'n' * largo}"]))
    assert len(tabla.filas[0].celdas[1]) == largo


@pytest.mark.parametrize("largo", [8193, 10000])
def test_ca_a7_3_7_notas_de_mas_de_8192_se_rechaza_con_el_valor_real(largo):
    e = _error(csv_bytes(["nombre;notas", f"a;{'n' * largo}"]))
    assert e.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert e.params["tipo"] == "celda"
    assert e.params["celda"] == str(largo)
    assert e.params["max"] == "8192"
    assert e.params["fila"] == "2"


@pytest.mark.parametrize("columna", ["nombre", "pool", "etiquetas", "perfil", "fuente", "red"])
def test_ca_a7_3_7_las_demas_columnas_conservan_el_limite_de_256(columna):
    ok = leer_tabla(csv_bytes([f"nombre;{columna}", f"a;{'x' * 256}"]) if columna != "nombre"
                    else csv_bytes(["nombre;cpu", f"{'x' * 256};2"]))  # fmt: skip
    assert ok.filas
    datos = (
        csv_bytes([f"nombre;{columna}", f"a;{'x' * 257}"])
        if columna != "nombre"
        else csv_bytes(["nombre;cpu", f"{'x' * 257};2"])
    )
    e = _error(datos)
    assert e.params["tipo"] == "celda" and e.params["max"] == "256"


@pytest.mark.parametrize("alias", ["notes", "NOTAS", "Notas", " notas "])
def test_ca_a7_3_7_el_limite_ampliado_se_aplica_tambien_a_los_alias_y_variantes_del_encabezado(
    alias,
):
    tabla = leer_tabla(csv_bytes([f"nombre;{alias}", f"a;{'n' * 400}"]))
    assert len(tabla.filas[0].celdas[1]) == 400


def test_ca_a7_3_7_un_alias_traducido_pasado_por_la_interfaz_tambien_amplia_el_limite():
    datos = csv_bytes(["nombre;comentarios", f"a;{'n' * 400}"])
    tabla = leer_tabla(datos, alias_extra={"comentarios": "notas"})
    assert len(tabla.filas[0].celdas[1]) == 400
    assert _error(datos).params["max"] == "256"  # sin el alias, es una columna desconocida


def test_ca_a7_3_7_el_encabezado_nunca_se_amplia():
    e = _error(csv_bytes([f"nombre;{'n' * 300}", "a;b"]), alias_extra={"n" * 300: "notas"})
    assert e.params["tipo"] == "celda" and e.params["max"] == "256"


def test_ca_a7_3_7_el_limite_amplio_es_de_la_columna_y_no_de_la_fila():
    datos = csv_bytes(["nombre;notas;pool", f"a;{'n' * 400};{'p' * 300}"])
    e = _error(datos)
    assert e.params["tipo"] == "celda" and e.params["celda"] == "300" and e.params["max"] == "256"


def test_ca_a2_6_1_notas_largas_con_saltos_de_linea_dentro_de_comillas_cuentan_por_caracteres():
    cuerpo = ("linea\n" * 1000)[:6000]
    tabla = leer_tabla(csv_bytes(["nombre;notas", f'a;"{cuerpo}"']))
    assert tabla.filas[0].celdas[1] == cuerpo


# --- CL-A9 y tamaño del archivo ---------------------------------------------------------------


def test_cl_a9_cien_filas_con_notas_de_7500_caracteres_caben_en_el_csv_y_se_leen_rapido():
    lineas = ["nombre;notas;etiquetas"] + [f"vm-{i:03d};{'n' * 7500};web,prod" for i in range(100)]
    datos = csv_bytes(lineas)
    assert 700_000 < len(datos) < MAX_BYTES_CSV
    t0 = time.perf_counter()
    r = importar_csv(lineas)
    assert time.perf_counter() - t0 < 10
    assert len(r.filas) == 100
    # 7500 caracteres alcanzan el umbral de aviso (V-A08) sin llegar a error (CL-A7)
    assert all(f.estado == EstadoFila.CON_AVISO for f in r.filas)
    assert {p.regla for f in r.filas for p in f.problemas} == {"V-A08"}
    assert all(len(f.opciones.notas) == 7500 for f in r.filas)


def test_cl_a9_un_csv_de_mas_de_1_mib_se_rechaza_con_error_de_tamano():
    lineas = ["nombre;notas"] + [f"vm-{i:03d};{'n' * 8192}" for i in range(140)]
    e = _error(csv_bytes(lineas))
    assert e.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert e.params["motivo"] == "demasiado_grande"
    assert e.params["limite"] == str(MAX_BYTES_CSV)


def test_cl_a9_leer_archivo_csv_aplica_los_mismos_limites(tmp_path):
    ruta = tmp_path / "notas.csv"
    ruta.write_bytes(csv_bytes(["nombre;notas", f"a;{'n' * 5000}"]))
    assert len(leer_archivo_csv(ruta).filas[0].celdas[1]) == 5000
    ruta.write_bytes(csv_bytes(["nombre;notas", f"a;{'n' * 9000}"]))
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_csv(ruta)
    assert exc.value.params["max"] == "8192"


# --- CA-A7.3.10: plantilla descargable --------------------------------------------------------


NUEVAS = (
    "encender",
    "arranque_auto",
    "notas",
    "etiquetas",
    "pool",
    "proteger",
    "mtu",
    "limite_red",
)


def test_ca_a7_3_10_la_plantilla_incluye_las_columnas_nuevas():
    for c in NUEVAS:
        assert c in ENCABEZADO_PLANTILLA
    assert len(ENCABEZADO_PLANTILLA) <= MAX_COLUMNAS_CSV


@pytest.mark.parametrize("separador", SEPARADORES_PLANTILLA)
def test_ca_a7_3_10_la_plantilla_se_lee_y_pasa_su_propia_validacion(tmp_path, separador):
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta, separador=separador)
    tabla = leer_archivo_csv(ruta)
    assert set(NUEVAS) <= set(tabla.encabezado)
    perfiles = tuple(perfiles_fabrica())
    resultado = interpretar(
        tabla, perfil_base=perfil_base(), perfiles=perfiles, inv=None, nodo_referencia=None
    )
    assert Aviso.COLUMNA_NO_USADA not in {a.codigo for a in resultado.avisos}
    # solo el aviso V-M11 de los nombres «ejemplo-»: ningún error ni problema de las columnas nuevas
    assert all(f.estado != EstadoFila.CON_ERROR for f in resultado.filas)
    assert {p.regla for f in resultado.filas for p in f.problemas} == {"V-M11"}


def test_ca_a7_3_10_la_plantilla_tiene_ejemplos_de_las_columnas_nuevas(tmp_path):
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta)
    tabla = leer_archivo_csv(ruta)
    r = interpretar(
        tabla, perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()), inv=None,
        nodo_referencia=None,
    )  # fmt: skip
    filas = list(r.filas)
    assert any(f.opciones is not None and f.opciones.encender is not None for f in filas)
    assert any(f.opciones is not None and f.opciones.etiquetas_usuario for f in filas)
    assert any(f.opciones is not None and f.opciones.notas for f in filas)
    assert any(f.cfg.redes[0].limite_mb is not None for f in filas)


def test_ca_a7_3_10_la_plantilla_no_empieza_ninguna_celda_con_disparador_de_formula(tmp_path):
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta)
    for linea in ruta.read_text("utf-8-sig").splitlines():
        for celda in linea.split(";"):
            assert not celda.startswith(("=", "+", "@")), celda
