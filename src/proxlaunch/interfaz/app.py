"""Arranque de la aplicación: QApplication, fuentes, traducciones y tema."""

from __future__ import annotations

import logging
import sys
from importlib import resources

from PySide6.QtCore import QSize, Qt, QTranslator
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from proxlaunch import __version__
from proxlaunch.interfaz.fuentes import cargar_fuentes
from proxlaunch.interfaz.tema import GestorTema, ModoTema
from proxlaunch.interfaz.textos import textos_perfiles_fabrica
from proxlaunch.interfaz.ventana_principal import Dependencias, VentanaPrincipal
from proxlaunch.interfaz.vistas.barra_superior import cargar_svg
from proxlaunch.nucleo.api.transporte import crear_transporte_http
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.persistencia.preferencias import RepositorioPreferencias
from proxlaunch.nucleo.persistencia.rutas import Rutas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.registro import configurar_registro
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.conexion import ServicioConexion

NOMBRE_APP = "ProxLaunch"
_log = logging.getLogger("proxlaunch.interfaz.app")


def crear_icono() -> QIcon:
    """Icono de la aplicación (símbolo sin texto) en varios tamaños."""
    icono = QIcon()
    for lado in (16, 24, 32, 48, 64, 128, 256):
        icono.addPixmap(cargar_svg("proxlaunch-icono-sin-texto.svg", QSize(lado, lado)))
    return icono


def cargar_traductor(app: QApplication) -> QTranslator | None:
    """Carga ``proxlaunch_es.qm`` si existe; la interfaz está en español en el propio código."""
    try:
        recurso = resources.files("proxlaunch.recursos").joinpath(
            "traducciones", "proxlaunch_es.qm"
        )
        if not recurso.is_file():
            return None
        traductor = QTranslator(app)
        if traductor.load(str(recurso)):
            app.installTranslator(traductor)
            return traductor
    except (OSError, ModuleNotFoundError):
        pass
    _log.info("No hay catálogo .qm: se usan los textos del código")
    return None


def crear_dependencias(rutas: Rutas, gestor_tema: GestorTema) -> Dependencias:
    """Servicios reales de producción (red, llavero y carpetas del usuario)."""
    huellas = RepositorioHuellas(rutas.huellas)
    secretos = AlmacenSecretos()
    reloj = RelojReal()
    servicio = ServicioConexion(crear_transporte_http, huellas, secretos, reloj)
    almacen_perfiles = AlmacenPerfilesMaquina(
        rutas.perfiles_maquina,
        fabrica=perfiles_fabrica(textos_perfiles_fabrica()),
        app_version=__version__,
    )
    almacen_perfiles.cargar()
    return Dependencias(
        servicio_conexion=servicio,
        perfiles=RepositorioPerfiles(rutas.perfiles),
        huellas=huellas,
        secretos=secretos,
        preferencias=RepositorioPreferencias(rutas.preferencias),
        reloj=reloj,
        gestor_tema=gestor_tema,
        perfiles_maquina=almacen_perfiles,
        directorio_lotes=rutas.lotes,
        version_app=__version__,
    )


def main() -> int:
    """Crea la aplicación, aplica el tema guardado y abre la ventana principal."""
    # Alta resolución: escalado fraccionario sin redondeos (150 %, 175 %...) (RNF-11).
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv)
    assert isinstance(app, QApplication)
    app.setApplicationName(NOMBRE_APP)
    app.setApplicationDisplayName(NOMBRE_APP)
    app.setOrganizationName(NOMBRE_APP)
    app.setWindowIcon(crear_icono())

    rutas = Rutas()
    configurar_registro(rutas.directorio_log)

    familia, _mono = cargar_fuentes()
    fuente = QFont(familia)
    fuente.setPixelSize(13)
    app.setFont(fuente)
    cargar_traductor(app)

    preferencias = RepositorioPreferencias(rutas.preferencias).cargar()
    gestor = GestorTema(app, ModoTema(preferencias.tema.value))
    gestor.aplicar()

    ventana = VentanaPrincipal(crear_dependencias(rutas, gestor))
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
