"""Descubrimiento del inventario a partir de una Sesion."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor
from proxlaunch.nucleo.modelos.inventario import (
    Bridge,
    Inventario,
    Nodo,
    RedVirtual,
    Storage,
    Topologia,
)
from proxlaunch.nucleo.red.redes_nodo import RedesNodo, filtrar_vnets
from proxlaunch.nucleo.servicios.catalogo import leer_politica_etiquetas, leer_pools
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso, Sesion, leer_permisos
from proxlaunch.nucleo.validacion import TIPOS_BRIDGE

_log = logging.getLogger("proxlaunch.servicios.descubrimiento")

# Solo estos errores marcan un nodo como sin conexión (CA-11.8).
_CODIGOS_DE_NODO = frozenset(
    {
        CodigoError.NODO_NO_DISPONIBLE,
        CodigoError.SERVIDOR_NO_RESPONDE,
        CodigoError.PERMISO_INSUFICIENTE,  # solo se propaga si es global (ver más abajo)
    }
)

MAX_HILOS = 8  # tope de nodos consultados a la vez


def descubrir_nodo_completo(
    sesion: Sesion, nodo: str
) -> tuple[list[Storage], list[Storage], list[Bridge]]:
    """``(con_images, todos, bridges)`` de UN nodo con las mismas peticiones que M3.

    ``todos`` sale de la misma respuesta de ``GET /nodes/{n}/storage`` (cero GET nuevos,
    MVP 4); ``con_images`` es el filtro histórico y ``bridges`` solo ``bridge`` y ``OVSBridge``.
    """
    todos = list(sesion.cliente.storages(nodo))
    bridges = [b for b in sesion.cliente.bridges(nodo) if b.tipo in TIPOS_BRIDGE]
    return [s for s in todos if "images" in s.contenido], todos, bridges


def descubrir_redes_sdn(sesion: Sesion, nodo: str, interfaces: Collection[str]) -> RedesNodo:
    """VNets de SDN de UN nodo con ``GET /nodes/{n}/network?type=any_bridge`` (C2, DT-C3).

    ``interfaces`` son los nombres de la lista normal de redes del nodo: una entrada sin ``type``
    que ya esté ahí es un bridge conocido, no una VNet. Nunca lanza: un fallo (400/403/500/red)
    queda en ``RedesNodo.error`` y no afecta al resto del descubrimiento (CA-C2.1.3).
    """
    try:
        entradas = sesion.cliente.redes_any_bridge(nodo)
    except ErrorProxLaunch as e:
        _log.warning("Sin lectura de VNets en el nodo %s: %s", nodo, e.codigo)
        return RedesNodo(vnets=(), error=e)
    except Exception as e:  # el descubrimiento no debe romperse por una lectura opcional
        _log.warning("Fallo inesperado leyendo las VNets del nodo %s: %s", nodo, type(e).__name__)
        return RedesNodo(
            vnets=(), error=ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, type(e).__name__)
        )
    return RedesNodo(vnets=filtrar_vnets(entradas, interfaces))


def descubrir_nodo_c(
    sesion: Sesion, nodo: str
) -> tuple[list[Storage], list[Storage], list[Bridge], RedesNodo]:
    """``(con_images, todos, bridges, redes)`` de UN nodo, con las VNets de la fase C.

    Mismas peticiones que ``descubrir_nodo_completo`` pero con la lista de redes leída UNA vez
    (todas las interfaces, que además sirven de filtro para las VNets) y la consulta nueva
    ``?type=any_bridge``, tolerante a errores.
    """
    todos = list(sesion.cliente.storages(nodo))
    interfaces = list(sesion.cliente.bridges(nodo))
    bridges = [b for b in interfaces if b.tipo in TIPOS_BRIDGE]
    redes = descubrir_redes_sdn(sesion, nodo, {b.nombre for b in interfaces})
    return [s for s in todos if "images" in s.contenido], todos, bridges, redes


def descubrir_nodo(sesion: Sesion, nodo: str) -> tuple[list[Storage], list[Bridge]]:
    """Storages con contenido ``images`` y bridges de UN nodo (CA-11.7).

    Los storages inactivos se conservan (la interfaz los muestra deshabilitados,
    CA-11.3). De la red solo se devuelven los tipos ``bridge`` y ``OVSBridge`` (CA-11.5).
    """
    con_images, _, bridges = descubrir_nodo_completo(sesion, nodo)
    return con_images, bridges


def _topologia(sesion: Sesion, nodos: list[Nodo]) -> Topologia:
    """Topología según ``/cluster/status``; ante un 403 queda degradada (A-6)."""
    try:
        estado = sesion.cliente.estado_cluster()
    except ErrorProxLaunch as e:
        if e.codigo != CodigoError.PERMISO_INSUFICIENTE:
            raise
        aviso = Aviso(CodigoAviso.TOPOLOGIA_DEGRADADA, {"nodos": str(len(nodos))})
        if aviso not in sesion.avisos:
            sesion.avisos.append(aviso)
        _log.warning("Sin permiso para /cluster/status: topología degradada")
        return Topologia(es_cluster=False, nombre_cluster=None, nodos=tuple(nodos))
    return Topologia(
        es_cluster=estado.es_cluster, nombre_cluster=estado.nombre_cluster, nodos=tuple(nodos)
    )


def descubrir(sesion: Sesion) -> Inventario:
    """Descubre nodos, storages, bridges y el próximo VMID (RF-11).

    Los nodos en línea se consultan en paralelo. Si un nodo falla, queda registrado en
    ``errores_por_nodo``, se marca fuera de línea y el resto sigue siendo utilizable
    (CA-11.8).
    """
    # Los avisos de topología se recalculan en cada descubrimiento (sin duplicados).
    sesion.avisos[:] = [a for a in sesion.avisos if a.codigo != CodigoAviso.TOPOLOGIA_DEGRADADA]
    nodos = sesion.cliente.nodos()
    topologia = _topologia(sesion, nodos)
    proximo_vmid = sesion.cliente.proximo_vmid()

    consultables = [n.nombre for n in topologia.nodos if n.en_linea]
    storages: dict[str, tuple[Storage, ...]] = {n.nombre: () for n in topologia.nodos}
    storages_todos: dict[str, tuple[Storage, ...]] = {n.nombre: () for n in topologia.nodos}
    bridges: dict[str, tuple[Bridge, ...]] = {n.nombre: () for n in topologia.nodos}
    errores: dict[str, ErrorProxLaunch] = {}
    redes_sdn: dict[str, tuple[RedVirtual, ...]] = {}
    errores_sdn: dict[str, ErrorProxLaunch] = {}

    if consultables:
        with ThreadPoolExecutor(max_workers=min(len(consultables), MAX_HILOS)) as pool:
            futuros = {
                nombre: pool.submit(descubrir_nodo_c, sesion, nombre) for nombre in consultables
            }
            for nombre, futuro in futuros.items():
                try:
                    st, todos, br, redes = futuro.result()
                except ErrorProxLaunch as e:
                    if e.codigo not in _CODIGOS_DE_NODO:
                        # Un error de sesión o de permisos no es un nodo caído: se propaga.
                        raise
                    errores[nombre] = e
                    _log.warning("Nodo %s no disponible en el descubrimiento: %s", nombre, e.codigo)
                else:
                    storages[nombre] = tuple(st)
                    storages_todos[nombre] = tuple(todos)
                    bridges[nombre] = tuple(br)
                    if redes.error is not None:
                        errores_sdn[nombre] = redes.error
                    else:
                        redes_sdn[nombre] = redes.vnets

    if errores and len(errores) == len(consultables):
        permiso = [e for e in errores.values() if e.codigo == CodigoError.PERMISO_INSUFICIENTE]
        if len(permiso) == len(errores):
            # Falta el permiso en todos los nodos: es un problema global, no nodos caídos.
            raise permiso[0]

    if errores:
        # Un nodo que falla se marca fuera de línea: así tampoco lo elige el modo Automático.
        topologia = dataclasses.replace(
            topologia,
            nodos=tuple(
                dataclasses.replace(n, en_linea=False) if n.nombre in errores else n
                for n in topologia.nodos
            ),
        )
    # Los permisos efectivos se leen UNA vez aquí (antes los pedía RF-12 por su cuenta). El
    # resto del catálogo (listados, plantillas, formatos) se lee bajo demanda con
    # ``ServicioCatalogo``. Si la consulta falla quedan como desconocidos (``None``).
    # Fase A: pools y política de etiquetas (dos GET por conexión, nunca por MV).
    permisos = leer_permisos(sesion)
    politica, politica_fallida = leer_politica_etiquetas(sesion.cliente)
    return Inventario(
        version=sesion.version,
        topologia=topologia,
        proximo_vmid=proximo_vmid,
        storages=storages,
        bridges=bridges,
        errores_por_nodo=errores,
        redes_sdn=redes_sdn,
        errores_sdn=errores_sdn,
        storages_todos=storages_todos,
        catalogo=CatalogoServidor(
            permisos=permisos,
            pools=leer_pools(sesion.cliente, permisos),
            politica_etiquetas=politica,
            politica_etiquetas_fallida=politica_fallida,
        ),
    )
