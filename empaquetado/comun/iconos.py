"""Iconos de la aplicación (AR-5, DT-E9, RF-E11/E12, CA-E11.4).

Los iconos APROBADOS por el usuario viven versionados en ``empaquetado/iconos/`` (PNG de 16 a
256 px, ``proxlaunch.ico`` y ``SHA256SUMS``). La construcción (Linux y Windows) NO los redibuja:
los copia a ``build/iconos/`` después de verificar su ``SHA256SUMS`` (``copiar``), porque
redibujar con otra versión de Qt cambia los píxeles. ``generar`` conserva el renderizado desde
el SVG, pero solo para producir una propuesta y su vista previa (``build/iconos-propuesta/``)
que el usuario debe aprobar; ``aprobar --desde`` instala esa propuesta como nueva versión
aprobada y registra sus sumas.

Uso::

    python empaquetado/comun/iconos.py copiar    [--salida build/iconos]
    python empaquetado/comun/iconos.py verificar [--salida build/iconos] [--provisional]
    python empaquetado/comun/iconos.py generar   [--salida build/iconos-propuesta]
    python empaquetado/comun/iconos.py aprobar   [--desde build/iconos-propuesta]  # tras aprobar

``copiar`` y ``verificar`` no usan Qt (solo biblioteca estándar).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
from pathlib import Path

# El render no necesita pantalla: se fuerza el plugin sin ventanas antes de importar Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TAMANOS = TAMANOS_PNG = (16, 24, 32, 48, 64, 128, 256)
RAIZ = Path(__file__).resolve().parents[2]
SVG = RAIZ / "src" / "proxlaunch" / "recursos" / "marca" / "proxlaunch-icono-sin-texto.svg"
FAVICON = RAIZ / "boton-icono-favicon.png"
APROBADOS = Path(__file__).resolve().with_name("iconos-aprobados.json")
VERSIONADOS = RAIZ / "empaquetado" / "iconos"
SALIDA_POR_DEFECTO = RAIZ / "build" / "iconos"
PROPUESTA_POR_DEFECTO = RAIZ / "build" / "iconos-propuesta"
NOMBRES = tuple(f"proxlaunch-{lado}.png" for lado in TAMANOS_PNG) + ("proxlaunch.ico",)


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
    """Genera una PROPUESTA (PNG, ``.ico`` y vista previa) desde el SVG; no es lo aprobado."""
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


def leer_sumas(carpeta: Path) -> dict[str, str]:
    """Lee ``SHA256SUMS`` de la carpeta (formato ``suma␠␠nombre``, solo nombres relativos)."""
    ruta = carpeta / "SHA256SUMS"
    if not ruta.is_file():
        raise RuntimeError(f"falta {ruta}")
    sumas: dict[str, str] = {}
    for linea in ruta.read_text("utf-8").splitlines():
        suma, _, nombre = linea.partition("  ")
        if len(suma) != 64 or not nombre or "/" in nombre or "\\" in nombre:
            raise RuntimeError(f"línea no válida en {ruta}: {linea!r}")
        sumas[nombre] = suma
    return sumas


def _lado_png(datos: bytes) -> int:
    """Ancho de un PNG cuadrado leído de su cabecera IHDR (sin Qt)."""
    if datos[:8] != b"\x89PNG\r\n\x1a\n" or datos[12:16] != b"IHDR":
        raise RuntimeError("no es un PNG")
    ancho, alto = struct.unpack(">II", datos[16:24])
    if ancho != alto:
        raise RuntimeError(f"PNG no cuadrado ({ancho}x{alto})")
    return int(ancho)


def comprobar_versionados() -> dict[str, str]:
    """Verifica los iconos aprobados de ``empaquetado/iconos/``; devuelve sus sumas.

    Falla si ``SHA256SUMS`` no cubre exactamente los archivos esperados, si alguna suma no coincide,
    si el JSON de aprobación no refleja los mismos archivos o si el SVG fuente cambió desde la
    aprobación (los iconos aprobados quedarían desfasados respecto del logotipo).
    """
    sumas = leer_sumas(VERSIONADOS)
    if set(sumas) != set(NOMBRES):
        raise RuntimeError(
            f"SHA256SUMS de los iconos debe listar exactamente: {', '.join(NOMBRES)}"
        )
    for nombre, esperada in sumas.items():
        ruta = VERSIONADOS / nombre
        if not ruta.is_file():
            raise RuntimeError(f"falta el icono aprobado {ruta}")
        if sha256_archivo(ruta) != esperada:
            raise RuntimeError(f"la suma de {nombre} no coincide con empaquetado/iconos/SHA256SUMS")
    for lado in TAMANOS_PNG:
        real = _lado_png((VERSIONADOS / f"proxlaunch-{lado}.png").read_bytes())
        if real != lado:
            raise RuntimeError(f"proxlaunch-{lado}.png mide {real} px")
    if leer_tamanos_ico(VERSIONADOS / "proxlaunch.ico") != list(TAMANOS_PNG):
        raise RuntimeError("proxlaunch.ico no contiene exactamente los tamaños 16 a 256")
    try:
        aprobado = json.loads(APROBADOS.read_text("utf-8"))
    except (OSError, ValueError):
        aprobado = {}
    if aprobado.get("estado") != "aprobado":
        raise RuntimeError("los iconos aún no están aprobados (iconos-aprobados.json)")
    if aprobado.get("archivos_sha256") != sumas:
        raise RuntimeError("iconos-aprobados.json no refleja empaquetado/iconos/SHA256SUMS")
    if aprobado.get("svg_sha256") != sha256_archivo(SVG):
        raise RuntimeError(
            "el SVG fuente cambió respecto del aprobado: hay que aprobar iconos nuevos"
        )
    return sumas


def copiar(salida: Path) -> int:
    """Copia los iconos aprobados (ya verificados) a ``salida``. No redibuja nada."""
    sumas = comprobar_versionados()
    salida.mkdir(parents=True, exist_ok=True)
    for nombre in NOMBRES:
        shutil.copyfile(VERSIONADOS / nombre, salida / nombre)
    # Comprobación posterior: lo copiado es byte a byte lo aprobado.
    for nombre, suma in sumas.items():
        if sha256_archivo(salida / nombre) != suma:
            raise RuntimeError(f"la copia de {nombre} no coincide con lo aprobado")
    print(f"iconos aprobados verificados y copiados a {salida}")
    return 0


def verificar(salida: Path, provisional: bool) -> int:
    """0 si los iconos versionados están aprobados y ``salida`` tiene exactamente esos archivos."""
    try:
        sumas = comprobar_versionados()
    except RuntimeError as exc:
        if provisional and "aún no están aprobados" in str(exc):
            print("ICONOS: sin aprobación del usuario; uso PROVISIONAL (artefacto no publicable)")
            return 0
        raise
    for nombre, suma in sumas.items():
        ruta = salida / nombre
        if not ruta.is_file() or sha256_archivo(ruta) != suma:
            print(f"ICONOS: {ruta} no coincide con el icono aprobado", file=sys.stderr)
            return 1
    print("iconos coinciden con la aprobación registrada")
    return 0


def aprobar(desde: Path | None) -> int:
    """Registra como aprobados los iconos versionados (si se da ``desde``, los copia antes)."""
    if desde is not None:
        for nombre in NOMBRES:
            origen = desde / nombre
            if not origen.is_file():
                raise RuntimeError(f"falta {origen}; ejecute 'iconos.py generar'")
            VERSIONADOS.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origen, VERSIONADOS / nombre)
    sumas = {n: sha256_archivo(VERSIONADOS / n) for n in NOMBRES if (VERSIONADOS / n).is_file()}
    if set(sumas) != set(NOMBRES):
        raise RuntimeError("faltan iconos en empaquetado/iconos/")
    (VERSIONADOS / "SHA256SUMS").write_text(
        "".join(f"{sumas[n]}  {n}\n" for n in sorted(sumas)), encoding="utf-8"
    )
    registro = {"estado": "aprobado", "archivos_sha256": sumas, "svg_sha256": sha256_archivo(SVG)}
    APROBADOS.write_text(json.dumps(registro, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    comprobar_versionados()
    print(f"aprobación registrada en {APROBADOS} y {VERSIONADOS / 'SHA256SUMS'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    for nombre in ("copiar", "verificar", "generar"):
        p = sub.add_parser(nombre)
        defecto = PROPUESTA_POR_DEFECTO if nombre == "generar" else SALIDA_POR_DEFECTO
        p.add_argument("--salida", type=Path, default=defecto)
        if nombre == "verificar":
            p.add_argument("--provisional", action="store_true")
    p = sub.add_parser("aprobar")
    p.add_argument("--desde", type=Path, default=None)
    args = ap.parse_args(argv)
    try:
        if args.orden == "generar":
            generar(args.salida)
            print(f"propuesta de iconos y vista previa en {args.salida} (NO aprobada)")
            return 0
        if args.orden == "copiar":
            return copiar(args.salida)
        if args.orden == "verificar":
            return verificar(args.salida, args.provisional)
        return aprobar(args.desde)
    except RuntimeError as exc:
        print(f"ICONOS: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
