"""Elegir un ISO, una imagen de disco o una plantilla del servidor (RF-O07, RF-O16, RF-O19).

El diálogo solo muestra datos que le entrega quien lo abre (el catálogo se lee fuera de este
hilo): filtra por nombre, muestra tamaño y nodo, marca los drivers virtio-win y deja las filas
que no se pueden elegir deshabilitadas con el motivo escrito. «Subir…» y «Descargar…» no hacen nada
por sí mismos: emiten una señal para que el controlador abra el diálogo de transferencia. No hay
ningún botón de borrado (INV-O4).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.modelos_tabla_origen import (
    ROL_FILA,
    FilaPlantilla,
    FilaVolumen,
    FiltroPorNombre,
    ModeloCatalogoVolumenes,
    ModeloPlantillas,
    texto_explicacion_via,
)
from proxlaunch.interfaz.textos import texto_error
from proxlaunch.interfaz.vistas.campos import poner_mensaje
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import (
    Contenido,
    ListadoStorage,
    PermisosEfectivos,
    Plantilla,
    Volumen,
)
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, EstadoVia


class FuenteCatalogo(StrEnum):
    """Qué se está eligiendo."""

    ISO = "iso"  # ISO de instalación
    DRIVERS = "drivers"  # ISO de drivers virtio-win (también contenido ``iso``)
    IMAGEN = "imagen"  # imagen de disco a importar (contenido ``import``)
    PLANTILLA = "plantilla"  # plantilla de Proxmox a clonar

    @property
    def contenido(self) -> Contenido | None:
        """Contenido de storage que usa la fuente (``None`` para plantillas)."""
        if self == FuenteCatalogo.IMAGEN:
            return Contenido.IMPORT
        if self == FuenteCatalogo.PLANTILLA:
            return None
        return Contenido.ISO


class DialogoCatalogo(QDialog):
    """Lista filtrable de volúmenes o plantillas con «Subir», «Descargar» y «Actualizar».

    Señales:
    - ``elegido(object)``: el usuario eligió; lleva ``FilaVolumen`` o ``FilaPlantilla``.
    - ``subir_solicitado()`` / ``descargar_solicitado()``: abrir el diálogo de transferencia.
    - ``actualizar_solicitado()``: volver a leer el catálogo.
    """

    elegido = Signal(object)
    subir_solicitado = Signal()
    descargar_solicitado = Signal()
    actualizar_solicitado = Signal()

    def __init__(
        self,
        fuente: FuenteCatalogo,
        parent: QWidget | None = None,
        *,
        estado_subir: EstadoVia | None = None,
        estado_descargar: EstadoVia | None = None,
        tema: str = "oscuro",
    ) -> None:
        super().__init__(parent)
        self.fuente = fuente
        self._es_plantilla = fuente == FuenteCatalogo.PLANTILLA
        self._estado_subir = estado_subir
        self._estado_descargar = estado_descargar
        self._seleccion: FilaVolumen | FilaPlantilla | None = None
        self._modelo: ModeloCatalogoVolumenes | ModeloPlantillas
        self._modelo = (
            ModeloPlantillas(self) if self._es_plantilla else ModeloCatalogoVolumenes(self)
        )
        self._modelo.establecer_tema(tema)
        self._filtro = FiltroPorNombre(self)
        self._filtro.setSourceModel(self._modelo)
        self._cargando = False
        self._hay_datos = False

        self.setWindowTitle(self._titulo())
        self.setModal(True)
        self.setMinimumSize(900, 460)

        explicacion = QLabel(self._explicacion())
        explicacion.setWordWrap(True)
        explicacion.setProperty("secundario", True)

        self.campo_filtro = QLineEdit()
        self.campo_filtro.setClearButtonEnabled(True)
        self.campo_filtro.setPlaceholderText(self.tr("Filtrar por nombre"))
        self.campo_filtro.setAccessibleName(self.tr("Filtrar por nombre"))
        self.campo_filtro.textChanged.connect(self._al_filtrar)

        self.tabla = QTableView()
        self.tabla.setModel(self._filtro)
        self.tabla.setAccessibleName(self._nombre_tabla())
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSortingEnabled(True)
        self.tabla.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tabla.setWordWrap(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # La última columna (nota o motivo de deshabilitado) ocupa el espacio que sobra.
        cabecera.setSectionResizeMode(
            self._modelo.columnCount() - 1, QHeaderView.ResizeMode.Stretch
        )
        self.tabla.selectionModel().selectionChanged.connect(self._actualizar_botones)
        self.tabla.doubleClicked.connect(self._al_doble_clic)

        self.etiqueta_estado = QLabel()
        self.etiqueta_estado.setWordWrap(True)
        self.etiqueta_estado.setTextFormat(Qt.TextFormat.PlainText)
        self.etiqueta_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.etiqueta_estado.setProperty("secundario", True)
        self.etiqueta_estado.setAccessibleName(self.tr("Estado del catálogo"))

        self.etiqueta_errores = QLabel()
        self.etiqueta_errores.setWordWrap(True)
        self.etiqueta_errores.setTextFormat(Qt.TextFormat.PlainText)
        self.etiqueta_errores.setProperty("aviso", True)
        self.etiqueta_errores.hide()

        self.boton_subir = QPushButton(self.tr("Subir desde mi equipo…"))
        self.boton_subir.setAutoDefault(False)
        self.boton_subir.clicked.connect(self.subir_solicitado)
        self.boton_descargar = QPushButton(self.tr("Descargar en el servidor…"))
        self.boton_descargar.setAutoDefault(False)
        self.boton_descargar.clicked.connect(self.descargar_solicitado)
        self.boton_actualizar = QPushButton(self.tr("Actualizar"))
        self.boton_actualizar.setAutoDefault(False)
        self.boton_actualizar.clicked.connect(self.actualizar_solicitado)
        self.boton_cancelar = QPushButton(self.tr("Cancelar"))
        self.boton_cancelar.setAutoDefault(False)
        self.boton_cancelar.clicked.connect(self.reject)
        self.boton_elegir = QPushButton(self.tr("Elegir"))
        self.boton_elegir.setProperty("primario", True)
        self.boton_elegir.setDefault(True)
        self.boton_elegir.clicked.connect(self._elegir)

        self.motivo_subir = QLabel()
        self.motivo_subir.setWordWrap(True)
        self.motivo_subir.setTextFormat(Qt.TextFormat.PlainText)
        self.motivo_subir.setProperty("secundario", True)
        self.motivo_subir.hide()

        capa = QVBoxLayout(self)
        capa.addWidget(explicacion)
        capa.addWidget(self.campo_filtro)
        capa.addWidget(self.etiqueta_errores)
        capa.addWidget(self.tabla, 1)
        capa.addWidget(self.etiqueta_estado)
        capa.addWidget(self.motivo_subir)
        fila = QHBoxLayout()
        if not self._es_plantilla:
            fila.addWidget(self.boton_subir)
            fila.addWidget(self.boton_descargar)
        else:
            self.boton_subir.hide()
            self.boton_descargar.hide()
        fila.addWidget(self.boton_actualizar)
        fila.addStretch(1)
        fila.addWidget(self.boton_cancelar)
        fila.addWidget(self.boton_elegir)
        capa.addLayout(fila)

        self._aplicar_estado_vias()
        self._refrescar_vacio()
        self._actualizar_botones()
        self.campo_filtro.setFocus()

    # --- API pública --------------------------------------------------------------------

    @property
    def seleccion(self) -> FilaVolumen | FilaPlantilla | None:
        """Lo elegido tras aceptar (``None`` si se canceló)."""
        return self._seleccion

    @property
    def modelo(self) -> ModeloCatalogoVolumenes | ModeloPlantillas:
        """Modelo de origen (sin filtrar)."""
        return self._modelo

    def establecer_tema(self, tema: str) -> None:
        """Recolorea las filas según el tema (``"claro"`` u ``"oscuro"``)."""
        self._modelo.establecer_tema(tema)

    def establecer_cargando(self, cargando: bool) -> None:
        """Muestra «Cargando…» mientras el controlador lee el catálogo."""
        self._cargando = cargando
        self.boton_actualizar.setEnabled(not cargando)
        self._refrescar_vacio()

    def establecer_volumenes(
        self,
        volumenes: Sequence[Volumen],
        *,
        nodo: str = "",
        errores: Sequence[ErrorProxLaunch] = (),
    ) -> None:
        """Carga los volúmenes de ``nodo`` (los de otro contenido se ignoran) y los errores por
        storage (E-O05), que se muestran aparte sin impedir ver los demás."""
        if isinstance(self._modelo, ModeloCatalogoVolumenes):
            contenido = self.fuente.contenido
            self._modelo.establecer_volumenes(
                [v for v in volumenes if contenido is None or v.contenido == contenido], nodo
            )
        self._cargando = False
        self._hay_datos = True
        self._mostrar_errores(errores)
        self._tras_cargar()

    def establecer_listados(self, listados: Sequence[ListadoStorage]) -> None:
        """Igual que ``establecer_volumenes`` partiendo de los listados por storage y nodo."""
        if isinstance(self._modelo, ModeloCatalogoVolumenes):
            contenido = self.fuente.contenido
            self._modelo.establecer_listados(
                [lst for lst in listados if contenido is None or lst.contenido == contenido]
            )
        self._cargando = False
        self._hay_datos = True
        self._mostrar_errores([lst.error for lst in listados if lst.error is not None])
        self._tras_cargar()

    def establecer_plantillas(
        self,
        plantillas: Sequence[Plantilla] | None,
        permisos: PermisosEfectivos | None = None,
    ) -> None:
        """Carga las plantillas (``None`` = aún no leídas) y deshabilita las no clonables."""
        if isinstance(self._modelo, ModeloPlantillas):
            self._modelo.establecer_plantillas(plantillas or (), permisos)
        self._hay_datos = plantillas is not None
        self._cargando = plantillas is None
        self._mostrar_errores(())
        self._tras_cargar()

    def seleccionar_volid(self, volid: str) -> bool:
        """Deja marcado el volumen con ese volid (p. ej. el recién subido); ``False`` si no está
        o no es elegible."""
        if not isinstance(self._modelo, ModeloCatalogoVolumenes):
            return False
        return self._seleccionar_fila(self._modelo.buscar_volid(volid))

    def seleccionar_vmid(self, vmid: int) -> bool:
        """Deja marcada la plantilla con ese VMID; ``False`` si no está o no es elegible."""
        if not isinstance(self._modelo, ModeloPlantillas):
            return False
        return self._seleccionar_fila(self._modelo.buscar_vmid(vmid))

    def actualizar_vias(
        self, estado_subir: EstadoVia | None, estado_descargar: EstadoVia | None
    ) -> None:
        """Recibe los estados de las vías de subida y descarga (tras recalcular capacidades)."""
        self._estado_subir = estado_subir
        self._estado_descargar = estado_descargar
        self._aplicar_estado_vias()

    # --- Textos -------------------------------------------------------------------------

    def _titulo(self) -> str:
        return {
            FuenteCatalogo.ISO: self.tr("Elegir un archivo ISO"),
            FuenteCatalogo.DRIVERS: self.tr("Elegir el ISO de drivers virtio-win"),
            FuenteCatalogo.IMAGEN: self.tr("Elegir un disco existente"),
            FuenteCatalogo.PLANTILLA: self.tr("Elegir una plantilla de Proxmox"),
        }[self.fuente]

    def _explicacion(self) -> str:
        return {
            FuenteCatalogo.ISO: self.tr(
                "Estos son los archivos ISO que hay en el servidor. Si el tuyo no está, "
                "súbelo desde tu equipo o haz que el servidor lo descargue."
            ),
            FuenteCatalogo.DRIVERS: self.tr(
                "Windows necesita los drivers virtio-win para ver el disco y la red. "
                "Elige el ISO que empieza por «virtio-win»."
            ),
            FuenteCatalogo.IMAGEN: self.tr(
                "Estos son los discos (qcow2, vmdk, raw) que hay en el servidor para importar."
            ),
            FuenteCatalogo.PLANTILLA: self.tr(
                "Estas son las plantillas de Proxmox que tu cuenta puede ver. La nueva máquina "
                "será una copia de la que elijas."
            ),
        }[self.fuente]

    def _nombre_tabla(self) -> str:
        return {
            FuenteCatalogo.ISO: self.tr("Archivos ISO del servidor"),
            FuenteCatalogo.DRIVERS: self.tr("Archivos ISO del servidor"),
            FuenteCatalogo.IMAGEN: self.tr("Discos del servidor para importar"),
            FuenteCatalogo.PLANTILLA: self.tr("Plantillas del servidor"),
        }[self.fuente]

    def _texto_vacio(self) -> str:
        if self._es_plantilla:
            return texto_error(ErrorProxLaunch(CodigoError.SIN_PLANTILLAS))
        if self.fuente == FuenteCatalogo.IMAGEN:
            base = self.tr("No hay ningún disco en el servidor.")
        else:
            base = self.tr("No hay ningún ISO en el servidor.")
        puede_subir = self._via_ofrecida(self._estado_subir)
        puede_descargar = self._via_ofrecida(self._estado_descargar)
        if puede_subir and puede_descargar:
            return (
                base
                + " "
                + self.tr("Puedes subir uno desde tu equipo o hacer que el servidor lo descargue.")
            )
        if puede_subir:
            return base + " " + self.tr("Puedes subir uno desde tu equipo.")
        if puede_descargar:
            return base + " " + self.tr("Puedes hacer que el servidor lo descargue.")
        return base

    @staticmethod
    def _via_ofrecida(estado: EstadoVia | None) -> bool:
        return estado is not None and estado.disponibilidad != Disponibilidad.NO

    # --- Internos -----------------------------------------------------------------------

    def _aplicar_estado_vias(self) -> None:
        """Deshabilita «Subir»/«Descargar» con el motivo escrito debajo (RF-O24, CA-O10.5)."""
        motivos: list[str] = []
        for boton, estado in (
            (self.boton_subir, self._estado_subir),
            (self.boton_descargar, self._estado_descargar),
        ):
            if estado is None:
                boton.setEnabled(True)
                boton.setToolTip("")
                continue
            ofrecida = estado.disponibilidad != Disponibilidad.NO
            boton.setEnabled(ofrecida)
            motivo = texto_explicacion_via(estado)
            boton.setToolTip(motivo)
            if not ofrecida and motivo:
                motivos.append(f"{boton.text().rstrip('…')}: {motivo}")
        poner_mensaje(self.motivo_subir, "\n".join(motivos) if motivos else None)
        if motivos:
            self.motivo_subir.setProperty("secundario", True)
        self._refrescar_vacio()

    def _mostrar_errores(self, errores: Sequence[ErrorProxLaunch]) -> None:
        textos = [texto_error(e) for e in errores]
        poner_mensaje(self.etiqueta_errores, "\n".join(textos) if textos else None, aviso=True)

    def _tras_cargar(self) -> None:
        self.tabla.clearSelection()
        self._refrescar_vacio()
        self._actualizar_botones()

    def _al_filtrar(self, texto: str) -> None:
        self._filtro.establecer_texto(texto)
        self._refrescar_vacio()
        self._actualizar_botones()

    def _refrescar_vacio(self) -> None:
        """Texto de estado: cargando, catálogo vacío o ningún resultado del filtro."""
        if self._cargando:
            texto = self.tr("Cargando…")
        elif self._hay_datos and self._modelo.rowCount() == 0:
            texto = self._texto_vacio()
        elif self._hay_datos and self._filtro.rowCount() == 0:
            texto = self.tr("Ningún elemento coincide con el filtro.")
        else:
            texto = ""
        self.etiqueta_estado.setText(texto)
        self.etiqueta_estado.setVisible(bool(texto))

    def _fila_marcada(self) -> FilaVolumen | FilaPlantilla | None:
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return None
        fila = filas[0].data(ROL_FILA)
        if isinstance(fila, (FilaVolumen, FilaPlantilla)):
            return fila
        return None

    def _actualizar_botones(self, *_args: object) -> None:
        fila = self._fila_marcada()
        self.boton_elegir.setEnabled(fila is not None and fila.elegible)

    def _seleccionar_fila(self, fila_origen: int) -> bool:
        if fila_origen < 0:
            return False
        origen = self._modelo.index(fila_origen, 0)
        if not self._modelo.flags(origen) & Qt.ItemFlag.ItemIsSelectable:
            return False
        indice = self._filtro.mapFromSource(origen)
        if not indice.isValid():
            return False
        self.tabla.selectRow(indice.row())
        self.tabla.scrollTo(indice)
        return True

    def _al_doble_clic(self, indice: QModelIndex) -> None:
        if indice.isValid():
            self._elegir()

    def _elegir(self) -> None:
        fila = self._fila_marcada()
        if fila is None or not fila.elegible:
            return
        self._seleccion = fila
        self.elegido.emit(fila)
        self.accept()
