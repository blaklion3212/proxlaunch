"""Reloj inyectable: real para producción y simulado para pruebas."""

from __future__ import annotations

import time
from typing import Protocol


class Reloj(Protocol):
    """Fuente de tiempo y de esperas, para poder simular el paso del tiempo."""

    def ahora(self) -> float:
        """Devuelve un instante en segundos (monótono, solo útil para diferencias)."""
        ...

    def dormir(self, segundos: float) -> None:
        """Espera el número de segundos indicado."""
        ...


class RelojReal:
    """Reloj del sistema. Usa un reloj monótono: inmune a cambios de hora."""

    def ahora(self) -> float:
        return time.monotonic()

    def dormir(self, segundos: float) -> None:
        if segundos > 0:
            time.sleep(segundos)


class RelojSimulado:
    """Reloj controlado a mano: `dormir` avanza el tiempo sin esperar de verdad."""

    def __init__(self, inicio: float = 0.0) -> None:
        self._t = float(inicio)

    def ahora(self) -> float:
        return self._t

    def dormir(self, segundos: float) -> None:
        self.avanzar(segundos)

    def avanzar(self, segundos: float) -> None:
        """Adelanta el reloj `segundos` (los valores negativos se ignoran)."""
        if segundos > 0:
            self._t += segundos
