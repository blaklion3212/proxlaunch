"""Apoyo para las pruebas de aceptación de la fase A (0.6.0). Sin aserciones.

Contiene un reloj de calendario fijo, un clúster simulado (``ClusterA``) que además entiende
``POST …/status/start``, ``GET /pools`` y ``GET /cluster/options``, y constructores de catálogos,
permisos, inventarios y definiciones de lote con las opciones de la fase A. Los límites que se
simulan son la red, el reloj y el servidor; todo lo demás es código real del núcleo.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC, datetime
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, FilaLote
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor, PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.opciones.modelos import (
    EstadoPools,
    OpcionesLote,
    OpcionesParciales,
    PoliticaEtiquetas,
    PoolsServidor,
)
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH

from .apoyo_lote import (
    Banco,
    RelojSeguro,
    TransporteCluster,
    definicion,
    inventario,
    nodo,
    plantilla,
    upid_de,
)
from .apoyo_mvp4 import ClusterM4

FECHA_FIJA = datetime(2026, 11, 21, 10, 30, 15, tzinfo=UTC)
FECHA_FIJA_ISO = "2026-11-21T10:30:15+00:00"
VERSION_APP_PRUEBAS = "0.6.0"
ID_LOTE = "abcd1234"

ROL_BASE: tuple[str, ...] = ROL_PROXLAUNCH
ROL_COMPLETO: tuple[str, ...] = (*ROL_PROXLAUNCH, "VM.PowerMgmt", "Pool.Audit")


class RelojCalendarioFijo:
    """``RelojCalendario`` determinista: siempre devuelve la misma fecha."""

    def __init__(self, fecha: datetime = FECHA_FIJA) -> None:
        self._fecha = fecha

    def ahora(self) -> datetime:
        return self._fecha


def permisos(
    privilegios: tuple[str, ...] = ROL_BASE,
    *,
    quitar: tuple[str, ...] = (),
    extra: dict[str, dict[str, int]] | None = None,
) -> PermisosEfectivos:
    """Permisos ``{"/": {p: 1}}`` (con propagate) más las rutas de ``extra``."""
    rutas: dict[str, dict[str, int]] = {"/": {p: 1 for p in privilegios if p not in quitar}}
    rutas.update(extra or {})
    return PermisosEfectivos(rutas=rutas)


def permisos_en_vms(privilegios: tuple[str, ...], propagate: int = 1) -> PermisosEfectivos:
    """Permisos concedidos solo en ``/vms`` (con o sin propagate)."""
    return PermisosEfectivos(rutas={"/vms": {p: propagate for p in privilegios}})


def catalogo(
    *,
    perm: PermisosEfectivos | None | bool = True,
    pools: PoolsServidor | None = None,
    politica: PoliticaEtiquetas | None = None,
    politica_fallida: bool = False,
    **kw: Any,
) -> CatalogoServidor:
    """Catálogo con permisos del rol completo (``True``), desconocidos (``None``) o dados."""
    efectivos = permisos(ROL_COMPLETO) if perm is True else (perm or None)
    return CatalogoServidor(
        permisos=efectivos,
        pools=pools if pools is not None else PoolsServidor(EstadoPools.NO_LEIDO),
        politica_etiquetas=politica,
        politica_etiquetas_fallida=politica_fallida,
        **kw,
    )


def inv_con(cat: CatalogoServidor | None, **kw: Any) -> Inventario:
    """Inventario de ``apoyo_lote`` (storage ``datos``, bridge ``vmbr0``) con ese catálogo."""
    return dataclasses.replace(inventario(**kw), catalogo=cat)


def cfg_vm(**cambios: Any) -> ConfiguracionVM:
    """Configuración válida sobre ``inventario()``: vmid 100, nodo pve1, storage ``datos``."""
    return dataclasses.replace(plantilla(vmid=100, nombre="srv-web-01", nodo="pve1"), **cambios)


def ctx_notas(**cambios: Any) -> Any:
    from proxlaunch.nucleo.opciones.modelos import ContextoNotas

    base: dict[str, Any] = {
        "version_app": VERSION_APP_PRUEBAS,
        "fecha": FECHA_FIJA,
        "id_lote": ID_LOTE,
        "perfil": None,
        "usuario": None,
    }
    base.update(cambios)
    return ContextoNotas(**base)


def codigos(problemas: Any) -> list[str]:
    """Códigos de los problemas (de M1 o del lote)."""
    return [str(getattr(p, "codigo", None) or getattr(p, "regla", "")) for p in problemas]


# --- Clúster simulado con encendido, pools y opciones del centro de datos ------------------------

_RE_START = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/status/start$")
_RE_UPID_A = re.compile(r"UPID:[^:]+:[^:]+:[^:]+:[^:]+:(?P<t>qmstart|qmstop):(?P<v>\d+):")


class ClusterA(ClusterM4):
    """``ClusterM4`` con ``status/start``, ``GET /pools`` y ``GET /cluster/options``.

    ``pools``: lista de ids visibles (una excepción se lanza). ``opciones``: cuerpo de
    ``/cluster/options`` (una excepción se lanza). ``exitstatus_inicio``: ``{vmid: exitstatus}`` de
    la tarea ``qmstart``. ``inicios``: contador de ``status/start`` por VMID.
    """

    def __init__(self, nodos: tuple[str, ...] = ("pve1",)) -> None:
        super().__init__(nodos)
        self.pools: list[str] | BaseException = []
        self.opciones: Any = {}
        self.exitstatus_inicio: dict[int, str] = {}
        self.inicios: dict[int, int] = {}

    # Escrituras en orden de llegada (todo lo que no es GET), como (método, ruta, datos).
    @property
    def escrituras(self) -> list[tuple[str, str, dict[str, Any] | None]]:
        return [(c.metodo, c.ruta, c.datos) for c in self.llamadas if c.metodo != "GET"]

    def rutas_de_escritura(self) -> list[tuple[str, str]]:
        return [(m, r) for m, r, _ in self.escrituras]

    def _normal(self, ll):  # noqa: D102
        if ll.metodo == "GET" and ll.ruta == "/pools":
            if isinstance(self.pools, BaseException):
                raise self.pools
            return [{"poolid": p} for p in self.pools]
        if ll.metodo == "GET" and ll.ruta == "/cluster/options":
            if isinstance(self.opciones, BaseException):
                raise self.opciones
            return self.opciones
        if ll.metodo == "POST" and (mt := _RE_START.match(ll.ruta)):
            vmid = int(mt["v"])
            with self._cerrojo:
                vm = self.vms.get(vmid)
                if vm is None:
                    raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "no such VM")
                self.inicios[vmid] = self.inicios.get(vmid, 0) + 1
                if self.exitstatus_inicio.get(vmid, "OK") == "OK":
                    vm["status"] = "running"
            return upid_de(mt["n"], vmid, "qmstart")
        return super()._normal(ll)

    def _tarea(self, upid: str, que: str):  # noqa: D102
        mt = _RE_UPID_A.match(upid)
        if mt is None:
            return super()._tarea(upid, que)
        vmid = int(mt["v"])
        if que == "log":
            return [{"n": 1, "t": f"TASK log {vmid}"}]
        estado = self.exitstatus_inicio.get(vmid, "OK") if mt["t"] == "qmstart" else "OK"
        return {"status": "stopped", "exitstatus": estado}


@dataclasses.dataclass
class BancoA(Banco):
    """``Banco`` cuyo clúster es un ``ClusterA`` (con encendido, pools y opciones)."""

    cluster: ClusterA


def banco_a(
    nodos: tuple[str, ...] = ("pve1",),
    *,
    cluster: ClusterA | None = None,
    inv: Inventario | None = None,
) -> BancoA:
    """Banco (sesión real + motor) sobre un ``ClusterA``; ``banco.cluster`` es el clúster."""
    cl = cluster or ClusterA(nodos)
    from .apoyo_api import crear_sesion

    reloj = RelojSeguro()
    sesion = crear_sesion(TransporteCluster(cl), reloj=reloj)  # type: ignore[arg-type]
    return BancoA(cl, sesion, reloj, inv or inventario(tuple(nodo(n) for n in nodos)))


def planificador(banco: Banco, **kw: Any) -> Planificador:
    """Planificador con calendario fijo, versión de la app y id de lote deterministas."""
    kw.setdefault("generador_id", lambda: ID_LOTE)
    kw.setdefault("reloj_calendario", RelojCalendarioFijo())
    kw.setdefault("version_app", VERSION_APP_PRUEBAS)
    return Planificador(banco.sesion, banco.reloj, **kw)


def plan_de(banco: Banco, definicion_: DefinicionLote, **kw: Any) -> Any:
    """Planifica ``definicion_`` con el planificador determinista."""
    return planificador(banco).planificar(definicion_, banco.inv, **kw)


def def_lote(
    cantidad: int = 2,
    *,
    opciones: OpcionesLote | None = None,
    plantilla_vm: ConfiguracionVM | None = None,
    **kw: Any,
) -> DefinicionLote:
    return definicion(cantidad, plantilla_vm=plantilla_vm, opciones=opciones, **kw)


def fila_a(nombre: str, *, opciones: OpcionesParciales | None = None, **cambios: Any) -> FilaLote:
    """Fila de lote por filas sobre ``inventario()`` (hardware de ``plantilla()``)."""
    return FilaLote(nombre, cfg_vm(**cambios), opciones=opciones)


def def_filas(filas: list[FilaLote], **kw: Any) -> DefinicionLote:
    from .apoyo_mvp3 import definicion_filas

    return definicion_filas(filas, **kw)
