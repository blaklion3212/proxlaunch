"""Envoltura, versionado y migraciones de los archivos JSON propios (RF-X01).

Todo archivo lleva ``formato``, ``version_formato`` (entero ≥ 1) y ``app_version`` (informativa).

VERSIONES (MVP 4, DT-O15; fase A, DT-A9; fase B, DT-B12; fase C, RF-C6.1): ``VERSION_FORMATO``
(5) es la máxima que se LEE. Al escribir, un lote lleva ``5`` solo si usa algo de la fase C
(firewall, red del clon personalizada), ``4`` si usa algo de la fase B (cloud-init, espera de IP),
``3`` si usa algo de la fase A (encender, arranque, notas, etiquetas, pool, MTU, límite,
protección), ``2`` si usa algo del MVP 4 (origen distinto de disco vacío o datos de SO) y ``1``
en otro caso, de modo que una versión anterior siga abriendo los archivos que no necesitan lo
nuevo. Los perfiles nunca se escriben en v4 ni v5 (no guardan nada de las fases B y C). Las
migraciones v1 → v2, v2 → v3, v3 → v4 y v4 → v5 son la identidad (un archivo antiguo ya es uno
nuevo con los valores por defecto de cada campo añadido) y no avisan.

REGLA DE VERSIONADO (CA-X01.7): añadir un campo OPCIONAL con valor por defecto NO sube
``VERSION_FORMATO``; cambiar el significado de un campo existente, o volver obligatorio uno
nuevo, SÍ lo sube y exige registrar aquí una migración pura ``v → v+1``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from proxlaunch.nucleo.archivos.constantes import VERSION_FORMATO, VERSION_FORMATO_BASE
from proxlaunch.nucleo.archivos.esquema import AvisoArchivo, CodigoAvisoArchivo, Envoltura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

FORMATO_PERFILES = "proxlaunch.perfiles"
FORMATO_LOTE = "proxlaunch.lote"
FORMATOS_CONOCIDOS = frozenset({FORMATO_PERFILES, FORMATO_LOTE})

CLAVES_ENVOLTURA = frozenset({"formato", "version_formato", "app_version"})

# Una migración recibe el contenido (sin la envoltura) de la versión v y devuelve el de v+1.
Migracion = Callable[[dict[str, object]], dict[str, object]]


def _identidad(contenido: dict[str, object]) -> dict[str, object]:
    """v1 → v2 … v4 → v5: sin cambios. Los campos ausentes toman su valor por defecto."""
    return dict(contenido)


# formato → {versión de origen: migración}. v1 → v2 (MVP 4), v2 → v3 (fase A), v3 → v4 (fase B)
# y v4 → v5 (fase C) son la identidad.
MIGRACIONES: dict[str, dict[int, Migracion]] = {
    FORMATO_PERFILES: {1: _identidad, 2: _identidad, 3: _identidad, 4: _identidad},
    FORMATO_LOTE: {1: _identidad, 2: _identidad, 3: _identidad, 4: _identidad},
}
# Pasos de la tabla por defecto que no producen el aviso ``MIGRADO``: un archivo v1 sigue siendo
# válido tal cual (CA-O03.2: «se cargan sin cambios y sin avisos nuevos»; CA-A7.1.1 en 0.6). El
# paso 3 → 4 tampoco avisa (decisión del orquestador: perfiles y lotes de 0.6.0 se abren sin ruido)
# ni el 4 → 5 (CA-C6.1.1: los de 0.7.0 se leen sin aviso ``MIGRADO``).
PASOS_SIN_AVISO: frozenset[int] = frozenset({1, 2, 3, 4})


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
        con_aviso = migraciones is not None  # tabla por defecto: pasos silenciosos
        while actual < version_soportada:
            migrar = pasos.get(actual)
            if migrar is None:
                raise ErrorProxLaunch(
                    CodigoError.ARCHIVO_DANADO,
                    {"campo": "", "detalle": "sin_migracion", "version_archivo": str(actual)},
                )
            contenido = migrar(contenido)
            con_aviso = con_aviso or actual not in PASOS_SIN_AVISO
            actual += 1
        if con_aviso:
            avisos = (
                AvisoArchivo(
                    CodigoAvisoArchivo.MIGRADO,
                    {"desde": str(version), "hasta": str(version_soportada)},
                ),
            )
    return Envoltura(formato=formato, version_original=version, contenido=contenido, avisos=avisos)


def crear_envoltura(
    formato: str,
    contenido: Mapping[str, object],
    *,
    app_version: str,
    version_formato: int = VERSION_FORMATO_BASE,
) -> dict[str, object]:
    """Objeto raíz listo para serializar: envoltura + contenido.

    ``version_formato`` es la versión que se ESCRIBE (1 por defecto; 2 si el contenido usa algo
    del MVP 4, ver ``esquema_config.requiere_version_2``; 3 si usa algo de la fase A, ver
    ``esquema_config.requiere_version_3``; 4 si usa algo de la fase B, ver
    ``esquema_config.requiere_version_4``; 5 si usa algo de la fase C, ver
    ``esquema_config.requiere_version_5``).
    """
    if CLAVES_ENVOLTURA & contenido.keys():
        raise ValueError("El contenido no puede usar claves de la envoltura")
    if (
        isinstance(version_formato, bool)
        or not isinstance(version_formato, int)
        or not VERSION_FORMATO_BASE <= version_formato <= VERSION_FORMATO
    ):
        raise ValueError("version_formato fuera de las versiones conocidas")
    raiz: dict[str, object] = {
        "formato": formato,
        "version_formato": version_formato,
        "app_version": app_version,
    }
    raiz.update(contenido)
    return raiz


def a_bytes_json(obj: Mapping[str, object]) -> bytes:
    """JSON en UTF-8 sin BOM, ``ensure_ascii=False``, sangría y claves ordenadas (CA-X03.6)."""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode(
        "utf-8"
    )
