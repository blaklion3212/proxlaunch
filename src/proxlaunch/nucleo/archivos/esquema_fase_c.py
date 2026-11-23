"""Lista blanca de la red del clon y del firewall de la fase C en archivos de lote (RF-C6.1).

Cubre las claves ``red_clon`` y ``firewall`` (en la configuración de una MV, en las opciones de
lote y, como ``FirewallParcial``, en las opciones de una fila). Todo es opcional y se omite si vale
su defecto: un lote sin nada de la fase C queda idéntico al de 0.7.0 (y con su misma versión).

La serialización la hace el modelo (``red_clon_a_dict``/``firewall_a_dict``, fase C, I1); aquí se
añaden los controles de archivo: el lector valida tipo y RANGO con la ruta del campo
(``…red_clon.tarjetas[0].vlan``, CA-C6.1.6) y el escritor pasa lo que produce por ese mismo lector
(si lo rechazaría no se guarda: ``ARCHIVO_NO_GUARDABLE``) y rechaza textos con aspecto de token
(``exigir_sin_credencial``).

En una tarjeta ``cambiar`` una clave presente es un campo fijado (``null`` = quitar ese valor) y una
ausente se conserva; por eso el lector rellena ``TarjetaClon.fijados`` con las claves que ve.
"""

from __future__ import annotations

import math

from proxlaunch.nucleo.archivos.esquema import LectorEsquema, MotivoCampo
from proxlaunch.nucleo.archivos.texto import exigir_sin_credencial
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import (
    RE_GRUPO,
    FirewallMV,
    FirewallParcial,
    ModoDhcp,
    Politica,
    firewall_a_dict,
)
from proxlaunch.nucleo.modelos.vm import (
    MAX_LIMITE_MB,
    MTU_IGUAL_BRIDGE,
    MTU_MAX,
    MTU_MIN,
)
from proxlaunch.nucleo.red.modelos import (
    MAX_TARJETAS,
    RE_NOMBRE_RED,
    AccionTarjeta,
    CampoRed,
    ModoRedClon,
    RedClon,
    TarjetaClon,
    red_clon_a_dict,
    usa_red_clon,
)

# Rango de VLAN de Proxmox (V-15 / V-C15); se repite aquí para no importar ``validacion`` (ciclo).
_VLAN_MIN, _VLAN_MAX = 1, 4094
_MODELOS_RED = ("virtio", "e1000")

CLAVES_RED_CLON = frozenset({"modo", "tarjetas"})
CLAVES_TARJETA_CLON = frozenset(
    {"indice", "accion", "bridge", "modelo", "vlan", "mtu", "limite_mb", "mac_nueva"}
)
CLAVES_FIREWALL = frozenset(
    {"activo", "grupo", "politica_entrada", "politica_salida", "dhcp", "acepto_aislada"}
)
CLAVES_FIREWALL_PARCIAL = frozenset({"activo", "grupo", "politica_entrada", "politica_salida"})


def _no_guardable(campo: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "caracteres", "campo": campo}
    )


def _ruta(base: str, clave: str) -> str:
    return f"{base}.{clave}" if base else clave


# --- Qué versión de archivo hace falta ----------------------------------------------------------


def red_clon_requiere_v5(red: RedClon | None) -> bool:
    """¿La red del clon se personaliza (cambiar, añadir o quitar tarjetas)? Si no, no se escribe."""
    return usa_red_clon(red)


def firewall_requiere_v5(fw: FirewallMV | None) -> bool:
    """¿El firewall tiene algo distinto del defecto (``FirewallMV()``)? Si no, no se escribe."""
    return fw is not None and fw != FirewallMV()


def firewall_parcial_requiere_v5(fw: FirewallParcial | None) -> bool:
    """¿Alguna celda de firewall de la fila está fijada (no hereda)?"""
    return fw is not None and fw != FirewallParcial()


# --- Lectura ------------------------------------------------------------------------------------


def _leer_campo_tarjeta(
    lector: LectorEsquema, obj: dict[str, object], clave: str, ruta: str
) -> object | None:
    """Valor de un campo de la tarjeta ``clave`` ya validado (``None`` si falta, es ``null`` o
    es inválido: el error queda anotado)."""
    if clave not in obj or obj[clave] is None:
        return None
    campo = _ruta(ruta, clave)
    valor = obj[clave]
    if clave == "bridge":
        texto = lector.texto(obj, clave, ruta, minimo=1, maximo=40, sin_token=True)
        if texto is not None and RE_NOMBRE_RED.fullmatch(texto) is None:
            lector.error(campo, MotivoCampo.TEXTO_NO_VALIDO)
            return None
        return texto
    if clave == "modelo":
        if not isinstance(valor, str):
            lector.error(campo, MotivoCampo.TIPO)
        elif valor not in _MODELOS_RED:
            lector.error(campo, MotivoCampo.ENUM, validos=", ".join(_MODELOS_RED))
        else:
            return valor
        return None
    if clave == "vlan":
        return lector.entero(obj, clave, ruta, minimo=_VLAN_MIN, maximo=_VLAN_MAX)
    if clave == "mtu":
        mtu = lector.entero(obj, clave, ruta, minimo=MTU_IGUAL_BRIDGE, maximo=MTU_MAX)
        if mtu is not None and mtu != MTU_IGUAL_BRIDGE and mtu < MTU_MIN:
            lector.error(campo, MotivoCampo.RANGO, minimo=str(MTU_MIN), maximo=str(MTU_MAX))
            return None
        return mtu
    # limite_mb: real finito, > 0 y hasta ``MAX_LIMITE_MB``.
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        lector.error(campo, MotivoCampo.TIPO)
        return None
    if not math.isfinite(valor) or not 0 < valor <= MAX_LIMITE_MB:
        lector.error(campo, MotivoCampo.RANGO, minimo="0", maximo=str(MAX_LIMITE_MB))
        return None
    return float(valor)


def _leer_tarjeta(lector: LectorEsquema, valor: object, ruta: str) -> TarjetaClon | None:
    obj = lector.objeto(valor, ruta, CLAVES_TARJETA_CLON)
    if obj is None:
        return None
    n0 = len(lector.errores)
    indice = lector.entero(obj, "indice", ruta, minimo=0, maximo=MAX_TARJETAS - 1)
    accion = lector.enumerado(
        obj, "accion", ruta, AccionTarjeta, requerido=False, defecto=AccionTarjeta.CONSERVAR
    )
    mac_nueva = lector.booleano(obj, "mac_nueva", ruta, requerido=False, defecto=False)
    bridge = _leer_campo_tarjeta(lector, obj, "bridge", ruta)
    modelo = _leer_campo_tarjeta(lector, obj, "modelo", ruta)
    vlan = _leer_campo_tarjeta(lector, obj, "vlan", ruta)
    mtu = _leer_campo_tarjeta(lector, obj, "mtu", ruta)
    limite = _leer_campo_tarjeta(lector, obj, "limite_mb", ruta)
    if len(lector.errores) > n0 or indice is None or accion is None or mac_nueva is None:
        return None
    fijados: frozenset[CampoRed] = frozenset()
    if accion == AccionTarjeta.CAMBIAR:
        fijados = frozenset(c for c in CampoRed if c.value in obj)
    return TarjetaClon(
        indice=indice,
        accion=accion,
        bridge=bridge if isinstance(bridge, str) else None,
        modelo=modelo if isinstance(modelo, str) else None,
        vlan=vlan if isinstance(vlan, int) else None,
        mtu=mtu if isinstance(mtu, int) else None,
        limite_mb=limite if isinstance(limite, float) else None,
        fijados=fijados,
        mac_nueva=mac_nueva,
    )


def leer_red_clon(lector: LectorEsquema, valor: object, ruta: str) -> RedClon | None:
    """Lee ``red_clon`` {``modo``, ``tarjetas``}. ``None`` ante un error (anotado en el lector)."""
    obj = lector.objeto(valor, ruta, CLAVES_RED_CLON)
    if obj is None:
        return None
    n0 = len(lector.errores)
    modo = lector.enumerado(
        obj, "modo", ruta, ModoRedClon, requerido=False, defecto=ModoRedClon.PLANTILLA
    )
    items = lector.lista(obj, "tarjetas", ruta, maximo=MAX_TARJETAS, requerido=False)
    base = _ruta(ruta, "tarjetas")
    tarjetas: list[TarjetaClon] = []
    vistos: set[int] = set()
    for i, item in enumerate(items or []):
        tarjeta = _leer_tarjeta(lector, item, f"{base}[{i}]")
        if tarjeta is None:
            continue
        if tarjeta.indice in vistos:
            lector.error(f"{base}[{i}].indice", MotivoCampo.DUPLICADO)
            continue
        vistos.add(tarjeta.indice)
        tarjetas.append(tarjeta)
    if len(lector.errores) > n0 or modo is None:
        return None
    return RedClon(modo=modo, tarjetas=tuple(tarjetas))


def _leer_grupo(lector: LectorEsquema, obj: dict[str, object], ruta: str) -> str | None:
    """Nombre del grupo de seguridad (V-C31): ausente o ``null`` = sin grupo."""
    grupo = lector.texto(obj, "grupo", ruta, minimo=1, nulo=True, requerido=False, sin_token=True)
    if grupo is not None and RE_GRUPO.fullmatch(grupo) is None:
        lector.error(_ruta(ruta, "grupo"), MotivoCampo.TEXTO_NO_VALIDO)
        return None
    return grupo


def leer_firewall(lector: LectorEsquema, valor: object, ruta: str) -> FirewallMV | None:
    """Lee ``firewall``; las claves ausentes valen su defecto. ``None`` ante un error."""
    obj = lector.objeto(valor, ruta, CLAVES_FIREWALL)
    if obj is None:
        return None
    n0 = len(lector.errores)
    activo = lector.booleano(obj, "activo", ruta, requerido=False, defecto=False)
    grupo = _leer_grupo(lector, obj, ruta)
    entrada = lector.enumerado(
        obj, "politica_entrada", ruta, Politica, requerido=False, defecto=Politica.BLOQUEAR
    )
    salida = lector.enumerado(
        obj, "politica_salida", ruta, Politica, requerido=False, defecto=Politica.PERMITIR
    )
    dhcp = lector.enumerado(obj, "dhcp", ruta, ModoDhcp, requerido=False, defecto=ModoDhcp.AUTO)
    # ``acepto_aislada`` se acepta al leer (archivos antiguos) pero se ignora: la confirmación
    # de «MV aislada» se pide siempre de nuevo y no viaja en el archivo (SEG-C-B2).
    if (
        len(lector.errores) > n0
        or activo is None
        or entrada is None
        or salida is None
        or dhcp is None
    ):
        return None
    return FirewallMV(
        activo=activo,
        grupo=grupo,
        politica_entrada=entrada,
        politica_salida=salida,
        dhcp=dhcp,
        acepto_aislada=False,
    )


def leer_firewall_parcial(
    lector: LectorEsquema, valor: object, ruta: str
) -> FirewallParcial | None:
    """Lee las celdas de firewall de una fila: una clave ausente es ``None`` (hereda)."""
    obj = lector.objeto(valor, ruta, CLAVES_FIREWALL_PARCIAL)
    if obj is None:
        return None
    n0 = len(lector.errores)
    activo = lector.booleano(obj, "activo", ruta, requerido=False) if "activo" in obj else None
    grupo = _leer_grupo(lector, obj, ruta)
    entrada = (
        lector.enumerado(obj, "politica_entrada", ruta, Politica, requerido=False)
        if "politica_entrada" in obj
        else None
    )
    salida = (
        lector.enumerado(obj, "politica_salida", ruta, Politica, requerido=False)
        if "politica_salida" in obj
        else None
    )
    if len(lector.errores) > n0:
        return None
    return FirewallParcial(
        activo=activo, grupo=grupo, politica_entrada=entrada, politica_salida=salida
    )


# --- Escritura ----------------------------------------------------------------------------------


def _comprobar_con_lector(datos: dict[str, object], campo: str, tipo: str) -> None:
    """El lector debe aceptar todo lo que el escritor produce: si no, el guardado se rechaza."""
    lector = LectorEsquema()
    if tipo == "red_clon":
        leer_red_clon(lector, datos, campo)
    elif tipo == "firewall":
        leer_firewall(lector, datos, campo)
    else:
        leer_firewall_parcial(lector, datos, campo)
    if lector.errores:
        raise _no_guardable(campo)


def red_clon_para_escribir(red: RedClon, campo: str = "red_clon") -> dict[str, object]:
    """``red_clon`` listo para escribir (E-M08 si un texto parece un token; no guardable si el
    lector lo rechazaría, p. ej. una VLAN fuera de 1-4094)."""
    for t in red.tarjetas:
        if t.bridge is not None:
            exigir_sin_credencial(t.bridge, f"{campo}.bridge")
    datos = red_clon_a_dict(red)
    _comprobar_con_lector(datos, campo, "red_clon")
    return datos


def firewall_para_escribir(fw: FirewallMV, campo: str = "firewall") -> dict[str, object]:
    """``firewall`` listo para escribir (sin tokens y con un grupo que el lector acepte)."""
    if fw.grupo is not None:
        exigir_sin_credencial(fw.grupo, f"{campo}.grupo")
    datos = firewall_a_dict(fw)
    datos.pop("acepto_aislada", None)  # no se guarda en el archivo (SEG-C-B2)
    _comprobar_con_lector(datos, campo, "firewall")
    return datos


def firewall_parcial_a_dict(fw: FirewallParcial, campo: str = "firewall") -> dict[str, object]:
    """Celdas de firewall de una fila listas para escribir (``None`` = hereda y se omite)."""
    datos: dict[str, object] = {}
    if fw.activo is not None:
        datos["activo"] = fw.activo
    if fw.grupo is not None:
        exigir_sin_credencial(fw.grupo, f"{campo}.grupo")
        datos["grupo"] = fw.grupo
    if fw.politica_entrada is not None:
        datos["politica_entrada"] = str(fw.politica_entrada)
    if fw.politica_salida is not None:
        datos["politica_salida"] = str(fw.politica_salida)
    _comprobar_con_lector(datos, campo, "parcial")
    return datos


def fase_c_a_dict(
    red_clon: RedClon | None, firewall: FirewallMV | None, prefijo: str
) -> dict[str, object]:
    """Claves de la fase C de una configuración o de las opciones de un lote, solo si difieren
    del defecto (``prefijo`` forma la ruta de los errores: ``"opciones."``)."""
    datos: dict[str, object] = {}
    if red_clon is not None and red_clon_requiere_v5(red_clon):
        datos["red_clon"] = red_clon_para_escribir(red_clon, f"{prefijo}red_clon")
    if firewall is not None and firewall_requiere_v5(firewall):
        datos["firewall"] = firewall_para_escribir(firewall, f"{prefijo}firewall")
    return datos


__all__ = [
    "CLAVES_FIREWALL",
    "CLAVES_FIREWALL_PARCIAL",
    "CLAVES_RED_CLON",
    "CLAVES_TARJETA_CLON",
    "fase_c_a_dict",
    "firewall_a_dict",
    "firewall_parcial_a_dict",
    "firewall_parcial_requiere_v5",
    "firewall_para_escribir",
    "firewall_requiere_v5",
    "leer_firewall",
    "leer_firewall_parcial",
    "leer_red_clon",
    "red_clon_a_dict",
    "red_clon_para_escribir",
    "red_clon_requiere_v5",
]
