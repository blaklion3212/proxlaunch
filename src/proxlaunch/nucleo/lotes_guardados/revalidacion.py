"""Desajustes de un lote cargado con el servidor actual (RF-G04, «Este lote no encaja»).

Puro: solo mira el inventario. Nunca sustituye en silencio: ``sustituir`` es una acción
explícita del usuario.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from enum import StrEnum

from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, FilaLote, ModoDestino
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Firmware
from proxlaunch.nucleo.validacion import TIPOS_BRIDGE


class TipoDesajuste(StrEnum):
    STORAGE = "storage"
    STORAGE_EFI = "storage_efi"
    BRIDGE = "bridge"
    NODO = "nodo"


@dataclass(frozen=True)
class Desajuste:
    """Un valor del lote que el servidor actual no tiene.

    ``indices``: filas afectadas (vacío en homogéneo). ``campos``: rutas de los campos que
    lo usan (en por filas con prefijo ``filas[i].``). ``disponibles``: alternativas válidas.
    """

    tipo: TipoDesajuste
    valor: str
    indices: tuple[int, ...]
    campos: tuple[str, ...]
    disponibles: tuple[str, ...]


def _usos(cfg: ConfiguracionVM, prefijo: str) -> list[tuple[TipoDesajuste, str, str]]:
    """(tipo, valor, campo) de cada storage y bridge que usa la configuración."""
    usos: list[tuple[TipoDesajuste, str, str]] = []
    if cfg.con_disco:
        usos += [
            (TipoDesajuste.STORAGE, d.storage, f"{prefijo}discos[{i}].storage")
            for i, d in enumerate(cfg.discos)
        ]
    if cfg.firmware == Firmware.OVMF and cfg.storage_efi:
        usos.append((TipoDesajuste.STORAGE_EFI, cfg.storage_efi, f"{prefijo}storage_efi"))
    usos += [
        (TipoDesajuste.BRIDGE, r.bridge, f"{prefijo}redes[{i}].bridge")
        for i, r in enumerate(cfg.redes)
    ]
    return usos


def _nodos_universo(definicion: DefinicionLote, inv: Inventario) -> list[str]:
    """Nodos donde puede caer el lote: los elegidos que existen, o todos."""
    todos = [n.nombre for n in inv.topologia.nodos]
    d = definicion.destino
    if not definicion.es_por_filas and d.modo != ModoDestino.AUTOMATICO:
        elegidos = [n for n in todos if n in d.nodos]
        return elegidos or todos
    return todos


def desajustes(definicion: DefinicionLote, inv: Inventario) -> tuple[Desajuste, ...]:
    """Storage, bridge y nodos del lote que no existen (o no sirven) en el servidor actual."""
    universo = _nodos_universo(definicion, inv)
    storages = sorted(
        {
            s.id
            for n in universo
            for s in inv.storages.get(n, ())
            if s.activo and "images" in s.contenido
        }
    )
    bridges = sorted(
        {b.nombre for n in universo for b in inv.bridges.get(n, ()) if b.tipo in TIPOS_BRIDGE}
    )
    en_linea = tuple(n.nombre for n in inv.topologia.nodos if n.en_linea)
    validos = {
        TipoDesajuste.STORAGE: set(storages),
        TipoDesajuste.STORAGE_EFI: set(storages),
        TipoDesajuste.BRIDGE: set(bridges),
    }
    alternativas = {
        TipoDesajuste.STORAGE: tuple(storages),
        TipoDesajuste.STORAGE_EFI: tuple(storages),
        TipoDesajuste.BRIDGE: tuple(bridges),
        TipoDesajuste.NODO: en_linea,
    }

    # (tipo, valor) → (índices, campos), en orden de aparición.
    grupos: dict[tuple[TipoDesajuste, str], tuple[list[int], list[str]]] = {}

    def anotar(tipo: TipoDesajuste, valor: str, campo: str, indice: int | None) -> None:
        indices, campos = grupos.setdefault((tipo, valor), ([], []))
        if indice is not None and indice not in indices:
            indices.append(indice)
        campos.append(campo)

    if definicion.es_por_filas:
        for i, fila in enumerate(definicion.filas):
            for tipo, valor, campo in _usos(fila.cfg, f"filas[{i}]."):
                if valor not in validos[tipo]:
                    anotar(tipo, valor, campo, i)
            if fila.nodo and fila.nodo not in en_linea:
                anotar(TipoDesajuste.NODO, fila.nodo, f"filas[{i}].nodo", i)
    else:
        for tipo, valor, campo in _usos(definicion.plantilla, ""):
            if valor not in validos[tipo]:
                anotar(tipo, valor, campo, None)
        d = definicion.destino
        if d.modo != ModoDestino.AUTOMATICO:
            for j, nodo in enumerate(d.nodos):
                if nodo not in en_linea:
                    anotar(TipoDesajuste.NODO, nodo, f"destino.nodos[{j}]", None)
    return tuple(
        Desajuste(tipo, valor, tuple(indices), tuple(campos), alternativas[tipo])
        for (tipo, valor), (indices, campos) in grupos.items()
    )


def _sustituir_cfg(
    cfg: ConfiguracionVM, tipo: TipoDesajuste, valor: str, nuevo: str
) -> ConfiguracionVM:
    copia = copy.deepcopy(cfg)
    if tipo == TipoDesajuste.STORAGE:
        for d in copia.discos:
            if d.storage == valor:
                d.storage = nuevo
    elif tipo == TipoDesajuste.STORAGE_EFI:
        if copia.storage_efi == valor:
            copia.storage_efi = nuevo
    elif tipo == TipoDesajuste.BRIDGE:
        for r in copia.redes:
            if r.bridge == valor:
                r.bridge = nuevo
    return copia


def sustituir(
    definicion: DefinicionLote, desajuste: Desajuste, nuevo: str | None
) -> DefinicionLote:
    """Definición nueva con ``desajuste.valor`` cambiado por ``nuevo`` (acción explícita).

    ``None`` solo vale para ``NODO``: en homogéneo pasa el destino a Automático (conserva el
    algoritmo); en por filas deja el nodo de las filas afectadas vacío (reparto automático).
    """
    tipo = desajuste.tipo
    if nuevo is None and tipo != TipoDesajuste.NODO:
        raise ValueError("Solo el nodo puede pasar a Automático")
    if definicion.es_por_filas:
        filas: list[FilaLote] = list(definicion.filas)
        for i in desajuste.indices:
            f = filas[i]
            if tipo == TipoDesajuste.NODO:
                if f.nodo == desajuste.valor:
                    filas[i] = replace(f, nodo=nuevo)
            else:
                assert nuevo is not None
                filas[i] = replace(f, cfg=_sustituir_cfg(f.cfg, tipo, desajuste.valor, nuevo))
        return replace(definicion, filas=tuple(filas))
    if tipo == TipoDesajuste.NODO:
        if nuevo is None:
            destino = Destino(ModoDestino.AUTOMATICO, (), definicion.destino.algoritmo)
        else:
            nodos = tuple(
                dict.fromkeys(
                    nuevo if n == desajuste.valor else n for n in definicion.destino.nodos
                )
            )
            destino = replace(definicion.destino, nodos=nodos)
        return replace(definicion, destino=destino)
    assert nuevo is not None
    return replace(
        definicion, plantilla=_sustituir_cfg(definicion.plantilla, tipo, desajuste.valor, nuevo)
    )
