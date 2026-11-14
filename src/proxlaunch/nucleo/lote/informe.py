"""Informe estructurado del lote (RF-L19). Solo datos y códigos: sin textos de usuario.

La interfaz lo convierte en texto con una única función. Nunca incluye host, IP ni usuario
(CA-L19.3): los ``MetadatosInforme`` solo llevan el nombre del perfil (saneado igual que el
resto) y los UPID, errores y logs se sanean al construir el informe.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import re
from collections.abc import Sequence
from urllib.parse import quote

from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import LINEAS_LOG_TAREA
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    EntradaLibro,
    EstadoMV,
    InformeLote,
    MetadatosInforme,
    Plan,
    Problema,
    ResultadoRollback,
)
from proxlaunch.nucleo.reloj import Reloj

_CON_PROBLEMA = frozenset({EstadoMV.CON_AVISOS, EstadoMV.ERROR, EstadoMV.PARCIAL})

# Claves de parámetros de error que identifican al servidor o al usuario (CA-L19.3).
_CLAVES_PROHIBIDAS = frozenset({"host", "ip", "usuario", "user", "servidor", "direccion", "url"})
_RE_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
# usuario@realm con !token opcional; el usuario admite cualquier carácter salvo separadores
# (p. ej. ``john+ci@pve!ci``), para que no queden restos como ``…!ci`` o ``john+…``.
_RE_USUARIO = re.compile(r"""[^\s@:/'"]+@[\w.\-]+(?:![\w.\-]+)?""")
# Candidatos a IPv6 (con corchetes y puerto opcionales); cada uno se valida con ``ipaddress``.
_RE_IPV6 = re.compile(
    r"(?<![\w:.])\[?([0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*(?:%[\w.\-]+)?)\]?(?::\d{1,5}\b)?(?![\w:])"
)
_RE_UPID = re.compile(r"UPID:(?:[^:\s]*:){6}[^:\s]*:")
_OCULTO = "…"


def upid_sin_usuario(upid: str) -> str:
    """UPID sin el campo del usuario (``UPID:nodo:pid:inicio:hora:tipo:id:usuario:``)."""
    partes = upid.split(":")
    if len(partes) >= 8 and partes[0] == "UPID":
        partes[7] = _OCULTO
    return ":".join(partes)


def _ocultar_ipv6(texto: str) -> str:
    def _sustituir(m: re.Match[str]) -> str:
        candidato = m.group(1)
        if not any(c in "0123456789abcdefABCDEF" for c in candidato):
            return m.group(0)  # p. ej. «::» suelto: no es una dirección identificable
        try:
            ipaddress.IPv6Address(candidato)
        except ValueError:
            return m.group(0)
        return _OCULTO

    return _RE_IPV6.sub(_sustituir, texto)


def _sanear_texto(texto: str, ocultar: Sequence[str] = ()) -> str:
    """Quita de un texto libre los UPID completos, los ``usuario@realm[!token]``, los valores de
    ``ocultar`` (host y usuario del perfil, tal cual y codificados como URL, sin distinguir
    mayúsculas: el DNS no las distingue), las IPv6 (validadas, también entre corchetes y con
    puerto) y las IPv4."""
    texto = _RE_UPID.sub(lambda m: upid_sin_usuario(m.group(0)), texto)
    texto = _RE_USUARIO.sub(_OCULTO, texto)
    valores = {v for v in ocultar if v}
    valores |= {quote(v, safe="") for v in valores}
    for valor in sorted(valores, key=len, reverse=True):
        texto = re.sub(re.escape(valor), _OCULTO, texto, flags=re.IGNORECASE)
    texto = _ocultar_ipv6(texto)
    return _RE_IPV4.sub(_OCULTO, texto)


def _nombre_perfil_saneado(nombre: str, ocultar: Sequence[str]) -> str:
    """Nombre del perfil sin host, IP ni usuario; si queda vacío u oculto se usa «—»."""
    limpio = _sanear_texto(nombre, ocultar).strip()
    if not limpio.strip(_OCULTO + " "):
        return "—"
    return limpio


def _sanear_error(
    error: ErrorProxLaunch | None, ocultar: Sequence[str] = ()
) -> ErrorProxLaunch | None:
    """Copia del error sin host, IP ni usuario en sus parámetros ni en el detalle técnico."""
    if error is None:
        return None
    params = {
        k: _sanear_texto(v, ocultar)
        for k, v in error.params.items()
        if k.lower() not in _CLAVES_PROHIBIDAS
    }
    detalle = _sanear_texto(error.detalle_tecnico, ocultar)
    if params == error.params and detalle == error.detalle_tecnico:
        return error  # nada que ocultar: se conserva el mismo objeto
    return ErrorProxLaunch(error.codigo, params, detalle)


def _saneada(entrada: EntradaLibro, ocultar: Sequence[str] = ()) -> EntradaLibro:
    return dataclasses.replace(
        entrada,
        upid=upid_sin_usuario(entrada.upid) if entrada.upid else None,
        error=_sanear_error(entrada.error, ocultar),
        log_tarea=tuple(_sanear_texto(linea, ocultar) for linea in entrada.log_tarea),
    )


def _rollback_saneado(r: ResultadoRollback, ocultar: Sequence[str] = ()) -> ResultadoRollback:
    return dataclasses.replace(
        r,
        upid=upid_sin_usuario(r.upid) if r.upid else None,
        error=_sanear_error(r.error, ocultar),
    )


def _problema_saneado(p: Problema, ocultar: Sequence[str]) -> Problema:
    """Los parámetros de un problema del plan también pueden traer host o usuario."""
    params = {
        k: _sanear_texto(v, ocultar)
        for k, v in p.params.items()
        if k.lower() not in _CLAVES_PROHIBIDAS
    }
    return p if params == p.params else dataclasses.replace(p, params=params)


def _recortada(entrada: EntradaLibro) -> EntradaLibro:
    """Conserva el log de la tarea (últimas ``LINEAS_LOG_TAREA`` líneas) solo si la MV
    tiene avisos o error."""
    con_problema = (
        entrada.error is not None or bool(entrada.avisos) or entrada.estado in _CON_PROBLEMA
    )
    if not con_problema:
        return dataclasses.replace(entrada, log_tarea=())
    return dataclasses.replace(entrada, log_tarea=entrada.log_tarea[-LINEAS_LOG_TAREA:])


def construir_informe(
    plan: Plan,
    libro: Libro,
    metadatos: MetadatosInforme,
    *,
    rollback: Sequence[ResultadoRollback] = (),
    reloj: Reloj,
    ocultar: Sequence[str] = (),
) -> InformeLote:
    """Construye el informe a partir del libro (única fuente de verdad, CA-L12.10).

    ``ocultar`` son valores literales (host y usuario del perfil) que se quitan de todo texto
    del informe (parámetros, detalle técnico y log); nunca pasan a ``MetadatosInforme``
    (CA-L19.3).

    ``duraciones_s`` incluye las MVs terminadas (``t_fin - t_inicio``) y, en un informe
    parcial (cierre de la aplicación), las que siguen en curso medidas hasta ``reloj.ahora()``.
    """
    return informe_desde_entradas(
        plan,
        libro.instantanea(),
        metadatos,
        tuple(rollback),
        reloj.ahora(),
        ocultar,
    )


def informe_desde_entradas(
    plan: Plan,
    entradas_crudas: Sequence[EntradaLibro],
    metadatos: MetadatosInforme,
    rollback: Sequence[ResultadoRollback],
    ahora: float,
    ocultar: Sequence[str] = (),
) -> InformeLote:
    """Informe a partir de una instantánea (también para el cierre de la aplicación o un fallo
    del motor), con el mismo saneado que ``construir_informe``."""
    metadatos = dataclasses.replace(
        metadatos, nombre_perfil=_nombre_perfil_saneado(metadatos.nombre_perfil, ocultar)
    )
    entradas = tuple(_saneada(_recortada(e), ocultar) for e in entradas_crudas)
    contadores = {estado.value: 0 for estado in EstadoMV}
    for entrada in entradas:
        contadores[entrada.estado.value] += 1
    duraciones: dict[int, float] = {}
    for entrada in entradas:
        if entrada.t_inicio is None:
            continue
        fin = entrada.t_fin if entrada.t_fin is not None else ahora
        duraciones[entrada.elemento.vmid] = max(0.0, fin - entrada.t_inicio)
    return InformeLote(
        metadatos=metadatos,
        id_lote=plan.id_lote,
        es_simulacion=plan.es_simulacion,
        pedidas=len(plan.elementos),
        contadores=contadores,
        entradas=entradas,
        duraciones_s=duraciones,
        plantilla=plan.definicion.plantilla,  # por filas: solo informativa (CA-C08.8)
        rollback=tuple(_rollback_saneado(r, ocultar) for r in rollback),
        problemas_plan=tuple(_problema_saneado(p, ocultar) for p in plan.problemas),
        permisos_verificados=plan.permisos_verificados,
        por_filas=plan.definicion.es_por_filas,
    )
