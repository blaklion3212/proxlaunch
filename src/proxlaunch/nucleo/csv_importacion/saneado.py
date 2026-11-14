"""Saneado de textos del archivo antes de mostrarlos o guardarlos en mensajes."""

import unicodedata

from proxlaunch.nucleo.archivos.texto import es_formato_invisible

LONG_VALOR_MOSTRADO = 40  # CA-C05.1


def sin_control(texto: str) -> str:
    """Quita caracteres de control (``Cc``, incluidos tab y saltos) y de dirección de texto."""
    if texto.isascii() and texto.isprintable():
        return texto
    return "".join(
        c for c in texto if not es_formato_invisible(c) and unicodedata.category(c) != "Cc"
    )


def texto_visible(texto: str, maximo: int = LONG_VALOR_MOSTRADO) -> str:
    """Texto apto para mensajes: sin control ni bidi, recortado a ``maximo`` con «…»."""
    limpio = sin_control(texto).strip()
    if len(limpio) > maximo:
        return limpio[: maximo - 1] + "…"
    return limpio
