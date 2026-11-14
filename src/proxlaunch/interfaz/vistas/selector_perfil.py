"""Selector de perfil de máquina del formulario (RF-P05, RF-P11, docs/arquitectura/mvp3.md §6.1).

Muestra los perfiles de fábrica primero (con el texto «De fábrica») y después los del usuario,
con un resumen en lenguaje llano y la descripción del perfil elegido. Tras cualquier edición del
formulario el selector dice «<perfil> (modificado)»; si el perfil desaparece o nunca hubo uno,
«Personalizado». También aloja el panel cerrable de avisos de pistas y el de compatibilidad.
La ventana principal decide qué hacer al elegir (confirmar el reemplazo, aplicar, avisar): aquí
solo se dibuja y se emiten señales.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import ayuda
from proxlaunch.interfaz.textos import texto_resumen_perfil, tooltip_plano
from proxlaunch.interfaz.vistas.campos import boton_ayuda, etiqueta, poner_mensaje
from proxlaunch.nucleo.perfiles_maquina.modelos import OrigenPerfil, PerfilMaquina


class PanelAvisos(QFrame):
    """Panel cerrable con avisos no bloqueantes (pistas que no sirvieron, avisos de un archivo)."""

    def __init__(self, nombre_accesible: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(nombre_accesible)
        self._texto = etiqueta("")
        self._texto.setProperty("aviso", True)
        self.boton_cerrar = QPushButton(QCoreApplication.translate("PanelAvisos", "Cerrar"))
        self.boton_cerrar.setAccessibleName(
            QCoreApplication.translate("PanelAvisos", "Cerrar los avisos")
        )
        self.boton_cerrar.clicked.connect(lambda: self.mostrar([]))
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self._texto, 1)
        capa.addWidget(self.boton_cerrar, 0, Qt.AlignmentFlag.AlignTop)
        self.hide()

    def mostrar(self, textos: Sequence[str]) -> None:
        """Muestra un aviso por línea; sin textos se oculta."""
        texto = "\n".join(f"⚠ {t}" for t in textos)
        self._texto.setText(texto)
        self.setVisible(bool(texto))

    @property
    def texto(self) -> str:
        return "" if self.isHidden() else self._texto.text()


class SelectorPerfil(QGroupBox):
    """Combo de perfiles con resumen, estado «(modificado)» y paneles de avisos."""

    perfil_elegido = Signal(str)  # id del perfil que el usuario eligió en el combo
    guardar_solicitado = Signal()  # «Guardar como perfil de máquina…»
    actualizar_solicitado = Signal()  # «Guardar cambios en el perfil «X»»
    administrar_solicitado = Signal()  # «Administrar perfiles…» (avanzado)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QCoreApplication.translate("SelectorPerfil", "Perfil de máquina"), parent)
        self._perfiles: dict[str, PerfilMaquina] = {}
        self._actual: str | None = None  # id del perfil aplicado; None = personalizado
        self._modificado = False
        self._avanzado = False

        self.combo = QComboBox()
        self.combo.setAccessibleName(
            QCoreApplication.translate("SelectorPerfil", "Perfil de máquina")
        )
        self.combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.combo.setMinimumContentsLength(24)
        self.combo.activated.connect(self._al_activar)
        self._ayuda = boton_ayuda("perfil")
        self._resumen = etiqueta("", secundario=True)
        self._resumen.setAccessibleName(
            QCoreApplication.translate("SelectorPerfil", "Resumen del perfil")
        )
        self._descripcion = etiqueta("", secundario=True)
        self._descripcion.setAccessibleName(
            QCoreApplication.translate("SelectorPerfil", "Descripción del perfil")
        )

        self.boton_guardar = QPushButton(
            QCoreApplication.translate("SelectorPerfil", "Guardar como perfil…")
        )
        self.boton_guardar.setToolTip(ayuda("perfil_guardar"))
        self.boton_guardar.setAccessibleName(
            QCoreApplication.translate("SelectorPerfil", "Guardar como perfil de máquina")
        )
        self.boton_guardar.clicked.connect(self.guardar_solicitado)
        self.boton_actualizar = QPushButton()
        self.boton_actualizar.clicked.connect(self.actualizar_solicitado)
        self.boton_actualizar.hide()
        self.boton_administrar = QPushButton(
            QCoreApplication.translate("SelectorPerfil", "Administrar perfiles…")
        )
        self.boton_administrar.setAccessibleName(
            QCoreApplication.translate("SelectorPerfil", "Administrar perfiles de máquina")
        )
        self.boton_administrar.clicked.connect(self.administrar_solicitado)
        self.boton_administrar.hide()

        # Avisos de pistas (cerrable) y compatibilidad (se recalcula, no se cierra).
        self._panel_avisos = PanelAvisos(
            QCoreApplication.translate("SelectorPerfil", "Avisos del perfil")
        )

        self._compat_titulo = QLabel(
            QCoreApplication.translate("SelectorPerfil", "Compatibilidad del perfil")
        )
        fuente = self._compat_titulo.font()
        fuente.setBold(True)
        self._compat_titulo.setFont(fuente)
        self._compat_titulo.hide()
        self._compat_errores = etiqueta("")
        self._compat_errores.setProperty("error", True)
        self._compat_errores.setAccessibleName(
            QCoreApplication.translate("SelectorPerfil", "Errores de compatibilidad del perfil")
        )
        self._compat_errores.hide()
        self._compat_avisos = etiqueta("")
        self._compat_avisos.setProperty("aviso", True)
        self._compat_avisos.setAccessibleName(
            QCoreApplication.translate("SelectorPerfil", "Avisos de compatibilidad del perfil")
        )
        self._compat_avisos.hide()

        fila = QHBoxLayout()
        fila.addWidget(self.combo, 1)
        fila.addWidget(self._ayuda)
        botones = QHBoxLayout()
        botones.addWidget(self.boton_guardar)
        botones.addWidget(self.boton_actualizar)
        botones.addWidget(self.boton_administrar)
        botones.addStretch(1)
        capa = QVBoxLayout(self)
        capa.setSpacing(4)
        capa.addLayout(fila)
        capa.addWidget(self._resumen)
        capa.addWidget(self._descripcion)
        capa.addWidget(self._panel_avisos)
        capa.addWidget(self._compat_titulo)
        capa.addWidget(self._compat_errores)
        capa.addWidget(self._compat_avisos)
        capa.addLayout(botones)
        self.establecer_perfiles((), None)

    # --- Perfiles y estado ---------------------------------------------------------------

    def establecer_perfiles(self, perfiles: Sequence[PerfilMaquina], actual_id: str | None) -> None:
        """Recarga la lista (fábrica primero). Si ``actual_id`` ya no existe queda Personalizado."""
        self._perfiles = {p.id: p for p in perfiles}
        self._actual = actual_id if actual_id in self._perfiles else None
        self._reconstruir()

    def _texto_perfil(self, p: PerfilMaquina) -> str:
        if p.origen == OrigenPerfil.FABRICA:
            return QCoreApplication.translate("SelectorPerfil", "{nombre} — De fábrica").format(
                nombre=p.nombre
            )
        return p.nombre

    def _reconstruir(self) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(QCoreApplication.translate("SelectorPerfil", "Personalizado"), None)
        for p in self._perfiles.values():
            self.combo.addItem(self._texto_perfil(p), p.id)
            tip = texto_resumen_perfil(p.config)
            if p.descripcion:
                tip += "\n" + p.descripcion
            self.combo.setItemData(
                self.combo.count() - 1, tooltip_plano(tip), Qt.ItemDataRole.ToolTipRole
            )
        self.combo.blockSignals(False)
        self._refrescar()

    def _refrescar(self) -> None:
        """Texto del combo, resumen y descripción según el perfil aplicado y si está modificado."""
        idx = max(self.combo.findData(self._actual), 0)
        for i in range(self.combo.count()):
            dato = self.combo.itemData(i)
            base = (
                QCoreApplication.translate("SelectorPerfil", "Personalizado")
                if dato is None
                else self._texto_perfil(self._perfiles[dato])
            )
            if i == idx and self._modificado and self._actual is not None:
                base = QCoreApplication.translate("SelectorPerfil", "{perfil} (modificado)").format(
                    perfil=base
                )
            self.combo.setItemText(i, base)
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        perfil = self._perfiles.get(self._actual) if self._actual else None
        if perfil is None:
            self._resumen.setText("")
            self._descripcion.setText("")
        else:
            self._resumen.setText(texto_resumen_perfil(perfil.config))
            self._descripcion.setText(perfil.descripcion)
        self._resumen.setVisible(bool(self._resumen.text()))
        self._descripcion.setVisible(bool(self._descripcion.text()))
        puede_actualizar = (
            perfil is not None and perfil.origen == OrigenPerfil.USUARIO and self._modificado
        )
        if puede_actualizar and perfil is not None:
            self.boton_actualizar.setText(
                QCoreApplication.translate(
                    "SelectorPerfil", "Guardar cambios en el perfil «{nombre}»"
                ).format(nombre=perfil.nombre)
            )
            self.boton_actualizar.setAccessibleName(self.boton_actualizar.text())
        self.boton_actualizar.setVisible(puede_actualizar)

    @property
    def perfil_actual_id(self) -> str | None:
        """Id del perfil aplicado (``None`` = personalizado)."""
        return self._actual

    @property
    def modificado(self) -> bool:
        return self._modificado

    @property
    def texto_combo(self) -> str:
        """Texto que muestra el combo ahora (con «(modificado)» si corresponde)."""
        return self.combo.currentText()

    def marcar_aplicado(self, id_perfil: str | None) -> None:
        """El perfil ``id_perfil`` quedó aplicado al formulario (sin modificar)."""
        self._actual = id_perfil if id_perfil in self._perfiles else None
        self._modificado = False
        self._refrescar()

    def marcar_modificado(self, modificado: bool) -> None:
        """El formulario ya no coincide con el perfil aplicado (CA-P05.8)."""
        if modificado == self._modificado:
            return
        self._modificado = modificado
        self._refrescar()

    def restaurar(self) -> None:
        """Vuelve a mostrar el perfil aplicado (el usuario canceló el cambio)."""
        self._refrescar()

    def bloquear(self, bloqueado: bool) -> None:
        """Con un lote en ejecución el selector está deshabilitado (§6.1)."""
        self.combo.setEnabled(not bloqueado)
        self.boton_guardar.setEnabled(not bloqueado)
        self.boton_actualizar.setEnabled(not bloqueado)
        self.boton_administrar.setEnabled(not bloqueado)

    def establecer_modo(self, avanzado: bool) -> None:
        """«Administrar perfiles…» solo se ve en modo avanzado (CA-P11.1)."""
        self._avanzado = avanzado
        self.boton_administrar.setVisible(avanzado)

    # --- Paneles de avisos ---------------------------------------------------------------

    def mostrar_avisos(self, textos: Sequence[str]) -> None:
        """Panel cerrable con los avisos de pistas que no sirvieron (vacío = se oculta)."""
        self._panel_avisos.mostrar(textos)

    @property
    def texto_avisos(self) -> str:
        return self._panel_avisos.texto

    def mostrar_compatibilidad(self, errores: Sequence[str], avisos: Sequence[str]) -> None:
        """Panel «Compatibilidad del perfil»: errores y avisos con este servidor y versión."""
        poner_mensaje(self._compat_errores, "\n".join(f"✕ {t}" for t in errores))
        poner_mensaje(self._compat_avisos, "\n".join(f"⚠ {t}" for t in avisos), aviso=True)
        self._compat_titulo.setVisible(bool(errores or avisos))

    @property
    def texto_compatibilidad(self) -> str:
        partes = [w.text() for w in (self._compat_errores, self._compat_avisos) if not w.isHidden()]
        return "\n".join(partes)

    # --- Señales --------------------------------------------------------------------------

    def _al_activar(self, indice: int) -> None:
        dato = self.combo.itemData(indice)
        if dato is None:
            self.restaurar()  # «Personalizado» no es un perfil que se pueda aplicar
            return
        self.perfil_elegido.emit(str(dato))
