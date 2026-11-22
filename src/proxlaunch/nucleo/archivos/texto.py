"""Utilidades de texto para archivos: cadenas seguras, nombres y nombres de archivo.

Reglas V-M01 (nombre), V-M04 (cadenas de archivos) y V-M05 (token en texto libre).
Todo es puro y sin textos para el usuario.
"""

from __future__ import annotations

import re
import unicodedata

from proxlaunch.nucleo.archivos.constantes import LONG_NOMBRE_PERFIL, MAX_LONG_TEXTO
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

# Caracteres de dirección de texto que pueden engañar a quien lee (V-M04).
CARACTERES_BIDI = frozenset(
    {chr(c) for c in range(0x202A, 0x202F)}  # U+202A..U+202E
    | {chr(c) for c in range(0x2066, 0x206A)}  # U+2066..U+2069
    | {"‎", "‏", "؜"}
)

# Caracteres de formato invisibles (categoría Cf) que no se ven pero engañan: además de la
# dirección de texto, espacios de ancho cero, unión de palabras y BOM. Constante compartida
# por el CSV seguro y el saneado de mensajes (S3).
CARACTERES_FORMATO_INVISIBLES = CARACTERES_BIDI | frozenset(
    {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}
)


def es_formato_invisible(c: str) -> bool:
    """Indica si ``c`` es un carácter de formato invisible (lista fija o categoría ``Cf``)."""
    return c in CARACTERES_FORMATO_INVISIBLES or unicodedata.category(c) == "Cf"


# Patrón de API Token (V-18 de M1) buscado dentro de un texto libre, y cabecera PVEAPIToken.
# Cuantificadores acotados (SEG-A-03): sin retroceso cuadrático en textos largos. El secreto
# basta con un carácter: no hace falta recorrerlo entero para saber que hay un token.
_RE_TOKEN_EN_TEXTO = re.compile(r"[^@!=\s]{1,128}@[^@!=\s]{1,128}![A-Za-z0-9._-]{1,128}=\S")
_RE_CABECERA_TOKEN = re.compile(r"PVEAPIToken\s*=", re.IGNORECASE)

# Nombres reservados de Windows (sin extensión, sin distinguir mayúsculas).
_RESERVADOS_WINDOWS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_PROHIBIDOS_EN_ARCHIVO = frozenset('<>:"/\\|?*')
MAX_LONG_NOMBRE_ARCHIVO = 80

# Motivos de ``analizar_texto``.
MOTIVO_LONGITUD = "longitud"
MOTIVO_CARACTERES = "caracteres"


def _caracter_no_permitido(c: str, multilinea: bool, tabulador: bool) -> bool:
    """Control (salvo ``\\n`` en multilínea y ``\\t`` si se permite), dirección de texto o
    sustituto suelto."""
    if c in CARACTERES_BIDI:
        return True
    categoria = unicodedata.category(c)
    if categoria == "Cc":
        return not ((multilinea and c == "\n") or (tabulador and c == "\t"))
    return categoria == "Cs"  # sustitutos sueltos (``\ud800``): no se pueden codificar


def analizar_texto(
    valor: str, *, maximo: int, multilinea: bool = False, tabulador: bool = False
) -> tuple[str, str | None]:
    """Normaliza a NFC y devuelve ``(texto, motivo)``; ``motivo`` es ``None`` si es seguro.

    ``tabulador`` admite además ``\\t`` (notas de la MV, fase A).

    Motivos: ``"longitud"`` (supera ``maximo``) y ``"caracteres"`` (control, dirección de
    texto o sustituto suelto). Si el texto es desmesurado no se normaliza (ahorra trabajo).
    """
    if len(valor) > maximo * 4:  # NFC no reduce más de ~3x: ya es demasiado largo
        return valor[: maximo + 1], MOTIVO_LONGITUD
    texto = unicodedata.normalize("NFC", valor)
    if len(texto) > maximo:
        return texto, MOTIVO_LONGITUD
    if any(_caracter_no_permitido(c, multilinea, tabulador) for c in texto):
        return texto, MOTIVO_CARACTERES
    return texto, None


def texto_seguro(valor: str, *, maximo: int, multilinea: bool = False) -> str | None:
    """Cadena normalizada a NFC o ``None`` si no es válida (V-M04).

    Inválida: más larga que ``maximo``, con caracteres de control (salvo ``\\n`` si
    ``multilinea``) o de dirección de texto (U+202A–202E, U+2066–2069, U+200E/F, U+061C).
    """
    if not isinstance(valor, str):
        return None
    texto, motivo = analizar_texto(valor, maximo=maximo, multilinea=multilinea)
    return texto if motivo is None else None


def _sin_invisibles(texto: str) -> str:
    """Quita los caracteres de control (Cc, salvo saltos y tabulador), de formato (Cf) y de
    dirección de texto: con ellos se podría partir un token sin que se vea (SEG-A-02)."""
    if texto.isascii() and texto.isprintable():
        return texto  # camino rápido: nada que quitar
    return "".join(
        c
        for c in texto
        if c in "\t\n\r"
        or (c not in CARACTERES_BIDI and unicodedata.category(c) not in ("Cc", "Cf"))
    )


def contiene_token(texto: str) -> bool:
    """Indica si el texto trae un API Token (``usuario@realm!id=secreto``) o ``PVEAPIToken=``.

    Se normaliza antes de buscar (sin Cc, Cf ni bidi): un carácter invisible dentro del id o
    del realm no debe esquivar la detección.
    """
    if not isinstance(texto, str) or "=" not in texto:  # ambos patrones exigen un «=»
        return False
    texto = _sin_invisibles(texto)
    if _RE_CABECERA_TOKEN.search(texto):
        return True
    # El patrón del token exige «@» y «!»: evita el costo de la expresión en notas largas (8192).
    return "@" in texto and "!" in texto and bool(_RE_TOKEN_EN_TEXTO.search(texto))


def exigir_sin_credencial(texto: str, campo: str) -> None:
    """INV-M2 al serializar: lanza E-M08 (motivo ``credencial``) si el texto parece un token.

    Los ``params`` llevan solo el nombre técnico del campo, nunca el valor.
    """
    if contiene_token(texto):
        raise ErrorProxLaunch(
            CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "credencial", "campo": campo}
        )


def validar_nombre(texto: str, *, maximo: int = LONG_NOMBRE_PERFIL) -> tuple[str, str | None]:
    """Valida un nombre de perfil o de lote (V-M01 sin unicidad).

    Devuelve ``(normalizado, regla)``: el texto recortado y en NFC, y la regla incumplida
    o ``None``. ``V-M01``: vacío o más largo que ``maximo``; ``V-M04``: caracteres de control
    o de dirección de texto, o texto desmesurado (> ``MAX_LONG_TEXTO``); ``V-M05``: parece un token.
    """
    if not isinstance(texto, str):
        return "", "V-M01"
    normalizado, motivo = analizar_texto(texto, maximo=MAX_LONG_TEXTO)
    if motivo == MOTIVO_CARACTERES:
        return normalizado.strip(), "V-M04"
    if motivo == MOTIVO_LONGITUD:
        return normalizado.strip(), "V-M04"
    normalizado = normalizado.strip()
    if not normalizado or len(normalizado) > maximo:
        return normalizado, "V-M01"
    if contiene_token(normalizado):
        return normalizado, "V-M05"
    return normalizado, None


def clave_comparacion(texto: str, *, sin_acentos: bool = False) -> str:
    """Clave para comparar nombres sin distinguir mayúsculas (y opcionalmente acentos)."""
    t = unicodedata.normalize("NFC", texto).strip().casefold()
    if sin_acentos:
        t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
        t = unicodedata.normalize("NFC", t)
    return t


def nombre_archivo_seguro(base: str, extension: str) -> str:
    """Nombre de archivo sugerido a partir de un texto cualquiera (CA-P08.5).

    Sin separadores de ruta ni caracteres prohibidos en Windows, sin ``.``/``..``, sin
    nombres reservados de Windows y de a lo sumo 80 caracteres en total (con ``extension``,
    que se espera con el punto inicial, p. ej. ``".proxlaunch-perfiles.json"``).
    """
    limpio = []
    for c in unicodedata.normalize("NFC", str(base)):
        if (
            c in _PROHIBIDOS_EN_ARCHIVO
            or c in CARACTERES_BIDI
            or unicodedata.category(c) in ("Cc", "Cs")
        ):
            limpio.append("_")
        else:
            limpio.append(c)
    # Sin espacios ni puntos en los extremos (Windows los recorta y ``..`` sería peligroso).
    stem = "".join(limpio).strip(" .")
    if not stem:
        stem = "archivo"
    if stem.split(".", 1)[0].strip().upper() in _RESERVADOS_WINDOWS:
        stem = "_" + stem
    disponible = max(1, MAX_LONG_NOMBRE_ARCHIVO - len(extension))
    stem = stem[:disponible].rstrip(" .") or "archivo"
    return stem + extension
