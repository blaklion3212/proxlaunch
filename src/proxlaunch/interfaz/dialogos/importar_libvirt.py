"""Asistente «Importar desde libvirt»: elegir el XML, ver la vista previa y rellenar el formulario.

El diálogo solo MUESTRA: no cambia el formulario ni envía nada al servidor (CA-D1.6.3). No lee el
archivo ni calcula la propuesta él mismo: lo pide con señales y recibe el resultado con
``establecer_resultado`` y ``establecer_propuesta`` (quien lo abre lo hace en un trabajador,
RNF-D6). Nada del XML se guarda; las contraseñas (``passwd``) nunca se leen (V-D39).

Flujo: ``elegir_archivo`` → ``pide_lectura(Path)`` → ``establecer_resultado(dominio, error)`` →
``pide_propuesta(dominio, conservar_mac, nodo)`` → ``establecer_propuesta(propuesta)``. Cambiar
el servidor de destino o la casilla de la MAC vuelve a pedir la propuesta (CA-D1.6.6). «Rellenar el
formulario» queda deshabilitado mientras haya una fila «Bloquea» (V-D35 no bloquea, CA-D1.11.2) y
deja en ``propuesta_aceptada`` lo que debe aplicar quien abrió el diálogo.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.archivos_ui import boton_ayuda_texto
from proxlaunch.interfaz.ayuda import ayuda
from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.modelos_tabla import TablaCopiable
from proxlaunch.interfaz.textos import texto_error, texto_problema, tooltip_plano
from proxlaunch.interfaz.textos_d import (
    texto_comandos_obtener_xml,
    texto_concepto_fila,
    texto_estado_fila_simbolo,
    texto_nodo_con_arquitectura,
    texto_nombre_opcion_d,
    texto_problema_d,
)
from proxlaunch.interfaz.vistas.campos import etiqueta, mensaje, poner_mensaje
from proxlaunch.nucleo.arquitectura.modelos import arquitectura_efectiva
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.libvirt.correspondencias import EstadoFila, PropuestaLibvirt
from proxlaunch.nucleo.libvirt.modelos import DominioLibvirt
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.validacion import Problema, Severidad

# Columnas de la vista previa (RF-D1.6): «Concepto · En libvirt · En Proxmox · Estado».
_COLUMNAS = 4


class DialogoImportarLibvirt(QDialog):
    """Vista previa accesible de una máquina de libvirt antes de rellenar el formulario.

    Args:
        parent: ventana que lo abre.
        inv: inventario de la conexión (nombra la arquitectura de cada servidor); puede ser
            ``None`` y entonces los servidores salen sin su arquitectura.
        nodos: servidores de destino posibles (los del formulario o, si no hay elegidos, todos).
        nodo: el servidor que se propone al abrir (el del formulario); si no está en ``nodos``,
            el primero.
        cantidad: copias que se crearán; la MAC de origen solo se puede conservar con una (V-D33).
        formulario_modificado: si el formulario ya tiene datos del usuario, «Rellenar» pide
            confirmar que se reemplazarán (RF-D1.6).
    """

    pide_lectura = Signal(object)  # Path del XML elegido -> un trabajador lo lee
    pide_propuesta = Signal(object, bool, str)  # (DominioLibvirt, conservar_mac, nodo)

    def __init__(
        self,
        parent: QWidget | None,
        *,
        inv: Inventario | None = None,
        nodos: Sequence[str] = (),
        nodo: str | None = None,
        cantidad: int = 1,
        formulario_modificado: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Importar desde libvirt"))
        self.setModal(True)
        self.resize(900, 640)
        self._inv = inv
        self._nodos = tuple(nodos)
        self._cantidad = cantidad
        self._formulario_modificado = formulario_modificado
        self._dominio: DominioLibvirt | None = None
        self._propuesta: PropuestaLibvirt | None = None
        self._leyendo = False
        self.propuesta_aceptada: PropuestaLibvirt | None = None
        # La pregunta de reemplazo se puede sustituir (pruebas) sin abrir una caja modal.
        self.confirmar_reemplazo: Callable[[], bool] = self._confirmar_reemplazo_por_defecto
        self._construir(nodo)
        self._actualizar_boton()

    # --- Construcción --------------------------------------------------------------------

    def _construir(self, nodo: str | None) -> None:
        capa, capa_pie, _ = hacer_desplazable(self)
        capa.addWidget(
            etiqueta(
                self.tr(
                    "Elige el archivo XML de una máquina de libvirt (la que genera «virsh "
                    "dumpxml»). Aquí solo se revisa: el formulario no cambia hasta que pulses "
                    "«Rellenar el formulario». Nada del archivo se guarda."
                ),
                secundario=True,
            )
        )

        # Archivo y ayuda.
        fila_archivo = QHBoxLayout()
        self.etiqueta_archivo = QLabel(self.tr("Todavía no elegiste un archivo."))
        self.etiqueta_archivo.setAccessibleName(self.tr("Archivo XML elegido"))
        self.etiqueta_archivo.setTextFormat(Qt.TextFormat.PlainText)
        self.boton_elegir = QPushButton(self.tr("Elegir archivo XML…"))
        self.boton_elegir.setAutoDefault(False)
        self.boton_como_obtener = QPushButton(self.tr("Cómo obtener el XML"))
        self.boton_como_obtener.setFlat(True)
        self.boton_como_obtener.setCheckable(True)
        self.boton_como_obtener.setProperty("enlace", True)
        self.boton_como_obtener.setAutoDefault(False)
        fila_archivo.addWidget(self.etiqueta_archivo, 1)
        fila_archivo.addWidget(self.boton_elegir)
        fila_archivo.addWidget(self.boton_como_obtener)
        fila_archivo.addWidget(boton_ayuda_texto(ayuda("libvirt_xml")))
        capa.addLayout(fila_archivo)

        # Las cuatro órdenes de RF-D1.14, copiables.
        self.texto_ayuda_xml = QPlainTextEdit()
        self.texto_ayuda_xml.setReadOnly(True)
        self.texto_ayuda_xml.setAccessibleName(self.tr("Órdenes para obtener y revisar el XML"))
        self.texto_ayuda_xml.setPlainText(
            "\n\n".join(
                f"{orden}\n    {para_que}" for orden, para_que in texto_comandos_obtener_xml()
            )
        )
        self.texto_ayuda_xml.setMaximumHeight(170)
        self.texto_ayuda_xml.hide()
        capa.addWidget(self.texto_ayuda_xml)
        # Un botón «Copiar» por orden (CA-D1.13.4): solo copia al portapapeles, no ejecuta nada.
        self.panel_copiar_ordenes = QWidget()
        capa_copiar = QVBoxLayout(self.panel_copiar_ordenes)
        capa_copiar.setContentsMargins(0, 0, 0, 0)
        for orden, _para_que in texto_comandos_obtener_xml():
            fila_orden = QHBoxLayout()
            texto_orden = QLabel(orden)
            texto_orden.setTextFormat(Qt.TextFormat.PlainText)
            texto_orden.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            boton_copiar = QPushButton(self.tr("Copiar"))
            boton_copiar.setAutoDefault(False)
            boton_copiar.setAccessibleName(self.tr("Copiar la orden: {orden}").format(orden=orden))
            boton_copiar.clicked.connect(lambda _=False, o=orden: self._copiar_orden(o))
            fila_orden.addWidget(texto_orden, 1)
            fila_orden.addWidget(boton_copiar)
            capa_copiar.addLayout(fila_orden)
        self.panel_copiar_ordenes.hide()
        capa.addWidget(self.panel_copiar_ordenes)

        # Servidor de destino y MAC.
        fila_destino = QHBoxLayout()
        self.combo_nodo = QComboBox()
        self.combo_nodo.setAccessibleName(self.tr("Servidor de destino"))
        for n in self._nodos:
            self.combo_nodo.addItem(self._texto_nodo(n), n)
        if nodo is not None and self.combo_nodo.findData(nodo) >= 0:
            self.combo_nodo.setCurrentIndex(self.combo_nodo.findData(nodo))
        etiqueta_nodo = QLabel(self.tr("Servidor de destino:"))
        etiqueta_nodo.setBuddy(self.combo_nodo)
        fila_destino.addWidget(etiqueta_nodo)
        fila_destino.addWidget(self.combo_nodo, 1)
        capa.addLayout(fila_destino)
        self.combo_nodo.setVisible(bool(self._nodos))
        etiqueta_nodo.setVisible(bool(self._nodos))

        self.casilla_mac = QCheckBox(texto_nombre_opcion_d("conservar_mac"))
        self.casilla_mac.setChecked(False)  # por defecto, MAC nueva (DT-D15)
        self.casilla_mac.setToolTip(ayuda("mac_origen"))
        self.casilla_mac.setAccessibleDescription(ayuda("mac_origen"))
        capa.addWidget(self.casilla_mac)
        self.aviso_mac = mensaje(aviso=True)
        capa.addWidget(self.aviso_mac)
        if self._cantidad > 1:
            # Con varias copias la MAC se repetiría: la casilla no se ofrece y se dice por qué.
            self.casilla_mac.setEnabled(False)
            poner_mensaje(
                self.aviso_mac,
                texto_problema_d(
                    Problema("cantidad", "V-D33", Severidad.ERROR, {"n": str(self._cantidad)})
                ),
                aviso=True,
            )

        # Estado, errores y motivos de bloqueo (siempre visibles, no solo al pasar el ratón).
        self.estado_lectura = etiqueta("", secundario=True)
        self.error_lectura = mensaje(error=True)
        self.motivos_bloqueo = mensaje(error=True)
        for w in (self.estado_lectura, self.error_lectura, self.motivos_bloqueo):
            capa.addWidget(w)

        # Tabla (modelo, no un widget por fila) y detalle de avisos.
        self.modelo = QStandardItemModel(0, _COLUMNAS, self)
        self.modelo.setHorizontalHeaderLabels(
            [
                self.tr("Concepto"),
                self.tr("En libvirt"),
                self.tr("En Proxmox"),
                self.tr("Estado"),
            ]
        )
        self.tabla = TablaCopiable(self.tr("Vista previa de la máquina de libvirt"))
        self.tabla.setModel(self.modelo)
        self.tabla.setSelectionMode(TablaCopiable.SelectionMode.SingleSelection)
        # Las columnas se ajustan al contenido y la última ocupa el sitio que sobre; así la
        # cabecera no se ve colapsada con la tabla vacía ni queda un hueco a la derecha.
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(_COLUMNAS - 1, QHeaderView.ResizeMode.Stretch)
        capa.addWidget(self.tabla, 3)

        self.detalle = QPlainTextEdit()
        self.detalle.setReadOnly(True)
        self.detalle.setAccessibleName(self.tr("Avisos y explicaciones de la vista previa"))
        self.detalle.setPlaceholderText(
            self.tr("Aquí aparecerán los avisos de lo que no se traslada o cambia.")
        )
        self.detalle.setMaximumHeight(150)
        capa.addWidget(self.detalle, 1)

        # Botones.
        pie = QHBoxLayout()
        self.boton_cancelar = QPushButton(self.tr("Cancelar"))
        self.boton_rellenar = QPushButton(self.tr("Rellenar el formulario"))
        for b in (self.boton_cancelar, self.boton_rellenar):
            b.setAutoDefault(False)
        pie.addStretch(1)
        pie.addWidget(self.boton_cancelar)
        pie.addWidget(self.boton_rellenar)
        capa_pie.addLayout(pie)

        self.boton_elegir.clicked.connect(self.elegir_archivo)
        self.boton_como_obtener.toggled.connect(self.texto_ayuda_xml.setVisible)
        self.boton_como_obtener.toggled.connect(self.panel_copiar_ordenes.setVisible)
        self.boton_cancelar.clicked.connect(self.reject)
        self.boton_rellenar.clicked.connect(self._rellenar)
        self.casilla_mac.toggled.connect(self._al_cambiar_opcion)
        self.combo_nodo.currentIndexChanged.connect(self._al_cambiar_opcion)

    def _copiar_orden(self, orden: str) -> None:
        """Copia la orden al portapapeles; nunca la ejecuta."""
        QApplication.clipboard().setText(orden)

    def _texto_nodo(self, nodo: str) -> str:
        if self._inv is None:
            return nodo
        return texto_nodo_con_arquitectura(nodo, arquitectura_efectiva(self._inv, nodo))

    # --- Datos de entrada ------------------------------------------------------------------

    @property
    def nodo_elegido(self) -> str:
        """Servidor de destino elegido en la vista previa (``""`` si no hay)."""
        return str(self.combo_nodo.currentData() or "")

    @property
    def conservar_mac(self) -> bool:
        """La casilla marcada y disponible (solo con una copia)."""
        return self.casilla_mac.isChecked() and self.casilla_mac.isEnabled()

    @property
    def macs_origen(self) -> tuple[str | None, ...]:
        """La MAC de cada tarjeta del XML leído, en orden (``None`` si no la trae)."""
        if self._dominio is None:
            return ()
        return tuple(t.mac for t in self._dominio.tarjetas)

    @property
    def propuesta(self) -> PropuestaLibvirt | None:
        """La propuesta que muestra la tabla ahora mismo."""
        return self._propuesta

    def elegir_archivo(self) -> None:
        """Pide el XML con el diálogo del sistema y lo manda leer (``pide_lectura``)."""
        ruta, _filtro = QFileDialog.getOpenFileName(
            self,
            self.tr("Elegir el XML de libvirt"),
            "",
            self.tr("Descripción de máquina (*.xml);;Todos los archivos (*)"),
        )
        if ruta:
            self.leer(Path(ruta))

    def leer(self, ruta: Path) -> None:
        """Manda leer ``ruta``: la lectura corre fuera del hilo de la interfaz (RNF-D6)."""
        self._dominio = None
        self._propuesta = None
        self._leyendo = True
        self.etiqueta_archivo.setText(ruta.name)
        poner_mensaje(self.error_lectura, None)
        self._vaciar_vista()
        self.estado_lectura.setText(self.tr("Leyendo el archivo…"))
        self.boton_elegir.setEnabled(False)
        self._actualizar_boton()
        self.pide_lectura.emit(ruta)

    # --- Resultados --------------------------------------------------------------------------

    def establecer_resultado(
        self, dominio: DominioLibvirt | None, error: ErrorProxLaunch | None
    ) -> None:
        """Resultado de la lectura: el dominio interpretado o el error (V-D20..V-D23)."""
        self._leyendo = False
        self.boton_elegir.setEnabled(True)
        self.estado_lectura.setText("")
        if error is not None or dominio is None:
            self._dominio = None
            self._vaciar_vista()
            poner_mensaje(
                self.error_lectura,
                texto_error(error)
                if error is not None
                else self.tr("No pude leer el archivo como una máquina de libvirt."),
            )
            self._actualizar_boton()
            return
        self._dominio = dominio
        self._pedir_propuesta()

    def _pedir_propuesta(self) -> None:
        if self._dominio is None:
            return
        self.pide_propuesta.emit(self._dominio, self.conservar_mac, self.nodo_elegido)

    def _al_cambiar_opcion(self, *_args: object) -> None:
        """Otro servidor de destino o la casilla de la MAC: se recalculan las filas (CA-D1.6.6)."""
        poner_mensaje(
            self.aviso_mac,
            texto_problema_d(Problema("", "V-D32", Severidad.AVISO, {}))
            if self.conservar_mac
            else None,
            aviso=True,
        )
        self._pedir_propuesta()

    def establecer_propuesta(self, propuesta: PropuestaLibvirt) -> None:
        """Pinta la vista previa: una fila por concepto con su estado en palabras y símbolo."""
        self._propuesta = propuesta
        self._vaciar_vista()
        lineas: list[str] = []
        bloqueos: list[str] = []
        for f in propuesta.filas:
            concepto = texto_concepto_fila(f.campo)
            items = [
                QStandardItem(concepto),
                QStandardItem(f.origen or "—"),
                QStandardItem(f.destino or "—"),
                QStandardItem(texto_estado_fila_simbolo(f.estado)),
            ]
            texto_p = texto_problema(f.problema) if f.problema is not None else ""
            for it in items:
                it.setEditable(False)
                if texto_p:
                    # Qt interpreta HTML en los tooltips y el texto puede venir del XML.
                    it.setToolTip(tooltip_plano(texto_p))
            self.modelo.appendRow(items)
            if texto_p:
                linea = f"{texto_estado_fila_simbolo(f.estado)} · {concepto}: {texto_p}"
                lineas.append(linea)
                if f.estado == EstadoFila.BLOQUEA:
                    bloqueos.append(f"{concepto}: {texto_p}")
        self.detalle.setPlainText("\n".join(dict.fromkeys(lineas)))
        poner_mensaje(
            self.motivos_bloqueo,
            "\n".join([self.tr("«Rellenar el formulario» no está disponible por esto:"), *bloqueos])
            if bloqueos
            else None,
        )
        self._actualizar_boton()

    def _vaciar_vista(self) -> None:
        self.modelo.removeRows(0, self.modelo.rowCount())
        self.detalle.clear()
        poner_mensaje(self.motivos_bloqueo, None)

    # --- Aceptar -----------------------------------------------------------------------------

    def _actualizar_boton(self) -> None:
        """«Rellenar» solo con una propuesta sin filas «Bloquea» y sin lectura en curso."""
        propuesta = self._propuesta
        habilitado = propuesta is not None and not propuesta.bloquea() and not self._leyendo
        self.boton_rellenar.setEnabled(habilitado)

    def _confirmar_reemplazo_por_defecto(self) -> bool:
        return confirmar(
            self,
            self.tr("Reemplazar lo que escribiste"),
            self.tr(
                "El formulario ya tiene datos tuyos. Al rellenarlo se reemplazan el nombre, la "
                "CPU, la memoria, los discos y las redes por los de la máquina de libvirt."
            ),
            self.tr("Reemplazar"),
            self.tr("Cancelar"),
        )

    def _rellenar(self) -> None:
        propuesta = self._propuesta
        if propuesta is None or propuesta.bloquea() or self._leyendo:
            return
        if self._formulario_modificado and not self.confirmar_reemplazo():
            return  # CA-D1.6.4: sin confirmar no cambia nada
        self.propuesta_aceptada = propuesta
        self.accept()

    def reject(self) -> None:
        self.propuesta_aceptada = None
        super().reject()
