"""RF-A0.2: con los valores por defecto la petición es idéntica a la de 0.5.1.

Las instantáneas (``tests/datos/fase_a/golden_v051.json``) se generaron con el código de la
etiqueta ``v0.5.1`` (véase ``apoyo_golden_fase_a``) para disco vacío, ISO, importar disco y
clonar. Aquí se reconstruyen los mismos escenarios con el código de 0.6 (``notas_origen=False``,
el valor del dataclass) y se comparan **byte a byte** (mismas claves, mismos valores y mismo
orden). CA-A0.2.1, CA-A0.2.2, CA-A0.2.3 (parte de petición), CA-A0.1.3 (sin parámetros nuevos).
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.modelos.origen import ModoClon
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.opciones.preparacion import preparar_elemento
from proxlaunch.nucleo.origen.clon import (
    construir_ajustes_clon,
    construir_peticion_clon,
    detalle_de_config,
)

from . import apoyo_golden_fase_a as g
from .apoyo_fase_a import ctx_notas
from .apoyo_mvp4 import ClusterM4, cfg_base, cfg_clon, detalle_plantilla, inv_origen

GOLDEN = json.loads(g.RUTA_GOLDEN.read_text(encoding="utf-8"))
ESCENARIOS_ACTUALES = g.escenarios()


def test_las_instantaneas_vienen_de_la_version_0_5_1():
    """Las instantáneas deben haberse generado con el código de la etiqueta v0.5.1."""
    assert GOLDEN["version_codigo"] == "0.5.1"
    assert set(GOLDEN["escenarios"]) == set(ESCENARIOS_ACTUALES)
    assert len(GOLDEN["escenarios"]) >= 14


@pytest.mark.parametrize("nombre", sorted(GOLDEN["escenarios"]))
def test_ca_a0_2_2_peticion_identica_byte_a_byte_a_la_de_0_5_1(nombre: str):
    """CA-A0.2.2 / CA-A0.2.1: notas desmarcadas y resto por defecto = petición de 0.5.1."""
    esperado = GOLDEN["escenarios"][nombre]
    actual = json.loads(json.dumps(ESCENARIOS_ACTUALES[nombre]))
    # json.loads conserva el orden de inserción: se compara también el orden de las claves.
    assert json.dumps(actual, sort_keys=False) == json.dumps(esperado, sort_keys=False)
    # Y ningún parámetro de la fase A aparece con los valores por defecto.
    for clave in ("onboot", "startup", "description", "pool", "protection"):
        assert clave not in actual.get("parametros", {})
        assert clave not in actual.get("ajustes_config", {})


def _escenarios_post() -> list[str]:
    return sorted(n for n in GOLDEN["escenarios"] if "parametros" in GOLDEN["escenarios"][n])


def test_ningun_escenario_de_post_lleva_parametros_de_la_fase_a():
    """CA-A0.1.3 / CA-A0.2.2: con los valores por defecto no sale ninguna clave nueva."""
    nuevas = {"onboot", "startup", "description", "pool", "protection"}
    for nombre in _escenarios_post():
        assert not nuevas & set(ESCENARIOS_ACTUALES[nombre]["parametros"]), nombre


def test_ca_a0_2_1_el_dataclass_por_defecto_no_activa_notas_ni_nada_nuevo():
    """CA-A0.2.2: el valor por defecto del dataclass reproduce 0.5.1 (notas desmarcadas)."""
    cfg = ConfiguracionVM(vmid=1, nombre="x", nodo="pve1")
    assert cfg.notas_origen is False
    assert (cfg.encender, cfg.arranque_auto, cfg.proteger, cfg.pool) == (False, False, False, None)
    assert (cfg.arranque_orden, cfg.arranque_espera, cfg.notas) == (None, None, "")
    assert cfg.etiquetas_usuario == () and cfg.descripcion is None


@pytest.mark.parametrize("nombre", ["vacio_basico", "iso_linux", "importar_basico"])
def test_ca_a0_2_1_con_notas_marcadas_solo_se_anade_description(nombre: str):
    """CA-A0.2.1: con «Añadir notas de origen» (valor del formulario) solo cambia ``description``.

    Se construye el mismo escenario con ``notas_origen=True`` y la descripción calculada por
    ``preparar_elemento``; quitándole ``description`` debe coincidir con la instantánea de 0.5.1.
    """
    construir = {
        "vacio_basico": lambda: cfg_base(),
        "iso_linux": lambda: g.cfg_iso(etiquetas=g.ETIQUETAS_LOTE),
        "importar_basico": lambda: g.cfg_import(),
    }[nombre]
    cfg = dataclasses.replace(construir(), notas_origen=True)
    cfg = preparar_elemento(cfg, ctx_notas(), None, (9, 2))
    actual = construir_parametros(cfg, inv_origen(), (9, 2))
    esperado = GOLDEN["escenarios"][nombre]["parametros"]
    assert "description" in actual
    sin_notas = {k: v for k, v in actual.items() if k != "description"}
    assert list(sin_notas.items()) == list(esperado.items())


def test_ca_a0_2_1_clon_con_notas_marcadas_solo_se_anade_description():
    """CA-A0.2.1 (clonar): el POST de clone gana ``description`` y nada más."""
    esperado = GOLDEN["escenarios"]["clon_enlazado"]["parametros"]
    cfg = cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, notas_origen=True)
    cfg = preparar_elemento(cfg, ctx_notas(), detalle_plantilla(), (9, 2))
    peticion = construir_peticion_clon(cfg, inv_origen())
    assert "description" in peticion.parametros
    resto = {k: v for k, v in peticion.parametros.items() if k != "description"}
    assert list(resto.items()) == list(esperado.items())


def test_ca_a0_2_clon_ajustes_por_defecto_identicos_a_0_5_1():
    """CA-A0.2.2 (clonar): el PUT posterior al clon con valores por defecto es el de 0.5.1."""
    cl = ClusterM4(("pve1",))
    cl.agregar_plantilla(9000, "base", "pve1", tags="plantilla")
    detalle: Any = detalle_de_config(cl.plantillas[9000]["config"])
    cfg = cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, etiquetas=g.ETIQUETAS_LOTE)
    ajustes = construir_ajustes_clon(cfg, detalle, cfg.etiquetas)
    esperado = GOLDEN["escenarios"]["clon_enlazado_etiquetado"]
    assert dict(ajustes.config) == esperado["ajustes_config"]
    assert set(ajustes.config) == {"tags"}


def test_dt_a1_el_formulario_parte_con_notas_marcadas_y_todo_lo_demas_por_defecto():
    """CA-A0.2.1 / R-A3: la única excepción al comportamiento de 0.5.1 es la casilla de notas."""
    from proxlaunch.nucleo.valores_defecto import configuracion_por_defecto

    cfg = configuracion_por_defecto(100, "srv-web-01", "pve1", "local-lvm", "vmbr0")
    assert cfg.notas_origen is True
    resto = (cfg.encender, cfg.arranque_auto, cfg.proteger, cfg.pool, cfg.notas_usuario)
    assert resto == (False, False, False, None, False)
    assert (cfg.arranque_orden, cfg.arranque_espera, cfg.notas) == (None, None, "")
    assert cfg.etiquetas_usuario == () and cfg.redes[0].mtu is None
    assert cfg.redes[0].limite_mb is None
    # Con la casilla desmarcada la petición es la de 0.5.1 (instantánea «vacio_basico»).
    cfg = dataclasses.replace(cfg, notas_origen=False)
    esperado = GOLDEN["escenarios"]["vacio_basico"]["parametros"]
    assert dict(construir_parametros(cfg, inv_origen(), (9, 2))) == esperado


def test_ca_a0_2_3_una_configuracion_de_0_5_1_sin_claves_nuevas_se_lee_con_los_valores_de_0_5_1():
    """CA-A0.2.3: ``a_dict`` de 0.6 con valores por defecto no escribe claves nuevas, y un dict de
    0.5.1 (sin ellas) se lee con los valores por defecto y produce la misma petición."""
    cfg = cfg_base(etiquetas=g.ETIQUETAS_LOTE)
    d = cfg.a_dict()
    nuevas = {
        "encender", "arranque_auto", "arranque_orden", "arranque_espera", "notas_origen",
        "notas_usuario", "notas", "etiquetas_usuario", "pool", "proteger", "descripcion",
    }  # fmt: skip
    assert not nuevas & set(d)
    assert all("mtu" not in r and "limite_mb" not in r for r in d["redes"])
    leida = ConfiguracionVM.desde_dict(d)
    assert leida == cfg
    inv = inv_origen()
    assert construir_parametros(leida, inv, (9, 2)) == construir_parametros(cfg, inv, (9, 2))
