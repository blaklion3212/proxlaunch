"""Apoyo para las pruebas de interfaz: inventarios, sesión falsa y servicios falsos.

Solo contiene piezas de los límites del sistema (red, llavero, disco). No contiene
aserciones de las pruebas.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import PerfilConexion
from proxlaunch.nucleo.modelos.inventario import (
    Bridge,
    Inventario,
    Nodo,
    Storage,
    Topologia,
    Version,
)
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.servicios.conexion import (
    Aviso,
    EstadoHuella,
    InformacionHuella,
    Sesion,
)

GIB = 1024**3
HUELLA_A = ":".join(["AB"] * 32)
HUELLA_B = ":".join(["CD"] * 32)
UPID = "UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:100:root@pam:"


def storage(id_, tipo, contenido, libre_gib, activo=True):
    """Storage con espacio libre en GiB."""
    return Storage(
        id=id_,
        tipo=tipo,
        contenido=frozenset(contenido.split(",")),
        compartido=False,
        activo=activo,
        total_bytes=int(libre_gib * 2 * GIB),
        libre_bytes=int(libre_gib * GIB),
    )


def _storages_pve1():
    return (
        storage("local", "dir", "iso,backup,images", 50),
        storage("local-lvm", "lvmthin", "images,rootdir", 150),
        storage("inactivo", "lvm", "images", 100, activo=False),
    )


def inventario_cluster() -> Inventario:
    """Clúster de tres nodos: pve1 y pve3 en línea, pve2 caído."""
    return Inventario(
        version=Version("9.2", 9, 2, 0),
        topologia=Topologia(
            es_cluster=True,
            nombre_cluster="lab",
            nodos=(
                Nodo("pve1", True, 8192, 8),
                Nodo("pve2", False, None, None),
                Nodo("pve3", True, 4096, 4),
            ),
        ),
        proximo_vmid=101,
        storages={
            "pve1": _storages_pve1(),
            "pve2": (storage("local-lvm", "lvmthin", "images", 150),),
            "pve3": (storage("local-lvm", "lvmthin", "images", 100),),
        },
        bridges={
            "pve1": (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "bridge", True)),
            "pve2": (Bridge("vmbr0", "bridge", False),),
            "pve3": (Bridge("vmbr0", "bridge", False),),
        },
        errores_por_nodo={},
    )


def inventario_individual() -> Inventario:
    """Servidor individual con un nodo."""
    return Inventario(
        version=Version("9.2", 9, 2, 0),
        topologia=Topologia(
            es_cluster=False, nombre_cluster=None, nodos=(Nodo("pve", True, 8192, 8),)
        ),
        proximo_vmid=100,
        storages={"pve": _storages_pve1()},
        bridges={"pve": (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "bridge", True))},
        errores_por_nodo={},
    )


def perfil(id_="p1", nombre="Laboratorio", hosts=("10.0.0.5",), **cambios) -> PerfilConexion:
    base = {"id": id_, "nombre": nombre, "hosts": list(hosts)}
    base.update(cambios)
    return PerfilConexion(**base)


def sesion_falsa(
    perfil_: PerfilConexion | None = None,
    avisos: list[Aviso] | None = None,
    version: tuple[int, int] = (9, 2),
    forzada: bool = False,
    cliente: Any = None,
) -> Sesion:
    """Sesión sin red: el cliente es un marcador salvo que se pase uno falso (lotes)."""
    v = Version(f"{version[0]}.{version[1]}", version[0], version[1], 0)
    return Sesion(
        perfil=perfil_ or perfil(),
        cliente=cliente if cliente is not None else object(),  # type: ignore[arg-type]
        version=v,
        capacidades=capacidades_para(v, version if forzada else None),
        host_activo=(perfil_ or perfil()).hosts[0],
        usuario_efectivo="ana@pve!lab",
        avisos=avisos or [],
    )


class LlaveroFalso:
    """Backend con la interfaz de keyring, en memoria."""

    def __init__(self) -> None:
        self.datos: dict[tuple[str, str], str] = {}

    def set_password(self, servicio, clave, valor):
        self.datos[(servicio, clave)] = valor

    def get_password(self, servicio, clave):
        return self.datos.get((servicio, clave))

    def delete_password(self, servicio, clave):
        import keyring.errors

        if (servicio, clave) not in self.datos:
            raise keyring.errors.PasswordDeleteError("no existe")
        del self.datos[(servicio, clave)]


@dataclass
class ServicioConexionFalso:
    """Imita ``ServicioConexion`` sin red; registra las llamadas y devuelve lo programado."""

    infos: list[InformacionHuella] = field(default_factory=list)
    resultado_conectar: Any = None  # Sesion, DesafioTFA o ErrorProxLaunch
    resultado_tfa: Any = None  # Sesion o ErrorProxLaunch (o lista para varios intentos)
    llamadas: list[tuple] = field(default_factory=list)
    error_cerrar_sesion: Any = None  # excepción a lanzar en cerrar_sesion (opcional)

    def consultar_huellas(self, perfil_):
        self.llamadas.append(("consultar_huellas", perfil_))
        if isinstance(self.infos, ErrorProxLaunch):
            raise self.infos
        return list(self.infos)

    def confiar_huella(self, perfil_, host, huella):
        self.llamadas.append(("confiar", host, huella))

    def reemplazar_huella(self, perfil_, host, huella):
        self.llamadas.append(("reemplazar", host, huella))

    def conectar(self, perfil_, credencial, *, version_forzada=None):
        self.llamadas.append(("conectar", perfil_, credencial, version_forzada))
        return self._devolver(self.resultado_conectar)

    def completar_tfa(self, desafio, codigo, tipo):
        self.llamadas.append(("tfa", codigo, tipo))
        pendiente = self.resultado_tfa
        if isinstance(pendiente, list):
            pendiente = pendiente.pop(0)
        return self._devolver(pendiente)

    def cancelar_tfa(self, desafio):
        self.llamadas.append(("cancelar_tfa", desafio))

    def cerrar_sesion(self, sesion):
        self.llamadas.append(("cerrar_sesion", sesion))
        if isinstance(self.error_cerrar_sesion, ErrorProxLaunch | RuntimeError):
            raise self.error_cerrar_sesion

    @staticmethod
    def _devolver(valor):
        if isinstance(valor, ErrorProxLaunch):
            raise valor
        return valor


def info_huella(estado=EstadoHuella.NUEVA, host="10.0.0.5", puerto=8006, guardada=None):
    return InformacionHuella(
        host,
        puerto,
        estado,
        HUELLA_A if estado != EstadoHuella.CAMBIADA else HUELLA_B,
        guardada
        if guardada is not None
        else (HUELLA_A if estado == EstadoHuella.CAMBIADA else None),
    )


class CreacionFalsa:
    """Servicio de creación falso. ``crear`` avisa etapas y UPID y devuelve ``resultado``."""

    def __init__(self, resultado: ResultadoCreacion | BaseException, enviar_upid=True):
        self.resultado = resultado
        self.enviar_upid = enviar_upid
        self.llamadas_crear = 0
        self.liberar = threading.Event()
        self.respuestas_reanudar: list[ResultadoCreacion] = []
        self.llamadas_reanudar: list[str] = []
        self.inventarios_reanudar: list[Any] = []
        self.llamadas_existe_vm: list[Any] = []
        self.respuesta_existe_vm: bool | None = None
        self.cfgs_recibidas: list[Any] = []  # configuraciones tal como llegaron a ``crear``

    def crear(
        self, cfg, inv, al_cambiar_etapa: Callable, cancelado, *, al_enviar=None, puede_enviar=None
    ):
        self.llamadas_crear += 1
        self.cfgs_recibidas.append(cfg)
        al_cambiar_etapa(Etapa.VALIDANDO)
        # El servicio real devuelve CANCELADO sin UPID solo ANTES de enviar: nunca anuncia
        # ENVIANDO en ese caso (la máquina no salió hacia Proxmox).
        if (
            isinstance(self.resultado, ResultadoCreacion)
            and self.resultado.desenlace == Desenlace.CANCELADO
            and self.resultado.upid is None
        ):
            return self.resultado
        if puede_enviar is not None and not puede_enviar():
            return ResultadoCreacion(Desenlace.CANCELADO, cfg.vmid, cfg.nodo, None, None, [])
        al_cambiar_etapa(Etapa.ENVIANDO)
        if self.enviar_upid and al_enviar is not None:
            al_enviar(UPID)
        al_cambiar_etapa(Etapa.CREANDO)
        if isinstance(self.resultado, BaseException):
            raise self.resultado
        return self.resultado

    def seguir(self, cfg, upid, cancelado, al_cambiar_etapa, *, inv=None):
        self.llamadas_reanudar.append("seguir")
        self.inventarios_reanudar.append(inv)
        return self.respuestas_reanudar.pop(0)

    def comprobar_ahora(self, cfg, upid, *, inv=None):
        self.llamadas_reanudar.append("comprobar")
        self.inventarios_reanudar.append(inv)
        return self.respuestas_reanudar.pop(0)

    def existe_vm(self, cfg):
        self.llamadas_existe_vm.append(cfg)
        if isinstance(self.respuesta_existe_vm, BaseException):
            raise self.respuesta_existe_vm
        return self.respuesta_existe_vm


def resultado(desenlace=Desenlace.OK, error=None, upid=UPID, vmid=101, nodo="pve1", log=None):
    return ResultadoCreacion(desenlace, vmid, nodo, upid, error, log or [])


# --- Lotes (MVP 2) ------------------------------------------------------------------------


def upid_de(vmid: int, nodo: str = "pve1", usuario: str = "root@pam") -> str:
    """UPID con la forma real de Proxmox (incluye el usuario) para el VMID dado."""
    return f"UPID:{nodo}:0003A1B2:00F4C1D3:6535AB12:qmcreate:{vmid}:{usuario}:"


class CreacionPorVmid(CreacionFalsa):
    """Servicio de creación falso para lotes: un desenlace distinto por VMID.

    - ``por_vmid``: VMID -> ``ResultadoCreacion`` o excepción que lanza ``crear``; también
      puede ser una función ``cfg -> resultado`` (por ejemplo, para fallar por nodo).
    - ``puertas``: VMID -> ``Event``; la creación de esa máquina queda «en vuelo» (UPID ya
      anunciado) hasta que la prueba libere la puerta o se pida abandonar la espera.
    - ``existe_por_vmid``: VMID -> respuesta de ``existe_vm`` (si falta, ``respuesta_existe_vm``).
    Es seguro entre hilos (el motor llama a ``crear`` desde un hilo por nodo).
    """

    def __init__(self, por_vmid=None, puertas=None, existe_por_vmid=None):
        super().__init__(resultado(Desenlace.OK))
        self.por_vmid: dict[int, Any] = dict(por_vmid or {})
        self.puertas: dict[int, threading.Event] = dict(puertas or {})
        self.existe_por_vmid: dict[int, Any] = dict(existe_por_vmid or {})
        self.entraron: dict[int, threading.Event] = {}
        self.vmids_creados: list[int] = []
        self._cerrojo = threading.Lock()

    def entro(self, vmid: int) -> threading.Event:
        with self._cerrojo:
            return self.entraron.setdefault(vmid, threading.Event())

    def crear(
        self, cfg, inv, al_cambiar_etapa: Callable, cancelado, *, al_enviar=None, puede_enviar=None
    ):
        with self._cerrojo:
            self.llamadas_crear += 1
            self.vmids_creados.append(cfg.vmid)
            self.cfgs_recibidas.append(cfg)
        res = self.por_vmid.get(cfg.vmid)
        if callable(res):
            res = res(cfg)
        if res is None:
            res = resultado(Desenlace.OK, upid=upid_de(cfg.vmid), vmid=cfg.vmid, nodo=cfg.nodo)
        al_cambiar_etapa(Etapa.VALIDANDO)
        if (
            isinstance(res, ResultadoCreacion)
            and res.desenlace == Desenlace.CANCELADO
            and res.upid is None
        ):
            return res
        if puede_enviar is not None and not puede_enviar():
            return resultado(Desenlace.CANCELADO, upid=None, vmid=cfg.vmid, nodo=cfg.nodo)
        al_cambiar_etapa(Etapa.ENVIANDO)
        upid = res.upid if isinstance(res, ResultadoCreacion) else upid_de(cfg.vmid)
        if upid and al_enviar is not None:
            al_enviar(upid)
        al_cambiar_etapa(Etapa.CREANDO)
        self.entro(cfg.vmid).set()
        puerta = self.puertas.get(cfg.vmid)
        if puerta is not None:
            # En vuelo: espera la puerta o que se pida «Dejar de esperar» (sin dormir de verdad).
            for _ in range(500):
                if puerta.wait(0.01):
                    break
                if cancelado.is_set():
                    return resultado(Desenlace.CANCELADO, upid=upid, vmid=cfg.vmid, nodo=cfg.nodo)
        if isinstance(res, BaseException):
            raise res
        return res

    def existe_vm(self, cfg):
        self.llamadas_existe_vm.append(cfg)
        r = self.existe_por_vmid.get(cfg.vmid, self.respuesta_existe_vm)
        if isinstance(r, BaseException):
            raise r
        return r


class _VistaSoloLectura:
    """Cliente de solo lectura: cualquier escritura es un error de programación."""

    _LECTURAS = frozenset(
        {
            "vmid_libre",
            "vms_visibles",
            "config_vm",
            "permisos",
            "estado_actual_vm",
            "estado_tarea",
            "estado_nodo",
        }
    )

    def __init__(self, base: ClienteLoteFalso) -> None:
        self._base = base

    def __getattr__(self, nombre: str):
        if nombre in self._LECTURAS:
            return getattr(self._base, nombre)
        raise AssertionError(f"Escritura o método no permitido en simulación: {nombre}")


class ClienteLoteFalso:
    """Cliente de Proxmox falso para planificar, deshacer y reconciliar lotes (sin red)."""

    PRIVILEGIOS = (
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

    def __init__(self) -> None:
        self.vmids_ocupados: set[int] = set()
        self.visibles: list[Any] = []
        self.configs: dict[int, dict | None] = {}
        self.estados_vm: dict[int, dict] = {}
        self.privilegios_que_faltan: set[str] = set()
        self.fallo_permisos: ErrorProxLaunch | None = None
        self.fallo_vmid_libre: ErrorProxLaunch | None = None
        self.eliminar_falla: dict[int, ErrorProxLaunch] = {}
        self.eliminados: list[int] = []
        # Creación directa (cuando el motor usa el ServicioCreacion real, p. ej. al continuar).
        self.creados: list[tuple[str, dict[str, str]]] = []
        self.crear_falla: dict[int, ErrorProxLaunch] = {}
        self.nodos_caidos: dict[str, ErrorProxLaunch] = {}  # sonda ``estado_nodo`` que falla
        self.puerta_eliminar: threading.Event | None = None  # retiene el DELETE hasta liberarla
        self.llamadas: list[tuple] = []
        self.pidio_solo_lectura = 0
        self._cerrojo = threading.Lock()

    def _anotar(self, *dato) -> None:
        with self._cerrojo:
            self.llamadas.append(dato)

    def solo_lectura(self) -> _VistaSoloLectura:
        self.pidio_solo_lectura += 1
        return _VistaSoloLectura(self)

    def vmid_libre(self, vmid: int) -> bool:
        self._anotar("vmid_libre", vmid)
        if self.fallo_vmid_libre is not None:
            raise self.fallo_vmid_libre
        return vmid not in self.vmids_ocupados and not self.configs.get(vmid)

    def proximo_vmid(self, vmid: int | None = None) -> int:
        """``GET /cluster/nextid`` (con ``vmid`` valida que esté libre)."""
        self._anotar("proximo_vmid", vmid)
        usados = self.vmids_ocupados | {v for v, c in self.configs.items() if c is not None}
        if vmid is None:
            return max(usados | {99}) + 1
        if vmid in usados:
            raise ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": str(vmid)})
        return vmid

    def crear_vm(self, nodo: str, parametros: dict[str, str]) -> str:
        """``POST /nodes/{n}/qemu``: crea la MV (queda con su nombre y etiquetas)."""
        vmid = int(parametros["vmid"])
        self._anotar("crear_vm", nodo, vmid)
        if vmid in self.crear_falla:
            raise self.crear_falla[vmid]
        with self._cerrojo:
            self.creados.append((nodo, dict(parametros)))
        self.configs[vmid] = {"name": parametros.get("name"), "tags": parametros.get("tags", "")}
        return upid_de(vmid, nodo)

    def log_tarea(self, nodo: str, upid: str) -> list[str]:
        return []

    def vms_visibles(self) -> list[Any]:
        self._anotar("vms_visibles")
        return list(self.visibles)

    def permisos(self) -> dict[str, dict[str, int]]:
        self._anotar("permisos")
        if self.fallo_permisos is not None:
            raise self.fallo_permisos
        return {"/": {p: 1 for p in self.PRIVILEGIOS if p not in self.privilegios_que_faltan}}

    def config_vm(self, nodo: str, vmid: int):
        self._anotar("config_vm", nodo, vmid)
        return self.configs.get(vmid)

    def estado_nodo(self, nodo: str) -> dict:
        """``GET /nodes/{n}/status``: responde salvo que el nodo esté en ``nodos_caidos``."""
        self._anotar("estado_nodo", nodo)
        if nodo in self.nodos_caidos:
            raise self.nodos_caidos[nodo]
        return {"uptime": 1}

    def estado_actual_vm(self, nodo: str, vmid: int) -> dict:
        self._anotar("estado_actual_vm", nodo, vmid)
        return self.estados_vm.get(vmid, {"status": "stopped"})

    def eliminar_vm(self, nodo: str, vmid: int) -> str:
        self._anotar("eliminar_vm", nodo, vmid)
        if self.puerta_eliminar is not None:
            self.puerta_eliminar.wait(5)
        if vmid in self.eliminar_falla:
            raise self.eliminar_falla[vmid]
        self.eliminados.append(vmid)
        self.configs[vmid] = None
        return f"UPID:{nodo}:0003A1B2:00F4C1D3:6535AB12:qmdestroy:{vmid}:root@pam:"

    def estado_tarea(self, nodo: str, upid: str):
        from proxlaunch.nucleo.modelos.tarea import EstadoTarea

        self._anotar("estado_tarea", nodo, upid)
        return EstadoTarea(estado="stopped", exitstatus="OK")
