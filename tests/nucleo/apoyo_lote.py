"""Apoyo para las pruebas del núcleo de lotes (MVP 2).

Contiene: un clúster simulado en memoria (``Cluster``) con inyección de fallos y contadores
de métodos HTTP, dos formas de ponerlo delante del cliente (``TransporteCluster``, directo, y
``instalar_http``, que lo sirve a través del ``TransporteHttp`` real con ``responses``), un
reloj simulado seguro entre hilos, constructores de inventario y plantilla, y un ``Banco``
que une sesión, motor y observador. No contiene aserciones de las pruebas.

Los límites del sistema que se simulan son la red, el reloj y el servidor de Proxmox; todo
lo demás es código real del núcleo.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlencode, urlsplit

from proxlaunch.nucleo.api.autenticacion import Autenticador
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    DefinicionLote,
    Destino,
    EntradaLibro,
    ModoDestino,
    PatronNombres,
    Plan,
)
from proxlaunch.nucleo.lote.motor import ControlLote, MotorLote
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.modelos import (
    Bridge,
    ConfiguracionVM,
    Disco,
    InterfazRed,
    Inventario,
    Nodo,
    Storage,
    Topologia,
    Version,
)
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.servicios.conexion import Sesion

from .apoyo_api import Llamada, crear_sesion

GIB = 1024**3
MIB = 1024**2

# Secretos centinela únicos (RNF-L06): ninguno puede aparecer en una salida del lote.
CENTINELA_TOKEN = "SENTINELA-lote-token-5d1e8c"
CENTINELA_TICKET = "PVE:root@pam:SENTINELALOTE::c2lnTE9URQ"
CENTINELA_CSRF = "SENTINELALOTE:Y3NyZkxPVEU"
CENTINELA_CLAVE = "SENTINELA-lote-clave-9a77"
TODOS_LOS_CENTINELAS = (CENTINELA_TOKEN, CENTINELA_TICKET, CENTINELA_CSRF, CENTINELA_CLAVE)

HOST = "10.0.0.1"
USUARIO = "ana@pve!lab"


# --- Reloj seguro entre hilos ---------------------------------------------------------------


class RelojSeguro(RelojSimulado):
    """``RelojSimulado`` con cerrojo: el motor lo usa desde varios hilos de nodo."""

    def __init__(self, inicio: float = 0.0) -> None:
        super().__init__(inicio)
        self._cerrojo = threading.Lock()

    def ahora(self) -> float:
        with self._cerrojo:
            return super().ahora()

    def avanzar(self, segundos: float) -> None:
        with self._cerrojo:
            super().avanzar(segundos)


# --- Constructores de inventario y plantilla ---------------------------------------------------


def storage(
    id_: str,
    tipo: str = "dir",
    libre_gib: float = 500,
    *,
    compartido: bool = False,
    activo: bool = True,
    contenido: str = "images",
) -> Storage:
    return Storage(
        id=id_,
        tipo=tipo,
        contenido=frozenset(contenido.split(",")),
        compartido=compartido,
        activo=activo,
        total_bytes=int(libre_gib * 4 * GIB),
        libre_bytes=int(libre_gib * GIB),
    )


def nodo(
    nombre: str, mem_gib: float | None = 64, *, en_linea: bool = True, cpus: int | None = 16
) -> Nodo:
    return Nodo(nombre, en_linea, None if mem_gib is None else int(mem_gib * 1024), cpus)


def inventario(
    nodos: tuple[Nodo, ...] | None = None,
    *,
    storages: dict[str, tuple[Storage, ...]] | None = None,
    bridges: dict[str, tuple[Bridge, ...]] | None = None,
    libre_gib: float = 500,
    tipo_storage: str = "dir",
    proximo_vmid: int = 100,
    version: Version | None = None,
    es_cluster: bool = True,
) -> Inventario:
    """Inventario de clúster; por defecto 3 nodos con 64/32/32 GiB y el storage ``datos``.

    ``storages``/``bridges`` sustituyen lo predeterminado (por nombre de nodo).
    """
    nodos = nodos or (nodo("pve1", 64), nodo("pve2", 32), nodo("pve3", 32))
    nombres = [n.nombre for n in nodos]
    return Inventario(
        version=version or Version("9.2.1", 9, 2, 1),
        topologia=Topologia(es_cluster, "lab" if es_cluster else None, nodos),
        proximo_vmid=proximo_vmid,
        storages=storages
        if storages is not None
        else {n: (storage("datos", tipo_storage, libre_gib),) for n in nombres},
        bridges=bridges
        if bridges is not None
        else {n: (Bridge("vmbr0", "bridge", False),) for n in nombres},
        errores_por_nodo={},
    )


def plantilla(**cambios: Any) -> ConfiguracionVM:
    """Plantilla de lote válida sobre ``inventario()``: 8 GiB de RAM y un disco de 32 GiB."""
    base: dict[str, Any] = {
        "vmid": 0,
        "nombre": "plantilla",
        "nodo": "",
        "memoria_mib": 8192,
        "discos": [Disco("datos", 32)],
        "redes": [InterfazRed("vmbr0")],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def definicion(
    cantidad: int = 3,
    *,
    prefijo: str = "web",
    separador: str = "-",
    inicio: int = 1,
    relleno: int = 2,
    modo: ModoDestino = ModoDestino.AUTOMATICO,
    nodos: tuple[str, ...] = (),
    algoritmo: Algoritmo = Algoritmo.EQUILIBRADO,
    plantilla_vm: ConfiguracionVM | None = None,
    **otros: Any,
) -> DefinicionLote:
    return DefinicionLote(
        plantilla=plantilla_vm or plantilla(),
        cantidad=cantidad,
        patron=PatronNombres(prefijo, separador, inicio, relleno),
        destino=Destino(modo, nodos, algoritmo),
        **otros,
    )


# --- Clúster simulado ---------------------------------------------------------------------------


def upid_de(nodo_: str, vmid: int, tipo: str = "qmcreate") -> str:
    return f"UPID:{nodo_}:0003A1B2:00F4C1D3:6535AB12:{tipo}:{vmid}:root@pam:"


_RE_UPID_VMID = re.compile(
    r"UPID:[^:]+:[^:]+:[^:]+:[^:]+:(qmcreate|qmdestroy|qmstop|qmtemplate):(\d+):"
)
_RE_QEMU = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu$")
_RE_CONFIG = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/config$")
_RE_ACTUAL = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/status/current$")
_RE_STOP = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/status/stop$")
_RE_QEMU_VM = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)$")
_RE_ESTADO_NODO = re.compile(r"^/nodes/(?P<n>[^/]+)/status$")
_RE_TAREA = re.compile(r"^/nodes/(?P<n>[^/]+)/tasks/(?P<u>.+)/(?P<q>status|log)$")
# Fase B (0.7): agente invitado, conversión en plantilla y listado de snippets.
_RE_AGENTE = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/agent/network-get-interfaces$")
_RE_PLANTILLA = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/template$")
_RE_CONTENIDO = re.compile(r"^/nodes/(?P<n>[^/]+)/storage/(?P<s>[^/]+)/content$")
_RE_CLONAR = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/clone$")


@dataclass
class Http:
    """Respuesta HTTP de error (solo para el camino ``instalar_http``)."""

    estado: int
    motivo: str = ""
    cuerpo: dict[str, Any] | str | None = None


@dataclass
class Regla:
    """Inyección de fallo: si (método, ruta) casan, ``accion`` decide (lanza o devuelve).

    ``veces=None`` = siempre; si no, se agota tras ese número de disparos. ``accion`` recibe la
    ``Llamada`` y puede devolver el valor de la respuesta o ``NORMAL`` para seguir la ruta normal.
    """

    metodo: str
    patron: str
    accion: Callable[[Llamada], Any]
    veces: int | None = None
    disparos: int = 0

    def aplica(self, metodo: str, ruta: str) -> bool:
        if self.metodo != metodo or re.search(self.patron, ruta) is None:
            return False
        return self.veces is None or self.disparos < self.veces


class _Normal:
    """Valor centinela: la regla no resuelve la petición, sigue la ruta normal."""


NORMAL = _Normal()


def lanzar(excepcion: BaseException) -> Callable[[Llamada], Any]:
    def _accion(_: Llamada) -> Any:
        raise excepcion

    return _accion


def nodo_caido(nodo_: str = "pve1", estado: int = 596) -> ErrorProxLaunch:
    """El error que produce el transporte real ante un 595/596/597 en un GET."""
    return ErrorProxLaunch(
        CodigoError.NODO_NO_DISPONIBLE,
        {"nodo": nodo_, "estado_http": str(estado)},
        f"HTTP {estado}",
    )


def envio_incierto() -> ErrorProxLaunch:
    """El error del transporte real ante un POST que pudo llegar (596/597, conexión abortada)."""
    return ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE,
        {"host": HOST, "motivos": f"{HOST}=596", "incierto": "1"},
        "HTTP 596",
    )


def error_http(estado: int, mensaje: str, nodo: str = "pve1") -> ErrorProxLaunch:
    """El error que produce el traductor real ante una respuesta HTTP de error de Proxmox."""
    from proxlaunch.nucleo.api.traductor_errores import traducir_http

    cuerpo = json.dumps({"data": None, "message": mensaje})
    return traducir_http(estado, mensaje, cuerpo, nodo=nodo)


def respuesta_agente(*interfaces: tuple[str, str | None, tuple[str, ...]]) -> dict[str, Any]:
    """``data`` de ``network-get-interfaces``: ``(nombre, mac, (ip, ...))`` por interfaz."""
    resultado = []
    for nombre, mac, ips in interfaces:
        direcciones = [
            {
                "ip-address": ip,
                "ip-address-type": "ipv6" if ":" in ip else "ipv4",
                "prefix": 64 if ":" in ip else 24,
            }
            for ip in ips
        ]
        entrada: dict[str, Any] = {"name": nombre, "ip-addresses": direcciones}
        if mac is not None:
            entrada["hardware-address"] = mac
        resultado.append(entrada)
    return {"result": resultado}


# --- Respuestas de la API de la fase D (0.9) ----------------------------------------------------


def mapeo_api(
    id_: str,
    *entradas: tuple[str, str],
    descripcion: str = "",
    mdev: bool | None = None,
    migrable: bool | None = None,
) -> dict[str, Any]:
    """Un elemento de ``GET /cluster/mapping/pci|usb``: ``entradas`` = ``(nodo, ruta)``."""
    fila: dict[str, Any] = {
        "id": id_,
        "description": descripcion,
        "map": [f"node={n},path={ruta},id=10de:2236" for n, ruta in entradas],
    }
    if mdev is not None:
        fila["mdev"] = int(mdev)
    if migrable is not None:
        fila["live-migration-capable"] = int(migrable)
    return fila


def modelo_cpu_api(
    nombre: str, *, custom: bool = False, abstract: bool = False, vendor: str = "default"
) -> dict[str, Any]:
    """Un elemento de ``GET /nodes/{n}/capabilities/qemu/cpu``."""
    return {
        "name": nombre,
        "custom": int(custom),
        "vendor": vendor,
        **({"abstract": 1} if abstract else {}),
    }


def estado_nodo_api(maquina: str | None = "x86_64", **extra: Any) -> dict[str, Any]:
    """``data`` de ``GET /nodes/{n}/status`` con ``current-kernel.machine`` (sin él, ``None``)."""
    datos: dict[str, Any] = {"uptime": 12345, "pveversion": "pve-manager/9.2.1"}
    if maquina is not None:
        datos["current-kernel"] = {"machine": maquina, "sysname": "Linux", "release": "6.17"}
    datos.update(extra)
    return datos


class Cluster:
    """Servidor de Proxmox simulado: estado, rutas de la API usadas por el lote y contadores.

    Seguro entre hilos. ``metodos`` cuenta los métodos HTTP recibidos; ``posts`` los POST de
    creación por VMID; ``deletes`` los DELETE por VMID.
    """

    def __init__(self, nodos: tuple[str, ...] = ("pve1",)) -> None:
        self.nodos = nodos
        self._cerrojo = threading.Lock()
        self.llamadas: list[Llamada] = []
        self.metodos: Counter[str] = Counter()
        self.posts: Counter[int] = Counter()
        self.deletes: Counter[int] = Counter()
        self.nodos_post: dict[int, str] = {}
        self.cuerpos_post: dict[int, dict[str, Any]] = {}
        self.params_delete: dict[int, dict[str, Any] | None] = {}
        self.ocupados: set[int] = set()
        self.vms: dict[int, dict[str, Any]] = {}  # vmid -> {"nodo", "config", "status"}
        self.visibles_extra: list[dict[str, Any]] = []
        self.reglas: list[Regla] = []
        self.exitstatus: dict[int, str] = {}  # por VMID de la tarea; por defecto "OK"
        self.tareas_en_curso: dict[int, int] = {}  # consultas de status que devuelven "running"
        self.permisos: dict[str, dict[str, int]] | None = None
        self.al_post: Callable[[int], None] | None = None
        self.crea_en_post = True  # si el POST llega, la MV queda creada en el clúster
        self.parciales: set[int] = set()  # tarea fallida que deja la config a medias
        # Concurrencia observada de POST (CA-L12.3/L12.4).
        self._activos_post: Counter[str] = Counter()
        self.max_post_por_nodo = 0
        self.max_post_total = 0
        self.max_nodos_con_post = 0
        self.max_peticiones = 0
        self._activas = 0
        self.barrera: threading.Barrier | None = None
        self.barrera_usada: set[str] = set()
        # --- Fase B (0.7) -----------------------------------------------------------------
        # Agente invitado: guion de respuestas por VMID (la última se repite). Cada elemento es
        # un ``ErrorProxLaunch`` (se lanza), un ``Http`` (solo con ``instalar_http``), un
        # ``callable(Llamada)`` o el valor de ``data``. Sin guion: «agent is not running».
        self.agente_guion: dict[int, list[Any]] = {}
        self.sondeos_agente: Counter[int] = Counter()
        self.llamadas_agente: list[tuple[str, int]] = []  # (método, vmid) en orden de llegada
        self.conversiones: Counter[int] = Counter()  # POST …/template por VMID
        # Snippets por (nodo, storage): [(volid, tamaño)]; ``listados_snippets`` cuenta consultas.
        self.snippets: dict[tuple[str, str], list[tuple[str, int]]] = {}
        self.listados_snippets: list[tuple[str, str]] = []
        # ``PUT …/config`` en bruto (VMID, cuerpo del formulario en bytes) y modo eco: con
        # ``eco_put`` el servidor falla (500) repitiendo el cuerpo en el texto del error. ``True``
        # = todo PUT de config; un conjunto = solo si el cuerpo lleva alguna de esas claves.
        self.puts_crudos: list[tuple[int, bytes]] = []
        self.eco_put: bool | set[str] = False
        # VMIDs cuyo clon queda con ``lock: clone`` de forma persistente.
        self.bloqueo_clon: set[int] = set()
        # Traza completa (método, ruta, consulta, cuerpo en bytes); la llena ``instalar_http``.
        self.trazas: list[tuple[str, str, str, bytes]] = []
        # --- Fase D (0.9): arquitectura, CPU y mapeos del clúster ------------------------------
        # Cada valor puede ser el ``data`` de la respuesta o una excepción (se lanza). Sin valor
        # fijado la ruta sigue su camino de siempre (arquitectura) o responde vacía (CPU, mapeos).
        self.recursos_nodo: Any = None  # ``GET /cluster/resources?type=node`` (lista de filas)
        self.estados_nodo: dict[str, Any] = {}  # ``GET /nodes/{n}/status`` por nodo
        self.cpus_api: dict[str, Any] = {}  # ``GET /nodes/{n}/capabilities/qemu/cpu`` por nodo
        self.cpus_por_arch: dict[tuple[str, str], Any] = {}  # ídem con ``?arch=`` (nodo, arch)
        self.mapeos_api: dict[str, Any] = {}  # ``GET /cluster/mapping/{pci|usb}`` por tipo
        self.check_node_api: dict[tuple[str, str], Any] = {}  # ``?check-node=`` por (tipo, nodo)

    # --- Configuración ---------------------------------------------------------------------

    def regla(
        self,
        metodo: str,
        patron: str,
        accion: Callable[[Llamada], Any] | BaseException,
        veces: int | None = None,
    ) -> Regla:
        if isinstance(accion, BaseException):
            accion = lanzar(accion)
        r = Regla(metodo.upper(), patron, accion, veces)
        self.reglas.append(r)
        return r

    def agregar_vm(
        self,
        vmid: int,
        nodo_: str = "pve1",
        nombre: str = "otra",
        *,
        tags: str | None = None,
        status: str = "stopped",
        extra: dict[str, Any] | None = None,
    ) -> None:
        config: dict[str, Any] = {"name": nombre, "digest": "d"}
        if tags is not None:
            config["tags"] = tags
        config.update(extra or {})
        self.vms[vmid] = {"nodo": nodo_, "config": config, "status": status}

    def etiquetas_del_lote(self, id_lote: str) -> str:
        return f"{ETIQUETA_APP};{PREFIJO_ETIQUETA_LOTE}{id_lote}"

    def reiniciar_llamadas(self) -> None:
        """Olvida las peticiones y los contadores de métodos (no el estado del clúster)."""
        with self._cerrojo:
            self.llamadas.clear()
            self.metodos.clear()

    # --- Resumen para las aserciones ---------------------------------------------------------

    def total(self, metodo: str) -> int:
        return self.metodos[metodo.upper()]

    @property
    def solo_lecturas(self) -> bool:
        return set(self.metodos) <= {"GET", "HEAD"}

    def llamadas_a(self, metodo: str, patron: str = "") -> list[Llamada]:
        return [
            c for c in self.llamadas if c.metodo == metodo.upper() and re.search(patron, c.ruta)
        ]

    # --- Atención de peticiones --------------------------------------------------------------

    def atender(
        self,
        metodo: str,
        ruta: str,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
        crudo: bytes | None = None,
    ) -> Any:
        metodo = metodo.upper()
        llamada = Llamada(metodo, ruta, params, datos)
        with self._cerrojo:
            self.llamadas.append(llamada)
            self.metodos[metodo] += 1
            if metodo == "PUT" and (mc := _RE_CONFIG.match(ruta)):
                # Cuerpo en bruto del formulario: el real si lo hay (HTTP) o el que codificaría
                # ``requests`` para el diccionario (transporte en memoria).
                cuerpo = crudo if crudo is not None else urlencode(datos or {}).encode()
                self.puts_crudos.append((int(mc["v"]), cuerpo))
            # Un POST de creación cuenta como intento aunque una regla de fallo lo corte después.
            if metodo == "POST" and (mt := _RE_QEMU.match(ruta)) and datos and "vmid" in datos:
                vmid = int(datos["vmid"])
                self.posts[vmid] += 1
                self.nodos_post[vmid] = mt["n"]
                self.cuerpos_post[vmid] = dict(datos)
            elif metodo == "DELETE" and (mt := _RE_QEMU_VM.match(ruta)):
                vmid = int(mt["v"])
                self.deletes[vmid] += 1
                self.params_delete[vmid] = dict(params) if params is not None else None
            self._activas += 1
            self.max_peticiones = max(self.max_peticiones, self._activas)
        try:
            return self._despachar(llamada)
        finally:
            with self._cerrojo:
                self._activas -= 1

    def _despachar(self, ll: Llamada) -> Any:
        for r in self.reglas:
            with self._cerrojo:
                if not r.aplica(ll.metodo, ll.ruta):
                    continue
                r.disparos += 1
            resultado = r.accion(ll)
            if not isinstance(resultado, _Normal):
                return resultado
        propio = self._fase_b(ll)  # antes que ``_normal``: sirve también a los clústeres derivados
        if not isinstance(propio, _Normal):
            return propio
        propio = self._fase_d(ll)
        if not isinstance(propio, _Normal):
            return propio
        resultado = self._normal(ll)
        self._tras_normal(ll)
        return resultado

    # --- Rutas de la fase B (0.7) --------------------------------------------------------------

    def guion_agente(self, vmid: int, *respuestas: Any) -> None:
        """Fija el guion del agente de una MV (véase ``agente_guion``)."""
        self.agente_guion[vmid] = list(respuestas)

    def _fase_b(self, ll: Llamada) -> Any:
        m, ruta = ll.metodo, ll.ruta
        if m in ("GET", "POST") and (mt := _RE_AGENTE.match(ruta)):
            return self._agente(ll, int(mt["v"]))
        if m == "POST" and (mt := _RE_PLANTILLA.match(ruta)):
            vmid = int(mt["v"])
            with self._cerrojo:
                vm = self.vms.get(vmid)
                if vm is None:
                    raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "no such VM")
                self.conversiones[vmid] += 1
                vm["config"]["template"] = 1
            return upid_de(mt["n"], vmid, "qmtemplate")
        if (
            m == "GET"
            and (mt := _RE_CONTENIDO.match(ruta))
            and (ll.params or {}).get("content") == "snippets"
        ):
            with self._cerrojo:
                self.listados_snippets.append((mt["n"], mt["s"]))
                lista = list(self.snippets.get((mt["n"], mt["s"]), []))
            return [{"volid": v, "size": t, "ctime": 1} for v, t in lista]
        if m == "PUT" and (mt := _RE_CONFIG.match(ruta)) and self.eco_put:
            cuerpo = next(
                (b.decode() for v, b in reversed(self.puts_crudos) if v == int(mt["v"])), ""
            )
            claves = {k for k, _ in (ll.datos or {}).items()}
            if self.eco_put is True or claves & set(self.eco_put):
                # El servidor repite el cuerpo (codificado y decodificado) en el texto del error.
                raise ErrorProxLaunch(
                    CodigoError.DESCONOCIDO,
                    {},
                    f"HTTP 500: Parameter verification failed. cuerpo: {cuerpo} | "
                    f"{unquote_plus(cuerpo)}",
                )
        return NORMAL

    # --- Rutas de la fase D (0.9) ----------------------------------------------------------------

    @staticmethod
    def _valor_d(valor: Any) -> Any:
        if isinstance(valor, BaseException):
            raise valor
        return valor

    def _fase_d(self, ll: Llamada) -> Any:
        """Arquitectura, capacidades de CPU y mapeos del clúster (solo lecturas, ``GET``)."""
        if ll.metodo != "GET":
            return NORMAL
        ruta, params = ll.ruta, ll.params or {}
        if ruta == "/cluster/resources" and params.get("type") == "node":
            return NORMAL if self.recursos_nodo is None else self._valor_d(self.recursos_nodo)
        if (mt := _RE_ESTADO_NODO.match(ruta)) and mt["n"] in self.estados_nodo:
            return self._valor_d(self.estados_nodo[mt["n"]])
        if mt := re.match(r"^/nodes/(?P<n>[^/]+)/capabilities/qemu/cpu$", ruta):
            arch = params.get("arch")
            if arch is not None and (mt["n"], arch) in self.cpus_por_arch:
                return self._valor_d(self.cpus_por_arch[(mt["n"], arch)])
            return self._valor_d(self.cpus_api.get(mt["n"], []))
        if mt := re.match(r"^/cluster/mapping/(?P<t>pci|usb)$", ruta):
            tipo = mt["t"]
            if "check-node" in params:
                return self._valor_d(self.check_node_api.get((tipo, params["check-node"]), []))
            return self._valor_d(self.mapeos_api.get(tipo, []))
        return NORMAL

    def lecturas_d(self, patron: str) -> list[Llamada]:
        """``GET`` recibidos cuya ruta casa ``patron`` (cuenta lecturas de la fase D)."""
        return self.llamadas_a("GET", patron)

    def _agente(self, ll: Llamada, vmid: int) -> Any:
        with self._cerrojo:
            self.sondeos_agente[vmid] += 1
            self.llamadas_agente.append((ll.metodo, vmid))
            guion = self.agente_guion.get(vmid)
            indice = self.sondeos_agente[vmid] - 1
        if not guion:
            raise error_http(500, "QEMU guest agent is not running")
        item = guion[min(indice, len(guion) - 1)]
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item = item(ll)
        return item

    def _tras_normal(self, ll: Llamada) -> None:
        """Efectos de la fase B sobre el estado del clúster tras atender una petición normal."""
        if ll.metodo == "PUT" and (mt := _RE_CONFIG.match(ll.ruta)):
            with self._cerrojo:
                vm = self.vms.get(int(mt["v"]))
                if vm is not None and "cipassword" in vm["config"]:
                    # Proxmox nunca devuelve la contraseña: la lee como «**********» (CA-B1.6.8).
                    vm["config"]["cipassword"] = "**********"
        elif ll.metodo == "POST" and _RE_CLONAR.match(ll.ruta):
            nuevo = int((ll.datos or {}).get("newid", 0))
            if nuevo in self.bloqueo_clon:
                with self._cerrojo:
                    if nuevo in self.vms:
                        self.vms[nuevo]["config"]["lock"] = "clone"

    def _normal(self, ll: Llamada) -> Any:
        m, ruta = ll.metodo, ll.ruta
        if m == "GET":
            return self._get(ll, ruta)
        if m == "POST" and (mt := _RE_QEMU.match(ruta)):
            return self._post(ll, mt["n"])
        if m == "POST" and (mt := _RE_STOP.match(ruta)):
            return self._stop(mt["n"], int(mt["v"]))
        if m == "PUT" and (mt := _RE_CONFIG.match(ruta)):
            return self._put_config(ll, int(mt["v"]))
        if m == "DELETE" and (mt := _RE_QEMU_VM.match(ruta)):
            return self._delete(ll, mt["n"], int(mt["v"]))
        raise AssertionError(f"ruta no simulada: {m} {ruta}")

    def _get(self, ll: Llamada, ruta: str) -> Any:
        if ruta == "/cluster/nextid":
            if ll.params and "vmid" in ll.params:
                vmid = int(ll.params["vmid"])
                with self._cerrojo:
                    ocupado = vmid in self.ocupados or vmid in self.vms
                if ocupado:
                    raise ErrorProxLaunch(
                        CodigoError.VMID_OCUPADO, {"vmid": str(vmid)}, f"VM {vmid} already exists"
                    )
                return str(vmid)
            return "100"
        if ruta == "/cluster/resources":
            filas = [
                {"vmid": v, "name": d["config"].get("name", ""), "node": d["nodo"], "type": "qemu"}
                for v, d in self.vms.items()
            ]
            return filas + self.visibles_extra
        if ruta == "/access/permissions":
            if self.permisos is not None:
                return self.permisos
            privs = {
                p: 1
                for p in [
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
                ]
            }
            return {"/": privs}
        if mt := _RE_CONFIG.match(ruta):
            vm = self.vms.get(int(mt["v"]))
            if vm is None or vm["nodo"] != mt["n"]:
                raise ErrorProxLaunch(
                    CodigoError.RECURSO_INEXISTENTE, {"nodo": mt["n"]}, "does not exist"
                )
            return dict(vm["config"])
        if mt := _RE_ACTUAL.match(ruta):
            vm = self.vms.get(int(mt["v"]))
            if vm is None:
                raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "does not exist")
            estado = {"status": vm["status"], "vmid": int(mt["v"])}
            if "lock" in vm["config"]:
                estado["lock"] = vm["config"]["lock"]
            return estado
        if mt := _RE_ESTADO_NODO.match(ruta):
            # Sonda de nodo (``estado_nodo``): responde salvo que una regla simule 595/596.
            return {"uptime": 12345, "pveversion": "pve-manager/9.2.1"}
        if mt := _RE_TAREA.match(ruta):
            return self._tarea(mt["u"], mt["q"])
        raise AssertionError(f"ruta no simulada: GET {ruta}")

    def _tarea(self, upid: str, que: str) -> Any:
        mt = _RE_UPID_VMID.match(upid)
        vmid = int(mt.group(2)) if mt else -1
        if que == "log":
            return [{"n": 1, "t": f"TASK log {vmid}"}]
        with self._cerrojo:
            faltan = self.tareas_en_curso.get(vmid, 0)
            if faltan > 0:
                self.tareas_en_curso[vmid] = faltan - 1
                return {"status": "running"}
        return {"status": "stopped", "exitstatus": self.exitstatus.get(vmid, "OK")}

    def _post(self, ll: Llamada, nodo_: str) -> Any:
        datos = ll.datos or {}
        vmid = int(datos["vmid"])
        with self._cerrojo:
            self._activos_post[nodo_] += 1
            self.max_post_por_nodo = max(self.max_post_por_nodo, self._activos_post[nodo_])
            total = sum(self._activos_post.values())
            self.max_post_total = max(self.max_post_total, total)
            self.max_nodos_con_post = max(
                self.max_nodos_con_post, sum(1 for v in self._activos_post.values() if v)
            )
            barrera = self.barrera if nodo_ not in self.barrera_usada else None
            if barrera is not None:
                self.barrera_usada.add(nodo_)
        try:
            if self.al_post is not None:
                self.al_post(vmid)
            if barrera is not None:
                with contextlib.suppress(threading.BrokenBarrierError):
                    barrera.wait(timeout=5)
            tarea_ok = self.exitstatus.get(vmid, "OK") == "OK" or vmid in self.parciales
            if self.crea_en_post and tarea_ok:
                config: dict[str, Any] = {"name": datos.get("name", ""), "digest": "d"}
                if "tags" in datos:
                    config["tags"] = datos["tags"]
                with self._cerrojo:
                    self.vms[vmid] = {"nodo": nodo_, "config": config, "status": "stopped"}
            return upid_de(nodo_, vmid)
        finally:
            with self._cerrojo:
                self._activos_post[nodo_] -= 1

    def _stop(self, nodo_: str, vmid: int) -> Any:
        with self._cerrojo:
            vm = self.vms.get(vmid)
            if vm is None:
                raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "no such VM")
            if self.exitstatus.get(vmid, "OK") == "OK":
                vm["status"] = "stopped"
        return upid_de(nodo_, vmid, "qmstop")

    def _put_config(self, ll: Llamada, vmid: int) -> Any:
        with self._cerrojo:
            vm = self.vms.get(vmid)
            if vm is None:
                raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "no such VM")
            for clave, valor in (ll.datos or {}).items():
                vm["config"][clave] = valor
        return None

    def _delete(self, ll: Llamada, nodo_: str, vmid: int) -> Any:
        with self._cerrojo:
            existe = vmid in self.vms
        if not existe:
            raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {"nodo": nodo_}, "no such VM")
        with self._cerrojo:
            if self.exitstatus.get(vmid, "OK") == "OK":
                self.vms.pop(vmid, None)
        return upid_de(nodo_, vmid, "qmdestroy")


class TransporteCluster:
    """``Transporte`` en memoria sobre un ``Cluster`` (aplica el autenticador como el real)."""

    def __init__(self, cluster: Cluster | None = None) -> None:
        self.cluster = cluster or Cluster()
        self._auth: Autenticador | None = None

    @property
    def host_activo(self) -> str:
        return HOST

    def usar_autenticador(self, auth: Autenticador | None) -> None:
        self._auth = auth

    def peticion(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
    ) -> Any:
        if self._auth is not None:
            self._auth.aplicar(metodo.upper(), {}, {})
        return self.cluster.atender(metodo, ruta, params, datos)


# --- El mismo clúster, servido a través del TransporteHttp real (con ``responses``) ---------------


def instalar_http(rsps: Any, cluster: Cluster, host: str = HOST) -> None:
    """Sirve ``cluster`` con ``responses``: el transporte y el traductor reales quedan en juego.

    Una excepción de ``requests`` lanzada por una regla sale tal cual (ReadTimeout, SSLError,
    ConnectionError); un ``Http`` se convierte en la respuesta de error correspondiente; un
    ``ErrorProxLaunch`` se responde como un 500 con su detalle.
    """
    import responses

    def _callback(request: Any) -> tuple[int, dict[str, str], str]:
        partes = urlsplit(request.url)
        ruta = partes.path.removeprefix("/api2/json")
        params = {k: v[0] for k, v in parse_qs(partes.query).items()} or None
        cuerpo = request.body
        crudo = cuerpo if isinstance(cuerpo, bytes) else (cuerpo or "").encode()
        if isinstance(cuerpo, bytes):
            cuerpo = cuerpo.decode()
        datos = {k: v[0] for k, v in parse_qs(cuerpo or "").items()} or None
        with cluster._cerrojo:
            cluster.trazas.append((request.method, ruta, partes.query, crudo))
        try:
            valor = cluster.atender(request.method, ruta, params, datos, crudo)
        except ErrorProxLaunch as e:
            texto = e.detalle_tecnico or str(e.codigo)
            return 500, {}, json.dumps({"data": None, "message": texto})
        if isinstance(valor, Http):
            return _respuesta_http(valor)
        return 200, {}, json.dumps({"data": valor})

    rsps.add_callback(responses.GET, re.compile(r"https://.*/api2/json/.*"), callback=_callback)
    rsps.add_callback(responses.POST, re.compile(r"https://.*/api2/json/.*"), callback=_callback)
    rsps.add_callback(responses.DELETE, re.compile(r"https://.*/api2/json/.*"), callback=_callback)
    rsps.add_callback(responses.PUT, re.compile(r"https://.*/api2/json/.*"), callback=_callback)


def _respuesta_http(h: Http) -> tuple[int, dict[str, str], str]:
    cuerpo = h.cuerpo
    if cuerpo is None:
        cuerpo = {"data": None, "message": h.motivo}
    return h.estado, {}, cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo)


# --- Banco: sesión + motor + observador -----------------------------------------------------------


class ControlConEspera(ControlLote):
    """``ControlLote`` que avisa (``esperando``) cuando un trabajador se bloquea por una pausa.

    Permite probar la pausa de forma determinista con un hilo del motor y el hilo de la prueba.
    """

    def __init__(self) -> None:
        super().__init__()
        self.esperando = threading.Event()

    def esperar_si_pausado(self, timeout: float | None = None) -> bool:
        self.esperando.set()
        return super().esperar_si_pausado(timeout)


class ControlAutomatico(ControlLote):
    """``ControlLote`` que responde solo cuando el lote se pausa (sin hilos ni esperas).

    ``accion`` se invoca al producirse la pausa: ``"suspender"`` (el motor sale y deja las
    pendientes), ``"cancelar"`` o ``"continuar"`` (reanuda ignorando la causa).
    """

    def __init__(self, accion: str = "suspender") -> None:
        super().__init__()
        self.accion = accion
        self.pausas: list[tuple[Any, ErrorProxLaunch | None]] = []

    def pausar(self, motivo: Any, error: ErrorProxLaunch | None = None) -> bool:
        causo = super().pausar(motivo, error)
        if causo:
            self.pausas.append((motivo, error))
            if self.accion == "suspender":
                self.suspender()
            elif self.accion == "cancelar":
                self.cancelar()
            elif self.accion == "continuar":
                self.reanudar(ignorar_causa=True)
        return causo


@dataclass
class Banco:
    """Escenario completo: clúster + sesión real + reloj + inventario + observador."""

    cluster: Cluster
    sesion: Sesion
    reloj: RelojSeguro
    inv: Inventario
    eventos: list[EntradaLibro] = field(default_factory=list)
    ultimo: dict[int, EntradaLibro] = field(default_factory=dict)
    _cerrojo: threading.Lock = field(default_factory=threading.Lock)

    def observador(self, entrada: EntradaLibro) -> None:
        with self._cerrojo:
            self.eventos.append(entrada)
            self.ultimo[entrada.elemento.vmid] = entrada

    def planificar(self, definicion_: DefinicionLote, **kw: Any) -> Plan:
        return Planificador(self.sesion, self.reloj, generador_id=lambda: "abcd1234").planificar(
            definicion_, self.inv, **kw
        )

    def motor(self, **kw: Any) -> MotorLote:
        return MotorLote(self.sesion, self.reloj, **kw)

    def ejecutar(
        self,
        plan: Plan,
        control: ControlLote | None = None,
        motor: MotorLote | None = None,
    ) -> Libro:
        """Ejecuta el plan. Sin ``control`` explícito el lote que se pausa se suspende (nunca
        se queda esperando una decisión humana y cuelga la prueba)."""
        return (motor or self.motor()).ejecutar(
            plan, self.inv, self.observador, control or ControlAutomatico("suspender")
        )

    def estados(self, libro: Libro) -> list[str]:
        return [e.estado.value for e in libro.instantanea()]


def crear_banco(
    nodos: tuple[str, ...] = ("pve1",),
    inv: Inventario | None = None,
    cluster: Cluster | None = None,
) -> Banco:
    cl = cluster or Cluster(nodos)
    reloj = RelojSeguro()
    transporte = TransporteCluster(cl)
    sesion = crear_sesion(transporte, reloj=reloj)  # type: ignore[arg-type]
    return Banco(cl, sesion, reloj, inv or inventario(tuple(nodo(n) for n in nodos)))


def crear_banco_http(
    rsps: Any, nodos: tuple[str, ...] = ("pve1",), cluster: Cluster | None = None
) -> Banco:
    """Como ``crear_banco`` pero con el ``TransporteHttp`` real y el clúster en ``responses``.

    ``cluster`` permite pasar un clúster derivado (``ClusterM4``, ``ClusterA``…)."""
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
    from proxlaunch.nucleo.api.cliente import ClienteProxmox
    from proxlaunch.nucleo.api.transporte import TransporteHttp
    from proxlaunch.nucleo.modelos.conexion import CredencialToken

    from .apoyo_api import HUELLA_A, TOKEN_ID, TOKEN_SECRETO, TransporteFalso

    cl = cluster or Cluster(nodos)
    instalar_http(rsps, cl)
    reloj = RelojSeguro()
    sesion = crear_sesion(TransporteFalso(), reloj=reloj)
    auth = AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO))
    sesion.cliente = ClienteProxmox(
        TransporteHttp([HOST], 8006, huellas={HOST: HUELLA_A}), auth, reloj
    )
    return Banco(cl, sesion, reloj, inventario(tuple(nodo(n) for n in nodos)))


# --- Volcado profundo (para buscar secretos, host, usuario en cualquier estructura) ---------------


def volcar(obj: Any, _nivel: int = 0) -> str:
    """Texto con TODO el contenido de ``obj`` (dataclasses, enums, errores, dicts, listas)."""
    if _nivel > 12:
        return "…"
    if obj is None or isinstance(obj, bool | int | float):
        return repr(obj)
    if isinstance(obj, str):
        return obj
    if isinstance(obj, Enum):
        return f"{obj.name}={obj.value}"
    if isinstance(obj, ErrorProxLaunch):
        return f"Error({volcar(obj.codigo)}|{volcar(obj.params, _nivel + 1)}|{obj.detalle_tecnico})"
    if is_dataclass(obj) and not isinstance(obj, type):
        return " ".join(f"{f.name}={volcar(getattr(obj, f.name), _nivel + 1)}" for f in fields(obj))
    if isinstance(obj, dict):
        return " ".join(f"{volcar(k, _nivel + 1)}:{volcar(v, _nivel + 1)}" for k, v in obj.items())
    if isinstance(obj, list | tuple | set | frozenset):
        return " ".join(volcar(x, _nivel + 1) for x in obj)
    return repr(obj)
