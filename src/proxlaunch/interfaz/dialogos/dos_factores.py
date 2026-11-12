"""Diálogo del segundo factor: código TOTP de 6 dígitos o clave de recuperación (RF-04)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_problema
from proxlaunch.interfaz.vistas.campos import EnlaceLabel, boton_ayuda, mensaje, poner_mensaje
from proxlaunch.nucleo.api.autenticacion import DesafioTFA, TipoTFA
from proxlaunch.nucleo.validacion import validar_codigo_totp


class DialogoDosFactores(QDialog):
    """Pide el segundo factor. Emite ``enviado(codigo, tipo)``; no cierra hasta que acierte."""

    enviado = Signal(str, object)

    def __init__(self, desafio: DesafioTFA, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Código de verificación"))
        self.setModal(True)
        self.setMinimumWidth(420)
        self._desafio = desafio
        self._recuperacion = not desafio.totp and desafio.recuperacion
        self._titulo = QLabel()
        self._titulo.setWordWrap(True)
        self._campo = QLineEdit()
        self._campo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._campo.setProperty("mono", True)
        self._alternar = EnlaceLabel("")
        self._error = mensaje(error=True)
        self._boton_ok = QPushButton(self.tr("Verificar"))
        self._boton_ok.setDefault(True)
        self._boton_ok.setProperty("primario", True)
        self._boton_cancelar = QPushButton(self.tr("Cancelar"))
        fila_campo = QHBoxLayout()
        fila_campo.addWidget(self._campo, 1)
        fila_campo.addWidget(boton_ayuda("tfa"))
        botones = QHBoxLayout()
        botones.addStretch(1)
        botones.addWidget(self._boton_cancelar)
        botones.addWidget(self._boton_ok)
        capa = QVBoxLayout(self)
        capa.addWidget(self._titulo)
        capa.addLayout(fila_campo)
        capa.addWidget(self._alternar)
        capa.addWidget(self._error)
        capa.addLayout(botones)
        self._boton_ok.clicked.connect(self._enviar)
        self._campo.returnPressed.connect(self._enviar)
        self._boton_cancelar.clicked.connect(self.reject)
        self._alternar.clicked.connect(self._cambiar_modo)
        # Solo se ofrece el cambio si el servidor admite ambos métodos.
        self._alternar.setVisible(desafio.totp and desafio.recuperacion)
        self._aplicar_modo()

    @property
    def uso_recuperacion(self) -> bool:
        return self._recuperacion

    def _aplicar_modo(self) -> None:
        self._campo.clear()
        poner_mensaje(self._error, None)
        if self._recuperacion:
            self._titulo.setText(
                self.tr("Escribe una de tus claves de recuperación. Cada clave solo sirve una vez.")
            )
            self._campo.setMaxLength(64)
            self._campo.setPlaceholderText(self.tr("clave de recuperación"))
            self._alternar.setText(self.tr("Usar el código de la aplicación"))
        else:
            self._titulo.setText(
                self.tr(
                    "Escribe el código de 6 números que muestra tu aplicación de autenticación."
                )
            )
            self._campo.setMaxLength(6)
            self._campo.setPlaceholderText("123456")
            self._alternar.setText(self.tr("Usar una clave de recuperación"))
        self._campo.setFocus()

    def _cambiar_modo(self) -> None:
        self._recuperacion = not self._recuperacion
        self._aplicar_modo()

    def _enviar(self) -> None:
        codigo = self._campo.text().strip()
        if self._recuperacion:
            if not codigo:
                poner_mensaje(self._error, self.tr("Escribe la clave de recuperación."))
                return
            tipo = TipoTFA.RECUPERACION
        else:
            problemas = validar_codigo_totp(codigo)
            if problemas:
                poner_mensaje(self._error, texto_problema(problemas[0]))
                return
            tipo = TipoTFA.TOTP
        poner_mensaje(self._error, None)
        self.establecer_ocupado(True)
        self.enviado.emit(codigo, tipo)

    def establecer_ocupado(self, ocupado: bool) -> None:
        for w in (self._campo, self._boton_ok, self._alternar):
            w.setEnabled(not ocupado)

    def mostrar_error(self, texto: str) -> None:
        """Muestra el error y permite reintentar sin volver a pedir usuario y contraseña."""
        poner_mensaje(self._error, texto)
        self.establecer_ocupado(False)
        self._campo.selectAll()
        self._campo.setFocus()
