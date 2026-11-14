"""Saneado de textos del archivo antes de mostrarlos o guardarlos en mensajes."""

import unicodedata

LONG_VALOR_MOSTRADO = 40  # CA-C05.1

# Marcas de dirección de texto (categoría Cf): se quitan además de los caracteres de control.
_BIDI = frozenset("‪‫‬‭‮⁦⁧⁨⁩‎‏؜​‌‍﻿")


def sin_control(texto: str) -> str:
    """Quita caracteres de control (``Cc``, incluidos tab y saltos) y de dirección de texto."""
    if texto.isascii() and texto.isprintable():
        return texto
    return "".join(c for c in texto if c not in _BIDI and unicodedata.category(c) != "Cc")


def texto_visible(texto: str, maximo: int = LONG_VALOR_MOSTRADO) -> str:
    """Texto apto para mensajes: sin control ni bidi, recortado a ``maximo`` con «…»."""
    limpio = sin_control(texto).strip()
    if len(limpio) > maximo:
        return limpio[: maximo - 1] + "…"
    return limpio
