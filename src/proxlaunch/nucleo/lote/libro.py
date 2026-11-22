"""Libro del lote: registro en memoria, seguro entre hilos (docs/arquitectura/mvp2.md §4.3).

Es el único estado mutable compartido entre los trabajadores del motor y la interfaz. La
interfaz solo lee instantáneas inmutables (``EntradaLibro``). Cada método de transición
devuelve la entrada ya actualizada para que quien llama la pase al observador *fuera* del
cerrojo.
"""

from __future__ import annotations

import dataclasses
import threading

from proxlaunch.nucleo.agente.modelos import SIN_IP_UTIL, EstadoIp, ResultadoIp
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import LINEAS_LOG_TAREA
from proxlaunch.nucleo.lote.modelos import (
    ESTADOS_EN_CURSO,
    EntradaLibro,
    EstadoMV,
    MotivoNoEnviada,
    Plan,
)

# Avisos de la espera de IP (RF-B3.5): nunca hacen fallar la MV ni pausan el lote.
AVISO_IP_NO_OBTENIDA = "ip_no_obtenida"
AVISO_IP_PARCIAL = "ip_parcial"
AVISO_IP_NO_COINCIDE = "ip_no_coincide"


def _avisos_de_ip(resultado: ResultadoIp) -> tuple[str, ...]:
    """Avisos que añade un resultado de la espera de IP (``omitida`` y ``cancelada`` no añaden)."""
    avisos: list[str] = []
    if resultado.estado in SIN_IP_UTIL:
        avisos.append(AVISO_IP_NO_OBTENIDA)
    elif resultado.estado == EstadoIp.OBTENIDA_PARCIAL:
        avisos.append(AVISO_IP_PARCIAL)
    if resultado.no_coincide:
        avisos.append(AVISO_IP_NO_COINCIDE)
    return tuple(avisos)


class Libro:
    """Registro del lote: una ``EntradaLibro`` por MV del plan, indexada por VMID.

    Las transiciones sobre una entrada que ya está en estado final se ignoran, salvo
    ``resolver`` (que sirve para las comprobaciones posteriores de MVs dudosas).
    """

    def __init__(self, plan: Plan) -> None:
        self._plan = plan
        self._cerrojo = threading.Lock()
        self._entradas: dict[int, EntradaLibro] = {e.vmid: EntradaLibro(e) for e in plan.elementos}
        self._orden: tuple[int, ...] = tuple(e.vmid for e in plan.elementos)

    # --- Lectura ----------------------------------------------------------------------

    @property
    def plan(self) -> Plan:
        return self._plan

    @property
    def id_lote(self) -> str:
        return self._plan.id_lote

    def entrada(self, vmid: int) -> EntradaLibro:
        with self._cerrojo:
            return self._entradas[vmid]

    def instantanea(self) -> tuple[EntradaLibro, ...]:
        """Copia consistente de todas las entradas, en el orden del plan."""
        with self._cerrojo:
            return tuple(self._entradas[v] for v in self._orden)

    def contadores(self) -> dict[EstadoMV, int]:
        """Cantidad de MVs por estado (solo los estados presentes)."""
        cuenta: dict[EstadoMV, int] = {}
        for entrada in self.instantanea():
            cuenta[entrada.estado] = cuenta.get(entrada.estado, 0) + 1
        return cuenta

    def terminado(self) -> bool:
        """``True`` si ninguna MV está en un estado en curso (incluido ``PENDIENTE``)."""
        return all(e.estado not in ESTADOS_EN_CURSO for e in self.instantanea())

    def pendientes(self) -> tuple[EntradaLibro, ...]:
        """MVs que nunca se intentaron: ``PENDIENTE`` y sin POST (CA-L17.3)."""
        return tuple(
            e for e in self.instantanea() if e.estado == EstadoMV.PENDIENTE and not e.post_intentado
        )

    # --- Transiciones -----------------------------------------------------------------

    def marcar_post_intentado(self, vmid: int, t: float | None = None) -> EntradaLibro:
        """Marca que el POST se va a enviar (INV-L1). Solo puede hacerse una vez.

        Raises:
            AssertionError: si la entrada ya estaba marcada (defensa en profundidad).
        """
        with self._cerrojo:
            actual = self._entradas[vmid]
            assert not actual.post_intentado, f"INV-L1: segundo envío para el VMID {vmid}"
            nueva = dataclasses.replace(
                actual,
                post_intentado=True,
                t_inicio=actual.t_inicio if actual.t_inicio is not None else t,
            )
            self._entradas[vmid] = nueva
            return nueva

    def iniciar(self, vmid: int, t: float) -> EntradaLibro:
        """Registra el inicio del procesamiento (estado ``VALIDANDO``) y la hora de inicio."""
        with self._cerrojo:
            actual = self._entradas[vmid]
            if actual.estado != EstadoMV.PENDIENTE:
                return actual
            nueva = dataclasses.replace(actual, estado=EstadoMV.VALIDANDO, t_inicio=t)
            self._entradas[vmid] = nueva
            return nueva

    def actualizar_estado(self, vmid: int, estado: EstadoMV) -> EntradaLibro:
        """Cambia la etapa de una MV en curso; si ya terminó no hace nada."""
        with self._cerrojo:
            actual = self._entradas[vmid]
            if actual.estado in ESTADOS_EN_CURSO and estado in ESTADOS_EN_CURSO:
                actual = dataclasses.replace(actual, estado=estado)
                self._entradas[vmid] = actual
            return actual

    def registrar_upid(self, vmid: int, upid: str) -> EntradaLibro:
        with self._cerrojo:
            actual = dataclasses.replace(self._entradas[vmid], upid=upid)
            self._entradas[vmid] = actual
            return actual

    def registrar_log(self, vmid: int, log: list[str] | tuple[str, ...]) -> EntradaLibro:
        with self._cerrojo:
            actual = dataclasses.replace(
                self._entradas[vmid], log_tarea=tuple(log)[-LINEAS_LOG_TAREA:]
            )
            self._entradas[vmid] = actual
            return actual

    def finalizar(
        self,
        vmid: int,
        estado: EstadoMV,
        *,
        t_fin: float | None = None,
        upid: str | None = None,
        error: ErrorProxLaunch | None = None,
        log: list[str] | tuple[str, ...] = (),
        avisos: tuple[str, ...] = (),
    ) -> EntradaLibro:
        """Fija el estado final de una MV. Ignora la llamada si ya estaba en estado final."""
        assert estado not in ESTADOS_EN_CURSO, "finalizar exige un estado final"
        with self._cerrojo:
            actual = self._entradas[vmid]
            if actual.estado not in ESTADOS_EN_CURSO:
                return actual
            return self._escribir(actual, estado, t_fin, upid, error, log, avisos)

    def resolver(
        self,
        vmid: int,
        estado: EstadoMV,
        *,
        t_fin: float | None = None,
        upid: str | None = None,
        error: ErrorProxLaunch | None = None,
        log: list[str] | tuple[str, ...] = (),
        avisos: tuple[str, ...] = (),
    ) -> EntradaLibro:
        """Reemplaza el estado de una MV *ya intentada* tras una comprobación (CA-L15.7).

        Conserva UPID, log y avisos previos si el nuevo valor viene vacío. No permite
        resolver una MV que nunca se intentó (``post_intentado`` falso).
        """
        assert estado not in ESTADOS_EN_CURSO, "resolver exige un estado final"
        with self._cerrojo:
            actual = self._entradas[vmid]
            assert actual.post_intentado, f"resolver sobre una MV sin POST (vmid {vmid})"
            return self._escribir(
                actual,
                estado,
                t_fin,
                upid if upid is not None else actual.upid,
                error,
                log if log else actual.log_tarea,
                avisos if avisos else actual.avisos,
            )

    def registrar_ip(self, vmid: int, resultado: ResultadoIp) -> EntradaLibro | None:
        """Anota el resultado de la espera de IP (RF-B3.5, DT-B8).

        Añade el aviso que corresponda (``ip_no_obtenida``, ``ip_parcial`` o ``ip_no_coincide``)
        y pasa ``OK`` a ``CON_AVISOS``: es un aviso, nunca un fallo, y NO pasa por la política
        de pausa. No cambia ningún otro estado (una MV con error o ya deshecha conserva el
        suyo). Devuelve la entrada actualizada o ``None`` si el VMID no es del lote.
        """
        with self._cerrojo:
            actual = self._entradas.get(vmid)
            if actual is None:
                return None
            avisos = actual.avisos
            for aviso in _avisos_de_ip(resultado):
                if aviso not in avisos:
                    avisos = (*avisos, aviso)
            estado = actual.estado
            if avisos != actual.avisos and estado == EstadoMV.OK:
                estado = EstadoMV.CON_AVISOS
            nueva = dataclasses.replace(actual, ip=resultado, avisos=avisos, estado=estado)
            self._entradas[vmid] = nueva
            return nueva

    def marcar_no_enviada(
        self, vmid: int, motivo: MotivoNoEnviada, t_fin: float | None = None
    ) -> EntradaLibro:
        """Marca una MV que nunca se envió. Solo desde ``PENDIENTE``/en curso sin POST.

        Raises:
            AssertionError: si el POST ya se intentó (sería una MV incierta, no "no enviada").
        """
        with self._cerrojo:
            actual = self._entradas[vmid]
            assert not actual.post_intentado, f"INV-L1: la MV {vmid} ya se intentó enviar"
            if actual.estado not in ESTADOS_EN_CURSO:
                return actual
            nueva = dataclasses.replace(
                actual, estado=EstadoMV.NO_ENVIADA, motivo_no_enviada=motivo, t_fin=t_fin
            )
            self._entradas[vmid] = nueva
            return nueva

    def _escribir(
        self,
        actual: EntradaLibro,
        estado: EstadoMV,
        t_fin: float | None,
        upid: str | None,
        error: ErrorProxLaunch | None,
        log: list[str] | tuple[str, ...],
        avisos: tuple[str, ...],
    ) -> EntradaLibro:
        nueva = dataclasses.replace(
            actual,
            estado=estado,
            t_fin=t_fin if t_fin is not None else actual.t_fin,
            upid=upid if upid is not None else actual.upid,
            error=error,
            log_tarea=tuple(log)[-LINEAS_LOG_TAREA:] if log else actual.log_tarea,
            avisos=avisos if avisos else actual.avisos,
            motivo_no_enviada=None,
        )
        self._entradas[actual.elemento.vmid] = nueva
        return nueva
