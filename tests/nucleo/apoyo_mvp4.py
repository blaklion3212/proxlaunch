"""Apoyo para las pruebas del núcleo del MVP 4 (origen del SO). Sin aserciones.

Construye inventarios con ``storages_todos`` y catálogo, configuraciones por origen, permisos
(rol de 10 y de 14 privilegios) y un clúster simulado que entiende ``clone``, ``PUT config``,
``PUT resize`` y los listados de contenido. Los límites que se simulan son la red, el reloj y el
servidor; todo lo demás es código real del núcleo.
"""

from __future__ import annotations

import contextlib
import dataclasses
import re
import threading
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import (
    CatalogoServidor,
    Contenido,
    DetallePlantilla,
    DiscoPlantilla,
    ListadoStorage,
    PermisosEfectivos,
    Plantilla,
    Volumen,
)
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage, Version
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    RefPlantilla,
    RefVolumen,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed, OrigenSO
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH

from .apoyo_lote import GIB, Cluster, inventario, nodo, storage, upid_de

ROL_MVP3: tuple[str, ...] = ROL_PROXLAUNCH[:10]
ROL_MVP4: tuple[str, ...] = ROL_PROXLAUNCH

VOLID_ISO = "local:iso/alpine.iso"
VOLID_VIRTIO = "local:iso/virtio-win-0.1.271.iso"
VOLID_IMAGEN = "local:import/cirros.qcow2"


def permisos(privilegios=ROL_MVP4, *, quitar: tuple[str, ...] = ()) -> PermisosEfectivos:
    """Permisos efectivos ``{"/": {privilegio: 1}}`` sin los privilegios de ``quitar``."""
    return PermisosEfectivos(rutas={"/": {p: 1 for p in privilegios if p not in quitar}})


def volumen(
    volid: str, contenido: Contenido = Contenido.ISO, tamano: int | None = 100 * 1024**2
) -> Volumen:
    storage_, _, resto = volid.partition(":")
    from proxlaunch.nucleo.origen.nombres import validar_volid

    return Volumen(
        volid=volid,
        storage=storage_,
        contenido=contenido,
        nombre=resto.partition("/")[2],
        tamano_bytes=tamano,
        creado=1,
        admitido=validar_volid(volid, contenido) is None,
    )


def disco_plantilla(clave: str = "scsi0", storage_: str = "local-lvm", gib: int = 8):
    return DiscoPlantilla(clave, storage_, gib * GIB, "raw")


def detalle_plantilla(
    discos=None, *, bridges=("vmbr0",), etiquetas=frozenset(), cores=2, memoria=2048, lock=None
) -> DetallePlantilla:
    return DetallePlantilla(
        es_plantilla=True,
        bloqueo=lock,
        discos=tuple(discos if discos is not None else [disco_plantilla()]),
        bridges=tuple(bridges),
        sockets=1,
        cores=cores,
        tipo_cpu="x86-64-v2-AES",
        memoria_mib=memoria,
        etiquetas=frozenset(etiquetas),
    )


def plantilla_pve(
    vmid: int = 9000, nombre: str = "base", nodo_: str = "pve1", detalle=None, bloqueo=None
) -> Plantilla:
    return Plantilla(
        vmid,
        nombre,
        nodo_,
        bloqueo,
        8 * GIB,
        detalle if detalle is not None else detalle_plantilla(),
    )


def listado(nodo_: str, storage_: str, contenido: Contenido, *volids: str) -> ListadoStorage:
    return ListadoStorage(nodo_, storage_, contenido, tuple(volumen(v, contenido) for v in volids))


def inv_origen(
    *,
    version: Version | None = None,
    nodos: tuple[str, ...] = ("pve1", "pve2"),
    privilegios=ROL_MVP4,
    permisos_efectivos: PermisosEfectivos | None | bool = True,
    listados: tuple[ListadoStorage, ...] = (),
    plantillas: tuple[Plantilla, ...] | None = None,
    formatos: dict[str, frozenset[str]] | None = None,
    extra_storages: dict[str, tuple[Storage, ...]] | None = None,
) -> Inventario:
    """Inventario con ``local`` (dir: iso, import, images), ``local-lvm`` (lvmthin: images),
    ``nfs1`` compartido (nfs: images) y catálogo. ``permisos_efectivos=None`` = desconocidos."""
    base = (
        storage("local", "dir", 200, contenido="images,iso,import"),
        storage("local-lvm", "lvmthin", 300, contenido="images"),
        storage("nfs1", "nfs", 400, compartido=True, contenido="images,iso"),
    )
    todos = {n: base + (extra_storages or {}).get(n, ()) for n in nodos}
    inv = inventario(
        tuple(nodo(n) for n in nodos),
        storages={n: tuple(s for s in sts if "images" in s.contenido) for n, sts in todos.items()},
        version=version,
    )
    inv.storages_todos = todos
    if permisos_efectivos is True:
        permisos_efectivos = permisos(privilegios)
    inv.catalogo = CatalogoServidor(
        permisos=permisos_efectivos or None,
        listados=listados,
        plantillas=plantillas,
        formatos=formatos or {},
    )
    return inv


def cfg_base(**cambios: Any) -> ConfiguracionVM:
    base: dict[str, Any] = {
        "vmid": 100,
        "nombre": "srv-web-01",
        "nodo": "pve1",
        "discos": [Disco("local-lvm", 32)],
        "redes": [InterfazRed("vmbr0")],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def cfg_iso(
    volid: str | None = VOLID_ISO,
    tipo_so: TipoSO | None = TipoSO.LINUX,
    *,
    drivers: str | None = None,
    sin_drivers: bool = False,
    **cambios: Any,
) -> ConfiguracionVM:
    det = DetalleIso(
        iso=RefVolumen(volid.partition("/")[2] if volid else "", volid),
        drivers=None if drivers is None else RefVolumen(drivers.partition("/")[2], drivers),
        sin_drivers=sin_drivers,
    )
    return cfg_base(origen=OrigenSO.ISO, tipo_so=tipo_so, detalle_origen=det, **cambios)


def cfg_import(volid: str | None = VOLID_IMAGEN, **det: Any) -> ConfiguracionVM:
    cambios = det.pop("cfg", {})
    ref = RefVolumen(volid.partition("/")[2] if volid else "", volid)
    return cfg_base(
        origen=OrigenSO.IMPORTAR_DISCO,
        detalle_origen=DetalleImportacion(imagen=ref, **det),
        **cambios,
    )


def cfg_clon(
    plantilla: str = "base",
    vmid_plantilla: int | None = None,
    nodo_plantilla: str | None = None,
    *,
    modo: ModoClon = ModoClon.AUTOMATICO,
    efectivo: ModoClon | None = None,
    ajustes: AjustesClon | None = None,
    storage_destino: str | None = None,
    **cambios: Any,
) -> ConfiguracionVM:
    det = DetalleClon(
        plantilla=RefPlantilla(plantilla, vmid_plantilla, nodo_plantilla),
        modo=modo,
        ajustes=ajustes or AjustesClon(),
        storage_destino=storage_destino,
        modo_efectivo=efectivo,
    )
    return cfg_base(origen=OrigenSO.CLONAR_PLANTILLA, detalle_origen=det, **cambios)


# --- Clúster con clon, ajustes y contenido de storage ---------------------------------------


class ClusterM4(Cluster):
    """``Cluster`` que además atiende ``clone``, ``PUT config``/``resize`` y los listados.

    ``plantillas``: ``{vmid: {"nodo", "nombre", "config"}}``. ``contenido``: ``{(nodo, storage):
    [volids]}``. Cuenta ``POST …/clone`` por ``newid`` (``clones``) y las escrituras PUT.
    """

    def __init__(self, nodos: tuple[str, ...] = ("pve1",)) -> None:
        super().__init__(nodos)
        self.plantillas: dict[int, dict[str, Any]] = {}
        self.contenido: dict[tuple[str, str], list[str]] = {}
        self.clones: dict[int, int] = {}
        self.cuerpos_clon: dict[int, dict[str, Any]] = {}
        self.puts: list[tuple[str, int, str, dict[str, Any]]] = []
        self.storages_api: dict[str, list[dict[str, Any]]] = {}
        self._activos_clon: dict[str, int] = {}
        self.max_clon_por_nodo = 0
        self.max_clon_total = 0
        self.barrera_clon: threading.Barrier | None = None
        self.retardo_clon = 0.0
        self._cerr_m4 = threading.Lock()

    @staticmethod
    def _storages_por_defecto() -> list[dict[str, Any]]:
        def st(id_: str, tipo: str, content: str, formatos: Any, compartido: int = 0):
            return {
                "storage": id_, "type": tipo, "content": content, "active": 1, "enabled": 1,
                "shared": compartido, "total": 800 * GIB, "avail": 400 * GIB, "formats": formatos,
            }  # fmt: skip

        return [
            st("local", "dir", "images,iso,import", [{"raw": 1, "qcow2": 1}, "raw"]),
            st("local-lvm", "lvmthin", "images", [{"raw": 1}, "raw"]),
        ]

    def agregar_plantilla(
        self, vmid: int, nombre: str = "base", nodo_: str = "pve1", **config: Any
    ) -> None:
        cfg = {
            "template": 1,
            "name": nombre,
            "cores": 2,
            "sockets": 1,
            "memory": 2048,
            "scsi0": "local-lvm:base-9000-disk-0,size=8G",
            "net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0",
            "digest": "d",
        }
        cfg.update(config)
        self.plantillas[vmid] = {"nodo": nodo_, "nombre": nombre, "config": cfg}

    def _normal(self, ll):  # noqa: D102
        m, ruta = ll.metodo, ll.ruta
        if m == "GET":
            if ruta == "/cluster/resources" and (ll.params or {}).get("type") == "vm":
                filas = [
                    {
                        "vmid": v,
                        "name": p["nombre"],
                        "node": p["nodo"],
                        "type": "qemu",
                        "template": 1,
                        "maxdisk": 8 * GIB,
                    }
                    for v, p in self.plantillas.items()
                ]
                return filas + super()._normal(ll)
            if mt := re.match(r"^/nodes/([^/]+)/qemu/(\d+)/config$", ruta):
                p = self.plantillas.get(int(mt[2]))
                if p is not None and p["nodo"] == mt[1]:
                    return dict(p["config"])
            if mt := re.match(r"^/nodes/([^/]+)/storage$", ruta):
                return self.storages_api.get(mt[1], self._storages_por_defecto())
            if mt := re.match(r"^/nodes/([^/]+)/storage/([^/]+)/content$", ruta):
                volids = self.contenido.get((mt[1], mt[2]), [])
                tipo = (ll.params or {}).get("content", "iso")
                return [
                    {"volid": v, "size": 1000, "ctime": 1}
                    for v in volids
                    if v.partition(":")[2].startswith(tipo + "/")
                ]
        if m == "POST" and (mt := re.match(r"^/nodes/([^/]+)/qemu/(\d+)/clone$", ruta)):
            return self._clonar(ll, mt[1], int(mt[2]))
        if m == "PUT" and (mt := re.match(r"^/nodes/([^/]+)/qemu/(\d+)/(config|resize)$", ruta)):
            return self._put(ll, mt[1], int(mt[2]), mt[3])
        return super()._normal(ll)

    def _clonar(self, ll, nodo_: str, plantilla: int):
        datos = ll.datos or {}
        newid = int(datos["newid"])
        with self._cerr_m4:
            self.clones[newid] = self.clones.get(newid, 0) + 1
            self.cuerpos_clon[newid] = dict(datos)
            self._activos_clon[nodo_] = self._activos_clon.get(nodo_, 0) + 1
            self.max_clon_por_nodo = max(self.max_clon_por_nodo, self._activos_clon[nodo_])
            self.max_clon_total = max(self.max_clon_total, sum(self._activos_clon.values()))
        try:
            if self.barrera_clon is not None:
                with contextlib.suppress(threading.BrokenBarrierError):
                    self.barrera_clon.wait(timeout=3)
            if self.retardo_clon:
                import time

                time.sleep(self.retardo_clon)
            base = self.plantillas[plantilla]["config"]
            config = {k: v for k, v in base.items() if k != "template"}
            config["name"] = datos.get("name", "")
            destino = datos.get("target") or nodo_
            if self.exitstatus.get(newid, "OK") == "OK":
                with self._cerrojo:
                    self.vms[newid] = {"nodo": destino, "config": config, "status": "stopped"}
            return upid_de(nodo_, newid, "qmclone")
        finally:
            with self._cerr_m4:
                self._activos_clon[nodo_] -= 1

    def _put(self, ll, nodo_: str, vmid: int, que: str):
        with self._cerr_m4:
            self.puts.append((nodo_, vmid, que, dict(ll.datos or {})))
        vm = self.vms.get(vmid)
        if vm is None:
            raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {"nodo": nodo_}, "no existe")
        if que == "config":
            vm["config"].update(ll.datos or {})
            return None
        disco = (ll.datos or {})["disk"]
        gib = int(str(ll.datos["size"]).rstrip("G"))
        actual = vm["config"].get(disco, "")
        vm["config"][disco] = re.sub(r"size=\w+", f"size={gib}G", actual) or f"x:y,size={gib}G"
        return None

    # La API del clúster base solo reconoce RE_UPID de qmcreate/qmdestroy: la ampliamos.
    def _tarea(self, upid: str, que: str):
        mt = re.match(r"UPID:[^:]+:[^:]+:[^:]+:[^:]+:(?:qmcreate|qmdestroy|qmclone):(\d+):", upid)
        if mt is None:
            return super()._tarea(upid, que)
        vmid = int(mt[1])
        if que == "log":
            return [{"n": 1, "t": f"TASK log {vmid}"}]
        return {"status": "stopped", "exitstatus": self.exitstatus.get(vmid, "OK")}


def copia_con(cfg: ConfiguracionVM, **cambios: Any) -> ConfiguracionVM:
    return dataclasses.replace(cfg, **cambios)


# --- Transporte con subida (servidor de archivos simulado) ----------------------------------------


class ServidorArchivos:
    """Transporte en memoria que entiende los endpoints de transferencia y ``subir``.

    Estado: ``contenido`` = ``{(nodo, storage): {nombre: (tamano, tipo)}}``. ``subidas`` guarda
    el cuerpo multipart COMPLETO de cada subida (solo para archivos pequeños). Los fallos se
    inyectan con ``fallos[clave]`` (una excepción o un ``callable``).
    """

    UPID = "UPID:pve1:0003A1B2:00F4C1D3:6535AB12:imgcopy::ana@pve!lab:"
    UPID_DESCARGA = "UPID:pve1:0003A1B3:00F4C1D4:6535AB13:download::ana@pve!lab:"

    def __init__(self, *, hosts=("10.0.0.1",), libre=500 * GIB, raiz_libre: int | None = 50 * GIB):
        self._hosts = hosts
        self._auth = None
        self.llamadas: list[Any] = []
        self.contenido: dict[tuple[str, str], dict[str, tuple[int, str]]] = {("pve1", "local"): {}}
        self.libre = libre
        self.raiz_libre = raiz_libre
        self.subidas: list[bytes] = []
        self.cabeceras_subida: list[dict[str, Any]] = []
        self.timeouts_subida: list[float] = []
        self.fallos: dict[str, Any] = {}
        self.estados_tarea: list[Any] = [
            {"status": "running"},
            {"status": "stopped", "exitstatus": "OK"},
        ]
        self.log: list[str] = []
        self.metadatos: dict[str, Any] = {"filename": "x.iso", "size": 1000, "mimetype": "x/y"}
        self.guardar_al_subir = True
        self.tamano_guardado: int | None = None  # fuerza un tamaño distinto en el servidor
        self.al_subir = None  # callback(cuerpo_bytes) antes de devolver el UPID
        self._i = 0
        self._cerrojo = threading.Lock()

    host_activo = property(lambda self: self._hosts[0])

    def usar_autenticador(self, auth) -> None:
        self._auth = auth

    def _registrar(self, metodo, ruta, params, datos):
        from .apoyo_api import Llamada

        ll = Llamada(metodo, ruta, params, datos)
        with self._cerrojo:
            self.llamadas.append(ll)
        return ll

    def llamadas_a(self, metodo: str, patron: str = ""):
        return [
            c for c in self.llamadas if c.metodo == metodo.upper() and re.search(patron, c.ruta)
        ]

    def _fallo(self, clave: str):
        f = self.fallos.get(clave)
        if f is None:
            return
        if callable(f) and not isinstance(f, BaseException):
            f = f()
        if isinstance(f, BaseException):
            raise f

    def peticion(self, metodo, ruta, *, params=None, datos=None):
        metodo = metodo.upper()
        if metodo in ("DELETE", "PUT"):
            raise AssertionError(f"escritura no esperada en transferencias: {metodo} {ruta}")
        if self._auth is not None:
            self._auth.aplicar(metodo, {}, {})
        self._registrar(metodo, ruta, params, datos)
        if mt := re.match(r"^/nodes/([^/]+)/storage/([^/]+)/content$", ruta):
            self._fallo("contenido")
            tipo = (params or {}).get("content", "iso")
            archivos = self.contenido.get((mt[1], mt[2]), {})
            return [
                {"volid": f"{mt[2]}:{tipo}/{n}", "size": t, "ctime": 1}
                for n, (t, _) in archivos.items()
            ]
        if mt := re.match(r"^/nodes/([^/]+)/storage$", ruta):
            self._fallo("storages")
            return [
                {"storage": s, "type": "dir", "content": "iso,import,images", "active": 1,
                 "shared": 0, "total": self.libre * 2, "avail": self.libre}
                for (n, s) in self.contenido if n == mt[1]
            ]  # fmt: skip
        if re.match(r"^/nodes/[^/]+/status$", ruta):
            self._fallo("estado_nodo")
            return {} if self.raiz_libre is None else {"rootfs": {"avail": self.raiz_libre}}
        if re.match(r"^/nodes/[^/]+/query-url-metadata$", ruta):
            self._fallo("metadatos")
            return dict(self.metadatos)
        if mt := re.match(r"^/nodes/([^/]+)/storage/([^/]+)/download-url$", ruta):
            self._fallo("descargar")
            nombre = (datos or {})["filename"]
            if self.guardar_al_subir:
                self.contenido.setdefault((mt[1], mt[2]), {})[nombre] = (
                    self.tamano_guardado or int(self.metadatos.get("size") or 0),
                    (datos or {})["content"],
                )
            return self.UPID_DESCARGA
        if re.search(r"/tasks/.+/status$", ruta):
            self._fallo("estado_tarea")
            with self._cerrojo:
                item = self.estados_tarea[min(self._i, len(self.estados_tarea) - 1)]
                self._i += 1
            if isinstance(item, BaseException):
                raise item
            return item
        if re.search(r"/tasks/.+/log$", ruta):
            return [{"n": i, "t": t} for i, t in enumerate(self.log)]
        raise AssertionError(f"ruta no simulada: {metodo} {ruta}")

    def subir(self, ruta, cuerpo, *, timeout_lectura):
        from proxlaunch.nucleo.api.multipart import SubidaCancelada

        self._registrar("POST", ruta, None, None)
        self.timeouts_subida.append(timeout_lectura)
        if self._auth is not None:
            self._auth.aplicar("POST", {}, {})
        trozos = []
        try:
            for trozo in cuerpo:
                trozos.append(trozo)
                self._fallo("durante_subida")
        except SubidaCancelada:
            raise ErrorProxLaunch(
                CodigoError.TRANSFERENCIA_CANCELADA, {"quedo_archivo": "desconocido"}
            ) from None
        crudo = b"".join(trozos)
        assert len(crudo) == len(cuerpo)  # Content-Length exacto
        self.subidas.append(crudo)
        self.cabeceras_subida.append(
            {"Content-Type": cuerpo.tipo_contenido, "Content-Length": len(cuerpo)}
        )
        self._fallo("tras_subir")
        if self.al_subir is not None:
            self.al_subir(crudo)
        mt = re.match(r"^/nodes/([^/]+)/storage/([^/]+)/upload$", ruta)
        nodo_, st = mt[1], mt[2]
        nombre = re.search(rb'filename="([^"]*)"', crudo)[1].decode()
        contenido = re.search(rb'name="content"\r\n\r\n([^\r]*)', crudo)[1].decode()
        if self.guardar_al_subir:
            tam = self.tamano_guardado if self.tamano_guardado is not None else cuerpo._parte.tamano
            self.contenido.setdefault((nodo_, st), {})[nombre] = (tam, contenido)
        return self.UPID

    @property
    def metodos(self) -> list[str]:
        return [c.metodo for c in self.llamadas]
