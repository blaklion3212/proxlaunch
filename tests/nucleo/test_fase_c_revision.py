"""Correcciones de la revisión F6 de la fase C (0.8.0): pruebas de regresión del núcleo.

Derivadas de docs/investigacion/fase-c-revision-f6.md. Cada prueba cita su ID (QA-C-*, SEG-C-*).
Solo se simula la red y el servidor; servicio, motor, cliente y libro son código real.
"""

from __future__ import annotations

import dataclasses
import json
import re

import pytest

from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.firewall.modelos import FirewallMV, ModoDhcp, Politica
from proxlaunch.nucleo.lote.ajustes import reintentar_ajustes
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.servicios.creacion import (
    AJUSTE_FIREWALL_REGLA,
    AVISO_AJUSTE_PENDIENTE,
    AVISO_FIREWALL_INCOMPLETO_NO_ENCENDIDA,
)

from . import apoyo_fase_c_firewall as apfw
from .apoyo_fase_b_p1 import ci
from .apoyo_fase_c_firewall import GRUPO, fallar_fw, fw, perder_respuesta_regla, secuencia
from .apoyo_fase_c_red import MundoC as MundoRed
from .apoyo_fase_c_red import anadir, bridge, cambiar, cfg_con_red, quitar, red_clon, vnet
from .apoyo_lote import NORMAL, envio_incierto, error_http

RE_MAC = re.compile(r"^[a-z0-9]+=([0-9A-F]{2}(?::[0-9A-F]{2}){5})", re.IGNORECASE)


def _reintentar(m, libro, *vmids):
    reintentar_ajustes(
        libro, list(vmids), m.sesion, m.reloj, m.inv, m.banco.observador, ControlLote()
    )


def _plan_fw(m, **kw):
    plan = m.planificar(m.definicion(1, ci(), **kw))
    assert not plan.bloqueado, plan.problemas
    return plan


# --- QA-C-A1: respuesta perdida del POST de la regla ---------------------------------------------


def test_qa_c_a1_respuesta_perdida_por_envio_incierto_deja_una_sola_regla_y_un_solo_post():
    m = apfw.MundoC()
    m.leer_firewall()
    perder_respuesta_regla(m.cl, 100, envio_incierto())
    libro = m.ejecutar(_plan_fw(m, firewall=fw()))
    assert len(m.cl.fw_reglas[100]) == 1
    assert secuencia(m.cl).count("fw_regla") == 1  # el POST no se reenvía a ciegas
    assert libro.entrada(100).estado == EstadoMV.OK, libro.entrada(100).avisos


def test_qa_c_a1_si_la_relectura_falla_el_paso_queda_pendiente_y_el_reintento_no_duplica():
    m = apfw.MundoC()
    m.leer_firewall()
    perder_respuesta_regla(m.cl, 100, envio_incierto())

    def caida(_ll):
        if m.cl.fw_reglas.get(100):  # solo la relectura posterior al POST perdido
            raise error_http(500, "lectura caída")
        return NORMAL

    relectura = m.cl.regla("GET", r"/qemu/100/firewall/rules$", caida)
    libro = m.ejecutar(_plan_fw(m, firewall=fw()))
    e = libro.entrada(100)
    assert e.estado == EstadoMV.PARCIAL
    assert f"{AVISO_AJUSTE_PENDIENTE}:{AJUSTE_FIREWALL_REGLA}" in e.avisos
    assert len(m.cl.fw_reglas[100]) == 1
    m.cl.reglas.remove(relectura)  # el servidor vuelve a responder
    m.cl.llamadas.clear()
    _reintentar(m, libro, 100)
    assert "fw_regla" not in secuencia(m.cl)  # la lee, la encuentra y no la reenvía
    assert len(m.cl.fw_reglas[100]) == 1
    assert libro.entrada(100).estado == EstadoMV.OK


# --- QA-C-M1: la MAC nueva se genera una sola vez ------------------------------------------------


def _mundo_red(**kw):
    kw.setdefault("bridges", {"pve1": (bridge("vmbr0"), bridge("vmbr1"))})
    kw.setdefault("redes_sdn", {"pve1": ()})
    return MundoRed(**kw)


def _perder_put_de_red(m, vmid: int = 100):
    """El primer ``PUT config`` con ``netN`` llega al servidor pero su respuesta se pierde."""
    estado = {"n": 0}

    def accion(ll):
        if "net0" in (ll.datos or {}) and estado["n"] == 0:
            estado["n"] = 1
            m.cluster._put(ll, "pve1", vmid, "config")
            raise envio_incierto()
        return NORMAL

    m.cluster.regla("PUT", rf"/qemu/{vmid}/config$", accion)


def test_qa_c_m1_mac_nueva_con_la_respuesta_del_put_perdida_genera_una_sola_mac():
    m = _mundo_red()
    _perder_put_de_red(m)
    r = m.crear(cfg_con_red(m, red_clon(cambiar(0, mac_nueva=True))))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), (r.desenlace, r.error)
    assert len(m.cluster.macs_generadas) == 1
    assert m.cluster.vms[100]["config"]["net0"].count("DE:AD:BE:EF") == 1


def _lote_mac_nueva(m):
    plan = m.planificar(m.definicion(1, ci(), red_clon=red_clon(cambiar(0, mac_nueva=True))))
    assert not plan.bloqueado, plan.problemas
    return plan


def test_qa_c_m1_reintentar_ajustes_tras_perder_la_respuesta_no_genera_otra_mac():
    m = _mundo_red()
    _perder_put_de_red(m)
    fallar_put_ci(m)
    libro = m.ejecutar(_lote_mac_nueva(m))
    assert libro.entrada(100).estado == EstadoMV.PARCIAL
    assert len(m.cluster.macs_generadas) == 1
    mac = RE_MAC.match(m.cluster.vms[100]["config"]["net0"])[1]
    _reintentar(m, libro, 100)
    assert len(m.cluster.macs_generadas) == 1
    assert RE_MAC.match(m.cluster.vms[100]["config"]["net0"])[1] == mac
    assert libro.entrada(100).estado == EstadoMV.OK


def test_qa_c_m1_tras_una_reconexion_el_mismo_libro_con_otra_sesion_no_genera_otra_mac():
    m = _mundo_red()
    _perder_put_de_red(m)
    fallar_put_ci(m)
    libro = m.ejecutar(_lote_mac_nueva(m))
    assert len(m.cluster.macs_generadas) == 1
    mac = RE_MAC.match(m.cluster.vms[100]["config"]["net0"])[1]
    assert libro.entrada(100).macs_originales  # la MAC original consta en el libro
    otro = _mundo_red()  # otra sesión y otro servicio, pero sobre el mismo servidor y libro
    otro.cluster.vms = m.cluster.vms
    reintentar_ajustes(
        libro, [100], otro.sesion, otro.reloj, otro.inv, otro.banco.observador, ControlLote()
    )
    assert len(m.cluster.macs_generadas) == 1 and not otro.cluster.macs_generadas
    assert RE_MAC.match(otro.cluster.vms[100]["config"]["net0"])[1] == mac


def fallar_put_ci(m):
    """Falla una vez el ``PUT`` de cloud-init (ciuser) para dejar la MV ``PARCIAL``."""
    from .apoyo_fase_b_p1 import fallar_put

    return fallar_put(m.cl, "ciuser", error_http(500, "fallo de prueba"), veces=1)


# --- QA-C-M2: reparto con los bridges FINALES del clon -------------------------------------------

_COMPARTIDA = {
    "scsi0": "nfs1:base-9000-disk-0,size=8G",
    "ide2": "nfs1:vm-9000-cloudinit,media=cdrom",
}


def _mundo_dos_nodos(*, bridges_pve2=("vmbr0",), vnets_pve1=(), **extra):
    """Dos nodos; la plantilla vive en storage compartido para que ambos sean aptos."""
    return MundoRed(
        extra={**_COMPARTIDA, **extra},
        nodos=("pve1", "pve2"),
        bridges={
            "pve1": (bridge("vmbr0"), bridge("vmbr1")),
            "pve2": tuple(bridge(b) for b in bridges_pve2),
        },
        redes_sdn={"pve1": tuple(vnet(v) for v in vnets_pve1), "pve2": ()},
    )


def _reglas_bloqueantes(plan):
    return [p.regla for p in plan.problemas if p.severidad.value == "error"]


def test_qa_c_m2_net0_cambiada_a_una_vnet_que_solo_existe_en_pve1_reparte_solo_en_pve1():
    m = _mundo_dos_nodos(vnets_pve1=("solo1",))
    plan = m.planificar(m.definicion(4, None, red_clon=red_clon(cambiar(0, bridge="solo1"))))
    assert not plan.bloqueado, plan.problemas
    assert _reglas_bloqueantes(plan) == []  # sin V-C11 ni V-16
    assert set(plan.reparto) == {"pve1"} and plan.reparto["pve1"][0] == 4
    libro = m.ejecutar(plan)
    assert set(m.estados(libro).values()) <= {EstadoMV.OK, EstadoMV.CON_AVISOS}
    assert m.cluster.vms[100]["config"]["net0"].endswith("bridge=solo1")


def test_qa_c_m2_control_sin_cambio_de_red_ambos_nodos_siguen_siendo_elegibles():
    m = _mundo_dos_nodos(vnets_pve1=("solo1",))
    plan = m.planificar(m.definicion(4, None, red_clon=red_clon(cambiar(0, bridge="vmbr0"))))
    assert set(plan.reparto) == {"pve1", "pve2"}


def test_qa_c_m2_quitar_una_tarjeta_cuyo_bridge_falta_en_un_nodo_no_descarta_ese_nodo():
    # net1 de la plantilla usa vmbr1, que pve2 no tiene.
    m = _mundo_dos_nodos(net1="virtio=AA:BB:CC:DD:EE:01,bridge=vmbr1")
    sin_quitar = m.planificar(m.definicion(4, None, red_clon=red_clon(cambiar(0, vlan=5))))
    assert set(sin_quitar.reparto) == {"pve1"}  # control: sin quitar, pve2 no sirve
    plan = m.planificar(m.definicion(4, None, red_clon=red_clon(quitar(1))))
    assert not plan.bloqueado, plan.problemas
    assert set(plan.reparto) == {"pve1", "pve2"}


def test_qa_c_m2_anadir_una_tarjeta_en_un_bridge_ausente_de_un_nodo_lo_descarta():
    m = _mundo_dos_nodos()
    plan = m.planificar(m.definicion(4, None, red_clon=red_clon(anadir(2, bridge="vmbr1"))))
    assert set(plan.reparto) == {"pve1"}


# --- QA-C-B3: «Permitir DHCP» en NO explícito envía dhcp=0 ---------------------------------------


@pytest.mark.parametrize("cloudinit", [None, ci()], ids=["sin_cloudinit", "cloudinit_dhcp"])
def test_qa_c_b3_dhcp_no_explicito_con_firewall_activo_envia_dhcp_0(cloudinit):
    m = apfw.MundoC()
    m.cl.fw_opciones[9000] = {"dhcp": 1}  # la plantilla traía dhcp=1: no se hereda
    r = m.crear(m.cfg(cloudinit, firewall=fw(dhcp=ModoDhcp.NO, politica_entrada=Politica.PERMITIR)))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r.error
    assert m.cl.fw_opciones[100]["dhcp"] in ("0", 0)


def test_qa_c_b3_sin_firewall_activo_no_hay_ninguna_peticion_de_firewall():
    m = apfw.MundoC()
    r = m.crear(m.cfg(ci(), firewall=FirewallMV(dhcp=ModoDhcp.NO)))
    assert r.desenlace == Desenlace.OK, r.error
    assert [c.ruta for c in m.cl.llamadas if "/firewall" in c.ruta] == []
    r2 = m.crear(dataclasses.replace(m.cfg(ci()), vmid=101, nombre="srv-web-02", firewall=None))
    assert r2.desenlace == Desenlace.OK, r2.error
    assert [c.ruta for c in m.cl.llamadas if "/firewall" in c.ruta] == []


# --- QA-C-B6: red_final cuando el paso de red no envía nada --------------------------------------


def test_qa_c_b6_paso_de_red_sin_envio_informa_las_tarjetas_leidas_en_el_resultado_y_el_libro():
    m = MundoRed(bridges={"pve1": (bridge("vmbr0"),)})
    r = m.crear(cfg_con_red(m, red_clon(cambiar(0, bridge="vmbr0"))))
    assert r.desenlace == Desenlace.OK, r.error
    assert m.cluster.puts_de_red(100) == []  # no se envió nada
    assert [t.indice for t in r.red_final] == [0, 1]
    assert {t.red for t in r.red_final} == {"vmbr0"}
    m2 = MundoRed(bridges={"pve1": (bridge("vmbr0"),)})
    libro = m2.ejecutar(
        m2.planificar(m2.definicion(1, None, red_clon=red_clon(cambiar(0, bridge="vmbr0"))))
    )
    assert [t.indice for t in libro.entrada(100).red_final] == [0, 1]


# --- Un 400 del POST de la regla solo es «grupo inexistente» si el grupo falta en la lista -------


def test_400_del_post_con_el_grupo_en_la_lista_es_un_error_generico():
    m = apfw.MundoC()
    fallar_fw(m.cl, "POST", "rules", error_http(400, "regla rara"))
    assert GRUPO in m.cl.grupos
    r = m.crear(m.cfg(None, firewall=fw()))
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo != CodigoError.FIREWALL_GRUPO_INEXISTENTE
    assert r.error.codigo == CodigoError.AJUSTE_POST_CLON_FALLIDO


def test_400_del_post_con_el_grupo_ausente_de_la_lista_es_firewall_grupo_inexistente():
    m = apfw.MundoC()
    m.cl.grupos.clear()
    r = m.crear(m.cfg(None, firewall=fw()))
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.FIREWALL_GRUPO_INEXISTENTE
    assert r.error.params["grupo"] == GRUPO


# --- SEG-C-M1 y SEG-C-B1: textos del servidor saneados -------------------------------------------

HOSTIL = "<b>pve</b>‮&\x07​" + "x" * 200


def test_seg_c_m1_el_nodo_de_cluster_resources_sale_saneado_y_acotado():
    from .apoyo_fase_c_inventario import Mundo

    m = Mundo()
    m.cluster.lista_cruda = [
        {"vmid": 100, "node": HOSTIL, "type": "qemu", "name": "a", "status": "stopped"}
    ]
    (r,) = m.sesion.cliente.recursos_vm()
    assert r.nodo is not None
    assert not set("<>&") & set(r.nodo)
    assert "‮" not in r.nodo and "​" not in r.nodo and "\x07" not in r.nodo
    assert len(r.nodo) <= 64


def test_seg_c_b1_reglas_de_grupo_con_type_y_action_hostiles_salen_saneadas():
    m = apfw.MundoC()
    m.cl.grupos[GRUPO] = [
        {"type": "<i>in</i>‮\n" + "t" * 500, "action": "AC&CE\x00PT" + "a" * 500, "enable": 1}
    ]
    (regla,) = m.sesion.cliente.reglas_grupo_firewall(GRUPO)
    for texto in (regla.tipo, regla.accion):
        assert len(texto) <= 64
        assert not set("<>&‮\n\x00") & set(texto)
    assert regla.tipo.startswith("iin") and regla.accion.startswith("ACCEPT")


def test_seg_c_b1_un_grupo_con_miles_de_reglas_devuelve_como_maximo_200():
    m = apfw.MundoC()
    m.cl.grupos[GRUPO] = [{"type": "in", "action": "ACCEPT", "enable": 1}] * 1000
    assert len(m.sesion.cliente.reglas_grupo_firewall(GRUPO)) == 200
    m.cl.fw_reglas[100] = [{"type": "in", "action": "DROP", "enable": 1}] * 1000
    assert len(m.sesion.cliente.reglas_firewall_vm("pve1", 100)) == 200


# --- SEG-C-M2: con el firewall pedido y una tarjeta ilegible la MV no se enciende -----------------


def _mundo_tarjeta_ilegible(**plantilla):
    from .apoyo_fase_b_p1 import config_plantilla

    cfg = config_plantilla(redes=2, net1="esto no se entiende", **plantilla)
    return apfw.MundoC(plantillas={9000: ("base", cfg)})


AVISO_NO_ENCENDIDA = f"{AVISO_FIREWALL_INCOMPLETO_NO_ENCENDIDA}:net1"


def test_seg_c_m2_firewall_con_tarjeta_ilegible_y_encender_no_enciende_la_mv():
    m = _mundo_tarjeta_ilegible()
    r = m.crear(m.cfg(None, firewall=fw(), encender=True))
    assert "start" not in secuencia(m.cl)
    assert r.desenlace == Desenlace.CON_AVISOS, (r.desenlace, r.error, r.avisos)
    assert AVISO_NO_ENCENDIDA in r.avisos
    assert m.cl.vms[100]["status"] != "running"


def test_seg_c_m2_en_un_lote_la_entrada_queda_con_avisos_y_apagada():
    m = _mundo_tarjeta_ilegible()
    m.leer_firewall()
    libro = m.ejecutar(m.planificar(m.definicion(1, None, firewall=fw(), encender=True)))
    e = libro.entrada(100)
    assert e.estado == EstadoMV.CON_AVISOS, (e.estado, e.avisos)
    assert AVISO_NO_ENCENDIDA in e.avisos
    assert "start" not in secuencia(m.cl)


def test_seg_c_m2_la_simulacion_anuncia_que_no_se_encendera():
    from proxlaunch.nucleo.lote.simulacion import avisos_de_simulacion, simular

    m = _mundo_tarjeta_ilegible()
    res = simular(
        m.sesion, m.definicion(1, None, firewall=fw(), encender=True), m.inv, reloj=m.reloj
    )
    avisos = avisos_de_simulacion(res, m.inv, 100)
    assert AVISO_NO_ENCENDIDA in avisos


def test_seg_c_m2_con_todas_las_tarjetas_legibles_la_mv_si_se_enciende():
    m = apfw.MundoC()
    r = m.crear(m.cfg(None, firewall=fw(), encender=True))
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    assert "start" in secuencia(m.cl)
    assert not any(a.startswith(AVISO_FIREWALL_INCOMPLETO_NO_ENCENDIDA) for a in r.avisos)


def test_seg_c_m2_sin_firewall_la_tarjeta_ilegible_no_impide_encender():
    m = _mundo_tarjeta_ilegible()
    r = m.crear(m.cfg(None, encender=True))
    assert "start" in secuencia(m.cl)
    assert AVISO_NO_ENCENDIDA not in r.avisos


# --- SEG-C-B2: acepto_aislada no se guarda en el lote v5 -----------------------------------------


def _lote_con_firewall(**kw):
    from .test_fase_c_archivos import lote_c

    return lote_c(firewall=FirewallMV(**kw))


def test_seg_c_b2_un_lote_v5_escrito_no_contiene_acepto_aislada():
    from .test_fase_c_archivos import bytes_de

    datos = bytes_de(_lote_con_firewall(activo=True, grupo=None, acepto_aislada=True))
    assert b"acepto_aislada" not in datos
    assert json.loads(datos)["version_formato"] == 5


def test_seg_c_b2_un_lote_que_la_trae_se_lee_sin_error_y_con_la_casilla_desmarcada():
    from proxlaunch.nucleo.lotes_guardados.formato import leer_lote

    from .test_fase_c_archivos import bytes_de

    cuerpo = json.loads(bytes_de(_lote_con_firewall(activo=True, grupo=None)))
    cuerpo["homogeneo"]["config"]["firewall"]["acepto_aislada"] = True
    leido = leer_lote(json.dumps(cuerpo).encode())
    fwl = leido.lote.definicion.plantilla.firewall
    assert fwl is not None and fwl.activo is True
    assert fwl.acepto_aislada is False


# --- SEG-C-S1: firewall activo sin lectura del catálogo da V-C34 ----------------------------------


def test_seg_c_s1_firewall_activo_sin_lectura_del_catalogo_da_v_c34():
    from proxlaunch.nucleo.capacidades import capacidades_para
    from proxlaunch.nucleo.firewall.validacion import validar_firewall

    m = apfw.MundoC()
    inv = dataclasses.replace(m.inv, catalogo=dataclasses.replace(m.inv.catalogo, firewall=None))
    problemas = validar_firewall(m.cfg(None, firewall=fw()), inv, capacidades_para(m.version, None))
    assert [p.codigo for p in problemas] == ["V-C34"]


def test_seg_c_s1_con_el_firewall_apagado_no_hay_v_c34():
    from proxlaunch.nucleo.capacidades import capacidades_para
    from proxlaunch.nucleo.firewall.validacion import validar_firewall

    m = apfw.MundoC()
    inv = dataclasses.replace(m.inv, catalogo=dataclasses.replace(m.inv.catalogo, firewall=None))
    assert validar_firewall(m.cfg(None), inv, capacidades_para(m.version, None)) == []
