"""Medición del progreso de una transferencia (RNF-O02, CA-O11.5). Sin E/S ni Qt.

``MedidorProgreso`` calcula velocidad y tiempo restante con una media móvil y decide cuándo
emitir (reloj inyectado). ``progreso_de_log`` extrae porcentaje y bytes del log de la tarea
``download`` de Proxmox si lo trae (formato por confirmar en LAB-M4-06; es tolerante).
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Sequence

from proxlaunch.nucleo.lote.constantes import ACTUALIZACIONES_POR_S
from proxlaunch.nucleo.reloj import Reloj

_INTERVALO_MIN_S = 1.0 / ACTUALIZACIONES_POR_S  # máximo 10 emisiones por segundo

_RE_PORCENTAJE = re.compile(r"(?<![\d.])(\d{1,3})(?:[.,]\d+)?\s*%")
_RE_BYTES_PUNTOS = re.compile(r"^\s*(\d+)\s*([KMG])\b", re.IGNORECASE)
_RE_LARGO = re.compile(r"(?:Length|Content-Length|size|tama[nñ]o)\s*[:=]\s*(\d+)", re.IGNORECASE)
_FACTOR = {"K": 1024, "M": 1024**2, "G": 1024**3}


class MedidorProgreso:
    """Velocidad y tiempo restante con media móvil de ``ventana_s`` segundos."""

    def __init__(self, reloj: Reloj, *, ventana_s: float = 5.0) -> None:
        self._reloj = reloj
        self._ventana = ventana_s
        self._muestras: deque[tuple[float, int]] = deque()
        self._ultima_emision: float | None = None

    def registrar(self, hechos: int, total: int | None) -> tuple[float | None, float | None]:
        """Anota una muestra y devuelve ``(velocidad_bps, restante_s)``; ``None`` sin dato."""
        ahora = self._reloj.ahora()
        self._muestras.append((ahora, hechos))
        # Se conserva una muestra anterior a la ventana para poder medir sobre toda ella.
        while len(self._muestras) > 2 and ahora - self._muestras[1][0] >= self._ventana:
            self._muestras.popleft()
        t0, h0 = self._muestras[0]
        dt = ahora - t0
        if dt <= 0 or hechos < h0:
            return None, None
        velocidad = (hechos - h0) / dt
        if velocidad <= 0:
            return None, None
        if total is None:
            return velocidad, None
        return velocidad, max(0.0, (total - hechos) / velocidad)

    def debe_emitir(self) -> bool:
        """``True`` si toca emitir una actualización (no más de 10 por segundo)."""
        ahora = self._reloj.ahora()
        if self._ultima_emision is None or ahora - self._ultima_emision >= _INTERVALO_MIN_S:
            self._ultima_emision = ahora
            return True
        return False


def progreso_de_log(lineas: Sequence[str]) -> tuple[int | None, int | None, float | None]:
    """``(bytes, total, porcentaje)`` a partir de las líneas del log; ``None`` donde no consta.

    Tolerante: ignora lo que no entiende y nunca lanza. El porcentaje va de 0 a 100.
    """
    total: int | None = None
    for linea in lineas:
        m = _RE_LARGO.search(linea)
        if m:
            total = int(m.group(1))
    porcentaje: float | None = None
    hechos: int | None = None
    for linea in reversed(lineas):
        m = _RE_PORCENTAJE.search(linea)
        if m is None:
            continue
        valor = int(m.group(1))
        if 0 <= valor <= 100:
            porcentaje = float(valor)
            mb = _RE_BYTES_PUNTOS.match(linea)
            if mb:
                hechos = int(mb.group(1)) * _FACTOR[mb.group(2).upper()]
            break
    if hechos is None and porcentaje is not None and total:
        hechos = int(total * porcentaje / 100)
    if hechos is not None and total is not None and hechos > total:
        hechos = total
    return hechos, total, porcentaje
