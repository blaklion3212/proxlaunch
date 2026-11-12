"""Reglas V-01 a V-17 y V-20 de la configuración de la MV (sección 4 de los requisitos)."""

import pytest

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
from proxlaunch.nucleo.validacion import (
    Severidad,
    formatos_permitidos,
    nombre_dns_valido,
    opciones_permitidas,
    validar_vm,
)

# --- Línea base ---------------------------------------------------------------------


def test_configuracion_base_es_valida(hacer_cfg, inv, caps):
    """CA-19.2 (caso feliz): una configuración correcta no produce problemas."""
    assert validar_vm(hacer_cfg(), inv, caps) == []


# --- V-01 nombre --------------------------------------------------------------------

NOMBRES_VALIDOS = [
    pytest.param("srv-web-01", id="V-01-valido-srv-web-01"),
    pytest.param("db.lab.local", id="V-01-valido-db.lab.local"),
    pytest.param("A1", id="V-01-valido-A1"),
    pytest.param("a" * 63, id="V-01-valido-etiqueta-de-63"),
    pytest.param(".".join(["a" * 63] * 3 + ["a" * 61]), id="V-01-valido-total-253"),
]
NOMBRES_INVALIDOS = [
    pytest.param("srv_web", id="V-01-invalido-guion-bajo"),
    pytest.param("-web", id="V-01-invalido-empieza-con-guion"),
    pytest.param("web-", id="V-01-invalido-termina-con-guion"),
    pytest.param("mi máquina", id="V-01-invalido-acento-y-espacio"),
    pytest.param("maquina ", id="V-01-invalido-espacio-final"),
    pytest.param("", id="V-01-invalido-vacio"),
    pytest.param("a..b", id="V-01-invalido-etiqueta-vacia"),
    pytest.param("a" * 64, id="V-01-invalido-64-letras"),
    pytest.param("web.", id="V-01-invalido-punto-final"),
    pytest.param(".web", id="V-01-invalido-punto-inicial"),
    pytest.param("ñandu", id="V-01-invalido-letra-no-ascii"),
    pytest.param(".".join(["a" * 63] * 3 + ["a" * 62]), id="V-01-invalido-total-254"),
    # RNF-16: un salto de línea no puede colarse en el nombre.
    pytest.param("srv-web\nvmid=101", id="RNF-16-invalido-salto-de-linea-medio"),
    pytest.param("a,b=c&d", id="RNF-16-invalido-separadores"),
]


@pytest.mark.parametrize("nombre", NOMBRES_VALIDOS)
def test_v01_nombre_valido(nombre, hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(nombre=nombre), inv, caps), "V-01") == []
    assert nombre_dns_valido(nombre)


@pytest.mark.parametrize("nombre", NOMBRES_INVALIDOS)
def test_v01_nombre_invalido(nombre, hacer_cfg, inv, caps, con_codigo):
    problemas = validar_vm(hacer_cfg(nombre=nombre), inv, caps)
    assert con_codigo(problemas, "V-01", "nombre")
    assert not nombre_dns_valido(nombre)


def test_v01_rnf16_salto_de_linea_final_es_invalido(hacer_cfg, inv, caps, con_codigo):
    problemas = validar_vm(hacer_cfg(nombre="srv-web\n"), inv, caps)
    assert con_codigo(problemas, "V-01", "nombre")


@pytest.mark.parametrize("valor", [None, 123, ["a"]], ids=["V-01-None", "V-01-int", "V-01-lista"])
def test_v01_nombre_de_tipo_incorrecto(valor):
    assert nombre_dns_valido(valor) is False


# --- V-02 VMID ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "vmid",
    [
        pytest.param(100, id="V-02-valido-minimo-100"),
        pytest.param(101, id="V-02-valido-101"),
        pytest.param(999_999_999, id="V-02-valido-maximo"),
    ],
)
def test_v02_vmid_valido(vmid, hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(vmid=vmid), inv, caps), "V-02") == []


@pytest.mark.parametrize(
    "vmid",
    [
        pytest.param(99, id="V-02-invalido-99"),
        pytest.param(0, id="V-02-invalido-0"),
        pytest.param(-1, id="V-02-invalido--1"),
        pytest.param(1_000_000_000, id="V-02-invalido-1000000000"),
        pytest.param("10a", id="V-02-invalido-10a"),
        pytest.param(1.5, id="V-02-invalido-1.5"),
        pytest.param("100", id="V-02-invalido-cadena-numerica"),
        pytest.param(True, id="V-02-invalido-booleano"),
        pytest.param(None, id="V-02-invalido-None"),
    ],
)
def test_v02_vmid_invalido(vmid, hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(vmid=vmid), inv, caps), "V-02", "vmid")


# --- V-04 nodo ----------------------------------------------------------------------


def test_v04_nodo_en_linea_es_valido(hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(nodo="pve1"), inv, caps), "V-04") == []


@pytest.mark.parametrize(
    "nodo",
    [
        pytest.param("pve2", id="V-04-invalido-sin-conexion"),
        pytest.param("nube", id="V-04-inexistente"),
    ],
)
def test_v04_nodo_no_disponible(nodo, hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(
        validar_vm(hacer_cfg(nodo=nodo, discos=[], con_disco=False), inv, caps), "V-04"
    )


# --- V-05 sockets / cores -----------------------------------------------------------


@pytest.mark.parametrize(
    ("sockets", "cores"),
    [
        pytest.param(1, 1, id="V-05-valido-minimos"),
        pytest.param(4, 128, id="V-05-valido-maximos"),
        pytest.param(2, 4, id="CA-15.2-valido-2x4"),
    ],
)
def test_v05_sockets_cores_validos(sockets, cores, hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(sockets=sockets, cores=cores), inv, caps), "V-05") == []


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        pytest.param("sockets", 0, id="V-05-invalido-sockets-0"),
        pytest.param("sockets", 5, id="V-05-invalido-sockets-5"),
        pytest.param("sockets", 1.5, id="V-05-invalido-sockets-decimal"),
        pytest.param("cores", 0, id="CA-15.3-invalido-cores-0"),
        pytest.param("cores", 129, id="V-05-invalido-cores-129"),
        pytest.param("cores", "2", id="V-05-invalido-cores-cadena"),
    ],
)
def test_v05_sockets_cores_invalidos(campo, valor, hacer_cfg, inv, caps, con_codigo):
    problemas = validar_vm(hacer_cfg(**{campo: valor}), inv, caps)
    assert con_codigo(problemas, "V-05", campo)


# --- V-06 memoria / balloon ---------------------------------------------------------


@pytest.mark.parametrize(
    ("memoria", "balloon"),
    [
        pytest.param(16, None, id="V-06-valido-memoria-16"),
        pytest.param(4096, Ballooning(True, 1024), id="CA-15.5-valido-balloon-1024"),
        pytest.param(4096, Ballooning(True, 4096), id="V-06-valido-minimo-igual-a-memoria"),
        pytest.param(4096, Ballooning(True, 16), id="V-06-valido-minimo-16"),
        pytest.param(4096, Ballooning(False, 99999), id="V-06-valido-balloon-desactivado"),
    ],
)
def test_v06_memoria_y_balloon_validos(memoria, balloon, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(memoria_mib=memoria, ballooning=balloon)
    assert con_codigo(validar_vm(cfg, inv, caps), "V-06") == []


@pytest.mark.parametrize(
    ("memoria", "balloon"),
    [
        pytest.param(15, None, id="V-06-invalido-memoria-15"),
        pytest.param(0, None, id="V-06-invalido-memoria-0"),
        pytest.param("2048", None, id="V-06-invalido-memoria-cadena"),
        pytest.param(1024, Ballooning(True, 2048), id="CA-15.6-invalido-minimo-mayor-que-memoria"),
        pytest.param(4096, Ballooning(True, 15), id="V-06-invalido-minimo-15"),
    ],
)
def test_v06_memoria_y_balloon_invalidos(memoria, balloon, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(memoria_mib=memoria, ballooning=balloon)
    assert con_codigo(validar_vm(cfg, inv, caps), "V-06")


# --- V-07 bus y máximo de dispositivos ----------------------------------------------


def _discos_n(bus, n, storage="nfs1"):
    """n discos de 1 GiB sin opciones que dependan del bus (aisla la regla V-07)."""
    return [Disco(storage, 1, bus=bus, discard=False, ssd=False, iothread=False) for _ in range(n)]


@pytest.mark.parametrize(
    ("bus", "maximo"),
    [
        pytest.param(Bus.SCSI, 31, id="V-07-scsi"),
        pytest.param(Bus.VIRTIO, 16, id="V-07-virtio"),
        pytest.param(Bus.SATA, 6, id="V-07-sata"),
        pytest.param(Bus.IDE, 4, id="V-07-ide"),
    ],
)
def test_v07_maximo_de_dispositivos_por_bus(bus, maximo, hacer_cfg, inv, caps, con_codigo):
    en_el_limite = validar_vm(hacer_cfg(discos=_discos_n(bus, maximo)), inv, caps)
    assert con_codigo(en_el_limite, "V-07") == []
    excedido = validar_vm(hacer_cfg(discos=_discos_n(bus, maximo + 1)), inv, caps)
    assert con_codigo(excedido, "V-07", f"discos[{maximo}].bus")


def test_v07_bus_inexistente_es_invalido(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("local-lvm", 8, bus="nvme")])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-07", "discos[0].bus")


def test_v07_el_maximo_es_por_bus_no_total(hacer_cfg, inv, caps, con_codigo):
    """Mezclar buses no acumula el límite: 4 ide + 6 sata son válidos."""
    discos = _discos_n(Bus.IDE, 4) + _discos_n(Bus.SATA, 6)
    assert con_codigo(validar_vm(hacer_cfg(discos=discos), inv, caps), "V-07") == []


# --- V-08 tamaño de disco -----------------------------------------------------------


def _con_tamano(hacer_cfg, tamano, storage="nfs1"):
    return hacer_cfg(discos=[Disco(storage, tamano)])


@pytest.mark.parametrize(
    "tamano",
    [
        pytest.param(1, id="V-08-valido-1"),
        pytest.param(32, id="V-08-valido-32"),
        pytest.param(65536, id="V-08-valido-65536"),
    ],
)
def test_v08_tamano_valido(tamano, hacer_cfg, inv, caps, con_codigo):
    problemas = validar_vm(_con_tamano(hacer_cfg, tamano), inv, caps)
    assert con_codigo(problemas, "V-08") == []


@pytest.mark.parametrize(
    "tamano",
    [
        pytest.param(0, id="CA-16.6-invalido-0"),
        pytest.param(-5, id="CA-16.6-invalido--5"),
        pytest.param(1.5, id="CA-16.6-invalido-1.5"),
        pytest.param("abc", id="CA-16.6-invalido-abc"),
        pytest.param(65537, id="V-08-invalido-65537"),
        pytest.param(None, id="V-08-invalido-None"),
    ],
)
def test_v08_tamano_invalido(tamano, hacer_cfg, inv, caps, con_codigo):
    problemas = validar_vm(_con_tamano(hacer_cfg, tamano), inv, caps)
    assert con_codigo(problemas, "V-08", "discos[0].tamano_gib")


# --- V-09 formato -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [
        pytest.param("lvmthin", (FormatoDisco.RAW,), id="V-09-lvmthin-solo-raw"),
        pytest.param("lvm", (FormatoDisco.RAW,), id="V-09-lvm-solo-raw"),
        pytest.param("zfspool", (FormatoDisco.RAW,), id="V-09-zfspool-solo-raw"),
        pytest.param("rbd", (FormatoDisco.RAW,), id="V-09-rbd-solo-raw"),
        pytest.param("dir", (FormatoDisco.RAW, FormatoDisco.QCOW2), id="V-09-dir-raw-qcow2"),
        pytest.param("nfs", (FormatoDisco.RAW, FormatoDisco.QCOW2), id="V-09-nfs-raw-qcow2"),
        pytest.param("cifs", (FormatoDisco.RAW, FormatoDisco.QCOW2), id="P-06-cifs-raw-qcow2"),
        pytest.param("btrfs", (FormatoDisco.RAW,), id="P-06-btrfs-solo-raw"),
        pytest.param("glusterfs", (FormatoDisco.RAW,), id="P-06-glusterfs-solo-raw"),
    ],
)
def test_v09_formatos_permitidos_por_backend(tipo, esperado):
    assert tuple(formatos_permitidos(tipo)) == esperado


def test_v09_subvol_nunca_se_ofrece():
    """CA-16.8 / CT-1: ni el modelo ni los formatos permitidos incluyen `subvol`."""
    assert "subvol" not in {f.value for f in FormatoDisco}
    for tipo in ("lvmthin", "dir", "nfs", "zfspool", "cifs", "btrfs"):
        assert "subvol" not in {f.value for f in formatos_permitidos(tipo)}


@pytest.mark.parametrize(
    ("storage", "formato"),
    [
        pytest.param("local-lvm", FormatoDisco.AUTO, id="V-09-valido-lvmthin-auto"),
        pytest.param("local-lvm", FormatoDisco.RAW, id="V-09-valido-lvmthin-raw"),
        pytest.param("dirimg", FormatoDisco.QCOW2, id="V-09-valido-dir-qcow2"),
        pytest.param("nfs1", FormatoDisco.RAW, id="V-09-valido-nfs-raw"),
        pytest.param("cifs1", FormatoDisco.QCOW2, id="P-06-valido-cifs-qcow2"),
    ],
)
def test_v09_formato_valido(storage, formato, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco(storage, 8, formato=formato)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-09") == []


@pytest.mark.parametrize(
    ("storage", "formato"),
    [
        pytest.param("local-lvm", FormatoDisco.QCOW2, id="V-09-invalido-lvmthin-qcow2"),
        pytest.param("zfs1", FormatoDisco.QCOW2, id="V-09-invalido-zfspool-qcow2"),
        pytest.param("lvm1", FormatoDisco.QCOW2, id="V-09-invalido-lvm-qcow2"),
        pytest.param("btrfs1", FormatoDisco.QCOW2, id="P-06-invalido-btrfs-qcow2"),
    ],
)
def test_v09_formato_invalido(storage, formato, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco(storage, 8, formato=formato)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-09", "discos[0].formato")


def test_v09_al_cambiar_de_storage_se_revalida(hacer_cfg, inv, caps, con_codigo):
    """CA-16.5: qcow2 deja de ser válido al pasar de un storage de directorio a LVM-thin."""
    en_dir = hacer_cfg(discos=[Disco("dirimg", 8, formato=FormatoDisco.QCOW2)])
    assert con_codigo(validar_vm(en_dir, inv, caps), "V-09") == []
    en_dir.discos[0].storage = "local-lvm"
    assert con_codigo(validar_vm(en_dir, inv, caps), "V-09")


# --- V-10 scsihw --------------------------------------------------------------------


@pytest.mark.parametrize("ctrl", list(ControladorScsi), ids=lambda c: f"V-10-valido-{c.value}")
def test_v10_controlador_valido(ctrl, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(controlador_scsi=ctrl)
    assert con_codigo(validar_vm(cfg, inv, caps), "V-10") == []


def test_v10_controlador_desconocido_es_invalido(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(controlador_scsi="controlador-inexistente")
    assert con_codigo(validar_vm(cfg, inv, caps), "V-10", "controlador_scsi")


def test_v10_valor_por_defecto_es_virtio_scsi_single(hacer_cfg):
    assert hacer_cfg().controlador_scsi == "virtio-scsi-single"


# --- V-11 IO Thread -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("bus", "ctrl"),
    [
        pytest.param(Bus.VIRTIO, ControladorScsi.VIRTIO_SINGLE, id="V-11-valido-virtio"),
        pytest.param(Bus.SCSI, ControladorScsi.VIRTIO_SINGLE, id="V-11-valido-scsi-single"),
    ],
)
def test_v11_iothread_permitido(bus, ctrl, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(
        controlador_scsi=ctrl,
        discos=[Disco("nfs1", 8, bus=bus, ssd=False, iothread=True)],
    )
    assert con_codigo(validar_vm(cfg, inv, caps), "V-11") == []
    assert opciones_permitidas(cfg.discos[0], ctrl).iothread is True


@pytest.mark.parametrize(
    ("bus", "ctrl"),
    [
        pytest.param(Bus.SATA, ControladorScsi.VIRTIO_SINGLE, id="V-11-invalido-sata"),
        pytest.param(Bus.IDE, ControladorScsi.VIRTIO_SINGLE, id="V-11-invalido-ide"),
        pytest.param(Bus.SCSI, ControladorScsi.VIRTIO_PCI, id="V-11-invalido-scsi-virtio-pci"),
    ],
)
def test_v11_iothread_no_permitido(bus, ctrl, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(
        controlador_scsi=ctrl,
        discos=[Disco("nfs1", 8, bus=bus, discard=False, iothread=True)],
    )
    assert con_codigo(validar_vm(cfg, inv, caps), "V-11", "discos[0].iothread")
    assert opciones_permitidas(cfg.discos[0], ctrl).iothread is False


def test_v11_iothread_desmarcado_no_genera_problema(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=Bus.SATA, discard=False, iothread=False)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-11") == []


# --- V-12 SSD -----------------------------------------------------------------------


@pytest.mark.parametrize("bus", [Bus.SCSI, Bus.SATA, Bus.IDE], ids=lambda b: f"V-12-valido-{b}")
def test_v12_ssd_permitido(bus, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=bus, discard=False, iothread=False, ssd=True)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-12") == []
    assert opciones_permitidas(cfg.discos[0], cfg.controlador_scsi).ssd is True


def test_v12_ssd_en_virtio_es_invalido(hacer_cfg, inv, caps, con_codigo):
    """CA-16.4 / CT-4: virtio + ssd no es válido."""
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=Bus.VIRTIO, ssd=True)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-12", "discos[0].ssd")
    assert opciones_permitidas(cfg.discos[0], cfg.controlador_scsi).ssd is False


# --- V-13 discard -------------------------------------------------------------------


@pytest.mark.parametrize("bus", [Bus.SCSI, Bus.SATA, Bus.VIRTIO], ids=lambda b: f"V-13-valido-{b}")
def test_v13_discard_permitido(bus, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=bus, discard=True, ssd=False, iothread=False)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-13") == []
    assert opciones_permitidas(cfg.discos[0], cfg.controlador_scsi).discard is True


def test_v13_discard_es_independiente_de_ssd(hacer_cfg, inv, caps, con_codigo):
    """CT-4: discard en virtio sin ssd es válido; ssd sin discard en scsi también."""
    virtio = hacer_cfg(discos=[Disco("nfs1", 8, bus=Bus.VIRTIO, discard=True, ssd=False)])
    scsi = hacer_cfg(discos=[Disco("nfs1", 8, bus=Bus.SCSI, discard=False, ssd=True)])
    for cfg in (virtio, scsi):
        problemas = validar_vm(cfg, inv, caps)
        assert con_codigo(problemas, "V-12") == []
        assert con_codigo(problemas, "V-13") == []


def test_v13_a2_discard_en_ide_se_permite(hacer_cfg, inv, caps, con_codigo):
    """Aclaración A-2 (tras F1): la API admite discard en ide."""
    cfg = hacer_cfg(discos=[Disco("nfs1", 8, bus=Bus.IDE, discard=True, ssd=False, iothread=False)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-13") == []


# --- V-14 espacio -------------------------------------------------------------------


def test_v14_suma_dentro_del_libre_es_valida(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("dirimg", 60), Disco("dirimg", 40)])  # 100 GiB libres
    problemas = validar_vm(cfg, inv, caps)
    assert con_codigo(problemas, "V-14") == []
    assert con_codigo(problemas, "V-14.thin") == []


def test_v14_suma_excede_en_no_thin_bloquea(hacer_cfg, inv, caps, con_codigo):
    """CA-16.7: dos discos del mismo storage se suman (60 + 50 > 100)."""
    cfg = hacer_cfg(discos=[Disco("dirimg", 60), Disco("dirimg", 50)])
    problemas = con_codigo(validar_vm(cfg, inv, caps), "V-14")
    assert len(problemas) == 1
    assert problemas[0].severidad == Severidad.ERROR


def test_v14_un_solo_disco_mayor_que_el_libre_bloquea(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("lvm1", 41)])  # lvm (no thin) con 40 GiB libres
    assert con_codigo(validar_vm(cfg, inv, caps), "V-14")


def test_v14_en_thin_solo_advierte(hacer_cfg, inv, caps, con_codigo):
    """P-01 / CT-5: en lvmthin, zfspool o rbd el exceso es un aviso no bloqueante."""
    cfg = hacer_cfg(discos=[Disco("local-lvm", 100), Disco("local-lvm", 100)])  # 150 libres
    problemas = validar_vm(cfg, inv, caps)
    assert con_codigo(problemas, "V-14") == []
    avisos = con_codigo(problemas, "V-14.thin")
    assert len(avisos) == 1
    assert avisos[0].severidad == Severidad.AVISO


def test_v14_zfspool_tambien_es_thin(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("zfs1", 201)])
    problemas = validar_vm(cfg, inv, caps)
    assert con_codigo(problemas, "V-14") == []
    assert con_codigo(problemas, "V-14.thin")


def test_v14_storages_distintos_no_se_suman(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("dirimg", 90), Disco("lvm1", 35)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-14") == []


def test_v14_usa_el_storage_del_nodo_destino(hacer_cfg, inv, caps, con_codigo):
    """D-08: pve1 tiene 150 GiB en local-lvm; el exceso se mide en el nodo elegido."""
    cfg = hacer_cfg(discos=[Disco("dirimg", 100)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-14") == []  # exacto = permitido


# --- V-15 VLAN ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "vlan",
    [
        pytest.param(None, id="V-15-valido-sin-vlan"),
        pytest.param(1, id="V-15-valido-1"),
        pytest.param(120, id="CA-17.3-valido-120"),
        pytest.param(4094, id="V-15-valido-4094"),
    ],
)
def test_v15_vlan_valida(vlan, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(redes=[InterfazRed("vmbr1", vlan=vlan)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-15") == []


@pytest.mark.parametrize(
    "vlan",
    [
        pytest.param(0, id="CA-17.4-invalido-0"),
        pytest.param(4095, id="CA-17.4-invalido-4095"),
        pytest.param("abc", id="CA-17.4-invalido-abc"),
        pytest.param(-3, id="V-15-invalido-negativo"),
        pytest.param(1.5, id="V-15-invalido-decimal"),
    ],
)
def test_v15_vlan_invalida(vlan, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(redes=[InterfazRed("vmbr1", vlan=vlan)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-15", "redes[0].vlan")


# --- V-16 bridge --------------------------------------------------------------------


@pytest.mark.parametrize(
    "bridge",
    [
        pytest.param("vmbr0", id="V-16-valido-bridge"),
        pytest.param("vmbr1", id="CA-11.5-valido-OVSBridge"),
    ],
)
def test_v16_bridge_valido(bridge, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(redes=[InterfazRed(bridge)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-16") == []


@pytest.mark.parametrize(
    "bridge",
    [
        pytest.param("vmbr9", id="CA-17.5-invalido-no-existe"),
        pytest.param("eno1", id="CA-11.5-invalido-interfaz-fisica"),
        pytest.param("vmbr,9", id="V-16-invalido-coma-en-el-nombre"),
        pytest.param("vmbr=0", id="V-16-invalido-igual-en-el-nombre"),
        pytest.param("", id="V-16-invalido-vacio"),
    ],
)
def test_v16_bridge_invalido(bridge, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(redes=[InterfazRed(bridge)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-16", "redes[0].bridge")


def test_v16_bridge_se_valida_en_el_nodo_destino(hacer_cfg, inv, caps, con_codigo):
    """D-08: vmbr1 existe en pve1 pero no en pve3."""
    cfg = hacer_cfg(nodo="pve3", discos=[], con_disco=False, redes=[InterfazRed("vmbr1")])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-16", "redes[0].bridge")


def test_v16_modelo_de_tarjeta_desconocido_es_invalido(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(redes=[InterfazRed("vmbr0", modelo="ne2k")])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-16", "redes[0].modelo")


@pytest.mark.parametrize("modelo", list(ModeloRed), ids=lambda m: f"CA-17.6-valido-{m.value}")
def test_v16_modelos_de_tarjeta_validos(modelo, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(redes=[InterfazRed("vmbr0", modelo=modelo)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-16") == []


# --- V-17 storage -------------------------------------------------------------------


@pytest.mark.parametrize(
    "storage",
    [
        pytest.param("local", id="V-17-invalido-sin-images"),
        pytest.param("inactivo", id="CA-11.3-invalido-inactivo"),
        pytest.param("no-existe", id="V-17-invalido-inexistente"),
    ],
)
def test_v17_storage_no_disponible(storage, hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco(storage, 8)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-17", "discos[0].storage")


def test_v17_storage_con_images_activo_es_valido(hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(), inv, caps), "V-17") == []


def test_v17_storage_debe_existir_en_el_nodo_destino(hacer_cfg, inv, caps, con_codigo):
    """D-08: nfs1 existe en pve1 pero no en pve2 (y pve2 está además sin conexión)."""
    cfg = hacer_cfg(nodo="pve2", discos=[Disco("nfs1", 8)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-17", "discos[0].storage")


# --- RF-14 firmware y efidisk0 ------------------------------------------------------


def test_ca14_4_ovmf_sin_storage_con_images_se_bloquea(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(nodo="pve3", firmware=Firmware.OVMF, discos=[], con_disco=False, redes=[])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-17", "storage_efi")


def test_ca14_4_seabios_sin_storage_ni_disco_es_valido(hacer_cfg, inv, caps):
    """CA-11.9: sin almacenamiento, SeaBIOS con 'sin disco' se puede crear."""
    cfg = hacer_cfg(nodo="pve3", discos=[], con_disco=False, redes=[])
    assert validar_vm(cfg, inv, caps) == []


def test_ca14_2_ovmf_con_disco_valido_no_da_problemas(hacer_cfg, inv, caps):
    assert validar_vm(hacer_cfg(firmware=Firmware.OVMF), inv, caps) == []


def test_ca14_3_ovmf_con_storage_efi_invalido(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(firmware=Firmware.OVMF, storage_efi="local")
    assert con_codigo(validar_vm(cfg, inv, caps), "V-17", "storage_efi")


# --- V-20 origen y sin disco --------------------------------------------------------


def test_v20_origen_disco_vacio_es_valido(hacer_cfg, inv, caps, con_codigo):
    assert con_codigo(validar_vm(hacer_cfg(), inv, caps), "V-20") == []


def test_v20_origen_distinto_se_detecta_aunque_se_asigne_despues(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg()
    cfg.origen = "iso"
    assert con_codigo(validar_vm(cfg, inv, caps), "V-20", "origen")


def test_ca16_3_sin_disco_ignora_la_lista_de_discos(hacer_cfg, inv, caps):
    """CA-16.3: con 'Sin disco' los discos de la lista no se validan."""
    cfg = hacer_cfg(con_disco=False, discos=[Disco("storage-roto", 0)])
    assert validar_vm(cfg, inv, caps) == []


def test_validar_vm_devuelve_todos_los_problemas(hacer_cfg, inv, caps):
    """La validación no se detiene en el primer error (CA-19.2: cada error junto a su campo)."""
    cfg = hacer_cfg(nombre="-x", vmid=1, sockets=9, cores=0, memoria_mib=1)
    campos = {p.campo for p in validar_vm(cfg, inv, caps)}
    assert {"nombre", "vmid", "sockets", "cores", "memoria_mib"} <= campos


def test_los_discos_y_redes_se_numeran_en_el_campo(hacer_cfg, inv, caps, con_codigo):
    cfg = hacer_cfg(discos=[Disco("dirimg", 8), Disco("dirimg", 0)])
    assert con_codigo(validar_vm(cfg, inv, caps), "V-08", "discos[1].tamano_gib")
