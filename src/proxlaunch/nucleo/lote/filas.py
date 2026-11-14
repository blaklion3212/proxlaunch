"""Lote por filas (D-22): camino único ``filas_efectivas`` y utilidades sobre las filas.

Planificador, reparto, presupuesto e informe trabajan sobre filas. El lote homogéneo es el
caso particular «todas las filas comparten ``cfg`` y nada es fijo» (CA-C08.12). Funciones
puras, sin E/S (docs/arquitectura/mvp3.md §4).
"""

import copy
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import replace

from proxlaunch.nucleo.lote.constantes import (
    ETIQUETA_APP,
    MAX_LOTE,
    PREFIJO_ETIQUETA_LOTE,
    VMID_MAXIMO,
    VMID_MINIMO,
)
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    DefinicionLote,
    Destino,
    ElementoPlan,
    FilaLote,
    ModoDestino,
    PatronNombres,
    PoliticaThin,
    Problema,
    Severidad,
)
from proxlaunch.nucleo.lote.nombres import generar_nombres
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM


def _es_entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def usa_nombre_de_plantilla(definicion: DefinicionLote) -> bool:
    """N=1 con prefijo vacío en un lote homogéneo: el nombre es el de la plantilla (CA-L04.1).

    En un lote por filas es siempre falso: cada fila trae su propio nombre.
    """
    return (
        not definicion.es_por_filas and definicion.cantidad == 1 and definicion.patron.prefijo == ""
    )


def filas_efectivas(definicion: DefinicionLote) -> tuple[FilaLote, ...]:
    """Convierte CUALQUIER definición en filas (camino único).

    Por filas devuelve ``definicion.filas``. Homogéneo genera ``cantidad`` filas
    ``FilaLote(nombre_i, plantilla)`` con los nombres del patrón (o el de la plantilla si
    ``usa_nombre_de_plantilla``), sin VMID ni nodo fijos. La plantilla de un lote
    homogéneo se comparte entre las filas (quien la use debe copiarla, no mutarla).
    """
    if definicion.es_por_filas:
        return definicion.filas
    nombres = (
        [definicion.plantilla.nombre]
        if usa_nombre_de_plantilla(definicion)
        else generar_nombres(definicion.patron, definicion.cantidad)
    )
    return tuple(FilaLote(nombre, definicion.plantilla) for nombre in nombres)


def _etiqueta_fila(fila: FilaLote, posicion: int) -> str:
    """Número con el que se nombra una fila en los mensajes: su origen o su posición (1..N)."""
    return str(fila.origen if fila.origen is not None else posicion + 1)


def validar_filas(definicion: DefinicionLote) -> list[Problema]:
    """Capa 1 de un lote por filas, sin servidor (docs/arquitectura/mvp3.md §4.1).

    V-L01 (1 ≤ N ≤ ``MAX_LOTE`` y ``cantidad == len(filas)``), V-M07 (nombre vacío), V-M10
    (nombres sin distinguir mayúsculas o VMIDs explícitos repetidos: una entrada por CADA fila
    implicada, con su ``indice``), V-02 (VMID explícito fuera de rango) y V-L13 (el destino
    de un lote por filas es siempre Automático). En un lote homogéneo no valida nada.
    """
    if not definicion.es_por_filas:
        return []
    filas = definicion.filas
    p: list[Problema] = []
    n = len(filas)
    if not _es_entero(definicion.cantidad) or definicion.cantidad != n or not 1 <= n <= MAX_LOTE:
        p.append(Problema("V-L01", Severidad.ERROR, "cantidad", {"max": str(MAX_LOTE)}))
    if definicion.destino.modo != ModoDestino.AUTOMATICO:
        p.append(
            Problema("V-L13", Severidad.ERROR, "destino", {"modo": definicion.destino.modo.value})
        )

    por_nombre: dict[str, list[int]] = defaultdict(list)
    por_vmid: dict[int, list[int]] = defaultdict(list)
    for i, fila in enumerate(filas):
        if not fila.nombre.strip():
            p.append(Problema("V-M07", Severidad.ERROR, "nombre", {}, indice=i))
        else:
            por_nombre[fila.nombre.casefold()].append(i)
        if fila.vmid is not None:
            if _es_entero(fila.vmid) and VMID_MINIMO <= fila.vmid <= VMID_MAXIMO:
                por_vmid[fila.vmid].append(i)
            else:
                p.append(Problema("V-02", Severidad.ERROR, "vmid", {}, indice=i))

    for indices in por_nombre.values():
        if len(indices) > 1:
            lista = ",".join(_etiqueta_fila(filas[i], i) for i in indices)
            for i in indices:
                params = {"nombre": filas[i].nombre, "filas": lista}
                p.append(Problema("V-M10", Severidad.ERROR, "nombre", params, indice=i))
    for vmid, indices in por_vmid.items():
        if len(indices) > 1:
            lista = ",".join(_etiqueta_fila(filas[i], i) for i in indices)
            for i in indices:
                params = {"vmid": str(vmid), "filas": lista}
                p.append(Problema("V-M10", Severidad.ERROR, "vmid", params, indice=i))
    return p


def definicion_por_filas(
    filas: Sequence[FilaLote],
    *,
    plantilla_base: ConfiguracionVM,
    algoritmo: Algoritmo = Algoritmo.EQUILIBRADO,
    vmid_inicial: int | None = None,
    etiquetar: bool = True,
    politica_thin: PoliticaThin = PoliticaThin.CONFIRMAR_CON_TOPE,
) -> DefinicionLote:
    """Definición de un lote por filas: destino Automático, patrón vacío e ignorado y
    ``cantidad == len(filas)``. ``plantilla_base`` es solo informativa (ningún cálculo la lee).

    Con ``filas`` vacío el resultado no es «por filas» (``es_por_filas`` es falso) y la
    validación lo rechaza con V-L01 por cantidad 0.
    """
    return DefinicionLote(
        plantilla=plantilla_base,
        cantidad=len(filas),
        patron=PatronNombres(prefijo=""),
        destino=Destino(ModoDestino.AUTOMATICO, (), algoritmo),
        vmid_inicial=vmid_inicial,
        etiquetar=etiquetar,
        politica_thin=politica_thin,
        filas=tuple(filas),
    )


def _exigir_por_filas(definicion: DefinicionLote) -> None:
    if not definicion.es_por_filas:
        raise ValueError("la definición no es un lote por filas")


def sin_filas(definicion: DefinicionLote, indices: Collection[int]) -> DefinicionLote:
    """Definición sin las filas de ``indices`` (posiciones 0..N-1) y con ``cantidad`` ajustada.

    Raises:
        ValueError: la definición no es por filas o algún índice no existe.
    """
    _exigir_por_filas(definicion)
    n = len(definicion.filas)
    if any(not _es_entero(i) or not 0 <= i < n for i in indices):
        raise ValueError("índice de fila fuera de rango")
    quitar = set(indices)
    quedan = tuple(f for i, f in enumerate(definicion.filas) if i not in quitar)
    return replace(definicion, filas=quedan, cantidad=len(quedan))


def reemplazar_fila(definicion: DefinicionLote, indice: int, fila: FilaLote) -> DefinicionLote:
    """Definición con la fila ``indice`` sustituida por ``fila`` (p. ej. ``vmid=None``).

    Raises:
        ValueError: la definición no es por filas o el índice no existe.
    """
    _exigir_por_filas(definicion)
    if not _es_entero(indice) or not 0 <= indice < len(definicion.filas):
        raise ValueError("índice de fila fuera de rango")
    filas = list(definicion.filas)
    filas[indice] = fila
    return replace(definicion, filas=tuple(filas))


def definicion_para_reintento(
    definicion: DefinicionLote, elementos: Sequence[ElementoPlan]
) -> DefinicionLote:
    """Definición para reintentar los ``elementos`` no creados (RF-L21, CA-C08.10).

    Homogéneo: igual que hoy, ``cantidad`` ajustada y ``vmid_inicial`` en ``None``. Por filas:
    una fila por elemento, en su orden, con su nombre, VMID y nodo y una copia de su ``cfg``
    sin las etiquetas del lote anterior (el plan nuevo añade las suyas).
    """
    if not definicion.es_por_filas:
        return replace(definicion, cantidad=len(elementos), vmid_inicial=None)
    filas: list[FilaLote] = []
    for e in elementos:
        cfg = copy.deepcopy(e.cfg)
        cfg.etiquetas = tuple(
            t
            for t in cfg.etiquetas
            if t != ETIQUETA_APP and not t.startswith(PREFIJO_ETIQUETA_LOTE)
        )
        origen = (
            definicion.filas[e.indice].origen if 0 <= e.indice < len(definicion.filas) else None
        )
        filas.append(FilaLote(e.nombre, cfg, vmid=e.vmid, nodo=e.nodo, origen=origen))
    return replace(definicion, filas=tuple(filas), cantidad=len(filas), vmid_inicial=None)
