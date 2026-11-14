"""Motor del lote: colas por nodo, pausa, cancelación y reconciliación (RF-L12..L17).

Núcleo sin Qt. ``MotorLote.ejecutar`` es bloqueante: la interfaz lo llama en un hilo de
trabajo y recibe el avance por el ``observador`` (que se invoca desde los hilos del motor).

Invariante crítico (INV-L1): para un mismo elemento del plan ``ServicioCreacion.crear`` se
llama como máximo una vez y el motor jamás reintenta un envío.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import MAX_NODOS_PARALELOS, UMBRAL_PAUSA_ERRORES
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    ESTADOS_DUDOSOS,
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
    MotivoNoEnviada,
    MotivoPausa,
)
from proxlaunch.nucleo.lote.politica_pausa import PoliticaPausa
from proxlaunch.nucleo.lote.reconciliacion import reconciliar_incierta
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.registro import enmascarar
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

_log = logging.getLogger("proxlaunch.lote.motor")

Observador = Callable[[EntradaLibro], None]
FabricaCreacion = Callable[[Sesion, Reloj], ServicioCreacion]

_MAX_DETALLE_LOG = 300

_ESTADO_POR_ETAPA: dict[Etapa, EstadoMV] = {
    Etapa.VALIDANDO: EstadoMV.VALIDANDO,
    Etapa.ENVIANDO: EstadoMV.ENVIANDO,
    Etapa.CREANDO: EstadoMV.CREANDO,
    Etapa.COMPROBANDO: EstadoMV.COMPROBANDO,
}
_ESTADO_POR_DESENLACE: dict[Desenlace, EstadoMV] = {
    Desenlace.OK: EstadoMV.OK,
    Desenlace.CON_AVISOS: EstadoMV.CON_AVISOS,
    Desenlace.ERROR: EstadoMV.ERROR,
    Desenlace.PARCIAL: EstadoMV.PARCIAL,
    Desenlace.TIEMPO_AGOTADO: EstadoMV.TIEMPO_AGOTADO,
    Desenlace.CONEXION_PERDIDA: EstadoMV.CONEXION_PERDIDA,
}


class ControlLote:
    """Control compartido entre la interfaz y los hilos del motor (seguro entre hilos).

    - ``cancelar()``: no se envía ninguna MV más; las ya enviadas siguen esperando su
      desenlace (CA-L16.2).
    - ``dejar_de_esperar()``: además deja de esperar las tareas en vuelo (quedan
      ``CONEXION_PERDIDA`` con su UPID). No detiene ninguna tarea en Proxmox.
    - ``pausar``/``reanudar``: pausa del envío; las MVs sin enviar siguen ``PENDIENTE``.
    - ``suspender()``: hace que el motor salga sin cancelar, dejando las MVs sin enviar como
      ``PENDIENTE`` (para continuar después con ``ejecutar_pendientes``, p. ej. con una
      sesión nueva).

    Una operación nueva (comprobar, ejecutar pendientes, deshacer) debe usar un
    ``ControlLote`` nuevo: un control cancelado no se puede rearmar.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._cancelado = threading.Event()
        self._abandono = threading.Event()
        self._suspendido = False
        self._motivo: MotivoPausa | None = None
        self._error: ErrorProxLaunch | None = None
        self._ignoradas: set[CodigoError] = set()

    @property
    def cancelado(self) -> threading.Event:
        """Se activa con ``cancelar()`` o ``dejar_de_esperar()``."""
        return self._cancelado

    @property
    def evento_abandono(self) -> threading.Event:
        """Evento que se entrega a ``ServicioCreacion``: solo ``dejar_de_esperar()`` lo activa."""
        return self._abandono

    @property
    def suspendido(self) -> bool:
        return self._suspendido

    @property
    def motivo_pausa(self) -> MotivoPausa | None:
        return self._motivo

    @property
    def error_pausa(self) -> ErrorProxLaunch | None:
        return self._error

    @property
    def causas_ignoradas(self) -> frozenset[CodigoError]:
        with self._cond:
            return frozenset(self._ignoradas)

    def cancelar(self) -> None:
        with self._cond:
            self._cancelado.set()
            self._cond.notify_all()

    def dejar_de_esperar(self) -> None:
        with self._cond:
            self._abandono.set()
            self._cancelado.set()
            self._cond.notify_all()

    def suspender(self) -> None:
        with self._cond:
            self._suspendido = True
            self._cond.notify_all()

    def pausar(self, motivo: MotivoPausa, error: ErrorProxLaunch | None = None) -> bool:
        """Pausa el envío. Conserva la primera causa si ya estaba en pausa.

        Devuelve ``True`` si esta llamada provocó la pausa.
        """
        with self._cond:
            if self._motivo is not None or self._cancelado.is_set():
                return False
            self._motivo = motivo
            self._error = error
            return True

    def reanudar(self, ignorar_causa: bool = False) -> None:
        """Reanuda el envío. Con ``ignorar_causa`` no se vuelve a pausar por la misma
        causa (``CodigoError`` del error de la pausa) en este lote (CA-L14.4)."""
        with self._cond:
            if ignorar_causa and self._error is not None:
                self._ignoradas.add(self._error.codigo)
            self._motivo = None
            self._error = None
            self._cond.notify_all()

    def esperar_si_pausado(self, timeout: float | None = None) -> bool:
        """Bloquea mientras el lote esté en pausa (y no cancelado ni suspendido).

        Devuelve ``True`` si ya puede continuar (o se canceló/suspendió: quien llama debe
        mirar ``cancelado``/``suspendido``) y ``False`` si venció ``timeout`` en pausa.
        """
        with self._cond:
            return self._cond.wait_for(
                lambda: self._motivo is None or self._cancelado.is_set() or self._suspendido,
                timeout,
            )


class _Turno(StrEnum):
    SEGUIR = "seguir"
    CANCELADO = "cancelado"
    PAUSA = "pausa"
    SUSPENDER = "suspender"


@dataclass
class _Corrida:
    """Estado de una ejecución del motor."""

    libro: Libro
    inv: Inventario
    observador: Observador
    control: ControlLote
    politica: PoliticaPausa
    cerrojo: threading.Lock = field(default_factory=threading.Lock)
    intentados: set[int] = field(default_factory=set)  # vmids para los que se llamó a crear


class MotorLote:
    """Ejecuta un ``Plan`` con una cola por nodo y como máximo ``max_nodos`` nodos a la vez."""

    def __init__(
        self,
        sesion: Sesion,
        reloj: Reloj,
        *,
        fabrica_creacion: FabricaCreacion = ServicioCreacion,
        max_nodos: int = MAX_NODOS_PARALELOS,
        umbral_pausa: int = UMBRAL_PAUSA_ERRORES,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._fabrica = fabrica_creacion
        self._max_nodos = max(1, max_nodos)
        self._umbral = umbral_pausa

    # --- API pública ------------------------------------------------------------------

    def ejecutar(
        self,
        plan: Any,
        inv: Inventario,
        observador: Observador,
        control: ControlLote,
    ) -> Libro:
        """Ejecuta el plan completo y devuelve el libro. Bloqueante.

        Si el lote se pausa, bloquea hasta ``control.reanudar()``, ``cancelar()`` o
        ``suspender()``.
        """
        libro = Libro(plan)
        corrida = _Corrida(libro, inv, observador, control, PoliticaPausa(self._umbral))
        self._correr(corrida, [e.elemento for e in libro.instantanea()])
        return libro

    def ejecutar_pendientes(
        self,
        libro: Libro,
        inv: Inventario,
        observador: Observador,
        control: ControlLote,
    ) -> Libro:
        """Envía solo las MVs ``PENDIENTE`` que nunca se intentaron (CA-L17.3).

        Nunca toca una MV ya intentada (INV-L1/INV-L3). Devuelve el mismo libro.
        """
        corrida = _Corrida(libro, inv, observador, control, PoliticaPausa(self._umbral))
        self._correr(corrida, [e.elemento for e in libro.pendientes()])
        return libro

    def comprobar_dudosas(self, libro: Libro, observador: Observador, control: ControlLote) -> None:
        """Comprueba las MVs ``CONEXION_PERDIDA``/``TIEMPO_AGOTADO``. Solo lecturas (CA-L15.7).

        Con UPID usa ``comprobar_ahora``; sin UPID, la reconciliación por existencia.
        """
        dudosas = [e for e in libro.instantanea() if e.estado in ESTADOS_DUDOSOS]
        if not dudosas:
            return
        trabajadores = max(1, min(self._max_nodos, len(dudosas)))
        with ThreadPoolExecutor(max_workers=trabajadores, thread_name_prefix="dudosas") as pool:
            futuros = [
                pool.submit(self._comprobar_una, libro, e, observador, control) for e in dudosas
            ]
        for futuro in futuros:
            if (exc := futuro.exception()) is not None:
                raise exc

    # --- Ejecución --------------------------------------------------------------------

    def _correr(self, c: _Corrida, elementos: list[ElementoPlan]) -> None:
        colas: dict[str, list[ElementoPlan]] = {}
        for elemento in elementos:
            colas.setdefault(elemento.nodo, []).append(elemento)
        if not colas:
            return
        trabajadores = max(1, min(self._max_nodos, len(colas)))
        with ThreadPoolExecutor(max_workers=trabajadores, thread_name_prefix="lote") as pool:
            futuros = [pool.submit(self._procesar_cola, c, cola) for cola in colas.values()]
        for futuro in futuros:
            if (exc := futuro.exception()) is not None:
                raise exc

    def _procesar_cola(self, c: _Corrida, cola: list[ElementoPlan]) -> None:
        """Procesa de forma secuencial las MVs de un nodo (≤ 1 creación en curso por nodo)."""
        servicio = self._fabrica(self._sesion, self._reloj)
        for posicion, elemento in enumerate(cola):
            turno = self._esperar_turno(c.control)
            if turno == _Turno.SUSPENDER:
                return
            if turno != _Turno.SEGUIR:
                motivo = (
                    MotivoNoEnviada.CANCELADO
                    if turno == _Turno.CANCELADO
                    else MotivoNoEnviada.PAUSA
                )
                self._no_enviadas(c, cola[posicion:], motivo)
                return
            if self._procesar_elemento(c, servicio, elemento):
                # Nodo caído: solo se vacía la cola de este nodo (CA-L14.5).
                self._no_enviadas(c, cola[posicion + 1 :], MotivoNoEnviada.NODO_CAIDO)
                return

    @staticmethod
    def _esperar_turno(control: ControlLote) -> _Turno:
        """Decide si se puede enviar la siguiente MV; espera mientras haya pausa."""
        espero = False
        while True:
            if control.suspendido:
                return _Turno.SUSPENDER
            if control.cancelado.is_set():
                return _Turno.PAUSA if espero else _Turno.CANCELADO
            if control.motivo_pausa is None:
                return _Turno.SEGUIR
            espero = True
            control.esperar_si_pausado(None)

    def _no_enviadas(
        self, c: _Corrida, elementos: list[ElementoPlan], motivo: MotivoNoEnviada
    ) -> None:
        for elemento in elementos:
            entrada = c.libro.marcar_no_enviada(elemento.vmid, motivo, self._reloj.ahora())
            self._emitir(c, entrada)

    def _procesar_elemento(self, c: _Corrida, servicio: ServicioCreacion, el: ElementoPlan) -> bool:
        """Crea una MV. Devuelve ``True`` si hay que vaciar la cola del nodo (nodo caído)."""
        libro = c.libro
        with c.cerrojo:
            if el.vmid in c.intentados:
                raise AssertionError(f"INV-L1: segundo intento de crear el VMID {el.vmid}")
            c.intentados.add(el.vmid)
        self._emitir(c, libro.iniciar(el.vmid, self._reloj.ahora()))

        def al_cambiar_etapa(etapa: Etapa) -> None:
            if etapa == Etapa.ENVIANDO:
                # Justo antes del POST: desde aquí la MV nunca se considera "no enviada".
                self._emitir(c, libro.marcar_post_intentado(el.vmid, self._reloj.ahora()))
            estado = _ESTADO_POR_ETAPA.get(etapa)
            if estado is not None:
                self._emitir(c, libro.actualizar_estado(el.vmid, estado))

        def al_enviar(upid: str) -> None:
            self._emitir(c, libro.registrar_upid(el.vmid, upid))

        try:
            resultado = servicio.crear(
                el.cfg,
                c.inv,
                al_cambiar_etapa,
                c.control.evento_abandono,
                al_enviar=al_enviar,
            )
        except AssertionError:
            raise
        except Exception as exc:  # CA-L12.8: un fallo inesperado no aborta el lote
            _log.exception(
                "Fallo inesperado al procesar la MV (lote=%s vmid=%s)", libro.id_lote, el.vmid
            )
            error = ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, type(exc).__name__)
            enviado = libro.entrada(el.vmid).post_intentado
            resultado = ResultadoCreacion(
                Desenlace.CONEXION_PERDIDA if enviado else Desenlace.ERROR,
                el.vmid,
                el.nodo,
                libro.entrada(el.vmid).upid,
                error,
            )
        return self._cerrar(c, servicio, el, resultado)

    def _cerrar(
        self, c: _Corrida, servicio: ServicioCreacion, el: ElementoPlan, res: ResultadoCreacion
    ) -> bool:
        """Traduce el ``ResultadoCreacion`` al estado final del libro y evalúa la pausa."""
        libro = c.libro
        vmid = el.vmid
        if res.upid is not None and not libro.entrada(vmid).post_intentado:
            # Una fábrica ajena puede no avisar de la etapa de envío: hubo POST igualmente.
            self._emitir(c, libro.marcar_post_intentado(vmid, self._reloj.ahora()))
        enviado = libro.entrada(vmid).post_intentado
        upid = res.upid
        error = res.error
        avisos: tuple[str, ...] = ()

        if res.desenlace == Desenlace.CANCELADO:
            if upid is None and not enviado:
                self._emitir(
                    c, libro.marcar_no_enviada(vmid, MotivoNoEnviada.CANCELADO, self._reloj.ahora())
                )
                return False
            estado = EstadoMV.CONEXION_PERDIDA  # dejó de esperarse una tarea en vuelo
            if upid is None:
                error = ErrorProxLaunch(
                    CodigoError.LOTE_ENVIO_INCIERTO, {"nombre": el.nombre, "vmid": str(vmid)}
                )
        else:
            estado = _ESTADO_POR_DESENLACE[res.desenlace]
            if estado == EstadoMV.CONEXION_PERDIDA and upid is None:
                if enviado:
                    estado, aviso, error_rec = reconciliar_incierta(
                        servicio,
                        el.cfg,
                        self._reloj,
                        c.control.evento_abandono,
                        id_lote=libro.id_lote,
                        etiquetar=libro.plan.definicion.etiquetar,
                        cliente=self._sesion.cliente,
                    )
                    avisos = (aviso,) if aviso else ()
                    if estado == EstadoMV.CONEXION_PERDIDA:
                        error = error_rec
                    elif estado == EstadoMV.OK:
                        error = None
                else:
                    # Falló la red antes del POST: no se envió nada, la MV no se creó.
                    estado = EstadoMV.ERROR

        entrada = libro.finalizar(
            vmid,
            estado,
            t_fin=self._reloj.ahora(),
            upid=upid,
            error=error,
            log=res.log_tarea,
            avisos=avisos,
        )
        self._registrar(libro, entrada)
        self._emitir(c, entrada)
        self._evaluar_pausa(c, entrada)
        return (
            entrada.estado == EstadoMV.ERROR
            and error is not None
            and error.codigo == CodigoError.NODO_NO_DISPONIBLE
        )

    def _evaluar_pausa(self, c: _Corrida, entrada: EntradaLibro) -> None:
        """Alimenta la política de pausa y pausa el lote si corresponde (RF-L14, E-L09)."""
        for causa in c.control.causas_ignoradas:
            c.politica.ignorar(causa)
        error = entrada.error
        estado = entrada.estado
        motivo: MotivoPausa | None = None
        if estado in (EstadoMV.OK, EstadoMV.CON_AVISOS):
            motivo = c.politica.registrar(None)
        elif error is not None and error.codigo != CodigoError.NODO_NO_DISPONIBLE:
            motivo = c.politica.registrar(error)
        if motivo is not None:
            c.control.pausar(motivo, error)
        elif estado == EstadoMV.CONEXION_PERDIDA and entrada.upid is not None:
            # Pérdida sostenida con una tarea en vuelo: no se envía nada más (E-L09).
            c.control.pausar(MotivoPausa.CONEXION, error)

    def _emitir(self, c: _Corrida, entrada: EntradaLibro) -> None:
        """Avisa al observador sin dejar que un fallo suyo afecte al lote."""
        try:
            c.observador(entrada)
        except Exception:
            _log.exception("El observador del lote falló (vmid=%s)", entrada.elemento.vmid)

    @staticmethod
    def _registrar(libro: Libro, entrada: EntradaLibro) -> None:
        """Línea de registro por MV (RF-L20): sin secretos, detalle enmascarado y acotado."""
        error = entrada.error
        _log.info(
            "Lote %s: vmid=%s nodo=%s upid=%s estado=%s codigo=%s detalle=%s",
            libro.id_lote,
            entrada.elemento.vmid,
            entrada.elemento.nodo,
            entrada.upid,
            entrada.estado,
            error.codigo if error else "-",
            enmascarar(error.detalle_tecnico)[:_MAX_DETALLE_LOG] if error else "-",
        )

    # --- Comprobación de dudosas ------------------------------------------------------

    def _comprobar_una(
        self, libro: Libro, entrada: EntradaLibro, observador: Observador, control: ControlLote
    ) -> None:
        elemento = entrada.elemento
        try:
            servicio = self._fabrica(self._sesion, self._reloj)
            if entrada.upid is not None:
                res = servicio.comprobar_ahora(elemento.cfg, entrada.upid)
                estado = _ESTADO_POR_DESENLACE.get(res.desenlace, EstadoMV.CONEXION_PERDIDA)
                terminal = estado not in ESTADOS_DUDOSOS
                nueva = libro.resolver(
                    elemento.vmid,
                    estado,
                    t_fin=self._reloj.ahora() if terminal else None,
                    upid=entrada.upid,
                    error=res.error,
                    log=res.log_tarea,
                )
            else:
                estado, aviso, error = reconciliar_incierta(
                    servicio,
                    elemento.cfg,
                    self._reloj,
                    control.cancelado,
                    id_lote=libro.id_lote,
                    etiquetar=libro.plan.definicion.etiquetar,
                    cliente=self._sesion.cliente,
                )
                nueva = libro.resolver(
                    elemento.vmid,
                    estado,
                    t_fin=self._reloj.ahora() if estado not in ESTADOS_DUDOSOS else None,
                    error=error,
                    avisos=(aviso,) if aviso else (),
                )
        except Exception:
            _log.exception("Fallo al comprobar la MV dudosa (vmid=%s)", elemento.vmid)
            return
        self._registrar(libro, nueva)
        try:
            observador(nueva)
        except Exception:
            _log.exception("El observador del lote falló (vmid=%s)", elemento.vmid)
