"""Pruebas estáticas del núcleo nuevo del MVP 3 (INV-M4, INV-M1, RNF-M08, CA-X02.3, CA-X05.2).

- INV-M4: nada se ejecuta ni se evalúa: sin ``pickle``, ``eval``, ``exec``, ``yaml``, ``importlib``,
  ``__import__`` ni ejecución de procesos en el código que lee archivos de terceros.
- INV-M1: ninguna función de los módulos de archivos, perfiles, lotes guardados ni CSV recibe una
  ``Sesion`` ni un cliente (solo bytes, rutas e ``Inventario``).
- RNF-M08: se importan sin PySide6 ni la interfaz.
"""

import ast
import inspect
import os
import pkgutil
import subprocess
import sys
import textwrap
from pathlib import Path

import proxlaunch
from proxlaunch.nucleo import archivos, csv_importacion, lotes_guardados, perfiles_maquina

NUCLEO = Path(proxlaunch.__file__).resolve().parent / "nucleo"
PAQUETES = ("archivos", "perfiles_maquina", "lotes_guardados", "csv_importacion")
MODULOS_LOTE_NUEVOS = ("filas.py",)


def _archivos_py() -> list[Path]:
    rutas = [p for paquete in PAQUETES for p in sorted((NUCLEO / paquete).rglob("*.py"))]
    rutas += [NUCLEO / "lote" / n for n in MODULOS_LOTE_NUEVOS]
    return rutas


def _modulos() -> list[str]:
    nombres = []
    for paquete in (archivos, perfiles_maquina, lotes_guardados, csv_importacion):
        for info in pkgutil.walk_packages(paquete.__path__, paquete.__name__ + "."):
            nombres.append(info.name)
        nombres.append(paquete.__name__)
    nombres.append("proxlaunch.nucleo.lote.filas")
    return sorted(set(nombres))


def test_la_lista_de_modulos_revisados_no_esta_vacia():
    assert len(_archivos_py()) >= 25 and len(_modulos()) >= 25


def test_inv_m4_sin_pickle_eval_exec_yaml_importlib_ni_ejecucion_de_procesos():
    prohibidos_nombre = {
        "pickle",
        "cPickle",
        "marshal",
        "shelve",
        "yaml",
        "importlib",
        "subprocess",
        "runpy",
        "ctypes",
        "socket",
        "requests",
        "urllib",
    }
    prohibidas_llamadas = {"eval", "exec", "compile", "__import__", "execfile"}
    ofensas = []
    for ruta in _archivos_py():
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                ofensas += [
                    (ruta.name, a.name)
                    for a in nodo.names
                    if a.name.split(".")[0] in prohibidos_nombre
                ]
            elif (
                isinstance(nodo, ast.ImportFrom)
                and nodo.module
                and nodo.module.split(".")[0] in prohibidos_nombre
            ):
                ofensas.append((ruta.name, nodo.module))
            elif isinstance(nodo, ast.Call):
                f = nodo.func
                if (
                    isinstance(f, ast.Name) and f.id in prohibidas_llamadas
                ):  # funciones incorporadas
                    ofensas.append((ruta.name, f.id))
                elif (
                    isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name)
                    and f.value.id in {"os", "pickle", "yaml", "marshal"}
                    and f.attr
                    in {"system", "popen", "spawn", "Popen", "load", "loads", "execv", "execvp"}
                ):
                    ofensas.append((ruta.name, f"{f.value.id}.{f.attr}"))
    assert ofensas == []


def test_solo_se_interpreta_json_con_json_loads_y_csv_con_csv_reader():
    """CA-X02.3: ``json.load`` (con archivo) no se usa y ``json.loads`` solo en el módulo estricto."""  # noqa: E501
    usos_loads = [r.name for r in _archivos_py() if "json.loads(" in r.read_text(encoding="utf-8")]
    assert usos_loads == ["json_estricto.py"]
    usos_reader = [r.name for r in _archivos_py() if "csv.reader(" in r.read_text(encoding="utf-8")]
    assert set(usos_reader) <= {"lectura.py", "separador.py"}


def test_inv_m1_ninguna_funcion_publica_recibe_sesion_cliente_ni_transporte():
    ofensas = []
    for nombre in _modulos():
        modulo = __import__(nombre, fromlist=["x"])
        for n, objeto in vars(modulo).items():
            if n.startswith("_") or getattr(objeto, "__module__", None) != nombre:
                continue
            funciones = (
                [objeto]
                if inspect.isfunction(objeto)
                else [m for _, m in inspect.getmembers(objeto, inspect.isfunction)]
                if inspect.isclass(objeto)
                else []
            )
            for f in funciones:
                for parametro in inspect.signature(f).parameters.values():
                    texto = f"{parametro.name} {parametro.annotation}".lower()
                    if any(
                        x in texto for x in ("sesion", "cliente", "transporte", "clienteproxmox")
                    ):
                        ofensas.append((nombre, f.__qualname__, parametro.name))
    assert ofensas == []


def test_los_modulos_nuevos_no_importan_la_capa_api_ni_servicios():
    """Solo el planificador (con su GET) toca el servidor; el resto del MVP 3 ni lo importa."""
    ofensas = []
    for ruta in _archivos_py():
        if ruta.name == "filas.py":
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            modulo = ""
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                modulo = nodo.module
            elif isinstance(nodo, ast.Import):
                modulo = nodo.names[0].name
            if modulo.startswith(
                (
                    "proxlaunch.nucleo.api",
                    "proxlaunch.nucleo.servicios",
                    "proxlaunch.interfaz",
                    "PySide6",
                )
            ):
                ofensas.append((ruta.name, modulo))
    assert ofensas == []


GUION_SIN_QT = textwrap.dedent(
    """
    import importlib, sys

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
    assert not qt, qt
    assert not interfaz, interfaz
    print("OK")
    """
)


def test_rnf_m08_el_nucleo_nuevo_se_importa_sin_pyside6_ni_la_interfaz():
    entorno = {**os.environ, "PYTHONPATH": str(NUCLEO.parent.parent)}
    r = subprocess.run(
        [sys.executable, "-c", GUION_SIN_QT, *_modulos()],
        env=entorno,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr[-2000:]


def test_ningun_modulo_abre_archivos_directamente_con_open():
    """CA-X03.3 / INV-M3: todo pasa por ``leer_archivo_limitado``, ``escribir_atomico`` o ``AlmacenJson``."""  # noqa: E501
    pasos = []
    for ruta in _archivos_py():
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "open"
            ):
                pasos.append(ruta.name)
    assert (
        pasos == []
    )  # ningún ``open`` directo: todo pasa por lector_limitado/escribir_atomico/AlmacenJson


def test_las_constantes_unicas_solo_se_definen_en_archivos_constantes_y_max_lote_nunca():
    """RNF-M02 / CA-C15.2: ``MAX_BYTES_*``, ``MAX_COLUMNAS_CSV``... solo en
    ``archivos/constantes.py``;
    ``MAX_LOTE`` es la de M2 (se importa, no se redefine)."""
    unicas = {
        "MAX_BYTES_PERFILES",
        "MAX_BYTES_LOTE",
        "MAX_BYTES_CSV",
        "MAX_COLUMNAS_CSV",
        "MAX_PERFILES_USUARIO",
        "PROFUNDIDAD_JSON_MAX",
        "MAX_LONG_TEXTO",
        "LONG_NOMBRE_PERFIL",
        "MAX_PROBLEMAS_FILA",
    }
    ofensas = []
    for ruta in _archivos_py():
        for nodo in ast.parse(ruta.read_text(encoding="utf-8")).body:
            destinos = (
                nodo.targets
                if isinstance(nodo, ast.Assign)
                else [nodo.target]
                if isinstance(nodo, ast.AnnAssign)
                else []
            )
            for d in destinos:
                if isinstance(d, ast.Name) and (
                    d.id == "MAX_LOTE" or (d.id in unicas and ruta.name != "constantes.py")
                ):
                    ofensas.append((ruta.name, d.id))
    assert ofensas == []
