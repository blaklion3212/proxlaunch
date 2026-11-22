"""Reglas V-B60..V-B65 de la espera de IP (RF-B3.1, RF-B3.8). Puro.

V-B63 (privilegio del agente) está en ``cloudinit.validacion`` junto a los demás permisos.
Todas las reglas usan su identificador como ``Problema.codigo``.
"""

from __future__ import annotations

import re

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.cloudinit.codigos import CODIGOS_ESPERA_IP_SIN_SERVIDOR
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, DetalleIso
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, DetalleClon, OrigenSO
from proxlaunch.nucleo.validacion import Problema, Severidad

__all__ = ["CODIGOS_ESPERA_IP_SIN_SERVIDOR", "PLAZO_MAX_S", "PLAZO_MIN_S", "validar_espera_ip"]

PLAZO_MIN_S = 10
PLAZO_MAX_S = 1800
PLAZO_CORTO_S = 60  # V-B65: con ``ciupgrade`` el primer arranque puede tardar más
_RE_UBUNTU_DEBIAN = re.compile(r"ubuntu|debian", re.IGNORECASE)


def _nombre_de_origen(cfg: ConfiguracionVM) -> str:
    """Nombre de la plantilla o de la imagen/ISO de origen (para V-B64)."""
    d = cfg.detalle_origen
    if isinstance(d, DetalleClon):
        return d.plantilla.nombre
    if isinstance(d, DetalleImportacion):
        return f"{d.imagen.nombre} {d.imagen.volid or ''}"
    if isinstance(d, DetalleIso):
        return f"{d.iso.nombre} {d.iso.volid or ''}"
    return ""


def validar_espera_ip(cfg: ConfiguracionVM, caps: Capacidades) -> list[Problema]:
    """V-B60, V-B61, V-B62, V-B64 y V-B65. Sin ``esperar_ip`` no devuelve nada (0.6.0 intacto).

    ``caps`` se recibe por la firma de la arquitectura: hoy ninguna regla depende de la versión.
    """
    if not cfg.esperar_ip:
        return []
    p: list[Problema] = []
    campo = "esperar_ip"

    # V-B60: solo se puede conocer la IP con la MV encendida.
    if not cfg.encender:
        p.append(Problema(campo, "V-B60", Severidad.ERROR, {}))

    # V-B61: plazo entero en 10–1800 s.
    plazo = cfg.plazo_ip_s
    plazo_valido = (
        isinstance(plazo, int)
        and not isinstance(plazo, bool)
        and PLAZO_MIN_S <= plazo <= PLAZO_MAX_S
    )
    if not plazo_valido:
        p.append(
            Problema(
                "plazo_ip_s",
                "V-B61",
                Severidad.ERROR,
                {"minimo": str(PLAZO_MIN_S), "maximo": str(PLAZO_MAX_S)},
            )
        )

    # V-B62: sin agente habilitado no habrá IP que leer (aviso; la casilla de RF-B1.15 lo arregla).
    ci = cfg.cloudinit
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        info = cfg.info_cloudinit
        activara = ci is not None and ci.activar_agente
        if info is not None and info.agente is False and not activara:
            p.append(Problema(campo, "V-B62", Severidad.AVISO, {"origen": "plantilla"}))
    elif not cfg.agente_qemu:
        p.append(Problema(campo, "V-B62", Severidad.AVISO, {"origen": str(cfg.origen)}))

    # V-B64: las imágenes de Ubuntu y Debian no traen el agente instalado.
    if _RE_UBUNTU_DEBIAN.search(_nombre_de_origen(cfg)):
        p.append(Problema(campo, "V-B64", Severidad.AVISO, {}))

    # V-B65: con actualizaciones en el primer arranque el plazo corto puede no bastar. También sin
    # cloud-init propio (``cfg.cloudinit is None``) si se clona una plantilla con unidad
    # cloud-init que hereda ``ciupgrade`` (CA-B1.10.3).
    sin_unidad = cfg.info_cloudinit is not None and cfg.info_cloudinit.unidad is False
    aplica = ci is not None or (cfg.origen == OrigenSO.CLONAR_PLANTILLA and not sin_unidad)
    if plazo_valido and plazo <= PLAZO_CORTO_S and aplica:
        heredado = cfg.info_cloudinit.heredados.get("ciupgrade") if cfg.info_cloudinit else None
        actualizar = ci.actualizar if ci is not None else None
        # Proxmox trata un ``ciupgrade`` sin definir como «sí» (decisión del orquestador, §10).
        activa = actualizar is True or (
            actualizar is None and (heredado is None or heredado.strip().lower() in ("1", "true"))
        )
        if activa:
            p.append(Problema("plazo_ip_s", "V-B65", Severidad.AVISO, {"plazo_s": str(plazo)}))
    return p
