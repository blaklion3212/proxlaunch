"""Fase A (0.6.0): perfiles de máquina (arranque, MTU y límite) y su formato.

Cubre CA-A1.4.1, CA-A2.6.3, CA-A3.6 (perfil), CA-A4.6.3, CA-A5.3.3 a A5.3.5, CA-A6.2.3, RF-A7.2
(CA-A7.2.1 a A7.2.6) y RNF-A4. Los archivos ``*-051-*`` los escribió el código de 0.5.1.
"""

import dataclasses
import json
import random
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.constantes import VERSION_FORMATO
from proxlaunch.nucleo.archivos.envoltura import FORMATO_PERFILES, abrir_envoltura
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo, ErrorArchivo
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, InterfazRed, ModeloRed
from proxlaunch.nucleo.perfiles_maquina.aplicar import (
    aplicar_perfil,
    config_desde_configuracion,
    hardware_igual,
)
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import (
    leer_archivo_perfiles,
    leer_perfiles,
    perfiles_a_bytes,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_fase_a_p2 import SEMILLA, permisos
from .apoyo_lote import inventario, plantilla
from .apoyo_mvp3 import DATOS_MVP3, archivo_perfiles, config_perfil_json, perfil_json

DATOS = Path(__file__).resolve().parent.parent / "datos" / "fase_a_p2"
CLAVES_NO_PERFIL = ("encender", "notas", "etiquetas_usuario", "pool", "proteger", "notas_origen")


def _perfil(config: ConfigPerfil, nombre: str = "P") -> PerfilMaquina:
    return PerfilMaquina("a" * 32, nombre, "", OrigenPerfil.USUARIO, config)


def _config(**cambios) -> ConfigPerfil:
    base = {
        "discos": (DiscoPerfil(32),),
        "redes": (RedPerfil(),),
    }
    base.update(cambios)
    return ConfigPerfil(**base)


def _version(*perfiles: PerfilMaquina) -> int:
    return json.loads(perfiles_a_bytes(perfiles, con_pistas=True, app_version="0.6.0"))[
        "version_formato"
    ]


def _ida_y_vuelta(config: ConfigPerfil) -> ConfigPerfil:
    datos = perfiles_a_bytes([_perfil(config)], con_pistas=True, app_version="0.6.0")
    return leer_perfiles(datos).validos[0].config


def _config_de_formulario(**cambios) -> ConfiguracionVM:
    base = {"vmid": 321, "nombre": "mi-vm", "nodo": "pve1", "etiquetas": ("proxlaunch", "lote-x")}
    base.update(cambios)
    cfg = plantilla(**{k: v for k, v in base.items()})
    return cfg


# --- CA-A1.4.1: arranque sí, encender no ------------------------------------------------------


def test_ca_a1_4_1_el_perfil_guarda_arrancar_con_el_servidor_y_no_encender():
    cfg = _config_de_formulario(arranque_auto=True, encender=True)
    config = config_desde_configuracion(cfg, con_pistas=False)
    assert config.arranque_auto is True
    datos = perfiles_a_bytes([_perfil(config)], con_pistas=False, app_version="0.6.0").decode()
    assert '"arranque_auto": true' in datos
    assert "encender" not in datos


def test_ca_a1_4_1_al_cargar_el_perfil_arranque_queda_marcado_y_encender_en_su_defecto(inv):
    config = _ida_y_vuelta(_config(arranque_auto=True))
    assert config.arranque_auto is True
    # El formulario tenía «Encender al terminar» marcado: aplicar el perfil lo devuelve al defecto
    actual = ConfiguracionVM(vmid=1, nombre="x", nodo="pve1", encender=True)
    cfg = aplicar_perfil(_perfil(config), actual, inv).cfg
    assert cfg.arranque_auto is True
    assert cfg.encender is False


def test_ca_a1_4_1_perfil_sin_arranque_desmarca_la_casilla_al_aplicarlo(inv):
    actual = ConfiguracionVM(vmid=1, nombre="x", nodo="pve1", arranque_auto=True)
    cfg = aplicar_perfil(_perfil(_config()), actual, inv).cfg
    assert cfg.arranque_auto is False


# --- Lo que un perfil NO guarda (A2.6.3, A3.6, A4.6.3, A6.2.3) --------------------------------


def test_ca_a2_6_3_a3_6_a4_6_3_a6_2_3_el_archivo_del_perfil_no_guarda_lo_que_no_le_toca():
    cfg = _config_de_formulario(
        encender=True,
        notas_origen=True,
        notas_usuario=True,
        notas="TEXTO-LIBRE-UNICO",
        etiquetas_usuario=("etiqueta-unica",),
        pool="pool-unico",
        proteger=True,
        arranque_orden=4,
        arranque_espera=9,
    )
    config = config_desde_configuracion(cfg, con_pistas=True)
    datos = perfiles_a_bytes([_perfil(config)], con_pistas=True, app_version="0.6.0").decode()
    for clave in CLAVES_NO_PERFIL:
        assert f'"{clave}"' not in datos
    for valor in ("TEXTO-LIBRE-UNICO", "etiqueta-unica", "pool-unico"):
        assert valor not in datos
    assert "arranque_orden" not in datos and "arranque_espera" not in datos


def test_ca_a2_6_3_aplicar_un_perfil_conserva_las_opciones_del_formulario_que_no_guarda(inv):
    actual = ConfiguracionVM(
        vmid=1,
        nombre="x",
        nodo="pve1",
        notas_origen=True,
        notas_usuario=True,
        notas="mis notas",
        etiquetas_usuario=("web",),
        pool="produccion",
        proteger=True,
        arranque_orden=2,
        arranque_espera=5,
    )
    cfg = aplicar_perfil(_perfil(_config(arranque_auto=True)), actual, inv).cfg
    assert (cfg.notas_origen, cfg.notas_usuario, cfg.notas) == (True, True, "mis notas")
    assert cfg.etiquetas_usuario == ("web",)
    assert (cfg.pool, cfg.proteger) == ("produccion", True)
    assert (cfg.arranque_orden, cfg.arranque_espera) == (2, 5)


@pytest.mark.parametrize("clave", ["proteger", "pool", "notas", "etiquetas_usuario", "encender"])
def test_ca_a6_2_3_un_perfil_manipulado_con_claves_que_no_guarda_se_ignora_con_aviso(clave):
    config = config_perfil_json(**{clave: True if clave in ("proteger", "encender") else "x"})
    r = leer_perfiles(archivo_perfiles([perfil_json(config=config)]))
    assert len(r.validos) == 1
    assert CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS in {a.codigo for a in r.avisos}
    assert not hasattr(r.validos[0].config, clave)


# --- CA-A5.3.3 a A5.3.5: MTU y límite ---------------------------------------------------------


def test_ca_a5_3_3_el_perfil_con_mtu_9000_y_limite_50_se_guarda_y_se_restaura():
    config = _config(redes=(RedPerfil(ModeloRed.VIRTIO, None, "vmbr0", 9000, 50.0),))
    leida = _ida_y_vuelta(config)
    assert leida.redes[0].mtu == 9000
    assert leida.redes[0].limite_mb == 50.0


def test_ca_a5_3_3_aplicado_a_un_formulario_sustituye_lo_de_la_tarjeta(inv):
    config = _config(redes=(RedPerfil(ModeloRed.VIRTIO, None, "vmbr0", 9000, 50.0),))
    actual = ConfiguracionVM(
        vmid=1,
        nombre="x",
        nodo="pve1",
        redes=[InterfazRed("vmbr0", ModeloRed.VIRTIO, 7, 1500, 5.0)],
    )
    cfg = aplicar_perfil(_perfil(config), actual, inv).cfg
    assert (cfg.redes[0].mtu, cfg.redes[0].limite_mb) == (9000, 50.0)


def test_ca_a5_3_3_el_formulario_con_mtu_y_limite_genera_un_perfil_que_los_conserva():
    cfg = _config_de_formulario(redes=[InterfazRed("vmbr0", ModeloRed.VIRTIO, None, 1, 12.5)])
    config = config_desde_configuracion(cfg, con_pistas=False)
    assert (config.redes[0].mtu, config.redes[0].limite_mb) == (1, 12.5)


def test_ca_a5_3_3_mtu_o_limite_cambian_la_huella_de_hardware():
    base = _config_de_formulario()
    con_mtu = dataclasses.replace(base, redes=[InterfazRed("vmbr0", mtu=9000)])
    con_limite = dataclasses.replace(base, redes=[InterfazRed("vmbr0", limite_mb=10.0)])
    assert not hardware_igual(base, con_mtu)
    assert not hardware_igual(base, con_limite)
    assert not hardware_igual(base, dataclasses.replace(base, arranque_auto=True))


@pytest.mark.parametrize("nombre", ["perfiles-051-v1.json", "perfiles-051-v2.json"])
def test_ca_a5_3_4_perfil_de_051_se_carga_con_mtu_heredar_y_sin_limite(nombre):
    r = leer_archivo_perfiles(DATOS / nombre)
    assert r.validos and not r.invalidos
    for p in r.validos:
        assert p.config.arranque_auto is False  # CA-A7.2.1
        assert all(red.mtu is None and red.limite_mb is None for red in p.config.redes)


def test_ca_a5_3_5_perfil_con_mtu_y_modelo_no_virtio_se_marca_invalido():
    red = {"modelo": "e1000", "vlan": None, "mtu": 9000}
    r = leer_perfiles(archivo_perfiles([perfil_json(config=config_perfil_json(redes=[red]))]))
    assert r.validos == ()
    (inv,) = r.invalidos
    reglas = {e.params.get("regla") for e in inv.errores}
    assert "V-A05" in reglas
    assert any("redes[0]" in e.ruta for e in inv.errores)


def test_ca_a5_3_5_el_perfil_invalido_no_impide_importar_los_demas():
    malo = perfil_json("Malo", config=config_perfil_json(redes=[{"modelo": "e1000", "mtu": 9000}]))
    bueno = perfil_json("Bueno")
    r = leer_perfiles(archivo_perfiles([malo, bueno]))
    assert [p.nombre for p in r.validos] == ["Bueno"]
    assert len(r.invalidos) == 1


@pytest.mark.parametrize(
    ("red", "campo"),
    [
        ({"modelo": "virtio", "mtu": 100}, "mtu"),
        ({"modelo": "virtio", "mtu": 70000}, "mtu"),
        ({"modelo": "virtio", "mtu": "9000"}, "mtu"),
        ({"modelo": "virtio", "limite_mb": 0}, "limite_mb"),
        ({"modelo": "virtio", "limite_mb": -3}, "limite_mb"),
        ({"modelo": "virtio", "limite_mb": "50"}, "limite_mb"),
        ({"modelo": "virtio", "limite_mb": True}, "limite_mb"),
    ],
)
def test_ca_a5_3_perfil_con_mtu_o_limite_de_tipo_o_rango_erroneo_es_invalido_con_su_ruta(
    red, campo
):
    r = leer_perfiles(archivo_perfiles([perfil_json(config=config_perfil_json(redes=[red]))]))
    assert r.validos == ()
    assert f"perfiles[0].config.redes[0].{campo}" in [e.ruta for e in r.invalidos[0].errores]


def test_ca_a7_2_perfil_con_arranque_auto_no_booleano_es_invalido():
    config = config_perfil_json(arranque_auto="sí")
    r = leer_perfiles(archivo_perfiles([perfil_json(config=config)]))
    assert r.validos == ()
    assert "perfiles[0].config.arranque_auto" in [e.ruta for e in r.invalidos[0].errores]


# --- RF-A7.2: versión del formato -------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["perfiles-051-v1.json", "perfiles-051-v2.json"])
def test_ca_a7_2_1_perfiles_de_051_v1_y_v2_se_leen_sin_aviso_migrado(nombre):
    """Desviación §0 de la arquitectura: sin aviso ``MIGRADO`` al abrir v1/v2."""
    r = leer_archivo_perfiles(DATOS / nombre)
    assert CodigoAvisoArchivo.MIGRADO not in {a.codigo for a in r.avisos}
    assert r.avisos == ()
    assert all(not p.config.arranque_auto for p in r.validos)


def test_rnf_a4_lo_que_lee_06_del_perfil_de_051_es_lo_que_leia_051():
    esperado = json.loads((DATOS / "perfiles-051-v1.esperado.json").read_text())
    p = leer_archivo_perfiles(DATOS / "perfiles-051-v1.json").validos[0]
    from proxlaunch.nucleo.perfiles_maquina.formato import perfil_a_dict

    leido = perfil_a_dict(
        PerfilMaquina("x", p.nombre, p.descripcion, OrigenPerfil.USUARIO, p.config),
        con_pistas=True,
    )
    assert json.loads(json.dumps(leido, sort_keys=True)) == esperado


def test_rnf_a4_los_perfiles_de_mvp3_siguen_abriendose_con_los_mismos_valores():
    r = leer_archivo_perfiles(DATOS_MVP3 / "perfiles-v1.json")
    assert r.validos and not r.invalidos
    assert r.avisos == ()


@pytest.mark.parametrize("nombre", ["perfiles-051-v1.json", "perfiles-051-v2.json"])
def test_ca_a7_2_2_regrabar_un_perfil_de_051_conserva_la_version_minima(nombre):
    original = json.loads((DATOS / nombre).read_text())
    r = leer_archivo_perfiles(DATOS / nombre)
    perfiles = [
        PerfilMaquina("x", p.nombre, p.descripcion, OrigenPerfil.USUARIO, p.config)
        for p in r.validos
    ]
    regrabado = json.loads(perfiles_a_bytes(perfiles, con_pistas=True, app_version="0.5.1"))
    assert regrabado == original


def test_ca_a7_2_2_perfil_nuevo_sin_nada_de_lo_nuevo_se_escribe_en_v1():
    assert _version(_perfil(_config())) == 1


def test_ca_a7_2_2_perfil_con_origen_de_mvp4_sin_nada_nuevo_se_escribe_en_v2():
    assert _version(_perfil(_config(agente_qemu=True))) == 2


@pytest.mark.parametrize(
    "cambios",
    [
        {"arranque_auto": True},
        {"redes": (RedPerfil(mtu=9000),)},
        {"redes": (RedPerfil(mtu=1),)},
        {"redes": (RedPerfil(limite_mb=50.0),)},
        {"redes": (RedPerfil(), RedPerfil(ModeloRed.E1000, limite_mb=0.5))},
    ],
)
def test_ca_a7_2_3_arranque_mtu_o_limite_obligan_a_v3(cambios):
    assert _version(_perfil(_config(**cambios))) == 3


def test_ca_a7_2_3_un_solo_perfil_con_lo_nuevo_sube_todo_el_archivo_a_v3():
    assert _version(_perfil(_config()), _perfil(_config(arranque_auto=True), "B")) == 3


def test_ca_a7_2_3_las_claves_nuevas_solo_se_escriben_si_difieren_del_defecto():
    datos = json.loads(perfiles_a_bytes([_perfil(_config())], con_pistas=True, app_version="x"))
    cfg = datos["perfiles"][0]["config"]
    assert "arranque_auto" not in cfg
    assert all("mtu" not in r and "limite_mb" not in r for r in cfg["redes"])


def test_ca_a7_2_4_los_perfiles_de_fabrica_no_cambian_respecto_a_051():
    esperado = (DATOS / "perfiles-fabrica-051.json").read_bytes()
    ahora = perfiles_a_bytes(perfiles_fabrica(), con_pistas=True, app_version="0.5.1")
    assert ahora == esperado


def test_ca_a7_2_4_los_perfiles_de_fabrica_tienen_todo_en_su_valor_por_defecto():
    for p in perfiles_fabrica():
        assert p.config.arranque_auto is False
        assert all(r.mtu is None and r.limite_mb is None for r in p.config.redes)


def test_ca_a7_2_5_un_archivo_v3_se_rechaza_en_0_5_1_como_version_futura():
    datos = json.loads(
        perfiles_a_bytes(
            [_perfil(_config(arranque_auto=True))], con_pistas=True, app_version="0.6.0"
        )
    )
    assert datos["version_formato"] == 3 == VERSION_FORMATO
    with pytest.raises(ErrorProxLaunch) as exc:
        abrir_envoltura(datos, FORMATO_PERFILES, version_soportada=2)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA


def test_ca_a7_2_5_una_version_4_se_rechaza_en_0_6():
    datos = json.loads(archivo_perfiles([perfil_json()]))
    datos["version_formato"] = 4
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_perfiles(json.dumps(datos).encode())
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA


def test_ca_a7_2_5_archivo_de_perfiles_que_no_es_objeto_o_con_formato_ajeno_se_rechaza():
    with pytest.raises(ErrorProxLaunch):
        leer_perfiles(b"[]")
    with pytest.raises(ErrorArchivo):
        leer_perfiles(json.dumps({"formato": FORMATO_PERFILES, "version_formato": 3}).encode())


# --- CA-A7.2.6: opciones que el servidor no admite --------------------------------------------


def _inv_con_permisos(privs):
    inv = inventario()
    cat = CatalogoServidor(permisos=permisos(*privs, ruta="/"))
    return dataclasses.replace(inv, catalogo=cat)


def test_ca_a7_2_6_perfil_con_arranque_y_servidor_sin_config_options_se_bloquea_al_comprobar():
    inv = _inv_con_permisos(["VM.Allocate", "VM.Config.Network", "VM.Audit"])
    actual = ConfiguracionVM(vmid=100, nombre="vm", nodo="pve1", **_hw())
    cfg = aplicar_perfil(_perfil(_config(arranque_auto=True)), actual, inv).cfg
    problemas = validar_vm(cfg, inv, capacidades_para(inv.version, None))
    v_a12 = [p for p in problemas if p.codigo == "V-A12"]
    assert v_a12 and all(p.severidad == Severidad.ERROR for p in v_a12)
    assert v_a12[0].params["privilegio"] == "VM.Config.Options"


def test_ca_a7_2_6_perfil_con_mtu_y_servidor_sin_config_network_se_bloquea():
    inv = _inv_con_permisos(["VM.Allocate", "VM.Config.Options", "VM.Audit"])
    actual = ConfiguracionVM(vmid=100, nombre="vm", nodo="pve1", **_hw())
    config = _config(redes=(RedPerfil(ModeloRed.VIRTIO, None, "vmbr0", 9000, None),))
    cfg = aplicar_perfil(_perfil(config), actual, inv).cfg
    problemas = validar_vm(cfg, inv, capacidades_para(inv.version, None))
    assert any(
        p.codigo == "V-A12" and p.params.get("privilegio") == "VM.Config.Network" for p in problemas
    )


def test_ca_a7_2_6_con_permisos_desconocidos_no_se_bloquea():
    """RF-A0.3.2: permisos ``None`` = desconocido = se intenta."""
    inv = dataclasses.replace(inventario(), catalogo=CatalogoServidor(permisos=None))
    actual = ConfiguracionVM(vmid=100, nombre="vm", nodo="pve1", **_hw())
    cfg = aplicar_perfil(_perfil(_config(arranque_auto=True)), actual, inv).cfg
    problemas = validar_vm(cfg, inv, capacidades_para(inv.version, None))
    assert not [p for p in problemas if p.codigo == "V-A12"]


def _hw():
    from proxlaunch.nucleo.modelos.vm import Disco

    return {"discos": [Disco("datos", 32)], "redes": [InterfazRed("vmbr0")]}


# --- Ida y vuelta (propiedad) -----------------------------------------------------------------


def test_ca_a7_2_ida_y_vuelta_de_configuraciones_de_perfil_aleatorias():
    rng = random.Random(SEMILLA + 3)
    for _ in range(150):
        redes = tuple(
            RedPerfil(
                modelo := rng.choice([ModeloRed.VIRTIO, ModeloRed.E1000]),
                rng.choice([None, 10]),
                rng.choice([None, "vmbr0"]),
                rng.choice([None, 1, 576, 9000, 65520]) if modelo == ModeloRed.VIRTIO else None,
                rng.choice([None, 0.5, 50.0, 1000.0]),
            )
            for _ in range(rng.randint(1, 3))
        )
        config = _config(arranque_auto=rng.random() < 0.5, redes=redes)
        leida = _ida_y_vuelta(config)
        assert leida.arranque_auto == config.arranque_auto
        assert leida.redes == config.redes
