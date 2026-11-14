"""Diálogo con el informe del lote: texto monoespaciado, copiar y guardar (RF-L19)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.informe_lote import guardar_con_dialogo, texto_informe
from proxlaunch.nucleo.lote.modelos import InformeLote


class DialogoInforme(QDialog):
    """Muestra el informe y permite copiarlo o guardarlo (el mismo texto en ambos casos)."""

    def __init__(
        self, informe: InformeLote, carpeta: Path | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._informe = informe
        self._carpeta = carpeta
        self.texto = texto_informe(informe)
        self.setWindowTitle(
            QCoreApplication.translate("DialogoInforme", "Simulación del lote")
            if informe.es_simulacion
            else QCoreApplication.translate("DialogoInforme", "Informe del lote")
        )
        self.resize(760, 520)
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setProperty("mono", True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlainText(self.texto)
        self.editor.setAccessibleName(
            QCoreApplication.translate("DialogoInforme", "Texto del informe")
        )
        self._estado = QLabel()
        self._estado.setProperty("secundario", True)
        self.boton_copiar = QPushButton(
            QCoreApplication.translate("DialogoInforme", "Copiar informe")
        )
        self.boton_guardar = QPushButton(
            QCoreApplication.translate("DialogoInforme", "Guardar informe…")
        )
        self.boton_cerrar = QPushButton(QCoreApplication.translate("DialogoInforme", "Cerrar"))
        self.boton_copiar.clicked.connect(self._copiar)
        self.boton_guardar.clicked.connect(self._guardar)
        self.boton_cerrar.clicked.connect(self.accept)
        fila = QHBoxLayout()
        fila.addWidget(self.boton_copiar)
        fila.addWidget(self.boton_guardar)
        fila.addStretch(1)
        fila.addWidget(self.boton_cerrar)
        capa = QVBoxLayout(self)
        capa.addWidget(self.editor, 1)
        capa.addWidget(self._estado)
        capa.addLayout(fila)

    def _copiar(self) -> None:
        QApplication.clipboard().setText(self.texto)
        self._estado.setText(QCoreApplication.translate("DialogoInforme", "Informe copiado."))

    def _guardar(self) -> None:
        ruta = guardar_con_dialogo(self, self._informe, self._carpeta)
        if ruta is not None:
            self._estado.setText(
                QCoreApplication.translate("DialogoInforme", "Guardado en {ruta}").format(
                    ruta=str(ruta)
                )
            )
