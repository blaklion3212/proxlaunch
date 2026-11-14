"""Patrón de nombres del lote (RF-L02, V-L02..V-L04). Funciones puras."""

import re

from proxlaunch.nucleo.lote.constantes import MAX_LOTE, NUMERO_NOMBRE_MAXIMO, RELLENO_MAXIMO
from proxlaunch.nucleo.lote.modelos import PatronNombres, Problema, Severidad
from proxlaunch.nucleo.validacion import nombre_dns_valido

_RE_PREFIJO = re.compile(r"^[A-Za-z0-9.\-]+$")
_MAX_ETIQUETA_DNS = 63
_MAX_NOMBRE = 253


def _es_entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def relleno_efectivo(patron: PatronNombres, cantidad: int) -> int:
    """Dígitos mínimos reales: ``max(relleno, dígitos del mayor número)`` (CA-L02.2)."""
    mayor = patron.inicio + max(cantidad, 1) - 1
    return max(patron.relleno, len(str(abs(mayor))))


def generar_nombres(patron: PatronNombres, cantidad: int) -> list[str]:
    """Nombres del lote: ``prefijo`` + ``separador`` + número con el relleno efectivo.

    Todos tienen la misma longitud (el relleno efectivo es común). No valida: use
    ``validar_patron``. Con ``cantidad`` < 1 devuelve una lista vacía.
    """
    if cantidad < 1:
        return []
    ancho = relleno_efectivo(patron, cantidad)
    return [
        f"{patron.prefijo}{patron.separador}{patron.inicio + i:0{ancho}d}" for i in range(cantidad)
    ]


def causa_nombre_invalido(nombre: str) -> tuple[str, dict[str, str]] | None:
    """Causa por la que ``nombre`` incumple V-01, como ``(código, params)``; ``None`` si es válido.

    Códigos: ``caracter`` (con ``caracter``), ``longitud``, ``formato``.
    """
    if nombre_dns_valido(nombre):
        return None
    for c in nombre:
        if not (c.isascii() and (c.isalnum() or c in ".-")):
            return "caracter", {"caracter": c}
    if len(nombre) > _MAX_NOMBRE or any(len(e) > _MAX_ETIQUETA_DNS for e in nombre.split(".")):
        return "longitud", {"longitud": str(len(nombre))}
    return "formato", {}  # guion o punto al borde de una etiqueta, etiqueta vacía...


def validar_patron(patron: PatronNombres, cantidad: int) -> list[Problema]:
    """V-L02 (prefijo), V-L03 (separador) y V-L04 (números y primer nombre inválido).

    Devuelve todos los problemas; V-L04 trae ``nombre`` (el primero inválido), ``causa`` y
    los parámetros de la causa. Una ``cantidad`` fuera de 1..MAX_LOTE no se juzga aquí
    (V-L01); para generar nombres se usa ``min(cantidad, MAX_LOTE)``.
    """
    p: list[Problema] = []

    def err(regla: str, campo: str, **params: str) -> None:
        p.append(Problema(regla, Severidad.ERROR, campo, dict(params)))

    prefijo_ok = isinstance(patron.prefijo, str) and bool(_RE_PREFIJO.fullmatch(patron.prefijo))
    if not prefijo_ok:
        err("V-L02", "patron.prefijo")
    if patron.separador not in ("", "-"):
        err("V-L03", "patron.separador")

    numeros_ok = True
    if not _es_entero(patron.inicio) or not 0 <= patron.inicio <= NUMERO_NOMBRE_MAXIMO:
        err(
            "V-L04",
            "patron.inicio",
            causa="inicio_fuera_de_rango",
            maximo=str(NUMERO_NOMBRE_MAXIMO),
        )
        numeros_ok = False
    elif (
        _es_entero(cantidad)
        and cantidad >= 1
        and patron.inicio + cantidad - 1 > NUMERO_NOMBRE_MAXIMO
    ):
        err(
            "V-L04",
            "patron.inicio",
            causa="numero_fuera_de_rango",
            ultimo=str(patron.inicio + cantidad - 1),
            maximo=str(NUMERO_NOMBRE_MAXIMO),
        )
        numeros_ok = False
    if not _es_entero(patron.relleno) or not 0 <= patron.relleno <= RELLENO_MAXIMO:
        err("V-L04", "patron.relleno", causa="relleno_fuera_de_rango", maximo=str(RELLENO_MAXIMO))
        numeros_ok = False

    # Primer nombre inválido (CA-L02.4). Con prefijo vacío no se juzga: ya lo marca V-L02.
    if numeros_ok and patron.separador in ("", "-") and patron.prefijo and _es_entero(cantidad):
        for nombre in generar_nombres(patron, min(max(cantidad, 1), MAX_LOTE)):
            causa = causa_nombre_invalido(nombre)
            if causa is not None:
                codigo, params = causa
                err("V-L04", "patron.prefijo", nombre=nombre, causa=codigo, **params)
                break
    return p
