"""Transporte de solo lectura: guardián de la simulación (INV-L5, RF-L11).

Envuelve un ``Transporte`` y deja pasar únicamente GET y HEAD. Cualquier otro método
lanza ``ESCRITURA_EN_SIMULACION`` ANTES de tocar la red.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from proxlaunch.nucleo.api.transporte import Transporte
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

if TYPE_CHECKING:
    from proxlaunch.nucleo.api.autenticacion import Autenticador

METODOS_LECTURA = frozenset({"GET", "HEAD"})


class TransporteSoloLectura:
    """Implementa el protocolo ``Transporte`` rechazando toda escritura."""

    def __init__(self, transporte: Transporte) -> None:
        self._transporte = transporte

    def peticion(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
    ) -> Any:
        if str(metodo).upper() not in METODOS_LECTURA:
            # Error de programación: nunca debe llegar a la red. Sin cuerpo ni secretos.
            raise ErrorProxLaunch(
                CodigoError.ESCRITURA_EN_SIMULACION,
                {"metodo": str(metodo).upper(), "ruta": ruta},
            )
        return self._transporte.peticion(metodo, ruta, params=params, datos=datos)

    @property
    def host_activo(self) -> str:
        return self._transporte.host_activo

    def usar_autenticador(self, auth: Autenticador | None) -> None:
        self._transporte.usar_autenticador(auth)
