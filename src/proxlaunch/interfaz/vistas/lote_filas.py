"""Panel del lote por filas (D-22, RF-C01 CA-C01.3, docs/arquitectura/mvp3.md §6.6 paso 7).

Sustituye al formulario mientras hay un lote cargado desde un CSV o un archivo de lote por filas:
una tabla de solo lectura con cada máquina y su configuración. No se edita fila por fila
(CA-G07.3): para cambiar algo se corrige el archivo y se importa de nuevo, o se quitan filas.
Cargar o importar NUNCA habilita «Crear»: solo «Ver resumen», que ejecuta el planificador y
exige la confirmación habitual (INV-M6).
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from proxlaunch.interfaz.modelos_tabla import ModeloFilasLote, TablaCopiable
from proxlaunch.interfaz.vistas.campos import boton_ayuda, etiqueta, mensaje, poner_mensaje
from proxlaunch.nucleo.lote.modelos import DefinicionLote


def texto_titulo_filas(n: int, origen: str | None, *, desde_archivo: bool) -> str:
    """«12 máquinas desde el archivo «x.csv»» / «3 máquinas del lote «web»» (CA-C01.3)."""
    nombre = origen or ""
    if desde_archivo:
        if n == 1:
            return QCoreApplication.translate(
                "PanelLoteFilas", "1 máquina desde el archivo «{origen}»"
            ).format(origen=nombre)
        return QCoreApplication.translate(
            "PanelLoteFilas", "%n máquinas desde el archivo «{origen}»", None, n
        ).format(origen=nombre)
    if n == 1:
        return QCoreApplication.translate("PanelLoteFilas", "1 máquina del lote «{origen}»").format(
            origen=nombre
        )
    return QCoreApplication.translate(
        "PanelLoteFilas", "%n máquinas del lote «{origen}»", None, n
    ).format(origen=nombre)


class PanelLoteFilas(QWidget):
    """Tabla de solo lectura del lote por filas y sus acciones."""

    resumen_solicitado = Signal()  # «Ver resumen»
    revisar_solicitado = Signal()  # «Revisar filas…» (reabre la vista previa del CSV)
    guardar_solicitado = Signal()  # «Guardar lote…»
    salir_solicitado = Signal()  # «Salir del lote por filas»
    quitar_solicitado = Signal(object)  # tuple[int, ...] con las posiciones a quitar

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._definicion: DefinicionLote | None = None
        self._bloqueado = False
        self._bloqueo_resumen: str | None = None

        self._titulo = QLabel()
        fuente = self._titulo.font()
        fuente.setPointSize(fuente.pointSize() + 3)
        fuente.setBold(True)
        self._titulo.setFont(fuente)
        self._titulo.setTextFormat(Qt.TextFormat.PlainText)
        self._titulo.setWordWrap(True)
        self._titulo.setAccessibleName(
            QCoreApplication.translate("PanelLoteFilas", "Título del lote por filas")
        )
        self._nota = etiqueta(
            QCoreApplication.translate(
                "PanelLoteFilas",
                "Cada máquina trae su propia configuración. Para cambiar algo, corrige el "
                "archivo e impórtalo de nuevo, o quita las filas que no quieras.",
            ),
            secundario=True,
        )
        self._ayuda = boton_ayuda("lote_por_filas")
        self._problemas = mensaje(error=True)
        self._problemas.setAccessibleName(
            QCoreApplication.translate("PanelLoteFilas", "Problemas de las filas")
        )

        self.modelo = ModeloFilasLote(self)
        self.tabla = TablaCopiable(
            QCoreApplication.translate("PanelLoteFilas", "Máquinas del lote por filas")
        )
        self.tabla.setModel(self.modelo)
        self.tabla.setMinimumHeight(220)
        self.tabla.selectionModel().selectionChanged.connect(lambda *_a: self._refrescar_botones())

        self.boton_resumen = QPushButton(
            QCoreApplication.translate("PanelLoteFilas", "Ver resumen")
        )
        self.boton_resumen.setProperty("primario", True)
        self.boton_resumen.setAccessibleName(
            QCoreApplication.translate("PanelLoteFilas", "Ver el resumen del lote")
        )
        self.boton_revisar = QPushButton(
            QCoreApplication.translate("PanelLoteFilas", "Revisar filas…")
        )
        self.boton_revisar.setAccessibleName(
            QCoreApplication.translate("PanelLoteFilas", "Revisar las filas del archivo")
        )
        self.boton_guardar = QPushButton(
            QCoreApplication.translate("PanelLoteFilas", "Guardar lote…")
        )
        self.boton_guardar.setAccessibleName(
            QCoreApplication.translate("PanelLoteFilas", "Guardar el lote en un archivo")
        )
        self.boton_quitar = QPushButton(
            QCoreApplication.translate("PanelLoteFilas", "Quitar las filas seleccionadas")
        )
        self.boton_quitar.setAccessibleName(
            QCoreApplication.translate("PanelLoteFilas", "Quitar las filas seleccionadas del lote")
        )
        self.boton_salir = QPushButton(
            QCoreApplication.translate("PanelLoteFilas", "Salir del lote por filas")
        )
        self.boton_salir.setAccessibleName(
            QCoreApplication.translate("PanelLoteFilas", "Salir del lote por filas")
        )
        self.boton_resumen.clicked.connect(self.resumen_solicitado)
        self.boton_revisar.clicked.connect(self.revisar_solicitado)
        self.boton_guardar.clicked.connect(self.guardar_solicitado)
        self.boton_quitar.clicked.connect(self._al_quitar)
        self.boton_salir.clicked.connect(self.salir_solicitado)
        self.boton_revisar.hide()

        cabecera = QHBoxLayout()
        cabecera.addWidget(self._titulo, 1)
        cabecera.addWidget(self._ayuda, 0, Qt.AlignmentFlag.AlignTop)
        principal = QHBoxLayout()
        principal.addStretch(1)
        principal.addWidget(self.boton_resumen)
        botones = QHBoxLayout()
        botones.addWidget(self.boton_salir)
        botones.addWidget(self.boton_quitar)
        botones.addWidget(self.boton_revisar)
        botones.addWidget(self.boton_guardar)
        botones.addStretch(1)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addLayout(cabecera)
        capa.addWidget(self._nota)
        capa.addWidget(self._problemas)
        capa.addWidget(self.tabla, 1)
        capa.addLayout(principal)
        capa.addLayout(botones)
        self._refrescar_botones()

    # --- API ----------------------------------------------------------------------------

    def establecer(
        self,
        definicion: DefinicionLote,
        *,
        origen: str | None,
        desde_archivo: bool,
        puede_revisar: bool = False,
    ) -> None:
        """Muestra las filas de ``definicion``. ``origen`` es el nombre del archivo o del lote.

        ``puede_revisar`` muestra «Revisar filas…» (solo si hay un CSV que reabrir).
        """
        self._definicion = definicion
        self.modelo.establecer_filas(definicion.filas)
        self._titulo.setText(
            texto_titulo_filas(len(definicion.filas), origen, desde_archivo=desde_archivo)
        )
        self.boton_revisar.setVisible(puede_revisar)
        self._refrescar_botones()

    def actualizar_filas(self, definicion: DefinicionLote, titulo: str) -> None:
        """Sustituye las filas (p. ej. tras quitar algunas) conservando el modo."""
        self._definicion = definicion
        self.modelo.establecer_filas(definicion.filas)
        self._titulo.setText(titulo)
        self._refrescar_botones()

    @property
    def definicion(self) -> DefinicionLote | None:
        return self._definicion

    @property
    def titulo(self) -> str:
        return self._titulo.text()

    def mostrar_problemas(self, textos: Sequence[str]) -> None:
        """Errores de capa 1 de las filas (V-M10, V-02…), uno por línea."""
        poner_mensaje(self._problemas, "\n".join(f"✕ {t}" for t in textos))

    def establecer_bloqueo_resumen(self, motivo: str | None) -> None:
        """Con errores de capa 1 en las filas «Ver resumen» no se puede pulsar."""
        self._bloqueo_resumen = motivo
        self._refrescar_botones()

    def bloquear(self, bloqueado: bool) -> None:
        """Con el lote en ejecución no se puede cambiar nada."""
        self._bloqueado = bloqueado
        self._refrescar_botones()

    def filas_seleccionadas(self) -> tuple[int, ...]:
        return tuple(sorted({i.row() for i in self.tabla.selectionModel().selectedRows()}))

    # --- Internos -----------------------------------------------------------------------

    def _refrescar_botones(self) -> None:
        n = len(self._definicion.filas) if self._definicion is not None else 0
        seleccion = self.filas_seleccionadas()
        libre = not self._bloqueado
        self.boton_resumen.setEnabled(libre and n > 0 and not self._bloqueo_resumen)
        self.boton_resumen.setToolTip(self._bloqueo_resumen or "")
        self.boton_guardar.setEnabled(n > 0)
        self.boton_revisar.setEnabled(libre)
        self.boton_salir.setEnabled(libre)
        # No se puede quitar todo: para eso está «Salir del lote por filas».
        self.boton_quitar.setEnabled(libre and 0 < len(seleccion) < n)

    def _al_quitar(self) -> None:
        seleccion = self.filas_seleccionadas()
        if seleccion and not self._bloqueado:
            self.quitar_solicitado.emit(seleccion)
