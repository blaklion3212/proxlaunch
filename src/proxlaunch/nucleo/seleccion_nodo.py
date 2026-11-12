"""Selección del nodo «Automático» (P-07, CA-13.5)."""

from enum import StrEnum

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Inventario

_GIB = 1024**3


class MotivoNodo(StrEnum):
    """Por qué se eligió el nodo (la interfaz lo traduce)."""

    UNICO_CANDIDATO = "unico_candidato"
    MAS_MEMORIA_LIBRE = "mas_memoria_libre"
    DESEMPATE_ESPACIO_LIBRE = "desempate_espacio_libre"


def elegir_nodo(inv: Inventario, espacio_requerido_gib: int) -> tuple[str, MotivoNodo]:
    """Elige el nodo en línea con un storage con espacio suficiente y más RAM libre.

    ``espacio_requerido_gib`` es el total que piden los discos. Un storage sirve si está
    activo, admite ``images`` y tiene al menos ese espacio libre. Desempata el mayor
    espacio libre y, si aún empatan, el nombre (orden determinista).

    Lanza ``ErrorProxLaunch`` con ``NODO_NO_DISPONIBLE`` (ningún nodo en línea) o
    ``SIN_ESPACIO`` (ninguno con espacio suficiente).
    """
    en_linea = [n for n in inv.topologia.nodos if n.en_linea]
    if not en_linea:
        raise ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE)

    requerido = max(espacio_requerido_gib, 0) * _GIB
    # (nombre, memoria libre, mayor espacio libre entre los storages aptos)
    candidatos: list[tuple[str, int, int]] = []
    for nodo in en_linea:
        aptos = [
            s.libre_bytes
            for s in inv.storages.get(nodo.nombre, ())
            if s.activo and "images" in s.contenido and s.libre_bytes >= requerido
        ]
        if aptos or requerido == 0:
            mem = nodo.mem_libre_mib if nodo.mem_libre_mib is not None else -1
            candidatos.append((nodo.nombre, mem, max(aptos, default=0)))

    if not candidatos:
        raise ErrorProxLaunch(
            CodigoError.SIN_ESPACIO, {"requerido_gib": str(espacio_requerido_gib)}
        )
    if len(candidatos) == 1:
        return candidatos[0][0], MotivoNodo.UNICO_CANDIDATO

    mejor_mem = max(c[1] for c in candidatos)
    empatados = [c for c in candidatos if c[1] == mejor_mem]
    if len(empatados) == 1:
        return empatados[0][0], MotivoNodo.MAS_MEMORIA_LIBRE
    empatados.sort(key=lambda c: (-c[2], c[0]))
    return empatados[0][0], MotivoNodo.DESEMPATE_ESPACIO_LIBRE
