"""Contrato con las respuestas REALES de PVE 9.2 capturadas en el laboratorio.

Usa ``tests/datos/respuestas/9.2-lab/`` (saneadas; ver capturar_respuestas.py). No
necesita red: comprueba que los analizadores del núcleo entienden lo que Proxmox
devuelve de verdad y que las capturas no contienen secretos.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from proxlaunch.nucleo.api.autenticacion import (
    AutenticadorToken,
    DesafioTFA,
    iniciar_sesion_ticket,
)
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.traductor_errores import traducir_exitstatus, traducir_http
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.conexion import CredencialToken, Ticket
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo_api import TransporteFalso

DIR = Path(__file__).resolve().parents[1] / "datos" / "respuestas" / "9.2-lab"
HTTP = json.loads((DIR / "_http.json").read_text(encoding="utf-8"))


def cuerpo(nombre: str):
    return json.loads((DIR / f"{nombre}.json").read_text(encoding="utf-8"))


def dato(nombre: str):
    return cuerpo(nombre)["data"]


def traducir(nombre: str, **kw):
    meta = HTTP[f"{nombre}.json"]
    return traducir_http(
        meta["estado_http"],
        meta["motivo_http"],
        (DIR / f"{nombre}.json").read_text(encoding="utf-8"),
        **kw,
    )


def cliente(transporte: TransporteFalso) -> ClienteProxmox:
    return ClienteProxmox(
        transporte, AutenticadorToken(CredencialToken("plc@pve!t1", "x" * 8)), RelojSimulado()
    )


# --- Higiene: las capturas no llevan secretos -----------------------------------------


def test_las_capturas_existen():
    assert len(list(DIR.glob("*.json"))) >= 40


def test_ninguna_captura_contiene_secretos_conocidos_del_laboratorio():
    secretos = Path.home() / "aprovprox-lab" / "secretos"
    valores = []
    for nombre in ("root_pam.pass", "aprovprox_pve.pass"):
        if (secretos / nombre).exists():
            valores.append((secretos / nombre).read_text().strip())
    if (secretos / "token.txt").exists():
        valores.append((secretos / "token.txt").read_text().strip().rsplit("=", 1)[1])
    for f in DIR.glob("*.json"):
        texto = f.read_text(encoding="utf-8")
        for v in valores:
            assert v not in texto, f"secreto en {f.name}"


@pytest.mark.parametrize("archivo", sorted(p.name for p in DIR.glob("*.json")))
def test_captura_saneada(archivo):
    texto = (DIR / archivo).read_text(encoding="utf-8")
    # Tickets: la firma siempre es el marcador.
    for m in re.finditer(r"PVE:[^\"\s]*", texto):
        assert m.group(0).endswith("::FIRMA_SANEADA"), m.group(0)[:40]
    # CSRF: siempre el marcador.
    for m in re.finditer(r'"CSRFPreventionToken":\s*"([^"]*)"', texto):
        assert m.group(1) == "00000000:CSRF_SANEADO"
    # Huellas de certificado y UPIDs reales.
    assert not re.search(r"(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}", texto)
    for m in re.finditer(r"UPID:[^\"\s,]+", texto):
        assert re.match(r"UPID:pve-lab:0000000\d:0000000\d:0000000\d:", m.group(0)), m.group(0)
    assert "SECRETO_SANEADO" in texto or "SECRETO" not in texto


# --- Autenticación real ----------------------------------------------------------------


def test_ticket_completo_real_se_entiende():
    t = TransporteFalso().en("POST", "/access/ticket", dato("ticket_completo"))
    r = iniciar_sesion_ticket(t, "plc", "pve", "x", reloj=RelojSimulado())
    assert isinstance(r, Ticket)
    assert r.usuario == "plc@pve"


def test_desafio_tfa_real_con_totp_y_recuperacion():
    t = TransporteFalso().en("POST", "/access/ticket", dato("ticket_tfa_totp_recovery"))
    r = iniciar_sesion_ticket(t, "tfacap", "pve", "x", reloj=RelojSimulado())
    assert isinstance(r, DesafioTFA)
    assert (r.totp, r.recuperacion, r.no_soportados) == (True, True, ())


def test_desafio_tfa_real_solo_recuperacion():
    t = TransporteFalso().en("POST", "/access/ticket", dato("ticket_tfa_solo_recovery"))
    r = iniciar_sesion_ticket(t, "tfacaprec", "pve", "x", reloj=RelojSimulado())
    assert isinstance(r, DesafioTFA)
    assert (r.totp, r.recuperacion) == (False, True)


def test_ticket_renovado_real_trae_ticket_y_csrf():
    d = dato("ticket_renovado")
    assert d["ticket"].startswith("PVE:plc@pve:") and d["CSRFPreventionToken"]


# --- Lecturas reales -------------------------------------------------------------------


def test_cliente_entiende_version_real():
    v = cliente(TransporteFalso().en("GET", "/version", dato("version"))).version()
    assert (v.mayor, v.menor) == (9, 2) and v.parche >= 0


def test_cliente_entiende_nodos_y_estado_de_cluster_reales():
    c = cliente(
        TransporteFalso()
        .en("GET", "/nodes", dato("nodes"))
        .en("GET", "/cluster/status", dato("cluster_status_individual"))
    )
    n = c.nodos()[0]
    assert (n.nombre, n.en_linea, n.cpus) == ("pve-lab", True, 4)
    assert n.mem_libre_mib is not None and n.mem_libre_mib > 0
    topo = c.estado_cluster()
    assert topo.es_cluster is False and [x.nombre for x in topo.nodos] == ["pve-lab"]


def test_nodos_sin_sys_audit_reales_no_traen_memoria_ni_cpu():
    c = cliente(TransporteFalso().en("GET", "/nodes", dato("nodes_sin_sys_audit")))
    n = c.nodos()[0]
    assert (n.nombre, n.mem_libre_mib, n.cpus) == ("pve-lab", None, None)


def test_cliente_entiende_storages_reales():
    c = cliente(TransporteFalso().en("GET", "/nodes/pve-lab/storage", dato("storage")))
    por_id = {s.id: s for s in c.storages("pve-lab")}
    assert por_id["local"].tipo == "dir" and "images" in por_id["local"].contenido
    assert por_id["lab-lvmthin"].es_thin
    assert por_id["local"].libre_bytes > 0 and por_id["lab-lvmthin"].total_bytes > 0


def test_cliente_entiende_bridges_reales_con_y_sin_clave_vlan_aware():
    c = cliente(TransporteFalso().en("GET", "/nodes/pve-lab/network", dato("network")))
    b = {x.nombre: x for x in c.bridges("pve-lab")}
    assert b["vmbr1"].vlan_aware is True
    assert b["vmbr0"].vlan_aware is False  # PVE omite la clave en lugar de enviar 0
    assert b["enp0s2"].tipo == "eth"


def test_cliente_entiende_permisos_reales():
    c = cliente(TransporteFalso().en("GET", "/access/permissions", dato("permisos_completos")))
    p = c.permisos()
    assert {"/", "/vms", "/storage", "/sdn"} <= set(p)
    assert p["/"]["VM.Allocate"] == 1


def test_permisos_reales_sin_vm_allocate_hacen_que_falte_ese_privilegio():
    from proxlaunch.nucleo.servicios.conexion import _tiene_privilegio

    p = cliente(
        TransporteFalso().en("GET", "/access/permissions", dato("permisos_sin_vm_allocate"))
    ).permisos()
    assert not _tiene_privilegio(p, "/vms", "VM.Allocate")
    assert _tiene_privilegio(p, "/vms", "VM.Audit")


def test_permisos_reales_sin_sdn_use_no_dan_la_ruta_de_bridges():
    from proxlaunch.nucleo.servicios.conexion import _tiene_privilegio

    p = cliente(
        TransporteFalso().en("GET", "/access/permissions", dato("permisos_sin_sdn_use"))
    ).permisos()
    assert not _tiene_privilegio(p, "/sdn/zones/localnetwork", "SDN.Use")
    assert _tiene_privilegio(p, "/vms", "VM.Allocate")


def test_cliente_entiende_upid_estado_y_log_de_tarea_reales():
    upid = dato("crear_vm_upid")
    ruta = f"/nodes/pve-lab/tasks/{upid}"
    c = cliente(
        TransporteFalso()
        .en("POST", "/nodes/pve-lab/qemu", upid)
        .en("GET", f"{ruta}/status", dato("tarea_status_ok"))
        .en("GET", f"{ruta}/log", dato("tarea_log"))
    )
    assert c.crear_vm("pve-lab", {"vmid": "9040"}) == upid
    est = c.estado_tarea("pve-lab", upid)
    assert est.terminada and est.exitstatus == "OK"
    log = c.log_tarea("pve-lab", upid)
    assert log[-1] == "TASK OK"


def test_estado_running_real_no_trae_exitstatus():
    upid = dato("crear_vm_upid")
    c = cliente(
        TransporteFalso().en(
            "GET", f"/nodes/pve-lab/tasks/{upid}/status", dato("tarea_status_running")
        )
    )
    est = c.estado_tarea("pve-lab", upid)
    assert not est.terminada and est.exitstatus is None


def test_config_real_de_mv_seabios_y_ovmf():
    c = cliente(
        TransporteFalso()
        .en("GET", "/nodes/pve-lab/qemu/9040/config", dato("qemu_config"))
        .en("GET", "/nodes/pve-lab/qemu/9041/config", dato("qemu_config_ovmf"))
    )
    sea = c.config_vm("pve-lab", 9040)
    assert sea["scsihw"] == "virtio-scsi-single" and "bios" not in sea
    ovmf = c.config_vm("pve-lab", 9041)
    assert ovmf["bios"] == "ovmf"
    assert "efitype=4m" in ovmf["efidisk0"] and "pre-enrolled-keys=1" in ovmf["efidisk0"]


# --- Errores reales --------------------------------------------------------------------


def test_403_real_con_ruta_y_privilegio():
    e = traducir("error_permiso_403", nodo="pve-lab")
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert e.params == {"privilegio": "VM.Config.Memory", "ruta": "/vms/9044"}


def test_403_real_de_sdn_use_nombra_el_bridge():
    e = traducir("error_permiso_403_sdn")
    assert e.params["privilegio"] == "SDN.Use"
    assert e.params["ruta"] == "/sdn/zones/localnetwork/vmbr0"


def test_403_real_de_vm_allocate_no_trae_privilegio_ni_ruta():
    # Hecho real de PVE 9.2: este 403 es solo "Permission check failed".
    e = traducir("error_permiso_403_vm_allocate")
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert e.params == {}


@pytest.mark.parametrize(
    "archivo", ["error_vmid_ocupado_crear_500", "error_vmid_ocupado_ct_crear_500"]
)
def test_500_real_de_vmid_ocupado_en_post(archivo):
    e = traducir(archivo)
    assert e.codigo == CodigoError.VMID_OCUPADO
    assert e.params["nodo"] == "pve-lab"
    assert e.params["vmid"] in ("9040", "9050")


@pytest.mark.parametrize(
    "archivo", ["error_vmid_ocupado_nextid_400", "error_vmid_ocupado_ct_nextid_400"]
)
def test_400_real_de_nextid_ocupado(archivo):
    e = traducir(archivo)
    assert e.codigo == CodigoError.VMID_OCUPADO


def test_500_real_de_config_inexistente():
    assert traducir("error_config_inexistente_500").codigo == CodigoError.RECURSO_INEXISTENTE
    assert traducir("error_config_vm_de_un_ct_500").codigo == CodigoError.RECURSO_INEXISTENTE


def test_401_reales():
    assert traducir("error_credenciales_401").codigo == CodigoError.CREDENCIALES_INVALIDAS
    assert traducir("error_token_401").codigo == CodigoError.CREDENCIALES_INVALIDAS  # cuerpo vacío
    assert (
        traducir("error_ticket_invalido_401", sesion_ticket=True).codigo
        == CodigoError.SESION_EXPIRADA
    )


def test_400_real_de_formato_de_net0():
    e = traducir("error_formato_net0_400")
    assert e.codigo == CodigoError.ERROR_FORMATO
    assert e.params["campo"] == "net0"


def test_exitstatus_real_sin_espacio_en_lvm_grueso():
    texto = dato("tarea_status_error_sin_espacio")["exitstatus"]
    e = traducir_exitstatus(texto)
    assert e.codigo == CodigoError.SIN_ESPACIO
    assert e.params == {"storage": "lab"}  # el grupo de volúmenes; creacion.py lo cambia al id


@pytest.mark.xfail(
    strict=True,
    reason="El detalle técnico repite el mensaje: el motivo HTTP no lleva '\\n' y el cuerpo "
    "'message' sí; traductor_errores.py:_analizar_cuerpo no lo recorta y la deduplicación "
    "de traducir_http no los reconoce como iguales.",
)
def test_detalle_tecnico_de_un_403_real_no_repite_el_mensaje():
    e = traducir("error_permiso_403", nodo="pve-lab")
    texto = "Permission check failed (/vms/9044, VM.Config.Memory)"
    assert e.detalle_tecnico.count(texto) == 1
