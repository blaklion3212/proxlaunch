"""Panel de resumen en lenguaje llano y botón «Crear máquina» (RF-19, CA-24.5, RF-27)."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget

from proxlaunch.interfaz.textos import (
    texto_ajustes_clon,
    texto_cambio_asistente,
    texto_campo,
    texto_modo_clon,
    texto_problema,
    texto_resumen_origen,
    texto_tipo_so,
)
from proxlaunch.interfaz.vistas.campos import mensaje, poner_mensaje
from proxlaunch.interfaz.vistas.formulario_vm import mib_a_texto_gib
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Nodo
from proxlaunch.nucleo.modelos.origen import DetalleClon, DetalleImportacion, DetalleIso, ModoClon
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    Firmware,
    FormatoDisco,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.origen.asistente import CambioAsistente
from proxlaunch.nucleo.origen.constantes import ORDEN_ARRANQUE
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.validacion import Problema, Severidad, opciones_permitidas
from proxlaunch.nucleo.valores_defecto import TIPO_CPU


def nombre_campo(campo: str) -> str:
    """Nombre corto del campo para prefijar un problema; ``""`` si no hay uno traducido (nunca
    se muestra un identificador crudo: el mensaje va sin prefijo)."""
    return texto_campo(campo)


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
        self._modo_lote = False
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

    def establecer_modo_lote(self, activo: bool) -> None:
        """Con más de una máquina el botón lleva al resumen del lote en vez de crear."""
        self._modo_lote = activo
        self.boton_crear.setText(
            QCoreApplication.translate("ResumenVM", "Ver resumen")
            if activo
            else QCoreApplication.translate("ResumenVM", "Crear máquina")
        )

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
        cambios_asistente: Sequence[CambioAsistente] = (),
        permisos: PermisosEfectivos | None = None,
    ) -> None:
        """Redibuja el resumen y decide si se puede crear."""
        e = escape
        et_nombre = QCoreApplication.translate("ResumenVM", "Nombre")
        et_vmid = QCoreApplication.translate("ResumenVM", "Número de máquina")
        et_nodo = QCoreApplication.translate("ResumenVM", "Nodo")
        et_arranque = QCoreApplication.translate("ResumenVM", "Arranque")
        et_cpu = QCoreApplication.translate("ResumenVM", "Procesadores")
        et_memoria = QCoreApplication.translate("ResumenVM", "Memoria")
        et_discos = QCoreApplication.translate("ResumenVM", "Discos")
        et_redes = QCoreApplication.translate("ResumenVM", "Redes")
        sin_disco = QCoreApplication.translate("ResumenVM", "Sin disco")
        sin_red = QCoreApplication.translate("ResumenVM", "Sin red")
        lineas: list[str] = []
        lineas.append(f"<b>{e(et_nombre)}:</b> {e(cfg.nombre) or '—'}")
        lineas.append(f"<b>{e(et_vmid)}:</b> {cfg.vmid or '—'}")
        nodo_txt = e(cfg.nodo) if cfg.nodo else "—"
        if motivo_nodo and cfg.nodo:
            nodo_txt += f" <i>({e(motivo_nodo)})</i>"
        lineas.append(f"<b>{e(et_nodo)}:</b> {nodo_txt}")
        clon = cfg.origen == OrigenSO.CLONAR_PLANTILLA
        if cfg.origen != OrigenSO.DISCO_VACIO:
            lineas.extend(self._lineas_origen(cfg, cambios_asistente, permisos, avanzado))
        if cfg.firmware == Firmware.OVMF:
            firmware = "UEFI (OVMF)"
        else:
            firmware = QCoreApplication.translate("ResumenVM", "SeaBIOS (clásico)")
        if not clon:  # un clon hereda el arranque de la plantilla
            lineas.append(f"<b>{e(et_arranque)}:</b> {e(firmware)}")
        total = QCoreApplication.translate(
            "ResumenVM", "{n} procesadores virtuales en total"
        ).format(n=cfg.sockets * cfg.cores)
        lineas.append(f"<b>{e(et_cpu)}:</b> {e(total)} ({cfg.sockets} × {cfg.cores})")
        memoria = QCoreApplication.translate("ResumenVM", "{valor} GiB").format(
            valor=mib_a_texto_gib(cfg.memoria_mib)
        )
        lineas.append(f"<b>{e(et_memoria)}:</b> {e(memoria)}")
        de_plantilla = QCoreApplication.translate("ResumenVM", "los de la plantilla")
        if clon:
            lineas.append(f"<b>{e(et_discos)}:</b> {e(de_plantilla)}")
            lineas.append(f"<b>{e(et_redes)}:</b> {e(de_plantilla)}")
        elif cfg.con_disco and cfg.discos:
            partes = []
            for i, d in enumerate(cfg.discos):
                etiqueta = etiquetas_discos[i] if i < len(etiquetas_discos) else f"#{i + 1}"
                detalle = QCoreApplication.translate(
                    "ResumenVM", "{etiqueta}: {tam} GiB en {storage}"
                ).format(etiqueta=etiqueta, tam=d.tamano_gib, storage=d.storage or "—")
                partes.append("• " + e(detalle))
            lineas.append(f"<b>{e(et_discos)}:</b><br>" + "<br>".join(partes))
        else:
            lineas.append(f"<b>{e(et_discos)}:</b> {e(sin_disco)}")
        if clon:
            pass
        elif cfg.redes:
            partes = []
            for i, r in enumerate(cfg.redes):
                vlan = f", VLAN {r.vlan}" if r.vlan is not None else ""
                partes.append(f"• net{i}: {e(r.bridge or '—')}{e(vlan)}")
            lineas.append(f"<b>{e(et_redes)}:</b><br>" + "<br>".join(partes))
        else:
            lineas.append(f"<b>{e(et_redes)}:</b> {e(sin_red)}")
        if not avanzado and not clon:
            ocultas = opciones_avanzadas_no_predeterminadas(cfg)
            if ocultas:
                titulo = QCoreApplication.translate(
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
            cuerpo = "\n".join(
                f"• {nombre_campo(p.campo)}: {texto_problema(p)}"
                if nombre_campo(p.campo)
                else f"• {texto_problema(p)}"
                for p in errores
            )
            poner_mensaje(self._pendientes, f"{cabecera}\n{cuerpo}")
        else:
            poner_mensaje(self._pendientes, None)
        textos_aviso = [texto_problema(p) for p in avisos]
        textos_aviso.extend(self._avisos_recursos(cfg, nodo))
        textos_aviso.extend(self._avisos_origen(cfg))
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
    def _lineas_origen(
        cfg: ConfiguracionVM,
        cambios: Sequence[CambioAsistente],
        permisos: PermisosEfectivos | None,
        avanzado: bool,
    ) -> list[str]:
        """Origen del SO: de dónde sale el sistema y qué hará la app (RF-O08, O13, O14, O18, O20).

        Los nombres de archivo vienen del servidor: se escapan como el resto del resumen.
        """
        e = escape
        et_origen = QCoreApplication.translate("ResumenVM", "Origen")
        lineas = [f"<b>{e(et_origen)}:</b> {e(texto_resumen_origen(cfg))}"]
        det = cfg.detalle_origen
        if isinstance(det, DetalleIso):
            lineas.append(
                e(
                    QCoreApplication.translate(
                        "ResumenVM",
                        "Montará el ISO «{iso}» como CD. ProxLaunch no enciende la máquina: "
                        "arráncala tú en Proxmox para instalar el sistema.",
                    ).format(iso=det.iso.nombre or det.iso.volid)
                )
            )
            if estado_privilegio(permisos, "VM.Config.Disk", "/vms") is True:
                nombres = {
                    "disco": QCoreApplication.translate("ResumenVM", "disco"),
                    "cd": QCoreApplication.translate("ResumenVM", "CD"),
                    "red": QCoreApplication.translate("ResumenVM", "red"),
                }
                orden = ", ".join(nombres[x] for x in ORDEN_ARRANQUE)
                lineas.append(
                    e(
                        QCoreApplication.translate(
                            "ResumenVM", "Orden de arranque: {orden}."
                        ).format(orden=orden)
                    )
                )
            if det.drivers is not None and not det.sin_drivers:
                lineas.append(
                    e(
                        QCoreApplication.translate(
                            "ResumenVM", "CD de drivers (virtio-win): {nombre}."
                        ).format(nombre=det.drivers.nombre or det.drivers.volid)
                    )
                )
                lineas.append(
                    e(
                        QCoreApplication.translate(
                            "ResumenVM",
                            "Al instalar Windows, carga los controladores desde ese CD: "
                            "vioscsi (disco), NetKVM (red) y Balloon.",
                        )
                    )
                )
        elif isinstance(det, DetalleImportacion):
            lineas.append(
                e(
                    QCoreApplication.translate(
                        "ResumenVM", "El primer disco será una copia del disco «{imagen}»."
                    ).format(imagen=det.imagen.nombre or det.imagen.volid)
                )
            )
        elif isinstance(det, DetalleClon):
            modo = det.modo_efectivo or det.modo
            lineas.append(
                e(
                    QCoreApplication.translate("ResumenVM", "Forma de copiar: {modo}.").format(
                        modo=texto_modo_clon(modo, avanzado=avanzado)
                    )
                )
            )
            ajustes = texto_ajustes_clon(cfg)
            if ajustes:
                lineas.append(
                    e(
                        QCoreApplication.translate("ResumenVM", "Ajustes: {ajustes}.").format(
                            ajustes=ajustes
                        )
                    )
                )
            if modo == ModoClon.ENLAZADO:
                lineas.append(
                    e(
                        QCoreApplication.translate(
                            "ResumenVM",
                            "La máquina depende de la plantilla: Proxmox no te dejará borrarla "
                            "mientras exista.",
                        )
                    )
                )
        if cambios and cfg.tipo_so is not None:
            titulo = QCoreApplication.translate(
                "ResumenVM", "Para {so} el asistente aplicó:"
            ).format(so=texto_tipo_so(cfg.tipo_so))
            lineas.append(
                f"<b>{e(titulo)}</b><br>"
                + "<br>".join("• " + e(texto_cambio_asistente(c)) for c in cambios)
            )
        return lineas

    @staticmethod
    def _avisos_origen(cfg: ConfiguracionVM) -> list[str]:
        """Aviso persistente de «crear sin los drivers» (CA-O14.3)."""
        det = cfg.detalle_origen
        if isinstance(det, DetalleIso) and det.sin_drivers:
            return [
                QCoreApplication.translate(
                    "ResumenVM", "Sin los drivers, Windows no verá el disco VirtIO ni la red."
                )
            ]
        return []

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
