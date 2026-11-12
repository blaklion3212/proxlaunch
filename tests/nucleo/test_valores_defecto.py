"""Sección 5 de los requisitos: valores por defecto (CA-15.1, CA-16.1, CA-17.1)."""

from proxlaunch.nucleo import valores_defecto as vd
from proxlaunch.nucleo.modelos import (
    Bridge,
    Bus,
    ControladorScsi,
    Firmware,
    FormatoDisco,
    ModeloRed,
    OrigenSO,
)

from .conftest import storage


def test_constantes_de_la_seccion_5():
    assert vd.PUERTO == 8006
    assert vd.REALM == "pam"
    assert vd.SOCKETS == 1
    assert vd.CORES == 2
    assert vd.TIPO_CPU == "x86-64-v2-AES"
    assert vd.MEMORIA_MIB == 2048
    assert vd.TAMANO_DISCO_GIB == 32
    assert vd.TIMEOUT_TAREA_S == 600  # P-05: 10 minutos


def test_ca15_1_y_16_1_configuracion_inicial():
    cfg = vd.configuracion_por_defecto(101, "mv-nueva", "pve1", "local-lvm", "vmbr0")
    assert (cfg.vmid, cfg.nombre, cfg.nodo) == (101, "mv-nueva", "pve1")
    assert cfg.firmware == Firmware.SEABIOS
    assert cfg.sockets == 1
    assert cfg.cores == 2
    assert cfg.tipo_cpu == "x86-64-v2-AES"
    assert cfg.memoria_mib == 2048
    assert cfg.ballooning is None  # no se envía (sección 5)
    assert cfg.con_disco is True
    assert cfg.controlador_scsi == ControladorScsi.VIRTIO_SINGLE
    assert cfg.origen == OrigenSO.DISCO_VACIO


def test_ca16_1_un_disco_scsi_de_32_gib_con_opciones_activadas():
    cfg = vd.configuracion_por_defecto(101, "x", "pve1", "local-lvm", "vmbr0")
    assert len(cfg.discos) == 1
    disco = cfg.discos[0]
    assert (disco.storage, disco.tamano_gib, disco.bus) == ("local-lvm", 32, Bus.SCSI)
    assert disco.formato == FormatoDisco.AUTO
    assert (disco.discard, disco.ssd, disco.iothread) == (True, True, True)


def test_ca17_1_una_interfaz_virtio_sin_vlan():
    cfg = vd.configuracion_por_defecto(101, "x", "pve1", "local-lvm", "vmbr0")
    assert len(cfg.redes) == 1
    assert (cfg.redes[0].modelo, cfg.redes[0].bridge, cfg.redes[0].vlan) == (
        ModeloRed.VIRTIO,
        "vmbr0",
        None,
    )


def test_sin_storage_no_se_agrega_disco_y_sin_bridge_no_se_agrega_red():
    cfg = vd.configuracion_por_defecto(101, "x", "pve1", None, None)
    assert cfg.discos == []
    assert cfg.redes == []


def test_cada_configuracion_tiene_sus_propias_listas():
    a = vd.configuracion_por_defecto(101, "a", "pve1", "s", "vmbr0")
    b = vd.configuracion_por_defecto(102, "b", "pve1", "s", "vmbr0")
    a.discos.append(vd.disco_por_defecto("otro"))
    assert len(b.discos) == 1


# --- bridge por defecto (CA-17.1) ---------------------------------------------------


def test_ca17_1_prefiere_vmbr0_aunque_no_sea_el_primero():
    bridges = [Bridge("vmbr1", "bridge", False), Bridge("vmbr0", "bridge", False)]
    assert vd.bridge_por_defecto(bridges) == "vmbr0"


def test_ca17_1_sin_vmbr0_usa_el_primer_bridge():
    bridges = [Bridge("vmbr5", "bridge", False), Bridge("vmbr2", "OVSBridge", True)]
    assert vd.bridge_por_defecto(bridges) == "vmbr5"


def test_ca17_1_sin_bridges_devuelve_none():
    assert vd.bridge_por_defecto([]) is None


# --- storage por defecto (sección 5) ------------------------------------------------


def test_storage_por_defecto_es_el_de_mayor_espacio_libre_con_images():
    storages = [
        storage("local", "dir", "iso,backup", 900),  # sin images: se ignora
        storage("local-lvm", "lvmthin", "images,rootdir", 150),
        storage("nfs1", "nfs", "images", 500),
    ]
    assert vd.storage_por_defecto(storages) == "nfs1"


def test_storage_por_defecto_ignora_los_inactivos():
    storages = [
        storage("grande", "lvm", "images", 900, activo=False),
        storage("chico", "lvm", "images", 10),
    ]
    assert vd.storage_por_defecto(storages) == "chico"


def test_ca11_9_storage_por_defecto_sin_candidatos_es_none():
    assert vd.storage_por_defecto([storage("local", "dir", "iso,backup", 50)]) is None
    assert vd.storage_por_defecto([]) is None
