"""CSV de filas con error, reimportable (RF-C12).

Conserva las columnas originales (menos las de credenciales) de las filas con error y añade
``fila_original``, ``columna`` y ``problema``. Al reimportarlo, esas tres son columnas
desconocidas y se ignoran (CA-C12.3). El escritor único sanea toda celda de texto.
"""

from collections.abc import Callable
from pathlib import Path

from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv
from proxlaunch.nucleo.archivos.texto import contiene_token
from proxlaunch.nucleo.cloudinit.claves import contiene_clave_privada
from proxlaunch.nucleo.csv_importacion.columnas import es_encabezado_secreto, normalizar_encabezado
from proxlaunch.nucleo.csv_importacion.interpretacion import TEXTOS_SIN_TOKEN
from proxlaunch.nucleo.csv_importacion.modelos import (
    EstadoFila,
    ProblemaCelda,
    ResultadoImportacion,
    TablaCsv,
)
from proxlaunch.nucleo.origen.nombres import parece_url_o_credenciales
from proxlaunch.nucleo.transferencias.url import url_saneada
from proxlaunch.nucleo.validacion import Severidad

COLUMNAS_EXTRA = ("fila_original", "columna", "problema")
SEPARADOR_PROBLEMAS = " | "  # varios problemas de una fila en una sola celda


def _celda_segura(celda: str, es_fuente: bool) -> str:
    """La celda ``fuente`` con forma de URL se escribe como ``host/archivo`` (INV-O6)."""
    return url_saneada(celda) if es_fuente and parece_url_o_credenciales(celda) else celda


def _celda_errores(celda: str, es_fuente: bool, sin_token: bool) -> str:
    """La celda tal como se copia al CSV de errores: sin token en las columnas que lo vetan."""
    if sin_token and contiene_token(celda):
        return ""
    return _celda_segura(celda, es_fuente)


def _sin_secretos_en_claves(celdas: tuple[str, ...], pos: int) -> tuple[str, ...]:
    """Vacía la celda ``ci_claves`` si contiene una clave privada o un token."""
    if pos < len(celdas) and (contiene_clave_privada(celdas[pos]) or contiene_token(celdas[pos])):
        return (*celdas[:pos], "", *celdas[pos + 1 :])
    return celdas


def filas_con_error(
    tabla: TablaCsv,
    resultado: ResultadoImportacion,
    traducir: Callable[[ProblemaCelda], str],
) -> tuple[list[str], list[list[str | int]]]:
    """Encabezado y filas del CSV de errores: una fila por fila original con error.

    ``columna`` y ``problema`` reúnen los problemas de severidad error de la fila (separados
    por `` | ``); ``traducir`` aporta el texto del problema.
    """
    credenciales = set(resultado.columnas.credenciales)
    extra = {normalizar_encabezado(c) for c in COLUMNAS_EXTRA}
    conservar = [
        i
        for i, titulo in enumerate(tabla.encabezado)
        if i not in credenciales
        and not es_encabezado_secreto(titulo)  # ci_contrasena y similares nunca se copian
        and normalizar_encabezado(titulo) not in extra
    ]
    # Columnas de texto cuyo valor no se conserva si trae un token (INV-M2): se escriben vacías.
    sin_token = {
        pos
        for canonica, pos in resultado.columnas.posiciones.items()
        if canonica in TEXTOS_SIN_TOKEN
    }
    encabezado = [tabla.encabezado[i] for i in conservar] + list(COLUMNAS_EXTRA)
    pos_fuente = resultado.columnas.posiciones.get("fuente", -1)
    pos_claves = resultado.columnas.posiciones.get("ci_claves")
    originales = {f.numero: f.celdas for f in tabla.filas}
    filas: list[list[str | int]] = []
    for fila in resultado.filas:
        if fila.estado != EstadoFila.CON_ERROR:
            continue
        celdas = originales.get(fila.numero, ())
        if pos_claves is not None:
            # Una clave privada (o un token) pegada por error en ``ci_claves`` no se copia (M1).
            celdas = _sin_secretos_en_claves(celdas, pos_claves)
        errores = [p for p in fila.problemas if p.severidad == Severidad.ERROR]
        columnas = [p.columna for p in errores if p.columna]
        fila_csv: list[str | int] = [
            _celda_errores(celdas[i], i == pos_fuente, i in sin_token) if i < len(celdas) else ""
            for i in conservar
        ]
        fila_csv.append(fila.numero)
        fila_csv.append(SEPARADOR_PROBLEMAS.join(dict.fromkeys(columnas)))
        fila_csv.append(SEPARADOR_PROBLEMAS.join(traducir(p) for p in errores))
        filas.append(fila_csv)
    return encabezado, filas


def escribir_filas_con_error(
    ruta: Path,
    tabla: TablaCsv,
    resultado: ResultadoImportacion,
    traducir: Callable[[ProblemaCelda], str],
    *,
    separador: str = ";",
) -> None:
    """Escribe el CSV de errores (UTF-8 con BOM, atómico y saneado)."""
    encabezado, filas = filas_con_error(tabla, resultado, traducir)
    escribir_csv(ruta, encabezado, filas, separador=separador)
