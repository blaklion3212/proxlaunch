"""Preferencias de usuario: tema, modo y versión forzada (RF-22.3, RF-24.4)."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from proxlaunch.nucleo.capacidades import VERSION_MINIMA
from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson

VERSION_ESQUEMA = 1


class Tema(StrEnum):
    AUTOMATICO = "automatico"
    OSCURO = "oscuro"
    CLARO = "claro"


class Modo(StrEnum):
    BASICO = "basico"
    AVANZADO = "avanzado"


@dataclass
class Preferencias:
    """Preferencias persistibles. `version_forzada` es (mayor, menor) o `None`."""

    tema: Tema = Tema.AUTOMATICO
    modo: Modo = Modo.BASICO
    version_forzada: tuple[int, int] | None = None


def _version_desde_texto(valor: object) -> tuple[int, int] | None:
    if not isinstance(valor, str):
        return None
    partes = valor.split(".")
    if len(partes) != 2 or not all(p.isdigit() for p in partes):
        return None
    return int(partes[0]), int(partes[1])


class RepositorioPreferencias:
    """Lee y guarda `Preferencias`; los valores inválidos caen al valor por defecto."""

    def __init__(self, ruta: Path) -> None:
        self._almacen = AlmacenJson(ruta)
        self.hubo_corrupcion = False
        self.copia_danada: Path | None = None
        self.error_lectura = False
        # V-D03: texto («8.2») de una versión forzada anterior a la mínima que se descartó al cargar
        self.version_forzada_descartada: str | None = None

    def cargar(self) -> Preferencias:
        r = self._almacen.leer()
        if r.hubo_corrupcion:
            self.hubo_corrupcion = True
            self.copia_danada = r.copia_danada
            self.error_lectura = self.error_lectura or r.error_lectura
        d = r.datos
        pref = Preferencias()
        with contextlib.suppress(ValueError):
            pref.tema = Tema(d.get("tema", pref.tema))
        with contextlib.suppress(ValueError):
            pref.modo = Modo(d.get("modo", pref.modo))
        forzada = _version_desde_texto(d.get("version_forzada"))
        if forzada is not None and forzada < VERSION_MINIMA:
            # La mínima subió a 8.4 (V-D03): se descarta y la ventana lo avisa una vez.
            self.version_forzada_descartada = f"{forzada[0]}.{forzada[1]}"
            forzada = None
        pref.version_forzada = forzada
        return pref

    def guardar(self, pref: Preferencias) -> None:
        vf = pref.version_forzada
        self._almacen.escribir(
            {
                "version_esquema": VERSION_ESQUEMA,
                "tema": str(pref.tema),
                "modo": str(pref.modo),
                "version_forzada": None if vf is None else f"{vf[0]}.{vf[1]}",
            }
        )
