"""Construcción del ``PUT config`` de cloud-init (RF-B1.17, DT-B4, RF-B4.5). Puro.

El diccionario nunca lleva ``cipassword`` (va en un ``PUT`` propio, ``configurar_contrasena``).
Solo se envían las claves que el usuario fijó (RF-B1.13) y ``delete`` solo para ``cicustom``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from proxlaunch.nucleo.cloudinit.claves import analizar_claves, codificar_sshkeys
from proxlaunch.nucleo.cloudinit.modelos import (
    NINGUNO,
    TIPOS_SNIPPET,
    CicustomHeredado,
    ConfigCloudInit,
    InfoCloudInitPlantilla,
    ModoTarjeta,
    SnippetsCloudInit,
)
from proxlaunch.nucleo.cloudinit.red import (
    dominio_valido,
    motivo_cidr,
    motivo_puerta,
    normalizar_dns,
    valor_ipconfig,
)
from proxlaunch.nucleo.cloudinit.snippets import volid_snippet_valido
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.secreto import MASCARA

ORDEN_CLAVES: Final[tuple[str, ...]] = (
    "ciuser",
    "sshkeys",
    *(f"ipconfig{i}" for i in range(32)),
    "nameserver",
    "searchdomain",
    "ciupgrade",
    "cicustom",
    "delete",
    "agent",
)
_POSICION: Final = {clave: i for i, clave in enumerate(ORDEN_CLAVES)}

_RE_USUARIO_PROHIBIDO = re.compile(r"[\s:\x00-\x1f\x7f-\x9f]")

PARAMETROS_CONTRASENA_SIMULADOS: Final[Mapping[str, str]] = MappingProxyType(
    {"cipassword": MASCARA}
)


def valor_cicustom(
    s: SnippetsCloudInit, heredado: CicustomHeredado | None
) -> tuple[str | None, bool]:
    """Valor de ``cicustom`` combinando lo heredado con lo elegido (RF-B4.5).

    Devuelve ``(valor, borrar)``: ``valor`` ``None`` = no enviar ``cicustom``; ``borrar`` True =
    enviar ``delete=cicustom`` (quedó vacío y la plantilla traía algo). Parte de lo heredado,
    sobrescribe los tipos elegidos y quita los ``ninguno``. Un heredado no interpretable no se
    toca.
    """
    if s.como_la_plantilla:
        return None, False
    if heredado is not None and not heredado.interpretable:
        return None, False
    resultado: dict[str, str] = dict(heredado.tipos) if heredado is not None else {}
    for tipo in TIPOS_SNIPPET:
        elegido: str | None = getattr(s, tipo)
        if elegido is None:
            continue
        if elegido == NINGUNO:
            resultado.pop(tipo, None)
        else:
            resultado[tipo] = elegido
    if not resultado:
        return None, bool(heredado is not None and heredado.tipos)
    return ",".join(f"{t}={resultado[t]}" for t in TIPOS_SNIPPET if t in resultado), False


def _invalido(campo: str) -> ErrorProxLaunch:
    """``PARAMETRO_INVALIDO`` que solo nombra el campo (nunca su valor)."""
    return ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": campo})


def _revalidar(ci: ConfigCloudInit) -> None:
    """Defensa en profundidad (I2): lo que va al servidor se vuelve a comprobar aquí, aunque la
    validación del plan ya lo hiciera, por si un valor llega por otro camino (archivo, CSV).

    Raises:
        ErrorProxLaunch: ``PARAMETRO_INVALIDO`` con ``campo`` si algo no es válido.
    """
    if ci.usuario and (not isinstance(ci.usuario, str) or _RE_USUARIO_PROHIBIDO.search(ci.usuario)):
        raise _invalido("cloudinit.usuario")
    if ci.claves:
        resultado = analizar_claves("\n".join(ci.claves))
        if resultado.problemas or resultado.duplicadas or resultado.claves != tuple(ci.claves):
            raise _invalido("cloudinit.claves")
    for t in ci.tarjetas:
        if t.modo != ModoTarjeta.FIJA:
            continue  # la puerta de una tarjeta que no es fija no viaja (``valor_ipconfig``)
        if motivo_cidr(t.ip or "") is not None:
            raise _invalido(f"cloudinit.tarjetas[{t.indice}].ip")
        if t.puerta and motivo_puerta(t.ip or "", t.puerta) is not None:
            raise _invalido(f"cloudinit.tarjetas[{t.indice}].puerta")
    if ci.dns and (
        any(not isinstance(d, str) or not d for d in ci.dns)
        or normalizar_dns(" ".join(ci.dns))[1] is not None
    ):
        raise _invalido("cloudinit.dns")
    if ci.dominio and not dominio_valido(ci.dominio):
        raise _invalido("cloudinit.dominio")
    if ci.actualizar is not None and not isinstance(ci.actualizar, bool):
        raise _invalido("cloudinit.actualizar")
    for tipo, volid in ci.snippets.elegidos().items():
        if not volid_snippet_valido(volid):
            raise _invalido(f"cloudinit.snippets.{tipo}")


def construir_put_cloudinit(ci: ConfigCloudInit, info: InfoCloudInitPlantilla) -> dict[str, str]:
    """Parámetros del ``PUT config`` de cloud-init (sin ``cipassword``); ``{}`` si no hay nada.

    ``agent=1`` solo si ``activar_agente`` y la plantilla no lo tiene ya. Revalida los valores
    (I2) y lanza ``PARAMETRO_INVALIDO`` si alguno no es válido.
    """
    _revalidar(ci)
    p: dict[str, str] = {}
    if ci.usuario:
        p["ciuser"] = ci.usuario
    if ci.claves:
        p["sshkeys"] = codificar_sshkeys(ci.claves)
    for t in ci.tarjetas:
        valor = valor_ipconfig(t)
        if valor is not None:
            p[f"ipconfig{t.indice}"] = valor
    if ci.dns:
        p["nameserver"] = " ".join(ci.dns)
    if ci.dominio:
        p["searchdomain"] = ci.dominio
    if ci.actualizar is not None:
        p["ciupgrade"] = "1" if ci.actualizar else "0"
    cicustom, borrar = valor_cicustom(ci.snippets, info.cicustom)
    if cicustom is not None:
        p["cicustom"] = cicustom
    elif borrar:
        p["delete"] = "cicustom"
    if ci.activar_agente and info.agente is not True:
        p["agent"] = "1"
    return dict(sorted(p.items(), key=lambda kv: _POSICION.get(kv[0], len(_POSICION))))


def parametros_simulados(put: Mapping[str, str], ci: ConfigCloudInit) -> dict[str, str]:
    """Como el ``PUT``, pero ``sshkeys`` es ``[n]`` (nunca el cuerpo de las claves)."""
    simulados = dict(put)
    if "sshkeys" in simulados:
        simulados["sshkeys"] = f"[{len(ci.claves)}]"
    return simulados
