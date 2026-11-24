"""Formulario de la MV en secciones: General, Firmware, Cómputo, Discos y Red (RF-13 a RF-17).

El formulario es la fuente de la verdad de lo que escribe el usuario: ``configuracion()``
construye un ``ConfiguracionVM`` en cada llamada. Un texto que no es un número se
convierte en 0, un valor que las reglas V-xx rechazan, y así el error aparece junto al
campo sin que el formulario tenga que duplicar reglas.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import ayuda, ayuda_cpu_host
from proxlaunch.interfaz.textos import (
    texto_error,
    texto_estado_opcion,
    texto_motivo_nodo,
    texto_opcion_restablecida,
    texto_problema,
)
from proxlaunch.interfaz.textos_d import (
    etiqueta_experimental_arm,
    texto_arquitectura,
    texto_arquitectura_detectada,
    texto_cambios_arquitectura,
    texto_cpu_arm_sin_listar,
    texto_cpus_no_leidas,
    texto_cpus_ocultas,
    texto_grupo_cpu_personalizada,
    texto_linea_experimental_arm,
    texto_nodo_con_arquitectura,
)
from proxlaunch.interfaz.vistas.campos import (
    FilaCampo,
    etiqueta,
    mensaje,
    poner_mensaje,
)
from proxlaunch.interfaz.vistas.seccion_cloudinit import SeccionCloudInit
from proxlaunch.interfaz.vistas.seccion_firewall import SeccionFirewall
from proxlaunch.interfaz.vistas.seccion_hardware_cluster import SeccionHardwareCluster
from proxlaunch.interfaz.vistas.seccion_red_clon import SeccionRedClon
from proxlaunch.interfaz.vistas.selector_origen import SelectorOrigen
from proxlaunch.interfaz.vistas.tabla_discos import TablaDiscos, entero_o_cero, texto_ausente
from proxlaunch.interfaz.vistas.tabla_redes import TablaRedes
from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    FuenteArquitectura,
    arquitectura_efectiva,
)
from proxlaunch.nucleo.arquitectura.perfil import CambioArquitectura, adaptar_a_arquitectura
from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.cloudinit.disponibilidad import OpcionB
from proxlaunch.nucleo.cloudinit.modelos import (
    ConfigCloudInit,
    InfoCloudInitPlantilla,
    ModoTarjeta,
)
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import LecturaGrupos, ReglaFirewall
from proxlaunch.nucleo.hardware_cluster.modelos import InfoHardwareCluster, ModeloCpu
from proxlaunch.nucleo.modelos.catalogo import ListadoSnippets, PermisosEfectivos, Plantilla
from proxlaunch.nucleo.modelos.cpu import TIPOS_CPU_ARM, TIPOS_CPU_X86, es_cpu_personalizada
from proxlaunch.nucleo.modelos.inventario import Inventario, RedVirtual
from proxlaunch.nucleo.modelos.origen import DetalleClon, TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    ConfiguracionVM,
    ControladorScsi,
    Firmware,
    OrigenSO,
)
from proxlaunch.nucleo.opciones.etiquetas import normalizar_etiquetas
from proxlaunch.nucleo.opciones.modelos import (
    EstadoOpcion,
    EstadoPools,
    OpcionA,
    OpcionC,
    OpcionD,
    OpcionesLote,
    PoolsServidor,
)
from proxlaunch.nucleo.origen.asistente import aplicar_asistente
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.red.modelos import RedClon
from proxlaunch.nucleo.red.redes_nodo import RedesNodo, interseccion_redes
from proxlaunch.nucleo.red.tarjetas import tarjetas_finales
from proxlaunch.nucleo.seleccion_nodo import MotivoNodo, elegir_nodo
from proxlaunch.nucleo.validacion import Problema, Severidad
from proxlaunch.nucleo.valores_defecto import (
    bridge_por_defecto,
    configuracion_por_defecto,
    storage_disco_por_defecto,
)

if TYPE_CHECKING:
    from proxlaunch.nucleo.libvirt.correspondencias import PropuestaLibvirt

# Tipos de CPU fijos de un servidor x86 (la lista vive en el núcleo, RF-D2.11).
TIPOS_CPU = TIPOS_CPU_X86


def gib_a_mib(texto: str) -> int:
    """GiB escritos por el usuario (admite coma o punto decimal) a MiB; inválido -> 0."""
    try:
        valor = float(texto.strip().replace(",", "."))
    except ValueError:
        return 0
    if not math.isfinite(valor):
        return 0
    return round(valor * 1024)


def mib_a_texto_gib(mib: int) -> str:
    """MiB a un texto de GiB sin ceros sobrantes (2048 -> «2», 512 -> «0.5»)."""
    return f"{mib / 1024:g}"


def entero_opcional(texto: str) -> int | None:
    """Entero escrito en un campo opcional: vacío = ``None``; un texto que no es un entero se
    convierte en -1, un valor que la regla V-A01 rechaza (así el error sale junto al campo)."""
    t = texto.strip()
    if not t:
        return None
    try:
        return int(t)
    except ValueError:
        return -1


class _ComboCpu(QComboBox):
    """Desplegable de CPU que avisa al abrirse: entonces se leen los modelos personalizados."""

    se_abre = Signal()

    def showPopup(self) -> None:
        self.se_abre.emit()
        super().showPopup()


class _Transparente(QWidget):
    """Contenedor que no pinta el fondo del QSS: se ve el del grupo, como las demás filas."""


@dataclass
class _GrupoOpcion:
    """Controles de una opción de la fase A que se habilitan o no juntos (RF-A0.3, RF-A0.4)."""

    opcion: OpcionA
    fila: FilaCampo  # donde se escribe la explicación
    controles: list[QWidget]
    no_predeterminado: Callable[[], bool]  # ¿hay un valor que el estado no permite?
    restablecer: Callable[[], None]


class FormularioVM(QWidget):
    """Formulario de creación de una MV con validación en vivo y modo básico/avanzado."""

    cambiado = Signal()  # el usuario cambió algo: hay que revalidar
    nodo_elegido = Signal(str)  # cambio manual de nodo: recargar sus recursos (CA-11.7)
    vmid_confirmado = Signal(int)  # el usuario terminó de escribir un VMID (V-03)
    # Fase C: la ventana lee en un trabajador y responde con ``establecer_grupos_firewall`` y
    # ``establecer_reglas_grupo``.
    pide_grupos_firewall = Signal()  # al activar «Activar el firewall» o pulsar «Recargar»
    pide_reglas_grupo = Signal(str)  # «Ver reglas» (RF-C3.11)
    # Fase D: la ventana lee en un trabajador y responde con ``establecer_cpus``,
    # ``establecer_hardware`` y (tras ``arquitectura_forzada``) ``establecer_arquitecturas``.
    pide_cpus = Signal(object)  # nodos cuyos modelos de CPU hay que leer (RNF-D4)
    pide_mapeos = Signal()  # reemite el de la sección «Hardware del clúster»
    arquitectura_forzada = Signal(str, object)  # (nodo, Arquitectura | None) del selector manual

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._inv: Inventario | None = None
        self._avanzado = False
        self._modo_lote = False
        self._ocupado = False  # evita reentradas al rellenar widgets por código
        self._nodo_cargado = ""
        self._nodo_actual = ""
        self._motivo_nodo: MotivoNodo | None = None
        self._error_nodo: ErrorProxLaunch | None = None
        self._vmid_ocupado: tuple[int, str | None] | None = None
        # Registro de widgets avanzados: (widget, condición extra de visibilidad).
        self._avanzados: list[tuple[QWidget, Callable[[], bool]]] = []
        # Storage de UEFI cargado de un lote o perfil que el nodo no tiene (CA-G04.3).
        self._efi_ausente: str | None = None
        # Configuración (widgets) justo antes de la PRIMERA aplicación del asistente de SO: cada
        # SO se aplica sobre esta base (no se arrastra el hardware del anterior) y de ella sale la
        # lista de cambios. Se descarta al cargar un perfil o lote y al dejar ISO/disco importado.
        self._base_asistente: ConfiguracionVM | None = None
        # Storage de discos recordado para este servidor (RF-O05); None = el de más espacio.
        self._recordado_mv: str | None = None
        # Fase A: disponibilidad de cada opción (privilegio, versión, pools) y avisos por fila.
        self._estados_opciones: dict[OpcionA, EstadoOpcion] = {}
        self._pools = PoolsServidor(EstadoPools.NO_LEIDO)
        self._pool_restablecido: str | None = None  # pool que volvió a «Ninguno» (aviso CL-A15)
        self._notas_forzadas_off = False
        self._texto_estado: dict[int, str] = {}  # id(fila) -> explicación de disponibilidad
        self._texto_validacion: dict[int, str] = {}  # id(fila) -> avisos de validación
        self._grupos_opciones: list[_GrupoOpcion] = []
        # Fase B: disponibilidad de «Esperar la IP» y texto de por qué no se puede marcar.
        self._estados_b: dict[OpcionB, EstadoOpcion] = {}
        # Fase C: disponibilidad (privilegios y versión), capacidades y nodos destino del lote.
        self._estados_c: dict[OpcionC, EstadoOpcion] = {}
        self._caps_c: Capacidades | None = None
        self._nodos_destino: tuple[str, ...] = ()
        # Fase D: arquitectura del nodo efectivo, valores x86 cambiados al pasar a ARM64 y modelos
        # de CPU personalizados leídos por nodo (con los nodos ya pedidos y los que fallaron).
        self._arq = Arquitectura.X86_64
        self._nodo_sincronizado = ""
        self._cambios_arq: tuple[CambioArquitectura, ...] = ()
        self._cpus: dict[str, tuple[ModeloCpu, ...]] = {}
        self._errores_cpu: dict[str, ErrorProxLaunch] = {}
        self._cpus_pedidas: set[str] = set()
        self._estados_d: dict[OpcionD, EstadoOpcion] = {}

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(10)
        self._construir_origen(capa)
        self._construir_general(capa)
        self._construir_firmware(capa)
        self._caja_firmware = self._ultima_caja
        self._construir_computo(capa)
        self._caja_computo = self._ultima_caja
        self._construir_discos(capa)
        self._caja_discos = self._ultima_caja
        self._construir_red(capa)
        self._caja_red = self._ultima_caja
        self._construir_red_clon(capa)
        self._construir_firewall(capa)
        self._construir_hardware_cluster(capa)
        self._construir_cloudinit(capa)
        capa.addStretch(1)
        self._aplicar_modo()
        self._actualizar_total_cpu()

    # --- Construcción -----------------------------------------------------------------

    def _grupo(self, titulo: str, capa: QVBoxLayout) -> QVBoxLayout:
        grupo = QGroupBox(titulo)
        interior = QVBoxLayout(grupo)
        interior.setSpacing(4)
        capa.addWidget(grupo)
        self._ultima_caja = grupo
        return interior

    def _construir_origen(self, capa: QVBoxLayout) -> None:
        """«¿Cómo quieres crear la máquina?» (RF-O01): vacía, ISO, disco existente o plantilla."""
        g = self._grupo(self.tr("Origen del sistema"), capa)
        self.selector_origen = SelectorOrigen()
        self._nota_clon = etiqueta(
            self.tr(
                "El hardware, los discos y la red se copian de la plantilla. Arriba eliges solo "
                "lo que quieres cambiar."
            ),
            secundario=True,
        )
        self._nota_clon.hide()
        self._nota_importar = etiqueta(
            self.tr("El primer disco de la máquina será la copia del disco que elegiste."),
            secundario=True,
        )
        self._nota_importar.hide()
        g.addWidget(self.selector_origen)
        g.addWidget(self._nota_clon)
        self.selector_origen.seleccion_cambiada.connect(self._al_cambiar_origen)
        self.selector_origen.asistente_solicitado.connect(self._al_pedir_asistente)
        self.selector_origen.origen_cambiado.connect(self._al_dejar_origen_con_asistente)

    def _registrar_avanzado(self, w: QWidget, condicion: Callable[[], bool] | None = None) -> None:
        self._avanzados.append((w, condicion or (lambda: True)))

    def _construir_general(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("General"), capa)
        self._caja_general = g.parentWidget()
        self.vmid = QLineEdit()
        self.vmid.setMaximumWidth(140)
        self.fila_vmid = FilaCampo(self.tr("Número de máquina (VMID)"), self.vmid, "vmid")
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText(self.tr("por ejemplo srv-web-01"))
        self.fila_nombre = FilaCampo(self.tr("Nombre"), self.nombre)
        # Selector de nodo (solo en clúster, CA-13.5 y CA-13.6).
        self._radio_auto = QRadioButton(self.tr("Automático"))
        self._radio_manual = QRadioButton(self.tr("Manual"))
        self._radio_auto.setChecked(True)
        self._grupo_nodo = QButtonGroup(self)
        self._grupo_nodo.addButton(self._radio_auto)
        self._grupo_nodo.addButton(self._radio_manual)
        self.combo_nodo = QComboBox()
        self.combo_nodo.setEnabled(False)
        self._texto_motivo = etiqueta("", secundario=True)
        contenedor = _Transparente()
        cn = QVBoxLayout(contenedor)
        cn.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(self._radio_auto)
        fila.addWidget(self._radio_manual)
        fila.addWidget(self.combo_nodo, 1)
        cn.addLayout(fila)
        cn.addWidget(self._texto_motivo)
        self.fila_nodo = FilaCampo(self.tr("Nodo destino"), contenedor, "nodo")
        self.fila_nodo.hide()
        # Fase D (RF-D2.5): selector manual de la arquitectura del servidor, solo en avanzado.
        self.combo_arquitectura = QComboBox()
        self.combo_arquitectura.addItem(self.tr("Detectarla automáticamente"), None)
        self.combo_arquitectura.addItem(
            texto_arquitectura(Arquitectura.X86_64), Arquitectura.X86_64
        )
        self.combo_arquitectura.addItem(
            f"{texto_arquitectura(Arquitectura.AARCH64)} ({etiqueta_experimental_arm()})",
            Arquitectura.AARCH64,
        )
        self.combo_arquitectura.setAccessibleName(self.tr("Arquitectura de este servidor"))
        self._texto_arq = etiqueta("", secundario=True)
        cont_arq = _Transparente()
        ca = QVBoxLayout(cont_arq)
        ca.setContentsMargins(0, 0, 0, 0)
        ca.addWidget(self.combo_arquitectura)
        ca.addWidget(self._texto_arq)
        self.fila_arquitectura = FilaCampo(
            self.tr("Arquitectura de este servidor"), cont_arq, "arquitectura_servidor"
        )
        self._registrar_avanzado(self.fila_arquitectura)
        # Aviso permanente de ARM64 (experimental) y de los valores adaptados (V-D08).
        self._aviso_arq = mensaje(aviso=True)
        for f in (
            self.fila_vmid,
            self.fila_nombre,
            self.fila_nodo,
            self.fila_arquitectura,
            self._aviso_arq,
        ):
            g.addWidget(f)
        self._construir_opciones(g)
        # Conexiones.
        self.vmid.textEdited.connect(self._al_editar_vmid)
        self.vmid.editingFinished.connect(self._al_terminar_vmid)
        self.nombre.textEdited.connect(lambda _t: self._al_editar(self.fila_nombre))
        self.nombre.editingFinished.connect(lambda: self._tocar(self.fila_nombre))
        self._radio_auto.toggled.connect(self._al_cambiar_modo_nodo)
        self.combo_nodo.currentIndexChanged.connect(self._al_elegir_nodo)
        self.combo_arquitectura.currentIndexChanged.connect(self._al_elegir_arquitectura)

    def _casilla(self, nombre: str, ayuda_texto: str, texto: str = "") -> QCheckBox:
        """Casilla con nombre accesible y sugerencia (el texto va en la etiqueta de la fila)."""
        chk = QCheckBox(texto)
        chk.setAccessibleName(nombre)
        chk.setToolTip(ayuda_texto)
        return chk

    def _construir_opciones(self, g: QVBoxLayout) -> None:
        """Opciones de la fase A del paso General: encendido, arranque, notas, etiquetas, pool y
        protección (RF-A1 a RF-A6). Las de arranque (orden, espera) y protección son avanzadas."""
        self.chk_encender = self._casilla(
            self.tr("Encender al terminar"),
            self.tr("Enciende la máquina cuando termina de crearse y de ajustarse."),
        )
        self.fila_encender = FilaCampo(self.tr("Encender al terminar"), self.chk_encender)
        # Fase B (RF-B3.1): «Esperar la IP de cada máquina» y su plazo, junto a «Encender».
        self.chk_esperar_ip = self._casilla(
            self.tr("Esperar la IP de cada máquina"),
            self.tr(
                "Tras encender cada máquina, ProxLaunch pregunta a Proxmox por su IP hasta que "
                "la tenga o se acabe el plazo. Necesita el agente invitado dentro de la máquina."
            ),
            self.tr("Esperar la IP de cada máquina"),
        )
        self.txt_plazo_ip = QLineEdit("120")
        self.txt_plazo_ip.setMaximumWidth(70)
        self.txt_plazo_ip.setAccessibleName(self.tr("Plazo (segundos)"))
        self.txt_plazo_ip.setToolTip(
            self.tr("Segundos que se espera la IP de cada máquina, entre 10 y 1800.")
        )
        self.txt_plazo_ip.setEnabled(False)
        cont_ip = _Transparente()
        ci = QHBoxLayout(cont_ip)
        ci.setContentsMargins(0, 0, 0, 0)
        ci.addWidget(self.chk_esperar_ip)
        ci.addWidget(etiqueta(self.tr("Plazo (segundos)")))
        ci.addWidget(self.txt_plazo_ip)
        ci.addStretch(1)
        self.fila_esperar_ip = FilaCampo(self.tr("Esperar la IP"), cont_ip, "esperar_ip")
        self.chk_arranque_auto = self._casilla(
            self.tr("Arrancar con el servidor"),
            self.tr("La máquina se enciende sola cuando arranca el servidor Proxmox."),
        )
        self.fila_arranque_auto = FilaCampo(
            self.tr("Arrancar con el servidor"), self.chk_arranque_auto
        )
        self.chk_notas_origen = self._casilla(
            self.tr("Añadir notas de origen"),
            self.tr(
                "Escribe en las notas de la máquina que la creó ProxLaunch: versión, fecha, "
                "lote y perfil."
            ),
        )
        self.chk_notas_origen.setChecked(True)
        self.fila_notas_origen = FilaCampo(self.tr("Añadir notas de origen"), self.chk_notas_origen)
        self.chk_notas_usuario = self._casilla(
            self.tr("Incluir mi usuario en las notas"),
            self.tr("Escribe tu usuario de Proxmox en las notas de origen."),
            self.tr("Incluir mi usuario en las notas"),
        )
        self.chk_notas_usuario.setAccessibleDescription(
            self.tr("Cualquiera con acceso a la máquina en Proxmox podrá ver tu usuario.")
        )
        self._aviso_usuario = etiqueta(
            self.tr("Cualquiera con acceso a la máquina en Proxmox podrá ver tu usuario."),
            secundario=True,
        )
        cont_usuario = _Transparente()
        cu = QVBoxLayout(cont_usuario)
        cu.setContentsMargins(0, 0, 0, 0)
        cu.setSpacing(1)
        cu.addWidget(self.chk_notas_usuario)
        cu.addWidget(self._aviso_usuario)
        self.fila_notas_usuario = FilaCampo("", cont_usuario)
        self.txt_notas = QPlainTextEdit()
        self.txt_notas.setAccessibleName(self.tr("Notas"))
        self.txt_notas.setPlaceholderText(
            self.tr("Texto libre para la descripción de la máquina (opcional)")
        )
        self.txt_notas.setTabChangesFocus(True)  # la tecla Tab pasa al campo siguiente
        self.txt_notas.setFixedHeight(84)
        self.fila_notas = FilaCampo(self.tr("Notas"), self.txt_notas)
        self.txt_etiquetas = QLineEdit()
        self.txt_etiquetas.setAccessibleName(self.tr("Etiquetas"))
        self.txt_etiquetas.setPlaceholderText(self.tr("por ejemplo web, produccion"))
        self.txt_etiquetas.setToolTip(
            self.tr(
                "Separadas por comas. Se suman a las etiquetas que ProxLaunch pone siempre. "
                "Solo minúsculas, números, «_», «-», «+» y «.»."
            )
        )
        self.fila_etiquetas = FilaCampo(self.tr("Etiquetas"), self.txt_etiquetas)
        self.combo_pool = QComboBox()
        self.combo_pool.setAccessibleName(self.tr("Pool"))
        self.combo_pool.setToolTip(self.tr("Pool de recursos donde se crea la máquina."))
        self._poblar_pool(None)
        self.fila_pool = FilaCampo(self.tr("Pool"), self.combo_pool)
        # Avanzado: orden y espera del arranque, y protección contra borrado.
        self.txt_orden = QLineEdit()
        self.txt_orden.setMaximumWidth(100)
        self.txt_orden.setAccessibleName(self.tr("Orden de arranque"))
        self.txt_orden.setToolTip(
            self.tr("Número de orden con que arranca respecto a otras máquinas. Vacío = sin orden.")
        )
        self.fila_orden = FilaCampo(self.tr("Orden de arranque"), self.txt_orden)
        self.txt_espera = QLineEdit()
        self.txt_espera.setMaximumWidth(100)
        self.txt_espera.setAccessibleName(self.tr("Espera (s)"))
        self.txt_espera.setToolTip(
            self.tr("Segundos que se espera tras arrancar esta máquina. Vacío = sin espera.")
        )
        self.fila_espera = FilaCampo(self.tr("Espera (s)"), self.txt_espera)
        self.chk_proteger = self._casilla(
            self.tr("Proteger contra borrado"),
            self.tr("Proxmox no dejará eliminar la máquina hasta que quites la protección."),
        )
        self.fila_proteger = FilaCampo(self.tr("Proteger contra borrado"), self.chk_proteger)
        for f in (
            self.fila_encender,
            self.fila_esperar_ip,
            self.fila_arranque_auto,
            self.fila_notas_origen,
            self.fila_notas_usuario,
            self.fila_notas,
            self.fila_etiquetas,
            self.fila_pool,
            self.fila_orden,
            self.fila_espera,
            self.fila_proteger,
        ):
            g.addWidget(f)
        for f in (self.fila_orden, self.fila_espera, self.fila_proteger):
            self._registrar_avanzado(f)
        self._grupos_opciones = [
            _GrupoOpcion(
                OpcionA.ENCENDER,
                self.fila_encender,
                [self.chk_encender],
                self.chk_encender.isChecked,
                lambda: self.chk_encender.setChecked(False),
            ),
            _GrupoOpcion(
                OpcionA.ARRANQUE_AUTO,
                self.fila_arranque_auto,
                [self.chk_arranque_auto],
                self.chk_arranque_auto.isChecked,
                lambda: self.chk_arranque_auto.setChecked(False),
            ),
            _GrupoOpcion(
                OpcionA.ARRANQUE_ORDEN,
                self.fila_orden,
                [self.txt_orden, self.txt_espera],
                lambda: bool(self.txt_orden.text().strip() or self.txt_espera.text().strip()),
                self._vaciar_arranque,
            ),
            _GrupoOpcion(
                OpcionA.NOTAS,
                self.fila_notas_origen,
                [self.chk_notas_origen, self.txt_notas],
                lambda: self.chk_notas_origen.isChecked() or bool(self.txt_notas.toPlainText()),
                self._vaciar_notas,
            ),
            _GrupoOpcion(
                OpcionA.ETIQUETAS,
                self.fila_etiquetas,
                [self.txt_etiquetas],
                lambda: bool(self.txt_etiquetas.text().strip()),
                self.txt_etiquetas.clear,
            ),
            _GrupoOpcion(
                OpcionA.POOL,
                self.fila_pool,
                [self.combo_pool],
                lambda: self.combo_pool.currentData() is not None,
                lambda: self.combo_pool.setCurrentIndex(0),
            ),
            _GrupoOpcion(
                OpcionA.PROTEGER,
                self.fila_proteger,
                [self.chk_proteger],
                self.chk_proteger.isChecked,
                lambda: self.chk_proteger.setChecked(False),
            ),
        ]
        # Orden de tabulación coherente: tras el nodo, las opciones en el orden en que se ven.
        orden = [
            self.combo_nodo,
            self.chk_encender,
            self.chk_esperar_ip,
            self.txt_plazo_ip,
            self.chk_arranque_auto,
            self.chk_notas_origen,
            self.chk_notas_usuario,
            self.txt_notas,
            self.txt_etiquetas,
            self.combo_pool,
            self.txt_orden,
            self.txt_espera,
            self.chk_proteger,
        ]
        for anterior, siguiente in zip(orden, orden[1:], strict=False):
            QWidget.setTabOrder(anterior, siguiente)
        for chk in (
            self.chk_encender,
            self.chk_arranque_auto,
            self.chk_notas_usuario,
            self.chk_proteger,
        ):
            chk.toggled.connect(lambda _m: self._al_editar())
        self.chk_notas_origen.toggled.connect(self._al_cambiar_notas_origen)
        self.chk_encender.toggled.connect(lambda _m: self._actualizar_esperar_ip())
        self.chk_esperar_ip.toggled.connect(self._al_cambiar_esperar_ip)
        self.txt_plazo_ip.textEdited.connect(lambda _t: self._al_editar(self.fila_esperar_ip))
        self.txt_plazo_ip.editingFinished.connect(lambda: self._tocar(self.fila_esperar_ip))
        self.txt_notas.textChanged.connect(lambda: self._al_editar(self.fila_notas))
        self.txt_etiquetas.textEdited.connect(lambda _t: self._al_editar(self.fila_etiquetas))
        self.txt_etiquetas.editingFinished.connect(lambda: self._tocar(self.fila_etiquetas))
        self.combo_pool.currentIndexChanged.connect(lambda _i: self._al_editar(self.fila_pool))
        self.txt_orden.textEdited.connect(lambda _t: self._al_editar(self.fila_orden))
        self.txt_orden.editingFinished.connect(lambda: self._tocar(self.fila_orden))
        self.txt_espera.textEdited.connect(lambda _t: self._al_editar(self.fila_espera))
        self.txt_espera.editingFinished.connect(lambda: self._tocar(self.fila_espera))
        self._actualizar_notas_usuario()

    def _construir_firmware(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("Firmware"), capa)
        self.combo_firmware = QComboBox()
        self.combo_firmware.addItem(self.tr("SeaBIOS (clásico)"), Firmware.SEABIOS)
        self.combo_firmware.addItem(self.tr("UEFI (OVMF)"), Firmware.OVMF)
        self.fila_firmware = FilaCampo(self.tr("Tipo de arranque"), self.combo_firmware, "firmware")
        self.combo_efi = QComboBox()
        self.fila_efi = FilaCampo(
            self.tr("Almacenamiento de UEFI"), self.combo_efi, "almacenamiento"
        )
        self._registrar_avanzado(
            self.fila_efi, lambda: self.combo_firmware.currentData() == Firmware.OVMF
        )
        # TPM y agente de QEMU: los fija el asistente de SO y el avanzado puede dejarlos distintos
        # (CA-O13.8). En básico no se ven, pero su valor es el que se envía.
        self.chk_tpm = QCheckBox()
        self.chk_tpm.setAccessibleName(self.tr("TPM 2.0"))
        self.fila_tpm = FilaCampo(self.tr("TPM 2.0"), self.chk_tpm)
        self.chk_agente = QCheckBox()
        self.chk_agente.setAccessibleName(self.tr("Agente de QEMU"))
        self.fila_agente = FilaCampo(self.tr("Agente de QEMU"), self.chk_agente)
        self._registrar_avanzado(self.fila_tpm)
        self._registrar_avanzado(self.fila_agente)
        g.addWidget(self.fila_firmware)
        g.addWidget(self.fila_efi)
        g.addWidget(self.fila_tpm)
        g.addWidget(self.fila_agente)
        self.chk_tpm.toggled.connect(lambda _m: self._al_editar())
        self.chk_agente.toggled.connect(lambda _m: self._al_editar())
        self.combo_firmware.currentIndexChanged.connect(self._al_cambiar_firmware)
        self.combo_efi.currentIndexChanged.connect(self._al_cambiar_efi)

    def _construir_computo(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("Cómputo"), capa)
        self.combo_sockets = QComboBox()
        for n in range(1, 5):
            self.combo_sockets.addItem(str(n), n)
        self.combo_sockets.setMaximumWidth(80)
        self.fila_sockets = FilaCampo(self.tr("Sockets"), self.combo_sockets, "sockets")
        self.cores = QLineEdit("2")
        self.cores.setMaximumWidth(80)
        self.fila_cores = FilaCampo(self.tr("Núcleos por socket"), self.cores, "cores")
        self._total_cpu = etiqueta("", secundario=True)
        self.combo_cpu = _ComboCpu()
        for t in TIPOS_CPU:
            self.combo_cpu.addItem(t, t)
        self.fila_cpu = FilaCampo(self.tr("Tipo de CPU"), self.combo_cpu, "tipo_cpu")
        self._aviso_cpu = etiqueta(ayuda_cpu_host(), secundario=True)
        self._aviso_cpu.hide()
        # Fase D: por qué no hay CPUs personalizadas (permiso, lectura fallida, modelos ocultos).
        self._aviso_cpu_d = mensaje(aviso=True)
        self.memoria = QLineEdit("2")
        self.memoria.setMaximumWidth(100)
        self.fila_memoria = FilaCampo(self.tr("Memoria (GiB)"), self.memoria, "memoria")
        self.combo_balloon = QComboBox()
        self.combo_balloon.addItem(self.tr("Predeterminado de Proxmox"), None)
        self.combo_balloon.addItem(self.tr("Activado"), True)
        self.combo_balloon.addItem(self.tr("Desactivado"), False)
        self.fila_balloon = FilaCampo(self.tr("Ballooning"), self.combo_balloon, "ballooning")
        self.balloon_min = QLineEdit("1")
        self.balloon_min.setMaximumWidth(100)
        self.fila_balloon_min = FilaCampo(
            self.tr("Memoria mínima (GiB)"), self.balloon_min, "ballooning"
        )
        for f in (
            self.fila_sockets,
            self.fila_cores,
            self._total_cpu,
            self.fila_cpu,
            self._aviso_cpu,
            self._aviso_cpu_d,
            self.fila_memoria,
            self.fila_balloon,
            self.fila_balloon_min,
        ):
            g.addWidget(f)
        self._registrar_avanzado(self.fila_cpu)
        self._registrar_avanzado(self._aviso_cpu, lambda: self.combo_cpu.currentData() == "host")
        self._registrar_avanzado(self._aviso_cpu_d, lambda: bool(self._aviso_cpu_d.text()))
        self._registrar_avanzado(self.fila_balloon)
        self._registrar_avanzado(
            self.fila_balloon_min, lambda: self.combo_balloon.currentData() is True
        )
        self.combo_sockets.currentIndexChanged.connect(self._al_cambiar_cpu)
        self.cores.textEdited.connect(lambda _t: self._al_cambiar_cpu(fila=self.fila_cores))
        self.cores.editingFinished.connect(lambda: self._tocar(self.fila_cores))
        self.combo_cpu.currentIndexChanged.connect(self._al_cambiar_tipo_cpu)
        self.combo_cpu.se_abre.connect(self._pedir_cpus)
        self.memoria.textEdited.connect(lambda _t: self._al_editar(self.fila_memoria))
        self.memoria.editingFinished.connect(lambda: self._tocar(self.fila_memoria))
        self.combo_balloon.currentIndexChanged.connect(self._al_cambiar_balloon)
        self.balloon_min.textEdited.connect(lambda _t: self._al_editar(self.fila_balloon_min))
        self.balloon_min.editingFinished.connect(lambda: self._tocar(self.fila_balloon_min))

    def _construir_discos(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("Discos"), capa)
        self.chk_sin_disco = QCheckBox(self.tr("Sin disco"))
        self.chk_sin_disco.setToolTip(ayuda("sin_disco"))
        self._sin_storage = mensaje(error=True)
        self.combo_ctrl = QComboBox()
        self.combo_ctrl.addItem("virtio-scsi-single", ControladorScsi.VIRTIO_SINGLE)
        self.combo_ctrl.addItem("virtio-scsi-pci", ControladorScsi.VIRTIO_PCI)
        self.fila_ctrl = FilaCampo(self.tr("Controlador SCSI"), self.combo_ctrl, "controlador")
        self.tabla_discos = TablaDiscos()
        self._registrar_avanzado(self.fila_ctrl, lambda: not self.chk_sin_disco.isChecked())
        g.addWidget(self.chk_sin_disco)
        g.addWidget(self._nota_importar)
        g.addWidget(self._sin_storage)
        g.addWidget(self.fila_ctrl)
        g.addWidget(self.tabla_discos)
        self.chk_sin_disco.toggled.connect(self._al_cambiar_sin_disco)
        self.combo_ctrl.currentIndexChanged.connect(self._al_cambiar_controlador)
        self.tabla_discos.cambiado.connect(self._al_cambiar_tabla)
        # Al quitar un disco, cada imagen sigue con su disco (no con su posición).
        self.tabla_discos.disco_quitado.connect(self.selector_origen.al_quitar_disco)

    def _construir_red(self, capa: QVBoxLayout) -> None:
        g = self._grupo(self.tr("Red"), capa)
        self.tabla_redes = TablaRedes()
        g.addWidget(self.tabla_redes)
        self.tabla_redes.cambiado.connect(self._al_cambiar_tabla)

    def _construir_red_clon(self, capa: QVBoxLayout) -> None:
        """«Red de las copias»: solo al clonar una plantilla (RF-C4.1)."""
        self.seccion_red_clon = SeccionRedClon()
        self.seccion_red_clon.hide()
        capa.addWidget(self.seccion_red_clon)
        self.seccion_red_clon.cambiado.connect(self._al_cambiar_red_clon)

    def _construir_firewall(self, capa: QVBoxLayout) -> None:
        """«Firewall de la máquina»: plegada y apagada, con cualquier origen (RF-C3.1)."""
        self.seccion_firewall = SeccionFirewall()
        capa.addWidget(self.seccion_firewall)
        self.seccion_firewall.cambiado.connect(self._al_editar)
        self.seccion_firewall.pide_grupos.connect(self.pide_grupos_firewall)
        self.seccion_firewall.pide_reglas.connect(self.pide_reglas_grupo)

    def _construir_hardware_cluster(self, capa: QVBoxLayout) -> None:
        """«Hardware del clúster»: mapeos PCI/USB, plegada y apagada (RF-D3.2)."""
        self.seccion_hardware = SeccionHardwareCluster()
        capa.addWidget(self.seccion_hardware)
        self.seccion_hardware.cambiado.connect(self._al_editar)
        self.seccion_hardware.pide_mapeos.connect(self.pide_mapeos)

    def _construir_cloudinit(self, capa: QVBoxLayout) -> None:
        """«Configuración inicial (cloud-init)»: solo con origen «Clonar plantilla» (RF-B1.2)."""
        self.seccion_cloudinit = SeccionCloudInit()
        self.seccion_cloudinit.hide()
        capa.addWidget(self.seccion_cloudinit)
        self._caja_cloudinit = self.seccion_cloudinit
        self.seccion_cloudinit.cambiado.connect(self._al_editar)

    # --- Modo básico / avanzado -------------------------------------------------------

    def establecer_modo(self, avanzado: bool) -> None:
        """Cambia solo la visibilidad de los widgets avanzados; no restablece valores."""
        self._avanzado = avanzado
        self.selector_origen.establecer_modo(avanzado)
        self.seccion_cloudinit.establecer_modo(avanzado)
        self.seccion_red_clon.establecer_modo_avanzado(avanzado)
        self._aplicar_modo()

    def _aplicar_modo(self) -> None:
        for w, condicion in self._avanzados:
            w.setVisible(self._avanzado and condicion())
        self.tabla_discos.establecer_avanzado(self._avanzado)
        self.tabla_redes.establecer_avanzado(self._avanzado)

    # --- Inventario y valores por defecto ---------------------------------------------

    def establecer_inventario(self, inv: Inventario, *, reiniciar: bool = False) -> None:
        """Carga el inventario descubierto.

        La primera vez (o con ``reiniciar``) rellena los valores por defecto de la sección
        5; en una actualización conserva lo que el usuario ya escribió (CA-03.3).
        """
        primera = self._inv is None or reiniciar
        if reiniciar:
            self.limpiar_secretos()  # otro servidor: la contraseña no se arrastra
            self._reiniciar_fase_d()
        self._inv = inv
        self._ocupado = True
        try:
            self._llenar_combo_nodos()
            es_cluster = inv.topologia.es_cluster
            self.fila_nodo.setVisible(es_cluster and not self._modo_lote)
            if primera:
                nodo, motivo, error = self._calcular_nodo(requerido_gib=32)
                nodo_inicial = nodo or next(
                    (n.nombre for n in inv.topologia.nodos if n.en_linea), ""
                )
                storage_inicial = storage_disco_por_defecto(
                    list(inv.storages.get(nodo_inicial, ())), self._recordado_mv
                )
                cfg = configuracion_por_defecto(
                    inv.proximo_vmid,
                    "",
                    nodo_inicial,
                    storage_inicial,
                    bridge_por_defecto(list(inv.bridges.get(nodo_inicial, ()))),
                )
                if storage_inicial is None:
                    cfg.con_disco = False  # CA-11.9: sin almacenamiento solo se puede «Sin disco»
                self._aplicar_configuracion_interna(cfg, motivo, error)
            else:
                if not self.fila_vmid.tocado:
                    self.vmid.setText(str(inv.proximo_vmid))
                self._nodo_cargado = ""  # fuerza la recarga de recursos del nodo
                self._nodo_sincronizado = ""
                self._actualizar_nodo()
        finally:
            self._ocupado = False
        self._aplicar_modo()
        self.cambiado.emit()

    def establecer_storage_recordado(self, storage: str | None) -> None:
        """Storage de discos recordado del servidor: es el de partida de los discos (RF-O05)."""
        self._recordado_mv = storage
        self.tabla_discos.establecer_storage_recordado(storage)

    def usar_storage_mv(self, storage: str) -> None:
        """El usuario eligió el storage de discos de este servidor: los discos que usaban el de
        partida pasan a él y los nuevos lo usan (RF-O05)."""
        inv = self._inv
        anterior = None
        if inv is not None:
            anterior = storage_disco_por_defecto(
                list(inv.storages.get(self._nodo_actual, ())), self._recordado_mv
            )
        self.establecer_storage_recordado(storage)
        self.tabla_discos.reemplazar_storage(anterior, storage)

    def aplicar_configuracion(self, cfg: ConfiguracionVM) -> None:
        """Rellena el formulario con una configuración (pruebas y «Crear otra»)."""
        self._base_asistente = None
        self._ocupado = True
        try:
            self._aplicar_configuracion_interna(cfg, None, None)
        finally:
            self._ocupado = False
        self._aplicar_modo()
        self.cambiado.emit()

    def aplicar_hardware(
        self,
        cfg: ConfiguracionVM,
        *,
        origen: bool = True,
        asistente: bool = False,
        conservar_fase_c: bool = False,
        conservar_fase_d: bool = False,
    ) -> None:
        """Aplica SOLO el hardware de ``cfg`` (perfil de máquina o lote guardado) y sus opciones.

        Las opciones de la fase A (encender, notas, etiquetas, pool, arranque, protección) se
        vuelcan con el resto: un perfil trae las de la configuración actual con «Encender» en su
        valor por defecto y «Arrancar con el servidor» del perfil; un lote guardado, las suyas.
        No toca el nombre, el VMID, el nodo ni sus marcas de «tocado». Un almacenamiento o una
        red que el nodo no tiene se muestran como «x (no existe)» con error, nunca se sustituyen
        en silencio (CA-G04.3); el usuario debe elegir otro. Con ``origen`` también carga el
        origen del SO de ``cfg`` y su detalle (un lote guardado, un perfil con origen sugerido).
        Con ``asistente`` (perfil con ``tipo_so``) se aplica además, una vez, el asistente de SO
        sobre lo cargado; un lote guardado ya trae lo que el usuario dejó y no se toca.
        Con ``conservar_fase_c`` (perfiles: no guardan red del clon ni firewall, RF-C6.2) no se
        tocan esas dos secciones; sin él (lote guardado) se cargan las de ``cfg``.
        Con ``conservar_fase_d`` (perfiles: no guardan mapeos, MAC ni imágenes, CA-D6.2.2) no se
        toca el hardware del clúster; si el nodo es ARM64, los valores x86 del perfil se adaptan
        y se avisa (RF-D2.10).
        """
        self._base_asistente = None
        self._ocupado = True
        try:
            if origen:
                self.selector_origen.aplicar(cfg)
            self.combo_firmware.setCurrentIndex(max(self.combo_firmware.findData(cfg.firmware), 0))
            self.chk_tpm.setChecked(cfg.tpm)
            self.chk_agente.setChecked(cfg.agente_qemu)
            self.combo_sockets.setCurrentIndex(max(self.combo_sockets.findData(cfg.sockets), 0))
            self.cores.setText(str(cfg.cores))
            self._poblar_cpu(cfg.tipo_cpu)
            self.memoria.setText(mib_a_texto_gib(cfg.memoria_mib))
            if cfg.ballooning is None:
                self.combo_balloon.setCurrentIndex(0)
            else:
                self.combo_balloon.setCurrentIndex(1 if cfg.ballooning.activo else 2)
                if cfg.ballooning.activo:
                    self.balloon_min.setText(mib_a_texto_gib(cfg.ballooning.minimo_mib))
            self.chk_sin_disco.setChecked(not cfg.con_disco)
            self.combo_ctrl.setCurrentIndex(max(self.combo_ctrl.findData(cfg.controlador_scsi), 0))
            self.tabla_discos.establecer_controlador(cfg.controlador_scsi)
            self.tabla_discos.establecer_discos(cfg.discos, conservar_ausentes=True)
            self.tabla_redes.establecer_redes(cfg.redes, conservar_ausentes=True)
            self._escribir_opciones(cfg, fase_c=not conservar_fase_c)
            if not conservar_fase_d:
                self.seccion_hardware.establecer_valor(cfg.hardware_cluster)
            self._efi_ausente = None
            self._poblar_efi(cfg.storage_efi, conservar_ausente=True)
            self._actualizar_total_cpu()
            self._actualizar_sin_disco()
            self._actualizar_nodo()
            self._avisar_ausentes()
            self._actualizar_para_origen()
            # Valores x86 de un perfil o lote guardado hacia un nodo ARM64 (RF-D2.10).
            self._sincronizar_arquitectura(adaptar=True, nueva=True)
            self._pedir_cpus_cargadas()
            if (
                asistente
                and origen
                and cfg.tipo_so is not None
                and cfg.origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO)
            ):
                self._escribir_asistente(cfg.tipo_so, solo_bus=False)
        finally:
            self._ocupado = False
        self._aplicar_modo()
        self.cambiado.emit()

    def _avisar_ausentes(self) -> None:
        """Avisa de cada valor cargado que el nodo actual no tiene (siguen marcados como error)."""
        nodo = self._nodo_actual
        self.tabla_discos.mostrar_aviso_nodo(
            "\n".join(
                self.tr(
                    "El almacenamiento «{recurso}» no existe en el nodo «{nodo}». Elige otro."
                ).format(recurso=sid, nodo=nodo)
                for sid in self.tabla_discos.valores_ausentes()
            )
        )
        self.tabla_redes.mostrar_aviso_nodo(
            "\n".join(
                self.tr("La red «{recurso}» no existe en el nodo «{nodo}». Elige otra.").format(
                    recurso=b, nodo=nodo
                )
                for b in self.tabla_redes.valores_ausentes()
            )
        )
        self.fila_efi.mostrar_aviso(
            self.tr(
                "El almacenamiento de UEFI «{recurso}» no existe en el nodo «{nodo}». Elige otro."
            ).format(recurso=self._efi_ausente, nodo=nodo)
            if self._efi_ausente
            else None
        )

    def _aplicar_configuracion_interna(
        self, cfg: ConfiguracionVM, motivo: MotivoNodo | None, error: ErrorProxLaunch | None
    ) -> None:
        self.vmid.setText(str(cfg.vmid))
        self.nombre.setText(cfg.nombre)
        self.selector_origen.aplicar(cfg)
        self.combo_firmware.setCurrentIndex(max(self.combo_firmware.findData(cfg.firmware), 0))
        self.chk_tpm.setChecked(cfg.tpm)
        self.chk_agente.setChecked(cfg.agente_qemu)
        self.combo_sockets.setCurrentIndex(max(self.combo_sockets.findData(cfg.sockets), 0))
        self.cores.setText(str(cfg.cores))
        self._poblar_cpu(cfg.tipo_cpu)
        self.memoria.setText(mib_a_texto_gib(cfg.memoria_mib))
        if cfg.ballooning is None:
            self.combo_balloon.setCurrentIndex(0)
        else:
            self.combo_balloon.setCurrentIndex(1 if cfg.ballooning.activo else 2)
            if cfg.ballooning.activo:
                self.balloon_min.setText(mib_a_texto_gib(cfg.ballooning.minimo_mib))
        self.chk_sin_disco.setChecked(not cfg.con_disco)
        self.combo_ctrl.setCurrentIndex(max(self.combo_ctrl.findData(cfg.controlador_scsi), 0))
        self.tabla_discos.establecer_controlador(cfg.controlador_scsi)
        # Recursos del nodo y filas de las tablas.
        self._nodo_actual = cfg.nodo
        self._motivo_nodo, self._error_nodo = motivo, error
        self._cargar_recursos_nodo(cfg.nodo)
        self.tabla_discos.establecer_discos(cfg.discos)
        self.tabla_redes.establecer_redes(cfg.redes)
        self._escribir_opciones(cfg)
        self.seccion_hardware.establecer_valor(cfg.hardware_cluster)
        self._poblar_efi(cfg.storage_efi)
        self._refrescar_etiqueta_nodo()
        self._actualizar_total_cpu()
        self._actualizar_sin_disco()
        self._actualizar_para_origen()
        self._nodo_sincronizado = cfg.nodo
        self._sincronizar_arquitectura(adaptar=True, nueva=True)
        self._pedir_cpus_cargadas()

    # --- Lectura ----------------------------------------------------------------------

    def configuracion(self) -> ConfiguracionVM:
        """Construye la configuración con lo que hay en los widgets.

        Incluye el origen del SO y su detalle. El asistente de SO se aplicó una vez a los widgets
        al elegir el sistema (``_escribir_asistente``): aquí se lee lo que muestran (CA-O13.8).
        """
        return self.selector_origen.completar(self._configuracion_base())

    def _configuracion_base(self) -> ConfiguracionVM:
        nodo = self.nodo_efectivo()
        balloon_estado = self.combo_balloon.currentData()
        ballooning: Ballooning | None
        if balloon_estado is None:
            ballooning = None
        elif balloon_estado:
            ballooning = Ballooning(True, gib_a_mib(self.balloon_min.text()))
        else:
            ballooning = Ballooning(False, 0)
        return ConfiguracionVM(
            vmid=entero_o_cero(self.vmid.text()),
            nombre=self.nombre.text().strip(),
            nodo=nodo,
            firmware=Firmware(self.combo_firmware.currentData()),
            tpm=self.chk_tpm.isChecked(),
            agente_qemu=self.chk_agente.isChecked(),
            storage_efi=self.combo_efi.currentData() or None,
            sockets=self.combo_sockets.currentData(),
            cores=entero_o_cero(self.cores.text()),
            tipo_cpu=self.combo_cpu.currentData(),
            memoria_mib=gib_a_mib(self.memoria.text()),
            ballooning=ballooning,
            con_disco=not self.chk_sin_disco.isChecked(),
            discos=self.tabla_discos.discos(),
            controlador_scsi=ControladorScsi(self.combo_ctrl.currentData()),
            redes=self.tabla_redes.redes(),
            encender=self.chk_encender.isChecked(),
            arranque_auto=self.chk_arranque_auto.isChecked(),
            arranque_orden=entero_opcional(self.txt_orden.text()),
            arranque_espera=entero_opcional(self.txt_espera.text()),
            notas_origen=self.chk_notas_origen.isChecked(),
            notas_usuario=self.chk_notas_usuario.isChecked(),
            notas=self.txt_notas.toPlainText(),
            etiquetas_usuario=normalizar_etiquetas(self.txt_etiquetas.text()),
            pool=cast("str | None", self.combo_pool.currentData()),
            proteger=self.chk_proteger.isChecked(),
            cloudinit=self._cloudinit_actual(),
            esperar_ip=self.chk_esperar_ip.isChecked(),
            plazo_ip_s=self._plazo_ip(),
            red_clon=self._red_clon_actual(),
            firewall=self.seccion_firewall.firewall(),
            hardware_cluster=self.seccion_hardware.valor(),
        )

    def _red_clon_actual(self) -> RedClon | None:
        """La red del clon solo existe al clonar una plantilla (V-C51); si no, no se envía."""
        if self.selector_origen.origen != OrigenSO.CLONAR_PLANTILLA:
            return None
        return self.seccion_red_clon.red_clon()

    def _cloudinit_actual(self) -> ConfigCloudInit | None:
        """Cloud-init solo existe al clonar una plantilla; con otro origen no se envía (V-B39)."""
        if self.selector_origen.origen != OrigenSO.CLONAR_PLANTILLA:
            return None
        return self.seccion_cloudinit.configuracion()

    def _plazo_ip(self) -> int:
        """Plazo escrito. Con la casilla marcada un valor que no es número da un valor que V-B61
        rechaza (el error sale junto al campo); sin marcar, uno inválido vuelve a 120."""
        texto = self.txt_plazo_ip.text().strip()
        try:
            valor = int(texto)
        except ValueError:
            valor = -1 if texto else 0
        if not self.chk_esperar_ip.isChecked() and not 10 <= valor <= 1800:
            return 120
        return valor

    # --- Opciones de la fase A -------------------------------------------------------------

    def _escribir_opciones(self, cfg: ConfiguracionVM, *, fase_c: bool = True) -> None:
        """Vuelca en los widgets las opciones de la fase A de ``cfg`` y aplica la disponibilidad.

        Con ``fase_c`` ``False`` no toca el firewall ni la red del clon (perfiles).
        """
        previo, self._ocupado = self._ocupado, True
        try:
            self.txt_orden.setText("" if cfg.arranque_orden is None else str(cfg.arranque_orden))
            self.txt_espera.setText("" if cfg.arranque_espera is None else str(cfg.arranque_espera))
            self._escribir_opciones_lote(
                OpcionesLote(
                    encender=cfg.encender,
                    arranque_auto=cfg.arranque_auto,
                    notas=cfg.notas,
                    etiquetas_usuario=tuple(cfg.etiquetas_usuario),
                    pool=cfg.pool,
                    proteger=cfg.proteger,
                    notas_origen=cfg.notas_origen,
                    notas_usuario=cfg.notas_usuario,
                    cloudinit=cfg.cloudinit,
                    esperar_ip=cfg.esperar_ip,
                    plazo_ip_s=cfg.plazo_ip_s,
                    firewall=cfg.firewall,
                    red_clon=cfg.red_clon,
                ),
                fase_c=fase_c,
            )
        finally:
            self._ocupado = previo

    def _escribir_opciones_lote(self, o: OpcionesLote, *, fase_c: bool = True) -> None:
        self.chk_encender.setChecked(o.encender)
        self.chk_arranque_auto.setChecked(o.arranque_auto)
        self.chk_notas_origen.setChecked(o.notas_origen)
        self.chk_notas_usuario.setChecked(o.notas_usuario)
        self.txt_notas.setPlainText(o.notas)
        self.txt_etiquetas.setText(", ".join(o.etiquetas_usuario))
        self._poblar_pool(o.pool)
        self.chk_proteger.setChecked(o.proteger)
        # Fase B: cloud-init (sin contraseña, que nunca se guarda) y espera de IP.
        self.seccion_cloudinit.aplicar(o.cloudinit)
        self.chk_esperar_ip.setChecked(o.esperar_ip)
        self.txt_plazo_ip.setText(str(o.plazo_ip_s))
        if fase_c:
            # Fase C: firewall de la máquina y red del clon (``None`` = apagados).
            self.seccion_firewall.aplicar(o.firewall)
            self.seccion_red_clon.aplicar(o.red_clon)
        self._notas_forzadas_off = False
        self._actualizar_notas_usuario()
        self._reaplicar_disponibilidad()
        self._actualizar_esperar_ip()

    def aplicar_opciones_lote(self, opciones: OpcionesLote) -> None:
        """Rellena las opciones de lote (un lote por filas guardado trae las suyas)."""
        self._ocupado = True
        try:
            self._escribir_opciones_lote(opciones)
        finally:
            self._ocupado = False
        self.cambiado.emit()

    def _vaciar_arranque(self) -> None:
        self.txt_orden.clear()
        self.txt_espera.clear()

    def _vaciar_notas(self) -> None:
        self.chk_notas_origen.setChecked(False)
        self.chk_notas_usuario.setChecked(False)
        self.txt_notas.clear()
        self._notas_forzadas_off = True

    # --- Fase B: esperar la IP y configuración inicial -----------------------------------

    def _al_cambiar_esperar_ip(self, marcada: bool) -> None:
        self.txt_plazo_ip.setEnabled(marcada and self.chk_esperar_ip.isEnabled())
        self.seccion_cloudinit.establecer_esperar_ip(marcada)
        self._al_editar()

    def _actualizar_esperar_ip(self) -> None:
        """«Esperar la IP» solo se puede marcar con «Encender al terminar» y con el privilegio del
        agente (RF-B3.1, V-B60, V-B63). Si deja de poderse, se desmarca y se explica por qué."""
        estado = self._estados_b.get(OpcionB.ESPERAR_IP)
        sin_permiso = estado is not None and estado.disponibilidad == Disponibilidad.NO
        sin_encender = not self.chk_encender.isChecked()
        if estado is not None and sin_permiso:
            texto = texto_estado_opcion(estado)
        elif sin_encender:
            texto = texto_problema(Problema("esperar_ip", "V-B60", Severidad.ERROR, {}))
        else:
            texto = texto_estado_opcion(estado) if estado is not None else ""
        libre = not sin_permiso and not sin_encender
        previo, self._ocupado = self._ocupado, True
        cambio = False
        try:
            if not libre and self.chk_esperar_ip.isChecked():
                self.chk_esperar_ip.setChecked(False)
                texto = texto_opcion_restablecida(OpcionB.ESPERAR_IP.value, texto)
                cambio = True
            self.chk_esperar_ip.setEnabled(libre)
            self.txt_plazo_ip.setEnabled(libre and self.chk_esperar_ip.isChecked())
            self.chk_esperar_ip.setAccessibleDescription(texto)
            self.seccion_cloudinit.establecer_esperar_ip(self.chk_esperar_ip.isChecked())
        finally:
            self._ocupado = previo
        self._texto_estado[id(self.fila_esperar_ip)] = texto
        self._refrescar_aviso(self.fila_esperar_ip)
        if cambio and not previo:
            self.cambiado.emit()

    def storages_snippets(self) -> tuple[str, ...]:
        """Ids de los almacenamientos del nodo destino con contenido «snippets» (B4)."""
        inv = self._inv
        if inv is None:
            return ()
        return tuple(
            s.id
            for s in inv.storages_todos.get(self.nodo_efectivo(), ())
            if s.activo and "snippets" in s.contenido
        )

    def hay_storage_snippets(self) -> bool:
        """¿El nodo destino tiene algún almacenamiento activo con contenido «snippets»?"""
        return bool(self.storages_snippets())

    def almacen_snippets(self) -> str | None:
        """Almacén de snippets para la guía de permisos (B3): el del primer script elegido en la
        sección de cloud-init y, si no hay ninguno, el primero del nodo destino; ``None`` si el
        inventario no tiene ninguno."""
        ids = self.storages_snippets()
        if not ids:
            return None
        for sel in self.seccion_cloudinit.selectores_snippet.values():
            valor = sel.valor()
            almacen = valor.partition(":")[0] if valor and ":" in valor else ""
            if almacen in ids:
                return almacen
        return ids[0]

    def _listados_snippets(self) -> tuple[list[ListadoSnippets], bool]:
        """Listados de snippets del nodo destino que ya trae el catálogo, y si falta alguno por
        leer (DT-B11: ``CatalogoServidor.snippets_en``)."""
        inv = self._inv
        catalogo = inv.catalogo if inv is not None else None
        nodo = self.nodo_efectivo()
        listados: list[ListadoSnippets] = []
        pendientes = False
        for storage in self.storages_snippets():
            listado = catalogo.snippets_en(nodo, storage) if catalogo is not None else None
            if listado is None:
                pendientes = True
            else:
                listados.append(listado)
        return listados, pendientes

    def establecer_info_cloudinit(
        self,
        info: InfoCloudInitPlantilla | None,
        disponibilidad: Mapping[OpcionB, EstadoOpcion],
    ) -> None:
        """Lo que dice la plantilla elegida de cloud-init y qué opciones de la fase B están
        disponibles (privilegios, versión, almacenamiento de snippets).

        ``info`` ``None`` = plantilla sin leer o desconocida. Reparte el estado entre la sección
        de cloud-init y la casilla «Esperar la IP», y refresca la lista de scripts con lo que
        ya trae el catálogo del inventario. Es barato: se puede llamar en cada revalidación.
        """
        self._estados_b = dict(disponibilidad)
        listados, pendientes = self._listados_snippets()
        self.seccion_cloudinit.establecer_snippets(listados, pendientes=pendientes)
        self.seccion_cloudinit.establecer_info(info, disponibilidad)
        self._actualizar_esperar_ip()
        self._sincronizar_fase_c()

    # --- Fase C: red del clon, firewall y VNets ---------------------------------------------

    def establecer_disponibilidad_c(
        self, estados: Mapping[OpcionC, EstadoOpcion], caps: Capacidades | None = None
    ) -> None:
        """Habilita o deshabilita las opciones de la fase C según privilegios y versión
        (``disponibilidad_fase_c``) y guarda las capacidades para el texto de V-C13. Es barato:
        se puede llamar en cada revalidación (ignora lo que no cambió)."""
        if dict(estados) == self._estados_c and caps == self._caps_c:
            return
        cambio_caps = caps != self._caps_c
        self._estados_c = dict(estados)
        self._caps_c = caps
        self.seccion_hardware.establecer_driver_keep(
            caps is not None and caps.tiene(Funcion.MAPEO_DRIVER_KEEP)
        )
        self.seccion_red_clon.establecer_disponibilidad(estados.get(OpcionC.RED_CLON))
        self.seccion_firewall.establecer_disponibilidad(
            estados.get(OpcionC.FIREWALL), estados.get(OpcionC.FIREWALL_GENERAL)
        )
        if cambio_caps and self._inv is not None and self._nodo_actual:
            self._ocupado = True
            try:
                self._cargar_recursos_nodo(self._nodo_actual)
            finally:
                self._ocupado = False

    def establecer_grupos_firewall(self, lectura: LecturaGrupos) -> None:
        """Resultado de leer los grupos de seguridad (lo pidió ``pide_grupos_firewall``)."""
        self.seccion_firewall.establecer_grupos(lectura)

    def establecer_reglas_grupo(
        self,
        grupo: str,
        reglas: tuple[ReglaFirewall, ...] | None,
        error: ErrorProxLaunch | None,
    ) -> None:
        """Contenido de un grupo (lo pidió ``pide_reglas_grupo``); solo lectura."""
        self.seccion_firewall.establecer_reglas(grupo, reglas, error)

    # --- Fase D: arquitectura, CPU personalizadas y hardware del clúster -------------------

    @property
    def arquitectura_actual(self) -> Arquitectura:
        """Arquitectura del nodo efectivo (x86 si no se pudo leer, P-D3)."""
        return self._arq

    @property
    def cambios_arquitectura(self) -> tuple[CambioArquitectura, ...]:
        """Valores x86 que se cambiaron al pasar a un nodo ARM64 (V-D08), para el Resumen."""
        return self._cambios_arq

    def _nombre_nodo(self, nodo: str) -> str:
        """El nodo con la marca «(ARM64, experimental)» si lo es (CA-D2.12.1)."""
        if self._inv is None:
            return nodo
        return texto_nodo_con_arquitectura(nodo, arquitectura_efectiva(self._inv, nodo))

    def establecer_arquitecturas(self, inv: Inventario) -> None:
        """Arquitecturas por nodo (detectadas o elegidas a mano): ajusta los desplegables
        (CA-D2.7.1) y aplica V-D08 en vivo si el nodo efectivo es ARM64. ``inv`` puede ser el
        mismo inventario o uno nuevo con ``arquitecturas`` distintas; el resto no se toca."""
        if self._inv is None:
            return
        if inv is not self._inv:
            self._inv.arquitecturas = dict(inv.arquitecturas)
        self._ocupado = True
        try:
            self._llenar_combo_nodos()
            self._sincronizar_arquitectura(adaptar=True)
            self._pedir_cpus_cargadas()
        finally:
            self._ocupado = False
        self._refrescar_etiqueta_nodo()
        self.cambiado.emit()

    def _sincronizar_arquitectura(self, *, adaptar: bool = False, nueva: bool = False) -> None:
        """Ajusta el formulario a la arquitectura del nodo efectivo: tipos de CPU, SeaBIOS (no
        existe en ARM64), selector manual y, con ``adaptar``, los valores x86 ya escritos
        (``adaptar_a_arquitectura``, fuente única con el planificador). ``nueva``: se acaba de
        cargar otra configuración y la lista de cambios anterior ya no vale."""
        inv = self._inv
        arq = (
            arquitectura_efectiva(inv, self._nodo_actual)
            if inv is not None and self._nodo_actual
            else Arquitectura.X86_64
        )
        previa = self._arq
        self._arq = arq
        previo, self._ocupado = self._ocupado, True
        try:
            if nueva or arq != previa:
                self._cambios_arq = ()
            modelo = cast(QStandardItemModel, self.combo_firmware.model())
            fila_seabios = self.combo_firmware.findData(Firmware.SEABIOS)
            item = modelo.item(fila_seabios)
            if item is not None:
                item.setEnabled(arq != Arquitectura.AARCH64)
            self._poblar_cpu(None)
            if adaptar and arq == Arquitectura.AARCH64:
                self._adaptar_a_arm()
            self.seccion_hardware.establecer_arquitectura(arq)
            self._refrescar_arquitectura()
        finally:
            self._ocupado = previo
        self._aplicar_modo()

    def _adaptar_a_arm(self) -> None:
        """Cambia los valores x86 del formulario a su equivalente ARM64 y recuerda la lista."""
        if self.selector_origen.origen == OrigenSO.CLONAR_PLANTILLA:
            return  # un clon hereda el hardware de la plantilla
        cfg = self._configuracion_base()
        cpus = self._cpus.get(self._nodo_actual)
        adaptada, cambios = adaptar_a_arquitectura(cfg, self._arq, cpus_nodo=cpus)
        if not cambios:
            return
        self._cambios_arq = cambios
        idx = self.combo_firmware.findData(adaptada.firmware)
        self.combo_firmware.setCurrentIndex(max(idx, 0))
        self._poblar_cpu(adaptada.tipo_cpu)
        self.tabla_discos.establecer_discos(adaptada.discos, conservar_ausentes=True)
        self.tabla_redes.establecer_redes(adaptada.redes, conservar_ausentes=True)

    def _refrescar_arquitectura(self) -> None:
        """Selector manual, texto de lo detectado y aviso de ARM64 (experimental, V-D08)."""
        inv = self._inv
        nodo = self._nodo_actual
        info = inv.arquitecturas.get(nodo) if inv is not None and nodo else None
        forzada = info is not None and info.fuente == FuenteArquitectura.MANUAL
        self.combo_arquitectura.blockSignals(True)
        self.combo_arquitectura.setCurrentIndex(
            max(self.combo_arquitectura.findData(self._arq), 0) if forzada else 0
        )
        self.combo_arquitectura.blockSignals(False)
        self.combo_arquitectura.setEnabled(bool(nodo))
        self._texto_arq.setText(
            texto_arquitectura_detectada(
                self._arq, info.fuente.value if info is not None else "", forzada
            )
        )
        lineas: list[str] = []
        if self._arq == Arquitectura.AARCH64:
            lineas.append(texto_linea_experimental_arm())
        if self._cambios_arq:
            lineas.append(texto_cambios_arquitectura(self._cambios_arq))
        poner_mensaje(self._aviso_arq, "\n".join(lineas) or None, aviso=True)

    def _al_elegir_arquitectura(self, _i: int) -> None:
        """El usuario fijó la arquitectura a mano: la ventana la guarda en el inventario y
        vuelve a llamar a ``establecer_arquitecturas``."""
        if self._ocupado or not self._nodo_actual:
            return
        valor = self.combo_arquitectura.currentData()
        try:
            arq = Arquitectura(valor) if valor else None  # Qt devuelve el texto del valor
        except ValueError:
            arq = None
        self.arquitectura_forzada.emit(self._nodo_actual, arq)

    def _reiniciar_fase_d(self) -> None:
        """Otro servidor: se olvidan los modelos de CPU y los mapeos leídos del anterior."""
        self._cpus.clear()
        self._errores_cpu.clear()
        self._cpus_pedidas.clear()
        self._cambios_arq = ()
        self._nodo_sincronizado = ""
        self.seccion_hardware.reiniciar()

    # CPU personalizadas ----------------------------------------------------------------------

    def _nodos_de_cpu(self) -> tuple[str, ...]:
        """Nodos donde se creará la máquina: los del lote o, si no hay, el nodo efectivo."""
        if self._nodos_destino:
            return self._nodos_destino
        return (self._nodo_actual,) if self._nodo_actual else ()

    def _cpu_personalizada_permitida(self) -> bool:
        estado = self._estados_d.get(OpcionD.CPU_PERSONALIZADA)
        return estado is None or estado.disponibilidad != Disponibilidad.NO

    def _pedir_cpus(self) -> None:
        """Pide a la ventana los modelos de CPU de los nodos aún no leídos (≤ 1 lectura por nodo
        y conexión; ninguna sin nodos elegidos ni sin permiso)."""
        if not self._cpu_personalizada_permitida() or self._inv is None:
            return
        pendientes = tuple(n for n in self._nodos_de_cpu() if n not in self._cpus_pedidas)
        if not pendientes:
            return
        self._cpus_pedidas.update(pendientes)
        self.pide_cpus.emit(pendientes)

    def _pedir_cpus_cargadas(self) -> None:
        """Una CPU personalizada cargada de un perfil o lote pide ya los modelos del nodo, para
        poder comprobar que existe (V-D61)."""
        if es_cpu_personalizada(str(self.combo_cpu.currentData() or "")):
            self._pedir_cpus()

    def establecer_cpus(
        self,
        cpus: Mapping[str, Sequence[ModeloCpu]],
        errores: Mapping[str, ErrorProxLaunch],
    ) -> None:
        """Modelos de CPU leídos por nodo (y los nodos cuya lectura falló, V-D62). El desplegable
        gana el grupo «Personalizados del clúster» con los que existen en todos los nodos."""
        for nodo, modelos in cpus.items():
            self._cpus[nodo] = tuple(modelos)
            self._errores_cpu.pop(nodo, None)
        for nodo, error in errores.items():
            self._errores_cpu[nodo] = error
            self._cpus.pop(nodo, None)
        self._ocupado = True
        try:
            self._poblar_cpu(None)
        finally:
            self._ocupado = False
        self._aplicar_modo()
        self.cambiado.emit()

    def _personalizados_comunes(self) -> tuple[tuple[str, ...], int]:
        """Modelos personalizados presentes en todos los nodos leídos y cuántos se ocultan por
        faltar en alguno (CA-D3.6.2)."""
        if not self._cpu_personalizada_permitida():
            return (), 0
        if (
            self._arq == Arquitectura.AARCH64
            and self._caps_c is not None
            and not self._caps_c.tiene(Funcion.CAPACIDADES_POR_ARCH)
        ):
            return (), 0  # sin ``arch=`` no se pueden listar los de ARM64 (RF-D3.6)
        listas = [
            {m.nombre for m in self._cpus[n] if m.personalizado}
            for n in self._nodos_de_cpu()
            if n in self._cpus
        ]
        if not listas:
            return (), 0
        comunes = set.intersection(*listas)
        union = set.union(*listas)
        return tuple(sorted(comunes)), len(union - comunes)

    def _poblar_cpu(self, seleccion: str | None) -> None:
        """Rellena el desplegable de CPU: tipos fijos de la arquitectura y, aparte, los
        personalizados del clúster. Conserva la selección (un valor que ya no está se mantiene a
        la vista y la validación lo marca, nunca se cambia en silencio)."""
        actual = self.combo_cpu.currentData()
        previo = (
            seleccion if seleccion is not None else (actual if isinstance(actual, str) else None)
        )
        fijos = TIPOS_CPU_ARM if self._arq == Arquitectura.AARCH64 else TIPOS_CPU_X86
        personalizados, ocultos = self._personalizados_comunes()
        self.combo_cpu.blockSignals(True)
        self.combo_cpu.clear()
        for t in fijos:
            self.combo_cpu.addItem(t, t)
        if personalizados:
            self.combo_cpu.addItem(texto_grupo_cpu_personalizada(), None)
            cast(QStandardItemModel, self.combo_cpu.model()).item(
                self.combo_cpu.count() - 1
            ).setEnabled(False)
            for nombre in personalizados:
                self.combo_cpu.addItem(nombre, nombre)
        if previo and self.combo_cpu.findData(previo) < 0:
            self.combo_cpu.addItem(previo, previo)
        self.combo_cpu.setCurrentIndex(max(self.combo_cpu.findData(previo), 0) if previo else 0)
        self.combo_cpu.blockSignals(False)
        avisos: list[str] = []
        if ocultos:
            avisos.append(texto_cpus_ocultas(ocultos))
        if any(n in self._errores_cpu for n in self._nodos_de_cpu()):
            avisos.append(texto_cpus_no_leidas())
        estado = self._estados_d.get(OpcionD.CPU_PERSONALIZADA)
        if estado is not None and estado.disponibilidad == Disponibilidad.NO:
            avisos.append(texto_estado_opcion(estado))
        elif (
            self._arq == Arquitectura.AARCH64
            and self._caps_c is not None
            and not self._caps_c.tiene(Funcion.CAPACIDADES_POR_ARCH)
        ):
            avisos.append(texto_cpu_arm_sin_listar())
        poner_mensaje(self._aviso_cpu_d, "\n".join(avisos) or None, aviso=True)

    def establecer_disponibilidad_d(self, estados: Mapping[OpcionD, EstadoOpcion]) -> None:
        """Habilita o deshabilita las opciones de la fase D según privilegios y versión
        (``disponibilidad_fase_d``). Es barato: ignora lo que no cambió."""
        if dict(estados) == self._estados_d:
            return
        self._estados_d = dict(estados)
        mapeos = estados.get(OpcionD.MAPEOS)
        if mapeos is not None:
            self.seccion_hardware.establecer_disponibilidad(mapeos)
        self._ocupado = True
        try:
            self._poblar_cpu(None)
        finally:
            self._ocupado = False
        self._aplicar_modo()

    def establecer_hardware(self, info: InfoHardwareCluster | None) -> None:
        """Mapeos PCI/USB leídos del clúster (lo pidió ``pide_mapeos``)."""
        inv = self._inv
        permisos: PermisosEfectivos | None = (
            inv.catalogo.permisos if inv is not None and inv.catalogo is not None else None
        )
        self.seccion_hardware.establecer_info(info, permisos)

    def aplicar_propuesta_libvirt(
        self, propuesta: PropuestaLibvirt, macs_origen: Sequence[str | None] = ()
    ) -> None:
        """Rellena el formulario con la propuesta de la vista previa de libvirt, de una sola vez
        (CL-D23): origen «Importar disco», discos, redes, CPU, memoria, firmware y nombre."""
        cfg = propuesta.cfg
        self._base_asistente = None
        self._ocupado = True
        try:
            if cfg.nombre:
                self.nombre.setText(cfg.nombre)
                self.fila_nombre.marcar_tocado()
        finally:
            self._ocupado = False
        self.aplicar_hardware(
            cfg, origen=True, asistente=False, conservar_fase_c=True, conservar_fase_d=True
        )
        # Cada tarjeta con MAC de origen ofrece su casilla, desmarcada salvo que ya se conserve.
        self.tabla_redes.establecer_macs_origen(macs_origen)

    def _plantilla_elegida(self) -> Plantilla | None:
        """La plantilla del clon que ya está en el catálogo (por VMID o por nombre único)."""
        inv = self._inv
        if (
            inv is None
            or inv.catalogo is None
            or self.selector_origen.origen != OrigenSO.CLONAR_PLANTILLA
        ):
            return None
        det = self.configuracion().detalle_origen
        if not isinstance(det, DetalleClon):
            return None
        ref = det.plantilla
        plantillas = inv.catalogo.plantillas or ()
        if ref.vmid is not None:
            return next((p for p in plantillas if p.vmid == ref.vmid), None)
        por_nombre = [p for p in plantillas if ref.nombre and p.nombre == ref.nombre]
        return por_nombre[0] if len(por_nombre) == 1 else None

    def _sincronizar_fase_c(self) -> None:
        """Reparte lo que une las secciones: las tarjetas de la plantilla a «Red de las copias»,
        las tarjetas finales a cloud-init (B1) y si hay DHCP al firewall. Es idempotente: solo
        emite ``cambiado`` si alguna sección lo hace."""
        plantilla = self._plantilla_elegida()
        detalle = plantilla.detalle if plantilla is not None else None
        self.seccion_red_clon.establecer_tarjetas(detalle.tarjetas if detalle is not None else None)
        red = self.seccion_red_clon.red_clon()
        clon = self.selector_origen.origen == OrigenSO.CLONAR_PLANTILLA
        if clon and red is not None and detalle is not None:
            finales: tuple[int, ...] | None = tarjetas_finales(
                self.seccion_red_clon.indices_actuales(), red
            )
        else:
            finales = None
        self.seccion_cloudinit.establecer_tarjetas_finales(finales)
        ci = self._cloudinit_actual()
        self.seccion_firewall.establecer_hay_dhcp(
            ci is not None and any(t.modo == ModoTarjeta.DHCP for t in ci.tarjetas)
        )

    def _al_cambiar_red_clon(self) -> None:
        if self._ocupado:
            return
        self._sincronizar_fase_c()
        self._al_editar()

    def ceder_secreto(self) -> None:
        """Al lanzar un lote: su ``Secreto`` pasa al lote (no se olvida) y los campos se vacían."""
        self.seccion_cloudinit.ceder_secreto()

    def limpiar_secretos(self) -> None:
        """Borra los campos de la contraseña y olvida el ``Secreto`` que aún posea el formulario."""
        self.seccion_cloudinit.limpiar_secretos()

    def _poblar_pool(self, seleccion: str | None) -> None:
        """«Ninguno» y los pools del servidor; un pool que ya no está (de un lote guardado) se
        conserva como «x (no existe)» para que la validación lo marque (V-A10)."""
        self.combo_pool.blockSignals(True)
        try:
            self.combo_pool.clear()
            self.combo_pool.addItem(self.tr("Ninguno"), None)
            for pid in self._pools.ids:
                self.combo_pool.addItem(pid, pid)
            if seleccion and self.combo_pool.findData(seleccion) < 0:
                texto = (
                    texto_ausente(seleccion) if self._pools.estado == EstadoPools.OK else seleccion
                )
                self.combo_pool.addItem(texto, seleccion)
            idx = self.combo_pool.findData(seleccion) if seleccion else 0
            self.combo_pool.setCurrentIndex(max(idx, 0))
        finally:
            self.combo_pool.blockSignals(False)

    def _al_cambiar_notas_origen(self, _marcado: bool) -> None:
        self._actualizar_notas_usuario()
        self._al_editar()

    def _actualizar_notas_usuario(self) -> None:
        """«Incluir mi usuario» solo vale con las notas de origen marcadas (CA-A2.3.3)."""
        notas = self._estado_efectivo(OpcionA.NOTAS)
        libre = notas is None or notas.disponibilidad != Disponibilidad.NO
        self.chk_notas_usuario.setEnabled(libre and self.chk_notas_origen.isChecked())

    def _estado_efectivo(self, opcion: OpcionA) -> EstadoOpcion | None:
        """Estado de una opción. En un clon las notas viajan en el POST de clone, que no pide
        ``VM.Config.Options`` (CA-A2.1.5): no se deshabilitan por ese privilegio."""
        estado = self._estados_opciones.get(opcion)
        if (
            estado is not None
            and opcion == OpcionA.NOTAS
            and self.selector_origen.origen == OrigenSO.CLONAR_PLANTILLA
        ):
            return None
        return estado

    def establecer_disponibilidad(
        self, estados: Mapping[OpcionA, EstadoOpcion], pools: PoolsServidor | None = None
    ) -> None:
        """Habilita o deshabilita cada opción según privilegios, versión y pools (RF-A0.3/0.4).

        Una opción no disponible queda deshabilitada (no oculta) con el texto que nombra el
        privilegio y la ruta o la versión; si traía un valor, vuelve a su valor por defecto con
        un aviso (CL-A15). ``pools`` trae la lista que llena el selector de pool.
        """
        self._estados_opciones = dict(estados)
        if pools is not None:
            elegido = cast("str | None", self.combo_pool.currentData())
            # CL-A15: un pool que era válido en el servidor anterior y el nuevo no tiene vuelve
            # a «Ninguno» con aviso. Uno cargado de un archivo (ya «no existe») se conserva
            # para que «Comprobar» lo bloquee con V-A10.
            if (
                elegido
                and elegido in self._pools.ids
                and pools.estado == EstadoPools.OK
                and elegido not in pools.ids
            ):
                self._pool_restablecido = elegido
                elegido = None
            self._pools = pools
            self._poblar_pool(elegido)
        self.tabla_redes.establecer_disponibilidad(estados)
        self._reaplicar_disponibilidad()

    def _reaplicar_disponibilidad(self) -> None:
        previo, self._ocupado = self._ocupado, True
        cambios = False
        try:
            for grupo in self._grupos_opciones:
                estado = self._estado_efectivo(grupo.opcion)
                bloqueada = estado is not None and estado.disponibilidad == Disponibilidad.NO
                texto = texto_estado_opcion(estado) if estado is not None else ""
                for w in grupo.controles:
                    w.setEnabled(not bloqueada)
                    w.setAccessibleDescription(texto)
                if grupo.opcion == OpcionA.POOL and self._pool_restablecido is not None:
                    texto = texto_opcion_restablecida(
                        grupo.opcion.value,
                        self.tr("El servidor no tiene el pool «{pool}».").format(
                            pool=self._pool_restablecido
                        ),
                    )
                    self._pool_restablecido = None
                    cambios = True
                elif bloqueada and grupo.no_predeterminado():
                    grupo.restablecer()
                    texto = texto_opcion_restablecida(grupo.opcion.value, texto)
                    cambios = True
                elif not bloqueada and grupo.opcion == OpcionA.NOTAS and self._notas_forzadas_off:
                    # Vuelve el privilegio: las notas de origen recuperan su valor por defecto.
                    self.chk_notas_origen.setChecked(True)
                    self._notas_forzadas_off = False
                self._texto_estado[id(grupo.fila)] = texto
                self._refrescar_aviso(grupo.fila)
            self._actualizar_notas_usuario()
        finally:
            self._ocupado = previo
        if cambios and not previo:
            self.cambiado.emit()

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

    def campos_no_numericos(self) -> list[str]:
        """Campos numéricos cuyo texto no es un número: el lote no se puede guardar así.

        Devuelve los nombres que ve el usuario («Núcleos por socket», «scsi0»…). Un texto no
        numérico se leería como 0 y se guardaría un valor que el usuario nunca escribió.
        """
        malos: list[str] = []

        def revisar(texto: str, nombre: str, *, decimal: bool = False) -> None:
            try:
                if decimal:
                    float(texto.strip().replace(",", "."))
                else:
                    int(texto.strip())
            except ValueError:
                malos.append(nombre)

        if not self._modo_lote:
            revisar(self.vmid.text(), self.tr("Número de máquina (VMID)"))
        revisar(self.cores.text(), self.tr("Núcleos por socket"))
        revisar(self.memoria.text(), self.tr("Memoria (GiB)"), decimal=True)
        if self.combo_balloon.currentData() is True:
            revisar(self.balloon_min.text(), self.tr("Memoria mínima (GiB)"), decimal=True)
        if not self.chk_sin_disco.isChecked():
            malos.extend(
                self.tr("Tamaño del disco {n}").format(n=n)
                for n in self.tabla_discos.tamanos_no_numericos()
            )
        malos.extend(
            self.tr("VLAN de {n}").format(n=n) for n in self.tabla_redes.vlan_no_numericas()
        )
        for texto, nombre in (
            (self.txt_orden.text(), self.tr("Orden de arranque")),
            (self.txt_espera.text(), self.tr("Espera (s)")),
        ):
            if texto.strip():
                revisar(texto, nombre)
        if self.chk_esperar_ip.isChecked() and self.txt_plazo_ip.text().strip():
            revisar(self.txt_plazo_ip.text(), self.tr("Plazo (segundos)"))
        malos.extend(self.tr("MTU de {n}").format(n=n) for n in self.tabla_redes.mtu_no_numericas())
        malos.extend(
            self.tr("Límite de {n}").format(n=n) for n in self.tabla_redes.limites_no_numericos()
        )
        return malos

    def establecer_nombre(self, nombre: str) -> None:
        """Pone el nombre de la máquina (lote guardado de una sola máquina con nombre propio)."""
        self.nombre.setText(nombre)
        self.fila_nombre.marcar_tocado()
        self.cambiado.emit()

    def nodo_efectivo(self) -> str:
        """Nodo que se usará (el manual, el que eligió Automático o el único)."""
        return self._nodo_actual

    @property
    def motivo_nodo(self) -> MotivoNodo | None:
        return self._motivo_nodo

    @property
    def error_nodo(self) -> ErrorProxLaunch | None:
        return self._error_nodo

    @property
    def es_automatico(self) -> bool:
        return self._radio_auto.isChecked()

    def etiquetas_discos(self) -> list[str]:
        """Etiquetas de los discos tal como están en la tabla (el asistente ya escribió el bus
        del primero)."""
        return self.tabla_discos.etiquetas_discos()

    # --- Nodo -------------------------------------------------------------------------

    def _espacio_requerido(self) -> int:
        if self.chk_sin_disco.isChecked():
            return 0
        return sum(d.tamano_gib for d in self.tabla_discos.discos() if d.tamano_gib > 0)

    def _calcular_nodo(
        self, requerido_gib: int | None = None
    ) -> tuple[str, MotivoNodo | None, ErrorProxLaunch | None]:
        """Nodo según el modo: único, manual o Automático (P-07)."""
        inv = self._inv
        if inv is None:
            return "", None, None
        if not inv.topologia.es_cluster:
            nodos = inv.topologia.nodos
            return (nodos[0].nombre if nodos else ""), None, None
        if not self._radio_auto.isChecked():
            return str(self.combo_nodo.currentData() or ""), None, None
        requerido = self._espacio_requerido() if requerido_gib is None else requerido_gib
        try:
            nodo, motivo = elegir_nodo(inv, requerido)
        except ErrorProxLaunch as e:
            return "", None, e
        return nodo, motivo, None

    def _actualizar_nodo(self) -> None:
        nodo, motivo, error = self._calcular_nodo()
        self._nodo_actual, self._motivo_nodo, self._error_nodo = nodo, motivo, error
        self._refrescar_etiqueta_nodo()
        if nodo != self._nodo_cargado:
            self._cargar_recursos_nodo(nodo)
        if nodo != self._nodo_sincronizado:
            # Otro nodo efectivo: puede ser de otra arquitectura (RF-D2.7, CA-D2.7.5).
            self._nodo_sincronizado = nodo
            self._sincronizar_arquitectura(adaptar=True, nueva=True)
            self._pedir_cpus_cargadas()

    def _refrescar_etiqueta_nodo(self) -> None:
        if self._inv is None or not self._inv.topologia.es_cluster:
            return
        if not self._radio_auto.isChecked():
            self._texto_motivo.setText("")
            self._texto_motivo.hide()
            return
        if self._error_nodo is not None:
            self._texto_motivo.setText(texto_error(self._error_nodo))
        elif self._motivo_nodo is not None:
            self._texto_motivo.setText(
                self.tr("Nodo elegido: {nodo} ({motivo})").format(
                    nodo=self._nombre_nodo(self._nodo_actual),
                    motivo=texto_motivo_nodo(self._motivo_nodo),
                )
            )
        self._texto_motivo.show()

    def _llenar_combo_nodos(self) -> None:
        inv = self._inv
        if inv is None:
            return
        previo = self.combo_nodo.currentData()
        self.combo_nodo.blockSignals(True)
        self.combo_nodo.clear()
        for n in inv.topologia.nodos:
            nombre = self._nombre_nodo(n.nombre)
            texto = nombre if n.en_linea else f"{nombre} — {self.tr('Sin conexión')}"
            self.combo_nodo.addItem(texto, n.nombre)
            if not n.en_linea:
                cast(QStandardItemModel, self.combo_nodo.model()).item(
                    self.combo_nodo.count() - 1
                ).setEnabled(False)
        idx = self.combo_nodo.findData(previo) if previo else -1
        if idx < 0:
            idx = next((i for i, n in enumerate(inv.topologia.nodos) if n.en_linea), -1)
        self.combo_nodo.setCurrentIndex(idx)
        self.combo_nodo.blockSignals(False)

    def _cargar_recursos_nodo(self, nodo: str) -> None:
        """Rellena almacenamientos y bridges con los del nodo (CA-11.7)."""
        inv = self._inv
        if inv is None:
            return
        self._nodo_cargado = nodo
        almacenes = inv.storages.get(nodo, ())
        redes = inv.bridges.get(nodo, ())
        avisos: list[str] = []
        perdidos = self.tabla_discos.establecer_storages(almacenes)
        self.tabla_discos.mostrar_aviso_nodo(None)
        for sid in perdidos:
            avisos.append(
                self.tr(
                    "El almacenamiento «{recurso}» no existe en el nodo «{nodo}». Elige otro."
                ).format(recurso=sid, nodo=nodo)
            )
        self.tabla_discos.mostrar_aviso_nodo("\n".join(avisos))
        perdidas = self._establecer_redes_disponibles(nodo, redes)
        self.tabla_redes.mostrar_aviso_nodo(
            "\n".join(
                self.tr("La red «{recurso}» no existe en el nodo «{nodo}». Elige otra.").format(
                    recurso=b, nodo=nodo
                )
                for b in perdidas
            )
        )
        self._poblar_efi(self.combo_efi.currentData())
        self._actualizar_sin_disco()

    def _establecer_redes_disponibles(self, nodo: str, bridges: Sequence) -> list[str]:
        """Bridges y VNets del nodo (o la intersección de los nodos del lote, RF-C2.3) para la
        tabla de redes y para la red del clon. Devuelve las redes elegidas que ya no existen."""
        inv = self._inv
        vnets: tuple[RedVirtual, ...] = ()
        ocultas = 0
        sin_leer: tuple[str, ...] = ()
        sdn_leido = False
        sdn_fallido: str | None = None
        if inv is not None:
            if len(self._nodos_destino) > 1:
                inter = interseccion_redes(inv, self._nodos_destino)
                bridges, vnets = inter.bridges, inter.vnets
                ocultas, sin_leer = inter.ocultas, inter.sin_leer
                sdn_leido = not sin_leer
            else:
                vnets = tuple(inv.redes_sdn.get(nodo, ()))
                sdn_leido = nodo in inv.redes_sdn and nodo not in inv.errores_sdn
                if nodo in inv.errores_sdn:
                    sdn_fallido = nodo
        incluido = True  # con la mínima 8.4 el SDN viene instalado (DT-D3)
        perdidas = self.tabla_redes.establecer_bridges(
            bridges,
            vnets,
            sdn_leido=sdn_leido,
            sdn_incluido=incluido,
            ocultas=ocultas,
            sin_leer=sin_leer,
            sdn_fallido=sdn_fallido,
        )
        self.seccion_red_clon.establecer_redes(bridges, vnets)
        return perdidas

    def establecer_nodos_destino(self, nodos: Sequence[str]) -> None:
        """Nodos destino del lote (un lote repartido entre varios nodos solo ofrece las redes que
        existen en todos, RF-C2.3). Con uno o ninguno se usa el nodo de referencia."""
        nuevos = tuple(sorted(set(nodos)))
        if nuevos == self._nodos_destino:
            return
        self._nodos_destino = nuevos
        if self._inv is not None and self._nodo_actual:
            self._ocupado = True
            try:
                self._cargar_recursos_nodo(self._nodo_actual)
            finally:
                self._ocupado = False
            self.cambiado.emit()

    def actualizar_recursos_nodo(
        self,
        nodo: str,
        storages: Sequence,
        bridges: Sequence,
        redes: RedesNodo | None = None,
    ) -> None:
        """Guarda los recursos releídos de un nodo y los recarga si es el efectivo.

        ``redes`` (fase C) trae las VNets leídas con «Recargar nodo»; ``None`` deja las que había.
        """
        if self._inv is None:
            return
        self._inv.storages[nodo] = tuple(storages)
        self._inv.bridges[nodo] = tuple(bridges)
        if redes is not None:
            self._inv.redes_sdn[nodo] = redes.vnets
            if redes.error is not None:
                self._inv.errores_sdn[nodo] = redes.error
            else:
                self._inv.errores_sdn.pop(nodo, None)
        if nodo == self._nodo_actual:
            self._ocupado = True
            try:
                self._cargar_recursos_nodo(nodo)
            finally:
                self._ocupado = False
            self.cambiado.emit()

    def _poblar_efi(self, seleccionado: str | None, *, conservar_ausente: bool = False) -> None:
        inv = self._inv
        self.combo_efi.blockSignals(True)
        self.combo_efi.clear()
        self.combo_efi.addItem(self.tr("Automático (el del primer disco)"), None)
        activos: set[str] = set()
        if inv is not None:
            for s in inv.storages.get(self._nodo_actual, ()):
                if s.activo:
                    self.combo_efi.addItem(s.id, s.id)
                    activos.add(s.id)
        if conservar_ausente and seleccionado and seleccionado not in activos:
            self._efi_ausente = seleccionado
        if self._efi_ausente and self._efi_ausente not in activos:
            self.combo_efi.addItem(texto_ausente(self._efi_ausente), self._efi_ausente)
            cast(QStandardItemModel, self.combo_efi.model()).item(
                self.combo_efi.count() - 1
            ).setEnabled(False)
        elif self._efi_ausente in activos:
            self._efi_ausente = None
        idx = self.combo_efi.findData(seleccionado) if seleccionado else 0
        self.combo_efi.setCurrentIndex(max(idx, 0))
        self.combo_efi.blockSignals(False)

    def _al_cambiar_efi(self, _i: int) -> None:
        if self._efi_ausente and self.combo_efi.currentData() != self._efi_ausente:
            self._efi_ausente = None
            self.fila_efi.mostrar_aviso(None)
        self._al_editar(self.fila_efi)

    def _actualizar_sin_disco(self) -> None:
        """CA-11.9: sin almacenamiento para discos solo se puede crear «sin disco»."""
        inv = self._inv
        hay = inv is not None and any(s.activo for s in inv.storages.get(self._nodo_actual, ()))
        if inv is not None and not hay:
            poner_mensaje(
                self._sin_storage,
                self.tr("Este servidor no tiene almacenamiento para discos de máquinas virtuales"),
            )
        else:
            poner_mensaje(self._sin_storage, None)
        self.tabla_discos.setVisible(not self.chk_sin_disco.isChecked())

    # --- Señales internas -------------------------------------------------------------

    def _tocar(self, fila: FilaCampo) -> None:
        if not fila.tocado:
            fila.marcar_tocado()
            self.cambiado.emit()

    def _al_editar(self, fila: FilaCampo | None = None) -> None:
        if self._ocupado:
            return
        if fila is not None:
            fila.marcar_tocado()
        self._actualizar_nodo()
        self.cambiado.emit()

    def _al_editar_vmid(self, _texto: str) -> None:
        self.fila_vmid.marcar_tocado()
        self._al_editar(self.fila_vmid)

    def _al_terminar_vmid(self) -> None:
        self.fila_vmid.marcar_tocado()
        try:
            n = int(self.vmid.text().strip())
        except ValueError:
            return
        if self._inv is not None and n != self._inv.proximo_vmid:
            self.vmid_confirmado.emit(n)

    def _al_cambiar_cpu(self, *_args: object, fila: FilaCampo | None = None) -> None:
        self._actualizar_total_cpu()
        self._al_editar(fila)

    def _al_cambiar_tipo_cpu(self, _i: int) -> None:
        self._aplicar_modo()
        self._al_editar()

    def _al_cambiar_balloon(self, _i: int) -> None:
        self._aplicar_modo()
        self._al_editar()

    def _al_cambiar_firmware(self, _i: int) -> None:
        self._aplicar_modo()
        self._al_editar()

    def _al_cambiar_origen(self) -> None:
        """Otro origen, fuente o sistema operativo: se ajusta el formulario y se revalida."""
        self._actualizar_para_origen()
        self._al_editar()

    def _al_dejar_origen_con_asistente(self, origen: object) -> None:
        """Con otro origen que no usa el asistente se descarta su base (los widgets quedan como
        están): al volver a ISO o disco importado la base será lo que muestre el formulario."""
        if origen not in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO):
            self._base_asistente = None

    def _al_pedir_asistente(self, tipo: object, solo_bus: bool) -> None:
        """El usuario eligió otro SO (o «Disco compatible»): se aplica el asistente una vez."""
        if self._ocupado or not isinstance(tipo, TipoSO):
            return
        self._escribir_asistente(tipo, solo_bus=solo_bus)
        self._aplicar_modo()
        self._al_editar()

    def _escribir_asistente(self, tipo: TipoSO, *, solo_bus: bool) -> None:
        """Aplica el asistente de SO a los widgets (firmware, TPM, agente, controlador, tarjeta de
        red y bus del primer disco). A partir de aquí ``configuracion()`` devuelve lo que muestran
        los widgets y el modo avanzado puede dejar otros valores (CA-O13.8). Con ``solo_bus`` solo
        se reescribe el bus del primer disco (casilla «Disco compatible»)."""
        selector = self.selector_origen
        # La base se fija una sola vez; cada SO (y «Otro», que vuelve a ella) se aplica sobre ella.
        if self._base_asistente is None:
            self._base_asistente = self._configuracion_base()
        base = self._base_asistente
        resultado = aplicar_asistente(base, tipo, disco_compatible=selector.disco_compatible)
        cfg = resultado.cfg
        previo, self._ocupado = self._ocupado, True
        try:
            if not solo_bus:
                self.combo_firmware.setCurrentIndex(
                    max(self.combo_firmware.findData(cfg.firmware), 0)
                )
                self.chk_tpm.setChecked(cfg.tpm)
                self.chk_agente.setChecked(cfg.agente_qemu)
                self.combo_ctrl.setCurrentIndex(
                    max(self.combo_ctrl.findData(cfg.controlador_scsi), 0)
                )
                if cfg.redes and len({r.modelo for r in cfg.redes}) == 1:
                    self.tabla_redes.establecer_modelo_todas(cfg.redes[0].modelo)
            if cfg.con_disco and cfg.discos:
                self.tabla_discos.establecer_bus_primero(cfg.discos[0].bus)
        finally:
            self._ocupado = previo
        selector.establecer_cambios(resultado.cambios)

    def _actualizar_para_origen(self) -> None:
        """Con una plantilla el hardware es el suyo; con un disco importado el primero es la
        imagen y no puede faltar (CA-O15.4, CA-O22.1)."""
        origen = self.selector_origen.origen
        clon = origen == OrigenSO.CLONAR_PLANTILLA
        importar = origen == OrigenSO.IMPORTAR_DISCO
        for caja in (self._caja_firmware, self._caja_computo, self._caja_discos, self._caja_red):
            caja.setVisible(not clon)
        self._caja_cloudinit.setVisible(clon)  # cloud-init solo al clonar (RF-B1.2)
        self.seccion_red_clon.setVisible(clon)  # red del clon solo al clonar (RF-C4.1)
        self._sincronizar_fase_c()
        self._nota_clon.setVisible(clon)
        self._nota_importar.setVisible(importar)
        if importar and self.chk_sin_disco.isChecked():
            self.chk_sin_disco.setChecked(False)
        self.chk_sin_disco.setEnabled(not importar)
        self.tabla_discos.establecer_primero_importado(importar)
        self._reaplicar_disponibilidad()  # las notas de un clon no piden VM.Config.Options

    def _al_cambiar_sin_disco(self, _marcado: bool) -> None:
        if self._ocupado:
            return
        self._actualizar_sin_disco()
        self._aplicar_modo()
        self._al_editar()

    def _al_cambiar_controlador(self, _i: int) -> None:
        self.tabla_discos.establecer_controlador(ControladorScsi(self.combo_ctrl.currentData()))
        self._al_editar()

    def _al_cambiar_tabla(self) -> None:
        if self._ocupado:
            return
        self._actualizar_nodo()
        self.cambiado.emit()

    def _al_cambiar_modo_nodo(self, _auto: bool) -> None:
        if self._ocupado:
            return
        self.combo_nodo.setEnabled(not self._radio_auto.isChecked())
        self._actualizar_nodo()
        self.cambiado.emit()
        if not self._radio_auto.isChecked() and self._nodo_actual:
            self.nodo_elegido.emit(self._nodo_actual)

    def _al_elegir_nodo(self, _i: int) -> None:
        if self._ocupado or self._radio_auto.isChecked():
            return
        self._actualizar_nodo()
        self.cambiado.emit()
        if self._nodo_actual:
            self.nodo_elegido.emit(self._nodo_actual)

    def _actualizar_total_cpu(self) -> None:
        sockets = self.combo_sockets.currentData() or 1
        cores = entero_o_cero(self.cores.text())
        if cores > 0:
            self._total_cpu.setText(
                self.tr("{n} procesadores virtuales en total").format(n=sockets * cores)
            )
            self._total_cpu.show()
        else:
            self._total_cpu.hide()

    # --- VMID -------------------------------------------------------------------------

    def marcar_vmid_ocupado(self, vmid: int, siguiente: str | None) -> None:
        self._vmid_ocupado = (vmid, siguiente)
        self.fila_vmid.marcar_tocado()
        self.cambiado.emit()

    def limpiar_vmid_ocupado(self) -> None:
        if self._vmid_ocupado is not None:
            self._vmid_ocupado = None
            self.cambiado.emit()

    def preparar_otra(self) -> None:
        """«Crear otra»: conserva la configuración, vacía el nombre y libera el VMID."""
        self.nombre.clear()
        self.limpiar_secretos()  # la contraseña no se arrastra a la siguiente máquina
        self.fila_nombre.tocado = False
        self.fila_vmid.tocado = False
        self._vmid_ocupado = None
        self.cambiado.emit()

    def sugerir_vmid(self, vmid: int) -> None:
        self.vmid.setText(str(vmid))
        self._vmid_ocupado = None
        self.cambiado.emit()

    def problemas_extra(self) -> list[Problema]:
        """Problemas que el núcleo no calcula con datos locales (V-03, CA-17.1)."""
        extra: list[Problema] = []
        if self._vmid_ocupado is not None:
            vmid, siguiente = self._vmid_ocupado
            if entero_o_cero(self.vmid.text()) == vmid:
                params = {"vmid": str(vmid)}
                if siguiente:
                    params["siguiente"] = siguiente
                extra.append(Problema("vmid", "V-03", Severidad.ERROR, params))
        if self._inv is not None and self._nodo_actual and not self.tabla_redes.hay_bridges():
            extra.append(Problema("redes", "V-16.sinredes", Severidad.ERROR, {}))
        if self.selector_origen.origen == OrigenSO.CLONAR_PLANTILLA:
            # V-B22, V-B24 y V-B25 sobre lo escrito: lo inválido no llega a ``configuracion()``.
            extra.extend(self.seccion_cloudinit.problemas())
        return extra

    # --- Errores y bloqueo ------------------------------------------------------------

    def aplicar_problemas(self, problemas: Sequence[Problema]) -> None:
        """Muestra cada error junto a su campo (propiedad ``invalido``)."""
        por_campo: dict[str, list[Problema]] = {}
        for p in problemas:
            por_campo.setdefault(p.campo, []).append(p)

        def texto(campo: str) -> str | None:
            errores = [
                texto_problema(p)
                for p in por_campo.get(campo, [])
                if p.severidad == Severidad.ERROR
            ]
            return errores[0] if errores else None

        self.fila_vmid.mostrar_error(texto("vmid"))
        self.fila_nombre.mostrar_error(texto("nombre"))
        nodo_txt = texto("nodo")
        if self._error_nodo is not None:
            nodo_txt = None  # el motivo ya está debajo del selector
        self.fila_nodo.marcar_tocado()
        self.fila_nodo.mostrar_error(nodo_txt)
        self.fila_cpu.marcar_tocado()
        self.fila_cpu.mostrar_error(texto("tipo_cpu"))
        self.fila_sockets.mostrar_error(texto("sockets"))
        self.fila_cores.mostrar_error(texto("cores"))
        self.fila_memoria.mostrar_error(texto("memoria_mib"))
        self.fila_balloon_min.mostrar_error(texto("ballooning.minimo_mib"))
        self.fila_ctrl.mostrar_error(texto("controlador_scsi"))
        self._aplicar_problemas_opciones(problemas)
        self.seccion_cloudinit.mostrar_problemas(problemas)
        self.seccion_red_clon.mostrar_problemas(problemas)
        self.seccion_firewall.mostrar_problemas(problemas)
        self.seccion_hardware.mostrar_problemas(problemas)
        self.fila_efi.marcar_tocado()
        self.fila_efi.mostrar_error(texto("storage_efi"))
        self.tabla_discos.aplicar_problemas(problemas)
        self.tabla_redes.aplicar_problemas(problemas)

    def _aplicar_problemas_opciones(self, problemas: Sequence[Problema]) -> None:
        """Errores y avisos de las reglas V-A junto a su opción (siempre visibles: un valor que
        viene de un lote guardado no lo escribió el usuario en esta sesión)."""
        filas = {
            "encender": self.fila_encender,
            "arranque_auto": self.fila_arranque_auto,
            "arranque_orden": self.fila_orden,
            "arranque_espera": self.fila_espera,
            "notas": self.fila_notas,
            "etiquetas": self.fila_etiquetas,
            "etiquetas_usuario": self.fila_etiquetas,
            "pool": self.fila_pool,
            "proteger": self.fila_proteger,
            "esperar_ip": self.fila_esperar_ip,
            "plazo_ip_s": self.fila_esperar_ip,
        }
        errores: dict[int, list[str]] = {}
        avisos: dict[int, list[str]] = {}
        for p in problemas:
            fila = filas.get(p.campo.split("[")[0])
            if fila is None:
                continue
            destino = errores if p.severidad == Severidad.ERROR else avisos
            destino.setdefault(id(fila), []).append(texto_problema(p))
        for fila in dict.fromkeys(filas.values()):
            fila.marcar_tocado()
            fila.mostrar_error("\n".join(dict.fromkeys(errores.get(id(fila), []))) or None)
            self._texto_validacion[id(fila)] = "\n".join(dict.fromkeys(avisos.get(id(fila), [])))
            self._refrescar_aviso(fila)

    def bloquear(self, bloqueado: bool) -> None:
        """Bloquea los campos mientras se crea la máquina (CA-19.4); con ellos, el origen."""
        self.selector_origen.establecer_bloqueado(bloqueado)
        self.setEnabled(not bloqueado)

    # --- Lote (MVP 2) -----------------------------------------------------------------

    def establecer_lote(self, activo: bool) -> None:
        """Con más de una máquina el nombre, el VMID y el nodo salen del bloque «Lote»."""
        self._modo_lote = activo
        self.seccion_cloudinit.establecer_lote(activo)
        # El grupo «General» sigue visible en un lote: las opciones de la fase A (encender, notas,
        # etiquetas, pool…) valen para todo el lote; solo se ocultan nombre, VMID y nodo.
        self.fila_nombre.setVisible(not activo)
        self.fila_vmid.setVisible(not activo)
        es_cluster = self._inv is not None and self._inv.topologia.es_cluster
        self.fila_nodo.setVisible(es_cluster and not activo)

    @property
    def modo_lote(self) -> bool:
        return self._modo_lote

    def usar_nodo_manual(self, nodo: str) -> None:
        """El bloque «Lote» eligió un nodo: sus almacenamientos y redes alimentan el formulario."""
        if self._inv is None or not self._inv.topologia.es_cluster:
            return
        self._ocupado = True
        try:
            idx = self.combo_nodo.findData(nodo)
            if idx >= 0:
                self.combo_nodo.setCurrentIndex(idx)
            self._radio_manual.setChecked(True)
            self.combo_nodo.setEnabled(True)
        finally:
            self._ocupado = False
        self._actualizar_nodo()
        self.cambiado.emit()
        if self._nodo_actual:
            self.nodo_elegido.emit(self._nodo_actual)

    def usar_nodo_automatico(self) -> None:
        """Vuelve a la elección automática del nodo (lo que usa de referencia el formulario)."""
        if self._inv is None or self._radio_auto.isChecked():
            return
        self._ocupado = True
        try:
            self._radio_auto.setChecked(True)
            self.combo_nodo.setEnabled(False)
        finally:
            self._ocupado = False
        self._actualizar_nodo()
        self.cambiado.emit()
