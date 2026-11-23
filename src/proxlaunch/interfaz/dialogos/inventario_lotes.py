"""Diálogo «Lotes en el servidor» (fase C, C1): encontrar, exportar y deshacer lotes.

Lista los lotes que ProxLaunch etiquetó en el servidor aunque se creasen en otra sesión. Toda
lectura va en un trabajador (``Lanzador``); el hilo de la interfaz nunca toca la red. Abrir,
elegir, «Comprobar», exportar y «Obtener IP» solo hacen GET. La única escritura es el Deshacer
con doble control (RF-C1.8): las etiquetas y la nota del lote, y además escribir su código.

Flujo de Deshacer: lista desmarcable -> inspección (solo lectura) -> confirmación expresa de la
fase A si hay máquinas encendidas o protegidas -> confirmación escribiendo el código -> borrado
(releyendo cada config justo antes, en el núcleo) -> resultado por máquina.
"""

from __future__ import annotations

import dataclasses
import html
import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.archivos_ui import TipoArchivo, elegir_para_guardar
from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.dialogos.confirmar_deshacer import (
    DialogoConfirmarDeshacerForzado,
    EleccionDeshacer,
)
from proxlaunch.interfaz.modelos_tabla import ModeloRollback, TablaCopiable
from proxlaunch.interfaz.textos import texto_error
from proxlaunch.interfaz.textos_inventario import (
    cabeceras_detalle,
    cabeceras_lotes,
    texto_aviso_borrado,
    texto_aviso_lote,
    texto_bloqueo,
    texto_borrando,
    texto_boton,
    texto_buscar_lote,
    texto_casilla_ip_csv,
    texto_casilla_todos_los_lotes,
    texto_cierre_con_borrado,
    texto_comprobando_para_borrar,
    texto_csv_guardado,
    texto_demasiadas_marcadas,
    texto_detalle_incompleto,
    texto_elige_un_lote,
    texto_estado_maquina,
    texto_fecha_lote,
    texto_intro_inventario,
    texto_ip,
    texto_ip_obtenida,
    texto_ip_sin_permiso,
    texto_ip_sin_version,
    texto_lectura_cancelada,
    texto_leyendo_detalle,
    texto_leyendo_lotes,
    texto_limitacion_inventario,
    texto_lote_abierto_en_sesion,
    texto_lotes_leidos,
    texto_motivos_mv,
    texto_ninguna_deshacible,
    texto_nota_origen,
    texto_pedir_codigo,
    texto_resumen_resultado,
    texto_seleccion_vacia,
    texto_si_no,
    texto_sin_leer,
    texto_sin_lotes_de_proxlaunch,
    texto_sin_lotes_visibles,
    texto_sin_nombre,
    texto_sin_resultados_busqueda,
    titulo_confirmar_codigo,
    titulo_inventario,
    titulo_resultado,
)
from proxlaunch.interfaz.trabajadores import (
    Lanzador,
    PuenteRollback,
    Trabajador,
    deshacer_inventario,
    detallar_lote_servidor,
    exportar_inventario_csv,
    inspeccionar_inventario,
    leer_lotes_servidor,
    obtener_ips_inventario,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.inventario.agrupacion import filtrar_lotes
from proxlaunch.nucleo.inventario.modelos import (
    DetalleLote,
    IpInventario,
    ListaLotes,
    LoteServidor,
    MotivoNoDeshacible,
    MVInventario,
)
from proxlaunch.nucleo.inventario.propiedad import codigo_confirmado, problema_seleccion
from proxlaunch.nucleo.lote.modelos import EstadoRollback, ResultadoRollback
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import InspeccionRollback
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion

_log = logging.getLogger("proxlaunch.interfaz.inventario_lotes")

_ROL_CODIGO = Qt.ItemDataRole.UserRole


def _tooltip_plano(texto: str) -> str:
    """Tooltip que Qt muestra como texto literal aunque el dato del servidor traiga ``<``/``&``
    (SEG-C-M1): se escapa y se marca como rich text para que no se interprete como HTML."""
    if not texto:
        return ""
    return f"<p style='white-space:pre-wrap'>{html.escape(texto)}</p>"


_COL_NOMBRE = 0
_COL_IP = 8
_COL_MOTIVO = 9
_INTERVALO_PROGRESO_MS = 250


class DialogoConfirmarCodigoLote(QDialog):
    """Última confirmación del borrado: hay que escribir el código del lote (V-C06).

    «Borrar definitivamente» está deshabilitado hasta que el texto coincide (sin distinguir
    mayúsculas ni espacios en los extremos). «Cancelar» es el botón predeterminado.
    """

    def __init__(self, codigo: str, cantidad: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._codigo = codigo
        self.setWindowTitle(titulo_confirmar_codigo())
        self.setModal(True)
        self.setMinimumWidth(480)
        self.aviso = QLabel(texto_aviso_borrado(cantidad, codigo))
        self.aviso.setWordWrap(True)
        self.aviso.setTextFormat(Qt.TextFormat.PlainText)
        self.aviso.setProperty("error", True)
        self.pista = QLabel(texto_pedir_codigo(codigo))
        self.pista.setWordWrap(True)
        self.pista.setTextFormat(Qt.TextFormat.PlainText)
        self.campo = QLineEdit()
        self.campo.setAccessibleName(
            QCoreApplication.translate("DialogoConfirmarCodigoLote", "Código del lote")
        )
        self.boton_borrar = QPushButton(texto_boton("borrar"))
        self.boton_cancelar = QPushButton(texto_boton("cancelar"))
        self.boton_borrar.setAutoDefault(False)
        self.boton_borrar.setEnabled(False)
        self.campo.textChanged.connect(self._al_escribir)
        self.boton_borrar.clicked.connect(self.accept)
        self.boton_cancelar.clicked.connect(self.reject)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self.boton_borrar)
        fila.addWidget(self.boton_cancelar)
        capa = QVBoxLayout(self)
        capa.addWidget(self.aviso)
        capa.addWidget(self.pista)
        capa.addWidget(self.campo)
        capa.addLayout(fila)
        # Acción destructiva: Intro y Esc son de «Cancelar».
        self.boton_cancelar.setDefault(True)
        self.boton_cancelar.setFocus()

    def _al_escribir(self, texto: str) -> None:
        self.boton_borrar.setEnabled(codigo_confirmado(texto, self._codigo))

    def accept(self) -> None:
        # Doble guarda: ni Intro ni una señal mal conectada borran sin el código escrito.
        if codigo_confirmado(self.campo.text(), self._codigo):
            super().accept()


class DialogoInventarioLotes(QDialog):
    """«Lotes en el servidor»: lista, detalle, exportación, IP y Deshacer con doble control.

    ``lotes_de_sesion`` devuelve los códigos de los lotes abiertos en esta sesión (V-C07): su
    «Deshacer…» queda deshabilitado aquí. ``estado_ip`` es la disponibilidad de la IP del
    inventario (privilegio del agente según la versión); ``None`` = sin información.
    """

    deshacer_empezado = Signal(str)  # código del lote (DT-C16): «Lote > Deshacer» lo bloquea
    deshacer_terminado = Signal(str)
    sesion_expirada = Signal(object)  # ErrorProxLaunch: la ventana pide reconectar

    def __init__(
        self,
        *,
        sesion: Sesion,
        reloj: Reloj,
        lanzador: Lanzador,
        permisos: PermisosEfectivos | None,
        lotes_de_sesion: Callable[[], frozenset[str]],
        estado_ip: EstadoOpcion | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sesion = sesion
        self._reloj = reloj
        self._lanzador = lanzador
        self._permisos = permisos
        self._lotes_de_sesion = lotes_de_sesion
        self._estado_ip = estado_ip
        # Estado de lo leído.
        self._lista: ListaLotes | None = None
        self._detalles: dict[str, DetalleLote] = {}
        self._previos: dict[str, DetalleLote] = {}
        self._marcas: dict[str, set[int]] = {}
        self._vistas: dict[str, set[int]] = {}
        self._deshacibles_vistas: dict[str, set[int]] = {}
        self._ips: dict[int, IpInventario] = {}
        self._codigo: str | None = None
        # Control de trabajos y cierre.
        self._gen = 0  # sube al cancelar o cerrar: los resultados viejos se descartan
        self._token_detalle = 0
        self._activos: list[Trabajador] = []
        self._trabajador_detalle: Trabajador | None = None
        self._ocupado = False  # lista, IP, exportación o inspección en curso
        self._leyendo_detalle = False
        self._deshaciendo = False
        self._codigo_borrando: str | None = None
        self._cerrado = False
        self._forzar_cierre = False
        self._poblando = False
        self._control: ControlLote | None = None
        self._puente: PuenteRollback | None = None
        self._modelo_resultado = ModeloRollback(self)
        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVALO_PROGRESO_MS)
        self._timer.timeout.connect(self._refrescar_progreso)

        self.setWindowTitle(titulo_inventario())
        self.setModal(False)
        self.resize(980, 640)
        self._construir()
        self._refrescar_botones()

    # ------------------------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------------------------

    def _construir(self) -> None:
        intro = QLabel(texto_intro_inventario())
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.PlainText)
        # Visible sin pasar el ratón (CA-C1.9.3).
        self.texto_limitacion = QLabel(texto_limitacion_inventario())
        self.texto_limitacion.setWordWrap(True)
        self.texto_limitacion.setTextFormat(Qt.TextFormat.PlainText)
        self.texto_limitacion.setProperty("secundario", True)

        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText(texto_buscar_lote())
        self.busqueda.setAccessibleName(texto_buscar_lote())
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.textChanged.connect(self._al_buscar)
        self.boton_comprobar = QPushButton(texto_boton("comprobar"))
        self.boton_comprobar.clicked.connect(self.comprobar)
        self.boton_cancelar_lectura = QPushButton(texto_boton("cancelar_lectura"))
        self.boton_cancelar_lectura.clicked.connect(self.cancelar_lectura)
        fila_busqueda = QHBoxLayout()
        fila_busqueda.addWidget(self.busqueda, 1)
        fila_busqueda.addWidget(self.boton_comprobar)
        fila_busqueda.addWidget(self.boton_cancelar_lectura)

        self.estado = QLabel()
        self.estado.setWordWrap(True)
        self.estado.setTextFormat(Qt.TextFormat.PlainText)

        self.tabla_lotes = QTableWidget(0, len(cabeceras_lotes()))
        self.tabla_lotes.setAccessibleName(
            QCoreApplication.translate("DialogoInventarioLotes", "Lotes del servidor")
        )
        self.tabla_lotes.setHorizontalHeaderLabels(list(cabeceras_lotes()))
        self.tabla_lotes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_lotes.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_lotes.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_lotes.verticalHeader().setVisible(False)
        # Las columnas se ajustan al contenido y a la cabecera, para que no se corten la fecha
        # ni «Se pueden deshacer»; la última ocupa el sitio que sobre.
        cab_lotes = self.tabla_lotes.horizontalHeader()
        cab_lotes.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cab_lotes.setStretchLastSection(True)
        self.tabla_lotes.setMaximumHeight(170)
        self.tabla_lotes.itemSelectionChanged.connect(self._al_elegir_lote)

        self.tabla_detalle = QTableWidget(0, len(cabeceras_detalle()))
        self.tabla_detalle.setAccessibleName(
            QCoreApplication.translate("DialogoInventarioLotes", "Máquinas del lote")
        )
        self.tabla_detalle.setHorizontalHeaderLabels(list(cabeceras_detalle()))
        self.tabla_detalle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_detalle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_detalle.verticalHeader().setVisible(False)
        cab = self.tabla_detalle.horizontalHeader()
        cab.setStretchLastSection(True)
        cab.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(_COL_MOTIVO, QHeaderView.ResizeMode.Stretch)
        self.tabla_detalle.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tabla_detalle.setMinimumHeight(180)
        self.tabla_detalle.itemChanged.connect(self._al_marcar)

        self.motivo_deshacer = QLabel()
        self.motivo_deshacer.setWordWrap(True)
        self.motivo_deshacer.setTextFormat(Qt.TextFormat.PlainText)
        self.motivo_deshacer.setProperty("secundario", True)

        self.chk_ip = QCheckBox(texto_casilla_ip_csv())
        self.chk_todos = QCheckBox(texto_casilla_todos_los_lotes())
        self.boton_ip = QPushButton(texto_boton("obtener_ip"))
        self.boton_exportar = QPushButton(texto_boton("exportar"))
        self.boton_deshacer = QPushButton(texto_boton("deshacer"))
        self.boton_cerrar = QPushButton(texto_boton("cerrar"))
        self.boton_ip.clicked.connect(self.obtener_ip)
        self.boton_exportar.clicked.connect(self.exportar)
        self.boton_deshacer.clicked.connect(self.deshacer)
        self.boton_cerrar.clicked.connect(self.reject)
        self.boton_deshacer.setAutoDefault(False)
        self.boton_cerrar.setAutoDefault(False)

        # Resultado del borrado (oculto hasta el primer Deshacer).
        self.titulo_resultado = QLabel(titulo_resultado())
        fuente = self.titulo_resultado.font()
        fuente.setBold(True)
        self.titulo_resultado.setFont(fuente)
        self.resumen_resultado = QLabel()
        self.resumen_resultado.setWordWrap(True)
        self.resumen_resultado.setTextFormat(Qt.TextFormat.PlainText)
        self.tabla_resultado = TablaCopiable(
            QCoreApplication.translate("DialogoInventarioLotes", "Resultado del borrado")
        )
        self.tabla_resultado.setModel(self._modelo_resultado)
        self.tabla_resultado.setMaximumHeight(170)
        self.boton_detener = QPushButton(texto_boton("cancelar_deshacer"))
        self.boton_detener.clicked.connect(self.detener_borrado)
        self._bloque_resultado = QWidget()
        capa_res = QVBoxLayout(self._bloque_resultado)
        capa_res.setContentsMargins(0, 0, 0, 0)
        capa_res.addWidget(self.titulo_resultado)
        capa_res.addWidget(self.resumen_resultado)
        capa_res.addWidget(self.tabla_resultado)
        capa_res.addWidget(self.boton_detener, 0, Qt.AlignmentFlag.AlignRight)
        self._bloque_resultado.setVisible(False)

        fila_acciones = QHBoxLayout()
        fila_acciones.addWidget(self.chk_ip)
        fila_acciones.addWidget(self.chk_todos)
        fila_acciones.addStretch(1)
        fila_acciones.addWidget(self.boton_ip)
        fila_acciones.addWidget(self.boton_exportar)
        fila_acciones.addWidget(self.boton_deshacer)
        fila_acciones.addWidget(self.boton_cerrar)

        capa, capa_pie, _ = hacer_desplazable(self)
        capa.addWidget(intro)
        capa.addWidget(self.texto_limitacion)
        capa.addLayout(fila_busqueda)
        capa.addWidget(self.estado)
        capa.addWidget(self.tabla_lotes)
        capa.addWidget(self.tabla_detalle, 1)
        capa.addWidget(self.motivo_deshacer)
        capa.addWidget(self._bloque_resultado)
        capa_pie.addLayout(fila_acciones)

    # ------------------------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------------------------

    def iniciar(self) -> None:
        """Primera lectura de la lista (una sola petición, en un trabajador)."""
        self._leer_lista(None)

    @property
    def hay_trabajo(self) -> bool:
        """Hay un borrado en curso (la ventana no destruye el diálogo hasta que termine)."""
        return self._deshaciendo

    @property
    def codigo_seleccionado(self) -> str | None:
        return self._codigo

    def comprobar(self) -> None:
        """Relee la lista y el detalle del lote elegido (RF-C1.5); solo lectura."""
        if self._cerrado or self._ocupado or self._deshaciendo:
            return
        self._previos = dict(self._detalles)
        self._detalles.clear()
        self._leer_lista(self._codigo)

    def cancelar_lectura(self) -> None:
        """Corta las lecturas en curso; sus resultados tardíos se descartan."""
        if self._deshaciendo:
            return
        self._cancelar_trabajos()
        self._ocupado = False
        self._leyendo_detalle = False
        self._previos.clear()
        self._poner_estado(texto_lectura_cancelada(), aviso=True)
        self._refrescar_botones()

    def cerrar_por_cambio_de_servidor(self) -> None:
        """El perfil de conexión cambió: nada de este diálogo se ejecuta contra el servidor nuevo
        (CA-C1.14.1). Se corta todo, también un borrado en curso, y se cierra."""
        self.cancelar_borrado()
        self._forzar_cierre = True
        self.reject()

    def cancelar_borrado(self) -> None:
        """Detiene el borrado en curso (no se envían más ``DELETE``) y las lecturas."""
        self._cancelar_trabajos()
        control = self._control
        if control is not None:
            control.cancelar()
            control.dejar_de_esperar()

    def detener_borrado(self) -> None:
        """«Detener el borrado»: no se envía ninguna eliminación más (las enviadas siguen)."""
        control = self._control
        if control is not None:
            control.cancelar()
        self.boton_detener.setEnabled(False)

    def reject(self) -> None:
        if self._deshaciendo and not self._forzar_cierre:
            self._poner_estado(texto_cierre_con_borrado(), aviso=True)
            return
        self._cerrado = True
        self._timer.stop()
        self._cancelar_trabajos()
        super().reject()

    # ------------------------------------------------------------------------------------
    # Lectura de la lista y del detalle
    # ------------------------------------------------------------------------------------

    def _lanzar(
        self,
        funcion: Callable[..., Any],
        *args: Any,
        al_terminar: Callable[[Any], None],
        al_fallar: Callable[[ErrorProxLaunch], None],
        con_contexto: bool = False,
    ) -> Trabajador:
        propio: list[Trabajador] = []

        def terminar(resultado: Any) -> None:
            self._soltar(propio)
            al_terminar(resultado)

        def fallar(error: ErrorProxLaunch) -> None:
            self._soltar(propio)
            al_fallar(error)

        trabajador = self._lanzador.lanzar(
            funcion,
            *args,
            al_terminar=terminar,
            al_fallar=fallar,
            con_contexto=con_contexto,
        )
        propio.append(trabajador)
        self._activos.append(trabajador)
        return trabajador

    def _soltar(self, propio: list[Trabajador]) -> None:
        """Poda de ``_activos`` el trabajador que ya terminó (no crece sin límite)."""
        for trabajador in propio:
            if trabajador in self._activos:
                self._activos.remove(trabajador)

    def _cancelar_detalle(self) -> None:
        """Cancela el trabajador de la lectura de detalle anterior, si sigue en curso."""
        anterior = self._trabajador_detalle
        self._trabajador_detalle = None
        if anterior is not None:
            anterior.cancelar()
            if anterior in self._activos:
                self._activos.remove(anterior)

    def _cancelar_trabajos(self) -> None:
        self._gen += 1
        self._trabajador_detalle = None
        for trabajador in self._activos:
            trabajador.cancelar()
        self._activos.clear()

    def _leer_lista(self, reabrir: str | None) -> None:
        self._ocupado = True
        self._poner_estado(texto_leyendo_lotes())
        self._refrescar_botones()
        gen = self._gen
        self._lanzar(
            leer_lotes_servidor,
            self._sesion,
            self._reloj,
            al_terminar=lambda lista: self._tras_lista(gen, lista, reabrir),
            al_fallar=lambda e: self._fallo(gen, e),
        )

    def _tras_lista(self, gen: int, lista: ListaLotes, reabrir: str | None) -> None:
        if self._cerrado or gen != self._gen:
            return
        self._ocupado = False
        self._lista = lista
        # Un lote que ya no está en la lista se olvida con su caché.
        presentes = {lote.codigo for lote in lista.lotes}
        for codigo in [c for c in self._detalles if c not in presentes]:
            del self._detalles[codigo]
        self._pintar_lotes()
        if lista.total_visibles == 0:
            self._poner_estado(texto_sin_lotes_visibles(), aviso=True)  # V-C01
        elif not lista.lotes:
            self._poner_estado(texto_sin_lotes_de_proxlaunch(lista.total_visibles), aviso=True)
        else:
            self._poner_estado(texto_lotes_leidos(len(lista.lotes)))
        if reabrir is not None and reabrir in presentes:
            self._seleccionar_fila(reabrir)
            self._leer_detalle(reabrir)
        else:
            self._codigo = None
            self._pintar_detalle()
        self._refrescar_botones()

    def _leer_detalle(self, codigo: str) -> None:
        """Lee las máquinas del lote (o usa la caché: no se repiten lecturas hasta «Comprobar»)."""
        lote = self._lote(codigo)
        if lote is None:
            return
        # Cambiar de lote corta la lectura del anterior (y cancela su trabajador).
        self._token_detalle += 1
        self._cancelar_detalle()
        if codigo in self._detalles:
            self._leyendo_detalle = False
            self._pintar_detalle()
            self._refrescar_botones()
            return
        self._leyendo_detalle = True
        self._pintar_detalle()
        self._poner_estado(texto_leyendo_detalle(codigo))
        self._refrescar_botones()
        gen, token = self._gen, self._token_detalle
        self._trabajador_detalle = self._lanzar(
            detallar_lote_servidor,
            self._sesion,
            self._reloj,
            lote,
            self._permisos,
            con_contexto=True,
            al_terminar=lambda d: self._tras_detalle(gen, token, d),
            al_fallar=lambda e: self._fallo(gen, e, token),
        )

    def _tras_detalle(self, gen: int, token: int, detalle: DetalleLote) -> None:
        if self._cerrado or gen != self._gen or token != self._token_detalle:
            return
        self._leyendo_detalle = False
        codigo = detalle.lote.codigo
        if not detalle.completo:
            self._previos.pop(codigo, None)
            self._poner_estado(texto_lectura_cancelada(), aviso=True)
            self._refrescar_botones()
            return
        self._guardar_detalle(self._fusionar(detalle))
        if self._codigo == codigo:
            self._pintar_detalle()
            self._poner_estado(texto_lotes_leidos(len(self._lista.lotes)) if self._lista else "")
        self._pintar_lotes()
        self._refrescar_botones()

    def _fusionar(self, detalle: DetalleLote) -> DetalleLote:
        """Las máquinas del lote que ya no aparecen se conservan como «ya no existe» (CA-C1.5.1)."""
        previo = self._previos.pop(detalle.lote.codigo, None)
        if previo is None:
            return detalle
        actuales = {mv.recurso.vmid for mv in detalle.maquinas}
        desaparecidas = tuple(
            MVInventario(mv.recurso, None, None, (MotivoNoDeshacible.YA_NO_EXISTE,))
            for mv in previo.maquinas
            if mv.recurso.vmid not in actuales
        )
        if not desaparecidas:
            return detalle
        return dataclasses.replace(detalle, maquinas=(*detalle.maquinas, *desaparecidas))

    def _guardar_detalle(self, detalle: DetalleLote) -> None:
        """Guarda el detalle y decide qué máquinas quedan marcadas (CA-C1.5.3).

        La primera lectura marca todas las deshacibles. Al releer se conserva lo que el usuario
        desmarcó, las máquinas nuevas quedan desmarcadas y las que dejaron de existir, también.
        """
        codigo = detalle.lote.codigo
        self._detalles[codigo] = detalle
        deshacibles = {mv.recurso.vmid for mv in detalle.maquinas if mv.deshacible}
        todas = {mv.recurso.vmid for mv in detalle.maquinas}
        if codigo not in self._vistas:
            marcas = set(deshacibles)
        else:
            marcas_previas = self._marcas.get(codigo, set())
            antes_deshacibles = self._deshacibles_vistas.get(codigo, set())
            vistas = self._vistas[codigo]
            marcas = set()
            for vmid in deshacibles:
                if vmid in antes_deshacibles:
                    if vmid in marcas_previas:
                        marcas.add(vmid)
                elif vmid in vistas:
                    marcas.add(vmid)  # estaba sin estado conocido y ya se puede deshacer
                # Nueva en el servidor: queda desmarcada.
        self._marcas[codigo] = marcas
        self._vistas[codigo] = todas
        self._deshacibles_vistas[codigo] = deshacibles

    # ------------------------------------------------------------------------------------
    # Pintado
    # ------------------------------------------------------------------------------------

    def _lote(self, codigo: str) -> LoteServidor | None:
        if self._lista is None:
            return None
        return next((x for x in self._lista.lotes if x.codigo == codigo), None)

    def _poner_estado(self, texto: str, *, aviso: bool = False) -> None:
        self.estado.setText(texto)
        self.estado.setProperty("aviso", aviso)
        self.estado.style().unpolish(self.estado)
        self.estado.style().polish(self.estado)

    def _fecha_texto(self, detalle: DetalleLote | None) -> str:
        if detalle is None:
            return texto_sin_leer()
        fecha: datetime | None = detalle.fecha
        return texto_fecha_lote(fecha.astimezone().strftime("%Y-%m-%d %H:%M") if fecha else None)

    def _pintar_lotes(self) -> None:
        lista = self._lista
        seleccion = self._codigo
        sesion = self._lotes_de_sesion()
        lotes = filtrar_lotes(lista.lotes, self.busqueda.text()) if lista is not None else ()
        self.tabla_lotes.blockSignals(True)
        try:
            self.tabla_lotes.setRowCount(len(lotes))
            for fila, lote in enumerate(lotes):
                detalle = self._detalles.get(lote.codigo)
                deshacibles = (
                    str(sum(1 for mv in detalle.maquinas if mv.deshacible))
                    if detalle is not None
                    else texto_sin_leer()
                )
                celdas = (
                    lote.codigo,
                    str(len(lote.recursos)),
                    deshacibles,
                    self._fecha_texto(detalle),
                    texto_aviso_lote(lote, lote.codigo in sesion),
                )
                for col, texto in enumerate(celdas):
                    item = QTableWidgetItem(texto)
                    item.setData(_ROL_CODIGO, lote.codigo)
                    item.setToolTip(_tooltip_plano(texto))
                    self.tabla_lotes.setItem(fila, col, item)
                if lote.codigo == seleccion:
                    self.tabla_lotes.selectRow(fila)
        finally:
            self.tabla_lotes.blockSignals(False)
        if lista is not None and lista.lotes and not lotes:
            self._poner_estado(texto_sin_resultados_busqueda(), aviso=True)

    def _seleccionar_fila(self, codigo: str) -> None:
        self._codigo = codigo
        self._pintar_lotes()

    def _pintar_detalle(self) -> None:
        codigo = self._codigo
        detalle = self._detalles.get(codigo) if codigo is not None else None
        self._poblando = True
        self.tabla_detalle.blockSignals(True)
        try:
            self.tabla_detalle.setRowCount(0)
            if detalle is None:
                if codigo is None:
                    self.motivo_deshacer.setText(texto_elige_un_lote())
                return
            marcas = self._marcas.get(detalle.lote.codigo, set())
            self.tabla_detalle.setRowCount(len(detalle.maquinas))
            for fila, mv in enumerate(detalle.maquinas):
                self._poner_fila(fila, mv, detalle.lote.codigo, mv.recurso.vmid in marcas)
        finally:
            self.tabla_detalle.blockSignals(False)
            self._poblando = False

    def _poner_fila(self, fila: int, mv: MVInventario, codigo: str, marcada: bool) -> None:
        r = mv.recurso
        motivo = texto_motivos_mv(mv, codigo)
        celdas = (
            r.nombre or texto_sin_nombre(),
            str(r.vmid),
            r.nodo or "",
            texto_estado_maquina(r.estado),
            texto_bloqueo(r.bloqueo),
            texto_si_no(r.plantilla),
            texto_si_no(mv.protegida),
            texto_nota_origen(mv),
            texto_ip(self._ips.get(r.vmid)),
            motivo,
        )
        for col, texto in enumerate(celdas):
            item = QTableWidgetItem(texto)
            item.setToolTip(_tooltip_plano(texto))
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if col == _COL_NOMBRE:
                if mv.deshacible:
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                    item.setCheckState(
                        Qt.CheckState.Checked if marcada else Qt.CheckState.Unchecked
                    )
                item.setData(_ROL_CODIGO, r.vmid)
            item.setFlags(flags)
            self.tabla_detalle.setItem(fila, col, item)

    def _refrescar_columna_ip(self) -> None:
        detalle = self._detalle_actual()
        if detalle is None:
            return
        for fila, mv in enumerate(detalle.maquinas):
            item = self.tabla_detalle.item(fila, _COL_IP)
            if item is not None:
                texto = texto_ip(self._ips.get(mv.recurso.vmid))
                item.setText(texto)
                item.setToolTip(_tooltip_plano(texto))

    # ------------------------------------------------------------------------------------
    # Selección y marcas
    # ------------------------------------------------------------------------------------

    def _al_buscar(self, _texto: str) -> None:
        self._pintar_lotes()

    def _al_elegir_lote(self) -> None:
        if self._cerrado or self._ocupado or self._deshaciendo:
            return
        filas = self.tabla_lotes.selectionModel().selectedRows()
        if not filas:
            return
        item = self.tabla_lotes.item(filas[0].row(), 0)
        if item is None:
            return
        codigo = str(item.data(_ROL_CODIGO))
        if codigo == self._codigo:
            return
        self._codigo = codigo
        self._leer_detalle(codigo)

    def _al_marcar(self, item: QTableWidgetItem) -> None:
        if self._poblando or item.column() != _COL_NOMBRE:
            return
        codigo = self._codigo
        if codigo is None:
            return
        vmid = item.data(_ROL_CODIGO)
        marcas = self._marcas.setdefault(codigo, set())
        if item.checkState() == Qt.CheckState.Checked:
            marcas.add(int(vmid))
        else:
            marcas.discard(int(vmid))
        self._refrescar_botones()

    def _detalle_actual(self) -> DetalleLote | None:
        return self._detalles.get(self._codigo) if self._codigo is not None else None

    def marcadas(self) -> frozenset[int]:
        """VMIDs marcadas del lote elegido (solo pueden estarlo las deshacibles)."""
        detalle = self._detalle_actual()
        if detalle is None:
            return frozenset()
        validas = {mv.recurso.vmid for mv in detalle.maquinas if mv.deshacible}
        return frozenset(self._marcas.get(detalle.lote.codigo, set()) & validas)

    # ------------------------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------------------------

    def _motivo_sin_deshacer(self) -> str | None:
        """Por qué «Deshacer…» no se puede usar ahora (``None`` si se puede)."""
        detalle = self._detalle_actual()
        if detalle is None or self._ocupado or self._leyendo_detalle or self._deshaciendo:
            return None if detalle is not None else texto_elige_un_lote()
        if not detalle.completo:
            return texto_detalle_incompleto()
        if detalle.lote.codigo in self._lotes_de_sesion():
            return texto_lote_abierto_en_sesion()  # V-C07
        if not any(mv.deshacible for mv in detalle.maquinas):
            return texto_ninguna_deshacible()
        problema = problema_seleccion(len(self.marcadas()))
        if problema == "V-C09":
            return texto_demasiadas_marcadas()
        if problema == "vacia":
            return texto_seleccion_vacia()
        return None

    def _motivo_ip(self) -> str | None:
        """Por qué la IP no está disponible (privilegio o versión); ``None`` si lo está."""
        estado = self._estado_ip
        if estado is None or estado.disponibilidad != Disponibilidad.NO:
            return None
        if estado.codigo == CodigoError.OPCION_SIN_VERSION:
            return texto_ip_sin_version(estado.params.get("version", ""))
        return texto_ip_sin_permiso(estado.params.get("privilegio", ""))

    def _refrescar_botones(self) -> None:
        ocupado = self._ocupado or self._deshaciendo
        detalle = self._detalle_actual()
        hay_detalle = detalle is not None and not self._leyendo_detalle
        self.boton_comprobar.setEnabled(not ocupado and not self._leyendo_detalle)
        self.boton_cancelar_lectura.setVisible(
            (self._ocupado or self._leyendo_detalle) and not self._deshaciendo
        )
        self.tabla_lotes.setEnabled(not ocupado)
        self.busqueda.setEnabled(not ocupado)
        self.tabla_detalle.setEnabled(not self._deshaciendo)
        # Exportar.
        puede_exportar = not ocupado and (
            (self.chk_todos.isChecked() and self._lista is not None and bool(self._lista.lotes))
            or hay_detalle
        )
        self.boton_exportar.setEnabled(puede_exportar)
        self.chk_todos.setEnabled(not ocupado)
        # IP.
        motivo_ip = self._motivo_ip()
        self.boton_ip.setEnabled(not ocupado and hay_detalle and motivo_ip is None)
        self.chk_ip.setEnabled(not ocupado and motivo_ip is None)
        if motivo_ip is not None:
            self.chk_ip.setChecked(False)
        for control in (self.boton_ip, self.chk_ip):
            control.setToolTip(motivo_ip or "")
        # Deshacer.
        motivo = self._motivo_sin_deshacer()
        self.boton_deshacer.setEnabled(not ocupado and hay_detalle and motivo is None)
        self.boton_deshacer.setToolTip(motivo or "")
        if self._leyendo_detalle or ocupado:
            self.motivo_deshacer.setText("")
        else:
            self.motivo_deshacer.setText(motivo or "")
        self.boton_cerrar.setEnabled(not self._deshaciendo)

    # ------------------------------------------------------------------------------------
    # Exportar e IP (solo lectura)
    # ------------------------------------------------------------------------------------

    def _elegir_ruta_csv(self, sugerido: str) -> Path | None:
        """Selector de archivos estándar (se sobrescribe en las pruebas)."""
        return elegir_para_guardar(self, TipoArchivo.CSV, sugerido)

    def exportar(self) -> None:
        if self._cerrado or self._ocupado or self._deshaciendo or self._lista is None:
            return
        todos = self.chk_todos.isChecked()
        if todos:
            detalles = [self._detalles[c] for c in sorted(self._detalles)]
            pendientes = [x for x in self._lista.lotes if x.codigo not in self._detalles]
            sugerido = "lotes-servidor.csv"
        else:
            actual = self._detalle_actual()
            if actual is None:
                return
            detalles, pendientes = [actual], []
            sugerido = f"lote-{actual.lote.codigo}.csv"
        ruta = self._elegir_ruta_csv(sugerido)
        if ruta is None:
            return  # no se crea nada sin elegir ruta (CA-C1.6.4)
        con_ip = self.chk_ip.isChecked() and self._motivo_ip() is None
        self._ocupado = True
        self._poner_estado(texto_leyendo_lotes())
        self._refrescar_botones()
        gen = self._gen
        self._lanzar(
            exportar_inventario_csv,
            self._sesion,
            self._reloj,
            ruta,
            detalles,
            pendientes,
            dict(self._ips),
            con_ip,
            self._permisos,
            con_contexto=True,
            al_terminar=lambda r: self._tras_exportar(gen, r),
            al_fallar=lambda e: self._fallo(gen, e),
        )

    def _tras_exportar(
        self, gen: int, resultado: tuple[Path | None, list[DetalleLote], dict[int, IpInventario]]
    ) -> None:
        if self._cerrado or gen != self._gen:
            return
        ruta, detalles, ips = resultado
        self._ocupado = False
        for detalle in detalles:
            if detalle.completo and detalle.lote.codigo not in self._detalles:
                self._previos.pop(detalle.lote.codigo, None)
                self._guardar_detalle(detalle)
        self._ips.update(ips)
        self._pintar_lotes()
        self._pintar_detalle()
        if ruta is None:
            self._poner_estado(texto_lectura_cancelada(), aviso=True)
        else:
            self._poner_estado(texto_csv_guardado(ruta.name))
        self._refrescar_botones()

    def obtener_ip(self) -> None:
        detalle = self._detalle_actual()
        if (
            detalle is None
            or self._cerrado
            or self._ocupado
            or self._deshaciendo
            or self._motivo_ip() is not None
        ):
            return
        self._ocupado = True
        self._poner_estado(texto_leyendo_detalle(detalle.lote.codigo))
        self._refrescar_botones()
        gen = self._gen
        vmids = [mv.recurso.vmid for mv in detalle.maquinas]
        self._lanzar(
            obtener_ips_inventario,
            self._sesion,
            self._reloj,
            detalle,
            vmids,
            self._permisos,
            con_contexto=True,
            al_terminar=lambda ips: self._tras_ips(gen, ips),
            al_fallar=lambda e: self._fallo(gen, e),
        )

    def _tras_ips(self, gen: int, ips: dict[int, IpInventario]) -> None:
        if self._cerrado or gen != self._gen:
            return
        self._ocupado = False
        self._ips.update(ips)
        self._refrescar_columna_ip()
        self._poner_estado(texto_ip_obtenida(len(ips)))
        self._refrescar_botones()

    def _fallo(self, gen: int, error: ErrorProxLaunch, token: int | None = None) -> None:
        if self._cerrado or gen != self._gen:
            return
        if token is not None:
            # Fallo de una lectura de detalle: si ya se cambió de lote es obsoleto y no toca
            # el estado de otra operación en curso.
            if token != self._token_detalle:
                return
            self._leyendo_detalle = False
        else:
            self._ocupado = False
        self._previos.clear()
        self._poner_estado(texto_error(error), aviso=True)
        self._refrescar_botones()
        if error.codigo == CodigoError.SESION_EXPIRADA:
            self.sesion_expirada.emit(error)

    # ------------------------------------------------------------------------------------
    # Deshacer con doble control
    # ------------------------------------------------------------------------------------

    def deshacer(self) -> None:
        """«Deshacer…»: inspecciona (solo lectura) las marcadas y encadena las confirmaciones."""
        detalle = self._detalle_actual()
        if detalle is None or self._cerrado or self._ocupado or self._deshaciendo:
            return
        # Se reevalúa justo ahora: el lote pudo abrirse en la sesión desde la última vez.
        if self._motivo_sin_deshacer() is not None:
            self._refrescar_botones()
            return
        marcadas = self.marcadas()
        self._ocupado = True
        self._poner_estado(texto_comprobando_para_borrar())
        self._refrescar_botones()
        gen = self._gen
        self._lanzar(
            inspeccionar_inventario,
            self._sesion,
            self._reloj,
            detalle,
            marcadas,
            self._permisos,
            al_terminar=lambda insp: self._tras_inspeccion(gen, detalle, marcadas, insp),
            al_fallar=lambda e: self._fallo(gen, e),
        )

    def _tras_inspeccion(
        self,
        gen: int,
        detalle: DetalleLote,
        marcadas: frozenset[int],
        inspeccion: InspeccionRollback,
    ) -> None:
        if self._cerrado or gen != self._gen:
            return
        self._ocupado = False
        self._poner_estado(texto_lotes_leidos(len(self._lista.lotes)) if self._lista else "")
        self._refrescar_botones()
        if not inspeccion.hay_algo_que_avisar:
            self._pedir_codigo(detalle, marcadas, frozenset(), frozenset())
            return
        dialogo = DialogoConfirmarDeshacerForzado(inspeccion, self)
        dialogo.finished.connect(
            lambda _r: self._tras_confirmar_forzado(gen, dialogo, detalle, marcadas, inspeccion)
        )
        dialogo.open()

    def _tras_confirmar_forzado(
        self,
        gen: int,
        dialogo: DialogoConfirmarDeshacerForzado,
        detalle: DetalleLote,
        marcadas: frozenset[int],
        inspeccion: InspeccionRollback,
    ) -> None:
        eleccion = dialogo.eleccion
        dialogo.deleteLater()
        if eleccion == EleccionDeshacer.CANCELAR or self._cerrado or gen != self._gen:
            return  # sin confirmar no se escribe nada
        # SEG-A-01: solo se fuerzan exactamente las máquinas que el usuario vio en el diálogo.
        if eleccion == EleccionDeshacer.FORZAR:
            self._pedir_codigo(
                detalle,
                marcadas,
                frozenset(inspeccion.encendidas),
                frozenset(inspeccion.protegidas),
            )
        else:
            self._pedir_codigo(detalle, marcadas, frozenset(), frozenset())

    def _pedir_codigo(
        self,
        detalle: DetalleLote,
        marcadas: frozenset[int],
        forzar_apagado: frozenset[int],
        forzar_desproteccion: frozenset[int],
    ) -> None:
        gen = self._gen
        dialogo = DialogoConfirmarCodigoLote(detalle.lote.codigo, len(marcadas), self)
        dialogo.finished.connect(
            lambda r: self._tras_codigo(
                gen,
                dialogo,
                r == QDialog.DialogCode.Accepted,
                detalle,
                marcadas,
                forzar_apagado,
                forzar_desproteccion,
            )
        )
        dialogo.open()

    def _tras_codigo(
        self,
        gen: int,
        dialogo: DialogoConfirmarCodigoLote,
        aceptado: bool,
        detalle: DetalleLote,
        marcadas: frozenset[int],
        forzar_apagado: frozenset[int],
        forzar_desproteccion: frozenset[int],
    ) -> None:
        confirmado = aceptado and codigo_confirmado(dialogo.campo.text(), detalle.lote.codigo)
        dialogo.deleteLater()
        if not confirmado or self._cerrado or gen != self._gen or self._deshaciendo:
            return
        if detalle.lote.codigo in self._lotes_de_sesion():
            # V-C07: mientras se confirmaba, el lote se abrió en la sesión.
            self._refrescar_botones()
            return
        self._ejecutar_borrado(detalle, marcadas, forzar_apagado, forzar_desproteccion)

    def _ejecutar_borrado(
        self,
        detalle: DetalleLote,
        marcadas: frozenset[int],
        forzar_apagado: frozenset[int],
        forzar_desproteccion: frozenset[int],
    ) -> None:
        if problema_seleccion(len(marcadas)) is not None:
            return  # V-C09 / vacía: el botón ya estaba deshabilitado
        codigo = detalle.lote.codigo
        previstas = [
            (mv.recurso.nombre or "", mv.recurso.vmid, mv.recurso.nodo or "")
            for mv in detalle.maquinas
            if mv.recurso.vmid in marcadas and mv.deshacible
        ]
        self._deshaciendo = True
        self._codigo_borrando = codigo
        self._control = ControlLote()
        self._puente = PuenteRollback(self)
        self._modelo_resultado.iniciar(previstas)
        self.resumen_resultado.setText(texto_borrando())
        self._bloque_resultado.setVisible(True)
        self.boton_detener.setEnabled(True)
        self._poner_estado(texto_borrando())
        self._refrescar_botones()
        self.deshacer_empezado.emit(codigo)
        self._timer.start()
        gen = self._gen
        self._lanzar(
            deshacer_inventario,
            self._sesion,
            self._reloj,
            detalle,
            marcadas,
            self._puente.observar,
            self._control,
            forzar_apagado,
            forzar_desproteccion,
            self._permisos,
            al_terminar=lambda r: self._tras_borrado(gen, codigo, r),
            al_fallar=lambda e: self._fallo_borrado(gen, codigo, e),
        )

    def _refrescar_progreso(self) -> None:
        puente = self._puente
        if puente is None or self._cerrado:
            return
        resultados = puente.tomar_si_sucio()
        if resultados is not None:
            self._modelo_resultado.registrar_todos(resultados)

    def _resumir(self, resultados: Sequence[ResultadoRollback]) -> None:
        eliminadas = sum(1 for r in resultados if r.estado == EstadoRollback.ELIMINADA)
        ya_no_estaban = sum(1 for r in resultados if r.estado == EstadoRollback.YA_NO_EXISTIA)
        fallidas = sum(
            1 for r in resultados if r.estado in (EstadoRollback.FALLO, EstadoRollback.INCIERTA)
        )
        omitidas = len(resultados) - eliminadas - ya_no_estaban - fallidas
        self.resumen_resultado.setText(
            texto_resumen_resultado(eliminadas, omitidas, fallidas, ya_no_estaban)
        )

    def _tras_borrado(self, gen: int, codigo: str, resultados: list[ResultadoRollback]) -> None:
        self._deshaciendo = False
        self._codigo_borrando = None
        self._control = None
        self._puente = None
        # La ventana se entera aunque el diálogo ya se cerrase (desbloquea «Lote > Deshacer»).
        self.deshacer_terminado.emit(codigo)
        if self._cerrado or gen != self._gen:
            return
        self._timer.stop()
        self._modelo_resultado.registrar_todos(resultados)
        self._resumir(resultados)
        self.boton_detener.setEnabled(False)
        # Se relee el estado real del servidor: lo borrado desaparece de la lista.
        self._detalles.pop(codigo, None)
        # Se conservan _vistas y _marcas: la relectura respeta lo que el usuario desmarcó.
        self._previos.clear()  # lo borrado no se muestra como «ya no existe»
        self._refrescar_botones()
        self._leer_lista(self._codigo)

    def _fallo_borrado(self, gen: int, codigo: str, error: ErrorProxLaunch) -> None:
        self._deshaciendo = False
        self._codigo_borrando = None
        self._control = None
        self._puente = None
        self.deshacer_terminado.emit(codigo)
        if self._cerrado or gen != self._gen:
            return
        self._timer.stop()
        self.resumen_resultado.setText(texto_error(error))
        self.boton_detener.setEnabled(False)
        self._poner_estado(texto_error(error), aviso=True)
        self._refrescar_botones()
        if error.codigo == CodigoError.SESION_EXPIRADA:
            self.sesion_expirada.emit(error)
