"""Tokens de color por tema (único lugar del proyecto con códigos de color).

Paleta aprobada (D-02): naranja ``#E57000`` para acciones, selección y progreso;
turquesa del logo (``#3FA6C5``) como secundario; grises pizarra como base.

Colores derivados (contraste WCAG AA, D-02):
- ``acento_texto``: texto oscuro sobre el naranja (el blanco no llega a 4.5:1).
- ``acento_enlace`` (tema claro): naranja oscurecido para texto sobre fondos claros.
- ``secundario_texto`` (tema claro): turquesa oscurecido para texto sobre fondos claros.
"""

from __future__ import annotations

TOKENS_OSCURO: dict[str, str] = {
    "fondo": "#1E1E1E",
    "fondo_panel": "#2D3238",
    "fondo_alterno": "#262A2F",
    "fondo_campo": "#1A1D20",
    "borde": "#4A545E",
    "borde_suave": "#3E444A",
    "texto": "#E0E0E0",
    "texto_secundario": "#9DADB9",
    "texto_deshabilitado": "#7A858E",
    "acento": "#E57000",
    "acento_hover": "#F28A26",
    "acento_presionado": "#C96100",
    "acento_texto": "#1E1E1E",
    "acento_enlace": "#F28A26",
    "secundario": "#3FA6C5",
    "secundario_texto": "#3FA6C5",
    "foco": "#E57000",
    "seleccion": "#E57000",
    "seleccion_texto": "#1E1E1E",
    "hover_fila": "#3A3F45",
    "barra_superior": "#212529",
    "barra_superior_texto": "#F0F0F0",
    "boton": "#3A4047",
    "boton_hover": "#454C54",
    "boton_texto": "#E0E0E0",
    "deshabilitado_fondo": "#2A2E33",
    "tooltip_fondo": "#14161A",
    "tooltip_texto": "#E0E0E0",
    "error": "#FF6B6B",
    "aviso": "#F2B233",
    "exito": "#5FCB7A",
}

TOKENS_CLARO: dict[str, str] = {
    "fondo": "#F2F4F6",
    "fondo_panel": "#FFFFFF",
    "fondo_alterno": "#EAEEF1",
    "fondo_campo": "#FFFFFF",
    "borde": "#9AA5AE",
    "borde_suave": "#CBD2D8",
    "texto": "#212529",
    "texto_secundario": "#4F606D",
    "texto_deshabilitado": "#6B7782",
    "acento": "#E57000",
    "acento_hover": "#F28A26",
    "acento_presionado": "#C96100",
    "acento_texto": "#1E1E1E",
    "acento_enlace": "#A84F00",
    "secundario": "#3FA6C5",
    "secundario_texto": "#1B6A85",
    "foco": "#E57000",
    "seleccion": "#E57000",
    "seleccion_texto": "#1E1E1E",
    "hover_fila": "#FBE3CC",
    "barra_superior": "#2C3E50",
    "barra_superior_texto": "#F0F0F0",
    "boton": "#E3E7EA",
    "boton_hover": "#D5DBE0",
    "boton_texto": "#212529",
    "deshabilitado_fondo": "#E6E9EC",
    "tooltip_fondo": "#2C3E50",
    "tooltip_texto": "#F0F0F0",
    "error": "#B3261E",
    "aviso": "#8A5A00",
    "exito": "#1E7B3A",
}

# Pares (token_texto, token_fondo) que deben cumplir contraste >= 4.5:1 (CA-22.5).
# El texto deshabilitado queda fuera: WCAG 1.4.3 exime a los componentes inactivos.
PARES_TEXTO_FONDO: list[tuple[str, str]] = [
    ("texto", "fondo"),
    ("texto", "fondo_panel"),
    ("texto", "fondo_alterno"),
    ("texto", "fondo_campo"),
    ("texto", "hover_fila"),
    ("texto_secundario", "fondo"),
    ("texto_secundario", "fondo_panel"),
    ("texto_secundario", "fondo_alterno"),
    ("acento_texto", "acento"),
    ("acento_texto", "acento_hover"),
    ("seleccion_texto", "seleccion"),
    ("boton_texto", "boton"),
    ("boton_texto", "boton_hover"),
    ("barra_superior_texto", "barra_superior"),
    ("tooltip_texto", "tooltip_fondo"),
    ("acento_enlace", "fondo"),
    ("acento_enlace", "fondo_panel"),
    ("secundario_texto", "fondo"),
    ("secundario_texto", "fondo_panel"),
    ("error", "fondo"),
    ("error", "fondo_panel"),
    ("aviso", "fondo"),
    ("aviso", "fondo_panel"),
    ("exito", "fondo"),
    ("exito", "fondo_panel"),
]


def _luminancia(color: str) -> float:
    """Luminancia relativa WCAG 2.x de un color ``#RRGGBB``."""
    hexa = color.lstrip("#")
    canales = [int(hexa[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lineales = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineales[0] + 0.7152 * lineales[1] + 0.0722 * lineales[2]


def contraste(c1: str, c2: str) -> float:
    """Razón de contraste WCAG 2.x entre dos colores ``#RRGGBB`` (de 1 a 21)."""
    la, lb = _luminancia(c1), _luminancia(c2)
    claro, oscuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (oscuro + 0.05)
