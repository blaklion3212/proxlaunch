"""Modelos del firewall de la máquina de la fase C (C3). Puro, sin E/S.

``ConfiguracionVM.firewall`` referencia ``FirewallMV``; la lógica (reglas, lecturas, validación)
es de otros módulos del paquete. Todo texto del servidor (grupos, comentarios) es no confiable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

RE_GRUPO: Final = re.compile(r"^[A-Za-z][A-Za-z0-9\-_]{1,17}$")  # V-C31
COMENTARIO_REGLA: Final = "ProxLaunch"


class Politica(StrEnum):
    BLOQUEAR = "bloquear"
    PERMITIR = "permitir"


VALOR_POLITICA: Final[Mapping[Politica, str]] = {
    Politica.BLOQUEAR: "DROP",
    Politica.PERMITIR: "ACCEPT",
}


class ModoDhcp(StrEnum):
    AUTO = "auto"  # dhcp=1 si alguna tarjeta usa DHCP por cloud-init (RF-C3.4)
    SI = "si"
    NO = "no"


@dataclass(frozen=True)
class FirewallMV:
    activo: bool = False
    grupo: str | None = None  # None = sin grupo
    politica_entrada: Politica = Politica.BLOQUEAR
    politica_salida: Politica = Politica.PERMITIR
    dhcp: ModoDhcp = ModoDhcp.AUTO
    acepto_aislada: bool = (
        False  # casilla «Entiendo que la máquina no aceptará conexiones…» (V-C36)
    )


@dataclass(frozen=True)
class FirewallParcial:
    """Celdas de una fila de CSV; ``None`` = hereda del formulario."""

    activo: bool | None = None
    grupo: str | None = None
    politica_entrada: Politica | None = None
    politica_salida: Politica | None = None


@dataclass(frozen=True)
class GrupoSeguridad:
    nombre: str  # ya validado con RE_GRUPO (los que no cumplen no se listan)
    comentario: str = ""  # saneado, ≤ 128


@dataclass(frozen=True)
class ReglaFirewall:
    tipo: str  # "in" | "out" | "group" (otros: se conservan tal cual)
    accion: str  # ACCEPT/DROP/REJECT, macro o nombre de grupo (tipo "group")
    activa: bool
    comentario: str = ""


@dataclass(frozen=True)
class LecturaGrupos:
    grupos: tuple[GrupoSeguridad, ...] | None  # None = ilegible (V-C32)
    error: ErrorProxLaunch | None = None


@dataclass(frozen=True)
class FirewallPlantilla:
    legible: bool  # False → aviso de CA-C3.6.5
    activo: bool | None = None
    grupos: frozenset[str] = frozenset()  # reglas type=group ya presentes
    con_reglas: bool | None = None


@dataclass(frozen=True)
class InfoFirewall:
    """Lecturas de «Comprobar» (DT-C11)."""

    grupos: tuple[GrupoSeguridad, ...] | None
    error_grupos: ErrorProxLaunch | None = None
    general_activo: bool | None = None  # None = no se pudo leer (V-C34)
    # None = no se pudo leer
    entrada_por_grupo: Mapping[str, bool | None] = field(default_factory=dict)
    # por VMID de plantilla
    plantillas: Mapping[int, FirewallPlantilla] = field(default_factory=dict)


def usa_firewall(fw: FirewallMV | None) -> bool:
    """``True`` si el firewall de la máquina está activado en la configuración."""
    return fw is not None and fw.activo


# --- Serialización (ida y vuelta de ``ConfiguracionVM.a_dict`` / ``desde_dict``) ---------------


def _invalido(campo: str, valor: object) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.PARAMETRO_INVALIDO, {"campo": campo, "valor": type(valor).__name__}
    )


def firewall_a_dict(fw: FirewallMV) -> dict[str, object]:
    """Serializa el firewall (tolerante: nunca lanza). ``grupo`` solo si hay uno."""
    d: dict[str, object] = {"activo": fw.activo}
    if fw.grupo is not None:
        d["grupo"] = fw.grupo
    d["politica_entrada"] = str(fw.politica_entrada)
    d["politica_salida"] = str(fw.politica_salida)
    d["dhcp"] = str(fw.dhcp)
    d["acepto_aislada"] = fw.acepto_aislada
    return d


def _enum(tipo: type[StrEnum], valor: Any, campo: str) -> Any:
    try:
        return tipo(valor)
    except ValueError:
        raise _invalido(campo, valor) from None


def _booleano(d: Mapping[str, object], clave: str) -> bool:
    valor = d.get(clave, False)
    if not isinstance(valor, bool):
        raise _invalido(f"firewall.{clave}", valor)
    return valor


def firewall_desde_dict(d: Mapping[str, object]) -> FirewallMV:
    """Reconstruye el firewall desde ``firewall_a_dict``.

    Raises:
        ErrorProxLaunch: ``PARAMETRO_INVALIDO`` con ``params["campo"]`` = ruta del campo malo.
    """
    if not isinstance(d, Mapping):
        raise _invalido("firewall", d)
    grupo = d.get("grupo")
    if grupo is not None and not isinstance(grupo, str):
        raise _invalido("firewall.grupo", grupo)
    return FirewallMV(
        activo=_booleano(d, "activo"),
        grupo=grupo,
        politica_entrada=_enum(
            Politica,
            d.get("politica_entrada", Politica.BLOQUEAR.value),
            "firewall.politica_entrada",
        ),
        politica_salida=_enum(
            Politica, d.get("politica_salida", Politica.PERMITIR.value), "firewall.politica_salida"
        ),
        dhcp=_enum(ModoDhcp, d.get("dhcp", ModoDhcp.AUTO.value), "firewall.dhcp"),
        acepto_aislada=_booleano(d, "acepto_aislada"),
    )
