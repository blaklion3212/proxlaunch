"""Fase A (0.6.0): formato v3 de lotes guardados y compatibilidad con los archivos de 0.5.1.

Cubre RF-A7.1 (CA-A7.1.1 a A7.1.10), RF-A7.4 (ida y vuelta), RF-A2.6.4, RF-A5.3.6, RF-A1.4.5,
RNF-A2, RNF-A4 y CL-A9. Desviaciones de la sección 0 de la arquitectura: abrir v1/v2 NO avisa
``MIGRADO``; ``notas_origen`` marcada no obliga a v3 pero sí escribe su clave.

Los archivos ``*-051-*.json`` de ``tests/datos/fase_a_p2`` los escribió el código de 0.5.1
(``generar_datos.py``); los ``*.esperado.json`` son lo que 0.5.1 lee de ellos.
"""

import copy
import dataclasses
import json
import random
import time
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.constantes import (
    MAX_BYTES_LOTE,
    MAX_LONG_NOTAS,
    VERSION_FORMATO,
    VERSION_FORMATO_FASE_A,
)
from proxlaunch.nucleo.archivos.envoltura import FORMATO_LOTE, abrir_envoltura
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo, ErrorArchivo
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, FilaLote, PatronNombres
from proxlaunch.nucleo.lotes_guardados.formato import (
    guardar_lote,
    leer_archivo_lote,
    leer_lote,
    lote_a_bytes,
    lote_a_dict,
    version_para,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, InterfazRed, ModeloRed
from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales
from proxlaunch.nucleo.validacion import validar_sin_servidor

from .apoyo_fase_a_p2 import SEMILLA, lote_aleatorio
from .apoyo_lote import definicion, plantilla
from .apoyo_mvp3 import (
    DATOS_MVP3,
    archivo_lote,
    archivo_lote_por_filas,
    config_lote_json,
    lote_homogeneo_json,
)

DATOS = Path(__file__).resolve().parent.parent / "datos" / "fase_a_p2"
NUEVAS_CLAVES = {
    "encender",
    "arranque_auto",
    "arranque_orden",
    "arranque_espera",
    "notas_origen",
    "notas_usuario",
    "notas",
    "etiquetas_usuario",
    "pool",
    "proteger",
}


def _lote(**cambios) -> LoteGuardado:
    return LoteGuardado("Lote", definicion(3, plantilla_vm=plantilla(**cambios)))


def _version_escrita(lote: LoteGuardado) -> int:
    return json.loads(lote_a_bytes(lote, app_version="0.6.0"))["version_formato"]


def _rutas_error(datos: bytes) -> list[str]:
    with pytest.raises(ErrorArchivo) as exc:
        leer_lote(datos)
    return [e.ruta for e in exc.value.errores]


# --- CA-A7.1.1 / RNF-A4: los archivos de 0.5.1 se siguen abriendo igual -----------------------

ARCHIVOS_051 = [
    ("lote-homogeneo-051-v1.json", 1),
    ("lote-homogeneo-051-v2.json", 2),
    ("lote-por-filas-051-v2.json", 2),
]


@pytest.mark.parametrize(("nombre", "version"), ARCHIVOS_051)
def test_ca_a7_1_1_lotes_de_051_v1_y_v2_se_leen_sin_aviso_migrado(nombre, version):
    """Desviación §0: los pasos v1→v2→v3 son silenciosos (archivos válidos tal cual)."""
    archivo = leer_archivo_lote(DATOS / nombre)
    assert archivo.version_original == version
    assert CodigoAvisoArchivo.MIGRADO not in {a.codigo for a in archivo.avisos}
    assert archivo.avisos == ()


@pytest.mark.parametrize(("nombre", "version"), ARCHIVOS_051)
def test_rnf_a4_lo_que_lee_06_es_lo_mismo_que_leia_051(nombre, version):
    esperado = json.loads((DATOS / nombre.replace(".json", ".esperado.json")).read_text())
    leido = leer_archivo_lote(DATOS / nombre).lote
    assert json.loads(json.dumps(lote_a_dict(leido), sort_keys=True)) == esperado


@pytest.mark.parametrize(("nombre", "version"), ARCHIVOS_051)
def test_ca_a7_1_5_regrabar_un_archivo_de_051_no_cambia_nada_ni_sube_la_version(nombre, version):
    """0.6 escribe en la versión más baja posible: 0.5.1 puede volver a abrir lo regrabado."""
    original = json.loads((DATOS / nombre).read_text())
    lote = leer_archivo_lote(DATOS / nombre).lote
    regrabado = json.loads(lote_a_bytes(lote, app_version=original["app_version"]))
    assert regrabado == original
    assert regrabado["version_formato"] == version


@pytest.mark.parametrize("nombre", sorted(p.name for p in DATOS_MVP3.glob("lote-*-v1.json")))
def test_rnf_a4_los_lotes_de_tests_datos_mvp3_se_siguen_abriendo(nombre):
    archivo = leer_archivo_lote(DATOS_MVP3 / nombre)
    assert archivo.version_original == 1
    assert archivo.avisos == ()
    d = archivo.lote.definicion
    assert not NUEVAS_CLAVES & set(json.dumps(lote_a_dict(archivo.lote)).replace('"', " ").split())
    assert d.opciones is None


def test_rnf_a4_los_perfiles_de_mvp3_siguen_abriendose():
    from proxlaunch.nucleo.perfiles_maquina.formato import leer_archivo_perfiles

    r = leer_archivo_perfiles(DATOS_MVP3 / "perfiles-v1.json")
    assert r.validos and not r.invalidos
    assert all(not p.config.arranque_auto for p in r.validos)
    assert all(
        red.mtu is None and red.limite_mb is None for p in r.validos for red in p.config.redes
    )


# --- CA-A7.1.2 / A7.1.3: valores que reproducen 0.5.1 -----------------------------------------


@pytest.mark.parametrize(("nombre", "version"), ARCHIVOS_051)
def test_ca_a7_1_2_los_campos_nuevos_toman_el_valor_de_0_5_1(nombre, version):
    d = leer_archivo_lote(DATOS / nombre).lote.definicion
    cfgs = [f.cfg for f in d.filas] if d.es_por_filas else [d.plantilla]
    for cfg in cfgs:
        assert cfg.encender is False
        assert cfg.arranque_auto is False
        assert cfg.arranque_orden is None and cfg.arranque_espera is None
        assert cfg.notas_origen is False  # P-4: al migrar queda desmarcada
        assert cfg.notas_usuario is False and cfg.notas == ""
        assert cfg.etiquetas_usuario == ()
        assert cfg.pool is None
        assert cfg.proteger is False
        assert all(r.mtu is None and r.limite_mb is None for r in cfg.redes)
    assert d.opciones is None
    assert all(f.opciones is None for f in d.filas)


def test_ca_a7_1_3_el_lote_migrado_no_añade_ningun_parametro_nuevo_a_la_peticion(inv):
    from proxlaunch.nucleo.constructor_peticion import construir_parametros

    d = leer_archivo_lote(DATOS / "lote-homogeneo-051-v1.json").lote.definicion
    cfg = dataclasses.replace(d.plantilla, vmid=100, nombre="web-01", nodo="pve1")
    params = construir_parametros(cfg, inv)
    nuevos = {"onboot", "startup", "description", "pool", "protection"}
    assert not nuevos & set(params)
    assert "mtu=" not in params["net0"] and "rate=" not in params["net0"]
    assert "tags" not in params  # sin etiquetas propias; las fijas las añade el plan


# --- CA-A7.1.4 / A7.1.6: versión futura y versión 3 en el archivo -----------------------------


def test_ca_a7_1_4_version_5_se_rechaza_con_version_futura():
    # Con la fase B (CA-B6.1.5) la máxima legible es 4: la 5 es la primera «futura».
    datos = json.loads(archivo_lote())
    datos["version_formato"] = VERSION_FORMATO + 1
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_lote(json.dumps(datos).encode())
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert exc.value.params["version_archivo"] == "5"
    assert exc.value.params["version_soportada"] == "4"


def test_ca_a7_1_6_un_lote_con_opciones_nuevas_declara_version_formato_3():
    datos = json.loads(lote_a_bytes(_lote(proteger=True), app_version="0.6.0"))
    assert datos["version_formato"] == VERSION_FORMATO_FASE_A == 3


def test_ca_a7_1_6_un_lector_de_0_5_1_rechaza_la_v3_como_version_futura():
    """0.5.1 lee como máximo la v2: simulado con ``version_soportada=2`` (misma regla)."""
    datos = json.loads(lote_a_bytes(_lote(encender=True), app_version="0.6.0"))
    with pytest.raises(ErrorProxLaunch) as exc:
        abrir_envoltura(datos, FORMATO_LOTE, version_soportada=2)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA


# --- CA-A7.1.5: versión mínima posible --------------------------------------------------------

OPCION_V3 = {
    "encender": {"encender": True},
    "arranque_auto": {"arranque_auto": True},
    "arranque_orden": {"arranque_orden": 3},
    "arranque_espera": {"arranque_espera": 30},
    "notas_usuario": {"notas_usuario": True},
    "notas": {"notas": "hola"},
    "etiquetas": {"etiquetas_usuario": ("web",)},
    "pool": {"pool": "produccion"},
    "proteger": {"proteger": True},
    "mtu": {"redes": [InterfazRed("vmbr0", ModeloRed.VIRTIO, None, 9000)]},
    "limite": {"redes": [InterfazRed("vmbr0", ModeloRed.VIRTIO, None, None, 50.0)]},
}


def test_ca_a7_1_5_sin_ninguna_opcion_nueva_se_escribe_v1():
    assert _version_escrita(_lote()) == 1


def test_ca_a7_1_5_con_opciones_de_mvp4_y_ninguna_nueva_se_escribe_v2():
    assert _version_escrita(_lote(agente_qemu=True)) == 2


@pytest.mark.parametrize("cambios", OPCION_V3.values(), ids=OPCION_V3.keys())
def test_ca_a7_1_5_cada_opcion_nueva_obliga_a_v3(cambios):
    assert _version_escrita(_lote(**cambios)) == 3


def test_ca_a7_1_5_las_opciones_de_lote_y_de_fila_tambien_obligan_a_v3():
    base = definicion(2, plantilla_vm=plantilla())
    con_lote = dataclasses.replace(base, opciones=OpcionesLote(proteger=True))
    assert version_para(LoteGuardado("x", con_lote)) == 3
    fila = FilaLote("a", plantilla(), opciones=OpcionesParciales(pool="p"))
    por_filas = DefinicionLote(plantilla(), 1, PatronNombres(""), Destino(), filas=(fila,))
    assert version_para(LoteGuardado("x", por_filas)) == 3


def test_ca_a7_1_5_notas_origen_marcada_no_obliga_a_v3_pero_se_escribe_la_clave():
    """Desviación §0 / P-4: 0.5.1 ignora ``notas_origen`` con aviso; el archivo sigue siendo v1."""
    lote = _lote(notas_origen=True)
    assert _version_escrita(lote) == 1
    datos = json.loads(lote_a_bytes(lote, app_version="0.6.0"))
    assert datos["homogeneo"]["config"]["notas_origen"] is True
    assert leer_lote(lote_a_bytes(lote, app_version="0.6.0")).lote.definicion.plantilla.notas_origen


def test_ca_a7_1_5_notas_origen_desmarcada_no_escribe_la_clave():
    datos = json.loads(lote_a_bytes(_lote(), app_version="0.6.0"))
    assert not NUEVAS_CLAVES & set(datos["homogeneo"]["config"])


def test_ca_a7_1_5_las_claves_nuevas_solo_se_escriben_si_difieren_del_defecto():
    datos = json.loads(lote_a_bytes(_lote(proteger=True), app_version="0.6.0"))
    claves = NUEVAS_CLAVES & set(datos["homogeneo"]["config"])
    assert claves == {"proteger"}


# --- CA-A7.1.7: validación de tipo y rango ----------------------------------------------------


def _archivo_v3(config=None, **extra) -> bytes:
    cuerpo = json.loads(archivo_lote(lote_homogeneo_json(config=config or config_lote_json())))
    cuerpo["version_formato"] = 3
    cuerpo["homogeneo"].update(extra)
    return json.dumps(cuerpo).encode()


@pytest.mark.parametrize(
    ("cambios", "ruta"),
    [
        (
            {"redes": [{"bridge": "vmbr0", "modelo": "virtio", "vlan": None, "mtu": 100}]},
            "homogeneo.config.redes[0].mtu",
        ),
        (
            {"redes": [{"bridge": "vmbr0", "modelo": "virtio", "vlan": None, "mtu": 70000}]},
            "homogeneo.config.redes[0].mtu",
        ),
        (
            {"redes": [{"bridge": "vmbr0", "modelo": "virtio", "vlan": None, "mtu": "1500"}]},
            "homogeneo.config.redes[0].mtu",
        ),
        (
            {"redes": [{"bridge": "vmbr0", "modelo": "virtio", "vlan": None, "limite_mb": -1}]},
            "homogeneo.config.redes[0].limite_mb",
        ),
        (
            {"redes": [{"bridge": "vmbr0", "modelo": "virtio", "vlan": None, "limite_mb": 0}]},
            "homogeneo.config.redes[0].limite_mb",
        ),
        (
            {"redes": [{"bridge": "vmbr0", "modelo": "virtio", "vlan": None, "limite_mb": "5"}]},
            "homogeneo.config.redes[0].limite_mb",
        ),
        ({"pool": 5}, "homogeneo.config.pool"),
        ({"proteger": "sí"}, "homogeneo.config.proteger"),
        ({"encender": 1}, "homogeneo.config.encender"),
        ({"arranque_auto": "true"}, "homogeneo.config.arranque_auto"),
        ({"arranque_orden": -1}, "homogeneo.config.arranque_orden"),
        ({"arranque_orden": 2**31}, "homogeneo.config.arranque_orden"),
        ({"arranque_espera": "5"}, "homogeneo.config.arranque_espera"),
        ({"notas": 7}, "homogeneo.config.notas"),
        ({"notas": "x" * (MAX_LONG_NOTAS + 1)}, "homogeneo.config.notas"),
        ({"etiquetas_usuario": "web"}, "homogeneo.config.etiquetas_usuario"),
        ({"etiquetas_usuario": ["web", 3]}, "homogeneo.config.etiquetas_usuario[1]"),
        ({"etiquetas_usuario": ["con espacio"]}, "homogeneo.config.etiquetas_usuario[0]"),
        ({"etiquetas_usuario": ["a" * 129]}, "homogeneo.config.etiquetas_usuario[0]"),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_ca_a7_1_7_campo_nuevo_con_tipo_o_rango_erroneo_se_marca_con_su_ruta(cambios, ruta):
    datos = _archivo_v3(config_lote_json(**cambios))
    assert ruta in _rutas_error(datos)


@pytest.mark.parametrize("mtu", [1, 576, 1500, 9000, 65520, None])
def test_ca_a7_1_7_mtu_validos_se_aceptan(mtu):
    red = {"bridge": "vmbr0", "modelo": "virtio", "vlan": None, "mtu": mtu}
    cfg = leer_lote(_archivo_v3(config_lote_json(redes=[red]))).lote.definicion.plantilla
    assert cfg.redes[0].mtu == mtu


@pytest.mark.parametrize("mtu", [2, 575, 65521, 0, -1])
def test_ca_a7_1_7_mtu_fuera_de_1_o_576_a_65520_se_rechaza(mtu):
    red = {"bridge": "vmbr0", "modelo": "virtio", "vlan": None, "mtu": mtu}
    assert "homogeneo.config.redes[0].mtu" in _rutas_error(
        _archivo_v3(config_lote_json(redes=[red]))
    )


def test_ca_a7_1_7_nada_se_ejecuta_ni_se_devuelve_parcial():
    """Carga atómica: un campo malo invalida todo el lote (no hay lectura parcial)."""
    datos = _archivo_v3(config_lote_json(proteger="sí"))
    with pytest.raises(ErrorArchivo):
        leer_lote(datos)


def test_ca_a7_1_7_ruta_de_opciones_de_lote_y_de_fila():
    cuerpo = json.loads(_archivo_v3(opciones={"encender": "sí"}))
    assert "homogeneo.opciones.encender" in _rutas_error(json.dumps(cuerpo).encode())
    filas = [{"nombre": "a", "config": config_lote_json(), "opciones": {"proteger": "no"}}]
    cuerpo = json.loads(archivo_lote_por_filas(filas))
    cuerpo["version_formato"] = 3
    assert "por_filas.filas[0].opciones.proteger" in _rutas_error(json.dumps(cuerpo).encode())


# --- CA-A7.1.8: campos desconocidos -----------------------------------------------------------


def test_ca_a7_1_8_campos_desconocidos_en_v3_se_ignoran_con_aviso():
    config = config_lote_json(proteger=True, campo_del_futuro=1)
    archivo = leer_lote(_archivo_v3(config))
    assert archivo.lote.definicion.plantilla.proteger is True
    assert CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS in {a.codigo for a in archivo.avisos}


def test_ca_a7_1_8_los_avisos_no_incluyen_el_valor_ni_el_nombre_del_campo_desconocido():
    config = config_lote_json(campo_secreto_del_futuro="VALOR-SENSIBLE-123")
    archivo = leer_lote(_archivo_v3(config))
    texto = repr(archivo.avisos)
    assert "VALOR-SENSIBLE-123" not in texto


# --- CA-A7.1.9 / RNF-A2: credenciales en campos nuevos ----------------------------------------

TOKEN = "root@pam!lab=0a1b2c3d-1111-2222-3333-444455556666"


def test_ca_a7_1_9_un_token_en_las_notas_impide_guardar_el_lote():
    lote = _lote(notas=f"mi token es {TOKEN}")
    with pytest.raises(ErrorProxLaunch) as exc:
        lote_a_bytes(lote, app_version="0.6.0")
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    assert exc.value.params["motivo"] == "credencial"
    assert "0a1b2c3d" not in repr(exc.value.params)


@pytest.mark.parametrize("campo", ["pool", "etiquetas_usuario"])
def test_ca_a7_1_9_un_token_en_pool_o_etiquetas_impide_guardar(campo):
    valor = TOKEN if campo == "pool" else (TOKEN,)
    with pytest.raises(ErrorProxLaunch) as exc:
        lote_a_bytes(_lote(**{campo: valor}), app_version="0.6.0")
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


def test_ca_a7_1_9_un_token_en_notas_de_las_opciones_o_de_una_fila_impide_guardar():
    base = definicion(1, plantilla_vm=plantilla())
    con_lote = dataclasses.replace(base, opciones=OpcionesLote(notas=TOKEN))
    fila = FilaLote("a", plantilla(), opciones=OpcionesParciales(notas=TOKEN))
    por_filas = DefinicionLote(plantilla(), 1, PatronNombres(""), Destino(), filas=(fila,))
    for d in (con_lote, por_filas):
        with pytest.raises(ErrorProxLaunch) as exc:
            lote_a_bytes(LoteGuardado("x", d), app_version="0.6.0")
        assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


def test_ca_a7_1_9_un_archivo_de_terceros_con_token_en_notas_se_rechaza_al_leer():
    datos = _archivo_v3(config_lote_json(notas=f"x {TOKEN}"))
    assert "homogeneo.config.notas" in _rutas_error(datos)


def test_rnf_a2_el_error_de_credencial_no_filtra_el_secreto_ni_en_el_texto():
    with pytest.raises(ErrorProxLaunch) as exc:
        lote_a_bytes(_lote(notas=TOKEN), app_version="0.6.0")
    assert "0a1b2c3d" not in str(exc.value) + repr(exc.value.params) + exc.value.detalle_tecnico


def test_ca_a2_6_notas_con_caracteres_de_control_no_se_guardan_ni_se_leen():
    with pytest.raises(ErrorProxLaunch) as exc:
        lote_a_bytes(_lote(notas="a\x00b"), app_version="0.6.0")
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    assert "homogeneo.config.notas" in _rutas_error(_archivo_v3(config_lote_json(notas="a\x07b")))


def test_ca_a2_6_notas_conservan_saltos_de_linea_y_tabuladores():
    lote = _lote(notas="línea 1\n\tsangrada\nlínea 3")
    leido = leer_lote(lote_a_bytes(lote, app_version="0.6.0")).lote.definicion.plantilla
    assert leido.notas == "línea 1\n\tsangrada\nlínea 3"


# --- CA-A2.6.4 / CA-A1.4.5 / CA-A5.3.6: ida y vuelta de cada opción ---------------------------


def _ida_y_vuelta(cfg: ConfiguracionVM) -> ConfiguracionVM:
    lote = LoteGuardado("x", definicion(1, plantilla_vm=cfg))
    return leer_lote(lote_a_bytes(lote, app_version="0.6.0")).lote.definicion.plantilla


def test_ca_a2_6_4_notas_restaura_los_tres_valores():
    cfg = plantilla(notas_origen=True, notas_usuario=True, notas="Hola\nmundo % 20")
    leida = _ida_y_vuelta(cfg)
    assert (leida.notas_origen, leida.notas_usuario, leida.notas) == (
        True,
        True,
        "Hola\nmundo % 20",
    )


def test_ca_a1_4_5_encender_arranque_orden_y_espera_se_restauran():
    cfg = plantilla(encender=True, arranque_auto=True, arranque_orden=2, arranque_espera=45)
    leida = _ida_y_vuelta(cfg)
    assert (leida.encender, leida.arranque_auto) == (True, True)
    assert (leida.arranque_orden, leida.arranque_espera) == (2, 45)


def test_ca_a5_3_6_mtu_y_limite_ida_y_vuelta_integra():
    redes = [
        InterfazRed("vmbr0", ModeloRed.VIRTIO, 20, 9000, 50.0),
        InterfazRed("vmbr0", ModeloRed.E1000, None, None, 12.5),
        InterfazRed("vmbr0", ModeloRed.VIRTIO, None, 1, None),
    ]
    leida = _ida_y_vuelta(plantilla(redes=redes))
    assert leida.redes == redes


def test_ca_a7_1_ida_y_vuelta_de_etiquetas_pool_y_proteccion():
    leida = _ida_y_vuelta(plantilla(etiquetas_usuario=("web", "prod"), pool="lab", proteger=True))
    assert leida.etiquetas_usuario == ("web", "prod")
    assert (leida.pool, leida.proteger) == ("lab", True)


def test_ca_a7_1_la_etiqueta_fija_y_la_descripcion_calculada_nunca_se_serializan():
    cfg = plantilla(etiquetas=("proxlaunch", "lote-abcd1234"), descripcion="calculada")
    datos = lote_a_bytes(_lote(), app_version="0.6.0").decode()
    assert "calculada" not in datos
    leida = _ida_y_vuelta(cfg)
    assert leida.etiquetas == () and leida.descripcion is None


# --- CA-A7.4.1: propiedad de ida y vuelta con opciones aleatorias -----------------------------


def _normalizada(cfg: ConfiguracionVM) -> ConfiguracionVM:
    """Lo que sobrevive a un guardado (sin vmid, nombre, nodo ni etiquetas de propiedad)."""
    return dataclasses.replace(
        copy.deepcopy(cfg), vmid=0, nombre="", nodo="", etiquetas=(), descripcion=None
    )


def _parciales_efectivas(op: OpcionesParciales | None) -> OpcionesParciales | None:
    return None if op in (None, OpcionesParciales()) else op


@pytest.mark.parametrize("filas", [False, True], ids=["homogeneo", "por_filas"])
def test_ca_a7_4_1_ida_y_vuelta_con_opciones_aleatorias(filas):
    rng = random.Random(SEMILLA + int(filas))
    for _ in range(150):
        d = lote_aleatorio(rng, filas)
        datos = lote_a_bytes(LoteGuardado("rnd", d), app_version="0.6.0")
        leida = leer_lote(datos).lote.definicion
        if filas:
            assert len(leida.filas) == len(d.filas)
            for orig, vuelta in zip(d.filas, leida.filas, strict=True):
                assert vuelta.cfg == _normalizada(orig.cfg)
                assert _parciales_efectivas(vuelta.opciones) == _parciales_efectivas(orig.opciones)
        else:
            assert leida.plantilla == _normalizada(d.plantilla)
            assert leida.cantidad == d.cantidad
        # y la relectura del archivo reescrito es idéntica byte a byte (estabilidad)
        assert lote_a_bytes(LoteGuardado("rnd", leida), app_version="0.6.0") == datos


def test_ca_a7_4_1_opciones_de_lote_aleatorias_sobreviven():
    rng = random.Random(SEMILLA + 7)
    for _ in range(100):
        op = OpcionesLote(
            encender=rng.random() < 0.5,
            arranque_auto=rng.random() < 0.5,
            notas=rng.choice(["", "n1\nn2", "ñandú"]),
            etiquetas_usuario=rng.choice([(), ("a",), ("a", "b")]),
            pool=rng.choice([None, "p1"]),
            proteger=rng.random() < 0.5,
            notas_origen=rng.random() < 0.5,
            notas_usuario=rng.random() < 0.5,
        )
        base = definicion(2, plantilla_vm=plantilla())
        d = dataclasses.replace(base, opciones=op)
        leida = leer_lote(lote_a_bytes(LoteGuardado("x", d), app_version="0.6.0")).lote.definicion
        efectivas = leida.opciones or OpcionesLote.desde_config(leida.plantilla)
        assert efectivas == op


# --- CA-A7.1.10 / CL-A9: tamaño ---------------------------------------------------------------


def _lote_de_100_con_notas(largo: int, doble: bool = False) -> LoteGuardado:
    filas = tuple(
        FilaLote(
            f"vm-{i:03d}",
            plantilla(notas="x" * largo, etiquetas_usuario=("web", "prod")),
            None,
            None,
            i + 2,
            OpcionesParciales(notas="y" * largo) if doble else None,
        )
        for i in range(100)
    )
    return LoteGuardado(
        "grande", DefinicionLote(plantilla(), 100, PatronNombres(""), Destino(), filas=filas)
    )


def test_ca_a7_1_10_cien_filas_con_notas_de_7500_caracteres_caben_en_1_mib(tmp_path):
    lote = _lote_de_100_con_notas(7500)
    ruta = tmp_path / "grande.json"
    guardar_lote(ruta, lote, app_version="0.6.0")
    assert 700_000 < ruta.stat().st_size < MAX_BYTES_LOTE
    leido = leer_archivo_lote(ruta).lote.definicion
    assert len(leido.filas) == 100
    assert all(len(f.cfg.notas) == 7500 for f in leido.filas)


def test_ca_a7_1_10_un_lote_que_excede_1_mib_produce_un_error_claro_de_tamano(tmp_path):
    lote = _lote_de_100_con_notas(MAX_LONG_NOTAS, doble=True)
    ruta = tmp_path / "enorme.json"
    ruta.write_bytes(lote_a_bytes(lote, app_version="0.6.0"))
    assert ruta.stat().st_size > MAX_BYTES_LOTE
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_lote(ruta)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert exc.value.params["motivo"] == "demasiado_grande"
    assert exc.value.params["limite"] == str(MAX_BYTES_LOTE)


def test_cl_a9_comprobar_cien_maquinas_con_notas_largas_y_etiquetas_es_rapido(inv):
    lote = _lote_de_100_con_notas(7500)
    t0 = time.perf_counter()
    for f in lote.definicion.filas:
        validar_sin_servidor(dataclasses.replace(f.cfg, nombre=f.nombre))
    assert time.perf_counter() - t0 < 10
