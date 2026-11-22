"""ClienteProxmox: operaciones de alto nivel sobre la API.

Es el ÚNICO lugar que construye rutas de la API (arquitectura §5.3).
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import quote

from proxlaunch.nucleo.api.autenticacion import Autenticador
from proxlaunch.nucleo.api.multipart import CuerpoMultipart, ParteArchivo
from proxlaunch.nucleo.api.solo_lectura import TransporteSoloLectura
from proxlaunch.nucleo.api.transporte import Transporte, TransporteSubida, limitar_respuesta
from proxlaunch.nucleo.capacidades import interpretar_version
from proxlaunch.nucleo.cloudinit.snippets import nombre_de_snippet, volid_snippet_valido
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido, Plantilla, Snippet, Volumen
from proxlaunch.nucleo.modelos.inventario import (
    Bridge,
    Nodo,
    Storage,
    Topologia,
    Version,
    VMRemota,
)
from proxlaunch.nucleo.modelos.tarea import EstadoTarea
from proxlaunch.nucleo.origen.constantes import PARO_SIN_PROGRESO_S
from proxlaunch.nucleo.origen.nombres import validar_volid
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.transferencias.url import ChecksumTransferencia, UrlDescarga, ocultar_url

_log = logging.getLogger("proxlaunch.api.cliente")

_MIB = 1024**2
# UPID: "UPID:<nodo>:<pid>:<pstart>:<starttime>:<tipo>:<id>:<usuario>:" (forma laxa).
_RE_UPID = re.compile(r"^UPID:[A-Za-z0-9._-]+:\S+$")
# Líneas de log pedidas (por defecto la API devuelve solo 50). Por verificar en laboratorio.
LINEAS_LOG_TAREA = 500
# Método con el que se lee ``agent/network-get-interfaces`` (DT-B9, R-B3). Único punto: si el
# servidor responde «Method not implemented», ``interfaces_agente`` prueba el otro una vez.
METODO_AGENTE_INICIAL: Final = "GET"
# Tope de la respuesta del agente invitado, que no es de fiar (B4): 4 MiB antes de interpretarla.
MAX_RESPUESTA_AGENTE: Final = 4 * 1024 * 1024


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


def _formatos_de(valor: Any) -> frozenset[str] | None:
    """Formatos de disco de un storage según ``?format=1`` (tolerante); ``None`` si no constan.

    La API los devuelve como ``[{"raw": 1, "qcow2": 1}, "raw"]`` (permitidos y por defecto);
    también se aceptan un mapa, una lista de textos o una cadena separada por comas.
    """
    if isinstance(valor, list) and valor and isinstance(valor[0], dict):
        valor = valor[0]
    if isinstance(valor, dict):
        nombres = [str(k) for k in valor]
    elif isinstance(valor, list):
        nombres = [str(x) for x in valor]
    elif isinstance(valor, str):
        nombres = valor.split(",")
    else:
        return None
    formatos = frozenset(n.strip() for n in nombres if n.strip())
    return formatos or None


def _no_implementado(error: ErrorProxLaunch) -> bool:
    """¿El servidor dijo que el método no está implementado? (501 / «Method not implemented»)."""
    texto = error.detalle_tecnico.lower()
    return "not implemented" in texto or texto.startswith("http 501")


def _nombre_en_storage(volid: str) -> str | None:
    """Parte del volid tras ``storage:contenido/`` (``x.iso``); ``None`` si no tiene forma."""
    _, separador, resto = volid.partition(":")
    if not separador or not resto:
        return None
    _, barra, nombre = resto.partition("/")
    return nombre if barra and nombre else None


@dataclass(frozen=True)
class MetadatosUrl:
    """Lo que el SERVIDOR ve de una URL (``query-url-metadata``, CA-O11.1)."""

    nombre: str | None
    tamano: int | None
    tipo_mime: str | None


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
        # Método de lectura del agente (DT-B9): propio de cada cliente, es decir, de la sesión.
        self._metodo_agente: str = METODO_AGENTE_INICIAL
        self._agente_alternado = False
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

    def _preparar_credencial(self) -> None:
        """Comprueba que la sesión siga abierta y renueva la credencial si hace falta."""
        if self._cerrada.is_set():
            # Sesión cerrada: no se renueva con una credencial ya olvidada (hallazgo B1).
            raise ErrorProxLaunch(CodigoError.SESION_EXPIRADA)
        if self._auth.necesita_renovar():
            with self._cerrojo_renovacion:
                if self._auth.necesita_renovar():
                    self._auth.renovar(self._transporte_renovacion)

    def _llamar(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
    ) -> Any:
        self._preparar_credencial()
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

    def storages(self, nodo: str, *, con_formatos: bool = False) -> list[Storage]:
        """``GET /nodes/{n}/storage``: todos; el filtro ``images`` va en descubrimiento.

        ``?format=1`` solo se pide con ``con_formatos`` (CA-O04.6): el descubrimiento de la
        conexión no lo usa, para no cambiar la secuencia de peticiones del MVP 3.
        """
        data = self._llamar(
            "GET",
            f"/nodes/{_seg(nodo)}/storage",
            params={"format": 1} if con_formatos else None,
        )
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
                    formatos=_formatos_de(e.get("formats", e.get("format")))
                    if con_formatos
                    else None,
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

    def contenido_storage(self, nodo: str, storage: str, contenido: Contenido) -> list[Volumen]:
        """``GET /nodes/{n}/storage/{s}/content?content=…``: volúmenes de un tipo (I4-§A, §C).

        El nombre y el volid son texto no confiable: ``admitido`` indica si pasan la lista
        blanca (V-O02/V-O03, INV-O7); los no admitidos se devuelven igualmente para poder
        mostrarlos deshabilitados, pero nunca deben llegar a un parámetro de la API.
        """
        data = self._llamar(
            "GET",
            f"/nodes/{_seg(nodo)}/storage/{_seg(storage)}/content",
            params={"content": contenido.value},
        )
        resultado: list[Volumen] = []
        for e in data if isinstance(data, list) else []:
            if not isinstance(e, dict):
                continue
            volid = e.get("volid")
            nombre = _nombre_en_storage(volid) if isinstance(volid, str) else None
            if not isinstance(volid, str) or nombre is None:
                continue
            resultado.append(
                Volumen(
                    volid=volid,
                    storage=storage,
                    contenido=contenido,
                    nombre=nombre,
                    tamano_bytes=_entero(e.get("size")),
                    creado=_entero(e.get("ctime")),
                    admitido=validar_volid(volid, contenido) is None,
                )
            )
        return resultado

    def contenido_snippets(self, nodo: str, storage: str) -> list[Snippet]:
        """``GET /nodes/{n}/storage/{s}/content?content=snippets`` (B4, DT-B11).

        Como ``contenido_storage``, el volid y el nombre son texto no confiable: ``admitido``
        indica si tienen el formato ``almacén:snippets/archivo`` (V-B54).
        """
        data = self._llamar(
            "GET",
            f"/nodes/{_seg(nodo)}/storage/{_seg(storage)}/content",
            params={"content": "snippets"},
        )
        resultado: list[Snippet] = []
        for e in data if isinstance(data, list) else []:
            volid = e.get("volid") if isinstance(e, dict) else None
            if not isinstance(volid, str) or not nombre_de_snippet(volid):
                continue
            resultado.append(
                Snippet(
                    volid=volid,
                    nombre=nombre_de_snippet(volid),
                    tamano=_entero(e.get("size")),
                    admitido=volid_snippet_valido(volid),
                )
            )
        return resultado

    def plantillas_visibles(self) -> list[Plantilla]:
        """``GET /cluster/resources?type=vm``, solo las plantillas (``template = 1``, I4-§D)."""
        data = self._llamar("GET", "/cluster/resources", params={"type": "vm"})
        resultado: list[Plantilla] = []
        for e in data if isinstance(data, list) else []:
            if not isinstance(e, dict) or not _como_bool(e.get("template")):
                continue
            vmid = _entero(e.get("vmid"))
            if vmid is None or str(e.get("type", "qemu")) != "qemu":
                continue
            bloqueo = e.get("lock")
            resultado.append(
                Plantilla(
                    vmid=vmid,
                    nombre=str(e.get("name", "")),
                    nodo=str(e.get("node", "")),
                    bloqueo=str(bloqueo) if bloqueo else None,
                    disco_total_bytes=_entero(e.get("maxdisk")),
                )
            )
        return resultado

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

    def clonar_vm(self, nodo: str, vmid: int, parametros: dict[str, str]) -> str:
        """``POST /nodes/{n}/qemu/{vmid}/clone`` (``vmid`` = plantilla). Devuelve el UPID.

        Raises:
            ErrorProxLaunch: ``UPID_INVALIDO`` si la respuesta no trae un UPID válido.
        """
        data = self._llamar(
            "POST", f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/clone", datos=parametros
        )
        if not isinstance(data, str) or not _RE_UPID.match(data):
            raise ErrorProxLaunch(CodigoError.UPID_INVALIDO, {}, f"respuesta: {data!r}")
        return data

    def iniciar_vm(self, nodo: str, vmid: int) -> str:
        """``POST /nodes/{n}/qemu/{vmid}/status/start`` (``VM.PowerMgmt``). Devuelve el UPID.

        Raises:
            ErrorProxLaunch: ``UPID_INVALIDO`` si la respuesta no trae un UPID válido.
        """
        data = self._llamar("POST", f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/status/start")
        if not isinstance(data, str) or not _RE_UPID.match(data):
            raise ErrorProxLaunch(CodigoError.UPID_INVALIDO, {}, f"respuesta: {data!r}")
        return data

    def detener_vm(self, nodo: str, vmid: int) -> str:
        """``POST /nodes/{n}/qemu/{vmid}/status/stop`` (apagado inmediato; lo usa Deshacer).

        Devuelve el UPID de la tarea.

        Raises:
            ErrorProxLaunch: ``UPID_INVALIDO`` si la respuesta no trae un UPID válido.
        """
        data = self._llamar("POST", f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/status/stop")
        if not isinstance(data, str) or not _RE_UPID.match(data):
            raise ErrorProxLaunch(CodigoError.UPID_INVALIDO, {}, f"respuesta: {data!r}")
        return data

    def pools(self) -> list[dict[str, Any]]:
        """``GET /pools``: pools visibles para el usuario (``[{"poolid": …}]``)."""
        data = self._llamar("GET", "/pools")
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []

    def opciones_cluster(self) -> dict[str, Any]:
        """``GET /cluster/options``: opciones del centro de datos (política de etiquetas).

        Lanza ``ValueError`` si el cuerpo no es un diccionario: ``leer_politica_etiquetas`` lo
        trata como lectura fallida (V-A09) en vez de suponer la política por defecto.
        """
        data = self._llamar("GET", "/cluster/options")
        if not isinstance(data, dict):
            raise ValueError("cuerpo inesperado de /cluster/options")
        return data

    def configurar_vm(self, nodo: str, vmid: int, parametros: dict[str, str]) -> None:
        """``PUT /nodes/{n}/qemu/{vmid}/config`` (ajustes tras un clon)."""
        self._llamar("PUT", f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/config", datos=parametros)

    def configurar_contrasena(self, nodo: str, vmid: int, contrasena: Secreto) -> None:
        """``PUT /nodes/{n}/qemu/{vmid}/config`` con SOLO ``cipassword`` (RF-B1.17, R-B5).

        Es el único sitio que llama a ``Secreto.revelar()``. El valor se envía en claro por HTTPS
        (Proxmox lo guarda con hash salvo en Windows). Nunca se registra: el ``Secreto`` ya está
        en la lista de secretos del registro, que enmascara cualquier eco del servidor.

        Raises:
            ValueError: si el ``Secreto`` no está definido (ya se olvidó); no se envía nada.
        """
        if not contrasena.definido:
            raise ValueError("la contraseña no está definida")
        self._llamar(
            "PUT",
            f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/config",
            datos={"cipassword": contrasena.revelar()},
        )

    def interfaces_agente(self, nodo: str, vmid: int) -> Any:
        """``…/qemu/{vmid}/agent/network-get-interfaces``: respuesta cruda del agente (B3).

        Usa ``METODO_AGENTE_INICIAL`` (GET). Ante «Method not implemented» prueba el otro método
        UNA vez y lo recuerda en este cliente (una sesión): DT-B9, R-B3 [LAB]. Los demás
        errores se propagan tal cual para que ``clasificar_error`` los interprete.
        """
        with limitar_respuesta(MAX_RESPUESTA_AGENTE):  # B4: la respuesta del invitado no es fiable
            return self._interfaces_agente(nodo, vmid)

    def _interfaces_agente(self, nodo: str, vmid: int) -> Any:
        ruta = f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/agent/network-get-interfaces"
        try:
            return self._llamar(self._metodo_agente, ruta)
        except ErrorProxLaunch as e:
            if self._agente_alternado or not _no_implementado(e):
                raise
            self._agente_alternado = True  # solo se prueba el otro método una vez
            otro = "POST" if self._metodo_agente == "GET" else "GET"
            try:
                resultado = self._llamar(otro, ruta)
            except ErrorProxLaunch as e2:
                if not _no_implementado(e2):
                    # El servidor sí implementa ese método (respondió algo distinto de 501, p. ej.
                    # un 500 «agent is not running»): se recuerda aunque el intento fallara.
                    self._metodo_agente = otro
                raise
            self._metodo_agente = otro
            return resultado

    def convertir_en_plantilla(self, nodo: str, vmid: int) -> str | None:
        """``POST /nodes/{n}/qemu/{vmid}/template`` (``VM.Allocate``). Devuelve el UPID de la
        tarea o ``None`` si el servidor responde sin ella."""
        data = self._llamar("POST", f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/template")
        return data if isinstance(data, str) and _RE_UPID.match(data) else None

    def ampliar_disco(self, nodo: str, vmid: int, disco: str, tamano_gib: int) -> str | None:
        """``PUT /nodes/{n}/qemu/{vmid}/resize`` con ``size=<n>G`` (valor absoluto, idempotente).

        Devuelve el UPID si el servidor lanza una tarea o ``None`` si responde sin ella
        (por confirmar en LAB-M4-12).
        """
        data = self._llamar(
            "PUT",
            f"/nodes/{_seg(nodo)}/qemu/{_seg(vmid)}/resize",
            datos={"disk": disco, "size": f"{int(tamano_gib)}G"},
        )
        return data if isinstance(data, str) and _RE_UPID.match(data) else None

    def subir_archivo(
        self,
        nodo: str,
        storage: str,
        contenido: Contenido,
        parte: ParteArchivo,
        checksum_sha256: str,
        *,
        al_progresar: Callable[[int, int], None] | None = None,
        cancelado: threading.Event | None = None,
        al_leer: Callable[[bytes], None] | None = None,
    ) -> str:
        """``POST /nodes/{n}/storage/{s}/upload`` en streaming (I4-§B). Devuelve el UPID.

        Envía, en este orden, ``content``, ``checksum-algorithm=sha256``, ``checksum`` y, al
        final, la parte ``filename`` con ``Content-Type: application/octet-stream``. Sin
        reintento ni failover. Nunca se envía ``tmpfilename``.

        Raises:
            TypeError: si el transporte no admite subidas (``TransporteSubida``).
            ErrorProxLaunch: ``UPID_INVALIDO``, ``TRANSFERENCIA_CANCELADA`` y los de red.
        """
        if contenido == Contenido.IMAGENES:
            raise ValueError("solo se suben archivos de contenido iso o import")
        transporte = self._transporte
        if not isinstance(transporte, TransporteSubida):
            raise TypeError("el transporte no admite subidas (TransporteSubida)")
        self._preparar_credencial()
        # El orden lo impone pveproxy (AnyEvent.pm, file_upload_multipart): content,
        # checksum-algorithm, checksum y al final el archivo; otro orden da 400 «wrong
        # Content-Disposition … in multipart» (DEFECTO-LAB-01). No reordenar.
        cuerpo = CuerpoMultipart(
            {
                "content": contenido.value,
                "checksum-algorithm": "sha256",
                "checksum": checksum_sha256,
            },
            parte,
            al_progresar=al_progresar,
            cancelado=cancelado,
            al_leer=al_leer,
        )
        data = transporte.subir(
            f"/nodes/{_seg(nodo)}/storage/{_seg(storage)}/upload",
            cuerpo,
            timeout_lectura=PARO_SIN_PROGRESO_S,
        )
        if not isinstance(data, str) or not _RE_UPID.match(data):
            raise ErrorProxLaunch(CodigoError.UPID_INVALIDO, {}, f"respuesta: {data!r}")
        return data

    @staticmethod
    def _sin_url(error: ErrorProxLaunch, url: UrlDescarga) -> ErrorProxLaunch:
        """Quita la URL del detalle técnico y de los parámetros del error (INV-O6)."""
        error.detalle_tecnico = ocultar_url(error.detalle_tecnico, url)
        error.params = {k: ocultar_url(v, url) for k, v in error.params.items()}
        return error

    def metadatos_url(
        self, nodo: str, url: UrlDescarga, *, verificar_certificados: bool = True
    ) -> MetadatosUrl:
        """``GET /nodes/{n}/query-url-metadata``: nombre, tamaño y tipo que ve el SERVIDOR.

        La app no se conecta a la URL (RNF-O05).
        """
        try:
            data = self._llamar(
                "GET",
                f"/nodes/{_seg(nodo)}/query-url-metadata",
                params={"url": url.texto, "verify-certificates": int(verificar_certificados)},
            )
        except ErrorProxLaunch as e:
            raise self._sin_url(e, url) from None
        info = data if isinstance(data, dict) else {}
        nombre = info.get("filename")
        tipo = info.get("mimetype")
        return MetadatosUrl(
            nombre=str(nombre) if nombre else None,
            tamano=_entero(info.get("size")),
            tipo_mime=str(tipo) if tipo else None,
        )

    def descargar_url(
        self,
        nodo: str,
        storage: str,
        *,
        url: UrlDescarga,
        contenido: Contenido,
        nombre: str,
        checksum: ChecksumTransferencia | None,
        verificar_certificados: bool = True,
    ) -> str:
        """``POST /nodes/{n}/storage/{s}/download-url``: el nodo descarga la URL. Devuelve el UPID.

        Sin ``compression`` (los archivos se guardan tal cual). El ``detalle_tecnico`` y los
        parámetros de cualquier error pasan por ``ocultar_url`` (INV-O6).
        """
        if contenido == Contenido.IMAGENES:
            raise ValueError("solo se descargan archivos de contenido iso o import")
        datos: dict[str, Any] = {
            "url": url.texto,
            "content": contenido.value,
            "filename": nombre,
            "verify-certificates": int(verificar_certificados),
        }
        if checksum is not None:
            datos["checksum"] = checksum.valor
            datos["checksum-algorithm"] = checksum.algoritmo.value
        try:
            data = self._llamar(
                "POST", f"/nodes/{_seg(nodo)}/storage/{_seg(storage)}/download-url", datos=datos
            )
        except ErrorProxLaunch as e:
            raise self._sin_url(e, url) from None
        if not isinstance(data, str) or not _RE_UPID.match(data):
            raise ErrorProxLaunch(CodigoError.UPID_INVALIDO, {}, "respuesta sin UPID")
        return data


class _ClienteSoloLectura(ClienteProxmox):
    """Cliente de la simulación: su ``cerrar()`` no suelta la credencial compartida."""

    def cerrar(self) -> None:
        return None
