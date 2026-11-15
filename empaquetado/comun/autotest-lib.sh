#!/usr/bin/env bash
# Autotest de lib.sh (QA-M5-01/02): comprueba que `paso` hace fallar la orden en cuanto un comando
# intermedio falla (set -e activo dentro de la función) y que el resto del contrato se cumple.
# No usa red, MVs ni sudo. Uso: empaquetado/comun/autotest-lib.sh   (sale 0 si todo es correcto)
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/plk-autotest-XXXX")"
trap 'rm -rf -- "${TMP:?}"' EXIT
fallos=0

# ejecutar_caso <nombre> <código esperado> <cuerpo de bash>: corre el cuerpo en un bash nuevo con lib.sh.
ejecutar_caso() {
    local nombre="$1" esperado="$2" cuerpo="$3" rc=0
    bash -c "set -euo pipefail; NOMBRE_SCRIPT=autotest; . '$AQUI/lib.sh'; $cuerpo" \
        >"$TMP/salida" 2>&1 || rc=$?
    if [ "$rc" -ne "$esperado" ]; then
        printf 'FALLÓ  %s: código %s (se esperaba %s)\n' "$nombre" "$rc" "$esperado"
        sed 's/^/    /' "$TMP/salida"
        fallos=$((fallos + 1))
    else
        printf 'correcto  %s\n' "$nombre"
    fi
}

# 1. El caso del hallazgo: un comando intermedio falla y `paso` debe fallar sin llegar al final.
ejecutar_caso "paso falla si un comando intermedio falla" 1 \
    'f() { false; echo sigue; }; paso "caso" f'
if grep -q '^sigue$' "$TMP/salida"; then
    echo "FALLÓ  paso siguió ejecutando tras el fallo (se imprimió «sigue»)"
    fallos=$((fallos + 1))
fi

# 2. Lo mismo con la salida de una orden externa y con una función anidada.
ejecutar_caso "paso falla con una función anidada" 1 \
    'g() { false; }; f() { g; echo sigue; }; paso "caso" f'
ejecutar_caso "paso falla con una orden externa" 1 'paso "caso" false'

# 3. Un paso correcto devuelve 0 y registra el tiempo.
ejecutar_caso "paso correcto devuelve 0 y mide el tiempo" 0 \
    'f() { true; echo bien; }; paso "caso" f; [ "${#TIEMPOS[@]}" -eq 1 ]'

# 4. Un `return 1` explícito dentro de la función también corta el paso.
ejecutar_caso "paso falla con return 1" 1 'f() { return 1; }; paso "caso" f'

# 5. La subshell no ejecuta la trampa EXIT del llamador (no borra su carpeta de trabajo).
ejecutar_caso "la trampa EXIT del llamador no corre dentro del paso" 0 \
    "d='$TMP/trampa'; mkdir -p \"\$d\"; trap 'rm -rf -- \"\$d\"' EXIT; f() { true; }; paso caso f; [ -d \"\$d\" ]"

if [ "$fallos" -ne 0 ]; then
    echo "autotest de lib.sh: $fallos caso(s) fallido(s)" >&2
    exit 1
fi
echo "autotest de lib.sh correcto"
