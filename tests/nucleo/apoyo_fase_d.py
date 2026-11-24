"""Apoyo para las pruebas de la fase D (0.9.0): arquitectura, hardware del clúster y formatos.

Solo constructores de inventarios, catálogos, configuraciones y mundos de clon; sin aserciones.
Los límites que se simulan son la red, el reloj y el servidor (``Cluster`` de ``apoyo_lote`` con
las rutas de la fase D); todo lo demás es código real del núcleo.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from typing import Any

from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    ArquitecturaNodo,
    FuenteArquitectura,
)
from proxlaunch.nucleo.capacidades import Capacidades, capacidades_para
from proxlaunch.nucleo.hardware_cluster.modelos import (
    AsignacionPCI,
    AsignacionUSB,
    ComprobacionNodo,
    EntradaMapeo,
    HardwareCluster,
    InfoHardwareCluster,
    Mapeo,
    ModeloCpu,
    TipoMapeo,
)
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario, Version
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH

from .apoyo_fase_a import BancoA, ClusterA, banco_a, cfg_vm
from .apoyo_fase_b_p1 import V_84, V_90, V_91, V_92, MundoB, config_plantilla
from .apoyo_mvp4 import ROL_MVP4, VOLID_IMAGEN, VOLID_ISO, VOLID_VIRTIO, inv_origen, listado

__all__ = [
    "V_84",
    "V_90",
    "V_91",
    "V_92",
    "ARM",
    "VOLID_IMAGEN_2",
    "X86",
    "DESC",
    "caps_de",
    "cluster_d",
    "banco_d",
    "inv_arq",
    "mapeo",
    "info_hw",
    "hw",
    "pci",
    "usb",
    "cfg_arm",
    "MundoD",
    "con_hardware",
    "permisos_mapeo",
]

VOLID_IMAGEN_2 = "local:import/debian.qcow2"
X86 = ArquitecturaNodo(Arquitectura.X86_64, FuenteArquitectura.KERNEL)
ARM = ArquitecturaNodo(Arquitectura.AARCH64, FuenteArquitectura.KERNEL)
DESC = ArquitecturaNodo(Arquitectura.DESCONOCIDA, FuenteArquitectura.NINGUNA, "sin_permiso")


def caps_de(version: Version) -> Capacidades:
    return capacidades_para(version, None)


def inv_arq(
    arqs: Mapping[str, ArquitecturaNodo | Arquitectura] | None = None,
    *,
    nodos: tuple[str, ...] = ("pve1", "pve2"),
    version: Version = V_92,
    privilegios: Iterable[str] = ROL_MVP4,
    hardware: InfoHardwareCluster | None = None,
    **kw: Any,
) -> Inventario:
    """Inventario con ``local``/``local-lvm``/``nfs1``, el catálogo y la arquitectura de cada nodo.

    ``arqs``: ``{nodo: ArquitecturaNodo | Arquitectura}``; un nodo ausente queda sin detectar.
    """
    kw.setdefault(
        "listados",
        tuple(
            f
            for n in nodos
            for f in (
                listado(n, "local", Contenido.ISO, VOLID_ISO, VOLID_VIRTIO),
                listado(n, "local", Contenido.IMPORT, VOLID_IMAGEN, VOLID_IMAGEN_2),
            )
        ),
    )
    inv = inv_origen(version=version, nodos=nodos, privilegios=tuple(privilegios), **kw)
    mapa: dict[str, ArquitecturaNodo] = {}
    for n, a in (arqs or {}).items():
        mapa[n] = (
            a if isinstance(a, ArquitecturaNodo) else ArquitecturaNodo(a, FuenteArquitectura.KERNEL)
        )
    inv.arquitecturas = mapa
    if hardware is not None and inv.catalogo is not None:
        inv.catalogo = dataclasses.replace(inv.catalogo, hardware=hardware)
    return inv


def cluster_d(nodos: tuple[str, ...] = ("pve1",)) -> ClusterA:
    """``ClusterA`` con el ISO, virtio-win y las imágenes de importación en ``local`` de cada nodo
    (el planificador relee el catálogo del servidor: el doble debe servirlo)."""
    cl = ClusterA(nodos)
    for n in nodos:
        cl.contenido[(n, "local")] = [VOLID_ISO, VOLID_VIRTIO, VOLID_IMAGEN, VOLID_IMAGEN_2]
    return cl


def banco_d(
    arqs: Mapping[str, ArquitecturaNodo | Arquitectura] | None = None,
    *,
    nodos: tuple[str, ...] = ("pve1",),
    version: Version = V_92,
    hardware: InfoHardwareCluster | None = None,
    cluster: ClusterA | None = None,
    **kw: Any,
) -> BancoA:
    """Banco (sesión real + motor) con inventario ``inv_arq`` y la versión de Proxmox dada."""
    inv = inv_arq(arqs, nodos=nodos, version=version, hardware=hardware, **kw)
    banco = banco_a(nodos, cluster=cluster or cluster_d(nodos), inv=inv)
    banco.sesion.version = version
    banco.sesion.capacidades = caps_de(version)
    return banco


def permisos_mapeo(
    *rutas: str, base: Iterable[str] = ROL_PROXLAUNCH, privilegio: str = "Mapping.Use"
):
    """Permisos efectivos: el rol de 14 en ``/`` más ``privilegio`` en cada ruta de ``rutas``."""
    from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos

    todas: dict[str, dict[str, int]] = {"/": dict.fromkeys(base, 1)}
    for r in rutas:
        todas[r] = {privilegio: 1}
    return PermisosEfectivos(rutas=todas)


def mapeo(
    tipo: TipoMapeo | str,
    id_: str,
    *nodos: str,
    mdev: bool = False,
    migrable: bool = False,
    por_nodo: Mapping[str, int] | None = None,
    descripcion: str = "",
) -> Mapeo:
    """``Mapeo`` del modelo; ``por_nodo`` repite la entrada (varios dispositivos en un nodo)."""
    conteo = dict.fromkeys(nodos, 1) | dict(por_nodo or {})
    entradas = tuple(EntradaMapeo(n, "/dev/x") for n, c in conteo.items() for _ in range(c))
    return Mapeo(
        tipo=TipoMapeo(tipo),
        id=id_,
        descripcion=descripcion,
        entradas=entradas,
        mdev=mdev,
        migrable_en_vivo=migrable,
    )


def info_hw(
    *mapeos: Mapeo,
    cpus: Mapping[str, Iterable[str]] | None = None,
    comprobaciones: Iterable[ComprobacionNodo] = (),
    sin_comprobar: Iterable[tuple[str, str, str]] = (),
    leidos: bool = True,
) -> InfoHardwareCluster:
    """``InfoHardwareCluster``; ``cpus`` = ``{nodo: nombres}`` (``custom-*`` = personalizado)."""
    return InfoHardwareCluster(
        mapeos=tuple(mapeos) if leidos else None,
        comprobaciones=tuple(comprobaciones),
        errores_comprobacion=tuple(sin_comprobar),
        cpus={
            n: tuple(ModeloCpu(c, c.startswith("custom-")) for c in nombres)
            for n, nombres in (cpus or {}).items()
        },
    )


def pci(mapeo_: str, **kw: bool) -> AsignacionPCI:
    return AsignacionPCI(mapeo_, **kw)


def usb(mapeo_: str, **kw: bool) -> AsignacionUSB:
    return AsignacionUSB(mapeo_, **kw)


def hw(*dispositivos: AsignacionPCI | AsignacionUSB) -> HardwareCluster:
    return HardwareCluster(
        pci=tuple(d for d in dispositivos if isinstance(d, AsignacionPCI)),
        usb=tuple(d for d in dispositivos if isinstance(d, AsignacionUSB)),
    )


def con_hardware(cfg: ConfiguracionVM, *dispositivos: AsignacionPCI | AsignacionUSB, **kw: Any):
    return dataclasses.replace(cfg, hardware_cluster=hw(*dispositivos), **kw)


def cfg_arm(**cambios: Any) -> ConfiguracionVM:
    """Configuración válida (disco ``local-lvm``) sobre ``inv_arq``: vmid 100, nodo pve1."""
    base: dict[str, Any] = {
        "vmid": 100,
        "nombre": "srv-arm-01",
        "nodo": "pve1",
        "discos": [Disco("local-lvm", 32)],
        "redes": [InterfazRed("vmbr0")],
    }
    base.update(cambios)
    return dataclasses.replace(cfg_vm(), **base)


class MundoD(MundoB):
    """``MundoB`` (clon con plantilla 9000 «base») con config de plantilla y versión elegibles.

    ``extra``: claves de la config de la plantilla (``hostpci0``, ``machine``, ``arch``...);
    ``arqs``: ``{nodo: ArquitecturaNodo}`` del inventario; ``hardware``: lo leído de mapeos y CPU.
    """

    def __init__(
        self,
        *,
        extra: dict[str, Any] | None = None,
        arqs: Mapping[str, ArquitecturaNodo] | None = None,
        hardware: InfoHardwareCluster | None = None,
        **kw: Any,
    ) -> None:
        kw.setdefault("plantillas", {9000: ("base", config_plantilla(**(extra or {})))})
        super().__init__(**kw)
        if arqs is not None:
            self.inv.arquitecturas = dict(arqs)
        if hardware is not None and self.inv.catalogo is not None:
            self.inv.catalogo = dataclasses.replace(self.inv.catalogo, hardware=hardware)
        self.banco.inv = self.inv
