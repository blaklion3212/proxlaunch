"""Diálogos de huella SSL: servidor nuevo (CA-05.1) y certificado cambiado (CA-05.4/05.5)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_error
from proxlaunch.interfaz.vistas.campos import boton_ayuda
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.servicios.conexion import EstadoHuella, InformacionHuella


def _plano(texto: str) -> QLabel:
    lbl = QLabel(texto)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    return lbl


def _caja_huella(huella: str) -> QPlainTextEdit:
    """Huella en fuente monoespaciada, seleccionable y que ajusta la línea en cualquier punto."""
    from PySide6.QtGui import QTextOption

    caja = QPlainTextEdit(huella)
    caja.setReadOnly(True)
    caja.setProperty("mono", True)
    caja.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
    caja.setFixedHeight(60)
    return caja


class DialogoHuella(QDialog):
    """Muestra la huella SHA-256 del servidor para confiar en ella o bloquear la conexión.

    ``reemplazar`` es ``True`` si el usuario eligió, en modo avanzado y tras confirmarlo,
    sustituir la huella guardada.
    """

    def __init__(
        self,
        info: InformacionHuella,
        avanzado: bool,
        parent: QWidget | None = None,
        *,
        archivo_danado: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(520)
        self.info = info
        self.reemplazar = False
        self._avanzado = avanzado
        capa = QVBoxLayout(self)
        destino = f"{info.host}:{info.puerto}"
        botones = QHBoxLayout()
        botones.addStretch(1)
        if info.estado == EstadoHuella.CAMBIADA:
            self.setWindowTitle(self.tr("El certificado del servidor cambió"))
            aviso = QLabel(texto_error(ErrorProxLaunch(CodigoError.HUELLA_CAMBIADA)))
            aviso.setWordWrap(True)
            aviso.setProperty("error", True)
            capa.addWidget(aviso)
            capa.addWidget(_plano(self.tr("Servidor: {destino}").format(destino=destino)))
            capa.addWidget(QLabel(self.tr("Huella guardada:")))
            capa.addWidget(_caja_huella(info.huella_guardada or ""))
            capa.addWidget(QLabel(self.tr("Huella nueva:")))
            capa.addWidget(_caja_huella(info.huella_observada or ""))
            cerrar = QPushButton(self.tr("Cerrar"))
            cerrar.setDefault(True)
            cerrar.clicked.connect(self.reject)
            botones.addWidget(cerrar)
            if avanzado:
                # CA-05.5: solo en modo avanzado y con confirmación explícita.
                boton = QPushButton(self.tr("Reemplazar la huella guardada"))
                boton.setAutoDefault(False)
                boton.clicked.connect(self._confirmar_reemplazo)
                botones.addWidget(boton)
        else:
            self.setWindowTitle(self.tr("Confiar en este servidor"))
            if archivo_danado:
                # Seg M2: no es «primera vez»: se perdió el registro, hay que comparar.
                texto_intro = self.tr(
                    "No tenemos registro de este servidor porque el archivo de huellas se "
                    "dañó. Compara la huella con la de tu administrador antes de confiar."
                )
            else:
                texto_intro = self.tr(
                    "Es la primera vez que te conectas a este servidor. Comprueba que la "
                    "huella de abajo coincide con la que te dio tu administrador. No se ha "
                    "enviado ninguna credencial."
                )
            intro = QLabel(texto_intro)
            intro.setTextFormat(Qt.TextFormat.PlainText)
            intro.setWordWrap(True)
            capa.addWidget(intro)
            capa.addWidget(_plano(self.tr("Servidor: {host}").format(host=info.host)))
            capa.addWidget(QLabel(self.tr("Puerto: {puerto}").format(puerto=info.puerto)))
            fila = QHBoxLayout()
            fila.addWidget(QLabel(self.tr("Huella SHA-256:")))
            fila.addStretch(1)
            fila.addWidget(boton_ayuda("huella_ssl"))
            capa.addLayout(fila)
            capa.addWidget(_caja_huella(info.huella_observada or ""))
            cancelar = QPushButton(self.tr("Cancelar"))
            cancelar.setDefault(True)  # Seg B1: Intro nunca confía por accidente
            cancelar.clicked.connect(self.reject)
            confiar = QPushButton(self.tr("Confiar y continuar"))
            confiar.setAutoDefault(False)
            confiar.setProperty("primario", True)
            confiar.clicked.connect(self.accept)
            botones.addWidget(cancelar)
            botones.addWidget(confiar)
        capa.addLayout(botones)

    def _confirmar_reemplazo(self) -> None:
        respuesta = QMessageBox.warning(
            self,
            self.tr("Reemplazar la huella guardada"),
            self.tr(
                "Vas a confiar en el certificado nuevo de {destino}. Hazlo solo si tu "
                "administrador confirmó el cambio. ¿Reemplazar la huella guardada?"
            ).format(destino=f"{self.info.host}:{self.info.puerto}"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            self.reemplazar = True
            self.accept()
