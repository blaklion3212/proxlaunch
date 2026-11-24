"""Traducción de los errores del servidor ligados al hardware del clúster (RF-D3.8).

Solo reconoce patrones sobre el texto ya saneado (``detalle_tecnico`` y ``params``); nunca usa un
valor del servidor salvo que cumpla ``RE_ID_MAPEO``. El texto original se conserva en
``detalle_tecnico`` para mostrarlo junto a la explicación.
"""

from __future__ import annotations

import re

from proxlaunch.nucleo.api.traductor_errores import CODIGOS_DE_RED
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import RE_ID_MAPEO
from proxlaunch.nucleo.modelos.cpu import RE_CPU_PERSONALIZADA
from proxlaunch.nucleo.modelos.origen import DetalleClon
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM

# Errores que no son del hardware: sesión y red se dejan tal cual.
_CODIGOS_INTACTOS = frozenset(
    {
        CodigoError.SESION_EXPIRADA,
        CodigoError.CREDENCIALES_INVALIDAS,
        CodigoError.HUELLA_CAMBIADA,
        CodigoError.HUELLA_NO_CONFIADA,
        *CODIGOS_DE_RED,
    }
)

_RE_RUTA_MAPEO = re.compile(r"/mapping/(?P<tipo>pci|usb)/(?P<id>[^/\s]+)")
_RE_RUTA_CPU = re.compile(r"/mapping/cpu/(?P<nombre>[^/\s]+)")
_RE_MAPEO_NO_ENCONTRADO = re.compile(
    r"(?:PCI device|USB device|USB)?\s*mapping not found(?: for ['\"](?P<id>[^'\"]*)['\"])?",
    re.IGNORECASE,
)
_RE_MAPEO_INVALIDO = re.compile(
    r"(?:PCI device mapping|USB mapping) invalid|hardware probably changed", re.IGNORECASE
)
_RE_SIN_Q35 = re.compile(r"q35 machine model is not enabled", re.IGNORECASE)
_RE_SIN_IOMMU = re.compile(r"IOMMU not present", re.IGNORECASE)
_RE_USB_EN_USO = re.compile(r"more than one USB mapping per host", re.IGNORECASE)
_RE_NO_MIGRABLE = re.compile(r"cannot migrate|can't migrate", re.IGNORECASE)
_RE_CUSTOM = re.compile(r"custom-", re.IGNORECASE)

# Motivos de MAPEO_NO_DISPONIBLE (params["motivo"]).
MOTIVO_SIN_DISPOSITIVO = "sin_dispositivo"
MOTIVO_NO_ENCONTRADO = "no_encontrado"
MOTIVO_HARDWARE_CAMBIADO = "hardware_cambiado"
MOTIVO_SIN_Q35 = "necesita_q35"
MOTIVO_SIN_IOMMU = "sin_iommu"
MOTIVO_USB_EN_USO = "usb_en_uso"
MOTIVO_NO_MIGRABLE = "no_migrable"


def _mapeos_de(cfg: ConfiguracionVM) -> list[str]:
    """Ids de los mapeos que lleva la configuración (en orden, sin repetir)."""
    hw = cfg.hardware_cluster
    if hw is None:
        return []
    ids = [a.mapeo for a in hw.pci] + [a.mapeo for a in hw.usb]
    return list(dict.fromkeys(i for i in ids if RE_ID_MAPEO.fullmatch(i)))


def _mapeo_unico(cfg: ConfiguracionVM) -> str:
    """El mapeo de la MV si solo hay uno; si hay varios o ninguno, vacío (no se adivina)."""
    ids = _mapeos_de(cfg)
    return ids[0] if len(ids) == 1 else ""


def tipo_cpu_efectivo(cfg: ConfiguracionVM) -> str | None:
    """Tipo de CPU que se pide de verdad: el de los ajustes del clon (si es clon) o el de la MV."""
    det = cfg.detalle_origen
    cpu = det.ajustes.tipo_cpu if isinstance(det, DetalleClon) else cfg.tipo_cpu
    return cpu if isinstance(cpu, str) else None


def _cpu_personalizada(cfg: ConfiguracionVM) -> str:
    cpu = tipo_cpu_efectivo(cfg)
    return cpu if isinstance(cpu, str) and RE_CPU_PERSONALIZADA.fullmatch(cpu) else ""


def _con_detalle(
    codigo: CodigoError, params: dict[str, str], err: ErrorProxLaunch
) -> ErrorProxLaunch:
    return ErrorProxLaunch(codigo, params, err.detalle_tecnico)


def traducir_error_hardware(err: ErrorProxLaunch, cfg: ConfiguracionVM) -> ErrorProxLaunch:
    """Devuelve el error con un código claro si es de mapeos o de CPU personalizada; si no, ``err``.

    - 403 con ruta ``/mapping/pci|usb/<id>``: ``PERMISO_INSUFICIENTE`` con ``privilegio``, ``ruta``
      y ``mapeo``.
    - 403 de la CPU (``/mapping/cpu/<n>`` en 9.2; ``Sys.Audit`` en ``/nodes`` en 8.4–9.1) o un
      texto con ``custom-`` cuando la MV usa una CPU personalizada: ``CPU_PERSONALIZADA_RECHAZADA``
      con ``cpu`` y, si el servidor los dio, ``privilegio`` y ``ruta``.
    - «mapping not found», «mapping invalid», «q35 machine model is not enabled», «IOMMU not
      present», «More than one USB mapping per host» y «cannot migrate»: ``MAPEO_NO_DISPONIBLE``
      con ``mapeo``, ``nodo`` y ``motivo``.
    """
    if err.codigo in _CODIGOS_INTACTOS:
        return err
    texto = f"{err.detalle_tecnico} {' '.join(err.params.values())}"
    ruta = err.params.get("ruta", "")
    cpu = _cpu_personalizada(cfg)

    if err.codigo == CodigoError.PERMISO_INSUFICIENTE:
        m = _RE_RUTA_MAPEO.fullmatch(ruta) or _RE_RUTA_MAPEO.search(ruta)
        if m and RE_ID_MAPEO.fullmatch(m.group("id")):
            params = {k: v for k, v in err.params.items() if k in ("privilegio", "ruta")}
            params |= {"tipo": m.group("tipo"), "mapeo": m.group("id")}
            return _con_detalle(CodigoError.PERMISO_INSUFICIENTE, params, err)
        mc = _RE_RUTA_CPU.search(ruta)
        if mc or (cpu and ruta.rstrip("/") == "/nodes"):
            params = {k: v for k, v in err.params.items() if k in ("privilegio", "ruta")}
            params["cpu"] = cpu or (
                f"custom-{mc.group('nombre')}"
                if mc and RE_ID_MAPEO.fullmatch(mc.group("nombre"))
                else ""
            )
            return _con_detalle(CodigoError.CPU_PERSONALIZADA_RECHAZADA, params, err)
        return err

    nodo = cfg.nodo if isinstance(cfg.nodo, str) else ""
    mn = _RE_MAPEO_NO_ENCONTRADO.search(texto)
    if mn:
        id_texto = mn.group("id") or ""
        mapeo = id_texto if RE_ID_MAPEO.fullmatch(id_texto) else _mapeo_unico(cfg)
        motivo = MOTIVO_SIN_DISPOSITIVO if id_texto else MOTIVO_NO_ENCONTRADO
        return _con_detalle(
            CodigoError.MAPEO_NO_DISPONIBLE, {"mapeo": mapeo, "nodo": nodo, "motivo": motivo}, err
        )
    for patron, motivo in (
        (_RE_MAPEO_INVALIDO, MOTIVO_HARDWARE_CAMBIADO),
        (_RE_SIN_Q35, MOTIVO_SIN_Q35),
        (_RE_SIN_IOMMU, MOTIVO_SIN_IOMMU),
        (_RE_USB_EN_USO, MOTIVO_USB_EN_USO),
        (_RE_NO_MIGRABLE, MOTIVO_NO_MIGRABLE),
    ):
        if patron.search(texto):
            return _con_detalle(
                CodigoError.MAPEO_NO_DISPONIBLE,
                {"mapeo": _mapeo_unico(cfg), "nodo": nodo, "motivo": motivo},
                err,
            )
    if cpu and _RE_CUSTOM.search(texto):
        return _con_detalle(CodigoError.CPU_PERSONALIZADA_RECHAZADA, {"cpu": cpu}, err)
    return err
