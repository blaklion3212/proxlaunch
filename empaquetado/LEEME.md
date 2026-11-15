# Empaquetado de ProxLaunch (MVP 5)

Parte común, de Linux y de Windows. La arquitectura está en `docs/arquitectura/mvp5.md`.

## Comandos principales

| Comando | Qué hace |
|---|---|
| `empaquetado/entornos/mv.sh crear ubuntu2204` (o `ubuntu2404`) | Crea la MV QEMU (imagen cloud verificada, SSH solo en 127.0.0.1:2241/2242). |
| `empaquetado/verificar-todo.sh linux [--iconos-provisionales]` | Todo en orden desde un árbol limpio: calidad, build en 22.04, instalación y humo en 22.04 y 24.04, `remove`/`purge`, sello y `SHA256SUMS`. Detiene las MVs al terminar. |
| `empaquetado/verificar-todo.sh windows [--iconos-provisionales]` | Lo mismo en la MV de Windows 11 (ya instalada y preparada): herramientas fijadas, calidad, build del `-setup.exe`, instalación silenciosa, humo con escritorio, desinstalación y residuos, sello y `SHA256SUMS`. |
| `empaquetado/calidad.sh` / `calidad.ps1` | Lockfile con hashes, `ruff`, `mypy`, `pytest -m "not integracion"`, cobertura. |
| `empaquetado/construir-linux.sh [--iconos-provisionales] [--sin-calidad]` | Construye `dist/proxlaunch_<versión>_amd64.deb` (dentro de Ubuntu 22.04). |
| `empaquetado/construir-windows.ps1 [-IconosProvisionales] [-SinCalidad]` | Construye `dist\proxlaunch-<versión>-windows-x64-setup.exe` (dentro de la MV de Windows). |
| `empaquetado/verificar-deb.sh <deb>` / `verificar-windows.ps1` | Verifican el artefacto instalado (dentro de la MV). |
| `empaquetado/entornos/mv.sh destruir-todo` | Limpieza total (RF-E41): QEMU, `swtpm`, estado del TPM, `/tmp/plw-*`, ISO y carpetas de todas las MVs. Solo al cerrar el MVP. |

`mv.sh` también ofrece `arrancar`, `detener`, `ssh`, `copiar`, `traer`, `restaurar` (Ubuntu: vuelve a la instantánea
`limpio`), `instrucciones` (Windows) y `destruir`. Los archivos de las MVs viven en `~/aprovprox-empaquetado/`.

## MV de Windows 11 (una sola vez)

1. Descargue usted la ISO oficial de Windows 11 (se usa la edición Pro sin activar) desde la página de Microsoft, compare su
   SHA-256 con la lista «Verificar la descarga» y déjela en `~/aprovprox-empaquetado/iso/` (espere a que termine de copiarse).
   Opcional: `PROXLAUNCH_ISO` (nombre del archivo) y `PROXLAUNCH_ISO_SHA256` o `iso/ISO.sha256` (suma confirmada; una ISO
   distinta se rechaza).
2. `empaquetado/entornos/mv.sh crear windows11` comprueba la ISO (UDF), registra su SHA-256, la URL oficial y la fecha en
   `iso/ISO-ORIGEN.txt`, crea el disco de 80 GB, el TPM 2.0 (`swtpm`), las variables UEFI con Secure Boot, la clave SSH y la
   contraseña de la cuenta `prueba` (solo en la carpeta de la MV, modo 600), abre la ventana y **imprime los pasos** del
   asistente de Windows (con esa contraseña, para que la teclee) y la orden que se ejecuta desde la unidad `APOYO`.
3. `empaquetado/entornos/mv.sh arrancar windows11` (cuando `preparar.ps1` dijo «LISTO») comprueba SSH, expulsa el DVD y
   deja la MV lista. Después basta `empaquetado/verificar-todo.sh windows`.

Las herramientas de construcción (CPython 3.13.17 e Inno Setup 6.7.4) se descargan en el anfitrión con SHA-256 fijado en
`entornos/windows/herramientas.json` (con el origen de cada suma), se copian por `scp` y `windows/preparar-build.ps1` las
vuelve a verificar (suma y firma Authenticode) antes de instalarlas para el usuario, sin administrador.

## Iconos

Los iconos **aprobados** por el usuario están versionados en `empaquetado/iconos/` (PNG de 16 a 256 px,
`proxlaunch.ico` y `SHA256SUMS`). La construcción (Linux y Windows) no los redibuja: `iconos.py copiar` verifica ese
`SHA256SUMS`, el registro `comun/iconos-aprobados.json` y que el SVG fuente no cambió, y copia los archivos a
`build/iconos/`; `iconos.py verificar` confirma que lo copiado es lo aprobado. `iconos.py generar` (opcional) renderiza una
**propuesta** y su vista previa en `build/iconos-propuesta/`; si el usuario la aprueba, `iconos.py aprobar --desde
build/iconos-propuesta` la instala en `empaquetado/iconos/` y registra las sumas. `--iconos-provisionales` se conserva
solo para construir con iconos sin aprobar (el artefacto queda en `dist/provisional/` y nunca entra en `SHA256SUMS`).

## Instalador de Windows (`windows/proxlaunch.iss`)

Ámbito «solo para mí» por defecto (sin administrador) con diálogo para «todos los usuarios»; asistente en español;
`AppId` fijo; datos del usuario conservados. Al desinstalar se pregunta «¿Borrar también sus datos?» (respuesta
predeterminada «No»); en modo silencioso el parámetro es `unins000.exe /VERYSILENT /BORRARDATOS=1`, que borra solo
`%LOCALAPPDATA%\ProxLaunch\ProxLaunch` del usuario que desinstala (las rutas de `platformdirs` en Windows: sin roaming y con
el nombre de la aplicación también como autor). El llavero nunca se toca. Sin firma: el paso de firma de
`construir-windows.ps1` está desactivado y solo se activa con `PROXLAUNCH_FIRMA_CONFIG` apuntando a un archivo fuera del
repositorio (ver la cabecera del script).

## Lockfiles

`python empaquetado/comun/comprobar_lock.py` comprueba que `empaquetado/requisitos/*.txt` están al día respecto de
`pyproject.toml`; con `--regenerar` los recompila con `uv pip compile --generate-hashes` (CPython 3.13; Linux y Windows).

## Revisión estática

`python empaquetado/comun/revisar_estatico.py` aplica CA-E30.1, E30.2, E33.1, E35.1, E21.3, E23.4 y E24.2 (sin CI activa,
plantilla válida y fijada por SHA, sin trazas del shell ni de PowerShell, sin volcado del entorno, sin certificados ni
secretos), exige BOM UTF-8 en los `.ps1` con acentos (Windows PowerShell 5.1), valida su sintaxis si hay PowerShell
disponible y comprueba las condiciones del `.iss` (CA-E01.4) y de `herramientas.json`. No hay CI activa:
`empaquetado/ci/github-actions.yml.plantilla` es solo una referencia.
