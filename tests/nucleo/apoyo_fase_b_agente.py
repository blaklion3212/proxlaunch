"""Apoyo de las pruebas P3 de la fase B (0.7.0): espera de IP (B3) y plantilla desde imagen (B2).

Sin aserciones. Contiene:

- ``ClusterAgente``: un ``ClusterA`` (que ya entiende ``status/start``, ``clone``, ``PUT config``,
  ``resize`` y los listados) con ``agent/network-get-interfaces`` en GET y POST guionizado por
  VMID, ``POST …/template`` (tarea ``qmtemplate``), contenido ``import`` con tamaños,
  ``download-url``
  y ``query-url-metadata``.
- ``TransporteAgente``: ``TransporteCluster`` que además admite subidas multipart (``subir``).
- Constructores de respuestas del agente (con errores traducidos con el traductor REAL de Proxmox),
  de imágenes qcow2 mínimas, de solicitudes de B2 y del «mundo» de cada flujo.

Los límites del sistema que se simulan son la red, el reloj y el servidor; el resto es código real.
Ninguna prueba que use esto hace ``sleep`` ni red.
"""

from __future__ import annotations

import dataclasses
import json
import re
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from proxlaunch.nucleo.api.traductor_errores import traducir_http
from proxlaunch.nucleo.capacidades import Capacidades, capacidades_para
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.motor import enlazar_espera
from proxlaunch.nucleo.modelos.inventario import Inventario, Version
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed
from proxlaunch.nucleo.plantilla_imagen import (
    EstadoPlantillaImagen,
    FijasPlantilla,
    OrigenImagen,
    ServicioPlantillaImagen,
    SolicitudPlantillaImagen,
)
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion, ServicioTransferencias

from .apoyo_api import Llamada, crear_sesion
from .apoyo_fase_a import ClusterA, banco_a, def_lote, plan_de
from .apoyo_lote import (
    NORMAL,
    ControlAutomatico,
    RelojSeguro,
    TransporteCluster,
    _Normal,
    plantilla,
    upid_de,
)
from .apoyo_mvp4 import inv_origen

DIR_DATOS = Path(__file__).resolve().parents[1] / "datos" / "fase_b"

GIB = 1024**3

# --- Respuestas y errores del agente -------------------------------------------------------------

MAC_NET0 = "BC:24:11:AA:BB:01"
MAC_OTRA = "BC:24:11:CC:DD:02"


def error_http(estado: int, motivo: str, cuerpo: str = "") -> ErrorProxLaunch:
    """El error que produce el traductor REAL ante esa respuesta de Proxmox (no uno inventado)."""
    return traducir_http(estado, motivo, cuerpo, nodo="pve1", sesion_ticket=False)


def err_no_en_ejecucion() -> ErrorProxLaunch:
    return error_http(500, "QEMU guest agent is not running")


def err_mv_apagada(vmid: int = 100) -> ErrorProxLaunch:
    return error_http(500, f"VM {vmid} is not running")


def err_sin_agente() -> ErrorProxLaunch:
    return error_http(500, "No QEMU guest agent configured")


def err_sin_permiso() -> ErrorProxLaunch:
    return error_http(403, "Permission check failed (/vms/100, VM.GuestAgent.Audit)")


def err_no_implementado() -> ErrorProxLaunch:
    return error_http(501, "Method not implemented")


def err_no_existe(vmid: int = 100) -> ErrorProxLaunch:
    return error_http(
        500, f"Configuration file 'nodes/pve1/qemu-server/{vmid}.conf' does not exist"
    )


def err_sesion_caducada() -> ErrorProxLaunch:
    return traducir_http(401, "invalid PVE ticket", "", sesion_ticket=True)


def interfaz(nombre: str, mac: str | None, *ips: str) -> dict[str, Any]:
    """Una interfaz como la devuelve el agente (``ip-addresses`` con prefijo)."""
    direcciones = [
        {
            "ip-address": ip,
            "ip-address-type": "ipv6" if ":" in ip else "ipv4",
            "prefix": 64 if ":" in ip else 24,
        }
        for ip in ips
    ]
    datos: dict[str, Any] = {"name": nombre, "ip-addresses": direcciones}
    if mac is not None:
        datos["hardware-address"] = mac.lower()
    return datos


def respuesta(*interfaces: dict[str, Any]) -> dict[str, Any]:
    """Cuerpo ``data`` de ``network-get-interfaces``."""
    return {"result": list(interfaces)}


def respuesta_con_ip(ip: str = "192.168.1.50", mac: str = MAC_NET0) -> dict[str, Any]:
    """El caso típico: ``lo`` y la interfaz de la MV con su IPv4 y su IPv6 local de enlace."""
    return respuesta(
        interfaz("lo", "00:00:00:00:00:00", "127.0.0.1", "::1"),
        interfaz("ens18", mac, ip, "fe80::be24:11ff:feaa:bb01"),
    )


def cargar_respuestas_agente() -> dict[str, Any]:
    """Respuestas de ejemplo de ``tests/datos/fase_b/p3_agente_respuestas.json``."""
    return json.loads((DIR_DATOS / "p3_agente_respuestas.json").read_text(encoding="utf-8"))


# --- Clúster simulado con agente, plantilla y transferencias -------------------------------------

_RE_AGENTE = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/agent/network-get-interfaces$")
_RE_PLANTILLA = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/template$")
_RE_CONTENIDO = re.compile(r"^/nodes/(?P<n>[^/]+)/storage/(?P<s>[^/]+)/content$")
_RE_DESCARGA = re.compile(r"^/nodes/(?P<n>[^/]+)/storage/(?P<s>[^/]+)/download-url$")
_RE_METADATOS = re.compile(r"^/nodes/(?P<n>[^/]+)/query-url-metadata$")
_RE_POST_QEMU = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu$")
_RE_UPID_TIPO = re.compile(r"UPID:[^:]+:[^:]+:[^:]+:[^:]+:(?P<t>\w+):(?P<v>\d*):")

UPID_COPIA = "UPID:pve1:0003A1B2:00F4C1D3:6535AB12:imgcopy::ana@pve!lab:"
UPID_DESCARGA = "UPID:pve1:0003A1B3:00F4C1D4:6535AB13:download::ana@pve!lab:"


def mac_de(vmid: int) -> str:
    """MAC determinista de ``net0`` para una MV creada por el doble."""
    return f"BC:24:11:00:{(vmid >> 8) & 0xFF:02X}:{vmid & 0xFF:02X}"


class ClusterAgente(ClusterA):
    """``ClusterA`` con agente invitado, conversión en plantilla e imágenes ``import``.

    - ``guion[vmid]``: respuestas sucesivas de ``network-get-interfaces`` (la última se repite).
      Cada elemento es un valor (se devuelve), un ``ErrorProxLaunch`` (se lanza) o un ``callable``
      que recibe el número de sondeo (1, 2…) y devuelve o lanza. Sin guion: «agent is not running».
    - ``sondeos``: ``(vmid, método, instante)`` de cada petición al agente (instante = ``reloj``).
    - ``metodos_agente``: métodos HTTP que el servidor implementa (si no, 501).
    - ``archivos[(nodo, storage)]``: ``{nombre: tamaño}`` del contenido ``import``.
    - ``config_extra``: se funde en la configuración de cada MV creada con ``POST /qemu``; las MVs
      creadas llevan ``net0`` con MAC (``mac_de``) y el ``agent``/``scsi0`` pedidos.
    """

    def __init__(self, nodos: tuple[str, ...] = ("pve1",)) -> None:
        super().__init__(nodos)
        self.reloj: RelojSeguro | None = None
        self.guion: dict[int, list[Any]] = {}
        self.sondeos: list[tuple[int, str, float]] = []
        self.metodos_agente: set[str] = {"GET", "POST"}
        self.config_extra: dict[str, Any] = {}
        self._contador: dict[int, int] = {}
        # B2
        self.archivos: dict[tuple[str, str], dict[str, int]] = {("pve1", "local"): {}}
        self.subidas: list[dict[str, Any]] = []
        self.descargas: list[dict[str, Any]] = []
        self.metadatos: dict[str, Any] = {
            "filename": "imagen.img",
            "size": 600 * 1024**2,
            "mimetype": "application/octet-stream",
        }
        self.salida_tarea: dict[str, str] = {}  # por tipo de tarea: imgcopy, download, qmtemplate
        self.convertidas: list[int] = []
        self.en_curso: dict[tuple[str, int], int] = {}  # (tipo, vmid) → consultas «running»
        self.guardar_aun_fallando = False  # la imagen queda en import aunque la tarea falle
        self.snapshots: set[int] = set()
        self.tamano_importado_gib = 3  # tamaño del disco que deja la importación de una URL
        self.virtuales: dict[str, int] = {}  # nombre → tamaño virtual (cabecera qcow2 subida)

    # --- Atención ------------------------------------------------------------------------------

    def _ahora(self) -> float:
        return self.reloj.ahora() if self.reloj is not None else 0.0

    def _fase_b(self, ll: Llamada) -> Any:
        """Antes que lo de la clase base: el agente y las rutas de B2 son de este doble."""
        propio = self._propio(ll)
        if not isinstance(propio, _Normal):
            return propio
        base = getattr(super(), "_fase_b", None)
        return base(ll) if base is not None else NORMAL

    def _propio(self, ll: Llamada) -> Any:
        """Rutas que atiende este doble; ``NORMAL`` si no es ninguna de ellas."""
        m, ruta = ll.metodo, ll.ruta
        if m in ("GET", "POST") and (mt := _RE_AGENTE.match(ruta)):
            return self._agente(ll, int(mt["v"]))
        if m == "POST" and (mt := _RE_PLANTILLA.match(ruta)):
            return self._convertir(mt["n"], int(mt["v"]))
        if (
            m == "GET"
            and (mt := _RE_CONTENIDO.match(ruta))
            and (ll.params or {}).get("content") == "import"
        ):
            archivos = self.archivos.get((mt["n"], mt["s"]), {})
            return [
                {"volid": f"{mt['s']}:import/{n}", "size": t, "ctime": 1}
                for n, t in archivos.items()
            ]
        if m == "POST" and ruta.endswith("/upload"):
            return None  # la subida la completa ``TransporteAgente.subir``
        if m == "GET" and _RE_METADATOS.match(ruta):
            return dict(self.metadatos)
        if m == "POST" and (mt := _RE_DESCARGA.match(ruta)):
            datos = dict(ll.datos or {})
            self.descargas.append(datos)
            nombre = datos["filename"]
            if self.exito("download"):
                tam = int(self.metadatos.get("size") or 0)
                self.archivos.setdefault((mt["n"], mt["s"]), {})[nombre] = tam
            return UPID_DESCARGA
        return NORMAL

    def _normal(self, ll: Llamada) -> Any:  # noqa: D102
        m, ruta = ll.metodo, ll.ruta
        propio = self._propio(ll)  # por si la clase base ya no delega en ``_fase_b``
        if not isinstance(propio, _Normal):
            return propio
        resultado = super()._normal(ll)
        if m == "GET" and ruta == "/cluster/resources" and (ll.params or {}).get("type") == "vm":
            plantillas = set(self.plantillas_visibles())
            for fila in resultado:
                if fila.get("vmid") in plantillas:
                    fila["template"] = 1  # la MV convertida por B2 ya es una plantilla visible
        if m == "POST" and _RE_POST_QEMU.match(ruta) and ll.datos and "vmid" in ll.datos:
            self._enriquecer(int(ll.datos["vmid"]), ll.datos)
        return resultado

    def exito(self, tipo: str) -> bool:
        return self.salida_tarea.get(tipo, "OK") == "OK"

    def _enriquecer(self, vmid: int, datos: dict[str, Any]) -> None:
        """La MV creada conserva lo pedido (``agent``, ``scsi0``, ``ide2``…) y gana MAC en net0."""
        with self._cerrojo:
            vm = self.vms.get(vmid)
            if vm is None:
                return
            config = vm["config"]
            for clave, valor in datos.items():
                if clave in ("vmid", "tags", "start"):
                    continue
                config[clave] = valor
            if "net0" in config and "=" in str(config["net0"]):
                modelo, _, resto = str(config["net0"]).partition(",")
                if not re.search(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}", modelo):
                    config["net0"] = f"{modelo.split('=')[0]}={mac_de(vmid)},{resto}"
            scsi0 = str(config.get("scsi0", ""))
            if "import-from=" in scsi0:
                almacen = scsi0.split(":", 1)[0]
                nombre = scsi0.split("import-from=", 1)[1].split(",", 1)[0].rpartition("/")[2]
                virtual = self.virtuales.get(nombre)
                gib = -(-virtual // GIB) if virtual else self.tamano_importado_gib
                config["scsi0"] = f"{almacen}:vm-{vmid}-disk-0,size={gib}G"
            config.update(self.config_extra)

    def _agente(self, ll: Llamada, vmid: int) -> Any:
        with self._cerrojo:
            self.sondeos.append((vmid, ll.metodo, self._ahora()))
            if ll.metodo not in self.metodos_agente:
                n = 0
            else:  # un 501 no consume elemento del guion
                n = self._contador.get(vmid, 0) + 1
                self._contador[vmid] = n
            guion = list(self.guion.get(vmid, []))
        if n == 0:
            raise err_no_implementado()
        if vmid not in self.vms:
            raise err_no_existe(vmid)
        if not guion:
            raise err_no_en_ejecucion()
        item = guion[min(n - 1, len(guion) - 1)]
        if callable(item) and not isinstance(item, BaseException):
            item = item(n)
        if isinstance(item, BaseException):
            raise item
        return item

    def sondeos_de(self, vmid: int) -> list[float]:
        """Instantes de los sondeos de una MV."""
        return [t for v, _, t in self.sondeos if v == vmid]

    def metodos_de(self, vmid: int) -> list[str]:
        return [m for v, m, _ in self.sondeos if v == vmid]

    def _convertir(self, nodo_: str, vmid: int) -> Any:
        with self._cerrojo:
            vm = self.vms.get(vmid)
            if vm is None or vm["nodo"] != nodo_:
                raise err_no_existe(vmid)
            if vm["status"] == "running":
                raise error_http(500, "you can't convert a VM to template if VM is running")
            if vmid in self.snapshots:
                raise error_http(500, "you can't convert a VM to template if VM contains snapshots")
            self.convertidas.append(vmid)
            if self.exito("qmtemplate"):
                vm["config"]["template"] = 1
        return upid_de(nodo_, vmid, "qmtemplate")

    def _tarea(self, upid: str, que: str) -> Any:  # noqa: D102
        mt = _RE_UPID_TIPO.match(upid)
        if mt is None:
            return super()._tarea(upid, que)
        tipo = mt["t"]
        vmid = int(mt["v"]) if mt["v"] else -1
        if que == "status":
            with self._cerrojo:
                faltan = self.en_curso.get((tipo, vmid), 0)
                if faltan > 0:
                    self.en_curso[(tipo, vmid)] = faltan - 1
                    return {"status": "running"}
        if tipo in ("imgcopy", "download", "qmtemplate"):
            if que == "log":
                return [{"n": 1, "t": f"TASK log {tipo}"}]
            return {"status": "stopped", "exitstatus": self.salida_tarea.get(tipo, "OK")}
        return super()._tarea(upid, que)

    # --- Resumen para las aserciones --------------------------------------------------------------

    def escrituras_de(self, patron: str = "") -> list[Llamada]:
        return [
            c for c in self.llamadas if c.metodo != "GET" and re.search(patron, c.ruta) is not None
        ]

    def plantillas_visibles(self) -> list[int]:
        return [v for v, d in self.vms.items() if str(d["config"].get("template")) == "1"]


class TransporteAgente(TransporteCluster):
    """``TransporteCluster`` con subida multipart (``TransporteSubida``) sobre ``ClusterAgente``."""

    def __init__(self, cluster: ClusterAgente) -> None:
        super().__init__(cluster)
        self.cluster: ClusterAgente = cluster
        self.fallo_subida: BaseException | None = None

    def subir(self, ruta: str, cuerpo: Any, *, timeout_lectura: float) -> Any:
        cl = self.cluster
        cl.atender("POST", ruta, None, None)  # queda en el registro de llamadas
        if self._auth is not None:
            self._auth.aplicar("POST", {}, {})
        trozos = [bytes(t) for t in cuerpo]
        crudo = b"".join(trozos)
        mt = re.match(r"^/nodes/([^/]+)/storage/([^/]+)/upload$", ruta)
        assert mt is not None, ruta
        nombre = re.search(rb'filename="([^"]*)"', crudo)
        contenido = re.search(rb'name="content"\r\n\r\n([^\r]*)', crudo)
        assert nombre is not None and contenido is not None
        marca = b"Content-Type: application/octet-stream\r\n\r\n"
        archivo = crudo.split(marca, 1)[1].rsplit(b"\r\n--", 1)[0]
        campos = {
            k.decode(): v.decode()
            for k, v in re.findall(rb'name="([^"]+)"\r\n\r\n([^\r]*)\r\n', crudo)
        }
        if archivo[:4] == b"QFI\xfb" and len(archivo) >= 32:
            cl.virtuales[nombre[1].decode()] = struct.unpack_from(">Q", archivo, 24)[0]
        cl.subidas.append(
            {
                "nodo": mt[1],
                "storage": mt[2],
                "nombre": nombre[1].decode(),
                "content": contenido[1].decode(),
                "archivo": archivo,
                "campos": campos,
            }
        )
        if self.fallo_subida is not None:
            raise self.fallo_subida
        if cl.exito("imgcopy") or cl.guardar_aun_fallando:
            cl.archivos.setdefault((mt[1], mt[2]), {})[nombre[1].decode()] = len(archivo)
        return UPID_COPIA


# --- Mundos de prueba ----------------------------------------------------------------------------


@dataclass
class MundoAgente:
    """Sesión real + reloj seguro + ``ClusterAgente`` (para B3)."""

    cluster: ClusterAgente
    sesion: Sesion
    reloj: RelojSeguro
    resultados: list[tuple[int, Any]] = field(default_factory=list)
    _cerrojo: threading.Lock = field(default_factory=threading.Lock)

    def al_resultado(self, vmid: int, resultado: Any) -> None:
        with self._cerrojo:
            self.resultados.append((vmid, resultado))

    def espera(self, **kw: Any) -> Any:
        from proxlaunch.nucleo.agente.espera import EsperaIp

        return EsperaIp(self.sesion, self.reloj, self.al_resultado, **kw)


def crear_mundo_agente(
    nodos: tuple[str, ...] = ("pve1",), cluster: ClusterAgente | None = None
) -> MundoAgente:
    cl = cluster or ClusterAgente(nodos)
    reloj = RelojSeguro()
    cl.reloj = reloj
    sesion = crear_sesion(TransporteAgente(cl), reloj=reloj)  # type: ignore[arg-type]
    return MundoAgente(cl, sesion, reloj)


def agregar_mv_con_agente(
    cl: ClusterAgente,
    vmid: int,
    nodo: str = "pve1",
    nombre: str | None = None,
    *,
    agent: str | None = "1",
    mac: str | None = MAC_NET0,
    status: str = "running",
) -> None:
    """MV ya encendida con ``agent`` y ``net0`` con la MAC dada."""
    extra: dict[str, Any] = {}
    if agent is not None:
        extra["agent"] = agent
    if mac is not None:
        extra["net0"] = f"virtio={mac},bridge=vmbr0"
    cl.agregar_vm(vmid, nodo, nombre or f"mv-{vmid}", status=status, extra=extra)


def mundo_con_mvs(*vmids: int, mac: str = MAC_NET0, **kw: Any) -> MundoAgente:
    m = crear_mundo_agente()
    for v in vmids:
        agregar_mv_con_agente(m.cluster, v, mac=mac, **kw)
    return m


def ejecutar_espera(m: MundoAgente, espera: Any, *, limite_s: float = 20.0) -> dict[int, Any]:
    """Cierra el alta y ejecuta la espera en el hilo de la prueba (el reloj es simulado, así que
    termina sin esperar de verdad). Un vigilante evita que un fallo cuelgue la suite."""
    espera.sin_mas_objetivos()
    resultado: dict[str, Any] = {}

    def correr() -> None:
        resultado["r"] = espera.ejecutar()

    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    hilo.join(limite_s)
    assert not hilo.is_alive(), "EsperaIp.ejecutar no terminó en el tiempo acotado"
    return resultado["r"]  # type: ignore[no-any-return]


# --- B2: imágenes y solicitudes ------------------------------------------------------------------


def cabecera_qcow2(virtual_bytes: int = 2 * GIB, *, version: int = 3, backing: int = 0) -> bytes:
    """Cabecera qcow2 mínima (104 bytes): firma, versión, tamaño virtual y sin cifrado."""
    h = bytearray(104)
    h[0:4] = b"QFI\xfb"
    struct.pack_into(">I", h, 4, version)
    struct.pack_into(">Q", h, 8, backing)
    struct.pack_into(">Q", h, 24, virtual_bytes)
    struct.pack_into(">I", h, 32, 0)
    return bytes(h)


def crear_imagen(
    ruta: Path, virtual_bytes: int = 2 * GIB, *, relleno: int = 4096, contenido: bytes | None = None
) -> Path:
    """Escribe una imagen PEQUEÑA con cabecera qcow2 (el tamaño virtual es solo el declarado)."""
    ruta.write_bytes(contenido if contenido is not None else cabecera_qcow2(virtual_bytes))
    if contenido is None and relleno:
        with ruta.open("ab") as f:
            f.write(bytes(range(256)) * (relleno // 256))
    return ruta


def crear_imagen_cruda(ruta: Path, tamano: int = 4096) -> Path:
    """Imagen cruda (sin firma conocida): ``inspeccionar_imagen`` la trata como ``raw``."""
    ruta.write_bytes(bytes(range(1, 255)) * (tamano // 254 + 1))
    return ruta


def cfg_plantilla(**cambios: Any) -> ConfiguracionVM:
    """``cfg`` de B2: nombre, VMID, CPU, memoria y red; el disco final (10 GiB) en ``discos[0]``."""
    base: dict[str, Any] = {
        "vmid": 9100,
        "nombre": "plantilla-ubuntu-2404",
        "nodo": "pve1",
        "cores": 2,
        "memoria_mib": 2048,
        "discos": [Disco("local-lvm", 10)],
        "redes": [InterfazRed("vmbr0")],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def solicitud(
    ruta: Path | None = None,
    *,
    origen: OrigenImagen = OrigenImagen.ARCHIVO_LOCAL,
    nombre_archivo: str = "ubuntu-24.04.qcow2",
    **cambios: Any,
) -> SolicitudPlantillaImagen:
    """Solicitud completa y válida (con la casilla de irreversibilidad marcada).

    Para un archivo local pasa ``ruta`` (el tamaño virtual se toma de la cabecera si no se da).
    """
    base: dict[str, Any] = {
        "origen": origen,
        "ruta_local": ruta,
        "url": None,
        "volid_existente": None,
        "suma": None,
        "nodo": "pve1",
        "storage_import": "local",
        "nombre_archivo": nombre_archivo,
        "accion_existente": None,
        "storage_destino": "local-lvm",
        "cfg": cfg_plantilla(),
        "fijas": FijasPlantilla(),
        "cloudinit": None,
        "confirmada": True,
    }
    base.update(cambios)
    return SolicitudPlantillaImagen(**base)


def caps(version: tuple[int, int, int] = (9, 2, 1)) -> Capacidades:
    return capacidades_para(Version(".".join(map(str, version)), *version), None)


@dataclass
class MundoB2:
    """Servicio de B2 real sobre un ``ClusterAgente`` con subida e inventario de ``inv_origen``."""

    cluster: ClusterAgente
    sesion: Sesion
    reloj: RelojSeguro
    inv: Inventario
    registro: RegistroSesion
    transferencias: ServicioTransferencias
    servicio: ServicioPlantillaImagen
    cancelado: threading.Event = field(default_factory=threading.Event)
    estado: EstadoPlantillaImagen = field(default_factory=EstadoPlantillaImagen)
    cambios: list[EstadoPlantillaImagen] = field(default_factory=list)
    progreso: list[Any] = field(default_factory=list)

    def ejecutar(self, sol: SolicitudPlantillaImagen) -> EstadoPlantillaImagen:
        return self.servicio.ejecutar(
            sol,
            self.inv,
            self.estado,
            self.cambios.append,
            self.progreso.append,
            self.cancelado,
        )

    def escrituras(self) -> list[tuple[str, str]]:
        return [(c.metodo, c.ruta) for c in self.cluster.llamadas if c.metodo != "GET"]


def crear_mundo_b2(
    *,
    version: Version | None = None,
    permisos_efectivos: Any = True,
    cluster: ClusterAgente | None = None,
    inv: Inventario | None = None,
) -> MundoB2:
    cl = cluster or ClusterAgente(("pve1",))
    reloj = RelojSeguro()
    cl.reloj = reloj
    sesion = crear_sesion(TransporteAgente(cl), reloj=reloj, version=version)  # type: ignore[arg-type]
    inventario_ = inv or inv_origen(
        version=version, nodos=("pve1",), permisos_efectivos=permisos_efectivos
    )
    registro = RegistroSesion()
    transferencias = ServicioTransferencias(
        sesion, reloj, registro, intervalo_s=0.01, hora_local=lambda: "10:00"
    )
    servicio = ServicioPlantillaImagen(sesion, reloj, transferencias, intervalo_s=0.01)
    return MundoB2(cl, sesion, reloj, inventario_, registro, transferencias, servicio)


def con_cfg(sol: SolicitudPlantillaImagen, **cambios: Any) -> SolicitudPlantillaImagen:
    """Copia de la solicitud con cambios en su ``cfg``."""
    return dataclasses.replace(sol, cfg=dataclasses.replace(sol.cfg, **cambios))


def hacer_plantilla_a_medias(
    m: MundoB2, vmid: int = 9100, nombre: str = "plantilla-ubuntu-2404", **extra: Any
) -> None:
    """Una MV con ese nombre ya existente en el clúster (como la deja un paso 2 interrumpido)."""
    m.cluster.agregar_vm(vmid, "pve1", nombre, status="stopped", extra=extra)


def callable_en(accion: Callable[[int], Any]) -> Callable[[int], Any]:
    """Azúcar para guiones: un elemento que ejecuta ``accion`` en cada sondeo."""
    return accion


# --- B3 con el motor del lote --------------------------------------------------------------------


def lote(cantidad: int = 3, *, esperar_ip: bool = True, plazo: int = 60, **cfg):
    """Banco sobre ``ClusterAgente`` y un plan de ``cantidad`` MVs con agente y encendido."""
    cl = ClusterAgente(("pve1",))
    cl.config_extra = {"agent": "1"}  # la MV creada trae el agente habilitado (como un clon)
    b = banco_a(cluster=cl)
    cl.reloj = b.reloj
    base: dict[str, Any] = {
        "agente_qemu": True,
        "encender": True,
        "esperar_ip": esperar_ip,
        "plazo_ip_s": plazo,
    }
    base.update(cfg)
    plan = plan_de(b, def_lote(cantidad, plantilla_vm=plantilla(**base)))
    return b, plan


def correr(b, plan, *, con_espera: bool = True, control: ControlAutomatico | None = None):
    """Ejecuta el lote con el motor real y deja la espera SIN ejecutar (el motor no la aguarda)."""
    from proxlaunch.nucleo.agente.espera import EsperaIp

    libro = Libro(plan)
    espera = (
        EsperaIp(b.sesion, b.reloj, enlazar_espera(libro, b.observador)) if con_espera else None
    )
    control = control or ControlAutomatico("suspender")
    b.motor().ejecutar(plan, b.inv, b.observador, control, libro=libro, espera_ip=espera)
    return libro, espera, control


def vmids(plan) -> list[int]:
    return [e.vmid for e in plan.elementos]
