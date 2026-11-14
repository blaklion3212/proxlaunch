"""Tipos del esquema estricto de archivos (docs/arquitectura/mvp3.md §3.3).

Aquí solo viven los tipos compartidos; ``LectorEsquema`` y el resto de la lógica se añaden
en la fase F3a.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch


class MotivoCampo(StrEnum):
    """Por qué un campo del archivo no pasa el esquema."""

    REQUERIDO = "requerido"
    TIPO = "tipo"
    RANGO = "rango"
    LONGITUD = "longitud"
    ENUM = "enum"
    TEXTO_NO_VALIDO = "texto_no_valido"
    TOKEN = "token"
    DEMASIADOS = "demasiados"
    DUPLICADO = "duplicado"


@dataclass(frozen=True)
class ErrorCampo:
    """Un campo inválido: ruta (``"discos[1].tamano_gib"``), motivo y parámetros."""

    ruta: str
    motivo: MotivoCampo
    params: dict[str, str] = field(default_factory=dict)


class ErrorArchivo(ErrorProxLaunch):
    """E-M04 con la lista completa de errores de campo (CA-G03.3).

    ``params["campo"]`` es la ruta del primer error y ``params["n"]`` el total.
    """

    def __init__(
        self,
        errores: tuple[ErrorCampo, ...],
        params: dict[str, str] | None = None,
        detalle_tecnico: str = "",
    ) -> None:
        base = {"campo": errores[0].ruta if errores else "", "n": str(len(errores))}
        base.update(params or {})
        super().__init__(CodigoError.ARCHIVO_DANADO, base, detalle_tecnico)
        self.errores = errores


class CodigoAvisoArchivo(StrEnum):
    """Avisos no bloqueantes al leer un archivo (nunca incluyen valores del usuario)."""

    CAMPOS_DESCONOCIDOS = "campos_desconocidos"  # CA-X01.6: params n
    CREDENCIAL_IGNORADA = "credencial_ignorada"  # E-M16 / CA-X04.2: params n
    MIGRADO = "migrado"  # CA-X01.3: params desde, hasta
    COLUMNA_NO_USADA = "columna_no_usada"  # CA-C03.3: params columna (saneada y recortada)
    GIB_ASUMIDO = "gib_asumido"  # CA-C05.6, una vez por columna y archivo
    DECIMAL_COMA = "decimal_coma"
    GB_COMO_GIB = "gb_como_gib"


@dataclass(frozen=True)
class AvisoArchivo:
    codigo: CodigoAvisoArchivo
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Envoltura:
    """Raíz de un archivo propio ya verificada: formato, versión original y contenido."""

    formato: str
    version_original: int
    contenido: dict[str, object]
    avisos: tuple[AvisoArchivo, ...] = ()
