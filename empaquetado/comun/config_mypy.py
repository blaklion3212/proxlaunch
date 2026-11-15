"""Genera la configuración de mypy para ``calidad.sh`` a partir de ``[tool.mypy]`` de pyproject.

Copia las opciones de ``pyproject.toml`` y añade que ``PySide6`` se trate como sin tipos
(``follow_imports = skip``), que es lo que ve el desarrollo cuando la instalación de PySide6 no
trae los stubs ``.pyi``. Con los stubs de la rueda fijada en el lockfile, mypy encuentra errores
reales de tipos contra la API de Qt que el flujo habitual no ve (véase el reporte de la fase).

Uso::

    python empaquetado/comun/config_mypy.py <salida.ini>
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def generar() -> str:
    opciones = tomllib.loads((RAIZ / "pyproject.toml").read_text("utf-8"))["tool"]["mypy"]
    lineas = ["[mypy]"]
    for clave, valor in opciones.items():
        if isinstance(valor, bool):
            valor = "True" if valor else "False"
        lineas.append(f"{clave} = {valor}")
    lineas += ["", "[mypy-PySide6.*]", "follow_imports = skip", "follow_imports_for_stubs = True"]
    return "\n".join(lineas) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    destino = Path(argv[0])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(generar(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
