"""Apoyo de las pruebas de interfaz de la fase A (0.6.0). Sin aserciones.

Solo piezas de los límites del sistema: permisos y estados de opciones construidos con el núcleo
público, un cliente falso de Proxmox con ``stop`` y ``PUT config`` para Deshacer, y ayudas para
leer lo que la interfaz muestra. Nunca hay red real ni diálogos modales.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtWidgets import QLabel, QWidget

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor, PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Inventario, Version
from proxlaunch.nucleo.opciones.disponibilidad import disponibilidad_opciones
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, EstadoPools, OpcionA, PoolsServidor
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH

from .apoyo import ClienteLoteFalso

OPCIONALES = ("VM.PowerMgmt",)


def permisos_fase_a(
    *, quitar: Iterable[str] = (), anadir: Iterable[str] = ("VM.PowerMgmt",)
) -> PermisosEfectivos:
    """Permisos del rol (14) más ``anadir``, sin ``quitar``, concedidos en «/» con herencia."""
    quitados = set(quitar)
    privilegios = [p for p in (*ROL_PROXLAUNCH, *anadir) if p not in quitados]
    return PermisosEfectivos(rutas={"/": dict.fromkeys(privilegios, 1)})


def caps_de(version: tuple[int, int] = (9, 2), forzada: bool = False):
    return capacidades_para(
        Version(f"{version[0]}.{version[1]}", version[0], version[1], 0),
        version if forzada else None,
    )


def estados_opciones(
    permisos: PermisosEfectivos | None = None,
    pools: PoolsServidor | None = None,
    *,
    version: tuple[int, int] = (9, 2),
    forzada: bool = False,
) -> dict[OpcionA, EstadoOpcion]:
    """Estados de las opciones con la función pura del núcleo (la que usa la ventana)."""
    return disponibilidad_opciones(
        permisos if permisos is not None else permisos_fase_a(),
        caps_de(version, forzada),
        pools if pools is not None else PoolsServidor(EstadoPools.OK, ("produccion", "pruebas")),
    )


def inventario_con(
    inv: Inventario,
    permisos: PermisosEfectivos | None,
    pools: PoolsServidor | None = None,
) -> Inventario:
    """Copia del inventario con un catálogo de solo permisos y pools (lo que lee la ventana)."""
    from dataclasses import replace

    previo = inv.catalogo or CatalogoServidor()
    catalogo = replace(
        previo,
        permisos=permisos,
        pools=pools if pools is not None else PoolsServidor(EstadoPools.OK, ("produccion",)),
    )
    inv2 = replace(inv)
    inv2.catalogo = catalogo
    return inv2


def textos_de(raiz: QWidget) -> str:
    """Texto de las etiquetas visibles bajo ``raiz`` (avisos y explicaciones de una fila)."""
    return "\n".join(
        lbl.text() for lbl in raiz.findChildren(QLabel) if lbl.isVisibleTo(raiz) and lbl.text()
    )


def explicacion(control: QWidget) -> str:
    """Descripción accesible del control (la explicación de por qué está deshabilitado)."""
    return control.accessibleDescription()


def orden_visual(controles: Iterable[QWidget], raiz: QWidget) -> list[QWidget]:
    """Controles visibles de ``raiz`` ordenados como se ven (arriba abajo, izquierda derecha)."""
    visibles = [c for c in controles if c.isVisibleTo(raiz)]
    return sorted(
        visibles,
        key=lambda c: (
            c.mapTo(raiz, c.rect().topLeft()).y(),
            c.mapTo(raiz, c.rect().topLeft()).x(),
        ),
    )


def cadena_de_foco(inicio: QWidget, longitud: int = 400) -> list[QWidget]:
    """Widgets en el orden en que la tecla Tab los recorre a partir de ``inicio``."""
    cadena: list[QWidget] = []
    w = inicio
    for _ in range(longitud):
        cadena.append(w)
        w = w.nextInFocusChain()
        if w is inicio:
            break
    return cadena


class ClienteDeshacerFalso(ClienteLoteFalso):
    """``ClienteLoteFalso`` con apagado y ``PUT config`` (Deshacer forzado de la fase A).

    Anota cada escritura en ``escrituras`` en el orden en que llega. ``protegidas`` lista los
    VMID con ``protection=1`` (se lee en ``config_vm``) y ``encendidas`` los que están ``running``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.escrituras: list[tuple[Any, ...]] = []
        self.detenidas: list[int] = []
        self.desprotegidas: list[int] = []

    def marcar(self, vmid: int, *, encendida: bool = False, protegida: bool = False) -> None:
        if encendida:
            self.estados_vm[vmid] = {"status": "running"}
        if protegida:
            config = dict(self.configs.get(vmid) or {})
            config["protection"] = 1
            self.configs[vmid] = config

    def detener_vm(self, nodo: str, vmid: int) -> str:
        self._anotar("detener_vm", nodo, vmid)
        self.escrituras.append(("stop", vmid))
        self.detenidas.append(vmid)
        self.estados_vm[vmid] = {"status": "stopped"}
        return f"UPID:{nodo}:0003A1B2:00F4C1D3:6535AB12:qmstop:{vmid}:root@pam:"

    def configurar_vm(self, nodo: str, vmid: int, parametros: dict[str, str]) -> str | None:
        self._anotar("configurar_vm", nodo, vmid, dict(parametros))
        self.escrituras.append(("config", vmid, dict(parametros)))
        if parametros.get("protection") == "0":
            self.desprotegidas.append(vmid)
            config = dict(self.configs.get(vmid) or {})
            config["protection"] = 0
            self.configs[vmid] = config
        return None

    def eliminar_vm(self, nodo: str, vmid: int) -> str:
        self.escrituras.append(("delete", vmid))
        return super().eliminar_vm(nodo, vmid)


# --- Ventana: lote creado y listo para Deshacer ---


def lote_creado(
    qtbot,
    entorno,
    cliente: ClienteDeshacerFalso,
    *,
    cantidad: int = 3,
    encendidas: tuple[int, ...] = (),
    protegidas: tuple[int, ...] = (),
):
    """Crea un lote con el servicio falso y deja el cliente como lo vería Proxmox después.

    Las MVs quedan con la etiqueta del lote (propias) y, según se pida, ``running`` o con
    ``protection=1``. Devuelve la ventana con el lote terminado.
    """
    from .apoyo_ventana_lote import crear_lote, esperar_fin, preparar_lote, ver_resumen

    preparar_lote(qtbot, entorno, cantidad=cantidad, cliente=cliente)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    id_lote = v.resumen_lote.plan.id_lote
    for i in range(cantidad):
        cliente.configs[101 + i] = {
            "name": f"web-{i + 1:02d}",
            "tags": f"proxlaunch;lote-{id_lote}",
        }
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    for vmid in encendidas:
        cliente.marcar(vmid, encendida=True)
    for vmid in protegidas:
        cliente.marcar(vmid, protegida=True)
    return v


def abrir_confirmacion_forzada(qtbot, v):
    """Pulsa Deshacer, elige todas las máquinas y espera el diálogo de confirmación expresa."""
    from proxlaunch.interfaz.dialogos.confirmar_deshacer import DialogoConfirmarDeshacerForzado
    from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer

    v._deshacer()
    d = v.findChildren(DialogoDeshacer)[0]
    d.boton_eliminar.click()
    qtbot.waitUntil(lambda: bool(v.findChildren(DialogoConfirmarDeshacerForzado)), timeout=4000)
    return v.findChildren(DialogoConfirmarDeshacerForzado)[0]
