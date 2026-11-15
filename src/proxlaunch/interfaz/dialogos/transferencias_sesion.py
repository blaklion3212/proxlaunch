"""«Archivos subidos en esta sesión»: lista copiable o guardable en .txt (RF-O25, CA-O25.3).

Las subidas no se pueden deshacer desde ProxLaunch (hace falta un permiso de administrador), así
que esta lista sirve para pedirle al administrador que borre lo que sobre. El registro vive solo
en memoria: nada se guarda si el usuario no lo pide, y nunca contiene URL, ruta local ni huella.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.modelos_tabla_origen import formatear_bytes
from proxlaunch.interfaz.textos import (
    texto_error,
    texto_estado_transferencia,
    texto_registro_transferencia,
    texto_tipo_transferencia,
)
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.archivos.escritura import escribir_atomico
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.transferencias.modelos import RegistroTransferencia
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion


def texto_registros(registros: Sequence[RegistroTransferencia]) -> str:
    """Texto plano de los registros, una línea por archivo, para copiar o guardar.

    Incluye el identificador del volumen (``storage:iso/archivo``) porque es lo que el
    administrador necesita para borrarlo. No contiene URL, ruta local ni huella (INV-O6).
    """
    if not registros:
        return QCoreApplication.translate(
            "DialogoTransferenciasSesion",
            "En esta sesión no se ha subido ni descargado ningún archivo.",
        )
    lineas = [
        QCoreApplication.translate(
            "DialogoTransferenciasSesion",
            "Archivos subidos o descargados en esta sesión de ProxLaunch:",
        )
    ]
    for r in registros:
        linea = texto_registro_transferencia(r)
        if r.volid:
            linea += f" · {r.volid}"
        lineas.append(f"- {linea}")
    return "\n".join(lineas)


class DialogoTransferenciasSesion(QDialog):
    """Tabla con los archivos transferidos en la sesión y botones para copiar o guardar.

    ``lanzador`` (opcional) escribe el .txt fuera del hilo de la interfaz; sin él se escribe en
    el acto (útil en pruebas).
    """

    COL_HORA = 0
    COL_TIPO = 1
    COL_ARCHIVO = 2
    COL_STORAGE = 3
    COL_NODO = 4
    COL_TAMANO = 5
    COL_ESTADO = 6

    def __init__(
        self,
        registro: RegistroSesion,
        parent: QWidget | None = None,
        *,
        lanzador: Lanzador | None = None,
    ) -> None:
        super().__init__(parent)
        self._registro = registro
        self._lanzador = lanzador
        self.setWindowTitle(self.tr("Archivos subidos en esta sesión"))
        self.setModal(True)
        self.setMinimumSize(760, 400)

        aviso = QLabel(
            self.tr(
                "Estos archivos quedan en el servidor hasta que un administrador los borre: "
                "ProxLaunch no puede borrarlos. La lista solo existe mientras la aplicación "
                "está abierta y no se guarda sola."
            )
        )
        aviso.setWordWrap(True)
        aviso.setProperty("secundario", True)

        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels(
            [
                self.tr("Hora"),
                self.tr("Tipo"),
                self.tr("Archivo"),
                self.tr("Almacenamiento"),
                self.tr("Nodo"),
                self.tr("Tamaño"),
                self.tr("Estado"),
            ]
        )
        self.tabla.setAccessibleName(self.tr("Archivos transferidos en esta sesión"))
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setStretchLastSection(True)

        self.etiqueta_vacia = QLabel(
            self.tr("En esta sesión no se ha subido ni descargado ningún archivo.")
        )
        self.etiqueta_vacia.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.etiqueta_vacia.setProperty("secundario", True)

        self.boton_copiar = QPushButton(self.tr("Copiar lista"))
        self.boton_copiar.setAutoDefault(False)
        self.boton_copiar.clicked.connect(self.copiar)
        self.boton_guardar = QPushButton(self.tr("Guardar como .txt…"))
        self.boton_guardar.setAutoDefault(False)
        self.boton_guardar.clicked.connect(self._guardar)
        self.boton_cerrar = QPushButton(self.tr("Cerrar"))
        self.boton_cerrar.setDefault(True)
        self.boton_cerrar.clicked.connect(self.accept)

        capa, capa_pie, _ = hacer_desplazable(self)
        capa.addWidget(aviso)
        capa.addWidget(self.tabla, 1)
        capa.addWidget(self.etiqueta_vacia)
        fila = QHBoxLayout()
        fila.addWidget(self.boton_copiar)
        fila.addWidget(self.boton_guardar)
        fila.addStretch(1)
        fila.addWidget(self.boton_cerrar)
        capa_pie.addLayout(fila)
        self.actualizar()

    # --- API pública --------------------------------------------------------------------

    def actualizar(self) -> None:
        """Vuelve a leer el registro de la sesión (llamar tras cada transferencia)."""
        registros = self._registro.lista()
        self.tabla.setRowCount(len(registros))
        for fila, r in enumerate(registros):
            valores = (
                r.hora_local,
                texto_tipo_transferencia(r.tipo),
                r.nombre_archivo,
                r.storage,
                r.nodo,
                formatear_bytes(r.tamano_bytes),
                texto_estado_transferencia(r.estado),
            )
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if r.volid:
                    item.setToolTip(r.volid)
                if col == self.COL_TAMANO:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.tabla.setItem(fila, col, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setStretchLastSection(True)
        hay = bool(registros)
        self.tabla.setVisible(hay)
        self.etiqueta_vacia.setVisible(not hay)
        self.boton_copiar.setEnabled(hay)
        self.boton_guardar.setEnabled(hay)

    def texto(self) -> str:
        """El mismo texto que se copia y se guarda."""
        return texto_registros(self._registro.lista())

    def copiar(self) -> None:
        """Copia la lista al portapapeles."""
        QGuiApplication.clipboard().setText(self.texto())

    def guardar_en(self, ruta: Path) -> None:
        """Escribe la lista en ``ruta`` (atómico, en un hilo si hay lanzador)."""
        datos = (self.texto() + "\n").encode("utf-8")
        if self._lanzador is None:
            escribir_atomico(ruta, datos)
            return
        self._lanzador.lanzar(escribir_atomico, ruta, datos, al_fallar=self._al_fallar_escritura)

    # --- Internos -----------------------------------------------------------------------

    def _guardar(self) -> None:
        ruta, _filtro = QFileDialog.getSaveFileName(
            self,
            self.tr("Guardar la lista de archivos"),
            "archivos-transferidos.txt",
            self.tr("Texto (*.txt)"),
        )
        if not ruta:
            return
        try:
            self.guardar_en(Path(ruta))
        except ErrorProxLaunch as error:
            self._al_fallar_escritura(error)

    def _al_fallar_escritura(self, error: ErrorProxLaunch) -> None:
        caja = QMessageBox(
            QMessageBox.Icon.Warning,
            self.tr("No se pudo guardar"),
            texto_error(error),
            parent=self,
        )
        caja.setTextFormat(Qt.TextFormat.PlainText)
        caja.exec()
