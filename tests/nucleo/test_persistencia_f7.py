"""Persistencia (ronda F7): errores de lectura sin excepción, perfiles con tipos incorrectos
descartados y recuperación de huellas desde la copia dañada."""

import json
from pathlib import Path

import pytest

from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles

HUELLA = ":".join(["AB"] * 32)
HUELLA2 = ":".join(["CD"] * 32)


# --- OSError al leer ---------------------------------------------------------------------


def test_leer_un_directorio_en_vez_de_archivo_da_vacio_con_error_de_lectura(tmp_path):
    ruta = tmp_path / "datos.json"
    ruta.mkdir()
    r = AlmacenJson(ruta).leer()
    assert r.datos == {}
    assert r.hubo_corrupcion is True
    assert r.error_lectura is True
    assert r.copia_danada is None


def test_leer_sin_permiso_da_vacio_con_error_de_lectura(tmp_path, monkeypatch):
    ruta = tmp_path / "datos.json"
    ruta.write_text("{}", encoding="utf-8")

    def sin_permiso(self, *a, **k):
        raise PermissionError(13, "denegado")

    monkeypatch.setattr(Path, "read_text", sin_permiso)
    r = AlmacenJson(ruta).leer()
    assert (r.datos, r.hubo_corrupcion, r.error_lectura, r.copia_danada) == ({}, True, True, None)


@pytest.mark.parametrize("clase", [RepositorioPerfiles, RepositorioHuellas])
def test_los_repositorios_no_lanzan_si_la_ruta_es_un_directorio(tmp_path, clase):
    ruta = tmp_path / "x.json"
    ruta.mkdir()
    repo = clase(ruta)
    if clase is RepositorioPerfiles:
        assert repo.listar() == []
    else:
        assert repo.obtener("10.0.0.1", 8006) is None
    assert repo.hubo_corrupcion is True
    assert repo.error_lectura is True
    assert repo.copia_danada is None


# --- Perfiles con tipos incorrectos ---------------------------------------------------------

BASE = {"id": "p1", "nombre": "lab", "hosts": ["10.0.0.5"], "puerto": 8006}


@pytest.mark.parametrize(
    "cambio",
    [
        {"hosts": "10.0.0.5"},
        {"hosts": []},
        {"hosts": [5]},
        {"hosts": [""]},
        {"hosts": None},
        {"puerto": "abc"},
        {"puerto": "8006"},
        {"puerto": True},
        {"puerto": 0},
        {"puerto": 70000},
        {"puerto": 80.5},
        {"nombre": 5},
        {"id": None},
        {"usuario": ["x"]},
        {"realm": 3},
        {"ignorar_ssl": "si"},
        {"recordar_credenciales": 1},
        {"metodo": "inexistente"},
    ],
    ids=lambda c: next(iter(c)) + "=" + repr(next(iter(c.values()))),
)
def test_perfil_con_tipos_incorrectos_se_descarta(tmp_path, cambio):
    ruta = tmp_path / "perfiles.json"
    bueno = {**BASE, "id": "bueno", "nombre": "bueno"}
    ruta.write_text(json.dumps({"perfiles": [{**BASE, **cambio}, bueno]}), encoding="utf-8")
    perfiles = RepositorioPerfiles(ruta).listar()
    assert [p.id for p in perfiles] == ["bueno"]


def test_perfil_valido_se_conserva(tmp_path):
    ruta = tmp_path / "perfiles.json"
    ruta.write_text(json.dumps({"perfiles": [BASE]}), encoding="utf-8")
    assert [p.id for p in RepositorioPerfiles(ruta).listar()] == ["p1"]


# --- Huellas: recuperación desde la copia dañada ----------------------------------------------


def test_archivo_de_huellas_danado_recupera_las_entradas_legibles(tmp_path):
    ruta = tmp_path / "huellas.json"
    truncado = (
        '{"version_esquema": 1, "huellas": {'
        f'"10.0.0.1:8006": "{HUELLA}", "10.0.0.2:8006": "{HUELLA2}", "10.0.0.3:8006": "AB:C'
    )
    ruta.write_text(truncado, encoding="utf-8")
    repo = RepositorioHuellas(ruta)
    assert repo.obtener("10.0.0.1", 8006) == HUELLA
    assert repo.obtener("10.0.0.2", 8006) == HUELLA2
    assert repo.obtener("10.0.0.3", 8006) is None  # la ilegible no se inventa
    assert repo.hubo_corrupcion is True
    assert repo.copia_danada is not None and repo.copia_danada.exists()
    assert set(repo.huellas_recuperadas) == {"10.0.0.1:8006", "10.0.0.2:8006"}


def test_las_huellas_recuperadas_se_restauran_en_el_archivo(tmp_path):
    ruta = tmp_path / "huellas.json"
    ruta.write_text(f'{{"huellas": {{"10.0.0.1:8006": "{HUELLA}", ', encoding="utf-8")
    RepositorioHuellas(ruta).obtener("10.0.0.1", 8006)
    nuevo = RepositorioHuellas(ruta)  # otra instancia: lee el archivo ya restaurado
    assert nuevo.obtener("10.0.0.1", 8006) == HUELLA
    assert nuevo.hubo_corrupcion is False


def test_archivo_dañado_sin_entradas_legibles_no_recupera_nada(tmp_path):
    ruta = tmp_path / "huellas.json"
    ruta.write_text("basura {{{", encoding="utf-8")
    repo = RepositorioHuellas(ruta)
    assert repo.obtener("10.0.0.1", 8006) is None
    assert repo.hubo_corrupcion is True
    assert repo.huellas_recuperadas == ()


def test_archivo_sano_no_marca_recuperacion(tmp_path):
    repo = RepositorioHuellas(tmp_path / "huellas.json")
    repo.guardar("10.0.0.1", 8006, HUELLA)
    assert repo.obtener("10.0.0.1", 8006) == HUELLA
    assert repo.hubo_corrupcion is False
    assert repo.huellas_recuperadas == ()
