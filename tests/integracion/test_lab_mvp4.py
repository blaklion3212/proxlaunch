"""MVP 4 (origen del SO) contra el laboratorio real: LAB-M4-01..14 de docs/requisitos/mvp4.md §12.

Solo con ``PROXLAUNCH_LAB=1`` y solo contra el laboratorio local (127.0.0.1:8006, nodo ``pve-lab``).
VMIDs 9000-9099 únicamente; archivos subidos con prefijo ``proxlaunch-lab-``. Todo lo que se crea se
destruye al terminar (también si la prueba falla): MVs, plantilla, archivos subidos, roles, usuarios
y tokens de prueba, y el contenido ``import`` de ``local`` vuelve a su estado original.

Los pasos de administrador (crear roles, activar ``import``, convertir en plantilla, borrar archivos,
mirar ``/var/tmp``, encender MVs) se hacen con ``lab.ssh`` como root del laboratorio. Las operaciones
que se prueban (subir, descargar por URL, crear, clonar, listar) las hace el núcleo de ProxLaunch o,
cuando hay que observar la respuesta cruda del servidor, la API con el token del rol ampliado.

Las pruebas imprimen líneas ``EVIDENCIA[...]`` (visibles con ``-s``) con las medidas reales.
"""

# ruff: noqa: E501
# (cadenas largas de EVIDENCIA y de comandos del laboratorio)
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import http.server
import io
import json
import re
import socket
import socketserver
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import requests

from proxlaunch.nucleo.api.multipart import CuerpoMultipart, ParteArchivo
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.conexion import CredencialToken, MetodoAuth
from proxlaunch.nucleo.modelos.origen import (
    DetalleImportacion,
    DetalleIso,
    RefVolumen,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import (
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
    OrigenSO,
)
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, Via, calcular_capacidades
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH, tiene_privilegio
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.catalogo import ServicioCatalogo
from proxlaunch.nucleo.servicios.descubrimiento import descubrir
from proxlaunch.nucleo.transferencias.modelos import (
    DestinoTransferencia,
    EstadoTransferencia,
)
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion, ServicioTransferencias
from proxlaunch.nucleo.transferencias.url import validar_url

from . import apoyo_lab as lab

pytestmark = [
    pytest.mark.integracion,
    pytest.mark.filterwarnings("ignore::urllib3.exceptions.InsecureRequestWarning"),
]

STORAGE = "lab-lvmthin"
LOCAL = "local"
URL = f"https://{lab.HOST}:{lab.PUERTO}/api2/json"
NODO = lab.NODO
DISCOS = lab.DIR_LAB / "discos"
ISO_LOCAL = DISCOS / "proxlaunch-lab-alpine.iso"
CIRROS_LOCAL = DISCOS / "proxlaunch-lab-cirros.qcow2"
BACKING_LOCAL = DISCOS / "proxlaunch-lab-backing.qcow2"
OVA_LOCAL = DISCOS / "proxlaunch-lab-falso.ova"
SHA256_ALPINE = "157d353f8e54252cad2d9812a0d56bb7fa2231fc154a110e1d180d7480ef8b4f"
TAM_ALPINE = 70254592
ROL14 = "ProxLaunchCreadorM4"
USUARIO14 = "plcm4@pve"
CONTENIDO_LOCAL_ORIGINAL = "images,iso,vztmpl,backup"  # orden de storage.cfg
VMID_PLANTILLA = 9050
PRIVS10 = lab.PRIVILEGIOS_ROL
PRIVS14 = ROL_PROXLAUNCH
PUERTO_HTTP = 38411  # servidor HTTP local temporal (solo 127.0.0.1)
IP_ANFITRION = "10.0.2.2"  # el anfitrión visto desde el laboratorio (red user de QEMU)


def evidencia(clave: str, **datos: Any) -> None:
    detalle = " ".join(f"{k}={v!r}" for k, v in datos.items())
    print(f"EVIDENCIA[{clave}] {detalle}")


# --- Apoyo: administración (root del laboratorio) ---------------------------------------------


@dataclass(frozen=True)
class Cred:
    userid: str
    token_id: str
    secreto: str = field(repr=False)
    contrasena: str = field(default="", repr=False)


@contextlib.contextmanager
def usuario_con(privs: tuple[str, ...], etiqueta: str, rol: str | None = None) -> Iterator[Cred]:
    """Rol + usuario (en ``/``, propagate) + token privsep=0; todo se borra al salir."""
    nombre_rol = rol or f"PlcM4{etiqueta}"
    userid = f"plcm4{etiqueta.lower()}@pve"
    lab.borrar_usuario(userid)
    lab.borrar_rol(nombre_rol)
    lab.crear_rol(privs, nombre_rol)
    try:
        contrasena = lab.nuevo_secreto()
        lab.crear_usuario(userid, contrasena, nombre_rol)
        completo = lab.crear_token(userid, "tk", privsep=0)
        token_id, secreto = completo.rsplit("=", 1)
        yield Cred(userid, token_id, secreto, contrasena)
    finally:
        lab.borrar_usuario(userid)
        lab.borrar_rol(nombre_rol)


@contextlib.contextmanager
def usuario_administrador(etiqueta: str = "Adm") -> Iterator[Cred]:
    """Usuario con el rol Administrator en ``/`` (equivale al administrador del servidor)."""
    userid = f"plcm4{etiqueta.lower()}@pve"
    lab.borrar_usuario(userid)
    try:
        lab.ssh(f"sudo pveum user add {userid} --password '{lab.nuevo_secreto()}'")
        lab.ssh(f"sudo pveum acl modify / --users {userid} --roles Administrator --propagate 1")
        completo = lab.crear_token(userid, "tk", privsep=0)
        token_id, secreto = completo.rsplit("=", 1)
        yield Cred(userid, token_id, secreto)
    finally:
        lab.borrar_usuario(userid)


def contenido_de_local() -> str:
    salida = lab.ssh("sudo pvesh get /storage/local --output-format json")
    return str(json.loads(salida).get("content", ""))


def fijar_contenido_local(contenido: str) -> None:
    lab.ssh(f"sudo pvesm set {LOCAL} --content {contenido}")


def contenido_con_import() -> str:
    return CONTENIDO_LOCAL_ORIGINAL + ",import"


def borrar_archivos_lab() -> None:
    """Borra como root todo ``proxlaunch-lab-*`` de ``local`` (iso e import)."""
    lab.ssh(
        "for v in $(sudo pvesm list local | awk 'NR>1 && /proxlaunch-lab-/{print $1}'); "
        "do sudo pvesm free $v; done; "
        "sudo rm -f /var/lib/vz/template/iso/proxlaunch-lab-* "
        "/var/lib/vz/import/proxlaunch-lab-*; true",
        comprobar=False,
        timeout=300,
    )


def temporales_subida() -> set[str]:
    """Temporales ``/var/tmp/pveupload-*`` del nodo (los crea pveproxy al recibir una subida)."""
    salida = lab.ssh("sudo ls -A /var/tmp | grep '^pveupload-' || true", comprobar=False)
    return set(salida.split())


def borrar_temporales_subida() -> None:
    lab.ssh("sudo rm -f /var/tmp/pveupload-*", comprobar=False)


def archivos_lab() -> list[str]:
    salida = lab.ssh("sudo pvesm list local | awk 'NR>1 && /proxlaunch-lab-/{print $1}'")
    return [ln for ln in salida.split() if ln]


def esperar_api(max_s: float = 120.0) -> None:
    fin = time.monotonic() + max_s
    while time.monotonic() < fin:
        try:
            if requests.get(URL + "/version", verify=False, timeout=5).status_code in (200, 401):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    pytest.exit("la API del laboratorio no responde", 2)


def limpiar_vms(vmids: list[int] | None = None) -> None:
    """Destruye las MVs 9000-9099 que existan (clones antes que la plantilla) y los volúmenes
    sueltos de ese rango. Con ``vmids`` solo toca esos; sin él, todo el rango."""
    existentes = set(lab.vmids_de_prueba())
    objetivo = existentes if vmids is None else existentes & set(vmids)
    ordenes = [
        f"sudo qm unlock {v}; sudo qm set {v} --protection 0; sudo qm stop {v} --skiplock 1; "
        f"sudo qm destroy {v} --purge 1 --skiplock 1 --destroy-unreferenced-disks 1"
        for v in sorted(objetivo, reverse=True)
    ]
    sueltos = (
        "for s in lab-lvmthin local; do for vol in $(sudo pvesm list $s | "
        r"awk 'NR>1 && NF==5 && $NF>=9000 && $NF<=9099 && $1 !~ /proxlaunch-lab-/{print $1}'); "
        "do sudo pvesm free $vol; done; done"
    )
    # Los volúmenes sueltos solo se barren en la limpieza final (con la plantilla ya destruida):
    # el disco base de una plantilla viva también "pertenece" a un VMID del rango.
    if vmids is None:
        ordenes.append(sueltos)
    if ordenes:
        lab.ssh(f"({'; '.join(ordenes)}) >/dev/null 2>&1; true", comprobar=False, timeout=900)


# --- Apoyo: API cruda con token ----------------------------------------------------------------


class Api:
    """Peticiones HTTP directas con un token (solo 127.0.0.1:8006). Devuelve la respuesta cruda."""

    def __init__(self, cred: Cred) -> None:
        lab.comprobar_destino(lab.HOST, lab.PUERTO, lab.NODO)
        self._cab = {"Authorization": f"PVEAPIToken={cred.token_id}={cred.secreto}"}

    def get(self, ruta: str, **params: Any) -> requests.Response:
        return requests.get(
            URL + ruta, headers=self._cab, params=params or None, verify=False, timeout=60
        )

    def post(self, ruta: str, **datos: Any) -> requests.Response:
        return requests.post(URL + ruta, headers=self._cab, data=datos, verify=False, timeout=120)

    def put(self, ruta: str, **datos: Any) -> requests.Response:
        return requests.put(URL + ruta, headers=self._cab, data=datos, verify=False, timeout=120)

    def delete(self, ruta: str, **params: Any) -> requests.Response:
        return requests.delete(
            URL + ruta, headers=self._cab, params=params or None, verify=False, timeout=120
        )

    def datos(self, resp: requests.Response) -> Any:
        assert resp.status_code == 200, f"{resp.status_code} {resp.text[:300]}"
        return resp.json()["data"]

    def tarea(self, upid: str, max_s: float = 600.0) -> tuple[str, list[str], float]:
        """Espera una tarea; devuelve ``(exitstatus, log, segundos)``."""
        t0 = time.monotonic()
        ruta = f"/nodes/{NODO}/tasks/{upid}"
        while time.monotonic() - t0 < max_s:
            est = self.datos(self.get(f"{ruta}/status"))
            if est["status"] == "stopped":
                log = self.datos(self.get(f"{ruta}/log", limit=500))
                return (
                    str(est.get("exitstatus")),
                    [str(e.get("t")) for e in log],
                    (time.monotonic() - t0),
                )
            time.sleep(0.5)
        raise AssertionError(f"tarea {upid} no terminó en {max_s} s")

    def crear_vm(self, vmid: int, **extra: Any) -> requests.Response:
        base: dict[str, Any] = {"vmid": vmid, "name": f"plc-m4-{vmid}", "memory": 128, "cores": 1}
        base.update(extra)
        return self.post(f"/nodes/{NODO}/qemu", **base)

    def crear_ok(self, vmid: int, **extra: Any) -> None:
        resp = self.crear_vm(vmid, **extra)
        assert resp.status_code == 200, f"{resp.status_code} {resp.text[:300]}"
        estado, log, _ = self.tarea(resp.json()["data"])
        assert estado == "OK", (estado, log[-3:])

    def config(self, vmid: int) -> dict[str, Any]:
        return self.datos(self.get(f"/nodes/{NODO}/qemu/{vmid}/config"))


def mensaje(resp: requests.Response) -> str:
    """Texto breve de un error de la API (sin secretos)."""
    try:
        cuerpo = resp.json()
    except ValueError:
        return f"{resp.status_code} {resp.text[:160]}"
    return f"{resp.status_code} {cuerpo.get('message', '')[:200]} {cuerpo.get('errors', '')}"


# --- Apoyo: núcleo de ProxLaunch ----------------------------------------------------------------


def abrir_sesion(entorno: lab.Entorno, cred: Cred, puerto: int = lab.PUERTO) -> Any:
    p = dataclasses.replace(lab.perfil(MetodoAuth.TOKEN, cred.token_id), puerto=puerto)
    lab.confiar_en_laboratorio(entorno, p)
    return entorno.servicio.conectar(p, CredencialToken(cred.token_id, cred.secreto))


def servicio_transferencias(sesion: Any) -> ServicioTransferencias:
    return ServicioTransferencias(
        sesion,
        RelojReal(),
        RegistroSesion(),
        intervalo_s=0.5,
        hora_local=lambda: time.strftime("%H:%M:%S"),
    )


def destino(contenido: Contenido, nombre: str, storage: str = LOCAL) -> DestinoTransferencia:
    return DestinoTransferencia(NODO, storage, contenido, nombre)


def subir(
    sesion: Any,
    ruta: Path,
    contenido: Contenido,
    nombre: str,
    *,
    cancelado: threading.Event | None = None,
    al_progresar: Callable[[Any], None] | None = None,
    servicio: ServicioTransferencias | None = None,
    inv: Any = None,
) -> Any:
    inv = inv if inv is not None else descubrir(sesion)
    return (servicio or servicio_transferencias(sesion)).subir(
        ruta,
        destino(contenido, nombre),
        inv,
        al_progresar=al_progresar or (lambda _p: None),
        cancelado=cancelado or threading.Event(),
        acepta_aviso_raiz=True,
    )


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# --- Fixtures ------------------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _limpieza_m4() -> Iterator[None]:
    """Estado inicial comprobado y limpieza total al terminar el módulo."""
    esperar_api()
    original = contenido_de_local()
    assert "import" not in original.split(","), f"local ya tiene import: {original}"
    assert set(original.split(",")) == set(CONTENIDO_LOCAL_ORIGINAL.split(",")), original
    borrar_archivos_lab()
    yield
    limpiar_vms()
    borrar_archivos_lab()
    borrar_temporales_subida()
    fijar_contenido_local(CONTENIDO_LOCAL_ORIGINAL)
    for rol in ("PlcM4Menos", "PlcM4Tmp", ROL14):
        lab.borrar_rol(rol)


@pytest.fixture(scope="module")
def entorno_m4(tmp_path_factory: pytest.TempPathFactory) -> lab.Entorno:
    return lab.crear_entorno(tmp_path_factory.mktemp("m4"))


@pytest.fixture(scope="module")
def cred14() -> Iterator[Cred]:
    with usuario_con(PRIVS14, "14", rol=ROL14) as c:
        yield c


@pytest.fixture(scope="module")
def cred10() -> Iterator[Cred]:
    with usuario_con(PRIVS10, "10") as c:
        yield c


@pytest.fixture(scope="module")
def sesion14(entorno_m4: lab.Entorno, cred14: Cred) -> Iterator[Any]:
    sesion = abrir_sesion(entorno_m4, cred14)
    yield sesion
    entorno_m4.servicio.cerrar_sesion(sesion)


@pytest.fixture(scope="module")
def api14(cred14: Cred) -> Api:
    return Api(cred14)


@pytest.fixture
def con_import() -> Iterator[None]:
    """Activa ``import`` en ``local`` durante la prueba y lo revierte."""
    fijar_contenido_local(contenido_con_import())
    try:
        yield
    finally:
        borrar_archivos_lab()
        fijar_contenido_local(CONTENIDO_LOCAL_ORIGINAL)


@pytest.fixture
def vmids() -> Iterator[Callable[..., int]]:
    """Registra VMIDs (9000-9099); se destruyen al terminar."""
    creados: list[int] = []

    def registrar(*ids: int) -> int:
        for i in ids:
            if not lab.VMID_MIN <= i <= lab.VMID_MAX:
                raise ValueError(f"VMID fuera de rango: {i}")
        creados.extend(ids)
        return ids[0]

    yield registrar
    limpiar_vms(creados)


@pytest.fixture
def iso_alpine(sesion14: Any) -> Iterator[str]:
    """Sube Alpine a ``local`` como ``proxlaunch-lab-alpine.iso`` (con el núcleo) y lo borra."""
    r = subir(sesion14, ISO_LOCAL, Contenido.ISO, "proxlaunch-lab-alpine.iso")
    assert r.estado == EstadoTransferencia.TERMINADA, r
    try:
        yield r.volid
    finally:
        borrar_archivos_lab()


@pytest.fixture(scope="module")
def plantilla(sesion14: Any) -> Iterator[int]:
    """Plantilla CirrOS (VMID 9050) en ``lab-lvmthin``: imagen subida con el núcleo e importada
    por root; se convierte en plantilla como root (el rol de 14 no puede)."""
    fijar_contenido_local(contenido_con_import())
    try:
        r = subir(sesion14, CIRROS_LOCAL, Contenido.IMPORT, "proxlaunch-lab-cirros.qcow2")
        assert r.estado == EstadoTransferencia.TERMINADA, r
        lab.ssh(
            f"sudo qm create {VMID_PLANTILLA} --name plc-m4-plantilla --memory 128 --cores 1 "
            f"--net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-single --ostype l26 "
            f"--scsi0 {STORAGE}:0,import-from={r.volid},discard=on,iothread=1 "
            f"--boot order=scsi0 && sudo qm template {VMID_PLANTILLA}",
            timeout=300,
        )
        # /cluster/resources se refresca cada ~10 s (pvestatd): se espera a que la plantilla se vea
        fin = time.monotonic() + 60
        while time.monotonic() < fin and VMID_PLANTILLA not in {
            p.vmid for p in sesion14.cliente.plantillas_visibles()
        }:
            time.sleep(1)
        yield VMID_PLANTILLA
    finally:
        limpiar_vms()
        borrar_archivos_lab()
        fijar_contenido_local(CONTENIDO_LOCAL_ORIGINAL)


# =========================================================================================
# LAB-M4-01  Rol ampliado
# =========================================================================================

RUTAS_PERMISOS = ("/", f"/nodes/{NODO}", "/storage/local", f"/storage/{STORAGE}", "/vms/9010")


def test_lab_m4_01_el_rol_de_14_privilegios_se_ve_en_access_permissions(sesion14, api14):
    """RF-O24, CA-O24.1: los 14 privilegios llegan por ``/access/permissions`` (y el parser del
    núcleo los reconoce en ``/``, ``/nodes/pve-lab``, ``/storage/*`` y ``/vms/*``)."""
    crudo = api14.datos(api14.get("/access/permissions"))
    evidencia("M4-01-permisos-rutas", rutas=sorted(crudo))
    permisos = sesion14.cliente.permisos()
    faltan = {
        (ruta, p)
        for ruta in RUTAS_PERMISOS
        for p in PRIVS14
        if not tiene_privilegio(permisos, ruta, p)
    }
    assert not faltan, faltan
    assert set(PRIVS14) <= set(permisos["/"])
    assert all(permisos["/"][p] == 1 for p in PRIVS14)  # propagate
    sobran = set(permisos["/"]) - set(PRIVS14)
    assert not sobran, sobran  # nada de Datastore.Allocate ni Sys.Modify (INV-O4)
    puntual = api14.datos(api14.get("/access/permissions", path="/vms/9010"))
    evidencia(
        "M4-01-permisos-path", rutas=sorted(puntual), privilegios=len(puntual.get("/vms/9010", {}))
    )
    assert set(PRIVS14) <= set(puntual.get("/vms/9010", {}))


@pytest.mark.parametrize("quien", ["10", "14"])
def test_lab_m4_01_ambos_roles_crean_mvs_vacias(quien, cred10, cred14, vmids):
    """CA-O24.4: el rol de 10 del MVP 3 sigue creando MVs vacías (y el de 14 también)."""
    api = Api(cred10 if quien == "10" else cred14)
    vmid = vmids(9010 if quien == "10" else 9011)
    api.crear_ok(
        vmid,
        scsi0=f"{STORAGE}:1,discard=on,ssd=1,iothread=1",
        scsihw="virtio-scsi-single",
        net0="virtio,bridge=vmbr0",
    )
    assert api.config(vmid)["scsi0"].startswith(f"{STORAGE}:vm-{vmid}-disk-")


def test_lab_m4_01_sin_vm_config_disk_boot_da_403_y_sin_boot_crea(vmids):
    """CA-O08.3 / INV-O10: sin ``VM.Config.Disk`` el ``boot`` en el POST de creación da 403 y la
    misma petición sin ``boot`` se crea; ``resize`` también da 403."""
    menos = tuple(p for p in PRIVS14 if p != "VM.Config.Disk")
    with usuario_con(menos, "Menos") as c:
        api = Api(c)
        vmid = vmids(9012)
        base = {
            "scsi0": f"{STORAGE}:1,discard=on,ssd=1,iothread=1",
            "scsihw": "virtio-scsi-single",
            "net0": "virtio,bridge=vmbr0",
        }
        r = api.crear_vm(vmid, boot="order=scsi0;net0", **base)
        evidencia("M4-01-boot-sin-Disk", respuesta=mensaje(r))
        assert r.status_code == 403
        assert "VM.Config.Disk" in r.text
        assert not lab.ssh(f"sudo qm status {vmid} 2>&1", comprobar=False).startswith("status")
        api.crear_ok(vmid, **base)
        r = api.put(f"/nodes/{NODO}/qemu/{vmid}/resize", disk="scsi0", size="2G")
        evidencia("M4-01-resize-sin-Disk", respuesta=mensaje(r))
        assert r.status_code == 403


def test_lab_m4_01_sin_vm_clone_el_clon_da_403(plantilla, vmids):
    """CA-O24.1: sin ``VM.Clone`` la clonación da 403."""
    menos = tuple(p for p in PRIVS14 if p != "VM.Clone")
    with usuario_con(menos, "Menos") as c:
        vmid = vmids(9051)
        r = Api(c).post(
            f"/nodes/{NODO}/qemu/{plantilla}/clone", newid=vmid, name="plc-m4-sinclone", full=0
        )
        evidencia("M4-01-clone-sin-VM.Clone", respuesta=mensaje(r))
        assert r.status_code == 403
        assert "VM.Clone" in r.text


def test_lab_m4_01_sin_allocate_template_la_subida_da_403(con_import):
    """CA-O24.1: sin ``Datastore.AllocateTemplate`` la subida a ``iso`` y a ``import`` da 403."""
    menos = tuple(p for p in PRIVS14 if p != "Datastore.AllocateTemplate")
    with usuario_con(menos, "Menos") as c:
        api = Api(c)
        for contenido, nombre in (
            ("iso", "proxlaunch-lab-x.iso"),
            ("import", "proxlaunch-lab-x.qcow2"),
        ):
            r = requests.post(
                f"{URL}/nodes/{NODO}/storage/{LOCAL}/upload",
                headers={"Authorization": f"PVEAPIToken={c.token_id}={c.secreto}"},
                data={"content": contenido},
                files={"filename": (nombre, b"x" * 1024, "application/octet-stream")},
                verify=False,
                timeout=60,
            )
            evidencia(
                "M4-01-upload-sin-AllocateTemplate", contenido=contenido, respuesta=mensaje(r)
            )
            assert r.status_code == 403
        assert not [a for a in archivos_lab() if "proxlaunch-lab-x" in a]
        del api


def test_lab_m4_01_sin_sys_access_network_la_descarga_da_403(con_import):
    """CA-O24.1: sin ``Sys.AccessNetwork`` fallan ``query-url-metadata`` y ``download-url``."""
    menos = tuple(p for p in PRIVS14 if p != "Sys.AccessNetwork")
    with usuario_con(menos, "Menos") as c:
        api = Api(c)
        url = f"http://{IP_ANFITRION}:{PUERTO_HTTP}/proxlaunch-lab-alpine.iso"
        r1 = api.get(f"/nodes/{NODO}/query-url-metadata", url=url)
        r2 = api.post(
            f"/nodes/{NODO}/storage/{LOCAL}/download-url",
            url=url,
            content="iso",
            filename="proxlaunch-lab-x.iso",
        )
        evidencia("M4-01-descarga-sin-AccessNetwork", metadata=mensaje(r1), download=mensaje(r2))
        assert r1.status_code == 403
        assert r2.status_code == 403
        assert archivos_lab() == []


# =========================================================================================
# LAB-M4-02  Detección y catálogo
# =========================================================================================


def _storages_nodo(api: Api, **params: Any) -> dict[str, dict[str, Any]]:
    return {s["storage"]: s for s in api.datos(api.get(f"/nodes/{NODO}/storage", **params))}


def test_lab_m4_02_campos_de_storage_del_nodo_y_globales(api14, con_import):
    """RF-O04, CA-O04.6: ``content``, ``active``, ``shared`` y ``formats`` de ``GET
    /nodes/pve-lab/storage`` y los campos de ``GET /storage`` con el rol de 14."""
    por_nodo = _storages_nodo(api14)
    evidencia(
        "M4-02-nodo-local",
        **{k: por_nodo[LOCAL].get(k) for k in ("type", "content", "active", "shared", "enabled")},
    )
    evidencia(
        "M4-02-nodo-lvmthin",
        **{k: por_nodo[STORAGE].get(k) for k in ("type", "content", "active", "shared", "enabled")},
    )
    assert set(por_nodo[LOCAL]["content"].split(",")) == set(contenido_con_import().split(","))
    assert por_nodo[LOCAL]["active"] == 1 and por_nodo[LOCAL]["shared"] == 0
    assert por_nodo[STORAGE]["type"] == "lvmthin" and "iso" not in por_nodo[STORAGE]["content"]
    con_formatos = _storages_nodo(api14, format=1)
    evidencia(
        "M4-02-formats",
        local=con_formatos[LOCAL].get("format"),
        lvmthin=con_formatos[STORAGE].get("format"),
    )
    assert "qcow2" in con_formatos[LOCAL]["format"][0]
    assert con_formatos[STORAGE]["format"][0] == {"raw": 1}  # solo raw en lvmthin
    globales = {s["storage"]: s for s in api14.datos(api14.get("/storage"))}
    evidencia(
        "M4-02-global-campos", campos=sorted(globales[LOCAL]), lvmthin=sorted(globales[STORAGE])
    )
    assert {LOCAL, STORAGE} <= set(globales)
    assert "import" in globales[LOCAL]["content"]
    # filtros por contenido del servidor
    for contenido, esperado in (
        ("iso", {LOCAL}),
        ("import", {LOCAL}),
        ("images", {LOCAL, STORAGE}),
    ):
        filtrado = set(_storages_nodo(api14, content=contenido))
        evidencia("M4-02-filtro-content", content=contenido, storages=sorted(filtrado))
        assert filtrado == esperado, (contenido, filtrado)


def test_lab_m4_02_la_clasificacion_sale_del_contenido_y_no_del_nombre(sesion14, con_import):
    """CA-O04.2: storages con nombres engañosos se clasifican por su ``content`` real."""
    from proxlaunch.nucleo.origen.storages import candidatos

    ruta = "/var/lib/proxlaunch-lab-falsos"
    lab.ssh(
        f"sudo mkdir -p {ruta}/a {ruta}/b && "
        f"sudo pvesm add dir proxlaunch-lab-isos --path {ruta}/a --content images && "
        f"sudo pvesm add dir proxlaunch-lab-datos --path {ruta}/b --content iso,import"
    )
    try:
        inv = descubrir(sesion14)
        iso = {s.id for s in candidatos(inv, Contenido.ISO, NODO)}
        imp = {s.id for s in candidatos(inv, Contenido.IMPORT, NODO)}
        img = {s.id for s in candidatos(inv, Contenido.IMAGENES, NODO)}
        evidencia(
            "M4-02-nombres-enganosos", iso=sorted(iso), importar=sorted(imp), imagenes=sorted(img)
        )
        assert iso == {LOCAL, "proxlaunch-lab-datos"}  # «isos» no es candidato: solo images
        assert imp == {LOCAL, "proxlaunch-lab-datos"}
        assert "proxlaunch-lab-isos" in img
        assert "proxlaunch-lab-isos" not in iso | imp
    finally:
        lab.ssh(
            "sudo pvesm remove proxlaunch-lab-isos; sudo pvesm remove proxlaunch-lab-datos; "
            f"sudo rm -rf {ruta}",
            comprobar=False,
        )


def test_lab_m4_02_desactivar_y_reactivar_import_cambia_la_deteccion(sesion14, api14):
    """RF-O05, E-O01: sin ``import`` en ningún storage la vía de importación pasa a «no»; al
    reactivarlo vuelve a «sí»."""
    from proxlaunch.nucleo.origen.storages import candidatos

    def estado() -> tuple[set[str], Any]:
        inv = descubrir(sesion14)
        caps = calcular_capacidades(sesion14.capacidades, inv, NODO)
        return {s.id for s in candidatos(inv, Contenido.IMPORT, NODO)}, caps.estado(Via.IMPORTAR)

    ids, via = estado()
    evidencia(
        "M4-02-import-desactivado",
        storages=sorted(ids),
        via=via.disponibilidad,
        codigo=str(via.codigo),
    )
    assert ids == set() and via.disponibilidad == Disponibilidad.NO
    assert str(via.codigo) == "importar_sin_storage_import" or "import" in str(via.codigo)
    fijar_contenido_local(contenido_con_import())
    try:
        ids, via = estado()
        evidencia("M4-02-import-activado", storages=sorted(ids), via=via.disponibilidad)
        assert ids == {LOCAL} and via.disponibilidad == Disponibilidad.SI
        assert _storages_nodo(api14, content="import").keys() == {LOCAL}
    finally:
        fijar_contenido_local(CONTENIDO_LOCAL_ORIGINAL)
    ids, via = estado()
    assert ids == set() and via.disponibilidad == Disponibilidad.NO


def test_lab_m4_02_catalogo_de_isos_e_imagenes_con_el_rol(sesion14, iso_alpine, con_import):
    """RF-O06: ``?content=iso`` y ``?content=import`` con el rol: el núcleo lista la ISO subida."""
    inv = descubrir(sesion14)
    catalogo = ServicioCatalogo(sesion14, RelojReal())
    listados = catalogo.listar(inv, NODO, Contenido.ISO)
    todos = [v for lst in listados for v in lst.volumenes]
    evidencia(
        "M4-02-catalogo-iso", volumenes=[(v.volid, v.tamano_bytes, v.admitido) for v in todos]
    )
    assert any(v.volid == iso_alpine and v.tamano_bytes == TAM_ALPINE and v.admitido for v in todos)
    sin_error = [lst for lst in listados if lst.error is None]
    assert [lst.storage for lst in sin_error] == [LOCAL]
    assert catalogo.listar(inv, NODO, Contenido.IMPORT)[0].volumenes == ()


# =========================================================================================
# LAB-M4-03  Subir Alpine con token + checksum
# =========================================================================================


def _estado_vartmp() -> list[str]:
    return lab.ssh("ls -A /var/tmp | grep -v systemd-private || true").split()


def test_lab_m4_03_el_orden_de_campos_del_multipart_del_cliente_lo_acepta_pveproxy(sesion14):
    """Regresión DEFECTO-LAB-01 (corregido): pveproxy lee los campos de la subida en orden FIJO
    ``content``, ``checksum-algorithm``, ``checksum`` y luego el archivo; con otro orden responde
    ``400`` («wrong Content-Disposition … in multipart»). El cliente real ya los envía así."""
    r = subir(sesion14, ISO_LOCAL, Contenido.ISO, "proxlaunch-lab-orden.iso")
    evidencia("M4-03-orden-correcto", estado=str(r.estado), error=r.error)
    assert r.estado == EstadoTransferencia.TERMINADA, r
    borrar_archivos_lab()


def test_lab_m4_03_subir_alpine_con_token_y_checksum(sesion14):
    """RF-O09, RF-O10, CA-O09.9: tamaño y sha256 en el nodo iguales; volid; ``Content-Type`` de la
    parte; ``rootfs`` en ``GET /nodes/pve-lab/status``."""
    progresos: list[Any] = []
    antes = _estado_vartmp()
    r = subir(
        sesion14,
        ISO_LOCAL,
        Contenido.ISO,
        "proxlaunch-lab-alpine.iso",
        al_progresar=progresos.append,
    )
    evidencia(
        "M4-03-subida",
        estado=str(r.estado),
        volid=r.volid,
        duracion_s=round(r.duracion_s, 2),
        upid=bool(r.upid),
    )
    try:
        assert r.estado == EstadoTransferencia.TERMINADA, r
        assert r.volid == "local:iso/proxlaunch-lab-alpine.iso"
        en_nodo = lab.ssh(
            "sudo stat -c %s /var/lib/vz/template/iso/proxlaunch-lab-alpine.iso; "
            "sudo sha256sum /var/lib/vz/template/iso/proxlaunch-lab-alpine.iso"
        ).split()
        assert int(en_nodo[0]) == TAM_ALPINE == ISO_LOCAL.stat().st_size
        assert en_nodo[1] == SHA256_ALPINE == sha256_de(ISO_LOCAL)
        estados = [p.estado for p in progresos]
        assert estados[0] == EstadoTransferencia.CALCULANDO_HUELLA
        assert EstadoTransferencia.TRANSFIRIENDO in estados
        hechos = [
            p.hechos_bytes for p in progresos if p.estado == EstadoTransferencia.TRANSFIRIENDO
        ]
        assert hechos == sorted(hechos) and progresos[-1].hechos_bytes == TAM_ALPINE
        assert _estado_vartmp() == antes  # no queda temporal tras una subida correcta
        # Content-Type de la parte (cabecera que construye el núcleo, aceptada por el servidor)
        cuerpo = CuerpoMultipart({"content": "iso"}, ParteArchivo("x.iso", 0, io.BytesIO(b"")))
        assert b"Content-Type: application/octet-stream" in next(iter(cuerpo))
        estado = sesion14.cliente.estado_nodo(NODO)
        evidencia("M4-03-rootfs", rootfs=estado["rootfs"])
        df = int(lab.ssh("df -B1 --output=avail /var/tmp | tail -1"))
        assert abs(int(estado["rootfs"]["avail"]) - df) < 200 * 1024**2
    finally:
        borrar_archivos_lab()


def test_lab_m4_03_el_servidor_sobrescribe_sin_avisar_y_la_app_lo_evita(
    sesion14, api14, iso_alpine
):
    """CA-O10: la API pisa un archivo existente (misma ruta) y el núcleo se niega antes de enviar."""
    r = subir(sesion14, ISO_LOCAL, Contenido.ISO, "proxlaunch-lab-alpine.iso")
    evidencia(
        "M4-03-nombre-existente",
        estado=str(r.estado),
        codigo=str(r.error.codigo) if r.error else None,
    )
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error is not None and str(r.error.codigo) == "nombre_ya_existe"
    assert (
        sha256_de(ISO_LOCAL)
        == lab.ssh("sudo sha256sum /var/lib/vz/template/iso/proxlaunch-lab-alpine.iso").split()[0]
    )
    # El servidor, en cambio, sobrescribe sin aviso:
    pequeno = b"contenido distinto " * 10
    resp = requests.post(
        f"{URL}/nodes/{NODO}/storage/{LOCAL}/upload",
        headers=api14._cab,
        data={"content": "iso"},
        files={"filename": ("proxlaunch-lab-alpine.iso", pequeno, "application/octet-stream")},
        verify=False,
        timeout=60,
    )
    assert resp.status_code == 200, resp.text
    estado, log, _ = api14.tarea(resp.json()["data"])
    tam = int(lab.ssh("sudo stat -c %s /var/lib/vz/template/iso/proxlaunch-lab-alpine.iso"))
    evidencia("M4-03-sobrescribe", tarea=estado, tamano_final=tam)
    assert estado == "OK" and tam == len(pequeno)


def test_lab_m4_03_checksum_erroneo_falla_la_tarea_y_no_queda_archivo(api14):
    """CA-O09.9: con un ``checksum`` que no coincide la tarea falla y no hay archivo."""
    mal = "0" * 64
    resp = requests.post(
        f"{URL}/nodes/{NODO}/storage/{LOCAL}/upload",
        headers=api14._cab,
        data={"content": "iso", "checksum-algorithm": "sha256", "checksum": mal},
        files={"filename": ("proxlaunch-lab-mal.iso", b"abc" * 100, "application/octet-stream")},
        verify=False,
        timeout=60,
    )
    evidencia("M4-03-checksum-malo-respuesta", estado=resp.status_code, cuerpo=resp.text[:200])
    if resp.status_code == 200:
        estado, log, _ = api14.tarea(resp.json()["data"])
        evidencia("M4-03-checksum-malo-tarea", estado=estado, log=log[-3:])
        assert estado != "OK"
    else:
        assert resp.status_code >= 400
    assert archivos_lab() == []


def test_lab_m4_03_cancelar_a_la_mitad_no_deja_archivo(sesion14):
    """RF-O12, CA-O12.2: cancelar a mitad de la subida: ``CANCELADA``, sin archivo en el storage
    y sin temporales de ``/var/tmp``; se mide el tiempo de reacción."""
    cancelado = threading.Event()
    marcas: dict[str, float] = {}

    def vigilar(p: Any) -> None:
        if (
            p.estado == EstadoTransferencia.TRANSFIRIENDO
            and p.hechos_bytes >= TAM_ALPINE // 2
            and not cancelado.is_set()
        ):
            marcas["pedida"] = time.monotonic()
            cancelado.set()

    antes = _estado_vartmp()
    r = subir(
        sesion14,
        ISO_LOCAL,
        Contenido.ISO,
        "proxlaunch-lab-mitad.iso",
        cancelado=cancelado,
        al_progresar=vigilar,
    )
    marcas["fin"] = time.monotonic()
    time.sleep(1)
    restos = [f for f in _estado_vartmp() if f not in antes]
    evidencia(
        "M4-03-cancelar",
        estado=str(r.estado),
        quedo_archivo=r.quedo_archivo,
        reaccion_s=round(marcas["fin"] - marcas["pedida"], 3),
        restos_vartmp=restos,
        archivos=archivos_lab(),
    )
    assert r.estado == EstadoTransferencia.CANCELADA, r
    assert archivos_lab() == []
    assert r.quedo_archivo in (False, None)
    assert marcas["fin"] - marcas["pedida"] < 5
    assert restos == [], restos


def test_lab_m4_03_subidas_rechazadas_por_el_servidor_dejan_temporales_en_var_tmp(
    sesion14, api14, con_import
):
    """CA-O10.4 / RF-O12: se mide qué deja pveproxy en ``/var/tmp`` cuando RECHAZA una subida (no
    cuando el cliente la corta o cancela, que no deja nada). Es evidencia de cuánto espacio puede
    consumir un rechazo tardío; los temporales se borran al terminar."""
    borrar_temporales_subida()
    medidas: dict[str, list[tuple[str, int]]] = {}

    def residuo(caso: str) -> None:
        time.sleep(2)
        nuevos = temporales_subida()
        tam = [(n, int(lab.ssh(f"sudo stat -c %s /var/tmp/{n}").strip())) for n in sorted(nuevos)]
        medidas[caso] = tam
        borrar_temporales_subida()

    try:
        # a) la tarea falla por checksum (el archivo ya se recibió entero)
        datos = ISO_LOCAL.read_bytes()[: 8 * 1024**2]
        requests.post(
            f"{URL}/nodes/{NODO}/storage/{LOCAL}/upload",
            headers=api14._cab,
            data={"content": "iso", "checksum-algorithm": "sha256", "checksum": "0" * 64},
            files={"filename": ("proxlaunch-lab-x1.iso", datos, "application/octet-stream")},
            verify=False,
            timeout=120,
        )
        residuo("checksum_erroneo_8MiB")
        # b) sin permiso (403 tras recibir la cabecera)
        with usuario_con(
            tuple(p for p in PRIVS14 if p != "Datastore.AllocateTemplate"), "Menos"
        ) as c:
            try:
                r = _subida_cruda(Api(c), "proxlaunch-lab-x2.iso", datos, "iso")
                assert r.status_code == 403
            except requests.ConnectionError:
                pass  # el servidor rechaza y corta antes de que termine el cuerpo
        residuo("sin_permiso_8MiB")
        # c) campos fuera de orden (400 antes de leer el archivo; el servidor puede cerrar sin responder)
        try:
            r = requests.post(
                f"{URL}/nodes/{NODO}/storage/{LOCAL}/upload",
                headers=api14._cab,
                data={"content": "iso", "checksum": "0" * 64, "checksum-algorithm": "sha256"},
                files={"filename": ("proxlaunch-lab-x3.iso", datos, "application/octet-stream")},
                verify=False,
                timeout=120,
            )
            assert r.status_code == 400
        except requests.ConnectionError:
            pass
        residuo("campos_fuera_de_orden_8MiB")
        evidencia("M4-03-temporales-tras-rechazo", **medidas)
    finally:
        borrar_temporales_subida()
        borrar_archivos_lab()


# =========================================================================================
# LAB-M4-04  MV con ISO (q35 + OVMF + efidisk0 + ide2 + boot)
# =========================================================================================


def cfg_iso(
    vmid: int,
    iso_volid: str,
    *,
    firmware: Firmware = Firmware.OVMF,
    tipo_so: TipoSO | None = TipoSO.LINUX,
    storage_efi: str | None = None,
    **extra: Any,
) -> ConfiguracionVM:
    base: dict[str, Any] = {
        "vmid": vmid,
        "nombre": f"plc-m4-{vmid}",
        "nodo": NODO,
        "firmware": firmware,
        "storage_efi": storage_efi,
        "cores": 1,
        "memoria_mib": 512,
        "discos": [Disco(storage=STORAGE, tamano_gib=1)],
        "redes": [InterfazRed(bridge="vmbr0")],
        "origen": OrigenSO.ISO,
        "detalle_origen": DetalleIso(iso=RefVolumen(iso_volid.split("/")[-1], iso_volid)),
        "tipo_so": tipo_so,
    }
    base.update(extra)
    return ConfiguracionVM(**base)


def parametros(sesion: Any, cfg: ConfiguracionVM) -> dict[str, str]:
    return construir_parametros(
        cfg, descubrir(sesion), (sesion.version.mayor, sesion.version.menor)
    )


def crear_con(api: Api, params: dict[str, str]) -> requests.Response:
    return api.post(f"/nodes/{NODO}/qemu", **params)


def crear_con_ok(api: Api, params: dict[str, str]) -> float:
    t0 = time.monotonic()
    resp = crear_con(api, params)
    assert resp.status_code == 200, mensaje(resp)
    estado, log, _ = api.tarea(resp.json()["data"])
    assert estado == "OK", (estado, log[-3:])
    return time.monotonic() - t0


def consola(vmid: int, segundos: int = 40) -> str:
    """Salida del puerto serie de la MV durante ``segundos`` (necesita ``serial0: socket``)."""
    sock = f"/var/run/qemu-server/{vmid}.serial0"
    salida = lab.ssh(
        f"for i in $(seq 40); do [ -S {sock} ] && break; sleep 0.5; done; "
        f"sudo timeout {segundos} socat -u UNIX-CONNECT:{sock} - 2>/dev/null | "
        "tr -c '[:print:]\\n' ' ' | tail -c 3000; true",
        comprobar=False,
        timeout=segundos + 90,
    )
    return salida


def leido_del_cd(api: Api, vmid: int, clave: str = "ide2") -> int:
    actual = api.datos(api.get(f"/nodes/{NODO}/qemu/{vmid}/status/current"))
    bloque = actual.get("blockstat", {}).get(clave, {})
    return int(bloque.get("rd_bytes", 0))


def arrancar_y_observar(api: Api, vmid: int, segundos: int = 45) -> tuple[int, str]:
    """Enciende como root, escucha la consola y devuelve ``(bytes leídos del CD, consola)``."""
    lab.ssh(f"sudo qm set {vmid} --serial0 socket && sudo qm start {vmid}", timeout=120)
    texto = consola(vmid, segundos)
    leido = leido_del_cd(api, vmid)
    lab.ssh(f"sudo qm stop {vmid} --skiplock 1", comprobar=False, timeout=120)
    return leido, texto


@pytest.fixture
def dos_isos(sesion14: Any) -> Iterator[tuple[str, str]]:
    """Alpine como ``proxlaunch-lab-alpine.iso`` y como ``proxlaunch-lab-drivers.iso``."""
    a = subir(sesion14, ISO_LOCAL, Contenido.ISO, "proxlaunch-lab-alpine.iso")
    b = subir(sesion14, ISO_LOCAL, Contenido.ISO, "proxlaunch-lab-drivers.iso")
    assert a.estado == b.estado == EstadoTransferencia.TERMINADA, (a, b)
    try:
        yield a.volid, b.volid
    finally:
        borrar_archivos_lab()


def test_lab_m4_04_crear_con_iso_boot_y_efidisk_sin_vm_config_cdrom(
    sesion14, api14, iso_alpine, vmids
):
    """RF-O08, CA-O08.2/3, DT-O1: el rol de 14 (SIN ``VM.Config.CDROM``) crea la MV con ``q35`` +
    OVMF + ``efidisk0`` + ``ide2`` (ISO) + ``boot=order=scsi0;ide2;net0``."""
    assert "VM.Config.CDROM" not in PRIVS14
    vmid = vmids(9013)
    params = parametros(sesion14, cfg_iso(vmid, iso_alpine))
    evidencia(
        "M4-04-post",
        parametros={
            k: v
            for k, v in params.items()
            if k in ("ide2", "boot", "efidisk0", "machine", "bios", "ostype")
        },
    )
    assert params["boot"] == "order=scsi0;ide2;net0" and params["ide2"].endswith("media=cdrom")
    segundos = crear_con_ok(api14, params)
    conf = api14.config(vmid)
    evidencia(
        "M4-04-config",
        ide2=conf.get("ide2"),
        boot=conf.get("boot"),
        efidisk0=conf.get("efidisk0"),
        machine=conf.get("machine"),
        bios=conf.get("bios"),
        s=round(segundos, 2),
    )
    assert conf["ide2"].startswith(f"{iso_alpine},media=cdrom")
    assert conf["boot"] == "order=scsi0;ide2;net0"
    assert conf["bios"] == "ovmf" and "q35" in conf["machine"] and "efidisk0" in conf


def test_lab_m4_04_sin_vm_config_disk_el_boot_da_403_pero_ide2_sin_boot_crea(
    sesion14, iso_alpine, vmids
):
    """CA-O08.3 / INV-O10: sin ``VM.Config.Disk`` el POST con ``boot`` da 403 (se prueba también
    con ``ide2``); sin ``boot`` la MV con ISO se crea y se confirma que ``ide2`` no pide CDROM."""
    menos = tuple(p for p in PRIVS14 if p != "VM.Config.Disk")
    with usuario_con(menos, "Menos") as c:
        api = Api(c)
        vmid = vmids(9014)
        params = parametros(sesion14, cfg_iso(vmid, iso_alpine))  # incluye boot (permisos del 14)
        r = crear_con(api, params)
        evidencia("M4-04-boot-sin-Disk", respuesta=mensaje(r))
        assert r.status_code == 403
        sin_boot = {k: v for k, v in params.items() if k != "boot"}
        crear_con_ok(api, sin_boot)
        conf = api.config(vmid)
        # Hallazgo: sin ``boot`` PVE 9.2 fija por su cuenta el mismo orden que DT-O1.
        evidencia("M4-04-orden-por-defecto-del-servidor", boot=conf.get("boot"))
        assert conf["ide2"].startswith(iso_alpine)
        assert conf.get("boot") == "order=scsi0;ide2;net0"


def test_lab_m4_04_seabios_arranca_el_instalador_con_el_disco_vacio(
    sesion14, api14, iso_alpine, vmids
):
    """DT-O1: encendida por root, la MV con disco vacío y ``order=scsi0;ide2;net0`` arranca el
    instalador del CD. Se mide cuántos bytes leyó del CD (>8 MiB = cargó el instalador)."""
    vmid = vmids(9015)
    params = parametros(sesion14, cfg_iso(vmid, iso_alpine, firmware=Firmware.SEABIOS))
    assert params["boot"] == "order=scsi0;ide2;net0"
    crear_con_ok(api14, params)
    leido, _ = arrancar_y_observar(api14, vmid)
    evidencia("M4-04-arranque", firmware="seabios", orden=params["boot"], leido_cd_bytes=leido)
    assert leido > 8 * 1024**2, "el instalador no arrancó (ver EVIDENCIA)"


def test_lab_m4_04_linux_con_ovmf_y_la_peticion_real_arranca_el_iso_sin_firmar(
    sesion14, api14, iso_alpine, vmids
):
    """DEFECTO-LAB-02 (corregido): el constructor real pide ``pre-enrolled-keys=0`` para Linux y
    Alpine (sin firmar) arranca con OVMF: lee casi todo el ISO (70 MB) del CD, no ~2 MiB."""
    vmid = vmids(9016)
    params = parametros(sesion14, cfg_iso(vmid, iso_alpine, tipo_so=TipoSO.LINUX))
    assert params["bios"] == "ovmf"
    assert "pre-enrolled-keys=0" in params["efidisk0"]
    assert params["boot"] == "order=scsi0;ide2;net0"
    crear_con_ok(api14, params)
    assert "pre-enrolled-keys=0" in api14.config(vmid)["efidisk0"]
    leido, _ = arrancar_y_observar(api14, vmid)
    evidencia(
        "M4-04-arranque",
        firmware="ovmf",
        tipo_so="linux",
        orden=params["boot"],
        leido_cd_bytes=leido,
    )
    assert leido > 40 * 1024**2, "Alpine no arrancó con OVMF (ver EVIDENCIA)"


def test_lab_m4_04_windows_con_ovmf_mantiene_las_claves_precargadas_en_la_config(
    sesion14, api14, iso_alpine, vmids
):
    """Windows conserva ``pre-enrolled-keys=1``: la config de Proxmox lo refleja. (Se usa el ISO
    de Alpine como cuerpo del CD: solo se comprueba la configuración, la MV no se enciende.)"""
    vmid = vmids(9018)
    params = parametros(sesion14, cfg_iso(vmid, iso_alpine, tipo_so=TipoSO.WINDOWS_11))
    assert "pre-enrolled-keys=1" in params["efidisk0"]
    crear_con_ok(api14, params)
    efi = api14.config(vmid)["efidisk0"]
    evidencia("M4-04-windows-efidisk", efidisk0=efi)
    assert "pre-enrolled-keys=1" in efi and "efitype=4m" in efi


def test_lab_m4_04_ide0_e_ide2_juntos(sesion14, api14, dos_isos, vmids):
    """CA-O08.7: la ISO en ``ide2`` y los drivers en ``ide0`` conviven en la misma MV."""
    iso, drivers = dos_isos
    vmid = vmids(9017)
    cfg = cfg_iso(
        vmid,
        iso,
        tipo_so=TipoSO.WINDOWS_10,
        firmware=Firmware.SEABIOS,
        detalle_origen=DetalleIso(
            iso=RefVolumen("proxlaunch-lab-alpine.iso", iso),
            drivers=RefVolumen("proxlaunch-lab-drivers.iso", drivers),
        ),
    )
    params = parametros(sesion14, cfg)
    assert params["ide0"].startswith(drivers) and params["ide2"].startswith(iso)
    crear_con_ok(api14, params)
    conf = api14.config(vmid)
    evidencia("M4-04-ide0-ide2", ide0=conf["ide0"], ide2=conf["ide2"], boot=conf.get("boot"))
    assert conf["ide0"].startswith(drivers) and conf["ide2"].startswith(iso)


# =========================================================================================
# LAB-M4-05  Hardware de Windows (sin Windows real)
# =========================================================================================


@pytest.mark.parametrize("storage_efi", [STORAGE, LOCAL], ids=["tpm-en-lvmthin", "tpm-en-local"])
def test_lab_m4_05_hardware_de_windows_11_coincide_con_la_config(
    storage_efi, sesion14, api14, dos_isos, vmids
):
    """RF-O13, CA-O13.1..5: ``ostype=win11``, ``tpmstate0`` v2.0, ``efitype=4m``, ``agent=1``,
    segundo CD en ``ide0`` y ``scsi0`` con ``iothread``/``discard``; el rol de 14 basta."""
    iso, drivers = dos_isos
    vmid = vmids(9020 if storage_efi == STORAGE else 9021)
    cfg = cfg_iso(
        vmid,
        iso,
        tipo_so=TipoSO.WINDOWS_11,
        storage_efi=storage_efi,
        cores=2,
        memoria_mib=4096,
        tpm=True,
        agente_qemu=True,
        discos=[Disco(storage=STORAGE, tamano_gib=1, iothread=True, discard=True)],
        detalle_origen=DetalleIso(
            iso=RefVolumen("proxlaunch-lab-alpine.iso", iso),
            drivers=RefVolumen("proxlaunch-lab-drivers.iso", drivers),
        ),
    )
    params = parametros(sesion14, cfg)
    evidencia(
        "M4-05-post",
        **{
            k: params[k]
            for k in ("ostype", "tpmstate0", "efidisk0", "agent", "ide0", "boot", "scsi0")
        },
    )
    crear_con_ok(api14, params)
    conf = api14.config(vmid)
    evidencia(
        "M4-05-config",
        ostype=conf["ostype"],
        tpmstate0=conf["tpmstate0"],
        efidisk0=conf["efidisk0"],
        agent=conf["agent"],
        machine=conf["machine"],
        bios=conf["bios"],
        scsi0=conf["scsi0"],
    )
    assert conf["ostype"] == "win11" and conf["bios"] == "ovmf" and "q35" in conf["machine"]
    assert "version=v2.0" in conf["tpmstate0"] and conf["tpmstate0"].startswith(f"{storage_efi}:")
    assert "efitype=4m" in conf["efidisk0"]
    assert str(conf["agent"]).startswith("1")
    assert conf["ide0"].startswith(drivers) and conf["ide2"].startswith(iso)
    assert "iothread=1" in conf["scsi0"] and "discard=on" in conf["scsi0"]
    assert conf["scsihw"] == "virtio-scsi-single"
    # formato del volumen del TPM en el storage
    listado = lab.ssh(f"sudo pvesm list {storage_efi} --vmid {vmid}")
    evidencia("M4-05-volumenes", storage=storage_efi, listado=listado.replace("\n", " | "))
    assert "tpmstate0" in conf or "disk" in listado


def test_lab_m4_05_el_rol_de_10_no_basta_para_la_iso_con_boot(sesion14, cred10, iso_alpine, vmids):
    """Información para CA-O13.4: qué ocurre con la misma petición con el rol de 10 privilegios."""
    api = Api(cred10)
    vmid = vmids(9022)
    params = parametros(sesion14, cfg_iso(vmid, iso_alpine))
    r = crear_con(api, params)
    evidencia("M4-05-rol10", respuesta=mensaje(r))
    assert r.status_code == 403


# =========================================================================================
# Servidor HTTP local temporal (LAB-M4-06) — solo 127.0.0.1; el laboratorio lo ve como 10.0.2.2
# =========================================================================================


class _ManejadorLento(http.server.SimpleHTTPRequestHandler):
    """Sirve una carpeta; los archivos ``lento-*`` se entregan a ~7 MiB/s para ver el avance."""

    def log_message(self, *_a: Any) -> None:  # silencio
        return

    def do_GET(self) -> None:  # noqa: N802
        if not self.path.lstrip("/").startswith("lento-"):
            return super().do_GET()
        ruta = Path(self.translate_path(self.path))
        if not ruta.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(ruta.stat().st_size))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        with ruta.open("rb") as f:
            try:
                while bloque := f.read(1 << 20):
                    self.wfile.write(bloque)
                    time.sleep(0.15)
            except (BrokenPipeError, ConnectionResetError):
                return


@pytest.fixture(scope="module")
def servidor_http(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Servidor temporal en 127.0.0.1:PUERTO_HTTP; se cierra al terminar el módulo."""
    raiz = tmp_path_factory.mktemp("www")
    (raiz / "proxlaunch-lab-alpine.iso").symlink_to(ISO_LOCAL)
    (raiz / "lento-alpine.iso").symlink_to(ISO_LOCAL)
    (raiz / "proxlaunch-lab-cirros.qcow2").symlink_to(CIRROS_LOCAL)
    manejador = lambda *a, **k: _ManejadorLento(*a, directory=str(raiz), **k)  # noqa: E731
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", PUERTO_HTTP), manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        visto = lab.ssh(
            f"curl -s -m 10 -o /dev/null -w '%{{http_code}}' http://{IP_ANFITRION}:{PUERTO_HTTP}/proxlaunch-lab-alpine.iso -I",
            comprobar=False,
        )
        assert visto.strip() == "200", f"el laboratorio no ve el servidor local: {visto!r}"
        yield f"http://{IP_ANFITRION}:{PUERTO_HTTP}"
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=10)


def _url(texto: str) -> Any:
    url, error = validar_url(texto, permitir_http=True)
    assert error is None and url is not None, error
    return url


def _checksum(hexa: str) -> Any:
    from proxlaunch.nucleo.transferencias.url import validar_checksum

    ck, error = validar_checksum(hexa)
    assert error is None and ck is not None, error
    return ck


def descargar(
    sesion: Any,
    url: str,
    nombre: str,
    *,
    checksum: str | None = None,
    verificar: bool = True,
    contenido: Contenido = Contenido.ISO,
    permitir_http: bool = True,
    progresos: list[Any] | None = None,
) -> Any:
    inv = descubrir(sesion)
    u, error = validar_url(url, permitir_http=permitir_http)
    assert error is None and u is not None, error
    return servicio_transferencias(sesion).descargar(
        u,
        destino(contenido, nombre),
        inv,
        checksum=_checksum(checksum) if checksum else None,
        verificar_certificados=verificar,
        al_progresar=(progresos.append if progresos is not None else (lambda _p: None)),
        dejar_de_esperar=threading.Event(),
    )


# =========================================================================================
# LAB-M4-06  Descarga por URL
# =========================================================================================


def test_lab_m4_06_query_url_metadata_ve_nombre_y_tamano(sesion14, servidor_http):
    """CA-O11.1: ``query-url-metadata`` (lo ve el SERVIDOR, no la app) da nombre y tamaño."""
    meta = servicio_transferencias(sesion14).consultar_url(
        NODO, _url(f"{servidor_http}/proxlaunch-lab-alpine.iso"), verificar_certificados=False
    )
    evidencia("M4-06-metadata", nombre=meta.nombre, tamano=meta.tamano, tipo=meta.tipo_mime)
    assert meta.tamano == TAM_ALPINE and meta.nombre == "proxlaunch-lab-alpine.iso"


def test_lab_m4_06_descarga_con_checksum_y_progreso_del_log(sesion14, api14, servidor_http):
    """CA-O11.2..5: descarga con checksum correcto; tamaño y sha256 en el nodo; ¿trae el log de la
    tarea porcentaje?"""
    progresos: list[Any] = []
    r = descargar(
        sesion14,
        f"{servidor_http}/lento-alpine.iso",
        "proxlaunch-lab-descarga.iso",
        checksum=SHA256_ALPINE,
        verificar=False,
        progresos=progresos,
    )
    try:
        assert r.estado == EstadoTransferencia.TERMINADA, r
        assert r.volid == "local:iso/proxlaunch-lab-descarga.iso"
        en_nodo = lab.ssh(
            "sudo sha256sum /var/lib/vz/template/iso/proxlaunch-lab-descarga.iso"
        ).split()[0]
        assert en_nodo == SHA256_ALPINE
        _, log, _ = api14.tarea(r.upid)
        porcentajes = [
            p.porcentaje_servidor for p in progresos if p.porcentaje_servidor is not None
        ]
        emisiones = len(progresos)
        con_porcentaje = [ln for ln in log if "%" in ln]
        evidencia(
            "M4-06-log-descarga",
            duracion_s=round(r.duracion_s, 1),
            lineas_log=len(log),
            lineas_con_porcentaje=len(con_porcentaje),
            muestra=log[:4] + con_porcentaje[:3],
            porcentajes_en_progreso=porcentajes[:6],
            emisiones_de_progreso=emisiones,
        )
        assert len(con_porcentaje) >= 1  # el log trae «NN%» (wget), aunque se vuelque casi al final
    finally:
        borrar_archivos_lab()


def test_lab_m4_06_checksum_erroneo_no_deja_archivo(sesion14, servidor_http):
    """CA-O11.6: con un checksum que no coincide la tarea falla y no hay archivo."""
    r = descargar(
        sesion14,
        f"{servidor_http}/proxlaunch-lab-alpine.iso",
        "proxlaunch-lab-malsha.iso",
        checksum="1" * 64,
        verificar=False,
    )
    evidencia(
        "M4-06-checksum-malo",
        estado=str(r.estado),
        codigo=str(r.error.codigo) if r.error else None,
        quedo=r.quedo_archivo,
    )
    assert r.estado == EstadoTransferencia.FALLIDA
    assert archivos_lab() == []


def test_lab_m4_06_url_inexistente_falla_limpia(sesion14, servidor_http):
    """CA-O11.7: una URL que da 404 falla sin dejar archivo."""
    r = descargar(
        sesion14,
        f"{servidor_http}/proxlaunch-lab-no-existe.iso",
        "proxlaunch-lab-404.iso",
        verificar=False,
    )
    evidencia("M4-06-404", estado=str(r.estado), codigo=str(r.error.codigo) if r.error else None)
    assert r.estado == EstadoTransferencia.FALLIDA
    assert archivos_lab() == []


def test_lab_m4_06_verify_certificates_rechaza_un_certificado_autofirmado(api14):
    """CA-O11.8: con ``verify-certificates=1`` el nodo rechaza el certificado autofirmado de su
    propia API; con ``0`` lo acepta."""
    url = "https://127.0.0.1:8006/pve2/images/logo-128.png"
    estricto = api14.get(f"/nodes/{NODO}/query-url-metadata", url=url, **{"verify-certificates": 1})
    laxo = api14.get(f"/nodes/{NODO}/query-url-metadata", url=url, **{"verify-certificates": 0})
    evidencia("M4-06-verify", con_verificacion=mensaje(estricto), sin_verificacion=laxo.status_code)
    assert estricto.status_code != 200 and "certificate verify failed" in estricto.text.lower()
    assert "certificate" not in laxo.text.lower()  # sin verificación ya no falla por el certificado


def test_lab_m4_06_sin_sys_access_network_la_vía_no_se_ofrece_y_falla_limpia(
    entorno_m4, servidor_http
):
    """CA-O11.3: sin ``Sys.AccessNetwork`` el núcleo no ofrece la vía y, si se intenta, falla sin
    dejar archivo."""
    menos = tuple(p for p in PRIVS14 if p != "Sys.AccessNetwork")
    with usuario_con(menos, "Menos") as c:
        sesion = abrir_sesion(entorno_m4, c)
        try:
            inv = descubrir(sesion)
            caps = calcular_capacidades(sesion.capacidades, inv, NODO)
            estado = caps.estado(Via.DESCARGAR_URL)
            evidencia(
                "M4-06-sin-AccessNetwork", via=estado.disponibilidad, codigo=str(estado.codigo)
            )
            assert estado.disponibilidad == Disponibilidad.NO
            r = descargar(
                sesion,
                f"{servidor_http}/proxlaunch-lab-alpine.iso",
                "proxlaunch-lab-sinred.iso",
                verificar=False,
            )
            assert r.estado == EstadoTransferencia.FALLIDA and r.error is not None
            evidencia("M4-06-sin-AccessNetwork-error", codigo=str(r.error.codigo))
            assert archivos_lab() == []
        finally:
            entorno_m4.servicio.cerrar_sesion(sesion)


def test_lab_m4_06_descarga_https_real_desde_internet(sesion14, api14):
    """El nodo anidado SÍ tiene Internet: descarga la ISO oficial por HTTPS con verificación de
    certificado y la compara con el sha256 oficial."""
    oficial = (
        "https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/alpine-virt-3.24.4-x86_64.iso"
    )
    meta = servicio_transferencias(sesion14).consultar_url(NODO, _url(oficial))
    evidencia("M4-06-internet-metadata", nombre=meta.nombre, tamano=meta.tamano)
    r = descargar(
        sesion14,
        oficial,
        "proxlaunch-lab-oficial.iso",
        checksum=SHA256_ALPINE,
        verificar=True,
        permitir_http=False,
    )
    try:
        evidencia("M4-06-internet", estado=str(r.estado), duracion_s=round(r.duracion_s, 1))
        assert r.estado == EstadoTransferencia.TERMINADA, r
    finally:
        borrar_archivos_lab()


# =========================================================================================
# LAB-M4-07  virtio-win (opcional)
# =========================================================================================

TAM_VIRTIO_WIN = 877_373_440  # medido en el laboratorio (ISO 0.1.302)


def test_lab_m4_07_virtio_win_real_se_descarga_en_el_servidor_con_su_sha256(sesion14, api14):
    """RF-O14, CA-O14.6: el núcleo descarga en el servidor la ISO virtio-win con las constantes
    reales (``URL_VIRTIO_WIN`` + ``SHA256_VIRTIO_WIN``, ``download-url`` con checksum) y el sha256
    calculado en el nodo coincide. Después se borra."""
    from proxlaunch.nucleo.origen.constantes import SHA256_VIRTIO_WIN, URL_VIRTIO_WIN

    assert URL_VIRTIO_WIN and SHA256_VIRTIO_WIN
    servicio = servicio_transferencias(sesion14)
    try:
        meta = servicio.consultar_url(NODO, _url(URL_VIRTIO_WIN))
    except ErrorProxLaunch as e:
        evidencia("M4-07-metadata-error", codigo=str(e.codigo))
        pytest.skip(f"el nodo no alcanza la URL de virtio-win ({e.codigo})")
    evidencia("M4-07-metadata", nombre=meta.nombre, tamano=meta.tamano, tipo=meta.tipo_mime)
    r = descargar(
        sesion14,
        URL_VIRTIO_WIN,
        "virtio-win-0.1.302.iso",
        checksum=SHA256_VIRTIO_WIN,
        verificar=True,
        permitir_http=False,
    )
    try:
        evidencia(
            "M4-07-descarga", estado=str(r.estado), duracion_s=round(r.duracion_s, 1), error=r.error
        )
        assert r.estado == EstadoTransferencia.TERMINADA, r
        salida = lab.ssh(
            "sudo stat -c %s /var/lib/vz/template/iso/virtio-win-0.1.302.iso; "
            "sudo sha256sum /var/lib/vz/template/iso/virtio-win-0.1.302.iso",
            timeout=600,
        ).split()
        tam, sha = int(salida[0]), salida[1]
        evidencia("M4-07-sha256", tamano_real=tam, sha256=sha, url=URL_VIRTIO_WIN)
        assert sha == SHA256_VIRTIO_WIN
        assert tam == TAM_VIRTIO_WIN
        assert meta.tamano is None or tam == meta.tamano
    finally:
        borrar_archivos_lab()
        lab.ssh("sudo rm -f /var/lib/vz/template/iso/virtio-win-0.1.302.iso", comprobar=False)


# =========================================================================================
# LAB-M4-08  Importación de imágenes (contenido import)
# =========================================================================================


@pytest.fixture
def imagen_cirros(sesion14: Any, con_import: None) -> Iterator[str]:
    """``proxlaunch-lab-cirros.qcow2`` subida con el núcleo a ``local:import`` (import activo)."""
    borrar_archivos_lab()
    r = subir(sesion14, CIRROS_LOCAL, Contenido.IMPORT, "proxlaunch-lab-cirros.qcow2")
    assert r.estado == EstadoTransferencia.TERMINADA, r
    yield r.volid


def _subida_cruda(
    api: Api, nombre: str, contenido: bytes | Path, tipo: str = "import"
) -> requests.Response:
    datos = contenido.read_bytes() if isinstance(contenido, Path) else contenido
    return requests.post(
        f"{URL}/nodes/{NODO}/storage/{LOCAL}/upload",
        headers=api._cab,
        data={"content": tipo},
        files={"filename": (nombre, datos, "application/octet-stream")},
        verify=False,
        timeout=120,
    )


def test_lab_m4_08_subir_qcow2_y_tamano_que_devuelve_import(sesion14, imagen_cirros):
    """RF-O15, RF-O16: subida con token; ¿``size`` de ``content=import`` es el archivo o el
    tamaño virtual?"""
    assert imagen_cirros == "local:import/proxlaunch-lab-cirros.qcow2"
    inv = descubrir(sesion14)
    listados = ServicioCatalogo(sesion14, RelojReal()).listar(inv, NODO, Contenido.IMPORT)
    vol = next(v for lst in listados for v in lst.volumenes if v.volid == imagen_cirros)
    archivo = CIRROS_LOCAL.stat().st_size
    virtual = 117440512
    evidencia(
        "M4-08-size-import",
        size_api=vol.tamano_bytes,
        tamano_archivo=archivo,
        tamano_virtual=virtual,
        es="archivo"
        if vol.tamano_bytes == archivo
        else "virtual"
        if vol.tamano_bytes == virtual
        else "otro",
    )
    assert vol.tamano_bytes == archivo, "size de content=import NO es el tamaño del archivo"
    assert lab.ssh("sudo stat -c %s /var/lib/vz/import/proxlaunch-lab-cirros.qcow2").strip() == str(
        archivo
    )


def test_lab_m4_08_qcow2_con_backing_file_se_rechaza_en_la_app_y_en_el_servidor(
    sesion14, api14, con_import
):
    """CA-O16.2/4: un qcow2 con *backing file* lo rechaza la app (antes de enviar) y también el
    servidor si se le manda por la API."""
    from proxlaunch.nucleo.transferencias.archivo_local import inspeccionar

    insp = inspeccionar(BACKING_LOCAL, Contenido.IMPORT)
    evidencia("M4-08-backing-app", motivo=insp.motivo_rechazo, tipo=str(insp.tipo))
    assert insp.motivo_rechazo is not None
    resp = _subida_cruda(api14, "proxlaunch-lab-backing.qcow2", BACKING_LOCAL)
    estado = "n/a"
    if resp.status_code == 200:
        estado, log, _ = api14.tarea(resp.json()["data"])
        evidencia("M4-08-backing-servidor", http=200, tarea=estado, log=log[-3:])
    else:
        evidencia("M4-08-backing-servidor", http=resp.status_code, cuerpo=resp.text[:200])
    quedo = archivos_lab()
    evidencia("M4-08-backing-quedo", archivos=quedo)
    assert (resp.status_code != 200 or estado != "OK") and quedo == [], (
        "el servidor aceptó el backing file"
    )


def test_lab_m4_08_ova_se_rechaza_en_la_app_y_se_observa_el_servidor(api14, con_import):
    """CA-O16.6: la app rechaza ``.ova``; se registra qué hace el servidor con ella."""
    from proxlaunch.nucleo.transferencias.archivo_local import inspeccionar

    insp = inspeccionar(OVA_LOCAL, Contenido.IMPORT)
    evidencia("M4-08-ova-app", motivo=insp.motivo_rechazo, tipo=str(insp.tipo))
    assert insp.motivo_rechazo is not None
    resp = _subida_cruda(api14, "proxlaunch-lab-falso.ova", OVA_LOCAL)
    if resp.status_code == 200:
        estado, log, _ = api14.tarea(resp.json()["data"])
    else:
        estado, log = f"http {resp.status_code}", [resp.text[:200]]
    evidencia("M4-08-ova-servidor", resultado=estado, log=log[-2:], archivos=archivos_lab())


def test_lab_m4_08_ruta_absoluta_en_import_from_solo_la_puede_pasar_root(
    sesion14, api14, imagen_cirros, vmids
):
    """CA-O15.3: ``import-from`` con una ruta del sistema de archivos da el error esperado."""
    vmid = vmids(9031)
    r = crear_con(
        api14,
        {
            "vmid": str(vmid),
            "name": "plc-m4-ruta",
            "memory": "128",
            "scsi0": f"{STORAGE}:0,import-from=/var/lib/vz/import/proxlaunch-lab-cirros.qcow2",
        },
    )
    evidencia("M4-08-ruta-absoluta", respuesta=mensaje(r))
    assert r.status_code in (400, 403, 500)
    assert "Only root can pass arbitrary filesystem paths" in r.text
    assert vmid not in lab.vmids_de_prueba()


# =========================================================================================
# LAB-M4-09  Crear con import-from
# =========================================================================================


def cfg_import(vmid: int, volid: str, **extra: Any) -> ConfiguracionVM:
    base: dict[str, Any] = {
        "vmid": vmid,
        "nombre": f"plc-m4-{vmid}",
        "nodo": NODO,
        "cores": 1,
        "memoria_mib": 256,
        "discos": [Disco(storage=STORAGE, tamano_gib=1)],
        "redes": [InterfazRed(bridge="vmbr0")],
        "origen": OrigenSO.IMPORTAR_DISCO,
        "detalle_origen": DetalleImportacion(imagen=RefVolumen(volid.split("/")[-1], volid)),
        "tipo_so": TipoSO.LINUX,
    }
    base.update(extra)
    return ConfiguracionVM(**base)


def test_lab_m4_09_crear_con_import_from_en_lvmthin(sesion14, api14, imagen_cirros, vmids):
    """RF-O17, CA-O17.x: el disco queda raw en ``lab-lvmthin`` con el tamaño virtual de la imagen;
    se miden el tiempo y si el log trae progreso; luego ``resize`` absoluto (CA-O18.4)."""
    vmid = vmids(9030)
    params = parametros(sesion14, cfg_import(vmid, imagen_cirros))
    assert params["scsi0"].startswith(f"{STORAGE}:0,import-from={imagen_cirros}")
    t0 = time.monotonic()
    resp = crear_con(api14, params)
    assert resp.status_code == 200, mensaje(resp)
    estado, log, _ = api14.tarea(resp.json()["data"])
    segundos = time.monotonic() - t0
    assert estado == "OK", (estado, log[-3:])
    conf = api14.config(vmid)
    con_progreso = [ln for ln in log if "%" in ln]
    evidencia(
        "M4-09-import",
        scsi0=conf["scsi0"],
        segundos=round(segundos, 2),
        lineas_log=len(log),
        lineas_con_porcentaje=len(con_progreso),
        muestra=(con_progreso[:2] + log[:2]),
    )
    assert conf["scsi0"].startswith(f"{STORAGE}:vm-{vmid}-disk-") and "size=112M" in conf["scsi0"]
    assert "format=" not in conf["scsi0"]  # lvmthin es raw
    # resize absoluto
    upid = sesion14.cliente.ampliar_disco(NODO, vmid, "scsi0", 2)
    if upid:
        assert api14.tarea(upid)[0] == "OK"
    evidencia("M4-09-resize-devuelve", upid="UPID" if upid else None)
    assert "size=2G" in api14.config(vmid)["scsi0"]
    try:
        upid = sesion14.cliente.ampliar_disco(NODO, vmid, "scsi0", 2)
        if upid:
            api14.tarea(upid)
        otra = "sin error"
    except ErrorProxLaunch as e:
        otra = f"error {e.codigo}: {e.detalle_tecnico[:120]}"
    evidencia("M4-09-resize-repetido", resultado=otra)
    assert "size=2G" in api14.config(vmid)["scsi0"]


def test_lab_m4_09_lote_de_tres_importaciones_simultaneas(sesion14, api14, imagen_cirros, vmids):
    """RF-O18: tres importaciones a la vez: todas terminan y se anotan los tiempos."""
    ids = [vmids(9030), vmids(9031), vmids(9032)]
    tiempos: dict[int, float] = {}
    errores: list[str] = []

    def uno(vmid: int) -> None:
        try:
            tiempos[vmid] = crear_con_ok(
                api14, parametros(sesion14, cfg_import(vmid, imagen_cirros))
            )
        except AssertionError as e:
            errores.append(f"{vmid}: {e}")

    t0 = time.monotonic()
    hilos = [threading.Thread(target=uno, args=(v,)) for v in ids]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    total = time.monotonic() - t0
    evidencia(
        "M4-09-lote3",
        tiempos={k: round(v, 2) for k, v in tiempos.items()},
        total_s=round(total, 2),
        errores=errores,
    )
    assert not errores and len(tiempos) == 3


def _usuario_con_alloc(destino: list[str], lectura_origen: bool) -> Any:
    """Rol de 14 SIN ``Datastore.AllocateSpace`` global; esa pieza se concede por storage."""
    base = tuple(p for p in PRIVS14 if p != "Datastore.AllocateSpace")
    return base


@pytest.mark.parametrize(
    ("alloc_en", "audit_en", "esperado"),
    [
        ([STORAGE], [], "falla_leer_origen"),
        ([STORAGE], [LOCAL], "crea"),
        ([LOCAL], [], "falla_destino"),
        ([STORAGE, LOCAL], [], "crea"),
    ],
    ids=["alloc-solo-destino", "alloc-destino+audit-origen", "alloc-solo-origen", "alloc-en-ambos"],
)
def test_lab_m4_09_variantes_del_permiso_de_lectura_de_la_fuente(
    alloc_en, audit_en, esperado, sesion14, imagen_cirros, vmids
):
    """CA-O17.x: qué privilegio hace falta para leer la imagen fuente y para el destino. Se prueba
    el rol de 14 sin ``Datastore.AllocateSpace`` global y con ACL puntuales por storage."""
    base = _usuario_con_alloc(alloc_en, bool(audit_en))
    with usuario_con(base, "Menos") as c:
        userid = c.userid
        lab.ssh(
            "sudo pveum role add PlcM4Aloc --privs Datastore.AllocateSpace; sudo pveum role add PlcM4Audit --privs Datastore.Audit"
        )
        try:
            for st in alloc_en:
                lab.ssh(
                    f"sudo pveum acl modify /storage/{st} --users {userid} --roles PlcM4Aloc --propagate 1"
                )
            for st in audit_en:
                lab.ssh(
                    f"sudo pveum acl modify /storage/{st} --users {userid} --roles PlcM4Audit --propagate 1"
                )
            vmid = vmids(9033)
            params = parametros(sesion14, cfg_import(vmid, imagen_cirros))
            api = Api(c)
            r = crear_con(api, params)
            detalle = mensaje(r)
            if r.status_code == 200:
                estado, log, _ = api.tarea(r.json()["data"])
                detalle = f"tarea {estado} {log[-1:]}"
            evidencia(
                "M4-09-permiso-lectura",
                alloc_en=alloc_en,
                audit_en=audit_en,
                http=r.status_code,
                detalle=detalle[:200],
            )
            creada = vmid in lab.vmids_de_prueba()
            assert creada == (esperado == "crea"), (esperado, detalle)
        finally:
            lab.ssh(
                "sudo pveum role delete PlcM4Aloc; sudo pveum role delete PlcM4Audit",
                comprobar=False,
            )


def test_lab_m4_09_fallo_a_mitad_deja_o_no_un_volumen_suelto(sesion14, api14, con_import, vmids):
    """CA-O30.4: importar una imagen cortada falla; se mira si queda MV o volumen suelto."""
    borrar_archivos_lab()
    datos = CIRROS_LOCAL.read_bytes()[: 4 * 1024 * 1024]
    resp = _subida_cruda(api14, "proxlaunch-lab-roto.qcow2", datos)
    evidencia("M4-09-roto-subida", http=resp.status_code, cuerpo=resp.text[:160])
    if resp.status_code == 200:
        estado, _, _ = api14.tarea(resp.json()["data"])
        evidencia("M4-09-roto-subida-tarea", estado=estado)
    if "local:import/proxlaunch-lab-roto.qcow2" not in archivos_lab():
        pytest.skip(
            "el servidor no aceptó la imagen cortada: no se puede provocar el fallo a mitad"
        )
    vmid = vmids(9034)
    r = crear_con(
        api14,
        {
            "vmid": str(vmid),
            "name": "plc-m4-roto",
            "memory": "128",
            "scsi0": f"{STORAGE}:0,import-from=local:import/proxlaunch-lab-roto.qcow2",
        },
    )
    if r.status_code == 200:
        estado, log, _ = api14.tarea(r.json()["data"])
    else:
        estado, log = f"http {r.status_code}", [r.text[:200]]
    existe = vmid in lab.vmids_de_prueba()
    sueltos = lab.ssh(f"sudo pvesm list {STORAGE} --vmid {vmid} | tail -n +2").strip()
    evidencia(
        "M4-09-roto-resultado",
        tarea=estado,
        log=log[-2:],
        mv_existe=existe,
        volumenes_sueltos=sueltos or "ninguno",
    )
    assert estado != "OK"
    assert not sueltos, f"quedó un volumen suelto: {sueltos}"


def test_lab_m4_09_destino_local_con_format_qcow2(sesion14, api14, imagen_cirros, vmids):
    """RF-O17: destino ``local`` (directorio) con ``format=qcow2``."""
    vmid = vmids(9035)
    disco = Disco(storage=LOCAL, tamano_gib=1)
    params = parametros(sesion14, cfg_import(vmid, imagen_cirros, discos=[disco]))
    evidencia("M4-09-local-post", scsi0=params["scsi0"])
    assert "format=qcow2" in params["scsi0"]
    segundos = crear_con_ok(api14, params)
    conf = api14.config(vmid)
    evidencia("M4-09-local", scsi0=conf["scsi0"], segundos=round(segundos, 2))
    assert (
        conf["scsi0"].startswith(f"{LOCAL}:{vmid}/vm-{vmid}-disk-0.qcow2")
        and "size=112M" in conf["scsi0"]
    )


# =========================================================================================
# LAB-M4-10  Clonación de plantillas
# =========================================================================================


def clonar(api: Api, origen: int, nuevo: int, **extra: Any) -> requests.Response:
    datos: dict[str, Any] = {"newid": nuevo, "name": f"plc-m4-{nuevo}"}
    datos.update(extra)
    return api.post(f"/nodes/{NODO}/qemu/{origen}/clone", **datos)


def clonar_ok(api: Api, origen: int, nuevo: int, **extra: Any) -> float:
    t0 = time.monotonic()
    resp = clonar(api, origen, nuevo, **extra)
    assert resp.status_code == 200, mensaje(resp)
    estado, log, _ = api.tarea(resp.json()["data"])
    assert estado == "OK", (estado, log[-3:])
    return time.monotonic() - t0


def mac_de(conf: dict[str, Any]) -> str:
    m = re.search(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", str(conf["net0"]))
    assert m is not None
    return m.group(1).upper()


def test_lab_m4_10_la_plantilla_se_ve_y_el_modo_automatico_es_enlazado(sesion14, plantilla):
    """RF-O19, CA-O21: el núcleo ve la plantilla, parsea su configuración y elige enlazado (lvmthin)."""
    from proxlaunch.nucleo.modelos.origen import DetalleClon, ModoClon, RefPlantilla
    from proxlaunch.nucleo.origen.clon import modo_efectivo

    catalogo = ServicioCatalogo(sesion14, RelojReal())
    fin = time.monotonic() + 40
    visibles = {p.vmid: p for p in catalogo.plantillas()}
    while plantilla not in visibles and time.monotonic() < fin:  # pvestatd refresca cada ~10 s
        time.sleep(2)
        visibles = {p.vmid: p for p in catalogo.plantillas()}
    evidencia("M4-10-visibilidad", visible=plantilla in visibles)
    assert plantilla in visibles
    detalle = catalogo.detalle_plantilla(NODO, plantilla)
    assert detalle is not None
    inv = descubrir(sesion14)
    modo, problema = modo_efectivo(
        DetalleClon(RefPlantilla("plc-m4-plantilla", plantilla, NODO)), detalle, inv, NODO
    )
    evidencia(
        "M4-10-plantilla",
        discos=[(d.clave, d.storage) for d in detalle.discos],
        modo=str(modo),
        cores=detalle.cores,
    )
    assert problema is None and modo == ModoClon.ENLAZADO


def test_lab_m4_10_tiempos_con_un_clon_y_con_tres_simultaneos(api14, plantilla, vmids):
    """RF-O21, CA-O21.x (decide P-O03): 1 clon enlazado frente a 3 simultáneos en el mismo nodo:
    tiempos, ¿errores de bloqueo?, MACs distintas entre sí y de la plantilla (CA-O22.10)."""
    uno = vmids(9051)
    t1 = clonar_ok(api14, plantilla, uno)
    base_mac = mac_de(api14.config(plantilla))
    macs = {mac_de(api14.config(uno))}
    ids = [vmids(9052), vmids(9053), vmids(9054)]
    resultados: dict[int, tuple[str, float]] = {}
    lock_visto: list[str] = []
    fin = threading.Event()

    def uno_a_uno(v: int) -> None:
        t0 = time.monotonic()
        resp = clonar(api14, plantilla, v)
        if resp.status_code != 200:
            resultados[v] = (mensaje(resp), time.monotonic() - t0)
            return
        estado, log, _ = api14.tarea(resp.json()["data"])
        resultados[v] = (
            estado if estado == "OK" else f"{estado} {log[-1:]}",
            time.monotonic() - t0,
        )

    def vigilar() -> None:
        while not fin.is_set():
            r = api14.get(f"/nodes/{NODO}/qemu/{plantilla}/config")
            if r.status_code == 200 and "lock" in r.json()["data"]:
                lock_visto.append(str(r.json()["data"]["lock"]))
            time.sleep(0.05)

    vigia = threading.Thread(target=vigilar, daemon=True)
    vigia.start()
    t0 = time.monotonic()
    hilos = [threading.Thread(target=uno_a_uno, args=(v,)) for v in ids]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    total3 = time.monotonic() - t0
    fin.set()
    vigia.join(timeout=5)
    for v in ids:
        macs.add(mac_de(api14.config(v)))
    # el mismo trabajo, de uno en uno (para comparar)
    secuencial = []
    for v in [vmids(9055), vmids(9056), vmids(9057)]:
        secuencial.append(clonar_ok(api14, plantilla, v))
    evidencia(
        "M4-10-tiempos",
        un_clon_s=round(t1, 2),
        tres_simultaneos_total_s=round(total3, 2),
        tres_simultaneos_cada_uno_s={k: round(v[1], 2) for k, v in resultados.items()},
        tres_secuencial_total_s=round(sum(secuencial), 2),
        estados={k: v[0] for k, v in resultados.items()},
        lock_en_la_plantilla=sorted(set(lock_visto)),
        macs_distintas=len(macs),
        mac_plantilla_distinta=base_mac not in macs,
    )
    assert all(v[0] == "OK" for v in resultados.values()), resultados
    assert len(macs) == 4 and base_mac not in macs


def test_lab_m4_10_clon_completo_a_local_con_qcow2(api14, plantilla, vmids):
    """RF-O19: clon completo con ``storage=local`` y ``format=qcow2``."""
    nuevo = vmids(9058)
    s = clonar_ok(api14, plantilla, nuevo, full=1, storage=LOCAL, format="qcow2")
    conf = api14.config(nuevo)
    evidencia("M4-10-completo", scsi0=conf["scsi0"], segundos=round(s, 2))
    assert conf["scsi0"].startswith(f"{LOCAL}:{nuevo}/vm-{nuevo}-disk-0.qcow2")


def test_lab_m4_10_etiquetas_por_put_config_y_resize(sesion14, api14, plantilla, vmids):
    """RF-O22, CA-O22.x: tras clonar, ``tags`` (unión), ``cores``/``memory`` y ``resize`` absoluto
    con el rol de 14; ``clone`` mismo no admite ``tags`` (por eso el PUT)."""
    nuevo = vmids(9051)
    clonar_ok(api14, plantilla, nuevo)
    r = clonar(api14, plantilla, vmids(9052), tags="proxlaunch")
    evidencia("M4-10-clone-con-tags", respuesta=mensaje(r))
    assert r.status_code != 200  # clone no admite ``tags``
    antes = api14.config(nuevo)
    r = api14.put(
        f"/nodes/{NODO}/qemu/{nuevo}/config", tags="proxlaunch;lote-lab", cores=2, memory=192
    )
    assert r.status_code == 200, mensaje(r)
    upid = sesion14.cliente.ampliar_disco(NODO, nuevo, "scsi0", 2)
    if upid:
        assert api14.tarea(upid)[0] == "OK"
    conf = api14.config(nuevo)
    evidencia(
        "M4-10-ajustes",
        tags=conf.get("tags"),
        cores=conf["cores"],
        memory=conf["memory"],
        scsi0=conf["scsi0"],
        mac_igual=mac_de(antes) == mac_de(conf),
    )
    assert set(str(conf["tags"]).split(";")) == {"proxlaunch", "lote-lab"}
    assert (int(conf["cores"]), int(conf["memory"])) == (2, 192) and "size=2G" in conf["scsi0"]


def test_lab_m4_10_tpm_en_clon_completo_y_enlazado(api14, vmids):
    """RF-O23: plantilla con ``tpmstate0`` (≥ 8.4): clon completo y enlazado; se anota el resultado."""
    lab.ssh(
        "sudo qm create 9049 --name plc-m4-plantilla-tpm --memory 128 --bios ovmf --machine q35 "
        f"--efidisk0 {STORAGE}:1,efitype=4m,pre-enrolled-keys=0 --tpmstate0 {STORAGE}:1,version=v2.0 "
        f"--scsi0 {STORAGE}:1 --scsihw virtio-scsi-single --net0 virtio,bridge=vmbr0 && sudo qm template 9049",
        timeout=120,
    )
    try:
        completo = vmids(9051)
        s = clonar_ok(api14, 9049, completo, full=1)
        conf = api14.config(completo)
        evidencia("M4-10-tpm-completo", tpmstate0=conf.get("tpmstate0"), segundos=round(s, 2))
        assert "tpmstate0" in conf and "version=v2.0" in conf["tpmstate0"]
        enlazado = vmids(9052)
        r = clonar(api14, 9049, enlazado)
        if r.status_code == 200:
            estado, log, _ = api14.tarea(r.json()["data"])
            res = f"tarea {estado} {log[-1:]}"
        else:
            res = mensaje(r)
        evidencia(
            "M4-10-tpm-enlazado", resultado=res[:300], existe=enlazado in lab.vmids_de_prueba()
        )
    finally:
        limpiar_vms([9049, 9051, 9052])


def test_lab_m4_10_negativo_storage_en_un_clon_enlazado(api14, plantilla, vmids):
    """V-O21: ``storage`` junto a un clon enlazado (sin ``full``) no es un clon enlazado válido."""
    nuevo = vmids(9051)
    r = clonar(api14, plantilla, nuevo, storage=LOCAL)
    detalle = mensaje(r)
    if r.status_code == 200:
        estado, log, _ = api14.tarea(r.json()["data"])
        detalle = f"tarea {estado} {log[-1:]}"
        conf = api14.config(nuevo)
        evidencia("M4-10-storage-en-enlazado", resultado=detalle, scsi0=conf["scsi0"])
    else:
        evidencia("M4-10-storage-en-enlazado", resultado=detalle)
    assert nuevo not in lab.vmids_de_prueba() or "base-" not in api14.config(nuevo)["scsi0"], (
        detalle
    )


def test_lab_m4_10_enlazado_sobre_raw_en_directorio_y_decision_de_la_app(sesion14, api14, vmids):
    """V-O21: el laboratorio solo tiene lvmthin y dir; no hay un backend SIN clon enlazado (LVM grueso,
    etc.), así que ese negativo no es reproducible. Se anota qué hace el servidor con una plantilla raw
    en un directorio y se comprueba que la decisión de la app coincide con el servidor."""
    from proxlaunch.nucleo.modelos.origen import DetalleClon, ModoClon, RefPlantilla
    from proxlaunch.nucleo.origen.clon import modo_efectivo

    lab.ssh(
        "sudo qm create 9048 --name plc-m4-plantilla-raw --memory 128 --scsi0 local:1,format=raw "
        "&& sudo qm template 9048",
        timeout=120,
    )
    try:
        nuevo = vmids(9051)
        r = clonar(api14, 9048, nuevo)
        detalle = mensaje(r)
        if r.status_code == 200:
            estado, log, _ = api14.tarea(r.json()["data"])
            detalle = f"tarea {estado} {log[-1:]}"
        conf = api14.config(nuevo) if nuevo in lab.vmids_de_prueba() else {}
        detalle_pl = ServicioCatalogo(sesion14, RelojReal()).detalle_plantilla(NODO, 9048)
        assert detalle_pl is not None
        modo, problema = modo_efectivo(
            DetalleClon(RefPlantilla("plc-m4-plantilla-raw", 9048, NODO)),
            detalle_pl,
            descubrir(sesion14),
            NODO,
        )
        evidencia(
            "M4-10-enlazado-sobre-raw-dir",
            servidor=detalle[:200],
            scsi0=conf.get("scsi0"),
            app_modo=str(modo),
            app_problema=problema,
        )
        assert "OK" in detalle  # el servidor lo permite (superposición qcow2 sobre base raw)
        assert modo == ModoClon.ENLAZADO and problema is None  # la app coincide con el servidor
        completo = vmids(9052)
        clonar_ok(api14, 9048, completo, full=1)
    finally:
        limpiar_vms([9048, 9051, 9052])


@pytest.mark.parametrize(
    ("storage", "plantilla_protegida"),
    [
        # HALLAZGO-LAB-03 (documentado, no es un defecto): en lvmthin PVE 9.2 SÍ destruye la
        # plantilla aunque tenga clones enlazados (snapshots thin independientes). La interfaz ya
        # no promete que Proxmox lo impida: avisa de que no se borre mientras existan clones.
        pytest.param(STORAGE, False, id="lvmthin-el-servidor-permite-destruirla"),
        pytest.param(LOCAL, True, id="directorio-el-servidor-la-protege"),
    ],
)
def test_lab_m4_10_borrar_la_plantilla_con_clones_enlazados_segun_el_storage(
    storage, plantilla_protegida, api14, vmids
):
    """CA-O21.x / HALLAZGO-LAB-03: en dir la plantilla con un clon enlazado vivo no se destruye;
    en lvmthin sí se destruye y el clon sigue existiendo y arrancable (plantilla propia de la
    prueba, para no tocar la plantilla compartida)."""
    lab.ssh(
        f"sudo qm create 9047 --name plc-m4-plantilla-borrar --memory 128 --scsi0 {storage}:1 "
        "&& sudo qm template 9047",
        timeout=120,
    )
    try:
        nuevo = vmids(9051)
        clonar_ok(api14, 9047, nuevo)
        r = api14.delete(f"/nodes/{NODO}/qemu/9047", **{"destroy-unreferenced-disks": 0})
        detalle = mensaje(r)
        if r.status_code == 200:
            estado, log, _ = api14.tarea(r.json()["data"])
            detalle = f"tarea {estado} {log[-1:]}"
        sigue = 9047 in lab.vmids_de_prueba()
        clon_existe = nuevo in lab.vmids_de_prueba()
        evidencia(
            "M4-10-borrar-plantilla",
            storage=storage,
            resultado=detalle[:300],
            plantilla_sigue=sigue,
            clon_existe=clon_existe,
        )
        assert sigue == plantilla_protegida
        assert clon_existe
        if not plantilla_protegida:
            # El clon no queda roto: arranca (disco vacío, sin SO; basta con que Proxmox lo encienda).
            lab.ssh(f"sudo qm start {nuevo} && sudo qm stop {nuevo} --skiplock 1", timeout=180)
    finally:
        limpiar_vms([9047, 9051])


# =========================================================================================
# LAB-M4-11  Rollback
# =========================================================================================


def test_lab_m4_11_rollback_borra_las_mvs_y_deja_plantilla_iso_e_imagen(
    sesion14, api14, imagen_cirros, iso_alpine, plantilla, vmids
):
    """RF-O30, CA-O20.8, CA-O25.2: ``DELETE`` con ``destroy-unreferenced-disks=0`` de un clon
    enlazado, uno completo, una MV de importación y una de ISO; la plantilla, la ISO y la imagen
    quedan intactas y los archivos subidos no se pueden borrar con el rol."""
    enlazado, completo, importada, con_iso = vmids(9051), vmids(9052), vmids(9053), vmids(9054)
    clonar_ok(api14, plantilla, enlazado)
    clonar_ok(api14, plantilla, completo, full=1, storage=LOCAL, format="qcow2")
    crear_con_ok(api14, parametros(sesion14, cfg_import(importada, imagen_cirros)))
    crear_con_ok(
        api14, parametros(sesion14, cfg_iso(con_iso, iso_alpine, firmware=Firmware.SEABIOS))
    )
    plantilla_antes = api14.config(plantilla)
    for v in (enlazado, completo, importada, con_iso):
        upid = sesion14.cliente.eliminar_vm(NODO, v)
        estado, log, _ = api14.tarea(upid)
        assert estado == "OK", (v, estado, log[-2:])
    quedan = set(lab.vmids_de_prueba())
    sueltos = lab.ssh(f"sudo pvesm list {STORAGE}; sudo pvesm list {LOCAL}")
    evidencia(
        "M4-11-rollback",
        quedan=sorted(quedan),
        volumenes_de_las_borradas=[
            ln for ln in sueltos.splitlines() if re.search(r"\b905[1-4]\b", ln)
        ],
    )
    assert quedan == {plantilla}
    assert not [ln for ln in sueltos.splitlines() if re.search(r"vm-905[1-4]-", ln)]
    assert api14.config(plantilla) == plantilla_antes
    assert "base-9050-disk-0" in sueltos
    assert {iso_alpine, imagen_cirros} <= set(archivos_lab())
    # los archivos subidos siguen y el rol NO puede borrarlos
    for volid in (iso_alpine, imagen_cirros):
        r = api14.delete(f"/nodes/{NODO}/storage/{LOCAL}/content/{volid}")
        detalle = mensaje(r)
        if r.status_code == 200:
            estado, log, _ = (
                api14.tarea(r.json()["data"])
                if isinstance(r.json().get("data"), str) and r.json()["data"].startswith("UPID")
                else ("sin tarea", [], 0)
            )
            detalle = f"borrado {estado}"
        evidencia("M4-11-borrar-archivo-con-el-rol", volid=volid, resultado=detalle[:160])
    assert {iso_alpine, imagen_cirros} <= set(archivos_lab()), (
        "el rol de 14 pudo borrar archivos subidos"
    )


# =========================================================================================
# LAB-M4-12  Lote por filas mixto (CSV, tres orígenes)
# =========================================================================================


def _lote_mixto(sesion: Any, tmp: Path) -> tuple[Any, Any]:
    from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
    from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv
    from proxlaunch.nucleo.lote.filas import definicion_por_filas
    from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
    from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO

    ruta = tmp / "mixto.csv"
    ruta.write_bytes(
        (
            "nombre;cpu;memoria;disco;almacenamiento;red;nodo;vmid;origen;fuente;so;modo_clon\r\n"
            f"plc-m4-iso;1;512 MiB;1;{STORAGE};vmbr0;;9040;iso;proxlaunch-lab-alpine.iso;linux;\r\n"
            f"plc-m4-imp;1;256 MiB;2;{STORAGE};vmbr0;;9041;importar;proxlaunch-lab-cirros.qcow2;;\r\n"
            f"plc-m4-clon;2;192 MiB;2;;;;9042;clonar;plc-m4-plantilla;;auto\r\n"
        ).encode()
    )
    tabla = leer_archivo_csv(ruta)
    inv = descubrir(sesion)
    perfil = {p.id: p for p in perfiles_fabrica()}[ID_PREDETERMINADO]
    resultado = interpretar(
        tabla, perfil_base=perfil, perfiles=perfiles_fabrica(), inv=inv, nodo_referencia=NODO
    )
    errores = [(f.numero, f.problemas) for f in resultado.filas if f.estado.value == "con_error"]
    assert not errores, errores
    base = resultado.filas[0].cfg
    assert base is not None
    definicion = definicion_por_filas(
        filas_lote(resultado, resultado.numeros_validos), plantilla_base=base, vmid_inicial=9040
    )
    return definicion, inv


def test_lab_m4_12_lote_mixto_simulacion_creacion_config_y_rollback(
    sesion14, cred14, plantilla, imagen_cirros, iso_alpine, vmids, tmp_path
):
    """RF-O28..O30: CSV con ISO, importación y clon: la simulación solo emite GET, la creación envía
    un POST por MV, cada fila tiene su ``config`` y el rollback deja intactos plantilla y archivos."""
    from proxlaunch.nucleo.lote.modelos import EstadoMV, EstadoRollback
    from proxlaunch.nucleo.lote.simulacion import simular

    from .test_lab_mvp3 import _deshacer, _ejecutar, _lineas_acceso, _metodos_nuevos, _planificar

    vmids(9040, 9041, 9042)
    definicion, inv = _lote_mixto(sesion14, tmp_path)
    inicio = _lineas_acceso()
    sim = simular(sesion14, definicion, inv, reloj=RelojReal())
    assert not sim.plan.bloqueado, sim.plan.problemas
    metodos = _metodos_nuevos(inicio, usuario=cred14.token_id, minimo=3)
    evidencia(
        "M4-12-simulacion",
        metodos=sorted({m.split()[0] for m in metodos}),
        n=len(metodos),
        peticiones={
            v: [(p.accion.value, sorted(p.parametros)) for p in ps]
            for v, ps in sim.peticiones_detalle.items()
        },
    )
    assert {m.split()[0] for m in metodos} <= {"GET"}
    assert set(sim.peticiones_detalle) == {9040, 9041, 9042}
    assert not ({9040, 9041, 9042} & set(lab.vmids_de_prueba()))  # la simulación no creó nada

    plan, inv = _planificar(sesion14, definicion)
    assert not plan.bloqueado, plan.problemas
    inicio = _lineas_acceso()
    libro = _ejecutar(sesion14, plan, inv)
    estados = {e.elemento.vmid: e.estado for e in libro.instantanea()}
    assert set(estados.values()) <= {EstadoMV.OK, EstadoMV.CON_AVISOS}, libro.instantanea()
    metodos = _metodos_nuevos(inicio, usuario=cred14.token_id, minimo=6)
    posts = [m for m in metodos if m.startswith("POST")]
    puts = [m for m in metodos if m.startswith("PUT")]
    evidencia(
        "M4-12-ejecucion", estados={k: str(v) for k, v in estados.items()}, posts=posts, puts=puts
    )
    assert len([m for m in posts if m.endswith("/qemu")]) == 2  # iso + importación
    assert len([m for m in posts if m.endswith("/clone")]) == 1
    etiquetas = {"proxlaunch", f"lote-{plan.id_lote}"}

    iso, imp, clon = (sesion14.cliente.config_vm(NODO, v) for v in (9040, 9041, 9042))
    assert iso["ide2"].startswith(iso_alpine) and (int(iso["cores"]), int(iso["memory"])) == (
        1,
        512,
    )
    assert "size=2G" in imp["scsi0"] and "ide2" not in imp
    assert (int(clon["cores"]), int(clon["memory"])) == (2, 192) and "size=2G" in clon["scsi0"]
    for conf in (iso, imp, clon):
        assert set(str(conf["tags"]).replace(",", ";").split(";")) >= etiquetas, conf["tags"]
    mac = {mac_de(c) for c in (iso, imp, clon)}
    assert len(mac) == 3

    resultados = _deshacer(sesion14, libro)
    evidencia("M4-12-rollback", estados=[str(r.estado) for r in resultados])
    assert {r.estado for r in resultados} == {EstadoRollback.ELIMINADA} and len(resultados) == 3
    assert set(lab.vmids_de_prueba()) == {plantilla}
    assert {iso_alpine, imagen_cirros} <= set(archivos_lab())


def test_lab_m4_12_inv_l1_un_clon_cuya_respuesta_se_pierde_no_se_reenvia(
    sesion14, plantilla, vmids, tmp_path
):
    """INV-L1/INV-O3: el POST ``clone`` llega al servidor pero se pierde la respuesta (fallo
    inyectado): el motor NO lo reenvía (una sola llamada) y existe a lo sumo una MV con ese VMID."""
    from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
    from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv
    from proxlaunch.nucleo.errores import CodigoError
    from proxlaunch.nucleo.lote.filas import definicion_por_filas
    from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
    from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO

    from .test_lab_mvp3 import _ejecutar, _planificar

    vmids(9042)
    ruta = tmp_path / "clon.csv"
    ruta.write_bytes(
        b"nombre;cpu;memoria;disco;vmid;origen;fuente;modo_clon\r\nplc-m4-clon;1;128 MiB;1;9042;clonar;plc-m4-plantilla;auto\r\n"
    )
    inv = descubrir(sesion14)
    perfil = {p.id: p for p in perfiles_fabrica()}[ID_PREDETERMINADO]
    res = interpretar(
        leer_archivo_csv(ruta),
        perfil_base=perfil,
        perfiles=perfiles_fabrica(),
        inv=inv,
        nodo_referencia=NODO,
    )
    base = res.filas[0].cfg
    assert base is not None
    definicion = definicion_por_filas(
        filas_lote(res, res.numeros_validos), plantilla_base=base, vmid_inicial=9042
    )
    plan, inv = _planificar(sesion14, definicion)
    assert not plan.bloqueado, plan.problemas
    llamadas: list[str] = []
    original = sesion14.cliente.clonar_vm

    def con_fallo(nodo: str, vmid: int, params: dict[str, str]) -> str:
        llamadas.append(params["newid"])
        original(nodo, vmid, params)  # el POST sale y la respuesta se pierde
        raise ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "inyectado por la prueba")

    with mock.patch.object(sesion14.cliente, "clonar_vm", con_fallo):
        libro = _ejecutar(sesion14, plan, inv, maximo_s=120)
    time.sleep(3)
    existentes = [v for v in lab.vmids_de_prueba() if v == 9042]
    evidencia(
        "M4-12-inv-l1",
        llamadas=llamadas,
        estado=[str(e.estado) for e in libro.instantanea()],
        existentes=existentes,
    )
    assert llamadas == ["9042"], llamadas  # exactamente un envío
    assert len(existentes) <= 1


# =========================================================================================
# LAB-M4-13  Capacidades frente a lo observado
# =========================================================================================


def _capacidades_con_catalogo(sesion: Any) -> Any:
    from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo
    from proxlaunch.nucleo.servicios.catalogo import con_catalogo

    inv = descubrir(sesion)
    nec = NecesidadesCatalogo(
        contenidos=frozenset({Contenido.ISO, Contenido.IMPORT}),
        plantillas=frozenset({"plc-m4-plantilla"}),
        formatos=True,
    )
    catalogo = ServicioCatalogo(sesion, RelojReal()).leer_para(inv, nec, [NODO])
    inv = con_catalogo(inv, catalogo)
    return calcular_capacidades(sesion.capacidades, inv, NODO)


def _sonda(cred: Cred, plantilla: int, url: str) -> dict[Via, int]:
    """Estado HTTP de una petición representativa por vía (no destructiva; limpia lo que crea)."""
    api = Api(cred)
    estados: dict[Via, int] = {}
    for via, contenido, nombre in (
        (Via.SUBIR_ISO, "iso", "proxlaunch-lab-cap.iso"),
        (Via.SUBIR_IMAGEN, "import", "proxlaunch-lab-cap.qcow2"),
    ):
        estados[via] = _subida_cruda(api, nombre, b"x" * 512, contenido).status_code
    estados[Via.DESCARGAR_URL] = api.get(f"/nodes/{NODO}/query-url-metadata", url=url).status_code
    estados[Via.CLONAR] = clonar(api, plantilla, 9055).status_code
    estados[Via.ORDEN_ARRANQUE] = api.crear_vm(
        9056, boot="order=net0", net0="virtio,bridge=vmbr0"
    ).status_code
    time.sleep(3)
    limpiar_vms([9055, 9056])
    borrar_archivos_lab()
    return estados


@pytest.mark.parametrize(
    ("etiqueta", "quien"),
    [
        ("10", "rol de 10"),
        ("14", "rol de 14"),
        ("Adm", "administrador"),
        ("SinAudit", "rol de 14 sin Sys.Audit"),
    ],
)
def test_lab_m4_13_capacidades_coinciden_con_lo_observado(
    etiqueta, quien, entorno_m4, plantilla, servidor_http, con_import
):
    """RF-O02, RF-O24: ``/version`` y ``/access/permissions`` con cada identidad; la disponibilidad
    de cada vía que calcula ``CapacidadesOrigen`` coincide con lo que el servidor acepta (SI) o
    rechaza con 403 (NO)."""
    if etiqueta == "Adm":
        contexto = usuario_administrador()
    elif etiqueta == "10":
        contexto = usuario_con(PRIVS10, "R10")
    elif etiqueta == "14":
        contexto = usuario_con(PRIVS14, "R14")
    else:
        contexto = usuario_con(tuple(p for p in PRIVS14 if p != "Sys.Audit"), "SinAudit")
    with contexto as cred:
        api = Api(cred)
        version = api.get("/version")
        permisos = api.datos(api.get("/access/permissions"))
        privilegios_raiz = sorted(permisos.get("/", {}))
        evidencia(
            "M4-13-crudo",
            quien=quien,
            version_http=version.status_code,
            privilegios_en_raiz=len(privilegios_raiz),
        )
        try:
            sesion = abrir_sesion(entorno_m4, cred)
        except ErrorProxLaunch as e:
            evidencia("M4-13-sin-sesion", quien=quien, codigo=str(e.codigo))
            assert etiqueta == "SinAudit"
            return
        try:
            caps = _capacidades_con_catalogo(sesion)
            url = f"{servidor_http}/proxlaunch-lab-alpine.iso"
            sondas = _sonda(cred, plantilla, url)
            tabla = {v.value: (caps.estado(v).disponibilidad.value, sondas.get(v)) for v in Via}
            evidencia("M4-13-tabla", quien=quien, version=caps.version, vias=tabla)
            for via, http in sondas.items():
                prevista = caps.estado(via).disponibilidad
                aceptada = http != 403
                assert (prevista != Disponibilidad.NO) == aceptada, (
                    quien,
                    via.value,
                    prevista.value,
                    http,
                )
        finally:
            entorno_m4.servicio.cerrar_sesion(sesion)


# =========================================================================================
# LAB-M4-14  Cancelación y cortes
# =========================================================================================


class ProxyLab:
    """Proxy TCP 127.0.0.1:puerto → 127.0.0.1:8006 que puede cortar o frenar las subidas.

    Solo reenvía al laboratorio (el tráfico es TLS: no se parsea HTTP). ``cortar_tras``: bytes
    enviados al servidor tras los que cierra la conexión de golpe; ``bytes_por_s``: limita el ritmo.
    ``posts_subida`` cuenta las conexiones que enviaron más de 1 MiB (intentos de subida)."""

    def __init__(self, *, cortar_tras: int | None = None, bytes_por_s: int | None = None) -> None:
        self._cortar_tras = cortar_tras
        self._bytes_por_s = bytes_por_s
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(16)
        self.puerto: int = self._srv.getsockname()[1]
        self.posts_subida = 0
        self._cerrado = threading.Event()
        threading.Thread(target=self._aceptar, daemon=True).start()

    def _aceptar(self) -> None:
        while not self._cerrado.is_set():
            try:
                cli, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._atender, args=(cli,), daemon=True).start()

    def _atender(self, cli: socket.socket) -> None:
        try:
            up = socket.create_connection((lab.HOST, lab.PUERTO), timeout=30)
        except OSError:
            cli.close()
            return

        def cerrar() -> None:
            for sck in (cli, up):
                with contextlib.suppress(OSError):
                    sck.shutdown(socket.SHUT_RDWR)
                with contextlib.suppress(OSError):
                    sck.close()

        def bajada() -> None:
            try:
                while datos := up.recv(65536):
                    cli.sendall(datos)
            except OSError:
                pass
            finally:
                cerrar()

        threading.Thread(target=bajada, daemon=True).start()
        enviados = 0
        try:
            while datos := cli.recv(65536):
                enviados += len(datos)
                if self._cortar_tras is not None and enviados >= self._cortar_tras:
                    cerrar()
                    return
                if self._bytes_por_s and enviados > 256 * 1024:  # el tráfico es TLS: no se parsea
                    time.sleep(len(datos) / self._bytes_por_s)
                up.sendall(datos)
        except OSError:
            pass
        finally:
            if enviados > 1024**2:  # una conexión que subió más de 1 MiB = un intento de subida
                self.posts_subida += 1
            cerrar()

    def cerrar(self) -> None:
        self._cerrado.set()
        with contextlib.suppress(OSError):
            self._srv.close()


@contextlib.contextmanager
def proxy_lab(**kw: Any) -> Iterator[ProxyLab]:
    proxy = ProxyLab(**kw)
    try:
        yield proxy
    finally:
        proxy.cerrar()


def test_lab_m4_14_corte_de_red_durante_la_subida_sin_reintento(entorno_m4, cred14):
    """RNF-O03, CA-O09.7: la conexión muere a mitad de la subida: ``FALLIDA`` con error de red, un
    único POST (sin reintento automático) y el catálogo confirma que no quedó archivo."""
    antes = _estado_vartmp()
    with proxy_lab(cortar_tras=20 * 1024**2) as proxy:
        sesion = abrir_sesion(entorno_m4, cred14, proxy.puerto)
        try:
            t0 = time.monotonic()
            r = subir(sesion, ISO_LOCAL, Contenido.ISO, "proxlaunch-lab-corte.iso")
            dur = time.monotonic() - t0
        finally:
            entorno_m4.servicio.cerrar_sesion(sesion)
        posts = proxy.posts_subida
    time.sleep(3)
    restos = [f for f in _estado_vartmp() if f not in antes]
    evidencia(
        "M4-14-corte",
        estado=str(r.estado),
        codigo=str(r.error.codigo) if r.error else None,
        quedo_archivo=r.quedo_archivo,
        posts_de_subida=posts,
        duracion_s=round(dur, 2),
        archivos_en_catalogo=archivos_lab(),
        restos_vartmp=restos,
    )
    assert r.estado == EstadoTransferencia.FALLIDA and r.error is not None
    assert posts == 1, "hubo reintento automático"
    assert archivos_lab() == []
    assert restos == [], restos


def test_lab_m4_14_ctrl_c_a_un_proceso_que_sube(entorno_m4, cred14, tmp_path):
    """RNF-O12, CA-O12.x: ``SIGINT`` a un proceso que está subiendo (el manejador activa la
    cancelación, como la interfaz al cerrarse): ``CANCELADA`` en segundos, sin archivo ni temporales."""
    import os
    import signal
    import subprocess
    import sys

    guion = tmp_path / "hijo.py"
    guion.write_text(
        "import json, os, signal, sys, threading, time\n"
        "from pathlib import Path\n"
        f"sys.path[:0] = [{str(Path(__file__).resolve().parents[2] / 'src')!r}, {str(Path(__file__).resolve().parents[1])!r}]\n"
        "from integracion import test_lab_mvp4 as m\n"
        "from integracion import apoyo_lab as lab\n"
        "from proxlaunch.nucleo.modelos.catalogo import Contenido\n"
        "cancelado = threading.Event()\n"
        "signal.signal(signal.SIGINT, lambda *_: cancelado.set())\n"
        "entorno = lab.crear_entorno(Path(sys.argv[1]))\n"
        "cred = m.Cred('x', os.environ['PLC_TOKEN_ID'], os.environ['PLC_TOKEN_SECRETO'])\n"
        "sesion = m.abrir_sesion(entorno, cred, int(sys.argv[3]))\n"
        "def prog(p):\n"
        "    if p.estado.value == 'transfiriendo' and p.hechos_bytes > 0:\n"
        "        Path(sys.argv[2]).write_text(str(p.hechos_bytes))\n"
        "r = m.subir(sesion, m.ISO_LOCAL, Contenido.ISO, 'proxlaunch-lab-sigint.iso', cancelado=cancelado, al_progresar=prog)\n"
        "print(json.dumps({'estado': r.estado.value, 'quedo': r.quedo_archivo, 't': time.time()}))\n"
    )
    progreso = tmp_path / "progreso.txt"
    antes = _estado_vartmp()
    with proxy_lab(bytes_por_s=8 * 1024**2) as proxy:
        entorno_hijo = {
            **os.environ,
            "PLC_TOKEN_ID": cred14.token_id,
            "PLC_TOKEN_SECRETO": cred14.secreto,
            "PYTHONPATH": "",
        }
        hijo = subprocess.Popen(
            [
                sys.executable,
                "-I",
                str(guion),
                str(tmp_path / "hijo-estado"),
                str(progreso),
                str(proxy.puerto),
            ],
            env=entorno_hijo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(tmp_path),
        )
        try:
            fin = time.monotonic() + 90
            while time.monotonic() < fin and hijo.poll() is None:
                if (
                    progreso.exists()
                    and progreso.read_text().strip().isdigit()
                    and int(progreso.read_text()) > 8 * 1024**2
                ):
                    break
                time.sleep(0.1)
            assert hijo.poll() is None, (
                f"el hijo terminó antes de tiempo: {hijo.stderr.read()[-400:] if hijo.stderr else ''}"
            )
            enviado = int(progreso.read_text())
            t_senal = time.time()
            hijo.send_signal(signal.SIGINT)
            salida, errores = hijo.communicate(timeout=60)
        finally:
            if hijo.poll() is None:
                hijo.kill()
    resultado = json.loads(salida.strip().splitlines()[-1])
    time.sleep(3)
    restos = [f for f in _estado_vartmp() if f not in antes]
    evidencia(
        "M4-14-sigint",
        estado=resultado["estado"],
        quedo=resultado["quedo"],
        enviado_bytes=enviado,
        reaccion_s=round(resultado["t"] - t_senal, 2),
        archivos=archivos_lab(),
        restos_vartmp=restos,
    )
    assert resultado["estado"] == "cancelada", (salida, errores[-400:])
    assert resultado["t"] - t_senal < 5
    assert archivos_lab() == [] and restos == []


def test_lab_m4_14_ticket_caducado_simulado_no_se_reintenta(entorno_m4, tmp_path):
    """CA-O09.7: con sesión por contraseña/ticket, un ticket invalidado a mitad de camino da
    ``SESION_EXPIRADA`` (401) en la subida, sin reintento y sin archivo."""
    from proxlaunch.nucleo.modelos.conexion import CredencialContrasena, Ticket

    with usuario_con(PRIVS14, "Tkt") as cred, proxy_lab() as proxy:
        p = dataclasses.replace(
            lab.perfil(MetodoAuth.CONTRASENA, cred.userid.split("@")[0], realm="pve"),
            puerto=proxy.puerto,
        )
        lab.confiar_en_laboratorio(entorno_m4, p)
        sesion = entorno_m4.servicio.conectar(
            p, CredencialContrasena(cred.userid.split("@")[0], "pve", cred.contrasena)
        )
        try:
            inv = descubrir(sesion)
            auth = sesion.cliente._auth
            ticket = auth.ticket
            auth._ticket = Ticket(
                ticket="PVE:" + cred.userid + ":00000000::invalido",
                csrf=ticket.csrf,
                usuario=ticket.usuario,
                emitido_en=ticket.emitido_en,
            )
            r = subir(sesion, ISO_LOCAL, Contenido.ISO, "proxlaunch-lab-ticket.iso", inv=inv)
        finally:
            entorno_m4.servicio.cerrar_sesion(sesion)
        posts = proxy.posts_subida
    evidencia(
        "M4-14-ticket",
        estado=str(r.estado),
        codigo=str(r.error.codigo) if r.error else None,
        posts_de_subida=posts,
        archivos=archivos_lab(),
    )
    assert r.estado == EstadoTransferencia.FALLIDA and r.error is not None
    assert str(r.error.codigo) in ("sesion_expirada", "credenciales_invalidas")
    assert posts <= 1
    assert archivos_lab() == []


# =========================================================================================
# F7 (revisión QA y seguridad): guía de permisos acotada, QA-M4-07 (balloon/vcpus) y QA-M4-08
# =========================================================================================

POOL_F7 = "plantillas-proxlaunch"  # el nombre que sugiere la guía
ROL_CREADOR_F7 = "ProxLaunchCreadorF7"  # mismos privilegios que «ProxLaunchCreador» (la guía);
# el sufijo evita pisar el rol de 10 privilegios que usa la fixture de sesión ``plc``.
ROL_MAQUINAS_F7 = "ProxLaunchMaquinas"  # nombre exacto de la guía
USUARIO_F7 = "plcf7@pve"
VMID_PLANT_POOL = 9060  # plantilla DENTRO del pool
VMID_PLANT_FUERA = 9061  # plantilla fuera del pool
VMID_MV_FUERA = 9062  # MV normal fuera del pool
VMID_PLANT_BALLOON = 9065  # memory=4096, balloon=2048
VMID_PLANT_VCPUS = 9066  # cores=4, vcpus=4 (sin ``sockets`` en la config: valor por defecto)
VMID_PLANT_VCPUS_S = 9068  # sockets=1 explícito, cores=4, vcpus=4
VMID_PLANT_LOTE = 9067


def _crear_plantilla_root(vmid: int, nombre: str, extra: str = "") -> None:
    lab.ssh(
        f"sudo qm create {vmid} --name {nombre} --memory 128 --cores 1 --scsihw virtio-scsi-single "
        f"--scsi0 {STORAGE}:1 --net0 virtio,bridge=vmbr0 {extra} && sudo qm template {vmid}",
        timeout=180,
    )


def _esperar_plantillas(sesion: Any, vmids: set[int], max_s: float = 60.0) -> None:
    fin = time.monotonic() + max_s
    while time.monotonic() < fin and not vmids <= {
        p.vmid for p in sesion.cliente.plantillas_visibles()
    }:
        time.sleep(2)


def _limpiar_guia_f7() -> None:
    """Todo lo que crea la fixture de la guía, también si quedó a medias."""
    limpiar_vms()
    lab.borrar_usuario(USUARIO_F7)
    lab.ssh(f"sudo pveum pool delete {POOL_F7}", comprobar=False)
    for rol in (ROL_CREADOR_F7, ROL_MAQUINAS_F7):
        lab.borrar_rol(rol)


def aplicar_guia_acotada() -> Cred:
    """Reproduce, con ``pveum`` como root, los pasos de la guía de alcance acotado
    (``ayuda.permisos_acotados``): pool con la plantilla, rol completo en el pool, segundo rol sin
    VM.Clone en ``/vms``, storages, nodo, ``/sdn/zones/localnetwork`` y ``/`` sin propagar."""
    from proxlaunch.interfaz import ayuda as ay

    guia = "\n".join(ay.permisos_acotados())
    for ruta in (
        f"/pool/{POOL_F7}",
        "/vms",
        "/storage/<almacenamiento>",
        "/nodes/<nodo>",
        "/sdn/zones/localnetwork",
    ):
        if ruta.replace(POOL_F7, "plantillas-proxlaunch") not in guia:
            raise AssertionError(f"la guía ya no menciona {ruta}: hay que actualizar la prueba")
    _limpiar_guia_f7()
    lab.crear_rol(PRIVS14, ROL_CREADOR_F7)
    lab.crear_rol(tuple(ay.PRIVILEGIOS_ROL_MAQUINAS), ROL_MAQUINAS_F7)
    _crear_plantilla_root(VMID_PLANT_POOL, "plc-f7-tpl")
    _crear_plantilla_root(VMID_PLANT_FUERA, "plc-f7-fuera")
    lab.ssh(
        f"sudo qm create {VMID_MV_FUERA} --name plc-f7-mv --memory 128 --cores 1 "
        f"--net0 virtio,bridge=vmbr0 --scsi0 {STORAGE}:1 --scsihw virtio-scsi-single",
        timeout=120,
    )
    lab.ssh(
        f"sudo pveum pool add {POOL_F7} && sudo pveum pool modify {POOL_F7} --vms {VMID_PLANT_POOL}"
    )
    lab.ssh(f"sudo pveum user add {USUARIO_F7} --password '{lab.nuevo_secreto()}'")
    asignaciones = [
        (f"/pool/{POOL_F7}", ROL_CREADOR_F7, 1),
        ("/vms", ROL_MAQUINAS_F7, 1),
        (f"/storage/{LOCAL}", ROL_CREADOR_F7, 1),
        (f"/storage/{STORAGE}", ROL_CREADOR_F7, 1),
        (f"/nodes/{NODO}", ROL_CREADOR_F7, 1),
        ("/sdn/zones/localnetwork", ROL_CREADOR_F7, 1),
        ("/", ROL_CREADOR_F7, 0),  # SIN Propagar: solo Sys.Audit en la raíz
    ]
    for ruta, rol, propaga in asignaciones:
        lab.ssh(
            f"sudo pveum acl modify {ruta} --users {USUARIO_F7} --roles {rol} --propagate {propaga}"
        )
    completo = lab.crear_token(USUARIO_F7, "tk", privsep=0)
    token_id, secreto = completo.rsplit("=", 1)
    return Cred(USUARIO_F7, token_id, secreto)


@pytest.fixture(scope="module")
def cred_guia() -> Iterator[Cred]:
    try:
        yield aplicar_guia_acotada()
    finally:
        _limpiar_guia_f7()


@pytest.fixture(scope="module")
def sesion_guia(entorno_m4: lab.Entorno, cred_guia: Cred) -> Iterator[Any]:
    sesion = abrir_sesion(entorno_m4, cred_guia)
    _esperar_plantillas(sesion, {VMID_PLANT_POOL})
    yield sesion
    entorno_m4.servicio.cerrar_sesion(sesion)


def _capacidades_de(sesion: Any, plantillas: set[str]) -> Any:
    from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo
    from proxlaunch.nucleo.servicios.catalogo import con_catalogo

    inv = descubrir(sesion)
    nec = NecesidadesCatalogo(
        contenidos=frozenset({Contenido.ISO, Contenido.IMPORT}),
        plantillas=frozenset(plantillas),
        formatos=True,
    )
    inv = con_catalogo(inv, ServicioCatalogo(sesion, RelojReal()).leer_para(inv, nec, [NODO]))
    return calcular_capacidades(sesion.capacidades, inv, NODO), inv


_CABECERA_CSV = "nombre;cpu;memoria;disco;almacenamiento;red;nodo;vmid;origen;fuente;so;modo_clon"


def _definicion_csv(sesion: Any, tmp: Path, filas: list[str], vmid_inicial: int) -> tuple[Any, Any]:
    from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
    from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv
    from proxlaunch.nucleo.lote.filas import definicion_por_filas
    from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
    from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO

    ruta = tmp / f"f7-{vmid_inicial}.csv"
    ruta.write_bytes(("\r\n".join([_CABECERA_CSV, *filas]) + "\r\n").encode())
    inv = descubrir(sesion)
    perfil = {p.id: p for p in perfiles_fabrica()}[ID_PREDETERMINADO]
    resultado = interpretar(
        leer_archivo_csv(ruta),
        perfil_base=perfil,
        perfiles=perfiles_fabrica(),
        inv=inv,
        nodo_referencia=NODO,
    )
    errores = [(f.numero, f.problemas) for f in resultado.filas if f.estado.value == "con_error"]
    assert not errores, errores
    base = resultado.filas[0].cfg
    assert base is not None
    definicion = definicion_por_filas(
        filas_lote(resultado, resultado.numeros_validos),
        plantilla_base=base,
        vmid_inicial=vmid_inicial,
    )
    return definicion, inv


def _correr_lote(sesion: Any, definicion: Any) -> Any:
    from .test_lab_mvp3 import _ejecutar, _planificar

    plan, inv = _planificar(sesion, definicion)
    assert not plan.bloqueado, plan.problemas
    return _ejecutar(sesion, plan, inv)


# --- (a) La guía acotada funciona de verdad ---------------------------------------------------------


def test_lab_f7_a1_la_app_ve_clonar_y_el_resto_de_vias_con_los_permisos_de_la_guia(
    sesion_guia, cred_guia
):
    """SEG-M4-01: con el alcance acotado (pool + rol sin VM.Clone en /vms + storages + nodo + SDN +
    «/» sin propagar), ``/access/permissions`` y ``CapacidadesOrigen`` ofrecen «clonar» y las demás
    vías, y el catálogo ve la plantilla del pool."""
    caps, inv = _capacidades_de(sesion_guia, {"plc-f7-tpl"})
    api = Api(cred_guia)
    permisos = api.datos(api.get("/access/permissions"))
    rutas = sorted(permisos)
    tabla = {v.value: caps.estado(v).disponibilidad.value for v in Via}
    plantillas = {p.vmid: p.nombre for p in (inv.catalogo.plantillas or ())}
    evidencia(
        "F7-a1-capacidades",
        rutas_con_permisos=rutas,
        vm_clone_en={r: "VM.Clone" in p for r, p in permisos.items() if "VM.Clone" in p},
        plantillas_visibles=plantillas,
        vias=tabla,
    )
    # VM.Audit viene también del rol de /vms: el catálogo ve las dos plantillas (la guía dice que
    # VM.Audit «vale solo para esas plantillas», lo que no es exacto; ver hallazgo F7-a1).
    assert plantillas == {VMID_PLANT_POOL: "plc-f7-tpl", VMID_PLANT_FUERA: "plc-f7-fuera"}
    assert tiene_privilegio(permisos, f"/vms/{VMID_PLANT_POOL}", "VM.Clone")
    assert not tiene_privilegio(permisos, f"/vms/{VMID_PLANT_FUERA}", "VM.Clone")
    assert not tiene_privilegio(permisos, f"/vms/{VMID_MV_FUERA}", "VM.Clone")
    assert caps.disponible(Via.CLONAR), caps.estado(Via.CLONAR)
    for via in (Via.SUBIR_ISO, Via.DESCARGAR_URL, Via.ORDEN_ARRANQUE, Via.AMPLIAR_DISCO, Via.ISO):
        assert caps.disponible(via), (via.value, caps.estado(via))


def test_lab_f7_a2_el_clon_real_funciona_con_los_permisos_de_la_guia(
    sesion_guia, cred_guia, tmp_path, vmids
):
    """SEG-M4-01: clon enlazado real (con etiquetas por PUT y ajuste de memoria) con el token de
    alcance acotado, ejecutado por el motor de la app."""
    from proxlaunch.nucleo.lote.modelos import EstadoMV

    nuevo = vmids(9071)
    definicion, _ = _definicion_csv(
        sesion_guia,
        tmp_path,
        [f"plc-f7-guia;1;192 MiB;1;;;;{nuevo};clonar;plc-f7-tpl;;auto"],
        nuevo,
    )
    libro = _correr_lote(sesion_guia, definicion)
    estados = {e.elemento.vmid: e.estado for e in libro.instantanea()}
    conf = Api(cred_guia).config(nuevo)
    evidencia(
        "F7-a2-clon",
        estados={k: str(v) for k, v in estados.items()},
        memory=conf["memory"],
        tags=conf.get("tags"),
    )
    assert estados == {nuevo: EstadoMV.OK}, libro.instantanea()
    assert int(conf["memory"]) == 192 and "proxlaunch" in str(conf["tags"])


def test_lab_f7_a3_con_ese_token_no_se_puede_clonar_fuera_del_pool(cred_guia, vmids):
    """SEG-M4-01: VM.Clone solo vale para las plantillas del pool: plantilla ajena, MV normal ->
    403; la plantilla del pool -> 200 (control)."""
    api = Api(cred_guia)
    fuera_plantilla = clonar(api, VMID_PLANT_FUERA, vmids(9072))
    fuera_mv = clonar(api, VMID_MV_FUERA, vmids(9073))
    evidencia(
        "F7-a3-fuera-del-pool",
        plantilla_ajena=mensaje(fuera_plantilla),
        mv_normal=mensaje(fuera_mv),
    )
    assert fuera_plantilla.status_code == 403, mensaje(fuera_plantilla)
    assert fuera_mv.status_code == 403, mensaje(fuera_mv)
    dentro = clonar(api, VMID_PLANT_POOL, vmids(9074))
    assert dentro.status_code == 200, mensaje(dentro)
    assert api.tarea(dentro.json()["data"])[0] == "OK"


def test_lab_f7_a3b_la_app_bloquea_en_la_planificacion_la_plantilla_visible_pero_no_clonable(
    sesion_guia, tmp_path
):
    """SEG-M4-01 (hallazgo): la plantilla ajena al pool es visible (VM.Audit viene de /vms) pero no
    clonable. ``CapacidadesOrigen`` solo mira si ALGUNA plantilla es clonable, pero el plan del lote
    la bloquea con V-O17 (VM.Clone en /vms/<id>) ANTES de enviar nada."""
    from .test_lab_mvp3 import _planificar

    nuevo = 9086
    definicion, _ = _definicion_csv(
        sesion_guia,
        tmp_path,
        [f"plc-f7-ajeno;1;128 MiB;1;;;;{nuevo};clonar;plc-f7-fuera;;auto"],
        nuevo,
    )
    plan, _inv = _planificar(sesion_guia, definicion)
    reglas = [(p.regla, dict(p.params)) for p in plan.problemas]
    evidencia("F7-a3b-clon-ajeno-por-la-app", bloqueado=plan.bloqueado, problemas=reglas)
    assert plan.bloqueado
    assert any(
        r == "V-O17" and prm.get("privilegio") == "VM.Clone" and prm.get("ruta") == "/vms/9061"
        for r, prm in reglas
    )
    assert nuevo not in lab.vmids_de_prueba()


def test_lab_f7_a4_iso_subida_descarga_y_creacion_con_los_permisos_de_la_guia(
    sesion_guia, cred_guia, servidor_http, vmids
):
    """SEG-M4-01: con el alcance acotado funcionan subir un ISO, descargarlo por URL, listarlo y
    crear una MV con ISO + orden de arranque (VM.Config.Disk viene del rol sin VM.Clone en /vms)."""
    from proxlaunch.nucleo.lote.modelos import EstadoMV  # noqa: F401  (documenta el estado esperado)
    from proxlaunch.nucleo.servicios.creacion import Desenlace, Etapa, ServicioCreacion

    try:
        subida = subir(sesion_guia, ISO_LOCAL, Contenido.ISO, "proxlaunch-lab-f7-subido.iso")
        assert subida.estado == EstadoTransferencia.TERMINADA, (subida.estado, subida.error)
        bajada = descargar(
            sesion_guia,
            f"{servidor_http}/proxlaunch-lab-alpine.iso",
            "proxlaunch-lab-f7-bajado.iso",
            checksum=SHA256_ALPINE,
        )
        assert bajada.estado == EstadoTransferencia.TERMINADA, (bajada.estado, bajada.error)
        vmid = vmids(9075)
        cfg = cfg_iso(vmid, subida.volid, firmware=Firmware.SEABIOS, tipo_so=TipoSO.LINUX)
        inv = descubrir(sesion_guia)
        r = ServicioCreacion(sesion_guia, RelojReal(), intervalo_s=0.5).crear(
            cfg, inv, lambda _e: None, threading.Event()
        )
        conf = Api(cred_guia).config(vmid)
        evidencia(
            "F7-a4-iso",
            desenlace=str(r.desenlace),
            subido=subida.volid,
            bajado=bajada.volid,
            ide2=conf.get("ide2"),
            boot=conf.get("boot"),
        )
        assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), (r.desenlace, r.error)
        assert str(conf["ide2"]).startswith(subida.volid) and "ide2" in str(conf["boot"])
        assert Etapa.LISTO is not None
    finally:
        borrar_archivos_lab()


# --- (b) QA-M4-07: balloon y vcpus del clon ---------------------------------------------------------


@pytest.fixture
def plantillas_balloon_vcpus() -> Iterator[None]:
    _crear_plantilla_root(VMID_PLANT_BALLOON, "plc-f7-balloon", "--memory 4096 --balloon 2048")
    _crear_plantilla_root(VMID_PLANT_VCPUS, "plc-f7-vcpus", "--cores 4 --vcpus 4")
    _crear_plantilla_root(VMID_PLANT_VCPUS_S, "plc-f7-vcpus-s", "--sockets 1 --cores 4 --vcpus 4")
    try:
        yield
    finally:
        limpiar_vms()


def test_lab_f7_b1_sin_la_correccion_el_servidor_rechaza_el_balloon_y_los_vcpus_rompen_el_arranque(
    api14, plantillas_balloon_vcpus, vmids
):
    """QA-M4-07 (demostración con llamadas directas, sin la corrección de la app): el PUT de solo
    ``memory`` por debajo del ``balloon`` heredado da error; el de solo ``cores`` por debajo de
    ``vcpus`` se acepta pero la MV ya no arranca (``Invalid CPU topology``)."""
    mem = vmids(9076)
    clonar_ok(api14, VMID_PLANT_BALLOON, mem)
    r_mem = api14.put(f"/nodes/{NODO}/qemu/{mem}/config", memory=1024)
    cpu = vmids(9077)
    clonar_ok(api14, VMID_PLANT_VCPUS, cpu)
    r_cpu = api14.put(f"/nodes/{NODO}/qemu/{cpu}/config", cores=2)
    arranque = lab.ssh(f"sudo qm start {cpu} 2>&1; true", comprobar=False, timeout=120)
    lab.ssh(f"sudo qm stop {cpu} --skiplock 1", comprobar=False, timeout=60)
    evidencia(
        "F7-b1-sin-correccion",
        put_memory=mensaje(r_mem),
        put_cores=r_cpu.status_code,
        arranque=arranque.strip()[-160:],
    )
    assert r_mem.status_code != 200 and "balloon" in mensaje(r_mem).lower()
    assert r_cpu.status_code == 200 and "Invalid CPU topology" in arranque


def _clonar_con_app(sesion: Any, tmp: Path, filas: list[str], inicio: int) -> dict[int, Any]:
    definicion, _ = _definicion_csv(sesion, tmp, filas, inicio)
    libro = _correr_lote(sesion, definicion)
    return {e.elemento.vmid: e.estado for e in libro.instantanea()}


def _arranca(vmid: int) -> str:
    return lab.ssh(
        f"sudo qm start {vmid} 2>&1 && echo ARRANCO; sudo qm stop {vmid} --skiplock 1 "
        ">/dev/null 2>&1; true",
        comprobar=False,
        timeout=120,
    )


def test_lab_f7_b2_con_la_app_memoria_menor_que_el_balloon_queda_ok_con_balloon_ajustado(
    sesion14, plantillas_balloon_vcpus, tmp_path, vmids
):
    """QA-M4-07: clonar con memoria 1024 (< balloon 2048): la app envía ``balloon`` = 1024 en el
    mismo PUT; el resultado es OK (no PARCIAL)."""
    from proxlaunch.nucleo.lote.modelos import EstadoMV

    _esperar_plantillas(sesion14, {VMID_PLANT_BALLOON})
    a = vmids(9078)
    estados = _clonar_con_app(
        sesion14, tmp_path, [f"plc-f7-mem;1;1024 MiB;1;;;;{a};clonar;plc-f7-balloon;;auto"], a
    )
    conf = sesion14.cliente.config_vm(NODO, a)
    evidencia(
        "F7-b2-balloon",
        estados={k: str(v) for k, v in estados.items()},
        mem=(conf["memory"], conf.get("balloon")),
    )
    assert estados == {a: EstadoMV.OK}
    assert (int(conf["memory"]), int(conf["balloon"])) == (1024, 1024)


def test_lab_f7_b3_con_la_app_menos_nucleos_que_vcpus_ajusta_vcpus_y_la_mv_arranca(
    sesion14, plantillas_balloon_vcpus, tmp_path, vmids
):
    """QA-M4-07: plantilla con ``sockets`` explícito, cores=4 y vcpus=4; clon con 2 núcleos: la app
    envía ``vcpus`` = 2, el clon queda OK y arranca."""
    from proxlaunch.nucleo.lote.modelos import EstadoMV

    _esperar_plantillas(sesion14, {VMID_PLANT_VCPUS_S})
    b = vmids(9079)
    estados = _clonar_con_app(
        sesion14, tmp_path, [f"plc-f7-cpu;2;128 MiB;1;;;;{b};clonar;plc-f7-vcpus-s;;auto"], b
    )
    conf = sesion14.cliente.config_vm(NODO, b)
    arranque = _arranca(b)
    evidencia(
        "F7-b3-vcpus",
        estados={k: str(v) for k, v in estados.items()},
        cpu=(conf["cores"], conf.get("vcpus")),
        arranque=arranque.strip()[-40:],
    )
    assert estados == {b: EstadoMV.OK}
    assert (int(conf["cores"]), int(conf["vcpus"])) == (2, 2) and "ARRANCO" in arranque


def test_lab_f7_b4_defecto_vcpus_no_se_ajusta_si_la_plantilla_omite_sockets(
    sesion14, plantillas_balloon_vcpus, tmp_path, vmids
):
    """QA-M4-07, reproducción: misma prueba que la anterior pero con la plantilla 9066, cuya config
    no trae ``sockets`` (``qm config`` muestra ``cores: 4`` y ``vcpus: 4`` solamente)."""
    from proxlaunch.nucleo.lote.modelos import EstadoMV

    _esperar_plantillas(sesion14, {VMID_PLANT_VCPUS})
    c = vmids(9087)
    plantilla_conf = sesion14.cliente.config_vm(NODO, VMID_PLANT_VCPUS)
    assert "sockets" not in plantilla_conf and int(plantilla_conf["vcpus"]) == 4
    estados = _clonar_con_app(
        sesion14, tmp_path, [f"plc-f7-cpu2;2;128 MiB;1;;;;{c};clonar;plc-f7-vcpus;;auto"], c
    )
    conf = sesion14.cliente.config_vm(NODO, c)
    arranque = _arranca(c)
    evidencia(
        "F7-b4-defecto",
        estados={k: str(v) for k, v in estados.items()},
        cpu=(conf["cores"], conf.get("vcpus")),
        arranque=arranque.strip()[-70:],
    )
    assert estados == {c: EstadoMV.OK}
    assert int(conf["vcpus"]) == 2 and "ARRANCO" in arranque


# --- (c) QA-M4-08: nunca más de 3 qmclone simultáneos ------------------------------------------------


def test_lab_f7_c1_un_lote_de_seis_clones_enlazados_nunca_supera_tres_qmclone_a_la_vez(
    sesion14, api14, tmp_path, vmids
):
    """QA-M4-08: el tope de 3 clones enlazados simultáneos se cuenta en el nodo de la plantilla.
    Se mide con la lista de tareas activas ``qmclone`` (muestreo cada ~50 ms) y el lote termina OK."""
    from proxlaunch.nucleo.lote.modelos import EstadoMV

    _crear_plantilla_root(VMID_PLANT_LOTE, "plc-f7-lote")
    try:
        _esperar_plantillas(sesion14, {VMID_PLANT_LOTE})
        ids = list(range(9080, 9086))
        vmids(*ids)
        definicion, _ = _definicion_csv(
            sesion14,
            tmp_path,
            [f"plc-f7-l{i};1;128 MiB;1;;;;{v};clonar;plc-f7-lote;;auto" for i, v in enumerate(ids)],
            ids[0],
        )
        muestras: list[int] = []
        fin = threading.Event()

        def vigilar() -> None:
            while not fin.is_set():
                r = api14.get(f"/nodes/{NODO}/tasks", source="active", typefilter="qmclone")
                if r.status_code == 200:
                    muestras.append(
                        sum(1 for t in r.json()["data"] if str(t.get("type")) == "qmclone")
                    )
                time.sleep(0.05)

        hilo = threading.Thread(target=vigilar, daemon=True)
        hilo.start()
        t0 = time.monotonic()
        try:
            libro = _correr_lote(sesion14, definicion)
        finally:
            fin.set()
            hilo.join(timeout=10)
        total = time.monotonic() - t0
        estados = {e.elemento.vmid: e.estado for e in libro.instantanea()}
        evidencia(
            "F7-c1-concurrencia",
            clones=len(ids),
            muestras=len(muestras),
            maximo_qmclone_activos=max(muestras or [0]),
            segundos=round(total, 1),
            estados=sorted({str(s) for s in estados.values()}),
        )
        assert set(estados) == set(ids) and set(estados.values()) == {EstadoMV.OK}, estados
        assert muestras and max(muestras) <= 3, max(muestras or [0])
    finally:
        limpiar_vms()
