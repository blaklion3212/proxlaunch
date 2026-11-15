"""Descarga y verifica las herramientas de Windows fijadas en ``herramientas.json`` (RF-E21).

Se ejecuta en el anfitrión (Linux o Windows) con la biblioteca estándar. Cada archivo se descarga
por HTTPS a un temporal, se compara su SHA-256 con el fijado y solo entonces se mueve al destino;
si la suma no coincide se borra y falla. No ejecuta nada de lo descargado.

Uso::

    python3 -I descargar-herramientas.py [--destino DIR] [--solo-verificar]

Imprime una línea por archivo con su ruta; con ``--listar`` solo muestra el inventario.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

JSON = Path(__file__).resolve().with_name("herramientas.json")
DESTINO_POR_DEFECTO = Path.home() / "aprovprox-empaquetado" / "descargas" / "windows"
LIMITE_BYTES = 200 * 1024 * 1024


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def cargar() -> dict[str, dict[str, object]]:
    datos = json.loads(JSON.read_text("utf-8"))
    return dict(datos["herramientas"])


def validar_entrada(nombre: str, h: dict[str, object]) -> None:
    url = str(h["url"])
    suma = str(h["sha256"])
    archivo = str(h["archivo"])
    if not url.startswith("https://"):
        raise SystemExit(f"HERRAMIENTAS: {nombre}: la URL debe ser HTTPS")
    if len(suma) != 64 or any(c not in "0123456789abcdef" for c in suma):
        raise SystemExit(f"HERRAMIENTAS: {nombre}: SHA-256 no válido")
    if "/" in archivo or "\\" in archivo or archivo.startswith("."):
        raise SystemExit(f"HERRAMIENTAS: {nombre}: nombre de archivo no válido")


def obtener(nombre: str, h: dict[str, object], destino: Path, solo_verificar: bool) -> Path:
    validar_entrada(nombre, h)
    ruta = destino / str(h["archivo"])
    suma = str(h["sha256"])
    if ruta.is_file() and sha256_de(ruta) == suma:
        print(f"{nombre}: ya descargado y verificado -> {ruta}")
        return ruta
    if solo_verificar:
        raise SystemExit(f"HERRAMIENTAS: {nombre}: falta o su suma no coincide ({ruta})")
    destino.mkdir(parents=True, exist_ok=True, mode=0o700)
    print(f"{nombre}: descargando {h['url']}")
    fd, temporal = tempfile.mkstemp(dir=destino, prefix=".descarga-")
    try:
        total = 0
        with (
            os.fdopen(fd, "wb") as salida,
            urllib.request.urlopen(str(h["url"]), timeout=60) as respuesta,  # noqa: S310
        ):
            for bloque in iter(lambda: respuesta.read(1 << 20), b""):
                total += len(bloque)
                if total > LIMITE_BYTES:
                    raise SystemExit(f"HERRAMIENTAS: {nombre}: la descarga supera el límite")
                salida.write(bloque)
        real = sha256_de(Path(temporal))
        if real != suma:
            raise SystemExit(
                f"HERRAMIENTAS: {nombre}: SHA-256 distinto (esperada {suma}, real {real})"
            )
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal):
            os.unlink(temporal)
    print(f"{nombre}: SHA-256 verificado ({suma}) -> {ruta}")
    return ruta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--destino", type=Path, default=DESTINO_POR_DEFECTO)
    ap.add_argument("--solo-verificar", action="store_true", help="no descarga: solo comprueba")
    ap.add_argument("--listar", action="store_true", help="muestra el inventario fijado")
    args = ap.parse_args(argv)
    herramientas = cargar()
    if args.listar:
        for nombre, h in herramientas.items():
            print(f"{nombre}: {h['archivo']} sha256={h['sha256']}")
        return 0
    for nombre, h in herramientas.items():
        obtener(nombre, h, args.destino, args.solo_verificar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
