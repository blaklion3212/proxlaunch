"""Disponibilidad de las opciones de la fase B según permisos, versión y plantilla (DT-B6). Puro.

Mismo patrón que ``opciones.disponibilidad``: la versión se mira antes que el privilegio;
permisos desconocidos (``None``) = habilitada; la zona de incertidumbre 9.0–9.1 de cloud-init y
``cicustom`` en 8.x (``Datastore.Allocate`` no verificado) = ``CON_AVISO``. La interfaz solo
pinta el resultado.

``params`` de cada estado: ``opcion`` y, según el caso, ``privilegio``, ``ruta``, ``version``,
``alternativo`` y ``motivo`` (``sin_unidad``, ``unidad_desconocida``, ``windows``,
``version_incierta``, ``no_verificado``, ``sin_storage_snippets``, ``agente_ya_activo``).
"""

from __future__ import annotations

from enum import StrEnum

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.cloudinit.modelos import INFO_DESCONOCIDA, InfoCloudInitPlantilla
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.origen.permisos import (
    estado_privilegio,
    privilegios_agente,
    privilegios_cloudinit,
)

RUTA_VMS = "/vms"
RUTA_STORAGE = "/storage"
PRIVILEGIO_CLOUDINIT = "VM.Config.Cloudinit"
PRIVILEGIO_RED = "VM.Config.Network"
PRIVILEGIO_OPCIONES = "VM.Config.Options"
PRIVILEGIO_STORAGE_AUDIT = "Datastore.Audit"
PRIVILEGIO_STORAGE_USAR = "Datastore.AllocateSpace"
PRIVILEGIO_STORAGE_8X = "Datastore.Allocate"


class OpcionB(StrEnum):
    """Opciones de la fase B cuya disponibilidad depende de permisos, versión o plantilla."""

    CLOUDINIT = "cloudinit"
    CONTRASENA = "contrasena"
    DNS_DOMINIO = "dns_dominio"
    SNIPPETS = "snippets"
    ESPERAR_IP = "esperar_ip"
    ACTIVAR_AGENTE = "activar_agente"


def _si(opcion: OpcionB) -> EstadoOpcion:
    return EstadoOpcion(opcion, Disponibilidad.SI)


def _sin_version(opcion: OpcionB, caps: Capacidades, funcion: Funcion) -> EstadoOpcion:
    minima = caps.requisito(funcion)
    return EstadoOpcion(
        opcion,
        Disponibilidad.NO,
        CodigoError.OPCION_SIN_VERSION,
        {"opcion": opcion.value, "version": f"{minima[0]}.{minima[1]}"},
    )


def _sin_privilegio(
    opcion: OpcionB, privilegio: str, ruta: str, *, alternativo: str = ""
) -> EstadoOpcion:
    params = {"opcion": opcion.value, "privilegio": privilegio, "ruta": ruta}
    if alternativo:
        params["alternativo"] = alternativo
    return EstadoOpcion(opcion, Disponibilidad.NO, CodigoError.OPCION_SIN_PRIVILEGIO, params)


def _con_aviso(opcion: OpcionB, privilegio: str, ruta: str, motivo: str) -> EstadoOpcion:
    return EstadoOpcion(
        opcion,
        Disponibilidad.CON_AVISO,
        CodigoError.OPCION_SIN_PRIVILEGIO,
        {"opcion": opcion.value, "privilegio": privilegio, "ruta": ruta, "motivo": motivo},
    )


def estado_permisos_cloudinit(
    permisos: PermisosEfectivos | None,
    caps: Capacidades,
    opcion: OpcionB = OpcionB.CLOUDINIT,
    *,
    solo_red_basta: bool = False,
) -> EstadoOpcion:
    """Privilegio para aplicar cloud-init (RF-B5.3), sin mirar la plantilla.

    8.x: basta ``VM.Config.Cloudinit`` o ``VM.Config.Network``. 9.0–9.1 (incierto): con solo
    ``Network`` se habilita con aviso. Desde 9.2: ``Cloudinit``. ``solo_red_basta`` (DNS y
    dominio) acepta ``Network`` siempre y sin aviso.
    """
    if not caps.tiene(Funcion.CLOUDINIT):
        return _sin_version(opcion, caps, Funcion.CLOUDINIT)
    tiene_ci = estado_privilegio(permisos, PRIVILEGIO_CLOUDINIT, RUTA_VMS)
    tiene_red = estado_privilegio(permisos, PRIVILEGIO_RED, RUTA_VMS)
    if tiene_ci is None or tiene_red is None:
        return _si(opcion)  # permisos desconocidos
    if tiene_ci:
        return _si(opcion)
    if solo_red_basta:
        if tiene_red:
            return _si(opcion)
        return _sin_privilegio(opcion, PRIVILEGIO_CLOUDINIT, RUTA_VMS, alternativo=PRIVILEGIO_RED)
    aceptables = privilegios_cloudinit(caps)
    if PRIVILEGIO_RED in aceptables and tiene_red:
        if caps.tiene(Funcion.CLOUDINIT_PRIVILEGIO_INCIERTO):
            return _con_aviso(opcion, PRIVILEGIO_CLOUDINIT, RUTA_VMS, "version_incierta")
        return _si(opcion)
    alternativo = PRIVILEGIO_RED if PRIVILEGIO_RED in aceptables else ""
    return _sin_privilegio(opcion, PRIVILEGIO_CLOUDINIT, RUTA_VMS, alternativo=alternativo)


def estado_permisos_snippets(permisos: PermisosEfectivos | None, caps: Capacidades) -> EstadoOpcion:
    """Privilegios de B4 (RF-B5.3): listar (``Audit`` o ``AllocateSpace``) y usar ``cicustom``.

    9.x pide ``AllocateSpace``; 8.x, ``Allocate`` (no verificado): con solo ``AllocateSpace``
    se habilita con aviso.
    """
    opcion = OpcionB.SNIPPETS
    if not caps.tiene(Funcion.SNIPPETS_CICUSTOM):
        return _sin_version(opcion, caps, Funcion.SNIPPETS_CICUSTOM)
    audit = estado_privilegio(permisos, PRIVILEGIO_STORAGE_AUDIT, RUTA_STORAGE)
    espacio = estado_privilegio(permisos, PRIVILEGIO_STORAGE_USAR, RUTA_STORAGE)
    if audit is False and espacio is False:
        return _sin_privilegio(opcion, PRIVILEGIO_STORAGE_AUDIT, RUTA_STORAGE)
    if caps.tiene(Funcion.CICUSTOM_CON_ALLOCATESPACE):
        if espacio is False:
            return _sin_privilegio(opcion, PRIVILEGIO_STORAGE_USAR, RUTA_STORAGE)
        return _si(opcion)
    allocate = estado_privilegio(permisos, PRIVILEGIO_STORAGE_8X, RUTA_STORAGE)
    if allocate is False:
        if espacio is False:
            return _sin_privilegio(opcion, PRIVILEGIO_STORAGE_8X, RUTA_STORAGE)
        return _con_aviso(opcion, PRIVILEGIO_STORAGE_8X, RUTA_STORAGE, "no_verificado")
    return _si(opcion)


def estado_permisos_agente(permisos: PermisosEfectivos | None, caps: Capacidades) -> EstadoOpcion:
    """Privilegio para sondear el agente (V-B63): ``VM.Monitor`` (8.x) o ``VM.GuestAgent.Audit``
    / ``Unrestricted`` (9.x)."""
    opcion = OpcionB.ESPERAR_IP
    if not caps.tiene(Funcion.AGENTE_IP):
        return _sin_version(opcion, caps, Funcion.AGENTE_IP)
    aceptables = privilegios_agente(caps)
    estados = [estado_privilegio(permisos, p, RUTA_VMS) for p in aceptables]
    if any(e is None for e in estados) or any(estados):
        return _si(opcion)
    return _sin_privilegio(opcion, aceptables[0], RUTA_VMS)


def _peor(base: EstadoOpcion, opcion: OpcionB) -> EstadoOpcion:
    """Reetiqueta el estado de otra opción de la que depende (misma disponibilidad y motivo)."""
    params = dict(base.params)
    params["opcion"] = opcion.value
    return EstadoOpcion(opcion, base.disponibilidad, base.codigo, params)


def disponibilidad_fase_b(
    permisos: PermisosEfectivos | None,
    caps: Capacidades,
    info: InfoCloudInitPlantilla | None,
    hay_storage_snippets: bool,
) -> dict[OpcionB, EstadoOpcion]:
    """Estado de cada opción de la fase B.

    ``info`` ``None`` = plantilla desconocida (habilitada con aviso, V-B20). Windows bloquea la
    contraseña (V-B25). Sin unidad se bloquean todas las de cloud-init. ``ESPERAR_IP`` solo
    depende de la versión y del privilegio del agente.
    """
    info = INFO_DESCONOCIDA if info is None else info
    estados: dict[OpcionB, EstadoOpcion] = {}

    ci = estado_permisos_cloudinit(permisos, caps)
    if ci.disponibilidad != Disponibilidad.NO:
        if info.unidad is False:
            ci = EstadoOpcion(
                OpcionB.CLOUDINIT,
                Disponibilidad.NO,
                CodigoError.CLOUDINIT_SIN_UNIDAD,
                {"opcion": OpcionB.CLOUDINIT.value, "motivo": "sin_unidad"},
            )
        elif info.unidad is None and ci.disponibilidad == Disponibilidad.SI:
            ci = EstadoOpcion(
                OpcionB.CLOUDINIT,
                Disponibilidad.CON_AVISO,
                None,
                {"opcion": OpcionB.CLOUDINIT.value, "motivo": "unidad_desconocida"},
            )
    estados[OpcionB.CLOUDINIT] = ci

    if ci.disponibilidad == Disponibilidad.NO:
        estados[OpcionB.CONTRASENA] = _peor(ci, OpcionB.CONTRASENA)
    elif info.es_windows:
        estados[OpcionB.CONTRASENA] = EstadoOpcion(
            OpcionB.CONTRASENA,
            Disponibilidad.NO,
            None,
            {"opcion": "contrasena", "motivo": "windows"},
        )
    else:
        estados[OpcionB.CONTRASENA] = _peor(ci, OpcionB.CONTRASENA)

    # DNS y dominio: basta ``Network`` en cualquier versión; solo les afecta la falta de unidad.
    dns = estado_permisos_cloudinit(permisos, caps, OpcionB.DNS_DOMINIO, solo_red_basta=True)
    if dns.disponibilidad != Disponibilidad.NO and ci.codigo == CodigoError.CLOUDINIT_SIN_UNIDAD:
        dns = _peor(ci, OpcionB.DNS_DOMINIO)
    elif dns.disponibilidad == Disponibilidad.SI and info.unidad is None:
        dns = EstadoOpcion(
            OpcionB.DNS_DOMINIO,
            Disponibilidad.CON_AVISO,
            None,
            {"opcion": "dns_dominio", "motivo": "unidad_desconocida"},
        )
    estados[OpcionB.DNS_DOMINIO] = dns

    sn = estado_permisos_snippets(permisos, caps)
    if sn.disponibilidad != Disponibilidad.NO:
        if ci.disponibilidad == Disponibilidad.NO:
            sn = _peor(ci, OpcionB.SNIPPETS)
        elif not hay_storage_snippets:
            sn = EstadoOpcion(
                OpcionB.SNIPPETS,
                Disponibilidad.NO,
                None,
                {"opcion": "snippets", "motivo": "sin_storage_snippets"},
            )
        elif (
            sn.disponibilidad == Disponibilidad.SI and ci.disponibilidad == Disponibilidad.CON_AVISO
        ):
            sn = _peor(ci, OpcionB.SNIPPETS)
    estados[OpcionB.SNIPPETS] = sn

    estados[OpcionB.ESPERAR_IP] = estado_permisos_agente(permisos, caps)

    # ``agent=1`` viaja en el PUT de cloud-init y necesita VM.Config.Options.
    if ci.disponibilidad == Disponibilidad.NO:
        estados[OpcionB.ACTIVAR_AGENTE] = _peor(ci, OpcionB.ACTIVAR_AGENTE)
    elif estado_privilegio(permisos, PRIVILEGIO_OPCIONES, RUTA_VMS) is False:
        estados[OpcionB.ACTIVAR_AGENTE] = _sin_privilegio(
            OpcionB.ACTIVAR_AGENTE, PRIVILEGIO_OPCIONES, RUTA_VMS
        )
    elif info.agente is True:
        estados[OpcionB.ACTIVAR_AGENTE] = EstadoOpcion(
            OpcionB.ACTIVAR_AGENTE,
            Disponibilidad.NO,
            None,
            {"opcion": "activar_agente", "motivo": "agente_ya_activo"},
        )
    else:
        estados[OpcionB.ACTIVAR_AGENTE] = _si(OpcionB.ACTIVAR_AGENTE)
    return estados
