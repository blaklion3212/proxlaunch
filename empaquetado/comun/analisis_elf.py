"""Análisis de binarios ELF del congelado de Linux: dependencias del sistema y glibc.

Subcomandos (solo Linux; usan ``ldd``, ``objdump`` y ``dpkg``)::

    analisis_elf.py paquetes  <carpeta>              # paquetes de sistema que la app usa
    analisis_elf.py comprobar <carpeta> <control>    # CA-E02.3: sin «not found» y Depends completo
    analisis_elf.py glibc     <carpeta> [--maximo 2.35]  # CA-E05.1: versión máxima de glibc exigida

``paquetes`` resuelve cada biblioteca que carga el congelado y no está dentro de él al paquete de
Debian que la contiene; ``comprobar`` exige que todos estén en ``Depends`` del ``control``.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def archivos_elf(carpeta: Path) -> list[Path]:
    """Archivos ELF regulares (ejecutables y bibliotecas) bajo ``carpeta``."""
    salida = []
    for ruta in sorted(carpeta.rglob("*")):
        if ruta.is_symlink() or not ruta.is_file():
            continue
        try:
            with ruta.open("rb") as f:
                if f.read(4) == b"\x7fELF":
                    salida.append(ruta)
        except OSError:
            continue
    return salida


def _entorno_ldd(carpeta: Path) -> dict[str, str]:
    """Entorno con ``LD_LIBRARY_PATH`` como lo deja el arranque de PyInstaller."""
    dirs = {str(p.parent) for p in carpeta.rglob("*.so*") if p.is_file()}
    entorno = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}
    entorno["LD_LIBRARY_PATH"] = ":".join(sorted(dirs))
    return entorno


def _necesarias(elf: Path) -> set[str]:
    """Sonames que el ELF declara como dependencia directa (``NEEDED``)."""
    res = subprocess.run(["objdump", "-p", str(elf)], capture_output=True, text=True, check=False)
    return set(re.findall(r"^\s*NEEDED\s+(\S+)", res.stdout, re.MULTILINE))


def resolver(carpeta: Path) -> tuple[set[str], set[str]]:
    """(rutas del sistema que el congelado enlaza directamente, nombres «not found»).

    Solo cuentan las dependencias directas (``NEEDED``): las transitivas las traen los paquetes
    declarados. Lo que ``ldd`` no encuentra se reporta aparte.
    """
    entorno = _entorno_ldd(carpeta)
    carpeta_real = str(carpeta.resolve())
    sistema: set[str] = set()
    faltan: set[str] = set()
    for elf in archivos_elf(carpeta):
        res = subprocess.run(["ldd", str(elf)], capture_output=True, text=True, env=entorno)
        resueltas: dict[str, str] = {}
        for linea in res.stdout.splitlines():
            m = re.match(r"\s*(\S+) => (\S+) \(0x", linea)
            if m:
                resueltas[m.group(1)] = m.group(2)
            elif "not found" in linea:
                faltan.add(f"{linea.split()[0]} (requerida por {elf.relative_to(carpeta)})")
        for soname in _necesarias(elf):
            ruta = resueltas.get(soname)
            if ruta and not os.path.realpath(ruta).startswith(carpeta_real):
                sistema.add(ruta)
    return sistema, faltan


def paquete_de(ruta: str) -> str | None:
    """Paquete de Debian dueño de ``ruta`` (la ruta, su destino real o su equivalente en /usr)."""
    candidatos = [ruta, os.path.realpath(ruta)]
    if ruta.startswith(("/lib/", "/lib64/")):
        candidatos.append("/usr" + ruta)
    for candidato in dict.fromkeys(candidatos):
        res = subprocess.run(
            ["dpkg-query", "-S", candidato], capture_output=True, text=True, check=False
        )
        if res.returncode == 0 and res.stdout:
            return res.stdout.split(":")[0].strip()
    return None


def paquetes_de_sistema(carpeta: Path) -> tuple[set[str], list[str]]:
    sistema, faltan = resolver(carpeta)
    paquetes: set[str] = set()
    problemas = sorted(faltan)
    for ruta in sorted(sistema):
        paquete = paquete_de(ruta)
        if paquete is None:
            problemas.append(f"{ruta} no pertenece a ningún paquete de Debian")
        else:
            paquetes.add(paquete)
    return paquetes, problemas


def depends_declarados(control: Path) -> set[str]:
    texto = control.read_text("utf-8")
    m = re.search(r"^Depends:\s*((?:.*\n(?:[ \t].*\n?)*))", texto, re.MULTILINE)
    if not m:
        return set()
    nombres = set()
    for parte in m.group(1).replace("\n", " ").split(","):
        primero = parte.split("|")[0].strip()
        nombre = re.split(r"[\s(:]", primero)[0]
        if nombre:
            nombres.add(nombre)
    return nombres


def glibc_maxima(carpeta: Path) -> tuple[tuple[int, int], str]:
    maximo, donde = (0, 0), ""
    for elf in archivos_elf(carpeta):
        res = subprocess.run(["objdump", "-T", str(elf)], capture_output=True, text=True)
        for m in re.finditer(r"GLIBC_(\d+)\.(\d+)(?:\.\d+)?", res.stdout):
            version = (int(m.group(1)), int(m.group(2)))
            if version > maximo:
                maximo, donde = version, str(elf.relative_to(carpeta))
    return maximo, donde


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("paquetes").add_argument("carpeta", type=Path)
    c = sub.add_parser("comprobar")
    c.add_argument("carpeta", type=Path)
    c.add_argument("control", type=Path)
    g = sub.add_parser("glibc")
    g.add_argument("carpeta", type=Path)
    g.add_argument("--maximo", default=None, help="versión máxima admitida, p. ej. 2.35")
    args = ap.parse_args(argv)

    if args.orden == "paquetes":
        paquetes, problemas = paquetes_de_sistema(args.carpeta)
        print("\n".join(sorted(paquetes)))
        for p in problemas:
            print(f"ELF: {p}", file=sys.stderr)
        return 1 if problemas else 0
    if args.orden == "comprobar":
        paquetes, problemas = paquetes_de_sistema(args.carpeta)
        declarados = depends_declarados(args.control)
        # En Ubuntu 24.04 algunos paquetes llevan el sufijo «t64» y proveen el nombre antiguo.
        sin_t64 = {re.sub(r"t64$", "", d) for d in declarados}
        for p in sorted(x for x in paquetes if re.sub(r"t64$", "", x) not in sin_t64):
            problemas.append(f"el congelado usa el paquete '{p}' y Depends no lo declara")
        for p in problemas:
            print(f"ELF: {p}", file=sys.stderr)
        if not problemas:
            print(f"ldd sin «not found»; {len(paquetes)} paquetes de sistema, todos en Depends")
        return 1 if problemas else 0
    version, donde = glibc_maxima(args.carpeta)
    texto = f"{version[0]}.{version[1]}"
    print(f"glibc máxima requerida: {texto} ({donde})")
    if args.maximo:
        tope = tuple(int(x) for x in args.maximo.split("."))
        if version > tope:
            print(f"ELF: {texto} supera el máximo admitido {args.maximo}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
