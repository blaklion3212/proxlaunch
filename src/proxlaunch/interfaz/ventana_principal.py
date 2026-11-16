"""Ventana principal: barra superior, formulario, resumen y progreso (RF-19 a RF-24)."""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from proxlaunch import __version__
from proxlaunch.interfaz.archivos_ui import (
    TipoArchivo,
    descargar_plantilla,
    elegir_para_abrir,
    elegir_para_guardar,
)
from proxlaunch.interfaz.controlador_origen import ControladorOrigen
from proxlaunch.interfaz.desplazable import AreaInterna, crear_area_desplazable, limitar_a_pantalla
from proxlaunch.interfaz.dialogos.acerca_de import DialogoAcercaDe
from proxlaunch.interfaz.dialogos.conexion import DialogoConexion
from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.guardar_lote import AccionGuardarLote, DialogoGuardarLote
from proxlaunch.interfaz.dialogos.guardar_perfil import DialogoGuardarPerfil
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.dialogos.lote_no_encaja import PanelLoteNoEncaja
from proxlaunch.interfaz.dialogos.pausa_lote import AccionPausa, DialogoPausaLote
from proxlaunch.interfaz.dialogos.perfiles_maquina import DialogoPerfilesMaquina
from proxlaunch.interfaz.dialogos.transferencias_sesion import DialogoTransferenciasSesion
from proxlaunch.interfaz.informe_lote import (
    guardar_informe_parcial,
    nombre_archivo_csv_sugerido,
    tomar_aviso_informe_parcial,
)
from proxlaunch.interfaz.modelos_tabla import texto_aviso_entrada
from proxlaunch.interfaz.tema import GestorTema, ModoTema
from proxlaunch.interfaz.textos import (
    alias_columnas_csv,
    privilegio_faltante_critico,
    texto_aviso,
    texto_aviso_archivo,
    texto_aviso_pista,
    texto_desenlace,
    texto_error,
    texto_existe_sin_confirmar,
    texto_fallo,
    texto_motivo_nodo,
    texto_problema,
    texto_problema_lote,
    textos_perfiles_fabrica,
)
from proxlaunch.interfaz.trabajadores import (
    Lanzador,
    PuenteLote,
    PuenteRollback,
    armar_reintento,
    comprobar_dudosas_lote,
    comprobar_existencia,
    comprobar_vmid,
    continuar_lote,
    descubrir_y_comprobar_permisos,
    deshacer_lotes,
    ejecutar_lote,
    escribir_informe_csv,
    guardar_lote_guardado,
    leer_lote_guardado,
    planificar_lote,
    reanudar_seguimiento,
    recargar_nodo,
    reintentar_ajustes_lote,
    reintentar_nodos,
    replanificar_lote,
    simular_lote,
    simular_reintento,
)
from proxlaunch.interfaz.vistas.barra_superior import BarraSuperior, cargar_svg, nombre_logotipo
from proxlaunch.interfaz.vistas.bloque_lote import BloqueLote
from proxlaunch.interfaz.vistas.campos import mensaje, poner_mensaje
from proxlaunch.interfaz.vistas.detalles_tecnicos import texto_detalles
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.interfaz.vistas.lote_filas import PanelLoteFilas, texto_titulo_filas
from proxlaunch.interfaz.vistas.progreso import PanelProgreso
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, ProgresoLote, texto_barra
from proxlaunch.interfaz.vistas.resumen import ResumenVM, nombre_campo
from proxlaunch.interfaz.vistas.resumen_lote import ResumenLote
from proxlaunch.interfaz.vistas.selector_perfil import PanelAvisos, SelectorPerfil
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.modelos import ResultadoImportacion, TablaCsv
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.ajustes import tiene_ajustes_pendientes
from proxlaunch.nucleo.lote.constantes import (
    ACTUALIZACIONES_POR_S,
    ETIQUETA_APP,
    PLAN_MAX_EDAD_S,
    PREFIJO_ETIQUETA_LOTE,
    UMBRAL_CONFIRMACION_DOBLE,
    UMBRAL_PAUSA_ERRORES,
)
from proxlaunch.nucleo.lote.filas import (
    definicion_para_reintento,
    definicion_por_filas,
    reemplazar_fila,
    sin_filas,
    usa_nombre_de_plantilla,
)
from proxlaunch.nucleo.lote.informe import construir_informe, informe_desde_entradas
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    ESTADOS_DUDOSOS,
    ESTADOS_EN_CURSO,
    Algoritmo,
    CandidatoRollback,
    DefinicionLote,
    Destino,
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
    EstadoRollback,
    InformeLote,
    MetadatosInforme,
    ModoDestino,
    MotivoPausa,
    MotivoReparto,
    PatronNombres,
    Plan,
    ResultadoRollback,
    ResultadoSimulacion,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.reconciliacion import AVISO_CREADA_TRAS_COMPROBAR
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.lotes_guardados.formato import lote_a_dict
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.lotes_guardados.revalidacion import (
    Desajuste,
    TipoDesajuste,
    desajustes,
    sustituir,
)
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.origen.storages import candidatos_servidor
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.aplicar import (
    aplicar_perfil,
    config_desde_configuracion,
    hardware_igual,
)
from proxlaunch.nucleo.perfiles_maquina.compatibilidad import evaluar_compatibilidad
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO, PerfilMaquina
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.persistencia.preferencias import (
    Modo,
    Preferencias,
    RepositorioPreferencias,
    Tema,
)
from proxlaunch.nucleo.persistencia.rutas import crear_carpeta_privada
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import CodigoAviso, ServicioConexion, Sesion
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.validacion import Severidad, validar_vm

_log = logging.getLogger("proxlaunch.interfaz.ventana")


@dataclass
class Dependencias:
    """Servicios del núcleo que usa la interfaz (se inyectan para poder probar sin red)."""

    servicio_conexion: ServicioConexion
    perfiles: RepositorioPerfiles
    huellas: RepositorioHuellas
    secretos: AlmacenSecretos
    preferencias: RepositorioPreferencias
    reloj: Reloj
    gestor_tema: GestorTema
    # Carpeta de los informes parciales (``Rutas.informes``); obligatoria para que ningún
    # camino de escritura salga de ``Rutas``.
    directorio_informes: Path
    # Carpeta sugerida para guardar lotes (``Rutas.lotes``); obligatoria, como la de informes.
    directorio_lotes: Path
    # Permite ajustar el intervalo de sondeo (por defecto el del núcleo).
    fabrica_creacion: Callable[[Sesion], ServicioCreacion] | None = None
    # Perfiles de máquina (MVP 3). Si no se inyecta, la ventana crea el almacén junto al archivo
    # de perfiles de conexión y lo carga. Uno inyectado debe venir ya cargado (``cargar()``).
    perfiles_maquina: AlmacenPerfilesMaquina | None = None
    # Versión que se escribe en los archivos propios (``app_version``).
    version_app: str = __version__


# Estados que permiten reintentar la máquina en un lote nuevo: nunca se creó (RF-L21).
_ESTADOS_REINTENTABLES = frozenset(
    {EstadoMV.NO_ENVIADA, EstadoMV.NO_CREADA_SEGURA, EstadoMV.ERROR, EstadoMV.PENDIENTE}
)
_ETAPA_POR_ESTADO = {
    EstadoMV.VALIDANDO: Etapa.VALIDANDO,
    EstadoMV.ENVIANDO: Etapa.ENVIANDO,
    EstadoMV.CREANDO: Etapa.CREANDO,
    EstadoMV.AJUSTANDO: Etapa.AJUSTANDO,
    EstadoMV.COMPROBANDO: Etapa.COMPROBANDO,
}
_DESENLACE_POR_ESTADO = {
    EstadoMV.OK: Desenlace.OK,
    EstadoMV.CON_AVISOS: Desenlace.CON_AVISOS,
    EstadoMV.ERROR: Desenlace.ERROR,
    EstadoMV.PARCIAL: Desenlace.PARCIAL,
    EstadoMV.TIEMPO_AGOTADO: Desenlace.TIEMPO_AGOTADO,
    EstadoMV.CONEXION_PERDIDA: Desenlace.CONEXION_PERDIDA,
    EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD: Desenlace.CONEXION_PERDIDA,
    EstadoMV.NO_ENVIADA: Desenlace.CANCELADO,
    EstadoMV.NO_CREADA_SEGURA: Desenlace.CANCELADO,
}


@dataclass
class _Lote:
    """Lote en pantalla: su plan, su control y lo necesario para deshacer o informar."""

    plan: Plan
    inv: Inventario
    sesion: Sesion
    perfil_id: str | None
    control: ControlLote
    puente: PuenteLote
    modo_uno: bool
    libro: Libro | None = None
    terminado: bool = False
    cancelando: bool = False
    pausa_mostrada: bool = False
    dialogo_pausa: DialogoPausaLote | None = None
    continuacion: AccionPausa | None = None
    esperando_reconexion: bool = False
    deshaciendo: bool = False
    control_rollback: ControlLote | None = None
    puente_rollback: PuenteRollback | None = None
    resultados_rollback: list[ResultadoRollback] = field(default_factory=list)
    cerrado: bool = False


@dataclass
class _OrigenLote:
    """De dónde salió el lote que hay en pantalla (importación CSV o archivo de lote).

    ``tipo``: ``"csv"`` o ``"guardado"``. ``nombre`` es el nombre del archivo (CSV) o del lote
    (guardado), nunca una ruta. Del CSV se conservan la tabla y el resultado para «Revisar
    filas…» sin releer el archivo y el total de filas del archivo («N de N+M», CA-C07.2).
    """

    tipo: str
    nombre: str
    tabla: TablaCsv | None = None
    resultado: ResultadoImportacion | None = None
    total_filas: int = 0


# Huella de «hay cambios sin guardar» para un lote importado de CSV que nunca se guardó.
_SIN_GUARDAR: dict[str, object] = {}


def diferencia_planes(antes: Plan, despues: Plan) -> str:
    """Texto breve de lo que cambió entre dos planes; vacío si son equivalentes (CA-L10.6)."""
    cambios: list[str] = []
    if despues.bloqueado and not antes.bloqueado:
        cambios.append(
            QCoreApplication.translate(
                "VentanaPrincipal", "ahora hay errores que impiden crear el lote"
            )
        )
    previos = {e.indice: e for e in antes.elementos}
    for e in despues.elementos:
        a = previos.get(e.indice)
        if a is None:
            continue
        if a.vmid != e.vmid:
            cambios.append(
                QCoreApplication.translate(
                    "VentanaPrincipal", "el número {a} ya no está libre (ahora se usa el {b})"
                ).format(a=a.vmid, b=e.vmid)
            )
        elif a.nodo != e.nodo:
            cambios.append(
                QCoreApplication.translate("VentanaPrincipal", "«{n}» pasa de {a} a {b}").format(
                    n=e.nombre, a=a.nodo, b=e.nodo
                )
            )
    if len(cambios) > 3:
        resto = len(cambios) - 3
        cambios = [
            *cambios[:3],
            QCoreApplication.translate("VentanaPrincipal", "y %n cambios más", None, resto),
        ]
    return "; ".join(cambios)


class VentanaPrincipal(QMainWindow):
    """Orquesta conexión, descubrimiento, validación en vivo y creación de la MV."""

    def __init__(self, deps: Dependencias, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("ProxLaunch"))
        self.resize(QSize(1240, 820))
        self.setMinimumSize(QSize(1000, 640))
        self._deps = deps
        self._prefs: Preferencias = deps.preferencias.cargar()
        self._lanzador = Lanzador(self)
        self.origen = ControladorOrigen(self._lanzador, deps.perfiles, deps.reloj, self)
        self._sesion: Sesion | None = None
        self._inv: Inventario | None = None
        self._perfil_id: str | None = None
        self._formulario_listo = False
        self._creando = False
        self._cfg_creacion: ConfiguracionVM | None = None
        self._servicio_creacion: ServicioCreacion | None = None
        self._ultimo_resultado: ResultadoCreacion | None = None
        self._bloqueo_permiso: str | None = None
        self._dialogo_conexion: DialogoConexion | None = None
        self._descubriendo = False
        self._upid_recibido: str | None = None
        self._errores_sesion: list[str] = []
        self._avisos_extra: list[str] = []
        # Lotes (MVP 2).
        self._lote: _Lote | None = None
        self._lotes_previos: list[_Lote] = []  # lotes anteriores de la sesión (CA-L21.4)
        self._planificando = False
        self._gen_plan = 0  # cada cancelación lo sube y descarta lo que aún llegue (CA-L11.10)
        self._iniciando_lote = False
        self._plan_mostrado: Plan | None = None
        self._reintento: tuple[ElementoPlan, ...] | None = None
        self._nodo_reintento: str | None = None
        self._fin_uno_inicial = False
        self._sin_etiquetas_forzado = False
        self._aviso_informe_parcial: str | None = None
        self._tomar_aviso_informe_parcial()
        # Perfiles de máquina y lotes guardados (MVP 3).
        self._almacen_perfiles = self._preparar_almacen_perfiles()
        self._cfg_ultima_aplicada: ConfiguracionVM | None = None  # base de «(modificado)»
        self._aplicando = False  # se está volcando un perfil o un lote en el formulario
        self._origen_lote: _OrigenLote | None = None
        self._ruta_lote: Path | None = None  # archivo desde el que se abrió o donde se guardó
        self._huella_guardada: dict[str, object] | None = None  # None = nada que proteger
        self._hay_problemas = False
        self._cierre_confirmado = False
        self._guardando_para_cerrar = False  # escritura asíncrona de «Guardar y cerrar» en curso

        self._construir()
        self._crear_menus()
        self._timer_validar = QTimer(self)
        self._timer_validar.setSingleShot(True)
        self._timer_validar.setInterval(0)
        self._timer_validar.timeout.connect(self._revalidar)
        self.formulario.cambiado.connect(self._timer_validar.start)
        self.formulario.cambiado.connect(self._al_cambiar_formulario)
        self.selector_perfil.perfil_elegido.connect(self._al_elegir_perfil)
        self.selector_perfil.guardar_solicitado.connect(self._guardar_perfil)
        self.selector_perfil.actualizar_solicitado.connect(self._actualizar_perfil)
        self.selector_perfil.administrar_solicitado.connect(self._administrar_perfiles)
        self.panel_filas.resumen_solicitado.connect(self._ver_resumen_lote)
        self.panel_filas.revisar_solicitado.connect(self._revisar_filas)
        self.panel_filas.guardar_solicitado.connect(lambda: self._guardar_lote())
        self.panel_filas.salir_solicitado.connect(self._salir_de_por_filas)
        self.panel_filas.quitar_solicitado.connect(self._quitar_filas)
        self.panel_no_encaja.sustitucion_pedida.connect(self._sustituir_desajuste)
        self.resumen_lote.quitar_excedentes_solicitado.connect(self._quitar_filas_que_no_caben)
        self.resumen_lote.asignar_automatico_solicitado.connect(self._asignar_automaticamente)
        self.formulario.nodo_elegido.connect(self._al_elegir_nodo)
        self.formulario.vmid_confirmado.connect(self._al_confirmar_vmid)
        self.resumen.crear_solicitado.connect(self._crear)
        self.bloque_lote.cambiado.connect(self._timer_validar.start)
        self.bloque_lote.cambiado.connect(self._al_editar_plantilla)
        self.formulario.cambiado.connect(self._al_editar_plantilla)
        self.bloque_lote.destino_cambiado.connect(self._al_cambiar_destino_lote)
        self.resumen_lote.simular_solicitado.connect(self._simular)
        self.resumen_lote.crear_solicitado.connect(self._crear_lote_solicitado)
        self.resumen_lote.reducir_solicitado.connect(self._reducir)
        self.resumen_lote.volver_solicitado.connect(self._volver_del_resumen)
        self.resumen_lote.cancelar_solicitado.connect(self._cancelar_preparacion)
        self.resumen_lote.informe_simulacion_solicitado.connect(self._informe_simulacion)
        self.resumen_lote.nodo_reintento_cambiado.connect(self._al_cambiar_nodo_reintento)
        self.progreso_lote.cancelar_solicitado.connect(self._cancelar_lote)
        self.progreso_lote.dejar_de_esperar_solicitado.connect(self._dejar_de_esperar)
        self.progreso_lote.comprobar_dudosas_solicitado.connect(self._comprobar_dudosas)
        self.progreso_lote.comprobar_una_solicitado.connect(
            lambda vmid: self._comprobar_dudosas(frozenset({vmid}))
        )
        self.progreso_lote.deshacer_solicitado.connect(self._deshacer)
        self.progreso_lote.reintentar_ajustes_solicitado.connect(self._reintentar_ajustes)
        self.progreso_lote.reintentar_solicitado.connect(lambda: self._reintentar_pendientes())
        self.progreso_lote.informe_solicitado.connect(self._mostrar_informe)
        self.progreso_lote.decidir_pausa_solicitado.connect(self._decidir_pausa)
        self.progreso_lote.volver_solicitado.connect(self._volver_de_lote)
        self.progreso.deshacer_solicitado.connect(self._deshacer)
        self._timer_lote = QTimer(self)
        self._timer_lote.setInterval(max(1, 1000 // ACTUALIZACIONES_POR_S))
        self._timer_lote.timeout.connect(self._tick_lote)
        self.progreso.crear_otra.connect(self._crear_otra)
        self.progreso.crear_sin_etiquetas.connect(self._preparar_sin_etiquetas)
        self.progreso.reintentar_ajustes_solicitado.connect(self._reintentar_ajustes_uno)
        self.progreso.seguir_esperando.connect(lambda: self._reanudar(una_vez=False))
        self.progreso.comprobar_ahora.connect(lambda: self._reanudar(una_vez=True))
        self.progreso.volver.connect(self._volver_al_formulario)
        deps.gestor_tema.tema_cambiado.connect(self._al_cambiar_tema)
        self._enlazar_origen()
        self.bloque_lote.establecer_modo(self._prefs.modo == Modo.AVANZADO)
        self.formulario.establecer_modo(self._prefs.modo == Modo.AVANZADO)
        self.origen.establecer_modo(self._prefs.modo == Modo.AVANZADO)
        self.selector_perfil.establecer_modo(self._prefs.modo == Modo.AVANZADO)
        self.selector_perfil.establecer_perfiles(self._almacen_perfiles.todos(), None)
        self._actualizar_acciones()
        self._al_cambiar_tema(deps.gestor_tema.tema_actual)
        self.statusBar().showMessage(self.tr("Sin conexión"))
        # Tamaño y mínimo pedidos, acotados al área útil de la pantalla donde se abre.
        self.ajuste_pantalla = limitar_a_pantalla(
            self, self._paginas, tamano_deseado=QSize(1240, 820)
        )

    # --- Construcción -----------------------------------------------------------------

    def _construir(self) -> None:
        central = QWidget()
        capa = QVBoxLayout(central)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        self.barra = BarraSuperior()
        capa.addWidget(self.barra)
        self._paginas = QStackedWidget()
        # Las páginas van en un área desplazable: si la pantalla es pequeña se desplazan con
        # barras y la barra superior queda fija. El centralWidget sigue siendo ``central``.
        capa.addWidget(crear_area_desplazable(self._paginas), 1)
        self.setCentralWidget(central)

        # Página 0: bienvenida.
        bienvenida = QWidget()
        cb = QVBoxLayout(bienvenida)
        cb.addStretch(1)
        self._logo_bienvenida = QLabel()
        self._logo_bienvenida.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo = QLabel(self.tr("Conecta con tu servidor Proxmox para empezar"))
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fuente = titulo.font()
        fuente.setPointSize(fuente.pointSize() + 4)
        titulo.setFont(fuente)
        self.boton_conectar = QPushButton(self.tr("Conectar..."))
        self.boton_conectar.setProperty("primario", True)
        self.boton_conectar.clicked.connect(lambda: self.abrir_conexion())
        cb.addWidget(self._logo_bienvenida)
        cb.addWidget(titulo)
        cb.addWidget(self.boton_conectar, 0, Qt.AlignmentFlag.AlignCenter)
        cb.addStretch(2)
        self._paginas.addWidget(bienvenida)

        # Página 1: trabajo.
        trabajo = QWidget()
        ct = QVBoxLayout(trabajo)
        ct.setContentsMargins(10, 8, 10, 8)
        self._zona_avisos = QVBoxLayout()
        ct.addLayout(self._zona_avisos)
        fila = QHBoxLayout()
        self.boton_actualizar = QPushButton(self.tr("Actualizar"))
        self.boton_actualizar.clicked.connect(lambda: self._descubrir())
        self._estado_descubrimiento = QLabel()
        self._estado_descubrimiento.setProperty("secundario", True)
        self.boton_reintentar = QPushButton(self.tr("Reintentar"))
        self.boton_reintentar.clicked.connect(self._reintentar_nodos)
        self.boton_reintentar.hide()
        fila.addWidget(self.boton_actualizar)
        fila.addWidget(self._estado_descubrimiento, 1)
        fila.addWidget(self.boton_reintentar)
        ct.addLayout(fila)
        self._nodos_fallidos = mensaje(aviso=True)
        ct.addWidget(self._nodos_fallidos)

        self.formulario = FormularioVM()
        self.bloque_lote = BloqueLote()
        self.selector_perfil = SelectorPerfil()
        self.panel_filas = PanelLoteFilas()
        self.panel_filas.hide()
        self.panel_no_encaja = PanelLoteNoEncaja()
        self.panel_avisos_archivo = PanelAvisos(self.tr("Avisos del archivo"))
        izquierda = QWidget()
        ci = QVBoxLayout(izquierda)
        ci.setContentsMargins(0, 0, 0, 0)
        ci.addWidget(self.selector_perfil)
        ci.addWidget(self.panel_avisos_archivo)
        ci.addWidget(self.panel_no_encaja)
        ci.addWidget(self.bloque_lote)
        ci.addWidget(self.formulario)
        ci.addWidget(self.panel_filas, 1)
        zona = AreaInterna()
        zona.setWidgetResizable(True)
        zona.setFrameShape(QFrame.Shape.NoFrame)
        zona.setWidget(izquierda)
        derecha = QWidget()
        cd = QVBoxLayout(derecha)
        cd.setContentsMargins(0, 0, 0, 0)
        self.resumen = ResumenVM()
        self.progreso = PanelProgreso()
        cd.addWidget(self.resumen)
        cd.addWidget(self.progreso)
        cd.addStretch(1)
        zona_derecha = AreaInterna()
        zona_derecha.setWidgetResizable(True)
        zona_derecha.setFrameShape(QFrame.Shape.NoFrame)
        zona_derecha.setWidget(derecha)
        self.resumen_lote = ResumenLote()
        self.progreso_lote = ProgresoLote()
        self._pila_derecha = QStackedWidget()
        self._pila_derecha.addWidget(zona_derecha)  # 0: resumen y progreso de una máquina
        for pagina in (self.resumen_lote, self.progreso_lote):  # 1 y 2: lotes
            area = AreaInterna()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setWidget(pagina)
            self._pila_derecha.addWidget(area)
        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.addWidget(zona)
        divisor.addWidget(self._pila_derecha)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)
        ct.addWidget(divisor, 1)
        self._paginas.addWidget(trabajo)

    def _crear_menus(self) -> None:
        barra = self.menuBar()
        m_archivo = barra.addMenu(self.tr("&Archivo"))
        a_conectar = QAction(self.tr("Conectar..."), self)
        a_conectar.setShortcut(QKeySequence("Ctrl+K"))
        a_conectar.triggered.connect(lambda: self.abrir_conexion())
        a_cerrar = QAction(self.tr("Cerrar sesión"), self)
        a_cerrar.triggered.connect(self._cerrar_sesion)
        a_salir = QAction(self.tr("Salir"), self)
        a_salir.setShortcut(QKeySequence.StandardKey.Quit)
        a_salir.triggered.connect(self.close)
        self._accion_ultimo_lote = QAction(self.tr("Ver el último lote"), self)
        self._accion_ultimo_lote.setEnabled(False)
        self._accion_ultimo_lote.triggered.connect(self._ver_ultimo_lote)
        self._accion_archivos_subidos = QAction(self.tr("Archivos subidos en esta sesión…"), self)
        self._accion_archivos_subidos.triggered.connect(self._ver_archivos_subidos)
        m_archivo.addActions(
            [a_conectar, a_cerrar, self._accion_ultimo_lote, self._accion_archivos_subidos]
        )
        m_archivo.addSeparator()
        m_archivo.addAction(a_salir)

        m_lote = barra.addMenu(self.tr("&Lote"))
        self._accion_abrir_lote = QAction(self.tr("Abrir lote…"), self)
        self._accion_abrir_lote.setShortcut(QKeySequence("Ctrl+O"))
        self._accion_abrir_lote.triggered.connect(self._abrir_lote)
        self._accion_guardar_lote = QAction(self.tr("Guardar lote…"), self)
        self._accion_guardar_lote.setShortcut(QKeySequence("Ctrl+S"))
        self._accion_guardar_lote.triggered.connect(lambda: self._guardar_lote())
        self._accion_guardar_lote_como = QAction(self.tr("Guardar lote como…"), self)
        self._accion_guardar_lote_como.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._accion_guardar_lote_como.triggered.connect(lambda: self._guardar_lote(como=True))
        self._accion_importar_csv = QAction(self.tr("Importar desde CSV…"), self)
        self._accion_importar_csv.triggered.connect(self._importar_csv)
        self._accion_plantilla_csv = QAction(self.tr("Descargar plantilla CSV…"), self)
        self._accion_plantilla_csv.triggered.connect(self._descargar_plantilla_csv)
        self._accion_informe_csv = QAction(self.tr("Guardar el informe del lote como CSV…"), self)
        self._accion_informe_csv.triggered.connect(self._guardar_informe_csv)
        m_lote.addActions([self._accion_abrir_lote, self._accion_guardar_lote])
        m_lote.addAction(self._accion_guardar_lote_como)
        m_lote.addSeparator()
        m_lote.addActions([self._accion_importar_csv, self._accion_plantilla_csv])
        m_lote.addSeparator()
        m_lote.addAction(self._accion_informe_csv)

        m_perfiles = barra.addMenu(self.tr("&Perfiles"))
        self._accion_guardar_perfil = QAction(self.tr("Guardar como perfil de máquina…"), self)
        self._accion_guardar_perfil.triggered.connect(self._guardar_perfil)
        self._accion_administrar_perfiles = QAction(self.tr("Administrar perfiles…"), self)
        self._accion_administrar_perfiles.triggered.connect(self._administrar_perfiles)
        self._accion_administrar_perfiles.setVisible(self._prefs.modo == Modo.AVANZADO)
        m_perfiles.addActions([self._accion_guardar_perfil, self._accion_administrar_perfiles])

        m_ver = barra.addMenu(self.tr("&Ajustes"))
        self._accion_recordados = QAction(self.tr("Almacenamientos recordados…"), self)
        self._accion_recordados.triggered.connect(lambda: self.origen.revisar_recordados(self))
        m_ver.addAction(self._accion_recordados)
        m_tema = m_ver.addMenu(self.tr("Tema"))
        self._grupo_tema = QActionGroup(self)
        self._acciones_tema: dict[ModoTema, QAction] = {}
        for modo, texto in (
            (ModoTema.AUTOMATICO, self.tr("Automático")),
            (ModoTema.OSCURO, self.tr("Oscuro")),
            (ModoTema.CLARO, self.tr("Claro")),
        ):
            accion = QAction(texto, self, checkable=True)
            accion.setChecked(self._deps.gestor_tema.modo == modo)
            accion.triggered.connect(lambda _c=False, m=modo: self.establecer_tema(m))
            self._grupo_tema.addAction(accion)
            m_tema.addAction(accion)
            self._acciones_tema[modo] = accion
        m_modo = m_ver.addMenu(self.tr("Modo"))
        self._grupo_modo = QActionGroup(self)
        self._acciones_modo: dict[Modo, QAction] = {}
        for modo_i, texto in (
            (Modo.BASICO, self.tr("Básico")),
            (Modo.AVANZADO, self.tr("Avanzado")),
        ):
            accion = QAction(texto, self, checkable=True)
            accion.setChecked(self._prefs.modo == modo_i)
            accion.triggered.connect(lambda _c=False, m=modo_i: self.establecer_modo(m))
            self._grupo_modo.addAction(accion)
            m_modo.addAction(accion)
            self._acciones_modo[modo_i] = accion

        m_ayuda = barra.addMenu(self.tr("A&yuda"))
        a_guia = QAction(self.tr("¿Cómo creo un API Token?"), self)
        a_guia.triggered.connect(lambda: self._mostrar_y_borrar(DialogoGuiaToken(self)))
        a_acerca = QAction(self.tr("Acerca de ProxLaunch"), self)
        a_acerca.triggered.connect(
            lambda: self._mostrar_y_borrar(
                DialogoAcercaDe(self._deps.gestor_tema.tema_actual, self)
            )
        )
        self._accion_capacidades = QAction(self.tr("Qué puedo hacer en este servidor…"), self)
        self._accion_capacidades.triggered.connect(
            self.formulario.selector_origen.abrir_capacidades
        )
        m_ayuda.addActions([self._accion_capacidades, a_guia, a_acerca])

    @staticmethod
    def _mostrar_y_borrar(dialogo: QDialog) -> None:
        dialogo.exec()
        dialogo.deleteLater()

    # --- Ajustes persistentes ---------------------------------------------------------

    def establecer_tema(self, modo: ModoTema) -> None:
        """Cambia el tema y lo guarda (RF-22)."""
        self._deps.gestor_tema.establecer_modo(modo)
        self._prefs.tema = Tema(modo.value)
        self._guardar_preferencias()
        self._acciones_tema[modo].setChecked(True)

    def establecer_modo(self, modo: Modo) -> None:
        """Cambia entre básico y avanzado sin perder lo escrito (RF-24) y lo guarda."""
        self._prefs.modo = modo
        self._guardar_preferencias()
        self._acciones_modo[modo].setChecked(True)
        self.formulario.establecer_modo(modo == Modo.AVANZADO)
        self.origen.establecer_modo(modo == Modo.AVANZADO)
        self.bloque_lote.establecer_modo(modo == Modo.AVANZADO)
        self.selector_perfil.establecer_modo(modo == Modo.AVANZADO)
        self._accion_administrar_perfiles.setVisible(modo == Modo.AVANZADO)
        self._actualizar_barra()
        self._timer_validar.start()

    def _guardar_preferencias(self) -> None:
        try:
            self._deps.preferencias.guardar(self._prefs)
        except OSError:
            _log.exception("No se pudieron guardar las preferencias")

    def _al_cambiar_tema(self, tema: str) -> None:
        pixmap = cargar_svg(nombre_logotipo(tema), QSize(240, 148), self.devicePixelRatioF())
        self._logo_bienvenida.setPixmap(pixmap)
        self.barra.actualizar_logo(tema)
        self.progreso_lote.establecer_tema(tema)
        self.origen.establecer_tema(tema)

    def _enlazar_origen(self) -> None:
        """Conecta el selector del formulario con el controlador del origen del SO."""
        self.origen.enlazar(self.formulario.selector_origen, self.formulario.nodo_efectivo)
        self.origen.catalogo_cargado.connect(lambda _c: self._timer_validar.start())
        self.origen.fallo.connect(lambda e: self._manejar_fallo(e, durante="al leer el catálogo"))
        self.origen.mensaje.connect(self.statusBar().showMessage)
        self.origen.storage_mv_elegido.connect(self.formulario.usar_storage_mv)
        self.origen.transferencia_terminada.connect(lambda _r: self._timer_validar.start())

    @property
    def avanzado(self) -> bool:
        return self._prefs.modo == Modo.AVANZADO

    # --- Conexión ---------------------------------------------------------------------

    def abrir_conexion(self, motivo: str | None = None) -> None:
        """Abre el diálogo de conexión (sin perder el formulario, CA-03.3).

        Si el usuario la pide con un lote con cambios sin guardar, antes se le pregunta (RF-G08).
        """
        if motivo is None and self._sesion is not None and self._hay_cambios_sin_guardar():
            self._confirmar_cambios(lambda: self._abrir_conexion(None))
            return
        self._abrir_conexion(motivo)

    def _abrir_conexion(self, motivo: str | None) -> None:
        if self._dialogo_conexion is not None or self._creando or self._lote_bloquea_conexion():
            return
        dialogo = DialogoConexion(
            self._deps.servicio_conexion,
            self._deps.perfiles,
            self._deps.huellas,
            self._deps.secretos,
            self._lanzador,
            candidatos_storage=self._candidatos_storage(),
            avanzado=self.avanzado,
            version_forzada=self._prefs.version_forzada,
            perfil_id=self._perfil_id,
            motivo=motivo,
            parent=self,
        )
        self._dialogo_conexion = dialogo
        dialogo.accepted.connect(lambda: self._al_conectar(dialogo))
        dialogo.finished.connect(lambda _r: self._dialogo_cerrado(dialogo))
        dialogo.open()

    def _candidatos_storage(self) -> dict[Contenido, tuple[str, ...]]:
        """Almacenamientos del servidor conectado, para elegir cuál recordar (RF-O05)."""
        inv = self._inv
        if inv is None:
            return {}
        return {c: candidatos_servidor(inv, c) for c in Contenido}

    def _dialogo_cerrado(self, dialogo: DialogoConexion) -> None:
        self._dialogo_conexion = None
        dialogo.deleteLater()
        lote = self._lote
        if lote is not None and lote.esperando_reconexion and not lote.cerrado:
            # Se cerró el diálogo sin reconectar: el lote queda detenido con sus pendientes.
            lote.esperando_reconexion = False
            self._finalizar_lote()

    def _al_conectar(self, dialogo: DialogoConexion) -> None:
        sesion = dialogo.sesion
        perfil = dialogo.perfil_conectado
        if sesion is None or perfil is None:
            return
        cambio_perfil = perfil.id != self._perfil_id
        self._sesion = sesion
        self._perfil_id = perfil.id
        self.origen.establecer_sesion(sesion, None if cambio_perfil else self._inv)
        self._restaurar_etiquetado()
        if dialogo.version_forzada != self._prefs.version_forzada:
            self._prefs.version_forzada = dialogo.version_forzada
            self._guardar_preferencias()
        self._avisos_extra = []
        if dialogo.uso_clave_recuperacion:
            self._avisos_extra.append(
                self.tr("Esa clave de recuperación ya no se puede volver a usar")
            )
        self._errores_sesion = []
        self._actualizar_barra()
        primero = perfil.hosts[0] if perfil.hosts else ""
        if sesion.host_activo and sesion.host_activo != primero:
            texto = self.tr("Conectado a {b} ({a} no respondió)").format(
                a=primero, b=sesion.host_activo
            )
        else:
            texto = self.tr("Conectado")
        self.statusBar().showMessage(texto)
        self._paginas.setCurrentIndex(1)
        lote = self._lote
        continuar = lote is not None and lote.esperando_reconexion and not cambio_perfil
        if cambio_perfil and lote is not None:
            self._cerrar_lote_por_cambio_de_perfil(lote)
        if cambio_perfil:
            # Un lote cargado o importado se conserva en el formulario con el servidor nuevo;
            # su resumen y sus desajustes se recalculan con el inventario nuevo (CA-G04.8).
            if self._origen_lote is None:
                self._formulario_listo = False
            self.panel_no_encaja.establecer_desajustes(())
            self._al_editar_plantilla()
            self._inv = None
            # Un resultado pendiente de otro servidor ya no se puede retomar.
            self._ultimo_resultado = None
            self._servicio_creacion = None
            self._cfg_creacion = None
            self._upid_recibido = None
            self.progreso.reiniciar()
            self._bloquear_edicion(False)
            self.resumen.liberar()
        if continuar and lote is not None:
            self._continuar_lote(lote, sesion=sesion, comprobar=True)
            return
        self._descubrir()

    def _actualizar_barra(self) -> None:
        sesion = self._sesion
        if sesion is None:
            self.barra.limpiar()
            return
        perfil = sesion.perfil
        self.barra.establecer_conexion(
            perfil.nombre,
            sesion.version.texto,
            sesion.capacidades.forzada,
            perfil.ignorar_ssl,
            sesion.usuario_efectivo,
        )
        if self._inv is not None:
            self.barra.establecer_topologia(self._inv.topologia, self._topologia_degradada())

    def _topologia_degradada(self) -> bool:
        return self._sesion is not None and any(
            a.codigo == CodigoAviso.TOPOLOGIA_DEGRADADA for a in self._sesion.avisos
        )

    def _cerrar_sesion(self) -> None:
        if self._creando or self._lote_en_curso or self.origen.transferencia_activa:
            return
        # Un lote importado o editado no se pierde sin preguntar (RF-G08).
        self._confirmar_cambios(self._cerrar_sesion_confirmada)

    def _cerrar_sesion_confirmada(self) -> None:
        if self._creando or self._lote_en_curso:
            return  # pudo cambiar mientras se guardaba el lote
        sesion = self._sesion
        if sesion is not None:
            try:
                self._deps.servicio_conexion.cerrar_sesion(sesion)
            except ErrorProxLaunch:
                _log.warning("No se pudo cerrar la sesión limpiamente")
        self._sesion = None
        self.origen.establecer_sesion(None, None)
        self._restaurar_etiquetado()
        self._inv = None
        if self._origen_lote is None:
            # Un lote cargado o importado se conserva: al reconectar no se reinicia el
            # formulario (igual que al cambiar de servidor).
            self._formulario_listo = False
        self._perfil_id = None
        self._ultimo_resultado = None
        self.barra.limpiar()
        self._paginas.setCurrentIndex(0)
        self.statusBar().showMessage(self.tr("Sin conexión"))
        self._actualizar_acciones()

    def _manejar_fallo(self, error: ErrorProxLaunch, *, durante: str = "") -> None:
        """Gestiona el error de una operación de red; reabre la conexión si expiró."""
        if error.codigo == CodigoError.SESION_EXPIRADA:
            self.abrir_conexion(texto_error(error))
            return
        self._errores_sesion = [texto_error(error)]
        self._pintar_avisos()
        self.statusBar().showMessage(texto_error(error))
        _log.warning("Fallo %s: %s", durante, error.codigo)

    # --- Avisos -----------------------------------------------------------------------

    def _pintar_avisos(self) -> None:
        while self._zona_avisos.count():
            item = self._zona_avisos.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        textos_aviso = list(self._avisos_extra) + self._avisos_archivos()
        if self._aviso_informe_parcial:
            textos_aviso.append(self._aviso_informe_parcial)
        if self._sesion is not None:
            textos_aviso.extend(texto_aviso(a) for a in self._sesion.avisos)
        for texto in dict.fromkeys(textos_aviso):
            self._zona_avisos.addWidget(self._etiqueta_aviso(texto, error=False))
        for texto in self._errores_sesion:
            self._zona_avisos.addWidget(self._etiqueta_aviso(texto, error=True))

    def _avisos_archivos(self) -> list[str]:
        """Avisa si algún archivo de datos estaba dañado o no se pudo leer (RNF-15)."""
        avisos: list[str] = []
        huellas = self._deps.huellas
        if huellas.error_lectura:
            avisos.append(self.tr("No se pudo leer el archivo de huellas (permisos)"))
        elif huellas.hubo_corrupcion:
            avisos.append(
                self.tr(
                    "Se dañó el archivo de huellas; se recuperaron {n} servidores. Los demás "
                    "tendrás que confirmarlos de nuevo comparando la huella con tu "
                    "administrador."
                ).format(n=len(huellas.huellas_recuperadas))
            )
        perfiles = self._deps.perfiles
        if perfiles.error_lectura:
            avisos.append(self.tr("No se pudo leer el archivo de perfiles (permisos)"))
        elif perfiles.hubo_corrupcion:
            avisos.append(
                self.tr(
                    "El archivo de perfiles estaba dañado: se guardó una copia y se empezó uno "
                    "nuevo."
                )
            )
        if self._deps.preferencias.error_lectura:
            avisos.append(self.tr("No se pudo leer el archivo de preferencias (permisos)"))
        avisos.extend(self._avisos_perfiles_maquina())
        return avisos

    @staticmethod
    def _etiqueta_aviso(texto: str, *, error: bool) -> QLabel:
        lbl = QLabel(texto)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.PlainText)
        lbl.setProperty("error" if error else "aviso", True)
        return lbl

    # --- Descubrimiento ---------------------------------------------------------------

    def _descubrir(self) -> None:
        sesion = self._sesion
        if sesion is None or self._descubriendo or self._creando or self._lote_en_curso:
            return
        self._descubriendo = True
        self._refrescar_botones_red()
        self._estado_descubrimiento.setText(self.tr("Buscando nodos, almacenamientos y redes..."))
        self._errores_sesion = []
        self._lanzador.lanzar(
            descubrir_y_comprobar_permisos,
            sesion,
            al_terminar=self._al_descubierto,
            al_fallar=self._fallo_descubrimiento,
        )

    def _fallo_descubrimiento(self, error: ErrorProxLaunch) -> None:
        self._descubriendo = False
        self._refrescar_botones_red()
        self._estado_descubrimiento.setText(self.tr("No se pudo leer el servidor."))
        self._manejar_fallo(error, durante="en el descubrimiento")

    def _al_descubierto(self, resultado: tuple[Inventario, list[str] | None]) -> None:
        inv, _faltantes = resultado
        self._descubriendo = False
        self._refrescar_botones_red()
        self._inv = self.origen.adoptar(inv)
        self.formulario.establecer_storage_recordado(self.origen.recordado(Contenido.IMAGENES))
        self._estado_descubrimiento.setText(
            self.tr("{n} nodo(s) encontrados.").format(n=len(inv.topologia.nodos))
        )
        self._actualizar_barra()
        self._bloqueo_permiso = None
        if self._sesion is not None and any(
            privilegio_faltante_critico(a) for a in self._sesion.avisos
        ):
            self._bloqueo_permiso = self.tr(
                "Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate"
            )
        self._mostrar_nodos_fallidos()
        reiniciar = not self._formulario_listo
        if reiniciar:
            self._reiniciar_lote()
        self.bloque_lote.establecer_inventario(inv)
        self.formulario.establecer_inventario(inv, reiniciar=reiniciar)
        self._formulario_listo = True
        if reiniciar:
            self._fijar_perfil_inicial(inv)
        self._pintar_avisos()
        self._timer_validar.start()

    def _reiniciar_lote(self) -> None:
        """Deja el lote como recién abierto: sin archivo de origen y con el bloque por defecto.

        Va siempre que se reinicia el formulario, para que un lote armado a mano o cargado de
        antes no sobreviva (ni se sobrescriba luego con el hardware por defecto).
        """
        self._ruta_lote = None
        self._origen_lote = None
        self._huella_guardada = None
        self.bloque_lote.reiniciar()  # cantidad 1, sin prefijo, automático, sin nodos ausentes
        self._mostrar_modo_filas(False)
        self.panel_no_encaja.establecer_desajustes(())
        self.panel_avisos_archivo.mostrar([])
        self.resumen_lote.establecer_total_filas_archivo(None)

    def _mostrar_nodos_fallidos(self) -> None:
        inv = self._inv
        fallidos = sorted(inv.errores_por_nodo) if inv is not None else []
        if fallidos:
            poner_mensaje(
                self._nodos_fallidos,
                self.tr("No se pudo leer el nodo {nodos}: aparece como «Sin conexión».").format(
                    nodos=", ".join(fallidos)
                ),
                aviso=True,
            )
        else:
            poner_mensaje(self._nodos_fallidos, None)
        self.boton_reintentar.setVisible(bool(fallidos))

    def _reintentar_nodos(self) -> None:
        sesion, inv = self._sesion, self._inv
        if (
            sesion is None
            or inv is None
            or not inv.errores_por_nodo
            or self._creando
            or self._lote_en_curso
        ):
            return
        self.boton_reintentar.setEnabled(False)
        self._lanzador.lanzar(
            reintentar_nodos,
            sesion,
            sorted(inv.errores_por_nodo),
            al_terminar=self._tras_reintento,
            al_fallar=lambda e: self._manejar_fallo(e, durante="al reintentar nodos"),
        )

    def _tras_reintento(self, resultado: Any) -> None:
        recuperados, _fallidos = resultado
        inv = self._inv
        self._refrescar_botones_red()
        if inv is None:
            return
        for nodo, (storages, bridges, *resto) in recuperados.items():
            inv.storages[nodo] = tuple(storages)
            inv.bridges[nodo] = tuple(bridges)
            if resto:  # ``storages_todos`` sale de la misma respuesta (origen del SO)
                inv.storages_todos[nodo] = tuple(resto[0])
            inv.errores_por_nodo.pop(nodo, None)
        if recuperados:
            nodos = tuple(
                dataclasses.replace(n, en_linea=True) if n.nombre in recuperados else n
                for n in inv.topologia.nodos
            )
            inv.topologia = dataclasses.replace(inv.topologia, nodos=nodos)
            self.formulario.establecer_inventario(inv)
            self.bloque_lote.establecer_inventario(inv)
        self._mostrar_nodos_fallidos()
        self._timer_validar.start()

    def _al_elegir_nodo(self, nodo: str) -> None:
        """CA-11.7: al cambiar de nodo se recargan sus storages y bridges."""
        sesion = self._sesion
        if sesion is None:
            return
        self._lanzador.lanzar(
            recargar_nodo,
            sesion,
            nodo,
            al_terminar=self._tras_recargar_nodo,
            al_fallar=lambda e: self._manejar_fallo(e, durante="al cambiar de nodo"),
        )

    def _tras_recargar_nodo(self, r: tuple[Any, ...]) -> None:
        if self._inv is not None and len(r) > 3:
            self._inv.storages_todos[r[0]] = tuple(r[3])
        self.formulario.actualizar_recursos_nodo(r[0], r[1], r[2])

    def _al_confirmar_vmid(self, vmid: int) -> None:
        """V-03: comprueba en segundo plano que el VMID escrito está libre (CA-13.2)."""
        sesion = self._sesion
        if sesion is None:
            return
        self._lanzador.lanzar(
            comprobar_vmid,
            sesion,
            vmid,
            al_terminar=self._tras_comprobar_vmid,
            al_fallar=lambda e: self._manejar_fallo(e, durante="al comprobar el VMID"),
        )

    def _tras_comprobar_vmid(self, resultado: tuple[int, str | None]) -> None:
        vmid, siguiente = resultado
        if siguiente is None:
            self.formulario.limpiar_vmid_ocupado()
        else:
            self.formulario.marcar_vmid_ocupado(vmid, siguiente)

    # --- Validación en vivo -----------------------------------------------------------

    def _revalidar(self) -> None:
        self._actualizar_acciones()
        sesion, inv = self._sesion, self._inv
        if sesion is None or inv is None:
            return
        if self.bloque_lote.es_por_filas:
            self._revalidar_por_filas()
            return
        en_lote = self.bloque_lote.es_lote
        if en_lote != self.formulario.modo_lote:
            self.formulario.establecer_lote(en_lote)
            self.resumen.establecer_modo_lote(en_lote)
        cfg = self.formulario.configuracion()
        self.origen.sincronizar(cfg)
        cfg, problemas_origen = self.origen.resolver(cfg)
        problemas_lote = self.bloque_lote.problemas(cfg)
        self.bloque_lote.aplicar_problemas(problemas_lote)
        if en_lote:
            # El nombre y el VMID de cada máquina los fija el plan: aquí solo se muestran de
            # ejemplo y no se validan (V-L02..V-L07 ya los cubren).
            nombres = self.bloque_lote.nombres_previstos()
            cfg.nombre = nombres[0] if nombres else ""
            cfg.vmid = self.bloque_lote.definicion(cfg).vmid_inicial or inv.proximo_vmid
        problemas = validar_vm(cfg, inv, sesion.capacidades) + self.formulario.problemas_extra()
        vistos = {(p.codigo, p.campo) for p in problemas}
        problemas += [p for p in problemas_origen if (p.codigo, p.campo) not in vistos]
        if en_lote:
            problemas = [p for p in problemas if p.campo not in ("nombre", "vmid")]
        self._hay_problemas = any(p.severidad == Severidad.ERROR for p in problemas) or any(
            p.severidad.value == "error" for p in problemas_lote
        )
        self._actualizar_compatibilidad(cfg, en_lote=en_lote)
        desajuste_nodo = False
        if self._origen_lote is not None:
            self._actualizar_desajustes()
            # Un nodo elegido que el servidor no tiene bloquea igual que storage y bridge
            # (CA-G04.3) hasta quitarlo de la lista o pasar a Automático.
            desajuste_nodo = any(
                d.tipo == TipoDesajuste.NODO for d in desajustes(self._definicion_actual(), inv)
            )
            if desajuste_nodo:
                self._hay_problemas = True
        self.formulario.aplicar_problemas(problemas)
        motivo = (
            texto_motivo_nodo(self.formulario.motivo_nodo)
            if self.formulario.es_automatico and self.formulario.motivo_nodo and not en_lote
            else ""
        )
        nodo = next((n for n in inv.topologia.nodos if n.nombre == cfg.nodo), None)
        bloqueo = None if en_lote else self._bloqueo_permiso
        errores_lote = [p for p in problemas_lote if p.severidad.value == "error"]
        if errores_lote:
            bloqueo = texto_problema_lote(errores_lote[0])
        elif desajuste_nodo:
            bloqueo = self.tr(
                "Este servidor no tiene uno de los nodos del lote. Quítalo de la lista o pasa a "
                "Automático para continuar."
            )
        self.resumen.actualizar(
            cfg,
            self.formulario.etiquetas_discos(),
            problemas,
            avanzado=self.avanzado,
            motivo_nodo=motivo,
            bloqueo=bloqueo,
            ocupado=self._creando or self._lote_en_curso or self._planificando,
            nodo=nodo,
            cambios_asistente=self.formulario.selector_origen.cambios_asistente,
            permisos=inv.catalogo.permisos if inv.catalogo is not None else None,
        )

    # --- Creación ---------------------------------------------------------------------

    def _crear(self) -> None:
        sesion, inv = self._sesion, self._inv
        # CA-19.6: la bandera se pone antes de lanzar nada; un segundo clic no hace nada.
        if self._creando or self._lote_en_curso or sesion is None or inv is None:
            return
        if self.bloque_lote.es_lote:
            self.resumen.liberar()
            self._ver_resumen_lote()
            self._timer_validar.start()
            return
        self._creando = True
        self._upid_recibido = None
        cfg, _ = self.origen.resolver(self.formulario.configuracion())
        self._cfg_creacion = cfg
        self._bloquear_edicion(True)
        self.progreso.iniciar()
        self._refrescar_botones_red()
        # CA-L18.13: una máquina también pasa por el motor, para etiquetarla y poder deshacerla.
        plan = self._plan_de_uno(cfg, sesion)
        self._iniciar_lote(plan, inv, modo_uno=True)
        self._timer_validar.start()

    def _plan_de_uno(self, cfg: ConfiguracionVM, sesion: Sesion) -> Plan:
        """Plan de una sola máquina con el nombre, VMID y nodo que escribió el usuario."""
        etiquetar = self.bloque_lote.chk_etiquetar.isChecked()
        id_lote = secrets.token_hex(4)
        propias = (ETIQUETA_APP, f"{PREFIJO_ETIQUETA_LOTE}{id_lote}") if etiquetar else ()
        cfg_final = dataclasses.replace(cfg, etiquetas=tuple(cfg.etiquetas) + propias)
        definicion = DefinicionLote(
            plantilla=cfg,
            cantidad=1,
            patron=PatronNombres(prefijo=cfg.nombre),
            destino=Destino(ModoDestino.UN_NODO, (cfg.nodo,)),
            vmid_inicial=cfg.vmid,
            etiquetar=etiquetar,
        )
        return Plan(
            id_lote=id_lote,
            definicion=definicion,
            elementos=(ElementoPlan(0, cfg.nombre, cfg.vmid, cfg.nodo, cfg_final),),
            vmids_saltados=(),
            reparto={cfg.nodo: (1, MotivoReparto.ELEGIDO_POR_USUARIO.value)},
            uso={},
            problemas=(),
            capacidad_maxima=None,
            generado_en=self._deps.reloj.ahora(),
            version_validacion=sesion.capacidades.version,
            catalogo=self._inv.catalogo
            if cfg.origen != OrigenSO.DISCO_VACIO and self._inv
            else None,
        )

    def _nuevo_servicio_creacion(self, sesion: Sesion) -> ServicioCreacion:
        """Servicio ligado a la sesión ACTUAL (la anterior pudo expirar o cambiar)."""
        fabrica = self._deps.fabrica_creacion
        return fabrica(sesion) if fabrica else ServicioCreacion(sesion, self._deps.reloj)

    def _refrescar_botones_red(self) -> None:
        """«Actualizar» y «Reintentar» no se usan mientras se crea o se descubre."""
        libre = not self._creando and not self._descubriendo and not self._lote_en_curso
        self.boton_actualizar.setEnabled(libre)
        self.boton_reintentar.setEnabled(libre)

    def _al_upid(self, upid: str) -> None:
        """Muestra el UPID en cuanto Proxmox acepta la petición."""
        self._upid_recibido = upid
        self.progreso.establecer_upid(upid)
        cfg = self._cfg_creacion
        if cfg is not None:
            self.progreso.detalles.establecer(f"UPID: {upid}\nVMID: {cfg.vmid}\nNodo: {cfg.nodo}")

    def _al_etapa(self, etapa: Etapa) -> None:
        self.progreso.establecer_etapa(etapa)

    def _fallo_creacion(self, error: ErrorProxLaunch) -> None:
        """Error inesperado fuera del flujo normal del servicio.

        Si la petición pudo haber salido, no se sabe el estado real: se trata como conexión
        perdida (con el UPID ya mostrado, si lo hay) y no se desbloquea el formulario.
        """
        cfg = self._cfg_creacion
        if cfg is None:
            self._creando = False
            return
        self._al_terminar_creacion(
            ResultadoCreacion(
                Desenlace.CONEXION_PERDIDA, cfg.vmid, cfg.nodo, self._upid_recibido, error
            )
        )

    def _al_terminar_creacion(self, resultado: ResultadoCreacion, aviso: str = "") -> None:
        cfg = self._cfg_creacion
        self._creando = False
        self._restaurar_etiquetado()  # el desmarcado forzado vale para una sola creación
        self._refrescar_botones_red()
        self._ultimo_resultado = resultado
        self._sincronizar_libro_uno(resultado)
        nombre = cfg.nombre if cfg else ""
        texto = texto_desenlace(resultado, nombre)
        d = resultado.desenlace
        if resultado.error is not None and d == Desenlace.CON_AVISOS:
            texto += "\n" + texto_error(resultado.error)
        elif (
            resultado.error is not None
            and d == Desenlace.CONEXION_PERDIDA
            and (
                resultado.error.codigo
                in (CodigoError.LOTE_ENVIO_INCIERTO, CodigoError.LOTE_EXISTENCIA_INDETERMINADA)
                or (
                    resultado.error.codigo == CodigoError.SERVIDOR_NO_RESPONDE
                    and resultado.error.params.get("incierto") == "1"
                )
            )
        ):
            texto = texto_error(resultado.error)
        if aviso:
            texto += "\n" + aviso  # CA-L15.2: se creó, pero Proxmox tardó en responder
        if d in (Desenlace.OK, Desenlace.CON_AVISOS):
            # El motor no emite LISTO: al terminar bien se marcan todas las etapas como hechas.
            self.progreso.establecer_etapa(Etapa.LISTO)
        self.progreso.mostrar_resultado(texto, d, resultado.upid)
        self.progreso.detalles.establecer(
            texto_detalles(resultado.error, resultado),
            desplegar=d == Desenlace.CON_AVISOS and bool(resultado.log_tarea),
        )
        error = resultado.error
        lote_uno = self._lote
        if (
            error is not None
            and error.codigo == CodigoError.ETIQUETA_RECHAZADA
            and d == Desenlace.ERROR
            and lote_uno is not None
            and lote_uno.modo_uno
            and lote_uno.plan.definicion.etiquetar
        ):
            # Un solo equipo: la tarea falló de forma definitiva, así que se puede ofrecer otra vez.
            texto += "\n" + self.tr(
                "El servidor no permite poner etiquetas a las máquinas. Puedes crearla sin "
                "etiquetas; después, «Deshacer» solo podrá eliminarla si el nombre coincide."
            )
            self.progreso.mostrar_resultado(texto, d, resultado.upid)
            self.progreso.ofrecer_sin_etiquetas(True)
        self.statusBar().showMessage(texto.splitlines()[0] if texto else "")
        if d in (Desenlace.OK, Desenlace.CON_AVISOS, Desenlace.TIEMPO_AGOTADO):
            pass  # el formulario sigue bloqueado hasta «Crear otra» o «Volver»
        elif d == Desenlace.CONEXION_PERDIDA:
            pass
        else:
            self._desbloquear()
        if error is not None:
            if error.codigo == CodigoError.VMID_OCUPADO and cfg is not None:
                self.formulario.marcar_vmid_ocupado(cfg.vmid, error.params.get("siguiente"))
            elif error.codigo == CodigoError.NODO_NO_DISPONIBLE:
                self._descubrir()  # CA-13.7: se ofrece volver a elegir con datos frescos
            elif error.codigo == CodigoError.SESION_EXPIRADA:
                self.abrir_conexion(texto_error(error))
        self._timer_validar.start()

    def _desbloquear(self) -> None:
        self._bloquear_edicion(False)
        self.resumen.liberar()

    def _restaurar_etiquetado(self) -> None:
        """Devuelve la casilla a «marcada» si solo estaba desmarcada por el rechazo (un uso)."""
        if self._sin_etiquetas_forzado:
            self._sin_etiquetas_forzado = False
            self.bloque_lote.chk_etiquetar.setChecked(True)

    def _preparar_sin_etiquetas(self) -> None:
        """Vuelve al formulario con «Etiquetar las máquinas» desmarcada y datos frescos.

        La creación pasa por el flujo normal (validación, VMID reconsultado y «Crear»).
        """
        if self._creando:
            return
        self._sin_etiquetas_forzado = True
        self.bloque_lote.chk_etiquetar.setChecked(False)
        self.progreso.reiniciar()
        self._desbloquear()
        self._descubrir()  # refresca VMID libre y permisos antes de volver a crear
        self.statusBar().showMessage(
            self.tr("Etiquetas desactivadas. Pulsa «Crear» para crear la máquina sin ellas.")
        )
        self._timer_validar.start()

    def _volver_al_formulario(self) -> None:
        if self._creando:
            return
        res = self._ultimo_resultado
        if res is not None and res.desenlace in (
            Desenlace.CONEXION_PERDIDA,
            Desenlace.TIEMPO_AGOTADO,
        ):
            # Aún no se sabe si la máquina se creó: volver y repetir podría duplicarla.
            boton = QMessageBox.question(
                self,
                self.tr("Todavía no sabemos si se creó"),
                self.tr(
                    "No hemos podido confirmar si la máquina se creó. Si vuelves al formulario "
                    "y la creas otra vez, podrías duplicarla. ¿Volver de todos modos?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if boton != QMessageBox.StandardButton.Yes:
                return
        self._restaurar_etiquetado()
        self.progreso.reiniciar()
        self._desbloquear()
        self._timer_validar.start()

    def _crear_otra(self) -> None:
        if self._creando:
            return
        self.progreso.reiniciar()
        self._desbloquear()
        self._restaurar_etiquetado()
        self.formulario.preparar_otra()
        self._descubrir()  # refresca VMID y espacio libre
        self._timer_validar.start()

    def _reanudar(self, *, una_vez: bool) -> None:
        sesion, cfg, res = self._sesion, self._cfg_creacion, self._ultimo_resultado
        if self._creando or sesion is None or cfg is None or res is None:
            return
        # Siempre con la sesión actual: la de la creación pudo expirar o cambiar.
        servicio = self._nuevo_servicio_creacion(sesion)
        self._servicio_creacion = servicio
        self._creando = True
        self._refrescar_botones_red()
        if not res.upid:
            # Envío incierto: se comprueba si la máquina existe, sin volver a enviar nada.
            self.progreso.mostrar_progreso_mensaje(self.tr("Comprobando si la máquina existe..."))
            lote = self._lote
            id_lote = lote.plan.id_lote if lote is not None else ""
            etiquetar = lote.plan.definicion.etiquetar if lote is not None else False
            self._lanzador.lanzar(
                comprobar_existencia,
                servicio,
                cfg,
                sesion.cliente,
                id_lote,
                etiquetar,
                al_terminar=self._tras_existencia,
                al_fallar=self._fallo_reanudar,
            )
            return
        self.progreso.mostrar_progreso_mensaje(
            self.tr("Comprobando la tarea...")
            if una_vez
            else self.tr("Esperando a que termine la tarea...")
        )
        self._lanzador.lanzar(
            reanudar_seguimiento,
            servicio,
            cfg,
            res.upid,
            una_vez,
            self._inv,
            con_contexto=True,
            al_etapa=self._al_etapa,
            al_terminar=self._al_terminar_creacion,
            al_fallar=self._fallo_reanudar,
        )

    def _tras_existencia(self, estado: EstadoMV | None) -> None:
        """Resultado de comprobar si una creación de envío incierto llegó a crearse.

        ``estado``: ``None`` si no se pudo saber; ``NO_CREADA_SEGURA`` si no existe; ``OK`` si
        existe y es de este lote; ``EXISTE_SIN_CONFIRMAR_PROPIEDAD`` si existe pero no se puede
        demostrar que es suya (CA-L15.5).
        """
        cfg, res = self._cfg_creacion, self._ultimo_resultado
        self._creando = False
        self._refrescar_botones_red()
        if cfg is None:
            return
        if estado == EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD:
            entrada = self._resolver_uno_sin_confirmar(cfg)
            if entrada is not None:
                self._mostrar_existe_sin_confirmar(entrada)
            else:
                self._creando = False
                self.progreso.mostrar_resultado(
                    texto_existe_sin_confirmar(), Desenlace.CONEXION_PERDIDA, None
                )
                self.progreso.boton_comprobar.setVisible(False)
            self._timer_validar.start()
            return
        existe = None if estado is None else estado != EstadoMV.NO_CREADA_SEGURA
        if existe is True:
            texto = self.tr("La máquina sí se creó. Verifica en Proxmox que quedó como esperabas.")
            self._ultimo_resultado = ResultadoCreacion(Desenlace.OK, cfg.vmid, cfg.nodo, None, None)
            self.progreso.establecer_etapa(Etapa.LISTO)  # como al terminar la creación
            self.progreso.mostrar_resultado(texto, Desenlace.OK, None)
            # M3: rescatada por «Comprobar»; el aviso consta en el libro y en el informe.
            self._sincronizar_libro_uno(
                self._ultimo_resultado, avisos=(AVISO_CREADA_TRAS_COMPROBAR,)
            )
        elif existe is False:
            texto = self.tr("No se creó; puedes intentarlo de nuevo.")
            self._ultimo_resultado = ResultadoCreacion(
                Desenlace.CANCELADO, cfg.vmid, cfg.nodo, None, None
            )
            self.progreso.mostrar_resultado(texto, Desenlace.CANCELADO, None)
            self._sincronizar_libro_uno(self._ultimo_resultado)
            self._desbloquear()
        else:
            texto = self.tr(
                "No se pudo comprobar si la máquina existe. Revisa la conexión e inténtalo "
                "de nuevo antes de volver a crearla."
            )
            self.progreso.mostrar_resultado(texto, Desenlace.CONEXION_PERDIDA, None)
            if res is not None:
                self._ultimo_resultado = res
        self.statusBar().showMessage(texto)
        self._timer_validar.start()

    def _fallo_reanudar(self, error: ErrorProxLaunch) -> None:
        cfg, res = self._cfg_creacion, self._ultimo_resultado
        if cfg is None:
            self._creando = False
            return
        self._al_terminar_creacion(
            ResultadoCreacion(
                Desenlace.CONEXION_PERDIDA,
                cfg.vmid,
                cfg.nodo,
                res.upid if res else self._upid_recibido,
                error,
            )
        )

    # --- Lotes (MVP 2) ----------------------------------------------------------------

    @property
    def _lote_en_curso(self) -> bool:
        """Hay un lote ejecutándose, pausado o deshaciéndose (V-L17)."""
        lote = self._lote
        return lote is not None and not lote.cerrado and (not lote.terminado or lote.deshaciendo)

    def _lote_bloquea_conexion(self) -> bool:
        """Con un lote en marcha solo se puede reconectar si está pausado o esperándolo."""
        lote = self._lote
        if lote is None or not self._lote_en_curso:
            return False
        return not (lote.esperando_reconexion or lote.control.motivo_pausa is not None)

    def _version_forzada(self, sesion: Sesion) -> tuple[int, int] | None:
        caps = sesion.capacidades
        return caps.version if caps.forzada else None

    def _tomar_aviso_informe_parcial(self) -> None:
        ruta = tomar_aviso_informe_parcial(self._deps.directorio_informes)
        if ruta is not None:
            self._aviso_informe_parcial = self.tr(
                "El último lote se cerró sin terminar. Informe: {ruta}"
            ).format(ruta=str(ruta))

    def _al_editar_plantilla(self) -> None:
        """CA-L04.3: editar la plantilla o el lote invalida el resumen ya generado."""
        if (
            self._pila_derecha.currentIndex() == 1
            and not self._planificando
            and not self._iniciando_lote
        ):
            self.resumen_lote.mostrar_vacio()
            self._plan_mostrado = None
            self._pila_derecha.setCurrentIndex(0)

    def _al_cambiar_destino_lote(self) -> None:
        if self.bloque_lote.modo_destino == ModoDestino.UN_NODO and self.bloque_lote.nodo_elegido:
            self.formulario.usar_nodo_manual(self.bloque_lote.nodo_elegido)
        else:
            self.formulario.usar_nodo_automatico()

    # --- Resumen y simulación ---

    def _ver_resumen_lote(self) -> None:
        sesion, inv = self._sesion, self._inv
        if sesion is None or inv is None or self._planificando or self._lote_en_curso:
            return
        if self.origen.transferencia_activa:
            return  # V-O27: el resumen no se genera con una transferencia en curso
        definicion = self.bloque_lote.definicion(self.formulario.configuracion())
        self._reintento = None
        self._nodo_reintento = None
        self._planificar(definicion, simulando=False)

    def _planificar(self, definicion: DefinicionLote, *, simulando: bool) -> None:
        sesion, inv = self._sesion, self._inv
        if sesion is None or inv is None or self._planificando:
            return
        self._planificando = True
        self.resumen_lote.establecer_reintento(self._reintento is not None)
        self.resumen_lote.mostrar_planificando()
        self._pila_derecha.setCurrentIndex(1)
        vf = self._version_forzada(sesion)
        reloj = self._deps.reloj
        gen = self._gen_plan
        if simulando and self._reintento is not None:
            # B6: con un reintento pendiente se simula el plan del reintento, no un lote nuevo.
            self._lanzador.lanzar(
                simular_reintento,
                sesion,
                reloj,
                self._reintento,
                definicion,
                vf,
                self._nodo_reintento,
                al_terminar=self._si_vigente(gen, self._al_reintento_simulado),
                al_fallar=self._si_vigente(gen, self._fallo_planificacion),
            )
        elif simulando:
            self._lanzador.lanzar(
                simular_lote,
                sesion,
                reloj,
                definicion,
                inv,
                vf,
                al_terminar=self._si_vigente(gen, self._al_simulado),
                al_fallar=self._si_vigente(gen, self._fallo_planificacion),
            )
        elif self._reintento is not None:
            self._lanzador.lanzar(
                armar_reintento,
                sesion,
                reloj,
                self._reintento,
                definicion,
                vf,
                self._nodo_reintento,
                al_terminar=self._si_vigente(gen, self._al_reintento_armado),
                al_fallar=self._si_vigente(gen, self._fallo_planificacion),
            )
        else:
            self._lanzador.lanzar(
                planificar_lote,
                sesion,
                reloj,
                definicion,
                inv,
                vf,
                al_terminar=self._si_vigente(gen, self._al_planificado),
                al_fallar=self._si_vigente(gen, self._fallo_planificacion),
            )

    def _fallo_planificacion(self, error: ErrorProxLaunch) -> None:
        self._planificando = False
        self._iniciando_lote = False
        self.resumen_lote.mostrar_error(error)
        if error.codigo == CodigoError.SESION_EXPIRADA:
            self.abrir_conexion(texto_error(error))
        self._timer_validar.start()

    def _al_planificado(self, plan: Plan) -> None:
        self._planificando = False
        self._plan_mostrado = plan
        self.resumen_lote.mostrar_plan(plan, bloqueo_crear=self._bloqueo_permiso)
        self._timer_validar.start()

    def _al_reintento_armado(self, resultado: tuple[Inventario, Plan]) -> None:
        inv, plan = resultado
        self._inv = self.origen.adoptar(inv)
        self._al_planificado(plan)
        self.resumen_lote.mostrar_selector_nodo(
            [n.nombre for n in inv.topologia.nodos if n.en_linea], self._nodo_reintento
        )

    def _al_reintento_simulado(self, resultado: tuple[Inventario, ResultadoSimulacion]) -> None:
        inv, simulacion = resultado
        self._inv = self.origen.adoptar(inv)
        self._al_simulado(simulacion)
        self.resumen_lote.mostrar_selector_nodo(
            [n.nombre for n in inv.topologia.nodos if n.en_linea], self._nodo_reintento
        )

    def _al_cambiar_nodo_reintento(self, nodo: object) -> None:
        """CA-L21.1: otro nodo para todo el reintento; se revalida antes de confirmar."""
        plan = self.resumen_lote.plan
        if plan is None or self._reintento is None or self._planificando:
            return
        self._nodo_reintento = nodo if isinstance(nodo, str) else None
        self._planificar(plan.definicion, simulando=False)

    def _al_simulado(self, resultado: ResultadoSimulacion) -> None:
        self._planificando = False
        self._plan_mostrado = resultado.plan
        self.resumen_lote.mostrar_plan(
            resultado.plan, bloqueo_crear=self._bloqueo_permiso, simulacion=resultado
        )
        self._timer_validar.start()

    def _simular(self) -> None:
        plan = self.resumen_lote.plan
        if plan is None or self._planificando or self._lote_en_curso:
            return
        self._planificar(plan.definicion, simulando=True)

    def _reducir(self, n: int) -> None:
        """«Reducir a N»: baja la cantidad y vuelve a generar el resumen (CA-L07.7)."""
        self.bloque_lote.establecer_cantidad(n)
        if n > 1:
            self._ver_resumen_lote()
        else:
            self._volver_del_resumen()

    def _si_vigente(self, gen: int, destino: Callable[[Any], None]) -> Callable[[Any], None]:
        """Envuelve un resultado de segundo plano: si se canceló la preparación, se descarta."""

        def _entregar(valor: Any) -> None:
            if gen == self._gen_plan:
                destino(valor)

        return _entregar

    def _cancelar_preparacion(self) -> None:
        """CA-L11.10: cancela la preparación del plan o la simulación; no queda nada creado."""
        self._gen_plan += 1
        self._planificando = False
        self._iniciando_lote = False
        self.resumen_lote.mostrar_vacio()
        self._plan_mostrado = None
        self._pila_derecha.setCurrentIndex(0)
        self._timer_validar.start()

    def _volver_del_resumen(self) -> None:
        if self._iniciando_lote or self._planificando:
            self._cancelar_preparacion()
            return
        self.resumen_lote.mostrar_vacio()
        self._plan_mostrado = None
        self._pila_derecha.setCurrentIndex(0)

    # --- Confirmación e inicio ---

    def _crear_lote_solicitado(self) -> None:
        plan = self.resumen_lote.plan
        sesion = self._sesion
        # CA-L10.7: la bandera se activa antes de lanzar nada.
        if plan is None or sesion is None or self._iniciando_lote or self._lote_en_curso:
            return
        self._iniciando_lote = True
        edad = self._deps.reloj.ahora() - plan.generado_en
        if plan.es_simulacion or edad > PLAN_MAX_EDAD_S:
            self._replanificar(plan)
        else:
            self._confirmar_e_iniciar(plan)

    def _replanificar(self, plan: Plan) -> None:
        sesion = self._sesion
        if sesion is None:
            self._iniciando_lote = False
            return
        self.resumen_lote.mostrar_planificando()
        vf = self._version_forzada(sesion)
        gen = self._gen_plan
        if self._reintento is not None:
            self._lanzador.lanzar(
                armar_reintento,
                sesion,
                self._deps.reloj,
                self._reintento,
                plan.definicion,
                vf,
                self._nodo_reintento,
                al_terminar=self._si_vigente(gen, lambda r: self._tras_replanificar(plan, r)),
                al_fallar=self._si_vigente(gen, self._fallo_planificacion),
            )
            return
        self._lanzador.lanzar(
            replanificar_lote,
            sesion,
            self._deps.reloj,
            plan.definicion,
            vf,
            al_terminar=self._si_vigente(gen, lambda r: self._tras_replanificar(plan, r)),
            al_fallar=self._si_vigente(gen, self._fallo_planificacion),
        )

    def _tras_replanificar(self, anterior: Plan, resultado: tuple[Inventario, Plan]) -> None:
        inv, nuevo = resultado
        self._inv = self.origen.adoptar(inv)
        diferencia = diferencia_planes(anterior, nuevo)
        if nuevo.bloqueado or diferencia:
            # CA-L10.6: no se envía nada hasta que el usuario revise el plan nuevo.
            self._iniciando_lote = False
            self._plan_mostrado = nuevo
            self.resumen_lote.mostrar_plan(
                nuevo, bloqueo_crear=self._bloqueo_permiso, diferencia=diferencia or None
            )
            return
        self._confirmar_e_iniciar(nuevo)

    def _confirmar_e_iniciar(self, plan: Plan) -> None:
        inv = self._inv
        n = len(plan.elementos)
        if inv is None or n == 0:
            self._iniciando_lote = False
            self.resumen_lote.liberar()
            return
        if n > UMBRAL_CONFIRMACION_DOBLE:
            acepta = confirmar(
                self,
                QCoreApplication.translate("VentanaPrincipal", "Confirmar el envío"),
                QCoreApplication.translate(
                    "VentanaPrincipal",
                    "Se enviarán %n máquinas a Proxmox. ¿Continuar?",
                    None,
                    n,
                ),
                QCoreApplication.translate("VentanaPrincipal", "Crear las máquinas"),
                QCoreApplication.translate("VentanaPrincipal", "Cancelar"),
            )
            if not acepta:
                self._iniciando_lote = False
                self.resumen_lote.liberar()
                return
        self._iniciando_lote = False
        self._iniciar_lote(plan, inv, modo_uno=False)

    def _iniciar_lote(self, plan: Plan, inv: Inventario, *, modo_uno: bool) -> None:
        sesion = self._sesion
        if sesion is None:
            return
        control = ControlLote()
        puente = PuenteLote(plan.elementos, self)
        puente.sucio.connect(self._despertar_timer)
        anterior = self._lote
        if anterior is not None and anterior.libro is not None and not anterior.cerrado:
            # El lote anterior (p. ej. el que se reintenta) conserva su libro y su rollback.
            self._lotes_previos.append(anterior)
        # M4: el libro se crea aquí, antes de ejecutar, para que exista aunque el motor falle
        # y «Deshacer» y «Comprobar» sigan disponibles sobre lo ya creado.
        libro = Libro(plan)
        lote = _Lote(plan, inv, sesion, self._perfil_id, control, puente, modo_uno, libro=libro)
        self._lote = lote
        self._accion_ultimo_lote.setEnabled(False)
        self._bloquear_edicion(True)
        if not modo_uno:
            self.progreso_lote.iniciar(plan)
            self._pila_derecha.setCurrentIndex(2)
        self._refrescar_botones_red()
        adaptada = self._fabrica_adaptada()
        self._lanzador.lanzar(
            ejecutar_lote,
            sesion,
            self._deps.reloj,
            plan,
            inv,
            puente.observar,
            control,
            adaptada,
            libro,
            al_terminar=lambda r: self._al_lote_terminado(lote, r),
            al_fallar=lambda e: self._fallo_lote(lote, e),
        )
        self._timer_lote.start()

    def _reintentar_ajustes(self) -> None:
        """«Reintentar ajustes» de los clones PARCIAL: solo reenvía los PUT pendientes."""
        lote = self._lote
        vmids = self.progreso_lote.vmids_con_ajustes_pendientes()
        if lote is None or lote.libro is None or lote.cerrado or self._lote_en_curso or not vmids:
            return
        lote.terminado = False
        lote.control = ControlLote()
        lote.cancelando = False
        lote.pausa_mostrada = False
        self.progreso_lote.mostrar_aviso(None)
        self.progreso_lote.establecer_fase(FaseLote.EJECUTANDO)
        self._lanzador.lanzar(
            reintentar_ajustes_lote,
            lote.sesion,
            self._deps.reloj,
            lote.libro,
            vmids,
            lote.inv,
            lote.puente.observar,
            lote.control,
            self._fabrica_adaptada(),
            al_terminar=lambda libro: self._al_lote_terminado(lote, libro),
            al_fallar=lambda e: self._fallo_lote(lote, e),
        )
        self._timer_lote.start()

    def _fabrica_adaptada(self) -> Callable[[Sesion, Reloj], ServicioCreacion] | None:
        """Fábrica de creación inyectada, con la firma que espera el motor (igual en todo)."""
        fabrica = self._deps.fabrica_creacion
        return (lambda s, _r: fabrica(s)) if fabrica else None

    # --- Seguimiento ---

    def _despertar_timer(self) -> None:
        if not self._timer_lote.isActive():
            self._timer_lote.start()

    def _tick_lote(self) -> None:
        """Lee las instantáneas y las pinta como mucho ACTUALIZACIONES_POR_S veces por segundo."""
        lote = self._lote
        if lote is None:
            self._timer_lote.stop()
            return
        snap = lote.puente.tomar_si_sucio()
        if snap is not None and not lote.cerrado:
            if lote.modo_uno:
                self._refrescar_uno(snap[0])
            else:
                self.progreso_lote.actualizar(snap)
        if lote.puente_rollback is not None:
            res = lote.puente_rollback.tomar_si_sucio()
            if res is not None:
                self.progreso_lote.actualizar_rollback(res)
        if not lote.terminado and not lote.modo_uno:
            self._revisar_pausa(lote)
        if lote.terminado and not lote.deshaciendo:
            self._timer_lote.stop()

    def _refrescar_uno(self, e: EntradaLibro) -> None:
        etapa = _ETAPA_POR_ESTADO.get(e.estado)
        if etapa is not None:
            self.progreso.establecer_etapa(etapa)
        if e.upid and e.upid != self._upid_recibido:
            self._al_upid(e.upid)

    def _revisar_pausa(self, lote: _Lote) -> None:
        motivo = lote.control.motivo_pausa
        if motivo is None:
            lote.pausa_mostrada = False
            if self.progreso_lote.fase == FaseLote.PAUSADO:
                self.progreso_lote.establecer_fase(FaseLote.EJECUTANDO)
            return
        if lote.pausa_mostrada or lote.cancelando or lote.control.cancelado.is_set():
            return
        # Sin máquinas por enviar no hay nada que decidir: el lote ya está terminando.
        if not any(e.estado == EstadoMV.PENDIENTE for e in lote.puente.instantanea()):
            return
        lote.pausa_mostrada = True
        self.progreso_lote.establecer_fase(FaseLote.PAUSADO)
        self._mostrar_pausa(lote, motivo)

    def _mostrar_pausa(self, lote: _Lote, motivo: MotivoPausa) -> None:
        sin_confirmar = sum(1 for e in lote.puente.instantanea() if e.estado in ESTADOS_DUDOSOS)
        dialogo = DialogoPausaLote(
            motivo,
            lote.control.error_pausa,
            repetidos=UMBRAL_PAUSA_ERRORES,
            sin_confirmar=sin_confirmar,
            parent=self,
        )
        lote.dialogo_pausa = dialogo
        dialogo.finished.connect(lambda _r: self._tras_pausa(lote, dialogo))
        dialogo.open()

    def _decidir_pausa(self) -> None:
        lote = self._lote
        if lote is None or lote.terminado or lote.dialogo_pausa is not None:
            return
        motivo = lote.control.motivo_pausa
        if motivo is not None:
            self._mostrar_pausa(lote, motivo)

    def _cerrar_dialogo_pausa(self, lote: _Lote) -> None:
        dialogo = lote.dialogo_pausa
        lote.dialogo_pausa = None
        if dialogo is not None:
            dialogo.reject()

    def _tras_pausa(self, lote: _Lote, dialogo: DialogoPausaLote) -> None:
        if lote.dialogo_pausa is dialogo:
            lote.dialogo_pausa = None
        dialogo.deleteLater()
        accion = dialogo.accion
        if accion is None or lote.terminado or lote.cerrado:
            return  # sin decisión: sigue en pausa y «Decidir qué hacer…» la retoma
        if accion == AccionPausa.CONTINUAR:
            lote.control.reanudar(ignorar_causa=True)
        elif accion == AccionPausa.REINTENTAR:
            lote.control.reanudar(ignorar_causa=False)
        elif accion == AccionPausa.DETENER:
            self._cancelar_ya(lote)
            return
        elif accion == AccionPausa.SIN_ETIQUETAS:
            if not confirmar(
                self,
                QCoreApplication.translate("VentanaPrincipal", "Seguir sin etiquetas"),
                QCoreApplication.translate(
                    "VentanaPrincipal",
                    "Se detendrá este lote y se armará uno nuevo con las máquinas que faltan, sin "
                    "etiquetas. Después, «Deshacer» solo podrá eliminar las máquinas que "
                    "ProxLaunch confirme que creó él mismo. Antes de crear nada verás el resumen.",
                ),
                QCoreApplication.translate("VentanaPrincipal", "Preparar el lote sin etiquetas"),
                QCoreApplication.translate("VentanaPrincipal", "Cancelar"),
            ):
                lote.pausa_mostrada = False
                return
            lote.continuacion = AccionPausa.SIN_ETIQUETAS
            self._cancelar_ya(lote, mantener_continuacion=True)
            return
        elif accion in (AccionPausa.RECONECTAR, AccionPausa.COMPROBAR_Y_CONTINUAR):
            lote.continuacion = accion
            self.progreso_lote.mostrar_aviso(
                self.tr("Esperando a que terminen las tareas en curso para continuar…")
            )
            lote.control.suspender()
            return
        lote.pausa_mostrada = False
        self.progreso_lote.establecer_fase(FaseLote.EJECUTANDO)

    def _cancelar_lote(self) -> None:
        lote = self._lote
        if lote is None:
            return
        if lote.deshaciendo and lote.control_rollback is not None:
            lote.control_rollback.cancelar()
            return
        if lote.terminado or lote.cancelando:
            return
        # Se consulta el puente directamente: no depende del refresco de la tabla (100 ms).
        if any(e.post_intentado for e in lote.puente.instantanea()) and not confirmar(
            self,
            QCoreApplication.translate("VentanaPrincipal", "Cancelar el lote"),
            QCoreApplication.translate(
                "VentanaPrincipal",
                "Las máquinas que ya se enviaron seguirán creándose en Proxmox y se "
                "esperará su resultado. Las demás no se enviarán.",
            ),
            QCoreApplication.translate("VentanaPrincipal", "Cancelar el lote"),
            QCoreApplication.translate("VentanaPrincipal", "Seguir creando"),
        ):
            return
        self._cancelar_ya(lote)

    def _cancelar_ya(self, lote: _Lote, *, mantener_continuacion: bool = False) -> None:
        lote.cancelando = True
        if not mantener_continuacion:
            lote.continuacion = None
        self._cerrar_dialogo_pausa(lote)
        lote.control.cancelar()
        # Si lo único en vuelo son envíos sin UPID (esperando la comprobación de existencia,
        # +5 s y +15 s), no hay tarea que seguir esperando: se corta esa espera. La máquina
        # queda dudosa y nunca se reenvía. Con tareas ya enviadas se sigue esperando su
        # resultado (CA-L16.2) hasta «Dejar de esperar».
        en_vuelo = [
            e
            for e in lote.puente.instantanea()
            if e.estado in ESTADOS_EN_CURSO and e.post_intentado
        ]
        if en_vuelo and all(e.upid is None for e in en_vuelo):
            lote.control.dejar_de_esperar()
        self.progreso_lote.establecer_fase(FaseLote.CANCELANDO)

    def _dejar_de_esperar(self) -> None:
        lote = self._lote
        if lote is not None and not lote.terminado:
            lote.control.dejar_de_esperar()

    # --- Fin del lote ---

    def _vigente(self, lote: _Lote) -> bool:
        """El resultado de un hilo solo vale si su lote sigue siendo el actual y no se cerró."""
        return lote is self._lote and not lote.cerrado

    def _fallo_lote(self, lote: _Lote, error: ErrorProxLaunch) -> None:
        """El motor falló fuera de lo previsto: la interfaz no se queda «ocupada» (RNF-L11)."""
        if not self._vigente(lote):
            return
        if lote.modo_uno:
            self._fin_uno(lote, None, error)
            return
        self._cerrar_dialogo_pausa(lote)
        self.progreso_lote.mostrar_error(
            self.tr("El lote terminó de forma inesperada: {m}").format(m=texto_error(error))
        )
        self._finalizar_lote()

    def _al_lote_terminado(self, lote: _Lote, libro: Libro) -> None:
        if not self._vigente(lote):
            return
        lote.libro = libro
        self._cerrar_dialogo_pausa(lote)
        if lote.modo_uno:
            self._fin_uno(lote, libro, None)
            return
        cont, lote.continuacion = lote.continuacion, None
        self._tick_lote_final(lote)
        if cont == AccionPausa.COMPROBAR_Y_CONTINUAR:
            self._continuar_lote(lote, sesion=lote.sesion, comprobar=True)
        elif cont == AccionPausa.RECONECTAR:
            lote.esperando_reconexion = True
            self.progreso_lote.mostrar_aviso(
                self.tr("Reconecta para continuar con las máquinas que faltan.")
            )
            self.abrir_conexion(self.tr("Reconecta para continuar con el lote."))
            if self._dialogo_conexion is None:  # no se pudo abrir: el lote queda detenido
                lote.esperando_reconexion = False
                self._finalizar_lote()
        else:
            self._finalizar_lote()
            if cont == AccionPausa.SIN_ETIQUETAS:
                self._reintentar_pendientes(etiquetar=False)

    def _tick_lote_final(self, lote: _Lote) -> None:
        if lote.libro is not None:
            self.progreso_lote.actualizar(lote.libro.instantanea())

    def _continuar_lote(self, lote: _Lote, *, sesion: Sesion, comprobar: bool) -> None:
        """Comprueba las dudosas y envía solo las pendientes, con control y sesión nuevos."""
        libro = lote.libro
        if libro is None:
            return
        lote.esperando_reconexion = False
        lote.sesion = sesion
        lote.control = ControlLote()
        lote.cancelando = False
        lote.pausa_mostrada = False
        self.progreso_lote.mostrar_aviso(None)
        self.progreso_lote.establecer_fase(FaseLote.EJECUTANDO)
        self._lanzador.lanzar(
            continuar_lote,
            sesion,
            self._deps.reloj,
            libro,
            lote.inv,
            lote.puente.observar,
            lote.control,
            comprobar,
            al_terminar=lambda r: self._al_lote_terminado(lote, r),
            al_fallar=lambda e: self._fallo_lote(lote, e),
        )
        self._timer_lote.start()

    def _finalizar_lote(self) -> None:
        lote = self._lote
        if lote is None:
            return
        lote.terminado = True
        lote.deshaciendo = False
        entradas = lote.libro.instantanea() if lote.libro else lote.puente.instantanea()
        self.progreso_lote.actualizar(entradas)
        dudosas = sum(1 for e in entradas if e.estado in ESTADOS_DUDOSOS)
        reintentables = sum(1 for e in entradas if e.estado in _ESTADOS_REINTENTABLES)
        elegibles = 0
        for lt in self._lotes_deshacibles() or ([lote] if lote.libro is not None else []):
            assert lt.libro is not None
            candidatos = ServicioRollback(lt.sesion, self._deps.reloj).elegibles(
                lt.libro,
                etiquetado=lt.plan.definicion.etiquetar,
                excluir_vmids=self._vmids_eliminados(lt),
            )
            elegibles += sum(1 for c in candidatos if c.elegible)
        self.progreso_lote.establecer_fase(
            FaseLote.TERMINADO,
            dudosas=dudosas,
            elegibles=elegibles,
            reintentables=reintentables,
            con_ajustes=len(self.progreso_lote.vmids_con_ajustes_pendientes()),
        )
        self.statusBar().showMessage(texto_barra(entradas))
        self._accion_ultimo_lote.setEnabled(True)
        self._refrescar_botones_red()
        self._timer_validar.start()

    @staticmethod
    def _vmids_eliminados(lote: _Lote) -> frozenset[int]:
        """VMIDs que un «Deshacer» anterior ya eliminó (o ya no existían): no se ofrecen más."""
        return frozenset(
            r.vmid
            for r in lote.resultados_rollback
            if r.estado in (EstadoRollback.ELIMINADA, EstadoRollback.YA_NO_EXISTIA)
        )

    def _fin_uno(self, lote: _Lote, libro: Libro | None, error: ErrorProxLaunch | None) -> None:
        """Una sola máquina: el resultado del motor se muestra con el panel del MVP 1."""
        lote.terminado = True
        self._accion_ultimo_lote.setEnabled(lote.libro is not None)
        cfg = self._cfg_creacion
        if libro is None or cfg is None:
            self._fallo_creacion(error or ErrorProxLaunch(CodigoError.DESCONOCIDO))
            return
        e = libro.instantanea()[0]
        error_uno = e.error
        if error_uno is not None and error_uno.codigo in (
            CodigoError.LOTE_ENVIO_INCIERTO,
            CodigoError.LOTE_EXISTENCIA_INDETERMINADA,
        ):
            error_uno = ErrorProxLaunch(
                error_uno.codigo,
                {**error_uno.params, "nombre": cfg.nombre},
                error_uno.detalle_tecnico,
            )
        if e.estado == EstadoMV.NO_CREADA_SEGURA:
            # Se comprobó tres veces y no existe: mismo texto y estilo neutro que «Comprobar».
            self._fin_uno_inicial = True
            try:
                self._tras_existencia(EstadoMV.NO_CREADA_SEGURA)
            finally:
                self._fin_uno_inicial = False
            return
        if e.estado == EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD:
            self._mostrar_existe_sin_confirmar(e)
            return
        self._fin_uno_inicial = True
        try:
            self._terminar_uno(e, error_uno)
        finally:
            self._fin_uno_inicial = False

    def _terminar_uno(self, e: EntradaLibro, error_uno: ErrorProxLaunch | None) -> None:
        self._al_terminar_creacion(
            ResultadoCreacion(
                _DESENLACE_POR_ESTADO.get(e.estado, Desenlace.CONEXION_PERDIDA),
                e.elemento.vmid,
                e.elemento.nodo,
                e.upid,
                error_uno,
                list(e.log_tarea),
            ),
            " ".join(t for t in (texto_aviso_entrada(a) for a in e.avisos) if t),
        )
        # Clon PARCIAL con ajustes pendientes (E-O24): se puede reintentar sin crear otra máquina.
        self.progreso.ofrecer_reintentar_ajustes(tiene_ajustes_pendientes(e))

    def _reintentar_ajustes_uno(self) -> None:
        """«Reintentar ajustes» de una sola máquina: mismo camino que el lote, solo los PUT."""
        lote = self._lote
        if lote is None or lote.libro is None or lote.cerrado or not lote.modo_uno or self._creando:
            return
        vmids = tuple(
            e.elemento.vmid for e in lote.libro.instantanea() if tiene_ajustes_pendientes(e)
        )
        if not vmids:
            return
        lote.terminado = False
        lote.control = ControlLote()
        lote.cancelando = False
        self._creando = True
        self._bloquear_edicion(True)
        self._refrescar_botones_red()
        self.progreso.mostrar_progreso_mensaje(self.tr("Reintentando los ajustes pendientes..."))
        self._lanzador.lanzar(
            reintentar_ajustes_lote,
            lote.sesion,
            self._deps.reloj,
            lote.libro,
            vmids,
            lote.inv,
            lote.puente.observar,
            lote.control,
            self._fabrica_adaptada(),
            al_terminar=lambda libro: self._al_lote_terminado(lote, libro),
            al_fallar=lambda e: self._fallo_lote(lote, e),
        )
        self._timer_lote.start()

    def _sincronizar_libro_uno(
        self, resultado: ResultadoCreacion, *, avisos: tuple[str, ...] = ()
    ) -> None:
        """Tras «Comprobar» con una máquina, el libro refleja el resultado (Deshacer, informe)."""
        lote = self._lote
        if self._fin_uno_inicial or lote is None or not lote.modo_uno or lote.libro is None:
            return
        if resultado.desenlace == Desenlace.CANCELADO:
            # B5: cancelado con UPID es dudosa (la tarea pudo seguir); sin UPID no se envió.
            estado = EstadoMV.CONEXION_PERDIDA if resultado.upid else EstadoMV.NO_CREADA_SEGURA
        else:
            estado = EstadoMV(resultado.desenlace.value)
        try:
            nueva = lote.libro.resolver(
                resultado.vmid,
                estado,
                t_fin=self._deps.reloj.ahora(),
                upid=resultado.upid,
                error=resultado.error,
                log=resultado.log_tarea,
                avisos=avisos,
            )
        except (AssertionError, KeyError):
            _log.warning("No se pudo actualizar el libro tras comprobar", exc_info=True)
            return
        lote.puente.observar(nueva)
        # «Deshacer…» solo se ofrece si la máquina es elegible (p. ej. una rescatada sin
        # etiquetas no lo es: no hay forma de demostrar que es nuestra).
        candidatos = ServicioRollback(lote.sesion, self._deps.reloj).elegibles(
            lote.libro,
            etiquetado=lote.plan.definicion.etiquetar,
            excluir_vmids=self._vmids_eliminados(lote),
        )
        if not any(c.elegible for c in candidatos):
            self.progreso.boton_deshacer.setVisible(False)

    def _resolver_uno_sin_confirmar(self, cfg: ConfiguracionVM) -> EntradaLibro | None:
        """Tras «Comprobar» halla una máquina sin etiqueta del lote: el libro la marca así."""
        lote = self._lote
        if lote is None or not lote.modo_uno or lote.libro is None:
            return None
        try:
            nueva = lote.libro.resolver(
                cfg.vmid,
                EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD,
                t_fin=self._deps.reloj.ahora(),
            )
        except (AssertionError, KeyError):
            _log.warning("No se pudo actualizar el libro tras comprobar", exc_info=True)
            return None
        lote.puente.observar(nueva)
        return nueva

    def _mostrar_existe_sin_confirmar(self, e: EntradaLibro) -> None:
        """La máquina existe, pero no se puede asegurar que la creó este lote (CA-L15.5)."""
        self._creando = False
        self._refrescar_botones_red()
        texto = texto_existe_sin_confirmar()
        self._ultimo_resultado = ResultadoCreacion(
            Desenlace.CONEXION_PERDIDA, e.elemento.vmid, e.elemento.nodo, e.upid, None
        )
        self.progreso.mostrar_resultado(texto, Desenlace.CONEXION_PERDIDA, e.upid)
        # No se ofrece «Comprobar» (diría que sí se creó) ni crear otra con ese número.
        self.progreso.boton_comprobar.setVisible(False)
        self.statusBar().showMessage(texto)
        self._timer_validar.start()

    # --- Acciones sobre un lote terminado ---

    def _comprobar_dudosas(self, vmids: frozenset[int] | None = None) -> None:
        lote = self._lote
        if lote is None or lote.libro is None or not lote.terminado or lote.deshaciendo:
            return
        sesion = self._sesion
        if sesion is None or lote.cerrado or lote.perfil_id != self._perfil_id:
            return  # nunca se comprueba un lote contra otro servidor
        lote.terminado = False
        control = ControlLote()
        lote.control = control
        self._accion_ultimo_lote.setEnabled(False)
        self.progreso_lote.establecer_fase(FaseLote.COMPROBANDO)
        self._timer_lote.start()
        self._lanzador.lanzar(
            comprobar_dudosas_lote,
            sesion,
            self._deps.reloj,
            lote.libro,
            lote.puente.observar,
            control,
            None,
            vmids,
            al_terminar=lambda _l: self._tras_comprobar(lote),
            al_fallar=lambda e: self._fallo_lote(lote, e),
        )

    def _tras_comprobar(self, lote: _Lote) -> None:
        if self._vigente(lote):
            self._finalizar_lote()

    def _lotes_deshacibles(self) -> list[_Lote]:
        """Lotes de la sesión que se pueden deshacer: los anteriores y el actual, mismo servidor."""
        todos = [*self._lotes_previos, *([self._lote] if self._lote is not None else [])]
        return [
            lt
            for lt in todos
            if lt.libro is not None and not lt.cerrado and lt.perfil_id == self._perfil_id
        ]

    def _deshacer(self) -> None:
        lote = self._lote
        if lote is None or lote.libro is None or lote.deshaciendo or self._sesion is None:
            return
        if lote.perfil_id != self._perfil_id:
            return  # otro servidor: ya no se puede deshacer (CA-L18.14)
        servicio = ServicioRollback(self._sesion, self._deps.reloj)
        candidatos: list[CandidatoRollback] = []
        duenos: dict[int, _Lote] = {}  # id del candidato -> lote al que pertenece
        for lt in self._lotes_deshacibles():
            assert lt.libro is not None
            for c in servicio.elegibles(
                lt.libro,
                etiquetado=lt.plan.definicion.etiquetar,
                excluir_vmids=self._vmids_eliminados(lt),
            ):
                candidatos.append(c)
                duenos[id(c)] = lt
        dialogo = DialogoDeshacer(candidatos, self)
        dialogo.finished.connect(lambda r: self._tras_dialogo_deshacer(lote, dialogo, r, duenos))
        dialogo.open()

    def _tras_dialogo_deshacer(
        self, lote: _Lote, dialogo: DialogoDeshacer, r: int, duenos: dict[int, _Lote]
    ) -> None:
        elegidos = dialogo.elegidos() if r == QDialog.DialogCode.Accepted else []
        dialogo.deleteLater()
        sesion = self._sesion
        if not elegidos or sesion is None or lote.deshaciendo:
            return
        # A2: mientras el diálogo estaba abierto pudo cambiar el perfil o cerrarse el lote.
        # Nunca se deshace un lote contra un servidor distinto del suyo.
        if not self._vigente(lote) or lote.perfil_id != self._perfil_id:
            return
        elegidos = [
            c
            for c in elegidos
            if (dueno := duenos.get(id(c), lote)) is not None
            and not dueno.cerrado
            and dueno.perfil_id == self._perfil_id
        ]
        if not elegidos:
            return
        lote.deshaciendo = True
        self._accion_ultimo_lote.setEnabled(False)
        lote.control_rollback = ControlLote()
        lote.puente_rollback = PuenteRollback(self)
        if lote.modo_uno:
            # La vista de una máquina no tiene tabla de borrado: se usa la del lote.
            assert lote.libro is not None
            self.progreso_lote.iniciar(lote.plan)
            self.progreso_lote.actualizar(lote.libro.instantanea())
            self._pila_derecha.setCurrentIndex(2)
        self.progreso_lote.iniciar_rollback(
            (c.entrada.elemento.nombre, c.entrada.elemento.vmid, c.entrada.elemento.nodo)
            for c in elegidos
        )
        self.progreso_lote.establecer_fase(FaseLote.DESHACIENDO)
        self.statusBar().showMessage(self.tr("Eliminando las máquinas elegidas…"))
        # Cada lote se deshace con su propio id y su propia política de etiquetas.
        grupos: list[tuple[list[CandidatoRollback], str, bool]] = []
        dueno_de_vmid: dict[int, _Lote] = {}
        for lt in {id(x): x for x in (duenos.get(id(c), lote) for c in elegidos)}.values():
            propios = [c for c in elegidos if duenos.get(id(c), lote) is lt]
            grupos.append((propios, lt.plan.id_lote, lt.plan.definicion.etiquetar))
            for c in propios:
                dueno_de_vmid[c.entrada.elemento.vmid] = lt
        self._lanzador.lanzar(
            deshacer_lotes,
            sesion,
            self._deps.reloj,
            grupos,
            lote.puente_rollback.observar,
            lote.control_rollback,
            al_terminar=lambda r2: self._tras_deshacer(lote, r2, dueno_de_vmid),
            al_fallar=lambda e: self._fallo_deshacer(lote, e),
        )
        self._timer_lote.start()

    def _tras_deshacer(
        self,
        lote: _Lote,
        resultados: list[ResultadoRollback],
        duenos: dict[int, _Lote] | None = None,
    ) -> None:
        for lt in {id(x): x for x in [lote, *(duenos or {}).values()]}.values():
            propios = [r for r in resultados if (duenos or {}).get(r.vmid, lote) is lt]
            lt.resultados_rollback = [
                *(r for r in lt.resultados_rollback if r.vmid not in {x.vmid for x in propios}),
                *propios,
            ]
        if not self._vigente(lote):
            return  # el lote se cerró (cambio de perfil o cierre): solo quedan los datos
        self.progreso_lote.actualizar_rollback(resultados)
        error = lote.control_rollback.error_pausa if lote.control_rollback else None
        if error is not None:
            self.progreso_lote.mostrar_error(texto_error(error))
        lote.deshaciendo = False
        lote.puente_rollback = None
        self._finalizar_lote()
        self._descubrir()  # CA-L18.12: refresca VMIDs y espacio libre

    def _fallo_deshacer(self, lote: _Lote, error: ErrorProxLaunch) -> None:
        if not self._vigente(lote):
            return
        self.progreso_lote.mostrar_error(texto_error(error))
        lote.deshaciendo = False
        lote.puente_rollback = None
        self._finalizar_lote()

    def _reintentar_pendientes(self, *, etiquetar: bool | None = None) -> None:
        """RF-L21: arma un lote nuevo con lo que no se creó y lo pasa por el resumen."""
        lote = self._lote
        if lote is None or self._sesion is None or self._planificando:
            return
        entradas = lote.libro.instantanea() if lote.libro else lote.puente.instantanea()
        elementos = tuple(e.elemento for e in entradas if e.estado in _ESTADOS_REINTENTABLES)
        if not elementos:
            return
        # Homogéneo: igual que en el MVP 2. Por filas: una fila por máquina con su propia
        # configuración, nombre, VMID y nodo (CA-C08.10).
        definicion = dataclasses.replace(
            definicion_para_reintento(lote.plan.definicion, elementos),
            etiquetar=lote.plan.definicion.etiquetar if etiquetar is None else etiquetar,
        )
        self._reintento = elementos
        self._nodo_reintento = None
        self._planificar(definicion, simulando=False)

    def _metadatos_informe(self, sesion: Sesion, inv: Inventario) -> MetadatosInforme:
        """Contexto del informe: nunca host, IP ni usuario (CA-L19.3)."""
        topologia = inv.topologia
        return MetadatosInforme(
            nombre_perfil=sesion.perfil.nombre,
            version_proxmox=sesion.version.texto,
            es_cluster=topologia.es_cluster,
            nombre_cluster=topologia.nombre_cluster,
            fecha_hora_local=datetime.now().astimezone().isoformat(timespec="seconds"),
        )

    @staticmethod
    def _valores_a_ocultar(sesion: Sesion) -> list[str]:
        """Host(s) y usuario del perfil: se quitan literalmente de todo texto del informe."""
        perfil = sesion.perfil
        valores = [*perfil.hosts, sesion.host_activo, perfil.usuario, sesion.usuario_efectivo]
        return [v for v in valores if v]

    def _informe_actual(self) -> InformeLote | None:
        lote = self._lote
        if lote is None:
            return None
        metadatos = self._metadatos_informe(lote.sesion, lote.inv)
        rollback = tuple(lote.resultados_rollback)
        ocultar = self._valores_a_ocultar(lote.sesion)
        if lote.libro is not None:
            return construir_informe(
                lote.plan,
                lote.libro,
                metadatos,
                rollback=rollback,
                reloj=self._deps.reloj,
                ocultar=ocultar,
                transferencias=self.origen.registro.lista(),
            )
        return informe_desde_entradas(
            lote.plan,
            lote.puente.instantanea(),
            metadatos,
            rollback,
            self._deps.reloj.ahora(),
            ocultar,
            self.origen.registro.lista(),
        )

    def _informe_de_simulacion(self) -> InformeLote | None:
        """CA-L11.8: la simulación sale como informe RF-L19 con la misma función de generación."""
        plan, sesion, inv = self.resumen_lote.plan, self._sesion, self._inv
        if plan is None or sesion is None or inv is None or not plan.es_simulacion:
            return None
        return informe_desde_entradas(
            plan,
            tuple(EntradaLibro(e) for e in plan.elementos),
            self._metadatos_informe(sesion, inv),
            (),
            self._deps.reloj.ahora(),
            self._valores_a_ocultar(sesion),
            self.origen.registro.lista(),
        )

    def _informe_simulacion(self) -> None:
        informe = self._informe_de_simulacion()
        if informe is None:
            return
        dialogo = DialogoInforme(informe, self._deps.directorio_informes, self)
        dialogo.finished.connect(lambda _r: dialogo.deleteLater())
        dialogo.open()

    def _mostrar_informe(self) -> None:
        informe = self._informe_actual()
        if informe is None:
            return
        dialogo = DialogoInforme(informe, self._deps.directorio_informes, self)
        dialogo.finished.connect(lambda _r: dialogo.deleteLater())
        dialogo.open()

    def _volver_de_lote(self) -> None:
        lote = self._lote
        if (
            lote is not None
            and any(e.estado in ESTADOS_DUDOSOS for e in self.progreso_lote.entradas)
            and not confirmar(
                self,
                QCoreApplication.translate("VentanaPrincipal", "Hay máquinas sin confirmar"),
                QCoreApplication.translate(
                    "VentanaPrincipal",
                    "No sabemos si algunas máquinas se crearon. Si vuelves y repites el lote, "
                    "podrías duplicarlas. ¿Volver de todos modos?",
                ),
                QCoreApplication.translate("VentanaPrincipal", "Volver de todos modos"),
                QCoreApplication.translate("VentanaPrincipal", "Quedarme aquí"),
            )
        ):
            return
        self._pila_derecha.setCurrentIndex(0)
        if lote is not None and lote.modo_uno:
            self.progreso.reiniciar()
        self._desbloquear()
        self.resumen_lote.mostrar_vacio()
        self._plan_mostrado = None
        self._timer_validar.start()

    def _ver_ultimo_lote(self) -> None:
        lote = self._lote
        if lote is None or lote.libro is None or lote.cerrado or self._lote_en_curso:
            return  # A2: con un lote, rollback o comprobación en curso no se reinicia la vista
        self.progreso_lote.iniciar(lote.plan)
        self._pila_derecha.setCurrentIndex(2)
        self._bloquear_edicion(True)
        self._finalizar_lote()

    def _cerrar_lote_por_cambio_de_perfil(self, lote: _Lote) -> None:
        """CA-L17.4: con otro servidor el lote anterior queda cerrado y sin acciones."""
        lote.cerrado = True
        for previo in self._lotes_previos:
            previo.cerrado = True
        self._lotes_previos.clear()
        lote.control.dejar_de_esperar()
        if lote.control_rollback is not None:
            lote.control_rollback.cancelar()
        self._cerrar_dialogo_pausa(lote)
        self._lote = None
        self._timer_lote.stop()
        self._accion_ultimo_lote.setEnabled(False)
        self.progreso_lote.iniciar(lote.plan)
        self.resumen_lote.mostrar_vacio()
        self._pila_derecha.setCurrentIndex(0)

    def _guardar_informe_parcial(self, lote: _Lote) -> None:
        informe = self._informe_actual()
        if informe is not None:
            ruta = guardar_informe_parcial(informe, self._deps.directorio_informes)
            if ruta is not None:
                _log.info("Informe parcial guardado en %s", ruta)

    # --- MVP 3: perfiles de máquina, lotes guardados e importación CSV ----------------------

    def _preparar_almacen_perfiles(self) -> AlmacenPerfilesMaquina:
        """Almacén de perfiles de máquina: el inyectado o el de la carpeta de configuración."""
        if self._deps.perfiles_maquina is not None:
            return self._deps.perfiles_maquina
        ruta = Path(self._deps.perfiles.ruta).with_name("perfiles_maquina.json")
        almacen = AlmacenPerfilesMaquina(
            ruta, fabrica=perfiles_fabrica(textos_perfiles_fabrica()), app_version=__version__
        )
        almacen.cargar()  # inexistente = vacío; ilegible = solo fábrica y aviso (CA-P12.2/3)
        return almacen

    def _avisos_perfiles_maquina(self) -> list[str]:
        """Avisos del archivo de perfiles de máquina (ilegible, dañado, de versión futura)."""
        estado = self._almacen_perfiles.estado
        avisos: list[str] = []
        if estado.error_lectura:
            avisos.append(
                self.tr(
                    "No se pudo leer el archivo de perfiles de máquina (permisos): solo verás los "
                    "perfiles de fábrica."
                )
            )
        elif estado.hubo_corrupcion:
            avisos.append(
                self.tr(
                    "El archivo de perfiles de máquina estaba dañado: se guardó una copia y se "
                    "empezó uno nuevo."
                )
            )
        if estado.solo_lectura:
            avisos.append(texto_error(ErrorProxLaunch(CodigoError.PERFILES_SOLO_LECTURA)))
        if estado.descartados:
            avisos.append(
                self.tr(
                    "Se omitieron %n perfiles dañados del archivo de perfiles.",
                    None,
                    len(estado.descartados),
                )
            )
        return avisos

    def _bloquear_edicion(self, bloqueado: bool) -> None:
        """Bloquea o libera todo lo que edita el lote (formulario, bloque, perfil y filas)."""
        self.formulario.bloquear(bloqueado)
        self.bloque_lote.bloquear(bloqueado)
        self.selector_perfil.bloquear(bloqueado)
        self.panel_filas.bloquear(bloqueado)
        self.panel_no_encaja.setEnabled(not bloqueado)
        self._actualizar_acciones()

    def _actualizar_acciones(self) -> None:
        """Habilita las acciones de archivo y de perfil según la conexión y el trabajo en curso."""
        listo = self._formulario_listo and self._sesion is not None and self._inv is not None
        libre = not self._lote_en_curso and not self._creando
        sin_plan = not self._planificando and not self._iniciando_lote
        self._accion_abrir_lote.setEnabled(listo and libre and sin_plan)
        self._accion_guardar_lote.setEnabled(listo)  # también con un lote en marcha (CA-G02.4)
        self._accion_guardar_lote_como.setEnabled(listo)
        self._accion_importar_csv.setEnabled(libre and sin_plan)
        self._accion_plantilla_csv.setEnabled(True)
        self._accion_informe_csv.setEnabled(self._lote is not None and not self._lote.modo_uno)
        self._accion_guardar_perfil.setEnabled(
            listo and libre and not self.bloque_lote.es_por_filas
        )
        self._accion_administrar_perfiles.setEnabled(libre)
        self.origen.establecer_ocupado(not libre or not sin_plan)
        self._accion_capacidades.setEnabled(listo)
        self._accion_recordados.setEnabled(
            listo and self.origen.hay_recordado_no_disponible(self.formulario.nodo_efectivo())
        )

    def _ver_archivos_subidos(self) -> None:
        """«Archivos subidos en esta sesión»: copiar o guardar la lista (RF-O25)."""
        self._mostrar_y_borrar(
            DialogoTransferenciasSesion(self.origen.registro, self, lanzador=self._lanzador)
        )

    def _mostrar_error_archivo(self, error: ErrorProxLaunch) -> None:
        """Error al leer o escribir un archivo: banner rojo y barra de estado (sin diálogo)."""
        texto = texto_fallo(error)
        self._errores_sesion = [texto]
        self._pintar_avisos()
        self.statusBar().showMessage(texto.splitlines()[0] if texto else "")

    # --- Perfil de máquina en el formulario ---

    def _fijar_perfil_inicial(self, inv: Inventario) -> None:
        """Formulario recién abierto: el selector muestra el perfil predeterminado (CA-P05.4)."""
        cfg = self.formulario.configuracion()
        self._cfg_ultima_aplicada = cfg
        # Formulario pristino: base de «cambios sin guardar» (RF-G08, §6.8).
        if self._origen_lote is None:
            self._huella_guardada = self._huella_de(self._definicion_actual())
        try:
            predeterminado = self._almacen_perfiles.obtener(ID_PREDETERMINADO)
        except ErrorProxLaunch:
            self.selector_perfil.marcar_aplicado(None)
            return
        coincide = hardware_igual(aplicar_perfil(predeterminado, cfg, inv).cfg, cfg)
        self.selector_perfil.marcar_aplicado(ID_PREDETERMINADO if coincide else None)

    def _al_cambiar_formulario(self) -> None:
        """Tras cualquier edición el selector dice «<perfil> (modificado)» (CA-P05.8)."""
        if self._aplicando or self._cfg_ultima_aplicada is None:
            return
        modificado = not hardware_igual(self.formulario.configuracion(), self._cfg_ultima_aplicada)
        self.selector_perfil.marcar_modificado(modificado)

    def _recargar_selector(self, actual_id: str | None) -> None:
        self.selector_perfil.establecer_perfiles(self._almacen_perfiles.todos(), actual_id)

    def _al_elegir_perfil(self, id_perfil: str) -> None:
        """Aplica un perfil: solo hardware, sin red (INV-M1). Pide confirmar si hay cambios."""
        inv = self._inv
        if inv is None or self._lote_en_curso or self._creando or self.bloque_lote.es_por_filas:
            self.selector_perfil.restaurar()
            return
        try:
            perfil = self._almacen_perfiles.obtener(id_perfil)
        except ErrorProxLaunch as error:
            self._mostrar_error_archivo(error)
            self.selector_perfil.restaurar()
            return
        base = self._cfg_ultima_aplicada
        if base is not None and not hardware_igual(self.formulario.configuracion(), base):
            acepta = confirmar(
                self,
                self.tr("Cambiar de perfil"),
                self.tr("Se reemplazarán los ajustes de hardware que cambiaste."),
                self.tr("Reemplazar"),
                self.tr("Cancelar"),
            )
            if not acepta:
                self.selector_perfil.restaurar()
                return
        self._aplicar_perfil_elegido(perfil, inv)

    def _aplicar_perfil_elegido(self, perfil: PerfilMaquina, inv: Inventario) -> None:
        actual = self.formulario.configuracion()
        resultado = aplicar_perfil(perfil, actual, inv)
        if perfil.config.origen == OrigenSO.DISCO_VACIO:
            # Un perfil sin origen sugerido no cambia cómo se crea la máquina (solo su SO).
            resultado.cfg.origen, resultado.cfg.detalle_origen = (
                actual.origen,
                actual.detalle_origen,
            )
        self._aplicando = True
        try:
            self.formulario.aplicar_hardware(resultado.cfg, asistente=True)
        finally:
            self._aplicando = False
        self._cfg_ultima_aplicada = self.formulario.configuracion()
        self.selector_perfil.marcar_aplicado(perfil.id)
        self.selector_perfil.mostrar_avisos([texto_aviso_pista(a) for a in resultado.avisos])
        self.statusBar().showMessage(
            self.tr("Perfil «{nombre}» aplicado").format(nombre=perfil.nombre)
        )
        self._timer_validar.start()

    def _actualizar_compatibilidad(self, cfg: ConfiguracionVM, *, en_lote: bool) -> None:
        """Panel «Compatibilidad del perfil» con la validación existente (CA-P07.1)."""
        sesion, inv = self._sesion, self._inv
        id_perfil = self.selector_perfil.perfil_actual_id
        if sesion is None or inv is None or id_perfil is None:
            self.selector_perfil.mostrar_compatibilidad([], [])
            return
        try:
            perfil = self._almacen_perfiles.obtener(id_perfil)
        except ErrorProxLaunch:
            self.selector_perfil.mostrar_compatibilidad([], [])
            return
        problemas = evaluar_compatibilidad(cfg, perfil.config, inv, sesion.capacidades)
        # El nombre y el VMID no son del perfil: sus errores no son de compatibilidad.
        problemas = [p for p in problemas if p.campo not in ("nombre", "vmid")]
        errores: list[str] = []
        avisos: list[str] = []
        for p in problemas:
            texto = texto_problema(p)
            campo = nombre_campo(p.campo) if p.campo else ""
            linea = f"{campo}: {texto}" if campo else texto
            (errores if p.severidad == Severidad.ERROR else avisos).append(linea)
        self.selector_perfil.mostrar_compatibilidad(
            list(dict.fromkeys(errores)), list(dict.fromkeys(avisos))
        )

    def _guardar_perfil(self) -> None:
        """«Guardar como perfil de máquina…» (RF-P03)."""
        if not self._formulario_listo or self._lote_en_curso or self._creando:
            return
        dialogo = DialogoGuardarPerfil(
            self._almacen_perfiles,
            self.formulario.configuracion(),
            avanzado=self.avanzado,
            parent=self,
        )
        aceptado = dialogo.exec() == QDialog.DialogCode.Accepted
        perfil = getattr(dialogo, "perfil_creado", None)
        dialogo.deleteLater()
        if not aceptado or perfil is None:
            return
        self._cfg_ultima_aplicada = self.formulario.configuracion()
        self._recargar_selector(perfil.id)
        self.selector_perfil.marcar_aplicado(perfil.id)
        self.statusBar().showMessage(
            self.tr("Perfil «{nombre}» guardado").format(nombre=perfil.nombre)
        )

    def _actualizar_perfil(self) -> None:
        """«Guardar cambios en el perfil «X»»: reemplaza el hardware del perfil del usuario."""
        id_perfil = self.selector_perfil.perfil_actual_id
        if id_perfil is None or not self._formulario_listo or self._lote_en_curso:
            return
        try:
            perfil = self._almacen_perfiles.obtener(id_perfil)
        except ErrorProxLaunch as error:
            self._mostrar_error_archivo(error)
            return
        acepta = confirmar(
            self,
            self.tr("Guardar cambios en el perfil"),
            self.tr("Se reemplazará el hardware guardado en el perfil «{nombre}».").format(
                nombre=perfil.nombre
            ),
            self.tr("Guardar cambios"),
            self.tr("Cancelar"),
        )
        if not acepta:
            return
        config = config_desde_configuracion(self.formulario.configuracion(), con_pistas=True)
        try:
            self._almacen_perfiles.actualizar(id_perfil, config)
        except ErrorProxLaunch as error:
            self._mostrar_error_archivo(error)
            return
        self._cfg_ultima_aplicada = self.formulario.configuracion()
        self._recargar_selector(id_perfil)
        self.selector_perfil.marcar_aplicado(id_perfil)
        self.statusBar().showMessage(
            self.tr("Perfil «{nombre}» actualizado").format(nombre=perfil.nombre)
        )

    def _administrar_perfiles(self) -> None:
        """«Administrar perfiles…» (avanzado): lista, duplicar, renombrar, eliminar, E/I."""
        if self._lote_en_curso or self._creando:
            return
        dialogo = DialogoPerfilesMaquina(
            self._almacen_perfiles,
            self._lanzador,
            app_version=self._deps.version_app,
            tema=self._deps.gestor_tema.tema_actual,
            al_resultado_tardio=self._mostrar_resultado_tardio,
            parent=self,
        )
        dialogo.perfiles_cambiados.connect(self._al_cambiar_lista_perfiles)
        dialogo.usar_pedido.connect(self._usar_perfil_pedido)
        dialogo.crear_pedido.connect(self._guardar_perfil)
        dialogo.exec()
        dialogo.deleteLater()

    def _al_cambiar_lista_perfiles(self, cambiados: object) -> None:
        """Si el perfil aplicado se eliminó o cambió, el selector pasa a «Personalizado»."""
        actual = self.selector_perfil.perfil_actual_id
        ids = cambiados if isinstance(cambiados, (set, frozenset)) else frozenset()
        self._recargar_selector(None if actual in ids else actual)

    def _usar_perfil_pedido(self, perfil: object) -> None:
        if isinstance(perfil, PerfilMaquina) and perfil.id:
            self._al_elegir_perfil(perfil.id)

    # --- Cambios sin guardar (RF-G08) ---

    def _definicion_actual(self) -> DefinicionLote:
        return self.bloque_lote.definicion(self.formulario.configuracion())

    def _huella_de(self, definicion: DefinicionLote) -> dict[str, object] | None:
        """Huella de lo que se guardaría (``None`` si no se puede serializar)."""
        try:
            return lote_a_dict(LoteGuardado("", definicion))
        except (ValueError, TypeError, KeyError, ErrorProxLaunch):
            return None

    def _hay_cambios_sin_guardar(self) -> bool:
        """Hay un lote cargado, importado o guardado y el actual ya no coincide con él."""
        if self._huella_guardada is None or not self._formulario_listo:
            return False
        actual = self._huella_de(self._definicion_actual())
        return actual is None or actual != self._huella_guardada

    def _preguntar_guardar_cambios(self) -> str:
        """«Guardar / No guardar / Cancelar» con el foco en Cancelar: ``guardar``, ``descartar`` o
        ``cancelar``."""
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Icon.Warning)
        caja.setWindowTitle(self.tr("Cambios sin guardar"))
        caja.setText(self.tr("¿Guardar el lote antes de continuar?"))
        caja.setInformativeText(self.tr("Si no lo guardas, se perderán los cambios del lote."))
        guardar = caja.addButton(self.tr("Guardar"), QMessageBox.ButtonRole.AcceptRole)
        descartar = caja.addButton(self.tr("No guardar"), QMessageBox.ButtonRole.DestructiveRole)
        cancelar = caja.addButton(self.tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
        caja.setDefaultButton(cancelar)
        caja.setEscapeButton(cancelar)
        cancelar.setFocus()
        caja.exec()
        elegido = caja.clickedButton()
        if elegido is guardar:
            return "guardar"
        if elegido is descartar:
            return "descartar"
        return "cancelar"

    def _confirmar_cambios(self, continuar: Callable[[], None]) -> None:
        """Ejecuta ``continuar`` si no hay cambios sin guardar o el usuario los descarta; si
        elige «Guardar», lo ejecuta cuando el archivo ya se escribió; con «Cancelar», nada."""
        if not self._hay_cambios_sin_guardar():
            continuar()
            return
        respuesta = self._preguntar_guardar_cambios()
        if respuesta == "descartar":
            continuar()
        elif respuesta == "guardar":
            self._guardar_lote(despues=continuar)

    def _cerrar_confirmado(self) -> None:
        self._cierre_confirmado = True
        self.close()

    # --- Guardar un lote (RF-G01, RF-G02, RF-G07) ---

    def _carpeta_lotes(self) -> Path | None:
        """Carpeta sugerida de lotes, creada con permisos privados al usarla (CA-X03.2)."""
        carpeta = self._deps.directorio_lotes
        try:
            crear_carpeta_privada(carpeta)
        except OSError:
            _log.warning("No se pudo crear la carpeta de lotes")
            return None
        return carpeta

    def _nombre_sugerido_lote(self, definicion: DefinicionLote) -> str:
        if definicion.es_por_filas:
            origen = self._origen_lote
            return origen.nombre.rsplit(".", 1)[0] if origen is not None else ""
        if usa_nombre_de_plantilla(definicion):
            return definicion.plantilla.nombre
        return definicion.patron.prefijo

    def _version_proxmox_texto(self) -> str | None:
        sesion = self._sesion
        return sesion.version.texto if sesion is not None else None

    def _guardar_lote(
        self,
        *,
        como: bool = False,
        despues: Callable[[], None] | None = None,
        para_cerrar: bool = False,
    ) -> None:
        """«Guardar lote…»: errores de reglas no impiden guardar un borrador (CA-G02.1)."""
        if not self._formulario_listo:
            return
        if not self.bloque_lote.es_por_filas:
            malos = self.formulario.campos_no_numericos()
            if malos:
                texto = self.tr(
                    "No se puede guardar el lote: {campos} no es un número. Corrígelo e inténtalo "
                    "de nuevo."
                ).format(campos=", ".join(f"«{m}»" for m in malos))
                self._errores_sesion = [texto]
                self._pintar_avisos()
                self.statusBar().showMessage(texto)
                return
        definicion = self._definicion_actual()
        archivo_origen = self._ruta_lote.name if self._ruta_lote is not None and not como else None
        dialogo = DialogoGuardarLote(
            nombre_sugerido=self._nombre_sugerido_lote(definicion),
            hay_problemas=self._hay_problemas,
            archivo_origen=archivo_origen,
            parent=self,
        )
        if not dialogo.ejecutar():
            dialogo.deleteLater()
            return
        nombre, accion, sugerido = dialogo.nombre, dialogo.accion, dialogo.nombre_archivo_sugerido
        dialogo.deleteLater()
        if accion == AccionGuardarLote.SOBRESCRIBIR and self._ruta_lote is not None:
            ruta: Path | None = self._ruta_lote
        else:
            ruta = elegir_para_guardar(
                self, TipoArchivo.LOTE, sugerido, carpeta=self._carpeta_lotes()
            )
        if ruta is None:
            return
        lote = LoteGuardado(nombre, definicion, self._version_proxmox_texto())
        if para_cerrar:
            # Mientras se escribe, otro intento de cerrar se ignora y la ventana no se toca.
            self._guardando_para_cerrar = True
            self.setEnabled(False)
        self._lanzador.lanzar(
            guardar_lote_guardado,
            ruta,
            lote,
            self._deps.version_app,
            al_terminar=lambda r: self._lote_guardado(r, lote, despues),
            al_fallar=lambda e: self._fallo_guardar_lote(e),
        )

    def _liberar_cierre_en_guardado(self) -> None:
        if self._guardando_para_cerrar:
            self._guardando_para_cerrar = False
            self.setEnabled(True)

    def _fallo_guardar_lote(self, error: ErrorProxLaunch) -> None:
        self._liberar_cierre_en_guardado()
        self._mostrar_error_archivo(error)

    def _lote_guardado(
        self, ruta: Path, lote: LoteGuardado, despues: Callable[[], None] | None
    ) -> None:
        self._liberar_cierre_en_guardado()
        self._ruta_lote = ruta
        if self._origen_lote is None:
            # Un lote guardado cuenta como lote de archivo: cambiar de servidor no lo reinicia.
            self._origen_lote = _OrigenLote("guardado", lote.nombre)
        self._huella_guardada = self._huella_de(lote.definicion)
        self._errores_sesion = []
        self._pintar_avisos()
        self.statusBar().showMessage(
            self.tr("Lote guardado en «{archivo}»").format(archivo=ruta.name)
        )
        if despues is not None:
            despues()

    # --- Abrir un lote guardado (RF-G03..G06) ---

    def _abrir_lote(self) -> None:
        if not self._formulario_listo or self._lote_en_curso or self._planificando:
            return
        self._confirmar_cambios(self._elegir_y_leer_lote)

    def _elegir_y_leer_lote(self) -> None:
        ruta = elegir_para_abrir(self, TipoArchivo.LOTE)
        if ruta is None:
            return
        self.statusBar().showMessage(self.tr("Leyendo el lote…"))
        self._lanzador.lanzar(
            leer_lote_guardado,
            ruta,
            al_terminar=lambda archivo: self._lote_leido(archivo, ruta),
            al_fallar=self._mostrar_error_archivo,  # el formulario no cambia (carga atómica)
        )

    def _lote_leido(self, archivo: Any, ruta: Path) -> None:
        """Vuelca el lote leído de una vez en el hilo de la interfaz (RNF-M11). No crea nada."""
        lote: LoteGuardado = archivo.lote
        definicion = lote.definicion
        self._errores_sesion = []
        self._aplicando = True
        try:
            if definicion.es_por_filas:
                origen = _OrigenLote("guardado", lote.nombre, total_filas=0)
                self._entrar_por_filas(definicion, origen)
                self._origen_lote = origen
            else:
                self._mostrar_modo_filas(False)
                self.formulario.aplicar_hardware(definicion.plantilla)
                if usa_nombre_de_plantilla(definicion) and definicion.plantilla.nombre:
                    self.formulario.establecer_nombre(definicion.plantilla.nombre)
                self.bloque_lote.establecer_definicion(definicion)
                self.resumen_lote.establecer_total_filas_archivo(None)
                self._origen_lote = _OrigenLote("guardado", lote.nombre)
        finally:
            self._aplicando = False
        self._ruta_lote = ruta
        self.selector_perfil.marcar_aplicado(None)  # un lote cargado es «Personalizado»
        self._cfg_ultima_aplicada = self.formulario.configuracion()
        avisos = [texto_aviso_archivo(a) for a in archivo.avisos]
        aviso_version = self._aviso_version_lote(lote.version_proxmox)
        if aviso_version:
            avisos.append(aviso_version)
        self.panel_avisos_archivo.mostrar(avisos)
        self._al_editar_plantilla()  # el resumen anterior ya no vale (CA-G04.2)
        self._actualizar_desajustes()
        self._huella_guardada = self._huella_de(self._definicion_actual())
        self.statusBar().showMessage(self.tr("Lote «{nombre}» cargado").format(nombre=lote.nombre))
        self._timer_validar.start()

    def _aviso_version_lote(self, version: str | None) -> str:
        """CA-G04.6: el lote se guardó con una versión de Proxmox mayor que la del servidor."""
        inv = self._inv
        m = re.match(r"(\d+)\.(\d+)", version or "")
        if m is None or inv is None:
            return ""
        guardada = (int(m.group(1)), int(m.group(2)))
        if guardada <= (inv.version.mayor, inv.version.menor):
            return ""
        return self.tr(
            "El lote se guardó con Proxmox {guardada}; este servidor tiene {actual}. Algunas "
            "opciones podrían no estar disponibles."
        ).format(guardada=version, actual=f"{inv.version.mayor}.{inv.version.menor}")

    def _actualizar_desajustes(self) -> None:
        """Valores del lote que el servidor no tiene (E-M15): nunca se sustituyen solos."""
        inv = self._inv
        if inv is None or self._origen_lote is None:
            self.panel_no_encaja.establecer_desajustes(())
            return
        definicion = self._definicion_actual()
        self.origen.cargar_necesidades(definicion)
        self.panel_no_encaja.establecer_desajustes(
            desajustes(definicion, inv), [f.origen for f in definicion.filas]
        )

    def _sustituir_desajuste(self, desajuste: object, nuevo: object) -> None:
        """«Usar otro…» o «Pasar a Automático»: acción explícita del usuario."""
        if not isinstance(desajuste, Desajuste) or not (nuevo is None or isinstance(nuevo, str)):
            return
        if self._lote_en_curso:
            return
        try:
            definicion = sustituir(self._definicion_actual(), desajuste, nuevo)
        except ValueError:
            return
        self._aplicando = True
        try:
            if definicion.es_por_filas:
                self.bloque_lote.actualizar_filas(definicion)
                self.panel_filas.actualizar_filas(definicion, self.panel_filas.titulo)
            else:
                self.formulario.aplicar_hardware(definicion.plantilla)
                self.bloque_lote.establecer_definicion(definicion)
        finally:
            self._aplicando = False
        self._al_editar_plantilla()
        self._actualizar_desajustes()
        self._timer_validar.start()

    # --- Lote por filas (D-22) ---

    def _mostrar_modo_filas(self, activo: bool) -> None:
        """Con un lote por filas la tabla sustituye al formulario y al resumen de una máquina."""
        self.panel_filas.setVisible(activo)
        self.formulario.setVisible(not activo)
        self.selector_perfil.setVisible(not activo)
        self.resumen.setVisible(not activo)
        self._actualizar_acciones()

    def _entrar_por_filas(self, definicion: DefinicionLote, origen: _OrigenLote) -> None:
        """Muestra el lote por filas: bloque reducido y tabla de solo lectura. No crea (INV-M6)."""
        self.bloque_lote.establecer_por_filas(definicion)
        self.panel_filas.establecer(
            definicion,
            origen=origen.nombre,
            desde_archivo=origen.tipo == "csv",
            puede_revisar=origen.tabla is not None,
        )
        self.resumen_lote.establecer_total_filas_archivo(origen.total_filas or None)
        self._mostrar_modo_filas(True)

    def _salir_de_por_filas(self) -> None:
        if not self.bloque_lote.es_por_filas or self._lote_en_curso:
            return
        self._confirmar_cambios(self._salir_de_por_filas_confirmado)

    def _salir_de_por_filas_confirmado(self) -> None:
        if not self.bloque_lote.es_por_filas or self._lote_en_curso:
            return  # pudo cambiar mientras se guardaba el lote
        self.bloque_lote.salir_de_por_filas()
        self._mostrar_modo_filas(False)
        self._origen_lote = None
        self._ruta_lote = None
        self.panel_no_encaja.establecer_desajustes(())
        self.panel_avisos_archivo.mostrar([])
        self.resumen_lote.establecer_total_filas_archivo(None)
        self._al_editar_plantilla()
        # Base de «cambios sin guardar»: el formulario tal como queda al salir.
        self._huella_guardada = self._huella_de(self._definicion_actual())
        self._timer_validar.start()

    def _etiqueta_fila(self, definicion: DefinicionLote, indice: int | None) -> str | None:
        if indice is None or not 0 <= indice < len(definicion.filas):
            return None
        origen = definicion.filas[indice].origen
        return str(origen if origen is not None else indice + 1)

    def _revalidar_por_filas(self) -> None:
        """Capa 1 del lote por filas (V-L01, V-M07, V-M10, V-02): se muestra junto a la tabla."""
        cfg = self.formulario.configuracion()
        problemas = self.bloque_lote.problemas(cfg)
        self.bloque_lote.aplicar_problemas(problemas)
        definicion = self.bloque_lote.definicion(cfg)
        errores = [p for p in problemas if p.severidad.value == "error"]
        textos = list(
            dict.fromkeys(
                texto_problema_lote(p, fila=self._etiqueta_fila(definicion, p.indice))
                for p in errores
            )
        )
        self._hay_problemas = bool(errores)
        self.panel_filas.mostrar_problemas(textos)
        self.panel_filas.establecer_bloqueo_resumen(
            self.tr("Corrige los errores marcados para poder ver el resumen.") if textos else None
        )
        self.panel_filas.bloquear(self._creando or self._lote_lleno_o_ocupado())
        if self._origen_lote is not None:
            self._actualizar_desajustes()

    def _lote_lleno_o_ocupado(self) -> bool:
        return self._lote_en_curso or self._planificando or self._iniciando_lote

    def _actualizar_filas(self, definicion: DefinicionLote, *, replanificar: bool) -> None:
        """Cambia las filas del lote (quitar o reasignar VMID) y vuelve a mostrar lo que toque."""
        if not definicion.filas:
            self._salir_de_por_filas_confirmado()  # acción explícita: sin segunda pregunta
            return
        self.bloque_lote.actualizar_filas(definicion)
        origen = self._origen_lote
        nombre = origen.nombre if origen is not None else ""
        self.panel_filas.actualizar_filas(
            definicion,
            texto_titulo_filas(
                len(definicion.filas),
                nombre,
                desde_archivo=origen is not None and origen.tipo == "csv",
            ),
        )
        if replanificar:
            self._ver_resumen_lote()
        else:
            self._al_editar_plantilla()
        self._timer_validar.start()

    def _quitar_filas(self, indices: object) -> None:
        """«Quitar las filas seleccionadas» de la tabla (el resumen anterior deja de valer)."""
        if not isinstance(indices, tuple) or self._lote_en_curso:
            return
        try:
            nueva = sin_filas(self._definicion_actual(), indices)
        except ValueError:
            return
        self._actualizar_filas(nueva, replanificar=False)

    def _quitar_filas_que_no_caben(self, indices: object) -> None:
        """«Quitar las filas que no caben» (CA-C08.6): replanifica con las que sí caben."""
        plan = self.resumen_lote.plan
        if self._reintento is not None:
            return  # el plan es el de un reintento: no es el lote del formulario
        if plan is None or not isinstance(indices, tuple) or self._lote_lleno_o_ocupado():
            return
        try:
            nueva = sin_filas(plan.definicion, indices)
        except ValueError:
            return
        self._actualizar_filas(nueva, replanificar=True)

    def _asignar_automaticamente(self, indices: object) -> None:
        """VMID explícito ocupado: «Asignar automáticamente» (acción explícita, CA-C09.3)."""
        plan = self.resumen_lote.plan
        if self._reintento is not None:
            return  # el plan es el de un reintento: no es el lote del formulario
        if plan is None or not isinstance(indices, tuple) or self._lote_lleno_o_ocupado():
            return
        definicion = plan.definicion
        try:
            for i in indices:
                definicion = reemplazar_fila(
                    definicion, i, dataclasses.replace(definicion.filas[i], vmid=None)
                )
        except (ValueError, IndexError):
            return
        self._actualizar_filas(definicion, replanificar=True)

    # --- Importar desde CSV (RF-C01..C09, C13, C15) ---

    def _nuevo_dialogo_csv(self) -> DialogoImportarCsv:
        perfil_base = self.selector_perfil.perfil_actual_id or ID_PREDETERMINADO
        return DialogoImportarCsv(
            self,
            perfiles=self._almacen_perfiles.todos(),
            perfil_base_id=perfil_base,
            inv=self._inv,
            nodo_referencia=self.formulario.nodo_efectivo() or None,
            lanzador=self._lanzador,
            avanzado=self.avanzado,
            alias_extra=alias_columnas_csv(),
            tema=self._deps.gestor_tema.tema_actual,
            al_resultado_tardio=self._mostrar_resultado_tardio,
        )

    def _mostrar_resultado_tardio(self, texto: str, es_error: bool) -> None:
        """Resultado de una escritura que terminó cuando su diálogo ya estaba cerrado."""
        if es_error:
            self._errores_sesion = [texto]
            self._pintar_avisos()
        self.statusBar().showMessage(texto.splitlines()[0] if texto else "")

    def _importar_csv(self) -> None:
        if self._lote_en_curso or self._planificando or self._iniciando_lote:
            return
        self._confirmar_cambios(self._importar_csv_ya)

    def _importar_csv_ya(self) -> None:
        dialogo = self._nuevo_dialogo_csv()
        elegido = dialogo.ejecutar()
        try:
            if elegido is None:
                return  # el formulario no cambia (carga atómica)
            resultado, numeros = elegido
            self._aplicar_importacion(resultado, numeros, dialogo.tabla_csv, dialogo.nombre_archivo)
        finally:
            dialogo.deleteLater()

    def _revisar_filas(self) -> None:
        """«Revisar filas…»: reabre la vista previa del mismo CSV, sin releerlo."""
        origen = self._origen_lote
        if origen is None or origen.tabla is None or origen.resultado is None:
            return
        if self._lote_lleno_o_ocupado():
            return
        dialogo = self._nuevo_dialogo_csv()
        # Se reinterpreta contra el inventario ACTUAL antes de mostrar: el servidor pudo cambiar
        # desde la importación (storages, bridges, nodos).
        resultado_actual = origen.resultado
        with contextlib.suppress(ErrorProxLaunch):  # si falla se muestra el anterior
            resultado_actual = interpretar(
                origen.tabla,
                perfil_base=dialogo.perfil_base,
                perfiles=self._almacen_perfiles.todos(),
                inv=self._inv,
                nodo_referencia=self.formulario.nodo_efectivo() or None,
                alias_extra=alias_columnas_csv(),
            )
        dialogo.mostrar_resultado(origen.tabla, resultado_actual, origen.nombre)
        elegido = dialogo.ejecutar()
        try:
            if elegido is None:
                return
            resultado, numeros = elegido
            self._aplicar_importacion(resultado, numeros, origen.tabla, origen.nombre)
        finally:
            dialogo.deleteLater()

    def _aplicar_importacion(
        self,
        resultado: ResultadoImportacion,
        numeros: tuple[int, ...],
        tabla: TablaCsv | None,
        nombre_archivo: str,
    ) -> None:
        """Convierte las filas elegidas en un lote por filas. NO habilita «Crear» (INV-M6)."""
        try:
            filas = filas_lote(resultado, numeros)
        except ValueError:
            self.statusBar().showMessage(self.tr("No se pudieron importar las filas elegidas."))
            return
        if not filas:
            return
        algoritmo = Algoritmo(self.bloque_lote.combo_algoritmo.currentData())
        definicion = definicion_por_filas(
            filas,
            plantilla_base=copy.deepcopy(filas[0].cfg),
            algoritmo=algoritmo,
            vmid_inicial=None,
            etiquetar=self.bloque_lote.chk_etiquetar.isChecked(),
        )
        origen = _OrigenLote("csv", nombre_archivo, tabla, resultado, len(resultado.filas))
        self._entrar_por_filas(definicion, origen)
        self._origen_lote = origen
        self._ruta_lote = None
        self._huella_guardada = _SIN_GUARDAR  # importado y sin guardar (RF-G08)
        self.panel_no_encaja.establecer_desajustes(())
        self.panel_avisos_archivo.mostrar([])
        self._al_editar_plantilla()
        self.statusBar().showMessage(
            self.tr("Se importaron %n máquinas desde «{archivo}»", None, len(filas)).format(
                archivo=nombre_archivo
            )
        )
        self._timer_validar.start()

    def _descargar_plantilla_csv(self) -> None:
        descargar_plantilla(
            self,
            self._lanzador,
            al_terminar=lambda ruta: self.statusBar().showMessage(
                self.tr("Plantilla guardada en «{archivo}»").format(archivo=ruta.name)
            ),
            al_fallar=self._mostrar_error_archivo,
        )

    def _guardar_informe_csv(self) -> None:
        """«Guardar el informe del lote como CSV…» (RF-C14)."""
        informe = self._informe_actual() or self._informe_de_simulacion()
        if informe is None:
            return
        ruta = elegir_para_guardar(self, TipoArchivo.CSV, nombre_archivo_csv_sugerido(informe))
        if ruta is None:
            return
        self._lanzador.lanzar(
            escribir_informe_csv,
            ruta,
            informe,
            al_terminar=lambda r: self.statusBar().showMessage(
                self.tr("Informe guardado en «{archivo}»").format(archivo=r.name)
            ),
            al_fallar=self._mostrar_error_archivo,
        )

    # --- Cierre -----------------------------------------------------------------------

    def closeEvent(self, ev: QCloseEvent) -> None:
        """Cierra la ventana; si el cierre acaba ignorado, la confirmación previa se descarta."""
        if self._guardando_para_cerrar:
            ev.ignore()  # ya hay un cierre esperando a que termine el guardado
            return
        self._evaluar_cierre(ev)
        if not ev.isAccepted():
            self._cierre_confirmado = False

    def _cancelar_transferencia_al_cerrar(self) -> bool:
        """Pregunta (foco en «Cancelar») y, si se cierra, cancela y espera con tope (CA-O12.4)."""
        if not confirmar(
            self,
            QCoreApplication.translate("VentanaPrincipal", "Hay una transferencia en curso"),
            QCoreApplication.translate(
                "VentanaPrincipal",
                "Se está subiendo o descargando un archivo. Si cierras, se cancelará: puede quedar "
                "un archivo incompleto en el servidor y ProxLaunch no puede borrarlo.",
            ),
            QCoreApplication.translate("VentanaPrincipal", "Cancelar la transferencia y cerrar"),
            QCoreApplication.translate("VentanaPrincipal", "Seguir en ProxLaunch"),
        ):
            return False
        self.origen.cancelar_transferencia()
        self.origen.esperar_fin_de_transferencia()
        return True

    def _evaluar_cierre(self, ev: QCloseEvent) -> None:
        """CA-20.8 y RF-L23: con una tarea o un lote en curso se pide confirmación.

        Con un lote cargado o importado y cambios sin guardar se pregunta antes (RF-G08); si hay
        un lote en ejecución prevalece la confirmación de RF-L23 (un solo diálogo).
        """
        if (
            not self._cierre_confirmado
            and not self._lote_en_curso
            and not self._creando
            and self._hay_cambios_sin_guardar()
        ):
            respuesta = self._preguntar_guardar_cambios()
            if respuesta == "cancelar":
                ev.ignore()
                return
            if respuesta == "guardar":
                ev.ignore()
                self._guardar_lote(despues=self._cerrar_confirmado, para_cerrar=True)
                return
        if self.origen.transferencia_activa and not self._cancelar_transferencia_al_cerrar():
            ev.ignore()
            return
        lote = self._lote
        if lote is not None and not lote.modo_uno and self._lote_en_curso:
            snap = lote.puente.instantanea()
            terminadas = sum(1 for e in snap if e.estado not in ESTADOS_EN_CURSO)
            if not confirmar(
                self,
                QCoreApplication.translate("VentanaPrincipal", "Hay un lote en curso"),
                QCoreApplication.translate(
                    "VentanaPrincipal",
                    "Hay un lote en curso ({x} de {n} terminadas). Si cierras, las tareas ya "
                    "enviadas seguirán en Proxmox, pero ProxLaunch no enviará el resto ni podrá "
                    "deshacer lo creado.",
                ).format(x=terminadas, n=len(snap)),
                QCoreApplication.translate("VentanaPrincipal", "Cerrar de todos modos"),
                QCoreApplication.translate("VentanaPrincipal", "Seguir en ProxLaunch"),
            ):
                ev.ignore()
                return
            lote.control.dejar_de_esperar()
            if lote.control_rollback is not None:
                lote.control_rollback.cancelar()
                lote.control_rollback.dejar_de_esperar()  # B1: el «Deshacer» también se corta
            self._guardar_informe_parcial(lote)
        elif lote is not None and lote.modo_uno and lote.deshaciendo and not lote.cerrado:
            # B1: un «Deshacer» de una sola máquina se corta al cerrar (con lotes, ver arriba).
            if not confirmar(
                self,
                QCoreApplication.translate("VentanaPrincipal", "Hay un «Deshacer» en curso"),
                QCoreApplication.translate(
                    "VentanaPrincipal",
                    "Se están eliminando máquinas. Si cierras, ProxLaunch dejará de esperar: "
                    "las eliminaciones ya enviadas seguirán en Proxmox y el resto no se hará.",
                ),
                QCoreApplication.translate("VentanaPrincipal", "Cerrar de todos modos"),
                QCoreApplication.translate("VentanaPrincipal", "Seguir en ProxLaunch"),
            ):
                ev.ignore()
                return
            if lote.control_rollback is not None:
                lote.control_rollback.cancelar()
                lote.control_rollback.dejar_de_esperar()
            lote.control.dejar_de_esperar()
        elif lote is not None and lote.modo_uno and self._creando:
            lote.control.dejar_de_esperar()
        if self._creando:
            boton = QMessageBox.question(
                self,
                self.tr("Hay una máquina en creación"),
                self.tr(
                    "Se está creando una máquina. Si cierras ProxLaunch, la tarea sigue "
                    "ejecutándose en el servidor Proxmox, pero ya no verás su resultado. "
                    "¿Cerrar de todos modos?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if boton != QMessageBox.StandardButton.Yes:
                ev.ignore()
                return
        # Se avisa, se cancela y se espera un tope corto. Si algún hilo sigue (p. ej. una
        # petición de red bloqueada) no se fuerza la salida: los hilos del pool no impiden
        # que el proceso termine al cerrar la aplicación y la tarea sigue en Proxmox.
        if self._lanzador.hay_activos:
            self.statusBar().showMessage(self.tr("Cerrando..."))
            self.setEnabled(False)
            QApplication.processEvents()
        self._lanzador.cancelar_todos()
        terminaron = self._lanzador.esperar(3000)
        sesion = self._sesion
        if sesion is not None and not terminaron:
            # B1: un hilo sigue vivo y podría renovar el ticket tras cerrar la sesión (el
            # cliente suelta el autenticador). No se cierra la sesión: el proceso termina de
            # todos modos y los hilos del pool no lo retienen.
            _log.warning("Hay hilos activos al cerrar: no se cierra la sesión para no renovar")
        elif sesion is not None:
            try:
                self._deps.servicio_conexion.cerrar_sesion(sesion)
            except Exception:  # cerrar la ventana nunca debe fallar
                _log.warning("No se pudo cerrar la sesión limpiamente", exc_info=True)
        super().closeEvent(ev)
