#!/usr/bin/env bash
# Herramientas de construcción de Linux con versión y SHA-256 fijados (RF-E21). Se carga con `source`.
# No ejecuta nada por sí mismo.

UV_VERSION="0.13.7"
UV_ARCHIVO="uv-x86_64-unknown-linux-musl.tar.gz"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_ARCHIVO}"
UV_SHA256="287491da03f2a785c70fa75b13e1f849918c2f2b5415fe84876b8214eeb792f9"
# CPython gestionado por uv (python-build-standalone, con libpython compartida). uv comprueba el
# SHA-256 de cada distribución contra los valores que trae su propia tabla de descargas.
PYTHON_BUILD_VERSION="3.13.18"

# obtener_uv <carpeta_cache> : descarga uv (si falta), verifica su SHA-256 y escribe la ruta en stdout.
obtener_uv() {
    local cache="$1"
    mkdir -p "$cache"
    local archivo="$cache/$UV_ARCHIVO"
    if [ ! -f "$archivo" ] || ! echo "$UV_SHA256  $archivo" | sha256sum -c --status -; then
        curl --proto '=https' --tlsv1.2 -fsSL --retry 3 -o "$archivo" "$UV_URL"
        echo "$UV_SHA256  $archivo" | sha256sum -c --status - \
            || { echo "ERROR: la suma SHA-256 de uv no coincide con la fijada" >&2; return 1; }
    fi
    local destino="$cache/uv-$UV_VERSION"
    if [ ! -x "$destino/uv" ]; then
        mkdir -p "$destino"
        tar -xzf "$archivo" -C "$destino" --strip-components=1
    fi
    echo "$destino/uv"
}
