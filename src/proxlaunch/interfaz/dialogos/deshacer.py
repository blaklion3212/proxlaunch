"""Diálogo «Deshacer»: elige qué máquinas del lote se eliminarán de Proxmox (RF-L18)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_estado_mv, texto_motivo_no_elegible
from proxlaunch.nucleo.lote.modelos import CandidatoRollback

_ROL_INDICE = Qt.ItemDataRole.UserRole


class DialogoDeshacer(QDialog):
    """Lista con casillas, advertencia y botón «Eliminar N máquinas» con foco en Cancelar."""

    def __init__(self, candidatos: Sequence[CandidatoRollback], parent: QWidget | None = None):
        super().__init__(parent)
        self._candidatos = list(candidatos)
        self.setWindowTitle(
            QCoreApplication.translate("DialogoDeshacer", "Deshacer lo creado por el lote")
        )
        self.setModal(True)
        self.setMinimumWidth(520)

        self.radio_todo = QRadioButton(
            QCoreApplication.translate("DialogoDeshacer", "Todo lo que creó el lote")
        )
        self.radio_incompletas = QRadioButton(
            QCoreApplication.translate("DialogoDeshacer", "Solo las incompletas")
        )
        self.radio_todo.setChecked(True)
        self.radio_todo.toggled.connect(self._al_cambiar_alcance)

        self.lista = QListWidget()
        self.lista.setAccessibleName(
            QCoreApplication.translate("DialogoDeshacer", "Máquinas que se pueden eliminar")
        )
        for i, c in enumerate(self._candidatos):
            el = c.entrada.elemento
            if c.elegible:
                texto = f"{el.nombre} ({el.vmid}) — {texto_estado_mv(c.entrada.estado)}"
            else:
                texto = f"{el.nombre} ({el.vmid}) — {texto_motivo_no_elegible(c.motivo)}"
            item = QListWidgetItem(texto)
            item.setData(_ROL_INDICE, i)
            flags = item.flags() & ~Qt.ItemFlag.ItemIsUserTristate
            if c.elegible:
                item.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
            self.lista.addItem(item)
        self.lista.itemChanged.connect(lambda _i: self._actualizar())

        self._advertencia = QLabel()
        self._advertencia.setWordWrap(True)
        self._advertencia.setProperty("error", True)
        self._advertencia.setTextFormat(Qt.TextFormat.PlainText)
        self.boton_eliminar = QPushButton()
        self.boton_cancelar = QPushButton(QCoreApplication.translate("DialogoDeshacer", "Cancelar"))
        self.boton_eliminar.setAutoDefault(False)
        self.boton_eliminar.clicked.connect(self.accept)
        self.boton_cancelar.clicked.connect(self.reject)

        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self.boton_eliminar)
        fila.addWidget(self.boton_cancelar)
        capa = QVBoxLayout(self)
        capa.addWidget(
            QLabel(QCoreApplication.translate("DialogoDeshacer", "¿Qué quieres deshacer?"))
        )
        capa.addWidget(self.radio_todo)
        capa.addWidget(self.radio_incompletas)
        capa.addWidget(self.lista)
        capa.addWidget(self._advertencia)
        capa.addLayout(fila)
        self._actualizar()
        # Acción destructiva: el foco y la tecla Intro son de «Cancelar».
        self.boton_cancelar.setDefault(True)
        self.boton_cancelar.setFocus()

    def _al_cambiar_alcance(self, _todo: bool) -> None:
        solo_incompletas = self.radio_incompletas.isChecked()
        self.lista.blockSignals(True)
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            c = self._candidatos[item.data(_ROL_INDICE)]
            if c.elegible:
                marcado = c.incompleta if solo_incompletas else True
                item.setCheckState(Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked)
        self.lista.blockSignals(False)
        self._actualizar()

    def elegidos(self) -> list[CandidatoRollback]:
        """Candidatos marcados (solo los elegibles pueden estarlo)."""
        res: list[CandidatoRollback] = []
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            c = self._candidatos[item.data(_ROL_INDICE)]
            if c.elegible and item.checkState() == Qt.CheckState.Checked:
                res.append(c)
        return res

    def _actualizar(self) -> None:
        n = len(self.elegidos())
        if n == 1:
            self._advertencia.setText(
                QCoreApplication.translate(
                    "DialogoDeshacer",
                    "Se eliminará esta máquina y sus discos de Proxmox. Esta acción no se puede "
                    "deshacer.",
                )
            )
            self.boton_eliminar.setText(
                QCoreApplication.translate("DialogoDeshacer", "Eliminar 1 máquina")
            )
        else:
            self._advertencia.setText(
                QCoreApplication.translate(
                    "DialogoDeshacer",
                    "Se eliminarán estas %n máquinas y sus discos de Proxmox. Esta acción no se "
                    "puede deshacer.",
                    None,
                    n,
                )
            )
            self.boton_eliminar.setText(
                QCoreApplication.translate("DialogoDeshacer", "Eliminar %n máquinas", None, n)
            )
        self.boton_eliminar.setEnabled(n > 0)
