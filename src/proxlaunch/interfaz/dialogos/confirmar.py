"""Confirmaciones de acciones con consecuencias: el foco inicial va siempre a «Cancelar»."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget


def confirmar(
    parent: QWidget | None,
    titulo: str,
    texto: str,
    texto_aceptar: str,
    texto_cancelar: str,
) -> bool:
    """Pregunta con dos botones con nombre propio; devuelve ``True`` solo si acepta.

    El botón de cancelar es el predeterminado, así que pulsar Intro o cerrar la ventana no
    confirma nada (RNF-L04).
    """
    caja = QMessageBox(parent)
    caja.setIcon(QMessageBox.Icon.Warning)
    caja.setWindowTitle(titulo)
    caja.setText(texto)
    caja.setTextFormat(Qt.TextFormat.PlainText)
    aceptar = caja.addButton(texto_aceptar, QMessageBox.ButtonRole.AcceptRole)
    cancelar = caja.addButton(texto_cancelar, QMessageBox.ButtonRole.RejectRole)
    caja.setDefaultButton(cancelar)
    caja.setEscapeButton(cancelar)
    cancelar.setFocus()
    caja.exec()
    return caja.clickedButton() is aceptar
