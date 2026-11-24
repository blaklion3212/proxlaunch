"""Conexión y versión en la interfaz de la fase D (RF-D2.1 a RF-D2.3).

Derivadas de docs/requisitos/fase-d.md: CA-D2.2.1 a CA-D2.2.3 (aviso V-D02 una sola vez, no
bloqueante), CA-D2.3.1 y CA-D2.3.2 (el selector de versión solo ofrece 8.4, 9.0, 9.1 y 9.2 y una
versión forzada guardada anterior a 8.4 se descarta con V-D03), CA-D2.1.1 (texto de V-D01) y
CA-D2.4.2 (ningún texto presenta 8.0 a 8.3 como umbral). El lado núcleo de estas reglas lo cubre
``tests/nucleo/test_fase_d_version.py``.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication

from proxlaunch.interfaz.dialogos.conexion import DialogoConexion
from proxlaunch.interfaz.textos import texto_error, texto_problema
from proxlaunch.interfaz.textos_d import (
    texto_aviso_conexion_d,
    texto_version_forzada_descartada,
)
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.capacidades import VERSIONES_CONOCIDAS
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.persistencia.preferencias import Preferencias
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso
from proxlaunch.nucleo.validacion import Problema, Severidad

from . import test_ventana_principal as _base
from .apoyo import perfil, sesion_falsa
from .test_ventana_principal import _textos_avisos, conectar, esperar_validacion

entorno = _base.entorno  # fixture base de la ventana


@pytest.fixture
def lanzador(qtbot):
    lz = Lanzador()
    yield lz
    lz.esperar(2000)


@pytest.fixture
def crear(qtbot, deps, lanzador):
    def _crear(**kw):
        kw.setdefault("avanzado", True)
        d = DialogoConexion(
            deps.servicio_conexion, deps.perfiles, deps.huellas, deps.secretos, lanzador, **kw
        )
        qtbot.addWidget(d)
        d.show()
        return d

    return _crear


@pytest.fixture
def con_version_8_2_guardada(deps):
    """Preferencias en disco con una versión forzada anterior a la mínima (antes de la ventana)."""
    deps.preferencias.guardar(Preferencias(version_forzada=(8, 2)))


# --- CA-D2.3.1: el selector ---------------------------------------------------------------------


def test_ca_d2_3_1_el_selector_lista_detectar_8_4_9_0_9_1_y_9_2_y_nada_de_8_0_a_8_3(crear):
    d = crear()
    textos = [d.combo_version.itemText(i) for i in range(d.combo_version.count())]
    assert textos == ["Detectada", "8.4", "9.0", "9.1", "9.2"]
    datos = [d.combo_version.itemData(i) for i in range(d.combo_version.count())]
    assert datos == [None, (8, 4), (9, 0), (9, 1), (9, 2)]
    assert tuple(datos[1:]) == tuple(VERSIONES_CONOCIDAS)
    for prohibida in ("8.0", "8.1", "8.2", "8.3"):
        assert prohibida not in textos


def test_ca_d2_3_1_una_version_forzada_anterior_no_queda_seleccionada(crear):
    d = crear(version_forzada=(8, 2))
    # Si por cualquier camino llegara una versión sin entrada, el combo no inventa una.
    assert (
        d.combo_version.currentData() in (None, (8, 2)) and d.combo_version.findData((8, 2)) == -1
    )


# --- V-D03: versión forzada guardada ------------------------------------------------------------


def test_v_d03_el_dialogo_muestra_el_aviso_cuando_la_ventana_se_lo_pasa(crear):
    texto = texto_version_forzada_descartada("8.2")
    d = crear(aviso_version=texto)
    assert not d._aviso_version.isHidden()
    assert "8.2" in d._aviso_version.text() and "Detectar" in d._aviso_version.text()


def test_v_d03_sin_aviso_el_dialogo_no_dice_nada_de_versiones(crear):
    d = crear()
    assert d._aviso_version.isHidden() and d._aviso_version.text() == ""


def test_ca_d2_3_2_una_version_forzada_8_2_guardada_se_descarta_y_se_avisa_en_la_conexion(
    qtbot, con_version_8_2_guardada, entorno
):
    v = entorno.ventana
    assert v._prefs.version_forzada is None  # «Detectar»
    assert v._version_descartada == "8.2"
    v._abrir_conexion(None)
    d = v._dialogo_conexion
    assert d is not None
    assert "8.2" in d._aviso_version.text() and not d._aviso_version.isHidden()
    assert (
        d.combo_version.currentData() is None
    )  # modo avanzado o no, el valor elegido es «Detectar»
    d.reject()


def test_ca_d2_3_2_tras_descartar_la_version_la_ventana_guarda_detectar(
    qtbot, deps, con_version_8_2_guardada, entorno
):
    v = entorno.ventana
    deps.preferencias.guardar(v._prefs)
    assert deps.preferencias.cargar().version_forzada is None


def test_v_d03_una_vez_conectado_el_aviso_no_se_repite(qtbot, con_version_8_2_guardada, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno, sesion_falsa())
    esperar_validacion(qtbot, v)
    assert v._version_descartada is None
    v._abrir_conexion(None)
    d = v._dialogo_conexion
    assert d is not None and d._aviso_version.isHidden()
    d.reject()


def test_v_d03_sin_version_guardada_antigua_la_ventana_no_avisa(qtbot, entorno):
    v = entorno.ventana
    assert v._version_descartada is None
    v._abrir_conexion(None)
    assert v._dialogo_conexion._aviso_version.isHidden()
    v._dialogo_conexion.reject()


def test_v_d03_el_texto_nombra_la_version_y_la_alternativa_sin_marcadores():
    t = texto_version_forzada_descartada("8.3")
    assert "8.3" in t and "Detectar" in t and "{" not in t and "un dato" not in t


# --- V-D01: servidor 8.0 a 8.3 --------------------------------------------------------------------


def test_ca_d2_1_1_el_error_de_version_no_soportada_nombra_la_detectada_y_8_4():
    err = ErrorProxLaunch(CodigoError.VERSION_NO_SOPORTADA, {"version": "8.2.4", "minima": "8.4"})
    texto = texto_error(err)
    assert "8.2.4" in texto and "8.4" in texto
    assert "{" not in texto and "un dato" not in texto


def test_ca_d2_1_1_v_d01_como_problema_tiene_el_mismo_texto_llano():
    p = Problema("", "V-D01", Severidad.ERROR, {"version": "8.1.0", "minima": "8.4"})
    t = texto_problema(p)
    assert "8.1.0" in t and "8.4" in t and "Actualiza" in t


# --- V-D02: rama 8 sin soporte --------------------------------------------------------------------


def test_ca_d2_2_4_el_texto_de_v_d02_no_promete_nada_ajeno_y_no_lleva_marcadores():
    t = texto_aviso_conexion_d(Aviso(CodigoAviso.RAMA_8_SIN_SOPORTE, {"version": "8.4.1"}))
    assert t is not None
    assert "rama 8" in t and "{" not in t and "un dato" not in t
    assert "agosto de 2026" in t


def test_los_avisos_de_otras_fases_no_los_toma_la_fase_d():
    assert texto_aviso_conexion_d(Aviso(CodigoAviso.VERSION_NO_PROBADA, {"version": "9.9"})) is None


def test_ca_d2_2_1_el_aviso_v_d02_sale_una_sola_vez_por_conexion_y_no_bloquea(qtbot, entorno):
    v = entorno.ventana
    s = sesion_falsa(
        avisos=[Aviso(CodigoAviso.RAMA_8_SIN_SOPORTE, {"version": "8.4.1"})], version=(8, 4)
    )
    conectar(qtbot, entorno, s)
    esperar_validacion(qtbot, v)
    textos = [t for t in _textos_avisos(v) if "rama 8" in t]
    assert len(textos) == 1
    # No bloquea: sigue pudiéndose crear tras poner un nombre válido (no hay modal ni error).
    assert v.formulario.isEnabled()
    # Revalidar (comprobar, simular…) no la repite.
    for _ in range(3):
        v._revalidar()
    assert len([t for t in _textos_avisos(v) if "rama 8" in t]) == 1


def test_ca_d2_2_2_con_9_2_no_hay_aviso_de_rama_8(qtbot, entorno):
    conectar(qtbot, entorno, sesion_falsa(version=(9, 2)))
    assert not [t for t in _textos_avisos(entorno.ventana) if "rama 8" in t]


def test_ca_d2_2_1_una_nueva_conexion_vuelve_a_avisar_una_vez(qtbot, entorno):
    v = entorno.ventana
    s = sesion_falsa(
        avisos=[Aviso(CodigoAviso.RAMA_8_SIN_SOPORTE, {"version": "8.4"})], version=(8, 4)
    )
    conectar(qtbot, entorno, s)
    s2 = sesion_falsa(
        perfil(id_="p2", nombre="Otro", hosts=("10.0.0.6",)),
        avisos=[Aviso(CodigoAviso.RAMA_8_SIN_SOPORTE, {"version": "8.4"})],
        version=(8, 4),
    )
    conectar(qtbot, entorno, s2)
    assert len([t for t in _textos_avisos(v) if "rama 8" in t]) == 1


# --- CA-D2.4.2: ningún texto presenta 8.0 a 8.3 como umbral ---------------------------------------


def _textos_de_usuario_con_umbral_8_0_a_8_3() -> list[str]:
    """Cadenas de ``interfaz/`` (no docstrings) que presentan 8.0 a 8.3 como umbral de versión."""
    import ast
    import re
    from pathlib import Path

    import proxlaunch

    raiz = Path(proxlaunch.__file__).parent / "interfaz"
    encontrados: list[str] = []
    for ruta in sorted(raiz.rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        docstrings = {
            id(n.body[0].value)
            for n in ast.walk(arbol)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
            and n.body
            and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)
        }
        for n in ast.walk(arbol):
            if (
                isinstance(n, ast.Constant)
                and isinstance(n.value, str)
                and id(n) not in docstrings
                and re.search(r"(?<![\d.])8\.[0-3](?!\d)", n.value)
                and "ya no se admit" not in n.value  # V-D01 y V-D03 las nombran a propósito
            ):
                encontrados.append(f"{ruta.name}:{n.lineno}: {n.value[:70]}")
    return encontrados


def test_ca_d2_4_2_ningun_texto_de_interfaz_presenta_8_0_a_8_3_como_umbral():
    assert _textos_de_usuario_con_umbral_8_0_a_8_3() == []


def test_el_codigo_de_idioma_de_los_textos_nuevos_es_la_cadena_de_origen_sin_traductor():
    assert QCoreApplication.translate("TextosD", "Migrado") == "Migrado"
