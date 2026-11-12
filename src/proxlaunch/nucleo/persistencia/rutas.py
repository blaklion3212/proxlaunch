"""Rutas de datos, configuración y registro (platformdirs), todas inyectables."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import platformdirs

NOMBRE_APP = "ProxLaunch"


def crear_carpeta_privada(ruta: Path) -> None:
    """Crea la carpeta (y sus padres) y, en POSIX, la deja con permisos 0o700."""
    ruta.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        with contextlib.suppress(OSError):
            os.chmod(ruta, 0o700)


class Rutas:
    """Resuelve las carpetas y archivos de la aplicación.

    Si se pasa `base`, todo cuelga de ella (`base/` para datos y `base/log/` para el
    registro); así las pruebas nunca tocan la carpeta real del usuario. Sin `base` se
    usan las carpetas estándar del sistema.
    """

    def __init__(self, base: Path | str | None = None) -> None:
        if base is None:
            self._config = Path(platformdirs.user_config_dir(NOMBRE_APP))
            self._log = Path(platformdirs.user_log_dir(NOMBRE_APP))
        else:
            self._config = Path(base)
            self._log = self._config / "log"

    @property
    def directorio_config(self) -> Path:
        """Carpeta de perfiles, huellas y preferencias."""
        return self._config

    @property
    def directorio_log(self) -> Path:
        """Carpeta del registro rotativo."""
        return self._log

    @property
    def perfiles(self) -> Path:
        return self._config / "perfiles.json"

    @property
    def huellas(self) -> Path:
        return self._config / "huellas.json"

    @property
    def preferencias(self) -> Path:
        return self._config / "preferencias.json"
