"""Política de pausa del lote: errores globales y repetidos (RF-L14, P-L09).

Pura y segura entre hilos: el motor la consulta con el error de cada MV terminada, en
orden de finalización.
"""

from __future__ import annotations

import threading

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import UMBRAL_PAUSA_ERRORES
from proxlaunch.nucleo.lote.modelos import MotivoPausa

# Errores que harían fallar igual a todas las MVs restantes: pausa tras el primero.
CODIGOS_GLOBALES = frozenset(
    {
        CodigoError.SESION_EXPIRADA,
        CodigoError.CREDENCIALES_INVALIDAS,
        CodigoError.HUELLA_CAMBIADA,
        CodigoError.ETIQUETA_RECHAZADA,
        CodigoError.LOTE_SIN_NODO_APTO,  # ningún nodo en línea
    }
)
PRIVILEGIO_CREAR = "VM.Allocate"


def es_error_global(error: ErrorProxLaunch) -> bool:
    """``True`` si el error es global para el lote (CA-L14.2).

    ``PERMISO_INSUFICIENTE`` solo lo es sobre ``VM.Allocate`` (o sin privilegio indicado,
    que en la creación se infiere como ``VM.Allocate``); un permiso de solo lectura que
    impide confirmar la MV no detiene el lote.
    """
    if error.codigo in CODIGOS_GLOBALES:
        return True
    if error.codigo == CodigoError.PERMISO_INSUFICIENTE:
        privilegio = error.params.get("privilegio", "")
        return privilegio in ("", PRIVILEGIO_CREAR)
    return False


class PoliticaPausa:
    """Decide cuándo el lote debe pausarse."""

    def __init__(self, umbral: int = UMBRAL_PAUSA_ERRORES) -> None:
        self._umbral = umbral
        self._cerrojo = threading.Lock()
        self._ultimo: CodigoError | None = None
        self._racha = 0
        self._ignoradas: set[CodigoError] = set()

    def registrar(self, error: ErrorProxLaunch | None) -> MotivoPausa | None:
        """Registra el desenlace de una MV (``None`` = éxito) y devuelve el motivo de pausa
        si corresponde. Un éxito reinicia la racha; una causa ignorada no cuenta."""
        with self._cerrojo:
            if error is None:
                self._ultimo = None
                self._racha = 0
                return None
            if error.codigo in self._ignoradas:
                return None
            if es_error_global(error):
                return MotivoPausa.ERROR_GLOBAL
            if error.codigo == self._ultimo:
                self._racha += 1
            else:
                self._ultimo = error.codigo
                self._racha = 1
            if self._racha >= self._umbral:
                self._ultimo = None
                self._racha = 0
                return MotivoPausa.REPETIDO
            return None

    def ignorar(self, causa: CodigoError) -> None:
        """Tras "Continuar" no se vuelve a pausar por esta causa en este lote (CA-L14.4)."""
        with self._cerrojo:
            self._ignoradas.add(causa)
            if self._ultimo == causa:
                self._ultimo = None
                self._racha = 0
