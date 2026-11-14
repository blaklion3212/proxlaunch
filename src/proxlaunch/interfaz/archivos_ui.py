"""Piezas de interfaz comunes a perfiles, lotes guardados y CSV (MVP 3, RF-X05).

Diálogos del sistema para abrir y guardar archivos (filtros y extensiones de CA-X05.1,
carpeta inicial de CA-X05.3), textos de los códigos nuevos del núcleo de archivos y un botón
de ayuda con texto propio. Las rutas elegidas se recuerdan solo durante la sesión: nunca se
guardan en ``preferencias.json``.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

import platformdirs
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QToolButton,
    QToolTip,
    QWidget,
)

from proxlaunch.interfaz.textos import texto_fallo
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.archivos.texto import nombre_archivo_seguro
from proxlaunch.nucleo.csv_importacion.plantilla import escribir_plantilla
from proxlaunch.nucleo.errores import ErrorProxLaunch


class TipoArchivo(StrEnum):
    """Tipo de archivo que maneja la aplicación; decide filtro y extensión sugerida."""

    PERFILES = "perfiles"
    LOTE = "lote"
    CSV = "csv"


EXTENSION_SUGERIDA: dict[TipoArchivo, str] = {
    TipoArchivo.PERFILES: ".proxlaunch-perfiles.json",
    TipoArchivo.LOTE: ".proxlaunch-lote.json",
    TipoArchivo.CSV: ".csv",
}
# Sufijo que Qt añade si el usuario escribe un nombre sin extensión.
_SUFIJO_POR_DEFECTO: dict[TipoArchivo, str] = {
    TipoArchivo.PERFILES: "json",
    TipoArchivo.LOTE: "json",
    TipoArchivo.CSV: "csv",
}

# Carpeta del último archivo elegido en esta sesión (CA-X05.3). No se persiste.
_ultima_carpeta: Path | None = None


def filtro_de(tipo: TipoArchivo) -> str:
    """Filtro del diálogo del sistema para el tipo (CA-X05.1)."""
    if tipo == TipoArchivo.PERFILES:
        return QCoreApplication.translate("ArchivosUi", "Perfiles de ProxLaunch (*.json)")
    if tipo == TipoArchivo.LOTE:
        return QCoreApplication.translate("ArchivosUi", "Lotes de ProxLaunch (*.json)")
    return QCoreApplication.translate("ArchivosUi", "CSV (*.csv *.txt)")


def carpeta_inicial() -> Path:
    """Última carpeta usada en la sesión o la de documentos del usuario."""
    if _ultima_carpeta is not None and _ultima_carpeta.is_dir():
        return _ultima_carpeta
    return Path(platformdirs.user_documents_dir())


def olvidar_carpeta() -> None:
    """Borra la carpeta recordada (para pruebas)."""
    global _ultima_carpeta
    _ultima_carpeta = None


def _recordar(ruta: Path) -> None:
    global _ultima_carpeta
    _ultima_carpeta = ruta.parent


def nombre_sugerido(tipo: TipoArchivo, base: str) -> str:
    """Nombre de archivo sugerido y saneado a partir de un texto (CA-P08.5)."""
    return nombre_archivo_seguro(base, EXTENSION_SUGERIDA[tipo])


def elegir_para_abrir(parent: QWidget | None, tipo: TipoArchivo) -> Path | None:
    """Diálogo del sistema para abrir un archivo. ``None`` si el usuario cancela."""
    titulos = {
        TipoArchivo.PERFILES: QCoreApplication.translate("ArchivosUi", "Abrir archivo de perfiles"),
        TipoArchivo.LOTE: QCoreApplication.translate("ArchivosUi", "Abrir lote"),
        TipoArchivo.CSV: QCoreApplication.translate("ArchivosUi", "Elegir archivo CSV"),
    }
    ruta, _filtro = QFileDialog.getOpenFileName(
        parent, titulos[tipo], str(carpeta_inicial()), filtro_de(tipo)
    )
    if not ruta:
        return None
    destino = Path(ruta)
    _recordar(destino)
    return destino


def elegir_para_guardar(
    parent: QWidget | None,
    tipo: TipoArchivo,
    nombre_sugerido: str,
    carpeta: Path | None = None,
) -> Path | None:
    """Diálogo del sistema para guardar; pide confirmar si el archivo ya existe (CA-P08.6).

    ``nombre_sugerido`` ya debe venir saneado (ver ``nombre_sugerido``). Si el usuario no
    escribe extensión, Qt añade la del tipo antes de comprobar la sobrescritura.
    """
    titulos = {
        TipoArchivo.PERFILES: QCoreApplication.translate("ArchivosUi", "Exportar perfiles"),
        TipoArchivo.LOTE: QCoreApplication.translate("ArchivosUi", "Guardar lote"),
        TipoArchivo.CSV: QCoreApplication.translate("ArchivosUi", "Guardar archivo CSV"),
    }
    inicio = (carpeta if carpeta is not None else carpeta_inicial()) / nombre_sugerido
    dialogo = QFileDialog(parent, titulos[tipo], str(inicio), filtro_de(tipo))
    dialogo.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialogo.setFileMode(QFileDialog.FileMode.AnyFile)
    dialogo.setDefaultSuffix(_SUFIJO_POR_DEFECTO[tipo])
    if not dialogo.exec():
        return None
    elegidos = dialogo.selectedFiles()
    if not elegidos:
        return None
    destino = Path(elegidos[0])
    _recordar(destino)
    return destino


# --- Plantilla CSV (RF-C10) ------------------------------------------------------------


def pedir_separador_plantilla(parent: QWidget | None) -> str | None:
    """Pregunta el separador de la plantilla: «;» por defecto o «,» (CA-C10.2)."""
    opciones = [
        QCoreApplication.translate("ArchivosUi", "; (Excel en español)"),
        QCoreApplication.translate("ArchivosUi", ", (Excel en inglés)"),
    ]
    elegido, aceptado = QInputDialog.getItem(
        parent,
        QCoreApplication.translate("ArchivosUi", "Descargar plantilla CSV"),
        QCoreApplication.translate("ArchivosUi", "Separador de columnas:"),
        opciones,
        0,
        False,
    )
    if not aceptado:
        return None
    return ";" if elegido == opciones[0] else ","


def descargar_plantilla(
    parent: QWidget | None,
    lanzador: Lanzador,
    *,
    al_terminar: Callable[[Path], None] | None = None,
    al_fallar: Callable[[ErrorProxLaunch], None] | None = None,
    separador: str | None = None,
) -> bool:
    """«Descargar plantilla CSV…»: separador, ruta y escritura en un hilo (RF-C10).

    ``separador`` permite saltar la pregunta (pruebas). Devuelve ``False`` si el usuario
    cancela en cualquiera de los pasos. ``al_terminar`` recibe la ruta escrita.
    """
    sep = separador if separador is not None else pedir_separador_plantilla(parent)
    if sep is None:
        return False
    ruta = elegir_para_guardar(
        parent,
        TipoArchivo.CSV,
        nombre_archivo_seguro(
            QCoreApplication.translate("ArchivosUi", "plantilla-proxlaunch"), ".csv"
        ),
    )
    if ruta is None:
        return False

    def _listo(_resultado: object) -> None:
        if al_terminar is not None:
            al_terminar(ruta)

    lanzador.lanzar(
        escribir_plantilla, ruta, separador=sep, al_terminar=_listo, al_fallar=al_fallar
    )
    return True


# --- Textos ---------------------------------------------------------------------------


# --- Ayuda breve ----------------------------------------------------------------------


def boton_ayuda_texto(texto: str, parent: QWidget | None = None) -> QToolButton:
    """Icono «?» cuya sugerencia es ``texto`` (ayuda en lenguaje llano, D-14).

    Igual que ``campos.boton_ayuda`` pero con el texto ya resuelto, para diálogos cuyos
    textos de ayuda viven junto a ellos.
    """
    boton = QToolButton(parent)
    boton.setText("?")
    boton.setToolTip(texto)
    boton.setAccessibleName(QCoreApplication.translate("ArchivosUi", "Ayuda"))
    boton.setAccessibleDescription(texto)
    boton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    boton.setAutoRaise(True)
    boton.setCursor(Qt.CursorShape.WhatsThisCursor)
    boton.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    boton.setStyleSheet("padding: 0px; min-height: 0px;")
    boton.setFixedSize(24, 24)
    boton.clicked.connect(
        lambda: QToolTip.showText(boton.mapToGlobal(boton.rect().bottomLeft()), texto, boton)
    )
    return boton


def avisar_error(parent: QWidget | None, titulo: str, error: ErrorProxLaunch) -> None:
    """Muestra un error de archivo en una caja de mensaje sencilla."""
    caja = QMessageBox(QMessageBox.Icon.Warning, titulo, texto_fallo(error), parent=parent)
    caja.setTextFormat(Qt.TextFormat.PlainText)
    caja.exec()
