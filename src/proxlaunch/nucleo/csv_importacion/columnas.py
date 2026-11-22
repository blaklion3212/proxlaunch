"""Tabla única de columnas y alias del CSV (RF-C03) y su resolución contra un encabezado.

Los nombres de columna no distinguen mayúsculas, acentos ni espacios (espacio y guion = guion
bajo). Las columnas con aspecto de credencial se descartan sin leer nunca sus celdas.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence

from proxlaunch.nucleo.archivos.esquema import (
    AvisoArchivo,
    CodigoAvisoArchivo,
    es_clave_credencial,
)
from proxlaunch.nucleo.csv_importacion.modelos import DefColumna, MapaColumnas
from proxlaunch.nucleo.csv_importacion.saneado import texto_visible
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

MAX_DISCOS_CSV = 8  # disco … disco8


def _discos_adicionales() -> tuple[DefColumna, ...]:
    columnas: list[DefColumna] = []
    for n in range(2, MAX_DISCOS_CSV + 1):
        columnas.append(DefColumna(f"disco{n}"))
        columnas.append(DefColumna(f"almacenamiento{n}", (f"storage{n}",)))
    return tuple(columnas)


COLUMNAS: tuple[DefColumna, ...] = (
    DefColumna("nombre", ("name", "hostname"), obligatoria=True),
    DefColumna("perfil", ("profile",)),
    DefColumna("vmid", ("id",)),
    DefColumna("nodo", ("node",)),
    DefColumna("cpu", ("cores", "nucleos")),
    DefColumna("sockets", ("zocalos",), avanzada=True),
    DefColumna("memoria", ("ram", "memoria_gib", "memoria_mib")),
    DefColumna("disco", ("disco1", "disco_gib", "tamano_disco")),
    DefColumna("almacenamiento", ("storage", "almacenamiento1")),
    *_discos_adicionales(),
    DefColumna("red", ("bridge", "red1")),
    DefColumna("vlan", ("vlan1",)),
    DefColumna("modelo_red", ("tarjeta_red",), avanzada=True),
    DefColumna("firmware", ("bios",)),
    DefColumna("tipo_cpu", ("cpu_tipo",), avanzada=True),
    # MVP 4 (RF-O28): origen del sistema operativo de la fila.
    DefColumna("origen", ("source",)),
    DefColumna("fuente", ("origen_archivo", "iso", "plantilla", "imagen")),
    DefColumna("so", ("sistema",)),
    DefColumna("virtio", ("drivers",)),
    DefColumna("modo_clon", ("clon",), avanzada=True),
    # Fase A (RF-A7.3): opciones de la MV. Alias en inglés = nombre de la opción en Proxmox.
    DefColumna("encender", ("start",)),
    DefColumna("arranque_auto", ("onboot",)),
    DefColumna("notas", ("notes",)),
    DefColumna("etiquetas", ("tags",)),
    DefColumna("pool"),
    DefColumna("proteger", ("protection",)),
    DefColumna("mtu", avanzada=True),
    DefColumna("limite_red", ("rate",), avanzada=True),
)

_SEPARADORES = re.compile(r"[\s\-_]+")
_NUMERO_FINAL = re.compile(r"_([0-9]+)$")


def normalizar_encabezado(texto: str) -> str:
    """Minúsculas, sin acentos, sin BOM ni control; espacio y guion = guion bajo."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)
    )
    limpio = "".join(c for c in sin_acentos if c != "﻿" and unicodedata.category(c) != "Cc")
    return _SEPARADORES.sub("_", limpio.casefold().strip()).strip("_")


def _tabla_alias(alias_extra: Mapping[str, str] | None) -> dict[str, str]:
    """Clave normalizada (canónica o alias) -> canónica."""
    tabla: dict[str, str] = {}
    for col in COLUMNAS:
        tabla[normalizar_encabezado(col.canonica)] = col.canonica
        for a in col.alias:
            tabla.setdefault(normalizar_encabezado(a), col.canonica)
    canonicas = {c.canonica for c in COLUMNAS}
    for alias, canonica in (alias_extra or {}).items():
        if canonica in canonicas and (clave := normalizar_encabezado(alias)):
            tabla.setdefault(clave, canonica)
    return tabla


def _buscar(tabla: Mapping[str, str], clave: str) -> str | None:
    """Busca la clave y, si falla, la variante sin guion bajo antes del número final."""
    if clave in tabla:
        return tabla[clave]
    return tabla.get(_NUMERO_FINAL.sub(r"\1", clave))


def _error(
    motivo: str, columna: str, posiciones: Sequence[int], reconocidas: Sequence[str]
) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.CSV_COLUMNAS,
        {
            "motivo": motivo,
            "columna": texto_visible(columna),
            "posiciones": ", ".join(str(p + 1) for p in posiciones),  # base 1, como en Excel
            "reconocidas": ", ".join(reconocidas),
        },
    )


def posiciones_de_columna(
    encabezado: Sequence[str], canonica: str, alias_extra: Mapping[str, str] | None = None
) -> frozenset[int]:
    """Índices de las celdas del encabezado que se resuelven a la columna ``canonica``.

    Versión tolerante de ``resolver_columnas`` (nunca falla ante vacías ni duplicadas): la usa el
    lector para fijar el límite de celda de cada columna (DT-A11)."""
    tabla = _tabla_alias(alias_extra)
    return frozenset(
        i
        for i, celda in enumerate(encabezado)
        if _buscar(tabla, normalizar_encabezado(celda)) == canonica
    )


def resolver_columnas(
    encabezado: Sequence[str], *, alias_extra: Mapping[str, str] | None = None
) -> tuple[MapaColumnas, tuple[AvisoArchivo, ...]]:
    """Asocia cada celda del encabezado con su columna canónica.

    ``alias_extra`` (alias -> canónica) lo aporta la interfaz con los nombres del idioma activo.
    Avisos: ``COLUMNA_NO_USADA`` por cada columna desconocida y un único
    ``CREDENCIAL_IGNORADA`` (``n``) si alguna parece una credencial. Lanza ``ErrorProxLaunch``
    ``CSV_COLUMNAS`` (E-M10) con ``motivo`` ``vacia``, ``duplicada`` o ``falta_nombre``.
    """
    tabla = _tabla_alias(alias_extra)
    posiciones: dict[str, int] = {}
    textos: dict[str, str] = {}
    duplicadas: dict[str, list[int]] = {}
    ignoradas: list[int] = []
    credenciales: list[int] = []
    vacias: list[int] = []
    for i, celda in enumerate(encabezado):
        if not normalizar_encabezado(celda):
            vacias.append(i)
        elif es_clave_credencial(celda):
            credenciales.append(i)
        elif (canonica := _buscar(tabla, normalizar_encabezado(celda))) is None:
            ignoradas.append(i)
        elif canonica in posiciones:
            duplicadas.setdefault(canonica, [posiciones[canonica]]).append(i)
        else:
            posiciones[canonica] = i
            textos[canonica] = texto_visible(celda)
    reconocidas = [c for c in posiciones]
    if vacias:
        raise _error("vacia", "", vacias, reconocidas)
    if duplicadas:
        canonica = min(duplicadas, key=lambda c: duplicadas[c][0])
        raise _error("duplicada", canonica, duplicadas[canonica], reconocidas)
    if "nombre" not in posiciones:
        raise _error("falta_nombre", "nombre", [], reconocidas)

    avisos = [
        AvisoArchivo(CodigoAvisoArchivo.COLUMNA_NO_USADA, {"columna": texto_visible(encabezado[i])})
        for i in ignoradas
    ]
    if credenciales:
        avisos.append(
            AvisoArchivo(CodigoAvisoArchivo.CREDENCIAL_IGNORADA, {"n": str(len(credenciales))})
        )
    mapa = MapaColumnas(posiciones, textos, tuple(ignoradas), tuple(credenciales))
    return mapa, tuple(avisos)
