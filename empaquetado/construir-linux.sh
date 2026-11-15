#!/usr/bin/env bash
# Construye el paquete .deb de ProxLaunch (RF-E02, RF-E04, RF-E34). Pensado para Ubuntu 22.04
# (la base más antigua admitida: la glibc del congelado debe ser <= 2.35, CA-E05.1).
#
# Orden: versión -> calidad -> entorno desde lockfile -> .qm -> iconos -> avisos -> PyInstaller
#        -> comprobaciones del congelado -> .deb -> presupuesto de tamaño.
# Nada se escribe en dist/ si algún paso falla. Las sumas (SHA256SUMS) NO se escriben aquí: solo
# las escribe sumas.py tras la verificación instalada (verificar-deb.sh, INV-E6).
#
# Uso: empaquetado/construir-linux.sh [--iconos-provisionales] [--sin-calidad]
#   --iconos-provisionales  ya no hace falta con los iconos aprobados; se conserva para usar iconos
#                           sin aprobar (solo verificación interna). El artefacto queda en
#                           dist/provisional/ y NO es publicable.
#   --sin-calidad           omite calidad.sh (atajo de desarrollo; también deja el artefacto como
#                           provisional).
set -euo pipefail

NOMBRE_SCRIPT="construir-linux"
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun/lib.sh"
cd "$RAIZ"

PROVISIONAL=0
SIN_CALIDAD=0
for arg in "$@"; do
    case "$arg" in
        --iconos-provisionales) PROVISIONAL=1 ;;
        --sin-calidad) SIN_CALIDAD=1; PROVISIONAL=1 ;;
        -h | --help) sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "argumento desconocido: $arg" ;;
    esac
done

iniciar_registro construir-linux
export REGISTRO_YA_INICIADO=1
guardia_laboratorio
[ "$(uname -s)" = "Linux" ] || die "este script solo construye en Linux"
[ "$(uname -m)" = "x86_64" ] || die "solo se admite amd64"
command -v dpkg-deb >/dev/null || die "falta dpkg-deb (¿es un sistema Debian/Ubuntu?)"

# Epoch fijo para fechas de archivos (RF-E04b): el del último commit si hay git; si no, el de LICENSE.
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
    SOURCE_DATE_EPOCH="$(git -C "$RAIZ" log -1 --format=%ct 2>/dev/null || stat -c %Y "$RAIZ/LICENSE")"
fi
export SOURCE_DATE_EPOCH

# 1. Versión (CA-E10.1/E10.3): falla antes de construir si no es SemVer o es incoherente.
preparar_uv
PYB="$(python_build)"
VERSION="$("$PYB" -I empaquetado/comun/version.py --comprobar)" || die "versión no válida (vea arriba)"
msg "versión $VERSION"

# Nombre y destino del artefacto. Antes de construir se BORRA el artefacto de la misma versión y sus
# sellos de verificación: si un paso posterior fallara, nunca quedaría un .deb viejo que pudiera
# tomarse por el recién construido (QA-M5-01).
NOMBRE_DEB="proxlaunch_${VERSION}_amd64.deb"
if [ "$PROVISIONAL" -eq 1 ]; then
    DESTINO="$RAIZ/dist/provisional"
else
    DESTINO="$RAIZ/dist"
fi
rm -f -- "${DESTINO:?}/${NOMBRE_DEB:?}" "${DESTINO:?}/.verificado-${NOMBRE_DEB:?}" \
    "${RAIZ:?}/build/deb/${NOMBRE_DEB:?}"

if [ "$SIN_CALIDAD" -eq 0 ]; then
    paso "Calidad completa" bash empaquetado/calidad.sh
else
    msg "AVISO: se omite la calidad; el artefacto será provisional (no publicable)"
fi

VENV="$RAIZ/build/venv-construccion"
PY="$VENV/bin/python"
paso "Entorno de construcción desde el lockfile" \
    crear_entorno "$VENV" empaquetado/requisitos/linux-construccion.txt \
    empaquetado/requisitos/linux-ejecucion.txt
paso "Revisión estática (CA-E30/E33/E35/E21/E24)" "$PY" -I empaquetado/comun/revisar_estatico.py
paso "Traducciones (.qm)" "$PY" -I empaquetado/comun/compilar_qm.py

# Iconos: se COPIAN los aprobados por el usuario (empaquetado/iconos/) tras verificar su SHA256SUMS;
# no se redibujan (otra versión de Qt cambiaría los píxeles).
paso "Iconos aprobados (copia verificada)" "$PY" -I empaquetado/comun/iconos.py copiar --salida build/iconos
if [ "$PROVISIONAL" -eq 1 ]; then
    paso "Iconos (comprobación)" "$PY" -I empaquetado/comun/iconos.py verificar --salida build/iconos --provisional
else
    paso "Iconos (comprobación)" "$PY" -I empaquetado/comun/iconos.py verificar --salida build/iconos
fi
paso "Avisos de terceros" "$PY" -I empaquetado/comun/avisos.py \
    --lock empaquetado/requisitos/linux-ejecucion.txt --salida build/THIRD-PARTY-NOTICES.txt

paso "Congelado con PyInstaller" "$PY" -m PyInstaller --noconfirm --clean \
    --distpath build/pyi/dist --workpath build/pyi/work empaquetado/proxlaunch.spec
CONGELADO="$RAIZ/build/pyi/dist/proxlaunch"
[ -x "$CONGELADO/proxlaunch" ] || die "PyInstaller no produjo el ejecutable"

# Comprobaciones del congelado (antes de empaquetar).
comprobar_congelado() {
    local salida
    salida="$("$CONGELADO/proxlaunch" --version)" || return 1
    [ "$salida" = "ProxLaunch $VERSION" ] || { msg "--version devolvió '$salida'"; return 1; }
    # CA-E19.2: sin pruebas, sin .ts ni módulos de Qt no usados.
    if find "$CONGELADO" \( -name '*.ts' -o -path '*/tests/*' -o -name 'libQt6Qml*' \
        -o -name 'libQt6Quick*' -o -name 'libQt6WebEngine*' \) | grep -q .; then
        msg "el congelado contiene archivos que debían excluirse"; return 1
    fi
    # CA-E23.2: Qt como bibliotecas separadas.
    find "$CONGELADO" -name 'libQt6Core.so*' | grep -q . || { msg "falta libQt6Core.so"; return 1; }
    # CA-E03.3: una sola versión de Python.
    [ "$(find "$CONGELADO" -maxdepth 2 -name 'libpython3*.so*' | wc -l)" -eq 1 ] \
        || { msg "no hay exactamente un libpython"; return 1; }
    # CA-E06.1: recursos obligatorios.
    local r
    for r in LICENSE THIRD-PARTY-NOTICES.txt proxlaunch/recursos/traducciones/proxlaunch_es.qm \
        proxlaunch/recursos/fuentes/OpenSans-Variable.ttf proxlaunch/recursos/fuentes/OpenSans-OFL.txt \
        proxlaunch/recursos/fuentes/JetBrainsMono-Variable.ttf proxlaunch/interfaz/tema/plantilla.qss \
        proxlaunch/recursos/marca/proxlaunch-icono-sin-texto.svg; do
        [ -f "$CONGELADO/_internal/$r" ] || { msg "falta $r en el congelado"; return 1; }
    done
}
paso "Comprobaciones del congelado" comprobar_congelado

# Humo previo (RF-E34): del árbol de fuentes (CA-E17.3) y del congelado, con la plataforma
# offscreen. El humo oficial es el del paquete ya instalado (verificar-deb.sh).
humo_previo() {
    local salida
    salida="$(QT_QPA_PLATFORM=offscreen PYTHONPATH="$RAIZ/src" "$PY" -m proxlaunch \
        --prueba-de-humo --permitir-sin-llavero | grep '^{')" || return 1
    msg "humo del árbol de fuentes: $salida"
    salida="$(QT_QPA_PLATFORM=offscreen "$CONGELADO/proxlaunch" --prueba-de-humo \
        --permitir-sin-llavero | grep '^{')" || return 1
    msg "humo del congelado: $salida"
}
paso "Humo previo (fuentes y congelado, offscreen)" humo_previo
paso "glibc <= 2.35 (CA-E05.1)" "$PY" -I empaquetado/comun/analisis_elf.py glibc "$CONGELADO" --maximo 2.35

# --- Árbol del paquete ---------------------------------------------------------------------
STAGE="$RAIZ/build/deb/proxlaunch_${VERSION}_amd64"

preparar_arbol_deb() {
    rm -rf -- "${STAGE:?}"
    install -d -m 0755 "$STAGE/DEBIAN" "$STAGE/opt" "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
        "$STAGE/usr/share/doc/proxlaunch"
    cp -a "$CONGELADO" "$STAGE/opt/proxlaunch"
    ln -s /opt/proxlaunch/proxlaunch "$STAGE/usr/bin/proxlaunch"
    local lado
    for lado in 16 24 32 48 64 128 256; do
        install -D -m 0644 "build/iconos/proxlaunch-${lado}.png" \
            "$STAGE/usr/share/icons/hicolor/${lado}x${lado}/apps/proxlaunch.png"
    done
    install -m 0644 empaquetado/linux/proxlaunch.desktop "$STAGE/usr/share/applications/proxlaunch.desktop"
    install -m 0644 LICENSE build/THIRD-PARTY-NOTICES.txt "$STAGE/usr/share/doc/proxlaunch/"
    # copyright (DEP-5) con el texto de LICENSE; las líneas en blanco pasan a " ." (formato Debian).
    local licencia
    licencia="$(sed -e 's/^[[:space:]]*$/ ./' -e 's/^\([^ ]\)/ \1/' LICENSE)"
    awk -v lic="$licencia" '{ if ($0 == "@LICENCIA@") print lic; else print }' \
        empaquetado/linux/copyright.in > "$STAGE/usr/share/doc/proxlaunch/copyright"
    chmod 0644 "$STAGE/usr/share/doc/proxlaunch/copyright"
    # Permisos normalizados: nada escribible por grupo/otros, todo legible.
    chmod -R u+rwX,go+rX,go-w "$STAGE"
    local kb
    kb="$(du -sk --apparent-size "$STAGE" | cut -f1)"
    sed -e "s|@VERSION@|$VERSION|" -e "s|@TAMANO_KB@|$kb|" empaquetado/linux/control.in \
        > "$STAGE/DEBIAN/control"
    install -m 0755 empaquetado/linux/postinst empaquetado/linux/postrm "$STAGE/DEBIAN/"
    # Fechas estables (RF-E04b).
    find "$STAGE" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
}
paso "Árbol del paquete" preparar_arbol_deb

paso "Depends completo y sin «not found» (CA-E02.3)" \
    "$PY" -I empaquetado/comun/analisis_elf.py comprobar "$STAGE/opt/proxlaunch" "$STAGE/DEBIAN/control"
if command -v desktop-file-validate >/dev/null; then
    paso "desktop-file-validate (CA-E12.1)" desktop-file-validate "$STAGE/usr/share/applications/proxlaunch.desktop"
else
    die "falta desktop-file-validate (instale desktop-file-utils)"
fi

mkdir -p build/deb
construir_deb() {
    rm -f -- "${RAIZ:?}/build/deb/${NOMBRE_DEB:?}"
    dpkg-deb --root-owner-group -Zxz -z6 --build "$STAGE" "build/deb/$NOMBRE_DEB" >/dev/null
}
paso "dpkg-deb" construir_deb

comprobar_contenido() {
    local contenido info fuera
    contenido="$(dpkg-deb --contents "build/deb/$NOMBRE_DEB")"
    # CA-E02.4: solo las rutas permitidas y sin AppImage.
    fuera="$(awk '{print $6}' <<< "$contenido" | sed 's|^\./||' | grep -v -E \
        '^(opt/proxlaunch(/|$)|usr/bin(/|$)|usr/share/applications(/|$)|usr/share/icons(/|$)|usr/share/doc(/|$)|opt/?$|usr/?$|usr/share/?$|$)' || true)"
    if [ -n "$fuera" ]; then msg "archivos fuera de las rutas permitidas: $fuera"; return 1; fi
    if grep -qi appimage <<< "$contenido"; then msg "el paquete contiene un AppImage"; return 1; fi
    grep -q 'usr/share/doc/proxlaunch/copyright$' <<< "$contenido" || { msg "falta copyright"; return 1; }
    # CA-E02.2: metadatos.
    info="$(dpkg-deb --field "build/deb/$NOMBRE_DEB")"
    grep -q "^Architecture: amd64$" <<< "$info" || return 1
    grep -q "^Version: $VERSION$" <<< "$info" || return 1
    grep -q "^Maintainer: ProxLaunch <noreply@localhost>$" <<< "$info" || return 1
    if grep -E '^Depends:' <<< "$info" | grep -q 'python3'; then msg "Depends incluye python3"; return 1; fi
}
paso "Contenido y metadatos del .deb (CA-E02.2/E02.4)" comprobar_contenido

paso "Presupuesto de tamaño (CA-E19.1)" "$PY" -I empaquetado/comun/presupuesto.py linux \
    "build/deb/$NOMBRE_DEB" "$STAGE"

# --- Publicación local en dist/ (solo si todo salió bien) -----------------------------------------
mkdir -p "$DESTINO"
cp -f "build/deb/$NOMBRE_DEB" "$DESTINO/$NOMBRE_DEB"
if [ "$PROVISIONAL" -eq 1 ]; then
    printf 'Artefacto provisional (iconos sin aprobar o calidad omitida): NO publicable.\n' \
        > "$DESTINO/LEEME-NO-PUBLICABLE.txt"
fi
msg "artefacto: ${DESTINO#"$RAIZ"/}/$NOMBRE_DEB"
msg "tamaño del .deb: $(du -h --apparent-size "$DESTINO/$NOMBRE_DEB" | cut -f1); instalado: $(du -sh --apparent-size "$STAGE/opt" | cut -f1) en /opt/proxlaunch"
[ "$PROVISIONAL" -eq 0 ] || msg "AVISO: artefacto PROVISIONAL; no entrará en SHA256SUMS"
resumen_tiempos
msg "CONSTRUCCIÓN CORRECTA (falta la verificación instalada: verificar-deb.sh)"
