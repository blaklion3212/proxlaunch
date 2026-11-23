"""Fase C (0.8.0): los perfiles de máquina siguen guardando solo hardware (RF-C6.2).

Cubre CA-C6.2.1 (guardar un perfil desde un formulario con todo lo de C rellenado da el mismo
archivo que 0.7.0), CA-C6.2.2 (aplicar un perfil no toca los campos de C), CA-C6.4.1 (los perfiles
de 0.5.1 y 0.6.0 se abren y se regraban iguales) y la decisión S-C8 (firewall y red del clon son
datos de despliegue, no de perfil).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo
from proxlaunch.nucleo.firewall.modelos import FirewallMV, Politica
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.perfiles_maquina.aplicar import aplicar_config, config_desde_configuracion
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import (
    leer_archivo_perfiles,
    leer_perfiles,
    perfiles_a_bytes,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil, OrigenPerfil, PerfilMaquina
from proxlaunch.nucleo.red.modelos import AccionTarjeta, CampoRed, ModoRedClon, RedClon, TarjetaClon

from .apoyo_lote import plantilla

DATOS_B = Path(__file__).resolve().parent.parent / "datos" / "fase_b"
DATOS_A = Path(__file__).resolve().parent.parent / "datos" / "fase_a_p2"

FW = FirewallMV(activo=True, grupo="web-01", politica_entrada=Politica.PERMITIR)
RED = RedClon(
    ModoRedClon.PERSONALIZAR,
    (
        TarjetaClon(
            0, AccionTarjeta.CAMBIAR, bridge="prod", vlan=20, fijados=frozenset({CampoRed.BRIDGE})
        ),
    ),
)


def archivo(config: ConfigPerfil) -> bytes:
    perfil = PerfilMaquina("x", "P", "d", OrigenPerfil.USUARIO, config)
    return perfiles_a_bytes([perfil], con_pistas=True, app_version="0.7.0")


def test_ca_c6_2_1_un_perfil_no_tiene_ningun_campo_de_la_fase_c():
    campos = {f.name for f in dataclasses.fields(ConfigPerfil)}
    assert not {c for c in campos if "firewall" in c or "red_clon" in c or "grupo" in c}


def test_ca_c6_2_1_guardar_un_perfil_con_todo_lo_de_c_rellenado_da_el_archivo_de_070():
    hardware = plantilla(memoria_mib=4096, cores=4, arranque_auto=True)
    con_c = dataclasses.replace(hardware, firewall=FW, red_clon=RED)
    a = config_desde_configuracion(con_c, con_pistas=True)
    b = config_desde_configuracion(hardware, con_pistas=True)
    assert a == b
    assert archivo(a) == archivo(b)
    cuerpo = json.loads(archivo(a))
    assert cuerpo["version_formato"] <= 3  # nunca v5
    texto = archivo(a).decode()
    for clave in ("firewall", "red_clon", "web-01", "politica", "cortafuegos"):
        assert clave not in texto


def test_ca_c6_2_1_los_perfiles_de_fabrica_no_mencionan_el_firewall_ni_la_red_del_clon():
    datos = perfiles_a_bytes(list(perfiles_fabrica()), con_pistas=True, app_version="0.8.0")
    assert b"firewall" not in datos and b"red_clon" not in datos
    assert json.loads(datos)["version_formato"] <= 3


@pytest.mark.parametrize("origen", [OrigenSO.CLONAR_PLANTILLA, OrigenSO.DISCO_VACIO, OrigenSO.ISO])
def test_ca_c6_2_2_aplicar_un_perfil_conserva_el_firewall_y_la_red_del_formulario(origen):
    formulario = plantilla(firewall=FW, red_clon=RED)
    perfil = ConfigPerfil(memoria_mib=8192, cores=8, origen=origen)
    cfg = aplicar_config(perfil, formulario, None).cfg
    assert cfg.memoria_mib == 8192  # el hardware sí se aplicó
    assert cfg.firewall == FW
    assert cfg.red_clon == RED


def test_ca_c6_2_2_aplicar_un_perfil_a_un_formulario_sin_c_nunca_inventa_campos_de_c():
    cfg = aplicar_config(ConfigPerfil(memoria_mib=8192, cores=8), plantilla(), None).cfg
    assert cfg.firewall is None and cfg.red_clon is None


def test_ca_c6_2_2_aplicar_un_perfil_con_red_de_hardware_no_toca_la_red_del_clon():
    """La red del perfil (tarjeta 1 del hardware) y ``red_clon`` son cosas distintas."""
    from proxlaunch.nucleo.modelos.vm import ModeloRed
    from proxlaunch.nucleo.perfiles_maquina.modelos import RedPerfil

    perfil = ConfigPerfil(redes=(RedPerfil(ModeloRed.E1000, 30, "vmbr9"),))
    formulario = plantilla(red_clon=RED, firewall=FW)
    cfg = aplicar_config(perfil, formulario, None).cfg
    assert cfg.red_clon == RED and cfg.firewall == FW


def _con_claves_c(config_extra: dict) -> bytes:
    cuerpo = json.loads((DATOS_B / "p2_perfiles-060-v3.json").read_text())
    cuerpo["perfiles"][0]["config"].update(config_extra)
    return json.dumps(cuerpo).encode()


def test_ca_c6_2_1_un_perfil_con_claves_de_c_manipuladas_las_ignora_y_avisa():
    leido = leer_perfiles(
        _con_claves_c({"firewall": {"activo": True, "grupo": "web"}, "red_clon": {"modo": "x"}})
    )
    assert len(leido.validos) == 1 and not leido.invalidos
    assert "firewall" not in repr(leido.validos[0].config)
    (aviso,) = [a for a in leido.avisos if a.codigo == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS]
    assert aviso.params == {"n": "2"}
    regrabado = archivo(leido.validos[0].config).decode()
    assert "firewall" not in regrabado and "red_clon" not in regrabado


@pytest.mark.parametrize(
    "ruta",
    [
        DATOS_A / "perfiles-051-v1.json",
        DATOS_A / "perfiles-051-v2.json",
        DATOS_A / "perfiles-fabrica-051.json",
    ],
    ids=lambda r: r.name,
)
def test_ca_c6_4_1_los_perfiles_de_051_se_abren_y_se_regraban_iguales_con_080(ruta):
    original = json.loads(ruta.read_text())
    leidos = leer_archivo_perfiles(ruta)
    assert leidos.validos and not leidos.invalidos and leidos.avisos == ()
    perfiles = [
        PerfilMaquina(f"p{i}", v.nombre, v.descripcion, OrigenPerfil.USUARIO, v.config)
        for i, v in enumerate(leidos.validos)
    ]
    nuevo = json.loads(
        perfiles_a_bytes(perfiles, con_pistas=True, app_version=original["app_version"])
    )
    assert nuevo == original


def test_ca_c6_4_1_el_perfil_de_060_se_lee_igual_y_se_regraba_en_v3():
    ruta = DATOS_B / "p2_perfiles-060-v3.json"
    original = json.loads(ruta.read_text())
    leido = leer_archivo_perfiles(ruta)
    assert leido.validos and not leido.invalidos and leido.avisos == ()
    perfil = leido.validos[0]
    como = PerfilMaquina(
        "x", perfil.nombre, perfil.descripcion, OrigenPerfil.USUARIO, perfil.config
    )
    nuevo = json.loads(perfiles_a_bytes([como], con_pistas=True, app_version="0.6.0"))
    assert nuevo == original and nuevo["version_formato"] == 3
