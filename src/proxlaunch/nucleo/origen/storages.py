"""Storages por contenido y storage recordado por servidor (RF-O04..O06). Puro, sin E/S.

Un candidato se decide por el **contenido configurado** del storage (``content``), nunca por su
nombre, y debe estar activo en el nodo (CA-O04.1..O04.5). El storage recordado nunca se
sustituye en silencio (INV-O11): si deja de servir, ``decidir_storage`` lo dice y no elige otro.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.conexion import PerfilConexion
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage

# Tipos de storage que podrían llevar cada contenido (I4-§H). Solo sirve para el mensaje de
# «pide al administrador que lo active»; la lista de candidatos sale del contenido configurado.
# ``esxi`` queda fuera a propósito (importar desde ESXi está fuera del alcance, CA-O16.7).
_TIPOS_POSIBLES: dict[Contenido, frozenset[str]] = {
    Contenido.IMAGENES: frozenset(
        {"dir", "nfs", "cifs", "btrfs", "lvm", "lvmthin", "zfspool", "rbd", "iscsi", "zfs"}
    ),
    Contenido.ISO: frozenset({"dir", "nfs", "cifs", "btrfs", "cephfs"}),
    Contenido.IMPORT: frozenset({"dir", "nfs", "cifs", "btrfs", "cephfs"}),
}


class TipoDecision(StrEnum):
    UNICO = "unico"
    RECORDADO = "recordado"
    PREGUNTAR = "preguntar"
    RECORDADO_NO_DISPONIBLE = "recordado_no_disponible"
    SIN_CANDIDATOS = "sin_candidatos"


@dataclass(frozen=True)
class DecisionStorage:
    """Qué hacer con el storage de un contenido en un nodo."""

    tipo: TipoDecision
    storage: str | None
    candidatos: tuple[str, ...]
    recordado: str | None


def _storages_del_nodo(inv: Inventario, contenido: Contenido, nodo: str) -> tuple[Storage, ...]:
    """Storages del nodo con cualquier contenido; sin ``storages_todos`` solo se conocen los
    ``images`` de M1 (``Inventario.storages``)."""
    if nodo in inv.storages_todos:
        return inv.storages_todos[nodo]
    if contenido == Contenido.IMAGENES:
        return inv.storages.get(nodo, ())
    return ()


def candidatos(inv: Inventario, contenido: Contenido, nodo: str) -> tuple[Storage, ...]:
    """Storages activos del nodo con ese contenido configurado, ordenados por id (RF-O04)."""
    return tuple(
        sorted(
            (
                s
                for s in _storages_del_nodo(inv, contenido, nodo)
                if s.activo and contenido.value in s.contenido
            ),
            key=lambda s: s.id,
        )
    )


def candidatos_servidor(inv: Inventario, contenido: Contenido) -> tuple[str, ...]:
    """Ids de storage que son candidatos en al menos un nodo, ordenados y sin repetir."""
    nodos = set(inv.storages_todos) | set(inv.storages)
    return tuple(sorted({s.id for n in nodos for s in candidatos(inv, contenido, n)}))


def podria_admitir(tipo_storage: str, contenido: Contenido) -> bool:
    """¿Un storage de ese tipo admite el contenido si el administrador lo activa? (I4-§H)."""
    return tipo_storage in _TIPOS_POSIBLES.get(contenido, frozenset())


def decidir_storage(
    inv: Inventario, contenido: Contenido, nodo: str, recordado: str | None
) -> DecisionStorage:
    """Decide el storage de un contenido (RF-O05, RF-O06, INV-O11).

    - Recordado vigente (existe, activo, con el contenido y en el nodo) → ``RECORDADO``.
    - Recordado que ya no sirve → ``RECORDADO_NO_DISPONIBLE`` (E-O04), sin alternativa elegida.
    - Un candidato → ``UNICO`` (no se guarda); varios → ``PREGUNTAR``; ninguno →
      ``SIN_CANDIDATOS``.
    """
    ids = tuple(s.id for s in candidatos(inv, contenido, nodo))
    recordado = recordado or None
    if recordado is not None:
        if recordado in ids:
            return DecisionStorage(TipoDecision.RECORDADO, recordado, ids, recordado)
        return DecisionStorage(TipoDecision.RECORDADO_NO_DISPONIBLE, None, ids, recordado)
    if not ids:
        return DecisionStorage(TipoDecision.SIN_CANDIDATOS, None, ids, None)
    if len(ids) == 1:
        return DecisionStorage(TipoDecision.UNICO, ids[0], ids, None)
    return DecisionStorage(TipoDecision.PREGUNTAR, None, ids, None)


def recordado_de(perfil: PerfilConexion, contenido: Contenido) -> str | None:
    """Storage recordado en el perfil de conexión para ese contenido (``None`` = ninguno)."""
    if contenido == Contenido.IMAGENES:
        return perfil.storage_mv
    if contenido == Contenido.ISO:
        return perfil.storage_iso
    return perfil.storage_import


def con_recordado(
    perfil: PerfilConexion, contenido: Contenido, storage: str | None
) -> PerfilConexion:
    """Copia del perfil con el storage recordado cambiado (``None`` = dejar de recordar)."""
    if contenido == Contenido.IMAGENES:
        return replace(perfil, storage_mv=storage)
    if contenido == Contenido.ISO:
        return replace(perfil, storage_iso=storage)
    return replace(perfil, storage_import=storage)


def elegir_nodo_transferencia(
    inv: Inventario, storage: str, nodo_conectado: str | None
) -> str | None:
    """Nodo por el que subir o descargar a ``storage`` (DT-O4).

    El nodo de la sesión si el storage está activo en él; si no, el primer nodo en línea (por
    nombre) donde esté activo (un storage local solo existe en su nodo); ``None`` si ninguno.
    """
    en_linea = {n.nombre for n in inv.topologia.nodos if n.en_linea}

    def activo_en(nodo: str) -> bool:
        return nodo in en_linea and any(
            s.id == storage and s.activo for s in _storages_del_nodo(inv, Contenido.IMAGENES, nodo)
        )

    if nodo_conectado is not None and activo_en(nodo_conectado):
        return nodo_conectado
    for nodo in sorted(en_linea):
        if activo_en(nodo):
            return nodo
    return None
