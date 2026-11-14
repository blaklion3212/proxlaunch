"""Panel «Este lote no encaja en este servidor» (RF-G04, E-M15).

Lista cada almacenamiento, red o nodo del lote cargado que el servidor actual no tiene y deja
que el usuario elija con «Usar otro…» entre los que sí existen. Nunca sustituye nada por su
cuenta (CA-G04.3): solo emite ``sustitucion_pedida`` y la ventana aplica
``sustituir(definicion, desajuste, nuevo)`` y vuelve a llamar a ``establecer_desajustes``.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_desajuste
from proxlaunch.interfaz.vistas.campos import etiqueta
from proxlaunch.nucleo.lotes_guardados.revalidacion import Desajuste, TipoDesajuste

MAX_AFECTADAS_VISIBLES = 6


class PanelLoteNoEncaja(QFrame):
    """Panel con un renglón por desajuste.

    Señal: ``sustitucion_pedida(object, object)`` con el ``Desajuste`` y el valor elegido
    (``str``), o ``None`` para «Pasar a Automático» en un nodo. Métodos:
    ``establecer_desajustes(desajustes)`` (vacío oculta el panel), ``desajustes()`` y
    ``cantidad``. El panel no modifica el lote ni crea ninguna petición a Proxmox.
    """

    sustitucion_pedida = Signal(object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PanelLoteNoEncaja")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAccessibleName(self.tr("Este lote no encaja en este servidor"))
        self._desajustes: tuple[Desajuste, ...] = ()
        self._numeros: tuple[int | None, ...] = ()
        self.botones_usar_otro: list[QPushButton] = []
        self.botones_automatico: list[QPushButton] = []
        self._capa = QVBoxLayout(self)
        self.titulo = QLabel(self.tr("Este lote no encaja en este servidor"))
        fuente = self.titulo.font()
        fuente.setBold(True)
        self.titulo.setFont(fuente)
        self.titulo.setProperty("aviso", True)
        self.explicacion = etiqueta(
            self.tr(
                "Algunos valores guardados en el lote no existen aquí. Elige otros para poder "
                "continuar: ProxLaunch no cambia nada por su cuenta."
            ),
            secundario=True,
        )
        self._capa.addWidget(self.titulo)
        self._capa.addWidget(self.explicacion)
        self._zona = QVBoxLayout()
        self._capa.addLayout(self._zona)
        self.hide()

    # --- API ---------------------------------------------------------------------------

    @property
    def cantidad(self) -> int:
        return len(self._desajustes)

    def desajustes(self) -> tuple[Desajuste, ...]:
        return self._desajustes

    def establecer_desajustes(
        self, desajustes: Sequence[Desajuste], numeros: Sequence[int | None] = ()
    ) -> None:
        """Reconstruye los renglones. Sin desajustes el panel se oculta.

        ``numeros``: número de origen de cada fila (el que muestra la tabla); si falta
        para una posición se usa la posición + 1.
        """
        self._desajustes = tuple(desajustes)
        self._numeros = tuple(numeros)
        self.botones_usar_otro = []
        self.botones_automatico = []
        while self._zona.count():
            item = self._zona.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for d in self._desajustes:
            self._zona.addWidget(self._renglon(d))
        self.setVisible(bool(self._desajustes))

    # --- Textos ------------------------------------------------------------------------

    def texto_desajuste(self, d: Desajuste) -> str:
        """Descripción llana del valor que no existe (única fuente: ``textos``)."""
        return texto_desajuste(d)

    def _numero_fila(self, posicion: int) -> str:
        """Número con el que la tabla nombra la fila: su origen o su posición (1..N)."""
        origen = self._numeros[posicion] if 0 <= posicion < len(self._numeros) else None
        return str(origen if origen is not None else posicion + 1)

    def texto_afectadas(self, d: Desajuste) -> str:
        """«Afecta a 3 máquinas (n.º 2, 5, 7)». Vacío en un lote homogéneo."""
        if not d.indices:
            return ""
        numeros = [self._numero_fila(i) for i in d.indices[:MAX_AFECTADAS_VISIBLES]]
        resto = len(d.indices) - len(numeros)
        lista = ", ".join(numeros) + (f" +{resto}" if resto > 0 else "")
        n = len(d.indices)
        cuantas = (
            self.tr("Afecta a 1 máquina") if n == 1 else self.tr("Afecta a %n máquinas", None, n)
        )
        return f"{cuantas} " + self.tr("(n.º {lista}).").format(lista=lista)

    def _titulo_eleccion(self, d: Desajuste) -> tuple[str, str]:
        """(título, pregunta) del selector de alternativa."""
        titulo = self.tr("Usar otro valor")
        if d.tipo in (TipoDesajuste.STORAGE, TipoDesajuste.STORAGE_EFI):
            return titulo, self.tr("Almacenamiento que reemplaza a «{valor}»:").format(
                valor=d.valor
            )
        if d.tipo == TipoDesajuste.BRIDGE:
            return titulo, self.tr("Red que reemplaza a «{valor}»:").format(valor=d.valor)
        return titulo, self.tr("Nodo que reemplaza a «{valor}»:").format(valor=d.valor)

    # --- Renglones -----------------------------------------------------------------------

    def _renglon(self, d: Desajuste) -> QWidget:
        marco = QWidget()
        capa = QVBoxLayout(marco)
        capa.setContentsMargins(0, 4, 0, 4)
        texto = self.texto_desajuste(d)
        afectadas = self.texto_afectadas(d)
        capa.addWidget(etiqueta("✖ " + texto))
        if afectadas:
            capa.addWidget(etiqueta(afectadas, secundario=True))
        fila = QHBoxLayout()
        usar = QPushButton(self.tr("Usar otro…"))
        usar.setAccessibleName(self.tr("Usar otro en lugar de «{valor}»").format(valor=d.valor))
        usar.setEnabled(bool(d.disponibles))
        if d.disponibles:
            usar.setToolTip(
                self.tr("Disponibles en este servidor: {lista}").format(
                    lista=", ".join(d.disponibles)
                )
            )
        else:
            usar.setToolTip(self.tr("Este servidor no tiene ninguna alternativa."))
        usar.clicked.connect(lambda _c=False, desajuste=d: self._pedir_otro(desajuste))
        self.botones_usar_otro.append(usar)
        fila.addWidget(usar)
        if d.tipo == TipoDesajuste.NODO:
            auto = QPushButton(self.tr("Pasar a Automático"))
            auto.setAccessibleName(
                self.tr("Pasar a Automático en lugar del nodo «{valor}»").format(valor=d.valor)
            )
            auto.clicked.connect(
                lambda _c=False, desajuste=d: self.sustitucion_pedida.emit(desajuste, None)
            )
            self.botones_automatico.append(auto)
            fila.addWidget(auto)
        fila.addStretch(1)
        capa.addLayout(fila)
        return marco

    def elegir_alternativa(self, d: Desajuste) -> str | None:
        """Pregunta cuál de los valores disponibles usar (``None`` si se cancela).

        Es un método para poder sustituirlo en pruebas sin abrir un diálogo modal.
        """
        titulo, pregunta = self._titulo_eleccion(d)
        elegido, aceptado = QInputDialog.getItem(
            self, titulo, pregunta, list(d.disponibles), 0, False
        )
        return elegido if aceptado and elegido else None

    def _pedir_otro(self, d: Desajuste) -> None:
        nuevo = self.elegir_alternativa(d)
        if nuevo is not None:
            self.sustitucion_pedida.emit(d, nuevo)
