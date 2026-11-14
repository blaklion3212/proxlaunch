"""Escritor ÚNICO de CSV (RF-C11): neutraliza fórmulas y elimina caracteres peligrosos.

Ningún otro módulo debe usar ``csv.writer``. UTF-8 con BOM, ``\\r\\n``, ``QUOTE_ALL``.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path

from proxlaunch.nucleo.archivos.escritura import escribir_atomico
from proxlaunch.nucleo.archivos.texto import es_formato_invisible

# Primer carácter que Excel/LibreOffice podrían tratar como inicio de fórmula.
DISPARADORES: frozenset[str] = frozenset({"=", "+", "-", "@", "\t", "\r"})
_CONTROL_DE_RETORNO = frozenset({"\t", "\r", "\n"})
_SALTABLES = frozenset({" ", '"', "'"})  # se ignoran al buscar el primer carácter significativo
_SEPARADORES_VALIDOS = frozenset({";", ",", "\t", "|"})
# Tras estos caracteres Excel/LibreOffice pueden tratar lo siguiente como celda nueva (S2).
_INICIO_DE_SEGMENTO = frozenset({",", ";", "|", "\t"})


def _eliminable(c: str) -> bool:
    return es_formato_invisible(c) or unicodedata.category(c) in ("Cc", "Cs")


def _primer_significativo(texto: str) -> str:
    """Primer carácter que no es espacio, comilla ni apóstrofe ('' si no hay)."""
    for c in texto:
        if c in _SALTABLES or (c.isspace() and c not in _CONTROL_DE_RETORNO):
            continue
        return c
    return ""


def sanear_celda(valor: str) -> str:
    """Texto seguro para una celda: sin control ni formato invisible y sin fórmula activa.

    Elimina los caracteres ``Cc`` (incluidos ``\\t\\r\\n``), ``Cs`` y de formato invisible
    (``Cf``). Si el primer carácter significativo (tras espacios, comillas y apóstrofes) es un
    disparador, o era un ``\\t``/``\\r``/``\\n`` eliminado, antepone ``'`` (CA-C11.1/C11.2/C11.7).
    Lo mismo se hace con cada segmento que siga a ``,`` ``;`` ``|`` o a un ``\\t``/``\\r``/``\\n``
    eliminado dentro de la celda (S2): ``"a;=1+1"`` queda ``"a;'=1+1"``.
    """
    salida: list[str] = []
    inicio_segmento = 0  # posición en ``salida`` donde empieza el segmento actual
    pendiente = True  # aún no se vio el primer carácter significativo del segmento
    prefijar_inicio = _primer_significativo(valor) in _CONTROL_DE_RETORNO
    for c in valor:
        if _eliminable(c):
            if c in _CONTROL_DE_RETORNO:  # el control eliminado separaba dos segmentos
                inicio_segmento = len(salida)
                pendiente = True
            continue
        if pendiente and not (c in _SALTABLES or c.isspace()):
            pendiente = False
            if c in DISPARADORES:
                salida.insert(inicio_segmento, "'")
                if inicio_segmento == 0:
                    prefijar_inicio = False  # ya lleva su apóstrofe inicial
        salida.append(c)
        if c in _INICIO_DE_SEGMENTO:
            inicio_segmento = len(salida)
            pendiente = True
    if prefijar_inicio:
        salida.insert(0, "'")
    return "".join(salida)


def _celda(valor: object) -> str:
    # ``bool`` es subclase de ``int``: se rechaza explícitamente (fallo de programación).
    if isinstance(valor, bool):
        raise TypeError("Las celdas CSV solo admiten str o int")
    if isinstance(valor, int):
        # Enteros no negativos tal cual (CA-C11.3); los negativos van como texto saneado.
        return str(valor) if valor >= 0 else sanear_celda(str(valor))
    if isinstance(valor, str):
        return sanear_celda(valor)
    raise TypeError("Las celdas CSV solo admiten str o int")


def texto_csv(
    encabezado: Sequence[str],
    filas: Iterable[Sequence[str | int]],
    *,
    separador: str = ";",
) -> bytes:
    """CSV completo en bytes (UTF-8 con BOM, CRLF), con todas las celdas saneadas."""
    if len(separador) != 1 or separador not in _SEPARADORES_VALIDOS:
        raise ValueError("Separador CSV no admitido")
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=separador, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    escritor.writerow([_celda(c) for c in encabezado])
    for fila in filas:
        escritor.writerow([_celda(c) for c in fila])
    return salida.getvalue().encode("utf-8-sig")


def escribir_csv(
    ruta: Path,
    encabezado: Sequence[str],
    filas: Iterable[Sequence[str | int]],
    *,
    separador: str = ";",
) -> None:
    """Escribe el CSV de forma atómica en ``ruta`` (E/S)."""
    escribir_atomico(ruta, texto_csv(encabezado, filas, separador=separador))
