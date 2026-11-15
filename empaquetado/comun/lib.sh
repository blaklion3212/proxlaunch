#!/usr/bin/env bash
# Funciones comunes de los scripts de empaquetado para Linux. Se carga con `source`; no ejecuta nada.
# Define: msg, die, paso, iniciar_registro, resumen_tiempos, guardia_laboratorio,
# comprobar_exclusion_laboratorio, preparar_uv, python_build, crear_entorno.

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TIEMPOS=()

msg() { printf '[%s] %s\n' "${NOMBRE_SCRIPT:-empaquetado}" "$*"; }
die() { printf '[%s] ERROR: %s\n' "${NOMBRE_SCRIPT:-empaquetado}" "$*" >&2; exit 1; }

# paso "<nombre>" <orden...> : ejecuta, mide y falla con mensaje claro (RF-E37).
# La orden corre en una subshell con `set -e` ACTIVO: dentro de un `if`, `!`, `&&` o `||` Bash ignora
# `set -e` en todo el cuerpo de las funciones, y un fallo intermedio pasaba inadvertido (QA-M5-01/02).
# Consecuencia: lo que la orden asigne a variables globales NO llega al llamador; si hace falta un
# valor, la función lo escribe en un archivo o se calcula fuera del paso. Las trampas (trap EXIT) del
# llamador tampoco se ejecutan en la subshell.
paso() {
    local nombre="$1"; shift
    local t0=$SECONDS rc=0
    msg "=== $nombre"
    set +e
    ( set -e; "$@" )
    rc=$?
    set -e
    if [ "$rc" -ne 0 ]; then
        die "falló el paso: $nombre (código $rc)"
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

# Guarda de exclusión con el laboratorio Proxmox (SEG-M5-02): las MVs de empaquetado no conviven con él.
# shellcheck source=exclusion-laboratorio.sh
. "$(dirname "${BASH_SOURCE[0]}")/exclusion-laboratorio.sh"

# preparar_uv : deja en el PATH un `uv` con versión y SHA-256 fijados (SEG-M5-04, SEG-M5-05).
# Nunca se usa el `uv` que haya en el PATH: solo el de ~/herramientas (enviado por el anfitrión) si su
# SHA-256 es el fijado, o el descargado y verificado por obtener_uv.
preparar_uv() {
    # shellcheck source=../linux/herramientas.sh
    . "$RAIZ/empaquetado/linux/herramientas.sh"
    local uv=""
    if [ -x "$HOME/herramientas/uv" ] && verificar_binario_uv "$HOME/herramientas/uv"; then
        uv="$HOME/herramientas/uv"
    else
        uv="$(obtener_uv "$HOME/.cache/proxlaunch-herramientas")" || die "no se pudo obtener uv"
    fi
    PATH="$(dirname "$uv"):$PATH"
    export PATH
    export UV_NO_PROGRESS=1
    # Solo CPython gestionado por uv (el fijado) y sin configuración de uv ajena al repositorio.
    export UV_PYTHON_PREFERENCE=only-managed
    export UV_NO_CONFIG=1
    msg "uv $("$uv" --version | awk '{print $2}')"
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
    # --no-build: solo ruedas (nada compila ni ejecuta código de construcción de terceros, SEG-M5-04).
    uv pip install --quiet --python "$carpeta/bin/python" --require-hashes --no-deps --no-build "${args[@]}"
}
