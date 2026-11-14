"""Resumen del lote antes de crear: plan, totales, avisos y confirmación (RF-L10, RF-L11).

Muestra lo que se va a crear (tabla del plan con un modelo, no 100 widgets), el reparto, los
números saltados, los avisos ANTES de los botones y, si hace falta, la casilla de
sobreasignación. El mismo panel enseña el resultado de una simulación, etiquetado
«SIMULACIÓN — no se creó nada», con la petición de cada máquina en detalles técnicos.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.informe_lote import texto_permisos_no_verificados, texto_rangos
from proxlaunch.interfaz.modelos_tabla import ModeloPlan, TablaCopiable
from proxlaunch.interfaz.textos import (
    texto_error,
    texto_modo_clon,
    texto_motivo_reparto,
    texto_origen_corto,
    texto_problema_lote,
    texto_resumen_origen,
)
from proxlaunch.interfaz.vistas.campos import etiqueta, mensaje, poner_mensaje
from proxlaunch.interfaz.vistas.detalles_tecnicos import DetallesTecnicos
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    COMPARTIDO,
    AccionPeticion,
    ElementoPlan,
    Plan,
    Problema,
    ResultadoSimulacion,
    Severidad,
)
from proxlaunch.nucleo.modelos.origen import DetalleClon, DetalleImportacion, ModoClon
from proxlaunch.nucleo.modelos.vm import OrigenSO

_MAX_AVISOS_VISIBLES = 12


def texto_total_maquinas(n: int) -> str:
    """«Vas a crear una máquina» / «Vas a crear 12 máquinas» (CA-L01.5)."""
    if n == 1:
        return QCoreApplication.translate("ResumenLote", "Vas a crear una máquina")
    return QCoreApplication.translate("ResumenLote", "Vas a crear %n máquinas", None, n)


def texto_boton_crear(n: int, *, simulado: bool) -> str:
    if simulado:
        if n == 1:
            return QCoreApplication.translate("ResumenLote", "Crear de verdad esta máquina")
        return QCoreApplication.translate(
            "ResumenLote", "Crear de verdad estas %n máquinas", None, n
        )
    if n == 1:
        return QCoreApplication.translate("ResumenLote", "Crear 1 máquina")
    return QCoreApplication.translate("ResumenLote", "Crear %n máquinas", None, n)


def texto_boton_reducir(n: int) -> str:
    if n == 1:
        return QCoreApplication.translate("ResumenLote", "Reducir a 1")
    return QCoreApplication.translate("ResumenLote", "Reducir a %n", None, n)


def texto_boton_quitar_excedentes() -> str:
    return QCoreApplication.translate("ResumenLote", "Quitar las filas que no caben")


def texto_filas_del_archivo(n: int, total: int) -> str:
    """«Se van a crear 8 de las 10 filas del archivo» (CA-C07.2)."""
    return QCoreApplication.translate(
        "ResumenLote", "Se van a crear {n} de las {total} filas del archivo."
    ).format(n=n, total=total)


def _texto_maquinas(n: int) -> str:
    if n == 1:
        return QCoreApplication.translate("ResumenLote", "1 máquina")
    return QCoreApplication.translate("ResumenLote", "%n máquinas", None, n)


def _gib(bytes_: int) -> str:
    valor = bytes_ / 1024**3
    return f"{valor:.0f}" if abs(valor - round(valor)) < 0.05 else f"{valor:.1f}"


def _ruta_de_peticion(accion: AccionPeticion, nodo: str, vmid: int, e: ElementoPlan | None) -> str:
    """Método y ruta de una petición simulada (el clon va a la plantilla; los ajustes, al clon)."""
    if accion == AccionPeticion.CLONAR:
        det = e.cfg.detalle_origen if e is not None else None
        plantilla = det.plantilla.vmid if isinstance(det, DetalleClon) else None
        return f"POST /nodes/{nodo}/qemu/{plantilla if plantilla is not None else '?'}/clone"
    if accion == AccionPeticion.CONFIGURAR:
        return f"PUT /nodes/{nodo}/qemu/{vmid}/config"
    if accion == AccionPeticion.AMPLIAR:
        return f"PUT /nodes/{nodo}/qemu/{vmid}/resize"
    return f"POST /nodes/{nodo}/qemu"


def texto_peticiones(sim: ResultadoSimulacion) -> str:
    """Peticiones de cada máquina, tal como se enviarían (sin cabeceras ni secretos).

    Un clon envía varias (clonar, configurar, ampliar el disco): salen todas, en orden.
    """
    bloques: list[str] = []
    por_vmid = {e.vmid: e for e in sim.plan.elementos}
    for vmid, parametros in sim.peticiones.items():
        e = por_vmid.get(vmid)
        cabecera = f"# {e.nombre} (VMID {vmid})" if e else f"# VMID {vmid}"
        detalle = sim.peticiones_detalle.get(vmid)
        if detalle:
            lineas = [cabecera]
            for pet in detalle:
                lineas.append(_ruta_de_peticion(pet.accion, pet.nodo, vmid, e))
                lineas.extend(f"  {k} = {v}" for k, v in pet.parametros.items())
        else:
            nodo = e.nodo if e else "?"
            lineas = [cabecera, f"POST /nodes/{nodo}/qemu"]
            lineas.extend(f"  {k} = {v}" for k, v in parametros.items())
        bloques.append("\n".join(lineas))
    return "\n\n".join(bloques)


def texto_origen_del_plan(plan: Plan) -> str:
    """Cómo se creará cada máquina: ISO, disco importado o plantilla (RF-O29, CA-O18.8, CA-O23.4).

    Vacío si todas son discos vacíos (el lote de siempre no cambia).
    """
    elementos = plan.elementos
    if not elementos or all(e.cfg.origen == OrigenSO.DISCO_VACIO for e in elementos):
        return ""
    if plan.definicion.es_por_filas:
        cuenta: dict[OrigenSO, int] = {}
        for e in elementos:
            cuenta[e.cfg.origen] = cuenta.get(e.cfg.origen, 0) + 1
        partes = [f"{n} × {texto_origen_corto(o)}" for o, n in cuenta.items()]
        return QCoreApplication.translate(
            "ResumenLote", "Origen de las máquinas: {partes}."
        ).format(partes=", ".join(partes))
    primero = elementos[0].cfg
    lineas = [
        QCoreApplication.translate("ResumenLote", "Origen: {origen}.").format(
            origen=texto_resumen_origen(primero)
        )
    ]
    det = primero.detalle_origen
    if isinstance(det, DetalleClon):
        nodos = sorted(
            {
                str(x.cfg.detalle_origen.plantilla.nodo)
                for x in elementos
                if isinstance(x.cfg.detalle_origen, DetalleClon)
            }
        )
        if len(nodos) > 1:
            lineas.append(
                QCoreApplication.translate(
                    "ResumenLote",
                    "La plantilla «{nombre}» está en {nodos}: se clona la de cada nodo.",
                ).format(nombre=det.plantilla.nombre, nodos=" y ".join(nodos))
            )
        if (det.modo_efectivo or det.modo) == ModoClon.ENLAZADO:
            lineas.append(
                QCoreApplication.translate(
                    "ResumenLote",
                    "Las máquinas dependen de la plantilla (copia {modo}): Proxmox no te dejará "
                    "borrarla mientras existan.",
                ).format(modo=texto_modo_clon(ModoClon.ENLAZADO))
            )
    elif isinstance(det, DetalleImportacion) and primero.discos:
        tamano = det.tamano_virtual_bytes
        if tamano is not None:
            t = -(-tamano // 1024**3)
            lineas.append(
                QCoreApplication.translate(
                    "ResumenLote",
                    "Cada máquina recibirá una copia completa del disco ({t} GiB). "
                    "Total: {total} GiB en «{storage}».",
                ).format(t=t, total=t * len(elementos), storage=primero.discos[0].storage)
            )
    return "\n".join(lineas)


class ResumenLote(QWidget):
    """Pantalla de resumen del lote (y de su simulación)."""

    simular_solicitado = Signal()
    crear_solicitado = Signal()
    reducir_solicitado = Signal(int)
    volver_solicitado = Signal()
    cancelar_solicitado = Signal()  # cancela la preparación del plan o la simulación (CA-L11.10)
    informe_simulacion_solicitado = Signal()  # exporta la simulación como informe (CA-L11.8)
    nodo_reintento_cambiado = Signal(object)  # str o None (los mismos nodos de antes)
    # Lote por filas: quitar las filas que no caben (posiciones) y asignar VMID automáticos.
    quitar_excedentes_solicitado = Signal(object)  # tuple[int, ...]
    asignar_automatico_solicitado = Signal(object)  # tuple[int, ...] de posiciones de fila

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plan: Plan | None = None
        self._simulacion: ResultadoSimulacion | None = None
        self._bloqueo_crear: str | None = None
        self._enviado = False
        self._ocupado = False
        self._total_filas_archivo: int | None = None  # filas del CSV (para «N de N+M»)
        # Plan de un reintento: sus filas no son el lote del formulario, así que no se ofrece
        # reasignar ni quitar filas (cambiarían el formulario por las filas del reintento).
        self._es_reintento = False

        self._titulo = QLabel()
        fuente = self._titulo.font()
        fuente.setPointSize(fuente.pointSize() + 3)
        fuente.setBold(True)
        self._titulo.setFont(fuente)
        self._titulo.setTextFormat(Qt.TextFormat.PlainText)
        self._titulo.setAccessibleName(
            QCoreApplication.translate("ResumenLote", "Título del resumen")
        )
        self._simulacion_etiqueta = QLabel()
        self._simulacion_etiqueta.setProperty("aviso", True)
        self._simulacion_etiqueta.setWordWrap(True)
        self._simulacion_etiqueta.setTextFormat(Qt.TextFormat.PlainText)
        self._simulacion_etiqueta.hide()
        fuente_sim = self._simulacion_etiqueta.font()
        fuente_sim.setBold(True)
        self._simulacion_etiqueta.setFont(fuente_sim)

        self.modelo = ModeloPlan(self)
        self.tabla = TablaCopiable(
            QCoreApplication.translate("ResumenLote", "Máquinas que se van a crear")
        )
        self.tabla.setModel(self.modelo)
        self.tabla.setMinimumHeight(160)

        self._totales = self._etiqueta_datos()
        self._origen = self._etiqueta_datos()
        self._reparto = self._etiqueta_datos()
        self._saltados = self._etiqueta_datos(secundario=True)
        self._errores = mensaje(error=True)
        self._avisos = mensaje(aviso=True)
        self._nota_nombres = self._etiqueta_datos(secundario=True)
        self.casilla_thin = QCheckBox(
            QCoreApplication.translate("ResumenLote", "Entiendo el riesgo de sobreasignar espacio")
        )
        self.casilla_thin.setAccessibleName(
            QCoreApplication.translate(
                "ResumenLote", "Confirmo que entiendo el riesgo de sobreasignar espacio"
            )
        )
        self.casilla_thin.hide()
        self.casilla_thin.toggled.connect(lambda _c: self._refrescar_botones())
        self._motivo = self._etiqueta_datos(secundario=True)
        self.detalles_peticiones = DetallesTecnicos()

        self._etiqueta_nodo = QLabel(
            QCoreApplication.translate("ResumenLote", "Nodo de destino para el reintento")
        )
        self.combo_nodo_reintento = QComboBox()
        self.combo_nodo_reintento.setAccessibleName(
            QCoreApplication.translate("ResumenLote", "Nodo de destino para el reintento")
        )
        self.combo_nodo_reintento.currentIndexChanged.connect(self._al_cambiar_nodo_reintento)
        self._etiqueta_nodo.hide()
        self.combo_nodo_reintento.hide()
        self.boton_volver = QPushButton(
            QCoreApplication.translate("ResumenLote", "Volver al formulario")
        )
        self.boton_copiar = QPushButton(QCoreApplication.translate("ResumenLote", "Copiar resumen"))
        self.boton_cancelar = QPushButton(QCoreApplication.translate("ResumenLote", "Cancelar"))
        self.boton_cancelar.hide()
        self.boton_informe_simulacion = QPushButton(
            QCoreApplication.translate("ResumenLote", "Informe de la simulación…")
        )
        self.boton_informe_simulacion.hide()
        self.boton_reducir = QPushButton()
        self.boton_quitar_excedentes = QPushButton(texto_boton_quitar_excedentes())
        self.boton_quitar_excedentes.setAccessibleName(
            QCoreApplication.translate(
                "ResumenLote", "Quitar del lote las filas que no caben en el servidor"
            )
        )
        self.boton_quitar_excedentes.hide()
        self.boton_quitar_excedentes.clicked.connect(self._al_quitar_excedentes)
        self._nota_filas = etiqueta("", secundario=True)
        self._nota_filas.hide()
        self._excedentes = mensaje(error=True)
        # Filas con un VMID explícito ocupado: una línea y un botón por fila (CA-C09.3).
        self._zona_asignar = QWidget()
        self._zona_asignar.setAccessibleName(
            QCoreApplication.translate("ResumenLote", "Filas con el número de máquina ocupado")
        )
        self._capa_asignar = QVBoxLayout(self._zona_asignar)
        self._capa_asignar.setContentsMargins(0, 0, 0, 0)
        self._zona_asignar.hide()
        self.boton_simular = QPushButton(QCoreApplication.translate("ResumenLote", "Simular"))
        self.boton_simular.setToolTip(
            QCoreApplication.translate(
                "ResumenLote",
                "Hace todas las comprobaciones y muestra lo que se enviaría, sin crear nada.",
            )
        )
        self.boton_crear = QPushButton()
        self.boton_crear.setProperty("primario", True)
        self.boton_reducir.hide()
        self.boton_volver.clicked.connect(self.volver_solicitado)
        self.boton_cancelar.clicked.connect(self.cancelar_solicitado)
        self.boton_informe_simulacion.clicked.connect(self.informe_simulacion_solicitado)
        self.boton_copiar.clicked.connect(self.copiar_resumen)
        self.boton_reducir.clicked.connect(self._al_reducir)
        self.boton_simular.clicked.connect(self.simular_solicitado)
        self.boton_crear.clicked.connect(self._al_crear)

        botones = QHBoxLayout()
        botones.addWidget(self.boton_volver)
        botones.addWidget(self.boton_copiar)
        botones.addWidget(self.boton_informe_simulacion)
        botones.addStretch(1)
        botones.addWidget(self.boton_cancelar)
        botones.addWidget(self.boton_reducir)
        botones.addWidget(self.boton_quitar_excedentes)
        botones.addWidget(self.boton_simular)
        botones.addWidget(self.boton_crear)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        for w in (
            self._titulo,
            self._simulacion_etiqueta,
            self._nota_filas,
            self.tabla,
            self._totales,
            self._origen,
            self._reparto,
            self._saltados,
            self._errores,
            self._excedentes,
            self._zona_asignar,
            self._avisos,
            self._nota_nombres,
            self.casilla_thin,
            self._motivo,
            self._etiqueta_nodo,
            self.combo_nodo_reintento,
            self.detalles_peticiones,
        ):
            capa.addWidget(w)
        capa.addLayout(botones)
        self.mostrar_vacio()

    @staticmethod
    def _etiqueta_datos(*, secundario: bool = False) -> QLabel:
        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.PlainText)  # puede incluir nombres de nodos y storages
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if secundario:
            lbl.setProperty("secundario", True)
        lbl.hide()
        return lbl

    # --- Estados de la pantalla -------------------------------------------------------

    def mostrar_vacio(self) -> None:
        """Sin plan: todo oculto y sin botones de acción."""
        self._plan = None
        self._simulacion = None
        self._enviado = False
        self._ocupado = False
        self.modelo.establecer_plan(None)
        self._titulo.setText("")
        for w in (
            self._simulacion_etiqueta,
            self._totales,
            self._reparto,
            self._saltados,
            self._nota_nombres,
            self.casilla_thin,
            self._motivo,
            self.boton_reducir,
            self.boton_quitar_excedentes,
            self._nota_filas,
            self._zona_asignar,
            self._etiqueta_nodo,
            self.combo_nodo_reintento,
        ):
            w.hide()
        self._limpiar_asignar()
        poner_mensaje(self._excedentes, None)
        poner_mensaje(self._errores, None)
        poner_mensaje(self._avisos, None, aviso=True)
        self.detalles_peticiones.limpiar()
        self.casilla_thin.setChecked(False)
        self._refrescar_botones()

    def mostrar_selector_nodo(self, nodos: list[str], actual: str | None) -> None:
        """Reintento: deja elegir un nodo para todas las máquinas (CA-L21.1)."""
        self.combo_nodo_reintento.blockSignals(True)
        self.combo_nodo_reintento.clear()
        self.combo_nodo_reintento.addItem(
            QCoreApplication.translate("ResumenLote", "Los mismos nodos de antes"), None
        )
        for n in nodos:
            self.combo_nodo_reintento.addItem(n, n)
        self.combo_nodo_reintento.setCurrentIndex(
            max(self.combo_nodo_reintento.findData(actual), 0)
        )
        self.combo_nodo_reintento.blockSignals(False)
        self._etiqueta_nodo.show()
        self.combo_nodo_reintento.show()

    def _al_cambiar_nodo_reintento(self, _i: int) -> None:
        if not self._ocupado and not self._enviado:
            self.nodo_reintento_cambiado.emit(self.combo_nodo_reintento.currentData())

    def mostrar_planificando(self) -> None:
        """Mientras el núcleo reserva números y valida (en segundo plano)."""
        self.mostrar_vacio()
        self._ocupado = True
        self._titulo.setText(QCoreApplication.translate("ResumenLote", "Preparando el resumen…"))
        self._refrescar_botones()

    def mostrar_error(self, error: ErrorProxLaunch) -> None:
        """Falló la consulta al servidor: no se creó nada (E-L08)."""
        self.mostrar_vacio()
        self._ocupado = False
        self._titulo.setText(
            QCoreApplication.translate("ResumenLote", "No se pudo preparar el lote")
        )
        if error.codigo == CodigoError.SERVIDOR_NO_RESPONDE:
            texto = QCoreApplication.translate(
                "ResumenLote", "No se pudo consultar el servidor. No se creó nada."
            )
        else:
            texto = texto_error(error)
        poner_mensaje(self._errores, texto)
        self._refrescar_botones()

    def mostrar_diferencia(self, texto: str) -> None:
        """El plan cambió respecto al resumen visto: hay que confirmar otra vez (E-L11)."""
        poner_mensaje(
            self._avisos,
            texto_error(ErrorProxLaunch(CodigoError.LOTE_PLAN_CAMBIO, {"diferencia": texto})),
            aviso=True,
        )

    def mostrar_plan(
        self,
        plan: Plan,
        *,
        bloqueo_crear: str | None = None,
        simulacion: ResultadoSimulacion | None = None,
        diferencia: str | None = None,
    ) -> None:
        """Dibuja el plan (o el resultado de la simulación)."""
        self._plan = plan
        self._simulacion = simulacion
        self._bloqueo_crear = bloqueo_crear
        self._enviado = False
        self._ocupado = False
        n = len(plan.elementos) or plan.definicion.cantidad
        self.modelo.establecer_plan(plan)
        self._titulo.setText(texto_total_maquinas(n))
        total = self._total_filas_archivo
        self._nota_filas.setText(texto_filas_del_archivo(n, total) if total else "")
        self._nota_filas.setVisible(bool(total) and plan.definicion.es_por_filas)
        self._pintar_simulacion(simulacion)
        self._pintar_totales(plan)

        errores = [p for p in plan.problemas if p.severidad == Severidad.ERROR]
        avisos = [p for p in plan.problemas if p.severidad != Severidad.ERROR]
        poner_mensaje(self._errores, self._lista(errores, prefijo="✕ ", plan=plan))
        textos_avisos = self._lista(avisos, prefijo="⚠ ", plan=plan)
        if not plan.permisos_verificados:
            textos_avisos = f"⚠ {texto_permisos_no_verificados()}\n{textos_avisos}".strip()
        if diferencia:
            cambio = texto_error(
                ErrorProxLaunch(CodigoError.LOTE_PLAN_CAMBIO, {"diferencia": diferencia})
            )
            textos_avisos = f"⚠ {cambio}\n{textos_avisos}".strip()
        poner_mensaje(self._avisos, textos_avisos, aviso=True)
        hay_calificado = any(p.regla == "V-L06" for p in avisos)
        self._nota_nombres.setText(
            QCoreApplication.translate(
                "ResumenLote", "Puede haber otras máquinas con esos nombres que tú no puedes ver."
            )
        )
        self._nota_nombres.setVisible(hay_calificado)

        self.casilla_thin.setChecked(False)
        self.casilla_thin.setVisible(plan.requiere_confirmacion_thin)
        capacidad = plan.capacidad_maxima
        por_filas = plan.definicion.es_por_filas
        self.boton_reducir.setVisible(
            not por_filas and capacidad is not None and capacidad >= 1 and plan.bloqueado
        )
        if capacidad:
            self.boton_reducir.setText(texto_boton_reducir(capacidad))
        self._pintar_por_filas(plan)
        if simulacion is not None and simulacion.peticiones:
            self.detalles_peticiones.establecer(texto_peticiones(simulacion))
        else:
            self.detalles_peticiones.limpiar()
        self._refrescar_botones()

    def _pintar_simulacion(self, sim: ResultadoSimulacion | None) -> None:
        if sim is None:
            self._simulacion_etiqueta.hide()
            return
        texto = QCoreApplication.translate("ResumenLote", "SIMULACIÓN — no se creó nada")
        if sim.version_forzada is not None and sim.version_forzada != sim.version_detectada:
            texto += "\n" + QCoreApplication.translate(
                "ResumenLote",
                "Simulado con compatibilidad de Proxmox {forzada} (el servidor es {detectada})",
            ).format(
                forzada=f"{sim.version_forzada[0]}.{sim.version_forzada[1]}",
                detectada=f"{sim.version_detectada[0]}.{sim.version_detectada[1]}",
            )
        self._simulacion_etiqueta.setText(texto)
        self._simulacion_etiqueta.show()

    def _pintar_totales(self, plan: Plan) -> None:
        elementos = plan.elementos
        texto_origen = texto_origen_del_plan(plan)
        self._origen.setText(texto_origen)
        self._origen.setVisible(bool(texto_origen))
        if not elementos:
            self._totales.hide()
            self._reparto.hide()
            self._saltados.hide()
            return
        vcpu = sum(e.cfg.sockets * e.cfg.cores for e in elementos)
        memoria = sum(e.cfg.memoria_mib for e in elementos) / 1024
        lineas = [
            QCoreApplication.translate(
                "ResumenLote", "Totales: {n}, {v} procesadores virtuales, {m:g} GiB de memoria"
            ).format(n=_texto_maquinas(len(elementos)), v=vcpu, m=memoria)
        ]
        for clave in sorted(plan.uso, key=lambda c: (c.ambito, c.storage)):
            uso = plan.uso[clave]
            donde = (
                QCoreApplication.translate("ResumenLote", "«{s}» (compartido)").format(
                    s=clave.storage
                )
                if clave.ambito == COMPARTIDO
                else QCoreApplication.translate("ResumenLote", "«{s}» en {n}").format(
                    s=clave.storage, n=clave.ambito
                )
            )
            lineas.append(
                QCoreApplication.translate(
                    "ResumenLote", "Espacio en {donde}: {pedido} GiB de {libre} GiB libres"
                ).format(donde=donde, pedido=_gib(uso.pedido_bytes), libre=_gib(uso.libre_bytes))
            )
        self._totales.setText("\n".join(lineas))
        self._totales.show()

        reparto = []
        for nodo in sorted(plan.reparto):
            cantidad, motivo = plan.reparto[nodo]
            razon = texto_motivo_reparto(motivo)
            reparto.append(
                f"{nodo}: {_texto_maquinas(cantidad)}" + (f" ({razon})" if razon else "")
            )
        self._reparto.setText(
            QCoreApplication.translate("ResumenLote", "Reparto:") + "\n" + "\n".join(reparto)
        )
        self._reparto.setVisible(bool(reparto))

        if plan.vmids_saltados:
            self._saltados.setText(
                QCoreApplication.translate(
                    "ResumenLote",
                    "Se saltaron los números {rangos} (ya los usa otra máquina).",
                ).format(rangos=texto_rangos(plan.vmids_saltados))
            )
            self._saltados.show()
        else:
            self._saltados.hide()

    def _lista(self, problemas: list[Problema], *, prefijo: str, plan: Plan | None = None) -> str:
        """Textos únicos de los problemas; en un lote por filas cada uno dice «Fila N»."""
        por_filas = plan is not None and plan.definicion.es_por_filas

        def texto(p: Problema) -> str:
            if por_filas and p.indice is not None:
                return texto_problema_lote(p, fila=self.modelo.etiqueta_fila_de(p.indice))
            return texto_problema_lote(p)

        textos = list(dict.fromkeys(texto(p) for p in problemas))
        extra = len(textos) - _MAX_AVISOS_VISIBLES
        visibles = textos[:_MAX_AVISOS_VISIBLES]
        lineas = [prefijo + t for t in visibles]
        if extra > 0:
            lineas.append(QCoreApplication.translate("ResumenLote", "… y %n más", None, extra))
        return "\n".join(lineas)

    # --- Lote por filas (D-22) ------------------------------------------------------------

    def establecer_total_filas_archivo(self, total: int | None) -> None:
        """Filas que traía el archivo (para decir «N de N+M»); ``None`` si no viene de un CSV."""
        self._total_filas_archivo = total

    def establecer_reintento(self, es_reintento: bool) -> None:
        """Marca que el plan mostrado es el de un reintento (sin botones de reasignar/quitar)."""
        self._es_reintento = es_reintento

    def _limpiar_asignar(self) -> None:
        while self._capa_asignar.count():
            item = self._capa_asignar.takeAt(0)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()

    def _pintar_por_filas(self, plan: Plan) -> None:
        """Filas que no caben (con «Quitar las filas que no caben») y VMID ocupados."""
        self._limpiar_asignar()
        excedentes = plan.filas_excedentes if plan.definicion.es_por_filas else ()
        self.boton_quitar_excedentes.setVisible(
            bool(excedentes) and plan.bloqueado and not self._es_reintento
        )
        if excedentes:
            etiquetas = ", ".join(self.modelo.etiqueta_fila_de(i) for i in excedentes)
            poner_mensaje(
                self._excedentes,
                QCoreApplication.translate("ResumenLote", "No caben las filas: {filas}.").format(
                    filas=etiquetas
                ),
            )
        else:
            poner_mensaje(self._excedentes, None)
        ocupadas: list[int] = []
        if plan.definicion.es_por_filas:
            ocupadas = sorted(
                {p.indice for p in plan.problemas if p.regla == "V-03" and p.indice is not None}
            )
        if self._es_reintento:
            ocupadas = []  # sin botones; el aviso general de VMID ocupado sigue en los problemas
        for i in ocupadas[:_MAX_AVISOS_VISIBLES]:
            fila = QWidget()
            h = QHBoxLayout(fila)
            h.setContentsMargins(0, 0, 0, 0)
            vmid = plan.definicion.filas[i].vmid
            texto = QCoreApplication.translate(
                "ResumenLote", "Fila {n}: el número {vmid} ya lo usa otra máquina."
            ).format(n=self.modelo.etiqueta_fila_de(i), vmid=vmid)
            lbl = etiqueta(texto)
            boton = QPushButton(
                QCoreApplication.translate("ResumenLote", "Asignar automáticamente")
            )
            boton.setAccessibleName(
                QCoreApplication.translate(
                    "ResumenLote", "Asignar un número de máquina automático a la fila {n}"
                ).format(n=self.modelo.etiqueta_fila_de(i))
            )
            boton.clicked.connect(
                lambda _c=False, k=i: self.asignar_automatico_solicitado.emit((k,))
            )
            h.addWidget(lbl, 1)
            h.addWidget(boton)
            self._capa_asignar.addWidget(fila)
        if len(ocupadas) > 1:
            todas = QPushButton(
                QCoreApplication.translate(
                    "ResumenLote", "Asignar automáticamente a las %n filas", None, len(ocupadas)
                )
            )
            todas.clicked.connect(
                lambda _c=False, k=tuple(ocupadas): self.asignar_automatico_solicitado.emit(k)
            )
            self._capa_asignar.addWidget(todas, 0, Qt.AlignmentFlag.AlignLeft)
        self._zona_asignar.setVisible(bool(ocupadas))

    def _al_quitar_excedentes(self) -> None:
        plan = self._plan
        if plan is not None and plan.filas_excedentes:
            self.quitar_excedentes_solicitado.emit(tuple(plan.filas_excedentes))

    # --- Botones ----------------------------------------------------------------------

    @property
    def plan(self) -> Plan | None:
        return self._plan

    @property
    def es_simulacion(self) -> bool:
        return self._simulacion is not None

    @property
    def puede_crear(self) -> bool:
        plan = self._plan
        if plan is None or self._ocupado or self._enviado or plan.bloqueado:
            return False
        if self._bloqueo_crear:
            return False
        return not (plan.requiere_confirmacion_thin and not self.casilla_thin.isChecked())

    def _refrescar_botones(self) -> None:
        plan = self._plan
        n = (len(plan.elementos) or plan.definicion.cantidad) if plan else 0
        self.boton_crear.setText(texto_boton_crear(n, simulado=self.es_simulacion))
        self.boton_crear.setEnabled(self.puede_crear)
        self.boton_simular.setEnabled(plan is not None and not self._ocupado and not self._enviado)
        self.boton_copiar.setEnabled(plan is not None)
        self.boton_cancelar.setVisible(self._ocupado)
        self.boton_informe_simulacion.setVisible(self.es_simulacion and plan is not None)
        self.boton_volver.setEnabled(not self._enviado)
        motivo = ""
        if plan is not None:
            if self._bloqueo_crear:
                motivo = self._bloqueo_crear
            elif plan.bloqueado:
                motivo = QCoreApplication.translate(
                    "ResumenLote", "Corrige los errores marcados para poder crear las máquinas."
                )
            elif plan.requiere_confirmacion_thin and not self.casilla_thin.isChecked():
                motivo = QCoreApplication.translate(
                    "ResumenLote",
                    "Marca la casilla para confirmar que entiendes el riesgo de sobreasignar.",
                )
        self._motivo.setText(motivo)
        self._motivo.setVisible(bool(motivo))
        self.boton_crear.setToolTip(motivo)

    def _al_crear(self) -> None:
        # CA-L10.7: la bandera se activa antes de emitir; un doble clic inicia un solo lote.
        if not self.puede_crear:
            return
        self._enviado = True
        self._refrescar_botones()
        self.crear_solicitado.emit()

    def liberar(self) -> None:
        """Permite volver a pulsar (por ejemplo si se canceló la confirmación)."""
        self._enviado = False
        self._refrescar_botones()

    def _al_reducir(self) -> None:
        plan = self._plan
        if plan is not None and plan.capacidad_maxima:
            self.reducir_solicitado.emit(plan.capacidad_maxima)

    # --- Texto copiable ---------------------------------------------------------------

    def texto_resumen(self) -> str:
        """Resumen en texto plano (sin secretos) para copiar (CA-L10.8)."""
        partes = [self._titulo.text()]
        if not self._simulacion_etiqueta.isHidden():
            partes.append(self._simulacion_etiqueta.text())
        partes.append(self.tabla.texto(solo_seleccion=False))
        for w in (self._totales, self._reparto, self._saltados, self._errores, self._avisos):
            if not w.isHidden() and w.text():
                partes.append(w.text())
        return "\n\n".join(p for p in partes if p)

    def copiar_resumen(self) -> None:
        QApplication.clipboard().setText(self.texto_resumen())
