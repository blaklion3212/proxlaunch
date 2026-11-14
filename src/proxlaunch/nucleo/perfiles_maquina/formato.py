"""Archivos de perfiles de máquina: exportar e importar (RF-P08, RF-P09, formato §9.1).

Un perfil exportado no lleva ``id`` ni ``origen``; al importar, ``id`` y ``origen`` del archivo
se ignoran (el id lo genera el almacén y el origen es siempre ``usuario``, CA-P09.4).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from proxlaunch.nucleo.archivos.constantes import (
    LONG_DESCRIPCION,
    MAX_BYTES_PERFILES,
    MAX_PERFILES_ARCHIVO,
)
from proxlaunch.nucleo.archivos.envoltura import (
    FORMATO_PERFILES,
    a_bytes_json,
    abrir_envoltura,
    crear_envoltura,
)
from proxlaunch.nucleo.archivos.escritura import escribir_atomico
from proxlaunch.nucleo.archivos.esquema import (
    AvisoArchivo,
    ErrorCampo,
    LectorEsquema,
    MotivoCampo,
    combinar_avisos,
)
from proxlaunch.nucleo.archivos.esquema_config import config_perfil_a_dict, leer_config_perfil
from proxlaunch.nucleo.archivos.json_estricto import cargar_json_estricto
from proxlaunch.nucleo.archivos.lector import leer_archivo_limitado
from proxlaunch.nucleo.archivos.texto import contiene_token, texto_seguro
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil, PerfilMaquina
from proxlaunch.nucleo.perfiles_maquina.validacion import validar_config_perfil
from proxlaunch.nucleo.validacion import Severidad

_log = logging.getLogger("proxlaunch.perfiles_maquina.formato")

# ``id`` y ``origen`` se aceptan en el archivo pero nunca se leen (no se confía en ellos).
CLAVES_PERFIL_ARCHIVO = frozenset({"nombre", "descripcion", "config", "id", "origen"})


@dataclass(frozen=True)
class PerfilLeido:
    indice: int  # posición en el archivo, desde 0 (como en las rutas ``perfiles[i]``)
    nombre: str
    descripcion: str
    config: ConfigPerfil


@dataclass(frozen=True)
class PerfilInvalido:
    indice: int
    nombre: str | None  # solo si es un texto seguro (para mostrarlo en la lista de revisión)
    errores: tuple[ErrorCampo, ...]


@dataclass(frozen=True)
class ArchivoPerfiles:
    validos: tuple[PerfilLeido, ...]
    invalidos: tuple[PerfilInvalido, ...]
    avisos: tuple[AvisoArchivo, ...]


def perfil_a_dict(
    perfil: PerfilMaquina, *, con_pistas: bool, con_id: bool = False
) -> dict[str, object]:
    """Lista blanca de un perfil. ``con_id`` solo para el almacén propio."""
    datos: dict[str, object] = {
        "nombre": perfil.nombre,
        "descripcion": perfil.descripcion,
        "config": config_perfil_a_dict(perfil.config, con_pistas=con_pistas),
    }
    if con_id:
        datos["id"] = perfil.id
    return datos


def perfiles_a_bytes(
    perfiles: Sequence[PerfilMaquina], *, con_pistas: bool, app_version: str
) -> bytes:
    """Archivo ``proxlaunch.perfiles`` sin ``id`` ni ``origen`` (el de fábrica sale normal)."""
    contenido: dict[str, object] = {
        "perfiles": [perfil_a_dict(p, con_pistas=con_pistas) for p in perfiles]
    }
    return a_bytes_json(crear_envoltura(FORMATO_PERFILES, contenido, app_version=app_version))


def leer_perfil_dict(
    lector: LectorEsquema, valor: object, ruta: str
) -> tuple[str, str, ConfigPerfil] | None:
    """Esquema + capa 1 de un perfil. ``(nombre, descripcion, config)`` o ``None``.

    Los errores de capa 1 (``validar_sin_servidor``) se anotan como ``ErrorCampo`` con
    ``params["regla"]``.
    """
    obj = lector.objeto(valor, ruta, CLAVES_PERFIL_ARCHIVO)
    if obj is None:
        return None
    n0 = len(lector.errores)
    nombre = lector.nombre(obj, "nombre", ruta)
    descripcion = lector.texto(
        obj,
        "descripcion",
        ruta,
        maximo=LONG_DESCRIPCION,
        multilinea=True,
        sin_token=True,
        requerido=False,
        defecto="",
    )
    config = leer_config_perfil(lector, obj.get("config"), f"{ruta}.config" if ruta else "config")
    if "config" not in obj:
        lector.error(f"{ruta}.config" if ruta else "config", MotivoCampo.REQUERIDO)
    if len(lector.errores) > n0 or nombre is None or descripcion is None or config is None:
        return None
    for p in validar_config_perfil(config):
        if p.severidad == Severidad.ERROR:
            campo = f"{ruta}.config.{p.campo}" if ruta else f"config.{p.campo}"
            lector.error(campo, MotivoCampo.RANGO, regla=p.codigo)
    if len(lector.errores) > n0:
        return None
    return nombre, descripcion, config


def leer_perfiles(datos: bytes) -> ArchivoPerfiles:
    """Interpreta un archivo de perfiles de terceros (puro). Errores de archivo → excepción.

    Un perfil inválido NO invalida el archivo: va a ``invalidos`` con sus errores.
    """
    envoltura = abrir_envoltura(cargar_json_estricto(datos), FORMATO_PERFILES)
    lector = LectorEsquema()
    raiz = lector.objeto(envoltura.contenido, "", frozenset({"perfiles"}))
    items: list[object] = []
    if raiz is not None:
        crudo = raiz.get("perfiles")
        if isinstance(crudo, list) and len(crudo) > MAX_PERFILES_ARCHIVO:
            raise ErrorProxLaunch(
                CodigoError.ARCHIVO_NO_PERMITIDO,
                {
                    "motivo": "demasiadas_entradas",
                    "limite": str(MAX_PERFILES_ARCHIVO),
                    "tamano": str(len(crudo)),
                },
            )
        lista = lector.lista(raiz, "perfiles", "", maximo=MAX_PERFILES_ARCHIVO)
        items = lista or []
    lector.fallar_si_errores()
    validos: list[PerfilLeido] = []
    invalidos: list[PerfilInvalido] = []
    avisos: list[AvisoArchivo] = [*envoltura.avisos, *lector.avisos()]
    for i, item in enumerate(items):
        sub = LectorEsquema()
        resultado = leer_perfil_dict(sub, item, f"perfiles[{i}]")
        avisos.extend(sub.avisos())
        if resultado is not None and not sub.errores:
            validos.append(PerfilLeido(i, *resultado))
        else:
            nombre_crudo = item.get("nombre") if isinstance(item, dict) else None
            nombre = (
                texto_seguro(nombre_crudo, maximo=60) if isinstance(nombre_crudo, str) else None
            )
            if nombre is not None and contiene_token(nombre):
                nombre = None  # un nombre que parece un token no se devuelve (INV-M2)
            invalidos.append(PerfilInvalido(i, nombre, tuple(sub.errores)))
    return ArchivoPerfiles(tuple(validos), tuple(invalidos), combinar_avisos(avisos))


def leer_archivo_perfiles(ruta: Path) -> ArchivoPerfiles:
    """Lee un archivo de perfiles del usuario (E/S, solo lectura, ≤ 256 KiB)."""
    try:
        resultado = leer_perfiles(leer_archivo_limitado(ruta, MAX_BYTES_PERFILES))
    except ErrorProxLaunch as exc:
        _log.info("Perfiles rechazados archivo=%s codigo=%s", Path(ruta).name, exc.codigo)
        raise
    _log.info(
        "Perfiles leídos archivo=%s validos=%d invalidos=%d",
        Path(ruta).name,
        len(resultado.validos),
        len(resultado.invalidos),
    )
    return resultado


def exportar_perfiles(
    ruta: Path, perfiles: Sequence[PerfilMaquina], *, con_pistas: bool, app_version: str
) -> None:
    """Escribe los perfiles en la ruta elegida por el usuario, de forma atómica (E/S)."""
    escribir_atomico(
        ruta, perfiles_a_bytes(perfiles, con_pistas=con_pistas, app_version=app_version)
    )
