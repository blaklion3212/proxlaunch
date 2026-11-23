"""Sección «Firewall de la máquina» del formulario (RF-C3.1 a RF-C3.4, RF-C3.9, RF-C3.11).

Plegada y apagada por defecto: con la casilla «Activar el firewall» sin marcar no hay ninguna
petición de firewall (``firewall()`` devuelve ``None``, como en 0.7.0). Al activarla se pueden
elegir un grupo de seguridad (ya preparado por el administrador), las políticas de entrada y
salida y el DHCP. La lista de grupos y el contenido de un grupo los lee la ventana en un
trabajador: esta sección emite ``pide_grupos`` y ``pide_reglas`` y recibe el resultado en
``establecer_grupos`` y ``establecer_reglas``. Nunca se permite escribir a mano un grupo que no
está en la lista (evita reglas que no hacen nada).
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_estado_opcion, texto_opcion_restablecida
from proxlaunch.interfaz.textos_c import (
    texto_dhcp_automatico,
    texto_error_leer_reglas,
    texto_explicacion_politica,
    texto_grupos_ilegibles,
    texto_intro_firewall,
    texto_politica,
    texto_problema_c,
    texto_regla,
    texto_reglas_grupo,
    texto_riesgo_firewall,
    texto_sin_grupos,
    texto_ver_reglas_sin_permiso,
)
from proxlaunch.interfaz.vistas.campos import boton_ayuda, etiqueta, mensaje, poner_mensaje
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import (
    FirewallMV,
    LecturaGrupos,
    ModoDhcp,
    Politica,
    ReglaFirewall,
)
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, OpcionC
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.validacion import Problema, Severidad


def _fila(*widgets: QWidget) -> QHBoxLayout:
    fila = QHBoxLayout()
    for w in widgets:
        fila.addWidget(w)
    return fila


class SeccionFirewall(QGroupBox):
    """Grupo «Firewall de la máquina». Ver el módulo para la API pública."""

    cambiado = Signal()
    pide_grupos = Signal()  # al activar la casilla o pulsar «Recargar»
    pide_reglas = Signal(str)  # «Ver reglas» del grupo elegido

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            QCoreApplication.translate("SeccionFirewall", "Firewall de la máquina"), parent
        )
        self._lectura: LecturaGrupos | None = None
        self._grupo_cargado: str | None = None  # grupo de un lote guardado que aún no se listó
        self._dhcp_tocado = False
        self._hay_dhcp = False
        self._disponible = True
        self._puede_ver_reglas = True
        self._motivo_reglas = ""
        self._ocupado = False

        capa = QVBoxLayout(self)
        capa.setSpacing(4)
        cabecera = QHBoxLayout()
        cabecera.addWidget(etiqueta(texto_intro_firewall(), secundario=True), 1)
        cabecera.addWidget(boton_ayuda("firewall"))
        capa.addLayout(cabecera)
        self._motivo = mensaje(aviso=True)  # por qué está deshabilitada (RF-C0.3, CA-C0.6.2)
        capa.addWidget(self._motivo)
        self.chk_activar = QCheckBox(
            QCoreApplication.translate("SeccionFirewall", "Activar el firewall")
        )
        capa.addWidget(self.chk_activar)

        self._cuerpo = QWidget()
        cuerpo = QVBoxLayout(self._cuerpo)
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(4)

        self.combo_grupo = QComboBox()
        self.combo_grupo.setEditable(True)  # búsqueda por texto entre muchos grupos (CA-C3.2.5)
        self.combo_grupo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_grupo.setAccessibleName(
            QCoreApplication.translate("SeccionFirewall", "Grupo de seguridad")
        )
        completer = self.combo_grupo.completer()
        if completer is not None:
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.boton_recargar = QPushButton(QCoreApplication.translate("SeccionFirewall", "Recargar"))
        self.boton_reglas = QPushButton(QCoreApplication.translate("SeccionFirewall", "Ver reglas"))
        cuerpo.addLayout(
            _fila(
                etiqueta(QCoreApplication.translate("SeccionFirewall", "Grupo de seguridad")),
                self.combo_grupo,
                self.boton_recargar,
                self.boton_reglas,
                boton_ayuda("grupo_seguridad"),
            )
        )
        self._estado_grupos = mensaje(aviso=True)
        self._reglas = etiqueta("", secundario=True)
        self._reglas.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._reglas.hide()
        cuerpo.addWidget(self._estado_grupos)
        cuerpo.addWidget(self._reglas)

        self.combo_entrada = self._combo_politica(Politica.BLOQUEAR)
        self.combo_salida = self._combo_politica(Politica.PERMITIR)
        cuerpo.addLayout(
            _fila(
                etiqueta(
                    QCoreApplication.translate(
                        "SeccionFirewall", "Si ninguna regla lo permite, el tráfico que entra"
                    )
                ),
                self.combo_entrada,
                boton_ayuda("politica_entrada"),
            )
        )
        cuerpo.addWidget(etiqueta(texto_explicacion_politica(True), secundario=True))
        cuerpo.addLayout(
            _fila(
                etiqueta(QCoreApplication.translate("SeccionFirewall", "…el tráfico que sale")),
                self.combo_salida,
                boton_ayuda("politica_salida"),
            )
        )
        cuerpo.addWidget(etiqueta(texto_explicacion_politica(False), secundario=True))

        self.chk_dhcp = QCheckBox(
            QCoreApplication.translate(
                "SeccionFirewall", "Permitir que la máquina pida su IP por DHCP"
            )
        )
        self._nota_dhcp = etiqueta(texto_dhcp_automatico(), secundario=True)
        self._nota_dhcp.hide()
        cuerpo.addLayout(_fila(self.chk_dhcp, boton_ayuda("dhcp_firewall")))
        cuerpo.addWidget(self._nota_dhcp)

        self._riesgo = etiqueta(texto_riesgo_firewall(), secundario=True)
        cuerpo.addWidget(self._riesgo)
        self.chk_aislada = QCheckBox(
            QCoreApplication.translate(
                "SeccionFirewall", "Entiendo que la máquina no aceptará conexiones por la red"
            )
        )
        cuerpo.addWidget(self.chk_aislada)
        self._errores = mensaje(error=True)
        self._avisos = mensaje(aviso=True)
        cuerpo.addWidget(self._errores)
        cuerpo.addWidget(self._avisos)
        capa.addWidget(self._cuerpo)

        self.chk_activar.toggled.connect(self._al_activar)
        self.combo_grupo.currentIndexChanged.connect(self._al_cambiar_grupo)
        self.combo_grupo.editTextChanged.connect(lambda _t: self._emitir())
        self.combo_entrada.currentIndexChanged.connect(lambda _i: self._al_cambiar_politica())
        self.combo_salida.currentIndexChanged.connect(lambda _i: self._emitir())
        self.chk_dhcp.clicked.connect(self._al_tocar_dhcp)
        self.chk_aislada.toggled.connect(lambda _m: self._emitir())
        self.boton_recargar.clicked.connect(self.pide_grupos)
        self.boton_reglas.clicked.connect(self._al_pedir_reglas)
        self._llenar_grupos()
        self._refrescar()

    @staticmethod
    def _combo_politica(por_defecto: Politica) -> QComboBox:
        combo = QComboBox()
        combo.addItem(texto_politica(Politica.BLOQUEAR), Politica.BLOQUEAR)
        combo.addItem(texto_politica(Politica.PERMITIR), Politica.PERMITIR)
        combo.setCurrentIndex(combo.findData(por_defecto))
        return combo

    # --- Datos que entran --------------------------------------------------------------------

    def establecer_grupos(self, lectura: LecturaGrupos) -> None:
        """Resultado de leer los grupos (``grupos`` ``None`` = ilegible: V-C32)."""
        self._lectura = lectura
        self._llenar_grupos()
        self._refrescar()

    def establecer_reglas(
        self,
        grupo: str,
        reglas: tuple[ReglaFirewall, ...] | None,
        error: ErrorProxLaunch | None,
    ) -> None:
        """Contenido del grupo (solo lectura). Un resultado de otro grupo se descarta."""
        if grupo != self._grupo_elegido():
            return
        self.boton_reglas.setEnabled(self._puede_ver_reglas)
        if reglas is None:
            self._reglas.setText(texto_error_leer_reglas())
        else:
            lineas = [texto_regla(r.tipo, r.accion, r.activa, r.comentario) for r in reglas]
            self._reglas.setText(texto_reglas_grupo(grupo, lineas))
        self._reglas.show()

    def establecer_hay_dhcp(self, hay: bool) -> None:
        """Hay una tarjeta con DHCP por cloud-init: la casilla se marca sola, a la vista
        (RF-C3.4), mientras el usuario no la toque."""
        if hay == self._hay_dhcp:
            return
        self._hay_dhcp = hay
        self._refrescar()
        self.cambiado.emit()

    def establecer_disponibilidad(
        self, firewall: EstadoOpcion | None, general: EstadoOpcion | None
    ) -> None:
        """Sin ``VM.Config.Network`` o sin versión la sección queda deshabilitada con el motivo
        a la vista; «Ver reglas» necesita ``Sys.Audit`` en «/» (RF-C3.11)."""
        libre = firewall is None or firewall.disponibilidad != Disponibilidad.NO
        self._disponible = libre
        poner_mensaje(
            self._motivo,
            None if libre or firewall is None else texto_estado_opcion(firewall),
            aviso=True,
        )
        motivo_firewall = "" if libre or firewall is None else texto_estado_opcion(firewall)
        if not libre and self.chk_activar.isChecked():
            # CL-A15: lo que ya no se puede usar vuelve a su valor por defecto, con aviso.
            poner_mensaje(
                self._motivo,
                texto_opcion_restablecida(OpcionC.FIREWALL.value, motivo_firewall),
                aviso=True,
            )
        self._puede_ver_reglas = (
            general is None or general.codigo is None or general.disponibilidad == Disponibilidad.SI
        )
        self._motivo_reglas = "" if self._puede_ver_reglas else texto_ver_reglas_sin_permiso()
        if not libre and self.chk_activar.isChecked():
            self.chk_activar.setChecked(False)
        self._refrescar()

    def aplicar(self, fw: FirewallMV | None) -> None:
        """Carga el firewall de un lote guardado o del formulario («Crear otra»)."""
        self._ocupado = True
        try:
            activo = fw is not None and fw.activo
            self.chk_activar.setChecked(activo)
            if fw is None:
                self._grupo_cargado = None
                self.combo_entrada.setCurrentIndex(self.combo_entrada.findData(Politica.BLOQUEAR))
                self.combo_salida.setCurrentIndex(self.combo_salida.findData(Politica.PERMITIR))
                self._dhcp_tocado = False
                self.chk_aislada.setChecked(False)
            else:
                self._grupo_cargado = fw.grupo
                self.combo_entrada.setCurrentIndex(self.combo_entrada.findData(fw.politica_entrada))
                self.combo_salida.setCurrentIndex(self.combo_salida.findData(fw.politica_salida))
                self._dhcp_tocado = fw.dhcp != ModoDhcp.AUTO
                if self._dhcp_tocado:
                    self.chk_dhcp.setChecked(fw.dhcp == ModoDhcp.SI)
                self.chk_aislada.setChecked(fw.acepto_aislada)
            self._llenar_grupos()
        finally:
            self._ocupado = False
        self._refrescar()
        if activo and self._lectura is None:
            self.pide_grupos.emit()
        self.cambiado.emit()

    # --- Datos que salen ---------------------------------------------------------------------

    def firewall(self) -> FirewallMV | None:
        """El firewall pedido; ``None`` con la casilla apagada (comportamiento de 0.7.0)."""
        if not self.chk_activar.isChecked():
            return None
        if self._dhcp_tocado:
            dhcp = ModoDhcp.SI if self.chk_dhcp.isChecked() else ModoDhcp.NO
        else:
            dhcp = ModoDhcp.AUTO
        return FirewallMV(
            activo=True,
            grupo=self._grupo_elegido(),
            politica_entrada=Politica(self.combo_entrada.currentData()),
            politica_salida=Politica(self.combo_salida.currentData()),
            dhcp=dhcp,
            acepto_aislada=self.chk_aislada.isChecked() and self.chk_aislada.isVisibleTo(self),
        )

    def mostrar_problemas(self, problemas: Sequence[Problema]) -> None:
        """Errores y avisos de firewall (V-C30 a V-C40, V-C50, V-C52) junto a la sección."""
        errores: list[str] = []
        avisos: list[str] = []
        for p in problemas:
            if not p.campo.startswith("firewall"):
                continue
            texto = texto_problema_c(p)
            if texto is None:
                continue
            (errores if p.severidad == Severidad.ERROR else avisos).append(texto)
        poner_mensaje(self._errores, "\n".join(dict.fromkeys(errores)) or None)
        poner_mensaje(self._avisos, "\n".join(dict.fromkeys(avisos)) or None, aviso=True)

    # --- Internos ----------------------------------------------------------------------------

    def _grupo_elegido(self) -> str | None:
        """El grupo de la lista elegido; un texto escrito que no es de la lista no cuenta."""
        i = self.combo_grupo.currentIndex()
        if i < 0 or self.combo_grupo.currentText() != self.combo_grupo.itemText(i):
            return None
        valor = self.combo_grupo.itemData(i)
        return str(valor) if valor else None

    def _llenar_grupos(self) -> None:
        previo = self._grupo_elegido() or self._grupo_cargado
        self.combo_grupo.blockSignals(True)
        self.combo_grupo.clear()
        self.combo_grupo.addItem(QCoreApplication.translate("SeccionFirewall", "Sin grupo"), None)
        nombres: set[str] = set()
        grupos = self._lectura.grupos if self._lectura is not None else None
        for g in grupos or ():
            texto = f"{g.nombre} — {g.comentario}" if g.comentario else g.nombre
            self.combo_grupo.addItem(texto, g.nombre)
            nombres.add(g.nombre)
        if previo and previo not in nombres and (grupos is not None or previo):
            # Un grupo cargado que el servidor no lista (o aún sin lista): se muestra y la
            # validación lo marca (V-C30) en vez de cambiarlo en silencio.
            ausente = QCoreApplication.translate("SeccionFirewall", "{grupo} (no existe)").format(
                grupo=previo
            )
            self.combo_grupo.addItem(ausente if grupos is not None else previo, previo)
        pos = self.combo_grupo.findData(previo) if previo else 0
        self.combo_grupo.setCurrentIndex(max(pos, 0))
        self.combo_grupo.blockSignals(False)

    def _refrescar(self) -> None:
        activo = self.chk_activar.isChecked() and self._disponible
        self._cuerpo.setVisible(activo)
        self.chk_activar.setEnabled(self._disponible)
        grupos = self._lectura.grupos if self._lectura is not None else None
        ilegible = self._lectura is not None and grupos is None
        self.combo_grupo.setEnabled(not ilegible)
        poner_mensaje(
            self._estado_grupos,
            texto_grupos_ilegibles()
            if ilegible
            else (texto_sin_grupos() if grupos is not None and not grupos else None),
            aviso=True,
        )
        hay_grupo = self._grupo_elegido() is not None
        self.boton_reglas.setEnabled(hay_grupo and self._puede_ver_reglas)
        self.boton_reglas.setToolTip(self._motivo_reglas)
        if not self._puede_ver_reglas and hay_grupo:
            poner_mensaje(self._estado_grupos, self._motivo_reglas, aviso=True)
        if not hay_grupo:
            self._reglas.hide()
        # DHCP: marcada sola si hay DHCP por cloud-init y el usuario no la tocó.
        if not self._dhcp_tocado:
            previo = self.chk_dhcp.blockSignals(True)
            self.chk_dhcp.setChecked(self._hay_dhcp)
            self.chk_dhcp.blockSignals(previo)
        self._nota_dhcp.setVisible(self._hay_dhcp and self.chk_dhcp.isChecked())
        entrada_bloquea = self.combo_entrada.currentData() == Politica.BLOQUEAR
        self._riesgo.setVisible(entrada_bloquea)
        self.chk_aislada.setVisible(entrada_bloquea and not hay_grupo)

    def _al_activar(self, marcada: bool) -> None:
        self._refrescar()
        if marcada and not self._ocupado:
            self.pide_grupos.emit()
        self._emitir()

    def _al_cambiar_grupo(self, _i: int) -> None:
        self._grupo_cargado = None
        self._reglas.hide()
        self._refrescar()
        self._emitir()

    def _al_cambiar_politica(self) -> None:
        self._refrescar()
        self._emitir()

    def _al_tocar_dhcp(self, _marcada: bool) -> None:
        self._dhcp_tocado = True
        self._refrescar()
        self._emitir()

    def _al_pedir_reglas(self) -> None:
        grupo = self._grupo_elegido()
        if grupo is None:
            return
        self.boton_reglas.setEnabled(False)
        self.pide_reglas.emit(grupo)

    def _emitir(self) -> None:
        if not self._ocupado:
            self.cambiado.emit()
