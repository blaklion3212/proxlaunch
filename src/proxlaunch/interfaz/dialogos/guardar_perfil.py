"""Diálogos para poner nombre a un perfil de máquina: guardar, renombrar y duplicar.

``DialogoGuardarPerfil`` toma la configuración del formulario, comprueba la capa 1 y crea el
perfil en el almacén (RF-P03). ``DialogoNombrePerfil`` solo pide nombre (y descripción) y deja
la operación a quien lo llama: se usa para renombrar y duplicar desde el gestor (RF-P04).
El almacén se usa en el hilo de la interfaz (§10 de la arquitectura del MVP 3).
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.archivos_ui import boton_ayuda_texto
from proxlaunch.interfaz.textos import (
    texto_fallo,
    texto_problema,
    texto_regla_perfil,
    texto_resumen_perfil,
)
from proxlaunch.interfaz.vistas.campos import etiqueta, mensaje, poner_mensaje, poner_propiedad
from proxlaunch.nucleo.archivos.constantes import LONG_DESCRIPCION, MAX_PERFILES_USUARIO
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.aplicar import config_desde_configuracion
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil, OrigenPerfil, PerfilMaquina
from proxlaunch.nucleo.perfiles_maquina.validacion import (
    nombre_libre,
    validar_config_perfil,
    validar_descripcion,
    validar_nombre_perfil,
)
from proxlaunch.nucleo.validacion import Severidad


def _texto_solo_lectura() -> str:
    return QCoreApplication.translate(
        "DialogoGuardarPerfil",
        "Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden modificar.",
    )


class _DialogoBaseNombre(QDialog):
    """Nombre y descripción con validación en vivo (V-M01, V-M04, V-M05) y botón Aceptar."""

    _errores_capa1: tuple[str, ...] = ()

    def __init__(
        self,
        existentes: Sequence[PerfilMaquina],
        *,
        titulo: str,
        texto_aceptar: str,
        nombre_inicial: str,
        descripcion_inicial: str | None,
        excluir_id: str | None = None,
        bloqueo: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(480)
        self._existentes = tuple(existentes)
        self._excluir_id = excluir_id
        self._bloqueo = bloqueo
        self._nombre_tocado = False
        self.capa = QVBoxLayout(self)

        self.aviso_bloqueo = mensaje(error=True)
        self.capa.addWidget(self.aviso_bloqueo)

        self.campo_nombre = QLineEdit(nombre_inicial)
        self.campo_nombre.setAccessibleName(
            QCoreApplication.translate("DialogoGuardarPerfil", "Nombre del perfil")
        )
        self.campo_nombre.setPlaceholderText(
            QCoreApplication.translate("DialogoGuardarPerfil", "Por ejemplo: Servidor web")
        )
        etiqueta_nombre = QLabel(
            QCoreApplication.translate("DialogoGuardarPerfil", "Nombre del perfil")
        )
        etiqueta_nombre.setBuddy(self.campo_nombre)
        self.error_nombre = mensaje(error=True)
        self.capa.addWidget(etiqueta_nombre)
        self.capa.addWidget(self.campo_nombre)
        self.capa.addWidget(self.error_nombre)

        self.campo_descripcion: QPlainTextEdit | None = None
        self.error_descripcion = mensaje(error=True)
        if descripcion_inicial is not None:
            self.campo_descripcion = QPlainTextEdit(descripcion_inicial)
            self.campo_descripcion.setFixedHeight(70)
            self.campo_descripcion.setAccessibleName(
                QCoreApplication.translate("DialogoGuardarPerfil", "Descripción del perfil")
            )
            self.campo_descripcion.setPlaceholderText(
                QCoreApplication.translate(
                    "DialogoGuardarPerfil",
                    "Opcional: para qué sirve este perfil (hasta {n} caracteres)",
                ).format(n=LONG_DESCRIPCION)
            )
            etiqueta_desc = QLabel(
                QCoreApplication.translate("DialogoGuardarPerfil", "Descripción (opcional)")
            )
            etiqueta_desc.setBuddy(self.campo_descripcion)
            self.capa.addWidget(etiqueta_desc)
            self.capa.addWidget(self.campo_descripcion)
            self.capa.addWidget(self.error_descripcion)
            self.campo_descripcion.textChanged.connect(self._revisar)

        self.zona_extra = QVBoxLayout()
        self.capa.addLayout(self.zona_extra)
        self.error_general = mensaje(error=True)
        self.capa.addWidget(self.error_general)

        self.botones = QDialogButtonBox()
        self.boton_aceptar = QPushButton(texto_aceptar)
        self.boton_cancelar = QPushButton(
            QCoreApplication.translate("DialogoGuardarPerfil", "Cancelar")
        )
        self.botones.addButton(self.boton_aceptar, QDialogButtonBox.ButtonRole.AcceptRole)
        self.botones.addButton(self.boton_cancelar, QDialogButtonBox.ButtonRole.RejectRole)
        self.boton_aceptar.setDefault(True)
        self.boton_aceptar.setProperty("primario", True)
        self.botones.accepted.connect(self._al_aceptar)
        self.botones.rejected.connect(self.reject)
        self.capa.addWidget(self.botones)

        self.campo_nombre.textChanged.connect(self._al_editar_nombre)
        self.campo_nombre.selectAll()
        self.campo_nombre.setFocus()

    # --- Datos validados -------------------------------------------------------------

    @property
    def nombre(self) -> str:
        """Nombre normalizado (recortado, NFC) tal como se guardará."""
        return validar_nombre_perfil(self.campo_nombre.text(), self._existentes)[0]

    @property
    def descripcion(self) -> str:
        """Descripción normalizada (vacía si el campo no se muestra)."""
        if self.campo_descripcion is None:
            return ""
        return validar_descripcion(self.campo_descripcion.toPlainText())[0]

    # --- Validación ------------------------------------------------------------------

    def _al_editar_nombre(self) -> None:
        self._nombre_tocado = True
        self._revisar()

    def _problema_nombre(self) -> str | None:
        _norm, problemas = validar_nombre_perfil(
            self.campo_nombre.text(), self._existentes, excluir_id=self._excluir_id
        )
        if not problemas:
            return None
        p = problemas[0]
        return texto_regla_perfil(p.codigo, p.campo)

    def _problema_descripcion(self) -> str | None:
        if self.campo_descripcion is None:
            return None
        _texto, problemas = validar_descripcion(self.campo_descripcion.toPlainText())
        if not problemas:
            return None
        return texto_regla_perfil(
            problemas[0].codigo, QCoreApplication.translate("DialogoGuardarPerfil", "descripción")
        )

    def _revisar(self) -> None:
        """Muestra los errores y habilita Aceptar solo si todo es válido."""
        problema_nombre = self._problema_nombre()
        problema_desc = self._problema_descripcion()
        poner_mensaje(self.error_nombre, problema_nombre if self._nombre_tocado else None)
        poner_propiedad(
            self.campo_nombre, "invalido", bool(problema_nombre) and self._nombre_tocado
        )
        poner_mensaje(self.error_descripcion, problema_desc)
        poner_mensaje(self.aviso_bloqueo, self._bloqueo)
        self.boton_aceptar.setEnabled(
            problema_nombre is None and problema_desc is None and self._bloqueo is None
        )

    def _al_aceptar(self) -> None:
        self.accept()


class DialogoNombrePerfil(_DialogoBaseNombre):
    """Pide un nombre (y opcionalmente una descripción) para renombrar o duplicar.

    Atributos tras aceptar: ``nombre`` y ``descripcion``. El diálogo no toca el almacén.
    ``descripcion_inicial=None`` oculta la descripción (el perfil conserva la suya).
    """

    def __init__(
        self,
        existentes: Sequence[PerfilMaquina],
        *,
        titulo: str,
        texto_aceptar: str,
        nombre_inicial: str,
        descripcion_inicial: str | None = None,
        excluir_id: str | None = None,
        bloqueo: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            existentes,
            titulo=titulo,
            texto_aceptar=texto_aceptar,
            nombre_inicial=nombre_inicial,
            descripcion_inicial=descripcion_inicial,
            excluir_id=excluir_id,
            bloqueo=bloqueo,
            parent=parent,
        )
        self._nombre_tocado = True
        self._revisar()


class DialogoGuardarPerfil(_DialogoBaseNombre):
    """«Guardar como perfil de máquina…»: crea un perfil con la configuración del formulario.

    Uso: ``DialogoGuardarPerfil(almacen, cfg, avanzado=…, parent=…)`` y ``exec()``; si el
    resultado es aceptado, ``perfil_creado`` es el ``PerfilMaquina`` ya escrito en disco.
    Si el almacén falla (E-M08, límite de 100…), el error se muestra en el diálogo y este sigue
    abierto, así que no hay nada que hacer fuera. En básico no se ven la descripción ni las
    pistas (se guarda con pistas, CA-P03.7).

    No bloquea por errores de capa 2 (almacenamiento o red inexistentes en otro nodo,
    CA-P03.2); los de capa 1 se listan y deshabilitan «Guardar».
    """

    def __init__(
        self,
        almacen: AlmacenPerfilesMaquina,
        cfg: ConfiguracionVM,
        *,
        avanzado: bool,
        nombre_sugerido: str = "",
        parent: QWidget | None = None,
    ) -> None:
        usuario = sum(1 for p in almacen.todos() if p.origen == OrigenPerfil.USUARIO)
        bloqueo = None
        if almacen.estado.solo_lectura:
            bloqueo = _texto_solo_lectura()
        elif usuario >= MAX_PERFILES_USUARIO:
            bloqueo = texto_regla_perfil("V-M03")
        super().__init__(
            almacen.todos(),
            titulo=QCoreApplication.translate(
                "DialogoGuardarPerfil", "Guardar como perfil de máquina"
            ),
            texto_aceptar=QCoreApplication.translate("DialogoGuardarPerfil", "Guardar perfil"),
            nombre_inicial=nombre_libre(
                nombre_sugerido or QCoreApplication.translate("DialogoGuardarPerfil", "Mi perfil"),
                almacen.todos(),
            ),
            descripcion_inicial="" if avanzado else None,
            bloqueo=bloqueo,
            parent=parent,
        )
        self._almacen = almacen
        self._cfg = cfg
        self.perfil_creado: PerfilMaquina | None = None
        self.setObjectName("DialogoGuardarPerfil")
        self.setMinimumWidth(660)  # la casilla de pistas no se parte en varias líneas
        config = config_desde_configuracion(cfg, con_pistas=False)
        introduccion = etiqueta(
            QCoreApplication.translate(
                "DialogoGuardarPerfil",
                "Se guardará el hardware actual del formulario: procesador, memoria, discos y "
                "redes. No se guarda el nombre de la máquina, su número ni el nodo.",
            ),
            secundario=True,
        )
        self.capa.insertWidget(1, introduccion)
        self.resumen = etiqueta(texto_resumen_perfil(config))
        self.resumen.setAccessibleName(
            QCoreApplication.translate("DialogoGuardarPerfil", "Resumen del perfil")
        )
        self.capa.insertWidget(2, self.resumen)

        self.casilla_pistas = QCheckBox(
            QCoreApplication.translate(
                "DialogoGuardarPerfil",
                "Recordar los nombres de almacenamiento y red "
                "(solo sirven en servidores que los tengan)",
            )
        )
        self.casilla_pistas.setChecked(True)  # CA-P03.3
        self.casilla_pistas.setAccessibleName(
            QCoreApplication.translate(
                "DialogoGuardarPerfil", "Recordar los nombres de almacenamiento y red"
            )
        )
        ayuda_pistas = boton_ayuda_texto(
            QCoreApplication.translate(
                "DialogoGuardarPerfil",
                "Si lo marcas, el perfil recuerda en qué almacenamiento y red estaba cada disco. "
                "Al usarlo en otro servidor, si esos nombres no existen se elegirán otros y se "
                "te avisará.",
            )
        )
        fila_pistas = QHBoxLayout()
        fila_pistas.addWidget(self.casilla_pistas, 1)
        fila_pistas.addWidget(ayuda_pistas)
        contenedor = QWidget()
        contenedor.setLayout(fila_pistas)
        fila_pistas.setContentsMargins(0, 0, 0, 0)
        self.zona_extra.addWidget(contenedor)
        contenedor.setVisible(avanzado)  # CA-P03.7: en básico se usa el valor por defecto

        self.lista_capa1 = mensaje(error=True)
        self.zona_extra.addWidget(self.lista_capa1)
        self._errores_capa1 = self._revisar_capa1(config)
        self._revisar()

    def _revisar_capa1(self, config: ConfigPerfil) -> tuple[str, ...]:
        """Errores de capa 1 de la configuración (CA-P03.2): indican qué corregir."""
        errores = [p for p in validar_config_perfil(config) if p.severidad == Severidad.ERROR]
        textos = [texto_problema(p) for p in errores]
        if textos:
            poner_mensaje(
                self.lista_capa1,
                QCoreApplication.translate(
                    "DialogoGuardarPerfil",
                    "Corrige esto en el formulario antes de guardar el perfil:",
                )
                + "\n"
                + "\n".join(f"• {t}" for t in dict.fromkeys(textos)),
            )
        return tuple(dict.fromkeys(textos))

    def _revisar(self) -> None:
        super()._revisar()
        if self._errores_capa1:
            self.boton_aceptar.setEnabled(False)

    def _al_aceptar(self) -> None:
        config = config_desde_configuracion(self._cfg, con_pistas=self.casilla_pistas.isChecked())
        try:
            self.perfil_creado = self._almacen.crear(self.nombre, self.descripcion, config)
        except ErrorProxLaunch as error:
            poner_mensaje(self.error_general, texto_fallo(error))
            return
        poner_mensaje(self.error_general, None)
        self.accept()
