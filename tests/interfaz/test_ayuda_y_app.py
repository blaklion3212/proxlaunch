"""Textos de ayuda (RF-25) y arranque de la aplicación (sin abrir ventanas reales)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from proxlaunch.interfaz import app as modulo_app
from proxlaunch.interfaz import ayuda as ay
from proxlaunch.interfaz.tema import GestorTema, ModoTema
from proxlaunch.interfaz.ventana_principal import Dependencias, VentanaPrincipal
from proxlaunch.nucleo.persistencia.rutas import Rutas
from proxlaunch.nucleo.servicios.conexion import PRIVILEGIOS_REQUERIDOS

# --- Ayuda ------------------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ay.CAMPOS_AYUDA)
def test_cada_campo_tecnico_tiene_ayuda_breve(campo):
    # CA-25.1: de 1 a 3 frases.
    texto = ay.ayuda(campo)
    assert texto.strip()
    frases = [f for f in texto.replace("?", ".").split(".") if f.strip()]
    assert 1 <= len(frases) <= 3


@pytest.mark.parametrize(
    "campo",
    [
        "recordar",
        "ignorar_ssl",
        "version_forzada",
        "sin_disco",
        "memoria",
        "controlador",
        "almacenamiento",
        "tamano",
        "modelo_red",
    ],
)
def test_otros_campos_con_ayuda(campo):
    assert ay.ayuda(campo)


def test_ayuda_de_campo_inexistente_es_cadena_vacia():
    assert ay.ayuda("no-existe") == ""


def test_aviso_de_cpu_host_menciona_mover_entre_nodos():
    assert "nodos" in ay.ayuda_cpu_host()


def test_guia_de_token_cubre_los_privilegios_que_exige_el_nucleo():
    privilegios = set(ay.privilegios_guia_token().splitlines())
    assert set(PRIVILEGIOS_REQUERIDOS) <= privilegios
    assert set(ay.PRIVILEGIOS_ROL) == privilegios


def test_guia_de_token_tiene_pasos_notas_y_titulo():
    assert ay.titulo_guia_token()
    pasos = ay.pasos_guia_token()
    assert len(pasos) >= 4 and all("{" not in p for p in pasos)
    assert any(ay.NOMBRE_ROL in p for p in pasos)
    assert any("root@pam" in n for n in ay.notas_guia_token())


# --- Aplicación -------------------------------------------------------------------------------


def test_icono_de_la_aplicacion_tiene_varios_tamanos(qapp):
    icono = modulo_app.crear_icono()
    assert not icono.isNull()
    assert len(icono.availableSizes()) >= 5


def test_cargar_traductor_sin_catalogo_no_falla(qapp):
    # Sea que exista el .qm o no, la función no debe lanzar excepciones.
    resultado = modulo_app.cargar_traductor(qapp)
    assert resultado is None or resultado.parent() is qapp


def test_crear_dependencias_usa_las_rutas_dadas(qapp, tmp_path):
    rutas = Rutas(tmp_path / "datos")
    gestor = GestorTema(qapp, ModoTema.OSCURO)
    deps = modulo_app.crear_dependencias(rutas, gestor)
    assert isinstance(deps, Dependencias)
    assert deps.gestor_tema is gestor
    assert deps.perfiles.listar() == []  # lee de tmp_path, no del usuario
    assert deps.preferencias.cargar().modo.value == "basico"
    assert deps.fabrica_creacion is None


def test_main_arma_la_ventana_y_corre_el_bucle(qapp, tmp_path, monkeypatch):
    creadas = []
    monkeypatch.setattr(modulo_app, "Rutas", lambda: Rutas(tmp_path / "datos"))
    monkeypatch.setattr(modulo_app, "configurar_registro", lambda carpeta: None)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    original = VentanaPrincipal.show
    monkeypatch.setattr(
        VentanaPrincipal, "show", lambda self: creadas.append(self) or original(self)
    )
    antes = QApplication.font()
    try:
        assert modulo_app.main() == 0
    finally:
        qapp.setFont(antes)
    assert len(creadas) == 1
    assert qapp.applicationName() == "ProxLaunch"
    creadas[0].close()
