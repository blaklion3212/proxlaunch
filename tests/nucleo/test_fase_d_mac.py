"""D1.10: dirección MAC conservada (RF-D1.10, CL-D1; V-D32, V-D33 y V-D34).

Derivadas de docs/requisitos/fase-d.md: CA-D1.10.1 a CA-D1.10.7 y RF-D0.2 (sin MAC conservada la
petición es la de 0.8.0). La casilla «Conservar la MAC» es de la interfaz (ver las pruebas de
interfaz); aquí se comprueba el modelo (``InterfazRed.mac_conservada``), ``proponer``,
``validar_importacion_d`` y ``construir_parametros``.
"""

from __future__ import annotations

import dataclasses

import pytest

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.constructor_peticion import construir_parametros, valor_red
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.libvirt.validacion import (
    mac_valida,
    normalizar_mac,
    validar_importacion_d,
)
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.vm import InterfazRed, ModeloRed
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_fase_d_libvirt import (
    disco_xml,
    dominio_desde_texto,
    fila,
    inventario_d,
    proponer_de,
    xml_minimo,
)
from .apoyo_mvp4 import cfg_import, inv_origen

CAPS = capacidades_para(Version("9.2", 9, 2, 0), None)
INV = inv_origen()
MAC = "52:54:00:ab:cd:ef"


def _nic(mac: str | None, bridge: str = "vmbr0") -> str:
    m = "" if mac is None else f"<mac address='{mac}'/>"
    return (
        f"<interface type='bridge'>{m}<source bridge='{bridge}'/><model type='virtio'/></interface>"
    )


def _cfg_con_macs(*macs: str | None):
    cfg = cfg_import()
    cfg.redes = [InterfazRed("vmbr0", mac_conservada=m) for m in macs]
    return cfg


def _codigos(problemas) -> list[str]:
    return [p.codigo for p in problemas]


# --- CA-D1.10.1 y CA-D1.10.7: sin tocar nada, MAC nueva --------------------------------------


def test_ca_d1_10_1_sin_conservar_la_tarjeta_no_lleva_mac_y_la_genera_proxmox():
    p = proponer_de(dominio_desde_texto(xml_minimo(disco_xml() + _nic(MAC))), inv=inventario_d())
    assert p.cfg.redes[0].mac_conservada is None
    params = construir_parametros(_con_origen(p.cfg), INV)
    assert params["net0"] == "virtio,bridge=vmbr0"
    assert "macaddr" not in "".join(params.values()).lower()
    assert MAC not in "".join(params.values()).lower()


def _con_origen(cfg):
    """La propuesta pide elegir imagen: se le pone una para poder construir la petición."""
    from proxlaunch.nucleo.modelos.origen import DetalleImportacion, RefVolumen

    cfg = dataclasses.replace(cfg, nodo="pve1", discos=cfg.discos[:1] or cfg_import().discos)
    cfg.detalle_origen = DetalleImportacion(imagen=RefVolumen("a.qcow2", "local:import/a.qcow2"))
    cfg.discos[0].storage = "local-lvm"
    cfg.redes = [dataclasses.replace(r, bridge="vmbr0") for r in cfg.redes]
    return cfg


def test_ca_d1_10_1_la_fila_de_vista_previa_dice_que_la_mac_sera_nueva():
    p = proponer_de(dominio_desde_texto(xml_minimo(disco_xml() + _nic(MAC))), inv=inventario_d())
    f = fila(p, "red[0].mac")
    assert f.origen == MAC and f.destino == "nueva" and f.problema is None


def test_ca_d1_10_7_ninguna_mac_conservada_deja_la_peticion_de_0_8_0():
    cfg = _cfg_con_macs(None, None)
    params = construir_parametros(cfg, INV)
    assert params["net0"] == "virtio,bridge=vmbr0" and params["net1"] == "virtio,bridge=vmbr0"
    assert validar_importacion_d(cfg) == []


def test_ca_d1_10_7_el_valor_por_defecto_del_campo_es_none():
    assert InterfazRed("vmbr0").mac_conservada is None


# --- CA-D1.10.2: MAC conservada -----------------------------------------------------------------


def test_ca_d1_10_2_la_mac_conservada_va_en_mayusculas_tras_el_modelo():
    cfg = _cfg_con_macs(MAC)
    assert construir_parametros(cfg, INV)["net0"] == "virtio=52:54:00:AB:CD:EF,bridge=vmbr0"


def test_ca_d1_10_2_aparece_v_d32_como_aviso():
    p = validar_importacion_d(_cfg_con_macs(MAC))
    assert _codigos(p) == ["V-D32"]
    assert p[0].severidad == Severidad.AVISO and p[0].campo == "redes[0].mac_conservada"


def test_ca_d1_10_2_el_modelo_e1000_tambien_lleva_la_mac():
    r = InterfazRed("vmbr0", ModeloRed.E1000, mac_conservada=MAC)
    assert valor_red(r) == "e1000=52:54:00:AB:CD:EF,bridge=vmbr0"


def test_ca_d1_10_2_el_orden_de_las_opciones_de_red_se_mantiene_con_mac():
    r = InterfazRed("vmbr0", vlan=20, mtu=9000, limite_mb=11.0, mac_conservada=MAC)
    assert valor_red(r, firewall=True) == (
        "virtio=52:54:00:AB:CD:EF,bridge=vmbr0,tag=20,mtu=9000,rate=11,firewall=1"
    )


def test_ca_d1_10_2_proponer_con_conservar_mac_marca_todas_las_tarjetas_con_mac():
    xml = xml_minimo(disco_xml() + _nic(MAC) + _nic(None) + _nic("52:54:00:11:22:33"))
    p = proponer_de(dominio_desde_texto(xml), inv=inventario_d(), conservar_mac=True)
    assert [r.mac_conservada for r in p.cfg.redes] == [MAC, None, "52:54:00:11:22:33"]
    f = fila(p, "red[0].mac")
    assert f.destino == MAC and f.problema.codigo == "V-D32"
    assert fila(p, "red[1].mac") is None


def test_ca_d1_10_2_la_mac_del_xml_en_mayusculas_se_guarda_normalizada():
    p = proponer_de(
        dominio_desde_texto(xml_minimo(disco_xml() + _nic("52:54:00:AB:CD:EF"))),
        inv=inventario_d(),
        conservar_mac=True,
    )
    assert p.cfg.redes[0].mac_conservada == MAC
    assert validar_importacion_d(p.cfg) and "V-D34" not in _codigos(validar_importacion_d(p.cfg))


# --- CA-D1.10.3: solo con cantidad = 1 ----------------------------------------------------------


@pytest.mark.parametrize("cantidad", [2, 3, 100])
def test_ca_d1_10_3_con_varias_copias_es_v_d33_error(cantidad):
    p = validar_importacion_d(_cfg_con_macs(MAC), cantidad)
    v33 = [x for x in p if x.codigo == "V-D33"]
    assert len(v33) == 1 and v33[0].severidad == Severidad.ERROR
    assert v33[0].params["n"] == str(cantidad)


def test_ca_d1_10_3_con_una_sola_copia_se_permite():
    assert "V-D33" not in _codigos(validar_importacion_d(_cfg_con_macs(MAC), 1))


def test_ca_d1_10_3_cada_tarjeta_conservada_da_su_v_d33():
    p = validar_importacion_d(_cfg_con_macs(MAC, "52:54:00:11:22:33"), 3)
    assert [x.campo for x in p if x.codigo == "V-D33"] == [
        "redes[0].mac_conservada",
        "redes[1].mac_conservada",
    ]


def test_ca_d1_10_3_sin_mac_conservada_la_cantidad_no_importa():
    assert validar_importacion_d(_cfg_con_macs(None), 50) == []


def test_ca_d1_10_3_la_validacion_de_la_maquina_no_conoce_la_cantidad_y_asume_una():
    # validar_vm valida UNA máquina; V-D33 lo añade quien conoce el lote (planificador).
    assert "V-D33" not in [p.codigo for p in validar_vm(_cfg_con_macs(MAC), INV, CAPS)]


# --- CA-D1.10.4: MAC inválida --------------------------------------------------------------------


@pytest.mark.parametrize(
    "mac",
    [
        "01:00:5e:00:00:01",  # multidifusión (bit I/G = 1)
        "ff:ff:ff:ff:ff:ff",  # difusión
        "03:00:00:00:00:00",
        "zz:11:22:33:44:55",
        "52:54:00:ab:cd",  # corta
        "52:54:00:ab:cd:ef:00",  # larga
        "52-54-00-ab-cd-ef",  # separador distinto
        "525400abcdef",
        "52:54:00:AB:CD:EF",  # mayúsculas: lo almacenado ya viene normalizado
        " 52:54:00:ab:cd:ef",
        "52:54:00:ab:cd:ef\n",
        "",
        "52:54:00:ab:cd:e١",
    ],
)
def test_ca_d1_10_4_mac_con_formato_o_bit_de_grupo_invalidos_es_v_d34(mac):
    assert mac_valida(mac) is False
    p = validar_importacion_d(_cfg_con_macs(mac))
    v34 = [x for x in p if x.codigo == "V-D34"]
    assert len(v34) == 1 and v34[0].severidad == Severidad.ERROR
    assert v34[0].campo == "redes[0].mac_conservada"


@pytest.mark.parametrize(
    "mac", ["52:54:00:ab:cd:ef", "00:00:00:00:00:02", "fe:ff:ff:ff:ff:fe", "02:00:00:00:00:00"]
)
def test_ca_d1_10_4_las_mac_unicast_bien_formadas_son_validas(mac):
    assert mac_valida(mac) is True
    assert "V-D34" not in _codigos(validar_importacion_d(_cfg_con_macs(mac)))


def test_ca_d1_10_4_el_valor_mostrado_en_v_d34_va_acotado_y_sin_marcado():
    mala = "<b>" + "9" * 500 + "&"
    p = validar_importacion_d(_cfg_con_macs(mala))
    mostrado = next(x for x in p if x.codigo == "V-D34").params["mac"]
    assert len(mostrado) <= 32 and not set("<>&") & set(mostrado)


def test_ca_d1_10_4_las_mac_no_cadena_no_rompen_la_validacion():
    cfg = _cfg_con_macs(MAC)
    cfg.redes[0].mac_conservada = 12345  # tipo erróneo desde un archivo manipulado
    assert "V-D34" in _codigos(validar_importacion_d(cfg))


def test_ca_d1_10_4_la_peticion_rechaza_una_mac_malformada_aunque_la_validacion_se_saltara():
    for mala in (
        "zz:11:22:33:44:55",
        f"{MAC},bridge=evil",
        "52:54:00:ab:cd:ef;x",
        "52:54:00:ab:cd:ef\n",
    ):
        with pytest.raises(ErrorProxLaunch) as e:
            valor_red(InterfazRed("vmbr0", mac_conservada=mala))
        assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO


def test_ca_d1_10_4_validar_vm_integra_v_d34():
    assert "V-D34" in _codigos(validar_vm(_cfg_con_macs("01:00:5e:00:00:01"), INV, CAPS))


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("52:54:00:AB:CD:EF", MAC),
        ("52-54-00-AB-CD-EF", MAC),
        ("  52:54:00:ab:cd:ef  ", MAC),
        ("52:54:00:ab:cd", None),
        ("zz:54:00:ab:cd:ef", None),
        ("", None),
    ],
)
def test_normalizar_mac(texto, esperado):
    assert normalizar_mac(texto) == esperado


def test_normalizar_mac_con_no_cadena_devuelve_none():
    assert normalizar_mac(None) is None  # type: ignore[arg-type]
    assert mac_valida(None) is False  # type: ignore[arg-type]


# --- CA-D1.10.5: elegir por tarjeta --------------------------------------------------------------


def test_ca_d1_10_5_dos_tarjetas_con_mac_y_solo_una_marcada_solo_esa_lleva_mac():
    cfg = _cfg_con_macs(None, "52:54:00:11:22:33")
    params = construir_parametros(cfg, INV)
    assert params["net0"] == "virtio,bridge=vmbr0"
    assert params["net1"] == "virtio=52:54:00:11:22:33,bridge=vmbr0"


def test_ca_d1_10_5_una_marcada_y_la_otra_no_solo_avisa_de_la_marcada():
    p = validar_importacion_d(_cfg_con_macs(MAC, None))
    assert [x.campo for x in p] == ["redes[0].mac_conservada"]


def test_ca_d1_10_5_dos_tarjetas_con_la_misma_mac_no_se_detectan_en_esta_validacion():
    """Una MAC repetida entre tarjetas de la misma MV no es V-D33/V-D34 (queda a Proxmox)."""
    assert "V-D34" not in _codigos(validar_importacion_d(_cfg_con_macs(MAC, MAC)))


# --- CA-D1.10.6: sin <mac> en el XML ------------------------------------------------------------


def test_ca_d1_10_6_sin_mac_en_el_xml_no_hay_nada_que_conservar():
    d = dominio_desde_texto(xml_minimo(disco_xml() + _nic(None)))
    assert d.tarjetas[0].mac is None
    p = proponer_de(d, inv=inventario_d(), conservar_mac=True)
    assert p.cfg.redes[0].mac_conservada is None and fila(p, "red[0].mac") is None
    assert validar_importacion_d(p.cfg) == []


@pytest.mark.parametrize("mac", ["zz:11:22:33:44:55", "52:54:00", "", "no es una mac"])
def test_ca_d1_10_6_una_mac_ilegible_en_el_xml_se_trata_como_ausente(mac):
    d = dominio_desde_texto(xml_minimo(disco_xml() + _nic(mac)))
    assert d.tarjetas[0].mac is None


def test_la_mac_de_multidifusion_del_xml_llega_al_formulario_y_se_bloquea_con_v_d34():
    xml = xml_minimo(disco_xml() + _nic("01:00:5e:00:00:01"))
    p = proponer_de(dominio_desde_texto(xml), inv=inventario_d(), conservar_mac=True)
    assert p.cfg.redes[0].mac_conservada == "01:00:5e:00:00:01"
    assert "V-D34" in _codigos(validar_importacion_d(p.cfg))


def test_la_mac_se_guarda_siempre_en_minusculas_y_con_dos_puntos_en_el_dominio():
    d = dominio_desde_texto(xml_minimo(disco_xml() + _nic("52:54:00:AB:CD:EF")))
    assert d.tarjetas[0].mac == MAC


# --- Petición en ARM -----------------------------------------------------------------------------


def test_la_mac_conservada_tambien_viaja_en_un_nodo_aarch64():
    from proxlaunch.nucleo.arquitectura.modelos import Arquitectura

    inv = inventario_d({"pve1": Arquitectura.AARCH64}, bridges=("vmbr0",))
    # el almacenamiento de inv_origen no está en inventario_d: se reutiliza el de inv_origen
    inv = dataclasses.replace(INV, arquitecturas=inv.arquitecturas)
    cfg = _cfg_con_macs(MAC)
    params = construir_parametros(cfg, inv)
    assert params["net0"] == "virtio=52:54:00:AB:CD:EF,bridge=vmbr0"


# --- El plan del lote -----------------------------------------------------------------------------


def _plan_con_mac(cantidad: int):
    from .apoyo_lote import definicion
    from .test_lote_presupuesto import _plan

    return _plan(definicion(cantidad, plantilla_vm=_cfg_con_macs(MAC)), INV)


def test_ca_d1_10_3_un_lote_de_tres_copias_con_mac_conservada_queda_bloqueado_con_v_d33():
    plan = _plan_con_mac(3)
    assert plan.bloqueado
    assert ("V-D33", Severidad.ERROR) in [(p.regla, p.severidad) for p in plan.problemas]


def test_ca_d1_10_3_con_una_sola_copia_el_plan_solo_avisa_con_v_d32():
    plan = _plan_con_mac(1)
    assert not plan.bloqueado
    assert [(p.regla, p.severidad) for p in plan.problemas] == [("V-D32", Severidad.AVISO)]
