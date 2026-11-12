"""Apoyo para las pruebas de la capa API y de los servicios (F3).

Contiene: carga de respuestas simuladas, un ``Transporte`` falso (límite del sistema:
la red), un ``RespuestaConMotivo`` para reproducir la frase de estado HTTP de Proxmox y
constructores de sesiones. No contiene aserciones de las pruebas.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import responses

from proxlaunch.nucleo.api.autenticacion import Autenticador, AutenticadorToken
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos.conexion import CredencialToken, PerfilConexion
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.servicios.conexion import Sesion

DIR_RESPUESTAS = Path(__file__).resolve().parents[1] / "datos" / "respuestas"

# Huella SHA-256 sintética (32 bytes) y otra distinta.
HUELLA_A = ":".join(["AB"] * 32)
HUELLA_B = ":".join(["CD"] * 32)

UPID = "UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:100:root@pam:"
TOKEN_ID = "ana@pve!lab"
TOKEN_SECRETO = "11111111-2222-3333-4444-555555555555"


def cargar(version: str, nombre: str) -> Any:
    """Cuerpo JSON completo de una respuesta simulada (``tests/datos/respuestas``)."""
    return json.loads((DIR_RESPUESTAS / version / nombre).read_text(encoding="utf-8"))


def dato(version: str, nombre: str) -> Any:
    """Solo el campo ``data`` de una respuesta simulada."""
    return cargar(version, nombre)["data"]


def ticket_parcial(desafio: dict[str, Any]) -> str:
    """Ticket parcial ``PVE:!tfa!<desafío escapado>:<HEX8>::<firma>`` (f1 §3)."""
    cuerpo = quote(json.dumps(desafio, separators=(",", ":")), safe="")
    return f"PVE:!tfa!{cuerpo}:6535AB12::c2ludGV0aWNv"


def url(host: str, ruta: str, puerto: int = 8006) -> str:
    """URL absoluta de la API para ``responses``."""
    return f"https://{host}:{puerto}/api2/json{ruta}"


class RespuestaConMotivo(responses.Response):
    """Respuesta simulada con frase de estado propia.

    Proxmox pone el mensaje corto del error en la frase de estado HTTP
    (``HTTP/1.1 500 VM 100 already exists ...``); ``responses`` no lo permite de serie.
    """

    def __init__(self, *args: Any, motivo: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._motivo_pve = motivo

    def get_response(self, request: Any) -> Any:
        resp = super().get_response(request)
        resp.reason = self._motivo_pve
        return resp


def agregar_error(
    rsps: responses.RequestsMock,
    metodo: str,
    direccion: str,
    estado: int,
    motivo: str = "",
    cuerpo: Any = None,
) -> None:
    """Registra una respuesta de error de Proxmox (frase de estado + cuerpo JSON)."""
    rsps.add(
        RespuestaConMotivo(
            metodo,
            direccion,
            status=estado,
            body=json.dumps(cuerpo if cuerpo is not None else {"data": None}),
            content_type="application/json",
            motivo=motivo or "error",
        )
    )


# --- Transporte falso -----------------------------------------------------------------


@dataclass
class Llamada:
    """Petición recibida por el transporte falso."""

    metodo: str
    ruta: str
    params: dict[str, Any] | None
    datos: dict[str, Any] | None
    cabeceras: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)


class Secuencia:
    """Respuestas sucesivas de una ruta; la última se repite. Admite excepciones."""

    def __init__(self, *items: Any) -> None:
        self._items = list(items)
        self._i = 0
        self._lock = threading.Lock()

    def siguiente(self) -> Any:
        with self._lock:
            item = self._items[min(self._i, len(self._items) - 1)]
            self._i += 1
        return item


class TransporteFalso:
    """``Transporte`` en memoria: enruta por (método, ruta) y registra las peticiones.

    El valor registrado para una ruta puede ser: una excepción (se lanza), una función
    ``f(Llamada) -> valor``, una ``Secuencia`` o cualquier otro valor (se devuelve como
    ``data``). Aplica el autenticador como lo haría el transporte real. Una petición
    DELETE falla de inmediato: ningún flujo del MVP 1 debe borrar nada.
    """

    def __init__(self, hosts: tuple[str, ...] = ("10.0.0.1",)) -> None:
        self._hosts = hosts
        self._rutas: dict[tuple[str, str], Any] = {}
        self._auth: Autenticador | None = None
        self._lock = threading.Lock()
        self.llamadas: list[Llamada] = []

    @property
    def host_activo(self) -> str:
        return self._hosts[0]

    def usar_autenticador(self, auth: Autenticador | None) -> None:
        self._auth = auth

    def en(self, metodo: str, ruta: str, respuesta: Any) -> TransporteFalso:
        self._rutas[(metodo.upper(), ruta)] = respuesta
        return self

    def peticion(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
    ) -> Any:
        metodo = metodo.upper()
        if metodo == "DELETE":
            raise AssertionError(f"petición DELETE prohibida: {ruta}")
        cab: dict[str, str] = {}
        cook: dict[str, str] = {}
        if self._auth is not None:
            self._auth.aplicar(metodo, cab, cook)
        llamada = Llamada(metodo, ruta, params, datos, cab, cook)
        with self._lock:
            self.llamadas.append(llamada)
        if (metodo, ruta) not in self._rutas:
            raise AssertionError(f"ruta no simulada: {metodo} {ruta}")
        r = self._rutas[(metodo, ruta)]
        if isinstance(r, Secuencia):
            r = r.siguiente()
        if callable(r) and not isinstance(r, BaseException):
            r = r(llamada)
        if isinstance(r, BaseException):
            raise r
        return r

    def llamadas_a(self, metodo: str, ruta: str) -> list[Llamada]:
        return [c for c in self.llamadas if c.metodo == metodo.upper() and c.ruta == ruta]

    @property
    def metodos(self) -> list[str]:
        return [c.metodo for c in self.llamadas]


# --- Sesiones ---------------------------------------------------------------------------


def perfil_basico(**cambios: Any) -> PerfilConexion:
    base: dict[str, Any] = {
        "id": "perfil-1",
        "nombre": "lab",
        "hosts": ["10.0.0.1"],
        "usuario": TOKEN_ID,
    }
    base.update(cambios)
    return PerfilConexion(**base)


def crear_sesion(
    transporte: TransporteFalso,
    *,
    auth: Autenticador | None = None,
    reloj: RelojSimulado | None = None,
    version: Version | None = None,
) -> Sesion:
    """``Sesion`` real (``ClienteProxmox`` incluido) sobre un transporte falso."""
    reloj = reloj if reloj is not None else RelojSimulado()
    auth = auth if auth is not None else AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO))
    version = version or Version("9.2.1", 9, 2, 1)
    cliente = ClienteProxmox(transporte, auth, reloj)
    return Sesion(
        perfil=perfil_basico(),
        cliente=cliente,
        version=version,
        capacidades=capacidades_para(version, None),
        host_activo=transporte.host_activo,
        usuario_efectivo=TOKEN_ID,
    )


def rutas_inventario(t: TransporteFalso, ver: str = "9.2", nodos: str = "nodes.json") -> None:
    """Rutas de lectura típicas de un clúster de 3 nodos para el descubrimiento."""
    t.en("GET", "/cluster/status", dato(ver, "cluster_status.json"))
    t.en("GET", "/nodes", dato(ver, nodos))
    t.en("GET", "/cluster/nextid", dato(ver, "nextid.json"))
    for n in ("pve1", "pve2", "pve3"):
        t.en("GET", f"/nodes/{n}/storage", dato(ver, "storage.json"))
        t.en("GET", f"/nodes/{n}/network", dato(ver, "network.json"))


RutaFn = Callable[[Llamada], Any]


# --- Escenarios de creación -------------------------------------------------------------

RUTA_CREAR = "/nodes/pve1/qemu"
RUTA_ESTADO = f"/nodes/pve1/tasks/{UPID}/status"
RUTA_LOG = f"/nodes/pve1/tasks/{UPID}/log"
RUTA_CONFIG = "/nodes/pve1/qemu/100/config"


def estado_tarea(nombre: str, ver: str = "9.2") -> Any:
    """``data`` de ``tarea_status_<nombre>.json``."""
    return dato(ver, f"tarea_status_{nombre}.json")


def _nextid(llamada: Llamada) -> str:
    """Simula ``/cluster/nextid``: con ``vmid`` libre lo devuelve; sin él, el siguiente (101)."""
    if llamada.params and "vmid" in llamada.params:
        return str(llamada.params["vmid"])
    return "101"


def rutas_creacion(
    t: TransporteFalso,
    *,
    estado: Any,
    config: Any = None,
    log: Any = None,
    crear: Any = UPID,
) -> TransporteFalso:
    """Rutas de una creación en pve1 (VMID 100). ``estado`` puede ser una ``Secuencia``.

    ``config=None`` simula una máquina inexistente (500 "does not exist" -> ``None``).
    """
    from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

    if config is None:
        config = ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {"nodo": "pve1"}, "no existe")
    t.en("GET", "/cluster/nextid", _nextid)
    t.en("POST", RUTA_CREAR, crear)
    t.en("GET", RUTA_ESTADO, estado)
    t.en("GET", RUTA_CONFIG, config)
    t.en("GET", RUTA_LOG, log if log is not None else dato("9.2", "tarea_log.json"))
    return t
