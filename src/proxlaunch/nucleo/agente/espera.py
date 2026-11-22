"""Espera de la IP de cada máquina con el agente invitado (RF-B3, DT-B8). Sin Qt.

``EsperaIp`` corre en SU PROPIO trabajador, desacoplada del motor del lote: el motor solo le
entrega cada MV encendida (``anadir``) o la descarta (``omitir``) y, al terminar, avisa con
``sin_mas_objetivos``. Un único hilo (el que llama a ``ejecutar``) hace las peticiones una tras
otra, así que ninguna MV recibe dos a la vez; ``CalendarioSondeo`` (puro, con el ``Reloj``
inyectado) fija los turnos: ``max(5 s, en_espera / 5)`` por MV y 0,2 s de separación global
(≤ 5 peticiones por segundo, RF-B3.7).

La espera nunca pausa ni falla el lote (RF-B3.5): cada resultado, también los malos, se entrega
a ``al_resultado`` y el libro lo anota como aviso. Cancelar (``cancelar``) es síncrono: al volver,
ninguna de las MVs indicadas se sondea más, lo que permite llamarlo justo antes de un ``DELETE``
de Deshacer. No escribe nada en el servidor ni registra IP ni credenciales.
"""

from __future__ import annotations

import ipaddress
import logging
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass

from proxlaunch.nucleo.agente.calendario import CalendarioSondeo
from proxlaunch.nucleo.agente.clasificacion import Clase, clasificar_error, es_error_de_red
from proxlaunch.nucleo.agente.modelos import EstadoIp, InterfazAgente, ResultadoIp
from proxlaunch.nucleo.agente.seleccion import elegir_ip, interpretar_interfaces
from proxlaunch.nucleo.cloudinit.deteccion import info_cloudinit
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion

_log = logging.getLogger("proxlaunch.agente.espera")

# Tramo máximo de una espera con el ``Reloj`` (mira las cancelaciones y las altas nuevas).
_TRAMO_S = 0.5
# Espera real (no del ``Reloj``) cuando no hay ninguna MV en el calendario.
_ESPERA_VACIA_S = 0.25
# Tope (tiempo real) que ``cancelar`` espera a una petición en vuelo; las peticiones ya llevan su
# propio timeout, esto solo evita un bloqueo indefinido ante un fallo imprevisto.
_ESPERA_VUELO_MAX_S = 120.0

ResultadoObservador = Callable[[int, ResultadoIp], None]
EstadoObservador = Callable[[int, EstadoIp], None]


@dataclass
class _Mv:
    """Estado interno de una MV en espera."""

    nodo: str
    ip_configurada: str | None
    estado: EstadoIp = EstadoIp.PENDIENTE
    config_leida: bool = False
    mac_net0: str | None = None
    ultimas: tuple[InterfazAgente, ...] | None = None  # última respuesta 200 interpretada
    hubo_respuesta: bool = False  # el agente contestó (200) al menos una vez
    sondeos: int = 0
    # Último error de red del sondeo si fue lo último que pasó (una respuesta lo borra): si el
    # plazo vence así, el resultado es ERROR con ese código y no «el agente no responde».
    error_red: ErrorProxLaunch | None = None


def _no_coincide(configurada: str | None, obtenida: str) -> bool:
    """CA-B3.4.5: hay IP fija configurada (CIDR) y la obtenida es otra. Nunca lanza."""
    if not configurada or "/" not in configurada:
        return False  # DHCP o sin configurar: no hay nada con qué comparar
    try:
        esperada = ipaddress.ip_address(configurada.split("/", 1)[0].strip())
        real = ipaddress.ip_address(obtenida)
    except ValueError:
        return False
    return esperada != real


class EsperaIp:
    """Sondeo de IP de varias MVs con un único hilo (el que llama a ``ejecutar``).

    Flujo típico: el trabajador de la interfaz crea la instancia, la pasa al motor
    (``MotorLote.ejecutar(..., espera_ip=…)``) y llama a ``ejecutar()`` en otro hilo. Una
    instancia sirve para UNA ejecución del motor: para ``ejecutar_pendientes`` se crea otra.

    ``al_resultado(vmid, resultado)`` recibe cada resultado terminal (también ``omitida`` y
    ``cancelada``) desde el hilo de quien lo provoca: el de ``ejecutar``, el del motor
    (``omitir``/``anadir``) o el de ``cancelar``. ``al_estado`` (opcional) recibe los cambios
    no terminales (``pendiente`` → ``esperando``) para pintar la columna de IP.
    """

    def __init__(
        self,
        sesion: Sesion,
        reloj: Reloj,
        al_resultado: ResultadoObservador,
        *,
        al_estado: EstadoObservador | None = None,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._al_resultado = al_resultado
        self._al_estado = al_estado
        self._cond = threading.Condition()
        self._calendario = CalendarioSondeo()
        self._activas: dict[int, _Mv] = {}
        self._resultados: dict[int, ResultadoIp] = {}
        self._canceladas: set[int] = set()
        # MVs con una petición HTTP en curso, marcadas bajo el cerrojo ANTES de lanzarla.
        self._en_vuelo: dict[int, int] = {}  # vmid -> id del hilo que la hace
        self._cancelada_toda = False
        self._sin_mas = False

    # --- Alta y baja (las llama el motor, la interfaz y Deshacer) ---------------------------

    def anadir(self, vmid: int, nodo: str, plazo_s: int, ip_configurada: str | None = None) -> None:
        """Entrega una MV ya encendida: su plazo cuenta desde ahora (DT-B8, §0).

        ``ip_configurada``: IP fija (CIDR) de ``net0`` si B1 la fijó; sirve para avisar si la
        obtenida es otra. Si la espera ya se canceló (para esa MV o en general), la MV queda
        ``cancelada`` sin sondear. Una MV repetida se ignora.
        """
        emitir: list[tuple[int, ResultadoIp]] = []
        with self._cond:
            if vmid in self._activas or vmid in self._resultados:
                return
            if self._cancelada_toda or vmid in self._canceladas:
                self._cerrar(vmid, ResultadoIp(EstadoIp.CANCELADA), emitir)
            else:
                self._activas[vmid] = _Mv(nodo=nodo, ip_configurada=ip_configurada)
                self._calendario.anadir(vmid, self._reloj.ahora(), float(plazo_s))
                self._cond.notify_all()
        self._entregar(emitir)

    def omitir(self, vmid: int) -> None:
        """La MV no se sondea (no se enciende, falló el encendido o no se creó): ``omitida``."""
        emitir: list[tuple[int, ResultadoIp]] = []
        with self._cond:
            if vmid in self._resultados:
                return
            self._cerrar(vmid, ResultadoIp(EstadoIp.OMITIDA), emitir)
            self._cond.notify_all()
        self._entregar(emitir)

    def cancelar(self, vmids: Collection[int] | None = None) -> None:
        """Deja de esperar las MVs indicadas (``None`` = todas: «Dejar de esperar»).

        Síncrono: al volver, esas MVs ya están ``canceladas``, ninguna petición suya sigue en
        vuelo (se espera a que termine; su respuesta se descarta) y no se lanzará otra: la
        decisión de pedir se toma bajo el cerrojo, así que no hay carrera. Con ``None`` la espera
        da por cerrado el lote: las MVs que lleguen después también quedan ``canceladas``.
        Deshacer debe llamar a esto ANTES de lanzar el ``DELETE`` (RF-B3.5, CA-B3.5.4). No toca
        el servidor.
        """
        emitir: list[tuple[int, ResultadoIp]] = []
        with self._cond:
            if vmids is None:
                self._cancelada_toda = True
                self._sin_mas = True
                objetivo = list(self._activas)
            else:
                self._canceladas.update(vmids)
                objetivo = [v for v in vmids if v in self._activas]
            for vmid in objetivo:
                self._cerrar(vmid, ResultadoIp(EstadoIp.CANCELADA), emitir)
            self._cond.notify_all()
            # Espera a que no quede en vuelo ninguna de las MVs (salvo una petición de este mismo
            # hilo, que no puede terminar mientras espera aquí).
            yo = threading.get_ident()
            limite = time.monotonic() + _ESPERA_VUELO_MAX_S
            while True:
                pendientes = [
                    v
                    for v, hilo in self._en_vuelo.items()
                    if hilo != yo and (vmids is None or v in vmids)
                ]
                restante = limite - time.monotonic()
                if not pendientes or restante <= 0:
                    break
                self._cond.wait(restante)
        self._entregar(emitir)

    def sin_mas_objetivos(self) -> None:
        """El motor ya no entregará más MVs: ``ejecutar`` termina cuando acaben las que haya."""
        with self._cond:
            self._sin_mas = True
            self._cond.notify_all()

    def estado(self, vmid: int) -> EstadoIp:
        """Estado actual de una MV (``pendiente`` si aún no se conoce)."""
        with self._cond:
            activa = self._activas.get(vmid)
            if activa is not None:
                return activa.estado
            resultado = self._resultados.get(vmid)
            return resultado.estado if resultado is not None else EstadoIp.PENDIENTE

    def resultados(self) -> dict[int, ResultadoIp]:
        """Copia de los resultados terminales hasta ahora."""
        with self._cond:
            return dict(self._resultados)

    # --- Bucle del trabajador ---------------------------------------------------------------

    def ejecutar(self) -> dict[int, ResultadoIp]:
        """Bloqueante: sondea hasta que no queden MVs en espera y el motor haya terminado.

        Devuelve el resultado terminal de cada MV que pasó por la espera.
        """
        while True:
            with self._cond:
                if self._calendario.vacio():
                    if self._sin_mas:
                        return dict(self._resultados)
                    self._cond.wait(_ESPERA_VACIA_S)  # tiempo real: no adelanta el ``Reloj``
                    continue
                ahora = self._reloj.ahora()
                vencidas = self._calendario.vencidas(ahora)
                vmid, espera = (None, 0.0) if vencidas else self._calendario.siguiente(ahora)
            if vencidas:
                for v in vencidas:
                    self._vencer(v)
                continue
            if vmid is None:
                self._reloj.dormir(min(max(espera, 0.0), _TRAMO_S))
                continue
            try:
                self._turno(vmid)
            except Exception as exc:  # un fallo con una MV no detiene a las demás
                _log.exception("Fallo inesperado al sondear la IP (vmid=%s)", vmid)
                self._terminar(vmid, ResultadoIp(EstadoIp.ERROR, error=_error_inesperado(exc)))

    # --- Un turno ---------------------------------------------------------------------------

    def _turno(self, vmid: int) -> None:
        with self._cond:
            mv = self._activas.get(vmid)
            if mv is None:  # cancelada entre el calendario y aquí
                self._calendario.quitar(vmid)
                return
            nodo = mv.nodo
            primera = not mv.config_leida
            if mv.estado == EstadoIp.PENDIENTE:
                mv.estado = EstadoIp.ESPERANDO
                cambio = True
            else:
                cambio = False
            self._calendario.registrar_sondeo(vmid, self._reloj.ahora())
        if cambio and self._al_estado is not None:
            self._avisar_estado(vmid, EstadoIp.ESPERANDO)
        if primera:
            terminal = self._leer_config(vmid, nodo)
            if terminal is not None:
                self._terminar(vmid, terminal)
                return
        if not self._iniciar_vuelo(vmid, sondeo=True):  # cancelada: no se pide nada
            return
        try:
            respuesta = self._sesion.cliente.interfaces_agente(nodo, vmid)
        except ErrorProxLaunch as e:
            self._fin_vuelo(vmid)
            self._ante_error(vmid, e)
            return
        except BaseException:
            self._fin_vuelo(vmid)
            raise
        self._fin_vuelo(vmid)
        self._ante_respuesta(vmid, respuesta)

    def _iniciar_vuelo(self, vmid: int, *, sondeo: bool = False) -> bool:
        """Decide y marca, de forma atómica bajo el cerrojo, que se va a pedir algo de la MV.

        ``False`` = la MV ya no está activa (cancelada o cerrada): no se debe pedir nada. Quien
        recibe ``True`` DEBE llamar a ``_fin_vuelo`` al terminar la petición (QA-M1).
        """
        with self._cond:
            mv = self._activas.get(vmid)
            if mv is None:
                return False
            if sondeo:
                mv.sondeos += 1
            self._en_vuelo[vmid] = threading.get_ident()
            return True

    def _fin_vuelo(self, vmid: int) -> None:
        with self._cond:
            self._en_vuelo.pop(vmid, None)
            self._cond.notify_all()

    def _leer_config(self, vmid: int, nodo: str) -> ResultadoIp | None:
        """Un ``GET config`` por MV (§0, RF-B3.4): ``agent`` y MAC de ``net0``. No cuenta como
        sondeo. Devuelve un resultado terminal o ``None`` para seguir."""
        if not self._iniciar_vuelo(vmid):  # cancelada: no se pide nada
            return None
        try:
            config = self._sesion.cliente.config_vm(nodo, vmid)
        except ErrorProxLaunch as e:
            self._fin_vuelo(vmid)
            clase = clasificar_error(e)
            if clase == Clase.FATAL:
                return ResultadoIp(EstadoIp.ERROR, error=e)
            if clase == Clase.MV_NO_EXISTE:
                return ResultadoIp(EstadoIp.CANCELADA)
            # Sin leerla se sondea igual: sin la MAC no habrá IP principal hasta el fin del plazo.
            config = None
            leida = False
        except BaseException:
            self._fin_vuelo(vmid)
            raise
        else:
            self._fin_vuelo(vmid)
            leida = True
            if config is None:  # la máquina ya no existe (la borró Deshacer): CA-B3.2.5
                return ResultadoIp(EstadoIp.CANCELADA)
        with self._cond:
            mv = self._activas.get(vmid)
            if mv is None:
                return None
            mv.config_leida = True  # un intento por MV, tenga éxito o no
        if not leida or config is None:
            return None
        info = info_cloudinit(config)
        with self._cond:
            mv = self._activas.get(vmid)
            if mv is not None:
                mv.mac_net0 = info.mac_net0
        if info.agente is False:  # sin ``agent`` habilitado no se sondea (RF-B3.3)
            return ResultadoIp(EstadoIp.SIN_AGENTE)
        return None

    def _ante_respuesta(self, vmid: int, respuesta: object) -> None:
        interfaces = interpretar_interfaces(respuesta)
        with self._cond:
            mv = self._activas.get(vmid)
            if mv is None:  # cancelada con la petición en vuelo: se descarta
                return
            mv.hubo_respuesta = True
            mv.error_red = None
            mv.ultimas = interfaces
            mac, configurada, sondeos = mv.mac_net0, mv.ip_configurada, mv.sondeos
        eleccion = elegir_ip(interfaces, mac, final=False)
        if eleccion is not None:
            self._terminar(
                vmid,
                ResultadoIp(
                    EstadoIp.OBTENIDA,
                    principal=eleccion.principal,
                    otras=eleccion.otras,
                    descartadas=eleccion.descartadas,
                    sondeos=sondeos,
                    no_coincide=_no_coincide(configurada, eleccion.principal),
                ),
            )

    def _ante_error(self, vmid: int, e: ErrorProxLaunch) -> None:
        with self._cond:
            mv = self._activas.get(vmid)
            if mv is None:
                return
            sondeos = mv.sondeos
        clase = clasificar_error(e)
        if clase == Clase.TODAVIA_NO:
            with self._cond:
                if mv is self._activas.get(vmid):
                    mv.error_red = e if es_error_de_red(e) else None
            return  # sigue esperando; cuenta como un intento fallido
        if clase == Clase.SIN_AGENTE:
            self._terminar(
                vmid,
                ResultadoIp(
                    EstadoIp.SIN_AGENTE,
                    sondeos=sondeos,
                    error=ErrorProxLaunch(CodigoError.AGENTE_NO_CONFIGURADO, {}, e.detalle_tecnico),
                ),
            )
        elif clase == Clase.SIN_PERMISO:
            self._terminar(vmid, ResultadoIp(EstadoIp.SIN_PERMISO, sondeos=sondeos, error=e))
        elif clase == Clase.MV_NO_EXISTE:
            self._terminar(vmid, ResultadoIp(EstadoIp.CANCELADA, sondeos=sondeos))
        else:  # FATAL: sesión caducada o credenciales
            self._terminar(vmid, ResultadoIp(EstadoIp.ERROR, sondeos=sondeos, error=e))

    def _vencer(self, vmid: int) -> None:
        """Fin del plazo: se evalúa la última respuesta con ``final=True`` (RF-B3.3/B3.4)."""
        with self._cond:
            mv = self._activas.get(vmid)
            if mv is None:
                self._calendario.quitar(vmid)
                return
            ultimas, hubo, error_red = mv.ultimas, mv.hubo_respuesta, mv.error_red
            mac, configurada, sondeos = mv.mac_net0, mv.ip_configurada, mv.sondeos
        eleccion = elegir_ip(ultimas, mac, final=True) if ultimas is not None else None
        if eleccion is not None:
            estado = EstadoIp.OBTENIDA_PARCIAL if eleccion.parcial else EstadoIp.OBTENIDA
            resultado = ResultadoIp(
                estado,
                principal=eleccion.principal,
                otras=eleccion.otras,
                descartadas=eleccion.descartadas,
                sondeos=sondeos,
                no_coincide=_no_coincide(configurada, eleccion.principal),
            )
        elif error_red is not None:
            # QA-B1: lo último que pasó fue una caída de la conexión; no se culpa al agente.
            resultado = ResultadoIp(EstadoIp.ERROR, sondeos=sondeos, error=error_red)
        elif hubo:
            descartadas = (
                tuple(dict.fromkeys(i.nombre for i in ultimas)) if ultimas is not None else ()
            )
            resultado = ResultadoIp(EstadoIp.SIN_IP, descartadas=descartadas, sondeos=sondeos)
        else:
            resultado = ResultadoIp(
                EstadoIp.AGENTE_NO_RESPONDE,
                sondeos=sondeos,
                error=ErrorProxLaunch(CodigoError.AGENTE_NO_RESPONDE, {"vmid": str(vmid)}),
            )
        self._terminar(vmid, resultado)

    # --- Cierre y avisos --------------------------------------------------------------------

    def _terminar(self, vmid: int, resultado: ResultadoIp) -> None:
        """Cierra una MV si sigue activa (si la cancelaron mientras tanto, se descarta)."""
        emitir: list[tuple[int, ResultadoIp]] = []
        with self._cond:
            if vmid not in self._activas:
                self._calendario.quitar(vmid)
                return
            self._cerrar(vmid, resultado, emitir)
            self._cond.notify_all()
        self._entregar(emitir)

    def _cerrar(
        self, vmid: int, resultado: ResultadoIp, emitir: list[tuple[int, ResultadoIp]]
    ) -> None:
        """Anota el resultado terminal. Se llama con el cerrojo tomado."""
        self._activas.pop(vmid, None)
        self._calendario.quitar(vmid)
        self._resultados[vmid] = resultado
        emitir.append((vmid, resultado))

    def _entregar(self, emitir: list[tuple[int, ResultadoIp]]) -> None:
        """Avisa al observador fuera del cerrojo; un fallo suyo no detiene la espera."""
        for vmid, resultado in emitir:
            _log.info("Espera de IP: vmid=%s estado=%s sondeos=%s", vmid, resultado.estado.value,
                      resultado.sondeos)  # fmt: skip
            try:
                self._al_resultado(vmid, resultado)
            except Exception:
                _log.exception("El observador de la espera de IP falló (vmid=%s)", vmid)

    def _avisar_estado(self, vmid: int, estado: EstadoIp) -> None:
        if self._al_estado is None:
            return
        try:
            self._al_estado(vmid, estado)
        except Exception:
            _log.exception("El observador de estado de la espera de IP falló (vmid=%s)", vmid)


def _error_inesperado(exc: BaseException) -> ErrorProxLaunch:
    """Envuelve una excepción inesperada sin filtrar su texto (solo el tipo)."""
    return ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, type(exc).__name__)
