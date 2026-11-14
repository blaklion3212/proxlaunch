"""Repositorio de perfiles de conexión. Nunca persiste secretos (RF-07)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import fields
from pathlib import Path
from typing import Any, Protocol

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import MetodoAuth, PerfilConexion
from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas, clave_huella

VERSION_ESQUEMA = 1

_log = logging.getLogger("proxlaunch.persistencia.perfiles")
_CAMPOS_STORAGE = ("storage_mv", "storage_iso", "storage_import")


class _BorraSecretos(Protocol):
    def borrar(self, perfil_id: str) -> None: ...


def _a_dict(p: PerfilConexion) -> dict[str, Any]:
    """Serializa solo los campos declarados del perfil (sin secretos por construcción)."""
    d: dict[str, Any] = {}
    for campo in fields(p):
        valor = getattr(p, campo.name)
        if isinstance(valor, MetodoAuth):
            valor = valor.value
        elif isinstance(valor, list):
            valor = list(valor)
        d[campo.name] = valor
    return d


def _es_texto(valor: object) -> bool:
    return isinstance(valor, str)


def _es_booleano(valor: object) -> bool:
    return isinstance(valor, bool)


def _desde_dict(d: dict[str, Any]) -> PerfilConexion | None:
    """Reconstruye un perfil; ignora claves desconocidas y descarta entradas inválidas.

    Valida los tipos: ``hosts`` lista no vacía de textos no vacíos, ``puerto`` entero
    (no booleano) entre 1 y 65535, textos y booleanos donde corresponde.
    """
    try:
        conocidos = {c.name for c in fields(PerfilConexion)}
        datos = {k: v for k, v in d.items() if k in conocidos}
        if "metodo" in datos:
            datos["metodo"] = MetodoAuth(datos["metodo"])
        hosts = datos.get("hosts")
        if (
            not isinstance(hosts, list)
            or not hosts
            or not all(isinstance(h, str) and h.strip() for h in hosts)
        ):
            return None
        puerto = datos.get("puerto", 8006)
        if isinstance(puerto, bool) or not isinstance(puerto, int) or not 1 <= puerto <= 65535:
            return None
        if not all(_es_texto(datos.get(k, "x")) for k in ("id", "nombre", "usuario", "realm")):
            return None
        if not all(
            _es_booleano(datos.get(k, False)) for k in ("recordar_credenciales", "ignorar_ssl")
        ):
            return None
        # MVP 4 (RF-O05): storage recordado = texto o None; si no, None (se conserva el perfil).
        for campo in _CAMPOS_STORAGE:
            valor = datos.get(campo)
            if valor is not None and (not isinstance(valor, str) or not valor.strip()):
                _log.warning("Perfil de conexión: %s con tipo inválido; se ignora", campo)
                datos[campo] = None
        return PerfilConexion(**datos)
    except (TypeError, ValueError):
        return None


class RepositorioPerfiles:
    """Perfiles guardados en `perfiles.json` (orden de inserción)."""

    def __init__(self, ruta: Path) -> None:
        self._almacen = AlmacenJson(ruta)
        self.hubo_corrupcion = False
        self.copia_danada: Path | None = None
        self.error_lectura = False  # True si el archivo no se pudo leer (permisos, etc.)

    @property
    def ruta(self) -> Path:
        """Archivo de perfiles de conexión (su carpeta es la de configuración)."""
        return self._almacen.ruta

    def _cargar(self) -> list[PerfilConexion]:
        r = self._almacen.leer()
        if r.hubo_corrupcion:
            self.hubo_corrupcion = True
            self.copia_danada = r.copia_danada
            self.error_lectura = self.error_lectura or r.error_lectura
        crudos = r.datos.get("perfiles", [])
        if not isinstance(crudos, list):
            return []
        perfiles = (_desde_dict(c) for c in crudos if isinstance(c, dict))
        return [p for p in perfiles if p is not None]

    def _volcar(self, perfiles: list[PerfilConexion]) -> None:
        self._almacen.escribir(
            {"version_esquema": VERSION_ESQUEMA, "perfiles": [_a_dict(p) for p in perfiles]}
        )

    def listar(self) -> list[PerfilConexion]:
        """Todos los perfiles, en orden de creación."""
        return self._cargar()

    def obtener(self, perfil_id: str) -> PerfilConexion | None:
        return next((p for p in self._cargar() if p.id == perfil_id), None)

    def guardar(self, perfil: PerfilConexion) -> None:
        """Crea el perfil o, si el id ya existe, lo actualiza en su posición."""
        perfiles = self._cargar()
        for i, p in enumerate(perfiles):
            if p.id == perfil.id:
                perfiles[i] = perfil
                break
        else:
            perfiles.append(perfil)
        self._volcar(perfiles)

    def duplicar(self, perfil_id: str, nombre: str) -> PerfilConexion:
        """Copia un perfil con id nuevo y el `nombre` indicado (lo genera la interfaz con
        `tr()`, porque el núcleo no produce textos para el usuario).
        No copia secretos: la copia nace sin credenciales guardadas."""
        original = self.obtener(perfil_id)
        if original is None:
            raise ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {"perfil": perfil_id})
        copia = PerfilConexion(
            **{
                **{c.name: getattr(original, c.name) for c in fields(original)},
                "id": str(uuid.uuid4()),
                "nombre": nombre,
                "hosts": list(original.hosts),
            }
        )
        self.guardar(copia)
        return copia

    def eliminar(self, perfil_id: str) -> PerfilConexion | None:
        """Borra solo el perfil. Devuelve el perfil eliminado (o `None` si no existía).
        Para limpiar también secretos y huellas (CA-07.7) usar `eliminar_con_dependencias`."""
        perfiles = self._cargar()
        quedan = [p for p in perfiles if p.id != perfil_id]
        if len(quedan) == len(perfiles):
            return None
        eliminado = next(p for p in perfiles if p.id == perfil_id)
        self._volcar(quedan)
        return eliminado

    def huellas_huerfanas(self, perfil: PerfilConexion) -> list[tuple[str, int]]:
        """Pares (host, puerto) del perfil que ningún otro perfil guardado utiliza."""
        usadas = {
            clave_huella(h, p.puerto) for p in self._cargar() if p.id != perfil.id for h in p.hosts
        }
        return [
            (h, perfil.puerto) for h in perfil.hosts if clave_huella(h, perfil.puerto) not in usadas
        ]

    def eliminar_con_dependencias(
        self,
        perfil_id: str,
        secretos: _BorraSecretos | None = None,
        huellas: RepositorioHuellas | None = None,
    ) -> PerfilConexion | None:
        """Elimina el perfil, su secreto en el llavero y las huellas que solo él usaba.

        Si el llavero no está disponible se ignora el error (no había nada que borrar
        allí que pudiéramos alcanzar); el perfil ya fue eliminado.
        """
        eliminado = self.eliminar(perfil_id)
        if eliminado is None:
            return None
        if huellas is not None:
            for host, puerto in self.huellas_huerfanas(eliminado):
                huellas.eliminar(host, puerto)
        if secretos is not None:
            try:
                secretos.borrar(perfil_id)
            except ErrorProxLaunch as e:
                if e.codigo != CodigoError.LLAVERO_NO_DISPONIBLE:
                    raise
        return eliminado
