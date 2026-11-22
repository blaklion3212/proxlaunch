"""Asistente «Crear plantilla desde imagen cloud» (B2, RF-B2.1 a RF-B2.11).

Convierte una imagen cloud (qcow2, img, raw o vmdk) en una plantilla lista para clonar, en cinco
pasos que se pueden reanudar: 1) la imagen en el almacenamiento «import», 2) crear la máquina e
importar el disco, 3) ampliar el disco, 4) valores de cloud-init (opcional, sin contraseña) y
5) convertir en plantilla (irreversible).

Toda la E/S corre en el ``Lanzador`` (``ServicioPlantillaImagen`` es del núcleo y no sabe de Qt):
el estado llega por copias y el progreso de la transferencia, acotado a 10 veces por segundo.
El asistente NUNCA borra nada por sí solo: «Borrar la máquina a medio crear» solo se ofrece si
``condiciones_borrado`` confirma TODAS las condiciones de RF-B2.10 y exige un diálogo de
confirmación con el nombre y el número. Si no hay certeza de que la máquina sea suya, se explica
y se pide borrarla desde Proxmox. No existe ningún campo de contraseña (PB-1).
"""

from __future__ import annotations

import dataclasses
import re
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.archivos_ui import carpeta_inicial
from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.modelos_tabla_origen import formatear_bytes, texto_tiempo
from proxlaunch.interfaz.textos import (
    texto_error,
    texto_motivo_checksum,
    texto_motivo_url,
    texto_problema,
    texto_progreso_transferencia,
)
from proxlaunch.interfaz.textos_b import (
    ayuda_b2,
    es_error,
    simbolo_estado_paso_b2,
    texto_accion_omitir,
    texto_accion_reintentar,
    texto_aviso_b,
    texto_borrado_no_ofrecido,
    texto_cerrar_en_curso_b2,
    texto_clave_privada_rechazada,
    texto_confirmacion_b2,
    texto_confirmar_borrado,
    texto_ejemplos_urls_b2,
    texto_estado_control_b2,
    texto_estado_paso_b2,
    texto_intro_b2,
    texto_irreversible_b2,
    texto_nombre_paso_b2,
    texto_problema_b2,
    texto_problema_clave,
    texto_problema_completo,
    texto_que_queda_tras_fallo,
    texto_resultado_b2,
    texto_resultado_b2_sin_plantilla,
    titulo_asistente_b2,
)
from proxlaunch.interfaz.trabajadores import Lanzador, Trabajador, leer_listados
from proxlaunch.interfaz.vistas.campos import poner_mensaje, poner_propiedad
from proxlaunch.interfaz.vistas.detalles_tecnicos import DetallesTecnicos, texto_detalles
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.cloudinit.claves import (
    analizar_claves,
    contiene_clave_privada,
    leer_archivo_pub,
)
from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit, ModoTarjeta, TarjetaCloudInit
from proxlaunch.nucleo.cloudinit.red import normalizar_dns
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido, Volumen
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage
from proxlaunch.nucleo.modelos.vm import (
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
    ModeloRed,
)
from proxlaunch.nucleo.origen.storages import candidatos
from proxlaunch.nucleo.plantilla_imagen import (
    AccionExistente,
    CondicionesBorrado,
    ControlB2,
    DisponibilidadB2,
    EstadoPaso,
    EstadoPlantillaImagen,
    FijasPlantilla,
    InspeccionImagen,
    OrigenImagen,
    PasoB2,
    ServicioPlantillaImagen,
    SolicitudPlantillaImagen,
    disponibilidad_plantilla_imagen,
    hay_errores,
    inspeccionar_imagen,
    nombre_para_url,
    nombre_sugerido,
    validar_solicitud,
)
from proxlaunch.nucleo.plantilla_imagen.modelos import (
    AVISO_CONSOLA_SERIE,
    AVISO_SIN_AGENTE_IMAGEN,
    AVISO_SOLO_CLON_COMPLETO,
)
from proxlaunch.nucleo.plantilla_imagen.peticion import TAMANO_FINAL_POR_DEFECTO_GIB
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.transferencias.modelos import (
    ComprobacionPrevia,
    DestinoTransferencia,
    Progreso,
)
from proxlaunch.nucleo.transferencias.servicio import ServicioTransferencias
from proxlaunch.nucleo.transferencias.url import (
    ChecksumTransferencia,
    UrlDescarga,
    validar_checksum,
    validar_url,
)
from proxlaunch.nucleo.validacion import Problema, Severidad

# Cómo de seguido la interfaz toma el último progreso de la transferencia (10 veces por segundo).
INTERVALO_PROGRESO_MS = 100
# Espera tras el último cambio del formulario antes de volver a validar (lee la cabecera del
# archivo local, así que no se hace en cada pulsación de tecla).
INTERVALO_VALIDACION_MS = 250
_ESCALA_BARRA = 1000
_GIB = 1024**3
_MAX_MENSAJES = 6
_ORDEN_PASOS = tuple(PasoB2)
_PASOS_CON_MAQUINA = (PasoB2.CREAR, PasoB2.AMPLIAR, PasoB2.CLOUDINIT, PasoB2.CONVERTIR)
_PASOS_OMITIBLES = (PasoB2.AMPLIAR, PasoB2.CLOUDINIT, PasoB2.CONVERTIR)
_MARCAS_CAPAS = {Severidad.ERROR: "✕", Severidad.AVISO: "⚠"}


class _Fase(Enum):
    EDITANDO = "editando"  # el formulario se puede cambiar
    COMPROBANDO = "comprobando"  # lecturas previas (solo GET) antes de confirmar
    EN_CURSO = "en_curso"  # un paso (o el borrado) está trabajando
    DETENIDO = "detenido"  # un paso falló, quedó dudoso o se dejó de esperar
    TERMINADO = "terminado"  # los cinco pasos están resueltos


class _PuenteProgreso(QObject):
    """Guarda el último progreso (hilo de trabajo) para que la interfaz lo tome sin saturarse."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cerrojo = threading.Lock()
        self._ultimo: Progreso | None = None

    def observar(self, progreso: Progreso) -> None:
        with self._cerrojo:
            self._ultimo = progreso

    def tomar(self) -> Progreso | None:
        with self._cerrojo:
            progreso, self._ultimo = self._ultimo, None
            return progreso


def boton_ayuda_texto(texto: str, parent: QWidget | None = None) -> QToolButton:
    """Icono «?» con una explicación (RF-B8.1). Pulsarlo muestra el texto en el sitio."""
    btn = QToolButton(parent)
    btn.setText("?")
    btn.setToolTip(texto)
    btn.setAccessibleName(QCoreApplication.translate("DialogoPlantillaImagen", "Ayuda"))
    btn.setAccessibleDescription(texto)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    btn.setAutoRaise(True)
    btn.setCursor(Qt.CursorShape.WhatsThisCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    btn.setStyleSheet("padding: 0px; min-height: 0px;")
    btn.setFixedSize(24, 24)

    def _mostrar() -> None:
        from PySide6.QtWidgets import QToolTip

        QToolTip.showText(btn.mapToGlobal(btn.rect().bottomLeft()), btn.toolTip(), btn)

    btn.clicked.connect(_mostrar)
    return btn


def _titulo_con_ayuda(texto: str, ayuda: str) -> QWidget:
    """Cabecera de sección: título en negrita y su «?»."""
    caja = QWidget()
    capa = QHBoxLayout(caja)
    capa.setContentsMargins(0, 6, 0, 0)
    etiqueta = QLabel(texto)
    fuente = etiqueta.font()
    fuente.setBold(True)
    etiqueta.setFont(fuente)
    capa.addWidget(etiqueta)
    if ayuda:
        capa.addWidget(boton_ayuda_texto(ayuda))
    capa.addStretch(1)
    return caja


def _etiqueta(texto: str = "", *, secundario: bool = False) -> QLabel:
    lbl = QLabel(texto)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    if secundario:
        lbl.setProperty("secundario", True)
    return lbl


def texto_problema_completo_origen(q: Problema) -> str:
    """Texto de un problema de las comprobaciones de la transferencia (V-O13, V-O15…)."""
    return texto_problema(q)


def _gib_de_bytes(valor: int) -> int:
    """GiB redondeados hacia arriba (nunca se subestima el tamaño de una imagen)."""
    return -(-valor // _GIB)


class DialogoPlantillaImagen(QDialog):
    """Asistente de cinco pasos para crear una plantilla desde una imagen cloud.

    Señales:
    - ``terminada(object)``: ``EstadoPlantillaImagen`` cuando los cinco pasos están resueltos
      (la plantilla existe, o se dejó la máquina como máquina normal por elección del usuario).
    """

    terminada = Signal(object)

    def __init__(
        self,
        *,
        sesion: Sesion,
        reloj: Reloj,
        lanzador: Lanzador,
        transferencias: ServicioTransferencias,
        inv: Inventario,
        avanzado: bool,
        nodo: str = "",
        fabrica_creacion: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sesion = sesion
        self._reloj_app = reloj
        self._lanzador = lanzador
        self._transferencias = transferencias
        self._inv = inv
        self._avanzado = avanzado
        self._caps: Capacidades = sesion.capacidades
        self._servicio = ServicioPlantillaImagen(
            sesion, reloj, transferencias, fabrica_creacion=fabrica_creacion
        )
        self._estado = EstadoPlantillaImagen()
        self._vista = EstadoPlantillaImagen()  # última copia recibida del hilo de trabajo
        self._sol: SolicitudPlantillaImagen | None = None  # solicitud de la ejecución actual
        self._fase = _Fase.EDITANDO
        self._trabajador: Trabajador | None = None
        self._cancelando = False
        self._cerrar_al_terminar = False
        self._cerrado = False
        self._inicio = 0.0
        self._ultimo_progreso: Progreso | None = None
        self._tocado = False
        self._construyendo = True
        self._hay_errores = True
        self._problemas_claves: list[str] = []
        self._avisos_finales: list[str] = []
        self._existente_mostrado = False
        self._raiz_mostrada = False
        self._nombre_editado = False
        self._tamano_editado = False
        self._ruta: Path | None = None
        self._insp: InspeccionImagen | None = None
        self._gen_insp = 0
        self._gen_comp = 0
        self._url: UrlDescarga | None = None
        self._error_url = ""
        self._suma: ChecksumTransferencia | None = None
        self._error_suma = ""
        self._existente: str | None = None  # volid que la comprobación halló con el mismo nombre
        self._clave_comprobada: tuple[str, ...] | None = None
        self._volumenes_import: dict[str, tuple[Volumen, ...]] = {}
        self._volumenes_actuales: tuple[Volumen, ...] = ()
        self._disp: DisponibilidadB2 = {}
        self._condiciones: CondicionesBorrado | None = None
        self._gen_borrado = 0
        self._puente = _PuenteProgreso(self)
        self._temporizador = QTimer(self)
        self._temporizador.setInterval(INTERVALO_PROGRESO_MS)
        self._temporizador.timeout.connect(self._vaciar_progreso)
        self._timer_validar = QTimer(self)
        self._timer_validar.setSingleShot(True)
        self._timer_validar.setInterval(INTERVALO_VALIDACION_MS)
        self._timer_validar.timeout.connect(self._revalidar)

        self.setWindowTitle(titulo_asistente_b2())
        self.setModal(True)
        self.setMinimumWidth(640)
        self._capa, self._pie, self._ajuste = hacer_desplazable(self)
        # Hueco a la derecha para que los campos no queden pegados a la barra de desplazamiento.
        self._capa.setContentsMargins(0, 0, 8, 0)
        self._construir_intro()
        self._construir_progreso()
        self._construir_imagen()
        self._construir_destino()
        self._construir_maquina()
        self._construir_fijas()
        self._construir_cloudinit()
        self._construir_confirmacion()
        self._construir_pie()
        self._poblar_nodos(nodo)
        self._al_cambiar_origen()
        self._construyendo = False
        self._timer_validar.start()

    # ---------------------------------------------------------------------------------------
    # Construcción
    # ---------------------------------------------------------------------------------------

    def _construir_intro(self) -> None:
        self.etiqueta_intro = _etiqueta(texto_intro_b2())
        self.etiqueta_intro.setAccessibleName(self.tr("Qué hace este asistente"))
        self._capa.addWidget(_titulo_con_ayuda(self.tr("Qué vas a hacer"), ayuda_b2("intro")))
        self._capa.addWidget(self.etiqueta_intro)
        self.etiqueta_bloqueo = _etiqueta()
        self.etiqueta_bloqueo.setProperty("error", True)
        self.etiqueta_bloqueo.hide()
        self._capa.addWidget(self.etiqueta_bloqueo)

    def _construir_imagen(self) -> None:
        self._capa.addWidget(_titulo_con_ayuda(self.tr("1. La imagen"), ayuda_b2("imagen")))
        self.radio_archivo = QRadioButton(self.tr("Un archivo de mi equipo"))
        self.radio_url = QRadioButton(self.tr("Una dirección web (la descarga el servidor)"))
        self.radio_importada = QRadioButton(self.tr("Una imagen que ya está en el servidor"))
        self.radio_archivo.setChecked(True)
        for r in (self.radio_archivo, self.radio_url, self.radio_importada):
            r.toggled.connect(self._al_cambiar_origen)
            self._capa.addWidget(r)

        # Archivo local.
        self.panel_archivo = QWidget()
        capa_a = QVBoxLayout(self.panel_archivo)
        capa_a.setContentsMargins(20, 0, 0, 0)
        fila = QHBoxLayout()
        self.campo_ruta = QLineEdit()
        self.campo_ruta.setReadOnly(True)
        self.campo_ruta.setPlaceholderText(self.tr("Ningún archivo elegido"))
        self.campo_ruta.setAccessibleName(self.tr("Archivo de imagen elegido"))
        self.boton_elegir = QPushButton(self.tr("Elegir archivo…"))
        self.boton_elegir.setAutoDefault(False)
        self.boton_elegir.clicked.connect(self._elegir_archivo)
        fila.addWidget(self.campo_ruta, 1)
        fila.addWidget(self.boton_elegir)
        self.etiqueta_inspeccion = _etiqueta(secundario=True)
        capa_a.addLayout(fila)
        capa_a.addWidget(self.etiqueta_inspeccion)
        self._capa.addWidget(self.panel_archivo)

        # Dirección web.
        self.panel_url = QWidget()
        capa_u = QVBoxLayout(self.panel_url)
        capa_u.setContentsMargins(20, 0, 0, 0)
        self.campo_url = QLineEdit()
        self.campo_url.setPlaceholderText(self.tr("https://…"))
        self.campo_url.setAccessibleName(self.tr("Dirección web de la imagen"))
        self.campo_url.textChanged.connect(self._al_cambiar_url)
        self.casilla_certificados = QCheckBox(
            self.tr("Comprobar el certificado del servidor web (recomendado)")
        )
        self.casilla_certificados.setChecked(True)
        self.casilla_certificados.setVisible(self._avanzado)
        self.casilla_certificados.toggled.connect(self._cambio)
        self.etiqueta_url = _etiqueta(secundario=True)
        self.etiqueta_ejemplos = _etiqueta(texto_ejemplos_urls_b2(), secundario=True)
        self.etiqueta_ejemplos.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        capa_u.addWidget(self.campo_url)
        capa_u.addWidget(self.casilla_certificados)
        capa_u.addWidget(self.etiqueta_url)
        capa_u.addWidget(self.etiqueta_ejemplos)
        self._capa.addWidget(self.panel_url)

        # Imagen ya importada.
        self.panel_importada = QWidget()
        capa_i = QHBoxLayout(self.panel_importada)
        capa_i.setContentsMargins(20, 0, 0, 0)
        self.combo_importadas = QComboBox()
        self.combo_importadas.setAccessibleName(self.tr("Imágenes que ya están en el servidor"))
        self.combo_importadas.currentIndexChanged.connect(self._cambio)
        self.boton_actualizar_importadas = QPushButton(self.tr("Actualizar lista"))
        self.boton_actualizar_importadas.setAutoDefault(False)
        self.boton_actualizar_importadas.clicked.connect(self._leer_importadas)
        capa_i.addWidget(self.combo_importadas, 1)
        capa_i.addWidget(self.boton_actualizar_importadas)
        self._capa.addWidget(self.panel_importada)

        # Suma de verificación (opcional).
        self.campo_suma = QLineEdit()
        self.campo_suma.setPlaceholderText(self.tr("Opcional: suma de verificación (SHA-256…)"))
        self.campo_suma.setAccessibleName(self.tr("Suma de verificación de la imagen"))
        self.campo_suma.textChanged.connect(self._al_cambiar_suma)
        self.etiqueta_suma = _etiqueta(secundario=True)
        self.fila_suma = QWidget()
        capa_s = QVBoxLayout(self.fila_suma)
        capa_s.setContentsMargins(20, 0, 0, 0)
        cab = QHBoxLayout()
        cab.addWidget(self.campo_suma, 1)
        cab.addWidget(boton_ayuda_texto(ayuda_b2("suma")))
        capa_s.addLayout(cab)
        capa_s.addWidget(self.etiqueta_suma)
        self._capa.addWidget(self.fila_suma)

    def _construir_destino(self) -> None:
        self._capa.addWidget(_titulo_con_ayuda(self.tr("2. Dónde se crea"), ""))
        self.combo_nodo = QComboBox()
        self.combo_nodo.setAccessibleName(self.tr("Nodo donde se crea la plantilla"))
        self.combo_nodo.currentIndexChanged.connect(self._al_cambiar_nodo)
        self.combo_storage_import = QComboBox()
        self.combo_storage_import.setAccessibleName(
            self.tr("Almacenamiento donde queda la imagen importada")
        )
        self.combo_storage_import.currentIndexChanged.connect(self._al_cambiar_storage_import)
        self.combo_storage_destino = QComboBox()
        self.combo_storage_destino.setAccessibleName(self.tr("Almacenamiento del disco"))
        self.combo_storage_destino.currentIndexChanged.connect(self._cambio)
        self.etiqueta_lvm = _etiqueta(secundario=True)
        self.etiqueta_lvm.hide()
        formulario = QFormLayout()
        formulario.addRow(self.tr("Nodo"), self.combo_nodo)
        formulario.addRow(self.tr("Imagen importada en"), self.combo_storage_import)
        formulario.addRow(self.tr("Disco de la máquina en"), self.combo_storage_destino)
        self._capa.addLayout(formulario)
        self._capa.addWidget(self.etiqueta_lvm)

    def _construir_maquina(self) -> None:
        self._capa.addWidget(_titulo_con_ayuda(self.tr("3. La máquina modelo"), ""))
        self.campo_nombre = QLineEdit()
        self.campo_nombre.setAccessibleName(self.tr("Nombre de la plantilla"))
        self.campo_nombre.textEdited.connect(self._al_editar_nombre)
        self.spin_vmid = QSpinBox()
        self.spin_vmid.setRange(100, 999_999_999)
        self.spin_vmid.setValue(max(100, self._inv.proximo_vmid))
        self.spin_vmid.setAccessibleName(self.tr("Número de la máquina (VMID)"))
        self.spin_vmid.valueChanged.connect(self._cambio)
        self.spin_sockets = QSpinBox()
        self.spin_sockets.setRange(1, 4)
        self.spin_sockets.setValue(1)
        self.spin_sockets.setAccessibleName(self.tr("Sockets"))
        self.spin_cores = QSpinBox()
        self.spin_cores.setRange(1, 128)
        self.spin_cores.setValue(2)
        self.spin_cores.setAccessibleName(self.tr("Núcleos por socket"))
        self.spin_memoria = QDoubleSpinBox()
        self.spin_memoria.setRange(0.25, 4096.0)
        self.spin_memoria.setSingleStep(0.5)
        self.spin_memoria.setDecimals(2)
        self.spin_memoria.setValue(2.0)
        self.spin_memoria.setSuffix(self.tr(" GiB"))
        self.spin_memoria.setAccessibleName(self.tr("Memoria"))
        self.spin_tamano = QSpinBox()
        self.spin_tamano.setRange(1, 65536)
        self.spin_tamano.setValue(TAMANO_FINAL_POR_DEFECTO_GIB)
        self.spin_tamano.setSuffix(self.tr(" GiB"))
        self.spin_tamano.setAccessibleName(self.tr("Tamaño final del disco"))
        self.spin_tamano.valueChanged.connect(self._al_editar_tamano)
        self.etiqueta_tamano = _etiqueta(secundario=True)
        self.combo_firmware = QComboBox()
        self.combo_firmware.addItem(self.tr("SeaBIOS (el clásico)"), Firmware.SEABIOS)
        self.combo_firmware.addItem(self.tr("UEFI (OVMF)"), Firmware.OVMF)
        self.combo_firmware.setAccessibleName(self.tr("Firmware de arranque"))
        self.combo_firmware.currentIndexChanged.connect(self._cambio)
        self.combo_bridge = QComboBox()
        self.combo_bridge.setAccessibleName(self.tr("Red (bridge)"))
        self.combo_bridge.currentIndexChanged.connect(self._cambio)
        self.combo_modelo_red = QComboBox()
        self.combo_modelo_red.addItem("VirtIO", ModeloRed.VIRTIO)
        self.combo_modelo_red.addItem("Intel E1000", ModeloRed.E1000)
        self.combo_modelo_red.setAccessibleName(self.tr("Modelo de la tarjeta de red"))
        self.combo_modelo_red.currentIndexChanged.connect(self._cambio)
        self.spin_vlan = QSpinBox()
        self.spin_vlan.setRange(0, 4094)
        self.spin_vlan.setSpecialValueText(self.tr("Sin VLAN"))
        self.spin_vlan.setAccessibleName(self.tr("VLAN de la red"))
        self.spin_vlan.valueChanged.connect(self._cambio)
        fila_cpu = QHBoxLayout()
        fila_cpu.addWidget(self.spin_sockets)
        fila_cpu.addWidget(QLabel(self.tr("socket(s) ×")))
        fila_cpu.addWidget(self.spin_cores)
        fila_cpu.addWidget(QLabel(self.tr("núcleo(s)")))
        fila_cpu.addStretch(1)
        fila_red = QHBoxLayout()
        fila_red.addWidget(self.combo_bridge, 1)
        fila_red.addWidget(self.combo_modelo_red)
        fila_red.addWidget(self.spin_vlan)
        formulario = QFormLayout()
        formulario.addRow(self.tr("Nombre"), self.campo_nombre)
        formulario.addRow(self.tr("Número (VMID)"), self.spin_vmid)
        formulario.addRow(self.tr("Procesadores"), fila_cpu)
        formulario.addRow(self.tr("Memoria"), self.spin_memoria)
        formulario.addRow(self.tr("Tamaño final del disco"), self.spin_tamano)
        formulario.addRow(self.tr("Firmware"), self.combo_firmware)
        formulario.addRow(self.tr("Red"), fila_red)
        self._formulario_maquina = formulario
        self._capa.addLayout(formulario)
        self._capa.addWidget(self.etiqueta_tamano)

    def _construir_fijas(self) -> None:
        self._capa.addWidget(
            _titulo_con_ayuda(
                self.tr("4. Opciones para imágenes cloud"), ayuda_b2("opciones_cloud")
            )
        )
        self.casilla_unidad = QCheckBox(self.tr("Unidad cloud-init (donde Proxmox deja los datos)"))
        self.casilla_serie = QCheckBox(self.tr("Consola serie (la que esperan las imágenes cloud)"))
        self.casilla_agente = QCheckBox(
            self.tr("Agente invitado (para conocer la IP de las copias)")
        )
        for c in (self.casilla_unidad, self.casilla_serie, self.casilla_agente):
            c.setChecked(True)
            c.toggled.connect(self._cambio)
            self._capa.addWidget(c)
        self.etiqueta_fijas = _etiqueta(secundario=True)
        self._capa.addWidget(self.etiqueta_fijas)

    def _construir_cloudinit(self) -> None:
        self._capa.addWidget(_titulo_con_ayuda(self.tr("5. Valores de cloud-init (opcional)"), ""))
        self.grupo_cloudinit = QGroupBox(self.tr("Valores de cloud-init para las copias"))
        self.grupo_cloudinit.setCheckable(True)
        self.grupo_cloudinit.setChecked(False)
        self.grupo_cloudinit.toggled.connect(self._cambio)
        self.grupo_cloudinit.setAccessibleName(self.tr("Valores de cloud-init para las copias"))
        capa = QVBoxLayout(self.grupo_cloudinit)
        capa.addWidget(_titulo_con_ayuda(self.tr("Qué es esto"), ayuda_b2("cloudinit")))
        self.campo_usuario = QLineEdit()
        self.campo_usuario.setPlaceholderText(
            self.tr("Por ejemplo: ubuntu (vacío = el de la imagen)")
        )
        self.campo_usuario.setAccessibleName(self.tr("Usuario por defecto"))
        self.campo_usuario.textChanged.connect(self._cambio)
        self.campo_claves = QPlainTextEdit()
        self.campo_claves.setPlaceholderText(
            self.tr("Una clave pública por línea (ssh-ed25519 AAAA… tu@equipo)")
        )
        self.campo_claves.setAccessibleName(self.tr("Claves SSH públicas"))
        self.campo_claves.setFixedHeight(70)
        self.campo_claves.textChanged.connect(self._al_cambiar_claves)
        self.boton_pub = QPushButton(self.tr("Añadir archivo .pub…"))
        self.boton_pub.setAutoDefault(False)
        self.boton_pub.clicked.connect(self._anadir_pub)
        self.etiqueta_claves = _etiqueta()
        self.etiqueta_claves.setProperty("aviso", True)
        self.etiqueta_claves.hide()
        self.casilla_dhcp = QCheckBox(
            self.tr("Pedir IP por DHCP en la primera tarjeta (recomendado)")
        )
        self.casilla_dhcp.setChecked(True)
        self.casilla_dhcp.toggled.connect(self._cambio)
        self.campo_dns = QLineEdit()
        self.campo_dns.setPlaceholderText(self.tr("Por ejemplo: 1.1.1.1 8.8.8.8"))
        self.campo_dns.setAccessibleName(self.tr("Servidores DNS"))
        self.campo_dns.textChanged.connect(self._cambio)
        self.campo_dominio = QLineEdit()
        self.campo_dominio.setPlaceholderText(self.tr("Por ejemplo: lab.local"))
        self.campo_dominio.setAccessibleName(self.tr("Dominio de búsqueda"))
        self.campo_dominio.textChanged.connect(self._cambio)
        self.combo_actualizar = QComboBox()
        self.combo_actualizar.addItem(self.tr("Como la plantilla (sin cambios)"), None)
        self.combo_actualizar.addItem(self.tr("Sí, actualizar en el primer arranque"), True)
        self.combo_actualizar.addItem(self.tr("No actualizar"), False)
        self.combo_actualizar.setAccessibleName(self.tr("Actualizar paquetes al arrancar"))
        self.combo_actualizar.currentIndexChanged.connect(self._cambio)
        self.etiqueta_sin_contrasena = _etiqueta(
            self.tr(
                "Aquí no hay campo de contraseña a propósito: se copiaría a todas las máquinas."
            ),
            secundario=True,
        )
        formulario = QFormLayout()
        formulario.addRow(self.tr("Usuario"), self.campo_usuario)
        formulario.addRow(self.tr("Claves SSH"), self.campo_claves)
        formulario.addRow("", self.boton_pub)
        formulario.addRow("", self.etiqueta_claves)
        formulario.addRow("", self.casilla_dhcp)
        formulario.addRow(self.tr("DNS"), self.campo_dns)
        formulario.addRow(self.tr("Dominio"), self.campo_dominio)
        formulario.addRow(self.tr("Actualizar paquetes"), self.combo_actualizar)
        capa.addLayout(formulario)
        capa.addWidget(self.etiqueta_sin_contrasena)
        self.etiqueta_cloudinit_bloqueo = _etiqueta(secundario=True)
        self.etiqueta_cloudinit_bloqueo.hide()
        self._capa.addWidget(self.grupo_cloudinit)
        self._capa.addWidget(self.etiqueta_cloudinit_bloqueo)

    def _construir_confirmacion(self) -> None:
        self._capa.addWidget(_titulo_con_ayuda(self.tr("6. Confirmar"), ayuda_b2("irreversible")))
        self.casilla_irreversible = QCheckBox(texto_irreversible_b2())
        self.casilla_irreversible.setChecked(False)
        self.casilla_irreversible.setAccessibleName(texto_irreversible_b2())
        self.casilla_irreversible.toggled.connect(self._cambio)
        self.fila_existente = QWidget()
        capa_e = QVBoxLayout(self.fila_existente)
        capa_e.setContentsMargins(0, 0, 0, 0)
        self.etiqueta_existente = _etiqueta()
        self.etiqueta_existente.setProperty("aviso", True)
        self.radio_usar = QRadioButton(self.tr("Usar la que ya está (recomendado)"))
        self.radio_reemplazar = QRadioButton(self.tr("Reemplazarla por la nueva"))
        self.radio_usar.setChecked(True)
        capa_e.addWidget(self.etiqueta_existente)
        capa_e.addWidget(self.radio_usar)
        capa_e.addWidget(self.radio_reemplazar)
        self.fila_existente.hide()
        self.casilla_raiz = QCheckBox(self.tr("Entiendo que la subida puede fallar"))
        self.casilla_raiz.hide()
        self.etiqueta_validacion = _etiqueta()
        self.etiqueta_validacion.hide()
        self.etiqueta_precomprobacion = _etiqueta()
        self.etiqueta_precomprobacion.hide()
        for w in (
            self.casilla_irreversible,
            self.fila_existente,
            self.casilla_raiz,
            self.etiqueta_precomprobacion,
            self.etiqueta_validacion,
        ):
            self._capa.addWidget(w)

    def _construir_progreso(self) -> None:
        self.panel_progreso = QWidget()
        capa = QVBoxLayout(self.panel_progreso)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(_titulo_con_ayuda(self.tr("Progreso"), ""))
        self.etiquetas_pasos: dict[PasoB2, QLabel] = {}
        for paso in PasoB2:
            lbl = _etiqueta()
            lbl.setAccessibleName(texto_nombre_paso_b2(paso))
            self.etiquetas_pasos[paso] = lbl
            capa.addWidget(lbl)
        self.barra = QProgressBar()
        self.barra.setAccessibleName(self.tr("Avance del paso actual"))
        self.barra.setTextVisible(True)
        self.barra.hide()  # solo se ve mientras hay un trabajo en marcha
        self.etiqueta_progreso = _etiqueta()
        self.etiqueta_estado = _etiqueta()
        self.etiqueta_avisos = _etiqueta()
        self.etiqueta_avisos.setProperty("aviso", True)
        self.etiqueta_avisos.hide()
        self.etiqueta_final = _etiqueta()
        self.etiqueta_final.hide()
        self.etiqueta_borrado = _etiqueta(secundario=True)
        self.etiqueta_borrado.hide()
        self.detalles = DetallesTecnicos()
        self.boton_reintentar = QPushButton()
        self.boton_comprobar = QPushButton(self.tr("Comprobar ahora"))
        self.boton_omitir = QPushButton()
        self.boton_borrar = QPushButton(self.tr("Borrar la máquina a medio crear…"))
        for b, accion in (
            (self.boton_reintentar, self._reintentar),
            (self.boton_comprobar, self._comprobar_ahora),
            (self.boton_omitir, self._omitir),
            (self.boton_borrar, self._borrar),
        ):
            b.setAutoDefault(False)
            b.clicked.connect(accion)
            b.hide()
        fila = QHBoxLayout()
        for b in (
            self.boton_reintentar,
            self.boton_comprobar,
            self.boton_omitir,
            self.boton_borrar,
        ):
            fila.addWidget(b)
        fila.addStretch(1)
        for w in (
            self.barra,
            self.etiqueta_progreso,
            self.etiqueta_estado,
            self.etiqueta_avisos,
            self.etiqueta_final,
            self.etiqueta_borrado,
            self.detalles,
        ):
            capa.addWidget(w)
        capa.addLayout(fila)
        self.panel_progreso.hide()
        self._capa.addWidget(self.panel_progreso)

    def _construir_pie(self) -> None:
        self.boton_crear = QPushButton(self.tr("Crear plantilla"))
        self.boton_crear.setProperty("primario", True)
        self.boton_crear.setAutoDefault(False)
        self.boton_crear.setEnabled(False)
        self.boton_crear.clicked.connect(self._al_pulsar_crear)
        self.boton_cancelar = QPushButton(self.tr("Cancelar"))
        self.boton_cancelar.clicked.connect(self._al_pulsar_cancelar)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self.boton_crear)
        fila.addWidget(self.boton_cancelar)
        self._pie.addLayout(fila)
        # Acción con consecuencias: el foco inicial y la tecla Intro son de «Cancelar».
        self.boton_cancelar.setDefault(True)
        self.boton_cancelar.setFocus()

    # ---------------------------------------------------------------------------------------
    # API pública
    # ---------------------------------------------------------------------------------------

    @property
    def fase(self) -> str:
        return self._fase.value

    @property
    def estado(self) -> EstadoPlantillaImagen:
        """Estado de los pasos (la copia más reciente mientras trabaja)."""
        return self._vista if self._fase == _Fase.EN_CURSO else self._estado

    @property
    def en_curso(self) -> bool:
        """Un paso está trabajando (para el cierre de la aplicación)."""
        return self._fase in (_Fase.EN_CURSO, _Fase.COMPROBANDO)

    @property
    def mensajes_validacion(self) -> str:
        return self.etiqueta_validacion.text()

    @property
    def solicitud(self) -> SolicitudPlantillaImagen:
        """La solicitud que resulta del formulario ahora mismo (sin enviar nada)."""
        return self._construir_solicitud()

    def elegir_ruta(self, ruta: Path) -> None:
        """Fija el archivo local (equivale a «Elegir archivo…») y lee su cabecera."""
        self.radio_archivo.setChecked(True)
        self._ruta = ruta
        self._insp = None
        self.campo_ruta.setText(str(ruta))
        self.etiqueta_inspeccion.setText(self.tr("Leyendo el archivo…"))
        self._gen_insp += 1
        gen = self._gen_insp
        self._invalidar_comprobacion()

        def _al_terminar(insp: object) -> None:
            if gen == self._gen_insp and not self._cerrado and isinstance(insp, InspeccionImagen):
                self._al_inspeccionado(insp)

        def _al_fallar(error: ErrorProxLaunch) -> None:
            if gen == self._gen_insp and not self._cerrado:
                self._insp = None
                self.etiqueta_inspeccion.setText(texto_error(error))
                self._cambio()

        self._lanzador.lanzar(
            inspeccionar_imagen, ruta, al_terminar=_al_terminar, al_fallar=_al_fallar
        )

    def cancelar_trabajo(self) -> None:
        """Pide detener lo que trabaja (cierre de la aplicación); no se borra nada (CA-B2.10.6)."""
        if self._fase != _Fase.EN_CURSO or self._cancelando:
            return
        self._cancelando = True
        self.boton_cancelar.setEnabled(False)
        self.etiqueta_estado.setText(self.tr("Dejando de esperar…"))
        if self._trabajador is not None:
            self._trabajador.cancelar()

    # ---------------------------------------------------------------------------------------
    # Nodo, almacenamientos y disponibilidad
    # ---------------------------------------------------------------------------------------

    def _poblar_nodos(self, nodo: str) -> None:
        nodos = [n.nombre for n in self._inv.topologia.nodos if n.en_linea] or [
            n.nombre for n in self._inv.topologia.nodos
        ]
        self.combo_nodo.blockSignals(True)
        self.combo_nodo.clear()
        for n in nodos:
            self.combo_nodo.addItem(n, n)
        if nodo in nodos:
            self.combo_nodo.setCurrentIndex(nodos.index(nodo))
        self.combo_nodo.blockSignals(False)
        self._al_cambiar_nodo()

    def _nodo(self) -> str:
        return str(self.combo_nodo.currentData() or "")

    def _al_cambiar_nodo(self, *_args: object) -> None:
        nodo = self._nodo()
        self._poblar_combo_storages(
            self.combo_storage_import, candidatos(self._inv, Contenido.IMPORT, nodo)
        )
        self._poblar_combo_storages(
            self.combo_storage_destino, candidatos(self._inv, Contenido.IMAGENES, nodo)
        )
        self.combo_bridge.blockSignals(True)
        self.combo_bridge.clear()
        for b in self._inv.bridges.get(nodo, ()):
            self.combo_bridge.addItem(b.nombre, b.nombre)
        self.combo_bridge.blockSignals(False)
        permisos = self._inv.catalogo.permisos if self._inv.catalogo is not None else None
        self._disp = disponibilidad_plantilla_imagen(permisos, self._caps, self._inv, nodo)
        self._aplicar_disponibilidad()
        self._poblar_importadas()
        self._cambio()

    @staticmethod
    def _poblar_combo_storages(combo: QComboBox, storages: tuple[Storage, ...]) -> None:
        previo = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for s in storages:
            combo.addItem(f"{s.id} ({s.tipo}, {s.libre_gib:g} GiB libres)", s.id)
        indice = combo.findData(previo)
        combo.setCurrentIndex(indice if indice >= 0 else 0)
        combo.blockSignals(False)

    def _al_cambiar_storage_import(self, *_args: object) -> None:
        self._poblar_importadas()
        self._cambio()

    def _aplicar_disponibilidad(self) -> None:
        """Habilita o deshabilita cada control con su motivo (versión antes que privilegio)."""
        disp = self._disp

        def estado(control: ControlB2) -> tuple[bool, str]:
            e = disp.get(control)
            if e is None or e.habilitado:
                return True, ""
            return False, texto_estado_control_b2(e)

        ok, motivo = estado(ControlB2.ASISTENTE)
        self.etiqueta_bloqueo.setVisible(not ok)
        self.etiqueta_bloqueo.setText(motivo)
        for radio, control in (
            (self.radio_archivo, ControlB2.ORIGEN_ARCHIVO),
            (self.radio_url, ControlB2.ORIGEN_URL),
            (self.radio_importada, ControlB2.ORIGEN_YA_IMPORTADA),
        ):
            habilitado, razon = estado(control)
            radio.setEnabled(habilitado and ok)
            radio.setToolTip(razon)
        # Si el origen elegido ya no es posible, se pasa al primero que sí lo es.
        if not self._origen_radio().isEnabled():
            for radio in (self.radio_archivo, self.radio_url, self.radio_importada):
                if radio.isEnabled():
                    radio.setChecked(True)
                    break
        for casilla, control in (
            (self.casilla_unidad, ControlB2.UNIDAD_CLOUDINIT),
            (self.casilla_serie, ControlB2.CONSOLA_SERIE),
            (self.casilla_agente, ControlB2.AGENTE),
        ):
            habilitado, razon = estado(control)
            casilla.setEnabled(habilitado)
            casilla.setToolTip(razon)
            if not habilitado:
                casilla.setChecked(False)
        textos = [
            razon
            for control in (
                ControlB2.UNIDAD_CLOUDINIT,
                ControlB2.CONSOLA_SERIE,
                ControlB2.AGENTE,
                ControlB2.CONVERTIR,
            )
            if (razon := estado(control)[1])
        ]
        self.etiqueta_fijas.setText("\n".join(textos))
        self.etiqueta_fijas.setVisible(bool(textos))
        habilitado, razon = estado(ControlB2.VALORES_CLOUDINIT)
        self.grupo_cloudinit.setEnabled(habilitado)
        if not habilitado:
            self.grupo_cloudinit.setChecked(False)
        self.etiqueta_cloudinit_bloqueo.setText(razon)
        self.etiqueta_cloudinit_bloqueo.setVisible(bool(razon))

    # ---------------------------------------------------------------------------------------
    # Origen de la imagen
    # ---------------------------------------------------------------------------------------

    def _origen_radio(self) -> QRadioButton:
        if self.radio_url.isChecked():
            return self.radio_url
        if self.radio_importada.isChecked():
            return self.radio_importada
        return self.radio_archivo

    def _origen(self) -> OrigenImagen:
        if self.radio_url.isChecked():
            return OrigenImagen.URL
        if self.radio_importada.isChecked():
            return OrigenImagen.YA_IMPORTADA
        return OrigenImagen.ARCHIVO_LOCAL

    def _al_cambiar_origen(self, *_args: object) -> None:
        origen = self._origen()
        self.panel_archivo.setVisible(origen == OrigenImagen.ARCHIVO_LOCAL)
        self.panel_url.setVisible(origen == OrigenImagen.URL)
        self.panel_importada.setVisible(origen == OrigenImagen.YA_IMPORTADA)
        self.fila_suma.setVisible(origen != OrigenImagen.YA_IMPORTADA)
        self.combo_storage_import.setEnabled(origen != OrigenImagen.YA_IMPORTADA)
        self._invalidar_comprobacion()
        self._cambio()

    def _elegir_archivo(self) -> None:
        ruta, _filtro = QFileDialog.getOpenFileName(
            self,
            self.tr("Elegir la imagen de disco"),
            str(carpeta_inicial()),
            self.tr("Imágenes de disco (*.qcow2 *.img *.raw *.vmdk)"),
        )
        if ruta:
            self.elegir_ruta(Path(ruta))

    def _al_inspeccionado(self, insp: InspeccionImagen) -> None:
        self._insp = insp
        ruta = self._ruta
        partes: list[str] = []
        if insp.motivo_rechazo is not None:
            codigo = "V-B03" if insp.motivo_rechazo == "extension" else "V-B04"
            q = Problema(
                "origen",
                codigo,
                Severidad.ERROR,
                {"motivo": insp.motivo_rechazo, "archivo": ruta.name if ruta else ""},
            )
            partes.append(texto_problema_b2(q) or "")
        else:
            if insp.tamano_virtual_bytes is not None:
                partes.append(
                    self.tr("La imagen mide {tam} (tamaño del disco virtual).").format(
                        tam=formatear_bytes(insp.tamano_virtual_bytes)
                    )
                )
                virtual = _gib_de_bytes(insp.tamano_virtual_bytes)
                if not self._tamano_editado and virtual > self.spin_tamano.value():
                    self.spin_tamano.blockSignals(True)
                    self.spin_tamano.setValue(virtual)
                    self.spin_tamano.blockSignals(False)
            if insp.nombre_final and ruta is not None and insp.nombre_final != ruta.name:
                partes.append(
                    self.tr(
                        "Se subirá como «{nombre}» (el contenido del archivo no cambia)."
                    ).format(nombre=insp.nombre_final)
                )
            for aviso in insp.avisos:
                partes.append(texto_aviso_b(aviso) or aviso)
        self.etiqueta_inspeccion.setText(" ".join(p for p in partes if p))
        if insp.nombre_final and not self._nombre_editado:
            self.campo_nombre.setText(nombre_sugerido(insp.nombre_final))
        self._invalidar_comprobacion()
        self._cambio()

    def _al_cambiar_url(self, *_args: object) -> None:
        texto = self.campo_url.text().strip()
        self._url = None
        self._error_url = ""
        nota = ""
        if texto:
            url, motivo = validar_url(texto, permitir_http=self._avanzado)
            if url is None:
                self._error_url = texto_motivo_url(motivo or "")
            else:
                self._url = url
                nombre, _motivo, avisos = nombre_para_url(url)
                if nombre and not self._nombre_editado:
                    self.campo_nombre.setText(nombre_sugerido(nombre))
                nota = " ".join(t for t in (texto_aviso_b(a) for a in avisos) if t)
        if self._error_url:
            poner_mensaje(self.etiqueta_url, self._error_url)
        else:
            poner_mensaje(self.etiqueta_url, nota or None, aviso=True)
        self._invalidar_comprobacion()
        self._cambio()

    def _al_cambiar_suma(self, *_args: object) -> None:
        texto = self.campo_suma.text().strip()
        self._suma = None
        self._error_suma = ""
        if texto:
            suma, motivo = validar_checksum(texto)
            if suma is None:
                self._error_suma = texto_motivo_checksum(motivo or "")
            else:
                self._suma = suma
        poner_mensaje(self.etiqueta_suma, self._error_suma or None)
        self._cambio()

    def _poblar_importadas(self) -> None:
        """Lista de imágenes ya importadas del nodo (la del catálogo; ``Actualizar`` la relee)."""
        nodo = self._nodo()
        volumenes = self._volumenes_import.get(nodo)
        if volumenes is None:
            volumenes = self._volumenes_del_catalogo(nodo)
        previo = self.combo_importadas.currentData()
        self.combo_importadas.blockSignals(True)
        self.combo_importadas.clear()
        for v in volumenes:
            if not v.admitido:
                continue
            self.combo_importadas.addItem(
                f"{v.nombre} ({v.storage}, {formatear_bytes(v.tamano_bytes)})", v.volid
            )
        indice = self.combo_importadas.findData(previo)
        self.combo_importadas.setCurrentIndex(indice if indice >= 0 else 0)
        self.combo_importadas.blockSignals(False)
        self._volumenes_actuales = volumenes

    def _volumenes_del_catalogo(self, nodo: str) -> tuple[Volumen, ...]:
        catalogo = self._inv.catalogo
        if catalogo is None:
            return ()
        salida: list[Volumen] = []
        for listado in catalogo.listados:
            if listado.nodo == nodo and listado.contenido == Contenido.IMPORT:
                salida.extend(listado.volumenes)
        return tuple(salida)

    def _leer_importadas(self) -> None:
        """«Actualizar lista»: vuelve a leer las imágenes del servidor (solo lectura)."""
        nodo = self._nodo()
        if not nodo:
            return
        self.boton_actualizar_importadas.setEnabled(False)

        def _al_terminar(listados: object) -> None:
            self.boton_actualizar_importadas.setEnabled(True)
            if self._cerrado or nodo != self._nodo() or not isinstance(listados, tuple):
                return
            volumenes: list[Volumen] = []
            for listado in listados:
                volumenes.extend(listado.volumenes)
            self._volumenes_import[nodo] = tuple(volumenes)
            self._poblar_importadas()
            self._cambio()

        def _al_fallar(error: ErrorProxLaunch) -> None:
            self.boton_actualizar_importadas.setEnabled(True)
            if not self._cerrado:
                poner_mensaje(self.etiqueta_validacion, texto_error(error))

        self._lanzador.lanzar(
            leer_listados,
            self._sesion,
            self._reloj_app,
            self._inv,
            nodo,
            Contenido.IMPORT,
            al_terminar=_al_terminar,
            al_fallar=_al_fallar,
        )

    def _volumen_importado(self) -> Volumen | None:
        volid = self.combo_importadas.currentData()
        for v in self._volumenes_actuales:
            if v.volid == volid:
                return v
        return None

    # ---------------------------------------------------------------------------------------
    # Datos de la máquina
    # ---------------------------------------------------------------------------------------

    def _al_editar_nombre(self, _texto: str) -> None:
        self._nombre_editado = True
        self._cambio()

    def _al_editar_tamano(self, _valor: int) -> None:
        self._tamano_editado = True
        self._cambio()

    def _nombre_archivo(self, origen: OrigenImagen) -> str:
        if origen == OrigenImagen.ARCHIVO_LOCAL:
            if self._insp is not None and self._insp.nombre_final:
                return self._insp.nombre_final
            return self._ruta.name if self._ruta is not None else ""
        if origen == OrigenImagen.URL:
            if self._url is None:
                return ""
            nombre, _motivo, _avisos = nombre_para_url(self._url)
            return nombre or self._url.archivo
        volumen = self._volumen_importado()
        return volumen.nombre if volumen is not None else ""

    # ---------------------------------------------------------------------------------------
    # Valores de cloud-init de la plantilla (RF-B2.8): sin contraseña, solo la primera tarjeta
    # ---------------------------------------------------------------------------------------

    def _al_cambiar_claves(self) -> None:
        texto = self.campo_claves.toPlainText()
        if contiene_clave_privada(texto):
            # Se rechaza TODO y se borra de inmediato del campo (RF-B1.5).
            self.campo_claves.blockSignals(True)
            self.campo_claves.clear()
            self.campo_claves.blockSignals(False)
            self._problemas_claves = []
            poner_mensaje(self.etiqueta_claves, texto_clave_privada_rechazada(), aviso=True)
        else:
            resultado = analizar_claves(texto)
            self._problemas_claves = [
                texto_problema_clave(q.linea, str(q.motivo)) for q in resultado.problemas
            ]
            poner_mensaje(
                self.etiqueta_claves, " ".join(self._problemas_claves) or None, aviso=True
            )
        self._cambio()

    def _anadir_pub(self) -> None:
        rutas, _filtro = QFileDialog.getOpenFileNames(
            self,
            self.tr("Elegir claves públicas"),
            str(carpeta_inicial()),
            self.tr("Claves públicas (*.pub);;Todos los archivos (*)"),
        )
        for ruta in rutas:
            self.anadir_archivo_pub(Path(ruta))

    def anadir_archivo_pub(self, ruta: Path) -> None:
        """Añade el contenido de un archivo ``.pub`` (≤ 64 KiB, texto). Nada si es una clave
        privada o no se puede leer: se explica y no se guarda nada."""
        try:
            contenido = leer_archivo_pub(ruta)
        except ErrorProxLaunch as error:
            poner_mensaje(self.etiqueta_claves, texto_error(error), aviso=True)
            return
        if contiene_clave_privada(contenido):
            poner_mensaje(self.etiqueta_claves, texto_clave_privada_rechazada(), aviso=True)
            return
        actual = self.campo_claves.toPlainText().rstrip("\n")
        self.campo_claves.setPlainText((actual + "\n" if actual else "") + contenido.strip())

    def _cloudinit_actual(self) -> ConfigCloudInit | None:
        """Valores de cloud-init pedidos (``None`` si la sección está sin marcar). Nunca lleva
        contraseña, snippets ni IP fija: B2 no los admite (V-B39)."""
        if not self.grupo_cloudinit.isChecked() or not self.grupo_cloudinit.isEnabled():
            return None
        claves = analizar_claves(self.campo_claves.toPlainText()).claves
        texto_dns = self.campo_dns.text()
        dns, motivo = normalizar_dns(texto_dns)
        if motivo is not None:  # que la validación de B1 (V-B32) lo señale
            dns = tuple(t for t in re.split(r"[,\s]+", texto_dns.strip()) if t)
        tarjetas = (TarjetaCloudInit(0, ModoTarjeta.DHCP),) if self.casilla_dhcp.isChecked() else ()
        actualizar = self.combo_actualizar.currentData()
        return ConfigCloudInit(
            usuario=self.campo_usuario.text().strip(),
            claves=claves,
            tarjetas=tarjetas,
            dns=dns,
            dominio=self.campo_dominio.text().strip(),
            actualizar=actualizar if isinstance(actualizar, bool) else None,
        )

    # ---------------------------------------------------------------------------------------
    # Solicitud y validación
    # ---------------------------------------------------------------------------------------

    def _construir_solicitud(self) -> SolicitudPlantillaImagen:
        origen = self._origen()
        nodo = self._nodo()
        volumen = self._volumen_importado() if origen == OrigenImagen.YA_IMPORTADA else None
        storage_import = (
            volumen.storage
            if volumen is not None
            else str(self.combo_storage_import.currentData() or "")
        )
        storage_destino = str(self.combo_storage_destino.currentData() or "")
        bridge = str(self.combo_bridge.currentData() or "")
        redes = (
            [
                InterfazRed(
                    bridge,
                    ModeloRed(str(self.combo_modelo_red.currentData())),
                    self.spin_vlan.value() or None,
                )
            ]
            if bridge
            else []
        )
        cfg = ConfiguracionVM(
            vmid=self.spin_vmid.value(),
            nombre=self.campo_nombre.text().strip(),
            nodo=nodo,
            firmware=Firmware(str(self.combo_firmware.currentData())),
            sockets=self.spin_sockets.value(),
            cores=self.spin_cores.value(),
            memoria_mib=round(self.spin_memoria.value() * 1024),
            discos=[Disco(storage_destino, self.spin_tamano.value())],
            redes=redes,
        )
        local = origen == OrigenImagen.ARCHIVO_LOCAL
        accion: AccionExistente | None = None
        if self._existente is not None and origen != OrigenImagen.YA_IMPORTADA:
            accion = (
                AccionExistente.REEMPLAZAR
                if self.radio_reemplazar.isChecked()
                else AccionExistente.USAR
            )
        return SolicitudPlantillaImagen(
            origen=origen,
            ruta_local=self._ruta if local else None,
            url=self._url if origen == OrigenImagen.URL else None,
            volid_existente=volumen.volid if volumen is not None else None,
            suma=self._suma if origen != OrigenImagen.YA_IMPORTADA else None,
            nodo=nodo,
            storage_import=storage_import,
            nombre_archivo=self._nombre_archivo(origen),
            accion_existente=accion,
            storage_destino=storage_destino,
            cfg=cfg,
            fijas=FijasPlantilla(
                unidad_cloudinit=self.casilla_unidad.isChecked(),
                consola_serie=self.casilla_serie.isChecked(),
                agente=self.casilla_agente.isChecked(),
            ),
            cloudinit=self._cloudinit_actual(),
            confirmada=self.casilla_irreversible.isChecked(),
            tamano_virtual_bytes=(
                self._insp.tamano_virtual_bytes if local and self._insp is not None else None
            ),
            acepta_aviso_raiz=self.casilla_raiz.isChecked(),
            # I3: sin modo avanzado la casilla está oculta y siempre se verifica el certificado,
            # aunque quedara desmarcada de antes.
            verificar_certificados=self._verificar_certificados(),
        )

    def _verificar_certificados(self) -> bool:
        """Solo en modo avanzado se puede dejar de verificar el certificado del servidor web."""
        return not self._avanzado or self.casilla_certificados.isChecked()

    def _problemas(self, sol: SolicitudPlantillaImagen) -> list[Problema]:
        """Problemas de la solicitud, sin los que se resuelven en otro sitio (casilla de
        irreversibilidad, elección de «ya existe») ni el ruido de un origen todavía incompleto."""
        todos = validar_solicitud(sol, self._inv, self._caps)
        origen_incompleto = any(
            q.codigo == "V-B02"
            and q.params.get("motivo") in ("falta_archivo", "falta_url", "volid")
            for q in todos
        )
        salida: list[Problema] = []
        for q in todos:
            if q.codigo in ("V-B13",):
                continue
            if origen_incompleto and q.codigo in ("V-B03", "V-B04", "V-B05", "V-B16"):
                continue
            salida.append(q)
        return salida

    def _errores_locales(self) -> list[str]:
        """Errores que detecta el formulario antes de construir la solicitud."""
        errores: list[str] = []
        origen = self._origen()
        if origen == OrigenImagen.URL and self._error_url:
            errores.append(self._error_url)
        if origen != OrigenImagen.YA_IMPORTADA and self._error_suma:
            errores.append(self._error_suma)
        if self.grupo_cloudinit.isChecked():
            errores.extend(self._problemas_claves)
        return errores

    def _cambio(self, *_args: object) -> None:
        """Cualquier cambio del formulario: se vuelve a validar en un momento."""
        if not self._construyendo:
            self._tocado = True
        if self._fase == _Fase.EDITANDO:
            self._timer_validar.start()

    def _revalidar(self) -> None:
        if self._fase != _Fase.EDITANDO or self._cerrado:
            return
        sol = self._construir_solicitud()
        problemas = self._problemas(sol)
        locales = self._errores_locales()
        # El tamaño de la imagen y el aviso de «solo crece» se explican junto al campo.
        v_b12 = next((q for q in problemas if q.codigo == "V-B12"), None)
        self.etiqueta_tamano.setText((texto_problema_b2(v_b12) or "") if v_b12 else "")
        self.etiqueta_tamano.setVisible(v_b12 is not None)
        lvm = next((q for q in problemas if q.codigo == "V-B08"), None)
        self.etiqueta_lvm.setText((texto_problema_b2(lvm) or "") if lvm else "")
        self.etiqueta_lvm.setVisible(lvm is not None)
        visibles = [q for q in problemas if q.codigo not in ("V-B12", "V-B08", "V-B14")]
        errores = [q for q in visibles if es_error(q)]
        avisos = [q for q in visibles if not es_error(q)]
        lineas = [f"{_MARCAS_CAPAS[Severidad.ERROR]} {t}" for t in locales]
        lineas += [
            f"{_MARCAS_CAPAS[q.severidad]} {texto_problema_completo(q)}"
            for q in (*errores, *avisos)
        ]
        if len(lineas) > _MAX_MENSAJES:
            resto = len(lineas) - _MAX_MENSAJES
            lineas = [*lineas[:_MAX_MENSAJES], self.tr("…y {n} más.").format(n=resto)]
        if self._tocado and lineas:
            poner_mensaje(
                self.etiqueta_validacion, "\n".join(lineas), aviso=not (errores or locales)
            )
        else:
            poner_mensaje(self.etiqueta_validacion, None)
        bloqueado = bool(locales) or any(es_error(q) and q.codigo != "V-B14" for q in problemas)
        self._hay_errores = bloqueado
        self._actualizar_boton_crear()

    def _actualizar_boton_crear(self) -> None:
        asistente = self._disp.get(ControlB2.ASISTENTE)
        permitido = asistente is None or asistente.habilitado
        listo = (
            self._fase == _Fase.EDITANDO
            and permitido
            and not self._hay_errores
            and self.casilla_irreversible.isChecked()
            and self._origen_radio().isEnabled()
        )
        self.boton_crear.setEnabled(listo)

    def _invalidar_comprobacion(self) -> None:
        """Lo comprobado en el servidor deja de valer si cambia el destino o la imagen."""
        self._gen_comp += 1
        self._existente = None
        self._existente_mostrado = False
        self._raiz_mostrada = False
        self.fila_existente.hide()
        self.casilla_raiz.hide()
        self.casilla_raiz.setChecked(False)
        poner_mensaje(self.etiqueta_precomprobacion, None)

    # ---------------------------------------------------------------------------------------
    # Crear: comprobaciones previas (solo lecturas), confirmación y ejecución
    # ---------------------------------------------------------------------------------------

    def _al_pulsar_crear(self) -> None:
        if self._fase != _Fase.EDITANDO or not self.boton_crear.isEnabled():
            return
        sol = self._construir_solicitud()
        if self._errores_locales() or hay_errores(
            [q for q in self._problemas(sol) if q.codigo != "V-B14"]
        ):
            self._timer_validar.start()
            return
        if sol.origen == OrigenImagen.YA_IMPORTADA:
            self._confirmar_y_ejecutar(sol)
            return
        self._fase = _Fase.COMPROBANDO
        self._actualizar_boton_crear()
        poner_mensaje(
            self.etiqueta_precomprobacion,
            self.tr("Comprobando el servidor (solo lecturas, no se escribe nada)…"),
            aviso=True,
        )
        local = sol.origen == OrigenImagen.ARCHIVO_LOCAL
        destino = DestinoTransferencia(
            sol.nodo, sol.storage_import, Contenido.IMPORT, sol.nombre_archivo
        )
        tamano = self._insp.tamano_bytes if local and self._insp is not None else None
        self._gen_comp += 1
        gen = self._gen_comp

        def _al_terminar(comp: object) -> None:
            if gen == self._gen_comp and not self._cerrado and isinstance(comp, ComprobacionPrevia):
                self._tras_comprobacion(comp)

        def _al_fallar(error: ErrorProxLaunch) -> None:
            if gen != self._gen_comp or self._cerrado:
                return
            self._fase = _Fase.EDITANDO
            poner_mensaje(self.etiqueta_precomprobacion, texto_error(error))
            self._actualizar_boton_crear()

        self._lanzador.lanzar(
            self._transferencias.comprobar,
            destino,
            tamano,
            self._inv,
            para_subida=local,
            permitir_reemplazo=True,
            al_terminar=_al_terminar,
            al_fallar=_al_fallar,
        )

    def _tras_comprobacion(self, comp: ComprobacionPrevia) -> None:
        self._fase = _Fase.EDITANDO
        errores = [q for q in comp.problemas if q.severidad == Severidad.ERROR]
        if errores:
            texto = "\n".join(texto_problema_completo_origen(q) for q in errores)
            poner_mensaje(self.etiqueta_precomprobacion, texto)
            self._actualizar_boton_crear()
            return
        detener = False
        mensajes: list[str] = []
        if comp.volid_existente is not None:
            self._existente = comp.volid_existente
            if not self._existente_mostrado:
                self._existente_mostrado = True
                self.etiqueta_existente.setText(
                    self.tr(
                        "Ya hay un archivo con ese nombre en el servidor («{volid}»). Elige si "
                        "usar el que ya está o reemplazarlo, y vuelve a pulsar «Crear plantilla»."
                    ).format(volid=comp.volid_existente)
                )
                self.fila_existente.show()
                detener = True
        else:
            self._existente = None
        raiz = next((q for q in comp.problemas if q.codigo == "V-O13.raiz"), None)
        if raiz is not None:
            mensajes.append(texto_problema_completo_origen(raiz))
            if not self._raiz_mostrada:
                self._raiz_mostrada = True
                self.casilla_raiz.show()
                detener = True
            elif not self.casilla_raiz.isChecked():
                detener = True
        if detener:
            poner_mensaje(self.etiqueta_precomprobacion, "\n".join(mensajes) or None, aviso=True)
            self._actualizar_boton_crear()
            return
        poner_mensaje(self.etiqueta_precomprobacion, None)
        self._confirmar_y_ejecutar(self._construir_solicitud())

    def _confirmar_y_ejecutar(self, sol: SolicitudPlantillaImagen) -> None:
        """Confirmación expresa antes de escribir nada: el botón predeterminado es «Cancelar»."""
        destinos = candidatos(self._inv, Contenido.IMAGENES, sol.nodo)
        lvm = any(s.id == sol.storage_destino and s.tipo == "lvm" for s in destinos)
        texto = texto_confirmacion_b2(
            nombre=sol.cfg.nombre,
            vmid=sol.cfg.vmid,
            nodo=sol.nodo,
            gib=sol.cfg.discos[0].tamano_gib if sol.cfg.discos else 0,
            storage=sol.storage_destino,
            imagen=sol.nombre_archivo,
            lvm=lvm,
        )
        if sol.url is not None and sol.url.es_http:
            texto += "\n\n" + self.tr(
                "La dirección usa http://: no se puede garantizar que el archivo no fue alterado "
                "por el camino."
            )
        if sol.origen == OrigenImagen.URL and not sol.verificar_certificados:
            texto += "\n\n" + self.tr(
                "No se comprobará el certificado del servidor web: podrías descargar un archivo "
                "de un sitio falso."
            )
        aceptado = confirmar(
            self,
            self.tr("Crear la plantilla"),
            texto,
            self.tr("Crear la plantilla"),
            self.tr("Cancelar"),
        )
        if not aceptado:
            self._fase = _Fase.EDITANDO
            self._actualizar_boton_crear()
            return
        self._sol = sol
        self._avisos_finales = self._calcular_avisos_finales(sol)
        self._estado = EstadoPlantillaImagen()
        self._ejecutar()

    def _calcular_avisos_finales(self, sol: SolicitudPlantillaImagen) -> list[str]:
        """Advertencias que se repiten en el resultado (RF-B2.11): agente, consola y LVM."""
        problemas = {q.codigo for q in validar_solicitud(sol, self._inv, self._caps)}
        avisos: list[str] = []
        if "V-B16" in problemas:
            avisos.append(AVISO_SIN_AGENTE_IMAGEN)
        if sol.fijas.consola_serie:
            avisos.append(AVISO_CONSOLA_SERIE)
        if "V-B08" in problemas:
            avisos.append(AVISO_SOLO_CLON_COMPLETO)
        if sol.url is not None and sol.url.archivo.lower().endswith(".img"):
            avisos.append("se_asume_qcow2")
        return avisos

    def _ejecutar(self) -> None:
        """Lanza (o reanuda) los pasos pendientes en un hilo; nunca repite uno ya hecho."""
        sol = self._sol
        if sol is None:
            return
        self._empezar_trabajo()
        servicio, inv, estado, puente = self._servicio, self._inv, self._estado, self._puente
        estado.error = None

        def _trabajo(*, al_cambiar_etapa: Any, al_enviar: Any, cancelado: threading.Event) -> Any:
            del al_enviar
            return servicio.ejecutar(sol, inv, estado, al_cambiar_etapa, puente.observar, cancelado)

        self._trabajador = self._lanzador.lanzar(
            _trabajo,
            con_contexto=True,
            al_terminar=self._al_terminar_trabajo,
            al_fallar=self._al_fallar_trabajo,
            al_etapa=self._al_estado,
        )

    def _empezar_trabajo(self) -> None:
        self._fase = _Fase.EN_CURSO
        self._cancelando = False
        self._inicio = time.monotonic()
        self._ultimo_progreso = None
        self._congelar(True)
        self._ocultar_acciones()
        self.panel_progreso.show()
        self.etiqueta_final.hide()
        self.detalles.limpiar()
        poner_mensaje(self.etiqueta_estado, self.tr("Trabajando…"), aviso=True)
        self.etiqueta_progreso.setText("")
        self._poner_barra_indeterminada()
        self.barra.show()
        self._vista = self._estado.copia()
        self._pintar_pasos(self._vista)
        self._ajustar_botones()
        self._temporizador.start()

    # ---------------------------------------------------------------------------------------
    # Progreso
    # ---------------------------------------------------------------------------------------

    def _al_estado(self, copia: object) -> None:
        if self._cerrado or not isinstance(copia, EstadoPlantillaImagen):
            return
        self._vista = copia
        self._pintar_pasos(copia)

    def _pintar_pasos(self, estado: EstadoPlantillaImagen) -> None:
        for paso in PasoB2:
            ep = estado.pasos[paso]
            lbl = self.etiquetas_pasos[paso]
            lbl.setText(
                f"{simbolo_estado_paso_b2(ep)} {texto_nombre_paso_b2(paso)} — "
                f"{texto_estado_paso_b2(ep)}"
            )
            poner_propiedad(lbl, "exito", ep == EstadoPaso.HECHO)
            poner_propiedad(lbl, "error", ep == EstadoPaso.FALLIDO)
            poner_propiedad(lbl, "aviso", ep == EstadoPaso.INCIERTO)
            poner_propiedad(lbl, "secundario", ep in (EstadoPaso.PENDIENTE, EstadoPaso.OMITIDO))
        textos = [t for t in (texto_aviso_b(a) for a in dict.fromkeys(estado.avisos)) if t]
        poner_mensaje(self.etiqueta_avisos, "\n".join(textos) or None, aviso=True)

    def _poner_barra_indeterminada(self) -> None:
        self.barra.setRange(0, 0)
        self.barra.setFormat("")

    def _vaciar_progreso(self) -> None:
        progreso = self._puente.tomar()
        if progreso is not None:
            self._mostrar_progreso(progreso)
        elif self._fase == _Fase.EN_CURSO and self._ultimo_progreso is None:
            self.etiqueta_progreso.setText(
                self.tr("Tiempo transcurrido: {t}").format(
                    t=texto_tiempo(time.monotonic() - self._inicio)
                )
            )

    def _mostrar_progreso(self, progreso: Progreso) -> None:
        """Progreso de la transferencia de la imagen (paso 1); solo cifras reales."""
        self._ultimo_progreso = progreso
        if not self._cancelando:
            self.etiqueta_progreso.setText(texto_progreso_transferencia(progreso))
        fraccion: float | None = None
        if (
            progreso.total_bytes
            and progreso.hechos_bytes > 0
            and progreso.porcentaje_servidor is None
        ):
            fraccion = progreso.hechos_bytes / progreso.total_bytes
        elif progreso.porcentaje_servidor is not None:
            fraccion = progreso.porcentaje_servidor / 100.0
        if fraccion is None:
            self._poner_barra_indeterminada()
        else:
            self.barra.setRange(0, _ESCALA_BARRA)
            self.barra.setValue(int(max(0.0, min(1.0, fraccion)) * _ESCALA_BARRA))
            self.barra.setFormat("%p%")
        self.barra.setAccessibleDescription(self.etiqueta_progreso.text())

    # ---------------------------------------------------------------------------------------
    # Fin de un tramo: éxito, fallo, duda o «Dejar de esperar»
    # ---------------------------------------------------------------------------------------

    def _al_terminar_trabajo(self, resultado: object) -> None:
        self._temporizador.stop()
        self._vaciar_progreso()
        self._trabajador = None
        self._cancelando = False
        if self._cerrado:
            return
        if isinstance(resultado, EstadoPlantillaImagen):
            self._estado = resultado
        self._fin_de_tramo()

    def _al_fallar_trabajo(self, error: ErrorProxLaunch) -> None:
        """Fallo inesperado fuera del servicio: se muestra y se puede reintentar."""
        self._temporizador.stop()
        self._trabajador = None
        self._cancelando = False
        if self._cerrado:
            return
        self._estado.error = error
        paso = self._estado.paso_pendiente
        if paso is not None and self._estado.pasos[paso] == EstadoPaso.EN_CURSO:
            self._estado.pasos[paso] = EstadoPaso.INCIERTO
        self._fin_de_tramo()

    def _fin_de_tramo(self) -> None:
        estado = self._estado
        self._vista = estado
        self._pintar_pasos(estado)
        if self._cerrar_al_terminar:
            self._cerrar_al_terminar = False
            QDialog.reject(self)
            return
        if estado.completo:
            self._terminar_bien()
        else:
            self._detener()

    def _terminar_bien(self) -> None:
        self._fase = _Fase.TERMINADO
        estado, sol = self._estado, self._sol
        self.barra.setRange(0, _ESCALA_BARRA)
        self.barra.setValue(_ESCALA_BARRA)
        self.barra.setFormat("%p%")
        self.barra.hide()
        poner_mensaje(self.etiqueta_estado, None)
        self.etiqueta_progreso.setText("")
        nombre = estado.nombre_reservado or (sol.cfg.nombre if sol else "")
        vmid = (
            estado.vmid_reservado
            if estado.vmid_reservado is not None
            else (sol.cfg.vmid if sol else 0)
        )
        if estado.es_plantilla:
            texto = texto_resultado_b2(
                nombre=nombre, vmid=vmid, storage=sol.storage_destino if sol else ""
            )
        else:
            texto = texto_resultado_b2_sin_plantilla(nombre=nombre, vmid=vmid)
        pendientes = [t for t in (texto_aviso_b(a) for a in self._avisos_finales) if t]
        if pendientes:
            texto += "\n\n" + self.tr("Para tener en cuenta:") + "\n• " + "\n• ".join(pendientes)
        self.etiqueta_final.setText(texto)
        poner_propiedad(self.etiqueta_final, "exito", estado.es_plantilla)
        poner_propiedad(self.etiqueta_final, "aviso", not estado.es_plantilla)
        self.etiqueta_final.show()
        self._ocultar_acciones()
        self._ajustar_botones()
        self.terminada.emit(estado)

    def _detener(self) -> None:
        """Un paso falló, quedó dudoso o se dejó de esperar: se explica y se ofrecen acciones."""
        self._fase = _Fase.DETENIDO
        estado, sol = self._estado, self._sol
        paso = estado.paso_pendiente
        self.barra.setRange(0, _ESCALA_BARRA)  # fuera de «indeterminada»: ya no se trabaja
        self.barra.setValue(0)
        self.barra.setFormat("")
        self.barra.hide()  # sin trabajo en marcha no hay avance que enseñar
        self.etiqueta_progreso.setText("")
        self._ocultar_acciones()
        if paso is None or sol is None:
            self._ajustar_botones()
            return
        ep = estado.pasos[paso]
        nombre_paso = texto_nombre_paso_b2(paso)
        partes: list[str] = []
        if ep == EstadoPaso.FALLIDO and estado.error is not None:
            partes.append(texto_error(estado.error))
        elif ep == EstadoPaso.INCIERTO:
            partes.append(
                self.tr(
                    "No sabemos cómo terminó el paso «{paso}» (se perdió la conexión o se dejó "
                    "de esperar). Pulsa «Comprobar ahora» para consultarlo en el servidor: solo "
                    "lee, no cambia nada."
                ).format(paso=nombre_paso)
            )
            if estado.error is not None:
                partes.append(texto_error(estado.error))
        else:
            partes.append(
                self.tr(
                    "Se detuvo antes de terminar el paso «{paso}». Lo que ya se envió al "
                    "servidor sigue su curso y no se borró nada. Puedes continuar desde aquí."
                ).format(paso=nombre_paso)
            )
        if ep in (EstadoPaso.FALLIDO, EstadoPaso.INCIERTO):
            partes.append(texto_que_queda_tras_fallo(paso, sol.nombre_archivo))
        poner_mensaje(self.etiqueta_estado, "\n".join(partes), aviso=ep != EstadoPaso.FALLIDO)
        if estado.error is not None:
            self.detalles.establecer(texto_detalles(estado.error, None))
        # Acciones de la tabla de RF-B2.10.
        if ep in (EstadoPaso.FALLIDO, EstadoPaso.PENDIENTE):
            etiqueta = (
                texto_accion_reintentar(paso) if ep == EstadoPaso.FALLIDO else self.tr("Continuar")
            )
            self.boton_reintentar.setText(etiqueta)
            self.boton_reintentar.show()
        if ep == EstadoPaso.INCIERTO:
            self.boton_comprobar.show()
        if ep == EstadoPaso.FALLIDO and paso in _PASOS_OMITIBLES:
            self.boton_omitir.setText(texto_accion_omitir(paso))
            self.boton_omitir.show()
        # El VMID se puede cambiar para reintentar la creación con otro número.
        self.spin_vmid.setEnabled(
            estado.pasos[PasoB2.CREAR] not in (EstadoPaso.HECHO, EstadoPaso.OMITIDO)
        )
        self._evaluar_borrado(paso)
        self._ajustar_botones()

    def _ocultar_acciones(self) -> None:
        for b in (
            self.boton_reintentar,
            self.boton_comprobar,
            self.boton_omitir,
            self.boton_borrar,
        ):
            b.hide()
        self.etiqueta_borrado.hide()
        self._condiciones = None
        self._gen_borrado += 1

    # ---------------------------------------------------------------------------------------
    # Acciones tras un fallo (RF-B2.10)
    # ---------------------------------------------------------------------------------------

    def _evaluar_borrado(self, paso: PasoB2) -> None:
        """Lee (solo lecturas) si «Borrar la máquina a medio crear» se puede ofrecer."""
        estado, sol = self._estado, self._sol
        if sol is None or paso not in _PASOS_CON_MAQUINA:
            return
        hay_rastro = (
            estado.vmid_reservado is not None
            or estado.upid is not None
            or estado.pasos[PasoB2.CREAR] == EstadoPaso.INCIERTO
        )
        if not hay_rastro:
            return  # no llegó a enviarse la creación: no hay nada que borrar
        control = self._disp.get(ControlB2.BORRAR)
        if control is not None and not control.habilitado:
            poner_mensaje(self.etiqueta_borrado, texto_estado_control_b2(control), aviso=True)
            return
        self._gen_borrado += 1
        gen = self._gen_borrado

        def _al_terminar(cond: object) -> None:
            if (
                gen == self._gen_borrado
                and not self._cerrado
                and isinstance(cond, CondicionesBorrado)
            ):
                self._tras_condiciones(cond)

        def _al_fallar(_error: ErrorProxLaunch) -> None:
            if gen == self._gen_borrado and not self._cerrado:
                self._tras_condiciones(CondicionesBorrado(False, None, sin_certeza=True))

        self._lanzador.lanzar(
            self._servicio.condiciones_borrado,
            sol,
            estado,
            inv=self._inv,
            al_terminar=_al_terminar,
            al_fallar=_al_fallar,
        )

    def _tras_condiciones(self, cond: CondicionesBorrado) -> None:
        self._condiciones = cond
        if cond.ok:
            self.boton_borrar.show()
            poner_mensaje(self.etiqueta_borrado, None)
            return
        codigo = str(cond.error.codigo) if cond.error is not None else ""
        if cond.sin_certeza or codigo:
            poner_mensaje(
                self.etiqueta_borrado,
                texto_borrado_no_ofrecido(codigo, sin_certeza=cond.sin_certeza),
                aviso=True,
            )

    def _reintentar(self) -> None:
        """«Reintentar» / «Continuar»: reanuda en el primer paso sin resolver.

        Nunca repite un paso hecho. Con el paso 2 sin resolver se puede haber cambiado el VMID
        («reintentar con otro número»).
        """
        sol = self._sol
        if sol is None or self._fase != _Fase.DETENIDO:
            return
        if self._estado.pasos[PasoB2.CREAR] not in (EstadoPaso.HECHO, EstadoPaso.OMITIDO):
            cfg = dataclasses.replace(sol.cfg, vmid=self.spin_vmid.value())
            self._sol = dataclasses.replace(sol, cfg=cfg)
        self._ejecutar()

    def _comprobar_ahora(self) -> None:
        """«Comprobar ahora»: lee la config y reconcilia el paso dudoso. Nunca escribe."""
        sol = self._sol
        if sol is None or self._fase != _Fase.DETENIDO:
            return
        self._fase = _Fase.COMPROBANDO
        self._ocultar_acciones()
        poner_mensaje(self.etiqueta_estado, self.tr("Comprobando en el servidor…"), aviso=True)
        self._ajustar_botones()

        def _al_terminar(estado: object) -> None:
            if self._cerrado:
                return
            if isinstance(estado, EstadoPlantillaImagen):
                self._estado = estado
            self._fin_de_tramo()

        def _al_fallar(error: ErrorProxLaunch) -> None:
            if self._cerrado:
                return
            self._estado.error = error
            self._fin_de_tramo()

        self._lanzador.lanzar(
            self._servicio.comprobar_ahora,
            sol,
            self._estado,
            inv=self._inv,
            al_terminar=_al_terminar,
            al_fallar=_al_fallar,
        )

    def _omitir(self) -> None:
        """«Continuar sin ampliar / sin cloud-init / dejarla como máquina normal» (pasos 3 a 5)."""
        estado = self._estado
        paso = estado.paso_pendiente
        if paso is None or paso not in _PASOS_OMITIBLES or self._fase != _Fase.DETENIDO:
            return
        self._servicio.omitir(estado, paso)
        self._vista = estado
        self._pintar_pasos(estado)
        if estado.completo:
            self._terminar_bien()
        else:
            self._ejecutar()

    def _borrar(self) -> None:
        """«Borrar la máquina a medio crear…»: solo con las condiciones confirmadas y con el
        diálogo de confirmación (nombre y número). Nunca es automático."""
        sol, estado, cond = self._sol, self._estado, self._condiciones
        if sol is None or cond is None or not cond.ok or self._fase != _Fase.DETENIDO:
            return
        nombre = estado.nombre_reservado or sol.cfg.nombre
        vmid = estado.vmid_reservado if estado.vmid_reservado is not None else sol.cfg.vmid
        if not confirmar(
            self,
            self.tr("Borrar la máquina a medio crear"),
            texto_confirmar_borrado(nombre, vmid),
            self.tr("Borrar la máquina"),
            self.tr("Cancelar"),
        ):
            return
        servicio, inv = self._servicio, self._inv
        self._empezar_trabajo()
        poner_mensaje(self.etiqueta_estado, self.tr("Borrando la máquina…"), aviso=True)

        def _trabajo(*, al_cambiar_etapa: Any, al_enviar: Any, cancelado: threading.Event) -> Any:
            del al_cambiar_etapa, al_enviar
            return servicio.borrar_a_medio_crear(sol, estado, cancelado, confirmado=True, inv=inv)

        self._trabajador = self._lanzador.lanzar(
            _trabajo,
            con_contexto=True,
            al_terminar=self._al_terminar_trabajo,
            al_fallar=self._al_fallar_trabajo,
        )

    # ---------------------------------------------------------------------------------------
    # Botones, bloqueo del formulario y cierre
    # ---------------------------------------------------------------------------------------

    def _editables(self) -> list[QWidget]:
        return [
            self.radio_archivo,
            self.radio_url,
            self.radio_importada,
            self.boton_elegir,
            self.campo_url,
            self.casilla_certificados,
            self.combo_importadas,
            self.boton_actualizar_importadas,
            self.campo_suma,
            self.combo_nodo,
            self.combo_storage_import,
            self.combo_storage_destino,
            self.campo_nombre,
            self.spin_vmid,
            self.spin_sockets,
            self.spin_cores,
            self.spin_memoria,
            self.spin_tamano,
            self.combo_firmware,
            self.combo_bridge,
            self.combo_modelo_red,
            self.spin_vlan,
            self.casilla_unidad,
            self.casilla_serie,
            self.casilla_agente,
            self.grupo_cloudinit,
            self.casilla_irreversible,
            self.fila_existente,
            self.casilla_raiz,
        ]

    def _congelar(self, congelar: bool) -> None:
        for w in self._editables():
            w.setEnabled(not congelar)
        if not congelar:
            self._aplicar_disponibilidad()

    def _ajustar_botones(self) -> None:
        fase = self._fase
        self.boton_crear.setVisible(fase in (_Fase.EDITANDO, _Fase.COMPROBANDO))
        if fase == _Fase.EN_CURSO:
            self.boton_cancelar.setText(self.tr("Dejar de esperar"))
            self.boton_cancelar.setEnabled(not self._cancelando)
        elif fase in (_Fase.DETENIDO, _Fase.TERMINADO):
            self.boton_cancelar.setText(self.tr("Cerrar"))
            self.boton_cancelar.setEnabled(True)
        else:
            self.boton_cancelar.setText(self.tr("Cancelar"))
            self.boton_cancelar.setEnabled(True)
        self.boton_cancelar.setDefault(True)
        self.boton_cancelar.setFocus()

    def _al_pulsar_cancelar(self) -> None:
        if self._fase == _Fase.EN_CURSO:
            self.cancelar_trabajo()
        elif self._fase == _Fase.TERMINADO:
            self.accept()
        else:
            self.reject()

    def keyPressEvent(self, evento: QKeyEvent) -> None:
        """Intro en un campo de texto confirma el campo, nunca el botón predeterminado."""
        if evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and isinstance(
            self.focusWidget(), QLineEdit
        ):
            evento.accept()
            return
        super().keyPressEvent(evento)

    def reject(self) -> None:
        """Cerrar con un paso en curso pide confirmación y solo deja de esperar: no borra nada
        (CA-B2.10.6)."""
        if self._fase == _Fase.EN_CURSO:
            if confirmar(
                self,
                self.tr("El asistente está trabajando"),
                texto_cerrar_en_curso_b2(),
                self.tr("Dejar de esperar y cerrar"),
                self.tr("Seguir aquí"),
            ):
                self._cerrar_al_terminar = True
                self.cancelar_trabajo()
            return
        super().reject()

    def done(self, resultado: int) -> None:
        self._cerrado = True
        self._gen_comp += 1
        self._gen_insp += 1
        self._gen_borrado += 1
        self._temporizador.stop()
        self._timer_validar.stop()
        super().done(resultado)
