"""Reglas V-C30..V-C38, V-C40, V-C50 y V-C52 del firewall de la máquina (C3). Puro.

``validar_firewall`` lo llama ``nucleo.validacion.validar_vm`` al final, de modo que una MV
individual y un lote validan igual. Lo que depende del servidor sale de ``inv.catalogo.firewall``
(lecturas de «Comprobar»); sin esas lecturas no se afirma nada de lo que no se sabe. Los
``params`` nunca llevan texto largo del servidor: solo nombres ya validados con ``RE_GRUPO``.
V-C39 (política desconocida) la da el lector de archivos y CSV: el enumerado la hace imposible.
"""

from __future__ import annotations

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.firewall.modelos import (
    RE_GRUPO,
    FirewallMV,
    FirewallPlantilla,
    InfoFirewall,
    ModoDhcp,
    Politica,
)
from proxlaunch.nucleo.firewall.reglas import hay_dhcp_cloudinit
from proxlaunch.nucleo.modelos.catalogo import Plantilla
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleClon
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.red.modelos import usa_red_clon
from proxlaunch.nucleo.validacion import Problema, Severidad

PRIVILEGIO_FIREWALL = "VM.Config.Network"
RUTA_FIREWALL = "/vms"
_POLITICAS_POR_DEFECTO = (Politica.BLOQUEAR, Politica.PERMITIR)


def _error(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.ERROR, dict(params))


def _aviso(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.AVISO, dict(params))


def _plantilla_de(cfg: ConfiguracionVM, inv: Inventario) -> Plantilla | None:
    """Plantilla del clon en el catálogo (por VMID si ya está resuelto, si no por nombre)."""
    det = cfg.detalle_origen
    if inv.catalogo is None or not isinstance(det, DetalleClon):
        return None
    ref = det.plantilla
    for p in inv.catalogo.plantillas or ():
        if (ref.vmid is not None and p.vmid == ref.vmid) or (
            ref.vmid is None and p.nombre == ref.nombre
        ):
            return p
    return None


def _validar_plantilla(
    cfg: ConfiguracionVM, inv: Inventario, info: InfoFirewall | None, p: list[Problema]
) -> None:
    """V-C35 (la plantilla ya trae firewall o no se pudo comprobar) y el aviso previo de las
    tarjetas ilegibles, que quedarán sin ``firewall=1`` (decisión 1 de §9)."""
    if cfg.origen != OrigenSO.CLONAR_PLANTILLA:
        return
    plantilla = _plantilla_de(cfg, inv)
    nombre = plantilla.nombre if plantilla is not None else ""
    lectura: FirewallPlantilla | None = None
    if info is not None and plantilla is not None:
        lectura = info.plantillas.get(plantilla.vmid)
    if lectura is not None:
        if not lectura.legible:
            p.append(_aviso("firewall", "V-C35", plantilla=nombre, motivo="no_comprobable"))
        elif lectura.activo or lectura.con_reglas:
            p.append(_aviso("firewall", "V-C35", plantilla=nombre, motivo="heredado"))
    # Con la red personalizada, la tarjeta ilegible ya la avisa la validación de la red (V-C20).
    if plantilla is not None and plantilla.detalle is not None and not usa_red_clon(cfg.red_clon):
        for t in plantilla.detalle.tarjetas:
            if not t.legible:
                p.append(
                    _aviso(
                        "firewall",
                        "V-C35",
                        plantilla=nombre,
                        motivo="tarjeta_ilegible",
                        tarjeta=f"net{t.indice}",
                    )
                )


def _validar_grupo(fw: FirewallMV, info: InfoFirewall | None, p: list[Problema]) -> None:
    """V-C30, V-C31, V-C32 y V-C38 del grupo elegido (``fw.grupo`` no es ``None``)."""
    grupo = fw.grupo
    if grupo is None:
        return
    if not RE_GRUPO.fullmatch(grupo):
        p.append(_error("firewall.grupo", "V-C31"))
        return  # un nombre inválido nunca llega al servidor: no se compara con nada
    if info is None:
        return
    if info.grupos is None:
        p.append(_error("firewall.grupo", "V-C32"))
        return
    if grupo not in {g.nombre for g in info.grupos}:
        p.append(_error("firewall.grupo", "V-C30", grupo=grupo))
        return
    if info.entrada_por_grupo.get(grupo) is False:
        p.append(_aviso("firewall.grupo", "V-C38", grupo=grupo))


def validar_firewall(cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades) -> list[Problema]:
    """V-C30..V-C38, V-C40, V-C50 y V-C52 de una MV; sin firewall (``None``) no valida nada.

    Con el firewall apagado solo se evalúa V-C52 (no puede haber grupo ni políticas cambiadas).
    """
    fw = cfg.firewall
    if fw is None:
        return []
    p: list[Problema] = []
    if not fw.activo:
        cambiadas = (fw.politica_entrada, fw.politica_salida) != _POLITICAS_POR_DEFECTO
        if fw.grupo is not None or cambiadas:
            p.append(_error("firewall", "V-C52"))
        return p

    # V-C50: versión de Proxmox sin grupos de seguridad.
    if not caps.tiene(Funcion.FIREWALL_GRUPO):
        minima = caps.requisito(Funcion.FIREWALL_GRUPO)
        p.append(_error("firewall", "V-C50", version=f"{minima[0]}.{minima[1]}"))
    # V-C40: sin ``VM.Config.Network`` (desconocido no bloquea).
    permisos = inv.catalogo.permisos if inv.catalogo is not None else None
    if estado_privilegio(permisos, PRIVILEGIO_FIREWALL, RUTA_FIREWALL) is False:
        p.append(_error("firewall", "V-C40", privilegio=PRIVILEGIO_FIREWALL, ruta=RUTA_FIREWALL))

    info = inv.catalogo.firewall if inv.catalogo is not None else None
    _validar_grupo(fw, info, p)

    # V-C33 / V-C34: el firewall general (Centro de datos) apagado o ilegible; nunca bloquea.
    # Sin lectura del firewall del catálogo tampoco se puede comprobar (SEG-C-S1): V-C34.
    if info is None:
        p.append(_aviso("firewall", "V-C34"))
    elif info.general_activo is False:
        p.append(_aviso("firewall", "V-C33"))
    elif info.general_activo is None:
        p.append(_aviso("firewall", "V-C34"))

    _validar_plantilla(cfg, inv, info, p)

    # V-C36: sin grupo y con la entrada en Bloquear la máquina queda aislada (RF-C3.9).
    entrada_bloquea = fw.politica_entrada == Politica.BLOQUEAR
    if fw.grupo is None and entrada_bloquea:
        if fw.acepto_aislada:
            p.append(_aviso("firewall", "V-C36"))
        else:
            p.append(_error("firewall", "V-C36"))
    # V-C37: hay DHCP por cloud-init, el usuario lo apagó y la entrada bloquea.
    if entrada_bloquea and fw.dhcp == ModoDhcp.NO and hay_dhcp_cloudinit(cfg):
        p.append(_aviso("firewall.dhcp", "V-C37"))
    return p
