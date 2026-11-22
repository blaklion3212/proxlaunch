"""Fase B (0.7.0): formato v4 de lotes guardados, perfiles y compatibilidad (RF-B6.1, B6.2, B6.4).

Cubre CA-B6.1.1 a CA-B6.1.11, CA-B6.2.1, CA-B6.2.2, CA-B6.4.1, CA-B4.6.3, CA-B0.8.2 y CA-B0.8.3
(en archivos), CL-B24 y la propiedad de ida y vuelta con generación aleatoria (semilla fija: el
repositorio no usa ``hypothesis``).

Desviaciones aceptadas de la arquitectura (§0 y §12): la migración 3 -> 4 es la identidad y NO
avisa ``MIGRADO`` (CA-B6.1.1 lo pedía; el orquestador decidió que los lotes de 0.6.0 se abran sin
ruido), y los perfiles nunca se escriben en v4. Los archivos ``p2_*-060-*.json`` de
``tests/datos/fase_b`` los escribió el código de 0.6.0 (``p2_generar_datos.py``).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import random
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.constantes import (
    MAX_BYTES_LOTE,
    VERSION_FORMATO,
    VERSION_FORMATO_FASE_A,
)
from proxlaunch.nucleo.archivos.envoltura import FORMATO_LOTE, abrir_envoltura
from proxlaunch.nucleo.archivos.esquema import (
    CodigoAvisoArchivo,
    ErrorArchivo,
    MotivoCampo,
    es_clave_credencial,
)
from proxlaunch.nucleo.cloudinit.claves import analizar_claves
from proxlaunch.nucleo.cloudinit.modelos import (
    NINGUNO,
    CloudInitParcial,
    ConfigCloudInit,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, FilaLote, PatronNombres
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.lotes_guardados.formato import (
    guardar_lote,
    leer_archivo_lote,
    leer_lote,
    lote_a_bytes,
    lote_a_dict,
    version_para,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.catalogo import ListadoSnippets, Snippet
from proxlaunch.nucleo.modelos.inventario import Storage
from proxlaunch.nucleo.modelos.vm import PLAZO_IP_DEFECTO_S, OrigenSO
from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales
from proxlaunch.nucleo.perfiles_maquina.aplicar import aplicar_config, config_desde_configuracion
from proxlaunch.nucleo.perfiles_maquina.formato import (
    leer_archivo_perfiles,
    leer_perfiles,
    perfil_a_dict,
    perfiles_a_bytes,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil, OrigenPerfil, PerfilMaquina
from proxlaunch.nucleo.secreto import Secreto

from .apoyo_lote import definicion, plantilla
from .apoyo_mvp3 import DATOS_MVP3
from .apoyo_mvp4 import cfg_clon, inv_origen, plantilla_pve

DATOS_B = Path(__file__).resolve().parent.parent / "datos" / "fase_b"
DATOS_A = Path(__file__).resolve().parent.parent / "datos" / "fase_a_p2"
CENTINELA = "S3cr3t-Prueba!"
SEMILLA = 20261122
FIJA, DHCP, SIN = ModoTarjeta.FIJA, ModoTarjeta.DHCP, ModoTarjeta.SIN_CONFIGURAR
CLAVE = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAAAAAAAA= ana@pc"
CLAVE_RSA = "ssh-rsa AAAAB3NzaC1yc2EAAAAAAAAAAA== bea@pc"
TOKEN = "root@pam!lab=0a1b2c3d-1111-2222-3333-444455556666"


def ci_completa(**cambios) -> ConfigCloudInit:
    base = {
        "usuario": "deploy",
        "claves": (CLAVE, CLAVE_RSA),
        "tarjetas": (
            TarjetaCloudInit(0, FIJA, "10.0.0.50/24", serie=True, puerta="10.0.0.1"),
            TarjetaCloudInit(1, DHCP),
        ),
        "dns": ("1.1.1.1", "8.8.8.8"),
        "dominio": "lab.local",
        "actualizar": False,
        "snippets": SnippetsCloudInit(vendor="local:snippets/agente.yaml", user=NINGUNO),
        "activar_agente": True,
    }
    base.update(cambios)
    return ConfigCloudInit(**base)


def lote_b(cantidad: int = 3, **cfg) -> LoteGuardado:
    cambios = {"cloudinit": ci_completa(), "esperar_ip": True, "plazo_ip_s": 90, "encender": True}
    cambios.update(cfg)
    return LoteGuardado("Lote B", definicion(cantidad, plantilla_vm=plantilla(**cambios)))


def bytes_de(lote: LoteGuardado) -> bytes:
    return lote_a_bytes(lote, app_version="0.7.0")


def version_escrita(lote: LoteGuardado) -> int:
    return json.loads(bytes_de(lote))["version_formato"]


def mutar(lote: LoteGuardado, fn) -> bytes:
    cuerpo = json.loads(bytes_de(lote))
    fn(cuerpo)
    return json.dumps(cuerpo).encode()


def rutas_error(datos: bytes) -> list[tuple[str, MotivoCampo]]:
    with pytest.raises(ErrorArchivo) as exc:
        leer_lote(datos)
    return [(e.ruta, e.motivo) for e in exc.value.errores]


def cfg_ci(cuerpo: dict) -> dict:
    return cuerpo["homogeneo"]["config"]["cloudinit"]


def claves_json(obj) -> list[str]:
    """Todas las claves de un JSON, a cualquier profundidad."""
    if isinstance(obj, dict):
        return [*obj, *(k for v in obj.values() for k in claves_json(v))]
    if isinstance(obj, list):
        return [k for v in obj for k in claves_json(v)]
    return []


# --- RF-B6.1: versión escrita --------------------------------------------------------------------


def test_rf_b6_1_la_version_maxima_que_se_lee_es_4_y_la_de_la_fase_a_3():
    assert VERSION_FORMATO == 4 and VERSION_FORMATO_FASE_A == 3


def test_ca_b6_1_3_un_lote_que_no_usa_nada_de_b_se_escribe_con_la_version_minima():
    lote = LoteGuardado("x", definicion(3, plantilla_vm=plantilla()))
    assert version_escrita(lote) == 1
    con_a = LoteGuardado("x", definicion(3, plantilla_vm=plantilla(proteger=True)))
    assert version_escrita(con_a) == 3  # fase A: 0.6.0 lo sigue abriendo


def test_ca_b6_1_3_la_configuracion_por_defecto_de_b_no_cambia_la_version():
    por_defecto = plantilla(
        cloudinit=None, esperar_ip=False, plazo_ip_s=120, encender=True, proteger=True
    )
    assert version_escrita(LoteGuardado("x", definicion(2, plantilla_vm=por_defecto))) == 3
    vacia = plantilla(cloudinit=ConfigCloudInit(), proteger=True)
    assert version_escrita(LoteGuardado("x", definicion(2, plantilla_vm=vacia))) == 3


def test_ca_b6_1_3_los_claves_de_b_no_se_escriben_si_no_se_usan():
    datos = json.loads(bytes_de(LoteGuardado("x", definicion(2, plantilla_vm=plantilla()))))
    texto = json.dumps(datos)
    for clave in ("cloudinit", "esperar_ip", "plazo_s", "con_acceso_local"):
        assert clave not in texto


@pytest.mark.parametrize(
    "cambios",
    [
        {"cloudinit": ConfigCloudInit(usuario="u")},
        {"cloudinit": ConfigCloudInit(claves=(CLAVE,))},
        {"cloudinit": ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, DHCP),))},
        {"cloudinit": ConfigCloudInit(dns=("1.1.1.1",))},
        {"cloudinit": ConfigCloudInit(dominio="x.y")},
        {"cloudinit": ConfigCloudInit(actualizar=False)},
        {"cloudinit": ConfigCloudInit(snippets=SnippetsCloudInit(meta=NINGUNO))},
        {"cloudinit": ConfigCloudInit(activar_agente=True)},
        {"esperar_ip": True},
    ],
    ids=["usuario", "claves", "tarjeta", "dns", "dominio", "actualizar", "snippets", "agente",
         "esperar_ip"],
)  # fmt: skip
def test_ca_b6_1_4_cada_opcion_de_b_obliga_a_v4(cambios):
    assert version_escrita(LoteGuardado("x", definicion(2, plantilla_vm=plantilla(**cambios)))) == 4


def test_ca_b6_1_4_las_opciones_de_lote_y_de_fila_de_b_tambien_obligan_a_v4():
    homog = definicion(2, plantilla_vm=plantilla())
    con_lote = dataclasses.replace(homog, opciones=OpcionesLote(esperar_ip=True))
    assert version_para(LoteGuardado("x", con_lote)) == 4
    con_ci = dataclasses.replace(homog, opciones=OpcionesLote(cloudinit=ci_completa()))
    assert version_para(LoteGuardado("x", con_ci)) == 4
    filas = (
        FilaLote("a", plantilla()),
        FilaLote("b", plantilla(), opciones=OpcionesParciales(esperar_ip=True)),
    )
    por_filas = DefinicionLote(plantilla(), 2, PatronNombres(""), Destino(), filas=filas)
    assert version_para(LoteGuardado("x", por_filas)) == 4
    celdas = OpcionesParciales(cloudinit=CloudInitParcial(usuario="u"))
    filas2 = (FilaLote("a", plantilla(), opciones=celdas), FilaLote("b", plantilla()))
    assert (
        version_para(
            LoteGuardado(
                "x", DefinicionLote(plantilla(), 2, PatronNombres(""), Destino(), filas=filas2)
            )
        )
        == 4
    )


def test_ca_b6_1_4_un_lector_de_0_6_0_rechaza_la_v4_como_version_futura():
    """0.6.0 lee hasta v3: se emula con ``version_soportada=3``."""
    datos = json.loads(bytes_de(lote_b()))
    assert datos["version_formato"] == 4
    with pytest.raises(ErrorProxLaunch) as exc:
        abrir_envoltura(datos, FORMATO_LOTE, version_soportada=VERSION_FORMATO_FASE_A)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert exc.value.params == {"version_archivo": "4", "version_soportada": "3"}


def test_ca_b6_1_5_una_version_futura_se_rechaza_sin_leer_nada():
    datos = mutar(lote_b(), lambda d: d.__setitem__("version_formato", 5))
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_lote(datos)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert exc.value.params == {"version_archivo": "5", "version_soportada": "4"}


# --- CA-B6.1.1 / CA-B6.1.2 / CA-B6.4.1: archivos de 0.5.1 y 0.6.0 --------------------------------

ARCHIVOS_051 = [
    ("lote-homogeneo-051-v1.json", 1),
    ("lote-homogeneo-051-v2.json", 2),
    ("lote-por-filas-051-v2.json", 2),
]
ARCHIVOS_060 = [
    ("p2_lote-homogeneo-060-v3.json", 3),
    ("p2_lote-por-filas-060-v3.json", 3),
]


def _ruta(nombre: str) -> Path:
    return (DATOS_B if nombre.startswith("p2_") else DATOS_A) / nombre


@pytest.mark.parametrize(("nombre", "version"), [*ARCHIVOS_051, *ARCHIVOS_060])
def test_ca_b6_1_1_los_lotes_de_051_y_060_se_leen_con_los_campos_de_b_por_defecto(nombre, version):
    archivo = leer_archivo_lote(_ruta(nombre))
    assert archivo.version_original == version
    d = archivo.lote.definicion
    cfgs = [f.cfg for f in d.filas] if d.es_por_filas else [d.plantilla]
    for cfg in cfgs:
        assert cfg.cloudinit is None
        assert cfg.esperar_ip is False and cfg.plazo_ip_s == 120
    if d.opciones is not None:
        assert d.opciones.cloudinit is None and d.opciones.esperar_ip is False
    for fila in d.filas:
        assert fila.opciones is None or (
            fila.opciones.cloudinit is None and fila.opciones.esperar_ip is None
        )


@pytest.mark.parametrize(("nombre", "version"), [*ARCHIVOS_051, *ARCHIVOS_060])
def test_ca_b6_1_1_la_migracion_a_v4_es_la_identidad_y_no_avisa(nombre, version):
    """Decisión del orquestador (§12): el paso 3 -> 4 no avisa ``MIGRADO``."""
    archivo = leer_archivo_lote(_ruta(nombre))
    assert CodigoAvisoArchivo.MIGRADO not in {a.codigo for a in archivo.avisos}
    assert archivo.avisos == ()


@pytest.mark.parametrize(
    "nombre", ["p2_lote-homogeneo-060-v3.json", "p2_lote-por-filas-060-v3.json"]
)
def test_ca_b6_1_2_lo_que_lee_070_de_un_lote_de_060_es_lo_que_leia_060(nombre):
    esperado = json.loads((DATOS_B / nombre.replace(".json", ".esperado.json")).read_text())
    leido = leer_archivo_lote(DATOS_B / nombre).lote
    assert json.loads(json.dumps(lote_a_dict(leido), sort_keys=True)) == esperado


@pytest.mark.parametrize(("nombre", "version"), [*ARCHIVOS_051, *ARCHIVOS_060])
def test_ca_b6_4_1_la_ida_y_vuelta_es_identica_y_no_sube_la_version(nombre, version):
    original = json.loads(_ruta(nombre).read_text())
    lote = leer_archivo_lote(_ruta(nombre)).lote
    regrabado = json.loads(lote_a_bytes(lote, app_version=original["app_version"]))
    assert regrabado == original
    assert regrabado["version_formato"] == version  # 0.6.0 y 0.5.1 pueden volver a abrirlo


@pytest.mark.parametrize("nombre", sorted(p.name for p in DATOS_MVP3.glob("lote-*-v1.json")))
def test_ca_b6_4_1_los_lotes_de_mvp3_se_abren_y_siguen_siendo_v1(nombre):
    archivo = leer_archivo_lote(DATOS_MVP3 / nombre)
    assert archivo.avisos == ()
    assert version_para(archivo.lote) == 1


def test_ca_b6_1_2_la_planificacion_de_un_lote_migrado_no_lleva_nada_de_b():
    """Sin cloud-init ni espera de IP en el lote, el plan no tiene problemas ni IP calculadas."""
    lote = leer_archivo_lote(DATOS_B / "p2_lote-homogeneo-060-v3.json").lote
    from .apoyo_lote import inventario

    plan = construir_plan(
        lote.definicion, inventario(), [100, 101, 102, 103], [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip
    assert not [p for p in plan.problemas if p.regla.startswith("V-B")]
    assert all(e.cfg.cloudinit is None and not e.cfg.esperar_ip for e in plan.elementos)


@pytest.mark.parametrize(
    "nombre", ["perfiles-051-v1.json", "perfiles-051-v2.json", "perfiles-fabrica-051.json"]
)
def test_ca_b6_4_1_los_perfiles_de_051_se_siguen_abriendo_y_regrabando_igual(nombre):
    original = json.loads((DATOS_A / nombre).read_text())
    leidos = leer_archivo_perfiles(DATOS_A / nombre)
    assert leidos.validos and not leidos.invalidos
    assert [a.codigo for a in leidos.avisos] == []
    perfiles = [
        PerfilMaquina(f"p{i}", v.nombre, v.descripcion, OrigenPerfil.USUARIO, v.config)
        for i, v in enumerate(leidos.validos)
    ]
    regrabado = json.loads(
        perfiles_a_bytes(perfiles, con_pistas=True, app_version=original["app_version"])
    )
    assert regrabado == original  # misma versión y mismo contenido: 0.5.1 lo vuelve a abrir


def test_ca_b6_4_1_el_perfil_de_060_se_lee_igual_y_se_regraba_en_v3():
    ruta = DATOS_B / "p2_perfiles-060-v3.json"
    original = json.loads(ruta.read_text())
    leido = leer_archivo_perfiles(ruta)
    assert leido.validos and not leido.invalidos and leido.avisos == ()
    esperado = json.loads((DATOS_B / "p2_perfiles-060-v3.esperado.json").read_text())
    perfil = leido.validos[0]
    como = PerfilMaquina(
        "x", perfil.nombre, perfil.descripcion, OrigenPerfil.USUARIO, perfil.config
    )
    assert json.loads(json.dumps(perfil_a_dict(como, con_pistas=True), sort_keys=True)) == esperado
    nuevo = json.loads(perfiles_a_bytes([como], con_pistas=True, app_version="0.6.0"))
    assert nuevo["version_formato"] == 3
    assert nuevo == original


# --- CA-B6.2.1 / CA-B6.2.2 / CL-B24: perfiles ----------------------------------------------------


def test_ca_b6_2_1_un_perfil_no_tiene_ningun_campo_de_b():
    campos = {f.name for f in dataclasses.fields(ConfigPerfil)}
    assert not {
        c for c in campos if "cloudinit" in c or c == "ip" or "snippet" in c or "esperar" in c
    }


def test_ca_b6_2_1_guardar_un_perfil_desde_un_formulario_con_todo_b_rellenado_es_el_de_060():
    hardware = plantilla(memoria_mib=4096, cores=4, arranque_auto=True)
    con_b = dataclasses.replace(
        hardware,
        cloudinit=ci_completa(contrasena=Secreto(CENTINELA)),
        esperar_ip=True,
        plazo_ip_s=60,
    )
    sin_b = copy.deepcopy(hardware)
    a, b = (config_desde_configuracion(c, con_pistas=True) for c in (con_b, sin_b))
    assert a == b

    def archivo(cfg):
        p = PerfilMaquina("x", "P", "d", OrigenPerfil.USUARIO, cfg)
        return perfiles_a_bytes([p], con_pistas=True, app_version="0.7.0")

    assert archivo(a) == archivo(b)
    assert json.loads(archivo(a))["version_formato"] <= 3  # nunca v4
    assert CENTINELA.encode() not in archivo(a) and b"cloudinit" not in archivo(a)


def test_ca_b6_2_2_cl_b24_aplicar_un_perfil_de_clon_no_toca_los_campos_de_b_del_formulario():
    """Un perfil con origen «clonar» parte de lo que hay en el formulario y solo cambia hardware."""
    formulario = plantilla(
        cloudinit=ci_completa(contrasena=Secreto(CENTINELA)), esperar_ip=True, plazo_ip_s=45
    )
    perfil = ConfigPerfil(memoria_mib=8192, cores=8, origen=OrigenSO.CLONAR_PLANTILLA)
    cfg = aplicar_config(perfil, formulario, None).cfg
    assert cfg.cloudinit == formulario.cloudinit
    assert cfg.cloudinit.contrasena is formulario.cloudinit.contrasena
    assert (cfg.esperar_ip, cfg.plazo_ip_s) == (True, 45)


def test_obs_p2_b_aplicar_un_perfil_a_una_mv_que_no_clona_conserva_la_fase_b():
    """OBS-P2-b: la rama que no clona conserva cloud-init y la espera de IP, como la de clon."""
    formulario = plantilla(
        cloudinit=ci_completa(contrasena=Secreto(CENTINELA)), esperar_ip=True, plazo_ip_s=45
    )
    perfil = ConfigPerfil(memoria_mib=8192, cores=8, origen=OrigenSO.DISCO_VACIO)
    cfg = aplicar_config(perfil, formulario, None).cfg
    assert cfg.memoria_mib == 8192 and cfg.origen == OrigenSO.DISCO_VACIO
    assert cfg.cloudinit is formulario.cloudinit
    assert (cfg.esperar_ip, cfg.plazo_ip_s) == (True, 45)


def test_ca_b6_2_2_aplicar_un_perfil_sobre_un_formulario_sin_b_nunca_crea_campos_de_b():
    perfil = ConfigPerfil(memoria_mib=8192, cores=8)
    cfg = aplicar_config(perfil, plantilla(), None).cfg
    assert cfg.memoria_mib == 8192 and cfg.cores == 8  # el hardware sí se aplicó
    assert cfg.cloudinit is None
    assert (cfg.esperar_ip, cfg.plazo_ip_s) == (False, 120)


def _perfiles_060_con(config_extra: dict) -> bytes:
    cuerpo = json.loads((DATOS_B / "p2_perfiles-060-v3.json").read_text())
    cuerpo["perfiles"][0]["config"].update(config_extra)
    return json.dumps(cuerpo).encode()


def test_ca_b6_2_1_un_perfil_con_claves_de_b_manipuladas_las_ignora_y_avisa():
    leido = leer_perfiles(
        _perfiles_060_con({"cloudinit": {"usuario": "x"}, "esperar_ip": {"activo": True}})
    )
    assert len(leido.validos) == 1 and not leido.invalidos  # el perfil se acepta
    assert "cloudinit" not in repr(leido.validos[0].config)
    (aviso,) = [a for a in leido.avisos if a.codigo == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS]
    assert aviso.params == {"n": "2"}
    como = json.loads(
        perfiles_a_bytes(
            [PerfilMaquina("x", "P", "d", OrigenPerfil.USUARIO, leido.validos[0].config)],
            con_pistas=True,
            app_version="0.7.0",
        )
    )
    assert "cloudinit" not in json.dumps(como) and como["version_formato"] <= 3


# --- RF-B6.1: contenido del archivo v4 -----------------------------------------------------------


def test_rf_b6_1_el_archivo_v4_lleva_cloudinit_y_esperar_ip_con_el_formato_de_la_arquitectura():
    cuerpo = json.loads(bytes_de(lote_b()))
    assert cuerpo["version_formato"] == 4
    config = cuerpo["homogeneo"]["config"]
    assert config["esperar_ip"] == {"activo": True, "plazo_s": 90}
    assert config["cloudinit"] == {
        "usuario": "deploy",
        "claves": [CLAVE, CLAVE_RSA],
        "tarjetas": [
            {
                "indice": 0,
                "modo": "fija",
                "ip": "10.0.0.50/24",
                "serie": True,
                "puerta": "10.0.0.1",
            },
            {"indice": 1, "modo": "dhcp"},
        ],
        "dns": ["1.1.1.1", "8.8.8.8"],
        "dominio": "lab.local",
        "actualizar": False,
        "snippets": {"vendor": "local:snippets/agente.yaml", "user": "ninguno"},
        "activar_agente": True,
    }


def test_rf_b6_1_lo_que_vale_el_valor_por_defecto_se_omite():
    lote = lote_b(cloudinit=ConfigCloudInit(usuario="u"), esperar_ip=False, plazo_ip_s=120)
    config = json.loads(bytes_de(lote))["homogeneo"]["config"]
    assert config["cloudinit"] == {"usuario": "u"}
    assert "esperar_ip" not in config


def test_qa_b5_el_plazo_no_se_escribe_si_no_se_espera_y_el_archivo_sigue_en_v3():
    """Un plazo cambiado con la casilla desmarcada no obliga a v4 ni se escribe (QA-B5)."""
    lote = lote_b(cloudinit=None, esperar_ip=False, plazo_ip_s=30)
    config = json.loads(bytes_de(lote))
    assert "esperar_ip" not in config["homogeneo"]["config"]
    assert version_escrita(lote) != 4


def test_rf_b6_1_la_lectura_restaura_todo_lo_escrito():
    original = lote_b()
    leida = leer_lote(bytes_de(original)).lote.definicion.plantilla
    esperada = original.definicion.plantilla
    assert leida.cloudinit == esperada.cloudinit
    assert (leida.esperar_ip, leida.plazo_ip_s) == (True, 90)
    assert leida.cloudinit.tarjetas[0].serie is True


def test_rf_b6_1_el_campo_serie_inicial_calculado_no_se_escribe_ni_altera_la_igualdad():
    tarjeta = TarjetaCloudInit(0, FIJA, "10.0.0.52/24", serie=False, serie_inicial="10.0.0.50/24")
    lote = lote_b(cloudinit=ConfigCloudInit(tarjetas=(tarjeta,)))
    texto = bytes_de(lote).decode()
    assert "serie_inicial" not in texto and "10.0.0.50" not in texto
    leida = leer_lote(texto.encode()).lote.definicion.plantilla.cloudinit
    assert leida.tarjetas[0].serie_inicial is None
    assert leida.tarjetas[0] == tarjeta  # compare=False


# --- CA-B6.1.6: lectura estricta con la ruta del campo -------------------------------------------


def _cambiar(clave: str, valor):
    return lambda d: cfg_ci(d).__setitem__(clave, valor)


@pytest.mark.parametrize(
    ("cambio", "ruta", "motivo"),
    [
        (_cambiar("dns", 5), "homogeneo.config.cloudinit.dns", MotivoCampo.TIPO),
        (_cambiar("claves", "x"), "homogeneo.config.cloudinit.claves", MotivoCampo.TIPO),
        (_cambiar("usuario", 5), "homogeneo.config.cloudinit.usuario", MotivoCampo.TIPO),
        (_cambiar("dominio", ["x"]), "homogeneo.config.cloudinit.dominio", MotivoCampo.TIPO),
        (_cambiar("actualizar", "si"), "homogeneo.config.cloudinit.actualizar", MotivoCampo.TIPO),
        (
            _cambiar("activar_agente", "si"),
            "homogeneo.config.cloudinit.activar_agente",
            MotivoCampo.TIPO,
        ),
        (_cambiar("tarjetas", {}), "homogeneo.config.cloudinit.tarjetas", MotivoCampo.TIPO),
        (_cambiar("snippets", []), "homogeneo.config.cloudinit.snippets", MotivoCampo.TIPO),
        (_cambiar("dns", [5]), "homogeneo.config.cloudinit.dns[0]", MotivoCampo.TIPO),
        (_cambiar("claves", [5]), "homogeneo.config.cloudinit.claves[0]", MotivoCampo.TIPO),
        (
            lambda d: cfg_ci(d)["tarjetas"][0].__setitem__("modo", "magia"),
            "homogeneo.config.cloudinit.tarjetas[0].modo",
            MotivoCampo.ENUM,
        ),
        (
            lambda d: cfg_ci(d)["tarjetas"][0].__setitem__("indice", 32),
            "homogeneo.config.cloudinit.tarjetas[0].indice",
            MotivoCampo.RANGO,
        ),
        (
            lambda d: cfg_ci(d)["tarjetas"][0].__setitem__("indice", -1),
            "homogeneo.config.cloudinit.tarjetas[0].indice",
            MotivoCampo.RANGO,
        ),
        (
            lambda d: cfg_ci(d)["tarjetas"][0].__setitem__("serie", "yes"),
            "homogeneo.config.cloudinit.tarjetas[0].serie",
            MotivoCampo.TIPO,
        ),
        (
            lambda d: cfg_ci(d)["tarjetas"].append(dict(cfg_ci(d)["tarjetas"][0])),
            "homogeneo.config.cloudinit.tarjetas[2].indice",
            MotivoCampo.DUPLICADO,
        ),
        (
            lambda d: cfg_ci(d)["snippets"].__setitem__("vendor", 5),
            "homogeneo.config.cloudinit.snippets.vendor",
            MotivoCampo.TIPO,
        ),
        (
            lambda d: d["homogeneo"]["config"]["esperar_ip"].__setitem__("plazo_s", 5),
            "homogeneo.config.esperar_ip.plazo_s",
            MotivoCampo.RANGO,
        ),
        (
            lambda d: d["homogeneo"]["config"]["esperar_ip"].__setitem__("plazo_s", 1801),
            "homogeneo.config.esperar_ip.plazo_s",
            MotivoCampo.RANGO,
        ),
        (
            lambda d: d["homogeneo"]["config"]["esperar_ip"].__setitem__("plazo_s", "120"),
            "homogeneo.config.esperar_ip.plazo_s",
            MotivoCampo.TIPO,
        ),
        (
            lambda d: d["homogeneo"]["config"]["esperar_ip"].__setitem__("activo", "si"),
            "homogeneo.config.esperar_ip.activo",
            MotivoCampo.TIPO,
        ),
        (
            lambda d: d["homogeneo"]["config"].__setitem__("cloudinit", []),
            "homogeneo.config.cloudinit",
            MotivoCampo.TIPO,
        ),
        (
            lambda d: d["homogeneo"]["config"].__setitem__("esperar_ip", True),
            "homogeneo.config.esperar_ip",
            MotivoCampo.TIPO,
        ),
    ],
)
def test_ca_b6_1_6_un_campo_con_tipo_o_rango_erroneo_se_marca_con_su_ruta(cambio, ruta, motivo):
    errores = rutas_error(mutar(lote_b(), cambio))
    assert (ruta, motivo) in errores


def test_ca_b6_1_6_dns_5_claves_x_plazo_5_y_modo_magia_se_marcan_todos_a_la_vez():
    def estropear(d):
        cfg_ci(d)["dns"] = 5
        cfg_ci(d)["claves"] = "x"
        cfg_ci(d)["tarjetas"][0]["modo"] = "magia"
        d["homogeneo"]["config"]["esperar_ip"]["plazo_s"] = 5

    rutas = [r for r, _ in rutas_error(mutar(lote_b(), estropear))]
    assert {
        "homogeneo.config.cloudinit.dns",
        "homogeneo.config.cloudinit.claves",
        "homogeneo.config.cloudinit.tarjetas[0].modo",
        "homogeneo.config.esperar_ip.plazo_s",
    } <= set(rutas)


def test_ca_b6_1_6_la_carga_es_atomica_nada_se_devuelve_si_hay_un_error():
    datos = mutar(lote_b(), _cambiar("dns", 5))
    with pytest.raises(ErrorArchivo):
        leer_lote(datos)


def test_ca_b6_1_6_las_rutas_de_las_opciones_de_lote_y_de_fila_se_nombran():
    base = definicion(2, plantilla_vm=plantilla())
    lote = LoteGuardado(
        "x", dataclasses.replace(base, opciones=OpcionesLote(cloudinit=ci_completa()))
    )
    cuerpo = json.loads(bytes_de(lote))
    cuerpo["homogeneo"]["opciones"]["cloudinit"]["dns"] = 5
    assert ("homogeneo.opciones.cloudinit.dns", MotivoCampo.TIPO) in rutas_error(
        json.dumps(cuerpo).encode()
    )
    filas = (
        FilaLote(
            "a", plantilla(), opciones=OpcionesParciales(cloudinit=CloudInitParcial(usuario="u"))
        ),
    )
    por_filas = LoteGuardado(
        "x", DefinicionLote(plantilla(), 1, PatronNombres(""), Destino(), filas=filas)
    )
    cuerpo = json.loads(bytes_de(por_filas))
    cuerpo["por_filas"]["filas"][0]["opciones"]["cloudinit"]["usuario"] = 7
    assert ("por_filas.filas[0].opciones.cloudinit.usuario", MotivoCampo.TIPO) in rutas_error(
        json.dumps(cuerpo).encode()
    )


def test_ca_b6_1_6_las_claves_se_revalidan_y_una_clave_privada_invalida_el_archivo():
    privada = "-----BEGIN OPENSSH PRIVATE KEY-----"
    errores = rutas_error(mutar(lote_b(), _cambiar("claves", [CLAVE, privada])))
    assert ("homogeneo.config.cloudinit.claves", MotivoCampo.TEXTO_NO_VALIDO) in errores


@pytest.mark.parametrize(
    "clave_mala", ["hola", "ssh-rsa", "ssh-ed25519 !!!!", 'command="x" ' + CLAVE]
)
def test_ca_b6_1_6_una_clave_mal_formada_invalida_el_archivo(clave_mala):
    errores = rutas_error(mutar(lote_b(), _cambiar("claves", [CLAVE, clave_mala])))
    assert ("homogeneo.config.cloudinit.claves", MotivoCampo.TEXTO_NO_VALIDO) in errores


def test_ca_b6_1_6_mas_de_20_claves_invalida_el_archivo():
    claves = [CLAVE.replace("ana", f"c{i}") for i in range(21)]
    errores = rutas_error(mutar(lote_b(), _cambiar("claves", claves)))
    assert errores and errores[0][0].startswith("homogeneo.config.cloudinit.claves")


def test_ca_b6_1_6_el_error_nunca_repite_el_valor_de_la_clave_privada():
    cuerpo = "CuerpoPrivado-ZZZ-9f8e7d"
    datos = mutar(lote_b(), _cambiar("claves", [f"-----BEGIN OPENSSH PRIVATE KEY-----\n{cuerpo}"]))
    with pytest.raises(ErrorArchivo) as exc:
        leer_lote(datos)
    assert cuerpo not in repr(exc.value) and cuerpo not in str(exc.value.errores)


# --- CA-B6.1.7: campos desconocidos --------------------------------------------------------------


def test_ca_b6_1_7_un_campo_desconocido_en_cloudinit_se_ignora_con_aviso():
    archivo = leer_lote(mutar(lote_b(), _cambiar("campo_nuevo", 1)))
    avisos = {a.codigo: a for a in archivo.avisos}
    assert avisos[CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS].params == {"n": "1"}
    assert "campo_nuevo" not in repr(archivo.avisos)  # nunca el nombre del campo
    assert archivo.lote.definicion.plantilla.cloudinit == lote_b().definicion.plantilla.cloudinit


def test_ca_b6_1_7_los_desconocidos_de_tarjeta_snippets_y_esperar_ip_se_cuentan_juntos():
    def anadir(d):
        cfg_ci(d)["tarjetas"][0]["mtu"] = 1500
        cfg_ci(d)["snippets"]["otro"] = "x"
        d["homogeneo"]["config"]["esperar_ip"]["extra"] = True

    archivo = leer_lote(mutar(lote_b(), anadir))
    (aviso,) = [a for a in archivo.avisos if a.codigo == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS]
    assert aviso.params == {"n": "3"}


# --- CA-B6.1.8: claves públicas sí; tokens no ----------------------------------------------------


def test_ca_b6_1_8_las_claves_publicas_se_guardan_tal_cual():
    texto = bytes_de(lote_b()).decode()
    assert CLAVE.split()[1] in texto and CLAVE_RSA.split()[1] in texto


@pytest.mark.parametrize(
    "ci",
    [
        ConfigCloudInit(usuario=TOKEN),
        ConfigCloudInit(dominio=TOKEN),
        ConfigCloudInit(dns=(TOKEN,)),
        ConfigCloudInit(claves=(f"{CLAVE} {TOKEN}",)),
        ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, FIJA, TOKEN),)),
        ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.5/24", puerta=TOKEN),)),
        ConfigCloudInit(snippets=SnippetsCloudInit(vendor=f"local:snippets/{TOKEN}")),
    ],
    ids=["usuario", "dominio", "dns", "comentario_clave", "ip", "puerta", "snippet"],
)
def test_ca_b6_1_8_un_token_en_cualquier_texto_de_cloudinit_impide_guardar(ci):
    lote = lote_b(cloudinit=ci)
    with pytest.raises(ErrorProxLaunch) as exc:
        bytes_de(lote)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE or "credencial" in str(
        exc.value.params
    )
    assert TOKEN not in repr(exc.value) and TOKEN not in str(exc.value.params)


def test_ca_b6_1_8_un_archivo_de_terceros_con_token_en_cloudinit_se_rechaza_al_leer():
    datos = mutar(lote_b(), _cambiar("usuario", TOKEN))
    errores = rutas_error(datos)
    assert ("homogeneo.config.cloudinit.usuario", MotivoCampo.TOKEN) in errores


def test_ca_b6_1_8_un_token_en_las_celdas_de_fila_tambien_impide_guardar():
    celdas = OpcionesParciales(cloudinit=CloudInitParcial(usuario=TOKEN))
    filas = (FilaLote("a", plantilla(), opciones=celdas),)
    lote = LoteGuardado(
        "x", DefinicionLote(plantilla(), 1, PatronNombres(""), Destino(), filas=filas)
    )
    with pytest.raises(ErrorProxLaunch):
        bytes_de(lote)


def test_ca_b6_1_8_una_clave_privada_en_la_configuracion_no_se_guarda():
    lote = lote_b(cloudinit=ConfigCloudInit(claves=("-----BEGIN OPENSSH PRIVATE KEY-----",)))
    with pytest.raises(ErrorProxLaunch) as exc:
        bytes_de(lote)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


def test_ca_b6_1_8_nada_que_el_lector_rechazaria_se_escribe_plazo_fuera_de_rango():
    lote = lote_b(esperar_ip=True, plazo_ip_s=5)
    with pytest.raises(ErrorProxLaunch) as exc:
        bytes_de(lote)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


# --- CA-B6.1.9: tamaño ---------------------------------------------------------------------------


def _lote_de_100_con_4_kib_de_claves() -> LoteGuardado:
    claves = tuple(
        f"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAAAAAAAA= {'c' * 160}-{i}" for i in range(20)
    )
    assert 3800 < len("\n".join(claves)) < 4200
    filas = tuple(
        FilaLote(
            f"vm-{i:03d}",
            plantilla(cloudinit=ConfigCloudInit(claves=claves, usuario=f"u{i}")),
        )
        for i in range(100)
    )
    return LoteGuardado(
        "x", DefinicionLote(plantilla(), 100, PatronNombres(""), Destino(), filas=filas)
    )


def test_ca_b6_1_9_cien_filas_con_4_kib_de_claves_caben_o_dan_un_error_de_tamano_claro(tmp_path):
    lote = _lote_de_100_con_4_kib_de_claves()
    datos = bytes_de(lote)
    ruta = tmp_path / "grande.json"
    if len(datos) <= MAX_BYTES_LOTE:
        guardar_lote(ruta, lote, app_version="0.7.0")
        assert len(leer_archivo_lote(ruta).lote.definicion.filas) == 100
    else:
        with pytest.raises(ErrorProxLaunch) as exc:
            guardar_lote(ruta, lote, app_version="0.7.0")
        assert exc.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
        assert exc.value.params["motivo"] == "demasiado_grande"
        assert not ruta.exists()  # nada a medias


def test_ca_b6_1_9_el_error_de_tamano_al_guardar_es_el_mismo_que_al_leer(tmp_path):
    gigante = lote_b(cloudinit=ConfigCloudInit(usuario="u", dominio="a." * 5))
    ruta = tmp_path / "x.json"
    ruta.write_bytes(b" " * (MAX_BYTES_LOTE + 1))
    with pytest.raises(ErrorProxLaunch) as leyendo:
        leer_archivo_lote(ruta)
    assert leyendo.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert leyendo.value.params["motivo"] == "demasiado_grande"
    assert gigante is not None


# --- CA-B6.1.10: ida y vuelta (propiedad con generación aleatoria) -------------------------------


def _clave_aleatoria(rng: random.Random, n: int) -> str:
    tipo = rng.choice(["ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"])
    cuerpo = CLAVE.split()[1] if tipo == "ssh-ed25519" else CLAVE_RSA.split()[1]
    comentario = rng.choice(["a@b", "ñandú 🙂", "x y", ""])
    return f"{tipo} {cuerpo} {comentario}{n}".strip()


def _tarjeta_aleatoria(rng: random.Random, indice: int) -> TarjetaCloudInit:
    modo = rng.choice([FIJA, DHCP, SIN])
    if modo == FIJA:
        red = f"10.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
        ip = f"{red}.{rng.randint(1, 200)}/{rng.choice([16, 24, 30])}"
        return TarjetaCloudInit(
            indice, FIJA, ip, rng.random() < 0.5, rng.choice([None, "10.0.0.1", "192.168.1.1"])
        )
    return TarjetaCloudInit(indice, modo)


def ci_aleatoria(rng: random.Random) -> ConfigCloudInit:
    indices = sorted(rng.sample(range(8), rng.randint(0, 4)))
    claves = tuple(dict.fromkeys(_clave_aleatoria(rng, i) for i in range(rng.randint(0, 5))))
    snippets = SnippetsCloudInit(
        *(
            rng.choice([None, NINGUNO, f"local:snippets/{t}{rng.randint(0, 9)}.yaml"])
            for t in "uvnm"
        )
    )
    return ConfigCloudInit(
        usuario=rng.choice(["", "deploy", "ubuntu", "ñandú", "svc_x"]),
        claves=claves,
        tarjetas=tuple(_tarjeta_aleatoria(rng, i) for i in indices),
        dns=tuple(
            rng.sample(["1.1.1.1", "8.8.8.8", "9.9.9.9", "2001:4860:4860::8888"], rng.randint(0, 3))
        ),
        dominio=rng.choice(["", "lab.local", "a.b.c"]),
        actualizar=rng.choice([None, True, False]),
        snippets=snippets,
        activar_agente=rng.random() < 0.3,
    )


def _efectiva(ci: ConfigCloudInit | None) -> ConfigCloudInit | None:
    return None if ci is None or ci.vacia else ci


def _parcial_aleatoria(rng: random.Random) -> CloudInitParcial | None:
    ci = ci_aleatoria(rng)
    p = CloudInitParcial(
        usuario=rng.choice([None, ci.usuario or "u"]),
        claves=rng.choice([None, ci.claves]),
        tarjeta0=rng.choice([None, _tarjeta_aleatoria(rng, 0)]),
        dns=rng.choice([None, ci.dns]),
        dominio=rng.choice([None, ci.dominio]),
        actualizar=rng.choice([None, True, False]),
        snippets=rng.choice([None, ci.snippets]) if not ci.snippets.como_la_plantilla else None,
    )
    return None if p.vacia else p


@pytest.mark.parametrize("por_filas", [False, True], ids=["homogeneo", "por_filas"])
def test_ca_b6_1_10_ida_y_vuelta_con_configuraciones_de_b_aleatorias(por_filas):
    rng = random.Random(SEMILLA + int(por_filas))
    for _ in range(200):
        esperar = rng.random() < 0.5
        plazo = rng.choice([10, 30, 120, 600, 1800])
        # El plazo solo se escribe con la espera activa; si no, vuelve el predeterminado.
        plazo_vuelta = plazo if esperar else PLAZO_IP_DEFECTO_S
        if por_filas:
            filas = tuple(
                FilaLote(
                    f"vm-{i}",
                    plantilla(cloudinit=ci_aleatoria(rng), esperar_ip=esperar, plazo_ip_s=plazo),
                    opciones=(
                        OpcionesParciales(
                            cloudinit=_parcial_aleatoria(rng),
                            esperar_ip=rng.choice([None, True, False]),
                        )
                        if rng.random() < 0.7
                        else None
                    ),
                )
                for i in range(rng.randint(1, 4))
            )
            d = DefinicionLote(plantilla(), len(filas), PatronNombres(""), Destino(), filas=filas)
        else:
            cfg = plantilla(cloudinit=ci_aleatoria(rng), esperar_ip=esperar, plazo_ip_s=plazo)
            d = definicion(rng.randint(1, 5), plantilla_vm=cfg)
            if rng.random() < 0.5:
                d = dataclasses.replace(d, opciones=OpcionesLote.desde_config(cfg))
        datos = bytes_de(LoteGuardado("rnd", d))
        leida = leer_lote(datos).lote.definicion
        if por_filas:
            for orig, vuelta in zip(d.filas, leida.filas, strict=True):
                assert _efectiva(vuelta.cfg.cloudinit) == _efectiva(orig.cfg.cloudinit)
                assert (vuelta.cfg.esperar_ip, vuelta.cfg.plazo_ip_s) == (esperar, plazo_vuelta)
                o_op, v_op = orig.opciones, vuelta.opciones
                if o_op is not None and (o_op.cloudinit is not None or o_op.esperar_ip is not None):
                    assert v_op is not None
                    assert v_op.cloudinit == o_op.cloudinit
                    assert v_op.esperar_ip == o_op.esperar_ip
        else:
            assert _efectiva(leida.plantilla.cloudinit) == _efectiva(d.plantilla.cloudinit)
            assert (leida.plantilla.esperar_ip, leida.plantilla.plazo_ip_s) == (
                esperar,
                plazo_vuelta,
            )
            if d.opciones is not None:
                efectivas = leida.opciones or OpcionesLote.desde_config(leida.plantilla)
                assert _efectiva(efectivas.cloudinit) == _efectiva(d.opciones.cloudinit)
        # Estabilidad: volver a escribir lo leído da el mismo archivo.
        assert bytes_de(LoteGuardado("rnd", leida)) == datos


def test_ca_b6_1_10_configuracion_vm_a_dict_y_desde_dict_es_identica_salvo_la_contrasena():
    from proxlaunch.nucleo.modelos.vm import ConfiguracionVM

    rng = random.Random(SEMILLA + 5)
    for _ in range(100):
        cfg = plantilla(
            cloudinit=ci_aleatoria(rng),
            esperar_ip=rng.random() < 0.5,
            plazo_ip_s=rng.choice([10, 120, 1800]),
        )
        vuelta = ConfiguracionVM.desde_dict(cfg.a_dict())
        assert vuelta.cloudinit == cfg.cloudinit
        assert (vuelta.esperar_ip, vuelta.plazo_ip_s) == (cfg.esperar_ip, cfg.plazo_ip_s)


def test_ca_b6_1_10_la_contrasena_es_lo_unico_que_no_vuelve():
    cfg = plantilla(cloudinit=ci_completa(contrasena=Secreto(CENTINELA)))
    from proxlaunch.nucleo.modelos.vm import ConfiguracionVM

    vuelta = ConfiguracionVM.desde_dict(cfg.a_dict())
    assert vuelta.cloudinit.contrasena is None
    assert vuelta.cloudinit == cfg.cloudinit  # compare=False en ``contrasena``
    assert dataclasses.replace(vuelta.cloudinit, contrasena=None) == dataclasses.replace(
        cfg.cloudinit, contrasena=None
    )


# --- CA-B0.8.2 / CA-B0.8.3 / CA-B6.1.11: la contraseña no se guarda ------------------------------


def _con_contrasena() -> LoteGuardado:
    return lote_b(cloudinit=ci_completa(contrasena=Secreto(CENTINELA)))


def test_ca_b0_8_2_el_archivo_no_contiene_la_contrasena_ni_claves_con_aspecto_de_credencial():
    datos = bytes_de(_con_contrasena())
    assert CENTINELA.encode() not in datos
    cuerpo = json.loads(datos)
    assert [k for k in claves_json(cuerpo) if es_clave_credencial(k)] == []
    assert cfg_ci(cuerpo)["con_acceso_local"] is True


def test_ca_b0_8_2_el_indicador_se_escribe_solo_si_habia_contrasena():
    sin = json.loads(bytes_de(lote_b()))
    assert "con_acceso_local" not in cfg_ci(sin)


def test_ca_b0_8_2_al_reabrir_se_avisa_de_que_la_contrasena_no_se_guardo():
    archivo = leer_lote(bytes_de(_con_contrasena()))
    assert CodigoAvisoArchivo.CONTRASENA_NO_GUARDADA in {a.codigo for a in archivo.avisos}
    assert archivo.lote.definicion.plantilla.cloudinit.contrasena is None


def test_ca_b0_8_2_sin_contrasena_no_hay_aviso_de_contrasena():
    archivo = leer_lote(bytes_de(lote_b()))
    assert CodigoAvisoArchivo.CONTRASENA_NO_GUARDADA not in {a.codigo for a in archivo.avisos}


def test_ca_b0_8_2_una_contrasena_sola_ya_obliga_a_v4_y_deja_solo_el_indicador():
    lote = lote_b(
        cloudinit=ConfigCloudInit(contrasena=Secreto(CENTINELA)), esperar_ip=False, plazo_ip_s=120
    )
    cuerpo = json.loads(bytes_de(lote))
    assert cuerpo["version_formato"] == 4
    assert cfg_ci(cuerpo) == {"con_acceso_local": True}


def test_ca_b0_8_2_las_celdas_de_fila_con_contrasena_tambien_dejan_solo_el_indicador():
    celdas = OpcionesParciales(
        cloudinit=CloudInitParcial(usuario="u", contrasena=Secreto(CENTINELA))
    )
    filas = (FilaLote("a", plantilla(), opciones=celdas), FilaLote("b", plantilla()))
    lote = LoteGuardado(
        "x", DefinicionLote(plantilla(), 2, PatronNombres(""), Destino(), filas=filas)
    )
    datos = bytes_de(lote)
    assert CENTINELA.encode() not in datos
    archivo = leer_lote(datos)
    assert CodigoAvisoArchivo.CONTRASENA_NO_GUARDADA in {a.codigo for a in archivo.avisos}
    assert archivo.lote.definicion.filas[0].opciones.cloudinit.contrasena is None


@pytest.mark.parametrize(
    "clave", ["contrasena", "cipassword", "ci_password", "password", "Contraseña"]
)
def test_ca_b0_8_3_ca_b6_1_11_una_clave_de_contrasena_manipulada_se_ignora_con_aviso(clave):
    archivo = leer_lote(mutar(lote_b(), _cambiar(clave, CENTINELA)))
    avisos = {a.codigo: a for a in archivo.avisos}
    assert avisos[CodigoAvisoArchivo.CREDENCIAL_IGNORADA].params == {"n": "1"}
    ci = archivo.lote.definicion.plantilla.cloudinit
    assert ci.contrasena is None
    assert CENTINELA not in repr(archivo) and CENTINELA not in repr(ci)
    assert CENTINELA not in json.dumps(lote_a_dict(archivo.lote))


def test_ca_b0_8_3_la_contrasena_manipulada_en_opciones_de_lote_y_de_fila_tampoco_llega():
    lote = LoteGuardado(
        "x",
        dataclasses.replace(
            definicion(2, plantilla_vm=plantilla()), opciones=OpcionesLote(cloudinit=ci_completa())
        ),
    )
    cuerpo = json.loads(bytes_de(lote))
    cuerpo["homogeneo"]["opciones"]["cloudinit"]["cipassword"] = CENTINELA
    archivo = leer_lote(json.dumps(cuerpo).encode())
    assert archivo.lote.definicion.opciones.cloudinit.contrasena is None
    assert CENTINELA not in repr(archivo)

    celdas = OpcionesParciales(cloudinit=CloudInitParcial(usuario="u"))
    filas = (FilaLote("a", plantilla(), opciones=celdas),)
    por_filas = LoteGuardado(
        "x", DefinicionLote(plantilla(), 1, PatronNombres(""), Destino(), filas=filas)
    )
    cuerpo = json.loads(bytes_de(por_filas))
    cuerpo["por_filas"]["filas"][0]["opciones"]["cloudinit"]["contrasena"] = CENTINELA
    archivo = leer_lote(json.dumps(cuerpo).encode())
    assert archivo.lote.definicion.filas[0].opciones.cloudinit.contrasena is None
    assert CENTINELA not in repr(archivo)


def test_ca_b0_8_3_el_indicador_es_neutro_y_manipularlo_con_otro_tipo_se_rechaza():
    errores = rutas_error(mutar(lote_b(), _cambiar("con_acceso_local", "si")))
    assert ("homogeneo.config.cloudinit.con_acceso_local", MotivoCampo.TIPO) in errores


def test_ca_b0_8_3_una_contrasena_manipulada_en_un_perfil_se_ignora_con_aviso():
    leido = leer_perfiles(_perfiles_060_con({"contrasena": CENTINELA, "cipassword": CENTINELA}))
    assert len(leido.validos) == 1 and not leido.invalidos
    (aviso,) = [a for a in leido.avisos if a.codigo == CodigoAvisoArchivo.CREDENCIAL_IGNORADA]
    assert aviso.params == {"n": "2"}
    assert CENTINELA not in repr(leido)


def test_ca_b0_8_1_el_repr_de_lote_leido_y_las_excepciones_no_dejan_ver_la_contrasena():
    lote = _con_contrasena()
    assert CENTINELA not in repr(lote) and CENTINELA not in str(lote.definicion.plantilla)
    assert CENTINELA not in json.dumps(lote_a_dict(lote))


# --- CA-B4.6.3: snippets guardados ---------------------------------------------------------------


V_AGENTE = "local:snippets/agente.yaml"


def _plan_de(definicion_lote, snippets: tuple[str, ...]):
    sn = Storage("local", "dir", frozenset({"snippets"}), False, True, 10**12, 10**12)
    inv = inv_origen(
        nodos=("pve1",),
        plantillas=(plantilla_pve(9000, "base", "pve1"),),
        extra_storages={"pve1": (sn,)},
    )
    listado = ListadoSnippets(
        "pve1", "local", False, tuple(Snippet(v, v.partition("/")[2], 10, True) for v in snippets)
    )
    inv.catalogo = dataclasses.replace(inv.catalogo, snippets=(listado,))
    return construir_plan(
        definicion_lote, inv, [100], [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip


def test_ca_b4_6_3_un_lote_con_snippets_se_restaura_y_se_revalida_contra_el_servidor_actual():
    ci = ConfigCloudInit(snippets=SnippetsCloudInit(vendor=V_AGENTE, user=NINGUNO))
    cfg = cfg_clon("base", 9000, "pve1", cloudinit=ci)
    guardado = LoteGuardado("x", definicion(1, plantilla_vm=cfg))
    leida = leer_lote(bytes_de(guardado)).lote.definicion
    assert leida.plantilla.cloudinit.snippets == ci.snippets  # restaurados
    # El snippet sigue existiendo: sin problemas V-B51.
    ok = _plan_de(leida, (V_AGENTE,))
    assert [p for p in ok.problemas if p.regla == "V-B51"] == []
    # El snippet desapareció del servidor: se revalida y V-B51 bloquea.
    ausente = _plan_de(leida, ("local:snippets/otro.yaml",))
    (p,) = [p for p in ausente.problemas if p.regla == "V-B51"]
    assert p.params["snippet"] == V_AGENTE and p.params["tipo"] == "vendor"


# --- Archivos de terceros y robustez -------------------------------------------------------------


def test_un_archivo_v4_sin_nada_de_b_se_lee_igual_que_uno_v3():
    cuerpo = json.loads(bytes_de(LoteGuardado("x", definicion(2, plantilla_vm=plantilla()))))
    cuerpo["version_formato"] = 4
    archivo = leer_lote(json.dumps(cuerpo).encode())
    assert archivo.version_original == 4 and archivo.avisos == ()
    assert archivo.lote.definicion.plantilla.cloudinit is None


def test_rnf_b4_un_lote_v3_con_claves_de_b_en_la_plantilla_se_acepta_igual():
    """Las claves de B son opcionales: en una v3 manipulada se leen (son campos conocidos)."""
    cuerpo = json.loads(bytes_de(lote_b()))
    cuerpo["version_formato"] = 3
    archivo = leer_lote(json.dumps(cuerpo).encode())
    assert archivo.lote.definicion.plantilla.cloudinit is not None


def test_las_claves_publicas_con_comentario_unicode_sobreviven_a_la_ida_y_vuelta_byte_a_byte():
    clave = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAAAAAAAA= ñandú-🙂 日本"
    lote = lote_b(cloudinit=ConfigCloudInit(claves=(clave,)))
    leida = leer_lote(bytes_de(lote)).lote.definicion.plantilla.cloudinit
    assert leida.claves == (clave,)
    assert analizar_claves("\n".join(leida.claves)).problemas == ()
