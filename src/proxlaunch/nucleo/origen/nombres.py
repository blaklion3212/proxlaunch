"""Lista blanca de volids y nombres de archivo (V-O02, V-O03, V-O09, INV-O7). Funciones puras.

Todo volid o nombre que llega a un parámetro de la API (``ide2=…``, ``import-from=…``) o que se
guarda en un archivo pasa por aquí. La forma admitida es
``<storage>:<iso|import>/<archivo>`` con ``storage`` y ``archivo`` solo de ``[A-Za-z0-9._-]``:
nunca ``,`` ``=`` ``;`` ``:`` ``/`` espacios, saltos de línea ni rutas.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.origen.constantes import (
    MAX_LONG_NOMBRE_VOLUMEN,
    PREFIJO_VIRTIO_WIN,
    URL_VIRTIO_WIN,
)

# Extensiones admitidas por contenido (en minúsculas y con el punto).
EXTENSIONES: Mapping[Contenido, frozenset[str]] = {
    Contenido.ISO: frozenset({".iso", ".img"}),
    Contenido.IMPORT: frozenset({".qcow2", ".raw", ".vmdk"}),
    Contenido.IMAGENES: frozenset(),
}

MAX_LONG_STORAGE = 64
_EXTENSION_POR_DEFECTO: Mapping[Contenido, str] = {
    Contenido.ISO: ".iso",
    Contenido.IMPORT: ".qcow2",
}
_RE_NOMBRE = re.compile(r"[A-Za-z0-9._-]+")
_RE_UNIDAD_WINDOWS = re.compile(r"[A-Za-z]:[\\/]")
_RE_ESQUEMA_URL = re.compile(r"\s*[A-Za-z][A-Za-z0-9+.\-]*://")
_RESERVADOS_WINDOWS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def es_ruta_absoluta(texto: str) -> bool:
    """Ruta del servidor o del equipo: ``/x``, ``\\x``, ``\\\\srv\\x`` o ``C:\\x``/``C:/x``."""
    if not isinstance(texto, str):
        return False
    t = texto.strip()
    return t.startswith(("/", "\\")) or _RE_UNIDAD_WINDOWS.match(t) is not None


def parece_url(texto: str) -> bool:
    """Texto con esquema (``http://``, ``https://``, ``ftp://``…) o que empieza por ``www.``."""
    if not isinstance(texto, str):
        return False
    return _RE_ESQUEMA_URL.match(texto) is not None or texto.strip().casefold().startswith("www.")


def parece_url_o_credenciales(texto: str) -> bool:
    """``parece_url`` o texto con «@» / que empieza por ``//`` (URL sin esquema o con userinfo).

    Para decidir qué celdas se sanean como URL antes de conservarlas o escribirlas
    (INV-O6, SEG-M4-05): un volid o un nombre de archivo válido nunca lleva «@».
    """
    if not isinstance(texto, str):
        return False
    return parece_url(texto) or "@" in texto or texto.strip().startswith("//")


def es_virtio_win(nombre: str) -> bool:
    """Nombre que empieza por ``virtio-win`` y termina en ``.iso`` (CA-O14.1)."""
    if not isinstance(nombre, str):
        return False
    n = nombre.casefold()
    return n.startswith(PREFIJO_VIRTIO_WIN) and n.endswith(".iso")


def nombre_virtio_win_fijado() -> str:
    """Nombre de archivo del virtio-win fijado por la app (``virtio-win-<versión>.iso``).

    Se deriva de ``URL_VIRTIO_WIN``: es el único que la detección de drivers elige sin aviso
    (SEG-M4-02). Vacío si la constante no está definida.
    """
    return URL_VIRTIO_WIN.rsplit("/", 1)[-1]


def _extension(nombre: str) -> str:
    punto = nombre.rfind(".")
    return nombre[punto:].lower() if punto > 0 else ""


def validar_volid(volid: str, contenido: Contenido) -> str | None:
    """Motivo por el que ``volid`` no es admisible, o ``None`` si lo es (V-O02/V-O03, INV-O7).

    Motivos: ``forma``, ``caracteres``, ``extension``, ``ruta_absoluta``.
    """
    if not isinstance(volid, str) or not volid or contenido not in _EXTENSION_POR_DEFECTO:
        return "forma"
    if es_ruta_absoluta(volid):
        return "ruta_absoluta"
    storage, dos_puntos, resto = volid.partition(":")
    tipo, barra, nombre = resto.partition("/")
    if not dos_puntos or not storage or not barra or not nombre or "/" in nombre or ":" in resto:
        return "forma"
    if tipo != contenido.value:
        return "forma"
    if len(storage) > MAX_LONG_STORAGE or len(nombre) > MAX_LONG_NOMBRE_VOLUMEN:
        return "caracteres"
    if _RE_NOMBRE.fullmatch(storage) is None or _RE_NOMBRE.fullmatch(nombre) is None:
        return "caracteres"
    if nombre.startswith(".."):
        return "forma"
    if _extension(nombre) not in EXTENSIONES[contenido]:
        return "extension"
    return None


def partes_volid(volid: str) -> tuple[str, Contenido, str] | None:
    """``(storage, contenido, nombre)`` de un volid ISO o import admisible; ``None`` si no."""
    if not isinstance(volid, str):
        return None
    _, _, resto = volid.partition(":")
    tipo = resto.partition("/")[0]
    for contenido in (Contenido.ISO, Contenido.IMPORT):
        if tipo == contenido.value and validar_volid(volid, contenido) is None:
            storage = volid.partition(":")[0]
            return storage, contenido, resto.partition("/")[2]
    return None


def validar_nombre_archivo(nombre: str, contenido: Contenido) -> str | None:
    """Motivo por el que ``nombre`` no sirve como nombre de archivo del storage (V-O09).

    Motivos: ``forma`` (vacío o largo), ``ruta_absoluta``, ``caracteres``, ``extension``,
    ``reservado``.
    """
    if not isinstance(nombre, str) or not nombre or contenido not in _EXTENSION_POR_DEFECTO:
        return "forma"
    if es_ruta_absoluta(nombre):
        return "ruta_absoluta"
    if len(nombre) > MAX_LONG_NOMBRE_VOLUMEN:
        return "forma"
    if _RE_NOMBRE.fullmatch(nombre) is None or nombre.startswith("."):
        return "caracteres"
    if _extension(nombre) not in EXTENSIONES[contenido]:
        return "extension"
    if nombre.split(".", 1)[0].upper() in _RESERVADOS_WINDOWS:
        return "reservado"
    return None


def sanear_nombre_archivo(nombre: str, contenido: Contenido) -> str:
    """Nombre propuesto que cumple V-O09 a partir de un texto cualquiera.

    Se queda con el último componente de una ruta, quita acentos, cambia por ``_`` lo que no
    sea ``[A-Za-z0-9._-]``, evita el punto inicial y los nombres reservados de Windows, corrige
    una extensión ausente o ajena y recorta a ``MAX_LONG_NOMBRE_VOLUMEN``.
    """
    if contenido not in _EXTENSION_POR_DEFECTO:
        raise ValueError("contenido sin nombre de archivo")
    base = str(nombre).replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c))
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".")
    extension = _extension(base)
    if extension in EXTENSIONES[contenido]:
        raiz = base[: -len(extension)]
    else:
        raiz = base
        extension = _EXTENSION_POR_DEFECTO[contenido]
    raiz = raiz.rstrip(".") or "archivo"
    if raiz.split(".", 1)[0].upper() in _RESERVADOS_WINDOWS:
        raiz = "_" + raiz
    raiz = raiz[: MAX_LONG_NOMBRE_VOLUMEN - len(extension)].rstrip(".") or "archivo"
    return raiz + extension
