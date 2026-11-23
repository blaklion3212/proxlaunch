"""Apoyo de las pruebas de C3 (firewall con grupo de seguridad, 0.8.0). Solo dobles y
constructores; sin aserciones.

``ClusterC`` es un ``ClusterA`` que además entiende las rutas de firewall (grupos del clúster,
opciones del centro de datos y opciones y reglas de cada MV y plantilla) y copia el firewall de la
plantilla al clonar, como hace Proxmox. ``MundoC`` es un ``MundoB`` sobre ese clúster con
constructores del firewall y del catálogo de «Comprobar». Los límites que se simulan son la red,
el reloj y el servidor; todo lo demás es código real.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.lectura import leer_info_firewall
from proxlaunch.nucleo.firewall.modelos import FirewallMV, ModoDhcp, Politica
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor

from . import apoyo_fase_b_p1 as p1
from .apoyo_fase_a import ClusterA
from .apoyo_fase_b_p1 import MundoB
from .apoyo_lote import NORMAL, Llamada, error_http

_RE_FW_VM = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/firewall/(?P<q>options|rules)$")
_RE_GRUPO_RUTA = re.compile(r"^/cluster/firewall/groups/(?P<g>[^/]+)$")

GRUPO = "web"
CENTINELA_NOTA = "NOTA-PRIVADA-123"


def fw(grupo: str | None = GRUPO, **kw: Any) -> FirewallMV:
    """Firewall activo con las políticas por defecto (entrada Bloquear, salida Permitir)."""
    return FirewallMV(activo=True, grupo=grupo, **kw)


class ClusterC(ClusterA):
    """``ClusterA`` con las rutas de firewall de la fase C.

    ``grupos``: ``{nombre: [reglas]}`` (cada regla un dict ``type/action/enable``).
    ``general``: opciones de ``/cluster/firewall/options`` (o una excepción que se lanza).
    ``fw_opciones`` y ``fw_reglas``: por VMID (plantillas y clones).
    """

    def __init__(self, nodos: tuple[str, ...] = ("pve1",)) -> None:
        super().__init__(nodos)
        self.grupos: dict[str, list[dict[str, Any]]] = {
            GRUPO: [{"type": "in", "action": "ACCEPT", "enable": 1}]
        }
        self.comentarios_grupo: dict[str, str] = {}
        self.general: Any = {"enable": 1}
        self.grupos_fallo: BaseException | None = None
        self.fw_opciones: dict[int, dict[str, Any]] = {}
        self.fw_reglas: dict[int, list[dict[str, Any]]] = {}

    # --- Consultas -------------------------------------------------------------------------

    def escrituras_fw(self) -> list[tuple[str, str]]:
        return [
            (c.metodo, c.ruta)
            for c in self.llamadas
            if c.metodo != "GET" and "/firewall/" in c.ruta
        ]

    def escrituras_fuera_de_vm(self) -> list[tuple[str, str]]:
        """Escrituras a rutas del clúster o de SDN (RF-C0.8): debe ser siempre ``[]``."""
        return [
            (c.metodo, c.ruta)
            for c in self.llamadas
            if c.metodo != "GET" and re.match(r"^/(cluster/(firewall|sdn)|nodes/[^/]+/sdn)", c.ruta)
        ]

    def lecturas_fw(self, patron: str = "") -> list[Llamada]:
        return [
            c
            for c in self.llamadas
            if c.metodo == "GET" and re.search(r"firewall" + patron, c.ruta)
        ]

    # --- Rutas -----------------------------------------------------------------------------

    def _fase_b(self, ll: Llamada) -> Any:
        m, ruta = ll.metodo, ll.ruta
        if m == "GET" and ruta == "/cluster/firewall/groups":
            if self.grupos_fallo is not None:
                raise self.grupos_fallo
            return [{"group": g, "comment": self.comentarios_grupo.get(g, "")} for g in self.grupos]
        if m == "GET" and (mt := _RE_GRUPO_RUTA.match(ruta)):
            if mt["g"] not in self.grupos:
                raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "no such group")
            return [dict(r, pos=i) for i, r in enumerate(self.grupos[mt["g"]])]
        if m == "GET" and ruta == "/cluster/firewall/options":
            if isinstance(self.general, BaseException):
                raise self.general
            return dict(self.general)
        if mt := _RE_FW_VM.match(ruta):
            vmid = int(mt["v"])
            if mt["q"] == "options":
                if m == "GET":
                    return dict(self.fw_opciones.get(vmid, {}))
                if m == "PUT":
                    self.fw_opciones.setdefault(vmid, {}).update(ll.datos or {})
                    return None
            else:
                if m == "GET":
                    return [dict(r, pos=i) for i, r in enumerate(self.fw_reglas.get(vmid, []))]
                if m == "POST":
                    d = ll.datos or {}
                    if d.get("type") == "group" and d.get("action") not in self.grupos:
                        # Proxmox rechaza una regla de un grupo que no existe (400).
                        raise error_http(400, f"Security group '{d.get('action')}' does not exist")
                    self.fw_reglas.setdefault(vmid, []).append(dict(d))
                    return None
        return super()._fase_b(ll)

    def _clonar(self, ll, nodo_: str, plantilla: int):  # noqa: D102
        res = super()._clonar(ll, nodo_, plantilla)
        nuevo = int((ll.datos or {}).get("newid", 0))
        self.fw_opciones[nuevo] = dict(self.fw_opciones.get(plantilla, {}))
        self.fw_reglas[nuevo] = [dict(r) for r in self.fw_reglas.get(plantilla, [])]
        return res


def fallar_fw(
    cluster: ClusterC,
    metodo: str,
    que: str,
    respuesta: BaseException,
    *,
    vmid: int | None = None,
    veces: int | None = None,
):
    """El ``metodo`` de ``…/firewall/<que>`` (``options`` o ``rules``) falla con ``respuesta``
    (de una MV si se da ``vmid``; solo las primeras ``veces``)."""

    def accion(_: Llamada) -> Any:
        raise respuesta

    id_ = r"\d+" if vmid is None else str(vmid)
    return cluster.regla(metodo, rf"/qemu/{id_}/firewall/{que}$", accion, veces)


def perder_respuesta_regla(cluster: ClusterC, vmid: int, error: BaseException) -> None:
    """El primer ``POST …/firewall/rules`` de la MV SÍ llega al servidor (la regla se crea) pero
    la respuesta se pierde (``error``): el cliente no sabe que se aplicó (CA-C3.8.3)."""
    estado = {"hecho": False}

    def accion(ll: Llamada) -> Any:
        if estado["hecho"]:
            return NORMAL
        estado["hecho"] = True
        cluster.fw_reglas.setdefault(vmid, []).append(dict(ll.datos or {}))
        raise error

    cluster.regla("POST", rf"/qemu/{vmid}/firewall/rules$", accion)


class MundoC(MundoB):
    """``MundoB`` sobre un ``ClusterC``, con el catálogo de «Comprobar» (``info_firewall``)."""

    def __init__(self, **kw: Any) -> None:
        original = p1.ClusterA
        p1.ClusterA = ClusterC  # type: ignore[misc]
        try:
            super().__init__(**kw)
        finally:
            p1.ClusterA = original  # type: ignore[misc]
        assert isinstance(self.cl, ClusterC)
        self.cl: ClusterC

    def leer_firewall(self, *, grupos: tuple[str, ...] = (GRUPO,), plantillas: bool = True) -> None:
        """Hace las lecturas reales de «Comprobar» contra el clúster simulado y las guarda en el
        catálogo del inventario (como lo haría el planificador)."""
        cliente = self.sesion.cliente
        cat = self.inv.catalogo
        assert cat is not None
        info = leer_info_firewall(
            cliente, cat.permisos, grupos, list(cat.plantillas or ()) if plantillas else []
        )
        self.inv = dataclasses.replace(self.inv, catalogo=dataclasses.replace(cat, firewall=info))
        self.banco.inv = self.inv


_CLAVES_CI = frozenset(
    {"ciuser", "sshkeys", "nameserver", "searchdomain", "ciupgrade", "cicustom", "agent"}
)


def secuencia(cl: ClusterC, vmid: int = 100) -> list[str]:
    """Etiqueta de cada petición que toca la MV ``vmid`` (sin sondeo de tareas), en orden:
    ``clone``, ``leer_config``, ``ajustes``, ``red``, ``ci``, ``pw``, ``fw_opciones``,
    ``fw_leer_reglas``, ``fw_regla``, ``resize``, ``start``, ``delete``."""
    sal: list[str] = []
    for c in cl.llamadas:
        d = c.datos or {}
        if c.metodo == "POST" and c.ruta.endswith("/clone"):
            if d.get("newid") == str(vmid):
                sal.append("clone")
            continue
        if f"/qemu/{vmid}/" not in c.ruta + "/" or "/tasks/" in c.ruta:
            if c.metodo == "POST" and c.ruta.endswith("/qemu") and d.get("vmid") == str(vmid):
                sal.append("crear")
            continue
        if c.metodo == "GET" and c.ruta.endswith("/config"):
            sal.append("leer_config")
        elif c.metodo == "GET" and c.ruta.endswith("/firewall/rules"):
            sal.append("fw_leer_reglas")
        elif c.metodo == "GET" and c.ruta.endswith("/firewall/options"):
            sal.append("fw_leer_opciones")
        elif c.metodo == "PUT" and c.ruta.endswith("/config"):
            if "cipassword" in d:
                sal.append("pw")
            elif any(k.startswith("net") for k in d):
                sal.append("red")
            elif set(d) & _CLAVES_CI or any(k.startswith("ipconfig") for k in d):
                sal.append("ci")
            else:
                sal.append("ajustes")
        elif c.metodo == "PUT" and c.ruta.endswith("/firewall/options"):
            sal.append("fw_opciones")
        elif c.metodo == "POST" and c.ruta.endswith("/firewall/rules"):
            sal.append("fw_regla")
        elif c.metodo == "PUT" and c.ruta.endswith("/resize"):
            sal.append("resize")
        elif c.metodo == "POST" and c.ruta.endswith("/status/start"):
            sal.append("start")
        elif c.metodo == "DELETE":
            sal.append("delete")
        else:
            sal.append(f"{c.metodo} {c.ruta}")
    return sal


def fw_defecto() -> FirewallMV:
    return FirewallMV()


__all__ = [
    "CENTINELA_NOTA",
    "GRUPO",
    "NORMAL",
    "CatalogoServidor",
    "ClusterC",
    "FirewallMV",
    "ModoDhcp",
    "MundoC",
    "Politica",
    "fallar_fw",
    "fw",
    "fw_defecto",
    "secuencia",
]
