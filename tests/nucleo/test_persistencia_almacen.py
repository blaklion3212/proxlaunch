"""AlmacenJson y Rutas (RNF-15, S-3, RNF-04). Todo en tmp_path: nunca la carpeta real."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from proxlaunch.nucleo.persistencia import rutas as modulo_rutas
from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson
from proxlaunch.nucleo.persistencia.rutas import Rutas

SELLO = datetime(2026, 11, 11, 12, 30, 45)


def _almacen(tmp_path, nombre="datos.json"):
    return AlmacenJson(tmp_path / nombre, ahora=lambda: SELLO)


# --- lectura y escritura ------------------------------------------------------------


def test_leer_archivo_inexistente_devuelve_vacio_sin_corrupcion(tmp_path):
    r = _almacen(tmp_path).leer()
    assert r.datos == {}
    assert r.hubo_corrupcion is False
    assert r.copia_danada is None


def test_escribir_y_leer_ida_y_vuelta_con_unicode(tmp_path):
    datos = {"nombre": "Laboratorio ñandú", "lista": [1, 2, 3], "anidado": {"a": None}}
    almacen = _almacen(tmp_path)
    almacen.escribir(datos)
    assert almacen.leer().datos == datos
    assert "ñandú" in almacen.ruta.read_text(encoding="utf-8")


def test_escribir_crea_carpetas_intermedias(tmp_path):
    almacen = AlmacenJson(tmp_path / "a" / "b" / "datos.json")
    almacen.escribir({"x": 1})
    assert almacen.leer().datos == {"x": 1}


def test_escribir_no_deja_temporales(tmp_path):
    almacen = _almacen(tmp_path)
    almacen.escribir({"x": 1})
    almacen.escribir({"x": 2})
    assert [p.name for p in tmp_path.iterdir()] == ["datos.json"]


def test_rnf15_escritura_fallida_conserva_el_archivo_anterior(tmp_path):
    """Escritura atómica: si falla la serialización el archivo previo queda intacto."""
    almacen = _almacen(tmp_path)
    almacen.escribir({"version": 1})
    with pytest.raises(TypeError):
        almacen.escribir({"no_serializable": object()})
    assert almacen.leer().datos == {"version": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["datos.json"]


# --- archivos dañados (RNF-15) ------------------------------------------------------


@pytest.mark.parametrize(
    "contenido",
    [
        pytest.param(b"{no es json", id="RNF-15-json-truncado"),
        pytest.param(b"", id="RNF-15-archivo-vacio"),
        pytest.param(b"[1, 2, 3]", id="RNF-15-raiz-es-lista"),
        pytest.param(b'"texto"', id="RNF-15-raiz-es-cadena"),
        pytest.param(b"\xff\xfe\x00basura", id="RNF-15-utf8-invalido"),
    ],
)
def test_rnf15_archivo_corrupto_se_renombra_y_se_empieza_vacio(tmp_path, contenido):
    almacen = _almacen(tmp_path)
    almacen.ruta.write_bytes(contenido)
    r = almacen.leer()
    assert r.datos == {}
    assert r.hubo_corrupcion is True
    assert r.copia_danada is not None
    assert r.copia_danada.name == "datos.json.danado-20261111-123045"
    assert r.copia_danada.read_bytes() == contenido  # se conserva la copia
    assert not almacen.ruta.exists()


def test_rnf15_despues_de_la_corrupcion_se_puede_escribir_uno_nuevo(tmp_path):
    almacen = _almacen(tmp_path)
    almacen.ruta.write_text("{roto", encoding="utf-8")
    almacen.leer()
    almacen.escribir({"nuevo": True})
    assert almacen.leer().datos == {"nuevo": True}


def test_rnf15_dos_corrupciones_en_el_mismo_segundo_no_pisan_la_copia(tmp_path):
    almacen = _almacen(tmp_path)
    almacen.ruta.write_text("{uno", encoding="utf-8")
    primera = almacen.leer().copia_danada
    almacen.ruta.write_text("{dos", encoding="utf-8")
    segunda = almacen.leer().copia_danada
    assert primera != segunda
    assert primera.read_text(encoding="utf-8") == "{uno"
    assert segunda.read_text(encoding="utf-8") == "{dos"


def test_el_json_escrito_es_legible_por_humanos_y_valido(tmp_path):
    almacen = _almacen(tmp_path)
    almacen.escribir({"b": 1, "a": 2})
    assert json.loads(almacen.ruta.read_text(encoding="utf-8")) == {"a": 2, "b": 1}


# --- Rutas --------------------------------------------------------------------------


def test_rutas_con_base_cuelgan_de_ella(tmp_path):
    r = Rutas(tmp_path)
    assert r.directorio_config == tmp_path
    assert r.directorio_log == tmp_path / "log"
    assert r.perfiles == tmp_path / "perfiles.json"
    assert r.huellas == tmp_path / "huellas.json"
    assert r.preferencias == tmp_path / "preferencias.json"


def test_rutas_aceptan_texto_y_son_pathlib(tmp_path):
    r = Rutas(str(tmp_path))
    assert isinstance(r.perfiles, Path)
    assert r.perfiles.parent == tmp_path


def test_rutas_sin_base_usan_platformdirs_con_el_nombre_de_la_app(monkeypatch, tmp_path):
    pedidos = []

    def falso_config(nombre):
        pedidos.append(("config", nombre))
        return str(tmp_path / "cfg")

    def falso_log(nombre):
        pedidos.append(("log", nombre))
        return str(tmp_path / "lg")

    monkeypatch.setattr(modulo_rutas.platformdirs, "user_config_dir", falso_config)
    monkeypatch.setattr(modulo_rutas.platformdirs, "user_log_dir", falso_log)
    r = Rutas()
    assert r.directorio_config == tmp_path / "cfg"
    assert r.directorio_log == tmp_path / "lg"
    assert pedidos == [("config", "ProxLaunch"), ("log", "ProxLaunch")]


def test_rutas_no_crean_carpetas_al_construirse(tmp_path):
    Rutas(tmp_path / "no-existe")
    assert not (tmp_path / "no-existe").exists()
