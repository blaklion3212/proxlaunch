"""Diálogo «Guardar lote…»: nombre del lote y, si vino de un archivo, dónde guardarlo (RF-G02).

Solo recoge el nombre y la decisión. La ruta la pide después ``elegir_para_guardar`` y la
escritura (``guardar_lote``) corre en un hilo; ambas las orquesta la ventana principal.
"""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.archivos_ui import TipoArchivo, nombre_sugerido
from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.textos import texto_regla_perfil
from proxlaunch.interfaz.vistas.campos import etiqueta, mensaje, poner_mensaje, poner_propiedad
from proxlaunch.nucleo.archivos.constantes import LONG_NOMBRE_PERFIL
from proxlaunch.nucleo.archivos.texto import validar_nombre


class AccionGuardarLote(StrEnum):
    """Qué hacer con el archivo cuando el lote se abrió desde uno (CA-G03.6)."""

    NUEVO = "nuevo"  # pedir una ruta con el diálogo del sistema
    SOBRESCRIBIR = "sobrescribir"  # escribir encima del archivo de origen


class DialogoGuardarLote(QDialog):
    """Pide el nombre del lote (1–60 caracteres, V-M01 sin unicidad).

    Constructor: ``DialogoGuardarLote(nombre_sugerido=…, hay_problemas=…, archivo_origen=…,
    parent=…)``. ``nombre_sugerido`` suele ser el prefijo de nombres (CA-G02.2);
    ``hay_problemas`` muestra el aviso de borrador (CA-G02.1); ``archivo_origen`` es solo el
    nombre (no la ruta) del archivo desde el que se abrió el lote, y activa la elección entre
    sobrescribirlo o guardar uno nuevo.

    Tras ``exec()`` aceptado: ``nombre``, ``accion`` y ``nombre_archivo_sugerido``.
    """

    def __init__(
        self,
        *,
        nombre_sugerido: str = "",
        hay_problemas: bool = False,
        archivo_origen: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Guardar lote"))
        self.setModal(True)
        self.setMinimumWidth(480)
        self._tocado = False
        capa = QVBoxLayout(self)

        capa.addWidget(
            etiqueta(
                self.tr(
                    "Se guarda la configuración del lote para volver a usarla. No se guardan las "
                    "máquinas creadas ni ningún dato de conexión (servidor, usuario o "
                    "credenciales)."
                ),
                secundario=True,
            )
        )
        self.aviso_problemas = mensaje(aviso=True)
        if hay_problemas:
            poner_mensaje(
                self.aviso_problemas,
                self.tr("El lote tiene problemas; se comprobará otra vez al abrirlo."),
                aviso=True,
            )
        capa.addWidget(self.aviso_problemas)

        self.campo_nombre = QLineEdit(nombre_sugerido)
        self.campo_nombre.setAccessibleName(self.tr("Nombre del lote"))
        self.campo_nombre.setPlaceholderText(self.tr("Por ejemplo: Servidores web de pruebas"))
        etiqueta_nombre = QLabel(self.tr("Nombre del lote"))
        etiqueta_nombre.setBuddy(self.campo_nombre)
        self.error_nombre = mensaje(error=True)
        capa.addWidget(etiqueta_nombre)
        capa.addWidget(self.campo_nombre)
        capa.addWidget(self.error_nombre)

        self.radio_nuevo = QRadioButton(self.tr("Guardar como un archivo nuevo…"))
        self.radio_sobrescribir = QRadioButton(
            self.tr("Sobrescribir el archivo «{nombre}»").format(nombre=archivo_origen or "")
        )
        self._grupo = QButtonGroup(self)
        self._grupo.addButton(self.radio_nuevo)
        self._grupo.addButton(self.radio_sobrescribir)
        self.radio_nuevo.setChecked(True)
        if archivo_origen is not None:
            capa.addWidget(self.radio_nuevo)
            capa.addWidget(self.radio_sobrescribir)
        else:
            self.radio_nuevo.hide()
            self.radio_sobrescribir.hide()

        self.botones = QDialogButtonBox()
        self.boton_aceptar = QPushButton()
        self.boton_cancelar = QPushButton(self.tr("Cancelar"))
        self.botones.addButton(self.boton_aceptar, QDialogButtonBox.ButtonRole.AcceptRole)
        self.botones.addButton(self.boton_cancelar, QDialogButtonBox.ButtonRole.RejectRole)
        self.boton_aceptar.setDefault(True)
        self.boton_aceptar.setProperty("primario", True)
        capa.addWidget(self.botones)

        self._archivo_origen = archivo_origen
        self.botones.accepted.connect(self._aceptar)
        self.botones.rejected.connect(self.reject)
        self.campo_nombre.textChanged.connect(self._al_editar)
        self._grupo.buttonClicked.connect(lambda _b: self._revisar())
        self._revisar()
        self.campo_nombre.selectAll()
        self.campo_nombre.setFocus()

    # --- Resultado -------------------------------------------------------------------

    @property
    def nombre(self) -> str:
        """Nombre normalizado (recortado, NFC) que se guardará dentro del archivo."""
        return validar_nombre(self.campo_nombre.text(), maximo=LONG_NOMBRE_PERFIL)[0]

    @property
    def accion(self) -> AccionGuardarLote:
        if self.radio_sobrescribir.isChecked() and not self.radio_sobrescribir.isHidden():
            return AccionGuardarLote.SOBRESCRIBIR
        return AccionGuardarLote.NUEVO

    @property
    def nombre_archivo_sugerido(self) -> str:
        """Nombre de archivo saneado para el diálogo del sistema (``….proxlaunch-lote.json``)."""
        return nombre_sugerido(TipoArchivo.LOTE, self.nombre)

    # --- Validación ------------------------------------------------------------------

    def _al_editar(self) -> None:
        self._tocado = True
        self._revisar()

    def _regla(self) -> str | None:
        return validar_nombre(self.campo_nombre.text(), maximo=LONG_NOMBRE_PERFIL)[1]

    def _revisar(self) -> None:
        regla = self._regla()
        mostrar = regla is not None and (self._tocado or bool(self.campo_nombre.text()))
        texto = texto_regla_perfil(regla, self.tr("nombre")) if mostrar and regla else None
        poner_mensaje(self.error_nombre, texto)
        poner_propiedad(self.campo_nombre, "invalido", bool(mostrar))
        self.boton_aceptar.setEnabled(regla is None)
        self.boton_aceptar.setText(
            self.tr("Sobrescribir")
            if self.accion == AccionGuardarLote.SOBRESCRIBIR
            else self.tr("Elegir dónde guardar…")
        )

    def _aceptar(self) -> None:
        """Sobrescribir no pasa por el diálogo del sistema, así que se confirma aquí."""
        if self.accion == AccionGuardarLote.SOBRESCRIBIR and not confirmar(
            self,
            self.tr("Sobrescribir archivo"),
            self.tr(
                "¿Sobrescribir el archivo «{nombre}»? Su contenido anterior se perderá."
            ).format(nombre=self._archivo_origen or ""),
            self.tr("Sobrescribir"),
            self.tr("Cancelar"),
        ):
            return
        self.accept()

    def ejecutar(self) -> bool:
        """Muestra el diálogo; ``True`` si el usuario aceptó."""
        return self.exec() == QDialog.DialogCode.Accepted
