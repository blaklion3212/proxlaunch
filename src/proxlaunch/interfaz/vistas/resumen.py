"""Panel de resumen en lenguaje llano y botón «Crear máquina» (RF-19, CA-24.5, RF-27)."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget

from proxlaunch.interfaz.textos import texto_problema
from proxlaunch.interfaz.vistas.campos import mensaje, poner_mensaje
from proxlaunch.interfaz.vistas.formulario_vm import mib_a_texto_gib
from proxlaunch.nucleo.modelos.inventario import Nodo
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    Firmware,
    FormatoDisco,
    ModeloRed,
)
from proxlaunch.nucleo.validacion import Problema, Severidad, opciones_permitidas
from proxlaunch.nucleo.valores_defecto import TIPO_CPU


def nombre_campo(campo: str) -> str:
    """Nombre corto del campo para prefijar un problema en la lista del resumen."""
    base = campo.split("[")[0].split(".")[0]
    nombres = {
        "nombre": QCoreApplication.translate("ResumenVM", "Nombre"),
        "vmid": QCoreApplication.translate("ResumenVM", "Número de máquina"),
        "nodo": QCoreApplication.translate("ResumenVM", "Nodo"),
        "sockets": QCoreApplication.translate("ResumenVM", "Sockets"),
        "cores": QCoreApplication.translate("ResumenVM", "Núcleos"),
        "memoria_mib": QCoreApplication.translate("ResumenVM", "Memoria"),
        "ballooning": QCoreApplication.translate("ResumenVM", "Ballooning"),
        "controlador_scsi": QCoreApplication.translate("ResumenVM", "Controlador SCSI"),
        "storage_efi": QCoreApplication.translate("ResumenVM", "Almacenamiento de UEFI"),
        "discos": QCoreApplication.translate("ResumenVM", "Disco"),
        "redes": QCoreApplication.translate("ResumenVM", "Red"),
        "origen": QCoreApplication.translate("ResumenVM", "Origen"),
    }
    return nombres.get(base, base)


def opciones_avanzadas_no_predeterminadas(cfg: ConfiguracionVM) -> list[str]:
    """Valores ocultos en modo básico que no son los predeterminados (CA-24.5)."""
    lineas: list[str] = []
    if cfg.tipo_cpu != TIPO_CPU:
        lineas.append(
            QCoreApplication.translate("ResumenVM", "Tipo de CPU: {valor}").format(
                valor=cfg.tipo_cpu
            )
        )
    if cfg.ballooning is not None:
        if cfg.ballooning.activo:
            lineas.append(
                QCoreApplication.translate(
                    "ResumenVM", "Ballooning activado, memoria mínima {valor} GiB"
                ).format(valor=mib_a_texto_gib(cfg.ballooning.minimo_mib))
            )
        else:
            lineas.append(QCoreApplication.translate("ResumenVM", "Ballooning desactivado"))
    if cfg.controlador_scsi != ControladorScsi.VIRTIO_SINGLE:
        lineas.append(
            QCoreApplication.translate("ResumenVM", "Controlador SCSI: {valor}").format(
                valor=cfg.controlador_scsi
            )
        )
    if cfg.firmware == Firmware.OVMF and cfg.storage_efi:
        lineas.append(
            QCoreApplication.translate("ResumenVM", "UEFI se guarda en: {valor}").format(
                valor=cfg.storage_efi
            )
        )
    if cfg.con_disco:
        for i, d in enumerate(cfg.discos):
            op = opciones_permitidas(d, cfg.controlador_scsi)
            cambios: list[str] = []
            if d.bus != Bus.SCSI:
                cambios.append(
                    QCoreApplication.translate("ResumenVM", "conexión {valor}").format(
                        valor=str(d.bus).upper()
                    )
                )
            if d.formato != FormatoDisco.AUTO:
                cambios.append(
                    QCoreApplication.translate("ResumenVM", "formato {valor}").format(
                        valor=d.formato
                    )
                )
            if op.discard and not d.discard:
                cambios.append(QCoreApplication.translate("ResumenVM", "sin discard"))
            if op.ssd and not d.ssd:
                cambios.append(QCoreApplication.translate("ResumenVM", "sin SSD"))
            if op.iothread and not d.iothread:
                cambios.append(QCoreApplication.translate("ResumenVM", "sin IO Thread"))
            if cambios:
                lineas.append(
                    QCoreApplication.translate("ResumenVM", "Disco {n}: {cambios}").format(
                        n=i + 1, cambios=", ".join(cambios)
                    )
                )
    for i, r in enumerate(cfg.redes):
        if r.modelo != ModeloRed.VIRTIO:
            lineas.append(
                QCoreApplication.translate("ResumenVM", "Red {n}: tarjeta {valor}").format(
                    n=i + 1, valor=r.modelo
                )
            )
    return lineas


class ResumenVM(QGroupBox):
    """Resume lo que se va a crear y concentra el botón «Crear máquina»."""

    crear_solicitado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QCoreApplication.translate("ResumenVM", "Resumen"), parent)
        self._texto = QLabel()
        self._texto.setWordWrap(True)
        self._texto.setTextFormat(Qt.TextFormat.RichText)
        self._pendientes = mensaje(error=True)
        self._avisos = mensaje(aviso=True)
        self._motivo = QLabel()
        self._motivo.setWordWrap(True)
        self._motivo.setProperty("secundario", True)
        self.boton_crear = QPushButton(QCoreApplication.translate("ResumenVM", "Crear máquina"))
        self.boton_crear.setProperty("primario", True)
        self.boton_crear.setEnabled(False)
        self.boton_crear.clicked.connect(self._al_pulsar)
        self._enviado = False
        capa = QVBoxLayout(self)
        capa.addWidget(self._texto)
        capa.addWidget(self._pendientes)
        capa.addWidget(self._avisos)
        capa.addWidget(self._motivo)
        capa.addWidget(self.boton_crear)

    def _al_pulsar(self) -> None:
        # CA-19.6: ni un segundo clic ni un doble clic generan dos envíos.
        if self._enviado or not self.boton_crear.isEnabled():
            return
        self._enviado = True
        self.boton_crear.setEnabled(False)
        self.crear_solicitado.emit()

    def liberar(self) -> None:
        """Permite un nuevo envío (al terminar la tarea)."""
        self._enviado = False

    @property
    def texto_html(self) -> str:
        return self._texto.text()

    @property
    def texto_pendientes(self) -> str:
        return self._pendientes.text()

    def actualizar(
        self,
        cfg: ConfiguracionVM,
        etiquetas_discos: Sequence[str],
        problemas: Sequence[Problema],
        *,
        avanzado: bool,
        motivo_nodo: str,
        bloqueo: str | None,
        ocupado: bool,
        nodo: Nodo | None = None,
    ) -> None:
        """Redibuja el resumen y decide si se puede crear."""
        e = escape
        tr = QCoreApplication.translate
        et_nombre = tr("ResumenVM", "Nombre")
        et_vmid = tr("ResumenVM", "Número de máquina")
        et_nodo = tr("ResumenVM", "Nodo")
        et_arranque = tr("ResumenVM", "Arranque")
        et_cpu = tr("ResumenVM", "Procesadores")
        et_memoria = tr("ResumenVM", "Memoria")
        et_discos = tr("ResumenVM", "Discos")
        et_redes = tr("ResumenVM", "Redes")
        sin_disco = tr("ResumenVM", "Sin disco")
        sin_red = tr("ResumenVM", "Sin red")
        lineas: list[str] = []
        lineas.append(f"<b>{e(et_nombre)}:</b> {e(cfg.nombre) or '—'}")
        lineas.append(f"<b>{e(et_vmid)}:</b> {cfg.vmid or '—'}")
        nodo_txt = e(cfg.nodo) if cfg.nodo else "—"
        if motivo_nodo and cfg.nodo:
            nodo_txt += f" <i>({e(motivo_nodo)})</i>"
        lineas.append(f"<b>{e(et_nodo)}:</b> {nodo_txt}")
        if cfg.firmware == Firmware.OVMF:
            firmware = "UEFI (OVMF)"
        else:
            firmware = tr("ResumenVM", "SeaBIOS (clásico)")
        lineas.append(f"<b>{e(et_arranque)}:</b> {e(firmware)}")
        total = tr("ResumenVM", "{n} procesadores virtuales en total").format(
            n=cfg.sockets * cfg.cores
        )
        lineas.append(f"<b>{e(et_cpu)}:</b> {e(total)} ({cfg.sockets} × {cfg.cores})")
        memoria = tr("ResumenVM", "{valor} GiB").format(valor=mib_a_texto_gib(cfg.memoria_mib))
        lineas.append(f"<b>{e(et_memoria)}:</b> {e(memoria)}")
        if cfg.con_disco and cfg.discos:
            partes = []
            for i, d in enumerate(cfg.discos):
                etiqueta = etiquetas_discos[i] if i < len(etiquetas_discos) else f"#{i + 1}"
                detalle = tr("ResumenVM", "{etiqueta}: {tam} GiB en {storage}").format(
                    etiqueta=etiqueta, tam=d.tamano_gib, storage=d.storage or "—"
                )
                partes.append("• " + e(detalle))
            lineas.append(f"<b>{e(et_discos)}:</b><br>" + "<br>".join(partes))
        else:
            lineas.append(f"<b>{e(et_discos)}:</b> {e(sin_disco)}")
        if cfg.redes:
            partes = []
            for i, r in enumerate(cfg.redes):
                vlan = f", VLAN {r.vlan}" if r.vlan is not None else ""
                partes.append(f"• net{i}: {e(r.bridge or '—')}{e(vlan)}")
            lineas.append(f"<b>{e(et_redes)}:</b><br>" + "<br>".join(partes))
        else:
            lineas.append(f"<b>{e(et_redes)}:</b> {e(sin_red)}")
        if not avanzado:
            ocultas = opciones_avanzadas_no_predeterminadas(cfg)
            if ocultas:
                titulo = tr(
                    "ResumenVM", "Opciones avanzadas que se aplicarán (ocultas en modo básico)"
                )
                lineas.append(
                    f"<b>{e(titulo)}:</b><br>" + "<br>".join("• " + e(o) for o in ocultas)
                )
        self._texto.setText("<br>".join(lineas))

        errores = [p for p in problemas if p.severidad == Severidad.ERROR]
        avisos = [p for p in problemas if p.severidad == Severidad.AVISO]
        if errores:
            cabecera = QCoreApplication.translate(
                "ResumenVM", "Para crear la máquina hay que corregir:"
            )
            cuerpo = "\n".join(f"• {nombre_campo(p.campo)}: {texto_problema(p)}" for p in errores)
            poner_mensaje(self._pendientes, f"{cabecera}\n{cuerpo}")
        else:
            poner_mensaje(self._pendientes, None)
        textos_aviso = [texto_problema(p) for p in avisos]
        textos_aviso.extend(self._avisos_recursos(cfg, nodo))
        poner_mensaje(self._avisos, "\n".join(dict.fromkeys(textos_aviso)), aviso=True)

        if bloqueo:
            motivo = bloqueo
        elif errores:
            motivo = QCoreApplication.translate(
                "ResumenVM", "Corrige los datos marcados para poder crear la máquina."
            )
        else:
            motivo = ""
        self._motivo.setText(motivo)
        self._motivo.setVisible(bool(motivo))
        puede = not errores and not bloqueo and not ocupado and not self._enviado
        self.boton_crear.setEnabled(puede)
        self.boton_crear.setToolTip(motivo)

    @staticmethod
    def _avisos_recursos(cfg: ConfiguracionVM, nodo: Nodo | None) -> list[str]:
        """CA-27.1: avisa si la máquina pide más de lo que tiene el nodo (no bloquea)."""
        if nodo is None:
            return []
        avisos: list[str] = []
        total = cfg.sockets * cfg.cores
        if nodo.cpus is not None and total > nodo.cpus:
            avisos.append(
                QCoreApplication.translate(
                    "ResumenVM",
                    "Esta máquina pide más núcleos de los que tiene el servidor ({n} en el nodo).",
                ).format(n=nodo.cpus)
            )
        if nodo.mem_libre_mib is not None and cfg.memoria_mib > nodo.mem_libre_mib:
            avisos.append(
                QCoreApplication.translate(
                    "ResumenVM",
                    "Esta máquina pide más memoria de la que tiene libre el servidor "
                    "({valor} GiB libres en el nodo).",
                ).format(valor=mib_a_texto_gib(nodo.mem_libre_mib))
            )
        return avisos
