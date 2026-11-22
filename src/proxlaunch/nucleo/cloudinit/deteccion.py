"""Detección de cloud-init en la ``config`` de una plantilla (RF-B1.1, DT-B5). Puro.

``info_cloudinit`` nunca lanza: una config ilegible da ``INFO_DESCONOCIDA`` (la sección se
habilita con el aviso V-B20) y nunca se lee ni se devuelve ``cipassword``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from proxlaunch.nucleo.cloudinit.modelos import (
    INFO_DESCONOCIDA,
    MAX_TARJETAS,
    TIPOS_SNIPPET,
    CicustomHeredado,
    InfoCloudInitPlantilla,
)

# Volumen de la unidad: ``…:vm-9000-cloudinit``, ``…/vm-9000-cloudinit.qcow2``, ``local:cloudinit``.
RE_UNIDAD: Final = re.compile(r"[:/](?:vm-\d+-)?cloudinit(?:\.(?:raw|qcow2|vmdk))?$")
CLAVES_UNIDAD: Final[tuple[str, ...]] = (
    *(f"ide{i}" for i in range(4)),
    *(f"sata{i}" for i in range(6)),
    *(f"scsi{i}" for i in range(31)),
    *(f"virtio{i}" for i in range(16)),
)

_RE_NET = re.compile(r"net([0-9]{1,2})")
_RE_MAC = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")
_MAX_VALOR_HEREDADO = 512
_CLAVES_HEREDADAS = frozenset({"ciuser", "nameserver", "searchdomain", "ciupgrade"})


def es_windows(ostype: str | None) -> bool:
    """``ostype`` de Windows: ``wxp``, ``w2k*``, ``wvista``, ``win7``…``win11``."""
    return isinstance(ostype, str) and ostype.strip().lower().startswith("w")


def interpretar_cicustom(valor: str) -> CicustomHeredado:
    """Interpreta ``cicustom``: ``user=…,vendor=…,network=…,meta=…`` con volúmenes no vacíos.

    Cualquier otra forma (clave desconocida, repetida o sin valor) es no interpretable y deja
    ``tipos`` vacío: solo se admitirá «como la plantilla» (RF-B4.5).
    """
    tipos: dict[str, str] = {}
    texto = valor.strip() if isinstance(valor, str) else ""
    for trozo in texto.split(","):
        if not trozo.strip():
            continue
        clave, separador, volumen = trozo.strip().partition("=")
        if not separador or clave not in TIPOS_SNIPPET or not volumen or clave in tipos:
            return CicustomHeredado(tipos={}, interpretable=False)
        tipos[clave] = volumen
    return CicustomHeredado(tipos=tipos, interpretable=True)


def _como_texto(valor: Any) -> str | None:
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, (str, int)):
        return str(valor)
    return None


def _agente_habilitado(valor: Any) -> bool:
    """``agent``: ``1``, ``enabled=1``, ``1,fstrim_cloned_disks=1``… Ausente = no habilitado."""
    texto = _como_texto(valor)
    if texto is None:
        return False
    for parte in texto.split(","):
        clave, separador, v = parte.strip().partition("=")
        if (separador and clave == "enabled") or (not separador and clave in ("0", "1")):
            return (v if separador else clave).strip().lower() in ("1", "true", "yes", "on")
    return False


def _mac_de_net(valor: Any) -> str | None:
    """MAC de ``netN`` (``virtio=BC:24:…,bridge=…`` o ``macaddr=…``)."""
    texto = _como_texto(valor)
    if texto is None:
        return None
    for parte in texto.split(","):
        _, _, v = parte.strip().partition("=")
        if _RE_MAC.fullmatch(v.strip()):
            return v.strip()
    return None


def info_cloudinit(config: Mapping[str, Any] | None) -> InfoCloudInitPlantilla:
    """Interpreta la ``config`` de una plantilla. ``None`` o ilegible = ``INFO_DESCONOCIDA``."""
    if not isinstance(config, Mapping):
        return INFO_DESCONOCIDA
    try:
        clave_unidad: str | None = None
        for clave in CLAVES_UNIDAD:
            valor = _como_texto(config.get(clave))
            if valor is not None and RE_UNIDAD.search(valor.split(",", 1)[0]):
                clave_unidad = clave
                break
        tarjetas = sorted(
            int(m.group(1))
            for k in config
            if isinstance(k, str)
            and (m := _RE_NET.fullmatch(k)) is not None
            and int(m.group(1)) < MAX_TARJETAS
        )
        heredados: dict[str, str] = {}
        for k, v in config.items():
            if not isinstance(k, str):
                continue
            es_ipconfig = k.startswith("ipconfig") and k[8:].isdigit() and int(k[8:]) < MAX_TARJETAS
            texto = _como_texto(v)
            if (k in _CLAVES_HEREDADAS or es_ipconfig) and texto is not None:
                heredados[k] = texto[:_MAX_VALOR_HEREDADO]
        ostype = _como_texto(config.get("ostype"))
        cicustom = _como_texto(config.get("cicustom"))
        return InfoCloudInitPlantilla(
            unidad=clave_unidad is not None,
            clave_unidad=clave_unidad,
            ostype=ostype,
            es_windows=es_windows(ostype),
            agente=_agente_habilitado(config.get("agent")),
            tarjetas=tuple(tarjetas),
            mac_net0=_mac_de_net(config.get("net0")),
            heredados=heredados,
            cicustom=interpretar_cicustom(cicustom) if cicustom is not None else None,
        )
    except Exception:  # noqa: BLE001 - texto no confiable: nunca debe lanzar
        return INFO_DESCONOCIDA
