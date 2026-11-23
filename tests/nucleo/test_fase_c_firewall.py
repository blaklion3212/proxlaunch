"""Firewall con grupo de seguridad (C3, fase C, 0.8.0): validación V-C30..V-C40/V-C50/V-C52,
lecturas de «Comprobar», planificación de lotes, simulación e informe de riesgo.

Requisitos: RF-C3.2 (CA-C3.2.1 a CA-C3.2.3), RF-C3.3 (CA-C3.3.2), RF-C3.4 (CA-C3.4.2, CA-C3.4.4),
RF-C3.5 (CA-C3.5.1 a CA-C3.5.5), RF-C3.6 (CA-C3.6.1, CA-C3.6.3, CA-C3.6.5), RF-C3.9 (CA-C3.9.1 a
CA-C3.9.4), RF-C0.1 (CA-C0.1.2, CA-C0.1.3), RF-C0.3 (CA-C0.3.2, CA-C0.3.3), RF-C0.4 (CA-C0.4.1),
CA-C3.8.5 (parte automática), CA-C12.1 (V-C30..V-C40, V-C50, V-C52), RNF-C5 (carga), RNF-C6
(grupos validados y saneados) y P-C5/P-C6.

Los dobles son ``ClusterC`` (``MundoC``) para lo que pasa por la red y ``InfoFirewall`` armada a
mano para las reglas puras de validación.
"""

from __future__ import annotations

import dataclasses

import pytest

from proxlaunch.nucleo.capacidades import Capacidades, Funcion, capacidades_para
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.lectura import (
    leer_grupos,
    leer_info_firewall,
    leer_reglas_grupo,
)
from proxlaunch.nucleo.firewall.modelos import (
    FirewallMV,
    FirewallPlantilla,
    GrupoSeguridad,
    InfoFirewall,
    ModoDhcp,
    Politica,
    ReglaFirewall,
    firewall_a_dict,
    firewall_desde_dict,
)
from proxlaunch.nucleo.firewall.reglas import (
    parametros_opciones,
    parametros_regla,
    permite_entrada,
    regla_ya_existe,
)
from proxlaunch.nucleo.firewall.validacion import validar_firewall
from proxlaunch.nucleo.lote.informe import riesgo_firewall_parcial
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    AccionPeticion,
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
)
from proxlaunch.nucleo.lote.simulacion import avisos_de_simulacion, simular
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.origen import AjustesClon
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.servicios.creacion import ajustes_planeados
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_fase_b_p1 import CENTINELA, PRIVS_B_92, MundoB, ci, ci_completa, config_plantilla
from .apoyo_fase_c_firewall import GRUPO, MundoC, fw, secuencia
from .apoyo_lote import error_http
from .apoyo_mvp4 import VOLID_IMAGEN, VOLID_ISO, cfg_clon, cfg_iso

CAPS = capacidades_para(MundoB().version, None)


def _info(**cambios) -> InfoFirewall:
    base = {
        "grupos": (GrupoSeguridad(GRUPO), GrupoSeguridad("db", "base de datos")),
        "general_activo": True,
        "entrada_por_grupo": {GRUPO: True, "db": True},
    }
    base.update(cambios)
    return InfoFirewall(**base)


def _validar(cfg, info=None, *, mundo=None, caps=CAPS, permisos="defecto"):
    """Problemas de ``validar_firewall`` con ``info`` en el catálogo del inventario."""
    m = mundo or MundoB()
    cat = m.inv.catalogo
    cambios = {"firewall": info}
    if permisos != "defecto":
        cambios["permisos"] = permisos
    inv = dataclasses.replace(m.inv, catalogo=dataclasses.replace(cat, **cambios))
    return validar_firewall(cfg, inv, caps)


def _codigo(p) -> str:
    """Código V-xx de un problema (el de la validación de una MV o el del plan de un lote)."""
    return getattr(p, "regla", None) or p.codigo


def _reglas(problemas) -> list[str]:
    return [_codigo(p) for p in problemas]


def _por_regla(problemas, regla):
    return [p for p in problemas if _codigo(p) == regla]


def _cfg(cloudinit=None, *, m=None, **kw):
    return (m or MundoB()).cfg(cloudinit, **kw)


# --- RF-C3.2: grupo, formato (V-C31) y existencia (V-C30) -------------------------------------


@pytest.mark.parametrize("nombre", ["web", "web-01", "ab", "a" + "b" * 17, "Web_01", "g-1_x"])
def test_ca_c3_2_1_nombres_validos_se_aceptan(nombre):
    """CA-C3.2.1: de 2 a 18 caracteres, empieza por letra; letras, números, guion y guion bajo."""
    info = _info(grupos=(GrupoSeguridad(nombre),), entrada_por_grupo={nombre: True})
    assert _validar(_cfg(firewall=fw(nombre)), info) == []


@pytest.mark.parametrize(
    "nombre",
    ["1web", "a", "b" * 19, "con espacio", "web,db", "-web", "_web", "web!", "web\n", "", "w\x00b"],
)
def test_ca_c3_2_1_nombres_invalidos_dan_v_c31_error_y_no_se_comparan_con_el_servidor(nombre):
    """CA-C3.2.1 / V-C31 / RNF-C6.3: un nombre dudoso nunca llega a una petición."""
    problemas = _validar(_cfg(firewall=fw(nombre)), _info())
    assert _reglas(problemas) == ["V-C31"]
    assert problemas[0].severidad == Severidad.ERROR and problemas[0].campo == "firewall.grupo"
    assert not nombre or nombre not in str(problemas[0].params)  # nunca eco del valor


def test_ca_c3_2_2_grupo_inexistente_da_v_c30_con_el_nombre_en_los_params():
    problemas = _validar(_cfg(firewall=fw("inventado")), _info())
    assert _reglas(problemas) == ["V-C30"]
    assert problemas[0].severidad == Severidad.ERROR
    assert problemas[0].params == {"grupo": "inventado"}


def test_ca_c3_2_3_lista_ilegible_da_v_c32_error():
    info = _info(grupos=None, error_grupos=ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}))
    problemas = _validar(_cfg(firewall=fw()), info)
    assert _reglas(problemas) == ["V-C32"] and problemas[0].severidad == Severidad.ERROR


def test_ca_c3_2_3_con_lista_ilegible_se_puede_crear_sin_grupo():
    """«El resto de la app funciona»: sin grupo no hace falta la lista."""
    info = _info(grupos=None, error_grupos=ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}))
    problemas = _validar(_cfg(firewall=fw(None, politica_entrada=Politica.PERMITIR)), info)
    assert [p for p in problemas if p.severidad == Severidad.ERROR] == []


def test_ca_c3_2_2_sin_lecturas_de_firewall_no_se_afirma_nada_del_grupo():
    """Sin «Comprobar» (``info=None``) no hay V-C30/V-C32, pero sí V-C34 (SEG-C-S1)."""
    assert _reglas(_validar(_cfg(firewall=fw("inventado")), None)) == ["V-C34"]


# --- RF-C3.9: aislamiento (V-C36) y grupo sin entrada (V-C38) ---------------------------------


def test_ca_c3_9_1_sin_grupo_entrada_bloquear_y_sin_confirmar_da_v_c36_error():
    problemas = _validar(_cfg(firewall=fw(None)), _info())
    assert _reglas(problemas) == ["V-C36"] and problemas[0].severidad == Severidad.ERROR


def test_ca_c3_9_1_con_la_casilla_marcada_v_c36_es_solo_un_aviso():
    problemas = _validar(_cfg(firewall=fw(None, acepto_aislada=True)), _info())
    assert _reglas(problemas) == ["V-C36"] and problemas[0].severidad == Severidad.AVISO


def test_ca_c3_9_4_con_la_entrada_permitir_no_se_exige_la_casilla():
    """P-C6: Permitir entrada sin grupo es válido y sin avisos de aislamiento."""
    assert _validar(_cfg(firewall=fw(None, politica_entrada=Politica.PERMITIR)), _info()) == []


def test_ca_c3_9_1_con_grupo_no_se_exige_la_casilla():
    assert _por_regla(_validar(_cfg(firewall=fw()), _info()), "V-C36") == []


def test_ca_c3_9_2_un_grupo_solo_con_reglas_de_salida_da_v_c38_aviso():
    info = _info(entrada_por_grupo={GRUPO: False})
    problemas = _validar(_cfg(firewall=fw()), info)
    assert _reglas(problemas) == ["V-C38"] and problemas[0].severidad == Severidad.AVISO
    assert problemas[0].params == {"grupo": GRUPO}


def test_ca_c3_9_3_un_grupo_con_regla_de_entrada_accept_no_da_v_c38():
    assert _por_regla(_validar(_cfg(firewall=fw()), _info()), "V-C38") == []


def test_ca_c3_9_2_si_no_se_puede_leer_el_contenido_del_grupo_no_se_afirma_v_c38():
    """Sin ``Sys.Audit`` el contenido es ``None``: ni aviso ni error (texto genérico en la UI)."""
    info = _info(entrada_por_grupo={GRUPO: None})
    assert _por_regla(_validar(_cfg(firewall=fw()), info), "V-C38") == []


@pytest.mark.parametrize(
    ("reglas", "esperado"),
    [
        ([ReglaFirewall("in", "ACCEPT", True)], True),
        ([ReglaFirewall("in", "accept", True)], True),
        ([ReglaFirewall("in", "ACCEPT", False)], False),
        ([ReglaFirewall("out", "ACCEPT", True)], False),
        ([ReglaFirewall("in", "DROP", True)], False),
        ([ReglaFirewall("in", "REJECT", True)], False),
        ([ReglaFirewall("out", "ACCEPT", True), ReglaFirewall("in", "ACCEPT", True)], True),
        ([], False),
    ],
)
def test_ca_c3_9_3_permite_entrada_solo_con_una_regla_in_accept_activa(reglas, esperado):
    assert permite_entrada(reglas) is esperado


# --- RF-C3.4: DHCP (V-C37) --------------------------------------------------------------------


def test_ca_c3_4_2_dhcp_desmarcada_con_dhcp_cloudinit_y_entrada_bloquear_da_v_c37_aviso():
    cfg = _cfg(ci(), firewall=fw(dhcp=ModoDhcp.NO))
    problemas = _validar(cfg, _info())
    assert _reglas(problemas) == ["V-C37"] and problemas[0].severidad == Severidad.AVISO
    assert problemas[0].campo == "firewall.dhcp"


def test_ca_c3_4_4_con_entrada_permitir_no_aparece_v_c37():
    cfg = _cfg(ci(), firewall=fw(dhcp=ModoDhcp.NO, politica_entrada=Politica.PERMITIR))
    assert _por_regla(_validar(cfg, _info()), "V-C37") == []


@pytest.mark.parametrize("modo", [ModoDhcp.AUTO, ModoDhcp.SI])
def test_ca_c3_4_2_con_dhcp_automatico_o_marcado_no_aparece_v_c37(modo):
    assert _por_regla(_validar(_cfg(ci(), firewall=fw(dhcp=modo)), _info()), "V-C37") == []


def test_ca_c3_4_3_sin_dhcp_de_cloudinit_no_aparece_v_c37():
    cfg = _cfg(ci_completa(), firewall=fw(dhcp=ModoDhcp.NO))
    assert _por_regla(_validar(cfg, _info()), "V-C37") == []


@pytest.mark.parametrize(
    ("modo", "cloudinit", "esperado"),
    [
        (ModoDhcp.AUTO, ci(), True),
        (ModoDhcp.AUTO, ci_completa(), False),
        (ModoDhcp.AUTO, None, False),
        (ModoDhcp.SI, None, True),
        (ModoDhcp.NO, ci(), True),  # NO explícito: ``dhcp=0``
    ],
)
def test_ca_c3_4_1_parametros_de_opciones_dhcp_solo_cuando_procede(modo, cloudinit, esperado):
    """RF-C3.4: ``dhcp=1`` con SI o con AUTO y DHCP por cloud-init; NO explícito envía ``dhcp=0``;
    AUTO sin DHCP, sin la clave."""
    m = MundoB()
    cfg = m.cfg(cloudinit)
    assert ("dhcp" in parametros_opciones(fw(dhcp=modo), cfg)) is esperado


# --- RF-C3.5: firewall general (V-C33/V-C34) --------------------------------------------------


def test_ca_c3_5_1_firewall_general_apagado_da_v_c33_aviso_y_no_bloquea():
    problemas = _validar(_cfg(firewall=fw()), _info(general_activo=False))
    assert _reglas(problemas) == ["V-C33"] and problemas[0].severidad == Severidad.AVISO


def test_ca_c3_5_2_firewall_general_encendido_no_da_aviso():
    assert _validar(_cfg(firewall=fw()), _info(general_activo=True)) == []


def test_ca_c3_5_3_firewall_general_ilegible_da_v_c34_aviso():
    problemas = _validar(_cfg(firewall=fw()), _info(general_activo=None))
    assert _reglas(problemas) == ["V-C34"] and problemas[0].severidad == Severidad.AVISO


def test_ca_c3_5_1_el_plan_con_el_firewall_general_apagado_avisa_pero_no_bloquea_y_crea():
    m = MundoC()
    m.cl.general = {"enable": 0}
    plan = m.planificar(m.definicion(2, ci(), firewall=fw()))
    assert not plan.bloqueado
    assert "V-C33" in [p.regla for p in plan.problemas]
    libro = m.ejecutar(plan)
    assert set(m.estados(libro).values()) == {EstadoMV.OK}


def test_ca_c3_5_2_el_plan_con_el_firewall_general_encendido_no_avisa():
    m = MundoC()
    plan = m.planificar(m.definicion(2, ci(), firewall=fw()))
    assert list(plan.problemas) == []


def test_ca_c3_5_3_un_403_al_leer_el_firewall_general_da_v_c34_y_no_bloquea():
    m = MundoC()
    m.cl.general = error_http(403, "Permission check failed (/, Sys.Audit)")
    plan = m.planificar(m.definicion(2, ci(), firewall=fw()))
    assert not plan.bloqueado
    assert [p.regla for p in plan.problemas] == ["V-C34"]
    assert set(m.estados(m.ejecutar(plan)).values()) == {EstadoMV.OK}


def test_ca_c3_5_3_sin_sys_audit_no_se_pide_el_firewall_general_ni_el_contenido_del_grupo():
    """Sin el privilegio no se hace la petición (no se provoca un 403 inútil) y sale V-C34."""
    privs = [p for p in PRIVS_B_92 if p != "Sys.Audit"]
    m = MundoC(privilegios=privs)
    plan = m.planificar(m.definicion(1, ci(), firewall=fw()))
    assert not plan.bloqueado
    assert not [c for c in m.cl.llamadas if c.ruta == "/cluster/firewall/options"]
    assert not [c for c in m.cl.llamadas if c.ruta.startswith("/cluster/firewall/groups/")]
    assert "V-C34" in [p.regla for p in plan.problemas]


def test_ca_c3_5_4_un_lote_de_50_mvs_lee_el_firewall_general_una_sola_vez():
    """CA-C3.5.4 / RNF-C5: una lectura de grupos, una del general, una del grupo elegido y una
    (opciones + reglas) por plantilla distinta; ninguna por MV."""
    m = MundoC()
    plan = m.planificar(m.definicion(50, ci(), firewall=fw()))
    assert not plan.bloqueado, plan.problemas
    lecturas = [c.ruta for c in m.cl.lecturas_fw()]
    assert lecturas.count("/cluster/firewall/options") == 1
    assert lecturas.count("/cluster/firewall/groups") == 1
    assert lecturas.count(f"/cluster/firewall/groups/{GRUPO}") == 1
    assert lecturas.count("/nodes/pve1/qemu/9000/firewall/options") == 1
    assert lecturas.count("/nodes/pve1/qemu/9000/firewall/rules") == 1
    assert len(lecturas) == 5


def test_ca_c3_5_4_con_dos_plantillas_distintas_se_lee_cada_una_una_vez():
    m = MundoC(
        plantillas={
            9000: ("base", config_plantilla()),
            9001: ("otra", config_plantilla()),
        }
    )
    info = leer_info_firewall(
        m.sesion.cliente, m.inv.catalogo.permisos, (GRUPO,), list(m.inv.catalogo.plantillas) * 2
    )
    assert set(info.plantillas) == {9000, 9001}
    reglas_leidas = [c.ruta for c in m.cl.lecturas_fw("/rules")]
    assert sorted(reglas_leidas) == [
        "/nodes/pve1/qemu/9000/firewall/rules",
        "/nodes/pve1/qemu/9001/firewall/rules",
    ]


def test_ca_c3_5_5_la_lectura_de_firewall_son_solo_get():
    m = MundoC()
    m.cl.reiniciar_llamadas()
    m.planificar(m.definicion(3, ci(), firewall=fw()))
    assert m.cl.solo_lecturas


# --- RF-C3.2 (plan): V-C30, V-C32 -------------------------------------------------------------


def test_ca_c3_2_2_un_grupo_inventado_bloquea_el_plan_con_v_c30_y_no_se_escribe_nada():
    """CA-C3.2.2 (equivalente de lote guardado/CSV: el grupo viene en la definición)."""
    m = MundoC()
    plan = m.planificar(m.definicion(3, ci(), firewall=fw("inventado")))
    assert plan.bloqueado
    assert [p.regla for p in plan.problemas] == ["V-C30"]
    assert plan.problemas[0].params["grupo"] == "inventado"
    assert m.cl.solo_lecturas
    assert m.cl.posts == {} and m.cl.clones == {}
    # no se pide el contenido de un grupo que no existe
    assert not [c for c in m.cl.llamadas if c.ruta == "/cluster/firewall/groups/inventado"]


def test_ca_c3_2_3_un_403_al_listar_los_grupos_bloquea_con_v_c32_pero_sin_grupo_se_crea():
    m = MundoC()
    m.cl.grupos_fallo = error_http(403, "Permission check failed (/, Sys.Audit)")
    plan = m.planificar(m.definicion(2, ci(), firewall=fw()))
    assert plan.bloqueado and "V-C32" in [p.regla for p in plan.problemas]
    m2 = MundoC()
    m2.cl.grupos_fallo = error_http(500, "boom")
    plan2 = m2.planificar(
        m2.definicion(2, ci(), firewall=fw(None, politica_entrada=Politica.PERMITIR))
    )
    assert not plan2.bloqueado, plan2.problemas
    assert set(m2.estados(m2.ejecutar(plan2)).values()) == {EstadoMV.OK}


def test_ca_c3_9_1_el_plan_sin_grupo_con_entrada_bloquear_exige_la_casilla():
    """P-C6: el lote se bloquea con V-C36; con la casilla pasa y sin ``POST …/rules``."""
    m = MundoC()
    bloqueado = m.planificar(m.definicion(2, ci(), firewall=fw(None)))
    assert bloqueado.bloqueado and [p.regla for p in bloqueado.problemas] == ["V-C36"]
    assert m.cl.solo_lecturas
    m2 = MundoC()
    plan = m2.planificar(m2.definicion(2, ci(), firewall=fw(None, acepto_aislada=True)))
    assert not plan.bloqueado
    assert [(p.regla, p.severidad) for p in plan.problemas] == [("V-C36", Severidad.AVISO)]
    m2.ejecutar(plan)
    assert not m2.cl.llamadas_a("POST", r"/firewall/rules")


def test_ca_c3_9_2_el_plan_avisa_si_el_grupo_no_permite_ninguna_entrada():
    m = MundoC()
    m.cl.grupos[GRUPO] = [{"type": "out", "action": "ACCEPT", "enable": 1}]
    plan = m.planificar(m.definicion(2, ci(), firewall=fw()))
    assert not plan.bloqueado
    assert [p.regla for p in plan.problemas] == ["V-C38"]


def test_ca_c3_9_3_el_plan_con_un_grupo_que_permite_ssh_no_avisa():
    m = MundoC()
    m.cl.grupos[GRUPO] = [
        {"type": "in", "action": "ACCEPT", "proto": "tcp", "dport": "22", "enable": 1}
    ]
    assert list(m.planificar(m.definicion(2, ci(), firewall=fw())).problemas) == []


def test_ca_c3_6_1_el_plan_agrupa_el_aviso_v_c35_de_la_plantilla_una_sola_vez():
    """CA-C12.2: 100 filas con la misma plantilla dan un solo aviso agrupado."""
    m = MundoC()
    m.cl.fw_opciones[9000] = {"enable": 1}
    plan = m.planificar(m.definicion(100, ci(), firewall=fw()))
    avisos = [p for p in plan.problemas if p.regla == "V-C35"]
    assert len(avisos) == 1 and not plan.bloqueado


def test_ca_c3_6_5_una_plantilla_ilegible_da_v_c35_de_no_comprobable_y_no_bloquea():
    m = MundoC()
    from .apoyo_fase_c_firewall import fallar_fw

    fallar_fw(
        m.cl,
        "GET",
        "options",
        error_http(403, "Permission check failed (/vms/9000, VM.Audit)"),
        vmid=9000,
    )
    plan = m.planificar(m.definicion(2, ci(), firewall=fw()))
    assert not plan.bloqueado
    v35 = [p for p in plan.problemas if p.regla == "V-C35"]
    assert len(v35) == 1 and v35[0].params["motivo"] == "no_comprobable"


def test_ca_c3_6_3_una_plantilla_sin_firewall_no_da_v_c35():
    m = MundoC()
    assert [p.regla for p in m.planificar(m.definicion(2, ci(), firewall=fw())).problemas] == []


def test_ca_c3_6_1_v_c35_solo_aplica_al_origen_clon():
    m = MundoC()
    info = _info(plantillas={9000: FirewallPlantilla(True, True, frozenset(), True)})
    cfg = dataclasses.replace(cfg_clon("base"), firewall=fw(), origen=_origen_iso())
    assert _por_regla(_validar(cfg, info, mundo=m), "V-C35") == []


def _origen_iso():
    from proxlaunch.nucleo.modelos.vm import OrigenSO

    return OrigenSO.ISO


# --- RF-C0.3 / RF-C0.4: permisos (V-C40) y versión (V-C50) ------------------------------------


def test_ca_c0_3_3_sin_vm_config_network_comprobar_impide_crear_con_v_c40():
    privs = [p for p in PRIVS_B_92 if p != "VM.Config.Network"]
    m = MundoC(privilegios=privs)
    plan = m.planificar(m.definicion(2, ci(), firewall=fw()))
    assert plan.bloqueado
    v40 = [p for p in plan.problemas if p.regla == "V-C40"]
    assert v40 and v40[0].severidad == Severidad.ERROR
    assert v40[0].params["privilegio"] == "VM.Config.Network" and v40[0].params["ruta"] == "/vms"
    assert m.cl.solo_lecturas


def test_ca_c0_3_2_con_permisos_desconocidos_no_hay_v_c40():
    """``estado_privilegio == None``: el control queda habilitado y se decide al enviar."""
    m = MundoC(privilegios=None)
    assert (
        _por_regla(_validar(_cfg(m=m, firewall=fw()), _info(), mundo=m, permisos=None), "V-C40")
        == []
    )


def test_ca_c0_3_2_con_permisos_desconocidos_un_403_de_firewall_nombra_el_privilegio():
    from .apoyo_fase_c_firewall import fallar_fw

    m = MundoC(privilegios=None)
    fallar_fw(m.cl, "PUT", "options", error_http(403, "Permission denied"))
    r = m.crear(m.cfg(None, firewall=fw()))
    assert r.error is not None and r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["privilegio"] == "VM.Config.Network"


def test_ca_c0_3_3_permiso_concedido_solo_en_vms_tambien_vale():
    privs = tuple(p for p in PRIVS_B_92 if p != "VM.Config.Network")
    perm = PermisosEfectivos(rutas={"/": dict.fromkeys(privs, 1), "/vms": {"VM.Config.Network": 1}})
    m = MundoB()
    assert (
        _por_regla(_validar(_cfg(m=m, firewall=fw()), _info(), mundo=m, permisos=perm), "V-C40")
        == []
    )


@pytest.mark.parametrize("version", [(8, 0), (8, 4), (9, 0), (9, 2)])
def test_ca_c0_4_1_firewall_grupo_esta_disponible_desde_8_0(version):
    caps = Capacidades(version=version, forzada=True)
    assert caps.tiene(Funcion.FIREWALL_GRUPO)
    assert _por_regla(_validar(_cfg(firewall=fw()), _info(), caps=caps), "V-C50") == []


def test_ca_c12_1_v_c50_en_una_version_sin_grupos_de_seguridad_es_error():
    caps = Capacidades(version=(7, 4), forzada=True)
    problemas = _validar(_cfg(firewall=fw()), _info(), caps=caps)
    v50 = _por_regla(problemas, "V-C50")
    assert v50 and v50[0].severidad == Severidad.ERROR and v50[0].params == {"version": "8.0"}


# --- V-C52 y V-C39 ----------------------------------------------------------------------------


def test_ca_c6_3_9_grupo_con_el_firewall_apagado_da_v_c52_error():
    problemas = _validar(_cfg(firewall=FirewallMV(activo=False, grupo=GRUPO)), _info())
    assert _reglas(problemas) == ["V-C52"] and problemas[0].severidad == Severidad.ERROR


@pytest.mark.parametrize(
    "fwm",
    [
        FirewallMV(activo=False, politica_entrada=Politica.PERMITIR),
        FirewallMV(activo=False, politica_salida=Politica.BLOQUEAR),
    ],
)
def test_ca_c6_3_9_politicas_cambiadas_con_el_firewall_apagado_dan_v_c52(fwm):
    assert _reglas(_validar(_cfg(firewall=fwm), _info())) == ["V-C52"]


@pytest.mark.parametrize("fwm", [None, FirewallMV(), FirewallMV(activo=False)])
def test_ca_c0_1_3_sin_firewall_o_con_el_valor_por_defecto_no_se_valida_nada(fwm):
    assert _validar(_cfg(firewall=fwm), _info(grupos=None)) == []


@pytest.mark.parametrize("valor", ["REJECT", "reject", "rechazar", "xyz", "", None, 1])
def test_ca_c3_3_2_una_politica_desconocida_o_reject_se_rechaza_al_deserializar(valor):
    """CA-C3.3.2 / V-C39: el enumerado hace imposible un valor distinto de Bloquear/Permitir."""
    with pytest.raises(ErrorProxLaunch) as e:
        firewall_desde_dict({"activo": True, "politica_entrada": valor})
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO
    assert e.value.params["campo"] == "firewall.politica_entrada"


def test_ca_c3_3_2_la_salida_desconocida_tambien_se_rechaza():
    with pytest.raises(ErrorProxLaunch) as e:
        firewall_desde_dict({"activo": True, "politica_salida": "REJECT"})
    assert e.value.params["campo"] == "firewall.politica_salida"


def test_ca_c3_1_firewall_ida_y_vuelta_de_lote_guardado():
    original = FirewallMV(True, GRUPO, Politica.PERMITIR, Politica.BLOQUEAR, ModoDhcp.NO, True)
    assert firewall_desde_dict(firewall_a_dict(original)) == original
    assert firewall_desde_dict(firewall_a_dict(FirewallMV())) == FirewallMV()


@pytest.mark.parametrize(
    "malo",
    [{"activo": "si"}, {"activo": True, "grupo": 5}, {"activo": True, "dhcp": "tal"}, [], "x"],
)
def test_ca_c6_1_firewall_malformado_en_un_lote_guardado_se_rechaza_con_el_campo(malo):
    with pytest.raises(ErrorProxLaunch) as e:
        firewall_desde_dict(malo)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO


# --- Parámetros puros -------------------------------------------------------------------------


def test_ca_c3_7_3_parametros_de_regla_exactos_y_sin_nombres_dudosos():
    assert parametros_regla("web") == {
        "type": "group",
        "action": "web",
        "enable": "1",
        "comment": "ProxLaunch",
    }
    for malo in ("1web", "a b", "x,y", ""):
        with pytest.raises(ValueError):
            parametros_regla(malo)


def test_ca_c3_8_3_regla_ya_existe_solo_con_el_mismo_grupo_y_tipo_group():
    reglas = [ReglaFirewall("group", "db", True), ReglaFirewall("in", GRUPO, True)]
    assert not regla_ya_existe(reglas, GRUPO)
    assert regla_ya_existe([*reglas, ReglaFirewall("group", GRUPO, True)], GRUPO)


def test_ca_c3_1_ver_la_ayuda_los_params_de_opciones_incluyen_siempre_las_dos_politicas():
    """RF-C3.3: se envían explícitas, sin depender de los valores por defecto de cada versión."""
    p = parametros_opciones(FirewallMV(activo=True), MundoB().cfg())
    assert set(p) == {"enable", "policy_in", "policy_out"}


# --- Lecturas (firewall/lectura.py) -----------------------------------------------------------


def test_ca_c3_1_5_grupos_con_nombre_invalido_se_omiten_y_el_comentario_se_sanea():
    """CA-C3.1.5 / RNF-C6.2: texto de servidor no confiable."""
    m = MundoC()
    m.cl.grupos = {GRUPO: [], "con espacio": [], "1x": [], "ok_2": []}
    m.cl.comentarios_grupo = {GRUPO: "Web\x00 pública\x1b[31m" + "x" * 500, "ok_2": "<b>hola</b>"}
    lectura = leer_grupos(m.sesion.cliente)
    nombres = [g.nombre for g in lectura.grupos]
    assert nombres == [GRUPO, "ok_2"]
    for g in lectura.grupos:
        assert len(g.comentario) <= 128
        assert not any(ord(c) < 32 for c in g.comentario)


def test_ca_c3_2_5_200_grupos_se_leen_con_una_sola_peticion():
    m = MundoC()
    m.cl.grupos = {f"g{i:03d}": [] for i in range(200)}
    lectura = leer_grupos(m.sesion.cliente)
    assert len(lectura.grupos) == 200
    assert len(m.cl.lecturas_fw()) == 1


def test_ca_c3_2_3_leer_grupos_nunca_lanza_y_anota_el_error():
    m = MundoC()
    m.cl.grupos_fallo = error_http(500, "boom")
    lectura = leer_grupos(m.sesion.cliente)
    assert lectura.grupos is None and lectura.error is not None


def test_leer_reglas_grupo_rechaza_nombres_invalidos_sin_enviar_nada():
    m = MundoC()
    reglas, error = leer_reglas_grupo(m.sesion.cliente, "../../etc")
    assert reglas is None and error is not None
    assert m.cl.llamadas == []


def test_leer_info_no_pide_el_contenido_de_un_grupo_inexistente_ni_repite_grupos():
    m = MundoC()
    info = leer_info_firewall(
        m.sesion.cliente, m.inv.catalogo.permisos, (GRUPO, GRUPO, "no_existe"), []
    )
    assert list(info.entrada_por_grupo) == [GRUPO]
    rutas = [c.ruta for c in m.cl.lecturas_fw()]
    assert rutas.count(f"/cluster/firewall/groups/{GRUPO}") == 1
    assert "/cluster/firewall/groups/no_existe" not in rutas


def test_leer_info_marca_el_firewall_de_la_plantilla_con_activo_reglas_y_grupos():
    m = MundoC()
    m.cl.fw_opciones[9000] = {"enable": 1}
    m.cl.fw_reglas[9000] = [{"type": "group", "action": GRUPO, "enable": 1}]
    info = leer_info_firewall(
        m.sesion.cliente, m.inv.catalogo.permisos, (GRUPO,), list(m.inv.catalogo.plantillas)
    )
    p = info.plantillas[9000]
    assert p.legible and p.activo is True and p.con_reglas is True and p.grupos == {GRUPO}


# --- RF-C0.1: simulación ----------------------------------------------------------------------


def _simular(m, definicion):
    return simular(m.sesion, definicion, m.inv, reloj=m.reloj)


def test_ca_c0_1_2_la_simulacion_de_un_clon_lista_los_pasos_en_el_orden_y_no_escribe():
    """CA-C0.1.2: clonar → ajustes → leer config → red → cloud-init → contraseña → opciones →
    regla → ampliar → encender; sin ninguna escritura real."""
    m = MundoC()
    base = dataclasses.replace(
        cfg_clon("base", ajustes=AjustesClon(cores=4, disco_gib=64)),
        cloudinit=ci_completa(Secreto(CENTINELA), serie=True),
        firewall=fw(),
        encender=True,
        discos=MundoB().cfg().discos,
        redes=MundoB().cfg().redes,
    )
    from .apoyo_fase_a import def_lote

    res = _simular(m, def_lote(2, plantilla_vm=base))
    assert not res.plan.bloqueado, res.plan.problemas
    assert m.cl.solo_lecturas
    for vmid, pasos in res.peticiones_detalle.items():
        acciones = [p.accion for p in pasos]
        assert acciones == [
            AccionPeticion.CLONAR,
            AccionPeticion.CONFIGURAR,
            AccionPeticion.LEER_CONFIG,
            AccionPeticion.RED,
            AccionPeticion.CLOUDINIT,
            AccionPeticion.CONTRASENA,
            AccionPeticion.FIREWALL_OPCIONES,
            AccionPeticion.FIREWALL_REGLA,
            AccionPeticion.AMPLIAR,
            AccionPeticion.ENCENDER,
        ], (vmid, acciones)
        regla = next(p for p in pasos if p.accion == AccionPeticion.FIREWALL_REGLA)
        assert regla.parametros == {
            "type": "group",
            "action": GRUPO,
            "enable": "1",
            "comment": "ProxLaunch",
        }
        red = next(p for p in pasos if p.accion == AccionPeticion.RED)
        assert red.parametros["net0"].endswith(",firewall=1")
        assert CENTINELA not in str([p.parametros for p in pasos])


def test_ca_c0_1_2_la_simulacion_sin_plantilla_regla_si_ya_estaba_y_avisos_previos():
    m = MundoC()
    m.cl.fw_opciones[9000] = {"enable": 1}
    m.cl.fw_reglas[9000] = [{"type": "group", "action": GRUPO, "enable": 1}]
    from .apoyo_fase_a import def_lote

    base = dataclasses.replace(
        cfg_clon("base"), firewall=fw(), discos=MundoB().cfg().discos, redes=MundoB().cfg().redes
    )
    res = _simular(m, def_lote(2, plantilla_vm=base))
    for vmid, pasos in res.peticiones_detalle.items():
        acciones = [p.accion for p in pasos]
        assert AccionPeticion.FIREWALL_OPCIONES in acciones
        assert AccionPeticion.FIREWALL_REGLA not in acciones  # P-C8
        avisos = avisos_de_simulacion(res, m.inv, vmid)
        assert f"firewall_grupo_ya_estaba:{GRUPO}" in avisos and "firewall_heredado" in avisos
    assert m.cl.solo_lecturas


@pytest.mark.parametrize("origen", ["iso", "vacio", "importar"])
def test_ca_c0_1_2_la_simulacion_de_los_otros_origenes_pone_el_firewall_tras_crear(origen):
    """P-C9: crear → opciones → regla (→ ampliar), con ``firewall=1`` ya en el POST."""
    from proxlaunch.nucleo.lote.planificador import Planificador  # noqa: F401

    from .apoyo_fase_a import def_lote
    from .apoyo_mvp4 import VOLID_IMAGEN, VOLID_ISO, cfg_import, cfg_iso

    m = MundoC()
    m.cl.contenido[("pve1", "local")] = [VOLID_ISO, VOLID_IMAGEN]
    base = {
        "iso": cfg_iso(firewall=fw(), etiquetas=("proxlaunch",)),
        "vacio": dataclasses.replace(MundoB().cfg(), origen=cfg_iso().origen),
        "importar": cfg_import(cfg={"firewall": fw()}, ampliar_a_gib=64),
    }[origen]
    if origen == "vacio":
        from .apoyo_fase_a import catalogo, cfg_vm, inv_con

        base = cfg_vm(firewall=fw())
        m.inv = inv_con(catalogo())
    res = simular(m.sesion, def_lote(2, plantilla_vm=base), m.inv, reloj=m.reloj)
    assert not res.plan.bloqueado, res.plan.problemas
    for vmid, pasos in res.peticiones_detalle.items():
        acciones = [p.accion for p in pasos]
        assert acciones[0] == AccionPeticion.CREAR
        assert acciones[1:3] == [AccionPeticion.FIREWALL_OPCIONES, AccionPeticion.FIREWALL_REGLA]
        assert res.peticiones[vmid]["net0"].endswith(",firewall=1")
    assert m.cl.solo_lecturas


def test_ca_c0_1_3_la_simulacion_sin_opciones_c_no_gana_ningun_paso():
    """CA-C0.1.3: ni lectura de config, ni red, ni firewall."""
    from .apoyo_fase_a import def_lote

    m = MundoC()
    base = dataclasses.replace(
        cfg_clon("base", ajustes=AjustesClon(cores=4)),
        cloudinit=ci(),
        discos=MundoB().cfg().discos,
        redes=MundoB().cfg().redes,
    )
    res = _simular(m, def_lote(2, plantilla_vm=base))
    prohibidas = {
        AccionPeticion.LEER_CONFIG,
        AccionPeticion.RED,
        AccionPeticion.FIREWALL_OPCIONES,
        AccionPeticion.FIREWALL_REGLA,
    }
    for pasos in res.peticiones_detalle.values():
        assert not {p.accion for p in pasos} & prohibidas
    assert avisos_de_simulacion(res, m.inv, 100) == ()
    assert not any("firewall" in c.ruta for c in m.cl.llamadas)


# --- ajustes planeados / informe de riesgo ----------------------------------------------------


def test_ca_c0_7_2_ajustes_planeados_incluye_los_pasos_de_firewall_en_orden():
    cfg = MundoB().cfg(ci_completa(Secreto(CENTINELA)), firewall=fw())
    assert ajustes_planeados(cfg) == (
        "red",
        "cloudinit",
        "contrasena",
        "firewall_opciones",
        "firewall_regla",
    )


def test_ca_c0_7_2_sin_grupo_no_se_planea_la_regla_y_sin_firewall_no_se_planea_nada():
    m = MundoB()
    assert ajustes_planeados(m.cfg(None, firewall=fw(None, acepto_aislada=True))) == (
        "red",
        "firewall_opciones",
    )
    assert ajustes_planeados(m.cfg(None, firewall=FirewallMV())) == ()
    assert ajustes_planeados(m.cfg(None)) == ()


def _entrada(estado, *, firewall, avisos=()):
    m = MundoB()
    cfg = m.cfg(None, firewall=firewall)
    e = ElementoPlan(0, "web-01", 100, "pve1", cfg)
    return EntradaLibro(e, estado, post_intentado=True, upid="UPID:x", avisos=tuple(avisos))


@pytest.mark.parametrize("pendiente", ["red", "firewall_opciones", "firewall_regla"])
def test_ca_c3_8_5_riesgo_de_firewall_parcial_con_cada_paso_pendiente(pendiente):
    e = _entrada(EstadoMV.PARCIAL, firewall=fw(), avisos=(f"ajuste_pendiente:{pendiente}",))
    assert riesgo_firewall_parcial(e) is True


@pytest.mark.parametrize(
    ("estado", "firewall", "avisos"),
    [
        (EstadoMV.PARCIAL, fw(), ("ajuste_pendiente:etiquetas",)),
        (EstadoMV.PARCIAL, FirewallMV(), ("ajuste_pendiente:red",)),
        (EstadoMV.PARCIAL, None, ("ajuste_pendiente:firewall_regla",)),
        (EstadoMV.OK, fw(), ()),
        (EstadoMV.CON_AVISOS, fw(), ("firewall_heredado",)),
        (EstadoMV.ERROR, fw(), ("ajuste_pendiente:firewall_regla",)),
    ],
)
def test_ca_c3_8_5_sin_firewall_a_medias_no_hay_riesgo(estado, firewall, avisos):
    assert riesgo_firewall_parcial(_entrada(estado, firewall=firewall, avisos=avisos)) is False


def test_ca_c3_8_5_un_lote_real_con_la_regla_fallida_marca_el_riesgo_solo_en_esa_mv():
    from .apoyo_fase_c_firewall import fallar_fw

    m = MundoC()
    fallar_fw(m.cl, "POST", "rules", error_http(500, "boom"), vmid=101)
    libro: Libro = m.ejecutar(m.planificar(m.definicion(3, ci(), firewall=fw())))
    riesgos = {e.elemento.vmid: riesgo_firewall_parcial(e) for e in libro.instantanea()}
    assert riesgos == {100: False, 101: True, 102: False}


def test_ca_c3_8_4_el_403_de_firewall_no_pausa_el_lote():
    """DT-C8: la política de pausa no se activa por los pasos de firewall."""
    from .apoyo_fase_c_firewall import fallar_fw
    from .apoyo_lote import ControlAutomatico

    m = MundoC()
    fallar_fw(
        m.cl,
        "PUT",
        "options",
        error_http(403, "Permission check failed (/vms/100, VM.Config.Network)"),
    )  # noqa: E501
    control = ControlAutomatico("suspender")
    libro = m.ejecutar(m.planificar(m.definicion(4, ci(), firewall=fw())), control)
    assert not control.suspendido
    assert set(m.estados(libro).values()) == {EstadoMV.PARCIAL}
    assert all(secuencia(m.cl, v).count("fw_opciones") == 1 for v in (100, 101, 102, 103))


# --- RF-C0.5: valores por fila (CSV) y homogéneos ---------------------------------------------


def _definicion_filas(m, filas, opciones):
    from proxlaunch.nucleo.lote.filas import definicion_por_filas

    definicion = definicion_por_filas(filas, plantilla_base=cfg_clon("base"))
    return dataclasses.replace(definicion, opciones=opciones)


def test_ca_c0_5_2_cada_fila_lleva_su_firewall_o_el_del_formulario_si_su_celda_esta_vacia():
    """CA-C0.5.2: celdas fijadas ganan sobre el formulario; las vacías lo heredan."""
    from proxlaunch.nucleo.firewall.modelos import FirewallParcial
    from proxlaunch.nucleo.lote.modelos import FilaLote
    from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales

    m = MundoC()
    m.cl.grupos["db"] = [{"type": "in", "action": "ACCEPT", "enable": 1}]
    base = dataclasses.replace(
        cfg_clon("base"), discos=MundoB().cfg().discos, redes=MundoB().cfg().redes
    )
    filas = [
        FilaLote(
            "a-01",
            base,
            opciones=OpcionesParciales(
                firewall=FirewallParcial(grupo="db", politica_entrada=Politica.PERMITIR)
            ),
        ),
        FilaLote("a-02", base),
    ]
    plan = m.planificar(_definicion_filas(m, filas, OpcionesLote(firewall=fw())))
    assert not plan.bloqueado, plan.problemas
    libro = m.ejecutar(plan)
    assert set(m.estados(libro).values()) == {EstadoMV.OK}
    por_nombre = {e.elemento.nombre: e.elemento.vmid for e in libro.instantanea()}
    v1, v2 = por_nombre["a-01"], por_nombre["a-02"]
    assert m.cl.fw_opciones[v1]["policy_in"] == "ACCEPT"
    assert [r["action"] for r in m.cl.fw_reglas[v1]] == ["db"]
    assert m.cl.fw_opciones[v2]["policy_in"] == "DROP"
    assert [r["action"] for r in m.cl.fw_reglas[v2]] == [GRUPO]


def test_ca_c0_5_2_una_fila_con_el_firewall_apagado_sin_grupo_en_el_formulario_no_pide_nada():
    from proxlaunch.nucleo.firewall.modelos import FirewallParcial
    from proxlaunch.nucleo.lote.modelos import FilaLote
    from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales

    m = MundoC()
    base = dataclasses.replace(
        cfg_clon("base"), discos=MundoB().cfg().discos, redes=MundoB().cfg().redes
    )
    filas = [
        FilaLote("a-01", base, opciones=OpcionesParciales(firewall=FirewallParcial(activo=False))),
        FilaLote(
            "a-02",
            base,
            opciones=OpcionesParciales(firewall=FirewallParcial(activo=True, grupo=GRUPO)),
        ),
    ]
    plan = m.planificar(_definicion_filas(m, filas, OpcionesLote(firewall=FirewallMV())))
    assert not plan.bloqueado, plan.problemas
    libro = m.ejecutar(plan)
    ids = {e.elemento.nombre: e.elemento.vmid for e in libro.instantanea()}
    assert "firewall" not in m.cl.vms[ids["a-01"]]["config"]["net0"]
    assert not any(
        "firewall" in c.ruta and f"/{ids['a-01']}/" in c.ruta and c.metodo != "GET"
        for c in m.cl.llamadas
    )
    assert [r["action"] for r in m.cl.fw_reglas[ids["a-02"]]] == [GRUPO]


def test_ca_c6_3_9_una_fila_con_grupo_y_el_formulario_sin_firewall_da_v_c52_y_bloquea():
    """CA-C6.3.9 (parte de núcleo): el grupo de una fila no se ignora en silencio."""
    from proxlaunch.nucleo.firewall.modelos import FirewallParcial
    from proxlaunch.nucleo.lote.modelos import FilaLote
    from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales

    m = MundoC()
    base = dataclasses.replace(
        cfg_clon("base"), discos=MundoB().cfg().discos, redes=MundoB().cfg().redes
    )
    filas = [
        FilaLote("a-01", base, opciones=OpcionesParciales(firewall=FirewallParcial(grupo=GRUPO)))
    ]
    plan = m.planificar(_definicion_filas(m, filas, OpcionesLote()))
    assert plan.bloqueado and "V-C52" in [p.regla for p in plan.problemas]
    assert m.cl.solo_lecturas


def test_ca_c0_5_1_un_lote_homogeneo_de_clones_lleva_los_mismos_valores_en_todas_las_mvs():
    m = MundoC()
    libro = m.ejecutar(
        m.planificar(m.definicion(5, ci(), firewall=fw(politica_salida=Politica.BLOQUEAR)))
    )
    for v in range(100, 105):
        assert m.cl.fw_opciones[v] == {
            "enable": "1",
            "policy_in": "DROP",
            "policy_out": "DROP",
            "dhcp": "1",
        }
        assert [r["action"] for r in m.cl.fw_reglas[v]] == [GRUPO]
        assert m.cl.vms[v]["config"]["net0"].endswith(",firewall=1")
    assert set(m.estados(libro).values()) == {EstadoMV.OK}


def test_ca_c3_1_4_el_firewall_de_las_opciones_del_lote_llega_a_cada_mv_del_plan():
    """El firewall puede venir de ``OpcionesLote`` (formulario de lote), no solo de la plantilla."""
    from proxlaunch.nucleo.opciones.modelos import OpcionesLote

    from .apoyo_fase_a import def_lote

    m = MundoC()
    base = dataclasses.replace(
        cfg_clon("base"), discos=MundoB().cfg().discos, redes=MundoB().cfg().redes
    )
    plan = m.planificar(def_lote(2, plantilla_vm=base, opciones=OpcionesLote(firewall=fw())))
    assert not plan.bloqueado, plan.problemas
    assert all(e.cfg.firewall == fw() for e in plan.elementos)


# --- Sensibilidad a mayúsculas y plantilla con tarjeta ilegible (§9) --------------------------


def test_ca_c3_2_2_los_nombres_de_grupo_distinguen_mayusculas_como_proxmox():
    m = MundoC()
    m.cl.grupos = {"Web": []}
    plan = m.planificar(m.definicion(1, ci(), firewall=fw("web")))
    assert plan.bloqueado and [p.regla for p in plan.problemas] == ["V-C30"]


def _plantilla_con_net1_ilegible():
    return {
        9000: (
            "base",
            config_plantilla(redes=2, net1="virtio=AA:BB:CC:DD:EE:01,bridge=vmbr0,tag=abc"),
        )
    }


def test_ca_c3_7_2_una_tarjeta_ilegible_no_se_toca_y_se_avisa_antes_y_despues_de_crear():
    """§9 (pregunta 1) y V-C35/V-C20: el plan y la simulación avisan ANTES de crear; la MV queda
    ``CON_AVISOS`` con firewall=1 solo en las tarjetas legibles."""
    from .apoyo_fase_a import def_lote

    m = MundoC(plantillas=_plantilla_con_net1_ilegible())
    plan = m.planificar(m.definicion(2, ci(), firewall=fw()))
    assert not plan.bloqueado
    previo = [p for p in plan.problemas if p.regla == "V-C35"]
    assert previo and previo[0].params["motivo"] == "tarjeta_ilegible"
    assert previo[0].params["tarjeta"] == "net1"
    base = dataclasses.replace(
        cfg_clon("base"), firewall=fw(), discos=MundoB().cfg().discos, redes=MundoB().cfg().redes
    )
    sim = simular(m.sesion, def_lote(2, plantilla_vm=base), m.inv, reloj=m.reloj)
    assert avisos_de_simulacion(sim, m.inv, 100) == ("red_tarjeta_ilegible:net1",)
    libro = m.ejecutar(plan)
    for e in libro.instantanea():
        assert e.estado == EstadoMV.CON_AVISOS
        assert "red_tarjeta_ilegible:net1" in e.avisos
    config = m.cl.vms[100]["config"]
    assert config["net0"].endswith(",firewall=1")
    assert config["net1"] == "virtio=AA:BB:CC:DD:EE:01,bridge=vmbr0,tag=abc"  # intacta
    assert len(m.cl.fw_reglas[100]) == 1  # el firewall de la MV sí se aplicó


# --- Reintento fuera del clon y cascada -------------------------------------------------------


def test_ca_c3_8_2_un_fallo_de_cloudinit_deja_el_firewall_pendiente_y_el_reintento_lo_aplica():
    """DT-C7: cascada. Tras el reintento: cloud-init → contraseña → opciones → regla → start."""
    from .apoyo_fase_b_p1 import fallar_put

    m = MundoC()
    fallar_put(m.cl, "ciuser", error_http(500, "boom"), veces=1)
    libro = m.ejecutar(
        m.planificar(m.definicion(1, ci_completa(Secreto(CENTINELA)), firewall=fw(), encender=True))
    )
    e = libro.entrada(100)
    assert e.estado == EstadoMV.PARCIAL
    assert ajustes_pendientes_de(e) == {
        "cloudinit",
        "contrasena",
        "firewall_opciones",
        "firewall_regla",
    }
    assert "fw_opciones" not in secuencia(m.cl) and "start" not in secuencia(m.cl)
    m.cl.llamadas.clear()
    from proxlaunch.nucleo.lote.ajustes import reintentar_ajustes
    from proxlaunch.nucleo.lote.motor import ControlLote

    reintentar_ajustes(libro, [100], m.sesion, m.reloj, m.inv, m.banco.observador, ControlLote())
    esc = [x for x in secuencia(m.cl) if not x.startswith(("leer", "fw_leer"))]
    assert esc == ["ci", "pw", "fw_opciones", "fw_regla", "start"]
    assert "red" not in esc
    assert libro.entrada(100).estado == EstadoMV.OK


def _mundo_origenes() -> MundoC:
    m = MundoC()
    m.cl.contenido[("pve1", "local")] = [VOLID_ISO, VOLID_IMAGEN]
    return m


def ajustes_pendientes_de(entrada):
    from proxlaunch.nucleo.lote.ajustes import ajustes_pendientes

    return ajustes_pendientes(entrada)


def test_ca_c3_8_3_el_reintento_directo_sin_lista_de_pendientes_no_duplica_la_regla():
    """``reintentar_ajustes(pendientes=None)``: compara con lo que hay y no repite la regla."""
    m = MundoC()
    m.leer_firewall()
    cfg = m.cfg(ci(), firewall=fw())
    assert m.crear(cfg).desenlace == Desenlace.OK
    m.cl.llamadas.clear()
    r = m.reintentar(cfg)
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS)
    assert "fw_regla" not in secuencia(m.cl) and "red" not in secuencia(m.cl)
    assert len(m.cl.fw_reglas[100]) == 1


def test_ca_c3_8_3_origen_iso_reintenta_la_regla_sin_duplicarla_ni_tocar_lo_demas():
    from proxlaunch.nucleo.lote.ajustes import reintentar_ajustes
    from proxlaunch.nucleo.lote.motor import ControlLote

    from .apoyo_fase_a import def_lote
    from .apoyo_fase_c_firewall import fallar_fw

    m = _mundo_origenes()
    fallar_fw(m.cl, "POST", "rules", error_http(500, "boom"), veces=1)
    plan = m.planificar(def_lote(2, plantilla_vm=cfg_iso(firewall=fw(), etiquetas=("proxlaunch",))))
    assert not plan.bloqueado, plan.problemas
    libro = m.ejecutar(plan)
    estados = m.estados(libro)
    assert sorted(estados.values(), key=str) == [EstadoMV.OK, EstadoMV.PARCIAL]
    parcial = next(v for v, s in estados.items() if s == EstadoMV.PARCIAL)
    m.cl.llamadas.clear()
    reintentar_ajustes(
        libro, [100, 101], m.sesion, m.reloj, m.inv, m.banco.observador, ControlLote()
    )
    assert libro.entrada(parcial).estado == EstadoMV.OK
    assert [secuencia(m.cl, v) for v in (100, 101) if v != parcial] == [[]]
    assert {v: len(r) for v, r in m.cl.fw_reglas.items()} == {100: 1, 101: 1}


def test_ca_c3_1_4_origen_iso_con_varias_tarjetas_lleva_firewall_1_en_todas():
    m = _mundo_origenes()
    from proxlaunch.nucleo.modelos.vm import InterfazRed

    m.crear(
        cfg_iso(
            firewall=fw(),
            etiquetas=("proxlaunch",),
            redes=[InterfazRed("vmbr0"), InterfazRed("vmbr0")],
        )
    )
    cuerpo = m.cl.cuerpos_post[100]
    assert cuerpo["net0"].endswith(",firewall=1") and cuerpo["net1"].endswith(",firewall=1")


def test_ca_c3_1_4_con_el_clon_en_otro_nodo_el_firewall_se_escribe_en_el_nodo_destino():
    m = MundoC(nodos=("pve1", "pve2"))
    cfg = dataclasses.replace(m.cfg(None, firewall=fw()), nodo="pve2")
    r = m.crear(cfg)
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), (r.desenlace, r.error)
    rutas = [c.ruta for c in m.cl.llamadas if c.metodo != "GET" and "firewall" in c.ruta]
    assert rutas == ["/nodes/pve2/qemu/100/firewall/options", "/nodes/pve2/qemu/100/firewall/rules"]
