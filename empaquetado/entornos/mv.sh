#!/usr/bin/env bash
# Gestor de las máquinas virtuales de prueba de ProxLaunch (AR-9, RF-E40b, RF-E41).
#
# Uso:
#   mv.sh crear|arrancar|ssh|copiar|traer|detener|restaurar|destruir|estado <mv> [argumentos]
#   mv.sh destruir-todo
# <mv> = ubuntu2204 | ubuntu2404 | windows11
#
# Reglas: red de usuario de QEMU con reenvíos solo en 127.0.0.1 (SSH: 2241, 2242, 2243),
# todo en ~/aprovprox-empaquetado/, sin sudo en el anfitrión y sin tocar el laboratorio Proxmox.
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
        -o LogLevel=ERROR -o ConnectTimeout=5)
}

es_windows() { [ "$MV" = "windows11" ]; }

# La MV de Windows la implementa otra fase: si existe entornos/windows/mv-windows.sh, se carga
# y debe definir windows_crear, windows_arrancar, windows_detener, windows_destruir y windows_estado.
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

puerto_libre() {
    python3 -I -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()'
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
    if [ ! -f "$dest/$IMG_NOMBRE" ] || [ ! -f "$dest/.verificada" ]; then
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
    if [ -f "$DISCO" ]; then
        msg "$MV ya existe (idempotente); use 'destruir' para rehacerla"
        return 0
    fi
    command -v qemu-img >/dev/null || die "falta qemu-img"
    local t0=$SECONDS
    mkdir -p -m 700 "$RAIZ" "$DIR/semilla"
    descargar_imagen
    ssh-keygen -q -t ed25519 -N "" -C "aprovprox-$MV" -f "$CLAVE"
    qemu-img create -q -f qcow2 -b "$IMAGEN" -F qcow2 "$DISCO" 20G
    sed -e "s|@NOMBRE_MV@|$MV|g" -e "s|@CLAVE_PUBLICA@|$(cut -d' ' -f1,2 "$CLAVE.pub")|g" \
        "$AQUI/semilla-ubuntu/user-data.plantilla" > "$DIR/semilla/user-data"
    sed -e "s|@NOMBRE_MV@|$MV|g" "$AQUI/semilla-ubuntu/meta-data.plantilla" > "$DIR/semilla/meta-data"

    # Servidor HTTP efímero de la semilla: solo 127.0.0.1 y solo la carpeta de la semilla.
    local pto_semilla
    pto_semilla="$(puerto_libre)"
    python3 -I -m http.server "$pto_semilla" --bind 127.0.0.1 --directory "$DIR/semilla" \
        >/dev/null 2>&1 &
    local pid_http=$!
    echo "$pid_http" > "$DIR/semilla.pid"
    # shellcheck disable=SC2064
    trap "kill $pid_http 2>/dev/null || true" EXIT

    msg "arrancando $MV por primera vez (cloud-init instala paquetes; unos minutos)"
    lanzar_qemu -smbios "type=1,serial=ds=nocloud;s=http://10.0.2.2:${pto_semilla}/"
    esperar_ssh 300
    local t=0
    until ssh_mv 'test -f /var/lib/aprovprox-listo' 2>/dev/null; do
        t=$((t + 5))
        [ "$t" -le 900 ] || die "cloud-init no terminó en 900s (vea $SERIE)"
        sleep 5
    done
    ssh_mv 'cloud-init status --wait >/dev/null 2>&1 || true; dpkg -s xvfb gnome-keyring >/dev/null' \
        || die "faltan paquetes de la semilla en $MV"
    kill "$pid_http" 2>/dev/null || true
    rm -f -- "${DIR:?}/semilla.pid"
    trap - EXIT
    detener_qemu
    qemu-img snapshot -c "$SNAPSHOT_LIMPIO" "$DISCO"
    msg "$MV creada y detenida con la instantánea '$SNAPSHOT_LIMPIO' ($((SECONDS - t0)) s)"
}

cmd_arrancar() {
    if es_windows; then delegar_windows arrancar "$@"; return; fi
    [ -f "$DISCO" ] || die "$MV no existe: ejecute 'mv.sh crear $MV'"
    if en_marcha; then
        msg "$MV ya está en marcha"
    else
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
# Solo termina procesos cuya línea de órdenes apunta a ~/aprovprox-empaquetado (nunca el laboratorio).
procesos_propios() {
    local pid linea
    for pid in $(pgrep -f -- "$RAIZ/" || true); do
        [ "$pid" = "$$" ] && continue
        linea="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        case "$linea" in
            *qemu-system*|*swtpm*|*http.server*) echo "$pid" ;;
        esac
    done
}

destruir_todo() {
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
        for d in /tmp/plw-* /tmp/plg-*; do
            [ -e "$d" ] || continue
            echo "temporal eliminado: $d"
            rm -rf -- "${d:?}"
        done
        echo "--- comprobación ---"
        echo "procesos propios restantes: $(procesos_propios | wc -l)"
        echo "puertos 2241-2243 en escucha:"
        ss -ltn 2>/dev/null | grep -E ':(2241|2242|2243)\b' || echo "  ninguno"
        echo "carpeta de MVs: $([ -e "$RAIZ" ] && echo 'AÚN EXISTE' || echo 'no existe')"
    } | tee "$reg"
    msg "registro en $reg"
}

# --- Despacho -------------------------------------------------------------------------------
[ "$#" -ge 1 ] || die "uso: mv.sh {crear|arrancar|ssh|copiar|traer|detener|restaurar|destruir|estado} <mv> | destruir-todo"
accion="$1"; shift
if [ "$accion" = "destruir-todo" ]; then destruir_todo; exit 0; fi
[ "$#" -ge 1 ] || die "falta el nombre de la MV"
configurar "$1"; shift
case "$accion" in
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
