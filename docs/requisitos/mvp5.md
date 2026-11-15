# Requisitos del MVP 5 — ProxLaunch (instaladores para Ubuntu y Windows, y scripts de empaquetado con CI preparada)

Versión del documento: 1.1 (2026-11-14) · Estado: decisiones del usuario integradas; listo para arquitectura

Cambios de la v1.0 a la v1.1: se integran las decisiones del usuario y del orquestador (sección 14). Resumen: la CI
**no se activa** (solo scripts locales y una plantilla de GitHub Actions inactiva); el formato de Ubuntu es **solo
`.deb`** (AppImage fuera); **sin firma** en Windows; datos conservados al desinstalar; se **elimina RF-E13b**; icono
aprobado con revisión previa; editor «ProxLaunch»; las pruebas en Windows se hacen en una **MV de evaluación local
con KVM/QEMU, Windows 11 con TPM 2.0 emulado (`swtpm`) y Secure Boot**, que se elimina sin rastro (RF-E40 a RF-E42);
versión **0.5.0**.

Fuentes, en orden de autoridad: `docs/decisiones.md` (en especial **D-06**, **D-19**, **D-15**, D-04, D-05, D-09 y
D-12); `docs/bitacora.md` («Estado actual» y «Pendientes y riesgos abiertos»); `docs/requisitos/mvp4.md` (**M4**)
y `mvp3.md` (**M3**) como modelo de estilo; `README.md`; `pyproject.toml`; y el código existente citado en la
sección 2. Si se contradicen, manda `decisiones.md`. Lo que es inferencia del analista se marca **[A]**. Lo que
depende de un dato externo (versión de herramienta, comportamiento de un runner o biblioteca) se marca **HV-En**
(hipótesis a verificar, sección 11) y no puede darse por cierto.

Convenciones (las de M3/M4, con prefijos propios):
- **Prioridad:** Debe / Debería / Podría.
- **IDs:** RF-Enn, RNF-Enn, CA-Enn.y (criterio y del requisito), CL-En (caso límite), INV-En, DT-En (decisión
  técnica del analista, sección 12), HV-En (hipótesis), R-En (riesgo), M-En (comprobación manual).
- Criterios con "Dado / Cuando / Entonces". **Modo de verificación**, por decisión del usuario (la CI no se activa):
  - `[LOCAL]`: se ejecuta con los scripts del repositorio (carpeta propuesta `empaquetado/`) en el equipo de
    desarrollo, en contenedores o en la MV de evaluación (RF-E40). **Sustituye al antiguo `[CI]`.**
  - `[MANUAL]`: requiere una persona (revisión visual, asistente, escalado, lectura de la guía).
  - Los criterios sobre la plantilla de CI se verifican por **revisión estática** `[LOCAL]` (el script de revisión
    lee el YAML; la plantilla no se ejecuta).
- "Artefacto" = archivo entregado al usuario (`-setup.exe`, `.deb`). "Congelado" = la aplicación empaquetada con
  su intérprete y bibliotecas, sin necesitar Python instalado.

---

## 1. Objetivos y alcance

### 1.1 Objetivo
Que una persona sin conocimientos de Python instale ProxLaunch en Ubuntu 22.04/24.04 o en Windows 10/11 de 64 bits
con un solo artefacto, lo abra desde el menú, lo actualice y lo desinstale sin residuos; y que el mantenedor pueda
reconstruir y verificar esos artefactos con un comando por sistema, con garantías de integridad (D-06). Se entrega
además una definición de CI lista para activar el día que exista un remoto, sin activarla ahora.

### 1.2 Dentro del MVP 5
1. Artefactos instalables: instalador `.exe` con asistente (Windows) y `.deb` (Ubuntu), con Python embebido
   (resuelve «Python en Ubuntu 22.04», bitácora).
2. Integración de escritorio, desinstalación limpia y política de datos de usuario y llavero.
3. Empaquetado correcto de recursos, traducciones compiladas, fuentes, plugins de Qt y backend del llavero.
4. Versión única y visible (0.5.0), prueba de humo del artefacto instalado, presupuesto de tamaño.
5. **Scripts locales** de calidad (lint, formato, tipos, pruebas no-integración), construcción, prueba de humo y
   sumas SHA-256 en `dist/`; y la **plantilla de CI inactiva** (GitHub Actions) como referencia.
6. Seguridad de la cadena de suministro; paso de firma de Windows **preparado y desactivado**.
7. Entorno de pruebas local: MV Windows 11 de evaluación (TPM 2.0 emulado y Secure Boot) y contenedores/MVs Ubuntu,
   con eliminación total al final.
8. Guía de instalación y guía de construcción.

### 1.3 Fuera del MVP 5
- **macOS** (D-06), ARM y 32 bits (decisión: solo amd64).
- **AppImage** (decisión del usuario), Snap, Flatpak y repositorio APT propio.
- **CI activa**: no se crea `.github/workflows/` ni remoto git; la plantilla vive fuera de las rutas que un
  proveedor lee automáticamente.
- Firma de código en Windows (certificado EV/OV): el paso queda preparado y desactivado (RF-E24).
- Autoactualización, canal de actualizaciones, telemetría (la app solo habla con el Proxmox del usuario, D-18).
- Publicación en tiendas o repositorios públicos (D-19; `Private :: Do Not Upload`). La distribución es **manual**.
- Paquete MSI e instalación desatendida masiva (GPO/Intune/SCCM).
- Cambios funcionales de la app, salvo los mínimos de la sección 13. **No** se añade acción «Olvidar credenciales»
  (RF-E13b eliminado).
- Cambiar el logotipo (D-01): solo conversión de formato del símbolo aprobado.
- Pruebas `integracion` o tocar el laboratorio Proxmox desde los scripts (D-15, RF-E33). Probar contra Proxmox real.

### 1.4 Supuestos
- S-E1: distribución **interna y manual**: los artefactos quedan en `dist/` con `SHA256SUMS`.
- S-E2: arquitectura única **x86_64 / amd64**.
- S-E3: desarrollo con Python 3.14 en `.venv`; mínimo `requires-python >= 3.11`. El artefacto lleva su intérprete.
- S-E4: la persistencia no cambia: carpetas de `platformdirs` con nombre `ProxLaunch` y servicio de llavero
  `ProxLaunch`. Cambiar cualquiera rompería las actualizaciones (RF-E14, INV-E3).
- S-E5: no hay CI remota. Windows se prueba en una **MV de evaluación local** (RF-E40): **Windows 11** con TPM 2.0
  emulado y Secure Boot, sin saltarse comprobaciones; Windows 10 queda como prueba `[MANUAL]` opcional (M-E1).
- S-E6: el equipo de desarrollo dispone de `qemu-system-x86_64`, `qemu-img`, OVMF (incluido el `.ms.fd` con claves
  de Secure Boot), `swtpm` 0.10.1 con `swtpm_setup`, `/dev/kvm` accesible, ~16 GB de RAM libres y ~295 GB de disco
  (datos del usuario, verificados por el orquestador; `swtpm` se comprobó arrancándolo sin `sudo`).
- S-E7: borrar un perfil de conexión, o desmarcar «Recordar credenciales», ya borra su secreto del llavero (verificado
  por el orquestador en `nucleo/persistencia/perfiles.py:191` e `interfaz/dialogos/conexion.py:662`; no re-verificado
  por el analista).
- S-E8: el socket Unix de `swtpm` (unixio) debe tener una **ruta corta (< 108 caracteres)**; con rutas largas falla con
  «Path for UnioIO socket is too long» (verificado por el orquestador). El socket va en un directorio temporal corto
  (p. ej. bajo `/tmp`), no en la carpeta de la MV si esta es larga.

---

## 2. Hechos del estado actual (verificados en el repositorio)

| # | Hecho | Fuente | Consecuencia |
|---|---|---|---|
| H1 | Punto de entrada `proxlaunch = "proxlaunch.interfaz.app:main"`; existe `src/proxlaunch/__main__.py`. | `pyproject.toml`, árbol | El congelador parte de `main`. |
| H2 | Dependencias de ejecución: `PySide6-Essentials>=6.11`, `requests>=2.32.4`, `urllib3>=2.6.3,<3`, `keyring>=25`, `platformdirs>=4`. Sin tope superior salvo `urllib3`. | `pyproject.toml` | Fijar versiones exactas con hashes (RF-E21). |
| H3 | La app importa solo `PySide6.QtCore`, `QtGui`, `QtWidgets` y `QtSvg`. | búsqueda en `src/` | Se pueden excluir los demás módulos de Qt (RF-E19). |
| H4 | La versión está escrita **dos veces** (`0.1.0`) en `pyproject.toml` y `src/proxlaunch/__init__.py`. | archivos | RF-E10; pasa a 0.5.0. |
| H5 | **No hay `.qm` en el repo**, solo `proxlaunch_es.ts`. `cargar_traductor` busca `proxlaunch_es.qm` y, si falta, sigue con los textos del código. `package-data` ya incluye `recursos/traducciones/*`. | `app.py`, árbol | El build debe generar el `.qm` (RF-E07). |
| H6 | Fuentes `OpenSans-Variable.ttf`, `JetBrainsMono-Variable.ttf` y sus OFL; marca SVG; `interfaz/tema/plantilla.qss`. Se leen con `importlib.resources` o equivalentes. | árbol, `pyproject.toml` | Deben viajar en el congelado (RF-E06, RF-E16). |
| H7 | El icono de la ventana se arma en ejecución desde `proxlaunch-icono-sin-texto.svg`. **No existe** `.ico`, PNG empaquetado ni `.desktop`. En la raíz: `logotipo.png`, `boton-icono-favicon.png`. | `app.py`, árbol | Se generan en el build (RF-E11, RF-E12). |
| H8 | HiDPI: `setHighDpiScaleFactorRoundingPolicy(PassThrough)` antes de crear `QApplication`. | `app.py` | Comprobar en el artefacto (RF-E15). |
| H9 | Rutas con `platformdirs` (`ProxLaunch`); `Rutas(base)` redirige todo a una carpeta dada. | `rutas.py` | El modo de humo usa `Rutas(base_temporal)` (RF-E17). |
| H10 | Llavero: `SERVICIO = "ProxLaunch"`; `AlmacenSecretos` detecta backends `fail`/`null` y la app sigue sin «Recordar credenciales» (CA-08.4). | `secretos.py` | Degrada **en silencio** si el congelado pierde el backend (RF-E09). |
| H11 | `LICENSE` (todos los derechos reservados); D-19 exige incluir licencias de dependencias. | `LICENSE`, `decisiones.md` | RF-E23. |
| H12 | `.gitignore` ya ignora `build/`, `dist/`, `*.spec.bak`. No hay `.github/`, `.gitlab-ci.yml`, lockfile ni `requirements*.txt`. | `.gitignore`, árbol | Nada previo que respetar. |
| H13 | `main()` no admite argumentos propios: no hay `--version` ni modo de humo; usa `Rutas()` reales y el llavero real. | `app.py` | RF-E17 exige un cambio mínimo. |
| H14 | Suite: `python -m pytest -q -m "not integracion"` (~7200 pruebas, ~3 min, Qt offscreen), `addopts = "--disable-socket --allow-unix-socket"`, marca `integracion` solo con `PROXLAUNCH_LAB=1`; `ruff check`, `ruff format --check`, `mypy src`; cobertura documentada: 85 % núcleo, 75 % global. | `pyproject.toml`, README | Contenido de los pasos de calidad (RF-E32). |
| H15 | El repositorio git **no tiene remoto**. | encargo | Decisión: CI no activa (1.3). |
| H16 | Bitácora: «Python en Ubuntu 22.04: trae 3.10 … resolver al empaquetar», «Firma de código en Windows: pospuesta al MVP 5» y «Windows real (MVP 3)»: archivo bloqueado y rutas largas solo con simulación. | `bitacora.md` | RF-E03, RF-E24, RF-E40, CL-E13. |
| H17 | El README menciona que en Ubuntu puede faltar `libxcb-cursor0` y lo califica como pista no comprobada. | README | HV-E3, RF-E08. |

---

## 3. Usuarios y flujos

- **Usuario final:** recibe el artefacto de forma manual, comprueba la suma (opcional), instala, abre desde el menú,
  actualiza y desinstala.
- **Mantenedor:** ejecuta los scripts de `empaquetado/` en local; publica copiando `dist/` (manual).
- **Revisor de seguridad:** verifica sumas, dependencias fijadas y ausencia de secretos.

Flujos:
1. Instalar (Windows): `.exe` → asistente en español → ámbito (por usuario por defecto) → accesos → fin → abrir.
2. Instalar (Ubuntu): `sudo apt install ./proxlaunch_<v>_amd64.deb`.
3. Actualizar: instalar la versión nueva encima; perfiles, lotes, preferencias, huellas y credenciales siguen ahí.
4. Desinstalar: «Aplicaciones instaladas» (Windows) o `apt remove`; datos conservados por defecto.
5. Publicar: el mantenedor ejecuta calidad → build → humo → sumas; copia `dist/` por el medio interno que elija.

---

## 4. Requisitos funcionales

### 4.1 Artefactos y construcción

**RF-E01 — Instalador de Windows con asistente (Debe).** `proxlaunch-<versión>-windows-x64-setup.exe` para Windows 10
y 11 de 64 bits, con asistente en español: bienvenida, licencia (texto de `LICENSE`), **ámbito de instalación**
(«solo para mí», por defecto, sin administrador; o «para todos los usuarios», con UAC), carpeta de destino, accesos
directos, progreso y fin con casilla «Abrir ProxLaunch». Herramienta: Inno Setup (DT-E4, decisión del orquestador).
- CA-E01.1 Dado un Windows 11 limpio (la MV de evaluación, RF-E40; Windows 10 opcional), cuando se ejecuta el
  instalador aceptando los valores por defecto, entonces ProxLaunch se instala para el usuario actual sin pedir
  administrador, aparece en el menú Inicio con su icono y se abre. `[MANUAL]`
- CA-E01.2 Dado el instalador, cuando se ejecuta en modo silencioso, entonces instala sin interacción con código de
  salida 0 (lo usa RF-E18). `[LOCAL]`
- CA-E01.3 Dado el asistente, cuando se elige «para todos los usuarios», entonces pide elevación y instala en
  `Program Files`. `[MANUAL]`
- CA-E01.4 Dado Windows de 32 bits o anterior a Windows 10, cuando se lanza, entonces se niega con mensaje claro y no
  instala (se verifica leyendo la condición del script `.iss`). `[LOCAL]` [A]
- CA-E01.5 Dado el asistente, cuando se recorre, entonces todos sus textos están en español (D-04) y la licencia es la
  de `LICENSE` sin modificar. `[MANUAL]`

**RF-E02 — Paquete `.deb` para Ubuntu (Debe).** `proxlaunch_<versión>_amd64.deb` para Ubuntu 22.04 y 24.04 LTS: app
congelada bajo `/opt/proxlaunch/`, enlace `/usr/bin/proxlaunch`, `.desktop`, iconos y avisos de licencia. Instalación
para todo el equipo (decisión del orquestador). **AppImage queda fuera del alcance.** Campos: `Package: proxlaunch`,
`Maintainer: ProxLaunch <noreply@localhost>`, `Architecture: amd64`.
- CA-E02.1 Dado un Ubuntu 22.04 y uno 24.04 con su Python por defecto (3.10 y 3.12 [A]) y sin Python de pip, cuando
  se instala el `.deb`, entonces `proxlaunch` abre la ventana principal. `[LOCAL]` (contenedor con `xvfb` o MV local) y
  `[MANUAL]` (escritorio real, si hay MV con escritorio)
- CA-E02.2 Dado el `.deb`, cuando se inspecciona con `dpkg-deb --info`/`--contents`, entonces declara `amd64`, la versión
  de RF-E10, el `Maintainer` indicado, `Depends` solo con bibliotecas de sistema que Qt necesita y no van incluidas
  (p. ej. `libxcb-cursor0`, HV-E3), ninguna dependencia de `python3`/`python3-*`, e incluye
  `/usr/share/doc/proxlaunch/copyright`. `[LOCAL]`
- CA-E02.3 Dado el ejecutable y las `.so` de Qt incluidas, cuando se ejecuta `ldd`, entonces no hay «not found» fuera de
  las dependencias declaradas. `[LOCAL]`
- CA-E02.4 Dado el `.deb`, cuando se lista su contenido, entonces no hay AppImage ni archivos fuera de `/opt/proxlaunch`,
  `/usr/bin`, `/usr/share/applications`, `/usr/share/icons` y `/usr/share/doc`. `[LOCAL]`

**RF-E03 — Python embebido (Debe).** Los artefactos llevan su intérprete y bibliotecas; no usan el Python del sistema.
Resuelve el pendiente de la bitácora (3.10 en Ubuntu 22.04 vs `requires-python >= 3.11`).
- CA-E03.1 Dado un Ubuntu 22.04 cuyo único Python es 3.10, cuando se instala y abre el `.deb`, entonces arranca. `[LOCAL]`
- CA-E03.2 Dado el artefacto instalado, cuando se ejecuta `--version` (RF-E17) sin Python en el `PATH`, entonces imprime
  la versión y sale con 0. `[LOCAL]`
- CA-E03.3 Dado el congelado, cuando se inspecciona, entonces incluye una sola versión de Python, la de DT-E3, ≥ 3.11. `[LOCAL]`

**RF-E04 — Construcción reproducible por un comando por sistema (Debe).** Un script por sistema (Ubuntu: shell;
Windows: PowerShell) a partir de un checkout limpio produce los artefactos y sus sumas. Reproducible = mismas entradas
fijadas (código, lockfile con hashes, versiones de herramientas) → mismo contenido funcional. Bit a bit idéntico es
**Podría** (RF-E04b).
- CA-E04.1 Dado un checkout limpio, cuando se ejecuta el script de cada SO, entonces se generan los artefactos con el
  nombre `proxlaunch-<versión>-<so>-<arquitectura>.<ext>` (Windows `-setup.exe`; Ubuntu `.deb`) en `dist/` y
  `dist/SHA256SUMS`. `[LOCAL]`
- CA-E04.2 Dado el script, cuando se lanza dos veces en el mismo entorno, entonces ambas pasan la prueba de humo y
  producen el mismo conjunto de archivos. `[LOCAL]`
- CA-E04.3 Dado el script, cuando se revisa, entonces no descarga código ejecutable sin verificar su hash/firma y no
  escribe fuera del checkout y de su carpeta temporal. `[LOCAL]` (revisión estática) y `[MANUAL]`
- **RF-E04b — Reproducibilidad bit a bit (Podría).** Con `SOURCE_DATE_EPOCH` y orden estable de archivos, dos builds
  dan la misma suma; si una herramienta lo impide, se documenta (R-E8).

**RF-E05 — Compatibilidad de plataforma (Debe).**
- Linux: se construye en la base **más antigua** admitida (Ubuntu 22.04, en contenedor) para que funcione también en
  24.04.
- Windows: 10 y 11 de 64 bits; los runtimes de Microsoft que necesiten Python y Qt van incluidos o el instalador los
  comprueba (HV-E1, CL-E10).
- CA-E05.1 Dado el `.deb`, cuando se mide la versión máxima de símbolos glibc requeridos, entonces es ≤ 2.35. `[LOCAL]`
- CA-E05.2 Dado el artefacto de Windows, cuando se instala en un Windows 11 limpio de la MV (sin Visual C++
  instalado previamente), entonces arranca; en Windows 10, igual si se hace la prueba opcional. `[MANUAL]`
- CA-E05.3 Dado el ejecutable de Windows, cuando se inspecciona, entonces es PE de 64 bits. `[LOCAL]`

### 4.2 Contenido del congelado

**RF-E06 — Recursos empaquetados (Debe).** El congelado incluye, y la app encuentra: `recursos/marca/*.svg`,
`recursos/fuentes/*` (TTF y OFL), `recursos/traducciones/*` (incluido `proxlaunch_es.qm`),
`interfaz/tema/plantilla.qss`, `LICENSE` y el aviso de terceros (RF-E23). La lista sale de `package-data` [A].
- CA-E06.1 Dado el congelado, cuando se compara con `package-data` más `proxlaunch_es.qm`, `LICENSE` y avisos, entonces
  no falta ninguno. `[LOCAL]`
- CA-E06.2 Dado el modo de humo, cuando falta uno de esos recursos, entonces sale con código ≠ 0 y lo nombra. `[LOCAL]`

**RF-E07 — Traducciones compiladas (Debe).** El build compila `proxlaunch_es.ts` a `.qm` (herramienta de Qt de PySide6,
HV-E2) **antes** de congelar; el `.qm` es producto del build y no se versiona (DT-E7). Falla si la compilación falla o
el `.qm` queda vacío. El build no regenera el `.ts`.
- CA-E07.1 Dado el artefacto instalado, cuando corre el modo de humo, entonces el traductor se instala (el `.qm` existe
  y `QTranslator.load` tiene éxito); si no, el humo falla. `[LOCAL]`
- CA-E07.2 Dado el `.qm`, cuando se contrasta con el `.ts`, entonces coinciden los mensajes traducidos (sin contar los
  vacíos) dentro de la tolerancia del compilador. `[LOCAL]` [A]
- CA-E07.3 Dado un `.ts` con XML inválido en una copia de prueba, cuando se ejecuta el build, entonces falla con mensaje
  comprensible. `[LOCAL]`

**RF-E08 — Plugins de Qt (Debe).** Se incluyen los necesarios y solo esos: `platforms` (Windows `qwindows`; Linux `xcb`
y `offscreen` para pruebas; Wayland si hace falta), `imageformats` (SVG y PNG), `iconengines` (SVG), `styles`,
`platformthemes` en Linux, `tls` si Qt lo exige, según lo que el congelador detecte y el humo confirme. Las `libxcb-*`
ausentes se declaran como dependencia del `.deb` (HV-E3).
- CA-E08.1 Dado el artefacto, cuando arranca en pantalla virtual (`xvfb` en Linux; sesión de escritorio de la MV en
  Windows) con el plugin de plataforma **real**, entonces la ventana aparece y se cierra con éxito. `[LOCAL]`
- CA-E08.2 Dado el icono SVG de la ventana, cuando arranca, entonces `QIcon` no es nulo; si falta el plugin SVG, el humo
  falla. `[LOCAL]`
- CA-E08.3 Dado el congelado, cuando se enumeran los módulos de Qt, entonces solo están Core, Gui, Widgets, Svg y sus
  dependencias transitivas (H3). `[LOCAL]`
- CA-E08.4 Dado un Ubuntu con Wayland y otro con X11 (si hay MV con escritorio), cuando se abre la app, entonces funciona
  en ambos y el icono se asocia al `.desktop` (RF-E12). `[MANUAL]`

**RF-E09 — Backend del llavero en cada SO (Debe).** El congelado incluye y registra el backend de `keyring`: en Windows,
el Administrador de credenciales; en Linux, Secret Service (GNOME Keyring o KWallet). `keyring` elige backend por
**puntos de entrada de los metadatos** (HV-E5), que un congelador puede perder; la app degrada en silencio (H10), por
eso se prueba de forma expresa.
- CA-E09.1 Dado el artefacto de Windows instalado, cuando el modo de humo pregunta qué backend de `keyring` está activo
  (sin escribir secretos), entonces es el de Windows, no `fail`/`null`. `[LOCAL]` (en la MV)
- CA-E09.2 Dado el `.deb` en un entorno con servicio de secretos de prueba (D-Bus de sesión + `gnome-keyring-daemon`
  desbloqueado, en contenedor), cuando el humo pregunta el backend, entonces es el de Secret Service. `[LOCAL]`
- CA-E09.3 Dado el `.deb` **sin** servicio de secretos, cuando se abre la app, entonces arranca y «Recordar credenciales»
  queda desactivado con el mensaje existente (CA-08.4), sin excepciones. `[LOCAL]`
- CA-E09.4 Dadas credenciales de prueba con el servicio `ProxLaunch-prueba` (nunca el real), cuando se guardan, leen y
  borran con el artefacto instalado en la MV Windows, entonces el ciclo funciona y no quedan restos. `[MANUAL]`

**RF-E10 — Versión única, coherente y visible: 0.5.0 (Debe).** Una sola fuente de verdad (DT-E6). `pyproject.toml`,
`proxlaunch.__version__`, nombre del artefacto, metadatos de los instaladores (versión del producto y del archivo en
Windows; `Version` del `.deb`) y Ayuda → Acerca de coinciden. La versión del lanzamiento es **0.5.0**, con formato
**SemVer** `X.Y.Z` (los sufijos de preliberación, como `-rc1`, solo en la etiqueta git y no en los metadatos de
Windows, que exigen números [A]).
- CA-E10.1 Dado un commit, cuando se ejecuta el script de comprobación de versión, entonces compara `pyproject.toml`,
  `__version__` y la etiqueta (si existe) y falla si difieren. `[LOCAL]`
- CA-E10.2 Dado el artefacto instalado, cuando se consulta, entonces «Aplicaciones instaladas» (Windows), `dpkg -s
  proxlaunch`, Acerca de y `proxlaunch --version` muestran `0.5.0`. `[LOCAL]` y `[MANUAL]` (ficha del `.exe`)
- CA-E10.3 Dada una versión que no cumple `X.Y.Z`, cuando se ejecuta el build, entonces falla antes de construir. `[LOCAL]`

**RF-E11 — Integración de escritorio en Windows (Debe).**
- Icono del ejecutable, instalador y desinstalador: `.ico` multirresolución (16, 24, 32, 48, 64, 128, 256 px)
  generado en el build desde el **símbolo sin texto** del logotipo aprobado, **sin cambiar diseño ni colores** (DT-E9).
- Acceso directo en el menú Inicio («ProxLaunch»); acceso directo en el escritorio opcional y desmarcado por defecto [A].
- Entrada en «Aplicaciones instaladas» con nombre, versión, editor **«ProxLaunch»**, icono y desinstalador.
- AppUserModelID coherente para agrupar en la barra de tareas [A].
- CA-E11.1 Dado el artefacto instalado, cuando se mira el menú Inicio, la barra de tareas y «Aplicaciones instaladas»,
  entonces aparece «ProxLaunch», icono de la marca, editor «ProxLaunch» y versión correcta. `[MANUAL]`
- CA-E11.2 Dado el `.ico`, cuando se inspecciona, entonces contiene al menos 16, 32, 48 y 256 px. `[LOCAL]`
- CA-E11.3 Dado el acceso directo del escritorio, cuando se acepta el asistente sin tocar nada, entonces no se crea. `[MANUAL]`
- CA-E11.4 **Revisión previa del usuario.** Dados los iconos generados (`.ico` y PNG), cuando el mantenedor produce una
  vista previa (hoja con todos los tamaños sobre fondo claro y oscuro, junto al original), entonces el usuario la
  revisa y la aprueba **antes** de integrarlos en el instalador y el `.deb`; el criterio exige también que el
  símbolo no tenga texto, recortes ni cambios de color respecto del original. `[MANUAL]`

**RF-E12 — Integración de escritorio en Ubuntu (Debe).**
- `proxlaunch.desktop` con `Name=ProxLaunch`, `Comment` en español, `Exec=proxlaunch`, `Icon=proxlaunch`,
  `Terminal=false`, `Categories=Network;System;` [A], `StartupWMClass`/`desktop-file-name` coherentes (HV-E11).
- Iconos `hicolor` (PNG 16 a 256 px y/o SVG) en `/usr/share/icons/hicolor/<tamaño>/apps/proxlaunch.png`, derivados del
  símbolo aprobado (sujetos a CA-E11.4).
- CA-E12.1 Dado el `.desktop`, cuando se valida con `desktop-file-validate`, entonces no da errores. `[LOCAL]`
- CA-E12.2 Dado el `.deb` instalado en una MV con escritorio, cuando se busca «ProxLaunch» en las actividades, entonces
  aparece con su icono. `[MANUAL]`
- CA-E12.3 Dado el `.deb`, cuando se instala, entonces los *triggers* de dpkg para el menú y los iconos terminan sin
  errores. `[LOCAL]`

**RF-E13 — Desinstalación limpia y política de datos (Debe).**
- Se elimina todo lo instalado: archivos, accesos directos, entrada de «Aplicaciones instaladas», `.desktop`, iconos,
  enlace `/usr/bin/proxlaunch`, claves de registro propias.
- **Los datos del usuario se conservan por defecto** (perfiles, huellas de certificados, preferencias, lotes
  guardados, informes, registro): en `~/.config/ProxLaunch`, `~/.local/share/ProxLaunch`, `~/.local/state/ProxLaunch`
  (o equivalentes de `platformdirs`) en Ubuntu y en `%APPDATA%`/`%LOCALAPPDATA%` en Windows. En Ubuntu, `apt remove` y
  `apt purge` no tocan `$HOME`.
- **Windows:** el desinstalador ofrece una casilla **desmarcada** «Borrar también mis datos» que, marcada, borra las
  carpetas de datos, configuración y registro de `ProxLaunch` **del usuario que desinstala** y nada más.
- **El llavero nunca se toca** al desinstalar. Las credenciales guardadas quedan y reaparecen al reinstalar. **No se
  añade ninguna acción nueva en la app (RF-E13b eliminado):** la app ya borra el secreto al borrar un perfil de
  conexión o al desmarcar «Recordar credenciales» (S-E7). La guía documenta ese procedimiento para hacerlo **antes**
  de desinstalar y, si ya se desinstaló, cómo quitar a mano las entradas del servicio `ProxLaunch` desde el
  Administrador de credenciales (Windows) o «Contraseñas y claves» (Ubuntu).
- CA-E13.1 Dado ProxLaunch instalado y datos de usuario de prueba, cuando se desinstala sin marcar la casilla, entonces
  desaparecen los archivos instalados, accesos directos y la entrada de desinstalación propia, y los datos del usuario
  permanecen intactos (misma suma). `[LOCAL]` (contenedor para Ubuntu; MV para Windows)
- CA-E13.2 Dado lo mismo, cuando se desinstala marcando la casilla (Windows), entonces desaparecen las carpetas de datos,
  configuración y registro de ProxLaunch de **ese** usuario y no se toca nada más. `[LOCAL]` (MV)
- CA-E13.3 Dado un llavero de prueba con una entrada `ProxLaunch-prueba`, cuando se desinstala (con o sin casilla),
  entonces la entrada sigue ahí. `[MANUAL]`
- CA-E13.4 Dado el `.deb`, cuando se ejecuta `apt remove` y luego `apt purge`, entonces `dpkg -L proxlaunch` queda
  vacío, `find` no halla archivos de `proxlaunch` fuera de `$HOME` y `$HOME` no cambia. `[LOCAL]`
- CA-E13.5 Dado un proceso de ProxLaunch en ejecución, cuando se desinstala, entonces el desinstalador lo detecta y pide
  cerrarlo (Windows) o el paquete avisa (Linux); no deja archivos bloqueados a medio borrar. `[MANUAL]`
- CA-E13.6 Dada la guía, cuando se lee, entonces explica los dos caminos para quitar secretos (antes: borrar el perfil o
  desmarcar «Recordar credenciales»; después: a mano) y que el desinstalador no los toca. `[MANUAL]`

**RF-E14 — Actualización encima conservando datos (Debe).** Instalar una versión posterior reemplaza los archivos del
programa y conserva datos y credenciales. Identificador estable entre versiones (Windows: AppId; Linux: paquete
`proxlaunch`). Bajar de versión no se hace en silencio (Debería).
- CA-E14.1 Dada v(N) instalada con datos de prueba, cuando se instala v(N+1), entonces se actualiza (una sola entrada en
  «Aplicaciones instaladas»), la app abre y lee los datos previos. `[LOCAL]` (con dos builds de prueba) y `[MANUAL]`
- CA-E14.2 Dada v(N+1) instalada, cuando se instala v(N), entonces el instalador avisa y pide confirmación (Windows) o
  `dpkg`/`apt` lo advierte (Linux). `[MANUAL]` (Debería)
- CA-E14.3 Dada v(N) abierta, cuando se instala v(N+1), entonces el instalador detecta la app en uso y pide cerrarla. `[MANUAL]`
- CA-E14.4 Dados el servicio de llavero `ProxLaunch` y los nombres de carpetas de `platformdirs`, cuando se comparan entre
  versiones, entonces no cambiaron; una prueba del repositorio fija esas constantes. `[LOCAL]`

### 4.3 Comportamiento en ejecución del artefacto

**RF-E15 — Escalado de alta resolución en Windows (Debe).** La interfaz se ve nítida con 100, 125, 150 y 175 % y con
monitores mixtos (D-06, H8).
- CA-E15.1 Dado Windows con escalado 150 % (y, si es posible, otra pantalla al 100 %), cuando se mueve la ventana,
  entonces texto, iconos y márgenes se reajustan sin borrosidad ni cortes. `[MANUAL]` (en la MV se puede cambiar el
  escalado de la sesión; monitores mixtos solo en equipo físico)
- CA-E15.2 Dado el `.exe`, cuando se inspecciona su manifiesto, entonces declara DPI por monitor (`PerMonitorV2`) o el
  modo que Qt requiera (HV-E12). `[LOCAL]` [A]
- CA-E15.3 Dado escalado 125 % en 1366×768, cuando se abren los diálogos más grandes (Importar CSV, Lote por filas,
  Perfiles de máquina), entonces ninguno queda cortado fuera de la pantalla [A]. `[MANUAL]`

**RF-E16 — Fuentes incluidas y carga independiente de la instalación (Debe).** Open Sans y JetBrains Mono viajan en el
congelado (D-06) y se cargan desde el paquete, no desde el sistema; la resolución del recurso no depende de `__file__`
relativo a `src/`.
- CA-E16.1 Dado un equipo sin esas fuentes instaladas, cuando arranca el artefacto, entonces `cargar_fuentes()` devuelve
  las familias incluidas (el humo lo comprueba por nombre). `[LOCAL]`
- CA-E16.2 Dados los textos OFL, cuando se revisa el artefacto, entonces se entregan junto a las fuentes y Acerca de los
  muestra. `[LOCAL]` (archivos) y `[MANUAL]` (diálogo)

### 4.4 Prueba de humo

**RF-E17 — Modo de comprobación del artefacto (Debe).** Dos opciones de línea de comandos mínimas (nombres exactos: los
fija la arquitectura):
- `--version`: imprime `ProxLaunch <versión>` y sale con 0 sin crear `QApplication`.
- `--prueba-de-humo`: crea la `QApplication`, carga fuentes, traducciones, tema e icono, **crea y muestra la ventana
  principal**, procesa eventos un tiempo corto (≤ 5 s) y sale con 0. Ante cualquier problema (recurso, plugin, traductor,
  fuente, icono nulo, backend de llavero inesperado) sale ≠ 0 con motivo claro en la salida de error. En este modo la
  app **no hace llamadas de red**, **no usa las carpetas reales del usuario** (carpeta temporal con `Rutas(base)`, H9),
  **no lee ni escribe secretos** y no deja procesos ni archivos.
- CA-E17.1 Dado el artefacto instalado y sin red (`unshare -n` en Linux; adaptador de red de la MV desconectado en
  Windows [A]), cuando se ejecuta `--prueba-de-humo`, entonces sale con 0 en ≤ 15 s. `[LOCAL]`
- CA-E17.2 Dado el modo de humo, cuando termina, entonces las carpetas de datos/config/registro del usuario y el
  llavero no cambian (el script compara listados antes y después). `[LOCAL]`
- CA-E17.3 Dado el árbol de fuentes, cuando se ejecuta `python -m proxlaunch --prueba-de-humo`, entonces también pasa. `[LOCAL]`
- CA-E17.4 Dado un congelado al que se le quita a propósito un recurso (`.qm`, una fuente, el plugin de plataforma),
  cuando se ejecuta el humo, entonces sale ≠ 0 con el motivo. `[LOCAL]`
- CA-E17.5 Dado el modo normal (sin opciones), cuando arranca, entonces el comportamiento es idéntico al actual y las
  pruebas existentes pasan. `[LOCAL]`

**RF-E18 — El humo se ejecuta sobre el artefacto ya instalado (Debe).** El script de verificación no prueba el árbol de
build sino lo que recibirá el usuario. Windows (en la MV): instala el `-setup.exe` en modo silencioso, ejecuta el `.exe`
instalado y desinstala. Ubuntu: instala el `.deb` en contenedores 22.04 y 24.04, ejecuta, desinstala y comprueba RF-E13.
- CA-E18.1 Dado un artefacto recién construido, cuando termina la verificación, entonces se ejecutó: instalar →
  `--version` → `--prueba-de-humo` → desinstalar → comprobar que no queda nada. `[LOCAL]`
- CA-E18.2 Dado un artefacto cuyo humo falla, cuando termina el script, entonces **no** se escribe en `SHA256SUMS`
  (no hay suma «publicable») y el script sale con error. `[LOCAL]`

### 4.5 Tamaño

**RF-E19 — Tamaño razonable (Debe).** El congelado excluye lo que no se usa: módulos de Qt distintos de Core, Gui,
Widgets y Svg (H3), traducciones de Qt de otros idiomas, pruebas, documentación de bibliotecas y símbolos de
depuración. **Presupuesto aceptado como punto de partida**, a recalibrar tras medir (HV-E13): artefacto comprimido
≤ 90 MB e instalado ≤ 250 MB por plataforma; ventana visible en ≤ 5 s en un equipo medio [A].
- CA-E19.1 Dado un build, cuando termina, entonces el script imprime el tamaño de cada artefacto y del árbol instalado y
  los compara con el presupuesto; superarlo más de un 10 % hace fallar el script (el presupuesto se cambia en un commit
  explícito). `[LOCAL]`
- CA-E19.2 Dado el congelado, cuando se lista, entonces no hay `tests/`, `.ts` ni módulos de Qt no usados. `[LOCAL]`
- CA-E19.3 Dado un equipo medio (4 GB de RAM [A]) o la MV con RAM equivalente, cuando se abre la app, entonces la ventana
  aparece en ≤ 5 s. `[MANUAL]`

### 4.6 Cadena de suministro y licencias

**RF-E20 — Sumas SHA-256 (Debe).** `dist/SHA256SUMS` con la suma de cada artefacto (formato `suma␠␠nombre`,
verificable con `sha256sum -c` y `Get-FileHash`), calculada sobre el archivo final. La distribución es manual: la guía
pide al destinatario verificar la suma recibida por un medio distinto al del archivo cuando sea posible.
- CA-E20.1 Dado `dist/`, cuando se ejecuta `sha256sum -c SHA256SUMS`, entonces todos dan OK. `[LOCAL]`
- CA-E20.2 Dado un artefacto alterado en un byte, cuando se verifica, entonces falla. `[LOCAL]`
- CA-E20.3 Dado `SHA256SUMS`, cuando se lee, entonces solo trae nombres relativos, sin rutas ni nombres de usuario. `[LOCAL]`

**RF-E21 — Dependencias y herramientas fijadas (Debe).** Dependencias de ejecución **y transitivas** con versión exacta
y hash (DT-E8); lo mismo para herramientas de build (congelador, Inno Setup, `dpkg-deb`/`fakeroot` si aplica) y, en la
plantilla de CI, acciones e imágenes por commit/digest. El build instala con exigencia de hash.
- CA-E21.1 Dado el lockfile, cuando se instala con `--require-hashes` en un entorno limpio, entonces instala solo lo
  fijado; si un hash no coincide, falla. `[LOCAL]`
- CA-E21.2 Dado un cambio en las dependencias de `pyproject.toml` sin regenerar el lockfile, cuando se ejecuta la
  comprobación, entonces falla. `[LOCAL]`
- CA-E21.3 Dada la plantilla de CI, cuando se revisa, entonces ninguna acción ni imagen usa etiqueta móvil (`@main`,
  `latest`). `[LOCAL]` (revisión estática)
- CA-E21.4 Dado el lockfile, cuando se compara con `requires-python`, entonces resuelve para la versión de build
  (DT-E3) y las ruedas existen en ambas plataformas (HV-E1). `[LOCAL]`
- **RF-E21b — Auditoría de vulnerabilidades (Debería).** Un paso opcional de los scripts audita el lockfile y registra
  el resultado sin bloquear por una alerta sin parche.

**RF-E22 — SBOM (Podría).** Cada compilación puede generar una lista de materiales (CycloneDX o SPDX, DT-E10) con
componentes y versiones del congelado, incluidos Qt y el intérprete.
- CA-E22.1 Dado el SBOM, cuando se valida con la herramienta del formato, entonces es válido y lista PySide6, Qt,
  `requests`, `urllib3`, `keyring`, `platformdirs` y el intérprete con sus versiones. `[LOCAL]`

**RF-E23 — Avisos de licencias de terceros (Debe).** El artefacto incluye `LICENSE` y `THIRD-PARTY-NOTICES` con los
textos de licencia de cada dependencia incluida (PySide6/Qt LGPL-3.0, `requests`, `urllib3`, `keyring`, `platformdirs`,
transitivas, y las OFL de las fuentes; D-19; licencias exactas a verificar, HV-E14). Qt se mantiene como **bibliotecas
dinámicas separadas y reemplazables** (no un binario único), para cumplir la LGPL-3.0 (DT-E1, R-E4).
- CA-E23.1 Dado el congelado, cuando se inspecciona, entonces `THIRD-PARTY-NOTICES` existe y su lista coincide con el
  lockfile (generado, no escrito a mano). `[LOCAL]`
- CA-E23.2 Dado el congelado, cuando se enumeran los archivos, entonces las bibliotecas de Qt están como `.dll`/`.so`
  separadas. `[LOCAL]`
- CA-E23.3 Dada la guía de construcción, cuando se lee, entonces indica cómo se obtiene el código de las partes LGPL y
  cómo reemplazar Qt [A]. `[MANUAL]`
- CA-E23.4 Dados los scripts y la plantilla de CI, cuando se revisan, entonces no publican nada en sitios públicos. `[LOCAL]`

**RF-E24 — Sin firma de código en Windows; paso de firma preparado y desactivado (Debe).** Decisión del usuario: el
MVP 5 **no firma**. (Cierra el pendiente «Firma de código en Windows» de la bitácora con esta decisión explícita.)
- El instalador y el `.exe` salen sin firmar; Windows mostrará SmartScreen («Windows protegió su PC») y editor
  «Desconocido». Se compensa con el SHA-256 de RF-E20 y la guía.
- El script de build contiene un paso de firma Authenticode **desactivado por defecto** (se activa solo si existe
  configuración explícita de certificado fuera del repositorio); sin ella, se omite con un mensaje claro. Si algún día
  se activa: la clave y su contraseña nunca van en el repositorio, en la plantilla ni en registros (RF-E35), y el
  sello de tiempo es obligatorio.
- CA-E24.1 Dado el script sin certificado configurado, cuando se ejecuta, entonces el paso de firma se omite con mensaje
  claro y el resto sigue, y el resultado se identifica como «sin firmar». `[LOCAL]`
- CA-E24.2 Dado el repositorio, cuando se busca un certificado, clave, contraseña o ruta de certificado, entonces no
  hay ninguno. `[LOCAL]`
- CA-E24.3 Dada la guía de instalación (RF-E50), cuando se lee, entonces explica qué es SmartScreen, cómo verificar el
  SHA-256 y que solo se continúa («Más información → Ejecutar de todas formas») si la suma coincide con la publicada
  por el mantenedor. `[MANUAL]`
- CA-E24.4 Dado un Windows de la MV con SmartScreen, cuando se ejecuta el instalador sin firma, entonces el
  comportamiento coincide con lo que dice la guía (o se corrige la guía). `[MANUAL]`
- **RF-E24b — Firma de los artefactos de Linux (Podría).** Firma GPG *detached* de `SHA256SUMS`; no se hace en este MVP salvo que sobre tiempo.

### 4.7 Scripts de calidad y plantilla de CI inactiva

La CI **no se activa** (decisión del usuario). Lo que se entrega: (a) scripts locales que hacen todo el trabajo
(DT-E5) y (b) una plantilla de GitHub Actions como referencia, que invoca esos mismos scripts. Ambos cumplen los
requisitos de abajo; la plantilla se verifica por revisión estática, no ejecutándola.

**RF-E30 — Plantilla de CI preparada y sin activar (Debe).** Archivo de referencia (ruta propuesta
`empaquetado/ci/github-actions.yml.plantilla`; no `.github/workflows/`, para que ningún proveedor lo ejecute por
accidente) con disparadores sobre *push* a la rama principal, PR y etiquetas `v<versión>`, y ejecución manual.
- CA-E30.1 Dado el repositorio, cuando se busca `.github/workflows/`, `.gitlab-ci.yml` u otro archivo de CI activo,
  entonces no existe ninguno. `[LOCAL]`
- CA-E30.2 Dada la plantilla, cuando se revisa estáticamente, entonces es YAML válido, solo invoca scripts de
  `empaquetado/` (no duplica lógica) y declara los disparadores indicados. `[LOCAL]`
- CA-E30.3 Dado el README o la guía de construcción, cuando se leen, entonces explican cómo activar la plantilla si algún
  día hay remoto (copiarla a la ruta que lee el proveedor). `[MANUAL]`

**RF-E31 — Matriz Ubuntu y Windows (Debe).** Tanto la plantilla como la ejecución local cubren los dos sistemas.
Local: calidad y pruebas en el equipo Ubuntu (y en contenedores 22.04 y 24.04) con Python 3.11 (mínimo) y la versión
de build (DT-E3), y en la MV Windows de evaluación; el build de Linux en base 22.04. Plantilla: ídem con runners
`ubuntu-22.04`, `ubuntu-24.04` y Windows 64 bits (HV-E6, HV-E8).
- CA-E31.1 Dado el cierre del MVP, cuando se revisa el registro de ejecuciones locales, entonces existe una ejecución
  completa (calidad, build, humo y sumas) en Ubuntu 22.04 y 24.04 y otra en Windows (MV), todas con éxito. `[LOCAL]`
- CA-E31.2 Dada la plantilla, cuando se revisa, entonces define una matriz con al menos Ubuntu y Windows. `[LOCAL]`
- CA-E31.3 Dado que Windows 10 es solo prueba opcional, cuando se cierra el MVP, entonces las comprobaciones `[MANUAL]`
  de la sección 9 se registran en la bitácora, con las que quedaron sin hacer indicadas como pendientes. `[MANUAL]`

**RF-E32 — Pasos de calidad (Debe).** Un script de calidad (y la plantilla, que lo invoca) ejecuta en este orden, y
cada paso falla el script si falla:
1. instalación desde el lockfile con hashes (RF-E21) más el extra `dev`;
2. `ruff check src tests`;
3. `ruff format --check`;
4. `mypy src`;
5. `pytest -q -m "not integracion"` con `QT_QPA_PLATFORM=offscreen` (DT-E11) y las opciones de `pyproject.toml`
   (`--disable-socket --allow-unix-socket`);
6. cobertura con los mínimos documentados (85 % `proxlaunch.nucleo`, 75 % global).
- CA-E32.1 Dado un error de estilo, tipos o una prueba rota, cuando se ejecuta el script, entonces falla y no se
  construye ningún artefacto. `[LOCAL]`
- CA-E32.2 Dado un árbol sano, cuando se ejecuta, entonces pasan los pasos del encargo con el mismo resultado que a mano
  (~7200 pruebas). `[LOCAL]`
- CA-E32.3 Dada la suite en Windows (MV), cuando se ejecuta, entonces las pruebas específicas de POSIX ya existentes
  se saltan o pasan según su marca actual, sin saltos nuevos sin justificar [A]. `[LOCAL]`
- CA-E32.4 Dado el catálogo de traducción, cuando corre la verificación (`lupdate` sin cambios), entonces no deja el `.ts`
  modificado. `[LOCAL]` (Debería)

**RF-E33 — Las pruebas de laboratorio nunca corren desde los scripts ni la plantilla (Debe, D-15).** No definen
`PROXLAUNCH_LAB`, no usan `--force-enable-socket` y ejecutan explícitamente `-m "not integracion"`. Un paso de guarda
verifica que esa variable no esté definida y que ninguna prueba `integracion` se ejecute. No hay secretos ni datos de
Proxmox en los scripts.
- CA-E33.1 Dados los scripts y la plantilla, cuando se busca `PROXLAUNCH_LAB` o `force-enable-socket`, entonces solo
  aparecen en la guarda que los **prohíbe**. `[LOCAL]` (revisión estática)
- CA-E33.2 Dada la ejecución, cuando termina, entonces 0 pruebas `integracion` se ejecutaron (sí deseleccionadas). `[LOCAL]`
- CA-E33.3 Dado un intento de una prueba por abrir un socket externo, cuando corre el script, entonces falla por
  `pytest-socket`. `[LOCAL]`

**RF-E34 — Construcción condicionada a la calidad (Debe).** El script de build exige que calidad (RF-E32) y humo
(RF-E18) hayan pasado. Los artefactos y `SHA256SUMS` quedan en `dist/`.
- CA-E34.1 Dado un fallo en calidad, cuando se ejecuta el script completo, entonces no se construye ni se escribe nada en
  `dist/`. `[LOCAL]`
- CA-E34.2 Dada la ejecución correcta, cuando termina, entonces `dist/` contiene el `-setup.exe` (en Windows) o el `.deb`
  (en Ubuntu), `SHA256SUMS` y el SBOM si RF-E22. `[LOCAL]`

**RF-E35 — Sin secretos en los registros (Debe).** Aunque este MVP no firma ni hay CI activa, las reglas valen para los
scripts, los registros que producen y la plantilla (para cuando se active): sin secretos literales; no se activa
el modo de traza del shell (`set -x`, `Set-PSDebug -Trace`) ni se vuelca el entorno (`env`, `printenv`,
`Get-ChildItem Env:`); permisos mínimos del token en la plantilla (solo lectura); ejecuciones desde forks sin
secretos; los registros no incluyen datos personales evitables.
- CA-E35.1 Dados los scripts y la plantilla, cuando se revisan estáticamente, entonces ningún secreto aparece como
  literal, ningún paso usa trazas del shell ni vuelca el entorno, y los permisos del token son de solo lectura. `[LOCAL]`
- CA-E35.2 Dado el registro completo de una ejecución local de build y verificación, cuando se busca con un patrón de
  secretos (claves, contraseñas, tokens) y con el nombre de usuario del equipo, entonces no aparecen. `[LOCAL]`
- CA-E35.3 Dado el repositorio, cuando se busca con un detector de secretos (DT-E12), entonces no encuentra claves, tokens
  ni certificados. `[LOCAL]` (Debería)

**RF-E36 — Caché opcional (Podría).** Los scripts pueden reutilizar la caché local de `pip` y de descargas verificadas
por hash; la plantilla puede declarar caché con clave que incluya el hash del lockfile, la versión de Python y el SO.
Una caché perdida o corrupta nunca cambia el resultado ni hace fallar el script.
- CA-E36.1 Dadas una ejecución con caché y otra sin, cuando se comparan, entonces ambas pasan y los artefactos tienen el
  mismo contenido funcional (humo OK, tamaño ± 1 %). `[LOCAL]`
- CA-E36.2 Dado un cambio del lockfile, cuando se ejecuta, entonces la caché no se reutiliza. `[LOCAL]`

**RF-E37 — Duración y estabilidad (Debería).** Calidad completa ≤ 20 min por SO y build+humo ≤ 30 min por SO [A]; los
pasos largos tienen tiempo máximo; los fallos intermitentes se investigan, no se reintentan a ciegas.
- CA-E37.1 Dadas 5 ejecuciones locales, cuando se mide, entonces cada una acaba en el tiempo indicado. `[LOCAL]`

### 4.8 Entorno de pruebas local

**RF-E40 — MV Windows 11 de evaluación local con KVM/QEMU, TPM 2.0 emulado y Secure Boot (Debe).** Para construir y
probar el instalador de Windows se crea **una MV de evaluación en este equipo** con `qemu-system-x86_64`, `qemu-img`,
aceleración KVM, firmware **OVMF con claves de Secure Boot (`.ms.fd`)** y **TPM 2.0 emulado con `swtpm`** (S-E6), de modo
que Windows 11 se instala **sin saltarse ninguna comprobación** de requisitos. Windows 10 queda como prueba `[MANUAL]`
opcional (M-E1). Reglas:
- `swtpm` arranca como usuario normal, sin `sudo`; su **socket Unix (unixio) está en un directorio temporal de ruta
  corta (< 108 caracteres)** (S-E8), nunca en una carpeta larga como la del scratchpad; el **estado del TPM**
  (`swtpm_setup`) vive en una carpeta propia de la MV, también fuera del repositorio.
- Red: solo traducción de direcciones de usuario (*user-mode networking*), sin puente hacia la red real, y puertos
  reenviados enlazados únicamente a `127.0.0.1`. Nunca se conecta a un Proxmox de producción (D-15, INV-E1).
- Archivos de la MV (disco, ISO, variables UEFI, estado del TPM, instantáneas) en una carpeta **fuera del repositorio**
  [A] (p. ej. `~/aprovprox-win-eval`, igual que el laboratorio); nada de la MV se añade a git.
- El código se pasa a la MV con un medio que no exponga secretos (archivo comprimido del árbol limpio o carpeta
  compartida de solo lectura) [A]; los artefactos y registros vuelven a `dist/` y a una carpeta de resultados.
- Sin acceso a `root@pam`/SSH de ningún Proxmox, ni credenciales reales dentro de la MV (CA-E09.4 usa un servicio de
  prueba).
- CA-E40.1 Dado el equipo, cuando se arranca la MV, entonces usa aceleración KVM y no consume más de la RAM y el disco
  presupuestados [A: ≤ 8 GB de RAM y ≤ 80 GB de disco; sobra margen respecto de los 16 GB y 295 GB libres]. `[LOCAL]`
- CA-E40.2 Dada la MV en marcha, cuando se listan los sockets de escucha del anfitrión asociados a QEMU, entonces solo
  hay direcciones `127.0.0.1`; el socket de `swtpm` es Unix y de ruta corta. `[LOCAL]`
- CA-E40.3 Dada la MV Windows 11, cuando arranca el instalador de Windows con el TPM emulado y OVMF con claves de
  Secure Boot, entonces la instalación no exige saltarse la comprobación de TPM/Secure Boot y el sistema informa TPM 2.0
  y Secure Boot activos. `[MANUAL]`
- CA-E40.4 Dada la MV, cuando se ejecutan en ella los scripts de calidad, build y humo para Windows, entonces pasan
  (RF-E31, CA-E31.1). `[LOCAL]`
- CA-E40.5 Dado el cierre del MVP, cuando se revisa, entonces están registrados en la bitácora los resultados de las
  comprobaciones de la sección 9 hechas en la MV y las que no se pudieron hacer. `[MANUAL]`

**RF-E40b — Ubuntu 22.04 y 24.04 en contenedores o MVs locales (Debe).** El `.deb` se prueba en contenedores con
`xvfb` y D-Bus (instalar, humo, desinstalar, `apt purge`) y, si hace falta comprobar menú, icono, Wayland o llavero
con escritorio real, en MVs locales de Ubuntu 22.04 y 24.04 (con las mismas reglas de red y limpieza que RF-E40/E41).
- CA-E40b.1 Dado cada Ubuntu (22.04 y 24.04), cuando se ejecuta el script de verificación, entonces completa RF-E18 y
  RF-E13 sin intervención. `[LOCAL]`
- CA-E40b.2 Dado un contenedor, cuando termina la verificación, entonces se destruye (contenedor, imagen base propia
  y volúmenes creados para la prueba). `[LOCAL]`

**RF-E41 — Limpieza total de lo creado para las pruebas (Debe).** Al terminar el MVP (o cuando el usuario lo pida) se
elimina **sin rastro** todo lo creado, igual que el laboratorio de Proxmox (D-15), y se deja un registro de lo borrado.
- Procesos: ningún proceso de QEMU, **ningún proceso `swtpm`**, de visores o de contenedores de prueba queda en
  ejecución.
- Archivos: discos de la MV (`qcow2`/`raw`), instantáneas, copias de OVMF/variables UEFI, **el estado del TPM y su
  directorio**, **el socket temporal de `swtpm` y su directorio corto**, la ISO de evaluación y su suma, carpetas
  compartidas y temporales, y la carpeta de la MV entera.
- Puertos: ningún puerto de escucha de la MV queda abierto en el anfitrión.
- Contenedores e imágenes: los creados para la prueba (RF-E40b).
- Permisos: ningún cambio de permisos, grupos ni reglas de red en el anfitrión que no existiera antes (no se añaden
  grupos; `/dev/kvm` ya es accesible, S-E6); si hubiese alguno, se revierte.
- El repositorio no contiene referencias a la MV (rutas, claves, ISO) y `dist/` solo conserva los artefactos que el
  mantenedor decida conservar.
- CA-E41.1 Dada la limpieza, cuando termina, entonces `ps` no muestra procesos de QEMU, `swtpm` ni contenedores de
  prueba y `ss -ltnp` no muestra puertos de la MV. `[LOCAL]`
- CA-E41.2 Dada la limpieza, cuando termina, entonces la carpeta de la MV, la ISO, el estado del TPM y el directorio del
  socket temporal no existen y `qemu-img`/`find` no hallan discos de la prueba. `[LOCAL]`
- CA-E41.3 Dada la limpieza, cuando termina, entonces `docker`/`podman` (el que se haya usado) no listan contenedores,
  imágenes ni volúmenes de la prueba. `[LOCAL]`
- CA-E41.4 Dada la limpieza, cuando termina, entonces el estado de grupos y reglas de red del anfitrión es el previo. `[LOCAL]`
- CA-E41.5 Dado el cierre, cuando se revisa la bitácora, entonces consta la limpieza (fecha y lo eliminado) y se añade
  un punto equivalente al de «Eliminación del laboratorio» en la tabla de pendientes mientras la MV exista. `[MANUAL]`

**RF-E42 — Origen y verificación de la ISO de Windows (Debe).** Solo se descarga la **ISO oficial de evaluación** de
Windows 11 (y, si se hace la prueba opcional, de Windows 10) desde el sitio oficial de Microsoft; no se usan ISOs de
terceros, ni cracks, ni claves de activación ajenas. Se verifica contra el valor de integridad oficial disponible (suma
publicada o firma) antes de usarla; si Microsoft no publica una suma, se registra la suma calculada localmente y el
origen (HV-E16). La edición de evaluación tiene caducidad (HV-E17) y no se usa para nada más que estas pruebas. La ISO
no entra en el repositorio ni se redistribuye.
- CA-E42.1 Dado el archivo descargado, cuando se calcula su SHA-256, entonces coincide con el valor oficial (o, si no
  hay valor oficial, queda registrado junto con la URL oficial y la fecha). `[LOCAL]`
- CA-E42.2 Dado el repositorio, cuando se busca la ISO, su suma o su URL con parámetros personales, entonces no hay
  ISO ni datos personales; solo se permiten referencias genéricas en la guía de construcción. `[LOCAL]`
- CA-E42.3 Dada la licencia de evaluación, cuando se instala, entonces se aceptan los términos de Microsoft por una
  persona (no se automatiza la aceptación en nombre del usuario) y se anota la caducidad. `[MANUAL]`

### 4.9 Documentación

**RF-E50 — Guía de instalación (Debe).** Sección nueva de `docs/guia-usuario.md` y enlace desde el README (que hoy dice
«Por ahora se ejecuta desde el código fuente»), en español y sin jerga:
- Descarga y verificación del SHA-256 (`Get-FileHash`, `sha256sum -c`).
- Windows: instalación paso a paso, elección de ámbito, aviso de SmartScreen (RF-E24), accesos directos, actualización,
  desinstalación y qué pasa con los datos (casilla «Borrar también mis datos»).
- Ubuntu: `sudo apt install ./proxlaunch_<versión>_amd64.deb`, dependencias de sistema (`libxcb-cursor0`, HV-E3),
  desinstalación (`apt remove`) y que `purge` no borra los datos del usuario.
- Llavero: qué hace sin servicio de secretos y cómo quitar secretos (RF-E13, CA-E13.6).
- Dónde están los datos de usuario por SO y cómo respaldarlos o borrarlos a mano.
- Requisitos del sistema; ya no hace falta Python (la nota «Ubuntu 22.04 trae Python 3.10…» pasa a ser solo de
  *desarrollo*).
- CA-E50.1 Dada una persona sin conocimientos técnicos, cuando sigue la guía en la MV Windows y en un Ubuntu limpio,
  entonces instala, abre y desinstala sin ayuda. `[MANUAL]`
- CA-E50.2 Dados los comandos de la guía, cuando se ejecutan tal cual, entonces funcionan. `[MANUAL]`
- CA-E50.3 Dado el README, cuando se lee, entonces su «Estado del proyecto», la tabla «Requisitos» y los enlaces a esta
  guía y a estos requisitos están al día (incluye la versión 0.5.0). `[MANUAL]`

**RF-E51 — Guía de construcción para mantenedores (Debe).** Documento (p. ej. `docs/empaquetado.md`; nombre final a
cargo de la arquitectura) con: construcción local en cada SO, requisitos previos, creación y **limpieza** de la MV de
evaluación con su TPM (RF-E40 a RF-E42, incluida la regla del socket corto), cómo publicar una versión (etiqueta, orden
de pasos, copia manual de `dist/`), cómo actualizar el lockfile y el presupuesto de tamaño, cómo activar la plantilla de
CI y cómo activar el paso de firma si algún día se decide, y qué hacer si falla la prueba de humo.
- CA-E51.1 Dado el documento, cuando un desarrollador lo sigue en limpio, entonces obtiene un artefacto que pasa la
  prueba de humo. `[MANUAL]`

---

## 5. Requisitos no funcionales

- **RNF-E01 — Reproducibilidad (Debe).** Mismas entradas fijadas → mismo contenido funcional (RF-E04, RF-E21).
- **RNF-E02 — Privilegios mínimos (Debe).** En Windows, por defecto sin administrador (instalación por usuario); el
  `.deb` sí pide administrador (instalación de sistema). La app **nunca** se ejecuta como administrador/`root`; el
  instalador no deja servicios, tareas programadas ni entradas de arranque. [A]
- **RNF-E03 — Sin red sin acción del usuario (Debe).** Instalar, abrir y el humo no hacen conexiones salientes (D-18; sin
  telemetría ni búsqueda de actualizaciones).
- **RNF-E04 — Idioma (Debe).** Asistentes, mensajes del instalador, `.desktop`, descripción del paquete y guías en español
  (D-04).
- **RNF-E05 — Seguridad de los scripts (Debe).** Sin `curl | sh` ni descargas de binarios sin verificar hash; no ejecutan
  nada de datos de terceros.
- **RNF-E06 — Rutas (Debe).** Funciona con rutas con espacios, tildes y eñes (CL-E1).
- **RNF-E07 — Mantenibilidad (Debería).** La lógica vive en scripts del repositorio; la plantilla solo orquesta (DT-E5).
- **RNF-E08 — Accesibilidad del instalador (Debería).** Controles estándar del sistema en el asistente de Windows [A].
- **RNF-E09 — Registro (Debe).** La app congelada escribe su registro rotativo en la carpeta de `platformdirs` como hoy,
  sin secretos.
- **RNF-E10 — Aislamiento del entorno de pruebas (Debe).** Las MVs y contenedores de prueba no se conectan a ningún
  Proxmox ni a redes de producción y no dejan huella (RF-E40, RF-E41; D-15).

---

## 6. Casos límite

- **CL-E1** Usuario o ruta con tildes, espacios o eñes («José Núñez»); instalación en otra unidad.
- **CL-E2** Perfil de usuario en OneDrive/redirección de carpetas o perfil móvil.
- **CL-E3** Windows en modo S, edición N, Home sin directivas; antivirus corporativo que bloquea ejecutables sin firma o
  marca falsos positivos (HV-E10).
- **CL-E4** Usuario sin permisos de administrador y con ellos; instalación para todos los usuarios con datos por usuario
  separados.
- **CL-E5** Dos usuarios en el mismo equipo: cada uno con sus perfiles y su llavero; desinstalar con la casilla solo
  borra los del usuario que desinstala.
- **CL-E6** Ubuntu sin escritorio o por SSH sin pantalla: el mensaje de Qt debe entenderse o la guía lo describe.
- **CL-E7** Wayland vs X11; `xcb` sin `libxcb-cursor0`; Snap/Flatpak que aíslan el llavero.
- **CL-E8** Sin servicio de secretos o con el llavero bloqueado (CA-E09.3).
- **CL-E9** Instalar encima con la app abierta; desinstalar con la app abierta; reinstalar la misma versión; bajar de versión.
- **CL-E10** Windows sin Visual C++ Redistributable ni actualizaciones recientes (UCRT).
- **CL-E11** Escalado fraccionario (125, 150, 175 %), monitores con escalado distinto, pantalla de 1366×768.
- **CL-E12** Descarga corrupta (la suma lo detecta); «Marca de la Web» de Windows (Zone.Identifier).
- **CL-E13** Rutas largas de Windows (> 260 caracteres) en instalación o temporal, y «archivo bloqueado» (pendientes de
  MVP 3 en Windows real): se aprovecha la MV para probarlos.
- **CL-E14** Datos de una versión anterior con formato más antiguo al actualizar (los archivos llevan `app_version`).
- **CL-E15** Reloj del sistema erróneo (en la MV, desfase de hora; afecta también a la edición de evaluación).
- **CL-E16** Instalador ejecutado desde una ruta de red (UNC) o desde el navegador sin guardar.
- **CL-E17** Proxy corporativo al descargar dependencias en el build (la app ignora el proxy, D-18, y eso no cambia).
- **CL-E18** La edición de evaluación de Windows caduca o reinicia periódicamente (HV-E17): el plan de pruebas lo
  considera.
- **CL-E19** Disco o RAM insuficiente en el anfitrión durante la prueba (CA-E40.1) o QEMU sin KVM por permisos.
- **CL-E20** Limpieza interrumpida a medias: el script de limpieza es idempotente y puede repetirse.
- **CL-E21** Ruta del socket de `swtpm` demasiado larga («Path for UnioIO socket is too long»): el script la valida antes
  de arrancar y usa un directorio temporal corto (S-E8).
- **CL-E22** Un `swtpm` o QEMU huérfano tras un fallo: la limpieza lo detecta por proceso y por socket, no solo por archivos.

---

## 7. Invariantes

- **INV-E1:** nada de los scripts, la plantilla ni los entornos de prueba toca un Proxmox real o de laboratorio (D-15).
- **INV-E2:** ningún artefacto contiene secretos, rutas personales ni datos del desarrollador (CA-E19.2 y escaneo de
  cadenas `[LOCAL]`, Debería).
- **INV-E3:** el servicio del llavero (`ProxLaunch`) y los nombres de carpetas de datos no cambian entre versiones (CA-E14.4).
- **INV-E4:** el logotipo no se cambia (D-01); los iconos son conversión del símbolo aprobado, con revisión del usuario
  antes de integrarlos (CA-E11.4).
- **INV-E5:** el comportamiento de la app en modo normal no cambia (CA-E17.5).
- **INV-E6:** el artefacto publicado es exactamente el que pasó el humo; solo entonces se escribe su suma (CA-E18.2).
- **INV-E7:** el llavero del usuario nunca se modifica al instalar, actualizar o desinstalar (RF-E13).
- **INV-E8:** lo creado para las pruebas (MV, ISO, TPM, sockets, contenedores) se elimina sin rastro al final (RF-E41).

---

## 8. Trazabilidad con D-06, D-19, D-15 y la bitácora

| Origen | Requisito |
|---|---|
| D-06 Ubuntu 22.04 y 24.04 LTS (AppImage o .deb) | RF-E02 (solo `.deb`; AppImage fuera por decisión), RF-E03, RF-E05, RF-E12 |
| D-06 Windows 10 y 11 64 bits, .exe con asistente | RF-E01, RF-E05, RF-E11, RF-E15 |
| D-06 macOS fuera | Fuera del alcance (1.3) |
| D-06 `keyring` para secretos | RF-E09, RF-E13, INV-E7 |
| D-06 `platformdirs` para rutas | RF-E13, RF-E14, INV-E3, CA-E17.2 |
| D-06 fuentes incluidas | RF-E06, RF-E16 |
| D-06 escalado de alta resolución en Windows | RF-E15 |
| D-06 compilación por sistema operativo en CI | RF-E04, RF-E30, RF-E31, RF-E34 (CI como plantilla inactiva y scripts locales por SO, decisión del usuario) |
| D-06 firma de código pospuesta al MVP 5 | RF-E24 (resuelta: sin firma; paso preparado y desactivado) |
| D-04 español con traducción de Qt | RF-E07, RNF-E04 |
| D-19 licencia (uso interno, LGPL-3.0, OFL) | RF-E23, S-E1, 1.3 |
| D-15 sin Proxmox de pruebas; laboratorio fuera de CI; limpieza sin rastro | RF-E33, RF-E40, RF-E41, INV-E1, INV-E8 |
| D-18 sin proxy ni red implícita | RNF-E03, CL-E17, RF-E17 |
| Bitácora: Python en Ubuntu 22.04 | RF-E03, CA-E03.1 |
| Bitácora: Firma de código en Windows | RF-E24 |
| Bitácora: Windows real (archivo bloqueado, rutas largas) | CL-E13, RF-E40, sección 9 |

---

## 9. Verificación manual en equipos reales o MVs `[MANUAL]`

Con el resultado anotado en la bitácora antes de cerrar el MVP 5:

| # | Comprobación | En | Requisitos |
|---|---|---|---|
| M-E1 | Instalar, abrir, actualizar y desinstalar con el asistente | MV Windows 11 de evaluación (TPM 2.0 y Secure Boot); **Windows 10 opcional** | RF-E01, E11, E13, E14, E40 |
| M-E2 | Arranque sin Visual C++ instalado | MV Windows 11 (y Windows 10 si se hace la opcional) | RF-E05, CL-E10 |
| M-E3 | Escalado 125/150/175 % (monitores mixtos solo en equipo físico) | MV Windows | RF-E15 |
| M-E4 | Credenciales en el Administrador de credenciales; «archivo bloqueado» y rutas largas (pendiente de MVP 3) | MV Windows | RF-E09, CL-E13 |
| M-E5 | Aviso de SmartScreen sin firma y texto de la guía | MV Windows | RF-E24 |
| M-E6 | Instalar, abrir, actualizar y desinstalar `.deb` con menú e icono | MV Ubuntu 22.04 y 24.04 con escritorio (X11 y Wayland si es posible) | RF-E02, E12, E13 |
| M-E7 | Llavero (GNOME Keyring) y sin llavero | Ubuntu | RF-E09 |
| M-E8 | Revisión visual de iconos por el usuario (CA-E11.4) | vista previa | RF-E11, RF-E12 |
| M-E9 | Seguir la guía sin ayuda | ambos | RF-E50 |
| M-E10 | TPM 2.0 y Secure Boot activos en la MV, sin saltarse comprobaciones | MV Windows 11 | CA-E40.3 |

---

## 10. Riesgos

| ID | Riesgo | Prob. / impacto [A] | Mitigación |
|---|---|---|---|
| R-E1 | El congelador pierde recursos, plugins o metadatos de `keyring` y la app falla solo en el artefacto. | Alta / Alto | Humo sobre el instalado (RF-E17/E18) con comprobación expresa de backend, `.qm`, fuentes e icono. |
| R-E2 | Falsos positivos de antivirus y SmartScreen por no firmar. | Media-alta / Medio | SHA-256, guía (RF-E24), considerar Nuitka (DT-E1); paso de firma ya preparado. |
| R-E3 | `libxcb-cursor0` o la sesión Wayland impiden abrir en Ubuntu 24.04. | Media / Alto | Dependencia declarada en el `.deb`, guía, MV con escritorio. |
| R-E4 | Incumplir la LGPL de Qt al fundir bibliotecas. | Baja / Alto | Congelado en directorio con Qt separado (CA-E23.2). |
| R-E5 | **No hay CI remota.** Windows 10 y la edición Home/Pro solo en prueba opcional (la MV usa la edición de evaluación de Windows 11); monitores mixtos solo en equipo físico; Ubuntu con escritorio solo en MV. Defectos específicos pueden aparecer tarde. | Media / Medio | Sección 9; anotar en la bitácora lo no probado, como se hizo con otros pendientes. |
| R-E6 | Sin CI activa, nada obliga a ejecutar los scripts. | Media / Medio | Un script «verificar todo» y regla de ejecutarlo antes de cada versión; plantilla lista. |
| R-E7 | Firma futura: manejo inseguro de claves. | Baja / Muy alto | RF-E24 y RF-E35 ya fijan las reglas. |
| R-E8 | Dependencias transitivas cambian entre builds; sin rueda para la versión de Python o SO (3.14 en el desarrollo). | Media / Medio | Lockfile con hashes, HV-E1, DT-E3. |
| R-E9 | Tamaño excesivo (Qt es grande). | Media / Medio | RF-E19, exclusión de módulos, medición continua. |
| R-E10 | Credenciales huérfanas tras desinstalar en equipos compartidos. | Media / Medio | Guía (CA-E13.6); la app ya borra el secreto al borrar el perfil o desmarcar «Recordar». |
| R-E11 | Cambiar el servicio de llavero o las carpetas rompe actualizaciones. | Baja / Alto | INV-E3, CA-E14.4. |
| R-E12 | La suite nunca se corrió en Windows real: pruebas dependientes de POSIX o de Qt. | Media / Medio | CA-E32.3; corregir por el `probador`, no relajar. |
| R-E13 | El modo de humo exige cambiar `app.py` (H13). | Baja / Medio | INV-E5, CA-E17.5, mínima intrusión. |
| R-E14 | La MV de evaluación deja restos (disco, TPM, sockets, procesos `swtpm`/QEMU), ocupa recursos o se conecta donde no debe. | Media / Medio | RF-E40 (red solo local), RF-E41 (limpieza total, incluido el TPM), RNF-E10. |
| R-E15 | Licencia y caducidad de la edición de evaluación de Windows; ISO de origen dudoso. | Baja / Medio | RF-E42; solo ISO oficial verificada, sin redistribuir. |
| R-E16 | Rendimiento de la MV (KVM no disponible o poca RAM) hace lentas las pruebas. | Baja / Bajo | CA-E40.1; ajustar presupuesto. |
| R-E17 | Windows 11 en QEMU puede exigir ajustes (CPU, TPM, Secure Boot) y su instalación consume tiempo. | Media / Bajo | HV-E18, CA-E40.3; documentar el procedimiento en la guía de construcción (RF-E51). |

---

## 11. Hipótesis a verificar (HV)

No son hechos; el implementador o el investigador deben comprobarlas antes de apoyarse en ellas.

| ID | Hipótesis | Cómo verificar |
|---|---|---|
| HV-E1 | Existen ruedas de `PySide6-Essentials>=6.11`, `requests`, `urllib3`, `keyring`, `platformdirs` y transitivas para la versión de Python de build (DT-E3) en Windows 10/11 x64 y en manylinux compatible con Ubuntu 22.04; Qt 6.11 admite Windows 10. | `pip download --only-binary=:all:`; notas de versión de Qt. |
| HV-E2 | `PySide6-Essentials` trae la herramienta para compilar `.ts` a `.qm` (`lrelease`), como trae `lupdate`. | Buscar el binario en la rueda; si falta, `pyside6-lrelease` o el paquete `PySide6` completo solo en el build. |
| HV-E3 | Con Qt ≥ 6.5 el plugin `xcb` necesita `libxcb-cursor0`, que no viene en una instalación estándar de Ubuntu (H17). | Contenedor/MV limpios 22.04 y 24.04. |
| HV-E5 | `keyring` elige backend por puntos de entrada de los metadatos de los paquetes; el congelador debe incluirlos; en Windows requiere `pywin32-ctypes`; en Linux `SecretStorage`/`jeepney`. | Congelar, ejecutar el humo y mostrar `keyring.get_keyring()`. |
| HV-E6 | Los runners de Windows de los proveedores son Windows Server, no Windows 10/11 de escritorio (solo afecta a la plantilla). | Documentación del proveedor si se activa. |
| HV-E7 | El congelador propuesto (DT-E1) tiene soporte para PySide6 6.11, `keyring`, `importlib.resources` y la versión de Python elegida. | Notas de versión y una prueba de congelado. |
| HV-E8 | Si se activa la plantilla, el proveedor ofrece runners de Ubuntu 22.04/24.04 y Windows (los antiguos se retiran con el tiempo). | Documentación del proveedor; alternativa: contenedor 22.04. |
| HV-E10 | Los ejecutables PyInstaller son propensos a falsos positivos de antivirus; Nuitka menos. | Análisis interno de prueba. |
| HV-E11 | En Wayland, el icono del dock se asocia al `.desktop` mediante el `desktop-file-name` de la aplicación Qt (hoy no se establece). | Prueba manual en 24.04 con Wayland. |
| HV-E12 | Qt 6 en Windows declara DPI por monitor al arrancar; el manifiesto del `.exe` puede además declararlo. | Inspeccionar el manifiesto del `.exe`. |
| HV-E13 | Las cifras de tamaño de RF-E19 son razonables para PySide6 sin módulos extra. | Primera medición real. |
| HV-E14 | Las licencias de las dependencias son las esperadas (Apache-2.0/MIT, LGPL-3.0 para Qt) y compatibles con la distribución interna. | Inventario generado desde el lockfile. |
| HV-E16 | Microsoft publica una suma o firma verificable de la ISO de evaluación en su sitio oficial. | Página oficial de descarga de evaluación. |
| HV-E17 | La edición de evaluación de Windows funciona un período limitado (p. ej. 90 días) y, al caducar, reinicia o limita el uso. | Términos de la evaluación al descargar. |
| HV-E18 | Windows 11 de evaluación se instala y arranca en QEMU/KVM con `swtpm` (TPM 2.0), OVMF `.ms.fd` y un perfil de CPU, RAM (≥ 4 GB) y disco (≥ 64 GB) que cumplan sus requisitos mínimos, con controladores emulados o VirtIO aportados de forma verificada. | Prueba de instalación en la MV; documentación de Microsoft. |

(Se eliminaron HV-E4 (FUSE de AppImage), HV-E9 (SmartScreen/certificados, sin firma en este MVP) y HV-E15
(Windows 11 sin TPM; sustituida por S-E6/S-E8 al comprobar el orquestador que `swtpm` funciona). Los números no se
reutilizan.)

---

## 12. Decisiones técnicas del analista (DT-E)

Confirmadas por el orquestador salvo lo que cambian las decisiones del usuario.

**DT-E1 — Herramienta de congelado (confirmada: PyInstaller `--onedir`).** Alternativas consideradas: PyInstaller
(onedir; la más extendida con PySide6; hooks y `copy_metadata` para `keyring`; Qt separado, LGPL; contra: falsos
positivos de antivirus, no reproducible bit a bit por defecto); Nuitka `standalone` vía `pyside6-deploy` (nativo, menos
falsos positivos [A]; pero exige compilador C, más lento y su modo onefile esconde Qt); cx_Freeze (menos hooks para
PySide6); Briefcase (convenciones propias, cambia el repo); Python embebido manual (control total, más trabajo).
Nuitka queda como reserva si R-E2 es un problema real, ahora más probable al no firmar. No usar *onefile*.

**DT-E2 — Formato en Ubuntu (resuelta: solo `.deb`).** Por decisión del usuario; AppImage fuera del alcance. El `.deb`
empaqueta el congelado en `/opt/proxlaunch` (el Python del sistema no interviene) y declara dependencias de sistema.

**DT-E3 — Versión de Python del congelado.** Una sola, fija, ≥ 3.11, con ruedas en ambas plataformas (HV-E1).
Recomendación: una versión estable intermedia (p. ej. 3.12 o 3.13), no la 3.14 del desarrollo mientras no se compruebe;
los scripts prueban también con 3.11 (mínimo declarado).

**DT-E4 — Instalador de Windows (confirmada: Inno Setup).** Asistente en español, desinstalador, ámbito por usuario o
equipo con pregunta (`PrivilegesRequiredOverridesAllowed`, por usuario por defecto [A]), instalación silenciosa,
casilla de borrado de datos en el desinstalador (vía código del script), paso de firma integrable (desactivado).
NSIS, WiX/MSI y MSIX descartados (MSIX además cambia las rutas de datos, incompatible con S-E4 [A]).

**DT-E5 — Scripts neutros respecto del proveedor (reforzada).** Toda la lógica en `empaquetado/` (nombre final a cargo de
la arquitectura); la plantilla de CI (`empaquetado/ci/github-actions.yml.plantilla`) solo invoca los scripts. Un
script «verificar todo» encadena calidad, build, humo y sumas (R-E6).

**DT-E6 — Fuente única de la versión.** `proxlaunch.__version__` es la fuente; `pyproject.toml` la lee
(`dynamic = ["version"]`, `[tool.setuptools.dynamic] version = {attr = "proxlaunch.__version__"}`); una prueba compara
con la etiqueta y los metadatos. Se pasa de `0.1.0` a `0.5.0`.

**DT-E7 — `.qm` como producto del build.** No se versiona; se añade `*.qm` a `.gitignore` [A]; la app sigue funcionando
sin él en desarrollo (H5).

**DT-E8 — Bloqueo de dependencias.** `pip-tools` (`pip-compile --generate-hashes`) + `pip install --require-hashes`;
un lockfile por plataforma si difieren (Windows trae `pywin32-ctypes`; Linux `jeepney`). Alternativa: `uv`.

**DT-E9 — Iconos.** Se generan en el build (o se versionan como derivados) desde el **símbolo sin texto** aprobado
(SVG de marca y `boton-icono-favicon.png`) con una herramienta determinista, sin retoques; la integración espera la
revisión de CA-E11.4.

**DT-E10 — SBOM.** CycloneDX preferido [A]; opcional.

**DT-E11 — Pruebas en Windows.** `QT_QPA_PLATFORM=offscreen` en ambos SO para la suite; el plugin real solo en el humo.

**DT-E12 — Detector de secretos y auditoría.** Herramientas de código abierto estándar (p. ej. `gitleaks` o
`detect-secrets`, `pip-audit`), con versión y hash fijados.

**DT-E13 — Humo en Linux.** `xvfb-run` con el plugin `xcb` real y una pasada `offscreen`; bloqueo de red con
`unshare -n`. En Windows, sesión de escritorio de la MV con red desconectada [A].

**DT-E14 — MV de Windows 11 con TPM emulado (reescrita).** Windows 11 de evaluación sobre QEMU/KVM con UEFI OVMF
(`.ms.fd`, Secure Boot) y `swtpm` (TPM 2.0) por socket Unix de ruta corta, sin saltarse comprobaciones (RF-E40, S-E8,
HV-E18). Un script único crea y otro destruye todo el entorno; ambos idempotentes (CL-E20) y con la limpieza del TPM y
de los procesos `swtpm` (RF-E41). Discos y red emulados por defecto (más lentos pero sin controladores externos);
VirtIO solo si se aportan de forma verificada [A]. Windows 10 queda como prueba `[MANUAL]` opcional, no necesaria
para cerrar el MVP.

**DT-E15 — Entorno de contenedores.** Para Ubuntu 22.04/24.04, usar el motor de contenedores ya disponible en el
equipo; si no hay ninguno utilizable sin `sudo`, caer a MVs locales con QEMU y las mismas reglas de RF-E40/E41 [A:
no se verificó qué motor hay instalado].

---

## 13. Cambios mínimos en el código de la app que implican estos requisitos

(Para que la arquitectura los tenga en cuenta; este documento no los implementa.)
1. RF-E17: argumentos `--version` y `--prueba-de-humo` en `proxlaunch.interfaz.app:main` (y `__main__`).
2. RF-E10: eliminar la duplicación de la versión (DT-E6) y subir a **0.5.0**.
3. RF-E12 (HV-E11): establecer el nombre de archivo de escritorio de la aplicación en Qt, si la prueba en Wayland lo exige.
4. Prueba que fije las constantes del llavero y de las carpetas (CA-E14.4) y pruebas del modo de humo: las deriva el
   `probador` de estos requisitos.
5. `pyproject.toml`: `package-data` ya cubre fuentes, marca, traducciones y `plantilla.qss`; `LICENSE` y avisos van
   aparte en el artefacto (RF-E06).
6. **No hay** cambio funcional para el llavero (RF-E13b eliminado).

---

## 14. Decisiones adoptadas (antes, preguntas abiertas)

**Preguntas abiertas: ninguna.** Las 14 preguntas de la v1.0 quedaron resueltas; lo único pendiente de comprobación son
las hipótesis de la sección 11.

| Antes | Decisión | Quién | Efecto |
|---|---|---|---|
| P-E01 CI | Solo scripts locales; CI preparada y sin activar con plantilla de GitHub Actions; todo criterio antes `[CI]` pasa a `[LOCAL]`. | Usuario | RF-E30 a RF-E37, 1.3 |
| P-E02 Ubuntu | Solo `.deb`; AppImage fuera. | Usuario | RF-E02, DT-E2 |
| P-E03 Firma | Sin firma; SHA-256 y guía de SmartScreen; paso de firma preparado y desactivado. | Usuario | RF-E24 |
| P-E04 Instalador Windows | Inno Setup. | Orquestador | RF-E01, DT-E4 |
| P-E05 Ámbito | El asistente pregunta; «por usuario» por defecto; el `.deb` es para todo el equipo. | Orquestador | RF-E01, RNF-E02 |
| P-E06 Datos al desinstalar | Se conservan; en Windows casilla desmarcada «Borrar también mis datos»; el llavero nunca se toca. | Usuario | RF-E13 |
| RF-E13b | Eliminado: borrar un perfil o desmarcar «Recordar credenciales» ya borra el secreto (S-E7); solo se documenta el borrado manual. | Usuario | RF-E13, CA-E13.6 |
| P-E07 Artefactos | En `dist/` con `SHA256SUMS`; distribución manual. | Orquestador | RF-E20, RF-E34 |
| P-E08 Icono | Se aprueba generar `.ico` y PNG desde el símbolo sin texto, sin cambiar diseño ni colores; el usuario revisa una vista previa antes de integrarlos. | Usuario | RF-E11, CA-E11.4 |
| P-E09 Editor | «ProxLaunch»; `.deb`: `ProxLaunch <noreply@localhost>`. | Usuario | RF-E02, RF-E11 |
| P-E10 Tamaño | Presupuesto aceptado como punto de partida (≤ 90 MB comprimido, ≤ 250 MB instalado); se recalibra tras medir. | Orquestador | RF-E19 |
| P-E11 Arquitectura | Solo amd64. | Orquestador | S-E2, 1.3 |
| P-E12 Versión | 0.5.0. | Orquestador | RF-E10 |
| P-E13 Formato | SemVer. | Orquestador | RF-E10 |
| P-E14 Equipos de prueba | MV Windows 11 de evaluación en este equipo (KVM/QEMU, `swtpm` con TPM 2.0 y Secure Boot, socket de ruta corta), eliminada sin rastro al final (incluidos estado del TPM, socket y procesos `swtpm`); Windows 10 como prueba manual opcional; Ubuntu en contenedores o MVs; solo ISO oficial verificada. | Usuario / orquestador | RF-E40 a RF-E42, DT-E14, S-E6, S-E8 |
