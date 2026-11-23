"""«Qué puedo hacer en este servidor»: capacidades, permisos y texto para el administrador.

Muestra el estado de cada vía (RF-O02) con símbolo y texto —nunca solo color— y el motivo escrito
de lo que no está disponible (versión, permiso, almacenamiento). Debajo, un texto copiable para
pedirle al administrador lo que falta (RF-O32, CA-O32.2). La aplicación nunca ofrece activar nada
por su cuenta (INV-O4).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from proxlaunch.interfaz.ayuda import texto_pedir_al_administrador
from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.modelos_tabla_origen import (
    simbolo_disponibilidad,
    texto_explicacion_via,
)
from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.interfaz.textos import texto_disponibilidad, texto_via
from proxlaunch.interfaz.textos_c import (
    VIAS_FASE_C,
    texto_estado_fila_c,
    texto_explicacion_fila_c,
)
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.origen.capacidades_origen import (
    CapacidadesOrigen,
    Disponibilidad,
    Via,
)

# Orden en que se presentan las vías.
_ORDEN_VIAS: tuple[Via, ...] = (
    Via.ISO,
    Via.SUBIR_ISO,
    Via.DESCARGAR_URL,
    Via.IMPORTAR,
    Via.SUBIR_IMAGEN,
    Via.DESCARGAR_IMAGEN,
    Via.CLONAR,
    Via.ORDEN_ARRANQUE,
    Via.AMPLIAR_DISCO,
    # Fase C (0.8): lotes en el servidor, redes virtuales, firewall y red de las copias.
    *VIAS_FASE_C,
)
_TOKEN_DISPONIBILIDAD = {
    Disponibilidad.SI: "exito",
    Disponibilidad.CON_AVISO: "aviso",
    Disponibilidad.NO: "error",
}


def texto_faltante_para_administrador(caps: CapacidadesOrigen) -> str:
    """Lista, una por línea, de lo que no está disponible y por qué; ``""`` si todo lo está.

    Pensado para pegarlo en un mensaje al administrador: cada línea nombra la función y el
    motivo (permiso con su ruta, versión o almacenamiento con la ruta de Proxmox).
    """
    lineas: list[str] = []
    for via in _ORDEN_VIAS:
        estado = caps.vias.get(via)
        if estado is None or estado.disponibilidad != Disponibilidad.NO:
            continue
        explicacion = (
            texto_explicacion_fila_c(via, estado) if via in VIAS_FASE_C else ""
        ) or texto_explicacion_via(estado)
        lineas.append(f"- {texto_via(via)}: {explicacion}")
    return "\n".join(lineas)


class DialogoCapacidades(QDialog):
    """Tabla de vías con su estado y el texto copiable para el administrador.

    ``texto_administrador`` es el texto general «Qué pedirle a tu administrador» (los 14
    privilegios, la activación de «Import» y la creación de plantillas); lo aporta quien abre el
    diálogo (``textos``). Se le antepone la lista de lo que falta hoy en este servidor.
    """

    COL_VIA = 0
    COL_ESTADO = 1
    COL_MOTIVO = 2

    def __init__(
        self,
        capacidades: CapacidadesOrigen | None,
        parent: QWidget | None = None,
        *,
        texto_administrador: str | None = None,
        tema: str = "oscuro",
        caps: Capacidades | None = None,
    ) -> None:
        super().__init__(parent)
        self._capacidades = capacidades
        self._texto_general = (
            texto_pedir_al_administrador(caps)
            if texto_administrador is None
            else texto_administrador
        )
        self._tokens = TOKENS_CLARO if tema == "claro" else TOKENS_OSCURO
        self.setWindowTitle(self.tr("Qué puedo hacer en este servidor"))
        self.setModal(True)
        self.setMinimumSize(1000, 640)

        self.etiqueta_version = QLabel()
        self.etiqueta_version.setTextFormat(Qt.TextFormat.PlainText)
        self.etiqueta_version.setAccessibleName(self.tr("Versión de Proxmox"))
        self.etiqueta_version.setWordWrap(True)

        self.tabla = QTableWidget(0, 3)
        self.tabla.setHorizontalHeaderLabels(
            [self.tr("Qué quieres hacer"), self.tr("Estado"), self.tr("Por qué")]
        )
        self.tabla.setAccessibleName(self.tr("Funciones disponibles en este servidor"))
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setWordWrap(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(self.COL_VIA, QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(self.COL_ESTADO, QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(self.COL_MOTIVO, QHeaderView.ResizeMode.Stretch)

        titulo_admin = QLabel(self.tr("Qué pedirle a tu administrador"))
        fuente = titulo_admin.font()
        fuente.setBold(True)
        titulo_admin.setFont(fuente)
        self.texto_admin = QPlainTextEdit()
        self.texto_admin.setReadOnly(True)
        self.texto_admin.setAccessibleName(self.tr("Texto para el administrador"))
        self.texto_admin.setMinimumHeight(110)

        self.boton_copiar = QPushButton(self.tr("Copiar texto para el administrador"))
        self.boton_copiar.setAutoDefault(False)
        self.boton_copiar.clicked.connect(self.copiar_texto_administrador)
        self.boton_cerrar = QPushButton(self.tr("Cerrar"))
        self.boton_cerrar.setDefault(True)
        self.boton_cerrar.clicked.connect(self.accept)

        capa, capa_pie, _ = hacer_desplazable(self)
        capa.addWidget(self.etiqueta_version)
        capa.addWidget(self.tabla, 1)
        capa.addWidget(titulo_admin)
        capa.addWidget(self.texto_admin)
        fila = QHBoxLayout()
        fila.addWidget(self.boton_copiar)
        fila.addStretch(1)
        fila.addWidget(self.boton_cerrar)
        capa_pie.addLayout(fila)

        self.establecer_capacidades(capacidades)

    # --- API pública --------------------------------------------------------------------

    def establecer_capacidades(self, capacidades: CapacidadesOrigen | None) -> None:
        """Muestra las capacidades (``None`` = aún no calculadas)."""
        self._capacidades = capacidades
        self.tabla.setRowCount(0)
        if capacidades is None:
            self.etiqueta_version.setText(
                self.tr("Todavía no se conocen las capacidades: conéctate a un servidor.")
            )
            self.texto_admin.setPlainText(self._texto_general)
            self.boton_copiar.setEnabled(bool(self._texto_general))
            return
        self.etiqueta_version.setText(self._texto_version(capacidades))
        vias = [v for v in _ORDEN_VIAS if v in capacidades.vias]
        self.tabla.setRowCount(len(vias))
        for fila, via in enumerate(vias):
            self._poner_fila(fila, capacidades, via)
        self.texto_admin.setPlainText(self.texto_para_administrador())
        self.boton_copiar.setEnabled(True)

    def texto_para_administrador(self) -> str:
        """Texto copiable: lo que falta hoy en este servidor y, debajo, el texto general."""
        partes: list[str] = []
        if self._capacidades is not None:
            faltante = texto_faltante_para_administrador(self._capacidades)
            if faltante:
                partes.append(self.tr("En este servidor no puedo hacer lo siguiente:"))
                partes.append(faltante)
        if self._texto_general:
            if partes:
                partes.append("")
            partes.append(self._texto_general)
        if not partes:
            return self.tr("No hace falta pedir nada: todas las funciones están disponibles.")
        return "\n".join(partes)

    def copiar_texto_administrador(self) -> None:
        """Copia el texto para el administrador al portapapeles."""
        QGuiApplication.clipboard().setText(self.texto_para_administrador())

    # --- Internos -----------------------------------------------------------------------

    def _texto_version(self, caps: CapacidadesOrigen) -> str:
        version = f"{caps.version[0]}.{caps.version[1]}"
        texto = self.tr("Proxmox VE {version}").format(version=version)
        if caps.forzada:
            texto += " " + self.tr("(versión forzada)")
        if caps.nodo:
            texto += " · " + self.tr("nodo {nodo}").format(nodo=caps.nodo)
        return texto

    def _poner_fila(self, fila: int, caps: CapacidadesOrigen, via: Via) -> None:
        estado = caps.vias[via]
        disp = estado.disponibilidad
        simbolo = simbolo_disponibilidad(disp)
        es_c = via in VIAS_FASE_C
        # Las filas de la fase C dicen «Sí», «No» o «No se pudo comprobar» (RF-C5.2).
        texto_estado = texto_estado_fila_c(estado) if es_c else texto_disponibilidad(disp)
        if es_c and estado.codigo is not None and disp == Disponibilidad.CON_AVISO:
            simbolo = simbolo_disponibilidad(Disponibilidad.NO)
        item_estado = QTableWidgetItem(f"{simbolo} {texto_estado}")
        item_estado.setForeground(QColor(self._tokens[_TOKEN_DISPONIBILIDAD[disp]]))
        motivo = (texto_explicacion_fila_c(via, estado) if es_c else "") or texto_explicacion_via(
            estado
        )
        item_via = QTableWidgetItem(texto_via(via))
        item_motivo = QTableWidgetItem(motivo)
        accesible = f"{texto_via(via)}: {texto_estado}"
        if motivo:
            accesible += f". {motivo}"
        for item in (item_via, item_estado, item_motivo):
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, accesible)
            if motivo:
                item.setToolTip(motivo)
        self.tabla.setItem(fila, self.COL_VIA, item_via)
        self.tabla.setItem(fila, self.COL_ESTADO, item_estado)
        self.tabla.setItem(fila, self.COL_MOTIVO, item_motivo)
