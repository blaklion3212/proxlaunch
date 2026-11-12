"""Detalles técnicos plegables: texto original de Proxmox, UPID y log (RF-21, CA-20.4)."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import ResultadoCreacion


def texto_detalles(
    error: ErrorProxLaunch | None,
    resultado: ResultadoCreacion | None = None,
) -> str:
    """Compone el texto técnico (código, parámetros, mensaje original y log de la tarea)."""
    lineas: list[str] = []
    if resultado is not None:
        etiqueta_resultado = QCoreApplication.translate("Detalles", "Resultado")
        etiqueta_nodo = QCoreApplication.translate("Detalles", "Nodo")
        lineas.append(f"{etiqueta_resultado}: {resultado.desenlace}")
        lineas.append(f"VMID: {resultado.vmid}")
        lineas.append(f"{etiqueta_nodo}: {resultado.nodo}")
        if resultado.upid:
            lineas.append(f"UPID: {resultado.upid}")
    if error is not None:
        etiqueta_codigo = QCoreApplication.translate("Detalles", "Código")
        etiqueta_original = QCoreApplication.translate("Detalles", "Mensaje original")
        lineas.append(f"{etiqueta_codigo}: {error.codigo}")
        for clave, valor in error.params.items():
            lineas.append(f"  {clave}: {valor}")
        if error.detalle_tecnico:
            lineas.append(f"{etiqueta_original}: {error.detalle_tecnico}")
    if resultado is not None and resultado.log_tarea:
        etiqueta_log = QCoreApplication.translate("Detalles", "Registro de la tarea")
        lineas.append("")
        lineas.append(f"{etiqueta_log}:")
        lineas.extend(resultado.log_tarea)
    return "\n".join(lineas)


class DetallesTecnicos(QWidget):
    """Botón «Ver detalles técnicos» que despliega un cuadro de texto monoespaciado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._boton = QPushButton()
        self._boton.setCheckable(True)
        self._texto = QPlainTextEdit()
        self._texto.setReadOnly(True)
        self._texto.setProperty("mono", True)
        self._texto.setMinimumHeight(120)
        self._texto.hide()
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self._boton)
        capa.addWidget(self._texto)
        self._boton.toggled.connect(self._alternar)
        self._alternar(False)
        self.hide()

    def _alternar(self, visible: bool) -> None:
        self._texto.setVisible(visible)
        if visible:
            self._boton.setText(QCoreApplication.translate("Detalles", "Ocultar detalles técnicos"))
        else:
            self._boton.setText(QCoreApplication.translate("Detalles", "Ver detalles técnicos"))

    def establecer(self, texto: str, *, desplegar: bool = False) -> None:
        """Fija el texto; si está vacío el control se oculta."""
        self._texto.setPlainText(texto)
        self.setVisible(bool(texto))
        self._boton.setChecked(desplegar)

    def limpiar(self) -> None:
        self._texto.clear()
        self._boton.setChecked(False)
        self.hide()

    @property
    def texto(self) -> str:
        return self._texto.toPlainText()
