"""Tabla de capacidades por versión de Proxmox (RF-09).

Es el ÚNICO lugar donde se comparan versiones: el resto del código pregunta
``caps.tiene(Funcion.X)`` y nunca escribe condiciones de versión (CA-09.6).
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from proxlaunch.nucleo.modelos.inventario import Version

VERSION_MINIMA: tuple[int, int] = (8, 0)
# Última versión probada; una mayor se permite con aviso informativo (CA-09.3, S-4).
ULTIMA_VERSION_CONOCIDA: tuple[int, int] = (9, 2)
# Versiones conocidas, de la mínima a la última (selector de versión forzada, RF-26).
VERSIONES_CONOCIDAS: tuple[tuple[int, int], ...] = (
    (8, 0),
    (8, 1),
    (8, 2),
    (8, 3),
    (8, 4),
    (9, 0),
    (9, 1),
    (9, 2),
)

_PATRON_VERSION = re.compile(r"^\s*(\d+)\.(\d+)(?:[.-](\d+))?")


class Funcion(StrEnum):
    """Funciones cuya disponibilidad depende de la versión."""

    # Entrada de EJEMPLO: el MVP 4 añadirá las funciones reales (importaciones).
    IMPORTAR_DISCO = "importar_disco"
    ETIQUETAS = "etiquetas"  # parámetro ``tags`` al crear (RF-L24)


# Única tabla: función -> (mayor, menor) desde la que está disponible.
TABLA: dict[Funcion, tuple[int, int]] = {
    Funcion.IMPORTAR_DISCO: (8, 2),
    Funcion.ETIQUETAS: (7, 3),  # todas las versiones soportadas (>= 8.0) la admiten
}


@dataclass(frozen=True)
class Capacidades:
    """Capacidades efectivas para una versión (real o forzada)."""

    version: tuple[int, int]
    forzada: bool

    def tiene(self, funcion: Funcion) -> bool:
        """Indica si la función está disponible en esta versión."""
        return self.version >= TABLA[funcion]

    def requisito(self, funcion: Funcion) -> tuple[int, int]:
        """Versión mínima de la función (para mostrar «Requiere 8.2...»)."""
        return TABLA[funcion]

    def es_soportada(self) -> bool:
        """Indica si la versión cumple la mínima del programa (CA-09.2)."""
        return self.version >= VERSION_MINIMA


def admite_etiquetas(version: tuple[int, int]) -> bool:
    """Indica si la versión admite ``tags`` al crear una MV (desde 7.3)."""
    return version >= TABLA[Funcion.ETIQUETAS]


def interpretar_version(texto: str) -> tuple[Version, bool]:
    """Interpreta el texto de ``/version`` ("8.2.4", "9.2", "7.4-17").

    Devuelve ``(version, advertencia)``. Con un formato inesperado se usa la versión
    mínima y ``advertencia`` es ``True`` para que quien llame lo registre (CA-09.5).
    """
    coincidencia = _PATRON_VERSION.match(texto) if isinstance(texto, str) else None
    if coincidencia is None:
        mayor, menor = VERSION_MINIMA
        return Version(str(texto), mayor, menor, 0), True
    mayor = int(coincidencia.group(1))
    menor = int(coincidencia.group(2))
    parche = int(coincidencia.group(3) or 0)
    return Version(texto, mayor, menor, parche), False


def capacidades_para(version: Version, forzada: tuple[int, int] | None) -> Capacidades:
    """Capacidades para la versión detectada o, si se indica, la forzada (RF-26)."""
    if forzada is not None:
        return Capacidades(version=forzada, forzada=True)
    return Capacidades(version=(version.mayor, version.menor), forzada=False)
