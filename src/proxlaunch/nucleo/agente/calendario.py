"""Calendario de sondeos (RF-B3.7, DT-B8): quién sondea y cuándo. Puro y determinista.

Usa los instantes que recibe (el ``Reloj`` inyectado los da); no duerme ni lee la hora.
Intervalo por MV = ``max(5 s, en_espera / 5)`` y separación global mínima de 0,2 s entre dos
sondeos cualesquiera (≤ 5 peticiones por segundo). Un solo hilo consume el calendario.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

INTERVALO_S: Final = 5.0
MAX_POR_SEGUNDO: Final = 5
# 0,2 s entre sondeos más 1 µs de margen: el redondeo de coma flotante de quien avance el reloj
# no puede colar un sexto sondeo en una ventana de 1 s.
_SEPARACION_S: Final = 1.0 / MAX_POR_SEGUNDO + 1e-6


def intervalo_para(en_espera: int) -> float:
    """Segundos entre dos sondeos de una misma MV con ``en_espera`` MVs a la vez."""
    return max(INTERVALO_S, en_espera / MAX_POR_SEGUNDO)


@dataclass
class _Objetivo:
    vencimiento: float  # instante en que termina el plazo
    proximo: float  # instante del próximo turno


class CalendarioSondeo:
    """Turnos de sondeo de las MVs en espera."""

    def __init__(self) -> None:
        self._objetivos: dict[int, _Objetivo] = {}  # orden de inserción = desempate
        self._ultimo_global: float | None = None

    def anadir(self, vmid: int, ahora: float, plazo_s: float) -> None:
        """Añade una MV: su primer turno es ya y su plazo vence en ``ahora + plazo_s``."""
        self._objetivos[vmid] = _Objetivo(vencimiento=ahora + plazo_s, proximo=ahora)

    def quitar(self, vmid: int) -> None:
        self._objetivos.pop(vmid, None)

    def registrar_sondeo(self, vmid: int, ahora: float) -> None:
        """Anota que se sondeó ``vmid``: fija el turno global y el siguiente de esa MV."""
        self._ultimo_global = ahora
        objetivo = self._objetivos.get(vmid)
        if objetivo is not None:
            objetivo.proximo = ahora + intervalo_para(len(self._objetivos))

    def siguiente(self, ahora: float) -> tuple[int | None, float]:
        """``(vmid, 0.0)`` si toca sondear ya; ``(None, espera_s)`` si hay que esperar.

        Vacío devuelve ``(None, INTERVALO_S)``: quien llame debe mirar ``vacio()`` antes.
        """
        if not self._objetivos:
            return None, INTERVALO_S
        vmid, objetivo = min(self._objetivos.items(), key=lambda kv: kv[1].proximo)
        listo = objetivo.proximo
        if self._ultimo_global is not None:
            listo = max(listo, self._ultimo_global + _SEPARACION_S)
        if listo <= ahora:
            return vmid, 0.0
        return None, listo - ahora

    def vencidas(self, ahora: float) -> list[int]:
        """MVs cuyo plazo ya venció (siguen en el calendario hasta ``quitar``)."""
        return [v for v, o in self._objetivos.items() if ahora >= o.vencimiento]

    def vacio(self) -> bool:
        return not self._objetivos
