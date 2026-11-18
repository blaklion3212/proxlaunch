"""GestorTema: Automático, Oscuro y Claro, con detección del sistema (RF-22)."""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from importlib import resources
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication

from proxlaunch.interfaz.tema.iconos import generar_iconos
from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.nucleo.persistencia.rutas import Rutas

_log = logging.getLogger(__name__)

_MARCADOR = re.compile(r"\{\{(\w+)\}\}")
# Declaración ``image: url("{{icono_...}}");`` completa, para quitarla si no hay iconos.
_IMAGEN_ICONO = re.compile(r'[ \t]*image:\s*url\("\{\{icono_\w+\}\}"\);[ \t]*\n?')


class ModoTema(StrEnum):
    """Preferencia del usuario; el valor es el texto que se persiste."""

    AUTOMATICO = "automatico"
    OSCURO = "oscuro"
    CLARO = "claro"


TEMA_OSCURO = "oscuro"
TEMA_CLARO = "claro"


def generar_qss(plantilla: str, tokens: dict[str, str]) -> str:
    """Sustituye los marcadores ``{{token}}`` de la plantilla por los colores del tema.

    Lanza ``KeyError`` si la plantilla usa un token inexistente.
    """
    return _MARCADOR.sub(lambda m: tokens[m.group(1)], plantilla)


def quitar_iconos(plantilla: str) -> str:
    """Elimina de la plantilla las imágenes de iconos (respaldo cuando no se pudieron escribir)."""
    return _IMAGEN_ICONO.sub("", plantilla)


def leer_plantilla() -> str:
    """Lee ``plantilla.qss`` incluida en el paquete."""
    return resources.files("proxlaunch.interfaz.tema").joinpath("plantilla.qss").read_text("utf-8")


class GestorTema(QObject):
    """Aplica la hoja de estilos según el modo elegido y el esquema del sistema.

    No persiste la preferencia: la recibe en el constructor o con ``establecer_modo``
    y la entrega con ``modo``.
    """

    tema_cambiado = Signal(str)  # "oscuro" o "claro"

    def __init__(
        self,
        aplicacion: QApplication,
        modo: ModoTema = ModoTema.AUTOMATICO,
        parent: QObject | None = None,
        directorio_iconos: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._directorio_iconos = (
            directorio_iconos
            if directorio_iconos is not None
            else Rutas().directorio_cache / "tema"
        )
        self._app = aplicacion
        self._modo = ModoTema(modo)
        self._plantilla = leer_plantilla()
        self._tema = TEMA_OSCURO
        self._iconos_activos = False
        self._app.styleHints().colorSchemeChanged.connect(self._al_cambiar_esquema)

    @property
    def modo(self) -> ModoTema:
        """Modo elegido por el usuario."""
        return self._modo

    @property
    def tema_actual(self) -> str:
        """Tema efectivo aplicado: ``"oscuro"`` o ``"claro"``."""
        return self._tema

    @property
    def iconos_activos(self) -> bool:
        """True si la última ``aplicar`` pudo generar los iconos del tema."""
        return self._iconos_activos

    def establecer_modo(self, modo: ModoTema) -> None:
        """Cambia el modo y reaplica el tema."""
        self._modo = ModoTema(modo)
        self.aplicar()

    def aplicar(self) -> str:
        """Calcula el tema efectivo, aplica la QSS y emite ``tema_cambiado``."""
        tema = self._resolver_tema()
        tokens = TOKENS_CLARO if tema == TEMA_CLARO else TOKENS_OSCURO
        iconos = generar_iconos(tokens, self._directorio_iconos)
        self._iconos_activos = bool(iconos)
        plantilla = self._plantilla if iconos else quitar_iconos(self._plantilla)
        self._app.setStyleSheet(generar_qss(plantilla, {**tokens, **iconos}))
        self._tema = tema
        _log.info("Tema aplicado: %s (modo %s)", tema, self._modo.value)
        self.tema_cambiado.emit(tema)
        return tema

    def _resolver_tema(self) -> str:
        """Decide el tema efectivo; usa oscuro si el esquema es desconocido (P-14)."""
        if self._modo is ModoTema.OSCURO:
            return TEMA_OSCURO
        if self._modo is ModoTema.CLARO:
            return TEMA_CLARO
        try:
            esquema = self._app.styleHints().colorScheme()
        except Exception:  # detección rota en algún backend: respaldo oscuro
            _log.warning("Falló la detección del tema del sistema; se usa oscuro")
            return TEMA_OSCURO
        if esquema == Qt.ColorScheme.Light:
            return TEMA_CLARO
        if esquema == Qt.ColorScheme.Dark:
            return TEMA_OSCURO
        _log.warning("Esquema de color del sistema desconocido; se usa oscuro (P-14)")
        return TEMA_OSCURO

    @Slot(Qt.ColorScheme)
    def _al_cambiar_esquema(self, _esquema: Qt.ColorScheme) -> None:
        """Reacciona al cambio del sistema solo en modo Automático."""
        if self._modo is ModoTema.AUTOMATICO:
            self.aplicar()
