# Arquitectura del MVP 5 — ProxLaunch (instaladores, scripts de empaquetado y entornos de prueba)

Versión: 0.1 (2026-11-14) · Autor: orquestador · Requisitos: `docs/requisitos/mvp5.md` (v1.1, **R5**) · Decisiones: D-27.

Regla de lectura: los IDs RF-E/CA-E/HV-E/DT-E son los de R5. Lo que depende de un dato externo sigue siendo
hipótesis (HV) hasta que el responsable de la fase lo verifique; cada fase devuelve en su reporte qué HV confirmó o
refutó, y este documento se corrige en su Anexo B.

---

## 1. Hechos del equipo de desarrollo (verificados por el orquestador)

| # | Hecho | Consecuencia |
|---|---|---|
| A1 | Anfitrión Ubuntu **26.04** (glibc más nueva que la de 22.04). | El `.deb` **no** se construye en el anfitrión: se construye dentro de una MV Ubuntu 22.04 (CA-E05.1, glibc ≤ 2.35). |
| A2 | No hay Docker ni Podman; sí `qemu-system-x86_64`, `qemu-img`, OVMF (`OVMF_CODE_4M.ms.fd`, `OVMF_VARS_4M.ms.fd`), `swtpm` 0.10.1, `/dev/kvm` accesible (grupo `kvm` añadido temporalmente para el laboratorio). | DT-E15 se resuelve con **MVs QEMU** para Ubuntu 22.04/24.04, no contenedores. |
| A3 | `uv` en `~/.local/bin`, con CPython 3.12.16 y 3.13.18 gestionados. `lrelease` y `lupdate` vienen en la rueda de PySide6 del `.venv` (HV-E2 confirmada). | Lockfiles con `uv pip compile`; `.qm` con el `lrelease` de PySide6. |
| A4 | No hay `genisoimage`/`xorriso`. | La semilla de cloud-init se sirve por HTTP (NoCloud por `-smbios`), sin imagen ISO. |
| A5 | 16 GB de RAM libres, 295 GB de disco, 24 núcleos. | Una MV a la vez como norma: Windows 6 GB, Ubuntu 4 GB. |
| A6 | `main()` no acepta argumentos; `cargar_traductor` degrada en silencio; `crear_icono()` arma el icono desde SVG; `Rutas(base)` redirige todo. | Cambios mínimos de §3. |

## 2. Decisiones de arquitectura (complementan DT-E1..DT-E15)

- **AR-1 Python del congelado: CPython 3.13** (la serie más reciente con PyInstaller maduro; PySide6 publica ruedas
  `abi3`, HV-E1 a verificar con `pip download --only-binary=:all:`). Linux: CPython de `uv` (python-build-standalone,
  con `libpython` compartida) dentro de la MV 22.04; si PyInstaller lo rechaza, alternativa **deadsnakes** (`apt`,
  firmado). Windows: instalador oficial de python.org con SHA-256 fijado.
- **AR-2 PyInstaller `--onedir` con un `.spec` versionado** (`empaquetado/proxlaunch.spec`): `collect_data_files`
  sobre `proxlaunch` (solo lo de `package-data` + `.qm`), `copy_metadata` de `keyring` y sus backends (HV-E5),
  `excludes` de los módulos Qt no usados (H3), sin `tests`, sin `.ts`, `upx=False`, `console=False` en Windows
  (con `--version` escribiendo por la consola adjunta si existe; ver §3.3).
- **AR-3 Lockfiles por plataforma** en `empaquetado/requisitos/`: `ejecucion.in` (de `pyproject.toml`),
  `construccion.in` (PyInstaller y su hook-contrib), `calidad.in` (extra `dev`), compilados con
  `uv pip compile --generate-hashes --python-version 3.13 --python-platform {x86_64-manylinux_2_35|x86_64-pc-windows-msvc}`
  → `linux-*.txt` y `windows-*.txt`. Se instala siempre con `pip install --require-hashes --no-deps`.
  `comprobar_lock.py` falla si `pyproject.toml` cambió sin regenerar (CA-E21.2: guarda el hash de las entradas en
  la cabecera del lockfile).
- **AR-4 Versión única** (DT-E6): `proxlaunch.__version__ = "0.5.0"`, `pyproject.toml` con
  `dynamic = ["version"]`. Los scripts la leen con `empaquetado/comun/version.py` (sin importar Qt), que valida SemVer
  `X.Y.Z` (CA-E10.3) y la compara con la etiqueta `v<versión>` si `HEAD` está etiquetado (CA-E10.1).
- **AR-5 Iconos** (DT-E9, CA-E11.4): `empaquetado/comun/iconos.py` renderiza
  `src/proxlaunch/recursos/marca/proxlaunch-icono-sin-texto.svg` (el mismo SVG que ya usa la ventana, sin texto) con
  `QSvgRenderer` en modo offscreen a PNG 16–256 px, y escribe el `.ico` con entradas PNG (formato ICO trivial, sin
  dependencias). Salida en `build/iconos/` (no versionada) **y** una hoja de vista previa
  `build/iconos/vista-previa.png` (todos los tamaños sobre fondo claro y oscuro junto al original). **No se integran
  en ningún artefacto hasta que el usuario apruebe la vista previa**; la aprobación se registra fijando la suma
  SHA-256 del SVG fuente y de los PNG en `empaquetado/comun/iconos-aprobados.json`; el build falla si no coinciden.
- **AR-6 Avisos de terceros** (RF-E23): `empaquetado/comun/avisos.py` genera `THIRD-PARTY-NOTICES.txt` desde
  `importlib.metadata` del entorno de build (solo los paquetes del lockfile de ejecución; falla si alguno no trae
  texto de licencia y no está en una lista de excepciones con su texto oficial versionado), más Qt/PySide6 (LGPL-3.0,
  con el texto de la rueda), las OFL y el intérprete (PSF).
- **AR-7 Presupuesto de tamaño** en `empaquetado/comun/presupuesto.toml` (90 MB / 250 MB, tolerancia 10 %).
- **AR-8 Sumas**: `empaquetado/comun/sumas.py` añade a `dist/SHA256SUMS` solo artefactos cuya verificación
  instalada (§5) terminó con éxito y dejó un sello `dist/.verificado-<artefacto>` con la suma; si la suma actual no
  coincide con el sello, no escribe (INV-E6, CA-E18.2).
- **AR-9 Entornos de prueba = MVs QEMU** bajo `~/aprovprox-empaquetado/` (fuera del repo), con un único script
  `empaquetado/entornos/mv.sh {crear|arrancar|ssh|copiar|detener|destruir|estado} <ubuntu2204|ubuntu2404|windows11>`
  y `destruir-todo` (RF-E41, idempotente, CL-E20). Red de usuario de QEMU, reenvío solo `127.0.0.1` (SSH:
  2241 = 22.04, 2242 = 24.04, 2243 = Windows). Claves SSH ed25519 generadas por MV dentro de su carpeta.
- **AR-10 Sin CI activa**: `empaquetado/ci/github-actions.yml.plantilla` solo llama a `empaquetado/*.sh|*.ps1`, con
  acciones fijadas por SHA de commit y `permissions: contents: read`.

## 3. Cambios en la app (únicos cambios de `src/`, INV-E5)

### 3.1 Versión
`src/proxlaunch/__init__.py`: `__version__ = "0.5.0"`. `pyproject.toml`: quitar `version`, añadir
`dynamic = ["version"]` y `[tool.setuptools.dynamic] version = {attr = "proxlaunch.__version__"}`.

### 3.2 Argumentos (`interfaz/app.py`)
`main(argv: Sequence[str] | None = None) -> int`. Analiza con `argparse.ArgumentParser(add_help=True,
prog="proxlaunch")` y `parse_known_args` (los argumentos de Qt pasan a `QApplication`):
- `--version` → imprime `ProxLaunch 0.5.0` y devuelve 0 **sin importar** `QApplication` (el import de Qt de
  `app.py` se mantiene, pero no se instancia nada).
- `--prueba-de-humo` → `return ejecutar_prueba_de_humo(argv_qt, permitir_sin_llavero=…)` (§3.3).
- `--permitir-sin-llavero` (solo con el anterior): acepta backend `fail`/`null` (CA-E09.3).
- Sin opciones → comportamiento actual idéntico (CA-E17.5), más `app.setDesktopFileName("proxlaunch")` (HV-E11;
  no cambia nada visible en Windows ni en X11).
`__main__.py` sigue llamando a `main()`.

### 3.3 Módulo nuevo `interfaz/humo.py`
> **Cambió en la implementación:** el vigilante es de 15 s (no 5 s) y tiene respaldo de `faulthandler`; ver Anexo B, B-2.

```
@dataclass(frozen=True)
class InformeHumo:
    version: str; plataforma_qt: str; fuentes: tuple[str, str]; traductor: bool
    icono_ok: bool; recursos_faltantes: tuple[str, ...]; backend_llavero: str
    ventana_mostrada: bool; problemas: tuple[str, ...]
def recursos_esperados() -> tuple[str, ...]      # rutas relativas en proxlaunch.recursos + tema
def ejecutar_prueba_de_humo(argv_qt: list[str], *, permitir_sin_llavero: bool = False,
                            espera_ms: int = 1500) -> int
```
Flujo: carpeta temporal (`tempfile.mkdtemp(prefix="proxlaunch-humo-")`) → `Rutas(base)` → `configurar_registro` allí →
`QApplication` → icono (falla si `isNull()` o algún tamaño vacío: plugin SVG) → fuentes (falla si
`cargar_fuentes()` no devuelve las familias incluidas) → traductor (**obligatorio**: falla si `cargar_traductor`
devuelve `None`) → recursos de `recursos_esperados()` (falla nombrando los que falten) → tema → backend del llavero:
**solo** `type(keyring.get_keyring())` con su módulo y nombre, sin leer ni escribir (falla si es `fail`/`null` y no se
permitió) → `crear_dependencias(rutas_temporales, gestor)` y `VentanaPrincipal(...).show()` → `QTimer.singleShot(espera_ms,
app.quit)` y un vigilante a 5 s que fuerza salida ≠ 0 → borra la carpeta temporal → imprime **una línea JSON** con el
`InformeHumo` en `stdout` y los problemas en `stderr`; devuelve 0 solo si `problemas` está vacío.
Garantías: no crea transporte HTTP (solo se crea al conectar), no toca las carpetas reales ni secretos.
En Windows (`console=False`) `stdout` no existe: si `sys.stdout is None`, el informe se escribe además en el archivo
indicado por la variable `PROXLAUNCH_HUMO_SALIDA` (la usa `verificar.ps1`); `--version` hace lo mismo.
En el árbol de fuentes el `.qm` debe compilarse antes (`empaquetado/comun/compilar_qm.py`), así CA-E17.3 usa la misma
regla estricta que el artefacto.

### 3.4 Pruebas (las escribe el `probador`)
Modo normal sin cambios (suite existente), `--version`, humo con dobles (recurso faltante, `.qm` ausente, backend
`fail`, icono nulo, vigilante), constantes estables `SERVICIO = "ProxLaunch"` y nombre `ProxLaunch` de
`platformdirs` (CA-E14.4), y `empaquetado/comun/*.py` (versión, sumas, iconos, avisos, comprobar_lock).

## 4. Estructura de `empaquetado/`

```
empaquetado/
  calidad.sh | calidad.ps1           RF-E32/E33 (guarda: PROXLAUNCH_LAB prohibido; -m "not integracion")
  construir-linux.sh                 dentro de la MV 22.04: lock → qm → iconos aprobados → avisos → PyInstaller → .deb
  construir-windows.ps1              dentro de la MV Windows: ídem → Inno Setup → -setup.exe (paso de firma desactivado)
  verificar-deb.sh                   dentro de 22.04 y 24.04: instalar → --version → humo (xvfb + unshare -n; offscreen)
                                     → apt remove/purge → comprobar residuos (RF-E13/E18)
  verificar-windows.ps1              dentro de Windows: instalar silencioso → --version → humo (tarea interactiva,
                                     salida bloqueada por cortafuegos) → desinstalar → residuos
  verificar-todo.sh                  en el anfitrión: orquesta MVs, copia el árbol limpio (git archive), recoge dist/
  proxlaunch.spec
  requisitos/*.in, linux-*.txt, windows-*.txt
  comun/ version.py compilar_qm.py iconos.py iconos-aprobados.json avisos.py sumas.py presupuesto.toml
         comprobar_lock.py revisar_estatico.py (CA-E30.1/E30.2/E33.1/E35.1/E21.3/E24.2)
  linux/ control.in proxlaunch.desktop copyright.in postinst postrm (solo triggers; nunca tocan $HOME)
  windows/ proxlaunch.iss (es.isl, PrivilegesRequiredOverridesAllowed=dialog, casilla «Borrar también mis datos»,
           MinVersion=10.0, ArchitecturesAllowed=x64compatible, AppId fijo, AppMutex para detectar la app abierta)
  entornos/ mv.sh semilla-ubuntu/ (user-data plantilla) windows/ (preparar.ps1, ver §6)
  ci/github-actions.yml.plantilla
```
El código se pasa a las MVs con `git archive HEAD` + parche del árbol de trabajo (sin `.venv`, sin `secretos/`);
`dist/` y registros vuelven por `scp`. Los registros de los scripts se guardan en `build/registros/` (ignorado).

## 5. Flujo de verificación (INV-E6)

`verificar-todo.sh linux` = arrancar 22.04 → copiar árbol → `calidad.sh` → `construir-linux.sh` → `verificar-deb.sh`
en 22.04 → copiar `.deb` a 24.04 → `verificar-deb.sh` → sello y `sumas.py` en el anfitrión → detener MVs.
`verificar-todo.sh windows` = ídem en la MV Windows con los `.ps1`. La calidad del anfitrión (3.14) sigue siendo la
de siempre; las MVs añaden 3.13 (Linux y Windows) y 3.11 en 22.04 (mínimo declarado, `uv python`).

## 6. Entornos de prueba

### 6.1 Ubuntu 22.04 y 24.04 (`mv.sh crear ubuntu2204|ubuntu2404`)
> **Cambió en la implementación:** la semilla de cloud-init es un disco vvfat NoCloud, no un servidor HTTP; ver Anexo B, B-1.

Imagen cloud oficial (`cloud-images.ubuntu.com/releases/<código>/release/…-server-cloudimg-amd64.img`) verificada
con su `SHA256SUMS` y la firma `SHA256SUMS.gpg` contra `/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg` si existe
(si no, se registra que solo se verificó la suma). Disco qcow2 en capa sobre la imagen (20 GB), cloud-init NoCloud
servido por un `http.server` efímero en `127.0.0.1` (`-smbios type=1,serial=ds=nocloud;s=http://10.0.2.2:<puerto>/`),
usuario `prueba` con la clave pública de la MV, paquetes `xvfb dbus-x11 gnome-keyring desktop-file-utils` para la
verificación. Root solo dentro de la MV.

### 6.2 Windows 11 de evaluación (`mv.sh crear windows11`)
> **Cambió en la implementación:** se usó la ISO de consumo (Pro sin activar), no la de evaluación; ver Anexo B, B-3.

- **ISO**: la descarga **el usuario** desde el sitio oficial de evaluación de Microsoft (el formulario pide datos de
  contacto, que no enviamos en su nombre) y la deja en `~/aprovprox-empaquetado/iso/`. El script calcula y registra
  su SHA-256 junto con la URL oficial y la fecha (RF-E42, HV-E16) y se niega a seguir si el archivo no es una ISO UDF
  de Windows.
- **Máquina**: `-machine q35,accel=kvm -cpu host -smp 4 -m 6144`, OVMF `.ms.fd` (copia propia de `OVMF_VARS`),
  `swtpm socket --tpm2` con estado en la carpeta de la MV y socket en `mktemp -d /tmp/plw-XXXX` (S-E8, comprobado
  < 108 caracteres antes de arrancar), disco SATA/AHCI 80 GB qcow2 (sin controladores externos), red `e1000e` de
  usuario con `hostfwd=tcp:127.0.0.1:2243-:22`, ventana GTK en el escritorio del usuario.
- **Instalación (persona, CA-E42.3)**: el usuario recorre el asistente de Windows en la ventana, acepta la licencia de
  evaluación y crea la cuenta local `prueba`. Después ejecuta **una** orden desde la unidad de apoyo (disco FAT de solo
  lectura, `-drive file=fat:ro:<carpeta>`) que lanza `preparar.ps1`: instala OpenSSH Server (capacidad de Windows),
  autoriza la clave pública de la MV, configura inicio de sesión automático de `prueba` (necesario para el humo con
  escritorio) y comprueba TPM 2.0 y Secure Boot (`Get-Tpm`, `Confirm-SecureBootUEFI`, M-E10). Todo lo demás es por SSH.
- **Herramientas en la MV**: Python 3.13 (python.org) e Inno Setup 6 descargados **por el anfitrión** con SHA-256
  fijado en `empaquetado/entornos/windows/herramientas.json` y copiados por `scp`; instalación silenciosa.
- **Humo con escritorio**: `verificar-windows.ps1` registra una tarea programada interactiva para `prueba`, con una
  regla de cortafuegos de salida que bloquea el `.exe` instalado mientras dura (RNF-E03, CA-E17.1), y espera el
  archivo de `PROXLAUNCH_HUMO_SALIDA`.

### 6.3 Limpieza (`mv.sh destruir-todo`, RF-E41)
Mata QEMU/`swtpm`/`http.server` por PID **y** por patrón de línea de órdenes; borra `~/aprovprox-empaquetado/`
entero, los `/tmp/plw-*`, y comprueba `ps`, `ss -ltnp` (2241–2243 y el puerto de la semilla) y `find` de discos;
deja un registro de lo eliminado en `build/registros/limpieza-<fecha>.txt`. No toca grupos ni reglas de red.

## 7. Seguridad (resumen para el auditor)
Sin `curl | sh`; toda descarga con suma fijada; `--require-hashes`; sin `set -x` ni volcado de entorno; nada de
`PROXLAUNCH_LAB`; las MVs no tienen credenciales de Proxmox y su red es de usuario (no alcanzan la red del
laboratorio ni de producción salvo Internet por NAT, necesario para la capacidad OpenSSH de Windows y `apt`);
claves SSH de MV solo en su carpeta, borradas con ella; `revisar_estatico.py` aplica CA-E24.2/E33.1/E35.1.

## 8. Plan de fases y dueños de archivos

```
F3a App: versión, argumentos, humo     -> implementador -> implementador -> bajo  -> src/proxlaunch/{__init__,interfaz/app,interfaz/humo}.py, pyproject.toml
F3b Empaquetado común + Linux + MVs U   -> devops-ci     -> devops-ci     -> alto  -> empaquetado/ (salvo windows/), vista previa de iconos
F3c Windows + MV Windows               -> devops-ci     -> devops-ci     -> alto  -> empaquetado/windows/, entornos/windows/, *.ps1
F4  Pruebas y verificación completa    -> probador      -> probador      -> alto  -> tests/empaquetado/, tests/interfaz/test_humo*.py, registros
F5  Revisión                           -> revisor-qa + auditor-seguridad -> alto -> hallazgos
F6  Documentación                      -> documentador  -> documentador  -> medio -> guía de instalación, docs/empaquetado.md, README
F7  Cierre y limpieza total            -> orquestador   -> —             -> bajo  -> MVs y laboratorio eliminados, bitácora
```
F3a y F3b van en paralelo (F3b usa `--version`/`--prueba-de-humo` por su contrato de §3). F3c necesita la ISO y la
instalación de Windows hechas por el usuario. `.gitignore`: añadir `*.qm` (DT-E7).

## 9. Riesgos de diseño
- PyInstaller con python-build-standalone (AR-1): alternativa deadsnakes ya prevista.
- La tarea interactiva de Windows y el inicio de sesión automático son la parte más frágil: si fallan, el humo de
  Windows se hace desde la sesión interactiva por la propia unidad de apoyo y se documenta.
- La guía de 24.04 con Wayland y el menú (M-E6) exigen escritorio: se hace en la MV 24.04 instalando
  `ubuntu-desktop-minimal` solo para esa comprobación manual.

## Anexo B · Desviaciones e hechos de implementación

Completado al cierre del MVP 5 (2026-11-15), contrastado con el código. La descripción operativa vigente de los
scripts está en `empaquetado/LEEME.md` y en `docs/empaquetado.md`; aquí solo se anota en qué se apartó la
implementación de las secciones anteriores y qué incidencias aparecieron.

### B.1 Desviaciones respecto del diseño

| # | Diseño (sección) | Implementación real | Dónde verlo |
|---|---|---|---|
| B-1 | Semilla de cloud-init servida por `http.server` en `127.0.0.1` con `-smbios` (§1 A4, §6.1, AR-9). | Disco NoCloud **vvfat** de solo lectura con etiqueta `CIDATA`, sin servidor ni puertos. El plan B HTTP se conserva con `PROXLAUNCH_SEMILLA=http`. | `entornos/mv.sh` (`driver=vvfat,…,label=CIDATA`), `LEEME.md` |
| B-2 | Vigilante del humo a 5 s (§3.3). | Vigilante a **15 s** (`LIMITE_VIGILANTE_S`, CA-E17.1), código de salida 3, con respaldo de `faulthandler` (límite + 2 s, vuelca la traza y sale con 1), arbitraje entre hilo principal y vigilante (solo uno da el resultado) y cierre del registro antes de salir. | `interfaz/humo.py` |
| B-3 | ISO de **evaluación** de Windows 11 (§6.2). | ISO de **consumo** (edición Pro sin activar) descargada por el usuario, comparada con la lista «Verificar la descarga» de Microsoft; `mv.sh crear windows11` la comprueba (UDF) y registra su SHA-256, URL y fecha en `iso/ISO-ORIGEN.txt`. | `LEEME.md`, `entornos/windows/comprobar-iso.py` |
| B-4 | Casilla «Borrar también mis datos» en el desinstalador (§4, RF-E13). | Por decisión de implementación se usa una **pregunta Sí/No** (`MsgBox`) en lugar de una casilla (respuesta predeterminada «No»), o `/BORRARDATOS=1` en silencio. Con instalación «para todos los usuarios» no se pregunta ni se borra nada y `/BORRARDATOS=1` se ignora y se anota en el registro de Inno (`/LOG`). | `windows/proxlaunch.iss` (`InitializeUninstall`) |
| B-4b | Texto de la pregunta del desinstalador. | El `.iss` pregunta «¿Desea borrar también sus datos de ProxLaunch…?»; los requisitos lo llaman «Borrar también mis datos» y `empaquetado/LEEME.md` dice «¿Borrar también sus datos?» (discrepancia menor, LEEME.md sin editar). | `windows/proxlaunch.iss`, `empaquetado/LEEME.md` |
| B-5 | `AppMutex` para detectar la app abierta (§4). | `AppMutex=ProxLaunch.InstanciaUnica` sigue en el `.iss`, pero **la aplicación no crea ese mutex** (no hay `CreateMutex` en `src/`): no tiene efecto. La detección real la hace `CloseApplications=yes` (Restart Manager), solo si hay archivos de la instalación en uso. | `windows/proxlaunch.iss`; búsqueda en `src/` sin resultados |
| B-6 | `Categories=Network;System;` (RF-E12). | `Categories=Network;`. Nota de cambio en `docs/requisitos/mvp5.md`. | `linux/proxlaunch.desktop` |
| B-7 | Las sumas las escribe el flujo de verificación (§5, AR-8). | Confirmado y reforzado: `construir-linux.sh` y `construir-windows.ps1` **no** escriben `SHA256SUMS`; solo lo hace `comun/sumas.py` en el anfitrión tras la verificación instalada (CA-E04.1, INV-E6). Antes de construir se borran el artefacto de la versión y sus sellos, y `SHA256SUMS` se reescribe sin ellos. Un artefacto de otra versión se omite con aviso. | `verificar-todo.sh`, `comun/sumas.py` |
| B-8 | Exclusión mutua con el laboratorio (no prevista en §6). | `mv.sh crear\|arrancar` y `verificar-todo.sh` se niegan si algo escucha en `127.0.0.1:8006` o `:2222` o hay un proceso cuya orden contenga `aprovprox-lab`. Solo lee el estado. **El lado inverso (que el laboratorio rechace arrancar con MVs de empaquetado) no está implementado.** | `comun/exclusion-laboratorio.sh` |
| B-9 | Prueba de actualización (no detallada en §5). | `verificar-todo.sh actualizacion-linux\|actualizacion-windows`: build de prueba 0.5.1 (`__version__` cambiado solo en la copia del árbol enviada a la MV), sin calidad, instalada sobre el artefacto 0.5.0 ya sellado; datos idénticos byte a byte (SHA-256). El artefacto de prueba nunca va a `dist/` ni a `SHA256SUMS`. | `verificar-todo.sh`, `verificar-deb.sh --actualizar-desde`, `verificar-windows.ps1 -SoloActualizacion` |
| B-10 | Instalación de las herramientas de Windows (§6.2). | Herramientas fijadas en `entornos/windows/herramientas.json`; `preparar-build.ps1` las vuelve a verificar (suma y firma Authenticode) y deja `verificadas.json`; `lib.ps1` solo acepta esas herramientas. En Linux, `herramientas.sh` solo usa el `uv` fijado. | `windows/preparar-build.ps1`, `linux/herramientas.sh` |

### B.2 Incidencias resueltas

| # | Incidencia | Causa y solución | Dónde verlo |
|---|---|---|---|
| I-1 | `os.replace` fallaba de forma intermitente en Windows al reemplazar un archivo en uso. | Nuevo `reemplazar_con_reintentos`: solo en Windows y solo ante `winerror` 5, 32 o 33; hasta 8 intentos con espera exponencial desde 5 ms y tope total de 1 s; si se agotan, relanza la excepción original. En POSIX es un único `os.replace`. | `nucleo/archivos/reemplazo.py`, `escritura.py` |
| I-2 | Rutas largas en Windows. | `escribir_atomico` mide el destino **y** el temporal más largo posible (prefijo `.proxlaunch-`, 8 caracteres de nombre, 8 aleatorios y `.tmp`) y rechaza con motivo `ruta_larga` si alguno llega a 260 caracteres (`MAX_PATH` incluye el NUL final). | `nucleo/archivos/escritura.py` |
| I-3 | Pruebas dejaron **informes parciales** en `Rutas.informes` de la carpeta real del usuario. | La ventana principal exige `directorio_informes` (y `directorio_lotes`) en sus dependencias, sin valor por omisión; la aplicación pasa `rutas.informes`. La carpeta real afectada ya se limpió. | `interfaz/ventana_principal.py`, `interfaz/app.py` |
| I-4 | Fuga de pruebas a las carpetas reales. | `tests/conftest.py` redirige `HOME`, `XDG_*`, `LOCALAPPDATA` y `APPDATA` (y la resolución de `platformdirs` en Windows) a una carpeta temporal de la sesión, y al terminar compara una instantánea de las carpetas reales: si cambiaron, la sesión falla con «AISLAMIENTO VIOLADO». | `tests/conftest.py` |
| I-5 | La prueba de humo podía colgarse. | Ver B-2 (vigilante a 15 s con respaldo `faulthandler`, arbitraje y cierre del registro). | `interfaz/humo.py` |
| I-6 | `.Count` fallaba en `StrictMode` de PowerShell 5.1 con resultados de 0 o 1 elemento. | Los resultados se envuelven en `@()` antes de contar, en `verificar-windows.ps1` y `construir-windows.ps1` (commit `5a5a2c8`). | `empaquetado/verificar-windows.ps1`, `empaquetado/construir-windows.ps1` |
| I-7 | **QA-M5-01 (crítico):** `paso` ignoraba `set -e` dentro de las funciones (`if ! "$@"`) y un fallo intermedio se daba por correcto; llegó a sellar un `.deb` viejo. | `paso` ejecuta la orden en una subshell con `set -e` activo. Consecuencia: las variables globales que asigne una función pasada a `paso` no llegan al llamador. Autotest sin red ni MVs (`comun/autotest-lib.sh`), que también corre en `calidad.sh`. Se añadió el borrado previo de artefactos y sellos (B-7) y la traída con suma comprobada (`traer_verificado`). | `comun/lib.sh`, `comun/autotest-lib.sh`, `verificar-todo.sh` |
| I-8 | Un `lib.ps1` con error de sintaxis terminaba con código 0 sin hacer nada. | Los `.ps1` fijan `$ErrorActionPreference = 'Stop'` **antes** de cargar `lib.ps1`, y `verificar-todo.sh` valida con el analizador de PowerShell de la MV la sintaxis de todos los `.ps1` antes de ejecutar ninguno. `revisar_estatico.py` también lo valida si hay PowerShell. | `construir-windows.ps1`, `verificar-windows.ps1`, `verificar-todo.sh` |
| I-9 | Los subprocesos de las pruebas de empaquetado no encontraban `proxlaunch` en el venv de calidad (sin el paquete instalado). | Se les pasa `PYTHONPATH` apuntando a `src`. | pruebas de subprocesos como `tests/interfaz/test_mvp5_humo.py` (commit `431064d`) |
| I-10 | La MV de Windows tenía la red en perfil **Pública** y el cortafuegos bloqueaba SSH. | `preparar.ps1` pasa los perfiles Públicos a Privados (`Set-NetConnectionProfile -NetworkCategory Private`). | `entornos/windows/preparar.ps1` |

### B.3 Hipótesis y pendientes al cierre

- **Confirmado por la verificación local:** `.deb` en Ubuntu 22.04 y 24.04; instalador en Windows 11 con TPM 2.0 y Secure Boot;
  prueba de actualización 0.5.0 → 0.5.1 en ambos sistemas (resultados en la bitácora, entrada 18).
- **No implementado:** RF-E21b (auditoría de CVE, «Debería»); exclusión inversa del laboratorio (B-8).
- **Sin probar:** la semilla cloud-init por disco vvfat (B-1) en una MV **nueva**, porque las MVs de Ubuntu ya existían al
  introducirla.
- **Preparado y desactivado:** la firma de código (`PROXLAUNCH_FIRMA_CONFIG`, ver `docs/empaquetado.md`).
- **Comprobaciones manuales** (`[MANUAL]`: asistente en español, SmartScreen, escalado 125/150/175 %, icono del menú Inicio):
  pendientes de resultado; el orquestador las anota en la bitácora.
