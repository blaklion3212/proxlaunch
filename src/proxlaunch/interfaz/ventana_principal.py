"""Ventana principal: barra superior, formulario, resumen y progreso (RF-19 a RF-24)."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
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
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.tema import GestorTema, ModoTema
from proxlaunch.interfaz.textos import (
    privilegio_faltante_critico,
    texto_aviso,
    texto_desenlace,
    texto_error,
    texto_motivo_nodo,
)
from proxlaunch.interfaz.trabajadores import (
    Lanzador,
    comprobar_vmid,
    descubrir_y_comprobar_permisos,
    reanudar_seguimiento,
    recargar_nodo,
    reintentar_nodos,
)
from proxlaunch.interfaz.vistas.barra_superior import BarraSuperior, cargar_svg, nombre_logotipo
from proxlaunch.interfaz.vistas.campos import mensaje, poner_mensaje
from proxlaunch.interfaz.vistas.detalles_tecnicos import texto_detalles
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.interfaz.vistas.progreso import PanelProgreso
from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
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
        self._errores_sesion: list[str] = []
        self._avisos_extra: list[str] = []

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
        self.progreso.crear_otra.connect(self._crear_otra)
        self.progreso.seguir_esperando.connect(lambda: self._reanudar(una_vez=False))
        self.progreso.comprobar_ahora.connect(lambda: self._reanudar(una_vez=True))
        self.progreso.volver.connect(self._volver_al_formulario)
        deps.gestor_tema.tema_cambiado.connect(self._al_cambiar_tema)
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
        zona = QScrollArea()
        zona.setWidgetResizable(True)
        zona.setFrameShape(QFrame.Shape.NoFrame)
        zona.setWidget(self.formulario)
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
        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.addWidget(zona)
        divisor.addWidget(zona_derecha)
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
        m_archivo.addActions([a_conectar, a_cerrar])
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
        a_guia.triggered.connect(lambda: DialogoGuiaToken(self).exec())
        a_acerca = QAction(self.tr("Acerca de ProxLaunch"), self)
        a_acerca.triggered.connect(
            lambda: DialogoAcercaDe(self._deps.gestor_tema.tema_actual, self).exec()
        )
        m_ayuda.addActions([a_guia, a_acerca])

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

    @property
    def avanzado(self) -> bool:
        return self._prefs.modo == Modo.AVANZADO

    # --- Conexión ---------------------------------------------------------------------

    def abrir_conexion(self, motivo: str | None = None) -> None:
        """Abre el diálogo de conexión (sin perder el formulario, CA-03.3)."""
        if self._dialogo_conexion is not None or self._creando:
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
        dialogo.finished.connect(lambda _r: self._dialogo_cerrado())
        dialogo.open()

    def _dialogo_cerrado(self) -> None:
        self._dialogo_conexion = None

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
        if cambio_perfil:
            self._formulario_listo = False
            self._inv = None
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
        if self._creando:
            return
        self._sesion = None
        self._inv = None
        self._formulario_listo = False
        self._perfil_id = None
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
        textos_aviso = list(self._avisos_extra)
        if self._sesion is not None:
            textos_aviso.extend(texto_aviso(a) for a in self._sesion.avisos)
        for texto in dict.fromkeys(textos_aviso):
            self._zona_avisos.addWidget(self._etiqueta_aviso(texto, error=False))
        for texto in self._errores_sesion:
            self._zona_avisos.addWidget(self._etiqueta_aviso(texto, error=True))

    @staticmethod
    def _etiqueta_aviso(texto: str, *, error: bool) -> QLabel:
        lbl = QLabel(texto)
        lbl.setWordWrap(True)
        lbl.setProperty("error" if error else "aviso", True)
        return lbl

    # --- Descubrimiento ---------------------------------------------------------------

    def _descubrir(self) -> None:
        sesion = self._sesion
        if sesion is None or self._descubriendo:
            return
        self._descubriendo = True
        self.boton_actualizar.setEnabled(False)
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
        self.boton_actualizar.setEnabled(True)
        self._estado_descubrimiento.setText(self.tr("No se pudo leer el servidor."))
        self._manejar_fallo(error, durante="en el descubrimiento")

    def _al_descubierto(self, resultado: tuple[Inventario, list[str] | None]) -> None:
        inv, _faltantes = resultado
        self._descubriendo = False
        self.boton_actualizar.setEnabled(True)
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
        if sesion is None or inv is None or not inv.errores_por_nodo:
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
        self.boton_reintentar.setEnabled(True)
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
        cfg = self.formulario.configuracion()
        problemas = validar_vm(cfg, inv, sesion.capacidades) + self.formulario.problemas_extra()
        self.formulario.aplicar_problemas(problemas)
        motivo = (
            texto_motivo_nodo(self.formulario.motivo_nodo)
            if self.formulario.es_automatico and self.formulario.motivo_nodo
            else ""
        )
        nodo = next((n for n in inv.topologia.nodos if n.nombre == cfg.nodo), None)
        self.resumen.actualizar(
            cfg,
            self.formulario.etiquetas_discos(),
            problemas,
            avanzado=self.avanzado,
            motivo_nodo=motivo,
            bloqueo=self._bloqueo_permiso,
            ocupado=self._creando,
            nodo=nodo,
        )

    # --- Creación ---------------------------------------------------------------------

    def _crear(self) -> None:
        sesion, inv = self._sesion, self._inv
        # CA-19.6: la bandera se pone antes de lanzar nada; un segundo clic no hace nada.
        if self._creando or sesion is None or inv is None:
            return
        self._creando = True
        cfg = self.formulario.configuracion()
        self._cfg_creacion = cfg
        self.formulario.bloquear(True)
        self.progreso.iniciar()
        fabrica = self._deps.fabrica_creacion
        servicio = fabrica(sesion) if fabrica else ServicioCreacion(sesion, self._deps.reloj)
        self._servicio_creacion = servicio
        self._lanzador.lanzar(
            servicio.crear,
            cfg,
            inv,
            con_contexto=True,
            al_etapa=self._al_etapa,
            al_terminar=self._al_terminar_creacion,
            al_fallar=self._fallo_creacion,
        )
        self._timer_validar.start()

    def _al_etapa(self, etapa: Etapa) -> None:
        self.progreso.establecer_etapa(etapa)

    def _fallo_creacion(self, error: ErrorProxLaunch) -> None:
        """Error inesperado fuera del flujo normal del servicio."""
        cfg = self._cfg_creacion
        if cfg is None:
            return
        self._al_terminar_creacion(
            ResultadoCreacion(Desenlace.ERROR, cfg.vmid, cfg.nodo, None, error)
        )

    def _al_terminar_creacion(self, resultado: ResultadoCreacion) -> None:
        cfg = self._cfg_creacion
        self._creando = False
        self._ultimo_resultado = resultado
        nombre = cfg.nombre if cfg else ""
        texto = texto_desenlace(resultado, nombre)
        d = resultado.desenlace
        if resultado.error is not None and d == Desenlace.CON_AVISOS:
            texto += "\n" + texto_error(resultado.error)
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
        self.resumen.liberar()

    def _volver_al_formulario(self) -> None:
        if self._creando:
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
        servicio = self._servicio_creacion
        if self._creando or sesion is None or cfg is None or res is None or servicio is None:
            return
        if not res.upid:
            return
        self._creando = True
        self.progreso.mostrar_progreso_mensaje(
            self.tr("Comprobando la tarea...")
            if una_vez
            else self.tr("Esperando a que termine la tarea...")
        )
        self._lanzador.lanzar(
            reanudar_seguimiento,
            servicio,
            sesion,
            cfg,
            res.upid,
            una_vez,
            con_contexto=True,
            al_etapa=self._al_etapa,
            al_terminar=self._al_terminar_creacion,
            al_fallar=self._fallo_reanudar,
        )

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
                res.upid if res else None,
                error,
            )
        )

    # --- Cierre -----------------------------------------------------------------------

    def closeEvent(self, ev: QCloseEvent) -> None:
        """CA-20.8: con una tarea en curso se pide confirmación."""
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
        self._lanzador.cancelar_todos()
        self._lanzador.esperar(3000)
        super().closeEvent(ev)
