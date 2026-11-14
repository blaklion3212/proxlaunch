"""ServicioCatalogo: lo que el servidor tiene para elegir el origen del SO (solo GET).

Lee bajo demanda (nunca al conectar): archivos ``iso``/``import`` por storage, plantillas y su
configuración, y los formatos de los storages. Los permisos efectivos NO se vuelven a pedir:
se reutilizan los que ya trajo el descubrimiento (``inv.catalogo.permisos``). Ninguna operación
de este módulo escribe en el servidor (INV-M1, INV-O12).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Collection, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, TypeVar

from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import MAX_CONSULTAS_SIMULTANEAS
from proxlaunch.nucleo.modelos.catalogo import (
    CatalogoServidor,
    Contenido,
    DetallePlantilla,
    ListadoStorage,
    Plantilla,
    Volumen,
)
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, DetalleIso
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.origen.constantes import MAX_CATALOGO
from proxlaunch.nucleo.origen.nombres import partes_volid
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion

if TYPE_CHECKING:
    from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo

_log = logging.getLogger("proxlaunch.servicios.catalogo")

_T = TypeVar("_T")
_R = TypeVar("_R")

# Un fallo de estos no es del storage sino de la sesión: se propaga en vez de anotarse.
_CODIGOS_FATALES = frozenset(
    {
        CodigoError.SESION_EXPIRADA,
        CodigoError.CREDENCIALES_INVALIDAS,
        CodigoError.HUELLA_CAMBIADA,
        CodigoError.HUELLA_NO_CONFIADA,
    }
)

TIPO_FUENTE_ISO = "iso"
TIPO_FUENTE_DRIVERS = "drivers"
TIPO_FUENTE_IMAGEN = "imagen"


class ServicioCatalogo:
    """Lecturas del catálogo del servidor, en paralelo y con tope de consultas simultáneas."""

    def __init__(
        self, sesion: Sesion, reloj: Reloj, *, max_consultas: int = MAX_CONSULTAS_SIMULTANEAS
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._max_consultas = max(1, max_consultas)

    @property
    def _cliente(self) -> ClienteProxmox:
        return self._sesion.cliente

    def _en_paralelo(self, funcion: Callable[[_T], _R], elementos: Iterable[_T]) -> list[_R]:
        """Aplica ``funcion`` a cada elemento con a lo sumo ``max_consultas`` hilos; respeta el
        orden de entrada y propaga la primera excepción."""
        lista = list(elementos)
        if len(lista) <= 1:
            return [funcion(e) for e in lista]
        with ThreadPoolExecutor(max_workers=min(len(lista), self._max_consultas)) as pool:
            return [f.result() for f in [pool.submit(funcion, e) for e in lista]]

    # --- Listados de archivos -------------------------------------------------------------

    def listar(
        self, inv: Inventario, nodo: str, contenido: Contenido
    ) -> tuple[ListadoStorage, ...]:
        """Un ``ListadoStorage`` por cada storage ACTIVO del nodo con ese contenido.

        La clasificación sale del contenido configurado y nunca del nombre (RF-O04). Un 403
        en un storage queda como ``CATALOGO_SIN_PERMISO`` en ese listado (E-O05) y no impide
        leer los demás. Se muestran como máximo ``MAX_CATALOGO`` archivos por storage.
        """
        candidatos = [
            s
            for s in inv.storages_todos.get(nodo, ())
            if contenido.value in s.contenido and s.activo
        ]
        return tuple(self._en_paralelo(lambda s: self._listar_uno(nodo, s, contenido), candidatos))

    def _listar_uno(self, nodo: str, storage: Storage, contenido: Contenido) -> ListadoStorage:
        try:
            volumenes = self._cliente.contenido_storage(nodo, storage.id, contenido)
        except ErrorProxLaunch as e:
            if e.codigo in _CODIGOS_FATALES:
                raise
            if e.codigo == CodigoError.PERMISO_INSUFICIENTE:
                e = ErrorProxLaunch(
                    CodigoError.CATALOGO_SIN_PERMISO, {"storage": storage.id}, e.detalle_tecnico
                )
            _log.info("Listado de %s en %s no disponible: %s", storage.id, nodo, e.codigo)
            return ListadoStorage(nodo, storage.id, contenido, error=e)
        ordenados = sorted(volumenes, key=lambda v: (v.nombre.casefold(), v.volid))
        return ListadoStorage(nodo, storage.id, contenido, tuple(ordenados[:MAX_CATALOGO]))

    # --- Plantillas -----------------------------------------------------------------------

    def plantillas(self) -> tuple[Plantilla, ...]:
        """Plantillas visibles para el token (``GET /cluster/resources?type=vm``)."""
        return tuple(self._cliente.plantillas_visibles())

    def detalle_plantilla(self, nodo: str, vmid: int) -> DetallePlantilla | None:
        """Configuración parseada de la plantilla; ``None`` si no existe o no se puede ver."""
        try:
            config = self._cliente.config_vm(nodo, vmid)
        except ErrorProxLaunch as e:
            if e.codigo == CodigoError.PERMISO_INSUFICIENTE:
                return None
            raise
        return None if config is None else detalle_de_config(config)

    # --- Formatos -------------------------------------------------------------------------

    def formatos(self, inv: Inventario, nodos: Collection[str]) -> dict[str, frozenset[str]]:
        """Formatos admitidos por storage (``?format=1``) unidos entre los nodos dados.

        Un nodo que no responde se omite (la validación cae en la tabla fija de V-09).
        """
        del inv  # los storages se vuelven a pedir con formatos; el inventario no cambia

        def _de_nodo(nodo: str) -> list[Storage]:
            try:
                return self._cliente.storages(nodo, con_formatos=True)
            except ErrorProxLaunch as e:
                if e.codigo in _CODIGOS_FATALES:
                    raise
                _log.info("Formatos de %s no disponibles: %s", nodo, e.codigo)
                return []

        resultado: dict[str, frozenset[str]] = {}
        for storages in self._en_paralelo(_de_nodo, sorted(nodos)):
            for s in storages:
                if s.formatos:
                    resultado[s.id] = resultado.get(s.id, frozenset()) | s.formatos
        return resultado

    # --- Lectura completa para un plan ----------------------------------------------------

    def leer_para(
        self, inv: Inventario, necesidades: NecesidadesCatalogo, nodos: Collection[str]
    ) -> CatalogoServidor:
        """Lee SOLO lo que piden ``necesidades`` y lo devuelve como ``CatalogoServidor``.

        Con ``necesidades.vacias`` no hace ninguna petición. Los permisos se reutilizan de
        ``inv.catalogo`` (sin GET nuevo).
        """
        permisos = inv.catalogo.permisos if inv.catalogo is not None else None
        listados: list[ListadoStorage] = []
        plantillas: tuple[Plantilla, ...] | None = None
        formatos: dict[str, frozenset[str]] = {}
        if not necesidades.vacias:
            nodos_ord = sorted(nodos)
            for contenido in sorted(necesidades.contenidos, key=lambda c: c.value):
                for nodo in nodos_ord:
                    listados.extend(self.listar(inv, nodo, contenido))
            if necesidades.plantillas:
                plantillas = self._plantillas_usadas(necesidades.plantillas)
            if necesidades.formatos:
                formatos = self.formatos(inv, nodos_ord)
        return CatalogoServidor(
            permisos=permisos,
            listados=tuple(listados),
            plantillas=plantillas,
            formatos=formatos,
            leido_en=self._reloj.ahora(),
        )

    def _plantillas_usadas(self, nombres: Collection[str]) -> tuple[Plantilla, ...]:
        """Todas las plantillas visibles; las de los ``nombres`` dados llevan su detalle."""
        todas = self.plantillas()
        usadas = [p for p in todas if p.nombre in nombres]
        detalles = self._en_paralelo(lambda p: self.detalle_plantilla(p.nodo, p.vmid), usadas)
        con_detalle = {
            (p.nodo, p.vmid): dataclasses.replace(p, detalle=d)
            for p, d in zip(usadas, detalles, strict=True)
        }
        return tuple(con_detalle.get((p.nodo, p.vmid), p) for p in todas)


# --- Fuente vigente (INV-O8) ------------------------------------------------------------


def _fuentes_de(cfg: ConfiguracionVM) -> list[tuple[str, str, str | None]]:
    """``(tipo, nombre, volid)`` de cada archivo que la creación necesita."""
    detalle = cfg.detalle_origen
    if cfg.origen == OrigenSO.ISO and isinstance(detalle, DetalleIso):
        fuentes = [(TIPO_FUENTE_ISO, detalle.iso.nombre, detalle.iso.volid)]
        if detalle.drivers is not None and not detalle.sin_drivers:
            fuentes.append((TIPO_FUENTE_DRIVERS, detalle.drivers.nombre, detalle.drivers.volid))
        return fuentes
    if cfg.origen == OrigenSO.IMPORTAR_DISCO and isinstance(detalle, DetalleImportacion):
        return [(TIPO_FUENTE_IMAGEN, detalle.imagen.nombre, detalle.imagen.volid)]
    return []


def fuente_vigente(cliente: ClienteProxmox, cfg: ConfiguracionVM) -> ErrorProxLaunch | None:
    """Relee el contenido del storage de cada archivo fuente y comprueba que sigue (INV-O8).

    Devuelve ``None`` si todo está (también si no hay archivo fuente: disco vacío o clon);
    ``FUENTE_DESAPARECIO`` (E-O16) si un volid ya no está; y, ante cualquier otro fallo de
    lectura, ese error: quien crea no debe enviar el ``POST`` sin certeza de la fuente.
    """
    for tipo, nombre, volid in _fuentes_de(cfg):
        partes = partes_volid(volid) if volid else None
        if partes is None:
            return ErrorProxLaunch(CodigoError.FUENTE_DESAPARECIO, {"nombre": nombre, "tipo": tipo})
        storage, contenido, _ = partes
        try:
            volumenes: list[Volumen] = cliente.contenido_storage(cfg.nodo, storage, contenido)
        except ErrorProxLaunch as e:
            return e
        if not any(v.volid == volid for v in volumenes):
            return ErrorProxLaunch(CodigoError.FUENTE_DESAPARECIO, {"nombre": nombre, "tipo": tipo})
    return None


def con_catalogo(inv: Inventario, catalogo: CatalogoServidor | None) -> Inventario:
    """Copia del inventario con ese catálogo (el original no cambia)."""
    return dataclasses.replace(inv, catalogo=catalogo)
