"""URLs de descarga y checksums (V-O11, V-O12, INV-O6). Funciones puras, sin E/S.

La app nunca abre conexiones a la URL del usuario: la descarga la hace el nodo (RNF-O05).
Aquí solo se valida el texto y se evita que la URL llegue a logs, errores o archivos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import quote, quote_plus, unquote, urlsplit

from proxlaunch.nucleo.origen.constantes import MAX_LONG_URL

# Motivos de rechazo de ``validar_url`` (los textos los pone la interfaz).
URL_VACIA = "vacia"
URL_LARGA = "larga"
URL_CARACTERES = "caracteres"
URL_ESQUEMA = "esquema"
URL_SOLO_HTTPS = "solo_https"
URL_SIN_HOST = "sin_host"
URL_CREDENCIALES = "credenciales"
URL_PUERTO = "puerto"

CHECKSUM_VACIO = "vacio"
CHECKSUM_FORMATO = "formato"

_RE_HEX = re.compile(r"^[0-9a-fA-F]+$")
# Restos de cualquier URL (también codificada o cortada por el límite del detalle técnico).
_RE_URL_RESIDUAL = re.compile(r"(?i)https?(?::|%3A)(?://|%2F%2F)[^\s'\"<>)]*")


@dataclass(frozen=True, repr=False)
class UrlDescarga:
    """URL ya validada. Su ``__repr__`` muestra solo ``host/archivo`` (un volcado accidental no
    filtra la URL completa)."""

    texto: str
    host: str
    archivo: str
    es_http: bool

    def __repr__(self) -> str:
        return f"UrlDescarga({self.host}/{self.archivo})"


class AlgoritmoChecksum(StrEnum):
    MD5 = "md5"
    SHA1 = "sha1"
    SHA224 = "sha224"
    SHA256 = "sha256"
    SHA384 = "sha384"
    SHA512 = "sha512"


# Longitud hexadecimal → algoritmo (V-O12).
_ALGORITMO_POR_LONGITUD: dict[int, AlgoritmoChecksum] = {
    32: AlgoritmoChecksum.MD5,
    40: AlgoritmoChecksum.SHA1,
    56: AlgoritmoChecksum.SHA224,
    64: AlgoritmoChecksum.SHA256,
    96: AlgoritmoChecksum.SHA384,
    128: AlgoritmoChecksum.SHA512,
}


@dataclass(frozen=True, repr=False)
class ChecksumTransferencia:
    """Huella dada por el usuario. El ``__repr__`` no muestra el valor (INV-O6)."""

    algoritmo: AlgoritmoChecksum
    valor: str

    def __repr__(self) -> str:
        return f"ChecksumTransferencia({self.algoritmo.value})"


def _tiene_caracteres_no_permitidos(texto: str) -> bool:
    """Espacios, controles (incluidos los de Unicode) y todo lo que no sea ASCII imprimible.

    Un host internacional se escribe en punycode; así se evita además la confusión visual.
    """
    return any(ord(c) <= 32 or ord(c) >= 127 for c in texto)


def _sin_controles(texto: str) -> str:
    """Sustituye por «_» los caracteres de control (Cc) y de formato (Cf, p. ej. U+202E).

    Tras ``unquote`` el nombre puede traer controles o marcas bidireccionales codificados
    (``%E2%80%AE``) que falsearían lo que se muestra o registra.
    """
    return "".join("_" if unicodedata.category(c) in ("Cc", "Cf") else c for c in texto)


def validar_url(texto: str, *, permitir_http: bool) -> tuple[UrlDescarga | None, str | None]:
    """V-O11. Devuelve ``(url, None)`` o ``(None, motivo)``.

    Se aceptan ``https://`` y, solo con ``permitir_http`` (modo avanzado con confirmación,
    DT-O7), ``http://``. Se rechazan ``userinfo``, espacios, controles y otros esquemas.
    """
    texto = (texto or "").strip()
    if not texto:
        return None, URL_VACIA
    if len(texto) > MAX_LONG_URL:
        return None, URL_LARGA
    if _tiene_caracteres_no_permitidos(texto):
        return None, URL_CARACTERES
    try:
        partes = urlsplit(texto)
    except ValueError:
        return None, URL_CARACTERES
    esquema = partes.scheme.lower()
    if esquema not in ("https", "http"):
        return None, URL_ESQUEMA
    if esquema == "http" and not permitir_http:
        return None, URL_SOLO_HTTPS
    # ``netloc`` con «@» es userinfo (usuario:clave@host): nunca se admite.
    if "@" in partes.netloc:
        return None, URL_CREDENCIALES
    try:
        host = partes.hostname
        _ = partes.port  # fuerza la validación del puerto
    except ValueError:
        return None, URL_PUERTO
    if not host:
        return None, URL_SIN_HOST
    if "%" in host:
        # Un host con «%» (codificado) no es un nombre de host válido.
        return None, URL_CARACTERES
    host = _sin_controles(host)
    segmentos = [s for s in partes.path.split("/") if s]
    archivo = _sin_controles(unquote(segmentos[-1])) if segmentos else ""
    return UrlDescarga(texto=texto, host=host, archivo=archivo, es_http=esquema == "http"), None


def validar_checksum(texto: str) -> tuple[ChecksumTransferencia | None, str | None]:
    """V-O12: hexadecimal; el algoritmo se deduce de la longitud (32/40/56/64/96/128)."""
    limpio = (texto or "").strip()
    if not limpio:
        return None, CHECKSUM_VACIO
    algoritmo = _ALGORITMO_POR_LONGITUD.get(len(limpio))
    if algoritmo is None or not _RE_HEX.match(limpio):
        return None, CHECKSUM_FORMATO
    return ChecksumTransferencia(algoritmo, limpio.lower()), None


def host_y_archivo(url: UrlDescarga) -> tuple[str, str]:
    """``(host, archivo)``: lo único de la URL que se puede mostrar o registrar."""
    return url.host, url.archivo


def url_saneada(texto: str) -> str:
    """Forma mostrable ``host/archivo`` de un texto con forma de URL (admite userinfo).

    Pensada para celdas de CSV: la URL del usuario nunca se conserva con usuario, clave, ruta
    ni consulta (INV-O6). Si no se puede analizar, devuelve una marca fija sin datos de la URL.
    """
    try:
        partes = urlsplit(texto.strip())
        host = partes.hostname or ""
        segmentos = [s for s in partes.path.split("/") if s]
        archivo = _sin_controles(unquote(segmentos[-1])) if segmentos else ""
    except ValueError:
        return "(url)"
    if not host or "%" in host:
        return "(url)"
    host = _sin_controles(host)
    url = UrlDescarga(texto=texto.strip(), host=host, archivo=archivo, es_http=False)
    return ocultar_url(texto.strip(), url)


def ocultar_url(texto: str, url: UrlDescarga) -> str:
    """Sustituye la URL (y sus formas codificadas) por ``host/archivo`` en ``texto``.

    Cubre la URL tal cual y codificada con ``quote``/``quote_plus``, que es como aparece en
    los mensajes de ``requests`` y en las consultas (INV-O6). Se sustituye también la URL
    sin esquema, por si un mensaje del servidor la recorta, y cualquier resto con forma de URL.
    """
    reemplazo = f"{url.host}/{url.archivo}"
    sin_esquema = url.texto.split("://", 1)[-1]
    variantes = {
        url.texto,
        quote(url.texto, safe=""),
        quote(url.texto),
        quote_plus(url.texto),
        sin_esquema,
        quote(sin_esquema, safe=""),
        quote_plus(sin_esquema),
    }
    for variante in sorted(variantes, key=len, reverse=True):
        if variante:
            texto = texto.replace(variante, reemplazo)
    # Defensa final: una URL truncada o reescrita por una capa intermedia no casa con las
    # variantes anteriores; se elimina todo lo que aún parezca una URL.
    return _RE_URL_RESIDUAL.sub(reemplazo, texto)
