"""Creación real de MVs en el laboratorio (VMIDs 9000-9099, destruidas al terminar).

Derivadas de RF-13 a RF-20 y los CA de creación. Tras crear se lee la configuración real
y se comprueban los parámetros enviados (f1 §6).
"""

from __future__ import annotations

import dataclasses
import re
import threading
from collections.abc import Iterator

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, Firmware, InterfazRed
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.servicios.descubrimiento import descubrir

from . import apoyo_lab as lab

pytestmark = pytest.mark.integracion

PLANTILLA = "alpine-3.23-default_20261105_amd64.tar.xz"
VMID_CT = 9050


def _cfg(vmid: int, **kw) -> ConfiguracionVM:
    base = {
        "vmid": vmid,
        "nombre": f"plc-{vmid}",
        "nodo": lab.NODO,
        "discos": [Disco(storage="lab-lvmthin", tamano_gib=2)],
        "redes": [InterfazRed(bridge="vmbr0")],
    }
    base.update(kw)
    return ConfiguracionVM(**base)


def _crear(sesion, cfg, inv=None):
    inv = inv or descubrir(sesion)
    etapas: list[Etapa] = []
    enviados: list[str] = []
    r = ServicioCreacion(sesion, RelojReal()).crear(
        cfg, inv, etapas.append, threading.Event(), al_enviar=enviados.append
    )
    return r, etapas, enviados, inv


@pytest.fixture
def ct_9050() -> Iterator[int]:
    """Contenedor real (CT 9050) para comprobar el choque de VMID entre CT y MV."""
    descargada = False
    if PLANTILLA not in lab.ssh("sudo pveam list local"):
        lab.ssh(f"sudo pveam download local {PLANTILLA}", timeout=300)
        descargada = True
    lab.ssh(f"sudo pct destroy {VMID_CT} --purge 1", comprobar=False)  # restos previos
    lab.ssh(
        f"sudo pct create {VMID_CT} local:vztmpl/{PLANTILLA} --rootfs lab-lvmthin:1 "
        "--hostname ctprueba --unprivileged 1"
    )
    try:
        yield VMID_CT
    finally:
        lab.ssh(f"sudo pct destroy {VMID_CT} --purge 1", comprobar=False)
        if descargada:
            lab.ssh(f"sudo pveam remove local:vztmpl/{PLANTILLA}", comprobar=False)


# --- Camino feliz --------------------------------------------------------------------


def test_seabios_en_lvmthin_sin_format(sesion_plc, vms):
    vmid = vms(9001)
    r, etapas, enviados, _ = _crear(sesion_plc, _cfg(vmid))
    assert r.desenlace == Desenlace.OK, r
    assert r.error is None
    assert etapas == [
        Etapa.VALIDANDO,
        Etapa.ENVIANDO,
        Etapa.CREANDO,
        Etapa.COMPROBANDO,
        Etapa.LISTO,
    ]
    assert enviados == [r.upid]
    assert r.upid.startswith(f"UPID:{lab.NODO}:") and f":qmcreate:{vmid}:plc@pve!t1:" in r.upid

    c = sesion_plc.cliente.config_vm(lab.NODO, vmid)
    assert c["name"] == f"plc-{vmid}"
    assert (c["sockets"], c["cores"], c["memory"]) == (1, 2, "2048")
    assert c["cpu"] == "x86-64-v2-AES"
    assert c["scsihw"] == "virtio-scsi-single"
    assert "bios" not in c  # SeaBIOS es el valor por defecto: no se envía
    assert "efidisk0" not in c
    scsi0 = c["scsi0"]
    assert scsi0.startswith(f"lab-lvmthin:vm-{vmid}-disk-0,")
    for opcion in ("discard=on", "iothread=1", "size=2G", "ssd=1"):
        assert opcion in scsi0
    assert "format=" not in scsi0
    assert re.fullmatch(r"virtio=[0-9A-F:]{17},bridge=vmbr0", c["net0"])
    # La verdad independiente: el volumen es raw en lvmthin.
    vols = lab.ssh(f"sudo pvesm list lab-lvmthin --vmid {vmid}")
    assert f"vm-{vmid}-disk-0" in vols and " raw " in vols


def test_ovmf_en_local_con_efidisk_qcow2_y_claves_precargadas(sesion_plc, vms):
    vmid = vms(9002)
    cfg = _cfg(
        vmid,
        firmware=Firmware.OVMF,
        discos=[Disco(storage="local", tamano_gib=1)],
    )
    r, _, _, _ = _crear(sesion_plc, cfg)
    assert r.desenlace == Desenlace.OK, r
    c = sesion_plc.cliente.config_vm(lab.NODO, vmid)
    assert c["bios"] == "ovmf"
    assert c["machine"] == "q35"
    efi = c["efidisk0"]
    assert efi.startswith(f"local:{vmid}/vm-{vmid}-disk-0.qcow2,")
    assert "efitype=4m" in efi
    assert "pre-enrolled-keys=1" in efi
    assert c["scsi0"].startswith(f"local:{vmid}/vm-{vmid}-disk-1.qcow2,")
    vols = lab.ssh(f"sudo pvesm list local --vmid {vmid}")
    assert vols.count("qcow2") >= 2  # efidisk y disco, ambos qcow2 (format=qcow2 aceptado)


def test_ovmf_en_lvmthin_el_efidisk_es_raw_sin_format(sesion_plc, vms):
    vmid = vms(9003)
    r, _, _, _ = _crear(sesion_plc, _cfg(vmid, firmware=Firmware.OVMF))
    assert r.desenlace == Desenlace.OK, r
    efi = sesion_plc.cliente.config_vm(lab.NODO, vmid)["efidisk0"]
    assert efi.startswith(f"lab-lvmthin:vm-{vmid}-disk-0,")
    assert "efitype=4m" in efi and "pre-enrolled-keys=1" in efi
    assert "format=" not in efi


def test_bridge_vlan_aware_con_etiqueta(sesion_plc, vms):
    vmid = vms(9004)
    cfg = _cfg(vmid, redes=[InterfazRed(bridge="vmbr1", vlan=5)])
    r, _, _, _ = _crear(sesion_plc, cfg)
    assert r.desenlace == Desenlace.OK, r
    net0 = sesion_plc.cliente.config_vm(lab.NODO, vmid)["net0"]
    assert "bridge=vmbr1" in net0 and "tag=5" in net0


def test_dos_discos_y_dos_redes(sesion_plc, vms):
    vmid = vms(9005)
    cfg = _cfg(
        vmid,
        discos=[Disco("lab-lvmthin", 1), Disco("local", 1)],
        redes=[InterfazRed("vmbr0"), InterfazRed("vmbr1", vlan=7)],
    )
    r, _, _, _ = _crear(sesion_plc, cfg)
    assert r.desenlace == Desenlace.OK, r
    c = sesion_plc.cliente.config_vm(lab.NODO, vmid)
    assert c["scsi0"].startswith("lab-lvmthin:") and c["scsi1"].startswith("local:")
    assert "bridge=vmbr0" in c["net0"] and "tag=7" in c["net1"]


def test_mv_sin_disco(sesion_plc, vms):
    vmid = vms(9006)
    r, _, _, _ = _crear(sesion_plc, _cfg(vmid, con_disco=False, discos=[]))
    assert r.desenlace == Desenlace.OK, r
    c = sesion_plc.cliente.config_vm(lab.NODO, vmid)
    assert not any(k.startswith(("scsi", "virtio", "sata", "ide")) and k != "scsihw" for k in c)


def test_la_tarea_real_se_puede_seguir_y_comprobar_despues(sesion_plc, vms):
    vmid = vms(9007)
    cfg = _cfg(vmid)
    r, _, _, inv = _crear(sesion_plc, cfg)
    svc = ServicioCreacion(sesion_plc, RelojReal())
    r2 = svc.seguir(cfg, r.upid, threading.Event(), inv=inv)
    assert r2.desenlace == Desenlace.OK
    r3 = svc.comprobar_ahora(cfg, r.upid, inv=inv)
    assert r3.desenlace == Desenlace.OK
    estado = sesion_plc.cliente.estado_tarea(lab.NODO, r.upid)
    assert estado.terminada and estado.exitstatus == "OK"
    log = sesion_plc.cliente.log_tarea(lab.NODO, r.upid)
    assert log and log[-1] == "TASK OK"


def test_log_con_limite_500_es_aceptado_por_proxmox(sesion_plc, vms):
    # El cliente pide start=0&limit=500 (LINEAS_LOG_TAREA, marcado [LAB]): no da 400.
    vmid = vms(9008)
    r, _, _, _ = _crear(sesion_plc, _cfg(vmid))
    lineas = sesion_plc.cliente.log_tarea(lab.NODO, r.upid)
    assert any("successfully created disk" in x for x in lineas)


# --- existe_vm ------------------------------------------------------------------------


def test_existe_vm_true_tras_crear_y_false_si_no_existe(sesion_plc, vms):
    vmid = vms(9009)
    svc = ServicioCreacion(sesion_plc, RelojReal())
    assert svc.existe_vm(_cfg(vmid)) is False
    r, _, _, _ = _crear(sesion_plc, _cfg(vmid))
    assert r.desenlace == Desenlace.OK
    assert svc.existe_vm(_cfg(vmid)) is True


def test_existe_vm_con_vmid_de_contenedor_es_false(sesion_plc, ct_9050):
    # Un CT no es una MV: /qemu/<id>/config no existe aunque el VMID esté ocupado.
    assert ServicioCreacion(sesion_plc, RelojReal()).existe_vm(_cfg(ct_9050)) is False


# --- VMID ocupado ---------------------------------------------------------------------


def test_vmid_ocupado_por_mv_se_detecta_antes_de_enviar(sesion_plc, vms):
    vmid = vms(9010)
    r1, _, _, inv = _crear(sesion_plc, _cfg(vmid))
    assert r1.desenlace == Desenlace.OK
    r2, etapas, enviados, _ = _crear(sesion_plc, _cfg(vmid), inv)
    assert r2.desenlace == Desenlace.ERROR
    assert r2.error.codigo == CodigoError.VMID_OCUPADO
    assert r2.error.params["vmid"] == str(vmid)
    assert int(r2.error.params["siguiente"]) >= 100  # CA-13.3: propone el siguiente libre
    assert r2.upid is None and enviados == []
    assert Etapa.ENVIANDO not in etapas


def test_nextid_con_vmid_ocupado_da_400_y_vmid_ocupado(sesion_plc, vms):
    vmid = vms(9011)
    _crear(sesion_plc, _cfg(vmid))
    with pytest.raises(ErrorProxLaunch) as e:
        sesion_plc.cliente.proximo_vmid(vmid)
    assert e.value.codigo == CodigoError.VMID_OCUPADO
    assert e.value.params["vmid"] == str(vmid)
    # PVE 9.2.32+: "guest ID N is already in use"; antes: "VM N already exists".
    assert (
        f"guest ID {vmid} is already in use" in e.value.detalle_tecnico
        or f"VM {vmid} already exists" in e.value.detalle_tecnico
    )


def test_post_directo_con_vmid_ocupado_da_vmid_ocupado_con_nodo(sesion_plc, vms):
    from proxlaunch.nucleo.constructor_peticion import construir_parametros

    vmid = vms(9012)
    r, _, _, inv = _crear(sesion_plc, _cfg(vmid))
    assert r.desenlace == Desenlace.OK
    with pytest.raises(ErrorProxLaunch) as e:
        sesion_plc.cliente.crear_vm(lab.NODO, construir_parametros(_cfg(vmid), inv))
    assert e.value.codigo == CodigoError.VMID_OCUPADO
    assert e.value.params == {"vmid": str(vmid), "nodo": lab.NODO}
    assert f"VM {vmid} already exists on node '{lab.NODO}'" in e.value.detalle_tecnico


def test_vmid_ocupado_por_contenedor_nextid_dice_vm(sesion_plc, ct_9050):
    # nextid?vmid= escribe "VM <n> already exists" aunque el VMID sea de un CT.
    with pytest.raises(ErrorProxLaunch) as e:
        sesion_plc.cliente.proximo_vmid(ct_9050)
    assert e.value.codigo == CodigoError.VMID_OCUPADO
    # PVE 9.2.32+: "guest ID N is already in use"; antes: "VM N already exists".
    assert (
        f"guest ID {ct_9050} is already in use" in e.value.detalle_tecnico
        or f"VM {ct_9050} already exists" in e.value.detalle_tecnico
    )


def test_vmid_ocupado_por_contenedor_post_dice_ct(sesion_plc, ct_9050):
    from proxlaunch.nucleo.constructor_peticion import construir_parametros

    inv = descubrir(sesion_plc)
    with pytest.raises(ErrorProxLaunch) as e:
        sesion_plc.cliente.crear_vm(lab.NODO, construir_parametros(_cfg(ct_9050), inv))
    assert e.value.codigo == CodigoError.VMID_OCUPADO
    assert e.value.params == {"vmid": str(ct_9050), "nodo": lab.NODO}
    assert f"CT {ct_9050} already exists on node '{lab.NODO}'" in e.value.detalle_tecnico


def test_servicio_crear_con_vmid_de_contenedor_da_vmid_ocupado(sesion_plc, ct_9050):
    r, _, enviados, _ = _crear(sesion_plc, _cfg(ct_9050))
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.VMID_OCUPADO
    assert enviados == []


# --- Espacio --------------------------------------------------------------------------


@pytest.fixture
def storage_lvm_grueso() -> Iterator[str]:
    """Storage LVM no thin sobre el VG `labvg` (con ~3 GiB libres), solo para esta prueba."""
    lab.ssh("sudo pvesm remove lab-lvm", comprobar=False)
    lab.ssh(f"sudo pvesm add lvm lab-lvm --vgname {lab.VG_LAB} --content images")
    try:
        yield "lab-lvm"
    finally:
        lab.ssh("sudo pvesm remove lab-lvm", comprobar=False)


def test_disco_mayor_que_el_libre_en_storage_grueso_lo_frena_la_validacion_local(
    sesion_plc, storage_lvm_grueso, vms
):
    vmid = vms(9013)
    inv = descubrir(sesion_plc)
    lvm = next(s for s in inv.storages[lab.NODO] if s.id == storage_lvm_grueso)
    assert lvm.tipo == "lvm" and not lvm.es_thin and lvm.libre_bytes < 4 * 1024**3
    cfg = _cfg(vmid, discos=[Disco(storage_lvm_grueso, 10)])
    r, _, enviados, _ = _crear(sesion_plc, cfg, inv)
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.PARAMETRO_INVALIDO
    assert enviados == []
    assert ServicioCreacion(sesion_plc, RelojReal()).existe_vm(cfg) is False


def test_sin_espacio_real_con_inventario_desactualizado(sesion_plc, storage_lvm_grueso, vms):
    vmid = vms(9014)
    inv = descubrir(sesion_plc)
    # Inventario "viejo": cree que sobra espacio; Proxmox es quien dice la verdad.
    inflado = tuple(
        dataclasses.replace(s, libre_bytes=100 * 1024**3) if s.id == storage_lvm_grueso else s
        for s in inv.storages[lab.NODO]
    )
    inv.storages[lab.NODO] = inflado
    cfg = _cfg(vmid, discos=[Disco(storage_lvm_grueso, 10)])
    r, _, _, _ = _crear(sesion_plc, cfg, inv)
    assert r.desenlace == Desenlace.ERROR, r
    assert r.error.codigo == CodigoError.SIN_ESPACIO
    # Proxmox habla del grupo de volúmenes `labvg`; ProxLaunch lo traduce al id del storage.
    assert r.error.params["storage"] == storage_lvm_grueso
    assert r.error.params["vg"] == lab.VG_LAB
    assert "insufficient free space" in r.error.detalle_tecnico
    assert r.upid is not None
    assert ServicioCreacion(sesion_plc, RelojReal()).existe_vm(cfg) is False  # no quedó nada


def test_sin_espacio_con_ovmf_el_efidisk_va_en_el_mismo_storage(
    sesion_plc, storage_lvm_grueso, vms
):
    vmid = vms(9015)
    inv = descubrir(sesion_plc)
    inv.storages[lab.NODO] = tuple(
        dataclasses.replace(s, libre_bytes=100 * 1024**3) if s.id == storage_lvm_grueso else s
        for s in inv.storages[lab.NODO]
    )
    cfg = _cfg(vmid, firmware=Firmware.OVMF, discos=[Disco(storage_lvm_grueso, 10)])
    r, _, _, _ = _crear(sesion_plc, cfg, inv)
    assert r.desenlace in (Desenlace.ERROR, Desenlace.PARCIAL), r
    assert r.error.codigo == CodigoError.SIN_ESPACIO
    assert storage_lvm_grueso in r.error.params["storage"].split(",")


def test_dir_no_valida_espacio_y_crea_un_disco_disperso_mayor_que_el_libre(sesion_plc, vms):
    # Hecho real de PVE 9.2: en un storage de directorio (qcow2/raw) el disco es disperso y
    # no se comprueba el espacio libre. Solo la regla V-14 local protege al usuario.
    vmid = vms(9016)
    inv = descubrir(sesion_plc)
    local = next(s for s in inv.storages[lab.NODO] if s.id == "local")
    pedido = int(local.libre_bytes / 1024**3) + 40
    inv.storages[lab.NODO] = tuple(
        dataclasses.replace(s, libre_bytes=10**15) if s.id == "local" else s
        for s in inv.storages[lab.NODO]
    )
    cfg = _cfg(vmid, discos=[Disco("local", pedido)])
    r, _, _, _ = _crear(sesion_plc, cfg, inv)
    assert r.desenlace == Desenlace.OK, r


def test_disco_mayor_que_el_libre_en_local_lo_frena_la_validacion_local(sesion_plc, vms):
    vmid = vms(9017)
    inv = descubrir(sesion_plc)
    local = next(s for s in inv.storages[lab.NODO] if s.id == "local")
    cfg = _cfg(vmid, discos=[Disco("local", int(local.libre_bytes / 1024**3) + 40)])
    r, _, enviados, _ = _crear(sesion_plc, cfg, inv)
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.PARAMETRO_INVALIDO
    assert r.error.params["regla"] == "V-14"
    assert enviados == []
