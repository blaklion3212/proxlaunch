"""Panel de progreso por etapas (RF-20): barra naranja con texto, sin porcentaje falso."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_etapa
from proxlaunch.interfaz.vistas.campos import poner_propiedad
from proxlaunch.interfaz.vistas.detalles_tecnicos import DetallesTecnicos
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa

ETAPAS = (Etapa.VALIDANDO, Etapa.ENVIANDO, Etapa.CREANDO, Etapa.COMPROBANDO, Etapa.LISTO)


class PanelProgreso(QGroupBox):
    """Muestra la etapa actual, el UPID (monoespaciado y copiable) y el desenlace."""

    crear_otra = Signal()
    seguir_esperando = Signal()
    comprobar_ahora = Signal()
    volver = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QCoreApplication.translate("PanelProgreso", "Progreso"), parent)
        self.barra = QProgressBar()
        self.barra.setRange(0, len(ETAPAS))
        self.barra.setValue(0)
        self.barra.setFormat("")
        self._etapas = QVBoxLayout()
        self._etapas.setSpacing(2)
        self._lbl_etapas: dict[Etapa, QLabel] = {}
        for etapa in ETAPAS:
            lbl = QLabel(texto_etapa(etapa))
            lbl.setProperty("secundario", True)
            self._lbl_etapas[etapa] = lbl
            self._etapas.addWidget(lbl)
        self._mensaje = QLabel()
        self._mensaje.setTextFormat(Qt.TextFormat.PlainText)
        self._mensaje.setWordWrap(True)
        self._mensaje.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._upid_titulo = QLabel(
            QCoreApplication.translate("PanelProgreso", "Identificador de la tarea (UPID):")
        )
        self._upid_titulo.setProperty("secundario", True)
        # Campo de solo lectura: monoespaciado, seleccionable y sin forzar el ancho del panel.
        self._upid = QLineEdit()
        self._upid.setReadOnly(True)
        self._upid.setProperty("mono", True)
        self._copiar = QPushButton(QCoreApplication.translate("PanelProgreso", "Copiar UPID"))
        self._copiar.clicked.connect(self._copiar_upid)
        self.detalles = DetallesTecnicos()
        self.boton_crear_otra = QPushButton(
            QCoreApplication.translate("PanelProgreso", "Crear otra")
        )
        self.boton_crear_otra.setProperty("primario", True)
        self.boton_seguir = QPushButton(
            QCoreApplication.translate("PanelProgreso", "Seguir esperando")
        )
        self.boton_comprobar = QPushButton(
            QCoreApplication.translate("PanelProgreso", "Comprobar ahora")
        )
        self.boton_volver = QPushButton(
            QCoreApplication.translate("PanelProgreso", "Volver al formulario")
        )
        self.boton_crear_otra.clicked.connect(self.crear_otra)
        self.boton_seguir.clicked.connect(self.seguir_esperando)
        self.boton_comprobar.clicked.connect(self.comprobar_ahora)
        self.boton_volver.clicked.connect(self.volver)
        fila_upid = QHBoxLayout()
        fila_upid.addWidget(self._upid, 1)
        fila_upid.addWidget(self._copiar)
        fila_botones = QHBoxLayout()
        for b in (
            self.boton_crear_otra,
            self.boton_seguir,
            self.boton_comprobar,
            self.boton_volver,
        ):
            fila_botones.addWidget(b)
        fila_botones.addStretch(1)
        capa = QVBoxLayout(self)
        capa.addWidget(self.barra)
        capa.addLayout(self._etapas)
        capa.addWidget(self._mensaje)
        capa.addWidget(self._upid_titulo)
        capa.addLayout(fila_upid)
        capa.addWidget(self.detalles)
        capa.addLayout(fila_botones)
        self.reiniciar()

    def reiniciar(self) -> None:
        """Estado inicial, antes de crear nada."""
        self.barra.setValue(0)
        self.barra.setFormat(QCoreApplication.translate("PanelProgreso", "Sin tareas en curso"))
        for etapa, lbl in self._lbl_etapas.items():
            lbl.setText(texto_etapa(etapa))
            poner_propiedad(lbl, "secundario", True)
            poner_propiedad(lbl, "exito", False)
        self._mensaje.clear()
        self._mensaje.hide()
        self.establecer_upid(None)
        self.detalles.limpiar()
        self._botones(False, False, False, False)

    def _botones(self, otra: bool, seguir: bool, comprobar: bool, volver: bool) -> None:
        self.boton_crear_otra.setVisible(otra)
        self.boton_seguir.setVisible(seguir)
        self.boton_comprobar.setVisible(comprobar)
        self.boton_volver.setVisible(volver)

    def iniciar(self) -> None:
        """Comienza el seguimiento de una creación."""
        self.reiniciar()
        self.establecer_etapa(Etapa.VALIDANDO)

    def establecer_etapa(self, etapa: Etapa) -> None:
        """Marca la etapa actual: barra por etapas, sin porcentaje."""
        indice = ETAPAS.index(etapa)
        self.barra.setValue(indice + 1 if etapa == Etapa.LISTO else indice)
        self.barra.setFormat(texto_etapa(etapa))
        for i, e in enumerate(ETAPAS):
            lbl = self._lbl_etapas[e]
            base = texto_etapa(e)
            if i < indice or etapa == Etapa.LISTO:
                lbl.setText("✓ " + base)
                poner_propiedad(lbl, "secundario", False)
                poner_propiedad(lbl, "exito", True)
            elif i == indice:
                lbl.setText("● " + base)
                poner_propiedad(lbl, "secundario", False)
                poner_propiedad(lbl, "exito", False)
            else:
                lbl.setText(base)
                poner_propiedad(lbl, "secundario", True)
                poner_propiedad(lbl, "exito", False)

    def establecer_upid(self, upid: str | None) -> None:
        visible = bool(upid)
        self._upid.setText(upid or "")
        for w in (self._upid, self._upid_titulo, self._copiar):
            w.setVisible(visible)

    def _copiar_upid(self) -> None:
        QApplication.clipboard().setText(self._upid.text())

    def mostrar_resultado(self, texto: str, desenlace: Desenlace, upid: str | None) -> None:
        """Muestra el mensaje final con el color del desenlace y los botones que correspondan."""
        self.establecer_upid(upid)
        ok = desenlace in (Desenlace.OK, Desenlace.CON_AVISOS)
        poner_propiedad(self._mensaje, "exito", desenlace == Desenlace.OK)
        poner_propiedad(
            self._mensaje,
            "aviso",
            desenlace
            in (Desenlace.CON_AVISOS, Desenlace.TIEMPO_AGOTADO, Desenlace.CONEXION_PERDIDA),
        )
        poner_propiedad(self._mensaje, "error", desenlace in (Desenlace.ERROR, Desenlace.PARCIAL))
        self._mensaje.setText(texto)
        self._mensaje.show()
        self.boton_comprobar.setText(
            QCoreApplication.translate("PanelProgreso", "Comprobar")
            if not upid
            else QCoreApplication.translate("PanelProgreso", "Comprobar ahora")
        )
        if desenlace == Desenlace.TIEMPO_AGOTADO:
            self._botones(False, True, True, True)
        elif desenlace == Desenlace.CONEXION_PERDIDA:
            self._botones(False, False, True, True)
        else:
            self._botones(ok, False, False, not ok)

    def mostrar_progreso_mensaje(self, texto: str) -> None:
        """Mensaje intermedio (por ejemplo, mientras se vuelve a comprobar)."""
        poner_propiedad(self._mensaje, "exito", False)
        poner_propiedad(self._mensaje, "error", False)
        poner_propiedad(self._mensaje, "aviso", False)
        self._mensaje.setText(texto)
        self._mensaje.show()
        self._botones(False, False, False, False)

    @property
    def texto_mensaje(self) -> str:
        return self._mensaje.text()

    @property
    def texto_upid(self) -> str:
        return self._upid.text()
