"""Aislamiento de las carpetas del usuario: las pruebas nunca escriben en las reales.

La protección vive en ``tests/conftest.py`` (redirección del entorno al importar y guarda al
terminar la sesión). Estas pruebas demuestran que funciona.
"""

from __future__ import annotations

import os
from pathlib import Path

import platformdirs
import pytest

NOMBRE = "ProxLaunch"


def _dentro_de(ruta: Path, base: Path) -> bool:
    return Path(os.path.realpath(ruta)).is_relative_to(Path(os.path.realpath(base)))


def test_las_carpetas_de_platformdirs_caen_en_la_carpeta_temporal(aislamiento_sesion):
    temporal = aislamiento_sesion.temporal
    resueltas = [
        platformdirs.user_data_dir(NOMBRE),
        platformdirs.user_config_dir(NOMBRE),
        platformdirs.user_log_dir(NOMBRE),
        platformdirs.user_state_dir(NOMBRE),
        platformdirs.user_cache_dir(NOMBRE),
        Path.home(),
    ]
    for ruta in resueltas:
        assert _dentro_de(Path(ruta), temporal), ruta


def test_escribir_en_user_data_dir_no_toca_la_carpeta_real(aislamiento_sesion):
    destino = Path(platformdirs.user_data_dir(NOMBRE)) / "informes"
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / "parcial-prueba-aislamiento.txt"
    archivo.write_text("contenido de prueba", encoding="utf-8")

    assert _dentro_de(archivo, aislamiento_sesion.temporal)
    for real in aislamiento_sesion.reales:
        assert not _dentro_de(archivo, real)
        assert not (real / "informes" / archivo.name).exists()


def test_la_guarda_detecta_un_archivo_nuevo_en_una_carpeta_real(tmp_path, instantanea_carpetas):
    real = tmp_path / "real"
    real.mkdir()
    (real / "previo.txt").write_text("a", encoding="utf-8")
    antes = instantanea_carpetas([real])

    (real / "nuevo.txt").write_text("b", encoding="utf-8")
    despues = instantanea_carpetas([real])

    cambiados = [r for r, e in despues.items() if r not in antes or antes[r] != e]
    assert cambiados == [real / "nuevo.txt"]


def test_la_guarda_detecta_un_archivo_modificado(tmp_path, instantanea_carpetas):
    real = tmp_path / "real"
    real.mkdir()
    archivo = real / "previo.txt"
    archivo.write_text("a", encoding="utf-8")
    antes = instantanea_carpetas([real])

    archivo.write_text("contenido más largo", encoding="utf-8")
    despues = instantanea_carpetas([real])

    assert despues[archivo] != antes[archivo]


def test_la_guarda_ignora_carpetas_inexistentes(tmp_path, instantanea_carpetas):
    assert instantanea_carpetas([tmp_path / "no-existe"]) == {}


@pytest.mark.skipif(os.name != "nt", reason="la desviación de platformdirs es solo de Windows")
def test_en_windows_platformdirs_respeta_localappdata_redirigido(aislamiento_sesion):
    assert _dentro_de(Path(platformdirs.user_data_dir(NOMBRE)), aislamiento_sesion.temporal)
