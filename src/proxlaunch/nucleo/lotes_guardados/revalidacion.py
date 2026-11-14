"""Desajustes de un lote cargado con el servidor actual (RF-G04, «Este lote no encaja»).

Puro: solo mira el inventario. Nunca sustituye en silencio: ``sustituir`` es una acción
explícita del usuario.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from enum import StrEnum

from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, FilaLote, ModoDestino
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import (
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    RefPlantilla,
    RefVolumen,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Firmware
from proxlaunch.nucleo.origen.nombres import partes_volid
from proxlaunch.nucleo.validacion import TIPOS_BRIDGE


class TipoDesajuste(StrEnum):
    STORAGE = "storage"
    STORAGE_EFI = "storage_efi"
    BRIDGE = "bridge"
    NODO = "nodo"
    # MVP 4: fuentes del origen que el catálogo del servidor actual no tiene (RF-O27).
    ISO = "iso"
    DRIVERS = "drivers"
    IMAGEN = "imagen"
    PLANTILLA = "plantilla"


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


def _etiqueta_ref(ref: RefVolumen) -> str:
    return ref.volid or ref.nombre


def _usos_origen(cfg: ConfiguracionVM, prefijo: str) -> list[tuple[TipoDesajuste, str, str]]:
    """(tipo, valor, campo) de cada fuente (ISO, drivers, imagen, plantilla) de la configuración."""
    det = cfg.detalle_origen
    usos: list[tuple[TipoDesajuste, str, str]] = []
    base = f"{prefijo}detalle_origen"
    if isinstance(det, DetalleIso):
        if _etiqueta_ref(det.iso):
            usos.append((TipoDesajuste.ISO, _etiqueta_ref(det.iso), f"{base}.iso"))
        if det.drivers is not None and _etiqueta_ref(det.drivers) and not det.sin_drivers:
            usos.append((TipoDesajuste.DRIVERS, _etiqueta_ref(det.drivers), f"{base}.drivers"))
    elif isinstance(det, DetalleImportacion) and _etiqueta_ref(det.imagen):
        usos.append((TipoDesajuste.IMAGEN, _etiqueta_ref(det.imagen), f"{base}.imagen"))
    elif isinstance(det, DetalleClon) and det.plantilla.nombre:
        usos.append((TipoDesajuste.PLANTILLA, det.plantilla.nombre, f"{base}.plantilla"))
    return usos


def _fuentes_validas(
    inv: Inventario, universo: list[str]
) -> tuple[dict[TipoDesajuste, set[str]], dict[TipoDesajuste, tuple[str, ...]]]:
    """Valores válidos (volids y nombres) y alternativas por tipo de fuente leída del catálogo.

    Solo incluye los tipos cuyo catálogo ya se leyó: sin lectura no se afirma ningún desajuste.
    """
    validos: dict[TipoDesajuste, set[str]] = {}
    alternativas: dict[TipoDesajuste, tuple[str, ...]] = {}
    cat = inv.catalogo
    if cat is None:
        return validos, alternativas
    for contenido, tipos in (
        (Contenido.ISO, (TipoDesajuste.ISO, TipoDesajuste.DRIVERS)),
        (Contenido.IMPORT, (TipoDesajuste.IMAGEN,)),
    ):
        if not any(lst.contenido == contenido for lst in cat.listados):
            continue
        volumenes = [v for n in universo for v in cat.volumenes(n, contenido) if v.admitido]
        valores = {x for v in volumenes for x in (v.volid, v.nombre)}
        nombres = tuple(sorted({v.nombre for v in volumenes}))
        for tipo in tipos:
            validos[tipo] = valores
            alternativas[tipo] = nombres
    if cat.plantillas is not None:
        nombres_p = tuple(sorted({p.nombre for p in cat.plantillas}))
        validos[TipoDesajuste.PLANTILLA] = set(nombres_p)
        alternativas[TipoDesajuste.PLANTILLA] = nombres_p
    return validos, alternativas


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

    validos_fuente, alternativas_fuente = _fuentes_validas(inv, universo)
    validos.update(validos_fuente)
    alternativas.update(alternativas_fuente)

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
            for tipo, valor, campo in _usos_origen(fila.cfg, f"filas[{i}]."):
                if tipo in validos and valor not in validos[tipo]:
                    anotar(tipo, valor, campo, i)
            if fila.nodo and fila.nodo not in en_linea:
                anotar(TipoDesajuste.NODO, fila.nodo, f"filas[{i}].nodo", i)
    else:
        for tipo, valor, campo in _usos(definicion.plantilla, ""):
            if valor not in validos[tipo]:
                anotar(tipo, valor, campo, None)
        for tipo, valor, campo in _usos_origen(definicion.plantilla, ""):
            if tipo in validos and valor not in validos[tipo]:
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
    else:
        _sustituir_fuente(copia, tipo, valor, nuevo)
    return copia


def _ref_nueva(nuevo: str) -> RefVolumen:
    """Un volid completo se conserva; un nombre queda sin volid (se resuelve al planificar)."""
    partes = partes_volid(nuevo)
    return RefVolumen(nombre=partes[2], volid=nuevo) if partes else RefVolumen(nombre=nuevo)


def _sustituir_fuente(copia: ConfiguracionVM, tipo: TipoDesajuste, valor: str, nuevo: str) -> None:
    det = copia.detalle_origen
    if isinstance(det, DetalleIso):
        if tipo == TipoDesajuste.ISO and _etiqueta_ref(det.iso) == valor:
            copia.detalle_origen = replace(det, iso=_ref_nueva(nuevo))
        elif (
            tipo == TipoDesajuste.DRIVERS
            and det.drivers is not None
            and _etiqueta_ref(det.drivers) == valor
        ):
            copia.detalle_origen = replace(det, drivers=_ref_nueva(nuevo))
    elif isinstance(det, DetalleImportacion):
        if tipo == TipoDesajuste.IMAGEN and _etiqueta_ref(det.imagen) == valor:
            copia.detalle_origen = replace(det, imagen=_ref_nueva(nuevo))
    elif (
        isinstance(det, DetalleClon)
        and tipo == TipoDesajuste.PLANTILLA
        and det.plantilla.nombre == valor
    ):
        copia.detalle_origen = replace(det, plantilla=RefPlantilla(nombre=nuevo))


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
