"""Prueba de humo del arranque: comprueba recursos, Qt y ventana sin red ni datos reales."""

from __future__ import annotations

import contextlib
import faulthandler
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import IO

import keyring
import keyring.backends.fail
import keyring.backends.null
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication

from proxlaunch import __version__
from proxlaunch.interfaz.app import (
    NOMBRE_APP,
    adjuntar_consola_del_padre,
    cargar_traductor,
    crear_dependencias,
    crear_icono,
)
from proxlaunch.interfaz.fuentes import (
    FAMILIA_INTERFAZ_RESPALDO,
    FAMILIA_MONO_RESPALDO,
    cargar_fuentes,
)
from proxlaunch.interfaz.tema import GestorTema, ModoTema
from proxlaunch.interfaz.ventana_principal import VentanaPrincipal
from proxlaunch.nucleo.persistencia.rutas import Rutas
from proxlaunch.nucleo.registro import cerrar_registro, configurar_registro

# Variable con la ruta de un archivo donde copiar el informe (Windows sin consola).
VARIABLE_SALIDA = "PROXLAUNCH_HUMO_SALIDA"
# Tiempo máximo total antes de que el vigilante fuerce una salida con error (CA-E17.1: ≤ 15 s).
# El primer arranque de un ejecutable sin firmar en Windows puede tardar varios segundos (el
# antivirus analiza sus bibliotecas), así que el límite cubre todo el arranque, no solo la espera.
LIMITE_VIGILANTE_S = 15.0
CODIGO_VIGILANTE = 3
# Holgura del respaldo de faulthandler sobre el límite del vigilante (el Timer va primero).
_MARGEN_RESPALDO_S = 2.0
_TAMANOS_ICONO = (16, 24, 32, 48, 64, 128, 256)


@dataclass(frozen=True)
class InformeHumo:
    """Resultado de la prueba de humo (se imprime como una línea JSON)."""

    version: str
    plataforma_qt: str
    fuentes: tuple[str, str]
    traductor: bool
    icono_ok: bool
    recursos_faltantes: tuple[str, ...]
    backend_llavero: str
    ventana_mostrada: bool
    problemas: tuple[str, ...]


def recursos_esperados() -> tuple[str, ...]:
    """Rutas (relativas al paquete ``proxlaunch``) de los recursos que deben existir."""
    marca = (
        "proxlaunch-icono-sin-texto.svg",
        "proxlaunch-icono.svg",
        "proxlaunch-logotipo-claro.svg",
        "proxlaunch-logotipo-oscuro.svg",
        "proxlaunch-simbolo-claro.svg",
        "proxlaunch-simbolo-oscuro.svg",
    )
    fuentes = (
        "JetBrainsMono-OFL.txt",
        "JetBrainsMono-Variable.ttf",
        "OpenSans-OFL.txt",
        "OpenSans-Variable.ttf",
    )
    return (
        *(f"recursos/marca/{n}" for n in marca),
        *(f"recursos/fuentes/{n}" for n in fuentes),
        "recursos/traducciones/proxlaunch_es.qm",
        "interfaz/tema/plantilla.qss",
    )


def _faltantes() -> tuple[str, ...]:
    raiz = resources.files("proxlaunch")
    faltan: list[str] = []
    for ruta in recursos_esperados():
        try:
            if not raiz.joinpath(*ruta.split("/")).is_file():
                faltan.append(ruta)
        except (OSError, ModuleNotFoundError):
            faltan.append(ruta)
    return tuple(faltan)


def _icono_valido() -> bool:
    """Falla si el icono es nulo o algún tamaño sale vacío (p. ej. falta el plugin SVG)."""
    icono = crear_icono()
    if icono.isNull():
        return False
    return all(not icono.pixmap(lado, lado).isNull() for lado in _TAMANOS_ICONO)


def _nombre_backend() -> str:
    """Módulo y clase del backend del llavero, sin leer ni escribir ningún secreto."""
    tipo = type(keyring.get_keyring())
    return f"{tipo.__module__}.{tipo.__qualname__}"


def _backend_inutil() -> bool:
    return isinstance(
        keyring.get_keyring(), keyring.backends.fail.Keyring | keyring.backends.null.Keyring
    )


def _escribir_archivo_salida(destino: str, texto: str) -> None:
    """Escribe sin seguir enlaces simbólicos (POSIX) y, si el archivo no existe, en creación
    exclusiva. Si ya existe (p. ej. lo precreó quien lanza el proceso) lo trunca."""
    sin_enlaces = getattr(os, "O_NOFOLLOW", 0)  # no existe en Windows
    datos = (texto + "\n").encode("utf-8")
    try:
        try:
            fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | sin_enlaces, 0o600)
        except FileExistsError:
            fd = os.open(destino, os.O_WRONLY | os.O_TRUNC | sin_enlaces)
        with os.fdopen(fd, "wb") as flujo:
            flujo.write(datos)
    except OSError:
        pass


def _escribir_salida(texto: str) -> None:
    """Escribe ``texto`` en stdout (si existe) y en el archivo de la variable (si está definida)."""
    destino = os.environ.get(VARIABLE_SALIDA)
    if sys.stdout is not None:
        print(texto, flush=True)
    if destino:
        _escribir_archivo_salida(destino, texto)


def escribir_texto_plano(texto: str) -> None:
    """Salida de ``--version``: stdout y, si procede, el archivo de ``PROXLAUNCH_HUMO_SALIDA``."""
    adjuntar_consola_del_padre()
    _escribir_salida(texto)


def _emitir(informe: InformeHumo) -> None:
    _escribir_salida(json.dumps(asdict(informe), ensure_ascii=False))
    if sys.stderr is not None:
        for problema in informe.problemas:
            print(f"PROBLEMA: {problema}", file=sys.stderr, flush=True)


class _Progreso:
    """Paso en curso del humo, para que el vigilante diga dónde se quedó."""

    def __init__(self) -> None:
        self.paso = "inicio"
        self.inicio = time.monotonic()
        # Arbitraje con el hilo principal y respaldo de faulthandler (los fija el humo).
        self.cierre: _Cierre | None = None
        self.respaldo: _RespaldoFaulthandler | None = None


class _Cierre:
    """Arbitra quién da el resultado final: el hilo principal o el vigilante (nunca ambos)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._marcado = False
        self._abortando = False

    def reclamar_emision(self) -> bool:
        """El principal marca antes de emitir; False si el vigilante ya empezó a abortar."""
        with self._lock:
            if self._abortando:
                return False
            self._marcado = True
            return True

    def reclamar_aborto(self) -> bool:
        """El vigilante no hace nada si el principal ya marcó."""
        with self._lock:
            if self._marcado:
                return False
            self._abortando = True
            return True


class _RespaldoFaulthandler:
    """Respaldo del vigilante que no depende del GIL (``faulthandler``).

    Es solo un respaldo: el ``Timer`` sigue siendo el camino normal y el único que escribe el
    informe. Si el intérprete queda atascado con el GIL tomado, el Timer no corre y
    ``faulthandler`` vuelca la traza y sale (con código 1) pasado el límite más un margen.
    """

    def __init__(self, carpeta: Path) -> None:
        self._archivo: IO[str] | None = None
        destino: IO[str] | None = None
        # Con ``console=False`` (Windows) ``sys.stderr`` es None o no tiene descriptor.
        try:
            if sys.stderr is not None:
                sys.stderr.fileno()
                destino = sys.stderr
        except (OSError, ValueError, AttributeError):
            destino = None
        if destino is None:
            try:
                self._archivo = destino = (carpeta / "faulthandler.txt").open("w", encoding="utf-8")
            except OSError:
                return
        try:
            faulthandler.dump_traceback_later(
                LIMITE_VIGILANTE_S + _MARGEN_RESPALDO_S, exit=True, file=destino
            )
        except (OSError, ValueError, RuntimeError):
            self.cancelar()

    def cancelar(self) -> None:
        with contextlib.suppress(Exception):
            faulthandler.cancel_dump_traceback_later()
        if self._archivo is not None:
            with contextlib.suppress(OSError):
                self._archivo.close()
            self._archivo = None


def _arrancar_vigilante(carpeta: Path, progreso: _Progreso | None = None) -> threading.Timer:
    """Hilo que, pasado el límite, informa, borra la carpeta temporal y sale con error."""

    cierre = progreso.cierre if progreso is not None else None
    respaldo = progreso.respaldo if progreso is not None else None

    def _abortar() -> None:
        if cierre is not None and not cierre.reclamar_aborto():
            return  # el hilo principal ya está emitiendo el informe final
        mensaje = f"La prueba de humo superó {LIMITE_VIGILANTE_S:g} s y se abortó"
        if progreso is not None:
            transcurrido = time.monotonic() - progreso.inicio
            mensaje += f" (paso «{progreso.paso}», {transcurrido:.1f} s)"
        # Sin consola (Windows) stderr no existe: el motivo también va al archivo de salida.
        _escribir_salida(
            json.dumps({"version": __version__, "problemas": [mensaje]}, ensure_ascii=False)
        )
        if sys.stderr is not None:
            print(f"PROBLEMA: {mensaje}", file=sys.stderr, flush=True)
        if respaldo is not None:
            respaldo.cancelar()
        # En Windows el log abierto impide borrar la carpeta temporal.
        cerrar_registro()
        shutil.rmtree(carpeta, ignore_errors=True)
        os._exit(CODIGO_VIGILANTE)

    vigilante = threading.Timer(LIMITE_VIGILANTE_S, _abortar)
    vigilante.daemon = True
    vigilante.start()
    return vigilante


def ejecutar_prueba_de_humo(
    argv_qt: list[str], *, permitir_sin_llavero: bool = False, espera_ms: int = 1500
) -> int:
    """Arranca la app con carpetas temporales y sin red; devuelve 0 solo si no hay problemas."""
    carpeta = Path(tempfile.mkdtemp(prefix="proxlaunch-humo-"))
    adjuntar_consola_del_padre()
    progreso = _Progreso()
    cierre = progreso.cierre = _Cierre()
    respaldo_gil = progreso.respaldo = _RespaldoFaulthandler(carpeta)
    vigilante = _arrancar_vigilante(carpeta, progreso)
    problemas: list[str] = []
    plataforma = ""
    fuentes = ("", "")
    traductor_ok = icono_ok = ventana_ok = False
    faltantes: tuple[str, ...] = ()
    backend = ""
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        progreso.paso = "QApplication"
        app = QApplication.instance() or QApplication(argv_qt)
        assert isinstance(app, QApplication)
        app.setApplicationName(NOMBRE_APP)
        app.setApplicationDisplayName(NOMBRE_APP)
        app.setOrganizationName(NOMBRE_APP)
        app.setDesktopFileName("proxlaunch")
        plataforma = app.platformName()

        progreso.paso = "carpetas y registro"
        rutas = Rutas(carpeta)
        configurar_registro(rutas.directorio_log)

        progreso.paso = "icono"
        icono_ok = _icono_valido()
        if not icono_ok:
            problemas.append("El icono está vacío o es nulo (¿falta el plugin SVG de Qt?)")
        app.setWindowIcon(crear_icono())

        progreso.paso = "fuentes"
        fuentes = cargar_fuentes()
        for familia, respaldo in zip(
            fuentes, (FAMILIA_INTERFAZ_RESPALDO, FAMILIA_MONO_RESPALDO), strict=True
        ):
            if familia == respaldo:
                problemas.append(f"No cargó la fuente incluida (se usó «{respaldo}»)")
        app.setFont(QFont(fuentes[0]))

        progreso.paso = "traductor"
        traductor_ok = cargar_traductor(app) is not None
        if not traductor_ok:
            problemas.append("No se pudo cargar el catálogo proxlaunch_es.qm")

        progreso.paso = "recursos"
        faltantes = _faltantes()
        if faltantes:
            problemas.append("Recursos faltantes: " + ", ".join(faltantes))

        progreso.paso = "tema"
        # Los iconos van a la carpeta temporal del humo: nunca a la caché real del usuario.
        gestor = GestorTema(
            app, ModoTema.AUTOMATICO, directorio_iconos=rutas.directorio_cache / "tema"
        )
        gestor.aplicar()
        if not gestor.iconos_activos:
            problemas.append("No se generaron los iconos del tema")

        progreso.paso = "llavero"
        backend = _nombre_backend()
        if _backend_inutil() and not permitir_sin_llavero:
            problemas.append(f"Backend de llavero sin función: {backend}")

        progreso.paso = "ventana principal"
        ventana = VentanaPrincipal(crear_dependencias(rutas, gestor))
        ventana.show()
        visibilidad: list[bool] = []

        def _cerrar() -> None:
            # Se mide antes de salir: tras ``quit`` Qt puede ocultar las ventanas.
            visibilidad.append(ventana.isVisible())
            app.quit()

        progreso.paso = "bucle de eventos"
        QTimer.singleShot(espera_ms, _cerrar)
        app.exec()
        ventana_ok = bool(visibilidad and visibilidad[0])
        if not ventana_ok:
            problemas.append("La ventana principal no quedó visible")
        ventana.close()
    except Exception as exc:  # noqa: BLE001 - cualquier fallo es un fallo del humo
        problemas.append(f"Excepción {type(exc).__name__}: {exc}")
    finally:
        vigilante.cancel()
        respaldo_gil.cancelar()
        cerrar_registro()
        shutil.rmtree(carpeta, ignore_errors=True)

    if not cierre.reclamar_emision():
        # El vigilante ya empezó a abortar: él informa y el proceso termina con 3.
        return CODIGO_VIGILANTE

    informe = InformeHumo(
        version=__version__,
        plataforma_qt=plataforma,
        fuentes=fuentes,
        traductor=traductor_ok,
        icono_ok=icono_ok,
        recursos_faltantes=faltantes,
        backend_llavero=backend,
        ventana_mostrada=ventana_ok,
        problemas=tuple(problemas),
    )
    _emitir(informe)
    return 0 if not informe.problemas else 1
