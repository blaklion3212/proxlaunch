"""Rendimiento y memoria de la importación CSV (RNF-M05, RNF-M02, CA-C02.11, CA-C05.10).

Un CSV de 1 MiB / 100 filas (lectura limitada, decodificación, análisis e interpretación con
validación de capa 1 y de vista previa contra el servidor) cuesta ≤ 1 s de CPU, y la memoria pico
del análisis es ≤ 5 × el tamaño del archivo. El tiempo se mide con ``time.process_time`` (CPU, no
reloj de pared) y se toma el mejor de varios intentos para no depender de la carga de la máquina.
"""

import time
import tracemalloc

import pytest

from proxlaunch.nucleo.archivos.constantes import MAX_BYTES_CSV, MAX_COLUMNAS_CSV, MAX_LONG_CELDA
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv, leer_tabla
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica

from .apoyo_lote import inventario, nodo, storage
from .apoyo_mvp3 import csv_bytes, perfil_base

UMBRAL_CPU_S = 1.0
UMBRAL_MEMORIA = 5


def _csv_de_1_mib(filas: int = 100, *, con_errores: bool = False) -> bytes:
    """100 filas de datos con 60 columnas (50 desconocidas de 150 caracteres) y, hasta llegar a
    ~1 MiB, filas vacías de solo separadores (se ignoran y no cuentan para el límite, CA-C02.8)."""
    conocidas = [
        "nombre",
        "perfil",
        "cpu",
        "memoria",
        "disco",
        "almacenamiento",
        "red",
        "vlan",
        "nodo",
        "vmid",
    ]
    extras = [f"columna-extra-{i:02d}" for i in range(MAX_COLUMNAS_CSV - len(conocidas))]
    lineas = [";".join(conocidas + extras)]
    ancho = min(MAX_LONG_CELDA, 150)  # con 60 columnas (fase A) 250 superaría el MiB
    for i in range(filas):
        nombre = f"mal nombre {i}" if con_errores else f"maquina-{i:03d}"
        cpu = "0" if con_errores else str(1 + i % 4)
        base = [
            nombre,
            "servidor-mediano",
            cpu,
            f"{2 + i % 6} GiB",
            str(10 + i),
            "datos",
            "vmbr0",
            "",
            "",
            str(1000 + i),
        ]
        lineas.append(";".join(base + [("x" * ancho) for _ in extras]))
    vacia = ";" * (MAX_COLUMNAS_CSV - 1)
    tamano = sum(len(x) + 2 for x in lineas) + 3
    lineas += [vacia] * ((MAX_BYTES_CSV - 2000 - tamano) // (len(vacia) + 2))
    datos = csv_bytes(lineas, bom=True)
    assert 1_000_000 <= len(datos) <= MAX_BYTES_CSV, len(datos)
    return datos


@pytest.fixture(scope="module")
def inv():
    return inventario(
        (nodo("pve1"), nodo("pve2"), nodo("pve3")),
        storages={n: (storage("datos", libre_gib=2000),) for n in ("pve1", "pve2", "pve3")},
    )


def _analizar(datos: bytes, inv_, tmp=None):
    tabla = leer_tabla(datos)
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=inv_,
        nodo_referencia="pve1",
    )
    return tabla, resultado


def _mejor_cpu(funcion, intentos: int = 3) -> float:
    mejor = float("inf")
    for _ in range(intentos):
        inicio = time.process_time()
        funcion()
        mejor = min(mejor, time.process_time() - inicio)
    return mejor


def test_el_csv_de_prueba_ocupa_casi_1_mib_y_tiene_100_filas_validas(inv):
    datos = _csv_de_1_mib()
    tabla, resultado = _analizar(datos, inv)
    assert len(tabla.filas) == 100 and len(tabla.encabezado) == MAX_COLUMNAS_CSV
    assert len(resultado.numeros_validos) == 100, [
        f.problemas for f in resultado.filas if f.problemas
    ][:2]


@pytest.mark.parametrize("con_inventario", [False, True], ids=["solo_capa_1", "con_vista_previa"])
def test_leer_e_interpretar_1_mib_100_filas_cuesta_menos_de_1_s_de_cpu(inv, con_inventario):
    datos = _csv_de_1_mib()
    segundos = _mejor_cpu(lambda: _analizar(datos, inv if con_inventario else None))
    assert segundos < UMBRAL_CPU_S, f"{segundos:.3f} s de CPU"


def test_con_el_100_por_ciento_de_las_filas_con_error_tambien_cabe_en_el_presupuesto(inv):
    """CA-C05.10."""
    datos = _csv_de_1_mib(con_errores=True)
    segundos = _mejor_cpu(lambda: _analizar(datos, inv))
    _, resultado = _analizar(datos, inv)
    assert all(f.problemas for f in resultado.filas) and resultado.numeros_validos == ()
    assert segundos < UMBRAL_CPU_S, f"{segundos:.3f} s de CPU"


def test_construir_las_filas_del_lote_de_100_filas_es_rapido(inv):
    _, resultado = _analizar(_csv_de_1_mib(), inv)
    segundos = _mejor_cpu(lambda: filas_lote(resultado, resultado.numeros_validos))
    assert segundos < 0.5


def test_la_memoria_pico_del_analisis_es_menos_de_5_veces_el_tamano_del_archivo(tmp_path, inv):
    """RNF-M02 / arquitectura §10: ``tracemalloc`` sobre el máximo (lectura limitada + análisis +
    interpretación), «sin copias intermedias del texto»."""
    datos = _csv_de_1_mib()
    ruta = tmp_path / "grande.csv"
    ruta.write_bytes(datos)
    tracemalloc.start()
    try:
        tabla = leer_archivo_csv(ruta)
        interpretar(
            tabla,
            perfil_base=perfil_base(),
            perfiles=perfiles_fabrica(),
            inv=inv,
            nodo_referencia="pve1",
        )
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert pico <= UMBRAL_MEMORIA * len(datos), f"{pico / len(datos):.1f} × el tamaño"


def test_un_csv_con_miles_de_filas_sobrantes_se_rechaza_sin_guardarlas_en_memoria():
    """CA-C02.8: se cuentan todas las filas sin conservarlas (``tracemalloc``)."""
    base = "nombre;cpu;memoria\r\n"
    cuerpo = "".join(f"maquina-{i};2;4\r\n" for i in range(40_000))
    datos = (base + cuerpo).encode()
    assert len(datos) < MAX_BYTES_CSV
    tracemalloc.start()
    try:
        with pytest.raises(Exception) as exc:
            leer_tabla(datos)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert getattr(exc.value, "params", {}).get("filas") == "40000"
    # Guardar las 40 000 filas costaría ~10 MB (> 13 × el archivo); aquí solo hay texto + lector.
    assert pico <= 6 * len(datos), f"{pico / len(datos):.1f} × el tamaño"
