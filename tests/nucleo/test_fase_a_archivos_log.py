"""Fase A (0.6.0): las credenciales en notas, pool o etiquetas no llegan al registro (RNF-A2).

Cubre RNF-A2 y CA-A7.1.9 para los caminos de archivo con registro: guardar y leer lotes.
"""

import json
import logging

import pytest

from proxlaunch.nucleo.archivos.esquema import ErrorArchivo
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote, leer_archivo_lote
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado

from .apoyo_lote import definicion, plantilla
from .apoyo_mvp3 import archivo_lote, config_lote_json, lote_homogeneo_json

SECRETO = "0a1b2c3d-9999-8888-7777-666655554444"
TOKEN = f"root@pam!lab={SECRETO}"


def _todo_el_registro(caplog) -> str:
    return "\n".join(r.getMessage() + str(r.args) + (r.exc_text or "") for r in caplog.records)


@pytest.mark.parametrize("campo", ["notas", "pool"])
def test_rnf_a2_guardar_un_lote_con_token_falla_sin_escribir_ni_registrar_el_secreto(
    tmp_path, caplog, campo
):
    ruta = tmp_path / "lote.json"
    lote = LoteGuardado("x", definicion(2, plantilla_vm=plantilla(**{campo: f"uso {TOKEN}"})))
    with caplog.at_level(logging.DEBUG, logger="proxlaunch"), pytest.raises(ErrorProxLaunch):
        guardar_lote(ruta, lote, app_version="0.6.0")
    assert not ruta.exists()  # escritura atómica: nada a medias
    assert SECRETO not in _todo_el_registro(caplog)


def test_rnf_a2_leer_un_lote_de_terceros_con_token_en_notas_no_lo_registra(tmp_path, caplog):
    cuerpo = json.loads(archivo_lote(lote_homogeneo_json(config=config_lote_json(notas=TOKEN))))
    cuerpo["version_formato"] = 3
    ruta = tmp_path / "ajeno.json"
    ruta.write_text(json.dumps(cuerpo), encoding="utf-8")
    with caplog.at_level(logging.DEBUG, logger="proxlaunch"), pytest.raises(ErrorArchivo) as exc:
        leer_archivo_lote(ruta)
    assert SECRETO not in _todo_el_registro(caplog)
    assert SECRETO not in repr(exc.value.params) + str(exc.value) + repr(exc.value.errores)


def test_rnf_a2_un_lote_legitimo_si_se_registra_sin_notas(tmp_path, caplog):
    ruta = tmp_path / "ok.json"
    lote = LoteGuardado("x", definicion(2, plantilla_vm=plantilla(notas="NOTA-PRIVADA-XYZ")))
    with caplog.at_level(logging.DEBUG, logger="proxlaunch"):
        guardar_lote(ruta, lote, app_version="0.6.0")
        leer_archivo_lote(ruta)
    assert "NOTA-PRIVADA-XYZ" not in _todo_el_registro(caplog)  # el contenido de notas no se loguea
