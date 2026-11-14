"""Apoyo de las pruebas de interfaz del MVP 4 (origen del SO). Sin aserciones.

Solo contiene piezas de los límites del sistema: inventarios con ``storages_todos`` y catálogo,
capacidades de origen calculadas con el núcleo real, volúmenes y plantillas de ejemplo, y un
controlador de transferencias falso (lanzador real, servicio falso). Nunca hay red real ni
diálogos modales: ``ControladorOrigen._ejecutar`` se sustituye en las pruebas que lo necesitan.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.api.cliente import MetadatosUrl
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos.catalogo import (
    CatalogoServidor,
    Contenido,
    DetallePlantilla,
    DiscoPlantilla,
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
from proxlaunch.nucleo.origen.capacidades_origen import CapacidadesOrigen, calcular_capacidades
from proxlaunch.nucleo.origen.nombres import validar_volid
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.transferencias.modelos import (
    ComprobacionPrevia,
    EstadoTransferencia,
    Progreso,
    ResultadoTransferencia,
)

from .apoyo import GIB, inventario_individual, storage

VOLID_ISO = "local:iso/alpine.iso"
VOLID_VIRTIO = "local:iso/virtio-win-0.1.271.iso"
VOLID_IMAGEN = "local:import/cirros.qcow2"
ROL_10 = ROL_PROXLAUNCH[:10]
ROL_14 = ROL_PROXLAUNCH


def permisos(privilegios=ROL_14, *, quitar: tuple[str, ...] = ()) -> PermisosEfectivos:
    """Permisos efectivos ``{"/": {privilegio: 1}}`` sin los privilegios de ``quitar``."""
    return PermisosEfectivos(rutas={"/": {p: 1 for p in privilegios if p not in quitar}})


def volumen(volid: str, contenido: Contenido = Contenido.ISO, tamano: int | None = 100 * 1024**2):
    storage_, _, resto = volid.partition(":")
    return Volumen(
        volid=volid,
        storage=storage_,
        contenido=contenido,
        nombre=resto.partition("/")[2],
        tamano_bytes=tamano,
        creado=1,
        admitido=validar_volid(volid, contenido) is None,
    )


def detalle_plantilla(cores: int = 2, memoria: int = 2048) -> DetallePlantilla:
    return DetallePlantilla(
        es_plantilla=True,
        bloqueo=None,
        discos=(DiscoPlantilla("scsi0", "local-lvm", 8 * GIB, "raw"),),
        bridges=("vmbr0",),
        sockets=1,
        cores=cores,
        tipo_cpu="x86-64-v2-AES",
        memoria_mib=memoria,
        etiquetas=frozenset(),
    )


def plantilla_pve(vmid: int = 9000, nombre: str = "base", nodo: str = "pve") -> Plantilla:
    return Plantilla(vmid, nombre, nodo, None, 8 * GIB, detalle_plantilla())


def inv_origen(
    *,
    version: tuple[int, int] = (9, 2),
    contenido_local: str = "images,iso,import",
    privilegios=ROL_14,
    permisos_efectivos: PermisosEfectivos | None | bool = True,
    volumenes: tuple[Volumen, ...] = (),
    plantillas: tuple[Plantilla, ...] | None = None,
    extra_images: bool = False,
) -> Inventario:
    """Servidor individual (nodo «pve») con ``local`` (iso, import, images) y ``local-lvm``.

    ``permisos_efectivos=None`` = permisos desconocidos. ``extra_images`` añade un segundo
    storage con ``images`` (hay que preguntar cuál usar siempre).
    """
    inv = inventario_individual()
    inv.version = Version(f"{version[0]}.{version[1]}", version[0], version[1], 0)
    todos = [
        storage("local", "dir", contenido_local, 50),
        storage("local-lvm", "lvmthin", "images,rootdir", 150),
    ]
    if extra_images:
        todos.append(storage("datos", "dir", "images", 400))
    inv.storages_todos = {"pve": tuple(todos)}
    inv.storages = {"pve": tuple(s for s in todos if "images" in s.contenido)}
    if permisos_efectivos is True:
        permisos_efectivos = permisos(privilegios)
    inv.catalogo = CatalogoServidor(
        permisos=permisos_efectivos or None,
        listados=(),
        plantillas=plantillas,
        formatos={},
    )
    return inv


def caps_origen(inv: Inventario | None = None, nodo: str | None = "pve") -> CapacidadesOrigen:
    """Capacidades de origen con el núcleo real para la versión del inventario."""
    inv = inv or inv_origen()
    caps = capacidades_para(inv.version, None)
    return calcular_capacidades(caps, inv, nodo)


def storage_sin(id_: str, contenido: str, tipo: str = "dir") -> Storage:
    return storage(id_, tipo, contenido, 100)


def cfg_base(**cambios: Any) -> ConfiguracionVM:
    base: dict[str, Any] = {
        "vmid": 150,
        "nombre": "srv-web-01",
        "nodo": "pve",
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


def cfg_import(volid: str | None = VOLID_IMAGEN, **cambios: Any) -> ConfiguracionVM:
    ref = RefVolumen(volid.partition("/")[2] if volid else "", volid)
    return cfg_base(
        origen=OrigenSO.IMPORTAR_DISCO, detalle_origen=DetalleImportacion(imagen=ref), **cambios
    )


def cfg_clon(
    nombre_plantilla: str = "base",
    vmid_plantilla: int | None = 9000,
    *,
    modo: ModoClon = ModoClon.AUTOMATICO,
    efectivo: ModoClon | None = None,
    ajustes: AjustesClon | None = None,
    **cambios: Any,
) -> ConfiguracionVM:
    det = DetalleClon(
        plantilla=RefPlantilla(nombre_plantilla, vmid_plantilla, "pve"),
        modo=modo,
        ajustes=ajustes or AjustesClon(),
        modo_efectivo=efectivo,
    )
    return cfg_base(origen=OrigenSO.CLONAR_PLANTILLA, detalle_origen=det, **cambios)


# --- Transferencias: controlador y servicio falsos ---------------------------------------------


def resultado_transferencia(
    estado: EstadoTransferencia = EstadoTransferencia.TERMINADA,
    *,
    volid: str | None = VOLID_ISO,
    error: Any = None,
    quedo: bool | None = None,
    upid: str | None = None,
) -> ResultadoTransferencia:
    return ResultadoTransferencia(
        estado=estado, volid=volid, error=error, quedo_archivo=quedo, duracion_s=1.0, upid=upid
    )


def comprobacion(problemas=(), *, existente: str | None = None) -> ComprobacionPrevia:
    return ComprobacionPrevia(
        volid_existente=existente,
        libre_storage_bytes=10 * GIB,
        libre_raiz_bytes=10 * GIB,
        permiso=True,
        problemas=tuple(problemas),
    )


def progreso(
    hechos: int, total: int, estado: EstadoTransferencia = EstadoTransferencia.TRANSFIRIENDO
) -> Progreso:
    return Progreso(estado, hechos, total, 1_000_000.0, 10.0, None)


@dataclass
class ServicioTransferenciasFalso:
    """Imita ``ServicioTransferencias``: registra llamadas y devuelve lo programado.

    ``subir``/``descargar`` bloquean hasta que la prueba libera ``puerta`` (o se cancela el
    evento recibido) para poder observar el estado «en curso».
    """

    comprobacion: Any = field(default_factory=comprobacion)
    resultado: Any = field(default_factory=resultado_transferencia)
    metadatos: Any = field(default_factory=lambda: MetadatosUrl("alpine.iso", 1024 * 1024, None))
    progresos: list[Progreso] = field(default_factory=list)
    llamadas: list[tuple] = field(default_factory=list)
    bloquear: bool = False
    ocupado: bool = False
    puerta: threading.Event = field(default_factory=threading.Event)
    inicio: threading.Event = field(default_factory=threading.Event)
    cancelado_visto: bool = False

    def comprobar(self, destino, tamano, inv, *, para_subida):
        self.llamadas.append(("comprobar", destino, tamano, para_subida))
        if isinstance(self.comprobacion, BaseException):
            raise self.comprobacion
        return self.comprobacion

    def consultar_url(self, nodo, url, *, verificar_certificados=True):
        self.llamadas.append(("consultar_url", nodo, url.host, verificar_certificados))
        if isinstance(self.metadatos, BaseException):
            raise self.metadatos
        return self.metadatos

    def _correr(self, nombre, cancelado, al_progresar):
        self.ocupado = True
        self.inicio.set()
        try:
            for p in self.progresos:
                if al_progresar is not None:
                    al_progresar(p)
            if self.bloquear:
                while not self.puerta.is_set():
                    if cancelado.is_set():
                        self.cancelado_visto = True
                        return resultado_transferencia(
                            EstadoTransferencia.CANCELADA, volid=None, quedo=False
                        )
                    cancelado.wait(0.01)
            if isinstance(self.resultado, BaseException):
                raise self.resultado
            return self.resultado
        finally:
            self.ocupado = False

    def subir(self, ruta, destino, inv, *, cancelado, al_progresar=None, acepta_aviso_raiz=False):
        self.llamadas.append(("subir", destino, acepta_aviso_raiz))
        return self._correr("subir", cancelado, al_progresar)

    def descargar(
        self,
        url,
        destino,
        inv,
        *,
        checksum=None,
        verificar_certificados=True,
        al_progresar=None,
        dejar_de_esperar=None,
    ):
        self.llamadas.append(("descargar", destino, verificar_certificados))
        return self._correr("descargar", dejar_de_esperar, al_progresar)


class ControladorFalso:
    """Cumple ``ControladorTransferencia`` con lanzador real y servicio falso."""

    def __init__(self, inv: Inventario | None, servicio: ServicioTransferenciasFalso | None = None):
        self.lanzador = Lanzador()
        self.servicio_transferencias = servicio or ServicioTransferenciasFalso()
        self.inventario = inv
        self.modo_avanzado = False
        self.preguntas: list[tuple[Contenido, str]] = []
        self.respuesta_storage: str | None = "local"

    def storage_para(self, contenido, nodo, parent):
        self.preguntas.append((contenido, nodo))
        return self.respuesta_storage
