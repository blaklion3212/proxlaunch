# Convenciones de ESTE proyecto

## Stack
- Python >= 3.11 (el equipo de desarrollo usa 3.14); interfaz con PySide6.
- Dependencias de ejecución: PySide6-Essentials (sin Addons ni WebEngine, para instaladores más livianos), requests (sin proxmoxer, D-17), keyring, platformdirs.
- Desarrollo: pytest, pytest-qt, pytest-cov, responses, pytest-socket, ruff, mypy.
- Gestor: venv local en `.venv` (ignorado por git) + pip; metadatos en `pyproject.toml`
  (setuptools, layout `src/`, paquete `proxlaunch`).

## Estructura de carpetas
- `src/proxlaunch/nucleo/`: Python puro, NUNCA importa PySide6 (lo verifica una prueba).
  Contiene `modelos/`, `api/`, `servicios/`, `persistencia/` y módulos de reglas.
- `src/proxlaunch/interfaz/`: PySide6 (`tema/`, `dialogos/`, `vistas/`).
- `src/proxlaunch/recursos/`: marca (SVG), fuentes, traducciones; declarados como datos del paquete.
- `tests/`: `nucleo/`, `interfaz/`, `integracion/` (solo con `PROXLAUNCH_LAB=1`), `datos/respuestas/`.
- `docs/`: decisiones, requisitos y arquitectura (`docs/arquitectura/mvp1.md` manda en interfaces).

## Estilo y patrones
- Linter/formateo: ruff (line-length 100, py311, reglas E,F,I,B,UP,SIM); tipos con mypy.
- Identificadores del dominio en español (según la arquitectura); comentarios y docstrings en español.
- El núcleo devuelve códigos (`CodigoError`/`CodigoProblema`), la interfaz los traduce con `tr()`;
  el núcleo no contiene textos para el usuario.
- Dependencias (reloj, transporte, llavero, carpetas) se inyectan.
- Los secretos nunca se persisten ni se registran en el log.
- Firmas públicas de la arquitectura: no cambiar sin consultar al orquestador.

## Prohibido
- Importar Qt/PySide6 desde `proxlaunch.nucleo`.
- Colores fuera de `interfaz/tema/paleta.py`; reglas de versión fuera de `capacidades.py`.
- Guardar contraseñas, tokens o tickets en archivos; commitear `.venv` o secretos.
- Acceso a red real en pruebas (bloqueado por pytest-socket).

## Comandos (desde la raíz del repo)
- Crear entorno: `python3 -m venv .venv` y, si falta pip, instalarlo con get-pip.py usando
  `.venv/bin/python -I get-pip.py` (descargado fuera del repo).
- Instalar: `.venv/bin/pip install -e '.[dev]'`
- Ejecutar: `.venv/bin/python -m proxlaunch` (o `.venv/bin/proxlaunch`);
  sin pantalla: `QT_QPA_PLATFORM=offscreen`.
- Lint: `.venv/bin/ruff check src tests` (autocorrección: `--fix`).
- Tipos: `.venv/bin/python -m mypy src`
