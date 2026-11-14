"""Traducción de respuestas y excepciones a CodigoError.

Cubre la sección 7 de los requisitos y la aclaración A-8. Devuelve códigos con
parámetros; los textos para el usuario los pone la interfaz. El ``detalle_tecnico``
pasa siempre por ``enmascarar`` para que no lleve secretos.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import requests

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.registro import enmascarar

# Longitud máxima del detalle técnico conservado (evita volcar cuerpos enormes).
_MAX_DETALLE = 2000

HTTP_NODO_SIN_RUTA = 595
HTTP_NODO_TIMEOUT = 596
HTTP_FALLO_CUERPO = 597  # AnyEvent: fallo al recibir el cuerpo; la petición ya se procesó
ESTADOS_NODO_CAIDO = (HTTP_NODO_SIN_RUTA, HTTP_NODO_TIMEOUT, HTTP_FALLO_CUERPO)

# Códigos que indican un fallo de red/servidor (y no una respuesta definitiva).
CODIGOS_DE_RED = frozenset({CodigoError.SERVIDOR_NO_RESPONDE, CodigoError.NODO_NO_DISPONIBLE})

_RE_PERMISO = re.compile(
    r"Permission check failed \(\s*(?P<ruta>[^,)]*?)\s*,\s*(?P<priv>[^)]*?)\s*\)", re.IGNORECASE
)
_RE_VMID_EXISTE = re.compile(
    r"(?:VM|CT)\s+(?P<vmid>\d+)\s+already exists(?:\s+on node\s+'(?P<nodo>[^']*)')?", re.IGNORECASE
)
_RE_SIN_ESPACIO = re.compile(
    r"out of (?:data )?space|insufficient free space|no space left", re.IGNORECASE
)
_RE_FORMATO = re.compile(r"format error|invalid format", re.IGNORECASE)
_RE_CAMPO_FORMATO = re.compile(
    r"^\s*(?P<campo>[A-Za-z][\w-]*):\s.*?(?:invalid format|format error)",
    re.IGNORECASE | re.MULTILINE,
)
_RE_INEXISTENTE = re.compile(r"does not exist|no such|not found|does not exists", re.IGNORECASE)
_RE_ETIQUETA_RECHAZADA = re.compile(
    r"Sys\.Modify for modifying tags?\s*:?\s*['\"]?(?P<tag>[^\s'\")]+)?", re.IGNORECASE
)
_RE_ENTRE_COMILLAS = re.compile(r"['\"](?P<nombre>[^'\"]+)['\"]")
_RE_STORAGE = re.compile(
    r"storage\s+'(?P<id>[^']+)'|volume group\s+[\"'](?P<vg>[^\"']+)[\"']", re.IGNORECASE
)
_RE_NODO_EN_RUTA = re.compile(r"/nodes/(?P<nodo>[^/]+)")
# MVP 4 (docs/arquitectura/mvp4.md §8): textos de clonar, importar, subir y descargar.
_RE_CLON_NO_COMPARTIDO = re.compile(r"can't clone to non-shared storage", re.IGNORECASE)
_RE_CLON_SIN_IMAGES = re.compile(r"does not support vm images", re.IGNORECASE)
_RE_CLON_PARAMETRO = re.compile(r"not allowed for linked clones", re.IGNORECASE)
_RE_CLON_ENLAZADO = re.compile(r"Linked clone feature is not supported", re.IGNORECASE)
_RE_CLON_TPM = re.compile(r"cannot clone TPM state while VM is running", re.IGNORECASE)
_RE_CLON_ID_OCUPADO = re.compile(
    r"(?:unable to create VM\s+(?P<vmid>\d+)\s*:\s*)?config file already exists", re.IGNORECASE
)
_RE_RUTA_ABSOLUTA = re.compile(r"Only root can pass arbitrary filesystem paths", re.IGNORECASE)
_RE_IMAGEN_BACKING = re.compile(r"backing file not allowed for untrusted image", re.IGNORECASE)
_RE_NOMBRE_EXTENSION = re.compile(r"invalid filename or wrong extension", re.IGNORECASE)
_RE_CONTENIDO_NO_ADMITIDO = re.compile(
    r"does not support '(?P<contenido>[^']*)' content|is not configured for content-type",
    re.IGNORECASE,
)
_RE_MEDIA_CDROM = re.compile(r"explicit 'media=cdrom' is required", re.IGNORECASE)
_RE_REDUCIR_DISCO = re.compile(r"Shrinking disk size is not supported", re.IGNORECASE)


def limpiar_detalle(texto: str) -> str:
    """Enmascara secretos y acota la longitud del texto técnico."""
    limpio = enmascarar(str(texto)).strip()
    if len(limpio) > _MAX_DETALLE:
        limpio = limpio[:_MAX_DETALLE] + "..."
    return limpio


def nodo_de_ruta(ruta: str) -> str | None:
    """Extrae el nombre del nodo de una ruta ``/nodes/{nodo}/...`` (si lo hay)."""
    m = _RE_NODO_EN_RUTA.search(ruta)
    return m.group("nodo") if m else None


def _analizar_cuerpo(cuerpo: str) -> tuple[str, dict[str, str]]:
    """Devuelve ``(mensaje, errores)`` del cuerpo de una respuesta de error.

    Si es JSON usa ``message`` y ``errors``; si no, el texto plano es el mensaje.
    """
    texto = (cuerpo or "").strip()
    if not texto:
        return "", {}
    try:
        obj: Any = json.loads(texto)
    except ValueError:
        return texto, {}
    if not isinstance(obj, dict):
        return texto, {}
    mensaje = obj.get("message")
    errores = obj.get("errors")
    mapa = {str(k): str(v) for k, v in errores.items()} if isinstance(errores, dict) else {}
    return (str(mensaje) if mensaje else ""), mapa


def _clon_no_posible(motivo: str, detalle: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(CodigoError.CLON_NO_POSIBLE, {"motivo": motivo}, detalle)


def _parametro_invalido(campo: str, detalle: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.PARAMETRO_INVALIDO, {"campo": campo, "mensaje": detalle}, detalle
    )


def _clasificar_texto_origen(texto: str, detalle: str) -> ErrorProxLaunch | None:
    """Patrones del MVP 4 (clon, importación, subida y descarga). ``None`` si no casa ninguno."""
    if _RE_CLON_NO_COMPARTIDO.search(texto):
        return _clon_no_posible("no_compartido", detalle)
    if _RE_CLON_SIN_IMAGES.search(texto):
        return _clon_no_posible("sin_images", detalle)
    if _RE_CLON_PARAMETRO.search(texto):
        return _clon_no_posible("parametro_enlazado", detalle)
    if _RE_CLON_ENLAZADO.search(texto):
        return _clon_no_posible("enlazado_no_soportado", detalle)
    if _RE_CLON_TPM.search(texto):
        return _clon_no_posible("tpm_en_marcha", detalle)
    m = _RE_CLON_ID_OCUPADO.search(texto)
    if m:
        params = {"vmid": m.group("vmid")} if m.group("vmid") else {}
        return ErrorProxLaunch(CodigoError.CLON_ID_OCUPADO, params, detalle)
    if _RE_RUTA_ABSOLUTA.search(texto):
        return ErrorProxLaunch(CodigoError.RUTA_ABSOLUTA_NO_PERMITIDA, {}, detalle)
    if _RE_IMAGEN_BACKING.search(texto):
        return ErrorProxLaunch(CodigoError.IMAGEN_NO_ADMITIDA, {"motivo": "backing"}, detalle)
    if _RE_NOMBRE_EXTENSION.search(texto):
        return _parametro_invalido("filename", detalle)
    if _RE_CONTENIDO_NO_ADMITIDO.search(texto):
        return _parametro_invalido("content", detalle)
    if _RE_MEDIA_CDROM.search(texto):
        return _parametro_invalido("media", detalle)
    if _RE_REDUCIR_DISCO.search(texto):
        return _parametro_invalido("size", detalle)
    return None


def _clasificar_texto(
    texto: str, errores: Mapping[str, str] | None = None, nodo: str | None = None
) -> ErrorProxLaunch | None:
    """Reconoce los patrones de texto conocidos de Proxmox (sin mirar el estado HTTP).

    Devuelve ``None`` si el texto no coincide con ningún patrón.
    """
    errores = errores or {}
    detalle = limpiar_detalle(texto)

    m = _RE_PERMISO.search(texto)
    if m:
        return ErrorProxLaunch(
            CodigoError.PERMISO_INSUFICIENTE,
            {"privilegio": m.group("priv"), "ruta": m.group("ruta")},
            detalle,
        )

    nuevo = _clasificar_texto_origen(texto, detalle)
    if nuevo is not None:
        return nuevo

    m = _RE_VMID_EXISTE.search(texto)
    if m:
        params = {"vmid": m.group("vmid")}
        if m.group("nodo"):
            params["nodo"] = m.group("nodo")
        return ErrorProxLaunch(CodigoError.VMID_OCUPADO, params, detalle)

    if _RE_SIN_ESPACIO.search(texto):
        params = {}
        ms = _RE_STORAGE.search(texto)
        if ms:
            params["storage"] = ms.group("id") or ms.group("vg")
        return ErrorProxLaunch(CodigoError.SIN_ESPACIO, params, detalle)

    if _RE_FORMATO.search(texto):
        campo = ""
        for k, v in errores.items():
            if _RE_FORMATO.search(v):
                campo = k
                break
        if not campo:
            mc = _RE_CAMPO_FORMATO.search(texto)
            campo = mc.group("campo") if mc else ""
        return ErrorProxLaunch(CodigoError.ERROR_FORMATO, {"campo": campo}, detalle)

    if _RE_INEXISTENTE.search(texto):
        params = {}
        mq = _RE_ENTRE_COMILLAS.search(texto)
        if mq:
            params["recurso"] = mq.group("nombre")
        if nodo:
            params["nodo"] = nodo
        return ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, params, detalle)

    return None


def traducir_http(
    estado: int,
    motivo: str,
    cuerpo: str,
    *,
    nodo: str | None = None,
    sesion_ticket: bool = False,
) -> ErrorProxLaunch:
    """Traduce una respuesta HTTP de error de Proxmox.

    Args:
        estado: código HTTP.
        motivo: frase de estado (``reason``); Proxmox pone ahí el mensaje corto.
        cuerpo: cuerpo de la respuesta (JSON o texto).
        nodo: nodo de la petición, si se conoce (para 595/596/597).
        sesion_ticket: ``True`` si la petición iba con ticket; un 401 significa entonces
            sesión expirada y no credenciales inválidas.
    """
    mensaje, errores = _analizar_cuerpo(cuerpo)
    # Se recorta antes de deduplicar: el message del cuerpo trae un \n final y la frase HTTP no.
    partes = [
        p for p in (motivo.strip(), mensaje.strip(), *(v.strip() for v in errores.values())) if p
    ]
    texto = " | ".join(dict.fromkeys(partes))
    detalle = limpiar_detalle(f"HTTP {estado}: {texto}" if texto else f"HTTP {estado}")

    if estado == 401:
        codigo = (
            CodigoError.SESION_EXPIRADA if sesion_ticket else CodigoError.CREDENCIALES_INVALIDAS
        )
        return ErrorProxLaunch(codigo, {}, detalle)

    if estado in ESTADOS_NODO_CAIDO:
        params = {"nodo": nodo} if nodo else {}
        params["estado_http"] = str(estado)
        return ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, params, detalle)

    # E-L15: la política de etiquetas del sitio exige Sys.Modify (va antes del 403 genérico,
    # cuyo patrón de permiso también casaría con este texto).
    if estado == 403:
        me = _RE_ETIQUETA_RECHAZADA.search(texto)
        if me:
            params = {"tag": me.group("tag")} if me.group("tag") else {}
            return ErrorProxLaunch(CodigoError.ETIQUETA_RECHAZADA, params, detalle)

    clasificado = _clasificar_texto(texto, errores, nodo)
    if clasificado is not None:
        clasificado.detalle_tecnico = detalle
        return clasificado

    if estado == 403:
        return ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, detalle)
    if estado == 404:
        return ErrorProxLaunch(
            CodigoError.RECURSO_INEXISTENTE, {"nodo": nodo} if nodo else {}, detalle
        )
    if estado == 400 and errores:
        campo, valor = next(iter(errores.items()))
        return ErrorProxLaunch(
            CodigoError.PARAMETRO_INVALIDO,
            {"campo": campo, "mensaje": limpiar_detalle(valor)},
            detalle,
        )
    return ErrorProxLaunch(CodigoError.DESCONOCIDO, {"estado_http": str(estado)}, detalle)


def traducir_exitstatus(exitstatus: str | None) -> ErrorProxLaunch:
    """Traduce el ``exitstatus`` de una tarea terminada con error (CA-20.4)."""
    texto = exitstatus or ""
    # E-L15: con user-tag-access restringido el POST da 200 y la TAREA falla con este texto
    # (el nombre de la etiqueta puede salir como ``HASH(0x...)``: no se usa).
    me = _RE_ETIQUETA_RECHAZADA.search(texto)
    if me:
        tag = me.group("tag")
        params = {"tag": tag} if tag and not tag.upper().startswith("HASH") else {}
        return ErrorProxLaunch(CodigoError.ETIQUETA_RECHAZADA, params, limpiar_detalle(texto))
    clasificado = _clasificar_texto(texto)
    if clasificado is not None:
        return clasificado
    return ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, limpiar_detalle(texto))


def es_huella_distinta(exc: BaseException) -> bool:
    """Indica si la excepción de TLS es un fallo de ``assert_fingerprint``."""
    return "fingerprints did not match" in str(exc).lower()


def traducir_excepcion(exc: BaseException, *, host: str | None = None) -> ErrorProxLaunch:
    """Traduce una excepción de ``requests`` (o cualquier otra) a ``ErrorProxLaunch``."""
    if isinstance(exc, ErrorProxLaunch):
        return exc
    params = {"host": host} if host else {}
    detalle = limpiar_detalle(f"{type(exc).__name__}: {exc}")
    if isinstance(exc, requests.exceptions.SSLError):
        if es_huella_distinta(exc):
            return ErrorProxLaunch(CodigoError.HUELLA_CAMBIADA, params, detalle)
        return ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, params, detalle)
    if isinstance(exc, requests.exceptions.Timeout | requests.exceptions.ConnectionError):
        return ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, params, detalle)
    return ErrorProxLaunch(CodigoError.DESCONOCIDO, params, detalle)
