"""Fase C (0.8.0) contra el laboratorio real: lista [LAB] de docs/requisitos/fase-c.md §15.2.

Cubre el inventario «Lotes en el servidor» con Deshacer, las VNets de SDN, el firewall con grupo
y la red del clon conservando la MAC. Solo con ``PROXLAUNCH_LAB=1`` y solo contra el laboratorio
local (127.0.0.1:8006, nodo ``pve-lab``). VMIDs 9070-9084 únicamente.

Todo lo que se cambia en el laboratorio se revierte al terminar (también si la prueba falla):
MVs y plantillas, VNets/zonas temporales, ``user-tag-access``/``registered-tags`` del datacenter,
usuarios, roles y ACL, el fichero ``/var/tmp`` de la imagen y la directiva ``source`` de SDN en
``/etc/network/interfaces`` (ver ``sdn_realizado``). El firewall del datacenter NO se activa.

Las pruebas imprimen líneas ``EVIDENCIA[...]`` (visibles con ``-s``) con lo observado. Los fallos
de la APP se marcan ``xfail(strict=True, reason="LAB-C-n: …")``: no se toca ``src/``.
"""

# ruff: noqa: E501
# (cadenas largas de EVIDENCIA y de comandos del laboratorio)
from __future__ import annotations

import contextlib
import json
import re
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import pytest
import requests

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import FirewallMV, ModoDhcp, Politica
from proxlaunch.nucleo.inventario.modelos import MotivoNoDeshacible
from proxlaunch.nucleo.inventario.servicio import ServicioInventario
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    DefinicionLote,
    EstadoMV,
    EstadoRollback,
    PatronNombres,
    Plan,
)
from proxlaunch.nucleo.lote.motor import ControlLote, MotorLote
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.modelos.conexion import CredencialToken, MetodoAuth
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleClon, RefPlantilla
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed, OrigenSO
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.red.errores_sdn import anotar_error_red
from proxlaunch.nucleo.red.modelos import (
    AccionTarjeta,
    CampoRed,
    ModoRedClon,
    RedClon,
    TarjetaClon,
)
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.catalogo import leer_politica_etiquetas
from proxlaunch.nucleo.servicios.descubrimiento import descubrir

from . import apoyo_lab as lab

pytestmark = [
    pytest.mark.integracion,
    pytest.mark.filterwarnings("ignore::urllib3.exceptions.InsecureRequestWarning"),
]

NODO = lab.NODO
STORAGE = "lab-lvmthin"
URL = f"https://{lab.HOST}:{lab.PUERTO}/api2/json"
CIRROS_LOCAL = lab.DIR_LAB / "discos" / "proxlaunch-lab-cirros.qcow2"
CIRROS_REMOTA = "/var/tmp/proxlaunch-lab-cirros-fc.qcow2"
INTERFACES = "/etc/network/interfaces"
INTERFACES_COPIA = "/var/tmp/interfaces.orig-fase-c-test"
SOURCE_SDN = "source /etc/network/interfaces.d/sdn"

# VMIDs de esta fase (9070-9084)
V_PLANTILLA = 9070  # plantilla CirrOS con net0 en vmbr0
V_CLON_A = 9071  # clon suelto de las pruebas con la API cruda
V_PLANT_RED = 9072  # plantilla vacía con net0=labnet y net1=vmbr0
V_CLON_B = 9073  # segundo clon suelto
V_LOTE = 9074  # lote compartido (9074, 9075)
V_E2E = 9078  # lote del extremo a extremo (9078, 9079)
V_PLANT_FW = 9076  # plantilla con firewall propio
V_CLON_FW = 9077
V_VARIOS = 9080  # MVs sueltas de pruebas puntuales
V_MIN, V_MAX = 9070, 9084

# El rol de la guía menos los privilegios que cada prueba concede por separado
PRIVS_SIN_SDN = tuple(p for p in ROL_PROXLAUNCH if p != "SDN.Use")
PRIVS_SIN_AUDIT = tuple(p for p in ROL_PROXLAUNCH if p != "Sys.Audit")
BASE_VNETS = {"labnet", "labv20"}


def evidencia(clave: str, **datos: Any) -> None:
    detalle = " ".join(f"{k}={v!r}" for k, v in datos.items())
    print(f"EVIDENCIA[{clave}] {detalle}")


# --- Apoyo: administración (root del laboratorio) -------------------------------------------


def _root(orden: str, *, comprobar: bool = True, timeout: float = 240) -> str:
    return lab.ssh(orden, comprobar=comprobar, timeout=timeout)


def _opciones_dc() -> dict[str, Any]:
    return json.loads(_root("sudo pvesh get /cluster/options --output-format json"))


def _vnets_existentes() -> set[str]:
    datos = json.loads(_root("sudo pvesh get /cluster/sdn/vnets --output-format json"))
    return {v["vnet"] for v in datos}


def _zonas_existentes() -> set[str]:
    datos = json.loads(_root("sudo pvesh get /cluster/sdn/zones --output-format json"))
    return {z["zone"] for z in datos}


def _borrar_vnet(vnet: str) -> None:
    """Borra una VNet temporal: primero sus subredes (si no, Proxmox no la borra)."""
    salida = _root(
        f"sudo pvesh get /cluster/sdn/vnets/{vnet}/subnets --output-format json 2>/dev/null; true",
        comprobar=False,
    )
    for sub in json.loads(salida) if salida.strip() else []:
        _root(
            f"sudo pvesh delete /cluster/sdn/vnets/{vnet}/subnets/{sub['subnet']} >/dev/null 2>&1; true",
            comprobar=False,
        )
    _root(f"sudo pvesh delete /cluster/sdn/vnets/{vnet} >/dev/null 2>&1; true", comprobar=False)


def _aplicar_sdn(esperar_s: float = 40.0) -> None:
    """Aplica el SDN (como root) y espera a que ``ifreload`` termine."""
    _root("sudo pvesh set /cluster/sdn >/dev/null 2>&1; true", comprobar=False)
    time.sleep(3)
    fin = time.monotonic() + esperar_s
    while time.monotonic() < fin:
        tareas = _root(
            "sudo pvesh get /nodes/pve-lab/tasks --limit 6 --source active --output-format json",
            comprobar=False,
        )
        if "reloadnetworkall" not in tareas:
            return
        time.sleep(1)


def _etiqueta_sufijo() -> str:
    return time.strftime("%H%M%S")


def _destruir_rango() -> None:
    """Destruye (y desprotege) las MVs 9070-9084; nunca toca el resto del rango de pruebas."""
    ordenes = "; ".join(
        f"sudo qm unlock {v}; sudo qm set {v} --protection 0; sudo qm stop {v} --skiplock 1; "
        f"sudo qm destroy {v} --purge 1 --skiplock 1 --destroy-unreferenced-disks 1"
        for v in range(V_MIN, V_MAX + 1)
    )
    _root(f"({ordenes}) >/dev/null 2>&1; true", comprobar=False, timeout=600)


def _existentes_en_rango() -> list[int]:
    return sorted(v for v in lab.vmids_de_prueba() if V_MIN <= v <= V_MAX)


@pytest.fixture
def vms() -> Iterator[Callable[..., int]]:
    """Registra VMIDs de ESTA fase (9070-9084); se destruyen al terminar la prueba.

    Sustituye a la fixture homónima de ``conftest.py`` (rango completo) para no tocar nada ajeno.
    """
    creados: list[int] = []

    def registrar(*ids: int) -> int:
        for v in ids:
            if not V_MIN <= v <= V_MAX:
                raise ValueError(f"VMID fuera del rango de la fase C: {v}")
        creados.extend(ids)
        return ids[0]

    yield registrar
    if creados:
        ordenes = "; ".join(
            f"sudo qm unlock {v}; sudo qm set {v} --protection 0; sudo qm stop {v} --skiplock 1; "
            f"sudo qm destroy {v} --purge 1 --skiplock 1 --destroy-unreferenced-disks 1"
            for v in sorted(set(creados))
        )
        _root(f"({ordenes}) >/dev/null 2>&1; true", comprobar=False, timeout=600)


def _crear_plantilla_vacia(vmid: int, nombre: str, redes: str, extra: str = "") -> None:
    """Plantilla sin sistema (disco vacío de 1 GiB) para pruebas de red y firewall."""
    _root(
        f"sudo qm create {vmid} --name {nombre} --memory 64 --cores 1 --scsihw virtio-scsi-single "
        f"--scsi0 {STORAGE}:1 {redes} {extra} && sudo qm template {vmid}",
        timeout=180,
    )


# --- Apoyo: API cruda con token ---------------------------------------------------------------


@dataclass(frozen=True)
class Resp:
    estado: int
    motivo: str  # línea de estado HTTP («Permission check failed (…)»)
    datos: Any
    errores: Any = None

    @property
    def ok(self) -> bool:
        return self.estado == 200


class ApiCruda:
    """Peticiones directas con un token (solo 127.0.0.1:8006)."""

    def __init__(self, token_id: str, secreto: str) -> None:
        lab.comprobar_destino(lab.HOST, lab.PUERTO, NODO)
        self._cab = {"Authorization": f"PVEAPIToken={token_id}={secreto}"}

    def pedir(self, metodo: str, ruta: str, **parametros: Any) -> Resp:
        kw: dict[str, Any] = (
            {"params": parametros} if metodo == "GET" else {"data": parametros or None}
        )
        r = requests.request(metodo, URL + ruta, headers=self._cab, verify=False, timeout=60, **kw)
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = {}
        return Resp(r.status_code, r.reason, cuerpo.get("data"), cuerpo.get("errors"))

    def tarea(self, upid: str, maximo_s: float = 180.0) -> tuple[str, list[str]]:
        """Espera una tarea; devuelve ``(exitstatus, líneas del registro)``."""
        ruta = f"/nodes/{NODO}/tasks/{quote(upid, safe=':@!')}"
        fin = time.monotonic() + maximo_s
        while time.monotonic() < fin:
            r = self.pedir("GET", f"{ruta}/status")
            if r.ok and r.datos["status"] == "stopped":
                log = self.pedir("GET", f"{ruta}/log", limit=500)
                return str(r.datos.get("exitstatus")), [x["t"] for x in (log.datos or [])]
            time.sleep(0.5)
        raise AssertionError(f"la tarea no terminó en {maximo_s} s: {upid}")

    def clonar(self, origen: int, nuevo: int, nombre: str) -> str:
        """Clona y espera al fin de la tarea; devuelve el ``exitstatus``."""
        r = self.pedir("POST", f"/nodes/{NODO}/qemu/{origen}/clone", newid=nuevo, name=nombre)
        assert r.ok, (r.estado, r.motivo)
        return self.tarea(r.datos)[0]

    def config(self, vmid: int) -> dict[str, Any]:
        r = self.pedir("GET", f"/nodes/{NODO}/qemu/{vmid}/config")
        assert r.ok, (r.estado, r.motivo)
        return dict(r.datos)


@dataclass(frozen=True)
class Cred:
    userid: str
    token_id: str
    secreto: str = field(repr=False)


@contextlib.contextmanager
def usuario_con(
    privs: tuple[str, ...],
    sufijo: str,
    *,
    sdn_en: tuple[str, ...] = (),
    raiz: bool = True,
) -> Iterator[Cred]:
    """Rol ``PlcFC<sufijo>`` + usuario + token (privsep=0). Todo se borra al salir.

    ``privs`` se concede en ``/`` (si ``raiz``); ``SDN.Use`` suelto, con un segundo rol, solo en las
    rutas ``sdn_en`` (p. ej. ``/sdn/zones/labzona``).
    """
    rol, rol_sdn = f"PlcFC{sufijo}", f"PlcFC{sufijo}Sdn"
    userid = f"plcfc{sufijo.lower()}@pve"
    lab.borrar_usuario(userid)
    lab.borrar_rol(rol)
    lab.borrar_rol(rol_sdn)
    try:
        lab.crear_rol(privs, rol)
        lab.ssh(f"sudo pveum user add {userid} --password '{lab.nuevo_secreto()}'")
        if raiz:
            lab.ssh(f"sudo pveum acl modify / --users {userid} --roles {rol} --propagate 1")
        if sdn_en:
            lab.crear_rol(("SDN.Use",), rol_sdn)
            for ruta in sdn_en:
                lab.ssh(
                    f"sudo pveum acl modify {ruta} --users {userid} --roles {rol_sdn} --propagate 1"
                )
        completo = lab.crear_token(userid, "tk", privsep=0)
        token_id, secreto = completo.rsplit("=", 1)
        yield Cred(userid, token_id, secreto)
    finally:
        lab.borrar_usuario(userid)
        lab.borrar_rol(rol)
        lab.borrar_rol(rol_sdn)


def _sesion(entorno: lab.Entorno, cred: Cred) -> Any:
    """Sesión del núcleo de ProxLaunch (token) para ``cred``."""
    p = lab.perfil(MetodoAuth.TOKEN, cred.token_id)
    lab.confiar_en_laboratorio(entorno, p)
    sesion = entorno.servicio.conectar(p, CredencialToken(cred.token_id, cred.secreto))
    return sesion


@contextlib.contextmanager
def sesion_de(entorno: lab.Entorno, cred: Cred) -> Iterator[Any]:
    sesion = _sesion(entorno, cred)
    try:
        yield sesion
    finally:
        entorno.servicio.cerrar_sesion(sesion)


# --- Fixtures de módulo ------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _guarda_modulo() -> Iterator[None]:
    """Limpieza inicial y final de las MVs de la fase C (y de ningún VMID ajeno)."""
    lab.comprobar_destino(lab.HOST, lab.PUERTO, NODO)
    _destruir_rango()
    yield
    _destruir_rango()


@pytest.fixture(scope="module", autouse=True)
def sdn_realizado(_guarda_modulo: None) -> Iterator[None]:
    """Pone en pie los bridges de las VNets y deja el SDN y el datacenter como estaban.

    Hallazgo del laboratorio: ``/etc/network/interfaces`` no trae ``source …/interfaces.d/sdn``,
    así que ``labnet``/``labv20`` están «aplicadas» pero NO existen como bridges y ninguna MV
    puede arrancar en ellas. La fixture añade la directiva (con copia previa), aplica el SDN y,
    al final, borra lo temporal, restaura el fichero original y baja los bridges.
    """
    opciones0 = _opciones_dc()
    assert "user-tag-access" not in opciones0 and "registered-tags" not in opciones0, (
        "el datacenter ya tenía política de etiquetas: no se toca"
    )
    vnets0, zonas0 = _vnets_existentes(), _zonas_existentes()
    assert vnets0 >= BASE_VNETS, f"faltan las VNets base del laboratorio: {vnets0}"
    con_source = SOURCE_SDN in _root(f"sudo cat {INTERFACES}")
    try:
        if not con_source:
            _root(f"sudo cp {INTERFACES} {INTERFACES_COPIA}")
            _root(f"echo '{SOURCE_SDN}' | sudo tee -a {INTERFACES} >/dev/null")
        _aplicar_sdn()
        yield
    finally:
        # opciones del datacenter (por si una prueba murió a medias)
        _root(
            "sudo pvesh set /cluster/options --delete user-tag-access,registered-tags >/dev/null 2>&1; true",
            comprobar=False,
        )
        # VNets y zonas temporales (las que no estaban al empezar)
        for vnet in sorted(_vnets_existentes() - vnets0):
            _borrar_vnet(vnet)
        for zona in sorted(_zonas_existentes() - zonas0):
            _root(
                f"sudo pvesh delete /cluster/sdn/zones/{zona} >/dev/null 2>&1; true",
                comprobar=False,
            )
        _aplicar_sdn()
        if not con_source:
            _root(
                f"sudo ifdown labnet labv20 >/dev/null 2>&1; "
                f"sudo cp {INTERFACES_COPIA} {INTERFACES} && sudo rm -f {INTERFACES_COPIA}; "
                "sudo ip link del labnet >/dev/null 2>&1; sudo ip link del labv20 >/dev/null 2>&1; "
                "sudo ip link del vmbr1.20 >/dev/null 2>&1; true",
                comprobar=False,
            )
        assert _opciones_dc().get("user-tag-access") is None
        assert _vnets_existentes() == vnets0
        assert _zonas_existentes() == zonas0


@pytest.fixture(scope="module")
def plantilla_cirros(_guarda_modulo: None) -> Iterator[int]:
    """Plantilla CirrOS (9070) en ``lab-lvmthin`` con ``net0=virtio,bridge=vmbr0``.

    La imagen se copia por SSH a ``/var/tmp`` (no hace falta activar el contenido ``import``).
    """
    with CIRROS_LOCAL.open("rb") as f:
        r = subprocess.run(
            [str(lab.DIR_LAB / "lab.sh"), "ssh", f"cat > {CIRROS_REMOTA}"],
            stdin=f,
            capture_output=True,
            timeout=300,
            check=False,
        )
    assert r.returncode == 0, r.stderr[-300:]
    try:
        _root(
            f"sudo qm create {V_PLANTILLA} --name plc-fc-cirros --memory 128 --cores 1 "
            f"--scsihw virtio-scsi-single --ostype l26 --boot order=scsi0 "
            f"--net0 virtio,bridge=vmbr0 "
            f"--scsi0 {STORAGE}:0,import-from={CIRROS_REMOTA},discard=on,iothread=1 "
            f"&& sudo qm template {V_PLANTILLA}",
            timeout=300,
        )
        yield V_PLANTILLA
    finally:
        _root(f"sudo rm -f {CIRROS_REMOTA}", comprobar=False)


@pytest.fixture(scope="module")
def cred_app(_guarda_modulo: None) -> Iterator[Cred]:
    """Usuario con el rol de la guía (14 privilegios, ``SDN.Use`` incluido) en ``/``."""
    with usuario_con(ROL_PROXLAUNCH, "App") as c:
        yield c


@pytest.fixture(scope="module")
def api_app(cred_app: Cred) -> ApiCruda:
    return ApiCruda(cred_app.token_id, cred_app.secreto)


@pytest.fixture(scope="module")
def entorno_modulo(tmp_path_factory: pytest.TempPathFactory) -> lab.Entorno:
    return lab.crear_entorno(tmp_path_factory.mktemp("fase_c"))


@pytest.fixture(scope="module")
def sesion_app(entorno_modulo: lab.Entorno, cred_app: Cred) -> Iterator[Any]:
    with sesion_de(entorno_modulo, cred_app) as s:
        yield s


def _esperar_plantilla_visible(sesion: Any, vmid: int, maximo_s: float = 60.0) -> None:
    """``/cluster/resources`` tarda unos segundos (pvestatd) en mostrar la plantilla."""
    fin = time.monotonic() + maximo_s
    while time.monotonic() < fin:
        if any(p.vmid == vmid for p in sesion.cliente.plantillas_visibles()):
            return
        time.sleep(1)
    raise AssertionError(f"la plantilla {vmid} no apareció en /cluster/resources")


# --- Apoyo: lote con la APP ---------------------------------------------------------------------


def _cfg_clon(
    plantilla: int,
    nombre_plantilla: str,
    *,
    red_clon: RedClon | None = None,
    firewall: FirewallMV | None = None,
    **cambios: Any,
) -> ConfiguracionVM:
    """Configuración base del lote que clona ``plantilla`` (con nota de origen para el inventario)."""
    base: dict[str, Any] = {
        "vmid": 100,  # se ignora en el lote
        "nombre": "plantilla",
        "nodo": NODO,
        "cores": 1,
        "memoria_mib": 128,
        "discos": [Disco(storage=STORAGE, tamano_gib=1)],
        "redes": [InterfazRed(bridge="vmbr0")],
        "origen": OrigenSO.CLONAR_PLANTILLA,
        "detalle_origen": DetalleClon(plantilla=RefPlantilla(nombre_plantilla, plantilla, NODO)),
        "notas_origen": True,
        "red_clon": red_clon,
        "firewall": firewall,
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def _definicion(
    cfg: ConfiguracionVM, cantidad: int, vmid_inicial: int, prefijo: str
) -> DefinicionLote:
    return DefinicionLote(
        plantilla=cfg,
        cantidad=cantidad,
        patron=PatronNombres(prefijo=prefijo),
        vmid_inicial=vmid_inicial,
        etiquetar=True,
    )


def _planificar(sesion: Any, definicion: DefinicionLote) -> tuple[Plan, Inventario]:
    inv = descubrir(sesion)
    return Planificador(sesion, RelojReal()).planificar(definicion, inv), inv


@dataclass
class Corrida:
    libro: Libro
    control: ControlLote
    pausa: object
    segundos: float


def _ejecutar(sesion: Any, plan: Plan, inv: Inventario, *, maximo_s: float = 600.0) -> Corrida:
    """Ejecuta el plan con el motor real; si el lote se pausa lo cancela (como una decisión)."""
    control = ControlLote()
    resultado: dict[str, Libro] = {}
    hilo = threading.Thread(
        target=lambda: resultado.setdefault(
            "libro", MotorLote(sesion, RelojReal()).ejecutar(plan, inv, lambda _e: None, control)
        ),
        daemon=True,
    )
    t0 = time.monotonic()
    hilo.start()
    pausa = None
    while hilo.is_alive() and time.monotonic() - t0 < maximo_s:
        hilo.join(0.2)
        if control.motivo_pausa is not None and pausa is None:
            pausa = control.motivo_pausa
            control.cancelar()
    assert not hilo.is_alive(), "el motor no terminó"
    return Corrida(resultado["libro"], control, pausa, time.monotonic() - t0)


def _mac_de(valor: str) -> str:
    m = re.search(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", valor)
    assert m is not None, valor
    return m.group(1).upper()


def _red_a_labnet() -> RedClon:
    """Red del clon: ``net0`` pasa de ``vmbr0`` a la VNet ``labnet`` conservando la MAC."""
    return RedClon(
        ModoRedClon.PERSONALIZAR,
        (
            TarjetaClon(
                0,
                AccionTarjeta.CAMBIAR,
                bridge="labnet",
                fijados=frozenset({CampoRed.BRIDGE}),
            ),
        ),
    )


def _firewall_grupo() -> FirewallMV:
    return FirewallMV(
        activo=True,
        grupo="lab-web",
        politica_entrada=Politica.BLOQUEAR,
        politica_salida=Politica.PERMITIR,
        dhcp=ModoDhcp.AUTO,
    )


@dataclass
class LoteApp:
    plan: Plan
    corrida: Corrida
    vmids: tuple[int, ...]
    mac_plantilla: str


def _crear_lote_app(sesion: Any, vmid_inicial: int, prefijo: str, plantilla: int) -> LoteApp:
    """Lote de 2 clones de la plantilla CirrOS: VNet ``labnet``, firewall con grupo ``lab-web``."""
    _esperar_plantilla_visible(sesion, plantilla)
    mac_plantilla = _mac_de(_root(f"sudo qm config {plantilla} | grep ^net0").split(":", 1)[1])
    cfg = _cfg_clon(
        plantilla, "plc-fc-cirros", red_clon=_red_a_labnet(), firewall=_firewall_grupo()
    )
    plan, inv = _planificar(sesion, _definicion(cfg, 2, vmid_inicial, prefijo))
    assert not plan.bloqueado, [(p.regla, p.params) for p in plan.problemas]
    corrida = _ejecutar(sesion, plan, inv)
    return LoteApp(plan, corrida, tuple(e.vmid for e in plan.elementos), mac_plantilla)


@pytest.fixture(scope="module")
def lote_app(sesion_app: Any, plantilla_cirros: int) -> Iterator[LoteApp]:
    """Lote compartido (9074, 9075) creado por la APP; se destruye al terminar el módulo."""
    lote = _crear_lote_app(sesion_app, V_LOTE, "plc-fc", plantilla_cirros)
    yield lote
    _destruir_rango()


# =============================================================================================
# LAB-C-01  Retardo de /cluster/resources para MVs recién creadas
# =============================================================================================


def test_lab_c01_resources_con_mv_recien_creada_y_el_inventario_la_tolera(
    api_app, sesion_app, plantilla_cirros, vms
):
    """[LAB] 1: la fila nueva llega con ``status: unknown`` y sin ``name``/``template``; la app lo tolera."""
    vms(V_CLON_A)
    _esperar_plantilla_visible(sesion_app, plantilla_cirros)
    cliente = sesion_app.cliente
    inventario = ServicioInventario(sesion_app, RelojReal())
    codigo = "fc01" + _etiqueta_sufijo()[:4]

    t0 = time.monotonic()
    r = api_app.pedir(
        "POST", f"/nodes/{NODO}/qemu/{plantilla_cirros}/clone", newid=V_CLON_A, name="plc-fc-c01"
    )
    assert r.ok
    exit_ = api_app.tarea(r.datos)[0]
    assert exit_ == "OK"
    t_clon = round(time.monotonic() - t0, 1)
    # etiquetas con la política por defecto (user-allow=free): se pueden poner
    assert api_app.pedir(
        "PUT", f"/nodes/{NODO}/qemu/{V_CLON_A}/config", tags=f"proxlaunch;lote-{codigo}"
    ).ok

    vistas: list[tuple[str | None, bool, bool, bool]] = []  # (estado, nombre, plantilla, etiquetas)
    primera_completa: float | None = None
    detalle_unknown: set[str] = set()
    t1 = time.monotonic()
    while time.monotonic() - t1 < 45:
        crudo = api_app.pedir("GET", "/cluster/resources", type="vm").datos
        fila = next((x for x in crudo if x.get("vmid") == V_CLON_A), None)
        recursos = {x.vmid: x for x in cliente.recursos_vm()}  # el cliente real no debe lanzar
        rec = recursos.get(V_CLON_A)
        if fila is not None and rec is not None:
            vistas.append(
                (fila.get("status"), "name" in fila, "template" in fila, bool(fila.get("tags")))
            )
            lista = inventario.listar()  # tampoco debe lanzar con filas sin nombre/estado
            lote = next((x for x in lista.lotes if x.codigo == codigo), None)
            if lote is not None and rec.estado == "unknown":
                det = inventario.detallar(lote, threading.Event(), None)
                detalle_unknown.update(str(m) for mv in det.maquinas for m in mv.motivos)
            if (
                fila.get("status") in ("stopped", "running")
                and fila.get("name")
                and fila.get("tags")
            ):
                primera_completa = round(time.monotonic() - t1, 1)
                break
        time.sleep(0.4)
    combinaciones = sorted(set(vistas), key=str)
    evidencia(
        "C01-resources",
        clon_s=t_clon,
        hasta_fila_completa_s=primera_completa,
        combinaciones_estado_nombre_plantilla_etiquetas=combinaciones,
        motivos_con_unknown=sorted(detalle_unknown),
    )
    # La app nunca lanzó y la fila acabó completa
    assert primera_completa is not None
    # Con la fila incompleta (sin etiquetas) el lote aún no es localizable; con ella, sí
    lista = inventario.listar()
    assert any(x.codigo == codigo and V_CLON_A in {r.vmid for r in x.recursos} for x in lista.lotes)
    # Si se vio la fila en «unknown», el detalle la marcó no deshacible (no la borraría a ciegas)
    if detalle_unknown:
        assert MotivoNoDeshacible.ESTADO_DESCONOCIDO.value in detalle_unknown or any(
            "estado" in m for m in detalle_unknown
        )


# =============================================================================================
# LAB-C-02  Política de etiquetas con el rol sin Sys.Audit
# =============================================================================================


def test_lab_c02_politica_de_etiquetas_sin_sys_audit(
    entorno_modulo, plantilla_cirros, sesion_app, vms
):
    """[LAB] 2: ``user-allow=list`` sin ``lote-*`` y sin ``Sys.Audit`` -> 403 con texto de ``Sys.Modify``."""
    vms(V_CLON_A, V_LOTE, V_LOTE + 1)
    _esperar_plantilla_visible(sesion_app, plantilla_cirros)
    with usuario_con(PRIVS_SIN_AUDIT, "NoAudit") as cred:
        api = ApiCruda(cred.token_id, cred.secreto)
        try:
            _root(
                "sudo pvesh set /cluster/options "
                "--user-tag-access 'user-allow=list,user-allow-list=otra;web' --registered-tags reg1"
            )
            opciones = api.pedir("GET", "/cluster/options")
            evidencia(
                "C02-GET-options-sin-sys-audit",
                estado=opciones.estado,
                claves=sorted(opciones.datos or {}),
            )
            assert opciones.ok
            assert sorted(opciones.datos) == ["allowed-tags"]  # solo la lista de permitidas
            assert "lote-" not in " ".join(opciones.datos["allowed-tags"])

            assert api.clonar(plantilla_cirros, V_CLON_A, "plc-fc-c02") == "OK"
            rechazo = api.pedir(
                "PUT", f"/nodes/{NODO}/qemu/{V_CLON_A}/config", tags="proxlaunch;lote-abcd1234"
            )
            evidencia(
                "C02-PUT-tags",
                estado=rechazo.estado,
                motivo=rechazo.motivo,
                sincrono=rechazo.datos is None,
            )
            assert rechazo.estado == 403
            # La primera etiqueta rechazada depende de las que ya existen en el servidor: con
            # alguna MV «proxlaunch» solo se rechaza «lote-…» (la lista admite las existentes)
            assert re.search(
                r"Sys\.Modify for modifying tag '(proxlaunch|lote-abcd1234)'", rechazo.motivo
            )
            assert "tags" not in api.config(V_CLON_A)  # no quedó ninguna etiqueta

            # La APP: lectura de la política con el rol sin Sys.Audit y traducción del rechazo
            with sesion_de(entorno_modulo, cred) as s:
                politica, fallida = leer_politica_etiquetas(s.cliente)
                evidencia("C02-politica-leida", fallida=fallida, politica=politica)
                assert not fallida and politica is not None
                with pytest.raises(ErrorProxLaunch) as e:
                    s.cliente.configurar_vm(NODO, V_CLON_A, {"tags": "proxlaunch;lote-abcd1234"})
                evidencia("C02-app-traduccion", codigo=str(e.value.codigo), params=e.value.params)
                assert e.value.codigo == CodigoError.ETIQUETA_RECHAZADA

                # Lote de la app: la etiqueta es rechazada, el lote se pausa (E-L15) y no sigue
                cfg = _cfg_clon(plantilla_cirros, "plc-fc-cirros")
                plan, inv = _planificar(s, _definicion(cfg, 2, V_LOTE, "plc-fc-c02l"))
                avisos = sorted({(p.regla, p.severidad.value) for p in plan.problemas})
                evidencia("C02-plan-avisos-previos", avisos=avisos)
                c = _ejecutar(s, plan, inv)
                primera = c.libro.entrada(V_LOTE)
                evidencia(
                    "C02-lote",
                    estado=primera.estado.value,
                    codigo=str(primera.error.codigo) if primera.error else None,
                    params=primera.error.params if primera.error else None,
                    pausa=str(c.pausa),
                    existentes=_existentes_en_rango(),
                    estado_segunda=c.libro.entrada(V_LOTE + 1).estado.value,
                )
                # CA-O22.5: en un clon el rechazo de la etiqueta llega en el ``PUT`` posterior: la MV
                # queda «parcial» (clonada, sin etiqueta) con la causa traducida, sin pausar el lote
                assert primera.estado == EstadoMV.PARCIAL
                assert primera.error is not None
                assert primera.error.codigo == CodigoError.AJUSTE_POST_CLON_FALLIDO
                assert primera.error.params.get("causa") == str(CodigoError.ETIQUETA_RECHAZADA)
                assert {V_LOTE, V_LOTE + 1} <= set(_existentes_en_rango())
                assert "tags" not in api.config(V_LOTE)  # sin etiqueta: el inventario no la verá
        finally:
            _root(
                "sudo pvesh set /cluster/options --delete user-tag-access,registered-tags",
                comprobar=False,
            )
    assert "user-tag-access" not in _opciones_dc()


def _plan_con_politica_list(sesion: Any, plantilla: int) -> Plan:
    plan, _inv = _planificar(
        sesion, _definicion(_cfg_clon(plantilla, "plc-fc-cirros"), 2, V_LOTE, "plc-fc-c02p")
    )
    return plan


def test_lab_c02_con_sys_audit_el_plan_avisa_de_la_etiqueta_del_lote(
    entorno_modulo, plantilla_cirros, sesion_app, cred_app
):
    """Con ``Sys.Audit`` la política se lee completa; evidencia de lo que avisa el plan (V-A03)."""
    _esperar_plantilla_visible(sesion_app, plantilla_cirros)
    try:
        _root(
            "sudo pvesh set /cluster/options "
            "--user-tag-access 'user-allow=list,user-allow-list=otra;web'"
        )
        with sesion_de(entorno_modulo, cred_app) as s:
            politica, fallida = leer_politica_etiquetas(s.cliente)
            plan = _plan_con_politica_list(s, plantilla_cirros)
            avisos = sorted((p.regla, p.severidad.value, str(p.params)) for p in plan.problemas)
            evidencia("C02-con-sys-audit", politica=politica, fallida=fallida, plan=avisos)
            assert not fallida and politica is not None
            assert politica.permiso == "list"
    finally:
        _root("sudo pvesh set /cluster/options --delete user-tag-access", comprobar=False)


def test_lab_c02_sin_sys_audit_la_politica_parcial_no_se_da_por_libre(
    entorno_modulo, plantilla_cirros, sesion_app, vms
):
    """Una respuesta sin ``user-tag-access`` ni ``mac_prefix`` (parcial) no debería leerse como «free»."""
    vms(V_LOTE, V_LOTE + 1)
    _esperar_plantilla_visible(sesion_app, plantilla_cirros)
    with usuario_con(PRIVS_SIN_AUDIT, "NoAud2") as cred:
        try:
            _root(
                "sudo pvesh set /cluster/options "
                "--user-tag-access 'user-allow=list,user-allow-list=otra;web'"
            )
            with sesion_de(entorno_modulo, cred) as s:
                politica, fallida = leer_politica_etiquetas(s.cliente)
                plan = _plan_con_politica_list(s, plantilla_cirros)
                reglas = {p.regla for p in plan.problemas}
                evidencia(
                    "C02-parcial",
                    permiso=politica.permiso if politica else None,
                    plan=sorted(reglas),
                )
                # esperado: o no se da por «free» o el plan avisa de que no pudo comprobarla
                assert (
                    fallida
                    or (politica is not None and politica.permiso != "free")
                    or (reglas & {"V-A09", "V-A03"})
                )
        finally:
            _root("sudo pvesh set /cluster/options --delete user-tag-access", comprobar=False)


# =============================================================================================
# LAB-C-03  ?type=any_bridge
# =============================================================================================


@pytest.mark.parametrize(
    ("etiqueta", "sdn_en", "esperadas"),
    [
        ("Raiz", ("/",), {"labnet", "labv20"}),
        ("Zona", ("/sdn/zones/labzona",), {"labnet"}),
        ("Vnet", ("/sdn/zones/labvlan/labv20",), {"labv20"}),
        ("Nada", (), set()),
    ],
)
def test_lab_c03_any_bridge_segun_donde_este_sdn_use(entorno_modulo, etiqueta, sdn_en, esperadas):
    """[LAB] 3: ``any_bridge`` lista las VNets con ``SDN.Use`` heredado en la zona (o en la propia VNet)."""
    privs = PRIVS_SIN_SDN + (("SDN.Use",) if sdn_en == ("/",) else ())
    rutas = () if sdn_en == ("/",) else sdn_en
    with usuario_con(privs, f"Br{etiqueta}", sdn_en=rutas) as cred:
        api = ApiCruda(cred.token_id, cred.secreto)
        r = api.pedir("GET", f"/nodes/{NODO}/network", type="any_bridge")
        assert r.ok
        vnets = {e["iface"]: e for e in r.datos if e.get("type") == "vnet"}
        evidencia(
            "C03-any_bridge",
            acl=sdn_en,
            tipos={e["iface"]: e.get("type") for e in r.datos},
            campos_vnet={k: sorted(v) for k, v in vnets.items()},
            comentarios={k: v.get("comments") for k, v in vnets.items()},
            vlanaware={k: v.get("vlanaware") for k, v in vnets.items()},
        )
        assert set(vnets) == esperadas
        for v in vnets.values():
            assert {"iface", "type", "vlanaware", "comments"} <= set(v)
        with sesion_de(entorno_modulo, cred) as s:
            redes = {n.nombre: n for n in s.cliente.redes_any_bridge(NODO)}
            evidencia(
                "C03-app",
                redes={k: (v.alias, v.vlan_aware, v.tipo_declarado) for k, v in redes.items()},
            )
            assert set(redes) == esperadas
            if "labnet" in redes:
                assert redes["labnet"].alias == "Red de laboratorio"
                assert redes["labnet"].tipo_declarado and not redes["labnet"].vlan_aware
            inv = descubrir(s)
            assert {n.nombre for n in inv.redes_sdn.get(NODO, ())} == esperadas
            assert not inv.errores_sdn
            # los bridges locales no se mezclan con las VNets
            assert not ({b.nombre for b in inv.bridges[NODO]} & BASE_VNETS)


# =============================================================================================
# LAB-C-04  Arranque con VLAN en una VNet no vlanaware
# =============================================================================================


def test_lab_c04_arranque_con_vlan_en_vnet_no_vlanaware(entorno_modulo, plantilla_cirros, vms):
    """[LAB] 4: el ``PUT`` acepta ``tag`` en una VNet sin vlanaware; el arranque falla con un texto fijo."""
    vms(V_CLON_A)
    with usuario_con(ROL_PROXLAUNCH + ("VM.PowerMgmt",), "Arr") as cred:
        api = ApiCruda(cred.token_id, cred.secreto)
        assert api.clonar(plantilla_cirros, V_CLON_A, "plc-fc-c04") == "OK"
        mac = _mac_de(api.config(V_CLON_A)["net0"])
        mensajes: dict[str, str] = {}
        for red in ("labnet", "labv20"):
            put = api.pedir(
                "PUT",
                f"/nodes/{NODO}/qemu/{V_CLON_A}/config",
                net0=f"virtio={mac},bridge={red},tag=30",
            )
            assert put.ok, (put.estado, put.motivo)  # el PUT no lo detecta
            inicio = api.pedir("POST", f"/nodes/{NODO}/qemu/{V_CLON_A}/status/start")
            assert inicio.ok
            exit_, log = api.tarea(inicio.datos)
            mensajes[red] = log[0] if log else ""
            evidencia("C04-arranque", red=red, exitstatus=exit_, primera_linea=log[:1])
            assert exit_ != "OK"
            assert f"vm vlans are not allowed on vnet {red}" in log[0]
        # sin VLAN arranca
        assert api.pedir(
            "PUT", f"/nodes/{NODO}/qemu/{V_CLON_A}/config", net0=f"virtio={mac},bridge=labnet"
        ).ok
        inicio = api.pedir("POST", f"/nodes/{NODO}/qemu/{V_CLON_A}/status/start")
        assert api.tarea(inicio.datos)[0] == "OK"
        _root(f"sudo qm stop {V_CLON_A} --skiplock 1", comprobar=False)

        # La APP no deja llegar ahí: V-C10 con la VNet leída de any_bridge
        with sesion_de(entorno_modulo, cred) as s:
            _esperar_plantilla_visible(s, plantilla_cirros)
            red = RedClon(
                ModoRedClon.PERSONALIZAR,
                (
                    TarjetaClon(
                        0,
                        AccionTarjeta.CAMBIAR,
                        bridge="labnet",
                        vlan=30,
                        fijados=frozenset({CampoRed.BRIDGE, CampoRed.VLAN}),
                    ),
                ),
            )
            plan, _inv = _planificar(
                s,
                _definicion(
                    _cfg_clon(plantilla_cirros, "plc-fc-cirros", red_clon=red),
                    1,
                    V_VARIOS,
                    "plc-fc-c04v",
                ),
            )
            reglas = sorted({(p.regla, p.severidad.value) for p in plan.problemas})
            evidencia("C04-app-validacion", problemas=reglas, bloqueado=plan.bloqueado)
            assert plan.bloqueado
            assert any(p.regla == "V-C10" for p in plan.problemas)
    evidencia("C04-vnet-fuera-del-nodo", viable=False, motivo="el laboratorio es un nodo suelto")


# =============================================================================================
# LAB-C-05 / 07 / 11  Firewall y red del clon, tal como los deja la APP
# =============================================================================================


def test_lab_c05_firewall_policy_in_drop_tal_como_lo_deja_la_app(lote_app):
    """[LAB] 5: opciones y reglas de cada clon del lote; DHCP no se puede comprobar sin red."""
    corrida = lote_app.corrida
    estados = {v: corrida.libro.entrada(v).estado for v in lote_app.vmids}
    assert set(estados.values()) <= {EstadoMV.OK, EstadoMV.CON_AVISOS}, (
        estados,
        [corrida.libro.entrada(v).error for v in lote_app.vmids],
    )
    for vmid in lote_app.vmids:
        fw = _root(f"sudo cat /etc/pve/firewall/{vmid}.fw")
        opciones = json.loads(
            _root(f"sudo pvesh get /nodes/{NODO}/qemu/{vmid}/firewall/options --output-format json")
        )
        reglas = json.loads(
            _root(f"sudo pvesh get /nodes/{NODO}/qemu/{vmid}/firewall/rules --output-format json")
        )
        config = json.loads(
            _root(f"sudo pvesh get /nodes/{NODO}/qemu/{vmid}/config --output-format json")
        )
        evidencia(
            "C05-firewall",
            vmid=vmid,
            opciones={k: v for k, v in opciones.items() if k != "digest"},
            reglas=[{k: v for k, v in r.items() if k != "digest"} for r in reglas],
            net0=config["net0"],
            fichero_fw=fw.replace("\n", "|"),
        )
        assert opciones["enable"] == 1
        assert opciones["policy_in"] == "DROP"
        assert opciones.get("policy_out", "ACCEPT") == "ACCEPT"
        assert "firewall=1" in config["net0"]
        assert [(r["type"], r["action"]) for r in reglas] == [("group", "lab-web")]
    evidencia(
        "C05-dhcp",
        comprobado=False,
        motivo="sin red hacia el invitado no se puede verificar que sin dhcp=1 no haya IP; "
        "solo se confirma la opción escrita",
        dhcp_en_opciones=[
            json.loads(
                _root(
                    f"sudo pvesh get /nodes/{NODO}/qemu/{v}/firewall/options --output-format json"
                )
            ).get("dhcp")
            for v in lote_app.vmids
        ],
    )


def test_lab_c11_regla_de_grupo_sin_iface_para_todas_las_tarjetas(
    lote_app, api_app, plantilla_cirros, vms
):
    """[LAB] 11: ``type=group`` sin ``iface`` se guarda sin ``-i``: vale para todas las tarjetas."""
    for vmid in lote_app.vmids:
        reglas = json.loads(
            _root(f"sudo pvesh get /nodes/{NODO}/qemu/{vmid}/firewall/rules --output-format json")
        )
        assert reglas and all("iface" not in r for r in reglas), reglas
        linea = next(
            x
            for x in _root(f"sudo cat /etc/pve/firewall/{vmid}.fw").splitlines()
            if x.startswith("GROUP")
        )
        evidencia("C11-app", vmid=vmid, linea_fw=linea)
        assert "-i" not in linea.split("#")[0].split()

    # Control con la API cruda sobre una MV de dos tarjetas
    vms(V_CLON_B)
    _crear_plantilla_vacia(
        V_PLANT_RED, "plc-fc-red2", "--net0 virtio,bridge=labnet --net1 virtio,bridge=vmbr0"
    )
    vms(V_PLANT_RED)
    assert api_app.clonar(V_PLANT_RED, V_CLON_B, "plc-fc-c11") == "OK"
    r = api_app.pedir(
        "POST",
        f"/nodes/{NODO}/qemu/{V_CLON_B}/firewall/rules",
        type="group",
        action="lab-web",
        enable=1,
    )
    assert r.ok
    fw = _root(f"sudo cat /etc/pve/firewall/{V_CLON_B}.fw")
    evidencia("C11-cruda", fichero_fw=fw.replace("\n", "|"))
    assert "GROUP lab-web" in fw and " -i " not in fw
    # Hallazgo (no hay xfail: la app valida antes): Proxmox acepta un grupo que no existe
    inexistente = api_app.pedir(
        "POST",
        f"/nodes/{NODO}/qemu/{V_CLON_B}/firewall/rules",
        type="group",
        action="grupo-no-existe",
        enable=1,
    )
    evidencia("C11-grupo-inexistente", estado=inexistente.estado, motivo=inexistente.motivo)
    assert inexistente.ok  # supuesto de la arquitectura («400/404 = grupo inexistente») FALSO


def test_lab_c07_mac_al_reescribir_net_en_la_api_cruda(api_app, plantilla_cirros, vms):
    """[LAB] 7: ``PUT net0`` sin MAC genera una MAC nueva; reenviándola se conserva."""
    vms(V_CLON_A)
    assert api_app.clonar(plantilla_cirros, V_CLON_A, "plc-fc-c07") == "OK"
    original = _mac_de(api_app.config(V_CLON_A)["net0"])
    assert original != _mac_de(
        _root(f"sudo qm config {plantilla_cirros} | grep ^net0")
    )  # el clon ya trae MAC nueva
    assert api_app.pedir(
        "PUT", f"/nodes/{NODO}/qemu/{V_CLON_A}/config", net0="virtio,bridge=labnet"
    ).ok
    sin_mac = _mac_de(api_app.config(V_CLON_A)["net0"])
    assert api_app.pedir(
        "PUT", f"/nodes/{NODO}/qemu/{V_CLON_A}/config", net0=f"virtio={original},bridge=labnet"
    ).ok
    con_mac = _mac_de(api_app.config(V_CLON_A)["net0"])
    evidencia("C07-cruda", original=original, tras_put_sin_mac=sin_mac, tras_put_con_mac=con_mac)
    assert sin_mac != original
    assert con_mac == original


def test_lab_c07_la_red_del_clon_de_la_app_conserva_la_mac(lote_app):
    """[LAB] 7 (APP): ``vmbr0`` -> ``labnet`` en cada clon con la MAC que Proxmox le dio al clonar."""
    for vmid in lote_app.vmids:
        entrada = lote_app.corrida.libro.entrada(vmid)
        config = json.loads(
            _root(f"sudo pvesh get /nodes/{NODO}/qemu/{vmid}/config --output-format json")
        )
        mac_final = _mac_de(config["net0"])
        macs_originales = dict(entrada.macs_originales)
        evidencia(
            "C07-app",
            vmid=vmid,
            net0=config["net0"],
            mac_plantilla=lote_app.mac_plantilla,
            mac_original_del_clon=macs_originales.get(0),
            red_final=[
                (t.indice, t.accion.value, t.red, t.mac_conservada) for t in entrada.red_final
            ],
            avisos=entrada.avisos,
        )
        assert "bridge=labnet" in config["net0"]
        assert mac_final != lote_app.mac_plantilla
        assert macs_originales.get(0) == mac_final  # la MAC no cambió al reescribir la tarjeta
        assert all(t.mac_conservada for t in entrada.red_final)
        assert not any(a.startswith("red_mac_nueva") for a in entrada.avisos)


# =============================================================================================
# LAB-C-06  clone_vmfw_conf
# =============================================================================================


def test_lab_c06_el_clon_hereda_el_firewall_y_delete_borra_el_fw_sin_purge(api_app, vms):
    """[LAB] 6: ``<vmid>.fw`` de la plantilla se copia al clon y ``DELETE`` sin ``purge`` lo borra."""
    vms(V_CLON_FW, V_PLANT_FW)
    _crear_plantilla_vacia(V_PLANT_FW, "plc-fc-fw", "--net0 virtio,bridge=labnet")
    _root(
        f"sudo pvesh set /nodes/{NODO}/qemu/{V_PLANT_FW}/firewall/options --enable 1 --policy_in DROP --dhcp 1 "
        f"&& sudo pvesh create /nodes/{NODO}/qemu/{V_PLANT_FW}/firewall/rules "
        "--type in --action ACCEPT --proto tcp --dport 22 --enable 1 --comment plantilla"
    )
    assert api_app.clonar(V_PLANT_FW, V_CLON_FW, "plc-fc-c06") == "OK"
    fw_clon = _root(f"sudo cat /etc/pve/firewall/{V_CLON_FW}.fw")
    opciones = api_app.pedir("GET", f"/nodes/{NODO}/qemu/{V_CLON_FW}/firewall/options").datos
    evidencia("C06-clon", fichero_fw=fw_clon.replace("\n", "|"), enable=opciones.get("enable"))
    assert opciones["enable"] == 1 and opciones["policy_in"] == "DROP"
    assert "IN ACCEPT -p tcp -dport 22 # plantilla" in fw_clon

    borrado = api_app.pedir("DELETE", f"/nodes/{NODO}/qemu/{V_CLON_FW}")  # sin purge
    assert borrado.ok
    assert api_app.tarea(borrado.datos)[0] == "OK"
    quedan = _root("ls /etc/pve/firewall/").split()
    evidencia("C06-delete-sin-purge", ficheros_fw=quedan)
    assert f"{V_CLON_FW}.fw" not in quedan
    assert f"{V_PLANT_FW}.fw" in quedan  # la de la plantilla sigue


# =============================================================================================
# LAB-C-08  IPAM/DHCP de SDN
# =============================================================================================


def test_lab_c08_ipam_clon_y_cambio_de_bridge(
    entorno_modulo, cred_app, sesion_app, plantilla_cirros, vms
):
    """[LAB] 8 (parcial): zona con IPAM ``pve`` y subred; DHCP exige dnsmasq, que el laboratorio no trae."""
    vms(V_CLON_A)
    dnsmasq = _root("dpkg -s dnsmasq 2>&1 | head -1", comprobar=False).strip()
    evidencia("C08-dnsmasq", estado=dnsmasq, dhcp_viable=False)
    try:
        _root(
            "sudo pvesh create /cluster/sdn/zones --zone labipam --type simple --ipam pve "
            "&& sudo pvesh create /cluster/sdn/vnets --vnet labip1 --zone labipam "
            "&& sudo pvesh create /cluster/sdn/vnets --vnet labip2 --zone labipam "
            "&& sudo pvesh create /cluster/sdn/vnets/labip1/subnets --subnet 10.77.1.0/24 --type subnet --gateway 10.77.1.1 "
            "&& sudo pvesh create /cluster/sdn/vnets/labip2/subnets --subnet 10.77.2.0/24 --type subnet --gateway 10.77.2.1"
        )
        _aplicar_sdn()
        _esperar_plantilla_visible(sesion_app, plantilla_cirros)
        with sesion_de(entorno_modulo, cred_app) as s:
            redes = {n.nombre: n for n in s.cliente.redes_any_bridge(NODO)}
            evidencia(
                "C08-any_bridge",
                ipam={k: v.ipam for k, v in redes.items() if k.startswith("labip")},
            )
            assert {"labip1", "labip2"} <= set(redes)
            api = ApiCruda(cred_app.token_id, cred_app.secreto)
            assert api.clonar(plantilla_cirros, V_CLON_A, "plc-fc-c08") == "OK"
            mac = _mac_de(api.config(V_CLON_A)["net0"])
            for red in ("labip1", "labip2"):
                s.cliente.configurar_vm(NODO, V_CLON_A, {"net0": f"virtio={mac},bridge={red}"})
            final = api.config(V_CLON_A)["net0"]
            estado_ipam = _root(
                "sudo pvesh get /cluster/sdn/ipams/pve/status --output-format json", comprobar=False
            )
            evidencia("C08-clon", net0=final, ipam_pve_status=estado_ipam.replace("\n", " ")[:300])
            assert _mac_de(final) == mac and "bridge=labip2" in final
    finally:
        for vnet in ("labip1", "labip2"):
            _borrar_vnet(vnet)
        _root("sudo pvesh delete /cluster/sdn/zones/labipam >/dev/null 2>&1; true", comprobar=False)
        _aplicar_sdn()
        _root(
            "sudo ip link del labip1 >/dev/null 2>&1; sudo ip link del labip2 >/dev/null 2>&1; true",
            comprobar=False,
        )
    assert not ({"labip1", "labip2"} & _vnets_existentes())


# =============================================================================================
# LAB-C-09  VNet pendiente de aplicar
# =============================================================================================


def test_lab_c09_vnet_pendiente_de_aplicar(entorno_modulo, cred_app, plantilla_cirros, vms):
    """[LAB] 9: ``any_bridge`` no la lista; ``PUT config`` pasa y el arranque falla."""
    vms(V_CLON_A)
    with usuario_con(ROL_PROXLAUNCH + ("VM.PowerMgmt",), "Pend") as cred:
        api = ApiCruda(cred.token_id, cred.secreto)
        try:
            _root("sudo pvesh create /cluster/sdn/vnets --vnet labpend --zone labzona")
            pendientes = json.loads(
                _root("sudo pvesh get /cluster/sdn/vnets --pending 1 --output-format json")
            )
            estado = next((v.get("state") for v in pendientes if v["vnet"] == "labpend"), None)
            any_bridge = api.pedir("GET", f"/nodes/{NODO}/network", type="any_bridge").datos
            listada = "labpend" in {e["iface"] for e in any_bridge}
            assert api.clonar(plantilla_cirros, V_CLON_A, "plc-fc-c09") == "OK"
            mac = _mac_de(api.config(V_CLON_A)["net0"])
            put = api.pedir(
                "PUT", f"/nodes/{NODO}/qemu/{V_CLON_A}/config", net0=f"virtio={mac},bridge=labpend"
            )
            inicio = api.pedir("POST", f"/nodes/{NODO}/qemu/{V_CLON_A}/status/start")
            exit_, log = (
                api.tarea(inicio.datos) if inicio.ok else (f"HTTP {inicio.estado}", [inicio.motivo])
            )
            evidencia(
                "C09-vnet-pendiente",
                estado_en_cluster=estado,
                en_any_bridge=listada,
                put_estado=put.estado,
                put_motivo=put.motivo,
                arranque_exit=exit_,
                arranque_log=log[:2],
            )
            assert not listada
            assert put.ok  # check_vnet_access usa la config pendiente
            assert exit_ != "OK"
            with sesion_de(entorno_modulo, cred) as s:
                # la app no la ofrece: no está en el inventario de VNets del nodo
                assert "labpend" not in {n.nombre for n in descubrir(s).redes_sdn.get(NODO, ())}
        finally:
            _root("sudo qm stop 9071 --skiplock 1 >/dev/null 2>&1; true", comprobar=False)
            _root(
                "sudo pvesh delete /cluster/sdn/vnets/labpend >/dev/null 2>&1; true",
                comprobar=False,
            )
            _aplicar_sdn()
    assert "labpend" not in _vnets_existentes()


# =============================================================================================
# LAB-C-10  403 por SDN.Use en el bridge de la plantilla / antiguo / nuevo
# =============================================================================================


def test_lab_c10_403_sin_sdn_use_en_el_bridge_de_la_plantilla(
    entorno_modulo, plantilla_cirros, vms
):
    """[LAB] 10 (plantilla): el ``clone`` da 403 por la VNet de la plantilla; la app lo etiqueta ``lado=plantilla``."""
    vms(V_CLON_A, V_PLANT_RED)
    _crear_plantilla_vacia(V_PLANT_RED, "plc-fc-red", "--net0 virtio,bridge=labnet")
    with usuario_con(PRIVS_SIN_SDN, "S403", sdn_en=("/sdn/zones/localnetwork",)) as cred:
        api = ApiCruda(cred.token_id, cred.secreto)
        r = api.pedir(
            "POST", f"/nodes/{NODO}/qemu/{V_PLANT_RED}/clone", newid=V_CLON_A, name="plc-fc-c10"
        )
        evidencia("C10-clone", estado=r.estado, motivo=r.motivo, sincrono=r.datos is None)
        assert r.estado == 403
        assert "/sdn/zones/labzona/labnet, SDN.Use" in r.motivo
        assert V_CLON_A not in _existentes_en_rango()
        with sesion_de(entorno_modulo, cred) as s:
            with pytest.raises(ErrorProxLaunch) as e:
                s.cliente.clonar_vm(
                    NODO, V_PLANT_RED, {"newid": str(V_CLON_A), "name": "plc-fc-c10"}
                )
            anotado = anotar_error_red(e.value, paso="clon", antiguas={0: "labnet"}, nuevas={})
            evidencia("C10-app", codigo=str(anotado.codigo), params=anotado.params)
            assert anotado.codigo == CodigoError.PERMISO_INSUFICIENTE
            assert anotado.params["privilegio"] == "SDN.Use"
            assert anotado.params["zona"] == "labzona" and anotado.params["red"] == "labnet"
            assert anotado.params["lado"] == "plantilla" and anotado.params["tarjeta"] == "net0"


def test_lab_c10_403_del_bridge_nuevo_y_del_antiguo_en_el_put(
    entorno_modulo, plantilla_cirros, vms
):
    """[LAB] 10 (PUT): quién da el 403 primero cuando faltan el bridge nuevo, el antiguo o ambos."""
    vms(V_CLON_A)
    # El clon se crea como root (la plantilla usa vmbr0) para que el usuario no necesite SDN.Use en él
    _root(f"sudo qm clone {plantilla_cirros} {V_CLON_A} --name plc-fc-c10b", timeout=300)
    mac = _mac_de(_root(f"sudo qm config {V_CLON_A} | grep ^net0").split(":", 1)[1])
    casos: dict[str, tuple[tuple[str, ...], str]] = {
        # (donde tiene SDN.Use, bridge nuevo)
        "falta_nuevo": (("/sdn/zones/localnetwork",), "labnet"),
        "falta_antiguo": (("/sdn/zones/labzona",), "labnet"),
        "faltan_ambos": ((), "labnet"),
    }
    resultados: dict[str, str] = {}
    for caso, (rutas, nuevo) in casos.items():
        with usuario_con(PRIVS_SIN_SDN, "P" + caso.replace("_", "")[:8], sdn_en=rutas) as cred:
            api = ApiCruda(cred.token_id, cred.secreto)
            r = api.pedir(
                "PUT", f"/nodes/{NODO}/qemu/{V_CLON_A}/config", net0=f"virtio={mac},bridge={nuevo}"
            )
            resultados[caso] = f"{r.estado} {r.motivo}"
            with sesion_de(entorno_modulo, cred) as s:
                try:
                    s.cliente.configurar_vm(
                        NODO, V_CLON_A, {"net0": f"virtio={mac},bridge={nuevo}"}
                    )
                    anotado = None
                except ErrorProxLaunch as e:
                    anotado = anotar_error_red(
                        e, paso="red", antiguas={0: "vmbr0"}, nuevas={0: nuevo}
                    )
            evidencia(
                "C10-put",
                caso=caso,
                http=resultados[caso],
                app=None if anotado is None else (str(anotado.codigo), anotado.params),
            )
            assert r.estado == 403, (caso, r.estado, r.motivo)
            assert "SDN.Use" in r.motivo
    # Con ambos ausentes el mensaje dice cuál de las dos rutas se exige primero (en evidencia)
    assert (
        _mac_de(
            json.loads(
                _root(f"sudo pvesh get /nodes/{NODO}/qemu/{V_CLON_A}/config --output-format json")
            )["net0"]
        )
        == mac
    )


# =============================================================================================
# LAB-C-12  GET …/firewall/options y de grupos sin Sys.Audit
# =============================================================================================


def test_lab_c12_lecturas_de_firewall_sin_sys_audit(entorno_modulo, plantilla_cirros, vms):
    """[LAB] 12: las opciones de la MV/plantilla se leen con ``VM.Audit``; grupo y datacenter dan 403."""
    vms(V_PLANT_FW)
    _crear_plantilla_vacia(V_PLANT_FW, "plc-fc-c12", "--net0 virtio,bridge=labnet")
    with usuario_con(PRIVS_SIN_AUDIT, "NoAud12") as cred:
        api = ApiCruda(cred.token_id, cred.secreto)
        vm = api.pedir("GET", f"/nodes/{NODO}/qemu/{V_PLANT_FW}/firewall/options")
        grupos = api.pedir("GET", "/cluster/firewall/groups")
        grupo = api.pedir("GET", "/cluster/firewall/groups/lab-web")
        dc = api.pedir("GET", "/cluster/firewall/options")
        evidencia(
            "C12",
            opciones_plantilla=(vm.estado, vm.motivo),
            listar_grupos=(grupos.estado, [g["group"] for g in grupos.datos or []]),
            reglas_del_grupo=(grupo.estado, grupo.motivo),
            opciones_datacenter=(dc.estado, dc.motivo),
        )
        assert vm.ok  # supuesto de la lista [LAB] 12 («403 en las opciones de la plantilla») FALSO
        assert grupos.ok and [g["group"] for g in grupos.datos] == ["lab-web"]
        assert grupo.estado == 403 and "Permission check failed (/, Sys.Audit)" in grupo.motivo
        assert dc.estado == 403 and "Permission check failed (/, Sys.Audit)" in dc.motivo
        with sesion_de(entorno_modulo, cred) as s:
            assert s.cliente.opciones_firewall_vm(NODO, V_PLANT_FW) is not None
            assert [g.nombre for g in s.cliente.grupos_firewall()] == ["lab-web"]
            for llamada in (
                lambda: s.cliente.reglas_grupo_firewall("lab-web"),
                s.cliente.opciones_firewall_cluster,
            ):
                with pytest.raises(ErrorProxLaunch) as e:
                    llamada()
                evidencia("C12-app", codigo=str(e.value.codigo), params=e.value.params)
                assert e.value.codigo == CodigoError.PERMISO_INSUFICIENTE
                assert e.value.params.get("privilegio") == "Sys.Audit"


# =============================================================================================
# Extremo a extremo: lote de 2 clones -> inventario «Lotes en el servidor» -> Deshacer
# =============================================================================================


def test_lab_c_e2e_lote_inventario_y_deshacer_con_doble_control(sesion_app, plantilla_cirros, vms):
    """Lote de 2 clones (VNet ``labnet``, firewall ``lab-web``, MAC conservada) -> inventario -> Deshacer."""
    vms(V_E2E, V_E2E + 1)
    lote = _crear_lote_app(sesion_app, V_E2E, "plc-fce2e", plantilla_cirros)
    libro = lote.corrida.libro
    assert {libro.entrada(v).estado for v in lote.vmids} <= {EstadoMV.OK, EstadoMV.CON_AVISOS}
    codigo = libro.id_lote

    inventario = ServicioInventario(sesion_app, RelojReal())
    # /cluster/resources publica etiquetas y estado con retraso (pvestatd): como haría el usuario
    # con «Recargar», se relee hasta que el lote esté localizable y sus MVs no estén en «unknown»
    t0 = time.monotonic()
    encontrado = None
    detalle = None
    primera_vez: float | None = None
    estados_vistos: list[tuple[float, list[tuple[int, str | None, list[str]]]]] = []
    while time.monotonic() - t0 < 90:
        listado = inventario.listar()
        encontrado = next((x for x in listado.lotes if x.codigo == codigo), None)
        if encontrado is not None and {r.vmid for r in encontrado.recursos} == set(lote.vmids):
            primera_vez = primera_vez if primera_vez is not None else time.monotonic() - t0
            detalle = inventario.detallar(encontrado, threading.Event(), None)
            estados_vistos.append(
                (
                    round(time.monotonic() - t0, 1),
                    [
                        (m.recurso.vmid, m.recurso.estado, [str(x) for x in m.motivos])
                        for m in detalle.maquinas
                    ],
                )
            )
            if all(m.deshacible for m in detalle.maquinas):
                break
        time.sleep(1)
    evidencia(
        "E2E-detalle",
        lote=codigo,
        localizable_tras_s=None if primera_vez is None else round(primera_vez, 1),
        lecturas=estados_vistos[:1] + estados_vistos[-1:],
    )
    assert encontrado is not None, "el inventario no encontró el lote por etiqueta"
    assert encontrado.valido and encontrado.de_proxlaunch
    assert detalle is not None and detalle.completo
    assert all(m.deshacible for m in detalle.maquinas), estados_vistos[-1]

    marcadas = set(lote.vmids)
    inspeccion = inventario.inspeccionar(detalle, marcadas, None)
    evidencia("E2E-inspeccion", inspeccion=inspeccion)
    resultados = inventario.deshacer(
        detalle,
        marcadas,
        lambda _r: None,
        ControlLote(),
        forzar_apagado=frozenset(),
        forzar_desproteccion=frozenset(),
        permisos=None,
    )
    evidencia("E2E-deshacer", resultados=[(r.vmid, r.estado.value) for r in resultados])
    assert {r.estado for r in resultados} == {EstadoRollback.ELIMINADA}
    assert not (set(lote.vmids) & set(_existentes_en_rango()))
    quedan = _root("ls /etc/pve/firewall/").split()
    assert not any(f"{v}.fw" in quedan for v in lote.vmids)  # el DELETE de la app borró los .fw
    # la plantilla sigue donde estaba
    assert V_PLANTILLA in _existentes_en_rango()
