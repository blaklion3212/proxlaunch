"""Arranque de la aplicación: QApplication, fuentes, traducciones y tema."""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow


def main() -> int:
    """Abre una ventana vacía (esqueleto para comprobar que PySide6 funciona)."""
    app = QApplication.instance() or QApplication(sys.argv)
    ventana = QMainWindow()
    ventana.setWindowTitle("ProxLaunch")
    ventana.show()
    return app.exec()
