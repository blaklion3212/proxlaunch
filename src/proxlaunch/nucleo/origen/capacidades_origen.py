"""Capacidades de origen del SO: qué vías están disponibles y por qué no (RF-O02). Puro, sin E/S.

Combina la versión (solo por ``caps.tiene``, CA-09.6), los permisos efectivos (RF-O24), los
storages por contenido (RF-O04) y las plantillas ya leídas. Usa solo datos ya leídos (INV-M1).
Un permiso desconocido deja la vía ``CON_AVISO``, salvo ``ORDEN_ARRANQUE`` y ``AMPLIAR_DISCO``,
que pasan a ``NO`` (INV-O10). Los privilegios nuevos se evalúan por vía: el rol de 10 privilegios
del MVP 3 solo deja deshabilitadas las vías que de verdad necesitan los nuevos (CA-O24.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import Contenido, PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.origen.storages import candidatos, candidatos_servidor, podria_admitir


class Via(StrEnum):
    ISO = "iso"
    SUBIR_ISO = "subir_iso"
    DESCARGAR_URL = "descargar_url"
    IMPORTAR = "importar"
    SUBIR_IMAGEN = "subir_imagen"
    DESCARGAR_IMAGEN = "descargar_imagen"
    CLONAR = "clonar"
    ORDEN_ARRANQUE = "orden_arranque"
    AMPLIAR_DISCO = "ampliar_disco"


class Disponibilidad(StrEnum):
    SI = "si"
    NO = "no"
    CON_AVISO = "con_aviso"


@dataclass(frozen=True)
class EstadoVia:
    """Estado de una vía. ``params`` puede llevar version, privilegio, ruta, candidatos, nodo,
    motivo (p. ej. ``sin_storage_iso``, ``permisos_desconocidos``)."""

    via: Via
    disponibilidad: Disponibilidad
    codigo: CodigoError | None = None
    params: dict[str, str] = field(default_factory=dict)
    id_ayuda: str = ""


@dataclass(frozen=True)
class CapacidadesOrigen:
    version: tuple[int, int]
    forzada: bool
    nodo: str | None
    vias: Mapping[Via, EstadoVia]

    def estado(self, via: Via) -> EstadoVia:
        return self.vias[via]

    def disponible(self, via: Via) -> bool:
        """Se ofrece (con o sin aviso)."""
        return self.vias[via].disponibilidad != Disponibilidad.NO


def vias_de_origen(origen: OrigenSO) -> tuple[Via, ...]:
    """Vías imprescindibles de cada origen (el orden de arranque es opcional y no cuenta)."""
    return {
        OrigenSO.ISO: (Via.ISO,),
        OrigenSO.IMPORTAR_DISCO: (Via.IMPORTAR,),
        OrigenSO.CLONAR_PLANTILLA: (Via.CLONAR,),
    }.get(origen, ())


_AYUDA = {
    Via.ISO: "iso",
    Via.SUBIR_ISO: "subir",
    Via.DESCARGAR_URL: "descargar_url",
    Via.IMPORTAR: "importar",
    Via.SUBIR_IMAGEN: "subir",
    Via.DESCARGAR_IMAGEN: "descargar_url",
    Via.CLONAR: "plantilla",
    Via.ORDEN_ARRANQUE: "permisos_rol_ampliado",
    Via.AMPLIAR_DISCO: "permisos_rol_ampliado",
}


def _version(caps: Capacidades) -> str:
    return f"{caps.version[0]}.{caps.version[1]}"


def calcular_capacidades(caps: Capacidades, inv: Inventario, nodo: str | None) -> CapacidadesOrigen:
    """Estado de las nueve vías para la versión efectiva, el inventario y el nodo (o todo el
    servidor si ``nodo`` es ``None``)."""
    permisos: PermisosEfectivos | None = None if inv.catalogo is None else inv.catalogo.permisos
    nodos = [n.nombre for n in inv.topologia.nodos] if nodo is None else [nodo]
    vias: dict[Via, EstadoVia] = {}

    def poner(
        v: Via,
        disp: Disponibilidad,
        codigo: CodigoError | None = None,
        **params: str,
    ) -> None:
        vias[v] = EstadoVia(v, disp, codigo, dict(params), _AYUDA[v])

    def ids(contenido: Contenido) -> list[str]:
        if nodo is None:
            return list(candidatos_servidor(inv, contenido))
        return [s.id for s in candidatos(inv, contenido, nodo)]

    def falta_permiso(via: Via, privilegio: str, ruta: str, codigo: CodigoError) -> None:
        poner(via, Disponibilidad.NO, codigo, privilegio=privilegio, ruta=ruta, via=via.value)

    def con_privilegio(via: Via, privilegio: str, rutas: list[str], codigo: CodigoError) -> bool:
        """True si hay certeza de que se tiene en alguna ruta; si no, deja el estado puesto."""
        estados = [estado_privilegio(permisos, privilegio, r) for r in rutas]
        if permisos is None:
            poner(via, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
            return False
        if any(estados):
            return True
        falta_permiso(via, privilegio, rutas[0], codigo)
        return False

    def listo(via: Via) -> None:
        if via not in vias:
            poner(via, Disponibilidad.SI)

    # --- ISO y subida de ISO ---
    iso = ids(Contenido.ISO)
    rutas_iso = [f"/storage/{s}" for s in iso]
    if not iso:
        poner(Via.ISO, Disponibilidad.NO, None, motivo="sin_storage_iso")
        poner(Via.SUBIR_ISO, Disponibilidad.NO, None, motivo="sin_storage_iso")
    else:
        poner(Via.ISO, Disponibilidad.SI)
        if con_privilegio(
            Via.SUBIR_ISO,
            "Datastore.AllocateTemplate",
            rutas_iso,
            CodigoError.PERMISO_INSUFICIENTE,
        ):
            listo(Via.SUBIR_ISO)

    # --- Descarga por URL (ISO e imagen) ---
    def red_ok(via: Via) -> bool:
        if caps.tiene(Funcion.DESCARGAR_URL):
            rutas = [f"/nodes/{n}" for n in nodos]
            if permisos is None:
                poner(via, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
                return False
            if any(
                estado_privilegio(permisos, "Sys.AccessNetwork", r)
                or estado_privilegio(permisos, "Sys.Modify", "/")
                for r in rutas
            ):
                return True
            poner(
                via,
                Disponibilidad.NO,
                CodigoError.DESCARGA_URL_SIN_PERMISO,
                version=_version(caps),
                nodo=nodos[0] if nodos else "",
                privilegio="Sys.AccessNetwork",
            )
            return False
        if permisos is None:
            poner(via, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
            return False
        if estado_privilegio(permisos, "Sys.Modify", "/"):
            return True
        poner(
            via,
            Disponibilidad.NO,
            CodigoError.DESCARGA_URL_SIN_PERMISO,
            version=_version(caps),
            privilegio="Sys.Modify",
        )
        return False

    if not iso:
        poner(Via.DESCARGAR_URL, Disponibilidad.NO, None, motivo="sin_storage_iso")
    elif (
        red_ok(Via.DESCARGAR_URL)
        and estado_privilegio(permisos, "Datastore.AllocateTemplate", rutas_iso[0]) is not False
    ):
        poner(Via.DESCARGAR_URL, Disponibilidad.SI)
    elif Via.DESCARGAR_URL not in vias:
        falta_permiso(
            Via.DESCARGAR_URL,
            "Datastore.AllocateTemplate",
            rutas_iso[0],
            CodigoError.PERMISO_INSUFICIENTE,
        )

    # --- Importación (E-O01, E-O02, E-O12) ---
    imp = ids(Contenido.IMPORT)
    rutas_imp = [f"/storage/{s}" for s in imp]

    def candidatos_posibles() -> str:
        tipos = {
            s.id
            for n in inv.storages_todos
            for s in inv.storages_todos[n]
            if podria_admitir(s.tipo, Contenido.IMPORT)
            and Contenido.IMPORT.value not in s.contenido
        }
        return ",".join(sorted(tipos))

    def base_importacion(via: Via, funcion: Funcion) -> bool:
        if not caps.tiene(funcion):
            poner(via, Disponibilidad.NO, CodigoError.IMPORTAR_VERSION_NO_SOPORTADA,
                  version=_version(caps))  # fmt: skip
            return False
        if not imp:
            poner(via, Disponibilidad.NO, CodigoError.IMPORTAR_SIN_STORAGE_IMPORT,
                  candidatos=candidatos_posibles())  # fmt: skip
            return False
        return True

    if base_importacion(Via.IMPORTAR, Funcion.IMPORTAR_DISCO):
        lectura_ok = permisos is None or any(
            estado_privilegio(permisos, p, r)
            for r in rutas_imp
            for p in ("Datastore.AllocateSpace", "Datastore.Audit")
        )
        if permisos is None:
            poner(Via.IMPORTAR, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
        elif not lectura_ok:
            poner(
                Via.IMPORTAR,
                Disponibilidad.NO,
                CodigoError.IMPORTAR_SIN_PERMISO,
                privilegio="Datastore.AllocateSpace",
                ruta=rutas_imp[0],
                via=Via.IMPORTAR.value,
            )
        else:
            poner(Via.IMPORTAR, Disponibilidad.SI)
    if base_importacion(Via.SUBIR_IMAGEN, Funcion.SUBIR_IMAGEN_DISCO) and con_privilegio(
        Via.SUBIR_IMAGEN,
        "Datastore.AllocateTemplate",
        rutas_imp,
        CodigoError.IMPORTAR_SIN_PERMISO,
    ):
        listo(Via.SUBIR_IMAGEN)
    if (
        base_importacion(Via.DESCARGAR_IMAGEN, Funcion.SUBIR_IMAGEN_DISCO)
        and red_ok(Via.DESCARGAR_IMAGEN)
        and estado_privilegio(permisos, "Datastore.AllocateTemplate", rutas_imp[0]) is not False
    ):
        listo(Via.DESCARGAR_IMAGEN)
    elif Via.DESCARGAR_IMAGEN not in vias:
        falta_permiso(
            Via.DESCARGAR_IMAGEN,
            "Datastore.AllocateTemplate",
            rutas_imp[0],
            CodigoError.IMPORTAR_SIN_PERMISO,
        )

    # --- Clonar (E-O17) ---
    plantillas = None if inv.catalogo is None else inv.catalogo.plantillas
    if plantillas is not None and not plantillas:
        poner(Via.CLONAR, Disponibilidad.NO, CodigoError.SIN_PLANTILLAS)
    elif permisos is None:
        poner(Via.CLONAR, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
    elif plantillas and not any(
        estado_privilegio(permisos, "VM.Clone", f"/vms/{p.vmid}") for p in plantillas
    ):
        falta_permiso(
            Via.CLONAR,
            "VM.Clone",
            f"/vms/{plantillas[0].vmid}",
            CodigoError.PERMISO_INSUFICIENTE,
        )
    else:
        poner(Via.CLONAR, Disponibilidad.SI)

    # --- Parámetros opcionales que exigen VM.Config.Disk (INV-O10) ---
    for via in (Via.ORDEN_ARRANQUE, Via.AMPLIAR_DISCO):
        estado = estado_privilegio(permisos, "VM.Config.Disk", "/vms")
        if estado:
            poner(via, Disponibilidad.SI)
        else:
            poner(
                via,
                Disponibilidad.NO,
                CodigoError.PERMISO_INSUFICIENTE,
                privilegio="VM.Config.Disk",
                ruta="/vms",
                via=via.value,
                desconocido="1" if estado is None else "0",
            )
    return CapacidadesOrigen(caps.version, caps.forzada, nodo, vias)
