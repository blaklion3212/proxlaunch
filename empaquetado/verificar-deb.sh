#!/usr/bin/env bash
# Verificación del .deb YA INSTALADO (RF-E18, RF-E13, RF-E17; CA-E18.1): metadatos -> instalar ->
# --version sin Python -> humo con pantalla virtual y sin red -> humo con servicio de secretos
# -> (HV-E3) humo sin libxcb-cursor0 -> apt remove -> apt purge -> sin residuos ni cambios en $HOME.
#
# Se ejecuta dentro de Ubuntu 22.04 y de 24.04 (MVs de prueba o runners), con sudo sin contraseña.
# Necesita: xvfb-run (xvfb, xauth), dbus-run-session (dbus-x11), gnome-keyring, desktop-file-utils
# y binutils. No toca el laboratorio ni usa red salvo `apt` para las dependencias del paquete.
#
# Uso: empaquetado/verificar-deb.sh <paquete.deb> [--version-esperada X.Y.Z] [--sin-negativa]
#                                  [--actualizar-desde <anterior.deb>]
#   --actualizar-desde  modo actualización (QA-M5-07): en lugar de la verificación completa, instala el
#                       .deb anterior, siembra datos de usuario, actualiza al <paquete.deb> y comprueba
#                       versión nueva (dpkg y --version), una sola entrada instalada, datos idénticos
#                       (SHA-256) y humo correcto tras actualizar. Pensado para una build de prueba
#                       0.5.1 que no se publica nunca.
set -euo pipefail

NOMBRE_SCRIPT="verificar-deb"
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun/lib.sh"
cd "$RAIZ"

DEB=""
VERSION_ESPERADA=""
ANTERIOR=""
NEGATIVA=1
while [ "$#" -gt 0 ]; do
    case "$1" in
        --version-esperada) VERSION_ESPERADA="${2:?falta la versión}"; shift 2 ;;
        --sin-negativa) NEGATIVA=0; shift ;;
        --actualizar-desde) ANTERIOR="${2:?falta el .deb de la versión anterior}"; shift 2 ;;
        -h | --help) sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) die "argumento desconocido: $1" ;;
        *) DEB="$1"; shift ;;
    esac
done
[ -n "$DEB" ] || die "uso: verificar-deb.sh <paquete.deb> [--version-esperada X.Y.Z] [--sin-negativa] [--actualizar-desde <anterior.deb>]"
[ -f "$DEB" ] || die "no existe el paquete: $DEB"
DEB="$(realpath "$DEB")"

iniciar_registro verificar-deb
guardia_laboratorio
for h in dpkg-deb xvfb-run dbus-run-session gnome-keyring-daemon desktop-file-validate objdump unshare runuser; do
    command -v "$h" >/dev/null || die "falta la herramienta '$h' (use empaquetado/linux/preparar-build.sh o la semilla de la MV)"
done

USUARIO="$(id -un)"
TRABAJO="$(mktemp -d /tmp/plv-XXXX)"
trap 'rm -rf -- "${TRABAJO:?}"' EXIT
SALIDA_HUMO="$TRABAJO/humo.json"
VERSION="$(dpkg-deb --field "$DEB" Version)"
if [ -n "$VERSION_ESPERADA" ] && [ "$VERSION" != "$VERSION_ESPERADA" ]; then
    die "el .deb es ${VERSION} y se esperaba ${VERSION_ESPERADA}"
fi
sudo -n true || die "se necesita sudo sin contraseña (use la MV de prueba)"
VERSION_ANTERIOR=""
if [ -n "$ANTERIOR" ]; then
    [ -f "$ANTERIOR" ] || die "no existe el .deb anterior: $ANTERIOR"
    ANTERIOR="$(realpath "$ANTERIOR")"
    VERSION_ANTERIOR="$(dpkg-deb --field "$ANTERIOR" Version)"
    dpkg --compare-versions "$VERSION_ANTERIOR" lt "$VERSION" \
        || die "el .deb anterior ($VERSION_ANTERIOR) debe ser menor que el nuevo ($VERSION)"
fi

# Listado del $HOME sin lo que cambia por la propia ejecución (copia del repositorio, cachés).
listado_home() {
    # `|| true`: un archivo que desaparece durante el recorrido no debe abortar el paso (set -e activo).
    { find "$HOME" -mindepth 1 \
        \( -path "$RAIZ" -o -path "$HOME/.cache" -o -path "$HOME/.local/share/uv" \
        -o -path "$HOME/.local/bin" -o -path "$HOME/herramientas" -o -path "$HOME/venv-build" \
        -o -path "$HOME/.ssh" -o -path "$HOME/.bash_history" -o -path "$HOME/.sudo_as_admin_successful" \) -prune \
        -o -printf '%P %y %s %T@\n' || true; } | sort
}

# --- Pasos ---------------------------------------------------------------------------------
inspeccionar() {
    dpkg-deb --info "$DEB"
    msg "archivos en el paquete: $(dpkg-deb --contents "$DEB" | wc -l)"
    msg "tamaño del .deb: $(stat -c %s "$DEB") bytes"
    local info
    info="$(dpkg-deb --field "$DEB")"
    grep -q "^Architecture: amd64$" <<< "$info" || return 1
    grep -q "^Maintainer: ProxLaunch <noreply@localhost>$" <<< "$info" || return 1
    if grep -E '^Depends:' <<< "$info" | grep -q 'python3'; then return 1; fi
}

asegurar_no_instalado() {
    if dpkg -s proxlaunch >/dev/null 2>&1; then
        msg "había una instalación previa: se purga"
        sudo -n apt-get purge -y -qq proxlaunch >/dev/null
    fi
    [ ! -e /opt/proxlaunch ] || die "/opt/proxlaunch ya existe sin paquete"
}

instalar() {
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get update -qq
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$DEB"
    grep -q "^Status: install ok installed$" <<< "$(dpkg -s proxlaunch)"
    [ "$(dpkg-query -W -f='${Version}' proxlaunch)" = "$VERSION" ]
    msg "dpkg -s: versión $(dpkg-query -W -f='${Version}' proxlaunch)"
    [ -L /usr/bin/proxlaunch ] || { msg "falta el enlace /usr/bin/proxlaunch"; return 1; }
    [ -x /opt/proxlaunch/proxlaunch ] || { msg "falta el ejecutable /opt/proxlaunch/proxlaunch"; return 1; }
    msg "instalado en /opt/proxlaunch: $(du -sh --apparent-size /opt/proxlaunch | cut -f1) ($(du -sb /opt/proxlaunch | cut -f1) bytes)"
}

integracion_escritorio() {
    desktop-file-validate /usr/share/applications/proxlaunch.desktop
    local lado
    for lado in 16 24 32 48 64 128 256; do
        [ -f "/usr/share/icons/hicolor/${lado}x${lado}/apps/proxlaunch.png" ] || return 1
    done
    [ -f /usr/share/doc/proxlaunch/copyright ] && [ -f /usr/share/doc/proxlaunch/THIRD-PARTY-NOTICES.txt ]
}

dependencias_instaladas() {
    local control="$TRABAJO/control"
    dpkg-deb --field "$DEB" > "$control"
    python3 -I "$RAIZ/empaquetado/comun/analisis_elf.py" comprobar /opt/proxlaunch "$control"
    python3 -I "$RAIZ/empaquetado/comun/analisis_elf.py" glibc /opt/proxlaunch --maximo 2.35
}

version_sin_python() {
    local salida
    # PATH sin ningún directorio con Python (CA-E03.2).
    if env -i HOME="$HOME" PATH=/nonexistent /usr/bin/env python3 --version >/dev/null 2>&1; then
        die "el entorno de prueba no está limpio: hay Python en el PATH"
    fi
    salida="$(env -i HOME="$HOME" PATH=/nonexistent /usr/bin/proxlaunch --version)"
    msg "proxlaunch --version -> $salida"
    [ "$salida" = "ProxLaunch $VERSION" ]
}

# humo_xvfb <prefijo_salida> [VAR=valor...] : humo con pantalla virtual y SIN red (netns propio),
# como el usuario normal y sin servicio de secretos. La dirección de D-Bus apunta a un socket
# inexistente para que libdbus no lance un bus por su cuenta (crearía ~/.dbus). Escribe prefijo.json
# (stdout) y prefijo.err (stderr).
humo_xvfb() {
    local prefijo="$1"; shift
    local t0=$SECONDS rc=0
    sudo -n unshare -n -- runuser -u "$USUARIO" -- env -i HOME="$HOME" PATH=/usr/bin:/bin \
        LANG=C.UTF-8 DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent/bus "$@" timeout 20 xvfb-run -a /usr/bin/proxlaunch --prueba-de-humo \
        --permitir-sin-llavero > "$prefijo.json" 2> "$prefijo.err" || rc=$?
    DURACION_HUMO=$((SECONDS - t0))
    return "$rc"
}

comprobar_json() {
    # $1 = archivo JSON; $2 = plataforma Qt esperada; $3 = (opcional) fragmento del backend esperado.
    python3 -I - "$1" "$2" "${3:-}" <<'PY'
import json, sys
ruta, plataforma, backend = sys.argv[1:4]
# xvfb-run mezcla stderr con stdout: el informe es la única línea que empieza por «{».
lineas = [x for x in open(ruta, encoding="utf-8").read().splitlines() if x.startswith("{")]
if len(lineas) != 1:
    sys.exit(f"se esperaba una sola línea JSON y hay {len(lineas)}")
d = json.loads(lineas[0])
errores = []
if d["problemas"]:
    errores.append(f"problemas: {d['problemas']}")
for campo in ("traductor", "icono_ok", "ventana_mostrada"):
    if not d[campo]:
        errores.append(f"{campo} es falso")
if d["recursos_faltantes"]:
    errores.append(f"recursos faltantes: {d['recursos_faltantes']}")
if d["plataforma_qt"] != plataforma:
    errores.append(f"plataforma Qt {d['plataforma_qt']} (se esperaba {plataforma})")
if backend and backend not in str(d["backend_llavero"]):
    errores.append(f"backend de llavero {d['backend_llavero']} (se esperaba algo con {backend})")
if errores:
    sys.exit("; ".join(errores))
PY
}

humo_con_pantalla() {
    local antes="$TRABAJO/home-antes-humo" despues="$TRABAJO/home-despues-humo"
    listado_home > "$antes"
    humo_xvfb "$TRABAJO/xcb" || { cat "$TRABAJO/xcb.err" >&2; return 1; }
    msg "humo (xcb real, sin red, sin llavero) en ${DURACION_HUMO}s"
    msg "HUMO_JSON_XCB: $(grep '^{' "$TRABAJO/xcb.json")"
    [ "$DURACION_HUMO" -le 15 ] || { msg "el humo tardó más de 15 s"; return 1; }
    comprobar_json "$TRABAJO/xcb.json" xcb
    # CA-E17.2: el humo no deja nada en las carpetas del usuario.
    listado_home > "$despues"
    diff -u "$antes" "$despues" || { msg "el humo modificó \$HOME"; return 1; }
}

humo_offscreen() {
    humo_xvfb "$TRABAJO/off" QT_QPA_PLATFORM=offscreen || { cat "$TRABAJO/off.err" >&2; return 1; }
    msg "HUMO_JSON_OFFSCREEN: $(grep '^{' "$TRABAJO/off.json")"
    comprobar_json "$TRABAJO/off.json" offscreen
}

humo_con_secretos() {
    # CA-E09.2 / HV-E5: D-Bus de sesión + gnome-keyring desbloqueado; el humo solo pregunta el backend.
    local rc=0
    sudo -n unshare -n -- runuser -u "$USUARIO" -- env -i HOME="$HOME" PATH=/usr/bin:/bin LANG=C.UTF-8 \
        timeout 40 dbus-run-session -- bash -c '
            eval "$(printf "%s" "" | gnome-keyring-daemon --unlock --components=secrets 2>/dev/null)"
            export GNOME_KEYRING_CONTROL SSH_AUTH_SOCK
            xvfb-run -a /usr/bin/proxlaunch --prueba-de-humo
        ' > "$TRABAJO/sec.json" 2> "$TRABAJO/sec.err" || rc=$?
    if [ "$rc" -ne 0 ]; then cat "$TRABAJO/sec.err" >&2; cat "$TRABAJO/sec.json" >&2; return 1; fi
    msg "HUMO_JSON_SECRETOS: $(grep '^{' "$TRABAJO/sec.json")"
    comprobar_json "$TRABAJO/sec.json" xcb SecretService
}

prueba_negativa_cursor() {
    # HV-E3: sin libxcb-cursor0 el plugin xcb no carga y el humo debe fallar nombrando la causa.
    sudo -n dpkg --force-depends -r libxcb-cursor0 >/dev/null 2>&1
    local rc=0
    humo_xvfb "$TRABAJO/neg" || rc=$?
    msg "sin libxcb-cursor0: código de salida $rc"
    cat "$TRABAJO/neg.json" "$TRABAJO/neg.err" > "$TRABAJO/neg.txt"
    msg "mensaje: $(tr '\n' ' ' < "$TRABAJO/neg.txt" | cut -c1-400)"
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libxcb-cursor0 >/dev/null
    # El aborto de Qt lo recoge apport: se borra el informe para no dejar residuos (es de la prueba).
    sudo -n rm -f -- /var/crash/_opt_proxlaunch_proxlaunch.*.crash
    [ "$rc" -ne 0 ] || { msg "HV-E3 REFUTADA: el humo pasó sin libxcb-cursor0"; return 1; }
    grep -qi "xcb-cursor" "$TRABAJO/neg.txt" || { msg "HV-E3: falla, pero sin mencionar xcb-cursor"; return 1; }
    msg "HV-E3 CONFIRMADA: sin libxcb-cursor0 el plugin xcb no arranca (y el .deb la declara en Depends)"
}

desinstalar_y_purgar() {
    # Datos de usuario de prueba: deben sobrevivir a remove y purge (RF-E13, CA-E13.1/E13.4).
    mkdir -p "$HOME/.config/ProxLaunch" "$HOME/.local/share/ProxLaunch" "$HOME/.local/state/ProxLaunch"
    printf '{"prueba": true}\n' > "$HOME/.config/ProxLaunch/perfiles.json"
    printf 'dato\n' > "$HOME/.local/share/ProxLaunch/lote.json"
    printf 'registro\n' > "$HOME/.local/state/ProxLaunch/proxlaunch.log"
    local antes="$TRABAJO/home-antes-rm" despues_rm="$TRABAJO/home-despues-rm" despues_pg="$TRABAJO/home-despues-pg"
    listado_home > "$antes"
    local sumas_antes
    sumas_antes="$(cd "$HOME" && sha256sum .config/ProxLaunch/* .local/share/ProxLaunch/* .local/state/ProxLaunch/*)"

    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get remove -y -qq proxlaunch >/dev/null
    [ ! -e /opt/proxlaunch ] && [ ! -e /usr/bin/proxlaunch ] \
        && [ ! -e /usr/share/applications/proxlaunch.desktop ] \
        && [ -z "$(find /usr/share/icons -name 'proxlaunch.png' 2>/dev/null)" ] \
        || { msg "tras apt remove quedan archivos instalados"; return 1; }
    listado_home > "$despues_rm"
    diff -u "$antes" "$despues_rm" || { msg "apt remove cambió \$HOME"; return 1; }

    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq proxlaunch >/dev/null
    if dpkg -L proxlaunch >/dev/null 2>&1; then msg "dpkg -L aún lista archivos tras el purge"; return 1; fi
    listado_home > "$despues_pg"
    diff -u "$antes" "$despues_pg" || { msg "apt purge cambió \$HOME"; return 1; }
    local sumas_despues residuos
    sumas_despues="$(cd "$HOME" && sha256sum .config/ProxLaunch/* .local/share/ProxLaunch/* .local/state/ProxLaunch/*)"
    [ "$sumas_antes" = "$sumas_despues" ] || { msg "los datos del usuario cambiaron"; return 1; }
    # Ningún archivo de proxlaunch fuera de $HOME (el .deb y la copia del repositorio viven allí).
    residuos="$(sudo -n find / -xdev \( -path /home -o -path /root -o -path /proc -o -path /tmp \
        -o -path /var/lib/apt -o -path /var/cache -o -path /var/log \) -prune \
        -o -iname '*proxlaunch*' -print 2>/dev/null || true)"
    if [ -n "$residuos" ]; then msg "residuos: $residuos"; return 1; fi
    msg "sin residuos fuera de \$HOME; datos del usuario intactos (misma suma)"
    rm -rf -- "${HOME:?}/.config/ProxLaunch" "${HOME:?}/.local/share/ProxLaunch" "${HOME:?}/.local/state/ProxLaunch"
}

# --- Actualización (QA-M5-07) ---------------------------------------------------------------
# Datos de usuario sembrados con la versión anterior; deben sobrevivir byte a byte (SHA-256).
DIRS_DATOS=(.config/ProxLaunch .local/share/ProxLaunch .local/state/ProxLaunch)

instalar_anterior() {
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get update -qq
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$ANTERIOR"
    [ "$(dpkg-query -W -f='${Version}' proxlaunch)" = "$VERSION_ANTERIOR" ]
    local salida
    salida="$(env -i HOME="$HOME" PATH=/nonexistent /usr/bin/proxlaunch --version)"
    msg "versión anterior instalada: $salida"
    [ "$salida" = "ProxLaunch $VERSION_ANTERIOR" ]
}

sembrar_datos() {
    local d unico
    for d in "${DIRS_DATOS[@]}"; do mkdir -p "$HOME/$d"; done
    unico="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
    printf '{"prueba": "%s"}\n' "$unico" > "$HOME/.config/ProxLaunch/perfiles.json"
    printf 'dato %s\n' "$unico" > "$HOME/.local/share/ProxLaunch/lote.json"
    printf 'registro %s\n' "$unico" > "$HOME/.local/state/ProxLaunch/proxlaunch.log"
    (cd "$HOME" && sha256sum .config/ProxLaunch/* .local/share/ProxLaunch/* .local/state/ProxLaunch/*) \
        > "$TRABAJO/datos-sembrados.sha"
    listado_home > "$TRABAJO/home-sembrado"
    msg "datos de usuario sembrados con $VERSION_ANTERIOR: $(wc -l < "$TRABAJO/datos-sembrados.sha") archivos"
}

datos_intactos() {
    (cd "$HOME" && sha256sum --check --status "$TRABAJO/datos-sembrados.sha") \
        || { msg "los datos del usuario cambiaron (SHA-256) tras actualizar"; return 1; }
    listado_home > "$TRABAJO/home-actual"
    diff -u "$TRABAJO/home-sembrado" "$TRABAJO/home-actual" \
        || { msg "\$HOME cambió tras actualizar"; return 1; }
    msg "datos de usuario idénticos (misma suma) y \$HOME sin cambios"
}

actualizar() {
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$DEB"
    local version_dpkg entradas salida sin_dueno
    version_dpkg="$(dpkg-query -W -f='${Version}' proxlaunch)"
    msg "dpkg -s: versión $version_dpkg (antes $VERSION_ANTERIOR)"
    [ "$version_dpkg" = "$VERSION" ] || { msg "la versión instalada no es la nueva"; return 1; }
    grep -q "^Status: install ok installed$" <<< "$(dpkg -s proxlaunch)"
    # Una sola entrada instalada del paquete.
    entradas="$(dpkg -l | awk '$2 == "proxlaunch" && $1 == "ii"' | wc -l)"
    [ "$entradas" -eq 1 ] || { msg "hay $entradas entradas instaladas de proxlaunch"; return 1; }
    salida="$(env -i HOME="$HOME" PATH=/nonexistent /usr/bin/proxlaunch --version)"
    msg "proxlaunch --version -> $salida"
    [ "$salida" = "ProxLaunch $VERSION" ] || { msg "--version no informa la versión nueva"; return 1; }
    # Nada de la versión anterior debe quedar sin dueño dentro de /opt/proxlaunch.
    sin_dueno="$(comm -13 <(dpkg -L proxlaunch | sort) <(find /opt/proxlaunch -not -type d | sort) | head -n 5)" || true
    [ -z "$sin_dueno" ] || { msg "archivos sin dueño tras actualizar: $sin_dueno"; return 1; }
    datos_intactos
}

purgar_actualizacion() {
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq proxlaunch >/dev/null
    if dpkg -L proxlaunch >/dev/null 2>&1; then msg "dpkg -L aún lista archivos tras el purge"; return 1; fi
    [ ! -e /opt/proxlaunch ] || { msg "queda /opt/proxlaunch tras el purge"; return 1; }
    local d
    for d in "${DIRS_DATOS[@]}"; do rm -rf -- "${HOME:?}/$d"; done
}

# --- Ejecución -----------------------------------------------------------------------------
msg "Ubuntu $(. /etc/os-release && echo "$VERSION_ID"), paquete $(basename "$DEB") $VERSION"
if [ -n "$ANTERIOR" ]; then
    msg "MODO ACTUALIZACIÓN: $VERSION_ANTERIOR -> $VERSION (build de prueba; no se publica)"
    paso "Inspección del paquete nuevo (dpkg-deb --info)" inspeccionar
    paso "Sin instalación previa" asegurar_no_instalado
    paso "Instalación de la versión anterior ($VERSION_ANTERIOR)" instalar_anterior
    paso "Siembra de datos de usuario con la versión anterior" sembrar_datos
    paso "Actualización a $VERSION (versión, una sola entrada, datos intactos)" actualizar
    paso "--version sin Python en el PATH" version_sin_python
    paso "Humo con xcb real tras actualizar" humo_con_pantalla
    paso "Humo con plataforma offscreen tras actualizar" humo_offscreen
    paso "Datos de usuario intactos tras el humo" datos_intactos
    paso "apt purge y limpieza de los datos de prueba" purgar_actualizacion
    resumen_tiempos
    msg "ACTUALIZACIÓN CORRECTA $VERSION_ANTERIOR -> $VERSION en Ubuntu $(. /etc/os-release && echo "$VERSION_ID")"
    exit 0
fi
paso "Inspección del paquete (dpkg-deb --info)" inspeccionar
paso "Sin instalación previa" asegurar_no_instalado
paso "Instalación con apt (resuelve Depends)" instalar
paso "Integración de escritorio (.desktop, iconos, copyright)" integracion_escritorio
paso "ldd sin «not found», Depends completo y glibc <= 2.35" dependencias_instaladas
paso "--version sin Python en el PATH" version_sin_python
paso "Humo con xcb real, sin red y sin llavero" humo_con_pantalla
paso "Humo con plataforma offscreen" humo_offscreen
paso "Humo con servicio de secretos (Secret Service)" humo_con_secretos
if [ "$NEGATIVA" -eq 1 ]; then paso "Prueba negativa HV-E3 (sin libxcb-cursor0)" prueba_negativa_cursor; fi
paso "apt remove, apt purge y residuos" desinstalar_y_purgar

resumen_tiempos
msg "VERIFICACIÓN CORRECTA de $(basename "$DEB") en Ubuntu $(. /etc/os-release && echo "$VERSION_ID")"
