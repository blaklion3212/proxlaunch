"""Genera ``THIRD-PARTY-NOTICES.txt`` desde el entorno de build (AR-6, RF-E23, D-19).

Lista exactamente los paquetes del lockfile de ejecución (``--lock``), con su versión y los
textos de licencia que trae cada distribución instalada (``importlib.metadata``). Si un paquete
no trae texto y no tiene una excepción versionada en ``licencias-excepciones/``, falla
(CA-E23.1). Añade las licencias OFL de las fuentes incluidas y la del intérprete (PSF).

Uso (dentro del entorno donde se instaló el lockfile de ejecución)::

    python empaquetado/comun/avisos.py --lock empaquetado/requisitos/linux-ejecucion.txt \\
        --salida build/THIRD-PARTY-NOTICES.txt
"""

from __future__ import annotations

import argparse
import re
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
EXCEPCIONES = Path(__file__).resolve().with_name("licencias-excepciones")
FUENTES = RAIZ / "src" / "proxlaunch" / "recursos" / "fuentes"
_TEXTO_LICENCIA = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE)([^/]*)$", re.IGNORECASE)

# Paquetes cuya rueda no incluye el texto de su licencia: se entrega el texto oficial versionado.
# PySide6 y Qt se ofrecen como LGPL-3.0 (bibliotecas dinámicas separadas y reemplazables).
TEXTOS_EXCEPCION: dict[str, tuple[str, ...]] = {
    "pyside6-essentials": ("LGPL-3.0.txt", "GPL-3.0.txt"),
    "shiboken6": ("LGPL-3.0.txt", "GPL-3.0.txt"),
}
AVISO_QT = (
    "Qt y PySide6 (Qt for Python) se distribuyen bajo LGPL-3.0 como bibliotecas dinámicas\n"
    "separadas y reemplazables dentro de la carpeta de la aplicación (no van enlazadas en un\n"
    "único binario). Puede obtener su código fuente en https://code.qt.io/ (PySide6: repositorio\n"
    "pyside-setup) y sustituir las bibliotecas por otras compatibles de la misma versión menor.\n"
)


def normalizar(nombre: str) -> str:
    return re.sub(r"[-_.]+", "-", nombre).lower()


def paquetes_del_lock(ruta: Path) -> list[tuple[str, str]]:
    """Pares (nombre, versión) de un lockfile con hashes."""
    salida = []
    for linea in ruta.read_text("utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)", linea)
        if m:
            salida.append((normalizar(m.group(1)), m.group(2)))
    return sorted(salida)


def _distribucion(nombre: str) -> metadata.Distribution | None:
    for dist in metadata.distributions():
        if normalizar(dist.metadata["Name"] or "") == nombre:
            return dist
    return None


def textos_de(dist: metadata.Distribution) -> list[tuple[str, str]]:
    textos = []
    for archivo in dist.files or []:
        if _TEXTO_LICENCIA.search(archivo.as_posix()) and ".dist-info" in archivo.as_posix():
            try:
                texto = archivo.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if texto.strip():
                textos.append((archivo.name, texto))
    return sorted(textos)


def licencia_declarada(dist: metadata.Distribution) -> str:
    valor = dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
    return valor.strip().splitlines()[0] if valor.strip() else "no declarada"


def licencia_del_interprete() -> str | None:
    # En un venv «prefix» es el propio venv; la licencia está en la instalación base
    # (Windows: <base>\LICENSE.txt; Linux: <stdlib>/LICENSE.txt).
    prefijo = sysconfig.get_config_var("prefix") or ""
    bases = (sysconfig.get_path("stdlib"), sys.base_prefix, prefijo)
    for base in bases:
        for nombre in ("LICENSE.txt", "LICENSE"):
            ruta = Path(base) / nombre
            if ruta.is_file():
                return ruta.read_text("utf-8", errors="replace")
    ruta_exc = EXCEPCIONES / "python-psf.txt"
    return ruta_exc.read_text("utf-8") if ruta_exc.is_file() else None


def generar(lock: Path) -> str:
    paquetes = paquetes_del_lock(lock)
    if not paquetes:
        raise RuntimeError(f"el lockfile {lock} no lista paquetes")
    secciones: list[str] = []
    faltan: list[str] = []
    for nombre, version in paquetes:
        dist = _distribucion(nombre)
        if dist is None:
            raise RuntimeError(
                f"{nombre} está en el lockfile pero no está instalado en este entorno"
            )
        if dist.version != version:
            raise RuntimeError(f"{nombre}: instalado {dist.version}, el lockfile fija {version}")
        textos = textos_de(dist)
        if not textos and nombre in TEXTOS_EXCEPCION:
            textos = [(f, (EXCEPCIONES / f).read_text("utf-8")) for f in TEXTOS_EXCEPCION[nombre]]
        if not textos:
            faltan.append(nombre)
            continue
        cuerpo = [f"=== {nombre} {version} - licencia declarada: {licencia_declarada(dist)} ==="]
        for archivo, texto in textos:
            cuerpo.append(f"--- {archivo} ---\n{texto.strip()}")
        secciones.append("\n\n".join(cuerpo))
    if faltan:
        raise RuntimeError(
            "sin texto de licencia (añada su texto oficial a licencias-excepciones/): "
            + ", ".join(faltan)
        )
    for ofl in sorted(FUENTES.glob("*-OFL.txt")):
        secciones.append(
            f"=== Fuente incluida: {ofl.name.removesuffix('-OFL.txt')} (SIL OFL 1.1) ===\n"
            + ofl.read_text("utf-8").strip()
        )
    psf = licencia_del_interprete()
    if psf is None:
        raise RuntimeError("no se encontró el texto de licencia del intérprete (PSF)")
    secciones.append(
        f"=== CPython {sys.version.split()[0]} (Python Software Foundation License) ===\n"
        + psf.strip()
    )
    cabecera = [
        "ProxLaunch - Avisos de software de terceros",
        "",
        "Este archivo se genera desde el lockfile de ejecución; no se edita a mano.",
        "",
        AVISO_QT,
        "Componentes incluidos (lockfile de ejecución):",
        *[f"  - {n}=={v}" for n, v in paquetes],
        f"  - CPython {sys.version.split()[0]}",
        "  - Fuentes: Open Sans, JetBrains Mono (SIL OFL 1.1)",
        "",
    ]
    return "\n".join(cabecera) + "\n" + "\n\n\n".join(secciones) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        texto = generar(args.lock)
    except RuntimeError as exc:
        print(f"AVISOS: {exc}", file=sys.stderr)
        return 1
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(texto, encoding="utf-8")
    print(f"escrito {args.salida} ({len(texto)} caracteres)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
