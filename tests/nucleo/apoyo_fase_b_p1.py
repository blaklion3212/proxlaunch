"""Apoyo de las pruebas P1 de la fase B (0.7.0): secretos, creación por clon, disponibilidad,
planificación y Deshacer. Solo dobles y constructores; sin aserciones.

Contiene el centinela de contraseña, las configuraciones de plantilla de ejemplo (con y sin unidad
cloud-init, Windows, ``cicustom`` heredado, varias ``netN``) y ``MundoB``: un clúster ``ClusterA``
con una plantilla (9000), la sesión real, el inventario con catálogo y el servicio de creación.
Los límites que se simulan son la red, el reloj y el servidor; todo lo demás es código real.
"""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Iterable
from typing import Any

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.cloudinit.modelos import (
    ConfigCloudInit,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import DefinicionLote, EstadoMV, Plan
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage, Version
from proxlaunch.nucleo.modelos.tarea import Etapa
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.servicios.creacion import ResultadoCreacion, ServicioCreacion

from .apoyo_api import crear_sesion
from .apoyo_fase_a import BancoA, ClusterA, def_lote, plan_de
from .apoyo_lote import (
    ControlAutomatico,
    RelojSeguro,
    TransporteCluster,
    inventario,
    nodo,
    storage,
)
from .apoyo_mvp4 import cfg_clon, inv_origen, plantilla_pve

CENTINELA = "S3cr3t-Prueba!"
# Clave pública válida (ed25519) para los ejemplos; el comentario es inocuo.
CLAVE = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl ana@lab"
CLAVE_2 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEzV3nwUEq5vnKsm5E8KXPuAlzpzGMh1C9tbxuIXmTQi eva@lab"

V_80 = Version("8.0.4", 8, 0, 4)
V_84 = Version("8.4.1", 8, 4, 1)
V_90 = Version("9.0.2", 9, 0, 2)
V_91 = Version("9.1.1", 9, 1, 1)
V_92 = Version("9.2.1", 9, 2, 1)

# Privilegios de la fase B (opcionales: no forman parte del rol de 14).
PRIVS_B_92: tuple[str, ...] = (
    *ROL_PROXLAUNCH,
    "VM.PowerMgmt",
    "Pool.Audit",
    "VM.Config.Cloudinit",
    "VM.GuestAgent.Audit",
    "Datastore.Audit",
)
PRIVS_B_8X: tuple[str, ...] = (
    *ROL_PROXLAUNCH,
    "VM.PowerMgmt",
    "Pool.Audit",
    "VM.Config.Cloudinit",
    "VM.Monitor",
    "Datastore.Audit",
    "Datastore.Allocate",
)


def permisos_en(privilegios: Iterable[str], ruta: str = "/") -> PermisosEfectivos:
    """Permisos efectivos con propagación en ``ruta``."""
    return PermisosEfectivos(rutas={ruta: dict.fromkeys(privilegios, 1)})


# --- Configuraciones de plantilla de ejemplo ----------------------------------------------------


def config_plantilla(
    *,
    unidad: str | None = "ide2",
    ostype: str = "l26",
    agente: str | None = None,
    redes: int = 1,
    cicustom: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """``config`` de una plantilla (sin ``name`` ni ``template``: los pone ``agregar_plantilla``).

    ``unidad`` es la clave del bus de la unidad cloud-init (``None`` = sin unidad).
    """
    config: dict[str, Any] = {
        "ostype": ostype,
        "cores": 2,
        "sockets": 1,
        "memory": 2048,
        "scsi0": "local-lvm:base-9000-disk-0,size=8G",
        "net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0",
    }
    for i in range(1, redes):
        config[f"net{i}"] = f"virtio=AA:BB:CC:DD:EE:{i:02X},bridge=vmbr0"
    if unidad is not None:
        config[unidad] = "local-lvm:vm-9000-cloudinit,media=cdrom"
    if agente is not None:
        config["agent"] = agente
    if cicustom is not None:
        config["cicustom"] = cicustom
    config.update(extra)
    return config


def ci(**cambios: Any) -> ConfigCloudInit:
    """``ConfigCloudInit`` de ejemplo: usuario, una clave y la tarjeta 0 por DHCP."""
    base: dict[str, Any] = {
        "usuario": "deploy",
        "claves": (CLAVE,),
        "tarjetas": (TarjetaCloudInit(0, ModoTarjeta.DHCP),),
    }
    base.update(cambios)
    return ConfigCloudInit(**base)


def ci_completa(contrasena: Secreto | None = None, *, serie: bool = False) -> ConfigCloudInit:
    """Cloud-init con todo lo que viaja en el ``PUT`` de cloud-init (``serie``: IP en serie,
    necesaria en un lote de más de una MV con IP fija: V-B38)."""
    return ConfigCloudInit(
        usuario="deploy",
        claves=(CLAVE, CLAVE_2),
        contrasena=contrasena,
        tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, "10.0.0.50/24", serie, "10.0.0.1"),),
        dns=("1.1.1.1", "9.9.9.9"),
        dominio="lab.local",
        actualizar=False,
        snippets=SnippetsCloudInit(vendor="snip:snippets/agente.yaml"),
        activar_agente=True,
    )


def con_ci(cfg: ConfiguracionVM, cloudinit: ConfigCloudInit | None, **cambios: Any):
    return dataclasses.replace(cfg, cloudinit=cloudinit, **cambios)


# --- Mundo de la fase B ---------------------------------------------------------------------------


class MundoB:
    """Clúster ``ClusterA`` con una plantilla, sesión real, inventario con catálogo y servicio.

    ``plantillas``: ``{vmid: (nombre, config)}`` (por defecto, 9000 «base» con unidad cloud-init).
    ``privilegios``: los concedidos en ``/`` (``None`` = permisos desconocidos). ``snippets``:
    ``{(nodo, storage): [(volid, tamaño)]}``; crea además el storage ``snip`` con contenido
    ``snippets`` en cada nodo (compartido si ``snip_compartido``).
    """

    def __init__(
        self,
        *,
        version: Version = V_92,
        privilegios: Iterable[str] | None = PRIVS_B_92,
        nodos: tuple[str, ...] = ("pve1",),
        plantillas: dict[int, tuple[str, dict[str, Any]]] | None = None,
        snippets: dict[tuple[str, str], list[tuple[str, int]]] | None = None,
        snip_compartido: bool = False,
        rsps: Any = None,
    ) -> None:
        self.version = version
        self.nodos = nodos
        self.cl = ClusterA(nodos)
        for vmid, (nombre, config) in (plantillas or {9000: ("base", config_plantilla())}).items():
            self.cl.agregar_plantilla(vmid, nombre, nodos[0], **config)
        # Por defecto el snippet «agente.yaml» existe en el storage ``snip`` de cada nodo.
        self.cl.snippets = (
            dict(snippets)
            if snippets is not None
            else {(n, "snip"): [("snip:snippets/agente.yaml", 1000)] for n in nodos}
        )
        if rsps is None:
            self.reloj = RelojSeguro()
            self.sesion = crear_sesion(
                TransporteCluster(self.cl),  # type: ignore[arg-type]
                reloj=self.reloj,
                version=version,
            )
        else:
            # Transporte HTTP real (``responses``): cuerpos en bruto y traductor de errores reales.
            from .apoyo_lote import crear_banco_http

            b = crear_banco_http(rsps, nodos, cluster=self.cl)
            self.reloj, self.sesion = b.reloj, b.sesion
            self.sesion.version = version
            self.sesion.capacidades = capacidades_para(version, None)
        pls = tuple(
            plantilla_pve(
                vmid,
                nombre,
                nodos[0],
                detalle=detalle_de_config(self.cl.plantillas[vmid]["config"]),
            )
            for vmid, (nombre, _) in (plantillas or {9000: ("base", {})}).items()
        )
        extra: dict[str, tuple[Storage, ...]] = {
            n: (storage("snip", "dir", 100, compartido=snip_compartido, contenido="snippets"),)
            for n in nodos
        }
        self.privilegios = None if privilegios is None else tuple(privilegios)
        self.inv: Inventario = inv_origen(
            version=version,
            nodos=nodos,
            privilegios=self.privilegios or (),
            permisos_efectivos=True if privilegios is not None else None,
            plantillas=pls,
            extra_storages=extra,
        )
        self.banco = BancoA(self.cl, self.sesion, self.reloj, self.inv)
        self.etapas: list[Etapa] = []

    # --- Servicio y configuración ----------------------------------------------------------------

    def servicio(self) -> ServicioCreacion:
        return ServicioCreacion(self.sesion, self.reloj, intervalo_s=0.01)

    def cfg(self, cloudinit: ConfigCloudInit | None = None, **kw: Any) -> ConfiguracionVM:
        """Configuración de clon de la plantilla «base» con ``vmid`` 100 en el primer nodo."""
        kw.setdefault("etiquetas", ("proxlaunch", "lote-ab12cd34"))
        cfg, problemas = resolver_origen(cfg_clon("base", **kw), self.inv, self.nodos[0])
        assert problemas == [], problemas
        return dataclasses.replace(cfg, cloudinit=cloudinit)

    @property
    def macs_libro(self) -> dict[int, str]:
        """Hace de libro: MAC original de cada tarjeta del clon (QA-C-M1), entre llamadas."""
        return self.__dict__.setdefault("_macs_libro", {})

    def crear(self, cfg: ConfiguracionVM) -> ResultadoCreacion:
        return self.servicio().crear(
            cfg,
            self.inv,
            self.etapas.append,
            threading.Event(),
            macs_originales=self.macs_libro,
            al_leer_macs=self.macs_libro.update,
        )

    def reintentar(
        self, cfg: ConfiguracionVM, pendientes: frozenset[str] | None = None
    ) -> ResultadoCreacion:
        return self.servicio().reintentar_ajustes(
            cfg,
            self.inv,
            threading.Event(),
            pendientes=pendientes,
            macs_originales=self.macs_libro,
            al_leer_macs=self.macs_libro.update,
        )

    # --- Lotes ---------------------------------------------------------------------------------

    def definicion(
        self, n: int = 3, cloudinit: ConfigCloudInit | None = None, **kw: Any
    ) -> DefinicionLote:
        base = dataclasses.replace(cfg_clon("base"), cloudinit=cloudinit, **kw)
        return def_lote(n, plantilla_vm=base)

    def planificar(self, definicion: DefinicionLote, **kw: Any) -> Plan:
        return plan_de(self.banco, definicion, **kw)

    def ejecutar(
        self,
        plan: Plan,
        control: ControlLote | None = None,
        *,
        espera_ip: Any = None,
        libro: Libro | None = None,
    ) -> Libro:
        return self.banco.motor().ejecutar(
            plan,
            self.inv,
            self.banco.observador,
            control or ControlAutomatico("suspender"),
            libro=libro,
            espera_ip=espera_ip,
        )

    def lote(self, n: int = 3, cloudinit: ConfigCloudInit | None = None, **kw: Any):
        """Planifica y ejecuta; devuelve ``(plan, libro)``."""
        plan = self.planificar(self.definicion(n, cloudinit, **kw))
        assert not plan.bloqueado, plan.problemas
        return plan, self.ejecutar(plan)

    # --- Consultas sobre lo recibido -----------------------------------------------------------

    def puts_config(self, vmid: int | None = None) -> list[dict[str, Any]]:
        """Cuerpos (diccionario) de los ``PUT …/config`` recibidos, en orden."""
        return [
            dict(c.datos or {})
            for c in self.cl.llamadas
            if c.metodo == "PUT"
            and c.ruta.endswith("/config")
            and (vmid is None or f"/qemu/{vmid}/" in c.ruta)
        ]

    def escrituras(self, vmid: int) -> list[str]:
        """Etiqueta de cada escritura sobre una MV, en orden de llegada."""
        sal: list[str] = []
        for c in self.cl.llamadas:
            es_clon = c.metodo == "POST" and c.ruta.endswith("/clone")
            if es_clon:
                if (c.datos or {}).get("newid") == str(vmid):
                    sal.append("clone")
                continue
            if c.metodo == "GET" or f"/qemu/{vmid}/" not in c.ruta + "/":
                continue
            if False:
                pass
            elif c.metodo == "PUT" and c.ruta.endswith("/config"):
                claves = set(c.datos or {})
                if "cipassword" in claves:
                    sal.append("pw")
                elif claves & {"ciuser", "sshkeys", "cicustom", "nameserver", "searchdomain",
                               "ciupgrade", "agent", "delete"} or any(
                    k.startswith("ipconfig") for k in claves
                ):  # fmt: skip
                    sal.append("ci")
                else:
                    sal.append("ajustes")
            elif c.metodo == "PUT" and c.ruta.endswith("/resize"):
                sal.append("resize")
            elif c.metodo == "POST" and c.ruta.endswith("/status/start"):
                sal.append("start")
            elif c.metodo == "POST" and c.ruta.endswith("/status/stop"):
                sal.append("stop")
            elif c.metodo == "DELETE":
                sal.append("delete")
            else:
                sal.append(f"{c.metodo} {c.ruta}")
        return sal

    def estados(self, libro: Libro) -> dict[int, EstadoMV]:
        return {e.elemento.vmid: e.estado for e in libro.instantanea()}


def inventario_con_nodos(*nombres: str) -> Inventario:
    """Inventario simple de lote (storage ``datos``) con esos nodos en línea."""
    return inventario(tuple(nodo(n) for n in nombres))


def storage_snippets(id_: str = "snip", *, compartido: bool = False) -> Storage:
    return storage(id_, "dir", 100, compartido=compartido, contenido="snippets")


# --- Inyección de fallos en el ``PUT config`` ----------------------------------------------------


def fallar_put(
    cluster: Any,
    clave: str,
    respuesta: Any,
    *,
    vmid: int | None = None,
    veces: int | None = None,
):
    """El ``PUT …/config`` cuyo cuerpo lleva ``clave`` responde ``respuesta`` (un ``Http`` o un
    ``ErrorProxLaunch``). ``vmid`` limita la regla a una MV; ``veces`` a los primeros disparos.
    """
    from .apoyo_lote import NORMAL

    contador = {"n": 0}
    cerrojo = threading.Lock()
    ruta = rf"/qemu/{vmid}/config$" if vmid is not None else r"/qemu/\d+/config$"

    def accion(ll: Any) -> Any:
        if clave not in (ll.datos or {}):
            return NORMAL
        with cerrojo:
            contador["n"] += 1
            if veces is not None and contador["n"] > veces:
                return NORMAL
        if isinstance(respuesta, BaseException):
            raise respuesta
        return respuesta

    return cluster.regla("PUT", ruta, accion)
