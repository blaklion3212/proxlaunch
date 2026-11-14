"""Diálogo de pausa del lote: qué hacer ante un error general, repetido o de conexión (RF-L14)."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from proxlaunch.interfaz.textos import texto_error, texto_motivo_pausa
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import MotivoPausa

# Errores de sesión: «Reconectar» tiene sentido.
_CODIGOS_RECONECTAR = frozenset(
    {CodigoError.SESION_EXPIRADA, CodigoError.CREDENCIALES_INVALIDAS, CodigoError.HUELLA_CAMBIADA}
)


class AccionPausa(StrEnum):
    """Decisión del usuario ante la pausa."""

    CONTINUAR = "continuar"  # reanuda (y, si se repetía, ya no vuelve a preguntar por esa causa)
    REINTENTAR = "reintentar"  # reanuda sin ignorar la causa
    DETENER = "detener"  # cancela el lote
    RECONECTAR = "reconectar"
    SIN_ETIQUETAS = "sin_etiquetas"
    COMPROBAR_Y_CONTINUAR = "comprobar_y_continuar"


class DialogoPausaLote(QDialog):
    """Informa de la causa de la pausa y ofrece las acciones que corresponden."""

    def __init__(
        self,
        motivo: MotivoPausa,
        error: ErrorProxLaunch | None,
        *,
        repetidos: int = 0,
        sin_confirmar: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.motivo = motivo
        self.error = error
        self.accion: AccionPausa | None = None
        self.setWindowTitle(texto_motivo_pausa(motivo))
        self.setModal(True)
        self.setMinimumWidth(460)

        titulo = QLabel(texto_motivo_pausa(motivo))
        fuente = titulo.font()
        fuente.setBold(True)
        titulo.setFont(fuente)
        cuerpo = QLabel(self._texto(motivo, error, repetidos, sin_confirmar))
        cuerpo.setWordWrap(True)
        cuerpo.setTextFormat(Qt.TextFormat.PlainText)  # el mensaje puede traer datos del servidor
        cuerpo.setAccessibleName(
            QCoreApplication.translate("DialogoPausaLote", "Motivo de la pausa")
        )
        capa = QVBoxLayout(self)
        capa.addWidget(titulo)
        capa.addWidget(cuerpo)

        self.botones: dict[AccionPausa, QPushButton] = {}
        fila = QHBoxLayout()
        fila.addStretch(1)
        seguro = self._boton(AccionPausa.DETENER, self._texto_detener(motivo))
        if motivo == MotivoPausa.CONEXION:
            self._boton(
                AccionPausa.COMPROBAR_Y_CONTINUAR,
                QCoreApplication.translate("DialogoPausaLote", "Comprobar y continuar"),
            )
        elif motivo == MotivoPausa.REPETIDO:
            self._boton(
                AccionPausa.CONTINUAR, QCoreApplication.translate("DialogoPausaLote", "Continuar")
            )
        else:
            if error is not None and error.codigo in _CODIGOS_RECONECTAR:
                self._boton(
                    AccionPausa.RECONECTAR,
                    QCoreApplication.translate("DialogoPausaLote", "Reconectar…"),
                )
            if error is not None and error.codigo == CodigoError.ETIQUETA_RECHAZADA:
                self._boton(
                    AccionPausa.SIN_ETIQUETAS,
                    QCoreApplication.translate("DialogoPausaLote", "Seguir sin etiquetas"),
                )
            self._boton(
                AccionPausa.REINTENTAR, QCoreApplication.translate("DialogoPausaLote", "Reintentar")
            )
        for b in self.botones.values():
            if b is not seguro:
                fila.addWidget(b)
        fila.addWidget(seguro)
        capa.addLayout(fila)
        # El foco inicial va a la opción que no envía nada más.
        seguro.setDefault(True)
        seguro.setFocus()

    @staticmethod
    def _texto_detener(motivo: MotivoPausa) -> str:
        if motivo == MotivoPausa.REPETIDO:
            return QCoreApplication.translate("DialogoPausaLote", "Detener el lote")
        return QCoreApplication.translate("DialogoPausaLote", "Cancelar lote")

    def _boton(self, accion: AccionPausa, texto: str) -> QPushButton:
        b = QPushButton(texto)
        b.setAutoDefault(False)
        b.clicked.connect(lambda: self._elegir(accion))
        self.botones[accion] = b
        return b

    def _elegir(self, accion: AccionPausa) -> None:
        self.accion = accion
        self.accept()

    @staticmethod
    def _texto(
        motivo: MotivoPausa, error: ErrorProxLaunch | None, repetidos: int, sin_confirmar: int
    ) -> str:
        causa = texto_error(error) if error is not None else ""
        if motivo == MotivoPausa.REPETIDO:
            return texto_error(
                ErrorProxLaunch(
                    CodigoError.LOTE_PAUSADO_REPETIDO,
                    {
                        "n": str(repetidos),
                        "causa": causa
                        or QCoreApplication.translate("DialogoPausaLote", "desconocida"),
                    },
                )
            )
        if motivo == MotivoPausa.CONEXION:
            return (
                texto_error(
                    ErrorProxLaunch(CodigoError.LOTE_PAUSADO_CONEXION, {"n": str(sin_confirmar)})
                )
                + "\n\n"
                + QCoreApplication.translate(
                    "DialogoPausaLote",
                    "«Comprobar y continuar» mira qué pasó con las máquinas sin confirmar y "
                    "después envía solo las que faltaban. Nunca vuelve a enviar una máquina "
                    "que ya salió.",
                )
            )
        texto = causa or QCoreApplication.translate(
            "DialogoPausaLote", "Hubo un problema que afecta a todo el lote."
        )
        texto += "\n\n" + QCoreApplication.translate(
            "DialogoPausaLote", "No se enviará ninguna máquina más hasta que decidas."
        )
        if error is not None and error.codigo == CodigoError.ETIQUETA_RECHAZADA:
            texto += "\n\n" + QCoreApplication.translate(
                "DialogoPausaLote",
                "Puedes seguir sin etiquetas. En ese caso, «Deshacer» solo podrá eliminar las "
                "máquinas que ProxLaunch confirme que creó él mismo.",
            )
        return texto
