"""Validación de perfiles de máquina: V-M01..V-M05 y capa 1 de la configuración."""

from __future__ import annotations

import re
from collections.abc import Iterable

from proxlaunch.nucleo.archivos.constantes import (
    LONG_DESCRIPCION,
    LONG_NOMBRE_PERFIL,
    MAX_LONG_TEXTO,
)
from proxlaunch.nucleo.archivos.texto import (
    analizar_texto,
    clave_comparacion,
    contiene_token,
    texto_seguro,
    validar_nombre,
)
from proxlaunch.nucleo.modelos.origen import (
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    DetalleOrigen,
    RefPlantilla,
    RefVolumen,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    ConfiguracionVM,
    Disco,
    InterfazRed,
    OrigenSO,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import PREFIJO_FABRICA, ConfigPerfil, PerfilMaquina
from proxlaunch.nucleo.validacion import Problema, Severidad, validar_sin_servidor

_RE_ID_USUARIO = re.compile(r"[a-z0-9-]{1,64}")
_RE_ID_FABRICA = re.compile(r"fabrica\.[a-z0-9-]{1,64}")
_PISTA_FICTICIA = "x"


def id_valido(id_perfil: str, *, permitir_fabrica: bool = False) -> bool:
    """V-M02: ``[a-z0-9-]`` (uuid) y sin el prefijo reservado ``fabrica.``."""
    if not isinstance(id_perfil, str):
        return False
    if id_perfil.startswith(PREFIJO_FABRICA):
        return permitir_fabrica and _RE_ID_FABRICA.fullmatch(id_perfil) is not None
    return _RE_ID_USUARIO.fullmatch(id_perfil) is not None


def _error(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.ERROR, dict(params))


def validar_nombre_perfil(
    nombre: str, existentes: Iterable[PerfilMaquina], *, excluir_id: str | None = None
) -> tuple[str, list[Problema]]:
    """V-M01 (con unicidad entre fábrica y usuario), V-M04 y V-M05 sobre un nombre.

    Devuelve ``(nombre normalizado, problemas)``. El duplicado es ``V-M01.duplicado``.
    ``excluir_id`` omite al propio perfil al renombrar o actualizar.
    """
    normalizado, regla = validar_nombre(nombre, maximo=LONG_NOMBRE_PERFIL)
    if regla is not None:
        return normalizado, [_error("nombre", regla, maximo=str(LONG_NOMBRE_PERFIL))]
    clave = clave_comparacion(normalizado)
    for p in existentes:
        if p.id != excluir_id and clave_comparacion(p.nombre) == clave:
            return normalizado, [_error("nombre", "V-M01.duplicado")]
    return normalizado, []


def validar_descripcion(descripcion: str) -> tuple[str, list[Problema]]:
    """V-M04 y V-M05 sobre la descripción (0–200 caracteres, admite saltos de línea)."""
    if not isinstance(descripcion, str):
        return "", [_error("descripcion", "V-M04")]
    texto, motivo = analizar_texto(descripcion, maximo=LONG_DESCRIPCION, multilinea=True)
    if motivo is not None:
        return texto, [_error("descripcion", "V-M04", maximo=str(LONG_DESCRIPCION))]
    if contiene_token(texto):
        return texto, [_error("descripcion", "V-M05")]
    return texto, []


def nombre_libre(base: str, existentes: Iterable[PerfilMaquina]) -> str:
    """Primer nombre libre: ``base``, ``base (2)``, ``base (3)``... (recortado a 60)."""
    usados = {clave_comparacion(p.nombre) for p in existentes}
    base = base.strip()
    if clave_comparacion(base) not in usados:
        return base
    n = 2
    while True:
        sufijo = f" ({n})"
        candidato = base[: LONG_NOMBRE_PERFIL - len(sufijo)].rstrip() + sufijo
        if clave_comparacion(candidato) not in usados:
            return candidato
        n += 1


def _detalle_ficticio(config: ConfigPerfil) -> DetalleOrigen | None:
    """Detalle con fuente ficticia: un perfil sin fuente es válido (solo sugiere el origen)."""
    pista = config.pista_origen
    if config.origen == OrigenSO.ISO:
        return DetalleIso(iso=RefVolumen(_PISTA_FICTICIA), sin_drivers=True)
    if config.origen == OrigenSO.IMPORTAR_DISCO:
        ampliar = None if pista is None else pista.ampliar_a_gib
        return DetalleImportacion(imagen=RefVolumen(_PISTA_FICTICIA), ampliar_a_gib=ampliar)
    if config.origen == OrigenSO.CLONAR_PLANTILLA:
        return DetalleClon(
            plantilla=RefPlantilla(_PISTA_FICTICIA),
            modo=pista.modo_clon if pista else DetalleClon().modo,
            ajustes=pista.ajustes if pista else DetalleClon().ajustes,
        )
    return None


def cfg_ficticia(config: ConfigPerfil) -> ConfiguracionVM:
    """``ConfiguracionVM`` con storage y bridge ficticios, solo para validar la capa 1."""
    # Un perfil ISO sin tipo de SO es válido (solo sugiere): se valida como «otro».
    tipo_so = (
        TipoSO.OTRO if config.origen == OrigenSO.ISO and config.tipo_so is None else config.tipo_so
    )
    return ConfiguracionVM(
        vmid=0,
        nombre="",
        nodo="",
        firmware=config.firmware,
        storage_efi=None,
        sockets=config.sockets,
        cores=config.cores,
        tipo_cpu=config.tipo_cpu,
        memoria_mib=config.memoria_mib,
        ballooning=(
            None
            if config.ballooning is None
            else Ballooning(config.ballooning.activo, config.ballooning.minimo_mib)
        ),
        con_disco=config.con_disco,
        discos=[
            Disco(_PISTA_FICTICIA, d.tamano_gib, d.bus, d.formato, d.discard, d.ssd, d.iothread)
            for d in config.discos
        ],
        controlador_scsi=config.controlador_scsi,
        redes=[InterfazRed(_PISTA_FICTICIA, r.modelo, r.vlan) for r in config.redes],
        origen=config.origen,
        tipo_so=tipo_so,
        tpm=config.tpm,
        agente_qemu=config.agente_qemu,
        detalle_origen=_detalle_ficticio(config),
    )


def validar_config_perfil(config: ConfigPerfil) -> list[Problema]:
    """Capa 1 del perfil: ``validar_sin_servidor`` sobre la configuración + pistas (V-M04).

    Los errores de capa 2 (storage o bridge inexistentes) no existen aquí: son del sitio.
    """
    problemas = validar_sin_servidor(cfg_ficticia(config))
    pistas = [("storage_efi_preferido", config.storage_efi_preferido)]
    pistas += [
        (f"discos[{i}].storage_preferido", d.storage_preferido) for i, d in enumerate(config.discos)
    ]
    pistas += [
        (f"redes[{i}].bridge_preferido", r.bridge_preferido) for i, r in enumerate(config.redes)
    ]
    if config.pista_origen is not None:
        pistas += [
            ("detalle_origen.nombre_fuente", config.pista_origen.nombre_fuente or None),
            ("detalle_origen.storage_preferido", config.pista_origen.storage_preferido),
            ("detalle_origen.drivers", config.pista_origen.drivers),
        ]
    for campo, pista in pistas:
        if pista is not None and texto_seguro(pista, maximo=MAX_LONG_TEXTO) is None:
            problemas.append(_error(campo, "V-M04"))
    return problemas
