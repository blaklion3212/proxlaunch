"""Versión única de ProxLaunch para los scripts de empaquetado (AR-4, RF-E10).

Lee ``src/proxlaunch/__init__.py`` sin importar la aplicación (ni Qt), valida SemVer ``X.Y.Z``
(CA-E10.3) y la compara con ``pyproject.toml`` y con la etiqueta ``v<versión>`` si ``HEAD`` está
etiquetado (CA-E10.1).

Uso::

    python empaquetado/comun/version.py              # imprime la versión
    python empaquetado/comun/version.py --comprobar  # valida y compara; sale 1 si algo difiere
    python empaquetado/comun/version.py --windows    # X.Y.Z.0 para metadatos de Windows
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
INIT = RAIZ / "src" / "proxlaunch" / "__init__.py"
PYPROJECT = RAIZ / "pyproject.toml"
_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class ErrorVersion(Exception):
    """La versión no es válida o no es coherente."""


def version_del_codigo() -> str:
    """``__version__`` leído como texto de ``proxlaunch/__init__.py``."""
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', INIT.read_text("utf-8"), re.M)
    if not m:
        raise ErrorVersion(f"no se encontró __version__ en {INIT}")
    return m.group(1)


def validar_semver(version: str) -> str:
    # fullmatch: rechaza también un salto de línea final («1.2.3\n»), que `$` aceptaba.
    if not _SEMVER.fullmatch(version):
        raise ErrorVersion(
            f"la versión '{version}' no cumple SemVer X.Y.Z (sin sufijos de preliberación)"
        )
    return version


def _comprobar_pyproject(version: str) -> None:
    proyecto = tomllib.loads(PYPROJECT.read_text("utf-8"))
    p = proyecto["project"]
    if "version" in p:
        if p["version"] != version:
            raise ErrorVersion(
                f"pyproject.toml declara {p['version']} y __version__ declara {version}"
            )
        return
    dinamicos = p.get("dynamic", [])
    atributo = proyecto.get("tool", {}).get("setuptools", {}).get("dynamic", {}).get("version", {})
    if "version" not in dinamicos or atributo.get("attr") != "proxlaunch.__version__":
        raise ErrorVersion(
            "pyproject.toml no fija la versión: falta version estática o "
            "dynamic=['version'] con attr=proxlaunch.__version__"
        )


def etiqueta_de_head() -> str | None:
    """Etiqueta ``v*`` exacta de HEAD o ``None`` (sin git, sin repositorio o sin etiqueta)."""
    try:
        res = subprocess.run(
            ["git", "-C", str(RAIZ), "describe", "--exact-match", "--tags", "--match", "v*", "HEAD"],  # noqa: E501
            capture_output=True, text=True, check=False,
        )  # fmt: skip
    except FileNotFoundError:
        return None
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else None


def comprobar() -> str:
    """Valida y devuelve la versión; lanza ``ErrorVersion`` si hay incoherencias."""
    version = validar_semver(version_del_codigo())
    _comprobar_pyproject(version)
    etiqueta = etiqueta_de_head()
    if etiqueta is not None and etiqueta != f"v{version}":
        raise ErrorVersion(f"HEAD está etiquetado como {etiqueta} pero la versión es {version}")
    return version


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--comprobar", action="store_true", help="valida y compara las fuentes")
    ap.add_argument("--windows", action="store_true", help="imprime X.Y.Z.0")
    args = ap.parse_args(argv)
    try:
        version = comprobar() if args.comprobar else validar_semver(version_del_codigo())
    except ErrorVersion as exc:
        print(f"VERSIÓN: {exc}", file=sys.stderr)
        return 1
    print(f"{version}.0" if args.windows else version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
