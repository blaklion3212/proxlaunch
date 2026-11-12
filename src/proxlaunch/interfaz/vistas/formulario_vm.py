"""Formulario de la MV en secciones: General, Firmware, Cómputo, Discos y Red (RF-13 a RF-17).

El formulario es la fuente de la verdad de lo que escribe el usuario: ``configuracion()``
construye un ``ConfiguracionVM`` en cada llamada. Un texto que no es un número se
convierte en 0, un valor que las reglas V-xx rechazan, y así el error aparece junto al
campo sin que el formulario tenga que duplicar reglas.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import ayuda, ayuda_cpu_host
from proxlaunch.interfaz.textos import texto_error, texto_motivo_nodo, texto_problema
from proxlaunch.interfaz.vistas.campos import (
    FilaCampo,
    etiqueta,
    mensaje,
    poner_mensaje,
)
from proxlaunch.interfaz.vistas.tabla_discos import TablaDiscos, entero_o_cero
from proxlaunch.interfaz.vistas.tabla_redes import TablaRedes
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    ConfiguracionVM,
    ControladorScsi,
    Firmware,
)
from proxlaunch.nucleo.seleccion_nodo import MotivoNodo, elegir_nodo
from proxlaunch.nucleo.validacion import Problema, Severidad
from proxlaunch.nucleo.valores_defecto import (
    bridge_por_defecto,
    configuracion_por_defecto,
    storage_por_defecto,
)

TIPOS_CPU = ("x86-64-v2-AES", "x86-64-v2", "x86-64-v3", "x86-64-v4", "host", "kvm64")


def gib_a_mib(texto: str) -> int:
    """GiB escritos por el usuario (admite coma o punto decimal) a MiB; inválido -> 0."""
    try:
        valor = float(texto.strip().replace(",", "."))
    except ValueError:
        return 0
    if not math.isfinite(valor):
        return 0
    return round(valor * 1024)


def mib_a_texto_gib(mib: int) -> str:
    """MiB a un texto de GiB sin ceros sobrantes (2048 -> «2», 512 -> «0.5»)."""
    return f"{mib / 1024:g}"


class _Transparente(QWidget):
    """Contenedor que no pinta el fondo del QSS: se ve el del grupo, como las demás filas."""


class FormularioVM(QWidget):
    """Formulario de creación de una MV con validación en vivo y modo básico/avanzado."""

    cambiado = Signal()  # el usuario cambió algo: hay que revalidar
    nodo_elegido = Signal(str)  # cambio manual de nodo: recargar sus recursos (CA-11.7)
    vmid_confirmado = Signal(int)  # el usuario terminó de escribir un VMID (V-03)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._inv: Inventario | None = None
        self._avanzado = False
        self._ocupado = False  # evita reentradas al rellenar widgets por código
        self._nodo_cargado = ""
        self._nodo_actual = ""
        self._motivo_nodo: MotivoNodo | None = None
        self._error_nodo: ErrorProxLaunch | None = None
        self._vmid_ocupado: tuple[int, str | None] | None = None
        # Registro de widgets avanzados: (widget, condición extra de visibilidad).
        self._avanzados: list[tuple[QWidget, Callable[[], bool]]] = []

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(10)
        self._construir_general(capa)
        self._construir_firmware(capa)
        self._construir_computo(capa)
        self._construir_discos(capa)
        self._construir_red(capa)
        capa.addStretch(1)
        self._aplicar_modo()
        self._actualizar_total_cpu()

    # --- Construcción -----------------------------------------------------------------

    def _grupo(self, titulo: str, capa: QVBoxLayout) -> QVBoxLayout:
        grupo = QGroupBox(titulo)
        interior = QVBoxLayout(grupo)
        interior.setSpacing(4)
        capa.addWidget(grupo)
        return interior

    def _registrar_avanzado(self, w: QWidget, condicion: Callable[[], bool] | None = None) -> None:
        self._avanzados.append((w, condicion or (lambda: True)))

    def _construir_general(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("General"), capa)
        self.vmid = QLineEdit()
        self.vmid.setMaximumWidth(140)
        self.fila_vmid = FilaCampo(self.tr("Número de máquina (VMID)"), self.vmid, "vmid")
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText(self.tr("por ejemplo srv-web-01"))
        self.fila_nombre = FilaCampo(self.tr("Nombre"), self.nombre)
        # Selector de nodo (solo en clúster, CA-13.5 y CA-13.6).
        self._radio_auto = QRadioButton(self.tr("Automático"))
        self._radio_manual = QRadioButton(self.tr("Manual"))
        self._radio_auto.setChecked(True)
        self._grupo_nodo = QButtonGroup(self)
        self._grupo_nodo.addButton(self._radio_auto)
        self._grupo_nodo.addButton(self._radio_manual)
        self.combo_nodo = QComboBox()
        self.combo_nodo.setEnabled(False)
        self._texto_motivo = etiqueta("", secundario=True)
        contenedor = _Transparente()
        cn = QVBoxLayout(contenedor)
        cn.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(self._radio_auto)
        fila.addWidget(self._radio_manual)
        fila.addWidget(self.combo_nodo, 1)
        cn.addLayout(fila)
        cn.addWidget(self._texto_motivo)
        self.fila_nodo = FilaCampo(self.tr("Nodo destino"), contenedor, "nodo")
        self.fila_nodo.hide()
        for f in (self.fila_vmid, self.fila_nombre, self.fila_nodo):
            g.addWidget(f)
        # Conexiones.
        self.vmid.textEdited.connect(self._al_editar_vmid)
        self.vmid.editingFinished.connect(self._al_terminar_vmid)
        self.nombre.textEdited.connect(lambda _t: self._al_editar(self.fila_nombre))
        self.nombre.editingFinished.connect(lambda: self._tocar(self.fila_nombre))
        self._radio_auto.toggled.connect(self._al_cambiar_modo_nodo)
        self.combo_nodo.currentIndexChanged.connect(self._al_elegir_nodo)

    def _construir_firmware(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("Firmware"), capa)
        self.combo_firmware = QComboBox()
        self.combo_firmware.addItem(self.tr("SeaBIOS (clásico)"), Firmware.SEABIOS)
        self.combo_firmware.addItem(self.tr("UEFI (OVMF)"), Firmware.OVMF)
        self.fila_firmware = FilaCampo(self.tr("Tipo de arranque"), self.combo_firmware, "firmware")
        self.combo_efi = QComboBox()
        self.fila_efi = FilaCampo(
            self.tr("Almacenamiento de UEFI"), self.combo_efi, "almacenamiento"
        )
        self._registrar_avanzado(
            self.fila_efi, lambda: self.combo_firmware.currentData() == Firmware.OVMF
        )
        g.addWidget(self.fila_firmware)
        g.addWidget(self.fila_efi)
        self.combo_firmware.currentIndexChanged.connect(self._al_cambiar_firmware)
        self.combo_efi.currentIndexChanged.connect(lambda _i: self._al_editar(self.fila_efi))

    def _construir_computo(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("Cómputo"), capa)
        self.combo_sockets = QComboBox()
        for n in range(1, 5):
            self.combo_sockets.addItem(str(n), n)
        self.combo_sockets.setMaximumWidth(80)
        self.fila_sockets = FilaCampo(self.tr("Sockets"), self.combo_sockets, "sockets")
        self.cores = QLineEdit("2")
        self.cores.setMaximumWidth(80)
        self.fila_cores = FilaCampo(self.tr("Núcleos por socket"), self.cores, "cores")
        self._total_cpu = etiqueta("", secundario=True)
        self.combo_cpu = QComboBox()
        for t in TIPOS_CPU:
            self.combo_cpu.addItem(t, t)
        self.fila_cpu = FilaCampo(self.tr("Tipo de CPU"), self.combo_cpu, "tipo_cpu")
        self._aviso_cpu = etiqueta(ayuda_cpu_host(), secundario=True)
        self._aviso_cpu.hide()
        self.memoria = QLineEdit("2")
        self.memoria.setMaximumWidth(100)
        self.fila_memoria = FilaCampo(self.tr("Memoria (GiB)"), self.memoria, "memoria")
        self.combo_balloon = QComboBox()
        self.combo_balloon.addItem(self.tr("Predeterminado de Proxmox"), None)
        self.combo_balloon.addItem(self.tr("Activado"), True)
        self.combo_balloon.addItem(self.tr("Desactivado"), False)
        self.fila_balloon = FilaCampo(self.tr("Ballooning"), self.combo_balloon, "ballooning")
        self.balloon_min = QLineEdit("1")
        self.balloon_min.setMaximumWidth(100)
        self.fila_balloon_min = FilaCampo(
            self.tr("Memoria mínima (GiB)"), self.balloon_min, "ballooning"
        )
        for f in (
            self.fila_sockets,
            self.fila_cores,
            self._total_cpu,
            self.fila_cpu,
            self._aviso_cpu,
            self.fila_memoria,
            self.fila_balloon,
            self.fila_balloon_min,
        ):
            g.addWidget(f)
        self._registrar_avanzado(self.fila_cpu)
        self._registrar_avanzado(self._aviso_cpu, lambda: self.combo_cpu.currentData() == "host")
        self._registrar_avanzado(self.fila_balloon)
        self._registrar_avanzado(
            self.fila_balloon_min, lambda: self.combo_balloon.currentData() is True
        )
        self.combo_sockets.currentIndexChanged.connect(self._al_cambiar_cpu)
        self.cores.textEdited.connect(lambda _t: self._al_cambiar_cpu(fila=self.fila_cores))
        self.cores.editingFinished.connect(lambda: self._tocar(self.fila_cores))
        self.combo_cpu.currentIndexChanged.connect(self._al_cambiar_tipo_cpu)
        self.memoria.textEdited.connect(lambda _t: self._al_editar(self.fila_memoria))
        self.memoria.editingFinished.connect(lambda: self._tocar(self.fila_memoria))
        self.combo_balloon.currentIndexChanged.connect(self._al_cambiar_balloon)
        self.balloon_min.textEdited.connect(lambda _t: self._al_editar(self.fila_balloon_min))
        self.balloon_min.editingFinished.connect(lambda: self._tocar(self.fila_balloon_min))

    def _construir_discos(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("Discos"), capa)
        self.chk_sin_disco = QCheckBox(self.tr("Sin disco"))
        self.chk_sin_disco.setToolTip(ayuda("sin_disco"))
        self._sin_storage = mensaje(error=True)
        self.combo_ctrl = QComboBox()
        self.combo_ctrl.addItem("virtio-scsi-single", ControladorScsi.VIRTIO_SINGLE)
        self.combo_ctrl.addItem("virtio-scsi-pci", ControladorScsi.VIRTIO_PCI)
        self.fila_ctrl = FilaCampo(self.tr("Controlador SCSI"), self.combo_ctrl, "controlador")
        self.tabla_discos = TablaDiscos()
        self._registrar_avanzado(self.fila_ctrl, lambda: not self.chk_sin_disco.isChecked())
        g.addWidget(self.chk_sin_disco)
        g.addWidget(self._sin_storage)
        g.addWidget(self.fila_ctrl)
        g.addWidget(self.tabla_discos)
        self.chk_sin_disco.toggled.connect(self._al_cambiar_sin_disco)
        self.combo_ctrl.currentIndexChanged.connect(self._al_cambiar_controlador)
        self.tabla_discos.cambiado.connect(self._al_cambiar_tabla)

    def _construir_red(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("Red"), capa)
        self.tabla_redes = TablaRedes()
        g.addWidget(self.tabla_redes)
        self.tabla_redes.cambiado.connect(self._al_cambiar_tabla)

    # --- Modo básico / avanzado -------------------------------------------------------

    def establecer_modo(self, avanzado: bool) -> None:
        """Cambia solo la visibilidad de los widgets avanzados; no restablece valores."""
        self._avanzado = avanzado
        self._aplicar_modo()

    def _aplicar_modo(self) -> None:
        for w, condicion in self._avanzados:
            w.setVisible(self._avanzado and condicion())
        self.tabla_discos.establecer_avanzado(self._avanzado)
        self.tabla_redes.establecer_avanzado(self._avanzado)

    # --- Inventario y valores por defecto ---------------------------------------------

    def establecer_inventario(self, inv: Inventario, *, reiniciar: bool = False) -> None:
        """Carga el inventario descubierto.

        La primera vez (o con ``reiniciar``) rellena los valores por defecto de la sección
        5; en una actualización conserva lo que el usuario ya escribió (CA-03.3).
        """
        primera = self._inv is None or reiniciar
        self._inv = inv
        self._ocupado = True
        try:
            self._llenar_combo_nodos()
            es_cluster = inv.topologia.es_cluster
            self.fila_nodo.setVisible(es_cluster)
            if primera:
                nodo, motivo, error = self._calcular_nodo(requerido_gib=32)
                nodo_inicial = nodo or next(
                    (n.nombre for n in inv.topologia.nodos if n.en_linea), ""
                )
                storage_inicial = storage_por_defecto(list(inv.storages.get(nodo_inicial, ())))
                cfg = configuracion_por_defecto(
                    inv.proximo_vmid,
                    "",
                    nodo_inicial,
                    storage_inicial,
                    bridge_por_defecto(list(inv.bridges.get(nodo_inicial, ()))),
                )
                if storage_inicial is None:
                    cfg.con_disco = False  # CA-11.9: sin almacenamiento solo se puede «Sin disco»
                self._aplicar_configuracion_interna(cfg, motivo, error)
            else:
                if not self.fila_vmid.tocado:
                    self.vmid.setText(str(inv.proximo_vmid))
                self._nodo_cargado = ""  # fuerza la recarga de recursos del nodo
                self._actualizar_nodo()
        finally:
            self._ocupado = False
        self._aplicar_modo()
        self.cambiado.emit()

    def aplicar_configuracion(self, cfg: ConfiguracionVM) -> None:
        """Rellena el formulario con una configuración (pruebas y «Crear otra»)."""
        self._ocupado = True
        try:
            self._aplicar_configuracion_interna(cfg, None, None)
        finally:
            self._ocupado = False
        self._aplicar_modo()
        self.cambiado.emit()

    def _aplicar_configuracion_interna(
        self, cfg: ConfiguracionVM, motivo: MotivoNodo | None, error: ErrorProxLaunch | None
    ) -> None:
        self.vmid.setText(str(cfg.vmid))
        self.nombre.setText(cfg.nombre)
        self.combo_firmware.setCurrentIndex(max(self.combo_firmware.findData(cfg.firmware), 0))
        self.combo_sockets.setCurrentIndex(max(self.combo_sockets.findData(cfg.sockets), 0))
        self.cores.setText(str(cfg.cores))
        idx = self.combo_cpu.findData(cfg.tipo_cpu)
        if idx < 0:
            self.combo_cpu.addItem(cfg.tipo_cpu, cfg.tipo_cpu)
            idx = self.combo_cpu.count() - 1
        self.combo_cpu.setCurrentIndex(idx)
        self.memoria.setText(mib_a_texto_gib(cfg.memoria_mib))
        if cfg.ballooning is None:
            self.combo_balloon.setCurrentIndex(0)
        else:
            self.combo_balloon.setCurrentIndex(1 if cfg.ballooning.activo else 2)
            if cfg.ballooning.activo:
                self.balloon_min.setText(mib_a_texto_gib(cfg.ballooning.minimo_mib))
        self.chk_sin_disco.setChecked(not cfg.con_disco)
        self.combo_ctrl.setCurrentIndex(max(self.combo_ctrl.findData(cfg.controlador_scsi), 0))
        self.tabla_discos.establecer_controlador(cfg.controlador_scsi)
        # Recursos del nodo y filas de las tablas.
        self._nodo_actual = cfg.nodo
        self._motivo_nodo, self._error_nodo = motivo, error
        self._cargar_recursos_nodo(cfg.nodo)
        self.tabla_discos.establecer_discos(cfg.discos)
        self.tabla_redes.establecer_redes(cfg.redes)
        self._poblar_efi(cfg.storage_efi)
        self._refrescar_etiqueta_nodo()
        self._actualizar_total_cpu()
        self._actualizar_sin_disco()

    # --- Lectura ----------------------------------------------------------------------

    def configuracion(self) -> ConfiguracionVM:
        """Construye la configuración con lo que hay en los widgets."""
        nodo = self.nodo_efectivo()
        balloon_estado = self.combo_balloon.currentData()
        ballooning: Ballooning | None
        if balloon_estado is None:
            ballooning = None
        elif balloon_estado:
            ballooning = Ballooning(True, gib_a_mib(self.balloon_min.text()))
        else:
            ballooning = Ballooning(False, 0)
        return ConfiguracionVM(
            vmid=entero_o_cero(self.vmid.text()),
            nombre=self.nombre.text().strip(),
            nodo=nodo,
            firmware=Firmware(self.combo_firmware.currentData()),
            storage_efi=self.combo_efi.currentData() or None,
            sockets=self.combo_sockets.currentData(),
            cores=entero_o_cero(self.cores.text()),
            tipo_cpu=self.combo_cpu.currentData(),
            memoria_mib=gib_a_mib(self.memoria.text()),
            ballooning=ballooning,
            con_disco=not self.chk_sin_disco.isChecked(),
            discos=self.tabla_discos.discos(),
            controlador_scsi=ControladorScsi(self.combo_ctrl.currentData()),
            redes=self.tabla_redes.redes(),
        )

    def nodo_efectivo(self) -> str:
        """Nodo que se usará (el manual, el que eligió Automático o el único)."""
        return self._nodo_actual

    @property
    def motivo_nodo(self) -> MotivoNodo | None:
        return self._motivo_nodo

    @property
    def error_nodo(self) -> ErrorProxLaunch | None:
        return self._error_nodo

    @property
    def es_automatico(self) -> bool:
        return self._radio_auto.isChecked()

    def etiquetas_discos(self) -> list[str]:
        return self.tabla_discos.etiquetas_discos()

    # --- Nodo -------------------------------------------------------------------------

    def _espacio_requerido(self) -> int:
        if self.chk_sin_disco.isChecked():
            return 0
        return sum(d.tamano_gib for d in self.tabla_discos.discos() if d.tamano_gib > 0)

    def _calcular_nodo(
        self, requerido_gib: int | None = None
    ) -> tuple[str, MotivoNodo | None, ErrorProxLaunch | None]:
        """Nodo según el modo: único, manual o Automático (P-07)."""
        inv = self._inv
        if inv is None:
            return "", None, None
        if not inv.topologia.es_cluster:
            nodos = inv.topologia.nodos
            return (nodos[0].nombre if nodos else ""), None, None
        if not self._radio_auto.isChecked():
            return str(self.combo_nodo.currentData() or ""), None, None
        requerido = self._espacio_requerido() if requerido_gib is None else requerido_gib
        try:
            nodo, motivo = elegir_nodo(inv, requerido)
        except ErrorProxLaunch as e:
            return "", None, e
        return nodo, motivo, None

    def _actualizar_nodo(self) -> None:
        nodo, motivo, error = self._calcular_nodo()
        self._nodo_actual, self._motivo_nodo, self._error_nodo = nodo, motivo, error
        self._refrescar_etiqueta_nodo()
        if nodo != self._nodo_cargado:
            self._cargar_recursos_nodo(nodo)

    def _refrescar_etiqueta_nodo(self) -> None:
        if self._inv is None or not self._inv.topologia.es_cluster:
            return
        if not self._radio_auto.isChecked():
            self._texto_motivo.setText("")
            self._texto_motivo.hide()
            return
        if self._error_nodo is not None:
            self._texto_motivo.setText(texto_error(self._error_nodo))
        elif self._motivo_nodo is not None:
            self._texto_motivo.setText(
                self.tr("Nodo elegido: {nodo} ({motivo})").format(
                    nodo=self._nodo_actual, motivo=texto_motivo_nodo(self._motivo_nodo)
                )
            )
        self._texto_motivo.show()

    def _llenar_combo_nodos(self) -> None:
        inv = self._inv
        if inv is None:
            return
        previo = self.combo_nodo.currentData()
        self.combo_nodo.blockSignals(True)
        self.combo_nodo.clear()
        for n in inv.topologia.nodos:
            texto = n.nombre if n.en_linea else f"{n.nombre} — {self.tr('Sin conexión')}"
            self.combo_nodo.addItem(texto, n.nombre)
            if not n.en_linea:
                self.combo_nodo.model().item(self.combo_nodo.count() - 1).setEnabled(False)
        idx = self.combo_nodo.findData(previo) if previo else -1
        if idx < 0:
            idx = next((i for i, n in enumerate(inv.topologia.nodos) if n.en_linea), -1)
        self.combo_nodo.setCurrentIndex(idx)
        self.combo_nodo.blockSignals(False)

    def _cargar_recursos_nodo(self, nodo: str) -> None:
        """Rellena almacenamientos y bridges con los del nodo (CA-11.7)."""
        inv = self._inv
        if inv is None:
            return
        self._nodo_cargado = nodo
        almacenes = inv.storages.get(nodo, ())
        redes = inv.bridges.get(nodo, ())
        avisos: list[str] = []
        perdidos = self.tabla_discos.establecer_storages(almacenes)
        self.tabla_discos.mostrar_aviso_nodo(None)
        for sid in perdidos:
            avisos.append(
                self.tr(
                    "El almacenamiento «{recurso}» no existe en el nodo «{nodo}». Elige otro."
                ).format(recurso=sid, nodo=nodo)
            )
        self.tabla_discos.mostrar_aviso_nodo("\n".join(avisos))
        perdidas = self.tabla_redes.establecer_bridges(redes)
        self.tabla_redes.mostrar_aviso_nodo(
            "\n".join(
                self.tr("La red «{recurso}» no existe en el nodo «{nodo}». Elige otra.").format(
                    recurso=b, nodo=nodo
                )
                for b in perdidas
            )
        )
        self._poblar_efi(self.combo_efi.currentData())
        self._actualizar_sin_disco()

    def actualizar_recursos_nodo(self, nodo: str, storages: Sequence, bridges: Sequence) -> None:
        """Guarda los recursos releídos de un nodo y los recarga si es el efectivo."""
        if self._inv is None:
            return
        self._inv.storages[nodo] = tuple(storages)
        self._inv.bridges[nodo] = tuple(bridges)
        if nodo == self._nodo_actual:
            self._ocupado = True
            try:
                self._cargar_recursos_nodo(nodo)
            finally:
                self._ocupado = False
            self.cambiado.emit()

    def _poblar_efi(self, seleccionado: str | None) -> None:
        inv = self._inv
        self.combo_efi.blockSignals(True)
        self.combo_efi.clear()
        self.combo_efi.addItem(self.tr("Automático (el del primer disco)"), None)
        if inv is not None:
            for s in inv.storages.get(self._nodo_actual, ()):
                if s.activo:
                    self.combo_efi.addItem(s.id, s.id)
        idx = self.combo_efi.findData(seleccionado) if seleccionado else 0
        self.combo_efi.setCurrentIndex(max(idx, 0))
        self.combo_efi.blockSignals(False)

    def _actualizar_sin_disco(self) -> None:
        """CA-11.9: sin almacenamiento para discos solo se puede crear «sin disco»."""
        inv = self._inv
        hay = inv is not None and any(s.activo for s in inv.storages.get(self._nodo_actual, ()))
        if inv is not None and not hay:
            poner_mensaje(
                self._sin_storage,
                self.tr("Este servidor no tiene almacenamiento para discos de máquinas virtuales"),
            )
        else:
            poner_mensaje(self._sin_storage, None)
        self.tabla_discos.setVisible(not self.chk_sin_disco.isChecked())

    # --- Señales internas -------------------------------------------------------------

    def _tocar(self, fila: FilaCampo) -> None:
        if not fila.tocado:
            fila.marcar_tocado()
            self.cambiado.emit()

    def _al_editar(self, fila: FilaCampo | None = None) -> None:
        if self._ocupado:
            return
        if fila is not None:
            fila.marcar_tocado()
        self._actualizar_nodo()
        self.cambiado.emit()

    def _al_editar_vmid(self, _texto: str) -> None:
        self.fila_vmid.marcar_tocado()
        self._al_editar(self.fila_vmid)

    def _al_terminar_vmid(self) -> None:
        self.fila_vmid.marcar_tocado()
        try:
            n = int(self.vmid.text().strip())
        except ValueError:
            return
        if self._inv is not None and n != self._inv.proximo_vmid:
            self.vmid_confirmado.emit(n)

    def _al_cambiar_cpu(self, *_args: object, fila: FilaCampo | None = None) -> None:
        self._actualizar_total_cpu()
        self._al_editar(fila)

    def _al_cambiar_tipo_cpu(self, _i: int) -> None:
        self._aplicar_modo()
        self._al_editar()

    def _al_cambiar_balloon(self, _i: int) -> None:
        self._aplicar_modo()
        self._al_editar()

    def _al_cambiar_firmware(self, _i: int) -> None:
        self._aplicar_modo()
        self._al_editar()

    def _al_cambiar_sin_disco(self, _marcado: bool) -> None:
        if self._ocupado:
            return
        self._actualizar_sin_disco()
        self._aplicar_modo()
        self._al_editar()

    def _al_cambiar_controlador(self, _i: int) -> None:
        self.tabla_discos.establecer_controlador(ControladorScsi(self.combo_ctrl.currentData()))
        self._al_editar()

    def _al_cambiar_tabla(self) -> None:
        if self._ocupado:
            return
        self._actualizar_nodo()
        self.cambiado.emit()

    def _al_cambiar_modo_nodo(self, _auto: bool) -> None:
        if self._ocupado:
            return
        self.combo_nodo.setEnabled(not self._radio_auto.isChecked())
        self._actualizar_nodo()
        self.cambiado.emit()
        if not self._radio_auto.isChecked() and self._nodo_actual:
            self.nodo_elegido.emit(self._nodo_actual)

    def _al_elegir_nodo(self, _i: int) -> None:
        if self._ocupado or self._radio_auto.isChecked():
            return
        self._actualizar_nodo()
        self.cambiado.emit()
        if self._nodo_actual:
            self.nodo_elegido.emit(self._nodo_actual)

    def _actualizar_total_cpu(self) -> None:
        sockets = self.combo_sockets.currentData() or 1
        cores = entero_o_cero(self.cores.text())
        if cores > 0:
            self._total_cpu.setText(
                self.tr("{n} procesadores virtuales en total").format(n=sockets * cores)
            )
            self._total_cpu.show()
        else:
            self._total_cpu.hide()

    # --- VMID -------------------------------------------------------------------------

    def marcar_vmid_ocupado(self, vmid: int, siguiente: str | None) -> None:
        self._vmid_ocupado = (vmid, siguiente)
        self.fila_vmid.marcar_tocado()
        self.cambiado.emit()

    def limpiar_vmid_ocupado(self) -> None:
        if self._vmid_ocupado is not None:
            self._vmid_ocupado = None
            self.cambiado.emit()

    def preparar_otra(self) -> None:
        """«Crear otra»: conserva la configuración, vacía el nombre y libera el VMID."""
        self.nombre.clear()
        self.fila_nombre.tocado = False
        self.fila_vmid.tocado = False
        self._vmid_ocupado = None
        self.cambiado.emit()

    def sugerir_vmid(self, vmid: int) -> None:
        self.vmid.setText(str(vmid))
        self._vmid_ocupado = None
        self.cambiado.emit()

    def problemas_extra(self) -> list[Problema]:
        """Problemas que el núcleo no calcula con datos locales (V-03, CA-17.1)."""
        extra: list[Problema] = []
        if self._vmid_ocupado is not None:
            vmid, siguiente = self._vmid_ocupado
            if entero_o_cero(self.vmid.text()) == vmid:
                params = {"vmid": str(vmid)}
                if siguiente:
                    params["siguiente"] = siguiente
                extra.append(Problema("vmid", "V-03", Severidad.ERROR, params))
        if self._inv is not None and self._nodo_actual and not self.tabla_redes.hay_bridges():
            extra.append(Problema("redes", "V-16.sinredes", Severidad.ERROR, {}))
        return extra

    # --- Errores y bloqueo ------------------------------------------------------------

    def aplicar_problemas(self, problemas: Sequence[Problema]) -> None:
        """Muestra cada error junto a su campo (propiedad ``invalido``)."""
        por_campo: dict[str, list[Problema]] = {}
        for p in problemas:
            por_campo.setdefault(p.campo, []).append(p)

        def texto(campo: str) -> str | None:
            errores = [
                texto_problema(p)
                for p in por_campo.get(campo, [])
                if p.severidad == Severidad.ERROR
            ]
            return errores[0] if errores else None

        self.fila_vmid.mostrar_error(texto("vmid"))
        self.fila_nombre.mostrar_error(texto("nombre"))
        nodo_txt = texto("nodo")
        if self._error_nodo is not None:
            nodo_txt = None  # el motivo ya está debajo del selector
        self.fila_nodo.marcar_tocado()
        self.fila_nodo.mostrar_error(nodo_txt)
        self.fila_sockets.mostrar_error(texto("sockets"))
        self.fila_cores.mostrar_error(texto("cores"))
        self.fila_memoria.mostrar_error(texto("memoria_mib"))
        self.fila_balloon_min.mostrar_error(texto("ballooning.minimo_mib"))
        self.fila_ctrl.mostrar_error(texto("controlador_scsi"))
        self.fila_efi.marcar_tocado()
        self.fila_efi.mostrar_error(texto("storage_efi"))
        self.tabla_discos.aplicar_problemas(problemas)
        self.tabla_redes.aplicar_problemas(problemas)

    def bloquear(self, bloqueado: bool) -> None:
        """Bloquea los campos mientras se crea la máquina (CA-19.4)."""
        self.setEnabled(not bloqueado)
