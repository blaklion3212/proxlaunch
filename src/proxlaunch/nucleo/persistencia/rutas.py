"""Rutas de datos, configuración y registro (platformdirs), todas inyectables."""

from __future__ import annotations

import contextlib
import os
import stat
from pathlib import Path

import platformdirs

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

NOMBRE_APP = "ProxLaunch"


def _niveles_propios(ruta: Path) -> list[Path]:
    """Carpetas de la app: desde la que se llama ``NOMBRE_APP`` hacia abajo (o solo la última)."""
    partes = ruta.parts
    if NOMBRE_APP in partes:
        n = partes.index(NOMBRE_APP) + 1
        return [Path(*partes[:k]) for k in range(n, len(partes) + 1)]
    return [ruta]


def _asegurar_privada(nivel: Path) -> None:
    """POSIX: crea (0700) o endurece un nivel propio, sin seguir enlaces ni tocar ajenos."""
    try:
        nivel.mkdir(exist_ok=True, mode=0o700)
        info = os.lstat(nivel)
    except OSError as exc:
        raise ErrorProxLaunch(CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "sin_permiso"}) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ErrorProxLaunch(CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "sin_permiso"})
    with contextlib.suppress(OSError):
        os.chmod(nivel, 0o700)


def crear_carpeta_privada(ruta: Path) -> None:
    """Crea la carpeta (y sus padres) y, en POSIX, deja con 0o700 cada nivel propio de la app.

    Los niveles propios van desde la carpeta ``NOMBRE_APP`` hacia abajo (si la ruta no la
    contiene, solo el último). Se rechaza (E-M08, ``sin_permiso``) un nivel que sea enlace
    simbólico o de otro usuario. Los ancestros ajenos a la app no se modifican.
    """
    if os.name != "posix":
        ruta.mkdir(parents=True, exist_ok=True, mode=0o700)
        return
    propios = _niveles_propios(ruta)
    propios[0].parent.mkdir(parents=True, exist_ok=True)
    for nivel in propios:
        _asegurar_privada(nivel)


class Rutas:
    """Resuelve las carpetas y archivos de la aplicación.

    Si se pasa `base`, todo cuelga de ella (`base/` para datos y `base/log/` para el
    registro); así las pruebas nunca tocan la carpeta real del usuario. Sin `base` se
    usan las carpetas estándar del sistema.
    """

    def __init__(self, base: Path | str | None = None) -> None:
        if base is None:
            self._config = Path(platformdirs.user_config_dir(NOMBRE_APP))
            self._datos = Path(platformdirs.user_data_dir(NOMBRE_APP))
            self._log = Path(platformdirs.user_log_dir(NOMBRE_APP))
        else:
            self._config = Path(base)
            self._log = self._config / "log"
            self._datos = self._config / "datos"

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
    def perfiles_maquina(self) -> Path:
        """Perfiles de máquina del usuario (MVP 3)."""
        return self._config / "perfiles_maquina.json"

    @property
    def directorio_datos(self) -> Path:
        """Datos del usuario (lotes guardados): ``user_data_dir`` o ``base/datos``."""
        return self._datos

    @property
    def lotes(self) -> Path:
        """Carpeta sugerida para los lotes guardados (se crea 0700 solo al usarla)."""
        return self._datos / "lotes"

    @property
    def huellas(self) -> Path:
        return self._config / "huellas.json"

    @property
    def preferencias(self) -> Path:
        return self._config / "preferencias.json"
