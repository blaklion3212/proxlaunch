#!/usr/bin/env bash
# Exclusión mutua con el laboratorio Proxmox (SEG-M5-02). Se carga con `source`; no ejecuta nada.
# Define: comprobar_exclusion_laboratorio. Necesita `die` del llamador.
#
# Las MVs de empaquetado (QEMU con KVM) no deben convivir con el laboratorio de Proxmox: comparten
# el anfitrión y, sin esta guarda, un fallo de uno podría afectar al otro. La función se niega si:
#   - hay algo escuchando en el puerto 8006 o 2222 (reenvíos habituales del laboratorio), o
#   - existe algún proceso cuya línea de órdenes contenga «aprovprox-lab».
# Solo LEE el estado (/proc/net/tcp y la lista de procesos); no toca el laboratorio.
# El lado inverso (que el laboratorio rechace arrancar con MVs de empaquetado) queda fuera de alcance.

LAB_PUERTOS_PROHIBIDOS="8006 2222"
LAB_MARCA_PROCESO="aprovprox-lab"

# Imprime los puertos prohibidos que están en escucha (IPv4 e IPv6, cualquier dirección local).
_lab_puertos_en_escucha() {
    python3 -I - "$LAB_PUERTOS_PROHIBIDOS" <<'PY'
import sys

prohibidos = {int(p) for p in sys.argv[1].split()}
encontrados = set()
for tabla in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
        with open(tabla, encoding="ascii") as f:
            next(f, None)
            for linea in f:
                campos = linea.split()
                # campos[1] = dirección_local:puerto (hex); campos[3] = estado (0A = LISTEN)
                if len(campos) > 3 and campos[3] == "0A":
                    puerto = int(campos[1].rsplit(":", 1)[1], 16)
                    if puerto in prohibidos:
                        encontrados.add(puerto)
    except OSError:
        continue
print(" ".join(str(p) for p in sorted(encontrados)))
PY
}

# Imprime «pid:ejecutable» de los procesos del laboratorio, sin incluir este proceso ni sus ancestros
# (un intérprete que solo mencione la marca en su propia orden no cuenta como laboratorio).
_lab_procesos() {
    local propios=" $$ " p pid exe
    p=$$
    while [ -r "/proc/$p/status" ]; do
        p="$(awk '/^PPid:/ {print $2}' "/proc/$p/status" 2>/dev/null || echo 0)"
        [ -n "$p" ] && [ "$p" -gt 1 ] || break
        propios+="$p "
    done
    for pid in $(pgrep -f -- "$LAB_MARCA_PROCESO" 2>/dev/null || true); do
        case "$propios" in *" $pid "*) continue ;; esac
        exe="$(basename "$(readlink "/proc/$pid/exe" 2>/dev/null || echo desconocido)")"
        echo "$pid:$exe"
    done
}

comprobar_exclusion_laboratorio() {
    local puertos procesos
    puertos="$(_lab_puertos_en_escucha)"
    procesos="$(_lab_procesos | tr '\n' ' ')"
    if [ -n "$puertos" ] || [ -n "${procesos// /}" ]; then
        [ -z "$puertos" ] || printf '[exclusión] hay algo escuchando en el/los puerto(s): %s\n' "$puertos" >&2
        [ -z "${procesos// /}" ] || printf '[exclusión] procesos del laboratorio (pid:ejecutable): %s\n' "$procesos" >&2
        die "el laboratorio Proxmox parece estar activo: no se arrancan MVs de empaquetado a la vez (SEG-M5-02). Detenga el laboratorio y repita"
    fi
}
