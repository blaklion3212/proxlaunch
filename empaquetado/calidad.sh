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
# mypy con la configuración de pyproject.toml y PySide6 sin tipos (como en el entorno de desarrollo):
# con los stubs de la rueda de PySide6 aparecen errores de tipos que ese entorno no ve (ver reporte).
"$PY" -I empaquetado/comun/config_mypy.py build/mypy-calidad.ini
paso "mypy src" "$VENV/bin/mypy" --config-file build/mypy-calidad.ini src

export QT_QPA_PLATFORM=offscreen
export COVERAGE_FILE="$RAIZ/build/.coverage"
paso "pytest (sin pruebas de laboratorio)" \
    "$PY" -m pytest -q -m "not integracion" --cov=proxlaunch --cov-report= -p no:cacheprovider
paso "Cobertura del núcleo >= 85 %" \
    "$PY" -m coverage report --include='*/proxlaunch/nucleo/*' --fail-under=85
paso "Cobertura global >= 75 %" "$PY" -m coverage report --fail-under=75

resumen_tiempos
msg "CALIDAD CORRECTA"
