"""Lectura segura del XML de dominio de libvirt (RF-D1.2, RF-D1.3, DT-D13).

El archivo es no confiable. Solo se usa la biblioteca estándar (``xml.etree``) sobre texto ya
decodificado, y ANTES de interpretar nada se rechaza cualquier ``<!DOCTYPE`` o ``<!ENTITY``
(sin ellos no hay entidades que expandir ni DTD que resolver). No se usa ningún otro
analizador, no se resuelve nada externo y no se abre ninguna ruta leída del XML.
"""

from __future__ import annotations

import logging
import pyexpat
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.transferencias.archivo_local import ArchivoAbierto, _abrir_descriptor

if TYPE_CHECKING:
    from collections.abc import Iterator

_log = logging.getLogger("proxlaunch.libvirt.lectura_xml")

MAX_BYTES_XML: Final = 4 * 1024 * 1024
MAX_PROFUNDIDAD: Final = 64
MAX_ELEMENTOS: Final = 50_000
_TAM_BLOQUE: Final = 16 * 1024  # caracteres por ``feed``: el recuento corta casi al pasar el límite
_EXPAT_MINIMA: Final = (2, 7, 2)
_EXPAT_SIN_REDISPARO: Final = (2, 6, 0)  # antes: ``feed`` por bloques cuesta tiempo cuadrático

_BOM_UTF8: Final = b"\xef\xbb\xbf"
_BOM_UTF16_LE: Final = b"\xff\xfe"
_BOM_UTF16_BE: Final = b"\xfe\xff"
_BOM_UTF32_LE: Final = b"\xff\xfe\x00\x00"

# ``<!`` + DOCTYPE/ENTITY, con espacios intermedios y sin distinguir mayúsculas; también dentro de
# comentarios y CDATA (se rechaza el archivo entero).
_RE_PROHIBIDOS: Final = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)
_RE_DECLARACION: Final = re.compile(r"<\?xml\s[^>]{0,256}?\?>")
_RE_ENCODING: Final = re.compile(r"""\sencoding\s*=\s*(?:"[^"]*"|'[^']*')""")


class ErrorXml(Exception):
    """Archivo no aceptable. ``motivo`` es uno de los de ``CodigoError.XML_NO_VALIDO``.

    Motivos: ``tamano``, ``doctype``, ``formato``, ``codificacion``, ``limites``,
    ``no_dominio`` (V-D20, V-D21 y V-D22) y ``no_kvm`` (V-D23, lo emite quien interpreta).
    """

    def __init__(self, motivo: str, **params: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.params: dict[str, str] = dict(params)

    def a_error(self) -> ErrorProxLaunch:
        """El mismo problema como ``ErrorProxLaunch(XML_NO_VALIDO)`` con ``params["motivo"]``."""
        return ErrorProxLaunch(CodigoError.XML_NO_VALIDO, {"motivo": self.motivo, **self.params})


def decodificar(datos: bytes) -> str:
    """Decodifica a texto: UTF-8 con o sin BOM, o UTF-16 solo con BOM (LE o BE).

    La declaración ``encoding=`` del prólogo se ignora (ya se decodificó) y se quita del
    texto para que el analizador no discuta con la codificación real.

    Raises:
        ErrorXml: ``codificacion`` (cualquier otra cosa, UTF-32, bytes inválidos o NUL).
    """
    try:
        if datos.startswith(_BOM_UTF32_LE):
            raise ErrorXml("codificacion")
        if datos.startswith(_BOM_UTF16_LE):
            texto = datos[2:].decode("utf-16-le")
        elif datos.startswith(_BOM_UTF16_BE):
            texto = datos[2:].decode("utf-16-be")
        elif datos.startswith(_BOM_UTF8):
            texto = datos[3:].decode("utf-8")
        else:
            texto = datos.decode("utf-8")
    except UnicodeDecodeError:
        raise ErrorXml("codificacion") from None
    if "\x00" in texto:  # UTF-16 sin BOM leído como UTF-8, o binario: el rastreo no sería fiable
        raise ErrorXml("codificacion")
    return _sin_codificacion_declarada(texto)


def _sin_codificacion_declarada(texto: str) -> str:
    m = _RE_DECLARACION.match(texto)
    if m is None:
        return texto
    return _RE_ENCODING.sub("", m.group(0)) + texto[m.end() :]


def comprobar_prohibidos(texto: str) -> None:
    """Rechaza ``<!DOCTYPE`` y ``<!ENTITY`` (sin distinguir mayúsculas).

    Raises:
        ErrorXml: ``doctype``.
    """
    if _RE_PROHIBIDOS.search(texto) is not None:
        raise ErrorXml("doctype")


def _registrar_version_expat() -> tuple[int, ...]:
    """Anota en el registro si Expat es anterior a 2.7.2 (CA-D1.3.7); nunca bloquea.

    Devuelve la versión como tupla de números (vacía si no se conoce).
    """
    version = str(getattr(pyexpat, "EXPAT_VERSION", ""))
    numeros = tuple(int(n) for n in re.findall(r"\d+", version)[:3])
    if numeros and numeros < _EXPAT_MINIMA:
        _log.warning(
            "Expat %s es anterior a 2.7.2: el XML se lee con los límites de siempre", version
        )
    return numeros


def leer_xml(datos: bytes) -> ET.Element:
    """Interpreta ``datos`` como un ``<domain>`` de libvirt y devuelve su raíz.

    Orden: tamaño, decodificación, rechazo de DOCTYPE/ENTITY y análisis con recuento de
    profundidad y de elementos (se corta al pasar el límite).

    Raises:
        ErrorXml: ``tamano``, ``codificacion``, ``doctype``, ``formato`` (con ``linea`` si se
            conoce), ``limites`` o ``no_dominio``.
    """
    if len(datos) > MAX_BYTES_XML:
        raise ErrorXml("tamano", tamano=str(len(datos)))
    texto = decodificar(datos)
    comprobar_prohibidos(texto)
    version_expat = _registrar_version_expat()
    # Con Expat < 2.6 alimentar por bloques puede costar tiempo cuadrático: el texto (ya acotado
    # a 4 MiB en memoria) se analiza de una sola vez.
    bloque = (
        len(texto) or 1 if version_expat and version_expat < _EXPAT_SIN_REDISPARO else _TAM_BLOQUE
    )
    parser: ET.XMLPullParser = ET.XMLPullParser(events=("start", "end"))
    raiz: ET.Element | None = None
    profundidad = 0
    elementos = 0
    try:
        for desde in range(0, len(texto), bloque):
            parser.feed(texto[desde : desde + bloque])
            for evento, objeto in cast("Iterator[tuple[str, object]]", parser.read_events()):
                if evento == "start":
                    if raiz is None and isinstance(objeto, ET.Element):
                        raiz = objeto
                    profundidad += 1
                    elementos += 1
                    if profundidad > MAX_PROFUNDIDAD or elementos > MAX_ELEMENTOS:
                        raise ErrorXml("limites")
                else:
                    profundidad -= 1
        parser.close()
    except ET.ParseError as exc:
        posicion = getattr(exc, "position", None)
        if isinstance(posicion, tuple) and posicion:
            raise ErrorXml("formato", linea=str(posicion[0])) from None
        raise ErrorXml("formato") from None
    if raiz is None:
        raise ErrorXml("formato")
    if raiz.tag != "domain":
        raise ErrorXml("no_dominio")
    return raiz


def leer_archivo(ruta: Path) -> bytes:
    """Lee los bytes del archivo elegido (solo lectura, ``fstat`` regular, ≤ MAX + 1 bytes).

    Se lee un byte de más para que ``leer_xml`` detecte el exceso sin cargar un archivo enorme.

    Raises:
        ErrorProxLaunch: ``ARCHIVO_NO_ACCESIBLE`` o ``ARCHIVO_NO_PERMITIDO`` (no regular).
    """
    ruta = Path(ruta)
    fd, info = _abrir_descriptor(ruta)
    with ArchivoAbierto(fd, info, ruta.name) as archivo:
        try:
            return archivo.flujo.read(MAX_BYTES_XML + 1)
        except OSError as exc:
            raise ErrorProxLaunch(
                CodigoError.ARCHIVO_NO_ACCESIBLE, {"archivo": ruta.name, "motivo": "otro"}
            ) from exc
