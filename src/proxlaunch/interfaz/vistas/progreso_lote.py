"""Progreso del lote: tabla del libro, barra global, filtro y acciones (RF-L13 a RF-L21).

La tabla usa un modelo (``ModeloLibro``) que se refresca con instantáneas; no hay un widget
por máquina. La barra global cuenta máquinas terminadas, sin porcentaje inventado dentro de
cada una (CT-2) y sin tiempo estimado.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum

from PySide6.QtCore import QCoreApplication, QItemSelection, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.modelos_tabla import (
    ESTADOS_CON_ERROR,
    ESTADOS_SIN_CONFIRMAR,
    FiltroProblemas,
    ModeloLibro,
    ModeloRollback,
    TablaCopiable,
)
from proxlaunch.interfaz.textos import texto_estado_mv, texto_resumen_origen, texto_sin_urls
from proxlaunch.interfaz.vistas.campos import mensaje, poner_mensaje
from proxlaunch.interfaz.vistas.detalles_tecnicos import DetallesTecnicos
from proxlaunch.nucleo.lote.ajustes import tiene_ajustes_pendientes
from proxlaunch.nucleo.lote.modelos import (
    ESTADOS_DUDOSOS,
    ESTADOS_EN_CURSO,
    EntradaLibro,
    EstadoMV,
    Plan,
    ResultadoRollback,
)
from proxlaunch.nucleo.registro import enmascarar

_ESTADOS_EN_VUELO = frozenset(ESTADOS_EN_CURSO - {EstadoMV.PENDIENTE})


class FaseLote(StrEnum):
    """Qué está pasando con el lote; decide qué botones se ven."""

    EJECUTANDO = "ejecutando"
    CANCELANDO = "cancelando"  # se pidió cancelar y se espera a las ya enviadas
    PAUSADO = "pausado"
    COMPROBANDO = "comprobando"
    DESHACIENDO = "deshaciendo"
    TERMINADO = "terminado"


def texto_barra(entradas: Sequence[EntradaLibro]) -> str:
    """«7 de 20 terminadas · 1 con error · 2 en curso» (CA-L13.2)."""
    total = len(entradas)
    terminadas = sum(1 for e in entradas if e.estado not in ESTADOS_EN_CURSO)
    con_error = sum(1 for e in entradas if e.estado in ESTADOS_CON_ERROR)
    en_curso = sum(1 for e in entradas if e.estado in _ESTADOS_EN_VUELO)
    sin_confirmar = sum(1 for e in entradas if e.estado in ESTADOS_SIN_CONFIRMAR)
    no_enviadas = sum(1 for e in entradas if e.estado == EstadoMV.NO_ENVIADA)
    partes = [
        QCoreApplication.translate("ProgresoLote", "{t} de {n} terminadas").format(
            t=terminadas, n=total
        )
    ]
    if con_error:
        partes.append(
            QCoreApplication.translate("ProgresoLote", "{c} con error").format(c=con_error)
        )
    if sin_confirmar:
        partes.append(
            QCoreApplication.translate("ProgresoLote", "{c} sin confirmar").format(c=sin_confirmar)
        )
    if no_enviadas:
        partes.append(
            QCoreApplication.translate("ProgresoLote", "{c} sin enviar").format(c=no_enviadas)
        )
    if en_curso:
        partes.append(QCoreApplication.translate("ProgresoLote", "{c} en curso").format(c=en_curso))
    return " · ".join(partes)


def texto_detalles_entrada(e: EntradaLibro) -> str:
    """Detalles técnicos de una máquina: UPID, error original y registro de la tarea."""
    el = e.elemento
    lineas = [
        QCoreApplication.translate("ProgresoLote", "Estado: {estado} ({codigo})").format(
            estado=texto_estado_mv(e.estado), codigo=e.estado
        ),
        f"VMID: {el.vmid}",
        QCoreApplication.translate("ProgresoLote", "Nodo: {nodo}").format(nodo=el.nodo),
    ]
    origen = texto_resumen_origen(el.cfg)
    if origen:
        lineas.append(
            QCoreApplication.translate("ProgresoLote", "Sistema operativo: {o}").format(o=origen)
        )
    if e.upid:
        lineas.append(f"UPID: {e.upid}")
    if e.motivo_no_enviada:
        lineas.append(
            QCoreApplication.translate("ProgresoLote", "Motivo: {m}").format(m=e.motivo_no_enviada)
        )
    if e.avisos:
        lineas.append(
            QCoreApplication.translate("ProgresoLote", "Avisos: {a}").format(a=", ".join(e.avisos))
        )
    if e.error is not None:
        lineas.append(
            QCoreApplication.translate("ProgresoLote", "Código: {c}").format(c=e.error.codigo)
        )
        for clave, valor in e.error.params.items():
            lineas.append(f"  {clave}: {texto_sin_urls(valor)}")
        if e.error.detalle_tecnico:
            lineas.append(
                QCoreApplication.translate("ProgresoLote", "Mensaje original: {d}").format(
                    d=texto_sin_urls(e.error.detalle_tecnico)
                )
            )
    if e.log_tarea:
        lineas += ["", QCoreApplication.translate("ProgresoLote", "Registro de la tarea:")]
        lineas.extend(
            texto_sin_urls(enmascarar(linea)) for linea in e.log_tarea
        )  # defensa en profundidad
    return "\n".join(lineas)


class ProgresoLote(QWidget):
    """Seguimiento del lote en curso o terminado."""

    cancelar_solicitado = Signal()
    dejar_de_esperar_solicitado = Signal()
    comprobar_dudosas_solicitado = Signal()
    comprobar_una_solicitado = Signal(int)  # VMID de la máquina dudosa elegida
    deshacer_solicitado = Signal()
    reintentar_solicitado = Signal()
    reintentar_ajustes_solicitado = Signal()  # MVP 4: ajustes pendientes tras un clon
    informe_solicitado = Signal()
    copiar_informe_solicitado = Signal()
    decidir_pausa_solicitado = Signal()
    volver_solicitado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fase = FaseLote.TERMINADO
        self._total = 0
        self._entradas: tuple[EntradaLibro, ...] = ()

        self._titulo = QLabel()
        fuente = self._titulo.font()
        fuente.setPointSize(fuente.pointSize() + 3)
        fuente.setBold(True)
        self._titulo.setFont(fuente)
        self._titulo.setTextFormat(Qt.TextFormat.PlainText)
        self._aviso = mensaje(aviso=True)
        self._error = mensaje(error=True)

        self.barra = QProgressBar()
        self.barra.setAccessibleName(QCoreApplication.translate("ProgresoLote", "Avance del lote"))
        self.barra.setTextVisible(True)
        self.barra.setFormat("%v")  # se sustituye por el resumen en texto

        self.chk_problemas = QCheckBox(
            QCoreApplication.translate("ProgresoLote", "Mostrar solo problemas")
        )
        self.modelo = ModeloLibro(self)
        self.filtro = FiltroProblemas(self)
        self.filtro.setSourceModel(self.modelo)
        self.tabla = TablaCopiable(
            QCoreApplication.translate("ProgresoLote", "Estado de cada máquina del lote")
        )
        self.tabla.setModel(self.filtro)
        self.tabla.setMinimumHeight(180)
        self.chk_problemas.toggled.connect(self._al_filtrar)
        self.tabla.selectionModel().selectionChanged.connect(self._al_seleccionar)

        self._upid_titulo = QLabel(
            QCoreApplication.translate("ProgresoLote", "Identificador de la tarea (UPID):")
        )
        self._upid_titulo.setProperty("secundario", True)
        self._upid = QLineEdit()
        self._upid.setReadOnly(True)
        self._upid.setProperty("mono", True)
        self._upid.setAccessibleName(
            QCoreApplication.translate("ProgresoLote", "UPID de la máquina seleccionada")
        )
        self._copiar_upid = QPushButton(QCoreApplication.translate("ProgresoLote", "Copiar UPID"))
        self._copiar_upid.clicked.connect(
            lambda: QApplication.clipboard().setText(self._upid.text())
        )
        for w in (self._upid_titulo, self._upid, self._copiar_upid):
            w.hide()
        self.detalles = DetallesTecnicos()

        # Sección «Deshacer».
        self._titulo_rollback = QLabel(
            QCoreApplication.translate("ProgresoLote", "Deshaciendo el lote")
        )
        self._titulo_rollback.setProperty("secundario", True)
        self.modelo_rollback = ModeloRollback(self)
        self.tabla_rollback = TablaCopiable(
            QCoreApplication.translate("ProgresoLote", "Estado de cada máquina eliminada")
        )
        self.tabla_rollback.setModel(self.modelo_rollback)
        self.tabla_rollback.setMaximumHeight(160)
        self._titulo_rollback.hide()
        self.tabla_rollback.hide()

        self.boton_cancelar = QPushButton(
            QCoreApplication.translate("ProgresoLote", "Cancelar lote")
        )
        self.boton_decidir = QPushButton(
            QCoreApplication.translate("ProgresoLote", "Decidir qué hacer…")
        )
        self.boton_comprobar = QPushButton()
        # «Comprobar ahora» de la máquina dudosa seleccionada (CA-L15.6); solo lecturas.
        self.boton_comprobar_una = QPushButton(
            QCoreApplication.translate("ProgresoLote", "Comprobar ahora")
        )
        self.boton_comprobar_una.hide()
        self.boton_comprobar_una.clicked.connect(self._al_comprobar_una)
        self.boton_deshacer = QPushButton(QCoreApplication.translate("ProgresoLote", "Deshacer…"))
        self.boton_reintentar = QPushButton(
            QCoreApplication.translate("ProgresoLote", "Reintentar pendientes")
        )
        self.boton_reintentar_ajustes = QPushButton(
            QCoreApplication.translate("ProgresoLote", "Reintentar ajustes")
        )
        self.boton_reintentar_ajustes.setToolTip(
            QCoreApplication.translate(
                "ProgresoLote",
                "Vuelve a aplicar las etiquetas, los procesadores, la memoria o el tamaño del "
                "disco que no se pudieron cambiar tras clonar. No crea máquinas nuevas.",
            )
        )
        self.boton_informe = QPushButton(QCoreApplication.translate("ProgresoLote", "Informe"))
        self.boton_volver = QPushButton(
            QCoreApplication.translate("ProgresoLote", "Volver al formulario")
        )
        self.boton_volver.setProperty("primario", True)
        self.boton_cancelar.clicked.connect(self._al_cancelar)
        self.boton_decidir.clicked.connect(self.decidir_pausa_solicitado)
        self.boton_comprobar.clicked.connect(self.comprobar_dudosas_solicitado)
        self.boton_deshacer.clicked.connect(self.deshacer_solicitado)
        self.boton_reintentar.clicked.connect(self.reintentar_solicitado)
        self.boton_reintentar_ajustes.clicked.connect(self.reintentar_ajustes_solicitado)
        self.boton_informe.clicked.connect(self.informe_solicitado)
        self.boton_volver.clicked.connect(self.volver_solicitado)

        botones = QHBoxLayout()
        for b in (
            self.boton_cancelar,
            self.boton_decidir,
            self.boton_comprobar,
            self.boton_comprobar_una,
            self.boton_deshacer,
            self.boton_reintentar,
            self.boton_reintentar_ajustes,
            self.boton_informe,
        ):
            botones.addWidget(b)
        botones.addStretch(1)
        botones.addWidget(self.boton_volver)

        fila_upid = QHBoxLayout()
        fila_upid.addWidget(self._upid, 1)
        fila_upid.addWidget(self._copiar_upid)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        for w in (
            self._titulo,
            self._aviso,
            self._error,
            self.barra,
            self.chk_problemas,
            self.tabla,
        ):
            capa.addWidget(w)
        capa.addWidget(self._upid_titulo)
        capa.addLayout(fila_upid)
        capa.addWidget(self.detalles)
        capa.addWidget(self._titulo_rollback)
        capa.addWidget(self.tabla_rollback)
        capa.addLayout(botones)
        self.establecer_fase(FaseLote.TERMINADO)

    # --- Estado -----------------------------------------------------------------------

    def iniciar(self, plan: Plan) -> None:
        """Prepara la vista para un lote nuevo con todas las máquinas pendientes."""
        self.chk_problemas.setChecked(False)
        self._titulo_rollback.hide()
        self.tabla_rollback.hide()
        self.modelo_rollback.iniciar(())
        self.detalles.limpiar()
        self._upid.clear()
        for w in (self._upid_titulo, self._upid, self._copiar_upid):
            w.hide()
        self.mostrar_aviso(None)
        self.mostrar_error(None)
        self._total = len(plan.elementos)
        self.actualizar(tuple(EntradaLibro(e) for e in plan.elementos))
        self.establecer_fase(FaseLote.EJECUTANDO)

    def actualizar(self, entradas: Sequence[EntradaLibro]) -> None:
        """Refresca tabla y barra con una instantánea (como mucho 10 veces por segundo)."""
        self._entradas = tuple(entradas)
        self.modelo.establecer_entradas(self._entradas)
        self.filtro.refrescar()
        total = len(self._entradas)
        terminadas = sum(1 for e in self._entradas if e.estado not in ESTADOS_EN_CURSO)
        self.barra.setRange(0, max(total, 1))
        self.barra.setValue(terminadas)
        resumen = texto_barra(self._entradas)
        self.barra.setFormat(resumen)
        self.barra.setAccessibleDescription(resumen)

    @property
    def texto_resumen_barra(self) -> str:
        return self.barra.format()

    @property
    def fase(self) -> FaseLote:
        return self._fase

    @property
    def entradas(self) -> tuple[EntradaLibro, ...]:
        return self._entradas

    def mostrar_aviso(self, texto: str | None) -> None:
        poner_mensaje(self._aviso, texto, aviso=True)

    def mostrar_error(self, texto: str | None) -> None:
        poner_mensaje(self._error, texto)

    def establecer_fase(
        self,
        fase: FaseLote,
        *,
        dudosas: int = 0,
        elegibles: int = 0,
        reintentables: int = 0,
        con_ajustes: int = 0,
    ) -> None:
        """Muestra solo los botones que tienen sentido en la fase actual."""
        self._fase = fase
        self._titulo.setText(self._titulo_de_fase(fase))
        ejecutando = fase in (FaseLote.EJECUTANDO, FaseLote.CANCELANDO, FaseLote.PAUSADO)
        terminado = fase == FaseLote.TERMINADO
        self.boton_cancelar.setVisible(ejecutando or fase == FaseLote.DESHACIENDO)
        if fase == FaseLote.CANCELANDO:
            self.boton_cancelar.setText(
                QCoreApplication.translate("ProgresoLote", "Dejar de esperar")
            )
        elif fase == FaseLote.DESHACIENDO:
            self.boton_cancelar.setText(
                QCoreApplication.translate("ProgresoLote", "Detener lo que falta")
            )
        else:
            self.boton_cancelar.setText(QCoreApplication.translate("ProgresoLote", "Cancelar lote"))
        self.boton_decidir.setVisible(fase == FaseLote.PAUSADO)
        self.boton_comprobar.setVisible(terminado and dudosas > 0)
        if dudosas == 1:
            self.boton_comprobar.setText(
                QCoreApplication.translate("ProgresoLote", "Comprobar la dudosa")
            )
        else:
            self.boton_comprobar.setText(
                QCoreApplication.translate(
                    "ProgresoLote", "Comprobar las %n dudosas", None, dudosas
                )
            )
        self.boton_deshacer.setVisible(terminado)
        self.boton_deshacer.setEnabled(elegibles > 0)
        self.boton_reintentar.setVisible(terminado and reintentables > 0)
        self.boton_reintentar_ajustes.setVisible(terminado and con_ajustes > 0)
        self.boton_informe.setVisible(terminado or fase == FaseLote.DESHACIENDO)
        self.boton_informe.setEnabled(terminado)
        self.boton_volver.setVisible(terminado)
        self.chk_problemas.setEnabled(True)
        self._actualizar_comprobar_una()

    def _titulo_de_fase(self, fase: FaseLote) -> str:
        """Título según la fase: «Creando…» mientras trabaja y «Lote terminado» al acabar."""
        n = self._total
        if fase == FaseLote.TERMINADO:
            if n == 1:
                return QCoreApplication.translate("ProgresoLote", "Lote terminado (1 máquina)")
            return QCoreApplication.translate(
                "ProgresoLote", "Lote terminado (%n máquinas)", None, n
            )
        if fase == FaseLote.DESHACIENDO:
            return QCoreApplication.translate("ProgresoLote", "Deshaciendo el lote")
        if fase == FaseLote.COMPROBANDO:
            return QCoreApplication.translate("ProgresoLote", "Comprobando las máquinas dudosas")
        if n == 1:
            return QCoreApplication.translate("ProgresoLote", "Creando 1 máquina")
        return QCoreApplication.translate("ProgresoLote", "Creando %n máquinas", None, n)

    def _al_cancelar(self) -> None:
        if self._fase == FaseLote.CANCELANDO:
            self.dejar_de_esperar_solicitado.emit()
        else:
            self.cancelar_solicitado.emit()

    def vmids_con_ajustes_pendientes(self) -> tuple[int, ...]:
        """VMIDs de los clones creados a los que les falta algún ajuste (se pueden reintentar)."""
        return tuple(e.elemento.vmid for e in self._entradas if tiene_ajustes_pendientes(e))

    def hay_enviadas(self) -> bool:
        """``True`` si alguna máquina ya salió hacia Proxmox (pide confirmar la cancelación)."""
        return any(e.post_intentado for e in self._entradas)

    # --- Filtro y detalles -------------------------------------------------------------

    def _al_filtrar(self, activo: bool) -> None:
        self.filtro.establecer_solo_problemas(activo)

    def _entrada_seleccionada(self) -> EntradaLibro | None:
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return self.modelo.entrada(self.filtro.mapToSource(filas[0]).row())

    def _actualizar_comprobar_una(self) -> None:
        """«Comprobar ahora» se ofrece para la máquina dudosa elegida cuando el lote terminó."""
        entrada = self._entrada_seleccionada()
        self.boton_comprobar_una.setVisible(
            self._fase == FaseLote.TERMINADO
            and entrada is not None
            and entrada.estado in ESTADOS_DUDOSOS
        )

    def _al_comprobar_una(self) -> None:
        entrada = self._entrada_seleccionada()
        if entrada is not None:
            self.comprobar_una_solicitado.emit(entrada.elemento.vmid)

    def _al_seleccionar(self, _nueva: QItemSelection, _vieja: QItemSelection) -> None:
        entrada = self._entrada_seleccionada()
        self._actualizar_comprobar_una()
        visible = entrada is not None and bool(entrada.upid)
        for w in (self._upid_titulo, self._upid, self._copiar_upid):
            w.setVisible(visible)
        self._upid.setText(entrada.upid or "" if entrada else "")
        if entrada is None:
            self.detalles.limpiar()
        else:
            self.detalles.establecer(texto_detalles_entrada(entrada))

    # --- Deshacer ---------------------------------------------------------------------

    def iniciar_rollback(self, previstas: Iterable[tuple[str, int, str]]) -> None:
        self.modelo_rollback.iniciar(previstas)
        self._titulo_rollback.show()
        self.tabla_rollback.show()

    def actualizar_rollback(self, resultados: Iterable[ResultadoRollback]) -> None:
        self.modelo_rollback.registrar_todos(resultados)

    def establecer_tema(self, tema: str) -> None:
        self.modelo.establecer_tema(tema)
        self.modelo_rollback.establecer_tema(tema)
