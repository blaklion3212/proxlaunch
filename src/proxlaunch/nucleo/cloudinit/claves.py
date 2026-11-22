"""Claves SSH públicas (RF-B1.4, RF-B1.5): análisis, rechazo de claves privadas y codificación de
``sshkeys`` en un único punto (DT-B4). Puro salvo ``leer_archivo_pub``.

Los problemas nunca llevan el contenido de la clave ni la línea completa: solo su número.
"""

from __future__ import annotations

import base64
import binascii
import os
import re
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final
from urllib.parse import quote

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

TIPOS_CLAVE: Final[frozenset[str]] = frozenset(
    {
        "ssh-ed25519",
        "ssh-rsa",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "sk-ssh-ed25519@openssh.com",
        "sk-ecdsa-sha2-nistp256@openssh.com",
    }
)
MAX_CLAVES: Final = 20
MAX_BYTES_CLAVES: Final = 8192
MAX_BYTES_PUB: Final = 65536
MAX_COMENTARIO: Final = 64  # caracteres del comentario que muestra ``resumen_clave``

# Marcas de clave privada (RF-B1.5): PEM de cualquier tipo (RSA, EC, OPENSSH, ENCRYPTED, PGP…) y
# el formato de PuTTY.
_RE_PRIVADA = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY|PuTTY-User-Key-File-", re.IGNORECASE)
_RE_BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class MotivoClave(StrEnum):
    TIPO_DESCONOCIDO = "tipo_desconocido"
    SIN_CUERPO = "sin_cuerpo"
    BASE64 = "base64"
    CON_OPCIONES = "con_opciones"
    CLAVE_PRIVADA = "clave_privada"
    DEMASIADAS = "demasiadas"
    DEMASIADO_TEXTO = "demasiado_texto"


@dataclass(frozen=True)
class ProblemaClave:
    linea: int  # 1-based; 0 = todo el texto. Nunca lleva el contenido
    motivo: MotivoClave


@dataclass(frozen=True)
class ResultadoClaves:
    claves: tuple[str, ...]  # () si hubo clave privada (se rechaza todo)
    duplicadas: int
    problemas: tuple[ProblemaClave, ...]


def contiene_clave_privada(texto: str) -> bool:
    """¿Hay marcas de clave privada en el texto? (RF-B1.5)."""
    return isinstance(texto, str) and _RE_PRIVADA.search(texto) is not None


def _motivo_de_linea(partes: list[str]) -> MotivoClave | None:
    """Motivo por el que la línea (ya partida en palabras) no es una clave pública válida."""
    tipo = partes[0]
    if tipo not in TIPOS_CLAVE:
        # Una opción por delante (``command="x" ssh-ed25519 AAAA…``): el tipo viene después.
        if any(p in TIPOS_CLAVE for p in partes[1:]):
            return MotivoClave.CON_OPCIONES
        return MotivoClave.TIPO_DESCONOCIDO
    if len(partes) < 2:
        return MotivoClave.SIN_CUERPO
    cuerpo = partes[1]
    if not _RE_BASE64.fullmatch(cuerpo):
        return MotivoClave.BASE64
    try:
        # Con relleno y alfabeto correctos; al menos los 4 bytes del prefijo de longitud.
        if len(base64.b64decode(cuerpo, validate=True)) < 4:
            return MotivoClave.BASE64
    except (binascii.Error, ValueError):
        return MotivoClave.BASE64
    return None


def analizar_claves(texto: str) -> ResultadoClaves:
    """Analiza el texto pegado o leído de archivos ``.pub`` (una clave por línea).

    Convierte CRLF a ``\\n``; descarta líneas vacías y de comentario ``#``; quita duplicadas
    exactas y normaliza los espacios. Una marca de clave privada rechaza **todo** el contenido
    (``claves`` queda vacío). Los demás problemas dejan las claves válidas.
    """
    if not isinstance(texto, str):
        return ResultadoClaves((), 0, (ProblemaClave(0, MotivoClave.TIPO_DESCONOCIDO),))
    if contiene_clave_privada(texto):
        return ResultadoClaves((), 0, (ProblemaClave(0, MotivoClave.CLAVE_PRIVADA),))
    if len(texto.encode("utf-8", "replace")) > MAX_BYTES_PUB:
        return ResultadoClaves((), 0, (ProblemaClave(0, MotivoClave.DEMASIADO_TEXTO),))
    claves: list[str] = []
    vistas: set[str] = set()
    problemas: list[ProblemaClave] = []
    duplicadas = 0
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for numero, bruta in enumerate(lineas, start=1):
        linea = bruta.strip()
        if not linea or linea.startswith("#"):
            continue
        if _RE_CONTROL.search(linea.replace("\t", " ")):
            problemas.append(ProblemaClave(numero, MotivoClave.TIPO_DESCONOCIDO))
            continue
        partes = linea.split()
        motivo = _motivo_de_linea(partes)
        if motivo is not None:
            problemas.append(ProblemaClave(numero, motivo))
            continue
        normalizada = " ".join(partes)
        if normalizada in vistas:
            duplicadas += 1
            continue
        vistas.add(normalizada)
        claves.append(normalizada)
    if len(claves) > MAX_CLAVES:
        problemas.append(ProblemaClave(0, MotivoClave.DEMASIADAS))
    if len("\n".join(claves).encode("utf-8")) > MAX_BYTES_CLAVES:
        problemas.append(ProblemaClave(0, MotivoClave.DEMASIADO_TEXTO))
    return ResultadoClaves(tuple(claves), duplicadas, tuple(problemas))


def _error_archivo(motivo: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(CodigoError.ARCHIVO_CLAVES_NO_VALIDO, {"motivo": motivo})


def leer_archivo_pub(ruta: Path) -> str:
    """Lee un ``.pub`` como texto UTF-8 (≤ 64 KiB, sin NUL).

    Raises:
        ErrorProxLaunch: ``ARCHIVO_CLAVES_NO_VALIDO`` con ``motivo`` ``tamano``, ``binario`` o
            ``ilegible``. Nunca incluye la ruta ni el contenido.
    """
    try:
        # Se abre sin bloquear (una FIFO sin escritor no cuelga la interfaz) y se comprueba el
        # tipo sobre el MISMO descriptor, sin ventana entre la comprobación y la lectura (I1).
        banderas = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        descriptor = os.open(ruta, banderas)
        with os.fdopen(descriptor, "rb") as flujo:
            estado = os.fstat(flujo.fileno())
            if not stat.S_ISREG(estado.st_mode):
                raise _error_archivo("ilegible")
            if estado.st_size > MAX_BYTES_PUB:
                raise _error_archivo("tamano")
            datos = flujo.read(MAX_BYTES_PUB + 1)
    except OSError:
        raise _error_archivo("ilegible") from None
    if len(datos) > MAX_BYTES_PUB:
        raise _error_archivo("tamano")
    if b"\x00" in datos:
        raise _error_archivo("binario")
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _error_archivo("binario") from None
    # Lectura binaria: se normalizan los saltos de línea como haría el modo texto (\r\n de Windows).
    return texto.replace("\r\n", "\n").replace("\r", "\n")


def resumen_clave(clave: str) -> tuple[str, str]:
    """``(tipo, comentario)`` para mostrar en el Resumen; nunca el cuerpo. El comentario va
    sin caracteres de control y recortado."""
    partes = clave.split()
    tipo = partes[0] if partes else ""
    comentario = _RE_CONTROL.sub("", " ".join(partes[2:]))
    if len(comentario) > MAX_COMENTARIO:
        comentario = comentario[: MAX_COMENTARIO - 1] + "…"
    return tipo, comentario


def codificar_sshkeys(claves: Sequence[str]) -> str:
    """Valor de ``sshkeys``: las claves unidas con ``\\n`` y codificadas como URL (DT-B4).

    ÚNICO punto de codificación; el transporte vuelve a codificar el formulario.
    """
    return quote("\n".join(claves), safe="")
