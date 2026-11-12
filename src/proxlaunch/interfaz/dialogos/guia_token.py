"""Guía breve «¿Cómo creo un API Token?» (RF-25, CA-25.3)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import (
    NOMBRE_ROL,
    notas_guia_token,
    pasos_guia_token,
    privilegios_guia_token,
    titulo_guia_token,
)


class DialogoGuiaToken(QDialog):
    """Pasos para crear un token con permisos mínimos (rol ProxLaunchCreador)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo_guia_token())
        self.setMinimumSize(560, 480)
        contenido = QWidget()
        capa = QVBoxLayout(contenido)
        for n, paso in enumerate(pasos_guia_token(), start=1):
            lbl = QLabel(f"{n}. {paso}")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            capa.addWidget(lbl)
        titulo_rol = QLabel(self.tr("Privilegios del rol «{rol}»:").format(rol=NOMBRE_ROL))
        capa.addWidget(titulo_rol)
        privilegios = QPlainTextEdit(privilegios_guia_token())
        privilegios.setReadOnly(True)
        privilegios.setProperty("mono", True)
        privilegios.setFixedHeight(190)
        capa.addWidget(privilegios)
        for nota in notas_guia_token():
            lbl = QLabel(nota)
            lbl.setWordWrap(True)
            lbl.setProperty("aviso", True)
            capa.addWidget(lbl)
        capa.addStretch(1)
        zona = QScrollArea()
        zona.setWidgetResizable(True)
        zona.setWidget(contenido)
        cerrar = QPushButton(self.tr("Cerrar"))
        cerrar.setDefault(True)
        cerrar.clicked.connect(self.accept)
        principal = QVBoxLayout(self)
        principal.addWidget(zona)
        principal.addWidget(cerrar, 0, Qt.AlignmentFlag.AlignRight)
