"""ServicioCreacion: validar, enviar y seguir la tarea de creación."""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from typing import Any

from proxlaunch.nucleo.api.traductor_errores import CODIGOS_DE_RED, traducir_exitstatus
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.tarea import Desenlace, EstadoTarea, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Firmware
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.validacion import Severidad, storage_efi_efectivo, validar_vm

_log = logging.getLogger("proxlaunch.servicios.creacion")

INTERVALO_SONDEO_S = 1.5  # CA-20.1
MAX_ESPERA_S = 600.0  # P-05: 10 min
TOLERANCIA_RED_S = 60.0  # CA-20.7


class _Cancelado(Exception):
    """Interna: el usuario canceló durante una espera tolerante."""


class _ConexionPerdida(Exception):
    """Interna: la red falló durante más de la tolerancia."""

    def __init__(self, error: ErrorProxLaunch) -> None:
        super().__init__(str(error.codigo))
        self.error = error


class ServicioCreacion:
    """Máquina de etapas de RF-20. Nunca borra nada al fallar (CA-20.10)."""

    def __init__(
        self,
        sesion: Sesion,
        reloj: Reloj,
        intervalo_s: float = INTERVALO_SONDEO_S,
        max_espera_s: float = MAX_ESPERA_S,
        tolerancia_red_s: float = TOLERANCIA_RED_S,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._intervalo = intervalo_s
        self._max_espera = max_espera_s
        self._tolerancia_red = tolerancia_red_s
        self._cancelado_ev: threading.Event | None = None
        self._upid_actual: str | None = None
        self._inv_actual: Inventario | None = None

    # --- Utilidades -------------------------------------------------------------------

    def _tolerante(self, funcion: Callable[[], Any]) -> Any:
        """Ejecuta ``funcion`` reintentando ante fallos de red hasta agotar la tolerancia.

        Si ``self._cancelado`` se activa durante la espera lanza ``_Cancelado``.
        """
        primer_fallo: float | None = None
        while True:
            if self._cancelado_ev is not None and self._cancelado_ev.is_set():
                raise _Cancelado
            try:
                return funcion()
            except ErrorProxLaunch as e:
                if e.codigo not in CODIGOS_DE_RED:
                    raise
                ahora = self._reloj.ahora()
                if primer_fallo is None:
                    primer_fallo = ahora
                elif ahora - primer_fallo > self._tolerancia_red:
                    raise _ConexionPerdida(e) from None
                self._reloj.dormir(self._intervalo)

    @staticmethod
    def _resultado(
        desenlace: Desenlace,
        cfg: ConfiguracionVM,
        upid: str | None = None,
        error: ErrorProxLaunch | None = None,
        log: list[str] | None = None,
    ) -> ResultadoCreacion:
        return ResultadoCreacion(
            desenlace=desenlace,
            vmid=cfg.vmid,
            nodo=cfg.nodo,
            upid=upid,
            error=error,
            log_tarea=log or [],
        )

    def _log_seguro(self, nodo: str, upid: str) -> list[str]:
        """Log de la tarea; si no se puede leer devuelve una lista vacía."""
        try:
            return list(self._tolerante(lambda: self._sesion.cliente.log_tarea(nodo, upid)))
        except (ErrorProxLaunch, _ConexionPerdida):
            return []

    # --- Flujo principal --------------------------------------------------------------

    def crear(
        self,
        cfg: ConfiguracionVM,
        inv: Inventario,
        al_cambiar_etapa: Callable[[Etapa], None],
        cancelado: threading.Event,
        *,
        al_enviar: Callable[[str], None] | None = None,
    ) -> ResultadoCreacion:
        """Valida, envía y sigue la tarea hasta un desenlace.

        ``al_enviar`` (opcional) recibe el UPID justo después del POST exitoso y antes
        de empezar el sondeo.

        Si ``cancelado`` se activa se deja de esperar, sin borrar nada, y el desenlace es
        ``CANCELADO`` (con ``upid`` si la tarea ya se había enviado).
        """
        self._cancelado_ev = cancelado
        self._inv_actual = inv
        try:
            return self._crear(cfg, inv, al_cambiar_etapa, cancelado, al_enviar)
        except _Cancelado:
            return self._cancelado(cfg, self._upid_actual)
        finally:
            self._cancelado_ev = None
            self._upid_actual = None
            self._inv_actual = None

    def _crear(
        self,
        cfg: ConfiguracionVM,
        inv: Inventario,
        al_cambiar_etapa: Callable[[Etapa], None],
        cancelado: threading.Event,
        al_enviar: Callable[[str], None] | None = None,
    ) -> ResultadoCreacion:
        cliente = self._sesion.cliente

        # 1. Validación local y comprobación del VMID (V-03).
        al_cambiar_etapa(Etapa.VALIDANDO)
        problemas = [
            p
            for p in validar_vm(cfg, inv, self._sesion.capacidades)
            if p.severidad == Severidad.ERROR
        ]
        if problemas:
            primero = problemas[0]
            return self._resultado(
                Desenlace.ERROR,
                cfg,
                error=ErrorProxLaunch(
                    CodigoError.PARAMETRO_INVALIDO,
                    {"campo": primero.campo, "regla": primero.codigo},
                    "; ".join(f"{p.campo}:{p.codigo}" for p in problemas),
                ),
            )
        try:
            self._tolerante(lambda: cliente.proximo_vmid(cfg.vmid))
        except ErrorProxLaunch as e:
            return self._resultado(Desenlace.ERROR, cfg, error=self._con_siguiente_vmid(e))
        except _ConexionPerdida as p:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=p.error)
        try:
            parametros = construir_parametros(cfg, inv)
        except ErrorProxLaunch as e:
            return self._resultado(Desenlace.ERROR, cfg, error=e)
        if cancelado.is_set():
            return self._cancelado(cfg, None)

        # 2. Envío. No se reintenta: un POST repetido podría duplicar la operación.
        al_cambiar_etapa(Etapa.ENVIANDO)
        try:
            upid = cliente.crear_vm(cfg.nodo, parametros)
        except ErrorProxLaunch as e:
            error_envio = self._con_siguiente_vmid(e)
            desenlace = (
                Desenlace.CONEXION_PERDIDA
                if e.codigo == CodigoError.SERVIDOR_NO_RESPONDE
                else Desenlace.ERROR
            )
            return self._resultado(desenlace, cfg, error=error_envio)
        self._upid_actual = upid
        _log.info("Creación enviada: vmid=%s nodo=%s upid=%s", cfg.vmid, cfg.nodo, upid)

        if al_enviar is not None:
            al_enviar(upid)
        return self._seguir_y_comprobar(cfg, upid, cancelado, al_cambiar_etapa)

    def _seguir_y_comprobar(
        self,
        cfg: ConfiguracionVM,
        upid: str,
        cancelado: threading.Event,
        al_cambiar_etapa: Callable[[Etapa], None] | None,
    ) -> ResultadoCreacion:
        """Etapas 3 y 4 de RF-20: sondeo de la tarea y comprobación del resultado."""

        def etapa(e: Etapa) -> None:
            if al_cambiar_etapa is not None:
                al_cambiar_etapa(e)

        etapa(Etapa.CREANDO)
        final = self._seguir(cfg, upid, cancelado)
        if isinstance(final, ResultadoCreacion):
            return final

        etapa(Etapa.COMPROBANDO)
        try:
            resultado = self._comprobar(cfg, upid, final.exitstatus)
        except _ConexionPerdida as p:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, p.error)
        if resultado.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS):
            etapa(Etapa.LISTO)
        return resultado

    def seguir(
        self,
        cfg: ConfiguracionVM,
        upid: str,
        cancelado: threading.Event,
        al_cambiar_etapa: Callable[[Etapa], None] | None = None,
    ) -> ResultadoCreacion:
        """Sigue una tarea ya enviada y la comprueba al terminar (mismos desenlaces que
        ``crear``). Sirve para "Seguir esperando" tras ``TIEMPO_AGOTADO``/``CONEXION_PERDIDA``."""
        self._cancelado_ev = cancelado
        self._upid_actual = upid
        try:
            return self._seguir_y_comprobar(cfg, upid, cancelado, al_cambiar_etapa)
        except _Cancelado:
            return self._cancelado(cfg, upid)
        finally:
            self._cancelado_ev = None
            self._upid_actual = None

    def comprobar_ahora(self, cfg: ConfiguracionVM, upid: str) -> ResultadoCreacion:
        """Una sola consulta del estado. Si la tarea terminó, la comprueba con ``config_vm``;
        si sigue corriendo devuelve ``TIEMPO_AGOTADO`` sin esperar ("Comprobar ahora")."""
        try:
            estado = self._sesion.cliente.estado_tarea(cfg.nodo, upid)
        except ErrorProxLaunch as e:
            desenlace = (
                Desenlace.CONEXION_PERDIDA if e.codigo in CODIGOS_DE_RED else Desenlace.ERROR
            )
            return self._resultado(desenlace, cfg, upid, e)
        if not estado.terminada:
            return self._resultado(
                Desenlace.TIEMPO_AGOTADO,
                cfg,
                upid,
                ErrorProxLaunch(CodigoError.TAREA_TIEMPO_AGOTADO, {"upid": upid}),
            )
        try:
            return self._comprobar(cfg, upid, estado.exitstatus)
        except _ConexionPerdida as p:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, p.error)

    def _con_siguiente_vmid(self, error: ErrorProxLaunch) -> ErrorProxLaunch:
        """Si el VMID está ocupado intenta añadir el siguiente libre (CA-13.3)."""
        if error.codigo != CodigoError.VMID_OCUPADO:
            return error
        with contextlib.suppress(ErrorProxLaunch):
            error.params["siguiente"] = str(self._sesion.cliente.proximo_vmid())
        return error

    def _cancelado(self, cfg: ConfiguracionVM, upid: str | None) -> ResultadoCreacion:
        """Resultado de una cancelación. Sin error: cancelar no es un fallo. Si hay
        ``upid`` la tarea pudo seguir en Proxmox; la interfaz lo avisa."""
        return self._resultado(Desenlace.CANCELADO, cfg, upid, None)

    def _seguir(
        self, cfg: ConfiguracionVM, upid: str, cancelado: threading.Event
    ) -> EstadoTarea | ResultadoCreacion:
        """Sondea hasta que la tarea termina. Devuelve el ``EstadoTarea`` o un resultado final."""
        cliente = self._sesion.cliente
        inicio = self._reloj.ahora()
        primer_fallo: float | None = None
        while True:
            if cancelado.is_set():
                return self._cancelado(cfg, upid)
            try:
                estado = cliente.estado_tarea(cfg.nodo, upid)
            except ErrorProxLaunch as e:
                if e.codigo not in CODIGOS_DE_RED:
                    return self._resultado(Desenlace.ERROR, cfg, upid, e)
                ahora = self._reloj.ahora()
                if primer_fallo is None:
                    primer_fallo = ahora
                elif ahora - primer_fallo > self._tolerancia_red:
                    return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, e)
            else:
                primer_fallo = None
                if estado.terminada:
                    return estado
            if self._reloj.ahora() - inicio >= self._max_espera:
                # La tarea sigue en Proxmox: no se borra ni se reintenta nada (CA-20.6).
                return self._resultado(
                    Desenlace.TIEMPO_AGOTADO,
                    cfg,
                    upid,
                    ErrorProxLaunch(CodigoError.TAREA_TIEMPO_AGOTADO, {"upid": upid}),
                )
            self._reloj.dormir(self._intervalo)

    def _ajustar_storage(self, error: ErrorProxLaunch, cfg: ConfiguracionVM) -> ErrorProxLaunch:
        """En SIN_ESPACIO por un grupo de volúmenes LVM, sustituye el nombre por el id del
        storage de Proxmox (discos y, con OVMF, efidisk; sin duplicados). El original queda
        en ``params["vg"]``."""
        if error.codigo != CodigoError.SIN_ESPACIO:
            return error
        discos = cfg.discos if cfg.con_disco else []
        ids = list(dict.fromkeys(d.storage for d in discos))
        if cfg.firmware == Firmware.OVMF:
            if cfg.storage_efi:
                efi: str | None = cfg.storage_efi
            elif self._inv_actual is not None:
                efi = storage_efi_efectivo(cfg, self._inv_actual)
            else:
                efi = ids[0] if ids else None
            if efi and efi not in ids:
                ids.append(efi)
        original = error.params.get("storage")
        if not ids or original in ids:
            return error
        if original:
            error.params["vg"] = original
        error.params["storage"] = ",".join(ids)
        return error

    def _comprobar(
        self, cfg: ConfiguracionVM, upid: str, exitstatus: str | None
    ) -> ResultadoCreacion:
        """Interpreta el ``exitstatus`` y lo confirma con ``config_vm`` (CA-20.3 a CA-20.5)."""
        cliente = self._sesion.cliente
        exito = (exitstatus or "").strip()
        if exito == "OK" or exito.upper().startswith("WARNINGS"):
            try:
                config = self._tolerante(lambda: cliente.config_vm(cfg.nodo, cfg.vmid))
            except ErrorProxLaunch as e:
                # No se puede confirmar (p. ej. falta VM.Audit): se informa como aviso.
                log = self._log_seguro(cfg.nodo, upid)
                return self._resultado(Desenlace.CON_AVISOS, cfg, upid, e, log)
            if config is None:
                error = ErrorProxLaunch(
                    CodigoError.RECURSO_INEXISTENTE,
                    {"recurso": f"vm {cfg.vmid}", "nodo": cfg.nodo},
                    f"la tarea terminó con '{exito}' pero la máquina no existe",
                )
                return self._resultado(Desenlace.ERROR, cfg, upid, error)
            if exito == "OK":
                return self._resultado(Desenlace.OK, cfg, upid)
            return self._resultado(
                Desenlace.CON_AVISOS, cfg, upid, None, self._log_seguro(cfg.nodo, upid)
            )

        # La tarea falló. Si quedó una configuración a medias se informa (CA-20.10).
        error = self._ajustar_storage(traducir_exitstatus(exitstatus), cfg)
        log = self._log_seguro(cfg.nodo, upid)
        try:
            config = self._tolerante(lambda: cliente.config_vm(cfg.nodo, cfg.vmid))
        except ErrorProxLaunch:
            config = None
        desenlace = Desenlace.PARCIAL if config is not None else Desenlace.ERROR
        return self._resultado(desenlace, cfg, upid, error, log)
