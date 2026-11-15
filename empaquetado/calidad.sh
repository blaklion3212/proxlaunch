#!/usr/bin/env bash
# Calidad de ProxLaunch en Linux (RF-E32, RF-E33): lockfile con hashes, ruff, mypy, pytest y cobertura.
# Orden fijo; cada paso falla el script si falla. Nunca ejecuta pruebas de laboratorio (D-15).
# Uso: empaquetado/calidad.sh
set -euo pipefail

NOMBRE_SCRIPT="calidad"
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun/lib.sh"
cd "$RAIZ"
[ -n "${REGISTRO_YA_INICIADO:-}" ] || { iniciar_registro calidad; export REGISTRO_YA_INICIADO=1; }
guardia_laboratorio

# Autotest de lib.sh: `paso` debe cortar en cuanto falle un comando intermedio (QA-M5-01/02).
paso "Autotest de paso (set -e activo dentro de la orden)" bash empaquetado/comun/autotest-lib.sh

preparar_uv
VENV="$RAIZ/build/venv-calidad"
PY="$VENV/bin/python"

paso "Entorno desde el lockfile (--require-hashes)" \
    crear_entorno "$VENV" empaquetado/requisitos/linux-calidad.txt
paso "Lockfiles coherentes" "$PY" -I empaquetado/comun/comprobar_lock.py
paso "Revisión estática de los scripts" "$PY" -I empaquetado/comun/revisar_estatico.py

if grep -q -e "--force-enable-socket" pyproject.toml; then
    die "pyproject.toml no debe habilitar sockets reales (RF-E33)"
fi

paso "ruff check" "$VENV/bin/ruff" check src tests empaquetado
paso "ruff format --check" "$VENV/bin/ruff" format --check src tests empaquetado
# mypy con la configuración de pyproject.toml y los stubs reales de PySide6 de la rueda fijada.
paso "mypy src" "$VENV/bin/mypy" src
paso "mypy src (plataforma Windows)" "$VENV/bin/mypy" --platform win32 src

export QT_QPA_PLATFORM=offscreen
export COVERAGE_FILE="$RAIZ/build/.coverage"
paso "pytest (sin pruebas de laboratorio)" \
    "$PY" -m pytest -q -m "not integracion" --cov=proxlaunch --cov-report= -p no:cacheprovider
paso "Cobertura del núcleo >= 85 %" \
    "$PY" -m coverage report --include='*/proxlaunch/nucleo/*' --fail-under=85
paso "Cobertura global >= 75 %" "$PY" -m coverage report --fail-under=75

resumen_tiempos
msg "CALIDAD CORRECTA"
