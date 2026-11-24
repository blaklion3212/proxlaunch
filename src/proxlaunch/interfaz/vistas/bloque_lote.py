"""Bloque «Lote» del formulario: cantidad, nombres, destino y opciones (RF-L01 a RF-L05, RF-L22).

Con cantidad 1 solo se ve la cantidad y el formulario funciona como en el MVP 1. Con más de
una máquina aparecen el prefijo, la vista previa de los nombres y el destino; el modo
avanzado añade separador, número inicial, relleno, VMID inicial, nodos elegidos, algoritmo
y etiquetas. Los errores V-L salen junto a su campo.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from typing import cast

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_problema_lote
from proxlaunch.interfaz.textos_d import texto_nodo_con_arquitectura
from proxlaunch.interfaz.vistas.campos import FilaCampo, boton_ayuda, etiqueta
from proxlaunch.nucleo.arquitectura.modelos import arquitectura_efectiva
from proxlaunch.nucleo.lote.constantes import MAX_LOTE
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    DefinicionLote,
    Destino,
    ModoDestino,
    PatronNombres,
    Problema,
    Severidad,
)
from proxlaunch.nucleo.lote.nombres import generar_nombres, validar_patron
from proxlaunch.nucleo.lote.planificador import validar_definicion
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.opciones.modelos import OpcionesLote

# Campos de ``Problema.campo`` -> clave de la fila que los muestra.
_FILA_DE_CAMPO = {
    "cantidad": "cantidad",
    "patron.prefijo": "prefijo",
    "patron.separador": "separador",
    "patron.inicio": "inicio",
    "patron.relleno": "relleno",
    "vmid_inicial": "vmid_inicial",
    "destino": "destino",
}


def _entero(texto: str, defecto: int = 0) -> int:
    """Entero del texto; vacío = ``defecto``; no numérico = -1 (las reglas V-L lo rechazan)."""
    t = texto.strip()
    if not t:
        return defecto
    try:
        return int(t)
    except ValueError:
        return -1


class BloqueLote(QGroupBox):
    """Define el lote: cuántas máquinas, cómo se llaman y dónde se crean."""

    cambiado = Signal()  # algo del lote cambió: hay que revalidar
    destino_cambiado = Signal()  # cambió el nodo o el modo de destino (el formulario se adapta)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QCoreApplication.translate("BloqueLote", "Lote"), parent)
        self._inv: Inventario | None = None
        self._avanzado = False
        self._ocupado = False
        self._avanzados: list[tuple[QWidget, Callable[[], bool]]] = []
        self._solo_lote: list[QWidget] = []
        self._filas: dict[str, FilaCampo] = {}
        # Lote por filas (D-22): la definición con sus filas; ``None`` = lote homogéneo.
        self._base_por_filas: DefinicionLote | None = None
        # Nodos de un lote cargado que el servidor no tiene (se muestran, no se descartan).
        self._nodos_ausentes: list[str] = []
        self._destino_de_archivo = False  # el destino viene de un lote cargado o importado
        self._en_linea: set[str] = set()  # nodos del inventario en línea (checks habilitables)

        capa = QVBoxLayout(self)
        capa.setSpacing(4)
        self._construir_cantidad(capa)
        self._construir_nombres(capa)
        self._construir_destino(capa)
        self._construir_opciones(capa)
        self._aplicar_visibilidad()

    # --- Construcción -----------------------------------------------------------------

    def _fila(self, clave: str, texto: str, campo: QWidget, ayuda_clave: str) -> FilaCampo:
        fila = FilaCampo(texto, campo, ayuda_clave)
        self._filas[clave] = fila
        return fila

    def _construir_cantidad(self, capa: QVBoxLayout) -> None:
        self.cantidad = QLineEdit("1")
        self.cantidad.setMaximumWidth(80)
        self.cantidad.setAccessibleName(QCoreApplication.translate("BloqueLote", "Cantidad"))
        self.cantidad.setPlaceholderText("1")
        fila = self._fila(
            "cantidad",
            QCoreApplication.translate("BloqueLote", "Cantidad de máquinas"),
            self.cantidad,
            "lote_cantidad",
        )
        self.cantidad.textEdited.connect(lambda _t: self._al_editar("cantidad"))
        self.cantidad.editingFinished.connect(lambda: self._tocar("cantidad"))
        capa.addWidget(fila)

    def _construir_nombres(self, capa: QVBoxLayout) -> None:
        self.prefijo = QLineEdit()
        self.prefijo.setPlaceholderText(
            QCoreApplication.translate("BloqueLote", "por ejemplo srv-web")
        )
        self.prefijo.setAccessibleName(
            QCoreApplication.translate("BloqueLote", "Prefijo de los nombres")
        )
        f_prefijo = self._fila(
            "prefijo",
            QCoreApplication.translate("BloqueLote", "Prefijo"),
            self.prefijo,
            "lote_prefijo",
        )
        self._vista_previa = etiqueta("", secundario=True)
        self._vista_previa.setAccessibleName(
            QCoreApplication.translate("BloqueLote", "Vista previa de los nombres")
        )
        self.combo_separador = QComboBox()
        self.combo_separador.addItem(QCoreApplication.translate("BloqueLote", "Guion (-)"), "-")
        self.combo_separador.addItem(QCoreApplication.translate("BloqueLote", "Ninguno"), "")
        f_sep = self._fila(
            "separador",
            QCoreApplication.translate("BloqueLote", "Separador"),
            self.combo_separador,
            "lote_separador",
        )
        self.inicio = QLineEdit("1")
        self.inicio.setMaximumWidth(100)
        f_inicio = self._fila(
            "inicio",
            QCoreApplication.translate("BloqueLote", "Número inicial"),
            self.inicio,
            "lote_inicio",
        )
        self.relleno = QLineEdit("2")
        self.relleno.setMaximumWidth(60)
        f_relleno = self._fila(
            "relleno",
            QCoreApplication.translate("BloqueLote", "Relleno (dígitos)"),
            self.relleno,
            "lote_relleno",
        )
        self.vmid_inicial = QLineEdit()
        self.vmid_inicial.setMaximumWidth(140)
        self.vmid_inicial.setPlaceholderText(QCoreApplication.translate("BloqueLote", "automático"))
        f_vmid = self._fila(
            "vmid_inicial",
            QCoreApplication.translate("BloqueLote", "Número de máquina inicial (VMID)"),
            self.vmid_inicial,
            "lote_vmid_inicial",
        )
        for clave, campo in (
            ("prefijo", self.prefijo),
            ("inicio", self.inicio),
            ("relleno", self.relleno),
            ("vmid_inicial", self.vmid_inicial),
        ):
            campo.textEdited.connect(lambda _t, c=clave: self._al_editar(c))
            campo.editingFinished.connect(lambda c=clave: self._tocar(c))
        self.combo_separador.currentIndexChanged.connect(lambda _i: self._al_editar("separador"))
        for w in (f_prefijo, self._vista_previa):
            capa.addWidget(w)
            self._solo_lote.append(w)
        for w in (f_sep, f_inicio, f_relleno, f_vmid):
            capa.addWidget(w)
            self._solo_lote.append(w)
            self._avanzados.append((w, lambda: True))

    def _construir_destino(self, capa: QVBoxLayout) -> None:
        self._radio_auto = QRadioButton(QCoreApplication.translate("BloqueLote", "Automático"))
        self._radio_un_nodo = QRadioButton(QCoreApplication.translate("BloqueLote", "Un nodo"))
        self._radio_elegidos = QRadioButton(
            QCoreApplication.translate("BloqueLote", "Nodos elegidos")
        )
        self._radio_auto.setChecked(True)
        self._grupo_destino = QButtonGroup(self)
        for r in (self._radio_auto, self._radio_un_nodo, self._radio_elegidos):
            self._grupo_destino.addButton(r)
            r.toggled.connect(self._al_cambiar_destino)
        self.combo_nodo = QComboBox()
        self.combo_nodo.setAccessibleName(
            QCoreApplication.translate("BloqueLote", "Nodo de destino")
        )
        self.combo_nodo.currentIndexChanged.connect(self._al_cambiar_nodo)
        self._nodos_elegidos = QWidget()
        self._capa_nodos = QVBoxLayout(self._nodos_elegidos)
        self._capa_nodos.setContentsMargins(0, 0, 0, 0)
        self._checks_nodos: dict[str, QCheckBox] = {}
        self.combo_algoritmo = QComboBox()
        self.combo_algoritmo.addItem(
            QCoreApplication.translate("BloqueLote", "Equilibrado"), Algoritmo.EQUILIBRADO
        )
        self.combo_algoritmo.addItem(
            QCoreApplication.translate("BloqueLote", "Por turnos"), Algoritmo.POR_TURNOS
        )
        self.combo_algoritmo.setAccessibleName(
            QCoreApplication.translate("BloqueLote", "Algoritmo de reparto")
        )
        self.combo_algoritmo.currentIndexChanged.connect(lambda _i: self._al_editar("destino"))

        contenedor = QWidget()
        cc = QVBoxLayout(contenedor)
        cc.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(self._radio_auto)
        fila.addWidget(self._radio_un_nodo)
        fila.addWidget(self.combo_nodo, 1)
        cc.addLayout(fila)
        cc.addWidget(self._radio_elegidos)
        # Nota del modo básico cuando el lote cargado usa nodos elegidos (solo lectura).
        self._nota_elegidos = etiqueta(
            QCoreApplication.translate(
                "BloqueLote",
                "Este lote usa nodos elegidos; cámbialo en modo avanzado.",
            ),
            secundario=True,
        )
        self._nota_elegidos.hide()
        cc.addWidget(self._nota_elegidos)
        cc.addWidget(self._nodos_elegidos)
        self.fila_destino = self._fila(
            "destino",
            QCoreApplication.translate("BloqueLote", "Dónde crearlas"),
            contenedor,
            "lote_destino",
        )
        self.fila_algoritmo = FilaCampo(
            QCoreApplication.translate("BloqueLote", "Reparto"),
            self.combo_algoritmo,
            "lote_equilibrado",
        )
        self._boton_por_turnos = boton_ayuda("lote_por_turnos")
        cast(QGridLayout, self.fila_algoritmo.layout()).addWidget(self._boton_por_turnos, 0, 3)
        for w in (self.fila_destino, self.fila_algoritmo):
            capa.addWidget(w)
            self._solo_lote.append(w)
        self._avanzados.append((self._radio_elegidos, lambda: True))
        self._avanzados.append((self._nodos_elegidos, lambda: self._radio_elegidos.isChecked()))
        self._avanzados.append((self.fila_algoritmo, lambda: not self._radio_un_nodo.isChecked()))

    def _construir_opciones(self, capa: QVBoxLayout) -> None:
        self.chk_etiquetar = QCheckBox(
            QCoreApplication.translate("BloqueLote", "Etiquetar las máquinas")
        )
        self.chk_etiquetar.setChecked(True)
        self.chk_etiquetar.setToolTip(self._ayuda("lote_etiqueta"))
        self.chk_etiquetar.toggled.connect(lambda _c: self._al_editar("etiquetas"))
        self._boton_etiqueta = boton_ayuda("lote_etiqueta")
        contenedor = QWidget()
        h = QHBoxLayout(contenedor)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.chk_etiquetar)
        h.addWidget(self._boton_etiqueta)
        h.addStretch(1)
        capa.addWidget(contenedor)
        # Visible también con una máquina, solo en modo avanzado (ver _aplicar_visibilidad).
        self._fila_etiquetar = contenedor

    @staticmethod
    def _ayuda(clave: str) -> str:
        from proxlaunch.interfaz.ayuda import ayuda

        return ayuda(clave)

    # --- Modo e inventario ------------------------------------------------------------

    def establecer_modo(self, avanzado: bool) -> None:
        """Muestra u oculta lo avanzado sin perder lo escrito (CA-L22.3)."""
        self._avanzado = avanzado
        self._aplicar_visibilidad()

    @property
    def es_lote(self) -> bool:
        """Más de una máquina: se usan nombres, destino y resumen del lote."""
        return self._base_por_filas is not None or self.cantidad_valor() > 1

    @property
    def es_por_filas(self) -> bool:
        """Lote por filas (CSV o archivo): cantidad, nombres y destino los fijan las filas."""
        return self._base_por_filas is not None

    def establecer_cantidad(self, n: int) -> None:
        """Cambia la cantidad por código (por ejemplo «Reducir a N»)."""
        self.cantidad.setText(str(n))
        self._aplicar_visibilidad()
        self.cambiado.emit()

    def cantidad_valor(self) -> int:
        """Cantidad escrita; 0 si el texto no es un número (V-L01 lo rechaza)."""
        if self._base_por_filas is not None:
            return self._base_por_filas.cantidad
        t = self.cantidad.text().strip()
        try:
            return int(t)
        except ValueError:
            return 0

    def _aplicar_visibilidad(self) -> None:
        cluster = self._inv is not None and self._inv.topologia.es_cluster
        if self._base_por_filas is not None:
            self._visibilidad_por_filas(cluster)
            return
        self.setVisible(True)
        self._filas["cantidad"].setVisible(True)
        lote = self.es_lote or self.cantidad_valor() > MAX_LOTE
        for w in self._solo_lote:
            w.setVisible(lote)
        for w, cond in self._avanzados:
            w.setVisible(lote and self._avanzado and cond())
        # «Etiquetar las máquinas» también aplica con una sola máquina (servidores que
        # restringen las etiquetas).
        self._fila_etiquetar.setVisible(self._avanzado and self.cantidad_valor() >= 1)
        # En un servidor individual no hay selector de destino ni de reparto (CA-L05).
        self.fila_destino.setVisible(lote and cluster)
        if not (lote and cluster):
            self.fila_algoritmo.setVisible(False)
            self._nodos_elegidos.setVisible(False)
            self._nota_elegidos.setVisible(False)
        else:
            self.fila_algoritmo.setVisible(self._avanzado and not self._radio_un_nodo.isChecked())
            # Con nodos elegidos marcados (lote cargado) se muestran siempre; en básico en
            # solo lectura y con una nota, porque el destino los respeta (CA-G03.5).
            elegidos = self._radio_elegidos.isChecked()
            self._nodos_elegidos.setVisible(elegidos)
            self._nota_elegidos.setVisible(elegidos and not self._avanzado)
        self._radio_elegidos.setVisible(
            lote and cluster and (self._avanzado or self._radio_elegidos.isChecked())
        )
        self._radio_elegidos.setEnabled(self._avanzado)
        for nombre, check in self._checks_nodos.items():
            check.setEnabled(
                self._avanzado and (nombre in self._en_linea or nombre in self._nodos_ausentes)
            )
        self.combo_nodo.setEnabled(self._radio_un_nodo.isChecked())
        self._actualizar_vista_previa()

    def _visibilidad_por_filas(self, cluster: bool) -> None:
        """Por filas se oculta lo que fijan las filas; quedan reparto, VMID inicial y etiquetas."""
        self.setVisible(self._avanzado)  # en básico no queda nada que mostrar
        self._filas["cantidad"].setVisible(False)
        for w in self._solo_lote:
            w.setVisible(False)
        for w, _cond in self._avanzados:
            w.setVisible(False)
        self._filas["vmid_inicial"].setVisible(self._avanzado)
        self.fila_algoritmo.setVisible(self._avanzado and cluster)
        self._fila_etiquetar.setVisible(self._avanzado)
        self._vista_previa.hide()

    def establecer_inventario(self, inv: Inventario) -> None:
        """Carga los nodos del servidor; conserva la elección si el nodo sigue existiendo."""
        self._inv = inv
        estaba_ocupado = self._ocupado
        self._ocupado = True
        try:
            previo = self.combo_nodo.currentData()
            marcados = {n for n, c in self._checks_nodos.items() if c.isChecked()}
            self.combo_nodo.clear()
            while self._capa_nodos.count():
                item = self._capa_nodos.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.deleteLater()
            self._checks_nodos = {}
            self._en_linea = {n.nombre for n in inv.topologia.nodos if n.en_linea}
            sin_conexion = QCoreApplication.translate("BloqueLote", "Sin conexión")
            for n in inv.topologia.nodos:
                # Un nodo ARM64 lleva la marca «ARM64, experimental» (CA-D2.12.1).
                nombre = texto_nodo_con_arquitectura(n.nombre, arquitectura_efectiva(inv, n.nombre))
                texto = nombre if n.en_linea else f"{nombre} — {sin_conexion}"
                self.combo_nodo.addItem(texto, n.nombre)
                check = QCheckBox(texto)
                check.setEnabled(n.en_linea and self._avanzado)
                check.setChecked(n.en_linea and (not marcados or n.nombre in marcados))
                check.toggled.connect(lambda _c: self._al_editar("destino"))
                self._capa_nodos.addWidget(check)
                self._checks_nodos[n.nombre] = check
                if not n.en_linea:
                    modelo = cast(QStandardItemModel, self.combo_nodo.model())
                    modelo.item(self.combo_nodo.count() - 1).setEnabled(False)
            existentes = {n.nombre for n in inv.topologia.nodos}
            self._nodos_ausentes = [n for n in self._nodos_ausentes if n not in existentes]
            if self._destino_de_archivo:
                # Un lote cargado nunca cambia de nodo en silencio: el nodo que el servidor
                # nuevo no tiene queda visible como ausente y se informa como desajuste.
                pedidos = (
                    [previo]
                    if self._radio_un_nodo.isChecked() and previo
                    else sorted(marcados)
                    if self._radio_elegidos.isChecked()
                    else []
                )
                for nodo in pedidos:
                    if nodo not in existentes and nodo not in self._nodos_ausentes:
                        self._nodos_ausentes.append(nodo)
            for nodo in self._nodos_ausentes:
                self._agregar_nodo_ausente(nodo, marcado=True)
            idx = self.combo_nodo.findData(previo) if previo else -1
            if idx < 0:
                idx = next((i for i, n in enumerate(inv.topologia.nodos) if n.en_linea), -1)
            self.combo_nodo.setCurrentIndex(idx)
        finally:
            self._ocupado = estaba_ocupado
        self._aplicar_visibilidad()

    def _agregar_nodo_ausente(self, nodo: str, *, marcado: bool) -> None:
        """Un nodo del lote cargado que el servidor no tiene: visible, marcado y deshabilitado."""
        texto = QCoreApplication.translate("BloqueLote", "{nodo} (no existe)").format(nodo=nodo)
        self.combo_nodo.addItem(texto, nodo)
        cast(QStandardItemModel, self.combo_nodo.model()).item(
            self.combo_nodo.count() - 1
        ).setEnabled(False)
        check = QCheckBox(texto)
        check.setEnabled(self._avanzado)  # en avanzado se puede quitar de la lista
        check.setChecked(marcado)
        check.toggled.connect(lambda c, n=nodo: self._al_alternar_ausente(n, c))
        self._capa_nodos.addWidget(check)
        self._checks_nodos[nodo] = check

    def _al_alternar_ausente(self, nodo: str, marcado: bool) -> None:
        """Quitar de la lista un nodo que el servidor no tiene resuelve su desajuste."""
        if not marcado and nodo in self._nodos_ausentes:
            self._nodos_ausentes.remove(nodo)
        self._al_editar("destino")

    # --- Carga de una definición (lote guardado, RF-G03) ------------------------------

    def establecer_definicion(self, definicion: DefinicionLote) -> None:
        """Rellena el bloque con la definición de un lote guardado (carga atómica, RNF-M11).

        Homogéneo: cantidad, patrón, VMID inicial, destino, reparto y etiquetas. Por filas:
        entra en modo «por filas» (ver ``establecer_por_filas``). La plantilla de hardware la
        aplica quien llama con ``FormularioVM.aplicar_hardware``. No dispara ningún cálculo:
        emite ``cambiado`` y ``destino_cambiado`` una sola vez al final.
        """
        if definicion.es_por_filas:
            self.establecer_por_filas(definicion)
            return
        self._base_por_filas = None
        self._destino_de_archivo = True
        self._ocupado = True
        try:
            self.cantidad.setText(str(definicion.cantidad))
            patron = definicion.patron
            self.prefijo.setText(patron.prefijo)
            i = self.combo_separador.findData(patron.separador)
            if i < 0:
                self.combo_separador.addItem(patron.separador, patron.separador)
                i = self.combo_separador.count() - 1
            self.combo_separador.setCurrentIndex(i)
            self.inicio.setText(str(patron.inicio))
            self.relleno.setText(str(patron.relleno))
            self.vmid_inicial.setText(
                "" if definicion.vmid_inicial is None else str(definicion.vmid_inicial)
            )
            self.chk_etiquetar.setChecked(definicion.etiquetar)
            self._aplicar_destino(definicion.destino)
        finally:
            self._ocupado = False
        for fila in self._filas.values():
            fila.marcar_tocado()
        self._aplicar_visibilidad()
        self.destino_cambiado.emit()
        self.cambiado.emit()

    def _aplicar_destino(self, destino: Destino) -> None:
        indice = self.combo_algoritmo.findData(destino.algoritmo)
        self.combo_algoritmo.setCurrentIndex(max(indice, 0))
        # Se descartan los nodos ausentes anteriores y se muestran los de este destino.
        existentes = (
            {n.nombre for n in self._inv.topologia.nodos} if self._inv is not None else set()
        )
        self._nodos_ausentes = [n for n in destino.nodos if n not in existentes]
        if self._inv is not None:
            self.establecer_inventario(self._inv)
        if destino.modo == ModoDestino.UN_NODO:
            self._radio_un_nodo.setChecked(True)
            if destino.nodos:
                j = self.combo_nodo.findData(destino.nodos[0])
                if j < 0:
                    self._agregar_nodo_ausente(destino.nodos[0], marcado=False)
                    j = self.combo_nodo.findData(destino.nodos[0])
                self.combo_nodo.setCurrentIndex(j)
        elif destino.modo == ModoDestino.NODOS_ELEGIDOS:
            self._radio_elegidos.setChecked(True)
            for nombre, check in self._checks_nodos.items():
                check.setChecked(nombre in destino.nodos)
        else:
            self._radio_auto.setChecked(True)

    def establecer_por_filas(self, definicion: DefinicionLote) -> None:
        """Entra en modo «por filas» (D-22): oculta cantidad, nombres y destino (CA-C01.3).

        Quedan el algoritmo de reparto (avanzado), el VMID inicial de las filas sin VMID y las
        etiquetas. Las filas mismas se muestran en ``PanelLoteFilas``.
        """
        self._ocupado = True
        try:
            self._base_por_filas = definicion
            self.vmid_inicial.setText(
                "" if definicion.vmid_inicial is None else str(definicion.vmid_inicial)
            )
            self.chk_etiquetar.setChecked(definicion.etiquetar)
            indice = self.combo_algoritmo.findData(definicion.destino.algoritmo)
            self.combo_algoritmo.setCurrentIndex(max(indice, 0))
            self._radio_auto.setChecked(True)
        finally:
            self._ocupado = False
        for fila in self._filas.values():
            fila.marcar_tocado()
        self._aplicar_visibilidad()
        self.destino_cambiado.emit()
        self.cambiado.emit()

    def actualizar_filas(self, definicion: DefinicionLote) -> None:
        """Cambia las filas del lote por filas (por ejemplo tras quitar las que no caben)."""
        self._base_por_filas = definicion
        self._aplicar_visibilidad()
        self.cambiado.emit()

    def reiniciar(self) -> None:
        """Deja el bloque como recién creado: una máquina, sin prefijo y reparto automático.

        Lo usa la ventana cuando reinicia el formulario (el lote cargado o armado a mano no
        sobrevive a un cambio de servidor o a «Cerrar sesión»).
        """
        self._ocupado = True
        try:
            self._base_por_filas = None
            self._destino_de_archivo = False
            self._nodos_ausentes = []
            self.cantidad.setText("1")
            self.prefijo.setText("")
            self.combo_separador.setCurrentIndex(0)
            self.inicio.setText("1")
            self.relleno.setText("2")
            self.vmid_inicial.setText("")
            self.chk_etiquetar.setChecked(True)
            self.combo_algoritmo.setCurrentIndex(0)
            self._radio_auto.setChecked(True)
        finally:
            self._ocupado = False
        for fila in self._filas.values():
            fila.tocado = False
            fila.mostrar_error(None)
        if self._inv is not None:
            self.establecer_inventario(self._inv)
        else:
            self._aplicar_visibilidad()
        self.destino_cambiado.emit()
        self.cambiado.emit()

    def salir_de_por_filas(self) -> None:
        """Vuelve al lote homogéneo (cantidad 1) con los demás valores como estaban."""
        if self._base_por_filas is None:
            return
        self._base_por_filas = None
        self._destino_de_archivo = False
        self.cantidad.setText("1")
        self._aplicar_visibilidad()
        self.destino_cambiado.emit()
        self.cambiado.emit()

    # --- Lectura ----------------------------------------------------------------------

    def patron(self) -> PatronNombres:
        return PatronNombres(
            prefijo=self.prefijo.text().strip(),
            separador=str(self.combo_separador.currentData()),
            inicio=_entero(self.inicio.text(), 1),
            relleno=_entero(self.relleno.text(), 2),
        )

    def destino(self) -> Destino:
        algoritmo = Algoritmo(self.combo_algoritmo.currentData())
        if self._radio_un_nodo.isChecked():
            nodo = str(self.combo_nodo.currentData() or "")
            return Destino(ModoDestino.UN_NODO, (nodo,) if nodo else (), algoritmo)
        if self._radio_elegidos.isChecked():
            nodos = tuple(n for n, c in self._checks_nodos.items() if c.isChecked())
            return Destino(ModoDestino.NODOS_ELEGIDOS, nodos, algoritmo)
        return Destino(ModoDestino.AUTOMATICO, (), algoritmo)

    @property
    def modo_destino(self) -> ModoDestino:
        return self.destino().modo

    @property
    def nodo_elegido(self) -> str:
        """Nodo del modo «Un nodo» (vacío en los demás modos)."""
        d = self.destino()
        return d.nodos[0] if d.modo == ModoDestino.UN_NODO and d.nodos else ""

    def definicion(self, plantilla: ConfiguracionVM) -> DefinicionLote:
        """Lote que describe el bloque con la configuración del formulario como plantilla.

        Por filas devuelve las filas cargadas con los ajustes actuales del bloque (algoritmo,
        VMID inicial, etiquetas); el hardware sale de las filas (D-22), pero las opciones de lote
        de la fase A (encender, notas, etiquetas, pool, protección) salen del formulario y cada
        fila puede sobrescribirlas (DT-A10).
        """
        texto_vmid = self.vmid_inicial.text().strip()
        base = self._base_por_filas
        if base is not None:
            return dataclasses.replace(
                base,
                destino=Destino(
                    ModoDestino.AUTOMATICO, (), Algoritmo(self.combo_algoritmo.currentData())
                ),
                vmid_inicial=_entero(texto_vmid, 0) if texto_vmid else None,
                etiquetar=self.chk_etiquetar.isChecked(),
                opciones=OpcionesLote.desde_config(plantilla),
            )
        return DefinicionLote(
            plantilla=plantilla,
            cantidad=self.cantidad_valor(),
            patron=self.patron(),
            destino=self.destino(),
            vmid_inicial=_entero(texto_vmid, 0) if texto_vmid else None,
            etiquetar=self.chk_etiquetar.isChecked(),
        )

    def nombres_previstos(self) -> list[str]:
        """Todos los nombres si el patrón es válido; lista vacía si no."""
        if self._base_por_filas is not None:
            return []
        n = self.cantidad_valor()
        if not 1 <= n <= MAX_LOTE:
            return []
        patron = self.patron()
        if any(p.severidad == Severidad.ERROR for p in validar_patron(patron, n)):
            return []
        return generar_nombres(patron, n)

    # --- Validación -------------------------------------------------------------------

    def problemas(self, plantilla: ConfiguracionVM) -> list[Problema]:
        """Errores V-L que se deciden sin consultar al servidor (V-L01..V-L04, V-L07, V-L13)."""
        inv = self._inv
        if inv is None:
            return []
        definicion = self.definicion(plantilla)
        detectada = (inv.version.mayor, inv.version.menor)
        todos = validar_definicion(definicion, inv, detectada)
        resultado: list[Problema] = []
        # Con un prefijo no vacío y sin caracteres de inyección, el mensaje útil es V-L04
        # (primer nombre inválido y su causa), no el genérico de V-L02 (CA-L02.4).
        hay_nombre_invalido = any(p.regla == "V-L04" and "nombre" in p.params for p in todos)
        inyeccion = any(c in definicion.patron.prefijo for c in ",=&;\r\n")
        for p in todos:
            if (
                p.regla == "V-L02"
                and hay_nombre_invalido
                and not inyeccion
                and definicion.patron.prefijo
            ):
                continue
            if p.regla == "V-L15":
                continue  # solo bloquea crear de verdad: lo decide la ventana
            if not self.es_lote and p.regla != "V-L01":
                continue  # con una sola máquina el nombre y el destino son los de M1
            if p.regla == "V-L01" and self.cantidad_valor() > MAX_LOTE:
                p = Problema(p.regla, p.severidad, p.campo, {**p.params, "causa": "maximo"})
            if p.regla == "V-L02" and not definicion.patron.prefijo:
                p = Problema(p.regla, p.severidad, p.campo, {**p.params, "causa": "vacio"})
            resultado.append(p)
        return resultado

    def aplicar_problemas(self, problemas: Sequence[Problema]) -> None:
        """Muestra cada error junto a su campo y la vista previa de los nombres."""
        por_fila: dict[str, str] = {}
        for p in problemas:
            if p.severidad != Severidad.ERROR:
                continue
            clave = _FILA_DE_CAMPO.get(p.campo or "")
            if clave is not None and clave not in por_fila:
                por_fila[clave] = texto_problema_lote(p)
        for clave, fila in self._filas.items():
            fila.mostrar_error(por_fila.get(clave))
        self._actualizar_vista_previa()

    def _actualizar_vista_previa(self) -> None:
        nombres = self.nombres_previstos()
        if not nombres or not self.es_lote:
            self._vista_previa.setText("")
            self._vista_previa.hide()
            return
        if len(nombres) <= 4:
            texto = ", ".join(nombres)
        else:
            texto = ", ".join(nombres[:3]) + " … " + nombres[-1]
        self._vista_previa.setText(
            QCoreApplication.translate("BloqueLote", "Se llamarán: {nombres}").format(nombres=texto)
        )
        self._vista_previa.show()

    @property
    def texto_vista_previa(self) -> str:
        return self._vista_previa.text()

    # --- Señales ----------------------------------------------------------------------

    def _tocar(self, clave: str) -> None:
        fila = self._filas[clave]
        if not fila.tocado:
            fila.marcar_tocado()
            self.cambiado.emit()

    def _al_editar(self, clave: str) -> None:
        if self._ocupado:
            return
        fila = self._filas.get(clave)
        if fila is not None:
            fila.marcar_tocado()
        if clave == "cantidad":
            # El resto de las filas (nombres, destino) aparecen o se ocultan según la cantidad.
            for f in self._filas.values():
                if f is not self._filas["cantidad"]:
                    f.marcar_tocado()
            self._aplicar_visibilidad()
        self.cambiado.emit()

    def _al_cambiar_destino(self, _marcado: bool) -> None:
        if self._ocupado:
            return
        self._aplicar_visibilidad()
        self.destino_cambiado.emit()
        self.cambiado.emit()

    def _al_cambiar_nodo(self, _i: int) -> None:
        if self._ocupado:
            return
        if self._radio_un_nodo.isChecked():
            self.destino_cambiado.emit()
        self.cambiado.emit()

    def bloquear(self, bloqueado: bool) -> None:
        """Bloquea el bloque mientras el lote se ejecuta (CA-L10.9)."""
        self.setEnabled(not bloqueado)
