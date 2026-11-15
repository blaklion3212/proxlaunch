"""Gestor de perfiles de máquina: lista, duplicar, renombrar, eliminar, exportar e importar.

Se abre desde «Perfiles → Administrar perfiles…» (modo avanzado, CA-P04.6). No hay editor de
hardware aparte (S-M1): para cambiar un perfil se aplica al formulario, se modifica allí y se
guarda con «Guardar cambios en el perfil». El almacén se usa en el hilo de la interfaz; la
lectura de archivos de terceros y la exportación corren en un hilo del ``Lanzador``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeAlias

from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QItemSelection,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch import __version__
from proxlaunch.interfaz.archivos_ui import (
    TipoArchivo,
    boton_ayuda_texto,
    elegir_para_abrir,
    elegir_para_guardar,
    nombre_sugerido,
)
from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.dialogos.guardar_perfil import DialogoNombrePerfil
from proxlaunch.interfaz.dialogos.importar_perfiles import DialogoImportarPerfiles
from proxlaunch.interfaz.modelos_tabla import TablaCopiable
from proxlaunch.interfaz.textos import texto_aviso_archivo, texto_fallo, texto_resumen_perfil
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.interfaz.vistas.campos import etiqueta, mensaje, poner_mensaje
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.almacen import AccionImportar, AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.formato import (
    ArchivoPerfiles,
    exportar_perfiles,
    leer_archivo_perfiles,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import OrigenPerfil, PerfilMaquina
from proxlaunch.nucleo.perfiles_maquina.validacion import nombre_libre

_Indice: TypeAlias = QModelIndex | QPersistentModelIndex


def texto_origen(origen: OrigenPerfil) -> str:
    """«De fábrica» o «Propio» (texto, no solo icono ni color, CA-P02.1)."""
    if origen == OrigenPerfil.FABRICA:
        return QCoreApplication.translate("DialogoPerfilesMaquina", "De fábrica")
    return QCoreApplication.translate("DialogoPerfilesMaquina", "Propio")


class ModeloPerfilesGestor(QAbstractTableModel):
    """Perfiles visibles: los de fábrica primero y después los del usuario."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._perfiles: tuple[PerfilMaquina, ...] = ()

    def establecer_perfiles(self, perfiles: Sequence[PerfilMaquina]) -> None:
        self.beginResetModel()
        self._perfiles = tuple(perfiles)
        self.endResetModel()

    def perfil(self, fila: int) -> PerfilMaquina | None:
        return self._perfiles[fila] if 0 <= fila < len(self._perfiles) else None

    def fila_de(self, id_perfil: str) -> int:
        for i, p in enumerate(self._perfiles):
            if p.id == id_perfil:
                return i
        return -1

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._perfiles)

    def columnCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else 3

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return (
                QCoreApplication.translate("DialogoPerfilesMaquina", "Nombre"),
                QCoreApplication.translate("DialogoPerfilesMaquina", "Tipo"),
                QCoreApplication.translate("DialogoPerfilesMaquina", "Resumen"),
            )[section]
        return None

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        p = self.perfil(index.row()) if index.isValid() else None
        if p is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return (p.nombre, texto_origen(p.origen), texto_resumen_perfil(p.config))[
                index.column()
            ]
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return QCoreApplication.translate(
                "DialogoPerfilesMaquina", "{nombre}, {tipo}: {resumen}"
            ).format(
                nombre=p.nombre, tipo=texto_origen(p.origen), resumen=texto_resumen_perfil(p.config)
            )
        return None


class _DialogoExportar(QDialog):
    """Pregunta si el archivo lleva los nombres de almacenamiento y red (desmarcado, CA-P08.2)."""

    def __init__(self, perfiles: Sequence[PerfilMaquina], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Exportar perfiles"))
        self.setModal(True)
        self.setMinimumWidth(460)
        capa = QVBoxLayout(self)
        n = len(perfiles)
        if n == 1:
            titulo = self.tr("Se exportará el perfil «{nombre}».").format(nombre=perfiles[0].nombre)
        else:
            titulo = self.tr("Se exportarán %n perfiles.", None, n)
        capa.addWidget(etiqueta(titulo))
        self.casilla_pistas = QCheckBox(self.tr("Incluir los nombres de almacenamiento y red"))
        self.casilla_pistas.setChecked(False)
        self.casilla_pistas.setAccessibleName(
            self.tr("Incluir los nombres de almacenamiento y red")
        )
        fila = QHBoxLayout()
        fila.addWidget(self.casilla_pistas, 1)
        fila.addWidget(
            boton_ayuda_texto(
                self.tr(
                    "Normalmente conviene dejarlo sin marcar: esos nombres son de tu servidor y "
                    "casi nunca existen en el de otra persona."
                )
            )
        )
        capa.addLayout(fila)
        capa.addWidget(
            etiqueta(
                self.tr(
                    "El archivo nunca incluye contraseñas, tokens, direcciones ni nombres de "
                    "usuario."
                ),
                secundario=True,
            )
        )
        botones = QDialogButtonBox()
        self.boton_exportar = QPushButton(self.tr("Elegir dónde guardar…"))
        self.boton_cancelar = QPushButton(self.tr("Cancelar"))
        botones.addButton(self.boton_exportar, QDialogButtonBox.ButtonRole.AcceptRole)
        botones.addButton(self.boton_cancelar, QDialogButtonBox.ButtonRole.RejectRole)
        self.boton_exportar.setDefault(True)
        self.boton_exportar.setProperty("primario", True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)

    @property
    def con_pistas(self) -> bool:
        return self.casilla_pistas.isChecked()


class DialogoPerfilesMaquina(QDialog):
    """Administra los perfiles de máquina (RF-P02, RF-P04, RF-P08, RF-P09, RF-P10).

    Constructor: ``DialogoPerfilesMaquina(almacen, lanzador, *, app_version=…, tema="oscuro",
    parent=…)``; el almacén ya debe estar cargado (``almacen.cargar()``).

    Señales para la ventana principal:

    - ``perfiles_cambiados(object)``: tras cualquier alta, baja o cambio; el valor es un
      ``frozenset[str]`` con los ids que desaparecieron o cambiaron (eliminados, renombrados o
      reemplazados) para que el selector muestre «Personalizado» (CA-P04.5). Vacío si solo se
      añadieron perfiles. Conviene refrescar el selector con ``almacen.todos()``.
    - ``usar_pedido(object)``: el usuario pidió aplicar ese ``PerfilMaquina`` al formulario.
    - ``crear_pedido()``: el usuario pidió «Guardar como perfil de máquina…» (la ventana abre
      ``DialogoGuardarPerfil`` con la configuración del formulario).
    """

    perfiles_cambiados = Signal(object)
    usar_pedido = Signal(object)
    crear_pedido = Signal()

    def __init__(
        self,
        almacen: AlmacenPerfilesMaquina,
        lanzador: Lanzador,
        *,
        app_version: str = __version__,
        tema: str = "oscuro",
        al_resultado_tardio: Callable[[str, bool], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Administrar perfiles de máquina"))
        self.setModal(True)
        self.resize(820, 560)
        self._almacen = almacen
        self._lanzador = lanzador
        self._app_version = app_version
        self._tema = tema
        self._ocupado = False
        self._generacion = 0
        # Resultado de una escritura que termina con el diálogo ya cerrado: (texto, es_error)
        # se entrega a quien abrió el diálogo y no se toca ningún widget.
        self._al_resultado_tardio = al_resultado_tardio
        self._cerrado = False
        self._construir()
        self.recargar()

    # --- Construcción --------------------------------------------------------------------

    def _construir(self) -> None:
        capa, capa_pie, _ = hacer_desplazable(self)
        capa.addWidget(
            etiqueta(
                self.tr(
                    "Un perfil de máquina es un punto de partida con el hardware ya elegido "
                    "(procesador, memoria, discos y red). No es una plantilla de Proxmox ni un "
                    "perfil de conexión."
                ),
                secundario=True,
            )
        )
        self.aviso_almacen = mensaje(aviso=True)
        capa.addWidget(self.aviso_almacen)

        self.modelo = ModeloPerfilesGestor(self)
        self.tabla = TablaCopiable(self.tr("Perfiles de máquina"))
        self.tabla.setModel(self.modelo)
        capa.addWidget(self.tabla, 1)

        self.detalle = etiqueta("")
        self.detalle.setAccessibleName(self.tr("Descripción del perfil seleccionado"))
        self.nota_fabrica = etiqueta(
            self.tr(
                "Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia "
                "versión."
            ),
            secundario=True,
        )
        self.estado = etiqueta("", secundario=True)
        self.error = mensaje(error=True)
        for w in (self.detalle, self.nota_fabrica):
            capa.addWidget(w)
        # Estado y error quedan fuera del área desplazable: siempre visibles junto a los botones.
        capa_pie.addWidget(self.estado)
        capa_pie.addWidget(self.error)

        fila1 = QHBoxLayout()
        self.boton_usar = QPushButton(self.tr("Usar en el formulario"))
        self.boton_crear = QPushButton(self.tr("Guardar el formulario como perfil…"))
        self.boton_duplicar = QPushButton(self.tr("Duplicar…"))
        self.boton_renombrar = QPushButton(self.tr("Renombrar…"))
        self.boton_eliminar = QPushButton(self.tr("Eliminar…"))
        for b in (
            self.boton_usar,
            self.boton_crear,
            self.boton_duplicar,
            self.boton_renombrar,
            self.boton_eliminar,
        ):
            fila1.addWidget(b)
        fila1.addStretch(1)
        capa_pie.addLayout(fila1)

        fila2 = QHBoxLayout()
        self.boton_importar = QPushButton(self.tr("Importar…"))
        self.boton_exportar = QPushButton(self.tr("Exportar…"))
        self.boton_cerrar = QPushButton(self.tr("Cerrar"))
        fila2.addWidget(self.boton_importar)
        fila2.addWidget(self.boton_exportar)
        fila2.addStretch(1)
        fila2.addWidget(self.boton_cerrar)
        capa_pie.addLayout(fila2)
        self.boton_cerrar.setDefault(True)
        for b in (self.boton_importar, self.boton_exportar):
            b.setAutoDefault(False)

        self.boton_usar.clicked.connect(self._usar)
        self.boton_crear.clicked.connect(self.crear_pedido.emit)
        self.boton_duplicar.clicked.connect(self.duplicar)
        self.boton_renombrar.clicked.connect(self.renombrar)
        self.boton_eliminar.clicked.connect(self.eliminar)
        self.boton_importar.clicked.connect(lambda: self.importar())
        self.boton_exportar.clicked.connect(self.exportar)
        self.boton_cerrar.clicked.connect(self.accept)
        self.tabla.selectionModel().selectionChanged.connect(self._al_seleccionar)

    # --- Estado ------------------------------------------------------------------------------

    @property
    def almacen(self) -> AlmacenPerfilesMaquina:
        return self._almacen

    def seleccionados(self) -> tuple[PerfilMaquina, ...]:
        """Perfiles seleccionados en la tabla, en el orden de la lista."""
        filas = sorted({i.row() for i in self.tabla.selectionModel().selectedRows()})
        return tuple(p for f in filas if (p := self.modelo.perfil(f)) is not None)

    def seleccionar(self, id_perfil: str) -> None:
        fila = self.modelo.fila_de(id_perfil)
        if fila >= 0:
            self.tabla.selectRow(fila)

    def recargar(self, seleccionar: str | None = None) -> None:
        """Vuelve a leer la lista del almacén y actualiza avisos y botones."""
        anterior = [p.id for p in self.seleccionados()]
        self.modelo.establecer_perfiles(self._almacen.todos())
        self._mostrar_estado_almacen()
        elegido = seleccionar or (anterior[0] if anterior else None)
        if elegido is not None and self.modelo.fila_de(elegido) >= 0:
            self.seleccionar(elegido)
        elif self.modelo.rowCount():
            self.tabla.selectRow(0)
        self._actualizar_botones()

    def _mostrar_estado_almacen(self) -> None:
        """Avisos de solo lectura, corrupción, permisos y perfiles descartados."""
        e = self._almacen.estado
        lineas: list[str] = []
        if e.solo_lectura:
            lineas.append(
                self.tr(
                    "Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se "
                    "pueden modificar."
                )
            )
        if e.hubo_corrupcion and e.error_lectura:
            lineas.append(
                self.tr(
                    "No se pudo leer tu archivo de perfiles (revisa sus permisos). Solo se "
                    "muestran los de fábrica y no se guardará nada nuevo hasta que se pueda leer."
                )
            )
        elif e.hubo_corrupcion:
            copia = e.copia_danada.name if e.copia_danada is not None else ""
            lineas.append(
                self.tr(
                    "Tu archivo de perfiles estaba dañado. Se guardó una copia («{copia}») y se "
                    "empezó con la lista vacía."
                ).format(copia=copia)
            )
        if e.descartados:
            n = len(e.descartados)
            lineas.append(
                self.tr("Se descartó 1 campo no válido del archivo de perfiles.")
                if n == 1
                else self.tr(
                    "Se descartaron %n campos no válidos del archivo de perfiles.", None, n
                )
            )
        lineas.extend(texto_aviso_archivo(a) for a in e.avisos)
        poner_mensaje(self.aviso_almacen, "\n".join(lineas) if lineas else None, aviso=True)

    def _escribible(self) -> bool:
        e = self._almacen.estado
        return not e.solo_lectura and not e.error_lectura

    def _actualizar_botones(self) -> None:
        sel = self.seleccionados()
        uno = len(sel) == 1
        hay = bool(sel)
        propio = uno and sel[0].origen == OrigenPerfil.USUARIO
        libre = not self._ocupado
        escribible = self._escribible()
        self.boton_usar.setEnabled(uno and libre)
        self.boton_crear.setEnabled(libre and escribible)
        self.boton_duplicar.setEnabled(uno and libre and escribible)
        self.boton_renombrar.setEnabled(propio and libre and escribible)
        self.boton_eliminar.setEnabled(propio and libre and escribible)
        self.boton_exportar.setEnabled(hay and libre)
        self.boton_importar.setEnabled(libre and escribible)
        # CA-P02.2: editar, renombrar y eliminar quedan deshabilitados con su explicación.
        self.nota_fabrica.setVisible(hay and any(p.origen == OrigenPerfil.FABRICA for p in sel))
        if uno:
            texto = sel[0].descripcion or self.tr("Este perfil no tiene descripción.")
            self.detalle.setText(f"{sel[0].nombre}: {texto}\n{texto_resumen_perfil(sel[0].config)}")
        else:
            self.detalle.setText("")

    def _al_seleccionar(self, _nuevo: QItemSelection, _viejo: QItemSelection) -> None:
        self._actualizar_botones()

    def _poner_ocupado(self, ocupado: bool) -> None:
        self._ocupado = ocupado
        self._actualizar_botones()

    def _fallo(self, error: ErrorProxLaunch) -> None:
        poner_mensaje(self.error, texto_fallo(error))

    # --- Operaciones del almacén (hilo de la interfaz) -----------------------------------------

    def _usar(self) -> None:
        sel = self.seleccionados()
        if len(sel) == 1:
            self.usar_pedido.emit(sel[0])

    def duplicar(self) -> None:
        """«Duplicar…»: copia de cualquier perfil (también de fábrica) con nombre propio."""
        sel = self.seleccionados()
        if len(sel) != 1 or not self._escribible():
            return
        origen = sel[0]
        dialogo = DialogoNombrePerfil(
            self._almacen.todos(),
            titulo=self.tr("Duplicar perfil"),
            texto_aceptar=self.tr("Duplicar"),
            nombre_inicial=nombre_libre(
                self.tr("Copia de {nombre}").format(nombre=origen.nombre), self._almacen.todos()
            ),
            parent=self,
        )
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            copia = self._almacen.duplicar(origen.id, dialogo.nombre)
        except ErrorProxLaunch as error:
            self._fallo(error)
            return
        poner_mensaje(self.error, None)
        self.estado.setText(self.tr("Se creó «{nombre}».").format(nombre=copia.nombre))
        self.recargar(copia.id)
        self.perfiles_cambiados.emit(frozenset())

    def renombrar(self) -> None:
        """«Renombrar…»: nombre y descripción de un perfil propio; el hardware no cambia."""
        sel = self.seleccionados()
        if len(sel) != 1 or sel[0].origen != OrigenPerfil.USUARIO or not self._escribible():
            return
        perfil = sel[0]
        dialogo = DialogoNombrePerfil(
            self._almacen.todos(),
            titulo=self.tr("Renombrar perfil"),
            texto_aceptar=self.tr("Guardar"),
            nombre_inicial=perfil.nombre,
            descripcion_inicial=perfil.descripcion,
            excluir_id=perfil.id,
            parent=self,
        )
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            nuevo = self._almacen.renombrar(perfil.id, dialogo.nombre, dialogo.descripcion)
        except ErrorProxLaunch as error:
            self._fallo(error)
            return
        poner_mensaje(self.error, None)
        self.estado.setText(
            self.tr("Se cambió el nombre a «{nombre}».").format(nombre=nuevo.nombre)
        )
        self.recargar(nuevo.id)
        self.perfiles_cambiados.emit(frozenset({perfil.id}))

    def eliminar(self) -> None:
        """«Eliminar…»: confirma con el nombre y el foco en «Cancelar» (CA-P04.4)."""
        sel = self.seleccionados()
        if len(sel) != 1 or sel[0].origen != OrigenPerfil.USUARIO or not self._escribible():
            return
        perfil = sel[0]
        if not confirmar(
            self,
            self.tr("Eliminar perfil"),
            self.tr(
                "¿Eliminar el perfil «{nombre}»? Los lotes que ya guardaste no cambian."
            ).format(nombre=perfil.nombre),
            self.tr("Eliminar"),
            self.tr("Cancelar"),
        ):
            return
        try:
            self._almacen.eliminar(perfil.id)
        except ErrorProxLaunch as error:
            self._fallo(error)
            return
        poner_mensaje(self.error, None)
        self.estado.setText(self.tr("Se eliminó «{nombre}».").format(nombre=perfil.nombre))
        self.recargar()
        self.perfiles_cambiados.emit(frozenset({perfil.id}))

    # --- Exportar e importar (archivos en hilo) -----------------------------------------------

    def exportar(self) -> None:
        """«Exportar…»: casilla de pistas desmarcada, ruta del sistema y escritura en un hilo."""
        sel = self.seleccionados()
        if not sel or self._ocupado:
            return
        dialogo = _DialogoExportar(sel, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        base = sel[0].nombre if len(sel) == 1 else self.tr("perfiles-proxlaunch")
        ruta = elegir_para_guardar(
            self, TipoArchivo.PERFILES, nombre_sugerido(TipoArchivo.PERFILES, base)
        )
        if ruta is None:
            return
        self._poner_ocupado(True)
        poner_mensaje(self.error, None)
        self.estado.setText(self.tr("Exportando…"))
        n = len(sel)
        self._lanzador.lanzar(
            exportar_perfiles,
            ruta,
            list(sel),
            con_pistas=dialogo.con_pistas,
            app_version=self._app_version,
            al_terminar=lambda _r: self._al_exportar(n),
            al_fallar=self._al_fallar_archivo,
        )

    def _al_exportar(self, n: int) -> None:
        texto = (
            self.tr("Se exportó 1 perfil.")
            if n == 1
            else self.tr("Se exportaron %n perfiles.", None, n)
        )
        if self._cerrado:
            self._entregar_tardio(texto, False)
            return
        self._poner_ocupado(False)
        self.estado.setText(texto)

    def _entregar_tardio(self, texto: str, es_error: bool) -> None:
        """El diálogo ya se cerró: el resultado va a la ventana principal, no a los widgets."""
        if self._al_resultado_tardio is not None:
            self._al_resultado_tardio(texto, es_error)

    def _al_fallar_archivo(self, error: ErrorProxLaunch) -> None:
        if self._cerrado:
            self._entregar_tardio(texto_fallo(error), True)
            return
        self._poner_ocupado(False)
        self.estado.setText("")
        self._fallo(error)

    def importar(self, ruta: Path | None = None) -> None:
        """«Importar…»: lee el archivo en un hilo y abre la lista de revisión.

        ``ruta`` permite saltar el diálogo del sistema (pruebas, arrastrar y soltar).
        """
        if self._ocupado or not self._escribible():
            return
        if ruta is None:
            ruta = elegir_para_abrir(self, TipoArchivo.PERFILES)
            if ruta is None:
                return
        self._generacion += 1
        generacion = self._generacion
        self._poner_ocupado(True)
        poner_mensaje(self.error, None)
        self.estado.setText(self.tr("Leyendo el archivo…"))
        self._lanzador.lanzar(
            leer_archivo_perfiles,
            ruta,
            al_terminar=lambda a: self._si_vigente(generacion, lambda: self._revisar_archivo(a)),
            al_fallar=lambda e: self._si_vigente(generacion, lambda: self._al_fallar_archivo(e)),
        )

    def _si_vigente(self, generacion: int, accion: Callable[[], None]) -> None:
        if generacion == self._generacion:
            accion()

    def _revisar_archivo(self, archivo: ArchivoPerfiles) -> None:
        self._poner_ocupado(False)
        self.estado.setText("")
        revision = DialogoImportarPerfiles(
            archivo, self._almacen.todos(), tema=self._tema, parent=self
        )
        entradas = revision.ejecutar()
        if not entradas:
            return
        try:
            creados = self._almacen.importar(entradas)
        except ErrorProxLaunch as error:
            self._fallo(error)
            return
        afectados = frozenset(
            e.reemplaza_id
            for e in entradas
            if e.accion == AccionImportar.REEMPLAZAR and e.reemplaza_id is not None
        )
        n = len(creados)
        self.estado.setText(
            self.tr("Se importó 1 perfil.")
            if n == 1
            else self.tr("Se importaron %n perfiles.", None, n)
        )
        self.recargar(creados[-1].id if creados else None)
        self.perfiles_cambiados.emit(afectados)

    def showEvent(self, evento: QShowEvent) -> None:
        self._cerrado = False
        super().showEvent(evento)

    def done(self, resultado: int) -> None:
        """Al cerrar se descartan las lecturas en curso; las escrituras avisan a la ventana."""
        self._generacion += 1
        self._cerrado = True
        super().done(resultado)
