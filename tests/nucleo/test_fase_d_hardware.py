"""D3.2–D3.4 (0.9.0): asignar mapeos PCI/USB a la máquina, validación por nodo y restricciones.

CA-D3.2.1–8, CA-D3.3.1–7, CA-D3.4.1–6, CA-D5.1.3 (por mapeo), CA-D0.5.1, CA-D2.7.4/CA-D2.10.6
(``pcie`` en ARM), CL-D16, CL-D17, CL-D18, CL-D20, V-D50 a V-D64. Todo con dobles (sin servidor).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.lectura import leer_info_hardware
from proxlaunch.nucleo.hardware_cluster.modelos import (
    AsignacionPCI,
    AsignacionUSB,
    ComprobacionNodo,
    HardwareCluster,
    InfoHardwareCluster,
)
from proxlaunch.nucleo.hardware_cluster.peticion import (
    parametros_hardware,
    valor_hostpci,
    valor_usb,
)
from proxlaunch.nucleo.hardware_cluster.validacion import (
    validar_hardware_local,
    validar_hardware_servidor,
)
from proxlaunch.nucleo.lote.modelos import ModoDestino
from proxlaunch.nucleo.modelos.vm import Disco, Firmware
from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_fase_a import cfg_vm, def_lote, plan_de
from .apoyo_fase_d import (
    ARM,
    V_84,
    V_90,
    V_91,
    V_92,
    X86,
    banco_d,
    caps_de,
    cfg_arm,
    con_hardware,
    hw,
    info_hw,
    inv_arq,
    mapeo,
    pci,
    permisos_mapeo,
    usb,
)
from .apoyo_lote import error_http, mapeo_api


def _local(cfg, version=V_92, arq=Arquitectura.X86_64, **kw):
    return validar_hardware_local(cfg, caps_de(version), arq, **kw)


def _codigos(problemas) -> list[str]:
    return [p.codigo for p in problemas]


# --- CA-D3.2: la petición -------------------------------------------------------------------------


def test_ca_d3_2_1_gpu_con_pcie_y_x_vga_da_hostpci0_y_con_rombar_desactivado_lo_añade():
    assert valor_hostpci(pci("gpu-a2", pcie=True, x_vga=True)) == "mapping=gpu-a2,pcie=1,x-vga=1"
    a = AsignacionPCI("gpu-a2", pcie=True, x_vga=True, rombar=False)
    assert valor_hostpci(a) == "mapping=gpu-a2,pcie=1,x-vga=1,rombar=0"
    assert valor_hostpci(pci("g")) == "mapping=g"  # sin opciones: solo el mapeo


def test_ca_d3_2_1_el_orden_de_las_opciones_es_fijo_y_driver_keep_va_al_final():
    a = AsignacionPCI("g", pcie=True, x_vga=True, rombar=False, driver_keep=True)
    assert valor_hostpci(a) == "mapping=g,pcie=1,x-vga=1,rombar=0,driver=keep"


def test_ca_d3_2_2_un_usb_con_usb3_da_usb0_mapping_usb3_1():
    assert valor_usb(usb("llave-hasp", usb3=True)) == "mapping=llave-hasp,usb3=1"
    assert valor_usb(usb("llave-hasp")) == "mapping=llave-hasp"


def test_ca_d3_2_3_tres_pci_y_dos_usb_numeran_hostpci0_a_2_y_usb0_a_1():
    h = hw(pci("a"), pci("b"), pci("c"), usb("u1"), usb("u2"))
    assert parametros_hardware(h, set()) == {
        "hostpci0": "mapping=a",
        "hostpci1": "mapping=b",
        "hostpci2": "mapping=c",
        "usb0": "mapping=u1",
        "usb1": "mapping=u2",
    }


def test_sin_hardware_o_vacio_no_se_genera_ninguna_clave():
    assert parametros_hardware(None, set()) == {}
    assert parametros_hardware(HardwareCluster(), {"machine"}) == {}


@pytest.mark.parametrize(
    "malo", ["a b", "a;b", "a=b", "a,b", "x" * 65, "", "a/b", "a\nb", "<b>", "..;host=0000:00:00.0"]
)
def test_ca_d3_2_8_un_id_hostil_nunca_llega_a_la_peticion(malo):
    with pytest.raises(ValueError):
        parametros_hardware(hw(pci(malo)), set())
    with pytest.raises(ValueError):
        valor_usb(AsignacionUSB(malo))


def test_ca_d3_2_8_nunca_aparecen_host_romfile_legacy_igd_vendor_device_ni_mdev():
    h = hw(pci("a", pcie=True, x_vga=True, rombar=False, driver_keep=True), usb("u", usb3=True))
    texto = " ".join(parametros_hardware(h, set()).values())
    for prohibido in ("host=", "romfile", "legacy-igd", "vendor-id", "device-id", "mdev"):
        assert prohibido not in texto


def test_el_orden_de_las_claves_es_machine_vga_hostpci_usb():
    h = hw(pci("a", pcie=True, x_vga=True), usb("u"))
    assert list(parametros_hardware(h, set())) == ["machine", "vga", "hostpci0", "usb0"]


def test_ca_d3_2_5_los_indices_libres_del_clon_se_numeran_desde_el_primer_libre():
    p = parametros_hardware(
        hw(pci("nuevo"), usb("u")), {"net0"}, libres_pci=[1, 2, 3], libres_usb=[0, 2]
    )
    assert p == {"hostpci1": "mapping=nuevo", "usb0": "mapping=u"}


def test_sin_indices_libres_suficientes_es_valueerror():
    with pytest.raises(ValueError):
        parametros_hardware(hw(pci("a"), pci("b")), set(), libres_pci=[5])
    with pytest.raises(ValueError):
        parametros_hardware(hw(usb("u")), set(), libres_usb=[])


def test_los_indices_libres_fuera_de_rango_no_se_usan():
    with pytest.raises(ValueError):
        parametros_hardware(hw(pci("a")), set(), libres_pci=[16, 40])  # hostpci0..15 y usb0..4
    # usb: se miran los 14 índices de Proxmox (usb0..usb13); el tope de 5 propios va aparte
    assert parametros_hardware(hw(usb("u")), set(), libres_usb=[5]) == {"usb5": "mapping=u"}
    with pytest.raises(ValueError):
        parametros_hardware(hw(usb("u")), set(), libres_usb=[14])


# --- Dentro del POST de creación (DT-D11) ---------------------------------------------------------


def _post(cfg, version=V_92, arq=X86):
    inv = inv_arq({"pve1": arq} if arq else {}, nodos=("pve1",), version=version)
    return construir_parametros(cfg, inv, (version.mayor, version.menor))


def test_las_claves_de_hardware_van_al_final_del_cuerpo_tras_protection():
    cfg = con_hardware(cfg_vm(proteger=True, arranque_auto=True), pci("g"), usb("u"))
    claves = list(_post(cfg))
    assert claves[-3:] == ["protection", "hostpci0", "usb0"] and claves.index(
        "onboot"
    ) < claves.index("protection")


def test_ca_d3_4_1_pcie_con_seabios_en_x86_añade_machine_q35():
    cfg = con_hardware(cfg_vm(), pci("g", pcie=True))
    assert cfg.firmware == Firmware.SEABIOS
    p = _post(cfg)
    assert p["machine"] == "q35" and p["hostpci0"] == "mapping=g,pcie=1"
    assert "bios" not in p


def test_ca_d3_4_1_pcie_con_ovmf_no_duplica_machine():
    cfg = con_hardware(cfg_vm(firmware=Firmware.OVMF), pci("g", pcie=True))
    p = _post(cfg)
    assert p["machine"] == "q35" and list(p).count("machine") == 1


def test_sin_pcie_no_se_toca_machine_aunque_haya_mapeos():
    p = _post(con_hardware(cfg_vm(), pci("g"), usb("u")))
    assert "machine" not in p and "vga" not in p


def test_ca_d3_4_2_x_vga_con_pcie_añade_vga_none():
    p = _post(con_hardware(cfg_vm(), pci("g", pcie=True, x_vga=True)))
    assert p["vga"] == "none" and p["hostpci0"] == "mapping=g,pcie=1,x-vga=1"
    assert p["machine"] == "q35"


def test_en_aarch64_el_hardware_va_tambien_pero_nunca_con_machine_q35():
    p = _post(con_hardware(cfg_arm(), pci("g"), usb("u")), arq=ARM)
    assert p["hostpci0"] == "mapping=g" and p["usb0"] == "mapping=u" and "machine" not in p
    assert p["vga"] == "virtio"


def test_en_aarch64_x_vga_sustituye_a_la_vga_virtio_por_none():
    p = _post(con_hardware(cfg_arm(), pci("g", x_vga=True)), arq=ARM)
    assert p["vga"] == "none"


@pytest.mark.parametrize("version", [V_84, V_90, V_91, V_92], ids=["8.4", "9.0", "9.1", "9.2"])
def test_la_peticion_de_hardware_no_cambia_con_la_version_del_servidor(version):
    cfg = con_hardware(cfg_vm(), pci("g", pcie=True), usb("u", usb3=True))
    assert _post(cfg, version)["hostpci0"] == "mapping=g,pcie=1"


# --- CA-D3.2.5–7 y V-D54/V-D55/V-D57/V-D59/V-D60/V-D64 (locales) ----------------------------------


def test_ca_d3_2_5_17_pci_o_6_usb_dan_v_d59_y_16_y_5_se_aceptan():
    ok = con_hardware(
        cfg_vm(), *[pci(f"g{i}") for i in range(16)], *[usb(f"u{i}") for i in range(5)]
    )
    assert "V-D59" not in _codigos(_local(ok))
    mucho_pci = con_hardware(cfg_vm(), *[pci(f"g{i}") for i in range(17)])
    (p,) = [x for x in _local(mucho_pci) if x.codigo == "V-D59"]
    assert (
        p.severidad == Severidad.ERROR and p.params["tipo"] == "pci" and p.params["maximo"] == "16"
    )
    mucho_usb = con_hardware(cfg_vm(), *[usb(f"u{i}") for i in range(6)])
    (p,) = [x for x in _local(mucho_usb) if x.codigo == "V-D59"]
    assert p.params == {"tipo": "usb", "maximo": "5", "cantidad": "6"}


@pytest.mark.parametrize(
    ("version", "bloquea"), [(V_84, True), (V_90, True), (V_91, False), (V_92, False)]
)
def test_ca_d3_2_6_driver_keep_solo_desde_9_1(version, bloquea):
    cfg = con_hardware(cfg_vm(), pci("g", driver_keep=True))
    problemas = [p for p in _local(cfg, version) if p.codigo == "V-D60"]
    assert bool(problemas) is bloquea
    if bloquea:
        assert problemas[0].severidad == Severidad.ERROR and problemas[0].params["mapeo"] == "g"
        assert problemas[0].params["version"] == f"{version.mayor}.{version.menor}"


def test_ca_d3_2_7_el_mismo_mapeo_pci_dos_veces_en_la_misma_maquina_da_v_d64():
    cfg = con_hardware(cfg_vm(), pci("g"), pci("h"), pci("g"), pci("g"))
    (p,) = [x for x in _local(cfg) if x.codigo == "V-D64"]  # una sola vez por mapeo repetido
    assert p.severidad == Severidad.ERROR and p.params == {"mapeo": "g"}


def test_ca_d3_2_7_el_mismo_mapeo_en_pci_y_en_usb_no_es_repeticion():
    assert "V-D64" not in _codigos(_local(con_hardware(cfg_vm(), pci("x"), usb("x"))))


def test_ca_d3_4_1_pcie_avisa_v_d54_una_sola_vez_aunque_haya_varias_tarjetas():
    cfg = con_hardware(cfg_vm(), pci("a", pcie=True), pci("b", pcie=True))
    avisos = [p for p in _local(cfg) if p.codigo == "V-D54"]
    assert len(avisos) == 1 and avisos[0].severidad == Severidad.AVISO
    assert avisos[0].params == {"maquina": "q35"}


def test_ca_d3_4_2_x_vga_sin_pcie_es_error_v_d55_y_con_pcie_aviso_v_d55b():
    sin = [p for p in _local(con_hardware(cfg_vm(), pci("g", x_vga=True))) if p.codigo == "V-D55"]
    assert len(sin) == 1 and sin[0].severidad == Severidad.ERROR
    con = _local(con_hardware(cfg_vm(), pci("g", pcie=True, x_vga=True)))
    assert "V-D55" not in _codigos(con)
    (b,) = [p for p in con if p.codigo == "V-D55b"]
    assert b.severidad == Severidad.AVISO and b.params == {"vga": "none"}


def test_ca_d3_4_3_un_pci_no_migrable_o_un_usb_avisan_v_d57_y_uno_migrable_no():
    cfg = con_hardware(cfg_vm(), pci("g"), usb("u"))
    info = info_hw(mapeo("pci", "g", "pve1", migrable=True), mapeo("usb", "u", "pve1"))
    (v,) = [p for p in _local(cfg, info=info) if p.codigo == "V-D57"]
    assert v.severidad == Severidad.AVISO and v.params["mapeos"] == "u"  # solo el USB
    solo_pci = con_hardware(cfg_vm(), pci("g"))
    assert "V-D57" not in _codigos(_local(solo_pci, info=info))
    no_migrable = info_hw(mapeo("pci", "g", "pve1", migrable=False))
    assert "V-D57" in _codigos(_local(solo_pci, info=no_migrable))
    assert "V-D57" in _codigos(_local(solo_pci))  # sin lectura se avisa por prudencia


def test_cl_d17_pcie_en_aarch64_es_v_d09_con_motivo_pcie():
    cfg = con_hardware(cfg_arm(), pci("g", pcie=True))
    problemas = _local(cfg, arq=Arquitectura.AARCH64)
    (p,) = [x for x in problemas if x.codigo == "V-D09"]
    assert p.severidad == Severidad.ERROR
    assert p.params["motivo"] == "pcie" and p.params["arquitectura"] == "aarch64"
    assert "V-D54" not in _codigos(problemas)  # en ARM no hay q35 que avisar


def test_ca_d2_7_4_y_ca_d2_10_6_pcie_en_un_nodo_aarch64_bloquea_comprobar_y_no_se_adapta():
    banco = banco_d({"pve1": ARM}, hardware=None)
    cfg = con_hardware(cfg_arm(), pci("g", pcie=True))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("g", ("pve1", "/x"))]
    plan = plan_de(banco, def_lote(1, plantilla_vm=cfg))
    assert plan.bloqueado
    assert any(p.regla == "V-D09" and p.params["motivo"] == "pcie" for p in plan.problemas)
    assert plan.elementos[0].cfg.hardware_cluster.pci[0].pcie is True  # nunca se cambia solo


def test_cl_d18_un_mapeo_mdev_no_avisa_v_d56_pero_si_v_d57_segun_live_migration():
    cfgs = {"pve1": [con_hardware(cfg_vm(), pci("vgpu"))] * 5}
    info = info_hw(mapeo("pci", "vgpu", "pve1", mdev=True, migrable=False))
    assert "V-D56" not in _codigos(validar_hardware_servidor(cfgs, info, None))
    assert "V-D57" in _codigos(_local(cfgs["pve1"][0], info=info))
    ok = info_hw(mapeo("pci", "vgpu", "pve1", mdev=True, migrable=True))
    assert "V-D57" not in _codigos(_local(cfgs["pve1"][0], info=ok))


def test_ca_d3_2_5_driver_keep_con_version_forzada_9_0_no_se_ofrece_y_9_2_si():
    for version, ok in (((9, 0), False), ((9, 1), True), ((9, 2), True)):
        caps = Capacidades(version, True)
        cfg = con_hardware(cfg_vm(), pci("g", driver_keep=True))
        malos = [
            p for p in validar_hardware_local(cfg, caps, Arquitectura.X86_64) if p.codigo == "V-D60"
        ]
        assert (malos == []) is ok


# --- CA-D3.3 / CA-D3.4 contra el servidor ---------------------------------------------------------


def _cfgs(nodo: str, n: int, *dispositivos: Any) -> dict[str, list]:
    return {nodo: [con_hardware(cfg_vm(), *dispositivos) for _ in range(n)]}


def _servidor(cfgs, info, permisos=None):
    return validar_hardware_servidor(cfgs, info, permisos)


def test_ca_d3_3_1_un_mapeo_solo_en_pve1_con_un_lote_en_pve1_y_pve2_da_v_d52_nombrando_pve2():
    info = info_hw(mapeo("pci", "gpu-a2", "pve1"))
    cfgs = {**_cfgs("pve1", 2, pci("gpu-a2")), **_cfgs("pve2", 2, pci("gpu-a2"))}
    (p,) = [x for x in _servidor(cfgs, info) if x.codigo == "V-D52"]
    assert p.severidad == Severidad.ERROR and p.params["nodos"] == "pve2"
    assert p.params["mapeo"] == "gpu-a2"


def test_ca_d3_3_2_cl_d16_el_mapeo_en_todos_los_nodos_del_lote_no_da_error_aunque_sobren_nodos():
    info = info_hw(mapeo("pci", "gpu-a2", "pve1", "pve2", "pve3"))
    cfgs = {**_cfgs("pve1", 1, pci("gpu-a2")), **_cfgs("pve2", 1, pci("gpu-a2"))}
    assert [p for p in _servidor(cfgs, info) if p.severidad == Severidad.ERROR] == []


def test_ca_d3_3_7_un_mapeo_que_ya_no_existe_da_v_d51_nombrandolo():
    info = info_hw(mapeo("pci", "otro", "pve1"))
    (p,) = [x for x in _servidor(_cfgs("pve1", 3, pci("gpu-a2")), info) if x.codigo == "V-D51"]
    assert p.severidad == Severidad.ERROR and p.params["mapeo"] == "gpu-a2"


def test_v_d51_para_un_pci_y_un_usb_distintos_con_el_mismo_id_se_distingue_por_tipo():
    info = info_hw(mapeo("usb", "x", "pve1"))
    r = _servidor(_cfgs("pve1", 1, pci("x")), info)
    assert [p.params["tipo"] for p in r if p.codigo == "V-D51"] == ["pci"]


def test_ca_d3_3_3_check_node_con_error_da_v_d53_con_el_mensaje_y_sin_error_no():
    info = info_hw(
        mapeo("pci", "g", "pve1"),
        comprobaciones=[ComprobacionNodo("g", "pve1", ("Invalid configuration: no such device",))],
    )
    (p,) = [x for x in _servidor(_cfgs("pve1", 1, pci("g")), info) if x.codigo == "V-D53"]
    assert p.severidad == Severidad.ERROR and "Invalid configuration" in p.params["mensaje"]
    assert p.params["nodo"] == "pve1"
    limpio = info_hw(mapeo("pci", "g", "pve1"), comprobaciones=[ComprobacionNodo("g", "pve1", ())])
    assert "V-D53" not in _codigos(_servidor(_cfgs("pve1", 1, pci("g")), limpio))


def test_ca_d3_3_3_el_mensaje_de_check_node_va_saneado_y_acotado():
    sucio = "<img src=x onerror=1>\n\x00" + "z" * 3000
    info = info_hw(
        mapeo("pci", "g", "pve1"), comprobaciones=[ComprobacionNodo("g", "pve1", (sucio,))]
    )
    (p,) = [x for x in _servidor(_cfgs("pve1", 1, pci("g")), info) if x.codigo == "V-D53"]
    assert len(p.params["mensaje"]) <= 256 and not any(c in p.params["mensaje"] for c in "<>\n\x00")


def test_ca_d3_3_4_si_check_node_falla_solo_es_un_aviso_y_no_bloquea():
    info = info_hw(mapeo("pci", "g", "pve1"), sin_comprobar=[("pci", "g", "pve1")])
    r = _servidor(_cfgs("pve1", 1, pci("g")), info)
    (aviso,) = [p for p in r if p.codigo == "V-D53.sin_comprobar"]
    assert aviso.severidad == Severidad.AVISO
    assert [p for p in r if p.severidad == Severidad.ERROR] == []


def test_ca_d3_4_4_dos_dispositivos_en_pve1_y_cinco_maquinas_dan_v_d56_solo_podran_2_de_5():
    info = info_hw(mapeo("pci", "g", "pve1", por_nodo={"pve1": 2}))
    (p,) = [x for x in _servidor(_cfgs("pve1", 5, pci("g")), info) if x.codigo == "V-D56"]
    assert p.severidad == Severidad.AVISO
    assert p.params == {"mapeo": "g", "nodo": "pve1", "k": "2", "n": "5"}


def test_ca_d3_4_4_con_mdev_no_hay_v_d56():
    info = info_hw(mapeo("pci", "g", "pve1", mdev=True))
    assert "V-D56" not in _codigos(_servidor(_cfgs("pve1", 5, pci("g")), info))


def test_ca_d3_4_5_cl_d20_un_usb_con_una_entrada_y_dos_maquinas_en_el_nodo_da_v_d56():
    info = info_hw(mapeo("usb", "u", "pve1"))
    (p,) = [x for x in _servidor(_cfgs("pve1", 2, usb("u")), info) if x.codigo == "V-D56"]
    assert p.params["k"] == "1" and p.params["n"] == "2"
    (p,) = [x for x in _servidor(_cfgs("pve1", 100, usb("u")), info) if x.codigo == "V-D56"]
    assert (p.params["k"], p.params["n"]) == ("1", "100")  # «solo podrá arrancar 1 de 100»
    assert p.severidad == Severidad.AVISO  # sigue siendo creable


def test_ca_d3_4_6_cuatro_maquinas_repartidas_2_mas_2_con_dos_dispositivos_por_nodo_no_avisan():
    info = info_hw(mapeo("pci", "g", "pve1", "pve2", por_nodo={"pve1": 2, "pve2": 2}))
    cfgs = {**_cfgs("pve1", 2, pci("g")), **_cfgs("pve2", 2, pci("g"))}
    assert "V-D56" not in _codigos(_servidor(cfgs, info))


def test_ca_d3_4_4_un_mapeo_repetido_en_una_misma_maquina_cuenta_como_un_uso():
    info = info_hw(mapeo("pci", "g", "pve1", por_nodo={"pve1": 2}))
    cfgs = {"pve1": [con_hardware(cfg_vm(), pci("g"), pci("g")) for _ in range(2)]}
    assert "V-D56" not in _codigos(_servidor(cfgs, info))  # 2 máquinas, 2 dispositivos


def test_ca_d5_1_3_solo_el_mapeo_sin_mapping_use_queda_deshabilitado_los_otros_siguen():
    info = info_hw(
        mapeo("pci", "a", "pve1"), mapeo("pci", "b", "pve1"), mapeo("usb", "llave-hasp", "pve1")
    )
    permisos = permisos_mapeo("/mapping/pci/a", "/mapping/pci/b")
    cfgs = _cfgs("pve1", 1, pci("a"), pci("b"), usb("llave-hasp"))
    faltan = [p for p in _servidor(cfgs, info, permisos) if p.codigo == "V-D63"]
    assert [p.params["ruta"] for p in faltan] == ["/mapping/usb/llave-hasp"]
    assert (
        faltan[0].params["privilegio"] == "Mapping.Use" and faltan[0].severidad == Severidad.ERROR
    )


def test_ca_d0_3_2_con_permisos_desconocidos_no_hay_v_d63_ni_se_afirma_nada():
    info = info_hw(mapeo("pci", "a", "pve1"))
    assert "V-D63" not in _codigos(_servidor(_cfgs("pve1", 1, pci("a")), info, None))


def test_ca_d5_1_3_mapping_use_en_la_raiz_o_en_mapping_cubre_todos_los_mapeos():
    info = info_hw(mapeo("pci", "a", "pve1"), mapeo("usb", "u", "pve1"))
    cfgs = _cfgs("pve1", 1, pci("a"), usb("u"))
    for ruta in ("/", "/mapping", "/mapping/pci", "/mapping/usb"):
        faltan = [
            p.params["ruta"]
            for p in _servidor(cfgs, info, permisos_mapeo(ruta))
            if p.codigo == "V-D63"
        ]
        esperado = {"/mapping/pci": ["/mapping/usb/u"], "/mapping/usb": ["/mapping/pci/a"]}.get(
            ruta, []
        )
        assert faltan == esperado, ruta


def test_v_d50_sin_mapeos_visibles_o_no_leidos_solo_si_el_lote_usa_mapeos():
    assert _servidor({"pve1": [cfg_vm()]}, info_hw()) == []  # el lote no usa mapeos
    r = _servidor(_cfgs("pve1", 1, pci("g")), info_hw())
    assert any(p.codigo == "V-D50" and p.params["motivo"] == "sin_mapeos" for p in r)
    fallo = InfoHardwareCluster(
        mapeos=None,
        error_mapeos=ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"tipo": "pci,usb"}),
    )
    r = _servidor(_cfgs("pve1", 1, pci("g")), fallo)
    assert any(p.codigo == "V-D50" and p.params["motivo"] == "no_leido" for p in r)
    assert "V-D51" not in _codigos(r)  # si no se pudo leer no se afirma que no exista
    assert [p for p in r if p.severidad == Severidad.ERROR] == []


def test_sin_lectura_ninguna_la_validacion_no_afirma_nada():
    assert _servidor(_cfgs("pve1", 1, pci("g")), None) == []
    assert _servidor(_cfgs("pve1", 1, pci("g")), InfoHardwareCluster()) == []


# --- Lecturas de «Comprobar»: check-node (CA-D3.3.5, CA-D3.3.6, RNF-D4) ---------------------------


def _leer(banco, usados, nodos=("pve1", "pve2"), previo=None):
    return leer_info_hardware(
        banco.sesion.cliente,
        banco.inv.catalogo.permisos,
        banco.sesion.capacidades,
        NecesidadesCatalogo(mapeos=frozenset(usados)),
        nodos,
        previo,
        {},
    )


def _checks(banco) -> list[tuple[str, str]]:
    return [
        (c.ruta.rsplit("/", 1)[1], c.params["check-node"])
        for c in banco.cluster.llamadas
        if c.params and "check-node" in c.params
    ]


def test_ca_d3_3_5_cien_maquinas_en_dos_nodos_con_dos_mapeos_hacen_a_lo_sumo_cuatro_check_node():
    banco = banco_d(nodos=("pve1", "pve2"), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("g", ("pve1", "/x"), ("pve2", "/y"))]
    banco.cluster.mapeos_api["usb"] = [mapeo_api("u", ("pve1", "/u"), ("pve2", "/v"))]
    info = _leer(banco, {("pci", "g"), ("usb", "u")})
    assert len(_checks(banco)) == 4
    assert sorted(_checks(banco)) == [
        ("pci", "pve1"),
        ("pci", "pve2"),
        ("usb", "pve1"),
        ("usb", "pve2"),
    ]
    assert len(banco.cluster.lecturas_d(r"/cluster/mapping/")) == 2 + 4
    assert len(info.comprobaciones) == 4


def test_ca_d3_3_5_una_segunda_comprobacion_reutiliza_lo_leido_y_no_repite_nada():
    banco = banco_d(nodos=("pve1", "pve2"), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("g", ("pve1", "/x"), ("pve2", "/y"))]
    info = _leer(banco, {("pci", "g")})
    n = len(banco.cluster.llamadas)
    _leer(banco, {("pci", "g")}, previo=info)
    assert len(banco.cluster.llamadas) == n


def test_ca_d3_3_check_node_solo_se_pide_para_nodos_del_lote_donde_el_mapeo_tiene_entrada():
    banco = banco_d(nodos=("pve1", "pve2", "pve3"), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("g", ("pve1", "/x"), ("pve3", "/z"))]
    _leer(banco, {("pci", "g")}, nodos=("pve1", "pve2"))
    assert _checks(banco) == [("pci", "pve1")]  # pve2 no tiene entrada; pve3 no es del lote


def test_ca_d3_3_6_check_node_lee_checks_de_pci_y_errors_y_error_de_usb_y_solo_gravedad_error():
    banco = banco_d(nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping"))
    c = banco.cluster
    c.mapeos_api["pci"] = [mapeo_api("g", ("pve1", "/x"))]
    c.mapeos_api["usb"] = [mapeo_api("u", ("pve1", "/u")), mapeo_api("v", ("pve1", "/v"))]
    c.check_node_api[("pci", "pve1")] = [
        {"id": "g", "checks": [{"severity": "error", "message": "Invalid configuration: x"},
                               {"severity": "warning", "message": "solo aviso"}]},
        {"id": "otro", "checks": [{"severity": "error", "message": "de otro mapeo"}]},
    ]  # fmt: skip
    c.check_node_api[("usb", "pve1")] = [
        {"id": "u", "errors": [{"severity": "error", "message": "forma errors"}]},
        {"id": "v", "error": [{"severity": "error", "message": "forma error"}]},
    ]
    info = _leer(banco, {("pci", "g"), ("usb", "u"), ("usb", "v")}, nodos=("pve1",))
    por_mapeo = {x.mapeo: x.errores for x in info.comprobaciones}
    assert por_mapeo == {
        "g": (
            "Invalid configuration: x",
        ),  # el aviso (warning) no es error y el de otro id no cuenta
        "u": ("forma errors",),
        "v": ("forma error",),
    }


def test_ca_d3_3_4_si_check_node_devuelve_403_o_falla_la_red_queda_en_errores_y_no_lanza():
    for fallo in (error_http(403, "Permission check failed"), OSError("red"), error_http(500, "x")):
        banco = banco_d(nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping"))
        banco.cluster.mapeos_api["pci"] = [mapeo_api("g", ("pve1", "/x"))]
        banco.cluster.check_node_api[("pci", "pve1")] = fallo
        info = _leer(banco, {("pci", "g")}, nodos=("pve1",))
        assert info.errores_comprobacion == (("pci", "g", "pve1"),) and info.comprobaciones == ()


def test_check_node_se_omite_si_falta_mapping_use_en_ese_mapeo():
    banco = banco_d(nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping/pci/otro"))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("g", ("pve1", "/x"))]
    info = _leer(banco, {("pci", "g")}, nodos=("pve1",))
    assert _checks(banco) == [] and info.comprobaciones == ()


def test_sin_mapeos_usados_ni_seccion_abierta_no_se_hace_ninguna_lectura_nueva():
    """CA-D0.2 / RNF-D4: sin D3 no hay GET nuevos."""
    banco = banco_d(nodos=("pve1",))
    antes = len(banco.cluster.llamadas)
    info = leer_info_hardware(
        banco.sesion.cliente,
        None,
        banco.sesion.capacidades,
        NecesidadesCatalogo(),
        ("pve1",),
        None,
        {},
    )
    assert len(banco.cluster.llamadas) == antes
    assert info.mapeos is None and info.cpus == {}


def test_un_id_hostil_en_las_necesidades_no_provoca_ninguna_peticion():
    banco = banco_d(nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("g", ("pve1", "/x"))]
    _leer(banco, {("pci", "g;rm"), ("otro", "g"), ("pci", "../x")}, nodos=("pve1",))
    assert _checks(banco) == []


# --- Plan completo con mapeos (CA-D0.5.1 y la integración de la validación) -----------------------


def _plan_hw(n, *dispositivos, nodos=("pve1", "pve2"), por_nodo=None, **kw):
    banco = banco_d(
        {n_: X86 for n_ in nodos}, nodos=nodos, permisos_efectivos=permisos_mapeo("/mapping"), **kw
    )
    banco.cluster.mapeos_api["pci"] = [
        mapeo_api("gpu-a2", *[(n_, f"/dev/{n_}") for n_ in (por_nodo or nodos)], migrable=True)
    ]
    banco.cluster.mapeos_api["usb"] = [mapeo_api("llave", *[(n_, "/u") for n_ in nodos])]
    cfg = con_hardware(cfg_arm(discos=[Disco("local-lvm", 1)]), *dispositivos)
    return plan_de(banco, def_lote(n, plantilla_vm=cfg)), banco


def test_ca_d0_5_1_un_lote_homogeneo_lleva_los_mismos_mapeos_en_las_n_peticiones():
    plan, banco = _plan_hw(4, pci("gpu-a2", pcie=True), usb("llave", usb3=True))
    assert not plan.bloqueado, [(p.regla, p.params) for p in plan.problemas]
    cuerpos = [construir_parametros(e.cfg, banco.inv) for e in plan.elementos]
    assert len(cuerpos) == 4
    for c in cuerpos:
        assert c["hostpci0"] == "mapping=gpu-a2,pcie=1" and c["usb0"] == "mapping=llave,usb3=1"
        assert c["machine"] == "q35"


def test_el_plan_con_un_mapeo_inexistente_en_un_nodo_no_crea_nada_y_nombra_el_nodo():
    plan, _ = _plan_hw(4, pci("gpu-a2"), por_nodo=("pve1",))
    assert plan.bloqueado
    (p,) = [x for x in plan.problemas if x.regla == "V-D52"]
    assert p.params["nodos"] == "pve2" and p.params["mapeo"] == "gpu-a2"


def test_el_plan_del_lote_lee_los_mapeos_una_sola_vez_y_check_node_una_por_mapeo_y_nodo():
    plan, banco = _plan_hw(100, pci("gpu-a2"))
    assert not plan.bloqueado
    assert len(banco.cluster.lecturas_d(r"/cluster/mapping/(pci|usb)$")) == 2 + 2  # 2 + 2 check
    assert len(_checks(banco)) == 2  # pve1 y pve2: ≤ mapeos × nodos


def test_el_plan_marca_v_d56_cuando_hay_mas_maquinas_que_dispositivos():
    plan, _ = _plan_hw(5, pci("gpu-a2"), nodos=("pve1",))
    (p,) = [x for x in plan.problemas if x.regla == "V-D56"]
    assert p.params["k"] == "1" and p.params["n"] == "5" and p.severidad.value == "aviso"
    assert not plan.bloqueado  # sigue siendo creable (CL-D20)


def test_el_plan_sin_mapping_use_bloquea_con_v_d63_y_no_pide_check_node():
    banco = banco_d({"pve1": X86}, nodos=("pve1",))  # el rol de 14 no trae Mapping.Use
    banco.cluster.mapeos_api["pci"] = [mapeo_api("gpu-a2", ("pve1", "/x"))]
    plan = plan_de(banco, def_lote(1, plantilla_vm=con_hardware(cfg_arm(), pci("gpu-a2"))))
    assert plan.bloqueado
    (p,) = [x for x in plan.problemas if x.regla == "V-D63"]
    assert p.params["ruta"] == "/mapping/pci/gpu-a2" and p.params["privilegio"] == "Mapping.Use"
    assert _checks(banco) == []


def test_el_lote_sin_hardware_no_hace_ninguna_lectura_de_mapeos():
    banco = banco_d({"pve1": X86}, nodos=("pve1",))
    plan = plan_de(banco, def_lote(3, plantilla_vm=cfg_arm()))
    assert not plan.bloqueado
    assert banco.cluster.lecturas_d(r"/cluster/mapping") == []
    assert banco.cluster.lecturas_d(r"capabilities") == []


def test_las_dobles_de_apoyo_no_cambian_el_dataclass_original():
    cfg = cfg_arm()
    nuevo = dataclasses.replace(cfg, hardware_cluster=hw(pci("a")))
    assert cfg.hardware_cluster is None and nuevo.hardware_cluster.pci[0].mapeo == "a"
    assert ModoDestino.AUTOMATICO.value == "automatico"
