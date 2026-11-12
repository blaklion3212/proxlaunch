"""Configuración común de pruebas: los marcadores `integracion` requieren PROXLAUNCH_LAB=1."""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PROXLAUNCH_LAB") == "1":
        return
    saltar = pytest.mark.skip(reason="requiere el laboratorio: defina PROXLAUNCH_LAB=1")
    for item in items:
        if "integracion" in item.keywords:
            item.add_marker(saltar)
