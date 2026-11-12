"""Configuración común de pruebas.

- Los marcadores `integracion` requieren PROXLAUNCH_LAB=1.
- Qt corre sin pantalla (offscreen) para que las pruebas de interfaz funcionen en CI.
- Los secretos registrados en el filtro del log se olvidan entre casos (RNF-06).
"""

import os

# Debe fijarse antes de que se cree cualquier QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from proxlaunch.nucleo.registro import olvidar_secretos  # noqa: E402


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PROXLAUNCH_LAB") == "1":
        return
    saltar = pytest.mark.skip(reason="requiere el laboratorio: defina PROXLAUNCH_LAB=1")
    for item in items:
        if "integracion" in item.keywords:
            item.add_marker(saltar)


@pytest.fixture(autouse=True)
def _olvidar_secretos_entre_casos():
    """Evita que un secreto registrado en un caso se filtre al siguiente."""
    olvidar_secretos()
    yield
    olvidar_secretos()
