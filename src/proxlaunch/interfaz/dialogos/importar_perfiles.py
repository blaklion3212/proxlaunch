"""Revisión de un archivo de perfiles de terceros antes de importarlo (RF-P09).

Nada se guarda aquí: el diálogo solo recoge qué perfiles entran y qué hacer con los que
repiten un nombre (conservar ambos, reemplazar u omitir). Quien lo abre llama después a
``almacen.importar(dialogo.entradas())``, que es todo o nada (CA-P09.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.modelos_tabla import TablaCopiable
from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.interfaz.textos import (
    texto_aviso_archivo,
    texto_error_campo,
    texto_regla_perfil,
    texto_resumen_perfil,
    tooltip_plano,
)
from proxlaunch.interfaz.vistas.campos import etiqueta, mensaje, poner_mensaje
from proxlaunch.nucleo.archivos.constantes import MAX_PERFILES_USUARIO
from proxlaunch.nucleo.archivos.texto import clave_comparacion
from proxlaunch.nucleo.perfiles_maquina.almacen import AccionImportar, EntradaImportacion
from proxlaunch.nucleo.perfiles_maquina.formato import ArchivoPerfiles, PerfilInvalido, PerfilLeido
from proxlaunch.nucleo.perfiles_maquina.modelos import OrigenPerfil, PerfilMaquina

_Indice: TypeAlias = QModelIndex | QPersistentModelIndex


class AccionFila:
    """Qué hacer con un perfil del archivo (la interfaz distingue «omitir», que el núcleo no)."""

    CONSERVAR_AMBOS = "conservar_ambos"
    REEMPLAZAR = "reemplazar"
    OMITIR = "omitir"


@dataclass
class _FilaRevision:
    indice: int
    nombre: str
    leido: PerfilLeido | None
    invalido: PerfilInvalido | None
    conflicto: PerfilMaquina | None = None
    marcada: bool = True
    accion: str = AccionFila.CONSERVAR_AMBOS

    @property
    def valida(self) -> bool:
        return self.leido is not None


class ModeloRevisionPerfiles(QAbstractTableModel):
    """Tabla de revisión: casilla, nombre, resumen y estado (CA-P09.1)."""

    cambiado = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filas: list[_FilaRevision] = []
        self._tokens: dict[str, str] = TOKENS_OSCURO

    def establecer_tema(self, tema: str) -> None:
        self._tokens = TOKENS_CLARO if tema == "claro" else TOKENS_OSCURO
        if self._filas:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._filas) - 1, self.columnCount() - 1)
            )

    def cargar(self, filas: list[_FilaRevision]) -> None:
        self.beginResetModel()
        self._filas = filas
        self.endResetModel()
        self.cambiado.emit()

    @property
    def filas(self) -> list[_FilaRevision]:
        return self._filas

    def fila(self, i: int) -> _FilaRevision | None:
        return self._filas[i] if 0 <= i < len(self._filas) else None

    def refrescar(self, i: int) -> None:
        if 0 <= i < len(self._filas):
            self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount() - 1))
        self.cambiado.emit()

    def rowCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._filas)

    def columnCount(self, parent: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else 4

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return (
                QCoreApplication.translate("DialogoImportarPerfiles", "Importar"),
                QCoreApplication.translate("DialogoImportarPerfiles", "Nombre"),
                QCoreApplication.translate("DialogoImportarPerfiles", "Resumen"),
                QCoreApplication.translate("DialogoImportarPerfiles", "Estado"),
            )[section]
        return None

    def flags(self, index: _Indice) -> Qt.ItemFlag:
        base = super().flags(index)
        f = self.fila(index.row()) if index.isValid() else None
        if f is not None and f.valida and index.column() == 0:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def setData(self, index: _Indice, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:
        f = self.fila(index.row()) if index.isValid() else None
        if f is None or not f.valida or index.column() != 0:
            return False
        if role != Qt.ItemDataRole.CheckStateRole:
            return False
        f.marcada = value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value, 2, True)
        if f.conflicto is not None:
            f.accion = AccionFila.CONSERVAR_AMBOS if f.marcada else AccionFila.OMITIR
        self.refrescar(index.row())
        return True

    @staticmethod
    def texto_estado(f: _FilaRevision) -> str:
        if not f.valida:
            return QCoreApplication.translate("DialogoImportarPerfiles", "✖ No válido")
        if not f.marcada or f.accion == AccionFila.OMITIR:
            return QCoreApplication.translate("DialogoImportarPerfiles", "Omitido")
        if f.conflicto is None:
            return QCoreApplication.translate("DialogoImportarPerfiles", "✔ Nuevo")
        if f.accion == AccionFila.REEMPLAZAR:
            return QCoreApplication.translate("DialogoImportarPerfiles", "⚠ Reemplaza al existente")
        return QCoreApplication.translate(
            "DialogoImportarPerfiles", "⚠ Nombre repetido: se conservan ambos"
        )

    def data(self, index: _Indice, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        f = self.fila(index.row()) if index.isValid() else None
        if f is None:
            return None
        col = index.column()
        if col == 0:
            if f.valida and role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if f.marcada else Qt.CheckState.Unchecked
            if role == Qt.ItemDataRole.DisplayRole and not f.valida:
                return "—"
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return QCoreApplication.translate(
                    "DialogoImportarPerfiles", "Importar «{nombre}»"
                ).format(nombre=f.nombre)
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 1:
                return f.nombre
            if col == 2:
                return texto_resumen_perfil(f.leido.config) if f.leido is not None else ""
            return self.texto_estado(f)
        if role == Qt.ItemDataRole.ForegroundRole and col == 3:
            if not f.valida:
                return QColor(self._tokens["error"])
            if f.conflicto is not None and f.marcada:
                return QColor(self._tokens["aviso"])
            return QColor(self._tokens["exito"] if f.marcada else self._tokens["texto_secundario"])
        if role == Qt.ItemDataRole.ToolTipRole and not f.valida and f.invalido is not None:
            return tooltip_plano("\n".join(texto_error_campo(e) for e in f.invalido.errores[:10]))
        return None


class DialogoImportarPerfiles(QDialog):
    """Lista de revisión de un archivo de perfiles (CA-P09.1..P09.5).

    Constructor: ``DialogoImportarPerfiles(archivo, existentes, tema="oscuro", parent=…)``
    donde ``archivo`` es el ``ArchivoPerfiles`` ya leído (en un hilo) y ``existentes`` los
    perfiles visibles
    (``almacen.todos()``). Tras ``exec()`` aceptado: ``entradas()`` devuelve las
    ``EntradaImportacion`` para ``almacen.importar``. Reemplazar pide confirmación explícita
    (foco en «Cancelar») y solo existe frente a perfiles del usuario.
    """

    def __init__(
        self,
        archivo: ArchivoPerfiles,
        existentes: Sequence[PerfilMaquina],
        *,
        tema: str = "oscuro",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Importar perfiles de máquina"))
        self.setModal(True)
        self.resize(780, 520)
        self._existentes = tuple(existentes)
        self._usuario = sum(1 for p in self._existentes if p.origen == OrigenPerfil.USUARIO)
        self._archivo = archivo
        self._cargando = False

        capa, capa_pie, _ = hacer_desplazable(self)
        n_total = len(archivo.validos) + len(archivo.invalidos)
        if n_total == 1:
            texto_resumen = self.tr("El archivo tiene 1 perfil.")
        else:
            texto_resumen = self.tr("El archivo tiene %n perfiles.", None, n_total)
        if archivo.invalidos:
            texto_resumen += " " + self.tr("Se pueden importar {n}.").format(n=len(archivo.validos))
        self.resumen = etiqueta(texto_resumen)
        self.resumen.setAccessibleName(self.tr("Resumen del archivo"))
        capa.addWidget(self.resumen)
        capa.addWidget(
            etiqueta(
                self.tr("Todavía no se guardó nada. Elige qué perfiles quieres importar."),
                secundario=True,
            )
        )
        self.avisos = mensaje(aviso=True)
        lineas = [texto_aviso_archivo(a) for a in archivo.avisos]
        poner_mensaje(self.avisos, "\n".join(lineas) if lineas else None, aviso=True)
        capa.addWidget(self.avisos)

        self.modelo = ModeloRevisionPerfiles(self)
        self.modelo.establecer_tema(tema)
        self.tabla = TablaCopiable(self.tr("Perfiles del archivo"))
        self.tabla.setModel(self.modelo)
        self.tabla.setSelectionMode(TablaCopiable.SelectionMode.SingleSelection)
        capa.addWidget(self.tabla, 1)

        # Qué hacer con el perfil seleccionado cuando su nombre ya existe (CA-P09.3).
        self.grupo_conflicto = QGroupBox(self.tr("Este nombre ya existe"))
        self.grupo_conflicto.setAccessibleName(self.tr("Qué hacer con un nombre repetido"))
        self.radio_ambos = QRadioButton(self.tr("Conservar ambos (el importado se renombra)"))
        self.radio_reemplazar = QRadioButton(self.tr("Reemplazar el perfil que ya tengo"))
        self.radio_omitir = QRadioButton(self.tr("Omitir este perfil"))
        self.nota_conflicto = etiqueta("", secundario=True)
        self._radios = QButtonGroup(self)
        for r in (self.radio_ambos, self.radio_reemplazar, self.radio_omitir):
            self._radios.addButton(r)
        caja = QVBoxLayout(self.grupo_conflicto)
        caja.addWidget(self.radio_ambos)
        caja.addWidget(self.radio_reemplazar)
        caja.addWidget(self.radio_omitir)
        caja.addWidget(self.nota_conflicto)
        capa.addWidget(self.grupo_conflicto)
        self.grupo_conflicto.setVisible(False)

        self.error = mensaje(error=True)
        capa_pie.addWidget(self.error)  # fuera del área desplazable: siempre visible

        self.botones = QDialogButtonBox()
        self.boton_importar = QPushButton()
        self.boton_cancelar = QPushButton(self.tr("Cancelar"))
        self.botones.addButton(self.boton_importar, QDialogButtonBox.ButtonRole.AcceptRole)
        self.botones.addButton(self.boton_cancelar, QDialogButtonBox.ButtonRole.RejectRole)
        self.boton_importar.setDefault(True)
        self.boton_importar.setProperty("primario", True)
        capa_pie.addWidget(self.botones)

        self.botones.accepted.connect(self._aceptar)
        self.botones.rejected.connect(self.reject)
        self._radios.buttonClicked.connect(self._al_elegir_accion)
        self.modelo.cambiado.connect(self._actualizar)
        self.tabla.selectionModel().selectionChanged.connect(self._al_seleccionar)

        self.modelo.cargar(self._construir_filas(archivo))
        if self.modelo.rowCount():
            self.tabla.selectRow(0)
        self._actualizar()

    # --- Construcción --------------------------------------------------------------

    def _conflicto_de(self, nombre: str) -> PerfilMaquina | None:
        clave = clave_comparacion(nombre)
        for p in self._existentes:
            if clave_comparacion(p.nombre) == clave:
                return p
        return None

    def _construir_filas(self, archivo: ArchivoPerfiles) -> list[_FilaRevision]:
        filas: list[_FilaRevision] = []
        for leido in archivo.validos:
            filas.append(
                _FilaRevision(
                    leido.indice, leido.nombre, leido, None, self._conflicto_de(leido.nombre)
                )
            )
        for inv in archivo.invalidos:
            nombre = inv.nombre or self.tr("(perfil {n} sin nombre válido)").format(
                n=inv.indice + 1
            )
            filas.append(_FilaRevision(inv.indice, nombre, None, inv, marcada=False))
        filas.sort(key=lambda f: f.indice)
        return filas

    # --- Estado ----------------------------------------------------------------------

    def entradas(self) -> tuple[EntradaImportacion, ...]:
        """Perfiles elegidos con su acción, en el orden del archivo."""
        resultado: list[EntradaImportacion] = []
        for f in self.modelo.filas:
            if f.leido is None or not f.marcada or f.accion == AccionFila.OMITIR:
                continue
            if f.accion == AccionFila.REEMPLAZAR and f.conflicto is not None:
                resultado.append(
                    EntradaImportacion(f.leido, AccionImportar.REEMPLAZAR, f.conflicto.id)
                )
            else:
                resultado.append(EntradaImportacion(f.leido, AccionImportar.CONSERVAR_AMBOS))
        return tuple(resultado)

    @property
    def reemplazos(self) -> tuple[PerfilMaquina, ...]:
        """Perfiles del usuario que se sustituirían."""
        return tuple(
            f.conflicto
            for f in self.modelo.filas
            if f.marcada
            and f.accion == AccionFila.REEMPLAZAR
            and f.conflicto is not None
            and f.leido is not None
        )

    def _bloqueo(self) -> str | None:
        """V-M03: el total no puede pasar del máximo (todo o nada, CA-P09.5)."""
        entradas = self.entradas()
        nuevos = sum(1 for e in entradas if e.accion == AccionImportar.CONSERVAR_AMBOS)
        if self._usuario + nuevos > MAX_PERFILES_USUARIO:
            return texto_regla_perfil("V-M03")
        return None

    def _actualizar(self) -> None:
        n = len(self.entradas())
        texto = self.tr("Importar 1 perfil") if n == 1 else self.tr("Importar %n perfiles", None, n)
        self.boton_importar.setText(texto)
        bloqueo = self._bloqueo()
        poner_mensaje(self.error, bloqueo)
        self.boton_importar.setEnabled(n > 0 and bloqueo is None)

    def _al_seleccionar(self, _nuevo: QItemSelection, _viejo: QItemSelection) -> None:
        filas = self.tabla.selectionModel().selectedRows()
        f = self.modelo.fila(filas[0].row()) if filas else None
        self._cargando = True
        try:
            visible = f is not None and f.valida and f.conflicto is not None
            self.grupo_conflicto.setVisible(visible)
            if not visible or f is None or f.conflicto is None:
                return
            de_fabrica = f.conflicto.origen == OrigenPerfil.FABRICA
            self.radio_reemplazar.setEnabled(not de_fabrica)
            self.nota_conflicto.setText(
                self.tr(
                    "Ya existe «{nombre}» y es un perfil de fábrica: no se puede reemplazar."
                ).format(nombre=f.conflicto.nombre)
                if de_fabrica
                else self.tr("Ya tienes un perfil llamado «{nombre}».").format(
                    nombre=f.conflicto.nombre
                )
            )
            marcado = {
                AccionFila.CONSERVAR_AMBOS: self.radio_ambos,
                AccionFila.REEMPLAZAR: self.radio_reemplazar,
                AccionFila.OMITIR: self.radio_omitir,
            }[f.accion if f.marcada else AccionFila.OMITIR]
            marcado.setChecked(True)
        finally:
            self._cargando = False

    def _al_elegir_accion(self) -> None:
        if self._cargando:
            return
        filas = self.tabla.selectionModel().selectedRows()
        f = self.modelo.fila(filas[0].row()) if filas else None
        if f is None or f.conflicto is None:
            return
        if self.radio_omitir.isChecked():
            f.accion = AccionFila.OMITIR
            f.marcada = False
        elif self.radio_reemplazar.isChecked():
            f.accion = AccionFila.REEMPLAZAR
            f.marcada = True
        else:
            f.accion = AccionFila.CONSERVAR_AMBOS
            f.marcada = True
        self.modelo.refrescar(filas[0].row())

    # --- Aceptar -----------------------------------------------------------------------

    def _aceptar(self) -> None:
        reemplazos = self.reemplazos
        if reemplazos:
            nombres = "\n".join(f"• {p.nombre}" for p in reemplazos)
            texto = (
                self.tr("Se reemplazará %n perfil tuyo por el del archivo:", None, len(reemplazos))
                + "\n"
                + nombres
                + "\n\n"
                + self.tr("Esta acción no se puede deshacer.")
            )
            if not confirmar(
                self,
                self.tr("Reemplazar perfiles"),
                texto,
                self.tr("Reemplazar"),
                self.tr("Cancelar"),
            ):
                return
        self.accept()

    def ejecutar(self) -> tuple[EntradaImportacion, ...] | None:
        """Muestra el diálogo; devuelve las entradas elegidas o ``None`` si se cancela."""
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        return self.entradas()
