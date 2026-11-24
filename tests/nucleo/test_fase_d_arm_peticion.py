"""D2.6 y D2.7 (0.9.0): perfil de hardware aarch64 en la petición y opciones no válidas en ARM.

CA-D2.6.1–6, CA-D2.7.3 (núcleo), CA-D2.7.4/5 (núcleo) y CA-D2.11.1–3. ARM es experimental: la
rama ARM de ``construir_parametros`` solo se usa con un nodo ``aarch64``; el golden x86 queda en
``test_fase_d_golden``. La configuración llega al constructor ya adaptada por el planificador
(DT-D8): casi todo se prueba por el camino completo, ``plan_de`` + ``construir_parametros``.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import pytest

import proxlaunch
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.arquitectura.perfil import adaptar_a_arquitectura, ranura_cdrom_aarch64
from proxlaunch.nucleo.arquitectura.validacion import validar_arquitectura
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.modelos.cpu import (
    TIPO_CPU_ARM_DEFECTO,
    TIPO_CPU_X86_DEFECTO,
    TIPOS_CPU_ARM,
    TIPOS_CPU_X86,
    es_cpu_personalizada,
    es_cpu_solo_x86,
    tipo_cpu_por_defecto,
)
from proxlaunch.nucleo.modelos.origen import TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
    ModeloRed,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_fase_a import def_lote, plan_de
from .apoyo_fase_d import ARM, V_84, V_92, X86, banco_d, cfg_arm, inv_arq
from .apoyo_lote import modelo_cpu_api
from .apoyo_mvp4 import VOLID_VIRTIO, cfg_import, cfg_iso

RAIZ_SRC = Path(proxlaunch.__file__).parent


def _plan(cfg: ConfiguracionVM, n: int = 1, *, version=V_92, arq=ARM, cpus=None):
    """Plan sobre un nodo pve1; ``cpus`` = modelos que el servidor lista en ``capabilities``."""
    banco = banco_d({"pve1": arq}, version=version)
    if cpus is not None:
        banco.cluster.cpus_api["pve1"] = [
            modelo_cpu_api(c, custom=c.startswith("custom-")) for c in cpus
        ]
    plan = plan_de(banco, def_lote(n, plantilla_vm=cfg))
    assert not plan.bloqueado, [(p.regla, p.params) for p in plan.problemas]
    return plan, banco


def _params(cfg: ConfiguracionVM, **kw: Any) -> dict[str, str]:
    plan, banco = _plan(cfg, **kw)
    return construir_parametros(plan.elementos[0].cfg, banco.inv)


def _iso_x86(**cambios: Any) -> ConfiguracionVM:
    """ISO con los valores x86 de siempre (SeaBIOS, ``x86-64-v2-AES``, disco SCSI)."""
    return dataclasses.replace(cfg_iso(), **cambios)


def _claves_x86(params: dict[str, str]) -> list[str]:
    return [k for k in params if re.fullmatch(r"(ide|sata)\d+", k)]


# --- CA-D2.6.1: valores por defecto con ISO -------------------------------------------------------


def test_ca_d2_6_1_iso_por_defecto_en_aarch64_lleva_el_perfil_adaptado():
    p = _params(_iso_x86())
    assert p["bios"] == "ovmf"
    assert p["efidisk0"] == "local-lvm:1,pre-enrolled-keys=0"
    assert "efitype" not in p["efidisk0"]
    assert "machine" not in p
    assert p["cpu"] == "host"
    assert p["vga"] == "virtio"
    assert p["scsi0"].startswith("local-lvm:32")
    assert p["scsi1"] == "local:iso/alpine.iso,media=cdrom"
    assert _claves_x86(p) == []
    assert p["scsihw"] == "virtio-scsi-single"
    assert p["boot"] == "order=scsi0;scsi1;net0"  # arranque desde el CD en la ranura SCSI
    assert p["net0"] == "virtio,bridge=vmbr0"


def test_ca_d2_6_1_nunca_se_envia_arch_ni_q35_ni_i440fx():
    for cfg in (_iso_x86(), _iso_x86(tpm=True), cfg_import()):
        p = _params(cfg)
        assert "arch" not in p and "machine" not in p
        assert not any(v in ("q35", "i440fx") or "q35" in v for v in p.values())


def test_ca_d2_6_1_el_cdrom_va_en_la_primera_ranura_scsi_libre_tras_los_discos():
    cfg = _iso_x86(discos=[Disco("local-lvm", 32), Disco("local-lvm", 10), Disco("local-lvm", 5)])
    p = _params(cfg)
    assert {"scsi0", "scsi1", "scsi2"} <= set(p) and p["scsi3"].endswith("media=cdrom")
    assert _claves_x86(p) == []


def test_ca_d2_6_1_con_discos_virtio_el_cdrom_ocupa_scsi0():
    cfg = _iso_x86(discos=[Disco("local-lvm", 32, bus=Bus.VIRTIO, ssd=False)])
    p = _params(cfg)
    assert p["virtio0"].startswith("local-lvm:32")
    assert p["scsi0"].endswith("media=cdrom") and "scsi1" not in p
    assert p["boot"] == "order=virtio0;scsi0;net0"


def test_ca_d2_6_1_virtio_win_va_en_otra_ranura_scsi_y_no_en_ide3():
    cfg = _iso_x86(tipo_so=TipoSO.WINDOWS_11, tpm=True, memoria_mib=4096)
    p = _params(cfg)
    cds = {k: v for k, v in p.items() if v.endswith("media=cdrom")}
    assert set(cds) == {"scsi1", "scsi2"} and cds["scsi2"].startswith(VOLID_VIRTIO)
    assert _claves_x86(p) == []


def test_ca_d2_6_1_disco_vacio_sin_origen_tambien_usa_uefi_host_y_vga_virtio():
    cfg = cfg_arm(firmware=Firmware.SEABIOS)
    p = _params(cfg)
    assert p["bios"] == "ovmf" and p["vga"] == "virtio" and p["cpu"] == "host"
    assert "machine" not in p and _claves_x86(p) == []
    assert "boot" not in p and "scsi1" not in p  # sin ISO no hay CD ni orden de arranque


def test_ca_d2_6_1_importar_disco_en_aarch64_conserva_import_from_en_scsi0():
    p = _params(cfg_import())
    assert p["scsi0"].startswith("local-lvm:0,import-from=local:import/cirros.qcow2")
    assert p["bios"] == "ovmf" and "machine" not in p and _claves_x86(p) == []


def test_ca_d2_6_1_el_cpu_max_y_los_personalizados_se_respetan():
    assert _params(cfg_arm(tipo_cpu="max"))["cpu"] == "max"
    p = _params(cfg_arm(tipo_cpu="custom-gamer"), cpus=["host", "custom-gamer"])
    assert p["cpu"] == "custom-gamer"
    assert "flags" not in p["cpu"]


def test_ca_d2_6_1_etiquetas_y_opciones_comunes_siguen_igual_en_arm():
    cfg = cfg_arm(arranque_auto=True, proteger=True, pool=None)
    p = _params(cfg)
    assert p["onboot"] == "1" and p["protection"] == "1"
    assert p["tags"].startswith("proxlaunch;lote-")


# --- CA-D2.6.2: disco SATA/IDE --------------------------------------------------------------------


@pytest.mark.parametrize("bus", [Bus.SATA, Bus.IDE])
def test_ca_d2_6_2_un_disco_sata_o_ide_se_adapta_a_scsi_con_v_d08_y_nunca_sale_en_la_peticion(bus):
    cfg = cfg_arm(discos=[Disco("local-lvm", 32, bus=bus)])
    plan, banco = _plan(cfg)
    (v_d08,) = [p for p in plan.problemas if p.regla == "V-D08" and p.indice == 0]
    assert v_d08.severidad == Severidad.AVISO
    assert "discos[0].bus" in v_d08.params["lista"]
    assert f"discos[0].bus:{bus.value}>scsi" in v_d08.params["cambios"]
    p = construir_parametros(plan.elementos[0].cfg, banco.inv)
    assert _claves_x86(p) == [] and p["scsi0"].startswith("local-lvm:32")


@pytest.mark.parametrize("bus", [Bus.SATA, Bus.IDE])
def test_ca_d2_6_2_el_constructor_rechaza_un_disco_x86_que_llegue_sin_adaptar(bus):
    cfg = cfg_arm(discos=[Disco("local-lvm", 32, bus=bus)], firmware=Firmware.OVMF)
    with pytest.raises(ValueError):
        construir_parametros(cfg, inv_arq({"pve1": ARM}))


def test_ca_d2_6_2_el_constructor_rechaza_una_tarjeta_e1000_sin_adaptar():
    cfg = cfg_arm(redes=[InterfazRed("vmbr0", modelo=ModeloRed.E1000)])
    with pytest.raises(ValueError):
        construir_parametros(cfg, inv_arq({"pve1": ARM}))


def test_ca_d2_7_3_la_red_de_seguridad_v_d09_marca_error_lo_x86_que_llegue_a_un_nodo_arm():
    cfg = cfg_arm(
        firmware=Firmware.SEABIOS,
        tipo_cpu="x86-64-v3",
        discos=[Disco("local-lvm", 32, bus=Bus.SATA)],
        redes=[InterfazRed("vmbr0", modelo=ModeloRed.E1000)],
    )
    problemas = validar_arquitectura(cfg, inv_arq({"pve1": ARM}))
    errores = {p.campo: p for p in problemas if p.codigo == "V-D09"}
    assert set(errores) == {"firmware", "discos[0].bus", "tipo_cpu", "redes[0].modelo"}
    assert all(p.severidad == Severidad.ERROR for p in errores.values())
    assert errores["firmware"].params["alternativa"] == "ovmf"
    assert errores["discos[0].bus"].params["alternativa"] == "scsi"
    assert errores["tipo_cpu"].params["alternativa"] == "host"
    assert errores["redes[0].modelo"].params["alternativa"] == "virtio"
    assert any(p.codigo == "V-D05" and p.severidad == Severidad.AVISO for p in problemas)


@pytest.mark.parametrize("arq", [X86, None], ids=["x86", "sin_dato"])
def test_ca_d2_7_3_en_x86_o_sin_dato_no_hay_v_d09_ni_v_d05(arq):
    inv = inv_arq({"pve1": arq} if arq else {})
    cfg = cfg_arm(firmware=Firmware.SEABIOS, tipo_cpu="x86-64-v3")
    assert validar_arquitectura(cfg, inv) == []


# --- CA-D2.6.3 y CA-D2.6.4: TPM y claves del efidisk ----------------------------------------------


def test_ca_d2_6_3_con_tpm_en_aarch64_lleva_tpmstate0_v2_0():
    p = _params(_iso_x86(tpm=True))
    assert p["tpmstate0"] == "local-lvm:1,version=v2.0"
    p = _params(cfg_import(cfg={"tpm": True}))
    assert p["tpmstate0"] == "local-lvm:1,version=v2.0"


@pytest.mark.parametrize(
    ("so", "claves"),
    [
        (TipoSO.WINDOWS_11, "1"),
        (TipoSO.WINDOWS_10, "1"),
        (TipoSO.WINDOWS_SERVER_2022_2025, "1"),
        (TipoSO.LINUX, "0"),
        (TipoSO.OTRO, "0"),
    ],
)
def test_ca_d2_6_4_pre_enrolled_keys_es_1_solo_con_windows(so, claves):
    cfg = dataclasses.replace(
        cfg_arm(firmware=Firmware.OVMF), tipo_so=so, origen=cfg_iso().origen,
        detalle_origen=dataclasses.replace(cfg_iso().detalle_origen, sin_drivers=True),
    )  # fmt: skip
    p = construir_parametros(cfg, inv_arq({"pve1": ARM}))
    assert p["efidisk0"].endswith(f"pre-enrolled-keys={claves}")
    assert "efitype" not in p["efidisk0"]


# --- CA-D2.6.6 (esbozo): x86 y desconocida no cambian ---------------------------------------------


@pytest.mark.parametrize("arq", [X86, None], ids=["x86", "sin_dato"])
def test_ca_d2_6_6_con_x86_el_mismo_formulario_sigue_siendo_x86(arq):
    p = construir_parametros(
        dataclasses.replace(_iso_x86(), firmware=Firmware.OVMF),
        inv_arq({"pve1": arq} if arq else {}, nodos=("pve1",)),
    )
    assert p["machine"] == "q35" and "efitype=4m" in p["efidisk0"]
    assert p["ide2"].endswith("media=cdrom") and "vga" not in p
    assert p["cpu"] == "x86-64-v2-AES"


# --- adaptar_a_arquitectura -----------------------------------------------------------------------


def test_ca_d2_10_1_un_perfil_x86_adapta_exactamente_firmware_bus_y_cpu():
    cfg = cfg_arm(
        firmware=Firmware.SEABIOS, discos=[Disco("local-lvm", 32, bus=Bus.SATA)],
        tipo_cpu="x86-64-v2-AES",
    )  # fmt: skip
    nuevo, cambios = adaptar_a_arquitectura(cfg, Arquitectura.AARCH64)
    assert [(c.campo, c.antes, c.despues) for c in cambios] == [
        ("firmware", "seabios", "ovmf"),
        ("discos[0].bus", "sata", "scsi"),
        ("tipo_cpu", "x86-64-v2-AES", "host"),
    ]
    assert nuevo.firmware == Firmware.OVMF and nuevo.discos[0].bus == Bus.SCSI
    assert nuevo.tipo_cpu == "host"
    assert cfg.firmware == Firmware.SEABIOS and cfg.discos[0].bus == Bus.SATA  # el origen no cambia


@pytest.mark.parametrize("arq", [Arquitectura.X86_64, Arquitectura.DESCONOCIDA])
def test_ca_d2_10_2_en_x86_o_desconocida_no_hay_cambios_ni_copia(arq):
    cfg = cfg_arm(firmware=Firmware.SEABIOS, tipo_cpu="x86-64-v3")
    nuevo, cambios = adaptar_a_arquitectura(cfg, arq)
    assert nuevo is cfg and cambios == ()


def test_adaptar_es_idempotente_y_un_formulario_ya_arm_no_cambia():
    cfg = cfg_arm(
        firmware=Firmware.OVMF, tipo_cpu="host", discos=[Disco("local-lvm", 8, bus=Bus.VIRTIO)]
    )
    nuevo, cambios = adaptar_a_arquitectura(cfg, Arquitectura.AARCH64)
    assert cambios == ()
    again, c2 = adaptar_a_arquitectura(nuevo, Arquitectura.AARCH64)
    assert c2 == () and again == nuevo


@pytest.mark.parametrize("cpu", ["x86-64-v2", "x86-64-v3", "x86-64-v4", "kvm64", "Haswell"])
def test_ca_d2_7_1_todo_tipo_de_cpu_x86_se_cambia_por_host(cpu):
    nuevo, cambios = adaptar_a_arquitectura(cfg_arm(tipo_cpu=cpu), Arquitectura.AARCH64)
    assert nuevo.tipo_cpu == "host" and [c.campo for c in cambios] == ["firmware", "tipo_cpu"]


@pytest.mark.parametrize("cpu", ["host", "max", "custom-gamer"])
def test_ca_d2_7_1_host_max_y_personalizadas_no_se_tocan(cpu):
    nuevo, _ = adaptar_a_arquitectura(cfg_arm(tipo_cpu=cpu), Arquitectura.AARCH64)
    assert nuevo.tipo_cpu == cpu


def test_ca_d2_7_5_un_cambio_de_x86_a_arm_con_valores_elegidos_los_adapta_sin_corromper():
    cfg = cfg_arm(
        firmware=Firmware.SEABIOS,
        tipo_cpu="x86-64-v3",
        sockets=2, cores=4, memoria_mib=4096,
        discos=[Disco("local-lvm", 64, bus=Bus.IDE, ssd=True), Disco("local-lvm", 8, bus=Bus.SATA)],
        redes=[InterfazRed("vmbr0", vlan=20, mtu=1500, modelo=ModeloRed.E1000)],
    )  # fmt: skip
    nuevo, cambios = adaptar_a_arquitectura(cfg, Arquitectura.AARCH64)
    assert {c.campo for c in cambios} == {
        "firmware", "tipo_cpu", "discos[0].bus", "discos[1].bus", "redes[0].modelo",
    }  # fmt: skip
    assert (nuevo.sockets, nuevo.cores, nuevo.memoria_mib) == (2, 4, 4096)
    assert [d.tamano_gib for d in nuevo.discos] == [64, 8] and nuevo.discos[0].ssd is True
    assert nuevo.redes[0].vlan == 20 and nuevo.redes[0].mtu == 1500
    assert nuevo.redes[0].modelo == ModeloRed.VIRTIO and nuevo.redes[0].bridge == "vmbr0"


def test_ranura_cdrom_es_la_primera_scsi_libre():
    cfg = cfg_arm()
    assert ranura_cdrom_aarch64(cfg, set()) == "scsi0"
    assert ranura_cdrom_aarch64(cfg, {"scsi0", "scsi1", "virtio0"}) == "scsi2"
    assert ranura_cdrom_aarch64(cfg, {"scsi1"}) == "scsi0"


# --- CA-D2.11: tipo de CPU por defecto unificado --------------------------------------------------


def test_ca_d2_11_1_el_literal_de_la_cpu_por_defecto_vive_solo_en_modelos_cpu():
    donde = sorted(
        ruta.relative_to(RAIZ_SRC).as_posix()
        for ruta in RAIZ_SRC.rglob("*.py")
        if '"x86-64-v2-AES"' in ruta.read_text(encoding="utf-8")
    )
    assert donde == ["nucleo/modelos/cpu.py"]
    assert TIPOS_CPU_X86[0] == TIPO_CPU_X86_DEFECTO


def test_ca_d2_11_2_en_x86_el_valor_por_defecto_es_x86_64_v2_aes_en_formulario_modelo_y_perfil():
    from proxlaunch.nucleo import valores_defecto

    assert TIPO_CPU_X86_DEFECTO == "x86-64-v2-AES"
    assert valores_defecto.TIPO_CPU == "x86-64-v2-AES"
    assert ConfiguracionVM(vmid=1, nombre="x", nodo="n").tipo_cpu == "x86-64-v2-AES"
    assert ConfigPerfil().tipo_cpu == "x86-64-v2-AES"
    for arq in ("x86_64", "desconocida", "otra", ""):
        assert tipo_cpu_por_defecto(arq) == "x86-64-v2-AES"


def test_ca_d2_11_3_en_aarch64_el_valor_por_defecto_es_host():
    assert tipo_cpu_por_defecto("aarch64") == TIPO_CPU_ARM_DEFECTO == "host"
    assert TIPOS_CPU_ARM == ("host", "max")


@pytest.mark.parametrize(
    ("tipo", "solo_x86"),
    [("x86-64-v2-AES", True), ("kvm64", True), ("Haswell", True), ("", True), ("host", False),
     ("max", False), ("custom-x", False)],
)  # fmt: skip
def test_es_cpu_solo_x86(tipo, solo_x86):
    assert es_cpu_solo_x86(tipo) is solo_x86


@pytest.mark.parametrize(
    ("tipo", "valido"),
    [("custom-gamer", True), ("custom-a.b_c-1", True), ("custom-", False),
     ("custom-x;y=z", False), ("custom-con espacio", False), ("custom-" + "a" * 65, False),
     ("host", False), ("Custom-x", False)],
)  # fmt: skip
def test_ca_d3_6_4_solo_los_nombres_custom_validos_son_personalizados(tipo, valido):
    assert es_cpu_personalizada(tipo) is valido


# --- Versión del servidor: el perfil ARM no depende de la versión ---------------------------------


@pytest.mark.parametrize("version", [V_84, V_92], ids=["8.4", "9.2"])
def test_el_perfil_aarch64_es_el_mismo_en_8_4_y_9_2(version):
    p = _params(_iso_x86(), version=version)
    assert p["bios"] == "ovmf" and p["vga"] == "virtio" and p["scsi1"].endswith("media=cdrom")
