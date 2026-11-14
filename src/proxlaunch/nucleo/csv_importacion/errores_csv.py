"""CSV de filas con error, reimportable (RF-C12).

Conserva las columnas originales (menos las de credenciales) de las filas con error y añade
``fila_original``, ``columna`` y ``problema``. Al reimportarlo, esas tres son columnas
desconocidas y se ignoran (CA-C12.3). El escritor único sanea toda celda de texto.
"""

from collections.abc import Callable
from pathlib import Path

from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv
from proxlaunch.nucleo.csv_importacion.columnas import normalizar_encabezado
from proxlaunch.nucleo.csv_importacion.modelos import (
    EstadoFila,
    ProblemaCelda,
    ResultadoImportacion,
    TablaCsv,
)
from proxlaunch.nucleo.validacion import Severidad

COLUMNAS_EXTRA = ("fila_original", "columna", "problema")
SEPARADOR_PROBLEMAS = " | "  # varios problemas de una fila en una sola celda


def filas_con_error(
    tabla: TablaCsv,
    resultado: ResultadoImportacion,
    traducir: Callable[[ProblemaCelda], str],
) -> tuple[list[str], list[list[str | int]]]:
    """Encabezado y filas del CSV de errores: una fila por fila original con error.

    ``columna`` y ``problema`` reúnen los problemas de severidad error de la fila (separados
    por `` | ``); ``traducir`` aporta el texto del problema.
    """
    credenciales = set(resultado.columnas.credenciales)
    extra = {normalizar_encabezado(c) for c in COLUMNAS_EXTRA}
    conservar = [
        i
        for i, titulo in enumerate(tabla.encabezado)
        if i not in credenciales and normalizar_encabezado(titulo) not in extra
    ]
    encabezado = [tabla.encabezado[i] for i in conservar] + list(COLUMNAS_EXTRA)
    originales = {f.numero: f.celdas for f in tabla.filas}
    filas: list[list[str | int]] = []
    for fila in resultado.filas:
        if fila.estado != EstadoFila.CON_ERROR:
            continue
        celdas = originales.get(fila.numero, ())
        errores = [p for p in fila.problemas if p.severidad == Severidad.ERROR]
        columnas = [p.columna for p in errores if p.columna]
        fila_csv: list[str | int] = [celdas[i] if i < len(celdas) else "" for i in conservar]
        fila_csv.append(fila.numero)
        fila_csv.append(SEPARADOR_PROBLEMAS.join(dict.fromkeys(columnas)))
        fila_csv.append(SEPARADOR_PROBLEMAS.join(traducir(p) for p in errores))
        filas.append(fila_csv)
    return encabezado, filas


def escribir_filas_con_error(
    ruta: Path,
    tabla: TablaCsv,
    resultado: ResultadoImportacion,
    traducir: Callable[[ProblemaCelda], str],
    *,
    separador: str = ";",
) -> None:
    """Escribe el CSV de errores (UTF-8 con BOM, atómico y saneado)."""
    encabezado, filas = filas_con_error(tabla, resultado, traducir)
    escribir_csv(ruta, encabezado, filas, separador=separador)
