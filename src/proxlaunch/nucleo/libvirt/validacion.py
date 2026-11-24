"""Validaciones de la importación desde libvirt que no dependen del servidor (V-D27, V-D32..34).

Funciones puras: devuelven códigos y parámetros, nunca textos para el usuario.
"""

from __future__ import annotations

import re
from typing import Final

from proxlaunch.nucleo.modelos.origen import DetalleImportacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.validacion import Problema, Severidad

RE_MAC: Final = re.compile(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}")  # se usa con fullmatch
_MAX_MAC_MOSTRADA: Final = 32


def mac_valida(texto: str) -> bool:
    """¿Es una MAC ``xx:xx:xx:xx:xx:xx`` en minúsculas con el bit I/G a 0 (unicast, V-D34)?"""
    if not isinstance(texto, str) or RE_MAC.fullmatch(texto) is None:
        return False
    return int(texto[:2], 16) & 1 == 0


def normalizar_mac(texto: str) -> str | None:
    """Minúsculas y ``:`` como separador (acepta ``-``); ``None`` si no parece una MAC."""
    if not isinstance(texto, str):
        return None
    candidata = texto.strip().lower().replace("-", ":")
    return candidata if RE_MAC.fullmatch(candidata) is not None else None


def conserva_mac(cfg: ConfiguracionVM) -> bool:
    """¿Cuenta la MAC conservada de las tarjetas? Solo con el origen «Importar disco» (DT-D15);
    con cualquier otro origen se ignora (sin V-D32..34, sin subir la versión del archivo)."""
    return cfg.origen == OrigenSO.IMPORTAR_DISCO


def _mostrable(texto: str) -> str:
    """Recorta y deja solo caracteres imprimibles sin marcado (el valor viene de un archivo)."""
    limpio = "".join(c for c in str(texto) if c.isprintable() and c not in "<>&")
    return limpio[:_MAX_MAC_MOSTRADA]


def validar_importacion_d(cfg: ConfiguracionVM, cantidad: int = 1) -> list[Problema]:
    """V-D27 (disco sin imagen), V-D32 (MAC conservada), V-D33 (con varias copias) y V-D34.

    Args:
        cfg: configuración del formulario.
        cantidad: número de copias del lote (V-D33 si hay MAC conservada y es mayor que 1).

    El disco 0 sin imagen lo cubre V-O01 en 0.8.0; aquí solo se marca (V-D27) cuando hay más
    discos con imagen propia (``otras``), para no duplicar el error de siempre.
    """
    p: list[Problema] = []
    det = cfg.detalle_origen
    if cfg.origen == OrigenSO.IMPORTAR_DISCO and isinstance(det, DetalleImportacion) and det.otras:
        if not det.imagen.nombre and not det.imagen.volid:
            p.append(
                Problema(
                    "detalle_origen.imagen",
                    "V-D27",
                    Severidad.ERROR,
                    {"disco": "0", "sistema": "si"},
                )
            )
        for i, otra in enumerate(det.otras):
            sin_imagen = otra.imagen is None or (not otra.imagen.nombre and not otra.imagen.volid)
            if sin_imagen and not otra.crear_vacio:
                p.append(
                    Problema(
                        f"detalle_origen.otras[{i}]",
                        "V-D27",
                        Severidad.ERROR,
                        {"disco": str(otra.indice)},
                    )
                )
    for i, red in enumerate(cfg.redes):
        mac = red.mac_conservada
        if mac is None or not conserva_mac(cfg):
            continue
        campo = f"redes[{i}].mac_conservada"
        p.append(Problema(campo, "V-D32", Severidad.AVISO, {"tarjeta": str(i)}))
        if not mac_valida(mac):
            p.append(
                Problema(
                    campo, "V-D34", Severidad.ERROR, {"tarjeta": str(i), "mac": _mostrable(mac)}
                )
            )
        if cantidad > 1:
            p.append(Problema(campo, "V-D33", Severidad.ERROR, {"n": str(cantidad)}))
    return p
