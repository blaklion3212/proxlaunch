"""Tabla de interfaces de red de la MV (RF-17)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import ayuda
from proxlaunch.interfaz.textos import texto_problema
from proxlaunch.interfaz.vistas.campos import mensaje, poner_mensaje, poner_propiedad
from proxlaunch.nucleo.modelos.inventario import Bridge
from proxlaunch.nucleo.modelos.vm import InterfazRed, ModeloRed
from proxlaunch.nucleo.validacion import Problema, Severidad
from proxlaunch.nucleo.valores_defecto import bridge_por_defecto

_C_INDICE, _C_BRIDGE, _C_MODELO, _C_VLAN, _C_QUITAR = range(5)


def vlan_desde_texto(texto: str) -> int | None:
    """Vacío = sin etiqueta; un texto no numérico se convierte en 0 (la regla V-15 lo rechaza)."""
    t = texto.strip()
    if not t:
        return None
    try:
        return int(t)
    except ValueError:
        return 0


class _FilaRed:
    def __init__(self) -> None:
        self.indice = QLabel()
        self.indice.setProperty("mono", True)
        self.bridge = QComboBox()
        self.bridge.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.bridge.setMinimumContentsLength(10)
        self.modelo = QComboBox()
        self.modelo.addItem("VirtIO", ModeloRed.VIRTIO)
        self.modelo.addItem("Intel E1000", ModeloRed.E1000)
        self.perdido: str | None = None  # selección pedida que no existe en el nodo
        self.vlan = QLineEdit()
        self.vlan.setMaximumWidth(80)
        self.vlan.setPlaceholderText(QCoreApplication.translate("TablaRedes", "Sin VLAN"))
        self.quitar = QPushButton(QCoreApplication.translate("TablaRedes", "Quitar"))

    def widgets(self) -> list[tuple[int, QWidget]]:
        return [
            (_C_INDICE, self.indice),
            (_C_BRIDGE, self.bridge),
            (_C_MODELO, self.modelo),
            (_C_VLAN, self.vlan),
            (_C_QUITAR, self.quitar),
        ]


class TablaRedes(QWidget):
    """Lista editable de interfaces de red. Emite ``cambiado`` ante cualquier modificación."""

    cambiado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filas: list[_FilaRed] = []
        self._bridges: list[Bridge] = []
        self._avanzado = False
        self._avanzados: list[QWidget] = []
        self._rejilla = QGridLayout()
        self._rejilla.setHorizontalSpacing(8)
        self._rejilla.setVerticalSpacing(4)
        self._cabeceras: dict[int, QLabel] = {}
        for col, texto, clave in (
            (_C_INDICE, QCoreApplication.translate("TablaRedes", "Interfaz"), None),
            (_C_BRIDGE, QCoreApplication.translate("TablaRedes", "Red (bridge)"), "bridge"),
            (_C_MODELO, QCoreApplication.translate("TablaRedes", "Tarjeta"), "modelo_red"),
            (_C_VLAN, QCoreApplication.translate("TablaRedes", "VLAN"), "vlan"),
        ):
            lbl = QLabel(texto)
            lbl.setProperty("secundario", True)
            if clave:
                lbl.setToolTip(ayuda(clave))
            self._cabeceras[col] = lbl
            self._rejilla.addWidget(lbl, 0, col)
        self._avanzados.append(self._cabeceras[_C_MODELO])
        self._rejilla.setColumnStretch(_C_BRIDGE, 1)
        self._agregar = QPushButton(QCoreApplication.translate("TablaRedes", "Agregar interfaz"))
        self._agregar.clicked.connect(lambda: self.agregar_red())
        self._errores = mensaje(error=True)
        self._aviso_nodo = mensaje(aviso=True)
        self._sin_redes = mensaje(error=True)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addLayout(self._rejilla)
        capa.addWidget(self._agregar, 0, Qt.AlignmentFlag.AlignLeft)
        capa.addWidget(self._sin_redes)
        capa.addWidget(self._errores)
        capa.addWidget(self._aviso_nodo)
        self._aplicar_visibilidad()

    @property
    def widgets_avanzados(self) -> list[QWidget]:
        return list(self._avanzados)

    def establecer_avanzado(self, avanzado: bool) -> None:
        self._avanzado = avanzado
        self._aplicar_visibilidad()

    def _aplicar_visibilidad(self) -> None:
        for w in self._avanzados:
            w.setVisible(self._avanzado)

    def establecer_bridges(self, bridges: Sequence[Bridge]) -> list[str]:
        """Recarga los bridges del nodo; devuelve los que ya no existen (CA-11.7)."""
        self._bridges = list(bridges)
        perdidos: list[str] = []
        for f in self._filas:
            previo = f.bridge.currentData() or f.perdido
            self._llenar_bridge(f)
            idx = f.bridge.findData(previo) if previo else -1
            f.bridge.setCurrentIndex(idx)
            f.perdido = str(previo) if idx < 0 and previo else None
            if idx < 0 and previo:
                perdidos.append(str(previo))
        self._agregar.setEnabled(bool(self._bridges))
        poner_mensaje(
            self._sin_redes,
            None
            if self._bridges
            else QCoreApplication.translate(
                "TablaRedes", "El nodo no tiene redes (bridges) disponibles"
            ),
        )
        self.cambiado.emit()
        return perdidos

    def establecer_redes(self, redes: Sequence[InterfazRed]) -> None:
        for f in list(self._filas):
            self._quitar_fila(f, emitir=False)
        for r in redes:
            self._nueva_fila(r)
        self._renumerar()
        self.cambiado.emit()

    def agregar_red(self, red: InterfazRed | None = None) -> None:
        if red is None:
            red = InterfazRed(bridge=bridge_por_defecto(self._bridges) or "")
        self._nueva_fila(red)
        self._renumerar()
        self.cambiado.emit()

    def redes(self) -> list[InterfazRed]:
        return [
            InterfazRed(
                bridge=str(f.bridge.currentData() or ""),
                modelo=ModeloRed(f.modelo.currentData()),
                vlan=vlan_desde_texto(f.vlan.text()),
            )
            for f in self._filas
        ]

    def hay_bridges(self) -> bool:
        return bool(self._bridges)

    def aplicar_problemas(self, problemas: Sequence[Problema]) -> None:
        errores: list[str] = []
        con_vlan: set[int] = set()
        for p in problemas:
            if not p.campo.startswith("redes[") or p.severidad != Severidad.ERROR:
                continue
            try:
                i = int(p.campo[len("redes[") : p.campo.index("]")])
            except ValueError:
                continue
            if i >= len(self._filas):
                continue
            errores.append(f"{self._filas[i].indice.text()}: {texto_problema(p)}")
            if p.campo.endswith(".vlan"):
                con_vlan.add(i)
        for i, f in enumerate(self._filas):
            poner_propiedad(f.vlan, "invalido", i in con_vlan)
        poner_mensaje(self._errores, "\n".join(dict.fromkeys(errores)))

    def mostrar_aviso_nodo(self, texto: str | None) -> None:
        poner_mensaje(self._aviso_nodo, texto, aviso=True)

    def habilitar(self, habilitado: bool) -> None:
        self.setEnabled(habilitado)

    # --- Internos ---------------------------------------------------------------------

    def _llenar_bridge(self, f: _FilaRed) -> None:
        f.bridge.blockSignals(True)
        f.bridge.clear()
        f.bridge.setPlaceholderText(QCoreApplication.translate("TablaRedes", "Elige una red"))
        for b in self._bridges:
            f.bridge.addItem(b.nombre, b.nombre)
        f.bridge.blockSignals(False)

    def _nueva_fila(self, red: InterfazRed) -> None:
        f = _FilaRed()
        self._llenar_bridge(f)
        f.bridge.setCurrentIndex(f.bridge.findData(red.bridge))
        f.modelo.setCurrentIndex(max(f.modelo.findData(red.modelo), 0))
        f.vlan.setText("" if red.vlan is None else str(red.vlan))
        f.bridge.currentIndexChanged.connect(lambda _i, fila=f: self._al_cambiar_bridge(fila))
        f.modelo.currentIndexChanged.connect(lambda _i: self.cambiado.emit())
        f.vlan.textEdited.connect(lambda _t: self.cambiado.emit())
        f.quitar.clicked.connect(lambda _c=False, fila=f: self._quitar_fila(fila))
        self._filas.append(f)
        for col, w in f.widgets():
            self._rejilla.addWidget(w, len(self._filas), col)
        self._avanzados.append(f.modelo)
        f.modelo.setVisible(self._avanzado)

    def _al_cambiar_bridge(self, f: _FilaRed) -> None:
        if f.bridge.currentIndex() >= 0:
            f.perdido = None  # el usuario eligió otro valor
        self.cambiado.emit()

    def _quitar_fila(self, f: _FilaRed, *, emitir: bool = True) -> None:
        self._filas.remove(f)
        for _col, w in f.widgets():
            self._rejilla.removeWidget(w)
            if w in self._avanzados:
                self._avanzados.remove(w)
            w.deleteLater()
        for n, resto in enumerate(self._filas, start=1):
            for col, w in resto.widgets():
                self._rejilla.addWidget(w, n, col)
        if emitir:
            self._renumerar()
            self.cambiado.emit()

    def _renumerar(self) -> None:
        for n, f in enumerate(self._filas):
            f.indice.setText(f"net{n}")
