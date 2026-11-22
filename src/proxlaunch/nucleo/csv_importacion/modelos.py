"""Tipos de la importación CSV (docs/arquitectura/mvp3.md §3.5). Todos inmutables."""

from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.archivos.esquema import AvisoArchivo
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.opciones.modelos import OpcionesParciales
from proxlaunch.nucleo.secreto import MASCARA
from proxlaunch.nucleo.validacion import Severidad


class Codificacion(StrEnum):
    """Codificación del archivo; el valor es el nombre del códec de Python."""

    UTF8_BOM = "utf-8-sig"
    UTF16 = "utf-16"
    UTF8 = "utf-8"
    WINDOWS_1252 = "cp1252"
    ISO_8859_1 = "iso-8859-1"


@dataclass(frozen=True)
class OpcionesCsv:
    """Elecciones manuales (modo avanzado). ``None`` = detectar."""

    codificacion: Codificacion | None = None
    separador: str | None = None


@dataclass(frozen=True)
class DeteccionSeparador:
    """Resultado de la detección. ``candidatos`` lista los separadores empatados si ``ambiguo``."""

    separador: str
    ambiguo: bool
    candidatos: tuple[str, ...]
    linea_sep: bool  # la primera línea era «sep=;» (convención de Excel) y se omitió


@dataclass(frozen=True)
class FilaCsv:
    """Fila de datos no vacía. ``numero`` como en Excel: el encabezado suele ser la 1."""

    numero: int
    celdas: tuple[str, ...]

    def __repr__(self) -> str:
        """Sin las celdas: pueden traer contraseñas, claves o tokens (B5)."""
        return f"FilaCsv(numero={self.numero!r}, celdas=<{len(self.celdas)} celdas>)"


@dataclass(frozen=True)
class TablaCsv:
    codificacion: Codificacion
    deteccion: DeteccionSeparador
    encabezado: tuple[str, ...]
    filas: tuple[FilaCsv, ...]  # sin filas vacías

    def __repr__(self) -> str:
        """Como el ``repr`` generado, pero con las columnas secretas (``ci_contrasena``...)
        enmascaradas: un registro o un traceback con la tabla no debe filtrar contraseñas."""
        from proxlaunch.nucleo.csv_importacion.columnas import es_encabezado_secreto

        secretas = {i for i, titulo in enumerate(self.encabezado) if es_encabezado_secreto(titulo)}
        filas = tuple(
            FilaCsv(
                f.numero,
                tuple(MASCARA if i in secretas and c else c for i, c in enumerate(f.celdas)),
            )
            for f in self.filas
        )
        return (
            f"TablaCsv(codificacion={self.codificacion!r}, deteccion={self.deteccion!r}, "
            f"encabezado={self.encabezado!r}, filas={filas!r})"
        )


@dataclass(frozen=True)
class DefColumna:
    canonica: str
    alias: tuple[str, ...] = ()
    obligatoria: bool = False
    avanzada: bool = False


@dataclass(frozen=True)
class MapaColumnas:
    posiciones: dict[str, int]  # canónica -> índice de columna
    encabezados: dict[str, str]  # canónica -> texto del encabezado (saneado, para mensajes)
    ignoradas: tuple[int, ...]  # desconocidas (aviso una vez)
    credenciales: tuple[int, ...]  # parecen credencial: nunca se leen ni se exportan


class EstadoFila(StrEnum):
    CORRECTA = "correcta"
    CON_AVISO = "con_aviso"
    CON_ERROR = "con_error"


@dataclass(frozen=True)
class ProblemaCelda:
    """Problema de una celda o de una fila. Nunca es una excepción."""

    fila: int
    columna: str | None  # encabezado tal como está en el archivo; None = problema de la fila
    regla: str  # "V-05", "V-M08", "E-M11.no_numero"...
    severidad: Severidad
    params: dict[str, str] = field(default_factory=dict)
    valor: str = ""  # recortado a 40, sin control ni bidi (CA-C05.1)


@dataclass(frozen=True)
class FilaInterpretada:
    numero: int
    nombre: str
    perfil: str | None
    vmid: int | None
    nodo: str | None
    cfg: ConfiguracionVM | None  # None si un error impide construirla
    problemas: tuple[ProblemaCelda, ...]  # ordenados por columna; ≤ MAX_PROBLEMAS_FILA
    problemas_omitidos: int = 0
    originales: dict[str, str] = field(default_factory=dict)  # canónica -> texto original
    opciones: OpcionesParciales | None = None  # fase A: celdas fijadas (None = hereda todo)

    @property
    def estado(self) -> EstadoFila:
        if self.cfg is None or any(p.severidad == Severidad.ERROR for p in self.problemas):
            return EstadoFila.CON_ERROR
        if self.problemas or self.problemas_omitidos:
            return EstadoFila.CON_AVISO
        return EstadoFila.CORRECTA


@dataclass(frozen=True)
class ResultadoImportacion:
    codificacion: Codificacion
    deteccion: DeteccionSeparador
    columnas: MapaColumnas
    filas: tuple[FilaInterpretada, ...]
    avisos: tuple[AvisoArchivo, ...]
    perfil_base_id: str
    con_inventario: bool  # False -> solo capa 1 (CA-C06.10)

    @property
    def numeros_validos(self) -> tuple[int, ...]:
        """Números de fila que se pueden importar (sin error)."""
        return tuple(f.numero for f in self.filas if f.estado != EstadoFila.CON_ERROR)
