"""Lectura estricta de la nota de origen de una MV (DT-C15). Puro.

La nota (``description``) es texto no confiable: solo se extraen, con expresión regular y
líneas completas, ``- Lote:`` y ``- Fecha:`` del ÚLTIMO bloque «Creada con ProxLaunch …».
Nunca se guarda ni se muestra la nota completa (CA-C1.3.5, CA-C1.6.3).
"""

from __future__ import annotations

import re
from datetime import datetime

from proxlaunch.nucleo.inventario.modelos import EstadoNota, NotaOrigen

_CABECERA = "Creada con ProxLaunch "
_RE_LOTE = re.compile(r"^- Lote: ([0-9a-f]{8})$")
_RE_FECHA = re.compile(r"^- Fecha: (\S{19,32})$")
_MAX_CARACTERES = 16384  # Proxmox limita la nota a 8192; el resto no se examina


def _fecha(texto: str) -> datetime | None:
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    # Una fecha sin zona se interpreta como hora local, para poder compararlas entre sí.
    return fecha.astimezone() if fecha.tzinfo is None else fecha


def leer_nota_origen(descripcion: object, codigo: str) -> NotaOrigen:
    """Estado de la nota respecto de ``codigo``: coincide, falta u otro lote."""
    if not isinstance(descripcion, str):
        return NotaOrigen(EstadoNota.FALTA)
    lineas = descripcion[:_MAX_CARACTERES].splitlines()
    inicio = None
    for i, linea in enumerate(lineas):
        if linea.startswith(_CABECERA):
            inicio = i  # se queda con el último bloque
    if inicio is None:
        return NotaOrigen(EstadoNota.FALTA)
    lote: str | None = None
    fecha: datetime | None = None
    for linea in lineas[inicio + 1 :]:
        if not linea.strip():
            if lote is None and fecha is None:
                continue  # línea en blanco entre la cabecera y las viñetas
            break  # fin del bloque (lo que sigue es texto libre del usuario)
        if not linea.startswith("- "):
            break
        if (m := _RE_LOTE.match(linea)) is not None and lote is None:
            lote = m.group(1)
        elif (m := _RE_FECHA.match(linea)) is not None and fecha is None:
            fecha = _fecha(m.group(1))
    if lote is None:
        return NotaOrigen(EstadoNota.FALTA, fecha=fecha)
    estado = EstadoNota.COINCIDE if lote == codigo else EstadoNota.OTRO_LOTE
    return NotaOrigen(estado, lote, fecha)
