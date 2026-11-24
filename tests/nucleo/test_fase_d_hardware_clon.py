"""D3.2.4 y D3.5 (0.9.0): plantillas y clones con hardware del clúster asignado.

CA-D3.2.4, CA-D3.5.1–4, CL-D22. Al clonar, ``hostpciN``/``usbN`` no viajan en ``POST …/clone``:
van en un ``PUT config`` propio (paso ``hardware``) sobre los primeros índices libres de la
plantilla, con ``machine=q35`` solo si hace falta, y es idempotente al reintentar.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from proxlaunch.nucleo.modelos.origen import AjustesClon
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.origen.clon import detalle_de_config, parametros_hardware_clon
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.servicios.creacion import (
    AJUSTE_HARDWARE,
    ORDEN_AJUSTES,
)

from .apoyo_fase_a import def_lote, plan_de
from .apoyo_fase_d import V_84, MundoD, hw, pci, usb
from .apoyo_mvp4 import cfg_clon


def _base(m: MundoD, **kw: Any):
    """Clon de la plantilla ``base`` resuelto (admite los avisos V-D58b de la plantilla)."""
    kw.setdefault("etiquetas", ("proxlaunch", "lote-ab12cd34"))
    cfg, problemas = resolver_origen(cfg_clon("base", **kw), m.inv, m.nodos[0])
    assert not [p for p in problemas if p.severidad.value == "error"], problemas
    return cfg


def _cfg(m: MundoD, *dispositivos: Any, **kw: Any):
    cfg = _base(m, **kw)
    return dataclasses.replace(cfg, hardware_cluster=hw(*dispositivos) if dispositivos else None)


def _puts(m: MundoD, vmid: int = 100) -> list[dict[str, str]]:
    return [d for _n, v, q, d in m.cl.puts if v == vmid and q == "config"]


def _puts_hw(m: MundoD, vmid: int = 100) -> list[dict[str, str]]:
    return [d for d in _puts(m, vmid) if any(k.startswith(("hostpci", "usb")) for k in d)]


# --- CA-D3.2.4: índices libres de la plantilla ----------------------------------------------------


def test_ca_d3_2_4_con_hostpci0_en_la_plantilla_un_pci_nuevo_va_a_hostpci1_en_un_put_de_ajustes():
    m = MundoD(extra={"hostpci0": "mapping=ya-usado"})
    r = m.crear(_cfg(m, pci("gpu-a2")))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r.error
    (put,) = _puts_hw(m)
    assert put["hostpci1"] == "mapping=gpu-a2" and "hostpci0" not in put
    assert "hostpci1" not in m.cl.cuerpos_clon[100] and not any(
        k.startswith(("hostpci", "usb")) for k in m.cl.cuerpos_clon[100]
    )
    assert m.cl.vms[100]["config"]["hostpci0"] == "mapping=ya-usado"  # la de la plantilla sigue


def test_ca_d3_2_4_el_clon_sin_hostpci_en_la_plantilla_empieza_en_hostpci0_y_usb0():
    m = MundoD()
    m.crear(_cfg(m, pci("a"), pci("b"), usb("u")))
    (put,) = _puts_hw(m)
    assert {k: v for k, v in put.items() if k.startswith(("hostpci", "usb"))} == {
        "hostpci0": "mapping=a",
        "hostpci1": "mapping=b",
        "usb0": "mapping=u",
    }


def test_ca_d3_2_4_los_indices_ocupados_no_contiguos_se_saltan():
    m = MundoD(extra={"hostpci0": "mapping=x", "hostpci2": "mapping=y", "usb1": "mapping=z"})
    m.crear(_cfg(m, pci("a"), pci("b"), usb("u")))
    (put,) = _puts_hw(m)
    assert put["hostpci1"] == "mapping=a" and put["hostpci3"] == "mapping=b"
    assert put["usb0"] == "mapping=u"


def test_el_paso_hardware_va_tras_los_ajustes_de_cpu_y_memoria_y_antes_de_la_red():
    assert AJUSTE_HARDWARE == "hardware"
    i = ORDEN_AJUSTES.index
    assert i("cpu_memoria") < i("hardware") < i("red")


def test_el_put_de_hardware_va_aparte_del_de_cpu_memoria():
    m = MundoD()
    cfg = dataclasses.replace(
        _cfg(m, pci("g")), detalle_origen=dataclasses.replace(
            _base(m).detalle_origen, ajustes=AjustesClon(cores=4, memoria_mib=4096)
        )
    )  # fmt: skip
    m.crear(cfg)
    puts = _puts(m)
    ajustes = [d for d in puts if "cores" in d]
    assert len(ajustes) == 1 and not any(k.startswith("hostpci") for k in ajustes[0])
    assert len(_puts_hw(m)) == 1
    assert puts.index(ajustes[0]) < puts.index(_puts_hw(m)[0])


def test_el_clon_sin_hardware_no_escribe_nunca_hostpci_ni_usb_ni_machine_ni_vga():
    m = MundoD()
    m.crear(_base(m, ajustes=AjustesClon(cores=4)))
    assert all(
        not (set(d) & {"machine", "vga"}) and not any(k.startswith(("hostpci", "usb")) for k in d)
        for d in _puts(m)
    )


@pytest.mark.parametrize(
    ("maquina", "añade_q35"),
    [(None, True), ("pc-i440fx-9.0", True), ("q35", False), ("pc-q35-9.0", False)],
)
def test_ca_d3_4_1_pcie_en_un_clon_añade_machine_q35_solo_si_la_plantilla_no_lo_es(
    maquina, añade_q35
):
    extra = {"machine": maquina} if maquina else {}
    m = MundoD(extra=extra)
    m.crear(_cfg(m, pci("g", pcie=True)))
    (put,) = _puts_hw(m)
    assert put["hostpci0"] == "mapping=g,pcie=1"
    assert ("machine" in put and put["machine"] == "q35") is añade_q35


def test_ca_d3_4_2_x_vga_en_un_clon_añade_vga_none():
    m = MundoD()
    m.crear(_cfg(m, pci("g", pcie=True, x_vga=True)))
    (put,) = _puts_hw(m)
    assert put["vga"] == "none" and put["machine"] == "q35"


def test_parametros_hardware_clon_directo_usa_los_indices_de_la_plantilla():
    det = detalle_de_config({"hostpci0": "mapping=x", "usb0": "mapping=y", "machine": "q35"})
    assert det.hostpci == (0,) and det.usb == (0,) and det.mapeos == ("x", "y")
    cfg = dataclasses.replace(cfg_clon("base"), hardware_cluster=hw(pci("a", pcie=True), usb("u")))
    assert parametros_hardware_clon(cfg, det) == {
        "hostpci1": "mapping=a,pcie=1",
        "usb1": "mapping=u",
    }
    assert parametros_hardware_clon(cfg_clon("base"), det) == {}


# --- CA-D3.5: inspección de la plantilla ----------------------------------------------------------


def _problemas(extra: dict[str, Any]):
    m = MundoD(extra=extra)
    _, problemas = resolver_origen(cfg_clon("base"), m.inv, "pve1")
    return m, problemas


def test_ca_d3_5_1_una_plantilla_con_hostpci_sin_mapeo_da_v_d58_error_y_no_escribe_nada():
    m = MundoD(extra={"hostpci0": "0000:01:00.0"})
    plan = plan_de(m.banco, def_lote(2, plantilla_vm=cfg_clon("base")))
    assert (
        plan.bloqueado and plan.elementos == () or any(p.regla == "V-D58" for p in plan.problemas)
    )
    (v_d58,) = [p for p in plan.problemas if p.regla == "V-D58"]
    assert v_d58.severidad.value == "error" and v_d58.params["plantilla"] == "base"
    assert m.cl.total("POST") == 0 and m.cl.total("PUT") == 0
    assert m.cl.clones == {}


@pytest.mark.parametrize(
    "extra",
    [
        {"hostpci0": "0000:01:00.0,pcie=1"},
        {"usb0": "host=1234:5678"},
        {"usb1": "host=1234:5678,usb3=1"},
        {"virtiofs0": "dirid=datos"},
        {"rng0": "source=/dev/hwrng"},
        {"hostpci0": "mapping=ok", "usb0": "host=1234:5678"},  # mezcla: basta uno sin mapear
    ],
    ids=["pci_bdf", "usb_host", "usb_host3", "virtiofs", "rng_hwrng", "mezcla"],
)
def test_ca_d3_5_1_cl_d22_cualquier_dispositivo_sin_mapear_o_pasarela_directa_da_v_d58(extra):
    _, problemas = _problemas(extra)
    assert "V-D58" in [p.codigo for p in problemas]
    assert all(p.severidad.value == "error" for p in problemas if p.codigo == "V-D58")


@pytest.mark.parametrize(
    "extra",
    [
        {"rng0": "source=/dev/urandom"},
        {"usb0": "host=spice"},
        {"vga": "std"},
        {},
    ],
    ids=["rng_urandom", "usb_spice", "sin_hardware", "vacia"],
)
def test_ca_d3_5_3_lo_que_no_es_hardware_fisico_no_da_v_d58_ni_aviso(extra):
    _, problemas = _problemas(extra)
    assert not [p for p in problemas if p.codigo.startswith("V-D58")]


def test_ca_d3_5_2_una_plantilla_con_mapeos_da_v_d58b_aviso_y_se_permite():
    m = MundoD(extra={"hostpci0": "mapping=gpu-a2", "usb0": "mapping=llave"})
    _, problemas = resolver_origen(cfg_clon("base"), m.inv, "pve1")
    (p,) = [x for x in problemas if x.codigo == "V-D58b"]
    assert p.severidad.value == "aviso" and p.params["plantilla"] == "base"
    assert p.params["lista"] == "gpu-a2, llave"
    assert "V-D58" not in [x.codigo for x in problemas]
    r = m.crear(_base(m))  # se permite clonar (el clon hereda los mismos mapeos)
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r.error
    assert m.cl.vms[100]["config"]["hostpci0"] == "mapping=gpu-a2"


def test_ca_d3_5_2_en_un_lote_el_aviso_v_d58b_sale_una_vez_por_plantilla_y_no_por_mv():
    m = MundoD(extra={"hostpci0": "mapping=gpu-a2"})
    plan = plan_de(m.banco, def_lote(30, plantilla_vm=cfg_clon("base")))
    assert not plan.bloqueado
    avisos = [p for p in plan.problemas if p.regla == "V-D58b"]
    assert len(avisos) == 1 and avisos[0].params["plantilla"] == "base"  # CA-D11.2


def test_ca_d11_2_cien_mvs_con_dispositivo_sin_mapear_dan_un_solo_v_d58_agrupado():
    m = MundoD(extra={"hostpci0": "0000:01:00.0"})
    plan = plan_de(m.banco, def_lote(100, plantilla_vm=cfg_clon("base")))
    assert plan.bloqueado
    assert len([p for p in plan.problemas if p.regla == "V-D58"]) == 1


def test_ca_d3_5_3_sin_hardware_en_la_plantilla_no_hay_avisos_ni_lecturas_nuevas():
    m = MundoD()
    plan = plan_de(m.banco, def_lote(3, plantilla_vm=cfg_clon("base")))
    assert not plan.bloqueado
    assert not [p for p in plan.problemas if p.regla.startswith("V-D5")]
    assert m.cl.lecturas_d(r"/cluster/mapping") == [] and m.cl.lecturas_d(r"capabilities") == []


def test_ca_d3_5_3_la_inspeccion_no_añade_lecturas_por_mv_de_la_config_de_la_plantilla():
    """H12: se usa la config que ya se lee para la red del clon; no hay GET extra por MV."""
    sin = MundoD()
    plan_de(sin.banco, def_lote(10, plantilla_vm=cfg_clon("base")))
    con = MundoD(extra={"hostpci0": "mapping=g"})
    plan_de(con.banco, def_lote(10, plantilla_vm=cfg_clon("base")))
    n = lambda m: len(m.cl.llamadas_a("GET", r"/qemu/9000/config$"))  # noqa: E731
    assert n(con) == n(sin)


def test_ca_d3_5_clonar_una_plantilla_con_mapeos_en_aarch64_no_la_adapta_ni_pierde_los_mapeos():
    from .apoyo_fase_d import ARM

    m = MundoD(
        nodos=("pve1",), arqs={"pve1": ARM}, extra={"hostpci0": "mapping=g", "arch": "aarch64"}
    )
    plan = plan_de(m.banco, def_lote(1, plantilla_vm=cfg_clon("base")))
    assert not plan.bloqueado
    assert [p.regla for p in plan.problemas if p.regla in ("V-D07", "V-D08", "V-D58")] == []


# --- Orden por MV con el paso hardware (CA-D0.7.1 en el servicio) ---------------------------------


def _orden(m: MundoD) -> list[str]:
    sal = []
    for c in m.cl.llamadas:
        if c.metodo == "POST" and c.ruta.endswith("/clone"):
            sal.append("clone")
        elif c.metodo == "PUT" and c.ruta.endswith("/config"):
            d = c.datos or {}
            if any(k.startswith(("hostpci", "usb")) for k in d):
                sal.append("hardware")
            elif any(k.startswith("net") for k in d):
                sal.append("red")
            else:
                sal.append("ajustes")
        elif c.ruta.endswith("/status/start"):
            sal.append("start")
        elif c.metodo == "PUT" and c.ruta.endswith("/resize"):
            sal.append("resize")
    return sal


def test_el_orden_del_clon_es_clone_ajustes_hardware_resize_y_start():
    m = MundoD()
    cfg = _cfg(
        m,
        pci("g"),
        encender=True,
        ajustes=AjustesClon(cores=4, memoria_mib=4096, disco_gib=64),
    )
    r = m.crear(cfg)
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r.error
    assert _orden(m) == ["clone", "ajustes", "hardware", "resize", "start"]


def test_la_version_8_4_no_cambia_el_paso_hardware():
    m = MundoD(version=V_84)
    m.crear(_cfg(m, pci("g")))
    assert _orden(m)[-1] == "hardware" and _orden(m)[0] == "clone"
