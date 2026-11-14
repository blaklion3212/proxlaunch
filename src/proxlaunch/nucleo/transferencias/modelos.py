"""Modelos de las transferencias de archivos (MVP 4, arquitectura §3.5).

Solo datos inmutables. ``RegistroTransferencia`` no contiene URL, ruta local ni
checksum (INV-O6).
"""

from dataclasses import dataclass
from enum import StrEnum

from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.validacion import Problema


class TipoTransferencia(StrEnum):
    SUBIDA = "subida"
    DESCARGA = "descarga"


class EstadoTransferencia(StrEnum):
    CALCULANDO_HUELLA = "calculando_huella"
    COMPROBANDO = "comprobando"
    TRANSFIRIENDO = "transfiriendo"
    ESPERANDO_SERVIDOR = "esperando_servidor"  # tarea imgcopy/download
    VERIFICANDO = "verificando"
    TERMINADA = "terminada"
    CANCELADA = "cancelada"
    FALLIDA = "fallida"
    SIN_ESPERAR = "sin_esperar"  # «Dejar de esperar»


@dataclass(frozen=True)
class DestinoTransferencia:
    """Dónde queda el archivo. Volid esperado: ``{storage}:{contenido}/{nombre_archivo}``."""

    nodo: str
    storage: str
    contenido: Contenido
    nombre_archivo: str


@dataclass(frozen=True)
class ComprobacionPrevia:
    """Resultado de comprobar el destino antes de transferir."""

    volid_existente: str | None  # V-O14 (bloquea; sin opción de sobrescribir)
    libre_storage_bytes: int | None  # V-O13 (bloquea)
    libre_raiz_bytes: int | None  # CA-O10.4 (aviso con casilla)
    permiso: bool | None  # V-O15/V-O16 (None = desconocido)
    problemas: tuple[Problema, ...]  # de nucleo.validacion, con V-O13/O14/O15/O16


@dataclass(frozen=True)
class Progreso:
    estado: EstadoTransferencia
    hechos_bytes: int
    total_bytes: int | None
    velocidad_bps: float | None
    restante_s: float | None
    porcentaje_servidor: float | None


@dataclass(frozen=True)
class ResultadoTransferencia:
    estado: EstadoTransferencia
    volid: str | None
    error: ErrorProxLaunch | None
    quedo_archivo: bool | None  # tras cancelar o fallar (CA-O12.2); None = no se sabe
    duracion_s: float
    upid: str | None


@dataclass(frozen=True)
class RegistroTransferencia:
    """Entrada del registro de la sesión (RF-O25). INV-O6: sin URL, ruta local ni checksum."""

    tipo: TipoTransferencia
    nombre_archivo: str
    storage: str
    nodo: str
    tamano_bytes: int | None
    hora_local: str
    estado: EstadoTransferencia
    volid: str | None
