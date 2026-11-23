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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final
from urllib.parse import unquote

from proxlaunch.nucleo.api.traductor_errores import CODIGOS_DE_RED, traducir_exitstatus
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import FirewallPlantilla, usa_firewall
from proxlaunch.nucleo.firewall.reglas import parametros_opciones, parametros_regla, regla_ya_existe
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
from proxlaunch.nucleo.red.errores_sdn import anotar_error_red, es_error_digest
from proxlaunch.nucleo.red.modelos import (
    AccionTarjeta,
    TarjetaFinal,
    TarjetaPlantilla,
    usa_red_clon,
)
from proxlaunch.nucleo.red.reescritura import construir_peticion_red, requiere_paso_red
from proxlaunch.nucleo.red.tarjetas import ipconfigs_de_config, tarjetas_de_config
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
# Fase C (0.8): la red del clon (C4/C3) y las dos escrituras del firewall de la MV (C3).
AJUSTE_RED: Final = "red"
AJUSTE_FIREWALL_OPCIONES: Final = "firewall_opciones"
AJUSTE_FIREWALL_REGLA: Final = "firewall_regla"
# Orden en que se aplican los ajustes de una MV (DT-C7); un fallo deja pendiente su paso y los
# siguientes de C y B.
ORDEN_AJUSTES: Final = (
    AJUSTE_ETIQUETAS,
    AJUSTE_ARRANQUE,
    AJUSTE_PROTECCION,
    AJUSTE_CPU_MEMORIA,
    AJUSTE_RED,
    AJUSTE_CLOUDINIT,
    AJUSTE_CONTRASENA,
    AJUSTE_FIREWALL_OPCIONES,
    AJUSTE_FIREWALL_REGLA,
    AJUSTE_DISCO,
)
# Avisos de la fase C (los textos los pone la interfaz); los de ``AVISOS_C_ADVERTENCIA`` pasan una
# MV ``OK`` a ``CON_AVISOS`` (algo pedido no se aplicó o la plantilla ya traía firewall).
AVISO_FIREWALL_GRUPO_YA_ESTABA: Final = "firewall_grupo_ya_estaba"  # «…:<grupo>»
AVISO_FIREWALL_HEREDADO: Final = "firewall_heredado"
AVISO_RED_MAC_NUEVA: Final = "red_mac_nueva"  # «…:netN» (informativo)
AVISO_RED_MTU_IGNORADA: Final = "red_mtu_ignorada"  # «…:netN»
AVISO_RED_TARJETA_ILEGIBLE: Final = "red_tarjeta_ilegible"  # «…:netN»
# Con el firewall pedido, una tarjeta ilegible queda sin ``firewall=1``: la MV no se enciende.
AVISO_FIREWALL_INCOMPLETO_NO_ENCENDIDA: Final = "firewall_incompleto_no_encendida"  # «…:netN»
AVISOS_C_ADVERTENCIA: Final = frozenset(
    {
        AVISO_FIREWALL_HEREDADO,
        AVISO_RED_MTU_IGNORADA,
        AVISO_RED_TARJETA_ILEGIBLE,
        AVISO_FIREWALL_INCOMPLETO_NO_ENCENDIDA,
    }
)
PRIVILEGIO_RED = "VM.Config.Network"
_AJUSTES_B = (AJUSTE_CLOUDINIT, AJUSTE_CONTRASENA)
# Pasos cuyo fallo deja la MV PARCIAL sin pausar el lote (``params["ajuste"]``, DT-C8).
_AJUSTES_SIN_PAUSA = (
    AJUSTE_CLOUDINIT,
    AJUSTE_CONTRASENA,
    AJUSTE_RED,
    AJUSTE_FIREWALL_OPCIONES,
    AJUSTE_FIREWALL_REGLA,
)
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
    # Fase C: resultado del paso de red y avisos de C acumulados durante los ajustes.
    red_final: tuple[TarjetaFinal, ...] = ()
    avisos_c: list[str] = field(default_factory=list)
    # MAC original de cada tarjeta del clon (índice -> MAC), leída antes de tocar su red. Viene
    # del libro (persiste entre llamadas y reconexiones) y se vuelca al libro con ``al_leer_macs``.
    macs_originales: dict[int, str] = field(default_factory=dict)
    al_leer_macs: Callable[[Mapping[int, str]], None] | None = None


class _DigestCambiado(Exception):
    """Interna: el ``PUT`` de red falló por ``digest`` caducado (la config cambió)."""


class _EnvioIncierto(Exception):
    """Interna: el ``PUT`` de red falló por la red; puede haber llegado al servidor."""

    def __init__(self, error: ErrorProxLaunch) -> None:
        super().__init__(str(error.codigo))
        self.error = error


# Rondas máximas del paso de red cuando un ``PUT`` de red queda incierto (se relee y se decide).
_RONDAS_RED_INCIERTAS = 3


@dataclass(frozen=True)
class _PasosC:
    """Pasos de la fase C que toca ejecutar en esta llamada (DT-C7, DT-C9)."""

    red: bool = False
    opciones: bool = False
    regla: bool = False
    verificar_regla: bool = False  # ``GET …/firewall/rules`` del clon antes del ``POST``

    @property
    def alguno(self) -> bool:
        return self.red or self.opciones or self.regla


_SIN_PASOS_C = _PasosC()


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


def ajustes_planeados(cfg: ConfiguracionVM) -> tuple[str, ...]:
    """Ajustes de la fase B y C que el plan de ``cfg`` aplicará tras crear (en ``ORDEN_AJUSTES``).

    Para el informe y la simulación: «aplicados» = estos menos los ``ajuste_pendiente:*``. No
    incluye los ajustes que dependen de la config de la plantilla (etiquetas, arranque, CPU,
    memoria y disco de un clon): esos solo se conocen al ejecutar.
    """
    planeados: set[str] = set()
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        if requiere_paso_red(cfg):
            planeados.add(AJUSTE_RED)
        ci = cfg.cloudinit
        if ci is not None:
            if not ci.vacia:
                planeados.add(AJUSTE_CLOUDINIT)
            if ci.contrasena is not None:
                planeados.add(AJUSTE_CONTRASENA)
    fw = cfg.firewall
    if fw is not None and usa_firewall(fw):
        planeados.add(AJUSTE_FIREWALL_OPCIONES)
        if fw.grupo:
            planeados.add(AJUSTE_FIREWALL_REGLA)
    return tuple(n for n in ORDEN_AJUSTES if n in planeados)


def ipconfigs_de_plantilla(detalle: DetallePlantilla | None) -> frozenset[int]:
    """Índices ``N`` de los ``ipconfigN`` que la plantilla ya trae (para simular ``delete=``)."""
    if detalle is None or detalle.cloudinit is None:
        return frozenset()
    return frozenset(
        int(k.removeprefix("ipconfig"))
        for k in detalle.cloudinit.heredados
        if k.startswith("ipconfig") and k.removeprefix("ipconfig").isdigit()
    )


def _avisos_ilegibles(cfg: ConfiguracionVM, tarjetas: Sequence[TarjetaPlantilla]) -> list[str]:
    """``red_tarjeta_ilegible:netN`` de las tarjetas ilegibles que el plan iba a tocar."""
    red = cfg.red_clon if usa_red_clon(cfg.red_clon) else None
    avisos: list[str] = []
    for t in tarjetas:
        if t.legible:
            continue
        pedido = red.tarjeta(t.indice) if red is not None else None
        toca = usa_firewall(cfg.firewall) or (
            pedido is not None and pedido.accion != AccionTarjeta.CONSERVAR
        )
        if toca:
            avisos.append(f"{AVISO_RED_TARJETA_ILEGIBLE}:net{t.indice}")
    return avisos


def avisos_red_planeados(
    cfg: ConfiguracionVM,
    tarjetas: Sequence[TarjetaPlantilla],
    ipconfigs: frozenset[int] = frozenset(),
) -> tuple[str, ...]:
    """Avisos de red que dará el plan sobre las tarjetas de la plantilla (sin escribir nada).

    Sirve a la simulación y al Resumen (arquitectura §9, pregunta 1): una tarjeta ilegible que el
    plan iba a tocar queda sin tocar y se avisa ANTES de crear. Vacío sin paso de red.
    """
    if not requiere_paso_red(cfg):
        return ()
    avisos: list[str] = []
    try:
        peticion = construir_peticion_red(cfg, tarjetas, ipconfigs, None)
    except ErrorProxLaunch:
        peticion = None  # índice ocupado: el motivo lo da la ejecución (RED_PLANTILLA_CAMBIADA)
    if peticion is not None:
        avisos.extend(peticion.avisos)
    ilegibles = _avisos_ilegibles(cfg, tarjetas)
    avisos.extend(ilegibles)
    if cfg.encender and usa_firewall(cfg.firewall):
        avisos.extend(_avisos_no_encendida(ilegibles))
    return tuple(dict.fromkeys(avisos))


def _avisos_no_encendida(ilegibles: Sequence[str]) -> list[str]:
    """Un ``firewall_incompleto_no_encendida:netN`` por cada ``red_tarjeta_ilegible:netN``."""
    return [
        f"{AVISO_FIREWALL_INCOMPLETO_NO_ENCENDIDA}:{a.split(':', 1)[1]}"
        for a in ilegibles
        if a.startswith(f"{AVISO_RED_TARJETA_ILEGIBLE}:")
    ]


def firewall_de_plantilla(cfg: ConfiguracionVM, inv: Inventario | None) -> FirewallPlantilla | None:
    """Lo leído en «Comprobar» del firewall de la plantilla del clon; ``None`` si no consta."""
    if cfg.origen != OrigenSO.CLONAR_PLANTILLA or inv is None or inv.catalogo is None:
        return None
    info = inv.catalogo.firewall
    vmid = getattr(getattr(cfg.detalle_origen, "plantilla", None), "vmid", None)
    if info is None or not isinstance(vmid, int):
        return None
    return info.plantillas.get(vmid)


def avisos_firewall_planeados(cfg: ConfiguracionVM, inv: Inventario | None) -> tuple[str, ...]:
    """``firewall_heredado`` y ``firewall_grupo_ya_estaba:<g>`` según la plantilla del clon."""
    fw = cfg.firewall
    plantilla = firewall_de_plantilla(cfg, inv)
    if fw is None or not usa_firewall(fw) or plantilla is None or not plantilla.legible:
        return ()
    avisos: list[str] = []
    if plantilla.activo is True or plantilla.con_reglas is True:
        avisos.append(AVISO_FIREWALL_HEREDADO)
    if fw.grupo and fw.grupo in plantilla.grupos:
        avisos.append(f"{AVISO_FIREWALL_GRUPO_YA_ESTABA}:{fw.grupo}")
    return tuple(avisos)


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
        macs_originales: Mapping[int, str] | None = None,
        al_leer_macs: Callable[[Mapping[int, str]], None] | None = None,
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

        ``macs_originales`` y ``al_leer_macs`` (fase C) llevan la MAC original de cada tarjeta del
        clon desde y hacia el libro: así «MAC nueva» no se repite en un reintento (RF-C4.8).
        """
        ctx = _Contexto(cancelado=cancelado, inv=inv, al_leer_macs=al_leer_macs)
        ctx.macs_originales.update(macs_originales or {})
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
            nuevas = {i: r.bridge for i, r in enumerate(cfg.redes)}
            e = anotar_error_red(e, paso="crear", antiguas={}, nuevas=nuevas)  # 403 de SDN.Use
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
            antiguas = (
                {t.indice: t.bridge for t in plantilla.tarjetas if t.bridge} if plantilla else {}
            )
            e = anotar_error_red(e, paso="clon", antiguas=antiguas, nuevas={})  # la PLANTILLA
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
        macs_originales: Mapping[int, str] | None = None,
        al_leer_macs: Callable[[Mapping[int, str]], None] | None = None,
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

        ``macs_originales`` y ``al_leer_macs`` (fase C): ver ``crear``.
        """
        ctx = _Contexto(cancelado=cancelado, inv=inv, al_leer_macs=al_leer_macs)
        ctx.macs_originales.update(macs_originales or {})
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
            if cfg.origen not in (
                OrigenSO.CLONAR_PLANTILLA,
                OrigenSO.IMPORTAR_DISCO,
            ) and not usa_firewall(cfg.firewall):
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
        con_firewall = usa_firewall(cfg.firewall)
        if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
            pass
        elif cfg.origen == OrigenSO.IMPORTAR_DISCO:
            if not (self._pide_ampliar(cfg) or con_firewall):
                return resultado
        elif not con_firewall:  # disco vacío e ISO solo necesitan ajustes con firewall (§3.3)
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
        pasos = self._pasos_c(ctx, cfg, pendientes, reintento=reintento)
        pendientes_lectura: list[str] = []
        lista: list[str]
        error: ErrorProxLaunch | None = None
        if solo_lectura:
            if ajustes.config:
                pendientes_lectura += _nombres_ajuste(ajustes.config)
            if pasos.red and self._red_pendiente(ctx, cfg, config):
                pendientes_lectura.append(AJUSTE_RED)
            if ajustes.cloudinit or sin_unidad:
                pendientes_lectura.append(AJUSTE_CLOUDINIT)
            if ajustes.contrasena is not None:
                pendientes_lectura.append(AJUSTE_CONTRASENA)
            if pasos.alguno:
                pendientes_lectura += self._firewall_pendiente(cfg, pasos)
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
            or pasos.alguno
        ):
            lista, error = self._enviar_ajustes(
                ctx, cfg, ajustes, sin_unidad=sin_unidad, pasos=pasos
            )
        else:
            lista = []
        if olvidada:  # la contraseña pendiente ya no está en memoria: hay que volver a escribirla
            lista.append(AJUSTE_CONTRASENA)
            error = error or ErrorProxLaunch(
                CodigoError.CONTRASENA_OLVIDADA, {"nombre": cfg.nombre}
            )
        avisos = self._avisos_con_c(ctx, cfg, avisos)
        return self._con_c(ctx, self._con_ajustes(resultado, avisos, lista, error, omitido))

    # --- Fase C: pasos, avisos y estado ------------------------------------------------

    @staticmethod
    def _pasos_c(
        ctx: _Contexto,
        cfg: ConfiguracionVM,
        pendientes: frozenset[str] | None,
        *,
        reintento: bool,
    ) -> _PasosC:
        """Qué pasos de C se ejecutan: los del plan y, con ``pendientes``, solo esos (DT-C9).

        La regla de grupo no se envía si la plantilla ya la traía (CA-C3.6.2); se comprueba con
        ``GET …/firewall/rules`` antes del ``POST`` en un reintento o si el firewall de la plantilla
        no se pudo leer (DT-C10). Un origen ``POST`` envía la regla directamente.
        """

        def toca(nombre: str) -> bool:
            return pendientes is None or nombre in pendientes

        fw = cfg.firewall
        red = requiere_paso_red(cfg) and toca(AJUSTE_RED)
        if fw is None or not usa_firewall(fw):
            return _PasosC(red=red)
        plantilla = firewall_de_plantilla(cfg, ctx.inv)
        legible = plantilla is not None and plantilla.legible
        ya_estaba = bool(
            legible
            and plantilla is not None
            and fw.grupo is not None
            and fw.grupo in plantilla.grupos
        )
        regla = bool(fw.grupo) and toca(AJUSTE_FIREWALL_REGLA) and not ya_estaba
        clon = cfg.origen == OrigenSO.CLONAR_PLANTILLA
        return _PasosC(
            red=red,
            opciones=toca(AJUSTE_FIREWALL_OPCIONES),
            regla=regla,
            verificar_regla=reintento or (clon and not legible),
        )

    @staticmethod
    def _avisos_con_c(
        ctx: _Contexto, cfg: ConfiguracionVM, avisos: tuple[str, ...]
    ) -> tuple[str, ...]:
        """Suma a ``avisos`` los de C: los del paso de red y los del firewall de la plantilla."""
        nuevos = (*ctx.avisos_c, *avisos_firewall_planeados(cfg, ctx.inv))
        return tuple(dict.fromkeys((*avisos, *nuevos)))

    @staticmethod
    def _con_c(ctx: _Contexto, resultado: ResultadoCreacion) -> ResultadoCreacion:
        """Añade ``red_final`` y pasa ``OK`` a ``CON_AVISOS`` si hay un aviso de C que advierte."""
        if ctx.red_final:
            resultado = replace(resultado, red_final=ctx.red_final)
        advierte = any(a.split(":", 1)[0] in AVISOS_C_ADVERTENCIA for a in resultado.avisos)
        if resultado.desenlace == Desenlace.OK and advierte:
            resultado = replace(resultado, desenlace=Desenlace.CON_AVISOS)
        return resultado

    def _red_pendiente(
        self, ctx: _Contexto, cfg: ConfiguracionVM, config: Mapping[str, Any] | None
    ) -> bool:
        """Solo lectura: ¿la config del clon aún difiere de lo que escribiría el paso de red?"""
        if config is None:
            return True  # sin leerla no se puede afirmar que esté aplicado
        try:
            peticion = construir_peticion_red(
                cfg,
                tarjetas_de_config(config),
                ipconfigs_de_config(config),
                None,
                ctx.macs_originales,
            )
        except ErrorProxLaunch:
            return True
        return peticion is not None

    def _firewall_pendiente(self, cfg: ConfiguracionVM, pasos: _PasosC) -> list[str]:
        """Solo lectura: pasos de firewall que el servidor aún no refleja (lecturas de la MV).

        Si una lectura falla no se puede afirmar que esté aplicado: queda como pendiente.
        """
        fw = cfg.firewall
        if fw is None:
            return []
        cliente = self._sesion.cliente
        pendientes: list[str] = []
        if pasos.opciones:
            try:
                actuales = cliente.opciones_firewall_vm(cfg.nodo, cfg.vmid)
                # ``dhcp=0`` se da por aplicado si la clave falta (el valor por defecto es 0).
                faltan = any(
                    str(actuales.get(k, "0" if k == "dhcp" else None)) != v
                    for k, v in parametros_opciones(fw, cfg).items()
                )
            except Exception:
                faltan = True
            if faltan:
                pendientes.append(AJUSTE_FIREWALL_OPCIONES)
        if pasos.regla and fw.grupo:
            try:
                existe = regla_ya_existe(cliente.reglas_firewall_vm(cfg.nodo, cfg.vmid), fw.grupo)
            except Exception:
                existe = False
            if not existe:
                pendientes.append(AJUSTE_FIREWALL_REGLA)
        return pendientes

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
        sin_firewall = self._tarjetas_sin_firewall(ctx, cfg)
        if sin_firewall:
            # SEG-C-M2: con el firewall pedido no se enciende una MV con una tarjeta sin protección.
            avisos = tuple(dict.fromkeys((*resultado.avisos, *sin_firewall)))
            return replace(resultado, desenlace=Desenlace.CON_AVISOS, avisos=avisos)
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
    def _tarjetas_sin_firewall(ctx: _Contexto, cfg: ConfiguracionVM) -> list[str]:
        """``firewall_incompleto_no_encendida:netN`` de las tarjetas ilegibles del clon.

        Con el firewall pedido, una tarjeta que no se entiende no se reescribe y queda sin
        ``firewall=1``. Se toma del paso de red de esta llamada o, si no corrió, de la config leída.
        """
        if cfg.origen != OrigenSO.CLONAR_PLANTILLA or not usa_firewall(cfg.firewall):
            return []
        ilegibles = [a for a in ctx.avisos_c if a.startswith(f"{AVISO_RED_TARJETA_ILEGIBLE}:")]
        if ctx.config is not None:
            ilegibles.extend(
                f"{AVISO_RED_TARJETA_ILEGIBLE}:net{t.indice}"
                for t in tarjetas_de_config(ctx.config)
                if not t.legible
            )
        return _avisos_no_encendida(list(dict.fromkeys(ilegibles)))

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
        pasos: _PasosC = _SIN_PASOS_C,
    ) -> tuple[list[str], ErrorProxLaunch | None]:
        """Envía, en este orden, el ``PUT config`` (etiquetas, CPU, memoria…), [C: el ``PUT`` de
        red], el de cloud-init, el de la contraseña, [C: opciones y regla del firewall] y el
        ``PUT resize`` (la marca de propiedad primero, DT-B7; el orden de C es el de DT-C7).

        Devuelve los ajustes que no se aplicaron y el primer error. Cada ``PUT`` es idempotente
        (valores absolutos) y se envía una sola vez. Si falla el ``PUT config``, cloud-init y
        contraseña quedan pendientes sin intentarse; si falla cloud-init o la contraseña, lo que
        sigue también (la contraseña y el disco). ``sin_unidad`` marca cloud-init como pendiente
        con ``CLOUDINIT_SIN_UNIDAD`` sin emitir ningún ``PUT``. Fase C: un fallo de la red o del
        firewall deja pendiente su paso y todos los siguientes (incluido el disco), sin intentarlos.
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
        # Fase C: el ``PUT`` de red va aparte, tras el de ajustes y antes del de cloud-init.
        fallo_c = False
        if pasos.red:
            if fallo_config:
                pendientes.append(AJUSTE_RED)
                fallo_c = True
            else:
                error_red = self._paso_red(ctx, cfg)
                if error_red is not None:
                    pendientes.append(AJUSTE_RED)
                    primero = primero or error_red
                    fallo_c = True
        if ajustes.cloudinit or sin_unidad:
            if sin_unidad:
                pendientes.append(AJUSTE_CLOUDINIT)
                primero = primero or ErrorProxLaunch(
                    CodigoError.CLOUDINIT_SIN_UNIDAD,
                    {"nombre": cfg.nombre, "plantilla": self._nombre_plantilla(cfg)},
                )
                fallo_b = True
            elif fallo_config or fallo_c:
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
            if fallo_config or fallo_c or fallo_b:
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
        # Fase C: firewall de la MV. Cualquier paso pendiente antes lo bloquea (cascada, DT-C7).
        if pasos.opciones or pasos.regla:
            bloqueado = bool(pendientes)
            if pasos.opciones:
                error_fw = None if bloqueado else self._paso_firewall_opciones(ctx, cfg)
                if bloqueado or error_fw is not None:
                    pendientes.append(AJUSTE_FIREWALL_OPCIONES)
                    primero = primero or error_fw
                    bloqueado = True
                    fallo_c = True
            if pasos.regla:
                error_fw = None if bloqueado else self._paso_firewall_regla(ctx, cfg, pasos)
                if bloqueado or error_fw is not None:
                    pendientes.append(AJUSTE_FIREWALL_REGLA)
                    primero = primero or error_fw
                    fallo_c = True
        if ajustes.disco is not None:
            clave, gib = ajustes.disco
            if sin_red or fallo_b or fallo_c:
                pendientes.append(AJUSTE_DISCO)  # sin red o tras un fallo de cloud-init o de C
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

    def _enviar_c(
        self, ctx: _Contexto, enviar: Callable[[], Any], que: str
    ) -> ErrorProxLaunch | None:
        """Una escritura de la fase C, una sola vez y con la tolerancia a la red. Devuelve el error
        crudo (o ``None``); quien llama lo traduce a ajuste pendiente."""
        try:
            self._tolerante(ctx, enviar)
        except _Cancelado:
            raise
        except _ConexionPerdida as p:
            return p.error
        except ErrorProxLaunch as e:
            return e
        except Exception as e:
            _log.exception("Fallo inesperado al aplicar %s", que)
            return _error_inesperado(e)
        return None

    def _paso_red(self, ctx: _Contexto, cfg: ConfiguracionVM) -> ErrorProxLaunch | None:
        """Paso de red del clon (C4/C3, DT-C6): ``GET config`` del clon y un solo ``PUT config``.

        Calcula el ``PUT`` sobre la config DEL CLON recién leída (conserva su MAC). Un fallo del
        ``digest`` relee y reintenta una vez; el segundo es ``RED_CONFIG_CAMBIADA``. Rellena
        ``ctx.red_final`` y ``ctx.avisos_c``. Devuelve el error (ya con ``params["ajuste"]``) o
        ``None`` si quedó aplicado o no había nada que cambiar.
        """
        digest_reintentado = False
        incierto: ErrorProxLaunch | None = None
        for _ in range(_RONDAS_RED_INCIERTAS + 1):
            try:
                self._ronda_red(ctx, cfg)
            except _DigestCambiado:
                if digest_reintentado:
                    return self._error_c(cfg, CodigoError.RED_CONFIG_CAMBIADA, AJUSTE_RED)
                digest_reintentado = True
                continue
            except _EnvioIncierto as e:
                # El ``PUT`` pudo llegar: se relee la config y se decide sobre lo que hay (así
                # «MAC nueva» no se aplica dos veces); no se reenvía a ciegas.
                incierto = e.error
                continue
            except ErrorProxLaunch as e:
                return e
            return None
        if incierto is not None:
            return self._error_ajuste(cfg, incierto, AJUSTE_RED, "config", PRIVILEGIO_RED)
        return self._error_c(cfg, CodigoError.RED_CONFIG_CAMBIADA, AJUSTE_RED)

    def _ronda_red(self, ctx: _Contexto, cfg: ConfiguracionVM) -> None:
        """Una lectura de la config del clon y, si hace falta, su ``PUT`` de red.

        Raises:
            _DigestCambiado: el servidor rechazó el ``PUT`` por ``digest``.
            ErrorProxLaunch: el paso falló (``RED_CONFIG_ILEGIBLE``, ``RED_PLANTILLA_CAMBIADA``, 403
                de SDN anotado, IPAM agotado u otro, ya como error de ajuste).
        """
        cliente = self._sesion.cliente
        try:
            config = self._tolerante(ctx, lambda: cliente.config_vm(cfg.nodo, cfg.vmid))
        except _Cancelado:
            raise
        except (ErrorProxLaunch, _ConexionPerdida):
            config = None
        if config is None:  # V-C21: sin la config del clon no se escribe nada de red
            raise self._error_c(cfg, CodigoError.RED_CONFIG_ILEGIBLE, AJUSTE_RED)
        actuales = tarjetas_de_config(config)
        self._anotar_macs_originales(ctx, actuales)
        digest = config.get("digest")
        try:
            peticion = construir_peticion_red(
                cfg,
                actuales,
                ipconfigs_de_config(config),
                digest if isinstance(digest, str) and digest else None,
                ctx.macs_originales,
            )
        except ErrorProxLaunch as e:  # RED_PLANTILLA_CAMBIADA: el índice a añadir ya está ocupado
            raise self._error_c(cfg, e.codigo, AJUSTE_RED, **e.params) from None
        # Lo que no se entiende no se toca; se avisa aunque no haya nada más que escribir.
        ctx.avisos_c.extend(_avisos_ilegibles(cfg, actuales))
        if peticion is None:
            # Nada que escribir: el informe muestra las tarjetas tal como están (CA-C4.8.2).
            ctx.red_final = tuple(
                TarjetaFinal(
                    t.indice,
                    AccionTarjeta.CONSERVAR,
                    t.modelo,
                    t.bridge,
                    t.vlan,
                    True,
                    t.firewall,
                )
                for t in actuales
                if t.legible
            )
            return
        parametros = peticion.parametros
        error = self._enviar_una_vez(
            ctx, lambda: cliente.configurar_vm(cfg.nodo, cfg.vmid, parametros), AJUSTE_RED
        )
        if error is not None:
            if es_error_digest(error):
                raise _DigestCambiado
            if error.codigo in CODIGOS_DE_RED:
                raise _EnvioIncierto(error)
            error = anotar_error_red(
                error,
                paso="red",
                antiguas={t.indice: t.bridge for t in actuales if t.bridge},
                nuevas={f.indice: f.red for f in peticion.finales if f.red},
            )
            raise self._error_ajuste(cfg, error, AJUSTE_RED, "config", PRIVILEGIO_RED)
        ctx.red_final = peticion.finales
        ctx.avisos_c.extend(peticion.avisos)

    @staticmethod
    def _anotar_macs_originales(ctx: _Contexto, actuales: Sequence[TarjetaPlantilla]) -> None:
        """Guarda la MAC de cada tarjeta legible la primera vez que se lee (y la vuelca al libro).

        La primera lectura del clon es anterior a cualquier ``PUT`` de red de ProxLaunch: esa es
        la MAC original con la que se detecta que «MAC nueva» ya se aplicó (QA-C-M1).
        """
        nuevas = {
            t.indice: t.mac
            for t in actuales
            if t.legible and t.mac and t.indice not in ctx.macs_originales
        }
        if not nuevas:
            return
        ctx.macs_originales.update(nuevas)
        if ctx.al_leer_macs is not None:
            try:
                ctx.al_leer_macs(dict(nuevas))
            except Exception:
                _log.exception("No se pudieron registrar las MAC originales en el libro")

    def _enviar_una_vez(
        self, ctx: _Contexto, enviar: Callable[[], Any], que: str
    ) -> ErrorProxLaunch | None:
        """Una escritura que NO se reenvía por fallo de red (el llamador decide tras releer).

        Devuelve el error crudo (o ``None``); un fallo de red llega tal cual, sin ``_tolerante``.
        """
        if ctx.cancelado is not None and ctx.cancelado.is_set():
            raise _Cancelado
        try:
            enviar()
        except ErrorProxLaunch as e:
            return e
        except Exception as e:
            _log.exception("Fallo inesperado al aplicar %s", que)
            return _error_inesperado(e)
        return None

    @staticmethod
    def _error_c(
        cfg: ConfiguracionVM, codigo: CodigoError, ajuste: str, **params: str
    ) -> ErrorProxLaunch:
        """Error propio de un paso de C: ``nombre`` y ``ajuste`` (así el lote no se pausa)."""
        return ErrorProxLaunch(codigo, {**params, "nombre": cfg.nombre, "ajuste": ajuste})

    def _paso_firewall_opciones(
        self, ctx: _Contexto, cfg: ConfiguracionVM
    ) -> ErrorProxLaunch | None:
        """``PUT …/firewall/options`` de la MV (valores absolutos: idempotente, DT-C9)."""
        fw = cfg.firewall
        if fw is None:
            return None
        cliente = self._sesion.cliente
        parametros = parametros_opciones(fw, cfg)
        error = self._enviar_c(
            ctx,
            lambda: cliente.configurar_firewall_vm(cfg.nodo, cfg.vmid, parametros),
            AJUSTE_FIREWALL_OPCIONES,
        )
        if error is None:
            return None
        return self._error_ajuste(cfg, error, AJUSTE_FIREWALL_OPCIONES, "firewall", PRIVILEGIO_RED)

    def _paso_firewall_regla(
        self, ctx: _Contexto, cfg: ConfiguracionVM, pasos: _PasosC
    ) -> ErrorProxLaunch | None:
        """``POST …/firewall/rules`` con la regla del grupo, sin duplicarla (CA-C3.8.3).

        Con ``pasos.verificar_regla`` lee antes las reglas de la MV (``GET``) y no envía si ya
        está. Si el ``POST`` da 400/404 el grupo ya no existe (``FIREWALL_GRUPO_INEXISTENTE``).
        """
        fw = cfg.firewall
        if fw is None or not fw.grupo:
            return None
        grupo = fw.grupo
        cliente = self._sesion.cliente
        if pasos.verificar_regla:
            reglas: list[Any] = []

            def leer() -> None:
                reglas.extend(cliente.reglas_firewall_vm(cfg.nodo, cfg.vmid))

            error = self._enviar_c(ctx, leer, AJUSTE_FIREWALL_REGLA)
            if error is not None:  # sin poder comprobarlo no se arriesga una regla duplicada
                return self._error_ajuste(
                    cfg, error, AJUSTE_FIREWALL_REGLA, "firewall", PRIVILEGIO_RED
                )
            if regla_ya_existe(reglas, grupo):
                return None
        try:
            cuerpo = parametros_regla(grupo)
        except ValueError:
            return self._error_c(
                cfg, CodigoError.FIREWALL_GRUPO_INEXISTENTE, AJUSTE_FIREWALL_REGLA, grupo=grupo
            )
        # El POST va UNA sola vez: un reenvío tras perder la respuesta duplicaría la regla.
        error = self._enviar_una_vez(
            ctx,
            lambda: cliente.crear_regla_firewall_vm(cfg.nodo, cfg.vmid, cuerpo),
            AJUSTE_FIREWALL_REGLA,
        )
        if error is None:
            return None
        if error.codigo in CODIGOS_DE_RED:
            # Envío incierto: se relee y se decide si la regla ya está (QA-C-A1).
            if self._regla_presente(ctx, cfg, grupo):
                return None
            return self._error_ajuste(cfg, error, AJUSTE_FIREWALL_REGLA, "firewall", PRIVILEGIO_RED)
        grupo_perdido = error.codigo in (
            CodigoError.PARAMETRO_INVALIDO,
            CodigoError.RECURSO_INEXISTENTE,
        ) and (self._grupo_existe(ctx, grupo) is False)
        if grupo_perdido:
            return self._error_c(
                cfg, CodigoError.FIREWALL_GRUPO_INEXISTENTE, AJUSTE_FIREWALL_REGLA, grupo=grupo
            )
        return self._error_ajuste(cfg, error, AJUSTE_FIREWALL_REGLA, "firewall", PRIVILEGIO_RED)

    def _regla_presente(self, ctx: _Contexto, cfg: ConfiguracionVM, grupo: str) -> bool:
        """Relee las reglas de la MV (``GET`` tolerante): ``True`` si la del grupo ya está.

        Si no se puede leer devuelve ``False``: la regla queda pendiente y el reintento
        verifica antes de enviar (nunca se reenvía a ciegas).
        """
        reglas: list[Any] = []
        cliente = self._sesion.cliente

        def leer() -> None:
            reglas.extend(cliente.reglas_firewall_vm(cfg.nodo, cfg.vmid))

        if self._enviar_c(ctx, leer, AJUSTE_FIREWALL_REGLA) is not None:
            return False
        return regla_ya_existe(reglas, grupo)

    def _grupo_existe(self, ctx: _Contexto, grupo: str) -> bool | None:
        """``GET /cluster/firewall/groups``: ¿existe el grupo? ``None`` si no se pudo leer."""
        cliente = self._sesion.cliente
        nombres: list[str] = []

        def leer() -> None:
            nombres.extend(g.nombre for g in cliente.grupos_firewall())

        if self._enviar_c(ctx, leer, AJUSTE_FIREWALL_REGLA) is not None:
            return None
        return grupo in nombres

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
            if ajuste in _AJUSTES_SIN_PAUSA:  # el motor no pausa el lote por estos 403 (§0)
                err.params["ajuste"] = ajuste
            return err
        if err.codigo == CodigoError.RED_SIN_DIRECCIONES:  # IPAM agotado (RF-C4.9): código propio
            return ErrorProxLaunch(
                err.codigo,
                {**err.params, "nombre": cfg.nombre, "ajuste": ajuste},
                err.detalle_tecnico,
            )
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
