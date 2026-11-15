#!/usr/bin/env bash
# Envía a una MV el árbol limpio del repositorio: archivos versionados y no ignorados, con los
# cambios del árbol de trabajo (equivale a `git archive HEAD` + parche). No incluye .venv, build/,
# dist/ ni secretos (están en .gitignore).
# Uso: enviar-arbol.sh <mv> [carpeta_remota] [--version-prueba X.Y.Z]
#   carpeta_remota      por defecto ~/proxlaunch, que se recrea vacía.
#   --version-prueba    SOLO en la COPIA enviada a la MV cambia __version__ (build de prueba para verificar
#                       actualizaciones, QA-M5-07). El repositorio no se modifica nunca. Úsese con una
#                       carpeta remota distinta de la principal (p. ej. proxlaunch-act).
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$AQUI/../.." && pwd)"
MV="${1:?uso: enviar-arbol.sh <mv> [carpeta_remota] [--version-prueba X.Y.Z]}"
shift
REMOTA="proxlaunch"
VERSION_PRUEBA=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --version-prueba) VERSION_PRUEBA="${2:?falta la versión}"; shift 2 ;;
        -*) echo "ERROR: argumento desconocido: $1" >&2; exit 1 ;;
        *) REMOTA="$1"; shift ;;
    esac
done
case "$REMOTA" in ""|/*|*..*|*[!A-Za-z0-9._-]*) echo "ERROR: carpeta remota no válida: $REMOTA" >&2; exit 1 ;; esac
if [ -n "$VERSION_PRUEBA" ] && ! [[ "$VERSION_PRUEBA" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    echo "ERROR: --version-prueba debe ser X.Y.Z (SemVer sin sufijos): $VERSION_PRUEBA" >&2; exit 1
fi

cd "$REPO"
# Los archivos versionados que se borraron en el árbol de trabajo se omiten.
lista="$(mktemp /tmp/plk-lista-XXXX)"
trap 'rm -f -- "${lista:?}"' EXIT
git ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' f; do
    if [ -e "$f" ]; then printf '%s\0' "$f"; fi
done > "$lista"
if [ "$MV" = "windows11" ]; then
    # Windows: el intérprete de sshd es PowerShell, que no transporta binarios por tuberías; se copia
    # el archivo por scp y se extrae con tar.exe (incluido en Windows 10/11).
    tgz="$(mktemp /tmp/plk-arbol-XXXX)"
    trap 'rm -f -- "${lista:?}" "${tgz:?}"' EXIT
    tar --null -T "$lista" -czf "$tgz"
    "$AQUI/mv.sh" copiar "$MV" "$tgz" arbol-proxlaunch.tgz
    "$AQUI/mv.sh" ssh "$MV" "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue '$REMOTA'; New-Item -ItemType Directory -Force -Path '$REMOTA' | Out-Null; tar.exe -xzmf arbol-proxlaunch.tgz -C '$REMOTA'; \$codigo = \$LASTEXITCODE; Remove-Item -Force arbol-proxlaunch.tgz; exit \$codigo"
    if [ -n "$VERSION_PRUEBA" ]; then
        # Solo la copia de la MV: se reescribe la línea __version__ y se comprueba el resultado.
        "$AQUI/mv.sh" ssh "$MV" "\$f = '$REMOTA\\src\\proxlaunch\\__init__.py'; \$c = [IO.File]::ReadAllText((Resolve-Path \$f).Path); \$n = [regex]::Replace(\$c, '(?m)^(__version__\\s*=\\s*)\"[^\"]*\"', '\${1}\"$VERSION_PRUEBA\"'); if (\$n -eq \$c) { exit 1 }; [IO.File]::WriteAllText((Resolve-Path \$f).Path, \$n, (New-Object Text.UTF8Encoding(\$false))); exit 0"
    fi
else
    tar --null -T "$lista" -czf - \
        | "$AQUI/mv.sh" ssh "$MV" "rm -rf -- \"\$HOME/$REMOTA\" && mkdir -p \"\$HOME/$REMOTA\" && tar -xzmf - -C \"\$HOME/$REMOTA\""
    if [ -n "$VERSION_PRUEBA" ]; then
        "$AQUI/mv.sh" ssh "$MV" "sed -i -E 's/^(__version__ *= *)\"[^\"]*\"/\\1\"$VERSION_PRUEBA\"/' \"\$HOME/$REMOTA/src/proxlaunch/__init__.py\" && grep -qx '__version__ = \"$VERSION_PRUEBA\"' \"\$HOME/$REMOTA/src/proxlaunch/__init__.py\""
    fi
fi
echo "[enviar-arbol] árbol enviado a $MV:~/$REMOTA ($(git rev-parse --short HEAD))${VERSION_PRUEBA:+; COPIA con versión de prueba $VERSION_PRUEBA}"
