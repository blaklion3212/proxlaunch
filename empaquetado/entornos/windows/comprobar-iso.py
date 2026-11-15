"""Comprueba la ISO de Windows 11 y registra su origen (RF-E42, HV-E16, CA-E42.1).

Solo biblioteca estándar. Verifica que el archivo es una imagen UDF (formato de las ISO de Windows)
de tamaño razonable, calcula su SHA-256 y escribe un registro con el nombre, el tamaño, la suma,
la etiqueta del volumen, la página oficial de descarga y la fecha. Si se da ``--sha256-esperada``
(la suma que el usuario confirmó contra la lista oficial «Verificar la descarga» de Microsoft), la
calculada debe coincidir o se rechaza la ISO; si no se da, el registro deja constancia de que la
suma es solo la calculada localmente.

Uso::

    python3 -I comprobar-iso.py <iso> --registro <ISO-ORIGEN.txt> [--url <pagina oficial>]
        [--sha256-esperada <suma> --fecha-verificacion AAAA-MM-DD]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

SECTOR = 2048
TAMANO_MINIMO = 3 * 1024**3  # una ISO de Windows 11 pesa varios GB
URL_OFICIAL = "https://www.microsoft.com/es-mx/software-download/windows11"


def identificadores_de_volumen(ruta: Path) -> set[bytes]:
    """Identificadores de la secuencia de reconocimiento de volumen (sectores 16 a 63)."""
    ids: set[bytes] = set()
    with ruta.open("rb") as f:
        for n in range(16, 64):
            f.seek(n * SECTOR)
            bloque = f.read(8)
            if len(bloque) < 6:
                break
            ids.add(bytes(bloque[1:6]))
    return ids


def etiqueta_iso9660(ruta: Path) -> str:
    with ruta.open("rb") as f:
        f.seek(16 * SECTOR)
        pvd = f.read(SECTOR)
    if pvd[1:6] != b"CD001":
        return ""
    return pvd[40:72].decode("ascii", errors="replace").strip()


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("iso", type=Path)
    ap.add_argument("--registro", type=Path, required=True)
    ap.add_argument("--url", default=URL_OFICIAL)
    ap.add_argument("--sha256-esperada", default="")
    ap.add_argument("--fecha-verificacion", default="")
    args = ap.parse_args(argv)
    iso: Path = args.iso
    if not iso.is_file():
        print(f"ISO: no existe {iso}", file=sys.stderr)
        return 1
    tamano = iso.stat().st_size
    if tamano < TAMANO_MINIMO:
        print(
            f"ISO: {iso.name} pesa solo {tamano} bytes; una de Windows 11 pesa varios GB",
            file=sys.stderr,
        )
        return 1
    ids = identificadores_de_volumen(iso)
    if not (ids & {b"NSR02", b"NSR03"}):
        print(f"ISO: {iso.name} no es una imagen UDF (formato de Windows)", file=sys.stderr)
        return 1
    etiqueta = etiqueta_iso9660(iso)
    suma = sha256_de(iso)
    esperada = args.sha256_esperada.strip().lower()
    if esperada and esperada != suma:
        print(f"ISO: SHA-256 {suma} distinto del esperado {esperada}", file=sys.stderr)
        return 1
    if esperada:
        verificacion = (
            "suma verificada contra la lista oficial de Microsoft («Verificar la descarga»)"
        )
        if args.fecha_verificacion:
            verificacion += f", fecha {args.fecha_verificacion}"
    else:
        verificacion = "suma calculada localmente (sin suma oficial con la que compararla)"
    lineas = [
        "Origen y verificación de la ISO de Windows 11 (RF-E42)",
        f"archivo: {iso.name}",
        f"tamaño: {tamano} bytes",
        f"sha256: {suma}",
        f"etiqueta del volumen: {etiqueta or '(no legible)'}",
        f"pagina oficial de descarga (Microsoft): {args.url}",
        f"fecha del registro: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"verificación: {verificacion}",
        "Windows 11 Pro sin activar (ISO oficial de Microsoft); no se redistribuye.",
    ]
    args.registro.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.registro, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as salida:
        salida.write("\n".join(lineas) + "\n")
    print(f"ISO válida (UDF): {iso.name}")
    print(f"  SHA-256: {suma}")
    print(f"  etiqueta: {etiqueta or '(no legible)'}")
    print(f"  registro: {args.registro}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
