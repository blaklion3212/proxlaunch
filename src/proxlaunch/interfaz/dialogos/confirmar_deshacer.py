"""Confirmación expresa de Deshacer con máquinas encendidas o protegidas (RF-A1.5, RF-A6.4)."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QWidget

from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.textos import (
    texto_boton_cancelar_deshacer,
    texto_boton_deshacer_forzado,
    texto_boton_deshacer_sin_forzar,
    texto_casilla_confirmar_forzado,
    texto_confirmacion_forzada,
    texto_explicacion_sin_forzar,
    titulo_confirmacion_forzada,
)
from proxlaunch.nucleo.lote.rollback import InspeccionRollback


class EleccionDeshacer(Enum):
    """Lo que decidió el usuario ante la confirmación expresa."""

    CANCELAR = "cancelar"
    SIN_FORZAR = "sin_forzar"  # omite las encendidas y protegidas, como en 0.5.1
    FORZAR = "forzar"  # apaga a la fuerza y desprotege las propias, luego elimina


class DialogoConfirmarDeshacerForzado(QDialog):
    """Lista las máquinas que se apagarán y desprotegerán, con casilla desmarcada.

    Indica aparte las que se omitirán por falta de privilegio y las ilegibles. «Cancelar» es
    el botón predeterminado y el de Esc o cerrar la ventana. El botón que fuerza queda
    deshabilitado hasta marcar la casilla y no se ofrece si no hay ninguna máquina forzable.
    """

    def __init__(self, inspeccion: InspeccionRollback, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.eleccion = EleccionDeshacer.CANCELAR
        self.setWindowTitle(titulo_confirmacion_forzada())
        self.setModal(True)
        self.setMinimumWidth(520)
        self.inspeccion = inspeccion

        self.aviso = QLabel(texto_confirmacion_forzada(inspeccion))
        self.aviso.setWordWrap(True)
        self.aviso.setTextFormat(Qt.TextFormat.PlainText)
        self.aviso.setProperty("error", True)
        self.nota_sin_forzar = QLabel(texto_explicacion_sin_forzar())
        self.nota_sin_forzar.setWordWrap(True)
        self.nota_sin_forzar.setTextFormat(Qt.TextFormat.PlainText)
        self.nota_sin_forzar.setProperty("secundario", True)
        # Desmarcada por defecto: sin ella no se puede forzar (CA-A1.5.7).
        self.casilla = QCheckBox(texto_casilla_confirmar_forzado())
        self.casilla.setChecked(False)

        self.boton_forzar = QPushButton(texto_boton_deshacer_forzado())
        self.boton_sin_forzar = QPushButton(texto_boton_deshacer_sin_forzar())
        self.boton_cancelar = QPushButton(texto_boton_cancelar_deshacer())
        self.boton_forzar.setAutoDefault(False)
        self.boton_sin_forzar.setAutoDefault(False)
        self.boton_forzar.setEnabled(False)
        self.casilla.toggled.connect(self.boton_forzar.setEnabled)
        self.boton_forzar.clicked.connect(lambda: self._cerrar(EleccionDeshacer.FORZAR))
        self.boton_sin_forzar.clicked.connect(lambda: self._cerrar(EleccionDeshacer.SIN_FORZAR))
        self.boton_cancelar.clicked.connect(self.reject)

        if not inspeccion.hay_forzables:
            # Nada que apagar ni desproteger: no se ofrece forzar (todas sin privilegio).
            self.casilla.setVisible(False)
            self.boton_forzar.setVisible(False)

        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self.boton_forzar)
        fila.addWidget(self.boton_sin_forzar)
        fila.addWidget(self.boton_cancelar)
        capa, capa_pie, _ = hacer_desplazable(self)
        capa.addWidget(self.aviso)
        capa.addWidget(self.casilla)
        capa.addWidget(self.nota_sin_forzar)
        capa_pie.addLayout(fila)
        # Acción destructiva: el foco y la tecla Intro son de «Cancelar».
        self.boton_cancelar.setDefault(True)
        self.boton_cancelar.setFocus()

    def _cerrar(self, eleccion: EleccionDeshacer) -> None:
        self.eleccion = eleccion
        self.accept()
