"""Red de la fase C (0.8.0), parte pura: VNets de SDN (C2) y reescritura de la red al clonar (C4).

Derivadas de docs/requisitos/fase-c.md: RF-C2.1 a RF-C2.4, RF-C4.2 a RF-C4.6, V-C10 a V-C21, V-C50,
V-C51, CL-C12, CL-C13, CL-C15, CL-C21 y de las interfaces públicas de ``nucleo/red``,
``nucleo/constructor_peticion.py`` y ``nucleo/validacion.py``. Sin E/S: solo datos en memoria.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import RedVirtual
from proxlaunch.nucleo.modelos.vm import InterfazRed, ModeloRed
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.red.errores_sdn import anotar_error_red, es_error_digest
from proxlaunch.nucleo.red.modelos import (
    AccionTarjeta,
    CampoRed,
    ModoRedClon,
    RedClon,
    red_clon_a_dict,
    red_clon_desde_dict,
    usa_red_clon,
)
from proxlaunch.nucleo.red.redes_nodo import (
    filtrar_vnets,
    interseccion_redes,
    mtu_de_red,
    redes_de_nodo,
    vnet_de_nodo,
)
from proxlaunch.nucleo.red.reescritura import construir_peticion_red, requiere_paso_red
from proxlaunch.nucleo.red.tarjetas import (
    indice_libre,
    interpretar_tarjeta,
    ipconfigs_de_config,
    tarjetas_de_config,
    tarjetas_finales,
)
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_fase_c_red import (
    MundoC,
    anadir,
    bridge,
    cambiar,
    cfg_con_red,
    con_redes,
    quitar,
    red_clon,
    vnet,
)
from .apoyo_mvp4 import cfg_base

MAC = "BC:24:11:64:00:00"
MAC1 = "BC:24:11:64:00:01"
CONFIG_CLON = {
    "net0": f"virtio={MAC},bridge=vmbr0",
    "net1": f"virtio={MAC1},bridge=vmbr0,tag=20",
}
RE_CON_MAC = re.compile(r"^[A-Za-z0-9_]+=([0-9A-F]{2}:){5}[0-9A-F]{2}(,|$)")


def codigos(problemas, severidad: Severidad | None = None) -> list[str]:
    return [p.codigo for p in problemas if severidad is None or p.severidad == severidad]


def con_codigo(problemas, codigo: str):
    return [p for p in problemas if p.codigo == codigo]


@pytest.fixture(scope="module")
def mundo() -> MundoC:
    """Mundo de lectura: una plantilla con ``net0``/``net1`` en vmbr0 (no se crea nada)."""
    return MundoC(
        redes_sdn={
            "pve1": (
                vnet("prod", vlan_aware=True, alias="Producción"),
                vnet("lab"),
            )
        }
    )


def peticion(mundo: MundoC, red, config=None, *, digest="d1", **kw):
    """``construir_peticion_red`` sobre la config del clon dada (por defecto, ``CONFIG_CLON``)."""
    cfg = cfg_con_red(mundo, red, **kw)
    config = CONFIG_CLON if config is None else config
    return construir_peticion_red(
        cfg, tarjetas_de_config(config), ipconfigs_de_config(config), digest
    )


# --- RF-C4.2: lectura de las tarjetas ------------------------------------------------------------


def test_ca_c4_2_1_se_interpretan_todos_los_campos_de_una_tarjeta():
    t = interpretar_tarjeta(
        0, "virtio=BC:24:11:AA:BB:CC,bridge=vmbr0,tag=20,firewall=1,mtu=1500,rate=5,queues=4"
    )
    assert t.legible
    assert (t.modelo, t.mac, t.bridge, t.vlan) == ("virtio", "BC:24:11:AA:BB:CC", "vmbr0", 20)
    assert (t.firewall, t.mtu, t.limite_mb) == (True, 1500, 5.0)
    assert t.otras == (("queues", "4"),)


def test_ca_c4_2_1_queues_se_conserva_al_reescribir(mundo):
    config = {"net0": f"virtio={MAC},bridge=vmbr0,tag=20,firewall=1,mtu=1500,rate=5,queues=4"}
    r = peticion(mundo, red_clon(cambiar(0, bridge="lab")), config)
    assert r.parametros["net0"] == (
        f"virtio={MAC},bridge=lab,tag=20,mtu=1500,rate=5,firewall=1,queues=4"
    )


def test_ca_c4_2_2_link_down_se_conserva(mundo):
    config = {"net1": f"e1000={MAC1},bridge=vmbr1,link_down=1"}
    r = peticion(mundo, red_clon(cambiar(1, vlan=5)), config)
    assert r.parametros["net1"] == f"e1000={MAC1},bridge=vmbr1,tag=5,link_down=1"


def test_cl_c15_trunks_se_conserva_al_reescribir(mundo):
    config = {"net0": f"virtio={MAC},bridge=vmbr0,trunks=10;20;30"}
    r = peticion(mundo, red_clon(cambiar(0, bridge="lab")), config)
    assert r.parametros["net0"].endswith(",trunks=10;20;30")


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "   ",
        None,
        123,
        ["virtio=AA:BB:CC:DD:EE:FF"],
        "bridge=vmbr0",
        "virtio",
        "virtio=ZZ:BB:CC:DD:EE:FF,bridge=vmbr0",
        "virtio=AA:BB:CC:DD:EE,bridge=vmbr0",
        f"virtio={MAC},bridge",
        f"virtio={MAC},bridge=vmbr0,bridge=vmbr1",
        f"virtio={MAC},bridge=a b",
        f"virtio={MAC},bridge=<script>",
        f"virtio={MAC},bridge=vmbr0,tag=abc",
        f"virtio={MAC},bridge=vmbr0,tag=-1",
        f"virtio={MAC},bridge=vmbr0,firewall=2",
        f"virtio={MAC},bridge=vmbr0,mtu=1e3",
        f"virtio={MAC},bridge=vmbr0,rate=x",
        f"virtio={MAC},bridge=vmbr0,queues=",
        f"virtio={MAC},bridge=vmbr0,=4",
        f"vir tio={MAC},bridge=vmbr0",
    ],
)
def test_ca_c4_2_3_una_tarjeta_con_formato_inesperado_es_ilegible_y_nunca_lanza(valor):
    """CA-C4.2.3 / RNF-C6: lo que no se entiende queda ``legible=False``."""
    assert interpretar_tarjeta(3, valor).legible is False


def test_ca_c4_2_3_una_tarjeta_ilegible_no_se_reescribe_y_se_avisa(mundo):
    config = {"net0": f"virtio={MAC},bridge=vmbr0", "net1": "esto no se entiende"}
    r = peticion(mundo, red_clon(cambiar(0, bridge="lab"), cambiar(1, bridge="lab")), config)
    assert "net1" not in r.parametros
    assert "red_tarjeta_ilegible:net1" in r.avisos
    assert r.parametros["net0"].endswith("bridge=lab")


def test_ca_c4_2_3_con_las_tarjetas_ilegibles_y_sin_cambios_no_hay_peticion(mundo):
    assert peticion(mundo, red_clon(), {"net0": "???"}) is None


def test_ca_c4_2_tarjetas_de_config_ordena_y_solo_toma_net0_a_net31():
    config = {
        "net10": f"virtio={MAC},bridge=a",
        "net2": f"virtio={MAC},bridge=b",
        "net31": f"virtio={MAC},bridge=c",
        "net32": f"virtio={MAC},bridge=d",
        "net01": f"virtio={MAC},bridge=e",
        "net": "x",
        "netx": "x",
        "name": "web",
        5: "raro",
    }
    assert [t.indice for t in tarjetas_de_config(config)] == [2, 10, 31]


def test_ca_c4_4_ipconfigs_de_config_solo_toma_ipconfig0_a_ipconfig31():
    config = {"ipconfig0": "ip=dhcp", "ipconfig31": "ip=dhcp", "ipconfig32": "x", "ipconfig01": "x"}
    assert ipconfigs_de_config(config) == frozenset({0, 31})


# --- RF-C4.1 y RF-C4.3: reescritura conservando la MAC -------------------------------------------


def test_ca_c4_1_1_sin_red_personalizada_ni_firewall_no_hay_paso_de_red(mundo):
    cfg = mundo.cfg()
    assert not requiere_paso_red(cfg)
    assert peticion(mundo, None) is None
    # «Personalizar» sin ningún cambio tampoco escribe nada.
    assert peticion(mundo, red_clon()) is None


def test_ca_c4_1_4_con_un_origen_que_no_es_clon_no_hay_paso_de_red(mundo):
    cfg = dataclasses.replace(cfg_base(), red_clon=red_clon(cambiar(0, bridge="lab")))
    assert not requiere_paso_red(cfg)
    assert construir_peticion_red(cfg, tarjetas_de_config(CONFIG_CLON), frozenset(), "d") is None


def test_ca_c4_3_1_el_put_lleva_exactamente_la_mac_del_clon(mundo):
    r = peticion(mundo, red_clon(cambiar(0, bridge="vmbr1")))
    assert r.parametros["net0"] == f"virtio={MAC},bridge=vmbr1"
    assert "net1" not in r.parametros  # lo que no se cambia no se reenvía


@pytest.mark.parametrize(
    "cambios",
    [
        {"bridge": "lab"},
        {"vlan": 30},
        {"vlan": None},
        {"modelo": "e1000"},
        {"mtu": 1400},
        {"limite_mb": 12.5},
        {"bridge": "lab", "vlan": None, "modelo": "e1000", "limite_mb": None},
    ],
    ids=lambda c: "+".join(c),
)
def test_ca_c4_3_nunca_se_envia_un_netn_sin_mac_para_una_tarjeta_existente(mundo, cambios):
    """RF-C4.3: la MAC leída del clon se reenvía en cualquier cambio (modelo incluido)."""
    r = peticion(mundo, red_clon(cambiar(1, **cambios)))
    valor = r.parametros["net1"]
    assert RE_CON_MAC.match(valor), valor
    assert f"={MAC1}" in valor
    assert r.finales[1].mac_conservada is True


def test_ca_c4_3_nunca_sin_mac_tampoco_al_poner_firewall_sin_otros_cambios(mundo):
    from proxlaunch.nucleo.firewall.modelos import FirewallMV

    cfg = dataclasses.replace(mundo.cfg(), firewall=FirewallMV(activo=True))
    r = construir_peticion_red(cfg, tarjetas_de_config(CONFIG_CLON), frozenset(), "d1")
    assert r is not None
    for clave in ("net0", "net1"):
        assert RE_CON_MAC.match(r.parametros[clave])
        assert r.parametros[clave].endswith(",firewall=1")
    assert f"={MAC}," in r.parametros["net0"] + ","


def test_ca_c4_3_2_con_mac_nueva_la_tarjeta_sale_sin_mac_y_se_avisa(mundo):
    r = peticion(mundo, red_clon(cambiar(0, bridge="lab", mac_nueva=True)))
    assert r.parametros["net0"] == "virtio,bridge=lab"
    assert "red_mac_nueva:net0" in r.avisos
    assert r.finales[0].mac_conservada is False
    # Las demás tarjetas siguen conservando la suya.
    assert r.finales[1].mac_conservada is True


def test_ca_c4_3_2_mac_nueva_sin_otros_cambios_tambien_omite_la_mac(mundo):
    r = peticion(mundo, red_clon(cambiar(0, mac_nueva=True)))
    assert r.parametros["net0"] == "virtio,bridge=vmbr0"


def test_rd_c5_un_reintento_con_la_red_ya_aplicada_no_regenera_la_mac(mundo):
    """RF-C4.8 / CA-C4.8.1: con bridge ya puesto, ``mac_nueva`` no se repite (idempotente)."""
    red = red_clon(cambiar(0, bridge="lab", mac_nueva=True))
    config = {**CONFIG_CLON, "net0": "virtio=DE:AD:BE:EF:00:01,bridge=lab"}
    assert peticion(mundo, red, config) is None


def test_ca_c4_8_1_mac_nueva_sin_cambio_de_red_no_se_regenera_en_un_reintento(mundo):
    red = red_clon(cambiar(0, mac_nueva=True))
    config = {**CONFIG_CLON, "net0": "virtio=DE:AD:BE:EF:00:01,bridge=vmbr0"}
    cfg = cfg_con_red(mundo, red)
    # El libro recuerda la MAC original de cada tarjeta: si la actual es otra, ya se regeneró.
    r = construir_peticion_red(
        cfg,
        tarjetas_de_config(config),
        ipconfigs_de_config(config),
        "d1",
        {0: "AA:BB:CC:00:00:01"},
    )
    assert r is None


def test_ca_c4_3_4_modelo_e1000_con_mtu_sale_sin_mtu_y_se_avisa(mundo):
    r = peticion(mundo, red_clon(cambiar(0, modelo="e1000", mtu=1400)))
    assert r.parametros["net0"] == f"e1000={MAC},bridge=vmbr0"
    assert "red_mtu_ignorada:net0" in r.avisos


def test_ca_c4_3_cambiar_de_modelo_conserva_la_mac(mundo):
    r = peticion(mundo, red_clon(cambiar(0, modelo="e1000")))
    assert r.parametros["net0"] == f"e1000={MAC},bridge=vmbr0"


def test_ca_c4_3_5_una_sola_peticion_para_todas_las_tarjetas_modificadas(mundo):
    r = peticion(mundo, red_clon(cambiar(0, bridge="lab"), cambiar(1, vlan=40), quitar(5)))
    assert set(r.parametros) == {"net0", "net1", "digest"}
    assert r.parametros["net1"] == f"virtio={MAC1},bridge=vmbr0,tag=40"


def test_ca_c4_3_6_el_put_incluye_el_digest_de_la_config_leida(mundo):
    r = peticion(mundo, red_clon(cambiar(0, bridge="lab")), digest="abc123")
    assert r.parametros["digest"] == "abc123"


def test_ca_c4_3_6_sin_digest_en_la_config_no_se_envia_la_clave(mundo):
    r = peticion(mundo, red_clon(cambiar(0, bridge="lab")), digest=None)
    assert "digest" not in r.parametros


def test_cl_c21_un_campo_no_fijado_conserva_el_valor_de_la_tarjeta(mundo):
    """Solo se aplican los campos fijados: la VLAN de net1 sobrevive a un cambio de bridge."""
    r = peticion(mundo, red_clon(cambiar(1, bridge="lab")))
    assert r.parametros["net1"] == f"virtio={MAC1},bridge=lab,tag=20"


def test_ca_c4_3_un_campo_fijado_a_none_lo_quita(mundo):
    r = peticion(mundo, red_clon(cambiar(1, vlan=None)))
    assert r.parametros["net1"] == f"virtio={MAC1},bridge=vmbr0"


def test_dt_c9_aplicar_la_peticion_y_recalcular_no_da_nada_que_cambiar(mundo):
    """DT-C9: el cálculo es idempotente sobre la config ya aplicada."""
    red = red_clon(
        cambiar(0, bridge="lab", vlan=None), cambiar(1, modelo="e1000", mtu=1400), quitar(2)
    )
    config = {**CONFIG_CLON, "net2": "virtio=BC:24:11:64:00:02,bridge=vmbr0", "ipconfig2": "x"}
    r = peticion(mundo, red, config)
    aplicada = {k: v for k, v in config.items() if k not in ("net2", "ipconfig2")}
    aplicada.update({k: v for k, v in r.parametros.items() if k.startswith("net")})
    assert peticion(mundo, red, aplicada) is None


# --- RF-C4.4: añadir y quitar tarjetas -----------------------------------------------------------


def test_ca_c4_4_1_quitar_net1_con_ipconfig1_borra_las_dos_claves(mundo):
    config = {**CONFIG_CLON, "ipconfig1": "ip=dhcp"}
    r = peticion(mundo, red_clon(quitar(1)), config)
    assert r.parametros["delete"] == "net1,ipconfig1"
    assert "net1" not in r.parametros
    assert r.finales[-1].accion == AccionTarjeta.QUITAR


def test_ca_c4_4_2_quitar_net1_sin_ipconfig1_solo_borra_net1(mundo):
    r = peticion(mundo, red_clon(quitar(1)), {**CONFIG_CLON, "ipconfig0": "ip=dhcp"})
    assert r.parametros["delete"] == "net1"


def test_cl_c13_quitar_net2_con_net0_y_net2_borra_solo_net2(mundo):
    config = {"net0": f"virtio={MAC},bridge=vmbr0", "net2": f"virtio={MAC1},bridge=vmbr0"}
    r = peticion(mundo, red_clon(quitar(2)), config)
    assert r.parametros["delete"] == "net2"


def test_ca_c4_4_3_con_net0_y_net2_el_indice_libre_mas_bajo_es_net1():
    assert indice_libre({0, 2}) == 1
    assert indice_libre(set()) == 0
    assert indice_libre(set(range(32))) is None
    assert indice_libre(set(range(32)) - {31}) == 31


def test_ca_c4_4_una_tarjeta_nueva_sale_sin_mac_para_que_proxmox_la_genere(mundo):
    config = {"net0": f"virtio={MAC},bridge=vmbr0", "net2": f"virtio={MAC1},bridge=vmbr0"}
    r = peticion(mundo, red_clon(anadir(1, bridge="lab", vlan=7)), config)
    assert r.parametros["net1"] == "virtio,bridge=lab,tag=7"
    assert r.finales[1].accion == AccionTarjeta.ANADIR
    assert r.finales[1].mac_conservada is False


def test_ca_c4_4_anadir_sobre_un_indice_ocupado_por_otra_red_no_pisa_nada(mundo):
    """CL-C16 / RED_PLANTILLA_CAMBIADA: la plantilla cambió desde que se preparó el lote."""
    with pytest.raises(ErrorProxLaunch) as e:
        peticion(mundo, red_clon(anadir(1, bridge="lab")))
    assert e.value.codigo == CodigoError.RED_PLANTILLA_CAMBIADA
    assert e.value.params["tarjeta"] == "net1"


def test_dt_c9_anadir_cuando_ya_esta_anadida_con_la_misma_red_cuenta_como_hecha(mundo):
    r = peticion(mundo, red_clon(anadir(1, bridge="vmbr0", vlan=20)))
    assert r is None


def test_ca_c4_4_se_pueden_anadir_y_quitar_en_la_misma_peticion(mundo):
    config = {**CONFIG_CLON, "ipconfig0": "ip=dhcp"}
    r = peticion(mundo, red_clon(quitar(0), anadir(2, bridge="lab")), config)
    assert r.parametros["delete"] == "net0,ipconfig0"
    assert r.parametros["net2"] == "virtio,bridge=lab"


def test_ca_c4_4_tarjetas_finales_resta_las_quitadas_y_suma_las_anadidas():
    red = red_clon(quitar(1), anadir(3, bridge="x"), cambiar(0, vlan=2))
    assert tarjetas_finales([0, 1, 2], red) == (0, 2, 3)
    assert tarjetas_finales([0, 1], None) == (0, 1)
    # En «Como la plantilla» las acciones no cuentan.
    assert tarjetas_finales([0, 1], RedClon(ModoRedClon.PLANTILLA, (quitar(1),))) == (0, 1)


def test_ca_c4_1_usa_red_clon_solo_en_modo_personalizar():
    assert usa_red_clon(None) is False
    assert usa_red_clon(RedClon()) is False
    assert usa_red_clon(red_clon()) is True


# --- Serialización de la red del clon (lote guardado) --------------------------------------------


def test_red_clon_ida_y_vuelta_conserva_los_campos_fijados():
    red = red_clon(
        cambiar(0, bridge="lab", vlan=None, mac_nueva=True),
        quitar(1),
        anadir(2, bridge="prod", modelo="e1000", vlan=100, limite_mb=2.5),
    )
    assert red_clon_desde_dict(red_clon_a_dict(red)) == red


def test_red_clon_una_clave_ausente_no_es_lo_mismo_que_null():
    """Ausente = no fijado (se conserva); ``null`` = fijado a None (se quita), CL-C21."""
    d = {"modo": "personalizar", "tarjetas": [{"indice": 0, "accion": "cambiar", "vlan": None}]}
    t = red_clon_desde_dict(d).tarjetas[0]
    assert t.fijados == frozenset({CampoRed.VLAN})
    d2 = {"modo": "personalizar", "tarjetas": [{"indice": 0, "accion": "cambiar"}]}
    assert red_clon_desde_dict(d2).tarjetas[0].fijados == frozenset()


@pytest.mark.parametrize(
    ("d", "campo"),
    [
        ({"modo": "otro"}, "red_clon.modo"),
        ({"tarjetas": "x"}, "red_clon.tarjetas"),
        ({"tarjetas": [5]}, "red_clon.tarjetas[0]"),
        ({"tarjetas": [{"indice": 32}]}, "red_clon.tarjetas[0].indice"),
        ({"tarjetas": [{"indice": -1}]}, "red_clon.tarjetas[0].indice"),
        ({"tarjetas": [{"indice": True}]}, "red_clon.tarjetas[0].indice"),
        ({"tarjetas": [{"indice": 0, "accion": "borrar"}]}, "red_clon.tarjetas[0].accion"),
        ({"tarjetas": [{"indice": 0, "bridge": "a b"}]}, "red_clon.tarjetas[0].bridge"),
        ({"tarjetas": [{"indice": 0, "bridge": "<x>"}]}, "red_clon.tarjetas[0].bridge"),
        ({"tarjetas": [{"indice": 0, "modelo": "rtl8139"}]}, "red_clon.tarjetas[0].modelo"),
        ({"tarjetas": [{"indice": 0, "vlan": "20"}]}, "red_clon.tarjetas[0].vlan"),
        ({"tarjetas": [{"indice": 0, "vlan": True}]}, "red_clon.tarjetas[0].vlan"),
        ({"tarjetas": [{"indice": 0, "mac_nueva": "si"}]}, "red_clon.tarjetas[0].mac_nueva"),
    ],
)
def test_red_clon_desde_dict_rechaza_valores_malos_con_la_ruta_del_campo(d, campo):
    with pytest.raises(ErrorProxLaunch) as e:
        red_clon_desde_dict(d)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO
    assert e.value.params["campo"] == campo


# --- RF-C2.1: redes de un nodo, filtro de VNets e intersección -----------------------------------


def test_ca_c2_1_redes_de_nodo_incluye_bridges_y_vnets_y_no_las_interfaces_que_no_son_bridge(
    mundo,
):
    inv = con_redes(
        mundo.inv,
        bridges={"pve1": (bridge("vmbr0"), dataclasses.replace(bridge("eno1"), tipo="eth"))},
        vnets={"pve1": (vnet("prod"),)},
    )
    assert redes_de_nodo(inv, "pve1") == frozenset({"vmbr0", "prod"})
    assert vnet_de_nodo(inv, "pve1", "prod").nombre == "prod"
    assert vnet_de_nodo(inv, "pve1", "vmbr0") is None
    assert vnet_de_nodo(inv, "pve2", "prod") is None


def test_ca_c2_1_las_vnets_no_informan_mtu_y_los_bridges_si(mundo):
    inv = con_redes(
        mundo.inv, bridges={"pve1": (bridge("vmbr0", mtu=9000),)}, vnets={"pve1": (vnet("prod"),)}
    )
    assert mtu_de_red(inv, "pve1", "vmbr0") == 9000
    assert mtu_de_red(inv, "pve1", "prod") is None
    assert mtu_de_red(inv, "pve1", "no-existe") is None


def test_ca_c2_1_3_filtrar_vnets_descarta_duplicados_y_las_que_ya_son_interfaces_sin_type():
    entradas = (
        vnet("prod"),
        vnet("prod", alias="otra"),
        vnet("vmbr0", tipo_declarado=False),
        vnet("lab", tipo_declarado=False),
        vnet("vmbr1", tipo_declarado=True),
    )
    nombres = [v.nombre for v in filtrar_vnets(entradas, {"vmbr0", "vmbr1"})]
    # Una entrada sin type que ya es interfaz del nodo es un bridge; con type=vnet manda el type.
    assert nombres == ["prod", "lab", "vmbr1"]


def _inv_nodos(mundo, **por_nodo):
    """Inventario de varios nodos: ``nodo=(bridges, vnets)``."""
    nombres = tuple(por_nodo)
    base = MundoC(nodos=nombres).inv
    return con_redes(
        base,
        bridges={n: b for n, (b, _v) in por_nodo.items()},
        vnets={n: v for n, (_b, v) in por_nodo.items()},
        errores_sdn={},
        errores_red={},
    )


def test_ca_c2_3_1_con_vnets_a_b_y_b_c_solo_b_se_ofrece_y_hay_2_ocultas(mundo):
    inv = _inv_nodos(
        mundo,
        pve1=((bridge("vmbr0"),), (vnet("a"), vnet("b"))),
        pve2=((bridge("vmbr0"),), (vnet("b"), vnet("c"))),
    )
    r = interseccion_redes(inv, ["pve1", "pve2"])
    assert [v.nombre for v in r.vnets] == ["b"]
    assert [b.nombre for b in r.bridges] == ["vmbr0"]
    assert r.ocultas == 2
    assert r.sin_leer == ()


def test_ca_c2_3_los_bridges_tambien_se_intersectan(mundo):
    inv = _inv_nodos(
        mundo,
        pve1=((bridge("vmbr0"), bridge("vmbr1")), ()),
        pve2=((bridge("vmbr0"),), ()),
    )
    r = interseccion_redes(inv, ["pve1", "pve2"])
    assert [b.nombre for b in r.bridges] == ["vmbr0"]
    assert r.ocultas == 1


def test_ca_c2_3_3_con_un_solo_nodo_no_hay_ocultas(mundo):
    inv = _inv_nodos(mundo, pve1=((bridge("vmbr0"), bridge("vmbr1")), (vnet("a"), vnet("b"))))
    r = interseccion_redes(inv, ["pve1"])
    assert r.ocultas == 0
    assert {v.nombre for v in r.vnets} == {"a", "b"}
    assert {b.nombre for b in r.bridges} == {"vmbr0", "vmbr1"}


def test_ca_c2_3_4_un_nodo_sin_lectura_de_sdn_se_avisa_y_la_interseccion_usa_los_demas(mundo):
    inv = _inv_nodos(
        mundo,
        pve1=((bridge("vmbr0"),), (vnet("a"), vnet("b"))),
        pve2=((bridge("vmbr0"),), (vnet("b"),)),
        pve3=((bridge("vmbr0"),), ()),
    )
    inv = dataclasses.replace(
        inv,
        redes_sdn={n: v for n, v in inv.redes_sdn.items() if n != "pve3"},
        errores_sdn={"pve3": ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {})},
    )
    r = interseccion_redes(inv, ["pve1", "pve2", "pve3"])
    assert r.sin_leer == ("pve3",)
    assert [v.nombre for v in r.vnets] == ["b"]  # solo entre los nodos legibles
    assert [b.nombre for b in r.bridges] == ["vmbr0"]  # los bridges sí se leyeron en pve3


def test_ca_c2_3_4_un_nodo_sin_lectura_de_red_no_cuenta_para_los_bridges(mundo):
    inv = _inv_nodos(
        mundo,
        pve1=((bridge("vmbr0"), bridge("vmbr1")), ()),
        pve2=((), ()),
    )
    inv = dataclasses.replace(
        inv, errores_por_nodo={"pve2": ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {})}
    )
    r = interseccion_redes(inv, ["pve1", "pve2"])
    assert r.sin_leer == ("pve2",)
    assert {b.nombre for b in r.bridges} == {"vmbr0", "vmbr1"}


def test_ca_c2_2_la_interseccion_solo_es_vlanaware_si_lo_es_en_todos_los_nodos(mundo):
    inv = _inv_nodos(
        mundo,
        pve1=((bridge("vmbr0", vlan_aware=True),), (vnet("a", vlan_aware=True),)),
        pve2=((bridge("vmbr0", vlan_aware=True),), (vnet("a", vlan_aware=False),)),
    )
    r = interseccion_redes(inv, ["pve1", "pve2"])
    assert r.vnets[0].vlan_aware is False
    assert r.bridges[0].vlan_aware is True


# --- RF-C2.1/RF-C2.2: la VNet viaja como nombre de bridge ----------------------------------------


def test_ca_c2_1_2_la_vnet_elegida_viaja_como_bridge_sin_parametros_nuevos():
    from proxlaunch.nucleo.constructor_peticion import valor_red

    assert valor_red(InterfazRed("prod")) == "virtio,bridge=prod"


def test_ca_c2_2_2_con_vnet_vlanaware_y_vlan_100_la_peticion_lleva_bridge_y_tag():
    from proxlaunch.nucleo.constructor_peticion import valor_red

    assert valor_red(InterfazRed("prod", vlan=100)) == "virtio,bridge=prod,tag=100"


def test_ca_c2_2_5_un_bridge_con_vlan_sigue_como_en_0_7_0_y_sin_opciones_c():
    from proxlaunch.nucleo.constructor_peticion import valor_red

    r = InterfazRed("vmbr0", modelo=ModeloRed.E1000, vlan=20, mtu=1500, limite_mb=5.0)
    assert valor_red(r) == "e1000,bridge=vmbr0,tag=20,rate=5"  # el MTU no va con e1000
    r = InterfazRed("vmbr0", vlan=20, mtu=1500, limite_mb=12.5)
    assert valor_red(r) == "virtio,bridge=vmbr0,tag=20,mtu=1500,rate=12.5"
    assert valor_red(r, firewall=False) == valor_red(r)


# --- Validaciones V-C10..V-C21, V-C50, V-C51 ------------------------------------------------------


@pytest.fixture(scope="module")
def mundo_sdn() -> MundoC:
    """pve1 con ``vmbr0`` (MTU 1500), la VNet ``plana`` (sin vlanaware) y ``vlans`` (vlanaware);
    pve2 con solo ``vmbr0``. La plantilla trae ``net0`` y ``net1`` en vmbr0."""
    return MundoC(
        nodos=("pve1", "pve2"),
        bridges={
            "pve1": (bridge("vmbr0", mtu=1500), bridge("vmbr1", vlan_aware=True)),
            "pve2": (bridge("vmbr0", mtu=1500),),
        },
        redes_sdn={
            "pve1": (vnet("plana"), vnet("vlans", vlan_aware=True)),
            "pve2": (),
        },
    )


def validar(m: MundoC, cfg, version=(9, 2)):
    return validar_vm(cfg, m.inv, Capacidades(version=version, forzada=False))


def cfg_posts(m: MundoC, nodo="pve1", **kw):
    """Configuración de creación desde ISO (origen ``POST``) con ``redes`` a medida."""
    cfg = cfg_base(nodo=nodo, **kw)
    return cfg


def test_ca_c2_2_3_vlan_sobre_una_vnet_no_vlanaware_es_v_c10_con_la_vnet(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("plana", vlan=100)])
    p = con_codigo(validar(mundo_sdn, cfg), "V-C10")
    assert len(p) == 1
    assert p[0].severidad == Severidad.ERROR
    assert p[0].params["vnet"] == "plana"
    assert p[0].campo == "redes[0].vlan"


def test_ca_c2_2_sin_vlan_la_vnet_no_vlanaware_es_valida(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("plana")])
    assert "V-C10" not in codigos(validar(mundo_sdn, cfg))


def test_ca_c2_2_2_vlan_sobre_una_vnet_vlanaware_es_valida(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("vlans", vlan=100)])
    p = validar(mundo_sdn, cfg)
    assert not {"V-C10", "V-C11", "V-C15", "V-16"} & set(codigos(p))


@pytest.mark.parametrize("vlan", [0, 4095, -5, 100000])
def test_ca_c2_2_4_una_vnet_vlanaware_sigue_con_el_rango_1_a_4094(mundo_sdn, vlan):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("vlans", vlan=vlan)])
    assert "V-15" in codigos(validar(mundo_sdn, cfg), Severidad.ERROR)


@pytest.mark.parametrize("vlan", [1, 4094])
def test_ca_c2_2_4_los_extremos_del_rango_de_vlan_son_validos(mundo_sdn, vlan):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("vlans", vlan=vlan)])
    assert "V-15" not in codigos(validar(mundo_sdn, cfg))


def test_ca_c2_2_5_un_bridge_con_vlan_no_da_v_c10_aunque_se_llame_como_una_vnet(mundo_sdn):
    """CA-C2.1.4: si el nombre es de un bridge, se valida como bridge (el núcleo es la fuente)."""
    inv = con_redes(
        mundo_sdn.inv,
        bridges={"pve1": (bridge("plana"),), "pve2": ()},
        vnets={"pve1": (vnet("plana", vlan_aware=False),), "pve2": ()},
    )
    cfg = cfg_base(redes=[InterfazRed("plana", vlan=10)])
    p = validar_vm(cfg, inv, Capacidades((9, 2), False))
    assert "V-C10" not in codigos(p)
    cfg = cfg_base(redes=[InterfazRed("vmbr0", vlan=10)])
    assert "V-C10" not in codigos(validar(mundo_sdn, cfg))


def test_ca_c2_3_2_una_vnet_que_solo_existe_en_otro_nodo_es_v_c11_y_no_v_16(mundo_sdn):
    """CA-C2.3.2 / CL-C12: fila en pve2 con la VNet ``plana`` que solo existe en pve1."""
    cfg = cfg_posts(mundo_sdn, nodo="pve2", redes=[InterfazRed("plana")])
    p = validar(mundo_sdn, cfg)
    v11 = con_codigo(p, "V-C11")
    assert len(v11) == 1 and v11[0].severidad == Severidad.ERROR
    assert v11[0].params["vnet"] == "plana"
    assert v11[0].params["nodo"] == "pve2"
    assert "V-16" not in codigos(p)


def test_ca_c2_3_la_vnet_presente_en_el_nodo_asignado_no_da_v_c11(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, nodo="pve1", redes=[InterfazRed("plana")])
    assert "V-C11" not in codigos(validar(mundo_sdn, cfg))


def test_v_c12_una_red_que_no_existe_en_ningun_nodo_sigue_siendo_v_16(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("fantasma")])
    p = validar(mundo_sdn, cfg)
    v16 = con_codigo(p, "V-16")
    assert v16 and v16[0].params["bridge"] == "fantasma" and v16[0].params["nodo"] == "pve1"
    assert "V-C11" not in codigos(p)


def test_ca_c2_1_6_una_vnet_pendiente_de_aplicar_no_se_ofrece_y_si_se_pide_es_v_16(mundo_sdn):
    """CL-C11: no aparece en ``any_bridge``, luego el lote guardado que la usa da V-C12."""
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("recien-creada")])
    assert "V-16" in codigos(validar(mundo_sdn, cfg), Severidad.ERROR)


def test_ca_c4_6_2_mtu_9000_con_bridge_de_1500_conocida_es_v_c14_aviso(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("vmbr0", mtu=9000)])
    p = con_codigo(validar(mundo_sdn, cfg), "V-C14")
    assert len(p) == 1 and p[0].severidad == Severidad.AVISO
    assert (p[0].params["mtu"], p[0].params["mtu_red"]) == ("9000", "1500")


@pytest.mark.parametrize("mtu", [1500, 1400, 1])
def test_ca_c4_6_2_una_mtu_menor_igual_o_igual_al_bridge_no_avisa(mundo_sdn, mtu):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("vmbr0", mtu=mtu)])
    assert "V-C14" not in codigos(validar(mundo_sdn, cfg))


def test_ca_c4_6_2_sin_mtu_conocida_de_la_vnet_no_se_puede_avisar(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("vlans", mtu=9000)])
    assert "V-C14" not in codigos(validar(mundo_sdn, cfg))


def test_ca_c4_6_3_la_mtu_con_e1000_no_da_v_c14(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("vmbr0", modelo=ModeloRed.E1000, mtu=9000)])
    assert "V-C14" not in codigos(validar(mundo_sdn, cfg))


def test_v_c50_usar_una_vnet_en_una_version_sin_sdn_es_error_con_la_version(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("plana")])
    p = con_codigo(validar(mundo_sdn, cfg, version=(7, 4)), "V-C50")
    assert p and p[0].severidad == Severidad.ERROR
    assert p[0].params["version"] == "8.0"


def test_v_c50_con_bridges_no_se_exige_version_de_sdn(mundo_sdn):
    cfg = cfg_posts(mundo_sdn, redes=[InterfazRed("vmbr0")])
    assert "V-C50" not in codigos(validar(mundo_sdn, cfg, version=(7, 4)))


# --- Red del clon: validación -------------------------------------------------------------------


def clon(m: MundoC, red, nodo="pve1", **kw):
    cfg = cfg_con_red(m, red, **kw)
    return dataclasses.replace(cfg, nodo=nodo)


def test_ca_c2_2_3_clon_con_vlan_sobre_vnet_no_vlanaware_es_v_c10(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, bridge="plana", vlan=100)))
    p = con_codigo(validar(mundo_sdn, cfg), "V-C10")
    assert len(p) == 1 and p[0].params["vnet"] == "plana"
    assert p[0].campo == "red_clon.tarjetas[0].vlan"


def test_ca_c2_2_clon_vnet_no_vlanaware_sin_vlan_es_valido(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, bridge="plana", vlan=None)))
    assert not {"V-C10", "V-16", "V-C11"} & set(codigos(validar(mundo_sdn, cfg)))


def test_ca_c2_2_clon_vnet_vlanaware_con_vlan_es_valido(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, bridge="vlans", vlan=100)))
    assert not {"V-C10", "V-16", "V-C11", "V-C15"} & set(codigos(validar(mundo_sdn, cfg)))


def test_ca_c2_2_cambiar_solo_la_vlan_de_una_tarjeta_en_una_vnet_no_vlanaware_es_v_c10():
    """La red efectiva es la que ya tiene la tarjeta si no se cambia el bridge."""
    m = MundoC(
        extra={"net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=plana"},
        bridges={"pve1": (bridge("vmbr0"),)},
        redes_sdn={"pve1": (vnet("plana"),)},
    )
    cfg = clon(m, red_clon(cambiar(0, vlan=50)))
    assert "V-C10" in codigos(validar(m, cfg), Severidad.ERROR)


def test_ca_c2_3_2_clon_en_pve2_con_vnet_de_pve1_es_v_c11(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, bridge="plana")), nodo="pve2")
    p = validar(mundo_sdn, cfg)
    v11 = con_codigo(p, "V-C11")
    assert len(v11) == 1 and v11[0].params["nodo"] == "pve2"
    assert "V-16" not in codigos(p)


def test_v_c12_clon_con_red_inexistente_en_el_nodo_es_v_16(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, bridge="fantasma")))
    p = con_codigo(validar(mundo_sdn, cfg), "V-16")
    assert p and p[0].params["bridge"] == "fantasma"


def test_v_16_clon_con_nombre_de_red_con_caracteres_prohibidos_es_error(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, bridge="a,b=c")))
    assert "V-16" in codigos(validar(mundo_sdn, cfg), Severidad.ERROR)


@pytest.mark.parametrize("vlan", [0, 4095, -1])
def test_ca_c4_6_1_vlan_fuera_de_rango_en_el_clon_es_v_c15(mundo_sdn, vlan):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, vlan=vlan)))
    assert "V-C15" in codigos(validar(mundo_sdn, cfg), Severidad.ERROR)


def test_ca_c4_6_1_una_vlan_valida_en_el_clon_no_da_v_c15(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, vlan=20)))
    assert "V-C15" not in codigos(validar(mundo_sdn, cfg))


def test_ca_c4_6_1_en_una_tarjeta_nueva_la_vlan_tambien_se_valida(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(anadir(2, bridge="vmbr0", vlan=4095)))
    assert "V-C15" in codigos(validar(mundo_sdn, cfg), Severidad.ERROR)


def test_ca_c4_6_2_mtu_mayor_que_la_del_bridge_al_cambiar_tambien_el_bridge_es_v_c14(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, bridge="vmbr0", mtu=9000)))
    p = con_codigo(validar(mundo_sdn, cfg), "V-C14")
    assert len(p) == 1 and p[0].severidad == Severidad.AVISO
    assert p[0].params["mtu_red"] == "1500"


def test_ca_c4_6_2_mtu_mayor_que_la_del_bridge_cambiando_solo_la_mtu_es_v_c14(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, mtu=9000)))
    assert "V-C14" in codigos(validar(mundo_sdn, cfg), Severidad.AVISO)


def test_ca_c4_6_3_mtu_con_e1000_en_el_clon_es_aviso_v_a05(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, modelo="e1000", mtu=1400)))
    p = con_codigo(validar(mundo_sdn, cfg), "V-A05")
    assert p and p[0].severidad == Severidad.AVISO


@pytest.mark.parametrize("mtu", [0, 575, 65521])
def test_ca_c4_6_mtu_fuera_de_rango_en_el_clon_es_error_de_la_fase_a(mundo_sdn, mtu):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, mtu=mtu)))
    assert "V-A04" in codigos(validar(mundo_sdn, cfg), Severidad.ERROR)


def test_ca_c4_4_4_anadir_con_32_tarjetas_ya_presentes_es_v_c17():
    extra = {f"net{i}": f"virtio=AA:BB:CC:DD:00:{i:02X},bridge=vmbr0" for i in range(32)}
    m = MundoC(extra=extra, redes=32)
    cfg = clon(m, red_clon(anadir(0, bridge="vmbr0")))
    p = con_codigo(validar(m, cfg), "V-C17")
    assert p and p[0].severidad == Severidad.ERROR


def test_ca_c4_4_4_anadir_con_31_tarjetas_presentes_cabe():
    extra = {f"net{i}": f"virtio=AA:BB:CC:DD:00:{i:02X},bridge=vmbr0" for i in range(31)}
    m = MundoC(extra=extra, redes=31)
    cfg = clon(m, red_clon(anadir(31, bridge="vmbr0")))
    assert "V-C17" not in codigos(validar(m, cfg))


def test_ca_c4_4_5_quitar_todas_las_tarjetas_es_v_c18_aviso_y_se_permite(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(quitar(0), quitar(1)))
    p = validar(mundo_sdn, cfg)
    assert con_codigo(p, "V-C18")[0].severidad == Severidad.AVISO
    assert not [x for x in p if x.codigo.startswith("V-C") and x.severidad == Severidad.ERROR]


def test_ca_c4_4_5_quitar_todas_pero_anadir_otra_no_avisa(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(quitar(0), quitar(1), anadir(2, bridge="vmbr0")))
    assert "V-C18" not in codigos(validar(mundo_sdn, cfg))


def test_ca_c4_4_6_cloudinit_configurado_para_una_tarjeta_que_se_quita_es_v_c16(mundo_sdn):
    from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit, ModoTarjeta, TarjetaCloudInit

    ci = ConfigCloudInit(usuario="deploy", tarjetas=(TarjetaCloudInit(1, ModoTarjeta.DHCP),))
    cfg = dataclasses.replace(clon(mundo_sdn, red_clon(quitar(1))), cloudinit=ci)
    p = con_codigo(validar(mundo_sdn, cfg), "V-C16")
    assert len(p) == 1 and p[0].severidad == Severidad.ERROR
    assert p[0].params["tarjeta"] == "1"


def test_ca_c4_4_6_cloudinit_en_otra_tarjeta_o_sin_configurar_no_da_v_c16(mundo_sdn):
    from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit, ModoTarjeta, TarjetaCloudInit

    ci = ConfigCloudInit(
        usuario="deploy",
        tarjetas=(
            TarjetaCloudInit(0, ModoTarjeta.DHCP),
            TarjetaCloudInit(1, ModoTarjeta.SIN_CONFIGURAR),
        ),
    )
    cfg = dataclasses.replace(clon(mundo_sdn, red_clon(quitar(1))), cloudinit=ci)
    assert "V-C16" not in codigos(validar(mundo_sdn, cfg))


def test_ca_c4_2_3_una_tarjeta_ilegible_de_la_plantilla_es_v_c20_aviso():
    m = MundoC(extra={"net1": "esto no es una tarjeta"})
    cfg = clon(m, red_clon(cambiar(0, vlan=3)))
    p = con_codigo(validar(m, cfg), "V-C20")
    assert p and p[0].severidad == Severidad.AVISO and p[0].params["tarjeta"] == "net1"


def test_v_c51_red_del_clon_con_un_origen_que_no_clona_es_error(mundo_sdn):
    cfg = cfg_base(red_clon=red_clon(cambiar(0, bridge="vmbr0")))
    p = validar(mundo_sdn, cfg)
    assert "V-C51" in codigos(p, Severidad.ERROR)


def test_v_c50_reescribir_la_red_del_clon_en_una_version_sin_la_funcion_es_error(mundo_sdn):
    assert Capacidades((7, 4), False).tiene(Funcion.REESCRIBIR_RED_CLON) is False
    cfg = clon(mundo_sdn, red_clon(cambiar(0, vlan=3)))
    assert "V-C50" in codigos(validar(mundo_sdn, cfg, version=(7, 4)), Severidad.ERROR)


def test_v_c50_en_la_version_minima_8_0_reescribir_la_red_esta_permitido(mundo_sdn):
    cfg = clon(mundo_sdn, red_clon(cambiar(0, vlan=3)))
    assert "V-C50" not in codigos(validar(mundo_sdn, cfg, version=(8, 0)))


def _permisos(**rutas: dict[str, int]) -> PermisosEfectivos:
    return PermisosEfectivos(rutas={r.replace("__", "/"): p for r, p in rutas.items()})


def _con_permisos(m: MundoC, permisos: PermisosEfectivos | None):
    cat = dataclasses.replace(m.inv.catalogo, permisos=permisos)
    return dataclasses.replace(m.inv, catalogo=cat)


def test_ca_c4_5_4_con_sdn_use_conocido_en_false_comprobar_avisa_antes_v_c19(mundo_sdn):
    permisos = PermisosEfectivos(rutas={"/": {"VM.Allocate": 1}})
    inv = _con_permisos(mundo_sdn, permisos)
    cfg = clon(mundo_sdn, red_clon(cambiar(0, vlan=3)))
    p = con_codigo(validar_vm(cfg, inv, Capacidades((9, 2), False)), "V-C19")
    assert p and p[0].severidad == Severidad.AVISO
    assert p[0].params["red"] == "vmbr0" and p[0].params["plantilla"] == "base"


def test_ca_c4_5_4_con_permisos_desconocidos_no_hay_aviso_previo(mundo_sdn):
    inv = _con_permisos(mundo_sdn, None)
    cfg = clon(mundo_sdn, red_clon(cambiar(0, vlan=3)))
    assert "V-C19" not in codigos(validar_vm(cfg, inv, Capacidades((9, 2), False)))


def test_ca_c4_5_4_con_sdn_use_concedido_en_la_zona_local_no_hay_aviso(mundo_sdn):
    permisos = PermisosEfectivos(rutas={"/sdn/zones/localnetwork": {"SDN.Use": 1}})
    inv = _con_permisos(mundo_sdn, permisos)
    cfg = clon(mundo_sdn, red_clon(cambiar(0, vlan=3)))
    assert "V-C19" not in codigos(validar_vm(cfg, inv, Capacidades((9, 2), False)))


def test_ca_c4_5_4_v_c19_tambien_avisa_sin_red_personalizada_cuando_hay_paso_de_red(mundo_sdn):
    """Con el firewall (C3) activo hay ``PUT`` de red aunque la red sea «Como la plantilla»."""
    from proxlaunch.nucleo.firewall.modelos import FirewallMV

    inv = _con_permisos(mundo_sdn, PermisosEfectivos(rutas={"/": {"VM.Allocate": 1}}))
    cfg = dataclasses.replace(mundo_sdn.cfg(), firewall=FirewallMV(activo=True))
    assert "V-C19" in codigos(validar_vm(cfg, inv, Capacidades((9, 2), False)))
    sin = mundo_sdn.cfg()
    assert "V-C19" not in codigos(validar_vm(sin, inv, Capacidades((9, 2), False)))


def test_ca_c4_5_4_las_redes_virtuales_no_dan_v_c19_porque_su_zona_no_se_conoce():
    m = MundoC(
        redes=1,
        extra={"net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=prod"},
        redes_sdn={"pve1": (vnet("prod"),)},
    )
    inv = _con_permisos(m, PermisosEfectivos(rutas={"/": {"VM.Allocate": 1}}))
    cfg = clon(m, red_clon(cambiar(0, limite_mb=5.0)))
    assert "V-C19" not in codigos(validar_vm(cfg, inv, Capacidades((9, 2), False)))


def test_resolver_origen_de_un_clon_sin_red_personalizada_no_da_problemas_de_red(mundo_sdn):
    cfg, problemas = resolver_origen(mundo_sdn.cfg(), mundo_sdn.inv, "pve1")
    assert problemas == []
    assert cfg.red_clon is None


# --- RF-C4.5, RF-C4.9: lectura de los errores de SDN ---------------------------------------------


def _403(ruta: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE, {"ruta": ruta, "privilegio": "SDN.Use"}, "403"
    )


def test_ca_c4_5_1_un_403_de_sdn_use_al_reescribir_nombra_tarjeta_red_y_zona():
    e = anotar_error_red(
        _403("/sdn/zones/localnetwork/vmbr9"), paso="red", antiguas={0: "vmbr9"}, nuevas={0: "lab"}
    )
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert (e.params["zona"], e.params["red"], e.params["tarjeta"]) == (
        "localnetwork",
        "vmbr9",
        "net0",
    )
    assert e.params["lado"] == "antigua"


def test_ca_c4_5_el_403_de_la_red_nueva_se_distingue_de_la_antigua():
    e = anotar_error_red(
        _403("/sdn/zones/z1/prod"), paso="red", antiguas={0: "vmbr0"}, nuevas={0: "prod"}
    )
    assert e.params["lado"] == "nueva"
    assert e.params["tarjeta"] == "net0"


def test_ca_c4_5_2_un_403_durante_el_clon_es_de_la_red_de_la_plantilla():
    e = anotar_error_red(
        _403("/sdn/zones/localnetwork/vmbr9"), paso="clon", antiguas={1: "vmbr9"}, nuevas={}
    )
    assert e.params["lado"] == "plantilla" and e.params["tarjeta"] == "net1"


def test_ca_c2_5_3_un_403_al_crear_con_vnet_nombra_vnet_zona_y_vlan_si_la_ruta_la_trae():
    e = anotar_error_red(
        _403("/sdn/zones/z1/prod/100"), paso="crear", antiguas={}, nuevas={2: "prod"}
    )
    assert (e.params["zona"], e.params["red"], e.params["vlan"]) == ("z1", "prod", "100")
    assert e.params["lado"] == "nueva" and e.params["tarjeta"] == "net2"


def test_ca_c4_5_3_un_403_que_no_es_de_sdn_use_se_devuelve_igual():
    e = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"ruta": "/vms/100", "privilegio": "X"})
    assert anotar_error_red(e, paso="red", antiguas={}, nuevas={}) is e
    sin_ruta = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {})
    assert anotar_error_red(sin_ruta, paso="red", antiguas={}, nuevas={}) is sin_ruta


@pytest.mark.parametrize(
    "ruta", ["/sdn/zones/z1", "/sdn/zones/z1/<x>/", "/sdn/zones/z1/a b", "/sdn/zones/z1/p/12345"]
)
def test_ca_c4_5_una_ruta_de_sdn_mal_formada_no_se_anota(ruta):
    e = _403(ruta)
    assert anotar_error_red(e, paso="red", antiguas={}, nuevas={}) is e


def test_ca_c4_5_un_paso_desconocido_no_anota_nada():
    e = _403("/sdn/zones/z1/prod")
    assert anotar_error_red(e, paso="otro", antiguas={}, nuevas={}) is e


def test_ca_c4_9_1_sin_direcciones_libres_en_la_zona_se_traduce_a_red_sin_direcciones():
    e = ErrorProxLaunch(
        CodigoError.DESCONOCIDO, {}, "500: can't find any free ip in zone z1 for vnet prod"
    )
    r = anotar_error_red(e, paso="red", antiguas={}, nuevas={})
    assert r.codigo == CodigoError.RED_SIN_DIRECCIONES and r.params == {"zona": "z1"}
    sin_zona = ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "can't find any free ip")
    assert anotar_error_red(sin_zona, paso="red", antiguas={}, nuevas={}).params == {}


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("HTTP 400: digest: detected modified configuration - file changed", True),
        ("Parameter verification failed. DIGEST mismatch", True),
        ("HTTP 500: bridge does not exist", False),
        ("", False),
    ],
)
def test_ca_c4_3_6_el_error_de_digest_se_reconoce_por_el_texto(texto, esperado):
    assert es_error_digest(ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, texto)) is esperado


# --- RNF-C6 y reglas sobre el texto del servidor --------------------------------------------------


def test_rnf_c6_una_vnet_no_confiable_no_llega_a_la_peticion_si_no_cumple_el_patron():
    """CA-C2.1.5: el nombre de red de un lote guardado se valida antes de enviarse."""
    from proxlaunch.nucleo.red.modelos import RE_NOMBRE_RED

    for malo in ("a,b", "a b", "", "x" * 41, "a=b", "<b>", "a\n", "ñandú"):
        assert RE_NOMBRE_RED.fullmatch(malo) is None, malo
    for bueno in ("prod", "vmbr0", "z1.v-2_x", "x" * 40):
        assert RE_NOMBRE_RED.fullmatch(bueno) is not None, bueno


def test_ca_c2_1_5_redvirtual_es_un_dato_inmutable():
    v = RedVirtual("prod", "Producción", True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.nombre = "otra"  # type: ignore[misc]
    assert v.tipo_declarado is True and v.zona is None
