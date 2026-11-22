"""Ida y vuelta de ``ConfigCloudInit`` para ``ConfiguracionVM.a_dict`` / ``desde_dict`` (DT-B12).

La contraseña NUNCA se escribe: si había una, se anota el indicador neutro ``con_acceso_local``
(un nombre que no dispara ``es_clave_credencial``). Todo campo con su valor por defecto se
omite. ``desde_dict`` valida enumeraciones y tipos básicos y lanza ``ErrorProxLaunch``
(``PARAMETRO_INVALIDO``) con la ruta del campo; la lectura estricta de los archivos es de
``archivos.esquema_*``.
"""

from __future__ import annotations

from typing import Any

from proxlaunch.nucleo.cloudinit.modelos import (
    TIPOS_SNIPPET,
    ConfigCloudInit,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch


def _invalido(campo: str, valor: object) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.PARAMETRO_INVALIDO, {"campo": campo, "valor": type(valor).__name__}
    )


def _tarjeta_a_dict(t: TarjetaCloudInit) -> dict[str, Any]:
    d: dict[str, Any] = {"indice": t.indice, "modo": str(t.modo)}
    if t.ip is not None:
        d["ip"] = t.ip
    if t.serie:
        d["serie"] = True
    if t.puerta is not None:
        d["puerta"] = t.puerta
    return d


def a_dict(ci: ConfigCloudInit) -> dict[str, Any]:
    """Serializa sin contraseña; ``serie_inicial`` (calculado) tampoco se escribe."""
    d: dict[str, Any] = {}
    if ci.usuario:
        d["usuario"] = ci.usuario
    if ci.claves:
        d["claves"] = list(ci.claves)
    if ci.tarjetas:
        d["tarjetas"] = [_tarjeta_a_dict(t) for t in ci.tarjetas]
    if ci.dns:
        d["dns"] = list(ci.dns)
    if ci.dominio:
        d["dominio"] = ci.dominio
    if ci.actualizar is not None:
        d["actualizar"] = ci.actualizar
    snippets = {t: getattr(ci.snippets, t) for t in TIPOS_SNIPPET if getattr(ci.snippets, t)}
    if snippets:
        d["snippets"] = snippets
    if ci.activar_agente:
        d["activar_agente"] = True
    if ci.contrasena is not None and ci.contrasena.definido:
        d["con_acceso_local"] = True
    return d


def _texto(d: dict[str, Any], clave: str, ruta: str) -> str:
    valor = d.get(clave, "")
    if not isinstance(valor, str):
        raise _invalido(f"{ruta}.{clave}", valor)
    return valor


def _textos(d: dict[str, Any], clave: str, ruta: str) -> tuple[str, ...]:
    valor = d.get(clave, [])
    if not isinstance(valor, list) or not all(isinstance(x, str) for x in valor):
        raise _invalido(f"{ruta}.{clave}", valor)
    return tuple(valor)


def _tarjeta_desde_dict(d: Any, ruta: str) -> TarjetaCloudInit:
    if not isinstance(d, dict):
        raise _invalido(ruta, d)
    indice = d.get("indice")
    if not isinstance(indice, int) or isinstance(indice, bool):
        raise _invalido(f"{ruta}.indice", indice)
    try:
        modo = ModoTarjeta(d.get("modo", ModoTarjeta.SIN_CONFIGURAR))
    except ValueError:
        raise _invalido(f"{ruta}.modo", d.get("modo")) from None
    ip, puerta = d.get("ip"), d.get("puerta")
    for nombre, valor in (("ip", ip), ("puerta", puerta)):
        if valor is not None and not isinstance(valor, str):
            raise _invalido(f"{ruta}.{nombre}", valor)
    return TarjetaCloudInit(
        indice=indice, modo=modo, ip=ip, serie=bool(d.get("serie", False)), puerta=puerta
    )


def desde_dict(d: Any, ruta: str = "cloudinit") -> ConfigCloudInit:
    """Reconstruye la configuración desde ``a_dict``. La contraseña queda en ``None``."""
    if not isinstance(d, dict):
        raise _invalido(ruta, d)
    tarjetas_crudas = d.get("tarjetas", [])
    if not isinstance(tarjetas_crudas, list):
        raise _invalido(f"{ruta}.tarjetas", tarjetas_crudas)
    tarjetas = tuple(
        sorted(
            (
                _tarjeta_desde_dict(t, f"{ruta}.tarjetas[{i}]")
                for i, t in enumerate(tarjetas_crudas)
            ),
            key=lambda t: t.indice,
        )
    )
    crudos = d.get("snippets", {})
    if not isinstance(crudos, dict) or not all(
        k in TIPOS_SNIPPET and isinstance(v, str) for k, v in crudos.items()
    ):
        raise _invalido(f"{ruta}.snippets", crudos)
    actualizar = d.get("actualizar")
    if actualizar is not None and not isinstance(actualizar, bool):
        raise _invalido(f"{ruta}.actualizar", actualizar)
    return ConfigCloudInit(
        usuario=_texto(d, "usuario", ruta),
        claves=_textos(d, "claves", ruta),
        tarjetas=tarjetas,
        dns=_textos(d, "dns", ruta),
        dominio=_texto(d, "dominio", ruta),
        actualizar=actualizar,
        snippets=SnippetsCloudInit(**crudos),
        activar_agente=bool(d.get("activar_agente", False)),
    )
