"""Trabajos en segundo plano: ``Trabajador(QRunnable)`` con señales (RNF-01).

Toda llamada de red del núcleo se ejecuta aquí, en el ``QThreadPool`` global. El
resultado vuelve al hilo principal por señales en cola; solo ese hilo toca widgets.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Bridge, Inventario, Storage
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.registro import enmascarar
from proxlaunch.nucleo.servicios.conexion import Sesion, permisos_faltantes
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.servicios.descubrimiento import descubrir, descubrir_nodo

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
        # El Lanzador conserva la referencia hasta que termine; así no se destruye antes.
        self.setAutoDelete(False)

    def cancelar(self) -> None:
        """Pide al trabajo que deje de esperar (no deshace nada)."""
        self.cancelado.set()

    def run(self) -> None:
        try:
            if self._con_contexto:
                resultado = self._funcion(
                    *self._args,
                    al_cambiar_etapa=self.senales.etapa.emit,
                    al_enviar=self.senales.upid.emit,
                    cancelado=self.cancelado,
                    **self._kwargs,
                )
            else:
                resultado = self._funcion(*self._args, **self._kwargs)
        except ErrorProxLaunch as error:
            self.senales.fallo.emit(error)
        except Exception as exc:  # error inesperado: nunca debe romper el hilo
            _log.exception("Error inesperado en un trabajo en segundo plano")
            self.senales.fallo.emit(
                ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, enmascarar(str(exc)))
            )
        else:
            self.senales.terminado.emit(resultado)


class Lanzador(QObject):
    """Lanza trabajadores en el ``QThreadPool`` global y gestiona su ciclo de vida."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._activos: set[Trabajador] = set()

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
        cola = Qt.ConnectionType.QueuedConnection
        senales = trabajador.senales
        if al_upid is not None:
            senales.upid.connect(al_upid, cola)
        if al_etapa is not None:
            senales.etapa.connect(al_etapa, cola)
        senales.terminado.connect(lambda r: self._finalizar(trabajador, al_terminar, r), cola)
        senales.fallo.connect(lambda e: self._finalizar_fallo(trabajador, al_fallar, e), cola)
        self._activos.add(trabajador)
        QThreadPool.globalInstance().start(trabajador)
        return trabajador

    def _finalizar(
        self, trabajador: Trabajador, destino: Callable[[Any], None] | None, resultado: Any
    ) -> None:
        self._activos.discard(trabajador)
        if destino is not None:
            destino(resultado)

    def _finalizar_fallo(
        self,
        trabajador: Trabajador,
        destino: Callable[[ErrorProxLaunch], None] | None,
        error: ErrorProxLaunch,
    ) -> None:
        self._activos.discard(trabajador)
        if destino is not None:
            destino(error)

    def cancelar_todos(self) -> None:
        """Pide la cancelación de todos los trabajos activos."""
        for t in list(self._activos):
            t.cancelar()

    def esperar(self, milisegundos: int = 3000) -> bool:
        """Espera a que el pool termine (al cerrar la aplicación)."""
        return QThreadPool.globalInstance().waitForDone(milisegundos)


# --- Funciones de trabajo (se ejecutan en el pool, sin tocar widgets) -----------------


def descubrir_y_comprobar_permisos(sesion: Sesion) -> tuple[Inventario, list[str] | None]:
    """Descubre el inventario y comprueba los permisos tras conectar (RF-11, RF-12)."""
    inventario = descubrir(sesion)
    return inventario, permisos_faltantes(sesion)


def recargar_nodo(sesion: Sesion, nodo: str) -> tuple[str, list[Storage], list[Bridge]]:
    """Relee storages y bridges de un nodo (CA-11.7)."""
    storages, bridges = descubrir_nodo(sesion, nodo)
    return nodo, storages, bridges


def reintentar_nodos(
    sesion: Sesion, nodos: list[str]
) -> tuple[dict[str, tuple[list[Storage], list[Bridge]]], dict[str, ErrorProxLaunch]]:
    """Reintenta el descubrimiento de los nodos que fallaron (CA-11.8)."""
    recuperados: dict[str, tuple[list[Storage], list[Bridge]]] = {}
    fallidos: dict[str, ErrorProxLaunch] = {}
    for nodo in nodos:
        try:
            recuperados[nodo] = descubrir_nodo(sesion, nodo)
        except ErrorProxLaunch as e:
            fallidos[nodo] = e
    return recuperados, fallidos


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
        resultado = servicio.comprobar_ahora(cfg, upid)
        if resultado.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS):
            al_cambiar_etapa(Etapa.LISTO)
        return resultado
    return servicio.seguir(cfg, upid, cancelado, al_cambiar_etapa)
