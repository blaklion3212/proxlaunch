# Empaquetado de ProxLaunch: construcción y verificación (para desarrolladores)

Versión: 0.5.0 (MVP 5) · Decisiones: D-27 · Requisitos: `docs/requisitos/mvp5.md` · Arquitectura: `docs/arquitectura/mvp5.md`

Esta guía explica cómo se construyen y se verifican el `.deb` (Ubuntu 22.04 y 24.04) y el instalador de Windows
(`-setup.exe`). Es la vista de conjunto y el orden de las órdenes. El detalle de cada opción, las reglas de los scripts y
la mecánica de la prueba de actualización están en [`empaquetado/LEEME.md`](../empaquetado/LEEME.md); aquí se enlaza y no
se repite. Si buscas instalar la aplicación, lee la [guía de usuario](guia-usuario.md#instalar-y-desinstalar-proxlaunch).

---

## 1. Qué se produce

| Artefacto | Nombre | Se construye en |
|---|---|---|
| Paquete Debian (amd64) | `dist/proxlaunch_<versión>_amd64.deb` | Una MV Ubuntu 22.04 (la glibc del congelado debe ser ≤ 2.35) |
| Instalador de Windows (64 bits) | `dist/proxlaunch-<versión>-windows-x64-setup.exe` | Una MV Windows 11 |
| Sumas | `dist/SHA256SUMS` | El anfitrión, solo tras verificar |

Ambos llevan el intérprete de Python y las bibliotecas dentro (PyInstaller `--onedir`, CPython 3.13): no usan el Python
del sistema. La versión sale de `proxlaunch.__version__` (SemVer `X.Y.Z`); `empaquetado/comun/version.py` la valida.

## 2. Requisitos del anfitrión

Los scripts se ejecutan en el equipo de desarrollo (Ubuntu) y construyen **dentro de máquinas virtuales QEMU**; no hace
falta Docker ni Podman. Hace falta:

- `qemu-system-x86_64`, `qemu-img`, firmware OVMF con Secure Boot (`.ms.fd`) y `swtpm` (para la MV de Windows).
- `/dev/kvm` accesible para tu usuario (`mv.sh` se niega si no se puede leer y escribir).
- `git` y `python3` (los scripts del anfitrión usan `python3 -I`), `sha256sum`, `ssh` y `scp`.
- Espacio en disco y memoria para **una MV a la vez**: unos 6 GB de RAM para Windows y 4 GB para Ubuntu, y 80 GB de
  disco virtual para Windows (20 GB por MV Ubuntu).
- No ejecutar como root: `verificar-todo.sh` y `mv.sh destruir-todo` se niegan.
- Para la MV de Windows: la **ISO oficial de Windows 11** la descarga usted (no se descarga automáticamente) y la deja en
  `~/aprovprox-empaquetado/iso/`.

Todos los archivos de las MVs viven en `~/aprovprox-empaquetado/`, fuera del repositorio.

### Exclusión con el laboratorio de Proxmox

Las MVs de empaquetado y el laboratorio Proxmox no deben estar activos a la vez. `mv.sh crear|arrancar` y
`verificar-todo.sh` se niegan si algo escucha en `127.0.0.1:8006` o `:2222`, o si hay un proceso cuya orden contenga
`aprovprox-lab` (solo lee el estado; `empaquetado/comun/exclusion-laboratorio.sh`). **La comprobación inversa (que el
laboratorio rechace arrancar con MVs de empaquetado) no está implementada**: apaga el laboratorio antes de empaquetar y
las MVs antes de volver a él.

## 3. Orden de las órdenes

Todas se escriben desde la raíz del repositorio, con el árbol limpio y confirmado (`verificar-todo.sh` envía a la MV el
árbol de `HEAD` más el parche del árbol de trabajo; sin `.venv` ni `secretos/`).

1. **Crear las MVs (una vez).**

   ```bash
   empaquetado/entornos/mv.sh crear ubuntu2204
   empaquetado/entornos/mv.sh crear ubuntu2404
   empaquetado/entornos/mv.sh crear windows11
   ```

   - Ubuntu: imagen cloud oficial verificada con su `SHA256SUMS` (y la firma si el llavero de Ubuntu está instalado), disco
     qcow2 en capa y una instantánea `limpio` al final. `mv.sh restaurar` vuelve a ella.
   - Windows: antes de la orden, pon la ISO en `~/aprovprox-empaquetado/iso/`. `crear windows11` la comprueba, registra su
     SHA-256, la URL oficial y la fecha en `iso/ISO-ORIGEN.txt`, abre la ventana e **imprime los pasos del asistente de
     Windows** (los haces tú: cuenta local `prueba`, sin enviar datos en tu nombre) y la orden que se ejecuta desde la
     unidad `APOYO` (`preparar.ps1`: SSH, clave, inicio de sesión automático, red privada, comprobación de TPM 2.0 y
     Secure Boot). Después, `mv.sh arrancar windows11` comprueba SSH y deja la MV lista. Detalle en el apartado «MV de
     Windows 11 (una sola vez)» de `LEEME.md`.

2. **Verificar y construir.** Cada orden construye, instala el artefacto en la MV, lo prueba y, solo si todo fue bien,
   lo sella y lo suma:

   ```bash
   empaquetado/verificar-todo.sh linux
   empaquetado/verificar-todo.sh windows
   ```

   `linux` construye el `.deb` en 22.04 y lo verifica en 22.04 y 24.04, ambas desde su instantánea limpia. `windows`
   descarga en el anfitrión las herramientas fijadas (CPython 3.13 e Inno Setup 6, con SHA-256), las envía a la MV y
   construye y verifica allí el instalador. Las MVs se **detienen** siempre al terminar.

3. **Probar la actualización** (exige que el paso 2 correspondiente ya haya sellado el artefacto vigente):

   ```bash
   empaquetado/verificar-todo.sh actualizacion-linux
   empaquetado/verificar-todo.sh actualizacion-windows
   ```

   Usa una build de prueba con la versión siguiente (`--version-prueba X.Y.Z` para fijarla) que no se publica. Ver
   «Prueba de actualización» en `LEEME.md`.

4. **Limpieza total, solo al cerrar el MVP.**

   ```bash
   empaquetado/entornos/mv.sh destruir-todo
   ```

   Mata QEMU y `swtpm` del usuario, borra `~/aprovprox-empaquetado/` entera (ISO, discos, TPM, claves) y los temporales
   `/tmp/plw-*`, y deja un registro en `build/registros/limpieza-<fecha>.txt`. Después de esto hay que volver a crear
   las MVs para verificar de nuevo.

Opciones sueltas (por ejemplo `calidad.sh`, `construir-linux.sh`, `verificar-deb.sh`) y `--iconos-provisionales` están en
la tabla de «Comandos principales» de `LEEME.md`. Los registros de cada ejecución quedan en `build/registros/` (ignorado
por git).

## 4. Qué garantiza cada paso

| Paso | Qué comprueba |
|---|---|
| Versión | `X.Y.Z` válida y coherente con la etiqueta `v<versión>` si `HEAD` está etiquetado. |
| Calidad (`calidad.sh` / `calidad.ps1`) | Lockfiles con hashes al día respecto de `pyproject.toml`, `ruff`, `mypy`, `pytest -m "not integracion"` con cobertura, revisión estática (`revisar_estatico.py`). Se niega a correr con `PROXLAUNCH_LAB` definido. |
| Construcción | Entorno desde lockfile (`--require-hashes`), `.qm` compilados, iconos aprobados (suma y SVG fuente), avisos de terceros, PyInstaller, comprobaciones del congelado, humo previo y presupuesto de tamaño (90 MB comprimido, 250 MB instalado, tolerancia 10 %). Nada se escribe en `dist/` si un paso falla. |
| Verificación del `.deb` (`verificar-deb.sh`) | Metadatos, instalación con `apt`, `--version` sin Python, prueba de humo con pantalla virtual y **sin red**, humo con servicio de secretos, `apt remove` y `apt purge` sin residuos y con `$HOME` intacto, `desktop-file-validate`. |
| Verificación de Windows (`verificar-windows.ps1`) | Instalación silenciosa por usuario, `--version`, humo con escritorio en tarea interactiva y salida bloqueada por cortafuegos, llavero real de Windows, desinstalación sin residuos con datos intactos, reinstalación (una sola entrada), `/BORRARDATOS=1` solo en ese usuario con el llavero intacto, y modo «para todos» que ignora `/BORRARDATOS=1`. Solo corre en la MV marcada por `preparar.ps1`. |
| Actualización | Versión nueva instalada, una sola entrada, datos de usuario idénticos (SHA-256) y humo correcto. |
| Contraseña de la MV | Al terminar, ningún registro de `build/registros/` contiene la contraseña de la cuenta de prueba (se excluye `crear-windows11.txt`, que se conserva por decisión del usuario). |

La **prueba de humo** (`proxlaunch --prueba-de-humo`) abre la aplicación con carpetas temporales, comprueba icono,
fuentes, traductor, recursos y backend del llavero (sin leer ni escribir secretos), muestra la ventana un instante y
devuelve **una línea JSON**. Un vigilante la aborta a los 15 s. `--permitir-sin-llavero` acepta un entorno sin
servicio de secretos.

### INV-E6: solo se suma lo que pasó el humo

Los scripts de construcción **no** escriben `SHA256SUMS`. Lo hace `empaquetado/comun/sumas.py` en el anfitrión:

1. `sellar <artefacto>` escribe `dist/.verificado-<artefacto>` con la suma, solo después de que la verificación
   instalada terminó con éxito.
2. `publicar` reescribe `SHA256SUMS` con los artefactos de la versión vigente cuyo sello coincide con la suma actual. Un
   artefacto sin sello vigente no se publica; uno de otra versión se omite con un aviso.
3. `comprobar` equivale a `sha256sum -c`.

Los artefactos provisionales (`dist/provisional/`, de `--iconos-provisionales` o `--sin-calidad`) y los de la prueba de
actualización nunca se sellan ni entran. Antes de construir se borran el artefacto de la misma versión y sus sellos, y
los archivos traídos de una MV llegan con nombre temporal y solo se renombran si su SHA-256 coincide con el calculado en
la MV: un fallo a medias no puede dejar un artefacto viejo con aspecto de nuevo.

## 5. Cadena de suministro

- **Versiones fijadas con hashes:** `empaquetado/requisitos/*.in` se compilan a `linux-*.txt` y `windows-*.txt` con
  `uv pip compile --generate-hashes` (CPython 3.13) y se instalan con `--require-hashes --no-deps`.
  `python empaquetado/comun/comprobar_lock.py` falla si `pyproject.toml` cambió sin regenerar (`--regenerar` los
  recompila).
- **Herramientas con suma fijada:** `uv` en Linux (`linux/herramientas.sh`); CPython e Inno Setup en Windows
  (`entornos/windows/herramientas.json`, que `windows/preparar-build.ps1` vuelve a verificar, incluida la firma
  Authenticode). Sin `curl | sh`.
- **ISO y imágenes:** la ISO de Windows la aporta el usuario y su suma queda registrada; las imágenes de Ubuntu se
  verifican con `SHA256SUMS`.
- **Avisos de terceros:** `THIRD-PARTY-NOTICES.txt` se genera de los metadatos de los paquetes del lockfile de ejecución
  (PySide6/Qt bajo LGPL-3.0, fuentes OFL, intérprete PSF).
- **Compilación repetible:** `SOURCE_DATE_EPOCH` (el del último commit) fija las fechas de los archivos.
- **Seguridad de los scripts:** `revisar_estatico.py` rechaza trazas del shell o de PowerShell, volcados del entorno,
  certificados o secretos. Las MVs no tienen credenciales de Proxmox y usan red de usuario de QEMU con reenvíos solo en
  `127.0.0.1` (SSH: 2241 = 22.04, 2242 = 24.04, 2243 = Windows).

## 6. Firma de código (desactivada)

Los instaladores salen **sin firma** (D-27). El paso existe en `construir-windows.ps1` y solo se activa si defines
`PROXLAUNCH_FIRMA_CONFIG` con la ruta de un archivo JSON **fuera del repositorio** con:

| Campo | Contenido |
|---|---|
| `certificado` | Ruta al archivo del certificado (también fuera del repositorio). |
| `variable_contrasena` | Nombre de la variable de entorno que contiene su contraseña (se borra en cuanto se lee). |
| `url_marca_de_tiempo` | Servidor de sello de tiempo `http(s)://…`; es obligatorio, porque sin él la firma deja de valer al caducar el certificado. |

El certificado se carga solo en memoria. Si la firma no queda válida, la construcción falla. Sin la variable, el script
lo anuncia («Firma Authenticode OMITIDA») y sigue. Nunca guardes certificados ni contraseñas en el repositorio.

Nota: tras activar la firma, la suma del instalador cambia; vuelve a verificar y sellar con `verificar-todo.sh windows`.

## 7. CI en GitHub Actions (activa)

La CI vive en [`.github/workflows/empaquetado.yml`](../.github/workflows/empaquetado.yml), que es la única fuente de
verdad (la antigua plantilla `empaquetado/ci/github-actions.yml.plantilla` se retiró; el historial de la decisión P-E01
está en `decisiones.md`). Solo llama a los scripts de `empaquetado/`, usa acciones fijadas por SHA de commit,
`permissions: contents: read`, `persist-credentials: false`, no usa secretos y no publica nada.

**Disparadores (decisión del usuario: repo privado y cupo de minutos).** Solo al subir una etiqueta `v*` y a mano
(`workflow_dispatch`). No se dispara por push a ramas ni por pull request. Para lanzarla a mano:

```bash
gh workflow run empaquetado.yml --ref main      # --ref puede ser una rama o una etiqueta
gh run list --workflow empaquetado.yml          # estado
gh run watch                                    # seguir la última en vivo
gh run download <id> -n registros-windows-windows-2022   # bajar los registros de una ejecución
```

**Trabajos.**

| Trabajo | Ejecutor | Qué hace |
|---|---|---|
| `construir-linux` | `ubuntu-22.04` | `preparar-build.sh`, `construir-linux.sh` (incluye la calidad completa y el límite de glibc 2.35, por eso se construye solo en 22.04). |
| `verificar-linux` | `ubuntu-22.04` y `ubuntu-24.04` | Recibe el `.deb` y ejecuta `preparar-build.sh` y `verificar-deb.sh` (instalación, humo con xvfb y sin red, `remove`/`purge`). |
| `windows` | `windows-2022` | Descarga CPython e Inno Setup con `descargar-herramientas.py` (SHA-256 fijado en `herramientas.json`), `windows/preparar-build.ps1` (vuelve a comprobar suma y firma), `construir-windows.ps1` (incluye calidad) y `verificar-windows.ps1 -PermitirFueraDeLaMV`, todo con Windows PowerShell 5.1 como en la MV. |

**Artefactos.** Solo registros de build (`build/registros/`, con `$HOME` sustituido por `~`) con retención de 7 días,
subidos aunque el trabajo falle. Los instaladores finales (`-setup.exe`) nunca se suben. Único caso especial: el `.deb`
viaja entre `construir-linux` y `verificar-linux` como artefacto intermedio de 1 día (no hay otra forma de verificarlo
en 24.04 con un `.deb` construido en 22.04). No se escribe `SHA256SUMS` ni se sella nada: eso sigue siendo local
(`verificar-todo.sh`).

**Diferencias con la verificación local (y límites).**

- Las MVs locales parten de una instantánea limpia y verifican el `.deb` en una máquina sin las bibliotecas de
  construcción; en el ejecutor se usa la imagen alojada más `preparar-build.sh`, así que es una comprobación algo más
  permisiva. La referencia oficial para sellar sigue siendo `verificar-todo.sh`.
- Los ejecutores de Windows son Windows Server (no un escritorio Windows 10/11). `windows-2022` sí ofrece la sesión
  interactiva (`explorer.exe`) que `verificar-windows.ps1` necesita para el humo con escritorio: la verificación completa
  pasa allí (comprobado el 2026-11-16). `-PermitirFueraDeLaMV` omite solo el marcador de la MV; el resto de guardas se
  mantiene.
- La CI no cubre la actualización (`actualizacion-*`) ni la firma Authenticode.

**Coste en minutos (medido en la primera ejecución correcta, run 43806325999).** Con repo privado los minutos salen del
cupo del plan, y los de Windows cuentan x2. `construir-linux` ~10 min, cada `verificar-linux` ~3-5 min, `windows` ~10
min: unos 16 min reales (los trabajos van en paralelo) y unos 40 min facturables. El plan Free de GitHub incluye 2000 min
al mes (unas 50 ejecuciones). Por eso solo se dispara con etiquetas y a mano; la concurrencia
cancela la ejecución anterior de la misma referencia.

**Mantenimiento.** Las acciones están fijadas por SHA de commit con la versión en un comentario
(`actions/checkout` v7.0.1, `actions/upload-artifact` v7.0.2, `actions/download-artifact` v8.0.2). Para actualizarlas,
comprueba el SHA con `gh api repos/actions/<acción>/git/ref/tags/<versión>` y no uses etiquetas móviles.
`revisar_estatico.py` (parte de la calidad) rechaza cualquier otro archivo de CI, disparadores distintos de etiquetas
`v*` y `workflow_dispatch`, acciones sin SHA, secretos y permisos de escritura.

## 8. Resultados de referencia (versión 0.5.0)

Verificados al cerrar el MVP 5 (ver la entrada 18 de la [bitácora](bitacora.md)): suite local con 7790 pruebas correctas;
`verificar-todo.sh linux`, `windows`, `actualizacion-linux` y `actualizacion-windows` correctos; `dist/SHA256SUMS` con el
`.deb` (`8bb854ef…`) y el `-setup.exe` (`d255fc86…`). Comprobaciones visuales manuales hechas con el usuario
(asistente en español, SmartScreen, escalado 125/150/175 %, icono del menú Inicio); ver la bitácora.

## 9. Pendientes conocidos

- RF-E21b (auditoría de CVE, «Debería»): no implementada.
- Exclusión inversa con el laboratorio: no implementada.
- La semilla de cloud-init por disco vvfat no se probó en una MV nueva (las de Ubuntu ya existían).
- `AppMutex=ProxLaunch.InstanciaUnica` figura en el `.iss` pero la aplicación no crea ese mutex; la detección de la
  aplicación abierta la hace `CloseApplications=yes`.
