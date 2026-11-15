"""Comprueba (o regenera) los lockfiles con hashes de ``empaquetado/requisitos`` (AR-3, RF-E21).

Uso::

    python empaquetado/comun/comprobar_lock.py                 # comprueba; sale 1 si algo no cuadra
    python empaquetado/comun/comprobar_lock.py --regenerar     # recompila con ``uv pip compile``

Cada lockfile lleva en su primera línea el hash de sus entradas (``.in``), de modo que cambiar
``pyproject.toml`` o un ``.in`` sin regenerar hace fallar la comprobación (CA-E21.2). Solo usa la
biblioteca estándar (Python 3.11+); ``--regenerar`` necesita ``uv`` y red.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REQUISITOS = RAIZ / "empaquetado" / "requisitos"
PYPROJECT = RAIZ / "pyproject.toml"

PYTHON_BUILD = "3.13"
PLATAFORMAS = {
    "linux": "x86_64-manylinux_2_35",
    "windows": "x86_64-pc-windows-msvc",
}
# Juego -> archivos .in que lo definen (el primero es el propio; los demás entran por ``-r``).
JUEGOS = {
    "ejecucion": ("ejecucion.in",),
    "construccion": ("construccion.in",),
    "calidad": ("calidad.in", "ejecucion.in"),
}
_MARCA = "# proxlaunch-lock:"


def _lineas_utiles(ruta: Path) -> list[str]:
    """Líneas del ``.in`` sin comentarios ni blancos."""
    salida = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.split(" #")[0].strip()
        if linea and not linea.startswith("#"):
            salida.append(linea)
    return salida


def hash_entradas(juego: str) -> str:
    """SHA-256 del contenido útil de los ``.in`` del juego."""
    h = hashlib.sha256()
    for nombre in JUEGOS[juego]:
        h.update(nombre.encode())
        h.update(b"\0")
        h.update("\n".join(_lineas_utiles(REQUISITOS / nombre)).encode())
        h.update(b"\0")
    return h.hexdigest()


def _normalizar(req: str) -> str:
    return re.sub(r"\s+", "", req).lower()


def _comparar_con_pyproject() -> list[str]:
    """``ejecucion.in`` y ``calidad.in`` deben reflejar ``pyproject.toml``."""
    problemas: list[str] = []
    datos = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    proyecto = datos["project"]
    esperadas = {_normalizar(r) for r in proyecto["dependencies"]}
    reales = {_normalizar(r) for r in _lineas_utiles(REQUISITOS / "ejecucion.in")}
    if esperadas != reales:
        problemas.append(
            "ejecucion.in no coincide con [project].dependencies de pyproject.toml "
            f"(solo en pyproject: {sorted(esperadas - reales)}; "
            f"solo en .in: {sorted(reales - esperadas)})"
        )
    dev = {_normalizar(r) for r in proyecto.get("optional-dependencies", {}).get("dev", [])}
    reales_cal = {
        _normalizar(r) for r in _lineas_utiles(REQUISITOS / "calidad.in") if not r.startswith("-r")
    }
    if dev != reales_cal:
        problemas.append(
            "calidad.in no coincide con el extra [dev] de pyproject.toml "
            f"(solo en pyproject: {sorted(dev - reales_cal)}; "
            f"solo en .in: {sorted(reales_cal - dev)})"
        )
    minimo = re.search(r">=\s*(\d+)\.(\d+)", proyecto.get("requires-python", ""))
    if minimo:
        pedido = (int(minimo.group(1)), int(minimo.group(2)))
        build = tuple(int(x) for x in PYTHON_BUILD.split("."))
        if build < pedido:
            problemas.append(f"Python de build {PYTHON_BUILD} < requires-python {pedido}")
    return problemas


def _comprobar_lock(juego: str, plataforma: str, clave: str) -> list[str]:
    ruta = REQUISITOS / f"{clave}-{juego}.txt"
    if not ruta.is_file():
        return [f"falta {ruta.name}; ejecute --regenerar"]
    texto = ruta.read_text(encoding="utf-8")
    primera = texto.splitlines()[0] if texto else ""
    esperada = (
        f"{_MARCA} entradas-sha256={hash_entradas(juego)} python={PYTHON_BUILD} plataforma={clave}"
    )
    if primera != esperada:
        return [f"{ruta.name} está desactualizado respecto de sus entradas; ejecute --regenerar"]
    problemas = []
    # Cada paquete fijado debe llevar al menos un hash (instalación con --require-hashes).
    bloques = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", texto)
    for bloque in bloques[1:]:
        if "--hash=sha256:" not in bloque:
            problemas.append(f"{ruta.name}: '{bloque.splitlines()[0]}' no tiene hash")
    if len(bloques) < 2:
        problemas.append(f"{ruta.name}: no contiene paquetes fijados")
    return problemas


def comprobar() -> list[str]:
    problemas = _comparar_con_pyproject()
    for clave, plataforma in PLATAFORMAS.items():
        for juego in JUEGOS:
            problemas += _comprobar_lock(juego, plataforma, clave)
    return problemas


def regenerar() -> None:
    for clave, plataforma in PLATAFORMAS.items():
        for juego, entradas in JUEGOS.items():
            destino = REQUISITOS / f"{clave}-{juego}.txt"
            with tempfile.TemporaryDirectory(prefix="plk-") as tmp:
                salida = Path(tmp) / "lock.txt"
                orden = [
                    "uv", "pip", "compile", entradas[0], "--generate-hashes", "--no-header",
                    "--no-build", "--quiet", "--python-version", PYTHON_BUILD,
                    "--python-platform", plataforma, "-o", str(salida),
                ]  # fmt: skip
                subprocess.run(orden, cwd=REQUISITOS, check=True)
                cuerpo = salida.read_text(encoding="utf-8")
            cabecera = (
                f"{_MARCA} entradas-sha256={hash_entradas(juego)} python={PYTHON_BUILD} "
                f"plataforma={clave}\n"
                f"# Generado con: uv pip compile {entradas[0]} --generate-hashes --no-build "
                f"--python-version {PYTHON_BUILD} --python-platform {plataforma}\n"
                "# Instalar con: pip install --require-hashes --no-deps -r <este archivo>\n"
            )
            destino.write_text(cabecera + cuerpo, encoding="utf-8")
            print(f"regenerado {destino.name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--regenerar", action="store_true", help="recompila los lockfiles con uv")
    args = ap.parse_args(argv)
    if args.regenerar:
        try:
            regenerar()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"error al regenerar: {exc}", file=sys.stderr)
            return 1
    problemas = comprobar()
    for p in problemas:
        print(f"LOCK: {p}", file=sys.stderr)
    if problemas:
        return 1
    print("lockfiles coherentes con pyproject.toml y sus entradas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
