"""Correcciones S6, S7 y S8 de la fase 6 del MVP 3 (RF-X03, INV-M8).

S6: ``crear_carpeta_privada`` deja 0700 cada nivel desde «ProxLaunch» hacia abajo y rechaza
enlaces, no directorios y carpetas de otro usuario. S7: el temporal de la escritura atómica es
corto (el destino puede medir 255 bytes) y en Windows el límite de 260 también lo mide.
S8: en Windows «acceso denegado» al reemplazar un destino existente significa «bloqueado».
"""

import errno
import os
import stat
import tempfile
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos import escritura
from proxlaunch.nucleo.archivos.escritura import escribir_atomico
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.persistencia.rutas import NOMBRE_APP, crear_carpeta_privada

posix = pytest.mark.skipif(os.name != "posix", reason="permisos POSIX")


def _modo(ruta: Path) -> int:
    return stat.S_IMODE(ruta.stat().st_mode)


def _error(funcion, *args) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        funcion(*args)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    return exc.value


# --- S6: carpetas privadas por nivel -------------------------------------------------------------


@posix
def test_s6_cada_nivel_desde_proxlaunch_hacia_abajo_queda_0700(tmp_path):
    ancestro = tmp_path / "config"
    ancestro.mkdir(mode=0o755)
    ancestro.chmod(0o755)
    destino = ancestro / NOMBRE_APP / "datos" / "lotes"
    crear_carpeta_privada(destino)
    for nivel in (ancestro / NOMBRE_APP, ancestro / NOMBRE_APP / "datos", destino):
        assert _modo(nivel) == 0o700
    assert _modo(ancestro) == 0o755  # el ancestro fuera de «ProxLaunch» no se toca


@posix
def test_s6_un_nivel_existente_con_permisos_amplios_se_endurece(tmp_path):
    raiz = tmp_path / NOMBRE_APP
    (raiz / "log").mkdir(parents=True)
    raiz.chmod(0o755)
    (raiz / "log").chmod(0o775)
    crear_carpeta_privada(raiz / "log")
    assert _modo(raiz) == 0o700 and _modo(raiz / "log") == 0o700


@posix
def test_s6_los_ancestros_creados_por_la_funcion_no_se_endurecen(tmp_path):
    destino = tmp_path / "a" / "b" / NOMBRE_APP / "x"
    crear_carpeta_privada(destino)
    assert _modo(tmp_path / "a") == _modo(tmp_path / "a" / "b")  # ambos con el modo por defecto
    assert _modo(tmp_path / "a" / "b" / NOMBRE_APP) == 0o700 and _modo(destino) == 0o700


@posix
def test_s6_sin_carpeta_proxlaunch_solo_el_ultimo_nivel_es_privado(tmp_path):
    padre = tmp_path / "padre"
    padre.mkdir()
    padre.chmod(0o755)
    crear_carpeta_privada(padre / "hijo")
    assert _modo(padre / "hijo") == 0o700 and _modo(padre) == 0o755


@posix
def test_s6_es_idempotente(tmp_path):
    destino = tmp_path / NOMBRE_APP / "x"
    crear_carpeta_privada(destino)
    crear_carpeta_privada(destino)
    assert _modo(destino) == 0o700


@posix
def test_s6_un_enlace_simbolico_como_nivel_propio_es_sin_permiso_y_no_toca_el_destino(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    real.chmod(0o755)
    enlace = tmp_path / NOMBRE_APP
    enlace.symlink_to(real, target_is_directory=True)
    e = _error(crear_carpeta_privada, enlace / "datos")
    assert e.params == {"motivo": "sin_permiso"}
    assert _modo(real) == 0o755 and list(real.iterdir()) == []


@posix
def test_s6_un_enlace_en_un_nivel_intermedio_propio_tambien_se_rechaza(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    real.chmod(0o755)
    (tmp_path / NOMBRE_APP).mkdir()
    (tmp_path / NOMBRE_APP / "datos").symlink_to(real, target_is_directory=True)
    e = _error(crear_carpeta_privada, tmp_path / NOMBRE_APP / "datos" / "lotes")
    assert e.params == {"motivo": "sin_permiso"}
    assert _modo(real) == 0o755 and list(real.iterdir()) == []


@posix
def test_s6_un_enlace_roto_como_ultimo_nivel_se_rechaza(tmp_path):
    (tmp_path / NOMBRE_APP).mkdir()
    (tmp_path / NOMBRE_APP / "x").symlink_to(tmp_path / "no-existe")
    assert _error(crear_carpeta_privada, tmp_path / NOMBRE_APP / "x").params == {
        "motivo": "sin_permiso"
    }


@posix
def test_s6_un_archivo_en_lugar_de_carpeta_es_sin_permiso(tmp_path):
    (tmp_path / NOMBRE_APP).write_text("no soy carpeta")
    assert _error(crear_carpeta_privada, tmp_path / NOMBRE_APP / "x").params == {
        "motivo": "sin_permiso"
    }


@posix
def test_s6_un_nivel_de_otro_usuario_es_sin_permiso_y_no_se_modifica(tmp_path, monkeypatch):
    carpeta = tmp_path / NOMBRE_APP
    carpeta.mkdir()
    carpeta.chmod(0o755)
    monkeypatch.setattr(os, "geteuid", lambda: os.stat(carpeta).st_uid + 1)
    assert _error(crear_carpeta_privada, carpeta / "x").params == {"motivo": "sin_permiso"}
    assert _modo(carpeta) == 0o755  # no se endurece lo ajeno


class _OsWindows:
    """Vista del módulo ``os`` que solo cambia ``name``; el resto se delega al real.

    Se sustituye únicamente dentro de ``escritura``: cambiar ``os.name`` globalmente rompe
    ``pathlib`` (no puede crear rutas POSIX con ``name == "nt"``).
    """

    name = "nt"

    def __getattr__(self, atributo: str):
        return getattr(os, atributo)


def _simular_windows(monkeypatch) -> None:
    monkeypatch.setattr(escritura, "os", _OsWindows())


# --- S7: temporal corto y límite de Windows ------------------------------------------------------


def _capturar_temporal(monkeypatch) -> dict[str, str]:
    visto: dict[str, str] = {}
    real_mkstemp = tempfile.mkstemp
    real_replace = os.replace

    def _mkstemp(*args, **kw):
        visto["prefix"], visto["suffix"] = kw.get("prefix", ""), kw.get("suffix", "")
        return real_mkstemp(*args, **kw)

    def _replace(origen, destino):
        visto["nombre"] = os.path.basename(origen)
        return real_replace(origen, destino)

    monkeypatch.setattr(tempfile, "mkstemp", _mkstemp)
    monkeypatch.setattr(os, "replace", _replace)
    return visto


def test_s7_un_destino_de_255_bytes_se_escribe_sin_enametoolong(tmp_path):
    nombre = "a" * (255 - len(".json")) + ".json"
    assert len(nombre.encode()) == 255
    destino = tmp_path / nombre
    escribir_atomico(destino, b"contenido")
    assert destino.read_bytes() == b"contenido"
    assert [p.name for p in tmp_path.iterdir()] == [nombre]  # sin restos del temporal


def test_s7_un_destino_de_255_bytes_con_caracteres_no_ascii_tambien_se_escribe(tmp_path):
    nombre = "ñ" * 120 + ".csv"  # 120 * 2 + 4 = 244 bytes
    escribir_atomico(tmp_path / nombre, b"x")
    assert (tmp_path / nombre).read_bytes() == b"x"


def test_s7_el_temporal_lleva_prefijo_fijo_y_a_lo_sumo_ocho_caracteres_seguros(
    tmp_path, monkeypatch
):
    visto = _capturar_temporal(monkeypatch)
    escribir_atomico(tmp_path / "ñandú-informe_largo final.json", b"x")
    assert visto["prefix"] == ".proxlaunch-and-info"  # sin no-ASCII ni espacios; 8 caracteres
    assert len(visto["prefix"]) - len(".proxlaunch-") == 8
    # prefijo (≤ 20) + 8 aleatorios + sufijo: muy por debajo de NAME_MAX
    assert len(visto["nombre"]) <= 12 + 8 + 8 + len(visto["suffix"]) < 255
    assert visto["nombre"].startswith(visto["prefix"])


def test_s7_un_nombre_corto_o_sin_caracteres_seguros_da_un_prefijo_valido(tmp_path, monkeypatch):
    visto = _capturar_temporal(monkeypatch)
    escribir_atomico(tmp_path / "ñ.é", b"x")
    assert visto["prefix"] == ".proxlaunch-"
    escribir_atomico(tmp_path / "a.b", b"x")
    assert visto["prefix"] == ".proxlaunch-ab"


def test_s7_el_temporal_no_incluye_caracteres_de_ruta_ni_de_control(tmp_path, monkeypatch):
    visto = _capturar_temporal(monkeypatch)
    escribir_atomico(tmp_path / "a b;c'd.json", b"x")
    assert visto["prefix"] == ".proxlaunch-abcdjson"[: len(".proxlaunch-") + 8]
    assert all(c.isalnum() or c in "-_." for c in visto["nombre"])


def _carpeta_larga(tmp_path: Path, total: int) -> Path:
    """Ruta (inexistente) de carpeta con exactamente ``total`` caracteres."""
    base = str(tmp_path)
    relleno = total - len(base) - 1
    assert relleno > 0
    return Path(base) / ("d" * relleno)


def test_s7_en_windows_el_destino_corto_pero_con_temporal_de_mas_de_260_es_ruta_larga(
    tmp_path, monkeypatch
):
    _simular_windows(monkeypatch)
    carpeta = _carpeta_larga(tmp_path, 235)
    ruta = carpeta / "a.json"
    assert len(str(ruta)) <= 260  # el destino cabe, el temporal (carpeta + 33) no
    e = _error(escribir_atomico, ruta, b"x")
    assert e.params == {"motivo": "ruta_larga"}
    assert not carpeta.exists()


def test_s7_en_windows_un_temporal_que_cabe_no_se_rechaza_por_longitud(tmp_path, monkeypatch):
    _simular_windows(monkeypatch)
    ruta = _carpeta_larga(tmp_path, 200) / "a.json"  # temporal ≈ 233 < 260

    def _falla(*args, **kw):
        raise OSError(errno.EIO, "x")

    monkeypatch.setattr(tempfile, "mkstemp", _falla)
    assert _error(escribir_atomico, ruta, b"x").params == {"motivo": "otro"}


def test_s7_en_windows_el_limite_exacto_del_temporal_se_acepta_y_uno_mas_se_rechaza(
    tmp_path, monkeypatch
):
    _simular_windows(monkeypatch)
    monkeypatch.setattr(
        tempfile, "mkstemp", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EIO, "x"))
    )
    # nombre "a.json" → prefijo ".proxlaunch-ajson" (17) + 8 + ".tmp" (4) = 29, más "\" = 30
    exacto = _carpeta_larga(tmp_path, 260 - 30) / "a.json"
    pasado = _carpeta_larga(tmp_path, 260 - 30 + 1) / "a.json"
    assert _error(escribir_atomico, exacto, b"x").params == {"motivo": "otro"}
    assert _error(escribir_atomico, pasado, b"x").params == {"motivo": "ruta_larga"}


# --- S8: acceso denegado en Windows --------------------------------------------------------------


def _acceso_denegado(winerror: int | None = 5) -> PermissionError:
    falla = PermissionError(errno.EACCES, "acceso denegado")
    if winerror is not None:
        falla.winerror = winerror  # type: ignore[attr-defined]
    return falla


def _inyectar_replace(monkeypatch, falla: BaseException) -> None:
    def _replace(origen, destino):
        raise falla

    monkeypatch.setattr(os, "replace", _replace)


def test_s8_en_windows_acceso_denegado_con_destino_existente_es_bloqueado(tmp_path, monkeypatch):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _simular_windows(monkeypatch)
    _inyectar_replace(monkeypatch, _acceso_denegado(5))
    assert _error(escribir_atomico, destino, b"nuevo").params == {"motivo": "bloqueado"}
    assert destino.read_bytes() == b"anterior"
    assert [p.name for p in tmp_path.iterdir()] == ["datos.json"]  # temporal borrado


def test_s8_en_windows_acceso_denegado_sin_destino_es_sin_permiso(tmp_path, monkeypatch):
    _simular_windows(monkeypatch)
    _inyectar_replace(monkeypatch, _acceso_denegado(5))
    e = _error(escribir_atomico, tmp_path / "nuevo.json", b"x")
    assert e.params == {"motivo": "sin_permiso"}
    assert list(tmp_path.iterdir()) == []


@posix
def test_s8_en_posix_acceso_denegado_con_destino_existente_sigue_siendo_sin_permiso(
    tmp_path, monkeypatch
):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _inyectar_replace(monkeypatch, _acceso_denegado(5))
    assert _error(escribir_atomico, destino, b"nuevo").params == {"motivo": "sin_permiso"}
    assert destino.read_bytes() == b"anterior"


def test_s8_en_windows_otro_winerror_con_destino_existente_no_es_bloqueado(tmp_path, monkeypatch):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _simular_windows(monkeypatch)
    _inyectar_replace(monkeypatch, _acceso_denegado(None))  # PermissionError sin winerror
    assert _error(escribir_atomico, destino, b"n").params == {"motivo": "sin_permiso"}


@pytest.mark.parametrize("winerror", [32, 33])
def test_s8_los_codigos_de_uso_compartido_siguen_siendo_bloqueado(tmp_path, monkeypatch, winerror):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _simular_windows(monkeypatch)
    _inyectar_replace(monkeypatch, _acceso_denegado(winerror))
    assert _error(escribir_atomico, destino, b"n").params == {"motivo": "bloqueado"}


def test_s8_acceso_denegado_al_crear_el_temporal_no_es_bloqueado_aunque_el_destino_exista(
    tmp_path, monkeypatch
):
    destino = tmp_path / "datos.json"
    destino.write_bytes(b"anterior")
    _simular_windows(monkeypatch)

    def _mkstemp(*args, **kw):
        raise _acceso_denegado(5)

    monkeypatch.setattr(tempfile, "mkstemp", _mkstemp)
    assert _error(escribir_atomico, destino, b"n").params == {"motivo": "sin_permiso"}
    assert destino.read_bytes() == b"anterior"
