"""Apoyo de las pruebas de red de la fase C (0.8.0): VNets de SDN (C2) y reescritura de la red al
clonar (C4). Solo dobles y constructores; sin aserciones.

``ClusterC`` es un ``ClusterA`` que se parece más a Proxmox en lo que importa a C4: el clon recibe
MACs NUEVAS (distintas de las de la plantilla), el ``PUT config`` comprueba ``digest``, atiende
``delete=`` y genera otra MAC cuando un ``netN`` llega sin ella. Los límites que se simulan son la
red, el reloj y el servidor; todo lo demás es código real.
"""

from __future__ import annotations

import dataclasses
import threading
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Bridge, Inventario, RedVirtual
from proxlaunch.nucleo.red.modelos import (
    AccionTarjeta,
    CampoRed,
    ModoRedClon,
    RedClon,
    TarjetaClon,
)

from . import apoyo_fase_b_p1
from .apoyo_fase_a import ClusterA
from .apoyo_fase_b_p1 import PRIVS_B_92, V_92, MundoB, config_plantilla
from .apoyo_lote import Llamada

MAC_PLANTILLA_0 = "AA:BB:CC:DD:EE:FF"
MAC_PLANTILLA_1 = "AA:BB:CC:DD:EE:01"


def mac_clon(vmid: int, indice: int) -> str:
    """MAC que ``ClusterC`` da a ``netN`` del clon ``vmid`` (distinta de la de la plantilla)."""
    return f"BC:24:11:{vmid % 256:02X}:00:{indice:02X}"


def vnet(
    nombre: str, *, vlan_aware: bool = False, alias: str | None = None, tipo_declarado: bool = True
) -> RedVirtual:
    return RedVirtual(
        nombre=nombre, alias=alias, vlan_aware=vlan_aware, tipo_declarado=tipo_declarado
    )


def bridge(nombre: str, *, vlan_aware: bool = False, mtu: int | None = None) -> Bridge:
    return Bridge(nombre=nombre, tipo="bridge", vlan_aware=vlan_aware, mtu=mtu)


def con_redes(
    inv: Inventario,
    *,
    bridges: dict[str, tuple[Bridge, ...]] | None = None,
    vnets: dict[str, tuple[RedVirtual, ...]] | None = None,
    errores_sdn: dict[str, ErrorProxLaunch] | None = None,
    errores_red: dict[str, ErrorProxLaunch] | None = None,
) -> Inventario:
    """Copia del inventario con bridges, VNets y errores de lectura por nodo."""
    cambios: dict[str, Any] = {}
    if bridges is not None:
        cambios["bridges"] = dict(bridges)
    if vnets is not None:
        cambios["redes_sdn"] = dict(vnets)
    if errores_sdn is not None:
        cambios["errores_sdn"] = dict(errores_sdn)
    if errores_red is not None:
        cambios["errores_por_nodo"] = dict(errores_red)
    return dataclasses.replace(inv, **cambios)


def red_clon(*tarjetas: TarjetaClon) -> RedClon:
    return RedClon(ModoRedClon.PERSONALIZAR, tuple(tarjetas))


def cambiar(indice: int, *, mac_nueva: bool = False, **campos: Any) -> TarjetaClon:
    """``CAMBIAR`` de ``netN`` fijando los campos dados (``bridge``, ``vlan``, ``modelo``…)."""
    claves = {
        "bridge": CampoRed.BRIDGE,
        "modelo": CampoRed.MODELO,
        "vlan": CampoRed.VLAN,
        "mtu": CampoRed.MTU,
        "limite_mb": CampoRed.LIMITE,
    }
    return TarjetaClon(
        indice,
        AccionTarjeta.CAMBIAR,
        fijados=frozenset(claves[c] for c in campos),
        mac_nueva=mac_nueva,
        **campos,
    )


def quitar(indice: int) -> TarjetaClon:
    return TarjetaClon(indice, AccionTarjeta.QUITAR)


def anadir(indice: int, **campos: Any) -> TarjetaClon:
    return TarjetaClon(indice, AccionTarjeta.ANADIR, **campos)


def digest_obsoleto() -> ErrorProxLaunch:
    """Respuesta a un ``PUT`` con ``digest`` caducado (el texto exacto es [LAB])."""
    return ErrorProxLaunch(
        CodigoError.DESCONOCIDO,
        {},
        "HTTP 400: Parameter verification failed. digest: detected modified configuration - "
        "file changed by other user! Try again.",
    )


class ClusterC(ClusterA):
    """``ClusterA`` con MACs nuevas al clonar y un ``PUT config`` con ``digest`` y ``delete``.

    ``digest_caduca``: cantidad de ``PUT`` con ``digest`` que se rechazan por «configuración
    modificada» (y la config pasa a otro ``digest``, como si alguien la hubiera tocado).
    ``macs_generadas``: MACs que el servidor inventó para un ``netN`` recibido sin ella.
    """

    def __init__(self, nodos: tuple[str, ...] = ("pve1",)) -> None:
        super().__init__(nodos)
        self.digest_caduca = 0
        self.macs_generadas: list[tuple[int, int, str]] = []
        self._n_digest = 0
        self._n_mac = 0

    def _clonar(self, ll: Llamada, nodo_: str, plantilla: int):  # noqa: D102
        r = super()._clonar(ll, nodo_, plantilla)
        newid = int((ll.datos or {})["newid"])
        with self._cerrojo:
            vm = self.vms.get(newid)
            if vm is not None:
                for clave, valor in list(vm["config"].items()):
                    if clave.startswith("net") and clave[3:].isdigit() and isinstance(valor, str):
                        modelo, _, resto = valor.partition(",")
                        nombre, _, _mac = modelo.partition("=")
                        mac = mac_clon(newid, int(clave[3:]))
                        vm["config"][clave] = f"{nombre}={mac}" + (f",{resto}" if resto else "")
                vm["config"]["digest"] = "dclon"
        return r

    def _put(self, ll: Llamada, nodo_: str, vmid: int, que: str):  # noqa: D102
        if que != "config":
            return super()._put(ll, nodo_, vmid, que)
        datos = dict(ll.datos or {})
        with self._cerr_m4:
            self.puts.append((nodo_, vmid, que, dict(datos)))
        vm = self.vms.get(vmid)
        if vm is None:
            raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {"nodo": nodo_}, "no existe")
        config = vm["config"]
        digest = datos.pop("digest", None)
        if digest is not None:
            with self._cerr_m4:
                caduca = self._n_digest < self.digest_caduca
                self._n_digest += 1
            if caduca:
                config["digest"] = f"dotro{self._n_digest}"
                raise digest_obsoleto()
            if digest != config.get("digest"):
                raise digest_obsoleto()
        for clave in str(datos.pop("delete", "")).split(","):
            config.pop(clave.strip(), None)
        for clave, valor in datos.items():
            if clave.startswith("net") and clave[3:].isdigit():
                modelo, _, resto = str(valor).partition(",")
                if "=" not in modelo:  # sin MAC: Proxmox inventa otra (INV-C §4)
                    self._n_mac += 1
                    mac = f"DE:AD:BE:EF:00:{self._n_mac:02X}"
                    self.macs_generadas.append((vmid, int(clave[3:]), mac))
                    valor = f"{modelo}={mac}" + (f",{resto}" if resto else "")
            config[clave] = valor
        config["digest"] = f"d{len(self.puts)}"
        return None

    # --- Consultas -------------------------------------------------------------------------

    def puts_de(self, vmid: int) -> list[dict[str, Any]]:
        """Cuerpos de los ``PUT …/config`` recibidos por la MV, en orden."""
        return [d for _n, v, q, d in self.puts if v == vmid and q == "config"]

    def puts_de_red(self, vmid: int) -> list[dict[str, Any]]:
        """Los ``PUT config`` de la MV que llevan alguna ``netN`` o ``delete`` (los de red)."""
        return [
            d
            for d in self.puts_de(vmid)
            if any(k.startswith("net") and k[3:].isdigit() for k in d) or "delete" in d
        ]

    def gets_config(self, vmid: int) -> int:
        return len(self.llamadas_a("GET", rf"/qemu/{vmid}/config$"))


class MundoC(MundoB):
    """``MundoB`` sobre un ``ClusterC``. La plantilla ``base`` (9000) trae ``net0`` y ``net1`` en
    ``vmbr0`` (MAC de plantilla) y la unidad cloud-init; ``extra`` completa o sustituye su config
    (un valor ``None`` borra esa clave, p. ej. ``net1``). ``redes_sdn`` y ``bridges`` fijan lo que
    el inventario sabe de cada nodo."""

    def __init__(
        self,
        *,
        redes: int = 2,
        extra: dict[str, Any] | None = None,
        nodos: tuple[str, ...] = ("pve1",),
        redes_sdn: dict[str, tuple[RedVirtual, ...]] | None = None,
        bridges: dict[str, tuple[Bridge, ...]] | None = None,
        **kw: Any,
    ) -> None:
        config = config_plantilla(redes=redes, **(extra or {}))
        for clave in [k for k, v in config.items() if v is None]:
            del config[clave]
        kw.setdefault("privilegios", PRIVS_B_92)
        kw.setdefault("version", V_92)
        kw.setdefault("plantillas", {9000: ("base", config)})
        original = apoyo_fase_b_p1.ClusterA
        apoyo_fase_b_p1.ClusterA = ClusterC  # type: ignore[misc]
        try:
            super().__init__(nodos=nodos, **kw)
        finally:
            apoyo_fase_b_p1.ClusterA = original  # type: ignore[misc]
        sdn = redes_sdn if redes_sdn is not None else {n: () for n in nodos}
        self.inv = con_redes(self.inv, bridges=bridges, vnets=sdn)
        self.banco.inv = self.inv

    @property
    def cluster(self) -> ClusterC:
        return self.cl  # type: ignore[return-value]


def cfg_con_red(mundo: MundoB, red: RedClon | None, **kw: Any):
    """Configuración de clon de la plantilla ``base`` con la red del clon dada."""
    return dataclasses.replace(mundo.cfg(**kw), red_clon=red)


def esta_en_hilo_principal() -> bool:  # pragma: no cover - ayuda de depuración
    return threading.current_thread() is threading.main_thread()
