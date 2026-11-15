"""Almacén JSON con escritura atómica y recuperación ante archivos corruptos (RNF-15)."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from proxlaunch.nucleo.archivos.reemplazo import reemplazar_con_reintentos
from proxlaunch.nucleo.persistencia.rutas import crear_carpeta_privada


@dataclass(frozen=True)
class ResultadoLectura:
    """Resultado de leer un archivo JSON."""

    datos: dict[str, Any]
    hubo_corrupcion: bool = False
    copia_danada: Path | None = None  # ruta a la que se renombró el archivo dañado
    # No se pudo leer (permisos, es una carpeta...) o renombrar el dañado: se parte de vacío
    # y `hubo_corrupcion` también es True para que la interfaz avise.
    error_lectura: bool = False


class AlmacenJson:
    """Lee y escribe un objeto JSON (diccionario) en un archivo UTF-8."""

    def __init__(self, ruta: Path, ahora: Callable[[], datetime] = datetime.now) -> None:
        self.ruta = Path(ruta)
        self._ahora = ahora

    def leer(self) -> ResultadoLectura:
        """Lee el archivo. Si no existe, devuelve vacío. Si está dañado (JSON inválido,
        UTF-8 inválido o raíz que no es un objeto), lo renombra a
        `<nombre>.danado-<AAAAMMDD-HHMMSS>` y devuelve vacío indicando la corrupción."""
        try:
            texto = self.ruta.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ResultadoLectura({})
        except UnicodeDecodeError:
            return self._marcar_danado()
        except OSError:  # PermissionError, IsADirectoryError, fallo de disco...
            return ResultadoLectura({}, hubo_corrupcion=True, error_lectura=True)
        try:
            datos = json.loads(texto)
        except ValueError:
            return self._marcar_danado()
        if not isinstance(datos, dict):
            return self._marcar_danado()
        return ResultadoLectura(datos)

    def escribir(self, datos: dict[str, Any]) -> None:
        """Escribe de forma atómica: temporal en la misma carpeta y `os.replace`."""
        crear_carpeta_privada(self.ruta.parent)
        fd, nombre_tmp = tempfile.mkstemp(
            dir=self.ruta.parent, prefix=self.ruta.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            reemplazar_con_reintentos(nombre_tmp, self.ruta)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(nombre_tmp)
            raise

    def _marcar_danado(self) -> ResultadoLectura:
        sello = self._ahora().strftime("%Y%m%d-%H%M%S")
        destino = self.ruta.with_name(f"{self.ruta.name}.danado-{sello}")
        contador = 1
        while destino.exists():  # evita pisar una copia previa del mismo segundo
            destino = self.ruta.with_name(f"{self.ruta.name}.danado-{sello}-{contador}")
            contador += 1
        try:
            reemplazar_con_reintentos(self.ruta, destino)
        except OSError:
            return ResultadoLectura({}, hubo_corrupcion=True, error_lectura=True)
        return ResultadoLectura({}, hubo_corrupcion=True, copia_danada=destino)
