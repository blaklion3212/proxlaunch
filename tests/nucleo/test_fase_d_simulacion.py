"""D0.1.3 y D0.6 (0.9.0): simulación y escrituras de la fase D.

CA-D0.1.2 (informe sin D), CA-D0.1.3, CA-D0.6.1 y RF-D2.12 (anuncios del informe y la simulación).
La simulación muestra por MV los parámetros nuevos de la petición (``hostpciN``/``usbN``,
``machine``, el perfil ARM) sin ninguna escritura real; ninguna ejecución completa escribe en
``/cluster/mapping/*``, ``/cluster/*``, ``/nodes/*/capabilities/*`` ni ``/access/*``.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

import proxlaunch
from proxlaunch.nucleo.lote.informe import MetadatosInforme, anuncios_de_informe, construir_informe
from proxlaunch.nucleo.lote.modelos import AccionPeticion, EstadoMV
from proxlaunch.nucleo.lote.simulacion import anuncios_de_simulacion, simular
from proxlaunch.nucleo.modelos.vm import Disco
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH

from .apoyo_fase_a import def_lote, plan_de
from .apoyo_fase_b_p1 import PRIVS_B_92
from .apoyo_fase_d import (
    ARM,
    V_84,
    V_92,
    X86,
    MundoD,
    banco_d,
    cfg_arm,
    hw,
    pci,
    permisos_mapeo,
    usb,
)
from .apoyo_lote import mapeo_api, modelo_cpu_api
from .apoyo_mvp4 import cfg_clon

RAIZ_SRC = Path(proxlaunch.__file__).parent


def _banco(arqs=None, version=V_92, nodos=("pve1",)):
    banco = banco_d(
        arqs if arqs is not None else dict.fromkeys(nodos, X86),
        nodos=nodos,
        version=version,
        permisos_efectivos=permisos_mapeo("/mapping", base=(*ROL_PROXLAUNCH, "VM.PowerMgmt")),
    )
    banco.cluster.mapeos_api["pci"] = [
        mapeo_api("gpu-a2", *[(n, f"/dev/{n}/{i}") for n in nodos for i in range(8)], migrable=True)
    ]
    banco.cluster.mapeos_api["usb"] = [mapeo_api("llave", *[(n, "/u") for n in nodos])]
    banco.cluster.cpus_api.update(
        {n: [modelo_cpu_api("custom-gamer", custom=True), modelo_cpu_api("host")] for n in nodos}
    )
    return banco


def _cfg(*dispositivos, **kw):
    return dataclasses.replace(
        cfg_arm(discos=[Disco("local-lvm", 8)], **kw), hardware_cluster=hw(*dispositivos) or None
    )


# --- CA-D0.1.3: la simulación muestra los parámetros nuevos sin escribir --------------------------


@pytest.mark.parametrize("version", [V_84, V_92], ids=["8.4", "9.2"])
def test_ca_d0_1_3_cada_mv_lista_hostpci_y_usb_y_no_se_emite_ninguna_escritura(version):
    banco = _banco(version=version)
    cfg = _cfg(pci("gpu-a2", pcie=True), usb("llave", usb3=True))
    res = simular(banco.sesion, def_lote(3, plantilla_vm=cfg), banco.inv, reloj=banco.reloj)
    assert not res.plan.bloqueado, [(p.regla, p.params) for p in res.plan.problemas]
    assert banco.cluster.solo_lecturas  # ninguna escritura real
    assert set(res.peticiones) == {100, 101, 102}
    for vmid, params in res.peticiones.items():
        assert params["hostpci0"] == "mapping=gpu-a2,pcie=1", vmid
        assert params["usb0"] == "mapping=llave,usb3=1" and params["machine"] == "q35"


def test_ca_d0_1_3_la_simulacion_de_un_clon_muestra_el_put_de_hardware_como_configurar():
    m = MundoD(privilegios=(*PRIVS_B_92, "Mapping.Use", "Mapping.Audit"))
    m.cl.mapeos_api["pci"] = [mapeo_api("gpu-a2", ("pve1", "/x"), ("pve1", "/y"), migrable=True)]
    base = dataclasses.replace(
        cfg_clon("base"), hardware_cluster=hw(pci("gpu-a2", pcie=True)), discos=_cfg().discos
    )
    res = simular(m.banco.sesion, def_lote(2, plantilla_vm=base), m.inv, reloj=m.banco.reloj)
    assert not res.plan.bloqueado, [(p.regla, p.params) for p in res.plan.problemas]
    assert m.cl.solo_lecturas
    for vmid, detalles in res.peticiones_detalle.items():
        acciones = [d.accion for d in detalles]
        assert AccionPeticion.CLONAR in acciones
        con_hw = [d for d in detalles if any(k.startswith("hostpci") for k in d.parametros)]
        assert len(con_hw) == 1 and con_hw[0].accion == AccionPeticion.CONFIGURAR, vmid
        assert con_hw[0].parametros["hostpci0"] == "mapping=gpu-a2,pcie=1"
        assert con_hw[0].parametros["machine"] == "q35"
        clon = next(d for d in detalles if d.accion == AccionPeticion.CLONAR)
        assert not any(k.startswith(("hostpci", "usb")) for k in clon.parametros)


def test_ca_d0_1_3_la_simulacion_en_arm_muestra_el_perfil_adaptado_y_anuncia_lo_adaptado():
    banco = _banco({"pve1": ARM})
    cfg = _cfg(pci("gpu-a2"))
    cfg = dataclasses.replace(cfg, tipo_cpu="x86-64-v3")
    res = simular(banco.sesion, def_lote(2, plantilla_vm=cfg), banco.inv, reloj=banco.reloj)
    assert not res.plan.bloqueado
    for params in res.peticiones.values():
        assert params["bios"] == "ovmf" and params["cpu"] == "host" and params["vga"] == "virtio"
        assert "machine" not in params and params["hostpci0"] == "mapping=gpu-a2"
    anuncios = anuncios_de_simulacion(res)
    assert anuncios.experimental and anuncios.nodos_arm == ("pve1",)
    assert len(anuncios.adaptaciones) == 2  # un V-D08 por MV
    assert anuncios.hardware == ((100, ("pci:gpu-a2",)), (101, ("pci:gpu-a2",)))
    assert banco.cluster.solo_lecturas


def test_ca_d0_1_2_un_lote_x86_sin_opciones_de_d_no_anuncia_nada_nuevo():
    banco = _banco()
    res = simular(banco.sesion, def_lote(2, plantilla_vm=_cfg()), banco.inv, reloj=banco.reloj)
    a = anuncios_de_simulacion(res)
    assert not a.hay and not a.experimental
    assert a.nodos_arm == () and a.adaptaciones == () and a.hardware == ()
    assert not any("hostpci" in k or k == "machine" for p in res.peticiones.values() for k in p)


def test_rf_d2_12_un_lote_en_nodos_x86_no_marca_experimental_ni_siquiera_con_hardware():
    banco = _banco()
    res = simular(
        banco.sesion, def_lote(2, plantilla_vm=_cfg(pci("gpu-a2"))), banco.inv, reloj=banco.reloj
    )
    assert not anuncios_de_simulacion(res).experimental
    assert anuncios_de_simulacion(res).hardware


def test_ca_d0_1_3_la_simulacion_con_mapeos_lee_pero_nunca_escribe_en_mapping():
    banco = _banco()
    simular(
        banco.sesion, def_lote(4, plantilla_vm=_cfg(pci("gpu-a2"))), banco.inv, reloj=banco.reloj
    )
    assert all(c.metodo == "GET" for c in banco.cluster.llamadas)
    assert banco.cluster.lecturas_d(r"/cluster/mapping")  # sí lee los mapeos


# --- Informe: anuncios de la fase D ---------------------------------------------------------------


def test_los_anuncios_del_informe_salen_del_plan_y_del_libro_de_una_ejecucion_arm():
    banco = _banco({"pve1": ARM})
    plan = plan_de(banco, def_lote(2, plantilla_vm=_cfg(usb("llave"))))
    libro = banco.ejecutar(plan)
    meta = MetadatosInforme("lab", "9.2.1", False, None, "2026-11-23T10:00:00+00:00")
    informe = construir_informe(plan, libro, meta, reloj=banco.reloj)
    a = anuncios_de_informe(informe)
    assert a.experimental and a.nodos_arm == ("pve1",)
    assert [v for v, _ in a.hardware] == [100, 101]
    assert {e.estado for e in libro.instantanea()} <= {EstadoMV.OK, EstadoMV.CON_AVISOS}


def test_ca_d0_1_2_el_informe_de_un_lote_x86_sin_d_no_tiene_anuncios():
    banco = _banco()
    plan = plan_de(banco, def_lote(2, plantilla_vm=_cfg()))
    libro = banco.ejecutar(plan)
    meta = MetadatosInforme("lab", "9.2.1", False, None, "2026-11-23T10:00:00+00:00")
    assert not anuncios_de_informe(construir_informe(plan, libro, meta, reloj=banco.reloj)).hay


# --- CA-D0.6.1: nunca se escribe fuera de la MV ---------------------------------------------------

PROHIBIDAS = re.compile(
    r"^/(cluster/(mapping|config|options|firewall|sdn)|access|nodes/[^/]+/capabilities|"
    r"nodes/[^/]+/(network|sdn|apt|services))"
)
PERMITIDAS = re.compile(
    r"^/nodes/[^/]+/(qemu(/\d+(/(config|resize|clone|status/(start|stop)))?)?|storage/)"
)


def _escrituras(banco) -> list[tuple[str, str]]:
    return [(c.metodo, c.ruta) for c in banco.cluster.llamadas if c.metodo != "GET"]


def _comprobar(escrituras) -> None:
    assert escrituras, "la prueba no ejecutó ninguna escritura"
    for metodo, ruta in escrituras:
        assert not PROHIBIDAS.match(ruta), (metodo, ruta)
        assert PERMITIDAS.match(ruta), (metodo, ruta)


def test_ca_d0_6_1_un_lote_completo_con_mapeos_cpu_custom_y_encendido_solo_escribe_en_las_mv():
    banco = _banco()
    cfg = _cfg(
        pci("gpu-a2", pcie=True, x_vga=True), usb("llave"), tipo_cpu="custom-gamer", encender=True
    )
    plan = plan_de(banco, def_lote(3, plantilla_vm=cfg))
    assert not plan.bloqueado, [(p.regla, p.params) for p in plan.problemas]
    banco.ejecutar(plan)
    _comprobar(_escrituras(banco))


def test_ca_d0_6_1_un_lote_arm_completo_solo_escribe_en_las_mv():
    banco = _banco({"pve1": ARM})
    plan = plan_de(banco, def_lote(2, plantilla_vm=_cfg(pci("gpu-a2"), encender=True)))
    banco.ejecutar(plan)
    _comprobar(_escrituras(banco))


def test_ca_d0_6_1_un_lote_de_clones_con_mapeos_solo_escribe_en_las_mv_y_hace_el_put_de_hardware():
    m = MundoD(privilegios=(*PRIVS_B_92, "Mapping.Use", "Mapping.Audit"))
    m.cl.mapeos_api["pci"] = [mapeo_api("gpu-a2", *[("pve1", f"/{i}") for i in range(4)])]
    base = dataclasses.replace(cfg_clon("base"), hardware_cluster=hw(pci("gpu-a2")), encender=True)
    plan = plan_de(m.banco, def_lote(3, plantilla_vm=base))
    assert not plan.bloqueado
    m.ejecutar(plan)
    escrituras = [(c.metodo, c.ruta) for c in m.cl.llamadas if c.metodo != "GET"]
    _comprobar(escrituras)
    assert sum(1 for c in m.cl.llamadas if c.metodo == "PUT" and "hostpci0" in (c.datos or {})) == 3


def test_ca_d0_6_1_el_cliente_no_ofrece_ninguna_escritura_sobre_mapeos_ni_capacidades():
    """Estático: ningún método del cliente escribe en ``/cluster/mapping`` ni en capacidades."""
    fuente = (RAIZ_SRC / "nucleo" / "api" / "cliente.py").read_text(encoding="utf-8")
    patron = re.compile(
        r'_llamar\(\s*"(PUT|POST|DELETE)"\s*,\s*f?"[^"]*(mapping|capabilities|/access/)'
    )
    assert patron.findall(fuente) == []


def test_ca_d0_6_1_ningun_modulo_de_src_escribe_en_el_cluster_ni_en_acceso():
    patron = re.compile(r'"(PUT|POST|DELETE)"[^\n]*"/(cluster|access)')
    hallazgos = [
        f"{r.relative_to(RAIZ_SRC)}:{n}"
        for r in RAIZ_SRC.rglob("*.py")
        for n, linea in enumerate(r.read_text(encoding="utf-8").splitlines(), 1)
        if patron.search(linea)
    ]
    # Las escrituras históricas al clúster (firewall de la MV vive en /nodes/…/firewall; los grupos
    # de seguridad del clúster solo se LEEN) no deben existir.
    assert hallazgos == [], hallazgos
