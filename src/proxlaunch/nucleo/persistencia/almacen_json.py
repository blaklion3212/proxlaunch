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


@dataclass(frozen=True)
class ResultadoLectura:
    """Resultado de leer un archivo JSON."""

    datos: dict[str, Any]
    hubo_corrupcion: bool = False
    copia_danada: Path | None = None  # ruta a la que se renombró el archivo dañado


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
        try:
            datos = json.loads(texto)
        except ValueError:
            return self._marcar_danado()
        if not isinstance(datos, dict):
            return self._marcar_danado()
        return ResultadoLectura(datos)

    def escribir(self, datos: dict[str, Any]) -> None:
        """Escribe de forma atómica: temporal en la misma carpeta y `os.replace`."""
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        fd, nombre_tmp = tempfile.mkstemp(
            dir=self.ruta.parent, prefix=self.ruta.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(nombre_tmp, self.ruta)
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
        os.replace(self.ruta, destino)
        return ResultadoLectura({}, hubo_corrupcion=True, copia_danada=destino)
