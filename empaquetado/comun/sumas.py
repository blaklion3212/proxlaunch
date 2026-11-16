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
import importlib.util
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PATRONES = ("*.deb", "*-setup.exe")
# Artefactos con la versión en el nombre; los que no siguen este formato no se filtran por versión.
NOMBRE_CON_VERSION = (
    re.compile(r"proxlaunch_(\d+\.\d+\.\d+)_amd64\.deb"),
    re.compile(r"proxlaunch-(\d+\.\d+\.\d+)-windows-x64-setup\.exe"),
)


def version_vigente() -> str:
    """Versión del código (``version.py`` de esta carpeta, cargado por ruta: ``python -I``)."""
    spec = importlib.util.spec_from_file_location(
        "sumas_version", Path(__file__).resolve().with_name("version.py")
    )
    if spec is None or spec.loader is None:
        raise SystemExit("SUMAS: no se pudo cargar version.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    try:
        return modulo.validar_semver(modulo.version_del_codigo())
    except modulo.ErrorVersion as exc:
        raise SystemExit(f"SUMAS: no se pudo determinar la versión vigente: {exc}") from exc


def version_del_nombre(nombre: str) -> str | None:
    for patron in NOMBRE_CON_VERSION:
        m = patron.fullmatch(nombre)
        if m:
            return m.group(1)
    return None


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
    ruta_sello(artefacto).write_text(
        f"{sha256(artefacto)}  {artefacto.name}\n", encoding="utf-8", newline="\n"
    )
    print(f"sellado {artefacto.name}")


def artefactos(dist: Path) -> list[Path]:
    return sorted(
        {p for patron in PATRONES for p in dist.glob(patron) if p.is_file() and p.name[0] != "."}
    )


def publicar(dist: Path, version: str | None = None) -> int:
    """Escribe ``SHA256SUMS`` solo con artefactos sellados de la versión vigente.

    Devuelve 1 si algún artefacto de la versión vigente no está sellado. Los artefactos de OTRA
    versión (restos de construcciones anteriores o de pruebas) se omiten con un aviso (QA-M5-11).
    ``SHA256SUMS`` se escribe de forma atómica (temporal + ``os.replace``).
    """
    vigente = version if version is not None else version_vigente()
    lineas: list[str] = []
    sin_sello: list[str] = []
    for art in artefactos(dist):
        de_version = version_del_nombre(art.name)
        if de_version is not None and de_version != vigente:
            print(
                f"SUMAS: {art.name} es de la versión {de_version} y la vigente es {vigente}; "
                "se omite",
                file=sys.stderr,
            )
            continue
        sello = ruta_sello(art)
        actual = sha256(art)
        if sello.is_file() and sello.read_text("utf-8").split()[:1] == [actual]:
            lineas.append(f"{actual}  {art.name}")
        else:
            sin_sello.append(art.name)
    destino = dist / "SHA256SUMS"
    if lineas:
        temporal = dist / f".SHA256SUMS.{os.getpid()}.tmp"
        try:
            # newline="\n": en Windows, el modo texto escribiría CRLF y sha256sum -c fallaría.
            temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
            os.replace(temporal, destino)
        finally:
            temporal.unlink(missing_ok=True)
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
