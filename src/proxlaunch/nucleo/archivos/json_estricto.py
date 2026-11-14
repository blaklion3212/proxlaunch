"""JSON estricto para archivos de terceros (RF-X02, CA-X02.3).

Solo se usa ``json.loads`` de la biblioteca estándar: nunca ``eval``, ``pickle`` ni similares.
Rechaza UTF-8 inválido, ``NaN``/``Infinity``, números que desbordan (``1e999``), claves
repetidas y anidamiento excesivo (comprobado ANTES de llamar al analizador, de modo que no
puede producirse un ``RecursionError``). Tolera un BOM UTF-8 inicial (Bloc de notas, D-T7).
"""

from __future__ import annotations

import codecs
import json
import math
import re

from proxlaunch.nucleo.archivos.constantes import PROFUNDIDAD_JSON_MAX
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

# Solo los caracteres que cambian de estado el recorrido: comilla, barra y delimitadores.
_RE_SIGNIFICATIVOS = re.compile(r'["\\\[\]{}]')


def _danado(detalle: str) -> ErrorProxLaunch:
    """E-M04 de todo el archivo (sin campo): el detalle nunca incluye datos del usuario."""
    return ErrorProxLaunch(CodigoError.ARCHIVO_DANADO, {"campo": "", "detalle": detalle})


def _prohibir_constante(nombre: str) -> object:
    raise ValueError("constante no permitida")


def _numero_real(texto: str) -> float:
    valor = float(texto)
    if not math.isfinite(valor):
        raise ValueError("número fuera de rango")
    return valor


def _sin_claves_repetidas(pares: list[tuple[str, object]]) -> dict[str, object]:
    resultado: dict[str, object] = {}
    for clave, valor in pares:
        if clave in resultado:
            raise ValueError("clave repetida")
        resultado[clave] = valor
    return resultado


def _comprobar_profundidad(texto: str, maximo: int) -> None:
    """Recorrido lineal de un paso: cuenta ``[``/``{`` fuera de cadenas y corta al pasar ``maximo``.

    Una cadena sin cerrar deja el resto como contenido de cadena (el análisis posterior la
    rechaza como JSON inválido); así el coste es siempre O(n).
    """
    profundidad = 0
    en_cadena = False
    saltar_hasta = 0  # posición hasta la que el siguiente carácter está escapado
    for m in _RE_SIGNIFICATIVOS.finditer(texto):
        pos = m.start()
        if pos < saltar_hasta:
            continue
        c = m.group()
        if en_cadena:
            if c == "\\":
                saltar_hasta = pos + 2  # el carácter siguiente queda escapado
            elif c == '"':
                en_cadena = False
        elif c == '"':
            en_cadena = True
        elif c in "[{":
            profundidad += 1
            if profundidad > maximo:
                raise _danado("profundidad")
        elif c in "]}":
            profundidad -= 1


def cargar_json_estricto(datos: bytes, *, profundidad_max: int = PROFUNDIDAD_JSON_MAX) -> object:
    """Interpreta ``datos`` como JSON estricto; cualquier problema es E-M04 (sin trazas)."""
    if datos.startswith(codecs.BOM_UTF8):
        datos = datos[len(codecs.BOM_UTF8) :]
    try:
        texto = datos.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise _danado("utf8") from None
    _comprobar_profundidad(texto, profundidad_max)
    try:
        return json.loads(
            texto,
            parse_constant=_prohibir_constante,
            parse_float=_numero_real,
            object_pairs_hook=_sin_claves_repetidas,
        )
    except RecursionError:
        raise _danado("profundidad") from None
    except ValueError as exc:  # incluye JSONDecodeError y el límite de dígitos de int
        raise _danado(_clasificar(exc)) from None


def _clasificar(exc: ValueError) -> str:
    mensaje = str(exc)
    if "clave repetida" in mensaje:
        return "claves_repetidas"
    if "constante no permitida" in mensaje or "número fuera de rango" in mensaje:
        return "numero"
    if "digits" in mensaje:  # límite de dígitos de ``int`` de Python
        return "numero"
    return "json"
