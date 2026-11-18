"""Captura de cierres inesperados (núcleo): hooks de excepciones, faulthandler y receptor Qt."""

from __future__ import annotations

import faulthandler
import logging
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from proxlaunch.nucleo import registro
from proxlaunch.nucleo.registro import (
    ARCHIVO_FALLO_NATIVO,
    ARCHIVO_LOG,
    MAX_MENSAJES_QT_REPETIDOS,
    cerrar_registro,
    configurar_registro,
    desinstalar_captura_de_fallos,
    instalar_captura_de_fallos,
    registrar_secreto,
)

RAIZ = Path(__file__).resolve().parents[2]


class _Previos:
    """Hooks 'previos' falsos que cuentan las llamadas."""

    def __init__(self) -> None:
        self.sys: list[type] = []
        self.hilo: list[str] = []
        self.unraisable: list[object] = []

    def instalar(self) -> None:
        sys.excepthook = lambda t, v, tb: self.sys.append(t)
        threading.excepthook = lambda a: self.hilo.append(a.thread.name)
        sys.unraisablehook = lambda a: self.unraisable.append(a)


@pytest.fixture
def entorno(tmp_path):
    """Carpeta de log temporal, hooks previos falsos y desinstalación garantizada."""
    originales = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    desinstalar_captura_de_fallos()
    previos = _Previos()
    previos.instalar()
    previos.falsos = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    carpeta = tmp_path / "log"
    configurar_registro(carpeta)
    previos.carpeta = carpeta
    yield previos
    desinstalar_captura_de_fallos()
    cerrar_registro()
    sys.excepthook, threading.excepthook, sys.unraisablehook = originales


def _log(carpeta: Path) -> str:
    ruta = carpeta / ARCHIVO_LOG
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


def _lanzar(excepcion: BaseException):
    try:
        raise excepcion
    except BaseException:
        return sys.exc_info()


# --- R1 ---------------------------------------------------------------------------------


def test_r1_excepcion_principal_se_registra_critical_con_traza(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    sys.excepthook(*_lanzar(ValueError("boom-principal")))
    texto = _log(entorno.carpeta)
    assert "CRITICAL proxlaunch.fallos: Error no controlado" in texto
    assert "Traceback" in texto
    assert "ValueError: boom-principal" in texto


def test_r1_encadena_al_hook_previo_con_stderr(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    sys.excepthook(*_lanzar(ValueError("x")))
    assert entorno.sys == [ValueError]


# --- R2 ---------------------------------------------------------------------------------


def test_r2_excepcion_en_slot_qt_se_registra_y_app_sigue(entorno, qapp, qtbot):
    from PySide6.QtCore import QTimer

    instalar_captura_de_fallos(entorno.carpeta)
    ejecutado = []

    def slot_roto():
        raise RuntimeError("fallo-en-slot")

    QTimer.singleShot(0, slot_roto)
    QTimer.singleShot(0, lambda: ejecutado.append(True))
    qtbot.waitUntil(lambda: bool(ejecutado), timeout=2000)
    qapp.processEvents()
    texto = _log(entorno.carpeta)
    assert "fallo-en-slot" in texto
    assert "Error no controlado" in texto
    assert ejecutado == [True]  # el bucle siguió procesando eventos


# --- R3 ---------------------------------------------------------------------------------


def test_r3_excepcion_en_hilo_con_nombre(entorno):
    instalar_captura_de_fallos(entorno.carpeta)

    def objetivo():
        raise KeyError("fallo-hilo")

    hilo = threading.Thread(target=objetivo, name="trabajador-prueba")
    hilo.start()
    hilo.join()
    texto = _log(entorno.carpeta)
    assert "CRITICAL" in texto
    assert "trabajador-prueba" in texto
    assert "fallo-hilo" in texto
    assert entorno.hilo == ["trabajador-prueba"]


def test_r3_systemexit_en_hilo_no_se_registra(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    hilo = threading.Thread(target=lambda: sys.exit(3), name="sale")
    hilo.start()
    hilo.join()
    assert "sale" not in _log(entorno.carpeta)
    assert "Error no controlado" not in _log(entorno.carpeta)


def test_r3_keyboardinterrupt_se_delega_sin_registrar(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    sys.excepthook(*_lanzar(KeyboardInterrupt()))
    assert entorno.sys == [KeyboardInterrupt]
    assert "Error no controlado" not in _log(entorno.carpeta)


def test_r3_unraisable_se_registra_como_warning(entorno):
    instalar_captura_de_fallos(entorno.carpeta)

    class Roto:
        def __del__(self):
            raise RuntimeError("fallo-del")

    Roto()
    texto = _log(entorno.carpeta)
    assert "WARNING proxlaunch.fallos" in texto
    assert "fallo-del" in texto


# --- R4 ---------------------------------------------------------------------------------


def test_r4_secretos_enmascarados_en_la_traza(entorno):
    registrar_secreto("S3cretoRegistrado")
    instalar_captura_de_fallos(entorno.carpeta)
    sys.excepthook(*_lanzar(RuntimeError("login password=xyz789 y S3cretoRegistrado")))
    texto = _log(entorno.carpeta)
    assert "RuntimeError" in texto
    assert "xyz789" not in texto
    assert "S3cretoRegistrado" not in texto
    assert "***" in texto


def test_r4_secretos_enmascarados_en_hilos(entorno):
    registrar_secreto("OtroSecreto42")
    instalar_captura_de_fallos(entorno.carpeta)

    def objetivo():
        raise RuntimeError("token OtroSecreto42")

    hilo = threading.Thread(target=objetivo, name="h-secreto")
    hilo.start()
    hilo.join()
    assert "OtroSecreto42" not in _log(entorno.carpeta)


# --- R5 ---------------------------------------------------------------------------------


def test_r5_sin_stderr_los_hooks_no_fallan_ni_encadenan(entorno, monkeypatch):
    instalar_captura_de_fallos(entorno.carpeta)
    monkeypatch.setattr(sys, "stderr", None)
    sys.excepthook(*_lanzar(ValueError("sin-stderr")))
    hilo = threading.Thread(target=lambda: 1 / 0, name="h-sin-stderr")
    hilo.start()
    hilo.join()
    assert entorno.sys == []
    assert entorno.hilo == []
    monkeypatch.undo()
    texto = _log(entorno.carpeta)
    assert "sin-stderr" in texto
    assert "h-sin-stderr" in texto


def test_r5_con_stderr_encadena_hilo_y_sys(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    sys.excepthook(*_lanzar(ValueError("a")))
    hilo = threading.Thread(target=lambda: 1 / 0, name="h-con-stderr")
    hilo.start()
    hilo.join()
    assert entorno.sys == [ValueError]
    assert entorno.hilo == ["h-con-stderr"]


# --- R6 ---------------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="Los permisos 0o600 solo se comprueban en POSIX")
def test_r6_archivo_fallo_nativo_privado(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    ruta = entorno.carpeta / ARCHIVO_FALLO_NATIVO
    assert ruta.is_file()
    assert (ruta.stat().st_mode & 0o777) == 0o600


def test_r6_previo_con_contenido_se_rota_y_avisa(entorno):
    entorno.carpeta.mkdir(parents=True, exist_ok=True)
    (entorno.carpeta / ARCHIVO_FALLO_NATIVO).write_text("Segmentation fault previo", "utf-8")
    instalar_captura_de_fallos(entorno.carpeta)
    rotado = entorno.carpeta / f"{ARCHIVO_FALLO_NATIVO}.1"
    assert rotado.read_text("utf-8") == "Segmentation fault previo"
    assert (entorno.carpeta / ARCHIVO_FALLO_NATIVO).stat().st_size == 0
    texto = _log(entorno.carpeta)
    assert "WARNING" in texto
    assert "La ejecución anterior terminó con un fallo nativo; ver fallo-nativo.txt.1" in texto


def test_r6_previo_vacio_no_rota_ni_avisa(entorno):
    entorno.carpeta.mkdir(parents=True, exist_ok=True)
    (entorno.carpeta / ARCHIVO_FALLO_NATIVO).write_text("", "utf-8")
    instalar_captura_de_fallos(entorno.carpeta)
    assert not (entorno.carpeta / f"{ARCHIVO_FALLO_NATIVO}.1").exists()
    assert "fallo nativo" not in _log(entorno.carpeta)


def test_r6_archivo_nuevo_sin_previo_no_avisa(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    assert "fallo nativo" not in _log(entorno.carpeta)


def test_r6_el_archivo_se_trunca_en_cada_instalacion(entorno):
    entorno.carpeta.mkdir(parents=True, exist_ok=True)
    (entorno.carpeta / ARCHIVO_FALLO_NATIVO).write_text("viejo", "utf-8")
    instalar_captura_de_fallos(entorno.carpeta)
    assert (entorno.carpeta / ARCHIVO_FALLO_NATIVO).read_text("utf-8") == ""


@pytest.mark.skipif(
    sys.platform == "win32", reason="El volcado por señal se valida en POSIX; Windows usa otra ruta"
)
@pytest.mark.parametrize("provocar", ["faulthandler._sigsegv()", "ctypes.string_at(0)"])
def test_r6_fallo_nativo_real_en_subproceso_y_rotacion(entorno, tmp_path, provocar):
    carpeta = tmp_path / "log-subproceso"
    codigo = textwrap.dedent(
        f"""
        import ctypes, faulthandler, sys
        from proxlaunch.nucleo.registro import instalar_captura_de_fallos
        instalar_captura_de_fallos(sys.argv[1])
        {provocar}
        """
    )
    entorno_hijo = dict(os.environ)
    entorno_hijo["PYTHONPATH"] = str(RAIZ / "src") + os.pathsep + entorno_hijo.get("PYTHONPATH", "")
    try:
        proceso = subprocess.run(
            [sys.executable, "-c", codigo, str(carpeta)],
            env=entorno_hijo,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        pytest.skip(f"La plataforma no permite lanzar el subproceso: {exc}")
    assert proceso.returncode != 0
    contenido = (carpeta / ARCHIVO_FALLO_NATIVO).read_text("utf-8", errors="replace")
    assert "Segmentation fault" in contenido or "Fatal Python error" in contenido

    # Siguiente arranque (en este proceso): se rota y se avisa.
    configurar_registro(carpeta)
    instalar_captura_de_fallos(carpeta)
    rotado = carpeta / f"{ARCHIVO_FALLO_NATIVO}.1"
    assert rotado.read_text("utf-8", errors="replace") == contenido
    assert "ver fallo-nativo.txt.1" in _log(carpeta)


# --- R7 ---------------------------------------------------------------------------------


class _InstaladorFalso:
    """Instalador de Qt falso: captura el receptor y anota la restauración."""

    def __init__(self) -> None:
        self.receptor = None
        self.restaurado = False

    def __call__(self, receptor):
        self.receptor = receptor

        def restaurar():
            self.restaurado = True

        return restaurar


def _lineas_qt(carpeta: Path) -> list[str]:
    return [ln for ln in _log(carpeta).splitlines() if "proxlaunch.qt" in ln]


@pytest.fixture
def receptor(entorno):
    instalador = _InstaladorFalso()
    instalar_captura_de_fallos(entorno.carpeta, instalador)
    return instalador.receptor


def test_r7_niveles_mapeados_y_prefijo_de_categoria(entorno, receptor):
    receptor(logging.WARNING, "qt.test", "aviso")
    receptor(logging.ERROR, None, "critico")
    receptor(logging.DEBUG, "default", "depuracion")  # DEBUG no llega con nivel INFO
    receptor(logging.CRITICAL, "default", "fatal")
    lineas = _lineas_qt(entorno.carpeta)
    assert any("WARNING" in ln and ln.endswith("[qt.test] aviso") for ln in lineas)
    assert any("ERROR" in ln and ln.endswith("proxlaunch.qt: critico") for ln in lineas)
    assert any("CRITICAL" in ln and ln.endswith("proxlaunch.qt: fatal") for ln in lineas)
    assert not any("default" in ln for ln in lineas)
    assert not any("depuracion" in ln for ln in lineas)


def test_r7_debug_se_registra_con_nivel_debug(entorno, receptor):
    logging.getLogger("proxlaunch").setLevel(logging.DEBUG)
    receptor(logging.DEBUG, None, "detalle")
    assert any("DEBUG" in ln and "detalle" in ln for ln in _lineas_qt(entorno.carpeta))


def test_r7_treinta_identicos_dan_veinte_lineas_y_resumen(entorno, receptor):
    for _ in range(30):
        receptor(logging.WARNING, None, "repetido")
    receptor(logging.WARNING, None, "distinto")
    lineas = _lineas_qt(entorno.carpeta)
    assert sum(ln.endswith("proxlaunch.qt: repetido") for ln in lineas) == MAX_MENSAJES_QT_REPETIDOS
    assert sum("(mensaje de Qt repetido 10 veces más)" in ln for ln in lineas) == 1
    assert lineas[-1].endswith("distinto")


def test_r7_exactamente_veinte_no_genera_resumen(entorno, receptor):
    for _ in range(MAX_MENSAJES_QT_REPETIDOS):
        receptor(logging.WARNING, None, "justo")
    receptor(logging.WARNING, None, "otro")
    assert "repetido" not in _log(entorno.carpeta)


def test_r7_no_consecutivos_no_se_suprimen(entorno, receptor):
    for _ in range(15):
        receptor(logging.WARNING, None, "a")
        receptor(logging.WARNING, None, "b")
    assert len(_lineas_qt(entorno.carpeta)) == 30


def test_r7_fatal_hace_flush(entorno, receptor, monkeypatch):
    """Un mensaje fatal vacía los manejadores del registro (además del flush de cada emit)."""
    manejador = next(
        h for h in logging.getLogger("proxlaunch").handlers if getattr(h, "_proxlaunch", False)
    )
    llamadas = []
    monkeypatch.setattr(manejador, "flush", lambda: llamadas.append(1))
    # Se aísla la llamada interna de emit() para contar solo los flush explícitos del receptor.
    monkeypatch.setattr(manejador, "emit", lambda registro: None)
    receptor(logging.WARNING, None, "no fatal")
    assert llamadas == []
    receptor(logging.CRITICAL, None, "muerte")
    assert llamadas == [1]


def test_r7_el_receptor_enmascara_secretos(entorno, receptor):
    receptor(logging.WARNING, None, "password=abc123")
    assert "abc123" not in _log(entorno.carpeta)


# --- R8 ---------------------------------------------------------------------------------


def test_r8_instalar_dos_veces_no_duplica_registros(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    hooks = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    instalar_captura_de_fallos(entorno.carpeta)
    assert (sys.excepthook, threading.excepthook, sys.unraisablehook) == hooks
    sys.excepthook(*_lanzar(ValueError("una-sola-vez")))
    assert _log(entorno.carpeta).count("Error no controlado") == 1
    assert entorno.sys == [ValueError]


def test_r8_instalar_dos_veces_no_reabre_el_archivo(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    archivo = registro._estado.archivo_fallo
    instalar_captura_de_fallos(entorno.carpeta)
    assert registro._estado.archivo_fallo is archivo
    assert not archivo.closed
    assert not (entorno.carpeta / f"{ARCHIVO_FALLO_NATIVO}.1").exists()


def test_r8_instalar_dos_veces_llama_una_vez_al_instalador_qt(entorno):
    instalador = _InstaladorFalso()
    llamadas = []

    def contador(rec):
        llamadas.append(1)
        return instalador(rec)

    instalar_captura_de_fallos(entorno.carpeta, contador)
    instalar_captura_de_fallos(entorno.carpeta, contador)
    assert llamadas == [1]


def test_r8_desinstalar_restaura_hooks_y_faulthandler(entorno):
    antes = faulthandler.is_enabled()
    instalar_captura_de_fallos(entorno.carpeta)
    assert faulthandler.is_enabled()
    assert sys.excepthook is not entorno.falsos[0]
    archivo = registro._estado.archivo_fallo
    desinstalar_captura_de_fallos()
    assert (sys.excepthook, threading.excepthook, sys.unraisablehook) == entorno.falsos
    assert faulthandler.is_enabled() == antes
    assert archivo.closed


def test_r8_desinstalar_restaura_faulthandler_deshabilitado(entorno):
    previo = faulthandler.is_enabled()
    faulthandler.disable()
    try:
        instalar_captura_de_fallos(entorno.carpeta)
        desinstalar_captura_de_fallos()
        assert not faulthandler.is_enabled()
    finally:
        if previo:
            faulthandler.enable()


def test_r8_desinstalar_restaura_el_manejador_qt(entorno):
    instalador = _InstaladorFalso()
    instalar_captura_de_fallos(entorno.carpeta, instalador)
    desinstalar_captura_de_fallos()
    assert instalador.restaurado


def test_r8_desinstalar_sin_instalar_no_falla(entorno):
    desinstalar_captura_de_fallos()
    desinstalar_captura_de_fallos()
    assert (sys.excepthook, threading.excepthook, sys.unraisablehook) == entorno.falsos


def test_r8_tras_desinstalar_ya_no_registra(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    desinstalar_captura_de_fallos()
    sys.excepthook(*_lanzar(ValueError("tras-desinstalar")))
    assert "tras-desinstalar" not in _log(entorno.carpeta)


def test_r8_otra_carpeta_reinstala_y_cierra_el_archivo_anterior(entorno, tmp_path):
    instalar_captura_de_fallos(entorno.carpeta)
    primero = registro._estado.archivo_fallo
    otra = tmp_path / "otra"
    instalar_captura_de_fallos(otra)
    assert primero.closed
    assert (otra / ARCHIVO_FALLO_NATIVO).is_file()
    assert sys.excepthook is registro._estado.hook_sys
