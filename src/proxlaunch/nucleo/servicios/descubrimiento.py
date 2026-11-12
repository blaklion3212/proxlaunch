"""Descubrimiento del inventario a partir de una Sesion."""

from __future__ import annotations

import dataclasses
import logging
from concurrent.futures import ThreadPoolExecutor

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Bridge, Inventario, Nodo, Storage, Topologia
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso, Sesion
from proxlaunch.nucleo.validacion import TIPOS_BRIDGE

_log = logging.getLogger("proxlaunch.servicios.descubrimiento")

MAX_HILOS = 8  # tope de nodos consultados a la vez


def descubrir_nodo(sesion: Sesion, nodo: str) -> tuple[list[Storage], list[Bridge]]:
    """Storages con contenido ``images`` y bridges de UN nodo (CA-11.7).

    Los storages inactivos se conservan (la interfaz los muestra deshabilitados,
    CA-11.3). De la red solo se devuelven los tipos ``bridge`` y ``OVSBridge`` (CA-11.5).
    """
    storages = [s for s in sesion.cliente.storages(nodo) if "images" in s.contenido]
    bridges = [b for b in sesion.cliente.bridges(nodo) if b.tipo in TIPOS_BRIDGE]
    return storages, bridges


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
    nodos = sesion.cliente.nodos()
    topologia = _topologia(sesion, nodos)
    proximo_vmid = sesion.cliente.proximo_vmid()

    consultables = [n.nombre for n in topologia.nodos if n.en_linea]
    storages: dict[str, tuple[Storage, ...]] = {n.nombre: () for n in topologia.nodos}
    bridges: dict[str, tuple[Bridge, ...]] = {n.nombre: () for n in topologia.nodos}
    errores: dict[str, ErrorProxLaunch] = {}

    if consultables:
        with ThreadPoolExecutor(max_workers=min(len(consultables), MAX_HILOS)) as pool:
            futuros = {
                nombre: pool.submit(descubrir_nodo, sesion, nombre) for nombre in consultables
            }
            for nombre, futuro in futuros.items():
                try:
                    st, br = futuro.result()
                except ErrorProxLaunch as e:
                    errores[nombre] = e
                    _log.warning("Nodo %s no disponible en el descubrimiento: %s", nombre, e.codigo)
                else:
                    storages[nombre] = tuple(st)
                    bridges[nombre] = tuple(br)

    if errores:
        # Un nodo que falla se marca fuera de línea: así tampoco lo elige el modo Automático.
        topologia = dataclasses.replace(
            topologia,
            nodos=tuple(
                dataclasses.replace(n, en_linea=False) if n.nombre in errores else n
                for n in topologia.nodos
            ),
        )
    return Inventario(
        version=sesion.version,
        topologia=topologia,
        proximo_vmid=proximo_vmid,
        storages=storages,
        bridges=bridges,
        errores_por_nodo=errores,
    )
