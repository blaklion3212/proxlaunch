"""Arranque de la aplicación: QApplication, fuentes, traducciones y tema."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
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
        directorio_informes=rutas.informes,
        directorio_lotes=rutas.lotes,
        version_app=__version__,
    )


def adjuntar_consola_del_padre() -> None:
    """Con ``console=False`` (Windows) stdout es None: intenta usar la consola del proceso padre.

    Solo para los caminos de consola (``--version``, ayuda, humo). Si falla no hace nada: el
    archivo de ``PROXLAUNCH_HUMO_SALIDA`` sigue siendo el camino fiable.
    """
    if sys.platform != "win32" or sys.stdout is not None:
        return
    try:
        import ctypes

        if not ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
            return
        sys.stdout = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115
        sys.stderr = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115
    except (OSError, AttributeError):
        return


def _analizar_argumentos(argv: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    """Separa las opciones propias de las de Qt (que pasan intactas a ``QApplication``)."""
    analizador = argparse.ArgumentParser(add_help=True, prog="proxlaunch", allow_abbrev=False)
    analizador.add_argument("--version", action="store_true", help="muestra la versión y sale")
    analizador.add_argument(
        "--prueba-de-humo",
        action="store_true",
        help="arranca con carpetas temporales, comprueba recursos y sale",
    )
    analizador.add_argument(
        "--permitir-sin-llavero",
        action="store_true",
        help="con --prueba-de-humo: acepta un llavero no disponible",
    )
    propios, resto = analizador.parse_known_args(list(argv[1:]))
    return propios, [argv[0], *resto]


def main(argv: Sequence[str] | None = None) -> int:
    """Crea la aplicación, aplica el tema guardado y abre la ventana principal."""
    argumentos = list(sys.argv if argv is None else argv)
    if not argumentos:
        argumentos = ["proxlaunch"]
    if any(a in ("--version", "-h", "--help", "--prueba-de-humo") for a in argumentos[1:]):
        adjuntar_consola_del_padre()
    propios, argv_qt = _analizar_argumentos(argumentos)
    if propios.version:
        from proxlaunch.interfaz.humo import escribir_texto_plano

        escribir_texto_plano(f"{NOMBRE_APP} {__version__}")
        return 0
    if propios.prueba_de_humo:
        from proxlaunch.interfaz.humo import ejecutar_prueba_de_humo

        return ejecutar_prueba_de_humo(argv_qt, permitir_sin_llavero=propios.permitir_sin_llavero)

    # Alta resolución: escalado fraccionario sin redondeos (150 %, 175 %...) (RNF-11).
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(argv_qt)
    assert isinstance(app, QApplication)
    app.setApplicationName(NOMBRE_APP)
    app.setApplicationDisplayName(NOMBRE_APP)
    app.setOrganizationName(NOMBRE_APP)
    # Asocia la ventana con proxlaunch.desktop en Wayland (HV-E11).
    app.setDesktopFileName("proxlaunch")
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
