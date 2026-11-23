"""Lista blanca de las opciones de la fase A (0.6) en archivos de lote, perfil y filas de lote.

Cubre ``encender``, ``arranque_auto``, ``arranque_orden``, ``arranque_espera``, ``notas_origen``,
``notas_usuario``, ``notas``, ``etiquetas_usuario``, ``pool``, ``proteger`` y, por tarjeta de red,
``mtu`` y ``limite_mb``; de la fase B (0.7), ``cloudinit`` y ``esperar_ip`` (ver
``esquema_cloudinit``); y, de la fase C (0.8), ``red_clon`` y ``firewall`` (ver
``esquema_fase_c``). Las claves nuevas se escriben SOLO si difieren de su valor por defecto
(un archivo sin opciones nuevas queda idéntico al de 0.5.1), salvo ``notas_origen`` que se escribe
cuando es ``True`` aunque el archivo siga siendo v1/v2 (P-4). La lectura valida tipo y rango
(CA-A7.1.7); los textos libres pasan por ``exigir_sin_credencial`` al escribir (CA-A7.1.9).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from proxlaunch.nucleo.archivos.constantes import MAX_LONG_NOTAS, MAX_LONG_TEXTO
from proxlaunch.nucleo.archivos.esquema import LectorEsquema, MotivoCampo
from proxlaunch.nucleo.archivos.esquema_cloudinit import (
    cloudinit_a_dict,
    cloudinit_parcial_a_dict,
    cloudinit_requiere_v4,
    espera_ip_a_dict,
    espera_ip_requiere_v4,
    leer_cloudinit,
    leer_cloudinit_parcial,
    leer_espera_ip,
    parcial_requiere_v4,
)
from proxlaunch.nucleo.archivos.esquema_fase_c import (
    fase_c_a_dict,
    firewall_parcial_a_dict,
    firewall_parcial_requiere_v5,
    firewall_requiere_v5,
    leer_firewall,
    leer_firewall_parcial,
    leer_red_clon,
    red_clon_para_escribir,
    red_clon_requiere_v5,
)
from proxlaunch.nucleo.archivos.texto import (
    MOTIVO_CARACTERES,
    MOTIVO_LONGITUD,
    analizar_texto,
    contiene_token,
    exigir_sin_credencial,
)
from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import FirewallMV, FirewallParcial
from proxlaunch.nucleo.modelos.vm import (
    MAX_LIMITE_MB,
    MTU_IGUAL_BRIDGE,
    MTU_MAX,
    MTU_MIN,
    PLAZO_IP_DEFECTO_S,
    ConfiguracionVM,
    pool_valido,
)
from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales
from proxlaunch.nucleo.opciones.validacion import ENTERO_MAX, MAX_LONG_ETIQUETA
from proxlaunch.nucleo.red.modelos import RedClon
from proxlaunch.nucleo.validacion import etiqueta_valida

_MAX_ETIQUETAS = 256  # tope de cordura de la lista de etiquetas del usuario

CLAVES_OPCIONES_CFG = frozenset(
    {
        "encender",
        "arranque_auto",
        "arranque_orden",
        "arranque_espera",
        "notas_origen",
        "notas_usuario",
        "notas",
        "etiquetas_usuario",
        "pool",
        "proteger",
        "cloudinit",
        "esperar_ip",
        "red_clon",
        "firewall",
    }
)
CLAVES_OPCIONES_LOTE = frozenset(
    {
        "encender",
        "arranque_auto",
        "notas",
        "etiquetas_usuario",
        "pool",
        "proteger",
        "notas_origen",
        "notas_usuario",
        "cloudinit",
        "esperar_ip",
        "red_clon",
        "firewall",
    }
)
CLAVES_OPCIONES_FILA = frozenset(
    {
        "encender",
        "arranque_auto",
        "notas",
        "etiquetas_usuario",
        "pool",
        "proteger",
        "cloudinit",
        "esperar_ip",
        "red_clon",
        "firewall",
    }
)


def _no_guardable(campo: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "caracteres", "campo": campo}
    )


# --- Escritura ----------------------------------------------------------------------------


def notas_para_escribir(notas: str, campo: str) -> str:
    """Notas listas para escribir: sin credenciales (INV-M2) y en NFC. Un texto que el lector
    rechazaría (control salvo ``\\n``/``\\t``, dirección de texto o más de ``MAX_LONG_NOTAS``)
    no se guarda: el lector debe aceptar todo lo que el escritor produce."""
    exigir_sin_credencial(notas, campo)
    texto, motivo = analizar_texto(notas, maximo=MAX_LONG_NOTAS, multilinea=True, tabulador=True)
    if motivo in (MOTIVO_CARACTERES, MOTIVO_LONGITUD):
        raise _no_guardable(campo)
    return texto


def _etiquetas_para_escribir(etiquetas: tuple[str, ...], campo: str) -> list[str]:
    """Etiquetas listas para escribir: validan igual que ``leer_etiquetas`` (el lector debe
    aceptar todo lo que el escritor produce)."""
    if len(etiquetas) > _MAX_ETIQUETAS:
        raise _no_guardable(campo)
    for e in etiquetas:
        exigir_sin_credencial(e, campo)
        if not isinstance(e, str) or len(e) > MAX_LONG_ETIQUETA or not etiqueta_valida(e):
            raise _no_guardable(campo)
    return list(etiquetas)


def _pool_para_escribir(pool: str, campo: str) -> str:
    """Pool listo para escribir: sin credenciales y con el formato que acepta el lector."""
    exigir_sin_credencial(pool, campo)
    if pool and not pool_valido(pool):
        raise _no_guardable(campo)
    return pool


def mtu_para_escribir(mtu: int, campo: str) -> int:
    """MTU de tarjeta que el lector aceptaría (``1`` = igual al bridge, o 576..65520)."""
    if isinstance(mtu, bool) or not isinstance(mtu, int):
        raise _no_guardable(campo)
    if mtu != MTU_IGUAL_BRIDGE and not MTU_MIN <= mtu <= MTU_MAX:
        raise _no_guardable(campo)
    return mtu


def limite_para_escribir(limite: float, campo: str) -> float:
    """Límite de velocidad que el lector aceptaría (finito, > 0 y hasta ``MAX_LIMITE_MB``)."""
    if isinstance(limite, bool) or not isinstance(limite, (int, float)):
        raise _no_guardable(campo)
    if not math.isfinite(limite) or not 0 < limite <= MAX_LIMITE_MB:
        raise _no_guardable(campo)
    return limite


def opciones_cfg_a_dict(cfg: ConfiguracionVM) -> dict[str, object]:
    """Claves de la fase A de una configuración de lote (solo las distintas del defecto)."""
    datos: dict[str, object] = {}
    if cfg.encender:
        datos["encender"] = True
    if cfg.arranque_auto:
        datos["arranque_auto"] = True
    if cfg.arranque_orden is not None:
        datos["arranque_orden"] = cfg.arranque_orden
    if cfg.arranque_espera is not None:
        datos["arranque_espera"] = cfg.arranque_espera
    if cfg.notas_origen:
        datos["notas_origen"] = True  # P-4: se escribe aunque el archivo siga siendo v1/v2
    if cfg.notas_usuario:
        datos["notas_usuario"] = True
    if cfg.notas:
        datos["notas"] = notas_para_escribir(cfg.notas, "notas")
    if cfg.etiquetas_usuario:
        datos["etiquetas_usuario"] = _etiquetas_para_escribir(
            tuple(cfg.etiquetas_usuario), "etiquetas_usuario"
        )
    if cfg.pool is not None:
        datos["pool"] = _pool_para_escribir(cfg.pool, "pool")
    if cfg.proteger:
        datos["proteger"] = True
    datos.update(_fase_b_a_dict(cfg.cloudinit, cfg.esperar_ip, cfg.plazo_ip_s, ""))
    datos.update(fase_c_a_dict(cfg.red_clon, cfg.firewall, ""))
    return datos


def _fase_b_a_dict(
    cloudinit: ConfigCloudInit | None, esperar_ip: bool, plazo_ip_s: int, prefijo: str
) -> dict[str, object]:
    """Claves de la fase B (``cloudinit``, ``esperar_ip``), solo si difieren del defecto."""
    datos: dict[str, object] = {}
    if cloudinit_requiere_v4(cloudinit) and cloudinit is not None:
        datos["cloudinit"] = cloudinit_a_dict(cloudinit, f"{prefijo}cloudinit")
    if espera_ip_requiere_v4(esperar_ip, plazo_ip_s):
        datos["esperar_ip"] = espera_ip_a_dict(esperar_ip, plazo_ip_s, f"{prefijo}esperar_ip")
    return datos


def opciones_lote_a_dict(op: OpcionesLote) -> dict[str, object]:
    """Opciones de lote (``DefinicionLote.opciones``): solo las distintas del defecto."""
    datos: dict[str, object] = {}
    if op.encender:
        datos["encender"] = True
    if op.arranque_auto:
        datos["arranque_auto"] = True
    if op.notas:
        datos["notas"] = notas_para_escribir(op.notas, "opciones.notas")
    if op.etiquetas_usuario:
        datos["etiquetas_usuario"] = _etiquetas_para_escribir(
            tuple(op.etiquetas_usuario), "opciones.etiquetas_usuario"
        )
    if op.pool is not None:
        datos["pool"] = _pool_para_escribir(op.pool, "opciones.pool")
    if op.proteger:
        datos["proteger"] = True
    if op.notas_origen:
        datos["notas_origen"] = True
    if op.notas_usuario:
        datos["notas_usuario"] = True
    datos.update(_fase_b_a_dict(op.cloudinit, op.esperar_ip, op.plazo_ip_s, "opciones."))
    datos.update(fase_c_a_dict(op.red_clon, op.firewall, "opciones."))
    return datos


def opciones_parciales_a_dict(op: OpcionesParciales) -> dict[str, object]:
    """Sobrescrituras de una fila: solo las que no son ``None`` (``None`` = hereda)."""
    datos: dict[str, object] = {}
    if op.encender is not None:
        datos["encender"] = op.encender
    if op.arranque_auto is not None:
        datos["arranque_auto"] = op.arranque_auto
    if op.notas is not None:
        datos["notas"] = notas_para_escribir(op.notas, "fila.opciones.notas")
    if op.etiquetas_usuario is not None:
        datos["etiquetas_usuario"] = _etiquetas_para_escribir(
            tuple(op.etiquetas_usuario), "fila.opciones.etiquetas_usuario"
        )
    if op.pool is not None:
        datos["pool"] = _pool_para_escribir(
            op.pool, "fila.opciones.pool"
        )  # "" = sin pool explícito (anula el del lote)
    if op.proteger is not None:
        datos["proteger"] = op.proteger
    if op.cloudinit is not None and not op.cloudinit.vacia:
        datos["cloudinit"] = cloudinit_parcial_a_dict(op.cloudinit, "fila.opciones.cloudinit")
    if op.esperar_ip is not None:
        datos["esperar_ip"] = op.esperar_ip
    if op.firewall is not None and firewall_parcial_requiere_v5(op.firewall):
        datos["firewall"] = firewall_parcial_a_dict(op.firewall, "fila.opciones.firewall")
    if op.red_clon is not None:
        # Una fila fija su red del clon aunque sea «como la plantilla» (anula la del lote).
        datos["red_clon"] = red_clon_para_escribir(op.red_clon, "fila.opciones.red_clon")
    return datos


def opciones_lote_requieren_v3(op: OpcionesLote) -> bool:
    """¿Alguna opción de lote distinta del defecto, salvo ``notas_origen`` (P-4)?"""
    return (
        op.encender
        or op.arranque_auto
        or bool(op.notas)
        or bool(op.etiquetas_usuario)
        or op.pool is not None
        or op.proteger
        or op.notas_usuario
    )


def opciones_parciales_requieren_v3(op: OpcionesParciales) -> bool:
    """Cualquier sobrescritura de fila de la fase A (las de la fase B cuentan en ``v4``)."""
    return any(
        v is not None
        for v in (
            op.encender,
            op.arranque_auto,
            op.notas,
            op.etiquetas_usuario,
            op.pool,
            op.proteger,
        )
    )


def opciones_lote_requieren_v4(op: OpcionesLote) -> bool:
    """¿Las opciones de lote usan algo de la fase B (cloud-init o espera de IP)?"""
    return cloudinit_requiere_v4(op.cloudinit) or espera_ip_requiere_v4(
        op.esperar_ip, op.plazo_ip_s
    )


def opciones_parciales_requieren_v4(op: OpcionesParciales) -> bool:
    """¿Alguna sobrescritura de fila es de la fase B?"""
    return parcial_requiere_v4(op.cloudinit) or op.esperar_ip is not None


def opciones_lote_requieren_v5(o: OpcionesLote) -> bool:
    """¿Las opciones de lote usan algo de la fase C (red del clon personalizada o firewall)?"""
    return red_clon_requiere_v5(o.red_clon) or firewall_requiere_v5(o.firewall)


def opciones_parciales_requieren_v5(o: OpcionesParciales) -> bool:
    """¿Alguna sobrescritura de fila es de la fase C? Cualquier ``red_clon`` de la fila cuenta
    (también «como la plantilla»: es una elección explícita que anula la del lote)."""
    return o.red_clon is not None or firewall_parcial_requiere_v5(o.firewall)


# --- Lectura ------------------------------------------------------------------------------


def _ruta(base: str, clave: str) -> str:
    return f"{base}.{clave}" if base else clave


def leer_notas(lector: LectorEsquema, obj: dict[str, object], clave: str, ruta: str) -> str | None:
    """Notas: hasta ``MAX_LONG_NOTAS`` caracteres, con ``\\n`` y ``\\t`` y sin credenciales."""
    return lector.texto(
        obj,
        clave,
        ruta,
        maximo=MAX_LONG_NOTAS,
        multilinea=True,
        tabulador=True,
        requerido=False,
        defecto="",
        sin_token=True,
    )


def leer_pool(
    lector: LectorEsquema, obj: dict[str, object], ruta: str, *, nulo: bool
) -> str | None:
    """Pool (texto seguro, sin credenciales, con el formato de Proxmox: SEG-A-04; ``""`` = sin
    pool). Con ``nulo``, ausente o ``null`` → ``None``."""
    pool = lector.texto(
        obj, "pool", ruta, maximo=MAX_LONG_TEXTO, nulo=nulo, requerido=False, sin_token=True
    )
    if pool and not pool_valido(pool):
        lector.error(_ruta(ruta, "pool"), MotivoCampo.TEXTO_NO_VALIDO)
        return None
    return pool


def leer_etiquetas(
    lector: LectorEsquema, obj: dict[str, object], clave: str, ruta: str
) -> tuple[str, ...] | None:
    """Lista de etiquetas del usuario; cada una con el patrón de Proxmox (V-24) y ≤ 128."""
    n0 = len(lector.errores)
    items = lector.lista(obj, clave, ruta, maximo=_MAX_ETIQUETAS, requerido=False)
    base = _ruta(ruta, clave)
    etiquetas: list[str] = []
    for i, item in enumerate(items or []):
        campo = f"{base}[{i}]"
        if not isinstance(item, str):
            lector.error(campo, MotivoCampo.TIPO)
        elif len(item) > MAX_LONG_ETIQUETA:
            lector.error(campo, MotivoCampo.LONGITUD, maximo=str(MAX_LONG_ETIQUETA))
        elif not etiqueta_valida(item) or contiene_token(item):
            lector.error(campo, MotivoCampo.TEXTO_NO_VALIDO)
        else:
            etiquetas.append(item)
    return None if len(lector.errores) > n0 else tuple(etiquetas)


def leer_mtu(lector: LectorEsquema, obj: dict[str, object], ruta: str) -> tuple[bool, int | None]:
    """MTU de una tarjeta: ausente o ``null`` = heredar; ``1`` = igual al bridge; 576..65520.

    Devuelve ``(correcto, valor)``."""
    n0 = len(lector.errores)
    mtu = lector.entero(
        obj, "mtu", ruta, minimo=MTU_IGUAL_BRIDGE, maximo=MTU_MAX, nulo=True, requerido=False
    )
    if mtu is not None and mtu != MTU_IGUAL_BRIDGE and mtu < MTU_MIN:
        lector.error(
            _ruta(ruta, "mtu"), MotivoCampo.RANGO, minimo=str(MTU_MIN), maximo=str(MTU_MAX)
        )
        return False, None
    return len(lector.errores) == n0, mtu


def leer_limite(
    lector: LectorEsquema, obj: dict[str, object], ruta: str
) -> tuple[bool, float | None]:
    """Límite de velocidad (MB/s) de una tarjeta: número real finito y > 0; ausente = sin límite."""
    if "limite_mb" not in obj:
        return True, None
    valor = obj["limite_mb"]
    campo = _ruta(ruta, "limite_mb")
    if valor is None:
        return True, None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        lector.error(campo, MotivoCampo.TIPO)
        return False, None
    if not math.isfinite(valor) or not 0 < valor <= MAX_LIMITE_MB:
        lector.error(campo, MotivoCampo.RANGO, minimo="0", maximo=str(MAX_LIMITE_MB))
        return False, None
    return True, float(valor)


@dataclass
class OpcionesCfgLeidas:
    """Opciones de la fase A de una configuración de lote, ya validadas."""

    encender: bool = False
    arranque_auto: bool = False
    arranque_orden: int | None = None
    arranque_espera: int | None = None
    notas_origen: bool = False
    notas_usuario: bool = False
    notas: str = ""
    etiquetas_usuario: tuple[str, ...] = ()
    pool: str | None = None
    proteger: bool = False
    cloudinit: ConfigCloudInit | None = None
    esperar_ip: bool = False
    plazo_ip_s: int = PLAZO_IP_DEFECTO_S
    red_clon: RedClon | None = None
    firewall: FirewallMV | None = None


@dataclass
class _FaseCLeida:
    """``red_clon`` y ``firewall`` de un objeto de opciones, ya validados."""

    red_clon: RedClon | None = None
    firewall: FirewallMV | None = None


def _leer_fase_c(lector: LectorEsquema, obj: dict[str, object], ruta: str) -> _FaseCLeida | None:
    """Lee las claves de la fase C (``null`` = ausente)."""
    n0 = len(lector.errores)
    red_clon: RedClon | None = None
    if obj.get("red_clon") is not None:
        red_clon = leer_red_clon(lector, obj["red_clon"], _ruta(ruta, "red_clon"))
    firewall: FirewallMV | None = None
    if obj.get("firewall") is not None:
        firewall = leer_firewall(lector, obj["firewall"], _ruta(ruta, "firewall"))
    if len(lector.errores) > n0:
        return None
    return _FaseCLeida(red_clon, firewall)


@dataclass
class _FaseBLeida:
    """``cloudinit`` y ``esperar_ip`` de un objeto de opciones, ya validados."""

    cloudinit: ConfigCloudInit | None = None
    esperar_ip: bool = False
    plazo_ip_s: int = PLAZO_IP_DEFECTO_S


def _leer_fase_b(lector: LectorEsquema, obj: dict[str, object], ruta: str) -> _FaseBLeida | None:
    """Lee las claves de la fase B de una configuración o de las opciones de un lote.

    Un ``cloudinit`` sin nada (todo vacío) equivale a no tenerlo (``None``).
    """
    n0 = len(lector.errores)
    cloudinit: ConfigCloudInit | None = None
    if "cloudinit" in obj:
        cloudinit = leer_cloudinit(lector, obj["cloudinit"], _ruta(ruta, "cloudinit"))
        if cloudinit is not None and cloudinit.vacia:
            cloudinit = None
    espera = (False, PLAZO_IP_DEFECTO_S)
    if "esperar_ip" in obj:
        leida = leer_espera_ip(lector, obj["esperar_ip"], _ruta(ruta, "esperar_ip"))
        if leida is not None:
            espera = leida
    if len(lector.errores) > n0:
        return None
    return _FaseBLeida(cloudinit, espera[0], espera[1])


def leer_opciones_cfg(
    lector: LectorEsquema, obj: dict[str, object], ruta: str
) -> OpcionesCfgLeidas | None:
    """Lee y valida las claves de la fase A de una configuración de lote (``None`` si hay error)."""
    n0 = len(lector.errores)
    encender = lector.booleano(obj, "encender", ruta, requerido=False, defecto=False)
    arranque_auto = lector.booleano(obj, "arranque_auto", ruta, requerido=False, defecto=False)
    orden = lector.entero(
        obj, "arranque_orden", ruta, minimo=0, maximo=ENTERO_MAX, nulo=True, requerido=False
    )
    espera = lector.entero(
        obj, "arranque_espera", ruta, minimo=0, maximo=ENTERO_MAX, nulo=True, requerido=False
    )
    notas_origen = lector.booleano(obj, "notas_origen", ruta, requerido=False, defecto=False)
    notas_usuario = lector.booleano(obj, "notas_usuario", ruta, requerido=False, defecto=False)
    notas = leer_notas(lector, obj, "notas", ruta)
    etiquetas = leer_etiquetas(lector, obj, "etiquetas_usuario", ruta)
    pool = leer_pool(lector, obj, ruta, nulo=True)
    proteger = lector.booleano(obj, "proteger", ruta, requerido=False, defecto=False)
    fase_b = _leer_fase_b(lector, obj, ruta)
    fase_c = _leer_fase_c(lector, obj, ruta)
    if (
        len(lector.errores) > n0
        or encender is None
        or arranque_auto is None
        or notas_origen is None
        or notas_usuario is None
        or notas is None
        or etiquetas is None
        or proteger is None
        or fase_b is None
        or fase_c is None
    ):
        return None
    return OpcionesCfgLeidas(
        encender=encender,
        arranque_auto=arranque_auto,
        arranque_orden=orden,
        arranque_espera=espera,
        notas_origen=notas_origen,
        notas_usuario=notas_usuario,
        notas=notas,
        etiquetas_usuario=etiquetas,
        pool=pool,
        proteger=proteger,
        cloudinit=fase_b.cloudinit,
        esperar_ip=fase_b.esperar_ip,
        plazo_ip_s=fase_b.plazo_ip_s,
        red_clon=fase_c.red_clon,
        firewall=fase_c.firewall,
    )


def leer_opciones_lote(lector: LectorEsquema, valor: object, ruta: str) -> OpcionesLote | None:
    """Lee ``DefinicionLote.opciones``. Las claves ausentes valen su defecto."""
    obj = lector.objeto(valor, ruta, CLAVES_OPCIONES_LOTE)
    if obj is None:
        return None
    n0 = len(lector.errores)
    encender = lector.booleano(obj, "encender", ruta, requerido=False, defecto=False)
    arranque_auto = lector.booleano(obj, "arranque_auto", ruta, requerido=False, defecto=False)
    notas = leer_notas(lector, obj, "notas", ruta)
    etiquetas = leer_etiquetas(lector, obj, "etiquetas_usuario", ruta)
    pool = leer_pool(lector, obj, ruta, nulo=True)
    proteger = lector.booleano(obj, "proteger", ruta, requerido=False, defecto=False)
    notas_origen = lector.booleano(obj, "notas_origen", ruta, requerido=False, defecto=False)
    notas_usuario = lector.booleano(obj, "notas_usuario", ruta, requerido=False, defecto=False)
    fase_b = _leer_fase_b(lector, obj, ruta)
    fase_c = _leer_fase_c(lector, obj, ruta)
    if (
        len(lector.errores) > n0
        or encender is None
        or arranque_auto is None
        or notas is None
        or etiquetas is None
        or proteger is None
        or notas_origen is None
        or notas_usuario is None
        or fase_b is None
        or fase_c is None
    ):
        return None
    return OpcionesLote(
        encender=encender,
        arranque_auto=arranque_auto,
        notas=notas,
        etiquetas_usuario=etiquetas,
        pool=pool,
        proteger=proteger,
        notas_origen=notas_origen,
        notas_usuario=notas_usuario,
        cloudinit=fase_b.cloudinit,
        esperar_ip=fase_b.esperar_ip,
        plazo_ip_s=fase_b.plazo_ip_s,
        red_clon=fase_c.red_clon,
        firewall=fase_c.firewall,
    )


def leer_opciones_parciales(
    lector: LectorEsquema, valor: object, ruta: str
) -> OpcionesParciales | None:
    """Lee las sobrescrituras de una fila: una clave ausente es ``None`` (hereda)."""
    obj = lector.objeto(valor, ruta, CLAVES_OPCIONES_FILA)
    if obj is None:
        return None
    n0 = len(lector.errores)
    encender = (
        lector.booleano(obj, "encender", ruta, requerido=False) if "encender" in obj else None
    )
    arranque_auto = (
        lector.booleano(obj, "arranque_auto", ruta, requerido=False)
        if "arranque_auto" in obj
        else None
    )
    notas = leer_notas(lector, obj, "notas", ruta) if "notas" in obj else None
    etiquetas = (
        leer_etiquetas(lector, obj, "etiquetas_usuario", ruta)
        if "etiquetas_usuario" in obj
        else None
    )
    pool = leer_pool(lector, obj, ruta, nulo=False) if "pool" in obj else None
    proteger = (
        lector.booleano(obj, "proteger", ruta, requerido=False) if "proteger" in obj else None
    )
    cloudinit = (
        leer_cloudinit_parcial(lector, obj["cloudinit"], _ruta(ruta, "cloudinit"))
        if "cloudinit" in obj
        else None
    )
    esperar_ip = (
        lector.booleano(obj, "esperar_ip", ruta, requerido=False) if "esperar_ip" in obj else None
    )
    firewall = (
        leer_firewall_parcial(lector, obj["firewall"], _ruta(ruta, "firewall"))
        if obj.get("firewall") is not None
        else None
    )
    red_clon = (
        leer_red_clon(lector, obj["red_clon"], _ruta(ruta, "red_clon"))
        if obj.get("red_clon") is not None
        else None
    )
    if len(lector.errores) > n0:
        return None
    if cloudinit is not None and cloudinit.vacia:
        cloudinit = None
    if firewall == FirewallParcial():
        firewall = None
    return OpcionesParciales(
        encender=encender,
        arranque_auto=arranque_auto,
        notas=notas,
        etiquetas_usuario=etiquetas,
        pool=pool,
        proteger=proteger,
        cloudinit=cloudinit,
        esperar_ip=esperar_ip,
        firewall=firewall,
        red_clon=red_clon,
    )
