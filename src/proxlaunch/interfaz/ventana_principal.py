"""Ventana principal: barra superior, formulario, resumen y progreso (RF-19 a RF-24)."""

from __future__ import annotations

import dataclasses
import logging
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
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.dialogos.acerca_de import DialogoAcercaDe
from proxlaunch.interfaz.dialogos.conexion import DialogoConexion
from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.dialogos.pausa_lote import AccionPausa, DialogoPausaLote
from proxlaunch.interfaz.informe_lote import (
    guardar_informe_parcial,
    tomar_aviso_informe_parcial,
)
from proxlaunch.interfaz.modelos_tabla import texto_aviso_entrada
from proxlaunch.interfaz.tema import GestorTema, ModoTema
from proxlaunch.interfaz.textos import (
    privilegio_faltante_critico,
    texto_aviso,
    texto_desenlace,
    texto_error,
    texto_existe_sin_confirmar,
    texto_motivo_nodo,
    texto_problema_lote,
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
    planificar_lote,
    reanudar_seguimiento,
    recargar_nodo,
    reintentar_nodos,
    replanificar_lote,
    simular_lote,
)
from proxlaunch.interfaz.vistas.barra_superior import BarraSuperior, cargar_svg, nombre_logotipo
from proxlaunch.interfaz.vistas.bloque_lote import BloqueLote
from proxlaunch.interfaz.vistas.campos import mensaje, poner_mensaje
from proxlaunch.interfaz.vistas.detalles_tecnicos import texto_detalles
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.interfaz.vistas.progreso import PanelProgreso
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, ProgresoLote, texto_barra
from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.interfaz.vistas.resumen_lote import ResumenLote
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import (
    ACTUALIZACIONES_POR_S,
    ETIQUETA_APP,
    PLAN_MAX_EDAD_S,
    PREFIJO_ETIQUETA_LOTE,
    UMBRAL_CONFIRMACION_DOBLE,
    UMBRAL_PAUSA_ERRORES,
)
from proxlaunch.nucleo.lote.informe import construir_informe, informe_desde_entradas
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    ESTADOS_DUDOSOS,
    ESTADOS_EN_CURSO,
    CandidatoRollback,
    DefinicionLote,
    Destino,
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
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
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.persistencia.preferencias import (
    Modo,
    Preferencias,
    RepositorioPreferencias,
    Tema,
)
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import CodigoAviso, ServicioConexion, Sesion
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.validacion import validar_vm

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
    # Permite ajustar el intervalo de sondeo (por defecto el del núcleo).
    fabrica_creacion: Callable[[Sesion], ServicioCreacion] | None = None
    # Carpeta de los informes parciales (por defecto, la de datos del usuario).
    directorio_informes: Path | None = None


# Estados que permiten reintentar la máquina en un lote nuevo: nunca se creó (RF-L21).
_ESTADOS_REINTENTABLES = frozenset(
    {EstadoMV.NO_ENVIADA, EstadoMV.NO_CREADA_SEGURA, EstadoMV.ERROR, EstadoMV.PENDIENTE}
)
_ETAPA_POR_ESTADO = {
    EstadoMV.VALIDANDO: Etapa.VALIDANDO,
    EstadoMV.ENVIANDO: Etapa.ENVIANDO,
    EstadoMV.CREANDO: Etapa.CREANDO,
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
        self._aviso_informe_parcial: str | None = None
        self._tomar_aviso_informe_parcial()

        self._construir()
        self._crear_menus()
        self._timer_validar = QTimer(self)
        self._timer_validar.setSingleShot(True)
        self._timer_validar.setInterval(0)
        self._timer_validar.timeout.connect(self._revalidar)
        self.formulario.cambiado.connect(self._timer_validar.start)
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
        self.progreso_lote.reintentar_solicitado.connect(lambda: self._reintentar_pendientes())
        self.progreso_lote.informe_solicitado.connect(self._mostrar_informe)
        self.progreso_lote.decidir_pausa_solicitado.connect(self._decidir_pausa)
        self.progreso_lote.volver_solicitado.connect(self._volver_de_lote)
        self.progreso.deshacer_solicitado.connect(self._deshacer)
        self._timer_lote = QTimer(self)
        self._timer_lote.setInterval(max(1, 1000 // ACTUALIZACIONES_POR_S))
        self._timer_lote.timeout.connect(self._tick_lote)
        self.progreso.crear_otra.connect(self._crear_otra)
        self.progreso.seguir_esperando.connect(lambda: self._reanudar(una_vez=False))
        self.progreso.comprobar_ahora.connect(lambda: self._reanudar(una_vez=True))
        self.progreso.volver.connect(self._volver_al_formulario)
        deps.gestor_tema.tema_cambiado.connect(self._al_cambiar_tema)
        self.bloque_lote.establecer_modo(self._prefs.modo == Modo.AVANZADO)
        self.formulario.establecer_modo(self._prefs.modo == Modo.AVANZADO)
        self._al_cambiar_tema(deps.gestor_tema.tema_actual)
        self.statusBar().showMessage(self.tr("Sin conexión"))

    # --- Construcción -----------------------------------------------------------------

    def _construir(self) -> None:
        central = QWidget()
        capa = QVBoxLayout(central)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        self.barra = BarraSuperior()
        capa.addWidget(self.barra)
        self._paginas = QStackedWidget()
        capa.addWidget(self._paginas, 1)
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
        izquierda = QWidget()
        ci = QVBoxLayout(izquierda)
        ci.setContentsMargins(0, 0, 0, 0)
        ci.addWidget(self.bloque_lote)
        ci.addWidget(self.formulario)
        zona = QScrollArea()
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
        zona_derecha = QScrollArea()
        zona_derecha.setWidgetResizable(True)
        zona_derecha.setFrameShape(QFrame.Shape.NoFrame)
        zona_derecha.setWidget(derecha)
        self.resumen_lote = ResumenLote()
        self.progreso_lote = ProgresoLote()
        self._pila_derecha = QStackedWidget()
        self._pila_derecha.addWidget(zona_derecha)  # 0: resumen y progreso de una máquina
        for pagina in (self.resumen_lote, self.progreso_lote):  # 1 y 2: lotes
            area = QScrollArea()
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
        m_archivo.addActions([a_conectar, a_cerrar, self._accion_ultimo_lote])
        m_archivo.addSeparator()
        m_archivo.addAction(a_salir)

        m_ver = barra.addMenu(self.tr("&Ajustes"))
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
        m_ayuda.addActions([a_guia, a_acerca])

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
        self.bloque_lote.establecer_modo(modo == Modo.AVANZADO)
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

    @property
    def avanzado(self) -> bool:
        return self._prefs.modo == Modo.AVANZADO

    # --- Conexión ---------------------------------------------------------------------

    def abrir_conexion(self, motivo: str | None = None) -> None:
        """Abre el diálogo de conexión (sin perder el formulario, CA-03.3)."""
        if self._dialogo_conexion is not None or self._creando or self._lote_bloquea_conexion():
            return
        dialogo = DialogoConexion(
            self._deps.servicio_conexion,
            self._deps.perfiles,
            self._deps.huellas,
            self._deps.secretos,
            self._lanzador,
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
            self._formulario_listo = False
            self._inv = None
            # Un resultado pendiente de otro servidor ya no se puede retomar.
            self._ultimo_resultado = None
            self._servicio_creacion = None
            self._cfg_creacion = None
            self._upid_recibido = None
            self.progreso.reiniciar()
            self.formulario.bloquear(False)
            self.bloque_lote.bloquear(False)
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
        if self._creando or self._lote_en_curso:
            return
        sesion = self._sesion
        if sesion is not None:
            try:
                self._deps.servicio_conexion.cerrar_sesion(sesion)
            except ErrorProxLaunch:
                _log.warning("No se pudo cerrar la sesión limpiamente")
        self._sesion = None
        self._inv = None
        self._formulario_listo = False
        self._perfil_id = None
        self._ultimo_resultado = None
        self.barra.limpiar()
        self._paginas.setCurrentIndex(0)
        self.statusBar().showMessage(self.tr("Sin conexión"))

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
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()
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
        self._inv = inv
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
        self.bloque_lote.establecer_inventario(inv)
        self.formulario.establecer_inventario(inv, reiniciar=reiniciar)
        self._formulario_listo = True
        self._pintar_avisos()
        self._timer_validar.start()

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
        for nodo, (storages, bridges) in recuperados.items():
            inv.storages[nodo] = tuple(storages)
            inv.bridges[nodo] = tuple(bridges)
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
            al_terminar=lambda r: self.formulario.actualizar_recursos_nodo(r[0], r[1], r[2]),
            al_fallar=lambda e: self._manejar_fallo(e, durante="al cambiar de nodo"),
        )

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
        sesion, inv = self._sesion, self._inv
        if sesion is None or inv is None:
            return
        en_lote = self.bloque_lote.es_lote
        if en_lote != self.formulario.modo_lote:
            self.formulario.establecer_lote(en_lote)
            self.resumen.establecer_modo_lote(en_lote)
        cfg = self.formulario.configuracion()
        problemas_lote = self.bloque_lote.problemas(cfg)
        self.bloque_lote.aplicar_problemas(problemas_lote)
        if en_lote:
            # El nombre y el VMID de cada máquina los fija el plan: aquí solo se muestran de
            # ejemplo y no se validan (V-L02..V-L07 ya los cubren).
            nombres = self.bloque_lote.nombres_previstos()
            cfg.nombre = nombres[0] if nombres else ""
            cfg.vmid = self.bloque_lote.definicion(cfg).vmid_inicial or inv.proximo_vmid
        problemas = validar_vm(cfg, inv, sesion.capacidades) + self.formulario.problemas_extra()
        if en_lote:
            problemas = [p for p in problemas if p.campo not in ("nombre", "vmid")]
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
        self.resumen.actualizar(
            cfg,
            self.formulario.etiquetas_discos(),
            problemas,
            avanzado=self.avanzado,
            motivo_nodo=motivo,
            bloqueo=bloqueo,
            ocupado=self._creando or self._lote_en_curso or self._planificando,
            nodo=nodo,
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
        cfg = self.formulario.configuracion()
        self._cfg_creacion = cfg
        self.formulario.bloquear(True)
        self.bloque_lote.bloquear(True)
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
        self.progreso.mostrar_resultado(texto, d, resultado.upid)
        self.progreso.detalles.establecer(
            texto_detalles(resultado.error, resultado),
            desplegar=d == Desenlace.CON_AVISOS and bool(resultado.log_tarea),
        )
        self.statusBar().showMessage(texto.splitlines()[0] if texto else "")
        error = resultado.error
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
        self.formulario.bloquear(False)
        self.bloque_lote.bloquear(False)
        self.resumen.liberar()

    def _volver_al_formulario(self) -> None:
        if self._creando:
            return
        res = self._ultimo_resultado
        if res is not None and res.desenlace in (
            Desenlace.CONEXION_PERDIDA,
            Desenlace.TIEMPO_AGOTADO,
        ):
            # Aún no se sabe si la máquina se creó: volver y repetir podría duplicarla.
            respuesta = QMessageBox.question(
                self,
                self.tr("Todavía no sabemos si se creó"),
                self.tr(
                    "No hemos podido confirmar si la máquina se creó. Si vuelves al formulario "
                    "y la creas otra vez, podrías duplicarla. ¿Volver de todos modos?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                return
        self.progreso.reiniciar()
        self._desbloquear()
        self._timer_validar.start()

    def _crear_otra(self) -> None:
        if self._creando:
            return
        self.progreso.reiniciar()
        self._desbloquear()
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
            self.progreso.mostrar_resultado(texto, Desenlace.OK, None)
            self._sincronizar_libro_uno(self._ultimo_resultado)
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
        definicion = self.bloque_lote.definicion(self.formulario.configuracion())
        self._reintento = None
        self._nodo_reintento = None
        self._planificar(definicion, simulando=False)

    def _planificar(self, definicion: DefinicionLote, *, simulando: bool) -> None:
        sesion, inv = self._sesion, self._inv
        if sesion is None or inv is None or self._planificando:
            return
        self._planificando = True
        self.resumen_lote.mostrar_planificando()
        self._pila_derecha.setCurrentIndex(1)
        vf = self._version_forzada(sesion)
        reloj = self._deps.reloj
        gen = self._gen_plan
        if simulando:
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
        self._inv = inv
        self._al_planificado(plan)
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
        self._inv = inv
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
        self._lote = _Lote(plan, inv, sesion, self._perfil_id, control, puente, modo_uno)
        self._accion_ultimo_lote.setEnabled(False)
        self.formulario.bloquear(True)
        self.bloque_lote.bloquear(True)
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
            al_terminar=self._al_lote_terminado,
            al_fallar=self._fallo_lote,
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

    def _fallo_lote(self, error: ErrorProxLaunch) -> None:
        """El motor falló fuera de lo previsto: la interfaz no se queda «ocupada» (RNF-L11)."""
        lote = self._lote
        if lote is None:
            return
        if lote.modo_uno:
            self._fin_uno(lote, None, error)
            return
        self._cerrar_dialogo_pausa(lote)
        self.progreso_lote.mostrar_error(
            self.tr("El lote terminó de forma inesperada: {m}").format(m=texto_error(error))
        )
        self._finalizar_lote()

    def _al_lote_terminado(self, libro: Libro) -> None:
        lote = self._lote
        if lote is None or lote.cerrado:
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
            al_terminar=self._al_lote_terminado,
            al_fallar=self._fallo_lote,
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
                lt.libro, etiquetado=lt.plan.definicion.etiquetar
            )
            elegibles += sum(1 for c in candidatos if c.elegible)
        self.progreso_lote.establecer_fase(
            FaseLote.TERMINADO,
            dudosas=dudosas,
            elegibles=elegibles,
            reintentables=reintentables,
        )
        self.statusBar().showMessage(texto_barra(entradas))
        self._accion_ultimo_lote.setEnabled(True)
        self._refrescar_botones_red()
        self._timer_validar.start()

    def _fin_uno(self, lote: _Lote, libro: Libro | None, error: ErrorProxLaunch | None) -> None:
        """Una sola máquina: el resultado del motor se muestra con el panel del MVP 1."""
        lote.terminado = True
        self._accion_ultimo_lote.setEnabled(libro is not None)
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

    def _sincronizar_libro_uno(self, resultado: ResultadoCreacion) -> None:
        """Tras «Comprobar» con una máquina, el libro refleja el resultado (Deshacer, informe)."""
        lote = self._lote
        if self._fin_uno_inicial or lote is None or not lote.modo_uno or lote.libro is None:
            return
        estado = (
            EstadoMV.NO_CREADA_SEGURA
            if resultado.desenlace == Desenlace.CANCELADO
            else EstadoMV(resultado.desenlace.value)
        )
        try:
            nueva = lote.libro.resolver(
                resultado.vmid,
                estado,
                t_fin=self._deps.reloj.ahora(),
                upid=resultado.upid,
                error=resultado.error,
                log=resultado.log_tarea,
            )
        except (AssertionError, KeyError):
            _log.warning("No se pudo actualizar el libro tras comprobar", exc_info=True)
            return
        lote.puente.observar(nueva)

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
        if sesion is None:
            return
        lote.terminado = False
        control = ControlLote()
        lote.control = control
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
            al_terminar=lambda _l: self._finalizar_lote(),
            al_fallar=self._fallo_lote,
        )

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
            for c in servicio.elegibles(lt.libro, etiquetado=lt.plan.definicion.etiquetar):
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
        lote.deshaciendo = True
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
        self.progreso_lote.actualizar_rollback(resultados)
        error = lote.control_rollback.error_pausa if lote.control_rollback else None
        if error is not None:
            self.progreso_lote.mostrar_error(texto_error(error))
        lote.deshaciendo = False
        lote.puente_rollback = None
        self._finalizar_lote()
        self._descubrir()  # CA-L18.12: refresca VMIDs y espacio libre

    def _fallo_deshacer(self, lote: _Lote, error: ErrorProxLaunch) -> None:
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
        definicion = dataclasses.replace(
            lote.plan.definicion,
            cantidad=len(elementos),
            vmid_inicial=None,
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
        return [*perfil.hosts, sesion.host_activo, perfil.usuario, sesion.usuario_efectivo]

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
            )
        return informe_desde_entradas(
            lote.plan,
            lote.puente.instantanea(),
            metadatos,
            rollback,
            self._deps.reloj.ahora(),
            ocultar,
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
        if lote is None or lote.libro is None:
            return
        self.progreso_lote.iniciar(lote.plan)
        self._pila_derecha.setCurrentIndex(2)
        self.formulario.bloquear(True)
        self.bloque_lote.bloquear(True)
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

    # --- Cierre -----------------------------------------------------------------------

    def closeEvent(self, ev: QCloseEvent) -> None:
        """CA-20.8 y RF-L23: con una tarea o un lote en curso se pide confirmación."""
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
            self._guardar_informe_parcial(lote)
        elif lote is not None and lote.modo_uno and self._creando:
            lote.control.dejar_de_esperar()
        if self._creando:
            respuesta = QMessageBox.question(
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
            if respuesta != QMessageBox.StandardButton.Yes:
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
        self._lanzador.esperar(3000)
        sesion = self._sesion
        if sesion is not None:
            try:
                self._deps.servicio_conexion.cerrar_sesion(sesion)
            except Exception:  # cerrar la ventana nunca debe fallar
                _log.warning("No se pudo cerrar la sesión limpiamente", exc_info=True)
        super().closeEvent(ev)
