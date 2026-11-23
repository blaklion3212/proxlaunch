"""Exportación del inventario a CSV (RF-C1.6). Solo escribe el archivo local indicado.

No es un CSV de importación. Nunca incluye la nota completa ni credenciales: de la nota solo
va «coincide / falta / otro_lote». ``escribir_csv`` neutraliza las fórmulas y escribe de forma
atómica; aquí además se acotan las celdas de texto externo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv
from proxlaunch.nucleo.inventario.modelos import DetalleLote, IpInventario, MVInventario

COLUMNAS_EXPORTACION: Final = (
    "lote",
    "fecha",
    "nombre",
    "vmid",
    "nodo",
    "estado",
    "bloqueo",
    "plantilla",
    "protegida",
    "etiquetas",
    "nota_origen",
    "deshacible",
    "motivo",
)
COLUMNAS_IP: Final = ("ip", "ip_estado")
_MAX_CELDA: Final = 256
_SI, _NO = "sí", "no"


def _texto(valor: str | None) -> str:
    return (valor or "")[:_MAX_CELDA]


def _si_no(valor: bool | None) -> str:
    if valor is None:
        return ""
    return _SI if valor else _NO


def _fila(detalle: DetalleLote, mv: MVInventario) -> list[str]:
    r = mv.recurso
    return [
        _texto(detalle.lote.codigo),
        detalle.fecha.isoformat(timespec="seconds") if detalle.fecha else "",
        _texto(r.nombre),
        str(r.vmid),
        _texto(r.nodo),
        _texto(r.estado),
        _texto(r.bloqueo),
        _si_no(r.plantilla),
        _si_no(mv.protegida),
        _texto(";".join(r.etiquetas)),
        mv.nota.estado.value if mv.nota is not None else "",
        _si_no(mv.deshacible),
        _texto(";".join(m.value for m in mv.motivos)),
    ]


def filas_exportacion(
    detalles: Sequence[DetalleLote], ips: Mapping[int, IpInventario] | None
) -> tuple[list[str], list[list[str]]]:
    """Encabezado y filas (una por MV, en el orden de los detalles). Con ``ips`` añade
    ``ip`` e ``ip_estado`` (vacíos para las MVs sin dato)."""
    encabezado = list(COLUMNAS_EXPORTACION) + (list(COLUMNAS_IP) if ips is not None else [])
    filas: list[list[str]] = []
    for detalle in detalles:
        for mv in detalle.maquinas:
            fila = _fila(detalle, mv)
            if ips is not None:
                ip = ips.get(mv.recurso.vmid)
                fila += [_texto(ip.ip), ip.estado.value] if ip is not None else ["", ""]
            filas.append(fila)
    return encabezado, filas


def exportar_csv(
    ruta: Path, detalles: Sequence[DetalleLote], ips: Mapping[int, IpInventario] | None
) -> None:
    """Escribe el CSV en ``ruta`` (atómico, UTF-8 con BOM) y lo deja con permisos 0o600.

    Raises:
        ErrorProxLaunch: ``ARCHIVO_NO_GUARDABLE`` si no se puede escribir.
    """
    encabezado, filas = filas_exportacion(detalles, ips)
    escribir_csv(Path(ruta), encabezado, filas)  # la escritura atómica ya deja el archivo en 0600
