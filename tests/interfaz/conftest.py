"""Fixtures comunes de las pruebas de interfaz (todo sin red, sin llavero ni rutas reales)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from proxlaunch.interfaz import trabajadores as tr
from proxlaunch.interfaz import ventana_principal as vp
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


@pytest.fixture
def dir_iconos(tmp_path):
    """Carpeta de iconos del tema en ``tmp_path`` (la que usa ``GestorTema`` por defecto)."""
    return tmp_path / "cache" / "tema"


@pytest.fixture(autouse=True)
def _cache_de_iconos_en_tmp(monkeypatch, tmp_path):
    """Ningún ``GestorTema`` escribe iconos en la caché real: se desvía a ``tmp_path``."""
    monkeypatch.setattr(
        Rutas, "directorio_cache", property(lambda self: tmp_path / "cache"), raising=True
    )


@pytest.fixture(autouse=True)
def _sin_pregunta_de_cambios_sin_guardar(monkeypatch):
    """«¿Guardar el lote antes de continuar?» (RF-G08) responde «No guardar» por defecto."""
    monkeypatch.setattr(vp.VentanaPrincipal, "_preguntar_guardar_cambios", lambda self: "descartar")


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
    gestor = GestorTema(qapp, ModoTema.OSCURO, directorio_iconos=rutas.directorio_cache / "tema")
    return Dependencias(
        servicio_conexion=servicio_falso,  # type: ignore[arg-type]
        perfiles=RepositorioPerfiles(rutas.perfiles),
        huellas=RepositorioHuellas(rutas.huellas),
        secretos=AlmacenSecretos(backend=llavero),
        preferencias=RepositorioPreferencias(rutas.preferencias),
        reloj=RelojSimulado(),
        gestor_tema=gestor,
        # Informes parciales en la carpeta temporal, nunca en la de datos del usuario.
        directorio_informes=rutas.directorio_datos / "informes",
        directorio_lotes=rutas.lotes,
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


# --- Lotes (MVP 2): fixtures compartidos por las pruebas de la ventana -------------------------


@pytest.fixture
def confirmaciones(monkeypatch):
    """Sustituye ``confirmar``: registra las preguntas y responde lo programado (sí por defecto)."""
    from .apoyo_ventana_lote import Confirmaciones

    c = Confirmaciones(True)
    monkeypatch.setattr(vp, "confirmar", c)
    return c


@pytest.fixture
def descubrimiento_falso(request, monkeypatch):
    """Replanificar y reintentar releen el inventario de la prueba, sin tocar la red."""
    entorno = request.getfixturevalue("entorno")
    monkeypatch.setattr(tr, "descubrir", lambda sesion: entorno.inv)


@pytest.fixture
def limpieza(request, monkeypatch, descubrimiento_falso):
    """Nunca bloquea al cerrar: libera puertas, abandona esperas y evita la confirmación."""
    entorno = request.getfixturevalue("entorno")
    monkeypatch.setattr(vp, "confirmar", lambda *a, **k: True)
    yield
    cr = entorno.creacion
    for puerta in getattr(cr, "puertas", {}).values():
        puerta.set()
    cliente = getattr(entorno, "cliente", None)
    if cliente is not None and cliente.puerta_eliminar is not None:
        cliente.puerta_eliminar.set()
    v = entorno.ventana
    lote = v._lote
    if lote is not None:
        lote.control.dejar_de_esperar()
        if lote.control_rollback is not None:
            lote.control_rollback.cancelar()
        lote.control.reanudar()
    reloj = entorno.deps.reloj
    if hasattr(reloj, "liberar"):
        reloj.liberar.set()
    v._lanzador.esperar(3000)
    v._lote = None  # evita la confirmación de cierre de la ventana


@pytest.fixture
def widget_padre(qtbot):
    """Widget visible que hace de padre de los diálogos que abre el controlador del origen."""
    from PySide6.QtWidgets import QWidget

    w = QWidget()
    qtbot.addWidget(w)
    w.show()
    return w
