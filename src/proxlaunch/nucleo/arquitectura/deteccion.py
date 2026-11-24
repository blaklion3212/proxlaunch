"""Detección de la arquitectura de cada nodo (RF-D2.5, DT-D6). Sin Qt.

Orden de las fuentes (la primera que dé un valor válido): ``host-arch`` de
``/cluster/resources`` (9.2, ya leído por quien llama), ``current-kernel.machine`` y
``kversion`` de ``/nodes/{n}/status`` y, solo si la lista de CPU **ya se leyó**, la heurística
de los modelos (§0 de la arquitectura de la fase D: nunca provoca un GET propio).

Los datos del servidor no son confiables: solo se aceptan los valores de la lista normalizada;
cualquier otro texto acaba en ``DESCONOCIDA`` y no se propaga. Nada de aquí lanza: un fallo deja
el nodo en ``DESCONOCIDA`` con el motivo (V-D04) y el descubrimiento sigue.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    ArquitecturaNodo,
    FuenteArquitectura,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import ModeloCpu

if TYPE_CHECKING:
    from proxlaunch.nucleo.api.cliente import ClienteProxmox
    from proxlaunch.nucleo.modelos.inventario import Inventario
    from proxlaunch.nucleo.servicios.conexion import Sesion

_log = logging.getLogger("proxlaunch.arquitectura.deteccion")

MOTIVO_SIN_PERMISO: Final = "sin_permiso"
MOTIVO_NO_RESPONDE: Final = "no_responde"
MOTIVO_FORMATO: Final = "formato"

_MAX_TEXTO: Final = 512  # tope del texto de ``kversion`` que se examina
_VALORES_X86: Final = frozenset({"x86_64", "amd64"})
_VALORES_ARM: Final = frozenset({"aarch64", "arm64"})
_MODELOS_ARM: Final = frozenset({"cortex-a53", "neoverse-n1"})
_RE_PVEVERSION: Final = re.compile(r"(\d{1,3})\.(\d{1,3})")
_VERSION_HOST_ARCH: Final = (9, 2)  # primera versión que publica host-arch (y solo en no x86)


def _version_de_estado(estado: Mapping[str, object]) -> tuple[int, int] | None:
    """Versión (mayor, menor) de PVE de ESE nodo según ``pveversion`` (``pve-manager/9.2.1/…``)."""
    texto = estado.get("pveversion")
    if not isinstance(texto, str):
        return None
    m = _RE_PVEVERSION.search(texto[:_MAX_TEXTO])
    return (int(m.group(1)), int(m.group(2))) if m else None


def normalizar(texto: object) -> Arquitectura:
    """``x86_64|amd64`` → ``X86_64``; ``aarch64|arm64`` → ``AARCH64``; otro → ``DESCONOCIDA``."""
    if not isinstance(texto, str):
        return Arquitectura.DESCONOCIDA
    valor = texto.strip().lower()
    if valor in _VALORES_X86:
        return Arquitectura.X86_64
    if valor in _VALORES_ARM:
        return Arquitectura.AARCH64
    return Arquitectura.DESCONOCIDA


def _de_kernel(estado: Mapping[str, object]) -> Arquitectura:
    kernel = estado.get("current-kernel")
    if isinstance(kernel, Mapping):
        return normalizar(kernel.get("machine"))
    return Arquitectura.DESCONOCIDA


def _de_kversion(estado: Mapping[str, object]) -> Arquitectura:
    """Busca una palabra de arquitectura en ``kversion``; si hay de las dos, no se decide."""
    texto = estado.get("kversion")
    if not isinstance(texto, str):
        return Arquitectura.DESCONOCIDA
    vistas = {normalizar(p) for p in texto[:_MAX_TEXTO].split()}
    vistas.discard(Arquitectura.DESCONOCIDA)
    return vistas.pop() if len(vistas) == 1 else Arquitectura.DESCONOCIDA


def de_estado_nodo(estado: Mapping[str, object]) -> Arquitectura:
    """Arquitectura según ``current-kernel.machine`` y, si no sirve, ``kversion``."""
    arq = _de_kernel(estado)
    return arq if arq != Arquitectura.DESCONOCIDA else _de_kversion(estado)


def de_lista_cpu(modelos: Sequence[ModeloCpu]) -> Arquitectura:
    """Heurística (DT-D6 paso 4): ``kvm64`` → x86; ``cortex-a53``/``neoverse-n1`` sin él → ARM."""
    nombres = {m.nombre for m in modelos}
    if "kvm64" in nombres:
        return Arquitectura.X86_64
    if nombres & _MODELOS_ARM:
        return Arquitectura.AARCH64
    return Arquitectura.DESCONOCIDA


def _motivo_de_error(error: Exception) -> str:
    if isinstance(error, ErrorProxLaunch) and error.codigo == CodigoError.PERMISO_INSUFICIENTE:
        return MOTIVO_SIN_PERMISO
    return MOTIVO_NO_RESPONDE  # 595/596, red y cualquier otro fallo


def detectar_nodo(
    cliente: ClienteProxmox,
    nodo: str,
    *,
    recursos: Mapping[str, str | None] | None = None,
    modelos_cpu: Sequence[ModeloCpu] | None = None,
) -> ArquitecturaNodo:
    """Arquitectura de UN nodo en línea. Nunca lanza.

    ``recursos`` es el resultado de ``recursos_nodos()`` (9.2) o ``None``; con el nodo ahí y
    un valor válido no se hace ninguna llamada. Un nodo con fila EN LÍNEA pero valor ``None`` (sin
    ``host-arch``: en 9.2 solo lo publican los nodos no x86) es ``X86_64`` si el estado del nodo
    no da nada mejor (LAB-D-1); si ese estado dice que el nodo es anterior a 9.2, no se supone
    nada (un nodo viejo en un clúster mixto tampoco publica ``host-arch``).
    ``modelos_cpu`` es la lista de CPU del nodo si ya se leyó (no se lee aquí).
    """
    motivo: str | None = None
    version_nodo: tuple[int, int] | None = None
    crudo = None if recursos is None else recursos.get(nodo)
    fila_sin_arch = recursos is not None and nodo in recursos and crudo is None
    if crudo is not None:
        arq = normalizar(crudo)
        if arq != Arquitectura.DESCONOCIDA:
            return ArquitecturaNodo(arq, FuenteArquitectura.RECURSOS)
        motivo = MOTIVO_FORMATO
    try:
        estado: Mapping[str, Any] = cliente.estado_nodo(nodo)
    except Exception as e:  # el descubrimiento nunca se rompe por esto (DT-D6)
        motivo = _motivo_de_error(e)
        _log.warning("Sin estado del nodo %s para la arquitectura: %s", nodo, type(e).__name__)
    else:
        version_nodo = _version_de_estado(estado)
        arq = _de_kernel(estado)
        if arq != Arquitectura.DESCONOCIDA:
            return ArquitecturaNodo(arq, FuenteArquitectura.KERNEL)
        arq = _de_kversion(estado)
        if arq != Arquitectura.DESCONOCIDA:
            return ArquitecturaNodo(arq, FuenteArquitectura.KVERSION)
        motivo = MOTIVO_FORMATO
    if fila_sin_arch and (version_nodo is None or version_nodo >= _VERSION_HOST_ARCH):
        # 9.2 solo publica host-arch en nodos no x86: la clave ausente en un nodo en línea es x86
        # (``recursos_nodos`` ya descarta las filas de nodos que no están en línea).
        return ArquitecturaNodo(Arquitectura.X86_64, FuenteArquitectura.RECURSOS_AUSENTE)
    if modelos_cpu:
        arq = de_lista_cpu(modelos_cpu)
        if arq != Arquitectura.DESCONOCIDA:
            return ArquitecturaNodo(arq, FuenteArquitectura.LISTA_CPU)
    return ArquitecturaNodo(Arquitectura.DESCONOCIDA, FuenteArquitectura.NINGUNA, motivo)


def detectar(
    sesion: Sesion,
    nodos_en_linea: Sequence[str],
    *,
    recursos: Mapping[str, str | None] | None,
    modelos_cpu: Mapping[str, Sequence[ModeloCpu]] | None = None,
) -> dict[str, ArquitecturaNodo]:
    """Arquitectura de cada nodo en línea; ``estado_nodo`` solo para los que ``recursos`` no cubre.

    ``modelos_cpu`` (opcional): listas de CPU ya leídas por nodo, para la heurística. Nunca lanza.
    """
    return {
        n: detectar_nodo(
            sesion.cliente,
            n,
            recursos=recursos,
            modelos_cpu=None if modelos_cpu is None else modelos_cpu.get(n),
        )
        for n in nodos_en_linea
    }


def forzar(inv: Inventario, nodo: str, arq: Arquitectura | None) -> Inventario:
    """Copia del inventario con la arquitectura de ``nodo`` fijada a mano (``MANUAL``, P-D3).

    Con ``None`` (o ``DESCONOCIDA``) se quita la marca manual: el nodo queda sin dato hasta que
    quien llama vuelva a detectar. No modifica el inventario recibido.
    """
    nuevas = dict(inv.arquitecturas)
    if arq is None or arq == Arquitectura.DESCONOCIDA:
        actual = nuevas.get(nodo)
        if actual is not None and actual.fuente == FuenteArquitectura.MANUAL:
            del nuevas[nodo]
    else:
        nuevas[nodo] = ArquitecturaNodo(arq, FuenteArquitectura.MANUAL)
    return dataclasses.replace(inv, arquitecturas=nuevas)
