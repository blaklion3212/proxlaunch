#!/usr/bin/env bash
# Orquesta la verificación completa en el anfitrión (AR-9, sección 5 de la arquitectura, INV-E6):
#   22.04 (MV): calidad -> build del .deb -> [instantánea limpia] -> 22.04: instalar/humo/purge
#   24.04 (MV, instantánea limpia): instalar/humo/purge
#   anfitrión: sello y SHA256SUMS (solo si el artefacto no es provisional)
# Las MVs se detienen siempre al terminar (nunca se destruyen: se reutilizan).
#
# Uso: empaquetado/verificar-todo.sh {linux|windows} [--iconos-provisionales]
#      empaquetado/verificar-todo.sh {actualizacion-linux|actualizacion-windows} [--version-prueba X.Y.Z]
#
# windows: arranca la MV de Windows 11 (ya instalada y preparada con preparar.ps1), descarga con
#   SHA-256 verificado las herramientas fijadas, envía el árbol y las herramientas, y ejecuta en la MV
#   preparar-build.ps1, construir-windows.ps1 (calidad incluida) y verificar-windows.ps1; trae dist\ y
#   los registros, escribe el sello y SHA256SUMS (sumas.py) y detiene la MV.
#
# actualizacion-linux / actualizacion-windows (QA-M5-07): requieren que el artefacto 0.5.0 (la versión
#   vigente) ya esté verificado y sellado en dist/. Construyen una build de PRUEBA con versión mayor
#   (por defecto, el siguiente parche: 0.5.1) cambiando __version__ SOLO en la copia del árbol enviada a
#   la MV (el repositorio no cambia), instalan la versión vigente, siembran datos de usuario, instalan
#   encima la de prueba y comprueban versión nueva (dpkg/--version; DisplayVersion en Windows), una sola
#   entrada instalada, datos idénticos (SHA-256) y humo correcto. El artefacto de prueba nunca va a
#   dist/ ni a SHA256SUMS: vive en build/actualizacion/ (Linux) o en la MV (Windows) y se borra al
#   terminar. En ambos casos se omite la calidad en la build de prueba (las pruebas esperan 0.5.0).
#
# Además de lo anterior, al terminar comprueba que ningún registro de build/registros/ contiene la
# contraseña de la cuenta de prueba de la MV de Windows (SEG-M5-01; se excluye crear-windows11.txt) y,
# antes de arrancar MVs, que el laboratorio Proxmox no esté activo (SEG-M5-02).
set -euo pipefail

NOMBRE_SCRIPT="verificar-todo"
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun/lib.sh"
cd "$RAIZ"

OBJETIVO="${1:-}"
case "$OBJETIVO" in
    linux | windows | actualizacion-linux | actualizacion-windows) ;;
    *) die "uso: verificar-todo.sh {linux|windows} [--iconos-provisionales] | {actualizacion-linux|actualizacion-windows} [--version-prueba X.Y.Z]" ;;
esac
shift
PROVISIONAL=0
ARGS_CONSTRUIR=()
VERSION_PRUEBA=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --iconos-provisionales)
            case "$OBJETIVO" in actualizacion-*) die "--iconos-provisionales no aplica a $OBJETIVO" ;; esac
            PROVISIONAL=1; ARGS_CONSTRUIR+=("$1"); shift ;;
        --version-prueba)
            case "$OBJETIVO" in actualizacion-*) ;; *) die "--version-prueba solo aplica a actualizacion-*" ;; esac
            VERSION_PRUEBA="${2:?falta la versión de prueba}"; shift 2 ;;
        *) die "argumento desconocido: $1" ;;
    esac
done

iniciar_registro "verificar-todo-$OBJETIVO"
guardia_laboratorio
comprobar_exclusion_laboratorio
[ "$(id -u)" -ne 0 ] || die "no ejecute esto como root (no se usa sudo en el anfitrión)"
MV="$RAIZ/empaquetado/entornos/mv.sh"
ENVIAR="$RAIZ/empaquetado/entornos/enviar-arbol.sh"
# shellcheck source=linux/herramientas.sh
. "$RAIZ/empaquetado/linux/herramientas.sh"

# Carpeta de la MV donde vive el árbol (la principal o, en la actualización, la copia con versión de prueba).
CARPETA_MV="proxlaunch"
ARGS_ARBOL=()
DIR_ACT="$RAIZ/build/actualizacion"

detener_mvs() {
    case "$OBJETIVO" in
        windows | actualizacion-windows) "$MV" detener windows11 || true ;;
        *)
            "$MV" detener ubuntu2204 || true
            "$MV" detener ubuntu2404 || true ;;
    esac
}

# El artefacto de prueba de la actualización se borra siempre al terminar (también si falla).
limpiar_actualizacion() {
    case "$OBJETIVO" in
        actualizacion-linux) rm -rf -- "${DIR_ACT:?}" ;;
        actualizacion-windows)
            "$MV" ssh windows11 'Remove-Item -Recurse -Force -ErrorAction SilentlyContinue proxlaunch-act' || true
            rm -rf -- "${DIR_ACT:?}" ;;
    esac
}

finalizar() {
    limpiar_actualizacion
    detener_mvs
}
trap finalizar EXIT

VERSION="$(python3 -I empaquetado/comun/version.py --comprobar)"
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
msg "versión $VERSION; epoch $SOURCE_DATE_EPOCH; provisional=$PROVISIONAL"
if [ "$PROVISIONAL" -eq 1 ]; then SUBDIR="dist/provisional"; else SUBDIR="dist"; fi
NOMBRE_DEB="proxlaunch_${VERSION}_amd64.deb"
NOMBRE_SETUP="proxlaunch-${VERSION}-windows-x64-setup.exe"

# Build de prueba de la actualización: versión explícita o el siguiente parche de la vigente.
case "$OBJETIVO" in
    actualizacion-*)
        if [ -z "$VERSION_PRUEBA" ]; then
            IFS=. read -r _ma _mi _pa <<< "$VERSION"
            VERSION_PRUEBA="${_ma}.${_mi}.$((_pa + 1))"
        fi
        [[ "$VERSION_PRUEBA" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] \
            || die "la versión de prueba '$VERSION_PRUEBA' no es X.Y.Z"
        [ "$VERSION_PRUEBA" != "$VERSION" ] \
            && [ "$(printf '%s\n%s\n' "$VERSION" "$VERSION_PRUEBA" | sort -V | tail -n1)" = "$VERSION_PRUEBA" ] \
            || die "la versión de prueba ($VERSION_PRUEBA) debe ser mayor que la vigente ($VERSION)"
        NOMBRE_DEB_PRUEBA="proxlaunch_${VERSION_PRUEBA}_amd64.deb"
        NOMBRE_SETUP_PRUEBA="proxlaunch-${VERSION_PRUEBA}-windows-x64-setup.exe"
        msg "actualización $VERSION -> $VERSION_PRUEBA (build de prueba; no se publica)"
        ARGS_ARBOL=(--version-prueba "$VERSION_PRUEBA")
        CARPETA_MV="proxlaunch-act" ;;
esac

# Antes de construir se borran el artefacto de esta versión y sus sellos (solo de la plataforma que se va a
# construir): un fallo posterior (p. ej. al traerlo de la MV) nunca puede dejar un artefacto viejo que
# parezca el nuevo (QA-M5-01).
limpiar_artefactos_previos() {
    local carpeta="$RAIZ/$SUBDIR" nombre
    if [ "$OBJETIVO" = "windows" ]; then nombre="$NOMBRE_SETUP"; else nombre="$NOMBRE_DEB"; fi
    rm -f -- "${carpeta:?}/${nombre:?}" "${carpeta:?}/.verificado-${nombre:?}" "${carpeta:?}/.${nombre:?}.parcial"
    if [ "$OBJETIVO" = "windows" ]; then rm -f -- "${RAIZ:?}/build/verificacion/${NOMBRE_SETUP:?}.ok"; fi
    if [ "$PROVISIONAL" -eq 0 ]; then
        # SHA256SUMS no debe seguir listando lo que se acaba de borrar (los otros sellos se conservan).
        python3 -I empaquetado/comun/sumas.py publicar || true
    fi
}

enviar_uv() {
    local uv
    uv="$(obtener_uv "$HOME/aprovprox-empaquetado/descargas")"
    "$MV" ssh "$1" 'mkdir -p "$HOME/herramientas"'
    "$MV" copiar "$1" "$uv" herramientas/uv
}

# traer_verificado <mv> <ruta remota> <destino local> : trae el archivo a un nombre temporal, comprueba que
# su SHA-256 es el que calcula la MV y solo entonces lo pone en su sitio (nunca queda un archivo a medias
# ni uno viejo con el nombre definitivo).
traer_verificado() {
    local mv="$1" remoto="$2" destino="$3" parcial suma_remota suma_local
    parcial="$(dirname "$destino")/.$(basename "$destino").parcial"
    rm -f -- "${parcial:?}"
    "$MV" traer "$mv" "$remoto" "$parcial"
    suma_remota="$("$MV" ssh "$mv" "sha256sum '$remoto'" | awk '{print $1}')"
    suma_local="$(sha256sum "$parcial" | awk '{print $1}')"
    if [ -z "$suma_remota" ] || [ "$suma_remota" != "$suma_local" ]; then
        rm -f -- "${parcial:?}"
        die "la suma de $(basename "$destino") traído no coincide con la de la MV"
    fi
    mv -f -- "$parcial" "$destino"
}

# copiar_verificado <mv> <origen local> <destino remoto relativo> : copia a la MV y comprueba la suma allí.
copiar_verificado() {
    local mv="$1" origen="$2" destino="$3" suma_remota suma_local
    "$MV" copiar "$mv" "$origen" "$destino"
    suma_remota="$("$MV" ssh "$mv" "sha256sum '$destino'" | awk '{print $1}')"
    suma_local="$(sha256sum "$origen" | awk '{print $1}')"
    [ -n "$suma_remota" ] && [ "$suma_remota" = "$suma_local" ] \
        || die "la copia de $(basename "$origen") en la MV no coincide con el original"
}

construir_en_2204() {
    "$MV" arrancar ubuntu2204
    "$ENVIAR" ubuntu2204
    enviar_uv ubuntu2204
    "$MV" ssh ubuntu2204 'cd proxlaunch && bash empaquetado/linux/preparar-build.sh'
    "$MV" ssh ubuntu2204 "cd proxlaunch && SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH bash empaquetado/construir-linux.sh ${ARGS_CONSTRUIR[*]:-}"
    mkdir -p "$RAIZ/$SUBDIR" "$RAIZ/build/registros/mv-ubuntu2204"
    traer_verificado ubuntu2204 "proxlaunch/$SUBDIR/$NOMBRE_DEB" "$RAIZ/$SUBDIR/$NOMBRE_DEB"
    "$MV" traer ubuntu2204 proxlaunch/build/registros/. "$RAIZ/build/registros/mv-ubuntu2204/"
    sha256sum "$RAIZ/$SUBDIR/$NOMBRE_DEB" | awk '{print "SHA-256 del .deb construido: " $1}'
}

verificar_en() {
    local mv="$1"
    "$MV" arrancar "$mv"
    "$ENVIAR" "$mv"
    "$MV" ssh "$mv" "mkdir -p proxlaunch/$SUBDIR"
    copiar_verificado "$mv" "$RAIZ/$SUBDIR/$NOMBRE_DEB" "proxlaunch/$SUBDIR/$NOMBRE_DEB"
    "$MV" ssh "$mv" "cd proxlaunch && bash empaquetado/verificar-deb.sh $SUBDIR/$NOMBRE_DEB --version-esperada $VERSION"
    mkdir -p "$RAIZ/build/registros/mv-$mv"
    "$MV" traer "$mv" proxlaunch/build/registros/. "$RAIZ/build/registros/mv-$mv/"
}

# La MV de construcción (22.04) tiene bibliotecas extra y la 24.04 pudo usarse antes: las dos vuelven a la
# instantánea limpia antes de verificar el .deb (QA-M5-09).
verificar_en_limpia() {
    local mv="$1"
    "$MV" detener "$mv"
    "$MV" restaurar "$mv"
    verificar_en "$mv"
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

# SEG-M5-01: ningún registro de build/registros/ debe contener la contraseña de la cuenta «prueba» de la
# MV de Windows. Se lee el archivo DENTRO del proceso de Python y nunca se imprime; solo se listan los
# nombres de los registros que la contengan. Se excluye crear-windows11.txt (el usuario decidió
# conservarlo; no se modifica ni se borra).
comprobar_sin_contrasena_en_registros() {
    local archivo="$HOME/aprovprox-empaquetado/windows11/contrasena-prueba"
    if [ ! -f "$archivo" ]; then
        msg "no hay contraseña de la MV de Windows en el anfitrión: nada que buscar"
        return 0
    fi
    python3 -I - "$archivo" "$RAIZ/build/registros" "crear-windows11.txt" <<'PY'
import os
import sys

ruta_secreto, carpeta, excluido = sys.argv[1:4]
with open(ruta_secreto, "rb") as f:
    secreto = f.read().strip()
if len(secreto) < 8:
    sys.exit("SEG-M5-01: el archivo de la contraseña está vacío o es demasiado corto: no se puede comprobar")
coinciden = []
for base, _, nombres in os.walk(carpeta):
    for nombre in nombres:
        ruta = os.path.join(base, nombre)
        rel = os.path.relpath(ruta, carpeta)
        if rel == excluido:
            continue
        try:
            with open(ruta, "rb") as g:
                if secreto in g.read():
                    coinciden.append(rel)
        except OSError:
            continue
if coinciden:
    print("SEG-M5-01: la contraseña de la MV de Windows aparece en: " + ", ".join(sorted(coinciden)), file=sys.stderr)
    sys.exit(1)
print("SEG-M5-01: ningún registro contiene la contraseña de la MV de Windows")
PY
}

# --- Windows (MV de pruebas; los .ps1 corren dentro de la MV por SSH, intérprete PowerShell) ---------

# ps_mv <orden de PowerShell> : ejecuta en la MV desde la carpeta del árbol (~/proxlaunch, o la copia
# con versión de prueba ~/proxlaunch-act en la actualización).
ps_mv() {
    "$MV" ssh windows11 "Set-Location $CARPETA_MV; $1"
}

# Valida con el analizador de PowerShell de la MV la sintaxis de todos los .ps1 del árbol enviado.
# El anfitrión no tiene PowerShell, y un .ps1 que no se analiza puede terminar con código 0 sin
# haber hecho nada: este paso va antes de ejecutar ningún script.
windows_sintaxis_ps1() {
    local orden
    orden="\$m=@(); Get-ChildItem -Recurse -Filter *.ps1 -LiteralPath empaquetado | ForEach-Object { \$t=\$null; \$e=\$null; [void][System.Management.Automation.Language.Parser]::ParseFile(\$_.FullName,[ref]\$t,[ref]\$e); foreach (\$x in @(\$e)) { \$m += ('{0}:{1}: {2}' -f \$_.Name,\$x.Extent.StartLineNumber,\$x.Message) } }; if (@(\$m).Count -gt 0) { \$m; exit 1 }; 'sintaxis de los .ps1 correcta'; exit 0"
    ps_mv "$orden"
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
    "$ENVIAR" windows11 "$CARPETA_MV" ${ARGS_ARBOL[@]+"${ARGS_ARBOL[@]}"}
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

# En Windows el intérprete remoto es PowerShell: la suma se pide con Get-FileHash.
traer_verificado_windows() {
    local remoto="$1" destino="$2" parcial suma_remota suma_local
    parcial="$(dirname "$destino")/.$(basename "$destino").parcial"
    rm -f -- "${parcial:?}"
    "$MV" traer windows11 "$remoto" "$parcial"
    suma_remota="$("$MV" ssh windows11 "(Get-FileHash -Algorithm SHA256 -LiteralPath '${remoto//\//\\}').Hash" | tr -d '\r' | tr 'A-F' 'a-f')"
    suma_local="$(sha256sum "$parcial" | awk '{print $1}')"
    if [ -z "$suma_remota" ] || [ "$suma_remota" != "$suma_local" ]; then
        rm -f -- "${parcial:?}"
        die "la suma de $(basename "$destino") traído no coincide con la de la MV"
    fi
    mv -f -- "$parcial" "$destino"
}

windows_traer() {
    mkdir -p "$RAIZ/$SUBDIR" "$RAIZ/build/registros/mv-windows11" "$RAIZ/build/verificacion"
    traer_verificado_windows "proxlaunch/$SUBDIR/$NOMBRE_SETUP" "$RAIZ/$SUBDIR/$NOMBRE_SETUP"
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

# --- Actualización 0.5.0 -> 0.5.1 (QA-M5-07) ----------------------------------------------------------

# El artefacto de la versión vigente debe estar verificado y sellado en dist/ (es la «versión anterior»).
actualizacion_base() {
    local nombre="$1"
    [ -f "$RAIZ/dist/$nombre" ] || die "falta dist/$nombre: ejecute antes verificar-todo.sh ${OBJETIVO#actualizacion-}"
    python3 -I empaquetado/comun/sumas.py comprobar
    grep -q "  ${nombre}\$" "$RAIZ/dist/SHA256SUMS" \
        || die "$nombre no está en SHA256SUMS (no está verificado y sellado)"
}

actualizacion_preparar_linux() {
    actualizacion_base "$NOMBRE_DEB"
    rm -rf -- "${DIR_ACT:?}"
    mkdir -p "$DIR_ACT"
}

# Build de prueba en la MV de construcción: árbol con __version__ cambiado SOLO en la copia enviada.
actualizacion_construir_2204() {
    "$MV" arrancar ubuntu2204
    "$ENVIAR" ubuntu2204 proxlaunch-act --version-prueba "$VERSION_PRUEBA"
    enviar_uv ubuntu2204
    "$MV" ssh ubuntu2204 'cd proxlaunch-act && bash empaquetado/linux/preparar-build.sh'
    "$MV" ssh ubuntu2204 "cd proxlaunch-act && SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH bash empaquetado/construir-linux.sh --sin-calidad"
    traer_verificado ubuntu2204 "proxlaunch-act/dist/provisional/$NOMBRE_DEB_PRUEBA" "$DIR_ACT/$NOMBRE_DEB_PRUEBA"
    mkdir -p "$RAIZ/build/registros/mv-ubuntu2204-actualizacion"
    "$MV" traer ubuntu2204 proxlaunch-act/build/registros/. "$RAIZ/build/registros/mv-ubuntu2204-actualizacion/"
}

actualizacion_verificar_2204() {
    "$MV" detener ubuntu2204
    "$MV" restaurar ubuntu2204
    "$MV" arrancar ubuntu2204
    "$ENVIAR" ubuntu2204
    "$MV" ssh ubuntu2204 'mkdir -p proxlaunch/dist proxlaunch/build/actualizacion'
    copiar_verificado ubuntu2204 "$RAIZ/dist/$NOMBRE_DEB" "proxlaunch/dist/$NOMBRE_DEB"
    copiar_verificado ubuntu2204 "$DIR_ACT/$NOMBRE_DEB_PRUEBA" "proxlaunch/build/actualizacion/$NOMBRE_DEB_PRUEBA"
    "$MV" ssh ubuntu2204 "cd proxlaunch && bash empaquetado/verificar-deb.sh build/actualizacion/$NOMBRE_DEB_PRUEBA --version-esperada $VERSION_PRUEBA --actualizar-desde dist/$NOMBRE_DEB"
    mkdir -p "$RAIZ/build/registros/mv-ubuntu2204-actualizacion"
    "$MV" traer ubuntu2204 proxlaunch/build/registros/. "$RAIZ/build/registros/mv-ubuntu2204-actualizacion/"
}

actualizacion_preparar_windows() {
    actualizacion_base "$NOMBRE_SETUP"
    rm -rf -- "${DIR_ACT:?}"
}

# Copia el instalador vigente a la MV (comprobando la suma) para usarlo como «versión anterior».
actualizacion_windows_copiar_base() {
    "$MV" ssh windows11 'New-Item -ItemType Directory -Force -Path proxlaunch-act\build\actualizacion | Out-Null'
    "$MV" copiar windows11 "$RAIZ/dist/$NOMBRE_SETUP" "proxlaunch-act/build/actualizacion/$NOMBRE_SETUP"
    local suma_remota suma_local
    suma_remota="$("$MV" ssh windows11 "(Get-FileHash -Algorithm SHA256 -LiteralPath 'proxlaunch-act\\build\\actualizacion\\$NOMBRE_SETUP').Hash" | tr -d '\r' | tr 'A-F' 'a-f')"
    suma_local="$(sha256sum "$RAIZ/dist/$NOMBRE_SETUP" | awk '{print $1}')"
    [ -n "$suma_remota" ] && [ "$suma_remota" = "$suma_local" ] \
        || die "la copia de $NOMBRE_SETUP en la MV no coincide con el original"
}

actualizacion_windows_construir() {
    script_mv "empaquetado\\construir-windows.ps1" "-SinCalidad"
}

actualizacion_windows_verificar() {
    script_mv "empaquetado\\verificar-windows.ps1" \
        "-SoloActualizacion -Instalador dist\\provisional\\$NOMBRE_SETUP_PRUEBA -InstaladorAnterior build\\actualizacion\\$NOMBRE_SETUP -VersionEsperada $VERSION_PRUEBA"
}

actualizacion_windows_registros() {
    mkdir -p "$RAIZ/build/registros/mv-windows11-actualizacion"
    "$MV" traer windows11 proxlaunch-act/build/registros "$RAIZ/build/registros/mv-windows11-actualizacion/"
}

# --- Ejecución -------------------------------------------------------------------------------------

if [ "$OBJETIVO" = "actualizacion-windows" ]; then
    paso "Actualización: instalador vigente verificado y sellado" actualizacion_preparar_windows
    paso "Windows 11: arranque de la MV" windows_arrancar_mv
    paso "Herramientas fijadas (SHA-256) y árbol de prueba $VERSION_PRUEBA a la MV" windows_herramientas
    paso "Windows 11: sintaxis de los .ps1 (analizador de PowerShell)" windows_sintaxis_ps1
    paso "Windows 11: herramientas de construcción" script_mv "empaquetado\\windows\\preparar-build.ps1"
    paso "Windows 11: build de prueba $VERSION_PRUEBA (sin calidad; no se publica)" actualizacion_windows_construir
    paso "Windows 11: instalador vigente $VERSION a la MV (con suma)" actualizacion_windows_copiar_base
    paso "Windows 11: actualización $VERSION -> $VERSION_PRUEBA con datos de usuario" actualizacion_windows_verificar
    paso "Recogida de registros de la actualización" actualizacion_windows_registros
    paso "Sin la contraseña de la MV en los registros (SEG-M5-01)" comprobar_sin_contrasena_en_registros
    resumen_tiempos
    msg "ACTUALIZACIÓN WINDOWS CORRECTA ($VERSION -> $VERSION_PRUEBA en Windows 11); artefacto de prueba descartado"
    exit 0
fi

if [ "$OBJETIVO" = "actualizacion-linux" ]; then
    paso "Actualización: .deb vigente verificado y sellado" actualizacion_preparar_linux
    paso "Ubuntu 22.04: build de prueba $VERSION_PRUEBA (sin calidad; no se publica)" actualizacion_construir_2204
    paso "Ubuntu 22.04 (instantánea limpia): actualización $VERSION -> $VERSION_PRUEBA con datos de usuario" \
        actualizacion_verificar_2204
    paso "Sin la contraseña de la MV en los registros (SEG-M5-01)" comprobar_sin_contrasena_en_registros
    resumen_tiempos
    msg "ACTUALIZACIÓN LINUX CORRECTA ($VERSION -> $VERSION_PRUEBA en Ubuntu 22.04); artefacto de prueba descartado"
    exit 0
fi

limpiar_artefactos_previos

if [ "$OBJETIVO" = "windows" ]; then
    paso "Windows 11: arranque de la MV" windows_arrancar_mv
    paso "Herramientas fijadas (SHA-256), árbol y copia a la MV" windows_herramientas
    paso "Windows 11: sintaxis de los .ps1 (analizador de PowerShell)" windows_sintaxis_ps1
    paso "Windows 11: herramientas de construcción" script_mv "empaquetado\\windows\\preparar-build.ps1"
    paso "Windows 11: calidad y construcción del instalador" windows_construir
    paso "Windows 11: verificación del instalador instalado" \
        script_mv "empaquetado\\verificar-windows.ps1" "-VersionEsperada $VERSION"
    paso "Recogida de artefactos y registros" windows_traer
    paso "Sello y SHA256SUMS" sellar_y_publicar_windows
    paso "Sin la contraseña de la MV en los registros (SEG-M5-01)" comprobar_sin_contrasena_en_registros
    resumen_tiempos
    msg "VERIFICACIÓN WINDOWS CORRECTA ($NOMBRE_SETUP en Windows 11)"
    exit 0
fi

paso "Ubuntu 22.04: calidad y construcción del .deb" construir_en_2204
paso "Ubuntu 22.04 (instantánea limpia): verificación del .deb instalado" verificar_en_limpia ubuntu2204
paso "Ubuntu 24.04 (instantánea limpia): verificación del .deb instalado" verificar_en_limpia ubuntu2404
paso "Sello y SHA256SUMS" sellar_y_publicar
paso "Sin la contraseña de la MV en los registros (SEG-M5-01)" comprobar_sin_contrasena_en_registros

resumen_tiempos
msg "VERIFICACIÓN LINUX CORRECTA ($NOMBRE_DEB en Ubuntu 22.04 y 24.04)"
