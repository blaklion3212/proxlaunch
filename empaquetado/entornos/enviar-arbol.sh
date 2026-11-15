#!/usr/bin/env bash
# Envía a una MV el árbol limpio del repositorio: archivos versionados y no ignorados, con los
# cambios del árbol de trabajo (equivale a `git archive HEAD` + parche). No incluye .venv, build/,
# dist/ ni secretos (están en .gitignore).
# Uso: enviar-arbol.sh <mv> [carpeta_remota]   (por defecto ~/proxlaunch, que se recrea vacía)
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$AQUI/../.." && pwd)"
MV="${1:?uso: enviar-arbol.sh <mv> [carpeta_remota]}"
REMOTA="${2:-proxlaunch}"

cd "$REPO"
# Los archivos versionados que se borraron en el árbol de trabajo se omiten.
lista="$(mktemp /tmp/plk-lista-XXXX)"
trap 'rm -f -- "${lista:?}"' EXIT
git ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' f; do
    [ -e "$f" ] && printf '%s\0' "$f"
done > "$lista"
case "$REMOTA" in ""|/*|*..*) echo "ERROR: carpeta remota no válida: $REMOTA" >&2; exit 1 ;; esac
tar --null -T "$lista" -czf - \
    | "$AQUI/mv.sh" ssh "$MV" "rm -rf -- \"\$HOME/$REMOTA\" && mkdir -p \"\$HOME/$REMOTA\" && tar -xzmf - -C \"\$HOME/$REMOTA\""
echo "[enviar-arbol] árbol enviado a $MV:~/$REMOTA ($(git rev-parse --short HEAD))"
