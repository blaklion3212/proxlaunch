"""Compila ``proxlaunch_es.ts`` a ``proxlaunch_es.qm`` con el ``lrelease`` de PySide6 (RF-E07).

El ``.qm`` es producto del build (no se versiona). Falla si el ``.ts`` no es XML válido, si la
herramienta falla o si el ``.qm`` queda vacío. No regenera el ``.ts``.

Uso::

    python empaquetado/comun/compilar_qm.py [--ts RUTA] [--qm RUTA]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TRADUCCIONES = RAIZ / "src" / "proxlaunch" / "recursos" / "traducciones"


def buscar_lrelease() -> Path:
    """Ubica ``lrelease`` en la rueda de PySide6 instalada (HV-E2)."""
    import importlib.util

    spec = importlib.util.find_spec("PySide6")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("PySide6 no está instalado en este entorno")
    base = Path(next(iter(spec.submodule_search_locations)))
    for candidato in (
        base / "lrelease",
        base / "lrelease.exe",
        base / "Qt" / "libexec" / "lrelease",
        base / "Qt" / "bin" / "lrelease.exe",
    ):
        if candidato.is_file():
            return candidato
    raise RuntimeError(f"no se encontró lrelease dentro de {base}")


def contar_mensajes(ts: Path) -> tuple[int, int]:
    """(mensajes totales, mensajes con traducción) del ``.ts``."""
    raiz = ET.parse(ts).getroot()
    mensajes = raiz.findall(".//message")
    traducidos = [
        m for m in mensajes
        if (t := m.find("translation")) is not None and (t.text or "").strip()
        and t.get("type") not in ("unfinished", "vanished", "obsolete")
    ]  # fmt: skip
    return len(mensajes), len(traducidos)


def compilar(ts: Path, qm: Path) -> int:
    """Devuelve el tamaño en bytes del ``.qm`` generado."""
    if not ts.is_file():
        raise RuntimeError(f"no existe el catálogo {ts}")
    try:
        ET.parse(ts)
    except ET.ParseError as exc:
        raise RuntimeError(f"{ts.name} no es XML válido: {exc}") from exc
    qm.parent.mkdir(parents=True, exist_ok=True)
    if qm.exists():
        qm.unlink()
    res = subprocess.run(
        [str(buscar_lrelease()), str(ts), "-qm", str(qm)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if res.returncode != 0:
        raise RuntimeError(f"lrelease falló ({res.returncode}): {res.stderr.strip() or res.stdout}")
    if not qm.is_file() or qm.stat().st_size == 0:
        raise RuntimeError(f"{qm.name} quedó vacío o no se creó")
    return qm.stat().st_size


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ts", type=Path, default=TRADUCCIONES / "proxlaunch_es.ts")
    ap.add_argument("--qm", type=Path, default=None)
    args = ap.parse_args(argv)
    qm = args.qm or args.ts.with_suffix(".qm")
    try:
        tam = compilar(args.ts, qm)
    except RuntimeError as exc:
        print(f"TRADUCCIONES: {exc}", file=sys.stderr)
        return 1
    total, traducidos = contar_mensajes(args.ts)
    print(f"compilado {qm.name} ({tam} bytes; {traducidos} de {total} mensajes traducidos)")
    if traducidos == 0:
        print("AVISO: el catálogo no trae traducciones (la interfaz usa los textos del código)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
