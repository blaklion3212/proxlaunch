"""Fase D (0.9.0) contra el laboratorio real: los criterios ``[LAB]`` de docs/requisitos/fase-d.md §14.2.

Solo con ``PROXLAUNCH_LAB=1`` y solo contra el laboratorio local (127.0.0.1:8006, nodo ``pve-lab``).
VMIDs 9085-9099 únicamente (9070-9084 son de otra batería en paralelo). Todo lo que se crea se
elimina al terminar, también si la prueba falla: MVs, imágenes subidas a ``lab-import``, mapeos,
``cpu-models.conf`` (se restaura como estaba), usuarios, roles y ACL de prueba.

Los pasos de administrador (mapeos, modelos de CPU, ACL, encender, consola) se hacen con ``lab.ssh``
como root del laboratorio. Lo que se prueba (descubrimiento, lectura de libvirt, creación, listado
y comprobación de mapeos, lectura de CPU, traducción de errores) lo hace el núcleo de ProxLaunch;
la API cruda con token solo se usa para ver la respuesta literal del servidor.

Las pruebas imprimen líneas ``EVIDENCIA[...]`` (visibles con ``-s``) con las medidas reales.
"""

# ruff: noqa: E501
# (cadenas largas de EVIDENCIA y de órdenes del laboratorio)
from __future__ import annotations

import contextlib
import json
import re
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import requests

from proxlaunch.nucleo.arquitectura.modelos import Arquitectura, FuenteArquitectura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import (
    AsignacionPCI,
    AsignacionUSB,
    HardwareCluster,
    TipoMapeo,
)
from proxlaunch.nucleo.libvirt.correspondencias import EstadoFila, proponer
from proxlaunch.nucleo.libvirt.lectura_xml import leer_xml
from proxlaunch.nucleo.libvirt.modelos import interpretar_dominio
from proxlaunch.nucleo.libvirt.validacion import validar_importacion_d
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.conexion import CredencialToken, MetodoAuth
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, ImagenDisco, RefVolumen, TipoSO
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, Firmware, InterfazRed, OrigenSO
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.servicios.descubrimiento import descubrir, descubrir_nodo_d
from proxlaunch.nucleo.transferencias.modelos import DestinoTransferencia, EstadoTransferencia
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion, ServicioTransferencias

from . import apoyo_lab as lab

pytestmark = [
    pytest.mark.integracion,
    pytest.mark.filterwarnings("ignore::urllib3.exceptions.InsecureRequestWarning"),
]

URL = f"https://{lab.HOST}:{lab.PUERTO}/api2/json"
NODO = lab.NODO
STORAGE = "lab-lvmthin"
ALMACEN_IMPORT = "lab-import"
DISCOS = lab.DIR_LAB / "discos"
CIRROS_LOCAL = DISCOS / "proxlaunch-lab-cirros.qcow2"
BACKING_LOCAL = DISCOS / "proxlaunch-lab-backing.qcow2"
PREFIJO_IMAGEN = "proxlaunch-lab-d-"
IMG_SISTEMA = f"{PREFIJO_IMAGEN}sistema.qcow2"
IMG_DATOS = f"{PREFIJO_IMAGEN}datos.qcow2"
VMID_MIN_D, VMID_MAX_D = 9085, 9099
PRIVS_D = (*ROL_PROXLAUNCH, "VM.PowerMgmt")
# Mapeos y modelo de CPU de prueba (los únicos que estas pruebas crean y borran).
PCI_INVALIDO = "plc-pci-prueba"  # sin subsystem-id: check-node lo marca como inválido
PCI_VALIDO = "plc-pci-b"  # con subsystem-id: check-node sin errores
USB_PRUEBA = "plc-usb-prueba"
CPU_NOMBRE = "plc-prueba"
CPU_TIPO = f"custom-{CPU_NOMBRE}"
FICHERO_CPU = "/etc/pve/virtual-guest/cpu-models.conf"

XML_UBUNTU_UEFI = f"""<domain type='kvm'>
  <name>ubuntu-uefi-lab</name>
  <memory unit='MiB'>256</memory>
  <vcpu placement='static'>1</vcpu>
  <metadata>
    <libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">
      <libosinfo:os id="http://ubuntu.com/ubuntu/24.04"/>
    </libosinfo:libosinfo>
  </metadata>
  <os>
    <type arch='x86_64' machine='pc-q35-8.2'>hvm</type>
    <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE_4M.fd</loader>
    <nvram template='/usr/share/OVMF/OVMF_VARS_4M.fd'>/var/lib/libvirt/qemu/nvram/ubuntu_VARS.fd</nvram>
  </os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/{IMG_SISTEMA}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/{IMG_DATOS}'/>
      <target dev='vdb' bus='virtio'/>
    </disk>
    <interface type='bridge'>
      <mac address='52:54:00:ab:cd:ef'/>
      <source bridge='vmbr0'/>
      <model type='virtio'/>
    </interface>
  </devices>
</domain>
"""


def evidencia(clave: str, **datos: Any) -> None:
    detalle = " ".join(f"{k}={v!r}" for k, v in datos.items())
    print(f"EVIDENCIA[{clave}] {detalle}")


# --- Apoyo: administración (root del laboratorio) ---------------------------------------------


@dataclass(frozen=True)
class Cred:
    userid: str
    token_id: str
    secreto: str = field(repr=False)


@contextlib.contextmanager
def usuario_con(
    privs: tuple[str, ...],
    etiqueta: str,
    *,
    ruta: str = "/",
    extra: tuple[tuple[str, str], ...] = (),
) -> Iterator[Cred]:
    """Rol propio (``PlcD<etiqueta>``) en ``ruta`` + ACL ``extra`` ``(ruta, rol)`` + token.

    Nombres distintos de los de las demás baterías (``plc@pve``, ``plcm4*``) para no pisarlas.
    """
    rol = f"PlcD{etiqueta}"
    userid = f"plcd{etiqueta.lower()}@pve"
    lab.borrar_usuario(userid)
    lab.borrar_rol(rol)
    lab.crear_rol(privs, rol)
    try:
        lab.crear_usuario(userid, lab.nuevo_secreto(), rol, ruta)
        for ruta_extra, rol_extra in extra:
            lab.ssh(
                f"sudo pveum acl modify {ruta_extra} --users {userid} --roles {rol_extra} --propagate 1"
            )
        completo = lab.crear_token(userid, "tk", privsep=0)
        token_id, secreto = completo.rsplit("=", 1)
        yield Cred(userid, token_id, secreto)
    finally:
        lab.borrar_usuario(userid)
        lab.borrar_rol(rol)


def crear_mapeo_pci(ident: str, *, con_subsistema: bool) -> None:
    sub = ",subsystem-id=1af4:1100" if con_subsistema else ""
    lab.ssh(
        f"sudo pvesh create /cluster/mapping/pci --id {ident} "
        f"--map node={NODO},path=0000:00:1f.0,id=8086:2918{sub}"
    )


def crear_mapeo_usb(ident: str) -> None:
    lab.ssh(f"sudo pvesh create /cluster/mapping/usb --id {ident} --map node={NODO},id=0627:0001")


def borrar_mapeos_prueba() -> None:
    for tipo, ident in (("pci", PCI_INVALIDO), ("pci", PCI_VALIDO), ("usb", USB_PRUEBA)):
        lab.ssh(f"sudo pvesh delete /cluster/mapping/{tipo}/{ident}", comprobar=False)


def mapeos_de_prueba_restantes() -> list[str]:
    restantes: list[str] = []
    for tipo in ("pci", "usb"):
        datos = json.loads(lab.ssh(f"sudo pvesh get /cluster/mapping/{tipo} --output-format json"))
        restantes += [f"{tipo}/{m['id']}" for m in datos if str(m["id"]).startswith("plc-")]
    return restantes


def limpiar_vms_d() -> None:
    """Destruye solo las MVs 9085-9099 (las de otras baterías no se tocan)."""
    for vmid in lab.vmids_de_prueba():
        if VMID_MIN_D <= vmid <= VMID_MAX_D:
            lab.ssh(
                f"sudo qm unlock {vmid}; sudo qm set {vmid} --protection 0; "
                f"sudo qm stop {vmid} --skiplock 1; sudo qm destroy {vmid} --purge 1 "
                "--skiplock 1 --destroy-unreferenced-disks 1; true",
                comprobar=False,
                timeout=300,
            )
    # Volúmenes sueltos del rango propio (p. ej. de una creación a medias).
    lab.ssh(
        f"for vol in $(sudo pvesm list {STORAGE} | awk 'NR>1 && NF==5 && $NF>={VMID_MIN_D} && "
        f"$NF<={VMID_MAX_D}{{print $1}}'); do sudo pvesm free $vol; done; true",
        comprobar=False,
    )


def borrar_imagenes_d() -> None:
    lab.ssh(
        f"for v in $(sudo pvesm list {ALMACEN_IMPORT} | awk 'NR>1 && /{PREFIJO_IMAGEN}/{{print $1}}'); "
        "do sudo pvesm free $v; done; "
        f"sudo rm -f /var/lib/lab-import/import/{PREFIJO_IMAGEN}*; true",
        comprobar=False,
        timeout=300,
    )


def imagenes_d() -> list[str]:
    salida = lab.ssh(
        f"sudo pvesm list {ALMACEN_IMPORT} | awk 'NR>1 && /{PREFIJO_IMAGEN}/{{print $1}}'"
    )
    return [ln for ln in salida.split() if ln]


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

    def subir(self, almacen: str, nombre: str, ruta: Path) -> requests.Response:
        return requests.post(
            f"{URL}/nodes/{NODO}/storage/{almacen}/upload",
            headers=self._cab,
            data={"content": "import"},
            files={"filename": (nombre, ruta.read_bytes(), "application/octet-stream")},
            verify=False,
            timeout=180,
        )

    def datos(self, resp: requests.Response) -> Any:
        assert resp.status_code == 200, f"{resp.status_code} {resp.text[:300]}"
        return resp.json()["data"]

    def tarea(self, upid: str, max_s: float = 600.0) -> tuple[str, list[str]]:
        """Espera una tarea; devuelve ``(exitstatus, líneas del log)``."""
        t0 = time.monotonic()
        ruta = f"/nodes/{NODO}/tasks/{upid}"
        while time.monotonic() - t0 < max_s:
            est = self.datos(self.get(f"{ruta}/status"))
            if est["status"] == "stopped":
                log = self.datos(self.get(f"{ruta}/log", limit=500))
                return str(est.get("exitstatus")), [str(e.get("t")) for e in log]
            time.sleep(0.5)
        raise AssertionError(f"tarea {upid} no terminó en {max_s} s")

    def crear_vm(self, vmid: int, **extra: Any) -> requests.Response:
        base: dict[str, Any] = {"vmid": vmid, "name": f"plc-d-{vmid}", "memory": 128, "cores": 1}
        base.update(extra)
        return self.post(f"/nodes/{NODO}/qemu", **base)

    def config(self, vmid: int) -> dict[str, Any]:
        return self.datos(self.get(f"/nodes/{NODO}/qemu/{vmid}/config"))


def mensaje(resp: requests.Response) -> str:
    """Texto breve de un error de la API (sin secretos)."""
    try:
        cuerpo = resp.json()
    except ValueError:
        return f"{resp.status_code} {resp.text[:200]}"
    return f"{resp.status_code} {cuerpo.get('message', '')[:300]} {cuerpo.get('errors', '')}"


# --- Apoyo: núcleo de ProxLaunch ----------------------------------------------------------------


def abrir_sesion(entorno: lab.Entorno, cred: Cred) -> Any:
    p = lab.perfil(MetodoAuth.TOKEN, cred.token_id)
    lab.confiar_en_laboratorio(entorno, p)
    return entorno.servicio.conectar(p, CredencialToken(cred.token_id, cred.secreto))


def subir_a_import(sesion: Any, ruta: Path, nombre: str) -> Any:
    inv = descubrir(sesion)
    servicio = ServicioTransferencias(
        sesion,
        RelojReal(),
        RegistroSesion(),
        intervalo_s=0.5,
        hora_local=lambda: time.strftime("%H:%M:%S"),
    )
    return servicio.subir(
        ruta,
        DestinoTransferencia(NODO, ALMACEN_IMPORT, Contenido.IMPORT, nombre),
        inv,
        al_progresar=lambda _p: None,
        cancelado=threading.Event(),
        acepta_aviso_raiz=True,
    )


def crear_con_app(sesion: Any, cfg: ConfiguracionVM) -> Any:
    inv = descubrir(sesion)
    return ServicioCreacion(sesion, RelojReal(), intervalo_s=0.5).crear(
        cfg, inv, lambda _e: None, threading.Event()
    )


def cfg_vacia(vmid: int, **extra: Any) -> ConfiguracionVM:
    base: dict[str, Any] = {
        "vmid": vmid,
        "nombre": f"plc-d-{vmid}",
        "nodo": NODO,
        "cores": 1,
        "memoria_mib": 128,
        "discos": [Disco(storage=STORAGE, tamano_gib=1)],
        "redes": [InterfazRed(bridge="vmbr0")],
    }
    base.update(extra)
    return ConfiguracionVM(**base)


def consola(vmid: int, segundos: int) -> str:
    """Salida del puerto serie de la MV durante ``segundos`` (necesita ``serial0: socket``)."""
    sock = f"/var/run/qemu-server/{vmid}.serial0"
    return lab.ssh(
        f"for i in $(seq 40); do [ -S {sock} ] && break; sleep 0.5; done; "
        f"sudo timeout {segundos} socat -u UNIX-CONNECT:{sock} - 2>/dev/null | "
        "tr -c '[:print:]\\n' ' ' | tail -c 1500; true",
        comprobar=False,
        timeout=segundos + 90,
    )


# --- Fixtures ------------------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _guarda_laboratorio() -> Iterator[None]:
    """Sustituye a la del conftest en este módulo: comprueba el destino pero NO destruye las MVs de
    otras baterías (9000-9084) al terminar; la limpieza propia está en ``_limpieza_d``."""
    lab.comprobar_destino(lab.HOST, lab.PUERTO, lab.NODO)
    nombre = lab.ssh("hostname").strip()
    if nombre != lab.NODO:
        pytest.exit(f"el nodo del laboratorio es {nombre!r}, no {lab.NODO!r}: se aborta", 2)
    yield


@pytest.fixture(scope="module", autouse=True)
def _limpieza_d() -> Iterator[None]:
    """Limpieza total de lo propio al empezar y al terminar; ``cpu-models.conf`` se restaura."""
    previo = lab.ssh(f"sudo cat {FICHERO_CPU} 2>/dev/null; true", comprobar=False)
    existia = lab.ssh(f"sudo test -f {FICHERO_CPU} && echo si || echo no").strip() == "si"
    assert not existia or CPU_NOMBRE not in previo, (
        "cpu-models.conf con restos de una prueba previa"
    )
    limpiar_vms_d()
    borrar_mapeos_prueba()
    borrar_imagenes_d()
    try:
        yield
    finally:
        try:
            limpiar_vms_d()
            borrar_mapeos_prueba()
            borrar_imagenes_d()
            if existia:
                lab.ssh(f"sudo tee {FICHERO_CPU} >/dev/null <<'FIN'\n{previo}\nFIN")
            else:
                lab.ssh(f"sudo rm -f {FICHERO_CPU}", comprobar=False)
            for rol in ("PlcDSinAudit", "PlcDCompleto", "PlcDUso", "PlcDSinUso"):
                lab.borrar_rol(rol)
        finally:
            lab.ssh("sudo pveum user list --output-format json >/dev/null", comprobar=False)


@pytest.fixture(scope="module")
def entorno_d(tmp_path_factory: pytest.TempPathFactory) -> lab.Entorno:
    return lab.crear_entorno(tmp_path_factory.mktemp("fase_d"))


@pytest.fixture(scope="module")
def cred_completo() -> Iterator[Cred]:
    """Rol de 14 privilegios + ``VM.PowerMgmt`` en ``/`` (sin ningún permiso de mapeos)."""
    with usuario_con(PRIVS_D, "Completo") as c:
        yield c


@pytest.fixture(scope="module")
def sesion(entorno_d: lab.Entorno, cred_completo: Cred) -> Iterator[Any]:
    s = abrir_sesion(entorno_d, cred_completo)
    yield s
    entorno_d.servicio.cerrar_sesion(s)


@pytest.fixture(scope="module")
def api(cred_completo: Cred) -> Api:
    return Api(cred_completo)


@pytest.fixture
def vmids() -> Iterator[Callable[[int], int]]:
    """Registra VMIDs 9085-9099; se destruyen al terminar la prueba."""
    creados: list[int] = []

    def registrar(vmid: int) -> int:
        assert VMID_MIN_D <= vmid <= VMID_MAX_D, "VMID fuera del rango propio de la fase D"
        creados.append(vmid)
        return vmid

    yield registrar
    for vmid in creados:
        lab.destruir_vm(vmid)


# =========================================================================================
# CA-D2.5.10  Arquitectura del nodo (host-arch y current-kernel)
# =========================================================================================


def test_d2_5_10_host_arch_y_kernel_con_el_rol(api: Api) -> None:
    """9.2: ``current-kernel.machine`` = ``x86_64`` en el estado. ``host-arch`` NO se publica en un
    nodo x86 (pvestatd solo lo guarda en los no-x86; el esquema declara ``x86_64`` por defecto)."""
    recursos = api.datos(api.get("/cluster/resources", type="node"))
    nodo = next(r for r in recursos if r.get("node") == NODO)
    estado = api.datos(api.get(f"/nodes/{NODO}/status"))
    evidencia(
        "D2.5.10-con-sys-audit",
        host_arch_presente="host-arch" in nodo,
        host_arch=nodo.get("host-arch"),
        kernel=estado.get("current-kernel"),
        claves_recurso=sorted(nodo),
    )
    # Hecho del laboratorio: ausente (la investigación decía «x86_64»). Se acepta ausente o x86_64.
    assert nodo.get("host-arch") in (None, "x86_64")
    assert estado["current-kernel"]["machine"] == "x86_64"


def test_d2_5_10_host_arch_sin_sys_audit(entorno_d: lab.Entorno) -> None:
    """Sin ``Sys.Audit`` (solo ``VM.Audit``): qué ve el rol y qué concluye la app."""
    with usuario_con(("VM.Audit",), "SinAudit") as c:
        a = Api(c)
        recursos = a.datos(a.get("/cluster/resources", type="node"))
        nodo = next((r for r in recursos if r.get("node") == NODO), None)
        estado = a.get(f"/nodes/{NODO}/status")
        evidencia(
            "D2.5.10-sin-sys-audit",
            nodos_visibles=[r.get("node") for r in recursos],
            claves_nodo=None if nodo is None else sorted(nodo),
            host_arch=None if nodo is None else nodo.get("host-arch"),
            estado_http=estado.status_code,
            estado_msg=mensaje(estado) if estado.status_code != 200 else "ok",
        )
        assert nodo is None or nodo.get("host-arch") in (None, "x86_64")
        assert estado.status_code == 403  # sin Sys.Audit no hay current-kernel
        # La app: sin kernel (403) pero con la fila del nodo en línea sin host-arch, es x86
        # (RECURSOS_AUSENTE, LAB-D-1); si la fila no estuviera, quedaría DESCONOCIDA (V-D04).
        try:
            s = abrir_sesion(entorno_d, c)
        except ErrorProxLaunch as e:
            evidencia("D2.5.10-sin-sys-audit-app", conexion=f"error {e.codigo}")
            return
        try:
            info = descubrir(s).arquitecturas.get(NODO)
        finally:
            entorno_d.servicio.cerrar_sesion(s)
        evidencia(
            "D2.5.10-sin-sys-audit-app",
            arquitectura=None if info is None else str(info.arquitectura),
            fuente=None if info is None else str(info.fuente),
            motivo=None if info is None else info.motivo,
        )
        assert info is not None
        assert info.arquitectura in (Arquitectura.X86_64, Arquitectura.DESCONOCIDA)


def test_d2_5_10_la_app_detecta_x86_64(sesion: Any) -> None:
    """El descubrimiento de la app da ``X86_64`` en el nodo x86: como ``host-arch`` no viene, lo
    resuelve con ``current-kernel`` (fuente KERNEL), y con ``recursos`` vacío hace esa lectura."""
    inv = descubrir(sesion)
    info = inv.arquitecturas[NODO]
    evidencia(
        "D2.5.10-app-inventario", arquitectura=str(info.arquitectura), fuente=str(info.fuente)
    )
    assert info.arquitectura == Arquitectura.X86_64
    assert info.fuente == FuenteArquitectura.KERNEL

    recursos = sesion.cliente.arquitecturas_nodos()
    evidencia("D2.5.10-app-recursos", host_arch_por_nodo=recursos)
    assert recursos.get(NODO) in (None, "x86_64")
    *_, arq = descubrir_nodo_d(sesion, NODO, recursos=recursos)
    assert arq is not None and arq.arquitectura == Arquitectura.X86_64
    *_, arq_sin_recursos = descubrir_nodo_d(sesion, NODO)
    assert arq_sin_recursos is not None
    assert arq_sin_recursos.arquitectura == Arquitectura.X86_64
    assert arq_sin_recursos.fuente == FuenteArquitectura.KERNEL


# =========================================================================================
# CA-D1.8.9  qcow2 con backing file
# =========================================================================================


def test_d1_8_9_backing_file_rechazado_y_aplanado_aceptado(api: Api) -> None:
    """El servidor rechaza el qcow2 con backing file (texto exacto) y acepta el aplanado."""
    try:
        r = api.subir(ALMACEN_IMPORT, f"{PREFIJO_IMAGEN}backing.qcow2", BACKING_LOCAL)
        if r.status_code == 200:
            estado, log = api.tarea(r.json()["data"])
            texto = f"tarea={estado} log={' | '.join(log[-4:])}"
            rechazado = estado != "OK"
        else:
            texto = mensaje(r)
            rechazado = True
        evidencia("D1.8.9-backing", rechazado=rechazado, texto=texto, quedo=imagenes_d())
        assert rechazado, "el servidor aceptó un qcow2 con backing file"
        assert "backing file" in texto.lower()
        assert imagenes_d() == []
        # El aplanado (CirrOS) sí se acepta.
        r2 = api.subir(ALMACEN_IMPORT, IMG_SISTEMA, CIRROS_LOCAL)
        assert r2.status_code == 200, mensaje(r2)
        estado2, log2 = api.tarea(r2.json()["data"])
        evidencia("D1.8.9-aplanado", tarea=estado2, quedo=imagenes_d())
        assert estado2 == "OK", log2[-3:]
    finally:
        borrar_imagenes_d()


# =========================================================================================
# CA-D1.5.12 / CA-D1.7.10 / CA-D1.9.3 / CA-D1.10.8  Importación libvirt de extremo a extremo
# =========================================================================================


def test_d1_importacion_libvirt_de_extremo_a_extremo(sesion: Any, api: Api, vmids) -> None:
    """XML sintético UEFI (2 discos virtio, 1 tarjeta con MAC) → lectura → propuesta → subida de
    dos imágenes → creación con el servicio de la app → configuración real."""
    vmid = vmids(9085)
    dominio = interpretar_dominio(leer_xml(XML_UBUNTU_UEFI.encode()))
    assert dominio.uefi and dominio.con_nvram and len(dominio.discos) == 2
    assert dominio.tarjetas[0].mac == "52:54:00:ab:cd:ef"

    inv = descubrir(sesion)
    base = cfg_vacia(vmid)
    propuesta = proponer(dominio, base, inv, NODO, conservar_mac=True)
    filas = {f.campo: f for f in propuesta.filas}
    evidencia(
        "D1.5.12-propuesta",
        bloquea=propuesta.bloquea(),
        estados={c: str(f.estado) for c, f in filas.items()},
    )
    assert not propuesta.bloquea()
    assert filas["nvram"].estado == EstadoFila.NO_SE_MIGRA  # V-D30: la NVRAM no se migra
    cfg = propuesta.cfg
    assert cfg.firmware == Firmware.OVMF
    assert cfg.origen == OrigenSO.IMPORTAR_DISCO
    assert len(cfg.discos) == 2
    assert cfg.redes[0].bridge == "vmbr0"
    assert cfg.redes[0].mac_conservada == "52:54:00:ab:cd:ef"

    # Subir CirrOS como las dos imágenes del XML (contenido import del almacén del laboratorio).
    try:
        refs = []
        for nombre in (IMG_SISTEMA, IMG_DATOS):
            r = subir_a_import(sesion, CIRROS_LOCAL, nombre)
            assert r.estado == EstadoTransferencia.TERMINADA, r
            refs.append(RefVolumen(nombre, r.volid))
        evidencia("D1.7.10-imagenes", volids=[x.volid for x in refs])
        cfg.detalle_origen = DetalleImportacion(
            imagen=refs[0], otras=(ImagenDisco(indice=1, imagen=refs[1]),)
        )
        cfg.tipo_so = cfg.tipo_so or TipoSO.LINUX
        problemas = validar_importacion_d(cfg)
        evidencia("D1.7.10-validacion", problemas=[(p.campo, p.codigo) for p in problemas])
        assert not [p for p in problemas if str(p.severidad).endswith("error")]

        res = crear_con_app(sesion, cfg)
        evidencia(
            "D1.7.10-resultado",
            desenlace=str(res.desenlace),
            error=str(res.error),
            avisos=res.avisos,
        )
        assert res.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), res
        conf = api.config(vmid)
        evidencia(
            "D1.7.10-config",
            discos={k: v for k, v in conf.items() if re.fullmatch(r"(scsi|virtio|sata|ide)\d+", k)},
            net0=conf.get("net0"),
            bios=conf.get("bios"),
            efidisk0=conf.get("efidisk0"),
            machine=conf.get("machine"),
        )
        claves = [f"{d.bus.value}{i}" for i, d in enumerate(cfg.discos)]
        for clave in claves:
            assert clave in conf, f"falta {clave} en la configuración real"
            assert conf[clave].startswith(f"{STORAGE}:vm-{vmid}-disk-"), conf[clave]
            assert "size=112M" in conf[clave]  # el tamaño virtual de CirrOS: se importó la imagen
        assert conf["bios"] == "ovmf" and "efidisk0" in conf
        # CA-D1.10.8: la tarjeta conserva la MAC del origen.
        assert re.match(r"virtio=52:54:00:AB:CD:EF,", conf["net0"], re.IGNORECASE), conf["net0"]

        # CA-D1.5.12 / CA-D1.9.3: ¿arranca una MV UEFI importada sin NVRAM? Solo evidencia.
        lab.ssh(f"sudo qm set {vmid} --serial0 socket && sudo qm start {vmid}", timeout=120)
        estado = "?"
        for _ in range(20):
            estado = lab.ssh(f"sudo qm status {vmid}").strip()
            if "running" in estado:
                break
            time.sleep(1)
        salida = consola(vmid, 30)
        estado_final = lab.ssh(f"sudo qm status {vmid}", comprobar=False).strip()
        # Lectura del disco de sistema: señal de que el firmware llegó a arrancar desde él.
        bloques = api.datos(api.get(f"/nodes/{NODO}/qemu/{vmid}/status/current")).get(
            "blockstat", {}
        )
        leido = {k: v.get("rd_bytes") for k, v in bloques.items()}
        evidencia(
            "D1.5.12-arranque",
            estado=estado,
            estado_tras_30s=estado_final,
            bytes_leidos=leido,
            consola=" ".join(salida.split())[-600:],
        )
        lab.ssh(f"sudo qm stop {vmid} --skiplock 1", comprobar=False, timeout=120)
        assert "running" in estado, "la MV UEFI importada no llegó a estado running"
    finally:
        borrar_imagenes_d()


# =========================================================================================
# CA-D3.1.8 / CA-D3.2.9 / CA-D3.4.8 / CA-D3.8.6 / CA-D5.2.3 / CA-D3.3.8  Mapeos PCI y USB
# =========================================================================================


@pytest.fixture
def mapeos() -> Iterator[None]:
    """Mapeos PCI (uno inválido y otro válido según ``check-node``) y USB de prueba."""
    try:
        crear_mapeo_pci(PCI_INVALIDO, con_subsistema=False)
        crear_mapeo_pci(PCI_VALIDO, con_subsistema=True)
        crear_mapeo_usb(USB_PRUEBA)
        yield
    finally:
        borrar_mapeos_prueba()
        assert mapeos_de_prueba_restantes() == []


@pytest.fixture
def con_uso() -> Iterator[Cred]:
    """Rol completo en ``/`` y ``PVEMappingUser`` solo en el PCI válido y en el USB."""
    with usuario_con(
        PRIVS_D,
        "Uso",
        extra=(
            (f"/mapping/pci/{PCI_VALIDO}", "PVEMappingUser"),
            (f"/mapping/usb/{USB_PRUEBA}", "PVEMappingUser"),
        ),
    ) as c:
        yield c


def test_d3_1_8_el_mapeo_se_lista_solo_con_permiso_sobre_su_ruta(
    sesion: Any, entorno_d: lab.Entorno, con_uso: Cred, mapeos: None
) -> None:
    """Con ``PVEMappingUser`` solo en ``/mapping/pci/<id>`` el rol lista ese mapeo y no los otros;
    sin ningún permiso de mapeos la lista queda vacía (la app lo lee con ``cliente.mapeos``)."""
    s_uso = abrir_sesion(entorno_d, con_uso)
    try:
        con = s_uso.cliente.mapeos(TipoMapeo.PCI)
        usb = s_uso.cliente.mapeos(TipoMapeo.USB)
    finally:
        entorno_d.servicio.cerrar_sesion(s_uso)
    sin = sesion.cliente.mapeos(TipoMapeo.PCI)
    evidencia(
        "D3.1.8-listado",
        con_uso_pci=[m.id for m in con],
        con_uso_usb=[m.id for m in usb],
        sin_uso_pci=[m.id for m in sin],
        entradas=[(e.nodo, e.descripcion) for m in con for e in m.entradas],
    )
    assert [m.id for m in con] == [PCI_VALIDO]
    assert con[0].nodos() == frozenset({NODO})
    assert [m.id for m in usb] == [USB_PRUEBA]
    assert sin == []


def test_d3_2_9_crear_con_mapeo_con_y_sin_mapping_use(
    sesion: Any, api: Api, con_uso: Cred, mapeos: None, vmids
) -> None:
    """``POST qemu hostpci0=mapping=…``: crea con ``Mapping.Use``; 403 con la ruta sin él (API cruda)
    y la app lo traduce a ``PERMISO_INSUFICIENTE`` con la ruta del mapeo."""
    a_uso = Api(con_uso)
    v1 = vmids(9086)
    r = a_uso.crear_vm(v1, hostpci0=f"mapping={PCI_VALIDO}")
    assert r.status_code == 200, mensaje(r)
    estado, log = a_uso.tarea(r.json()["data"])
    assert estado == "OK", log[-3:]
    evidencia("D3.2.9-con-uso", hostpci0=a_uso.config(v1).get("hostpci0"))
    assert a_uso.config(v1)["hostpci0"].startswith(f"mapping={PCI_VALIDO}")

    v2 = vmids(9087)
    r = api.crear_vm(v2, hostpci0=f"mapping={PCI_VALIDO}")
    evidencia("D3.2.9-sin-uso-cruda", respuesta=mensaje(r))
    assert r.status_code == 403
    assert f"/mapping/pci/{PCI_VALIDO}" in r.text and "Mapping.Use" in r.text

    # La app (rol sin Mapping.Use): el 403 se traduce con la ruta del mapeo.
    cfg = cfg_vacia(v2, hardware_cluster=HardwareCluster(pci=(AsignacionPCI(PCI_VALIDO),)))
    res = crear_con_app(sesion, cfg)
    err = res.error
    evidencia(
        "D3.2.9-sin-uso-app",
        desenlace=str(res.desenlace),
        codigo=None if err is None else str(err.codigo),
        params=None if err is None else dict(err.params),
    )
    assert res.desenlace == Desenlace.ERROR and err is not None
    assert err.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert err.params.get("ruta") == f"/mapping/pci/{PCI_VALIDO}"
    assert err.params.get("mapeo") == PCI_VALIDO
    assert err.params.get("privilegio") == "Mapping.Use"
    assert v2 not in lab.vmids_de_prueba()  # no quedó nada a medias


def test_d3_2_9_la_app_crea_con_mapeos_pci_y_usb(
    entorno_d: lab.Entorno, con_uso: Cred, mapeos: None, vmids
) -> None:
    """La app crea la MV con PCI (``pcie`` → ``machine=q35``) y USB con ``Mapping.Use`` en cada ruta."""
    s = abrir_sesion(entorno_d, con_uso)
    try:
        vmid = vmids(9088)
        hw = HardwareCluster(
            pci=(AsignacionPCI(PCI_VALIDO, pcie=True),), usb=(AsignacionUSB(USB_PRUEBA, usb3=True),)
        )
        res = crear_con_app(s, cfg_vacia(vmid, hardware_cluster=hw))
    finally:
        entorno_d.servicio.cerrar_sesion(s)
    conf = Api(con_uso).config(vmid)
    evidencia(
        "D3.2.9-app-crea",
        desenlace=str(res.desenlace),
        error=str(res.error),
        hostpci0=conf.get("hostpci0"),
        usb0=conf.get("usb0"),
        machine=conf.get("machine"),
    )
    assert res.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), res
    assert conf["hostpci0"].startswith(f"mapping={PCI_VALIDO}") and "pcie=1" in conf["hostpci0"]
    assert conf["usb0"].startswith(f"mapping={USB_PRUEBA}") and "usb3=1" in conf["usb0"]
    assert "q35" in str(conf.get("machine"))


def traducir_arranque(
    estado_tarea: str, cfg: ConfiguracionVM
) -> tuple[ErrorProxLaunch, ErrorProxLaunch, str]:
    """Lo que hace la app con el fallo de una tarea de arranque: ``traducir_exitstatus`` +
    ``traducir_error_hardware`` y el texto final (``texto_error_d``). Devuelve ambos errores y el texto."""
    from proxlaunch.interfaz.textos_d import texto_error_d
    from proxlaunch.nucleo.api.traductor_errores import traducir_exitstatus
    from proxlaunch.nucleo.hardware_cluster.errores import traducir_error_hardware

    crudo = traducir_exitstatus(estado_tarea)
    final = traducir_error_hardware(crudo, cfg)
    return crudo, final, texto_error_d(final) or ""


def arrancar_por_api(a: Api, vmid: int) -> str:
    """``POST status/start`` con el token; devuelve el ``exitstatus`` de la tarea (o el 403)."""
    r = a.post(f"/nodes/{NODO}/qemu/{vmid}/status/start")
    if r.status_code != 200:
        return mensaje(r)
    estado, _ = a.tarea(r.json()["data"])
    return estado


@pytest.fixture
def arranque_pcie_sin_q35(con_uso: Cred, mapeos: None, vmids) -> tuple[ConfiguracionVM, str]:
    """Crea (acepta el servidor) y arranca una MV con ``hostpci0=mapping=…,pcie=1`` sin q35."""
    a = Api(con_uso)
    vmid = vmids(9089)
    r = a.crear_vm(vmid, hostpci0=f"mapping={PCI_VALIDO},pcie=1")
    evidencia("D3.4.8-crear-pcie-sin-q35", http=r.status_code, creada=vmid in lab.vmids_de_prueba())
    assert r.status_code == 200, mensaje(r)
    assert a.tarea(r.json()["data"])[0] == "OK"
    exitstatus = arrancar_por_api(a, vmid)
    evidencia("D3.4.8-arranque-pcie-sin-q35", exitstatus=exitstatus)
    cfg = cfg_vacia(
        vmid, hardware_cluster=HardwareCluster(pci=(AsignacionPCI(PCI_VALIDO, pcie=True),))
    )
    return cfg, exitstatus


def test_d3_4_8_pcie_sin_q35_se_acepta_al_crear_y_falla_al_arrancar(
    arranque_pcie_sin_q35: tuple[ConfiguracionVM, str],
) -> None:
    """``pcie=1`` sin ``machine=q35``: Proxmox 9.2 lo ACEPTA al crear (la investigación decía que lo
    rechazaba) y falla al arrancar con «q35 machine model is not enabled»; la app lo clasifica."""
    cfg, exitstatus = arranque_pcie_sin_q35
    assert "q35 machine model is not enabled" in exitstatus
    _, final, texto = traducir_arranque(exitstatus, cfg)
    evidencia(
        "D3.4.8-traduccion-app", codigo=str(final.codigo), params=dict(final.params), texto=texto
    )
    assert final.codigo == CodigoError.MAPEO_NO_DISPONIBLE
    assert final.params.get("mapeo") == PCI_VALIDO


def test_d3_4_8_el_texto_de_q35_explica_la_causa(
    arranque_pcie_sin_q35: tuple[ConfiguracionVM, str],
) -> None:
    cfg, exitstatus = arranque_pcie_sin_q35
    _, _, texto = traducir_arranque(exitstatus, cfg)
    assert "q35" in texto.lower(), texto


def test_d3_4_8_dos_mvs_con_el_mismo_mapeo_evidencia(con_uso: Cred, mapeos: None, vmids) -> None:
    """Dos MVs con el mismo mapeo: se arrancan una tras otra y se anota qué dice Proxmox. El
    laboratorio no tiene IOMMU, así que ya falla la primera (no se puede ver el choque real)."""
    a = Api(con_uso)
    v1, v2 = vmids(9090), vmids(9091)
    for v in (v1, v2):
        r = a.crear_vm(v, hostpci0=f"mapping={PCI_VALIDO}")
        assert r.status_code == 200, mensaje(r)
        assert a.tarea(r.json()["data"])[0] == "OK"
    salidas = [arrancar_por_api(a, v) for v in (v1, v2)]
    evidencia("D3.4.8-dos-mvs-mismo-mapeo", primera=salidas[0], segunda=salidas[1])
    assert all(x != "OK" for x in salidas)  # sin IOMMU ninguna arranca


def test_d3_8_6_arranque_usb_con_dispositivo_ausente(
    entorno_d: lab.Entorno, con_uso: Cred, mapeos: None, vmids
) -> None:
    """Mapeo USB sin el dispositivo presente: texto exacto y traducción de la app al encender."""
    s = abrir_sesion(entorno_d, con_uso)
    try:
        vmid = vmids(9092)
        cfg = cfg_vacia(
            vmid, hardware_cluster=HardwareCluster(usb=(AsignacionUSB(USB_PRUEBA),)), encender=True
        )
        res = crear_con_app(s, cfg)
    finally:
        entorno_d.servicio.cerrar_sesion(s)
    err = res.error
    from proxlaunch.interfaz.textos_d import texto_error_d

    evidencia(
        "D3.8.6-encender-usb",
        desenlace=str(res.desenlace),
        avisos=res.avisos,
        codigo=None if err is None else str(err.codigo),
        params=None if err is None else dict(err.params),
        detalle=None if err is None else err.detalle_tecnico,
        texto=None if err is None else texto_error_d(err),
    )
    assert res.desenlace == Desenlace.CON_AVISOS and "encendido_fallido" in res.avisos
    assert err is not None and err.codigo == CodigoError.MAPEO_NO_DISPONIBLE
    assert "USB Mapping invalid (hardware probably changed)" in err.detalle_tecnico
    assert vmid in lab.vmids_de_prueba()  # la MV se creó; solo falló el encendido


def test_d3_8_6_arranque_con_mapeo_pci_invalido(
    entorno_d: lab.Entorno, mapeos: None, vmids
) -> None:
    """Mapeo PCI que ``check-node`` marca inválido (sin ``subsystem-id``): texto exacto y traducción."""
    with usuario_con(PRIVS_D, "TodosPci", extra=(("/mapping/pci", "PVEMappingUser"),)) as c:
        s = abrir_sesion(entorno_d, c)
        try:
            vmid = vmids(9093)
            cfg = cfg_vacia(
                vmid,
                hardware_cluster=HardwareCluster(pci=(AsignacionPCI(PCI_INVALIDO),)),
                encender=True,
            )
            res = crear_con_app(s, cfg)
        finally:
            entorno_d.servicio.cerrar_sesion(s)
    err = res.error
    from proxlaunch.interfaz.textos_d import texto_error_d

    evidencia(
        "D3.8.6-encender-pci-invalido",
        desenlace=str(res.desenlace),
        codigo=None if err is None else str(err.codigo),
        params=None if err is None else dict(err.params),
        detalle=None if err is None else err.detalle_tecnico,
        texto=None if err is None else texto_error_d(err),
    )
    assert err is not None and err.codigo == CodigoError.MAPEO_NO_DISPONIBLE
    assert "PCI device mapping invalid (hardware probably changed)" in err.detalle_tecnico


def test_d3_8_6_arranque_pci_sin_iommu_se_traduce(
    entorno_d: lab.Entorno, con_uso: Cred, mapeos: None, vmids
) -> None:
    """Mapeo PCI válido en un nodo sin IOMMU: el texto real de Proxmox debería traducirse."""
    s = abrir_sesion(entorno_d, con_uso)
    try:
        vmid = vmids(9094)
        cfg = cfg_vacia(
            vmid, hardware_cluster=HardwareCluster(pci=(AsignacionPCI(PCI_VALIDO),)), encender=True
        )
        res = crear_con_app(s, cfg)
    finally:
        entorno_d.servicio.cerrar_sesion(s)
    err = res.error
    assert err is not None
    evidencia("D3.8.6-encender-pci-sin-iommu", codigo=str(err.codigo), detalle=err.detalle_tecnico)
    assert err.codigo != CodigoError.DESCONOCIDO


def test_d5_2_3_la_orden_de_la_guia_concede_el_uso_del_mapeo(mapeos: None, vmids) -> None:
    """La orden de ejemplo de ``textos_d.texto_admin_mapeo`` (con el usuario real) concede el uso:
    antes 403, después se crea la MV."""
    from proxlaunch.interfaz.textos_d import texto_admin_mapeo

    with usuario_con(PRIVS_D, "SinUso") as c:
        a = Api(c)
        vmid = vmids(9095)
        antes = a.crear_vm(vmid, hostpci0=f"mapping={PCI_VALIDO}")
        assert antes.status_code == 403, mensaje(antes)
        texto = texto_admin_mapeo(TipoMapeo.PCI, PCI_VALIDO, c.userid)
        m = re.search(r"pveum acl modify \S+ --roles PVEMappingUser --users \S+", texto)
        assert m is not None, texto
        orden = m.group(0).rstrip(".")
        evidencia("D5.2.3-orden", orden=orden)
        lab.ssh(f"sudo {orden}")
        try:
            despues = a.crear_vm(vmid, hostpci0=f"mapping={PCI_VALIDO}")
            assert despues.status_code == 200, mensaje(despues)
            estado, log = a.tarea(despues.json()["data"])
            assert estado == "OK", log[-3:]
        finally:
            lab.ssh(
                f"sudo pveum acl delete /mapping/pci/{PCI_VALIDO} --users {c.userid} --roles PVEMappingUser",
                comprobar=False,
            )


def test_d3_3_8_check_node_con_el_rol_y_con_un_nodo_inexistente(
    entorno_d: lab.Entorno, mapeos: None
) -> None:
    """``GET /cluster/mapping/pci?check-node=`` con el rol: respuesta real, nodo inexistente y la
    lectura de ``comprobar_mapeos`` de la app."""
    with usuario_con(PRIVS_D, "Uso", extra=(("/mapping/pci", "PVEMappingUser"),)) as c:
        a = Api(c)
        ok = a.get("/cluster/mapping/pci", **{"check-node": NODO})
        otro = a.get("/cluster/mapping/pci", **{"check-node": "nodo-inexistente"})
        evidencia(
            "D3.3.8-cruda",
            nodo_http=ok.status_code,
            nodo=ok.text[:500],
            inexistente_http=otro.status_code,
            inexistente=otro.text[:300],
        )
        assert ok.status_code == 200
        s = abrir_sesion(entorno_d, c)
        try:
            comp = s.cliente.comprobar_mapeos(TipoMapeo.PCI, NODO, [PCI_VALIDO, PCI_INVALIDO])
            evidencia("D3.3.8-app", resultado={k: v.errores for k, v in comp.items()})
            assert comp[PCI_VALIDO].errores == ()
            assert any("subsystem-id" in e for e in comp[PCI_INVALIDO].errores)
            try:
                s.cliente.comprobar_mapeos(TipoMapeo.PCI, "nodo-inexistente", [PCI_VALIDO])
                resultado = "sin error"
            except ErrorProxLaunch as e:
                resultado = f"error {e.codigo}: {e.detalle_tecnico[:160]}"
            evidencia("D3.3.8-app-nodo-inexistente", resultado=resultado)
        finally:
            entorno_d.servicio.cerrar_sesion(s)


# =========================================================================================
# CA-D3.6.10  CPU personalizada (cpu-models.conf)
# =========================================================================================


@pytest.fixture
def modelo_cpu() -> Iterator[None]:
    lab.ssh(
        f"sudo tee {FICHERO_CPU} >/dev/null <<'FIN'\ncpu-model: {CPU_NOMBRE}\n    reported-model kvm64\nFIN"
    )
    try:
        yield
    finally:
        lab.ssh(f"sudo rm -f {FICHERO_CPU}", comprobar=False)


def test_d3_6_10_cpu_personalizada_permisos_listado_y_creacion(
    sesion: Any, entorno_d: lab.Entorno, api: Api, modelo_cpu: None, vmids
) -> None:
    """9.2: ``Mapping.Audit`` en ``/mapping/cpu/<n>`` basta para verlo; ``cpu=custom-<n>`` sin
    ``Mapping.Use`` da 403 con la ruta; con él crea; la app lo lista y traduce el 403."""
    ruta = f"/mapping/cpu/{CPU_NOMBRE}"
    # Solo Mapping.Audit en la ruta (sin Sys.Audit): lista de modelos.
    with usuario_con(("Mapping.Audit",), "SoloAudit", ruta=ruta) as c_audit:
        a = Api(c_audit)
        r = a.get(f"/nodes/{NODO}/capabilities/qemu/cpu")
        evidencia("D3.6.10-solo-audit", http=r.status_code, cuerpo=r.text[:150])
        assert r.status_code == 200
        nombres = [m["name"] for m in r.json()["data"]]
        evidencia(
            "D3.6.10-solo-audit-modelos",
            total=len(nombres),
            custom=[n for n in nombres if n.startswith("custom-")],
        )
        assert CPU_TIPO in nombres
    # El rol completo sin permiso sobre el modelo: ¿lo ve? (evidencia) y 403 al crear.
    r = api.get(f"/nodes/{NODO}/capabilities/qemu/cpu")
    visibles = [m["name"] for m in api.datos(r) if str(m["name"]).startswith("custom-")]
    evidencia("D3.6.10-sin-permiso-listado", custom_visibles=visibles)
    vmid = vmids(9095)
    r = api.crear_vm(vmid, cpu=CPU_TIPO)
    evidencia("D3.6.10-sin-uso-cruda", respuesta=mensaje(r))
    assert r.status_code == 403
    assert ruta in r.text and "Mapping.Use" in r.text
    # La app traduce el 403 a CPU_PERSONALIZADA_RECHAZADA con la ruta.
    res = crear_con_app(sesion, cfg_vacia(vmid, tipo_cpu=CPU_TIPO))
    err = res.error
    evidencia(
        "D3.6.10-sin-uso-app",
        desenlace=str(res.desenlace),
        codigo=None if err is None else str(err.codigo),
        params=None if err is None else dict(err.params),
    )
    assert res.desenlace == Desenlace.ERROR and err is not None
    assert err.codigo == CodigoError.CPU_PERSONALIZADA_RECHAZADA
    assert err.params.get("ruta") == ruta
    assert err.params.get("cpu") == CPU_TIPO
    # Con Mapping.Use en la ruta: se crea y la app lo lista.
    with usuario_con(PRIVS_D, "UsoCpu", extra=((ruta, "PVEMappingUser"),)) as c_uso:
        s = abrir_sesion(entorno_d, c_uso)
        try:
            modelos = s.cliente.modelos_cpu(NODO, arch="x86_64")
            propio = [m for m in modelos if m.nombre == CPU_TIPO]
            evidencia("D3.6.10-app-listado", modelo=propio, total=len(modelos))
            assert propio and propio[0].personalizado
            res2 = crear_con_app(s, cfg_vacia(vmid, tipo_cpu=CPU_TIPO))
        finally:
            entorno_d.servicio.cerrar_sesion(s)
        assert res2.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), res2
        assert Api(c_uso).config(vmid)["cpu"].startswith(CPU_TIPO)


# =========================================================================================
# §14.2-11  MAC al clonar y al reescribir netN
# =========================================================================================


def test_d1_10_mac_nueva_sin_mac_y_conservada_con_mac(sesion: Any, api: Api, vmids) -> None:
    """Tras clonar, ``PUT net0=virtio,bridge=vmbr0`` sin MAC genera una MAC nueva; reenviando la MAC
    se conserva."""
    plantilla, clon = vmids(9096), vmids(9097)
    lab.ssh(
        f"sudo qm create {plantilla} --name plc-d-plantilla --memory 128 --cores 1 "
        f"--net0 virtio,bridge=vmbr0 --scsi0 {STORAGE}:1 && sudo qm template {plantilla}",
        timeout=180,
    )
    cli = sesion.cliente
    upid = cli.clonar_vm(NODO, plantilla, {"newid": str(clon), "name": "plc-d-clon", "full": "1"})
    assert api.tarea(upid)[0] == "OK"
    mac0 = re.search(r"=([0-9A-Fa-f:]{17})", str(api.config(plantilla)["net0"])).group(1)  # type: ignore[union-attr]
    mac1 = re.search(r"=([0-9A-Fa-f:]{17})", str(api.config(clon)["net0"])).group(1)  # type: ignore[union-attr]
    cli.configurar_vm(NODO, clon, {"net0": "virtio,bridge=vmbr0"})
    mac2 = re.search(r"=([0-9A-Fa-f:]{17})", str(api.config(clon)["net0"])).group(1)  # type: ignore[union-attr]
    cli.configurar_vm(NODO, clon, {"net0": f"virtio={mac2},bridge=vmbr0"})
    mac3 = re.search(r"=([0-9A-Fa-f:]{17})", str(api.config(clon)["net0"])).group(1)  # type: ignore[union-attr]
    evidencia("D1.10-mac", plantilla=mac0, clon_tras_clonar=mac1, sin_mac=mac2, con_mac=mac3)
    assert mac1.lower() != mac0.lower()  # el clon ya nace con MAC propia
    assert mac2.lower() != mac1.lower()  # sin MAC: Proxmox genera otra
    assert mac3.lower() == mac2.lower()  # con MAC: se conserva
