"""Tabla de interfaces de red de la MV (RF-17)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import cast

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel
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
from proxlaunch.interfaz.textos import (
    texto_estado_opcion,
    texto_mtu_solo_virtio,
    texto_opcion_restablecida,
    texto_problema,
)
from proxlaunch.interfaz.textos_c import (
    texto_grupo_bridges,
    texto_grupo_vnets,
    texto_nodos_sin_leer,
    texto_redes_ocultas,
    texto_sdn_sin_leer,
    texto_sin_vnets,
    texto_vlan_no_vlanaware,
    texto_vnet_con_alias,
)
from proxlaunch.interfaz.textos_d import texto_nombre_opcion_d
from proxlaunch.interfaz.vistas.campos import etiqueta, mensaje, poner_mensaje, poner_propiedad
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.constructor_peticion import formato_limite
from proxlaunch.nucleo.modelos.inventario import Bridge, RedVirtual
from proxlaunch.nucleo.modelos.vm import MTU_IGUAL_BRIDGE, InterfazRed, ModeloRed
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, OpcionA
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.validacion import Problema, Severidad
from proxlaunch.nucleo.valores_defecto import bridge_por_defecto

_C_INDICE, _C_BRIDGE, _C_MODELO, _C_VLAN, _C_MTU, _C_LIMITE, _C_MAC, _C_QUITAR = range(8)


def _cabecera_grupo(combo: QComboBox, titulo: str) -> None:
    """Título de grupo del desplegable: negrita y no elegible."""
    combo.addItem(titulo, None)
    item = cast(QStandardItemModel, combo.model()).item(combo.count() - 1)
    item.setEnabled(False)
    fuente = QFont(combo.font())
    fuente.setBold(True)
    item.setFont(fuente)


def llenar_combo_red(
    combo: QComboBox,
    bridges: Sequence[Bridge],
    vnets: Sequence[RedVirtual],
    *,
    ausente: str | None = None,
) -> None:
    """Rellena un desplegable de red. Sin VNets es la lista plana de 0.7.0; con ellas, dos grupos
    («Bridges del servidor» y «Redes virtuales (SDN)») y el alias de cada VNet (RF-C2.1)."""
    nombres = {b.nombre for b in bridges} | {v.nombre for v in vnets}
    if vnets:
        _cabecera_grupo(combo, texto_grupo_bridges())
    for b in bridges:
        combo.addItem(b.nombre, b.nombre)
    if vnets:
        _cabecera_grupo(combo, texto_grupo_vnets())
        for v in vnets:
            combo.addItem(texto_vnet_con_alias(v.nombre, v.alias), v.nombre)
    if ausente and ausente not in nombres:
        combo.addItem(texto_ausente(ausente), ausente)
        item: QStandardItem = cast(QStandardItemModel, combo.model()).item(combo.count() - 1)
        item.setEnabled(False)


def vlan_desde_texto(texto: str) -> int | None:
    """Vacío = sin etiqueta; un texto no numérico se convierte en 0 (la regla V-15 lo rechaza)."""
    t = texto.strip()
    if not t:
        return None
    try:
        return int(t)
    except ValueError:
        return 0


def limite_desde_texto(texto: str) -> float | None:
    """Límite en MB/s: vacío = sin límite; un texto que no es un número se convierte en 0.0 (la
    regla V-A06 lo rechaza, como el VLAN no numérico con V-15)."""
    t = texto.strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return 0.0


def texto_limite(limite: float | None) -> str:
    """Límite como texto del campo, sin ceros sobrantes ni notación científica (100.0 → «100»)."""
    if limite is None:
        return ""
    if not math.isfinite(limite):
        return f"{limite:g}"  # no es un límite válido: V-A06 lo marcará
    return formato_limite(limite)


def texto_ausente(valor: str) -> str:
    """«x (no existe)»: la red cargada de un archivo que este nodo no tiene (CA-G04.3)."""
    return QCoreApplication.translate("TablaRedes", "{id} (no existe)").format(id=valor)


class _FilaRed:
    def __init__(self) -> None:
        self.indice = QLabel()
        self.indice.setProperty("mono", True)
        self.bridge = QComboBox()
        self.bridge.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.bridge.setMinimumContentsLength(10)
        self.modelo = QComboBox()
        self.modelo.addItem("VirtIO", ModeloRed.VIRTIO)
        self.modelo.addItem("Intel E1000", ModeloRed.E1000)
        self.perdido: str | None = None  # selección pedida que no existe en el nodo
        # Bridge cargado de un lote o perfil que el nodo no tiene: se muestra «x (no existe)»
        # con error hasta que el usuario elija otro (nunca se sustituye en silencio).
        self.ausente: str | None = None
        self.vlan = QLineEdit()
        self.vlan.setMaximumWidth(80)
        self.vlan.setPlaceholderText(QCoreApplication.translate("TablaRedes", "Sin VLAN"))
        # Fase A (A5): MTU (Heredar / Igual al bridge / valor) y límite de velocidad en MB/s.
        self.mtu = QComboBox()
        self.mtu.setEditable(True)
        self.mtu.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.mtu.addItem(QCoreApplication.translate("TablaRedes", "Heredar del bridge"), None)
        self.mtu.addItem(QCoreApplication.translate("TablaRedes", "Igual al bridge"), 1)
        self.mtu.setMinimumContentsLength(14)
        self.mtu.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.limite = QLineEdit()
        self.limite.setMaximumWidth(90)
        self.limite.setPlaceholderText(QCoreApplication.translate("TablaRedes", "Sin límite"))
        # Fase D (D1): MAC de la tarjeta original de libvirt; solo existe si el formulario se
        # rellenó con el asistente y el usuario pidió conservarla (DT-D15).
        self.mac_origen: str | None = None
        self.chk_mac = QCheckBox(texto_nombre_opcion_d("conservar_mac"))
        self.chk_mac.setToolTip(ayuda("mac_origen"))
        self.chk_mac.hide()
        self.quitar = QPushButton(QCoreApplication.translate("TablaRedes", "Quitar"))

    def widgets(self) -> list[tuple[int, QWidget]]:
        return [
            (_C_INDICE, self.indice),
            (_C_BRIDGE, self.bridge),
            (_C_MODELO, self.modelo),
            (_C_VLAN, self.vlan),
            (_C_MTU, self.mtu),
            (_C_LIMITE, self.limite),
            (_C_MAC, self.chk_mac),
            (_C_QUITAR, self.quitar),
        ]


class TablaRedes(QWidget):
    """Lista editable de interfaces de red. Emite ``cambiado`` ante cualquier modificación."""

    cambiado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filas: list[_FilaRed] = []
        self._bridges: list[Bridge] = []
        self._vnets: list[RedVirtual] = []  # redes virtuales (SDN) del nodo o de la intersección
        self._sdn_leido = False
        self._sdn_fallido: str | None = None
        self._sdn_incluido = True  # texto de V-C13 según la versión de Proxmox
        self._avanzado = False
        self._avanzados: list[QWidget] = []
        # Disponibilidad de las opciones de red de la fase A (privilegio VM.Config.Network).
        self._mtu_ok = True
        self._limite_ok = True
        self._arm = False  # el servidor elegido es ARM64: sin la tarjeta Intel E1000
        self._texto_mtu_bloqueado = ""
        self._texto_limite_bloqueado = ""
        self._rejilla = QGridLayout()
        self._rejilla.setHorizontalSpacing(8)
        self._rejilla.setVerticalSpacing(4)
        self._cabeceras: dict[int, QLabel] = {}
        for col, texto, clave in (
            (_C_INDICE, QCoreApplication.translate("TablaRedes", "Interfaz"), None),
            (_C_BRIDGE, QCoreApplication.translate("TablaRedes", "Red (bridge)"), "bridge"),
            (_C_MODELO, QCoreApplication.translate("TablaRedes", "Tarjeta"), "modelo_red"),
            (_C_VLAN, QCoreApplication.translate("TablaRedes", "VLAN"), "vlan"),
            (_C_MTU, QCoreApplication.translate("TablaRedes", "MTU"), None),
            (_C_LIMITE, QCoreApplication.translate("TablaRedes", "Límite (MB/s)"), None),
        ):
            lbl = QLabel(texto)
            lbl.setProperty("secundario", True)
            if clave:
                lbl.setToolTip(ayuda(clave))
            self._cabeceras[col] = lbl
            self._rejilla.addWidget(lbl, 0, col)
        self._avanzados.append(self._cabeceras[_C_MODELO])
        self._avanzados.append(self._cabeceras[_C_MTU])
        self._avanzados.append(self._cabeceras[_C_LIMITE])
        cab_mac = QLabel(QCoreApplication.translate("TablaRedes", "MAC"))
        cab_mac.setProperty("secundario", True)
        cab_mac.setToolTip(ayuda("mac_origen"))
        cab_mac.hide()  # solo hay columna si alguna tarjeta trae la MAC de origen
        self._cabeceras[_C_MAC] = cab_mac
        self._rejilla.addWidget(cab_mac, 0, _C_MAC)
        self._rejilla.setColumnStretch(_C_BRIDGE, 1)
        self._agregar = QPushButton(QCoreApplication.translate("TablaRedes", "Agregar interfaz"))
        self._agregar.clicked.connect(lambda: self.agregar_red())
        self._errores = mensaje(error=True)
        self._aviso_nodo = mensaje(aviso=True)
        self._sin_redes = mensaje(error=True)
        self._aviso_opciones = mensaje(aviso=True)
        self._sin_vnets = etiqueta("", secundario=True)  # V-C13: visible sin pasar el ratón
        self._sin_vnets.hide()
        self._aviso_redes = mensaje(aviso=True)  # redes ocultas y nodos sin leer (RF-C2.3)
        self._motivo_vlan = mensaje(aviso=True)  # por qué una VLAN está deshabilitada (RF-C2.2)
        self._nota_mtu = etiqueta(texto_mtu_solo_virtio(), secundario=True)
        self._nota_mtu.hide()
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addLayout(self._rejilla)
        capa.addWidget(self._agregar, 0, Qt.AlignmentFlag.AlignLeft)
        capa.addWidget(self._sin_redes)
        capa.addWidget(self._sin_vnets)
        capa.addWidget(self._aviso_redes)
        capa.addWidget(self._motivo_vlan)
        capa.addWidget(self._nota_mtu)
        capa.addWidget(self._aviso_opciones)
        capa.addWidget(self._errores)
        capa.addWidget(self._aviso_nodo)
        self._aplicar_visibilidad()

    @property
    def widgets_avanzados(self) -> list[QWidget]:
        return list(self._avanzados)

    def establecer_avanzado(self, avanzado: bool) -> None:
        self._avanzado = avanzado
        self._aplicar_visibilidad()

    def _aplicar_visibilidad(self) -> None:
        for w in self._avanzados:
            w.setVisible(self._avanzado)
        self._refrescar_nota_mtu()

    def _refrescar_nota_mtu(self) -> None:
        """Explica por qué el MTU de una tarjeta que no es VirtIO está deshabilitado."""
        hay_otra = any(f.modelo.currentData() != ModeloRed.VIRTIO for f in self._filas)
        self._nota_mtu.setVisible(self._avanzado and self._mtu_ok and hay_otra)

    def establecer_bridges(
        self,
        bridges: Sequence[Bridge],
        vnets: Sequence[RedVirtual] = (),
        *,
        sdn_leido: bool = False,
        sdn_incluido: bool = True,
        ocultas: int = 0,
        sin_leer: Sequence[str] = (),
        sdn_fallido: str | None = None,
    ) -> list[str]:
        """Recarga las redes del nodo (bridges y, si las hay, VNets); devuelve las que ya no
        existen (CA-11.7).

        ``sdn_leido`` dice que se leyeron las VNets del nodo (sin ellas sale el texto V-C13);
        ``sdn_incluido`` elige el texto según la versión; ``ocultas`` y ``sin_leer`` son el
        resultado de la intersección de nodos de un lote (RF-C2.3); ``sdn_fallido`` es el nodo
        cuya lectura de redes virtuales falló (se avisa en vez de callar, CA-C2.1.3).
        """
        self._bridges = list(bridges)
        self._vnets = list(vnets)
        self._sdn_leido = sdn_leido
        self._sdn_incluido = sdn_incluido
        self._sdn_fallido = sdn_fallido
        self._refrescar_textos_sdn(ocultas, sin_leer)
        perdidos: list[str] = []
        for f in self._filas:
            previo = f.bridge.currentData() or f.perdido
            self._llenar_bridge(f)
            idx = f.bridge.findData(previo) if previo else -1
            f.bridge.setCurrentIndex(idx)
            f.perdido = str(previo) if idx < 0 and previo else None
            if previo and previo == f.ausente:
                # El valor cargado sigue sin existir en este nodo: se sigue mostrando.
                if idx >= 0 and previo in {b.nombre for b in self._bridges}:
                    f.ausente = None
                else:
                    f.perdido = str(previo)
                    perdidos.append(str(previo))
            elif idx < 0 and previo:
                perdidos.append(str(previo))
        self._agregar.setEnabled(bool(self._bridges or self._vnets))
        for f in self._filas:
            self._aplicar_estado_fila(f)
        self._refrescar_motivo_vlan()
        poner_mensaje(
            self._sin_redes,
            None
            if self._bridges or self._vnets
            else QCoreApplication.translate(
                "TablaRedes", "El nodo no tiene redes (bridges) disponibles"
            ),
        )
        self.cambiado.emit()
        return perdidos

    def establecer_redes(
        self, redes: Sequence[InterfazRed], *, conservar_ausentes: bool = False
    ) -> None:
        """Sustituye las filas por las redes dadas.

        Con ``conservar_ausentes`` (carga de un lote o perfil) un bridge que el nodo no tiene
        se muestra como «x (no existe)» y sigue siendo el valor de la interfaz: la validación lo
        marca y no se crea nada hasta que el usuario elija otro (CA-G04.3).
        """
        for f in list(self._filas):
            self._quitar_fila(f, emitir=False)
        for r in redes:
            self._nueva_fila(r, conservar_ausente=conservar_ausentes)
        self._renumerar()
        self._refrescar_opciones(emitir=False)
        self.cambiado.emit()

    def establecer_macs_origen(self, macs: Sequence[str | None]) -> None:
        """Ofrece la casilla «Conservar la MAC» en cada tarjeta que trae MAC de origen (la del
        XML de libvirt), aunque no se haya pedido en el asistente: queda desmarcada, salvo en
        las tarjetas que ya la conservan. Las filas se emparejan por posición."""
        for f, mac in zip(self._filas, macs, strict=False):
            if not mac or f.mac_origen:
                continue
            f.mac_origen = mac
            f.chk_mac.setText(f"{texto_nombre_opcion_d('conservar_mac')} ({mac})")
            f.chk_mac.blockSignals(True)
            f.chk_mac.setChecked(False)
            f.chk_mac.blockSignals(False)
            f.chk_mac.show()
        self._refrescar_columna_mac()

    def establecer_arquitectura(self, arq: Arquitectura) -> None:
        """En un servidor ARM64 no existe la tarjeta Intel E1000: se oculta de la lista.

        Solo oculta la opción; el valor de una tarjeta no cambia aquí (lo adapta el formulario
        con V-D08 y avisa).
        """
        arm = arq == Arquitectura.AARCH64
        if arm == self._arm:
            return
        self._arm = arm
        for f in self._filas:
            self._aplicar_arquitectura(f)

    def _aplicar_arquitectura(self, f: _FilaRed) -> None:
        posicion = f.modelo.findData(ModeloRed.E1000)
        if posicion < 0:
            return
        cast(QListView, f.modelo.view()).setRowHidden(posicion, self._arm)
        item = cast(QStandardItemModel, f.modelo.model()).item(posicion)
        if item is not None:
            item.setEnabled(not self._arm)

    def establecer_modelo_todas(self, modelo: ModeloRed) -> None:
        """Pone la misma tarjeta en todas las redes (lo usa el asistente de SO)."""
        for f in self._filas:
            idx = f.modelo.findData(modelo)
            if idx >= 0:
                f.modelo.setCurrentIndex(idx)

    def vlan_no_numericas(self) -> list[str]:
        """Etiquetas («net0»…) de las interfaces cuya VLAN escrita no es un número entero."""
        malas: list[str] = []
        for f in self._filas:
            texto = f.vlan.text().strip()
            if not texto:
                continue
            try:
                int(texto)
            except ValueError:
                malas.append(f.indice.text())
        return malas

    def valores_ausentes(self) -> list[str]:
        """Bridges cargados que el nodo actual no tiene y siguen sin reemplazar."""
        return list(dict.fromkeys(f.ausente for f in self._filas if f.ausente))

    def agregar_red(self, red: InterfazRed | None = None) -> None:
        if red is None:
            red = InterfazRed(bridge=bridge_por_defecto(self._bridges) or "")
        self._nueva_fila(red)
        self._renumerar()
        self.cambiado.emit()

    def redes(self) -> list[InterfazRed]:
        return [
            InterfazRed(
                bridge=str(f.bridge.currentData() or ""),
                modelo=ModeloRed(f.modelo.currentData()),
                vlan=vlan_desde_texto(f.vlan.text()),
                mtu=self._mtu_de(f),
                limite_mb=limite_desde_texto(f.limite.text()),
                mac_conservada=f.mac_origen if f.chk_mac.isChecked() else None,
            )
            for f in self._filas
        ]

    @staticmethod
    def _mtu_de(f: _FilaRed) -> int | None:
        """MTU escrito: ``None`` = heredar; un texto que no es un entero se convierte en 0 (la regla
        V-A04 lo rechaza)."""
        texto = f.mtu.currentText().strip()
        if not texto:
            return None
        indice = f.mtu.findText(texto)
        if indice >= 0:
            valor = f.mtu.itemData(indice)
            return None if valor is None else int(valor)
        try:
            return int(texto)
        except ValueError:
            return 0

    @staticmethod
    def _poner_mtu(f: _FilaRed, mtu: int | None) -> None:
        if mtu is None:
            f.mtu.setCurrentIndex(0)
        elif mtu == MTU_IGUAL_BRIDGE:
            f.mtu.setCurrentIndex(1)
        else:
            f.mtu.setCurrentIndex(-1)
            f.mtu.setEditText(str(mtu))

    def mtu_no_numericas(self) -> list[str]:
        """Etiquetas («net0»…) de las interfaces cuyo MTU escrito no es un número entero."""
        malas: list[str] = []
        for f in self._filas:
            texto = f.mtu.currentText().strip()
            if not texto or f.mtu.findText(texto) >= 0:
                continue
            try:
                int(texto)
            except ValueError:
                malas.append(f.indice.text())
        return malas

    def limites_no_numericos(self) -> list[str]:
        """Etiquetas de las interfaces cuyo límite escrito no es un número."""
        malas: list[str] = []
        for f in self._filas:
            texto = f.limite.text().strip().replace(",", ".")
            if not texto:
                continue
            try:
                float(texto)
            except ValueError:
                malas.append(f.indice.text())
        return malas

    def establecer_disponibilidad(self, estados: Mapping[OpcionA, EstadoOpcion]) -> None:
        """Habilita o deshabilita MTU y límite según ``VM.Config.Network`` (RF-A0.3).

        Un valor ya escrito en una opción que deja de estar disponible vuelve a su valor por
        defecto con un aviso (CL-A15). El texto de ayuda nombra el privilegio y la ruta.
        """
        mtu = estados.get(OpcionA.MTU)
        limite = estados.get(OpcionA.LIMITE_RED)
        self._mtu_ok = mtu is None or mtu.disponibilidad != Disponibilidad.NO
        self._limite_ok = limite is None or limite.disponibilidad != Disponibilidad.NO
        self._texto_mtu_bloqueado = "" if self._mtu_ok or mtu is None else texto_estado_opcion(mtu)
        self._texto_limite_bloqueado = (
            "" if self._limite_ok or limite is None else texto_estado_opcion(limite)
        )
        self._refrescar_opciones(emitir=True)

    def _refrescar_opciones(self, *, emitir: bool) -> None:
        """Aplica la disponibilidad a todas las filas: lo que no se puede usar vuelve a su valor
        por defecto (con aviso) y se deshabilita con la explicación al lado."""
        avisos: list[str] = []
        for f in self._filas:
            if not self._mtu_ok and self._mtu_de(f) is not None:
                self._poner_mtu(f, None)
                avisos.append(texto_opcion_restablecida(OpcionA.MTU.value, ""))
            if not self._limite_ok and f.limite.text().strip():
                f.limite.clear()
                avisos.append(texto_opcion_restablecida(OpcionA.LIMITE_RED.value, ""))
        for f in self._filas:
            self._aplicar_estado_fila(f)
        explicaciones = [self._texto_mtu_bloqueado, self._texto_limite_bloqueado]
        poner_mensaje(
            self._aviso_opciones,
            "\n".join(dict.fromkeys([*avisos, *(x for x in explicaciones if x)])),
            aviso=True,
        )
        self._refrescar_nota_mtu()
        if avisos and emitir:
            self.cambiado.emit()

    def _aplicar_estado_fila(self, f: _FilaRed) -> None:
        """MTU solo con VirtIO y con privilegio; el límite, solo con privilegio."""
        virtio = f.modelo.currentData() == ModeloRed.VIRTIO
        f.mtu.setEnabled(self._mtu_ok and virtio)
        f.limite.setEnabled(self._limite_ok)
        bloqueada = self._vlan_bloqueada(f)
        f.vlan.setEnabled(not bloqueada)
        motivo_vlan = texto_vlan_no_vlanaware() if bloqueada else ""
        f.vlan.setToolTip(motivo_vlan)
        f.vlan.setAccessibleDescription(motivo_vlan)
        motivo_mtu = (
            self._texto_mtu_bloqueado
            if not self._mtu_ok
            else ("" if virtio else texto_mtu_solo_virtio())
        )
        f.mtu.setToolTip(motivo_mtu)
        f.mtu.setAccessibleDescription(motivo_mtu)
        f.limite.setToolTip(self._texto_limite_bloqueado)
        f.limite.setAccessibleDescription(self._texto_limite_bloqueado)

    def hay_bridges(self) -> bool:
        return bool(self._bridges or self._vnets)

    def _refrescar_textos_sdn(self, ocultas: int, sin_leer: Sequence[str]) -> None:
        """V-C13 (sin VNets visibles) y los avisos de la intersección de nodos."""
        self._sin_vnets.setText(texto_sin_vnets(self._sdn_incluido))
        self._sin_vnets.setVisible(self._sdn_leido and not self._vnets)
        avisos: list[str] = []
        if ocultas:
            avisos.append(texto_redes_ocultas(ocultas))
        if sin_leer:
            avisos.append(texto_nodos_sin_leer(sin_leer))
        if self._sdn_fallido:
            avisos.append(texto_sdn_sin_leer(self._sdn_fallido))
        poner_mensaje(self._aviso_redes, "\n".join(avisos) or None, aviso=True)
        self._cabeceras[_C_BRIDGE].setText(
            QCoreApplication.translate("TablaRedes", "Red")
            if self._vnets
            else QCoreApplication.translate("TablaRedes", "Red (bridge)")
        )

    def vnet_de(self, nombre: str) -> RedVirtual | None:
        """La VNet de ese nombre si NO es también un bridge (como valida el núcleo)."""
        if any(b.nombre == nombre for b in self._bridges):
            return None
        return next((v for v in self._vnets if v.nombre == nombre), None)

    def _vlan_bloqueada(self, f: _FilaRed) -> bool:
        """``True`` si la red elegida es una VNet que no es «vlanaware» (RF-C2.2)."""
        nombre = f.bridge.currentData()
        vnet = self.vnet_de(str(nombre)) if nombre else None
        return vnet is not None and not vnet.vlan_aware

    def _refrescar_motivo_vlan(self) -> None:
        bloqueadas = [f.indice.text() for f in self._filas if self._vlan_bloqueada(f)]
        poner_mensaje(
            self._motivo_vlan,
            "\n".join(f"{n}: {texto_vlan_no_vlanaware()}" for n in bloqueadas) or None,
            aviso=True,
        )

    def aplicar_problemas(self, problemas: Sequence[Problema]) -> None:
        errores: list[str] = []
        con_vlan: set[int] = set()
        con_mtu: set[int] = set()
        con_limite: set[int] = set()
        con_mac: set[int] = set()
        for p in problemas:
            if p.severidad != Severidad.ERROR:
                continue
            if p.campo in ("mtu", "limite_red"):  # V-A12: opción sin privilegio o sin versión
                errores.append(texto_problema(p))
                continue
            if p.campo == "redes":  # reglas de la lista completa (V-23)
                errores.append(texto_problema(p))
                continue
            if not p.campo.startswith("redes["):
                continue
            try:
                i = int(p.campo[len("redes[") : p.campo.index("]")])
            except ValueError:
                continue
            if i >= len(self._filas):
                continue
            errores.append(f"{self._filas[i].indice.text()}: {texto_problema(p)}")
            if p.campo.endswith(".vlan"):
                con_vlan.add(i)
            elif p.campo.endswith(".mtu"):
                con_mtu.add(i)
            elif p.campo.endswith(".limite_mb"):
                con_limite.add(i)
            elif p.campo.endswith(".mac_conservada"):
                con_mac.add(i)
        for i, f in enumerate(self._filas):
            poner_propiedad(f.vlan, "invalido", i in con_vlan)
            poner_propiedad(f.mtu, "invalido", i in con_mtu)
            poner_propiedad(f.limite, "invalido", i in con_limite)
            poner_propiedad(f.chk_mac, "invalido", i in con_mac)
        poner_mensaje(self._errores, "\n".join(dict.fromkeys(errores)))

    def mostrar_aviso_nodo(self, texto: str | None) -> None:
        poner_mensaje(self._aviso_nodo, texto, aviso=True)

    def habilitar(self, habilitado: bool) -> None:
        self.setEnabled(habilitado)

    # --- Internos ---------------------------------------------------------------------

    def _llenar_bridge(self, f: _FilaRed) -> None:
        f.bridge.blockSignals(True)
        f.bridge.clear()
        f.bridge.setPlaceholderText(QCoreApplication.translate("TablaRedes", "Elige una red"))
        llenar_combo_red(f.bridge, self._bridges, self._vnets, ausente=f.ausente)
        f.bridge.blockSignals(False)

    def _nueva_fila(self, red: InterfazRed, *, conservar_ausente: bool = False) -> None:
        f = _FilaRed()
        if (
            conservar_ausente
            and red.bridge
            and red.bridge not in {b.nombre for b in self._bridges}
            and red.bridge not in {v.nombre for v in self._vnets}
        ):
            f.ausente = red.bridge
        self._llenar_bridge(f)
        f.bridge.setCurrentIndex(f.bridge.findData(red.bridge))
        f.modelo.setCurrentIndex(max(f.modelo.findData(red.modelo), 0))
        f.vlan.setText("" if red.vlan is None else str(red.vlan))
        self._poner_mtu(f, red.mtu)
        f.limite.setText(texto_limite(red.limite_mb))
        if red.mac_conservada:
            f.mac_origen = red.mac_conservada
            f.chk_mac.setText(f"{texto_nombre_opcion_d('conservar_mac')} ({red.mac_conservada})")
            f.chk_mac.setChecked(True)
            f.chk_mac.show()
        f.chk_mac.toggled.connect(lambda _v: self.cambiado.emit())
        f.bridge.currentIndexChanged.connect(lambda _i, fila=f: self._al_cambiar_bridge(fila))
        f.modelo.currentIndexChanged.connect(lambda _i, fila=f: self._al_cambiar_modelo(fila))
        f.vlan.textEdited.connect(lambda _t: self.cambiado.emit())
        f.mtu.currentIndexChanged.connect(lambda _i: self.cambiado.emit())
        f.mtu.editTextChanged.connect(lambda _t: self.cambiado.emit())
        f.limite.textEdited.connect(lambda _t: self.cambiado.emit())
        f.quitar.clicked.connect(lambda _c=False, fila=f: self._quitar_fila(fila))
        self._aplicar_arquitectura(f)
        self._filas.append(f)
        for col, w in f.widgets():
            self._rejilla.addWidget(w, len(self._filas), col)
        self._refrescar_columna_mac()
        for w in (f.modelo, f.mtu, f.limite):
            self._avanzados.append(w)
            w.setVisible(self._avanzado)
        self._aplicar_estado_fila(f)
        self._refrescar_nota_mtu()
        self._refrescar_motivo_vlan()

    def _al_cambiar_modelo(self, f: _FilaRed) -> None:
        """Al dejar VirtIO el MTU vuelve a «Heredar» (P-18); el MTU no vale con otras tarjetas."""
        if f.modelo.currentData() != ModeloRed.VIRTIO:
            self._poner_mtu(f, None)
        self._aplicar_estado_fila(f)
        self._refrescar_nota_mtu()
        self.cambiado.emit()

    def _al_cambiar_bridge(self, f: _FilaRed) -> None:
        if f.bridge.currentIndex() >= 0:
            f.perdido = None  # el usuario eligió otro valor
            if f.bridge.currentData() != f.ausente:
                f.ausente = None
        if self._vlan_bloqueada(f):
            f.vlan.clear()  # una VNet sin «vlanaware» no admite VLAN: no se envía ``tag``
        self._aplicar_estado_fila(f)
        self._refrescar_motivo_vlan()
        self.cambiado.emit()

    def _quitar_fila(self, f: _FilaRed, *, emitir: bool = True) -> None:
        self._filas.remove(f)
        for _col, w in f.widgets():
            self._rejilla.removeWidget(w)
            if w in self._avanzados:
                self._avanzados.remove(w)
            w.deleteLater()
        for n, resto in enumerate(self._filas, start=1):
            for col, w in resto.widgets():
                self._rejilla.addWidget(w, n, col)
        self._refrescar_nota_mtu()
        self._refrescar_columna_mac()
        if emitir:
            self._renumerar()
            self.cambiado.emit()

    def _refrescar_columna_mac(self) -> None:
        """La cabecera «MAC» solo se ve si alguna tarjeta trae la MAC de origen."""
        self._cabeceras[_C_MAC].setVisible(any(f.mac_origen for f in self._filas))

    def _renumerar(self) -> None:
        for n, f in enumerate(self._filas):
            f.indice.setText(f"net{n}")
            f.mtu.setAccessibleName(
                QCoreApplication.translate("TablaRedes", "MTU de net{n}").format(n=n)
            )
            f.limite.setAccessibleName(
                QCoreApplication.translate(
                    "TablaRedes", "Límite de velocidad de net{n} (MB/s)"
                ).format(n=n)
            )
            f.chk_mac.setAccessibleName(
                QCoreApplication.translate(
                    "TablaRedes", "Conservar la MAC de origen de net{n}"
                ).format(n=n)
            )
        self._refrescar_motivo_vlan()
