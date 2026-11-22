"""Códigos V-B que no dependen del servidor (capa 1 de perfiles, lotes y CSV).

Módulo hoja: ``nucleo.validacion`` lo importa sin arrastrar el resto del paquete (que importa
``validacion``). ``cloudinit.validacion`` y ``agente.validacion`` los reexportan.
"""

from __future__ import annotations

from typing import Final

# V-B21..V-B33, V-B36, V-B38, V-B39 y V-B54 (cloud-init y snippets que solo miran el contenido).
CODIGOS_CLOUDINIT_SIN_SERVIDOR: Final[tuple[str, ...]] = (
    "V-B21",
    "V-B22",
    "V-B23",
    "V-B24",
    "V-B25",
    "V-B26",
    "V-B27",
    "V-B28",
    "V-B29",
    "V-B30",
    "V-B31",
    "V-B32",
    "V-B33",
    "V-B36",
    "V-B38",
    "V-B39",
    "V-B54",
)

# B3: V-B60, V-B61, V-B64 y V-B65 (V-B62 mira la config de la plantilla; V-B63, los permisos).
CODIGOS_ESPERA_IP_SIN_SERVIDOR: Final[tuple[str, ...]] = ("V-B60", "V-B61", "V-B64", "V-B65")
