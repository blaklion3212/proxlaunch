"""CA-18.4 / CA-23.4 / RNF-02: el núcleo funciona sin PySide6 ni la capa de interfaz."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import proxlaunch

RAIZ_SRC = Path(proxlaunch.__file__).resolve().parent.parent

MODULOS_DEL_NUCLEO = [
    "proxlaunch.nucleo",
    "proxlaunch.nucleo.errores",
    "proxlaunch.nucleo.validacion",
    "proxlaunch.nucleo.capacidades",
    "proxlaunch.nucleo.valores_defecto",
    "proxlaunch.nucleo.constructor_peticion",
    "proxlaunch.nucleo.seleccion_nodo",
    "proxlaunch.nucleo.registro",
    "proxlaunch.nucleo.reloj",
    "proxlaunch.nucleo.modelos",
    "proxlaunch.nucleo.persistencia.almacen_json",
    "proxlaunch.nucleo.persistencia.huellas",
    "proxlaunch.nucleo.persistencia.perfiles",
    "proxlaunch.nucleo.persistencia.preferencias",
    "proxlaunch.nucleo.persistencia.rutas",
    "proxlaunch.nucleo.persistencia.secretos",
]

# Subproceso: bloquea cualquier importación de PySide6/shiboken6 y luego importa el núcleo.
GUION = textwrap.dedent(
    """
    import importlib
    import sys

    class BloqueaQt:
        def find_spec(self, nombre, ruta=None, destino=None):
            if nombre.split(".")[0] in ("PySide6", "shiboken6", "PyQt5", "PyQt6"):
                raise ImportError("Qt no está disponible: " + nombre)
            return None

    sys.meta_path.insert(0, BloqueaQt())
    for nombre in sys.argv[1:]:
        importlib.import_module(nombre)

    qt = [m for m in sys.modules if m.split(".")[0] in ("PySide6", "shiboken6")]
    interfaz = [m for m in sys.modules if m.startswith("proxlaunch.interfaz")]
    assert not qt, "el núcleo cargó Qt: %s" % qt
    assert not interfaz, "el núcleo cargó la interfaz: %s" % interfaz
    print("OK")
    """
)


def _ejecutar(args):
    entorno = {**os.environ, "PYTHONPATH": str(RAIZ_SRC)}
    return subprocess.run(
        [sys.executable, "-c", GUION, *args],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=60,
    )


def test_ca18_4_el_nucleo_se_importa_sin_pyside6():
    r = _ejecutar(MODULOS_DEL_NUCLEO)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "OK"


def test_el_bloqueo_del_subproceso_funciona_de_verdad():
    """Control negativo: importar el tema (que sí usa Qt) debe fallar en el subproceso."""
    r = _ejecutar(["proxlaunch.interfaz.tema.gestor_tema"])
    assert r.returncode != 0
    assert "Qt no está disponible" in r.stderr
