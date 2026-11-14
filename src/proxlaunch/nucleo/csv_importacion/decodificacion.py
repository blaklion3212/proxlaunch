"""Decodificación del CSV (RF-C02, CA-C02.1..C02.3).

Orden de detección: BOM UTF-8, BOM UTF-16 (LE/BE), UTF-8 estricto, Windows-1252 estricto.
ISO-8859-1 solo se usa si el usuario la elige (modo avanzado). Un byte nulo o el carácter
de sustitución U+FFFD nunca llegan al análisis (E-M07).
"""

import codecs
import re

from proxlaunch.nucleo.csv_importacion.modelos import Codificacion
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

_SALTO_LINEA = re.compile(rb"\r\n|\n|\r")
_BOM_UTF8 = codecs.BOM_UTF8
_BOMS_UTF16 = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)


def _fila_aproximada(datos: bytes, posicion: int) -> int:
    """Número de fila (base 1) del byte ``posicion``: saltos de línea anteriores + 1."""
    return len(_SALTO_LINEA.findall(datos, 0, max(posicion, 0))) + 1


def _error(motivo: str, fila: int) -> ErrorProxLaunch:
    return ErrorProxLaunch(CodigoError.CSV_CODIFICACION, {"fila": str(fila), "motivo": motivo})


def _decodificar_con(datos: bytes, codificacion: Codificacion) -> str:
    try:
        return datos.decode(codificacion.value, "strict")
    except UnicodeDecodeError as e:
        raise _error("codificacion", _fila_aproximada(datos, e.start)) from None


def _verificar(texto: str) -> None:
    """E-M07 por nulos (``nulo``) o caracteres de sustitución (``sustitucion``)."""
    pos = texto.find("\x00")
    if pos >= 0:
        raise _error("nulo", texto.count("\n", 0, pos) + 1)
    pos = texto.find("�")
    if pos >= 0:
        raise _error("sustitucion", texto.count("\n", 0, pos) + 1)


def decodificar(datos: bytes, forzada: Codificacion | None = None) -> tuple[str, Codificacion]:
    """Convierte los bytes en texto y devuelve la codificación usada.

    ``forzada`` (modo avanzado) salta la detección. Lanza ``ErrorProxLaunch`` ``CSV_CODIFICACION``
    (E-M07, ``fila`` y ``motivo``: ``codificacion``, ``nulo`` o ``sustitucion``).
    """
    if forzada is not None:
        usada = forzada
        texto = _decodificar_con(datos, usada)
    elif datos.startswith(_BOM_UTF8):
        usada = Codificacion.UTF8_BOM
        texto = _decodificar_con(datos, usada)
    elif datos.startswith(_BOMS_UTF16):
        usada = Codificacion.UTF16
        texto = _decodificar_con(datos, usada)
    else:
        try:
            texto = datos.decode("utf-8", "strict")
            usada = Codificacion.UTF8
        except UnicodeDecodeError:
            usada = Codificacion.WINDOWS_1252
            texto = _decodificar_con(datos, usada)
    _verificar(texto)
    return texto, usada
