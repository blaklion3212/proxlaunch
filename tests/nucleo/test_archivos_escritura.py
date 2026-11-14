"""Escritura atómica y rutas propias (RF-X03: CA-X03.1, CA-X03.2, CA-X03.5, CA-P03.6, CA-P04.8,
CA-G02.6; INV-M8; CA-P10.5; CA-G02.2; §13 caso 16 de los requisitos).

``escribir_atomico(ruta, datos)``: temporal en la misma carpeta, ``fsync`` y ``os.replace``;
ante cualquier fallo el destino anterior queda intacto, el temporal se borra y se lanza E-M08.
"""

import errno
import json
import logging
import os
import stat
import threading
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.escritura import escribir_atomico, motivo_oserror
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.persistencia.rutas import Rutas, crear_carpeta_privada

from .apoyo_lote import volcar

posix = pytest.mark.skipif(os.name != "posix", reason="permisos POSIX")


def _modo(ruta: Path) -> int:
    return stat.S_IMODE(ruta.stat().st_mode)


def _error(ruta: Path, datos: bytes = b"nuevo") -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        escribir_atomico(ruta, datos)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    return exc.value


def _sin_restos(carpeta: Path, esperados: set[str]) -> None:
    assert {p.name for p in carpeta.iterdir()} == esperados  # ni temporales ni copias


# --- Caso feliz ----------------------------------------------------------------------------------


def test_escribe_el_contenido_exacto(tmp_path):
    ruta = tmp_path / "salida.json"
    escribir_atomico(ruta, b"\xef\xbb\xbfhola \xc3\xb1")
    assert ruta.read_bytes() == b"\xef\xbb\xbfhola \xc3\xb1"
    _sin_restos(tmp_path, {"salida.json"})


def test_reemplaza_un_archivo_existente(tmp_path):
    ruta = tmp_path / "salida.json"
    ruta.write_bytes(b"viejo")
    escribir_atomico(ruta, b"nuevo")
    assert ruta.read_bytes() == b"nuevo"
    _sin_restos(tmp_path, {"salida.json"})


def test_escribir_datos_vacios_deja_un_archivo_vacio(tmp_path):
    ruta = tmp_path / "v"
    escribir_atomico(ruta, b"")
    assert ruta.read_bytes() == b""


def test_rutas_con_espacios_y_acentos(tmp_path):
    carpeta = tmp_path / "Mis documentos ñandú"
    carpeta.mkdir()
    ruta = carpeta / "perfil de prueba.json"
    escribir_atomico(ruta, b"{}")
    assert ruta.read_bytes() == b"{}"


@posix
def test_el_archivo_nace_con_permisos_0600(tmp_path):
    ruta = tmp_path / "privado.json"
    escribir_atomico(ruta, b"{}")
    assert _modo(ruta) == 0o600


@posix
def test_la_carpeta_elegida_por_el_usuario_no_se_modifica(tmp_path):
    carpeta = tmp_path / "elegida"
    carpeta.mkdir(mode=0o755)
    carpeta.chmod(0o755)
    escribir_atomico(carpeta / "a.csv", b"x")
    assert _modo(carpeta) == 0o755  # CA-X03.2


def test_no_toca_archivos_que_no_son_el_destino(tmp_path):
    """CA-X03.5."""
    otro = tmp_path / "otro.txt"
    otro.write_bytes(b"intacto")
    os.utime(otro, ns=(1_000_000_000, 1_000_000_000))
    escribir_atomico(tmp_path / "destino.json", b"{}")
    assert otro.read_bytes() == b"intacto"
    assert otro.stat().st_mtime_ns == 1_000_000_000


def test_no_crea_la_carpeta_de_destino(tmp_path):
    """CA-X03.2: la carpeta la elige el usuario; si no existe es E-M08, no se crea."""
    ruta = tmp_path / "no-existe" / "x.json"
    e = _error(ruta)
    assert e.params["motivo"] in {"otro", "sin_permiso"}
    assert not (tmp_path / "no-existe").exists()


# --- Fallos inyectados (CA-X03.1, INV-M8) ---------------------------------------------------------


class _ArchivoQueFalla:
    """Sustituye al objeto de ``os.fdopen``: cierra el descriptor real y falla al escribir."""

    def __init__(self, f):
        self._f = f

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._f.close()
        return False

    def write(self, datos):
        raise OSError(errno.ENOSPC, "No space left on device")

    def flush(self):
        pass

    def fileno(self):
        return self._f.fileno()


def _inyectar(monkeypatch, punto: str, excepcion: BaseException):
    if punto == "write":
        real = os.fdopen
        monkeypatch.setattr(os, "fdopen", lambda fd, *a, **k: _ArchivoQueFalla(real(fd, *a, **k)))
    elif punto == "fsync":

        def _fsync(fd):
            raise excepcion

        monkeypatch.setattr(os, "fsync", _fsync)
    elif punto == "replace":

        def _replace(*a, **k):
            raise excepcion

        monkeypatch.setattr(os, "replace", _replace)
    else:  # pragma: no cover
        raise AssertionError(punto)


@pytest.mark.parametrize("punto", ["write", "fsync", "replace"])
def test_un_fallo_en_cualquier_punto_deja_el_destino_intacto_y_sin_temporales(
    tmp_path, monkeypatch, punto
):
    ruta = tmp_path / "datos.json"
    ruta.write_bytes(b"ORIGINAL")
    _inyectar(monkeypatch, punto, OSError(errno.ENOSPC, "disco lleno"))
    e = _error(ruta)
    assert e.params["motivo"] == "sin_espacio"
    monkeypatch.undo()
    assert ruta.read_bytes() == b"ORIGINAL"
    _sin_restos(tmp_path, {"datos.json"})


@pytest.mark.parametrize("punto", ["fsync", "replace"])
def test_un_fallo_inesperado_no_oserror_tambien_es_e_m08_y_limpia(tmp_path, monkeypatch, punto):
    ruta = tmp_path / "datos.json"
    ruta.write_bytes(b"ORIGINAL")
    _inyectar(monkeypatch, punto, RuntimeError("boom"))
    assert _error(ruta).params["motivo"] == "otro"
    monkeypatch.undo()
    assert ruta.read_bytes() == b"ORIGINAL"
    _sin_restos(tmp_path, {"datos.json"})


def test_un_fallo_con_destino_inexistente_no_deja_archivo_a_medias(tmp_path, monkeypatch):
    ruta = tmp_path / "nuevo.json"
    _inyectar(monkeypatch, "replace", OSError(errno.EIO, "fallo"))
    _error(ruta)
    monkeypatch.undo()
    _sin_restos(tmp_path, set())


def test_el_destino_conserva_el_contenido_anterior_hasta_el_reemplazo(tmp_path, monkeypatch):
    """Atomicidad: justo antes de ``os.replace`` el destino sigue siendo el original."""
    ruta = tmp_path / "datos.json"
    ruta.write_bytes(b"ORIGINAL")
    real = os.replace
    vistos = []

    def _replace(origen, destino):
        vistos.append(Path(destino).read_bytes())
        real(origen, destino)

    monkeypatch.setattr(os, "replace", _replace)
    escribir_atomico(ruta, b"NUEVO")
    assert vistos == [b"ORIGINAL"]
    assert ruta.read_bytes() == b"NUEVO"


def test_el_temporal_se_crea_en_la_misma_carpeta_que_el_destino(tmp_path, monkeypatch):
    carpetas = []
    real = os.replace
    monkeypatch.setattr(
        os, "replace", lambda o, d: (carpetas.append((Path(o).parent, Path(d).parent)), real(o, d))
    )
    escribir_atomico(tmp_path / "x.json", b"1")
    assert carpetas == [(tmp_path, tmp_path)]


@pytest.mark.parametrize(
    ("codigo", "motivo"),
    [
        (errno.ENOSPC, "sin_espacio"),
        (getattr(errno, "EDQUOT", errno.ENOSPC), "sin_espacio"),
        (errno.EACCES, "sin_permiso"),
        (errno.EPERM, "sin_permiso"),
        (errno.EROFS, "sin_permiso"),
        (errno.ENAMETOOLONG, "ruta_larga"),
        (errno.EIO, "otro"),
        (errno.EBUSY, "otro"),
    ],
)
def test_motivos_de_e_m08_segun_el_errno(tmp_path, monkeypatch, codigo, motivo):
    _inyectar(monkeypatch, "replace", OSError(codigo, "x"))
    assert _error(tmp_path / "a.json").params["motivo"] == motivo


def test_archivo_abierto_en_excel_en_windows_es_motivo_bloqueado():
    """CA-X05.4: ``PermissionError`` con ``winerror`` 32 o 33."""
    for winerror in (32, 33):
        falla = PermissionError(errno.EACCES, "sharing violation")
        falla.winerror = winerror  # type: ignore[attr-defined]
        assert motivo_oserror(falla) == "bloqueado"


def test_motivo_oserror_distingue_permiso_de_otros():
    assert motivo_oserror(PermissionError()) == "sin_permiso"
    assert motivo_oserror(OSError(errno.EIO, "x")) == "otro"


@posix
def test_carpeta_sin_permiso_de_escritura_da_e_m08_sin_permiso(tmp_path):
    carpeta = tmp_path / "solo-lectura"
    carpeta.mkdir()
    carpeta.chmod(0o500)
    try:
        if os.access(carpeta, os.W_OK):
            pytest.skip("el proceso ignora los permisos (¿superusuario?)")
        e = _error(carpeta / "x.json")
    finally:
        carpeta.chmod(0o700)
    assert e.params["motivo"] == "sin_permiso"
    _sin_restos(carpeta, set())


def test_el_error_no_contiene_la_ruta_y_el_registro_solo_el_nombre(tmp_path, caplog, monkeypatch):
    carpeta = tmp_path / "carpeta-privada-usuario"
    carpeta.mkdir()
    _inyectar(monkeypatch, "replace", OSError(errno.ENOSPC, "x"))
    with caplog.at_level(logging.DEBUG):
        e = _error(carpeta / "informe.csv")
    assert "carpeta-privada-usuario" not in volcar(e)
    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "informe.csv" in texto
    assert "carpeta-privada-usuario" not in texto


def test_en_windows_una_ruta_de_mas_de_260_caracteres_es_ruta_larga(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    ruta = tmp_path / ("a" * 250) / "b.json"
    assert len(str(ruta)) > 260
    assert _error(ruta).params["motivo"] == "ruta_larga"


# --- Concurrencia: dos instancias (CA-P04.8, §13 caso 17) -----------------------------------------


def test_dos_escritores_a_la_vez_nunca_dejan_un_archivo_ilegible(tmp_path):
    ruta = tmp_path / "perfiles.json"
    a = json.dumps({"quien": "a", "x": "A" * 5000}).encode()
    b = json.dumps({"quien": "b", "x": "B" * 9000}).encode()
    fallos: list[BaseException] = []

    def _escribir(datos):
        try:
            for _ in range(60):
                escribir_atomico(ruta, datos)
        except BaseException as exc:  # noqa: BLE001
            fallos.append(exc)

    hilos = [threading.Thread(target=_escribir, args=(d,)) for d in (a, b)]
    for h in hilos:
        h.start()
    lector_ok = True
    while any(h.is_alive() for h in hilos):
        if ruta.exists():
            lector_ok &= ruta.read_bytes() in (a, b)  # nunca una mezcla ni un truncado
    for h in hilos:
        h.join()
    assert not fallos
    assert lector_ok
    assert ruta.read_bytes() in (a, b)
    assert [p.name for p in tmp_path.iterdir()] == ["perfiles.json"]


# --- Rutas y carpetas privadas --------------------------------------------------------------------


def test_rutas_con_base_cuelgan_de_ella(tmp_path):
    r = Rutas(tmp_path)
    assert r.perfiles_maquina == tmp_path / "perfiles_maquina.json"
    assert r.directorio_config == tmp_path
    assert r.directorio_datos == tmp_path / "datos"
    assert r.lotes == tmp_path / "datos" / "lotes"
    assert r.perfiles == tmp_path / "perfiles.json"  # sin cambios del MVP 1
    assert r.directorio_log == tmp_path / "log"


def test_rutas_no_crean_carpetas_al_consultarlas(tmp_path):
    """CA-G02.2: ``lotes/`` «se crea con 0700 solo al usarla»."""
    base = tmp_path / "base"
    r = Rutas(base)
    _ = (r.perfiles_maquina, r.directorio_datos, r.lotes)
    assert not base.exists()


def test_rutas_sin_base_usan_platformdirs(monkeypatch):
    import platformdirs

    monkeypatch.setattr(platformdirs, "user_config_dir", lambda *_a, **_k: "/cfg/proxlaunch")
    monkeypatch.setattr(platformdirs, "user_data_dir", lambda *_a, **_k: "/datos/proxlaunch")
    monkeypatch.setattr(platformdirs, "user_log_dir", lambda *_a, **_k: "/log/proxlaunch")
    r = Rutas()
    assert r.perfiles_maquina == Path("/cfg/proxlaunch/perfiles_maquina.json")
    assert r.directorio_datos == Path("/datos/proxlaunch")
    assert r.lotes == Path("/datos/proxlaunch/lotes")


@posix
def test_crear_carpeta_privada_deja_0700_incluidos_los_padres_creados(tmp_path):
    destino = tmp_path / "a" / "b" / "lotes"
    crear_carpeta_privada(destino)
    assert _modo(destino) == 0o700
    crear_carpeta_privada(destino)  # idempotente
    assert _modo(destino) == 0o700
