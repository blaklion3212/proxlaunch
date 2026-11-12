"""Fixtures comunes de las pruebas de interfaz (todo sin red, sin llavero ni rutas reales)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from proxlaunch.interfaz.tema import GestorTema, ModoTema
from proxlaunch.interfaz.ventana_principal import Dependencias
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.persistencia.preferencias import RepositorioPreferencias
from proxlaunch.nucleo.persistencia.rutas import Rutas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo import (
    LlaveroFalso,
    ServicioConexionFalso,
    inventario_cluster,
    inventario_individual,
)


@pytest.fixture(autouse=True)
def _sin_cajas_modales(monkeypatch):
    """Ningún QMessageBox puede bloquear: por defecto responde «No»."""
    for nombre in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, nombre, lambda *a, **k: QMessageBox.StandardButton.No)


@pytest.fixture
def inv_cluster():
    return inventario_cluster()


@pytest.fixture
def inv_individual():
    return inventario_individual()


@pytest.fixture
def llavero():
    return LlaveroFalso()


@pytest.fixture
def rutas(tmp_path):
    return Rutas(tmp_path / "datos")


@pytest.fixture
def servicio_falso():
    return ServicioConexionFalso()


@pytest.fixture
def deps(qapp, rutas, llavero, servicio_falso):
    """Dependencias con repositorios en ``tmp_path``, llavero en memoria y servicio falso."""
    gestor = GestorTema(qapp, ModoTema.OSCURO)
    return Dependencias(
        servicio_conexion=servicio_falso,  # type: ignore[arg-type]
        perfiles=RepositorioPerfiles(rutas.perfiles),
        huellas=RepositorioHuellas(rutas.huellas),
        secretos=AlmacenSecretos(backend=llavero),
        preferencias=RepositorioPreferencias(rutas.preferencias),
        reloj=RelojSimulado(),
        gestor_tema=gestor,
    )


@pytest.fixture(autouse=True)
def _cerrar_ventanas(qapp):
    yield
    for w in QApplication.topLevelWidgets():
        w.close()


@pytest.fixture
def hacer_cfg_ui():
    """Configuración válida sobre ``inv_cluster`` con valores no predeterminados."""
    from proxlaunch.nucleo.modelos.vm import (
        Ballooning,
        Bus,
        ConfiguracionVM,
        Disco,
        InterfazRed,
        ModeloRed,
    )

    def _hacer(**cambios):
        base = {
            "vmid": 150,
            "nombre": "srv-web-01",
            "nodo": "pve1",
            "sockets": 2,
            "cores": 4,
            "tipo_cpu": "x86-64-v3",
            "memoria_mib": 4096,
            "ballooning": Ballooning(True, 1024),
            "discos": [
                Disco("local-lvm", 20, Bus.VIRTIO, ssd=False),
                Disco("local", 10, Bus.SATA, iothread=False),
            ],
            "redes": [InterfazRed("vmbr1", ModeloRed.E1000, 120)],
        }
        base.update(cambios)
        return ConfiguracionVM(**base)

    return _hacer
