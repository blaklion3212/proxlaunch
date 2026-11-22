"""Lista blanca de cloud-init y de la espera de IP en archivos de lote (fase B, RF-B6.1, DT-B12).

Cubre la clave ``cloudinit`` (en la configuración de una MV, en las opciones de lote y, como
``CloudInitParcial``, en las opciones de una fila) y ``esperar_ip``. Todo es opcional y se omite si
vale su defecto: un lote sin nada de la fase B queda idéntico al de 0.6.0.

La contraseña NUNCA se escribe: si la había se anota el indicador neutro ``con_acceso_local``
(su nombre no dispara ``es_clave_credencial``) y al leerlo se marca el aviso
``CONTRASENA_NO_GUARDADA``. Una clave ``contrasena``/``cipassword`` manipulada en el archivo se
descarta sin leerla (``CREDENCIAL_IGNORADA``) y nunca llega a una petición.

El lector acepta todo lo que produce el escritor: cada escritor arma el diccionario y lo pasa por
el lector antes de devolverlo; si el lector lo rechazaría, no se guarda (``ARCHIVO_NO_GUARDABLE``).
Las reglas de contenido (formato de la IP, DNS válido...) las muestra el formulario tras cargar,
como en el resto de campos de un lote guardado (puede ser un borrador, CA-G02.1).
"""

from __future__ import annotations

from typing import Any

from proxlaunch.nucleo.agente.validacion import PLAZO_MAX_S, PLAZO_MIN_S
from proxlaunch.nucleo.archivos.constantes import MAX_LONG_TEXTO
from proxlaunch.nucleo.archivos.esquema import LectorEsquema, MotivoCampo
from proxlaunch.nucleo.archivos.texto import (
    MOTIVO_LONGITUD,
    analizar_texto,
    contiene_token,
    exigir_sin_credencial,
)
from proxlaunch.nucleo.cloudinit import serializacion
from proxlaunch.nucleo.cloudinit.claves import (
    MAX_BYTES_CLAVES,
    MAX_CLAVES,
    MotivoClave,
    analizar_claves,
)
from proxlaunch.nucleo.cloudinit.modelos import (
    MAX_TARJETAS,
    TIPOS_SNIPPET,
    CloudInitParcial,
    ConfigCloudInit,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.cloudinit.snippets import MAX_VOLID
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.vm import PLAZO_IP_DEFECTO_S

CLAVES_CLOUDINIT = frozenset(
    {
        "usuario",
        "claves",
        "tarjetas",
        "dns",
        "dominio",
        "actualizar",
        "snippets",
        "activar_agente",
        "con_acceso_local",
    }
)
CLAVES_CLOUDINIT_PARCIAL = frozenset(
    {
        "usuario",
        "claves",
        "tarjeta0",
        "dns",
        "dominio",
        "actualizar",
        "snippets",
        "con_acceso_local",
    }
)
_CLAVES_TARJETA = frozenset({"indice", "modo", "ip", "serie", "puerta"})
_CLAVES_SNIPPETS = frozenset(TIPOS_SNIPPET)
_CLAVES_ESPERA_IP = frozenset({"activo", "plazo_s"})

MAX_DNS_ARCHIVO = 16  # tope de cordura de la lista de DNS (V-B32 avisa a partir de 3)
MAX_LONG_DIRECCION = 64  # IP en CIDR, puerta de enlace o servidor DNS
MAX_LONG_DOMINIO = 253


def _no_guardable(campo: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "caracteres", "campo": campo}
    )


def _ruta(base: str, clave: str) -> str:
    return f"{base}.{clave}" if base else clave


# --- Lectura ------------------------------------------------------------------------------


def _leer_textos(
    lector: LectorEsquema,
    obj: dict[str, object],
    clave: str,
    ruta: str,
    *,
    maximo_items: int,
    maximo_long: int,
) -> tuple[str, ...] | None:
    """Lista de textos seguros (sin control ni token). ``None`` si hay error o no está."""
    n0 = len(lector.errores)
    items = lector.lista(obj, clave, ruta, maximo=maximo_items, requerido=False)
    base = _ruta(ruta, clave)
    textos: list[str] = []
    for i, item in enumerate(items or []):
        campo = f"{base}[{i}]"
        if not isinstance(item, str):
            lector.error(campo, MotivoCampo.TIPO)
            continue
        texto, motivo = analizar_texto(item, maximo=maximo_long)
        if motivo == MOTIVO_LONGITUD:
            lector.error(campo, MotivoCampo.LONGITUD, maximo=str(maximo_long))
        elif motivo is not None:
            lector.error(campo, MotivoCampo.TEXTO_NO_VALIDO)
        elif contiene_token(texto):
            lector.error(campo, MotivoCampo.TOKEN)
        else:
            textos.append(texto)
    return None if len(lector.errores) > n0 or items is None else tuple(textos)


def _leer_claves(
    lector: LectorEsquema, obj: dict[str, object], ruta: str
) -> tuple[str, ...] | None:
    """Claves públicas: se revalidan con ``analizar_claves`` (una privada invalida el archivo)."""
    textos = _leer_textos(
        lector, obj, "claves", ruta, maximo_items=MAX_CLAVES, maximo_long=MAX_BYTES_CLAVES
    )
    if textos is None:
        return None
    resultado = analizar_claves("\n".join(textos))
    if resultado.problemas:
        campo = _ruta(ruta, "claves")
        motivo = resultado.problemas[0].motivo
        if motivo in (MotivoClave.DEMASIADAS, MotivoClave.DEMASIADO_TEXTO):
            lector.error(campo, MotivoCampo.DEMASIADOS, detalle=motivo.value)
        else:
            lector.error(campo, MotivoCampo.TEXTO_NO_VALIDO, detalle=motivo.value)
        return None
    return resultado.claves


def _leer_tarjeta(lector: LectorEsquema, valor: object, ruta: str) -> TarjetaCloudInit | None:
    obj = lector.objeto(valor, ruta, _CLAVES_TARJETA)
    if obj is None:
        return None
    n0 = len(lector.errores)
    indice = lector.entero(obj, "indice", ruta, minimo=0, maximo=MAX_TARJETAS - 1)
    modo = lector.enumerado(
        obj, "modo", ruta, ModoTarjeta, requerido=False, defecto=ModoTarjeta.SIN_CONFIGURAR
    )
    ip = lector.texto(
        obj, "ip", ruta, maximo=MAX_LONG_DIRECCION, nulo=True, requerido=False, sin_token=True
    )
    serie = lector.booleano(obj, "serie", ruta, requerido=False, defecto=False)
    puerta = lector.texto(
        obj, "puerta", ruta, maximo=MAX_LONG_DIRECCION, nulo=True, requerido=False, sin_token=True
    )
    if len(lector.errores) > n0 or indice is None or modo is None or serie is None:
        return None
    return TarjetaCloudInit(indice=indice, modo=modo, ip=ip, serie=serie, puerta=puerta)


def _leer_tarjetas(
    lector: LectorEsquema, obj: dict[str, object], ruta: str
) -> tuple[TarjetaCloudInit, ...] | None:
    n0 = len(lector.errores)
    items = lector.lista(obj, "tarjetas", ruta, maximo=MAX_TARJETAS, requerido=False)
    base = _ruta(ruta, "tarjetas")
    tarjetas: list[TarjetaCloudInit] = []
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
    if len(lector.errores) > n0:
        return None
    return tuple(sorted(tarjetas, key=lambda t: t.indice))


def _leer_snippets(
    lector: LectorEsquema, obj: dict[str, object], ruta: str
) -> SnippetsCloudInit | None:
    """Un volid (o ``ninguno``) por tipo. El formato del volid lo revisa V-B54 en el formulario."""
    if "snippets" not in obj:
        return SnippetsCloudInit()
    campo = _ruta(ruta, "snippets")
    sub = lector.objeto(obj["snippets"], campo, _CLAVES_SNIPPETS)
    if sub is None:
        return None
    n0 = len(lector.errores)
    valores = {
        tipo: lector.texto(
            sub, tipo, campo, minimo=1, maximo=MAX_VOLID, nulo=True, requerido=False, sin_token=True
        )
        for tipo in TIPOS_SNIPPET
    }
    if len(lector.errores) > n0:
        return None
    return SnippetsCloudInit(**valores)


def _leer_actualizar(lector: LectorEsquema, obj: dict[str, object], ruta: str) -> bool | None:
    """``actualizar``: ausente o ``null`` = como la plantilla; si no, un booleano."""
    if "actualizar" not in obj or obj["actualizar"] is None:
        return None
    return lector.booleano(obj, "actualizar", ruta)


def _leer_indicador_contrasena(lector: LectorEsquema, obj: dict[str, object], ruta: str) -> None:
    """``con_acceso_local``: el lote tenía contraseña que no se guardó (aviso, nunca el valor)."""
    if lector.booleano(obj, "con_acceso_local", ruta, requerido=False, defecto=False):
        lector.marcar_contrasena_no_guardada()


def leer_cloudinit(lector: LectorEsquema, valor: object, ruta: str) -> ConfigCloudInit | None:
    """Lee ``cloudinit`` de una configuración o de las opciones de lote (sin contraseña)."""
    obj = lector.objeto(valor, ruta, CLAVES_CLOUDINIT)
    if obj is None:
        return None
    n0 = len(lector.errores)
    usuario = lector.texto(
        obj, "usuario", ruta, maximo=MAX_LONG_TEXTO, requerido=False, defecto="", sin_token=True
    )
    claves = _leer_claves(lector, obj, ruta) if "claves" in obj else ()
    tarjetas = _leer_tarjetas(lector, obj, ruta) if "tarjetas" in obj else ()
    dns = (
        _leer_textos(
            lector, obj, "dns", ruta, maximo_items=MAX_DNS_ARCHIVO, maximo_long=MAX_LONG_DIRECCION
        )
        if "dns" in obj
        else ()
    )
    dominio = lector.texto(
        obj, "dominio", ruta, maximo=MAX_LONG_DOMINIO, requerido=False, defecto="", sin_token=True
    )
    actualizar = _leer_actualizar(lector, obj, ruta)
    snippets = _leer_snippets(lector, obj, ruta)
    agente = lector.booleano(obj, "activar_agente", ruta, requerido=False, defecto=False)
    _leer_indicador_contrasena(lector, obj, ruta)
    if (
        len(lector.errores) > n0
        or usuario is None
        or claves is None
        or tarjetas is None
        or dns is None
        or dominio is None
        or snippets is None
        or agente is None
    ):
        return None
    return ConfigCloudInit(
        usuario=usuario,
        claves=claves,
        tarjetas=tarjetas,
        dns=dns,
        dominio=dominio,
        actualizar=actualizar,
        snippets=snippets,
        activar_agente=agente,
    )


def leer_cloudinit_parcial(
    lector: LectorEsquema, valor: object, ruta: str
) -> CloudInitParcial | None:
    """Lee ``cloudinit`` de las opciones de una fila: una clave ausente es ``None`` (hereda)."""
    obj = lector.objeto(valor, ruta, CLAVES_CLOUDINIT_PARCIAL)
    if obj is None:
        return None
    n0 = len(lector.errores)
    usuario = (
        lector.texto(obj, "usuario", ruta, maximo=MAX_LONG_TEXTO, sin_token=True)
        if "usuario" in obj
        else None
    )
    claves = _leer_claves(lector, obj, ruta) if "claves" in obj else None
    tarjeta0 = (
        _leer_tarjeta(lector, obj["tarjeta0"], _ruta(ruta, "tarjeta0"))
        if "tarjeta0" in obj
        else None
    )
    dns = (
        _leer_textos(
            lector, obj, "dns", ruta, maximo_items=MAX_DNS_ARCHIVO, maximo_long=MAX_LONG_DIRECCION
        )
        if "dns" in obj
        else None
    )
    dominio = (
        lector.texto(obj, "dominio", ruta, maximo=MAX_LONG_DOMINIO, sin_token=True)
        if "dominio" in obj
        else None
    )
    actualizar = lector.booleano(obj, "actualizar", ruta) if "actualizar" in obj else None
    snippets = _leer_snippets(lector, obj, ruta) if "snippets" in obj else None
    _leer_indicador_contrasena(lector, obj, ruta)  # solo cuenta como aviso: el valor no vuelve
    if len(lector.errores) > n0:
        return None
    if snippets is not None and snippets.como_la_plantilla:
        snippets = None
    return CloudInitParcial(
        usuario=usuario,
        claves=claves,
        tarjeta0=tarjeta0,
        dns=dns,
        dominio=dominio,
        actualizar=actualizar,
        snippets=snippets,
    )


def leer_espera_ip(lector: LectorEsquema, valor: object, ruta: str) -> tuple[bool, int] | None:
    """Lee ``esperar_ip`` {``activo``, ``plazo_s``} y devuelve ``(activo, plazo_s)``."""
    obj = lector.objeto(valor, ruta, _CLAVES_ESPERA_IP)
    if obj is None:
        return None
    n0 = len(lector.errores)
    activo = lector.booleano(obj, "activo", ruta, requerido=False, defecto=False)
    plazo = lector.entero(
        obj,
        "plazo_s",
        ruta,
        minimo=PLAZO_MIN_S,
        maximo=PLAZO_MAX_S,
        requerido=False,
        defecto=PLAZO_IP_DEFECTO_S,
    )
    if len(lector.errores) > n0 or activo is None or plazo is None:
        return None
    return activo, plazo


# --- Escritura ----------------------------------------------------------------------------


def _sin_credenciales(textos: list[str], campo: str) -> None:
    for texto in textos:
        exigir_sin_credencial(texto, campo)


def _comprobar_con_lector(datos: dict[str, Any], campo: str, parcial: bool) -> None:
    """El lector debe aceptar todo lo que el escritor produce: si no, el guardado se rechaza."""
    lector = LectorEsquema()
    if parcial:
        leer_cloudinit_parcial(lector, datos, campo)
    else:
        leer_cloudinit(lector, datos, campo)
    if lector.errores:
        raise _no_guardable(campo)


def _normalizar_claves(claves: tuple[str, ...], campo: str) -> list[str]:
    resultado = analizar_claves("\n".join(claves))
    if resultado.problemas:
        raise _no_guardable(f"{campo}.claves")
    return list(resultado.claves)


def cloudinit_a_dict(ci: ConfigCloudInit, campo: str = "cloudinit") -> dict[str, object]:
    """``cloudinit`` listo para escribir (sin contraseña; con ``con_acceso_local`` si la había).

    Lanza E-M08 si algún texto parece un token (CA-B6.1.8) y ``ARCHIVO_NO_GUARDABLE`` si el
    lector lo rechazaría (p. ej. una clave privada).
    """
    textos = [ci.usuario, ci.dominio, *ci.claves, *ci.dns]
    textos += [t.ip or "" for t in ci.tarjetas] + [t.puerta or "" for t in ci.tarjetas]
    textos += [v for v in (getattr(ci.snippets, t) for t in TIPOS_SNIPPET) if v]
    _sin_credenciales(textos, campo)
    datos: dict[str, Any] = serializacion.a_dict(ci)
    if ci.claves:
        datos["claves"] = _normalizar_claves(ci.claves, campo)
    _comprobar_con_lector(datos, campo, parcial=False)
    return datos


def _tarjeta_a_dict(t: TarjetaCloudInit) -> dict[str, Any]:
    datos: dict[str, Any] = {"indice": t.indice, "modo": str(t.modo)}
    if t.ip is not None:
        datos["ip"] = t.ip
    if t.serie:
        datos["serie"] = True
    if t.puerta is not None:
        datos["puerta"] = t.puerta
    return datos


def cloudinit_parcial_a_dict(p: CloudInitParcial, campo: str = "cloudinit") -> dict[str, object]:
    """Celdas de cloud-init de una fila listas para escribir (``None`` = hereda y se omite)."""
    datos: dict[str, Any] = {}
    textos: list[str] = []
    if p.usuario is not None:
        datos["usuario"] = p.usuario
        textos.append(p.usuario)
    if p.claves is not None:
        datos["claves"] = _normalizar_claves(p.claves, campo)
        textos.extend(p.claves)
    if p.tarjeta0 is not None:
        datos["tarjeta0"] = _tarjeta_a_dict(p.tarjeta0)
        textos += [p.tarjeta0.ip or "", p.tarjeta0.puerta or ""]
    if p.dns is not None:
        datos["dns"] = list(p.dns)
        textos.extend(p.dns)
    if p.dominio is not None:
        datos["dominio"] = p.dominio
        textos.append(p.dominio)
    if p.actualizar is not None:
        datos["actualizar"] = p.actualizar
    if p.snippets is not None:
        elegidos = {t: v for t in TIPOS_SNIPPET if (v := getattr(p.snippets, t))}
        if elegidos:
            datos["snippets"] = elegidos
            textos.extend(elegidos.values())
    if p.contrasena is not None and p.contrasena.definido:
        datos["con_acceso_local"] = True
    _sin_credenciales(textos, campo)
    _comprobar_con_lector(datos, campo, parcial=True)
    return datos


def espera_ip_a_dict(activo: bool, plazo_s: int, campo: str = "esperar_ip") -> dict[str, object]:
    """``{"activo", "plazo_s"}``; el plazo debe estar en el rango que el lector acepta."""
    datos: dict[str, object] = {"activo": activo, "plazo_s": plazo_s}
    lector = LectorEsquema()
    leer_espera_ip(lector, datos, campo)
    if lector.errores:
        raise _no_guardable(campo)
    return datos


# --- Qué versión de archivo hace falta -----------------------------------------------------


def cloudinit_requiere_v4(ci: ConfigCloudInit | None) -> bool:
    """¿Hay algo de cloud-init que escribir? (``None`` o vacía = nada: el lote sigue como antes)."""
    return ci is not None and not ci.vacia


def parcial_requiere_v4(p: CloudInitParcial | None) -> bool:
    return p is not None and not p.vacia


def espera_ip_requiere_v4(activo: bool, plazo_s: int) -> bool:
    """Solo con la espera activa (QA-B5): un plazo cambiado con la casilla desmarcada no se
    escribe, así que no obliga a subir de versión (el archivo sigue siendo de 0.6.0)."""
    return activo
