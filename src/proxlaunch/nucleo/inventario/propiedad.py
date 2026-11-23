"""Reglas de propiedad y deshacibilidad del inventario (DT-C14, DT-C17, RF-C1.8). Puro.

Una MV es «deshacible desde aquí» solo si, con su configuración releída, lleva las etiquetas
``proxlaunch`` y ``lote-<id>``, su nota nombra el mismo lote y no es una plantilla. Nunca se
decide por el nombre.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.inventario.modelos import (
    RE_CODIGO_LOTE,
    DetalleLote,
    EstadoNota,
    LoteServidor,
    MotivoNoDeshacible,
    MVInventario,
)
from proxlaunch.nucleo.inventario.nota import leer_nota_origen
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, MAX_LOTE, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.lote.modelos import CandidatoRollback, ElementoPlan, EntradaLibro, EstadoMV
from proxlaunch.nucleo.lote.reconciliacion import etiquetas_de_config
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import RecursoVM
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.origen.permisos import estado_privilegio

PRIVILEGIO_BORRAR = "VM.Allocate"
ESTADOS_CONOCIDOS = frozenset({"running", "stopped"})
_MAX_TEXTO_PARAMETRO = 64
_CODIGOS_NODO_CAIDO = frozenset({CodigoError.SERVIDOR_NO_RESPONDE, CodigoError.NODO_NO_DISPONIBLE})


def _verdadero(valor: object) -> bool:
    return str(valor).strip().lower() in ("1", "true", "yes", "on")


def _texto_corto(valor: object) -> str:
    """Valor externo apto para un parámetro de mensaje (sin controles, acotado)."""
    texto = "".join(c for c in str(valor) if c.isprintable() and c not in "<>&")
    return texto[:_MAX_TEXTO_PARAMETRO]


def mv_sin_detalle(recurso: RecursoVM) -> MVInventario:
    """MV aún no leída (o con la lectura cancelada): no deshacible hasta leerla."""
    return MVInventario(recurso, None, None, (MotivoNoDeshacible.SIN_DETALLE,))


def _sin_config(recurso: RecursoVM, error: ErrorProxLaunch | None) -> MVInventario:
    """MV cuya configuración no se obtuvo: ya no existe, nodo caído o ilegible."""
    params: dict[str, str] = {}
    if error is None or error.codigo == CodigoError.RECURSO_INEXISTENTE:
        motivo = MotivoNoDeshacible.YA_NO_EXISTE
    elif error.codigo in _CODIGOS_NODO_CAIDO:
        motivo = MotivoNoDeshacible.NODO_SIN_RESPUESTA
        params["nodo"] = _texto_corto(recurso.nodo or "")
    else:
        motivo = MotivoNoDeshacible.CONFIG_ILEGIBLE
    return MVInventario(recurso, None, None, (motivo,), params)


def evaluar_mv(
    recurso: RecursoVM,
    lote: LoteServidor,
    config: Mapping[str, Any] | None,
    error: ErrorProxLaunch | None,
    permisos: PermisosEfectivos | None,
) -> MVInventario:
    """Decide si una MV se puede deshacer desde el inventario y, si no, por qué (todos los motivos).

    ``config`` ``None`` y ``error`` ``None`` = la MV ya no existe. Con ``error`` se distingue
    nodo sin respuesta, inexistente y configuración ilegible.
    """
    if config is None:
        return _sin_config(recurso, error)
    if not isinstance(config, Mapping):
        return _sin_config(recurso, ErrorProxLaunch(CodigoError.DESCONOCIDO))
    motivos: list[MotivoNoDeshacible] = []
    params: dict[str, str] = {}
    if not lote.valido:
        motivos.append(MotivoNoDeshacible.CODIGO_INVALIDO)
    etiquetas = etiquetas_de_config(dict(config))
    etiqueta_lote = f"{PREFIJO_ETIQUETA_LOTE}{lote.codigo}"
    faltan = [e for e in (ETIQUETA_APP, etiqueta_lote) if e not in etiquetas]
    if faltan:
        motivos.append(MotivoNoDeshacible.FALTA_ETIQUETA)
        params["falta"] = ", ".join(faltan)
    nota = leer_nota_origen(config.get("description"), lote.codigo)
    if nota.estado == EstadoNota.FALTA:
        motivos.append(MotivoNoDeshacible.SIN_NOTA)
    elif nota.estado == EstadoNota.OTRO_LOTE:
        motivos.append(MotivoNoDeshacible.NOTA_OTRO_LOTE)
        params["otro"] = _texto_corto(nota.lote or "")
    if _verdadero(config.get("template", 0)) or recurso.plantilla is True:
        motivos.append(MotivoNoDeshacible.PLANTILLA)
    bloqueo = config.get("lock") or recurso.bloqueo
    if bloqueo:
        motivos.append(MotivoNoDeshacible.BLOQUEADA)
        params["bloqueo"] = _texto_corto(bloqueo)
    if (recurso.estado or "").lower() not in ESTADOS_CONOCIDOS:
        motivos.append(MotivoNoDeshacible.ESTADO_DESCONOCIDO)
    if recurso.nodo is None:
        motivos.append(MotivoNoDeshacible.CONFIG_ILEGIBLE)
    if estado_privilegio(permisos, PRIVILEGIO_BORRAR, f"/vms/{recurso.vmid}") is False:
        motivos.append(MotivoNoDeshacible.SIN_PERMISO_BORRAR)
    protegida = _verdadero(config.get("protection", 0))
    return MVInventario(recurso, protegida, nota, tuple(motivos), params)


def es_propia_inventario(
    config: Mapping[str, Any], entrada: EntradaLibro, id_lote: str, etiquetado: bool
) -> bool:
    """Regla de propiedad del inventario (DT-C14), con la firma de ``ReglaPropiedad``.

    Con la config releída: etiquetas ``proxlaunch`` y ``lote-<id>``, nota cuyo último bloque
    nombra ``id_lote`` y ``template`` distinto de 1. Ignora el nombre de la entrada y
    ``etiquetado`` (aquí las etiquetas siempre son obligatorias).
    """
    del entrada, etiquetado  # no intervienen: no hay plan y la etiqueta es siempre exigible
    if RE_CODIGO_LOTE.match(id_lote) is None:
        return False
    etiquetas = etiquetas_de_config(dict(config))
    if ETIQUETA_APP not in etiquetas or f"{PREFIJO_ETIQUETA_LOTE}{id_lote}" not in etiquetas:
        return False
    if leer_nota_origen(config.get("description"), id_lote).estado != EstadoNota.COINCIDE:
        return False
    return not _verdadero(config.get("template", 0))


def codigo_confirmado(escrito: str, codigo: str) -> bool:
    """V-C06: el texto escrito (sin mayúsculas ni espacios en los extremos) es el código."""
    return bool(codigo) and escrito.strip().lower() == codigo


def problema_seleccion(marcadas: int) -> str | None:
    """``"V-C09"`` si hay más de ``MAX_LOTE`` marcadas, ``"vacia"`` si ninguna, si no ``None``."""
    if marcadas > MAX_LOTE:
        return "V-C09"
    if marcadas <= 0:
        return "vacia"
    return None


def candidatos_inventario(
    detalle: DetalleLote, marcadas: Collection[int]
) -> list[CandidatoRollback]:
    """Candidatos de Deshacer: las MVs marcadas del detalle que son deshacibles.

    Sintetiza una ``EntradaLibro`` mínima (estado ``OK``, sin UPID) por MV; la regla de
    propiedad real se aplica al releer la config (``es_propia_inventario``).
    """
    elegidas = frozenset(marcadas)
    candidatos: list[CandidatoRollback] = []
    for mv in detalle.maquinas:
        r = mv.recurso
        if r.vmid not in elegidas or not mv.deshacible or r.nodo is None:
            continue
        elemento = ElementoPlan(
            indice=len(candidatos),
            nombre=r.nombre or "",
            vmid=r.vmid,
            nodo=r.nodo,
            cfg=ConfiguracionVM(vmid=r.vmid, nombre=r.nombre or "", nodo=r.nodo),
        )
        entrada = EntradaLibro(elemento, estado=EstadoMV.OK)
        candidatos.append(CandidatoRollback(entrada, True, None, False))
    return candidatos
