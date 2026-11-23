"""Red de la fase C (0.8.0) en el flujo de creación: reescribir la red al clonar (C4), VNets de SDN
(C2) y no regresión frente a 0.7.0.

Requisitos: RF-C4.1, RF-C4.3, RF-C4.4, RF-C4.5, RF-C4.7, RF-C4.8, RF-C4.9, RF-C2.1 (CA-C2.1.3),
RF-C2.5 (CA-C2.5.3), V-C21, CL-C14, CL-C16, CL-C20 y RF-C0.2 (golden de 0.7.0).

Dobles: ``ClusterC`` (``apoyo_fase_c_red``): el clon recibe MACs nuevas, el ``PUT config`` comprueba
``digest``, atiende ``delete`` y genera otra MAC cuando un ``netN`` llega sin ella. El servicio, el
motor y el cliente son los reales. Las instantáneas de 0.7.0 son las de
``tests/datos/fase_b/golden_v060.json`` (con las opciones de la fase B y C por defecto no cambia
ni un byte).
"""

from __future__ import annotations

import dataclasses
import json
import re

import pytest

from proxlaunch.nucleo.cloudinit.modelos import ModoTarjeta, TarjetaCloudInit
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.modelos.vm import InterfazRed
from proxlaunch.nucleo.servicios.descubrimiento import descubrir

from . import apoyo_golden_fase_b as g
from .apoyo_api import TransporteFalso, crear_sesion, dato, rutas_inventario
from .apoyo_fase_b_p1 import MundoB, ci, fallar_put
from .apoyo_fase_c_red import (
    MAC_PLANTILLA_0,
    MAC_PLANTILLA_1,
    MundoC,
    anadir,
    bridge,
    cambiar,
    cfg_con_red,
    mac_clon,
    quitar,
    red_clon,
    vnet,
)
from .apoyo_lote import error_http
from .apoyo_mvp4 import cfg_base

RE_NET = re.compile(r"^net\d+$")
RE_MAC = re.compile(r"=([0-9A-F]{2}(?::[0-9A-F]{2}){5})")

BRIDGES = {"pve1": (bridge("vmbr0"), bridge("vmbr1"), bridge("vmbr9"))}
VNETS = {"pve1": (vnet("prod", vlan_aware=True, alias="Producción"), vnet("plana"))}


def mundo(**kw) -> MundoC:
    kw.setdefault("bridges", BRIDGES)
    kw.setdefault("redes_sdn", VNETS)
    return MundoC(**kw)


def clon(m: MundoC, red, **kw):
    return cfg_con_red(m, red, **kw)


def err_403(ruta: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE,
        {"ruta": ruta, "privilegio": "SDN.Use"},
        f"403 Permission check failed ({ruta}, SDN.Use)",
    )


def redes_de(m: MundoC, vmid: int = 100) -> dict[str, str]:
    """``netN`` de la config final del clon en el servidor."""
    cfg = m.cluster.vms[vmid]["config"]
    return {k: v for k, v in cfg.items() if RE_NET.match(k)}


def claves_net(datos: dict) -> list[str]:
    return [k for k in datos if RE_NET.match(k)]


# --- RF-C4.1: modo «Como la plantilla» (sin regresiones) -----------------------------------------


def test_ca_c4_1_1_sin_red_personalizada_no_hay_lectura_ni_escritura_de_red_extra():
    """CA-C4.1.1 / CA-C0.2.3: las peticiones son las mismas que en 0.7.0 (``MundoB``)."""
    c = mundo()
    c.crear(c.cfg(encender=True))
    b = MundoB()
    b.crear(b.cfg(encender=True))
    assert [(x.metodo, x.ruta, x.datos) for x in c.cl.llamadas] == [
        (x.metodo, x.ruta, x.datos) for x in b.cl.llamadas
    ]
    assert not c.cluster.puts_de_red(100)


def test_ca_c4_1_1_la_red_en_modo_plantilla_no_deja_ninguna_tarjeta_tocada():
    m = mundo()
    m.crear(m.cfg())
    assert redes_de(m) == {
        "net0": f"virtio={mac_clon(100, 0)},bridge=vmbr0",
        "net1": f"virtio={mac_clon(100, 1)},bridge=vmbr0",
    }


def test_ca_c4_1_1_personalizar_sin_ningun_cambio_tampoco_escribe_la_red():
    m = mundo()
    r = m.crear(clon(m, red_clon()))
    assert r.desenlace == Desenlace.OK
    assert not m.cluster.puts_de_red(100)


# --- RF-C4.1 y RF-C4.3: reescritura conservando la MAC -------------------------------------------


def test_ca_c4_1_2_tras_el_clon_se_lee_la_config_y_se_emite_un_put_con_la_mac_del_clon():
    m = mundo()
    r = m.crear(clon(m, red_clon(cambiar(0, bridge="vmbr1"))))
    assert r.desenlace == Desenlace.OK, r.error
    puts = m.cluster.puts_de_red(100)
    assert len(puts) == 1
    assert puts[0]["net0"] == f"virtio={mac_clon(100, 0)},bridge=vmbr1"
    # La tarjeta que no se tocó no se reenvía ni se altera.
    assert "net1" not in puts[0]
    assert redes_de(m)["net1"] == f"virtio={mac_clon(100, 1)},bridge=vmbr0"


def test_ca_c4_3_1_la_mac_enviada_es_la_del_clon_y_no_la_de_la_plantilla():
    """INV-C §4: al clonar Proxmox da MAC nuevas; reenviar la de la plantilla las duplicaría."""
    m = mundo()
    m.crear(clon(m, red_clon(cambiar(0, bridge="vmbr1"), cambiar(1, vlan=30))))
    (put,) = m.cluster.puts_de_red(100)
    for clave in ("net0", "net1"):
        assert MAC_PLANTILLA_0 not in put[clave] and MAC_PLANTILLA_1 not in put[clave]
    assert not m.cluster.macs_generadas


@pytest.mark.parametrize(
    "red",
    [
        red_clon(cambiar(0, bridge="vmbr1")),
        red_clon(cambiar(0, vlan=10), cambiar(1, vlan=None)),
        red_clon(cambiar(1, modelo="e1000")),
        red_clon(cambiar(0, mtu=1400, limite_mb=5.0)),
        red_clon(quitar(1)),
        red_clon(anadir(2, bridge="vmbr1"), cambiar(0, bridge="prod", vlan=20)),
    ],
    ids=["bridge", "vlan", "modelo", "mtu+limite", "quitar", "anadir+vnet"],
)
def test_ca_c4_3_nunca_un_netn_sin_mac_para_una_tarjeta_existente_en_ningun_put(red):
    """RF-C4.3: en TODOS los ``PUT`` del clon cada ``netN`` de una tarjeta que ya existía lleva
    la MAC leída; solo las tarjetas nuevas pueden ir sin ella. El servidor no generó ninguna."""
    m = mundo()
    r = m.crear(clon(m, red))
    assert r.desenlace == Desenlace.OK, r.error
    nuevas = {f"net{t.indice}" for t in red.tarjetas if t.accion.value == "añadir"}
    for datos in m.cluster.puts_de(100):
        for clave in claves_net(datos):
            if clave in nuevas:
                assert "=" not in datos[clave].split(",")[0]
            else:
                assert RE_MAC.search(datos[clave].split(",")[0]), datos
    assert [x for x in m.cluster.macs_generadas if f"net{x[1]}" not in nuevas] == []


def test_ca_c4_3_2_mac_nueva_envia_la_tarjeta_sin_mac_y_proxmox_genera_una_sola():
    m = mundo()
    r = m.crear(clon(m, red_clon(cambiar(0, bridge="vmbr1", mac_nueva=True))))
    (put,) = m.cluster.puts_de_red(100)
    assert put["net0"] == "virtio,bridge=vmbr1"
    assert len(m.cluster.macs_generadas) == 1
    assert m.cluster.macs_generadas[0][:2] == (100, 0)
    assert "red_mac_nueva:net0" in r.avisos
    # La otra tarjeta conserva su MAC.
    assert redes_de(m)["net1"].startswith(f"virtio={mac_clon(100, 1)}")
    assert [f.mac_conservada for f in r.red_final] == [False, True]


def test_ca_c4_3_2_con_mac_nueva_y_cloudinit_el_put_de_red_va_antes_de_cloudinit():
    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1", mac_nueva=True)), cloudinit=ci())
    m.crear(cfg)
    assert orden_escrituras(m) == ["clone", "ajustes", "red", "ci"]


def orden_escrituras(m: MundoC, vmid: int = 100) -> list[str]:
    """Escrituras de la MV con los ``PUT config`` clasificados: ``red``, ``ci`` o ``ajustes``."""
    sal: list[str] = []
    for c in m.cl.llamadas:
        if c.metodo == "GET":
            continue
        if c.metodo == "POST" and c.ruta.endswith("/clone"):
            sal.append("clone")
        elif c.metodo == "PUT" and c.ruta.endswith(f"/qemu/{vmid}/config"):
            claves = set(c.datos or {})
            if claves & {"ciuser", "sshkeys", "cipassword", "nameserver", "searchdomain"} or any(
                k.startswith("ipconfig") for k in claves
            ):
                sal.append("ci")
            elif claves_net(c.datos or {}) or "delete" in claves:
                sal.append("red")
            else:
                sal.append("ajustes")
        elif c.metodo == "POST" and c.ruta.endswith("/status/start"):
            sal.append("start")
    return sal


def test_ca_c4_3_3_si_el_get_de_la_config_del_clon_falla_no_hay_put_de_red_y_queda_parcial():
    """CA-C4.3.3 / V-C21: no se escribe nada de red (no se perdería la MAC) y no se enciende."""
    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1")), encender=True)
    m.cl.regla("GET", r"/qemu/100/config$", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500"))
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.RED_CONFIG_ILEGIBLE
    assert not m.cluster.puts_de_red(100)
    assert not m.cluster.llamadas_a("POST", r"/status/start")
    assert "ajuste_pendiente:red" in r.avisos


def test_ca_c4_3_3_el_get_de_la_config_del_clon_con_403_tambien_deja_parcial_sin_put_de_red():
    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1")))
    m.cl.regla("GET", r"/qemu/100/config$", err_403("/vms/100"))
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert not m.cluster.puts_de_red(100)


def test_ca_c4_3_4_cambiar_a_e1000_con_mtu_fijada_envia_sin_mtu_y_avisa():
    m = mundo()
    r = m.crear(clon(m, red_clon(cambiar(0, modelo="e1000", mtu=1400))))
    (put,) = m.cluster.puts_de_red(100)
    assert put["net0"] == f"e1000={mac_clon(100, 0)},bridge=vmbr0"
    assert "red_mtu_ignorada:net0" in r.avisos


def test_ca_c4_3_5_todas_las_tarjetas_modificadas_viajan_en_una_sola_peticion():
    m = mundo()
    m.crear(
        clon(m, red_clon(cambiar(0, bridge="vmbr1"), cambiar(1, vlan=7), anadir(2, bridge="vmbr9")))
    )
    puts = m.cluster.puts_de_red(100)
    assert len(puts) == 1
    assert set(claves_net(puts[0])) == {"net0", "net1", "net2"}


def test_ca_c4_3_6_el_put_lleva_el_digest_de_la_config_del_clon():
    m = mundo()
    m.crear(clon(m, red_clon(cambiar(0, bridge="vmbr1"))))
    (put,) = m.cluster.puts_de_red(100)
    assert put["digest"] == "d1"  # el que dejó el PUT de ajustes anterior (config releída)


def _gets(caduca: int) -> tuple[MundoC, object]:
    m = mundo()
    m.cluster.digest_caduca = caduca
    r = m.crear(clon(m, red_clon(cambiar(0, bridge="vmbr1"), cambiar(1, vlan=9)), encender=True))
    return m, r


def test_ca_c4_3_6_ante_un_digest_caducado_se_relee_una_vez_y_se_reintenta_con_el_nuevo():
    base, _ = _gets(0)
    m, r = _gets(1)
    assert r.desenlace == Desenlace.OK, r.error
    puts = m.cluster.puts_de_red(100)
    assert len(puts) == 2
    assert puts[0]["digest"] != puts[1]["digest"]
    assert puts[1]["digest"] == "dotro1"  # el digest que el servidor tenía al releer
    assert m.cluster.gets_config(100) == base.cluster.gets_config(100) + 1
    # Resultado final correcto y sin MAC adicional.
    assert redes_de(m)["net0"] == f"virtio={mac_clon(100, 0)},bridge=vmbr1"
    assert redes_de(m)["net1"] == f"virtio={mac_clon(100, 1)},bridge=vmbr0,tag=9"
    assert not m.cluster.macs_generadas
    assert m.cluster.llamadas_a("POST", r"/status/start")


def test_ca_c4_3_6_si_el_digest_caduca_dos_veces_es_red_config_cambiada_sin_tercer_intento():
    base, _ = _gets(0)
    m, r = _gets(2)
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.RED_CONFIG_CAMBIADA
    assert len(m.cluster.puts_de_red(100)) == 2  # un intento y un solo reintento
    assert m.cluster.gets_config(100) == base.cluster.gets_config(100) + 1  # releída una sola vez
    assert not m.cluster.llamadas_a("POST", r"/status/start")
    assert "ajuste_pendiente:red" in r.avisos
    assert redes_de(m)["net0"].endswith("bridge=vmbr0")  # no se aplicó nada


# --- RF-C4.4: añadir y quitar con su ipconfigN ---------------------------------------------------


def test_ca_c4_4_1_quitar_net1_con_ipconfig1_borra_las_dos_y_no_queda_huerfana():
    m = mundo(extra={"ipconfig1": "ip=dhcp"})
    r = m.crear(clon(m, red_clon(quitar(1))))
    assert r.desenlace == Desenlace.OK, r.error
    (put,) = m.cluster.puts_de_red(100)
    assert put["delete"] == "net1,ipconfig1"
    cfg = m.cluster.vms[100]["config"]
    assert "net1" not in cfg and "ipconfig1" not in cfg and "net0" in cfg
    assert [(f.indice, f.accion.value) for f in r.red_final if f.indice == 1] == [(1, "quitar")]


def test_ca_c4_4_2_quitar_net1_sin_ipconfig1_solo_borra_net1():
    m = mundo(extra={"ipconfig0": "ip=dhcp"})
    m.crear(clon(m, red_clon(quitar(1))))
    (put,) = m.cluster.puts_de_red(100)
    assert put["delete"] == "net1"
    assert "ipconfig0" in m.cluster.vms[100]["config"]


def test_cl_c13_con_net0_y_net2_quitar_net2_borra_solo_net2():
    m = mundo(redes=1, extra={"net2": "virtio=AA:BB:CC:DD:EE:02,bridge=vmbr0"})
    m.crear(clon(m, red_clon(quitar(2))))
    (put,) = m.cluster.puts_de_red(100)
    assert put["delete"] == "net2"
    assert set(redes_de(m)) == {"net0"}


def test_ca_c4_4_3_una_tarjeta_anadida_toma_el_indice_que_pide_y_proxmox_genera_su_mac():
    m = mundo(redes=1, extra={"net2": "virtio=AA:BB:CC:DD:EE:02,bridge=vmbr0"})
    r = m.crear(clon(m, red_clon(anadir(1, bridge="prod", vlan=5))))
    assert r.desenlace == Desenlace.OK, r.error
    (put,) = m.cluster.puts_de_red(100)
    assert put["net1"] == "virtio,bridge=prod,tag=5"
    assert [i for _v, i, _m in m.cluster.macs_generadas] == [1]
    assert RE_MAC.search(redes_de(m)["net1"])
    assert [(f.indice, f.accion.value) for f in r.red_final if f.indice == 1] == [(1, "añadir")]


def test_ca_c4_4_anadir_sobre_un_indice_ocupado_por_otra_red_no_escribe_y_queda_parcial():
    """CL-C16 / RED_PLANTILLA_CAMBIADA: la plantilla cambió desde que se preparó el lote."""
    m = mundo()
    r = m.crear(clon(m, red_clon(anadir(1, bridge="prod")), encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.RED_PLANTILLA_CAMBIADA
    assert not m.cluster.puts_de_red(100)
    assert redes_de(m)["net1"] == f"virtio={mac_clon(100, 1)},bridge=vmbr0"
    assert not m.cluster.llamadas_a("POST", r"/status/start")


def test_ca_c4_4_quitar_todas_las_tarjetas_se_permite_y_deja_la_maquina_sin_net():
    m = mundo()
    r = m.crear(clon(m, red_clon(quitar(0), quitar(1))))
    assert r.desenlace == Desenlace.OK
    assert redes_de(m) == {}
    (put,) = m.cluster.puts_de_red(100)
    assert put["delete"] == "net0,net1"


# --- RF-C4.7: interacción con cloud-init ---------------------------------------------------------


def test_ca_c4_7_3_el_put_de_red_precede_al_de_cloudinit_en_el_registro():
    m = mundo()
    m.crear(clon(m, red_clon(cambiar(0, bridge="vmbr1")), cloudinit=ci()))
    orden = orden_escrituras(m)
    assert orden.index("red") < orden.index("ci")


def test_ca_c4_7_1_la_tarjeta_quitada_no_emite_su_ipconfig_en_cloudinit():
    m = mundo(extra={"ipconfig1": "ip=dhcp"})
    cfg = clon(m, red_clon(quitar(1)), cloudinit=ci())
    m.crear(cfg)
    ci_puts = [d for d in m.cluster.puts_de(100) if "ciuser" in d]
    assert ci_puts and "ipconfig1" not in ci_puts[0]
    assert "ipconfig1" not in m.cluster.vms[100]["config"]


def test_ca_c4_4_7_tarjeta_anadida_con_ip_fija_existe_antes_de_escribir_su_ipconfig():
    m = mundo()
    cfg = clon(m, red_clon(anadir(2, bridge="vmbr1")))
    cloudinit = ci(
        tarjetas=(
            TarjetaCloudInit(0, ModoTarjeta.DHCP),
            TarjetaCloudInit(2, ModoTarjeta.FIJA, "10.0.0.60/24", False, "10.0.0.1"),
        )
    )
    r = m.crear(dataclasses.replace(cfg, cloudinit=cloudinit))
    assert r.desenlace == Desenlace.OK, r.error
    orden = orden_escrituras(m)
    assert orden.index("red") < orden.index("ci")
    ci_put = next(d for d in m.cluster.puts_de(100) if "ciuser" in d)
    assert ci_put["ipconfig2"].startswith("ip=10.0.0.60/24")
    assert "net2" in m.cluster.vms[100]["config"]


def test_ca_c4_7_2_una_tarjeta_anadida_sin_configurar_en_cloudinit_no_emite_su_ipconfig():
    m = mundo()
    cfg = clon(m, red_clon(anadir(2, bridge="vmbr1")), cloudinit=ci())
    m.crear(cfg)
    ci_put = next(d for d in m.cluster.puts_de(100) if "ciuser" in d)
    assert "ipconfig2" not in ci_put


def test_ca_c4_7_4_un_clon_sin_unidad_cloudinit_reescribe_la_red_sin_escribir_ci():
    m = mundo(extra={"ide2": None})
    r = m.crear(clon(m, red_clon(cambiar(0, bridge="vmbr1"))))
    assert r.desenlace == Desenlace.OK, r.error
    assert "ide2" not in m.cluster.plantillas[9000]["config"]
    claves = {k for d in m.cluster.puts_de(100) for k in d}
    assert not {k for k in claves if k.startswith(("ci", "ipconfig"))}
    assert redes_de(m)["net0"].endswith("bridge=vmbr1")


# --- RF-C4.5, RF-C2.5: errores 403 de SDN.Use ----------------------------------------------------


def test_ca_c4_5_1_un_403_de_sdn_use_al_reescribir_deja_parcial_y_nombra_tarjeta_y_red():
    from proxlaunch.interfaz.textos_c import texto_error_c

    m = mundo(extra={"net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr9"})
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1")), encender=True)
    fallar_put(m.cl, "net0", err_403("/sdn/zones/localnetwork/vmbr9"))
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["red"] == "vmbr9" and r.error.params["zona"] == "localnetwork"
    texto = texto_error_c(r.error)
    assert texto and "SDN.Use" in texto and "vmbr9" in texto
    assert r.error.params["tarjeta"] == "net0"
    assert "net0" in texto
    assert not m.cluster.llamadas_a("POST", r"/status/start")
    assert "ajuste_pendiente:red" in r.avisos


def test_ca_c4_5_2_un_403_durante_el_post_clone_explica_que_la_plantilla_usa_una_red_sin_permiso():
    from proxlaunch.interfaz.textos_c import texto_error_c

    m = mundo(extra={"net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr9"})
    m.cl.regla("POST", r"/qemu/9000/clone$", err_403("/sdn/zones/localnetwork/vmbr9"))
    r = m.crear(m.cfg())
    assert r.desenlace != Desenlace.OK
    assert r.error.params["lado"] == "plantilla"
    assert r.error.params["red"] == "vmbr9"
    texto = texto_error_c(r.error)
    assert texto and "plantilla" in texto.lower() and "vmbr9" in texto
    assert 100 not in m.cl.vms  # el clon no existe


def test_ca_c4_5_3_un_403_que_no_es_de_sdn_use_no_se_anota_como_de_sdn():
    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1")))
    fallar_put(
        m.cl,
        "net0",
        ErrorProxLaunch(
            CodigoError.PERMISO_INSUFICIENTE,
            {"ruta": "/vms/100", "privilegio": "VM.Config.Network"},
        ),
    )
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert "zona" not in r.error.params and "lado" not in r.error.params
    assert r.error.params["privilegio"] == "VM.Config.Network"


def test_ca_c2_5_3_un_403_al_crear_con_una_vnet_nombra_vnet_zona_y_privilegio_y_no_crea_nada():
    from proxlaunch.interfaz.textos_c import texto_error_c

    m = mundo()
    m.cl.regla("POST", r"/nodes/pve1/qemu$", err_403("/sdn/zones/z1/prod"))
    cfg = cfg_base(redes=[InterfazRed("prod")])
    r = m.crear(cfg)
    assert r.desenlace != Desenlace.OK
    assert (r.error.params["zona"], r.error.params["red"]) == ("z1", "prod")
    assert r.error.params["lado"] == "nueva"
    texto = texto_error_c(r.error)
    assert texto and "prod" in texto and "z1" in texto and "SDN.Use" in texto
    assert 100 not in m.cl.vms


def test_ca_c2_1_2_crear_con_la_vnet_envia_bridge_con_su_nombre_y_nada_nuevo():
    m = mundo()
    r = m.crear(cfg_base(redes=[InterfazRed("prod", vlan=100)]))
    assert r.desenlace == Desenlace.OK, r.error
    (post,) = [c.datos for c in m.cl.llamadas if c.metodo == "POST" and c.ruta.endswith("/qemu")]
    assert post["net0"] == "virtio,bridge=prod,tag=100"
    assert not {k for k in post if k.startswith("net")} - {"net0"}


# --- RF-C4.8, RF-C4.9: reintento e informe -------------------------------------------------------


def test_ca_c4_8_1_un_put_fallido_y_reintentado_deja_la_config_esperada_sin_mac_adicional():
    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1", mac_nueva=True), cambiar(1, vlan=3)))
    fallar_put(m.cl, "net0", error_http(500, "boom"), veces=1)
    r = m.crear(dataclasses.replace(cfg, encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert "ajuste_pendiente:red" in r.avisos
    assert not m.cluster.macs_generadas  # el PUT fallido no aplicó nada
    r2 = m.reintentar(dataclasses.replace(cfg, encender=True))
    assert r2.desenlace == Desenlace.OK, r2.error
    assert len(m.cluster.macs_generadas) == 1  # exactamente una MAC nueva en total
    assert redes_de(m)["net0"].startswith("virtio=DE:AD:BE:EF:00:01,bridge=vmbr1")
    assert redes_de(m)["net1"] == f"virtio={mac_clon(100, 1)},bridge=vmbr0,tag=3"
    assert m.cluster.llamadas_a("POST", r"/status/start")


def test_ca_c4_8_1_reintentar_con_la_red_ya_aplicada_no_vuelve_a_escribirla():
    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1", mac_nueva=True)))
    m.crear(cfg)
    puts_antes = len(m.cluster.puts_de_red(100))
    m.reintentar(cfg)
    assert len(m.cluster.puts_de_red(100)) == puts_antes
    assert len(m.cluster.macs_generadas) == 1


def test_ca_c4_8_1_mac_nueva_sin_cambio_de_red_no_genera_otra_mac_al_reintentar_ajustes():
    m = mundo()
    cfg = dataclasses.replace(
        clon(m, red_clon(cambiar(0, mac_nueva=True))), cloudinit=ci(), encender=True
    )
    fallar_put(m.cl, "ciuser", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500"), veces=1)
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert len(m.cluster.macs_generadas) == 1
    m.reintentar(cfg)
    assert len(m.cluster.macs_generadas) == 1  # hoy son 2: la MAC cambió tras el cloud-init


def test_ca_c4_9_1_sin_direcciones_libres_en_la_zona_es_red_sin_direcciones_y_parcial():
    from proxlaunch.interfaz.textos_c import texto_error_c

    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="prod")), encender=True)
    fallar_put(
        m.cl,
        "net0",
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500: can't find any free ip in zone z1"),
    )
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.RED_SIN_DIRECCIONES
    assert "direcciones libres" in texto_error_c(r.error)
    assert not m.cluster.llamadas_a("POST", r"/status/start")


def test_cl_c16_un_put_de_red_parcial_es_una_sola_peticion_y_todo_o_nada():
    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1"), cambiar(1, bridge="vmbr9")))
    fallar_put(m.cl, "net1", error_http(500, "boom"))
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    intentos = [
        c for c in m.cl.llamadas_a("PUT", r"/qemu/100/config$") if claves_net(c.datos or {})
    ]
    assert len(intentos) == 1
    assert redes_de(m)["net0"].endswith("bridge=vmbr0")  # ninguna tarjeta cambió


def test_cl_c20_si_la_red_ya_se_aplico_pero_se_perdio_la_respuesta_el_reintento_es_idempotente():
    """El ``PUT`` llegó (la config cambió) pero el cliente vio un error: reintentar relee y no
    repite la escritura ni cambia la MAC."""
    m = mundo()
    cfg = clon(m, red_clon(cambiar(0, bridge="vmbr1", mac_nueva=True), cambiar(1, vlan=3)))
    original = m.cluster._put
    estado = {"n": 0}

    def put_con_respuesta_perdida(ll, nodo_, vmid, que):
        original(ll, nodo_, vmid, que)  # aplica de verdad
        if que == "config" and any(k.startswith("net") for k in (ll.datos or {})):
            estado["n"] += 1
            if estado["n"] == 1:
                raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500: connection reset")

    m.cluster._put = put_con_respuesta_perdida  # type: ignore[method-assign]
    r = m.crear(cfg)
    final = redes_de(m)
    assert final["net0"].endswith("bridge=vmbr1") and final["net1"].endswith("tag=3")
    assert len(m.cluster.macs_generadas) == 1
    if r.desenlace == Desenlace.PARCIAL:
        m.reintentar(cfg)
        assert len(m.cluster.macs_generadas) == 1
        assert redes_de(m) == final


# --- Lotes: cada copia con su propia MAC ----------------------------------------------------------


def test_ca_c4_3_un_lote_de_3_copias_reenvia_la_mac_de_cada_clon_y_ninguna_sale_sin_mac():
    m = mundo()
    plan, libro = m.lote(3, None, red_clon=red_clon(cambiar(0, bridge="vmbr1")))
    assert set(m.estados(libro).values()) == {EstadoMV.OK}
    for vmid in (100, 101, 102):
        (put,) = m.cluster.puts_de_red(vmid)
        assert put["net0"] == f"virtio={mac_clon(vmid, 0)},bridge=vmbr1"
        assert redes_de(m, vmid)["net1"].startswith(f"virtio={mac_clon(vmid, 1)}")
    assert not m.cluster.macs_generadas


def test_cl_c19_si_el_put_de_red_falla_en_una_copia_las_demas_quedan_bien_y_esa_parcial():
    m = mundo()
    fallar_put(m.cl, "net0", error_http(500, "boom"), vmid=101)
    plan, libro = m.lote(3, None, red_clon=red_clon(cambiar(0, bridge="vmbr1")))
    assert m.estados(libro) == {100: EstadoMV.OK, 101: EstadoMV.PARCIAL, 102: EstadoMV.OK}
    for vmid in (100, 102):
        assert redes_de(m, vmid)["net0"].endswith("bridge=vmbr1")
    assert redes_de(m, 101)["net0"].endswith("bridge=vmbr0")


# --- RF-C2.1/RF-C0.2: no regresión y descubrimiento ---------------------------------------------

ESCENARIOS_EJECUCION = [
    "vacio",
    "vacio_encender",
    "iso",
    "importar_con_resize",
    "clon_sin_ajustes",
    "clon_con_ajustes",
    "lote_3_encender",
    "reintento_de_ajustes",
]


@pytest.mark.parametrize("nombre", ESCENARIOS_EJECUCION)
def test_rf_c0_2_sin_opciones_c_la_secuencia_de_peticiones_es_identica_a_la_de_0_7_0(nombre):
    """Golden: método, ruta, consulta y cuerpo (bytes) de todas las peticiones, en orden."""
    esperado = g.golden()["escenarios"][nombre]
    actual = json.loads(json.dumps(g.actuales()[nombre]))
    assert actual == esperado


@pytest.mark.parametrize("nombre", ESCENARIOS_EJECUCION)
def test_rf_c0_2_sin_opciones_c_ninguna_peticion_de_red_ni_de_firewall_nueva(nombre):
    for metodo, ruta, cuerpo in g.actuales()[nombre]:
        assert "firewall" not in ruta and "/sdn" not in ruta
        assert "delete=" not in cuerpo and "firewall=" not in cuerpo
        if metodo == "PUT" and ruta.endswith("/config"):
            assert not re.search(r"(?:^|&)net\d+=", cuerpo)


# Las 12 peticiones de 0.7.0 para descubrir un clúster de 3 nodos (git tag v0.7.0).
LECTURAS_070 = sorted(
    [
        ("GET", "/access/permissions", None),
        ("GET", "/cluster/nextid", None),
        ("GET", "/cluster/options", None),
        ("GET", "/cluster/status", None),
        ("GET", "/nodes", None),
        ("GET", "/pools", None),
        *[("GET", f"/nodes/pve{i}/network", None) for i in (1, 2, 3)],
        *[("GET", f"/nodes/pve{i}/storage", None) for i in (1, 2, 3)],
    ],
    key=str,
)


def _transporte_descubrimiento(network=None) -> TransporteFalso:
    t = TransporteFalso()
    rutas_inventario(t)
    t.en("GET", "/cluster/options", {})
    t.en("GET", "/pools", [])
    if network is not None:
        for n in ("pve1", "pve2", "pve3"):
            t.en("GET", f"/nodes/{n}/network", network)
    return t


def _llamadas(t: TransporteFalso, *, con_any_bridge: bool) -> list[tuple]:
    return sorted(
        (
            (c.metodo, c.ruta, c.params)
            for c in t.llamadas
            if con_any_bridge or (c.params or {}).get("type") != "any_bridge"
        ),
        key=str,
    )


def test_rf_c0_2_el_descubrimiento_conserva_las_lecturas_de_0_7_0_y_solo_suma_any_bridge():
    t = _transporte_descubrimiento()
    inv = descubrir(crear_sesion(t))
    assert _llamadas(t, con_any_bridge=False) == LECTURAS_070
    extra = [c for c in t.llamadas if (c.params or {}).get("type") == "any_bridge"]
    assert sorted(c.ruta for c in extra) == [f"/nodes/pve{i}/network" for i in (1, 2, 3)]
    assert len(t.llamadas) == len(LECTURAS_070) + 3
    assert all(c.metodo == "GET" for c in t.llamadas)
    # Con la respuesta de 0.7.0 (solo interfaces y bridges) no aparece ninguna VNet.
    assert inv.redes_sdn == {"pve1": (), "pve2": (), "pve3": ()}
    assert inv.errores_sdn == {}


def test_ca_c2_1_3_si_any_bridge_falla_el_inventario_es_el_de_0_7_0_con_el_aviso_de_sdn():
    t = _transporte_descubrimiento()
    normal = descubrir(crear_sesion(t))

    def red(ll):
        if (ll.params or {}).get("type") == "any_bridge":
            raise error_http(403, "Permission check failed")
        return dato("9.2", "network.json")

    t2 = _transporte_descubrimiento()
    for n in ("pve1", "pve2", "pve3"):
        t2.en("GET", f"/nodes/{n}/network", red)
    inv = descubrir(crear_sesion(t2))
    assert inv.bridges == normal.bridges
    assert inv.storages == normal.storages
    assert inv.topologia == normal.topologia
    assert inv.errores_por_nodo == {}  # el fallo de SDN no marca al nodo como caído
    assert set(inv.errores_sdn) == {"pve1", "pve2", "pve3"}
    assert inv.redes_sdn == {}


def test_ca_c2_1_1_una_respuesta_any_bridge_con_bridges_y_vnets_solo_deja_las_vnets():
    entradas = [
        {"iface": "vmbr0", "type": "bridge", "bridge_vlan_aware": 1},
        {"iface": "vmbr1", "type": "OVSBridge"},
        {"iface": "prod", "type": "vnet", "comments": "Producción", "vlanaware": 1},
        {"iface": "lab", "type": "vnet"},
    ]

    def red(ll):
        return (
            entradas
            if (ll.params or {}).get("type") == "any_bridge"
            else dato("9.2", "network.json")
        )

    t = _transporte_descubrimiento()
    for n in ("pve1", "pve2", "pve3"):
        t.en("GET", f"/nodes/{n}/network", red)
    inv = descubrir(crear_sesion(t))
    vnets = inv.redes_sdn["pve1"]
    assert [(v.nombre, v.alias, v.vlan_aware) for v in vnets] == [
        ("prod", "Producción", True),
        ("lab", None, False),
    ]
    assert {b.nombre for b in inv.bridges["pve1"]} == {"vmbr0", "vmbr1"}


def test_ca_c2_1_5_los_nombres_y_alias_del_servidor_se_sanean_y_solo_un_iface_valido_pasa():
    entradas = [
        {"iface": "prod", "type": "vnet", "comments": "<b>Prod</b>\x00\x1b[31m rojo\n" + "x" * 200},
        {"iface": "mala red", "type": "vnet"},
        {"iface": "a,bridge=x", "type": "vnet"},
        {"iface": "<script>", "type": "vnet"},
        {"iface": "x" * 41, "type": "vnet"},
        {"iface": 5, "type": "vnet"},
        {"iface": "ok-1", "type": "vnet", "comments": 42},
        "no soy un dict",
        {"iface": "otro", "type": "eth"},
    ]
    t = TransporteFalso().en("GET", "/nodes/pve1/network", lambda ll: entradas)
    sesion = crear_sesion(t)
    vnets = sesion.cliente.redes_any_bridge("pve1")
    assert [v.nombre for v in vnets] == ["prod", "ok-1"]
    alias = vnets[0].alias
    assert alias is not None and len(alias) <= 64
    assert not re.search(r"[\x00-\x1f\x7f]|<|>", alias)
    assert vnets[1].alias is None


def test_ca_c2_1_cuando_la_respuesta_no_es_una_lista_no_hay_vnets_ni_excepcion():
    for cuerpo in (None, {}, "x", 7):
        t = TransporteFalso().en("GET", "/nodes/pve1/network", lambda ll, c=cuerpo: c)
        assert crear_sesion(t).cliente.redes_any_bridge("pve1") == []


def test_ca_c2_1_6_una_vnet_pendiente_de_aplicar_no_esta_en_la_respuesta_y_no_se_ofrece():
    t = _transporte_descubrimiento()
    for n in ("pve1", "pve2", "pve3"):
        t.en(
            "GET",
            f"/nodes/{n}/network",
            lambda ll: (
                [{"iface": "aplicada", "type": "vnet"}]
                if (ll.params or {}).get("type") == "any_bridge"
                else dato("9.2", "network.json")
            ),
        )
    inv = descubrir(crear_sesion(t))
    assert [v.nombre for v in inv.redes_sdn["pve1"]] == ["aplicada"]


def test_ca_c2_1_sin_type_una_entrada_que_ya_es_interfaz_es_un_bridge_y_la_otra_una_vnet():
    """Supuesto [A]: sin ``type`` se reconoce la VNet por no estar en la lista de interfaces."""
    t = _transporte_descubrimiento()

    def red(ll):
        if (ll.params or {}).get("type") == "any_bridge":
            return [{"iface": "vmbr0"}, {"iface": "soloanybridge"}]
        return dato("9.2", "network.json")

    for n in ("pve1", "pve2", "pve3"):
        t.en("GET", f"/nodes/{n}/network", red)
    inv = descubrir(crear_sesion(t))
    assert [v.nombre for v in inv.redes_sdn["pve1"]] == ["soloanybridge"]


@pytest.mark.parametrize("codigo", [400, 403, 500])
def test_ca_c2_1_3_una_lectura_any_bridge_con_cualquier_error_http_no_rompe_el_descubrimiento(
    codigo,
):
    t = _transporte_descubrimiento()

    def red(ll):
        if (ll.params or {}).get("type") == "any_bridge":
            raise error_http(codigo, "no")
        return dato("9.2", "network.json")

    for n in ("pve1", "pve2", "pve3"):
        t.en("GET", f"/nodes/{n}/network", red)
    inv = descubrir(crear_sesion(t))
    assert inv.errores_por_nodo == {}
    assert {b.nombre for b in inv.bridges["pve1"]} == {"vmbr0", "vmbr1"}
    assert "pve1" in inv.errores_sdn


def test_ca_c2_1_3_un_fallo_inesperado_al_leer_las_vnets_tampoco_rompe_el_descubrimiento():
    t = _transporte_descubrimiento()

    def red(ll):
        if (ll.params or {}).get("type") == "any_bridge":
            raise RuntimeError("fallo raro")
        return dato("9.2", "network.json")

    for n in ("pve1", "pve2", "pve3"):
        t.en("GET", f"/nodes/{n}/network", red)
    inv = descubrir(crear_sesion(t))
    assert inv.errores_sdn["pve1"].codigo == CodigoError.DESCONOCIDO
    assert inv.errores_por_nodo == {}
