"""ServicioCreacion: validar, enviar y seguir la tarea de creación."""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass
class _Contexto:
    """Estado de UNA llamada (así el servicio puede usarse desde varios hilos)."""

    cancelado: threading.Event | None = None
    upid: str | None = None
    inv: Inventario | None = None
    tolerante: bool = True  # False: una sola ronda, sin reintentos ni esperas


def _error_inesperado(exc: BaseException) -> ErrorProxLaunch:
    """Envuelve una excepción inesperada sin filtrar el texto completo (solo el tipo)."""
    return ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, type(exc).__name__)


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

    # --- Utilidades -------------------------------------------------------------------

    def _tolerante(self, ctx: _Contexto, funcion: Callable[[], Any]) -> Any:
        """Ejecuta ``funcion`` reintentando ante fallos de red hasta agotar la tolerancia.

        Si el evento de cancelación se activa lanza ``_Cancelado``. Con
        ``ctx.tolerante=False`` no reintenta: un fallo de red es ``_ConexionPerdida``.
        """
        primer_fallo: float | None = None
        while True:
            if ctx.cancelado is not None and ctx.cancelado.is_set():
                raise _Cancelado
            try:
                return funcion()
            except ErrorProxLaunch as e:
                if e.codigo not in CODIGOS_DE_RED:
                    raise
                if not ctx.tolerante:
                    raise _ConexionPerdida(e) from None
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

    def _log_seguro(self, ctx: _Contexto, nodo: str, upid: str) -> list[str]:
        """Log de la tarea; si no se puede leer devuelve una lista vacía."""
        try:
            return list(self._tolerante(ctx, lambda: self._sesion.cliente.log_tarea(nodo, upid)))
        except _Cancelado:
            raise
        except (ErrorProxLaunch, _ConexionPerdida):
            return []
        except Exception:
            _log.exception("Fallo inesperado al leer el log de la tarea")
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
        ``CANCELADO`` (con ``upid`` si la tarea ya se había enviado). Una vez enviada la
        tarea, cualquier fallo que no sea el desenlace de la propia tarea (sesión
        expirada, 403, error puntual, excepción inesperada) da ``CONEXION_PERDIDA`` con
        el ``upid``: no se sabe cómo terminó, así que no se declara un error.
        """
        ctx = _Contexto(cancelado=cancelado, inv=inv)
        try:
            return self._crear(ctx, cfg, inv, al_cambiar_etapa, al_enviar)
        except _Cancelado:
            return self._cancelado(cfg, ctx.upid)

    def _crear(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        inv: Inventario,
        al_cambiar_etapa: Callable[[Etapa], None],
        al_enviar: Callable[[str], None] | None,
    ) -> ResultadoCreacion:
        cliente = self._sesion.cliente
        cancelado = ctx.cancelado
        assert cancelado is not None

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
            self._tolerante(ctx, lambda: cliente.proximo_vmid(cfg.vmid))
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
        except Exception as e:  # el POST pudo salir: resultado incierto
            _log.exception("Fallo inesperado al enviar la creación")
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=_error_inesperado(e))
        ctx.upid = upid
        _log.info("Creación enviada: vmid=%s nodo=%s upid=%s", cfg.vmid, cfg.nodo, upid)
        if al_enviar is not None:
            al_enviar(upid)
        return self._seguir_y_comprobar(ctx, cfg, upid, al_cambiar_etapa)

    def _seguir_y_comprobar(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        upid: str,
        al_cambiar_etapa: Callable[[Etapa], None] | None,
    ) -> ResultadoCreacion:
        """Etapas 3 y 4 de RF-20: sondeo de la tarea y comprobación del resultado."""

        def etapa(e: Etapa) -> None:
            if al_cambiar_etapa is not None:
                al_cambiar_etapa(e)

        try:
            etapa(Etapa.CREANDO)
            final = self._seguir(ctx, cfg, upid)
            if isinstance(final, ResultadoCreacion):
                return final
            etapa(Etapa.COMPROBANDO)
            resultado = self._comprobar(ctx, cfg, upid, final.exitstatus)
            if resultado.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS):
                etapa(Etapa.LISTO)
            return resultado
        except _Cancelado:
            raise
        except _ConexionPerdida as p:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, p.error)
        except Exception as e:  # tras el envío nunca se declara ERROR por un fallo ajeno a la tarea
            _log.exception("Fallo inesperado en el seguimiento de la tarea")
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, _error_inesperado(e))

    def seguir(
        self,
        cfg: ConfiguracionVM,
        upid: str,
        cancelado: threading.Event,
        al_cambiar_etapa: Callable[[Etapa], None] | None = None,
        *,
        inv: Inventario | None = None,
    ) -> ResultadoCreacion:
        """Sigue una tarea ya enviada y la comprueba al terminar (mismos desenlaces que
        ``crear``). Sirve para "Seguir esperando" tras ``TIEMPO_AGOTADO``/``CONEXION_PERDIDA``.

        ``inv`` (opcional) permite resolver el storage del efidisk en los errores de espacio.
        """
        ctx = _Contexto(cancelado=cancelado, upid=upid, inv=inv)
        try:
            return self._seguir_y_comprobar(ctx, cfg, upid, al_cambiar_etapa)
        except _Cancelado:
            return self._cancelado(cfg, upid)

    def comprobar_ahora(
        self, cfg: ConfiguracionVM, upid: str, *, inv: Inventario | None = None
    ) -> ResultadoCreacion:
        """Una sola ronda de consultas, sin espera tolerante. Si la tarea terminó, la
        comprueba con ``config_vm``; si sigue corriendo devuelve ``TIEMPO_AGOTADO`` sin
        esperar; si la red falla, ``CONEXION_PERDIDA`` de inmediato ("Comprobar ahora")."""
        ctx = _Contexto(upid=upid, inv=inv, tolerante=False)
        try:
            estado = self._sesion.cliente.estado_tarea(cfg.nodo, upid)
            if not estado.terminada:
                return self._resultado(
                    Desenlace.TIEMPO_AGOTADO,
                    cfg,
                    upid,
                    ErrorProxLaunch(CodigoError.TAREA_TIEMPO_AGOTADO, {"upid": upid}),
                )
            return self._comprobar(ctx, cfg, upid, estado.exitstatus)
        except _ConexionPerdida as p:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, p.error)
        except ErrorProxLaunch as e:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, e)
        except Exception as e:
            _log.exception("Fallo inesperado al comprobar la tarea")
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, _error_inesperado(e))

    def existe_vm(self, cfg: ConfiguracionVM) -> bool | None:
        """Consulta ``config_vm`` una sola vez, sin espera tolerante.

        ``True`` si la máquina existe, ``False`` si Proxmox dice que no existe y ``None``
        si no se pudo saber (red, permisos, error). Sirve cuando no hay UPID.
        """
        try:
            return self._sesion.cliente.config_vm(cfg.nodo, cfg.vmid) is not None
        except Exception:
            return None

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
        self, ctx: _Contexto, cfg: ConfiguracionVM, upid: str
    ) -> EstadoTarea | ResultadoCreacion:
        """Sondea hasta que la tarea termina. Devuelve el ``EstadoTarea`` o un resultado final."""
        cliente = self._sesion.cliente
        inicio = self._reloj.ahora()
        primer_fallo: float | None = None
        while True:
            if ctx.cancelado is not None and ctx.cancelado.is_set():
                return self._cancelado(cfg, upid)
            try:
                estado = cliente.estado_tarea(cfg.nodo, upid)
            except ErrorProxLaunch as e:
                if e.codigo not in CODIGOS_DE_RED:
                    # Sesión expirada, 403, 500 puntual...: no es el desenlace de la tarea.
                    return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, upid, e)
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

    def _ajustar_storage(
        self, ctx: _Contexto, error: ErrorProxLaunch, cfg: ConfiguracionVM
    ) -> ErrorProxLaunch:
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
            elif ctx.inv is not None:
                efi = storage_efi_efectivo(cfg, ctx.inv)
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
        self, ctx: _Contexto, cfg: ConfiguracionVM, upid: str, exitstatus: str | None
    ) -> ResultadoCreacion:
        """Interpreta el ``exitstatus`` y lo confirma con ``config_vm`` (CA-20.3 a CA-20.5)."""
        cliente = self._sesion.cliente
        exito = (exitstatus or "").strip()
        if exito == "OK" or exito.upper().startswith("WARNINGS"):
            try:
                config = self._tolerante(ctx, lambda: cliente.config_vm(cfg.nodo, cfg.vmid))
            except ErrorProxLaunch as e:
                # No se puede confirmar (p. ej. falta VM.Audit): se informa como aviso.
                log = self._log_seguro(ctx, cfg.nodo, upid)
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
                Desenlace.CON_AVISOS, cfg, upid, None, self._log_seguro(ctx, cfg.nodo, upid)
            )

        # La tarea falló (desenlace definitivo). Si quedó una configuración a medias se
        # informa (CA-20.10). Si ahora falla la red al leer log o config, el resultado
        # sigue siendo ERROR con el error traducido: no cambia lo que ya se sabe.
        error = self._ajustar_storage(ctx, traducir_exitstatus(exitstatus), cfg)
        log = self._log_seguro(ctx, cfg.nodo, upid)
        try:
            config = self._tolerante(ctx, lambda: cliente.config_vm(cfg.nodo, cfg.vmid))
        except _Cancelado:
            raise
        except (ErrorProxLaunch, _ConexionPerdida):
            config = None
        except Exception:
            _log.exception("Fallo inesperado al comprobar la configuración")
            config = None
        desenlace = Desenlace.PARCIAL if config is not None else Desenlace.ERROR
        return self._resultado(desenlace, cfg, upid, error, log)
