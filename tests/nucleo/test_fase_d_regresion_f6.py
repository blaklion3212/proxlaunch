"""Regresión de los hallazgos corregidos de la revisión F6 de la fase D (0.9.0), parte del núcleo.

Cada prueba parte del escenario del hallazgo (entrada -> resultado esperado) y usa solo la interfaz
pública. El identificador del hallazgo (QA-n, Seg-Bn) va en el nombre. La parte de interfaz
(QA-2, QA-8, QA-10 y Seg-B1) está en ``tests/interfaz/test_fase_d_regresion_f6.py``.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import pyexpat
import xml.etree.ElementTree as ET
from typing import Any

import pytest

from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.archivos.esquema import ErrorArchivo, MotivoCampo
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.constructor_peticion import construir_parametros, valor_red
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.errores import tipo_cpu_efectivo, traducir_error_hardware
from proxlaunch.nucleo.hardware_cluster.lectura import leer_info_hardware
from proxlaunch.nucleo.hardware_cluster.modelos import (
    MAX_INDICE_USB,
    ComprobacionNodo,
    TipoMapeo,
)
from proxlaunch.nucleo.hardware_cluster.validacion import (
    validar_hardware_local,
    validar_hardware_servidor,
)
from proxlaunch.nucleo.libvirt import lectura_xml
from proxlaunch.nucleo.libvirt.lectura_xml import ErrorXml, leer_xml
from proxlaunch.nucleo.lote.modelos import AccionPeticion, FilaLote
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.lotes_guardados.formato import (
    leer_lote,
    lote_a_bytes,
    version_para,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    ImagenDisco,
    RefVolumen,
)
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed
from proxlaunch.nucleo.origen.clon import detalle_de_config, parametros_hardware_clon
from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo, resolver_origen
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.servicios.creacion import AJUSTE_HARDWARE
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_api import TransporteFalso
from .apoyo_fase_a import def_lote
from .apoyo_fase_b_p1 import PRIVS_B_92
from .apoyo_fase_d import (
    V_92,
    MundoD,
    banco_d,
    caps_de,
    cfg_arm,
    hw,
    info_hw,
    mapeo,
    pci,
    permisos_mapeo,
    usb,
)
from .apoyo_fase_d_libvirt import (
    disco_xml,
    dominio_desde_texto,
    inventario_d,
    proponer_de,
    xml_minimo,
)
from .apoyo_lote import error_http, mapeo_api, modelo_cpu_api
from .apoyo_mvp3 import definicion_filas
from .apoyo_mvp4 import cfg_clon, cfg_import

MAC = "52:54:00:ab:cd:ef"
PRIVS = (*PRIVS_B_92, "Mapping.Use", "Mapping.Audit")


# --- QA-1: clon cuya plantilla ya trae hostpci0 -------------------------------------------------


def _clon(m: MundoD, *dispositivos: Any, **kw: Any) -> ConfiguracionVM:
    """Clon de la plantilla «base» con los dispositivos pedidos (ya resuelto)."""
    kw.setdefault("etiquetas", ("proxlaunch", "lote-ab12cd34"))
    base = dataclasses.replace(cfg_clon("base", **kw), hardware_cluster=hw(*dispositivos))
    cfg, problemas = resolver_origen(base, m.inv, m.nodos[0])
    assert not [p for p in problemas if p.severidad.value == "error"], problemas
    return cfg


def _puts_hw(m: MundoD, vmid: int = 100) -> list[dict[str, str]]:
    return [
        d
        for _n, v, q, d in m.cl.puts
        if v == vmid and q == "config" and any(k.startswith(("hostpci", "usb")) for k in d)
    ]


def _mundo_gpu(**kw: Any) -> MundoD:
    """Plantilla con ``hostpci0=mapping=gpu`` y el mapeo ``gpu`` (y ``gpu2``) en el clúster."""
    kw.setdefault("extra", {"hostpci0": "mapping=gpu"})
    m = MundoD(privilegios=PRIVS, **kw)
    m.cl.mapeos_api["pci"] = [
        mapeo_api("gpu", ("pve1", "/dev/0"), ("pve1", "/dev/1"), migrable=True),
        mapeo_api("gpu2", ("pve1", "/dev/2"), migrable=True),
    ]
    return m


def test_qa1_plantilla_con_hostpci0_y_gpu_pcie_xvga_envia_hostpci1_machine_y_vga():
    m = _mundo_gpu()
    r = m.crear(_clon(m, pci("gpu", pcie=True, x_vga=True)))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r.error
    (put,) = _puts_hw(m)
    assert put == {"hostpci1": "mapping=gpu,pcie=1,x-vga=1", "machine": "q35", "vga": "none"}
    assert m.cl.vms[100]["config"]["hostpci0"] == "mapping=gpu"  # la de la plantilla sigue


def test_qa1_la_simulacion_muestra_exactamente_el_put_de_hardware_que_se_ejecuta():
    m = _mundo_gpu()
    base = dataclasses.replace(
        cfg_clon("base"), hardware_cluster=hw(pci("gpu", pcie=True, x_vga=True))
    )
    sim = simular(m.banco.sesion, def_lote(1, plantilla_vm=base), m.inv, reloj=m.banco.reloj)
    assert not sim.plan.bloqueado, [(p.regla, p.params) for p in sim.plan.problemas]
    (simulado,) = [
        d.parametros
        for d in sim.peticiones_detalle[100]
        if d.accion == AccionPeticion.CONFIGURAR and "hostpci1" in d.parametros
    ]
    assert m.cl.solo_lecturas  # la simulación no escribe
    plan = m.planificar(m.definicion(1, hardware_cluster=hw(pci("gpu", pcie=True, x_vga=True))))
    m.ejecutar(plan)
    (ejecutado,) = _puts_hw(m)
    assert dict(simulado) == ejecutado == {
        "hostpci1": "mapping=gpu,pcie=1,x-vga=1", "machine": "q35", "vga": "none",
    }  # fmt: skip


def test_qa1_reintentar_tras_aplicar_no_reenvia_lo_que_ya_esta_en_su_indice():
    m = _mundo_gpu()
    cfg = _clon(m, pci("gpu", pcie=True, x_vga=True))
    m.crear(cfg)
    antes = len(m.cl.llamadas)
    r = m.reintentar(cfg, pendientes=frozenset({AJUSTE_HARDWARE}))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r.error
    escrituras = [c for c in m.cl.llamadas[antes:] if c.metodo != "GET"]
    assert escrituras == []  # ni hostpci1 ni machine ni vga
    assert m.cl.vms[100]["config"]["hostpci1"] == "mapping=gpu,pcie=1,x-vga=1"


def test_qa1_si_solo_se_aplico_parte_el_reintento_envia_el_resto():
    m = _mundo_gpu()
    cfg = _clon(m, pci("gpu"), pci("gpu2"))
    m.crear(cfg)
    config = m.cl.vms[100]["config"]
    assert config["hostpci1"] == "mapping=gpu" and config["hostpci2"] == "mapping=gpu2"
    del config["hostpci2"]  # el servidor solo llegó a aplicar el primero
    antes = len(m.cl.llamadas)
    m.reintentar(cfg, pendientes=frozenset({AJUSTE_HARDWARE}))
    puts = [c.datos for c in m.cl.llamadas[antes:] if c.metodo == "PUT"]
    assert puts == [{"hostpci2": "mapping=gpu2"}]
    assert config["hostpci2"] == "mapping=gpu2"


def _sin_plantilla_en_catalogo(m: MundoD) -> None:
    m.inv.catalogo = dataclasses.replace(m.inv.catalogo, plantillas=())


def test_qa1_respaldo_sin_plantilla_en_el_catalogo_omite_lo_que_ya_consta_por_valor():
    m = _mundo_gpu()
    cfg = _clon(m, pci("gpu", pcie=True))
    m.crear(cfg)
    _sin_plantilla_en_catalogo(m)
    antes = len(m.cl.llamadas)
    m.reintentar(cfg, pendientes=frozenset({AJUSTE_HARDWARE}))
    assert [c for c in m.cl.llamadas[antes:] if c.metodo == "PUT"] == []


def test_qa1_respaldo_sin_plantilla_envia_en_el_primer_indice_libre_lo_que_no_consta():
    m = _mundo_gpu()
    cfg = _clon(m, pci("gpu2"))
    m.crear(cfg)
    config = m.cl.vms[100]["config"]
    del config["hostpci1"]  # no llegó a aplicarse: el reintento debe volver a escribirlo
    _sin_plantilla_en_catalogo(m)
    antes = len(m.cl.llamadas)
    m.reintentar(cfg, pendientes=frozenset({AJUSTE_HARDWARE}))
    puts = [c.datos for c in m.cl.llamadas[antes:] if c.metodo == "PUT"]
    assert puts == [{"hostpci1": "mapping=gpu2"}]


def test_qa1_limite_documentado_del_respaldo_un_mapeo_igual_al_de_la_plantilla_se_da_por_aplicado():
    """Sin plantilla en el catálogo no se sabe qué índice era de la plantilla: se compara por
    valor. Si el usuario pide el mismo mapeo que la plantilla ya traía y el primer intento no
    llegó a aplicarse, el reintento lo considera ya escrito (límite conocido del respaldo)."""
    m = _mundo_gpu()
    cfg = _clon(m, pci("gpu"))
    m.crear(cfg)
    # Estado del clon tras un primer intento fallido: solo trae lo heredado de la plantilla.
    del m.cl.vms[100]["config"]["hostpci1"]
    _sin_plantilla_en_catalogo(m)
    antes = len(m.cl.llamadas)
    m.reintentar(cfg, pendientes=frozenset({AJUSTE_HARDWARE}))
    assert [c for c in m.cl.llamadas[antes:] if c.metodo == "PUT"] == []


# --- QA-3: CPU personalizada de un clon ---------------------------------------------------------


def _clon_con_cpu(ajuste: str | None, residual: str | None = None) -> ConfiguracionVM:
    cfg = cfg_clon("base", ajustes=AjustesClon(tipo_cpu=ajuste))
    return dataclasses.replace(cfg, tipo_cpu=residual) if residual is not None else cfg


def _por_nodo(**cfgs: ConfiguracionVM) -> dict[str, list[ConfiguracionVM]]:
    return {n: [c] for n, c in cfgs.items()}


def test_qa3_el_tipo_de_cpu_efectivo_de_un_clon_es_el_de_sus_ajustes_y_no_el_residual():
    assert tipo_cpu_efectivo(_clon_con_cpu("custom-a", residual="host")) == "custom-a"
    assert tipo_cpu_efectivo(_clon_con_cpu(None, residual="custom-zzz")) is None
    assert tipo_cpu_efectivo(cfg_arm(tipo_cpu="custom-b")) == "custom-b"  # sin clon, el de la MV


def test_qa3_un_clon_con_custom_en_los_ajustes_que_falta_en_el_nodo_da_v_d61():
    info = info_hw(cpus={"pve1": ["custom-a"], "pve2": ["kvm64"]})
    r = validar_hardware_servidor(
        _por_nodo(pve1=_clon_con_cpu("custom-a"), pve2=_clon_con_cpu("custom-a")), info, None
    )
    (p,) = [x for x in r if x.codigo == "V-D61"]
    assert p.severidad == Severidad.ERROR and p.params == {"cpu": "custom-a", "nodos": "pve2"}


def test_qa3_un_tipo_cpu_residual_en_un_clon_sin_ajuste_de_cpu_no_da_v_d61_ni_v_d62():
    info = info_hw(cpus={"pve1": ["kvm64"]})
    r = validar_hardware_servidor(
        _por_nodo(pve1=_clon_con_cpu(None, residual="custom-zzz"), pve2=cfg_arm()), info, None
    )
    assert [x.codigo for x in r if x.codigo in ("V-D61", "V-D62")] == []


def test_qa3_el_plan_de_un_clon_con_custom_ausente_en_el_nodo_se_bloquea_con_v_d61():
    m = MundoD(privilegios=PRIVS)
    m.cl.cpus_api["pve1"] = [modelo_cpu_api("kvm64")]
    base = cfg_clon("base", ajustes=AjustesClon(tipo_cpu="custom-a"))
    plan = m.planificar(def_lote(2, plantilla_vm=base))
    assert plan.bloqueado
    (p,) = [x for x in plan.problemas if x.regla == "V-D61"]
    assert p.params["cpu"] == "custom-a" and p.params["nodos"] == "pve1"


def test_qa3_el_plan_de_un_clon_con_tipo_cpu_residual_no_lee_cpu_ni_da_v_d61_o_v_d62():
    m = MundoD(privilegios=PRIVS)
    plan = m.planificar(m.definicion(2, tipo_cpu="custom-zzz"))
    assert {x.regla for x in plan.problemas} & {"V-D61", "V-D62"} == set()
    assert m.cl.lecturas_d(r"/capabilities/qemu/cpu$") == []


@pytest.mark.parametrize(
    ("ruta", "priv"), [("/nodes", "Sys.Audit"), ("/mapping/cpu/gamer", "Mapping.Use")]
)
def test_qa3_un_403_al_aplicar_el_cpu_custom_de_un_clon_es_cpu_personalizada_rechazada(ruta, priv):
    e = error_http(403, f"Permission check failed ({ruta}, {priv})")
    cfg = _clon_con_cpu("custom-gamer")
    t = traducir_error_hardware(e, cfg)
    assert t.codigo == CodigoError.CPU_PERSONALIZADA_RECHAZADA
    assert t.params["cpu"] == "custom-gamer" and t.params["ruta"] == ruta


def test_qa3_un_403_de_nodes_en_un_clon_sin_cpu_custom_no_se_reinterpreta():
    e = error_http(403, "Permission check failed (/nodes, Sys.Audit)")
    # el residual ``custom-*`` de ``cfg.tipo_cpu`` no cuenta: el clon no pide esa CPU
    assert traducir_error_hardware(e, _clon_con_cpu(None, residual="custom-zzz")) is e


# --- QA-5: nombre de modelo ``custom-`` largo ---------------------------------------------------


def _cliente_cpu(modelos: list[dict[str, Any]]) -> ClienteProxmox:
    t = TransporteFalso().en("GET", "/nodes/pve1/capabilities/qemu/cpu", modelos)
    return ClienteProxmox(
        t, AutenticadorToken(CredencialToken("ana@pve!lab", "s")), RelojSimulado()
    )


@pytest.mark.parametrize("largo", [58, 60, 64])
def test_qa5_un_modelo_custom_con_nombre_de_58_a_64_caracteres_se_lee_como_personalizado(largo):
    nombre = "custom-" + "a" * largo
    modelos = _cliente_cpu([modelo_cpu_api(nombre, custom=True)]).modelos_cpu("pve1")
    assert [(m.nombre, m.personalizado) for m in modelos] == [(nombre, True)]


def test_qa5_un_modelo_custom_largo_leido_del_servidor_no_da_v_d61_falso():
    nombre = "custom-" + "b" * 64
    modelos = tuple(_cliente_cpu([modelo_cpu_api(nombre, custom=True)]).modelos_cpu("pve1"))
    info = dataclasses.replace(info_hw(), cpus={"pve1": modelos})
    cfg = cfg_arm(tipo_cpu=nombre)
    assert validar_hardware_servidor({"pve1": [cfg]}, info, None) == []


def test_qa5_un_nombre_de_mas_de_64_caracteres_tras_custom_no_es_personalizado():
    nombre = "custom-" + "a" * 65
    modelos = _cliente_cpu([modelo_cpu_api(nombre, custom=True)]).modelos_cpu("pve1")
    assert not [m for m in modelos if m.personalizado]


# --- QA-6: mismo id como mapeo PCI y USB en el mismo nodo ---------------------------------------


def _comp(tipo: TipoMapeo, errores: tuple[str, ...]) -> ComprobacionNodo:
    return ComprobacionNodo("x", "pve1", errores, tipo)


def _cfgs_hw(*dispositivos: Any) -> dict[str, list[ConfiguracionVM]]:
    return {"pve1": [dataclasses.replace(cfg_arm(), hardware_cluster=hw(*dispositivos))]}


def _v_d53(r: list[Any]) -> list[Any]:
    return [p for p in r if p.codigo == "V-D53"]


def test_qa6_el_error_de_check_node_de_un_pci_no_se_aplica_al_usb_con_el_mismo_id():
    info = info_hw(
        mapeo(TipoMapeo.PCI, "x", "pve1"),
        mapeo(TipoMapeo.USB, "x", "pve1"),
        comprobaciones=[_comp(TipoMapeo.PCI, ("fallo en el PCI",))],
    )
    solo_usb = validar_hardware_servidor(_cfgs_hw(usb("x")), info, None)
    assert _v_d53(solo_usb) == []
    solo_pci = validar_hardware_servidor(_cfgs_hw(pci("x")), info, None)
    assert [p.params["mensaje"] for p in _v_d53(solo_pci)] == ["fallo en el PCI"]


def test_qa6_el_error_de_check_node_de_un_usb_no_se_aplica_al_pci_con_el_mismo_id():
    info = info_hw(
        mapeo(TipoMapeo.PCI, "x", "pve1"),
        mapeo(TipoMapeo.USB, "x", "pve1"),
        comprobaciones=[_comp(TipoMapeo.USB, ("fallo en el USB",))],
    )
    assert _v_d53(validar_hardware_servidor(_cfgs_hw(pci("x")), info, None)) == []
    ambos = validar_hardware_servidor(_cfgs_hw(pci("x"), usb("x")), info, None)
    assert [p.params["mensaje"] for p in _v_d53(ambos)] == ["fallo en el USB"]


def test_qa6_la_lectura_pide_check_node_por_tipo_aunque_el_id_se_repita():
    banco = banco_d(nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("x", ("pve1", "/p"))]
    banco.cluster.mapeos_api["usb"] = [mapeo_api("x", ("pve1", "/u"))]
    banco.cluster.check_node_api[("pci", "pve1")] = [
        {"id": "x", "checks": [{"severity": "error", "message": "solo PCI"}]}
    ]
    info = leer_info_hardware(
        banco.sesion.cliente, banco.inv.catalogo.permisos, banco.sesion.capacidades,
        NecesidadesCatalogo(mapeos=frozenset({("pci", "x"), ("usb", "x")})),
        ("pve1",), None, {},
    )  # fmt: skip
    por_tipo = {c.tipo: c.errores for c in info.comprobaciones}
    assert por_tipo == {TipoMapeo.PCI: ("solo PCI",), TipoMapeo.USB: ()}
    r = validar_hardware_servidor(_cfgs_hw(usb("x")), info, None)
    assert _v_d53(r) == []


# --- QA-11: un check-node por tipo y nodo -------------------------------------------------------


def test_qa11_tres_mapeos_pci_en_dos_nodos_hacen_solo_dos_get_de_check_node():
    banco = banco_d(nodos=("pve1", "pve2"), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [
        mapeo_api(i, ("pve1", f"/{i}1"), ("pve2", f"/{i}2")) for i in ("a", "b", "c")
    ]
    info = leer_info_hardware(
        banco.sesion.cliente, banco.inv.catalogo.permisos, banco.sesion.capacidades,
        NecesidadesCatalogo(mapeos=frozenset({("pci", "a"), ("pci", "b"), ("pci", "c")})),
        ("pve1", "pve2"), None, {},
    )  # fmt: skip
    checks = [
        (c.ruta.rsplit("/", 1)[1], c.params["check-node"])
        for c in banco.cluster.llamadas
        if c.params and "check-node" in c.params
    ]
    assert sorted(checks) == [("pci", "pve1"), ("pci", "pve2")]
    assert len(info.comprobaciones) == 6  # cada mapeo recibe su resultado en cada nodo


# --- QA-7: MAC conservada con un origen distinto de «Importar disco» ----------------------------


def _clon_con_mac() -> dict[str, Any]:
    return {"redes": [InterfazRed("vmbr0", mac_conservada=MAC)]}


def test_qa7_clonar_con_tres_copias_y_mac_conservada_no_da_v_d33_ni_v_d32():
    m = MundoD(privilegios=PRIVS)
    plan = m.planificar(m.definicion(3, **_clon_con_mac()))
    reglas = {p.regla for p in plan.problemas}
    assert reglas & {"V-D32", "V-D33", "V-D33b", "V-D34"} == set()
    assert not plan.bloqueado, [(p.regla, p.params) for p in plan.problemas]


def test_qa7_la_mac_de_un_clon_no_sube_el_lote_a_v6():
    lote = LoteGuardado("Clon", MundoD().definicion(3, **_clon_con_mac()))
    assert version_para(lote) <= 5
    assert json.loads(lote_a_bytes(lote, app_version="0.9.0"))["version_formato"] <= 5


def test_qa7_la_mac_residual_de_un_clon_no_se_escribe_en_el_archivo():
    lote = LoteGuardado("Clon", MundoD().definicion(3, **_clon_con_mac()))
    cuerpo = json.loads(lote_a_bytes(lote, app_version="0.9.0"))
    assert "mac_conservada" not in json.dumps(cuerpo)


def test_qa7_la_mac_de_un_clon_no_llega_a_ninguna_escritura_ni_a_la_simulacion():
    m = MundoD(privilegios=PRIVS)
    definicion = m.definicion(3, **_clon_con_mac())
    sim = simular(m.banco.sesion, definicion, m.inv, reloj=m.banco.reloj)
    texto_sim = json.dumps(
        [d.parametros for ds in sim.peticiones_detalle.values() for d in ds], default=str
    )
    plan = m.planificar(definicion)
    m.ejecutar(plan)
    escrito = json.dumps([c.datos for c in m.cl.llamadas if c.metodo != "GET"], default=str)
    for texto in (texto_sim, escrito):
        assert MAC not in texto.lower()


def test_qa7_valor_red_sin_con_mac_ignora_la_mac_conservada():
    r = InterfazRed("vmbr0", mac_conservada=MAC)
    assert valor_red(r, con_mac=False) == "virtio,bridge=vmbr0"
    assert valor_red(r) == "virtio=52:54:00:AB:CD:EF,bridge=vmbr0"


# --- QA-4 y QA-9: imágenes adicionales de un lote ----------------------------------------------


def _importar(otras: tuple[ImagenDisco, ...], n_discos: int = 3) -> ConfiguracionVM:
    cfg = cfg_import(cfg={"discos": [Disco("datos", 8 * (i + 1)) for i in range(n_discos)]})
    return dataclasses.replace(
        cfg, detalle_origen=dataclasses.replace(cfg.detalle_origen, otras=otras)
    )


def _lote_de(cfg: ConfiguracionVM) -> LoteGuardado:
    from .apoyo_lote import definicion, plantilla

    base = plantilla()
    return LoteGuardado("Lote", definicion(2, plantilla_vm=dataclasses.replace(base, **{
        "origen": cfg.origen, "detalle_origen": cfg.detalle_origen,
        "discos": cfg.discos, "redes": cfg.redes,
    })))  # fmt: skip


def test_qa4_un_lote_libvirt_con_imagenes_adicionales_todas_pendientes_se_guarda_en_v6():
    pendientes = (ImagenDisco(1, None, False), ImagenDisco(2, None, False))
    lote = _lote_de(_importar(pendientes))
    assert version_para(lote) == 6
    cuerpo = json.loads(lote_a_bytes(lote, app_version="0.9.0"))
    assert cuerpo["version_formato"] == 6
    imagenes = cuerpo["homogeneo"]["config"]["detalle_origen"]["imagenes"]
    assert [(i["disco"], i["imagen"]) for i in imagenes] == [(1, None), (2, None)]


def test_qa4_al_reabrir_las_imagenes_pendientes_siguen_pendientes_y_dan_v_d27():
    from proxlaunch.nucleo.libvirt.validacion import validar_importacion_d

    pendientes = (ImagenDisco(1, None, False), ImagenDisco(2, None, False))
    leido = leer_lote(lote_a_bytes(_lote_de(_importar(pendientes)), app_version="0.9.0"))
    cfg = leido.lote.definicion.plantilla
    otras = cfg.detalle_origen.otras
    assert [(o.indice, o.imagen, o.crear_vacio) for o in otras] == [
        (1, None, False),
        (2, None, False),
    ]
    v27 = [p for p in validar_importacion_d(cfg) if p.codigo == "V-D27"]
    assert [p.params["disco"] for p in v27] == ["1", "2"]
    assert all(p.severidad == Severidad.ERROR for p in v27)


def _bytes_con_imagen(disco_imagen: int) -> bytes:
    ref = RefVolumen("debian.qcow2", "local:import/debian.qcow2")
    lote = _lote_de(_importar((ImagenDisco(1, ref),), n_discos=3))
    cuerpo = json.loads(lote_a_bytes(lote, app_version="0.9.0"))
    cuerpo["homogeneo"]["config"]["detalle_origen"]["imagenes"][0]["disco"] = disco_imagen
    return json.dumps(cuerpo).encode()


@pytest.mark.parametrize("disco", [3, 4, 16])
def test_qa9_una_imagen_de_un_disco_que_no_existe_hace_el_archivo_no_valido(disco):
    with pytest.raises(ErrorArchivo) as exc:
        leer_lote(_bytes_con_imagen(disco))
    errores = [(e.ruta, e.motivo) for e in exc.value.errores]
    assert any(
        ruta.endswith("detalle_origen.imagenes[0].disco") and motivo == MotivoCampo.RANGO
        for ruta, motivo in errores
    ), errores


def test_qa9_una_imagen_del_ultimo_disco_existente_se_lee_bien():
    leido = leer_lote(_bytes_con_imagen(2))
    assert [o.indice for o in leido.lote.definicion.plantilla.detalle_origen.otras] == [2]


def test_qa3_un_403_al_aplicar_cpu_custom_de_un_clon_deja_parcial_con_cpu_rechazada():
    from .apoyo_fase_b_p1 import fallar_put

    m = MundoD(privilegios=PRIVS)
    fallar_put(m.cl, "cpu", error_http(403, "Permission check failed (/nodes, Sys.Audit)"))
    cfg = _clon(m, ajustes=AjustesClon(tipo_cpu="custom-gamer"))
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.CPU_PERSONALIZADA_RECHAZADA
    assert r.error.params["cpu"] == "custom-gamer"


# --- Seg-B2: validación de la MAC conservada al construir --------------------------------------


@pytest.mark.parametrize("entrada", ["52:54:00:AB:CD:EF", "52:54:00:ab:cd:ef", "52-54-00-ab-cd-ef"])
def test_seg_b2_la_mac_conservada_se_normaliza_a_mayusculas(entrada):
    r = InterfazRed("vmbr0", mac_conservada=entrada)
    assert valor_red(r) == "virtio=52:54:00:AB:CD:EF,bridge=vmbr0"


@pytest.mark.parametrize(
    "mac",
    [
        "01:00:5e:00:00:01",  # multicast (bit I/G)
        "53:54:00:ab:cd:ef",  # multicast por el primer octeto impar
        "52:54:00:ab:cd:ef\n",  # salto de línea al final
        "52:54:00:ab:cd:e\n",
        "52:54:00:ab:cd:ef,bridge=vmbr9",  # intento de colar otra opción
        "",
    ],
)
def test_seg_b2_una_mac_multicast_o_con_caracteres_de_mas_es_parametro_invalido(mac):
    r = InterfazRed("vmbr0", mac_conservada=mac)
    with pytest.raises(ErrorProxLaunch) as e:
        valor_red(r)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO
    cfg = _importar(())
    cfg.redes = [r]
    with pytest.raises(ErrorProxLaunch) as e2:
        construir_parametros(cfg, banco_d().inv)
    assert e2.value.codigo == CodigoError.PARAMETRO_INVALIDO


# --- Seg-B3: tipo de CPU sin validar ------------------------------------------------------------


@pytest.mark.parametrize(
    "cpu", ["host,flags=+x", "host;x=1", "custom-a,flags=+aes", "x86-64-v2-AES\nvga=std", ""]
)
def test_seg_b3_construir_parametros_rechaza_un_tipo_de_cpu_con_opciones_colgadas(cpu):
    inv = banco_d().inv
    with pytest.raises(ErrorProxLaunch) as e:
        construir_parametros(cfg_arm(tipo_cpu=cpu), inv)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO
    assert e.value.params.get("campo") == "tipo_cpu"


def test_seg_b3_un_tipo_de_cpu_valido_pasa_tal_cual():
    assert construir_parametros(cfg_arm(tipo_cpu="host"), banco_d().inv)["cpu"] == "host"


# --- Seg-B4: Expat anterior a 2.6 ---------------------------------------------------------------


def _xml_grande(extra_elementos: int = 0) -> bytes:
    """Dominio de más de 16 KiB (varios bloques con el tamaño de bloque normal)."""
    relleno = "<!-- " + "x" * 40_000 + " -->"
    return (
        xml_minimo().replace("</domain>", relleno + "<a/>" * extra_elementos + "</domain>")
    ).encode()


@pytest.fixture
def alimentaciones(monkeypatch):
    """Cuenta las llamadas a ``feed`` del analizador (no cambia su comportamiento)."""
    llamadas: list[int] = []
    original = ET.XMLPullParser.feed

    def feed(self, datos=b""):
        llamadas.append(len(datos))
        return original(self, datos)

    monkeypatch.setattr(ET.XMLPullParser, "feed", feed)
    return llamadas


def test_seg_b4_con_expat_anterior_a_2_6_el_xml_se_analiza_de_una_vez(monkeypatch, alimentaciones):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", "expat_2.5.0")
    assert leer_xml(_xml_grande()).tag == "domain"
    assert len(alimentaciones) == 1 and alimentaciones[0] > 40_000


def test_seg_b4_con_expat_reciente_se_alimenta_por_bloques(monkeypatch, alimentaciones):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", "expat_2.7.2")
    leer_xml(_xml_grande())
    assert len(alimentaciones) > 1


@pytest.mark.parametrize("version", ["expat_2.5.0", "expat_2.4.9", "expat_2.0.1"])
def test_seg_b4_con_expat_antiguo_sigue_rechazando_doctype_y_entity(monkeypatch, version):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", version)
    for malo in (
        b"<!DOCTYPE domain [<!ENTITY a 'b'>]><domain/>",
        b"<domain><!ENTITY a 'b'></domain>",
        b"<!doctype  domain><domain/>",
    ):
        with pytest.raises(ErrorXml) as e:
            leer_xml(malo)
        assert e.value.motivo == "doctype"


def test_seg_b4_con_expat_antiguo_sigue_aplicando_los_limites(monkeypatch):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", "expat_2.5.0")
    profundo = ("<domain>" + "<a>" * 64 + "</a>" * 64 + "</domain>").encode()
    muchos = ("<domain>" + "<a/>" * lectura_xml.MAX_ELEMENTOS + "</domain>").encode()
    for datos in (profundo, muchos):
        with pytest.raises(ErrorXml) as e:
            leer_xml(datos)
        assert e.value.motivo == "limites"
    with pytest.raises(ErrorXml) as e:
        leer_xml(b"x" * (lectura_xml.MAX_BYTES_XML + 1))
    assert e.value.motivo == "tamano"


def test_seg_b4_con_expat_antiguo_un_xml_mal_formado_sigue_dando_formato(monkeypatch):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", "expat_2.5.0")
    with pytest.raises(ErrorXml) as e:
        leer_xml(b"<domain><a></domain>")
    assert e.value.motivo == "formato"


def test_seg_b4_con_expat_antiguo_se_anota_el_aviso_en_el_registro(monkeypatch, caplog):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", "expat_2.5.0")
    with caplog.at_level(logging.WARNING, logger="proxlaunch.libvirt.lectura_xml"):
        leer_xml(xml_minimo().encode())
    assert any("2.5.0" in r.getMessage() for r in caplog.records)


# --- Seg-B5: URL de un disco de red con credenciales -------------------------------------------

URL = "https://u:clave@h.example/x.qcow2?token=abc"


def _disco_red() -> str:
    return (
        "<disk type='network' device='disk'><driver name='qemu' type='qcow2'/>"
        f"<source protocol='https' name='{URL}'/><target dev='vdb' bus='virtio'/></disk>"
    )


def _recorrer(obj: Any):
    """Todos los textos de un objeto anidado (dataclasses, listas, diccionarios)."""
    if isinstance(obj, str):
        yield obj
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from _recorrer(getattr(obj, f.name))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _recorrer(k)
            yield from _recorrer(v)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            yield from _recorrer(v)
    elif hasattr(obj, "value") and isinstance(obj.value, str):
        yield obj.value


def test_seg_b5_el_archivo_de_un_disco_de_red_es_solo_el_nombre_sin_credenciales_ni_consulta():
    d = dominio_desde_texto(xml_minimo(disco_xml() + _disco_red()))
    assert d.discos[1].archivo == "x.qcow2"


def test_seg_b5_ni_la_clave_ni_el_token_aparecen_en_la_vista_previa_ni_en_el_dominio():
    d = dominio_desde_texto(xml_minimo(disco_xml() + _disco_red()))
    p = proponer_de(d, inv=inventario_d())
    for objeto in (d, p):
        textos = list(_recorrer(objeto)) + [repr(objeto)]
        for texto in textos:
            assert "clave" not in texto and "token" not in texto and "u:" not in texto, texto


def test_seg_b5_tambien_si_el_disco_de_red_es_el_de_sistema():
    d = dominio_desde_texto(xml_minimo(_disco_red().replace("vdb", "vda")))
    p = proponer_de(d, inv=inventario_d())
    assert d.discos[0].archivo == "x.qcow2"
    assert "clave" not in repr(p) and "token=abc" not in repr(p)


# --- Seg-B6: MAC conservada igual a la de una MV ya leída --------------------------------------


def _plan_importar_con_mac(m: MundoD, mac: str | None):
    """Lote por filas: un clon de la plantilla (obliga a leer sus tarjetas) y un importar disco
    con la MAC conservada ``mac``. Las plantillas solo se leen si alguna fila clona."""
    from .apoyo_mvp4 import VOLID_IMAGEN

    m.cl.contenido[("pve1", "local")] = [VOLID_IMAGEN]
    importar = dataclasses.replace(
        _importar(()), discos=[Disco("local-lvm", 8)],
        redes=[InterfazRed("vmbr0", mac_conservada=mac)],
    )  # fmt: skip
    filas = [FilaLote("clon-01", cfg_clon("base")), FilaLote("migrada-01", importar)]
    return m.planificar(definicion_filas(filas))


def test_seg_b6_una_mac_conservada_igual_al_net_de_una_plantilla_da_aviso_v_d33b():
    m = MundoD(privilegios=PRIVS)  # la plantilla 9000 trae net0 con AA:BB:CC:DD:EE:FF
    plan = _plan_importar_con_mac(m, "aa:bb:cc:dd:ee:ff")
    (p,) = [x for x in plan.problemas if x.regla == "V-D33b"]
    assert p.severidad == Severidad.AVISO
    assert p.params == {"mac": "aa:bb:cc:dd:ee:ff", "vmid": "9000"}
    assert not plan.bloqueado, [(x.regla, x.params) for x in plan.problemas]


def test_seg_b6_el_aviso_no_hace_lecturas_nuevas_del_servidor():
    sin = MundoD(privilegios=PRIVS)
    _plan_importar_con_mac(sin, None)
    con = MundoD(privilegios=PRIVS)
    _plan_importar_con_mac(con, "aa:bb:cc:dd:ee:ff")

    def lecturas(m: MundoD) -> list[tuple[str, str]]:
        return sorted((c.metodo, c.ruta) for c in m.cl.llamadas)

    assert lecturas(con) == lecturas(sin)


def test_seg_b6_una_mac_que_no_coincide_con_ninguna_mv_leida_no_avisa():
    m = MundoD(privilegios=PRIVS)
    plan = _plan_importar_con_mac(m, "52:54:00:12:34:56")
    assert "V-D33b" not in {x.regla for x in plan.problemas}


# --- USB: índices libres de la plantilla -------------------------------------------------------


def _det_usb(*ocupados: int):
    return detalle_de_config({f"usb{i}": "mapping=otro" for i in ocupados})


def test_usb_con_usb0_a_usb7_ocupados_el_clon_usa_usb8_en_adelante():
    det = _det_usb(*range(8))
    cfg = dataclasses.replace(cfg_clon("base"), hardware_cluster=hw(usb("a"), usb("b", usb3=True)))
    assert parametros_hardware_clon(cfg, det) == {"usb8": "mapping=a", "usb9": "mapping=b,usb3=1"}


def test_usb_el_tope_de_cinco_propios_se_mantiene_con_la_plantilla_ocupada():
    det = _det_usb(*range(8))
    cinco = dataclasses.replace(
        cfg_clon("base"), hardware_cluster=hw(*[usb(f"u{i}") for i in range(5)])
    )
    assert list(parametros_hardware_clon(cinco, det)) == [f"usb{i}" for i in range(8, 13)]
    seis = dataclasses.replace(
        cfg_clon("base"), hardware_cluster=hw(*[usb(f"u{i}") for i in range(6)])
    )
    problemas = validar_hardware_local(seis, caps_de(V_92), Arquitectura.X86_64)
    (v59,) = [p for p in problemas if p.codigo == "V-D59"]
    assert v59.severidad == Severidad.ERROR and v59.params["maximo"] == "5"


def test_usb_nunca_se_usa_el_indice_14_ni_mayor():
    assert MAX_INDICE_USB == 14
    det = _det_usb(*range(13))  # solo queda usb13
    uno = dataclasses.replace(cfg_clon("base"), hardware_cluster=hw(usb("a")))
    assert parametros_hardware_clon(uno, det) == {"usb13": "mapping=a"}
    dos = dataclasses.replace(cfg_clon("base"), hardware_cluster=hw(usb("a"), usb("b")))
    with pytest.raises(ValueError, match="libres"):
        parametros_hardware_clon(dos, det)  # no se inventa usb14


def test_usb_un_usb14_de_la_plantilla_no_cuenta_como_indice_ocupado_valido():
    det = detalle_de_config({"usb14": "mapping=x", "usb0": "mapping=y"})
    assert det.usb == (0,)  # usb14 no es un índice de Proxmox: se ignora al leer


def test_usb_el_clon_con_usb0_a_usb7_ocupados_escribe_usb8_en_el_servidor():
    m = MundoD(privilegios=PRIVS, extra={f"usb{i}": "mapping=otro" for i in range(8)})
    m.cl.mapeos_api["usb"] = [mapeo_api("llave", ("pve1", "/u"))]
    r = m.crear(_clon(m, usb("llave")))
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r.error
    (put,) = _puts_hw(m)
    assert put == {"usb8": "mapping=llave"}
