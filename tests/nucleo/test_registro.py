"""Registro rotativo y filtro de secretos (RNF-06, RNF-13, CA-08.5)."""

import logging
from urllib.parse import quote, quote_plus

import pytest

from proxlaunch.nucleo.registro import (
    ARCHIVO_LOG,
    MASCARA,
    configurar_registro,
    enmascarar,
    registrar_secreto,
)

CENTINELA = "CENTINELA-7f3a9c1e"


@pytest.fixture
def logger_limpio():
    """Restaura el logger `proxlaunch` tras cada caso (manejadores y propagación)."""
    yield logging.getLogger("proxlaunch")
    logger = logging.getLogger("proxlaunch")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def _contenido(carpeta):
    return (carpeta / ARCHIVO_LOG).read_text(encoding="utf-8")


# --- enmascarar ---------------------------------------------------------------------


def test_secreto_registrado_se_enmascara():
    registrar_secreto(CENTINELA)
    assert enmascarar(f"conectando con {CENTINELA} ok") == f"conectando con {MASCARA} ok"


def test_secreto_registrado_se_enmascara_tambien_codificado():
    secreto = "p@ss w/rd=1&x"
    registrar_secreto(secreto)
    for variante in (secreto, quote(secreto, safe=""), quote_plus(secreto)):
        assert variante not in enmascarar(f"cuerpo: {variante}")


def test_secreto_vacio_no_enmascara_todo():
    registrar_secreto("")
    assert enmascarar("texto normal") == "texto normal"


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param(
            f"Authorization: PVEAPIToken=ana@pve!lab={CENTINELA}", id="RNF-06-authorization"
        ),
        pytest.param(
            f"authorization: PVEAPIToken=ana@pve!lab={CENTINELA}",
            id="RNF-06-authorization-minusculas",
        ),
        pytest.param(f"Cookie: PVEAuthCookie={CENTINELA}; otra=1", id="RNF-06-cookie"),
        pytest.param(f"Set-Cookie: PVEAuthCookie={CENTINELA}", id="RNF-06-set-cookie"),
        pytest.param(f"CSRFPreventionToken: {CENTINELA}", id="RNF-06-csrf"),
        pytest.param(
            f"username=root&password={CENTINELA}&realm=pam", id="RNF-06-password-formulario"
        ),
        pytest.param(f"{{'ticket': '{CENTINELA}'}}", id="RNF-06-ticket-dict"),
        pytest.param(f'{{"password": "{CENTINELA}"}}', id="RNF-06-password-json"),
        pytest.param(f"otp={CENTINELA}", id="RNF-06-otp"),
    ],
)
def test_rnf06_cabeceras_y_campos_sensibles_se_enmascaran_sin_registrar(texto):
    """RNF-06: Authorization y cookies -> ***, aun sin conocer el valor de antemano."""
    resultado = enmascarar(texto)
    assert CENTINELA not in resultado
    assert MASCARA in resultado


def test_enmascarar_no_toca_texto_inocuo():
    texto = "Creando MV 100 en pve1 (UPID:pve1:0001)"
    assert enmascarar(texto) == texto


# --- archivo de log -----------------------------------------------------------------


def test_rnf13_log_en_la_carpeta_indicada_con_nivel_configurable(tmp_path, logger_limpio):
    log = configurar_registro(tmp_path / "log", nivel=logging.WARNING)
    log.info("mensaje-info")
    log.warning("mensaje-aviso")
    contenido = _contenido(tmp_path / "log")
    assert "mensaje-aviso" in contenido
    assert "mensaje-info" not in contenido


def test_rnf13_nivel_como_texto(tmp_path, logger_limpio):
    log = configurar_registro(tmp_path, nivel="DEBUG")
    log.debug("detalle-fino")
    assert "detalle-fino" in _contenido(tmp_path)


def test_rnf13_el_log_incluye_upid_vmid_y_nodo(tmp_path, logger_limpio):
    configurar_registro(tmp_path)
    logging.getLogger("proxlaunch.servicios.creacion").info(
        "Tarea %s: VMID %s en %s",
        "UPID:pve1:0000ABCD:00000001:6543:qmcreate:100:ana@pve:",
        100,
        "pve1",
    )
    contenido = _contenido(tmp_path)
    assert "UPID:pve1:0000ABCD" in contenido
    assert "VMID 100 en pve1" in contenido


def test_rnf13_rotacion_por_tamano(tmp_path, logger_limpio):
    log = configurar_registro(tmp_path, max_bytes=500, copias=2)
    for i in range(60):
        log.info("linea numero %03d con relleno suficiente para rotar", i)
    nombres = sorted(p.name for p in tmp_path.iterdir())
    assert nombres == [ARCHIVO_LOG, f"{ARCHIVO_LOG}.1", f"{ARCHIVO_LOG}.2"]


def test_configurar_registro_es_idempotente(tmp_path, logger_limpio):
    configurar_registro(tmp_path)
    log = configurar_registro(tmp_path)
    log.info("una-sola-vez")
    assert _contenido(tmp_path).count("una-sola-vez") == 1


def test_configurar_registro_crea_la_carpeta(tmp_path, logger_limpio):
    destino = tmp_path / "a" / "b"
    configurar_registro(destino)
    assert destino.is_dir()


# --- CA-08.5 / RNF-06: centinela en el log ------------------------------------------


def test_ca08_5_el_centinela_no_aparece_en_ningun_canal_del_log(tmp_path, logger_limpio, capsys):
    registrar_secreto(CENTINELA)
    configurar_registro(tmp_path)
    hijo = logging.getLogger("proxlaunch.api.transporte")

    hijo.info("mensaje directo %s", CENTINELA)  # argumento de formato
    hijo.info(f"mensaje formateado {CENTINELA}")
    hijo.error("cabecera Authorization: PVEAPIToken=ana@pve!lab=%s", CENTINELA)
    try:
        raise RuntimeError(f"fallo con {CENTINELA}")
    except RuntimeError:
        hijo.exception("excepción capturada")
    hijo.warning("pila", stack_info=True, extra={"centinela": CENTINELA})

    contenido = _contenido(tmp_path)
    assert CENTINELA not in contenido
    assert MASCARA in contenido
    salida = capsys.readouterr()
    assert CENTINELA not in salida.out + salida.err
    assert "excepción capturada" in contenido  # el registro no se descarta


def test_ca08_5_el_texto_de_la_excepcion_tambien_se_enmascara(tmp_path, logger_limpio):
    registrar_secreto(CENTINELA)
    configurar_registro(tmp_path)
    log = logging.getLogger("proxlaunch")
    try:
        raise ValueError(f"credencial {CENTINELA}")
    except ValueError:
        log.exception("error")
    contenido = _contenido(tmp_path)
    assert "ValueError" in contenido
    assert CENTINELA not in contenido


def test_registro_con_argumentos_invalidos_no_rompe_ni_filtra(tmp_path, logger_limpio):
    registrar_secreto(CENTINELA)
    configurar_registro(tmp_path)
    logging.getLogger("proxlaunch").info("texto %s %s", CENTINELA)  # faltan argumentos
    assert CENTINELA not in _contenido(tmp_path)


def test_olvidar_secretos_deja_de_enmascarar():
    from proxlaunch.nucleo.registro import olvidar_secretos

    registrar_secreto(CENTINELA)
    olvidar_secretos()
    assert enmascarar(f"valor {CENTINELA}") == f"valor {CENTINELA}"


def test_no_se_propaga_a_manejadores_sin_filtro(tmp_path, logger_limpio):
    configurar_registro(tmp_path)
    assert logging.getLogger("proxlaunch").propagate is False
