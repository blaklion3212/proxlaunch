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
if [ "$MV" = "windows11" ]; then
    # Windows: el intérprete de sshd es PowerShell, que no transporta binarios por tuberías; se copia
    # el archivo por scp y se extrae con tar.exe (incluido en Windows 10/11).
    tgz="$(mktemp /tmp/plk-arbol-XXXX)"
    trap 'rm -f -- "${lista:?}" "${tgz:?}"' EXIT
    tar --null -T "$lista" -czf "$tgz"
    "$AQUI/mv.sh" copiar "$MV" "$tgz" arbol-proxlaunch.tgz
    "$AQUI/mv.sh" ssh "$MV" "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue '$REMOTA'; New-Item -ItemType Directory -Force -Path '$REMOTA' | Out-Null; tar.exe -xzmf arbol-proxlaunch.tgz -C '$REMOTA'; \$codigo = \$LASTEXITCODE; Remove-Item -Force arbol-proxlaunch.tgz; exit \$codigo"
else
    tar --null -T "$lista" -czf - \
        | "$AQUI/mv.sh" ssh "$MV" "rm -rf -- \"\$HOME/$REMOTA\" && mkdir -p \"\$HOME/$REMOTA\" && tar -xzmf - -C \"\$HOME/$REMOTA\""
fi
echo "[enviar-arbol] árbol enviado a $MV:~/$REMOTA ($(git rev-parse --short HEAD))"
