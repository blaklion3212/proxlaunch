"""Bloque «Lote» del formulario: cantidad, nombres, destino y opciones (RF-L01 a RF-L05, RF-L22).

Con cantidad 1 solo se ve la cantidad y el formulario funciona como en el MVP 1. Con más de
una máquina aparecen el prefijo, la vista previa de los nombres y el destino; el modo
avanzado añade separador, número inicial, relleno, VMID inicial, nodos elegidos, algoritmo
y etiquetas. Los errores V-L salen junto a su campo.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QCoreApplication, Signal
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

from proxlaunch.interfaz.textos import texto_problema_lote
from proxlaunch.interfaz.vistas.campos import FilaCampo, boton_ayuda, etiqueta
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
        self.fila_algoritmo.layout().addWidget(self._boton_por_turnos, 0, 3)
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
        return self.cantidad_valor() > 1

    def establecer_cantidad(self, n: int) -> None:
        """Cambia la cantidad por código (por ejemplo «Reducir a N»)."""
        self.cantidad.setText(str(n))
        self._aplicar_visibilidad()
        self.cambiado.emit()

    def cantidad_valor(self) -> int:
        """Cantidad escrita; 0 si el texto no es un número (V-L01 lo rechaza)."""
        t = self.cantidad.text().strip()
        try:
            return int(t)
        except ValueError:
            return 0

    def _aplicar_visibilidad(self) -> None:
        lote = self.es_lote or self.cantidad_valor() > MAX_LOTE
        cluster = self._inv is not None and self._inv.topologia.es_cluster
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
        else:
            self.fila_algoritmo.setVisible(self._avanzado and not self._radio_un_nodo.isChecked())
            self._nodos_elegidos.setVisible(self._avanzado and self._radio_elegidos.isChecked())
        self._radio_elegidos.setVisible(lote and cluster and self._avanzado)
        self.combo_nodo.setEnabled(self._radio_un_nodo.isChecked())
        self._actualizar_vista_previa()

    def establecer_inventario(self, inv: Inventario) -> None:
        """Carga los nodos del servidor; conserva la elección si el nodo sigue existiendo."""
        self._inv = inv
        self._ocupado = True
        try:
            previo = self.combo_nodo.currentData()
            marcados = {n for n, c in self._checks_nodos.items() if c.isChecked()}
            self.combo_nodo.clear()
            while self._capa_nodos.count():
                item = self._capa_nodos.takeAt(0)
                if item is not None and item.widget() is not None:
                    item.widget().deleteLater()
            self._checks_nodos = {}
            sin_conexion = QCoreApplication.translate("BloqueLote", "Sin conexión")
            for n in inv.topologia.nodos:
                texto = n.nombre if n.en_linea else f"{n.nombre} — {sin_conexion}"
                self.combo_nodo.addItem(texto, n.nombre)
                check = QCheckBox(texto)
                check.setEnabled(n.en_linea)
                check.setChecked(n.en_linea and (not marcados or n.nombre in marcados))
                check.toggled.connect(lambda _c: self._al_editar("destino"))
                self._capa_nodos.addWidget(check)
                self._checks_nodos[n.nombre] = check
                if not n.en_linea:
                    modelo = self.combo_nodo.model()
                    modelo.item(self.combo_nodo.count() - 1).setEnabled(False)
            idx = self.combo_nodo.findData(previo) if previo else -1
            if idx < 0:
                idx = next((i for i, n in enumerate(inv.topologia.nodos) if n.en_linea), -1)
            self.combo_nodo.setCurrentIndex(idx)
        finally:
            self._ocupado = False
        self._aplicar_visibilidad()

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
        if self._radio_elegidos.isChecked() and self._avanzado:
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
        """Lote que describe el bloque con la configuración del formulario como plantilla."""
        texto_vmid = self.vmid_inicial.text().strip()
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
