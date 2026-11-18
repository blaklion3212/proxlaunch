"""Genera ``dist/proxlaunch-<versión>-guia-usuario.pdf`` a partir de ``docs/guia-usuario.md``.

Convierte el Markdown a HTML (Python-Markdown) y lo maqueta con WeasyPrint usando la hoja de
estilos ``guia_pdf.css`` de esta carpeta: portada, índice con números de página, enlaces internos,
pie con número de página y encabezado con el capítulo. No usa red ni modifica el repositorio salvo
el PDF de salida. Las dependencias NO son del proyecto: se instalan en un entorno temporal.

Uso::

    uv venv /tmp/venv-pdf && uv pip install --python /tmp/venv-pdf/bin/python markdown weasyprint
    /tmp/venv-pdf/bin/python empaquetado/comun/generar_pdf_guia.py [--salida RUTA]
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import re
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
GUIA = RAIZ / "docs" / "guia-usuario.md"
CSS = Path(__file__).resolve().with_name("guia_pdf.css")
FUENTES = RAIZ / "src" / "proxlaunch" / "recursos" / "fuentes"
LOGO = RAIZ / "src" / "proxlaunch" / "recursos" / "marca" / "proxlaunch-logotipo-oscuro.svg"
MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def version_vigente() -> str:
    """Versión del código (``version.py`` de esta carpeta, cargado por ruta)."""
    spec = importlib.util.spec_from_file_location(
        "guia_version", Path(__file__).resolve().with_name("version.py")
    )
    if spec is None or spec.loader is None:
        raise SystemExit("GUIA-PDF: no se pudo cargar version.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return str(modulo.version_del_codigo())


def slug(valor: str, separador: str = "-") -> str:
    """Ancla al estilo de GitHub (conserva acentos y ñ), que es la que usa la guía."""
    valor = re.sub(r"<[^>]+>", "", html.unescape(valor)).strip().lower()
    valor = re.sub(r"[^\w\s-]", "", valor)
    return re.sub(r"\s+", separador, valor)


def preparar_markdown(texto: str) -> str:
    """Quita el «Índice» escrito a mano (el PDF genera el suyo con páginas)."""
    return re.sub(r"^## Índice\n.*?(?=^## )", "", texto, flags=re.S | re.M)


def convertir(texto: str) -> tuple[str, list[dict]]:
    """Devuelve ``(html_cuerpo, tokens_del_toc)``."""
    import markdown

    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "attr_list", "sane_lists"],
        extension_configs={"toc": {"slugify": slug, "toc_depth": "2-3"}},
    )
    cuerpo = md.convert(texto)
    # Rutas locales (ejemplos, otros documentos): en el PDF no existen; se muestran como texto.
    cuerpo = re.sub(
        r'<a href="(?!#|https?://)[^"]*">(.*?)</a>',
        r'<span class="local">\1</span>',
        cuerpo,
        flags=re.S,
    )
    # Las imágenes se resuelven contra docs/ (rutas relativas ``img/...``).
    return cuerpo, md.toc_tokens  # type: ignore[attr-defined]


def aplanar(tokens: list[dict]) -> list[dict]:
    salida: list[dict] = []
    for t in tokens:
        salida.append(t)
        salida.extend(aplanar(t.get("children", [])))
    return salida


def indice_html(tokens: list[dict]) -> str:
    filas = []
    for t in aplanar(tokens):
        if t["level"] not in (2, 3):
            continue
        filas.append(f'<li class="n{t["level"]}"><a href="#{t["id"]}">{t["name"]}</a></li>')
    return '<nav id="indice"><h2 class="sin-num">Índice</h2><ul>' + "".join(filas) + "</ul></nav>"


def documento(version: str, fecha: str, cuerpo: str, indice: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>ProxLaunch — Guía de usuario</title>
<meta name="author" content="ProxLaunch">
</head><body>
<section id="portada">
  <img class="logo" src="{LOGO.as_uri()}" alt="ProxLaunch">
  <h1 class="titulo">ProxLaunch — Guía de usuario</h1>
  <p class="version">Versión {version}</p>
  <p class="fecha">{fecha}</p>
</section>
{indice}
<main>{cuerpo}</main>
</body></html>"""


def generar(salida: Path) -> None:
    try:
        from weasyprint import CSS as Css
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as exc:
        raise SystemExit(
            f"GUIA-PDF: falta una dependencia ({exc.name}); ver el encabezado del script"
        ) from exc

    version = version_vigente()
    hoy = date.today()
    fecha = f"{hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}"
    cuerpo, tokens = convertir(preparar_markdown(GUIA.read_text(encoding="utf-8")))
    texto = documento(version, fecha, cuerpo, indice_html(tokens))
    config = FontConfiguration()
    hoja = Css(
        string=CSS.read_text(encoding="utf-8").replace("{{FUENTES}}", FUENTES.as_uri()),
        font_config=config,
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=texto, base_url=(RAIZ / "docs").as_uri() + "/").write_pdf(
        str(salida), stylesheets=[hoja], font_config=config
    )
    print(f"GUIA-PDF: {salida} ({salida.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", type=Path, help="ruta del PDF (por defecto dist/…)")
    args = ap.parse_args()
    salida = args.salida or RAIZ / "dist" / f"proxlaunch-{version_vigente()}-guia-usuario.pdf"
    generar(salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
