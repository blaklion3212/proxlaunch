"""Constantes y reglas de los tipos de CPU de la máquina (RF-D2.11). Sin importaciones de la app.

Una sola fuente para el tipo de CPU por defecto de cada arquitectura, los tipos que ofrece el
formulario y el reconocimiento de los modelos personalizados (``custom-*``). No importa el
enum de arquitectura: recibe su valor en texto para no crear ciclos.
"""

from __future__ import annotations

import re
from typing import Final

TIPO_CPU_X86_DEFECTO: Final = "x86-64-v2-AES"
TIPO_CPU_HOST: Final = "host"
TIPO_CPU_ARM_DEFECTO: Final = TIPO_CPU_HOST
TIPOS_CPU_X86: Final = ("x86-64-v2-AES", "x86-64-v2", "x86-64-v3", "x86-64-v4", "host", "kvm64")
TIPOS_CPU_ARM: Final = (TIPO_CPU_HOST, "max")
# Tipos x86 con las instrucciones de x86-64-v3 o más (los pide Windows 11, por ejemplo).
TIPOS_CPU_X86_V3: Final = frozenset({"x86-64-v3", "x86-64-v4", "host"})
PREFIJO_CPU_PERSONALIZADA: Final = "custom-"
# Se usa con ``fullmatch``.
RE_CPU_PERSONALIZADA: Final = re.compile(r"custom-[A-Za-z0-9._-]{1,64}")

_TIPOS_COMUNES: Final = frozenset({TIPO_CPU_HOST, "max"})


def es_cpu_personalizada(tipo: str) -> bool:
    """``True`` si el texto es un modelo personalizado válido (``custom-<nombre>``)."""
    return RE_CPU_PERSONALIZADA.fullmatch(tipo) is not None


def es_cpu_solo_x86(tipo: str) -> bool:
    """``True`` si el tipo no vale en aarch64: no es ``host``, ``max`` ni ``custom-*``."""
    return tipo not in _TIPOS_COMUNES and not tipo.startswith(PREFIJO_CPU_PERSONALIZADA)


def tipo_cpu_por_defecto(arquitectura: str) -> str:
    """Tipo de CPU por defecto de la arquitectura (``aarch64`` → ``host``; otra → x86)."""
    return TIPO_CPU_ARM_DEFECTO if arquitectura == "aarch64" else TIPO_CPU_X86_DEFECTO
