"""La ventana guarda el informe parcial en ``Dependencias.directorio_informes``.

Regresión: antes se usaba ``platformdirs.user_data_dir`` y las pruebas dejaban cientos de
``parcial-*.txt`` en la carpeta real del desarrollador.
"""

from __future__ import annotations

import threading
from pathlib import Path

import platformdirs
import pytest

from . import test_ventana_principal as _base
from .apoyo import CreacionPorVmid
from .test_lote_ventana_acciones import lanzar

entorno = _base.entorno

pytestmark = pytest.mark.usefixtures("limpieza")


def test_el_parcial_se_guarda_en_el_directorio_de_informes_de_las_dependencias(
    qtbot, entorno, confirmaciones, tmp_path
):
    # Sin tocar nada: se usa el directorio que fija la fixture `deps`.
    carpeta = entorno.deps.directorio_informes
    assert carpeta is not None and Path(carpeta).is_relative_to(tmp_path)

    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)
    qtbot.waitUntil(lambda: entorno.ventana.progreso_lote.hay_enviadas(), timeout=2000)
    v = entorno.ventana
    id_lote = v._lote.plan.id_lote

    assert v.close() is True

    assert (carpeta / f"parcial-{id_lote}.txt").is_file()
    por_defecto = Path(platformdirs.user_data_dir("ProxLaunch")) / "informes"
    assert not (por_defecto / f"parcial-{id_lote}.txt").exists()
