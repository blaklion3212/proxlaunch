"""Fase B (0.7.0): detección de cloud-init en la ``config`` de una plantilla (RF-B1.1).

Cubre CA-B1.1.1 a CA-B1.1.5, CL-B11 y R-B7 (la detección acepta todos los buses). La función
``info_cloudinit`` es pura y no lanza nunca: el contenido de la config no es de fiar.
"""

from __future__ import annotations

import dataclasses
import random

import pytest

from proxlaunch.nucleo.cloudinit.deteccion import (
    CLAVES_UNIDAD,
    es_windows,
    info_cloudinit,
    interpretar_cicustom,
)
from proxlaunch.nucleo.cloudinit.modelos import INFO_DESCONOCIDA

CENTINELA = "S3cr3t-Prueba!"
UNIDAD = "local-lvm:vm-9000-cloudinit,media=cdrom"


# --- CA-B1.1.1: la unidad se detecta con las tres formas de volumen -----------------------------


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("ide2", "local-lvm:vm-9000-cloudinit,media=cdrom"),
        ("scsi5", "dir:9000/vm-9000-cloudinit.qcow2"),
        ("sata1", "local:cloudinit"),
    ],
)
def test_ca_b1_1_1_los_ejemplos_de_los_requisitos_detectan_la_unidad(clave, valor):
    info = info_cloudinit({clave: valor, "scsi0": "local-lvm:vm-9000-disk-0,size=8G"})
    assert info.unidad is True
    assert info.clave_unidad == clave


@pytest.mark.parametrize("formato", ["raw", "qcow2", "vmdk"])
def test_ca_b1_1_1_la_unidad_admite_los_formatos_de_imagen_en_el_nombre(formato):
    assert info_cloudinit({"ide2": f"dir:9000/vm-9000-cloudinit.{formato}"}).unidad is True


def test_ca_b1_1_1_las_opciones_del_volumen_tras_la_coma_no_cuentan():
    # ``,media=cdrom,size=4M`` va tras la coma; el patrón solo mira el volid.
    assert info_cloudinit({"ide0": "local:cloudinit,media=cdrom,size=4M"}).unidad is True


def test_ca_b1_1_1_la_unidad_sin_numero_de_vmid_tambien_se_detecta():
    assert info_cloudinit({"scsi1": "ceph:cloudinit"}).unidad is True


# --- R-B7: todos los buses; ninguno fuera de su rango --------------------------------------------


def test_r_b7_claves_unidad_cubre_todos_los_buses_y_rangos():
    esperadas = (
        {f"ide{i}" for i in range(4)}
        | {f"sata{i}" for i in range(6)}
        | {f"scsi{i}" for i in range(31)}
        | {f"virtio{i}" for i in range(16)}
    )
    assert set(CLAVES_UNIDAD) == esperadas
    assert len(CLAVES_UNIDAD) == len(esperadas)


@pytest.mark.parametrize("clave", sorted({f"ide{i}" for i in range(4)}
                                         | {f"sata{i}" for i in range(6)}
                                         | {"scsi0", "scsi30"}
                                         | {"virtio0", "virtio15"}))  # fmt: skip
def test_r_b7_la_unidad_se_detecta_en_los_extremos_de_cada_bus(clave):
    info = info_cloudinit({clave: "a:vm-1-cloudinit"})
    assert (info.unidad, info.clave_unidad) == (True, clave)


@pytest.mark.parametrize("clave", ["ide4", "sata6", "scsi31", "virtio16", "net0", "efidisk0"])
def test_r_b7_una_clave_fuera_de_los_buses_o_del_rango_no_detecta_unidad(clave):
    assert info_cloudinit({clave: "a:vm-1-cloudinit"}).unidad is False


# --- CA-B1.1.2 y CA-B1.1.3: lo que NO es una unidad ----------------------------------------------


def test_ca_b1_1_2_solo_disco_y_cd_rom_iso_no_detecta_unidad():
    info = info_cloudinit(
        {"scsi0": "local-lvm:vm-9000-disk-0,size=8G", "ide2": "local:iso/x.iso,media=cdrom"}
    )
    assert info.unidad is False
    assert info.clave_unidad is None


def test_ca_b1_1_3_el_nombre_con_cloudinit_en_otro_punto_no_cuenta():
    for valor in (
        "local:vm-1-cloudinit-backup",
        "local:iso/cloudinit.iso,media=cdrom",
        "local:vm-1-cloudinit.iso",
        "local:cloudinit-extra",
        "local:micloudinit",
    ):
        assert info_cloudinit({"ide2": valor}).unidad is False, valor


def test_ca_b1_1_3_una_config_vacia_pero_legible_es_sin_unidad_no_desconocida():
    info = info_cloudinit({})
    assert info.unidad is False  # False (se leyó y no hay) != None (no se pudo leer)


def test_ca_b1_1_unidad_gana_la_primera_en_orden_de_buses():
    info = info_cloudinit({"scsi3": "a:vm-1-cloudinit", "ide2": UNIDAD})
    assert info.clave_unidad == "ide2"


# --- CA-B1.1.4 y CL-B11: configuración no legible ------------------------------------------------


@pytest.mark.parametrize("config", [None, "no es un mapa", 42, ["ide2", UNIDAD], b"x"])
def test_ca_b1_1_4_una_config_no_legible_da_estado_desconocido(config):
    info = info_cloudinit(config)
    assert info == INFO_DESCONOCIDA
    assert info.unidad is None  # «desconocido»: V-B20 avisa y no bloquea


def test_cl_b11_la_info_desconocida_no_es_windows_ni_tiene_nada_heredado():
    assert INFO_DESCONOCIDA.unidad is None
    assert INFO_DESCONOCIDA.es_windows is False
    assert INFO_DESCONOCIDA.heredados == {}
    assert INFO_DESCONOCIDA.tarjetas == ()
    assert INFO_DESCONOCIDA.cicustom is None


def test_ca_b1_1_4_info_cloudinit_nunca_lanza_con_contenido_hostil():
    rng = random.Random(20261122)
    valores = [None, "", "x" * 5000, 7, True, 1.5, b"b", [], {}, ["a"], {"a": 1}, "\x00\n\r", "🙂"]
    claves = [
        "ide2", "scsi0", "net0", "net99", "net-1", "netX", "agent", "ostype", "cicustom",
        "ciuser", "ipconfig0", "ipconfig99", "ipconfigx", "nameserver", "ciupgrade", 5, None,
    ]  # fmt: skip
    for _ in range(300):
        config = {rng.choice(claves): rng.choice(valores) for _ in range(rng.randint(0, 8))}
        info = info_cloudinit(config)  # no debe lanzar
        assert info.unidad in (True, False, None)


# --- CA-B1.1.5 y CL-B11: ostype -------------------------------------------------------------------


@pytest.mark.parametrize("ostype", ["l26", "l24", "other", "solaris", "", None])
def test_ca_b1_1_5_los_ostype_no_windows(ostype):
    assert es_windows(ostype) is False
    config = {"ide2": UNIDAD, **({"ostype": ostype} if ostype is not None else {})}
    assert info_cloudinit(config).es_windows is False


@pytest.mark.parametrize(
    "ostype", ["wxp", "w2k", "w2k3", "w2k8", "wvista", "win7", "win8", "win10", "win11"]
)
def test_ca_b1_1_5_los_ostype_windows(ostype):
    assert es_windows(ostype) is True
    info = info_cloudinit({"ide2": UNIDAD, "ostype": ostype})
    assert info.es_windows is True
    assert info.ostype == ostype


def test_cl_b11_sin_ostype_en_la_config_se_trata_como_no_windows():
    info = info_cloudinit({"ide2": UNIDAD})
    assert info.es_windows is False
    assert info.ostype is None


# --- RF-B1.1: el resto de lo que se lee ----------------------------------------------------------


def test_rf_b1_1_lee_tarjetas_mac_y_valores_heredados():
    info = info_cloudinit(
        {
            "ide2": UNIDAD,
            "net0": "virtio=BC:24:11:AA:BB:CC,bridge=vmbr0,firewall=1",
            "net2": "e1000=BC:24:11:00:00:01,bridge=vmbr1",
            "ciuser": "ubuntu",
            "ipconfig0": "ip=dhcp",
            "ipconfig2": "ip=10.0.0.5/24,gw=10.0.0.1",
            "nameserver": "1.1.1.1",
            "searchdomain": "lab.local",
            "ciupgrade": "0",
        }
    )
    assert info.tarjetas == (0, 2)
    assert info.mac_net0 == "BC:24:11:AA:BB:CC"
    assert info.heredados == {
        "ciuser": "ubuntu",
        "ipconfig0": "ip=dhcp",
        "ipconfig2": "ip=10.0.0.5/24,gw=10.0.0.1",
        "nameserver": "1.1.1.1",
        "searchdomain": "lab.local",
        "ciupgrade": "0",
    }


def test_rf_b1_1_la_contrasena_enmascarada_nunca_se_lee_ni_se_conserva():
    info = info_cloudinit({"ide2": UNIDAD, "cipassword": "**********", "ciuser": "u"})
    assert "cipassword" not in info.heredados
    assert "**********" not in repr(info)
    # Ni siquiera un valor real que escapara del servidor se arrastra a la info.
    info2 = info_cloudinit({"ide2": UNIDAD, "cipassword": CENTINELA})
    assert CENTINELA not in repr(info2)
    assert CENTINELA not in repr(dataclasses.asdict(info2))


@pytest.mark.parametrize(
    ("agent", "esperado"),
    [
        ("1", True),
        ("enabled=1", True),
        ("1,fstrim_cloned_disks=1", True),
        ("enabled=1,type=virtio", True),
        ("0", False),
        ("enabled=0", False),
        ("fstrim_cloned_disks=1", False),
        ("", False),
    ],
)
def test_rf_b1_1_agent_habilitado_en_sus_formas(agent, esperado):
    assert info_cloudinit({"ide2": UNIDAD, "agent": agent}).agente is esperado


def test_rf_b1_1_sin_agent_en_la_config_no_esta_habilitado():
    assert info_cloudinit({"ide2": UNIDAD}).agente is False


def test_rf_b1_1_net_fuera_de_rango_o_mal_formado_no_cuenta_como_tarjeta():
    info = info_cloudinit(
        {"ide2": UNIDAD, "net0": "virtio", "net32": "x", "net99": "x", "netx": "x"}
    )
    assert info.tarjetas == (0,)


def test_rf_b1_1_los_valores_heredados_se_recortan_a_un_tope():
    info = info_cloudinit({"ide2": UNIDAD, "ciuser": "u" * 5000})
    assert 0 < len(info.heredados["ciuser"]) <= 512


# --- cicustom heredado ---------------------------------------------------------------------------


def test_rf_b1_1_cicustom_interpretable_se_separa_por_tipos():
    info = info_cloudinit(
        {"ide2": UNIDAD, "cicustom": "user=local:snippets/a.yaml,vendor=nfs:snippets/v.yaml"}
    )
    assert info.cicustom is not None and info.cicustom.interpretable is True
    assert dict(info.cicustom.tipos) == {
        "user": "local:snippets/a.yaml",
        "vendor": "nfs:snippets/v.yaml",
    }


def test_rf_b1_1_sin_cicustom_en_la_plantilla_es_none():
    assert info_cloudinit({"ide2": UNIDAD}).cicustom is None


@pytest.mark.parametrize(
    "valor",
    ["raro", "user=", "=local:snippets/a.yaml", "otro=local:snippets/a.yaml", "user=a,user=b"],
)
def test_ca_b4_5_4_un_cicustom_no_interpretable_se_marca_y_no_deja_tipos(valor):
    heredado = interpretar_cicustom(valor)
    assert heredado.interpretable is False
    assert dict(heredado.tipos) == {}
    info = info_cloudinit({"ide2": UNIDAD, "cicustom": valor})
    assert info.cicustom is not None and info.cicustom.interpretable is False
