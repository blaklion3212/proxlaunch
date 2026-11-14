"""Elegir el almacenamiento que se usará siempre en este servidor (RF-O05, RF-O06, D-24.6).

Se pregunta una sola vez por servidor y contenido cuando hay varios candidatos. El de más espacio
libre llega preseleccionado (resolución C4 del orquestador): el usuario puede aceptar sin más con
Intro. Si el recordado dejó de servir (E-O04) el diálogo ofrece «Elegir otro» o «Dejar de recordar»;
nunca sustituye nada en silencio (INV-O11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.modelos_tabla_origen import formatear_bytes
from proxlaunch.interfaz.textos import texto_contenido, texto_error
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Storage


@dataclass(frozen=True)
class EleccionStorage:
    """Resultado del diálogo.

    - ``storage``: el almacenamiento elegido (``None`` si se pidió dejar de recordar).
    - ``recordar``: guardar la elección en el perfil de conexión del servidor activo.
    - ``dejar_de_recordar``: borrar el storage recordado (solo en el modo «ya no disponible»).
    """

    storage: str | None
    recordar: bool
    dejar_de_recordar: bool = False


def preseleccionado(candidatos: Sequence[Storage]) -> str | None:
    """Id del candidato con más espacio libre (empate: el de menor id); ``None`` si no hay."""
    if not candidatos:
        return None
    return min(candidatos, key=lambda s: (-s.libre_bytes, s.id)).id


class DialogoElegirStorage(QDialog):
    """Lista los almacenamientos candidatos y devuelve la elección en ``eleccion``.

    ``no_disponible`` es el nombre del storage recordado que ya no sirve (E-O04); con él el
    diálogo cambia de mensaje y añade «Dejar de recordar».
    """

    COL_NOMBRE = 0
    COL_TIPO = 1
    COL_LIBRE = 2
    COL_COMPARTIDO = 3
    COL_NOTA = 4

    def __init__(
        self,
        contenido: Contenido,
        candidatos: Sequence[Storage],
        parent: QWidget | None = None,
        *,
        no_disponible: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.contenido = contenido
        self.eleccion: EleccionStorage | None = None
        self._candidatos = tuple(candidatos)
        self._no_disponible = no_disponible
        self.setWindowTitle(self.tr("Elegir almacenamiento"))
        self.setModal(True)
        self.setMinimumWidth(560)

        cuerpo = QLabel(self._texto_principal())
        cuerpo.setWordWrap(True)
        cuerpo.setTextFormat(Qt.TextFormat.PlainText)  # el nombre del storage viene del servidor
        cuerpo.setAccessibleName(self.tr("Explicación"))

        self.tabla = QTableWidget(len(self._candidatos), 5)
        self.tabla.setHorizontalHeaderLabels(
            [
                self.tr("Almacenamiento"),
                self.tr("Tipo"),
                self.tr("Espacio libre"),
                self.tr("Compartido"),
                self.tr("Nota"),
            ]
        )
        self.tabla.setAccessibleName(self.tr("Almacenamientos disponibles"))
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self._llenar()

        self.casilla_recordar = QCheckBox(self.tr("Recordar mi elección"))
        self.casilla_recordar.setChecked(True)
        self.casilla_recordar.setAccessibleName(self.tr("Recordar mi elección"))
        self.casilla_recordar.setToolTip(
            self.tr("Se guarda solo el nombre del almacenamiento, en el perfil de este servidor.")
        )

        capa = QVBoxLayout(self)
        capa.addWidget(cuerpo)
        capa.addWidget(self.tabla)
        capa.addWidget(self.casilla_recordar)

        fila = QHBoxLayout()
        fila.addStretch(1)
        self.boton_dejar = QPushButton(self.tr("Dejar de recordar"))
        self.boton_dejar.setAutoDefault(False)
        self.boton_dejar.setVisible(no_disponible is not None)
        self.boton_dejar.clicked.connect(self._dejar_de_recordar)
        self.boton_cancelar = QPushButton(self.tr("Cancelar"))
        self.boton_cancelar.setAutoDefault(False)
        self.boton_cancelar.clicked.connect(self.reject)
        self.boton_aceptar = QPushButton(
            self.tr("Elegir otro") if no_disponible is not None else self.tr("Usar este")
        )
        self.boton_aceptar.setProperty("primario", True)
        self.boton_aceptar.setDefault(True)
        self.boton_aceptar.clicked.connect(self._aceptar)
        fila.addWidget(self.boton_dejar)
        fila.addWidget(self.boton_cancelar)
        fila.addWidget(self.boton_aceptar)
        capa.addLayout(fila)

        self.tabla.itemSelectionChanged.connect(self._actualizar_botones)
        self.tabla.itemDoubleClicked.connect(lambda _item: self._aceptar())
        self._actualizar_botones()
        self.tabla.setFocus()

    # --- Textos y contenido -------------------------------------------------------------

    def _texto_principal(self) -> str:
        if self._no_disponible is not None:
            return texto_error(
                ErrorProxLaunch(
                    CodigoError.STORAGE_RECORDADO_NO_DISPONIBLE,
                    {"storage": self._no_disponible, "contenido": str(self.contenido)},
                )
            )
        return self.tr(
            "Hay varios almacenamientos para {contenido}. ¿Cuál usar siempre en este servidor?"
        ).format(contenido=texto_contenido(self.contenido))

    def _llenar(self) -> None:
        sugerido = preseleccionado(self._candidatos)
        fila_sugerida = 0
        for fila, s in enumerate(self._candidatos):
            nota = self.tr("Más espacio libre") if s.id == sugerido else ""
            valores = (
                s.id,
                s.tipo,
                f"{formatear_bytes(s.libre_bytes)} / {formatear_bytes(s.total_bytes)}",
                self.tr("Sí") if s.compartido else self.tr("No"),
                nota,
            )
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if col == self.COL_LIBRE:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.tabla.setItem(fila, col, item)
            if s.id == sugerido:
                fila_sugerida = fila
        self.tabla.resizeColumnsToContents()
        if self._candidatos:
            self.tabla.selectRow(fila_sugerida)

    # --- Acciones -----------------------------------------------------------------------

    @property
    def storage_seleccionado(self) -> str | None:
        """Id del almacenamiento marcado en la tabla (``None`` si no hay ninguno)."""
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return self._candidatos[filas[0].row()].id

    def _actualizar_botones(self) -> None:
        self.boton_aceptar.setEnabled(self.storage_seleccionado is not None)

    def _aceptar(self) -> None:
        elegido = self.storage_seleccionado
        if elegido is None:
            return
        self.eleccion = EleccionStorage(elegido, self.casilla_recordar.isChecked())
        self.accept()

    def _dejar_de_recordar(self) -> None:
        self.eleccion = EleccionStorage(None, False, dejar_de_recordar=True)
        self.accept()
