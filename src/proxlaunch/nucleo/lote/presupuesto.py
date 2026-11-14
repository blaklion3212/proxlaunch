"""Presupuesto de espacio del lote (RF-L06, RF-L07, RF-L08). Funciones puras.

La clave de presupuesto es ``(nodo, storage)`` para los storages locales y
``(COMPARTIDO, storage)`` para los compartidos, que se cuentan una sola vez en todo el
clúster con el MENOR espacio libre leído (CA-L06.7, conservador).
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import replace

from proxlaunch.nucleo.lote.constantes import FACTOR_THIN_MAX, TAM_EFIDISK_MIB
from proxlaunch.nucleo.lote.modelos import (
    COMPARTIDO,
    ClavePresupuesto,
    DefinicionLote,
    ElementoPlan,
    FilaLote,
    PoliticaThin,
    Problema,
    Severidad,
    UsoStorage,
)
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Firmware
from proxlaunch.nucleo.validacion import storage_efi_efectivo

_GIB = 1024**3
_MIB = 1024**2


def _es_entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _storage_de(inv: Inventario, nodo: str, id_storage: str) -> Storage | None:
    return next((s for s in inv.storages.get(nodo, ()) if s.id == id_storage), None)


def clave_de(inv: Inventario, nodo: str, id_storage: str) -> ClavePresupuesto | None:
    """Clave de presupuesto del storage visto desde ``nodo``; ``None`` si el nodo no lo tiene."""
    st = _storage_de(inv, nodo, id_storage)
    if st is None:
        return None
    return ClavePresupuesto(COMPARTIDO if st.compartido else nodo, id_storage)


def pedido_vm(cfg: ConfiguracionVM, inv: Inventario) -> dict[ClavePresupuesto, int]:
    """Bytes que pide UNA MV por clave de presupuesto (discos y efidisk) en ``cfg.nodo``.

    Los storages que el nodo no tiene se omiten (la validación V-17 los señala).
    """
    pedido: dict[ClavePresupuesto, int] = {}

    def sumar(id_storage: str, bytes_: int) -> None:
        clave = clave_de(inv, cfg.nodo, id_storage)
        if clave is not None:
            pedido[clave] = pedido.get(clave, 0) + bytes_

    discos = cfg.discos if cfg.con_disco else []
    for d in discos:
        if _es_entero(d.tamano_gib) and d.tamano_gib > 0:
            sumar(d.storage, d.tamano_gib * _GIB)
    if cfg.firmware == Firmware.OVMF:
        id_efi = storage_efi_efectivo(cfg, inv, discos)
        if id_efi is not None:
            sumar(id_efi, TAM_EFIDISK_MIB * _MIB)
    return pedido


def libre_de_clave(inv: Inventario, clave: ClavePresupuesto) -> tuple[int, bool] | None:
    """``(libre_bytes, thin)`` de la clave, o ``None`` si ningún nodo tiene el storage.

    Compartido: el menor ``avail`` entre los nodos donde está activo (si en ninguno lo
    está, entre todos).
    """
    if clave.ambito != COMPARTIDO:
        st = _storage_de(inv, clave.ambito, clave.storage)
        return None if st is None else (st.libre_bytes, st.es_thin)
    lecturas = [
        s
        for nodo in sorted(inv.storages)
        for s in inv.storages[nodo]
        if s.id == clave.storage and s.compartido
    ]
    if not lecturas:
        return None
    activas = [s for s in lecturas if s.activo] or lecturas
    return min(s.libre_bytes for s in activas), activas[0].es_thin


def libres_iniciales(
    inv: Inventario, claves: Iterable[ClavePresupuesto]
) -> dict[ClavePresupuesto, int]:
    """Espacio libre inicial por clave (las claves desconocidas se omiten)."""
    libres: dict[ClavePresupuesto, int] = {}
    for clave in claves:
        dato = libre_de_clave(inv, clave)
        if dato is not None:
            libres[clave] = dato[0]
    return libres


def _acumular(
    cfgs: Iterable[ConfiguracionVM], inv: Inventario
) -> dict[ClavePresupuesto, UsoStorage]:
    total: dict[ClavePresupuesto, int] = {}
    for cfg in cfgs:
        for clave, bytes_ in pedido_vm(cfg, inv).items():
            total[clave] = total.get(clave, 0) + bytes_
    uso: dict[ClavePresupuesto, UsoStorage] = {}
    for clave in sorted(total, key=lambda c: (c.ambito, c.storage)):
        dato = libre_de_clave(inv, clave)
        if dato is None:
            continue
        uso[clave] = UsoStorage(pedido_bytes=total[clave], libre_bytes=dato[0], thin=dato[1])
    return uso


def uso_por_clave(
    elementos: Sequence[ElementoPlan], inv: Inventario
) -> dict[ClavePresupuesto, UsoStorage]:
    """Suma lo pedido por todos los elementos por clave y lo compara con lo libre (RF-L07)."""
    return _acumular((e.cfg for e in elementos), inv)


def uso_de_filas(
    filas: Sequence[FilaLote], nodos: Sequence[str], inv: Inventario
) -> dict[ClavePresupuesto, UsoStorage]:
    """Igual que ``uso_por_clave`` a partir de las filas y el nodo de cada una ("" se omite).

    Cada fila aporta SUS discos (CA-C08.5); ``len(nodos)`` debe ser ``len(filas)``.
    """
    return _acumular((replace(f.cfg, nodo=n) for f, n in zip(filas, nodos, strict=True) if n), inv)


def uso_de_nodos(
    plantilla: ConfiguracionVM, nodos: Sequence[str], inv: Inventario
) -> dict[ClavePresupuesto, UsoStorage]:
    """Igual que ``uso_de_filas`` con la misma plantilla en todas las MVs (lote homogéneo)."""
    return uso_de_filas([FilaLote("", plantilla)] * len(nodos), nodos, inv)


def filas_que_exceden(
    elementos: Sequence[ElementoPlan], inv: Inventario, politica: PoliticaThin
) -> tuple[int, ...]:
    """Índices (``ElementoPlan.indice``) de los elementos que no caben (CA-C08.6).

    Recorre el plan en orden con totales acumulados por clave (variante voraz): un elemento
    excede si en alguna de sus claves el acumulado, contándolo a él, supera ``libre`` (storage
    no thin, o thin con ``BLOQUEAR``) o ``FACTOR_THIN_MAX × libre`` (thin con tope). Con
    ``ADVERTIR`` un storage thin nunca hace exceder (igual que ``evaluar_espacio``). Los
    elementos que exceden NO se suman al acumulado: quitándolos, el resto cabe.
    """
    acumulado: dict[ClavePresupuesto, int] = {}
    exceden: list[int] = []
    for e in elementos:
        pedido = pedido_vm(e.cfg, inv)
        excede = False
        for clave, bytes_ in pedido.items():
            dato = libre_de_clave(inv, clave)
            if dato is None:
                continue
            libre, thin = dato
            if thin:
                if politica == PoliticaThin.ADVERTIR:
                    continue
                limite = (
                    FACTOR_THIN_MAX * libre
                    if politica == PoliticaThin.CONFIRMAR_CON_TOPE
                    else libre
                )
            else:
                limite = libre
            if acumulado.get(clave, 0) + bytes_ > limite:
                excede = True
        if excede:
            exceden.append(e.indice)
        else:
            for clave, bytes_ in pedido.items():
                acumulado[clave] = acumulado.get(clave, 0) + bytes_
    return tuple(exceden)


def _gib_texto(valor: float) -> str:
    """GiB con un decimal solo si hace falta ("160", "150.5")."""
    entero = round(valor)
    return str(entero) if abs(valor - entero) < 1e-9 else f"{valor:.1f}"


def _pedido_gib(bytes_: int) -> str:
    return _gib_texto(math.ceil(bytes_ / _GIB * 10) / 10)  # hacia arriba: nunca subestima


def _libre_gib(bytes_: int) -> str:
    return _gib_texto(math.floor(bytes_ / _GIB * 10) / 10)  # hacia abajo, como Storage.libre_gib


def evaluar_espacio(
    uso: dict[ClavePresupuesto, UsoStorage], politica: PoliticaThin
) -> list[Problema]:
    """V-L09 (no thin) y V-L10 (thin) por clave. La comparación es ``pedido <= libre`` en bytes."""
    problemas: list[Problema] = []
    for clave in sorted(uso, key=lambda c: (c.ambito, c.storage)):
        u = uso[clave]
        if u.pedido_bytes <= u.libre_bytes:
            continue
        params = {
            "ambito": clave.ambito,
            "storage": clave.storage,
            "pedido_gib": _pedido_gib(u.pedido_bytes),
            "libre_gib": _libre_gib(u.libre_bytes),
            "pedido_bytes": str(u.pedido_bytes),
            "libre_bytes": str(u.libre_bytes),
        }
        if not u.thin:
            problemas.append(Problema("V-L09", Severidad.ERROR, "discos", params))
            continue
        if politica == PoliticaThin.ADVERTIR:
            severidad = Severidad.AVISO
        elif politica == PoliticaThin.BLOQUEAR:
            severidad = Severidad.ERROR
        elif u.pedido_bytes <= FACTOR_THIN_MAX * u.libre_bytes:
            severidad = Severidad.AVISO_CONFIRMABLE
        else:
            severidad = Severidad.ERROR
        params["thin"] = "1"
        problemas.append(Problema("V-L10", severidad, "discos", params))
    return problemas


def capacidad_maxima(definicion: DefinicionLote, inv: Inventario) -> int:
    """Cuántas MVs de la plantilla caben (≤ ``definicion.cantidad``) con el algoritmo elegido.

    Búsqueda binaria sobre ``repartir`` + ``evaluar_espacio``; «caben» = sin ERROR de
    reparto ni de espacio (un aviso thin confirmable no cuenta como error). 0 si ni una cabe.
    """
    from proxlaunch.nucleo.lote.reparto import repartir  # evita el ciclo presupuesto <-> reparto

    def cabe(n: int) -> bool:
        nodos, _, problemas = repartir(definicion, inv, n)
        if any(p.severidad == Severidad.ERROR for p in problemas):
            return False
        uso = uso_de_nodos(definicion.plantilla, nodos, inv)
        return not any(
            p.severidad == Severidad.ERROR for p in evaluar_espacio(uso, definicion.politica_thin)
        )

    alto = definicion.cantidad
    if alto < 1:
        return 0
    if cabe(alto):
        return alto
    bajo = 0  # siempre «cabe» (0 máquinas)
    while alto - bajo > 1:
        medio = (bajo + alto) // 2
        if cabe(medio):
            bajo = medio
        else:
            alto = medio
    return bajo
