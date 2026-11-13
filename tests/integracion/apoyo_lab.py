"""Apoyo de las pruebas de integración contra el laboratorio Proxmox VE (PVE 9.2).

Solo habla con 127.0.0.1:8006 / nodo ``pve-lab``. Los secretos se leen en tiempo de
ejecución de ``~/aprovprox-lab/secretos``; nunca se escriben en el repositorio ni en logs.
La administración del laboratorio (roles, usuarios, TFA, destruir MVs) se hace por SSH con
``lab.sh ssh`` (``pveum``/``pvesh``/``qm``), no por el núcleo bajo prueba.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proxlaunch.nucleo.api.transporte import crear_transporte_http
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import MetodoAuth, PerfilConexion
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.conexion import ServicioConexion

HOST = "127.0.0.1"
PUERTO = 8006
NODO = "pve-lab"
DIR_LAB = Path.home() / "aprovprox-lab"
DIR_SECRETOS = DIR_LAB / "secretos"
VMID_MIN, VMID_MAX = 9000, 9099
ROL = "ProxLaunchCreador"
USUARIO_PLC = "plc@pve"

PRIVILEGIOS_ROL: tuple[str, ...] = (
    "VM.Allocate",
    "VM.Audit",
    "VM.Config.Options",
    "VM.Config.HWType",
    "VM.Config.CPU",
    "VM.Config.Memory",
    "VM.Config.Network",
    "Datastore.AllocateSpace",
    "SDN.Use",
    "Sys.Audit",
)

# Privilegios que sobran para MVP 1 (se miden como "no requeridos").
PRIVILEGIOS_SOBRANTES: tuple[str, ...] = ("VM.Config.Disk", "Datastore.Audit")


def secreto(nombre: str) -> str:
    """Lee un secreto del laboratorio (sin saltos de línea)."""
    return (DIR_SECRETOS / nombre).read_text().strip()


def comprobar_destino(host: str, puerto: int, nodo: str) -> None:
    """Guarda de seguridad: solo el laboratorio local."""
    if host != HOST or puerto != PUERTO or nodo != NODO:
        raise RuntimeError(f"destino no permitido en integración: {host}:{puerto} nodo={nodo}")


def ssh(comando: str, *, comprobar: bool = True, timeout: float = 180) -> str:
    """Ejecuta un comando en el laboratorio (usuario debian, sudo disponible)."""
    r = subprocess.run(
        [str(DIR_LAB / "lab.sh"), "ssh", comando],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if comprobar and r.returncode != 0:
        raise RuntimeError(f"ssh falló ({r.returncode}): {comando[:80]}\n{r.stderr[-400:]}")
    return r.stdout


def pvesh_json(metodo: str, ruta: str, args: str = "") -> Any:
    """``pvesh`` como root del laboratorio, devolviendo JSON."""
    salida = ssh(f"sudo pvesh {metodo} {ruta} {args} --output-format json")
    return json.loads(salida) if salida.strip() else None


# --- Administración del laboratorio -------------------------------------------------


def crear_rol(privilegios: tuple[str, ...] = PRIVILEGIOS_ROL, nombre: str = ROL) -> None:
    ssh(f"sudo pveum role add {nombre} --privs '{','.join(privilegios)}'")


def modificar_rol(privilegios: tuple[str, ...], nombre: str = ROL) -> None:
    ssh(f"sudo pveum role modify {nombre} --privs '{','.join(privilegios)}'")


def borrar_rol(nombre: str = ROL) -> None:
    ssh(f"sudo pveum role delete {nombre}", comprobar=False)


def crear_usuario(userid: str, contrasena: str, rol: str = ROL, ruta: str = "/") -> None:
    ssh(f"sudo pveum user add {userid} --password '{contrasena}'")
    ssh(f"sudo pveum acl modify {ruta} --users {userid} --roles {rol} --propagate 1")


def borrar_usuario(userid: str) -> None:
    ssh(f"sudo pveum user delete {userid}", comprobar=False)


def crear_token(userid: str, nombre: str, privsep: int = 0) -> str:
    """Crea un token y devuelve ``usuario!nombre=secreto`` (solo en memoria)."""
    salida = ssh(
        f"sudo pveum user token add {userid} {nombre} --privsep {privsep} --output-format json"
    )
    datos = json.loads(salida)
    return f"{datos['full-tokenid']}={datos['value']}"


def borrar_token(userid: str, nombre: str) -> None:
    ssh(f"sudo pveum user token remove {userid} {nombre}", comprobar=False)


def nuevo_secreto() -> str:
    """Contraseña aleatoria para usuarios de prueba (solo hex: segura para el shell)."""
    return secrets.token_hex(12)


def destruir_vm(vmid: int) -> None:
    """Detiene (si corre) y destruye una MV del rango de pruebas, con sus discos."""
    if not VMID_MIN <= vmid <= VMID_MAX:
        raise RuntimeError(f"VMID fuera del rango de pruebas: {vmid}")
    ssh(
        f"sudo qm stop {vmid} --skiplock 1 >/dev/null 2>&1; "
        f"sudo qm destroy {vmid} --purge 1 --destroy-unreferenced-disks 1 >/dev/null 2>&1; true",
        comprobar=False,
    )


def vmids_de_prueba() -> list[int]:
    """VMIDs presentes en el rango de pruebas (por si algo quedó huérfano)."""
    salida = ssh("sudo pvesh get /cluster/resources --type vm --output-format json")
    return [int(r["vmid"]) for r in json.loads(salida) if VMID_MIN <= int(r["vmid"]) <= VMID_MAX]


# --- TOTP (RFC 6238, solo hmac/hashlib) ----------------------------------------------


def totp(secreto_b32: str, instante: float | None = None, desplazamiento: int = 0) -> str:
    """Código TOTP de 6 dígitos, SHA-1, paso de 30 s (RFC 6238 / RFC 4226)."""
    paso = int((time.time() if instante is None else instante) // 30) + desplazamiento
    clave = base64.b32decode(secreto_b32.upper() + "=" * (-len(secreto_b32) % 8))
    mac = hmac.new(clave, struct.pack(">Q", paso), hashlib.sha1).digest()
    pos = mac[-1] & 0x0F
    numero = struct.unpack(">I", mac[pos : pos + 4])[0] & 0x7FFFFFFF
    return f"{numero % 1_000_000:06d}"


def nuevo_secreto_totp() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def configurar_totp(userid: str, secreto_b32: str, contrasena_admin: str | None = None) -> None:
    """Registra un TOTP para ``userid`` (como root@pam, que no necesita contraseña propia).

    PVE exige el valor actual del TOTP para confirmar el alta; se calcula con la
    función estándar.
    """
    uri = f"otpauth://totp/{userid.replace('@', '%40')}?secret={secreto_b32}&issuer=ProxLaunchLab"
    ssh(
        f"sudo pvesh create /access/tfa/{userid} --type totp "
        f"--totp '{uri}' --value {totp(secreto_b32)} --description lab"
    )


def configurar_recuperacion(userid: str) -> list[str]:
    """Crea claves de recuperación y las devuelve (solo en memoria)."""
    salida = ssh(f"sudo pvesh create /access/tfa/{userid} --type recovery --output-format json")
    datos = json.loads(salida)
    return list(datos.get("recovery", []))


def borrar_tfa(userid: str) -> None:
    """Elimina todas las entradas TFA del usuario."""
    salida = ssh(f"sudo pvesh get /access/tfa/{userid} --output-format json", comprobar=False)
    try:
        entradas = json.loads(salida) if salida.strip() else []
    except ValueError:
        entradas = []
    for e in entradas:
        ssh(f"sudo pvesh delete /access/tfa/{userid}/{e['id']}", comprobar=False)


# --- Núcleo de ProxLaunch con persistencia aislada -----------------------------------


class LlaveroFalso:
    """Backend de llavero en memoria (nunca se usa el llavero real del sistema)."""

    def __init__(self) -> None:
        self.datos: dict[tuple[str, str], str] = {}

    def get_password(self, servicio: str, clave: str) -> str | None:
        return self.datos.get((servicio, clave))

    def set_password(self, servicio: str, clave: str, valor: str) -> None:
        self.datos[(servicio, clave)] = valor

    def delete_password(self, servicio: str, clave: str) -> None:
        self.datos.pop((servicio, clave), None)


@dataclass
class Entorno:
    servicio: ServicioConexion
    huellas: RepositorioHuellas
    llavero: LlaveroFalso


def crear_entorno(carpeta: Path) -> Entorno:
    """ServicioConexion real con transporte HTTP real y persistencia en ``carpeta``."""
    llavero = LlaveroFalso()
    huellas = RepositorioHuellas(carpeta / "huellas.json")
    servicio = ServicioConexion(
        crear_transporte_http,
        huellas,
        AlmacenSecretos(backend=llavero),
        RelojReal(),
    )
    return Entorno(servicio, huellas, llavero)


def perfil(
    metodo: MetodoAuth = MetodoAuth.TOKEN,
    usuario: str = "",
    realm: str = "pve",
    host: str = HOST,
    puerto: int = PUERTO,
    recordar: bool = False,
) -> PerfilConexion:
    comprobar_destino(host, puerto, NODO)
    return PerfilConexion(
        id="lab-" + secrets.token_hex(4),
        nombre="Laboratorio",
        hosts=[host],
        puerto=puerto,
        metodo=metodo,
        usuario=usuario,
        realm=realm,
        recordar_credenciales=recordar,
    )


def confiar_en_laboratorio(entorno: Entorno, p: PerfilConexion) -> str:
    """Sonda TOFU real y confianza explícita; devuelve la huella observada."""
    info = entorno.servicio.consultar_huellas(p)[0]
    assert info.huella_observada is not None
    entorno.servicio.confiar_huella(p, info.host, info.huella_observada)
    return info.huella_observada


def codigo_de(exc: ErrorProxLaunch) -> str:
    return str(exc.codigo)
