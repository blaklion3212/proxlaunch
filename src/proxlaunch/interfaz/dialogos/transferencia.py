"""Diálogos de transferencia: subir un archivo del equipo o descargar por URL en el servidor.

(RF-O09 a RF-O12, RF-O16, RF-O25.) Cada diálogo es la confirmación de la acción: muestra el nombre
final, el tamaño, el almacenamiento y el nodo de destino y el aviso de que no se puede deshacer
desde ProxLaunch, con «Cancelar» como botón predeterminado. Nunca hay opción de sobrescribir: si el
nombre ya existe se ofrece «Usar el existente» o «Cambiar el nombre» (INV-O2).

Toda la E/S (inspección del archivo, comprobaciones previas, subida, descarga) corre en el
``Lanzador``; el progreso llega del hilo de trabajo a un puente que lo entrega como mucho 10 veces
por segundo al hilo de la interfaz. «Cancelar» propaga el evento de cancelación al núcleo. Una URL
nunca se muestra completa: solo ``host/archivo``.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.modelos_tabla_origen import (
    formatear_bytes,
    texto_tiempo,
)
from proxlaunch.interfaz.textos import (
    texto_aviso_archivo_local,
    texto_error,
    texto_estado_transferencia,
    texto_motivo_checksum,
    texto_motivo_nombre_archivo,
    texto_motivo_url,
    texto_problema,
    texto_progreso_transferencia,
    texto_quedo_archivo,
)
from proxlaunch.interfaz.trabajadores import Lanzador, Trabajador
from proxlaunch.interfaz.vistas.campos import poner_mensaje, poner_propiedad
from proxlaunch.interfaz.vistas.detalles_tecnicos import DetallesTecnicos, texto_detalles
from proxlaunch.nucleo.api.cliente import MetadatosUrl
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.origen.nombres import sanear_nombre_archivo, validar_nombre_archivo
from proxlaunch.nucleo.origen.storages import elegir_nodo_transferencia
from proxlaunch.nucleo.transferencias import archivo_local
from proxlaunch.nucleo.transferencias.archivo_local import InspeccionArchivo, inspeccionar
from proxlaunch.nucleo.transferencias.modelos import (
    ComprobacionPrevia,
    DestinoTransferencia,
    EstadoTransferencia,
    Progreso,
    ResultadoTransferencia,
    TipoTransferencia,
)
from proxlaunch.nucleo.transferencias.servicio import ServicioTransferencias
from proxlaunch.nucleo.transferencias.url import (
    AlgoritmoChecksum,
    ChecksumTransferencia,
    UrlDescarga,
    validar_checksum,
    validar_url,
)
from proxlaunch.nucleo.validacion import Severidad

# Intervalo con el que la interfaz toma el último progreso (como mucho 10 veces por segundo).
INTERVALO_PROGRESO_MS = 100
# Resolución de la barra (milésimas) para no depender del tamaño del archivo.
_ESCALA_BARRA = 1000


class ControladorTransferencia(Protocol):
    """Lo que los diálogos de transferencia necesitan del controlador del origen (F5b).

    Es un protocolo: sirve cualquier objeto con estos miembros (propiedades o atributos), por
    ejemplo ``ControladorOrigen`` o un doble de pruebas.
    """

    @property
    def lanzador(self) -> Lanzador:
        """Lanzador en el que se ejecuta toda la E/S."""
        ...

    @property
    def servicio_transferencias(self) -> ServicioTransferencias:
        """Servicio de la sesión activa (una sola transferencia a la vez)."""
        ...

    @property
    def inventario(self) -> Inventario | None:
        """Inventario con el catálogo y los permisos ya leídos."""
        ...

    @property
    def modo_avanzado(self) -> bool:
        """``True`` en modo avanzado (permite ``http://`` y no verificar certificados)."""
        ...

    def storage_para(self, contenido: Contenido, nodo: str, parent: QWidget) -> str | None:
        """Almacenamiento donde guardar ``contenido`` (pregunta una vez si hay varios, RF-O05).

        ``None`` si no hay ninguno o el usuario cancela.
        """
        ...


class _PuenteProgreso(QObject):
    """Recoge el progreso (hilo de trabajo) y lo entrega acotado al hilo de la interfaz.

    ``observar`` solo guarda la última instantánea bajo un cerrojo; un ``QTimer`` del diálogo
    llama a ``tomar`` cada ``INTERVALO_PROGRESO_MS``. Así el hilo de trabajo no toca widgets y la
    interfaz se repinta como mucho 10 veces por segundo.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cerrojo = threading.Lock()
        self._ultimo: Progreso | None = None
        self._sucio = False

    def observar(self, progreso: Progreso) -> None:
        """Callback del núcleo; se llama desde cualquier hilo."""
        with self._cerrojo:
            self._ultimo = progreso
            self._sucio = True

    def tomar(self) -> Progreso | None:
        """Último progreso si cambió desde la lectura anterior; si no, ``None``."""
        with self._cerrojo:
            if not self._sucio:
                return None
            self._sucio = False
            return self._ultimo


class _Fase(Enum):
    PREPARANDO = "preparando"  # falta archivo/URL o se está comprobando
    LISTO = "listo"  # todo comprobado: se puede confirmar
    EN_CURSO = "en_curso"
    TERMINADO = "terminado"


# Estados en los que la subida ya envió todos los bytes y solo espera al servidor.
_ESTADOS_ESPERA_SERVIDOR = frozenset(
    {EstadoTransferencia.ESPERANDO_SERVIDOR, EstadoTransferencia.VERIFICANDO}
)


def _avisos_url(url: UrlDescarga) -> list[str]:
    """Avisos (no bloquean) de una dirección: IP literal interna o puerto poco habitual.

    Que el servidor descargue de una IP privada, de loopback o de enlace local puede alcanzar
    equipos de la red interna; un puerto distinto de 80/443 también es poco habitual.
    """
    avisos: list[str] = []
    try:
        ip = ipaddress.ip_address(url.host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local):
        avisos.append(
            QCoreApplication.translate(
                "DialogoTransferencia",
                "La dirección apunta a un equipo de la red interna del servidor. Descárgala solo "
                "si sabes de qué equipo se trata.",
            )
        )
    try:
        puerto = urlsplit(url.texto.strip()).port
    except ValueError:
        puerto = None
    if puerto is not None and puerto not in (80, 443):
        avisos.append(
            QCoreApplication.translate(
                "DialogoTransferencia",
                "La dirección usa el puerto {puerto}, que no es el habitual (80 o 443).",
            ).format(puerto=puerto)
        )
    return avisos


def _aviso_checksum(checksum: ChecksumTransferencia | None) -> str | None:
    """Aviso (no bloquea) si la huella usa un algoritmo débil (MD5 o SHA-1)."""
    if checksum is None or checksum.algoritmo not in (
        AlgoritmoChecksum.MD5,
        AlgoritmoChecksum.SHA1,
    ):
        return None
    return QCoreApplication.translate(
        "DialogoTransferencia",
        "La huella usa un algoritmo antiguo ({algoritmo}): ya no protege de un archivo "
        "manipulado a propósito. Si puedes, usa una huella SHA-256 o SHA-512.",
    ).format(algoritmo=str(checksum.algoritmo.value).upper())


def _texto_no_deshacer(tipo: TipoTransferencia) -> str:
    """Aviso obligatorio de CA-O09.2 / CA-O25.1."""
    if tipo == TipoTransferencia.SUBIDA:
        return QCoreApplication.translate(
            "DialogoTransferencia",
            "Esta subida no se puede deshacer desde ProxLaunch (requeriría un permiso de "
            "administrador). Si te equivocas, pídele al administrador que borre el archivo.",
        )
    return QCoreApplication.translate(
        "DialogoTransferencia",
        "Esta descarga no se puede deshacer desde ProxLaunch (requeriría un permiso de "
        "administrador). Si te equivocas, pídele al administrador que borre el archivo.",
    )


class _DialogoTransferencia(QDialog):
    """Base común: destino, comprobaciones, progreso, cancelación y resultado."""

    terminada = Signal(object)  # ResultadoTransferencia (también cancelada o fallida)
    usar_existente = Signal(str)  # volid del archivo que ya estaba

    tipo: TipoTransferencia = TipoTransferencia.SUBIDA

    def __init__(
        self,
        controlador: ControladorTransferencia,
        contenido: Contenido,
        nodo: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controlador = controlador
        self.contenido = contenido
        self.nodo = nodo
        self.storage: str | None = None
        self.nodo_destino: str = nodo
        self.resultado: ResultadoTransferencia | None = None
        self.volid_elegido: str | None = None
        self._fase = _Fase.PREPARANDO
        self._trabajador: Trabajador | None = None
        self._generacion = 0  # descarta respuestas de comprobaciones ya obsoletas
        self._cerrado = False
        self._cancelando = False
        self._inicio = 0.0
        self._ultimo_progreso: Progreso | None = None
        self._comprobacion: ComprobacionPrevia | None = None
        self._puente = _PuenteProgreso(self)
        self._temporizador = QTimer(self)
        self._temporizador.setInterval(INTERVALO_PROGRESO_MS)
        self._temporizador.timeout.connect(self._vaciar_progreso)
        self.setModal(True)
        self.setMinimumWidth(560)

        # --- Zona de resultado de las comprobaciones -----------------------------------
        self.mensaje_comprobacion = QLabel()
        self.mensaje_comprobacion.setWordWrap(True)
        self.mensaje_comprobacion.setTextFormat(Qt.TextFormat.PlainText)
        self.mensaje_comprobacion.setAccessibleName(
            QCoreApplication.translate("DialogoTransferencia", "Resultado de las comprobaciones")
        )
        self.mensaje_comprobacion.hide()

        self.boton_usar_existente = QPushButton(
            QCoreApplication.translate("DialogoTransferencia", "Usar el existente")
        )
        self.boton_usar_existente.setAutoDefault(False)
        self.boton_usar_existente.clicked.connect(self._al_usar_existente)
        self.boton_cambiar_nombre = QPushButton(
            QCoreApplication.translate("DialogoTransferencia", "Cambiar el nombre")
        )
        self.boton_cambiar_nombre.setAutoDefault(False)
        self.boton_cambiar_nombre.clicked.connect(self._al_cambiar_nombre)
        self.fila_existente = QWidget()
        capa_existente = QHBoxLayout(self.fila_existente)
        capa_existente.setContentsMargins(0, 0, 0, 0)
        capa_existente.addWidget(self.boton_usar_existente)
        capa_existente.addWidget(self.boton_cambiar_nombre)
        capa_existente.addStretch(1)
        self.fila_existente.hide()

        self.casilla_raiz = QCheckBox(
            QCoreApplication.translate(
                "DialogoTransferencia", "Entiendo que la subida puede fallar"
            )
        )
        self.casilla_raiz.setAccessibleName(
            QCoreApplication.translate(
                "DialogoTransferencia", "Entiendo que la subida puede fallar"
            )
        )
        self.casilla_raiz.toggled.connect(lambda _on: self._actualizar_botones())
        self.casilla_raiz.hide()

        self.etiqueta_resumen = QLabel()
        self.etiqueta_resumen.setWordWrap(True)
        self.etiqueta_resumen.setTextFormat(Qt.TextFormat.PlainText)
        self.etiqueta_resumen.setAccessibleName(
            QCoreApplication.translate("DialogoTransferencia", "Resumen de lo que se va a hacer")
        )
        self.etiqueta_resumen.hide()

        self.aviso_no_deshacer = QLabel(_texto_no_deshacer(self.tipo))
        self.aviso_no_deshacer.setWordWrap(True)
        self.aviso_no_deshacer.setProperty("aviso", True)
        self.aviso_no_deshacer.setAccessibleName(
            QCoreApplication.translate("DialogoTransferencia", "Aviso: no se puede deshacer")
        )

        # --- Progreso -----------------------------------------------------------------
        self.panel_progreso = QWidget()
        capa_progreso = QVBoxLayout(self.panel_progreso)
        capa_progreso.setContentsMargins(0, 0, 0, 0)
        self.etiqueta_estado = QLabel()
        self.etiqueta_estado.setWordWrap(True)
        self.etiqueta_estado.setAccessibleName(
            QCoreApplication.translate("DialogoTransferencia", "Estado de la transferencia")
        )
        self.barra = QProgressBar()
        self.barra.setRange(0, _ESCALA_BARRA)
        self.barra.setValue(0)
        self.barra.setAccessibleName(
            QCoreApplication.translate("DialogoTransferencia", "Progreso de la transferencia")
        )
        self.etiqueta_detalle = QLabel()
        self.etiqueta_detalle.setProperty("secundario", True)
        self.etiqueta_detalle.setAccessibleName(
            QCoreApplication.translate("DialogoTransferencia", "Velocidad y tiempo restante")
        )
        capa_progreso.addWidget(self.etiqueta_estado)
        capa_progreso.addWidget(self.barra)
        capa_progreso.addWidget(self.etiqueta_detalle)
        self.panel_progreso.hide()

        self.etiqueta_final = QLabel()
        self.etiqueta_final.setWordWrap(True)
        self.etiqueta_final.setTextFormat(Qt.TextFormat.PlainText)
        self.etiqueta_final.setAccessibleName(
            QCoreApplication.translate("DialogoTransferencia", "Resultado")
        )
        self.etiqueta_final.hide()
        self.detalles = DetallesTecnicos()

        # --- Botones ------------------------------------------------------------------
        self.boton_accion = QPushButton()
        self.boton_accion.setAutoDefault(False)
        self.boton_accion.setEnabled(False)
        self.boton_accion.clicked.connect(self._al_pulsar_accion)
        self.boton_reintentar = QPushButton(
            QCoreApplication.translate("DialogoTransferencia", "Reintentar")
        )
        self.boton_reintentar.setAutoDefault(False)
        self.boton_reintentar.clicked.connect(self._reintentar)
        self.boton_reintentar.hide()
        self.boton_cancelar = QPushButton(
            QCoreApplication.translate("DialogoTransferencia", "Cancelar")
        )
        self.boton_cancelar.setDefault(True)
        self.boton_cancelar.clicked.connect(self._al_pulsar_cancelar)

        self._capa = QVBoxLayout(self)
        self._fila_botones = QHBoxLayout()
        self._fila_botones.addStretch(1)
        self._fila_botones.addWidget(self.boton_reintentar)
        self._fila_botones.addWidget(self.boton_accion)
        self._fila_botones.addWidget(self.boton_cancelar)

    def _terminar_diseno(self) -> None:
        """Añade lo común tras el formulario propio de cada diálogo."""
        self._capa.addWidget(self.mensaje_comprobacion)
        self._capa.addWidget(self.fila_existente)
        self._capa.addWidget(self.casilla_raiz)
        self._capa.addWidget(self.etiqueta_resumen)
        self._capa.addWidget(self.aviso_no_deshacer)
        self._capa.addWidget(self.panel_progreso)
        self._capa.addWidget(self.etiqueta_final)
        self._capa.addWidget(self.detalles)
        self._capa.addLayout(self._fila_botones)
        self.boton_cancelar.setFocus()  # el foco inicial nunca confirma nada

    # --- API pública --------------------------------------------------------------------

    @property
    def transferencia_en_curso(self) -> bool:
        """``True`` mientras la subida o descarga corre (para el cierre de la aplicación)."""
        return self._fase == _Fase.EN_CURSO

    @property
    def listo_para_confirmar(self) -> bool:
        """``True`` cuando todo está comprobado y el botón de acción está activo."""
        return self._fase == _Fase.LISTO and self.boton_accion.isEnabled()

    def cancelar_transferencia(self) -> None:
        """Pide al núcleo que detenga la transferencia (CA-O12.2, CA-O12.4).

        En una descarga equivale a «Dejar de esperar»: la descarga sigue en el servidor.
        """
        if self._fase != _Fase.EN_CURSO or self._cancelando:
            return
        self._cancelando = True
        self.boton_cancelar.setEnabled(False)
        self.boton_cancelar.setText(self._texto_cancelando())
        self.etiqueta_estado.setText(self._texto_cancelando())
        if self._trabajador is not None:
            self._trabajador.cancelar()

    def keyPressEvent(self, evento: QKeyEvent) -> None:
        """Intro en un campo de texto confirma el campo, nunca el botón predeterminado."""
        if evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and isinstance(
            self.focusWidget(), QLineEdit
        ):
            evento.accept()
            return
        super().keyPressEvent(evento)

    def reject(self) -> None:
        """Con una transferencia en curso, cerrar equivale a cancelar (no se cierra aún)."""
        if self._fase == _Fase.EN_CURSO:
            self.cancelar_transferencia()
            return
        super().reject()

    def done(self, resultado: int) -> None:
        self._cerrado = True
        self._temporizador.stop()
        super().done(resultado)

    # --- Textos que cambian según el tipo -----------------------------------------------

    def _texto_cancelando(self) -> str:
        raise NotImplementedError

    def _texto_boton_cancelar_en_curso(self) -> str:
        raise NotImplementedError

    # --- Destino y comprobaciones -------------------------------------------------------

    def _resolver_destino(self) -> bool:
        """Elige almacenamiento y nodo de la transferencia (RF-O05, DT-O4)."""
        inv = self._controlador.inventario
        if inv is None:
            self._mostrar_bloqueo(
                QCoreApplication.translate(
                    "DialogoTransferencia", "Todavía no se conoce el servidor. Conéctate primero."
                )
            )
            return False
        if self.storage is None:
            self.storage = self._controlador.storage_para(self.contenido, self.nodo, self)
        if self.storage is None:
            self._mostrar_bloqueo(
                QCoreApplication.translate(
                    "DialogoTransferencia",
                    "No hay un almacenamiento donde guardar el archivo. Pídele al administrador "
                    "que active este tipo de contenido en un almacenamiento.",
                )
            )
            return False
        self.nodo_destino = elegir_nodo_transferencia(inv, self.storage, self.nodo) or self.nodo
        return True

    def _destino(self, nombre_archivo: str) -> DestinoTransferencia:
        assert self.storage is not None
        return DestinoTransferencia(
            nodo=self.nodo_destino,
            storage=self.storage,
            contenido=self.contenido,
            nombre_archivo=nombre_archivo,
        )

    def _lanzar_comprobacion(self, nombre: str, tamano: int | None, para_subida: bool) -> None:
        inv = self._controlador.inventario
        if inv is None or self.storage is None:
            return
        self._generacion += 1
        generacion = self._generacion
        self._fase = _Fase.PREPARANDO
        self._reiniciar_comprobacion()
        poner_mensaje(
            self.mensaje_comprobacion,
            QCoreApplication.translate("DialogoTransferencia", "Comprobando el destino…"),
            aviso=True,
        )
        destino = self._destino(nombre)
        servicio = self._controlador.servicio_transferencias

        def _al_terminar(comp: object) -> None:
            if (
                generacion == self._generacion
                and not self._cerrado
                and isinstance(comp, ComprobacionPrevia)
            ):
                self._aplicar_comprobacion(comp, nombre, tamano)

        def _al_fallar(error: ErrorProxLaunch) -> None:
            if generacion == self._generacion and not self._cerrado:
                self._mostrar_bloqueo(texto_error(error))

        self._controlador.lanzador.lanzar(
            servicio.comprobar,
            destino,
            tamano,
            inv,
            para_subida=para_subida,
            al_terminar=_al_terminar,
            al_fallar=_al_fallar,
        )

    def _reiniciar_comprobacion(self) -> None:
        self._comprobacion = None
        self.fila_existente.hide()
        self.casilla_raiz.hide()
        self.casilla_raiz.setChecked(False)
        self.etiqueta_resumen.hide()
        self.boton_accion.setEnabled(False)

    def _aplicar_comprobacion(
        self, comp: ComprobacionPrevia, nombre: str, tamano: int | None
    ) -> None:
        """Muestra bloqueos y avisos de ``comprobar`` y, si todo va bien, el resumen."""
        self._comprobacion = comp
        bloqueos: list[str] = []
        avisos: list[str] = []
        existe = comp.volid_existente is not None
        for problema in comp.problemas:
            if problema.codigo == "V-O14":  # el texto necesita el almacenamiento y el nombre
                params = {"storage": self.storage or "", "nombre": nombre, **problema.params}
                problema = dataclasses.replace(problema, params=params)
            if problema.codigo == "V-O13.raiz":
                avisos.append(texto_problema(problema))  # solo avisa: pide la casilla
            elif problema.severidad == Severidad.ERROR:
                bloqueos.append(texto_problema(problema))
        self.fila_existente.setVisible(existe)
        self.casilla_raiz.setVisible(bool(avisos))
        if bloqueos:
            self._mostrar_bloqueo("\n".join(bloqueos))
            if existe:
                self.boton_usar_existente.setDefault(True)
        elif avisos:
            poner_mensaje(self.mensaje_comprobacion, "\n".join(avisos), aviso=True)
        else:
            poner_mensaje(self.mensaje_comprobacion, None)
        if not bloqueos:
            self._mostrar_resumen(nombre, tamano)
            self._fase = _Fase.LISTO
        self._actualizar_botones()

    def _mostrar_bloqueo(self, texto: str) -> None:
        poner_mensaje(self.mensaje_comprobacion, texto)  # estilo de error
        self._fase = _Fase.PREPARANDO
        self.boton_accion.setEnabled(False)

    def _mostrar_resumen(self, nombre: str, tamano: int | None) -> None:
        raise NotImplementedError

    def _actualizar_botones(self) -> None:
        """Activa la acción solo con todo comprobado y, si hay aviso de la raíz, su casilla."""
        listo = self._fase == _Fase.LISTO
        if not self.casilla_raiz.isHidden():
            listo = listo and self.casilla_raiz.isChecked()
        self.boton_accion.setEnabled(listo and self._formulario_valido())

    def _formulario_valido(self) -> bool:
        return True

    def _al_usar_existente(self) -> None:
        if self._comprobacion is None or self._comprobacion.volid_existente is None:
            return
        self.volid_elegido = self._comprobacion.volid_existente
        self.usar_existente.emit(self.volid_elegido)
        self._fase = _Fase.TERMINADO
        self.accept()

    def _al_cambiar_nombre(self) -> None:
        raise NotImplementedError

    # --- Ejecución ----------------------------------------------------------------------

    def _al_pulsar_accion(self) -> None:
        raise NotImplementedError

    def _al_pulsar_cancelar(self) -> None:
        if self._fase == _Fase.EN_CURSO:
            self.cancelar_transferencia()
        elif self._fase == _Fase.TERMINADO:
            self.accept()
        else:
            self.reject()

    def _empezar_en_curso(self) -> None:
        """Pasa a la vista de progreso y arranca el temporizador de refresco."""
        self._fase = _Fase.EN_CURSO
        self._cancelando = False
        self._inicio = time.monotonic()
        self._ultimo_progreso = None
        self._comprobacion = None
        self._congelar_formulario(True)
        self.mensaje_comprobacion.hide()
        self.fila_existente.hide()
        self.casilla_raiz.hide()
        self.boton_accion.hide()
        self.boton_reintentar.hide()
        self.etiqueta_final.hide()
        self.detalles.limpiar()
        self.panel_progreso.show()
        self.etiqueta_estado.setText(texto_estado_transferencia(EstadoTransferencia.COMPROBANDO))
        self.etiqueta_detalle.setText("")
        self._poner_barra_indeterminada()
        self.boton_cancelar.setText(self._texto_boton_cancelar_en_curso())
        self.boton_cancelar.setEnabled(True)
        self.boton_cancelar.setFocus()
        self._temporizador.start()

    def _congelar_formulario(self, congelar: bool) -> None:
        raise NotImplementedError

    def _lanzar_trabajo(self, funcion: Any, *args: Any, **kwargs: Any) -> None:
        """Lanza la transferencia con contexto: recibe el evento de cancelación del trabajador."""

        def _trabajo(*, al_cambiar_etapa: Any, al_enviar: Any, cancelado: threading.Event) -> Any:
            del al_cambiar_etapa, al_enviar
            return funcion(*args, cancelado=cancelado, **kwargs)

        self._trabajador = self._controlador.lanzador.lanzar(
            _trabajo,
            con_contexto=True,
            al_terminar=self._al_terminar_trabajo,
            al_fallar=self._al_fallar_trabajo,
        )

    def _al_terminar_trabajo(self, resultado: object) -> None:
        if self._cerrado or not isinstance(resultado, ResultadoTransferencia):
            return
        self._terminar(resultado)

    def _al_fallar_trabajo(self, error: ErrorProxLaunch) -> None:
        """Error antes de obtener un resultado (p. ej. ``TRANSFERENCIA_EN_CURSO``)."""
        if self._cerrado:
            return
        self._terminar(
            ResultadoTransferencia(
                estado=EstadoTransferencia.FALLIDA,
                volid=None,
                error=error,
                quedo_archivo=None,
                duracion_s=max(0.0, time.monotonic() - self._inicio),
                upid=None,
            )
        )

    def _terminar(self, resultado: ResultadoTransferencia) -> None:
        self._temporizador.stop()
        self._vaciar_progreso()
        self._trabajador = None
        self.resultado = resultado
        self._fase = _Fase.TERMINADO
        self._cancelando = False
        self._congelar_formulario(False)
        self.etiqueta_estado.setText(texto_estado_transferencia(resultado.estado))
        ok = resultado.estado == EstadoTransferencia.TERMINADA
        self.barra.setRange(0, _ESCALA_BARRA)
        self.barra.setValue(_ESCALA_BARRA if ok else self.barra.value())
        self.barra.setFormat("%p%")
        self.etiqueta_detalle.setText(
            QCoreApplication.translate("DialogoTransferencia", "Duración: {tiempo}").format(
                tiempo=texto_tiempo(resultado.duracion_s)
            )
        )
        if ok:
            self.volid_elegido = resultado.volid
        self._mostrar_final(resultado)
        self.boton_cancelar.setText(QCoreApplication.translate("DialogoTransferencia", "Cerrar"))
        self.boton_cancelar.setEnabled(True)
        self.boton_cancelar.setDefault(True)
        self.boton_cancelar.setFocus()
        self.boton_reintentar.setVisible(resultado.estado == EstadoTransferencia.FALLIDA)
        self.terminada.emit(resultado)

    def _mostrar_final(self, resultado: ResultadoTransferencia) -> None:
        """Mensaje final según el estado, con la verdad sobre si quedó un archivo (CA-O12.2)."""
        estado = resultado.estado
        error_visible = False
        if estado == EstadoTransferencia.TERMINADA:
            texto = QCoreApplication.translate(
                "DialogoTransferencia", "Listo. El archivo «{volid}» está en el servidor."
            ).format(volid=resultado.volid or "")
        elif estado == EstadoTransferencia.CANCELADA:
            texto = self._texto_cancelada(resultado)
        elif estado == EstadoTransferencia.SIN_ESPERAR and self.tipo == TipoTransferencia.SUBIDA:
            texto = QCoreApplication.translate(
                "DialogoTransferencia",
                "Dejaste de esperar. El archivo ya se envió y el servidor sigue copiándolo: no "
                "se puede cancelar desde ProxLaunch y puede aparecer en el catálogo cuando "
                "termine. Revísalo allí más tarde.",
            )
        elif estado == EstadoTransferencia.SIN_ESPERAR:
            texto = QCoreApplication.translate(
                "DialogoTransferencia",
                "La descarga sigue en el servidor y no se puede cancelar desde ProxLaunch. "
                "Cuando termine, abre el catálogo para ver el resultado.",
            )
        else:
            error_visible = True
            texto = (
                texto_error(resultado.error)
                if resultado.error is not None
                else QCoreApplication.translate("DialogoTransferencia", "La transferencia falló.")
            )
            if resultado.quedo_archivo is not None:
                texto += "\n" + texto_quedo_archivo(resultado.quedo_archivo)
        if estado == EstadoTransferencia.TERMINADA:
            tono = "exito"
        elif error_visible:
            tono = "error"
        else:
            tono = "aviso"
        for nombre in ("exito", "aviso", "error"):
            poner_propiedad(self.etiqueta_final, nombre, nombre == tono)
        self.etiqueta_final.setText(texto)
        self.etiqueta_final.show()
        if error_visible and resultado.error is not None:
            self.detalles.establecer(texto_detalles(resultado.error))

    def _texto_cancelada(self, resultado: ResultadoTransferencia) -> str:
        if resultado.quedo_archivo is False:
            return QCoreApplication.translate(
                "DialogoTransferencia", "Se canceló. No se guardó ningún archivo."
            )
        if resultado.quedo_archivo:
            return QCoreApplication.translate(
                "DialogoTransferencia",
                "Se canceló, pero el archivo parcial quedó guardado: pídele al administrador "
                "que lo borre.",
            )
        return QCoreApplication.translate(
            "DialogoTransferencia",
            "Se canceló. No se pudo comprobar si quedó algún archivo a medias: míralo en el "
            "catálogo del servidor.",
        )

    def _reintentar(self) -> None:
        """Vuelve al formulario y repite las comprobaciones (también el nombre, RF-O10)."""
        self._fase = _Fase.PREPARANDO
        self.resultado = None
        self.panel_progreso.hide()
        self.etiqueta_final.hide()
        self.detalles.limpiar()
        self.boton_reintentar.hide()
        self.boton_accion.show()
        self.boton_cancelar.setText(QCoreApplication.translate("DialogoTransferencia", "Cancelar"))
        self._congelar_formulario(False)
        self._volver_a_comprobar()
        self.boton_cancelar.setFocus()

    def _volver_a_comprobar(self) -> None:
        raise NotImplementedError

    # --- Progreso -----------------------------------------------------------------------

    def _poner_barra_indeterminada(self) -> None:
        self.barra.setRange(0, 0)
        self.barra.setFormat("")

    def _vaciar_progreso(self) -> None:
        progreso = self._puente.tomar()
        if progreso is not None:
            self._mostrar_progreso(progreso)
        elif self._fase == _Fase.EN_CURSO:
            self._refrescar_tiempo()

    def _refrescar_tiempo(self) -> None:
        """Sin datos de bytes (descarga del servidor) se muestra el tiempo transcurrido."""
        p = self._ultimo_progreso
        if p is not None and not p.total_bytes and p.porcentaje_servidor is None:
            self.etiqueta_detalle.setText(
                QCoreApplication.translate(
                    "DialogoTransferencia", "Tiempo transcurrido: {tiempo}"
                ).format(tiempo=texto_tiempo(time.monotonic() - self._inicio))
            )

    def _mostrar_progreso(self, progreso: Progreso) -> None:
        """Barra y textos; el porcentaje solo sale de bytes reales o del que informa el servidor."""
        self._ultimo_progreso = progreso
        if not self._cancelando:
            self.etiqueta_estado.setText(texto_progreso_transferencia(progreso))
            # La subida que ya envió todo cambia «Cancelar subida» por «Dejar de esperar».
            self.boton_cancelar.setText(self._texto_boton_cancelar_en_curso())
        fraccion: float | None = None
        if progreso.estado in (
            EstadoTransferencia.CALCULANDO_HUELLA,
            EstadoTransferencia.TRANSFIRIENDO,
        ):
            if progreso.total_bytes:
                fraccion = progreso.hechos_bytes / progreso.total_bytes
        elif progreso.porcentaje_servidor is not None:
            fraccion = progreso.porcentaje_servidor / 100.0
        elif progreso.estado == EstadoTransferencia.VERIFICANDO:
            fraccion = 1.0
        if fraccion is None:
            self._poner_barra_indeterminada()
            self.etiqueta_detalle.setText(
                QCoreApplication.translate(
                    "DialogoTransferencia", "Tiempo transcurrido: {tiempo}"
                ).format(tiempo=texto_tiempo(time.monotonic() - self._inicio))
            )
        else:
            self.barra.setRange(0, _ESCALA_BARRA)
            self.barra.setValue(int(max(0.0, min(1.0, fraccion)) * _ESCALA_BARRA))
            self.barra.setFormat("%p%")
            self.etiqueta_detalle.setText("")
        self.barra.setAccessibleDescription(
            f"{self.etiqueta_estado.text()}. {self.etiqueta_detalle.text()}"
        )


# --- Subida -----------------------------------------------------------------------------


def _motivo_rechazo_archivo(motivo: str) -> str:
    """Texto del rechazo local de un archivo a subir (V-O10, CA-O16.2/3)."""
    if motivo == archivo_local.MOTIVO_VACIO:
        return QCoreApplication.translate("DialogoTransferencia", "El archivo está vacío.")
    return texto_error(ErrorProxLaunch(CodigoError.IMAGEN_NO_ADMITIDA, {"motivo": motivo}))


class DialogoSubida(_DialogoTransferencia):
    """Sube un ISO o una imagen de disco del equipo al servidor.

    ``ruta`` (opcional) salta el selector de archivo (útil en pruebas). Al terminar con éxito
    ``volid_elegido`` y ``resultado.volid`` llevan el volumen; si el usuario elige «Usar el
    existente» ``volid_elegido`` es ese volumen y ``resultado`` queda en ``None``.
    """

    tipo = TipoTransferencia.SUBIDA

    def __init__(
        self,
        controlador: ControladorTransferencia,
        contenido: Contenido,
        nodo: str,
        parent: QWidget | None = None,
        *,
        ruta: Path | None = None,
    ) -> None:
        super().__init__(controlador, contenido, nodo, parent)
        self._ruta: Path | None = None
        self._inspeccion: InspeccionArchivo | None = None
        self.setWindowTitle(
            self.tr("Subir un ISO desde mi equipo")
            if contenido == Contenido.ISO
            else self.tr("Subir un disco desde mi equipo")
        )
        self.boton_accion.setText(self.tr("Subir"))

        self.campo_archivo = QLineEdit()
        self.campo_archivo.setReadOnly(True)
        self.campo_archivo.setPlaceholderText(self.tr("Ningún archivo elegido"))
        self.campo_archivo.setAccessibleName(self.tr("Archivo elegido"))
        self.boton_elegir = QPushButton(self.tr("Elegir archivo…"))
        self.boton_elegir.setAutoDefault(False)
        self.boton_elegir.clicked.connect(self._elegir_archivo)
        fila_archivo = QHBoxLayout()
        fila_archivo.addWidget(self.campo_archivo, 1)
        fila_archivo.addWidget(self.boton_elegir)

        self.etiqueta_info = QLabel()
        self.etiqueta_info.setWordWrap(True)
        self.etiqueta_info.setTextFormat(Qt.TextFormat.PlainText)
        self.etiqueta_info.setAccessibleName(self.tr("Datos del archivo"))
        self.etiqueta_info.hide()

        self.campo_nombre = QLineEdit()
        self.campo_nombre.setAccessibleName(self.tr("Nombre del archivo en el servidor"))
        self.campo_nombre.setEnabled(False)
        self.campo_nombre.textChanged.connect(self._al_editar_nombre)
        self.campo_nombre.editingFinished.connect(self._volver_a_comprobar)
        self.error_nombre = QLabel()
        self.error_nombre.setWordWrap(True)
        self.error_nombre.setProperty("error", True)
        self.error_nombre.hide()

        formulario = QFormLayout()
        formulario.addRow(self.tr("Archivo del equipo"), fila_archivo)
        formulario.addRow(self.tr("Nombre en el servidor"), self.campo_nombre)
        self._capa.addLayout(formulario)
        self._capa.addWidget(self.etiqueta_info)
        self._capa.addWidget(self.error_nombre)
        self._terminar_diseno()

        if ruta is not None:
            self.elegir_ruta(ruta)

    # --- API pública --------------------------------------------------------------------

    @property
    def nombre_final(self) -> str:
        """Nombre con el que quedará el archivo en el servidor."""
        return self.campo_nombre.text().strip()

    def elegir_ruta(self, ruta: Path) -> None:
        """Elige el archivo a subir y lo inspecciona (E/S mínima, fuera del hilo de la interfaz)."""
        self._ruta = Path(ruta)
        self._inspeccion = None
        self.campo_archivo.setText(self._ruta.name)  # nunca se muestra la ruta completa
        self.campo_nombre.setEnabled(False)
        self._generacion += 1
        generacion = self._generacion
        self._fase = _Fase.PREPARANDO
        self._reiniciar_comprobacion()
        poner_mensaje(self.mensaje_comprobacion, self.tr("Leyendo el archivo…"), aviso=True)

        def _al_terminar(insp: object) -> None:
            vigente = generacion == self._generacion and not self._cerrado
            if vigente and isinstance(insp, InspeccionArchivo):
                self._al_inspeccionar(insp)

        def _al_fallar(error: ErrorProxLaunch) -> None:
            if generacion == self._generacion and not self._cerrado:
                self.etiqueta_info.hide()
                self._mostrar_bloqueo(texto_error(error))

        self._controlador.lanzador.lanzar(
            inspeccionar,
            self._ruta,
            self.contenido,
            al_terminar=_al_terminar,
            al_fallar=_al_fallar,
        )

    # --- Flujo --------------------------------------------------------------------------

    def _elegir_archivo(self) -> None:
        if self._fase == _Fase.EN_CURSO:
            return
        if self.contenido == Contenido.ISO:
            filtro = self.tr("Imágenes ISO (*.iso *.img);;Todos los archivos (*)")
        else:
            filtro = self.tr("Discos (*.qcow2 *.vmdk *.raw *.img);;Todos los archivos (*)")
        ruta, _filtro = QFileDialog.getOpenFileName(self, self.tr("Elegir archivo"), "", filtro)
        if ruta:
            self.elegir_ruta(Path(ruta))

    def _al_inspeccionar(self, insp: InspeccionArchivo) -> None:
        self._inspeccion = insp
        lineas = [
            self.tr("{nombre} · {tamano}").format(
                nombre=insp.nombre_local, tamano=formatear_bytes(insp.tamano_bytes)
            )
        ]
        lineas.extend(texto_aviso_archivo_local(a) for a in insp.avisos)
        self.etiqueta_info.setText("\n".join(lineas))
        self.etiqueta_info.show()
        if insp.motivo_rechazo is not None:
            self._mostrar_bloqueo(_motivo_rechazo_archivo(insp.motivo_rechazo))
            return
        stem = Path(insp.nombre_local).stem
        propuesto = sanear_nombre_archivo(stem + insp.extension_propuesta, self.contenido)
        self.campo_nombre.setEnabled(True)
        self.campo_nombre.blockSignals(True)
        self.campo_nombre.setText(propuesto)
        self.campo_nombre.blockSignals(False)
        self.error_nombre.hide()
        self._volver_a_comprobar()

    def _al_editar_nombre(self, _texto: str) -> None:
        motivo = validar_nombre_archivo(self.nombre_final, self.contenido)
        if motivo is None:
            self.error_nombre.hide()
        else:
            self.error_nombre.setText(texto_motivo_nombre_archivo(motivo, self.contenido))
            self.error_nombre.show()
        # Cualquier cambio invalida lo comprobado hasta ahora.
        self._generacion += 1
        self._fase = _Fase.PREPARANDO
        self._reiniciar_comprobacion()

    def _formulario_valido(self) -> bool:
        return (
            self._inspeccion is not None
            and self._inspeccion.motivo_rechazo is None
            and validar_nombre_archivo(self.nombre_final, self.contenido) is None
        )

    def _volver_a_comprobar(self) -> None:
        """Resuelve el destino y comprueba nombre, espacio y permisos con solo lecturas."""
        insp = self._inspeccion
        if insp is None or insp.motivo_rechazo is not None or self._fase == _Fase.EN_CURSO:
            return
        if validar_nombre_archivo(self.nombre_final, self.contenido) is not None:
            return
        if not self._resolver_destino():
            return
        self._lanzar_comprobacion(self.nombre_final, insp.tamano_bytes, para_subida=True)

    def _mostrar_resumen(self, nombre: str, tamano: int | None) -> None:
        self.etiqueta_resumen.setText(
            self.tr(
                "Se subirá «{nombre}» ({tamano}) al almacenamiento «{storage}» del nodo «{nodo}»."
            ).format(
                nombre=nombre,
                tamano=formatear_bytes(tamano),
                storage=self.storage or "",
                nodo=self.nodo_destino,
            )
        )
        self.etiqueta_resumen.show()

    def _al_cambiar_nombre(self) -> None:
        self.campo_nombre.setFocus()
        self.campo_nombre.selectAll()

    def _congelar_formulario(self, congelar: bool) -> None:
        self.campo_nombre.setEnabled(not congelar and self._inspeccion is not None)
        self.boton_elegir.setEnabled(not congelar)

    def _esperando_servidor(self) -> bool:
        p = self._ultimo_progreso
        return p is not None and p.estado in _ESTADOS_ESPERA_SERVIDOR

    def _texto_cancelando(self) -> str:
        if self._esperando_servidor():
            return self.tr("Dejando de esperar…")
        return self.tr("Cancelando…")

    def _texto_boton_cancelar_en_curso(self) -> str:
        if self._esperando_servidor():
            return self.tr("Dejar de esperar")
        return self.tr("Cancelar subida")

    def _al_pulsar_accion(self) -> None:
        if not self.listo_para_confirmar or self._ruta is None or self._inspeccion is None:
            return
        inv = self._controlador.inventario
        if inv is None or self.storage is None:
            return
        destino = self._destino(self.nombre_final)
        servicio = self._controlador.servicio_transferencias
        acepta_raiz = self.casilla_raiz.isChecked()
        puente = self._puente
        self._empezar_en_curso()
        self._lanzar_trabajo(
            servicio.subir,
            self._ruta,
            destino,
            inv,
            al_progresar=puente.observar,
            acepta_aviso_raiz=acepta_raiz,
        )


# --- Descarga por URL ---------------------------------------------------------------------


class DialogoDescarga(_DialogoTransferencia):
    """Hace que el servidor descargue una URL en su almacenamiento.

    ProxLaunch nunca abre esa dirección: pregunta al servidor qué ve («Comprobar») y le pide
    descargarla. La descarga no se puede cancelar desde la aplicación, solo «Dejar de esperar».
    ``url_inicial``/``checksum_inicial`` permiten preparar una descarga fija (p. ej. virtio-win)
    con ``url_fija=True`` para impedir editarlas.
    """

    tipo = TipoTransferencia.DESCARGA

    def __init__(
        self,
        controlador: ControladorTransferencia,
        contenido: Contenido,
        nodo: str,
        parent: QWidget | None = None,
        *,
        url_inicial: str = "",
        checksum_inicial: str = "",
        nombre_inicial: str = "",
        url_fija: bool = False,
    ) -> None:
        super().__init__(controlador, contenido, nodo, parent)
        self._url: UrlDescarga | None = None
        self._checksum: ChecksumTransferencia | None = None
        self._metadatos: MetadatosUrl | None = None
        # Riesgos ya confirmados (URL, ¿http?, ¿verifica certificados?): no se vuelve a preguntar
        # al descargar mientras no cambie nada de eso.
        self._riesgos_confirmados: tuple[str, bool, bool] | None = None
        self._nombre_inicial = nombre_inicial
        self.setWindowTitle(
            self.tr("Descargar un ISO en el servidor")
            if contenido == Contenido.ISO
            else self.tr("Descargar un disco en el servidor")
        )
        self.boton_accion.setText(self.tr("Descargar"))
        avanzado = bool(controlador.modo_avanzado)

        self.campo_url = QLineEdit(url_inicial)
        self.campo_url.setPlaceholderText(self.tr("https://…"))
        self.campo_url.setAccessibleName(self.tr("Dirección web del archivo"))
        self.campo_url.setReadOnly(url_fija)
        self.campo_url.textChanged.connect(self._invalidar)
        self.boton_comprobar = QPushButton(self.tr("Comprobar"))
        self.boton_comprobar.setAutoDefault(False)
        self.boton_comprobar.clicked.connect(self.comprobar_url)
        fila_url = QHBoxLayout()
        fila_url.addWidget(self.campo_url, 1)
        fila_url.addWidget(self.boton_comprobar)

        self.campo_checksum = QLineEdit(checksum_inicial)
        self.campo_checksum.setPlaceholderText(self.tr("Opcional: huella (sha256, sha512…)"))
        self.campo_checksum.setAccessibleName(self.tr("Huella para verificar el archivo"))
        self.campo_checksum.setReadOnly(url_fija)
        self.campo_checksum.textChanged.connect(self._invalidar)

        self.campo_nombre = QLineEdit(nombre_inicial)
        self.campo_nombre.setAccessibleName(self.tr("Nombre del archivo en el servidor"))
        self.campo_nombre.setEnabled(False)
        self.campo_nombre.textChanged.connect(self._al_editar_nombre)
        self.campo_nombre.editingFinished.connect(self._volver_a_comprobar)

        self.casilla_certificados = QCheckBox(
            self.tr("Comprobar el certificado del servidor web (recomendado)")
        )
        self.casilla_certificados.setChecked(True)
        self.casilla_certificados.setVisible(avanzado)
        self.casilla_certificados.setAccessibleName(self.tr("Comprobar el certificado"))
        self.casilla_certificados.toggled.connect(self._invalidar)

        self.error_campos = QLabel()
        self.error_campos.setWordWrap(True)
        self.error_campos.setProperty("error", True)
        self.error_campos.hide()

        # Avisos que no bloquean (IP interna, puerto raro, huella antigua).
        self.avisos_descarga = QLabel()
        self.avisos_descarga.setWordWrap(True)
        self.avisos_descarga.setTextFormat(Qt.TextFormat.PlainText)
        self.avisos_descarga.setAccessibleName(self.tr("Avisos de la descarga"))
        self.avisos_descarga.hide()

        self.etiqueta_metadatos = QLabel()
        self.etiqueta_metadatos.setWordWrap(True)
        self.etiqueta_metadatos.setTextFormat(Qt.TextFormat.PlainText)
        self.etiqueta_metadatos.setAccessibleName(self.tr("Lo que ve el servidor"))
        self.etiqueta_metadatos.hide()

        self.aviso_no_se_cancela = QLabel(
            self.tr(
                "La descarga la hace el servidor: una vez empezada, no se puede cancelar desde "
                "ProxLaunch. Solo puedes dejar de esperar."
            )
        )
        self.aviso_no_se_cancela.setWordWrap(True)
        self.aviso_no_se_cancela.setProperty("secundario", True)

        self.nota_registro = QLabel(
            self.tr("La dirección quedará en el registro de tareas del servidor.")
        )
        self.nota_registro.setWordWrap(True)
        self.nota_registro.setProperty("secundario", True)

        formulario = QFormLayout()
        formulario.addRow(self.tr("Dirección web"), fila_url)
        formulario.addRow(self.tr("Huella"), self.campo_checksum)
        formulario.addRow(self.tr("Nombre en el servidor"), self.campo_nombre)
        self._capa.addLayout(formulario)
        self._capa.addWidget(self.casilla_certificados)
        self._capa.addWidget(self.error_campos)
        self._capa.addWidget(self.avisos_descarga)
        self._capa.addWidget(self.etiqueta_metadatos)
        self._capa.addWidget(self.aviso_no_se_cancela)
        self._capa.addWidget(self.nota_registro)
        self._terminar_diseno()

    # --- API pública --------------------------------------------------------------------

    @property
    def nombre_final(self) -> str:
        return self.campo_nombre.text().strip()

    @property
    def verificar_certificados(self) -> bool:
        """``False`` solo si, en modo avanzado, se desmarcó la casilla (con confirmación)."""
        return self.casilla_certificados.isChecked()

    def comprobar_url(self) -> None:
        """Valida URL y huella y le pregunta al servidor qué ve (nombre, tamaño, tipo)."""
        if self._fase == _Fase.EN_CURSO:
            return
        avanzado = bool(self._controlador.modo_avanzado)
        url, motivo = validar_url(self.campo_url.text(), permitir_http=avanzado)
        if url is None:
            self._mostrar_error_campos(texto_motivo_url(motivo or ""))
            return
        texto_huella = self.campo_checksum.text().strip()
        checksum: ChecksumTransferencia | None = None
        if texto_huella:
            checksum, motivo_huella = validar_checksum(texto_huella)
            if checksum is None:
                self._mostrar_error_campos(texto_motivo_checksum(motivo_huella or ""))
                return
        self.error_campos.hide()
        # Consultar también hace que el servidor se conecte a la dirección: mismas confirmaciones
        # de riesgo que la descarga (http:// o certificado sin verificar).
        if not self._confirmar_riesgos(consulta=True, url=url):
            return
        self._url = url
        self._checksum = checksum
        avisos = _avisos_url(url)
        aviso_huella = _aviso_checksum(checksum)
        if aviso_huella is not None:
            avisos.append(aviso_huella)
        poner_mensaje(self.avisos_descarga, "\n".join(avisos), aviso=True)
        if not self._resolver_destino():
            return
        inv = self._controlador.inventario
        if inv is None:
            return
        self._generacion += 1
        generacion = self._generacion
        self._fase = _Fase.PREPARANDO
        self._reiniciar_comprobacion()
        self.etiqueta_metadatos.hide()
        poner_mensaje(
            self.mensaje_comprobacion,
            self.tr("Preguntando al servidor por «{host}/{archivo}»…").format(
                host=url.host, archivo=url.archivo
            ),
            aviso=True,
        )
        servicio = self._controlador.servicio_transferencias

        def _al_terminar(meta: object) -> None:
            vigente = generacion == self._generacion and not self._cerrado
            if vigente and isinstance(meta, MetadatosUrl):
                self._al_obtener_metadatos(url, meta)

        def _al_fallar(error: ErrorProxLaunch) -> None:
            if generacion == self._generacion and not self._cerrado:
                self._mostrar_bloqueo(texto_error(error))

        self._controlador.lanzador.lanzar(
            servicio.consultar_url,
            self.nodo_destino,
            url,
            verificar_certificados=self.verificar_certificados,
            al_terminar=_al_terminar,
            al_fallar=_al_fallar,
        )

    # --- Flujo --------------------------------------------------------------------------

    def _mostrar_error_campos(self, texto: str) -> None:
        self.error_campos.setText(texto)
        self.error_campos.show()
        self._invalidar()

    def _invalidar(self, *_args: object) -> None:
        """Cualquier cambio de URL, huella o certificados exige volver a «Comprobar»."""
        if self._fase == _Fase.EN_CURSO:
            return
        self._generacion += 1
        self._metadatos = None
        self._fase = _Fase.PREPARANDO
        self._reiniciar_comprobacion()
        self.etiqueta_metadatos.hide()
        poner_mensaje(self.avisos_descarga, None)
        self.campo_nombre.setEnabled(False)

    def _al_obtener_metadatos(self, url: UrlDescarga, meta: MetadatosUrl) -> None:
        self._metadatos = meta
        lineas = [
            self.tr("El servidor ve: «{host}/{archivo}»").format(host=url.host, archivo=url.archivo)
        ]
        lineas.append(
            self.tr("Nombre: {nombre}").format(nombre=meta.nombre or self.tr("no indicado"))
        )
        lineas.append(self.tr("Tamaño: {tamano}").format(tamano=formatear_bytes(meta.tamano)))
        if meta.tipo_mime:
            lineas.append(self.tr("Tipo: {tipo}").format(tipo=meta.tipo_mime))
        self.etiqueta_metadatos.setText("\n".join(lineas))
        self.etiqueta_metadatos.show()
        base = self._nombre_inicial or meta.nombre or url.archivo or "descarga"
        self.campo_nombre.setEnabled(True)
        self.campo_nombre.blockSignals(True)
        self.campo_nombre.setText(sanear_nombre_archivo(base, self.contenido))
        self.campo_nombre.blockSignals(False)
        self._volver_a_comprobar()

    def _al_editar_nombre(self, _texto: str) -> None:
        self._generacion += 1
        self._fase = _Fase.PREPARANDO
        self._reiniciar_comprobacion()

    def _formulario_valido(self) -> bool:
        return (
            self._url is not None
            and self._metadatos is not None
            and validar_nombre_archivo(self.nombre_final, self.contenido) is None
        )

    def _volver_a_comprobar(self) -> None:
        if self._fase == _Fase.EN_CURSO or self._url is None or self._metadatos is None:
            return
        motivo = validar_nombre_archivo(self.nombre_final, self.contenido)
        if motivo is not None:
            self._mostrar_bloqueo(texto_motivo_nombre_archivo(motivo, self.contenido))
            return
        if self.storage is None and not self._resolver_destino():
            return
        self._lanzar_comprobacion(self.nombre_final, self._metadatos.tamano, para_subida=False)

    def _mostrar_resumen(self, nombre: str, tamano: int | None) -> None:
        self.etiqueta_resumen.setText(
            self.tr(
                "El servidor descargará «{nombre}» ({tamano}) en el almacenamiento «{storage}» "
                "del nodo «{nodo}»."
            ).format(
                nombre=nombre,
                tamano=formatear_bytes(tamano),
                storage=self.storage or "",
                nodo=self.nodo_destino,
            )
        )
        self.etiqueta_resumen.show()

    def _al_cambiar_nombre(self) -> None:
        self.campo_nombre.setFocus()
        self.campo_nombre.selectAll()

    def _congelar_formulario(self, congelar: bool) -> None:
        self.campo_url.setEnabled(not congelar)
        self.campo_checksum.setEnabled(not congelar)
        self.boton_comprobar.setEnabled(not congelar)
        self.campo_nombre.setEnabled(not congelar and self._metadatos is not None)
        self.casilla_certificados.setEnabled(not congelar)

    def _texto_cancelando(self) -> str:
        return self.tr("Dejando de esperar…")

    def _texto_boton_cancelar_en_curso(self) -> str:
        return self.tr("Dejar de esperar")

    def _confirmar_riesgos(self, *, consulta: bool = False, url: UrlDescarga | None = None) -> bool:
        """Pide confirmar ``http://`` o certificados sin verificar (DT-O7, CA-O11.3/O11.4).

        También se pide al «Comprobar» (``consulta``): el servidor se conecta a la dirección
        con esas mismas condiciones, así que no se consulta sin la misma confirmación.
        """
        url = url or self._url
        riesgos: list[str] = []
        if url is not None and url.es_http:
            riesgos.append(
                self.tr(
                    "La dirección usa http://: no se puede garantizar que el archivo no fue "
                    "alterado por el camino. Conviene indicar la huella."
                )
            )
        if not self.verificar_certificados:
            riesgos.append(
                self.tr(
                    "No se comprobará el certificado del servidor web: podrías descargar un "
                    "archivo de un sitio falso."
                )
            )
        if not riesgos:
            return True
        clave = (
            url.texto if url is not None else "",
            bool(url and url.es_http),
            self.verificar_certificados,
        )
        if self._riesgos_confirmados == clave:
            return True
        if consulta:
            aceptado = confirmar(
                self,
                self.tr("Consulta con riesgo"),
                "\n\n".join(riesgos),
                self.tr("Consultar de todos modos"),
                self.tr("Cancelar"),
            )
        else:
            aceptado = confirmar(
                self,
                self.tr("Descarga con riesgo"),
                "\n\n".join(riesgos),
                self.tr("Descargar de todos modos"),
                self.tr("Cancelar"),
            )
        if aceptado:
            self._riesgos_confirmados = clave
        return aceptado

    def _al_pulsar_accion(self) -> None:
        if not self.listo_para_confirmar or self._url is None:
            return
        inv = self._controlador.inventario
        if inv is None or self.storage is None:
            return
        if not self._confirmar_riesgos():
            return
        destino = self._destino(self.nombre_final)
        servicio = self._controlador.servicio_transferencias
        puente = self._puente
        self._empezar_en_curso()

        def _descargar(*, cancelado: threading.Event) -> ResultadoTransferencia:
            assert self._url is not None
            return servicio.descargar(
                self._url,
                destino,
                inv,
                checksum=self._checksum,
                verificar_certificados=self.verificar_certificados,
                al_progresar=puente.observar,
                dejar_de_esperar=cancelado,
            )

        self._lanzar_trabajo(_descargar)
