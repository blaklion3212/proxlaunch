#!/usr/bin/env bash
# Herramientas de construcción de Linux con versión y SHA-256 fijados (RF-E21). Se carga con `source`.
# No ejecuta nada por sí mismo.

UV_VERSION="0.13.7"
UV_ARCHIVO="uv-x86_64-unknown-linux-musl.tar.gz"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_ARCHIVO}"
UV_SHA256="287491da03f2a785c70fa75b13e1f849918c2f2b5415fe84876b8214eeb792f9"
# SHA-256 del binario `uv` extraído de ese archivo (se vuelve a comprobar cada vez que se reutiliza).
UV_BIN_SHA256="500c0ec54518b2a53380783586b75a79907d937d741ebb04236d90a50ed5ab26"
# CPython gestionado por uv (python-build-standalone, con libpython compartida). uv comprueba el
# SHA-256 de cada distribución contra los valores que trae su propia tabla de descargas.
PYTHON_BUILD_VERSION="3.13.18"

# verificar_binario_uv <ruta> : verdadero si el SHA-256 del binario es el fijado.
verificar_binario_uv() {
    [ -f "$1" ] && echo "$UV_BIN_SHA256  $1" | sha256sum -c --status - 2>/dev/null
}

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
    # El uv ya extraído solo se reutiliza si su SHA-256 sigue siendo el fijado (SEG-M5-05); si no,
    # se extrae de nuevo del archivo ya verificado.
    if [ ! -x "$destino/uv" ] || ! verificar_binario_uv "$destino/uv"; then
        rm -rf -- "${destino:?}"
        mkdir -p "$destino"
        tar -xzf "$archivo" -C "$destino" --strip-components=1
        verificar_binario_uv "$destino/uv" \
            || { echo "ERROR: el binario uv extraído no coincide con la suma fijada" >&2; return 1; }
    fi
    echo "$destino/uv"
}
