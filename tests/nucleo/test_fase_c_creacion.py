"""Creación con firewall y grupo de seguridad (C3, fase C, 0.8.0): orden de las peticiones por MV,
``firewall=1``, ``dhcp`` automático, regla sin duplicar, fallo a mitad (``PARCIAL``), «Reintentar
ajustes», todos los orígenes y compatibilidad con 0.6.0/0.7.0.

Requisitos: RF-C0.2 (CA-C0.2.1, CA-C0.2.3), RF-C0.7 (CA-C0.7.1 a CA-C0.7.3), RF-C0.8 (CA-C0.8.1),
RF-C3.1 (CA-C3.1.1, CA-C3.1.4), RF-C3.2 (CA-C3.2.4), RF-C3.3, RF-C3.4, RF-C3.5 (CA-C3.5.5),
RF-C3.6 (CA-C3.6.1 a CA-C3.6.5), RF-C3.7, RF-C3.8, RF-C3.10 (CA-C3.10.1), P-C5, P-C8, P-C9 y
RNF-C6.5 (secretos).

Dobles: ``ClusterC`` (``ClusterA`` con las rutas de firewall) a través de ``MundoC``. Las
instantáneas de 0.6.0 son ``tests/datos/fase_b/golden_v060.json``.
"""

from __future__ import annotations

import dataclasses
import json
import logging

import pytest

from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.firewall.modelos import FirewallMV, ModoDhcp, Politica
from proxlaunch.nucleo.lote.ajustes import ajustes_pendientes, reintentar_ajustes
from proxlaunch.nucleo.lote.informe import ajustes_aplicados
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.modelos.origen import AjustesClon
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.servicios.creacion import (
    AVISO_FIREWALL_GRUPO_YA_ESTABA,
    AVISO_FIREWALL_HEREDADO,
)

from . import apoyo_golden_fase_b as g
from .apoyo_fase_a import catalogo as catalogo_a
from .apoyo_fase_a import cfg_vm, inv_con
from .apoyo_fase_b_p1 import CENTINELA, MundoB, ci, ci_completa, config_plantilla
from .apoyo_fase_c_firewall import (
    GRUPO,
    MundoC,
    fallar_fw,
    fw,
    perder_respuesta_regla,
    secuencia,
)
from .apoyo_lote import NORMAL, error_http
from .apoyo_mvp4 import VOLID_IMAGEN, VOLID_ISO, cfg_import, cfg_iso

E403 = "Permission check failed (/vms/100, VM.Config.Network)"
SOLO_ESCRITURAS = {
    "clone",
    "crear",
    "ajustes",
    "red",
    "ci",
    "pw",
    "fw_opciones",
    "fw_regla",
    "resize",
    "start",
}


def _escrituras(m, vmid: int = 100) -> list[str]:
    """Secuencia de la MV sin las lecturas (para comparar solo el orden de las escrituras)."""
    return [x for x in secuencia(m.cl, vmid) if x in SOLO_ESCRITURAS]


def _cuerpo(m, sufijo: str, metodo: str = "PUT") -> dict:
    """Cuerpo de la primera petición ``metodo`` cuya ruta acaba en ``sufijo``."""
    llamadas = [c for c in m.cl.llamadas if c.metodo == metodo and c.ruta.endswith(sufijo)]
    assert llamadas, (metodo, sufijo)
    return dict(llamadas[0].datos or {})


# --- RF-C3.7: orden de las peticiones por MV --------------------------------------------------


def test_ca_c3_7_1_orden_exacto_clone_ajustes_red_cloudinit_contrasena_firewall_resize_start():
    """CA-C3.7.1 y §0: clone → PUT ajustes → GET+PUT red → PUT cloud-init → PUT contraseña →
    PUT firewall/options → POST firewall/rules → resize → start (con la plantilla ya leída en
    «Comprobar», así que no hay ``GET …/firewall/rules`` del clon)."""
    m = MundoC()
    m.leer_firewall()
    cfg = m.cfg(
        ci_completa(Secreto(CENTINELA)),
        ajustes=AjustesClon(cores=4, disco_gib=64),
        firewall=fw(),
        encender=True,
    )
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    assert secuencia(m.cl) == [
        "clone",
        "leer_config",
        "ajustes",
        "leer_config",
        "red",
        "ci",
        "pw",
        "fw_opciones",
        "fw_regla",
        "resize",
        "start",
    ]


def test_ca_c3_7_1_la_lectura_de_config_precede_inmediatamente_al_put_de_red():
    """CA-C3.7.1 (§3.1): el ``PUT`` de red se calcula sobre la config DEL CLON recién leída (para
    conservar su MAC): el ``GET config`` va justo antes."""
    m = MundoC()
    m.leer_firewall()
    m.crear(m.cfg(ci(), firewall=fw()))
    sec = secuencia(m.cl)
    assert sec[sec.index("red") - 1] == "leer_config"


def test_ca_c3_7_1_sin_ajustes_ni_cloudinit_son_red_opciones_regla_y_start():
    """CA-C3.7.1: PUT net → PUT firewall/options → POST firewall/rules → start."""
    m = MundoC()
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw(), encender=True, etiquetas=()))
    assert r.desenlace == Desenlace.OK
    assert _escrituras(m) == ["clone", "red", "fw_opciones", "fw_regla", "start"]


def test_ca_c3_7_1_todas_las_escrituras_de_firewall_van_antes_de_encender():
    m = MundoC()
    m.crear(m.cfg(ci(), firewall=fw(), encender=True))
    sec = secuencia(m.cl)
    assert sec.index("fw_regla") < sec.index("start")
    assert sec.index("fw_opciones") < sec.index("fw_regla")
    assert sec.index("red") < sec.index("fw_opciones")


def test_ca_c3_7_4_sin_encender_las_escrituras_de_firewall_se_emiten_igualmente():
    """CA-C3.7.4: «Encender al terminar» apagado: opciones y regla se escriben y no hay start."""
    m = MundoC()
    r = m.crear(m.cfg(None, firewall=fw(), encender=False, etiquetas=()))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS)
    escrituras = _escrituras(m)
    assert escrituras == ["clone", "red", "fw_opciones", "fw_regla"]
    assert "start" not in secuencia(m.cl)


def test_ca_c3_7_1_cada_paso_se_envia_una_sola_vez():
    m = MundoC()
    m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), firewall=fw(), encender=True))
    sec = secuencia(m.cl)
    for paso in ("red", "ci", "pw", "fw_opciones", "fw_regla", "start"):
        assert sec.count(paso) == 1, (paso, sec)


# --- RF-C3.7 / RF-C3.1: cuerpos de las peticiones ---------------------------------------------


def test_ca_c3_7_3_la_regla_es_de_grupo_sin_iface_source_dest_proto_ni_dport():
    """CA-C3.7.3 y P-C5."""
    m = MundoC()
    m.crear(m.cfg(None, firewall=fw("web-01")))
    cuerpo = _cuerpo(m, "/firewall/rules", "POST")
    assert cuerpo == {"type": "group", "action": "web-01", "enable": "1", "comment": "ProxLaunch"}
    for prohibida in ("iface", "source", "dest", "proto", "dport", "sport", "macro", "log"):
        assert prohibida not in cuerpo


def test_ca_c3_1_2_las_opciones_activan_el_firewall_con_enable_1():
    """CA-C3.1.2: ``PUT …/firewall/options`` con ``enable=1`` y las dos políticas explícitas."""
    m = MundoC()
    m.crear(m.cfg(None, firewall=fw()))
    op = _cuerpo(m, "/firewall/options")
    assert op["enable"] == "1"
    assert op["policy_in"] == "DROP" and op["policy_out"] == "ACCEPT"


def test_ca_c3_3_1_politica_por_defecto_es_entrada_drop_y_salida_accept():
    m = MundoC()
    m.crear(m.cfg(None, firewall=fw()))
    op = _cuerpo(m, "/firewall/options")
    assert (op["policy_in"], op["policy_out"]) == ("DROP", "ACCEPT")


@pytest.mark.parametrize(
    ("entrada", "salida", "esperado"),
    [
        (Politica.PERMITIR, Politica.PERMITIR, ("ACCEPT", "ACCEPT")),
        (Politica.BLOQUEAR, Politica.BLOQUEAR, ("DROP", "DROP")),
        (Politica.PERMITIR, Politica.BLOQUEAR, ("ACCEPT", "DROP")),
    ],
)
def test_ca_c3_3_1_las_politicas_elegidas_viajan_como_accept_o_drop_nunca_reject(
    entrada, salida, esperado
):
    """RF-C3.3 / P-C5: solo Bloquear (DROP) y Permitir (ACCEPT); nunca REJECT."""
    m = MundoC()
    r = m.crear(m.cfg(None, firewall=fw(politica_entrada=entrada, politica_salida=salida)))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS)
    op = _cuerpo(m, "/firewall/options")
    assert (op["policy_in"], op["policy_out"]) == esperado
    assert "REJECT" not in str(op.values())


def test_ca_c3_7_2_firewall_1_va_en_todas_las_tarjetas_de_la_plantilla():
    """CA-C3.7.2: la plantilla con 3 tarjetas queda con ``firewall=1`` en net0, net1 y net2 y
    conserva MAC y bridge."""
    m = MundoC(plantillas={9000: ("base", config_plantilla(redes=3))})
    m.crear(m.cfg(ci(), firewall=fw()))
    red = _cuerpo(m, "/config")  # primer PUT config: etiquetas (si las hay); busca el de red
    puts = [dict(c.datos) for c in m.cl.llamadas if c.metodo == "PUT" and "net0" in (c.datos or {})]
    assert len(puts) == 1, red
    put = puts[0]
    for i in range(3):
        assert put[f"net{i}"].endswith(",firewall=1"), put
        assert "bridge=vmbr0" in put[f"net{i}"]
    assert "AA:BB:CC:DD:EE:FF" in put["net0"]  # la MAC se conserva


def test_ca_c3_7_2_el_clon_queda_con_firewall_1_en_su_config_leida():
    m = MundoC(plantillas={9000: ("base", config_plantilla(redes=2))})
    m.crear(m.cfg(None, firewall=fw()))
    config = m.cl.vms[100]["config"]
    assert config["net0"].endswith("firewall=1") and config["net1"].endswith("firewall=1")


def test_ca_c3_7_2_una_tarjeta_que_ya_tiene_firewall_1_no_se_duplica_el_parametro():
    m = MundoC(
        plantillas={
            9000: (
                "base",
                config_plantilla(net0="virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0,firewall=1"),
            )
        }
    )
    m.crear(m.cfg(None, firewall=fw()))
    assert m.cl.vms[100]["config"]["net0"].count("firewall=1") == 1


# --- RF-C3.4: DHCP automático -----------------------------------------------------------------


def test_ca_c3_4_1_con_cloudinit_dhcp_en_una_tarjeta_el_put_lleva_dhcp_1():
    m = MundoC()
    m.crear(m.cfg(ci(), firewall=fw()))
    assert _cuerpo(m, "/firewall/options")["dhcp"] == "1"


def test_ca_c3_4_3_con_ip_fija_el_put_no_lleva_dhcp():
    m = MundoC()
    m.crear(m.cfg(ci_completa(), firewall=fw()))
    assert "dhcp" not in _cuerpo(m, "/firewall/options")


def test_ca_c3_4_3_sin_cloudinit_el_put_no_lleva_dhcp():
    m = MundoC()
    m.crear(m.cfg(None, firewall=fw()))
    assert "dhcp" not in _cuerpo(m, "/firewall/options")


def test_ca_c3_4_2_dhcp_no_explicito_con_cloudinit_dhcp_no_se_envia():
    """El usuario la desmarca (``NO``): se envía ``dhcp=0`` (no se hereda el de la plantilla)."""
    m = MundoC()
    m.crear(m.cfg(ci(), firewall=fw(dhcp=ModoDhcp.NO, politica_entrada=Politica.PERMITIR)))
    assert _cuerpo(m, "/firewall/options")["dhcp"] == "0"


def test_ca_c3_4_1_dhcp_si_explicito_sin_cloudinit_envia_dhcp_1():
    m = MundoC()
    m.crear(m.cfg(None, firewall=fw(dhcp=ModoDhcp.SI)))
    assert _cuerpo(m, "/firewall/options")["dhcp"] == "1"


# --- RF-C3.1: firewall sin grupo --------------------------------------------------------------


def test_ca_c3_9_1_sin_grupo_y_confirmado_se_envian_las_opciones_pero_ninguna_regla():
    """RF-C3.9 / P-C6: con la casilla marcada se crea; sin grupo no hay ``POST …/rules``."""
    m = MundoC()
    r = m.crear(m.cfg(None, firewall=fw(None, acepto_aislada=True)))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), (r.desenlace, r.error)
    assert "fw_opciones" in secuencia(m.cl)
    assert "fw_regla" not in secuencia(m.cl)
    assert not m.cl.llamadas_a("POST", r"/firewall/rules")


def test_ca_c3_9_1_sin_grupo_con_entrada_bloquear_y_sin_confirmar_no_envia_nada():
    """P-C6 / V-C36 (error): la creación directa se rechaza antes de enviar nada."""
    m = MundoC()
    r = m.crear(m.cfg(None, firewall=fw(None)))
    assert r.desenlace == Desenlace.ERROR
    assert m.cl.total("POST") == 0 and m.cl.total("PUT") == 0
    assert m.cl.llamadas_a("POST", r"/clone") == []


def test_ca_c3_9_4_sin_grupo_con_entrada_permitir_no_exige_la_casilla():
    m = MundoC()
    r = m.crear(m.cfg(None, firewall=fw(None, politica_entrada=Politica.PERMITIR)))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS)
    assert _cuerpo(m, "/firewall/options")["policy_in"] == "ACCEPT"


def test_ca_c3_2_2_un_grupo_con_nombre_invalido_no_envia_ninguna_peticion():
    """V-C31 / RNF-C6.3: un nombre dudoso nunca llega al servidor."""
    m = MundoC()
    r = m.crear(m.cfg(None, firewall=fw("1web")))
    assert r.desenlace == Desenlace.ERROR
    assert m.cl.total("POST") == 0 and m.cl.total("PUT") == 0


# --- RF-C3.6: la plantilla ya trae firewall ---------------------------------------------------


def test_ca_c3_6_2_si_la_plantilla_ya_tiene_la_regla_del_grupo_no_se_emite_el_post():
    """CA-C3.6.2 y P-C8: ni el ``POST`` ni lecturas de reglas del clon; aviso en el informe."""
    m = MundoC()
    m.cl.fw_reglas[9000] = [{"type": "group", "action": GRUPO, "enable": 1}]
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw(), encender=True))
    assert "fw_regla" not in secuencia(m.cl)
    assert len(m.cl.fw_reglas[100]) == 1  # la heredada, no una segunda
    assert f"{AVISO_FIREWALL_GRUPO_YA_ESTABA}:{GRUPO}" in r.avisos
    assert "fw_opciones" in secuencia(m.cl)  # las opciones sí se aplican
    assert "start" in secuencia(m.cl)


def test_ca_c3_6_2_el_aviso_de_firewall_heredado_pasa_la_mv_a_con_avisos_sin_pausar():
    """CA-C3.6.1: plantilla con ``enable=1`` (y regla): V-C35 en el informe de cada clon."""
    m = MundoC()
    m.cl.fw_opciones[9000] = {"enable": 1}
    m.cl.fw_reglas[9000] = [{"type": "in", "action": "ACCEPT", "enable": 1}]
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw()))
    assert AVISO_FIREWALL_HEREDADO in r.avisos
    assert r.desenlace == Desenlace.CON_AVISOS
    assert "fw_regla" in secuencia(m.cl)  # es otra regla: la del grupo se suma


def test_ca_c3_6_1_cada_clon_de_un_lote_lleva_el_aviso_de_firewall_heredado():
    m = MundoC()
    m.cl.fw_opciones[9000] = {"enable": 1}
    m.leer_firewall()
    plan = m.planificar(m.definicion(3, ci(), firewall=fw()))
    assert not plan.bloqueado, plan.problemas
    libro = m.ejecutar(plan)
    assert all(AVISO_FIREWALL_HEREDADO in e.avisos for e in libro.instantanea())


def test_ca_c3_6_3_plantilla_sin_firewall_no_da_aviso_y_termina_ok():
    m = MundoC()
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw()))
    assert r.desenlace == Desenlace.OK
    assert not any(a.startswith("firewall_") for a in r.avisos)


def test_ca_c3_6_2_p_c8_una_regla_de_otro_grupo_en_la_plantilla_no_impide_la_del_elegido():
    m = MundoC()
    m.cl.grupos["db"] = []
    m.cl.fw_reglas[9000] = [{"type": "group", "action": "db", "enable": 1}]
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw()))
    assert "fw_regla" in secuencia(m.cl)
    assert f"{AVISO_FIREWALL_GRUPO_YA_ESTABA}:{GRUPO}" not in r.avisos
    assert [x["action"] for x in m.cl.fw_reglas[100]] == ["db", GRUPO]


def test_ca_c3_6_5_si_no_se_pudo_leer_la_plantilla_se_comprueba_el_clon_antes_del_post():
    """CA-C3.6.5 / DT-C10: sin saber qué trae la plantilla, ``GET …/rules`` del clon antes de
    escribir, y no se duplica una regla que ya estuviera."""
    m = MundoC()
    m.cl.fw_reglas[9000] = [{"type": "group", "action": GRUPO, "enable": 1}]
    fallar_fw(
        m.cl,
        "GET",
        "options",
        error_http(403, "Permission check failed (/vms/9000, VM.Audit)"),
        vmid=9000,
    )
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw()))
    sec = secuencia(m.cl)
    assert "fw_leer_reglas" in sec and "fw_regla" not in sec
    assert len(m.cl.fw_reglas[100]) == 1
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS)


# --- RF-C0.2 / CA-C3.1.1 / CA-C3.6.4: sin firewall nada cambia --------------------------------


def _llamadas(m):
    return [(c.metodo, c.ruta, c.datos) for c in m.cl.llamadas]


@pytest.mark.parametrize(
    "firewall",
    [None, FirewallMV(), FirewallMV(activo=False)],
    ids=["none", "defecto", "apagado"],
)
def test_ca_c0_2_3_clon_con_red_como_la_plantilla_y_firewall_apagado_es_identico_a_0_7_0(firewall):
    """CA-C0.2.3 / CA-C3.1.1: ningún ``GET config`` extra, ningún ``PUT`` de red ni petición de
    firewall; la secuencia coincide con la del ``MundoB`` (código de 0.7.0 sin firewall)."""
    nuevo = MundoC()
    nuevo.crear(
        nuevo.cfg(
            ci_completa(Secreto(CENTINELA)),
            firewall=firewall,
            ajustes=AjustesClon(cores=4, disco_gib=64),
            encender=True,
        )
    )
    base = MundoB()
    base.crear(
        base.cfg(
            ci_completa(Secreto(CENTINELA)),
            ajustes=AjustesClon(cores=4, disco_gib=64),
            encender=True,
        )
    )
    assert _llamadas(nuevo) == _llamadas(base)
    assert not any("firewall" in c.ruta for c in nuevo.cl.llamadas)
    assert "red" not in secuencia(nuevo.cl)


@pytest.mark.parametrize(
    "nombre",
    [
        "vacio",
        "iso",
        "importar_con_resize",
        "clon_sin_ajustes",
        "clon_con_ajustes",
        "lote_3_encender",
        "reintento_de_ajustes",
    ],
)
def test_ca_c0_2_1_la_secuencia_con_las_opciones_c_por_defecto_es_la_de_0_6_0(nombre):
    """CA-C0.2.1: método, ruta, consulta y cuerpo (bytes) de TODAS las peticiones, en orden."""
    esperado = g.golden()["escenarios"][nombre]
    actual = json.loads(json.dumps(g.actuales()[nombre]))
    assert actual == esperado
    assert not any("firewall" in ruta for _m, ruta, _c in actual)


def test_ca_c3_6_4_con_c3_apagada_la_planificacion_no_lee_el_firewall():
    """CA-C3.6.4 / RF-C0.2: ni grupos, ni firewall general, ni el de la plantilla."""
    m = MundoC()
    plan = m.planificar(m.definicion(2, ci()))
    assert not plan.bloqueado
    m.ejecutar(plan)
    assert not any("firewall" in c.ruta for c in m.cl.llamadas)


def test_ca_c3_6_4_con_firewall_inactivo_en_el_formulario_tampoco_se_lee_nada():
    m = MundoC()
    plan = m.planificar(m.definicion(2, ci(), firewall=FirewallMV(activo=False)))
    assert not plan.bloqueado
    assert not any("firewall" in c.ruta for c in m.cl.llamadas)


# --- RF-C3.1 / P-C9: todos los orígenes -------------------------------------------------------


def _mundo_origenes() -> MundoC:
    m = MundoC()
    m.cl.contenido[("pve1", "local")] = [VOLID_ISO, VOLID_IMAGEN]
    return m


def test_ca_c3_1_4_origen_iso_lleva_firewall_1_en_el_post_y_aplica_opciones_y_regla_despues():
    """CA-C3.1.4 / P-C9."""
    m = _mundo_origenes()
    r = m.crear(cfg_iso(firewall=fw(), etiquetas=("proxlaunch",)))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), (r.desenlace, r.error)
    cuerpo = m.cl.cuerpos_post[100]
    assert cuerpo["net0"] == "virtio,bridge=vmbr0,firewall=1"
    sec = secuencia(m.cl)
    assert sec.index("crear") < sec.index("fw_opciones") < sec.index("fw_regla")
    assert "red" not in sec  # no hay paso de red: la tarjeta ya nació con firewall=1


def test_ca_c3_1_4_origen_disco_vacio_lleva_firewall_1_y_aplica_opciones_y_regla_despues():
    m = _mundo_origenes()
    m.inv = inv_con(catalogo_a())
    m.banco.inv = m.inv
    r = m.crear(cfg_vm(firewall=fw(), encender=True))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), (r.desenlace, r.error)
    assert m.cl.cuerpos_post[100]["net0"].endswith(",firewall=1")
    assert _escrituras(m) == ["crear", "fw_opciones", "fw_regla", "start"]


def test_ca_c3_1_4_origen_importar_aplica_el_firewall_antes_de_ampliar_el_disco():
    """RF-C3.1 / P-C9: importar con ampliación: crear → opciones → regla → resize."""
    m = _mundo_origenes()
    cfg = cfg_import(cfg={"firewall": fw(), "etiquetas": ("proxlaunch",)}, ampliar_a_gib=64)
    r = m.crear(cfg)
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), (r.desenlace, r.error)
    assert m.cl.cuerpos_post[100]["net0"].endswith(",firewall=1")
    assert _escrituras(m) == ["crear", "fw_opciones", "fw_regla", "resize"]


@pytest.mark.parametrize("origen", ["iso", "vacio", "importar"])
def test_ca_c3_1_4_origen_no_clon_no_lee_las_reglas_del_clon_antes_de_enviar_la_regla(origen):
    m = _mundo_origenes()
    m.inv = inv_con(catalogo_a())
    m.banco.inv = m.inv
    cfg = {
        "iso": lambda: cfg_iso(firewall=fw(), etiquetas=("proxlaunch",)),
        "vacio": lambda: cfg_vm(firewall=fw()),
        "importar": lambda: cfg_import(cfg={"firewall": fw()}),
    }[origen]()
    if origen != "vacio":
        m.inv = MundoC().inv
        m.banco.inv = m.inv
    m.crear(cfg)
    assert "fw_leer_reglas" not in secuencia(m.cl)
    assert len(m.cl.fw_reglas[100]) == 1


def test_ca_c3_1_4_origen_iso_con_dhcp_manual_envia_dhcp_1():
    m = _mundo_origenes()
    m.crear(cfg_iso(firewall=fw(dhcp=ModoDhcp.SI), etiquetas=("proxlaunch",)))
    assert _cuerpo(m, "/firewall/options")["dhcp"] == "1"


def test_ca_c3_1_4_origen_iso_sin_firewall_es_el_post_de_0_7_0_sin_peticiones_nuevas():
    """CA-C0.2.1 para ISO con el formulario por defecto: sin ``firewall=1`` ni peticiones nuevas."""
    m = _mundo_origenes()
    m.crear(cfg_iso(etiquetas=("proxlaunch",)))
    assert "firewall" not in m.cl.cuerpos_post[100]["net0"]
    assert not any("firewall" in c.ruta for c in m.cl.llamadas)


# --- RF-C0.7 / RF-C3.8: fallo a mitad ---------------------------------------------------------


def test_ca_c0_7_1_un_403_en_el_put_de_red_deja_parcial_sin_encender_ni_escribir_firewall():
    """CA-C0.7.1: PARCIAL, sin ``status/start``, el error nombra el privilegio y la ruta, y lo
    posterior (firewall) no se intenta (cascada, DT-C7)."""
    m = MundoC()
    m.leer_firewall()

    def accion(ll):
        if "net0" in (ll.datos or {}):
            raise error_http(403, E403)
        return NORMAL

    m.cl.regla("PUT", r"/qemu/100/config$", accion)
    r = m.crear(m.cfg(ci_completa(), firewall=fw(), encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error is not None and r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["privilegio"] == "VM.Config.Network"
    assert r.error.params["ruta"] == "/vms/100"
    sec = secuencia(m.cl)
    assert "start" not in sec
    assert "fw_opciones" not in sec and "fw_regla" not in sec and "ci" not in sec
    assert "ajuste_pendiente:red" in r.avisos
    assert "ajuste_pendiente:firewall_opciones" in r.avisos
    assert "ajuste_pendiente:firewall_regla" in r.avisos
    assert "encendido_omitido" in r.avisos


def test_ca_c3_8_1_un_403_en_las_opciones_de_firewall_deja_parcial_y_no_enciende():
    """CA-C3.8.1."""
    m = MundoC()
    fallar_fw(m.cl, "PUT", "options", error_http(403, E403))
    r = m.crear(m.cfg(None, firewall=fw(), encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error is not None and r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["privilegio"] == "VM.Config.Network"
    assert r.error.params["ruta"] == "/vms/100"
    assert r.error.params["ajuste"] == "firewall_opciones"
    sec = secuencia(m.cl)
    assert "start" not in sec and "fw_regla" not in sec
    assert "ajuste_pendiente:firewall_opciones" in r.avisos
    assert "ajuste_pendiente:firewall_regla" in r.avisos


def test_ca_c0_7_2_un_fallo_en_la_regla_tras_red_y_opciones_aplicadas_distingue_lo_aplicado():
    """CA-C0.7.2: red aplicada; opciones aplicadas; regla de grupo NO aplicada; sin encender."""
    m = MundoC()
    fallar_fw(m.cl, "POST", "rules", error_http(403, E403))
    plan = m.planificar(m.definicion(1, ci(), firewall=fw(), encender=True))
    libro = m.ejecutar(plan)
    e = libro.entrada(100)
    assert e.estado == EstadoMV.PARCIAL
    assert ajustes_pendientes(e) == frozenset({"firewall_regla"})
    assert ajustes_aplicados(e) == ("red", "cloudinit", "firewall_opciones")
    assert "start" not in secuencia(m.cl)


def test_ca_c3_8_1_el_fallo_de_red_de_una_mv_no_enciende_pero_deja_la_mv_creada_sin_borrarla():
    """RF-C0.7: la MV nunca se borra sola."""
    m = MundoC()
    fallar_fw(m.cl, "PUT", "options", error_http(403, E403))
    m.crear(m.cfg(None, firewall=fw(), encender=True))
    assert m.cl.deletes[100] == 0 and 100 in m.cl.vms


def test_ca_c3_2_4_un_grupo_que_desaparece_tras_comprobar_deja_parcial_con_mensaje_claro():
    """CA-C3.2.4: el servidor rechaza la regla (400): ``FIREWALL_GRUPO_INEXISTENTE``, PARCIAL,
    sin encender."""
    m = MundoC()
    m.leer_firewall()
    del m.cl.grupos[GRUPO]
    r = m.crear(m.cfg(None, firewall=fw(), encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error is not None and r.error.codigo == CodigoError.FIREWALL_GRUPO_INEXISTENTE
    assert r.error.params["grupo"] == GRUPO
    assert "ajuste_pendiente:firewall_regla" in r.avisos
    assert "start" not in secuencia(m.cl)


def test_ca_c3_8_4_lote_de_10_mvs_con_fallo_en_2_las_otras_8_terminan_y_las_2_constan():
    """CA-C3.8.4: el 403 de firewall no pausa el lote; las dos fallidas quedan PARCIAL con el
    paso fallido y sin encender; las ocho restantes llegan a OK encendidas."""
    m = MundoC()
    for v in (103, 107):
        fallar_fw(m.cl, "PUT", "options", error_http(403, E403.replace("100", str(v))), vmid=v)
    plan = m.planificar(m.definicion(10, ci(), firewall=fw(), encender=True))
    assert not plan.bloqueado, plan.problemas
    libro = m.ejecutar(plan)
    estados = m.estados(libro)
    assert [v for v, s in estados.items() if s == EstadoMV.PARCIAL] == [103, 107]
    assert sum(1 for s in estados.values() if s == EstadoMV.OK) == 8
    for v in (103, 107):
        assert ajustes_pendientes(libro.entrada(v)) == {"firewall_opciones", "firewall_regla"}
        assert "start" not in secuencia(m.cl, v)
    for v in set(estados) - {103, 107}:
        assert secuencia(m.cl, v)[-1] == "start"
    assert m.cl.inicios == {v: 1 for v in set(estados) - {103, 107}}


# --- «Reintentar ajustes» ---------------------------------------------------------------------


def _reintentar(m, libro, *vmids):
    reintentar_ajustes(
        libro, list(vmids), m.sesion, m.reloj, m.inv, m.banco.observador, ControlLote()
    )


def test_ca_c0_7_3_el_reintento_tras_fallar_la_regla_repite_solo_la_regla():
    """CA-C0.7.3 / CA-C3.8.2: no vuelve a escribir la red, cloud-init ni las opciones."""
    m = MundoC()
    m.leer_firewall()
    regla = fallar_fw(m.cl, "POST", "rules", error_http(500, "fallo de prueba"), veces=1)
    plan = m.planificar(m.definicion(1, ci(), firewall=fw(), encender=True))
    libro = m.ejecutar(plan)
    assert libro.entrada(100).estado == EstadoMV.PARCIAL
    assert regla.disparos == 1
    m.cl.llamadas.clear()
    _reintentar(m, libro, 100)
    sec = secuencia(m.cl)
    assert sec.count("fw_regla") == 1
    for repetido in ("red", "ci", "pw", "ajustes", "fw_opciones", "clone", "resize"):
        assert repetido not in sec, (repetido, sec)
    assert libro.entrada(100).estado == EstadoMV.OK
    assert len(m.cl.fw_reglas[100]) == 1


def test_ca_c0_7_3_tras_el_reintento_ok_la_mv_se_enciende_una_sola_vez():
    m = MundoC()
    fallar_fw(m.cl, "POST", "rules", error_http(500, "fallo de prueba"), veces=1)
    libro = m.ejecutar(m.planificar(m.definicion(1, ci(), firewall=fw(), encender=True)))
    assert m.cl.inicios.get(100, 0) == 0
    _reintentar(m, libro, 100)
    assert m.cl.inicios.get(100, 0) == 1


def test_ca_c3_8_2_el_reintento_tras_fallar_las_opciones_repite_opciones_y_regla_sin_la_red():
    m = MundoC()
    fallar_fw(m.cl, "PUT", "options", error_http(500, "fallo de prueba"), veces=1)
    libro = m.ejecutar(m.planificar(m.definicion(1, ci(), firewall=fw())))
    assert ajustes_pendientes(libro.entrada(100)) == {"firewall_opciones", "firewall_regla"}
    m.cl.llamadas.clear()
    _reintentar(m, libro, 100)
    sec = secuencia(m.cl)
    assert "red" not in sec and "ci" not in sec
    assert sec.index("fw_opciones") < sec.index("fw_regla")
    assert libro.entrada(100).estado == EstadoMV.OK


def test_ca_c3_8_3_con_la_respuesta_perdida_de_la_primera_regla_el_reintento_no_la_duplica():
    """CA-C3.8.3: el primer ``POST`` se aplicó en el servidor y el cliente lo ignora; el reintento
    lee las reglas del clon antes de repetir y no crea una segunda."""
    m = MundoC()
    m.leer_firewall()
    perder_respuesta_regla(m.cl, 100, error_http(500, "respuesta perdida"))
    libro = m.ejecutar(m.planificar(m.definicion(1, ci(), firewall=fw())))
    assert libro.entrada(100).estado == EstadoMV.PARCIAL
    assert len(m.cl.fw_reglas[100]) == 1  # ya existe aunque el cliente no lo sepa
    m.cl.llamadas.clear()
    _reintentar(m, libro, 100)
    sec = secuencia(m.cl)
    assert "fw_leer_reglas" in sec and "fw_regla" not in sec
    assert len(m.cl.fw_reglas[100]) == 1
    assert libro.entrada(100).estado == EstadoMV.OK


def test_ca_c3_8_3_reintentar_dos_veces_seguidas_nunca_duplica_la_regla():
    m = MundoC()
    fallar_fw(m.cl, "POST", "rules", error_http(500, "fallo de prueba"), veces=1)
    libro = m.ejecutar(m.planificar(m.definicion(1, ci(), firewall=fw())))
    _reintentar(m, libro, 100)
    _reintentar(m, libro, 100)
    assert len(m.cl.fw_reglas[100]) == 1


def test_ca_c0_7_3_el_reintento_tras_fallar_la_red_repite_red_y_lo_siguiente_sin_duplicar_nada():
    """Fallo de red (paso 1): lo posterior queda pendiente; el reintento los aplica en orden y
    tras él la MV queda con firewall=1, opciones y UNA regla."""
    m = MundoC()
    m.leer_firewall()
    estado = {"n": 0}

    def una_vez(ll):
        if "net0" in (ll.datos or {}) and estado["n"] == 0:
            estado["n"] = 1
            raise error_http(403, E403)
        return NORMAL

    m.cl.regla("PUT", r"/qemu/100/config$", una_vez)
    libro = m.ejecutar(m.planificar(m.definicion(1, ci(), firewall=fw(), encender=True)))
    e = libro.entrada(100)
    assert e.estado == EstadoMV.PARCIAL
    assert ajustes_pendientes(e) >= {"red", "firewall_opciones", "firewall_regla"}
    m.cl.llamadas.clear()
    _reintentar(m, libro, 100)
    assert libro.entrada(100).estado == EstadoMV.OK
    assert m.cl.vms[100]["config"]["net0"].endswith("firewall=1")
    assert len(m.cl.fw_reglas[100]) == 1
    sec = secuencia(m.cl)
    assert sec.index("red") < sec.index("fw_opciones") < sec.index("fw_regla")


def test_ca_c3_8_2_un_reintento_de_una_mv_sin_pendientes_de_firewall_no_toca_el_firewall():
    m = MundoC()
    libro = m.ejecutar(m.planificar(m.definicion(2, ci(), firewall=fw())))
    m.cl.llamadas.clear()
    _reintentar(m, libro, 100, 101)
    assert not any(c.metodo != "GET" for c in m.cl.llamadas)


# --- RF-C0.8 / RF-C3.5.5: la app nunca escribe fuera de la MV ---------------------------------


def test_ca_c0_8_1_ninguna_escritura_apunta_a_cluster_firewall_ni_sdn():
    """CA-C0.8.1 y CA-C3.5.5 (también con el firewall general apagado)."""
    m = MundoC()
    m.cl.general = {"enable": 0}
    plan = m.planificar(m.definicion(3, ci_completa(serie=True), firewall=fw(), encender=True))
    m.ejecutar(plan)
    assert m.cl.escrituras_fuera_de_vm() == []
    assert not [
        c for c in m.cl.llamadas if c.metodo == "PUT" and c.ruta == "/cluster/firewall/options"
    ]
    escrituras_fw = m.cl.escrituras_fw()
    assert escrituras_fw and all(r.startswith("/nodes/pve1/qemu/10") for _m, r in escrituras_fw)


def test_ca_c0_8_1_el_clon_de_firewall_no_toca_los_grupos():
    m = MundoC()
    grupos_antes = {k: list(v) for k, v in m.cl.grupos.items()}
    m.crear(m.cfg(None, firewall=fw()))
    assert m.cl.grupos == grupos_antes
    assert not [c for c in m.cl.llamadas if "/cluster/" in c.ruta and c.metodo != "GET"]


# --- RF-C3.10: Deshacer -----------------------------------------------------------------------


def _deshacer(m, libro):
    servicio = ServicioRollback(m.sesion, m.reloj)
    candidatos = servicio.elegibles(libro, etiquetado=True)
    todas = frozenset(c.entrada.elemento.vmid for c in candidatos)
    servicio.deshacer(
        candidatos,
        lambda _r: None,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
        forzar_apagado=todas,
        forzar_desproteccion=todas,
        permisos=None,
    )


def _escrituras_deshacer(m):
    return [
        (c.metodo, c.ruta, dict(c.params or {}), c.datos)
        for c in m.cl.llamadas
        if c.metodo != "GET"
    ]


def test_ca_c3_10_1_el_delete_de_un_lote_con_firewall_es_identico_al_de_uno_sin_firewall():
    """CA-C3.10.1: mismas peticiones de escritura (DELETE con la misma consulta); no hay
    peticiones de firewall al deshacer."""
    resultados = []
    for firewall in (None, fw()):
        m = MundoC()
        libro = m.ejecutar(m.planificar(m.definicion(2, ci(), firewall=firewall, etiquetas=())))
        m.cl.llamadas.clear()
        _deshacer(m, libro)
        resultados.append(_escrituras_deshacer(m))
        assert not any("firewall" in c.ruta for c in m.cl.llamadas)
    assert resultados[0] == resultados[1]
    assert [r[0] for r in resultados[0]] == ["DELETE", "DELETE"]


# --- Secretos (RNF-C6.5) ----------------------------------------------------------------------


def test_rnf_c6_5_la_contrasena_solo_viaja_en_su_put_y_nunca_a_las_rutas_de_firewall(caplog):
    caplog.set_level(logging.DEBUG)
    m = MundoC()
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), firewall=fw(), encender=True))
    assert r.desenlace == Desenlace.OK
    con_secreto = [c for c in m.cl.llamadas if CENTINELA in str(c.datos)]
    assert [(c.metodo, c.ruta) for c in con_secreto] == [("PUT", "/nodes/pve1/qemu/100/config")]
    assert not any("firewall" in c.ruta and CENTINELA in str(c.datos) for c in m.cl.llamadas)
    assert CENTINELA not in caplog.text
    assert CENTINELA not in repr(r) and CENTINELA not in str(r.error)


def test_rnf_c6_5_un_fallo_de_firewall_con_contrasena_no_filtra_el_secreto_en_registros(caplog):
    caplog.set_level(logging.DEBUG)
    m = MundoC()
    fallar_fw(m.cl, "PUT", "options", error_http(500, "boom"))
    libro = m.ejecutar(
        m.planificar(m.definicion(1, ci_completa(Secreto(CENTINELA)), firewall=fw(), encender=True))
    )
    assert libro.entrada(100).estado == EstadoMV.PARCIAL
    _reintentar(m, libro, 100)
    assert CENTINELA not in caplog.text
    assert CENTINELA not in repr(libro.entrada(100))


def test_ca_c3_8_1_el_servicio_no_sube_la_nota_ni_valores_del_servidor_al_error_de_firewall():
    """RNF-C6.5: el error de un paso de firewall lleva nombres, no el cuerpo del servidor."""
    m = MundoC()
    fallar_fw(m.cl, "POST", "rules", error_http(500, "SECRETO-DEL-SERVIDOR-xyz"))
    r = m.crear(m.cfg(None, firewall=fw()))
    assert r.desenlace == Desenlace.PARCIAL
    assert "SECRETO-DEL-SERVIDOR-xyz" not in str(r.error.params)


def test_los_avisos_de_firewall_son_codigos_sin_datos_del_servidor():
    m = MundoC()
    m.cl.fw_reglas[9000] = [{"type": "group", "action": GRUPO, "enable": 1, "comment": "NOTA-X"}]
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw()))
    assert all("NOTA-X" not in a for a in r.avisos)
    assert dataclasses.is_dataclass(r)


# --- RF-C0.7: la MV PARCIAL cancela la espera de IP y las demás la conservan ------------------


def test_ca_c0_7_1_una_mv_parcial_por_firewall_no_espera_su_ip_y_las_demas_si():
    """RF-C0.7: «impide encender y cancela la espera de IP de esa MV; el resto continúa»."""
    from proxlaunch.nucleo.agente.espera import EsperaIp
    from proxlaunch.nucleo.lote.libro import Libro
    from proxlaunch.nucleo.lote.motor import enlazar_espera

    from .apoyo_lote import respuesta_agente

    m = MundoC()
    fallar_fw(m.cl, "PUT", "options", error_http(403, E403), vmid=101)
    plan = m.planificar(
        m.definicion(
            3, ci(activar_agente=True), firewall=fw(), encender=True, esperar_ip=True, plazo_ip_s=60
        )
    )
    assert not plan.bloqueado, plan.problemas
    libro = Libro(plan)
    espera = EsperaIp(m.sesion, m.reloj, enlazar_espera(libro, m.banco.observador))
    for v in (100, 101, 102):
        m.cl.guion_agente(v, respuesta_agente(("eth0", None, ("10.0.0.5",))))
    m.ejecutar(plan, libro=libro, espera_ip=espera)
    espera.sin_mas_objetivos()
    espera.ejecutar()
    estados = m.estados(libro)
    assert estados[101] == EstadoMV.PARCIAL
    assert m.cl.sondeos_agente.get(101, 0) == 0  # nunca se consultó el agente de la MV parcial
    assert m.cl.sondeos_agente.get(100, 0) >= 1 and m.cl.sondeos_agente.get(102, 0) >= 1
    assert "start" not in secuencia(m.cl, 101)


# --- Lote mixto: solo se leen las plantillas de las filas con firewall ------------------------


def test_ca_c3_6_4_en_un_lote_mixto_solo_se_lee_el_firewall_de_la_plantilla_de_las_filas_con_c3():
    from proxlaunch.nucleo.firewall.modelos import FirewallParcial
    from proxlaunch.nucleo.lote.filas import definicion_por_filas
    from proxlaunch.nucleo.lote.modelos import FilaLote
    from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales

    from .apoyo_mvp4 import cfg_clon

    m = MundoC(plantillas={9000: ("base", config_plantilla()), 9001: ("otra", config_plantilla())})
    base = dataclasses.replace(cfg_clon("base"), discos=cfg_vm().discos, redes=cfg_vm().redes)
    otra = dataclasses.replace(base, detalle_origen=cfg_clon("otra").detalle_origen)
    filas = [
        FilaLote(
            "a-01",
            base,
            opciones=OpcionesParciales(firewall=FirewallParcial(activo=True, grupo=GRUPO)),
        ),
        FilaLote("a-02", otra),
    ]
    definicion = dataclasses.replace(
        definicion_por_filas(filas, plantilla_base=base), opciones=OpcionesLote()
    )
    plan = m.planificar(definicion)
    assert not plan.bloqueado, plan.problemas
    leidas = [c.ruta for c in m.cl.lecturas_fw("/options")]
    assert "/nodes/pve1/qemu/9000/firewall/options" in leidas
    assert "/nodes/pve1/qemu/9001/firewall/options" not in leidas


def test_ca_c3_8_3_si_el_reintento_no_puede_leer_las_reglas_no_arriesga_una_regla_duplicada():
    """DT-C10: sin poder comprobar qué reglas hay, no se envía el ``POST`` y la MV sigue PARCIAL."""
    m = MundoC()
    fallar_fw(m.cl, "POST", "rules", error_http(500, "fallo de prueba"), veces=1)
    libro = m.ejecutar(m.planificar(m.definicion(1, ci(), firewall=fw(), encender=True)))
    assert libro.entrada(100).estado == EstadoMV.PARCIAL
    fallar_fw(m.cl, "GET", "rules", error_http(500, "no se puede leer"))
    m.cl.llamadas.clear()
    _reintentar(m, libro, 100)
    assert "fw_regla" not in secuencia(m.cl)
    assert libro.entrada(100).estado == EstadoMV.PARCIAL
    assert "start" not in secuencia(m.cl)
    assert len(m.cl.fw_reglas[100]) == 0
