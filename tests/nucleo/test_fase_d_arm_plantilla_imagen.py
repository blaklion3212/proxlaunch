"""D2.6.5 (0.9.0): el asistente de plantilla desde imagen cloud en un nodo ARM64.

CA-D2.6.5: en aarch64 no hay IDE, así que la unidad de cloud-init va en ``scsi1`` (no ``ide2``);
el firmware es OVMF, la CPU ``host`` y la consola serie (``vga=serial0``) sustituye a la
``vga=virtio`` del perfil ARM (DT-D9). En x86 nada cambia (golden). El servicio del asistente
pasa la arquitectura del nodo a ``cfg_de_creacion`` y a ``parametros_extra`` (el orquestador lo
corrigió en ``plantilla_imagen/servicio.py``).
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.modelos.vm import Bus, Disco, Firmware
from proxlaunch.nucleo.plantilla_imagen.modelos import FijasPlantilla
from proxlaunch.nucleo.plantilla_imagen.peticion import cfg_de_creacion, parametros_extra

from .apoyo_fase_b_agente import cfg_plantilla, crear_mundo_b2, solicitud
from .apoyo_fase_d import ARM, V_84, V_92, X86, inv_arq

VOLID = "local:import/ubuntu-24.04.qcow2"


def _sol(**kw):
    kw.setdefault("volid_existente", VOLID)
    kw.setdefault("nombre_archivo", "ubuntu-24.04.qcow2")
    from proxlaunch.nucleo.plantilla_imagen.modelos import OrigenImagen

    return solicitud(None, origen=OrigenImagen.YA_IMPORTADA, **kw)


def _mundo(arq=ARM, version=V_92):
    inv = inv_arq({"pve1": arq} if arq else {}, nodos=("pve1",), version=version)
    m = crear_mundo_b2(version=version, inv=inv)
    m.cluster.archivos[("pve1", "local")]["ubuntu-24.04.qcow2"] = 5 * 1024**3 // 10
    return m


# --- Funciones puras ---------------------------------------------------------------------------


def test_ca_d2_6_5_parametros_extra_en_aarch64_usa_scsi1_para_cloud_init_y_nunca_ide():
    extra = parametros_extra(FijasPlantilla(), "local-lvm", arquitectura=Arquitectura.AARCH64)
    assert extra == {
        "scsi1": "local-lvm:cloudinit",
        "serial0": "socket",
        "vga": "serial0",
        "boot": "order=scsi0",
    }
    assert not any(re.fullmatch(r"(ide|sata)\d+", k) for k in extra)


@pytest.mark.parametrize("arq", [Arquitectura.X86_64, Arquitectura.DESCONOCIDA])
def test_ca_d2_6_5_en_x86_o_desconocida_la_unidad_sigue_en_ide2(arq):
    extra = parametros_extra(FijasPlantilla(), "local-lvm", arquitectura=arq)
    assert extra["ide2"] == "local-lvm:cloudinit" and "scsi1" not in extra


def test_ca_d2_6_5_sin_valor_de_arquitectura_se_asume_x86_como_en_0_8_0():
    assert parametros_extra(FijasPlantilla(), "local-lvm") == parametros_extra(
        FijasPlantilla(), "local-lvm", arquitectura=Arquitectura.X86_64
    )


def test_ca_d2_6_5_sin_la_casilla_de_unidad_no_hay_cloud_init_ni_en_arm():
    extra = parametros_extra(
        FijasPlantilla(unidad_cloudinit=False), "local-lvm", arquitectura=Arquitectura.AARCH64
    )
    assert "scsi1" not in extra and "ide2" not in extra


def test_ca_d2_6_5_cfg_de_creacion_en_aarch64_usa_ovmf_host_y_disco_scsi():
    sol = dataclasses.replace(
        _sol(), cfg=cfg_plantilla(firmware=Firmware.SEABIOS, tipo_cpu="x86-64-v3")
    )
    cfg = cfg_de_creacion(sol, VOLID, arquitectura=Arquitectura.AARCH64)
    assert cfg.firmware == Firmware.OVMF and cfg.tipo_cpu == "host"
    assert cfg.discos[0].bus == Bus.SCSI


def test_ca_d2_6_5_cfg_de_creacion_en_x86_no_cambia_firmware_ni_cpu():
    sol = dataclasses.replace(
        _sol(), cfg=cfg_plantilla(firmware=Firmware.SEABIOS, tipo_cpu="x86-64-v3")
    )
    cfg = cfg_de_creacion(sol, VOLID)
    assert cfg.firmware == Firmware.SEABIOS and cfg.tipo_cpu == "x86-64-v3"


# --- El servicio completo -----------------------------------------------------------------------


@pytest.mark.parametrize("version", [V_84, V_92], ids=["8.4", "9.2"])
def test_ca_d2_6_5_el_servicio_en_un_nodo_aarch64_crea_con_scsi1_ovmf_y_serie(version):
    m = _mundo(version=version)
    est = m.ejecutar(_sol())
    assert est.completo, est
    c = m.cluster.cuerpos_post[9100]
    assert c["scsi1"] == "local-lvm:cloudinit"
    assert not [k for k in c if re.fullmatch(r"(ide|sata)\d+", k)]
    assert c["bios"] == "ovmf" and "machine" not in c and "efitype" not in c["efidisk0"]
    assert c["cpu"] == "host" and c["serial0"] == "socket"
    assert c["vga"] == "serial0"  # la consola serie sustituye a la ``vga=virtio`` del perfil ARM
    assert c["boot"] == "order=scsi0" and c["scsi0"].startswith("local-lvm:0,import-from=")
    assert c["agent"] == "1" and c["net0"] == "virtio,bridge=vmbr0"


def test_ca_d2_6_5_el_servicio_en_x86_sigue_usando_ide2_y_sin_cambios():
    m = _mundo(arq=X86)
    assert m.ejecutar(_sol()).completo
    c = m.cluster.cuerpos_post[9100]
    assert c["ide2"] == "local-lvm:cloudinit" and "scsi1" not in c
    assert c["vga"] == "serial0" and "bios" not in c and c["cpu"] == "x86-64-v2-AES"


def test_ca_d2_6_5_con_arquitectura_no_legible_el_servicio_trata_el_nodo_como_x86():
    m = _mundo(arq=None)
    assert m.ejecutar(_sol()).completo
    c = m.cluster.cuerpos_post[9100]
    assert c["ide2"] == "local-lvm:cloudinit" and "scsi1" not in c


def test_ca_d2_6_5_construir_parametros_directo_en_arm_pone_vga_virtio_si_no_hay_consola_serie():
    """Sin ``parametros_extra`` el constructor ARM pone ``vga=virtio``."""
    sol = _sol()
    cfg = cfg_de_creacion(sol, VOLID, arquitectura=Arquitectura.AARCH64)
    cfg = dataclasses.replace(cfg, discos=[Disco("local-lvm", 10)])
    p = construir_parametros(cfg, inv_arq({"pve1": ARM}, nodos=("pve1",)))
    assert p["vga"] == "virtio" and "ide2" not in p
