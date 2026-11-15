#!/usr/bin/env bash
# Orquesta la verificación completa en el anfitrión (AR-9, sección 5 de la arquitectura, INV-E6):
#   22.04 (MV): calidad -> build del .deb -> [instantánea limpia] -> 22.04: instalar/humo/purge
#   24.04 (MV): instalar/humo/purge
#   anfitrión: sello y SHA256SUMS (solo si el artefacto no es provisional)
# Las MVs se detienen siempre al terminar (nunca se destruyen: se reutilizan).
#
# Uso: empaquetado/verificar-todo.sh {linux|windows} [--iconos-provisionales]
#
# windows: arranca la MV de Windows 11 (ya instalada y preparada con preparar.ps1), descarga con
#   SHA-256 verificado las herramientas fijadas, envía el árbol y las herramientas, y ejecuta en la MV
#   preparar-build.ps1, construir-windows.ps1 (calidad incluida) y verificar-windows.ps1; trae dist\ y
#   los registros, escribe el sello y SHA256SUMS (sumas.py) y detiene la MV.
set -euo pipefail

NOMBRE_SCRIPT="verificar-todo"
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun/lib.sh"
cd "$RAIZ"

OBJETIVO="${1:-}"
case "$OBJETIVO" in
    linux | windows) ;;
    *) die "uso: verificar-todo.sh {linux|windows} [--iconos-provisionales]" ;;
esac
shift
PROVISIONAL=0
ARGS_CONSTRUIR=()
for arg in "$@"; do
    case "$arg" in
        --iconos-provisionales) PROVISIONAL=1; ARGS_CONSTRUIR+=("$arg") ;;
        *) die "argumento desconocido: $arg" ;;
    esac
done

iniciar_registro "verificar-todo-$OBJETIVO"
guardia_laboratorio
[ "$(id -u)" -ne 0 ] || die "no ejecute esto como root (no se usa sudo en el anfitrión)"
MV="$RAIZ/empaquetado/entornos/mv.sh"
ENVIAR="$RAIZ/empaquetado/entornos/enviar-arbol.sh"
# shellcheck source=linux/herramientas.sh
. "$RAIZ/empaquetado/linux/herramientas.sh"

detener_mvs() {
    if [ "$OBJETIVO" = "windows" ]; then
        "$MV" detener windows11 || true
    else
        "$MV" detener ubuntu2204 || true
        "$MV" detener ubuntu2404 || true
    fi
}
trap detener_mvs EXIT

VERSION="$(python3 -I empaquetado/comun/version.py --comprobar)"
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
msg "versión $VERSION; epoch $SOURCE_DATE_EPOCH; provisional=$PROVISIONAL"
if [ "$PROVISIONAL" -eq 1 ]; then SUBDIR="dist/provisional"; else SUBDIR="dist"; fi
NOMBRE_DEB="proxlaunch_${VERSION}_amd64.deb"
NOMBRE_SETUP="proxlaunch-${VERSION}-windows-x64-setup.exe"

enviar_uv() {
    local uv
    uv="$(obtener_uv "$HOME/aprovprox-empaquetado/descargas")"
    "$MV" ssh "$1" 'mkdir -p "$HOME/herramientas"'
    "$MV" copiar "$1" "$uv" herramientas/uv
}

construir_en_2204() {
    "$MV" arrancar ubuntu2204
    "$ENVIAR" ubuntu2204
    enviar_uv ubuntu2204
    "$MV" ssh ubuntu2204 'cd proxlaunch && bash empaquetado/linux/preparar-build.sh'
    "$MV" ssh ubuntu2204 "cd proxlaunch && SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH bash empaquetado/construir-linux.sh ${ARGS_CONSTRUIR[*]:-}"
    mkdir -p "$RAIZ/$SUBDIR" "$RAIZ/build/registros/mv-ubuntu2204"
    "$MV" traer ubuntu2204 "proxlaunch/$SUBDIR/$NOMBRE_DEB" "$RAIZ/$SUBDIR/$NOMBRE_DEB"
    "$MV" traer ubuntu2204 proxlaunch/build/registros/. "$RAIZ/build/registros/mv-ubuntu2204/"
    sha256sum "$RAIZ/$SUBDIR/$NOMBRE_DEB" | awk '{print "SHA-256 del .deb construido: " $1}'
}

verificar_en() {
    local mv="$1"
    "$MV" arrancar "$mv"
    "$ENVIAR" "$mv"
    "$MV" ssh "$mv" "mkdir -p proxlaunch/$SUBDIR"
    "$MV" copiar "$mv" "$RAIZ/$SUBDIR/$NOMBRE_DEB" "proxlaunch/$SUBDIR/$NOMBRE_DEB"
    "$MV" ssh "$mv" "cd proxlaunch && bash empaquetado/verificar-deb.sh $SUBDIR/$NOMBRE_DEB --version-esperada $VERSION"
    mkdir -p "$RAIZ/build/registros/mv-$mv"
    "$MV" traer "$mv" proxlaunch/build/registros/. "$RAIZ/build/registros/mv-$mv/"
}

verificar_en_2204_limpia() {
    # La MV de construcción tiene bibliotecas extra: se vuelve a la instantánea limpia (como la 24.04).
    "$MV" detener ubuntu2204
    "$MV" restaurar ubuntu2204
    verificar_en ubuntu2204
}

sellar_y_publicar() {
    if [ "$PROVISIONAL" -eq 1 ]; then
        msg "artefacto provisional: NO se sella ni entra en SHA256SUMS"
        return 0
    fi
    python3 -I empaquetado/comun/sumas.py sellar "dist/$NOMBRE_DEB"
    python3 -I empaquetado/comun/sumas.py publicar
    python3 -I empaquetado/comun/sumas.py comprobar
}

# --- Windows (MV de pruebas; los .ps1 corren dentro de la MV por SSH, intérprete PowerShell) ---------

# ps_mv <orden de PowerShell> : ejecuta en la MV desde la carpeta del árbol (~/proxlaunch).
ps_mv() {
    "$MV" ssh windows11 "Set-Location proxlaunch; $1"
}

# Ejecuta un .ps1 de empaquetado\ en la MV y propaga su código de salida.
script_mv() {
    local script="$1"; shift
    ps_mv "\$env:SOURCE_DATE_EPOCH='$SOURCE_DATE_EPOCH'; powershell -NoProfile -ExecutionPolicy Bypass -File $script $*; exit \$LASTEXITCODE"
}

windows_arrancar_mv() {
    "$MV" arrancar windows11
    [ "$(cat "$HOME/aprovprox-empaquetado/windows11/fase" 2>/dev/null)" = "lista" ] \
        || die "la MV windows11 aún no está preparada: siga 'empaquetado/entornos/mv.sh instrucciones windows11'"
}

windows_herramientas() {
    local carpeta="$HOME/aprovprox-empaquetado/descargas/windows"
    python3 -I "$RAIZ/empaquetado/entornos/windows/descargar-herramientas.py" --destino "$carpeta"
    "$ENVIAR" windows11
    "$MV" ssh windows11 'New-Item -ItemType Directory -Force -Path herramientas | Out-Null'
    local f
    for f in "$carpeta"/*.exe; do
        "$MV" copiar windows11 "$f" "herramientas/$(basename "$f")"
    done
}

windows_construir() {
    local args=""
    [ "$PROVISIONAL" -eq 0 ] || args="-IconosProvisionales"
    script_mv "empaquetado\\construir-windows.ps1" "$args"
}

windows_traer() {
    mkdir -p "$RAIZ/$SUBDIR" "$RAIZ/build/registros/mv-windows11" "$RAIZ/build/verificacion"
    "$MV" traer windows11 "proxlaunch/$SUBDIR/$NOMBRE_SETUP" "$RAIZ/$SUBDIR/$NOMBRE_SETUP"
    "$MV" traer windows11 proxlaunch/build/registros "$RAIZ/build/registros/mv-windows11/"
    if [ "$PROVISIONAL" -eq 0 ]; then
        "$MV" traer windows11 "proxlaunch/build/verificacion/$NOMBRE_SETUP.ok" \
            "$RAIZ/build/verificacion/$NOMBRE_SETUP.ok"
    fi
    sha256sum "$RAIZ/$SUBDIR/$NOMBRE_SETUP" | awk '{print "SHA-256 del instalador construido: " $1}'
}

sellar_y_publicar_windows() {
    if [ "$PROVISIONAL" -eq 1 ]; then
        msg "artefacto provisional: NO se sella ni entra en SHA256SUMS"
        return 0
    fi
    local sello="$RAIZ/build/verificacion/$NOMBRE_SETUP.ok" suma_local suma_sello
    [ -f "$sello" ] || die "la MV no dejó el sello de verificación ($sello)"
    suma_local="$(sha256sum "$RAIZ/dist/$NOMBRE_SETUP" | awk '{print $1}')"
    suma_sello="$(head -n1 "$sello" | awk '{print $1}')"
    [ "$suma_local" = "$suma_sello" ] \
        || die "el instalador traído no es el que verificó la MV (sumas distintas): no se publica"
    python3 -I empaquetado/comun/sumas.py sellar "dist/$NOMBRE_SETUP"
    python3 -I empaquetado/comun/sumas.py publicar
    python3 -I empaquetado/comun/sumas.py comprobar
}

if [ "$OBJETIVO" = "windows" ]; then
    paso "Windows 11: arranque de la MV" windows_arrancar_mv
    paso "Herramientas fijadas (SHA-256), árbol y copia a la MV" windows_herramientas
    paso "Windows 11: herramientas de construcción" script_mv "empaquetado\\windows\\preparar-build.ps1"
    paso "Windows 11: calidad y construcción del instalador" windows_construir
    paso "Windows 11: verificación del instalador instalado" \
        script_mv "empaquetado\\verificar-windows.ps1" "-VersionEsperada $VERSION"
    paso "Recogida de artefactos y registros" windows_traer
    paso "Sello y SHA256SUMS" sellar_y_publicar_windows
    resumen_tiempos
    msg "VERIFICACIÓN WINDOWS CORRECTA ($NOMBRE_SETUP en Windows 11)"
    exit 0
fi

paso "Ubuntu 22.04: calidad y construcción del .deb" construir_en_2204
paso "Ubuntu 22.04 (instantánea limpia): verificación del .deb instalado" verificar_en_2204_limpia
paso "Ubuntu 24.04: verificación del .deb instalado" verificar_en ubuntu2404
paso "Sello y SHA256SUMS" sellar_y_publicar

resumen_tiempos
msg "VERIFICACIÓN LINUX CORRECTA ($NOMBRE_DEB en Ubuntu 22.04 y 24.04)"
