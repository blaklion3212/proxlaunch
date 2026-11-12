"""Fuentes incluidas (RNF-11: no se depende de las del sistema)."""

import logging
from importlib import resources

import pytest

from proxlaunch.interfaz import fuentes


def test_rnf11_las_fuentes_y_sus_licencias_vienen_en_el_paquete():
    carpeta = resources.files("proxlaunch.recursos").joinpath("fuentes")
    for nombre in (
        "OpenSans-Variable.ttf",
        "JetBrainsMono-Variable.ttf",
        "OpenSans-OFL.txt",
        "JetBrainsMono-OFL.txt",
    ):
        assert carpeta.joinpath(nombre).is_file(), nombre


def test_rnf11_cargar_fuentes_registra_las_familias_incluidas(qapp):
    interfaz, mono = fuentes.cargar_fuentes()
    assert "Open Sans" in interfaz
    assert "JetBrains Mono" in mono
    from PySide6.QtGui import QFontDatabase

    familias = set(QFontDatabase.families())
    assert interfaz in familias
    assert mono in familias


def test_rnf11_cargar_fuentes_es_repetible(qapp):
    assert fuentes.cargar_fuentes() == fuentes.cargar_fuentes()


def test_rnf11_si_no_se_puede_leer_la_fuente_usa_el_respaldo_sin_excepciones(
    qapp, monkeypatch, caplog
):
    def sin_recurso(*_args, **_kwargs):
        raise FileNotFoundError("fuente ausente")

    monkeypatch.setattr(fuentes.resources, "files", sin_recurso)
    with caplog.at_level(logging.WARNING, logger="proxlaunch.interfaz.fuentes"):
        resultado = fuentes.cargar_fuentes()
    assert resultado == (fuentes.FAMILIA_INTERFAZ_RESPALDO, fuentes.FAMILIA_MONO_RESPALDO)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_rnf11_si_qt_rechaza_la_fuente_usa_el_respaldo(qapp, monkeypatch):
    class BaseFalsa:
        @staticmethod
        def addApplicationFontFromData(_datos):  # noqa: N802
            return -1

        @staticmethod
        def applicationFontFamilies(_id):  # noqa: N802
            return []

    monkeypatch.setattr(fuentes, "QFontDatabase", BaseFalsa)
    assert fuentes.cargar_fuentes() == (
        fuentes.FAMILIA_INTERFAZ_RESPALDO,
        fuentes.FAMILIA_MONO_RESPALDO,
    )


@pytest.mark.parametrize("familias", [[]], ids=["sin-familias-registradas"])
def test_rnf11_fuente_registrada_sin_familias_usa_el_respaldo(qapp, monkeypatch, familias):
    class BaseFalsa:
        @staticmethod
        def addApplicationFontFromData(_datos):  # noqa: N802
            return 7

        @staticmethod
        def applicationFontFamilies(_id):  # noqa: N802
            return familias

    monkeypatch.setattr(fuentes, "QFontDatabase", BaseFalsa)
    assert fuentes.cargar_fuentes()[0] == fuentes.FAMILIA_INTERFAZ_RESPALDO
