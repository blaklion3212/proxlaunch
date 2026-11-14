"""Lectura del CSV a una tabla de texto con límites (RF-C02, RF-C15).

RFC 4180 con ``csv.reader`` en modo estricto. Las celdas son solo texto: nada se evalúa.
La numeración de filas es la de Excel (cada registro cuenta una fila, también los vacíos;
una línea ``sep=;`` inicial no se cuenta). Los límites nunca recortan en silencio: lanzan
``ErrorProxLaunch`` ``ARCHIVO_DEMASIADAS_FILAS`` (E-M06) con el valor real.
"""

import csv
import re
from collections.abc import Iterator
from pathlib import Path

from proxlaunch.nucleo.archivos.constantes import (
    MAX_BYTES_CSV,
    MAX_COLUMNAS_CSV,
    MAX_LONG_CELDA,
)
from proxlaunch.nucleo.archivos.lector import leer_archivo_limitado
from proxlaunch.nucleo.csv_importacion.decodificacion import decodificar
from proxlaunch.nucleo.csv_importacion.modelos import (
    DeteccionSeparador,
    FilaCsv,
    OpcionesCsv,
    TablaCsv,
)
from proxlaunch.nucleo.csv_importacion.separador import detectar_separador, linea_sep
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import MAX_LOTE

# El límite por defecto de ``csv`` (128 KiB por campo) saltaría antes que MAX_LONG_CELDA y
# ocultaría el valor real. Solo se sube (nunca se baja): es inocuo para el resto del proceso.
if csv.field_size_limit() < MAX_BYTES_CSV + 1:
    csv.field_size_limit(MAX_BYTES_CSV + 1)

OPCIONES_AUTOMATICAS = OpcionesCsv()  # detectar codificación y separador


def _demasiado(tipo: str, valor: int, maximo: int, fila: int | None = None) -> ErrorProxLaunch:
    """E-M06: ``tipo`` (``filas``, ``columnas`` o ``celda``), el valor real en la clave del tipo."""
    params = {"tipo": tipo, tipo: str(valor), "max": str(maximo)}
    if fila is not None:
        params["fila"] = str(fila)
    return ErrorProxLaunch(CodigoError.ARCHIVO_DEMASIADAS_FILAS, params)


def _recortar_cola(celdas: list[str]) -> tuple[str, ...]:
    """Quita las celdas vacías del final (Excel suele arrastrar separadores sobrantes)."""
    fin = len(celdas)
    while fin and not celdas[fin - 1].strip():
        fin -= 1
    return tuple(celdas[:fin])


_LINEA = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+")


def _lineas(texto: str) -> Iterator[str]:
    """Líneas con su terminador (``\\n``, ``\\r`` o ``\\r\\n``), como ``StringIO(newline="")``.

    Genera una a una, sin duplicar el texto completo en memoria (RNF de rendimiento).
    """
    for m in _LINEA.finditer(texto):
        yield m.group()


def leer_tabla(datos: bytes, opciones: OpcionesCsv = OPCIONES_AUTOMATICAS) -> TablaCsv:
    """Decodifica, detecta el separador y lee la tabla.

    Errores (todos ``ErrorProxLaunch``): E-M01 (más de ``MAX_BYTES_CSV``), E-M07 (codificación,
    nulos, comillas sin cerrar), E-M06 (más de ``MAX_COLUMNAS_CSV`` columnas, celda de más de
    ``MAX_LONG_CELDA`` caracteres o más de ``MAX_LOTE`` filas de datos) y E-M09 (sin filas de
    datos). El encabezado es la primera fila no vacía.
    """
    if len(datos) > MAX_BYTES_CSV:
        raise ErrorProxLaunch(
            CodigoError.ARCHIVO_NO_PERMITIDO,
            {
                "motivo": "demasiado_grande",
                "limite": str(MAX_BYTES_CSV),
                "tamano": str(len(datos)),
            },
        )
    texto, codificacion = decodificar(datos, opciones.codificacion)
    texto = texto.removeprefix("﻿")
    deteccion = detectar_separador(texto)
    if opciones.separador is not None:
        if len(opciones.separador) != 1 or opciones.separador in '"\r\n':
            raise ValueError("el separador debe ser un único carácter")
        deteccion = DeteccionSeparador(
            opciones.separador, False, deteccion.candidatos, deteccion.linea_sep
        )
    if deteccion.linea_sep:
        explicita = linea_sep(texto)
        if explicita is not None:
            texto = texto[explicita[1] :]

    lector = csv.reader(_lineas(texto), delimiter=deteccion.separador, strict=True)
    encabezado: tuple[str, ...] | None = None
    filas: list[FilaCsv] = []
    n_filas = 0
    numero = 0
    while True:
        numero += 1  # fila (Excel) que se intenta leer
        try:
            registro = next(lector)
        except StopIteration:
            break
        except csv.Error:
            raise ErrorProxLaunch(
                CodigoError.CSV_CODIFICACION, {"fila": str(numero), "motivo": "comillas"}
            ) from None
        celdas = _recortar_cola(registro)
        if not celdas:
            continue  # fila vacía: no cuenta (CA-C02.8, CA-C15.3)
        if len(celdas) > MAX_COLUMNAS_CSV:
            raise _demasiado("columnas", len(celdas), MAX_COLUMNAS_CSV, numero)
        for c in celdas:
            if len(c) > MAX_LONG_CELDA:
                raise _demasiado("celda", len(c), MAX_LONG_CELDA, numero)
        if encabezado is None:
            encabezado = tuple(c.strip().lstrip("﻿").strip() for c in celdas)
            continue
        n_filas += 1  # se sigue contando aunque pase el límite, sin guardar las filas
        if n_filas <= MAX_LOTE:
            filas.append(FilaCsv(numero, celdas))
    if n_filas > MAX_LOTE:
        raise _demasiado("filas", n_filas, MAX_LOTE)
    if encabezado is None or not filas:
        raise ErrorProxLaunch(CodigoError.CSV_VACIO)
    return TablaCsv(codificacion, deteccion, encabezado, tuple(filas))


def leer_archivo_csv(ruta: Path, opciones: OpcionesCsv = OPCIONES_AUTOMATICAS) -> TablaCsv:
    """Lee el archivo (solo lectura, ≤ ``MAX_BYTES_CSV``) y lo convierte en ``TablaCsv``."""
    return leer_tabla(leer_archivo_limitado(ruta, MAX_BYTES_CSV), opciones)
