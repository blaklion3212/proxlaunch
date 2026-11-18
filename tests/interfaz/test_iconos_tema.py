"""Iconos SVG del tema: flechas y palomita (R1-R8 del cambio de iconos)."""

import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import platformdirs
import pytest
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox, QWidget

from proxlaunch.interfaz.tema import iconos as modulo_iconos
from proxlaunch.interfaz.tema.gestor_tema import (
    GestorTema,
    ModoTema,
    generar_qss,
    leer_plantilla,
    quitar_iconos,
)
from proxlaunch.interfaz.tema.iconos import generar_iconos
from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO
from proxlaunch.nucleo.persistencia.rutas import Rutas

TEMAS = {"oscuro": TOKENS_OSCURO, "claro": TOKENS_CLARO}
# marcador -> token de color esperado
COLOR_DE = {
    "icono_flecha_abajo": "texto_secundario",
    "icono_flecha_arriba": "texto_secundario",
    "icono_flecha_abajo_deshabilitada": "texto_deshabilitado",
    "icono_flecha_arriba_deshabilitada": "texto_deshabilitado",
    "icono_palomita": "acento_texto",
    "icono_palomita_deshabilitada": "texto_deshabilitado",
}
RE_URL = re.compile(r'url\("([^"]*)"\)')


def _color_svg(ruta: str) -> str:
    raiz = ET.parse(ruta).getroot()
    colores = {e.get("fill") for e in raiz.iter() if e.get("fill") not in (None, "none")}
    colores |= {e.get("stroke") for e in raiz.iter() if e.get("stroke")}
    assert len(colores) == 1, colores
    return colores.pop()


@pytest.fixture
def aplicado(qapp, tmp_path):
    """GestorTema real con iconos en tmp_path; restaura la hoja de la aplicación al salir."""
    anterior = qapp.styleSheet()
    gestor = GestorTema(qapp, ModoTema.CLARO, directorio_iconos=tmp_path / "iconos")
    yield gestor
    qapp.setStyleSheet(anterior)


# --- R1: archivos y contenido -------------------------------------------------------


@pytest.mark.parametrize("tema", TEMAS)
def test_r1_se_crean_los_seis_svg_validos_con_el_color_del_token(tmp_path, tema):
    tokens = TEMAS[tema]
    rutas = generar_iconos(tokens, tmp_path / "t")
    assert set(rutas) == set(COLOR_DE)
    for marcador, token in COLOR_DE.items():
        ruta = rutas[marcador]
        assert Path(ruta).is_file()
        raiz = ET.parse(ruta).getroot()  # XML parseable
        assert raiz.tag.endswith("svg")
        assert raiz.get("viewBox")
        assert _color_svg(ruta).lower() == tokens[token].lower()
    assert len(list((tmp_path / "t").glob("*.svg"))) == 6


def test_r1_los_colores_de_los_tokens_son_distintos_entre_flecha_y_palomita(tmp_path):
    # Protege la prueba anterior: si dos tokens coincidieran no distinguiría su origen.
    for tokens in TEMAS.values():
        assert len({tokens[t] for t in set(COLOR_DE.values())}) == 3


def test_r1_no_quedan_temporales_tras_escribir(tmp_path):
    generar_iconos(TOKENS_CLARO, tmp_path / "t")
    assert list((tmp_path / "t").glob("*.tmp")) == []


# --- R2: nombres deterministas ------------------------------------------------------


def test_r2_repetir_no_crea_archivos_nuevos_ni_reescribe(tmp_path):
    carpeta = tmp_path / "t"
    primera = generar_iconos(TOKENS_CLARO, carpeta)
    antes = {p.name: p.stat().st_mtime_ns for p in carpeta.iterdir()}
    for ruta in carpeta.iterdir():  # mtime antiguo: un reescrito lo cambiaría
        os.utime(ruta, ns=(1_000_000_000, 1_000_000_000))
    segunda = generar_iconos(TOKENS_CLARO, carpeta)
    despues = {p.name: p.stat().st_mtime_ns for p in carpeta.iterdir()}
    assert primera == segunda
    assert set(antes) == set(despues)
    assert set(despues.values()) == {1_000_000_000}


def test_r2_otros_colores_crean_archivos_distintos(tmp_path):
    carpeta = tmp_path / "t"
    claro = generar_iconos(TOKENS_CLARO, carpeta)
    oscuro = generar_iconos(TOKENS_OSCURO, carpeta)
    # La palomita usa el mismo color (acento_texto) en ambos temas: comparte archivo.
    assert TOKENS_CLARO["acento_texto"] == TOKENS_OSCURO["acento_texto"]
    assert claro["icono_palomita"] == oscuro["icono_palomita"]
    distintos = set(COLOR_DE) - {"icono_palomita"}  # incluye la palomita deshabilitada
    assert all(claro[m] != oscuro[m] for m in distintos)
    assert len(list(carpeta.glob("*.svg"))) == 11


def test_r2_el_nombre_incluye_el_color(tmp_path):
    rutas = generar_iconos(TOKENS_CLARO, tmp_path / "t")
    secundario = TOKENS_CLARO["texto_secundario"].lstrip("#").lower()
    assert secundario in Path(rutas["icono_flecha_abajo"]).name


def test_r2_un_archivo_corrupto_se_repara(tmp_path):
    rutas = generar_iconos(TOKENS_CLARO, tmp_path / "t")
    ruta = Path(rutas["icono_palomita"])
    ruta.write_text("basura", "utf-8")
    generar_iconos(TOKENS_CLARO, tmp_path / "t")
    ET.parse(ruta)  # vuelve a ser XML válido


# --- R3: rutas posix y plantilla ----------------------------------------------------


def test_r3_las_rutas_son_posix_y_absolutas(tmp_path):
    for ruta in generar_iconos(TOKENS_CLARO, tmp_path / "t").values():
        assert "\\" not in ruta
        assert ruta.endswith(".svg")
        assert ruta.startswith(tmp_path.as_posix())


def test_r3_la_plantilla_final_lleva_las_rutas_entre_comillas(tmp_path):
    rutas = generar_iconos(TOKENS_CLARO, tmp_path / "t")
    qss = generar_qss(leer_plantilla(), {**TOKENS_CLARO, **rutas})
    assert "{{" not in qss
    urls = set(RE_URL.findall(qss))
    assert urls == set(rutas.values())


def test_r3_ruta_con_espacios_y_acentos(tmp_path):
    carpeta = tmp_path / "José Pérez dir"
    rutas = generar_iconos(TOKENS_CLARO, carpeta)
    assert len(rutas) == 6
    for ruta in rutas.values():
        assert "José Pérez dir" in ruta
        assert Path(ruta).is_file()
    qss = generar_qss(leer_plantilla(), {**TOKENS_CLARO, **rutas})
    assert f'url("{rutas["icono_palomita"]}")' in qss


# --- R4: fallo de escritura ---------------------------------------------------------


def _carpeta_imposible(tmp_path):
    archivo = tmp_path / "es_un_archivo"
    archivo.write_text("x", "utf-8")
    return archivo / "tema"


def test_r4_carpeta_no_creable_devuelve_vacio_y_avisa(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="proxlaunch"):
        assert generar_iconos(TOKENS_CLARO, _carpeta_imposible(tmp_path)) == {}
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert avisos
    assert all(r.name.startswith("proxlaunch") for r in avisos)


def test_r4_fallo_al_escribir_un_archivo_devuelve_vacio(tmp_path, monkeypatch, caplog):
    def falla(*_a, **_k):
        raise OSError("disco lleno")

    monkeypatch.setattr(modulo_iconos.os, "replace", falla)
    with caplog.at_level(logging.WARNING, logger="proxlaunch"):
        assert generar_iconos(TOKENS_CLARO, tmp_path / "t") == {}
    assert any("disco lleno" in r.getMessage() for r in caplog.records)


def test_r4_quitar_iconos_elimina_las_imagenes_y_nada_mas():
    plantilla = leer_plantilla()
    sin = quitar_iconos(plantilla)
    assert "icono_" not in sin
    assert "image:" not in sin
    assert "{{texto}}" in sin  # el resto de marcadores sigue intacto
    assert quitar_iconos(sin) == sin  # idempotente
    assert quitar_iconos("QWidget { color: red; }") == "QWidget { color: red; }"


@pytest.mark.parametrize("modo", [ModoTema.CLARO, ModoTema.OSCURO])
def test_r4_aplicar_sin_iconos_instala_hoja_sin_url_ni_marcadores(qapp, tmp_path, modo, caplog):
    anterior = qapp.styleSheet()
    try:
        gestor = GestorTema(qapp, modo, directorio_iconos=_carpeta_imposible(tmp_path))
        with caplog.at_level(logging.WARNING, logger="proxlaunch"):
            gestor.aplicar()  # no debe lanzar
        hoja = qapp.styleSheet()
        assert hoja
        assert "url(" not in hoja
        assert "{{" not in hoja
        assert "}}" not in hoja
        assert gestor.tema_actual == modo.value
    finally:
        qapp.setStyleSheet(anterior)


# --- R5: cambio de tema -------------------------------------------------------------


def test_r5_cambiar_de_tema_cambia_las_rutas_de_iconos(qapp, aplicado):
    aplicado.establecer_modo(ModoTema.CLARO)
    claro = set(RE_URL.findall(qapp.styleSheet()))
    aplicado.establecer_modo(ModoTema.OSCURO)
    oscuro = set(RE_URL.findall(qapp.styleSheet()))
    assert len(claro) == 6
    assert len(oscuro) == 6
    # Todo cambia de archivo salvo la palomita, que comparte color (acento_texto) en ambos temas.
    assert len(claro - oscuro) == 5
    esperado = TOKENS_OSCURO["texto_secundario"].lstrip("#").lower()
    assert any(esperado in u for u in oscuro)
    for ruta in claro | oscuro:
        assert Path(ruta).is_file()
    aplicado.establecer_modo(ModoTema.CLARO)
    assert set(RE_URL.findall(qapp.styleSheet())) == claro


# --- R6: widgets reales -------------------------------------------------------------


def _formulario(qtbot):
    ventana = QWidget()
    combo = QComboBox(ventana)
    combo.addItems(["uno", "dos"])
    numero = QSpinBox(ventana)
    decimal = QDoubleSpinBox(ventana)
    inhabilitado = QSpinBox(ventana)
    inhabilitado.setEnabled(False)
    casilla = QCheckBox("marcada", ventana)
    casilla.setChecked(True)
    for i, w in enumerate((combo, numero, decimal, inhabilitado, casilla)):
        w.move(10, 10 + i * 40)
    ventana.resize(240, 240)
    qtbot.addWidget(ventana)
    return ventana, combo, numero, casilla


@pytest.mark.parametrize("modo", [ModoTema.CLARO, ModoTema.OSCURO])
def test_r6_los_widgets_se_renderizan_con_la_hoja_con_iconos(qapp, qtbot, aplicado, modo):
    aplicado.establecer_modo(modo)
    ventana, combo, numero, casilla = _formulario(qtbot)
    ventana.show()
    for widget in (combo, numero, casilla):
        imagen = widget.grab().toImage()
        assert not imagen.isNull()
        assert imagen.width() > 0
        assert imagen.height() > 0
    assert casilla.isChecked()


# --- R7: sin colores literales ------------------------------------------------------


def test_r7_iconos_py_no_tiene_colores_literales():
    fuente = Path(modulo_iconos.__file__).read_text("utf-8")
    assert re.findall(r"#[0-9A-Fa-f]{3,8}\b", fuente) == []
    assert re.findall(r"\b(?:rgba?|hsla?)\s*\(", fuente) == []


# --- R8: Rutas.directorio_cache -----------------------------------------------------


def test_r8_directorio_cache_con_base_inyectada(tmp_path):
    assert Rutas(tmp_path).directorio_cache == tmp_path / "cache"
    assert Rutas(str(tmp_path)).directorio_cache == tmp_path / "cache"


def test_r8_directorio_cache_por_defecto_cuelga_de_la_cache_del_sistema(monkeypatch):
    monkeypatch.undo()  # quita el desvío autouse a tmp_path; la sesión ya aísla XDG_CACHE_HOME
    cache = Rutas().directorio_cache
    # Linux: ~/.cache/ProxLaunch; Windows: %LOCALAPPDATA%\\ProxLaunch\\ProxLaunch\\Cache.
    assert cache == Path(platformdirs.user_cache_dir("ProxLaunch"))
    if os.name == "posix":
        assert cache.parent == Path(os.environ["XDG_CACHE_HOME"])


def test_r8_la_cache_no_pisa_otras_carpetas(tmp_path):
    rutas = Rutas(tmp_path)
    assert rutas.directorio_cache not in (rutas.directorio_config, rutas.directorio_log)


# --- Guardia: ninguna prueba escribe en la caché real -------------------------------


def test_guardia_el_gestor_por_defecto_escribe_en_tmp_path(qapp, tmp_path):
    anterior = qapp.styleSheet()
    try:
        GestorTema(qapp, ModoTema.CLARO).aplicar()
        assert list((tmp_path / "cache" / "tema").glob("*.svg"))
    finally:
        qapp.setStyleSheet(anterior)


def test_guardia_la_cache_efectiva_no_es_la_del_usuario_real():
    real = Path("~/.cache/ProxLaunch").expanduser()
    efectiva = Rutas().directorio_cache
    assert efectiva != real
    assert not efectiva.is_relative_to(real)
