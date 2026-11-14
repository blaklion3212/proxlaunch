"""Lectura limitada de archivos de terceros (RF-X02, INV-M3).

Es la ÚNICA puerta de entrada de archivos abiertos por el usuario: abre en solo lectura y
no existe aquí ninguna función que renombre, trunque o borre un archivo de entrada.
"""

from __future__ import annotations

import errno
import logging
import os
import stat
from pathlib import Path

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

_log = logging.getLogger("proxlaunch.archivos.lector")

_BLOQUE = 64 * 1024
_WINERROR_BLOQUEADO = (32, 33)


def _no_accesible(ruta: Path, motivo: str) -> ErrorProxLaunch:
    # Solo el nombre del archivo, nunca la ruta (puede contener el nombre del usuario).
    return ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_ACCESIBLE, {"archivo": ruta.name, "motivo": motivo}
    )


def _motivo_acceso(exc: OSError, ruta: Path) -> str:
    if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
        return "no_existe"
    if getattr(exc, "winerror", None) in _WINERROR_BLOQUEADO:
        return "bloqueado"
    if isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM):
        return "sin_permiso"
    return "otro"


def leer_archivo_limitado(ruta: Path, limite: int) -> bytes:
    """Lee un archivo regular de a lo sumo ``limite`` bytes (E/S, solo lectura).

    - No es un archivo regular (directorio, dispositivo, tubería con nombre) → E-M01
      ``no_regular``, sin bloquear (``O_NONBLOCK``) y sin leer.
    - Mayor que ``limite`` → E-M01 ``demasiado_grande`` sin leerlo entero: se leen como
      máximo ``limite + 1`` bytes, aunque ``st_size`` mienta o el archivo crezca.
    - Errores de E/S → E-M05 con ``motivo`` (``no_existe``, ``sin_permiso``, ``bloqueado``,
      ``otro``) y solo el nombre del archivo.
    """
    ruta = Path(ruta)
    banderas = os.O_RDONLY
    banderas |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    banderas |= getattr(os, "O_NOCTTY", 0)
    try:
        fd = os.open(ruta, banderas)
    except OSError as exc:
        # En Windows abrir una carpeta da PermissionError: se informa como no regular.
        if os.name == "nt" and ruta.is_dir():
            raise _no_permitido("no_regular", limite, None, ruta) from None
        raise _no_accesible(ruta, _motivo_acceso(exc, ruta)) from exc
    try:
        try:
            info = os.fstat(fd)
        except OSError as exc:
            raise _no_accesible(ruta, _motivo_acceso(exc, ruta)) from exc
        if not stat.S_ISREG(info.st_mode):
            raise _no_permitido("no_regular", limite, None, ruta)
        if info.st_size > limite:
            raise _no_permitido("demasiado_grande", limite, info.st_size, ruta)
        partes: list[bytes] = []
        total = 0
        while total <= limite:
            try:
                trozo = os.read(fd, min(_BLOQUE, limite + 1 - total))
            except OSError as exc:
                raise _no_accesible(ruta, _motivo_acceso(exc, ruta)) from exc
            if not trozo:
                break
            partes.append(trozo)
            total += len(trozo)
        if total > limite:
            raise _no_permitido("demasiado_grande", limite, total, ruta)
    finally:
        os.close(fd)
    _log.info("Archivo leído archivo=%s tamano=%d", ruta.name, total)
    return b"".join(partes)


def _no_permitido(motivo: str, limite: int, tamano: int | None, ruta: Path) -> ErrorProxLaunch:
    params = {"motivo": motivo, "limite": str(limite)}
    if tamano is not None:
        params["tamano"] = str(tamano)
    _log.info(
        "Archivo rechazado archivo=%s codigo=archivo_no_permitido motivo=%s", ruta.name, motivo
    )
    return ErrorProxLaunch(CodigoError.ARCHIVO_NO_PERMITIDO, params)
