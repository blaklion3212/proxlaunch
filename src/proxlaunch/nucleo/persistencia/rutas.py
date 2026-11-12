"""Rutas de datos, configuración y registro (platformdirs), todas inyectables."""

from __future__ import annotations

from pathlib import Path

import platformdirs

NOMBRE_APP = "ProxLaunch"


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
