"""Sección «Configuración inicial (cloud-init)» del formulario, solo al clonar (fase B, 0.7).

Reúne usuario, claves SSH, contraseña opcional, la red de cada tarjeta, DNS, dominio, actualizar
paquetes, scripts (snippets) y la casilla del agente invitado (RF-B1.2 a RF-B1.15, RF-B4.1). Su
API pública es la que cablea la ventana principal:

- ``configuracion() -> ConfigCloudInit | None``: lo que escribió el usuario; ``None`` si no hay
  nada que enviar (así sin cloud-init todo queda como en 0.6.0).
- ``establecer_info(info, disponibilidad)``: lo que la plantilla elegida dice de cloud-init y la
  disponibilidad (privilegios, versión) de cada opción de la fase B.
- ``limpiar_secretos()``: borra los campos de la contraseña.

La contraseña vive en dos campos enmascarados. Se valida el TEXTO EN CLARO con
``validar_contrasena`` y solo si no hay errores nace el ``Secreto``; un campo vacío da
``contrasena=None`` (nunca ``Secreto("")``). Nunca se escribe en ningún texto, aviso ni registro.
Las claves privadas se rechazan y se borran del campo al instante (RF-B1.5).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import ejemplo_snippet_agente, instrucciones_snippet_agente
from proxlaunch.interfaz.textos import (
    texto_claves_ssh,
    texto_error,
    texto_estado_opcion,
    texto_opcion_restablecida,
    texto_problema,
    texto_tipo_snippet,
)
from proxlaunch.interfaz.vistas.campos import (
    FilaCampo,
    boton_ayuda,
    etiqueta,
    mensaje,
    poner_mensaje,
)
from proxlaunch.nucleo.cloudinit.claves import (
    MotivoClave,
    analizar_claves,
    contiene_clave_privada,
    leer_archivo_pub,
)
from proxlaunch.nucleo.cloudinit.disponibilidad import OpcionB
from proxlaunch.nucleo.cloudinit.modelos import (
    INFO_DESCONOCIDA,
    NINGUNO,
    TIPOS_SNIPPET,
    ConfigCloudInit,
    InfoCloudInitPlantilla,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.cloudinit.red import normalizar_dns
from proxlaunch.nucleo.cloudinit.validacion import validar_contrasena
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import ListadoSnippets, Snippet
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.validacion import Problema, Severidad

# Valores internos de los combos (un identificador de snippet válido nunca es ninguno de ellos).
_COMO_PLANTILLA = ""
_MANUAL = "@manual"


@dataclass
class _Grupo:
    """Controles de una opción de la fase B que se habilitan o no juntos (RF-B0.3)."""

    opcion: OpcionB
    controles: list[QWidget]
    hay_valor: Callable[[], bool]
    restablecer: Callable[[], None]
    destino: Callable[[str], None]  # dónde se escribe la explicación del estado


class _Transparente(QWidget):
    """Contenedor que no pinta el fondo del QSS: se ve el del grupo, como las demás filas."""


class BloqueTarjeta(QWidget):
    """Red de una tarjeta ``netN``: modo (sin configurar, DHCP, IP fija), IP, serie y puerta."""

    cambiado = Signal()

    def __init__(self, indice: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.indice = indice
        self._habilitada = True
        self._lote = False
        self.combo_modo = QComboBox()
        self.combo_modo.addItem(QCoreApplication.translate("SeccionCloudInit", "Sin configurar"))
        self.combo_modo.setItemData(0, ModoTarjeta.SIN_CONFIGURAR)
        self.combo_modo.addItem(QCoreApplication.translate("SeccionCloudInit", "DHCP"))
        self.combo_modo.setItemData(1, ModoTarjeta.DHCP)
        self.combo_modo.addItem(QCoreApplication.translate("SeccionCloudInit", "IP fija"))
        self.combo_modo.setItemData(2, ModoTarjeta.FIJA)
        titulo = QCoreApplication.translate(
            "SeccionCloudInit", "Tarjeta de red {n} (net{i})"
        ).format(n=indice + 1, i=indice)
        self.combo_modo.setAccessibleName(titulo)
        self.txt_ip = QLineEdit()
        self.txt_ip.setPlaceholderText(
            QCoreApplication.translate("SeccionCloudInit", "por ejemplo 192.168.1.50/24")
        )
        self.txt_ip.setAccessibleName(
            QCoreApplication.translate("SeccionCloudInit", "IP de la tarjeta {n}").format(
                n=indice + 1
            )
        )
        self.chk_serie = QCheckBox(
            QCoreApplication.translate("SeccionCloudInit", "Sumar 1 a cada máquina del lote")
        )
        self.chk_serie.setChecked(True)  # en un lote la serie viene marcada (RF-B1.9)
        self.txt_puerta = QLineEdit()
        self.txt_puerta.setPlaceholderText(
            QCoreApplication.translate("SeccionCloudInit", "por ejemplo 192.168.1.1")
        )
        self.txt_puerta.setAccessibleName(
            QCoreApplication.translate(
                "SeccionCloudInit", "Puerta de enlace de la tarjeta {n}"
            ).format(n=indice + 1)
        )
        self.lbl_heredado = etiqueta("", secundario=True)
        self.lbl_heredado.hide()
        self.fila_modo = FilaCampo(titulo, self.combo_modo, "ci_red")
        self.fila_ip = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "IP con máscara"),
            self.txt_ip,
            "ci_ip",
        )
        self.fila_serie = FilaCampo("", self.chk_serie, "ci_serie")
        self.fila_puerta = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "Puerta de enlace"),
            self.txt_puerta,
            "ci_puerta",
        )
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(2)
        for w in (
            self.fila_modo,
            self.lbl_heredado,
            self.fila_ip,
            self.fila_serie,
            self.fila_puerta,
        ):
            capa.addWidget(w)
        self.combo_modo.currentIndexChanged.connect(self._al_cambiar_modo)
        self.txt_ip.textEdited.connect(lambda _t: self._al_editar(self.fila_ip))
        self.txt_ip.editingFinished.connect(self.fila_ip.marcar_tocado)
        self.txt_puerta.textEdited.connect(lambda _t: self._al_editar(self.fila_puerta))
        self.txt_puerta.editingFinished.connect(self.fila_puerta.marcar_tocado)
        self.chk_serie.toggled.connect(lambda _m: self.cambiado.emit())
        self._refrescar()

    # --- Estado --------------------------------------------------------------------------

    @property
    def modo(self) -> ModoTarjeta:
        return ModoTarjeta(self.combo_modo.currentData())

    def _al_editar(self, fila: FilaCampo) -> None:
        fila.marcar_tocado()
        self.cambiado.emit()

    def _al_cambiar_modo(self, _i: int) -> None:
        self.fila_modo.marcar_tocado()
        self._refrescar()
        self.cambiado.emit()

    def _refrescar(self) -> None:
        """IP y puerta solo valen con IP fija (CA-B1.7.3); la serie solo en un lote."""
        fija = self.modo == ModoTarjeta.FIJA
        self.combo_modo.setEnabled(self._habilitada)
        self.txt_ip.setEnabled(self._habilitada and fija)
        self.txt_puerta.setEnabled(self._habilitada and fija)
        self.chk_serie.setEnabled(self._habilitada and fija)
        self.fila_serie.setVisible(self._lote and fija)
        self.txt_ip.setPlaceholderText(
            QCoreApplication.translate(
                "SeccionCloudInit", "IP de la primera máquina, por ejemplo 192.168.1.50/24"
            )
            if self._lote
            else QCoreApplication.translate("SeccionCloudInit", "por ejemplo 192.168.1.50/24")
        )

    def habilitar(self, habilitada: bool) -> None:
        self._habilitada = habilitada
        self._refrescar()

    def establecer_lote(self, activo: bool) -> None:
        self._lote = activo
        self._refrescar()

    def establecer_heredado(self, texto: str | None) -> None:
        """«Heredado de la plantilla: ip=dhcp» como ayuda; el campo sigue vacío (CA-B1.2.5)."""
        self.lbl_heredado.setText(
            QCoreApplication.translate(
                "SeccionCloudInit", "Heredado de la plantilla: {valor}"
            ).format(valor=texto)
            if texto
            else ""
        )
        self.lbl_heredado.setVisible(bool(texto))

    # --- Valor ---------------------------------------------------------------------------

    def tarjeta(self) -> TarjetaCloudInit | None:
        """La tarjeta tal como la escribió el usuario; ``None`` = «Sin configurar»."""
        modo = self.modo
        if modo == ModoTarjeta.SIN_CONFIGURAR:
            return None
        if modo == ModoTarjeta.DHCP:
            return TarjetaCloudInit(self.indice, ModoTarjeta.DHCP)
        ip = self.txt_ip.text().strip()
        puerta = self.txt_puerta.text().strip()
        return TarjetaCloudInit(
            self.indice,
            ModoTarjeta.FIJA,
            ip=ip or None,
            serie=self._lote and self.chk_serie.isChecked(),
            puerta=puerta or None,
        )

    def aplicar(self, t: TarjetaCloudInit | None) -> None:
        """Vuelca una tarjeta (lote guardado, «Crear otra») sin emitir ``cambiado``."""
        bloqueado = self.blockSignals(True)
        try:
            self.combo_modo.setCurrentIndex(
                max(self.combo_modo.findData(t.modo if t else ModoTarjeta.SIN_CONFIGURAR), 0)
            )
            self.txt_ip.setText(t.ip or "" if t else "")
            self.txt_puerta.setText(t.puerta or "" if t else "")
            self.chk_serie.setChecked(True if t is None else t.serie)
            self._refrescar()
        finally:
            self.blockSignals(bloqueado)

    def hay_valor(self) -> bool:
        return (
            self.modo != ModoTarjeta.SIN_CONFIGURAR
            or bool(self.txt_ip.text().strip())
            or bool(self.txt_puerta.text().strip())
        )

    def restablecer(self) -> None:
        self.aplicar(None)


class SelectorSnippet(QWidget):
    """Un tipo de script (user, vendor, network o meta): lista del servidor o identificador."""

    cambiado = Signal()

    def __init__(self, tipo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tipo = tipo
        self.combo = QComboBox()
        self.combo.setAccessibleName(texto_tipo_snippet(tipo))
        self.txt_manual = QLineEdit()
        self.txt_manual.setPlaceholderText(
            QCoreApplication.translate("SeccionCloudInit", "almacén:snippets/archivo")
        )
        self.txt_manual.setAccessibleName(
            QCoreApplication.translate(
                "SeccionCloudInit", "Identificador del script ({tipo})"
            ).format(tipo=texto_tipo_snippet(tipo))
        )
        self.lbl_heredado = etiqueta("", secundario=True)
        self.lbl_heredado.hide()
        contenedor = _Transparente()
        capa_c = QVBoxLayout(contenedor)
        capa_c.setContentsMargins(0, 0, 0, 0)
        capa_c.setSpacing(2)
        capa_c.addWidget(self.combo)
        capa_c.addWidget(self.txt_manual)
        capa_c.addWidget(self.lbl_heredado)
        self.fila = FilaCampo(texto_tipo_snippet(tipo), contenedor, "snippets")
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(self.fila)
        self._rellenar([])
        self.combo.currentIndexChanged.connect(self._al_cambiar)
        self.txt_manual.textEdited.connect(self._al_editar_manual)

    def _al_cambiar(self, _i: int) -> None:
        self.fila.marcar_tocado()
        self._actualizar_manual()
        self.cambiado.emit()

    def _al_editar_manual(self, _t: str) -> None:
        self.fila.marcar_tocado()
        self.cambiado.emit()

    def _actualizar_manual(self) -> None:
        self.txt_manual.setVisible(self.combo.currentData() == _MANUAL)

    def _rellenar(self, snippets: Sequence[Snippet]) -> None:
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            self.combo.addItem(QCoreApplication.translate("SeccionCloudInit", "Como la plantilla"))
            self.combo.setItemData(0, _COMO_PLANTILLA)
            self.combo.addItem(QCoreApplication.translate("SeccionCloudInit", "Ninguno"))
            self.combo.setItemData(1, NINGUNO)
            for sn in snippets:
                texto = sn.volid
                if not sn.admitido:
                    texto += QCoreApplication.translate(
                        "SeccionCloudInit", " (demasiado grande: máximo 1 MiB)"
                    )
                self.combo.addItem(texto)
                idx = self.combo.count() - 1
                self.combo.setItemData(idx, sn.volid)
                modelo = self.combo.model()
                if not sn.admitido and isinstance(modelo, QStandardItemModel):
                    item = modelo.item(idx)
                    if item is not None:
                        item.setEnabled(False)
            self.combo.addItem(QCoreApplication.translate("SeccionCloudInit", "Escribir a mano…"))
            self.combo.setItemData(self.combo.count() - 1, _MANUAL)
        finally:
            self.combo.blockSignals(False)
        self._actualizar_manual()

    def establecer_opciones(self, snippets: Sequence[Snippet]) -> None:
        """Rellena la lista con los scripts del servidor; conserva lo elegido (si ya no está en la
        lista, pasa a entrada manual con ese identificador)."""
        actual = self.valor()
        self._rellenar(snippets)
        self.establecer_valor(actual)

    def valor(self) -> str | None:
        """``None`` = como la plantilla; ``NINGUNO``; o el identificador elegido o escrito."""
        dato = self.combo.currentData()
        if dato == _COMO_PLANTILLA or dato is None:
            return None
        if dato == _MANUAL:
            return self.txt_manual.text().strip() or None
        return str(dato)

    def establecer_valor(self, valor: str | None) -> None:
        bloqueado = self.combo.blockSignals(True)
        try:
            if valor is None:
                self.combo.setCurrentIndex(0)
                self.txt_manual.clear()
            elif valor == NINGUNO:
                self.combo.setCurrentIndex(1)
                self.txt_manual.clear()
            else:
                idx = self.combo.findData(valor)
                if idx >= 0:
                    self.combo.setCurrentIndex(idx)
                    self.txt_manual.clear()
                else:
                    self.combo.setCurrentIndex(max(self.combo.findData(_MANUAL), 0))
                    self.txt_manual.setText(valor)
        finally:
            self.combo.blockSignals(bloqueado)
        self._actualizar_manual()

    def hay_valor(self) -> bool:
        return self.combo.currentData() != _COMO_PLANTILLA or bool(self.txt_manual.text().strip())

    def habilitar(self, habilitado: bool) -> None:
        self.combo.setEnabled(habilitado)
        self.txt_manual.setEnabled(habilitado)

    def establecer_heredado(self, texto: str | None) -> None:
        self.lbl_heredado.setText(
            QCoreApplication.translate(
                "SeccionCloudInit", "Heredado de la plantilla: {valor}"
            ).format(valor=texto)
            if texto
            else ""
        )
        self.lbl_heredado.setVisible(bool(texto))


class SeccionCloudInit(QGroupBox):
    """Grupo «Configuración inicial (cloud-init)». Ver el módulo para la API pública."""

    cambiado = Signal()  # el usuario cambió algo: hay que revalidar

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            QCoreApplication.translate("SeccionCloudInit", "Configuración inicial (cloud-init)"),
            parent,
        )
        self._info: InfoCloudInitPlantilla | None = None
        self._disp: dict[OpcionB, EstadoOpcion] = {}
        self._ultimo_estado: object = None
        self._avanzado = False
        self._lote = False
        self._esperar_ip = False
        self._ocupado = False  # relleno por código: no se emite ``cambiado``
        self._secreto: Secreto | None = None
        self._privada = (
            False  # se rechazó una clave privada: el aviso queda hasta la próxima edición
        )
        self._errores_archivo: list[str] = []
        self._listados: Sequence[ListadoSnippets] = ()
        self._snippets_pendientes = False
        self._tarjetas: dict[int, BloqueTarjeta] = {}
        self._avanzados: list[QWidget] = []
        self._grupos: list[_Grupo] = []
        self._texto_estado: dict[int, str] = {}
        self._texto_validacion: dict[int, str] = {}

        capa = QVBoxLayout(self)
        capa.setSpacing(4)
        self._construir_cabecera(capa)
        self._construir_basico(capa)
        self._construir_avanzado(capa)
        self._registrar_grupos()
        self.establecer_info(None, {})
        self._aplicar_modo()

    # --- Construcción --------------------------------------------------------------------

    def _construir_cabecera(self, capa: QVBoxLayout) -> None:
        intro = etiqueta(
            QCoreApplication.translate(
                "SeccionCloudInit",
                "Cloud-init configura la máquina sola en su primer arranque con los datos que "
                "pongas aquí (usuario, claves, red). Todo es opcional: lo que dejes vacío se "
                "queda como lo tiene la plantilla.",
            ),
            secundario=True,
        )
        cabecera = QHBoxLayout()
        cabecera.addWidget(intro, 1)
        cabecera.addWidget(boton_ayuda("cloudinit"))
        capa.addLayout(cabecera)
        self._motivo = mensaje(aviso=True)
        self._avisos_reset = mensaje(aviso=True)
        self._global = mensaje(error=True)
        self._global_aviso = mensaje(aviso=True)
        for w in (self._motivo, self._avisos_reset, self._global, self._global_aviso):
            capa.addWidget(w)

    def _construir_basico(self, capa: QVBoxLayout) -> None:
        self.txt_usuario = QLineEdit()
        self.txt_usuario.setAccessibleName(
            QCoreApplication.translate("SeccionCloudInit", "Usuario")
        )
        self.txt_usuario.setPlaceholderText(
            QCoreApplication.translate("SeccionCloudInit", "por ejemplo deploy")
        )
        self.fila_usuario = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "Usuario"),
            self.txt_usuario,
            "ci_usuario",
        )
        # Claves SSH: texto, archivos .pub y resumen (nunca el cuerpo).
        self.txt_claves = QPlainTextEdit()
        self.txt_claves.setAccessibleName(
            QCoreApplication.translate("SeccionCloudInit", "Claves SSH públicas")
        )
        self.txt_claves.setPlaceholderText(
            QCoreApplication.translate(
                "SeccionCloudInit",
                "Una clave pública por línea, por ejemplo: ssh-ed25519 AAAAC3Nza… ana@portatil",
            )
        )
        self.txt_claves.setTabChangesFocus(True)
        self.txt_claves.setFixedHeight(84)
        self.btn_archivo_pub = QPushButton(
            QCoreApplication.translate("SeccionCloudInit", "Añadir archivo .pub…")
        )
        self.btn_archivo_pub.setToolTip(
            QCoreApplication.translate(
                "SeccionCloudInit",
                "Lee la clave pública de uno o varios archivos .pub (suelen estar en la carpeta "
                ".ssh de tu usuario).",
            )
        )
        self.lbl_resumen_claves = etiqueta("", secundario=True)
        self.lbl_resumen_claves.hide()
        self.lbl_error_claves = mensaje(error=True)
        contenedor = _Transparente()
        cc = QVBoxLayout(contenedor)
        cc.setContentsMargins(0, 0, 0, 0)
        cc.setSpacing(2)
        cc.addWidget(self.txt_claves)
        botones = QHBoxLayout()
        botones.addWidget(self.btn_archivo_pub)
        botones.addStretch(1)
        cc.addLayout(botones)
        cc.addWidget(self.lbl_resumen_claves)
        cc.addWidget(self.lbl_error_claves)
        self.fila_claves = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "Claves SSH"), contenedor, "ci_claves"
        )
        # Contraseña opcional (PB-1): dos campos enmascarados y aviso fijo.
        self.txt_contrasena = QLineEdit()
        self.txt_contrasena.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_contrasena.setAccessibleName(
            QCoreApplication.translate("SeccionCloudInit", "Contraseña")
        )
        self.txt_contrasena.setPlaceholderText(
            QCoreApplication.translate("SeccionCloudInit", "Contraseña")
        )
        self.txt_repeticion = QLineEdit()
        self.txt_repeticion.setPlaceholderText(
            QCoreApplication.translate("SeccionCloudInit", "Repite la contraseña")
        )
        self.txt_repeticion.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_repeticion.setAccessibleName(
            QCoreApplication.translate("SeccionCloudInit", "Repetir la contraseña")
        )
        self.chk_mostrar = QCheckBox(QCoreApplication.translate("SeccionCloudInit", "Mostrar"))
        self.chk_mostrar.setToolTip(
            QCoreApplication.translate(
                "SeccionCloudInit", "Muestra las contraseñas mientras las escribes."
            )
        )
        self.lbl_aviso_contrasena = etiqueta(
            QCoreApplication.translate(
                "SeccionCloudInit",
                "Las claves SSH son más seguras. La contraseña sirve para entrar por la consola "
                "de Proxmox si falla la red; quien tenga acceso a la consola o a la "
                "configuración podría obtenerla. Úsala solo para pruebas o como último recurso.",
            ),
            secundario=True,
        )
        cont_pw = _Transparente()
        cp = QVBoxLayout(cont_pw)
        cp.setContentsMargins(0, 0, 0, 0)
        cp.setSpacing(2)
        fila_pw = QHBoxLayout()
        fila_pw.addWidget(self.txt_contrasena, 1)
        fila_pw.addWidget(self.chk_mostrar)
        cp.addLayout(fila_pw)
        cp.addWidget(self.txt_repeticion)
        cp.addWidget(self.lbl_aviso_contrasena)
        self.fila_contrasena = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "Contraseña (opcional)"),
            cont_pw,
            "ci_contrasena",
        )
        # Una tarjeta por ``netN`` de la plantilla.
        self._caja_tarjetas = _Transparente()
        self._capa_tarjetas = QVBoxLayout(self._caja_tarjetas)
        self._capa_tarjetas.setContentsMargins(0, 0, 0, 0)
        self._capa_tarjetas.setSpacing(6)
        # Agente invitado (RF-B1.15): solo con «Esperar la IP» y una plantilla sin agente.
        self.chk_agente = QCheckBox()
        self.chk_agente.setAccessibleName(
            QCoreApplication.translate(
                "SeccionCloudInit", "Activar el agente invitado en la máquina"
            )
        )
        self.fila_agente = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "Activar el agente invitado"),
            self.chk_agente,
            "ci_activar_agente",
        )
        for w in (
            self.fila_usuario,
            self.fila_claves,
            self.fila_contrasena,
            self._caja_tarjetas,
            self.fila_agente,
        ):
            capa.addWidget(w)
        self.txt_usuario.textEdited.connect(lambda _t: self._al_editar(self.fila_usuario))
        self.txt_usuario.editingFinished.connect(self.fila_usuario.marcar_tocado)
        self.txt_claves.textChanged.connect(self._al_cambiar_claves)
        self.btn_archivo_pub.clicked.connect(self._elegir_archivos_pub)
        self.txt_contrasena.textEdited.connect(self._al_editar_contrasena)
        self.txt_repeticion.textEdited.connect(self._al_editar_contrasena)
        self.txt_repeticion.editingFinished.connect(self.fila_contrasena.marcar_tocado)
        self.chk_mostrar.toggled.connect(self._mostrar_contrasenas)
        self.chk_agente.toggled.connect(lambda _m: self._emitir())

    def _construir_avanzado(self, capa: QVBoxLayout) -> None:
        self.txt_dns = QLineEdit()
        self.txt_dns.setAccessibleName(QCoreApplication.translate("SeccionCloudInit", "DNS"))
        self.txt_dns.setPlaceholderText(
            QCoreApplication.translate("SeccionCloudInit", "por ejemplo 1.1.1.1, 8.8.8.8")
        )
        self.fila_dns = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "Servidores DNS"), self.txt_dns, "ci_dns"
        )
        self.txt_dominio = QLineEdit()
        self.txt_dominio.setAccessibleName(
            QCoreApplication.translate("SeccionCloudInit", "Dominio de búsqueda")
        )
        self.txt_dominio.setPlaceholderText(
            QCoreApplication.translate("SeccionCloudInit", "por ejemplo lab.local")
        )
        self.fila_dominio = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "Dominio de búsqueda"),
            self.txt_dominio,
            "ci_dominio",
        )
        self.combo_actualizar = QComboBox()
        self.combo_actualizar.addItem(
            QCoreApplication.translate("SeccionCloudInit", "Como la plantilla")
        )
        self.combo_actualizar.setItemData(0, None)
        self.combo_actualizar.addItem(QCoreApplication.translate("SeccionCloudInit", "Sí"))
        self.combo_actualizar.setItemData(1, True)
        self.combo_actualizar.addItem(QCoreApplication.translate("SeccionCloudInit", "No"))
        self.combo_actualizar.setItemData(2, False)
        self.combo_actualizar.setAccessibleName(
            QCoreApplication.translate(
                "SeccionCloudInit", "Actualizar paquetes en el primer arranque"
            )
        )
        self.lbl_heredado_actualizar = etiqueta("", secundario=True)
        self.lbl_heredado_actualizar.hide()
        cont_act = _Transparente()
        ca = QVBoxLayout(cont_act)
        ca.setContentsMargins(0, 0, 0, 0)
        ca.setSpacing(2)
        ca.addWidget(self.combo_actualizar)
        ca.addWidget(self.lbl_heredado_actualizar)
        self.fila_actualizar = FilaCampo(
            QCoreApplication.translate("SeccionCloudInit", "Actualizar paquetes"),
            cont_act,
            "ci_actualizar",
        )
        # Scripts (snippets): título, ayuda, aviso de listado y los cuatro tipos.
        self.caja_snippets = _Transparente()
        cs = QVBoxLayout(self.caja_snippets)
        cs.setContentsMargins(0, 0, 0, 0)
        cs.setSpacing(2)
        titulo = etiqueta(
            QCoreApplication.translate("SeccionCloudInit", "Scripts de configuración (avanzado)"),
        )
        fuente = titulo.font()
        fuente.setBold(True)
        titulo.setFont(fuente)
        explicacion = etiqueta(
            QCoreApplication.translate(
                "SeccionCloudInit",
                "Un script (snippet) es un archivo de texto guardado en el servidor que "
                "cloud-init usa para configurar la máquina, por ejemplo para instalar el agente "
                "invitado. ProxLaunch no los crea ni los sube: los deja tu administrador.",
            ),
            secundario=True,
        )
        cab = QHBoxLayout()
        cab.addWidget(titulo, 1)
        cab.addWidget(boton_ayuda("snippets"))
        cs.addLayout(cab)
        cs.addWidget(explicacion)
        self._motivo_snippets = mensaje(aviso=True)
        self._aviso_listado = mensaje(aviso=True)
        self._error_snippets = mensaje(error=True)
        for w in (self._motivo_snippets, self._aviso_listado, self._error_snippets):
            cs.addWidget(w)
        self.selectores_snippet: dict[str, SelectorSnippet] = {}
        for tipo in TIPOS_SNIPPET:
            sel = SelectorSnippet(tipo)
            sel.cambiado.connect(self._emitir)
            self.selectores_snippet[tipo] = sel
            cs.addWidget(sel)
        self.btn_ejemplo = QPushButton(
            QCoreApplication.translate(
                "SeccionCloudInit", "Ver ejemplo para instalar el agente invitado…"
            )
        )
        self.btn_ejemplo.setCheckable(True)
        self.caja_ejemplo = _Transparente()
        ce = QVBoxLayout(self.caja_ejemplo)
        ce.setContentsMargins(0, 0, 0, 0)
        ce.setSpacing(2)
        self.txt_ejemplo = QPlainTextEdit(ejemplo_snippet_agente())
        self.txt_ejemplo.setReadOnly(True)
        self.txt_ejemplo.setProperty("mono", True)
        self.txt_ejemplo.setAccessibleName(
            QCoreApplication.translate("SeccionCloudInit", "Ejemplo de script para el agente")
        )
        self.txt_ejemplo.setFixedHeight(120)
        self.btn_copiar_ejemplo = QPushButton(
            QCoreApplication.translate("SeccionCloudInit", "Copiar")
        )
        ce.addWidget(
            etiqueta(
                QCoreApplication.translate(
                    "SeccionCloudInit",
                    "Ejemplo de script «Datos del proveedor» (vendor) que instala y activa el "
                    "agente invitado:",
                ),
                secundario=True,
            )
        )
        ce.addWidget(self.txt_ejemplo)
        ce.addWidget(etiqueta(instrucciones_snippet_agente(), secundario=True))
        fila_copiar = QHBoxLayout()
        fila_copiar.addWidget(self.btn_copiar_ejemplo)
        fila_copiar.addStretch(1)
        ce.addLayout(fila_copiar)
        self.caja_ejemplo.hide()
        cs.addWidget(self.btn_ejemplo)
        cs.addWidget(self.caja_ejemplo)
        for bloque in (self.fila_dns, self.fila_dominio, self.fila_actualizar, self.caja_snippets):
            capa.addWidget(bloque)
            self._avanzados.append(bloque)
        self.txt_dns.textEdited.connect(lambda _t: self._al_editar(self.fila_dns))
        self.txt_dns.editingFinished.connect(self.fila_dns.marcar_tocado)
        self.txt_dominio.textEdited.connect(lambda _t: self._al_editar(self.fila_dominio))
        self.txt_dominio.editingFinished.connect(self.fila_dominio.marcar_tocado)
        self.combo_actualizar.currentIndexChanged.connect(lambda _i: self._emitir())
        self.btn_ejemplo.toggled.connect(self.caja_ejemplo.setVisible)
        self.btn_copiar_ejemplo.clicked.connect(self.copiar_ejemplo)

    def _registrar_grupos(self) -> None:
        """Cada opción de la fase B con los controles que se habilitan juntos (RF-B0.3)."""
        self._grupos = [
            _Grupo(
                OpcionB.CLOUDINIT,
                [
                    self.txt_usuario,
                    self.txt_claves,
                    self.btn_archivo_pub,
                    self.combo_actualizar,
                ],
                self._hay_valor_cloudinit,
                self._restablecer_cloudinit,
                lambda t: poner_mensaje(self._motivo, t or None, aviso=True),
            ),
            _Grupo(
                OpcionB.CONTRASENA,
                [self.txt_contrasena, self.txt_repeticion, self.chk_mostrar],
                lambda: bool(self.txt_contrasena.text() or self.txt_repeticion.text()),
                self._restablecer_contrasena,
                lambda t: self._poner_estado(self.fila_contrasena, t),
            ),
            _Grupo(
                OpcionB.DNS_DOMINIO,
                [self.txt_dns, self.txt_dominio],
                lambda: bool(self.txt_dns.text().strip() or self.txt_dominio.text().strip()),
                self._restablecer_dns,
                lambda t: self._poner_estado(self.fila_dns, t),
            ),
            _Grupo(
                OpcionB.SNIPPETS,
                [],
                lambda: any(s.hay_valor() for s in self.selectores_snippet.values()),
                self._restablecer_snippets,
                lambda t: poner_mensaje(self._motivo_snippets, t or None, aviso=True),
            ),
            _Grupo(
                OpcionB.ACTIVAR_AGENTE,
                [self.chk_agente],
                self.chk_agente.isChecked,
                lambda: self.chk_agente.setChecked(False),
                lambda t: self._poner_estado(self.fila_agente, t),
            ),
        ]

    # --- Utilidades de filas -------------------------------------------------------------

    def _poner_estado(self, fila: FilaCampo, texto: str) -> None:
        self._texto_estado[id(fila)] = texto
        self._refrescar_aviso(fila)

    def _refrescar_aviso(self, fila: FilaCampo) -> None:
        textos = [
            t
            for t in (
                self._texto_estado.get(id(fila), ""),
                self._texto_validacion.get(id(fila), ""),
            )
            if t
        ]
        fila.mostrar_aviso("\n".join(textos) or None)

    def _al_editar(self, fila: FilaCampo) -> None:
        fila.marcar_tocado()
        self._emitir()

    def _emitir(self) -> None:
        if not self._ocupado:
            self.cambiado.emit()

    # --- Modo y lote ---------------------------------------------------------------------

    def establecer_modo(self, avanzado: bool) -> None:
        """Muestra u oculta lo avanzado (DNS, dominio, actualizar y scripts); no borra valores."""
        self._avanzado = avanzado
        self._aplicar_modo()

    def _aplicar_modo(self) -> None:
        for w in self._avanzados:
            w.setVisible(self._avanzado)

    def establecer_lote(self, activo: bool) -> None:
        """En un lote, una IP fija puede sumarse de 1 en 1 a cada máquina (RF-B1.9)."""
        self._lote = activo
        for t in self._tarjetas.values():
            t.establecer_lote(activo)

    def establecer_esperar_ip(self, activo: bool) -> None:
        """La casilla del agente solo aparece con «Esperar la IP» (RF-B1.15)."""
        self._esperar_ip = activo
        self._actualizar_agente()

    def _actualizar_agente(self) -> None:
        info = self._info or INFO_DESCONOCIDA
        visible = self._esperar_ip and info.agente is not True
        self.fila_agente.setVisible(visible)
        if not visible and self.chk_agente.isChecked():
            self.chk_agente.setChecked(False)

    # --- Información de la plantilla y disponibilidad -------------------------------------

    def establecer_info(
        self,
        info: InfoCloudInitPlantilla | None,
        disponibilidad: Mapping[OpcionB, EstadoOpcion],
    ) -> None:
        """Lo que dice la plantilla elegida (``None`` = desconocida) y qué está disponible.

        Deshabilita y explica lo que no se puede usar (sin unidad, sin privilegio, Windows, sin
        almacenamiento de snippets). Una tarjeta que la plantilla anterior tenía y la nueva no,
        y lo que quedó deshabilitado con un valor, vuelven a su valor por defecto con un aviso
        (CA-B1.2.4). Es barato: si nada cambió desde la última llamada no hace nada.
        """
        estado = (info, dict(disponibilidad), self._snippets_clave())
        if estado == self._ultimo_estado:
            return
        self._ultimo_estado = estado
        previa = self._info
        self._info = info
        self._disp = dict(disponibilidad)
        previo, self._ocupado = self._ocupado, True
        avisos: list[str] = []
        try:
            avisos.extend(self._reconstruir_tarjetas(previa, info))
            self._mostrar_heredados(info)
            self._aplicar_disponibilidad(avisos)
            self._actualizar_agente()
            self._rellenar_snippets()
        finally:
            self._ocupado = previo
        poner_mensaje(self._avisos_reset, "\n".join(avisos) or None, aviso=True)
        if avisos and not previo:
            self.cambiado.emit()

    def _snippets_clave(self) -> object:
        return (
            self._snippets_pendientes,
            [
                (ls.nodo, ls.storage, ls.error is not None, tuple(s.volid for s in ls.snippets))
                for ls in self._listados
            ],
        )

    def _indices_de(self, info: InfoCloudInitPlantilla | None) -> tuple[int, ...]:
        return tuple(sorted(set(info.tarjetas))) if info is not None and info.tarjetas else (0,)

    def _reconstruir_tarjetas(
        self, previa: InfoCloudInitPlantilla | None, info: InfoCloudInitPlantilla | None
    ) -> list[str]:
        """Una tarjeta por ``netN`` de la plantilla (CA-B1.7.6); devuelve los avisos de reinicio."""
        avisos: list[str] = []
        nuevas = set(self._indices_de(info))
        tenia = set(previa.tarjetas) if previa is not None else set()
        for idx in list(self._tarjetas):
            bloque = self._tarjetas[idx]
            if idx in nuevas:
                continue
            if bloque.hay_valor() and idx not in tenia:
                continue  # valor cargado de un archivo: V-B34 lo señalará
            if bloque.hay_valor():
                avisos.append(
                    QCoreApplication.translate(
                        "SeccionCloudInit",
                        "Se restableció la tarjeta de red {n}: la plantilla elegida no la tiene.",
                    ).format(n=idx + 1)
                )
            self._capa_tarjetas.removeWidget(bloque)
            bloque.deleteLater()
            del self._tarjetas[idx]
        for idx in sorted(nuevas):
            self._asegurar_tarjeta(idx)
        self._ordenar_tarjetas()
        return avisos

    def _asegurar_tarjeta(self, idx: int) -> None:
        if idx in self._tarjetas:
            return
        bloque = BloqueTarjeta(idx)
        bloque.establecer_lote(self._lote)
        bloque.cambiado.connect(self._emitir)
        self._tarjetas[idx] = bloque

    def _ordenar_tarjetas(self) -> None:
        for pos, idx in enumerate(sorted(self._tarjetas)):
            self._capa_tarjetas.insertWidget(pos, self._tarjetas[idx])

    def _mostrar_heredados(self, info: InfoCloudInitPlantilla | None) -> None:
        """«Heredado de la plantilla: …» como ayuda; los campos siguen vacíos (CA-B1.2.5)."""
        heredados = dict(info.heredados) if info is not None else {}
        usuario = heredados.get("ciuser")
        self.txt_usuario.setPlaceholderText(
            QCoreApplication.translate(
                "SeccionCloudInit", "Heredado de la plantilla: {valor}"
            ).format(valor=usuario)
            if usuario
            else QCoreApplication.translate("SeccionCloudInit", "por ejemplo deploy")
        )
        for idx, bloque in self._tarjetas.items():
            bloque.establecer_heredado(heredados.get(f"ipconfig{idx}"))
        dns = heredados.get("nameserver")
        self.txt_dns.setPlaceholderText(
            QCoreApplication.translate(
                "SeccionCloudInit", "Heredado de la plantilla: {valor}"
            ).format(valor=dns)
            if dns
            else QCoreApplication.translate("SeccionCloudInit", "por ejemplo 1.1.1.1, 8.8.8.8")
        )
        dominio = heredados.get("searchdomain")
        self.txt_dominio.setPlaceholderText(
            QCoreApplication.translate(
                "SeccionCloudInit", "Heredado de la plantilla: {valor}"
            ).format(valor=dominio)
            if dominio
            else QCoreApplication.translate("SeccionCloudInit", "por ejemplo lab.local")
        )
        upgrade = heredados.get("ciupgrade")
        self.lbl_heredado_actualizar.setText(
            QCoreApplication.translate(
                "SeccionCloudInit", "Heredado de la plantilla: {valor}"
            ).format(valor=upgrade)
            if upgrade
            else ""
        )
        self.lbl_heredado_actualizar.setVisible(bool(upgrade))
        tipos = dict(info.cicustom.tipos) if info is not None and info.cicustom else {}
        for tipo, sel in self.selectores_snippet.items():
            sel.establecer_heredado(tipos.get(tipo))

    def _aplicar_disponibilidad(self, avisos: list[str]) -> None:
        """Habilita o deshabilita cada grupo y escribe por qué (RF-B0.3, CA-B0.6.2)."""
        ci = self._disp.get(OpcionB.CLOUDINIT)
        ci_no = ci is not None and ci.disponibilidad == Disponibilidad.NO
        for g in self._grupos:
            estado = self._disp.get(g.opcion)
            bloqueada = estado is not None and estado.disponibilidad == Disponibilidad.NO
            texto = texto_estado_opcion(estado) if estado is not None else ""
            for w in g.controles:
                w.setEnabled(not bloqueada)
                w.setAccessibleDescription(texto)
            if g.opcion == OpcionB.CLOUDINIT:
                for t in self._tarjetas.values():
                    t.habilitar(not bloqueada)
            if g.opcion == OpcionB.SNIPPETS:
                for sel in self.selectores_snippet.values():
                    sel.habilitar(not bloqueada)
            if bloqueada and g.hay_valor():
                g.restablecer()
                texto = texto_opcion_restablecida(g.opcion.value, texto)
                avisos.append(texto)
            if g.opcion != OpcionB.CLOUDINIT and ci_no and _misma_causa(estado, ci):
                texto = ""  # el motivo general ya está arriba: no se repite en cada fila
            g.destino(texto)

    # --- Claves SSH ---------------------------------------------------------------------

    def _al_cambiar_claves(self) -> None:
        if self._ocupado:
            return
        texto = self.txt_claves.toPlainText()
        if contiene_clave_privada(texto):
            self._rechazar_privada()
            return
        self._privada = False
        self.fila_claves.marcar_tocado()
        self._actualizar_resumen_claves()
        self._emitir()

    def _rechazar_privada(self) -> None:
        """Una clave privada se rechaza entera y se borra del campo al instante (RF-B1.5)."""
        self._ocupado = True
        try:
            self.txt_claves.clear()  # clear() también vacía el historial de deshacer
        finally:
            self._ocupado = False
        self._privada = True
        self._errores_archivo = []
        self._actualizar_resumen_claves()
        self._emitir()

    def _actualizar_resumen_claves(self) -> None:
        """Resumen de las claves (tipo y comentario, nunca el cuerpo) y errores de línea."""
        resultado = analizar_claves(self.txt_claves.toPlainText())
        partes: list[str] = []
        if resultado.claves:
            partes.append(texto_claves_ssh(resultado.claves))
        if resultado.duplicadas:
            partes.append(
                texto_problema(
                    Problema(
                        "cloudinit.claves",
                        "V-B24",
                        Severidad.AVISO,
                        {"motivo": "duplicadas", "cantidad": str(resultado.duplicadas)},
                    )
                )
            )
        self.lbl_resumen_claves.setText("\n".join(partes))
        self.lbl_resumen_claves.setVisible(bool(partes))
        self._mostrar_error_claves()

    def _mostrar_error_claves(self) -> None:
        if self._privada:
            poner_mensaje(self.lbl_error_claves, self._texto_privada())
            return
        if self._errores_archivo:
            poner_mensaje(self.lbl_error_claves, "\n".join(self._errores_archivo))
            return
        lineas = [
            texto_problema(p) for p in self._problemas_claves() if p.severidad == Severidad.ERROR
        ]
        poner_mensaje(self.lbl_error_claves, "\n".join(dict.fromkeys(lineas)) or None)

    @staticmethod
    def _texto_privada() -> str:
        return texto_problema(Problema("cloudinit.claves", "V-B23", Severidad.ERROR, {}))

    def _problemas_claves(self) -> list[Problema]:
        """V-B22 y V-B24 sobre el texto del campo (con su número de línea)."""
        texto = self.txt_claves.toPlainText()
        if not texto.strip():
            return []
        resultado = analizar_claves(texto)
        problemas: list[Problema] = []
        for p in resultado.problemas:
            if p.motivo == MotivoClave.CLAVE_PRIVADA:
                continue
            if p.motivo in (MotivoClave.DEMASIADAS, MotivoClave.DEMASIADO_TEXTO):
                problemas.append(
                    Problema(
                        "cloudinit.claves", "V-B24", Severidad.ERROR, {"motivo": p.motivo.value}
                    )
                )
            else:
                problemas.append(
                    Problema(
                        "cloudinit.claves",
                        "V-B22",
                        Severidad.ERROR,
                        {"linea": str(p.linea), "motivo": p.motivo.value},
                    )
                )
        return problemas

    def _elegir_archivos_pub(self) -> None:
        """Diálogo del sistema para elegir uno o varios ``.pub`` (RF-B1.4)."""
        inicio = Path.home() / ".ssh"
        rutas, _filtro = QFileDialog.getOpenFileNames(
            self,
            QCoreApplication.translate("SeccionCloudInit", "Añadir claves públicas"),
            str(inicio if inicio.is_dir() else Path.home()),
            QCoreApplication.translate(
                "SeccionCloudInit", "Claves públicas (*.pub);;Todos los archivos (*)"
            ),
        )
        if rutas:
            self.agregar_archivos_pub([Path(r) for r in rutas])

    def agregar_archivos_pub(self, rutas: Sequence[Path]) -> None:
        """Añade el contenido de cada ``.pub`` al campo de claves.

        Un archivo ilegible, binario o demasiado grande se descarta con su motivo. Si alguno
        contiene una clave privada se rechaza (no se añade nada de él y no se conserva su
        nombre ni su contenido) con el aviso de RF-B1.5; los demás archivos sí se añaden.
        """
        errores: list[str] = []
        privada = False
        nuevos: list[str] = []
        for ruta in rutas:
            try:
                contenido = leer_archivo_pub(ruta)
            except ErrorProxLaunch as e:
                errores.append(texto_error(e))
                continue
            if contiene_clave_privada(contenido):
                privada = True
                continue
            nuevos.append(contenido.strip())
        if nuevos:
            actual = self.txt_claves.toPlainText().rstrip("\n")
            anadido = "\n".join(n for n in nuevos if n)
            self.txt_claves.setPlainText((actual + "\n" + anadido) if actual else anadido)
        self._errores_archivo = list(dict.fromkeys(errores))
        self._privada = privada
        self.fila_claves.marcar_tocado()
        self._actualizar_resumen_claves()

    # --- Contraseña ----------------------------------------------------------------------

    def _mostrar_contrasenas(self, mostrar: bool) -> None:
        modo = QLineEdit.EchoMode.Normal if mostrar else QLineEdit.EchoMode.Password
        self.txt_contrasena.setEchoMode(modo)
        self.txt_repeticion.setEchoMode(modo)

    def _al_editar_contrasena(self, _texto: str) -> None:
        # El valor cambió: el ``Secreto`` anterior ya no vale y deja de estar registrado.
        self._olvidar_secreto()
        if self.txt_repeticion.text():
            self.fila_contrasena.marcar_tocado()
        self._emitir()

    def _olvidar_secreto(self) -> None:
        if self._secreto is not None:
            self._secreto.olvidar()
            self._secreto = None

    def _contrasena(self) -> Secreto | None:
        """El ``Secreto`` de lo escrito, o ``None`` (campo vacío o con errores).

        Se valida el texto en CLARO antes de crear el ``Secreto`` y nunca nace uno vacío. Se
        reutiliza la misma instancia mientras el texto no cambie (así un solo ``olvidar()`` del
        lote vale para todas las copias).
        """
        valor = self.txt_contrasena.text()
        if not valor:
            return None
        errores = [
            p
            for p in validar_contrasena(valor, self.txt_repeticion.text(), self._info)
            if p.severidad == Severidad.ERROR
        ]
        if errores:
            return None
        if self._secreto is not None and self._secreto.definido:
            if self._secreto.revelar() == valor:
                return self._secreto
            self._secreto.olvidar()
        self._secreto = Secreto(valor)
        return self._secreto

    def _restablecer_contrasena(self) -> None:
        self._olvidar_secreto()
        self._borrar_contrasenas()

    def _borrar_contrasenas(self) -> None:
        self.txt_contrasena.clear()
        self.txt_repeticion.clear()
        self.chk_mostrar.setChecked(False)

    def ceder_secreto(self) -> None:
        """El ``Secreto`` actual pasa a ser del lote que se lanza: se suelta la referencia SIN
        olvidarlo y se vacían los campos. Desde aquí, editar la contraseña crea un ``Secreto``
        nuevo y solo olvida los que la sección aún posee."""
        self._secreto = None
        self._vaciar_campos_contrasena()

    def limpiar_secretos(self) -> None:
        """Borra los campos de la contraseña (al cerrar el formulario o cambiar de servidor) y
        olvida el ``Secreto`` que la sección aún posea (uno ya cedido con ``ceder_secreto`` no)."""
        self._olvidar_secreto()
        self._vaciar_campos_contrasena()

    def _vaciar_campos_contrasena(self) -> None:
        self._ocupado, previo = True, self._ocupado
        try:
            self._borrar_contrasenas()
        finally:
            self._ocupado = previo
        self.fila_contrasena.tocado = False
        self._texto_validacion.pop(id(self.fila_contrasena), None)
        self.fila_contrasena.mostrar_error(None)
        self._refrescar_aviso(self.fila_contrasena)

    # --- Scripts (snippets) ---------------------------------------------------------------

    def establecer_snippets(
        self, listados: Sequence[ListadoSnippets], *, pendientes: bool = False
    ) -> None:
        """Scripts del servidor que ve el nodo destino (``CatalogoServidor.snippets_en``).

        ``pendientes``: algún almacenamiento aún se está leyendo. Un listado con error (403,
        tiempo agotado) pasa el selector a «Escribir a mano» con un aviso (CA-B4.2.5).
        """
        self._listados = tuple(listados)
        self._snippets_pendientes = pendientes
        previo, self._ocupado = self._ocupado, True
        try:
            self._rellenar_snippets()
        finally:
            self._ocupado = previo

    def _rellenar_snippets(self) -> None:
        todos: dict[str, Snippet] = {}
        con_error = False
        for ls in self._listados:
            if ls.error is not None:
                con_error = True
                continue
            for sn in ls.snippets:
                todos.setdefault(sn.volid, sn)
        ordenados = sorted(todos.values(), key=lambda s: (s.nombre.casefold(), s.volid))
        for sel in self.selectores_snippet.values():
            sel.establecer_opciones(ordenados)
        if con_error:
            texto = QCoreApplication.translate(
                "SeccionCloudInit",
                "No se pudo leer la lista de scripts del servidor. Elige «Escribir a mano…» y "
                "escribe el identificador (almacén:snippets/archivo); no se podrá comprobar que "
                "exista.",
            )
        elif self._snippets_pendientes:
            texto = QCoreApplication.translate(
                "SeccionCloudInit", "Leyendo la lista de scripts del servidor…"
            )
        else:
            texto = ""
        poner_mensaje(self._aviso_listado, texto or None, aviso=True)

    def copiar_ejemplo(self) -> None:
        """Copia el ejemplo del script del agente al portapapeles (RF-B4.7)."""
        QApplication.clipboard().setText(self.texto_ejemplo())

    @staticmethod
    def texto_ejemplo() -> str:
        """Texto del ejemplo: el mismo que figura en la guía de usuario."""
        return ejemplo_snippet_agente()

    # --- Valor ---------------------------------------------------------------------------

    def configuracion(self) -> ConfigCloudInit | None:
        """Lo que el usuario fijó, o ``None`` si no hay nada que enviar (RF-B0.2).

        La contraseña solo va si coincide con su repetición y pasa V-B25. Las claves son las
        válidas del campo; las líneas con error se señalan en ``problemas()``.
        """
        resultado = analizar_claves(self.txt_claves.toPlainText())
        claves = () if self._privada else resultado.claves
        dns, motivo = normalizar_dns(self.txt_dns.text())
        tarjetas = tuple(
            t for idx in sorted(self._tarjetas) if (t := self._tarjetas[idx].tarjeta()) is not None
        )
        snippets = SnippetsCloudInit(
            **{tipo: sel.valor() for tipo, sel in self.selectores_snippet.items()}
        )
        ci = ConfigCloudInit(
            usuario=self.txt_usuario.text().strip(),
            claves=claves,
            contrasena=self._contrasena(),
            tarjetas=tarjetas,
            dns=dns if motivo is None else tuple(self.txt_dns.text().replace(",", " ").split()),
            dominio=self.txt_dominio.text().strip(),
            actualizar=cast("bool | None", self.combo_actualizar.currentData()),
            snippets=snippets,
            activar_agente=self.chk_agente.isChecked() and self.fila_agente.isVisibleTo(self),
        )
        return None if ci.vacia else ci

    def aplicar(self, ci: ConfigCloudInit | None) -> None:
        """Vuelca una configuración en los campos (lote guardado, «Crear otra»).

        Nunca toca la contraseña (no se guarda en ningún archivo). Si ``ci`` coincide con lo que
        ya hay, no reescribe nada (así un perfil que reaplica lo actual no pierde líneas con error).
        """
        ci = ci if ci is not None else ConfigCloudInit()
        actual = self.configuracion() or ConfigCloudInit()
        if _sin_contrasena(ci) == _sin_contrasena(actual):
            return
        previo, self._ocupado = self._ocupado, True
        try:
            self.txt_usuario.setText(ci.usuario)
            self._privada = False
            self._errores_archivo = []
            self.txt_claves.setPlainText("\n".join(ci.claves))
            self._actualizar_resumen_claves()
            for t in ci.tarjetas:
                self._asegurar_tarjeta(t.indice)
            self._ordenar_tarjetas()
            for idx, bloque in self._tarjetas.items():
                bloque.aplicar(ci.tarjeta(idx))
            self.txt_dns.setText(", ".join(ci.dns))
            self.txt_dominio.setText(ci.dominio)
            self.combo_actualizar.setCurrentIndex(
                max(self.combo_actualizar.findData(ci.actualizar), 0)
            )
            for tipo, sel in self.selectores_snippet.items():
                sel.establecer_valor(getattr(ci.snippets, tipo))
            self.chk_agente.setChecked(ci.activar_agente)
        finally:
            self._ocupado = previo
        self._emitir()

    # --- Restablecer ----------------------------------------------------------------------

    def _hay_valor_cloudinit(self) -> bool:
        return bool(
            self.txt_usuario.text().strip()
            or self.txt_claves.toPlainText().strip()
            or any(t.hay_valor() for t in self._tarjetas.values())
            or self.combo_actualizar.currentData() is not None
        )

    def _restablecer_cloudinit(self) -> None:
        self.txt_usuario.clear()
        self.txt_claves.clear()
        self.combo_actualizar.setCurrentIndex(0)
        self._privada = False
        self._errores_archivo = []
        for t in self._tarjetas.values():
            t.restablecer()
        self._actualizar_resumen_claves()

    def _restablecer_dns(self) -> None:
        self.txt_dns.clear()
        self.txt_dominio.clear()

    def _restablecer_snippets(self) -> None:
        for sel in self.selectores_snippet.values():
            sel.establecer_valor(None)

    # --- Problemas -----------------------------------------------------------------------

    @property
    def tarjetas(self) -> Mapping[int, BloqueTarjeta]:
        """Bloques de tarjeta por índice ``netN`` (para pruebas y para el formulario)."""
        return self._tarjetas

    def problemas(self) -> list[Problema]:
        """Reglas que solo se pueden evaluar sobre el texto de los campos (V-B22, V-B24, V-B25).

        ``configuracion()`` descarta las líneas de clave con error y no crea el ``Secreto`` si la
        contraseña no vale; sin esto el formulario daría por buena una configuración a la que le
        falta algo. Los ``params`` nunca llevan claves ni contraseñas.
        """
        problemas = self._problemas_claves()
        valor, repeticion = self.txt_contrasena.text(), self.txt_repeticion.text()
        problemas.extend(validar_contrasena(valor, repeticion, self._info))
        return problemas

    def mostrar_problemas(self, problemas: Sequence[Problema]) -> None:
        """Muestra cada problema de ``cloudinit.*`` junto a su campo (errores y avisos)."""
        errores: dict[int, list[str]] = {}
        avisos: dict[int, list[str]] = {}
        globales: list[str] = []
        globales_aviso: list[str] = []
        snippets_generales: list[str] = []
        filas: list[FilaCampo] = [
            self.fila_usuario,
            self.fila_claves,
            self.fila_contrasena,
            self.fila_dns,
            self.fila_dominio,
            self.fila_actualizar,
            *(sel.fila for sel in self.selectores_snippet.values()),
        ]
        for bloque in self._tarjetas.values():
            filas.extend((bloque.fila_modo, bloque.fila_ip, bloque.fila_puerta))
        for p in problemas:
            if p.campo != "cloudinit" and not p.campo.startswith("cloudinit."):
                continue
            texto = texto_problema(p)
            es_error = p.severidad == Severidad.ERROR
            fila = self._fila_de_campo(p.campo)
            if fila is None:
                if p.campo == "cloudinit.snippets":
                    snippets_generales.append(texto)
                else:
                    (globales if es_error else globales_aviso).append(texto)
                continue
            if fila is self.fila_claves and es_error:
                continue  # los errores de línea ya salen bajo el campo de claves
            (errores if es_error else avisos).setdefault(id(fila), []).append(texto)
        for fila in filas:
            if fila is not self.fila_contrasena:  # su error sale al terminar de repetirla
                fila.marcar_tocado()
            fila.mostrar_error("\n".join(dict.fromkeys(errores.get(id(fila), []))) or None)
            self._texto_validacion[id(fila)] = "\n".join(dict.fromkeys(avisos.get(id(fila), [])))
            self._refrescar_aviso(fila)
        poner_mensaje(self._global, "\n".join(dict.fromkeys(globales)) or None)
        poner_mensaje(
            self._global_aviso, "\n".join(dict.fromkeys(globales_aviso)) or None, aviso=True
        )
        poner_mensaje(self._error_snippets, "\n".join(dict.fromkeys(snippets_generales)) or None)

    def _fila_de_campo(self, campo: str) -> FilaCampo | None:
        """Fila donde se muestra un problema («cloudinit.tarjetas[0].ip» → IP de la tarjeta 1)."""
        simples = {
            "cloudinit.usuario": self.fila_usuario,
            "cloudinit.claves": self.fila_claves,
            "cloudinit.contrasena": self.fila_contrasena,
            "cloudinit.dns": self.fila_dns,
            "cloudinit.dominio": self.fila_dominio,
            "cloudinit.actualizar": self.fila_actualizar,
        }
        if campo in simples:
            return simples[campo]
        if campo.startswith("cloudinit.snippets."):
            sel = self.selectores_snippet.get(campo.partition("cloudinit.snippets.")[2])
            return sel.fila if sel is not None else None
        if campo.startswith("cloudinit.tarjetas["):
            resto = campo[len("cloudinit.tarjetas[") :]
            numero, _, cola = resto.partition("]")
            try:
                bloque = self._tarjetas.get(int(numero))
            except ValueError:
                return None
            if bloque is None:
                return None
            if cola == ".ip":
                return bloque.fila_ip
            if cola == ".puerta":
                return bloque.fila_puerta
            return bloque.fila_modo
        return None


def _misma_causa(a: EstadoOpcion | None, b: EstadoOpcion | None) -> bool:
    """¿Dos estados de opción deshabilitada se explican igual? (ignora el nombre de la opción)."""
    if a is None or b is None or a.codigo != b.codigo:
        return False
    return {k: v for k, v in a.params.items() if k != "opcion"} == {
        k: v for k, v in b.params.items() if k != "opcion"
    }


def _sin_contrasena(ci: ConfigCloudInit) -> ConfigCloudInit:
    """La misma configuración sin contraseña (para comparar lo que se guarda en archivos)."""
    return ConfigCloudInit(
        usuario=ci.usuario,
        claves=ci.claves,
        tarjetas=ci.tarjetas,
        dns=ci.dns,
        dominio=ci.dominio,
        actualizar=ci.actualizar,
        snippets=ci.snippets,
        activar_agente=ci.activar_agente,
    )
