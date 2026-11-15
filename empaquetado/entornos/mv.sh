#!/usr/bin/env bash
# Gestor de las máquinas virtuales de prueba de ProxLaunch (AR-9, RF-E40b, RF-E41).
#
# Uso:
#   mv.sh crear|arrancar|ssh|copiar|traer|detener|restaurar|destruir|estado <mv> [argumentos]
#   mv.sh instrucciones windows11      (vuelve a mostrar los pasos de instalación de Windows)
#   mv.sh destruir-todo                (QEMU, swtpm, estado del TPM, /tmp/plw-*, ISO y carpetas de todas las MVs)
# <mv> = ubuntu2204 | ubuntu2404 | windows11
#
# Reglas: red de usuario de QEMU con reenvíos solo en 127.0.0.1 (SSH: 2241, 2242, 2243),
# todo en ~/aprovprox-empaquetado/, sin sudo en el anfitrión y sin tocar el laboratorio Proxmox.
# `crear` y `arrancar` se niegan si el laboratorio parece activo (puertos 8006/2222 o procesos
# «aprovprox-lab»; comun/exclusion-laboratorio.sh, SEG-M5-02).
# Semilla de cloud-init: disco NoCloud (vvfat con etiqueta CIDATA), sin servidor HTTP (SEG-M5-03).
# Variable opcional PROXLAUNCH_SEMILLA=http usa un servidor HTTP efímero en un puerto libre (plan B).
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$AQUI/../.." && pwd)"
RAIZ="$HOME/aprovprox-empaquetado"
REGISTROS="$REPO/build/registros"
LLAVERO_UBUNTU="/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg"
MV_RAM_MB=4096
MV_CPUS=4
SNAPSHOT_LIMPIO="limpio"

msg() { printf '[mv] %s\n' "$*"; }
die() { printf '[mv] ERROR: %s\n' "$*" >&2; exit 1; }

# shellcheck source=../comun/exclusion-laboratorio.sh
. "$AQUI/../comun/exclusion-laboratorio.sh"

# --- Configuración por MV -------------------------------------------------------------------
configurar() {
    MV="$1"
    DIR="$RAIZ/$MV"
    case "$MV" in
        ubuntu2204) CODIGO="22.04"; PUERTO=2241 ;;
        ubuntu2404) CODIGO="24.04"; PUERTO=2242 ;;
        windows11)  CODIGO="";      PUERTO=2243 ;;
        *) die "MV desconocida: '$MV' (use ubuntu2204, ubuntu2404 o windows11)" ;;
    esac
    IMG_NOMBRE="ubuntu-${CODIGO}-server-cloudimg-amd64.img"
    IMG_URL="https://cloud-images.ubuntu.com/releases/${CODIGO}/release"
    DISCO="$DIR/disco.qcow2"
    CLAVE="$DIR/id_ed25519"
    PIDFILE="$DIR/qemu.pid"
    SERIE="$DIR/serie.log"
    SSH_OPCIONES=(-i "$CLAVE" -p "$PUERTO" -o IdentitiesOnly=yes -o BatchMode=yes
        -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$DIR/known_hosts"
        -o LogLevel=ERROR -o ConnectTimeout=5 -o ServerAliveInterval=30 -o ServerAliveCountMax=40)
}

es_windows() { [ "$MV" = "windows11" ]; }

# La MV de Windows vive en entornos/windows/mv-windows.sh, que se carga aquí y define windows_crear,
# windows_arrancar, windows_detener, windows_destruir y windows_instrucciones.
delegar_windows() {
    local accion="$1"; shift
    local gancho="$AQUI/windows/mv-windows.sh"
    [ -f "$gancho" ] || die "windows11 aún no está implementado en este árbol (falta $gancho)"
    # shellcheck source=/dev/null
    . "$gancho"
    "windows_${accion}" "$@"
}

en_marcha() {
    [ -f "$PIDFILE" ] || return 1
    local pid
    pid="$(cat "$PIDFILE")"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && grep -q "aprovprox-empaquetado" "/proc/$pid/cmdline" 2>/dev/null
}

# Plan B de la semilla (PROXLAUNCH_SEMILLA=http): servidor HTTP efímero SOLO en 127.0.0.1 que se enlaza
# al puerto 0 (lo elige el sistema, sin la carrera de «buscar un puerto libre y usarlo después»), escribe
# el puerto real en $DIR/semilla.puerto y sirve únicamente la carpeta de la semilla. Deja SEMILLA_PUERTO
# y SEMILLA_PID; el llamador lo detiene con semilla_http_detener.
semilla_http_iniciar() {
    rm -f -- "${DIR:?}/semilla.puerto"
    python3 -I -c 'import functools, http.server, sys
manejador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=sys.argv[2])
servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
with open(sys.argv[1], "w", encoding="ascii") as f:
    f.write(str(servidor.server_address[1]))
servidor.serve_forever()' "$DIR/semilla.puerto" "$DIR/semilla" >/dev/null 2>&1 &
    SEMILLA_PID=$!
    echo "$SEMILLA_PID" > "$DIR/semilla.pid"
    local t=0
    until [ -s "$DIR/semilla.puerto" ]; do
        t=$((t + 1))
        if [ "$t" -gt 50 ] || ! kill -0 "$SEMILLA_PID" 2>/dev/null; then
            semilla_http_detener
            die "el servidor HTTP de la semilla no arrancó"
        fi
        sleep 0.2
    done
    SEMILLA_PUERTO="$(cat "$DIR/semilla.puerto")"
    # Se comprueba que el servidor vive antes de lanzar QEMU.
    kill -0 "$SEMILLA_PID" 2>/dev/null || die "el servidor HTTP de la semilla terminó antes de lanzar QEMU"
    msg "semilla por HTTP en 127.0.0.1:$SEMILLA_PUERTO (puerto asignado por el sistema)"
}

semilla_http_detener() {
    local pid
    pid="$(cat "$DIR/semilla.pid" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; fi
    rm -f -- "${DIR:?}/semilla.pid" "${DIR:?}/semilla.puerto"
}

# MVs creadas por versiones anteriores de este script no tienen la marca «creada»: si el disco ya trae
# la instantánea «limpio» (se tomó al final de la creación), se les pone la marca.
migrar_marca_creada() {
    if [ -f "$DIR/creada" ] || [ ! -f "$DISCO" ] || en_marcha; then return 0; fi
    if qemu-img snapshot -l "$DISCO" 2>/dev/null | awk -v s="$SNAPSHOT_LIMPIO" '$2 == s { f = 1 } END { exit !f }'; then
        : > "$DIR/creada"
        msg "$MV creada con una versión anterior del script: se registra la marca «creada»"
    fi
}

ssh_mv() { ssh "${SSH_OPCIONES[@]}" prueba@127.0.0.1 "$@"; }

esperar_ssh() {
    local limite="${1:-240}" t=0
    until ssh_mv true 2>/dev/null; do
        t=$((t + 3))
        [ "$t" -le "$limite" ] || die "la MV $MV no respondió por SSH en ${limite}s (vea $SERIE)"
        en_marcha || die "QEMU de $MV terminó antes de tiempo (vea $SERIE)"
        sleep 3
    done
}

# --- Descarga verificada de la imagen cloud -------------------------------------------------
descargar_imagen() {
    local dest="$RAIZ/imagenes/$CODIGO"
    mkdir -p -m 700 "$dest"
    if [ -f "$dest/$IMG_NOMBRE" ] && [ -f "$dest/.verificada" ]; then
        verificar_imagen_base "$dest"
    else
        msg "descargando SHA256SUMS y firma de Ubuntu $CODIGO"
        curl --proto '=https' --tlsv1.2 -fsSL -o "$dest/SHA256SUMS" "$IMG_URL/SHA256SUMS"
        curl --proto '=https' --tlsv1.2 -fsSL -o "$dest/SHA256SUMS.gpg" "$IMG_URL/SHA256SUMS.gpg"
        if [ -f "$LLAVERO_UBUNTU" ]; then
            local gh
            gh="$(mktemp -d /tmp/plg-XXXX)"
            if ! GNUPGHOME="$gh" gpgv --keyring "$LLAVERO_UBUNTU" "$dest/SHA256SUMS.gpg" \
                "$dest/SHA256SUMS" 2>"$dest/gpgv.log"; then
                rm -rf -- "${gh:?}"
                die "la firma GPG de SHA256SUMS no es válida (vea $dest/gpgv.log)"
            fi
            rm -rf -- "${gh:?}"
            msg "firma GPG de SHA256SUMS verificada con $LLAVERO_UBUNTU"
            echo "gpg: verificada" > "$dest/.verificada-gpg"
        else
            msg "AVISO: no existe $LLAVERO_UBUNTU; solo se verifica la suma SHA-256"
            echo "gpg: no verificada (sin llavero)" > "$dest/.verificada-gpg"
        fi
        msg "descargando $IMG_NOMBRE (puede tardar)"
        curl --proto "=https" --tlsv1.2 -fsSL --retry 3 -o "$dest/$IMG_NOMBRE" "$IMG_URL/$IMG_NOMBRE"
        local esperada real
        esperada="$(grep -E " \*?${IMG_NOMBRE}\$" "$dest/SHA256SUMS" | awk '{print $1}')"
        [ -n "$esperada" ] || die "SHA256SUMS no lista $IMG_NOMBRE"
        real="$(sha256sum "$dest/$IMG_NOMBRE" | awk '{print $1}')"
        if [ "$esperada" != "$real" ]; then
            rm -f -- "${dest:?}/${IMG_NOMBRE:?}"
            die "la suma SHA-256 de la imagen no coincide con SHA256SUMS"
        fi
        echo "$real  $IMG_NOMBRE" > "$dest/.verificada"
        msg "SHA-256 de la imagen verificada: $real"
    fi
    IMAGEN="$dest/$IMG_NOMBRE"
}

# Al reutilizar la imagen cloud se vuelve a calcular su SHA-256 y se compara con el valor guardado en
# .verificada cuando se descargó y verificó (SEG-M5-05). Es la base (backing file) de los discos.
verificar_imagen_base() {
    local dest="${1:-$RAIZ/imagenes/$CODIGO}" esperada real
    [ -f "$dest/$IMG_NOMBRE" ] && [ -f "$dest/.verificada" ] \
        || die "falta la imagen base verificada en $dest"
    esperada="$(awk '{print $1}' "$dest/.verificada")"
    real="$(sha256sum "$dest/$IMG_NOMBRE" | awk '{print $1}')"
    [ -n "$esperada" ] && [ "$real" = "$esperada" ] \
        || die "la imagen base $IMG_NOMBRE ya no coincide con la suma verificada: borre $dest y repita 'crear'"
}

# --- QEMU -----------------------------------------------------------------------------------
lanzar_qemu() {
    local extra=("$@")
    if [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ]; then die "/dev/kvm no es accesible"; fi
    # Reenvío solo en 127.0.0.1; sin puentes ni acceso desde fuera del anfitrión.
    qemu-system-x86_64 \
        -name "guest=aprovprox-$MV,process=aprovprox-$MV" \
        -machine q35,accel=kvm -cpu host -smp "$MV_CPUS" -m "$MV_RAM_MB" \
        -display none -daemonize -pidfile "$PIDFILE" -serial "file:$SERIE" \
        -drive "file=$DISCO,if=virtio,format=qcow2,cache=writeback" \
        -netdev "user,id=n0,hostfwd=tcp:127.0.0.1:${PUERTO}-:22" \
        -device virtio-net-pci,netdev=n0 \
        "${extra[@]}"
}

# --- Acciones -------------------------------------------------------------------------------
cmd_crear() {
    if es_windows; then delegar_windows crear "$@"; return; fi
    command -v qemu-img >/dev/null || die "falta qemu-img"
    migrar_marca_creada
    if [ -f "$DIR/creada" ]; then
        msg "$MV ya existe (idempotente); use 'destruir' para rehacerla"
        return 0
    fi
    # Sin la marca «creada» (se escribe solo tras la instantánea «limpio») cualquier resto viene de una
    # creación interrumpida: se limpia y se rehace desde cero (QA-M5-08).
    if [ -e "$DIR" ]; then
        msg "restos de una creación interrumpida de $MV: se limpian y se rehace"
        detener_qemu 2>/dev/null || true
        semilla_http_detener
        rm -rf -- "${DIR:?}"
    fi
    local t0=$SECONDS
    mkdir -p -m 700 "$RAIZ" "$DIR/semilla"
    descargar_imagen
    rm -f -- "$CLAVE" "$CLAVE.pub"
    ssh-keygen -q -t ed25519 -N "" -C "aprovprox-$MV" -f "$CLAVE" < /dev/null
    qemu-img create -q -f qcow2 -b "$IMAGEN" -F qcow2 "$DISCO" 20G
    sed -e "s|@NOMBRE_MV@|$MV|g" -e "s|@CLAVE_PUBLICA@|$(cut -d' ' -f1,2 "$CLAVE.pub")|g" \
        "$AQUI/semilla-ubuntu/user-data.plantilla" > "$DIR/semilla/user-data"
    sed -e "s|@NOMBRE_MV@|$MV|g" "$AQUI/semilla-ubuntu/meta-data.plantilla" > "$DIR/semilla/meta-data"

    # Semilla NoCloud: unidad FAT (vvfat de solo lectura) con la etiqueta CIDATA, sin red ni puertos.
    local extra=()
    case "${PROXLAUNCH_SEMILLA:-disco}" in
        disco)
            extra=(-blockdev "driver=vvfat,node-name=semilla,dir=$DIR/semilla,read-only=on,label=CIDATA"
                -device "virtio-blk-pci,drive=semilla")
            ;;
        http)
            semilla_http_iniciar
            # shellcheck disable=SC2064
            trap "semilla_http_detener" EXIT
            extra=(-smbios "type=1,serial=ds=nocloud;s=http://10.0.2.2:${SEMILLA_PUERTO}/")
            ;;
        *) die "PROXLAUNCH_SEMILLA debe ser «disco» o «http»" ;;
    esac

    msg "arrancando $MV por primera vez (cloud-init instala paquetes; unos minutos)"
    lanzar_qemu "${extra[@]}"
    esperar_ssh 300
    local t=0
    until ssh_mv 'test -f /var/lib/aprovprox-listo' 2>/dev/null; do
        t=$((t + 5))
        [ "$t" -le 900 ] || die "cloud-init no terminó en 900s (vea $SERIE)"
        sleep 5
    done
    ssh_mv 'cloud-init status --wait >/dev/null 2>&1 || true; dpkg -s xvfb gnome-keyring >/dev/null' \
        || die "faltan paquetes de la semilla en $MV"
    semilla_http_detener
    trap - EXIT
    detener_qemu
    qemu-img snapshot -c "$SNAPSHOT_LIMPIO" "$DISCO"
    # La marca se escribe al final: su existencia significa «creación completa con instantánea limpia».
    : > "$DIR/creada"
    msg "$MV creada y detenida con la instantánea '$SNAPSHOT_LIMPIO' ($((SECONDS - t0)) s)"
}

cmd_arrancar() {
    if es_windows; then delegar_windows arrancar "$@"; return; fi
    migrar_marca_creada
    [ -f "$DIR/creada" ] || die "$MV no existe o su creación quedó incompleta: ejecute 'mv.sh crear $MV'"
    if en_marcha; then
        msg "$MV ya está en marcha"
    else
        verificar_imagen_base
        lanzar_qemu
    fi
    esperar_ssh 240
    msg "$MV lista (SSH en 127.0.0.1:$PUERTO)"
}

detener_qemu() {
    if ! en_marcha; then rm -f -- "${PIDFILE:?}"; return 0; fi
    local pid t=0
    pid="$(cat "$PIDFILE")"
    ssh_mv 'sudo systemctl poweroff' 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null; do
        t=$((t + 1))
        if [ "$t" -gt 90 ]; then
            msg "apagado ordenado agotado; terminando QEMU ($pid)"
            kill "$pid" 2>/dev/null || true
            sleep 2
            kill -9 "$pid" 2>/dev/null || true
            break
        fi
        sleep 1
    done
    rm -f -- "${PIDFILE:?}"
}

cmd_detener() {
    if es_windows; then delegar_windows detener "$@"; return; fi
    detener_qemu
    msg "$MV detenida"
}

cmd_restaurar() {
    if es_windows; then die "restaurar no aplica a windows11"; fi
    if en_marcha; then die "detenga $MV antes de restaurarla"; fi
    migrar_marca_creada
    [ -f "$DIR/creada" ] || die "$MV no existe o su creación quedó incompleta: ejecute 'mv.sh crear $MV'"
    qemu-img snapshot -a "$SNAPSHOT_LIMPIO" "$DISCO"
    msg "$MV restaurada a la instantánea '$SNAPSHOT_LIMPIO'"
}

cmd_ssh() {
    if ! es_windows && ! en_marcha; then die "$MV no está en marcha"; fi
    ssh_mv "$@"
}

# copiar <mv> <origen_local>... <destino_remoto>
cmd_copiar() {
    [ "$#" -ge 2 ] || die "uso: mv.sh copiar <mv> <origen>... <destino_remoto>"
    local destino="${*: -1}"
    local origenes=("${@:1:$#-1}")
    scp -q -r -i "$CLAVE" -P "$PUERTO" -o IdentitiesOnly=yes -o BatchMode=yes \
        -o "UserKnownHostsFile=$DIR/known_hosts" -o LogLevel=ERROR \
        "${origenes[@]}" "prueba@127.0.0.1:$destino"
}

# traer <mv> <origen_remoto>... <destino_local>
cmd_traer() {
    [ "$#" -ge 2 ] || die "uso: mv.sh traer <mv> <origen_remoto>... <destino_local>"
    local destino="${*: -1}"
    local remotos=() o
    for o in "${@:1:$#-1}"; do remotos+=("prueba@127.0.0.1:$o"); done
    scp -q -r -i "$CLAVE" -P "$PUERTO" -o IdentitiesOnly=yes -o BatchMode=yes \
        -o "UserKnownHostsFile=$DIR/known_hosts" -o LogLevel=ERROR \
        "${remotos[@]}" "$destino"
}

cmd_destruir() {
    if es_windows; then delegar_windows destruir "$@"; return; fi
    detener_qemu 2>/dev/null || true
    if [ -d "$DIR" ]; then rm -rf -- "${DIR:?}"; fi
    msg "$MV destruida"
}

cmd_estado() {
    if es_windows && [ ! -f "$AQUI/windows/mv-windows.sh" ]; then
        echo "$MV: no implementada"; return 0
    fi
    if [ ! -d "$DIR" ]; then echo "$MV: no existe"; return 0; fi
    if en_marcha; then echo "$MV: en marcha (pid $(cat "$PIDFILE"), SSH 127.0.0.1:$PUERTO)"
    else echo "$MV: detenida"; fi
}

# --- Limpieza total (RF-E41, 6.3) --------------------------------------------------------------
# Solo termina procesos DEL USUARIO ACTUAL cuya línea de órdenes apunta a ~/aprovprox-empaquetado
# (nunca el laboratorio ni procesos de otros usuarios).
procesos_propios() {
    local pid linea exe uid
    uid="$(id -u)"
    # Por la carpeta de las MVs y también por el directorio corto de sockets de swtpm/QMP (CL-E22).
    for pid in $( { pgrep -u "$uid" -f -- "$RAIZ/" || true; pgrep -u "$uid" -f -- "/tmp/plw-" || true; } | sort -u); do
        [ "$pid" = "$$" ] && continue
        # Se identifica por el ejecutable (no por texto de la línea de órdenes): así un intérprete
        # de órdenes que solo mencione estas rutas nunca se confunde con una MV.
        exe="$(basename "$(readlink "/proc/$pid/exe" 2>/dev/null || true)")"
        linea="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        case "$exe" in
            qemu-system-* | swtpm) echo "$pid" ;;
            python3*) case "$linea" in *http.server*) echo "$pid" ;; esac ;;
        esac
    done
}

# Temporales del usuario actual que dejan estos scripts en /tmp: sockets de las MVs (plw-), gpg (plg-) y
# listas o árboles de enviar-arbol.sh y comprobar_lock.py (plk-). Solo lo que es DEL usuario.
temporales_propios() {
    find /tmp -maxdepth 1 -user "$(id -un)" \( -name 'plw-*' -o -name 'plg-*' -o -name 'plk-*' \) -print0 2>/dev/null
}

destruir_todo() {
    [ "$(id -u)" -ne 0 ] || die "destruir-todo no se ejecuta como root (solo toca lo del usuario actual)"
    mkdir -p "$REGISTROS"
    local reg
    reg="$REGISTROS/limpieza-$(date +%Y%m%d-%H%M%S).txt"
    {
        echo "Limpieza total de las MVs de prueba de ProxLaunch - $(date -Is)"
        local pid d
        for pid in $(procesos_propios); do
            echo "proceso terminado: $pid"
            kill "$pid" 2>/dev/null || true
        done
        sleep 2
        for pid in $(procesos_propios); do
            kill -9 "$pid" 2>/dev/null || true
        done
        if [ -d "$RAIZ" ]; then
            echo "archivos eliminados:"
            find "$RAIZ" -maxdepth 2 -printf '  %p (%s bytes)\n' 2>/dev/null || true
            rm -rf -- "${RAIZ:?}"
        fi
        while IFS= read -r -d '' d; do
            echo "temporal eliminado: $d"
            rm -rf -- "${d:?}"
        done < <(temporales_propios)
        echo "--- comprobación ---"
        echo "procesos propios restantes: $(procesos_propios | wc -l)"
        echo "puertos 2241-2243 en escucha:"
        ss -ltn 2>/dev/null | grep -E ':(2241|2242|2243)\b' || echo "  ninguno"
        echo "temporales /tmp/plw-*, plg-*, plk-* restantes (propios): $(temporales_propios | tr -cd '\0' | wc -c)"
        echo "ISO de Windows y estado del TPM: $([ -e "$RAIZ/iso" ] || [ -e "$RAIZ/windows11/tpm" ] && echo 'AÚN EXISTEN' || echo 'eliminados')"
        echo "carpeta de MVs: $([ -e "$RAIZ" ] && echo 'AÚN EXISTE' || echo 'no existe')"
    } | tee "$reg"
    msg "registro en $reg"
}

# --- Despacho -------------------------------------------------------------------------------
[ "$#" -ge 1 ] || die "uso: mv.sh {crear|arrancar|ssh|copiar|traer|detener|restaurar|destruir|estado|instrucciones} <mv> | destruir-todo"
accion="$1"; shift
if [ "$accion" = "destruir-todo" ]; then destruir_todo; exit 0; fi
[ "$#" -ge 1 ] || die "falta el nombre de la MV"
configurar "$1"; shift
# Exclusión mutua con el laboratorio Proxmox: solo al crear o arrancar (nunca al detener o limpiar).
case "$accion" in crear | arrancar) comprobar_exclusion_laboratorio ;; esac
case "$accion" in
    instrucciones)
        es_windows || die "solo windows11 tiene instrucciones de instalación"
        delegar_windows instrucciones "$@" ;;
    crear)     cmd_crear "$@" ;;
    arrancar)  cmd_arrancar "$@" ;;
    ssh)       cmd_ssh "$@" ;;
    copiar)    cmd_copiar "$@" ;;
    traer)     cmd_traer "$@" ;;
    detener)   cmd_detener "$@" ;;
    restaurar) cmd_restaurar "$@" ;;
    destruir)  cmd_destruir "$@" ;;
    estado)    cmd_estado "$@" ;;
    *) die "acción desconocida: $accion" ;;
esac
