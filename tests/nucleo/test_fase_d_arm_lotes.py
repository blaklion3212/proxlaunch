"""D2.7.2, D2.8 y D2.9 (0.9.0): lotes con arquitecturas mezcladas y clonar entre arquitecturas.

CA-D2.7.2, CA-D2.8.1–5, CA-D2.9.1–4, CL-D3, CL-D4, CL-D7, V-D04 a V-D07. Un lote usa nodos de
UNA sola arquitectura. En destino Automático o Nodos elegidos el reparto descarta los nodos de otra
arquitectura (aviso V-L11 ``arquitectura``, DT-D10); con la fila fijada a un nodo (CSV o filas) la
mezcla es el error V-D06 y recae en las filas de la minoría. La arquitectura de una plantilla es
la de su nodo o, si su config trae ``arch``, ese valor: otra distinta del destino es V-D07.

BUG-D-3 y BUG-D-4 (corregidos): ver las pruebas del final (V-D06 en reparto con nodos elegidos y
V-D07 ausente cuando el destino es «Un solo nodo»).
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.arquitectura.validacion import validar_mezcla
from proxlaunch.nucleo.lote.modelos import FilaLote, ModoDestino, Severidad

from .apoyo_fase_a import def_filas, def_lote, plan_de
from .apoyo_fase_d import ARM, DESC, V_84, X86, MundoD, banco_d, cfg_arm, inv_arq
from .apoyo_mvp4 import cfg_clon

NODOS = ("pve1", "pve2", "pve-arm", "pve-arm2", "pve-x")
ARQS = {"pve1": X86, "pve2": X86, "pve-arm": ARM, "pve-arm2": ARM, "pve-x": DESC}
COMPARTIDO = {"scsi0": "nfs1:base-9000-disk-0,size=8G"}  # plantilla alcanzable desde cualquier nodo


def _reglas(plan, *, solo: set[str] | None = None):
    return [(p.regla, p.indice) for p in plan.problemas if solo is None or p.regla in solo]


def _filas(*nodos: str) -> list[FilaLote]:
    return [FilaLote(f"a-0{i + 1}", cfg_arm(), nodo=n) for i, n in enumerate(nodos)]


@pytest.fixture
def banco():
    return banco_d(ARQS, nodos=NODOS)


# --- CA-D2.8: mezcla de arquitecturas en el lote --------------------------------------------------


def test_ca_d2_8_3_una_fila_en_un_nodo_arm_con_las_demas_en_x86_da_v_d06_asociado_a_esa_fila(banco):
    plan = plan_de(banco, def_filas(_filas("pve1", "pve1", "pve2", "pve-arm")))
    assert plan.bloqueado
    (v_d06,) = [p for p in plan.problemas if p.regla == "V-D06"]
    assert v_d06.indice == 3 and v_d06.severidad == Severidad.ERROR
    assert v_d06.params == {"nodos_x86": "pve1, pve2", "nodos_arm": "pve-arm", "nodo": "pve-arm"}


def test_ca_d2_8_3_con_mayoria_arm_la_fila_x86_es_la_del_error(banco):
    plan = plan_de(banco, def_filas(_filas("pve-arm", "pve1", "pve-arm2")))
    assert [(p.regla, p.indice) for p in plan.problemas if p.regla == "V-D06"] == [("V-D06", 1)]
    (p,) = [p for p in plan.problemas if p.regla == "V-D06"]
    assert p.params["nodos_arm"] == "pve-arm, pve-arm2" and p.params["nodos_x86"] == "pve1"


def test_ca_d2_8_1_con_empate_gana_la_arquitectura_de_la_primera_fila(banco):
    plan = plan_de(banco, def_filas(_filas("pve1", "pve-arm")))
    assert _reglas(plan, solo={"V-D06"}) == [("V-D06", 1)]
    plan = plan_de(banco, def_filas(_filas("pve-arm", "pve1")))
    assert _reglas(plan, solo={"V-D06"}) == [("V-D06", 1)]


def test_ca_d2_8_1_un_plan_con_v_d06_no_crea_nada(banco):
    plan = plan_de(banco, def_filas(_filas("pve1", "pve-arm")))
    assert plan.bloqueado
    cl = banco.cluster
    cl.reiniciar_llamadas()
    assert cl.total("POST") == 0 and cl.total("PUT") == 0  # planificar nunca escribe


def test_ca_d2_8_4_dos_nodos_aarch64_no_dan_error_y_el_perfil_adaptado_se_aplica_a_ambos(banco):
    plan = plan_de(banco, def_filas(_filas("pve-arm", "pve-arm2")))
    assert not plan.bloqueado and "V-D06" not in {p.regla for p in plan.problemas}
    adaptadas = [p for p in plan.problemas if p.regla == "V-D08"]
    assert sorted(p.indice for p in adaptadas) == [0, 1]
    assert all("firmware" in p.params["lista"] for p in adaptadas)
    assert {e.nodo for e in plan.elementos} == {"pve-arm", "pve-arm2"}
    assert all(e.cfg.firmware.value == "ovmf" and e.cfg.tipo_cpu == "host" for e in plan.elementos)


def test_ca_d2_8_5_un_nodo_desconocido_con_uno_x86_no_es_mezcla_y_v_d04_sigue_visible(banco):
    plan = plan_de(banco, def_filas(_filas("pve1", "pve-x")))
    assert not plan.bloqueado
    assert "V-D06" not in {p.regla for p in plan.problemas}
    (v_d04,) = [p for p in plan.problemas if p.regla == "V-D04"]
    assert v_d04.params["nodo"] == "pve-x" and v_d04.severidad == Severidad.AVISO


def test_cl_d4_un_nodo_desconocido_con_uno_aarch64_si_es_mezcla_hasta_forzarlo_a_mano(banco):
    plan = plan_de(banco, def_filas(_filas("pve-arm", "pve-x")))
    assert plan.bloqueado and _reglas(plan, solo={"V-D06"}) == [("V-D06", 1)]
    from proxlaunch.nucleo.arquitectura.deteccion import forzar
    from proxlaunch.nucleo.arquitectura.modelos import Arquitectura

    banco.inv = forzar(banco.inv, "pve-x", Arquitectura.AARCH64)
    plan = plan_de(banco, def_filas(_filas("pve-arm", "pve-x")))
    assert not plan.bloqueado and "V-D06" not in {p.regla for p in plan.problemas}


def test_ca_d2_8_2_el_reparto_automatico_descarta_los_nodos_de_otra_arquitectura_con_su_motivo(
    banco,
):
    """CA-D2.8.2 (parte núcleo): ``pve-arm`` queda fuera si el lote es x86_64 (modo automático)."""
    plan = plan_de(
        banco, def_lote(4, plantilla_vm=cfg_arm(), modo=ModoDestino.AUTOMATICO, nodos=())
    )
    assert {e.nodo for e in plan.elementos} <= {"pve1", "pve2", "pve-x"}  # desconocida = x86
    (motivo,) = [p for p in plan.problemas if p.regla == "V-L11" and p.params["nodo"] == "pve-arm"]
    assert motivo.params["motivo"] == "arquitectura"
    assert motivo.params["arquitectura"] == "aarch64" and motivo.params["esperada"] == "x86_64"


def test_ca_d2_7_2_un_lote_con_un_nodo_x86_y_otro_aarch64_no_los_mezcla_nunca(banco):
    # Automático: filtra por arquitectura sin error. Nodos elegidos: la mezcla es V-D06 (BUG-D-3).
    plan = plan_de(
        banco, def_lote(6, plantilla_vm=cfg_arm(), modo=ModoDestino.AUTOMATICO, nodos=())
    )
    arqs = {"aarch64" if e.nodo.startswith("pve-arm") else "x86" for e in plan.elementos}
    assert len(arqs) <= 1, plan.elementos
    plan = plan_de(
        banco,
        def_lote(
            6, plantilla_vm=cfg_arm(), modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve2", "pve-arm2")
        ),
    )
    assert plan.bloqueado and "V-D06" in {p.regla for p in plan.problemas}


def test_validar_mezcla_con_un_solo_nodo_o_una_sola_arquitectura_no_da_nada():
    inv = inv_arq(ARQS, nodos=NODOS)
    assert validar_mezcla({}, inv) == []
    assert validar_mezcla({0: "pve1"}, inv) == []
    assert validar_mezcla({0: "pve1", 1: "pve2", 2: "pve-x"}, inv) == []
    assert validar_mezcla({0: "pve-arm", 1: "pve-arm2"}, inv) == []


def test_validar_mezcla_nombra_los_nodos_de_cada_tipo_sin_repetirlos():
    inv = inv_arq(ARQS, nodos=NODOS)
    r = validar_mezcla({0: "pve1", 1: "pve1", 2: "pve2", 3: "pve-arm", 4: "pve-arm"}, inv)
    assert [p.indice for p in r] == [3, 4]
    assert all(
        p.params["nodos_x86"] == "pve1, pve2" and p.params["nodos_arm"] == "pve-arm" for p in r
    )


# --- CA-D2.9: clonar una plantilla de otra arquitectura -------------------------------------------


def _clon(extra=None, arqs=None, nodos=("pve1", "pve-arm")):
    return MundoD(nodos=nodos, arqs=arqs or {"pve1": X86, "pve-arm": ARM}, extra=extra)


def _plan_clon(m, modo, nodos, n=2):
    return plan_de(m.banco, def_lote(n, plantilla_vm=cfg_clon("base"), modo=modo, nodos=nodos))


def test_ca_d2_9_1_una_plantilla_x86_con_destino_exclusivo_arm_da_v_d07_y_no_crea_nada():
    m = _clon(COMPARTIDO)
    plan = _plan_clon(m, ModoDestino.NODOS_ELEGIDOS, ("pve-arm",))
    assert plan.bloqueado and plan.elementos == ()
    motivos = [p for p in plan.problemas if p.regla == "V-L11"]
    assert any(
        p.params.get("motivo") == "arquitectura_plantilla"
        and p.params["plantilla"] == "base"
        and p.params["arquitectura_plantilla"] == "x86_64"
        and p.params["arquitectura_nodo"] == "aarch64"
        and p.severidad == Severidad.ERROR
        for p in motivos
    ), motivos
    assert m.cl.total("POST") == 0


def test_ca_d2_9_1_con_nodos_elegidos_mixtos_el_clon_va_solo_al_nodo_de_la_misma_arquitectura():
    m = _clon(COMPARTIDO)
    plan = _plan_clon(m, ModoDestino.NODOS_ELEGIDOS, ("pve1", "pve-arm"))
    assert not plan.bloqueado and {e.nodo for e in plan.elementos} == {"pve1"}
    assert any(
        p.params.get("motivo") == "arquitectura_plantilla" and p.params["nodo"] == "pve-arm"
        for p in plan.problemas
        if p.regla == "V-L11"
    )


def test_ca_d2_9_2_una_plantilla_con_arch_aarch64_en_su_config_no_cabe_en_un_nodo_x86():
    m = _clon({**COMPARTIDO, "arch": "aarch64"}, nodos=("pve1", "pve2"),
              arqs={"pve1": X86, "pve2": X86})  # fmt: skip
    plan = _plan_clon(m, ModoDestino.NODOS_ELEGIDOS, ("pve1", "pve2"))
    assert plan.bloqueado and plan.elementos == ()
    assert {
        (p.params["nodo"], p.params["arquitectura_plantilla"], p.params["arquitectura_nodo"])
        for p in plan.problemas
        if p.regla == "V-L11" and p.params.get("motivo") == "arquitectura_plantilla"
    } == {("pve1", "aarch64", "x86_64"), ("pve2", "aarch64", "x86_64")}


def test_ca_d2_9_2_el_arch_de_la_config_manda_sobre_la_del_nodo_donde_vive():
    """Plantilla en un nodo x86 con ``arch: aarch64``: es aarch64 aunque el nodo sea x86."""
    m = _clon({**COMPARTIDO, "arch": "aarch64"})
    plan = _plan_clon(m, ModoDestino.NODOS_ELEGIDOS, ("pve-arm",))
    assert not plan.bloqueado and {e.nodo for e in plan.elementos} == {"pve-arm"}
    assert not any(p.regla == "V-L11" and "plantilla" in p.params for p in plan.problemas)


@pytest.mark.parametrize("arch", ["raro", "<script>", "", "riscv64"])
def test_ca_d2_9_2_un_arch_ilegible_se_ignora_y_vale_la_arquitectura_del_nodo(arch):
    m = _clon({**COMPARTIDO, "arch": arch}, nodos=("pve1", "pve2"), arqs={"pve1": X86, "pve2": X86})
    plan = _plan_clon(m, ModoDestino.NODOS_ELEGIDOS, ("pve1", "pve2"))
    assert not plan.bloqueado and len(plan.elementos) == 2


def test_ca_d2_9_3_una_plantilla_aarch64_clonada_a_otro_nodo_aarch64_no_se_adapta():
    """CL-D7: el clon hereda el hardware de la plantilla; sin V-D07 ni V-D08."""
    m = _clon(COMPARTIDO, nodos=("pve-arm", "pve-arm2"), arqs={"pve-arm": ARM, "pve-arm2": ARM})
    plan = _plan_clon(m, ModoDestino.NODOS_ELEGIDOS, ("pve-arm2",))
    reglas = {p.regla for p in plan.problemas}
    assert not plan.bloqueado and "V-D08" not in reglas and "V-L11" not in reglas
    assert {e.nodo for e in plan.elementos} == {"pve-arm2"}
    base = cfg_clon("base")
    assert plan.elementos[0].cfg.tipo_cpu == base.tipo_cpu  # sin cambios de CPU/firmware
    assert plan.elementos[0].cfg.firmware == base.firmware
    m.banco.cluster.reiniciar_llamadas()
    libro = m.ejecutar(plan)
    assert libro.instantanea() and m.cl.total("POST") == 2  # solo los dos «clone»
    assert all("clone" in c.ruta for c in m.cl.llamadas_a("POST", "/qemu"))


@pytest.mark.parametrize("quien", ["origen", "destino"])
def test_ca_d2_9_4_una_arquitectura_desconocida_en_origen_o_destino_no_bloquea_y_avisa_v_d04(quien):
    arqs = {"pve1": DESC if quien == "origen" else X86, "pve2": DESC if quien == "destino" else X86}
    m = _clon(COMPARTIDO, nodos=("pve1", "pve2"), arqs=arqs)
    plan = _plan_clon(m, ModoDestino.NODOS_ELEGIDOS, ("pve2",))
    assert not plan.bloqueado and {e.nodo for e in plan.elementos} == {"pve2"}
    avisos = {p.params["nodo"] for p in plan.problemas if p.regla == "V-D04"}
    assert avisos == ({"pve2"} if quien == "destino" else set())  # solo se avisa de los del lote


def test_ca_d2_9_4_desconocida_en_el_destino_y_plantilla_aarch64_si_es_incompatible():
    """Desconocida cuenta como x86 (P-D3): una plantilla ``arch: aarch64`` no cabe."""
    m = _clon({**COMPARTIDO, "arch": "aarch64"}, nodos=("pve1", "pve2"),
              arqs={"pve1": X86, "pve2": DESC})  # fmt: skip
    plan = _plan_clon(m, ModoDestino.NODOS_ELEGIDOS, ("pve2",))
    assert plan.bloqueado


def test_cl_d3_un_clon_en_un_clúster_de_tres_nodos_con_uno_arm_usa_solo_los_x86():
    m = MundoD(
        nodos=("pve1", "pve2", "pve-arm"),
        arqs={"pve1": X86, "pve2": X86, "pve-arm": ARM},
        extra=COMPARTIDO,
    )
    plan = _plan_clon(m, ModoDestino.AUTOMATICO, (), n=6)
    assert not plan.bloqueado and {e.nodo for e in plan.elementos} <= {"pve1", "pve2"}


# --- Mezcla desde la versión 8.4 (el comportamiento no depende de la versión) ---------------------


def test_la_mezcla_de_arquitecturas_es_error_tambien_con_8_4():
    banco = banco_d(ARQS, nodos=NODOS, version=V_84)
    plan = plan_de(banco, def_filas(_filas("pve1", "pve-arm")))
    assert plan.bloqueado and ("V-D06", 1) in _reglas(plan)


# --- Hallazgos corregidos (BUG-D-3 y BUG-D-4) ---


def test_ca_d2_8_1_literal_un_reparto_con_nodos_elegidos_mixtos_da_v_d06_y_no_crea_nada(banco):
    plan = plan_de(
        banco,
        def_lote(
            4, plantilla_vm=cfg_arm(), modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve1", "pve-arm")
        ),
    )
    assert "V-D06" in {p.regla for p in plan.problemas}
    assert plan.bloqueado


def test_ca_d2_9_1_literal_una_plantilla_x86_hacia_un_solo_nodo_arm_da_v_d07():
    m = _clon(COMPARTIDO)
    plan = _plan_clon(m, ModoDestino.UN_NODO, ("pve-arm",))
    assert plan.bloqueado
    assert any(p.params.get("motivo") == "arquitectura_plantilla" for p in plan.problemas)


def test_ca_d2_9_2_literal_una_plantilla_aarch64_hacia_un_solo_nodo_x86_da_v_d07():
    m = _clon({**COMPARTIDO, "arch": "aarch64"})
    plan = _plan_clon(m, ModoDestino.UN_NODO, ("pve1",))
    assert plan.bloqueado
    assert any(p.params.get("motivo") == "arquitectura_plantilla" for p in plan.problemas)
