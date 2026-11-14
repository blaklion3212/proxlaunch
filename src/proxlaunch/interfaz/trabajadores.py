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
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.csv_importacion.plantilla import escribir_plantilla
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
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
from proxlaunch.nucleo.lote.motor import ControlLote, MotorLote
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.lote.presupuesto import evaluar_espacio, uso_por_clave
from proxlaunch.nucleo.lote.reconciliacion import config_en_creacion, tiene_etiqueta_del_lote
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote, leer_archivo_lote
from proxlaunch.nucleo.lotes_guardados.modelos import ArchivoLote, LoteGuardado
from proxlaunch.nucleo.modelos.inventario import Bridge, Inventario, Storage
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.perfiles_maquina.formato import (
    ArchivoPerfiles,
    exportar_perfiles,
    leer_archivo_perfiles,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import PerfilMaquina
from proxlaunch.nucleo.registro import enmascarar
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion, permisos_faltantes
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.servicios.descubrimiento import descubrir, descubrir_nodo
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

    @staticmethod
    def _desconectar(trabajador: Trabajador) -> None:
        """Rompe el ciclo trabajador -> señales -> lambda -> trabajador."""
        for senal in (
            trabajador.senales.terminado,
            trabajador.senales.fallo,
            trabajador.senales.etapa,
            trabajador.senales.upid,
        ):
            with contextlib.suppress(RuntimeError, TypeError):
                senal.disconnect()

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
) -> Plan:
    """Planifica el lote (reserva VMIDs con lecturas) fuera del hilo de la interfaz."""
    return Planificador(sesion, reloj).planificar(definicion, inv, version_forzada=version_forzada)


def replanificar_lote(
    sesion: Sesion,
    reloj: Reloj,
    definicion: DefinicionLote,
    version_forzada: tuple[int, int] | None,
) -> tuple[Inventario, Plan]:
    """Relee el inventario y vuelve a planificar (plan viejo o simulación, CA-L10.6)."""
    inv = descubrir(sesion)
    plan = Planificador(sesion, reloj).planificar(definicion, inv, version_forzada=version_forzada)
    return inv, plan


def simular_lote(
    sesion: Sesion,
    reloj: Reloj,
    definicion: DefinicionLote,
    inv: Inventario,
    version_forzada: tuple[int, int] | None,
) -> ResultadoSimulacion:
    """Simulación de solo lectura (RF-L11)."""
    return simular(sesion, definicion, inv, version_forzada=version_forzada, reloj=reloj)


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
) -> Libro:
    """Ejecuta el plan con el motor; bloquea hasta que termine (hilo de trabajo).

    ``libro`` es el libro creado de antemano por la interfaz: así existe aunque el motor
    falle y «Deshacer» y «Comprobar» siguen disponibles sobre lo ya creado.
    """
    motor = _motor(sesion, reloj, fabrica)
    if libro is None:
        return motor.ejecutar(plan, inv, observador, control)
    return motor.ejecutar(plan, inv, observador, control, libro=libro)


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
) -> Libro:
    """«Comprobar y continuar» / «Reconectar»: comprueba las dudosas y envía solo las pendientes."""
    motor = _motor(sesion, reloj, fabrica)
    if comprobar_antes:
        motor.comprobar_dudosas(libro, observador, control)
    return motor.ejecutar_pendientes(libro, inv, observador, control)


def deshacer_lote(
    sesion: Sesion,
    reloj: Reloj,
    candidatos: list[CandidatoRollback],
    observador: Callable[[ResultadoRollback], None],
    control: ControlLote,
    id_lote: str,
    etiquetado: bool,
) -> list[ResultadoRollback]:
    """Elimina las máquinas elegidas del lote (acción confirmada por el usuario)."""
    return ServicioRollback(sesion, reloj).deshacer(
        candidatos, observador, control, id_lote=id_lote, etiquetado=etiquetado
    )


def deshacer_lotes(
    sesion: Sesion,
    reloj: Reloj,
    grupos: list[tuple[list[CandidatoRollback], str, bool]],
    observador: Callable[[ResultadoRollback], None],
    control: ControlLote,
) -> list[ResultadoRollback]:
    """Deshace las máquinas elegidas de uno o varios lotes de la sesión, lote por lote."""
    resultados: list[ResultadoRollback] = []
    for candidatos, id_lote, etiquetado in grupos:
        resultados.extend(
            deshacer_lote(sesion, reloj, candidatos, observador, control, id_lote, etiquetado)
        )
        if control.cancelado.is_set():
            break
    return resultados


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
