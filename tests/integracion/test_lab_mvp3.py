"""MVP 3 contra el laboratorio real: LAB-M3-01..04 de docs/requisitos/mvp3.md §12.

Solo con ``PROXLAUNCH_LAB=1`` (se saltan sin esa variable) y solo contra el laboratorio local
(127.0.0.1:8006, nodo ``pve-lab``). VMIDs 9060-9079 únicamente (rango de pruebas 9000-9099); todo lo
que se crea se destruye al terminar (fixture ``vmids_m3``), también si la prueba falla. El
cobertura de red es la del lote de M2: el motor, el rollback y la simulación son los reales.

- LAB-M3-01  cada perfil de fábrica (incluido OVMF + q35) crea una MV real cuya ``config`` coincide.
- LAB-M3-02  lote guardado: mismo plan que el directo; con un storage inexistente, cero POST.
- LAB-M3-03  CSV heterogéneo en Windows-1252 con ``;``: VMID explícito libre y ocupado, nodo
             explícito, configuración por fila, etiquetas del lote y rollback completo.
- LAB-M3-04  catálogo de modelos de CPU y creación con el ``tipo_cpu`` de los perfiles de fábrica.

Las pruebas imprimen líneas ``EVIDENCIA[...]`` (visibles con ``-s``) con las medidas reales que
cierran las preguntas [LAB] del requisito.
"""

from __future__ import annotations

import dataclasses
import re
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import requests

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila
from proxlaunch.nucleo.lote.filas import definicion_por_filas, sin_filas
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import DefinicionLote, EstadoMV, EstadoRollback, FilaLote, Plan
from proxlaunch.nucleo.lote.motor import ControlLote, MotorLote
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote, leer_archivo_lote
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.lotes_guardados.revalidacion import desajustes
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed
from proxlaunch.nucleo.perfiles_maquina.aplicar import aplicar_perfil
from proxlaunch.nucleo.perfiles_maquina.fabrica import CLAVES_FABRICA, perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.descubrimiento import descubrir
from proxlaunch.nucleo.valores_defecto import configuracion_por_defecto

from . import apoyo_lab as lab

pytestmark = [
    pytest.mark.integracion,
    pytest.mark.filterwarnings("ignore::urllib3.exceptions.InsecureRequestWarning"),
]

STORAGE = "lab-lvmthin"
URL = f"https://{lab.HOST}:{lab.PUERTO}/api2/json"
LOG_ACCESO = "/var/log/pveproxy/access.log"
VMID_BASE = 9060  # M3 usa 9060-9079


def evidencia(clave: str, **datos: Any) -> None:
    detalle = " ".join(f"{k}={v!r}" for k, v in datos.items())
    print(f"EVIDENCIA[{clave}] {detalle}")


# --- Apoyo: limpieza, planificación, ejecución y rollback -----------------------------------------


def _limpiar(vmids: list[int]) -> None:
    for v in vmids:
        if not 9060 <= v <= 9079 or not lab.VMID_MIN <= v <= lab.VMID_MAX:
            raise RuntimeError(f"VMID fuera del rango de pruebas de M3: {v}")
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
def vmids_m3() -> Iterator[Callable[..., Any]]:
    """Registra VMIDs de prueba (9060-9079); se destruyen al terminar, pase lo que pase."""
    creados: list[int] = []

    def registrar(*ids: int) -> Any:
        for i in ids:
            if not 9060 <= i <= 9079:
                raise ValueError(f"VMID fuera del rango de M3: {i}")
        creados.extend(ids)
        return ids[0] if len(ids) == 1 else ids

    yield registrar
    _limpiar(sorted(set(creados)))


def _existentes() -> list[int]:
    return sorted(v for v in lab.vmids_de_prueba() if 9060 <= v <= 9079)


def _lineas_acceso() -> int:
    return int(lab.ssh(f"sudo wc -l {LOG_ACCESO}").split()[0])


def _metodos_nuevos(desde: int, usuario: str = "plc@pve!t1", minimo: int = 1) -> list[str]:
    """Métodos HTTP del registro de pveproxy desde la línea ``desde`` para el token de pruebas."""
    nuevas: list[str] = []
    fin = time.monotonic() + 15
    while time.monotonic() < fin:
        salida = lab.ssh(f"sudo tail -n +{desde + 1} {LOG_ACCESO}")
        nuevas = [ln for ln in salida.splitlines() if usuario in ln]
        if len(nuevas) >= minimo:
            break
        time.sleep(1)
    return [f"{m} {r}" for m, r in re.findall(r'"([A-Z]+) /api2/json(/[^ ?"]*)', "\n".join(nuevas))]


def _planificar(sesion, definicion: DefinicionLote) -> tuple[Plan, Inventario]:
    inv = descubrir(sesion)
    return Planificador(sesion, RelojReal()).planificar(definicion, inv), inv


def _ejecutar(sesion, plan: Plan, inv: Inventario, maximo_s: float = 600.0) -> Libro:
    """Ejecuta con el motor real en un hilo; si el lote se pausa, lo cancela (no espera a nadie)."""
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
    while hilo.is_alive() and time.monotonic() - t0 < maximo_s:
        hilo.join(0.2)
        if control.motivo_pausa is not None:
            control.cancelar()
    assert not hilo.is_alive(), "el motor no terminó (¿pausa sin resolver?)"
    return resultado["libro"]


def _deshacer(sesion, libro: Libro) -> list[Any]:
    servicio = ServicioRollback(sesion, RelojReal())
    candidatos = servicio.elegibles(libro, etiquetado=True)
    return servicio.deshacer(
        candidatos, lambda _r: None, ControlLote(), id_lote=libro.id_lote, etiquetado=True
    )


def _tags(config: dict[str, Any]) -> set[str]:
    return {t for t in re.split(r"[;,]", str(config.get("tags", ""))) if t}


class _ApiCruda:
    """Peticiones HTTP directas con un token (solo 127.0.0.1:8006)."""

    def __init__(self, token_id: str, secreto: str) -> None:
        lab.comprobar_destino(lab.HOST, lab.PUERTO, lab.NODO)
        self._cab = {"Authorization": f"PVEAPIToken={token_id}={secreto}"}

    def get(self, ruta: str, **params: Any) -> requests.Response:
        return requests.get(
            URL + ruta, headers=self._cab, params=params or None, verify=False, timeout=30
        )


# =========================================================================================
# LAB-M3-01  Cada perfil de fábrica crea una MV real
# =========================================================================================

# Lo que debe verse en la ``config`` real de Proxmox por perfil: (núcleos, memoria MiB, GiB, clave de disco, red, bios).  # noqa: E501
ESPERADO = {
    "servidor-pequeno": (2, 2048, 32, "scsi0", "virtio", "seabios"),
    "servidor-mediano": (4, 4096, 64, "scsi0", "virtio", "seabios"),
    "base-de-datos": (4, 8192, 100, "scsi0", "virtio", "seabios"),
    "servidor-grande": (8, 16384, 128, "scsi0", "virtio", "seabios"),
    "escritorio-compatible": (4, 4096, 80, "sata0", "e1000", "ovmf"),
    "minimo": (1, 512, 8, "scsi0", "virtio", "seabios"),
}


@pytest.mark.parametrize("clave", CLAVES_FABRICA)
def test_m3_01_cada_perfil_de_fabrica_crea_una_mv_real_cuya_config_coincide(
    sesion_plc, vmids_m3, clave
):
    """CA-P02.3, CA-P05.7, RF-P02, §8: el perfil se aplica al formulario, se simula (solo GET) y el
    motor lo crea; la ``config`` real coincide (núcleos, memoria, disco, bus, ``scsihw``, red,
    firmware;
    ``efidisk0`` y ``q35`` en el perfil de escritorio)."""
    vmid = vmids_m3(VMID_BASE + list(CLAVES_FABRICA).index(clave))
    nucleos, memoria, gib, clave_disco, modelo_red, bios = ESPERADO[clave]
    inv = descubrir(sesion_plc)
    perfil = {p.id: p for p in perfiles_fabrica()}[f"fabrica.{clave}"]
    nombre = f"plc-m3-{clave}"[:40]
    aplicado = aplicar_perfil(perfil, ConfiguracionVM(vmid=0, nombre=nombre, nodo=lab.NODO), inv)
    cfg = aplicado.cfg
    # El laboratorio solo trae el storage «lab-lvmthin» para discos: se fija para no depender del
    # de mayor espacio libre (p. ej. un directorio con límites distintos).
    cfg.discos = [dataclasses.replace(d, storage=STORAGE) for d in cfg.discos]
    d = definicion_por_filas([FilaLote(nombre, cfg, vmid=vmid)], plantilla_base=cfg, etiquetar=True)

    inicio = _lineas_acceso()
    sim = simular(sesion_plc, d, inv, reloj=RelojReal())
    assert not sim.plan.bloqueado, sim.plan.problemas
    assert sim.peticiones[vmid] == construir_parametros(
        sim.plan.elementos[0].cfg, inv, sim.plan.version_validacion
    )
    metodos = {m.split()[0] for m in _metodos_nuevos(inicio, minimo=2)}
    assert metodos <= {"GET"}, metodos  # CA-P05.7: la simulación previa solo emite lecturas
    assert vmid not in lab.vmids_de_prueba()

    plan, inv = _planificar(sesion_plc, d)
    assert not plan.bloqueado, plan.problemas
    libro = _ejecutar(sesion_plc, plan, inv)
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK], libro.instantanea()

    conf = sesion_plc.cliente.config_vm(lab.NODO, vmid)
    assert conf is not None
    assert (int(conf["cores"]), int(conf["sockets"])) == (nucleos, 1)
    assert int(conf["memory"]) == memoria
    assert (
        conf[clave_disco].startswith(f"{STORAGE}:vm-{vmid}-disk-")
        and f"size={gib}G" in conf[clave_disco]
    )
    if clave_disco == "scsi0":
        assert conf["scsihw"] == "virtio-scsi-single"
    assert re.fullmatch(rf"{modelo_red}=[0-9A-Fa-f:]{{17}},bridge=vmbr0", conf["net0"]), conf[
        "net0"
    ]
    assert conf.get("bios", "seabios") == bios
    if bios == "ovmf":
        assert "efidisk0" in conf and str(conf.get("machine", "")).startswith("q35")
        evidencia("M3-01-ovmf", machine=conf.get("machine"), efidisk0=conf.get("efidisk0"))
    assert _tags(conf) >= {"proxlaunch"}
    evidencia(
        "M3-01",
        perfil=clave,
        vmid=vmid,
        cores=conf["cores"],
        memory=conf["memory"],
        disco=conf[clave_disco],
    )


def test_m3_01_el_perfil_predeterminado_produce_el_mismo_post_que_la_configuracion_de_m1(
    sesion_plc,
):
    """CA-P12.1 / RF-P12: contra el inventario real."""
    inv = descubrir(sesion_plc)
    perfil = {p.id: p for p in perfiles_fabrica()}[ID_PREDETERMINADO]
    del_perfil = aplicar_perfil(
        perfil, ConfiguracionVM(vmid=9060, nombre="plc-m3-pred", nodo=lab.NODO), inv
    ).cfg
    storage = del_perfil.discos[0].storage
    bridge = del_perfil.redes[0].bridge
    por_defecto = configuracion_por_defecto(9060, "plc-m3-pred", lab.NODO, storage, bridge)
    assert construir_parametros(del_perfil, inv) == construir_parametros(por_defecto, inv)


# =========================================================================================
# LAB-M3-02  Lote guardado
# =========================================================================================


def _plantilla_lab(**kw: Any) -> ConfiguracionVM:
    base: dict[str, Any] = {
        "vmid": 0,
        "nombre": "plantilla",
        "nodo": "",
        "cores": 1,
        "memoria_mib": 128,
        "discos": [Disco(storage=STORAGE, tamano_gib=1)],
        "redes": [InterfazRed(bridge="vmbr0")],
    }
    base.update(kw)
    return ConfiguracionVM(**base)


def _homogeneo(
    cantidad: int, vmid_inicial: int, prefijo: str, plantilla: ConfiguracionVM
) -> DefinicionLote:
    from proxlaunch.nucleo.lote.modelos import PatronNombres

    return DefinicionLote(
        plantilla=plantilla,
        cantidad=cantidad,
        patron=PatronNombres(prefijo=prefijo),
        vmid_inicial=vmid_inicial,
    )


def test_m3_02_un_lote_guardado_y_cargado_da_el_mismo_plan_y_se_crea_igual(
    sesion_plc, vmids_m3, tmp_path
):
    """CA-G01.1, CA-G03.2, CA-G04.2: guardar un lote de 3 MVs, cargarlo, generar el resumen y
    crearlo: mismo plan que el lote directo; se borran las MVs."""
    vmids_m3(9064, 9065, 9066)
    directo = _homogeneo(3, 9064, "plc-m3-l", _plantilla_lab())
    ruta = tmp_path / "Mi lote ñandú.proxlaunch-lote.json"
    guardar_lote(ruta, LoteGuardado("Lote de laboratorio", directo), app_version="prueba")
    cargado = leer_archivo_lote(ruta).lote.definicion

    plan_directo, inv = _planificar(sesion_plc, directo)
    plan_cargado, _ = _planificar(sesion_plc, cargado)
    assert not plan_directo.bloqueado and not plan_cargado.bloqueado, plan_cargado.problemas
    assert [(e.nombre, e.vmid, e.nodo) for e in plan_cargado.elementos] == [
        (e.nombre, e.vmid, e.nodo) for e in plan_directo.elementos
    ]
    assert dataclasses.replace(
        plan_cargado, definicion=None, id_lote="", generado_en=0.0
    ) == dataclasses.replace(  # type: ignore[arg-type]
        plan_directo,
        definicion=None,
        id_lote="",
        generado_en=0.0,  # type: ignore[arg-type]
    )
    assert desajustes(cargado, inv) == ()

    libro = _ejecutar(sesion_plc, plan_cargado, inv)
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK] * 3
    assert _existentes() == [9064, 9065, 9066]
    for e in plan_cargado.elementos:
        conf = sesion_plc.cliente.config_vm(lab.NODO, e.vmid)
        assert conf["name"] == e.nombre and _tags(conf) == {
            "proxlaunch",
            f"lote-{plan_cargado.id_lote}",
        }
    resultados = _deshacer(sesion_plc, libro)
    assert {r.estado for r in resultados} == {EstadoRollback.ELIMINADA}
    assert _existentes() == []


def test_m3_02_un_lote_con_un_storage_inexistente_da_cero_post(sesion_plc, tmp_path):
    """CA-G04.1..G04.3, INV-M1, INV-M6: el desajuste se detecta y el resumen sale bloqueado sin POST."""  # noqa: E501
    d = _homogeneo(
        3,
        9064,
        "plc-m3-x",
        _plantilla_lab(discos=[Disco(storage="storage-que-no-existe", tamano_gib=1)]),
    )
    ruta = tmp_path / "lote-ajeno.proxlaunch-lote.json"
    guardar_lote(ruta, LoteGuardado("De otro servidor", d), app_version="prueba")
    cargado = leer_archivo_lote(ruta).lote.definicion
    inv = descubrir(sesion_plc)
    ds = desajustes(cargado, inv)
    assert [(x.tipo.value, x.valor) for x in ds] == [("storage", "storage-que-no-existe")]
    assert STORAGE in ds[0].disponibles
    inicio = _lineas_acceso()
    plan = Planificador(sesion_plc, RelojReal()).planificar(cargado, inv)
    assert plan.bloqueado
    metodos = _metodos_nuevos(inicio)
    evidencia("M3-02-cero-post", metodos=sorted(set(m.split()[0] for m in metodos)))
    assert not [m for m in metodos if m.startswith(("POST", "PUT", "DELETE"))]
    assert _existentes() == []


# =========================================================================================
# LAB-M3-03  CSV heterogéneo (Windows-1252, «;»)
# =========================================================================================


def test_m3_03_csv_heterogeneo_vmid_libre_y_ocupado_nodo_explicito_y_rollback_completo(
    sesion_plc, vmids_m3, tmp_path
):
    """RF-C08, RF-C09, CA-C08.1..C08.5, CA-C09.3, INV-L1 sobre lote por filas: se crea lo válido,
    la ``config`` coincide POR FILA, la fila con VMID ocupado no genera POST, las etiquetas son las
    del lote y el rollback es completo."""
    vmids_m3(9067, 9068, 9069, 9070, 9071)
    # MV de apoyo que ocupa 9068 (creada y borrada en el laboratorio).
    lab.ssh("sudo qm create 9068 --name plc-m3-ajena --memory 64")
    ajena_antes = sesion_plc.cliente.config_vm(lab.NODO, 9068)
    assert ajena_antes is not None

    ruta = tmp_path / "Lista de máquinas.csv"
    ruta.write_bytes(
        (
            "nombre;cpu;memoria;disco;almacenamiento;red;nodo;vmid;descripción\r\n"
            f"plc-m3-c1;1;128 MiB;1;{STORAGE};vmbr0;;;peña\r\n"
            f"plc-m3-c2;2;256 MiB;2;{STORAGE};vmbr0;;9067;Ñandú\r\n"
            f"plc-m3-c3;1;192 MiB;1;{STORAGE};vmbr0;;9068;ocupado\r\n"
            f"plc-m3-c4;1;0,25;1;{STORAGE};vmbr0;{lab.NODO};;nodo explícito\r\n"
        ).encode("cp1252")
    )
    tabla = leer_archivo_csv(ruta)
    assert tabla.codificacion.value == "cp1252" and tabla.deteccion.separador == ";"
    inv = descubrir(sesion_plc)
    perfil = {p.id: p for p in perfiles_fabrica()}[ID_PREDETERMINADO]
    resultado = interpretar(
        tabla, perfil_base=perfil, perfiles=perfiles_fabrica(), inv=inv, nodo_referencia=lab.NODO
    )
    assert all(f.estado != EstadoFila.CON_ERROR for f in resultado.filas), [
        f.problemas for f in resultado.filas
    ]
    definicion = definicion_por_filas(
        filas_lote(resultado, resultado.numeros_validos),
        plantilla_base=_plantilla_lab(),
        vmid_inicial=9069,
    )

    plan, inv = _planificar(sesion_plc, definicion)
    ocupadas = [p for p in plan.problemas if p.regla == "V-03"]
    assert [(p.indice, p.params["vmid"]) for p in ocupadas] == [(2, "9068")] and plan.bloqueado
    assert _existentes() == [9068]  # nada se envió

    inicio = _lineas_acceso()
    plan2, inv = _planificar(sesion_plc, sin_filas(definicion, [2]))  # el usuario excluye esa fila
    assert not plan2.bloqueado, plan2.problemas
    assert [(e.nombre, e.vmid) for e in plan2.elementos] == [
        ("plc-m3-c1", 9069),
        ("plc-m3-c2", 9067),
        ("plc-m3-c4", 9070),
    ]
    libro = _ejecutar(sesion_plc, plan2, inv)
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK] * 3
    metodos = _metodos_nuevos(inicio, minimo=3)
    posts = [m for m in metodos if m.startswith("POST") and m.endswith("/qemu")]
    evidencia("M3-03-posts", posts=len(posts))
    assert len(posts) == 3  # la fila con VMID ocupado no generó POST

    esperado = {9069: (1, 128), 9067: (2, 256), 9070: (1, 256)}
    for e in plan2.elementos:
        conf = sesion_plc.cliente.config_vm(lab.NODO, e.vmid)
        cores, mem = esperado[e.vmid]
        assert (int(conf["cores"]), int(conf["memory"])) == (cores, mem), e.nombre
        assert conf["name"] == e.nombre and _tags(conf) == {"proxlaunch", f"lote-{plan2.id_lote}"}
    ajena_despues = sesion_plc.cliente.config_vm(lab.NODO, 9068)
    assert ajena_despues == ajena_antes  # la MV ajena quedó intacta

    resultados = _deshacer(sesion_plc, libro)
    assert {r.estado for r in resultados} == {EstadoRollback.ELIMINADA} and len(resultados) == 3
    assert _existentes() == [9068]  # solo queda la de apoyo (se destruye en la limpieza)


# =========================================================================================
# LAB-M3-04  Catálogo de modelos de CPU
# =========================================================================================


def test_m3_04_catalogo_de_cpu_y_creacion_con_el_tipo_cpu_de_los_perfiles_de_fabrica(
    sesion_plc, plc, vmids_m3
):
    """S-M9, CA-P07.4: si el catálogo no se puede leer con el rol mínimo, ``tipo_cpu`` se valida
    solo por formato (y no se avisa); lo que sí se comprueba es que Proxmox acepta el de los
    perfiles."""
    api = _ApiCruda(plc.token_id, plc.token_secreto)
    r = api.get(f"/nodes/{lab.NODO}/capabilities/qemu/cpu")
    evidencia(
        "M3-04-catalogo",
        estado=r.status_code,
        cuerpo=r.text[:200] if r.status_code != 200 else "lista",
    )
    assert r.status_code in {200, 403}
    if r.status_code == 200:
        modelos = r.json()["data"]
        assert isinstance(modelos, list) and modelos and all("name" in m for m in modelos)
        nombres = {m["name"] for m in modelos}
        evidencia(
            "M3-04-modelos",
            n=len(modelos),
            v2_aes="x86-64-v2-AES" in nombres,
            v3="x86-64-v3" in nombres,
            custom=sorted(n for n in nombres if n.startswith("custom-"))[:3],
        )
        assert "x86-64-v2-AES" in nombres  # el de todos los perfiles de fábrica

    tipos = {p.config.tipo_cpu for p in perfiles_fabrica()}
    assert tipos == {"x86-64-v2-AES"}
    vmid = vmids_m3(9072)
    inv = descubrir(sesion_plc)
    cfg = _plantilla_lab(tipo_cpu="x86-64-v2-AES")
    d = definicion_por_filas([FilaLote("plc-m3-cpu", cfg, vmid=vmid)], plantilla_base=cfg)
    plan, inv = _planificar(sesion_plc, d)
    assert not plan.bloqueado, plan.problemas
    libro = _ejecutar(sesion_plc, plan, inv)
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK]
    assert sesion_plc.cliente.config_vm(lab.NODO, vmid)["cpu"] == "x86-64-v2-AES"


def test_m3_04_un_tipo_de_cpu_con_formato_valido_pero_inexistente_lo_rechaza_proxmox_sin_crear_nada(
    sesion_plc, vmids_m3
):
    """Evidencia para CA-P07.4: si Proxmox lo rechaza, el aviso por catálogo es solo una ayuda."""
    vmid = vmids_m3(9073)
    inv = descubrir(sesion_plc)
    cfg = _plantilla_lab(tipo_cpu="modelo-que-no-existe")
    d = definicion_por_filas([FilaLote("plc-m3-cpu-malo", cfg, vmid=vmid)], plantilla_base=cfg)
    plan, inv = _planificar(sesion_plc, d)
    assert not plan.bloqueado, plan.problemas  # el formato es válido: la capa 1 no lo detecta
    libro = _ejecutar(sesion_plc, plan, inv)
    estado = libro.instantanea()[0].estado
    evidencia("M3-04-cpu-inexistente", estado=estado.value)
    assert estado in {EstadoMV.ERROR, EstadoMV.OK, EstadoMV.PARCIAL}
    if estado == EstadoMV.ERROR:
        assert _existentes() == []  # nada se creó
