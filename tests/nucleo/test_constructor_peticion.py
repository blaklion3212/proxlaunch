"""Construcción de los parámetros de la API (RF-14 a RF-17, RF-19, RNF-16)."""

import re
from urllib.parse import parse_qsl, urlencode

import pytest

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.modelos import (
    Ballooning,
    Bus,
    ControladorScsi,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
)

CLAVES_DE_DISCO = re.compile(r"^(scsi|virtio|sata|ide)\d+$")


def _claves_de_disco(params):
    return [k for k in params if CLAVES_DE_DISCO.match(k)]


# --- CA-19.3: el ejemplo del requisito, con igualdad exacta -------------------------


def test_ca19_3_peticion_del_ejemplo_es_exactamente_la_esperada(hacer_cfg, inv):
    """vmid=100, name=srv-web-01, OVMF, 1 socket, 2 cores, 2048 MiB, scsi0 de 32 GiB, vmbr0."""
    cfg = hacer_cfg(firmware=Firmware.OVMF)
    assert construir_parametros(cfg, inv) == {
        "vmid": "100",
        "name": "srv-web-01",
        "bios": "ovmf",
        "machine": "q35",
        "efidisk0": "local-lvm:1,efitype=4m,pre-enrolled-keys=1",
        "sockets": "1",
        "cores": "2",
        "cpu": "x86-64-v2-AES",
        "memory": "2048",
        "scsihw": "virtio-scsi-single",
        "scsi0": "local-lvm:32,discard=on,ssd=1,iothread=1",
        "net0": "virtio,bridge=vmbr0",
    }


def test_ca19_3_todos_los_valores_son_cadenas_sin_codificar(hacer_cfg, inv):
    params = construir_parametros(hacer_cfg(firmware=Firmware.OVMF), inv)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in params.items())
    assert "%" not in "".join(params.values())


def test_ca19_3_no_se_envian_parametros_fuera_de_alcance(hacer_cfg, inv):
    """CA-14.6 (TPM), P-09 (ostype), S-1/P-15 (iniciar), CA-17.7 (MAC)."""
    params = construir_parametros(hacer_cfg(firmware=Firmware.OVMF), inv)
    for ausente in ("tpmstate0", "ostype", "start", "onboot", "macaddr"):
        assert ausente not in params
    assert "macaddr" not in params["net0"]


# --- RF-14 firmware -----------------------------------------------------------------


def test_ca14_1_seabios_no_lleva_efidisk_ni_machine(hacer_cfg, inv):
    params = construir_parametros(hacer_cfg(firmware=Firmware.SEABIOS), inv)
    assert params.get("bios", "seabios") == "seabios"
    assert "efidisk0" not in params
    assert "machine" not in params


def test_ca14_2_ovmf_usa_el_storage_del_primer_disco(hacer_cfg, inv):
    cfg = hacer_cfg(firmware=Firmware.OVMF, discos=[Disco("dirimg", 8), Disco("local-lvm", 8)])
    params = construir_parametros(cfg, inv)
    assert params["bios"] == "ovmf"
    assert params["machine"] == "q35"
    assert params["efidisk0"].startswith("dirimg:1,efitype=4m,")


def test_ca14_2_ovmf_sin_disco_usa_el_primer_storage_con_images(hacer_cfg, inv):
    """En pve1 el primero con `images` es local-lvm (local solo tiene iso y backup)."""
    cfg = hacer_cfg(firmware=Firmware.OVMF, con_disco=False, discos=[])
    params = construir_parametros(cfg, inv)
    assert params["efidisk0"].startswith("local-lvm:1,efitype=4m,")
    assert _claves_de_disco(params) == []


def test_ca14_3_storage_efi_explicito_manda_sobre_el_del_disco(hacer_cfg, inv):
    cfg = hacer_cfg(firmware=Firmware.OVMF, storage_efi="nfs1")
    assert construir_parametros(cfg, inv)["efidisk0"].startswith("nfs1:1,efitype=4m,")


def test_ca14_2_efidisk_incluye_claves_precargadas(hacer_cfg, inv):
    """P-10: pre-enrolled-keys=1."""
    cfg = hacer_cfg(firmware=Firmware.OVMF)
    assert "pre-enrolled-keys=1" in construir_parametros(cfg, inv)["efidisk0"]


def test_ca14_5_volver_a_seabios_quita_efidisk_y_machine(hacer_cfg, inv):
    cfg = hacer_cfg(firmware=Firmware.OVMF)
    assert "efidisk0" in construir_parametros(cfg, inv)
    cfg.firmware = Firmware.SEABIOS
    params = construir_parametros(cfg, inv)
    assert "efidisk0" not in params
    assert "machine" not in params


# --- RF-15 cómputo ------------------------------------------------------------------


def test_ca15_2_sockets_y_cores_van_por_separado(hacer_cfg, inv):
    params = construir_parametros(hacer_cfg(sockets=2, cores=4), inv)
    assert (params["sockets"], params["cores"]) == ("2", "4")


def test_ca15_4_la_memoria_va_en_mib(hacer_cfg, inv):
    assert construir_parametros(hacer_cfg(memoria_mib=4096), inv)["memory"] == "4096"


def test_tipo_de_cpu_se_envia_tal_cual(hacer_cfg, inv):
    assert construir_parametros(hacer_cfg(tipo_cpu="host"), inv)["cpu"] == "host"


@pytest.mark.parametrize(
    ("ballooning", "esperado"),
    [
        pytest.param(Ballooning(True, 1024), "1024", id="CA-15.5-activo-minimo-1024"),
        pytest.param(Ballooning(False, 1024), "0", id="CA-15.5-desactivado-balloon-0"),
        pytest.param(None, None, id="CA-15.5-modo-basico-no-se-envia"),
    ],
)
def test_ca15_5_ballooning(ballooning, esperado, hacer_cfg, inv):
    params = construir_parametros(hacer_cfg(memoria_mib=4096, ballooning=ballooning), inv)
    assert params.get("balloon") == esperado


# --- RF-16 discos -------------------------------------------------------------------


def test_ca16_1_disco_por_defecto(hacer_cfg, inv):
    params = construir_parametros(hacer_cfg(), inv)
    assert params["scsihw"] == "virtio-scsi-single"
    assert params["scsi0"] == "local-lvm:32,discard=on,ssd=1,iothread=1"
    assert "format=" not in params["scsi0"]  # lvmthin: solo raw, no se envía


def test_ca16_2_indices_consecutivos_por_bus(hacer_cfg, inv):
    discos = [
        Disco("nfs1", 8, bus=Bus.SCSI),
        Disco("nfs1", 8, bus=Bus.VIRTIO, ssd=False),
        Disco("nfs1", 8, bus=Bus.SCSI),
    ]
    params = construir_parametros(hacer_cfg(discos=discos), inv)
    assert sorted(_claves_de_disco(params)) == ["scsi0", "scsi1", "virtio0"]
    assert params["virtio0"].startswith("nfs1:8")


def test_ca16_2_dos_discos_scsi_y_uno_virtio(hacer_cfg, inv):
    discos = [
        Disco("nfs1", 10),
        Disco("nfs1", 20),
        Disco("nfs1", 30, bus=Bus.VIRTIO, ssd=False),
    ]
    params = construir_parametros(hacer_cfg(discos=discos), inv)
    assert params["scsi0"].startswith("nfs1:10")
    assert params["scsi1"].startswith("nfs1:20")
    assert params["virtio0"].startswith("nfs1:30")


@pytest.mark.parametrize("bus", list(Bus), ids=lambda b: f"CA-16.2-{b.value}0")
def test_ca16_2_cada_bus_usa_su_propio_prefijo(bus, hacer_cfg, inv):
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=bus, discard=False, ssd=False, iothread=False)])
    assert f"{bus.value}0" in construir_parametros(cfg, inv)


def test_ca16_3_sin_disco_no_hay_discos_ni_scsihw(hacer_cfg, inv):
    """Aunque la lista de discos tenga elementos, `con_disco=False` los omite."""
    cfg = hacer_cfg(con_disco=False, discos=[Disco("local-lvm", 32)])
    params = construir_parametros(cfg, inv)
    assert _claves_de_disco(params) == []
    assert "scsihw" not in params


def test_v10_scsihw_solo_si_hay_discos_scsi(hacer_cfg, inv):
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=Bus.VIRTIO, ssd=False)])
    assert "scsihw" not in construir_parametros(cfg, inv)


def test_v10_scsihw_refleja_el_controlador_elegido(hacer_cfg, inv):
    cfg = hacer_cfg(controlador_scsi=ControladorScsi.VIRTIO_PCI)
    assert construir_parametros(cfg, inv)["scsihw"] == "virtio-scsi-pci"


def test_v12_ssd_no_se_envia_en_virtio(hacer_cfg, inv):
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=Bus.VIRTIO, ssd=True)])
    assert "ssd" not in construir_parametros(cfg, inv)["virtio0"]


@pytest.mark.parametrize("bus", [Bus.SATA, Bus.IDE], ids=lambda b: f"V-11-{b.value}")
def test_v11_iothread_no_se_envia_en_sata_ni_ide(bus, hacer_cfg, inv):
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=bus, iothread=True)])
    assert "iothread" not in construir_parametros(cfg, inv)[f"{bus.value}0"]


def test_v11_iothread_no_se_envia_con_controlador_distinto_de_single(hacer_cfg, inv):
    cfg = hacer_cfg(controlador_scsi=ControladorScsi.VIRTIO_PCI)
    assert "iothread" not in construir_parametros(cfg, inv)["scsi0"]


def test_discard_y_ssd_desmarcados_no_se_envian(hacer_cfg, inv):
    cfg = hacer_cfg(discos=[Disco("local-lvm", 8, discard=False, ssd=False, iothread=False)])
    assert construir_parametros(cfg, inv)["scsi0"] == "local-lvm:8"


def test_el_tamano_se_envia_en_gib(hacer_cfg, inv):
    """CT-6: el valor numérico del disco es GiB, sin sufijo."""
    cfg = hacer_cfg(discos=[Disco("local-lvm", 100)])
    assert construir_parametros(cfg, inv)["scsi0"].startswith("local-lvm:100,")


@pytest.mark.parametrize(
    ("storage", "formato", "esperado"),
    [
        pytest.param("local-lvm", FormatoDisco.AUTO, None, id="V-09-lvmthin-auto-sin-format"),
        pytest.param("zfs1", FormatoDisco.AUTO, None, id="V-09-zfspool-auto-sin-format"),
        pytest.param("lvm1", FormatoDisco.RAW, None, id="V-09-lvm-raw-sin-format"),
        pytest.param("dirimg", FormatoDisco.AUTO, "qcow2", id="P-06-dir-auto-qcow2"),
        pytest.param("nfs1", FormatoDisco.AUTO, "qcow2", id="P-06-nfs-auto-qcow2"),
        pytest.param("cifs1", FormatoDisco.AUTO, "qcow2", id="P-06-cifs-auto-qcow2"),
        pytest.param("nfs1", FormatoDisco.RAW, "raw", id="V-09-nfs-raw-explicito"),
        pytest.param("dirimg", FormatoDisco.QCOW2, "qcow2", id="V-09-dir-qcow2-explicito"),
        pytest.param("btrfs1", FormatoDisco.AUTO, None, id="P-06-btrfs-auto-sin-format"),
    ],
)
def test_v09_format_solo_cuando_el_storage_lo_admite(storage, formato, esperado, hacer_cfg, inv):
    cfg = hacer_cfg(discos=[Disco(storage, 8, formato=formato)])
    valor = construir_parametros(cfg, inv)["scsi0"]
    formatos = [p for p in valor.split(",") if p.startswith("format=")]
    assert formatos == ([] if esperado is None else [f"format={esperado}"])


# --- RF-17 red ----------------------------------------------------------------------


def test_ca17_2_net0_por_defecto_y_codificacion_en_el_cuerpo(hacer_cfg, inv):
    """CT-9: el constructor da el valor limpio; al codificar, `,` y `=` van en porcentaje."""
    params = construir_parametros(hacer_cfg(), inv)
    assert params["net0"] == "virtio,bridge=vmbr0"
    cuerpo = urlencode(params)
    assert "net0=virtio%2Cbridge%3Dvmbr0" in cuerpo.split("&")


def test_ca17_3_segunda_interfaz_con_vlan(hacer_cfg, inv):
    redes = [InterfazRed("vmbr0"), InterfazRed("vmbr1", vlan=120)]
    params = construir_parametros(hacer_cfg(redes=redes), inv)
    assert params["net0"] == "virtio,bridge=vmbr0"
    assert params["net1"] == "virtio,bridge=vmbr1,tag=120"


def test_ca17_4_vlan_vacia_no_agrega_tag(hacer_cfg, inv):
    params = construir_parametros(hacer_cfg(redes=[InterfazRed("vmbr0", vlan=None)]), inv)
    assert "tag" not in params["net0"]


def test_ca17_6_modelo_e1000(hacer_cfg, inv):
    cfg = hacer_cfg(redes=[InterfazRed("vmbr0", modelo=ModeloRed.E1000)])
    assert construir_parametros(cfg, inv)["net0"] == "e1000,bridge=vmbr0"


def test_sin_redes_no_hay_net(hacer_cfg, inv):
    params = construir_parametros(hacer_cfg(redes=[]), inv)
    assert not [k for k in params if k.startswith("net")]


# --- RNF-16 seguridad de entrada ----------------------------------------------------


def test_rnf16_un_nombre_hostil_no_altera_otros_parametros(hacer_cfg, inv):
    """El constructor no concatena el nombre en otro parámetro y el formulario lo recupera
    íntegro: una `&` o un `=` en el valor no crea claves nuevas."""
    hostil = "a&memory=1,x=y z\nvmid=1"
    params = construir_parametros(hacer_cfg(nombre=hostil), inv)
    assert params["name"] == hostil
    ida_y_vuelta = dict(parse_qsl(urlencode(params), keep_blank_values=True))
    assert ida_y_vuelta == params
    assert ida_y_vuelta["memory"] == "2048"
    assert ida_y_vuelta["vmid"] == "100"


def test_la_construccion_es_pura_no_modifica_la_configuracion(hacer_cfg, inv):
    cfg = hacer_cfg(firmware=Firmware.OVMF)
    antes = cfg.a_dict()
    construir_parametros(cfg, inv)
    assert cfg.a_dict() == antes
