"""Lecturas del hardware del clúster (D3): mapeos PCI/USB, ``check-node`` y CPU personalizadas.

Solo GET. Ninguna función lanza un error del servidor salvo los de sesión (que quien llama debe
propagar): un fallo se anota en ``InfoHardwareCluster`` y la validación lo traduce en un aviso
(V-D50, V-D53, V-D62), nunca bloquea (P-D11). Sin necesidades de D3 no se hace ninguna petición.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Collection, Mapping, Sequence
from typing import TYPE_CHECKING

from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import (
    RE_ID_MAPEO,
    ComprobacionNodo,
    InfoHardwareCluster,
    Mapeo,
    ModeloCpu,
    TipoMapeo,
)
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.origen.permisos import estado_mapeo

if TYPE_CHECKING:
    from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo

_log = logging.getLogger("proxlaunch.hardware_cluster.lectura")

# Un fallo de estos no es del hardware sino de la sesión: se propaga en vez de anotarse.
_CODIGOS_FATALES = frozenset(
    {
        CodigoError.SESION_EXPIRADA,
        CodigoError.CREDENCIALES_INVALIDAS,
        CodigoError.HUELLA_CAMBIADA,
        CodigoError.HUELLA_NO_CONFIADA,
    }
)

_ARQ_CON_CAPACIDADES = frozenset({Arquitectura.X86_64, Arquitectura.AARCH64})


def _leer_mapeos(
    cliente: ClienteProxmox,
) -> tuple[tuple[Mapeo, ...] | None, ErrorProxLaunch | None]:
    """Lee PCI y USB (2 GET). Una lista que falla no impide mostrar la otra (CA-D3.1.3).

    Devuelve ``(mapeos, error)``: ``mapeos`` es ``None`` solo si fallaron las dos; ``error`` es el
    primer fallo, con ``params["tipo"]`` = tipos que no se pudieron leer (``pci``, ``usb``).
    """
    leidos: list[Mapeo] = []
    fallidos: list[tuple[TipoMapeo, ErrorProxLaunch]] = []
    for tipo in (TipoMapeo.PCI, TipoMapeo.USB):
        try:
            leidos.extend(cliente.mapeos(tipo))
        except ErrorProxLaunch as e:
            if e.codigo in _CODIGOS_FATALES:
                raise
            _log.info("Mapeos %s no disponibles: %s", tipo.value, e.codigo)
            fallidos.append((tipo, e))
        except Exception:
            _log.exception("Fallo inesperado al leer los mapeos %s", tipo.value)
            fallidos.append((tipo, ErrorProxLaunch(CodigoError.DESCONOCIDO)))
    error: ErrorProxLaunch | None = None
    if fallidos:
        primero = fallidos[0][1]
        params = {**primero.params, "tipo": ",".join(t.value for t, _ in fallidos)}
        error = ErrorProxLaunch(primero.codigo, params, primero.detalle_tecnico)
    if len(fallidos) == 2:
        return None, error
    leidos.sort(key=lambda m: (m.tipo.value, m.id))
    return tuple(leidos), error


def _comprobar(
    cliente: ClienteProxmox, tipo: TipoMapeo, nodo: str, ids: Sequence[str]
) -> dict[str, ComprobacionNodo] | None:
    """``check-node`` de un tipo en un nodo (un ``GET`` para todos los ``ids``).

    ``None`` si falla (aviso, nunca bloquea; P-D11).
    """
    try:
        return cliente.comprobar_mapeos(tipo, nodo, ids)
    except ErrorProxLaunch as e:
        if e.codigo in _CODIGOS_FATALES:
            raise
        _log.info("check-node de %s en %s no disponible: %s", tipo.value, nodo, e.codigo)
    except ValueError:
        _log.info("check-node de un mapeo con identificador no válido: se omite")
    except Exception:
        _log.exception("Fallo inesperado en check-node de %s", tipo.value)
    return None


def _usados(necesidades: NecesidadesCatalogo) -> list[tuple[TipoMapeo, str]]:
    """Mapeos pedidos con tipo e identificador válidos, sin repetir y en orden estable."""
    resultado: set[tuple[TipoMapeo, str]] = set()
    for tipo_txt, id_mapeo in necesidades.mapeos:
        if tipo_txt in (t.value for t in TipoMapeo) and RE_ID_MAPEO.fullmatch(id_mapeo):
            resultado.add((TipoMapeo(tipo_txt), id_mapeo))
    return sorted(resultado, key=lambda par: (par[0].value, par[1]))


def _leer_cpus(
    cliente: ClienteProxmox,
    caps: Capacidades,
    nodo: str,
    arquitecturas: Mapping[str, Arquitectura],
) -> tuple[tuple[ModeloCpu, ...] | None, ErrorProxLaunch | None]:
    """``capabilities/qemu/cpu`` de un nodo; con ``arch=`` solo si ``CAPACIDADES_POR_ARCH``."""
    arch: str | None = None
    if caps.tiene(Funcion.CAPACIDADES_POR_ARCH):
        arq = arquitecturas.get(nodo, Arquitectura.DESCONOCIDA)
        arch = arq.value if arq in _ARQ_CON_CAPACIDADES else None
    try:
        return tuple(cliente.modelos_cpu(nodo, arch=arch)), None
    except ErrorProxLaunch as e:
        if e.codigo in _CODIGOS_FATALES:
            raise
        _log.info("CPU de %s no disponibles: %s", nodo, e.codigo)
        return None, e
    except Exception:
        _log.exception("Fallo inesperado al leer las CPU de un nodo")
        return None, ErrorProxLaunch(CodigoError.DESCONOCIDO)


def leer_info_hardware(
    cliente: ClienteProxmox,
    permisos: PermisosEfectivos | None,
    caps: Capacidades,
    necesidades: NecesidadesCatalogo,
    nodos: Collection[str],
    previo: InfoHardwareCluster | None,
    arquitecturas: Mapping[str, Arquitectura],
    *,
    leer_mapeos: bool = False,
    cpus_en: Collection[str] = (),
) -> InfoHardwareCluster:
    """Completa ``previo`` con lo que falte y piden ``necesidades`` (solo GET).

    - Mapeos: 2 GET (PCI y USB) si aún no se intentó leerlos y el lote usa mapeos o se abre la
      sección (``leer_mapeos``); máximo una vez por conexión (``previo`` conserva el resultado).
    - ``check-node``: una vez por (mapeo usado, nodo del lote donde el mapeo tiene entrada) que no
      conste en ``previo``; se omite si se sabe que falta ``Mapping.Use`` en ese mapeo (V-D63 ya
      bloquea). Un fallo queda en ``errores_comprobacion`` (aviso, P-D11).
    - CPU: una lectura por nodo (de ``nodos`` si el lote usa ``custom-*``, más ``cpus_en``) aún
      no intentado; un fallo queda en ``errores_cpu`` (V-D62).
    Con nada que leer devuelve ``previo`` (o una info vacía) sin ninguna petición.
    """
    base = previo if previo is not None else InfoHardwareCluster()
    mapeos, error_mapeos = base.mapeos, base.error_mapeos
    usados = _usados(necesidades)
    if mapeos is None and error_mapeos is None and (leer_mapeos or usados):
        mapeos, error_mapeos = _leer_mapeos(cliente)

    comprobaciones = list(base.comprobaciones)
    errores_comp = list(base.errores_comprobacion)
    if usados and mapeos is not None:
        por_clave = {(m.tipo, m.id): m for m in mapeos}
        hechos = {(c.tipo.value, c.mapeo, c.nodo) for c in comprobaciones} | set(errores_comp)
        # Un único GET por (tipo, nodo): la respuesta sirve a todos los mapeos de ese tipo.
        por_tipo_nodo: dict[tuple[TipoMapeo, str], list[str]] = {}
        for tipo, id_mapeo in usados:
            mapeo = por_clave.get((tipo, id_mapeo))
            if mapeo is None or estado_mapeo(permisos, tipo, id_mapeo) is False:
                continue  # inexistente (V-D51) o sin permiso (V-D63): no hay nada que comprobar
            for nodo in sorted(set(nodos) & mapeo.nodos()):
                if (tipo.value, id_mapeo, nodo) not in hechos:
                    por_tipo_nodo.setdefault((tipo, nodo), []).append(id_mapeo)
        for (tipo, nodo), ids in sorted(
            por_tipo_nodo.items(), key=lambda kv: (kv[0][0].value, kv[0][1])
        ):
            resultado = _comprobar(cliente, tipo, nodo, ids)
            for id_mapeo in ids:
                if resultado is None or id_mapeo not in resultado:
                    errores_comp.append((tipo.value, id_mapeo, nodo))
                else:
                    comprobaciones.append(resultado[id_mapeo])

    cpus = dict(base.cpus)
    errores_cpu = dict(base.errores_cpu)
    pendientes = set(cpus_en)
    if necesidades.cpus_personalizadas:
        pendientes |= set(nodos)
    for nodo in sorted(pendientes):
        if nodo in cpus or nodo in errores_cpu:
            continue
        modelos, error = _leer_cpus(cliente, caps, nodo, arquitecturas)
        if modelos is not None:
            cpus[nodo] = modelos
        elif error is not None:
            errores_cpu[nodo] = error

    return dataclasses.replace(
        base,
        mapeos=mapeos,
        error_mapeos=error_mapeos,
        comprobaciones=tuple(comprobaciones),
        errores_comprobacion=tuple(
            e
            for e in dict.fromkeys(errores_comp)
            if e not in {(c.tipo.value, c.mapeo, c.nodo) for c in comprobaciones}
        ),
        cpus=cpus,
        errores_cpu=errores_cpu,
    )
