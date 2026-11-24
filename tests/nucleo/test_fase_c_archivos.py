"""Fase C (0.8.0): formato v5 de lotes guardados (RF-C6.1, RF-C6.4, RF-C0.2/C0.3 en archivos).

Cubre CA-C6.1.1 a CA-C6.1.10, CA-C6.4.1 y la propiedad de ida y vuelta con generación aleatoria
(semilla fija: el repositorio no usa ``hypothesis``). Los archivos ``p4_*-070-*`` de
``tests/datos/fase_c`` los escribió el código de 0.7.0 (``p4_generar_datos.py``): con ellos se
comprueba que 0.8.0 los abre igual y que, al regrabarlos, salen byte a byte iguales y sin subir de
versión (un lote sin nada de la fase C se escribe como en 0.7.0).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import random
from pathlib import Path

import pytest

import proxlaunch
from proxlaunch.nucleo.archivos.constantes import (
    VERSION_FORMATO,
    VERSION_FORMATO_FASE_A,
    VERSION_FORMATO_FASE_B,
    VERSION_FORMATO_FASE_C,
)
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo, ErrorArchivo, MotivoCampo
from proxlaunch.nucleo.cloudinit.modelos import (
    ConfigCloudInit,
    ModoTarjeta,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import (
    FirewallMV,
    FirewallParcial,
    GrupoSeguridad,
    InfoFirewall,
    ModoDhcp,
    Politica,
)
from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, FilaLote, PatronNombres
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.lotes_guardados.formato import (
    leer_archivo_lote,
    leer_lote,
    lote_a_bytes,
    lote_a_dict,
    version_para,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco
from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales
from proxlaunch.nucleo.red.modelos import (
    AccionTarjeta,
    CampoRed,
    ModoRedClon,
    RedClon,
    TarjetaClon,
)

from .apoyo_lote import definicion, plantilla
from .apoyo_mvp3 import DATOS_MVP3
from .apoyo_mvp4 import inv_origen

DATOS_C = Path(__file__).resolve().parent.parent / "datos" / "fase_c"
DATOS_B = Path(__file__).resolve().parent.parent / "datos" / "fase_b"
DATOS_A = Path(__file__).resolve().parent.parent / "datos" / "fase_a_p2"
SEMILLA = 20261122
TOKEN = "root@pam!lab=0a1b2c3d-1111-2222-3333-444455556666"
Campo = CampoRed

CI_SIMPLE = ConfigCloudInit(usuario="deploy")
FW_ACTIVO = FirewallMV(activo=True, grupo="web-01", politica_entrada=Politica.PERMITIR)
RED_CAMBIAR = RedClon(
    ModoRedClon.PERSONALIZAR,
    (
        TarjetaClon(
            0,
            AccionTarjeta.CAMBIAR,
            bridge="prod",
            vlan=20,
            fijados=frozenset({Campo.BRIDGE, Campo.VLAN}),
        ),
    ),
)


def lote_c(cantidad: int = 2, **cfg) -> LoteGuardado:
    return LoteGuardado("Lote C", definicion(cantidad, plantilla_vm=plantilla(**cfg)))


def bytes_de(lote: LoteGuardado) -> bytes:
    return lote_a_bytes(lote, app_version="0.8.0")


def cuerpo_de(lote: LoteGuardado) -> dict:
    return json.loads(bytes_de(lote))


def version_escrita(lote: LoteGuardado) -> int:
    return cuerpo_de(lote)["version_formato"]


def mutar(datos: bytes, fn) -> bytes:
    cuerpo = json.loads(datos)
    fn(cuerpo)
    return json.dumps(cuerpo).encode()


def rutas_error(datos: bytes) -> list[tuple[str, MotivoCampo]]:
    with pytest.raises(ErrorArchivo) as exc:
        leer_lote(datos)
    return [(e.ruta, e.motivo) for e in exc.value.errores]


def cfg_json(cuerpo: dict) -> dict:
    return cuerpo["homogeneo"]["config"]


def leido(lote: LoteGuardado) -> LoteGuardado:
    return leer_lote(bytes_de(lote)).lote


# --- Versión 0.8.0 y constantes ---


def test_la_version_del_paquete_es_0_9_0():
    assert proxlaunch.__version__ == "0.9.0"


def test_rf_c6_1_la_version_maxima_es_6_y_la_de_las_fases_b_y_a_siguen_en_4_y_3():
    # Fase D (RF-D6.1): la máxima sube a 6; el escalón de la fase C sigue siendo 5.
    assert VERSION_FORMATO == 6
    assert VERSION_FORMATO_FASE_C == 5
    assert VERSION_FORMATO_FASE_B == 4
    assert VERSION_FORMATO_FASE_A == 3


# --- CA-C6.1.3: la versión mínima posible ---


def test_ca_c6_1_3_un_lote_sin_opciones_de_la_fase_c_se_escribe_en_v1():
    from proxlaunch.nucleo.modelos.vm import InterfazRed

    lote = lote_c(redes=[InterfazRed("vmbr0")])
    assert version_escrita(lote) == 1


def test_ca_c6_1_3_el_firewall_y_la_red_por_defecto_no_suben_la_version_ni_se_escriben():
    lote = lote_c(firewall=FirewallMV(), red_clon=RedClon(), proteger=True)
    cuerpo = cuerpo_de(lote)
    assert cuerpo["version_formato"] == 3  # solo por «proteger» (fase A)
    assert "firewall" not in cfg_json(cuerpo) and "red_clon" not in cfg_json(cuerpo)


def test_ca_c6_1_3_un_lote_solo_de_la_fase_b_se_escribe_en_v4_no_en_v5():
    lote = lote_c(cloudinit=CI_SIMPLE, esperar_ip=True, encender=True)
    assert version_escrita(lote) == 4
    lote_ops = LoteGuardado(
        "x",
        dataclasses.replace(
            definicion(2, plantilla_vm=plantilla()), opciones=OpcionesLote(esperar_ip=True)
        ),
    )
    assert version_para(lote_ops) == 4


def test_ca_c6_1_3_un_lote_solo_de_la_fase_a_se_escribe_en_v3():
    assert version_escrita(lote_c(proteger=True)) == 3


def test_ca_c6_1_3_las_claves_de_la_fase_c_no_se_escriben_si_no_se_usan():
    texto = json.dumps(cuerpo_de(lote_c(cloudinit=CI_SIMPLE)))
    for clave in ("red_clon", "firewall", "politica_entrada", "acepto_aislada"):
        assert clave not in texto


# --- CA-C6.1.4: qué obliga a v5 ---


@pytest.mark.parametrize(
    "cambios",
    [
        {"firewall": FirewallMV(activo=True)},
        {"firewall": FirewallMV(activo=True, grupo="web")},
        {"firewall": FirewallMV(politica_entrada=Politica.PERMITIR)},
        {"firewall": FirewallMV(politica_salida=Politica.BLOQUEAR)},
        {"firewall": FirewallMV(dhcp=ModoDhcp.NO)},
        {"firewall": FirewallMV(acepto_aislada=True)},
        {"red_clon": RED_CAMBIAR},
        {"red_clon": RedClon(ModoRedClon.PERSONALIZAR, (TarjetaClon(1, AccionTarjeta.QUITAR),))},
        {
            "red_clon": RedClon(
                ModoRedClon.PERSONALIZAR, (TarjetaClon(2, AccionTarjeta.ANADIR, bridge="vmbr1"),)
            )
        },
    ],
    ids=["activo", "grupo", "entrada", "salida", "dhcp", "acepto", "cambiar", "quitar", "anadir"],
)
def test_ca_c6_1_4_cada_opcion_de_la_fase_c_obliga_a_v5(cambios):
    assert version_escrita(lote_c(**cambios)) == 5


def test_ca_c6_1_4_c_junto_con_a_y_b_tambien_es_v5():
    lote = lote_c(firewall=FW_ACTIVO, cloudinit=CI_SIMPLE, esperar_ip=True, proteger=True)
    assert version_escrita(lote) == 5


def test_ca_c6_1_4_las_opciones_de_lote_con_firewall_o_red_obligan_a_v5():
    base = definicion(2, plantilla_vm=plantilla())
    con_fw = dataclasses.replace(base, opciones=OpcionesLote(firewall=FW_ACTIVO))
    con_red = dataclasses.replace(base, opciones=OpcionesLote(red_clon=RED_CAMBIAR))
    assert version_para(LoteGuardado("x", con_fw)) == 5
    assert version_para(LoteGuardado("x", con_red)) == 5
    sin = dataclasses.replace(
        base, opciones=OpcionesLote(firewall=FirewallMV(), red_clon=RedClon())
    )
    assert version_para(LoteGuardado("x", sin)) == 1


def test_ca_c6_1_4_las_celdas_de_firewall_de_una_fila_obligan_a_v5_y_vacias_no():
    def con_fila(opciones):
        filas = (FilaLote("a", plantilla()), FilaLote("b", plantilla(), None, None, None, opciones))
        return LoteGuardado(
            "x", DefinicionLote(plantilla(), 2, PatronNombres(""), Destino(), filas=filas)
        )

    assert version_para(con_fila(OpcionesParciales(firewall=FirewallParcial(activo=True)))) == 5
    assert version_para(con_fila(OpcionesParciales(firewall=FirewallParcial(grupo="web")))) == 5
    assert version_para(con_fila(OpcionesParciales(red_clon=RedClon()))) == 5
    assert version_para(con_fila(OpcionesParciales(firewall=FirewallParcial()))) == 1
    assert version_para(con_fila(OpcionesParciales(encender=True))) == 3  # fase A, no C


# --- Archivos de 0.7.0 (v1, v3, v4): CA-C6.1.1, CA-C6.1.2, CA-C6.4.1 ---

ARCHIVOS_070 = [
    ("p4_lote-homogeneo-070-v1.json", 1),
    ("p4_lote-homogeneo-070-v3.json", 3),
    ("p4_lote-homogeneo-070-v4.json", 4),
    ("p4_lote-por-filas-070-v4.json", 4),
]
ARCHIVOS_051 = [
    (DATOS_A / "lote-homogeneo-051-v1.json", 1),
    (DATOS_A / "lote-homogeneo-051-v2.json", 2),
    (DATOS_A / "lote-por-filas-051-v2.json", 2),
    (DATOS_B / "p2_lote-homogeneo-060-v3.json", 3),
    (DATOS_B / "p2_lote-por-filas-060-v3.json", 3),
]


def cfgs_de(lote: LoteGuardado) -> list[ConfiguracionVM]:
    d = lote.definicion
    return [f.cfg for f in d.filas] if d.es_por_filas else [d.plantilla]


@pytest.mark.parametrize(("nombre", "version"), ARCHIVOS_070)
def test_ca_c6_1_1_los_lotes_de_070_se_leen_con_los_campos_de_c_por_defecto_y_sin_aviso(
    nombre, version
):
    archivo = leer_archivo_lote(DATOS_C / nombre)
    assert archivo.version_original == version
    assert archivo.avisos == ()  # sin MIGRADO ni otro ruido
    for cfg in cfgs_de(archivo.lote):
        assert cfg.firewall is None and cfg.red_clon is None
    d = archivo.lote.definicion
    if d.opciones is not None:
        assert d.opciones.firewall is None and d.opciones.red_clon is None
    for f in d.filas:
        assert f.opciones is None or (f.opciones.firewall is None and f.opciones.red_clon is None)


@pytest.mark.parametrize(("nombre", "_v"), ARCHIVOS_070)
def test_ca_c6_1_2_lo_que_lee_080_de_un_lote_de_070_es_lo_que_leia_070(nombre, _v):
    esperado = json.loads((DATOS_C / nombre.replace(".json", ".esperado.json")).read_text())
    lote = leer_archivo_lote(DATOS_C / nombre).lote
    assert json.loads(json.dumps(lote_a_dict(lote), sort_keys=True)) == esperado


@pytest.mark.parametrize(("nombre", "version"), ARCHIVOS_070)
def test_ca_c6_4_1_la_ida_y_vuelta_de_un_lote_de_070_es_identica_byte_a_byte(nombre, version):
    original = (DATOS_C / nombre).read_bytes()
    lote = leer_archivo_lote(DATOS_C / nombre).lote
    regrabado = lote_a_bytes(lote, app_version="0.7.0")
    assert regrabado == original
    assert json.loads(regrabado)["version_formato"] == version  # 0.7.0 vuelve a abrirlo


@pytest.mark.parametrize(("ruta", "version"), ARCHIVOS_051, ids=lambda x: getattr(x, "name", x))
def test_ca_c6_4_1_los_lotes_de_051_y_060_se_abren_y_se_regraban_iguales(ruta, version):
    original = json.loads(ruta.read_text())
    archivo = leer_archivo_lote(ruta)
    assert archivo.version_original == version and archivo.avisos == ()
    regrabado = json.loads(lote_a_bytes(archivo.lote, app_version=original["app_version"]))
    assert regrabado == original


@pytest.mark.parametrize("nombre", sorted(p.name for p in DATOS_MVP3.glob("lote-*-v1.json")))
def test_ca_c6_4_1_los_lotes_de_mvp3_siguen_siendo_v1(nombre):
    archivo = leer_archivo_lote(DATOS_MVP3 / nombre)
    assert archivo.avisos == () and version_para(archivo.lote) == 1


def test_ca_c6_1_2_la_planificacion_de_un_lote_migrado_no_trae_nada_de_c():
    lote = leer_archivo_lote(DATOS_C / "p4_lote-homogeneo-070-v3.json").lote
    from .apoyo_lote import inventario

    plan = construir_plan(
        lote.definicion, inventario(), [100, 101], [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip
    assert not [p for p in plan.problemas if p.regla.startswith("V-C")]
    assert all(e.cfg.firewall is None and e.cfg.red_clon is None for e in plan.elementos)


# --- CA-C6.1.5: versión futura ---


def test_ca_c6_1_5_un_archivo_v7_se_rechaza_como_version_futura_y_no_cambia():
    datos = mutar(bytes_de(lote_c(firewall=FW_ACTIVO)), lambda c: c.update(version_formato=7))
    copia = bytes(datos)
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_lote(datos)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert exc.value.params["version_archivo"] == "7"
    assert exc.value.params["version_soportada"] == "6"
    assert datos == copia


def test_ca_c6_1_5_un_archivo_v5_se_abre_y_el_v100_tambien_es_futuro(tmp_path):
    assert leer_lote(bytes_de(lote_c(firewall=FW_ACTIVO))).version_original == 5
    ruta = tmp_path / "futuro.json"
    ruta.write_bytes(
        mutar(bytes_de(lote_c(firewall=FW_ACTIVO)), lambda c: c.update(version_formato=100))
    )
    antes = ruta.read_bytes()
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_lote(ruta)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert ruta.read_bytes() == antes


# --- CA-C6.1.8: ida y vuelta ---


def test_ca_c6_1_8_ida_y_vuelta_de_la_configuracion_con_todas_las_opciones_de_c():
    red = RedClon(
        ModoRedClon.PERSONALIZAR,
        (
            TarjetaClon(
                0,
                AccionTarjeta.CAMBIAR,
                bridge="prod",
                modelo="e1000",
                vlan=20,
                mtu=1500,
                limite_mb=12.5,
                fijados=frozenset(Campo),
                mac_nueva=True,
            ),
            TarjetaClon(1, AccionTarjeta.QUITAR),
            TarjetaClon(
                2,
                AccionTarjeta.ANADIR,
                bridge="vmbr1",
                modelo="virtio",
                vlan=5,
                mtu=1,
                limite_mb=3.0,
            ),
        ),
    )
    fw = FirewallMV(True, "web-01", Politica.BLOQUEAR, Politica.BLOQUEAR, ModoDhcp.SI, True)
    lote = lote_c(red_clon=red, firewall=fw)
    de_vuelta = leido(lote)
    assert de_vuelta.definicion.plantilla.red_clon == red
    # ``acepto_aislada`` no se guarda en el archivo (SEG-C-B2): al leer queda sin marcar.
    assert de_vuelta.definicion.plantilla.firewall == dataclasses.replace(fw, acepto_aislada=False)
    assert lote_a_dict(de_vuelta) == lote_a_dict(lote)
    assert bytes_de(de_vuelta) == bytes_de(lote)


def test_ca_c6_1_8_cambiar_distingue_quitar_un_valor_null_de_conservarlo_ausente():
    red = RedClon(
        ModoRedClon.PERSONALIZAR,
        (
            TarjetaClon(0, AccionTarjeta.CAMBIAR, vlan=None, fijados=frozenset({Campo.VLAN})),
            TarjetaClon(1, AccionTarjeta.CAMBIAR, bridge="x", fijados=frozenset({Campo.BRIDGE})),
        ),
    )
    t = cfg_json(cuerpo_de(lote_c(red_clon=red)))["red_clon"]["tarjetas"]
    assert t[0]["vlan"] is None and "vlan" in t[0]
    assert "vlan" not in t[1]
    vuelta = leido(lote_c(red_clon=red)).definicion.plantilla.red_clon
    assert vuelta.tarjetas[0].fijados == frozenset({Campo.VLAN})
    assert vuelta.tarjetas[1].fijados == frozenset({Campo.BRIDGE})


def test_ca_c6_1_8_ida_y_vuelta_de_las_opciones_de_lote_y_de_fila():
    ops = OpcionesLote(firewall=FW_ACTIVO, red_clon=RED_CAMBIAR, encender=True)
    filas = (
        FilaLote("a", plantilla()),
        FilaLote(
            "b",
            plantilla(),
            None,
            None,
            None,
            OpcionesParciales(
                firewall=FirewallParcial(True, "db-01", Politica.BLOQUEAR, Politica.PERMITIR),
                red_clon=RedClon(),
            ),
        ),
        FilaLote(
            "c",
            plantilla(),
            None,
            None,
            None,
            OpcionesParciales(firewall=FirewallParcial(activo=False), red_clon=RED_CAMBIAR),
        ),
    )
    lote = LoteGuardado(
        "x", DefinicionLote(plantilla(), 3, PatronNombres(""), Destino(), filas=filas, opciones=ops)
    )
    assert version_escrita(lote) == 5
    de_vuelta = leido(lote)
    assert de_vuelta.definicion.opciones == ops or (
        de_vuelta.definicion.opciones.firewall == FW_ACTIVO
        and de_vuelta.definicion.opciones.red_clon == RED_CAMBIAR
    )
    assert [f.opciones for f in de_vuelta.definicion.filas][1:] == [f.opciones for f in filas][1:]
    assert bytes_de(de_vuelta) == bytes_de(lote)


def _tarjeta_aleatoria(rnd: random.Random, indice: int) -> TarjetaClon:
    accion = rnd.choice(list(AccionTarjeta))
    if accion == AccionTarjeta.QUITAR or accion == AccionTarjeta.CONSERVAR:
        return TarjetaClon(indice, accion)
    valores = {
        Campo.BRIDGE: rnd.choice(["vmbr0", "prod", "dc1-vnet", None]),
        Campo.MODELO: rnd.choice(["virtio", "e1000", None]),
        Campo.VLAN: rnd.choice([1, 20, 4094, None]),
        Campo.MTU: rnd.choice([1, 576, 1500, 9000, None]),
        Campo.LIMITE: rnd.choice([0.5, 10.0, 125.5, None]),
    }
    if accion == AccionTarjeta.ANADIR:
        fijados: frozenset[Campo] = frozenset()
    else:
        fijados = frozenset(c for c in Campo if rnd.random() < 0.5)
        valores = {c: (v if c in fijados else None) for c, v in valores.items()}
        # Un campo fijado a ``None`` se quita; uno no fijado no puede traer valor.
    return TarjetaClon(
        indice,
        accion,
        valores[Campo.BRIDGE],
        valores[Campo.MODELO],
        valores[Campo.VLAN],
        valores[Campo.MTU],
        valores[Campo.LIMITE],
        fijados,
        mac_nueva=rnd.random() < 0.3,
    )


def test_ca_c6_1_8_ida_y_vuelta_aleatoria_con_semilla_fija():
    rnd = random.Random(SEMILLA)
    for _ in range(60):
        indices = rnd.sample(range(32), rnd.randint(1, 4))
        red = RedClon(
            ModoRedClon.PERSONALIZAR,
            tuple(_tarjeta_aleatoria(rnd, i) for i in sorted(indices)),
        )
        fw = FirewallMV(
            rnd.random() < 0.7,
            rnd.choice([None, "web-01", "ab", "G_" + "x" * 16]),
            rnd.choice(list(Politica)),
            rnd.choice(list(Politica)),
            rnd.choice(list(ModoDhcp)),
            rnd.random() < 0.5,
        )
        lote = lote_c(red_clon=red, firewall=fw)
        datos = bytes_de(lote)
        de_vuelta = leer_lote(datos).lote
        assert de_vuelta.definicion.plantilla.red_clon == (red if red.tarjetas else RedClon())
        fw = dataclasses.replace(fw, acepto_aislada=False)  # no se guarda (SEG-C-B2)
        esperado_fw = fw if fw != FirewallMV() else None
        assert (de_vuelta.definicion.plantilla.firewall or None) == esperado_fw
        assert bytes_de(de_vuelta) == datos


# --- CA-C6.1.6: tipos y rangos erróneos, con la ruta del campo ---


def v5() -> bytes:
    return bytes_de(
        lote_c(
            firewall=FW_ACTIVO,
            red_clon=RedClon(
                ModoRedClon.PERSONALIZAR,
                (
                    TarjetaClon(
                        0,
                        AccionTarjeta.CAMBIAR,
                        bridge="prod",
                        vlan=20,
                        fijados=frozenset({Campo.BRIDGE, Campo.VLAN}),
                    ),  # fmt: skip
                    TarjetaClon(1, AccionTarjeta.QUITAR),
                ),
            ),
        )
    )


def fw_j(c):
    return cfg_json(c)["firewall"]


def red_j(c):
    return cfg_json(c)["red_clon"]


def tar_j(c, i=0):
    return red_j(c)["tarjetas"][i]


FW = "firewall."
TJ = "red_clon.tarjetas[0]."
CASOS_INVALIDOS = [
    (
        "politica_entrada",
        lambda c: fw_j(c).update(politica_entrada="rechazar"),
        FW + "politica_entrada",
        MotivoCampo.ENUM,
    ),
    (
        "politica_salida",
        lambda c: fw_j(c).update(politica_salida="x"),
        FW + "politica_salida",
        MotivoCampo.ENUM,
    ),
    ("vlan", lambda c: tar_j(c).update(vlan=5000), TJ + "vlan", MotivoCampo.RANGO),
    ("vlan0", lambda c: tar_j(c).update(vlan=0), TJ + "vlan", MotivoCampo.RANGO),
    ("vlan_texto", lambda c: tar_j(c).update(vlan="20"), TJ + "vlan", MotivoCampo.TIPO),
    ("indice", lambda c: tar_j(c).update(indice=-1), TJ + "indice", MotivoCampo.RANGO),
    ("indice32", lambda c: tar_j(c).update(indice=32), TJ + "indice", MotivoCampo.RANGO),
    ("grupo", lambda c: fw_j(c).update(grupo=5), FW + "grupo", MotivoCampo.TIPO),
    (
        "grupo_formato",
        lambda c: fw_j(c).update(grupo="1abc"),
        FW + "grupo",
        MotivoCampo.TEXTO_NO_VALIDO,
    ),
    ("grupo_corto", lambda c: fw_j(c).update(grupo="a"), FW + "grupo", MotivoCampo.TEXTO_NO_VALIDO),
    (
        "grupo_largo",
        lambda c: fw_j(c).update(grupo="a" * 19),
        FW + "grupo",
        MotivoCampo.TEXTO_NO_VALIDO,
    ),
    ("activo", lambda c: fw_j(c).update(activo="si"), FW + "activo", MotivoCampo.TIPO),
    ("dhcp", lambda c: fw_j(c).update(dhcp="x"), FW + "dhcp", MotivoCampo.ENUM),
    ("modo", lambda c: red_j(c).update(modo="otro"), "red_clon.modo", MotivoCampo.ENUM),
    ("accion", lambda c: tar_j(c).update(accion="borrar"), TJ + "accion", MotivoCampo.ENUM),
    ("modelo", lambda c: tar_j(c).update(modelo="ne2k"), TJ + "modelo", MotivoCampo.ENUM),
    ("mtu", lambda c: tar_j(c).update(mtu=575), TJ + "mtu", MotivoCampo.RANGO),
    ("limite", lambda c: tar_j(c).update(limite_mb=-1), TJ + "limite_mb", MotivoCampo.RANGO),
    ("bridge", lambda c: tar_j(c).update(bridge="a b"), TJ + "bridge", MotivoCampo.TEXTO_NO_VALIDO),
    (
        "duplicado",
        lambda c: tar_j(c, 1).update(indice=0),
        "red_clon.tarjetas[1].indice",
        MotivoCampo.DUPLICADO,
    ),
    (
        "tarjetas",
        lambda c: red_j(c).update(tarjetas=[{"indice": i, "accion": "quitar"} for i in range(33)]),
        "red_clon.tarjetas",
        MotivoCampo.DEMASIADOS,
    ),
]


@pytest.mark.parametrize(
    ("mutacion", "campo", "motivo"),
    [c[1:] for c in CASOS_INVALIDOS],
    ids=[c[0] for c in CASOS_INVALIDOS],
)
def test_ca_c6_1_6_un_v5_con_tipos_o_rangos_erroneos_se_marca_invalido_con_la_ruta(
    mutacion, campo, motivo
):
    assert rutas_error(mutar(v5(), mutacion)) == [(f"homogeneo.config.{campo}", motivo)]


def test_ca_c6_1_6_el_error_no_ejecuta_nada_y_el_lector_no_devuelve_un_lote_parcial():
    datos = mutar(v5(), lambda c: tar_j(c).update(vlan=5000))
    with pytest.raises(ErrorArchivo) as exc:
        leer_lote(datos)
    assert exc.value.errores  # el error es una excepción: no hay lote que ejecutar


def test_ca_c6_1_6_los_errores_se_acumulan_y_cada_uno_nombra_su_ruta():
    def dos(c):
        fw_j(c).update(politica_entrada="rechazar", grupo=5)
        tar_j(c).update(vlan=5000)

    rutas = {r for r, _ in rutas_error(mutar(v5(), dos))}
    assert rutas == {
        "homogeneo.config.firewall.politica_entrada",
        "homogeneo.config.firewall.grupo",
        "homogeneo.config.red_clon.tarjetas[0].vlan",
    }


def test_ca_c6_1_6_los_errores_de_las_opciones_de_lote_y_de_fila_nombran_su_ruta():
    ops = OpcionesLote(firewall=FW_ACTIVO, red_clon=RED_CAMBIAR)
    fila = OpcionesParciales(firewall=FirewallParcial(True, "web", Politica.BLOQUEAR))
    filas = (FilaLote("a", plantilla(), None, None, None, fila),)
    lote = LoteGuardado(
        "x", DefinicionLote(plantilla(), 1, PatronNombres(""), Destino(), filas=filas, opciones=ops)
    )
    datos = bytes_de(lote)

    def romper(c):
        pf = c["por_filas"]
        pf["opciones"]["firewall"]["politica_entrada"] = "x"
        pf["opciones"]["red_clon"]["tarjetas"][0]["vlan"] = 9999
        pf["filas"][0]["opciones"]["firewall"]["politica_salida"] = "y"

    rutas = {r for r, _ in rutas_error(mutar(datos, romper))}
    assert rutas == {
        "por_filas.opciones.firewall.politica_entrada",
        "por_filas.opciones.red_clon.tarjetas[0].vlan",
        "por_filas.filas[0].opciones.firewall.politica_salida",
    }


# --- CA-C6.1.7: campos desconocidos ---


@pytest.mark.parametrize("destino", ["firewall", "red_clon", "tarjeta"])
def test_ca_c6_1_7_los_campos_desconocidos_se_ignoran_con_aviso(destino):
    def anadir(c):
        {"firewall": fw_j, "red_clon": red_j, "tarjeta": tar_j}[destino](c)["futuro"] = 1

    archivo = leer_lote(mutar(v5(), anadir))
    assert CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS in {a.codigo for a in archivo.avisos}
    assert archivo.lote.definicion.plantilla.firewall == FW_ACTIVO


# --- CA-C6.1.9: el grupo ya no existe al reabrir ---


def test_ca_c6_1_9_un_grupo_que_ya_no_existe_da_v_c30_al_comprobar_y_no_crea_nada():
    lote = leido(lote_c(firewall=FW_ACTIVO, discos=[Disco("local-lvm", 32)]))
    inv = inv_origen()
    inv.catalogo = dataclasses.replace(
        inv.catalogo,
        firewall=InfoFirewall(grupos=(GrupoSeguridad("otro"),), general_activo=True),
    )
    plan = construir_plan(
        lote.definicion, inv, [100, 101], [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip
    v_c30 = [p for p in plan.problemas if p.regla == "V-C30"]
    assert v_c30 and v_c30[0].params["grupo"] == "web-01"
    assert plan.bloqueado


def test_ca_c6_1_9_con_el_grupo_presente_no_hay_v_c30():
    lote = leido(lote_c(firewall=FW_ACTIVO, discos=[Disco("local-lvm", 32)]))
    inv = inv_origen()
    inv.catalogo = dataclasses.replace(
        inv.catalogo,
        firewall=InfoFirewall(
            grupos=(GrupoSeguridad("web-01"),),
            general_activo=True,
            entrada_por_grupo={"web-01": True},
        ),
    )
    plan = construir_plan(
        lote.definicion, inv, [100, 101], [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip
    assert not [p for p in plan.problemas if p.regla == "V-C30"]


# --- CA-C6.1.10: textos con aspecto de token ---


@pytest.mark.parametrize(
    "cambios",
    [
        {"firewall": FirewallMV(activo=True, grupo=TOKEN)},
        {
            "red_clon": RedClon(
                ModoRedClon.PERSONALIZAR,
                (
                    TarjetaClon(
                        0, AccionTarjeta.CAMBIAR, bridge=TOKEN, fijados=frozenset({Campo.BRIDGE})
                    ),
                ),
            )
        },
    ],
    ids=["grupo", "bridge"],
)
def test_ca_c6_1_10_el_guardado_rechaza_textos_con_aspecto_de_token(cambios):
    with pytest.raises(ErrorProxLaunch) as exc:
        bytes_de(lote_c(**cambios))
    assert exc.value.codigo in (CodigoError.ARCHIVO_NO_GUARDABLE, CodigoError.PARAMETRO_INVALIDO)
    assert TOKEN not in json.dumps(exc.value.params)


def test_ca_c6_1_10_un_grupo_o_bridge_invalido_no_se_guarda_en_las_opciones_de_fila():
    fila = OpcionesParciales(firewall=FirewallParcial(True, "1mal"))
    filas = (FilaLote("a", plantilla(), None, None, None, fila),)
    lote = LoteGuardado(
        "x", DefinicionLote(plantilla(), 1, PatronNombres(""), Destino(), filas=filas)
    )
    with pytest.raises(ErrorProxLaunch) as exc:
        bytes_de(lote)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


def test_ca_c6_1_10_una_vlan_fuera_de_rango_no_se_guarda():
    red = RedClon(
        ModoRedClon.PERSONALIZAR,
        (TarjetaClon(0, AccionTarjeta.CAMBIAR, vlan=5000, fijados=frozenset({Campo.VLAN})),),
    )
    with pytest.raises(ErrorProxLaunch) as exc:
        bytes_de(lote_c(red_clon=red))
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


# --- RF-C6.1: el archivo no lleva datos del servidor ni secretos ---


def test_rf_c6_1_el_archivo_v5_solo_lleva_la_lista_blanca():
    texto = bytes_de(lote_c(firewall=FW_ACTIVO, red_clon=RED_CAMBIAR)).decode()
    for prohibido in ("digest", "mac", "MAC", "password", "contrasena", "token", "upid"):
        assert prohibido not in texto, prohibido
    cuerpo = json.loads(texto)
    assert set(fw_j(cuerpo)) <= {
        "activo", "grupo", "politica_entrada", "politica_salida", "dhcp", "acepto_aislada",
    }  # fmt: skip
    assert set(tar_j(cuerpo)) <= {
        "indice", "accion", "bridge", "modelo", "vlan", "mtu", "limite_mb", "mac_nueva",
    }  # fmt: skip


def test_rf_c6_1_un_lote_c_no_modifica_el_objeto_original_al_escribirse():
    lote = lote_c(firewall=FW_ACTIVO, red_clon=RED_CAMBIAR)
    copia = copy.deepcopy(lote)
    bytes_de(lote)
    assert lote == copia


def test_rf_c6_1_un_archivo_v4_con_claves_de_c_las_conserva_sin_romper_la_lectura():
    """0.8.0 no impone la versión del archivo a las claves que ya conoce."""
    datos = mutar(v5(), lambda c: c.update(version_formato=4))
    archivo = leer_lote(datos)
    assert archivo.lote.definicion.plantilla.firewall == FW_ACTIVO


def test_ca_c6_1_3_un_tarjeta_de_cloudinit_no_cambia_con_la_fase_c():
    ci = ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, ModoTarjeta.DHCP),))
    assert version_escrita(lote_c(cloudinit=ci)) == 4
