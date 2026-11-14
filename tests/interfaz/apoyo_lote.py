"""Constructores para las pruebas de interfaz del lote (planes, entradas del libro, doubles).

Solo arma datos y dobles de los límites del sistema: no contiene aserciones.
"""

from __future__ import annotations

import threading
from typing import Any

from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    DefinicionLote,
    Destino,
    ElementoPlan,
    EntradaLibro,
    EstadoMV,
    InformeLote,
    MetadatosInforme,
    ModoDestino,
    PatronNombres,
    Plan,
)
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo import ClienteLoteFalso, sesion_falsa, upid_de


def cfg_simple(
    vmid: int = 0, nombre: str = "x", nodo: str = "pve1", gib: int = 10, **cambios: Any
) -> ConfiguracionVM:
    """Plantilla mínima válida sobre ``inventario_cluster`` (disco en local-lvm, red vmbr0)."""
    base: dict[str, Any] = {
        "vmid": vmid,
        "nombre": nombre,
        "nodo": nodo,
        "discos": [Disco("local-lvm", gib)],
        "redes": [InterfazRed("vmbr0")],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def definicion(
    cantidad: int = 3,
    prefijo: str = "web",
    *,
    plantilla: ConfiguracionVM | None = None,
    destino: Destino | None = None,
    **cambios: Any,
) -> DefinicionLote:
    return DefinicionLote(
        plantilla=plantilla or cfg_simple(),
        cantidad=cantidad,
        patron=PatronNombres(prefijo=prefijo),
        destino=destino or Destino(ModoDestino.UN_NODO, ("pve1",)),
        **cambios,
    )


def planificar(
    inv, defn: DefinicionLote, cliente: ClienteLoteFalso | None = None, reloj=None, **kw
) -> Plan:
    """Plan real con el Planificador del núcleo sobre un cliente falso (sin red)."""
    sesion = sesion_falsa(cliente=cliente or ClienteLoteFalso())
    return Planificador(sesion, reloj or RelojSimulado()).planificar(defn, inv, **kw)


def elemento(i: int, nombre: str | None = None, vmid: int | None = None, nodo: str = "pve1"):
    nombre = nombre or f"web-{i + 1:02d}"
    vmid = vmid if vmid is not None else 101 + i
    return ElementoPlan(i, nombre, vmid, nodo, cfg_simple(vmid, nombre, nodo))


def entrada(
    i: int,
    estado: EstadoMV,
    *,
    nombre: str | None = None,
    vmid: int | None = None,
    nodo: str = "pve1",
    upid: str | None = None,
    error: ErrorProxLaunch | None = None,
    **kw: Any,
) -> EntradaLibro:
    el = elemento(i, nombre, vmid, nodo)
    kw.setdefault("post_intentado", estado not in (EstadoMV.PENDIENTE, EstadoMV.NO_ENVIADA))
    return EntradaLibro(el, estado, upid=upid, error=error, **kw)


def entradas_de(estados: list[EstadoMV], **kw: Any) -> tuple[EntradaLibro, ...]:
    return tuple(entrada(i, e, **kw) for i, e in enumerate(estados))


def metadatos(perfil: str = "Laboratorio") -> MetadatosInforme:
    return MetadatosInforme(
        nombre_perfil=perfil,
        version_proxmox="9.2",
        es_cluster=True,
        nombre_cluster="lab",
        fecha_hora_local="2026-11-13T10:00:00-05:00",
    )


def informe_de(
    entradas: tuple[EntradaLibro, ...],
    *,
    perfil: str = "Laboratorio",
    simulacion: bool = False,
    id_lote: str = "ab12cd34",
    rollback=(),
    problemas=(),
) -> InformeLote:
    contadores = {e.value: 0 for e in EstadoMV}
    for e in entradas:
        contadores[e.estado.value] += 1
    return InformeLote(
        metadatos=metadatos(perfil),
        id_lote=id_lote,
        es_simulacion=simulacion,
        pedidas=len(entradas),
        contadores=contadores,
        entradas=entradas,
        duraciones_s={e.elemento.vmid: 12.0 for e in entradas if e.t_inicio is not None},
        plantilla=cfg_simple(),
        rollback=tuple(rollback),
        problemas_plan=tuple(problemas),
    )


def upid_con_usuario(vmid: int) -> str:
    return upid_de(vmid, "pve1", "ana@pve")


class RelojBloqueable(RelojSimulado):
    """Reloj simulado cuyo ``dormir`` puede quedarse retenido (sin dormir de verdad).

    Permite observar la espera de la reconciliación (+5 s, +15 s) de un envío incierto y
    cancelarla en ese instante. Con ``bloquear`` falso se comporta como ``RelojSimulado``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.bloquear = False
        self.dentro = threading.Event()
        self.liberar = threading.Event()
        self.dormidas: list[float] = []

    def dormir(self, segundos: float) -> None:
        self.dormidas.append(segundos)
        if self.bloquear:
            self.dentro.set()
            self.liberar.wait(5)
        super().dormir(segundos)


def res_perdida(vmid: int, *, incierto: bool = False, nodo: str = "pve1"):
    """Resultado de creación «conexión perdida»: con UPID, o sin él si ``incierto`` (596/597)."""
    from proxlaunch.nucleo.errores import CodigoError
    from proxlaunch.nucleo.modelos.tarea import Desenlace

    from .apoyo import resultado

    params = {"incierto": "1"} if incierto else {}
    error = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, params, "ReadTimeout")
    return resultado(
        Desenlace.CONEXION_PERDIDA,
        error=error,
        upid=None if incierto else upid_de(vmid),
        vmid=vmid,
        nodo=nodo,
    )


def res_error(
    vmid: int,
    codigo,
    *,
    con_upid: bool = True,
    nodo: str = "pve1",
    detalle: str = "texto original",
    **params: str,
):
    """Resultado de creación con error (la tarea falló, o el envío fue rechazado sin UPID)."""
    from proxlaunch.nucleo.modelos.tarea import Desenlace

    from .apoyo import resultado

    error = ErrorProxLaunch(codigo, dict(params), detalle)
    return resultado(
        Desenlace.ERROR,
        error=error,
        upid=upid_de(vmid) if con_upid else None,
        vmid=vmid,
        nodo=nodo,
    )
