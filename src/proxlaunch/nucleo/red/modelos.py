"""Modelos de la red del clon y de las tarjetas de red de la fase C (C2, C4). Puro, sin E/S.

``ConfiguracionVM.red_clon`` referencia ``RedClon``; la lógica (interpretar tarjetas, reescribir,
validar) es de otros módulos del paquete. Todo texto que venga de la config de Proxmox es no
confiable (RNF-C6).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

# Bridge o VNet que puede ir a una petición.
RE_NOMBRE_RED: Final = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
# Simulación: la MAC real la genera Proxmox al clonar.
MAC_SIMULADA: Final = "XX:XX:XX:XX:XX:XX"
MAX_TARJETAS: Final = 32  # net0..net31 (= validacion.MAX_INTERFACES_RED)

# Valores de ``ModeloRed`` (``modelos.vm``); se repiten aquí para no importar ``vm`` (ciclo).
_MODELOS_VALIDOS: Final = ("virtio", "e1000")


class ModoRedClon(StrEnum):
    PLANTILLA = "plantilla"
    PERSONALIZAR = "personalizar"


class AccionTarjeta(StrEnum):
    CONSERVAR = "conservar"
    CAMBIAR = "cambiar"
    QUITAR = "quitar"
    ANADIR = "añadir"  # con «ñ» tal como el requisito (el JSON es UTF-8)


class CampoRed(StrEnum):
    BRIDGE = "bridge"
    MODELO = "modelo"
    VLAN = "vlan"
    MTU = "mtu"
    LIMITE = "limite_mb"


@dataclass(frozen=True)
class TarjetaClon:
    """Lo que el usuario pide para la tarjeta ``net<indice>`` del clon."""

    indice: int  # 0..31
    accion: AccionTarjeta = AccionTarjeta.CONSERVAR
    bridge: str | None = None
    modelo: str | None = None  # "virtio" | "e1000" (valores de ModeloRed)
    vlan: int | None = None
    mtu: int | None = None
    limite_mb: float | None = None
    # CAMBIAR: campos que se aplican (los demás se conservan; uno fijado a None se quita).
    # AÑADIR: se ignoran (se usan todos los valores).
    fijados: frozenset[CampoRed] = frozenset()
    mac_nueva: bool = False


@dataclass(frozen=True)
class RedClon:
    modo: ModoRedClon = ModoRedClon.PLANTILLA
    tarjetas: tuple[TarjetaClon, ...] = ()

    @property
    def personaliza(self) -> bool:
        """``True`` si el usuario eligió personalizar la red del clon."""
        return self.modo == ModoRedClon.PERSONALIZAR

    def tarjeta(self, indice: int) -> TarjetaClon | None:
        """La petición para ``net<indice>``; ``None`` si no hay ninguna."""
        for t in self.tarjetas:
            if t.indice == indice:
                return t
        return None


@dataclass(frozen=True)
class TarjetaPlantilla:
    """Una ``netN`` interpretada de una config (de la plantilla o del clon). Texto no confiable."""

    indice: int
    legible: bool
    modelo: str | None = None
    mac: str | None = None
    bridge: str | None = None
    vlan: int | None = None
    firewall: bool = False
    mtu: int | None = None
    limite_mb: float | None = None
    otras: tuple[
        tuple[str, str], ...
    ] = ()  # opciones no gestionadas, en su orden, para reenviarlas


@dataclass(frozen=True)
class TarjetaFinal:
    """Resultado por tarjeta para el informe (RF-C4.8)."""

    indice: int
    accion: AccionTarjeta
    modelo: str | None
    red: str | None
    vlan: int | None
    mac_conservada: bool
    firewall: bool


@dataclass(frozen=True)
class PeticionRed:
    parametros: dict[str, str]  # netN=…, delete=…, digest=…
    finales: tuple[TarjetaFinal, ...]
    # "red_mtu_ignorada:net0", "red_tarjeta_ilegible:net2", "red_mac_nueva:net0"
    avisos: tuple[str, ...] = ()


def usa_red_clon(red: RedClon | None) -> bool:
    """``True`` si hay una red del clon personalizada."""
    return red is not None and red.personaliza


# --- Serialización (ida y vuelta de ``ConfiguracionVM.a_dict`` / ``desde_dict``) ---------------


def _invalido(campo: str, valor: object) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.PARAMETRO_INVALIDO, {"campo": campo, "valor": type(valor).__name__}
    )


def _tarjeta_a_dict(t: TarjetaClon) -> dict[str, object]:
    d: dict[str, object] = {"indice": t.indice, "accion": str(t.accion)}
    valores: dict[CampoRed, object] = {
        CampoRed.BRIDGE: t.bridge,
        CampoRed.MODELO: t.modelo,
        CampoRed.VLAN: t.vlan,
        CampoRed.MTU: t.mtu,
        CampoRed.LIMITE: t.limite_mb,
    }
    for campo, valor in valores.items():
        if t.accion == AccionTarjeta.CAMBIAR:
            # Una clave presente = campo fijado (``null`` = quitar ese valor).
            if campo in t.fijados:
                d[campo.value] = valor
        elif t.accion == AccionTarjeta.ANADIR and valor is not None:
            d[campo.value] = valor
    if t.mac_nueva:
        d["mac_nueva"] = True
    return d


def red_clon_a_dict(red: RedClon) -> dict[str, object]:
    """Serializa la red del clon (tolerante: nunca lanza)."""
    return {"modo": str(red.modo), "tarjetas": [_tarjeta_a_dict(t) for t in red.tarjetas]}


def _opcional(d: Mapping[str, object], clave: str, ruta: str, tipos: tuple[type, ...]) -> Any:
    valor = d.get(clave)
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, tipos):
        raise _invalido(f"{ruta}.{clave}", valor)
    return valor


def _tarjeta_desde_dict(d: object, ruta: str) -> TarjetaClon:
    if not isinstance(d, Mapping):
        raise _invalido(ruta, d)
    indice = d.get("indice")
    if isinstance(indice, bool) or not isinstance(indice, int) or not 0 <= indice < MAX_TARJETAS:
        raise _invalido(f"{ruta}.indice", indice)
    try:
        accion = AccionTarjeta(d.get("accion", AccionTarjeta.CONSERVAR.value))
    except ValueError:
        raise _invalido(f"{ruta}.accion", d.get("accion")) from None
    bridge = _opcional(d, "bridge", ruta, (str,))
    if bridge is not None and RE_NOMBRE_RED.fullmatch(bridge) is None:
        raise _invalido(f"{ruta}.bridge", bridge)
    modelo = _opcional(d, "modelo", ruta, (str,))
    if modelo is not None and modelo not in _MODELOS_VALIDOS:
        raise _invalido(f"{ruta}.modelo", modelo)
    vlan = _opcional(d, "vlan", ruta, (int,))
    mtu = _opcional(d, "mtu", ruta, (int,))
    limite = _opcional(d, "limite_mb", ruta, (int, float))
    mac_nueva = d.get("mac_nueva", False)
    if not isinstance(mac_nueva, bool):
        raise _invalido(f"{ruta}.mac_nueva", mac_nueva)
    fijados: frozenset[CampoRed] = frozenset()
    if accion == AccionTarjeta.CAMBIAR:
        fijados = frozenset(c for c in CampoRed if c.value in d)
    return TarjetaClon(
        indice=indice,
        accion=accion,
        bridge=bridge,
        modelo=modelo,
        vlan=vlan,
        mtu=mtu,
        limite_mb=None if limite is None else float(limite),
        fijados=fijados,
        mac_nueva=mac_nueva,
    )


def red_clon_desde_dict(d: Mapping[str, object]) -> RedClon:
    """Reconstruye la red del clon desde ``red_clon_a_dict``.

    Raises:
        ErrorProxLaunch: ``PARAMETRO_INVALIDO`` con ``params["campo"]`` = ruta del campo malo.
    """
    if not isinstance(d, Mapping):
        raise _invalido("red_clon", d)
    try:
        modo = ModoRedClon(str(d.get("modo", ModoRedClon.PLANTILLA.value)))
    except ValueError:
        raise _invalido("red_clon.modo", d.get("modo")) from None
    tarjetas = d.get("tarjetas", [])
    if not isinstance(tarjetas, (list, tuple)):
        raise _invalido("red_clon.tarjetas", tarjetas)
    return RedClon(
        modo=modo,
        tarjetas=tuple(
            _tarjeta_desde_dict(t, f"red_clon.tarjetas[{i}]") for i, t in enumerate(tarjetas)
        ),
    )
