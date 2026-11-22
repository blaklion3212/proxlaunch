"""Configuración común de pruebas.

- Los marcadores `integracion` requieren PROXLAUNCH_LAB=1.
- Qt corre sin pantalla (offscreen) para que las pruebas de interfaz funcionen en CI.
- Los secretos registrados en el filtro del log se olvidan entre casos (RNF-06).
- Aislamiento de carpetas del usuario: ninguna prueba puede escribir en las carpetas reales
  de ProxLaunch (datos, configuración, registro, estado). Se redirigen a una carpeta temporal
  de la sesión y, al terminar, una guarda comprueba que las reales no cambiaron.
"""

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Debe fijarse antes de que se cree cualquier QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import platformdirs  # noqa: E402
import pytest  # noqa: E402

# --- Aislamiento de las carpetas del usuario ----------------------------------------------------

_NOMBRE_APP = "ProxLaunch"
# Variables que platformdirs y Path.home() consultan para resolver las carpetas del usuario.
_VARIABLES_AISLADAS = (
    "HOME",
    "USERPROFILE",
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "LOCALAPPDATA",
    "APPDATA",
    "WIN_PD_OVERRIDE_LOCAL_APPDATA",
    "WIN_PD_OVERRIDE_APPDATA",
)


def _carpetas_reales() -> list[Path]:
    """Carpetas reales de la app según el entorno vigente (llamar ANTES de redirigir)."""
    return [
        Path(platformdirs.user_data_dir(_NOMBRE_APP)),
        Path(platformdirs.user_config_dir(_NOMBRE_APP)),
        Path(platformdirs.user_log_dir(_NOMBRE_APP)),
        Path(platformdirs.user_state_dir(_NOMBRE_APP)),
    ]


def _instantanea(carpetas: list[Path]) -> dict[Path, tuple[int, int] | None]:
    """Estado de cada archivo (mtime_ns, tamaño) y de cada carpeta (None) bajo ``carpetas``."""
    estado: dict[Path, tuple[int, int] | None] = {}
    for raiz in carpetas:
        if not raiz.exists():
            continue
        estado[raiz] = None
        for ruta in raiz.rglob("*"):
            try:
                if ruta.is_dir():
                    estado[ruta] = None
                else:
                    info = ruta.stat()
                    estado[ruta] = (info.st_mtime_ns, info.st_size)
            except OSError:
                continue  # desapareció durante el recorrido
    return estado


@dataclass
class _Aislamiento:
    """Datos del aislamiento de la sesión."""

    temporal: Path
    originales: dict[str, str | None]
    reales: list[Path]
    antes: dict[Path, tuple[int, int] | None]
    parche_windows: object | None = None
    violaciones: list[str] = field(default_factory=list)


_AISLAMIENTO: _Aislamiento | None = None


def _aislar_carpetas_del_usuario() -> None:
    """Redirige las carpetas del usuario a una carpeta temporal de la sesión.

    Se ejecuta al importar este módulo, antes de importar ``proxlaunch`` o crear nada, para que
    ninguna ruta se resuelva con el entorno real. Es idempotente.
    """
    global _AISLAMIENTO
    if _AISLAMIENTO is not None:
        return
    # El orden importa: primero se calculan las carpetas reales y se toma la instantánea.
    reales = _carpetas_reales()
    antes = _instantanea(reales)
    originales = {nombre: os.environ.get(nombre) for nombre in _VARIABLES_AISLADAS}

    temporal = Path(tempfile.mkdtemp(prefix="proxlaunch-pruebas-")).resolve()
    destinos = {
        "HOME": temporal / "home",
        "USERPROFILE": temporal / "home",
        "XDG_DATA_HOME": temporal / "xdg" / "data",
        "XDG_CONFIG_HOME": temporal / "xdg" / "config",
        "XDG_STATE_HOME": temporal / "xdg" / "state",
        "XDG_CACHE_HOME": temporal / "xdg" / "cache",
        "LOCALAPPDATA": temporal / "appdata" / "local",
        "APPDATA": temporal / "appdata" / "roaming",
        "WIN_PD_OVERRIDE_LOCAL_APPDATA": temporal / "appdata" / "local",
        "WIN_PD_OVERRIDE_APPDATA": temporal / "appdata" / "roaming",
    }
    for nombre, ruta in destinos.items():
        ruta.mkdir(parents=True, exist_ok=True)
        os.environ[nombre] = str(ruta)

    parche = None
    if sys.platform == "win32":
        # En Windows platformdirs resuelve con la API del sistema (ctypes) e ignora
        # LOCALAPPDATA/APPDATA; se desvía la resolución a las variables ya redirigidas.
        from platformdirs import windows as _pd_windows

        original = _pd_windows.get_win_folder

        def _carpeta_aislada(csidl_name: str) -> str:
            variable = {"CSIDL_LOCAL_APPDATA": "LOCALAPPDATA", "CSIDL_APPDATA": "APPDATA"}.get(
                csidl_name
            )
            if variable is not None:
                return os.environ[variable]
            return original(csidl_name)

        _pd_windows.get_win_folder = _carpeta_aislada
        parche = original

    _AISLAMIENTO = _Aislamiento(temporal, originales, reales, antes, parche)


def _restaurar_entorno() -> None:
    """Devuelve el entorno original y borra SOLO la carpeta temporal propia de la sesión."""
    global _AISLAMIENTO
    aislamiento = _AISLAMIENTO
    if aislamiento is None:
        return
    for nombre, valor in aislamiento.originales.items():
        if valor is None:
            os.environ.pop(nombre, None)
        else:
            os.environ[nombre] = valor
    if aislamiento.parche_windows is not None:
        from platformdirs import windows as _pd_windows

        _pd_windows.get_win_folder = aislamiento.parche_windows  # type: ignore[assignment]
    shutil.rmtree(aislamiento.temporal, ignore_errors=True)
    _AISLAMIENTO = None


_aislar_carpetas_del_usuario()

from proxlaunch.nucleo.registro import olvidar_secretos  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    """Guarda: las carpetas reales del usuario no deben tener archivos nuevos ni modificados."""
    aislamiento = _AISLAMIENTO
    if aislamiento is None:
        return
    despues = _instantanea(aislamiento.reales)
    tocados = sorted(
        str(ruta)
        for ruta, estado in despues.items()
        if ruta not in aislamiento.antes or aislamiento.antes[ruta] != estado
    )
    if tocados:
        aislamiento.violaciones = tocados
        lineas = "\n".join(f"  - {ruta}" for ruta in tocados[:50])
        extra = f"\n  ... y {len(tocados) - 50} más" if len(tocados) > 50 else ""
        mensaje = (
            "\nAISLAMIENTO VIOLADO: la sesión de pruebas creó o modificó "
            f"{len(tocados)} elemento(s) en las carpetas REALES del usuario:\n{lineas}{extra}\n"
            "Alguna prueba escribe fuera de tmp_path; inyecte la carpeta (Rutas(base), "
            "directorio_informes, etc.). Los archivos NO se borraron."
        )
        print(mensaje, file=sys.stderr)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_unconfigure(config):
    _restaurar_entorno()


@pytest.fixture(scope="session", autouse=True)
def aislamiento_sesion() -> _Aislamiento:
    """Garantiza el aislamiento durante toda la sesión y expone sus datos a las pruebas."""
    _aislar_carpetas_del_usuario()
    assert _AISLAMIENTO is not None
    return _AISLAMIENTO


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PROXLAUNCH_LAB") == "1":
        return
    saltar = pytest.mark.skip(reason="requiere el laboratorio: defina PROXLAUNCH_LAB=1")
    for item in items:
        if "integracion" in item.keywords:
            item.add_marker(saltar)


@pytest.fixture(autouse=True)
def _olvidar_secretos_entre_casos():
    """Evita que un secreto registrado en un caso se filtre al siguiente."""
    olvidar_secretos(incluir_cloudinit=True)
    yield
    olvidar_secretos(incluir_cloudinit=True)


@pytest.fixture(scope="session")
def instantanea_carpetas():
    """Función que toma la instantánea (archivo -> mtime, tamaño) de una lista de carpetas."""
    return _instantanea
