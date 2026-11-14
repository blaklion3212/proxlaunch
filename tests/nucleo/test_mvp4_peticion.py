"""MVP 4: construcción de la petición por origen y asistente de SO.

Requisitos: RF-O08 (CA-O08.1..O08.5), RF-O13 (CA-O13.1..O13.13), RF-O14, RF-O17 (CA-O17.1/O17.2/
O17.8/O17.9), CA-O03.1 (equivalencia con M3), INV-O7, INV-O10, RNF-O15 (determinismo).
"""

import copy

import pytest

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor
from proxlaunch.nucleo.modelos.origen import TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ControladorScsi,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
)
from proxlaunch.nucleo.origen.asistente import (
    TABLA_SO,
    CampoAsistente,
    aplicar_asistente,
    avisos_so,
)
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_mvp4 import (
    VOLID_IMAGEN,
    VOLID_ISO,
    VOLID_VIRTIO,
    cfg_base,
    cfg_clon,
    cfg_import,
    cfg_iso,
    inv_origen,
    permisos,
)

INV = inv_origen()


def _campos(res):
    return {c.campo: (c.antes, c.despues) for c in res.cambios}


# --- RF-O08: ISO ------------------------------------------------------------------------------


def test_ca_o08_1_el_iso_se_monta_en_ide2_como_cdrom():
    p = construir_parametros(cfg_iso(), INV)
    assert p["ide2"] == "local:iso/alpine.iso,media=cdrom"
    assert p["ostype"] == "l26"
    assert "import-from" not in "".join(p.values())


def test_ca_o08_2_orden_de_arranque_disco_cd_red():
    assert construir_parametros(cfg_iso(), INV)["boot"] == "order=scsi0;ide2;net0"
    assert construir_parametros(cfg_iso(redes=[]), INV)["boot"] == "order=scsi0;ide2"


def test_ca_o08_2_sin_disco_arranca_primero_del_cd():
    p = construir_parametros(cfg_iso(con_disco=False, discos=[]), INV)
    assert p["boot"] == "order=ide2;net0"
    assert not [k for k in p if k.startswith(("scsi", "sata", "virtio"))]


def test_ca_o08_3_inv_o10_sin_vm_config_disk_no_se_envia_boot():
    inv = inv_origen(permisos_efectivos=permisos(quitar=("VM.Config.Disk",)))
    p = construir_parametros(cfg_iso(), inv)
    assert "boot" not in p and p["ide2"].endswith("media=cdrom")  # la MV se crea igualmente


def test_inv_o10_con_permisos_desconocidos_o_sin_catalogo_tampoco_se_envia_boot():
    assert "boot" not in construir_parametros(cfg_iso(), inv_origen(permisos_efectivos=None))
    inv = inv_origen()
    inv.catalogo = None
    assert "boot" not in construir_parametros(cfg_iso(), inv)
    inv.catalogo = CatalogoServidor()  # catálogo sin permisos leídos
    assert "boot" not in construir_parametros(cfg_iso(), inv)


def test_inv_o10_el_permiso_en_el_vmid_concreto_basta():
    from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos

    inv = inv_origen(permisos_efectivos=PermisosEfectivos({"/vms/100": {"VM.Config.Disk": 0}}))
    assert "boot" in construir_parametros(cfg_iso(vmid=100), inv)
    assert "boot" not in construir_parametros(cfg_iso(vmid=101), inv)


@pytest.mark.parametrize(
    ("n_ide", "esperado"),
    [(1, ["ide1"]), (2, ["ide1", "ide3"])],
)
def test_ca_o08_4_los_discos_ide_con_iso_usan_ide1_e_ide3(n_ide, esperado):
    discos = [Disco("local-lvm", 8, bus=Bus.IDE) for _ in range(n_ide)]
    p = construir_parametros(cfg_iso(discos=discos), INV)
    assert [k for k in p if k.startswith("ide") and k != "ide2"] == esperado
    assert p["boot"].startswith(f"order={esperado[0]};")


def test_ca_o08_4_tres_discos_ide_con_iso_se_rechazan():
    discos = [Disco("local-lvm", 8, bus=Bus.IDE) for _ in range(3)]
    with pytest.raises(ErrorProxLaunch) as e:
        construir_parametros(cfg_iso(discos=discos), INV)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO


def test_ca_o08_4_sin_iso_la_numeracion_ide_no_cambia():
    discos = [Disco("local-lvm", 8, bus=Bus.IDE) for _ in range(2)]
    p = construir_parametros(cfg_base(discos=discos), INV)
    assert [k for k in p if k.startswith("ide")] == ["ide0", "ide1"]


@pytest.mark.parametrize(
    "volid",
    [
        "local:iso/x.iso,media=disk",
        "local:iso/x.iso,ide0=local:iso/y.iso",
        "local:iso/x.iso;ide0=a",
        "/var/x.iso",
        "local:iso/x y.iso",
        None,
        "",
    ],
)
def test_ca_o08_5_inv_o7_defensa_en_profundidad_contra_inyeccion_de_parametros(volid):
    with pytest.raises(ErrorProxLaunch) as e:
        construir_parametros(cfg_iso(volid), INV)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO and e.value.params["campo"] == "origen"


def test_ca_o14_los_drivers_inyectados_tambien_se_validan():
    with pytest.raises(ErrorProxLaunch):
        construir_parametros(
            cfg_iso(tipo_so=TipoSO.WINDOWS_10, drivers="local:iso/v.iso,ide2=a"), INV
        )


def test_el_clon_no_pasa_por_construir_parametros():
    with pytest.raises(ErrorProxLaunch) as e:
        construir_parametros(cfg_clon("base", 9000, "pve1"), INV)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO


def test_origen_sin_detalle_no_construye_peticion():
    from proxlaunch.nucleo.modelos.vm import OrigenSO

    with pytest.raises(ErrorProxLaunch):
        construir_parametros(cfg_base(origen=OrigenSO.ISO), INV)


# --- CA-O03.1: compatibilidad hacia atrás -------------------------------------------------------


def test_ca_o03_1_disco_vacio_no_envia_ninguna_clave_nueva():
    p = construir_parametros(cfg_base(), INV)
    for nueva in ("ide0", "ide2", "boot", "ostype", "tpmstate0", "agent"):
        assert nueva not in p
    assert not any("import-from" in v for v in p.values())


def test_ca_o03_1_los_permisos_no_cambian_la_peticion_de_disco_vacio():
    base = construir_parametros(cfg_base(), inv_origen(permisos_efectivos=None))
    assert construir_parametros(cfg_base(), inv_origen()) == base
    assert construir_parametros(cfg_base(), inv_origen(privilegios=())) == base


def test_rnf_o15_la_peticion_es_funcion_pura_de_la_entrada():
    cfg = cfg_iso()
    antes = copy.deepcopy(cfg)
    a = construir_parametros(cfg, INV)
    b = construir_parametros(cfg, INV)
    assert a == b and cfg == antes


# --- RF-O13: asistente de SO ---------------------------------------------------------------------


def _win11(**kw):
    base = cfg_iso("local:iso/win11.iso", None, drivers=VOLID_VIRTIO)
    base.tipo_so = None
    res = aplicar_asistente(base, TipoSO.WINDOWS_11)
    for k, v in kw.items():
        setattr(res.cfg, k, v)
    return res.cfg


def test_ca_o13_1_windows_11_genera_el_hardware_completo():
    p = construir_parametros(_win11(), INV)
    assert p["ostype"] == "win11"
    assert p["bios"] == "ovmf" and p["machine"] == "q35"
    assert p["efidisk0"] == "local-lvm:1,efitype=4m,pre-enrolled-keys=1"
    assert p["tpmstate0"] == "local-lvm:1,version=v2.0"  # siempre v2.0 (el defecto de PVE es v1.2)
    assert p["scsihw"] == "virtio-scsi-single"
    assert p["net0"] == "virtio,bridge=vmbr0"
    assert p["agent"] == "1"
    assert p["ide0"] == f"{VOLID_VIRTIO},media=cdrom"  # CD de drivers (CA-O14)
    assert p["ide2"] == f"{VOLID_ISO.replace('alpine', 'win11')},media=cdrom"
    assert p["scsi0"].startswith("local-lvm:32,")


def test_ca_o13_5_el_tpm_no_lleva_format_y_usa_el_storage_del_efidisk():
    cfg = _win11(storage_efi="nfs1")
    p = construir_parametros(cfg, INV)
    assert p["tpmstate0"] == "nfs1:1,version=v2.0" and p["efidisk0"].startswith("nfs1:1,")
    assert "format" not in p["tpmstate0"]


@pytest.mark.parametrize("tipo", [TipoSO.WINDOWS_10, TipoSO.WINDOWS_SERVER_2016_2019])
def test_ca_o13_2_windows_10_y_server_2016_2019_son_win10_sin_tpm(tipo):
    cfg = aplicar_asistente(cfg_iso(tipo_so=None, drivers=VOLID_VIRTIO), tipo).cfg
    p = construir_parametros(cfg, INV)
    assert p["ostype"] == "win10" and "tpmstate0" not in p
    assert p["bios"] == "ovmf" and p["machine"] == "q35" and p["agent"] == "1"


def test_server_2022_2025_es_win11_con_tpm_activado_por_defecto():
    cfg = aplicar_asistente(
        cfg_iso(tipo_so=None, drivers=VOLID_VIRTIO), TipoSO.WINDOWS_SERVER_2022_2025
    ).cfg
    p = construir_parametros(cfg, INV)
    assert p["ostype"] == "win11" and p["tpmstate0"] == "local-lvm:1,version=v2.0"


def test_ca_o13_3_linux_es_l26_sin_tpm_ni_drivers_y_el_firmware_lo_decide_el_perfil():
    p = construir_parametros(cfg_iso(), INV)
    assert p["ostype"] == "l26" and "bios" not in p and "tpmstate0" not in p and "ide0" not in p
    uefi = construir_parametros(cfg_iso(firmware=Firmware.OVMF), INV)
    assert uefi["bios"] == "ovmf" and uefi["ostype"] == "l26"


def test_ca_o13_11_agent_solo_para_windows_y_linux_que_lo_activen_nunca_para_otro():
    assert "agent" not in construir_parametros(cfg_iso(), INV)
    assert construir_parametros(cfg_iso(agente_qemu=True), INV)["agent"] == "1"
    otro = cfg_iso(tipo_so=TipoSO.OTRO, agente_qemu=True)
    assert "agent" not in construir_parametros(otro, INV)
    assert construir_parametros(otro, INV)["ostype"] == "other"


def test_ca_o14_3_crear_sin_drivers_no_monta_ide0():
    cfg = aplicar_asistente(cfg_iso(tipo_so=None, sin_drivers=True), TipoSO.WINDOWS_10).cfg
    assert "ide0" not in construir_parametros(cfg, INV)


def test_ca_o13_9_el_asistente_no_toca_nucleos_memoria_ni_tamanos_pero_si_el_hardware():
    base = cfg_iso(
        tipo_so=None, cores=1, sockets=2, memoria_mib=512,
        discos=[Disco("local-lvm", 10, bus=Bus.IDE), Disco("local-lvm", 20, bus=Bus.SATA)],
        controlador_scsi=ControladorScsi.VIRTIO_PCI, redes=[InterfazRed("vmbr0", ModeloRed.E1000)],
    )  # fmt: skip
    res = aplicar_asistente(base, TipoSO.WINDOWS_11)
    c = res.cfg
    assert (c.cores, c.sockets, c.memoria_mib) == (1, 2, 512)
    assert [d.tamano_gib for d in c.discos] == [10, 20]
    assert c.firmware == Firmware.OVMF and c.tpm is True and c.agente_qemu is True
    assert c.controlador_scsi == ControladorScsi.VIRTIO_SINGLE
    assert c.redes[0].modelo == ModeloRed.VIRTIO and c.tipo_so == TipoSO.WINDOWS_11
    assert c.discos[0].bus == Bus.SCSI and c.discos[1].bus == Bus.SATA  # solo el primero
    assert set(_campos(res)) == {
        CampoAsistente.FIRMWARE, CampoAsistente.TPM, CampoAsistente.CONTROLADOR,
        CampoAsistente.MODELO_RED, CampoAsistente.BUS_DISCO, CampoAsistente.AGENTE,
    }  # fmt: skip
    assert base.firmware == Firmware.SEABIOS and base.tipo_so is None  # el original no se muta


def test_ca_o13_9_el_asistente_avisa_de_cada_campo_que_cambio_con_antes_y_despues():
    res = aplicar_asistente(cfg_iso(tipo_so=None), TipoSO.WINDOWS_11)
    campos = _campos(res)
    assert campos[CampoAsistente.FIRMWARE] == ("seabios", "ovmf")
    assert campos[CampoAsistente.TPM] == ("no", "si")
    assert CampoAsistente.BUS_DISCO not in campos  # el disco por defecto ya es SCSI
    assert campos[CampoAsistente.AGENTE] == ("no", "si")


def test_ca_o13_9_aplicar_dos_veces_no_produce_mas_cambios():
    una = aplicar_asistente(cfg_iso(tipo_so=None), TipoSO.WINDOWS_11)
    dos = aplicar_asistente(una.cfg, TipoSO.WINDOWS_11)
    assert dos.cambios == () and dos.cfg == una.cfg


def test_dt_o9_disco_compatible_usa_sata_sin_iothread():
    res = aplicar_asistente(cfg_iso(tipo_so=None), TipoSO.WINDOWS_10, disco_compatible=True)
    d = res.cfg.discos[0]
    assert d.bus == Bus.SATA and d.iothread is False
    p = construir_parametros(res.cfg, INV)
    assert p["sata0"].startswith("local-lvm:32") and "iothread" not in p["sata0"]


def test_otro_solo_fija_el_tipo_y_no_cambia_nada_mas():
    base = cfg_iso(tipo_so=None, redes=[InterfazRed("vmbr0", ModeloRed.E1000)])
    res = aplicar_asistente(base, TipoSO.OTRO)
    assert res.cambios == ()
    assert res.cfg.tipo_so == TipoSO.OTRO and res.cfg.redes[0].modelo == ModeloRed.E1000


def test_linux_pone_virtio_pero_no_cambia_firmware_ni_agente():
    res = aplicar_asistente(
        cfg_iso(tipo_so=None, controlador_scsi=ControladorScsi.VIRTIO_PCI), TipoSO.LINUX
    )
    assert res.cfg.controlador_scsi == ControladorScsi.VIRTIO_SINGLE
    assert res.cfg.firmware == Firmware.SEABIOS and res.cfg.agente_qemu is False
    assert CampoAsistente.FIRMWARE not in _campos(res) and CampoAsistente.AGENTE not in _campos(res)


def test_tabla_so_ostype_y_drivers_segun_los_requisitos():
    esperado = {
        TipoSO.LINUX: ("l26", False, False),
        TipoSO.WINDOWS_11: ("win11", True, True),
        TipoSO.WINDOWS_SERVER_2022_2025: ("win11", True, True),
        TipoSO.WINDOWS_10: ("win10", False, True),
        TipoSO.WINDOWS_SERVER_2016_2019: ("win10", False, True),
        TipoSO.OTRO: ("other", False, False),
    }
    assert set(TABLA_SO) == set(TipoSO)
    for tipo, (ostype, tpm, drivers) in esperado.items():
        perfil = TABLA_SO[tipo]
        assert (perfil.ostype, perfil.tpm, perfil.drivers) == (ostype, tpm, drivers), tipo
    assert (
        TABLA_SO[TipoSO.WINDOWS_11].tpm_obligatorio
        and not TABLA_SO[TipoSO.WINDOWS_10].tpm_obligatorio
    )


# --- D-25.6: aviso de RHEL 10 / x86-64-v3 ---------------------------------------------------------


@pytest.mark.parametrize(
    "iso",
    [
        "local:iso/rhel-10.0-x86_64-dvd.iso",
        "local:iso/Rocky-10.0-x86_64-dvd.iso",
        "local:iso/AlmaLinux-10-x86_64.iso",
        "local:iso/centos-stream-10.iso",
    ],
)
def test_ca_o13_4_aviso_rhel10_con_cpu_v2(iso):
    avisos = [a for a in avisos_so(cfg_iso(iso)) if a.codigo == "V-O05.rhel10"]
    assert len(avisos) == 1 and avisos[0].severidad == Severidad.AVISO
    assert avisos[0].campo == "tipo_cpu" and avisos[0].params["tipo_cpu"] == "x86-64-v2-AES"


@pytest.mark.parametrize(
    "iso",
    [
        "local:iso/rhel-9.4-x86_64-dvd.iso",
        "local:iso/ubuntu-24.04.iso",
        "local:iso/alpine.iso",
        "local:iso/Rocky-9.4.iso",
    ],
)
def test_ca_o13_4_sin_aviso_para_otras_distribuciones(iso):
    assert not [a for a in avisos_so(cfg_iso(iso)) if a.codigo == "V-O05.rhel10"]


@pytest.mark.parametrize("cpu", ["x86-64-v3", "x86-64-v4", "host"])
def test_ca_o13_4_con_x86_64_v3_o_superior_ya_no_hay_aviso(cpu):
    cfg = cfg_iso("local:iso/rhel-10.0.iso", tipo_cpu=cpu)
    assert not [a for a in avisos_so(cfg) if a.codigo == "V-O05.rhel10"]


def test_ca_o13_4_el_aviso_rhel10_solo_aplica_a_linux():
    cfg = cfg_iso("local:iso/rhel-10.0.iso", TipoSO.OTRO)
    assert not [a for a in avisos_so(cfg) if a.codigo == "V-O05.rhel10"]
    assert avisos_so(cfg_base()) == []


# --- RF-O17: importación --------------------------------------------------------------------------


def test_ca_o17_1_el_primer_disco_se_crea_con_import_from_y_tamano_cero():
    p = construir_parametros(cfg_import(), INV)
    assert p["scsi0"] == f"local-lvm:0,import-from={VOLID_IMAGEN},discard=on,ssd=1,iothread=1"
    assert "32" not in p["scsi0"]  # nunca el tamaño del formulario


def test_ca_o17_1_los_demas_discos_se_crean_vacios():
    cfg = cfg_import(cfg={"discos": [Disco("local-lvm", 32), Disco("local-lvm", 16)]})
    p = construir_parametros(cfg, INV)
    assert "import-from" in p["scsi0"] and p["scsi1"].startswith("local-lvm:16,")
    assert "import-from" not in p["scsi1"]


def test_ca_o17_2_en_directorio_el_formato_sigue_la_regla_v_09():
    cfg = cfg_import(cfg={"discos": [Disco("local", 32, formato=FormatoDisco.QCOW2)]})
    assert construir_parametros(cfg, INV)["scsi0"].endswith(",format=qcow2")
    p = construir_parametros(cfg_import(), INV)  # lvmthin: solo raw, sin format
    assert "format=" not in p["scsi0"]


@pytest.mark.parametrize(
    "volid",
    [
        "local:import/x.qcow2,scsi1=local-lvm:1",
        "/mnt/pve/x.qcow2",
        "local:import/x.qcow2,import-from=/etc/passwd",
        "local:iso/x.iso",
        None,
    ],
)
def test_ca_o17_8_la_imagen_se_inserta_solo_si_cumple_la_lista_blanca(volid):
    with pytest.raises(ErrorProxLaunch) as e:
        construir_parametros(cfg_import(volid), INV)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO


def test_ca_o17_9_efidisk0_se_crea_vacio_junto_al_disco_importado():
    p = construir_parametros(cfg_import(cfg={"firmware": Firmware.OVMF}), INV)
    assert p["efidisk0"] == "local-lvm:1,efitype=4m,pre-enrolled-keys=1"
    assert "import-from" not in p["efidisk0"] and p["bios"] == "ovmf"


def test_importar_sin_disco_no_construye_la_peticion():
    with pytest.raises(ErrorProxLaunch):
        construir_parametros(cfg_import(cfg={"con_disco": False, "discos": []}), INV)


def test_la_importacion_no_monta_cd_ni_boot_ni_agente_sin_pedirlo():
    p = construir_parametros(cfg_import(), INV)
    assert "ide2" not in p and "boot" not in p and "agent" not in p


# --- LAB-M4-04 / DEFECTO-LAB-02: claves de Secure Boot según el tipo de SO ------------------------

EFI_SIN_CLAVES = "local-lvm:1,efitype=4m,pre-enrolled-keys=0"
EFI_CON_CLAVES = "local-lvm:1,efitype=4m,pre-enrolled-keys=1"


@pytest.mark.parametrize("tipo", [TipoSO.LINUX, TipoSO.OTRO])
def test_lab_02_linux_y_otro_envian_pre_enrolled_keys_0(tipo):
    cfg = cfg_iso(tipo_so=tipo, firmware=Firmware.OVMF)
    assert construir_parametros(cfg, INV)["efidisk0"] == EFI_SIN_CLAVES


@pytest.mark.parametrize(
    "tipo",
    [
        TipoSO.WINDOWS_11,
        TipoSO.WINDOWS_10,
        TipoSO.WINDOWS_SERVER_2022_2025,
        TipoSO.WINDOWS_SERVER_2016_2019,
    ],
)
def test_lab_02_cada_windows_conserva_pre_enrolled_keys_1(tipo):
    cfg = cfg_iso(tipo_so=tipo, firmware=Firmware.OVMF)
    assert construir_parametros(cfg, INV)["efidisk0"] == EFI_CON_CLAVES


def test_lab_02_sin_tipo_de_so_conserva_pre_enrolled_keys_1_como_en_mvp3():
    cfg = cfg_base(firmware=Firmware.OVMF)
    assert cfg.tipo_so is None
    assert construir_parametros(cfg, INV)["efidisk0"] == EFI_CON_CLAVES


def test_lab_02_el_asistente_de_linux_deja_el_efidisk_sin_claves():
    res = aplicar_asistente(cfg_iso(tipo_so=None), TipoSO.LINUX)
    res.cfg.firmware = Firmware.OVMF
    assert construir_parametros(res.cfg, INV)["efidisk0"] == EFI_SIN_CLAVES
