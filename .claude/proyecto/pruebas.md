# Pruebas de ESTE proyecto

## Herramientas
- pytest con pytest-qt (`qt_api = "pyside6"`), `responses` para simular HTTP,
  pytest-socket para bloquear la red (solo se permiten unix sockets).

## Comandos
- Toda la suite: `.venv/bin/python -m pytest`
- Un archivo: `.venv/bin/python -m pytest tests/test_humo.py`
- Un caso: `.venv/bin/python -m pytest tests/test_humo.py::test_paquete_importa_y_tiene_version`
- Interfaz sin pantalla: anteponer `QT_QPA_PLATFORM=offscreen`.
- Integración con el laboratorio: `PROXLAUNCH_LAB=1 .venv/bin/python -m pytest -m integracion`
  (sin esa variable se saltan; además requieren permitir sockets, p. ej. `--force-enable-socket`).

## Tipos y ubicación
- Unitarias del núcleo: `tests/nucleo/`; de la interfaz: `tests/interfaz/`.
- Integración (laboratorio real, marcador `integracion`): `tests/integracion/`.
- Respuestas capturadas y anonimizadas: `tests/datos/respuestas/{8.0,9.2}/`.
- Pruebas de humo transversales en `tests/` (importación y núcleo sin PySide6).

## Cobertura mínima
- Núcleo (`src/proxlaunch/nucleo`): **85 %** de líneas como mínimo.
- Global (núcleo + interfaz): **75 %** como mínimo.
- Las funciones puras (`validacion`, `constructor_peticion`, `capacidades`) deben cubrir
  todos los criterios de aceptación y todas las reglas V-xx (cerca del 100 %).
- Medición: `.venv/bin/python -m pytest --cov=proxlaunch --cov-report=term-missing`
  (núcleo: `--cov=proxlaunch.nucleo --cov-fail-under=85`).
