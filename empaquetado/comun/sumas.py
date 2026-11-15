"""Sellos de verificación y ``SHA256SUMS`` (AR-8, RF-E20, RF-E18, INV-E6).

Una suma solo se publica si el artefacto pasó la verificación instalada: el anfitrión escribe un
sello ``dist/.verificado-<artefacto>`` con la suma, y ``publicar`` solo incluye los artefactos
cuyo sello coincide con la suma actual. Los provisionales (``dist/provisional/``) nunca entran.

Uso::

    python empaquetado/comun/sumas.py sellar   <artefacto>   # tras verificar con éxito
    python empaquetado/comun/sumas.py publicar [--dist DIR]  # (re)escribe SHA256SUMS
    python empaquetado/comun/sumas.py comprobar [--dist DIR] # equivale a sha256sum -c
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PATRONES = ("*.deb", "*-setup.exe")


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def ruta_sello(artefacto: Path) -> Path:
    return artefacto.parent / f".verificado-{artefacto.name}"


def sellar(artefacto: Path) -> None:
    if artefacto.parent.name == "provisional":
        raise SystemExit("SUMAS: los artefactos provisionales no se sellan (no son publicables)")
    if not artefacto.is_file():
        raise SystemExit(f"SUMAS: no existe {artefacto}")
    ruta_sello(artefacto).write_text(f"{sha256(artefacto)}  {artefacto.name}\n", encoding="utf-8")
    print(f"sellado {artefacto.name}")


def artefactos(dist: Path) -> list[Path]:
    return sorted(
        {p for patron in PATRONES for p in dist.glob(patron) if p.is_file() and p.name[0] != "."}
    )


def publicar(dist: Path) -> int:
    """Escribe ``SHA256SUMS`` solo con artefactos sellados. Devuelve 1 si alguno no lo está."""
    lineas: list[str] = []
    sin_sello: list[str] = []
    for art in artefactos(dist):
        sello = ruta_sello(art)
        actual = sha256(art)
        if sello.is_file() and sello.read_text("utf-8").split()[:1] == [actual]:
            lineas.append(f"{actual}  {art.name}")
        else:
            sin_sello.append(art.name)
    destino = dist / "SHA256SUMS"
    if lineas:
        destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        print(f"SHA256SUMS con {len(lineas)} artefacto(s)")
    elif destino.exists():
        destino.unlink()
    for nombre in sin_sello:
        print(f"SUMAS: {nombre} sin verificación vigente; no se publica su suma", file=sys.stderr)
    return 1 if sin_sello else 0


def comprobar(dist: Path) -> int:
    destino = dist / "SHA256SUMS"
    if not destino.is_file():
        print("SUMAS: no hay SHA256SUMS", file=sys.stderr)
        return 1
    fallo = 0
    for linea in destino.read_text("utf-8").splitlines():
        suma, _, nombre = linea.partition("  ")
        if "/" in nombre or "\\" in nombre:
            print(f"SUMAS: nombre con ruta en SHA256SUMS: {nombre}", file=sys.stderr)
            fallo = 1
            continue
        ok = (dist / nombre).is_file() and sha256(dist / nombre) == suma
        print(f"{nombre}: {'OK' if ok else 'FALLÓ'}")
        fallo = fallo or (0 if ok else 1)
    return fallo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    s = sub.add_parser("sellar")
    s.add_argument("artefacto", type=Path)
    for nombre in ("publicar", "comprobar"):
        p = sub.add_parser(nombre)
        p.add_argument("--dist", type=Path, default=RAIZ / "dist")
    args = ap.parse_args(argv)
    if args.orden == "sellar":
        sellar(args.artefacto)
        return 0
    return publicar(args.dist) if args.orden == "publicar" else comprobar(args.dist)


if __name__ == "__main__":
    raise SystemExit(main())
