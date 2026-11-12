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
from proxlaunch.nucleo.errores import ErrorProxLaunch
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
) -> Sesion:
    """Sesión sin red: el cliente es un marcador (las pruebas no lo usan)."""
    v = Version(f"{version[0]}.{version[1]}", version[0], version[1], 0)
    return Sesion(
        perfil=perfil_ or perfil(),
        cliente=object(),  # type: ignore[arg-type]
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

    def crear(self, cfg, inv, al_cambiar_etapa: Callable, cancelado, *, al_enviar=None):
        self.llamadas_crear += 1
        for etapa in (Etapa.VALIDANDO, Etapa.ENVIANDO):
            al_cambiar_etapa(etapa)
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
