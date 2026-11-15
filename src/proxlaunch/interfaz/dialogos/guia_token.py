"""Guía breve «¿Cómo creo un API Token?» (RF-25, CA-25.3)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import (
    NOMBRE_ROL,
    PRIVILEGIOS_ROL,
    alternativa_simple_permisos,
    notas_guia_token,
    notas_privilegios_nuevos,
    pasos_guia_token,
    permisos_acotados,
    privilegios_guia_token,
    texto_pedir_al_administrador,
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
        # Alto para todas las líneas del rol (14 con el MVP 4) sin necesidad de desplazarse.
        privilegios.setFixedHeight(
            privilegios.fontMetrics().lineSpacing() * len(PRIVILEGIOS_ROL) + 24
        )
        capa.addWidget(privilegios)
        lbl_nuevos = QLabel(
            self.tr("Qué se pierde sin los cuatro privilegios nuevos:")
            + "\n"
            + "\n".join(f"• {n}" for n in notas_privilegios_nuevos())
        )
        lbl_nuevos.setWordWrap(True)
        lbl_nuevos.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        capa.addWidget(lbl_nuevos)
        titulo_acotado = QLabel(
            self.tr("Dónde asignar los permisos (recomendado: alcance acotado):")
        )
        titulo_acotado.setWordWrap(True)
        capa.addWidget(titulo_acotado)
        for linea in permisos_acotados():
            lbl_ruta = QLabel(f"• {linea}")
            lbl_ruta.setWordWrap(True)
            lbl_ruta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            capa.addWidget(lbl_ruta)
        self.aviso_alternativa = QLabel(alternativa_simple_permisos())
        self.aviso_alternativa.setWordWrap(True)
        self.aviso_alternativa.setProperty("aviso", True)
        self.aviso_alternativa.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        capa.addWidget(self.aviso_alternativa)
        for nota in notas_guia_token():
            lbl = QLabel(nota)
            lbl.setWordWrap(True)
            lbl.setProperty("aviso", True)
            capa.addWidget(lbl)
        capa.addStretch(1)
        zona = QScrollArea()
        zona.setWidgetResizable(True)
        zona.setWidget(contenido)
        # «Cerrar» se crea primero: es el primer botón del diálogo (orden de creación).
        cerrar = QPushButton(self.tr("Cerrar"))
        cerrar.setDefault(True)
        cerrar.clicked.connect(self.accept)
        self.boton_copiar = QPushButton(self.tr("Copiar texto para mi administrador"))
        self.boton_copiar.setToolTip(
            self.tr(
                "Copia un mensaje con los permisos, la activación de «Import» y la creación de "
                "plantillas que hay que pedir."
            )
        )
        self.boton_copiar.clicked.connect(self._copiar_para_administrador)
        self._estado = QLabel()
        self._estado.setProperty("secundario", True)
        # De derecha a izquierda: «Cerrar» queda a la derecha y es el primer botón del diálogo.
        fila = QHBoxLayout()
        fila.setDirection(QBoxLayout.Direction.RightToLeft)
        fila.addWidget(cerrar)
        fila.addWidget(self._estado, 1)
        fila.addWidget(self.boton_copiar)
        principal = QVBoxLayout(self)
        principal.addWidget(zona)
        principal.addLayout(fila)

    def _copiar_para_administrador(self) -> None:
        """Deja en el portapapeles el texto «Qué pedirle a tu administrador» (CA-O32.2)."""
        QApplication.clipboard().setText(texto_pedir_al_administrador())
        self._estado.setText(self.tr("Texto copiado."))
