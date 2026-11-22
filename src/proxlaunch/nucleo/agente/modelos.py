"""Modelos de la espera de IP (RF-B3.3, DT-B8). Sin E/S."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from proxlaunch.nucleo.errores import ErrorProxLaunch


class EstadoIp(StrEnum):
    PENDIENTE = "pendiente"
    ESPERANDO = "esperando"
    OBTENIDA = "obtenida"
    OBTENIDA_PARCIAL = "obtenida_parcial"
    SIN_AGENTE = "sin_agente"
    AGENTE_NO_RESPONDE = "agente_no_responde"
    SIN_IP = "sin_ip"
    SIN_PERMISO = "sin_permiso"
    OMITIDA = "omitida"
    CANCELADA = "cancelada"
    ERROR = "error"


TERMINALES: Final[frozenset[EstadoIp]] = frozenset(
    {
        EstadoIp.OBTENIDA,
        EstadoIp.OBTENIDA_PARCIAL,
        EstadoIp.SIN_AGENTE,
        EstadoIp.AGENTE_NO_RESPONDE,
        EstadoIp.SIN_IP,
        EstadoIp.SIN_PERMISO,
        EstadoIp.OMITIDA,
        EstadoIp.CANCELADA,
        EstadoIp.ERROR,
    }
)

# Terminales sin IP útil que añaden el aviso ``ip_no_obtenida`` (RF-B3.5). No lo añaden
# ``omitida`` («no aplicable») ni ``cancelada`` (el usuario dejó de esperar o la MV se deshizo).
SIN_IP_UTIL: Final[frozenset[EstadoIp]] = frozenset(
    {
        EstadoIp.SIN_AGENTE,
        EstadoIp.AGENTE_NO_RESPONDE,
        EstadoIp.SIN_IP,
        EstadoIp.SIN_PERMISO,
        EstadoIp.ERROR,
    }
)


@dataclass(frozen=True)
class InterfazAgente:
    """Interfaz que informa el agente, ya saneada (texto no confiable)."""

    nombre: str
    mac: str | None
    ipv4: tuple[str, ...]
    ipv6: tuple[str, ...]


@dataclass(frozen=True)
class ResultadoIp:
    estado: EstadoIp
    principal: str | None = None
    otras: tuple[str, ...] = ()
    descartadas: tuple[str, ...] = ()  # R-B25 (Debería): interfaces descartadas
    sondeos: int = 0
    no_coincide: bool = False  # CA-B3.4.5 (IP fija distinta de la obtenida)
    error: ErrorProxLaunch | None = None
