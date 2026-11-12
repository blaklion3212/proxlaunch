"""Registro (ronda F7): enmascarado de códigos 2FA con prefijo y permisos privados en POSIX."""

import logging
import os
import stat

import pytest

from proxlaunch.nucleo.registro import ARCHIVO_LOG, MASCARA, configurar_registro, enmascarar

posix = pytest.mark.skipif(os.name != "posix", reason="los permisos 0o700/0o600 son de POSIX")


@pytest.fixture
def logger_limpio():
    yield logging.getLogger("proxlaunch")
    logger = logging.getLogger("proxlaunch")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


# --- Enmascarado -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "secreto"),
    [
        ("tfa-challenge=PVE:!tfa!abc123", "abc123"),
        ("cuerpo tfa-challenge=SECRETO-XYZ&otro=1", "SECRETO-XYZ"),
        ("password=totp:123456", "123456"),
        ("codigo totp:654321 enviado", "654321"),
        ("codigo TOTP:654321 enviado", "654321"),
        ("clave recovery:abcd-efgh-ijkl", "abcd-efgh-ijkl"),
        ("form=totp%3A987654&x=1", "987654"),
        ("form=recovery%3Aaaaa-bbbb&x=1", "aaaa-bbbb"),
        ("form=TOTP%3a111222", "111222"),
    ],
)
def test_codigos_2fa_con_prefijo_se_enmascaran(texto, secreto):
    salida = enmascarar(texto)
    assert secreto not in salida
    assert MASCARA in salida


def test_se_conservan_el_resto_del_texto_y_el_prefijo():
    assert enmascarar("antes totp:123456 despues") == f"antes totp:{MASCARA} despues"


def test_el_json_del_desafio_con_recovery_en_lista_queda_intacto():
    desafio = '{"totp":true,"recovery": [0,1],"webauthn":"x"}'
    assert enmascarar('"recovery": [0,1]') == '"recovery": [0,1]'
    assert "[0,1]" in enmascarar(f"desafio={desafio}") or "[0,1]" in enmascarar(desafio)
    assert enmascarar('{"recovery":[0,1]}') == '{"recovery":[0,1]}'


def test_tfa_challenge_en_el_log_no_llega_al_archivo(tmp_path, logger_limpio):
    logger = configurar_registro(tmp_path)
    logger.info("login tfa-challenge=SECRETO-DESAFIO y totp:135790")
    for h in logger.handlers:
        h.flush()
    contenido = (tmp_path / ARCHIVO_LOG).read_text(encoding="utf-8")
    assert "SECRETO-DESAFIO" not in contenido
    assert "135790" not in contenido


# --- Permisos -------------------------------------------------------------------------------


def _modo(ruta):
    return stat.S_IMODE(ruta.stat().st_mode)


@posix
def test_carpeta_y_log_se_crean_privados(tmp_path, logger_limpio):
    destino = tmp_path / "a" / "b" / "log"
    os.umask(0o022)
    logger = configurar_registro(destino)
    logger.info("hola")
    assert _modo(destino) == 0o700
    assert _modo(destino / ARCHIVO_LOG) == 0o600


@posix
def test_el_log_sigue_privado_tras_rotar(tmp_path, logger_limpio):
    logger = configurar_registro(tmp_path / "log", max_bytes=200, copias=2)
    for i in range(40):
        logger.info("linea numero %s con relleno suficiente para rotar", i)
    carpeta = tmp_path / "log"
    archivos = sorted(carpeta.glob(f"{ARCHIVO_LOG}*"))
    assert len(archivos) > 1  # hubo rotación
    assert _modo(carpeta / ARCHIVO_LOG) == 0o600


@posix
def test_carpeta_preexistente_abierta_se_cierra_a_0o700(tmp_path, logger_limpio):
    carpeta = tmp_path / "log"
    carpeta.mkdir(mode=0o755)
    carpeta.chmod(0o755)
    configurar_registro(carpeta)
    assert _modo(carpeta) == 0o700
