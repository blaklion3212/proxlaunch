"""Reemplazo con reintentos ante bloqueos transitorios de Windows y límite de ruta de 259.

``reemplazar_con_reintentos(origen, destino, dormir)``: solo en Windows (``sys.platform``) y solo
ante ``OSError`` con ``winerror`` 5, 32 o 33; hasta 8 intentos con espera exponencial y tope
total de 1 s. ``escribir_atomico`` y ``AlmacenJson.escribir`` lo usan. MAX_PATH (260) incluye el
NUL final: 259 caracteres se aceptan y 260 dan ``ruta_larga``.

Windows se simula sin tocar ``os.name`` globalmente (rompería ``pathlib``): se sustituye ``sys``
dentro de ``reemplazo`` y ``os`` dentro de ``escritura``.
"""

import errno
import functools
import os
import types
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos import escritura, reemplazo
from proxlaunch.nucleo.archivos.escritura import escribir_atomico
from proxlaunch.nucleo.archivos.reemplazo import (
    MAX_INTENTOS,
    TOPE_TOTAL_S,
    reemplazar_con_reintentos,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson


def _con_winerror(winerror: int | None) -> PermissionError:
    falla = PermissionError(errno.EACCES, "acceso denegado")
    if winerror is not None:
        falla.winerror = winerror  # type: ignore[attr-defined]
    return falla


def _plataforma(monkeypatch, nombre: str) -> None:
    monkeypatch.setattr(reemplazo, "sys", types.SimpleNamespace(platform=nombre))


class _ReemplazoFalso:
    """Sustituye ``os.replace``: falla las primeras ``fallos`` veces y luego delega en el real."""

    def __init__(self, fallos: int | None, winerror: int | None = 5) -> None:
        self.fallos = fallos  # None = falla siempre
        self.winerror = winerror
        self.llamadas = 0
        self._real = os.replace

    def __call__(self, origen, destino):
        self.llamadas += 1
        if self.fallos is None or self.llamadas <= self.fallos:
            raise _con_winerror(self.winerror)
        return self._real(origen, destino)


def _instalar(monkeypatch, fallos: int | None, winerror: int | None = 5) -> _ReemplazoFalso:
    falso = _ReemplazoFalso(fallos, winerror)
    monkeypatch.setattr(os, "replace", falso)
    return falso


def _archivos(tmp_path: Path) -> tuple[Path, Path]:
    origen = tmp_path / "origen.tmp"
    destino = tmp_path / "destino.json"
    origen.write_bytes(b"nuevo")
    destino.write_bytes(b"anterior")
    return origen, destino


# --- reemplazar_con_reintentos -------------------------------------------------


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_en_windows_un_bloqueo_transitorio_se_reintenta_y_luego_tiene_exito(
    tmp_path, monkeypatch, winerror
):
    _plataforma(monkeypatch, "win32")
    falso = _instalar(monkeypatch, fallos=1, winerror=winerror)
    origen, destino = _archivos(tmp_path)
    esperas: list[float] = []
    reemplazar_con_reintentos(origen, destino, dormir=esperas.append)
    assert falso.llamadas == 2
    assert len(esperas) == 1
    assert destino.read_bytes() == b"nuevo"
    assert not origen.exists()


def test_en_windows_varios_bloqueos_seguidos_y_luego_exito(tmp_path, monkeypatch):
    _plataforma(monkeypatch, "win32")
    falso = _instalar(monkeypatch, fallos=MAX_INTENTOS - 1)
    origen, destino = _archivos(tmp_path)
    reemplazar_con_reintentos(origen, destino, dormir=lambda _s: None)
    assert falso.llamadas == MAX_INTENTOS  # el último intento permitido sí cuenta
    assert destino.read_bytes() == b"nuevo"


def test_en_windows_al_agotar_los_reintentos_relanza_la_ultima_excepcion(tmp_path, monkeypatch):
    _plataforma(monkeypatch, "win32")
    falso = _instalar(monkeypatch, fallos=None)
    origen, destino = _archivos(tmp_path)
    with pytest.raises(PermissionError) as exc:
        reemplazar_con_reintentos(origen, destino, dormir=lambda _s: None)
    assert exc.value.winerror == 5  # type: ignore[attr-defined]
    assert falso.llamadas == MAX_INTENTOS  # ni uno más
    assert destino.read_bytes() == b"anterior"


@pytest.mark.parametrize("winerror", [None, 2, 3, 123, 1224])
def test_en_windows_un_winerror_distinto_no_se_reintenta(tmp_path, monkeypatch, winerror):
    _plataforma(monkeypatch, "win32")
    falso = _instalar(monkeypatch, fallos=None, winerror=winerror)
    origen, destino = _archivos(tmp_path)
    esperas: list[float] = []
    with pytest.raises(PermissionError):
        reemplazar_con_reintentos(origen, destino, dormir=esperas.append)
    assert falso.llamadas == 1
    assert esperas == []


def test_en_windows_un_oserror_sin_winerror_no_se_reintenta(tmp_path, monkeypatch):
    _plataforma(monkeypatch, "win32")
    llamadas = []

    def _falla(origen, destino):
        llamadas.append(1)
        raise OSError(errno.EIO, "fallo de disco")

    monkeypatch.setattr(os, "replace", _falla)
    origen, destino = _archivos(tmp_path)
    with pytest.raises(OSError, match="fallo de disco"):
        reemplazar_con_reintentos(origen, destino, dormir=lambda _s: None)
    assert len(llamadas) == 1


def test_en_windows_las_esperas_son_exponenciales_y_no_pasan_del_tope(tmp_path, monkeypatch):
    _plataforma(monkeypatch, "win32")
    _instalar(monkeypatch, fallos=None)
    origen, destino = _archivos(tmp_path)
    esperas: list[float] = []
    with pytest.raises(PermissionError):
        reemplazar_con_reintentos(origen, destino, dormir=esperas.append)
    assert len(esperas) == MAX_INTENTOS - 1  # se duerme entre intentos, no después del último
    assert esperas[0] == pytest.approx(0.005)
    for anterior, actual in zip(esperas, esperas[1:], strict=False):
        assert actual == pytest.approx(anterior * 2)
    assert sum(esperas) <= TOPE_TOTAL_S


def test_el_tope_total_de_un_segundo_corta_los_reintentos_antes_de_superarlo(tmp_path, monkeypatch):
    _plataforma(monkeypatch, "win32")
    # 0,3 + 0,6 = 0,9; la siguiente espera (1,2) pasaría del tope
    monkeypatch.setattr(reemplazo, "ESPERA_INICIAL_S", 0.3)
    falso = _instalar(monkeypatch, fallos=None)
    origen, destino = _archivos(tmp_path)
    esperas: list[float] = []
    with pytest.raises(PermissionError):
        reemplazar_con_reintentos(origen, destino, dormir=esperas.append)
    assert sum(esperas) <= TOPE_TOTAL_S
    assert esperas == [pytest.approx(0.3), pytest.approx(0.6)]
    assert falso.llamadas == 3


@pytest.mark.parametrize("plataforma", ["linux", "darwin"])
def test_en_posix_no_hay_reintentos(tmp_path, monkeypatch, plataforma):
    _plataforma(monkeypatch, plataforma)
    falso = _instalar(monkeypatch, fallos=None, winerror=5)
    origen, destino = _archivos(tmp_path)
    esperas: list[float] = []
    with pytest.raises(PermissionError):
        reemplazar_con_reintentos(origen, destino, dormir=esperas.append)
    assert falso.llamadas == 1
    assert esperas == []


def test_sin_fallos_reemplaza_a_la_primera_y_no_duerme(tmp_path, monkeypatch):
    _plataforma(monkeypatch, "win32")
    falso = _instalar(monkeypatch, fallos=0)
    origen, destino = _archivos(tmp_path)
    esperas: list[float] = []
    reemplazar_con_reintentos(origen, destino, dormir=esperas.append)
    assert falso.llamadas == 1
    assert esperas == []
    assert destino.read_bytes() == b"nuevo"


# --- escribir_atomico con reintentos --------------------------------------------------------------


class _OsWindows:
    """Vista de ``os`` que solo cambia ``name``; se sustituye únicamente dentro de ``escritura``."""

    name = "nt"

    def __getattr__(self, atributo: str):
        return getattr(os, atributo)


def _windows_en_escritura(monkeypatch) -> None:
    """Windows simulado y sin esperas reales en el reintento que usa ``escribir_atomico``."""
    monkeypatch.setattr(escritura, "os", _OsWindows())
    _plataforma(monkeypatch, "win32")
    monkeypatch.setattr(
        escritura,
        "reemplazar_con_reintentos",
        functools.partial(reemplazar_con_reintentos, dormir=lambda _s: None),
    )


def test_escribir_atomico_se_recupera_de_un_acceso_denegado_transitorio(tmp_path, monkeypatch):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _windows_en_escritura(monkeypatch)
    falso = _instalar(monkeypatch, fallos=1, winerror=5)
    escribir_atomico(destino, b"nuevo")
    assert falso.llamadas == 2
    assert destino.read_bytes() == b"nuevo"
    assert [p.name for p in tmp_path.iterdir()] == ["datos.json"]


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_escribir_atomico_al_agotar_los_reintentos_da_bloqueado_y_no_deja_el_temporal(
    tmp_path, monkeypatch, winerror
):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _windows_en_escritura(monkeypatch)
    falso = _instalar(monkeypatch, fallos=None, winerror=winerror)
    with pytest.raises(ErrorProxLaunch) as exc:
        escribir_atomico(destino, b"nuevo")
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    assert exc.value.params == {"motivo": "bloqueado"}
    assert falso.llamadas == MAX_INTENTOS
    assert destino.read_bytes() == b"anterior"
    assert [p.name for p in tmp_path.iterdir()] == ["datos.json"]  # temporal borrado


def test_escribir_atomico_con_otro_winerror_falla_a_la_primera(tmp_path, monkeypatch):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _windows_en_escritura(monkeypatch)
    falso = _instalar(monkeypatch, fallos=None, winerror=None)
    with pytest.raises(ErrorProxLaunch) as exc:
        escribir_atomico(destino, b"nuevo")
    assert exc.value.params == {"motivo": "sin_permiso"}
    assert falso.llamadas == 1
    assert [p.name for p in tmp_path.iterdir()] == ["datos.json"]


@pytest.mark.skipif(
    os.name != "posix",
    reason="control de POSIX: en Windows real el sistema sí reintenta y limita la ruta",
)
def test_escribir_atomico_en_posix_no_reintenta(tmp_path, monkeypatch):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _plataforma(monkeypatch, "linux")
    falso = _instalar(monkeypatch, fallos=None, winerror=5)
    with pytest.raises(ErrorProxLaunch) as exc:
        escribir_atomico(destino, b"nuevo")
    assert exc.value.params == {"motivo": "sin_permiso"}
    assert falso.llamadas == 1
    assert destino.read_bytes() == b"anterior"


# --- AlmacenJson.escribir con reintentos ----------------------------------------------------------


def test_almacen_json_con_bloqueo_transitorio_guarda_bien(tmp_path, monkeypatch):
    _plataforma(monkeypatch, "win32")
    monkeypatch.setattr(
        "proxlaunch.nucleo.persistencia.almacen_json.reemplazar_con_reintentos",
        functools.partial(reemplazar_con_reintentos, dormir=lambda _s: None),
    )
    almacen = AlmacenJson(tmp_path / "perfiles.json")
    almacen.escribir({"v": 1})
    falso = _instalar(monkeypatch, fallos=3, winerror=32)
    almacen.escribir({"v": 2, "ñ": "ü"})
    assert falso.llamadas == 4
    assert almacen.leer().datos == {"v": 2, "ñ": "ü"}
    assert [p.name for p in tmp_path.iterdir()] == ["perfiles.json"]


def test_almacen_json_con_bloqueo_persistente_relanza_el_oserror_y_conserva_lo_anterior(
    tmp_path, monkeypatch
):
    _plataforma(monkeypatch, "win32")
    monkeypatch.setattr(
        "proxlaunch.nucleo.persistencia.almacen_json.reemplazar_con_reintentos",
        functools.partial(reemplazar_con_reintentos, dormir=lambda _s: None),
    )
    almacen = AlmacenJson(tmp_path / "perfiles.json")
    almacen.escribir({"v": 1})
    falso = _instalar(monkeypatch, fallos=None, winerror=5)
    with pytest.raises(PermissionError):
        almacen.escribir({"v": 2})
    assert falso.llamadas == MAX_INTENTOS
    assert almacen.leer().datos == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["perfiles.json"]  # sin temporal


def test_almacen_json_en_posix_no_reintenta(tmp_path, monkeypatch):
    almacen = AlmacenJson(tmp_path / "perfiles.json")
    almacen.escribir({"v": 1})
    _plataforma(monkeypatch, "linux")
    falso = _instalar(monkeypatch, fallos=None, winerror=5)
    with pytest.raises(PermissionError):
        almacen.escribir({"v": 2})
    assert falso.llamadas == 1


# --- Límite de ruta: 259 se acepta, 260 es ruta_larga ---------------------------------------------


def _ruta_de_largo(tmp_path: Path, total: int) -> Path:
    """Destino de ``total`` caracteres cuya carpeta existe y cuyo nombre es largo (50+ chars).

    Con un nombre largo el destino, y no el temporal, es lo más largo que mide la app.
    """
    nombre = "n" * 50 + ".json"
    base = str(tmp_path)
    relleno = total - len(base) - 1 - 1 - len(nombre)
    assert relleno > 0
    carpeta = Path(base) / ("d" * relleno)
    carpeta.mkdir()
    ruta = carpeta / nombre
    assert len(str(ruta)) == total
    return ruta


def test_en_windows_una_ruta_de_259_caracteres_se_acepta(tmp_path, monkeypatch):
    ruta = _ruta_de_largo(tmp_path, 259)
    monkeypatch.setattr(escritura, "os", _OsWindows())
    escribir_atomico(ruta, b"contenido")
    assert ruta.read_bytes() == b"contenido"


def test_en_windows_una_ruta_de_260_caracteres_es_ruta_larga(tmp_path, monkeypatch):
    ruta = _ruta_de_largo(tmp_path, 260)
    monkeypatch.setattr(escritura, "os", _OsWindows())
    with pytest.raises(ErrorProxLaunch) as exc:
        escribir_atomico(ruta, b"contenido")
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    assert exc.value.params == {"motivo": "ruta_larga"}
    assert not ruta.exists()
    assert list(ruta.parent.iterdir()) == []  # ni temporal


@pytest.mark.skipif(
    os.name != "posix",
    reason="control de POSIX: en Windows real el sistema sí reintenta y limita la ruta",
)
def test_en_posix_una_ruta_de_260_caracteres_no_se_rechaza_por_longitud(tmp_path):
    ruta = _ruta_de_largo(tmp_path, 260)
    escribir_atomico(ruta, b"contenido")
    assert ruta.read_bytes() == b"contenido"
