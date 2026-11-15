"""Compara el tamaño de un artefacto y de su árbol instalado con ``presupuesto.toml`` (CA-E19.1).

Uso::

    python empaquetado/comun/presupuesto.py {linux|windows} <artefacto> <carpeta_instalada>

Imprime los tamaños y falla (1) si alguno supera el presupuesto más la tolerancia.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

PRESUPUESTO = Path(__file__).resolve().with_name("presupuesto.toml")
MB = 1024 * 1024


def tamano_arbol(carpeta: Path) -> int:
    """Suma de los tamaños de los archivos regulares (los enlaces no se siguen)."""
    return sum(p.lstat().st_size for p in carpeta.rglob("*") if p.is_file() and not p.is_symlink())


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in ("linux", "windows"):
        print(__doc__, file=sys.stderr)
        return 2
    datos = tomllib.loads(PRESUPUESTO.read_text("utf-8"))
    tol = 1 + datos["tolerancia_porcentaje"] / 100
    lim = datos[argv[0]]
    medidas = {
        "artefacto": Path(argv[1]).stat().st_size / MB,
        "instalado": tamano_arbol(Path(argv[2])) / MB,
    }
    fallo = False
    for clave, valor in medidas.items():
        presupuesto = lim[f"{clave}_mb"]
        pasa = valor <= presupuesto * tol
        estado = "OK" if valor <= presupuesto else ("DENTRO DE LA TOLERANCIA" if pasa else "EXCEDE")
        print(f"tamaño {clave}: {valor:.1f} MB (presupuesto {presupuesto} MB, tolerancia "
              f"{datos['tolerancia_porcentaje']} %) -> {estado}")  # fmt: skip
        fallo = fallo or not pasa
    return 1 if fallo else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
