"""Almacén de los perfiles del usuario: ``perfiles_maquina.json`` (RF-P10, INV-M7, INV-M8).

Solo para el archivo PROPIO de la aplicación: usa la política de ``AlmacenJson`` (copia
``.danado-*`` ante corrupción). Los archivos de terceros nunca pasan por aquí.
Se usa solo desde el hilo de la interfaz (sin cerrojo); entre instancias gana la última escritura.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from proxlaunch import __version__
from proxlaunch.nucleo.archivos.constantes import MAX_PERFILES_USUARIO
from proxlaunch.nucleo.archivos.envoltura import (
    CLAVES_ENVOLTURA,
    FORMATO_PERFILES,
    abrir_envoltura,
    crear_envoltura,
)
from proxlaunch.nucleo.archivos.escritura import motivo_oserror
from proxlaunch.nucleo.archivos.esquema import (
    AvisoArchivo,
    ErrorCampo,
    LectorEsquema,
    MotivoCampo,
    combinar_avisos,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.formato import (
    PerfilLeido,
    leer_perfil_dict,
    perfil_a_dict,
    version_para,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil, OrigenPerfil, PerfilMaquina
from proxlaunch.nucleo.perfiles_maquina.validacion import (
    id_valido,
    nombre_libre,
    validar_config_perfil,
    validar_descripcion,
    validar_nombre_perfil,
)
from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson
from proxlaunch.nucleo.validacion import Severidad

_CLAVES_ID = frozenset({"id"})


class AccionImportar(StrEnum):
    CONSERVAR_AMBOS = "conservar_ambos"
    REEMPLAZAR = "reemplazar"


@dataclass(frozen=True)
class EntradaImportacion:
    perfil: PerfilLeido
    accion: AccionImportar = AccionImportar.CONSERVAR_AMBOS
    reemplaza_id: str | None = None  # perfil del usuario que se reemplaza (solo REEMPLAZAR)


@dataclass(frozen=True)
class EstadoAlmacen:
    solo_lectura: bool = False  # versión futura (E-M14): se lee, no se escribe
    hubo_corrupcion: bool = False
    copia_danada: Path | None = None
    error_lectura: bool = False
    descartados: tuple[ErrorCampo, ...] = ()  # perfiles individuales inválidos (CA-P10.4)
    avisos: tuple[AvisoArchivo, ...] = ()


def _uuid_hex() -> str:
    return uuid.uuid4().hex


def _rechazo(regla: str, campo: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(CodigoError.PERFIL_RECHAZADO, {"regla": regla, "campo": campo})


class AlmacenPerfilesMaquina:
    """Perfiles de fábrica (inmutables) + perfiles del usuario persistidos."""

    def __init__(
        self,
        ruta: Path,
        *,
        fabrica: Sequence[PerfilMaquina],
        generador_id: Callable[[], str] = _uuid_hex,
        ahora: Callable[[], datetime] = datetime.now,
        app_version: str = __version__,
    ) -> None:
        self.ruta = Path(ruta)
        self.fabrica = tuple(fabrica)
        self.generador_id = generador_id
        self.ahora = ahora
        self.app_version = app_version
        self._usuario: list[PerfilMaquina] = []
        self._estado = EstadoAlmacen()

    # --- Lectura ---

    @property
    def estado(self) -> EstadoAlmacen:
        return self._estado

    def todos(self) -> tuple[PerfilMaquina, ...]:
        """Fábrica primero y después los del usuario en orden de creación."""
        return (*self.fabrica, *self._usuario)

    def usuario(self) -> tuple[PerfilMaquina, ...]:
        return tuple(self._usuario)

    def obtener(self, id_perfil: str) -> PerfilMaquina:
        for p in self.todos():
            if p.id == id_perfil:
                return p
        disponibles = ", ".join(p.nombre for p in self.todos()[:5])
        raise ErrorProxLaunch(
            CodigoError.PERFIL_INEXISTENTE, {"nombre": str(id_perfil), "disponibles": disponibles}
        )

    def buscar_por_nombre(self, nombre: str) -> list[PerfilMaquina]:
        """Perfiles cuyo nombre (o id) coincide sin distinguir mayúsculas ni acentos."""
        from proxlaunch.nucleo.archivos.texto import clave_comparacion

        clave = clave_comparacion(nombre, sin_acentos=True)
        return [
            p
            for p in self.todos()
            if clave_comparacion(p.nombre, sin_acentos=True) == clave or p.id == nombre
        ]

    def cargar(self) -> EstadoAlmacen:
        """Lee el archivo propio (E/S). Inexistente → vacío, sin crear nada (CA-P12.2)."""
        self._usuario = []
        lectura = AlmacenJson(self.ruta, self.ahora).leer()
        if lectura.hubo_corrupcion:
            self._estado = EstadoAlmacen(
                hubo_corrupcion=True,
                copia_danada=lectura.copia_danada,
                error_lectura=lectura.error_lectura,
            )
            return self._estado
        if not lectura.datos:
            self._estado = EstadoAlmacen()
            return self._estado
        solo_lectura = False
        try:
            envoltura = abrir_envoltura(lectura.datos, FORMATO_PERFILES)
            contenido = envoltura.contenido
            avisos_env = envoltura.avisos
        except ErrorProxLaunch as exc:
            if exc.codigo == CodigoError.ARCHIVO_VERSION_FUTURA:
                solo_lectura = True
                contenido = {k: v for k, v in lectura.datos.items() if k not in CLAVES_ENVOLTURA}
                avisos_env = ()
            else:  # formato ajeno o versión inválida: no es nuestro archivo
                marcado = AlmacenJson(self.ruta, self.ahora)._marcar_danado()
                self._estado = EstadoAlmacen(
                    hubo_corrupcion=True,
                    copia_danada=marcado.copia_danada,
                    error_lectura=marcado.error_lectura,
                )
                return self._estado
        lector = LectorEsquema()
        raiz = lector.objeto(contenido, "", frozenset({"perfiles"}))
        crudos = lector.lista(raiz or {}, "perfiles", "", maximo=10**6, requerido=False) or []
        descartados: list[ErrorCampo] = []
        avisos_l: list[AvisoArchivo] = [*avisos_env, *lector.avisos()]
        ids: set[str] = set()
        for i, item in enumerate(crudos):
            ruta = f"perfiles[{i}]"
            if len(self._usuario) >= MAX_PERFILES_USUARIO:
                descartados.append(ErrorCampo(ruta, MotivoCampo.DEMASIADOS))
                continue
            sub = LectorEsquema()
            id_crudo = item.get("id") if isinstance(item, dict) else None
            leido = leer_perfil_dict(sub, item, ruta)
            avisos_l.extend(sub.avisos())
            if leido is None or sub.errores:
                descartados.extend(sub.errores or [ErrorCampo(ruta, MotivoCampo.TIPO)])
                continue
            if not isinstance(id_crudo, str) or not id_valido(id_crudo):
                descartados.append(ErrorCampo(f"{ruta}.id", MotivoCampo.TEXTO_NO_VALIDO))
                continue
            if id_crudo in ids or any(id_crudo == f.id for f in self.fabrica):
                descartados.append(ErrorCampo(f"{ruta}.id", MotivoCampo.DUPLICADO))
                continue
            ids.add(id_crudo)
            nombre, descripcion, config = leido
            self._usuario.append(
                PerfilMaquina(id_crudo, nombre, descripcion, OrigenPerfil.USUARIO, config)
            )
        self._estado = EstadoAlmacen(
            solo_lectura=solo_lectura,
            descartados=tuple(descartados),
            avisos=combinar_avisos(avisos_l),
        )
        return self._estado

    # --- Escritura ---

    def _guardar(self, nueva: list[PerfilMaquina]) -> None:
        """Escribe ANTES de cambiar la memoria. Falla → la lista en memoria no cambia."""
        if self._estado.solo_lectura:
            raise ErrorProxLaunch(CodigoError.PERFILES_SOLO_LECTURA)
        if self._estado.error_lectura:  # no se pisa un archivo que no se pudo leer
            raise ErrorProxLaunch(CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "sin_permiso"})
        contenido: dict[str, object] = {
            "perfiles": [perfil_a_dict(p, con_pistas=True, con_id=True) for p in nueva]
        }
        raiz = crear_envoltura(
            FORMATO_PERFILES,
            contenido,
            app_version=self.app_version,
            version_formato=version_para(nueva),
        )
        try:
            AlmacenJson(self.ruta, self.ahora).escribir(raiz)
        except OSError as exc:
            raise ErrorProxLaunch(
                CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": motivo_oserror(exc)}
            ) from exc
        self._usuario = nueva

    def _modificable(self, id_perfil: str) -> int:
        """Posición del perfil del usuario; fábrica → E-M13; inexistente → E-M12."""
        if any(f.id == id_perfil for f in self.fabrica):
            raise ErrorProxLaunch(CodigoError.PERFIL_NO_MODIFICABLE)
        for i, p in enumerate(self._usuario):
            if p.id == id_perfil:
                return i
        self.obtener(id_perfil)  # lanza PERFIL_INEXISTENTE
        raise AssertionError("inalcanzable")  # pragma: no cover

    def _validar(
        self,
        nombre: str,
        descripcion: str,
        config: ConfigPerfil,
        existentes: Sequence[PerfilMaquina],
        excluir_id: str | None,
    ) -> tuple[str, str]:
        nombre_ok, problemas = validar_nombre_perfil(nombre, existentes, excluir_id=excluir_id)
        descripcion_ok, p_desc = validar_descripcion(descripcion)
        problemas += p_desc
        problemas += [p for p in validar_config_perfil(config) if p.severidad == Severidad.ERROR]
        if problemas:
            raise _rechazo(problemas[0].codigo, problemas[0].campo)
        return nombre_ok, descripcion_ok

    def _nuevo_id(self, usados: set[str]) -> str:
        id_nuevo = self.generador_id()
        if not id_valido(id_nuevo) or id_nuevo in usados:
            raise _rechazo("V-M02", "id")
        return id_nuevo

    def _ids(self) -> set[str]:
        return {p.id for p in self.todos()}

    def crear(self, nombre: str, descripcion: str, config: ConfigPerfil) -> PerfilMaquina:
        if self._estado.solo_lectura:
            raise ErrorProxLaunch(CodigoError.PERFILES_SOLO_LECTURA)
        if len(self._usuario) >= MAX_PERFILES_USUARIO:
            raise _rechazo("V-M03", "perfiles")
        nombre_ok, desc_ok = self._validar(nombre, descripcion, config, self.todos(), None)
        perfil = PerfilMaquina(
            self._nuevo_id(self._ids()), nombre_ok, desc_ok, OrigenPerfil.USUARIO, config
        )
        self._guardar([*self._usuario, perfil])
        return perfil

    def actualizar(self, id_perfil: str, config: ConfigPerfil) -> PerfilMaquina:
        pos = self._modificable(id_perfil)
        actual = self._usuario[pos]
        self._validar(actual.nombre, actual.descripcion, config, self.todos(), id_perfil)
        nuevo = replace(actual, config=config)
        lista = list(self._usuario)
        lista[pos] = nuevo
        self._guardar(lista)
        return nuevo

    def renombrar(
        self, id_perfil: str, nombre: str, descripcion: str | None = None
    ) -> PerfilMaquina:
        pos = self._modificable(id_perfil)
        actual = self._usuario[pos]
        nombre_ok, desc_ok = self._validar(
            nombre,
            actual.descripcion if descripcion is None else descripcion,
            actual.config,
            self.todos(),
            id_perfil,
        )
        nuevo = replace(actual, nombre=nombre_ok, descripcion=desc_ok)
        lista = list(self._usuario)
        lista[pos] = nuevo
        self._guardar(lista)
        return nuevo

    def duplicar(self, id_perfil: str, nombre: str) -> PerfilMaquina:
        """Copia (también de un perfil de fábrica) con id nuevo y origen ``usuario``."""
        if self._estado.solo_lectura:
            raise ErrorProxLaunch(CodigoError.PERFILES_SOLO_LECTURA)
        original = self.obtener(id_perfil)
        if len(self._usuario) >= MAX_PERFILES_USUARIO:
            raise _rechazo("V-M03", "perfiles")
        nombre_ok, desc_ok = self._validar(
            nombre, original.descripcion, original.config, self.todos(), None
        )
        copia = PerfilMaquina(
            self._nuevo_id(self._ids()), nombre_ok, desc_ok, OrigenPerfil.USUARIO, original.config
        )
        self._guardar([*self._usuario, copia])
        return copia

    def eliminar(self, id_perfil: str) -> None:
        pos = self._modificable(id_perfil)
        self._guardar([p for i, p in enumerate(self._usuario) if i != pos])

    def importar(self, entradas: Sequence[EntradaImportacion]) -> tuple[PerfilMaquina, ...]:
        """Todo o nada: ``id`` nuevo y origen ``usuario`` siempre (CA-P09.4).

        ``CONSERVAR_AMBOS`` renombra a «nombre (2)» si hay conflicto; ``REEMPLAZAR`` sustituye
        a un perfil del usuario (nunca de fábrica, E-M13) conservando su posición.
        """
        if self._estado.solo_lectura:
            raise ErrorProxLaunch(CodigoError.PERFILES_SOLO_LECTURA)
        lista = list(self._usuario)
        usados = self._ids()
        creados: list[PerfilMaquina] = []
        for e in entradas:
            reemplaza = None
            if e.accion == AccionImportar.REEMPLAZAR:
                reemplaza = e.reemplaza_id
                if reemplaza is None:  # se deduce por nombre
                    cand = self.buscar_por_nombre(e.perfil.nombre)
                    reemplaza = cand[0].id if cand else None
                if reemplaza is None:
                    raise ErrorProxLaunch(
                        CodigoError.PERFIL_INEXISTENTE, {"nombre": e.perfil.nombre}
                    )
                if any(f.id == reemplaza for f in self.fabrica):
                    raise ErrorProxLaunch(CodigoError.PERFIL_NO_MODIFICABLE)
            visibles = [*self.fabrica, *lista]
            nombre = e.perfil.nombre
            if e.accion == AccionImportar.CONSERVAR_AMBOS:
                nombre = nombre_libre(nombre, visibles)
            nombre_ok, desc_ok = self._validar(
                nombre, e.perfil.descripcion, e.perfil.config, visibles, reemplaza
            )
            perfil = PerfilMaquina(
                self._nuevo_id(usados), nombre_ok, desc_ok, OrigenPerfil.USUARIO, e.perfil.config
            )
            usados.add(perfil.id)
            if reemplaza is not None:
                pos = next((i for i, p in enumerate(lista) if p.id == reemplaza), None)
                if pos is None:
                    raise ErrorProxLaunch(CodigoError.PERFIL_INEXISTENTE, {"nombre": reemplaza})
                lista[pos] = perfil
            else:
                lista.append(perfil)
            creados.append(perfil)
        if len(lista) > MAX_PERFILES_USUARIO:
            raise _rechazo("V-M03", "perfiles")
        self._guardar(lista)
        return tuple(creados)
