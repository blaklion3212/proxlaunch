"""Reemplazo de archivos con reintentos ante bloqueos transitorios de Windows."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable

# 5 = acceso denegado, 32 = violación de uso compartido, 33 = violación de bloqueo.
WINERROR_REINTENTABLES = (5, 32, 33)
MAX_INTENTOS = 8
ESPERA_INICIAL_S = 5 / 1000  # se duplica en cada intento: 5, 10, 20... ms (total < 1 s)
TOPE_TOTAL_S = 1.0


def reemplazar_con_reintentos(
    origen: str | os.PathLike[str],
    destino: str | os.PathLike[str],
    dormir: Callable[[float], None] = time.sleep,
) -> None:
    """``os.replace(origen, destino)``; en Windows reintenta si otro proceso o hilo lo bloquea.

    Solo en Windows y solo ante ``OSError`` con ``winerror`` 5, 32 o 33: hasta 8 intentos con
    espera exponencial desde 5 ms y tope total de 1 s. En POSIX es un único ``os.replace``.
    Si se agotan los reintentos relanza la última excepción original.
    """
    if sys.platform != "win32":
        os.replace(origen, destino)
        return
    espera = ESPERA_INICIAL_S
    esperado = 0.0
    intento = 1
    while True:
        try:
            os.replace(origen, destino)
            return
        except OSError as exc:
            reintentable = getattr(exc, "winerror", None) in WINERROR_REINTENTABLES
            if not reintentable or intento >= MAX_INTENTOS or esperado + espera > TOPE_TOTAL_S:
                raise
        dormir(espera)
        esperado += espera
        espera *= 2
        intento += 1
