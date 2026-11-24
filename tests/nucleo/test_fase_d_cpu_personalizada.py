"""D3.6 (0.9.0): modelos de CPU personalizados del clúster (RF-D3.6).

CA-D3.6.1–9, CL-D6, CL-D19. ``GET /nodes/{n}/capabilities/qemu/cpu`` por nodo (≤ 1, con caché);
solo valen los ``custom-<nombre>`` (``custom=1``, no ``abstract``); la petición lleva
``cpu=custom-<n>`` sin ``flags``; un modelo inexistente en un nodo del lote es V-D61 (error) y,
si la lista no se pudo leer, V-D62 (aviso). El combo de la interfaz está en ``tests/interfaz``.
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.lectura import leer_info_hardware
from proxlaunch.nucleo.hardware_cluster.validacion import validar_hardware_servidor
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.servicios.catalogo import ServicioCatalogo
from proxlaunch.nucleo.validacion import Severidad, tipo_cpu_valido

from .apoyo_api import TransporteFalso
from .apoyo_fase_a import cfg_vm, def_lote, plan_de
from .apoyo_fase_d import ARM, V_84, V_91, V_92, X86, banco_d, cfg_arm, info_hw, inv_arq
from .apoyo_lote import error_http, modelo_cpu_api

CPU = r"/capabilities/qemu/cpu$"


def _cliente(modelos) -> ClienteProxmox:
    t = TransporteFalso().en("GET", "/nodes/pve1/capabilities/qemu/cpu", modelos)
    return ClienteProxmox(
        t, AutenticadorToken(CredencialToken("ana@pve!lab", "s")), RelojSimulado()
    )


def _banco(cpus: dict[str, list], version=V_92, nodos=("pve1", "pve2"), arqs=None):
    banco = banco_d(
        dict.fromkeys(nodos, X86) if arqs is None else arqs, nodos=nodos, version=version
    )
    for nodo, modelos in cpus.items():
        banco.cluster.cpus_api[nodo] = modelos
    return banco


# --- CA-D3.6.1: filtro de la lista ----------------------------------------------------------------


def test_ca_d3_6_1_solo_custom_gamer_es_personalizado_y_x86_64_v2_abstracto_no_se_ofrece():
    cliente = _cliente(
        [
            modelo_cpu_api("custom-gamer", custom=True),
            modelo_cpu_api("x86-64-v2", abstract=True),
            modelo_cpu_api("kvm64"),
            modelo_cpu_api("host"),
        ]
    )
    modelos = cliente.modelos_cpu("pve1")
    assert [m.nombre for m in modelos] == ["custom-gamer", "kvm64", "host"]  # abstract fuera
    assert [m.nombre for m in modelos if m.personalizado] == ["custom-gamer"]


@pytest.mark.parametrize(
    "nombre",
    [
        "custom-x;y=z", "custom-con espacio", "custom-", "custom-" + "a" * 65, "custom-<b>",
        "custom-ñ", "custom-a,flags=+aes", "custom-a\nb",
    ],
)  # fmt: skip
def test_ca_d3_6_4_un_nombre_invalido_no_se_ofrece_como_personalizado_ni_llega_a_la_peticion(
    nombre,
):
    modelos = _cliente(
        [modelo_cpu_api(nombre, custom=True), modelo_cpu_api("custom-ok", custom=True)]
    )
    todos = modelos.modelos_cpu("pve1")
    assert not [m for m in todos if m.personalizado and m.nombre == nombre]
    assert [m.nombre for m in todos if m.personalizado] == ["custom-ok"]


def test_un_modelo_custom_0_o_un_nombre_que_no_empieza_por_custom_no_es_personalizado():
    cliente = _cliente([modelo_cpu_api("custom-a"), modelo_cpu_api("Haswell", custom=True)])
    assert [(m.nombre, m.personalizado) for m in cliente.modelos_cpu("pve1")] == [
        ("custom-a", False),
        ("Haswell", False),
    ]


@pytest.mark.parametrize("data", [None, {}, "x", 5, [None, 5, "a", {"sin": "nombre"}, {"name": 5}]])
def test_una_respuesta_con_forma_inesperada_da_lista_vacia_sin_excepcion(data):
    assert _cliente(data).modelos_cpu("pve1") == []


def test_los_textos_del_servidor_del_modelo_se_sanean():
    cliente = _cliente([{"name": "custom-a", "custom": 1, "vendor": "<b>AMD</b>\n" + "x" * 900}])
    (m,) = cliente.modelos_cpu("pve1")
    assert len(m.fabricante) <= 256 and not any(c in m.fabricante for c in "<>\n")


def test_el_cliente_acota_a_512_modelos():
    cliente = _cliente([modelo_cpu_api(f"m{i}") for i in range(900)])
    assert len(cliente.modelos_cpu("pve1")) <= 512


# --- CA-D3.6.9: arch según la versión -------------------------------------------------------------


def _arch_pedidos(banco) -> list[str | None]:
    return [(c.params or {}).get("arch") for c in banco.cluster.lecturas_d(CPU)]


@pytest.mark.parametrize(
    ("version", "arq", "esperado"),
    [
        (V_92, ARM, "aarch64"),
        (V_92, X86, "x86_64"),
        (V_84, ARM, None),
        (V_91, ARM, None),
        (V_84, X86, None),
    ],
    ids=["9.2_arm", "9.2_x86", "8.4_arm", "9.1_arm", "8.4_x86"],
)
def test_ca_d3_6_9_la_lectura_lleva_arch_solo_con_9_2(version, arq, esperado):
    banco = _banco({"pve1": []}, version=version, nodos=("pve1",), arqs={"pve1": arq})
    banco.cluster.cpus_por_arch[("pve1", "aarch64")] = [modelo_cpu_api("cortex-a53")]
    ServicioCatalogo(banco.sesion, banco.reloj).leer_hardware_seccion(
        banco.inv, ("pve1",), cpus=True
    )
    assert _arch_pedidos(banco) == [esperado]


def test_ca_d3_6_9_un_nodo_aarch64_en_9_2_lista_los_modelos_de_arm():
    banco = _banco({"pve1": []}, nodos=("pve1",), arqs={"pve1": ARM})
    banco.cluster.cpus_por_arch[("pve1", "aarch64")] = [
        modelo_cpu_api("host"), modelo_cpu_api("max"), modelo_cpu_api("cortex-a53"),
        modelo_cpu_api("custom-arm", custom=True),
    ]  # fmt: skip
    hw = (
        ServicioCatalogo(banco.sesion, banco.reloj)
        .leer_hardware_seccion(banco.inv, ("pve1",), cpus=True)
        .hardware
    )
    assert [m.nombre for m in hw.cpus["pve1"]] == ["host", "max", "cortex-a53", "custom-arm"]


def test_un_nodo_de_arquitectura_desconocida_no_manda_arch_ni_en_9_2():
    banco = _banco({"pve1": []}, nodos=("pve1",), arqs={})
    ServicioCatalogo(banco.sesion, banco.reloj).leer_hardware_seccion(
        banco.inv, ("pve1",), cpus=True
    )
    assert _arch_pedidos(banco) == [None]


def test_el_cliente_rechaza_un_arch_con_formato_de_inyeccion():
    cliente = _cliente([])
    for malo in ("x86_64&foo=1", "AARCH64", "a b", "../x", "", "x" * 17):
        with pytest.raises(ValueError):
            cliente.modelos_cpu("pve1", arch=malo)


# --- CA-D3.6.7: lecturas --------------------------------------------------------------------------


def test_ca_d3_6_7_el_combo_lee_una_vez_por_nodo_del_lote_y_ninguna_sin_nodos_elegidos():
    banco = _banco({"pve1": [modelo_cpu_api("custom-a", custom=True)], "pve2": []})
    srv = ServicioCatalogo(banco.sesion, banco.reloj)
    srv.leer_hardware_seccion(banco.inv, (), cpus=True)  # sin nodos elegidos
    assert banco.cluster.lecturas_d(CPU) == []
    cat = srv.leer_hardware_seccion(banco.inv, ("pve1", "pve2"), cpus=True)
    assert len(banco.cluster.lecturas_d(CPU)) == 2
    banco.inv.catalogo = cat
    srv.leer_hardware_seccion(banco.inv, ("pve1", "pve2"), cpus=True)  # caché
    assert len(banco.cluster.lecturas_d(CPU)) == 2


def test_ca_d3_6_7_sin_cpu_personalizada_en_el_lote_el_plan_no_lee_capacidades():
    banco = _banco({}, nodos=("pve1",))
    plan = plan_de(banco, def_lote(3, plantilla_vm=cfg_arm()))
    assert not plan.bloqueado and banco.cluster.lecturas_d(CPU) == []


def test_ca_d3_6_7_con_custom_en_el_lote_el_plan_lee_una_vez_por_nodo_del_lote():
    banco = _banco(
        {"pve1": [modelo_cpu_api("custom-a", custom=True)],
         "pve2": [modelo_cpu_api("custom-a", custom=True)]},
    )  # fmt: skip
    plan = plan_de(banco, def_lote(10, plantilla_vm=cfg_arm(tipo_cpu="custom-a")))
    assert not plan.bloqueado, [(p.regla, p.params) for p in plan.problemas]
    assert len(banco.cluster.lecturas_d(CPU)) <= 2


# --- CA-D3.6.3: la petición -----------------------------------------------------------------------


@pytest.mark.parametrize("arq", [X86, ARM], ids=["x86", "arm"])
def test_ca_d3_6_3_la_peticion_lleva_cpu_custom_sin_flags(arq):
    inv = inv_arq({"pve1": arq}, nodos=("pve1",))
    p = construir_parametros(cfg_arm(tipo_cpu="custom-b", firmware=_ovmf()), inv)
    assert p["cpu"] == "custom-b" and "flags" not in p["cpu"] and "," not in p["cpu"]


def _ovmf():
    from proxlaunch.nucleo.modelos.vm import Firmware

    return Firmware.OVMF


def test_ca_d3_6_4_tipo_cpu_valido_acepta_los_custom_bien_formados_y_rechaza_el_resto():
    for ok in ("custom-gamer", "custom-a.b_c-1", "host", "x86-64-v2-AES", "max"):
        assert tipo_cpu_valido(ok)
    for malo in ("custom-x;y=z", "custom-con espacio", "custom-ñ", "custom-a,flags=+aes", ""):
        assert not tipo_cpu_valido(malo), malo


def test_ca_d3_6_4_un_nombre_con_inyeccion_no_pasa_la_validacion_de_la_maquina():
    from proxlaunch.nucleo.validacion import validar_vm

    banco = _banco({}, nodos=("pve1",))
    for malo in ("custom-x;y=z", "custom-con espacio", "custom-a,flags=+aes"):
        problemas = validar_vm(cfg_arm(tipo_cpu=malo), banco.inv, banco.sesion.capacidades)
        assert [p for p in problemas if p.campo == "tipo_cpu" and p.severidad == Severidad.ERROR], (
            malo
        )


# --- CA-D3.6.2 y CA-D3.6.5: V-D61 y V-D62 ---------------------------------------------------------


def _cfgs(**por_nodo):
    return {n: [cfg_vm(tipo_cpu=cpu)] for n, cpu in por_nodo.items()}


def test_ca_d3_6_5_un_modelo_que_falta_en_un_nodo_del_lote_da_v_d61_nombrando_nodo_y_modelo():
    info = info_hw(cpus={"pve1": ["custom-a", "kvm64"], "pve2": ["kvm64"]})
    r = validar_hardware_servidor(_cfgs(pve1="custom-a", pve2="custom-a"), info, None)
    (p,) = [x for x in r if x.codigo == "V-D61"]
    assert p.severidad == Severidad.ERROR
    assert p.params == {"cpu": "custom-a", "nodos": "pve2"}


def test_ca_d3_6_5_si_la_lectura_falla_es_v_d62_aviso_y_se_permite_crear():
    info = info_hw(cpus={"pve1": ["custom-a"]})
    r = validar_hardware_servidor(_cfgs(pve1="custom-a", pve2="custom-a"), info, None)
    (p,) = [x for x in r if x.codigo == "V-D62"]
    assert p.severidad == Severidad.AVISO and p.params["nodos"] == "pve2"
    assert "V-D61" not in [x.codigo for x in r]
    assert [x for x in r if x.severidad == Severidad.ERROR] == []


def test_v_d62_sin_ninguna_lectura_avisa_de_todos_los_nodos():
    r = validar_hardware_servidor(_cfgs(pve1="custom-a", pve2="custom-a"), None, None)
    (p,) = [x for x in r if x.codigo == "V-D62"]
    assert p.params["nodos"] == "pve1, pve2"


def test_un_modelo_listado_pero_no_personalizado_no_vale_como_custom():
    from proxlaunch.nucleo.hardware_cluster.modelos import InfoHardwareCluster, ModeloCpu

    info = InfoHardwareCluster(cpus={"pve1": (ModeloCpu("custom-a", False),)})
    r = validar_hardware_servidor(_cfgs(pve1="custom-a"), info, None)
    assert "V-D61" in [x.codigo for x in r]


@pytest.mark.parametrize("cpu", ["host", "max", "x86-64-v2-AES", "kvm64"])
def test_los_tipos_que_no_son_custom_no_se_validan_contra_la_lista(cpu):
    assert validar_hardware_servidor(_cfgs(pve1=cpu), info_hw(), None) == []


def test_ca_d3_6_5_el_plan_con_un_modelo_ausente_en_un_nodo_bloquea_y_con_403_solo_avisa():
    banco = _banco(
        {"pve1": [modelo_cpu_api("custom-a", custom=True)], "pve2": [modelo_cpu_api("kvm64")]}
    )
    plan = plan_de(banco, def_lote(4, plantilla_vm=cfg_arm(tipo_cpu="custom-a")))
    assert plan.bloqueado
    (p,) = [x for x in plan.problemas if x.regla == "V-D61"]
    assert p.params["cpu"] == "custom-a" and "pve2" in p.params["nodos"]
    # ca. 3.6.8: un 403 en la lectura es V-D62 (aviso) y no bloquea
    banco2 = _banco(
        {"pve1": error_http(403, "Permission check failed"), "pve2": error_http(403, "x")}
    )
    plan2 = plan_de(banco2, def_lote(4, plantilla_vm=cfg_arm(tipo_cpu="custom-a")))
    assert not plan2.bloqueado
    assert {x.regla for x in plan2.problemas} >= {"V-D62"} and "V-D61" not in {
        x.regla for x in plan2.problemas
    }


def test_ca_d3_6_6_en_9_2_con_un_solo_modelo_visible_solo_ese_se_ofrece_sin_error():
    banco = _banco({"pve1": [modelo_cpu_api("custom-uno", custom=True)]}, nodos=("pve1",))
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_arm(tipo_cpu="custom-uno")))
    assert not plan.bloqueado
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_arm(tipo_cpu="custom-otro")))
    assert plan.bloqueado and "V-D61" in {p.regla for p in plan.problemas}


# --- CL-D6: perfil con custom-x abierto en ARM ----------------------------------------------------


def test_cl_d6_un_custom_x_inexistente_en_el_nodo_arm_se_sustituye_por_host_con_aviso_v_d08():
    banco = _banco({"pve1": [modelo_cpu_api("host"), modelo_cpu_api("max")]}, nodos=("pve1",),
                   arqs={"pve1": ARM})  # fmt: skip
    plan = plan_de(banco, def_lote(1, plantilla_vm=cfg_arm(tipo_cpu="custom-x")))
    assert not plan.bloqueado
    assert plan.elementos[0].cfg.tipo_cpu == "host"
    (p,) = [x for x in plan.problemas if x.regla == "V-D08"]
    assert "tipo_cpu:custom-x>host" in p.params["cambios"]


def test_cl_d6_un_custom_x_que_si_existe_en_arm_se_conserva():
    banco = _banco({"pve1": [modelo_cpu_api("custom-x", custom=True)]}, nodos=("pve1",),
                   arqs={"pve1": ARM})  # fmt: skip
    plan = plan_de(banco, def_lote(1, plantilla_vm=cfg_arm(tipo_cpu="custom-x")))
    assert plan.elementos[0].cfg.tipo_cpu == "custom-x"
    assert not [
        p for p in plan.problemas if p.regla == "V-D08" and "tipo_cpu" in p.params["cambios"]
    ]


def test_la_lectura_de_cpu_con_error_de_sesion_se_propaga_y_no_se_disfraza_de_v_d62():
    banco = _banco(
        {"pve1": ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "401")}, nodos=("pve1",)
    )
    with pytest.raises(ErrorProxLaunch) as e:
        leer_info_hardware(
            banco.sesion.cliente, None, banco.sesion.capacidades,
            NecesidadesCatalogo(cpus_personalizadas=frozenset({"custom-a"})), ("pve1",), None, {},
        )  # fmt: skip
    assert e.value.codigo == CodigoError.SESION_EXPIRADA


def test_tipo_cpu_valido_rechaza_custom_vacio_y_nombres_de_mas_de_64_caracteres():
    assert not tipo_cpu_valido("custom-")
    assert tipo_cpu_valido("custom-" + "a" * 64)
    assert not tipo_cpu_valido("custom-" + "a" * 65)
