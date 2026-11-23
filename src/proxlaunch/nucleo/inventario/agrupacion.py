"""Agrupación de las MVs del servidor por lote (RF-C1.2). Puro."""

from __future__ import annotations

from collections.abc import Sequence

from proxlaunch.nucleo.inventario.modelos import RE_CODIGO_LOTE, ListaLotes, LoteServidor
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.modelos.inventario import RecursoVM


def agrupar_lotes(recursos: Sequence[RecursoVM]) -> ListaLotes:
    """Agrupa las MVs ``qemu`` con alguna etiqueta ``lote-<código>`` (sin distinguir mayúsculas).

    Los contenedores (``lxc``) se ignoran. Una MV con dos etiquetas de lote figura en ambos.
    """
    qemu = [r for r in recursos if r.tipo == "qemu"]
    grupos: dict[str, dict[int, RecursoVM]] = {}
    for r in qemu:
        for etiqueta in r.etiquetas:
            etiqueta = etiqueta.lower()
            if not etiqueta.startswith(PREFIJO_ETIQUETA_LOTE):
                continue
            codigo = etiqueta[len(PREFIJO_ETIQUETA_LOTE) :]
            if codigo:
                grupos.setdefault(codigo, {})[r.vmid] = r
    lotes = []
    for codigo in sorted(grupos):
        miembros = tuple(sorted(grupos[codigo].values(), key=lambda r: r.vmid))
        lotes.append(
            LoteServidor(
                codigo=codigo,
                valido=RE_CODIGO_LOTE.match(codigo) is not None,
                de_proxlaunch=any(
                    ETIQUETA_APP in (e.lower() for e in r.etiquetas) for r in miembros
                ),
                recursos=miembros,
            )
        )
    return ListaLotes(tuple(lotes), len(qemu))


def filtrar_lotes(lotes: Sequence[LoteServidor], texto: str) -> tuple[LoteServidor, ...]:
    """Lotes cuyo código o cuyo nombre de alguna MV contiene ``texto`` (vacío = todos)."""
    buscado = texto.strip().casefold()
    if not buscado:
        return tuple(lotes)
    return tuple(
        lote
        for lote in lotes
        if buscado in lote.codigo.casefold()
        or any(r.nombre is not None and buscado in r.nombre.casefold() for r in lote.recursos)
    )
