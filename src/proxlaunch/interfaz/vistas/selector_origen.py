"""Selector «¿Cómo quieres crear la máquina?» (RF-O01, RF-O02, RF-O13, RF-O14, RF-O20, RF-O22).

Presenta los cuatro orígenes (vacía, instalar desde ISO, usar un disco existente y copiar una
plantilla de Proxmox). Un origen no disponible aparece **deshabilitado con el motivo escrito
debajo** —nunca oculto— y, si falta el almacenamiento «Import», con la ruta exacta en Proxmox para
pedírselo al administrador. Según el origen muestra la fuente (con el catálogo), el sistema
operativo con la lista de cambios que aplicará el asistente (antes → después), los drivers
virtio-win de Windows y las opciones de la copia.

No hace E/S: pide los datos con señales y los recibe con ``establecer_*``. El catálogo se abre en un
diálogo propio (``DialogoCatalogo``); las subidas y descargas las abre quien enlaza las señales.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.dialogos.capacidades import DialogoCapacidades
from proxlaunch.interfaz.dialogos.catalogo import DialogoCatalogo, FuenteCatalogo
from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.modelos_tabla_origen import (
    FilaPlantilla,
    FilaVolumen,
    texto_explicacion_via,
)
from proxlaunch.interfaz.textos import texto_cambio_asistente, texto_modo_clon, texto_tipo_so
from proxlaunch.interfaz.vistas.campos import etiqueta, poner_mensaje, poner_propiedad
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import (
    Contenido,
    DetallePlantilla,
    PermisosEfectivos,
    Plantilla,
    Volumen,
)
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    RefPlantilla,
    RefVolumen,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.origen.asistente import CambioAsistente
from proxlaunch.nucleo.origen.capacidades_origen import (
    CapacidadesOrigen,
    Disponibilidad,
    EstadoVia,
    Via,
    vias_de_origen,
)
from proxlaunch.nucleo.origen.nombres import es_virtio_win

# Orden de las opciones del selector y vía que cada una necesita.
_ORIGENES: tuple[OrigenSO, ...] = (
    OrigenSO.DISCO_VACIO,
    OrigenSO.ISO,
    OrigenSO.IMPORTAR_DISCO,
    OrigenSO.CLONAR_PLANTILLA,
)
_TIPOS_WINDOWS = frozenset(
    {
        TipoSO.WINDOWS_11,
        TipoSO.WINDOWS_SERVER_2022_2025,
        TipoSO.WINDOWS_10,
        TipoSO.WINDOWS_SERVER_2016_2019,
    }
)


@dataclass(frozen=True)
class PeticionFuente:
    """Lo que el selector pide al controlador.

    - ``fuente``: qué se está eligiendo (ISO, drivers virtio-win, imagen de disco o plantilla).
    - ``padre``: widget que debe ser el padre del diálogo que se abra (el diálogo del catálogo si
      la petición viene de él, o la ventana que contiene el selector).
    """

    fuente: FuenteCatalogo
    padre: QWidget


def texto_opcion_origen(origen: OrigenSO) -> str:
    """Texto llano de cada origen (CA-O01 «¿Cómo quieres crear la máquina?»)."""
    return {
        OrigenSO.DISCO_VACIO: QCoreApplication.translate(
            "SelectorOrigen", "Vacía, sin sistema operativo"
        ),
        OrigenSO.ISO: QCoreApplication.translate("SelectorOrigen", "Instalar desde un archivo ISO"),
        OrigenSO.IMPORTAR_DISCO: QCoreApplication.translate(
            "SelectorOrigen", "Usar un disco existente (qcow2, vmdk, raw)"
        ),
        OrigenSO.CLONAR_PLANTILLA: QCoreApplication.translate(
            "SelectorOrigen", "Copiar una plantilla de Proxmox"
        ),
    }[origen]


class SelectorOrigen(QWidget):
    """Elige cómo se crea la máquina y qué fuente usa.

    Señales:
    - ``origen_cambiado(object)``: ``OrigenSO`` tras cambiar de opción.
    - ``pedir_catalogo(object)``: ``FuenteCatalogo``; hay que (re)leer ese catálogo y entregarlo
      con ``establecer_catalogo``.
    - ``pedir_subida(object)`` / ``pedir_descarga(object)``: ``PeticionFuente``; abrir el diálogo
      de transferencia para ``fuente.contenido`` con ``padre`` como padre.
    - ``seleccion_cambiada()``: cambió la fuente, el SO, el modo o un ajuste (el resumen debe
      regenerarse).
    """

    origen_cambiado = Signal(object)
    pedir_catalogo = Signal(object)
    pedir_subida = Signal(object)
    pedir_descarga = Signal(object)
    seleccion_cambiada = Signal()
    # El asistente de SO debe aplicarse UNA vez al formulario: (tipo_so, solo_bus). ``solo_bus``
    # = solo cambió «Disco compatible (SATA)» y basta con reescribir el bus del primer disco.
    asistente_solicitado = Signal(object, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._avanzado = False
        self._bloqueado = False
        self._tema = "oscuro"
        self._caps: CapacidadesOrigen | None = None
        self._origen = OrigenSO.DISCO_VACIO
        self._cambios: tuple[CambioAsistente, ...] = ()
        # Se cargó una configuración sin pasar por el asistente: no se sabe qué cambió.
        self._cambios_desconocidos = False
        # Catálogo recibido
        self._volumenes: tuple[Volumen, ...] = ()
        self._nodo_catalogo = ""
        self._errores: tuple[ErrorProxLaunch, ...] = ()
        self._plantillas: tuple[Plantilla, ...] | None = None
        self._permisos: PermisosEfectivos | None = None
        self._detalle_plantilla: DetallePlantilla | None = None
        self._virtio_descargable = False
        self._texto_administrador: str | None = None
        # Elecciones
        self._iso = RefVolumen()
        self._drivers: RefVolumen | None = None
        self._sin_drivers = False
        # Almacenamiento de destino pedido (lote guardado): se conserva aunque el combo aún no
        # tenga la lista del servidor o esté oculto (modo básico) y se reaplica al rellenarlo.
        self._storage_destino: str | None = None
        self._imagen = RefVolumen()
        self._plantilla = RefPlantilla()
        self._modo_efectivo: ModoClon | None = None
        self.dialogo_catalogo: DialogoCatalogo | None = None
        # Pregunta de CA-O01.3; se puede sustituir (pruebas) sin abrir una caja modal.
        self.confirmar_cambio: Callable[[str], bool] = self._confirmar_cambio_por_defecto

        self._construir()
        self.establecer_capacidades(None)
        self._mostrar_pagina()

    # ------------------------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------------------------

    def _construir(self) -> None:
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)

        titulo = QLabel(self.tr("¿Cómo quieres crear la máquina?"))
        fuente = titulo.font()
        fuente.setBold(True)
        titulo.setFont(fuente)
        titulo.setAccessibleName(self.tr("¿Cómo quieres crear la máquina?"))
        capa.addWidget(titulo)

        self.grupo_origen = QButtonGroup(self)
        self.opciones: dict[OrigenSO, QRadioButton] = {}
        self.motivos: dict[OrigenSO, QLabel] = {}
        for origen in _ORIGENES:
            radio = QRadioButton(texto_opcion_origen(origen))
            radio.setAccessibleName(texto_opcion_origen(origen))
            self.grupo_origen.addButton(radio)
            self.opciones[origen] = radio
            motivo = etiqueta("", secundario=True)
            motivo.setContentsMargins(24, 0, 0, 0)
            motivo.hide()
            self.motivos[origen] = motivo
            capa.addWidget(radio)
            capa.addWidget(motivo)
            radio.toggled.connect(lambda marcado, o=origen: self._al_marcar(o, marcado))
        self.opciones[OrigenSO.DISCO_VACIO].setChecked(True)

        self.boton_capacidades = QPushButton(self.tr("¿Por qué no puedo usar alguna opción?"))
        self.boton_capacidades.setFlat(True)
        self.boton_capacidades.setAutoDefault(False)
        self.boton_capacidades.setProperty("enlace", True)
        self.boton_capacidades.clicked.connect(self.abrir_capacidades)
        capa.addWidget(self.boton_capacidades, 0, Qt.AlignmentFlag.AlignLeft)

        # Una página por origen; solo se muestra la del origen marcado (así la altura se ajusta
        # al contenido y no al de la página más alta).
        self.paginas: dict[OrigenSO, QWidget] = {
            OrigenSO.DISCO_VACIO: self._pagina_vacia(),
            OrigenSO.ISO: self._pagina_iso(),
            OrigenSO.IMPORTAR_DISCO: self._pagina_importar(),
            OrigenSO.CLONAR_PLANTILLA: self._pagina_clonar(),
        }
        for pagina in self.paginas.values():
            capa.addWidget(pagina)

        self.grupo_so = self._grupo_so()
        capa.addWidget(self.grupo_so)
        self.grupo_drivers = self._grupo_drivers()
        capa.addWidget(self.grupo_drivers)
        capa.addStretch(1)

    def _pagina_vacia(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(24, 4, 0, 4)
        capa.addWidget(
            etiqueta(
                self.tr(
                    "La máquina se crea con un disco vacío y sin sistema operativo. "
                    "Instálalo después desde la consola de Proxmox."
                ),
                secundario=True,
            )
        )
        return pagina

    def _fila_fuente(
        self, texto_boton: str, nombre_accesible: str
    ) -> tuple[QWidget, QLabel, QPushButton]:
        """Fila «nombre elegido + botón» común a ISO, imagen y plantilla."""
        fila = QWidget()
        capa = QHBoxLayout(fila)
        capa.setContentsMargins(24, 4, 0, 4)
        valor = QLabel()
        valor.setTextFormat(Qt.TextFormat.PlainText)  # el nombre viene del servidor
        valor.setAccessibleName(nombre_accesible)
        valor.setWordWrap(True)
        boton = QPushButton(texto_boton)
        boton.setAutoDefault(False)
        capa.addWidget(valor, 1)
        capa.addWidget(boton)
        return fila, valor, boton

    def _pagina_iso(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(0, 0, 0, 0)
        fila, self.valor_iso, self.boton_elegir_iso = self._fila_fuente(
            self.tr("Elegir ISO…"), self.tr("Archivo ISO elegido")
        )
        self.boton_elegir_iso.clicked.connect(lambda: self._abrir_catalogo(FuenteCatalogo.ISO))
        capa.addWidget(fila)
        return pagina

    def _pagina_importar(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(0, 0, 0, 0)
        fila, self.valor_imagen, self.boton_elegir_imagen = self._fila_fuente(
            self.tr("Elegir disco…"), self.tr("Disco elegido")
        )
        self.boton_elegir_imagen.clicked.connect(
            lambda: self._abrir_catalogo(FuenteCatalogo.IMAGEN)
        )
        capa.addWidget(fila)
        ampliar = QWidget()
        capa_ampliar = QHBoxLayout(ampliar)
        capa_ampliar.setContentsMargins(24, 0, 0, 0)
        capa_ampliar.addWidget(QLabel(self.tr("Ampliar el disco a")))
        self.spin_ampliar = QSpinBox()
        self.spin_ampliar.setRange(0, 1_000_000)
        self.spin_ampliar.setSuffix(" GiB")
        self.spin_ampliar.setSpecialValueText(self.tr("Tamaño del disco importado"))
        self.spin_ampliar.setAccessibleName(self.tr("Ampliar el disco importado a (GiB)"))
        self.spin_ampliar.valueChanged.connect(lambda _v: self.seleccion_cambiada.emit())
        capa_ampliar.addWidget(self.spin_ampliar)
        capa_ampliar.addStretch(1)
        capa.addWidget(ampliar)
        return pagina

    def _pagina_clonar(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(0, 0, 0, 0)
        fila, self.valor_plantilla, self.boton_elegir_plantilla = self._fila_fuente(
            self.tr("Elegir plantilla…"), self.tr("Plantilla elegida")
        )
        self.boton_elegir_plantilla.clicked.connect(
            lambda: self._abrir_catalogo(FuenteCatalogo.PLANTILLA)
        )
        capa.addWidget(fila)

        # Tipo de copia: en básico solo la frase del modo automático; en avanzado, la lista.
        self.etiqueta_modo = etiqueta(
            self.tr(
                "Rápido y ligero (recomendado): la copia comparte el disco con la plantilla "
                "y se crea en segundos. Si el almacenamiento no lo permite, Proxmox hace una "
                "copia independiente."
            ),
            secundario=True,
        )
        self.etiqueta_modo.setContentsMargins(24, 0, 0, 0)
        capa.addWidget(self.etiqueta_modo)
        self.fila_modo = QWidget()
        capa_modo = QHBoxLayout(self.fila_modo)
        capa_modo.setContentsMargins(24, 0, 0, 0)
        capa_modo.addWidget(QLabel(self.tr("Tipo de copia")))
        self.combo_modo = QComboBox()
        self.combo_modo.setAccessibleName(self.tr("Tipo de copia"))
        for modo in ModoClon:
            self.combo_modo.addItem(texto_modo_clon(modo, avanzado=True), modo.value)
        self.combo_modo.currentIndexChanged.connect(self._al_cambiar_modo)
        capa_modo.addWidget(self.combo_modo, 1)
        capa.addWidget(self.fila_modo)
        self.etiqueta_modo_efectivo = etiqueta("", secundario=True)
        self.etiqueta_modo_efectivo.setContentsMargins(24, 0, 0, 0)
        self.etiqueta_modo_efectivo.hide()
        capa.addWidget(self.etiqueta_modo_efectivo)

        self.fila_storage_destino = QWidget()
        capa_dest = QHBoxLayout(self.fila_storage_destino)
        capa_dest.setContentsMargins(24, 0, 0, 0)
        capa_dest.addWidget(QLabel(self.tr("Guardar la copia en")))
        self.combo_storage_destino = QComboBox()
        self.combo_storage_destino.setAccessibleName(self.tr("Almacenamiento de la copia"))
        self.combo_storage_destino.addItem(self.tr("El de la plantilla"), None)
        self.combo_storage_destino.currentIndexChanged.connect(self._al_cambiar_storage_destino)
        capa_dest.addWidget(self.combo_storage_destino, 1)
        capa.addWidget(self.fila_storage_destino)

        # Ajustes opcionales: 0 / vacío = «igual que la plantilla» (CA-O22.1).
        self.grupo_ajustes = QGroupBox(self.tr("Ajustes de la copia (opcional)"))
        capa_ajustes = QVBoxLayout(self.grupo_ajustes)
        self.spin_sockets = self._spin_ajuste(self.tr("Procesadores (sockets)"), 64)
        self.spin_cores = self._spin_ajuste(self.tr("Núcleos"), 1024)
        self.spin_memoria = self._spin_ajuste(self.tr("Memoria (MiB)"), 16_000_000)
        self.spin_disco = self._spin_ajuste(self.tr("Disco principal (GiB)"), 1_000_000)
        self.campo_tipo_cpu = QLineEdit()
        self.campo_tipo_cpu.setPlaceholderText(self.tr("Igual que la plantilla"))
        self.campo_tipo_cpu.setAccessibleName(self.tr("Tipo de CPU"))
        self.campo_tipo_cpu.textChanged.connect(lambda _t: self.seleccion_cambiada.emit())
        self._filas_ajuste: dict[str, QWidget] = {}
        for clave, texto, widget in (
            ("sockets", self.tr("Procesadores (sockets)"), self.spin_sockets),
            ("cores", self.tr("Núcleos"), self.spin_cores),
            ("tipo_cpu", self.tr("Tipo de CPU"), self.campo_tipo_cpu),
            ("memoria", self.tr("Memoria (MiB)"), self.spin_memoria),
            ("disco", self.tr("Disco principal (GiB)"), self.spin_disco),
        ):
            fila_aj = QWidget()
            capa_fila = QHBoxLayout(fila_aj)
            capa_fila.setContentsMargins(0, 0, 0, 0)
            capa_fila.addWidget(QLabel(texto), 1)
            capa_fila.addWidget(widget, 1)
            self._filas_ajuste[clave] = fila_aj
            capa_ajustes.addWidget(fila_aj)
        capa.addWidget(self.grupo_ajustes)
        return pagina

    def _spin_ajuste(self, nombre: str, maximo: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, maximo)
        spin.setSpecialValueText(self.tr("Igual que la plantilla"))
        spin.setAccessibleName(nombre)
        spin.valueChanged.connect(lambda _v: self.seleccion_cambiada.emit())
        return spin

    def _grupo_so(self) -> QGroupBox:
        grupo = QGroupBox(self.tr("Sistema operativo"))
        capa = QVBoxLayout(grupo)
        self.combo_so = QComboBox()
        self.combo_so.setAccessibleName(self.tr("Sistema operativo que vas a instalar"))
        self.combo_so.addItem(self.tr("Elige el sistema operativo…"), None)
        for tipo in TipoSO:
            self.combo_so.addItem(texto_tipo_so(tipo), tipo.value)
        self.combo_so.currentIndexChanged.connect(self._al_cambiar_so)
        capa.addWidget(self.combo_so)

        self.casilla_disco_compatible = QCheckBox(
            self.tr("Disco compatible (SATA): no hace falta cargar un controlador al instalar")
        )
        self.casilla_disco_compatible.setAccessibleName(self.tr("Disco compatible (SATA)"))
        self.casilla_disco_compatible.toggled.connect(self._al_cambiar_disco_compatible)
        capa.addWidget(self.casilla_disco_compatible)

        self.titulo_cambios = etiqueta("", secundario=True)
        capa.addWidget(self.titulo_cambios)
        # Una sola etiqueta con todas las líneas: no se crean ni destruyen widgets al regenerar la
        # lista, así que no quedan restos encimados (defecto de repintado).
        self.contenedor_cambios = QWidget()
        capa_cambios = QVBoxLayout(self.contenedor_cambios)
        capa_cambios.setContentsMargins(12, 0, 0, 0)
        self.lista_cambios = etiqueta("")
        capa_cambios.addWidget(self.lista_cambios)
        self.contenedor_cambios.hide()
        capa.addWidget(self.contenedor_cambios)
        return grupo

    def _grupo_drivers(self) -> QGroupBox:
        grupo = QGroupBox(self.tr("Drivers de Windows (virtio-win)"))
        capa = QVBoxLayout(grupo)
        self.etiqueta_drivers = etiqueta("")
        self.etiqueta_drivers.setAccessibleName(self.tr("Drivers virtio-win elegidos"))
        capa.addWidget(self.etiqueta_drivers)
        fila = QHBoxLayout()
        self.boton_elegir_drivers = QPushButton(self.tr("Elegir otro ISO de drivers…"))
        self.boton_elegir_drivers.setAutoDefault(False)
        self.boton_elegir_drivers.clicked.connect(
            lambda: self._abrir_catalogo(FuenteCatalogo.DRIVERS)
        )
        self.boton_descargar_drivers = QPushButton(self.tr("Descargarlo en el servidor"))
        self.boton_descargar_drivers.setAutoDefault(False)
        self.boton_descargar_drivers.clicked.connect(
            lambda: self.pedir_descarga.emit(PeticionFuente(FuenteCatalogo.DRIVERS, self.window()))
        )
        self.boton_subir_drivers = QPushButton(self.tr("Ya lo tengo en mi equipo"))
        self.boton_subir_drivers.setAutoDefault(False)
        self.boton_subir_drivers.clicked.connect(
            lambda: self.pedir_subida.emit(PeticionFuente(FuenteCatalogo.DRIVERS, self.window()))
        )
        fila.addWidget(self.boton_elegir_drivers)
        fila.addWidget(self.boton_descargar_drivers)
        fila.addWidget(self.boton_subir_drivers)
        fila.addStretch(1)
        capa.addLayout(fila)
        self.casilla_sin_drivers = QCheckBox(self.tr("Crear sin los drivers"))
        self.casilla_sin_drivers.setAccessibleName(self.tr("Crear sin los drivers"))
        self.casilla_sin_drivers.toggled.connect(self._al_cambiar_sin_drivers)
        capa.addWidget(self.casilla_sin_drivers)
        self.aviso_sin_drivers = etiqueta(
            self.tr("Sin los drivers, Windows no verá el disco VirtIO ni la red.")
        )
        self.aviso_sin_drivers.setProperty("aviso", True)
        self.aviso_sin_drivers.hide()
        capa.addWidget(self.aviso_sin_drivers)
        return grupo

    # ------------------------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------------------------

    @property
    def origen(self) -> OrigenSO:
        """Origen marcado ahora."""
        return self._origen

    @property
    def tipo_so(self) -> TipoSO | None:
        """Sistema operativo elegido (``None`` = sin elegir)."""
        dato = self.combo_so.currentData()
        try:
            return TipoSO(dato) if dato else None
        except ValueError:
            return None

    @property
    def cambios_asistente(self) -> tuple[CambioAsistente, ...]:
        """Cambios que el asistente aplicará con la elección actual (los que se ven en pantalla)."""
        return self._cambios

    @property
    def modo_clon(self) -> ModoClon:
        """Modo de copia: el del selector (en básico no se puede cambiar y queda ``AUTOMATICO``
        salvo que se haya cargado otro desde un lote guardado)."""
        try:
            return ModoClon(self.combo_modo.currentData())
        except ValueError:
            return ModoClon.AUTOMATICO

    def establecer_tema(self, tema: str) -> None:
        """Tema (``"claro"``/``"oscuro"``) para los diálogos que abre el selector."""
        self._tema = tema
        if self.dialogo_catalogo is not None:
            self.dialogo_catalogo.establecer_tema(tema)

    def establecer_modo(self, avanzado: bool) -> None:
        """Modo básico o avanzado (D-14): muestra u oculta lo técnico."""
        self._avanzado = avanzado
        self.fila_modo.setVisible(avanzado)
        self.etiqueta_modo.setVisible(not avanzado)
        for clave in ("sockets", "tipo_cpu"):
            self._filas_ajuste[clave].setVisible(avanzado)
        self.casilla_disco_compatible.setVisible(avanzado)
        self._actualizar_visibilidad()
        self.seleccion_cambiada.emit()

    def establecer_bloqueado(self, bloqueado: bool) -> None:
        """Deshabilita todo mientras corre un lote (CA-O01.7)."""
        self._bloqueado = bloqueado
        self.setEnabled(not bloqueado)

    def establecer_capacidades(self, caps: CapacidadesOrigen | None) -> None:
        """Habilita cada origen según sus vías y escribe el motivo de los que no se pueden usar.

        ``None`` (sin servidor) deja solo «Vacía». Si el origen marcado deja de estar disponible
        se vuelve a «Vacía».
        """
        self._caps = caps
        for origen in _ORIGENES:
            radio = self.opciones[origen]
            motivo = self.motivos[origen]
            disponible, texto, aviso = self._disponibilidad_origen(origen)
            radio.setEnabled(disponible)
            if texto:
                poner_mensaje(motivo, texto, aviso=aviso)
                if not aviso:
                    poner_propiedad(motivo, "error", False)  # es una explicación, no un fallo
                    motivo.setProperty("secundario", True)
            else:
                poner_mensaje(motivo, None)
            radio.setAccessibleDescription(texto)
        if not self.opciones[self._origen].isEnabled():
            self.opciones[OrigenSO.DISCO_VACIO].setChecked(True)
        self._actualizar_vias_dialogo()
        self._actualizar_drivers()

    def establecer_catalogo(
        self,
        volumenes: Sequence[Volumen],
        plantillas: Sequence[Plantilla] | None,
        *,
        nodo: str | None = None,
        errores: Sequence[ErrorProxLaunch] = (),
        permisos: PermisosEfectivos | None = None,
    ) -> None:
        """Recibe el catálogo (ISOs, imágenes y plantillas) y lo reparte a lo que esté abierto.

        ``plantillas=None`` = aún no leídas. ``nodo`` es el nodo de los volúmenes; ``errores`` los
        E-O05 por storage; ``permisos`` sirve para deshabilitar plantillas sin ``VM.Clone``.
        """
        self._volumenes = tuple(volumenes)
        self._plantillas = None if plantillas is None else tuple(plantillas)
        self._nodo_catalogo = nodo or ""
        self._errores = tuple(errores)
        self._permisos = permisos
        self._refrescar_dialogo()
        self._actualizar_drivers()

    def establecer_detalle_plantilla(self, detalle: DetallePlantilla | None) -> None:
        """Valores de la plantilla elegida: se muestran como «Igual que la plantilla (valor)»."""
        self._detalle_plantilla = detalle
        pares: tuple[tuple[QSpinBox, int | None, str], ...] = (
            (self.spin_sockets, detalle.sockets if detalle else None, ""),
            (self.spin_cores, detalle.cores if detalle else None, ""),
            (self.spin_memoria, detalle.memoria_mib if detalle else None, ""),
            (self.spin_disco, None, ""),
        )
        for spin, valor, _ in pares:
            texto = self.tr("Igual que la plantilla")
            if valor is not None:
                texto = self.tr("Igual que la plantilla ({valor})").format(valor=valor)
            spin.setSpecialValueText(texto)
        cpu = detalle.tipo_cpu if detalle else None
        self.campo_tipo_cpu.setPlaceholderText(
            self.tr("Igual que la plantilla ({valor})").format(valor=cpu)
            if cpu
            else self.tr("Igual que la plantilla")
        )

    def establecer_modo_efectivo(self, modo: ModoClon | None) -> None:
        """Dice qué modo se aplicará de verdad con el automático (``ENLAZADO``/``COMPLETO``)."""
        self._modo_efectivo = modo
        if modo is None:
            poner_mensaje(self.etiqueta_modo_efectivo, None)
        elif modo == ModoClon.ENLAZADO:
            poner_mensaje(
                self.etiqueta_modo_efectivo,
                self.tr(
                    "Se hará una copia rápida y ligera. Las máquinas comparten el disco base con "
                    "la plantilla: no borres la plantilla mientras existan."
                ),
                aviso=True,
            )
        else:
            poner_mensaje(
                self.etiqueta_modo_efectivo,
                self.tr(
                    "Se hará una copia independiente: tarda más y ocupa el espacio completo "
                    "del disco."
                ),
                aviso=True,
            )

    def establecer_storages_destino(self, storages: Sequence[str]) -> None:
        """Almacenamientos posibles para una copia completa (solo avanzado)."""
        self.combo_storage_destino.blockSignals(True)
        self.combo_storage_destino.clear()
        self.combo_storage_destino.addItem(self.tr("El de la plantilla"), None)
        for s in storages:
            self.combo_storage_destino.addItem(s, s)
        indice = self.combo_storage_destino.findData(self._storage_destino)
        self.combo_storage_destino.setCurrentIndex(max(0, indice))
        self.combo_storage_destino.blockSignals(False)

    def establecer_virtio_descargable(self, descargable: bool) -> None:
        """Hay URL fija verificada de virtio-win (si no, esa vía no se ofrece, DT-O10)."""
        self._virtio_descargable = descargable
        self._actualizar_drivers()

    def establecer_texto_administrador(self, texto: str | None) -> None:
        """Texto general «Qué pedirle a tu administrador» para el diálogo de capacidades."""
        self._texto_administrador = texto

    def establecer_seleccion(
        self, fuente: FuenteCatalogo, elegido: Volumen | Plantilla, *, emitir: bool = True
    ) -> None:
        """Deja elegido un volumen o una plantilla (p. ej. el archivo recién subido)."""
        if isinstance(elegido, Plantilla):
            self._plantilla = RefPlantilla(elegido.nombre, elegido.vmid)
            self._actualizar_valores()
        else:
            ref = RefVolumen(elegido.nombre, elegido.volid)
            if fuente == FuenteCatalogo.IMAGEN:
                self._imagen = ref
            elif fuente == FuenteCatalogo.DRIVERS:
                self._drivers = ref
                self._sin_drivers = False
            else:
                self._iso = ref
            self._actualizar_valores()
        if self.dialogo_catalogo is not None and self.dialogo_catalogo.fuente == fuente:
            if isinstance(elegido, Plantilla):
                self.dialogo_catalogo.seleccionar_vmid(elegido.vmid)
            else:
                self.dialogo_catalogo.seleccionar_volid(elegido.volid)
        if emitir:
            self.seleccion_cambiada.emit()

    def seleccionar_volid(self, fuente: FuenteCatalogo, volid: str) -> bool:
        """Elige el volumen con ese volid del catálogo recibido; ``False`` si no está."""
        for v in self._volumenes:
            if v.volid == volid:
                self.establecer_seleccion(fuente, v)
                return True
        return False

    def abrir_capacidades(self) -> None:
        """Abre «Qué puedo hacer en este servidor» con las capacidades actuales."""
        dialogo = DialogoCapacidades(
            self._caps,
            self.window(),
            texto_administrador=self._texto_administrador,
            tema=self._tema,
        )
        dialogo.open()
        self.dialogo_capacidades = dialogo

    @property
    def disco_compatible(self) -> bool:
        """Casilla «Disco compatible (SATA)» marcada (solo cuenta con un SO Windows)."""
        return self.casilla_disco_compatible.isChecked()

    def establecer_cambios(self, cambios: Sequence[CambioAsistente]) -> None:
        """Lista de lo que el asistente cambió en el formulario (la calcula el formulario al
        aplicarlo una vez). Es lo que muestran el selector y el resumen."""
        self._cambios = tuple(cambios)
        self._cambios_desconocidos = False
        self._pintar_cambios()

    def aplicar(self, cfg: ConfiguracionVM) -> None:
        """Pone el selector como ``cfg`` (carga de un lote, perfil o formulario)."""
        det = cfg.detalle_origen
        self._iso = RefVolumen()
        self._drivers = None
        self._sin_drivers = False
        self._imagen = RefVolumen()
        self._plantilla = RefPlantilla()
        self.spin_ampliar.setValue(0)
        for spin in (self.spin_sockets, self.spin_cores, self.spin_memoria, self.spin_disco):
            spin.setValue(0)
        self.campo_tipo_cpu.clear()
        self._storage_destino = None
        self.combo_storage_destino.blockSignals(True)
        self.combo_storage_destino.setCurrentIndex(0)
        self.combo_storage_destino.blockSignals(False)
        if isinstance(det, DetalleIso):
            self._iso, self._drivers, self._sin_drivers = det.iso, det.drivers, det.sin_drivers
        elif isinstance(det, DetalleImportacion):
            self._imagen = det.imagen
            self.spin_ampliar.setValue(det.ampliar_a_gib or 0)
        elif isinstance(det, DetalleClon):
            self._plantilla = det.plantilla
            indice = self.combo_modo.findData(det.modo.value)
            self.combo_modo.setCurrentIndex(max(0, indice))
            a = det.ajustes
            self.spin_sockets.setValue(a.sockets or 0)
            self.spin_cores.setValue(a.cores or 0)
            self.spin_memoria.setValue(a.memoria_mib or 0)
            self.spin_disco.setValue(a.disco_gib or 0)
            self.campo_tipo_cpu.setText(a.tipo_cpu or "")
            self._storage_destino = det.storage_destino
            self.combo_storage_destino.blockSignals(True)
            indice_dest = self.combo_storage_destino.findData(det.storage_destino)
            self.combo_storage_destino.setCurrentIndex(max(0, indice_dest))
            self.combo_storage_destino.blockSignals(False)
        self.combo_so.blockSignals(True)
        self.combo_so.setCurrentIndex(
            max(0, self.combo_so.findData(cfg.tipo_so.value if cfg.tipo_so else None))
        )
        self.combo_so.blockSignals(False)
        self.casilla_sin_drivers.blockSignals(True)
        self.casilla_sin_drivers.setChecked(self._sin_drivers)
        self.casilla_sin_drivers.blockSignals(False)
        self.opciones[cfg.origen].blockSignals(True)
        self.opciones[cfg.origen].setChecked(True)
        self.opciones[cfg.origen].blockSignals(False)
        self._origen = cfg.origen
        self._mostrar_pagina()
        self._actualizar_valores()
        # La lista se rellena cuando el formulario aplica el asistente; al cargar sin él se oculta.
        self._cambios = ()
        self._cambios_desconocidos = True
        self._pintar_cambios()

    def completar(self, cfg: ConfiguracionVM) -> ConfiguracionVM:
        """Copia de ``cfg`` con el origen y su detalle. El asistente de SO NO se reaplica aquí: se
        aplicó una vez a los widgets del formulario y ``cfg`` ya trae lo que ellos muestran. Con
        ISO o disco importado solo se fija el tipo de SO elegido (CA-O13.8)."""
        nueva = copy.deepcopy(cfg)
        nueva.origen = self._origen
        if self._origen == OrigenSO.DISCO_VACIO:
            nueva.detalle_origen = None
            nueva.tipo_so, nueva.tpm, nueva.agente_qemu = None, False, False
            return nueva
        if self._origen == OrigenSO.ISO:
            nueva.detalle_origen = DetalleIso(
                iso=self._iso,
                drivers=None if self._sin_drivers else self._drivers,
                sin_drivers=self._sin_drivers,
            )
        elif self._origen == OrigenSO.IMPORTAR_DISCO:
            ampliar = self.spin_ampliar.value()
            nueva.detalle_origen = DetalleImportacion(
                imagen=self._imagen, ampliar_a_gib=ampliar or None
            )
        else:
            nueva.detalle_origen = self._detalle_clon()
            nueva.tipo_so, nueva.tpm, nueva.agente_qemu = None, False, False
            return nueva
        nueva.tipo_so = self.tipo_so
        return nueva

    # ------------------------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------------------------

    def _detalle_clon(self) -> DetalleClon:
        ajustes = AjustesClon(
            sockets=self.spin_sockets.value() or None,
            cores=self.spin_cores.value() or None,
            tipo_cpu=self.campo_tipo_cpu.text().strip() or None,
            memoria_mib=self.spin_memoria.value() or None,
            disco_gib=self.spin_disco.value() or None,
        )
        modo = self.modo_clon
        return DetalleClon(
            plantilla=self._plantilla,
            modo=modo,
            ajustes=ajustes,
            # En básico el combo está oculto, pero un destino cargado de un lote se conserva.
            storage_destino=self._storage_destino if modo == ModoClon.COMPLETO else None,
        )

    def _al_cambiar_storage_destino(self, _indice: int) -> None:
        self._storage_destino = self.combo_storage_destino.currentData()
        self.seleccion_cambiada.emit()

    def _via_de(self, origen: OrigenSO) -> EstadoVia | None:
        if self._caps is None:
            return None
        vias = vias_de_origen(origen)
        if not vias:
            return None
        return self._caps.vias.get(vias[0])

    def _disponibilidad_origen(self, origen: OrigenSO) -> tuple[bool, str, bool]:
        """``(habilitado, motivo, es_aviso)`` de un origen."""
        if origen == OrigenSO.DISCO_VACIO:
            return True, "", False
        if self._caps is None:
            return (
                False,
                self.tr("Conéctate a un servidor para ver si esta opción está disponible."),
                False,
            )
        estado = self._via_de(origen)
        if estado is None:
            return True, "", False
        if estado.disponibilidad == Disponibilidad.NO:
            return False, texto_explicacion_via(estado), False
        if estado.disponibilidad == Disponibilidad.CON_AVISO:
            return True, texto_explicacion_via(estado), True
        return True, "", False

    def _confirmar_cambio_por_defecto(self, que_se_pierde: str) -> bool:
        return confirmar(
            self.window(),
            self.tr("Cambiar la forma de crear la máquina"),
            self.tr("Si cambias, se pierde lo que elegiste: {que_se_pierde}.").format(
                que_se_pierde=que_se_pierde
            ),
            self.tr("Cambiar"),
            self.tr("Cancelar"),
        )

    def _eleccion_actual(self) -> str:
        """Descripción de la fuente ya elegida del origen actual (``""`` si no hay)."""
        if self._origen == OrigenSO.ISO:
            return self._iso.nombre
        if self._origen == OrigenSO.IMPORTAR_DISCO:
            return self._imagen.nombre
        if self._origen == OrigenSO.CLONAR_PLANTILLA:
            return self._plantilla.nombre
        return ""

    def _al_marcar(self, origen: OrigenSO, marcado: bool) -> None:
        if not marcado or origen == self._origen:
            return
        perdida = self._eleccion_actual()
        if perdida and not self.confirmar_cambio(perdida):
            # Se mantiene lo elegido: se vuelve a marcar el origen anterior sin avisar.
            for o, radio in self.opciones.items():
                radio.blockSignals(True)
                radio.setChecked(o == self._origen)
                radio.blockSignals(False)
            return
        self._origen = origen
        self._mostrar_pagina()
        self._pedir_asistente(solo_bus=False)
        self.origen_cambiado.emit(origen)
        self.seleccion_cambiada.emit()

    def _mostrar_pagina(self) -> None:
        for origen, pagina in self.paginas.items():
            pagina.setVisible(origen == self._origen)
        self._actualizar_visibilidad()
        self._actualizar_valores()

    def _actualizar_visibilidad(self) -> None:
        iso = self._origen == OrigenSO.ISO
        importar = self._origen == OrigenSO.IMPORTAR_DISCO
        clonar = self._origen == OrigenSO.CLONAR_PLANTILLA
        self.grupo_so.setVisible(iso or importar)
        windows = self.tipo_so in _TIPOS_WINDOWS
        self.casilla_disco_compatible.setVisible(self._avanzado and windows)
        self.grupo_drivers.setVisible(iso and windows)
        self.fila_modo.setVisible(clonar and self._avanzado)
        self.etiqueta_modo.setVisible(clonar and not self._avanzado)
        self.fila_storage_destino.setVisible(
            clonar and self._avanzado and self.modo_clon == ModoClon.COMPLETO
        )
        self.grupo_ajustes.setVisible(clonar)

    def _actualizar_valores(self) -> None:
        """Refresca las etiquetas con lo elegido."""
        self.valor_iso.setText(self._iso.nombre or self.tr("Ningún archivo ISO elegido"))
        self.valor_imagen.setText(self._imagen.nombre or self.tr("Ningún disco elegido"))
        if self._plantilla.nombre:
            texto = self._plantilla.nombre
            if self._plantilla.vmid is not None:
                texto += f" (VMID {self._plantilla.vmid})"
            self.valor_plantilla.setText(texto)
        else:
            self.valor_plantilla.setText(self.tr("Ninguna plantilla elegida"))
        self._actualizar_drivers()

    def _al_cambiar_so(self, *_args: object) -> None:
        """Otro sistema operativo: el asistente se aplica una vez al formulario."""
        if self.tipo_so not in _TIPOS_WINDOWS:
            # Sin drivers que usar: no se conserva el CD de drivers de un SO anterior.
            self._drivers = None
            self._sin_drivers = False
            self.casilla_sin_drivers.blockSignals(True)
            self.casilla_sin_drivers.setChecked(False)
            self.casilla_sin_drivers.blockSignals(False)
            self.aviso_sin_drivers.hide()
        self._actualizar_visibilidad()
        self._actualizar_drivers()
        self._pedir_asistente(solo_bus=False)
        self.seleccion_cambiada.emit()

    def _al_cambiar_disco_compatible(self, *_args: object) -> None:
        """Solo cambia el bus del primer disco; el resto de lo que dejó el usuario se respeta."""
        self._actualizar_visibilidad()
        self._actualizar_drivers()
        self._pedir_asistente(solo_bus=True)
        self.seleccion_cambiada.emit()

    def _pedir_asistente(self, *, solo_bus: bool) -> None:
        """Pide al formulario aplicar el asistente (SO elegido con ISO o disco importado)."""
        tipo = self.tipo_so
        if tipo is None or self._origen not in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO):
            self._cambios = ()
            self._cambios_desconocidos = False
            self._pintar_cambios()
            return
        self.asistente_solicitado.emit(tipo, solo_bus)

    def _al_cambiar_modo(self, _indice: int) -> None:
        self._actualizar_visibilidad()
        self.seleccion_cambiada.emit()

    def _al_cambiar_sin_drivers(self, marcado: bool) -> None:
        self._sin_drivers = marcado
        self.aviso_sin_drivers.setVisible(marcado)
        self._actualizar_drivers()
        self.seleccion_cambiada.emit()

    def _drivers_detectado(self) -> Volumen | None:
        """ISO de virtio-win ya presente en el servidor (el último por nombre, CA-O14.1)."""
        candidatos = [
            v for v in self._volumenes if v.contenido == Contenido.ISO and es_virtio_win(v.nombre)
        ]
        return max(candidatos, key=lambda v: v.nombre.casefold(), default=None)

    def _actualizar_drivers(self) -> None:
        """Texto de los drivers y botones de los tres caminos (RF-O14)."""
        if self._sin_drivers:
            texto = self.tr("La máquina se creará sin el CD de drivers.")
        elif self._drivers is not None and self._drivers.nombre:
            texto = self.tr("Se usará el CD de drivers «{nombre}».").format(
                nombre=self._drivers.nombre
            )
        else:
            detectado = self._drivers_detectado()
            if detectado is not None:
                texto = self.tr(
                    "Se usará el CD de drivers «{nombre}», que ya está en el servidor."
                ).format(nombre=detectado.nombre)
            else:
                texto = self.tr(
                    "No hay ningún ISO de virtio-win en el servidor. Elige cómo conseguirlo."
                )
        self.etiqueta_drivers.setText(texto)
        es_ofrecida = self._via_ofrecida
        self.boton_descargar_drivers.setVisible(self._virtio_descargable)
        self.boton_descargar_drivers.setEnabled(es_ofrecida(Via.DESCARGAR_URL))
        self.boton_subir_drivers.setEnabled(es_ofrecida(Via.SUBIR_ISO))
        self.boton_elegir_drivers.setEnabled(not self._sin_drivers)

    def _via_ofrecida(self, via: Via) -> bool:
        return self._caps is not None and self._caps.disponible(via)

    def _pintar_cambios(self) -> None:
        """Muestra la lista de cambios del asistente para el SO elegido (antes → después)."""
        tipo = self.tipo_so
        activo = tipo is not None and self._origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO)
        if not activo or tipo is None or self._cambios_desconocidos:
            self.titulo_cambios.setText("")
            self.titulo_cambios.hide()
            self.contenedor_cambios.hide()
            return
        self.titulo_cambios.show()
        if self._cambios:
            self.titulo_cambios.setText(
                self.tr("Para {so} el asistente va a cambiar:").format(so=texto_tipo_so(tipo))
            )
            self.lista_cambios.setText(
                "\n".join(f"• {texto_cambio_asistente(c)}" for c in self._cambios)
            )
            self.contenedor_cambios.show()
        else:
            self.titulo_cambios.setText(
                self.tr("Para {so} no hace falta cambiar nada más.").format(so=texto_tipo_so(tipo))
            )
            self.lista_cambios.setText("")
            self.contenedor_cambios.hide()
        self.contenedor_cambios.updateGeometry()

    # --- Catálogo -----------------------------------------------------------------------

    def _abrir_catalogo(self, fuente: FuenteCatalogo) -> None:
        """Abre el catálogo de la fuente y pide al controlador que lo lea."""
        estado_subir = self._estado_subida(fuente)
        estado_descargar = self._estado_descarga(fuente)
        dialogo = DialogoCatalogo(
            fuente,
            self.window(),
            estado_subir=estado_subir,
            estado_descargar=estado_descargar,
            tema=self._tema,
        )
        dialogo.elegido.connect(lambda fila: self._al_elegir(fuente, fila))
        dialogo.subir_solicitado.connect(
            lambda: self.pedir_subida.emit(PeticionFuente(fuente, dialogo))
        )
        dialogo.descargar_solicitado.connect(
            lambda: self.pedir_descarga.emit(PeticionFuente(fuente, dialogo))
        )
        dialogo.actualizar_solicitado.connect(lambda: self._pedir(fuente, dialogo))
        dialogo.finished.connect(lambda _r: self._al_cerrar_catalogo(dialogo))
        self.dialogo_catalogo = dialogo
        self._refrescar_dialogo()
        dialogo.open()
        self.pedir_catalogo.emit(fuente)

    def _pedir(self, fuente: FuenteCatalogo, dialogo: DialogoCatalogo) -> None:
        dialogo.establecer_cargando(True)
        self.pedir_catalogo.emit(fuente)

    def _al_cerrar_catalogo(self, dialogo: DialogoCatalogo) -> None:
        if self.dialogo_catalogo is dialogo:
            self.dialogo_catalogo = None

    def _estado_subida(self, fuente: FuenteCatalogo) -> EstadoVia | None:
        if self._caps is None:
            return None
        via = Via.SUBIR_IMAGEN if fuente == FuenteCatalogo.IMAGEN else Via.SUBIR_ISO
        return self._caps.vias.get(via)

    def _estado_descarga(self, fuente: FuenteCatalogo) -> EstadoVia | None:
        if self._caps is None:
            return None
        via = Via.DESCARGAR_IMAGEN if fuente == FuenteCatalogo.IMAGEN else Via.DESCARGAR_URL
        return self._caps.vias.get(via)

    def _actualizar_vias_dialogo(self) -> None:
        dialogo = self.dialogo_catalogo
        if dialogo is not None:
            dialogo.actualizar_vias(
                self._estado_subida(dialogo.fuente), self._estado_descarga(dialogo.fuente)
            )

    def _refrescar_dialogo(self) -> None:
        """Entrega al diálogo abierto (si lo hay) el catálogo que tiene el selector."""
        dialogo = self.dialogo_catalogo
        if dialogo is None:
            return
        if dialogo.fuente == FuenteCatalogo.PLANTILLA:
            dialogo.establecer_plantillas(self._plantillas, self._permisos)
        else:
            dialogo.establecer_volumenes(
                self._volumenes, nodo=self._nodo_catalogo, errores=self._errores
            )

    def _al_elegir(self, fuente: FuenteCatalogo, fila: object) -> None:
        if isinstance(fila, FilaVolumen):
            self.establecer_seleccion(fuente, fila.volumen)
        elif isinstance(fila, FilaPlantilla):
            self.establecer_seleccion(fuente, fila.plantilla)
