#!/usr/bin/env bash
# Orquesta la verificación completa en el anfitrión (AR-9, sección 5 de la arquitectura, INV-E6):
#   22.04 (MV): calidad -> build del .deb -> [instantánea limpia] -> 22.04: instalar/humo/purge
#   24.04 (MV): instalar/humo/purge
#   anfitrión: sello y SHA256SUMS (solo si el artefacto no es provisional)
# Las MVs se detienen siempre al terminar (nunca se destruyen: se reutilizan).
#
# Uso: empaquetado/verificar-todo.sh linux [--iconos-provisionales]
#   (el objetivo «windows» lo implementa la fase de Windows con los .ps1)
set -euo pipefail

NOMBRE_SCRIPT="verificar-todo"
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun/lib.sh"
cd "$RAIZ"

OBJETIVO="${1:-}"
[ "$OBJETIVO" = "linux" ] || die "uso: verificar-todo.sh linux [--iconos-provisionales]"
shift
PROVISIONAL=0
ARGS_CONSTRUIR=()
for arg in "$@"; do
    case "$arg" in
        --iconos-provisionales) PROVISIONAL=1; ARGS_CONSTRUIR+=("$arg") ;;
        *) die "argumento desconocido: $arg" ;;
    esac
done

iniciar_registro verificar-todo-linux
guardia_laboratorio
[ "$(id -u)" -ne 0 ] || die "no ejecute esto como root (no se usa sudo en el anfitrión)"
MV="$RAIZ/empaquetado/entornos/mv.sh"
ENVIAR="$RAIZ/empaquetado/entornos/enviar-arbol.sh"
# shellcheck source=linux/herramientas.sh
. "$RAIZ/empaquetado/linux/herramientas.sh"

detener_mvs() {
    "$MV" detener ubuntu2204 || true
    "$MV" detener ubuntu2404 || true
}
trap detener_mvs EXIT

VERSION="$(python3 -I empaquetado/comun/version.py --comprobar)"
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
msg "versión $VERSION; epoch $SOURCE_DATE_EPOCH; provisional=$PROVISIONAL"
if [ "$PROVISIONAL" -eq 1 ]; then SUBDIR="dist/provisional"; else SUBDIR="dist"; fi
NOMBRE_DEB="proxlaunch_${VERSION}_amd64.deb"

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

paso "Ubuntu 22.04: calidad y construcción del .deb" construir_en_2204
paso "Ubuntu 22.04 (instantánea limpia): verificación del .deb instalado" verificar_en_2204_limpia
paso "Ubuntu 24.04: verificación del .deb instalado" verificar_en ubuntu2404
paso "Sello y SHA256SUMS" sellar_y_publicar

resumen_tiempos
msg "VERIFICACIÓN LINUX CORRECTA ($NOMBRE_DEB en Ubuntu 22.04 y 24.04)"
