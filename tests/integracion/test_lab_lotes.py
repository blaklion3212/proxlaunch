"""Lotes (MVP 2) contra el laboratorio real: LAB-L01..LAB-L13 de docs/requisitos/mvp2.md §10.

Derivadas de los requisitos RF-L* / CA-L* y de las interfaces públicas (Planificador, simular,
MotorLote, ServicioRollback, construir_informe, ClienteProxmox). Solo VMIDs 9000-9099 y solo el
laboratorio local (127.0.0.1:8006, nodo pve-lab). Todo lo que se cambia en el laboratorio
(storage temporal, ``user-tag-access``, protección, bloqueos, usuarios y roles) se revierte.

Las pruebas imprimen líneas ``EVIDENCIA[...]`` (visibles con ``-s``) con las medidas reales
que responden a las preguntas [LAB] del requisito.
"""

from __future__ import annotations

import contextlib
import re
import secrets
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

import pytest
import requests

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.informe import construir_informe
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    CandidatoRollback,
    DefinicionLote,
    EstadoMV,
    EstadoRollback,
    MetadatosInforme,
    MotivoNoEnviada,
    PatronNombres,
    Plan,
    ResultadoRollback,
)
from proxlaunch.nucleo.lote.motor import ControlLote, MotorLote
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, Firmware, InterfazRed
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.servicios.descubrimiento import descubrir

from . import apoyo_lab as lab

pytestmark = [
    pytest.mark.integracion,
    pytest.mark.filterwarnings("ignore::urllib3.exceptions.InsecureRequestWarning"),
]

STORAGE = "lab-lvmthin"
URL = f"https://{lab.HOST}:{lab.PUERTO}/api2/json"
LOG_ACCESO = "/var/log/pveproxy/access.log"


def evidencia(clave: str, **datos: Any) -> None:
    detalle = " ".join(f"{k}={v!r}" for k, v in datos.items())
    print(f"EVIDENCIA[{clave}] {detalle}")


# --- Apoyo: limpieza, usuarios temporales, API cruda ------------------------------------


def _limpiar(vmids: list[int]) -> None:
    """Desbloquea, desprotege, detiene y destruye (con discos) MVs del rango de pruebas."""
    for v in vmids:
        if not lab.VMID_MIN <= v <= lab.VMID_MAX:
            raise RuntimeError(f"VMID fuera del rango de pruebas: {v}")
    if not vmids:
        return
    ordenes = "; ".join(
        f"sudo qm unlock {v}; sudo qm set {v} --protection 0; sudo qm stop {v} --skiplock 1; "
        f"sudo qm destroy {v} --purge 1 --skiplock 1 --destroy-unreferenced-disks 1; "
        f"for s in {STORAGE} local; do for vol in $(sudo pvesm list $s --vmid {v} | "
        "awk 'NR>1{print $1}'); do sudo pvesm free $vol; done; done"
        for v in vmids
    )
    lab.ssh(f"({ordenes}) >/dev/null 2>&1; true", comprobar=False, timeout=600)


@pytest.fixture
def vmids() -> Iterator[Callable[..., Any]]:
    """Registra VMIDs de prueba (9000-9099); se destruyen al terminar la prueba."""
    creados: list[int] = []

    def registrar(*ids: int) -> Any:
        creados.extend(ids)
        return ids[0] if len(ids) == 1 else ids

    yield registrar
    _limpiar(sorted(set(creados)))


@dataclass(frozen=True)
class Usuario:
    userid: str
    token_id: str
    token_secreto: str


@contextlib.contextmanager
def usuario_temporal(privilegios: tuple[str, ...], ruta: str = "/") -> Iterator[Usuario]:
    """Rol + usuario + token (privsep=0) temporales; se borran al salir."""
    sufijo = secrets.token_hex(3)
    rol = f"PLCTmp{sufijo}"
    userid = f"plct{sufijo}@pve"
    lab.crear_rol(privilegios, rol)
    try:
        lab.crear_usuario(userid, lab.nuevo_secreto(), rol, ruta)
        completo = lab.crear_token(userid, "t1", privsep=0)
        token_id, secreto = completo.rsplit("=", 1)
        yield Usuario(userid, token_id, secreto)
    finally:
        lab.borrar_usuario(userid)
        lab.borrar_rol(rol)


class ApiCruda:
    """Peticiones HTTP directas con un token (solo 127.0.0.1:8006)."""

    def __init__(self, token_id: str, secreto: str) -> None:
        lab.comprobar_destino(lab.HOST, lab.PUERTO, lab.NODO)
        self._cab = {"Authorization": f"PVEAPIToken={token_id}={secreto}"}

    def pedir(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
    ) -> requests.Response:
        return requests.request(
            metodo,
            URL + ruta,
            headers=self._cab,
            params=params,
            data=datos,
            verify=False,
            timeout=30,
        )


def _api_plc(plc) -> ApiCruda:
    return ApiCruda(plc.token_id, plc.token_secreto)


def _esperar_tarea(api: ApiCruda, upid: str, maximo_s: float = 120.0) -> str:
    """Espera a que una tarea termine y devuelve su ``exitstatus``."""
    fin = time.monotonic() + maximo_s
    ruta = f"/nodes/{lab.NODO}/tasks/{requests.utils.quote(upid, safe=':@!')}/status"
    while time.monotonic() < fin:
        d = api.pedir("GET", ruta).json()["data"]
        if d["status"] == "stopped":
            return str(d.get("exitstatus"))
        time.sleep(0.3)
    raise AssertionError(f"la tarea no terminó en {maximo_s} s: {upid}")


def _volumenes(storage: str, vmid: int) -> str:
    return lab.ssh(f"sudo pvesm list {storage} --vmid {vmid}", comprobar=False)


# --- Apoyo: plan, ejecución y rollback --------------------------------------------------


def _plantilla(**kw: Any) -> ConfiguracionVM:
    base: dict[str, Any] = {
        "vmid": 100,  # se ignora en el lote
        "nombre": "plantilla",  # se ignora cuando hay patrón
        "nodo": lab.NODO,
        "cores": 1,
        "memoria_mib": 128,
        "discos": [Disco(storage=STORAGE, tamano_gib=1)],
        "redes": [InterfazRed(bridge="vmbr0")],
    }
    base.update(kw)
    return ConfiguracionVM(**base)


def _defn(
    cantidad: int,
    vmid_inicial: int | None,
    prefijo: str,
    plantilla: ConfiguracionVM | None = None,
    **kw: Any,
) -> DefinicionLote:
    return DefinicionLote(
        plantilla=plantilla or _plantilla(),
        cantidad=cantidad,
        patron=PatronNombres(prefijo=prefijo),
        vmid_inicial=vmid_inicial,
        **kw,
    )


def _planificar(sesion, definicion: DefinicionLote) -> tuple[Plan, Inventario]:
    inv = descubrir(sesion)
    return Planificador(sesion, RelojReal()).planificar(definicion, inv), inv


@dataclass
class Corrida:
    libro: Libro
    control: ControlLote
    pausa: object  # MotivoPausa observado o None
    segundos: float
    eventos: list[Any]


def _ejecutar(
    sesion,
    plan: Plan,
    inv: Inventario,
    *,
    al_observar: Callable[[Any, ControlLote], None] | None = None,
    maximo_s: float = 900.0,
) -> Corrida:
    """Ejecuta el plan con el motor real en un hilo; si el lote se pausa, lo cancela."""
    control = ControlLote()
    eventos: list[Any] = []

    def observador(entrada: Any) -> None:
        eventos.append(entrada)
        if al_observar is not None:
            al_observar(entrada, control)

    resultado: dict[str, Libro] = {}
    hilo = threading.Thread(
        target=lambda: resultado.setdefault(
            "libro", MotorLote(sesion, RelojReal()).ejecutar(plan, inv, observador, control)
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
            control.cancelar()  # el lote espera una decisión: en la prueba se cancela
    assert not hilo.is_alive(), "el motor no terminó (¿pausa sin resolver?)"
    return Corrida(resultado["libro"], control, pausa, time.monotonic() - t0, eventos)


def _estados(libro: Libro) -> dict[int, EstadoMV]:
    return {e.elemento.vmid: e.estado for e in libro.instantanea()}


def _deshacer(
    sesion, libro: Libro, *, etiquetado: bool = True
) -> tuple[list[CandidatoRollback], list[ResultadoRollback]]:
    servicio = ServicioRollback(sesion, RelojReal())
    candidatos = servicio.elegibles(libro, etiquetado=etiquetado)
    resultados = servicio.deshacer(
        candidatos, lambda _r: None, ControlLote(), id_lote=libro.id_lote, etiquetado=etiquetado
    )
    return candidatos, resultados


def _tags(config: dict[str, Any]) -> set[str]:
    return {t for t in re.split(r"[;,]", str(config.get("tags", ""))) if t}


def _esperar_nombre_visible(sesion, vmid: int, maximo_s: float = 30.0) -> float:
    """``/cluster/resources`` tarda en mostrar el nombre de una MV recién creada (pvestatd)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < maximo_s:
        if any(v.vmid == vmid and v.nombre for v in sesion.cliente.vms_visibles()):
            return round(time.monotonic() - t0, 1)
        time.sleep(0.5)
    raise AssertionError(f"la MV {vmid} no apareció con nombre en /cluster/resources")


def _existentes_en_rango() -> list[int]:
    return sorted(lab.vmids_de_prueba())


# =========================================================================================
# LAB-L01  Lote de 5 MVs
# =========================================================================================


def test_l01_lote_de_5_nombres_vmids_config_y_tiempos(sesion_plc, vmids):
    plan, inv = _planificar(sesion_plc, _defn(5, 9000, "plc-l01"))
    assert not plan.bloqueado, plan.problemas
    vmids(*(e.vmid for e in plan.elementos))
    assert [e.vmid for e in plan.elementos] == [9000, 9001, 9002, 9003, 9004]
    assert [e.nombre for e in plan.elementos] == [f"plc-l01-0{i}" for i in range(1, 6)]

    c = _ejecutar(sesion_plc, plan, inv)
    assert set(_estados(c.libro).values()) == {EstadoMV.OK}, c.libro.instantanea()
    assert c.pausa is None
    evidencia("L01", segundos_total=round(c.segundos, 1), por_mv=round(c.segundos / 5, 1))

    etiqueta = f"lote-{plan.id_lote}"
    for e in c.libro.instantanea():
        v = e.elemento.vmid
        assert e.upid is not None and f":qmcreate:{v}:plc@pve!t1:" in e.upid
        conf = sesion_plc.cliente.config_vm(lab.NODO, v)
        assert conf is not None
        assert conf["name"] == e.elemento.nombre
        assert (conf["sockets"], conf["cores"], conf["memory"]) == (1, 1, "128")
        assert conf["scsi0"].startswith(f"{STORAGE}:vm-{v}-disk-0,") and "size=1G" in conf["scsi0"]
        assert re.fullmatch(r"virtio=[0-9A-F:]{17},bridge=vmbr0", conf["net0"])
        assert _tags(conf) == {"proxlaunch", etiqueta}
    evidencia("L01-tags", formato_en_config=sesion_plc.cliente.config_vm(lab.NODO, 9000)["tags"])
    assert _existentes_en_rango() == [9000, 9001, 9002, 9003, 9004]

    informe = construir_informe(
        plan,
        c.libro,
        MetadatosInforme("lab", "9.2.26", False, None, "2026-11-13T00:00:00"),
        reloj=RelojReal(),
        ocultar=(lab.HOST, "plc@pve"),
    )
    assert informe.contadores["ok"] == 5 and informe.pedidas == 5
    assert all(v >= 0 for v in informe.duraciones_s.values()) and len(informe.duraciones_s) == 5


def _normalizada(conf: dict[str, Any], vmid: int) -> dict[str, str]:
    """Config sin lo que cambia por MV (nombre, etiquetas, MAC, uuids) para comparar."""
    ignorar = {"name", "tags", "vmgenid", "smbios1", "digest", "meta"}
    salida: dict[str, str] = {}
    for k, v in conf.items():
        if k in ignorar:
            continue
        texto = str(v).replace(str(vmid), "VMID")
        salida[k] = re.sub(r"virtio=[0-9A-F:]{17}", "virtio=MAC", texto)
    return salida


def test_l01_lote_de_1_equivale_a_la_creacion_de_m1(sesion_plc, vmids):
    plan, inv = _planificar(sesion_plc, _defn(1, 9010, "plc-l01n1"))
    vmids(9010, 9011)
    c = _ejecutar(sesion_plc, plan, inv)
    assert _estados(c.libro) == {9010: EstadoMV.OK}

    cfg_m1 = replace(_plantilla(), vmid=9011, nombre="plc-m1")
    r = ServicioCreacion(sesion_plc, RelojReal()).crear(
        cfg_m1, inv, lambda _e: None, threading.Event()
    )
    assert r.desenlace == Desenlace.OK, r
    lote = sesion_plc.cliente.config_vm(lab.NODO, 9010)
    m1 = sesion_plc.cliente.config_vm(lab.NODO, 9011)
    assert _normalizada(lote, 9010) == _normalizada(m1, 9011)
    assert "tags" not in m1 and _tags(lote) >= {"proxlaunch"}  # única diferencia: la etiqueta


# =========================================================================================
# LAB-L02  VMID ocupado en el rango
# =========================================================================================


def test_l02_el_lote_salta_el_vmid_existente(sesion_plc, vmids):
    vmids(9021, 9020, 9022, 9023)
    lab.ssh("sudo qm create 9021 --name plc-l02-ajena --memory 64")
    plan, inv = _planificar(sesion_plc, _defn(3, 9020, "plc-l02"))
    assert not plan.bloqueado, plan.problemas
    assert [e.vmid for e in plan.elementos] == [9020, 9022, 9023]
    assert plan.vmids_saltados == (9021,)
    c = _ejecutar(sesion_plc, plan, inv)
    assert set(_estados(c.libro).values()) == {EstadoMV.OK}
    # La MV ajena no se tocó.
    ajena = sesion_plc.cliente.config_vm(lab.NODO, 9021)
    assert ajena["name"] == "plc-l02-ajena" and "tags" not in ajena


def test_l02_vmid_inicial_ocupado_arranca_en_el_siguiente(sesion_plc, vmids):
    vmids(9025, 9026, 9027)
    lab.ssh("sudo qm create 9025 --name plc-l02b-ajena --memory 64")
    plan, _inv = _planificar(sesion_plc, _defn(2, 9025, "plc-l02b"))
    assert [e.vmid for e in plan.elementos] == [9026, 9027]
    assert plan.vmids_saltados == (9025,)


# =========================================================================================
# LAB-L03  nextid
# =========================================================================================


def test_l03_nextid_sin_parametro_devuelve_lo_mismo_a_peticiones_simultaneas(plc):
    api = _api_plc(plc)
    with ThreadPoolExecutor(max_workers=8) as pool:
        resp = list(pool.map(lambda _i: api.pedir("GET", "/cluster/nextid"), range(8)))
    assert all(r.status_code == 200 for r in resp)
    ids = {r.json()["data"] for r in resp}
    evidencia("L03-nextid-simultaneo", ids_distintos=sorted(ids), peticiones=8)
    assert len(ids) == 1  # CT-8: nextid no reserva, todas reciben el mismo VMID


def test_l03_ventana_hasta_que_nextid_marca_ocupado_tras_el_post(plc, vmids):
    vmid = vmids(9030)
    api = _api_plc(plc)
    assert api.pedir("GET", "/cluster/nextid", params={"vmid": vmid}).status_code == 200
    r = api.pedir(
        "POST",
        f"/nodes/{lab.NODO}/qemu",
        datos={"vmid": vmid, "name": "plc-l03", "memory": 64},
    )
    assert r.status_code == 200, r.text
    t0 = time.monotonic()
    ventana = None
    primera = None
    while time.monotonic() - t0 < 15:
        resp = api.pedir("GET", "/cluster/nextid", params={"vmid": vmid})
        if primera is None:
            primera = resp.status_code
        if resp.status_code == 400:
            ventana = time.monotonic() - t0
            assert f"VM {vmid} already exists" in resp.text
            break
        time.sleep(0.02)
    evidencia("L03-ventana", primera_consulta_tras_post=primera, ventana_s=ventana)
    assert ventana is not None, "nextid?vmid= nunca marcó ocupado el VMID creado"
    assert _esperar_tarea(api, r.json()["data"]) == "OK"


# =========================================================================================
# LAB-L04  Lote que no cabe: LVM pequeño temporal
# =========================================================================================


@pytest.fixture
def lvm_pequeno() -> Iterator[str]:
    """Storage LVM (no thin) de ~4,3 GiB sobre un archivo disperso; se elimina al terminar."""
    nombre = "plcl04"
    imagen = "/var/tmp/plc-l04.img"
    lab.ssh(f"sudo pvesm remove {nombre}; sudo vgremove -f {nombre}; true", comprobar=False)
    try:
        lab.ssh(
            f"sudo truncate -s 4300M {imagen} && dev=$(sudo losetup -f --show {imagen}) && "
            f"sudo pvcreate $dev && sudo vgcreate {nombre} $dev && "
            f"sudo pvesm add lvm {nombre} --vgname {nombre} --content images"
        )
        yield nombre
    finally:
        lab.ssh(
            f"sudo pvesm remove {nombre}; sudo lvremove -f {nombre}; sudo vgremove -f {nombre}; "
            f"for d in $(sudo losetup -j {imagen} | cut -d: -f1); do "
            f"sudo pvremove -f $d; sudo losetup -d $d; done; sudo rm -f {imagen}; true",
            comprobar=False,
        )


def _tamano_lv(vg: str, lv: str) -> int:
    salida = lab.ssh(
        f"sudo lvs --noheadings --units b --nosuffix -o lv_size {vg}/{lv}", comprobar=False
    )
    return int(salida.strip() or 0)


def test_l04_lote_que_no_cabe_fallan_las_ultimas_y_el_lote_sigue(sesion_plc, vmids, lvm_pequeno):
    vg = lvm_pequeno
    plantilla = _plantilla(firmware=Firmware.OVMF, discos=[Disco(storage=vg, tamano_gib=1)])
    plan, inv = _planificar(sesion_plc, _defn(4, 9040, "plc-l04", plantilla))
    vmids(*(e.vmid for e in plan.elementos))
    assert not plan.bloqueado, plan.problemas  # al planificar el espacio alcanza

    libre_mib = int(float(lab.ssh(f"sudo vgs --noheadings --units m --nosuffix -o vg_free {vg}")))
    # Un consumidor externo deja sitio para solo 2 MVs (1 GiB + 4 MiB de efidisk cada una).
    hog = libre_mib - 2 * 1028 - 100
    lab.ssh(f"sudo lvcreate -y -L {hog}M -n relleno {vg}")
    libre_antes = int(float(lab.ssh(f"sudo vgs --noheadings --units m --nosuffix -o vg_free {vg}")))

    c = _ejecutar(sesion_plc, plan, inv)
    estados = _estados(c.libro)
    evidencia(
        "L04-estados", estados={k: v.value for k, v in estados.items()}, libre_mib=libre_antes
    )
    assert [estados[v] for v in (9040, 9041)] == [EstadoMV.OK, EstadoMV.OK]
    assert [estados[v] for v in (9042, 9043)] == [
        EstadoMV.ERROR,
        EstadoMV.ERROR,
    ]  # sigue con las demás
    assert c.pausa is None  # 2 fallos no alcanzan el umbral de repetición (3)
    for v in (9042, 9043):
        entrada = c.libro.entrada(v)
        assert entrada.error is not None
        evidencia(
            "L04-error",
            vmid=v,
            codigo=str(entrada.error.codigo),
            detalle=entrada.error.detalle_tecnico[:300],
            log=list(entrada.log_tarea)[-3:],
        )
        assert entrada.error.codigo == CodigoError.SIN_ESPACIO
        assert entrada.error.params.get("storage") == vg

    # Volúmenes huérfanos y configuración residual de las fallidas.
    lvs = lab.ssh(f"sudo lvs --noheadings -o lv_name {vg}")
    huerfanos = [n for n in lvs.split() if n.startswith(("vm-9042", "vm-9043"))]
    evidencia("L04-huerfanos", volumenes=huerfanos)
    for v in (9042, 9043):
        existe = sesion_plc.cliente.config_vm(lab.NODO, v)
        evidencia("L04-config-residual", vmid=v, existe=existe is not None)
    assert not huerfanos, f"la creación fallida dejó volúmenes: {huerfanos}"

    # Tamaño real del efidisk en LVM (no thin).
    conf = sesion_plc.cliente.config_vm(lab.NODO, 9040)
    efi = conf["efidisk0"].split(",")[0].split(":")[1]
    tam = _tamano_lv(vg, efi)
    evidencia("L04-efidisk-lvm", bytes=tam, mib=tam / 2**20, efidisk=conf["efidisk0"])
    assert tam == 4 * 2**20  # TAM_EFIDISK_MIB = 4


def test_l04_tamano_real_del_efidisk_en_lvmthin(sesion_plc, vmids):
    plan, inv = _planificar(
        sesion_plc, _defn(1, 9045, "plc-l04e", _plantilla(firmware=Firmware.OVMF))
    )
    vmids(9045)
    c = _ejecutar(sesion_plc, plan, inv)
    assert _estados(c.libro) == {9045: EstadoMV.OK}
    conf = sesion_plc.cliente.config_vm(lab.NODO, 9045)
    efi = conf["efidisk0"].split(",")[0].split(":")[1]
    tam = _tamano_lv("lab", efi)
    evidencia("L04-efidisk-lvmthin", mib=tam / 2**20, efidisk=conf["efidisk0"])
    assert tam == 4 * 2**20


# =========================================================================================
# LAB-L05  DELETE de una MV
# =========================================================================================

PRIV_ROL = lab.PRIVILEGIOS_ROL


def _crear_con_disco_suelto(sesion, vmid: int) -> tuple[Inventario, str]:
    plan, inv = _planificar(sesion, _defn(1, vmid, f"plc-l05-{vmid}"))
    c = _ejecutar(sesion, plan, inv)
    assert _estados(c.libro) == {vmid: EstadoMV.OK}
    suelto = f"vm-{vmid}-disk-7"
    lab.ssh(f"sudo pvesm alloc {STORAGE} {vmid} {suelto} 1G")
    assert suelto in _volumenes(STORAGE, vmid)
    return inv, suelto


def test_l05_delete_con_rol_de_10_privilegios_d21_no_borra_discos_sueltos(sesion_plc, plc, vmids):
    vmid = vmids(9050)
    _crear_con_disco_suelto(sesion_plc, vmid)
    api = _api_plc(plc)
    perm = api.pedir("GET", "/access/permissions", params={"path": f"/vms/{vmid}"})
    assert perm.status_code == 200
    evidencia(
        "L05-permisos-ruta",
        ruta=f"/vms/{vmid}",
        privilegios=sorted(perm.json()["data"].get(f"/vms/{vmid}", {})),
    )
    assert perm.json()["data"][f"/vms/{vmid}"].get("VM.Allocate") == 1

    upid = sesion_plc.cliente.eliminar_vm(lab.NODO, vmid)  # camino real del código
    assert upid.startswith(f"UPID:{lab.NODO}:") and f":qmdestroy:{vmid}:plc@pve!t1:" in upid
    assert _esperar_tarea(api, upid) == "OK"
    assert sesion_plc.cliente.config_vm(lab.NODO, vmid) is None
    restos = _volumenes(STORAGE, vmid)
    evidencia("L05-delete-consulta", volumenes_restantes=restos.strip().splitlines()[1:])
    # D-21: con destroy-unreferenced-disks=0 y sin purge, el disco de la config se borra pero un
    # volumen suelto del mismo VMID (que podría ser de otra persona) NO se toca.
    assert f"vm-{vmid}-disk-0" not in restos
    assert f"vm-{vmid}-disk-7" in restos


def test_l05_rollback_d21_elimina_la_maquina_y_sus_discos_pero_no_un_volumen_suelto(
    sesion_plc, vmids
):
    plan, inv = _planificar(sesion_plc, _defn(1, 9053, "plc-l05d"))
    vmids(9053)
    c = _ejecutar(sesion_plc, plan, inv)
    assert _estados(c.libro) == {9053: EstadoMV.OK}
    lab.ssh(f"sudo pvesm alloc {STORAGE} 9053 vm-9053-disk-7 1G")
    _cands, res = _deshacer(sesion_plc, c.libro)
    assert [r.estado for r in res] == [EstadoRollback.ELIMINADA]
    assert sesion_plc.cliente.config_vm(lab.NODO, 9053) is None
    restos = _volumenes(STORAGE, 9053)
    evidencia("L05-rollback-d21", restos=restos.strip().splitlines()[1:])
    assert "vm-9053-disk-0" not in restos  # el disco de la config sí se borra
    assert "vm-9053-disk-7" in restos  # el suelto no: el rollback no destruye lo que no es suyo


def test_l05_delete_sin_destroy_unreferenced_deja_el_disco_suelto(sesion_plc, plc, vmids):
    vmid = vmids(9051)
    _crear_con_disco_suelto(sesion_plc, vmid)
    api = _api_plc(plc)
    r = api.pedir("DELETE", f"/nodes/{lab.NODO}/qemu/{vmid}")
    assert r.status_code == 200, r.text
    assert _esperar_tarea(api, r.json()["data"]) == "OK"
    assert sesion_plc.cliente.config_vm(lab.NODO, vmid) is None
    restos = _volumenes(STORAGE, vmid)
    evidencia("L05-delete-sin-param", restos=restos.strip().splitlines()[1:])
    assert f"vm-{vmid}-disk-7" in restos, "el disco suelto debería sobrevivir sin el parámetro"
    assert f"vm-{vmid}-disk-0" not in restos  # el disco referenciado sí se borra


def test_l05_delete_con_params_en_cuerpo(sesion_plc, plc, vmids):
    vmid = vmids(9052)
    _crear_con_disco_suelto(sesion_plc, vmid)
    api = _api_plc(plc)
    r = api.pedir(
        "DELETE",
        f"/nodes/{lab.NODO}/qemu/{vmid}",
        datos={"destroy-unreferenced-disks": 1, "purge": 0},
    )
    evidencia("L05-delete-cuerpo", status=r.status_code, texto=r.text[:200])
    if r.status_code == 200:
        assert _esperar_tarea(api, r.json()["data"]) == "OK"
    restos = _volumenes(STORAGE, vmid)
    evidencia("L05-delete-cuerpo-restos", suelto_sobrevive=f"vm-{vmid}-disk-7" in restos)
    # El cliente usa la consulta (probado arriba); aquí solo se documenta el comportamiento.
    assert r.status_code in (200, 400, 501)


def test_l05_delete_con_purge_1_aceptado(sesion_plc, plc, vmids):
    vmid = vmids(9053)
    _crear_con_disco_suelto(sesion_plc, vmid)
    api = _api_plc(plc)
    r = api.pedir(
        "DELETE",
        f"/nodes/{lab.NODO}/qemu/{vmid}",
        params={"destroy-unreferenced-disks": 1, "purge": 1},
    )
    assert r.status_code == 200, r.text
    assert _esperar_tarea(api, r.json()["data"]) == "OK"
    assert f"vm-{vmid}-" not in _volumenes(STORAGE, vmid)


def test_l05_privilegio_minimo_solo_vm_allocate_basta_para_borrar(vmids):
    vmid = vmids(9054)
    lab.ssh(f"sudo qm create {vmid} --name plc-l05-min --memory 64 --scsi0 {STORAGE}:1")
    with usuario_temporal(("VM.Allocate",)) as u:
        api = ApiCruda(u.token_id, u.token_secreto)
        r = api.pedir(
            "DELETE",
            f"/nodes/{lab.NODO}/qemu/{vmid}",
            params={"destroy-unreferenced-disks": 1, "purge": 0},
        )
        evidencia("L05-solo-allocate", status=r.status_code, texto=r.text[:200])
        assert r.status_code == 200, r.text
        assert _esperar_tarea(api, r.json()["data"]) == "OK"
    assert f"vm-{vmid}-" not in _volumenes(STORAGE, vmid)


def test_l05_sin_vm_allocate_da_403_con_ruta_y_privilegio(sesion_plc, vmids):
    vmid = vmids(9055)
    lab.ssh(f"sudo qm create {vmid} --name plc-l05-sinperm --memory 64")
    sin = tuple(p for p in PRIV_ROL if p != "VM.Allocate")
    with usuario_temporal(sin) as u:
        api = ApiCruda(u.token_id, u.token_secreto)
        r = api.pedir(
            "DELETE",
            f"/nodes/{lab.NODO}/qemu/{vmid}",
            params={"destroy-unreferenced-disks": 1, "purge": 0},
        )
        evidencia("L05-403", status=r.status_code, texto=r.text[:200])
        assert r.status_code == 403
        assert "VM.Allocate" in r.text and f"/vms/{vmid}" in r.text
    # La MV sigue ahí.
    assert sesion_plc.cliente.config_vm(lab.NODO, vmid) is not None


def test_l05_eliminar_vm_inexistente_lanza_error_del_nucleo(sesion_plc):
    with pytest.raises(ErrorProxLaunch) as e:
        sesion_plc.cliente.eliminar_vm(lab.NODO, 9098)
    evidencia("L05-inexistente", codigo=str(e.value.codigo), detalle=e.value.detalle_tecnico[:200])
    assert e.value.codigo in (CodigoError.RECURSO_INEXISTENTE, CodigoError.DESCONOCIDO)


def test_l05_delete_de_mv_protegida_no_actua(sesion_plc, plc, vmids):
    vmid = vmids(9056)
    _crear_con_disco_suelto(sesion_plc, vmid)
    lab.ssh(f"sudo qm set {vmid} --protection 1")
    api = _api_plc(plc)
    r = api.pedir(
        "DELETE",
        f"/nodes/{lab.NODO}/qemu/{vmid}",
        params={"destroy-unreferenced-disks": 1, "purge": 0},
    )
    evidencia("L05-protegida", status=r.status_code, texto=r.text[:200])
    if r.status_code == 200:
        evidencia("L05-protegida-tarea", exitstatus=_esperar_tarea(api, r.json()["data"]))
    assert sesion_plc.cliente.config_vm(lab.NODO, vmid) is not None
    assert f"vm-{vmid}-disk-0" in _volumenes(STORAGE, vmid)


def test_l05_delete_de_mv_encendida_falla(sesion_plc, plc, vmids):
    vmid = vmids(9057)
    _crear_con_disco_suelto(sesion_plc, vmid)
    lab.ssh(f"sudo qm set {vmid} --kvm 0 --ide2 none,media=cdrom")  # arrancar sin KVM anidado
    lab.ssh(f"sudo qm start {vmid}", timeout=120)
    api = _api_plc(plc)
    r = api.pedir(
        "DELETE",
        f"/nodes/{lab.NODO}/qemu/{vmid}",
        params={"destroy-unreferenced-disks": 1, "purge": 0},
    )
    evidencia("L05-encendida", status=r.status_code, texto=r.text[:200])
    if r.status_code == 200:
        evidencia("L05-encendida-tarea", exitstatus=_esperar_tarea(api, r.json()["data"]))
    assert sesion_plc.cliente.config_vm(lab.NODO, vmid) is not None


def test_l05_delete_de_mv_bloqueada_falla(sesion_plc, plc, vmids):
    vmid = vmids(9058)
    _crear_con_disco_suelto(sesion_plc, vmid)
    lab.ssh(f"sudo sh -c 'echo \"lock: backup\" >> /etc/pve/qemu-server/{vmid}.conf'")
    estado = sesion_plc.cliente.estado_actual_vm(lab.NODO, vmid)
    evidencia("L05-lock-estado", lock=estado.get("lock"))
    api = _api_plc(plc)
    r = api.pedir(
        "DELETE",
        f"/nodes/{lab.NODO}/qemu/{vmid}",
        params={"destroy-unreferenced-disks": 1, "purge": 0},
    )
    evidencia("L05-bloqueada", status=r.status_code, texto=r.text[:200])
    if r.status_code == 200:
        evidencia("L05-bloqueada-tarea", exitstatus=_esperar_tarea(api, r.json()["data"]))
    assert sesion_plc.cliente.config_vm(lab.NODO, vmid) is not None


def test_l05_rollback_del_lote_con_omisiones_reales(sesion_plc, vmids):
    plan, inv = _planificar(sesion_plc, _defn(5, 9060, "plc-l05r"))
    vmids(*(e.vmid for e in plan.elementos))
    c = _ejecutar(sesion_plc, plan, inv)
    assert set(_estados(c.libro).values()) == {EstadoMV.OK}
    # 9060 protegida, 9061 encendida, 9062 ajena (etiquetas cambiadas),
    # 9063 ya borrada, 9064 normal.
    lab.ssh("sudo qm set 9060 --protection 1")
    lab.ssh("sudo qm set 9061 --kvm 0 --ide2 none,media=cdrom && sudo qm start 9061", timeout=120)
    lab.ssh("sudo qm set 9062 --tags otro-lote")
    lab.ssh("sudo qm destroy 9063 --purge 1 --destroy-unreferenced-disks 1")

    candidatos, res = _deshacer(sesion_plc, c.libro)
    assert all(x.elegible for x in candidatos)
    por_vmid = {r.vmid: r for r in res}
    evidencia(
        "L05-rollback",
        estados={v: r.estado.value for v, r in por_vmid.items()},
        errores={v: str(r.error.codigo) for v, r in por_vmid.items() if r.error},
    )
    assert por_vmid[9060].estado == EstadoRollback.OMITIDA
    assert por_vmid[9060].error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    assert por_vmid[9061].estado == EstadoRollback.OMITIDA
    assert por_vmid[9061].error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    assert por_vmid[9062].estado == EstadoRollback.OMITIDA
    assert por_vmid[9062].error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert por_vmid[9063].estado == EstadoRollback.YA_NO_EXISTIA
    assert por_vmid[9064].estado == EstadoRollback.ELIMINADA
    assert _existentes_en_rango() == [9060, 9061, 9062]  # las omitidas siguen intactas
    assert sesion_plc.cliente.config_vm(lab.NODO, 9064) is None


def test_l05_rollback_omite_mv_bloqueada_por_lock(sesion_plc, vmids):
    plan, inv = _planificar(sesion_plc, _defn(1, 9065, "plc-l05l"))
    vmids(9065)
    c = _ejecutar(sesion_plc, plan, inv)
    lab.ssh("sudo sh -c 'echo \"lock: backup\" >> /etc/pve/qemu-server/9065.conf'")
    _cands, res = _deshacer(sesion_plc, c.libro)
    assert res[0].estado == EstadoRollback.OMITIDA
    assert res[0].error.codigo == CodigoError.ROLLBACK_BLOQUEADA
    assert sesion_plc.cliente.config_vm(lab.NODO, 9065) is not None


def test_l05_rollback_sin_permiso_se_detiene_con_403(sesion_plc, vmids, entorno):
    """Un usuario sin VM.Allocate crea con otro, pero no puede deshacer: error global (CA-L18.9)."""
    from proxlaunch.nucleo.modelos.conexion import CredencialToken, MetodoAuth

    plan, inv = _planificar(sesion_plc, _defn(2, 9066, "plc-l05p"))
    vmids(9066, 9067)
    c = _ejecutar(sesion_plc, plan, inv)
    assert set(_estados(c.libro).values()) == {EstadoMV.OK}
    sin = tuple(p for p in PRIV_ROL if p != "VM.Allocate")
    with usuario_temporal(sin) as u:
        p = lab.perfil(MetodoAuth.TOKEN, u.token_id)
        lab.confiar_en_laboratorio(entorno, p)
        sesion = entorno.servicio.conectar(p, CredencialToken(u.token_id, u.token_secreto))
        try:
            _c, res = _deshacer(sesion, c.libro)
        finally:
            entorno.servicio.cerrar_sesion(sesion)
    evidencia(
        "L05-rollback-403",
        resultados=[
            (r.vmid, r.estado.value, str(r.error.codigo) if r.error else None) for r in res
        ],
    )
    assert res[0].estado == EstadoRollback.FALLO
    assert res[0].error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert res[1].estado == EstadoRollback.NO_ENVIADA
    assert _existentes_en_rango() == [9066, 9067]


# =========================================================================================
# LAB-L06  Etiquetas
# =========================================================================================


def _post_etiquetas(api: ApiCruda, vmid: int, tags: str) -> requests.Response:
    return api.pedir(
        "POST",
        f"/nodes/{lab.NODO}/qemu",
        datos={"vmid": vmid, "name": f"plc-l06-{vmid}", "memory": 64, "tags": tags},
    )


@pytest.mark.parametrize(
    ("tags", "esperadas"),
    [
        ("proxlaunch;lote-1a2b3c4d", {"proxlaunch", "lote-1a2b3c4d"}),
        ("proxlaunch,lote-1a2b3c4d", {"proxlaunch", "lote-1a2b3c4d"}),
        ("proxlaunch lote-1a2b3c4d", {"proxlaunch", "lote-1a2b3c4d"}),
    ],
)
def test_l06_formatos_de_separador_aceptados(plc, vmids, tags, esperadas):
    vmid = vmids(9070)
    api = _api_plc(plc)
    r = _post_etiquetas(api, vmid, tags)
    assert r.status_code == 200, r.text
    assert _esperar_tarea(api, r.json()["data"]) == "OK"
    conf = api.pedir("GET", f"/nodes/{lab.NODO}/qemu/{vmid}/config").json()["data"]
    evidencia("L06-separador", enviado=tags, config_tags=conf["tags"])
    assert _tags(conf) == esperadas


@pytest.mark.parametrize("tags", ["Lote Uno", "lote/uno", "lote@1", "ñandú", "-lote"])
def test_l06_etiquetas_con_patron_invalido_se_rechazan_o_normalizan(plc, vmids, tags):
    vmid = vmids(9071)
    api = _api_plc(plc)
    r = _post_etiquetas(api, vmid, tags)
    resultado: dict[str, Any] = {"enviado": tags, "status": r.status_code, "texto": r.text[:160]}
    if r.status_code == 200:
        _esperar_tarea(api, r.json()["data"])
        conf = api.pedir("GET", f"/nodes/{lab.NODO}/qemu/{vmid}/config").json()["data"]
        resultado["config_tags"] = conf.get("tags")
    evidencia("L06-patron", **resultado)
    assert r.status_code in (200, 400)


def test_l06_mayusculas_y_longitud_de_etiqueta(plc, vmids):
    vmid = vmids(9072)
    api = _api_plc(plc)
    r = _post_etiquetas(api, vmid, "ProxLaunch;lote-ABCDEF12")
    assert r.status_code == 200, r.text
    _esperar_tarea(api, r.json()["data"])
    conf = api.pedir("GET", f"/nodes/{lab.NODO}/qemu/{vmid}/config").json()["data"]
    evidencia("L06-mayusculas", config_tags=conf["tags"])
    assert _tags(conf) == {"proxlaunch", "lote-abcdef12"}  # Proxmox pasa a minúsculas


def test_l06_privilegio_exigido_al_crear_con_etiquetas(vmids):
    """Sin ``VM.Config.Options``: con ``name`` el POST da 403; solo con ``tags`` el POST da 200
    y la TAREA falla con el mismo 403 (``tags`` exige ``VM.Config.Options`` al crear)."""
    vmid = vmids(9073)
    sin = tuple(p for p in PRIV_ROL if p != "VM.Config.Options")
    with usuario_temporal(sin) as u:
        api = ApiCruda(u.token_id, u.token_secreto)
        con_nombre = api.pedir(
            "POST",
            f"/nodes/{lab.NODO}/qemu",
            datos={"vmid": vmid, "name": "plc-l06-x", "memory": 64, "tags": "proxlaunch"},
        )
        evidencia(
            "L06-sin-options-con-name", status=con_nombre.status_code, texto=con_nombre.text[:160]
        )
        assert con_nombre.status_code == 403 and "VM.Config.Options" in con_nombre.text
        solo_tags = api.pedir(
            "POST",
            f"/nodes/{lab.NODO}/qemu",
            datos={"vmid": vmid, "memory": 64, "tags": "proxlaunch"},
        )
        exit_ = (
            _esperar_tarea(api, solo_tags.json()["data"]) if solo_tags.status_code == 200 else ""
        )
        evidencia("L06-sin-options-solo-tags", status=solo_tags.status_code, exitstatus=exit_)
        assert solo_tags.status_code == 200
        assert "VM.Config.Options" in exit_


@contextlib.contextmanager
def _user_tag_access(valor: str) -> Iterator[None]:
    """Fija ``user-tag-access`` del datacenter y SIEMPRE lo deja como estaba (ausente)."""
    antes = lab.ssh("sudo pvesh get /cluster/options --output-format json")
    assert "user-tag-access" not in antes, "estado inicial inesperado del laboratorio"
    try:
        lab.ssh(f"sudo pvesh set /cluster/options --user-tag-access '{valor}'")
        yield
    finally:
        lab.ssh("sudo pvesh set /cluster/options --delete user-tag-access", comprobar=False)
        assert "user-tag-access" not in lab.ssh(
            "sudo pvesh get /cluster/options --output-format json"
        )


@pytest.mark.parametrize("politica", ["user-allow=none", "user-allow=existing"])
def test_l06_user_tag_access_restringido_rechaza_la_etiqueta(plc, vmids, politica):
    """El rechazo NO llega como HTTP 403 en el POST: el POST da 200 y la TAREA falla."""
    vmid = vmids(9074)
    api = _api_plc(plc)
    with _user_tag_access(politica):
        r = _post_etiquetas(api, vmid, "proxlaunch;lote-1a2b3c4d")
        exit_ = _esperar_tarea(api, r.json()["data"]) if r.status_code == 200 else ""
        evidencia("L06-user-tag-access", politica=politica, status=r.status_code, exitstatus=exit_)
        assert r.status_code == 200
        assert "Sys.Modify" in exit_
    assert api.pedir("GET", f"/nodes/{lab.NODO}/qemu/{vmid}/config").status_code != 200


def test_l06_lote_con_user_tag_access_restringido_se_pausa_con_etiqueta_rechazada(
    sesion_plc, vmids
):
    plan, inv = _planificar(sesion_plc, _defn(3, 9075, "plc-l06"))
    vmids(*(e.vmid for e in plan.elementos))
    with _user_tag_access("user-allow=none"):
        c = _ejecutar(sesion_plc, plan, inv)
        estados = _estados(c.libro)
        primera = c.libro.entrada(9075)
        evidencia(
            "L06-lote-restringido",
            estados={k: v.value for k, v in estados.items()},
            codigo=str(primera.error.codigo) if primera.error else None,
            detalle=primera.error.detalle_tecnico[:200] if primera.error else None,
            pausa=str(c.pausa),
        )
    assert primera.estado == EstadoMV.ERROR
    assert primera.error.codigo == CodigoError.ETIQUETA_RECHAZADA
    assert c.pausa is not None  # error global (E-L15): pausa tras la primera
    assert [estados[9076], estados[9077]] == [EstadoMV.NO_ENVIADA] * 2
    assert _existentes_en_rango() == []


def test_l06_lote_sin_etiquetar_funciona_con_user_tag_access_restringido(sesion_plc, vmids):
    plan, inv = _planificar(sesion_plc, _defn(2, 9078, "plc-l06s", etiquetar=False))
    vmids(9078, 9079)
    with _user_tag_access("user-allow=none"):
        c = _ejecutar(sesion_plc, plan, inv)
    assert set(_estados(c.libro).values()) == {EstadoMV.OK}
    assert "tags" not in sesion_plc.cliente.config_vm(lab.NODO, 9078)


# =========================================================================================
# LAB-L07  Nombres duplicados
# =========================================================================================


def test_l07_proxmox_permite_dos_mvs_con_el_mismo_nombre(plc, vmids):
    a, b = vmids(9080, 9081)
    api = _api_plc(plc)
    for v in (a, b):
        r = api.pedir(
            "POST",
            f"/nodes/{lab.NODO}/qemu",
            datos={"vmid": v, "name": "plc-l07-duplicada", "memory": 64},
        )
        evidencia("L07-post", vmid=v, status=r.status_code)
        assert r.status_code == 200, r.text
        assert _esperar_tarea(api, r.json()["data"]) == "OK"


def test_l07_el_plan_avisa_del_nombre_existente_sin_bloquear(sesion_plc, vmids):
    vmids(9082, 9083, 9084)
    lab.ssh("sudo qm create 9082 --name plc-l07-01 --memory 64")
    retraso = _esperar_nombre_visible(sesion_plc, 9082)
    evidencia("L07-retraso-nombre-en-cluster-resources", segundos=retraso)
    plan, inv = _planificar(sesion_plc, _defn(2, 9083, "plc-l07"))
    avisos = [p for p in plan.problemas if p.regla == "V-L06"]
    evidencia("L07-aviso", avisos=[(p.indice, dict(p.params)) for p in avisos])
    assert [p.indice for p in avisos] == [0]
    assert avisos[0].params["vmid"] == "9082"
    assert not plan.bloqueado
    c = _ejecutar(sesion_plc, plan, inv)
    assert set(_estados(c.libro).values()) == {EstadoMV.OK}
    nombres = [sesion_plc.cliente.config_vm(lab.NODO, v)["name"] for v in (9082, 9083)]
    assert nombres[0] == nombres[1] == "plc-l07-01"


# =========================================================================================
# LAB-L08  Cancelación a mitad
# =========================================================================================


def test_l08_cancelar_no_envia_las_demas_y_la_enviada_termina(sesion_plc, vmids):
    plan, inv = _planificar(sesion_plc, _defn(4, 9085, "plc-l08"))
    vmids(*(e.vmid for e in plan.elementos))

    def al_observar(entrada, control: ControlLote) -> None:
        if entrada.estado == EstadoMV.CREANDO:
            control.cancelar()

    c = _ejecutar(sesion_plc, plan, inv, al_observar=al_observar)
    estados = _estados(c.libro)
    evidencia("L08-cancelar", estados={k: v.value for k, v in estados.items()})
    assert estados[9085] == EstadoMV.OK  # la enviada se espera hasta su desenlace (CA-L16.2)
    assert [estados[v] for v in (9086, 9087, 9088)] == [EstadoMV.NO_ENVIADA] * 3
    for v in (9086, 9087, 9088):
        assert c.libro.entrada(v).motivo_no_enviada == MotivoNoEnviada.CANCELADO
        assert not c.libro.entrada(v).post_intentado
    assert _existentes_en_rango() == [9085]
    conf = sesion_plc.cliente.config_vm(lab.NODO, 9085)
    assert "scsi0" in conf and "net0" in conf


def test_l08_dejar_de_esperar_la_tarea_sigue_y_se_confirma_despues(sesion_plc, vmids):
    plan, inv = _planificar(sesion_plc, _defn(3, 9089, "plc-l08d"))
    vmids(*(e.vmid for e in plan.elementos))

    def al_observar(entrada, control: ControlLote) -> None:
        if entrada.estado == EstadoMV.CREANDO:
            control.dejar_de_esperar()

    c = _ejecutar(sesion_plc, plan, inv, al_observar=al_observar)
    estados = _estados(c.libro)
    evidencia("L08-dejar-de-esperar", estados={k: v.value for k, v in estados.items()})
    primera = c.libro.entrada(9089)
    assert primera.estado == EstadoMV.CONEXION_PERDIDA and primera.upid is not None
    assert [estados[9090], estados[9091]] == [EstadoMV.NO_ENVIADA] * 2

    # La tarea sigue en Proxmox hasta terminar: la MV acaba completa.
    api_estado = None
    for _ in range(100):
        api_estado = sesion_plc.cliente.estado_tarea(lab.NODO, primera.upid)
        if api_estado.terminada:
            break
        time.sleep(0.3)
    assert api_estado is not None and api_estado.terminada and api_estado.exitstatus == "OK"
    MotorLote(sesion_plc, RelojReal()).comprobar_dudosas(c.libro, lambda _e: None, ControlLote())
    assert c.libro.entrada(9089).estado == EstadoMV.OK
    assert "scsi0" in sesion_plc.cliente.config_vm(lab.NODO, 9089)
    assert _existentes_en_rango() == [9089]


# =========================================================================================
# LAB-L09  Envío incierto
# =========================================================================================


def _perdida_tras_post(
    sesion,
    monkeypatch,
    *,
    enviar: bool,
    quitar_tags: bool = False,
    error: CodigoError = CodigoError.SERVIDOR_NO_RESPONDE,
) -> None:
    """Hace que ``crear_vm`` descarte la respuesta del POST (el POST real sí sale si ``enviar``)."""
    real = sesion.cliente.crear_vm

    def descarta(nodo: str, parametros: dict[str, str]) -> str:
        params = {k: v for k, v in parametros.items() if not (quitar_tags and k == "tags")}
        if enviar:
            real(nodo, params)
        raise ErrorProxLaunch(error, {"incierto": "1"}, "respuesta descartada por la prueba")

    monkeypatch.setattr(sesion.cliente, "crear_vm", descarta)


def _lote_de_uno(sesion, vmid: int, prefijo: str, **kw):
    plan, inv = _planificar(sesion, _defn(1, vmid, prefijo, **kw))
    return plan, inv


def test_l09_post_entregado_pero_sin_respuesta_se_reconcilia_como_ok(
    sesion_plc, vmids, monkeypatch
):
    plan, inv = _lote_de_uno(sesion_plc, 9092, "plc-l09a")
    vmids(9092)
    _perdida_tras_post(sesion_plc, monkeypatch, enviar=True)
    c = _ejecutar(sesion_plc, plan, inv)
    e = c.libro.entrada(9092)
    evidencia(
        "L09-entregado", estado=e.estado.value, avisos=e.avisos, segundos=round(c.segundos, 1)
    )
    assert e.post_intentado and e.upid is None
    assert e.estado == EstadoMV.OK and "creada_tras_comprobar" in e.avisos
    assert sesion_plc.cliente.config_vm(lab.NODO, 9092) is not None
    # Rescatada pero con la etiqueta del lote: es elegible para el rollback.
    cands = ServicioRollback(sesion_plc, RelojReal()).elegibles(c.libro, etiquetado=True)
    assert cands[0].elegible and cands[0].incompleta


def test_l09_post_que_no_llego_queda_no_creada_segura_tras_las_3_comprobaciones(
    sesion_plc, vmids, monkeypatch
):
    plan, inv = _lote_de_uno(sesion_plc, 9093, "plc-l09b")
    vmids(9093)
    _perdida_tras_post(sesion_plc, monkeypatch, enviar=False)
    c = _ejecutar(sesion_plc, plan, inv)
    e = c.libro.entrada(9093)
    evidencia("L09-no-llego", estado=e.estado.value, segundos=round(c.segundos, 1))
    assert e.estado == EstadoMV.NO_CREADA_SEGURA
    assert c.segundos >= 15  # t = 0, +5 s, +15 s
    assert sesion_plc.cliente.config_vm(lab.NODO, 9093) is None


def test_l09_existe_sin_la_etiqueta_del_lote_no_confirma_propiedad(sesion_plc, vmids, monkeypatch):
    plan, inv = _lote_de_uno(sesion_plc, 9094, "plc-l09c")
    vmids(9094)
    _perdida_tras_post(sesion_plc, monkeypatch, enviar=True, quitar_tags=True)
    c = _ejecutar(sesion_plc, plan, inv)
    e = c.libro.entrada(9094)
    assert e.estado == EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD
    cands = ServicioRollback(sesion_plc, RelojReal()).elegibles(c.libro, etiquetado=True)
    assert not cands[0].elegible


def test_l09_596_tras_entrega_real_queda_conexion_perdida_sin_reenvio(
    sesion_plc, vmids, monkeypatch
):
    """CA-L15.1: un 596 al enviar (la MV puede haberse creado) no es un error definitivo."""
    plan, inv = _lote_de_uno(sesion_plc, 9095, "plc-l09d")
    vmids(9095)
    llamadas: list[int] = []
    # Lo que produce el transporte real ante un 596/597 tras enviar un POST: no hay respuesta y
    # el envío es incierto (``SERVIDOR_NO_RESPONDE`` con ``incierto=1``), no un nodo caído.
    _perdida_tras_post(sesion_plc, monkeypatch, enviar=True, error=CodigoError.SERVIDOR_NO_RESPONDE)
    original = sesion_plc.cliente.crear_vm
    monkeypatch.setattr(
        sesion_plc.cliente, "crear_vm", lambda n, p: (llamadas.append(1), original(n, p))[1]
    )
    c = _ejecutar(sesion_plc, plan, inv)
    e = c.libro.entrada(9095)
    evidencia(
        "L09-596",
        estado=e.estado.value,
        codigo=str(e.error.codigo) if e.error else None,
        avisos=e.avisos,
        existe=sesion_plc.cliente.config_vm(lab.NODO, 9095) is not None,
    )
    assert len(llamadas) == 1  # INV-L1: nunca se reenvía
    assert e.estado in (EstadoMV.CONEXION_PERDIDA, EstadoMV.OK)


# =========================================================================================
# LAB-L10  Concurrencia 1/2/4 en el mismo nodo
# =========================================================================================


@pytest.mark.parametrize("storage", [STORAGE, "local"])
@pytest.mark.parametrize("n", [1, 2, 4])
def test_l10_creaciones_simultaneas_en_el_mismo_nodo(sesion_plc, vmids, storage, n):
    base = 9096 if storage == STORAGE else 9096
    ids = list(range(base, base + n))
    vmids(*ids)
    inv = descubrir(sesion_plc)

    def crear(v: int):
        cfg = _plantilla(discos=[Disco(storage=storage, tamano_gib=1)])
        cfg = replace(cfg, vmid=v, nombre=f"plc-l10-{v}")
        t = time.monotonic()
        r = ServicioCreacion(sesion_plc, RelojReal()).crear(
            cfg, inv, lambda _e: None, threading.Event()
        )
        return r, time.monotonic() - t

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=n) as pool:
        res = list(pool.map(crear, ids))
    total = time.monotonic() - t0
    evidencia(
        "L10",
        storage=storage,
        concurrencia=n,
        total_s=round(total, 1),
        por_mv_s=[round(t, 1) for _r, t in res],
        desenlaces=[r.desenlace.value for r, _t in res],
    )
    assert all(r.desenlace == Desenlace.OK for r, _t in res), [r for r, _t in res]
    assert _existentes_en_rango() == ids


# =========================================================================================
# LAB-L11  /cluster/resources con el rol mínimo
# =========================================================================================


def test_l11_cluster_resources_con_rol_minimo_lista_todas_las_mvs(sesion_plc, vmids):
    vmids(9041, 9042)
    lab.ssh(
        "sudo qm create 9041 --name plc-l11-a --memory 64 && "
        "sudo qm create 9042 --name plc-l11-b --memory 64"
    )
    visibles = {v.vmid for v in sesion_plc.cliente.vms_visibles()}
    evidencia("L11-rol-minimo", visibles=sorted(visibles))
    assert {9041, 9042} <= visibles


def test_l11_con_acl_restringida_solo_lista_las_visibles(vmids):
    vmids(9043, 9044)
    lab.ssh(
        "sudo qm create 9043 --name plc-l11-c --memory 64 && "
        "sudo qm create 9044 --name plc-l11-d --memory 64"
    )
    with usuario_temporal(("VM.Audit",), ruta="/vms/9043") as u:
        api = ApiCruda(u.token_id, u.token_secreto)
        r = api.pedir("GET", "/cluster/resources", params={"type": "vm"})
        assert r.status_code == 200
        ids = sorted(int(x["vmid"]) for x in r.json()["data"])
        evidencia("L11-acl-restringida", visibles=ids)
        assert ids == [9043]


def test_l11_sin_vm_audit_no_lista_ninguna(vmids):
    vmids(9045)
    lab.ssh("sudo qm create 9045 --name plc-l11-e --memory 64")
    sin = tuple(p for p in PRIV_ROL if p != "VM.Audit")
    with usuario_temporal(sin) as u:
        api = ApiCruda(u.token_id, u.token_secreto)
        ids = [
            int(x["vmid"])
            for x in api.pedir("GET", "/cluster/resources", params={"type": "vm"}).json()["data"]
        ]
        evidencia("L11-sin-audit", visibles=ids)
        assert 9045 not in ids


# =========================================================================================
# LAB-L12  La simulación solo hace GET
# =========================================================================================


def _lineas_acceso() -> int:
    return int(lab.ssh(f"sudo wc -l {LOG_ACCESO}").split()[0])


def test_l12_simulacion_solo_deja_get_en_el_registro_de_acceso(sesion_plc):
    inv = descubrir(sesion_plc)
    inicio = _lineas_acceso()
    sim = simular(sesion_plc, _defn(3, 9046, "plc-l12"), inv, reloj=RelojReal())
    assert sim.plan.es_simulacion and not sim.plan.bloqueado, sim.plan.problemas
    assert sorted(sim.peticiones) == [9046, 9047, 9048]
    assert all(p["name"].startswith("plc-l12-") for p in sim.peticiones.values())

    nuevas: list[str] = []
    fin = time.monotonic() + 15
    while time.monotonic() < fin:
        salida = lab.ssh(f"sudo tail -n +{inicio + 1} {LOG_ACCESO}")
        nuevas = [ln for ln in salida.splitlines() if "plc@pve!t1" in ln]
        if len(nuevas) >= 3:
            break
        time.sleep(1)
    metodos = re.findall(r'"([A-Z]+) /', "\n".join(nuevas))
    evidencia("L12", lineas=len(nuevas), metodos=sorted(set(metodos)))
    assert len(nuevas) >= 3, "el registro de pveproxy no mostró las lecturas de la simulación"
    assert set(metodos) == {"GET"}
    assert _existentes_en_rango() == []


def test_l12_control_el_registro_de_acceso_si_muestra_un_post_real(plc, vmids):
    """Control positivo de LAB-L12: sin esto, «solo hay GET» podría ser un registro ciego."""
    vmid = vmids(9049)
    api = _api_plc(plc)
    inicio = _lineas_acceso()
    r = api.pedir(
        "POST", f"/nodes/{lab.NODO}/qemu", datos={"vmid": vmid, "name": "plc-l12-ctl", "memory": 64}
    )
    assert r.status_code == 200
    _esperar_tarea(api, r.json()["data"])
    nuevas: list[str] = []
    fin = time.monotonic() + 15
    while time.monotonic() < fin and not any('"POST /' in ln for ln in nuevas):
        nuevas = lab.ssh(f"sudo tail -n +{inicio + 1} {LOG_ACCESO}").splitlines()
        time.sleep(1)
    assert any('"POST /api2/json/nodes/pve-lab/qemu' in ln for ln in nuevas)


# =========================================================================================
# LAB-L13  Lote grande y rollback completo
# =========================================================================================


def test_l13_lote_de_30_mvs_y_rollback_completo(sesion_plc, vmids):
    """30 MVs de 1 GiB en lvm-thin (el laboratorio no tiene ``local-lvm``) y su rollback."""
    cantidad = 30
    plan, inv = _planificar(sesion_plc, _defn(cantidad, 9060, "plc-l13"))
    assert not plan.bloqueado, plan.problemas
    ids = [e.vmid for e in plan.elementos]
    vmids(*ids)
    c = _ejecutar(sesion_plc, plan, inv, maximo_s=1500)
    assert set(_estados(c.libro).values()) == {EstadoMV.OK}, c.libro.contadores()
    assert _existentes_en_rango() == ids
    evidencia(
        "L13-creacion",
        mvs=cantidad,
        segundos=round(c.segundos, 1),
        por_mv=round(c.segundos / cantidad, 1),
    )

    t0 = time.monotonic()
    cands, res = _deshacer(sesion_plc, c.libro)
    seg = time.monotonic() - t0
    evidencia("L13-rollback", segundos=round(seg, 1), por_mv=round(seg / cantidad, 1))
    assert all(x.elegible for x in cands)
    assert [r.estado for r in res] == [EstadoRollback.ELIMINADA] * cantidad
    assert _existentes_en_rango() == []
    restos = lab.ssh(f"sudo pvesm list {STORAGE}")
    assert not re.search(r"vm-90[6-8]\d-", restos), "quedaron volúmenes del lote"
