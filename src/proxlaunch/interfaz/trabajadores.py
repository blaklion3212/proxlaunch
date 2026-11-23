"""Trabajos en segundo plano: ``Trabajador(QRunnable)`` con señales (RNF-01).

Toda llamada de red del núcleo se ejecuta aquí, en el ``QThreadPool`` global. El
resultado vuelve al hilo principal por señales en cola; solo ese hilo toca widgets.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import logging
import secrets
import threading
import time
from collections.abc import Callable, Collection, Iterable, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

from proxlaunch.nucleo.agente.espera import EsperaIp
from proxlaunch.nucleo.agente.exportacion import guardar_ips_csv
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.cloudinit.modelos import ModoTarjeta
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.csv_importacion.plantilla import escribir_plantilla
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall import lectura as lectura_firewall
from proxlaunch.nucleo.firewall.modelos import LecturaGrupos, ReglaFirewall
from proxlaunch.nucleo.inventario.exportacion import exportar_csv
from proxlaunch.nucleo.inventario.modelos import DetalleLote, IpInventario, ListaLotes, LoteServidor
from proxlaunch.nucleo.inventario.servicio import ServicioInventario
from proxlaunch.nucleo.lote.ajustes import reintentar_ajustes
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    CandidatoRollback,
    DefinicionLote,
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
    InformeLote,
    MotivoReparto,
    Plan,
    Problema,
    ResultadoRollback,
    ResultadoSimulacion,
    Severidad,
)
from proxlaunch.nucleo.lote.motor import ControlLote, MotorLote, enlazar_espera
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.lote.presupuesto import evaluar_espacio, uso_por_clave
from proxlaunch.nucleo.lote.reconciliacion import config_en_creacion, tiene_etiqueta_del_lote
from proxlaunch.nucleo.lote.rollback import InspeccionRollback, ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote, leer_archivo_lote
from proxlaunch.nucleo.lotes_guardados.modelos import ArchivoLote, LoteGuardado
from proxlaunch.nucleo.modelos.catalogo import (
    CatalogoServidor,
    Contenido,
    DetallePlantilla,
    ListadoStorage,
    PermisosEfectivos,
    Plantilla,
)
from proxlaunch.nucleo.modelos.conexion import PerfilConexion
from proxlaunch.nucleo.modelos.inventario import Bridge, Inventario, Storage
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.opciones.modelos import ContextoNotas
from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo
from proxlaunch.nucleo.origen.storages import con_recordado
from proxlaunch.nucleo.perfiles_maquina.formato import (
    ArchivoPerfiles,
    exportar_perfiles,
    leer_archivo_perfiles,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import PerfilMaquina
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.red.redes_nodo import RedesNodo
from proxlaunch.nucleo.registro import enmascarar
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.servicios.catalogo import ServicioCatalogo
from proxlaunch.nucleo.servicios.conexion import Sesion, permisos_faltantes
from proxlaunch.nucleo.servicios.creacion import (
    AVISO_ENCENDIDO_FALLIDO,
    AVISO_ENCENDIDO_OMITIDO,
    ServicioCreacion,
)
from proxlaunch.nucleo.servicios.descubrimiento import (
    descubrir,
    descubrir_nodo_c,
)
from proxlaunch.nucleo.validacion import Severidad as SeveridadM1
from proxlaunch.nucleo.validacion import validar_vm

_log = logging.getLogger("proxlaunch.interfaz.trabajadores")


class SenalesTrabajador(QObject):
    """Señales de un trabajador (un ``QRunnable`` no puede tenerlas)."""

    terminado = Signal(object)  # resultado de la función
    fallo = Signal(object)  # ErrorProxLaunch
    etapa = Signal(object)  # Etapa (solo trabajos con contexto)
    upid = Signal(str)  # UPID en cuanto se envía la petición de creación


class Trabajador(QRunnable):
    """Ejecuta una función del núcleo fuera del hilo de la interfaz.

    Si ``con_contexto`` es verdadero, la función recibe además los argumentos con nombre
    ``al_cambiar_etapa`` (callable que emite ``etapa``) y ``cancelado``
    (``threading.Event``), tal como pide ``ServicioCreacion.crear``.
    """

    def __init__(
        self,
        funcion: Callable[..., Any],
        *args: Any,
        con_contexto: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._funcion = funcion
        self._args = args
        self._kwargs = kwargs
        self._con_contexto = con_contexto
        self.senales = SenalesTrabajador()
        self.cancelado = threading.Event()
        # Señales a las que el Lanzador conectó algo: solo esas se desconectan al terminar
        # (desconectar una sin receptores emite un RuntimeWarning de PySide6).
        self.conectadas: list[Any] = []
        # El Lanzador conserva la referencia hasta que termine; así no se destruye antes.
        self.setAutoDelete(False)

    def cancelar(self) -> None:
        """Pide al trabajo que deje de esperar (no deshace nada)."""
        self.cancelado.set()

    @staticmethod
    def _emitir(senal: Any, valor: Any) -> None:
        """Emite la señal sin fallar si el objeto Qt ya se destruyó (cierre de la ventana)."""
        try:
            senal.emit(valor)
        except RuntimeError:
            _log.debug("Señal descartada: el receptor ya no existe")

    def _emitir_etapa(self, etapa: Any) -> None:
        self._emitir(self.senales.etapa, etapa)

    def _emitir_upid(self, upid: str) -> None:
        self._emitir(self.senales.upid, upid)

    def run(self) -> None:
        try:
            if self._con_contexto:
                resultado = self._funcion(
                    *self._args,
                    al_cambiar_etapa=self._emitir_etapa,
                    al_enviar=self._emitir_upid,
                    cancelado=self.cancelado,
                    **self._kwargs,
                )
            else:
                resultado = self._funcion(*self._args, **self._kwargs)
        except ErrorProxLaunch as error:
            self._emitir(self.senales.fallo, error)
        except Exception as exc:  # error inesperado: nunca debe romper el hilo
            _log.exception("Error inesperado en un trabajo en segundo plano")
            self._emitir(
                self.senales.fallo,
                ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, enmascarar(str(exc))),
            )
        else:
            self._emitir(self.senales.terminado, resultado)


# Hilos de fondo que cancelan una ``EsperaIp``: ``cancelar`` bloquea hasta que termina la petición
# en vuelo (hasta el tope HTTP), así que nunca se llama desde el hilo de la interfaz.
_cancelaciones: list[threading.Thread] = []
_cerrojo_cancelaciones = threading.Lock()


def cancelar_espera_en_fondo(
    espera: EsperaIp, vmids: Collection[int] | None = None
) -> threading.Thread:
    """Lanza ``espera.cancelar(vmids)`` en un hilo de fondo (fire and forget) y lo devuelve.

    Se usa desde el hilo de la interfaz («Dejar de esperar la IP», desconectar, cerrar). Un hilo
    propio (y no el grupo de la espera) evita que la cancelación espere turno detrás de las
    esperas que debe cortar.
    """

    def _cancelar() -> None:
        try:
            espera.cancelar(vmids)
        except Exception:  # nunca debe romper el hilo
            _log.exception("Error al cancelar la espera de IP")

    hilo = threading.Thread(target=_cancelar, name="cancelar-espera-ip", daemon=True)
    with _cerrojo_cancelaciones:
        _cancelaciones[:] = [h for h in _cancelaciones if h.is_alive()]
        _cancelaciones.append(hilo)
    hilo.start()
    return hilo


def esperar_cancelaciones(milisegundos: int) -> bool:
    """Espera (con tope) a los hilos de cancelación en curso; ``True`` si ya no queda ninguno."""
    limite = time.monotonic() + milisegundos / 1000
    with _cerrojo_cancelaciones:
        hilos = list(_cancelaciones)
    for hilo in hilos:
        hilo.join(max(0.0, limite - time.monotonic()))
    return not any(h.is_alive() for h in hilos)


class _TrabajadorEspera(Trabajador):
    """Trabajador de la espera de IP (B3): ``ejecutar()`` en su propio hilo.

    Cancelarlo («Dejar de esperar», cierre de la aplicación) cancela también la espera: así
    ``EsperaIp.ejecutar`` vuelve enseguida y no se hacen más peticiones.
    """

    def __init__(self, espera: EsperaIp) -> None:
        super().__init__(espera.ejecutar)
        self._espera = espera

    def cancelar(self) -> None:
        super().cancelar()
        cancelar_espera_en_fondo(self._espera)


class Lanzador(QObject):
    """Lanza trabajadores en el ``QThreadPool`` global y gestiona su ciclo de vida."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._activos: set[Trabajador] = set()
        # La espera de IP vive en un grupo propio: nunca compite con el motor del lote por un
        # hilo del grupo global (con un solo procesador la espera no arrancaría hasta que el
        # motor terminase y el plazo de las máquinas ya habría vencido).
        self._pool_espera = QThreadPool(self)
        self._pool_espera.setMaxThreadCount(4)

    @property
    def hay_activos(self) -> bool:
        return bool(self._activos)

    def lanzar(
        self,
        funcion: Callable[..., Any],
        *args: Any,
        al_terminar: Callable[[Any], None] | None = None,
        al_fallar: Callable[[ErrorProxLaunch], None] | None = None,
        al_etapa: Callable[[Any], None] | None = None,
        al_upid: Callable[[str], None] | None = None,
        con_contexto: bool = False,
        **kwargs: Any,
    ) -> Trabajador:
        """Lanza ``funcion`` en segundo plano y conecta los resultados en cola."""
        trabajador = Trabajador(funcion, *args, con_contexto=con_contexto, **kwargs)
        self._arrancar(
            trabajador,
            QThreadPool.globalInstance(),
            al_terminar=al_terminar,
            al_fallar=al_fallar,
            al_etapa=al_etapa,
            al_upid=al_upid,
        )
        return trabajador

    def lanzar_espera(
        self,
        espera: EsperaIp,
        *,
        al_terminar: Callable[[Any], None] | None = None,
        al_fallar: Callable[[ErrorProxLaunch], None] | None = None,
    ) -> Trabajador:
        """Lanza ``espera.ejecutar()`` en su propio hilo (B3). El resultado de cada MV llega por
        el ``al_resultado`` de la espera; ``al_terminar`` recibe el diccionario final."""
        trabajador = _TrabajadorEspera(espera)
        self._arrancar(
            trabajador,
            self._pool_espera,
            al_terminar=al_terminar,
            al_fallar=al_fallar,
        )
        return trabajador

    def _arrancar(
        self,
        trabajador: Trabajador,
        pool: QThreadPool,
        *,
        al_terminar: Callable[[Any], None] | None = None,
        al_fallar: Callable[[ErrorProxLaunch], None] | None = None,
        al_etapa: Callable[[Any], None] | None = None,
        al_upid: Callable[[str], None] | None = None,
    ) -> None:
        cola = Qt.ConnectionType.QueuedConnection
        senales = trabajador.senales
        if al_upid is not None:
            senales.upid.connect(al_upid, cola)
            trabajador.conectadas.append(senales.upid)
        if al_etapa is not None:
            senales.etapa.connect(al_etapa, cola)
            trabajador.conectadas.append(senales.etapa)
        senales.terminado.connect(lambda r: self._finalizar(trabajador, al_terminar, r), cola)
        senales.fallo.connect(lambda e: self._finalizar_fallo(trabajador, al_fallar, e), cola)
        trabajador.conectadas.extend((senales.terminado, senales.fallo))
        self._activos.add(trabajador)
        pool.start(trabajador)

    @staticmethod
    def _desconectar(trabajador: Trabajador) -> None:
        """Rompe el ciclo trabajador -> señales -> lambda -> trabajador."""
        for senal in trabajador.conectadas:
            with contextlib.suppress(RuntimeError, TypeError):
                senal.disconnect()
        trabajador.conectadas.clear()

    def _finalizar(
        self, trabajador: Trabajador, destino: Callable[[Any], None] | None, resultado: Any
    ) -> None:
        self._activos.discard(trabajador)
        self._desconectar(trabajador)
        if destino is not None:
            destino(resultado)

    def _finalizar_fallo(
        self,
        trabajador: Trabajador,
        destino: Callable[[ErrorProxLaunch], None] | None,
        error: ErrorProxLaunch,
    ) -> None:
        self._activos.discard(trabajador)
        self._desconectar(trabajador)
        if destino is not None:
            destino(error)

    def cancelar_todos(self) -> None:
        """Pide la cancelación de todos los trabajos activos."""
        for t in list(self._activos):
            t.cancelar()

    def esperar(self, milisegundos: int = 3000) -> bool:
        """Espera a que los grupos terminen (al cerrar la aplicación)."""
        # Lo que aún no arrancó en el grupo de la espera no tiene sentido al cerrar (QA-B6).
        self._pool_espera.clear()
        global_ok = QThreadPool.globalInstance().waitForDone(milisegundos)
        espera_ok = self._pool_espera.waitForDone(milisegundos)
        cancelaciones_ok = esperar_cancelaciones(milisegundos)
        return bool(global_ok and espera_ok and cancelaciones_ok)


# --- Funciones de trabajo (se ejecutan en el pool, sin tocar widgets) -----------------


def descubrir_y_comprobar_permisos(sesion: Sesion) -> tuple[Inventario, list[str] | None]:
    """Descubre el inventario y comprueba los permisos tras conectar (RF-11, RF-12).

    Los permisos efectivos ya los leyó ``descubrir`` (``inv.catalogo.permisos``): se reutilizan
    para no repetir ``GET /access/permissions``. Si esa lectura falló, quedan desconocidos y no
    se vuelve a pedir (CA-12.3); un inventario sin catálogo conserva la consulta de siempre.
    """
    inventario = descubrir(sesion)
    catalogo = inventario.catalogo
    if catalogo is None:
        return inventario, permisos_faltantes(sesion)
    if catalogo.permisos is None:
        return inventario, None
    return inventario, permisos_faltantes(sesion, permisos=catalogo.permisos.rutas)


def recargar_nodo(
    sesion: Sesion, nodo: str
) -> tuple[str, list[Storage], list[Bridge], list[Storage], RedesNodo]:
    """Relee storages, bridges y VNets de un nodo (CA-11.7, CA-C2.1.3).

    Devuelve ``(nodo, con_images, bridges, todos, redes)``: ``todos`` (de la misma respuesta, sin
    GET extra) mantiene al día ``Inventario.storages_todos`` para el origen del SO y ``redes``
    trae las VNets de SDN (la lectura es tolerante: un fallo queda en ``RedesNodo.error``).
    """
    con_images, todos, bridges, redes = descubrir_nodo_c(sesion, nodo)
    return nodo, con_images, bridges, todos, redes


def reintentar_nodos(
    sesion: Sesion, nodos: list[str]
) -> tuple[
    dict[str, tuple[list[Storage], list[Bridge], list[Storage], RedesNodo]],
    dict[str, ErrorProxLaunch],
]:
    """Reintenta el descubrimiento de los nodos que fallaron (CA-11.8).

    Cada nodo recuperado trae ``(con_images, bridges, todos, redes)``.
    """
    recuperados: dict[str, tuple[list[Storage], list[Bridge], list[Storage], RedesNodo]] = {}
    fallidos: dict[str, ErrorProxLaunch] = {}
    for nodo in nodos:
        try:
            con_images, todos, bridges, redes = descubrir_nodo_c(sesion, nodo)
            recuperados[nodo] = (con_images, bridges, todos, redes)
        except ErrorProxLaunch as e:
            fallidos[nodo] = e
    return recuperados, fallidos


# --- Fase C: lecturas del firewall (solo GET) ---------------------------------------------------


def leer_grupos_firewall(sesion: Sesion) -> LecturaGrupos:
    """Grupos de seguridad del clúster para el selector del formulario (RF-C3.2)."""
    return lectura_firewall.leer_grupos(sesion.cliente)


def leer_reglas_grupo(
    sesion: Sesion, grupo: str
) -> tuple[str, tuple[ReglaFirewall, ...] | None, ErrorProxLaunch | None]:
    """Reglas de un grupo para «Ver reglas» (RF-C3.11); solo lectura."""
    reglas, error = lectura_firewall.leer_reglas_grupo(sesion.cliente, grupo)
    return grupo, reglas, error


# --- Fase C: inventario de lotes del servidor (C1) ------------------------------------------------
# Todo es lectura salvo ``deshacer_inventario`` (el Deshacer confirmado, con doble control).


def leer_lotes_servidor(sesion: Sesion, reloj: Reloj) -> ListaLotes:
    """Una sola petición (``/cluster/resources``) agrupada por lote (RF-C1.2)."""
    return ServicioInventario(sesion, reloj).listar()


def detallar_lote_servidor(
    sesion: Sesion,
    reloj: Reloj,
    lote: LoteServidor,
    permisos: PermisosEfectivos | None,
    *,
    al_cambiar_etapa: Callable[[Any], None],
    al_enviar: Callable[[str], None],
    cancelado: threading.Event,
) -> DetalleLote:
    """Lee la config de cada máquina del lote (≤ 4 a la vez); con ``cancelado`` corta (RF-C1.12)."""
    del al_cambiar_etapa, al_enviar  # el trabajador con contexto los pasa siempre
    return ServicioInventario(sesion, reloj).detallar(lote, cancelado, permisos)


def obtener_ips_inventario(
    sesion: Sesion,
    reloj: Reloj,
    detalle: DetalleLote,
    vmids: Collection[int],
    permisos: PermisosEfectivos | None,
    *,
    al_cambiar_etapa: Callable[[Any], None],
    al_enviar: Callable[[str], None],
    cancelado: threading.Event,
) -> dict[int, IpInventario]:
    """Una sonda del agente por máquina, sin esperar (RF-C1.7); solo lectura."""
    del al_cambiar_etapa, al_enviar
    return ServicioInventario(sesion, reloj).obtener_ips(detalle, vmids, cancelado, permisos)


def exportar_inventario_csv(
    sesion: Sesion,
    reloj: Reloj,
    ruta: Path,
    detalles: Sequence[DetalleLote],
    pendientes: Sequence[LoteServidor],
    ips_previas: dict[int, IpInventario],
    con_ip: bool,
    permisos: PermisosEfectivos | None,
    *,
    al_cambiar_etapa: Callable[[Any], None],
    al_enviar: Callable[[str], None],
    cancelado: threading.Event,
) -> tuple[Path | None, list[DetalleLote], dict[int, IpInventario]]:
    """Lee lo que falte (lotes sin detalle, IP) y escribe el CSV de exportación (RF-C1.6).

    Solo hace GET y escribe el archivo local ``ruta``. Devuelve la ruta (``None`` si se canceló
    antes de escribir), los detalles y las IP leídas, para que el diálogo los conserve.
    """
    del al_cambiar_etapa, al_enviar
    servicio = ServicioInventario(sesion, reloj)
    todos = list(detalles)
    for lote in pendientes:
        if cancelado.is_set():
            break
        todos.append(servicio.detallar(lote, cancelado, permisos))
    ips = dict(ips_previas)
    if con_ip:
        for detalle in todos:
            faltan = [m.recurso.vmid for m in detalle.maquinas if m.recurso.vmid not in ips]
            if faltan and not cancelado.is_set():
                ips.update(servicio.obtener_ips(detalle, faltan, cancelado, permisos))
    if cancelado.is_set():
        return None, todos, ips
    exportar_csv(ruta, todos, ips if con_ip else None)
    return ruta, todos, ips


def inspeccionar_inventario(
    sesion: Sesion,
    reloj: Reloj,
    detalle: DetalleLote,
    marcadas: Collection[int],
    permisos: PermisosEfectivos | None,
) -> InspeccionRollback:
    """Solo lectura: encendidas, protegidas e ilegibles entre las marcadas (RF-C1.8 paso 2)."""
    return ServicioInventario(sesion, reloj).inspeccionar(detalle, marcadas, permisos)


def deshacer_inventario(
    sesion: Sesion,
    reloj: Reloj,
    detalle: DetalleLote,
    marcadas: Collection[int],
    observador: Callable[[ResultadoRollback], None],
    control: ControlLote,
    forzar_apagado: frozenset[int],
    forzar_desproteccion: frozenset[int],
    permisos: PermisosEfectivos | None,
) -> list[ResultadoRollback]:
    """Borra las máquinas marcadas del lote tras la confirmación con el código (RF-C1.8).

    La UI deshabilita el botón con más de 100 marcadas: ``deshacer`` lanzaría ``ValueError``.
    """
    return ServicioInventario(sesion, reloj).deshacer(
        detalle,
        marcadas,
        observador,
        control,
        forzar_apagado=forzar_apagado,
        forzar_desproteccion=forzar_desproteccion,
        permisos=permisos,
    )


def comprobar_vmid(sesion: Sesion, vmid: int) -> tuple[int, str | None]:
    """V-03: ``(vmid, None)`` si está libre o ``(vmid, siguiente_libre)`` si está ocupado."""
    try:
        sesion.cliente.proximo_vmid(vmid)
    except ErrorProxLaunch as e:
        if e.codigo != CodigoError.VMID_OCUPADO:
            raise
        return vmid, str(sesion.cliente.proximo_vmid())
    return vmid, None


def reanudar_seguimiento(
    servicio: ServicioCreacion,
    cfg: ConfiguracionVM,
    upid: str,
    una_vez: bool,
    inv: Inventario | None = None,
    *,
    al_cambiar_etapa: Callable[[Etapa], None],
    cancelado: threading.Event,
    al_enviar: Callable[[str], None] | None = None,
) -> ResultadoCreacion:
    """«Seguir esperando» (``una_vez=False``) y «Comprobar ahora» (``una_vez=True``).

    Retoma el seguimiento de una tarea YA enviada, sin volver a crear nada (CA-20.6),
    con la API pública del servicio. ``al_enviar`` se ignora (solo lo usa ``crear``).
    """
    del al_enviar
    al_cambiar_etapa(Etapa.CREANDO)
    if una_vez:
        resultado = servicio.comprobar_ahora(cfg, upid, inv=inv)
        if resultado.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS):
            al_cambiar_etapa(Etapa.LISTO)
        return resultado
    return servicio.seguir(cfg, upid, cancelado, al_cambiar_etapa, inv=inv)


def comprobar_existencia(
    servicio: ServicioCreacion,
    cfg: ConfiguracionVM,
    cliente: Any,
    id_lote: str,
    etiquetar: bool,
) -> EstadoMV | None:
    """Envío incierto sin UPID: ¿existe ya la máquina y es de este lote?

    ``None`` si no se pudo comprobar; ``NO_CREADA_SEGURA`` si no existe; si existe, la misma
    regla de propiedad que la reconciliación del motor y el rollback: ``OK`` (lleva la
    etiqueta del lote o el lote no etiqueta) o ``EXISTE_SIN_CONFIRMAR_PROPIEDAD`` (CA-L15.5),
    también cuando no se puede releer la configuración (la propiedad no está demostrada).
    """
    existe = servicio.existe_vm(cfg)
    if existe is None:
        return None
    if not existe:
        return EstadoMV.NO_CREADA_SEGURA
    if not etiquetar:
        return EstadoMV.OK
    try:
        config = cliente.config_vm(cfg.nodo, cfg.vmid)
    except Exception:
        # Mismo criterio que la reconciliación del motor: si no se puede releer la config, la
        # propiedad no está demostrada y la máquina no es elegible para «Deshacer».
        _log.warning("No se pudo releer la config para verificar la etiqueta (vmid=%s)", cfg.vmid)
        return EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD
    if config_en_creacion(config):
        return None  # sigue en creación (lock: create): la propiedad aún no se puede decidir
    if tiene_etiqueta_del_lote(config, id_lote):
        return EstadoMV.OK
    return EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD


# --- Lotes (MVP 2): puentes entre los hilos del motor y la interfaz --------------------


class PuenteLote(QObject):
    """Recoge las entradas del motor (hilos de trabajo) y las entrega a la interfaz.

    El observador solo guarda la última instantánea de cada MV y marca «sucio» con una señal
    ligera; un ``QTimer`` en el hilo de la interfaz lee ``tomar_si_sucio`` como mucho
    ``ACTUALIZACIONES_POR_S`` veces por segundo (coalescencia, CA-L13.5).
    """

    sucio = Signal()

    def __init__(self, elementos: tuple[ElementoPlan, ...], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cerrojo = threading.Lock()
        self._orden = tuple(e.vmid for e in elementos)
        self._entradas: dict[int, EntradaLibro] = {e.vmid: EntradaLibro(e) for e in elementos}
        self._sucio = True

    def observar(self, entrada: EntradaLibro) -> None:
        """Observador del motor: se llama desde cualquier hilo y nunca falla."""
        with self._cerrojo:
            self._entradas[entrada.elemento.vmid] = entrada
            ya_marcado = self._sucio
            self._sucio = True
        if not ya_marcado:
            try:
                self.sucio.emit()
            except RuntimeError:
                _log.debug("Señal descartada: el puente ya no existe")

    def instantanea(self) -> tuple[EntradaLibro, ...]:
        with self._cerrojo:
            return tuple(self._entradas[v] for v in self._orden)

    def tomar_si_sucio(self) -> tuple[EntradaLibro, ...] | None:
        """Instantánea si hubo cambios desde la última lectura; si no, ``None``."""
        with self._cerrojo:
            if not self._sucio:
                return None
            self._sucio = False
            return tuple(self._entradas[v] for v in self._orden)


class PuenteRollback(QObject):
    """Igual que ``PuenteLote`` para el avance de «Deshacer» (clave: VMID)."""

    sucio = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cerrojo = threading.Lock()
        self._resultados: dict[int, ResultadoRollback] = {}
        self._sucio = False

    def observar(self, resultado: ResultadoRollback) -> None:
        with self._cerrojo:
            self._resultados[resultado.vmid] = resultado
            ya_marcado = self._sucio
            self._sucio = True
        if not ya_marcado:
            try:
                self.sucio.emit()
            except RuntimeError:
                _log.debug("Señal descartada: el puente ya no existe")

    def tomar_si_sucio(self) -> list[ResultadoRollback] | None:
        with self._cerrojo:
            if not self._sucio:
                return None
            self._sucio = False
            return list(self._resultados.values())


def planificar_lote(
    sesion: Sesion,
    reloj: Reloj,
    definicion: DefinicionLote,
    inv: Inventario,
    version_forzada: tuple[int, int] | None,
    contexto_notas: ContextoNotas | None = None,
) -> Plan:
    """Planifica el lote (reserva VMIDs con lecturas) fuera del hilo de la interfaz.

    ``contexto_notas`` (fase A) trae el perfil elegido y la fecha de las notas de origen.
    """
    return Planificador(sesion, reloj).planificar(
        definicion, inv, version_forzada=version_forzada, contexto_notas=contexto_notas
    )


def replanificar_lote(
    sesion: Sesion,
    reloj: Reloj,
    definicion: DefinicionLote,
    version_forzada: tuple[int, int] | None,
    contexto_notas: ContextoNotas | None = None,
) -> tuple[Inventario, Plan]:
    """Relee el inventario y vuelve a planificar (plan viejo o simulación, CA-L10.6)."""
    inv = descubrir(sesion)
    plan = Planificador(sesion, reloj).planificar(
        definicion, inv, version_forzada=version_forzada, contexto_notas=contexto_notas
    )
    return inv, plan


def simular_lote(
    sesion: Sesion,
    reloj: Reloj,
    definicion: DefinicionLote,
    inv: Inventario,
    version_forzada: tuple[int, int] | None,
    contexto_notas: ContextoNotas | None = None,
) -> ResultadoSimulacion:
    """Simulación de solo lectura (RF-L11)."""
    return simular(
        sesion,
        definicion,
        inv,
        version_forzada=version_forzada,
        reloj=reloj,
        contexto_notas=contexto_notas,
    )


def simular_reintento(
    sesion: Sesion,
    reloj: Reloj,
    elementos: tuple[ElementoPlan, ...],
    definicion: DefinicionLote,
    version_forzada: tuple[int, int] | None,
    nodo_destino: str | None = None,
) -> tuple[Inventario, ResultadoSimulacion]:
    """Simula el plan del reintento (mismos nombres y VMIDs), solo con lecturas (RF-L11)."""
    sesion_ro = dataclasses.replace(sesion, cliente=sesion.cliente.solo_lectura())
    inv, plan = armar_reintento(
        sesion_ro, reloj, elementos, definicion, version_forzada, nodo_destino
    )
    plan = dataclasses.replace(plan, es_simulacion=True)
    peticiones: dict[int, dict[str, str]] = {}
    for e in plan.elementos:
        try:
            peticiones[e.vmid] = construir_parametros(e.cfg, inv, plan.version_validacion)
        except ErrorProxLaunch:
            continue  # su problema ya consta en el plan
    return inv, ResultadoSimulacion(
        plan=plan,
        peticiones=peticiones,
        version_detectada=(inv.version.mayor, inv.version.menor),
        version_forzada=version_forzada,
    )


def _motor(
    sesion: Sesion,
    reloj: Reloj,
    fabrica: Callable[[Sesion, Reloj], ServicioCreacion] | None,
) -> MotorLote:
    """Motor con la fábrica de creación inyectada (si la hay), igual en todas las acciones."""
    if fabrica:
        return MotorLote(sesion, reloj, fabrica_creacion=fabrica)
    return MotorLote(sesion, reloj)


def ejecutar_lote(
    sesion: Sesion,
    reloj: Reloj,
    plan: Plan,
    inv: Inventario,
    observador: Callable[[EntradaLibro], None],
    control: ControlLote,
    fabrica: Callable[[Sesion, Reloj], ServicioCreacion] | None = None,
    libro: Libro | None = None,
    espera_ip: EsperaIp | None = None,
) -> Libro:
    """Ejecuta el plan con el motor; bloquea hasta que termine (hilo de trabajo).

    ``libro`` es el libro creado de antemano por la interfaz: así existe aunque el motor
    falle y «Deshacer» y «Comprobar» siguen disponibles sobre lo ya creado. ``espera_ip`` (fase
    B) es la espera de IP, que corre en otro hilo; el motor solo le entrega cada máquina.
    """
    motor = _motor(sesion, reloj, fabrica)
    if libro is None:
        return motor.ejecutar(plan, inv, observador, control, espera_ip=espera_ip)
    return motor.ejecutar(plan, inv, observador, control, libro=libro, espera_ip=espera_ip)


def comprobar_dudosas_lote(
    sesion: Sesion,
    reloj: Reloj,
    libro: Libro,
    observador: Callable[[EntradaLibro], None],
    control: ControlLote,
    fabrica: Callable[[Sesion, Reloj], ServicioCreacion] | None = None,
    vmids: frozenset[int] | None = None,
) -> Libro:
    """Comprueba las máquinas dudosas, o solo las de ``vmids`` (solo lecturas, CA-L15.7)."""
    _motor(sesion, reloj, fabrica).comprobar_dudosas(libro, observador, control, vmids)
    return libro


def continuar_lote(
    sesion: Sesion,
    reloj: Reloj,
    libro: Libro,
    inv: Inventario,
    observador: Callable[[EntradaLibro], None],
    control: ControlLote,
    comprobar_antes: bool,
    fabrica: Callable[[Sesion, Reloj], ServicioCreacion] | None = None,
    espera_ip: EsperaIp | None = None,
) -> Libro:
    """«Comprobar y continuar» / «Reconectar»: comprueba las dudosas y envía solo las pendientes."""
    motor = _motor(sesion, reloj, fabrica)
    if comprobar_antes:
        motor.comprobar_dudosas(libro, observador, control)
    return motor.ejecutar_pendientes(libro, inv, observador, control, espera_ip=espera_ip)


def deshacer_lote(
    sesion: Sesion,
    reloj: Reloj,
    candidatos: list[CandidatoRollback],
    observador: Callable[[ResultadoRollback], None],
    control: ControlLote,
    id_lote: str,
    etiquetado: bool,
    forzar_apagado: frozenset[int] = frozenset(),
    forzar_desproteccion: frozenset[int] = frozenset(),
    permisos: PermisosEfectivos | None = None,
) -> list[ResultadoRollback]:
    """Elimina las máquinas elegidas del lote (acción confirmada por el usuario).

    Solo las máquinas de ``forzar_apagado`` / ``forzar_desproteccion`` (las que el usuario vio
    en la confirmación expresa) se apagan y desprotegen antes de borrar; el resto se omite.
    """
    return ServicioRollback(sesion, reloj).deshacer(
        candidatos,
        observador,
        control,
        id_lote=id_lote,
        etiquetado=etiquetado,
        forzar_apagado=forzar_apagado,
        forzar_desproteccion=forzar_desproteccion,
        permisos=permisos,
    )


def inspeccionar_lotes(
    sesion: Sesion,
    reloj: Reloj,
    grupos: list[tuple[list[CandidatoRollback], str, bool]],
    permisos: PermisosEfectivos | None = None,
) -> InspeccionRollback:
    """Inspecciona las máquinas propias encendidas, protegidas e ilegibles de los grupos (GET)."""
    servicio = ServicioRollback(sesion, reloj)
    encendidas: list[int] = []
    protegidas: list[int] = []
    encendidas_sin: list[int] = []
    protegidas_sin: list[int] = []
    ilegibles: list[int] = []
    nombres: dict[int, str] = {}
    for candidatos, id_lote, etiquetado in grupos:
        inspeccion = servicio.inspeccionar(
            candidatos, id_lote=id_lote, etiquetado=etiquetado, permisos=permisos
        )
        encendidas.extend(inspeccion.encendidas)
        protegidas.extend(inspeccion.protegidas)
        encendidas_sin.extend(inspeccion.encendidas_sin_privilegio)
        protegidas_sin.extend(inspeccion.protegidas_sin_privilegio)
        ilegibles.extend(inspeccion.ilegibles)
        nombres.update(inspeccion.nombres)
    return InspeccionRollback(
        tuple(encendidas),
        tuple(protegidas),
        tuple(encendidas_sin),
        tuple(protegidas_sin),
        tuple(ilegibles),
        nombres,
    )


def deshacer_lotes(
    sesion: Sesion,
    reloj: Reloj,
    grupos: list[tuple[list[CandidatoRollback], str, bool]],
    observador: Callable[[ResultadoRollback], None],
    control: ControlLote,
    forzar_apagado: frozenset[int] = frozenset(),
    forzar_desproteccion: frozenset[int] = frozenset(),
    permisos: PermisosEfectivos | None = None,
    esperas_a_cancelar: Sequence[tuple[EsperaIp, frozenset[int]]] = (),
) -> list[ResultadoRollback]:
    """Deshace las máquinas elegidas de uno o varios lotes de la sesión, lote por lote.

    ``esperas_a_cancelar`` (B3, DT-B14): ANTES del primer ``DELETE`` se deja de sondear la IP de
    las máquinas elegidas. ``EsperaIp.cancelar`` bloquea hasta que termina la petición en vuelo,
    por eso se hace aquí, en el hilo del trabajador, y de forma síncrona.
    """
    for espera, vmids in esperas_a_cancelar:
        espera.cancelar(vmids)
    resultados: list[ResultadoRollback] = []
    for candidatos, id_lote, etiquetado in grupos:
        resultados.extend(
            deshacer_lote(
                sesion,
                reloj,
                candidatos,
                observador,
                control,
                id_lote,
                etiquetado,
                forzar_apagado,
                forzar_desproteccion,
                permisos,
            )
        )
        if control.cancelado.is_set():
            break
    return resultados


def crear_espera_ip(
    sesion: Sesion, reloj: Reloj, libro: Libro, observador: Callable[[EntradaLibro], None]
) -> EsperaIp:
    """Espera de IP de UNA ejecución del motor (B3).

    Su ``al_resultado`` es ``enlazar_espera(libro, observador)``: anota el resultado en el libro
    (con su aviso) y avisa al observador, que pasa a Qt por señales (``PuenteLote``). Para
    ``ejecutar_pendientes`` se crea otra instancia.
    """
    return EsperaIp(sesion, reloj, enlazar_espera(libro, observador))


def guardar_ips(ruta: Path, entradas: Sequence[EntradaLibro]) -> Path:
    """Exporta «nombre → IP» a CSV (RF-B3.6): escritura atómica, sin datos de cloud-init."""
    return guardar_ips_csv(ruta, entradas)


def _secretos_de_config(cfg: ConfiguracionVM | None, vistos: dict[int, Secreto]) -> None:
    ci = cfg.cloudinit if cfg is not None else None
    if ci is not None and ci.contrasena is not None:
        vistos[id(ci.contrasena)] = ci.contrasena


def secretos_de_plan(plan: Plan) -> list[Secreto]:
    """Las contraseñas (``Secreto``) que un plan mantiene en memoria, sin repetidas.

    Un ``Secreto`` se copia por identidad (``deepcopy`` devuelve la misma instancia), así que
    una sola llamada a ``olvidar()`` sirve para el plan, el libro y las filas (DT-B1).
    """
    vistos: dict[int, Secreto] = {}
    for e in plan.elementos:
        _secretos_de_config(e.cfg, vistos)
    definicion = plan.definicion
    _secretos_de_config(definicion.plantilla, vistos)
    if definicion.opciones is not None and definicion.opciones.cloudinit is not None:
        sec = definicion.opciones.cloudinit.contrasena
        if sec is not None:
            vistos[id(sec)] = sec
    for fila in definicion.filas:
        _secretos_de_config(fila.cfg, vistos)
        parcial = fila.opciones.cloudinit if fila.opciones is not None else None
        if parcial is not None and parcial.contrasena is not None:
            vistos[id(parcial.contrasena)] = parcial.contrasena
    return list(vistos.values())


def olvidar_secretos_de_plan(plan: Plan) -> int:
    """Olvida las contraseñas del plan (``Secreto.olvidar``, que también las quita del
    registro de enmascarado). Devuelve cuántas se olvidaron."""
    secretos = secretos_de_plan(plan)
    for s in secretos:
        s.olvidar()
    return len(secretos)


def secretos_de_filas(filas: Iterable[Any]) -> list[Secreto]:
    """Las contraseñas de unas filas (``FilaLote`` o ``FilaInterpretada``: ``cfg`` y ``opciones``).

    Sirve para olvidar las de la vista previa de un CSV o de un lote «por filas» (B6, QA-M4).
    Sin repetidas: cada ``Secreto`` se cuenta una vez aunque lo compartan varias copias.
    """
    vistos: dict[int, Secreto] = {}
    for fila in filas:
        _secretos_de_config(fila.cfg, vistos)
        parcial = fila.opciones.cloudinit if fila.opciones is not None else None
        if parcial is not None and parcial.contrasena is not None:
            vistos[id(parcial.contrasena)] = parcial.contrasena
    return list(vistos.values())


def olvidar_secretos_de_filas(filas: Iterable[Any], *, salvo: Collection[Secreto] = ()) -> int:
    """Olvida las contraseñas de unas filas, menos las de ``salvo`` (por identidad).

    Devuelve cuántas se olvidaron.
    """
    conservar = {id(x) for x in salvo}
    olvidados = 0
    for secreto in secretos_de_filas(filas):
        if id(secreto) not in conservar:
            secreto.olvidar()
            olvidados += 1
    return olvidados


def hay_contrasena_pendiente(entradas: Iterable[EntradaLibro]) -> bool:
    """¿Alguna máquina necesita aún reenviar su contraseña (``ajuste_pendiente:contrasena``)?"""
    return any("ajuste_pendiente:contrasena" in e.avisos for e in entradas)


def armar_reintento(
    sesion: Sesion,
    reloj: Reloj,
    elementos: tuple[ElementoPlan, ...],
    definicion: DefinicionLote,
    version_forzada: tuple[int, int] | None,
    nodo_destino: str | None = None,
) -> tuple[Inventario, Plan]:
    """Plan nuevo con las máquinas que no se crearon (RF-L21).

    Conserva nombres y VMIDs, y los nodos (o los lleva todos a ``nodo_destino``). Relee el
    inventario, comprueba que cada VMID siga libre y valida cada máquina y el espacio con
    las mismas reglas del planificador.
    """
    inv = descubrir(sesion)
    version = version_forzada if version_forzada is not None else sesion.capacidades.version
    id_lote = secrets.token_hex(4)
    propias = (ETIQUETA_APP, f"{PREFIJO_ETIQUETA_LOTE}{id_lote}") if definicion.etiquetar else ()
    nuevos: list[ElementoPlan] = []
    problemas: list[Problema] = []
    for i, e in enumerate(elementos):
        cfg = copy.deepcopy(e.cfg)
        base = tuple(
            t
            for t in cfg.etiquetas
            if t != ETIQUETA_APP and not t.startswith(PREFIJO_ETIQUETA_LOTE)
        )
        cfg.etiquetas = base + propias
        nodo = nodo_destino or e.nodo
        cfg.nodo = nodo
        nuevos.append(ElementoPlan(i, e.nombre, e.vmid, nodo, cfg))
        if not sesion.cliente.vmid_libre(e.vmid):
            problemas.append(
                Problema("V-03", Severidad.ERROR, "vmid", {"vmid": str(e.vmid)}, indice=i)
            )
    detectada = (inv.version.mayor, inv.version.menor)
    caps = Capacidades(version=version, forzada=version != detectada)
    for e in nuevos:
        for pm in validar_vm(e.cfg, inv, caps):
            sev = Severidad.ERROR if pm.severidad == SeveridadM1.ERROR else Severidad.AVISO
            problemas.append(Problema(pm.codigo, sev, pm.campo, dict(pm.params), e.indice))
    uso = uso_por_clave(nuevos, inv)
    problemas.extend(evaluar_espacio(uso, definicion.politica_thin))
    por_nodo: dict[str, int] = {}
    for e in nuevos:
        por_nodo[e.nodo] = por_nodo.get(e.nodo, 0) + 1
    plan = Plan(
        id_lote=id_lote,
        definicion=definicion,
        elementos=tuple(nuevos),
        vmids_saltados=(),
        reparto={n: (c, MotivoReparto.ELEGIDO_POR_USUARIO.value) for n, c in por_nodo.items()},
        uso=uso,
        problemas=tuple(problemas),
        capacidad_maxima=None,
        generado_en=reloj.ahora(),
        version_validacion=version,
    )
    return inv, plan


# --- Archivos del usuario (MVP 3): lectura, análisis y escritura fuera del hilo de la interfaz ---
# Envoltorios finos del núcleo (RNF-M05): solo reciben rutas y datos, nunca una sesión ni un
# cliente (INV-M1). Leen con ``O_RDONLY`` y escriben de forma atómica; los errores salen como
# ``ErrorProxLaunch`` y el ``Lanzador`` los entrega al hilo de la interfaz.


def leer_lote_guardado(ruta: Path) -> ArchivoLote:
    """Lee y valida un lote guardado (carga atómica: o todo válido o error, RF-G03)."""
    return leer_archivo_lote(ruta)


def guardar_lote_guardado(ruta: Path, lote: LoteGuardado, app_version: str) -> Path:
    """Escribe un lote guardado (lista blanca, atómico, 0600). Devuelve la ruta escrita."""
    guardar_lote(ruta, lote, app_version=app_version)
    return ruta


def leer_perfiles_de_archivo(ruta: Path) -> ArchivoPerfiles:
    """Lee un archivo de perfiles de máquina de un tercero (≤ 256 KiB, RF-P09)."""
    return leer_archivo_perfiles(ruta)


def exportar_perfiles_a_archivo(
    ruta: Path, perfiles: Sequence[PerfilMaquina], con_pistas: bool, app_version: str
) -> Path:
    """Exporta perfiles de máquina a un archivo (RF-P08). Devuelve la ruta escrita."""
    exportar_perfiles(ruta, perfiles, con_pistas=con_pistas, app_version=app_version)
    return ruta


def escribir_plantilla_csv(ruta: Path, separador: str) -> Path:
    """Escribe la plantilla CSV descargable (RF-C10). Devuelve la ruta escrita."""
    escribir_plantilla(ruta, separador=separador)
    return ruta


def escribir_informe_csv(ruta: Path, informe: InformeLote) -> Path:
    """Escribe el informe del lote como CSV por el escritor único (RF-C14)."""
    from proxlaunch.interfaz.informe_lote import guardar_informe_csv

    guardar_informe_csv(ruta, informe)
    return ruta


# --- Origen del SO (MVP 4): lecturas del catálogo, storages recordados y ajustes ---------------
# Solo lecturas (GET) salvo el reintento de ajustes (PUT idempotentes sobre MVs del libro).


def leer_listados(
    sesion: Sesion, reloj: Reloj, inv: Inventario, nodo: str, contenido: Contenido
) -> tuple[ListadoStorage, ...]:
    """Archivos ``iso`` o ``import`` de cada storage activo del nodo (RF-O07, RF-O16)."""
    return ServicioCatalogo(sesion, reloj).listar(inv, nodo, contenido)


def leer_plantillas(sesion: Sesion, reloj: Reloj) -> tuple[Plantilla, ...]:
    """Plantillas que el token puede ver (RF-O19)."""
    return ServicioCatalogo(sesion, reloj).plantillas()


def leer_detalle_plantilla(
    sesion: Sesion, reloj: Reloj, inv: Inventario, nodo: str, vmid: int
) -> tuple[DetallePlantilla | None, dict[str, frozenset[str]]]:
    """Configuración de la plantilla elegida y los formatos de los storages de su nodo."""
    servicio = ServicioCatalogo(sesion, reloj)
    return servicio.detalle_plantilla(nodo, vmid), servicio.formatos(inv, [nodo])


def leer_catalogo_para(
    sesion: Sesion,
    reloj: Reloj,
    inv: Inventario,
    necesidades: NecesidadesCatalogo,
    nodos: Sequence[str],
) -> CatalogoServidor:
    """Lo que necesita un lote cargado o importado para revisar sus desajustes (RF-O27)."""
    return ServicioCatalogo(sesion, reloj).leer_para(inv, necesidades, nodos, opciones=True)


def guardar_storage_recordado(
    repositorio: RepositorioPerfiles, perfil_id: str, contenido: Contenido, storage: str | None
) -> PerfilConexion | None:
    """Guarda (o borra, con ``None``) el storage recordado del perfil de conexión (RF-O05).

    Lee el perfil guardado y le cambia solo ese campo, para no pisar lo que haya editado el
    diálogo de conexión. Devuelve el perfil escrito, o ``None`` si ya no existe.
    """
    perfil = repositorio.obtener(perfil_id)
    if perfil is None:
        return None
    nuevo = con_recordado(perfil, contenido, storage)
    repositorio.guardar(nuevo)
    return nuevo


def reintentar_ajustes_lote(
    sesion: Sesion,
    reloj: Reloj,
    libro: Libro,
    vmids: tuple[int, ...],
    inv: Inventario,
    observador: Callable[[EntradaLibro], None],
    control: ControlLote,
    fabrica: Callable[[Sesion, Reloj], ServicioCreacion] | None = None,
    espera: EsperaIp | None = None,
) -> Libro:
    """«Reintentar ajustes»: reenvía solo los ``PUT`` pendientes de los clones (CA-O22.6).

    El reintento del núcleo no devuelve nada (solo actualiza el libro); también enciende la MV si
    procede. Con ``espera`` (QA-M6) las MVs que quedan bien y encendidas, y que pidieron esperar
    su IP, se le entregan al terminar, igual que hace el motor al crear.
    """
    if fabrica:
        reintentar_ajustes(
            libro, vmids, sesion, reloj, inv, observador, control, fabrica_creacion=fabrica
        )
    else:
        reintentar_ajustes(libro, vmids, sesion, reloj, inv, observador, control)
    if espera is not None:
        _entregar_a_espera_tras_reintento(libro, vmids, espera)
    return libro


def _entregar_a_espera_tras_reintento(
    libro: Libro, vmids: Collection[int], espera: EsperaIp
) -> None:
    """Entrega a la espera de IP las MVs reintentadas que ahora están bien y encendidas."""
    pedidos = set(vmids)
    for entrada in libro.instantanea():
        cfg = entrada.elemento.cfg
        if (
            entrada.elemento.vmid not in pedidos
            or not (cfg.encender and cfg.esperar_ip)
            or entrada.estado not in (EstadoMV.OK, EstadoMV.CON_AVISOS)
            or AVISO_ENCENDIDO_FALLIDO in entrada.avisos
            or AVISO_ENCENDIDO_OMITIDO in entrada.avisos
        ):
            continue
        tarjeta = cfg.cloudinit.tarjeta(0) if cfg.cloudinit is not None else None
        ip_fija = tarjeta.ip if tarjeta is not None and tarjeta.modo == ModoTarjeta.FIJA else None
        try:
            espera.anadir(entrada.elemento.vmid, entrada.elemento.nodo, cfg.plazo_ip_s, ip_fija)
        except Exception:  # nunca debe romper el reintento
            _log.exception(
                "Fallo al entregar la MV a la espera de IP (vmid=%s)", entrada.elemento.vmid
            )
