"""Validación (ronda F7): host con id de zona, tipo de CPU, límite de redes, disco marcado sin
discos, nodo sin bridges y ids de storage/bridge con caracteres que alterarían la API."""

import dataclasses

import pytest

from proxlaunch.nucleo.modelos import Disco, Firmware, InterfazRed, PerfilConexion
from proxlaunch.nucleo.validacion import validar_perfil, validar_vm

from .conftest import storage


def _perfil(host):
    return PerfilConexion(id="p", nombre="lab", hosts=[host])


# --- Hosts ---------------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["fe80::1%eth0", "10.0.0.5%eth0", "srv%1.lab", "fe80::1%25eth0"])
def test_v19_host_con_id_de_zona_es_invalido(host):
    assert [p.codigo for p in validar_perfil(_perfil(host))] == ["V-19"]


@pytest.mark.parametrize("host", ["fe80::1", "2001:db8::1", "10.0.0.5", "pve.lab"])
def test_v19_hosts_sin_porcentaje_siguen_siendo_validos(host):
    assert validar_perfil(_perfil(host)) == []


# --- V-22 tipo de CPU ------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", ["host", "x86-64-v3", "kvm64", "Skylake-Server.v2", "a_b-c.9"])
def test_v22_tipo_de_cpu_valido(tipo, hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(tipo_cpu=tipo), inv, caps), "V-22") == []


@pytest.mark.parametrize(
    "tipo",
    ["", "host,flags=+aes", "kvm 64", "cpu=host", "a:b", "host\n", "host;x", "x" + "é", None, 5],
)
def test_v22_tipo_de_cpu_invalido(tipo, hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(tipo_cpu=tipo), inv, caps), "V-22", "tipo_cpu")


# --- V-23 máximo de redes ---------------------------------------------------------------------


def test_v23_32_redes_es_el_maximo_valido(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(redes=[InterfazRed("vmbr0") for _ in range(32)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-23") == []


def test_v23_mas_de_32_redes_es_invalido(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(redes=[InterfazRed("vmbr0") for _ in range(33)])
    assert len(con_codigo(validar_vm(cfg, inv, caps), "V-23", "redes")) == 1


# --- V-07.sindisco ---------------------------------------------------------------------------


def test_v07_sindisco_con_disco_marcado_y_lista_vacia(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(con_disco=True, discos=[])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-07.sindisco", "discos")


def test_v07_sindisco_no_aplica_si_no_se_pide_disco(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(con_disco=False, discos=[])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-07.sindisco") == []


def test_v07_sindisco_no_aplica_con_discos(hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(), inv, caps), "V-07.sindisco") == []


# --- V-16.sinredes sale de validar_vm ---------------------------------------------------------


def test_v16_sinredes_si_el_nodo_no_tiene_bridges(hacer_cfg, inv, caps, con_codigo):
    sin_bridges = dataclasses.replace(inv, bridges={**inv.bridges, "pve1": ()})
    problemas = validar_vm(hacer_cfg(), sin_bridges, caps)
    assert con_codigo(problemas, "V-16.sinredes", "redes")


def test_v16_sinredes_ignora_interfaces_que_no_son_bridge(hacer_cfg, inv, caps, con_codigo):
    from proxlaunch.nucleo.modelos import Bridge

    solo_eth = dataclasses.replace(
        inv, bridges={**inv.bridges, "pve1": (Bridge("eno1", "eth", False),)}
    )
    assert con_codigo(validar_vm(hacer_cfg(), solo_eth, caps), "V-16.sinredes")


def test_v16_sinredes_no_aparece_con_bridges(hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(), inv, caps), "V-16.sinredes") == []


# --- Caracteres prohibidos en ids -------------------------------------------------------------


def _inv_con_storage(inv, id_):
    extra = storage(id_, "dir", "images", 100)
    return dataclasses.replace(
        inv, storages={**inv.storages, "pve1": (*inv.storages["pve1"], extra)}
    )


@pytest.mark.parametrize("id_", ["a,b", "a=b", "a:b"])
def test_v17_storage_de_disco_con_separador_de_api_es_invalido(
    id_, hacer_cfg, inv, caps, con_codigo
):
    inv2 = _inv_con_storage(inv, id_)
    cfg = hacer_cfg(discos=[Disco(id_, 10)])
    assert con_codigo(validar_vm(cfg, inv2, caps), "V-17", "discos[0].storage")


@pytest.mark.parametrize("id_", ["a,b", "a=b", "a:b"])
def test_v17_storage_efi_con_separador_de_api_es_invalido(id_, hacer_cfg, inv, caps, con_codigo):
    inv2 = _inv_con_storage(inv, id_)
    cfg = hacer_cfg(firmware=Firmware.OVMF, storage_efi=id_)
    assert con_codigo(validar_vm(cfg, inv2, caps), "V-17", "storage_efi")


@pytest.mark.parametrize("bridge", ["vmbr,9", "vmbr=1", "vmbr:1"])
def test_v16_bridge_con_separador_de_api_es_invalido(bridge, hacer_cfg, inv, caps, con_codigo):
    from proxlaunch.nucleo.modelos import Bridge

    inv2 = dataclasses.replace(
        inv,
        bridges={**inv.bridges, "pve1": (*inv.bridges["pve1"], Bridge(bridge, "bridge", False))},
    )
    cfg = hacer_cfg(redes=[InterfazRed(bridge)])
    assert con_codigo(validar_vm(cfg, inv2, caps), "V-16", "redes[0].bridge")
