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
from proxlaunch.nucleo.origen.permisos import (
    RUTA_MAPEO_CPU,
    RUTA_MAPEO_PCI,
    RUTA_ZONA_GENERICA,
    estado_algun_mapeo,
    estado_cpu_personalizada,
    estado_privilegio,
    estado_sdn_fuera_de_local,
)
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
    # Fase C (0.8): filas de «Qué puedo hacer» (RF-C5.2). No son vías de origen: no entran en
    # ``vias_de_origen``.
    LOTES_SERVIDOR = "lotes_servidor"  # VM.Audit + VM.Allocate en /vms
    VNETS_SDN = "vnets_sdn"  # SDN.Use fuera de localnetwork
    FIREWALL = "firewall"  # VM.Config.Network en /vms
    FIREWALL_GENERAL = "firewall_general"  # Sys.Audit en /
    RED_CLON = "red_clon"  # VM.Config.Network en /vms
    # Fase D (0.9): filas de «Qué puedo hacer» (RF-D5.2). Siempre calculadas; no son de origen.
    ARQUITECTURA = "arquitectura"  # Sys.Audit en /nodes (9.2: siempre SI por host-arch)
    MAPEOS = "mapeos"  # Mapping.Use en alguna /mapping/{pci,usb}[/id]; None -> CON_AVISO
    CPU_PERSONALIZADA = "cpu_personalizada"  # Mapping.Use en /mapping/cpu (9.2); antes Sys.Audit


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
    Via.LOTES_SERVIDOR: "permisos_rol_ampliado",
    Via.VNETS_SDN: "permisos_rol_ampliado",
    Via.FIREWALL: "permisos_rol_ampliado",
    Via.FIREWALL_GENERAL: "permisos_rol_ampliado",
    Via.RED_CLON: "permisos_rol_ampliado",
    Via.ARQUITECTURA: "permisos_rol_ampliado",
    Via.MAPEOS: "permisos_rol_ampliado",
    Via.CPU_PERSONALIZADA: "permisos_rol_ampliado",
}


def _version(caps: Capacidades) -> str:
    return f"{caps.version[0]}.{caps.version[1]}"


def calcular_capacidades(caps: Capacidades, inv: Inventario, nodo: str | None) -> CapacidadesOrigen:
    """Estado de las vías (nueve de origen, cinco de la fase C y tres de la D) para la versión
    efectiva, el inventario y el nodo (o todo el servidor si ``nodo`` es ``None``)."""
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

    def base_importacion(via: Via) -> bool:
        if not imp:
            poner(via, Disponibilidad.NO, CodigoError.IMPORTAR_SIN_STORAGE_IMPORT,
                  candidatos=candidatos_posibles())  # fmt: skip
            return False
        return True

    if base_importacion(Via.IMPORTAR):
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
    if base_importacion(Via.SUBIR_IMAGEN) and con_privilegio(
        Via.SUBIR_IMAGEN,
        "Datastore.AllocateTemplate",
        rutas_imp,
        CodigoError.IMPORTAR_SIN_PERMISO,
    ):
        listo(Via.SUBIR_IMAGEN)
    if (
        base_importacion(Via.DESCARGAR_IMAGEN)
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

    # --- Fase C (0.8): filas de «Qué puedo hacer» (RF-C5.2) ---
    def sin_version(via: Via, funcion: Funcion) -> bool:
        """Deja la vía en ``NO`` si la versión no tiene la función; ``True`` si la deja puesta."""
        if caps.tiene(funcion):
            return False
        minima = caps.requisito(funcion)
        poner(
            via,
            Disponibilidad.NO,
            CodigoError.OPCION_SIN_VERSION,
            version=f"{minima[0]}.{minima[1]}",
            via=via.value,
        )
        return True

    def con_privilegios(via: Via, ruta: str, privilegios: tuple[str, ...]) -> None:
        estados = [estado_privilegio(permisos, p, ruta) for p in privilegios]
        if all(estados):
            poner(via, Disponibilidad.SI)
        elif any(e is None for e in estados):
            poner(via, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
        else:
            falta = privilegios[estados.index(False)]
            falta_permiso(via, falta, ruta, CodigoError.PERMISO_INSUFICIENTE)

    if not sin_version(Via.LOTES_SERVIDOR, Funcion.INVENTARIO_LOTES):
        con_privilegios(Via.LOTES_SERVIDOR, "/vms", ("VM.Audit", "VM.Allocate"))
    if not sin_version(Via.VNETS_SDN, Funcion.VNETS_SDN):
        fuera_de_local = estado_sdn_fuera_de_local(permisos)
        if fuera_de_local is None:
            poner(Via.VNETS_SDN, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
        elif fuera_de_local:
            poner(Via.VNETS_SDN, Disponibilidad.SI)
        else:
            falta_permiso(
                Via.VNETS_SDN, "SDN.Use", RUTA_ZONA_GENERICA, CodigoError.PERMISO_INSUFICIENTE
            )
    if not sin_version(Via.FIREWALL, Funcion.FIREWALL_GRUPO):
        con_privilegios(Via.FIREWALL, "/vms", ("VM.Config.Network",))
    # Leer el firewall general exige Sys.Audit; sin él solo se pierde un aviso: nunca ``NO``.
    general = estado_privilegio(permisos, "Sys.Audit", "/")
    if general:
        poner(Via.FIREWALL_GENERAL, Disponibilidad.SI)
    elif general is None:
        poner(Via.FIREWALL_GENERAL, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
    else:
        poner(
            Via.FIREWALL_GENERAL,
            Disponibilidad.CON_AVISO,
            CodigoError.PERMISO_INSUFICIENTE,
            privilegio="Sys.Audit",
            ruta="/",
            via=Via.FIREWALL_GENERAL.value,
        )
    if not sin_version(Via.RED_CLON, Funcion.REESCRIBIR_RED_CLON):
        con_privilegios(Via.RED_CLON, "/vms", ("VM.Config.Network",))

    # --- Fase D (0.9): arquitectura, mapeos y CPU personalizadas (RF-D5.2) ---
    sys_audit_nodos = estado_privilegio(permisos, "Sys.Audit", "/nodes")
    if caps.tiene(Funcion.HOST_ARCH_EN_RESOURCES) or sys_audit_nodos:
        poner(Via.ARQUITECTURA, Disponibilidad.SI)
    elif sys_audit_nodos is None:
        poner(Via.ARQUITECTURA, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
    else:
        falta_permiso(Via.ARQUITECTURA, "Sys.Audit", "/nodes", CodigoError.PERMISO_INSUFICIENTE)
    uso_mapeos = estado_algun_mapeo(permisos)
    if uso_mapeos:
        poner(Via.MAPEOS, Disponibilidad.SI)
    elif uso_mapeos is None:
        poner(Via.MAPEOS, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
    else:
        falta_permiso(Via.MAPEOS, "Mapping.Use", RUTA_MAPEO_PCI, CodigoError.PERMISO_INSUFICIENTE)
    uso_cpu = estado_cpu_personalizada(permisos, caps)
    if uso_cpu:
        poner(Via.CPU_PERSONALIZADA, Disponibilidad.SI)
    elif uso_cpu is None:
        poner(Via.CPU_PERSONALIZADA, Disponibilidad.CON_AVISO, motivo="permisos_desconocidos")
    elif caps.tiene(Funcion.CPU_PERSONALIZADA_POR_MAPPING):
        falta_permiso(
            Via.CPU_PERSONALIZADA, "Mapping.Use", RUTA_MAPEO_CPU, CodigoError.PERMISO_INSUFICIENTE
        )
    else:
        falta = (
            "Sys.Audit"
            if not estado_privilegio(permisos, "Sys.Audit", "/nodes")
            else "VM.Config.CPU"
        )
        ruta = "/nodes" if falta == "Sys.Audit" else "/vms"
        falta_permiso(Via.CPU_PERSONALIZADA, falta, ruta, CodigoError.PERMISO_INSUFICIENTE)
    return CapacidadesOrigen(caps.version, caps.forzada, nodo, vias)
