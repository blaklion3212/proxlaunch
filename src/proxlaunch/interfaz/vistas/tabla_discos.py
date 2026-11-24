"""Tabla de discos de la MV (RF-16): una fila por disco, con opciones que se deshabilitan
según el bus y el controlador (CA-16.4)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import ayuda
from proxlaunch.interfaz.textos import texto_problema
from proxlaunch.interfaz.vistas.campos import mensaje, poner_mensaje, poner_propiedad
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.modelos.inventario import Storage
from proxlaunch.nucleo.modelos.vm import Bus, ControladorScsi, Disco, FormatoDisco
from proxlaunch.nucleo.validacion import (
    Problema,
    Severidad,
    formatos_permitidos,
    opciones_permitidas,
)
from proxlaunch.nucleo.valores_defecto import TAMANO_DISCO_GIB, disco_por_defecto

# Columnas de la rejilla.
_C_INDICE, _C_STORAGE, _C_TAMANO, _C_BUS, _C_FORMATO, _C_DISCARD, _C_SSD, _C_IOTHREAD = range(8)
_C_QUITAR = 8
# Conexiones que no existen en un servidor ARM64 (D2, RF-D2.7): se ocultan de la lista.
_BUSES_SOLO_X86 = (Bus.SATA, Bus.IDE)


def entero_o_cero(texto: str) -> int:
    """Convierte el texto a entero; si no lo es devuelve 0, que la validación rechaza."""
    try:
        return int(texto.strip())
    except ValueError:
        return 0


def texto_storage(s: Storage) -> str:
    """«local-lvm (lvmthin, 150 GiB libres)» (CA-11.2); los inactivos llevan «Inactivo»."""
    texto = QCoreApplication.translate("TablaDiscos", "{id} ({tipo}, {libre:g} GiB libres)").format(
        id=s.id, tipo=s.tipo, libre=s.libre_gib
    )
    if not s.activo:
        texto += " — " + QCoreApplication.translate("TablaDiscos", "Inactivo")
    return texto


def texto_ausente(valor: str) -> str:
    """«x (no existe)»: el valor cargado de un archivo que este servidor no tiene (CA-G04.3)."""
    return QCoreApplication.translate("TablaDiscos", "{id} (no existe)").format(id=valor)


class _FilaDisco:
    """Widgets de una fila de la tabla y las preferencias del usuario sobre sus opciones."""

    def __init__(self) -> None:
        self.indice = QLabel()
        self.indice.setProperty("mono", True)
        self.storage = QComboBox()
        self.storage.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.storage.setMinimumContentsLength(18)
        self.tamano = QLineEdit(str(TAMANO_DISCO_GIB))
        self.tamano.setMaximumWidth(80)
        self.bus = QComboBox()
        for bus, texto in (
            (Bus.SCSI, "SCSI"),
            (Bus.VIRTIO, "VirtIO"),
            (Bus.SATA, "SATA"),
            (Bus.IDE, "IDE"),
        ):
            self.bus.addItem(texto, bus)
        self.formato = QComboBox()
        self.discard = QCheckBox()
        self.ssd = QCheckBox()
        self.iothread = QCheckBox()
        self.quitar = QPushButton(QCoreApplication.translate("TablaDiscos", "Quitar"))
        # Lo que el usuario quiere, aunque la opción esté deshabilitada ahora.
        self.pref_discard = True
        self.pref_ssd = True
        self.pref_iothread = True
        # Selección pedida que no existe en el nodo actual (el aviso debe sobrevivir a recargas).
        self.perdido: str | None = None
        # Valor cargado de un lote o perfil que el nodo no tiene: se muestra «x (no existe)»
        # con error hasta que el usuario elija otro (nunca se sustituye en silencio).
        self.ausente: str | None = None

    def widgets(self) -> list[tuple[int, QWidget]]:
        return [
            (_C_INDICE, self.indice),
            (_C_STORAGE, self.storage),
            (_C_TAMANO, self.tamano),
            (_C_BUS, self.bus),
            (_C_FORMATO, self.formato),
            (_C_DISCARD, self.discard),
            (_C_SSD, self.ssd),
            (_C_IOTHREAD, self.iothread),
            (_C_QUITAR, self.quitar),
        ]

    def avanzados(self) -> list[QWidget]:
        return [self.bus, self.formato, self.discard, self.ssd, self.iothread]


class TablaDiscos(QWidget):
    """Lista editable de discos. Emite ``cambiado`` ante cualquier modificación."""

    cambiado = Signal()
    # Posición del disco que el usuario va a quitar; se emite antes de quitarlo y de renumerar.
    disco_quitado = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filas: list[_FilaDisco] = []
        self._storages: dict[str, Storage] = {}
        self._recordado: str | None = None  # storage recordado del servidor (RF-O05)
        self._primero_importado = False  # el primer disco sale de una imagen (RF-O17)
        self._arm = False  # el servidor elegido es ARM64: sin SATA ni IDE
        self._ctrl = ControladorScsi.VIRTIO_SINGLE
        self._avanzado = False
        self._avanzados: list[QWidget] = []  # registro de widgets que solo ve el modo avanzado
        self._rejilla = QGridLayout()
        self._rejilla.setHorizontalSpacing(8)
        self._rejilla.setVerticalSpacing(4)
        self._cabeceras: dict[int, QLabel] = {}
        for col, texto, clave in (
            (_C_INDICE, QCoreApplication.translate("TablaDiscos", "Disco"), None),
            (
                _C_STORAGE,
                QCoreApplication.translate("TablaDiscos", "Almacenamiento"),
                "almacenamiento",
            ),
            (_C_TAMANO, QCoreApplication.translate("TablaDiscos", "Tamaño (GiB)"), "tamano"),
            (_C_BUS, QCoreApplication.translate("TablaDiscos", "Conexión (bus)"), "bus"),
            (_C_FORMATO, QCoreApplication.translate("TablaDiscos", "Formato"), "formato"),
            (_C_DISCARD, QCoreApplication.translate("TablaDiscos", "Discard"), "discard"),
            (_C_SSD, QCoreApplication.translate("TablaDiscos", "SSD"), "ssd"),
            (_C_IOTHREAD, QCoreApplication.translate("TablaDiscos", "IO Thread"), "iothread"),
        ):
            lbl = QLabel(texto)
            lbl.setProperty("secundario", True)
            if clave:
                lbl.setToolTip(ayuda(clave))
            self._cabeceras[col] = lbl
            self._rejilla.addWidget(lbl, 0, col)
        self._avanzados.extend(self._cabeceras[c] for c in (_C_BUS, _C_FORMATO))
        self._avanzados.extend(self._cabeceras[c] for c in (_C_DISCARD, _C_SSD, _C_IOTHREAD))
        self._rejilla.setColumnStretch(_C_STORAGE, 1)

        self._agregar = QPushButton(QCoreApplication.translate("TablaDiscos", "Agregar disco"))
        self._agregar.clicked.connect(self._al_agregar)
        self._errores = mensaje(error=True)
        self._avisos = mensaje(aviso=True)
        self._aviso_nodo = mensaje(aviso=True)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addLayout(self._rejilla)
        capa.addWidget(self._agregar, 0, Qt.AlignmentFlag.AlignLeft)
        capa.addWidget(self._errores)
        capa.addWidget(self._avisos)
        capa.addWidget(self._aviso_nodo)
        self._aplicar_visibilidad()

    # --- API pública ------------------------------------------------------------------

    @property
    def widgets_avanzados(self) -> list[QWidget]:
        return list(self._avanzados)

    def establecer_avanzado(self, avanzado: bool) -> None:
        """Solo cambia la visibilidad; los valores se conservan (CA-24.5)."""
        self._avanzado = avanzado
        self._aplicar_visibilidad()

    def establecer_storage_recordado(self, storage: str | None) -> None:
        """Almacenamiento recordado del servidor: es el de partida de los discos nuevos."""
        self._recordado = storage

    def reemplazar_storage(self, viejo: str | None, nuevo: str) -> None:
        """Cambia a ``nuevo`` los discos que usaban ``viejo`` (el de partida) si existe."""
        if viejo == nuevo or nuevo not in self._storages:
            return
        for f in self._filas:
            if f.storage.currentData() == viejo:
                f.storage.setCurrentIndex(f.storage.findData(nuevo))

    def establecer_primero_importado(self, activo: bool) -> None:
        """Con una imagen importada, el tamaño del primer disco es el de la imagen (CA-O17.1)."""
        self._primero_importado = activo
        self._aplicar_importado()

    def _aplicar_importado(self) -> None:
        for i, f in enumerate(self._filas):
            importado = self._primero_importado and i == 0
            f.tamano.setEnabled(not importado)
            f.tamano.setToolTip(
                QCoreApplication.translate(
                    "TablaDiscos",
                    "Este disco es una copia de la imagen que elegiste: tiene el tamaño de la "
                    "imagen. Para hacerlo más grande usa «Ampliar el disco» en el origen.",
                )
                if importado
                else ""
            )

    def establecer_arquitectura(self, arq: Arquitectura) -> None:
        """En un servidor ARM64 no existen SATA ni IDE: se ocultan de la lista de conexiones.

        Solo se ocultan opciones; el valor de un disco no cambia aquí (lo adapta el formulario
        con V-D08 y avisa), así que un disco cargado de un lote guardado no se pierde en silencio.
        """
        arm = arq == Arquitectura.AARCH64
        if arm == self._arm:
            return
        self._arm = arm
        for f in self._filas:
            self._aplicar_arquitectura(f)

    def _aplicar_arquitectura(self, f: _FilaDisco) -> None:
        modelo = cast(QStandardItemModel, f.bus.model())
        vista = cast(QListView, f.bus.view())
        for bus in _BUSES_SOLO_X86:
            posicion = f.bus.findData(bus)
            if posicion < 0:
                continue
            vista.setRowHidden(posicion, self._arm)
            item = modelo.item(posicion)
            if item is not None:
                item.setEnabled(not self._arm)

    def establecer_controlador(self, ctrl: ControladorScsi) -> None:
        self._ctrl = ctrl
        for f in self._filas:
            self._refrescar_opciones(f)
        self._renumerar()

    def establecer_storages(self, storages: Sequence[Storage]) -> list[str]:
        """Recarga los almacenamientos del nodo. Devuelve los que ya no existen (CA-11.7)."""
        self._storages = {s.id: s for s in storages}
        perdidos: list[str] = []
        for f in self._filas:
            previo = f.storage.currentData() or f.perdido
            self._llenar_storage(f)
            idx = f.storage.findData(previo) if previo else -1
            existente = self._storages.get(str(previo)) if previo else None
            if idx >= 0 and existente is not None and existente.activo:
                f.storage.setCurrentIndex(idx)
                f.perdido = None
                if f.ausente == previo:
                    f.ausente = None
            elif idx >= 0 and existente is None and previo == f.ausente:
                # El valor cargado sigue sin existir en este nodo: se sigue mostrando.
                f.storage.setCurrentIndex(idx)
                f.perdido = str(previo)
                perdidos.append(str(previo))
            else:
                f.storage.setCurrentIndex(-1)
                f.perdido = str(previo) if previo else None
                if previo:
                    perdidos.append(str(previo))
            self._refrescar_formato(f)
        self.cambiado.emit()
        return perdidos

    def establecer_discos(
        self, discos: Sequence[Disco], *, conservar_ausentes: bool = False
    ) -> None:
        """Sustituye las filas por los discos dados.

        Con ``conservar_ausentes`` (carga de un lote o perfil) un almacenamiento que el nodo
        no tiene se muestra como «x (no existe)» y sigue siendo el valor del disco, de modo que
        la validación lo marca y no se crea nada hasta que el usuario elija otro (CA-G04.3).
        Sin él (comportamiento de siempre) la selección queda vacía.
        """
        for f in list(self._filas):
            self._quitar_fila(f, emitir=False)
        for d in discos:
            self._nueva_fila(d, conservar_ausente=conservar_ausentes)
        self._renumerar()
        self.cambiado.emit()

    def establecer_bus_primero(self, bus: Bus) -> None:
        """Pone el bus del primer disco (lo usa el asistente de SO); no toca los demás."""
        if not self._filas:
            return
        f = self._filas[0]
        idx = f.bus.findData(bus)
        if idx >= 0 and f.bus.currentIndex() != idx:
            f.bus.setCurrentIndex(idx)  # dispara _al_cambiar_bus: opciones, etiquetas y cambiado

    def tamanos_no_numericos(self) -> list[str]:
        """Etiquetas («scsi0»…) de los discos cuyo tamaño escrito no es un número entero."""
        malos: list[str] = []
        for f in self._filas:
            try:
                int(f.tamano.text().strip())
            except ValueError:
                malos.append(f.indice.text())
        return malos

    def valores_ausentes(self) -> list[str]:
        """Almacenamientos cargados que el nodo actual no tiene y siguen sin reemplazar."""
        return list(dict.fromkeys(f.ausente for f in self._filas if f.ausente))

    def agregar_disco(self, disco: Disco | None = None) -> None:
        """Añade un disco (por defecto el de la sección 5 en el mejor almacenamiento)."""
        if disco is None:
            from proxlaunch.nucleo.valores_defecto import storage_disco_por_defecto

            disco = disco_por_defecto(
                storage_disco_por_defecto(list(self._storages.values()), self._recordado) or ""
            )
        self._nueva_fila(disco)
        self._renumerar()
        self.cambiado.emit()

    def discos(self) -> list[Disco]:
        """Los discos tal como están en la tabla (texto no numérico -> tamaño 0)."""
        resultado: list[Disco] = []
        for f in self._filas:
            resultado.append(
                Disco(
                    storage=str(f.storage.currentData() or ""),
                    tamano_gib=entero_o_cero(f.tamano.text()),
                    bus=Bus(f.bus.currentData()),
                    formato=FormatoDisco(f.formato.currentData() or FormatoDisco.AUTO),
                    discard=f.discard.isChecked(),
                    ssd=f.ssd.isChecked(),
                    iothread=f.iothread.isChecked(),
                )
            )
        return resultado

    def etiquetas_discos(self) -> list[str]:
        """Etiquetas «scsi0», «virtio0»... en el mismo orden que ``discos()``."""
        return [f.indice.text() for f in self._filas]

    @staticmethod
    def etiquetas_para(discos: Sequence[Disco]) -> list[str]:
        """Etiquetas «scsi0»... de una lista de discos (p. ej. tras el asistente de SO)."""
        cuenta: dict[Bus, int] = {}
        etiquetas: list[str] = []
        for d in discos:
            n = cuenta.get(d.bus, 0)
            cuenta[d.bus] = n + 1
            etiquetas.append(f"{d.bus}{n}")
        return etiquetas

    def habilitar(self, habilitado: bool) -> None:
        self.setEnabled(habilitado)

    def aplicar_problemas(self, problemas: Sequence[Problema]) -> None:
        """Muestra los errores junto a la tabla y marca los tamaños inválidos."""
        etiquetas = self.etiquetas_discos()
        errores: list[str] = []
        avisos: list[str] = []
        con_error_tamano: set[int] = set()
        for p in problemas:
            if p.campo == "discos":  # regla de la lista completa (V-07.sindisco)
                errores.append(texto_problema(p))
                continue
            if not p.campo.startswith("discos["):
                continue
            try:
                i = int(p.campo[len("discos[") : p.campo.index("]")])
            except ValueError:
                continue
            if i >= len(etiquetas):
                continue
            linea = f"{etiquetas[i]}: {texto_problema(p)}"
            if p.severidad == Severidad.ERROR:
                errores.append(linea)
                if p.campo.endswith(".tamano_gib"):
                    con_error_tamano.add(i)
            else:
                avisos.append(linea)
        for i, f in enumerate(self._filas):
            poner_propiedad(f.tamano, "invalido", i in con_error_tamano)
        poner_mensaje(self._errores, "\n".join(dict.fromkeys(errores)))
        poner_mensaje(self._avisos, "\n".join(dict.fromkeys(avisos)), aviso=True)

    def mostrar_aviso_nodo(self, texto: str | None) -> None:
        poner_mensaje(self._aviso_nodo, texto, aviso=True)

    # --- Internos ---------------------------------------------------------------------

    def _aplicar_visibilidad(self) -> None:
        for w in self._avanzados:
            w.setVisible(self._avanzado)

    def _llenar_storage(self, f: _FilaDisco) -> None:
        f.storage.blockSignals(True)
        f.storage.clear()
        f.storage.setPlaceholderText(
            QCoreApplication.translate("TablaDiscos", "Elige un almacenamiento")
        )
        for s in self._storages.values():
            f.storage.addItem(texto_storage(s), s.id)
            if not s.activo:
                cast(QStandardItemModel, f.storage.model()).item(f.storage.count() - 1).setEnabled(
                    False
                )
        if f.ausente and f.ausente not in self._storages:
            f.storage.addItem(texto_ausente(f.ausente), f.ausente)
            cast(QStandardItemModel, f.storage.model()).item(f.storage.count() - 1).setEnabled(
                False
            )
        f.storage.blockSignals(False)

    def _nueva_fila(self, disco: Disco, *, conservar_ausente: bool = False) -> None:
        f = _FilaDisco()
        if conservar_ausente and disco.storage and disco.storage not in self._storages:
            f.ausente = disco.storage
        self._llenar_storage(f)
        idx = f.storage.findData(disco.storage)
        f.storage.setCurrentIndex(idx)
        f.tamano.setText(str(disco.tamano_gib))
        f.bus.setCurrentIndex(max(f.bus.findData(disco.bus), 0))
        f.pref_discard, f.pref_ssd, f.pref_iothread = disco.discard, disco.ssd, disco.iothread
        self._refrescar_formato(f, disco.formato)
        self._refrescar_opciones(f)
        # Conexiones.
        f.storage.currentIndexChanged.connect(lambda _i, fila=f: self._al_cambiar_storage(fila))
        f.tamano.textEdited.connect(lambda _t: self.cambiado.emit())
        f.bus.currentIndexChanged.connect(lambda _i, fila=f: self._al_cambiar_bus(fila))
        f.formato.currentIndexChanged.connect(lambda _i: self.cambiado.emit())
        f.discard.toggled.connect(lambda v, fila=f: self._al_marcar(fila, "discard", v))
        f.ssd.toggled.connect(lambda v, fila=f: self._al_marcar(fila, "ssd", v))
        f.iothread.toggled.connect(lambda v, fila=f: self._al_marcar(fila, "iothread", v))
        f.quitar.clicked.connect(lambda _c=False, fila=f: self._al_quitar(fila))
        self._aplicar_arquitectura(f)
        self._filas.append(f)
        fila_rejilla = len(self._filas)
        for col, w in f.widgets():
            self._rejilla.addWidget(w, fila_rejilla, col)
        for w in f.avanzados():
            self._avanzados.append(w)
            w.setVisible(self._avanzado)
        self._actualizar_quitar()
        self._aplicar_importado()

    def _quitar_fila(self, f: _FilaDisco, *, emitir: bool = True) -> None:
        self._filas.remove(f)
        for _col, w in f.widgets():
            self._rejilla.removeWidget(w)
            if w in self._avanzados:
                self._avanzados.remove(w)
            w.deleteLater()
        # Recoloca las filas restantes.
        for n, resto in enumerate(self._filas, start=1):
            for col, w in resto.widgets():
                self._rejilla.addWidget(w, n, col)
        self._actualizar_quitar()
        self._aplicar_importado()
        if emitir:
            self._renumerar()
            self.cambiado.emit()

    def _actualizar_quitar(self) -> None:
        # Con disco debe haber al menos uno (para no tener disco existe «Sin disco»).
        for f in self._filas:
            f.quitar.setEnabled(len(self._filas) > 1)

    def _renumerar(self) -> None:
        cuenta: dict[Bus, int] = {}
        for f in self._filas:
            bus = Bus(f.bus.currentData())
            n = cuenta.get(bus, 0)
            cuenta[bus] = n + 1
            f.indice.setText(f"{bus}{n}")

    def _al_agregar(self) -> None:
        self.agregar_disco()

    def _al_quitar(self, f: _FilaDisco) -> None:
        if len(self._filas) > 1:
            self.disco_quitado.emit(self._filas.index(f))
            self._quitar_fila(f)

    def _al_cambiar_storage(self, f: _FilaDisco) -> None:
        if f.storage.currentIndex() >= 0:
            f.perdido = None  # el usuario eligió otro valor
            if f.storage.currentData() != f.ausente:
                f.ausente = None
        self._refrescar_formato(f)
        self.cambiado.emit()

    def _al_cambiar_bus(self, f: _FilaDisco) -> None:
        self._refrescar_opciones(f)
        self._renumerar()
        self.cambiado.emit()

    def _al_marcar(self, f: _FilaDisco, nombre: str, valor: bool) -> None:
        # Solo se recuerda lo que el usuario cambia con la casilla habilitada.
        if getattr(f, nombre).isEnabled():
            setattr(f, f"pref_{nombre}", valor)
        self.cambiado.emit()

    def _refrescar_formato(self, f: _FilaDisco, preferido: FormatoDisco | None = None) -> None:
        """Formato automático en raw-only (CA-16.5) o elegible raw/qcow2 en dir/NFS."""
        previo = preferido if preferido is not None else f.formato.currentData()
        s = self._storages.get(str(f.storage.currentData() or ""))
        permitidos = formatos_permitidos(s.tipo) if s is not None else (FormatoDisco.RAW,)
        f.formato.blockSignals(True)
        f.formato.clear()
        if len(permitidos) > 1:
            f.formato.addItem(
                QCoreApplication.translate("TablaDiscos", "Automático (qcow2)"), FormatoDisco.AUTO
            )
            f.formato.addItem("raw", FormatoDisco.RAW)
            f.formato.addItem("qcow2", FormatoDisco.QCOW2)
            f.formato.setEnabled(True)
            f.formato.setToolTip(ayuda("formato"))
            idx = f.formato.findData(previo) if previo is not None else 0
            f.formato.setCurrentIndex(max(idx, 0))
        else:
            f.formato.addItem(
                QCoreApplication.translate("TablaDiscos", "(automático, raw)"), FormatoDisco.AUTO
            )
            f.formato.setEnabled(False)
            f.formato.setToolTip(texto_problema(Problema("", "V-09", Severidad.ERROR, {})))
        f.formato.blockSignals(False)

    def _refrescar_opciones(self, f: _FilaDisco) -> None:
        """Deshabilita (y desmarca) las opciones inválidas explicando el motivo (CA-16.4)."""
        bus = Bus(f.bus.currentData())
        op = opciones_permitidas(Disco(storage="", tamano_gib=1, bus=bus), self._ctrl)
        for nombre, permitido, regla in (
            ("discard", op.discard, "V-13"),
            ("ssd", op.ssd, "V-12"),
            ("iothread", op.iothread, "V-11"),
        ):
            casilla: QCheckBox = getattr(f, nombre)
            casilla.blockSignals(True)
            casilla.setEnabled(permitido)
            if permitido:
                casilla.setChecked(getattr(f, f"pref_{nombre}"))
                casilla.setToolTip(ayuda(nombre))
            else:
                casilla.setChecked(False)
                casilla.setToolTip(texto_problema(Problema("", regla, Severidad.ERROR, {})))
            casilla.blockSignals(False)
