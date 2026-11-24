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
from typing import TYPE_CHECKING, Any, TypeVar

from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.traductor_errores import CODIGOS_DE_RED
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.lectura import leer_info_firewall
from proxlaunch.nucleo.hardware_cluster.lectura import leer_info_hardware
from proxlaunch.nucleo.lote.constantes import MAX_CONSULTAS_SIMULTANEAS
from proxlaunch.nucleo.modelos.catalogo import (
    CatalogoServidor,
    Contenido,
    DetallePlantilla,
    ListadoSnippets,
    ListadoStorage,
    PermisosEfectivos,
    Plantilla,
    Volumen,
)
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, DetalleIso
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.opciones.modelos import EstadoPools, PoliticaEtiquetas, PoolsServidor
from proxlaunch.nucleo.origen.asistente import TABLA_SO
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.origen.constantes import MAX_CATALOGO
from proxlaunch.nucleo.origen.nombres import partes_volid
from proxlaunch.nucleo.origen.permisos import estado_privilegio
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


def _arquitecturas_de(inv: Inventario) -> dict[str, Arquitectura]:
    """Arquitectura detectada por nodo (D2); los nodos sin dato no constan."""
    return {nodo: info.arquitectura for nodo, info in inv.arquitecturas.items()}


def leer_pools(cliente: ClienteProxmox, permisos: PermisosEfectivos | None) -> PoolsServidor:
    """Pools visibles (``GET /pools``) y por qué, si no hay ninguno (fase A, arq. §3.5).

    Lista no vacía → OK. Vacía: sin ``Pool.Audit`` en ``/pool`` Proxmox la devuelve vacía en
    silencio (SIN_PERMISO); con permisos desconocidos, DESCONOCIDO; con el privilegio, OK sin
    pools. Un fallo de lectura es ERROR (nunca bloquea); los errores de sesión se propagan.
    """
    try:
        filas = cliente.pools()
    except ErrorProxLaunch as e:
        if e.codigo in _CODIGOS_FATALES:
            raise
        _log.info("Pools no disponibles: %s", e.codigo)
        return PoolsServidor(EstadoPools.ERROR)
    except Exception:
        _log.exception("Fallo inesperado al leer los pools")
        return PoolsServidor(EstadoPools.ERROR)
    ids = tuple(dict.fromkeys(str(f["poolid"]) for f in filas if isinstance(f.get("poolid"), str)))
    if ids:
        return PoolsServidor(EstadoPools.OK, ids)
    audit = estado_privilegio(permisos, "Pool.Audit", "/pool")
    if audit is None:
        return PoolsServidor(EstadoPools.DESCONOCIDO)
    return PoolsServidor(EstadoPools.OK if audit else EstadoPools.SIN_PERMISO)


def leer_politica_etiquetas(cliente: ClienteProxmox) -> tuple[PoliticaEtiquetas | None, bool]:
    """``(política, fallida)`` desde ``GET /cluster/options`` (fase A, arq. §3.5).

    Un fallo de lectura o un cuerpo inesperado da ``(None, True)``: la validación avisa (V-A09)
    pero no bloquea. Los errores de sesión se propagan.
    """
    try:
        return PoliticaEtiquetas.desde_opciones(cliente.opciones_cluster()), False
    except ErrorProxLaunch as e:
        if e.codigo in _CODIGOS_FATALES:
            raise
        _log.info("Opciones del cluster no disponibles: %s", e.codigo)
    except ValueError:
        _log.info("Opciones del cluster con un cuerpo inesperado")
    except Exception:
        _log.exception("Fallo inesperado al leer las opciones del cluster")
    return None, True


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

    # --- Snippets (fase B, B4) -------------------------------------------------------------

    def leer_snippets(
        self, inv: Inventario, nodos: Collection[str], storages: Collection[str]
    ) -> tuple[ListadoSnippets, ...]:
        """Listado de snippets de cada storage de ``storages`` en los ``nodos`` dados (solo GET).

        Una consulta por (nodo, storage), salvo un storage compartido, que se lista una sola vez
        (en el primer nodo, por orden alfabético, que lo ve) y vale para todos (CA-B4.2.2).
        Solo se consultan los nodos donde el storage está activo y admite ``snippets``. Un fallo
        de un listado queda en ``ListadoSnippets.error`` (el selector pasa a entrada manual y no
        bloquea); un 403 se anota como ``CATALOGO_SIN_PERMISO``. Los errores de sesión se
        propagan. Se muestran como máximo ``MAX_CATALOGO`` archivos por listado.
        """
        pares: list[tuple[str, Storage]] = []
        for id_storage in sorted(set(storages)):
            compartido_leido = False
            for nodo in sorted(set(nodos)):
                storage = next(
                    (
                        s
                        for s in inv.storages_todos.get(nodo, ())
                        if s.id == id_storage and s.activo and "snippets" in s.contenido
                    ),
                    None,
                )
                if storage is None or (storage.compartido and compartido_leido):
                    continue
                compartido_leido = compartido_leido or storage.compartido
                pares.append((nodo, storage))
        return tuple(self._en_paralelo(lambda par: self._listar_snippets_uno(*par), pares))

    def _listar_snippets_uno(self, nodo: str, storage: Storage) -> ListadoSnippets:
        try:
            snippets = self._cliente.contenido_snippets(nodo, storage.id)
        except ErrorProxLaunch as e:
            if e.codigo in _CODIGOS_FATALES:
                raise
            if e.codigo == CodigoError.PERMISO_INSUFICIENTE:
                e = ErrorProxLaunch(
                    CodigoError.CATALOGO_SIN_PERMISO, {"storage": storage.id}, e.detalle_tecnico
                )
            _log.info("Snippets de %s en %s no disponibles: %s", storage.id, nodo, e.codigo)
            return ListadoSnippets(nodo, storage.id, storage.compartido, error=e)
        ordenados = sorted(snippets, key=lambda sn: (sn.nombre.casefold(), sn.volid))
        return ListadoSnippets(
            nodo, storage.id, storage.compartido, tuple(ordenados[:MAX_CATALOGO])
        )

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
        self,
        inv: Inventario,
        necesidades: NecesidadesCatalogo,
        nodos: Collection[str],
        *,
        opciones: bool = False,
    ) -> CatalogoServidor:
        """Lee SOLO lo que piden ``necesidades`` y lo devuelve como ``CatalogoServidor``.

        Con ``necesidades.vacias`` y sin ``opciones`` no hace ninguna petición. Los permisos se
        reutilizan de ``inv.catalogo`` (sin GET nuevo). Con ``opciones=True`` (fase A) lee además
        ``GET /pools`` y ``GET /cluster/options`` (dos GET por lectura, no por MV); sin ello se
        conservan los pools y la política que ya traía ``inv.catalogo``. Fase C: con
        ``necesidades.firewall`` lee además los grupos, el firewall general, el contenido de los
        grupos elegidos y el firewall de cada plantilla usada; sin él conserva el anterior.
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
        previo = inv.catalogo
        extra: dict[str, Any] = {}
        # Fase B: solo se listan los storages de los snippets elegidos; sin ellos se conserva lo
        # que ya hubiera (sin ninguna consulta nueva).
        if necesidades.snippets:
            extra["snippets"] = self.leer_snippets(inv, nodos, necesidades.snippets)
        elif previo is not None and previo.snippets:
            extra["snippets"] = previo.snippets
        if opciones:
            politica, fallida = leer_politica_etiquetas(self._cliente)
            extra |= {
                "pools": leer_pools(self._cliente, permisos),
                "politica_etiquetas": politica,
                "politica_etiquetas_fallida": fallida,
            }
        elif previo is not None:
            extra |= {
                "pools": previo.pools,
                "politica_etiquetas": previo.politica_etiquetas,
                "politica_etiquetas_fallida": previo.politica_etiquetas_fallida,
            }
        # Fase C (DT-C11): lecturas del firewall solo si alguna fila usa C3; sin C3, cero GET y se
        # conserva lo que ya hubiera.
        if necesidades.firewall:
            elegidas = [p for p in plantillas or () if p.nombre in necesidades.firewall_plantillas]
            extra["firewall"] = leer_info_firewall(
                self._cliente, permisos, necesidades.grupos_firewall, elegidas
            )
        elif previo is not None:
            extra["firewall"] = previo.firewall
        # Fase D (DT-D12): mapeos, ``check-node`` y CPU personalizadas solo si alguna fila los
        # usa; sin D3, cero GET y se conserva lo que ya hubiera.
        if necesidades.mapeos or necesidades.cpus_personalizadas:
            extra["hardware"] = leer_info_hardware(
                self._cliente,
                permisos,
                self._sesion.capacidades,
                necesidades,
                nodos,
                previo.hardware if previo is not None else None,
                _arquitecturas_de(inv),
            )
        elif previo is not None:
            extra["hardware"] = previo.hardware
        return CatalogoServidor(
            permisos=permisos,
            listados=tuple(listados),
            plantillas=plantillas,
            formatos=formatos,
            leido_en=self._reloj.ahora(),
            **extra,
        )

    def leer_hardware_seccion(
        self, inv: Inventario, nodos: Collection[str], *, cpus: bool = False
    ) -> CatalogoServidor:
        """Lee los mapeos (2 GET, una vez por conexión) al abrir la sección «Hardware del clúster».

        Con ``cpus=True`` lee además los modelos de CPU de ``nodos`` (≤ 1 GET por nodo, con la
        caché de lo ya leído). Devuelve el catálogo previo con ``hardware`` completado; los
        permisos y el resto no se tocan. Un fallo queda anotado en ``hardware`` (V-D50, V-D62).
        """
        from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo  # evita el ciclo

        previo = inv.catalogo
        info = leer_info_hardware(
            self._cliente,
            previo.permisos if previo is not None else None,
            self._sesion.capacidades,
            NecesidadesCatalogo(),
            nodos,
            previo.hardware if previo is not None else None,
            _arquitecturas_de(inv),
            leer_mapeos=True,
            cpus_en=nodos if cpus else (),
        )
        if previo is None:
            return CatalogoServidor(leido_en=self._reloj.ahora(), hardware=info)
        return dataclasses.replace(previo, hardware=info)

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
        # Misma condición que el constructor de la petición (QA-M4-06): solo si el SO usa drivers.
        usa_drivers = cfg.tipo_so is not None and TABLA_SO[cfg.tipo_so].drivers
        if detalle.drivers is not None and not detalle.sin_drivers and usa_drivers:
            fuentes.append((TIPO_FUENTE_DRIVERS, detalle.drivers.nombre, detalle.drivers.volid))
        return fuentes
    if cfg.origen == OrigenSO.IMPORTAR_DISCO and isinstance(detalle, DetalleImportacion):
        fuentes = [(TIPO_FUENTE_IMAGEN, detalle.imagen.nombre, detalle.imagen.volid)]
        # Fase D (DT-D14): también las imágenes de los discos 1.. deben seguir en el servidor.
        fuentes.extend(
            (TIPO_FUENTE_IMAGEN, o.imagen.nombre, o.imagen.volid)
            for o in detalle.otras
            if o.imagen is not None
        )
        return fuentes
    return []


def fuente_vigente(cliente: ClienteProxmox, cfg: ConfiguracionVM) -> ErrorProxLaunch | None:
    """Relee el contenido del storage de cada archivo fuente y comprueba que sigue (INV-O8).

    Devuelve ``None`` si todo está (también si no hay archivo fuente: disco vacío o clon);
    ``FUENTE_DESAPARECIO`` (E-O16) si un volid ya no está; y, ante un fallo de lectura
    definitivo (p. ej. un 403), ese error: quien crea no debe enviar el ``POST`` sin certeza
    de la fuente. Los fallos de red (``CODIGOS_DE_RED``: 595/596, servidor sin respuesta) se
    RELANZAN para que quien llama los reintente con su tolerancia de red (QA-M4-05).
    """
    for tipo, nombre, volid in _fuentes_de(cfg):
        partes = partes_volid(volid) if volid else None
        if partes is None:
            return ErrorProxLaunch(CodigoError.FUENTE_DESAPARECIO, {"nombre": nombre, "tipo": tipo})
        storage, contenido, _ = partes
        try:
            volumenes: list[Volumen] = cliente.contenido_storage(cfg.nodo, storage, contenido)
        except ErrorProxLaunch as e:
            if e.codigo in CODIGOS_DE_RED:
                raise
            return e
        if not any(v.volid == volid for v in volumenes):
            return ErrorProxLaunch(CodigoError.FUENTE_DESAPARECIO, {"nombre": nombre, "tipo": tipo})
    return None


def con_catalogo(inv: Inventario, catalogo: CatalogoServidor | None) -> Inventario:
    """Copia del inventario con ese catálogo (el original no cambia)."""
    return dataclasses.replace(inv, catalogo=catalogo)
