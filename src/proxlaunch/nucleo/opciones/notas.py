"""Notas de la MV (campo ``description``): bloque automático, texto libre y límites. Puro.

El bloque automático es Markdown controlado por la app: todo valor externo (perfil, lote,
usuario) se escapa. El texto libre del usuario se envía tal cual, salvo la normalización de
saltos de línea y la eliminación de caracteres de control.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from proxlaunch.nucleo.archivos.texto import CARACTERES_BIDI
from proxlaunch.nucleo.opciones.modelos import ContextoNotas

if TYPE_CHECKING:
    from proxlaunch.nucleo.modelos.vm import ConfiguracionVM

LIMITE_DESCRIPCION = 8192  # límite duro de Proxmox (caracteres)
AVISO_DESCRIPCION = 7500  # a partir de aquí se avisa (P-11)


class _DescripcionIlegible(str):
    """Marca para «la descripción de la plantilla no se pudo leer» (se compara con ``is``)."""

    __slots__ = ()


# Valor de ``descripcion_plantilla`` cuando el GET de la plantilla no pudo leerla (P-10): no se
# envía ``description`` para no pisar las notas de la plantilla. Es un ``str`` vacío especial.
LEIDA_NO: str = _DescripcionIlegible("")

_ESCAPABLES = "\\`*_[]()<>#|~&"
_RE_ESQUEMA = re.compile(r"\b(javascript|vbscript|data):", re.IGNORECASE)
_RE_SALTOS = re.compile(r"\r\n|\r|\n")
_RE_PORCENTAJE = re.compile(r"%(?=[0-9A-Fa-f]{2})")
_ZWSP = "​"


def _es_control(c: str) -> bool:
    return unicodedata.category(c) == "Cc" and c not in ("\n", "\t")


def escapar_markdown(texto: str) -> str:
    """Escapa un valor para el bloque Markdown: los saltos de línea pasan a espacio, se quitan los
    caracteres de control y se antepone ``\\`` a los signos con significado en Markdown. El
    ``:`` de un esquema como ``javascript:`` también se escapa."""
    sin_saltos = _RE_SALTOS.sub(" ", texto)
    limpio = "".join(c for c in sin_saltos if not _es_control(c))
    escapado = "".join(f"\\{c}" if c in _ESCAPABLES else c for c in limpio)
    return _RE_ESQUEMA.sub(lambda m: f"{m.group(1)}\\:", escapado)


def limpiar_texto_libre(texto: str) -> tuple[str, bool]:
    """Normaliza ``\\r\\n`` y ``\\r`` a ``\\n`` y quita los caracteres de control salvo ``\\n`` y
    ``\\t`` y los de dirección de texto (bidi, que pueden disfrazar el contenido; QA-A-12).
    Devuelve ``(limpio, hubo_cambios)``: ``True`` solo si se eliminó algún carácter de control o
    bidi (la normalización de saltos de línea no merece aviso)."""
    normalizado = _RE_SALTOS.sub("\n", texto)
    limpio = "".join(c for c in normalizado if not _es_control(c) and c not in CARACTERES_BIDI)
    return limpio, limpio != normalizado


def usuario_para_notas(usuario_efectivo: str) -> str:
    """``usuario@realm`` a partir del usuario efectivo: corta en ``!`` (nombre del token)."""
    return usuario_efectivo.split("!", 1)[0].strip()


def bloque_automatico(ctx: ContextoNotas) -> str:
    """Bloque de «notas de origen»: versión, fecha y, si existen, lote, perfil y usuario."""
    lineas = [
        f"Creada con ProxLaunch {escapar_markdown(ctx.version_app)}",
        "",
        f"- Fecha: {ctx.fecha.isoformat(timespec='seconds')}",
    ]
    if ctx.id_lote:
        lineas.append(f"- Lote: {escapar_markdown(ctx.id_lote)}")
    if ctx.perfil:
        lineas.append(f"- Perfil: {escapar_markdown(ctx.perfil)}")
    if ctx.usuario:
        lineas.append(f"- Usuario: {escapar_markdown(ctx.usuario)}")
    return "\n".join(lineas)


def neutralizar_porcentajes(texto: str, version: tuple[int, int] | None) -> str:
    """Inserta U+200B entre ``%`` y dos dígitos hex cuando la versión es desconocida (``None``).

    El issue 5486 (Proxmox < 8.3 decodifica ``%xx`` como URL) no afecta a las versiones
    soportadas (mínima 8.4): con versión conocida el texto no se toca; sin ella, por prudencia."""
    if version is not None:
        return texto
    return _RE_PORCENTAJE.sub(f"%{_ZWSP}", texto)


def componer_descripcion(
    cfg: ConfiguracionVM,
    ctx: ContextoNotas,
    descripcion_plantilla: str | None,
    version: tuple[int, int] | None,
) -> str | None:
    """Texto final de ``description``; ``None`` si no hay nada que enviar.

    Sin clon: bloque (si ``notas_origen``) y texto libre, separados por una línea en blanco.
    Clon: descripción de la plantilla, ``\\n\\n`` y lo anterior. Un clon con la descripción de la
    plantilla ilegible (``LEIDA_NO``) devuelve ``None`` para no pisarla (P-10).
    """
    # Importación local: ``vm`` no importa este paquete, pero así el módulo carga sin él.
    from proxlaunch.nucleo.modelos.vm import OrigenSO

    partes: list[str] = []
    if cfg.notas_origen:
        partes.append(bloque_automatico(ctx))
    libre = limpiar_texto_libre(cfg.notas)[0].rstrip()
    if libre.strip():
        partes.append(libre)
    if not partes:
        return None
    texto = "\n\n".join(partes)
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        if descripcion_plantilla is LEIDA_NO:
            return None
        previa = _RE_SALTOS.sub("\n", descripcion_plantilla or "").rstrip()
        if previa.strip():
            texto = f"{previa}\n\n{texto}"
    return neutralizar_porcentajes(texto, version)
