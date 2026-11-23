"""Sección «Red de las copias» del formulario al clonar una plantilla (RF-C4.1 a RF-C4.4, RF-C4.7).

Por defecto la red queda «Como la plantilla» (no se toca nada, igual que en 0.7.0). Con
«Personalizar» se muestran las tarjetas de la plantilla (leídas de su configuración) para cambiar
su red (bridge o VNet), tarjeta, VLAN, MTU y límite, quitarlas o añadir otras; la MAC se conserva
salvo que se marque «Generar una MAC nueva». Una tarjeta que no se entiende se muestra en solo
lectura y nunca se reescribe.

La sección no toca el servidor: ``red_clon()`` devuelve lo que pide el usuario y la creación hace
el resto. Emite ``cambiado`` ante cualquier edición.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_estado_opcion, texto_opcion_restablecida
from proxlaunch.interfaz.textos_c import (
    texto_intro_red_clon,
    texto_modo_red_personalizar,
    texto_modo_red_plantilla,
    texto_plantilla_sin_tarjetas,
    texto_problema_c,
    texto_red_clon_sin_leer,
    texto_tarjeta_ilegible,
    texto_vlan_no_vlanaware,
)
from proxlaunch.interfaz.vistas.campos import boton_ayuda, etiqueta, mensaje, poner_mensaje
from proxlaunch.interfaz.vistas.tabla_redes import (
    limite_desde_texto,
    llenar_combo_red,
    texto_limite,
    vlan_desde_texto,
)
from proxlaunch.nucleo.modelos.inventario import Bridge, RedVirtual
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, OpcionC
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.red.modelos import (
    MAX_TARJETAS,
    AccionTarjeta,
    CampoRed,
    ModoRedClon,
    RedClon,
    TarjetaClon,
    TarjetaPlantilla,
)
from proxlaunch.nucleo.red.tarjetas import indice_libre
from proxlaunch.nucleo.validacion import Problema, Severidad

_MODELOS = (("VirtIO", "virtio"), ("Intel E1000", "e1000"))
_COLUMNAS = 8


def _entero_o_cero(texto: str) -> int | None:
    """MTU escrito: vacío = ``None`` (heredar); un texto que no es entero se lee como 0, un valor
    que las reglas de red rechazan (así el error sale junto al campo)."""
    t = texto.strip()
    if not t:
        return None
    try:
        return int(t)
    except ValueError:
        return 0


class _FilaTarjeta:
    """Una tarjeta: la de la plantilla (``base``) o una añadida (``base`` ``None``)."""

    def __init__(self, indice: int, base: TarjetaPlantilla | None) -> None:
        self.indice = indice
        self.base = base
        self.quitada = False
        self.nombre = etiqueta(f"net{indice}")
        self.nombre.setProperty("mono", True)
        self.red = QComboBox()
        self.red.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        # Cabe un alias de VNet razonable («prod — Producción»); los más largos se ven en la lista.
        self.red.setMinimumContentsLength(20)
        self.modelo = QComboBox()
        for texto, valor in _MODELOS:
            self.modelo.addItem(texto, valor)
        self.vlan = QLineEdit()
        # Anchos mínimos para que se lea entero el texto de ayuda («Sin VLAN», «Heredar»…).
        self.vlan.setMinimumWidth(90)
        self.vlan.setMaximumWidth(110)
        self.vlan.setPlaceholderText(QCoreApplication.translate("SeccionRedClon", "Sin VLAN"))
        self.mtu = QLineEdit()
        self.mtu.setMinimumWidth(90)
        self.mtu.setMaximumWidth(110)
        self.mtu.setPlaceholderText(QCoreApplication.translate("SeccionRedClon", "Heredar"))
        self.limite = QLineEdit()
        self.limite.setMinimumWidth(100)
        self.limite.setMaximumWidth(120)
        self.limite.setPlaceholderText(QCoreApplication.translate("SeccionRedClon", "Sin límite"))
        self.mac = QCheckBox(QCoreApplication.translate("SeccionRedClon", "Generar una MAC nueva"))
        self.boton = QPushButton(QCoreApplication.translate("SeccionRedClon", "Quitar"))
        self.nota = etiqueta("", secundario=True)
        self.nota.hide()

    def widgets(self) -> list[QWidget]:
        return [
            self.nombre,
            self.red,
            self.modelo,
            self.vlan,
            self.mtu,
            self.limite,
            self.mac,
            self.boton,
        ]

    @property
    def legible(self) -> bool:
        return self.base is None or self.base.legible


class SeccionRedClon(QGroupBox):
    """Grupo «Red de las copias»: modo y tarjetas del clon. Ver el módulo para el detalle."""

    cambiado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QCoreApplication.translate("SeccionRedClon", "Red de las copias"), parent)
        self._bridges: list[Bridge] = []
        self._vnets: list[RedVirtual] = []
        self._tarjetas: tuple[TarjetaPlantilla, ...] | None = None
        self._filas: list[_FilaTarjeta] = []
        self._pendiente: RedClon | None = None  # carga de un lote guardado a la espera de tarjetas
        self._avanzado = False
        self._disponible = True
        self._ocupado = False

        capa = QVBoxLayout(self)
        capa.setSpacing(4)
        cabecera = QHBoxLayout()
        cabecera.addWidget(etiqueta(texto_intro_red_clon(), secundario=True), 1)
        cabecera.addWidget(boton_ayuda("red_clon"))
        capa.addLayout(cabecera)
        self._motivo = mensaje(aviso=True)  # por qué está deshabilitada (RF-C0.3, CA-C0.6.2)
        capa.addWidget(self._motivo)
        modos = QHBoxLayout()
        self.radio_plantilla = QRadioButton(texto_modo_red_plantilla())
        self.radio_personalizar = QRadioButton(texto_modo_red_personalizar())
        self.radio_plantilla.setChecked(True)
        modos.addWidget(self.radio_plantilla)
        modos.addWidget(self.radio_personalizar)
        modos.addStretch(1)
        capa.addLayout(modos)

        self._cuerpo = QWidget()
        cuerpo = QVBoxLayout(self._cuerpo)
        cuerpo.setContentsMargins(0, 0, 0, 0)
        self._estado = mensaje(aviso=True)
        cuerpo.addWidget(self._estado)
        self._rejilla = QGridLayout()
        self._rejilla.setHorizontalSpacing(8)
        self._rejilla.setVerticalSpacing(4)
        self._cabeceras: list[QWidget] = []
        for col, texto in enumerate(
            (
                QCoreApplication.translate("SeccionRedClon", "Interfaz"),
                QCoreApplication.translate("SeccionRedClon", "Red"),
                QCoreApplication.translate("SeccionRedClon", "Tarjeta"),
                QCoreApplication.translate("SeccionRedClon", "VLAN"),
                QCoreApplication.translate("SeccionRedClon", "MTU"),
                QCoreApplication.translate("SeccionRedClon", "Límite (MB/s)"),
            )
        ):
            lbl = etiqueta(texto, secundario=True)
            self._cabeceras.append(lbl)
            self._rejilla.addWidget(lbl, 0, col)
        self._rejilla.setColumnStretch(1, 1)
        cuerpo.addLayout(self._rejilla)
        self._agregar = QPushButton(QCoreApplication.translate("SeccionRedClon", "Añadir tarjeta"))
        cuerpo.addWidget(self._agregar)
        self._errores = mensaje(error=True)
        self._avisos = mensaje(aviso=True)
        cuerpo.addWidget(self._errores)
        cuerpo.addWidget(self._avisos)
        capa.addWidget(self._cuerpo)

        self.radio_personalizar.toggled.connect(self._al_cambiar_modo)
        self._agregar.clicked.connect(self._al_agregar)
        self._aplicar_visibilidad()

    # --- Datos que entran --------------------------------------------------------------------

    def establecer_modo_avanzado(self, avanzado: bool) -> None:
        """MTU y límite son avanzados: se ven solo en modo avanzado (o si traen valor)."""
        self._avanzado = avanzado
        self._aplicar_visibilidad()

    def establecer_redes(self, bridges: Sequence[Bridge], vnets: Sequence[RedVirtual]) -> None:
        """Bridges y VNets del nodo (o de la intersección) para los desplegables."""
        self._bridges, self._vnets = list(bridges), list(vnets)
        for f in self._filas:
            self._llenar_red(f, f.red.currentData())
            self._estado_fila(f)

    def establecer_tarjetas(self, tarjetas: tuple[TarjetaPlantilla, ...] | None) -> None:
        """Tarjetas de la plantilla elegida (``None`` = aún sin leer). Si cambian, la elección del
        usuario se descarta (era sobre otra plantilla); una carga pendiente se aplica ahora."""
        if tarjetas == self._tarjetas:
            return
        self._tarjetas = tarjetas
        self._reconstruir()
        if self._pendiente is not None and tarjetas is not None:
            pendiente, self._pendiente = self._pendiente, None
            self._aplicar_cargado(pendiente)
        self._aplicar_visibilidad()
        self.cambiado.emit()

    def establecer_disponibilidad(self, estado: EstadoOpcion | None) -> None:
        """Sin ``VM.Config.Network`` o sin versión, «Personalizar» queda deshabilitado con el
        motivo a la vista; una elección previa vuelve a «Como la plantilla» (RF-C0.3)."""
        libre = estado is None or estado.disponibilidad != Disponibilidad.NO
        self._disponible = libre
        self.radio_personalizar.setEnabled(libre)
        motivo = "" if libre or estado is None else texto_estado_opcion(estado)
        if not libre and self.radio_personalizar.isChecked():
            self.radio_plantilla.setChecked(True)
            motivo = texto_opcion_restablecida(OpcionC.RED_CLON.value, motivo)
        poner_mensaje(self._motivo, motivo or None, aviso=True)

    def aplicar(self, red: RedClon | None) -> None:
        """Carga la red de un lote guardado o del formulario («Crear otra»)."""
        self._ocupado = True
        try:
            if red is None or not red.personaliza:
                self._pendiente = None
                self.radio_plantilla.setChecked(True)
                self._reconstruir()
            elif self._tarjetas is None:
                self._pendiente = red
                self.radio_personalizar.setChecked(True)
            else:
                self.radio_personalizar.setChecked(True)
                self._aplicar_cargado(red)
        finally:
            self._ocupado = False
        self._aplicar_visibilidad()
        self.cambiado.emit()

    # --- Datos que salen ---------------------------------------------------------------------

    @property
    def personaliza(self) -> bool:
        return self.radio_personalizar.isChecked()

    def indices_actuales(self) -> tuple[int, ...]:
        """Índices ``N`` de las tarjetas de la plantilla (para ofrecer solo las finales a B1)."""
        return tuple(t.indice for t in self._tarjetas or ())

    def red_clon(self) -> RedClon | None:
        """Lo que pide el usuario; ``None`` con «Como la plantilla» (comportamiento de 0.7.0)."""
        if not self.personaliza:
            return None
        pedidas: list[TarjetaClon] = []
        for f in self._filas:
            if not f.legible:
                continue
            if f.base is None:
                pedidas.append(self._tarjeta_nueva(f))
            elif f.quitada:
                pedidas.append(TarjetaClon(f.indice, AccionTarjeta.QUITAR))
            else:
                cambio = self._tarjeta_cambiada(f, f.base)
                if cambio is not None:
                    pedidas.append(cambio)
        return RedClon(ModoRedClon.PERSONALIZAR, tuple(pedidas))

    def mostrar_problemas(self, problemas: Sequence[Problema]) -> None:
        """Errores y avisos de la red del clon (V-C10 a V-C20, V-C51) junto a la sección."""
        errores: list[str] = []
        avisos: list[str] = []
        for p in problemas:
            if not (p.campo.startswith("red_clon") or p.codigo in ("V-C16", "V-C17", "V-C18")):
                continue
            texto = texto_problema_c(p)
            if texto is None:
                continue
            (errores if p.severidad == Severidad.ERROR else avisos).append(texto)
        poner_mensaje(self._errores, "\n".join(dict.fromkeys(errores)) or None)
        poner_mensaje(self._avisos, "\n".join(dict.fromkeys(avisos)) or None, aviso=True)

    # --- Internos ----------------------------------------------------------------------------

    def _aplicar_visibilidad(self) -> None:
        self._cuerpo.setVisible(self.personaliza)
        sin_leer = self._tarjetas is None
        vacia = self._tarjetas is not None and not self._tarjetas
        poner_mensaje(
            self._estado,
            texto_red_clon_sin_leer()
            if sin_leer
            else (texto_plantilla_sin_tarjetas() if vacia and not self._filas else None),
            aviso=True,
        )
        self._cabeceras[4].setVisible(self._avanzado)
        self._cabeceras[5].setVisible(self._avanzado)
        for f in self._filas:
            f.mtu.setVisible(self._avanzado)
            f.limite.setVisible(self._avanzado)
        self._agregar.setEnabled(self._tarjetas is not None and self._disponible)

    def _al_cambiar_modo(self, _marcado: bool) -> None:
        self._aplicar_visibilidad()
        if not self._ocupado:
            self.cambiado.emit()

    def _reconstruir(self) -> None:
        for f in list(self._filas):
            self._quitar_widgets(f)
        self._filas.clear()
        for t in self._tarjetas or ():
            self._nueva_fila(t.indice, t)
        self._reordenar()

    def _nueva_fila(self, indice: int, base: TarjetaPlantilla | None) -> _FilaTarjeta:
        f = _FilaTarjeta(indice, base)
        self._llenar_red(f, base.bridge if base is not None else None)
        if base is not None and base.legible:
            if base.modelo is not None:
                pos = f.modelo.findData(base.modelo)
                if pos < 0:  # modelo poco común: se muestra y se conserva
                    f.modelo.addItem(base.modelo, base.modelo)
                    pos = f.modelo.count() - 1
                f.modelo.setCurrentIndex(pos)
            f.vlan.setText("" if base.vlan is None else str(base.vlan))
            f.mtu.setText("" if base.mtu is None else str(base.mtu))
            f.limite.setText(texto_limite(base.limite_mb))
        f.red.currentIndexChanged.connect(lambda _i, fila=f: self._al_cambiar_red(fila))
        f.modelo.currentIndexChanged.connect(lambda _i, fila=f: self._al_cambiar_modelo(fila))
        for edit in (f.vlan, f.mtu, f.limite):
            edit.textEdited.connect(lambda _t: self._emitir())
        f.mac.toggled.connect(lambda _m: self._emitir())
        f.boton.clicked.connect(lambda _c=False, fila=f: self._al_pulsar_boton(fila))
        if base is None:
            f.mac.hide()  # una tarjeta nueva no tiene MAC que conservar: Proxmox genera la suya
        if base is not None and not base.legible:
            f.nota.setText(texto_tarjeta_ilegible(indice))
            f.nota.show()
            for w in (f.red, f.modelo, f.vlan, f.mtu, f.limite, f.mac, f.boton):
                w.setEnabled(False)
        self._filas.append(f)
        self._estado_fila(f)
        return f

    def _al_cambiar_modelo(self, f: _FilaTarjeta) -> None:
        """La MTU solo vale con VirtIO (RF-C4.6): se recalcula el estado de la fila."""
        self._estado_fila(f)
        self._emitir()

    def _llenar_red(self, f: _FilaTarjeta, elegido: object) -> None:
        f.red.blockSignals(True)
        f.red.clear()
        nombre = str(elegido) if elegido else None
        llenar_combo_red(f.red, self._bridges, self._vnets, ausente=nombre)
        pos = f.red.findData(nombre) if nombre else -1
        f.red.setCurrentIndex(pos)
        f.red.blockSignals(False)

    def _vnet_bloquea_vlan(self, f: _FilaTarjeta) -> bool:
        nombre = f.red.currentData()
        if not nombre or any(b.nombre == nombre for b in self._bridges):
            return False
        vnet = next((v for v in self._vnets if v.nombre == nombre), None)
        return vnet is not None and not vnet.vlan_aware

    def _estado_fila(self, f: _FilaTarjeta) -> None:
        if not f.legible:
            return
        activa = not f.quitada
        bloqueada = self._vnet_bloquea_vlan(f)
        for w in (f.red, f.modelo, f.mtu, f.limite, f.mac):
            w.setEnabled(activa)
        f.vlan.setEnabled(activa and not bloqueada)
        motivo = texto_vlan_no_vlanaware() if bloqueada else ""
        f.vlan.setToolTip(motivo)
        f.vlan.setAccessibleDescription(motivo)
        f.mtu.setEnabled(activa and f.modelo.currentData() == "virtio")
        f.boton.setText(
            QCoreApplication.translate("SeccionRedClon", "Conservar")
            if f.quitada
            else QCoreApplication.translate("SeccionRedClon", "Quitar")
        )
        f.nota.setText(
            texto_vlan_no_vlanaware()
            if bloqueada and activa
            else (
                QCoreApplication.translate("SeccionRedClon", "Esta tarjeta se quitará de la copia.")
                if f.quitada
                else ""
            )
        )
        f.nota.setVisible(bool(f.nota.text()))

    def _al_cambiar_red(self, f: _FilaTarjeta) -> None:
        if self._vnet_bloquea_vlan(f):
            f.vlan.clear()  # una VNet sin «vlanaware» no admite VLAN
        self._estado_fila(f)
        self._emitir()

    def _al_pulsar_boton(self, f: _FilaTarjeta) -> None:
        if f.base is None:  # tarjeta añadida: se descarta
            self._quitar_widgets(f)
            self._filas.remove(f)
            self._reordenar()
        else:
            f.quitada = not f.quitada
            self._estado_fila(f)
        self._aplicar_visibilidad()
        self._emitir()

    def _al_agregar(self) -> None:
        ocupados = {f.indice for f in self._filas}
        libre = indice_libre(ocupados)
        if libre is None:
            poner_mensaje(
                self._errores,
                texto_problema_c(Problema("red_clon", "V-C17", Severidad.ERROR, {})),
            )
            return
        f = self._nueva_fila(libre, None)
        if self._bridges or self._vnets:
            nombre = self._bridges[0].nombre if self._bridges else self._vnets[0].nombre
            f.red.setCurrentIndex(f.red.findData(nombre))
        self._estado_fila(f)
        self._reordenar()
        self._aplicar_visibilidad()
        self._emitir()

    def _reordenar(self) -> None:
        """Vuelve a colocar las filas en la rejilla, ordenadas por índice de tarjeta."""
        self._filas.sort(key=lambda f: f.indice)
        for fila, f in enumerate(self._filas, start=1):
            for col, w in enumerate(f.widgets()):
                self._rejilla.addWidget(w, fila * 2 - 1, col)
            self._rejilla.addWidget(f.nota, fila * 2, 0, 1, _COLUMNAS)

    def _quitar_widgets(self, f: _FilaTarjeta) -> None:
        for w in (*f.widgets(), f.nota):
            self._rejilla.removeWidget(w)
            w.deleteLater()

    def _emitir(self) -> None:
        if not self._ocupado:
            self.cambiado.emit()

    # --- Conversión entre widgets y ``RedClon`` ------------------------------------------------

    def _tarjeta_cambiada(self, f: _FilaTarjeta, base: TarjetaPlantilla) -> TarjetaClon | None:
        """``CAMBIAR`` con solo los campos que difieren de la plantilla; ``None`` si no hay."""
        fijados: set[CampoRed] = set()
        bridge = str(f.red.currentData() or "") or None
        modelo = str(f.modelo.currentData() or "") or None
        vlan = vlan_desde_texto(f.vlan.text())
        mtu = _entero_o_cero(f.mtu.text())
        limite = limite_desde_texto(f.limite.text())
        if bridge != base.bridge:
            fijados.add(CampoRed.BRIDGE)
        if modelo != base.modelo:
            fijados.add(CampoRed.MODELO)
        if vlan != base.vlan:
            fijados.add(CampoRed.VLAN)
        if mtu != base.mtu:
            fijados.add(CampoRed.MTU)
        if limite != base.limite_mb:
            fijados.add(CampoRed.LIMITE)
        mac = f.mac.isChecked()
        if not fijados and not mac:
            return None
        return TarjetaClon(
            indice=f.indice,
            accion=AccionTarjeta.CAMBIAR,
            bridge=bridge,
            modelo=modelo,
            vlan=vlan,
            mtu=mtu,
            limite_mb=limite,
            fijados=frozenset(fijados),
            mac_nueva=mac,
        )

    def _tarjeta_nueva(self, f: _FilaTarjeta) -> TarjetaClon:
        return TarjetaClon(
            indice=f.indice,
            accion=AccionTarjeta.ANADIR,
            bridge=str(f.red.currentData() or "") or None,
            modelo=str(f.modelo.currentData() or "") or None,
            vlan=vlan_desde_texto(f.vlan.text()),
            mtu=_entero_o_cero(f.mtu.text()),
            limite_mb=limite_desde_texto(f.limite.text()),
        )

    def _aplicar_cargado(self, red: RedClon) -> None:
        """Vuelca una ``RedClon`` guardada sobre las filas ya construidas."""
        previo, self._ocupado = self._ocupado, True
        try:
            self._reconstruir()
            for t in red.tarjetas:
                if t.accion == AccionTarjeta.ANADIR:
                    if t.indice >= MAX_TARJETAS or any(f.indice == t.indice for f in self._filas):
                        continue
                    nueva = self._nueva_fila(t.indice, None)
                    self._poner_valores(nueva, t, todos=True)
                    continue
                f = next((x for x in self._filas if x.indice == t.indice), None)
                if f is None or not f.legible:
                    continue
                if t.accion == AccionTarjeta.QUITAR:
                    f.quitada = True
                elif t.accion == AccionTarjeta.CAMBIAR:
                    self._poner_valores(f, t, todos=False)
                    f.mac.setChecked(t.mac_nueva)
                self._estado_fila(f)
            self._reordenar()
        finally:
            self._ocupado = previo

    def _poner_valores(self, f: _FilaTarjeta, t: TarjetaClon, *, todos: bool) -> None:
        if todos or CampoRed.BRIDGE in t.fijados:
            self._llenar_red(f, t.bridge)
        if (todos or CampoRed.MODELO in t.fijados) and t.modelo:
            pos = f.modelo.findData(t.modelo)
            if pos >= 0:
                f.modelo.setCurrentIndex(pos)
        if todos or CampoRed.VLAN in t.fijados:
            f.vlan.setText("" if t.vlan is None else str(t.vlan))
        if todos or CampoRed.MTU in t.fijados:
            f.mtu.setText("" if t.mtu is None else str(t.mtu))
        if todos or CampoRed.LIMITE in t.fijados:
            f.limite.setText(texto_limite(t.limite_mb))
        self._estado_fila(f)
