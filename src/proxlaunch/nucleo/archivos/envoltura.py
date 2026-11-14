"""Envoltura, versionado y migraciones de los archivos JSON propios (RF-X01).

Todo archivo lleva ``formato``, ``version_formato`` (entero ≥ 1) y ``app_version`` (informativa).

REGLA DE VERSIONADO (CA-X01.7): añadir un campo OPCIONAL con valor por defecto NO sube
``VERSION_FORMATO``; cambiar el significado de un campo existente, o volver obligatorio uno
nuevo, SÍ lo sube y exige registrar aquí una migración pura ``v → v+1``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from proxlaunch.nucleo.archivos.constantes import VERSION_FORMATO
from proxlaunch.nucleo.archivos.esquema import AvisoArchivo, CodigoAvisoArchivo, Envoltura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

FORMATO_PERFILES = "proxlaunch.perfiles"
FORMATO_LOTE = "proxlaunch.lote"
FORMATOS_CONOCIDOS = frozenset({FORMATO_PERFILES, FORMATO_LOTE})

CLAVES_ENVOLTURA = frozenset({"formato", "version_formato", "app_version"})

# Una migración recibe el contenido (sin la envoltura) de la versión v y devuelve el de v+1.
Migracion = Callable[[dict[str, object]], dict[str, object]]

# formato → {versión de origen: migración}. En el MVP 3 la cadena está vacía (solo existe v1).
MIGRACIONES: dict[str, dict[int, Migracion]] = {FORMATO_PERFILES: {}, FORMATO_LOTE: {}}


def _formato_ajeno(esperado: str, encontrado: object = None) -> ErrorProxLaunch:
    params = {"esperado": esperado}
    # Solo se revela otro formato si es uno conocido de ProxLaunch (nunca texto del archivo).
    if isinstance(encontrado, str) and encontrado in FORMATOS_CONOCIDOS and encontrado != esperado:
        params["encontrado"] = encontrado
    return ErrorProxLaunch(CodigoError.ARCHIVO_FORMATO_AJENO, params)


def abrir_envoltura(
    dato: object,
    formato: str,
    *,
    version_soportada: int = VERSION_FORMATO,
    migraciones: Mapping[int, Migracion] | None = None,
) -> Envoltura:
    """Verifica la raíz y devuelve el contenido migrado a ``version_soportada``.

    - Raíz que no es objeto, ``formato`` ausente o distinto → E-M02 (``esperado`` y, solo si es
      otro formato conocido de ProxLaunch, ``encontrado``).
    - ``version_formato`` ausente, no entero, booleano o < 1 → E-M02.
    - Mayor que la soportada → E-M03 (sin lectura parcial).
    - Menor → se aplica la cadena de migraciones y se añade el aviso ``MIGRADO``.

    ``contenido`` es el objeto raíz SIN ``formato``, ``version_formato`` ni ``app_version``.
    """
    if not isinstance(dato, dict):
        raise _formato_ajeno(formato)
    encontrado = dato.get("formato")
    if encontrado != formato:
        raise _formato_ajeno(formato, encontrado)
    version = dato.get("version_formato")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise _formato_ajeno(formato)
    if version > version_soportada:
        raise ErrorProxLaunch(
            CodigoError.ARCHIVO_VERSION_FUTURA,
            {"version_archivo": str(version), "version_soportada": str(version_soportada)},
        )
    contenido = {k: v for k, v in dato.items() if k not in CLAVES_ENVOLTURA}
    avisos: tuple[AvisoArchivo, ...] = ()
    if version < version_soportada:
        pasos = MIGRACIONES.get(formato, {}) if migraciones is None else migraciones
        actual = version
        while actual < version_soportada:
            migrar = pasos.get(actual)
            if migrar is None:
                raise ErrorProxLaunch(
                    CodigoError.ARCHIVO_DANADO,
                    {"campo": "", "detalle": "sin_migracion", "version_archivo": str(actual)},
                )
            contenido = migrar(contenido)
            actual += 1
        avisos = (
            AvisoArchivo(
                CodigoAvisoArchivo.MIGRADO,
                {"desde": str(version), "hasta": str(version_soportada)},
            ),
        )
    return Envoltura(formato=formato, version_original=version, contenido=contenido, avisos=avisos)


def crear_envoltura(
    formato: str, contenido: Mapping[str, object], *, app_version: str
) -> dict[str, object]:
    """Objeto raíz listo para serializar: envoltura + contenido."""
    if CLAVES_ENVOLTURA & contenido.keys():
        raise ValueError("El contenido no puede usar claves de la envoltura")
    raiz: dict[str, object] = {
        "formato": formato,
        "version_formato": VERSION_FORMATO,
        "app_version": app_version,
    }
    raiz.update(contenido)
    return raiz


def a_bytes_json(obj: Mapping[str, object]) -> bytes:
    """JSON en UTF-8 sin BOM, ``ensure_ascii=False``, sangría y claves ordenadas (CA-X03.6)."""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode(
        "utf-8"
    )
