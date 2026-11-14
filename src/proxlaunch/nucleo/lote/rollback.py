"""Rollback del lote: deshacer lo creado (RF-L18, D-20 (1)).

Acción manual con confirmación. Solo actúa sobre MVs del libro (INV-L4) y antes de cada
``DELETE`` vuelve a comprobar propiedad, protección, bloqueo y encendido. Nunca reintenta
un ``DELETE`` a ciegas: ante la duda lee la configuración y, si sigue existiendo, informa
``INCIERTA``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from proxlaunch.nucleo.api.traductor_errores import CODIGOS_DE_RED
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import MAX_NODOS_PARALELOS
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    CandidatoRollback,
    EntradaLibro,
    EstadoMV,
    EstadoRollback,
    MotivoPausa,
    ResultadoRollback,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.politica_pausa import es_error_global
from proxlaunch.nucleo.lote.reconciliacion import (
    AVISO_CREADA_TRAS_COMPROBAR,
    tiene_etiqueta_del_lote,
)
from proxlaunch.nucleo.registro import enmascarar
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.servicios.creacion import (
    INTERVALO_SONDEO_S,
    MAX_ESPERA_S,
    TOLERANCIA_RED_S,
)

_log = logging.getLogger("proxlaunch.lote.rollback")

ESTADOS_ELEGIBLES = frozenset({EstadoMV.OK, EstadoMV.CON_AVISOS, EstadoMV.PARCIAL})
ESTADOS_INCOMPLETOS = frozenset({EstadoMV.CON_AVISOS, EstadoMV.PARCIAL})
MOTIVO_PROPIEDAD_NO_DEMOSTRADA = "propiedad_no_demostrada"
_MAX_DETALLE_LOG = 300

ObservadorRollback = Callable[[ResultadoRollback], None]


def _verdadero(valor: Any) -> bool:
    return str(valor).strip().lower() in ("1", "true", "yes", "on")


class ServicioRollback:
    """Calcula las MVs elegibles y las elimina con las garantías de RF-L18."""

    def __init__(
        self,
        sesion: Sesion,
        reloj: Reloj,
        *,
        max_nodos: int = MAX_NODOS_PARALELOS,
        intervalo_s: float = INTERVALO_SONDEO_S,
        max_espera_s: float = MAX_ESPERA_S,
        tolerancia_red_s: float = TOLERANCIA_RED_S,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._max_nodos = max(1, max_nodos)
        self._intervalo = intervalo_s
        self._max_espera = max_espera_s
        self._tolerancia_red = tolerancia_red_s

    # --- Elegibilidad -----------------------------------------------------------------

    def elegibles(self, libro: Libro, *, etiquetado: bool) -> list[CandidatoRollback]:
        """Un candidato por cada MV del libro, en el orden del plan (CA-L18.1/18.2).

        Elegibles: ``OK``, ``CON_AVISOS`` y ``PARCIAL``. El motivo de las no elegibles es el
        valor de ``EstadoMV`` que lo impide (``no_enviada``, ``error``, ``no_creada_segura``,
        ``existe_sin_confirmar_propiedad``, ``conexion_perdida``...). Con ``etiquetado`` falso,
        una MV rescatada por reconciliación (sin UPID propio ni etiqueta que la ate al lote)
        tiene la propiedad sin demostrar y no es elegible (``propiedad_no_demostrada``).

        ``incompleta`` es verdadera para ``PARCIAL`` y ``CON_AVISOS`` (la tarea no terminó
        limpia) y para las rescatadas por reconciliación; es falsa para ``OK`` limpio.
        """
        candidatos: list[CandidatoRollback] = []
        for entrada in libro.instantanea():
            rescatada = AVISO_CREADA_TRAS_COMPROBAR in entrada.avisos
            elegible = entrada.estado in ESTADOS_ELEGIBLES
            motivo: str | None = None if elegible else entrada.estado.value
            if elegible and rescatada and entrada.upid is None and not etiquetado:
                elegible = False
                motivo = MOTIVO_PROPIEDAD_NO_DEMOSTRADA
            incompleta = elegible and (entrada.estado in ESTADOS_INCOMPLETOS or rescatada)
            candidatos.append(CandidatoRollback(entrada, elegible, motivo, incompleta))
        return candidatos

    # --- Ejecución --------------------------------------------------------------------

    def deshacer(
        self,
        candidatos: list[CandidatoRollback],
        observador: ObservadorRollback,
        control: ControlLote,
        *,
        id_lote: str,
        etiquetado: bool,
    ) -> list[ResultadoRollback]:
        """Elimina las MVs elegibles (las no elegibles se ignoran). Bloqueante.

        Como máximo un ``DELETE`` a la vez por nodo y ``max_nodos`` nodos en paralelo.
        Devuelve un resultado por candidato elegible, en el orden recibido. Usa un
        ``ControlLote`` nuevo (uno cancelado no se rearma). Un 403 (u otro error global)
        detiene el rollback: ``control.pausar(ERROR_GLOBAL, error)`` y las demás MVs quedan
        ``NO_ENVIADA`` (CA-L18.9).
        """
        pendientes = [c for c in candidatos if c.elegible and c.entrada.estado in ESTADOS_ELEGIBLES]
        resultados: dict[int, ResultadoRollback] = {}
        cerrojo = threading.Lock()
        detener = threading.Event()
        colas: dict[str, list[CandidatoRollback]] = {}
        for candidato in pendientes:
            colas.setdefault(candidato.entrada.elemento.nodo, []).append(candidato)
        if not colas:
            return []

        def emitir(resultado: ResultadoRollback) -> None:
            with cerrojo:
                resultados[resultado.vmid] = resultado
            try:
                observador(resultado)
            except Exception:
                _log.exception("El observador del rollback falló (vmid=%s)", resultado.vmid)

        def procesar_cola(cola: list[CandidatoRollback]) -> None:
            for posicion, candidato in enumerate(cola):
                if control.cancelado.is_set() or detener.is_set():
                    for resto in cola[posicion:]:
                        emitir(self._resultado(resto.entrada, EstadoRollback.NO_ENVIADA))
                    return
                emitir(
                    self._procesar(candidato.entrada, id_lote, etiquetado, control, detener, emitir)
                )

        trabajadores = max(1, min(self._max_nodos, len(colas)))
        with ThreadPoolExecutor(max_workers=trabajadores, thread_name_prefix="rollback") as pool:
            futuros = [pool.submit(procesar_cola, cola) for cola in colas.values()]
        for futuro in futuros:
            if (exc := futuro.exception()) is not None:
                raise exc
        return [resultados[c.entrada.elemento.vmid] for c in pendientes]

    # --- Una MV -----------------------------------------------------------------------

    @staticmethod
    def _resultado(
        entrada: EntradaLibro,
        estado: EstadoRollback,
        *,
        upid: str | None = None,
        error: ErrorProxLaunch | None = None,
    ) -> ResultadoRollback:
        el = entrada.elemento
        return ResultadoRollback(el.vmid, el.nodo, el.nombre, estado, upid, error)

    @staticmethod
    def _error(
        codigo: CodigoError, entrada: EntradaLibro, detalle: str = "", **extra: str
    ) -> ErrorProxLaunch:
        el = entrada.elemento
        params = {"nombre": el.nombre, "vmid": str(el.vmid), "nodo": el.nodo, **extra}
        return ErrorProxLaunch(codigo, params, detalle)

    def _fallo_de(
        self,
        e: ErrorProxLaunch,
        entrada: EntradaLibro,
        control: ControlLote,
        detener: threading.Event,
    ) -> ResultadoRollback:
        """Un error definitivo al comprobar o eliminar: FALLO (y parada si es global)."""
        el = entrada.elemento
        if e.codigo == CodigoError.PERMISO_INSUFICIENTE and not e.params.get("privilegio"):
            e.params["privilegio"] = "VM.Allocate"
            e.params["ruta"] = f"/vms/{el.vmid}"
            e.params["inferido"] = "1"
        if e.codigo == CodigoError.PERMISO_INSUFICIENTE or es_error_global(e):
            detener.set()
            control.pausar(MotivoPausa.ERROR_GLOBAL, e)
            return self._resultado(entrada, EstadoRollback.FALLO, error=e)
        error = self._error(
            CodigoError.ROLLBACK_FALLO, entrada, e.detalle_tecnico, causa=str(e.codigo)
        )
        return self._resultado(entrada, EstadoRollback.FALLO, error=error)

    def _procesar(
        self,
        entrada: EntradaLibro,
        id_lote: str,
        etiquetado: bool,
        control: ControlLote,
        detener: threading.Event,
        emitir: ObservadorRollback,
    ) -> ResultadoRollback:
        el = entrada.elemento
        cliente = self._sesion.cliente
        emitir(self._resultado(entrada, EstadoRollback.COMPROBANDO))

        # 1. Comprobaciones previas: existe, es propia, no está protegida, bloqueada ni encendida.
        try:
            config = cliente.config_vm(el.nodo, el.vmid)
            if config is None:
                return self._resultado(entrada, EstadoRollback.YA_NO_EXISTIA)
            omision = self._motivo_omision(config, entrada, id_lote, etiquetado)
            if omision is None:
                estado_vm = cliente.estado_actual_vm(el.nodo, el.vmid)
                omision = self._motivo_omision_estado(estado_vm, entrada)
        except ErrorProxLaunch as e:
            return self._fallo_de(e, entrada, control, detener)
        except Exception as exc:
            _log.exception("Fallo inesperado al comprobar la MV (vmid=%s)", el.vmid)
            error = self._error(CodigoError.ROLLBACK_FALLO, entrada, type(exc).__name__)
            return self._resultado(entrada, EstadoRollback.FALLO, error=error)
        if omision is not None:
            return self._resultado(entrada, EstadoRollback.OMITIDA, error=omision)
        if control.cancelado.is_set() or detener.is_set():
            return self._resultado(entrada, EstadoRollback.NO_ENVIADA)

        # 2. DELETE. Una sola vez: un fallo incierto se resuelve leyendo, no reenviando.
        _log.info("Rollback: eliminando vmid=%s nodo=%s lote=%s", el.vmid, el.nodo, id_lote)
        try:
            upid = cliente.eliminar_vm(el.nodo, el.vmid)
        except ErrorProxLaunch as e:
            if e.codigo in CODIGOS_DE_RED:
                return self._resolver_incierta(entrada, None)
            return self._fallo_de(e, entrada, control, detener)
        except Exception:
            _log.exception("Fallo inesperado al enviar el DELETE (vmid=%s)", el.vmid)
            return self._resolver_incierta(entrada, None)
        emitir(self._resultado(entrada, EstadoRollback.ELIMINANDO, upid=upid))

        # 3. Sondeo de la tarea de borrado.
        exitstatus = self._sondear(el.nodo, upid, control.evento_abandono)
        if exitstatus is None:
            return self._resolver_incierta(entrada, upid)
        if exitstatus == "OK" or exitstatus.upper().startswith("WARNINGS"):
            return self._resultado(entrada, EstadoRollback.ELIMINADA, upid=upid)
        detalle = enmascarar(exitstatus)[:_MAX_DETALLE_LOG]
        error = self._error(CodigoError.ROLLBACK_FALLO, entrada, detalle, causa="tarea")
        return self._resultado(entrada, EstadoRollback.FALLO, upid=upid, error=error)

    def _motivo_omision(
        self, config: dict[str, Any], entrada: EntradaLibro, id_lote: str, etiquetado: bool
    ) -> ErrorProxLaunch | None:
        el = entrada.elemento
        nombre = config.get("name")
        propia = tiene_etiqueta_del_lote(config, id_lote) if etiquetado else True
        if not propia or (isinstance(nombre, str) and nombre and nombre != el.nombre):
            return self._error(CodigoError.ROLLBACK_NO_PROPIA, entrada)
        if _verdadero(config.get("protection", 0)) or config.get("lock"):
            return self._error(CodigoError.ROLLBACK_BLOQUEADA, entrada)
        return None

    def _motivo_omision_estado(
        self, estado_vm: dict[str, Any], entrada: EntradaLibro
    ) -> ErrorProxLaunch | None:
        if str(estado_vm.get("status", "")).lower() == "running":
            return self._error(CodigoError.ROLLBACK_ENCENDIDA, entrada)
        if estado_vm.get("lock"):
            return self._error(CodigoError.ROLLBACK_BLOQUEADA, entrada)
        return None

    def _sondear(self, nodo: str, upid: str, abandono: threading.Event) -> str | None:
        """Espera a que termine la tarea y devuelve su ``exitstatus``; ``None`` si no se pudo
        saber (tiempo agotado, abandono, pérdida sostenida o error ajeno a la tarea)."""
        cliente = self._sesion.cliente
        inicio = self._reloj.ahora()
        primer_fallo: float | None = None
        while True:
            if abandono.is_set():
                return None
            try:
                estado = cliente.estado_tarea(nodo, upid)
            except ErrorProxLaunch as e:
                if e.codigo not in CODIGOS_DE_RED:
                    return None
                ahora = self._reloj.ahora()
                if primer_fallo is None:
                    primer_fallo = ahora
                elif ahora - primer_fallo > self._tolerancia_red:
                    return None
            except Exception:
                _log.exception("Fallo inesperado al sondear la tarea de borrado")
                return None
            else:
                primer_fallo = None
                if estado.terminada:
                    return (estado.exitstatus or "").strip()
            if self._reloj.ahora() - inicio >= self._max_espera:
                return None
            self._reloj.dormir(self._intervalo)

    def _resolver_incierta(self, entrada: EntradaLibro, upid: str | None) -> ResultadoRollback:
        """No se sabe cómo terminó el DELETE: ``config_vm`` decide (sin reintento, E-L22)."""
        el = entrada.elemento
        try:
            config = self._sesion.cliente.config_vm(el.nodo, el.vmid)
        except Exception:
            config = {}
        if config is None:
            return self._resultado(entrada, EstadoRollback.ELIMINADA, upid=upid)
        error = self._error(CodigoError.ROLLBACK_INCIERTO, entrada)
        return self._resultado(entrada, EstadoRollback.INCIERTA, upid=upid, error=error)
