"""Correcciones de revisión de los iconos del tema (C1, C9, C11, C12 y regresión visual M4).

Se derivan de los requisitos: los iconos son decorativos y nunca impiden aplicar el tema; los
temporales no se acumulan; las rutas que romperían ``url("...")`` se rechazan; la casilla marcada
y deshabilitada tiene su propia palomita; y los iconos se dibujan de verdad en los widgets.
"""

from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QCheckBox, QComboBox, QSpinBox, QStyle, QStyleOptionButton, QWidget

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

TEMAS = {"oscuro": TOKENS_OSCURO, "claro": TOKENS_CLARO}
TOTAL_ICONOS = 6
# Cuerpo de la regla (el bloque termina en una «}» al inicio de línea; los marcadores usan «}}»).
_REGLA_CHECKED_DISABLED = r"QCheckBox::indicator:checked:disabled\s*\{\n(.*?)\n\}"


class _Avisos(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.mensajes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensajes.append(record.getMessage())


@pytest.fixture
def avisos() -> Iterator[_Avisos]:
    """Recoge los avisos del módulo de iconos sin depender de la propagación al logger raíz."""
    manejador = _Avisos()
    logger = logging.getLogger(modulo_iconos.__name__)
    logger.addHandler(manejador)
    yield manejador
    logger.removeHandler(manejador)


@pytest.fixture
def hoja(qapp):
    """Restaura la hoja de estilos de la aplicación al terminar la prueba."""
    anterior = qapp.styleSheet()
    yield qapp
    qapp.setStyleSheet(anterior)


# --- C1: archivos corruptos y excepciones inesperadas -----------------------------------


def test_c1_svg_con_bytes_no_utf8_se_repara(tmp_path):
    carpeta = tmp_path / "t"
    rutas = generar_iconos(TOKENS_CLARO, carpeta)
    objetivo = Path(rutas["icono_palomita"])
    objetivo.write_bytes(b"\xff\xfe\x80\x81\xc3\x28")  # no es UTF-8 válido
    reparadas = generar_iconos(TOKENS_CLARO, carpeta)
    assert len(reparadas) == TOTAL_ICONOS
    assert ET.parse(objetivo).getroot().tag.endswith("svg")


def test_c1_todos_los_svg_no_utf8_se_reparan(tmp_path):
    carpeta = tmp_path / "t"
    generar_iconos(TOKENS_OSCURO, carpeta)
    for archivo in carpeta.glob("*.svg"):
        archivo.write_bytes(b"\xff\xfe\x00\x80")
    rutas = generar_iconos(TOKENS_OSCURO, carpeta)
    assert len(rutas) == TOTAL_ICONOS
    for ruta in rutas.values():
        ET.parse(ruta)


@pytest.mark.parametrize("modo", [ModoTema.CLARO, ModoTema.OSCURO])
def test_c1_aplicar_con_svg_no_utf8_en_cache_no_lanza(hoja, tmp_path, modo):
    carpeta = tmp_path / "iconos"
    gestor = GestorTema(hoja, modo, directorio_iconos=carpeta)
    gestor.aplicar()
    for archivo in carpeta.glob("*.svg"):
        archivo.write_bytes(b"\x89PNG\xff\xfe\x80")
    gestor.aplicar()  # no debe lanzar
    # Se repara (iconos activos) o se degrada sin iconos: en ambos casos la hoja es coherente.
    texto = hoja.styleSheet()
    assert texto
    assert "{{" not in texto
    assert ("url(" in texto) == gestor.iconos_activos


def test_c1_cualquier_excepcion_en_generar_iconos_da_vacio_y_avisa(tmp_path, monkeypatch, avisos):
    def explota(*_a, **_k):
        raise RuntimeError("fallo-inesperado-iconos")

    monkeypatch.setattr(modulo_iconos, "_svg", explota)
    assert generar_iconos(TOKENS_CLARO, tmp_path / "t") == {}
    assert any("fallo-inesperado-iconos" in m for m in avisos.mensajes)


def test_c1_token_de_color_ausente_da_vacio_sin_lanzar(tmp_path, avisos):
    tokens = {k: v for k, v in TOKENS_CLARO.items() if k != "acento_texto"}
    assert generar_iconos(tokens, tmp_path / "t") == {}
    assert avisos.mensajes


def test_c1_un_directorio_en_lugar_del_svg_da_vacio_sin_lanzar(tmp_path, avisos):
    carpeta = tmp_path / "t"
    rutas = generar_iconos(TOKENS_CLARO, carpeta)
    objetivo = Path(rutas["icono_flecha_abajo"])
    objetivo.unlink()
    objetivo.mkdir()
    assert generar_iconos(TOKENS_CLARO, carpeta) == {}
    assert avisos.mensajes


@pytest.mark.parametrize("modo", [ModoTema.CLARO, ModoTema.OSCURO])
def test_c1_aplicar_con_excepcion_en_generar_iconos_instala_hoja_sin_url(
    hoja, tmp_path, monkeypatch, modo
):
    def explota(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(modulo_iconos, "_escribir", explota)
    gestor = GestorTema(hoja, modo, directorio_iconos=tmp_path / "iconos")
    gestor.aplicar()  # no debe lanzar
    texto = hoja.styleSheet()
    assert texto
    assert "url(" not in texto
    assert "{{" not in texto
    assert "image:" not in texto
    assert gestor.iconos_activos is False
    assert gestor.tema_actual == modo.value


def test_c1_iconos_activos_se_recupera_al_volver_a_aplicar(hoja, tmp_path, monkeypatch):
    gestor = GestorTema(hoja, ModoTema.CLARO, directorio_iconos=tmp_path / "iconos")
    with monkeypatch.context() as m:
        m.setattr(modulo_iconos, "_escribir", lambda *_a, **_k: (_ for _ in ()).throw(OSError("x")))
        gestor.aplicar()
        assert gestor.iconos_activos is False
    gestor.aplicar()
    assert gestor.iconos_activos is True
    assert "url(" in hoja.styleSheet()


# --- C9: temporal único ------------------------------------------------------------------


def test_c9_no_quedan_temporales_tras_generar(tmp_path):
    carpeta = tmp_path / "t"
    generar_iconos(TOKENS_OSCURO, carpeta)
    generar_iconos(TOKENS_OSCURO, carpeta)  # segunda pasada: nada que reescribir
    assert list(carpeta.glob("*.tmp")) == []
    assert list(carpeta.glob("*.svg"))


def test_c9_no_quedan_temporales_si_el_reemplazo_falla(tmp_path, monkeypatch):
    def falla(*_a, **_k):
        raise OSError("sin permiso")

    monkeypatch.setattr(modulo_iconos.os, "replace", falla)
    carpeta = tmp_path / "t"
    assert generar_iconos(TOKENS_CLARO, carpeta) == {}
    assert list(carpeta.glob("*.tmp")) == []


def test_c9_los_temporales_tienen_nombres_distintos_entre_escrituras(tmp_path, monkeypatch):
    vistos: list[str] = []
    real = os.replace

    def espia(origen, destino):
        vistos.append(Path(origen).name)
        return real(origen, destino)

    monkeypatch.setattr(modulo_iconos.os, "replace", espia)
    generar_iconos(TOKENS_CLARO, tmp_path / "t")
    assert len(vistos) == TOTAL_ICONOS
    assert len(set(vistos)) == TOTAL_ICONOS  # un nombre único por escritura, no «icono.svg.tmp»


def test_c9_si_el_reemplazo_falla_pero_el_destino_ya_es_correcto_no_es_error(tmp_path, monkeypatch):
    """En Windows otra instancia puede tener el archivo abierto con el mismo contenido."""
    real = os.replace

    def otra_instancia_gano(origen, destino):
        real(origen, destino)  # el destino queda con el contenido correcto...
        raise PermissionError("el archivo está en uso")  # ...pero el reemplazo informa fallo

    monkeypatch.setattr(modulo_iconos.os, "replace", otra_instancia_gano)
    carpeta = tmp_path / "t"
    rutas = generar_iconos(TOKENS_CLARO, carpeta)
    assert len(rutas) == TOTAL_ICONOS
    assert list(carpeta.glob("*.tmp")) == []
    for ruta in rutas.values():
        ET.parse(ruta)


def test_c9_si_el_reemplazo_falla_y_el_destino_difiere_es_error(tmp_path, monkeypatch, avisos):
    carpeta = tmp_path / "t"
    rutas = generar_iconos(TOKENS_CLARO, carpeta)
    Path(rutas["icono_palomita"]).write_text("viejo", "utf-8")

    def falla(*_a, **_k):
        raise PermissionError("en uso")

    monkeypatch.setattr(modulo_iconos.os, "replace", falla)
    assert generar_iconos(TOKENS_CLARO, carpeta) == {}
    assert avisos.mensajes


# --- C11: rutas que romperían url("...") -------------------------------------------------


@pytest.mark.parametrize("nombre", ['a"b', "a\\b", "a\nb", "a\x7fb"])
def test_c11_ruta_con_caracteres_prohibidos_da_vacio_y_avisa(tmp_path, avisos, nombre):
    carpeta = tmp_path / nombre
    assert generar_iconos(TOKENS_CLARO, carpeta) == {}
    assert avisos.mensajes
    assert not carpeta.exists()  # se rechaza antes de crear nada


@pytest.mark.parametrize("nombre", ['a"b', "a\\b"])
def test_c11_aplicar_con_ruta_prohibida_instala_hoja_sin_url(hoja, tmp_path, nombre):
    gestor = GestorTema(hoja, ModoTema.CLARO, directorio_iconos=tmp_path / nombre)
    gestor.aplicar()
    texto = hoja.styleSheet()
    assert texto
    assert "url(" not in texto
    assert "{{" not in texto
    assert gestor.iconos_activos is False


def test_c11_una_ruta_normal_con_espacios_y_comillas_simples_si_se_admite(tmp_path):
    carpeta = tmp_path / "Mi carpeta d'prueba"
    assert len(generar_iconos(TOKENS_CLARO, carpeta)) == TOTAL_ICONOS


# --- C12: casilla marcada y deshabilitada -----------------------------------------------


def test_c12_la_plantilla_tiene_la_regla_checked_disabled_con_su_palomita():
    plantilla = leer_plantilla()
    bloque = re.search(_REGLA_CHECKED_DISABLED, plantilla, flags=re.DOTALL)
    assert bloque is not None
    assert 'image: url("{{icono_palomita_deshabilitada}}");' in bloque.group(1)


@pytest.mark.parametrize("tema", TEMAS)
def test_c12_la_hoja_usa_la_palomita_deshabilitada_con_el_color_deshabilitado(hoja, tmp_path, tema):
    modo = ModoTema.OSCURO if tema == "oscuro" else ModoTema.CLARO
    GestorTema(hoja, modo, directorio_iconos=tmp_path / "i").aplicar()
    texto = hoja.styleSheet()
    bloque = re.search(_REGLA_CHECKED_DISABLED, texto, flags=re.DOTALL)
    assert bloque is not None
    ruta = re.search(r'url\("([^"]+)"\)', bloque.group(1))
    assert ruta is not None
    assert "palomita" in Path(ruta.group(1)).name
    assert (
        Path(ruta.group(1)).name
        != Path(generar_iconos(TEMAS[tema], tmp_path / "i")["icono_palomita"]).name
    )
    color = TEMAS[tema]["texto_deshabilitado"].lstrip("#").lower()
    assert color in Path(ruta.group(1)).name
    assert ET.parse(ruta.group(1)).getroot().find(".//{*}path").get("stroke", "").lower() == (
        TEMAS[tema]["texto_deshabilitado"].lower()
    )


def test_c12_sin_iconos_la_regla_pierde_la_imagen_pero_conserva_el_fondo():
    sin = quitar_iconos(leer_plantilla())
    bloque = re.search(_REGLA_CHECKED_DISABLED, sin, flags=re.DOTALL)
    assert bloque is not None
    assert "image" not in bloque.group(1)
    assert "background-color" in bloque.group(1)


# --- M4: regresión visual por píxeles ---------------------------------------------------
#
# Umbrales (medidos a escala 1 en offscreen; ver informe): se cuentan píxeles cuya distancia
# Manhattan RGB al color esperado es <= TOLERANCIA (admite el suavizado de bordes del SVG).
# Mediciones con la hoja con iconos: combo ~14, spin ~6-12, palomita ~23; sin iconos: 0 en las
# tres zonas. Los mínimos exigidos son aprox. la mitad de lo medido para absorber diferencias de
# versión de Qt/fuentes sin perder poder de detección (sin iconos hay 0, así que el margen entre
# «hay icono» y «no hay icono» es amplio). Las zonas se acotan a la parte derecha (combo/spin) o
# al rectángulo del indicador (casilla) para que el texto no cuente.

TOLERANCIA = 120
MINIMO_COMBO = 6
MINIMO_SPIN = 3
MINIMO_PALOMITA = 10


def _contar(imagen: QImage, color: str, x0: int, y0: int, x1: int, y1: int) -> int:
    objetivo = QColor(color)
    cuenta = 0
    for y in range(max(0, y0), min(imagen.height(), y1)):
        for x in range(max(0, x0), min(imagen.width(), x1)):
            p = imagen.pixelColor(x, y)
            distancia = (
                abs(p.red() - objetivo.red())
                + abs(p.green() - objetivo.green())
                + abs(p.blue() - objetivo.blue())
            )
            if distancia <= TOLERANCIA:
                cuenta += 1
    return cuenta


def _medir(qapp, qtbot, tokens: dict[str, str]) -> dict[str, int]:
    ventana = QWidget()
    combo = QComboBox(ventana)
    combo.addItems(["uno", "dos"])
    spin = QSpinBox(ventana)
    casilla = QCheckBox("marcada", ventana)
    casilla.setChecked(True)
    for i, w in enumerate((combo, spin, casilla)):
        w.move(10, 10 + i * 50)
    ventana.resize(260, 200)
    qtbot.addWidget(ventana)
    ventana.show()
    qapp.processEvents()
    img_combo = combo.grab().toImage()
    img_spin = spin.grab().toImage()
    img_casilla = casilla.grab().toImage()
    opcion = QStyleOptionButton()
    casilla.initStyleOption(opcion)
    ind = casilla.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opcion, casilla)
    flecha = tokens["texto_secundario"]
    return {
        "combo": _contar(
            img_combo, flecha, img_combo.width() - 22, 0, img_combo.width(), img_combo.height()
        ),
        "spin": _contar(
            img_spin, flecha, img_spin.width() - 20, 0, img_spin.width(), img_spin.height()
        ),
        "palomita": _contar(
            img_casilla, tokens["acento_texto"], ind.left(), ind.top(), ind.right(), ind.bottom()
        ),
    }


@pytest.mark.parametrize("tema", TEMAS)
def test_m4_las_flechas_y_la_palomita_se_dibujan_y_desaparecen_sin_iconos(
    qapp, qtbot, hoja, tmp_path, tema
):
    tokens = TEMAS[tema]
    modo = ModoTema.OSCURO if tema == "oscuro" else ModoTema.CLARO
    gestor = GestorTema(qapp, modo, directorio_iconos=tmp_path / "iconos")
    gestor.aplicar()
    assert gestor.iconos_activos
    con = _medir(qapp, qtbot, tokens)

    qapp.setStyleSheet(generar_qss(quitar_iconos(leer_plantilla()), tokens))
    sin = _medir(qapp, qtbot, tokens)

    assert con["combo"] >= MINIMO_COMBO, (con, sin)
    assert con["spin"] >= MINIMO_SPIN, (con, sin)
    assert con["palomita"] >= MINIMO_PALOMITA, (con, sin)
    for zona in con:
        assert sin[zona] < con[zona], (zona, con, sin)
        assert sin[zona] <= 1, (zona, con, sin)  # sin imagen no hay trazo del color del icono
