"""Detección del separador de campos (RF-C02, CA-C02.4..C02.6)."""

import csv
import io
import re
from collections import Counter

from proxlaunch.nucleo.archivos.constantes import LINEAS_DETECCION
from proxlaunch.nucleo.csv_importacion.modelos import DeteccionSeparador

CANDIDATOS = (";", ",", "\t")  # orden de preferencia ante un empate

_LINEA_SEP = re.compile(r"sep=([^\w\"'\r\n])[ \t]*(?:\r\n|\n|\r|$)", re.IGNORECASE)
_DECIMAL_COMA = re.compile(r"[0-9],[0-9]")


def linea_sep(texto: str) -> tuple[str, int] | None:
    """Si la primera línea es ``sep=X`` (convención de Excel): ``(X, longitud de la línea)``."""
    m = _LINEA_SEP.match(texto)
    return (m.group(1), m.end()) if m else None


def _muestra(texto: str) -> str:
    """Primeras ``LINEAS_DETECCION`` líneas físicas, sin copiar el texto completo."""
    fin = 0
    for _ in range(LINEAS_DETECCION):
        i = texto.find("\n", fin)
        if i < 0:
            return texto
        fin = i + 1
    return texto[:fin]


def _puntaje(muestra: str, separador: str) -> int:
    """Líneas que comparten el número de columnas (≥ 2) más frecuente con este separador."""
    cuentas: Counter[int] = Counter()
    try:
        for registro in csv.reader(io.StringIO(muestra, newline=""), delimiter=separador):
            if len(registro) >= 2:
                cuentas[len(registro)] += 1
    except csv.Error:
        pass  # la muestra puede cortar un campo entre comillas: se usa lo leído hasta ahí
    return max(cuentas.values(), default=0)


def detectar_separador(texto: str) -> DeteccionSeparador:
    """Detecta ``;``, ``,`` o tabulador.

    Una primera línea ``sep=X`` manda y se omite. Si no, gana el separador que da el mismo
    número de columnas (≥ 2) en más líneas de las primeras 20; en un empate gana ``;`` si
    aparece un decimal con coma y, si no, gana ``,`` y el resultado es ambiguo (``ambiguo=True``,
    ``candidatos`` = los empatados). Sin ninguna candidata con ≥ 2 columnas (una sola columna)
    devuelve ``;`` sin ambigüedad ni candidatos.
    """
    texto = texto.removeprefix("﻿")
    explicita = linea_sep(texto)
    if explicita is not None:
        return DeteccionSeparador(explicita[0], False, (explicita[0],), True)
    muestra = _muestra(texto)
    puntajes = {s: _puntaje(muestra, s) for s in CANDIDATOS}
    mejor = max(puntajes.values())
    if mejor == 0:
        return DeteccionSeparador(";", False, (), False)
    empatados = tuple(s for s in CANDIDATOS if puntajes[s] == mejor)
    if len(empatados) == 1:
        return DeteccionSeparador(empatados[0], False, empatados, False)
    if ";" in empatados and _DECIMAL_COMA.search(muestra):
        return DeteccionSeparador(";", False, empatados, False)
    # CA-C02.4: ante un empate sin decimal con coma se elige ',' (ambiguo).
    elegido = "," if "," in empatados else empatados[0]
    return DeteccionSeparador(elegido, True, empatados, False)
