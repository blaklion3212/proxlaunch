"""Lectura limitada de archivos de terceros (RF-X02: CA-X02.1, CA-X02.2, CA-X02.7, CA-X02.9,
CA-X02.10; INV-M3; RNF-M02).

``leer_archivo_limitado(ruta, limite)`` es la única puerta de entrada de archivos del usuario:
solo lectura, acotada al límite, sin bloquear con tuberías y sin revelar la ruta completa.
"""

import errno
import hashlib
import logging
import os
import stat
import subprocess
import threading
import tracemalloc
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.constantes import (
    MAX_BYTES_CSV,
    MAX_BYTES_LOTE,
    MAX_BYTES_PERFILES,
)
from proxlaunch.nucleo.archivos.lector import leer_archivo_limitado
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

from .apoyo_lote import volcar

LIMITE = 1024


def _error(ruta: Path, limite: int = LIMITE) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_limitado(ruta, limite)
    return exc.value


def _en_hilo(funcion, segundos: float = 10.0):
    """Ejecuta ``funcion`` en un hilo; si no termina en ``segundos`` se considera bloqueada."""
    resultado: dict[str, object] = {}

    def _correr() -> None:
        try:
            resultado["valor"] = funcion()
        except BaseException as exc:  # noqa: BLE001 - se devuelve para la aserción
            resultado["error"] = exc

    hilo = threading.Thread(target=_correr, daemon=True)
    hilo.start()
    hilo.join(segundos)
    assert not hilo.is_alive(), "la lectura se bloqueó"
    return resultado


# --- Lectura normal y límites ------------------------------------------------------------------


def test_lee_un_archivo_regular_pequeno(tmp_path):
    ruta = tmp_path / "a.json"
    ruta.write_bytes(b'{"x": 1}')
    assert leer_archivo_limitado(ruta, LIMITE) == b'{"x": 1}'


def test_un_archivo_vacio_devuelve_bytes_vacios(tmp_path):
    ruta = tmp_path / "vacio"
    ruta.write_bytes(b"")
    assert leer_archivo_limitado(ruta, LIMITE) == b""


def test_un_archivo_exactamente_del_limite_se_acepta(tmp_path):
    ruta = tmp_path / "justo"
    ruta.write_bytes(b"a" * LIMITE)
    assert len(leer_archivo_limitado(ruta, LIMITE)) == LIMITE


def test_un_archivo_un_byte_sobre_el_limite_da_e_m01_demasiado_grande(tmp_path):
    ruta = tmp_path / "pasado"
    ruta.write_bytes(b"a" * (LIMITE + 1))
    e = _error(ruta)
    assert e.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert e.params["motivo"] == "demasiado_grande"
    assert e.params["limite"] == str(LIMITE)
    assert e.params["tamano"] == str(LIMITE + 1)


@pytest.mark.parametrize(
    ("nombre", "limite"),
    [("perfiles", MAX_BYTES_PERFILES), ("lote", MAX_BYTES_LOTE), ("csv", MAX_BYTES_CSV)],
)
def test_los_limites_de_los_requisitos(nombre, limite):
    assert {"perfiles": 256 * 1024, "lote": 1024 * 1024, "csv": 1024 * 1024}[nombre] == limite


def test_un_archivo_de_2_gb_se_rechaza_sin_leerlo_ni_cargarlo_en_memoria(tmp_path, monkeypatch):
    """CA-X02.2 / RNF-M02: archivo disperso de 2 GB (``truncate``), sin ocupar disco real."""
    ruta = tmp_path / "gigante.csv"
    subprocess.run(["truncate", "-s", "2G", str(ruta)], check=True)
    assert ruta.stat().st_size == 2 * 1024**3
    assert ruta.stat().st_blocks * 512 < 1024 * 1024  # disperso: casi sin bloques reales

    lecturas = []
    real = os.read
    monkeypatch.setattr(os, "read", lambda fd, n: lecturas.append(n) or real(fd, n))
    tracemalloc.start()
    try:
        e = _error(ruta, MAX_BYTES_CSV)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert e.params["motivo"] == "demasiado_grande"
    assert e.params["tamano"] == str(2 * 1024**3)
    assert lecturas == []  # se rechazó por tamaño, sin leer ni un byte
    assert pico < 5 * 1024 * 1024  # nunca se cargó el archivo en memoria


def test_si_st_size_miente_no_se_leen_mas_de_limite_mas_uno_bytes(tmp_path, monkeypatch):
    """CA-X02.2: un archivo que crece o miente en ``st_size`` tampoco se lee entero."""
    ruta = tmp_path / "miente"
    ruta.write_bytes(b"a" * (LIMITE * 50))
    real_fstat = os.fstat

    class _Mentira:
        def __init__(self, st):
            self.st_mode = st.st_mode
            self.st_size = 10  # dice ser pequeño

    monkeypatch.setattr(os, "fstat", lambda fd: _Mentira(real_fstat(fd)))
    pedidos: list[int] = []
    real_read = os.read
    monkeypatch.setattr(os, "read", lambda fd, n: pedidos.append(n) or real_read(fd, n))
    e = _error(ruta)
    assert e.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert e.params["motivo"] == "demasiado_grande"
    assert sum(pedidos) <= LIMITE + 1  # nunca se pidió más de límite + 1 bytes


# --- Tipos de archivo --------------------------------------------------------------------------


def test_un_directorio_da_e_m01_no_regular(tmp_path):
    e = _error(tmp_path)
    assert e.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert e.params["motivo"] == "no_regular"


def test_una_tuberia_con_nombre_da_e_m01_sin_bloquear(tmp_path):
    """CA-X02.1: abrir una tubería sin escritor no debe colgar el programa."""
    ruta = tmp_path / "tuberia"
    os.mkfifo(ruta)
    resultado = _en_hilo(lambda: leer_archivo_limitado(ruta, LIMITE))
    error = resultado.get("error")
    assert isinstance(error, ErrorProxLaunch), resultado
    assert error.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert error.params["motivo"] == "no_regular"


@pytest.mark.parametrize("dispositivo", ["/dev/zero", "/dev/null", "/dev/urandom"])
def test_un_dispositivo_da_e_m01_no_regular(dispositivo):
    if not Path(dispositivo).exists():
        pytest.skip(f"{dispositivo} no existe en este sistema")
    resultado = _en_hilo(lambda: leer_archivo_limitado(Path(dispositivo), MAX_BYTES_CSV))
    error = resultado.get("error")
    assert isinstance(error, ErrorProxLaunch), resultado
    assert error.params["motivo"] == "no_regular"


def test_un_enlace_simbolico_a_un_archivo_regular_se_lee_como_el_archivo(tmp_path):
    destino = tmp_path / "real.csv"
    destino.write_bytes(b"nombre\r\nweb\r\n")
    enlace = tmp_path / "enlace.csv"
    enlace.symlink_to(destino)
    assert leer_archivo_limitado(enlace, LIMITE) == b"nombre\r\nweb\r\n"


def test_un_enlace_simbolico_a_un_directorio_es_no_regular(tmp_path):
    carpeta = tmp_path / "carpeta"
    carpeta.mkdir()
    enlace = tmp_path / "enlace"
    enlace.symlink_to(carpeta, target_is_directory=True)
    assert _error(enlace).params["motivo"] == "no_regular"


def test_un_enlace_simbolico_roto_da_e_m05_no_existe(tmp_path):
    enlace = tmp_path / "roto"
    enlace.symlink_to(tmp_path / "no-existe")
    e = _error(enlace)
    assert e.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE
    assert e.params["motivo"] == "no_existe"


# --- Errores de E/S (E-M05) --------------------------------------------------------------------


def test_archivo_inexistente_da_e_m05_y_solo_el_nombre(tmp_path):
    ruta = tmp_path / "carpeta-privada-del-usuario" / "no-existe.json"
    e = _error(ruta)
    assert e.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE
    assert e.params["motivo"] == "no_existe"
    assert e.params["archivo"] == "no-existe.json"
    assert "carpeta-privada-del-usuario" not in volcar(e)  # nunca la ruta completa
    assert str(tmp_path) not in volcar(e)


def test_archivo_sin_permiso_de_lectura_da_e_m05_sin_permiso(tmp_path):
    ruta = tmp_path / "secreto.json"
    ruta.write_bytes(b"{}")
    ruta.chmod(0)
    try:
        if os.access(ruta, os.R_OK):
            pytest.skip("el proceso ignora los permisos (¿superusuario?)")
        e = _error(ruta)
    finally:
        ruta.chmod(0o600)
    assert e.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE
    assert e.params["motivo"] == "sin_permiso"
    assert str(tmp_path) not in volcar(e)


def test_archivo_bloqueado_por_otro_programa_en_windows_da_motivo_bloqueado(tmp_path, monkeypatch):
    """CA-X02.9 / CA-X05.4: ``PermissionError`` con ``winerror`` 32 o 33 = abierto en Excel."""
    ruta = tmp_path / "abierto-en-excel.csv"
    ruta.write_bytes(b"a")
    for winerror in (32, 33):
        falla = PermissionError(errno.EACCES, "sharing violation")
        falla.winerror = winerror  # type: ignore[attr-defined]

        def _abrir(*_a, _falla=falla, **_k):
            raise _falla

        monkeypatch.setattr(os, "open", _abrir)
        assert _error(ruta).params["motivo"] == "bloqueado"


def test_un_error_de_disco_desconocido_da_motivo_otro(tmp_path, monkeypatch):
    ruta = tmp_path / "x.json"
    ruta.write_bytes(b"a")

    def _abrir(*_a, **_k):
        raise OSError(errno.EIO, "fallo de disco")

    monkeypatch.setattr(os, "open", _abrir)
    e = _error(ruta)
    assert e.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE
    assert e.params["motivo"] == "otro"


def test_un_fallo_al_leer_a_mitad_da_e_m05(tmp_path, monkeypatch):
    ruta = tmp_path / "x.json"
    ruta.write_bytes(b"a" * 100)

    def _leer(*_a, **_k):
        raise OSError(errno.EIO, "fallo")

    monkeypatch.setattr(os, "read", _leer)
    assert _error(ruta).codigo == CodigoError.ARCHIVO_NO_ACCESIBLE


# --- INV-M3: el archivo del usuario no se toca -------------------------------------------------


def _huella(ruta: Path):
    info = ruta.stat()
    return (
        hashlib.sha256(ruta.read_bytes()).hexdigest(),
        info.st_mtime_ns,
        info.st_ino,
        info.st_size,
    )


def test_leer_no_modifica_ni_el_contenido_ni_la_fecha_ni_la_carpeta(tmp_path):
    ruta = tmp_path / "entrada.json"
    ruta.write_bytes(b"\xff\xfe esto ni siquiera es JSON \x00")
    antes = _huella(ruta)
    carpeta_antes = sorted(p.name for p in tmp_path.iterdir())
    leer_archivo_limitado(ruta, LIMITE)
    assert _huella(ruta) == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == carpeta_antes  # nada renombrado ni creado


def test_leer_un_archivo_rechazado_tampoco_lo_modifica(tmp_path):
    ruta = tmp_path / "grande.json"
    ruta.write_bytes(b"a" * (LIMITE * 3))
    antes = _huella(ruta)
    _error(ruta)
    assert _huella(ruta) == antes
    assert [p.name for p in tmp_path.iterdir()] == ["grande.json"]


def test_el_archivo_se_abre_solo_para_lectura(tmp_path, monkeypatch):
    ruta = tmp_path / "x.json"
    ruta.write_bytes(b"{}")
    banderas: list[int] = []
    real = os.open

    def _abrir(path, flags, *a, **k):
        banderas.append(flags)
        return real(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", _abrir)
    leer_archivo_limitado(ruta, LIMITE)
    assert banderas
    escritura = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    assert all(b & escritura == 0 for b in banderas)


def test_el_modulo_lector_no_expone_operaciones_que_modifiquen_archivos():
    """INV-M3: en ``nucleo/archivos/lector.py`` no hay renombrar, truncar ni borrar."""
    import proxlaunch.nucleo.archivos.lector as modulo

    codigo = Path(modulo.__file__).read_text(encoding="utf-8")
    for prohibido in (
        "os.rename",
        "os.replace",
        "os.remove",
        "os.unlink",
        "truncate",
        "shutil",
        "write(",
    ):
        assert prohibido not in codigo, prohibido


# --- Registro (CA-X02.10) ----------------------------------------------------------------------


def test_el_registro_lleva_nombre_y_tamano_pero_no_el_contenido_ni_la_ruta(tmp_path, caplog):
    ruta = tmp_path / "subcarpeta-del-usuario" / "datos.json"
    ruta.parent.mkdir()
    ruta.write_bytes(b'{"contenido": "CENTINELA-SECRETO-no-registrar"}')
    with caplog.at_level(logging.DEBUG):
        leer_archivo_limitado(ruta, LIMITE)
    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "datos.json" in texto
    assert "CENTINELA-SECRETO" not in texto
    assert "subcarpeta-del-usuario" not in texto


def test_el_rechazo_se_registra_con_nombre_y_codigo_sin_ruta(tmp_path, caplog):
    ruta = tmp_path / "carpeta-privada" / "enorme.csv"
    ruta.parent.mkdir()
    ruta.write_bytes(b"a" * (LIMITE + 5))
    with caplog.at_level(logging.DEBUG):
        _error(ruta)
    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "enorme.csv" in texto
    assert "archivo_no_permitido" in texto
    assert "carpeta-privada" not in texto


def test_un_archivo_regular_es_regular_para_stat(tmp_path):
    """Sanidad de la prueba de tubería: ``mkfifo`` crea realmente una tubería."""
    ruta = tmp_path / "t"
    os.mkfifo(ruta)
    assert stat.S_ISFIFO(ruta.stat().st_mode)
