"""Acerca de ProxLaunch: versión, compatibilidad y licencias de las fuentes (D-01, RNF-14)."""

from __future__ import annotations

from importlib import resources

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from proxlaunch import __version__
from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.vistas.barra_superior import cargar_svg, nombre_logotipo

LICENCIAS = (
    ("Open Sans", "OpenSans-OFL.txt"),
    ("JetBrains Mono", "JetBrainsMono-OFL.txt"),
)


def leer_licencia(archivo: str) -> str:
    """Texto de una licencia OFL incluida con la aplicación."""
    try:
        return (
            resources.files("proxlaunch.recursos")
            .joinpath("fuentes", archivo)
            .read_text(encoding="utf-8")
        )
    except OSError:
        return ""


class DialogoAcercaDe(QDialog):
    """Muestra el logo, la versión, «Compatible con Proxmox VE» y las licencias."""

    def __init__(self, tema: str = "oscuro", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Acerca de ProxLaunch"))
        self.setMinimumSize(560, 520)
        logo = QLabel()
        logo.setPixmap(cargar_svg(nombre_logotipo(tema), QSize(200, 123), self.devicePixelRatioF()))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version = QLabel(self.tr("ProxLaunch {version}").format(version=__version__))
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        compat = QLabel(self.tr("Compatible con Proxmox VE"))
        compat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nota = QLabel(
            self.tr(
                "Asistente para crear máquinas virtuales. Proxmox es una marca de Proxmox "
                "Server Solutions GmbH; ProxLaunch es un proyecto independiente."
            )
        )
        nota.setWordWrap(True)
        nota.setProperty("secundario", True)
        nota.setAlignment(Qt.AlignmentFlag.AlignCenter)
        etiquetas = QLabel(
            self.tr(
                "Las máquinas que crea ProxLaunch llevan la etiqueta «proxlaunch» (y otra «lote-…» "
                "si se crean en un lote). Así se reconocen en Proxmox y se pueden deshacer."
            )
        )
        etiquetas.setWordWrap(True)
        etiquetas.setProperty("secundario", True)
        etiquetas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._selector = QComboBox()
        self._licencia = QPlainTextEdit()
        self._licencia.setReadOnly(True)
        self._licencia.setProperty("mono", True)
        for nombre, archivo in LICENCIAS:
            self._selector.addItem(
                self.tr("Licencia de la fuente {nombre} (SIL Open Font License)").format(
                    nombre=nombre
                ),
                archivo,
            )
        self._selector.currentIndexChanged.connect(self._mostrar_licencia)
        cerrar = QPushButton(self.tr("Cerrar"))
        cerrar.setDefault(True)
        cerrar.clicked.connect(self.accept)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(cerrar)
        capa, capa_pie, _ = hacer_desplazable(self)
        for w in (logo, version, compat, nota, etiquetas, self._selector, self._licencia):
            capa.addWidget(w)
        capa_pie.addLayout(fila)
        self._mostrar_licencia()

    def _mostrar_licencia(self) -> None:
        self._licencia.setPlainText(leer_licencia(str(self._selector.currentData())))
