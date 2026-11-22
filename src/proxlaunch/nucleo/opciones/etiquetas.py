"""Etiquetas del usuario: normalización y evaluación contra la política del centro de datos.
Puro, sin E/S."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from proxlaunch.nucleo.opciones.modelos import PoliticaEtiquetas

if TYPE_CHECKING:
    from proxlaunch.nucleo.modelos.vm import ConfiguracionVM

MOTIVO_REGISTRADA = "registrada"
MOTIVO_NO_PERMITIDA = "no_permitida"
MOTIVO_NINGUNA = "ninguna_permitida"

_SEPARADORES = re.compile(r"[,;]")


def normalizar_etiquetas(texto: str) -> tuple[str, ...]:
    """Separa por comas o ``;``, recorta espacios, descarta vacías y duplicados (respeta el orden).

    No cambia mayúsculas ni espacios internos: eso lo rechaza la validación sintáctica.
    """
    vistas: dict[str, None] = {}
    for trozo in _SEPARADORES.split(texto):
        limpio = trozo.strip()
        if limpio:
            vistas.setdefault(limpio, None)
    return tuple(vistas)


def etiquetas_finales(cfg: ConfiguracionVM) -> tuple[str, ...]:
    """Etiquetas fijas (``cfg.etiquetas``) y después las del usuario, sin duplicados."""
    return tuple(dict.fromkeys((*cfg.etiquetas, *cfg.etiquetas_usuario)))


def rechazadas_por_politica(
    etiquetas: Sequence[str], politica: PoliticaEtiquetas, puede_sys_modify: bool | None
) -> list[tuple[str, str]]:
    """Etiquetas que Proxmox rechazaría para este usuario: ``[(etiqueta, motivo)]``.

    Regla de ``assert_tag_permissions``: con ``Sys.Modify`` en ``/`` todo pasa. Si no, una
    etiqueta registrada se rechaza (``registrada``); después, según ``user-allow``: ``none``
    rechaza todas (``ninguna_permitida``), ``list`` y ``existing`` solo admiten las de la lista
    del usuario o las ya existentes (``no_permitida``) y ``free`` no restringe.

    La comparación con las listas es **exacta** (S-1, fase A §15): no se puede verificar cómo
    compara Proxmox, y exacta nunca deja pasar algo que Proxmox rechace. ``distingue_mayusculas``
    se conserva en el modelo pero no interviene en la decisión. ``puede_sys_modify`` en ``None``
    (permisos desconocidos) no rechaza por «registrada»: no se puede afirmar (y la validación
    degrada a aviso el resto de rechazos, QA-A-10).
    """
    if puede_sys_modify is True:
        return []

    registradas = set(politica.registradas)
    permitidas = {*politica.lista_usuario, *politica.existentes}
    rechazadas: list[tuple[str, str]] = []
    for etiqueta in dict.fromkeys(etiquetas):
        if etiqueta in registradas and puede_sys_modify is False:
            rechazadas.append((etiqueta, MOTIVO_REGISTRADA))
        elif politica.permiso == "none":
            rechazadas.append((etiqueta, MOTIVO_NINGUNA))
        elif politica.permiso in ("list", "existing") and etiqueta not in permitidas:
            rechazadas.append((etiqueta, MOTIVO_NO_PERMITIDA))
    return rechazadas
