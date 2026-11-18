"""Prueba de humo e iconos del tema (C2): sin escribir en la caché del usuario y con informe.

Estas pruebas DESACTIVAN el desvío autouse de ``directorio_cache`` del conftest para comprobar
que el humo, por sí mismo, nunca toca la caché real (aislada por la sesión de pruebas).
"""

from __future__ import annotations

import os
from pathlib import Path

import platformdirs
import pytest

from proxlaunch.interfaz.tema import gestor_tema
from proxlaunch.interfaz.tema.gestor_tema import GestorTema
from proxlaunch.nucleo.persistencia.rutas import Rutas

# Fixtures y utilidades de la prueba de humo en proceso (se reutilizan tal cual).
from . import test_mvp5_humo as base

# ``entorno_humo`` requiere ``llavero``: se expone aquí para que pytest lo resuelva en este módulo.
llavero = base.llavero
ejecutar = base.ejecutar
informe_de = base.informe_de
entorno_del_humo = base.entorno_humo
catalogo_del_humo = base.catalogo_qm

# Propiedad original, capturada al importar el módulo (antes de que actúe el autouse).
_CACHE_ORIGINAL = Rutas.__dict__["directorio_cache"]
PROBLEMA = "No se generaron los iconos del tema"


@pytest.fixture
def sin_desvio_de_cache(monkeypatch):
    """Deshace el desvío autouse: ``Rutas.directorio_cache`` vuelve a su implementación real."""
    monkeypatch.setattr(Rutas, "directorio_cache", _CACHE_ORIGINAL, raising=True)
    assert "cache" in str(Rutas(Path("/x/y")).directorio_cache)


@pytest.fixture
def espia_gestor(monkeypatch):
    """Registra el directorio de iconos de cada GestorTema y su ``iconos_activos`` tras aplicar."""
    registro: list[dict] = []
    init_real = GestorTema.__init__
    aplicar_real = GestorTema.aplicar

    def init(self, *args, **kwargs):
        init_real(self, *args, **kwargs)
        registro.append({"carpeta": self._directorio_iconos, "activos": None})

    def aplicar(self):
        aplicar_real(self)
        registro[-1]["activos"] = self.iconos_activos

    monkeypatch.setattr(GestorTema, "__init__", init)
    monkeypatch.setattr(GestorTema, "aplicar", aplicar)
    return registro


def _cache_del_usuario() -> Path:
    return Path(platformdirs.user_cache_dir("ProxLaunch"))


def _carpetas_tema_del_usuario() -> list[Path]:
    """Posibles ``ProxLaunch/tema`` fuera de la carpeta temporal del humo."""
    candidatas = [_cache_del_usuario() / "tema", Path("~/.cache/ProxLaunch/tema").expanduser()]
    if "XDG_CACHE_HOME" in os.environ:
        candidatas.append(Path(os.environ["XDG_CACHE_HOME"]) / "ProxLaunch" / "tema")
    return candidatas


def test_c2_el_humo_no_escribe_en_la_cache_del_usuario(
    entorno_del_humo,
    catalogo_del_humo,
    sin_desvio_de_cache,
    espia_gestor,
    capsys,
    tmp_path,
):
    antes = [c.exists() for c in _carpetas_tema_del_usuario()]
    rc, salida, _ = ejecutar(capsys, permitir_sin_llavero=True)
    informe = informe_de(salida)
    assert rc == 0, informe
    assert informe["problemas"] == []

    # La carpeta del tema vive dentro de la carpeta temporal del humo, no en la caché real.
    assert len(espia_gestor) == 1
    carpeta = espia_gestor[0]["carpeta"]
    assert carpeta.name == "tema"
    assert any(carpeta.is_relative_to(c) for c in entorno_del_humo.carpetas)
    assert espia_gestor[0]["activos"] is True

    # Nada apareció en la caché del usuario (aislada por la sesión): ni ProxLaunch/tema ni svg.
    assert [c.exists() for c in _carpetas_tema_del_usuario()] == antes
    assert not any(c.exists() for c in _carpetas_tema_del_usuario())
    assert not (_cache_del_usuario() / "tema").exists()
    cache_real = _cache_del_usuario()
    if cache_real.exists():
        assert list(cache_real.rglob("*.svg")) == []


def test_c2_la_carpeta_temporal_del_humo_se_borra_con_sus_iconos(
    entorno_del_humo,
    catalogo_del_humo,
    sin_desvio_de_cache,
    espia_gestor,
    capsys,
):
    rc, _, _ = ejecutar(capsys, permitir_sin_llavero=True)
    assert rc == 0
    carpeta = espia_gestor[0]["carpeta"]
    assert not carpeta.exists()
    assert all(not c.exists() for c in entorno_del_humo.carpetas)


def test_c2_si_no_se_generan_iconos_el_informe_lo_reporta(
    entorno_del_humo,
    catalogo_del_humo,
    sin_desvio_de_cache,
    espia_gestor,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(gestor_tema, "generar_iconos", lambda tokens, carpeta: {})
    rc, salida, _ = ejecutar(capsys, permitir_sin_llavero=True)
    informe = informe_de(salida)
    assert PROBLEMA in informe["problemas"]
    assert rc == 1
    assert espia_gestor[0]["activos"] is False


def test_c2_con_iconos_el_informe_no_incluye_el_problema(
    entorno_del_humo,
    catalogo_del_humo,
    sin_desvio_de_cache,
    espia_gestor,
    capsys,
):
    rc, salida, _ = ejecutar(capsys, permitir_sin_llavero=True)
    informe = informe_de(salida)
    assert PROBLEMA not in informe["problemas"]
    assert rc == 0
    assert espia_gestor[0]["activos"] is True


def test_c2_gestor_iconos_activos_true_y_false(qapp, tmp_path, monkeypatch):
    anterior = qapp.styleSheet()
    try:
        bueno = GestorTema(qapp, directorio_iconos=tmp_path / "ok")
        assert bueno.iconos_activos is False  # antes de aplicar todavía no hay iconos
        bueno.aplicar()
        assert bueno.iconos_activos is True

        monkeypatch.setattr(gestor_tema, "generar_iconos", lambda tokens, carpeta: {})
        bueno.aplicar()
        assert bueno.iconos_activos is False
        assert "url(" not in qapp.styleSheet()
    finally:
        qapp.setStyleSheet(anterior)
