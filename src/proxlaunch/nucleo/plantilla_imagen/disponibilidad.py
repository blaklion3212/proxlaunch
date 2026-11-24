"""Disponibilidad de cada control del asistente B2 según versión, permisos y almacenamientos
(RF-B0.3, RF-B0.4, RF-B2.1, RF-B2.2, RF-B2.7, RF-B2.8, RF-B5.4). Puro: la interfaz solo pinta.

Mismo patrón que ``opciones.disponibilidad``: la versión se mira antes que el privilegio y los
permisos desconocidos (``None``) no deshabilitan nada. Cada ``EstadoControlB2`` lleva el
``CodigoError`` y los ``params`` que la interfaz traduce a la explicación; el resto del asistente
sigue funcionando aunque un control esté deshabilitado.

``params`` según el caso: ``control``, ``privilegio``, ``ruta``, ``version``, ``motivo``
(``sin_import``, ``sin_images``, ``permisos_desconocidos``), ``alternativo``.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.cloudinit.disponibilidad import estado_permisos_cloudinit
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor, Contenido, PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.origen.capacidades_origen import (
    Disponibilidad,
    EstadoVia,
    Via,
    calcular_capacidades,
)
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.origen.storages import candidatos

RUTA_VMS = "/vms"
PRIVILEGIO_HWTYPE = "VM.Config.HWType"
PRIVILEGIO_OPCIONES = "VM.Config.Options"
PRIVILEGIO_DISCO = "VM.Config.Disk"
PRIVILEGIO_ASIGNAR = "VM.Allocate"


class ControlB2(StrEnum):
    """Controles del asistente cuya disponibilidad se calcula."""

    ASISTENTE = "asistente"  # el punto de entrada (versión + contenido ``import``)
    ORIGEN_ARCHIVO = "origen_archivo"  # subir un archivo local
    ORIGEN_URL = "origen_url"  # que el servidor descargue una URL
    ORIGEN_YA_IMPORTADA = "origen_ya_importada"  # «Usar una imagen ya importada» (Podría)
    CONSOLA_SERIE = "consola_serie"  # serial0=socket y vga=serial0
    UNIDAD_CLOUDINIT = "unidad_cloudinit"  # ide2=<destino>:cloudinit
    AGENTE = "agente"  # agent=1
    VALORES_CLOUDINIT = "valores_cloudinit"  # sección «Valores de cloud-init» (RF-B2.8)
    CONVERTIR = "convertir"  # POST …/template
    BORRAR = "borrar"  # «Borrar la máquina a medio crear»


@dataclass(frozen=True)
class EstadoControlB2:
    control: ControlB2
    disponibilidad: Disponibilidad
    codigo: CodigoError | None = None
    params: dict[str, str] = field(default_factory=dict)

    @property
    def habilitado(self) -> bool:
        """Se ofrece (con o sin aviso)."""
        return self.disponibilidad != Disponibilidad.NO


DisponibilidadB2 = dict[ControlB2, EstadoControlB2]


def _si(control: ControlB2) -> EstadoControlB2:
    return EstadoControlB2(control, Disponibilidad.SI)


def _privilegio(
    control: ControlB2, permisos: PermisosEfectivos | None, privilegio: str, ruta: str
) -> EstadoControlB2:
    """Habilitado salvo que se SEPA que falta el privilegio (``None`` = desconocido)."""
    if estado_privilegio(permisos, privilegio, ruta) is False:
        return EstadoControlB2(
            control,
            Disponibilidad.NO,
            CodigoError.OPCION_SIN_PRIVILEGIO,
            {"control": control.value, "privilegio": privilegio, "ruta": ruta},
        )
    return _si(control)


def _de_via(control: ControlB2, via: EstadoVia) -> EstadoControlB2:
    """Traduce el estado de una vía de origen (subir/descargar/importar) a un control de B2.

    Con permisos desconocidos la vía ya viene como ``CON_AVISO``: no se deshabilita.
    """
    return EstadoControlB2(
        control, via.disponibilidad, via.codigo, {"control": control.value, **via.params}
    )


def disponibilidad_plantilla_imagen(
    permisos: PermisosEfectivos | None, caps: Capacidades, inv: Inventario, nodo: str
) -> DisponibilidadB2:
    """Estado de cada control para el ``nodo`` elegido (RF-B2.1, RF-B5.4).

    - ``ASISTENTE``: versión ≥ 8.4 con importar y subir o descargar (V-B01) y algún
      almacenamiento activo con ``import`` en el nodo (CA-B2.1.2, ``PLANTILLA_IMAGEN_SIN_IMPORT``).
    - ``ORIGEN_ARCHIVO`` / ``ORIGEN_URL``: ``Datastore.AllocateTemplate`` (la URL, además de
      ``Sys.AccessNetwork`` o ``Sys.Modify``); sin ello se explica y se ofrece usar una imagen ya
      importada (CA-B5.4.1).
    - ``CONSOLA_SERIE`` (``VM.Config.HWType``), ``AGENTE`` (``VM.Config.Options``),
      ``UNIDAD_CLOUDINIT`` (``VM.Config.Disk``), ``CONVERTIR`` y ``BORRAR`` (``VM.Allocate``).
    - ``VALORES_CLOUDINIT``: privilegio de cloud-init de la versión (RF-B2.8).
    """
    # ``calcular_capacidades`` lee los permisos del catálogo del inventario: se alinean.
    catalogo = inv.catalogo
    if catalogo is None or catalogo.permisos is not permisos:
        base = catalogo if catalogo is not None else CatalogoServidor()
        inv = dataclasses.replace(inv, catalogo=dataclasses.replace(base, permisos=permisos))
    vias = calcular_capacidades(caps, inv, nodo)
    estados: DisponibilidadB2 = {}

    if not candidatos(inv, Contenido.IMPORT, nodo):
        estados[ControlB2.ASISTENTE] = EstadoControlB2(
            ControlB2.ASISTENTE,
            Disponibilidad.NO,
            CodigoError.PLANTILLA_IMAGEN_SIN_IMPORT,
            {"control": ControlB2.ASISTENTE.value, "motivo": "sin_import", "nodo": nodo},
        )
    else:
        estados[ControlB2.ASISTENTE] = _si(ControlB2.ASISTENTE)

    estados[ControlB2.ORIGEN_ARCHIVO] = _de_via(
        ControlB2.ORIGEN_ARCHIVO, vias.estado(Via.SUBIR_IMAGEN)
    )
    estados[ControlB2.ORIGEN_URL] = _de_via(ControlB2.ORIGEN_URL, vias.estado(Via.DESCARGAR_IMAGEN))
    estados[ControlB2.ORIGEN_YA_IMPORTADA] = _de_via(
        ControlB2.ORIGEN_YA_IMPORTADA, vias.estado(Via.IMPORTAR)
    )
    estados[ControlB2.CONSOLA_SERIE] = _privilegio(
        ControlB2.CONSOLA_SERIE, permisos, PRIVILEGIO_HWTYPE, RUTA_VMS
    )
    estados[ControlB2.AGENTE] = _privilegio(
        ControlB2.AGENTE, permisos, PRIVILEGIO_OPCIONES, RUTA_VMS
    )
    estados[ControlB2.UNIDAD_CLOUDINIT] = _privilegio(
        ControlB2.UNIDAD_CLOUDINIT, permisos, PRIVILEGIO_DISCO, RUTA_VMS
    )
    ci = estado_permisos_cloudinit(permisos, caps)
    estados[ControlB2.VALORES_CLOUDINIT] = EstadoControlB2(
        ControlB2.VALORES_CLOUDINIT,
        ci.disponibilidad,
        ci.codigo,
        {"control": ControlB2.VALORES_CLOUDINIT.value, **ci.params},
    )
    estados[ControlB2.CONVERTIR] = _privilegio(
        ControlB2.CONVERTIR, permisos, PRIVILEGIO_ASIGNAR, RUTA_VMS
    )
    estados[ControlB2.BORRAR] = _privilegio(
        ControlB2.BORRAR, permisos, PRIVILEGIO_ASIGNAR, RUTA_VMS
    )
    return estados
