"""Iconos de la aplicación y vista previa para su aprobación (AR-5, DT-E9, RF-E11/E12, CA-E11.4).

Renderiza ``proxlaunch-icono-sin-texto.svg`` (el mismo SVG que usa la ventana) con ``QSvgRenderer``
fuera de pantalla, sin retoques, a PNG de 16 a 256 px y a un ``.ico`` multirresolución con entradas
PNG. También genera ``vista-previa.png``: todos los tamaños sobre fondo claro y oscuro, junto al
original. Los iconos NO se integran en ningún artefacto hasta que el usuario apruebe la vista
previa; la aprobación se registra con ``aprobar`` en ``iconos-aprobados.json`` y el build falla
(``verificar``) si el SVG o los píxeles generados ya no coinciden con lo aprobado.

Uso::

    python empaquetado/comun/iconos.py generar   [--salida build/iconos]
    python empaquetado/comun/iconos.py verificar [--salida build/iconos] [--provisional]
    python empaquetado/comun/iconos.py aprobar   [--salida build/iconos]   # SOLO tras la aprobación
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

# El render no necesita pantalla: se fuerza el plugin sin ventanas antes de importar Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parents[2]
SVG = RAIZ / "src" / "proxlaunch" / "recursos" / "marca" / "proxlaunch-icono-sin-texto.svg"
FAVICON = RAIZ / "boton-icono-favicon.png"
APROBADOS = Path(__file__).resolve().with_name("iconos-aprobados.json")
SALIDA_POR_DEFECTO = RAIZ / "build" / "iconos"
TAMANOS = (16, 24, 32, 48, 64, 128, 256)


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def sha256_archivo(ruta: Path) -> str:
    return sha256_bytes(ruta.read_bytes())


def _renderizar(lado: int):  # noqa: ANN202 - tipo de Qt importado de forma diferida
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        raise RuntimeError(f"SVG no válido: {SVG}")
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(pintor)
    pintor.end()
    return imagen


def _pixeles_sha256(imagen) -> str:  # noqa: ANN001
    """Suma de los píxeles RGBA (no depende del codificador PNG de cada plataforma)."""
    return sha256_bytes(bytes(imagen.constBits()))


def escribir_ico(entradas: list[tuple[int, bytes]], destino: Path) -> None:
    """ICO con entradas PNG: cabecera + directorio + datos (formato trivial, sin dependencias)."""
    cabecera = struct.pack("<HHH", 0, 1, len(entradas))
    directorio = b""
    datos = b""
    desplazamiento = 6 + 16 * len(entradas)
    for lado, png in entradas:
        dim = 0 if lado >= 256 else lado
        directorio += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), desplazamiento)
        datos += png
        desplazamiento += len(png)
    destino.write_bytes(cabecera + directorio + datos)


def leer_tamanos_ico(ruta: Path) -> list[int]:
    datos = ruta.read_bytes()
    _, tipo, n = struct.unpack_from("<HHH", datos, 0)
    if tipo != 1:
        raise ValueError("no es un .ico")
    lados = []
    for i in range(n):
        ancho = struct.unpack_from("<B", datos, 6 + 16 * i)[0]
        lados.append(ancho or 256)
    return lados


def _hoja_de_vista_previa(salida: Path) -> Path:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    margen = 24
    ancho_panel = 700
    alto = 640
    hoja = QImage(margen * 3 + ancho_panel * 2 + 340, alto, QImage.Format.Format_ARGB32)
    hoja.fill(QColor("#888888"))
    p = QPainter(hoja)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    fuente = QFont("DejaVu Sans", 9)
    p.setFont(fuente)

    def paneles(x0: int, color: str, texto: str) -> None:
        p.fillRect(x0, margen, ancho_panel, alto - 2 * margen, QColor(color))
        p.setPen(QColor("#FFFFFF" if color == "#1E1E1E" else "#202020"))
        p.drawText(x0 + 10, margen + 18, f"Fondo {texto}: tamaños generados (escala 1:1)")
        x = x0 + 14
        base = margen + 40 + 256
        for lado in TAMANOS:
            png = QImage(str(salida / f"proxlaunch-{lado}.png"))
            p.drawImage(x, base - lado, png)
            etiqueta = QRect(x - 4, base + 6, lado + 8, 16)
            p.drawText(etiqueta, Qt.AlignmentFlag.AlignHCenter, str(lado))
            x += lado + 14
        # Ampliación x3 de los tamaños pequeños, sin suavizar, para ver el píxel.
        x = x0 + 14
        y = base + 36
        for lado in (16, 24, 32, 48):
            png = QImage(str(salida / f"proxlaunch-{lado}.png"))
            p.drawImage(QRect(x, y, lado * 3, lado * 3), png)
            x += lado * 3 + 14

    paneles(margen, "#F3F3F3", "claro")
    paneles(margen * 2 + ancho_panel, "#1E1E1E", "oscuro")

    # Original: el SVG a 256 px (referencia directa) y el favicon del repositorio.
    x = margen * 3 + ancho_panel * 2
    p.fillRect(x, margen, 340, alto - 2 * margen, QColor("#FFFFFF"))
    p.setPen(QColor("#202020"))
    p.drawText(x + 10, margen + 18, "Original (SVG sin texto, 256 px)")
    p.drawImage(x + 40, margen + 30, _renderizar(256))
    if FAVICON.is_file():
        p.drawText(x + 10, margen + 320, "Favicon del repositorio (referencia)")
        fav = QImage(str(FAVICON)).scaledToWidth(128, Qt.TransformationMode.SmoothTransformation)
        p.drawImage(x + 40, margen + 332, fav)
    p.end()
    destino = salida / "vista-previa.png"
    if not hoja.save(str(destino), "PNG"):
        raise RuntimeError("no se pudo guardar la vista previa")
    return destino


def generar(salida: Path) -> dict[str, object]:
    """Genera PNG, ``.ico`` y vista previa en ``salida``; devuelve el inventario con sumas."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QGuiApplication

    _app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # necesario para el texto
    salida.mkdir(parents=True, exist_ok=True)
    inventario: dict[str, object] = {"svg_sha256": sha256_archivo(SVG), "pixeles_sha256": {}}
    entradas: list[tuple[int, bytes]] = []
    for lado in TAMANOS:
        imagen = _renderizar(lado)
        if imagen.isNull() or all(imagen.pixelColor(x, x).alpha() == 0 for x in range(lado)):
            raise RuntimeError(f"el icono de {lado} px salió vacío")
        destino = salida / f"proxlaunch-{lado}.png"
        if not imagen.save(str(destino), "PNG"):
            raise RuntimeError(f"no se pudo escribir {destino}")
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        imagen.save(buf, "PNG")
        entradas.append((lado, bytes(buf.data())))
        inventario["pixeles_sha256"][f"proxlaunch-{lado}.png"] = _pixeles_sha256(imagen)  # type: ignore[index]
    escribir_ico(entradas, salida / "proxlaunch.ico")
    _hoja_de_vista_previa(salida)
    return inventario


def _inventario_actual(salida: Path) -> dict[str, object]:
    """Recalcula las sumas de los PNG ya generados."""
    from PySide6.QtGui import QImage

    pix = {}
    for lado in TAMANOS:
        ruta = salida / f"proxlaunch-{lado}.png"
        if not ruta.is_file():
            raise RuntimeError(f"falta {ruta}; ejecute 'iconos.py generar'")
        imagen = QImage(str(ruta)).convertToFormat(QImage.Format.Format_ARGB32)
        pix[ruta.name] = _pixeles_sha256(imagen)
    return {"svg_sha256": sha256_archivo(SVG), "pixeles_sha256": pix}


def verificar(salida: Path, provisional: bool) -> int:
    """0 si lo generado coincide con lo aprobado (o si es una verificación provisional)."""
    try:
        aprobado = json.loads(APROBADOS.read_text("utf-8"))
    except (OSError, ValueError):
        aprobado = {}
    if aprobado.get("estado") != "aprobado":
        if provisional:
            print("ICONOS: sin aprobación del usuario; uso PROVISIONAL (artefacto no publicable)")
            return 0
        print("ICONOS: los iconos aún no están aprobados (iconos-aprobados.json)", file=sys.stderr)
        return 1
    actual = _inventario_actual(salida)
    if actual["svg_sha256"] != aprobado.get("svg_sha256"):
        print("ICONOS: el SVG fuente cambió respecto del aprobado", file=sys.stderr)
        return 1
    if actual["pixeles_sha256"] != aprobado.get("pixeles_sha256"):
        print("ICONOS: los píxeles generados no coinciden con lo aprobado", file=sys.stderr)
        return 1
    print("iconos coinciden con la aprobación registrada")
    return 0


def aprobar(salida: Path) -> int:
    inv = _inventario_actual(salida)
    registro = {"estado": "aprobado", **inv}
    APROBADOS.write_text(json.dumps(registro, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"aprobación registrada en {APROBADOS}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    for nombre in ("generar", "verificar", "aprobar"):
        p = sub.add_parser(nombre)
        p.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)
        if nombre == "verificar":
            p.add_argument("--provisional", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.orden == "generar":
            generar(args.salida)
            print(f"iconos y vista previa en {args.salida}")
            return 0
        if args.orden == "verificar":
            return verificar(args.salida, args.provisional)
        return aprobar(args.salida)
    except RuntimeError as exc:
        print(f"ICONOS: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
