"""Piezas reutilizables de formulario: propiedades de estilo, filas con ayuda y enlaces."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from proxlaunch.interfaz.ayuda import ayuda


def poner_propiedad(widget: QWidget, nombre: str, valor: bool) -> None:
    """Fija una propiedad booleana del QSS (``invalido``, ``error``...) y repinta."""
    actual = bool(widget.property(nombre))
    if actual == valor:
        return
    widget.setProperty(nombre, valor)
    estilo = widget.style()
    estilo.unpolish(widget)
    estilo.polish(widget)
    widget.update()


def etiqueta(texto: str, *, secundario: bool = False, mono: bool = False) -> QLabel:
    """Crea una etiqueta con ajuste de línea y las propiedades del tema."""
    lbl = QLabel(texto)
    lbl.setWordWrap(True)
    if secundario:
        lbl.setProperty("secundario", True)
    if mono:
        lbl.setProperty("mono", True)
    return lbl


def mensaje(*, error: bool = False, aviso: bool = False) -> QLabel:
    """Etiqueta oculta para mensajes de error (``error``) o aviso (``aviso``)."""
    lbl = QLabel()
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    if error:
        lbl.setProperty("error", True)
    if aviso:
        lbl.setProperty("aviso", True)
    lbl.hide()
    return lbl


def poner_mensaje(lbl: QLabel, texto: str | None, *, aviso: bool = False) -> None:
    """Muestra ``texto`` como error o aviso (o lo oculta si es ``None`` o vacío)."""
    if not texto:
        lbl.hide()
        lbl.clear()
        return
    poner_propiedad(lbl, "error", not aviso)
    poner_propiedad(lbl, "aviso", aviso)
    lbl.setText(texto)
    lbl.show()


class EnlaceLabel(QLabel):
    """Etiqueta con aspecto de enlace (propiedad ``enlace``) que emite ``clicked``."""

    clicked = Signal()

    def __init__(self, texto: str, parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setProperty("enlace", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        fuente = self.font()
        fuente.setUnderline(True)
        self.setFont(fuente)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(ev)

    def keyPressEvent(self, ev) -> None:
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(ev)


def boton_ayuda(clave: str, parent: QWidget | None = None) -> QToolButton:
    """Icono «?» con la ayuda del campo como sugerencia (CA-25.1)."""
    texto = ayuda(clave)
    btn = QToolButton(parent)
    btn.setText("?")
    btn.setToolTip(texto)
    btn.setAccessibleName(QCoreApplication.translate("Campos", "Ayuda"))
    btn.setAccessibleDescription(texto)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    btn.setAutoRaise(True)
    btn.setCursor(Qt.CursorShape.WhatsThisCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    # El QSS general da 12 px de relleno a los botones: aquí se anula para que quepa el «?».
    btn.setStyleSheet("padding: 0px; min-height: 0px;")
    btn.setFixedSize(24, 24)
    # Al pulsar muestra la sugerencia en el sitio (útil con teclado y pantallas táctiles).
    btn.clicked.connect(lambda: _mostrar_tooltip(btn))
    return btn


def _mostrar_tooltip(btn: QToolButton) -> None:
    from PySide6.QtWidgets import QToolTip

    QToolTip.showText(btn.mapToGlobal(btn.rect().bottomLeft()), btn.toolTip(), btn)


class FilaCampo(QWidget):
    """Una fila «etiqueta + campo + ayuda» con una línea de error/aviso debajo.

    Atributos:
        campo: el widget editable.
        tocado: el usuario ya interactuó; hasta entonces no se muestran errores (así el
            formulario recién abierto no aparece en rojo).
    """

    ANCHO_ETIQUETA = 150

    def __init__(
        self,
        texto: str,
        campo: QWidget,
        clave_ayuda: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.campo = campo
        self.tocado = False
        self._tooltip_original = campo.toolTip()
        self._etiqueta = QLabel(texto)
        self._etiqueta.setMinimumWidth(self.ANCHO_ETIQUETA)
        self._etiqueta.setBuddy(campo)
        self._aviso_extra = mensaje(aviso=True)
        self._error = mensaje(error=True)
        rejilla = QGridLayout(self)
        rejilla.setContentsMargins(0, 2, 0, 2)
        rejilla.setHorizontalSpacing(8)
        rejilla.setVerticalSpacing(1)
        rejilla.addWidget(self._etiqueta, 0, 0, Qt.AlignmentFlag.AlignTop)
        # Un campo con ancho máximo se alinea a la izquierda; los demás ocupan toda la celda.
        alineacion = (
            Qt.AlignmentFlag.AlignLeft if campo.maximumWidth() < 16777215 else Qt.AlignmentFlag(0)
        )
        rejilla.addWidget(campo, 0, 1, alineacion)
        if clave_ayuda:
            rejilla.addWidget(boton_ayuda(clave_ayuda), 0, 2, Qt.AlignmentFlag.AlignTop)
        rejilla.addWidget(self._error, 1, 1)
        rejilla.addWidget(self._aviso_extra, 2, 1)
        rejilla.setColumnStretch(1, 1)

    def marcar_tocado(self) -> None:
        self.tocado = True

    def mostrar_error(self, texto: str | None) -> None:
        """Muestra el error junto al campo (propiedad ``invalido`` incluida)."""
        visible = bool(texto) and self.tocado
        poner_mensaje(self._error, texto if visible else None)
        poner_propiedad(self.campo, "invalido", visible)
        self.campo.setToolTip((texto or "") if visible else self._tooltip_original)

    def mostrar_aviso(self, texto: str | None) -> None:
        """Muestra un aviso no bloqueante junto al campo."""
        poner_mensaje(self._aviso_extra, texto, aviso=True)

    @property
    def hay_error(self) -> bool:
        return not self._error.isHidden()
