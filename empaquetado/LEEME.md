# Empaquetado de ProxLaunch (MVP 5)

Parte común y de Linux. La de Windows (`windows/`, `entornos/windows/`, `*.ps1`) la aporta otra fase.
La arquitectura está en `docs/arquitectura/mvp5.md`.

## Comandos principales (Linux)

| Comando | Qué hace |
|---|---|
| `empaquetado/entornos/mv.sh crear ubuntu2204` (o `ubuntu2404`) | Crea la MV QEMU (imagen cloud verificada, SSH solo en 127.0.0.1:2241/2242). |
| `empaquetado/verificar-todo.sh linux [--iconos-provisionales]` | Todo en orden desde un árbol limpio: calidad, build en 22.04, instalación y humo en 22.04 y 24.04, `remove`/`purge`, sello y `SHA256SUMS`. Detiene las MVs al terminar. |
| `empaquetado/calidad.sh` | Lockfile con hashes, `ruff`, `mypy`, `pytest -m "not integracion"`, cobertura. |
| `empaquetado/construir-linux.sh [--iconos-provisionales] [--sin-calidad]` | Construye `dist/proxlaunch_<versión>_amd64.deb` (dentro de Ubuntu 22.04). |
| `empaquetado/verificar-deb.sh <deb>` | Verifica el `.deb` instalado (dentro de Ubuntu 22.04 o 24.04, con sudo sin contraseña). |
| `empaquetado/entornos/mv.sh destruir-todo` | Limpieza total (RF-E41). Solo al cerrar el MVP. |

`mv.sh` también ofrece `arrancar`, `detener`, `ssh`, `copiar`, `traer`, `restaurar` (vuelve a la instantánea
`limpio`) y `destruir`. Los archivos de las MVs viven en `~/aprovprox-empaquetado/`.

## Iconos

`python empaquetado/comun/iconos.py generar` deja los PNG, el `.ico` y `build/iconos/vista-previa.png`. Hasta que el usuario
apruebe la vista previa, `empaquetado/comun/iconos-aprobados.json` está en estado `pendiente` y los builds solo pueden usar
`--iconos-provisionales`: el artefacto queda en `dist/provisional/` y nunca entra en `SHA256SUMS`. Tras la aprobación:
`python empaquetado/comun/iconos.py aprobar` registra las sumas (se hace una vez, con la vista previa ya aprobada).

## Lockfiles

`python empaquetado/comun/comprobar_lock.py` comprueba que `empaquetado/requisitos/*.txt` están al día respecto de
`pyproject.toml`; con `--regenerar` los recompila con `uv pip compile --generate-hashes` (CPython 3.13; Linux y Windows).

## Revisión estática

`python empaquetado/comun/revisar_estatico.py` aplica CA-E30.1, E30.2, E33.1, E35.1, E21.3, E23.4 y E24.2 (sin CI activa, plantilla
válida y fijada por SHA, sin trazas del shell ni volcado del entorno, sin certificados ni secretos). No hay CI activa:
`empaquetado/ci/github-actions.yml.plantilla` es solo una referencia.
