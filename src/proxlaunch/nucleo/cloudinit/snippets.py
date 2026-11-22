"""Formato de los identificadores de snippets (RF-B4.3, V-B54). Módulo hoja y puro."""

from __future__ import annotations

import re
from typing import Final

# ``almacén:snippets/archivo``: sin coma, espacios, controles, ``=`` ni subcarpetas.
RE_VOLID_SNIPPET: Final = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*:snippets/[^/,=\s\x00-\x1f\x7f]+")
MAX_VOLID: Final = 256


def volid_snippet_valido(texto: object) -> bool:
    """¿Tiene el formato ``almacén:snippets/archivo``, sin ``..`` y de longitud razonable?"""
    return (
        isinstance(texto, str)
        and len(texto) <= MAX_VOLID
        and ".." not in texto
        and RE_VOLID_SNIPPET.fullmatch(texto) is not None
    )


def nombre_de_snippet(volid: str) -> str:
    """Parte del volid tras ``snippets/`` (``""`` si no tiene esa forma)."""
    _, separador, nombre = volid.partition(":snippets/")
    return nombre if separador else ""
