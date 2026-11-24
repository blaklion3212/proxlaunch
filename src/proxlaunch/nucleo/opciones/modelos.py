"""Modelos de las opciones de la fase A: estado de cada opción, contexto de notas, pools y política
de etiquetas del centro de datos, y opciones de lote."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from proxlaunch.nucleo.cloudinit.modelos import CloudInitParcial, ConfigCloudInit
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.firewall.modelos import FirewallMV, FirewallParcial
from proxlaunch.nucleo.red.modelos import RedClon

if TYPE_CHECKING:  # solo para anotaciones: evita ciclos con ``catalogo`` y ``capacidades_origen``
    from proxlaunch.nucleo.cloudinit.disponibilidad import OpcionB
    from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
    from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad


class OpcionA(StrEnum):
    """Opciones nuevas de la fase A cuya disponibilidad depende de permisos o versión."""

    ENCENDER = "encender"
    ARRANQUE_AUTO = "arranque_auto"
    ARRANQUE_ORDEN = "arranque_orden"
    NOTAS = "notas"
    ETIQUETAS = "etiquetas"
    POOL = "pool"
    MTU = "mtu"
    LIMITE_RED = "limite_red"
    PROTEGER = "proteger"


class OpcionC(StrEnum):
    """Opciones de la fase C cuya disponibilidad depende de permisos o versión."""

    INVENTARIO = "inventario"
    VNETS = "vnets"
    FIREWALL = "firewall"
    FIREWALL_GENERAL = "firewall_general"
    RED_CLON = "red_clon"
    IP_INVENTARIO = "ip_inventario"


class OpcionD(StrEnum):
    """Opciones de la fase D cuya disponibilidad depende de permisos o versión."""

    MAPEOS = "mapeos"
    CPU_PERSONALIZADA = "cpu_personalizada"
    CONSERVAR_MAC = "conservar_mac"


@dataclass(frozen=True)
class EstadoOpcion:
    """Estado de una opción. ``codigo``: ``OPCION_SIN_PRIVILEGIO``, ``OPCION_SIN_VERSION`` o
    ``POOLS_*``. ``params``: privilegio, ruta, version, opcion, motivo."""

    opcion: OpcionA | OpcionB | OpcionC | OpcionD
    disponibilidad: Disponibilidad
    codigo: CodigoError | None = None
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextoNotas:
    """Datos para el bloque automático de las notas."""

    version_app: str
    fecha: datetime  # de ``RelojCalendario``
    id_lote: str | None  # None = MV individual (la línea se omite)
    perfil: str | None  # None = sin perfil (la línea se omite)
    usuario: str | None  # ya recortado a ``usuario@realm``


class EstadoPools(StrEnum):
    OK = "ok"
    SIN_PERMISO = "sin_permiso"  # sin Pool.Audit: la lista llega vacía en silencio
    DESCONOCIDO = "desconocido"  # lista vacía y permisos desconocidos
    ERROR = "error"  # falló ``GET /pools``
    NO_LEIDO = "no_leido"


@dataclass(frozen=True)
class PoolsServidor:
    estado: EstadoPools
    ids: tuple[str, ...] = ()


PERMISOS_ETIQUETAS = ("none", "list", "existing", "free")


def _lista_de(valor: Any, campo: str) -> tuple[str, ...]:
    """Convierte una lista (de la API) o una cadena separada por ``;``/``,`` en tupla de textos."""
    if valor is None:
        return ()
    if isinstance(valor, str):
        return tuple(t.strip() for t in valor.replace(",", ";").split(";") if t.strip())
    if isinstance(valor, (list, tuple)) and all(isinstance(t, str) for t in valor):
        return tuple(t.strip() for t in valor if t.strip())
    raise ValueError(f"{campo}: formato inesperado")


def _como_dict(valor: Any, campo: str) -> Mapping[str, Any]:
    """Una propiedad de ``/cluster/options`` puede llegar como objeto o como cadena
    ``clave=valor,clave=valor``."""
    if valor is None:
        return {}
    if isinstance(valor, Mapping):
        return valor
    if isinstance(valor, str):
        resultado: dict[str, Any] = {}
        for trozo in valor.split(","):
            if not trozo.strip():
                continue
            clave, separador, v = trozo.partition("=")
            if not separador:
                raise ValueError(f"{campo}: formato inesperado")
            resultado[clave.strip()] = v.strip()
        return resultado
    raise ValueError(f"{campo}: formato inesperado")


@dataclass(frozen=True)
class PoliticaEtiquetas:
    """Política de etiquetas del centro de datos (``GET /cluster/options``)."""

    permiso: Literal["none", "list", "existing", "free"] = "free"
    lista_usuario: tuple[str, ...] = ()  # user-tag-access.user-allow-list
    registradas: tuple[str, ...] = ()  # registered-tags
    existentes: tuple[str, ...] = ()  # allowed-tags
    distingue_mayusculas: bool = False  # tag-style.case-sensitive
    # True si la respuesta NO trajo ``user-tag-access`` (respuesta parcial, p. ej. sin Sys.Audit):
    # la política ``free`` es entonces un supuesto, no un dato del servidor (LAB-C-1). No cuenta
    # en la igualdad: la política efectiva es la misma con o sin la clave.
    acceso_ausente: bool = field(default=False, compare=False)

    @classmethod
    def desde_opciones(cls, opciones: Mapping[str, Any]) -> PoliticaEtiquetas:
        """Interpreta el cuerpo de ``/cluster/options``. Un cuerpo inesperado lanza
        ``ValueError`` (el catálogo lo convierte en «política no legible»). Sin
        ``user-tag-access`` la política es ``free``."""
        if not isinstance(opciones, Mapping):
            raise ValueError("cuerpo de /cluster/options inesperado")
        acceso = _como_dict(opciones.get("user-tag-access"), "user-tag-access")
        permiso = acceso.get("user-allow", "free")
        if not isinstance(permiso, str) or permiso not in PERMISOS_ETIQUETAS:
            raise ValueError("user-tag-access.user-allow: valor inesperado")
        estilo = _como_dict(opciones.get("tag-style"), "tag-style")
        sensible = estilo.get("case-sensitive", 0)
        if isinstance(sensible, str):
            if sensible not in ("0", "1"):
                raise ValueError("tag-style.case-sensitive: valor inesperado")
            sensible = int(sensible)
        if isinstance(sensible, bool):
            sensible = int(sensible)
        if not isinstance(sensible, int) or sensible not in (0, 1):
            raise ValueError("tag-style.case-sensitive: valor inesperado")
        return cls(
            permiso=permiso,  # type: ignore[arg-type]  # validado contra PERMISOS_ETIQUETAS
            lista_usuario=_lista_de(acceso.get("user-allow-list"), "user-allow-list"),
            registradas=_lista_de(opciones.get("registered-tags"), "registered-tags"),
            existentes=_lista_de(opciones.get("allowed-tags"), "allowed-tags"),
            distingue_mayusculas=bool(sensible),
            acceso_ausente=opciones.get("user-tag-access") is None,
        )


@dataclass(frozen=True)
class OpcionesParciales:
    """Sobrescrituras de una fila de CSV; ``None`` = hereda las del lote."""

    encender: bool | None = None
    arranque_auto: bool | None = None
    notas: str | None = None
    etiquetas_usuario: tuple[str, ...] | None = None
    pool: str | None = None  # "" = sin pool explícito
    proteger: bool | None = None
    # Fase B: celdas de cloud-init de la fila y «esperar IP» (None = hereda del lote).
    cloudinit: CloudInitParcial | None = None
    esperar_ip: bool | None = None
    # Fase C: celdas de firewall de la fila y ``reescribir_red`` (sí → PERSONALIZAR, no → PLANTILLA)
    firewall: FirewallParcial | None = None
    red_clon: RedClon | None = None


@dataclass(frozen=True)
class OpcionesLote:
    """Opciones «de lote» (un mismo valor para todo el lote; cada fila puede sobrescribirlas)."""

    encender: bool = False
    arranque_auto: bool = False
    notas: str = ""
    etiquetas_usuario: tuple[str, ...] = ()
    pool: str | None = None
    proteger: bool = False
    notas_origen: bool = False
    notas_usuario: bool = False
    # Fase B: cloud-init y espera de IP del lote (valores por defecto = 0.6.0).
    cloudinit: ConfigCloudInit | None = None
    esperar_ip: bool = False
    plazo_ip_s: int = 120
    # Fase C: firewall y red del clon del lote (``None`` = comportamiento de 0.7.0).
    firewall: FirewallMV | None = None
    red_clon: RedClon | None = None

    @classmethod
    def desde_config(cls, cfg: ConfiguracionVM) -> OpcionesLote:
        """Extrae las opciones de lote del formulario (la configuración plantilla)."""
        return cls(
            encender=cfg.encender,
            arranque_auto=cfg.arranque_auto,
            notas=cfg.notas,
            etiquetas_usuario=tuple(cfg.etiquetas_usuario),
            pool=cfg.pool,
            proteger=cfg.proteger,
            notas_origen=cfg.notas_origen,
            notas_usuario=cfg.notas_usuario,
            cloudinit=cfg.cloudinit,
            esperar_ip=cfg.esperar_ip,
            plazo_ip_s=cfg.plazo_ip_s,
            firewall=cfg.firewall,
            red_clon=cfg.red_clon,
        )
