"""Registro (log) rotativo con filtro que enmascara secretos (RNF-06, CA-08.5)."""

from __future__ import annotations

import logging
import re
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import quote, quote_plus

MASCARA = "***"
NOMBRE_LOGGER = "proxlaunch"
ARCHIVO_LOG = "proxlaunch.log"

# Nombres de campo cuyo valor siempre se enmascara (cabeceras, parámetros de formulario,
# claves de diccionarios o JSON). Cubre `clave=valor`, `clave: valor` y `'clave': 'valor'`.
_CAMPOS = "password|contrasena|otp|tfa|ticket|CSRFPreventionToken|PVEAuthCookie|PVEAPIToken"
_RE_CAMPO = re.compile(
    rf"""(?ix)(?<![A-Za-z])({_CAMPOS})(["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s&;,}}"']+)"""
)
# Cabeceras que se enmascaran hasta el fin del valor (puede contener espacios).
_RE_CABECERA = re.compile(
    r"""(?i)(?<![A-Za-z])((?:set-)?cookie|authorization|proxy-authorization)(["']?\s*[:=]\s*)["']?[^\r\n"',}]+"""
)

_lock = threading.Lock()
_secretos: set[str] = set()


def registrar_secreto(valor: str) -> None:
    """Registra un valor concreto para que se enmascare en cualquier mensaje del log
    (incluidas sus variantes codificadas para URL). Los vacíos se ignoran."""
    if not valor:
        return
    with _lock:
        _secretos.update({valor, quote(valor, safe=""), quote_plus(valor)})


def olvidar_secretos() -> None:
    """Vacía la lista de secretos registrados (útil en pruebas)."""
    with _lock:
        _secretos.clear()


def enmascarar(texto: str) -> str:
    """Devuelve `texto` con todos los secretos conocidos sustituidos por `***`."""
    texto = _RE_CABECERA.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASCARA}", texto)
    texto = _RE_CAMPO.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASCARA}", texto)
    with _lock:
        conocidos = sorted(_secretos, key=len, reverse=True)
    for s in conocidos:
        texto = texto.replace(s, MASCARA)
    return texto


class FiltroSecretos(logging.Filter):
    """Enmascara secretos en el mensaje ya formateado, sus argumentos, el texto de las
    excepciones y la traza de pila. Nunca descarta registros."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            mensaje = record.getMessage()
        except Exception:
            mensaje = str(record.msg)
        record.msg = enmascarar(mensaje)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = enmascarar(record.exc_text)
        if record.stack_info:
            record.stack_info = enmascarar(record.stack_info)
        return True


def configurar_registro(
    directorio: Path | str,
    nivel: int | str = logging.INFO,
    max_bytes: int = 1_000_000,
    copias: int = 5,
) -> logging.Logger:
    """Configura el logger "proxlaunch" con archivo rotativo (1 MB x 5 por defecto) y
    filtro de secretos. Es idempotente: reemplaza el manejador previo si lo hubiera."""
    carpeta = Path(directorio)
    carpeta.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(NOMBRE_LOGGER)
    for h in list(logger.handlers):
        if getattr(h, "_proxlaunch", False):
            logger.removeHandler(h)
            h.close()
    manejador = RotatingFileHandler(
        carpeta / ARCHIVO_LOG, maxBytes=max_bytes, backupCount=copias, encoding="utf-8"
    )
    manejador._proxlaunch = True  # type: ignore[attr-defined]
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    # El filtro va en el manejador: afecta a los registros de todos los submódulos.
    manejador.addFilter(FiltroSecretos())
    logger.addHandler(manejador)
    logger.setLevel(nivel)
    logger.propagate = False  # evita que un manejador raíz escriba sin filtrar
    return logger
