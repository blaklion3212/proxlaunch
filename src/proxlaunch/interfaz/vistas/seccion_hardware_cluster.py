"""Sección «Hardware del clúster» del formulario (RF-D3.1, RF-D3.2, RF-D3.4, RF-D0.3).

Plegada y apagada por defecto: con la casilla sin marcar no hay ninguna petición de hardware
(``valor()`` devuelve ``None``, como en 0.8.0). Al activarla por primera vez emite
``pide_mapeos``: la ventana lee los mapeos del clúster en un trabajador y responde con
``establecer_info``. Se pueden añadir hasta 16 tarjetas PCI y 5 dispositivos USB; cada tarjeta
lleva sus opciones (PCIe, gráfica principal, ROM y, con Proxmox 9.1 o posterior, mantener el
controlador) y cada USB, «USB 3». Solo se ofrecen los mapeos que lista el servidor: el
identificador va validado a la petición y nunca se escribe a mano.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import (
    texto_estado_opcion,
    texto_opcion_restablecida,
    tooltip_plano,
)
from proxlaunch.interfaz.textos_d import (
    texto_hardware_sin_leer,
    texto_intro_hardware_cluster,
    texto_leyendo_mapeos,
    texto_mapeo_con_detalle,
    texto_mapeo_no_listado,
    texto_mapeo_sin_permiso,
    texto_maximo_dispositivos,
    texto_pcie_no_en_arm,
    texto_problema_d,
    texto_sin_mapeos_de,
)
from proxlaunch.interfaz.vistas.campos import boton_ayuda, etiqueta, mensaje, poner_mensaje
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import (
    MAX_PCI,
    MAX_USB,
    AsignacionPCI,
    AsignacionUSB,
    HardwareCluster,
    InfoHardwareCluster,
    Mapeo,
    TipoMapeo,
)
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, OpcionD
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.origen.permisos import estado_mapeo
from proxlaunch.nucleo.validacion import Problema, Severidad

_CAMPOS_PROPIOS = ("hardware_cluster", "hostpci", "usb")


class _FilaDispositivo(QWidget):
    """Una tarjeta PCI o un dispositivo USB: mapeo, opciones y botón para quitarla."""

    cambiado = Signal()
    quitar = Signal(object)

    def __init__(self, tipo: TipoMapeo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tipo = tipo
        self._mapeo_cargado: str | None = None  # mapeo de un lote guardado aún sin listar
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(2)
        # Primera línea: el desplegable con todo el ancho y «Quitar». Segunda: las opciones.
        capa = QHBoxLayout()
        capa.setContentsMargins(0, 0, 0, 0)
        raiz.addLayout(capa)
        opciones = QHBoxLayout()
        opciones.setContentsMargins(24, 0, 0, 0)  # sangrada bajo el desplegable
        self.combo = QComboBox()
        self.combo.setMinimumContentsLength(24)
        self.combo.setAccessibleName(
            QCoreApplication.translate("SeccionHardwareCluster", "Tarjeta PCI del clúster")
            if tipo == TipoMapeo.PCI
            else QCoreApplication.translate("SeccionHardwareCluster", "USB del clúster")
        )
        capa.addWidget(self.combo, 1)
        self.chk_pcie = QCheckBox(
            QCoreApplication.translate("SeccionHardwareCluster", "Es una tarjeta PCIe")
        )
        self.chk_x_vga = QCheckBox(
            QCoreApplication.translate("SeccionHardwareCluster", "Es la gráfica principal")
        )
        self.chk_rombar = QCheckBox(
            QCoreApplication.translate("SeccionHardwareCluster", "Mostrar la ROM")
        )
        self.chk_rombar.setChecked(True)
        self.chk_driver = QCheckBox(
            QCoreApplication.translate(
                "SeccionHardwareCluster", "Mantener el controlador del servidor"
            )
        )
        self.chk_usb3 = QCheckBox(QCoreApplication.translate("SeccionHardwareCluster", "USB 3"))
        self.ayudas: list[QToolButton] = []
        if tipo == TipoMapeo.PCI:
            for chk, clave in (
                (self.chk_pcie, "pcie"),
                (self.chk_x_vga, "gpu_principal"),
                (self.chk_rombar, "rombar"),
                (self.chk_driver, "driver_keep"),
            ):
                opciones.addWidget(chk)
                ayuda = boton_ayuda(clave)
                opciones.addWidget(ayuda)
                self.ayudas.append(ayuda)
            opciones.addStretch(1)
            raiz.addLayout(opciones)
            self.chk_usb3.hide()
        else:
            for chk in (self.chk_pcie, self.chk_x_vga, self.chk_rombar, self.chk_driver):
                chk.hide()
            opciones.addWidget(self.chk_usb3)
            opciones.addWidget(boton_ayuda("usb3"))
            opciones.addStretch(1)
            raiz.addLayout(opciones)
        self.boton_quitar = QPushButton(
            QCoreApplication.translate("SeccionHardwareCluster", "Quitar")
        )
        self.boton_quitar.setAutoDefault(False)
        capa.addWidget(self.boton_quitar)
        self.combo.currentIndexChanged.connect(lambda _i: self._cambio())
        for chk in (self.chk_pcie, self.chk_x_vga, self.chk_rombar, self.chk_driver, self.chk_usb3):
            chk.toggled.connect(lambda _m: self._cambio())
        self.boton_quitar.clicked.connect(lambda: self.quitar.emit(self))

    def _cambio(self) -> None:
        self._mapeo_cargado = None
        self.cambiado.emit()

    def mapeo(self) -> str | None:
        """El mapeo elegido (``None`` si no hay ninguno o el elemento está deshabilitado)."""
        valor = self.combo.currentData()
        return str(valor) if valor else None

    def llenar(
        self,
        mapeos: Sequence[Mapeo] | None,
        permisos: PermisosEfectivos | None,
        elegido: str | None,
    ) -> None:
        """Rellena el desplegable conservando lo elegido. Un mapeo elegido que el servidor no
        lista se muestra como «x (no existe)»: nunca se cambia en silencio (V-D51 lo marca)."""
        previo = elegido or self.mapeo() or self._mapeo_cargado
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(
            QCoreApplication.translate("SeccionHardwareCluster", "Elige un mapeo"), None
        )
        listados: set[str] = set()
        modelo = cast(QStandardItemModel, self.combo.model())
        for m in mapeos or ():
            listados.add(m.id)
            nodos = sorted(m.nodos())
            texto = texto_mapeo_con_detalle(m.id, m.descripcion, nodos, migrable=m.migrable_en_vivo)
            permitido = estado_mapeo(permisos, self.tipo, m.id)
            if permitido is False:
                motivo = texto_mapeo_sin_permiso(self.tipo, m.id)
                texto = f"{texto} — {motivo}"
            self.combo.addItem(texto, m.id)
            fila = self.combo.count() - 1
            if permitido is False:
                modelo.item(fila).setEnabled(False)
                # El identificador del mapeo viene del servidor y Qt interpreta HTML en tooltips.
                self.combo.setItemData(fila, tooltip_plano(motivo), Qt.ItemDataRole.ToolTipRole)
        if previo and previo not in listados:
            ausente = texto_mapeo_no_listado(previo) if mapeos is not None else previo
            self.combo.addItem(ausente, previo)
        self.combo.setCurrentIndex(max(self.combo.findData(previo), 0) if previo else 0)
        self.combo.blockSignals(False)
        self._mapeo_cargado = previo

    def aplicar_pci(self, a: AsignacionPCI) -> None:
        self._mapeo_cargado = a.mapeo
        for chk, valor in (
            (self.chk_pcie, a.pcie),
            (self.chk_x_vga, a.x_vga),
            (self.chk_rombar, a.rombar),
            (self.chk_driver, a.driver_keep),
        ):
            chk.blockSignals(True)
            chk.setChecked(valor)
            chk.blockSignals(False)

    def aplicar_usb(self, a: AsignacionUSB) -> None:
        self._mapeo_cargado = a.mapeo
        self.chk_usb3.blockSignals(True)
        self.chk_usb3.setChecked(a.usb3)
        self.chk_usb3.blockSignals(False)


class SeccionHardwareCluster(QGroupBox):
    """Grupo «Hardware del clúster». Ver el módulo para la API pública."""

    pide_mapeos = Signal()  # al abrirse por primera vez y con «Releer» (RNF-D4)
    cambiado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            QCoreApplication.translate("SeccionHardwareCluster", "Hardware del clúster"), parent
        )
        self._info: InfoHardwareCluster | None = None
        self._permisos: PermisosEfectivos | None = None
        self._arq = Arquitectura.X86_64
        self._driver_keep_ok = False
        self._disponible = True
        self._pedido = False  # ya se emitió ``pide_mapeos``
        self._ocupado = False
        self._filas: list[_FilaDispositivo] = []

        capa = QVBoxLayout(self)
        capa.setSpacing(4)
        cabecera = QHBoxLayout()
        cabecera.addWidget(etiqueta(texto_intro_hardware_cluster(), secundario=True), 1)
        cabecera.addWidget(boton_ayuda("mapeo"))
        capa.addLayout(cabecera)
        self._motivo = mensaje(aviso=True)  # por qué está deshabilitada (RF-D0.3)
        capa.addWidget(self._motivo)
        self.chk_activar = QCheckBox(
            QCoreApplication.translate(
                "SeccionHardwareCluster", "Dar a la máquina tarjetas PCI o USB del clúster"
            )
        )
        capa.addWidget(self.chk_activar)

        self._cuerpo = QWidget()
        cuerpo = QVBoxLayout(self._cuerpo)
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(4)
        self._estado = mensaje(aviso=True)
        cuerpo.addWidget(self._estado)
        self._capa_pci = QVBoxLayout()
        self._capa_usb = QVBoxLayout()
        cuerpo.addLayout(self._capa_pci)
        cuerpo.addLayout(self._capa_usb)
        botones = QHBoxLayout()
        self.boton_anadir_pci = QPushButton(
            QCoreApplication.translate("SeccionHardwareCluster", "Añadir tarjeta PCI")
        )
        self.boton_anadir_usb = QPushButton(
            QCoreApplication.translate("SeccionHardwareCluster", "Añadir dispositivo USB")
        )
        self.boton_releer = QPushButton(
            QCoreApplication.translate("SeccionHardwareCluster", "Releer")
        )
        for b in (self.boton_anadir_pci, self.boton_anadir_usb, self.boton_releer):
            b.setAutoDefault(False)
            botones.addWidget(b)
        botones.addStretch(1)
        cuerpo.addLayout(botones)
        self._nota_arm = mensaje(aviso=True)
        self._errores = mensaje(error=True)
        self._avisos = mensaje(aviso=True)
        cuerpo.addWidget(self._nota_arm)
        cuerpo.addWidget(self._errores)
        cuerpo.addWidget(self._avisos)
        capa.addWidget(self._cuerpo)

        self.chk_activar.toggled.connect(self._al_activar)
        self.boton_anadir_pci.clicked.connect(lambda: self._anadir(TipoMapeo.PCI))
        self.boton_anadir_usb.clicked.connect(lambda: self._anadir(TipoMapeo.USB))
        self.boton_releer.clicked.connect(self._al_releer)
        self._refrescar()

    # --- Datos que entran --------------------------------------------------------------------

    def establecer_info(
        self, info: InfoHardwareCluster | None, permisos: PermisosEfectivos | None
    ) -> None:
        """Mapeos leídos del clúster (``None`` = aún sin leer) y los permisos para deshabilitar
        los que el usuario no puede usar (CA-D0.3.1, CA-D5.1.3)."""
        self._info = info
        self._permisos = permisos
        for fila in self._filas:
            self._llenar_fila(fila)
        self._refrescar()

    def reiniciar(self) -> None:
        """Otro servidor: se olvidan los mapeos leídos del anterior y la lectura pedida."""
        self._info = None
        self._permisos = None
        self._pedido = False
        for fila in self._filas:
            fila.llenar(None, None, None)
        self._refrescar()

    def establecer_arquitectura(self, arq: Arquitectura) -> None:
        """En ARM64 «PCIe» y «gráfica principal» se deshabilitan, con el motivo (V-D09)."""
        if arq == self._arq:
            return
        self._arq = arq
        self._ocupado = True
        try:
            for fila in self._filas:
                self._aplicar_arquitectura_a(fila)
        finally:
            self._ocupado = False
        self._refrescar()
        self.cambiado.emit()

    def establecer_driver_keep(self, disponible: bool) -> None:
        """«Mantener el controlador del servidor» solo existe con Proxmox 9.1 o posterior."""
        if disponible == self._driver_keep_ok:
            return
        self._driver_keep_ok = disponible
        for fila in self._filas:
            self._aplicar_arquitectura_a(fila)
        self._refrescar()

    def establecer_disponibilidad(self, estado: EstadoOpcion) -> None:
        """Sin ``Mapping.Use`` en ningún mapeo la sección queda deshabilitada con el motivo a la
        vista (V-D63, RF-D0.3); sin saberlo (``CON_AVISO``) se puede intentar."""
        libre = estado.disponibilidad != Disponibilidad.NO
        self._disponible = libre
        motivo = "" if estado.disponibilidad == Disponibilidad.SI else texto_estado_opcion(estado)
        if not libre and self.chk_activar.isChecked():
            # CL-A15: lo que ya no se puede usar vuelve a su valor por defecto, con aviso.
            motivo = texto_opcion_restablecida(OpcionD.MAPEOS.value, motivo)
            self.chk_activar.setChecked(False)
        poner_mensaje(self._motivo, motivo or None, aviso=True)
        self._refrescar()

    def establecer_valor(self, hw: HardwareCluster | None) -> None:
        """Carga el hardware de un lote guardado o del formulario («Crear otra»); ``None`` lo
        deja apagado."""
        self._ocupado = True
        try:
            self._vaciar()
            activo = hw is not None and not hw.vacio
            if activo and hw is not None:
                for a in hw.pci:
                    self._crear_fila(TipoMapeo.PCI).aplicar_pci(a)
                for u in hw.usb:
                    self._crear_fila(TipoMapeo.USB).aplicar_usb(u)
                for fila in self._filas:
                    self._llenar_fila(fila)
            self.chk_activar.setChecked(activo and self._disponible)
        finally:
            self._ocupado = False
        pedir = self.chk_activar.isChecked() and not self._pedido
        if pedir:
            self._pedido = True  # antes de refrescar, para que el estado diga «Leyendo…»
        self._refrescar()
        if pedir:
            self.pide_mapeos.emit()
        self.cambiado.emit()

    # --- Datos que salen ---------------------------------------------------------------------

    def valor(self) -> HardwareCluster | None:
        """El hardware pedido; ``None`` con la casilla apagada o sin ningún mapeo elegido."""
        if not self.chk_activar.isChecked() or not self._disponible:
            return None
        pci: list[AsignacionPCI] = []
        usb: list[AsignacionUSB] = []
        for fila in self._filas:
            mapeo = fila.mapeo()
            if mapeo is None:
                continue
            if fila.tipo == TipoMapeo.PCI:
                en_arm = self._arq == Arquitectura.AARCH64
                pci.append(
                    AsignacionPCI(
                        mapeo=mapeo,
                        pcie=fila.chk_pcie.isChecked() and not en_arm,
                        x_vga=fila.chk_x_vga.isChecked() and not en_arm,
                        rombar=fila.chk_rombar.isChecked(),
                        driver_keep=fila.chk_driver.isChecked() and self._driver_keep_ok,
                    )
                )
            else:
                usb.append(AsignacionUSB(mapeo=mapeo, usb3=fila.chk_usb3.isChecked()))
        hw = HardwareCluster(pci=tuple(pci), usb=tuple(usb))
        return None if hw.vacio else hw

    def mostrar_problemas(self, problemas: Sequence[Problema]) -> None:
        """Errores y avisos de hardware (V-D50 a V-D64) junto a la sección."""
        errores: list[str] = []
        avisos: list[str] = []
        for p in problemas:
            if not p.campo.startswith(_CAMPOS_PROPIOS):
                continue
            texto = texto_problema_d(p)
            if texto is None:
                continue
            (errores if p.severidad == Severidad.ERROR else avisos).append(texto)
        poner_mensaje(self._errores, "\n".join(dict.fromkeys(errores)) or None)
        poner_mensaje(self._avisos, "\n".join(dict.fromkeys(avisos)) or None, aviso=True)

    def mostrar_error_lectura(self, error: ErrorProxLaunch | None) -> None:
        """La lectura de los mapeos falló del todo: V-D50 «no pude leer» sin romper la sección."""
        if error is None:
            return
        self._info = InfoHardwareCluster(mapeos=None, error_mapeos=error)
        self._refrescar()

    # --- Internos ----------------------------------------------------------------------------

    def _mapeos_de(self, tipo: TipoMapeo) -> tuple[Mapeo, ...] | None:
        """Los mapeos leídos de un tipo; ``None`` si aún no se leyeron o la lectura falló."""
        if self._info is None or self._info.mapeos is None:
            return None
        return tuple(m for m in self._info.mapeos if m.tipo == tipo)

    def _crear_fila(self, tipo: TipoMapeo) -> _FilaDispositivo:
        fila = _FilaDispositivo(tipo)
        fila.cambiado.connect(self._emitir)
        fila.quitar.connect(self._quitar)
        (self._capa_pci if tipo == TipoMapeo.PCI else self._capa_usb).addWidget(fila)
        self._filas.append(fila)
        self._aplicar_arquitectura_a(fila)
        self._llenar_fila(fila)
        return fila

    def _llenar_fila(self, fila: _FilaDispositivo) -> None:
        fila.llenar(self._mapeos_de(fila.tipo), self._permisos, None)

    def _aplicar_arquitectura_a(self, fila: _FilaDispositivo) -> None:
        if fila.tipo != TipoMapeo.PCI:
            return
        en_arm = self._arq == Arquitectura.AARCH64
        for chk in (fila.chk_pcie, fila.chk_x_vga):
            chk.setEnabled(not en_arm)
            chk.setToolTip(texto_pcie_no_en_arm() if en_arm else "")
            if en_arm and chk.isChecked():
                chk.setChecked(False)
        # «Mantener el controlador» solo con Proxmox 9.1 o posterior: se oculta, no se ofrece.
        fila.chk_driver.setVisible(self._driver_keep_ok)
        if not self._driver_keep_ok and fila.chk_driver.isChecked():
            fila.chk_driver.setChecked(False)
        if fila.ayudas:
            fila.ayudas[-1].setVisible(self._driver_keep_ok)

    def _vaciar(self) -> None:
        for fila in self._filas:
            fila.setParent(None)
            fila.deleteLater()
        self._filas.clear()

    def _anadir(self, tipo: TipoMapeo) -> None:
        self._crear_fila(tipo)
        self._refrescar()
        self._emitir()

    def _quitar(self, fila: object) -> None:
        if isinstance(fila, _FilaDispositivo) and fila in self._filas:
            self._filas.remove(fila)
            fila.setParent(None)
            fila.deleteLater()
        self._refrescar()
        self._emitir()

    def _al_activar(self, marcada: bool) -> None:
        if marcada and not self._filas and not self._ocupado:
            self._crear_fila(TipoMapeo.PCI)
        # Se marca «pedido» antes de refrescar para que el estado diga «Leyendo…».
        pedir = marcada and not self._ocupado and not self._pedido
        if pedir:
            self._pedido = True
        self._refrescar()
        if pedir:
            self.pide_mapeos.emit()
        self._emitir()

    def _al_releer(self) -> None:
        self._info = None
        self._pedido = True
        self._refrescar()
        self.pide_mapeos.emit()

    def _emitir(self) -> None:
        if not self._ocupado:
            self.cambiado.emit()

    def _texto_estado(self) -> str | None:
        """Qué decir sobre la lectura de los mapeos: leyendo, sin mapeos o no se pudo leer."""
        if self._info is None:
            return texto_leyendo_mapeos() if self._pedido else texto_hardware_sin_leer()
        if self._info.mapeos is None:
            return texto_problema_d(
                Problema("hardware_cluster", "V-D50", Severidad.AVISO, {"motivo": "no_leidos"})
            )
        lineas: list[str] = []
        for tipo in (TipoMapeo.PCI, TipoMapeo.USB):
            if not self._mapeos_de(tipo):
                lineas.append(texto_sin_mapeos_de(tipo))
        if lineas == [texto_sin_mapeos_de(TipoMapeo.PCI), texto_sin_mapeos_de(TipoMapeo.USB)]:
            return texto_problema_d(Problema("hardware_cluster", "V-D50", Severidad.AVISO, {}))
        return "\n".join(lineas) or None

    def _refrescar(self) -> None:
        activo = self.chk_activar.isChecked() and self._disponible
        self._cuerpo.setVisible(activo)
        self.chk_activar.setEnabled(self._disponible)
        poner_mensaje(self._estado, self._texto_estado() if activo else None, aviso=True)
        n_pci = sum(1 for f in self._filas if f.tipo == TipoMapeo.PCI)
        n_usb = len(self._filas) - n_pci
        self.boton_anadir_pci.setEnabled(n_pci < MAX_PCI)
        self.boton_anadir_pci.setToolTip(
            texto_maximo_dispositivos(TipoMapeo.PCI, MAX_PCI) if n_pci >= MAX_PCI else ""
        )
        self.boton_anadir_usb.setEnabled(n_usb < MAX_USB)
        self.boton_anadir_usb.setToolTip(
            texto_maximo_dispositivos(TipoMapeo.USB, MAX_USB) if n_usb >= MAX_USB else ""
        )
        self.boton_releer.setEnabled(self._pedido)
        poner_mensaje(
            self._nota_arm,
            texto_pcie_no_en_arm() if self._arq == Arquitectura.AARCH64 and n_pci else None,
            aviso=True,
        )
