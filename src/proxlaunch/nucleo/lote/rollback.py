"""Rollback del lote: deshacer lo creado (RF-L18, D-20 (1)).

Acción manual con confirmación. Solo actúa sobre MVs del libro (INV-L4) y antes de cada
``DELETE`` vuelve a comprobar propiedad, protección, bloqueo y encendido. Nunca reintenta
un ``DELETE`` a ciegas: ante la duda lee la configuración y, si sigue existiendo, informa
``INCIERTA``.

Fase A (RF-A1.5, RF-A6.3, RF-A6.4): con ``forzar_apagado`` y ``forzar_desproteccion`` (los
VMIDs que el usuario confirmó expresamente tras ``inspeccionar``) también apaga a la fuerza esas
MVs propias encendidas y les quita la protección antes del ``DELETE``. Una MV encendida o
protegida que no esté en su conjunto se omite como sin forzar (SEG-A-01). Un ``lock`` nunca se
fuerza y una MV no propia nunca se toca.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Collection, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
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
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.origen import DetalleClon
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.origen.permisos import estado_privilegio
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

# Acciones realizadas sobre una MV (``ResultadoRollback.acciones``).
ACCION_APAGADA = "apagada"
ACCION_DESPROTEGIDA = "desprotegida"
ACCION_BORRADA = "borrada"
PRIVILEGIO_ENCENDIDO = "VM.PowerMgmt"
PRIVILEGIO_OPCIONES = "VM.Config.Options"

ObservadorRollback = Callable[[ResultadoRollback], None]


@dataclass(frozen=True)
class InspeccionRollback:
    """Resultado de solo lectura de ``inspeccionar`` (alimenta la confirmación expresa)."""

    # Forzables: VMIDs propios encendidos / protegidos cuyo privilegio es conocido o se desconoce.
    encendidas: tuple[int, ...] = ()  # en ``running``
    protegidas: tuple[int, ...] = ()  # con ``protection=1``
    # Encendidas / protegidas que se omitirán porque se sabe que falta el privilegio.
    encendidas_sin_privilegio: tuple[int, ...] = ()
    protegidas_sin_privilegio: tuple[int, ...] = ()
    # Candidatos cuyo estado no se pudo leer (ya no se descartan en silencio, QA-A-01).
    ilegibles: tuple[int, ...] = ()
    # Nombre del plan de cada VMID mencionado arriba, para listarlas en la confirmación.
    nombres: Mapping[int, str] = field(default_factory=dict)

    @property
    def hay_forzables(self) -> bool:
        return bool(self.encendidas or self.protegidas)

    @property
    def hay_algo_que_avisar(self) -> bool:
        """Hay algo que mostrar al usuario antes de borrar (forzables, omisiones o ilegibles)."""
        return bool(
            self.encendidas
            or self.protegidas
            or self.encendidas_sin_privilegio
            or self.protegidas_sin_privilegio
            or self.ilegibles
        )


def _verdadero(valor: Any) -> bool:
    return str(valor).strip().lower() in ("1", "true", "yes", "on")


def _ya_parada(texto: str) -> bool:
    """El ``stop`` respondió que la MV no estaba en marcha (cuenta como éxito)."""
    return "not running" in texto.lower()


def _vmid_de_plantilla(entrada: EntradaLibro) -> int | None:
    """VMID de la plantilla de la que se clonó la MV (``None`` si no es un clon)."""
    detalle = entrada.elemento.cfg.detalle_origen
    if entrada.elemento.cfg.origen == OrigenSO.CLONAR_PLANTILLA and isinstance(
        detalle, DetalleClon
    ):
        return detalle.plantilla.vmid
    return None


def es_propia(
    config: Mapping[str, Any], entrada: EntradaLibro, id_lote: str, etiquetado: bool
) -> bool:
    """Regla de propiedad antes de borrar (RF-L18, D-21; ampliada en MVP 4, C2).

    - Nunca se borra el VMID de la plantilla de un clon.
    - Con ``etiquetado``: la MV lleva la etiqueta del lote (y, si tiene nombre, es el del plan).
      Un CLON sin etiqueta (el ``PUT`` de etiquetas pudo fallar, DT-O14, CA-O22.5) también es
      propia si la creó una tarea nuestra (UPID propio), no fue rescatada por reconciliación y
      su ``name`` es exactamente el del plan.
    - Sin ``etiquetado``: solo la prueba del nombre (str e igual al del plan).
    """
    el = entrada.elemento
    if _vmid_de_plantilla(entrada) == el.vmid:
        return False
    nombre = config.get("name")
    nombre_igual = isinstance(nombre, str) and nombre == el.nombre
    if not etiquetado:
        return nombre_igual
    if tiene_etiqueta_del_lote(dict(config), id_lote):
        return not (isinstance(nombre, str) and nombre and nombre != el.nombre)
    if el.cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        rescatada = AVISO_CREADA_TRAS_COMPROBAR in entrada.avisos
        return entrada.upid is not None and not rescatada and nombre_igual
    return False


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

    def elegibles(
        self, libro: Libro, *, etiquetado: bool, excluir_vmids: Collection[int] = ()
    ) -> list[CandidatoRollback]:
        """Un candidato por cada MV del libro, en el orden del plan (CA-L18.1/18.2).

        ``excluir_vmids`` quita del resultado esos VMIDs (la interfaz pasa los ya
        ``ELIMINADA``/``YA_NO_EXISTIA`` de un intento anterior).

        Elegibles: ``OK``, ``CON_AVISOS`` y ``PARCIAL``. El motivo de las no elegibles es el
        valor de ``EstadoMV`` que lo impide (``no_enviada``, ``error``, ``no_creada_segura``,
        ``existe_sin_confirmar_propiedad``, ``conexion_perdida``...). Con ``etiquetado`` falso
        no hay etiqueta que ate la MV al lote: solo es elegible si la creó una tarea nuestra
        (entrada con UPID propio) y no fue rescatada por reconciliación; si no, la propiedad
        no está demostrada (``propiedad_no_demostrada``).

        ``incompleta`` es verdadera para ``PARCIAL`` y ``CON_AVISOS`` (la tarea no terminó
        limpia) y para las rescatadas por reconciliación; es falsa para ``OK`` limpio.
        """
        candidatos: list[CandidatoRollback] = []
        excluidos = frozenset(excluir_vmids)
        for entrada in libro.instantanea():
            if entrada.elemento.vmid in excluidos:
                continue
            rescatada = AVISO_CREADA_TRAS_COMPROBAR in entrada.avisos
            elegible = entrada.estado in ESTADOS_ELEGIBLES
            motivo: str | None = None if elegible else entrada.estado.value
            if elegible and not etiquetado and (rescatada or entrada.upid is None):
                elegible = False
                motivo = MOTIVO_PROPIEDAD_NO_DEMOSTRADA
            incompleta = elegible and (entrada.estado in ESTADOS_INCOMPLETOS or rescatada)
            candidatos.append(CandidatoRollback(entrada, elegible, motivo, incompleta))
        return candidatos

    def inspeccionar(
        self,
        candidatos: list[CandidatoRollback],
        *,
        id_lote: str,
        etiquetado: bool,
        permisos: PermisosEfectivos | None = None,
    ) -> InspeccionRollback:
        """Cuenta las MVs propias encendidas y protegidas entre los candidatos elegibles.

        Solo hace ``GET`` (config y estado actual). Se ignoran las que no son propias, las que
        tienen ``lock`` (nunca se fuerzan) y las que ya no existen. Las que no se pueden leer
        van en ``ilegibles``. Con ``permisos``, las encendidas (``VM.PowerMgmt``) o protegidas
        (``VM.Config.Options``) cuyo privilegio es ``False`` van aparte, como «sin privilegio»;
        con ``None`` (o privilegio desconocido) son forzables. Pensada para un trabajador:
        bloqueante y sin efectos.
        """
        encendidas: list[int] = []
        protegidas: list[int] = []
        encendidas_sin: list[int] = []
        protegidas_sin: list[int] = []
        ilegibles: list[int] = []
        nombres: dict[int, str] = {}
        cliente = self._sesion.cliente
        for c in candidatos:
            if not (c.elegible and c.entrada.estado in ESTADOS_ELEGIBLES):
                continue
            el = c.entrada.elemento
            try:
                config = cliente.config_vm(el.nodo, el.vmid)
                if config is None or not es_propia(config, c.entrada, id_lote, etiquetado):
                    continue
                if config.get("lock"):
                    continue
                estado_vm = cliente.estado_actual_vm(el.nodo, el.vmid)
            except Exception:
                _log.warning("Inspección del rollback: no se pudo leer vmid=%s", el.vmid)
                ilegibles.append(el.vmid)
                nombres[el.vmid] = el.nombre
                continue
            if estado_vm.get("lock"):
                continue
            ruta = f"/vms/{el.vmid}"
            if _verdadero(config.get("protection", 0)):
                sin = estado_privilegio(permisos, PRIVILEGIO_OPCIONES, ruta) is False
                (protegidas_sin if sin else protegidas).append(el.vmid)
                nombres[el.vmid] = el.nombre
            if str(estado_vm.get("status", "")).lower() == "running":
                sin = estado_privilegio(permisos, PRIVILEGIO_ENCENDIDO, ruta) is False
                (encendidas_sin if sin else encendidas).append(el.vmid)
                nombres[el.vmid] = el.nombre
        return InspeccionRollback(
            tuple(encendidas),
            tuple(protegidas),
            tuple(encendidas_sin),
            tuple(protegidas_sin),
            tuple(ilegibles),
            nombres,
        )

    # --- Ejecución --------------------------------------------------------------------

    def deshacer(
        self,
        candidatos: list[CandidatoRollback],
        observador: ObservadorRollback,
        control: ControlLote,
        *,
        id_lote: str,
        etiquetado: bool,
        forzar_apagado: frozenset[int] = frozenset(),
        forzar_desproteccion: frozenset[int] = frozenset(),
        permisos: PermisosEfectivos | None = None,
    ) -> list[ResultadoRollback]:
        """Elimina las MVs elegibles (las no elegibles se ignoran). Bloqueante.

        ``forzar_apagado`` y ``forzar_desproteccion`` (VMIDs confirmados expresamente tras
        ``inspeccionar``, RF-A6.4): una MV propia encendida que esté en el primero se apaga a
        la fuerza (``stop``, se espera la tarea) y una protegida que esté en el segundo pierde
        ``protection`` con un ``PUT``; después ``DELETE``. ``ResultadoRollback.acciones`` lo
        registra. Una MV encendida o protegida que NO esté en su conjunto (p. ej. se encendió
        mientras el usuario leía la confirmación) se omite con ``ROLLBACK_ENCENDIDA`` o
        ``ROLLBACK_PROTEGIDA``, igual que sin forzar. ``permisos`` decide los saltos: un
        privilegio en ``False`` omite la MV con ``ROLLBACK_SIN_POWERMGMT`` o
        ``ROLLBACK_SIN_OPCIONES`` (faltan ambos: el segundo va en ``params['tambien']``); con
        ``None`` (desconocido) se intenta. Tras el ``stop`` y tras el ``PUT`` se relee la
        configuración y se vuelve a comprobar propiedad y ``lock`` antes del paso siguiente
        (QA-A-07). El ``lock`` nunca se fuerza.

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
                if self._detenido(control, detener):
                    for resto in cola[posicion:]:
                        emitir(self._resultado(resto.entrada, EstadoRollback.NO_ENVIADA))
                    return
                emitir(
                    self._procesar(
                        candidato.entrada,
                        id_lote,
                        etiquetado,
                        control,
                        detener,
                        emitir,
                        forzar_apagado,
                        forzar_desproteccion,
                        permisos,
                    )
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
    def _detenido(control: ControlLote, detener: threading.Event) -> bool:
        """Cancelado, en pausa (p. ej. error global de otro grupo) o detenido: no más DELETE."""
        return control.cancelado.is_set() or detener.is_set() or control.motivo_pausa is not None

    @staticmethod
    def _resultado(
        entrada: EntradaLibro,
        estado: EstadoRollback,
        *,
        upid: str | None = None,
        error: ErrorProxLaunch | None = None,
        acciones: tuple[str, ...] = (),
    ) -> ResultadoRollback:
        el = entrada.elemento
        return ResultadoRollback(el.vmid, el.nodo, el.nombre, estado, upid, error, acciones)

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
        acciones: tuple[str, ...] = (),
    ) -> ResultadoRollback:
        """Un error definitivo al comprobar o eliminar: FALLO (y parada si es global)."""
        el = entrada.elemento
        if e.codigo == CodigoError.RECURSO_INEXISTENTE:
            return self._resultado(entrada, EstadoRollback.YA_NO_EXISTIA, acciones=acciones)
        if e.codigo == CodigoError.PERMISO_INSUFICIENTE and not e.params.get("privilegio"):
            e.params["privilegio"] = "VM.Allocate"
            e.params["ruta"] = f"/vms/{el.vmid}"
            e.params["inferido"] = "1"
        if e.codigo == CodigoError.PERMISO_INSUFICIENTE or es_error_global(e):
            detener.set()
            control.pausar(MotivoPausa.ERROR_GLOBAL, e)
            return self._resultado(entrada, EstadoRollback.FALLO, error=e, acciones=acciones)
        error = self._error(
            CodigoError.ROLLBACK_FALLO, entrada, e.detalle_tecnico, causa=str(e.codigo)
        )
        return self._resultado(entrada, EstadoRollback.FALLO, error=error, acciones=acciones)

    def _procesar(
        self,
        entrada: EntradaLibro,
        id_lote: str,
        etiquetado: bool,
        control: ControlLote,
        detener: threading.Event,
        emitir: ObservadorRollback,
        forzar_apagado: frozenset[int] = frozenset(),
        forzar_desproteccion: frozenset[int] = frozenset(),
        permisos: PermisosEfectivos | None = None,
    ) -> ResultadoRollback:
        el = entrada.elemento
        cliente = self._sesion.cliente
        emitir(self._resultado(entrada, EstadoRollback.COMPROBANDO))

        # 1. Previas: existe, es propia, sin lock; protección y encendido según forzar
        try:
            config = cliente.config_vm(el.nodo, el.vmid)
            if config is None:
                return self._resultado(entrada, EstadoRollback.YA_NO_EXISTIA)
            omision = self._motivo_omision(config, entrada, id_lote, etiquetado)
            encendida = False
            if omision is None:
                estado_vm = cliente.estado_actual_vm(el.nodo, el.vmid)
                omision = self._motivo_omision_lock(estado_vm, entrada)
                encendida = str(estado_vm.get("status", "")).lower() == "running"
            protegida = _verdadero(config.get("protection", 0))
            if omision is None:
                omision = self._motivo_omision_forzado(
                    entrada,
                    encendida,
                    protegida,
                    el.vmid in forzar_apagado,
                    el.vmid in forzar_desproteccion,
                    permisos,
                )
        except ErrorProxLaunch as e:
            return self._fallo_de(e, entrada, control, detener)
        except Exception as exc:
            _log.exception("Fallo inesperado al comprobar la MV (vmid=%s)", el.vmid)
            error = self._error(CodigoError.ROLLBACK_FALLO, entrada, type(exc).__name__)
            return self._resultado(entrada, EstadoRollback.FALLO, error=error)
        if omision is not None:
            return self._resultado(entrada, EstadoRollback.OMITIDA, error=omision)
        if self._detenido(control, detener):
            return self._resultado(entrada, EstadoRollback.NO_ENVIADA)

        acciones: list[str] = []
        # 2. Apagado forzado (solo confirmado y si estaba encendida).
        if encendida:
            fallo = self._apagar(entrada, control, detener, acciones)
            if fallo is not None:
                return fallo
            # QA-A-07: pasó tiempo; se vuelve a comprobar propiedad y lock antes de seguir.
            fallo, protegida = self._revalidar(
                entrada, id_lote, etiquetado, control, detener, acciones,
                el.vmid in forzar_desproteccion,
            )  # fmt: skip
            if fallo is not None:
                return fallo
        # 3. Quitar la protección (solo confirmada y si estaba protegida).
        if protegida:
            fallo = self._desproteger(entrada, control, detener, acciones)
            if fallo is not None:
                return fallo
            fallo, _ = self._revalidar(
                entrada, id_lote, etiquetado, control, detener, acciones, True
            )
            if fallo is not None:
                return fallo

        # 4. DELETE. Una sola vez: un fallo incierto se resuelve leyendo, no reenviando.
        _log.info("Rollback: eliminando vmid=%s nodo=%s lote=%s", el.vmid, el.nodo, id_lote)
        previas = tuple(acciones)
        try:
            upid = cliente.eliminar_vm(el.nodo, el.vmid)
        except ErrorProxLaunch as e:
            if e.codigo in CODIGOS_DE_RED:
                return self._resolver_incierta(entrada, None, previas)
            return self._fallo_de(e, entrada, control, detener, previas)
        except Exception:
            _log.exception("Fallo inesperado al enviar el DELETE (vmid=%s)", el.vmid)
            return self._resolver_incierta(entrada, None, previas)
        emitir(self._resultado(entrada, EstadoRollback.ELIMINANDO, upid=upid, acciones=previas))

        # 5. Sondeo de la tarea de borrado.
        exitstatus = self._sondear(el.nodo, upid, control.evento_abandono)
        if exitstatus is None:
            return self._resolver_incierta(entrada, upid, previas)
        if exitstatus == "OK" or exitstatus.upper().startswith("WARNINGS"):
            return self._resultado(
                entrada,
                EstadoRollback.ELIMINADA,
                upid=upid,
                acciones=(*previas, ACCION_BORRADA),
            )
        detalle = enmascarar(exitstatus)[:_MAX_DETALLE_LOG]
        error = self._error(CodigoError.ROLLBACK_FALLO, entrada, detalle, causa="tarea")
        return self._resultado(
            entrada, EstadoRollback.FALLO, upid=upid, error=error, acciones=previas
        )

    def _apagar(
        self,
        entrada: EntradaLibro,
        control: ControlLote,
        detener: threading.Event,
        acciones: list[str],
    ) -> ResultadoRollback | None:
        """``stop`` + espera de la tarea. ``None`` si quedó apagada; si no, el resultado del fallo.

        Un «not running» (la MV ya estaba parada) cuenta como éxito (CA-A1.5.8).
        """
        el = entrada.elemento
        if self._detenido(control, detener):
            return self._resultado(entrada, EstadoRollback.NO_ENVIADA, acciones=tuple(acciones))
        _log.info("Rollback: apagando a la fuerza vmid=%s nodo=%s", el.vmid, el.nodo)
        try:
            upid = self._sesion.cliente.detener_vm(el.nodo, el.vmid)
        except ErrorProxLaunch as e:
            if _ya_parada(e.detalle_tecnico):
                acciones.append(ACCION_APAGADA)
                return None
            return self._fallo_paso(
                e, entrada, control, detener, acciones, CodigoError.ROLLBACK_APAGADO_FALLIDO,
                PRIVILEGIO_ENCENDIDO,
            )  # fmt: skip
        except Exception as exc:
            _log.exception("Fallo inesperado al apagar la MV (vmid=%s)", el.vmid)
            error = self._error(
                CodigoError.ROLLBACK_APAGADO_FALLIDO,
                entrada,
                type(exc).__name__,
                causa="inesperado",
            )
            return self._resultado(
                entrada, EstadoRollback.FALLO, error=error, acciones=tuple(acciones)
            )
        exitstatus = self._sondear(el.nodo, upid, control.evento_abandono)
        if exitstatus is not None and (
            exitstatus == "OK"
            or exitstatus.upper().startswith("WARNINGS")
            or _ya_parada(exitstatus)
        ):
            acciones.append(ACCION_APAGADA)
            return None
        detalle = enmascarar(exitstatus or "sin_resultado")[:_MAX_DETALLE_LOG]
        error = self._error(CodigoError.ROLLBACK_APAGADO_FALLIDO, entrada, detalle, causa="tarea")
        return self._resultado(
            entrada, EstadoRollback.FALLO, upid=upid, error=error, acciones=tuple(acciones)
        )

    def _desproteger(
        self,
        entrada: EntradaLibro,
        control: ControlLote,
        detener: threading.Event,
        acciones: list[str],
    ) -> ResultadoRollback | None:
        """``PUT protection=0``. ``None`` si se quitó; si no, el resultado del fallo."""
        el = entrada.elemento
        if self._detenido(control, detener):
            return self._resultado(entrada, EstadoRollback.NO_ENVIADA, acciones=tuple(acciones))
        _log.info("Rollback: quitando la protección de vmid=%s nodo=%s", el.vmid, el.nodo)
        try:
            self._sesion.cliente.configurar_vm(el.nodo, el.vmid, {"protection": "0"})
        except ErrorProxLaunch as e:
            return self._fallo_paso(
                e, entrada, control, detener, acciones, CodigoError.ROLLBACK_DESPROTECCION_FALLIDA,
                PRIVILEGIO_OPCIONES,
            )  # fmt: skip
        except Exception as exc:
            _log.exception("Fallo inesperado al desproteger la MV (vmid=%s)", el.vmid)
            error = self._error(
                CodigoError.ROLLBACK_DESPROTECCION_FALLIDA,
                entrada,
                type(exc).__name__,
                causa="inesperado",
            )
            return self._resultado(
                entrada, EstadoRollback.FALLO, error=error, acciones=tuple(acciones)
            )
        acciones.append(ACCION_DESPROTEGIDA)
        return None

    def _fallo_paso(
        self,
        e: ErrorProxLaunch,
        entrada: EntradaLibro,
        control: ControlLote,
        detener: threading.Event,
        acciones: list[str],
        codigo: CodigoError,
        privilegio: str,
    ) -> ResultadoRollback:
        """Falla un paso previo al ``DELETE``: no se borra. Un 403 solo omite la MV."""
        hechas = tuple(acciones)
        if e.codigo == CodigoError.RECURSO_INEXISTENTE:
            return self._resultado(entrada, EstadoRollback.YA_NO_EXISTIA, acciones=hechas)
        if e.codigo == CodigoError.PERMISO_INSUFICIENTE:
            # Falta de privilegio en este paso: solo se omite esta MV (CA-A1.5.3, CA-A6.3.3).
            omision = (
                CodigoError.ROLLBACK_SIN_POWERMGMT
                if privilegio == PRIVILEGIO_ENCENDIDO
                else CodigoError.ROLLBACK_SIN_OPCIONES
            )
            error = self._error(omision, entrada, e.detalle_tecnico, privilegio=privilegio)
            return self._resultado(entrada, EstadoRollback.OMITIDA, error=error, acciones=hechas)
        if es_error_global(e):
            detener.set()
            control.pausar(MotivoPausa.ERROR_GLOBAL, e)
            return self._resultado(entrada, EstadoRollback.FALLO, error=e, acciones=hechas)
        error = self._error(codigo, entrada, e.detalle_tecnico, causa=str(e.codigo))
        return self._resultado(entrada, EstadoRollback.FALLO, error=error, acciones=hechas)

    def _revalidar(
        self,
        entrada: EntradaLibro,
        id_lote: str,
        etiquetado: bool,
        control: ControlLote,
        detener: threading.Event,
        acciones: list[str],
        desproteccion_confirmada: bool,
    ) -> tuple[ResultadoRollback | None, bool]:
        """Relee la configuración tras un paso destructivo y revalida la MV (QA-A-07).

        Devuelve ``(resultado, protegida)``: con ``resultado`` no nulo se detiene el borrado
        (omitida, ya inexistente o fallo); ``protegida`` es el estado actual de la protección.
        Una protección nueva sin confirmar omite la MV (``ROLLBACK_PROTEGIDA``).
        """
        el = entrada.elemento
        hechas = tuple(acciones)
        try:
            config = self._sesion.cliente.config_vm(el.nodo, el.vmid)
            if config is None:
                return self._resultado(
                    entrada, EstadoRollback.YA_NO_EXISTIA, acciones=hechas
                ), False
            omision = self._motivo_omision(config, entrada, id_lote, etiquetado)
            protegida = _verdadero(config.get("protection", 0))
            if omision is None and protegida and not desproteccion_confirmada:
                omision = self._error(CodigoError.ROLLBACK_PROTEGIDA, entrada)
        except ErrorProxLaunch as e:
            return self._fallo_de(e, entrada, control, detener, hechas), False
        except Exception as exc:
            _log.exception("Fallo inesperado al revalidar la MV (vmid=%s)", el.vmid)
            error = self._error(CodigoError.ROLLBACK_FALLO, entrada, type(exc).__name__)
            return self._resultado(
                entrada, EstadoRollback.FALLO, error=error, acciones=hechas
            ), False
        if omision is not None:
            return self._resultado(
                entrada, EstadoRollback.OMITIDA, error=omision, acciones=hechas
            ), protegida
        if self._detenido(control, detener):
            return self._resultado(entrada, EstadoRollback.NO_ENVIADA, acciones=hechas), protegida
        return None, protegida

    def _motivo_omision(
        self, config: dict[str, Any], entrada: EntradaLibro, id_lote: str, etiquetado: bool
    ) -> ErrorProxLaunch | None:
        """Propiedad y ``lock`` (este último nunca se fuerza)."""
        if not es_propia(config, entrada, id_lote, etiquetado):
            return self._error(CodigoError.ROLLBACK_NO_PROPIA, entrada)
        if config.get("lock"):
            return self._error(CodigoError.ROLLBACK_BLOQUEADA, entrada)
        return None

    def _motivo_omision_lock(
        self, estado_vm: dict[str, Any], entrada: EntradaLibro
    ) -> ErrorProxLaunch | None:
        if estado_vm.get("lock"):
            return self._error(CodigoError.ROLLBACK_BLOQUEADA, entrada)
        return None

    def _motivo_omision_forzado(
        self,
        entrada: EntradaLibro,
        encendida: bool,
        protegida: bool,
        apagar: bool,
        desproteger: bool,
        permisos: PermisosEfectivos | None,
    ) -> ErrorProxLaunch | None:
        """Protección y encendido: lo no confirmado omite; lo confirmado, según los privilegios."""
        if protegida and not desproteger:
            return self._error(CodigoError.ROLLBACK_PROTEGIDA, entrada)
        if encendida and not apagar:
            return self._error(CodigoError.ROLLBACK_ENCENDIDA, entrada)
        ruta = f"/vms/{entrada.elemento.vmid}"
        sin_encendido = (
            encendida and estado_privilegio(permisos, PRIVILEGIO_ENCENDIDO, ruta) is False
        )
        sin_opciones = protegida and estado_privilegio(permisos, PRIVILEGIO_OPCIONES, ruta) is False
        if sin_encendido and sin_opciones:
            error = self._error(CodigoError.ROLLBACK_SIN_POWERMGMT, entrada)
            error.params["tambien"] = str(CodigoError.ROLLBACK_SIN_OPCIONES)
            return error
        if sin_encendido:
            return self._error(CodigoError.ROLLBACK_SIN_POWERMGMT, entrada)
        if sin_opciones:
            return self._error(CodigoError.ROLLBACK_SIN_OPCIONES, entrada)
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

    def _resolver_incierta(
        self, entrada: EntradaLibro, upid: str | None, acciones: tuple[str, ...] = ()
    ) -> ResultadoRollback:
        """No se sabe cómo terminó el DELETE: ``config_vm`` decide (sin reintento, E-L22)."""
        el = entrada.elemento
        try:
            config = self._sesion.cliente.config_vm(el.nodo, el.vmid)
        except Exception:
            config = {}
        if config is None:
            return self._resultado(
                entrada, EstadoRollback.ELIMINADA, upid=upid, acciones=(*acciones, ACCION_BORRADA)
            )
        error = self._error(CodigoError.ROLLBACK_INCIERTO, entrada)
        return self._resultado(
            entrada, EstadoRollback.INCIERTA, upid=upid, error=error, acciones=acciones
        )
