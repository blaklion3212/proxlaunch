"""Pruebas de humo del esqueleto."""

import ast
from pathlib import Path

import proxlaunch


def test_paquete_importa_y_tiene_version():
    assert isinstance(proxlaunch.__version__, str)
    assert proxlaunch.__version__


def test_nucleo_no_importa_pyside6():
    raiz = Path(proxlaunch.__file__).parent / "nucleo"
    ofensores = []
    for archivo in raiz.rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                nombres = [nodo.module or ""]
            else:
                continue
            if any(n.split(".")[0] == "PySide6" for n in nombres):
                ofensores.append(str(archivo))
    assert not ofensores, f"El núcleo importa PySide6: {ofensores}"
