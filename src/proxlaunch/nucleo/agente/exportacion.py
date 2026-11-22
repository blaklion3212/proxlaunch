"""Exportación «nombre → IP» del lote (RF-B3.6). Solo datos de las MVs: nunca cloud-init.

El CSV lo escribe el escritor único de la aplicación (``archivos.csv_seguro``): UTF-8 con BOM,
separador coma, celdas saneadas contra fórmulas (``=``, ``+``, ``-``, ``@``) y escritura
atómica. Las columnas son fijas y no incluyen usuario, claves ni contraseña de cloud-init. No
sobrescribe nada por sí solo: la confirmación de reemplazo es del diálogo de guardado.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from proxlaunch.nucleo.agente.modelos import EstadoIp
from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv
from proxlaunch.nucleo.lote.modelos import ESTADOS_EN_CURSO, EntradaLibro, EstadoMV

COLUMNAS_IPS: Final = ("nombre", "vmid", "nodo", "ip", "otras_ips", "estado")

# Separador de las «otras IPs» dentro de una celda (no es el de columnas).
_SEPARADOR_OTRAS: Final = " "
_ESTADO_SIN_RESULTADO_ESPERANDO: Final = EstadoIp.PENDIENTE.value
_ESTADO_SIN_RESULTADO_OMITIDA: Final = EstadoIp.OMITIDA.value


def _estado_de(entrada: EntradaLibro) -> str:
    """Estado de IP de la entrada; si aún no hay resultado, ``pendiente`` u ``omitida``."""
    if entrada.ip is not None:
        return entrada.ip.estado.value
    if entrada.estado in ESTADOS_EN_CURSO or entrada.estado in (EstadoMV.OK, EstadoMV.CON_AVISOS):
        return _ESTADO_SIN_RESULTADO_ESPERANDO
    return _ESTADO_SIN_RESULTADO_OMITIDA


def _incluida(entrada: EntradaLibro) -> bool:
    """Solo las MVs que pasaron (o pasarán) por la espera de IP."""
    return entrada.ip is not None or entrada.elemento.cfg.esperar_ip


def filas_ips(entradas: Sequence[EntradaLibro]) -> list[list[str | int]]:
    """Filas ``nombre, vmid, nodo, ip, otras_ips, estado`` de las MVs que esperan IP, en el
    orden del plan. Sin IP, ``ip`` y ``otras_ips`` van vacías."""
    filas: list[list[str | int]] = []
    for e in entradas:
        if not _incluida(e):
            continue
        ip = e.ip
        filas.append(
            [
                e.elemento.nombre,
                e.elemento.vmid,
                e.elemento.nodo,
                ip.principal or "" if ip is not None else "",
                _SEPARADOR_OTRAS.join(ip.otras) if ip is not None else "",
                _estado_de(e),
            ]
        )
    return filas


def guardar_ips_csv(ruta: Path, entradas: Sequence[EntradaLibro]) -> Path:
    """Guarda el CSV de IPs en ``ruta`` (escritura atómica) y la devuelve.

    Raises:
        ErrorProxLaunch: ``ARCHIVO_NO_GUARDABLE`` si no se puede escribir.
    """
    escribir_csv(ruta, COLUMNAS_IPS, filas_ips(entradas), separador=",")
    return ruta


def lista_ips_texto(entradas: Sequence[EntradaLibro]) -> str:
    """``nombre<TAB>ip`` por línea, solo las MVs con IP principal (para «Copiar lista»)."""
    lineas = [
        f"{e.elemento.nombre}\t{e.ip.principal}"
        for e in entradas
        if e.ip is not None and e.ip.principal
    ]
    return "\n".join(lineas)
