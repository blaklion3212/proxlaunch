"""Cupos de concurrencia del motor por clase de carga (MVP 4, arquitectura §10).

Cada elemento del plan se clasifica en una ``ClaseCarga``:

- ``NORMAL``: disco vacío o ISO. Exclusiva por nodo (como en M2).
- ``PESADA``: importación de disco o clon completo. Exclusiva por nodo y, además, como
  máximo ``pesadas_por_storage`` simultáneas hacia el mismo storage destino.
- ``LIGERA``: clon enlazado. Hasta ``por_nodo`` simultáneas en el mismo nodo.

Por nodo hay ``por_nodo`` unidades de cupo: una ``LIGERA`` consume 1 y las demás consumen
todas. Con ``por_nodo == 1`` el comportamiento es exactamente el de M2 (una creación por
nodo). La adquisición es atómica (nodo y storages a la vez) y respeta el orden de llegada
por nodo, así que no hay interbloqueo ni inanición de las clases exclusivas.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from enum import StrEnum
from typing import TYPE_CHECKING

from proxlaunch.nucleo.lote import presupuesto
from proxlaunch.nucleo.lote.constantes import (
    CONCURRENCIA_ENLAZADO_POR_NODO,
    CONCURRENCIA_PESADA_POR_STORAGE,
)
from proxlaunch.nucleo.lote.modelos import ClavePresupuesto, ElementoPlan
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleClon, ModoClon
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO

if TYPE_CHECKING:  # evita el ciclo cupos <-> motor
    from proxlaunch.nucleo.lote.motor import ControlLote

_PASO_ESPERA_S = 1.0  # las esperas se parten para atender cancelación, pausa y suspensión


class ClaseCarga(StrEnum):
    NORMAL = "normal"
    PESADA = "pesada"
    LIGERA = "ligera"


def clase_de(cfg: ConfiguracionVM) -> ClaseCarga:
    """Clase de carga de una MV según su origen (y el modo efectivo del clon)."""
    if cfg.origen == OrigenSO.IMPORTAR_DISCO:
        return ClaseCarga.PESADA
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        detalle = cfg.detalle_origen
        modo = detalle.modo_efectivo if isinstance(detalle, DetalleClon) else None
        # Sin modo resuelto se asume la peor carga (copia completa).
        return ClaseCarga.LIGERA if modo == ModoClon.ENLAZADO else ClaseCarga.PESADA
    return ClaseCarga.NORMAL


class CuposEjecucion:
    """Reparte los cupos por nodo y por storage entre los carriles del motor.

    Seguro entre hilos. ``encolar`` (opcional) fija el turno de llegada de un elemento;
    ``adquirir`` lo hace por sí mismo si no se llamó antes.
    """

    def __init__(
        self,
        inv: Inventario,
        *,
        por_nodo: int = CONCURRENCIA_ENLAZADO_POR_NODO,
        pesadas_por_storage: int = CONCURRENCIA_PESADA_POR_STORAGE,
    ) -> None:
        self._inv = inv
        self._por_nodo = max(1, por_nodo)
        self._por_storage = max(1, pesadas_por_storage)
        self._cond = threading.Condition()
        self._usado_nodo: defaultdict[str, int] = defaultdict(int)
        self._usado_storage: defaultdict[ClavePresupuesto, int] = defaultdict(int)
        self._siguiente_turno = 0
        self._turno_de: dict[int, int] = {}  # vmid -> número de llegada
        self._esperando: defaultdict[str, set[int]] = defaultdict(set)  # nodo -> turnos
        self._tomados: dict[
            int, tuple[int, tuple[ClavePresupuesto, ...]]
        ] = {}  # vmid -> (u, claves)

    # --- Cálculo de lo que consume un elemento ------------------------------------------

    def _consumo(self, elemento: ElementoPlan) -> tuple[int, tuple[ClavePresupuesto, ...]]:
        clase = clase_de(elemento.cfg)
        if clase == ClaseCarga.LIGERA:
            return 1, ()
        if clase == ClaseCarga.PESADA:
            return self._por_nodo, presupuesto.claves_pesadas(elemento.cfg, self._inv)
        return self._por_nodo, ()

    # --- API --------------------------------------------------------------------------

    def encolar(self, elemento: ElementoPlan) -> None:
        """Reserva el turno de llegada del elemento en su nodo (idempotente)."""
        with self._cond:
            self._reservar_turno(elemento)

    def _reservar_turno(self, elemento: ElementoPlan) -> int:
        turno = self._turno_de.get(elemento.vmid)
        if turno is None:
            turno = self._siguiente_turno
            self._siguiente_turno += 1
            self._turno_de[elemento.vmid] = turno
            self._esperando[elemento.nodo].add(turno)
        return turno

    def descartar(self, elemento: ElementoPlan) -> None:
        """Renuncia al turno reservado con ``encolar`` sin haber adquirido el cupo."""
        with self._cond:
            turno = self._turno_de.pop(elemento.vmid, None)
            if turno is not None:
                self._esperando[elemento.nodo].discard(turno)
                self._cond.notify_all()

    def adquirir(self, elemento: ElementoPlan, control: ControlLote) -> bool:
        """Espera el cupo del elemento. ``False`` si se canceló, suspendió o pausó el lote
        mientras esperaba (no se adquirió nada y el elemento pierde su turno)."""
        consumo, claves = self._consumo(elemento)
        nodo = elemento.nodo
        with self._cond:
            turno = self._reservar_turno(elemento)
            try:
                while True:
                    if (
                        control.cancelado.is_set()
                        or control.suspendido
                        or control.motivo_pausa is not None
                    ):
                        return False
                    es_su_turno = turno == min(self._esperando[nodo])
                    hay_nodo = self._usado_nodo[nodo] + consumo <= self._por_nodo
                    hay_storage = all(self._usado_storage[k] < self._por_storage for k in claves)
                    if es_su_turno and hay_nodo and hay_storage:
                        self._usado_nodo[nodo] += consumo
                        for k in claves:
                            self._usado_storage[k] += 1
                        self._tomados[elemento.vmid] = (consumo, claves)
                        return True
                    self._cond.wait(_PASO_ESPERA_S)
            finally:
                # Haya o no cupo, el elemento deja de esperar (y los demás pueden avanzar).
                self._esperando[nodo].discard(turno)
                self._turno_de.pop(elemento.vmid, None)
                self._cond.notify_all()

    def liberar(self, elemento: ElementoPlan) -> None:
        """Devuelve el cupo del elemento (no hace nada si no lo tenía)."""
        with self._cond:
            tomado = self._tomados.pop(elemento.vmid, None)
            if tomado is None:
                return
            consumo, claves = tomado
            self._usado_nodo[elemento.nodo] -= consumo
            for k in claves:
                self._usado_storage[k] -= 1
            self._cond.notify_all()
