"""Apoyo de las pruebas del inventario de lotes (fase C, C1). Sin aserciones.

Amplía el ``Cluster`` de ``apoyo_lote`` con lo que el inventario necesita: ``/cluster/resources``
con etiquetas, estado, bloqueo y plantilla; filas de la lista distintas de la config (para
simular que algo cambia entre la lista y el borrado); un medidor de concurrencia de las lecturas
``GET config``; y constructores de máquinas «de ProxLaunch» con su nota de origen.

Los límites que se simulan son solo la red y el servidor de Proxmox. Sin ``sleep`` reales: el
medidor de concurrencia espera con un ``Event`` y un plazo de milisegundos.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from proxlaunch.nucleo.inventario.agrupacion import agrupar_lotes
from proxlaunch.nucleo.inventario.modelos import DetalleLote, ListaLotes, LoteServidor
from proxlaunch.nucleo.inventario.servicio import ServicioInventario
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos

from .apoyo_lote import Banco, Cluster, crear_banco, crear_banco_http

CODIGO = "ab12cd34"
OTRO_CODIGO = "ffffffff"
FECHA_BASE = "2026-11-20T10:00:00+00:00"
_RE_CONFIG_RUTA = re.compile(r"^/nodes/(?P<n>[^/]+)/qemu/(?P<v>\d+)/config$")


def nota_origen(
    codigo: str | None = CODIGO, fecha: str | None = FECHA_BASE, extra: str = ""
) -> str:
    """Nota ``description`` como la escribe ProxLaunch (``opciones/notas.py``)."""
    lineas = ["Creada con ProxLaunch 0.8.0", ""]
    if fecha is not None:
        lineas.append(f"- Fecha: {fecha}")
    if codigo is not None:
        lineas.append(f"- Lote: {codigo}")
    lineas.append("- Perfil: lab")
    texto = "\n".join(lineas)
    return f"{texto}\n\n{extra}" if extra else texto


def etiquetas_lote(codigo: str = CODIGO) -> str:
    return f"{ETIQUETA_APP};{PREFIJO_ETIQUETA_LOTE}{codigo}"


class ClusterInventario(Cluster):
    """``Cluster`` con la lista del inventario y un medidor de concurrencia de ``GET config``."""

    def __init__(self, nodos: tuple[str, ...] = ("pve1",)) -> None:
        super().__init__(nodos)
        # Campos de la FILA DE LA LISTA que difieren de la config (vmid -> campos).
        self.fila_lista: dict[int, dict[str, Any]] = {}
        self.ocultas_en_lista: set[int] = set()  # sin ``VM.Audit``: no salen en la lista
        self.lista_cruda: list[Any] | None = None  # sustituye por completo a la lista
        self.lecturas_config: list[tuple[str, int]] = []  # (nodo, vmid) de cada GET config
        self.consultas_lista = 0
        # Medidor de concurrencia de las lecturas de config.
        self.medir = False
        self._activas_cfg = 0
        self.max_lecturas_config = 0
        self._juntas = threading.Event()
        self.retardo_s = 0.01

    # --- Escenarios ----------------------------------------------------------------------

    def agregar_mv(
        self,
        vmid: int,
        nombre: str | None = None,
        *,
        nodo: str = "pve1",
        lote: str | None = CODIGO,
        etiquetas: str | None = None,
        nota: str | None | bool = True,
        status: str = "stopped",
        **config: Any,
    ) -> None:
        """MV de ProxLaunch por defecto: etiquetas ``proxlaunch;lote-<lote>`` y nota coincidente.

        ``etiquetas`` sustituye al valor por defecto; ``nota`` ``True`` = nota de ``lote``,
        ``False``/``None`` = sin nota, ``str`` = texto exacto.
        """
        cfg: dict[str, Any] = dict(config)
        cfg["name"] = nombre if nombre is not None else f"web-{vmid}"
        if etiquetas is not None:
            cfg["tags"] = etiquetas
        elif lote is not None:
            cfg["tags"] = etiquetas_lote(lote)
        if nota is True:
            cfg["description"] = nota_origen(lote)
        elif isinstance(nota, str):
            cfg["description"] = nota
        self.vms[vmid] = {"nodo": nodo, "config": {"digest": "d", **cfg}, "status": status}

    # --- Lista ---------------------------------------------------------------------------

    def _fila(self, vmid: int, d: dict[str, Any]) -> dict[str, Any]:
        cfg = d["config"]
        fila: dict[str, Any] = {
            "vmid": vmid,
            "node": d["nodo"],
            "type": "qemu",
            "status": d["status"],
        }
        for campo_lista, campo_cfg in (
            ("name", "name"),
            ("tags", "tags"),
            ("lock", "lock"),
            ("template", "template"),
        ):
            if campo_cfg in cfg:
                fila[campo_lista] = cfg[campo_cfg]
        fila.update(self.fila_lista.get(vmid, {}))
        return fila

    def _get(self, ll: Any, ruta: str) -> Any:
        if ruta == "/cluster/resources":
            with self._cerrojo:
                self.consultas_lista += 1
            if self.lista_cruda is not None:
                return list(self.lista_cruda)
            filas = [
                self._fila(v, d) for v, d in self.vms.items() if v not in self.ocultas_en_lista
            ]
            return filas + list(self.visibles_extra)
        mt = _RE_CONFIG_RUTA.match(ruta)
        if mt is None:
            return super()._get(ll, ruta)
        with self._cerrojo:
            self.lecturas_config.append((mt["n"], int(mt["v"])))
            self._activas_cfg += 1
            self.max_lecturas_config = max(self.max_lecturas_config, self._activas_cfg)
            if self._activas_cfg >= 5:
                self._juntas.set()
        try:
            if self.medir:
                # Deja que otras lecturas se solapen sin dormir: espera un evento con plazo.
                self._juntas.wait(self.retardo_s)
            return super()._get(ll, ruta)
        finally:
            with self._cerrojo:
                self._activas_cfg -= 1

    # --- Resumen para las aserciones -------------------------------------------------------

    def rutas(self, metodo: str) -> list[str]:
        return [c.ruta for c in self.llamadas if c.metodo == metodo.upper()]

    @property
    def escrituras(self) -> list[tuple[str, str]]:
        """Toda petición distinta de GET/HEAD como ``(método, ruta)``."""
        return [(c.metodo, c.ruta) for c in self.llamadas if c.metodo not in ("GET", "HEAD")]


class Mundo:
    """Clúster + sesión real + servicio del inventario (todo en memoria)."""

    def __init__(self, nodos: tuple[str, ...] = ("pve1",), *, rsps: Any = None) -> None:
        """Con ``rsps`` (``responses``) la sesión usa el transporte HTTP real y su traductor."""
        self.cluster = ClusterInventario(nodos)
        self.banco: Banco = (
            crear_banco(nodos, cluster=self.cluster)
            if rsps is None
            else crear_banco_http(rsps, nodos, cluster=self.cluster)
        )
        self.sesion = self.banco.sesion
        self.reloj = self.banco.reloj
        self.servicio = ServicioInventario(self.sesion, self.reloj)

    def listar(self) -> ListaLotes:
        return self.servicio.listar()

    def lote(self, codigo: str = CODIGO) -> LoteServidor:
        return next(x for x in self.listar().lotes if x.codigo == codigo)

    def detallar(
        self, codigo: str = CODIGO, permisos: PermisosEfectivos | None = None
    ) -> DetalleLote:
        return self.servicio.detallar(self.lote(codigo), threading.Event(), permisos)


def lista_de(*recursos: Any) -> ListaLotes:
    return agrupar_lotes(list(recursos))


def permisos(rutas: dict[str, dict[str, int]]) -> PermisosEfectivos:
    return PermisosEfectivos(rutas)
