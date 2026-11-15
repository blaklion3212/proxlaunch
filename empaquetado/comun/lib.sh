#!/usr/bin/env bash
# Funciones comunes de los scripts de empaquetado para Linux. Se carga con `source`; no ejecuta nada.
# Define: msg, die, paso, iniciar_registro, resumen_tiempos, guardia_laboratorio, preparar_uv,
# crear_entorno.

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TIEMPOS=()

msg() { printf '[%s] %s\n' "${NOMBRE_SCRIPT:-empaquetado}" "$*"; }
die() { printf '[%s] ERROR: %s\n' "${NOMBRE_SCRIPT:-empaquetado}" "$*" >&2; exit 1; }

# paso "<nombre>" <orden...> : ejecuta, mide y falla con mensaje claro (RF-E37).
paso() {
    local nombre="$1"; shift
    local t0=$SECONDS
    msg "=== $nombre"
    if ! "$@"; then
        die "falló el paso: $nombre"
    fi
    local dt=$((SECONDS - t0))
    TIEMPOS+=("$nombre: ${dt}s")
    msg "--- $nombre: correcto (${dt}s)"
}

resumen_tiempos() {
    msg "Tiempos por paso:"
    local t
    for t in "${TIEMPOS[@]}"; do msg "  $t"; done
}

# iniciar_registro <nombre> : copia la salida a build/registros/ sustituyendo $HOME por ~ (RF-E35).
iniciar_registro() {
    mkdir -p "$RAIZ/build/registros"
    REGISTRO="$RAIZ/build/registros/$1-$(date +%Y%m%d-%H%M%S).txt"
    exec > >(sed -u "s|$HOME|~|g" | tee -a "$REGISTRO") 2>&1
}

# Guarda de RF-E33: las pruebas de laboratorio nunca se lanzan desde estos scripts.
guardia_laboratorio() {
    if [ -n "${PROXLAUNCH_LAB:-}" ]; then
        die "la variable de laboratorio está definida; estos scripts no corren pruebas de laboratorio (RF-E33)"
    fi
}

# preparar_uv : deja `uv` en el PATH (el de la MV o el descargado con SHA-256 fijado).
preparar_uv() {
    # shellcheck source=../linux/herramientas.sh
    . "$RAIZ/empaquetado/linux/herramientas.sh"
    if ! command -v uv >/dev/null 2>&1; then
        if [ -x "$HOME/herramientas/uv" ]; then
            PATH="$HOME/herramientas:$PATH"
        else
            local uv
            uv="$(obtener_uv "$HOME/.cache/proxlaunch-herramientas")" || die "no se pudo obtener uv"
            PATH="$(dirname "$uv"):$PATH"
        fi
    fi
    export PATH
    export UV_NO_PROGRESS=1
    msg "uv $(uv --version | awk '{print $2}')"
}

# python_build : imprime la ruta del CPython fijado (lo instala con uv si falta).
python_build() {
    uv python install "$PYTHON_BUILD_VERSION" >/dev/null
    uv python find "$PYTHON_BUILD_VERSION"
}

# crear_entorno <carpeta> <lockfile>... : venv con CPython fijado e instalación con hashes obligatorios.
crear_entorno() {
    local carpeta="$1"; shift
    local args=() l
    for l in "$@"; do args+=(-r "$l"); done
    uv python install "$PYTHON_BUILD_VERSION" >/dev/null
    uv venv --quiet --clear --python "$PYTHON_BUILD_VERSION" "$carpeta"
    uv pip install --quiet --python "$carpeta/bin/python" --require-hashes --no-deps "${args[@]}"
}
