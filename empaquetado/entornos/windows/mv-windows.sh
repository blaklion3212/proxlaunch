#!/usr/bin/env bash
# MV de Windows 11 (ISO oficial de Microsoft, edición Pro sin activar) con KVM/QEMU, TPM 2.0 emulado (swtpm) y Secure Boot (RF-E40, RF-E42,
# AR-9, sección 6.2). Lo carga `mv.sh windows11 <acción>` con `source`: no se ejecuta solo.
# Contrato con mv.sh: windows_crear, windows_arrancar, windows_detener, windows_destruir (y, además,
# windows_instrucciones). Variables heredadas de mv.sh: MV, DIR, PUERTO, CLAVE, PIDFILE, RAIZ, REPO,
# SSH_OPCIONES y las funciones msg, die, en_marcha, ssh_mv.
#
# Disposición de la carpeta de la MV ($RAIZ/windows11, modo 700, fuera del repositorio):
#   disco.qcow2          disco SATA de 80 GB
#   OVMF_VARS.fd         copia propia de OVMF_VARS_4M.ms.fd (claves de Secure Boot de Microsoft)
#   tpm/                 estado del TPM 2.0 de swtpm
#   apoyo/               unidad de apoyo FAT de solo lectura (preparar.ps1, clave.pub, contrasena.txt)
#   id_ed25519(.pub)     clave SSH de la MV
#   contrasena-prueba    contraseña de «prueba» (modo 600; nunca en el repositorio ni en registros)
#   fase                 «instalando» hasta que SSH responde por primera vez; después «lista»
#   dir-socket           ruta del directorio corto /tmp/plw-XXXX con los sockets (swtpm y QMP)
# La ISO la deja el usuario en $RAIZ/iso/ y su registro (ISO-ORIGEN.txt) vive junto a ella.
# Variables opcionales: PROXLAUNCH_ISO (nombre del archivo dentro de iso/; por defecto la única .iso) y
# PROXLAUNCH_ISO_SHA256 (suma confirmada contra la lista oficial de Microsoft; o bien un archivo
# iso/ISO.sha256 con «suma  nombre»). Con suma esperada, una ISO distinta se rechaza.

WIN_AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIN_RAM_MB=6144
WIN_CPUS=4
WIN_DISCO="80G"
WIN_PAGINA_OFICIAL="https://www.microsoft.com/es-mx/software-download/windows11"
WIN_LIMITE_SOCKET=107   # sun_path de un socket Unix admite 108 bytes incluido el cero final

if ! declare -F msg >/dev/null 2>&1; then
    msg() { printf '[mv] %s\n' "$*"; }
    die() { printf '[mv] ERROR: %s\n' "$*" >&2; exit 1; }
fi

# --- Firmware, ISO y comprobaciones previas ------------------------------------------------------

windows_firmware() {
    local d
    for d in /usr/share/OVMF /usr/share/edk2/ovmf /usr/share/edk2-ovmf; do
        if [ -f "$d/OVMF_CODE_4M.ms.fd" ] && [ -f "$d/OVMF_VARS_4M.ms.fd" ]; then
            OVMF_CODIGO="$d/OVMF_CODE_4M.ms.fd"
            OVMF_VARIABLES="$d/OVMF_VARS_4M.ms.fd"
            return 0
        fi
    done
    die "no se encontraron OVMF_CODE_4M.ms.fd y OVMF_VARS_4M.ms.fd (paquete ovmf)"
}

windows_requisitos() {
    local h
    for h in qemu-system-x86_64 qemu-img swtpm swtpm_setup ssh ssh-keygen scp python3; do
        command -v "$h" >/dev/null 2>&1 || die "falta $h en el anfitrión"
    done
    if [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ]; then die "/dev/kvm no es accesible"; fi
    windows_firmware
}

# Imprime la ruta de la ISO (la de PROXLAUNCH_ISO o la única de $RAIZ/iso/); o termina con una explicación.
windows_buscar_iso() {
    local isos=() f
    if [ -n "${PROXLAUNCH_ISO:-}" ]; then
        case "$PROXLAUNCH_ISO" in */* | .*) die "PROXLAUNCH_ISO debe ser un nombre de archivo de $RAIZ/iso/" ;; esac
        if [ -f "$RAIZ/iso/$PROXLAUNCH_ISO" ]; then isos+=("$RAIZ/iso/$PROXLAUNCH_ISO"); fi
    else
        for f in "$RAIZ"/iso/*.iso; do [ -f "$f" ] && isos+=("$f"); done
    fi
    if [ "${#isos[@]}" -eq 0 ]; then
        cat >&2 <<EOF
[mv] No hay ninguna ISO de Windows 11 en $RAIZ/iso/

     Descargue usted la ISO oficial de Windows 11 (64 bits) desde la página de Microsoft:
         $WIN_PAGINA_OFICIAL
     y déjela en:  $RAIZ/iso/
     Compare su SHA-256 con la lista «Verificar la descarga» de esa página. Después repita:
         empaquetado/entornos/mv.sh crear windows11
     (No se usan ISO de terceros ni claves ajenas; Windows 11 Pro se usa sin activar.)
EOF
        return 1
    fi
    [ "${#isos[@]}" -eq 1 ] || die "hay más de una ISO en $RAIZ/iso/; deje solo una o fije PROXLAUNCH_ISO"
    # No se usa una ISO que aún se está copiando o descargando (cambia de tamaño o se modificó hace poco).
    local tamano1 tamano2 edad
    tamano1="$(stat -c %s "${isos[0]}")"
    edad=$(( $(date +%s) - $(stat -c %Y "${isos[0]}") ))
    sleep 2
    tamano2="$(stat -c %s "${isos[0]}")"
    if [ "$tamano1" != "$tamano2" ] || [ "$edad" -lt 30 ]; then
        echo "[mv] La ISO ${isos[0]##*/} parece estar copiándose o descargándose todavía; espere a que termine y repita." >&2
        return 1
    fi
    echo "${isos[0]}"
}

# --- Piezas de la MV -----------------------------------------------------------------------------

# Contraseña aleatoria de «prueba» (alfabeto sin caracteres ambiguos; con mayúsculas, minúsculas y dígitos).
windows_generar_contrasena() {
    python3 -I - <<'EOF'
import secrets

mayusculas = "ABCDEFGHJKLMNPQRSTUVWXYZ"
minusculas = "abcdefghijkmnpqrstuvwxyz"
digitos = "23456789"
todo = mayusculas + minusculas + digitos
caracteres = [secrets.choice(mayusculas), secrets.choice(minusculas), secrets.choice(digitos)]
caracteres += [secrets.choice(todo) for _ in range(13)]
secrets.SystemRandom().shuffle(caracteres)
print("".join(caracteres))
EOF
}

# Unidad de apoyo: carpeta con preparar.ps1, la clave pública y la contraseña (modo 700 en el anfitrión).
windows_preparar_apoyo() {
    local apoyo="$DIR/apoyo"
    rm -rf -- "${apoyo:?}"
    mkdir -p -m 700 "$apoyo"
    cp "$WIN_AQUI/preparar.ps1" "$apoyo/preparar.ps1"
    cut -d' ' -f1,2 "$CLAVE.pub" > "$apoyo/clave.pub"
    ( umask 077; cp "$DIR/contrasena-prueba" "$apoyo/contrasena.txt" )
    chmod 600 "$apoyo"/*
}

# Estado del TPM 2.0 (sin certificados: swtpm-localca necesitaría privilegios; Windows 11 no los exige).
windows_preparar_tpm() {
    rm -rf -- "${DIR:?}/tpm"
    mkdir -p -m 700 "$DIR/tpm"
    swtpm_setup --tpm2 --tpmstate "$DIR/tpm" --createek --decryption --lock-nvram --overwrite \
        --config /dev/null >"$DIR/swtpm-setup.log" 2>&1 \
        || die "swtpm_setup falló (vea $DIR/swtpm-setup.log)"
}

# Directorio corto para los sockets (swtpm y QMP): < 108 caracteres (CL-E21, S-E8).
windows_directorio_socket() {
    local dir
    dir="$(mktemp -d /tmp/plw-XXXX)"
    chmod 700 "$dir"
    # La ruta más larga que se usará es <dir>/swtpm.sock; se comprueba antes de arrancar nada.
    if [ "${#dir}" -gt $((WIN_LIMITE_SOCKET - 12)) ]; then
        rm -rf -- "${dir:?}"
        die "la ruta del socket es demasiado larga (${#dir} caracteres)"
    fi
    echo "$dir" > "$DIR/dir-socket"
    echo "$dir"
}

windows_comprobar_ruta_socket() {
    local ruta="$1"
    [ "${#ruta}" -le "$WIN_LIMITE_SOCKET" ] \
        || die "la ruta del socket mide ${#ruta} caracteres (máximo $WIN_LIMITE_SOCKET): ${ruta}"
}

windows_arrancar_swtpm() {
    local sockdir="$1"
    local sock="$sockdir/swtpm.sock"
    windows_comprobar_ruta_socket "$sock"
    swtpm socket --tpmstate "dir=$DIR/tpm" --ctrl "type=unixio,path=$sock,terminate" --tpm2 \
        --log "file=$DIR/swtpm.log,level=1" --pid "file=$DIR/swtpm.pid" --daemon \
        || die "no arrancó swtpm (vea $DIR/swtpm.log)"
    local t=0
    until [ -S "$sock" ]; do
        t=$((t + 1)); [ "$t" -le 10 ] || die "swtpm no creó su socket (vea $DIR/swtpm.log)"
        sleep 1
    done
}

windows_detener_swtpm() {
    if [ -f "$DIR/swtpm.pid" ]; then
        local pid
        pid="$(cat "$DIR/swtpm.pid" 2>/dev/null || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null \
            && tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "swtpm"; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f -- "$DIR/swtpm.pid"
    fi
    if [ -f "$DIR/dir-socket" ]; then
        local sockdir
        sockdir="$(cat "$DIR/dir-socket")"
        case "$sockdir" in /tmp/plw-*) rm -rf -- "${sockdir:?}" ;; esac
        rm -f -- "$DIR/dir-socket"
    fi
}

# Construye ARGS_QEMU (arreglo) con la configuración de la MV. $1 = directorio de sockets,
# $2 = «con-iso» (usa $WIN_ISO) o «sin-iso».
windows_armar_qemu() {
    local sockdir="$1" modo="$2"
    windows_firmware
    ARGS_QEMU=(
        -name "guest=aprovprox-$MV,process=aprovprox-$MV"
        -machine q35,accel=kvm,smm=on
        -global driver=cfi.pflash01,property=secure,value=on
        -cpu host -smp "$WIN_CPUS" -m "$WIN_RAM_MB" -rtc base=localtime
        -drive "if=pflash,format=raw,unit=0,file=$OVMF_CODIGO,readonly=on"
        -drive "if=pflash,format=raw,unit=1,file=$DIR/OVMF_VARS.fd"
        -chardev "socket,id=chrtpm,path=$sockdir/swtpm.sock"
        -tpmdev emulator,id=tpm0,chardev=chrtpm
        -device tpm-tis,tpmdev=tpm0
        -drive "file=$DIR/disco.qcow2,if=none,id=hd0,format=qcow2,cache=writeback,discard=unmap"
        -device ide-hd,drive=hd0,bus=ide.0,bootindex=2
        -netdev "user,id=n0,hostfwd=tcp:127.0.0.1:${PUERTO}-:22"
        -device e1000e,netdev=n0
        -device qemu-xhci,id=xhci
        -device usb-tablet,bus=xhci.0
        -blockdev "driver=vvfat,node-name=apoyo,dir=$DIR/apoyo,read-only=on,label=APOYO"
        -device usb-storage,bus=xhci.0,drive=apoyo
        -device VGA,vgamem_mb=64
        -display gtk
        -qmp "unix:$sockdir/qmp.sock,server=on,wait=off"
        -pidfile "$PIDFILE"
    )
    if [ "$modo" = "con-iso" ]; then
        ARGS_QEMU+=(
            -drive "file=$WIN_ISO,if=none,id=cd0,media=cdrom,readonly=on,format=raw"
            -device ide-cd,drive=cd0,bus=ide.1,bootindex=1
        )
    fi
}

windows_qmp() {
    local sockdir
    sockdir="$(cat "$DIR/dir-socket" 2>/dev/null || true)"
    [ -S "$sockdir/qmp.sock" ] || return 1
    python3 -I - "$sockdir/qmp.sock" "$1" <<'EOF'
import socket
import sys

s = socket.socket(socket.AF_UNIX)
s.settimeout(5)
s.connect(sys.argv[1])
s.recv(4096)
s.sendall(b'{"execute":"qmp_capabilities"}\n')
s.recv(4096)
s.sendall(sys.argv[2].encode() + b"\n")
s.recv(4096)
EOF
}

windows_lanzar() {
    local modo="$1"
    windows_requisitos
    if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        die "no hay escritorio gráfico (DISPLAY/WAYLAND_DISPLAY): la MV de Windows se muestra en una ventana"
    fi
    windows_detener_swtpm
    local sockdir
    sockdir="$(windows_directorio_socket)"
    windows_arrancar_swtpm "$sockdir"
    WIN_ISO=""
    if [ "$modo" = "con-iso" ]; then WIN_ISO="$(windows_buscar_iso)" || exit 1; fi
    windows_armar_qemu "$sockdir" "$modo"
    rm -f -- "$PIDFILE"
    setsid nohup qemu-system-x86_64 "${ARGS_QEMU[@]}" >>"$DIR/qemu.log" 2>&1 < /dev/null &
    local t=0
    until [ -s "$PIDFILE" ]; do
        t=$((t + 1))
        if [ "$t" -gt 20 ]; then
            windows_detener_swtpm
            die "QEMU no arrancó (vea $DIR/qemu.log)"
        fi
        sleep 1
    done
    msg "MV windows11 en marcha (pid $(cat "$PIDFILE"), SSH en 127.0.0.1:$PUERTO cuando esté preparada)"
}

# Espera a que SSH responda (PowerShell es el intérprete por defecto de sshd: «exit 0» es la orden neutra).
windows_esperar_ssh() {
    local limite="$1" t=0
    until ssh_mv 'exit 0' 2>/dev/null; do
        t=$((t + 3))
        [ "$t" -le "$limite" ] || return 1
        en_marcha || die "QEMU de $MV terminó antes de tiempo (vea $DIR/qemu.log)"
        sleep 3
    done
}

# --- Instrucciones para el usuario ---------------------------------------------------------------

windows_instrucciones() {
    [ -f "$DIR/contrasena-prueba" ] || die "la MV windows11 no existe: ejecute 'mv.sh crear windows11'"
    local clave
    clave="$(cat "$DIR/contrasena-prueba")"
    cat <<EOF

============================================================================================
 INSTALACIÓN DE WINDOWS 11 (una sola vez, la hace usted)
============================================================================================
La ventana de la MV ya está abierta. Haga clic dentro de ella para usar el teclado y el ratón
(para soltar el ratón: Ctrl+Alt+G). Siga estos pasos:

 1. Cuando aparezca «Press any key to boot from CD or DVD», pulse una tecla dentro de la ventana.
 2. En el asistente de instalación: elija idioma y teclado y pulse «Instalar ahora». En «Activar Windows»
    elija «No tengo clave de producto» y, en la lista de ediciones, «Windows 11 Pro». Lea y acepte usted
    mismo la licencia de Microsoft (este programa no la acepta por usted). Elija instalación
    «Personalizada» y el disco vacío de 80 GB; no hace falta tocar nada más.
 3. Windows se reiniciará solo varias veces. No pulse ninguna tecla en «Press any key to boot from CD
    or DVD» durante los reinicios: debe arrancar desde el disco.
 4. En el asistente inicial de Windows (OOBE): elija región y teclado a su gusto. La MV ya tiene
    Internet (red de usuario de QEMU). Para crear una CUENTA LOCAL sin cuenta Microsoft elija
    «Configurar para trabajo o escuela» > «Opciones de inicio de sesión» > «Unirse a un dominio en su
    lugar» (no se une a ningún dominio: crea una cuenta local). Si esa opción no aparece en esta
    versión (25H2), pulse Mayús+F10 para abrir una consola y escriba:  start ms-cxh:localonly
    y siga el asistente de cuenta local. Datos de la cuenta:

        Nombre de usuario:  prueba
        Contraseña:         $clave

    (Escriba la contraseña exactamente así. Si pide preguntas de seguridad, responda lo que quiera.
    Desactive los permisos de privacidad que no quiera: da igual para las pruebas.)
 5. Cuando llegue al escritorio de Windows, abra PowerShell como administrador: pulse la tecla Windows,
    escriba «powershell», clic derecho en «Windows PowerShell» > «Ejecutar como administrador» > «Sí».
 6. En esa ventana de PowerShell escriba estas DOS líneas (la unidad de apoyo se llama APOYO):

        \$u = (Get-Volume -FileSystemLabel APOYO).DriveLetter
        powershell -NoProfile -ExecutionPolicy Bypass -File "\${u}:\\preparar.ps1"

    Si no la encuentra: abra el Explorador de archivos, entre en la unidad «APOYO», anote su letra X y
    escriba:   powershell -NoProfile -ExecutionPolicy Bypass -File X:\\preparar.ps1
 7. preparar.ps1 instala OpenSSH Server, autoriza la clave de la MV, configura el inicio de sesión
    automático y le informa del TPM 2.0 y de Secure Boot. Termina con «LISTO». Puede tardar unos minutos.
 8. En el anfitrión (esta terminal) ejecute:

        empaquetado/entornos/mv.sh arrancar windows11

    Eso comprueba la conexión SSH, expulsa el DVD y deja la MV lista. A partir de ahí se usa con
    empaquetado/verificar-todo.sh windows (sin tocar la ventana).

 Para volver a ver estas instrucciones: empaquetado/entornos/mv.sh instrucciones windows11
 Si algo sale mal, la MV se puede rehacer con:  empaquetado/entornos/mv.sh destruir windows11
============================================================================================
EOF
}

# --- Acciones del contrato ----------------------------------------------------------------------

windows_crear() {
    if [ -f "$DIR/creada" ]; then
        msg "windows11 ya existe (idempotente); use 'destruir' para rehacerla"
        windows_instrucciones
        return 0
    fi
    windows_requisitos
    local iso
    iso="$(windows_buscar_iso)" || exit 1
    msg "comprobando la ISO y registrando su origen (SHA-256, URL oficial y fecha)"
    local esperada="${PROXLAUNCH_ISO_SHA256:-}" extra=()
    if [ -z "$esperada" ] && [ -f "$RAIZ/iso/ISO.sha256" ]; then
        esperada="$(awk 'NR==1{print $1}' "$RAIZ/iso/ISO.sha256")"
    fi
    if [ -n "$esperada" ]; then
        extra=(--sha256-esperada "$esperada" --fecha-verificacion "$(date +%F)")
    else
        msg "AVISO: sin suma esperada; se registrará solo la calculada (compárela con la lista de Microsoft)"
    fi
    python3 -I "$WIN_AQUI/comprobar-iso.py" "$iso" --registro "$RAIZ/iso/ISO-ORIGEN.txt" \
        --url "$WIN_PAGINA_OFICIAL" ${extra[@]+"${extra[@]}"} || die "la ISO no es válida (vea arriba)"

    mkdir -p -m 700 "$RAIZ" "$DIR"
    msg "creando disco de $WIN_DISCO, variables UEFI, TPM 2.0 y clave SSH"
    qemu-img create -q -f qcow2 "$DIR/disco.qcow2" "$WIN_DISCO"
    cp "$OVMF_VARIABLES" "$DIR/OVMF_VARS.fd"
    chmod 600 "$DIR/OVMF_VARS.fd"
    windows_preparar_tpm
    rm -f -- "$CLAVE" "$CLAVE.pub"
    ssh-keygen -q -t ed25519 -N "" -C "aprovprox-$MV" -f "$CLAVE"
    ( umask 077; windows_generar_contrasena > "$DIR/contrasena-prueba" )
    chmod 600 "$DIR/contrasena-prueba"
    windows_preparar_apoyo
    echo "instalando" > "$DIR/fase"
    touch "$DIR/creada"

    windows_lanzar con-iso
    windows_instrucciones
}

windows_arrancar() {
    [ -f "$DIR/creada" ] || die "windows11 no existe: ejecute 'mv.sh crear windows11'"
    local fase
    fase="$(cat "$DIR/fase" 2>/dev/null || echo instalando)"
    if en_marcha; then
        msg "windows11 ya está en marcha"
    elif [ "$fase" = "instalando" ]; then
        windows_lanzar con-iso
    else
        windows_lanzar sin-iso
    fi
    if [ "$fase" = "instalando" ]; then
        if windows_esperar_ssh 15; then
            echo "lista" > "$DIR/fase"
            windows_qmp '{"execute":"eject","arguments":{"id":"cd0","force":true}}' 2>/dev/null || true
            msg "SSH responde: Windows quedó preparado; el DVD se expulsó y no se vuelve a conectar"
        else
            msg "La MV está en marcha, pero SSH aún no responde: la instalación de Windows no ha terminado"
            msg "o falta ejecutar preparar.ps1. Siga los pasos de:  mv.sh instrucciones windows11"
            return 0
        fi
    else
        windows_esperar_ssh 300 || die "windows11 no respondió por SSH en 300 s (¿se ejecutó preparar.ps1? vea mv.sh instrucciones windows11)"
    fi
    msg "windows11 lista (SSH en 127.0.0.1:$PUERTO)"
    # Registro de TPM y Secure Boot (CA-E40.3, M-E10): informativo.
    ssh_mv 'try { $t = Get-Tpm; "TPM presente: $($t.TpmPresent); listo: $($t.TpmReady)" } catch { "TPM: sin datos" }; try { "Secure Boot activo: $(Confirm-SecureBootUEFI)" } catch { "Secure Boot: sin datos" }' 2>/dev/null \
        | while IFS= read -r l; do msg "  $l"; done || true
}

windows_detener() {
    if en_marcha; then
        local pid t=0
        pid="$(cat "$PIDFILE")"
        # Apagado ordenado: primero por SSH; si no, por QMP (botón de apagado ACPI).
        ssh_mv 'Stop-Computer -Force' 2>/dev/null || windows_qmp '{"execute":"system_powerdown"}' 2>/dev/null || true
        while kill -0 "$pid" 2>/dev/null; do
            t=$((t + 1))
            if [ "$t" -gt 120 ]; then
                msg "apagado ordenado agotado; terminando QEMU ($pid)"
                kill "$pid" 2>/dev/null || true
                sleep 2
                kill -9 "$pid" 2>/dev/null || true
                break
            fi
            sleep 1
        done
    fi
    rm -f -- "$PIDFILE"
    windows_detener_swtpm
    msg "windows11 detenida"
}

windows_destruir() {
    if [ -d "$DIR" ]; then
        windows_detener || true
        windows_detener_swtpm
        rm -rf -- "${DIR:?}"
    fi
    msg "windows11 destruida (la ISO y las descargas siguen en $RAIZ; 'destruir-todo' las borra)"
}
