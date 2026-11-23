"""Reglas V-B20..V-B56 de cloud-init y snippets (arquitectura de la fase B, §4). Puro.

``validar_cloudinit`` lo llama ``nucleo.validacion.validar_vm`` al final, de modo que una MV
individual y un lote validan igual. Lo que necesita datos de la plantilla sale de
``cfg.info_cloudinit`` (calculado por ``preparar_elemento``); lo que necesita datos del servidor
(storages, permisos) sale de ``inv`` y de ``inv.catalogo``. Las reglas de lote V-B30, V-B31 y
V-B38 están en ``cloudinit.serie`` y V-B51/V-B52, en el planificador.

Los ``params`` nunca llevan contraseñas, claves ni líneas completas (CA-B14.1). Todas las
reglas usan su identificador como ``Problema.codigo``; la severidad y ``params["motivo"]``
distinguen los casos.
"""

from __future__ import annotations

import re

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.cloudinit.claves import MotivoClave, analizar_claves
from proxlaunch.nucleo.cloudinit.codigos import CODIGOS_CLOUDINIT_SIN_SERVIDOR
from proxlaunch.nucleo.cloudinit.deteccion import es_windows
from proxlaunch.nucleo.cloudinit.disponibilidad import (
    OpcionB,
    estado_permisos_agente,
    estado_permisos_cloudinit,
    estado_permisos_snippets,
)
from proxlaunch.nucleo.cloudinit.modelos import (
    INFO_DESCONOCIDA,
    MAX_TARJETAS,
    ConfigCloudInit,
    InfoCloudInitPlantilla,
    ModoTarjeta,
)
from proxlaunch.nucleo.cloudinit.red import (
    MotivoRed,
    dominio_valido,
    motivo_cidr,
    motivo_puerta,
    normalizar_dns,
)
from proxlaunch.nucleo.cloudinit.snippets import volid_snippet_valido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, DetalleClon, OrigenSO
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.red.modelos import AccionTarjeta, RedClon, usa_red_clon
from proxlaunch.nucleo.red.tarjetas import tarjetas_finales
from proxlaunch.nucleo.validacion import Problema, Severidad

__all__ = [
    "CODIGOS_CLOUDINIT_SIN_SERVIDOR",
    "MAX_CONTRASENA",
    "MIN_CONTRASENA",
    "validar_cloudinit",
    "validar_contrasena",
]

MAX_CONTRASENA = 128
MIN_CONTRASENA = 8
MAX_DNS_SIN_AVISO = 3

_RE_USUARIO_PROHIBIDO = re.compile(r"[\s:\x00-\x1f\x7f-\x9f]")
_RE_USUARIO_TIPICO = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_MOTIVOS_V_B22 = frozenset(
    {
        MotivoClave.TIPO_DESCONOCIDO,
        MotivoClave.SIN_CUERPO,
        MotivoClave.BASE64,
        MotivoClave.CON_OPCIONES,
    }
)


def _error(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.ERROR, dict(params))


def _aviso(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.AVISO, dict(params))


def validar_contrasena(
    valor: str, repeticion: str, info: InfoCloudInitPlantilla | None
) -> list[Problema]:
    """V-B25 sobre el texto escrito (la interfaz y el CSV lo llaman ANTES de crear el ``Secreto``).

    Dos campos vacíos = sin contraseña (nada que validar). Errores: no coincide con la
    repetición, saltos de línea o controles, más de 128 caracteres, menos de 8 (B1: ya no es un
    aviso) o plantilla Windows. Los ``params`` solo llevan el motivo, nunca el valor.
    """
    campo = "cloudinit.contrasena"
    if not valor and not repeticion:
        return []
    p: list[Problema] = []
    if valor != repeticion:
        p.append(_error(campo, "V-B25", motivo="no_coincide"))
    if _RE_CONTROL.search(valor):
        p.append(_error(campo, "V-B25", motivo="control"))
    if len(valor) > MAX_CONTRASENA:
        p.append(_error(campo, "V-B25", motivo="larga"))
    elif valor and len(valor) < MIN_CONTRASENA:
        p.append(_error(campo, "V-B25", motivo="corta"))
    if info is not None and info.es_windows:
        p.append(_error(campo, "V-B25", motivo="windows"))
    return p


def _nombre_plantilla(cfg: ConfiguracionVM) -> str:
    detalle = cfg.detalle_origen
    return detalle.plantilla.nombre if isinstance(detalle, DetalleClon) else ""


def _validar_usuario(ci: ConfigCloudInit, p: list[Problema]) -> None:
    if not ci.usuario:
        return
    if _RE_USUARIO_PROHIBIDO.search(ci.usuario):
        p.append(_error("cloudinit.usuario", "V-B21", motivo="caracteres"))
    elif not _RE_USUARIO_TIPICO.fullmatch(ci.usuario):
        p.append(_aviso("cloudinit.usuario", "V-B21", motivo="patron"))


def _validar_claves(ci: ConfigCloudInit, p: list[Problema]) -> None:
    if not ci.claves:
        return
    campo = "cloudinit.claves"
    resultado = analizar_claves("\n".join(ci.claves))
    for problema in resultado.problemas:
        if problema.motivo == MotivoClave.CLAVE_PRIVADA:
            p.append(_error(campo, "V-B23"))
        elif problema.motivo in _MOTIVOS_V_B22:
            p.append(
                _error(campo, "V-B22", linea=str(problema.linea), motivo=problema.motivo.value)
            )
        else:
            p.append(_error(campo, "V-B24", motivo=problema.motivo.value))
    if resultado.duplicadas:
        p.append(_aviso(campo, "V-B24", motivo="duplicadas", cantidad=str(resultado.duplicadas)))


def _se_quita(red_clon: RedClon | None, indice: int) -> bool:
    """``True`` si la red del clon quita la tarjeta ``indice`` (el aviso es V-C16)."""
    if red_clon is None or not usa_red_clon(red_clon):
        return False
    pedido = red_clon.tarjeta(indice)
    return pedido is not None and pedido.accion == AccionTarjeta.QUITAR


def _validar_tarjetas(
    ci: ConfigCloudInit,
    info: InfoCloudInitPlantilla,
    es_clon: bool,
    p: list[Problema],
    red_clon: RedClon | None = None,
) -> None:
    # Con la red del clon personalizada (C4) las tarjetas que existirán son las finales: las
    # AÑADIR cuentan y las QUITAR no (en estas últimas el problema es V-C16, no V-B34).
    finales = set(tarjetas_finales(info.tarjetas, red_clon))
    vistos: set[int] = set()
    for t in ci.tarjetas:
        campo = f"cloudinit.tarjetas[{t.indice}]"
        tarjeta = str(t.indice)
        if (
            not isinstance(t.indice, int)
            or isinstance(t.indice, bool)
            or not 0 <= t.indice < MAX_TARJETAS
        ):
            p.append(_error(campo, "V-B34", tarjeta=tarjeta, motivo="rango"))
            continue
        if t.indice in vistos:
            p.append(_error(campo, "V-B34", tarjeta=tarjeta, motivo="repetida"))
        vistos.add(t.indice)
        if (
            es_clon
            and t.modo != ModoTarjeta.SIN_CONFIGURAR
            and info.unidad is not None
            and t.indice not in finales
            and not _se_quita(red_clon, t.indice)
        ):
            p.append(_error(campo, "V-B34", tarjeta=tarjeta, motivo="inexistente"))
        if t.puerta and t.modo != ModoTarjeta.FIJA:
            p.append(_error(f"{campo}.puerta", "V-B29", tarjeta=tarjeta))
        if t.modo != ModoTarjeta.FIJA:
            continue
        # Con serie se valida la IP inicial: las siguientes son asunto de V-B30.
        cidr = t.serie_inicial or t.ip or ""
        motivo = motivo_cidr(cidr)
        if motivo is not None:
            codigo = "V-B27" if motivo == MotivoRed.RED_O_DIFUSION else "V-B26"
            p.append(_error(f"{campo}.ip", codigo, tarjeta=tarjeta, motivo=motivo.value))
        elif t.puerta:
            motivo = motivo_puerta(cidr, t.puerta)
            if motivo is not None:
                p.append(_error(f"{campo}.puerta", "V-B28", tarjeta=tarjeta, motivo=motivo.value))


def _validar_red_general(ci: ConfigCloudInit, p: list[Problema]) -> None:
    # V-B32: DNS. ``dns`` ya viene separado; se revalida cada elemento (archivo, CSV).
    if ci.dns:
        _, motivo = normalizar_dns(" ".join(ci.dns))
        if motivo is not None or any(not isinstance(d, str) or not d for d in ci.dns):
            p.append(_error("cloudinit.dns", "V-B32"))
        elif len(ci.dns) > MAX_DNS_SIN_AVISO:
            p.append(_aviso("cloudinit.dns", "V-B32", cantidad=str(len(ci.dns))))
    if ci.dominio and not dominio_valido(ci.dominio):
        p.append(_error("cloudinit.dominio", "V-B33"))
    if ci.actualizar is not None and not isinstance(ci.actualizar, bool):
        p.append(_error("cloudinit.actualizar", "V-B36"))


def _validar_snippets(ci: ConfigCloudInit, p: list[Problema]) -> None:
    elegidos = ci.snippets.elegidos()
    for tipo, volid in elegidos.items():
        if not volid_snippet_valido(volid):
            p.append(_error(f"cloudinit.snippets.{tipo}", "V-B54", tipo=tipo))
    if "user" in elegidos and (
        ci.usuario or ci.claves or (ci.contrasena is not None and ci.contrasena.definido)
    ):
        p.append(_aviso("cloudinit.snippets.user", "V-B53"))


def _problema_de_estado(estado: EstadoOpcion, campo: str, codigo: str, p: list[Problema]) -> None:
    """Convierte un estado de disponibilidad en problema (error si NO; aviso si CON_AVISO)."""
    if estado.disponibilidad == Disponibilidad.SI:
        return
    params = dict(estado.params)
    if estado.codigo is not None:
        params.setdefault("motivo", str(estado.codigo))
    severidad = Severidad.ERROR if estado.disponibilidad == Disponibilidad.NO else Severidad.AVISO
    p.append(Problema(campo, codigo, severidad, params))


def validar_cloudinit(cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades) -> list[Problema]:
    """V-B20..V-B29, V-B32..V-B37, V-B39, V-B40, V-B50, V-B53..V-B56 y V-B63 de una MV.

    Sin cloud-init (``cfg.cloudinit`` ``None`` o vacía) solo se evalúa V-B63 si pide esperar la
    IP; así el comportamiento de 0.6.0 no cambia.
    """
    p: list[Problema] = []
    permisos = inv.catalogo.permisos if inv.catalogo is not None else None
    ci = cfg.cloudinit

    # V-B63: privilegio del agente para esperar la IP (deshabilita la opción: error).
    if cfg.esperar_ip:
        _problema_de_estado(estado_permisos_agente(permisos, caps), "esperar_ip", "V-B63", p)

    # V-B40: ``vacia`` no cuenta un ``Secreto`` olvidado, así que se comprueba antes de salir.
    if ci is not None and ci.contrasena is not None and not ci.contrasena.definido:
        p.append(_error("cloudinit.contrasena", "V-B40", motivo="olvidada"))

    # Una puerta en una tarjeta «sin configurar» es la única señal de la config y debe dar V-B29
    # (CA-B1.8.3), aunque ``vacia`` la dé por vacía.
    puerta_suelta = ci is not None and any(t.puerta for t in ci.tarjetas)
    if ci is None or (ci.vacia and not puerta_suelta):
        return p

    es_clon = cfg.origen == OrigenSO.CLONAR_PLANTILLA
    info = cfg.info_cloudinit if cfg.info_cloudinit is not None else INFO_DESCONOCIDA

    if not es_clon:  # V-B39: la sección solo existe al clonar
        p.append(_error("cloudinit", "V-B39", origen=str(cfg.origen)))

    # Contenido (no depende del servidor).
    _validar_usuario(ci, p)
    _validar_claves(ci, p)
    _validar_tarjetas(ci, info, es_clon, p, cfg.red_clon)
    _validar_red_general(ci, p)
    _validar_snippets(ci, p)
    tiene_contrasena = ci.contrasena is not None and ci.contrasena.definido
    if tiene_contrasena and (info.es_windows or es_windows(info.ostype)):
        p.append(_error("cloudinit.contrasena", "V-B25", motivo="windows"))

    if not es_clon:
        return p

    # V-B20 / V-B35 / V-B56: lo que dice la config de la plantilla.
    plantilla = _nombre_plantilla(cfg)
    if info.unidad is False:
        p.append(_error("cloudinit", "V-B20", plantilla=plantilla))
    elif info.unidad is None:
        p.append(_aviso("cloudinit", "V-B20", plantilla=plantilla, motivo="no_comprobable"))
    if info.es_windows:
        p.append(_aviso("cloudinit", "V-B35", plantilla=plantilla))
    no_interpretable = info.cicustom is not None and not info.cicustom.interpretable
    if no_interpretable and not ci.snippets.como_la_plantilla:
        p.append(_aviso("cloudinit.snippets", "V-B56", plantilla=plantilla))

    # V-B50: el nodo necesita un almacenamiento con contenido «snippets».
    if ci.snippets.elegidos() and inv.storages_todos:
        hay = any(
            s.activo and "snippets" in s.contenido for s in inv.storages_todos.get(cfg.nodo, ())
        )
        if not hay:
            p.append(_error("cloudinit.snippets", "V-B50", nodo=cfg.nodo))

    # V-B37 / V-B55: privilegios de la versión (opción fijada sin permiso).
    necesita_ci = bool(
        ci.usuario
        or ci.claves
        or tiene_contrasena
        or any(t.modo != ModoTarjeta.SIN_CONFIGURAR for t in ci.tarjetas)
        or ci.actualizar is not None
        or not ci.snippets.como_la_plantilla
    )
    if necesita_ci:
        _problema_de_estado(estado_permisos_cloudinit(permisos, caps), "cloudinit", "V-B37", p)
    if ci.dns or ci.dominio:
        estado = estado_permisos_cloudinit(permisos, caps, OpcionB.DNS_DOMINIO, solo_red_basta=True)
        _problema_de_estado(estado, "cloudinit.dns", "V-B37", p)
    if not ci.snippets.como_la_plantilla:
        _problema_de_estado(
            estado_permisos_snippets(permisos, caps), "cloudinit.snippets", "V-B55", p
        )
    return p
