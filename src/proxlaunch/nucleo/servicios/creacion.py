"""ServicioCreacion: validar, enviar y seguir la tarea de creación.

Despacha por origen del SO (MVP 4, arquitectura §5): disco vacío, ISO e importación de disco
usan ``POST /nodes/{n}/qemu``; clonar una plantilla usa ``POST …/clone``. Cada MV recibe como
máximo UN envío de creación (INV-L1/INV-O3); los ajustes posteriores son ``PUT`` idempotentes
con valores absolutos y nunca reenvían la creación.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import unquote

from proxlaunch.nucleo.api.traductor_errores import CODIGOS_DE_RED, traducir_exitstatus
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import DetallePlantilla
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleImportacion
from proxlaunch.nucleo.modelos.tarea import Desenlace, EstadoTarea, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Firmware, OrigenSO
from proxlaunch.nucleo.opciones.etiquetas import etiquetas_finales
from proxlaunch.nucleo.origen.clon import (
    AjustesTrasClon,
    PeticionClon,
    construir_ajustes_clon,
    construir_peticion_clon,
    detalle_de_config,
)
from proxlaunch.nucleo.origen.permisos import estado_privilegio, privilegios_cloudinit
from proxlaunch.nucleo.origen.resolucion import espera_maxima_s, nodo_de_upid
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.catalogo import fuente_vigente
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.validacion import Severidad, storage_efi_efectivo, validar_vm

_log = logging.getLogger("proxlaunch.servicios.creacion")

INTERVALO_SONDEO_S = 1.5  # CA-20.1
MAX_ESPERA_S = 600.0  # P-05: 10 min
TOLERANCIA_RED_S = 60.0  # CA-20.7

_GIB = 1024**3
_LOCK_CLONE = "clone"  # config de un clon en curso (I4-§D)
PRIVILEGIO_DISCO = "VM.Config.Disk"
PRIVILEGIO_CLONAR = "VM.Clone"
# Códigos de aviso del MVP 4 (los textos los pone la interfaz).
AVISO_AJUSTE_PENDIENTE = "ajuste_pendiente"  # «ajuste_pendiente:etiquetas|cpu_memoria|disco»
AVISO_AJUSTE_OMITIDO = "ajuste_omitido"  # «ajuste_omitido:disco» (permiso no comprobado)
AVISO_ENCENDIDO_FALLIDO = "encendido_fallido"  # la MV existe pero no se pudo encender (DT-A5)
AVISO_ENCENDIDO_OMITIDO = "encendido_omitido"  # no se enciende porque quedan ajustes pendientes
PRIVILEGIO_ENERGIA = "VM.PowerMgmt"
AJUSTE_ETIQUETAS = "etiquetas"
AJUSTE_ARRANQUE = "arranque"  # onboot y startup
AJUSTE_PROTECCION = "proteccion"  # protection
AJUSTE_CPU_MEMORIA = "cpu_memoria"
AJUSTE_DISCO = "disco"
AJUSTE_CLOUDINIT = "cloudinit"  # fase B: PUT de ciuser, sshkeys, ipconfigN, cicustom, agent…
AJUSTE_CONTRASENA = "contrasena"  # fase B: PUT propio con solo cipassword
_AJUSTES_B = (AJUSTE_CLOUDINIT, AJUSTE_CONTRASENA)
_CLAVES_CPU = ("sockets", "cores", "cpu", "vcpus")
_CLAVES_MEMORIA = ("memory", "balloon")
_CLAVES_OPCIONES = ("tags", "onboot", "startup", "protection")  # exigen VM.Config.Options


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
    # MVP 4: la tarea de un clon corre en el nodo de la plantilla (el del UPID), no en cfg.nodo
    nodo_tarea: str | None = None
    espera: float | None = None  # espera máxima de la tarea; None = la del servicio
    plantilla: DetallePlantilla | None = None  # config de la plantilla leída antes del clon
    config: dict[str, Any] | None = None  # config de la MV creada, leída al comprobar


def _error_inesperado(exc: BaseException) -> ErrorProxLaunch:
    """Envuelve una excepción inesperada sin filtrar el texto completo (solo el tipo)."""
    return ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, type(exc).__name__)


# --- Funciones puras compartidas con la simulación (INV-O12) -------------------------


def clave_primer_disco(cfg: ConfiguracionVM) -> str | None:
    """Clave que ``construir_parametros`` da al primer disco de la MV (``scsi0``, ``sata0``…)."""
    if not cfg.con_disco or not cfg.discos:
        return None
    return f"{cfg.discos[0].bus.value}0"


def disco_seguro(cfg: ConfiguracionVM, inv: Inventario | None) -> bool:
    """``True`` solo si se SABE que el token tiene ``VM.Config.Disk`` (INV-O10).

    Con permisos desconocidos o ausentes no se envía ningún ``resize``.
    """
    permisos = inv.catalogo.permisos if inv is not None and inv.catalogo is not None else None
    return estado_privilegio(permisos, PRIVILEGIO_DISCO, f"/vms/{cfg.vmid}") is True


def ampliacion_importacion(
    cfg: ConfiguracionVM, inv: Inventario | None, tamano_actual_gib: int | None = None
) -> tuple[str, int] | None:
    """``(clave del disco, tamaño absoluto en GiB)`` si hay que ampliar el disco importado.

    Solo si el origen es ``importar_disco`` con ``ampliar_a_gib`` y ese tamaño supera el actual
    (``tamano_actual_gib`` leído de la MV; si no se pasa, el tamaño virtual de la imagen). No mira
    permisos: lo hace quien envía (``disco_seguro``).
    """
    detalle = cfg.detalle_origen
    if cfg.origen != OrigenSO.IMPORTAR_DISCO or not isinstance(detalle, DetalleImportacion):
        return None
    objetivo = detalle.ampliar_a_gib
    clave = clave_primer_disco(cfg)
    if objetivo is None or clave is None:
        return None
    actual = tamano_actual_gib
    if actual is None and detalle.tamano_virtual_bytes is not None:
        actual = -(-detalle.tamano_virtual_bytes // _GIB)  # techo: nunca se subestima
    if actual is not None and objetivo <= actual:
        return None
    return clave, objetivo


def ajustes_de_clon(
    cfg: ConfiguracionVM, inv: Inventario | None, base: DetallePlantilla
) -> tuple[AjustesTrasClon, bool]:
    """Ajustes que siguen a un clon (arquitectura §5.2) y si se omitió el disco por permisos.

    ``base`` es el detalle de la plantilla. Etiquetas = unión plantilla + lote (DT-O14). El
    ``resize`` solo se conserva si ``disco_seguro`` (INV-O10); el segundo valor indica que se
    descartó por eso.
    """
    ajustes = construir_ajustes_clon(cfg, base, etiquetas_finales(cfg))
    if ajustes.disco is not None and not disco_seguro(cfg, inv):
        return replace(ajustes, disco=None), True
    return ajustes, False


def _nombres_ajuste(config: dict[str, str]) -> list[str]:
    """Ajustes (etiquetas, arranque, proteccion, cpu_memoria) que lleva un ``PUT …/config``."""
    nombres: list[str] = []
    if "tags" in config:
        nombres.append(AJUSTE_ETIQUETAS)
    if "onboot" in config or "startup" in config:
        nombres.append(AJUSTE_ARRANQUE)
    if "protection" in config:
        nombres.append(AJUSTE_PROTECCION)
    if any(k in config for k in (*_CLAVES_CPU, *_CLAVES_MEMORIA)):
        nombres.append(AJUSTE_CPU_MEMORIA)
    return nombres


def _privilegio_de_config(config: dict[str, str]) -> str:
    """Privilegio que exige el ``PUT config`` si es inequívoco; vacío si hay varios."""
    privilegios: set[str] = set()
    if any(k in config for k in _CLAVES_OPCIONES):
        privilegios.add("VM.Config.Options")
    if any(k in config for k in _CLAVES_CPU):
        privilegios.add("VM.Config.CPU")
    if any(k in config for k in _CLAVES_MEMORIA):
        privilegios.add("VM.Config.Memory")
    return next(iter(privilegios)) if len(privilegios) == 1 else ""


def _separar_etiquetas(valor: object) -> frozenset[str]:
    return frozenset(t for t in str(valor).replace(",", ";").replace(" ", ";").split(";") if t)


def _separar_startup(valor: object) -> frozenset[str]:
    """``order=1,up=30`` como conjunto de pares (Proxmox puede reordenar las partes)."""
    return frozenset(t.strip() for t in str(valor).split(",") if t.strip())


def _filtrar_ajustes(ajustes: AjustesTrasClon, config: dict[str, Any] | None) -> AjustesTrasClon:
    """Deja solo los ajustes que la MV aún no tiene (los ``PUT`` son idempotentes, CA-O22.6)."""
    if config is None:
        return ajustes
    pendientes: dict[str, str] = {}
    for clave, valor in ajustes.config.items():
        actual = config.get(clave)
        if clave == "tags":
            igual = actual is not None and _separar_etiquetas(actual) == _separar_etiquetas(valor)
        elif clave == "startup":
            igual = actual is not None and _separar_startup(actual) == _separar_startup(valor)
        else:
            igual = actual is not None and str(actual) == valor
        if not igual:
            pendientes[clave] = valor
    disco = ajustes.disco
    if disco is not None:
        actual_bytes = next(
            (d.tamano_bytes for d in detalle_de_config(config).discos if d.clave == disco[0]),
            None,
        )
        if actual_bytes is not None and actual_bytes >= disco[1] * _GIB:
            disco = None
    # Cloud-init y contraseña se conservan tal cual: aquí no se comparan (``_ajustar`` decide).
    return replace(ajustes, config=pendientes, disco=disco)


def _nombre_de_clave(clave: str) -> str | None:
    """Ajuste (``etiquetas``, ``arranque``…) al que pertenece una clave del ``PUT config``."""
    if clave == "tags":
        return AJUSTE_ETIQUETAS
    if clave in ("onboot", "startup"):
        return AJUSTE_ARRANQUE
    if clave == "protection":
        return AJUSTE_PROTECCION
    if clave in (*_CLAVES_CPU, *_CLAVES_MEMORIA):
        return AJUSTE_CPU_MEMORIA
    return None


def _restringir_ajustes(ajustes: AjustesTrasClon, pendientes: frozenset[str]) -> AjustesTrasClon:
    """Deja solo los pasos de ``pendientes`` (reintento de ajustes de la fase B, DT-B7)."""
    config = {k: v for k, v in ajustes.config.items() if _nombre_de_clave(k) in pendientes}
    return AjustesTrasClon(
        config=config,
        disco=ajustes.disco if AJUSTE_DISCO in pendientes else None,
        cloudinit=ajustes.cloudinit if AJUSTE_CLOUDINIT in pendientes else {},
        contrasena=ajustes.contrasena if AJUSTE_CONTRASENA in pendientes else None,
    )


def _mismo_cicustom(a: object, b: str) -> bool:
    """``cicustom`` sin orden: Proxmox puede reordenar los tipos."""
    return {t.strip() for t in str(a).split(",") if t.strip()} == {
        t.strip() for t in b.split(",") if t.strip()
    }


def _cloudinit_aplicado(put: Mapping[str, str], config: Mapping[str, Any]) -> bool:
    """¿La config de la MV ya tiene todo lo que enviaría el ``PUT`` de cloud-init?

    Mejor esfuerzo, solo para reintentos y comprobaciones de solo lectura. ``sshkeys`` se
    compara decodificado; ``agent`` basta que esté activo; ``delete=cicustom`` se cumple si ya
    no hay ``cicustom``.
    """
    for clave, valor in put.items():
        actual = config.get(clave)
        if clave == "delete":
            if config.get(valor) is not None:
                return False
        elif clave == "sshkeys":
            if actual is None or unquote(str(actual)).strip() != unquote(valor).strip():
                return False
        elif clave == "cicustom":
            if actual is None or not _mismo_cicustom(actual, valor):
                return False
        elif clave == "agent":
            texto = str(actual or "")
            if not (texto.startswith("1") or "enabled=1" in texto):
                return False
        elif actual is None or str(actual) != valor:
            return False
    return True


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
        avisos: tuple[str, ...] = (),
    ) -> ResultadoCreacion:
        return ResultadoCreacion(
            desenlace=desenlace,
            vmid=cfg.vmid,
            nodo=cfg.nodo,
            upid=upid,
            error=error,
            log_tarea=log or [],
            avisos=avisos,
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
        puede_enviar: Callable[[], bool] | None = None,
        parametros_extra: Mapping[str, str] | None = None,
    ) -> ResultadoCreacion:
        """Valida, envía y sigue la tarea hasta un desenlace.

        ``al_enviar`` (opcional) recibe el UPID justo después del POST exitoso y antes
        de empezar el sondeo.

        ``puede_enviar`` (opcional) se evalúa justo antes de anunciar ``Etapa.ENVIANDO`` y de
        hacer el POST: si devuelve ``False`` el desenlace es ``CANCELADO`` sin UPID y sin POST
        (así una cancelación o pausa del lote impide enviar una MV que aún validaba).

        ``parametros_extra`` (opcional) se fusiona con los de ``construir_parametros`` solo en el
        ``POST /qemu`` (disco vacío, ISO, importación); el clon lo ignora. Una clave que ya
        existe en los parámetros construidos lanza ``ValueError`` antes de enviar nada.

        Si ``cancelado`` se activa se deja de esperar, sin borrar nada, y el desenlace es
        ``CANCELADO`` (con ``upid`` si la tarea ya se había enviado). Una vez enviada la
        tarea, cualquier fallo que no sea el desenlace de la propia tarea (sesión
        expirada, 403, error puntual, excepción inesperada) da ``CONEXION_PERDIDA`` con
        el ``upid``: no se sabe cómo terminó, así que no se declara un error.
        """
        ctx = _Contexto(cancelado=cancelado, inv=inv)
        try:
            return self._crear(
                ctx, cfg, inv, al_cambiar_etapa, al_enviar, puede_enviar, parametros_extra
            )
        except _Cancelado:
            return self._cancelado(cfg, ctx.upid)

    def _crear(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        inv: Inventario,
        al_cambiar_etapa: Callable[[Etapa], None],
        al_enviar: Callable[[str], None] | None,
        puede_enviar: Callable[[], bool] | None = None,
        parametros_extra: Mapping[str, str] | None = None,
    ) -> ResultadoCreacion:
        """Despacha por origen: el clon usa ``POST …/clone``; el resto, ``POST /qemu``."""
        if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
            return self._crear_por_clon(ctx, cfg, inv, al_cambiar_etapa, al_enviar, puede_enviar)
        return self._crear_por_post(
            ctx, cfg, inv, al_cambiar_etapa, al_enviar, puede_enviar, parametros_extra
        )

    def _validar_local(self, cfg: ConfiguracionVM, inv: Inventario) -> ResultadoCreacion | None:
        """``validar_vm`` (M1 + reglas del origen): un ERROR cierra sin enviar nada."""
        problemas = [
            p
            for p in validar_vm(cfg, inv, self._sesion.capacidades)
            if p.severidad == Severidad.ERROR
        ]
        if not problemas:
            return None
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

    def _validar_vmid(self, ctx: _Contexto, cfg: ConfiguracionVM) -> ResultadoCreacion | None:
        """V-03: ``GET /cluster/nextid?vmid=`` (INV-L2). Cualquier fallo cierra sin enviar."""
        try:
            self._tolerante(ctx, lambda: self._sesion.cliente.proximo_vmid(cfg.vmid))
        except ErrorProxLaunch as e:
            return self._resultado(Desenlace.ERROR, cfg, error=self._con_siguiente_vmid(e))
        except _ConexionPerdida as p:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=p.error)
        return None

    def _crear_por_post(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        inv: Inventario,
        al_cambiar_etapa: Callable[[Etapa], None],
        al_enviar: Callable[[str], None] | None,
        puede_enviar: Callable[[], bool] | None = None,
        parametros_extra: Mapping[str, str] | None = None,
    ) -> ResultadoCreacion:
        """Disco vacío, ISO e importación de disco: un único ``POST /nodes/{n}/qemu``."""
        cliente = self._sesion.cliente
        cancelado = ctx.cancelado
        assert cancelado is not None

        # 1. Validación local, revalidación de la fuente (INV-O8) y comprobación del VMID (V-03).
        al_cambiar_etapa(Etapa.VALIDANDO)
        invalido = self._validar_local(cfg, inv)
        if invalido is not None:
            return invalido
        if cfg.origen != OrigenSO.DISCO_VACIO:
            try:
                perdida = self._tolerante(ctx, lambda: fuente_vigente(cliente, cfg))
            except ErrorProxLaunch as e:
                return self._resultado(Desenlace.ERROR, cfg, error=e)
            except _ConexionPerdida as p:
                return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=p.error)
            if perdida is not None:  # E-O16: la fuente ya no está; no se envía nada
                return self._resultado(Desenlace.ERROR, cfg, error=perdida)
        sin_vmid = self._validar_vmid(ctx, cfg)
        if sin_vmid is not None:
            return sin_vmid
        try:
            parametros = construir_parametros(cfg, inv, self._sesion.capacidades.version)
        except ErrorProxLaunch as e:
            return self._resultado(Desenlace.ERROR, cfg, error=e)
        if parametros_extra:
            repetidas = sorted(k for k in parametros_extra if k in parametros)
            if repetidas:
                raise ValueError(f"parametros_extra repite claves ya construidas: {repetidas}")
            parametros = {**parametros, **parametros_extra}
        if cancelado.is_set():
            return self._cancelado(cfg, None)
        if puede_enviar is not None and not puede_enviar():
            return self._cancelado(cfg, None)

        # 2. Envío. No se reintenta: un POST repetido podría duplicar la operación.
        al_cambiar_etapa(Etapa.ENVIANDO)
        try:
            upid = cliente.crear_vm(cfg.nodo, parametros)
        except ErrorProxLaunch as e:
            return self._fallo_de_envio(cfg, e)
        except Exception as e:  # el POST pudo salir: resultado incierto
            _log.exception("Fallo inesperado al enviar la creación")
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=_error_inesperado(e))
        ctx.upid = upid
        ctx.espera = self._espera_para(cfg, inv)
        _log.info("Creación enviada: vmid=%s nodo=%s upid=%s", cfg.vmid, cfg.nodo, upid)
        if al_enviar is not None:
            al_enviar(upid)
        return self._seguir_y_comprobar(ctx, cfg, upid, al_cambiar_etapa)

    def _fallo_de_envio(
        self,
        cfg: ConfiguracionVM,
        e: ErrorProxLaunch,
        privilegio: str = "VM.Allocate",
        ruta: str | None = None,
    ) -> ResultadoCreacion:
        """Resultado de un envío de creación que falló (mismo tratamiento para POST y clon)."""
        error_envio = self._completar_permiso(self._con_siguiente_vmid(e), cfg, privilegio, ruta)
        desenlace = (
            Desenlace.CONEXION_PERDIDA
            if e.codigo == CodigoError.SERVIDOR_NO_RESPONDE or e.params.get("incierto") == "1"
            else Desenlace.ERROR
        )
        return self._resultado(desenlace, cfg, error=error_envio)

    def _crear_por_clon(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        inv: Inventario,
        al_cambiar_etapa: Callable[[Etapa], None],
        al_enviar: Callable[[str], None] | None,
        puede_enviar: Callable[[], bool] | None = None,
    ) -> ResultadoCreacion:
        """Clon de una plantilla: un único ``POST …/clone`` (cuenta como la creación, INV-L1)."""
        cliente = self._sesion.cliente
        cancelado = ctx.cancelado
        assert cancelado is not None

        # 1. Validación local, revalidación de la plantilla (CA-O21.11) y V-03.
        al_cambiar_etapa(Etapa.VALIDANDO)
        invalido = self._validar_local(cfg, inv)
        if invalido is not None:
            return invalido
        try:
            peticion = construir_peticion_clon(cfg, inv)
        except ErrorProxLaunch as e:
            return self._resultado(Desenlace.ERROR, cfg, error=e)
        try:
            config_plantilla = self._tolerante(
                ctx,
                lambda: cliente.config_vm(peticion.nodo_plantilla, peticion.vmid_plantilla),
            )
        except ErrorProxLaunch as e:
            return self._resultado(Desenlace.ERROR, cfg, error=e)
        except _ConexionPerdida as p:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=p.error)
        plantilla = detalle_de_config(config_plantilla) if config_plantilla is not None else None
        error_plantilla = self._plantilla_invalida(cfg, plantilla)
        if error_plantilla is not None:
            return self._resultado(Desenlace.ERROR, cfg, error=error_plantilla)
        ctx.plantilla = plantilla
        sin_vmid = self._validar_vmid(ctx, cfg)
        if sin_vmid is not None:
            return sin_vmid
        if cancelado.is_set():
            return self._cancelado(cfg, None)
        if puede_enviar is not None and not puede_enviar():
            return self._cancelado(cfg, None)

        # 2. Envío. El clon ES la creación de esta MV: no se reintenta jamás.
        al_cambiar_etapa(Etapa.ENVIANDO)
        try:
            upid = cliente.clonar_vm(
                peticion.nodo_plantilla, peticion.vmid_plantilla, peticion.parametros
            )
        except ErrorProxLaunch as e:
            return self._fallo_de_envio(
                cfg, e, PRIVILEGIO_CLONAR, f"/vms/{peticion.vmid_plantilla}"
            )
        except Exception as e:  # el POST pudo salir: resultado incierto
            _log.exception("Fallo inesperado al enviar el clon")
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=_error_inesperado(e))
        ctx.upid = upid
        ctx.nodo_tarea = self._nodo_de_tarea(cfg, upid, peticion)
        ctx.espera = self._espera_para(cfg, inv)
        _log.info(
            "Clon enviado: vmid=%s nodo=%s plantilla=%s upid=%s",
            cfg.vmid,
            cfg.nodo,
            peticion.vmid_plantilla,
            upid,
        )
        if al_enviar is not None:
            al_enviar(upid)
        return self._seguir_y_comprobar(ctx, cfg, upid, al_cambiar_etapa)

    @staticmethod
    def _plantilla_invalida(
        cfg: ConfiguracionVM, plantilla: DetallePlantilla | None
    ) -> ErrorProxLaunch | None:
        """E-O16/E-O18 si la plantilla desapareció, dejó de serlo o está bloqueada."""
        detalle = cfg.detalle_origen
        nombre = getattr(getattr(detalle, "plantilla", None), "nombre", "")
        if plantilla is None:
            return ErrorProxLaunch(
                CodigoError.FUENTE_DESAPARECIO, {"nombre": nombre, "tipo": "plantilla"}
            )
        if not plantilla.es_plantilla:
            return ErrorProxLaunch(
                CodigoError.CLON_NO_POSIBLE, {"motivo": "no_plantilla", "nombre": nombre}
            )
        if plantilla.bloqueo:
            return ErrorProxLaunch(
                CodigoError.CLON_NO_POSIBLE, {"motivo": "bloqueada", "nombre": nombre}
            )
        return None

    @staticmethod
    def _nodo_de_tarea(cfg: ConfiguracionVM, upid: str, peticion: PeticionClon | None) -> str:
        """Nodo donde corre la tarea de un clon: el del UPID (el de la plantilla)."""
        nodo = nodo_de_upid(upid)
        if nodo:
            return nodo
        return peticion.nodo_plantilla if peticion is not None else cfg.nodo

    def _espera_para(self, cfg: ConfiguracionVM, inv: Inventario | None) -> float:
        """Espera máxima de la tarea: proporcional al tamaño en importación y clon (CA-O17.4)."""
        if cfg.origen == OrigenSO.DISCO_VACIO or inv is None:
            return self._max_espera
        return espera_maxima_s(cfg, inv, self._max_espera)

    def _seguir_y_comprobar(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        upid: str,
        al_cambiar_etapa: Callable[[Etapa], None] | None,
    ) -> ResultadoCreacion:
        """Etapas 3 a 5 de RF-20: sondeo de la tarea, comprobación del resultado y, en clon
        e importación con ampliación, los ajustes posteriores (RF-O18, RF-O22)."""

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
                resultado = self._ajustar(ctx, cfg, resultado, etapa)
                resultado = self._encender_si_procede(ctx, cfg, resultado, etapa)
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

        ``inv`` (opcional) permite resolver el storage del efidisk en los errores de espacio y
        calcular la espera y los ajustes de un clon o una importación.
        """
        ctx = self._contexto_de_tarea(cfg, upid, inv, cancelado=cancelado)
        try:
            return self._seguir_y_comprobar(ctx, cfg, upid, al_cambiar_etapa)
        except _Cancelado:
            return self._cancelado(cfg, upid)

    def _contexto_de_tarea(
        self,
        cfg: ConfiguracionVM,
        upid: str,
        inv: Inventario | None,
        *,
        cancelado: threading.Event | None = None,
        tolerante: bool = True,
    ) -> _Contexto:
        """Contexto para seguir o comprobar una tarea ya enviada (nodo y espera del origen)."""
        ctx = _Contexto(cancelado=cancelado, upid=upid, inv=inv, tolerante=tolerante)
        if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
            ctx.nodo_tarea = self._nodo_de_tarea(cfg, upid, None)
        ctx.espera = self._espera_para(cfg, inv)
        return ctx

    def comprobar_ahora(
        self, cfg: ConfiguracionVM, upid: str, *, inv: Inventario | None = None
    ) -> ResultadoCreacion:
        """Una sola ronda de consultas, sin espera tolerante. Si la tarea terminó, la
        comprueba con ``config_vm``; si sigue corriendo devuelve ``TIEMPO_AGOTADO`` sin
        esperar; si la red falla, ``CONEXION_PERDIDA`` de inmediato ("Comprobar ahora").

        Solo lee: en un clon o importación con ampliación, si faltan ajustes los reporta como
        ``PARCIAL`` (``ajuste_pendiente:*``) sin enviarlos; se reintentan con
        ``reintentar_ajustes``.
        """
        ctx = self._contexto_de_tarea(cfg, upid, inv, tolerante=False)
        try:
            estado = self._sesion.cliente.estado_tarea(ctx.nodo_tarea or cfg.nodo, upid)
            if not estado.terminada:
                return self._resultado(
                    Desenlace.TIEMPO_AGOTADO,
                    cfg,
                    upid,
                    ErrorProxLaunch(CodigoError.TAREA_TIEMPO_AGOTADO, {"upid": upid}),
                )
            resultado = self._comprobar(ctx, cfg, upid, estado.exitstatus)
            if resultado.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS):
                resultado = self._ajustar(ctx, cfg, resultado, None, solo_lectura=True)
            if (
                cfg.encender
                and resultado.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS)
                and AVISO_ENCENDIDO_OMITIDO not in resultado.avisos
            ):
                # QA-A-02: esta ronda solo lee, nunca enciende la máquina.
                resultado.avisos = (*resultado.avisos, AVISO_ENCENDIDO_OMITIDO)
            return resultado
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
        si no se pudo saber (red, permisos, error). Sirve cuando no hay UPID. Un clon que aún
        no llegó a su nodo destino (``target``) vive todavía en el nodo de la plantilla.
        """
        try:
            cliente = self._sesion.cliente
            if cliente.config_vm(cfg.nodo, cfg.vmid) is not None:
                return True
            detalle = cfg.detalle_origen
            otro = getattr(getattr(detalle, "plantilla", None), "nodo", None)
            if cfg.origen == OrigenSO.CLONAR_PLANTILLA and otro and otro != cfg.nodo:
                return cliente.config_vm(otro, cfg.vmid) is not None
            return False
        except Exception:
            return None

    # --- Ajustes posteriores (RF-O18, RF-O22) -------------------------------------------

    def reintentar_ajustes(
        self,
        cfg: ConfiguracionVM,
        inv: Inventario,
        cancelado: threading.Event,
        *,
        pendientes: frozenset[str] | None = None,
    ) -> ResultadoCreacion:
        """Reenvía solo los ``PUT`` de ajuste que la MV aún no tiene (CA-O22.6, Debería).

        Relee la config de la MV, comprueba que es la del plan (mismo ``name`` y sin
        bloqueo), calcula qué falta y lo envía con valores absolutos (idempotente). Nunca
        envía un ``POST`` ni toca otra MV. El llamador (``lote.ajustes``) garantiza que la MV
        está en el libro con su UPID.

        ``pendientes`` (fase B) son los nombres de ajuste (``AJUSTE_*``) que constan como
        pendientes: solo se reenvían esos. La contraseña solo si su nombre está ahí y el
        ``Secreto`` sigue definido; si no, el resultado es ``PARCIAL`` con
        ``ajuste_pendiente:contrasena`` y el error ``CONTRASENA_OLVIDADA``. Con ``None`` se
        reenvía lo que difiera de la config leída (cloud-init y contraseña incluidos, por
        comparación de mejor esfuerzo).
        """
        ctx = _Contexto(cancelado=cancelado, inv=inv)
        try:
            try:
                config = self._tolerante(
                    ctx, lambda: self._sesion.cliente.config_vm(cfg.nodo, cfg.vmid)
                )
            except ErrorProxLaunch as e:
                return self._resultado(Desenlace.ERROR, cfg, error=e)
            except _ConexionPerdida as p:
                return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=p.error)
            params = {"nombre": cfg.nombre, "vmid": str(cfg.vmid), "nodo": cfg.nodo}
            if config is None:
                return self._resultado(
                    Desenlace.ERROR,
                    cfg,
                    error=ErrorProxLaunch(
                        CodigoError.RECURSO_INEXISTENTE,
                        {"recurso": f"vm {cfg.vmid}", "nodo": cfg.nodo},
                    ),
                )
            if config.get("name") != cfg.nombre or config.get("lock"):
                return self._resultado(
                    Desenlace.ERROR,
                    cfg,
                    error=ErrorProxLaunch(CodigoError.ROLLBACK_NO_PROPIA, params),
                )
            ctx.config = config
            base = ResultadoCreacion(Desenlace.OK, cfg.vmid, cfg.nodo, None, None)
            if cfg.origen not in (OrigenSO.CLONAR_PLANTILLA, OrigenSO.IMPORTAR_DISCO):
                return base
            ajustado = self._ajustar(ctx, cfg, base, None, pendientes=pendientes, reintento=True)
            return self._encender_si_procede(ctx, cfg, ajustado, None)
        except _Cancelado:
            return self._cancelado(cfg, None)
        except _ConexionPerdida as p:
            return self._resultado(Desenlace.CONEXION_PERDIDA, cfg, error=p.error)
        except Exception as e:
            _log.exception("Fallo inesperado al reintentar los ajustes")
            return self._resultado(Desenlace.ERROR, cfg, error=_error_inesperado(e))

    def _ajustar(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        resultado: ResultadoCreacion,
        etapa: Callable[[Etapa], None] | None,
        *,
        solo_lectura: bool = False,
        pendientes: frozenset[str] | None = None,
        reintento: bool = False,
    ) -> ResultadoCreacion:
        """Etapa AJUSTANDO: lo que falta tras crear. Un fallo deja ``PARCIAL`` sin reenviar la
        creación (INV-L1); lo omitido por falta de certeza de permisos deja ``CON_AVISOS``.

        Con ``solo_lectura`` calcula lo pendiente y lo reporta sin enviar nada. ``pendientes``
        (fase B) restringe el envío a esos ajustes; ``reintento`` indica que la config leída es
        la de una MV ya ajustada en parte, así que cloud-init y contraseña se comparan con ella.
        """
        if cfg.origen not in (OrigenSO.CLONAR_PLANTILLA, OrigenSO.IMPORTAR_DISCO):
            return resultado
        if cfg.origen == OrigenSO.IMPORTAR_DISCO and not self._pide_ampliar(cfg):
            return resultado
        if etapa is not None:
            etapa(Etapa.AJUSTANDO)
        cliente = self._sesion.cliente
        config = ctx.config
        if config is None:
            try:
                config = self._tolerante(ctx, lambda: cliente.config_vm(cfg.nodo, cfg.vmid))
            except ErrorProxLaunch:
                config = None  # sin leerla se envía todo lo calculado (idempotente)
            except _ConexionPerdida:
                config = None
        omitido = False
        sin_unidad = olvidada = False
        if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
            base = ctx.plantilla
            if base is None and config is not None:
                base = detalle_de_config(config)
            if base is None:
                return resultado  # sin plantilla ni config no hay con qué comparar
            try:
                if solo_lectura and ctx.inv is None:
                    # Sin inventario no se conocen los permisos: se informa lo que falta.
                    ajustes = construir_ajustes_clon(cfg, base, etiquetas_finales(cfg))
                else:
                    ajustes, omitido = ajustes_de_clon(cfg, ctx.inv, base)
            except ErrorProxLaunch as e:
                # Un valor de ajuste inválido (la validación previa debió impedirlo): la MV
                # existe, así que queda PARCIAL en vez de perderse el resultado.
                invalido = ErrorProxLaunch(
                    CodigoError.AJUSTE_POST_CLON_FALLIDO,
                    {"nombre": cfg.nombre, "ajuste": "desconocido", "causa": str(e.codigo)},
                )
                return self._con_ajustes(
                    resultado, tuple(resultado.avisos), ["desconocido"], invalido, False
                )
            ajustes = _filtrar_ajustes(ajustes, config)
            ajustes, sin_unidad, olvidada = self._decidir_fase_b(
                cfg, base, ajustes, config, pendientes, comparar=reintento or solo_lectura
            )
        else:
            actual_gib = None
            if config is not None:
                clave = clave_primer_disco(cfg)
                tam = next(
                    (d.tamano_bytes for d in detalle_de_config(config).discos if d.clave == clave),
                    None,
                )
                actual_gib = -(-tam // _GIB) if tam is not None else None
            ampliacion = ampliacion_importacion(cfg, ctx.inv, actual_gib)
            sin_juicio = solo_lectura and ctx.inv is None
            if ampliacion is not None and not sin_juicio and not disco_seguro(cfg, ctx.inv):
                ampliacion, omitido = None, True
            ajustes = AjustesTrasClon(config={}, disco=ampliacion)
            if pendientes is not None:
                ajustes = _restringir_ajustes(ajustes, pendientes)
        avisos = tuple(resultado.avisos)
        if omitido:
            avisos += (f"{AVISO_AJUSTE_OMITIDO}:{AJUSTE_DISCO}",)
        pendientes_lectura: list[str] = []
        lista: list[str]
        error: ErrorProxLaunch | None = None
        if solo_lectura:
            if ajustes.config:
                pendientes_lectura += _nombres_ajuste(ajustes.config)
            if ajustes.cloudinit or sin_unidad:
                pendientes_lectura.append(AJUSTE_CLOUDINIT)
            if ajustes.contrasena is not None:
                pendientes_lectura.append(AJUSTE_CONTRASENA)
            if ajustes.disco is not None:
                pendientes_lectura.append(AJUSTE_DISCO)
            if pendientes_lectura:
                error = self._error_ajuste_pendiente(cfg, pendientes_lectura)
            lista = pendientes_lectura
        elif (
            ajustes.config
            or ajustes.disco is not None
            or ajustes.cloudinit
            or ajustes.contrasena is not None
            or sin_unidad
        ):
            lista, error = self._enviar_ajustes(ctx, cfg, ajustes, sin_unidad=sin_unidad)
        else:
            lista = []
        if olvidada:  # la contraseña pendiente ya no está en memoria: hay que volver a escribirla
            lista.append(AJUSTE_CONTRASENA)
            error = error or ErrorProxLaunch(
                CodigoError.CONTRASENA_OLVIDADA, {"nombre": cfg.nombre}
            )
        return self._con_ajustes(resultado, avisos, lista, error, omitido)

    def _decidir_fase_b(
        self,
        cfg: ConfiguracionVM,
        base: DetallePlantilla,
        ajustes: AjustesTrasClon,
        config: dict[str, Any] | None,
        pendientes: frozenset[str] | None,
        *,
        comparar: bool,
    ) -> tuple[AjustesTrasClon, bool, bool]:
        """Qué de cloud-init y de la contraseña toca enviar: ``(ajustes, sin_unidad, olvidada)``.

        ``sin_unidad``: la plantilla leída ahora no tiene unidad cloud-init (CA-B0.2.3): no se
        emite el ``PUT`` y el paso queda pendiente. ``olvidada``: la contraseña consta como
        pendiente pero el ``Secreto`` ya no está definido. Con ``pendientes`` solo cuentan esos
        nombres; con ``comparar`` (reintento o solo lectura) se descarta lo que la config ya
        tiene. En la creación normal se envía todo lo calculado.
        """
        ci = cfg.cloudinit
        if ci is None or ci.sin_nada_que_aplicar:
            if pendientes is not None:
                ajustes = _restringir_ajustes(ajustes, pendientes)
            return ajustes, False, False
        info = base.cloudinit
        sin_unidad = info is not None and info.unidad is False
        if sin_unidad:
            # El PUT no se emite; la contraseña (si hay) queda pendiente tras él.
            secreto = ci.contrasena
            if secreto is not None:
                ajustes = replace(ajustes, contrasena=secreto)
        elif comparar and pendientes is None and config is not None:
            if ajustes.cloudinit and _cloudinit_aplicado(ajustes.cloudinit, config):
                ajustes = replace(ajustes, cloudinit={})
            if ajustes.contrasena is not None and config.get("cipassword"):
                ajustes = replace(ajustes, contrasena=None)
        olvidada = False
        if pendientes is not None:
            olvidada = AJUSTE_CONTRASENA in pendientes and ajustes.contrasena is None
            sin_unidad = sin_unidad and AJUSTE_CLOUDINIT in pendientes
            ajustes = _restringir_ajustes(ajustes, pendientes)
        return ajustes, sin_unidad, olvidada

    def _encender_si_procede(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        resultado: ResultadoCreacion,
        etapa: Callable[[Etapa], None] | None,
    ) -> ResultadoCreacion:
        """Etapa ENCENDIENDO (DT-A5): solo si el plan lo pide y los ajustes quedaron completos.

        Con ajustes pendientes (``PARCIAL``) no se enciende y se avisa ``encendido_omitido``.
        Un fallo al encender (también un 403) nunca es un error: la MV existe y queda
        ``CON_AVISOS`` con ``encendido_fallido``, de modo que no pausa el lote.
        """
        if not cfg.encender:
            return resultado
        if resultado.desenlace == Desenlace.PARCIAL:
            resultado.avisos = (*resultado.avisos, AVISO_ENCENDIDO_OMITIDO)
            return resultado
        if resultado.desenlace not in (Desenlace.OK, Desenlace.CON_AVISOS):
            return resultado
        if etapa is not None:
            etapa(Etapa.ENCENDIENDO)
        error: ErrorProxLaunch | None = None
        try:
            # Un solo POST (sin reintentos de red): repetirlo podría chocar con «ya en marcha».
            upid = self._sesion.cliente.iniciar_vm(cfg.nodo, cfg.vmid)
            self._esperar_ajuste(ctx, cfg, upid)
        except _Cancelado:
            raise
        except _ConexionPerdida as p:
            error = p.error
        except ErrorProxLaunch as e:
            error = self._completar_permiso(e, cfg, PRIVILEGIO_ENERGIA)
        except Exception as e:
            _log.exception("Fallo inesperado al encender la máquina")
            error = _error_inesperado(e)
        if error is None:
            return resultado
        _log.info("No se pudo encender la MV %s: %s", cfg.vmid, error.codigo)
        return ResultadoCreacion(
            Desenlace.CON_AVISOS,
            resultado.vmid,
            resultado.nodo,
            resultado.upid,
            resultado.error or error,
            resultado.log_tarea,
            (*resultado.avisos, AVISO_ENCENDIDO_FALLIDO),
        )

    @staticmethod
    def _pide_ampliar(cfg: ConfiguracionVM) -> bool:
        detalle = cfg.detalle_origen
        return isinstance(detalle, DetalleImportacion) and detalle.ampliar_a_gib is not None

    def _con_ajustes(
        self,
        resultado: ResultadoCreacion,
        avisos: tuple[str, ...],
        pendientes: list[str],
        error: ErrorProxLaunch | None,
        omitido: bool,
    ) -> ResultadoCreacion:
        """Desenlace tras los ajustes: ``PARCIAL`` con avisos si algo falló; ``CON_AVISOS`` si
        solo se omitió algo; el mismo resultado si todo se aplicó."""
        if pendientes:
            avisos += tuple(f"{AVISO_AJUSTE_PENDIENTE}:{a}" for a in dict.fromkeys(pendientes))
            return ResultadoCreacion(
                Desenlace.PARCIAL,
                resultado.vmid,
                resultado.nodo,
                resultado.upid,
                error,
                resultado.log_tarea,
                avisos,
            )
        if omitido and resultado.desenlace == Desenlace.OK:
            return ResultadoCreacion(
                Desenlace.CON_AVISOS,
                resultado.vmid,
                resultado.nodo,
                resultado.upid,
                resultado.error,
                resultado.log_tarea,
                avisos,
            )
        resultado.avisos = avisos
        return resultado

    def _error_ajuste_pendiente(
        self, cfg: ConfiguracionVM, pendientes: list[str]
    ) -> ErrorProxLaunch:
        return ErrorProxLaunch(
            CodigoError.AJUSTE_POST_CLON_FALLIDO,
            {
                "nombre": cfg.nombre,
                "ajuste": ",".join(dict.fromkeys(pendientes)),
                "causa": "sin_aplicar",
            },
        )

    def _enviar_ajustes(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        ajustes: AjustesTrasClon,
        *,
        sin_unidad: bool = False,
    ) -> tuple[list[str], ErrorProxLaunch | None]:
        """Envía, en este orden, el ``PUT config`` (etiquetas, CPU, memoria…), el de cloud-init,
        el de la contraseña y el ``PUT resize`` (la marca de propiedad primero, DT-B7).

        Devuelve los ajustes que no se aplicaron y el primer error. Cada ``PUT`` es idempotente
        (valores absolutos) y se envía una sola vez. Si falla el ``PUT config``, cloud-init y
        contraseña quedan pendientes sin intentarse; si falla cloud-init o la contraseña, lo que
        sigue también (la contraseña y el disco). ``sin_unidad`` marca cloud-init como pendiente
        con ``CLOUDINIT_SIN_UNIDAD`` sin emitir ningún ``PUT``.
        """
        cliente = self._sesion.cliente
        pendientes: list[str] = []
        primero: ErrorProxLaunch | None = None
        sin_red = False
        if ajustes.config:
            nombres = _nombres_ajuste(ajustes.config)
            try:
                self._tolerante(
                    ctx, lambda: cliente.configurar_vm(cfg.nodo, cfg.vmid, ajustes.config)
                )
            except (ErrorProxLaunch, _ConexionPerdida) as e:
                err = e.error if isinstance(e, _ConexionPerdida) else e
                sin_red = err.codigo in CODIGOS_DE_RED
                pendientes += nombres
                primero = self._error_ajuste(
                    cfg, err, ",".join(nombres), "config", _privilegio_de_config(ajustes.config)
                )
            except _Cancelado:
                raise
            except Exception as e:
                _log.exception("Fallo inesperado al ajustar la configuración")
                pendientes += nombres
                primero = self._error_ajuste(
                    cfg, _error_inesperado(e), ",".join(nombres), "config", ""
                )
        # Fase B: tras un fallo previo los pasos de cloud-init no se intentan (quedan pendientes).
        fallo_config = bool(pendientes)
        fallo_b = False
        if ajustes.cloudinit or sin_unidad:
            if sin_unidad:
                pendientes.append(AJUSTE_CLOUDINIT)
                primero = primero or ErrorProxLaunch(
                    CodigoError.CLOUDINIT_SIN_UNIDAD,
                    {"nombre": cfg.nombre, "plantilla": self._nombre_plantilla(cfg)},
                )
                fallo_b = True
            elif fallo_config:
                pendientes.append(AJUSTE_CLOUDINIT)
            else:
                fallo_b, sin_red, primero = self._enviar_paso_b(
                    ctx,
                    cfg,
                    AJUSTE_CLOUDINIT,
                    lambda: cliente.configurar_vm(cfg.nodo, cfg.vmid, ajustes.cloudinit),
                    pendientes,
                    primero,
                )
        if ajustes.contrasena is not None:
            secreto = ajustes.contrasena
            if fallo_config or fallo_b:
                pendientes.append(AJUSTE_CONTRASENA)
            elif not secreto.definido:  # se olvidó entre el plan y el envío: no se envía nada
                pendientes.append(AJUSTE_CONTRASENA)
                primero = primero or ErrorProxLaunch(
                    CodigoError.CONTRASENA_OLVIDADA, {"nombre": cfg.nombre}
                )
            else:
                # Único camino a ``Secreto.revelar()``: ``ClienteProxmox.configurar_contrasena``.
                fallo_pw, sin_red_pw, primero = self._enviar_paso_b(
                    ctx,
                    cfg,
                    AJUSTE_CONTRASENA,
                    lambda: cliente.configurar_contrasena(cfg.nodo, cfg.vmid, secreto),
                    pendientes,
                    primero,
                )
                fallo_b = fallo_b or fallo_pw
                sin_red = sin_red or sin_red_pw
        if ajustes.disco is not None:
            clave, gib = ajustes.disco
            if sin_red or fallo_b:
                pendientes.append(AJUSTE_DISCO)  # sin red o tras un fallo de cloud-init
            else:
                try:
                    upid = self._tolerante(
                        ctx, lambda: cliente.ampliar_disco(cfg.nodo, cfg.vmid, clave, gib)
                    )
                    if upid is not None:
                        self._esperar_ajuste(ctx, cfg, upid)
                except (ErrorProxLaunch, _ConexionPerdida) as e:
                    err = e.error if isinstance(e, _ConexionPerdida) else e
                    pendientes.append(AJUSTE_DISCO)
                    nuevo = self._error_ajuste(cfg, err, AJUSTE_DISCO, "resize", PRIVILEGIO_DISCO)
                    primero = primero or nuevo
                except _Cancelado:
                    raise
                except Exception as e:
                    _log.exception("Fallo inesperado al ampliar el disco")
                    pendientes.append(AJUSTE_DISCO)
                    primero = primero or self._error_ajuste(
                        cfg, _error_inesperado(e), AJUSTE_DISCO, "resize", PRIVILEGIO_DISCO
                    )
        return pendientes, primero

    def _enviar_paso_b(
        self,
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        ajuste: str,
        enviar: Callable[[], Any],
        pendientes: list[str],
        primero: ErrorProxLaunch | None,
    ) -> tuple[bool, bool, ErrorProxLaunch | None]:
        """Un ``PUT`` de la fase B (cloud-init o contraseña), una sola vez.

        Devuelve ``(fallo, sin_red, primer_error)``. Un fallo deja el ajuste pendiente. Un 403
        lleva ``params["ajuste"]`` para que el motor no pause el lote (arquitectura §0). Los
        parámetros del error nunca llevan valores enviados (claves, contraseña).
        """
        try:
            self._tolerante(ctx, enviar)
        except _Cancelado:
            raise
        except (ErrorProxLaunch, _ConexionPerdida) as e:
            err = e.error if isinstance(e, _ConexionPerdida) else e
            pendientes.append(ajuste)
            nuevo = self._error_ajuste(cfg, err, ajuste, "config", self._privilegio_b())
            return True, err.codigo in CODIGOS_DE_RED, primero or nuevo
        except Exception as e:
            _log.exception("Fallo inesperado al aplicar %s", ajuste)
            pendientes.append(ajuste)
            nuevo = self._error_ajuste(cfg, _error_inesperado(e), ajuste, "config", "")
            return True, False, primero or nuevo
        return False, False, primero

    def _privilegio_b(self) -> str:
        """Privilegio que se infiere de un 403 sin nombre en un ``PUT`` de cloud-init."""
        return privilegios_cloudinit(self._sesion.capacidades)[0]

    @staticmethod
    def _nombre_plantilla(cfg: ConfiguracionVM) -> str:
        return str(getattr(getattr(cfg.detalle_origen, "plantilla", None), "nombre", ""))

    def _esperar_ajuste(self, ctx: _Contexto, cfg: ConfiguracionVM, upid: str) -> None:
        """Si el ``resize`` devolvió una tarea, la sigue; un fallo o tiempo agotado lanza
        ``ErrorProxLaunch`` (el ajuste queda pendiente, es idempotente)."""
        sub = _Contexto(
            cancelado=ctx.cancelado,
            upid=upid,
            inv=ctx.inv,
            tolerante=ctx.tolerante,
            nodo_tarea=nodo_de_upid(upid) or cfg.nodo,
            espera=self._max_espera,
        )
        final = self._seguir(sub, cfg, upid)
        if isinstance(final, ResultadoCreacion):
            if final.desenlace == Desenlace.CANCELADO:
                raise _Cancelado
            raise final.error or ErrorProxLaunch(CodigoError.TAREA_TIEMPO_AGOTADO, {"upid": upid})
        exito = (final.exitstatus or "").strip()
        if not (exito == "OK" or exito.upper().startswith("WARNINGS")):
            raise traducir_exitstatus(final.exitstatus)

    @staticmethod
    def _error_ajuste(
        cfg: ConfiguracionVM, err: ErrorProxLaunch, ajuste: str, via: str, privilegio: str
    ) -> ErrorProxLaunch:
        """Un 403 conserva su código (E-O20, con privilegio y ``via``); el resto es E-O24."""
        if err.codigo == CodigoError.PERMISO_INSUFICIENTE:
            if not err.params.get("privilegio") and privilegio:
                err.params["privilegio"] = privilegio
                err.params["inferido"] = "1"
            err.params.setdefault("ruta", f"/vms/{cfg.vmid}")
            err.params["via"] = via
            if ajuste in _AJUSTES_B:  # el motor no pausa el lote por estos 403 (arquitectura §0)
                err.params["ajuste"] = ajuste
            return err
        params = {"nombre": cfg.nombre, "ajuste": ajuste, "causa": str(err.codigo)}
        if ajuste in _AJUSTES_B:
            # Solo nombres de parámetro o de snippet (``ipconfig0``, ``local:snippets/x``).
            for clave in ("campo", "snippet"):
                if err.params.get(clave):
                    params[clave] = err.params[clave]
        return ErrorProxLaunch(CodigoError.AJUSTE_POST_CLON_FALLIDO, params, err.detalle_tecnico)

    @staticmethod
    def _completar_permiso(
        error: ErrorProxLaunch,
        cfg: ConfiguracionVM,
        privilegio: str = "VM.Allocate",
        ruta: str | None = None,
    ) -> ErrorProxLaunch:
        """Un 403 real al crear llega sin (ruta, privilegio): se infiere ``VM.Allocate`` en
        ``/vms/{vmid}`` (``VM.Clone`` en la plantilla para un clon) y se marca ``inferido="1"``."""
        if error.codigo == CodigoError.PERMISO_INSUFICIENTE and not error.params.get("privilegio"):
            error.params["privilegio"] = privilegio
            error.params["ruta"] = ruta or f"/vms/{cfg.vmid}"
            error.params["inferido"] = "1"
        return error

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
        """Sondea hasta que la tarea termina. Devuelve el ``EstadoTarea`` o un resultado final.

        La tarea se sondea en el nodo del UPID (``ctx.nodo_tarea``; para un clon, el de la
        plantilla) y con la espera máxima de la llamada (proporcional al tamaño, CA-O17.4).
        """
        cliente = self._sesion.cliente
        nodo = ctx.nodo_tarea or cfg.nodo
        espera = ctx.espera if ctx.espera is not None else self._max_espera
        inicio = self._reloj.ahora()
        primer_fallo: float | None = None
        while True:
            if ctx.cancelado is not None and ctx.cancelado.is_set():
                return self._cancelado(cfg, upid)
            try:
                estado = cliente.estado_tarea(nodo, upid)
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
            if self._reloj.ahora() - inicio >= espera:
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
        if error.codigo != CodigoError.SIN_ESPACIO or cfg.origen == OrigenSO.CLONAR_PLANTILLA:
            return error  # en un clon los discos son los de la plantilla, no los del formulario
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

    def _leer_config(self, ctx: _Contexto, cfg: ConfiguracionVM) -> dict[str, Any] | None:
        """``config_vm`` de la MV con la espera tolerante a la red. Un clon que aún no llegó a
        su nodo destino (``target``) se busca también en el nodo de la plantilla."""
        cliente = self._sesion.cliente
        config = self._tolerante(ctx, lambda: cliente.config_vm(cfg.nodo, cfg.vmid))
        if config is None and cfg.origen == OrigenSO.CLONAR_PLANTILLA:
            otro = getattr(getattr(cfg.detalle_origen, "plantilla", None), "nodo", None)
            if otro and otro != cfg.nodo:
                config = self._tolerante(ctx, lambda: cliente.config_vm(otro, cfg.vmid))
        return config

    def _esperar_fin_de_clon(
        self, ctx: _Contexto, cfg: ConfiguracionVM, config: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Tras la tarea ``qmclone`` espera a que la MV deje de tener ``lock: clone`` (CA-O21.4),
        dentro de la espera máxima. Sin espera tolerante (``comprobar_ahora``) no espera."""
        if cfg.origen != OrigenSO.CLONAR_PLANTILLA or not ctx.tolerante:
            return config
        espera = ctx.espera if ctx.espera is not None else self._max_espera
        inicio = self._reloj.ahora()
        while config is not None and config.get("lock") == _LOCK_CLONE:
            if self._reloj.ahora() - inicio >= espera:
                break
            self._reloj.dormir(self._intervalo)
            config = self._leer_config(ctx, cfg)
        return config

    def _comprobar(
        self, ctx: _Contexto, cfg: ConfiguracionVM, upid: str, exitstatus: str | None
    ) -> ResultadoCreacion:
        """Interpreta el ``exitstatus`` y lo confirma con ``config_vm`` (CA-20.3 a CA-20.5)."""
        exito = (exitstatus or "").strip()
        nodo_tarea = ctx.nodo_tarea or cfg.nodo
        if exito == "OK" or exito.upper().startswith("WARNINGS"):
            try:
                config = self._esperar_fin_de_clon(ctx, cfg, self._leer_config(ctx, cfg))
            except ErrorProxLaunch as e:
                # No se puede confirmar (p. ej. falta VM.Audit): se informa como aviso.
                log = self._log_seguro(ctx, nodo_tarea, upid)
                return self._resultado(Desenlace.CON_AVISOS, cfg, upid, e, log)
            if config is None:
                error = ErrorProxLaunch(
                    CodigoError.RECURSO_INEXISTENTE,
                    {"recurso": f"vm {cfg.vmid}", "nodo": cfg.nodo},
                    f"la tarea terminó con '{exito}' pero la máquina no existe",
                )
                return self._resultado(Desenlace.ERROR, cfg, upid, error)
            if cfg.origen == OrigenSO.CLONAR_PLANTILLA and config.get("lock") == _LOCK_CLONE:
                # La tarea acabó pero la MV sigue bloqueada: aún no se puede ajustar (CA-O21.4).
                return self._resultado(
                    Desenlace.TIEMPO_AGOTADO,
                    cfg,
                    upid,
                    ErrorProxLaunch(CodigoError.TAREA_TIEMPO_AGOTADO, {"upid": upid}),
                )
            ctx.config = config
            if exito == "OK":
                return self._resultado(Desenlace.OK, cfg, upid)
            return self._resultado(
                Desenlace.CON_AVISOS, cfg, upid, None, self._log_seguro(ctx, nodo_tarea, upid)
            )

        # La tarea falló (desenlace definitivo). Si quedó una configuración a medias se
        # informa (CA-20.10). Si ahora falla la red al leer log o config, el resultado
        # sigue siendo ERROR con el error traducido: no cambia lo que ya se sabe.
        error = self._ajustar_storage(ctx, traducir_exitstatus(exitstatus), cfg)
        log = self._log_seguro(ctx, nodo_tarea, upid)
        try:
            config = self._leer_config(ctx, cfg)
        except _Cancelado:
            raise
        except (ErrorProxLaunch, _ConexionPerdida):
            config = None
        except Exception:
            _log.exception("Fallo inesperado al comprobar la configuración")
            config = None
        desenlace = Desenlace.PARCIAL if config is not None else Desenlace.ERROR
        return self._resultado(desenlace, cfg, upid, error, log)
