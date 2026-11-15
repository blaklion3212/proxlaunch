"""Correcciones del MVP 5 en el núcleo: ``cerrar_registro`` y ``_marcar_danado`` con reintentos."""

from __future__ import annotations

import logging
import os
import types
from datetime import datetime

import pytest

from proxlaunch.nucleo.archivos import reemplazo
from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson
from proxlaunch.nucleo.registro import ARCHIVO_LOG, cerrar_registro, configurar_registro


@pytest.fixture
def logger_limpio():
    """Restaura el logger ``proxlaunch`` tras cada caso (manejadores y propagación)."""
    logger = logging.getLogger("proxlaunch")
    previos = list(logger.handlers)
    yield logger
    for h in list(logger.handlers):
        if h not in previos:
            logger.removeHandler(h)
            h.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


class _ManejadorAjeno(logging.Handler):
    """Manejador de otro componente: registra si alguien lo cierra."""

    def __init__(self) -> None:
        super().__init__()
        self.cerrado = False

    def emit(self, record: logging.LogRecord) -> None:
        pass

    def close(self) -> None:
        self.cerrado = True
        super().close()


# --- cerrar_registro ----------------------------------------------------------------------------


def test_cerrar_registro_quita_y_cierra_el_manejador_de_la_app(tmp_path, logger_limpio):
    logger = configurar_registro(tmp_path)
    propio = [h for h in logger.handlers if getattr(h, "_proxlaunch", False)]
    assert len(propio) == 1
    cerrar_registro()
    assert [h for h in logger.handlers if getattr(h, "_proxlaunch", False)] == []
    assert propio[0].stream is None  # el archivo quedó cerrado


def test_cerrar_registro_libera_el_archivo_y_ya_no_escribe(tmp_path, logger_limpio):
    logger = configurar_registro(tmp_path)
    logger.info("antes del cierre")
    cerrar_registro()
    archivo = tmp_path / ARCHIVO_LOG
    tamano = archivo.stat().st_size
    logger.info("después del cierre")
    assert archivo.stat().st_size == tamano
    # Con el archivo liberado la carpeta se puede borrar (en Windows exige que no esté abierto).
    archivo.unlink()


def test_cerrar_registro_no_toca_manejadores_ajenos(tmp_path, logger_limpio):
    ajeno = _ManejadorAjeno()
    logger_limpio.addHandler(ajeno)
    configurar_registro(tmp_path)
    cerrar_registro()
    assert ajeno in logger_limpio.handlers
    assert ajeno.cerrado is False


def test_cerrar_registro_no_toca_manejadores_marcados_de_otro_logger(tmp_path, logger_limpio):
    otro = logging.getLogger("otro-componente")
    marcado = _ManejadorAjeno()
    marcado._proxlaunch = True  # type: ignore[attr-defined]
    otro.addHandler(marcado)
    try:
        configurar_registro(tmp_path)
        cerrar_registro()
        assert marcado in otro.handlers and marcado.cerrado is False
    finally:
        otro.removeHandler(marcado)


def test_cerrar_registro_es_idempotente(tmp_path, logger_limpio):
    configurar_registro(tmp_path)
    cerrar_registro()
    cerrar_registro()  # segunda llamada: no hay nada que cerrar y no debe lanzar
    assert [h for h in logger_limpio.handlers if getattr(h, "_proxlaunch", False)] == []


def test_cerrar_registro_sin_configurar_no_hace_nada(logger_limpio):
    antes = list(logger_limpio.handlers)
    cerrar_registro()
    assert logger_limpio.handlers == antes


def test_cerrar_registro_tolera_un_manejador_cuyo_cierre_falla(logger_limpio):
    class Malo(logging.Handler):
        def emit(self, record):
            pass

        def close(self):
            raise OSError("cierre fallido")

    malo = Malo()
    malo._proxlaunch = True  # type: ignore[attr-defined]
    logger_limpio.addHandler(malo)
    cerrar_registro()  # no debe propagar
    assert malo not in logger_limpio.handlers


def test_se_puede_reconfigurar_tras_cerrar(tmp_path, logger_limpio):
    configurar_registro(tmp_path)
    cerrar_registro()
    logger = configurar_registro(tmp_path)
    logger.info("otra vez")
    assert "otra vez" in (tmp_path / ARCHIVO_LOG).read_text("utf-8")


# --- AlmacenJson._marcar_danado con reintentos --------------------------------------------------


def _almacen_danado(tmp_path):
    ruta = tmp_path / "datos.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    almacen = AlmacenJson(ruta, ahora=lambda: datetime(2026, 1, 2, 3, 4, 5))
    return ruta, almacen


def _fallo_winerror(winerror: int) -> PermissionError:
    falla = PermissionError(13, "violación de uso compartido")
    falla.winerror = winerror  # type: ignore[attr-defined]
    return falla


def _como_windows(monkeypatch) -> None:
    # Solo el módulo de reintentos ve «win32»; el resto de la suite no se altera.
    monkeypatch.setattr(reemplazo, "sys", types.SimpleNamespace(platform="win32"))


def test_marcar_danado_reintenta_ante_winerror_32_y_acaba_renombrando(tmp_path, monkeypatch):
    ruta, almacen = _almacen_danado(tmp_path)
    _como_windows(monkeypatch)
    real = os.replace
    intentos: list[int] = []

    def replace(origen, destino):
        intentos.append(1)
        if len(intentos) == 1:
            raise _fallo_winerror(32)
        real(origen, destino)

    monkeypatch.setattr(os, "replace", replace)
    resultado = almacen.leer()
    assert len(intentos) == 2
    assert resultado.hubo_corrupcion and not resultado.error_lectura
    assert resultado.copia_danada is not None and resultado.copia_danada.exists()
    assert resultado.copia_danada.name == "datos.json.danado-20260102-030405"
    assert not ruta.exists()


def test_marcar_danado_si_el_bloqueo_no_cede_informa_error_de_lectura(tmp_path, monkeypatch):
    ruta, almacen = _almacen_danado(tmp_path)
    _como_windows(monkeypatch)

    def replace(origen, destino):
        raise _fallo_winerror(32)

    monkeypatch.setattr(os, "replace", replace)
    resultado = almacen.leer()
    assert resultado.hubo_corrupcion and resultado.error_lectura
    assert resultado.copia_danada is None
    assert ruta.exists()  # el original sigue donde estaba


def test_marcar_danado_en_posix_no_reintenta(tmp_path, monkeypatch):
    ruta, almacen = _almacen_danado(tmp_path)
    monkeypatch.setattr(reemplazo, "sys", types.SimpleNamespace(platform="linux"))
    intentos: list[int] = []

    def replace(origen, destino):
        intentos.append(1)
        raise _fallo_winerror(32)

    monkeypatch.setattr(os, "replace", replace)
    resultado = almacen.leer()
    assert len(intentos) == 1
    assert resultado.error_lectura is True
