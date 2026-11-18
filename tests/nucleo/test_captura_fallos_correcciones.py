"""Correcciones de revisión de la captura de cierres inesperados (C3, C5-C8 y C10).

Se derivan del contrato público de ``instalar_captura_de_fallos``/``desinstalar_captura_de_fallos``:
cierre limpio sin falsas alarmas, instalación robusta, encadenado enmascarado, receptor de Qt sin
interbloqueos, avalanchas acotadas y archivo de volcado privado.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
import types
import weakref
from pathlib import Path

import pytest

from proxlaunch.nucleo import registro
from proxlaunch.nucleo.registro import (
    ARCHIVO_FALLO_NATIVO,
    ARCHIVO_LOG,
    MAX_BYTES_FALLO_PREVIO,
    MAX_EXCEPCIONES_REPETIDAS,
    MAX_MENSAJES_QT_REPETIDOS,
    cerrar_registro,
    configurar_registro,
    desinstalar_captura_de_fallos,
    instalar_captura_de_fallos,
    registrar_secreto,
)

PREVIO = f"{ARCHIVO_FALLO_NATIVO}.1"


class _Previos:
    """Hooks previos falsos que cuentan las llamadas (hook personalizado de otra librería)."""

    def __init__(self) -> None:
        self.sys: list[BaseException] = []
        self.hilo: list[str] = []

    def instalar(self) -> None:
        sys.excepthook = lambda t, v, tb: self.sys.append(v)
        threading.excepthook = lambda a: self.hilo.append(a.thread.name)


def _restaurar(originales) -> None:
    sys.excepthook, threading.excepthook, sys.unraisablehook = originales


@pytest.fixture
def entorno(tmp_path):
    """Carpeta de log temporal y hooks previos falsos; garantiza la desinstalación."""
    originales = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    desinstalar_captura_de_fallos()
    previos = _Previos()
    previos.instalar()
    previos.carpeta = tmp_path / "log"
    configurar_registro(previos.carpeta)
    yield previos
    desinstalar_captura_de_fallos()
    cerrar_registro()
    _restaurar(originales)


@pytest.fixture
def entorno_defecto(tmp_path):
    """Como ``entorno`` pero con los hooks por defecto de Python como «previos»."""
    originales = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    desinstalar_captura_de_fallos()
    sys.excepthook = sys.__excepthook__
    threading.excepthook = threading.__excepthook__
    sys.unraisablehook = sys.__unraisablehook__
    carpeta = tmp_path / "log"
    configurar_registro(carpeta)
    yield carpeta
    desinstalar_captura_de_fallos()
    cerrar_registro()
    _restaurar(originales)


def _log(carpeta: Path) -> str:
    ruta = carpeta / ARCHIVO_LOG
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


def _lanzar(excepcion: BaseException):
    try:
        raise excepcion
    except BaseException:
        return sys.exc_info()


def _previo_con(carpeta: Path, contenido: bytes) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / ARCHIVO_FALLO_NATIVO).write_bytes(contenido)


# --- C3: cierre limpio y veredicto del volcado previo ------------------------------------


def test_c3_cierre_limpio_elimina_fallo_nativo(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    assert (entorno.carpeta / ARCHIVO_FALLO_NATIVO).exists()
    desinstalar_captura_de_fallos(limpio=True)
    assert not (entorno.carpeta / ARCHIVO_FALLO_NATIVO).exists()


def test_c3_cierre_no_limpio_conserva_fallo_nativo(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    desinstalar_captura_de_fallos(limpio=False)
    assert (entorno.carpeta / ARCHIVO_FALLO_NATIVO).exists()


def test_c3_por_defecto_la_desinstalacion_no_borra(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    desinstalar_captura_de_fallos()
    assert (entorno.carpeta / ARCHIVO_FALLO_NATIVO).exists()


def test_c3_tras_un_cierre_limpio_el_siguiente_arranque_no_avisa(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    desinstalar_captura_de_fallos(limpio=True)
    instalar_captura_de_fallos(entorno.carpeta)
    assert "fallo nativo" not in _log(entorno.carpeta)
    assert "excepciones nativas" not in _log(entorno.carpeta)
    assert not (entorno.carpeta / PREVIO).exists()


def test_c3_cierre_limpio_sin_instalar_no_falla(entorno):
    desinstalar_captura_de_fallos(limpio=True)


def test_c3a_solo_excepcion_nativa_manejada_es_info_y_no_warning(entorno):
    contenido = (
        "Windows fatal exception: code 0x8001010d\n\n"
        'Current thread 0x00001234 (most recent call first):\n  File "x.py", line 1 in f\n'
    )
    _previo_con(entorno.carpeta, contenido.encode())
    instalar_captura_de_fallos(entorno.carpeta)
    texto = _log(entorno.carpeta)
    lineas = [ln for ln in texto.splitlines() if "proxlaunch.fallos" in ln]
    assert any(" INFO " in ln and "excepciones nativas manejadas" in ln for ln in lineas)
    assert not any("terminó con un fallo nativo" in ln for ln in lineas)
    assert not any(" WARNING " in ln for ln in lineas)
    assert (entorno.carpeta / PREVIO).read_bytes() == contenido.encode()


@pytest.mark.parametrize(
    "contenido",
    [
        "Fatal Python error: Segmentation fault\n\nCurrent thread 0x1 (most recent call first):\n",
        "Windows fatal exception: access violation\n\nCurrent thread 0x1:\n",
        "Windows fatal exception: code 0x8001010d\nFatal Python error: Aborted\n",
        "Windows fatal exception: stack overflow\n",
    ],
)
def test_c3b_indicios_de_caida_real_dan_warning(entorno, contenido):
    _previo_con(entorno.carpeta, contenido.encode())
    instalar_captura_de_fallos(entorno.carpeta)
    lineas = [ln for ln in _log(entorno.carpeta).splitlines() if "proxlaunch.fallos" in ln]
    assert any(" WARNING " in ln and "terminó con un fallo nativo" in ln for ln in lineas)
    assert not any("excepciones nativas manejadas" in ln for ln in lineas)


def test_c3b_texto_sin_cabecera_windows_se_trata_como_caida(entorno):
    _previo_con(entorno.carpeta, b"volcado desconocido\n")
    instalar_captura_de_fallos(entorno.carpeta)
    assert "terminó con un fallo nativo" in _log(entorno.carpeta)


def test_c3c_contenido_enorme_se_trunca_a_256_kb_en_el_previo(entorno):
    assert MAX_BYTES_FALLO_PREVIO == 256 * 1024
    inicio = b"Fatal Python error: Segmentation fault\n"
    relleno = b"x" * (MAX_BYTES_FALLO_PREVIO * 2)
    _previo_con(entorno.carpeta, inicio + relleno)
    instalar_captura_de_fallos(entorno.carpeta)
    rotado = (entorno.carpeta / PREVIO).read_bytes()
    assert len(rotado) == MAX_BYTES_FALLO_PREVIO
    assert rotado.startswith(inicio)  # se conserva el INICIO del volcado
    assert (entorno.carpeta / ARCHIVO_FALLO_NATIVO).stat().st_size == 0


def test_c3c_contenido_justo_en_el_limite_no_se_recorta(entorno):
    datos = b"Fatal Python error: x\n".ljust(MAX_BYTES_FALLO_PREVIO, b"y")
    _previo_con(entorno.carpeta, datos)
    instalar_captura_de_fallos(entorno.carpeta)
    assert (entorno.carpeta / PREVIO).read_bytes() == datos


def test_c3_volcado_previo_con_bytes_no_utf8_no_impide_instalar(entorno):
    _previo_con(entorno.carpeta, b"Fatal Python error: \xff\xfe\x80 Segmentation fault\n")
    instalar_captura_de_fallos(entorno.carpeta)
    assert "terminó con un fallo nativo" in _log(entorno.carpeta)


# --- C5: instalación robusta -------------------------------------------------------------


def test_c5_si_instalar_qt_lanza_avisa_y_los_hooks_siguen_instalados(entorno):
    def instalador_roto(_receptor):
        raise RuntimeError("qt-no-disponible")

    anteriores = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    instalar_captura_de_fallos(entorno.carpeta, instalador_roto)  # no debe lanzar
    texto = _log(entorno.carpeta)
    assert "WARNING" in texto
    assert "qt-no-disponible" in texto
    assert sys.excepthook is registro._estado.hook_sys
    sys.excepthook(*_lanzar(ValueError("tras-fallo-qt")))
    assert "tras-fallo-qt" in _log(entorno.carpeta)

    desinstalar_captura_de_fallos()
    assert (sys.excepthook, threading.excepthook, sys.unraisablehook) == anteriores


def test_c5_reinstalar_tras_fallo_de_qt_no_duplica_hooks(entorno):
    def instalador_roto(_receptor):
        raise RuntimeError("qt-no-disponible")

    instalar_captura_de_fallos(entorno.carpeta, instalador_roto)
    desinstalar_captura_de_fallos()
    instalar_captura_de_fallos(entorno.carpeta)
    sys.excepthook(*_lanzar(ValueError("una-sola")))
    assert _log(entorno.carpeta).count("Error no controlado") == 1
    assert len(entorno.sys) == 1  # el hook previo se llama una sola vez (sin cadenas dobles)
    desinstalar_captura_de_fallos()
    sys.excepthook(*_lanzar(ValueError("ya-no")))
    assert "ya-no" not in _log(entorno.carpeta)
    assert len(entorno.sys) == 2


def test_c5_si_faulthandler_enable_lanza_avisa_y_sigue(entorno, monkeypatch):
    def falla(*_a, **_k):
        raise RuntimeError("faulthandler-no-disponible")

    monkeypatch.setattr(faulthandler, "enable", falla)
    llamadas: list[object] = []

    def instalador(receptor):
        llamadas.append(receptor)
        return lambda: None

    instalar_captura_de_fallos(entorno.carpeta, instalador)  # no debe lanzar
    texto = _log(entorno.carpeta)
    assert "WARNING" in texto
    assert "faulthandler-no-disponible" in texto
    assert sys.excepthook is registro._estado.hook_sys
    sys.excepthook(*_lanzar(ValueError("sigue-vivo")))
    assert "sigue-vivo" in _log(entorno.carpeta)
    assert len(llamadas) == 1  # Qt se instala aunque faulthandler haya fallado
    desinstalar_captura_de_fallos()  # no lanza y restaura


def test_c5_si_no_se_puede_abrir_el_archivo_de_fallo_avisa_y_sigue(entorno, monkeypatch):
    def falla(*_a, **_k):
        raise OSError("disco-lleno")

    monkeypatch.setattr(registro, "_abrir_archivo_fallo", falla)
    instalar_captura_de_fallos(entorno.carpeta)
    assert "disco-lleno" in _log(entorno.carpeta)
    sys.excepthook(*_lanzar(ValueError("aun-registra")))
    assert "aun-registra" in _log(entorno.carpeta)


# --- C6: encadenado -----------------------------------------------------------------------


def test_c6_hook_por_defecto_escribe_en_stderr_enmascarado(entorno_defecto, capsys):
    registrar_secreto("S3cretoDeLaPrueba")
    instalar_captura_de_fallos(entorno_defecto)
    sys.excepthook(*_lanzar(RuntimeError("login password=xyz789 con S3cretoDeLaPrueba")))
    err = capsys.readouterr().err
    assert "RuntimeError" in err  # sí se imprime la traza
    assert "xyz789" not in err
    assert "S3cretoDeLaPrueba" not in err
    assert "***" in err


def test_c6_hook_de_hilo_por_defecto_escribe_en_stderr_enmascarado(entorno_defecto, capsys):
    registrar_secreto("OtroSecretoHilo")
    instalar_captura_de_fallos(entorno_defecto)

    def objetivo():
        raise RuntimeError("password=abc123 OtroSecretoHilo")

    hilo = threading.Thread(target=objetivo, name="hilo-c6")
    hilo.start()
    hilo.join()
    err = capsys.readouterr().err
    assert "hilo-c6" in err
    assert "abc123" not in err
    assert "OtroSecretoHilo" not in err


def test_c6_unraisable_por_defecto_escribe_en_stderr_enmascarado(entorno_defecto, capsys):
    registrar_secreto("SecretoUnraisable")
    instalar_captura_de_fallos(entorno_defecto)
    sys.unraisablehook(
        types.SimpleNamespace(
            exc_type=RuntimeError,
            exc_value=RuntimeError("password=zzz SecretoUnraisable"),
            exc_traceback=None,
            err_msg="Exception ignored in",
            object=None,
        )
    )
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "SecretoUnraisable" not in err
    assert "zzz" not in err


def test_c6_con_hook_previo_personalizado_se_llama_a_ese_hook(entorno, capsys):
    instalar_captura_de_fallos(entorno.carpeta)
    error = ValueError("para-el-previo")
    sys.excepthook(*_lanzar(error))
    assert entorno.sys == [error]
    assert capsys.readouterr().err == ""  # el nuestro no imprime: delega en el previo
    hilo = threading.Thread(target=lambda: 1 / 0, name="hilo-previo")
    hilo.start()
    hilo.join()
    assert entorno.hilo == ["hilo-previo"]


def test_c6_con_stderr_none_no_se_escribe_ni_se_encadena(entorno_defecto, monkeypatch):
    # Hook por defecto + stderr None: no hay dónde escribir y no debe lanzar.
    instalar_captura_de_fallos(entorno_defecto)
    monkeypatch.setattr(sys, "stderr", None)
    sys.excepthook(*_lanzar(ValueError("sin-consola")))
    hilo = threading.Thread(target=lambda: 1 / 0, name="hilo-sin-consola")
    hilo.start()
    hilo.join()
    monkeypatch.undo()
    texto = _log(entorno_defecto)
    assert "sin-consola" in texto
    assert "hilo-sin-consola" in texto


def test_c6_con_hook_personalizado_y_stderr_none_no_se_encadena(entorno, monkeypatch):
    instalar_captura_de_fallos(entorno.carpeta)
    monkeypatch.setattr(sys, "stderr", None)
    sys.excepthook(*_lanzar(ValueError("a")))
    assert entorno.sys == []
    monkeypatch.undo()
    assert "ValueError: a" in _log(entorno.carpeta)


def test_c6_unraisable_incluye_repr_del_objeto_recortado_a_200(entorno_defecto):
    instalar_captura_de_fallos(entorno_defecto)

    class Grande:
        def __repr__(self) -> str:
            return "Z" * 1000

    sys.unraisablehook(
        types.SimpleNamespace(
            exc_type=RuntimeError,
            exc_value=RuntimeError("fallo-del"),
            exc_traceback=None,
            err_msg="Exception ignored in",
            object=Grande(),
        )
    )
    texto = _log(entorno_defecto)
    assert "(objeto: " in texto
    zetas = max(len(t) for t in texto.replace("(objeto: ", " ").split() if set(t) <= {"Z", ")"})
    assert 0 < zetas <= 201  # 200 caracteres de repr (+ el paréntesis de cierre)
    assert "Z" * 201 not in texto


def test_c6_unraisable_con_repr_que_lanza_no_impide_registrar(entorno_defecto):
    instalar_captura_de_fallos(entorno_defecto)

    class Roto:
        def __repr__(self) -> str:
            raise ValueError("repr-roto")

    sys.unraisablehook(
        types.SimpleNamespace(
            exc_type=RuntimeError,
            exc_value=RuntimeError("fallo-con-repr-roto"),
            exc_traceback=None,
            err_msg=None,
            object=Roto(),
        )
    )
    assert "fallo-con-repr-roto" in _log(entorno_defecto)


def test_c6_unraisable_real_de_un_callback_de_weakref_se_registra_con_su_mensaje(entorno):
    """Caso real: en CPython 3.14 ``object`` es None aquí; el callback va en ``err_msg``."""
    sys.unraisablehook = lambda _args: None  # hook previo mudo (el fixture restaura el original)
    instalar_captura_de_fallos(entorno.carpeta)

    class Dueno:
        pass

    def callback_c6(_ref):
        raise RuntimeError("callback-roto")

    dueno = Dueno()
    referencia = weakref.ref(dueno, callback_c6)
    del dueno
    assert referencia() is None
    texto = _log(entorno.carpeta)
    assert "callback-roto" in texto
    assert "(objeto: " in texto  # el sufijo siempre está, aunque el objeto sea None
    assert "callback_c6" in texto


# --- C7: receptor de Qt sin interbloqueos --------------------------------------------------


class _InstaladorFalso:
    def __init__(self) -> None:
        self.receptor = None

    def __call__(self, receptor):
        self.receptor = receptor
        return lambda: None


class _Reentrante(logging.Handler):
    """Al emitir un registro de Qt vuelve a llamar al receptor (reentrada desde el log)."""

    def __init__(self, receptor, disparador: str) -> None:
        super().__init__(logging.DEBUG)
        self.receptor = receptor
        self.disparador = disparador
        self.reentradas = 0

    def emit(self, record: logging.LogRecord) -> None:
        if self.disparador in record.getMessage() and self.reentradas == 0:
            self.reentradas += 1
            self.receptor(logging.WARNING, None, "reentrada")


def _con_tiempo_limite(funcion, segundos: float = 5.0) -> bool:
    """True si ``funcion`` terminó; False si sigue bloqueada (interbloqueo)."""
    hilo = threading.Thread(target=funcion, daemon=True)
    hilo.start()
    hilo.join(segundos)
    return not hilo.is_alive()


@pytest.fixture
def receptor(entorno):
    instalador = _InstaladorFalso()
    instalar_captura_de_fallos(entorno.carpeta, instalador)
    return instalador.receptor


def test_c7_emitir_un_mensaje_normal_no_ocurre_con_el_lock_tomado(entorno, receptor):
    manejador = _Reentrante(receptor, "normal")
    logger = logging.getLogger("proxlaunch.qt")
    logger.addHandler(manejador)
    try:
        assert _con_tiempo_limite(lambda: receptor(logging.WARNING, None, "mensaje normal"))
    finally:
        logger.removeHandler(manejador)
    assert manejador.reentradas == 1
    assert "reentrada" in _log(entorno.carpeta)


def test_c7_emitir_el_resumen_de_la_racha_no_ocurre_con_el_lock_tomado(entorno, receptor):
    manejador = _Reentrante(receptor, "repetido")
    logger = logging.getLogger("proxlaunch.qt")
    logger.addHandler(manejador)
    try:

        def secuencia():
            for _ in range(MAX_MENSAJES_QT_REPETIDOS + 5):
                receptor(logging.WARNING, None, "igual")
            receptor(logging.WARNING, None, "distinto")  # cierra la racha: emite el resumen

        assert _con_tiempo_limite(secuencia)
    finally:
        logger.removeHandler(manejador)
    assert manejador.reentradas == 1
    assert "repetido 5 veces más" in _log(entorno.carpeta)


def test_c7_un_mensaje_fatal_reentrante_tampoco_se_bloquea(entorno, receptor):
    manejador = _Reentrante(receptor, "fatal")
    logger = logging.getLogger("proxlaunch.qt")
    logger.addHandler(manejador)
    try:
        assert _con_tiempo_limite(lambda: receptor(logging.CRITICAL, None, "fatal"))
    finally:
        logger.removeHandler(manejador)
    assert "fatal" in _log(entorno.carpeta)


def test_c7_la_racha_pendiente_se_resume_al_desinstalar(entorno, receptor):
    for _ in range(MAX_MENSAJES_QT_REPETIDOS + 7):
        receptor(logging.WARNING, None, "racha-abierta")
    assert "repetido" not in _log(entorno.carpeta)  # aún no se cierra la racha
    desinstalar_captura_de_fallos()
    texto = _log(entorno.carpeta)
    assert "(mensaje de Qt repetido 7 veces más)" in texto


def test_c7_racha_de_exactamente_el_maximo_no_genera_resumen_al_desinstalar(entorno, receptor):
    for _ in range(MAX_MENSAJES_QT_REPETIDOS):
        receptor(logging.WARNING, None, "justo")
    desinstalar_captura_de_fallos()
    assert "repetido" not in _log(entorno.carpeta)


def test_c7_el_receptor_es_seguro_con_varios_hilos(entorno, receptor):
    def trabajo():
        for i in range(200):
            receptor(logging.WARNING, None, f"hilo-{i % 3}")

    hilos = [threading.Thread(target=trabajo) for _ in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(10)
    assert not any(h.is_alive() for h in hilos)


# --- C8: avalancha de excepciones ----------------------------------------------------------


def _misma_linea(i: int) -> None:
    raise RuntimeError(f"igual-{i}")  # siempre la misma línea: misma clave (tipo, archivo, línea)


def _disparar_misma(veces: int) -> None:
    for i in range(veces):
        try:
            _misma_linea(i)
        except RuntimeError:
            sys.excepthook(*sys.exc_info())


def test_c8_treinta_iguales_dan_veinte_registros_y_resumen_al_desinstalar(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    _disparar_misma(30)
    assert _log(entorno.carpeta).count("Error no controlado") == MAX_EXCEPCIONES_REPETIDAS
    assert "suprimidas" not in _log(entorno.carpeta)  # el resumen llega al desinstalar
    desinstalar_captura_de_fallos()
    texto = _log(entorno.carpeta)
    assert texto.count("Error no controlado") == MAX_EXCEPCIONES_REPETIDAS
    assert texto.count("(suprimidas)") == 1
    assert f"repetida {30 - MAX_EXCEPCIONES_REPETIDAS} veces más" in texto
    assert "RuntimeError" in texto
    assert len(entorno.sys) == MAX_EXCEPCIONES_REPETIDAS  # lo suprimido tampoco se encadena


def test_c8_exactamente_el_maximo_no_genera_resumen(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    _disparar_misma(MAX_EXCEPCIONES_REPETIDAS)
    desinstalar_captura_de_fallos()
    texto = _log(entorno.carpeta)
    assert texto.count("Error no controlado") == MAX_EXCEPCIONES_REPETIDAS
    assert "suprimidas" not in texto


def test_c8_resumen_periodico_en_la_repeticion_cien(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    _disparar_misma(100)
    texto = _log(entorno.carpeta)
    assert texto.count("Error no controlado") == MAX_EXCEPCIONES_REPETIDAS
    assert f"repetida {100 - MAX_EXCEPCIONES_REPETIDAS} veces más" in texto
    desinstalar_captura_de_fallos()
    assert _log(entorno.carpeta).count("(suprimidas)") == 1  # ya estaba al día: no se repite


def test_c8_excepciones_distintas_no_se_suprimen(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    for i in range(30):
        tipo = type(f"ErrorDistinto{i}", (Exception,), {})
        sys.excepthook(*_lanzar(tipo(f"distinta-{i}")))
    desinstalar_captura_de_fallos()
    texto = _log(entorno.carpeta)
    assert texto.count("Error no controlado") == 30
    assert "suprimidas" not in texto


def test_c8_mismo_tipo_en_lineas_distintas_no_se_suprime(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    for _ in range(MAX_EXCEPCIONES_REPETIDAS + 5):
        try:
            raise RuntimeError("linea-a")  # una línea
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
    for _ in range(3):
        try:
            raise RuntimeError("linea-b")  # otra línea: cuenta aparte
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
    texto = _log(entorno.carpeta)
    assert texto.count("RuntimeError: linea-a") == MAX_EXCEPCIONES_REPETIDAS
    assert texto.count("RuntimeError: linea-b") == 3


def test_c8_la_avalancha_de_hilos_tambien_se_acota(entorno):
    instalar_captura_de_fallos(entorno.carpeta)

    def objetivo():
        raise KeyError("hilo-repetido")

    for _ in range(30):
        hilo = threading.Thread(target=objetivo, name="avalancha")
        hilo.start()
        hilo.join()
    assert _log(entorno.carpeta).count("Error no controlado en el hilo avalancha") == (
        MAX_EXCEPCIONES_REPETIDAS
    )


def test_c8_exc_text_con_cr_y_controles_se_escapa_y_conserva_los_saltos_de_linea(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    sys.excepthook(*_lanzar(RuntimeError("uno\rFALSA linea\x07fin\ndos")))
    desinstalar_captura_de_fallos()
    crudo = (entorno.carpeta / ARCHIVO_LOG).read_bytes()
    sin_crlf = crudo.replace(b"\r\n", b"\n")  # en Windows el archivo de texto usa CRLF
    assert b"\r" not in sin_crlf
    assert b"\x07" not in sin_crlf
    texto = sin_crlf.decode("utf-8")
    assert "\\x0d" in texto
    assert "\\x07" in texto
    assert "RuntimeError: uno\\x0dFALSA linea\\x07fin\ndos" in texto  # \n sí se conserva
    # El texto inyectado no inicia una línea con aspecto de registro propio.
    assert not any(ln.startswith("FALSA") for ln in texto.splitlines())


# --- C10: permisos y enlaces simbólicos (POSIX) ---------------------------------------------

posix = pytest.mark.skipif(os.name != "posix", reason="Permisos y enlaces simbólicos: solo POSIX")


@posix
def test_c10_fallo_nativo_nuevo_es_0600(entorno):
    instalar_captura_de_fallos(entorno.carpeta)
    assert ((entorno.carpeta / ARCHIVO_FALLO_NATIVO).stat().st_mode & 0o777) == 0o600


@posix
def test_c10_fallo_nativo_previo_con_permisos_amplios_queda_0600_y_su_rotado_tambien(entorno):
    _previo_con(entorno.carpeta, b"Fatal Python error: x\n")
    os.chmod(entorno.carpeta / ARCHIVO_FALLO_NATIVO, 0o644)
    instalar_captura_de_fallos(entorno.carpeta)
    assert ((entorno.carpeta / ARCHIVO_FALLO_NATIVO).stat().st_mode & 0o777) == 0o600
    assert ((entorno.carpeta / PREVIO).stat().st_mode & 0o777) == 0o600


@posix
def test_c10_enlace_simbolico_no_se_sigue_y_avisa(entorno, tmp_path):
    entorno.carpeta.mkdir(parents=True, exist_ok=True)
    victima = tmp_path / "victima.txt"
    victima.write_text("contenido-importante", "utf-8")
    (entorno.carpeta / ARCHIVO_FALLO_NATIVO).symlink_to(victima)
    instalar_captura_de_fallos(entorno.carpeta)  # no debe lanzar
    assert victima.read_text("utf-8") == "contenido-importante"  # no se truncó
    assert not (entorno.carpeta / PREVIO).exists()  # tampoco se copió su contenido
    assert "WARNING" in _log(entorno.carpeta)
    assert "No se pudo preparar" in _log(entorno.carpeta)
    sys.excepthook(*_lanzar(ValueError("sigue-funcionando")))
    assert "sigue-funcionando" in _log(entorno.carpeta)
    desinstalar_captura_de_fallos(limpio=True)
    assert victima.read_text("utf-8") == "contenido-importante"


@posix
def test_c10_enlace_simbolico_en_el_rotado_no_se_sigue(entorno, tmp_path):
    victima = tmp_path / "victima-rotado.txt"
    victima.write_text("no-tocar", "utf-8")
    _previo_con(entorno.carpeta, b"Fatal Python error: x\n")
    (entorno.carpeta / PREVIO).symlink_to(victima)
    instalar_captura_de_fallos(entorno.carpeta)
    assert victima.read_text("utf-8") == "no-tocar"
