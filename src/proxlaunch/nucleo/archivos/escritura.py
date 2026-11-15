"""Escritura atómica de archivos (RF-X03): temporal en la misma carpeta, fsync y os.replace."""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import tempfile
from pathlib import Path

from proxlaunch.nucleo.archivos.reemplazo import reemplazar_con_reintentos
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

_log = logging.getLogger("proxlaunch.archivos.escritura")

# MAX_PATH (260) incluye el NUL final: el máximo real son 259 caracteres.
_LIMITE_RUTA_WINDOWS = 260
_WINERROR_BLOQUEADO = (32, 33)  # violación de uso compartido / de bloqueo (archivo abierto)
_WINERROR_ACCESO_DENEGADO = 5
_PREFIJO_TEMPORAL = ".proxlaunch-"
_MAX_CARS_NOMBRE_TEMPORAL = 8  # del nombre destino; mantiene el temporal muy por debajo de NAME_MAX
_SUFIJO_TEMPORAL = ".tmp"
_ALEATORIOS_MKSTEMP = 8  # mkstemp añade 8 caracteres aleatorios


def _prefijo_temporal(nombre: str) -> str:
    """Prefijo corto y fijo (``.proxlaunch-`` + hasta 8 caracteres seguros del nombre)."""
    seguros = "".join(c for c in nombre if c.isascii() and (c.isalnum() or c in "-_"))
    return _PREFIJO_TEMPORAL + seguros[:_MAX_CARS_NOMBRE_TEMPORAL]


def motivo_oserror(exc: OSError) -> str:
    """Traduce un ``OSError`` de escritura al ``motivo`` de E-M08.

    Valores: ``sin_espacio``, ``sin_permiso``, ``bloqueado``, ``ruta_larga`` y ``otro``.
    """
    if exc.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", -1)):
        return "sin_espacio"
    if exc.errno == errno.ENAMETOOLONG:
        return "ruta_larga"
    if getattr(exc, "winerror", None) in _WINERROR_BLOQUEADO:
        return "bloqueado"
    if isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        return "sin_permiso"
    return "otro"


def _no_guardable(motivo: str, archivo: Path) -> ErrorProxLaunch:
    # El registro lleva el nombre del archivo y el motivo; nunca la ruta ni el contenido.
    _log.warning("No se pudo guardar archivo=%s motivo=%s", archivo.name, motivo)
    return ErrorProxLaunch(CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": motivo})


def escribir_atomico(ruta: Path, datos: bytes) -> None:
    """Escribe ``datos`` en ``ruta`` sin dejar nunca un archivo a medias.

    ``mkstemp`` en la carpeta de destino (nace 0600 en POSIX) → escritura → ``flush`` +
    ``fsync`` → ``os.replace``. Ante cualquier error borra el temporal, deja intacto el destino
    anterior y lanza ``ARCHIVO_NO_GUARDABLE``. No crea la carpeta ni cambia sus permisos.
    """
    ruta = Path(ruta)
    prefijo = _prefijo_temporal(ruta.name)
    if os.name == "nt":
        # Se mide el destino y también el temporal más largo posible (S7).
        largo_tmp = (
            len(os.path.dirname(str(ruta)))
            + 1
            + len(prefijo)
            + _ALEATORIOS_MKSTEMP
            + len(_SUFIJO_TEMPORAL)
        )
        if max(len(str(ruta)), largo_tmp) >= _LIMITE_RUTA_WINDOWS:
            raise _no_guardable("ruta_larga", ruta)
    tmp: str | None = None
    reemplazando = False
    try:
        fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=prefijo, suffix=_SUFIJO_TEMPORAL)
        with os.fdopen(fd, "wb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        reemplazando = True
        reemplazar_con_reintentos(tmp, ruta)
        tmp = None
    except OSError as exc:
        motivo = motivo_oserror(exc)
        if (
            reemplazando
            and motivo == "sin_permiso"
            and os.name == "nt"
            and getattr(exc, "winerror", None) == _WINERROR_ACCESO_DENEGADO
            and ruta.exists()
        ):
            # El temporal se creó y el destino existe: lo más probable es que otra aplicación
            # lo tenga abierto (S8).
            motivo = "bloqueado"
        raise _no_guardable(motivo, ruta) from exc
    except Exception as exc:  # fallo inesperado: el destino anterior sigue intacto
        raise _no_guardable("otro", ruta) from exc
    finally:
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    _sincronizar_carpeta(ruta.parent)


def _sincronizar_carpeta(carpeta: Path) -> None:
    """Mejor esfuerzo (solo POSIX): hace durable el cambio de nombre."""
    if os.name != "posix":
        return
    with contextlib.suppress(OSError):
        fd = os.open(carpeta, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
