"""ClienteProxmox: operaciones de alto nivel sobre la API.

Es el ÚNICO lugar que construye rutas de la API (arquitectura §5.3).
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any
from urllib.parse import quote

from proxlaunch.nucleo.api.autenticacion import Autenticador
from proxlaunch.nucleo.api.solo_lectura import TransporteSoloLectura
from proxlaunch.nucleo.api.transporte import Transporte
from proxlaunch.nucleo.capacidades import interpretar_version
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import (
    Bridge,
    Nodo,
    Storage,
    Topologia,
    Version,
    VMRemota,
)
from proxlaunch.nucleo.modelos.tarea import EstadoTarea
from proxlaunch.nucleo.reloj import Reloj

_log = logging.getLogger("proxlaunch.api.cliente")

_MIB = 1024**2
# UPID: "UPID:<nodo>:<pid>:<pstart>:<starttime>:<tipo>:<id>:<usuario>:" (forma laxa).
_RE_UPID = re.compile(r"^UPID:[A-Za-z0-9._-]+:\S+$")
# Líneas de log pedidas (por defecto la API devuelve solo 50). Por verificar en laboratorio.
LINEAS_LOG_TAREA = 500


def _seg(valor: object) -> str:
    """Codifica un segmento de ruta (evita que un valor altere la ruta)."""
    return quote(str(valor), safe="")


def _entero(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _como_bool(valor: Any, defecto: bool = False) -> bool:
    """Interpreta los 0/1 (o bool/cadena) que devuelve la API."""
    if valor is None:
        return defecto
    return str(valor).strip().lower() in ("1", "true", "yes", "on")


class ClienteProxmox:
    """Operaciones de la API de Proxmox VE usadas por ProxLaunch.

    Al construirse fija el autenticador en el transporte. Antes de cada petición
    renueva la credencial si hace falta (CA-03.1), con un cerrojo para que los
    hilos del descubrimiento no renueven a la vez.
    """

    def __init__(
        self,
        transporte: Transporte,
        auth: Autenticador,
        reloj: Reloj,
        *,
        transporte_renovacion: Transporte | None = None,
        cerrada: threading.Event | None = None,
    ) -> None:
        self._transporte = transporte
        # Marca de sesión cerrada, compartida con los clientes de solo lectura derivados:
        # tras cerrar, ninguna petición tardía de otro hilo pide un ticket nuevo.
        self._cerrada = cerrada or threading.Event()
        # Transporte con el que se renueva la credencial (POST /access/ticket). Solo difiere
        # del principal en el cliente de solo lectura, cuyo transporte rechaza todo POST.
        self._transporte_renovacion = transporte_renovacion or transporte
        self._auth = auth
        self._reloj = reloj
        self._cerrojo_renovacion = threading.Lock()
        transporte.usar_autenticador(auth)

    def cerrar(self) -> None:
        """Cierra la conexión: suelta el autenticador (ticket o token) y cierra el transporte."""
        self._cerrada.set()
        olvidar = getattr(self._auth, "olvidar", None)
        if callable(olvidar):
            olvidar()
        self._transporte.usar_autenticador(None)
        cerrar = getattr(self._transporte, "cerrar", None)
        if callable(cerrar):
            cerrar()

    def solo_lectura(self) -> ClienteProxmox:
        """Cliente que comparte la sesión pero NO puede escribir (simulación, INV-L5).

        Renueva el ticket con el transporte subyacente (único POST permitido: el de
        ``/access/ticket``, que hace el autenticador). Su ``cerrar()`` no hace nada: no
        suelta la credencial compartida con el cliente original.
        """
        return _ClienteSoloLectura(
            TransporteSoloLectura(self._transporte),
            self._auth,
            self._reloj,
            transporte_renovacion=self._transporte,
            cerrada=self._cerrada,
        )

    # --- Base -------------------------------------------------------------------------

    def _llamar(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
    ) -> Any:
        if self._cerrada.is_set():
            # Sesión cerrada: no se renueva con una credencial ya olvidada (hallazgo B1).
            raise ErrorProxLaunch(CodigoError.SESION_EXPIRADA)
        if self._auth.necesita_renovar():
            with self._cerrojo_renovacion:
                if self._auth.necesita_renovar():
                    self._auth.renovar(self._transporte_renovacion)
        return self._transporte.peticion(metodo, ruta, params=params, datos=datos)

    # --- Lecturas ---------------------------------------------------------------------

    def version(self) -> Version:
        """``GET /version``. Con formato inesperado usa la versión mínima y lo registra."""
        data = self._llamar("GET", "/version")
        texto = data.get("version") if isinstance(data, dict) else None
        version, inesperado = interpretar_version(str(texto) if texto is not None else "")
        if inesperado:
            _log.warning("Formato de versión inesperado: %r", texto)
        return version

    def estado_cluster(self) -> Topologia:
        """``GET /cluster/status``. Los nodos salen sin memoria ni CPU (ver ``nodos``)."""
        data = self._llamar("GET", "/cluster/status")
        entradas = [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
        cluster = next((e for e in entradas if e.get("type") == "cluster"), None)
        nodos = tuple(
            Nodo(
                nombre=str(e.get("name", "")),
                en_linea=_como_bool(e.get("online")),
                mem_libre_mib=None,
                cpus=None,
            )
            for e in entradas
            if e.get("type") == "node"
        )
        return Topologia(
            es_cluster=cluster is not None,
            nombre_cluster=str(cluster["name"]) if cluster and cluster.get("name") else None,
            nodos=nodos,
        )

    def nodos(self) -> list[Nodo]:
        """``GET /nodes``. Memoria y CPU solo aparecen con ``Sys.Audit`` (si no, ``None``)."""
        data = self._llamar("GET", "/nodes")
        resultado: list[Nodo] = []
        for e in data if isinstance(data, list) else []:
            if not isinstance(e, dict) or not e.get("node"):
                continue
            maxmem, mem = _entero(e.get("maxmem")), _entero(e.get("mem"))
            libre = (maxmem - mem) // _MIB if maxmem is not None and mem is not None else None
            resultado.append(
                Nodo(
                    nombre=str(e["node"]),
                    en_linea=str(e.get("status", "")).lower() == "online",
                    mem_libre_mib=libre,
                    cpus=_entero(e.get("maxcpu")),
                )
            )
        return resultado

    def storages(self, nodo: str) -> list[Storage]:
        """``GET /nodes/{n}/storage``: todos; el filtro ``images`` va en descubrimiento."""
        data = self._llamar("GET", f"/nodes/{_seg(nodo)}/storage")
        resultado: list[Storage] = []
        for e in data if isinstance(data, list) else []:
            if not isinstance(e, dict) or not e.get("storage"):
                continue
            contenido = frozenset(c.strip() for c in str(e.get("content", "")).split(",") if c)
            resultado.append(
                Storage(
                    id=str(e["storage"]),
                    tipo=str(e.get("type", "")),
                    contenido=contenido,
                    compartido=_como_bool(e.get("shared")),
                    # Inactivo si active=0 o enabled=0 (CA-11.3).
                    activo=_como_bool(e.get("active"), True) and _como_bool(e.get("enabled"), True),
                    total_bytes=_entero(e.get("total")) or 0,
                    libre_bytes=_entero(e.get("avail")) or 0,
                )
            )
        return resultado

    def bridges(self, nodo: str) -> list[Bridge]:
        """``GET /nodes/{n}/network``: todas las interfaces con su tipo.

        El filtro a ``bridge``/``OVSBridge`` se hace en descubrimiento.
        """
        data = self._llamar("GET", f"/nodes/{_seg(nodo)}/network")
        resultado: list[Bridge] = []
        for e in data if isinstance(data, list) else []:
            if not isinstance(e, dict) or not e.get("iface"):
                continue
            resultado.append(
                Bridge(
                    nombre=str(e["iface"]),
                    tipo=str(e.get("type", "")),
                    vlan_aware=_como_bool(e.get("bridge_vlan_aware")),
                )
            )
        return resultado

    def proximo_vmid(self, sugerido: int | None = None) -> int:
        """``GET /cluster/nextid[?vmid=]``.

        Con ``sugerido`` ocupado Proxmox responde 400 y se lanza ``VMID_OCUPADO`` (A-8).
        """
        params = {"vmid": sugerido} if sugerido is not None else None
        data = self._llamar("GET", "/cluster/nextid", params=params)
        valor = _entero(data)
        if valor is None:
            raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, f"nextid inesperado: {data!r}")
        return valor

    def vmid_libre(self, vmid: int) -> bool:
        """``GET /cluster/nextid?vmid=``: ``True`` si el VMID está libre en todo el clúster.

        Un 400 por ``vmid`` (ya existe) es ``False``; cualquier otro error se propaga.
        """
        try:
            self._llamar("GET", "/cluster/nextid", params={"vmid": vmid})
        except ErrorProxLaunch as e:
            if e.codigo == CodigoError.VMID_OCUPADO or (
                e.codigo == CodigoError.PARAMETRO_INVALIDO and e.params.get("campo") == "vmid"
            ):
                return False
            raise
        return True

    def vms_visibles(self) -> list[VMRemota]:
        """``GET /cluster/resources?type=vm``: solo lo que el usuario puede ver (LAB-L11)."""
        data = self._llamar("GET", "/cluster/resources", params={"type": "vm"})
        resultado: list[VMRemota] = []
        for e in data if isinstance(data, list) else []:
            vmid = _entero(e.get("vmid")) if isinstance(e, dict) else None
            if vmid is None:
                continue
            resultado.append(
                VMRemota(
                    vmid=vmid,
                    nombre=str(e.get("name", "")),
                    nodo=str(e.get("node", "")),
                    tipo=str(e.get("type", "")),
                )
            )
        return resultado

    def permisos(self) -> dict[str, dict[str, int]]:
        """``GET /access/permissions``: ``{ruta: {privilegio: 1}}`` del usuario."""
        data = self._llamar("GET", "/access/permissions")
        if not isinstance(data, dict):
            return {}
        return {
            str(ruta): {str(p): int(v) for p, v in privs.items() if _entero(v) is not None}
            for ruta, privs in data.items()
            if isinstance(privs, dict)
        }

    # --- Creación y seguimiento -------------------------------------------------------

    def crear_vm(self, nodo: str, parametros: dict[str, str]) -> str:
        """``POST /nodes/{n}/qemu``. Devuelve el UPID de la tarea.

        Raises:
            ErrorProxLaunch: ``UPID_INVALIDO`` si la respuesta no trae un UPID válido.
        """
        data = self._llamar("POST", f"/nodes/{_seg(nodo)}/qemu", datos=parametros)
        if not isinstance(data, str) or not _RE_UPID.match(data):
            raise ErrorProxLaunch(CodigoError.UPID_INVALIDO, {}, f"respuesta: {data!r}")
        return data

    @staticmethod
    def _ruta_tarea(nodo: str, upid: str) -> str:
        # ':' '@' y '!' son válidos en un segmento de ruta y Proxmox los espera tal cual.
        return f"/nodes/{_seg(nodo)}/tasks/{quote(upid, safe=':@!')}"

    def estado_tarea(self, nodo: str, upid: str) -> EstadoTarea:
        """``GET /nodes/{n}/tasks/{upid}/status``."""
        data = self._llamar("GET", f"{self._ruta_tarea(nodo, upid)}/status")
        if not isinstance(data, dict) or "status" not in data:
            raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, f"estado inesperado: {data!r}")
        exit_ = data.get("exitstatus")
        return EstadoTarea(estado=str(data["status"]), exitstatus=str(exit_) if exit_ else None)

    def log_tarea(self, nodo: str, upid: str) -> list[str]:
        """``GET /nodes/{n}/tasks/{upid}/log``: líneas de texto del log."""
        data = self._llamar(
            "GET",
            f"{self._ruta_tarea(nodo, upid)}/log",
            params={"start": 0, "limit": LINEAS_LOG_TAREA},
        )
        return (
            [str(e["t"]) for e in data if isinstance(e, dict) and "t" in e]
            if isinstance(data, list)
            else []
        )

    def config_vm(self, nodo: str, vmid: int) -> dict[str, Any] | None:
        """``GET /nodes/{n}/qemu/{vmid}/config``; ``None`` si la máquina no existe."""
        try:
            data = self._llamar("GET", f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/config")
        except ErrorProxLaunch as e:
            if e.codigo == CodigoError.RECURSO_INEXISTENTE:
                return None
            raise
        return data if isinstance(data, dict) else None

    def estado_nodo(self, nodo: str) -> dict[str, Any]:
        """``GET /nodes/{n}/status``: sonda barata de que el nodo responde (595/596 si cayó)."""
        data = self._llamar("GET", f"/nodes/{_seg(nodo)}/status")
        return data if isinstance(data, dict) else {}

    def estado_actual_vm(self, nodo: str, vmid: int) -> dict[str, Any]:
        """``GET /nodes/{n}/qemu/{vmid}/status/current`` (``VM.Audit``): ``status``, ``lock``..."""
        data = self._llamar("GET", f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/status/current")
        if not isinstance(data, dict):
            raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, f"estado inesperado: {data!r}")
        return data

    def eliminar_vm(self, nodo: str, vmid: int) -> str:
        """``DELETE /nodes/{n}/qemu/{vmid}``. Devuelve el UPID de la tarea de borrado.

        Los parámetros van en la CONSULTA, no en el cuerpo (LAB-L05). Con
        ``destroy-unreferenced-disks=0`` y sin ``purge`` nunca se borra un volumen suelto
        (D-21). Método no seguro: el transporte no hace failover de host.

        Raises:
            ErrorProxLaunch: ``UPID_INVALIDO`` si la respuesta no trae un UPID válido.
        """
        data = self._llamar(
            "DELETE",
            f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}",
            params={"destroy-unreferenced-disks": 0},
        )
        if not isinstance(data, str) or not _RE_UPID.match(data):
            raise ErrorProxLaunch(CodigoError.UPID_INVALIDO, {}, f"respuesta: {data!r}")
        return data


class _ClienteSoloLectura(ClienteProxmox):
    """Cliente de la simulación: su ``cerrar()`` no suelta la credencial compartida."""

    def cerrar(self) -> None:
        return None
