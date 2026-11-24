"""Captura respuestas REALES de PVE 9.2 (laboratorio) y las guarda saneadas.

Uso (laboratorio encendido)::

    PYTHONPATH=src .venv/bin/python tests/integracion/capturar_respuestas.py

Escribe en ``tests/datos/respuestas/9.2-lab/``. No es una prueba: es una herramienta de
captura. Solo habla con 127.0.0.1:8006 y limpia todo lo que crea. Los secretos (tickets,
CSRF, tokens, contraseñas, códigos TOTP, claves de recuperación, huellas y UPIDs) se
reemplazan por marcadores coherentes antes de escribir; al final se comprueba que ningún
secreto de esta ejecución quedó en disco.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import requests
import urllib3

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))

from tests.integracion import apoyo_lab as lab  # noqa: E402

DESTINO = RAIZ / "tests" / "datos" / "respuestas" / "9.2-lab"
BASE = f"https://{lab.HOST}:{lab.PUERTO}/api2/json"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Saneado --------------------------------------------------------------------------

_SECRETOS: set[str] = set()  # valores sensibles de esta ejecución (para la verificación final)
_UPIDS: dict[str, str] = {}
_RE_UPID = re.compile(r"UPID:[^\"\s,]+")
_RE_HUELLA = re.compile(r"(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}")
_RE_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def secreto(valor: str) -> str:
    """Registra un valor sensible para borrarlo de todo lo que se escriba."""
    if valor:
        _SECRETOS.add(valor)
    return valor


def _upid_marcado(upid: str) -> str:
    if upid not in _UPIDS:
        partes = upid.split(":")
        n = len(_UPIDS) + 1
        # UPID:<nodo>:<pid>:<pstart>:<starttime>:<tipo>:<id>:<usuario>:
        tipo, ident, usuario = partes[5], partes[6], partes[7]
        _UPIDS[upid] = f"UPID:{partes[1]}:{n:08X}:{n:08X}:{n:08X}:{tipo}:{ident}:{usuario}:"
    return _UPIDS[upid]


def sanear_ticket(ticket: str) -> str:
    """``PVE:<usuario>:<HEX8>::<firma>`` conserva forma y desafío TFA; firma enmascarada."""
    partes = ticket.split(":")
    if len(partes) >= 5 and partes[0] == "PVE":
        medio = partes[1]
        if medio.startswith("!tfa!"):
            desafio = json.loads(unquote(medio[5:]))
            # Las claves de recuperación (si el desafío las trajera) se sustituyen por índices.
            if isinstance(desafio.get("recovery"), list):
                desafio["recovery"] = list(range(len(desafio["recovery"])))
            medio = "!tfa!" + quote(json.dumps(desafio, separators=(",", ":")), safe="")
        return f"PVE:{medio}:00000000::FIRMA_SANEADA"
    return "TICKET_SANEADO"


def sanear(valor: Any, clave: str = "") -> Any:
    """Recorre el JSON sustituyendo secretos y UPIDs por marcadores."""
    if isinstance(valor, dict):
        salida = {}
        for k, v in valor.items():
            if k == "ticket" and isinstance(v, str):
                salida[k] = sanear_ticket(v)
            elif k == "CSRFPreventionToken" and isinstance(v, str):
                salida[k] = "00000000:CSRF_SANEADO"
            elif k in ("digest",) and isinstance(v, str):
                salida[k] = "0" * 40
            elif k in ("value", "password", "secret") and isinstance(v, str):
                salida[k] = "SECRETO_SANEADO"
            elif k in ("pid", "pstart", "starttime") and isinstance(v, int):
                salida[k] = 241074 if k == "pid" else 16040403 if k == "pstart" else 1698000000
            else:
                salida[k] = sanear(v, k)
        return salida
    if isinstance(valor, list):
        return [sanear(x, clave) for x in valor]
    if isinstance(valor, str):
        t = _RE_UPID.sub(lambda m: _upid_marcado(m.group(0)), valor)
        t = _RE_HUELLA.sub("HUELLA:SANEADA", t)
        for s in _SECRETOS:
            t = t.replace(s, "SECRETO_SANEADO")
        return t
    return valor


# --- Cliente mínimo de captura (independiente del núcleo) -------------------------------


class Captura:
    def __init__(self) -> None:
        DESTINO.mkdir(parents=True, exist_ok=True)
        self.http: dict[str, dict[str, Any]] = {}
        self.sesion = requests.Session()
        self.sesion.verify = False
        self.sesion.trust_env = False

    def llamar(
        self,
        metodo: str,
        ruta: str,
        *,
        token: str | None = None,
        ticket: tuple[str, str] | None = None,
        datos: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> requests.Response:
        cab: dict[str, str] = {}
        cookies = None
        if token:
            cab["Authorization"] = f"PVEAPIToken={token}"
        if ticket:
            cookies = {"PVEAuthCookie": ticket[0]}
            if metodo != "GET":
                cab["CSRFPreventionToken"] = ticket[1]
        r = self.sesion.request(
            metodo,
            BASE + ruta,
            headers=cab,
            cookies=cookies,
            data=datos,
            params=params,
            timeout=60,
            allow_redirects=False,
        )
        return r

    def guardar(self, nombre: str, r: requests.Response, nota: str = "") -> Any:
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = {"_texto_no_json": r.text}
        limpio = sanear(cuerpo)
        (DESTINO / f"{nombre}.json").write_text(
            json.dumps(limpio, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        self.http[f"{nombre}.json"] = {
            "estado_http": r.status_code,
            "motivo_http": sanear(r.reason or ""),
            "nota": nota,
        }
        print(f"  {nombre}.json  HTTP {r.status_code} {sanear(r.reason or '')[:70]}")
        return cuerpo

    def esperar_tarea(self, nodo: str, upid: str, token: str) -> dict[str, Any]:
        ruta = f"/nodes/{nodo}/tasks/{quote(upid, safe=':@!')}/status"
        for _ in range(120):
            d = self.llamar("GET", ruta, token=token).json()["data"]
            if d["status"] == "stopped":
                return d
            time.sleep(0.5)
        raise RuntimeError("la tarea no terminó")


def main() -> None:  # noqa: PLR0915
    lab.comprobar_destino(lab.HOST, lab.PUERTO, lab.NODO)
    if lab.ssh("hostname").strip() != lab.NODO:
        raise SystemExit("el nodo no es pve-lab: se aborta")
    c = Captura()
    creadas: list[int] = []
    for u in (lab.USUARIO_PLC, "plcvar@pve", "tfacap@pve", "tfacaprec@pve"):
        lab.borrar_usuario(u)
    lab.borrar_rol()
    lab.borrar_rol("PLCVariante")
    lab.ssh("sudo pvesm remove lab-lvm", comprobar=False)
    try:
        lab.crear_rol()
        pw_plc = secreto(lab.nuevo_secreto())
        lab.crear_usuario(lab.USUARIO_PLC, pw_plc)
        completo = secreto(lab.crear_token(lab.USUARIO_PLC, "t1"))
        tid, tsec = completo.rsplit("=", 1)
        secreto(tsec)
        tok = completo

        print("Lecturas con el rol mínimo (token):")
        c.guardar("version", c.llamar("GET", "/version", token=tok))
        c.guardar("nextid", c.llamar("GET", "/cluster/nextid", token=tok))
        c.guardar("cluster_status_individual", c.llamar("GET", "/cluster/status", token=tok))
        c.guardar("nodes", c.llamar("GET", "/nodes", token=tok))
        c.guardar("nodes_individual", c.llamar("GET", "/nodes", token=tok))
        c.guardar("storage", c.llamar("GET", f"/nodes/{lab.NODO}/storage", token=tok))
        c.guardar("network", c.llamar("GET", f"/nodes/{lab.NODO}/network", token=tok))
        c.guardar("permisos_completos", c.llamar("GET", "/access/permissions", token=tok))

        print("Tickets:")
        r = c.llamar("POST", "/access/ticket", datos={"username": "plc@pve", "password": pw_plc})
        ticket = r.json()["data"]
        secreto(ticket["ticket"])
        secreto(ticket["CSRFPreventionToken"])
        c.guardar("ticket_completo", r)
        time.sleep(1.2)
        r = c.llamar(
            "POST",
            "/access/ticket",
            datos={"username": "plc@pve", "password": ticket["ticket"]},
        )
        nuevo = r.json()["data"]
        secreto(nuevo["ticket"])
        secreto(nuevo["CSRFPreventionToken"])
        c.guardar("ticket_renovado", r, "renovación con el ticket vigente como contraseña")
        c.guardar(
            "error_credenciales_401",
            c.llamar("POST", "/access/ticket", datos={"username": "plc@pve", "password": "mala"}),
        )
        c.guardar(
            "error_token_401",
            c.llamar("GET", "/version", token="plc@pve!t1=00000000-0000-0000-0000-000000000000"),
        )
        c.guardar(
            "error_ticket_invalido_401",
            c.llamar("GET", "/nodes", ticket=("PVE:plc@pve:00000000::AAAA", "0:x")),
        )

        print("Segundo factor:")
        for nombre, con_totp in (("tfacap", True), ("tfacaprec", False)):
            userid = f"{nombre}@pve"
            pw = secreto(lab.nuevo_secreto())
            lab.ssh(f"sudo pveum user add {userid} --password '{pw}'")
            sec = secreto(lab.nuevo_secreto_totp())
            if con_totp:
                lab.configurar_totp(userid, sec)
            claves = lab.configurar_recuperacion(userid)
            for k in claves:
                secreto(k)
            r1 = c.llamar("POST", "/access/ticket", datos={"username": userid, "password": pw})
            parcial = r1.json()["data"]
            secreto(parcial["ticket"])
            secreto(parcial["CSRFPreventionToken"])
            nombre_archivo = "ticket_tfa_totp_recovery" if con_totp else "ticket_tfa_solo_recovery"
            c.guardar(nombre_archivo, r1)
            if con_totp:
                secreto(lab.totp(sec))
                malo = f"{(int(lab.totp(sec)) + 1) % 1_000_000:06d}"
                c.guardar(
                    "error_tfa_codigo_incorrecto_401",
                    c.llamar(
                        "POST",
                        "/access/ticket",
                        datos={
                            "username": userid,
                            "tfa-challenge": parcial["ticket"],
                            "password": f"totp:{malo}",
                        },
                    ),
                )
                ok = c.llamar(
                    "POST",
                    "/access/ticket",
                    datos={
                        "username": userid,
                        "tfa-challenge": parcial["ticket"],
                        "password": f"totp:{lab.totp(sec)}",
                    },
                )
                if ok.status_code == 200:
                    d = ok.json()["data"]
                    secreto(d["ticket"])
                    secreto(d["CSRFPreventionToken"])
                c.guardar("ticket_tfa_paso2_ok", ok)
            lab.borrar_usuario(userid)

        print("Creación y tarea:")
        vmid = 9040
        params = {
            "vmid": vmid,
            "name": "captura-seabios",
            "sockets": 1,
            "cores": 2,
            "cpu": "x86-64-v2-AES",
            "memory": 2048,
            "scsihw": "virtio-scsi-single",
            "scsi0": "lab-lvmthin:2,discard=on,ssd=1,iothread=1",
            "net0": "virtio,bridge=vmbr0",
        }
        creadas.append(vmid)
        r = c.llamar("POST", f"/nodes/{lab.NODO}/qemu", token=tok, datos=params)
        upid = r.json()["data"]
        c.guardar("crear_vm_upid", r)
        ruta_t = f"/nodes/{lab.NODO}/tasks/{quote(upid, safe=':@!')}"
        primero = c.llamar("GET", f"{ruta_t}/status", token=tok)
        if primero.json()["data"]["status"] == "running":
            c.guardar("tarea_status_running", primero)
        final = c.esperar_tarea(lab.NODO, upid, tok)
        c.guardar("tarea_status_ok", c.llamar("GET", f"{ruta_t}/status", token=tok))
        c.guardar("tarea_log", c.llamar("GET", f"{ruta_t}/log", token=tok))
        c.guardar(
            "tarea_log_limit500",
            c.llamar("GET", f"{ruta_t}/log", token=tok, params={"start": 0, "limit": 500}),
        )
        assert final["exitstatus"] == "OK"
        c.guardar(
            "qemu_config", c.llamar("GET", f"/nodes/{lab.NODO}/qemu/{vmid}/config", token=tok)
        )

        vmid_ovmf = 9041
        creadas.append(vmid_ovmf)
        p2 = dict(params)
        p2.update(
            {
                "vmid": vmid_ovmf,
                "name": "captura-ovmf",
                "bios": "ovmf",
                "machine": "q35",
                "efidisk0": "local:1,efitype=4m,pre-enrolled-keys=1,format=qcow2",
                "scsi0": "local:1,discard=on,ssd=1,iothread=1,format=qcow2",
                "net0": "virtio,bridge=vmbr1,tag=5",
            }
        )
        r = c.llamar("POST", f"/nodes/{lab.NODO}/qemu", token=tok, datos=p2)
        u2 = r.json()["data"]
        c.esperar_tarea(lab.NODO, u2, tok)
        c.guardar(
            "qemu_config_ovmf",
            c.llamar("GET", f"/nodes/{lab.NODO}/qemu/{vmid_ovmf}/config", token=tok),
        )

        print("Errores:")
        c.guardar(
            "error_vmid_ocupado_crear_500",
            c.llamar("POST", f"/nodes/{lab.NODO}/qemu", token=tok, datos=params),
        )
        c.guardar(
            "error_vmid_ocupado_nextid_400",
            c.llamar("GET", "/cluster/nextid", token=tok, params={"vmid": vmid}),
        )
        c.guardar(
            "error_config_inexistente_500",
            c.llamar("GET", f"/nodes/{lab.NODO}/qemu/9099/config", token=tok),
        )
        c.guardar(
            "error_nodo_inexistente", c.llamar("GET", "/nodes/noexiste/qemu/9099/config", token=tok)
        )
        c.guardar(
            "error_formato_net0_400",
            c.llamar(
                "POST",
                f"/nodes/{lab.NODO}/qemu",
                token=tok,
                datos={**params, "vmid": 9042, "net0": "virtio,bridge=vmbr0,tag=99999"},
            ),
        )
        # format=qcow2 en lvmthin: el POST lo acepta y la tarea falla (error genérico real).
        creadas.append(9042)
        r = c.llamar(
            "POST",
            f"/nodes/{lab.NODO}/qemu",
            token=tok,
            datos={**params, "vmid": 9042, "scsi0": "lab-lvmthin:2,format=qcow2"},
        )
        u4 = r.json()["data"]
        c.esperar_tarea(lab.NODO, u4, tok)
        c.guardar(
            "tarea_status_error_generico",
            c.llamar("GET", f"/nodes/{lab.NODO}/tasks/{quote(u4, safe=':@!')}/status", token=tok),
            "format=qcow2 en lvmthin",
        )

        # Contenedor real para el choque de VMID.
        plantilla = "alpine-3.23-default_20261105_amd64.tar.xz"
        bajada = plantilla not in lab.ssh("sudo pveam list local")
        if bajada:
            lab.ssh(f"sudo pveam download local {plantilla}", timeout=300)
        lab.ssh("sudo pct destroy 9050 --purge 1", comprobar=False)
        lab.ssh(
            f"sudo pct create 9050 local:vztmpl/{plantilla} --rootfs lab-lvmthin:1 "
            "--hostname ctprueba --unprivileged 1"
        )
        try:
            c.guardar(
                "error_vmid_ocupado_ct_crear_500",
                c.llamar(
                    "POST", f"/nodes/{lab.NODO}/qemu", token=tok, datos={**params, "vmid": 9050}
                ),
            )
            c.guardar(
                "error_vmid_ocupado_ct_nextid_400",
                c.llamar("GET", "/cluster/nextid", token=tok, params={"vmid": 9050}),
            )
            c.guardar(
                "error_config_vm_de_un_ct_500",
                c.llamar("GET", f"/nodes/{lab.NODO}/qemu/9050/config", token=tok),
            )
        finally:
            lab.ssh("sudo pct destroy 9050 --purge 1", comprobar=False)
            if bajada:
                lab.ssh(f"sudo pveam remove local:vztmpl/{plantilla}", comprobar=False)

        print("Sin espacio (LVM grueso):")
        lab.ssh(f"sudo pvesm add lvm lab-lvm --vgname {lab.VG_LAB} --content images")
        try:
            c.guardar(
                "storage_con_lvm_grueso", c.llamar("GET", f"/nodes/{lab.NODO}/storage", token=tok)
            )
            creadas.append(9043)
            r = c.llamar(
                "POST",
                f"/nodes/{lab.NODO}/qemu",
                token=tok,
                datos={**params, "vmid": 9043, "scsi0": "lab-lvm:10"},
            )
            u3 = r.json()["data"]
            fin = c.esperar_tarea(lab.NODO, u3, tok)
            c.guardar(
                "tarea_status_error_sin_espacio",
                c.llamar(
                    "GET", f"/nodes/{lab.NODO}/tasks/{quote(u3, safe=':@!')}/status", token=tok
                ),
            )
            print("   exitstatus:", sanear(fin.get("exitstatus"))[:160])
        finally:
            lab.ssh("sudo pvesm remove lab-lvm", comprobar=False)

        print("Permisos (usuarios con un privilegio menos):")
        for quitar, archivo, es_post, extra in (
            ("VM.Allocate", "permisos_sin_vm_allocate", True, "error_permiso_403_vm_allocate"),
            ("Sys.Audit", "permisos_sin_sys_audit", False, ""),
            ("VM.Config.Memory", "permisos_sin_vm_config_memory", True, "error_permiso_403"),
            ("SDN.Use", "permisos_sin_sdn_use", True, "error_permiso_403_sdn"),
            ("VM.Audit", "permisos_sin_vm_audit", False, "error_permiso_403_config_vm_audit"),
            (
                "Datastore.AllocateSpace",
                "permisos_sin_allocate_space",
                True,
                "error_permiso_403_datastore",
            ),
        ):
            lab.crear_rol(tuple(p for p in lab.PRIVILEGIOS_ROL if p != quitar), "PLCVariante")
            lab.crear_usuario("plcvar@pve", lab.nuevo_secreto(), "PLCVariante")
            tv = secreto(lab.crear_token("plcvar@pve", "t1"))
            secreto(tv.rsplit("=", 1)[1])
            try:
                c.guardar(archivo, c.llamar("GET", "/access/permissions", token=tv))
                if quitar == "Sys.Audit":
                    c.guardar("nodes_sin_sys_audit", c.llamar("GET", "/nodes", token=tv))
                    c.guardar(
                        "error_cluster_status_sin_sys_audit_403",
                        c.llamar("GET", "/cluster/status", token=tv),
                    )
                if quitar == "SDN.Use":
                    c.guardar(
                        "network_sin_sdn_use",
                        c.llamar("GET", f"/nodes/{lab.NODO}/network", token=tv),
                    )
                if quitar == "VM.Audit":
                    c.guardar(
                        extra, c.llamar("GET", f"/nodes/{lab.NODO}/qemu/{vmid}/config", token=tv)
                    )
                elif es_post:
                    creadas.append(9044)
                    c.guardar(
                        extra,
                        c.llamar(
                            "POST",
                            f"/nodes/{lab.NODO}/qemu",
                            token=tv,
                            datos={**params, "vmid": 9044},
                        ),
                    )
            finally:
                lab.borrar_usuario("plcvar@pve")
                lab.borrar_rol("PLCVariante")

        (DESTINO / "_http.json").write_text(
            json.dumps(c.http, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        for v in dict.fromkeys(creadas):
            lab.destruir_vm(v)
        for u in (lab.USUARIO_PLC, "plcvar@pve", "tfacap@pve", "tfacaprec@pve"):
            lab.borrar_usuario(u)
        lab.borrar_rol()
        lab.borrar_rol("PLCVariante")
        lab.ssh("sudo pvesm remove lab-lvm", comprobar=False)

    # Verificación final: ningún secreto de esta ejecución quedó en disco.
    fugas = []
    for f in sorted(DESTINO.glob("*.json")):
        texto = f.read_text(encoding="utf-8")
        for s in _SECRETOS:
            if len(s) >= 6 and s in texto:
                fugas.append(f.name)
    if fugas:
        raise SystemExit(f"FUGA de secretos en: {sorted(set(fugas))}")
    print(f"OK: {len(list(DESTINO.glob('*.json')))} archivos saneados en {DESTINO}")


if __name__ == "__main__":
    main()
