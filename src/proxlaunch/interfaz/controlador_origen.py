"""Controlador del origen del SO: catálogo, capacidades, storages recordados y transferencias.

Reúne el estado de la sesión que necesita el selector «¿Cómo quieres crear la máquina?» (RF-O01,
RF-O02, RF-O05, RF-O06, RF-O07, RF-O09 a RF-O12, RF-O19, RF-O24, RF-O25, RF-O27) para que la
ventana principal solo lo enlace:

- lee el catálogo (ISO, imágenes, plantillas) bajo demanda y fuera del hilo de la interfaz, y lo
  deja en ``Inventario.catalogo`` para que validación, resolución y creación lo vean;
- calcula las capacidades de origen del servidor y del nodo efectivo;
- decide, pregunta y recuerda el storage de cada contenido en el perfil de conexión;
- abre los diálogos de subida y descarga (una transferencia a la vez) y las registra;
- resuelve el origen de una configuración (puro) y aporta las reglas de interfaz V-O26 y V-O27.

Toda E/S va en trabajadores (``Lanzador``); nunca se guardan secretos ni URL completas.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable, Collection
from datetime import datetime

from PySide6.QtCore import QCoreApplication, QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QDialog, QWidget

from proxlaunch.interfaz.dialogos.catalogo import FuenteCatalogo
from proxlaunch.interfaz.dialogos.elegir_storage import DialogoElegirStorage
from proxlaunch.interfaz.dialogos.transferencia import DialogoDescarga, DialogoSubida
from proxlaunch.interfaz.textos import texto_error
from proxlaunch.interfaz.trabajadores import (
    Lanzador,
    guardar_storage_recordado,
    leer_catalogo_para,
    leer_cpus,
    leer_detalle_plantilla,
    leer_hardware_cluster,
    leer_listados,
    leer_plantillas,
)
from proxlaunch.interfaz.vistas.selector_origen import PeticionFuente, SelectorOrigen
from proxlaunch.nucleo.cloudinit.modelos import InfoCloudInitPlantilla
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import InfoFirewall
from proxlaunch.nucleo.hardware_cluster.modelos import InfoHardwareCluster
from proxlaunch.nucleo.lote.filas import filas_efectivas
from proxlaunch.nucleo.lote.modelos import DefinicionLote
from proxlaunch.nucleo.modelos.catalogo import (
    CatalogoServidor,
    Contenido,
    DetallePlantilla,
    ListadoSnippets,
    ListadoStorage,
    PermisosEfectivos,
    Plantilla,
)
from proxlaunch.nucleo.modelos.conexion import PerfilConexion
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleClon, RefPlantilla
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.opciones.modelos import EstadoPools, PoliticaEtiquetas, PoolsServidor
from proxlaunch.nucleo.origen.capacidades_origen import CapacidadesOrigen, calcular_capacidades
from proxlaunch.nucleo.origen.clon import modo_efectivo
from proxlaunch.nucleo.origen.constantes import SHA256_VIRTIO_WIN, URL_VIRTIO_WIN
from proxlaunch.nucleo.origen.resolucion import (
    NecesidadesCatalogo,
    necesidades_catalogo,
    resolver_origen,
)
from proxlaunch.nucleo.origen.storages import (
    TipoDecision,
    candidatos,
    con_recordado,
    decidir_storage,
    recordado_de,
)
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.catalogo import ServicioCatalogo
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.transferencias.modelos import (
    EstadoTransferencia,
    ResultadoTransferencia,
)
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion, ServicioTransferencias
from proxlaunch.nucleo.validacion import Problema, Severidad

_log = logging.getLogger("proxlaunch.interfaz.controlador_origen")

# Tiempo máximo que se espera a que una transferencia cancelada deje de escribir al cerrar.
ESPERA_CANCELACION_S = 3.0

_Clave = tuple[str, Contenido]


def leer_snippets_del_nodo(
    sesion: Sesion, reloj: Reloj, inv: Inventario, nodo: str, storages: tuple[str, ...]
) -> tuple[ListadoSnippets, ...]:
    """Lista los snippets de los almacenamientos de un nodo (solo GET, en un trabajador)."""
    return ServicioCatalogo(sesion, reloj).leer_snippets(inv, [nodo], storages)


def _hora_local() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


class ControladorOrigen(QObject):
    """Estado y acciones del origen del SO para la sesión activa.

    Señales:
    - ``catalogo_cargado(object)``: ``CatalogoServidor`` actualizado (ya está en el inventario).
    - ``plantillas_cargadas(object)``: tupla de ``Plantilla`` (con detalle si se leyó).
    - ``capacidades_cambiadas(object)``: ``CapacidadesOrigen | None``.
    - ``transferencia_terminada(object)``: ``ResultadoTransferencia``.
    - ``storage_mv_elegido(str)``: el usuario eligió el storage de discos de este servidor.
    - ``hardware_leido(object)``: ``InfoHardwareCluster | None`` tras leer los mapeos o los modelos
      de CPU (D3); ``None`` si la lectura falló del todo.
    - ``fallo(object)``: ``ErrorProxLaunch`` de una lectura (la ventana decide cómo mostrarlo).
    - ``mensaje(str)``: texto breve para la barra de estado.
    """

    catalogo_cargado = Signal(object)
    plantillas_cargadas = Signal(object)
    capacidades_cambiadas = Signal(object)
    transferencia_terminada = Signal(object)
    storage_mv_elegido = Signal(str)
    hardware_leido = Signal(object)
    fallo = Signal(object)
    mensaje = Signal(str)

    def __init__(
        self,
        lanzador: Lanzador,
        repositorio_perfiles: RepositorioPerfiles,
        reloj: Reloj,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._lanzador = lanzador
        self._repositorio = repositorio_perfiles
        self._reloj = reloj
        self._sesion: Sesion | None = None
        self._inv: Inventario | None = None
        self._servicio_transferencias: ServicioTransferencias | None = None
        self._registro = RegistroSesion()
        self._perfil_id: str | None = None
        self._selector: SelectorOrigen | None = None
        self._nodo_de: Callable[[], str] = lambda: ""
        self._avanzado = False
        self._ocupado = False  # lote en ejecución o simulación: no hay transferencias
        # Catálogo leído (se vuelca en ``Inventario.catalogo`` con ``_publicar``).
        self._permisos: PermisosEfectivos | None = None
        self._listados: dict[_Clave, tuple[ListadoStorage, ...]] = {}
        self._errores_lectura: dict[_Clave, ErrorProxLaunch] = {}
        self._plantillas: tuple[Plantilla, ...] | None = None
        self._formatos: dict[str, frozenset[str]] = {}
        # Fase B: snippets leídos por (nodo, almacenamiento) (DT-B11).
        self._snippets: dict[tuple[str, str], ListadoSnippets] = {}
        # Fase A: pools y política de etiquetas del servidor (los lee el descubrimiento).
        self._pools = PoolsServidor(EstadoPools.NO_LEIDO)
        self._politica_etiquetas: PoliticaEtiquetas | None = None
        self._politica_etiquetas_fallida = False
        # Fase C: lecturas del firewall de «Comprobar» (DT-C11); se conservan al reconstruir.
        self._firewall: InfoFirewall | None = None
        # Fase D (D3): mapeos y modelos de CPU leídos en esta conexión (RNF-D4: una sola vez).
        self._hardware: InfoHardwareCluster | None = None
        self._en_curso: set[object] = set()  # lecturas lanzadas y aún sin respuesta
        self._fallidas: set[object] = set()  # lecturas que fallaron: no se repiten solas
        self._necesidades_hechas: set[NecesidadesCatalogo] = set()
        self._gen = 0  # descarta lecturas tardías tras cambiar de servidor o actualizar
        # Capacidades y estado del selector.
        self._caps: CapacidadesOrigen | None = None
        self._nodo_caps: str | None = None
        self._ultimo_clon: object = None
        # Transferencias.
        self._dialogo: DialogoSubida | DialogoDescarga | None = None
        self._pendiente: tuple[FuenteCatalogo | None, str] | None = None
        self._preguntando = False

    # ------------------------------------------------------------------------------------
    # Propiedades (también el protocolo ``ControladorTransferencia`` de los diálogos)
    # ------------------------------------------------------------------------------------

    @property
    def lanzador(self) -> Lanzador:
        return self._lanzador

    @property
    def servicio_transferencias(self) -> ServicioTransferencias:
        if self._servicio_transferencias is None:
            raise RuntimeError("No hay sesión: no hay servicio de transferencias")
        return self._servicio_transferencias

    @property
    def inventario(self) -> Inventario | None:
        return self._inv

    @property
    def modo_avanzado(self) -> bool:
        return self._avanzado

    @modo_avanzado.setter
    def modo_avanzado(self, valor: bool) -> None:
        self._avanzado = valor

    @property
    def registro(self) -> RegistroSesion:
        """Archivos subidos o descargados en la sesión (RF-O25); no se persiste."""
        return self._registro

    @property
    def transferencia_activa(self) -> bool:
        """Hay una subida o descarga corriendo (para el cierre de la aplicación, CA-O12.4)."""
        dialogo = self._dialogo
        if dialogo is not None and dialogo.transferencia_en_curso:
            return True
        servicio = self._servicio_transferencias
        return servicio is not None and servicio.ocupado

    @property
    def perfil(self) -> PerfilConexion | None:
        return None if self._sesion is None else self._sesion.perfil

    # ------------------------------------------------------------------------------------
    # Sesión e inventario
    # ------------------------------------------------------------------------------------

    def establecer_sesion(self, sesion: Sesion | None, inv: Inventario | None) -> None:
        """Nueva sesión (o ``None`` al cerrarla). Con otro servidor se olvida todo lo leído
        del anterior y los archivos subidos (CA-O05.7); nunca se arrastran storages recordados."""
        if sesion is not self._sesion:
            self._hardware = None  # lo leído (mapeos, CPU) vale para una sola conexión
        self._sesion = sesion
        if sesion is None:
            # La lista de archivos subidos se conserva al cerrar la sesión (CA-O25.3).
            self._servicio_transferencias = None
            self._inv = None
            self._reiniciar_lecturas()
            self._recalcular_capacidades(None)
            return
        if sesion.perfil.id != self._perfil_id:
            self._registro.vaciar()
        self._perfil_id = sesion.perfil.id
        self._servicio_transferencias = ServicioTransferencias(
            sesion, self._reloj, self._registro, hora_local=_hora_local
        )
        if inv is not None:
            self.adoptar(inv)
        else:
            self._inv = None
            self._reiniciar_lecturas()
            self._recalcular_capacidades(None)

    def adoptar(self, inv: Inventario) -> Inventario:
        """Toma un inventario recién descubierto y le pone el catálogo vigente.

        Un descubrimiento nuevo (Actualizar, replanificar, reintento) empieza con el catálogo
        vacío: lo ya leído se descarta y se vuelve a pedir lo que haga falta.
        """
        self._inv = inv
        self._permisos = inv.catalogo.permisos if inv.catalogo is not None else None
        # Fase A: pools y política de etiquetas los lee el descubrimiento; no se pierden al
        # reconstruir el catálogo.
        previo = inv.catalogo
        if previo is not None:
            self._pools = previo.pools
            self._politica_etiquetas = previo.politica_etiquetas
            self._politica_etiquetas_fallida = previo.politica_etiquetas_fallida
            self._firewall = previo.firewall
        else:
            self._firewall = None
        self._reiniciar_lecturas()
        self._reconstruir()
        self._recalcular_capacidades(self._nodo_caps)
        return inv

    def _reiniciar_lecturas(self) -> None:
        self._gen += 1
        self._listados.clear()
        self._snippets.clear()
        self._errores_lectura.clear()
        self._plantillas = None
        self._formatos.clear()
        self._en_curso.clear()
        self._fallidas.clear()
        self._necesidades_hechas.clear()
        self._ultimo_clon = None

    def _reconstruir(self) -> CatalogoServidor | None:
        """Vuelca lo leído en ``Inventario.catalogo`` (los permisos son los del descubrimiento)."""
        inv = self._inv
        if inv is None:
            return None
        catalogo = CatalogoServidor(
            permisos=self._permisos,
            listados=tuple(ls for clave in sorted(self._listados) for ls in self._listados[clave]),
            plantillas=self._plantillas,
            formatos=dict(self._formatos),
            leido_en=self._reloj.ahora(),
            pools=self._pools,
            politica_etiquetas=self._politica_etiquetas,
            politica_etiquetas_fallida=self._politica_etiquetas_fallida,
            snippets=tuple(self._snippets[k] for k in sorted(self._snippets)),
            firewall=self._firewall,
            hardware=self._hardware,
        )
        inv.catalogo = catalogo
        return catalogo

    def _publicar(self) -> None:
        """Catálogo nuevo: se actualiza el inventario, las capacidades y el selector."""
        catalogo = self._reconstruir()
        self._recalcular_capacidades(self._nodo_caps)
        self._entregar()
        if self._plantillas is not None:
            self.plantillas_cargadas.emit(self._plantillas)
        self.catalogo_cargado.emit(catalogo)
        self._elegir_pendiente()

    # ------------------------------------------------------------------------------------
    # Enlace con el selector
    # ------------------------------------------------------------------------------------

    def enlazar(self, selector: SelectorOrigen, nodo_de: Callable[[], str]) -> None:
        """Conecta el selector con el controlador (``nodo_de`` da el nodo efectivo)."""
        self._selector = selector
        self._nodo_de = nodo_de
        selector.pedir_catalogo.connect(self._al_pedir_catalogo)
        selector.pedir_subida.connect(self._al_pedir_subida)
        selector.pedir_descarga.connect(self._al_pedir_descarga)
        selector.origen_cambiado.connect(self._al_cambiar_origen)
        self.capacidades_cambiadas.connect(selector.establecer_capacidades)
        # Sin URL fija verificada de virtio-win esa vía no se ofrece (DT-O10, LAB-M4-07).
        selector.establecer_virtio_descargable(bool(URL_VIRTIO_WIN))
        selector.establecer_modo(self._avanzado)

    def establecer_tema(self, tema: str) -> None:
        if self._selector is not None:
            self._selector.establecer_tema(tema)

    def establecer_modo(self, avanzado: bool) -> None:
        self._avanzado = avanzado

    def establecer_ocupado(self, ocupado: bool) -> None:
        """Con un lote o una simulación en marcha no se sube ni se descarga (V-O27)."""
        self._ocupado = ocupado

    def _al_pedir_catalogo(self, fuente: object) -> None:
        if not isinstance(fuente, FuenteCatalogo):
            return
        self._entregar()  # lo que ya hay, para que el diálogo no se quede en «Cargando…»
        if fuente == FuenteCatalogo.PLANTILLA:
            self.cargar_plantillas(forzar=True)
        elif fuente.contenido is not None:
            self.cargar_catalogo(self._nodo_de(), fuente.contenido, forzar=True)

    def _al_pedir_subida(self, peticion: object) -> None:
        if isinstance(peticion, PeticionFuente) and peticion.fuente.contenido is not None:
            self.abrir_subida(
                peticion.fuente.contenido, self._nodo_de(), peticion.padre, fuente=peticion.fuente
            )

    def _al_pedir_descarga(self, peticion: object) -> None:
        if isinstance(peticion, PeticionFuente) and peticion.fuente.contenido is not None:
            self.abrir_descarga(
                peticion.fuente.contenido, self._nodo_de(), peticion.padre, fuente=peticion.fuente
            )

    def _al_cambiar_origen(self, origen: object) -> None:
        """ISO o disco importado necesitan un storage para el disco: se pregunta una vez
        por servidor si hay varios candidatos (RF-O05, resolución C4)."""
        if origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO):
            QTimer.singleShot(0, self.asegurar_storage_mv)

    def _entregar(self) -> None:
        """Pasa al selector lo leído del nodo efectivo (volúmenes, errores y plantillas)."""
        selector, inv = self._selector, self._inv
        if selector is None or inv is None:
            return
        nodo = self._nodo_de()
        volumenes = [
            v
            for (n, _c), ls in self._listados.items()
            if n == nodo
            for lst in ls
            for v in lst.volumenes
        ]
        errores = [
            lst.error
            for (n, _c), ls in self._listados.items()
            if n == nodo
            for lst in ls
            if lst.error
        ]
        errores.extend(e for (n, _c), e in self._errores_lectura.items() if n == nodo)
        selector.establecer_catalogo(
            volumenes, self._plantillas, nodo=nodo, errores=errores, permisos=self._permisos
        )

    # ------------------------------------------------------------------------------------
    # Capacidades
    # ------------------------------------------------------------------------------------

    def capacidades(self, nodo: str | None) -> CapacidadesOrigen | None:
        """Capacidades de origen para la versión efectiva, el inventario y el nodo."""
        sesion, inv = self._sesion, self._inv
        if sesion is None or inv is None:
            return None
        return calcular_capacidades(sesion.capacidades, inv, nodo or None)

    def _recalcular_capacidades(self, nodo: str | None) -> None:
        self._nodo_caps = nodo
        nuevas = self.capacidades(nodo)
        if nuevas != self._caps or nuevas is None:
            self._caps = nuevas
            self.capacidades_cambiadas.emit(nuevas)

    # ------------------------------------------------------------------------------------
    # Catálogo (lecturas en trabajadores)
    # ------------------------------------------------------------------------------------

    def cargar_catalogo(self, nodo: str, contenido: Contenido, *, forzar: bool = False) -> None:
        """Lee los archivos ``iso`` o ``import`` del nodo (solo GET) y avisa al terminar."""
        sesion, inv = self._sesion, self._inv
        clave: _Clave = (nodo, contenido)
        if sesion is None or inv is None or not nodo or clave in self._en_curso:
            return
        if not forzar and clave in self._fallidas:
            return
        self._fallidas.discard(clave)
        self._en_curso.add(clave)
        gen = self._gen
        self._lanzador.lanzar(
            leer_listados,
            sesion,
            self._reloj,
            inv,
            nodo,
            contenido,
            al_terminar=lambda r: self._tras_listados(gen, clave, r),
            al_fallar=lambda e: self._fallo_lectura(gen, clave, e),
        )

    def _tras_listados(self, gen: int, clave: _Clave, listados: tuple[ListadoStorage, ...]) -> None:
        if gen != self._gen:
            return
        self._en_curso.discard(clave)
        self._errores_lectura.pop(clave, None)
        self._listados[clave] = tuple(listados)
        self._publicar()

    def cargar_plantillas(self, *, forzar: bool = False) -> None:
        """Lee las plantillas visibles (solo GET) y avisa al terminar."""
        sesion = self._sesion
        clave = "plantillas"
        if sesion is None or clave in self._en_curso or (not forzar and clave in self._fallidas):
            return
        self._fallidas.discard(clave)
        self._en_curso.add(clave)
        gen = self._gen
        self._lanzador.lanzar(
            leer_plantillas,
            sesion,
            self._reloj,
            al_terminar=lambda r: self._tras_plantillas(gen, r),
            al_fallar=lambda e: self._fallo_lectura(gen, clave, e),
        )

    def _tras_plantillas(self, gen: int, plantillas: tuple[Plantilla, ...]) -> None:
        if gen != self._gen:
            return
        self._en_curso.discard("plantillas")
        previas = {(p.nodo, p.vmid): p.detalle for p in self._plantillas or ()}
        self._plantillas = tuple(
            dataclasses.replace(p, detalle=previas.get((p.nodo, p.vmid)) or p.detalle)
            for p in plantillas
        )
        self._publicar()

    def _cargar_detalle(self, plantilla: Plantilla) -> None:
        sesion, inv = self._sesion, self._inv
        clave = ("detalle", plantilla.nodo, plantilla.vmid)
        if sesion is None or inv is None or clave in self._en_curso or clave in self._fallidas:
            return
        self._en_curso.add(clave)
        gen = self._gen
        self._lanzador.lanzar(
            leer_detalle_plantilla,
            sesion,
            self._reloj,
            inv,
            plantilla.nodo,
            plantilla.vmid,
            al_terminar=lambda r: self._tras_detalle(gen, plantilla, r),
            al_fallar=lambda e: self._fallo_lectura(gen, clave, e),
        )

    def _tras_detalle(
        self,
        gen: int,
        plantilla: Plantilla,
        resultado: tuple[DetallePlantilla | None, dict[str, frozenset[str]]],
    ) -> None:
        if gen != self._gen:
            return
        clave = ("detalle", plantilla.nodo, plantilla.vmid)
        self._en_curso.discard(clave)
        detalle, formatos = resultado
        if detalle is None:
            self._fallidas.add(clave)  # no se ve la configuración: no se insiste
        else:
            self._plantillas = tuple(
                dataclasses.replace(p, detalle=detalle)
                if (p.nodo, p.vmid) == (plantilla.nodo, plantilla.vmid)
                else p
                for p in self._plantillas or ()
            )
        self._formatos.update(formatos)
        self._publicar()

    def cargar_necesidades(self, definicion: DefinicionLote) -> None:
        """Lee el catálogo que piden las filas de un lote cargado o importado, para revisar sus
        desajustes con datos del servidor y no con un catálogo vacío (RF-O27)."""
        sesion, inv = self._sesion, self._inv
        if sesion is None or inv is None:
            return
        # Fase B: las opciones del lote (cloud-init, snippets) añaden los storages a listar.
        necesidades = necesidades_catalogo(filas_efectivas(definicion), definicion.opciones)
        if necesidades.vacias or necesidades in self._necesidades_hechas:
            return
        self._necesidades_hechas.add(necesidades)
        nodos = [n.nombre for n in inv.topologia.nodos if n.en_linea]
        gen = self._gen
        self._lanzador.lanzar(
            leer_catalogo_para,
            sesion,
            self._reloj,
            inv,
            necesidades,
            nodos,
            al_terminar=lambda c: self._tras_necesidades(gen, c),
            al_fallar=lambda e: self._fallo_lectura(gen, "necesidades", e),
        )

    def _tras_necesidades(self, gen: int, catalogo: CatalogoServidor) -> None:
        if gen != self._gen:
            return
        porclave: dict[_Clave, list[ListadoStorage]] = {}
        for listado in catalogo.listados:
            porclave.setdefault((listado.nodo, listado.contenido), []).append(listado)
        for clave, grupo in porclave.items():
            self._listados[clave] = tuple(grupo)
        if catalogo.plantillas is not None:
            previas = {(p.nodo, p.vmid): p.detalle for p in self._plantillas or ()}
            self._plantillas = tuple(
                dataclasses.replace(p, detalle=p.detalle or previas.get((p.nodo, p.vmid)))
                for p in catalogo.plantillas
            )
        self._formatos.update(catalogo.formatos)
        for ls in catalogo.snippets:
            self._snippets[(ls.nodo, ls.storage)] = ls
        # Fase A: la lectura con ``opciones=True`` trae pools y política recién leídos.
        self._pools = catalogo.pools
        self._politica_etiquetas = catalogo.politica_etiquetas
        self._politica_etiquetas_fallida = catalogo.politica_etiquetas_fallida
        # Fase C: ``leer_para`` conserva lo previo si ninguna fila usa C3.
        self._firewall = catalogo.firewall
        # Fase D: «Comprobar» pudo leer mapeos o CPU que el lote usa y aún no se habían leído.
        if catalogo.hardware is not None:
            self._hardware = _fusionar_hardware(self._hardware, catalogo.hardware)
        self._publicar()

    # ------------------------------------------------------------------------------------
    # Hardware del clúster (D3): mapeos y modelos de CPU, bajo demanda
    # ------------------------------------------------------------------------------------

    def cargar_mapeos(self) -> None:
        """Lee los mapeos PCI/USB (2 GET, una vez por conexión) al abrir la sección (RNF-D4)."""
        sesion, inv = self._sesion, self._inv
        clave = "mapeos"
        if sesion is None or inv is None or clave in self._en_curso:
            return
        previo = self._hardware
        if previo is not None and (previo.mapeos is not None or previo.error_mapeos is not None):
            self.hardware_leido.emit(previo)  # ya se leyeron: nada que pedir
            return
        self._en_curso.add(clave)
        gen = self._gen
        self._lanzador.lanzar(
            leer_hardware_cluster,
            sesion,
            self._reloj,
            inv,
            (),
            al_terminar=lambda r: self._tras_hardware(gen, clave, r),
            al_fallar=lambda e: self._fallo_hardware(gen, clave, e),
        )

    def cargar_cpus(self, nodos: Collection[str]) -> None:
        """Lee los modelos de CPU de los nodos que falten (≤ 1 GET por nodo y conexión) sin leer
        los mapeos (RNF-D4)."""
        sesion, inv = self._sesion, self._inv
        pendientes = tuple(sorted(set(nodos)))
        clave = ("cpus", pendientes)
        if sesion is None or inv is None or not pendientes or clave in self._en_curso:
            return
        self._en_curso.add(clave)
        gen = self._gen
        self._lanzador.lanzar(
            leer_cpus,
            sesion,
            inv,
            pendientes,
            al_terminar=lambda r: self._tras_hardware(gen, clave, r),
            al_fallar=lambda e: self._fallo_hardware(gen, clave, e),
        )

    def _tras_hardware(self, gen: int, clave: object, info: InfoHardwareCluster) -> None:
        if gen != self._gen:
            return
        self._en_curso.discard(clave)
        self._hardware = _fusionar_hardware(self._hardware, info)
        self._publicar()
        self.hardware_leido.emit(self._hardware)

    def _fallo_hardware(self, gen: int, clave: object, error: ErrorProxLaunch) -> None:
        if gen != self._gen:
            return
        self._fallo_lectura(gen, clave, error)
        self.hardware_leido.emit(self._hardware)  # la sección deja de esperar

    def _fallo_lectura(self, gen: int, clave: object, error: ErrorProxLaunch) -> None:
        if gen != self._gen:
            return
        self._en_curso.discard(clave)
        self._fallidas.add(clave)
        _log.warning("No se pudo leer el catálogo: %s", error.codigo)
        if isinstance(clave, tuple) and len(clave) == 2 and isinstance(clave[1], Contenido):
            self._errores_lectura[clave] = error
        self._entregar()
        if error.codigo == CodigoError.SESION_EXPIRADA:
            self.fallo.emit(error)
        else:
            self.mensaje.emit(texto_error(error))

    # ------------------------------------------------------------------------------------
    # Sincronización con el formulario
    # ------------------------------------------------------------------------------------

    def sincronizar(self, cfg: ConfiguracionVM) -> None:
        """Pide lo que el origen elegido necesita y deja el selector al día.

        Se llama en cada revalidación: es barato salvo cuando cambia el nodo o el origen.
        """
        if self._inv is None or self._sesion is None:
            return
        nodo = cfg.nodo or None
        if nodo != self._nodo_caps or self._caps is None:
            self._recalcular_capacidades(nodo)
            self._entregar()
        if cfg.origen == OrigenSO.ISO and cfg.nodo:
            self._necesita(cfg.nodo, Contenido.ISO)
        elif cfg.origen == OrigenSO.IMPORTAR_DISCO and cfg.nodo:
            self._necesita(cfg.nodo, Contenido.IMPORT)
        elif cfg.origen == OrigenSO.CLONAR_PLANTILLA:
            self._sincronizar_clon(cfg)
            if self._avanzado and cfg.nodo:  # los scripts solo se ofrecen en modo avanzado
                self.cargar_snippets(cfg.nodo)

    def _buscar_snippets(self, nodo: str, storage: str) -> ListadoSnippets | None:
        """Listado de un almacenamiento visto desde un nodo (uno compartido vale para todos)."""
        for (n, st), listado in self._snippets.items():
            if st == storage and (n == nodo or listado.compartido):
                return listado
        return None

    def cargar_snippets(self, nodo: str, *, forzar: bool = False) -> None:
        """Lee los snippets de los almacenamientos del nodo que aún no se han leído (solo GET).

        Un almacenamiento compartido ya leído en otro nodo no se vuelve a pedir. Un fallo de
        listado queda en el propio ``ListadoSnippets`` y el formulario pasa a entrada manual.
        """
        sesion, inv = self._sesion, self._inv
        clave = ("snippets", nodo)
        if sesion is None or inv is None or not nodo or clave in self._en_curso:
            return
        if not forzar and clave in self._fallidas:
            return
        storages = tuple(
            s.id for s in inv.storages_todos.get(nodo, ()) if s.activo and "snippets" in s.contenido
        )
        if forzar:
            for st in storages:
                self._snippets.pop((nodo, st), None)
        pendientes = tuple(st for st in storages if self._buscar_snippets(nodo, st) is None)
        if not pendientes:
            return
        self._fallidas.discard(clave)
        self._en_curso.add(clave)
        gen = self._gen
        self._lanzador.lanzar(
            leer_snippets_del_nodo,
            sesion,
            self._reloj,
            inv,
            nodo,
            pendientes,
            al_terminar=lambda r: self._tras_snippets(gen, clave, r),
            al_fallar=lambda e: self._fallo_lectura(gen, clave, e),
        )

    def _tras_snippets(
        self, gen: int, clave: object, listados: tuple[ListadoSnippets, ...]
    ) -> None:
        if gen != self._gen:
            return
        self._en_curso.discard(clave)
        for listado in listados:
            self._snippets[(listado.nodo, listado.storage)] = listado
        self._publicar()

    def info_cloudinit(self, cfg: ConfiguracionVM) -> InfoCloudInitPlantilla | None:
        """Lo que la plantilla elegida dice de cloud-init (``DetallePlantilla.cloudinit``).

        ``None`` mientras no se haya leído su configuración o si el origen no es un clon: el
        formulario lo trata como «desconocida» (V-B20 avisa «no se pudo comprobar»).
        """
        det = cfg.detalle_origen
        if cfg.origen != OrigenSO.CLONAR_PLANTILLA or not isinstance(det, DetalleClon):
            return None
        plantilla = self._plantilla_elegida(det.plantilla)
        if plantilla is None or plantilla.detalle is None:
            return None
        return plantilla.detalle.cloudinit

    def _necesita(self, nodo: str, contenido: Contenido) -> None:
        clave: _Clave = (nodo, contenido)
        if clave not in self._listados:
            self.cargar_catalogo(nodo, contenido)

    def _plantilla_elegida(self, ref: RefPlantilla) -> Plantilla | None:
        for p in self._plantillas or ():
            if ref.vmid is not None and p.vmid == ref.vmid:
                return p
        if ref.vmid is None and ref.nombre:
            por_nombre = [p for p in self._plantillas or () if p.nombre == ref.nombre]
            if len(por_nombre) == 1:
                return por_nombre[0]
        return None

    def _sincronizar_clon(self, cfg: ConfiguracionVM) -> None:
        inv, selector = self._inv, self._selector
        det = cfg.detalle_origen
        if inv is None or not isinstance(det, DetalleClon):
            return
        if self._plantillas is None:
            self.cargar_plantillas()
            return
        plantilla = self._plantilla_elegida(det.plantilla)
        if plantilla is not None and plantilla.detalle is None:
            self._cargar_detalle(plantilla)
        detalle = None if plantilla is None else plantilla.detalle
        modo = None
        if plantilla is not None and detalle is not None:
            modo, _ = modo_efectivo(det, detalle, inv, plantilla.nodo)
        storages = tuple(s.id for s in candidatos(inv, Contenido.IMAGENES, cfg.nodo))
        estado = (None if plantilla is None else plantilla.vmid, detalle, modo, storages)
        if selector is None or estado == self._ultimo_clon:
            return
        self._ultimo_clon = estado
        selector.establecer_detalle_plantilla(detalle)
        selector.establecer_modo_efectivo(modo)
        selector.establecer_storages_destino(storages)

    # ------------------------------------------------------------------------------------
    # Resolución del origen y reglas de interfaz
    # ------------------------------------------------------------------------------------

    def resolver(self, cfg: ConfiguracionVM) -> tuple[ConfiguracionVM, list[Problema]]:
        """Configuración con el origen resuelto en su nodo (volids, drivers, plantilla, modo)
        y los problemas de la resolución más V-O26 y V-O27 (puro, sin E/S)."""
        inv = self._inv
        problemas: list[Problema] = []
        if inv is not None and cfg.origen != OrigenSO.DISCO_VACIO:
            cfg, problemas = resolver_origen(cfg, inv, cfg.nodo)
        problemas.extend(self._reglas_de_interfaz(cfg))
        return cfg, problemas

    def _reglas_de_interfaz(self, cfg: ConfiguracionVM) -> list[Problema]:
        """V-O26 (storage recordado que ya no sirve) y V-O27 (transferencia en curso)."""
        reglas: list[Problema] = []
        inv, perfil = self._inv, self.perfil
        if inv is not None and perfil is not None and cfg.nodo:
            decision = decidir_storage(
                inv, Contenido.IMAGENES, cfg.nodo, recordado_de(perfil, Contenido.IMAGENES)
            )
            if decision.tipo == TipoDecision.RECORDADO_NO_DISPONIBLE:
                necesita = cfg.origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO)
                reglas.append(
                    Problema(
                        "discos",
                        "V-O26",
                        Severidad.ERROR if necesita else Severidad.AVISO,
                        {"storage": decision.recordado or "", "contenido": Contenido.IMAGENES},
                    )
                )
        if self.transferencia_activa:
            reglas.append(Problema("origen", "V-O27", Severidad.ERROR, {}))
        return reglas

    # ------------------------------------------------------------------------------------
    # Storages recordados (RF-O05, RF-O06)
    # ------------------------------------------------------------------------------------

    def recordado(self, contenido: Contenido) -> str | None:
        perfil = self.perfil
        return None if perfil is None else recordado_de(perfil, contenido)

    def hay_recordado_no_disponible(self, nodo: str) -> bool:
        """Algún storage recordado ya no sirve en ese nodo (E-O04)."""
        inv = self._inv
        if inv is None or not nodo:
            return False
        return any(
            decidir_storage(inv, c, nodo, self.recordado(c)).tipo
            == TipoDecision.RECORDADO_NO_DISPONIBLE
            for c in Contenido
        )

    def storage_para(self, contenido: Contenido, nodo: str, parent: QWidget) -> str | None:
        """Almacenamiento donde guardar ``contenido`` en el servidor activo.

        Un recordado vigente o un único candidato se usan sin preguntar; con varios candidatos
        se pregunta una vez y se recuerda; si el recordado ya no sirve se avisa (E-O04) y se
        ofrece «Elegir otro» o «Dejar de recordar», nunca se sustituye en silencio (INV-O11).
        ``None`` si no hay ninguno o el usuario cancela.
        """
        inv = self._inv
        if inv is None:
            return None
        recordado = self.recordado(contenido)
        for _vuelta in range(2):
            decision = decidir_storage(inv, contenido, nodo, recordado)
            if decision.tipo in (TipoDecision.UNICO, TipoDecision.RECORDADO):
                return decision.storage
            if decision.tipo == TipoDecision.SIN_CANDIDATOS:
                return None
            no_disponible = (
                decision.recordado
                if decision.tipo == TipoDecision.RECORDADO_NO_DISPONIBLE
                else None
            )
            dialogo = DialogoElegirStorage(
                contenido,
                candidatos(inv, contenido, nodo),
                parent,
                no_disponible=no_disponible,
            )
            aceptado = self._ejecutar(dialogo)
            eleccion = dialogo.eleccion
            dialogo.deleteLater()
            if not aceptado or eleccion is None:
                return None
            if eleccion.dejar_de_recordar:
                self.recordar(contenido, None)
                recordado = None
                continue  # con el recordado olvidado se vuelve a decidir
            if eleccion.recordar:
                self.recordar(contenido, eleccion.storage)
            return eleccion.storage
        return None

    @staticmethod
    def _ejecutar(dialogo: QDialog) -> bool:
        """Muestra el diálogo y espera la respuesta (se puede sustituir en pruebas)."""
        return dialogo.exec() == QDialog.DialogCode.Accepted

    def recordar(self, contenido: Contenido, storage: str | None) -> None:
        """Recuerda (o deja de recordar, con ``None``) el storage de ``contenido`` en el perfil
        de conexión del servidor activo. La escritura va en un trabajador."""
        sesion = self._sesion
        if sesion is None:
            return
        nuevo = con_recordado(sesion.perfil, contenido, storage)
        sesion.perfil = nuevo
        self._lanzador.lanzar(
            guardar_storage_recordado,
            self._repositorio,
            nuevo.id,
            contenido,
            storage,
            al_fallar=lambda e: self.mensaje.emit(texto_error(e)),
        )

    def asegurar_storage_mv(self, parent: QWidget | None = None) -> None:
        """Si hay varios storages para los discos y ninguno recordado, pregunta una vez cuál usar
        siempre en este servidor (resolución C4: preselecciona el de más espacio libre)."""
        inv, selector = self._inv, self._selector
        nodo = self._nodo_de()
        if inv is None or not nodo or self._preguntando:
            return
        decision = decidir_storage(
            inv, Contenido.IMAGENES, nodo, self.recordado(Contenido.IMAGENES)
        )
        if decision.tipo != TipoDecision.PREGUNTAR:
            return
        padre = parent or (None if selector is None else selector.window())
        if padre is None:
            return
        self._preguntando = True
        try:
            elegido = self.storage_para(Contenido.IMAGENES, nodo, padre)
        finally:
            self._preguntando = False
        if elegido is not None:
            self.storage_mv_elegido.emit(elegido)

    def revisar_recordados(self, parent: QWidget) -> None:
        """«Elegir otro…» / «Dejar de recordar» para cada storage recordado que ya no sirve."""
        nodo = self._nodo_de()
        inv = self._inv
        if inv is None or not nodo:
            return
        for contenido in Contenido:
            decision = decidir_storage(inv, contenido, nodo, self.recordado(contenido))
            if decision.tipo != TipoDecision.RECORDADO_NO_DISPONIBLE:
                continue
            elegido = self.storage_para(contenido, nodo, parent)
            if elegido is not None and contenido == Contenido.IMAGENES:
                self.storage_mv_elegido.emit(elegido)

    # ------------------------------------------------------------------------------------
    # Transferencias (RF-O09 a RF-O12, RF-O25)
    # ------------------------------------------------------------------------------------

    def _puede_transferir(self) -> bool:
        if self._inv is None or self._servicio_transferencias is None:
            return False
        if self.transferencia_activa or self._ocupado:
            self.mensaje.emit(
                QCoreApplication.translate(
                    "ControladorOrigen",
                    "Hay una transferencia, un lote o una simulación en curso. Espera a que "
                    "termine o cancélala.",
                )
            )
            return False
        return True

    def abrir_subida(
        self,
        contenido: Contenido,
        nodo: str,
        parent: QWidget,
        *,
        fuente: FuenteCatalogo | None = None,
    ) -> None:
        """Abre «Subir desde mi equipo…» (una sola transferencia a la vez)."""
        if self._puede_transferir():
            self._abrir(DialogoSubida(self, contenido, nodo, parent), contenido, nodo, fuente)

    def abrir_descarga(
        self,
        contenido: Contenido,
        nodo: str,
        parent: QWidget,
        *,
        fuente: FuenteCatalogo | None = None,
    ) -> None:
        """Abre «Descargar en el servidor…»; la dirección de virtio-win va fija y verificada."""
        if not self._puede_transferir():
            return
        if fuente == FuenteCatalogo.DRIVERS and URL_VIRTIO_WIN:
            dialogo = DialogoDescarga(
                self,
                contenido,
                nodo,
                parent,
                url_inicial=URL_VIRTIO_WIN,
                checksum_inicial=SHA256_VIRTIO_WIN,
                url_fija=True,
            )
        else:
            dialogo = DialogoDescarga(self, contenido, nodo, parent)
        self._abrir(dialogo, contenido, nodo, fuente)

    def _abrir(
        self,
        dialogo: DialogoSubida | DialogoDescarga,
        contenido: Contenido,
        nodo: str,
        fuente: FuenteCatalogo | None,
    ) -> None:
        self._dialogo = dialogo
        dialogo.terminada.connect(lambda r: self._al_terminar(r, contenido, nodo, fuente))
        dialogo.usar_existente.connect(
            lambda v: self._seleccionar_tras_leer(contenido, nodo, fuente, v)
        )
        dialogo.finished.connect(lambda _r: self._al_cerrar(dialogo))
        dialogo.open()

    def _al_terminar(
        self,
        resultado: object,
        contenido: Contenido,
        nodo: str,
        fuente: FuenteCatalogo | None,
    ) -> None:
        if not isinstance(resultado, ResultadoTransferencia):
            return
        # Se relee el catálogo siempre: es la verdad de lo que quedó en el servidor (CA-O12.2).
        volid = resultado.volid if resultado.estado == EstadoTransferencia.TERMINADA else None
        if volid:
            self._seleccionar_tras_leer(contenido, nodo, fuente, volid)
        else:
            self.cargar_catalogo(nodo, contenido, forzar=True)
        self.transferencia_terminada.emit(resultado)

    def _seleccionar_tras_leer(
        self, contenido: Contenido, nodo: str, fuente: FuenteCatalogo | None, volid: str
    ) -> None:
        """Deja elegido ``volid`` cuando el catálogo recargado ya lo traiga (CA-O09.6)."""
        if fuente is None:
            fuente = FuenteCatalogo.IMAGEN if contenido == Contenido.IMPORT else FuenteCatalogo.ISO
        self._pendiente = (fuente, volid)
        self.cargar_catalogo(nodo, contenido, forzar=True)

    def _elegir_pendiente(self) -> None:
        selector, pendiente = self._selector, self._pendiente
        if selector is None or pendiente is None or pendiente[0] is None:
            return
        if selector.seleccionar_volid(pendiente[0], pendiente[1]):
            self._pendiente = None

    def _al_cerrar(self, dialogo: DialogoSubida | DialogoDescarga) -> None:
        if self._dialogo is dialogo:
            self._dialogo = None
        dialogo.deleteLater()

    def cancelar_transferencia(self) -> None:
        """Pide detener la transferencia en curso (la descarga solo «deja de esperar»)."""
        dialogo = self._dialogo
        if dialogo is not None and dialogo.transferencia_en_curso:
            dialogo.cancelar_transferencia()

    def esperar_fin_de_transferencia(self, limite_s: float = ESPERA_CANCELACION_S) -> bool:
        """Atiende eventos hasta que la transferencia cancelada termine o venza el límite
        (cierre de la aplicación, CA-O12.4). ``True`` si ya no hay ninguna activa."""
        fin = time.monotonic() + limite_s
        while self.transferencia_activa and time.monotonic() < fin:
            QCoreApplication.processEvents()
            QThread.msleep(20)
        return not self.transferencia_activa


def _fusionar_hardware(
    previo: InfoHardwareCluster | None, nuevo: InfoHardwareCluster
) -> InfoHardwareCluster:
    """Une dos lecturas del hardware del clúster que pudieron hacerse a la vez (mapeos y CPU):
    lo que una no leyó lo conserva de la otra, para no perder lo ya leído (RNF-D4)."""
    if previo is None:
        return nuevo
    leyo_mapeos = nuevo.mapeos is not None or nuevo.error_mapeos is not None
    cpus = {**previo.cpus, **nuevo.cpus}
    errores_cpu = {n: e for n, e in {**previo.errores_cpu, **nuevo.errores_cpu}.items()}
    for nodo in cpus:
        errores_cpu.pop(nodo, None)
    # Un mismo id puede existir como PCI y como USB: el tipo forma parte de la clave.
    vistas = {(c.tipo, c.mapeo, c.nodo) for c in nuevo.comprobaciones}
    comprobaciones = nuevo.comprobaciones + tuple(
        c for c in previo.comprobaciones if (c.tipo, c.mapeo, c.nodo) not in vistas
    )
    # Un par ya comprobado con éxito deja de figurar como fallido (QA-10).
    comprobados = {(c.tipo.value, c.mapeo, c.nodo) for c in comprobaciones}
    errores_comprobacion = tuple(
        e
        for e in dict.fromkeys(previo.errores_comprobacion + nuevo.errores_comprobacion)
        if e not in comprobados
    )
    return dataclasses.replace(
        nuevo,
        mapeos=nuevo.mapeos if leyo_mapeos else previo.mapeos,
        error_mapeos=nuevo.error_mapeos if leyo_mapeos else previo.error_mapeos,
        comprobaciones=comprobaciones,
        errores_comprobacion=errores_comprobacion,
        cpus=cpus,
        errores_cpu=errores_cpu,
    )
