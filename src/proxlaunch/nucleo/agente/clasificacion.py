"""Clasificación de los errores del sondeo del agente (RF-B3.3, R-B22). Puro.

Se mira el código y, después, el texto de ``detalle_tecnico``: Proxmox responde 500 a casi
todo y los mensajes del agente no son estables. Lo desconocido es ``TODAVIA_NO``.
"""

from __future__ import annotations

import re
from enum import StrEnum

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch


class Clase(StrEnum):
    TODAVIA_NO = "todavia_no"  # el agente aún no contesta: se sigue sondeando
    SIN_AGENTE = "sin_agente"  # la MV no tiene el agente configurado
    SIN_PERMISO = "sin_permiso"  # 403
    MV_NO_EXISTE = "mv_no_existe"  # la MV se deshizo
    FATAL = "fatal"  # sesión caducada o credenciales: no recuperable


_FATALES = frozenset(
    {
        CodigoError.SESION_EXPIRADA,
        CodigoError.CREDENCIALES_INVALIDAS,
        CodigoError.HUELLA_CAMBIADA,
        CodigoError.HUELLA_NO_CONFIADA,
    }
)
# Fallos de conexión con el servidor o el nodo (no del agente): QA-B1.
_CODIGOS_RED = frozenset({CodigoError.SERVIDOR_NO_RESPONDE, CodigoError.NODO_NO_DISPONIBLE})
_RE_SIN_AGENTE = re.compile(r"no qemu guest agent configured", re.IGNORECASE)
_RE_NO_EN_EJECUCION = re.compile(
    r"qemu guest agent is not running|vm \d+ (?:qmp command .* failed|is not running)|"
    r"vm is not running|not running",
    re.IGNORECASE,
)
_RE_MV_NO_EXISTE = re.compile(
    r"configuration file .* does not exist|vm \d+ does not exist|no such vm", re.IGNORECASE
)
_RE_PERMISO = re.compile(r"permission check failed", re.IGNORECASE)


def es_error_de_red(e: ErrorProxLaunch) -> bool:
    """El error es de conexión con Proxmox (servidor o nodo sin respuesta), no del agente.

    Sigue clasificándose como ``TODAVIA_NO`` (se reintenta), pero si el plazo vence con él como
    último error, la espera termina en ``ERROR`` y no en «el agente no responde» (QA-B1).
    """
    return e.codigo in _CODIGOS_RED


def clasificar_error(e: ErrorProxLaunch) -> Clase:
    """Clase del error de un sondeo. El código manda para permisos y sesión; el texto, para
    el agente; una respuesta 404/«no existe» es que la MV ya no está."""
    if e.codigo == CodigoError.PERMISO_INSUFICIENTE:
        return Clase.SIN_PERMISO
    if e.codigo in _FATALES:
        return Clase.FATAL
    texto = e.detalle_tecnico or ""
    if _RE_SIN_AGENTE.search(texto) or e.codigo == CodigoError.AGENTE_NO_CONFIGURADO:
        return Clase.SIN_AGENTE
    if _RE_PERMISO.search(texto):
        return Clase.SIN_PERMISO
    if _RE_NO_EN_EJECUCION.search(texto) or e.codigo in (
        CodigoError.AGENTE_NO_RESPONDE,
        CodigoError.MV_NO_EN_MARCHA,
    ):
        return Clase.TODAVIA_NO
    if _RE_MV_NO_EXISTE.search(texto) or e.codigo == CodigoError.RECURSO_INEXISTENTE:
        return Clase.MV_NO_EXISTE
    return Clase.TODAVIA_NO
