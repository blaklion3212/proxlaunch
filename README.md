# ProxLaunch

Asistente de escritorio para crear máquinas virtuales (MV) en Proxmox VE a través
de su API. Está pensado para personas que no son expertas en Proxmox: usa valores
seguros por defecto, ayuda en lenguaje llano y un modo básico y otro avanzado.

ProxLaunch es un proyecto independiente. Proxmox es una marca de Proxmox Server
Solutions GmbH. La aplicación solo se presenta como «Compatible con Proxmox VE».

## Estado del proyecto

**Versión `0.5.0` (MVP 5, en cierre).** Hay instaladores para Ubuntu (`.deb`) y Windows
(`-setup.exe`), además de poder ejecutarse desde el código fuente. Sobre el MVP 4 (origen del
sistema operativo), el MVP 3 (perfiles de máquina, lotes guardados e importación CSV), el MVP 2
(creación por lotes) y el MVP 1. Las secciones «Qué hace/añade» de más abajo describen cada
etapa; la del MVP 4 está en la [guía de usuario](docs/guia-usuario.md#elegir-el-origen-del-sistema-operativo)
y el estado vivo en la [bitácora](docs/bitacora.md). El MVP 5 es el último del plan; falta su
aprobación final.

Qué hace el MVP 1:

- Conecta con un servidor Proxmox VE 8.0 a 9.2, con **API Token** o con **usuario y
  contraseña** (con segundo factor TOTP o clave de recuperación si el servidor lo pide).
- Guarda **perfiles de conexión** con varias IP o nombres de servidor (si el primero no
  responde, prueba el siguiente).
- Comprueba la **huella del certificado** del servidor la primera vez (confianza en el primer
  uso) y bloquea la conexión si después cambia.
- Descubre nodos, almacenamientos y redes, y distingue un servidor individual de un clúster.
- Crea **una** MV con disco vacío (sin instalar sistema operativo), con seguimiento de la
  tarea por etapas.
- Modo básico y avanzado. Tema claro y oscuro, según el sistema o a elección.
- La MV se crea **detenida**: ProxLaunch no la enciende.

Qué añade el MVP 2 (**creación por lotes**, D-20 y D-21):

- Crea de **1 a 100 MV iguales** de una vez, con un patrón de nombres (`srv-web-01`,
  `srv-web-02`...) y números de MV (VMID) consecutivos que **salta los ocupados**.
- **Reparto entre nodos** de un clúster: Automático (equilibrado por memoria y espacio libres),
  un nodo o nodos elegidos, y reparto por turnos en modo avanzado.
- **Validación previa de todo el lote** (espacio acumulado por almacenamiento y nodo,
  sobreasignación en almacenamientos *thin* con confirmación explícita, nombres y números),
  con **resumen y confirmación** (doble confirmación con más de 10 MV).
- **Simulación**: hace todas las comprobaciones y muestra lo que se enviaría, leyendo solo del
  servidor (en el laboratorio solo quedaron consultas `GET` en el registro de acceso).
- **Progreso por MV**, pausa ante errores globales o repetidos, cancelación y **envío
  incierto**: una MV de la que no se sabe si se creó nunca se vuelve a enviar sola; se
  comprueba con consultas de solo lectura.
- **Etiquetas** `proxlaunch` y `lote-<id>` en las MV creadas (activadas por defecto y
  desactivables en modo avanzado) para demostrar de quién es cada MV.
- **Deshacer** (manual, con confirmación): elimina solo las MV que creó el lote, nunca MV
  ajenas, protegidas, encendidas o bloqueadas, ni discos sueltos (D-21).
- **Informe** del lote en texto plano (copiar o guardar `.txt`), sin host, IP, usuario ni
  secretos, e informe parcial si se cierra la aplicación con un lote en curso.

Qué añade el MVP 3 (**perfiles, lotes guardados y CSV**, D-22):

- **Perfiles de máquina**: seis de fábrica (solo lectura) y los tuyos (crear, guardar cambios,
  duplicar, renombrar, eliminar, exportar e importar). Aplican solo hardware y redes; nunca el
  nombre, el VMID ni el nodo. El almacenamiento y el bridge son pistas: si no existen en el
  nodo se usan los predeterminados y se avisa. Panel de compatibilidad.
- **Lotes guardados**: archivo JSON autocontenido (sin datos de conexión ni secretos). Se
  guarda aunque tenga errores; abrirlo requiere conexión y lo que no encaja con el servidor se
  muestra como desajuste para elegir otro valor, sin sustituir nada en silencio.
- **Importación desde CSV**: separador y codificación detectados, hasta 100 filas, columna de
  perfil por fila, unidades (GiB por defecto), vista previa con errores por fila (numeradas
  como en Excel), importar solo las filas correctas, CSV de errores reimportable, plantilla
  descargable e informe del lote en CSV. Todo CSV exportado lleva las celdas entre comillas y
  las fórmulas neutralizadas.
- **Lote por filas**: cada fila es una MV con su propia configuración, en un solo resumen,
  confirmación, informe y «Deshacer…». Permite quitar filas, asignar VMID automáticamente y
  quitar las filas que no caben.
- **Cambios sin guardar**: pregunta (Guardar / No guardar / Cancelar) al cerrar, cerrar sesión,
  abrir otro lote, importar, cambiar de servidor y salir del lote por filas.
- **Seguridad de archivos**: los archivos de terceros nunca se modifican; nada que parezca una
  credencial se guarda en lotes, perfiles ni CSV; archivos 0600 y carpetas 0700 (POSIX); límites
  de tamaño, filas y profundidad.

Fuera del MVP 3: ISO/OVA/migración desde VMware (MVP 4), contenedores LXC, alta disponibilidad,
editar o borrar MV que no creó un lote, instaladores (MVP 5), interfaz en otros idiomas y macOS.
El plan completo está en [`docs/decisiones.md`](docs/decisiones.md) (D-12).

> Validado contra Proxmox VE 9.2 real en laboratorio (rol mínimo, parámetros, 2FA, mensajes
> de error, y en el MVP 2 lotes de hasta 30 MV con deshacer; ver `tests/integracion/`).
> Clústeres multinodo (incluido el reparto entre nodos) y Proxmox 8.x solo con respuestas
> simuladas. Pendiente en el MVP 3: verificar en un Windows real los mensajes de «archivo
> bloqueado» y de rutas largas. Ver [`docs/bitacora.md`](docs/bitacora.md).

### Permisos de Proxmox

El **rol mínimo no cambia**: son los mismos 10 privilegios del MVP 1 (`VM.Allocate`, `VM.Audit`,
`VM.Config.Options`, `VM.Config.HWType`, `VM.Config.CPU`, `VM.Config.Memory`,
`VM.Config.Network`, `Datastore.AllocateSpace`, `SDN.Use` y `Sys.Audit`; lista y pasos en la
[guía de usuario](docs/guia-usuario.md#permisos-que-hacen-falta)). Crear lotes, etiquetar y
deshacer no piden ninguno más:

- Borrar una MV (`DELETE /nodes/{n}/qemu/{vmid}`) solo exige `VM.Allocate` (verificado en PVE 9.2).
- Las etiquetas al crear usan `VM.Config.Options`, que ya está en el rol.
- Excepción: si el administrador restringió la política `user-tag-access` del datacenter,
  Proxmox acepta la orden pero la tarea falla por falta de `Sys.Modify`. ProxLaunch pausa
  el lote y ofrece «Seguir sin etiquetas».

## Requisitos

| Componente | Requisito |
|---|---|
| Python | 3.11 o superior |
| Sistemas | Ubuntu 22.04 / 24.04 y Windows 10 / 11 (64 bits) |
| Proxmox VE | 8.0 hasta 9.2 (una versión mayor se admite con un aviso) |
| Llavero (opcional) | Servicio de secretos del sistema, para «Recordar credenciales» |

Notas:

- Solo para ejecutar desde el código fuente (los instaladores incluyen su Python): Ubuntu 22.04
  trae Python 3.10 por defecto. Necesitas instalar Python 3.11 o superior por tu cuenta antes de
  crear el entorno virtual.
- En Ubuntu necesitas el paquete `python3-venv` (o el equivalente de tu versión de Python).
- En Ubuntu, el llavero lo da el servicio de secretos del escritorio (por ejemplo GNOME
  Keyring). Si no hay ninguno, ProxLaunch funciona igual, pero no podrá recordar
  credenciales.
- En Windows se usa el Administrador de credenciales.

Dependencias de ejecución (se instalan solas): `PySide6-Essentials`, `requests`,
`urllib3`, `keyring` y `platformdirs`. Las de desarrollo están en el extra `dev` de
[`pyproject.toml`](pyproject.toml): `pytest`, `pytest-qt`, `pytest-cov`, `responses`,
`pytest-socket`, `ruff` y `mypy`.

## Instalación desde los instaladores

Los artefactos están en `dist/` (se generan con los scripts de [`empaquetado/`](empaquetado/LEEME.md)):

| Sistema | Archivo |
|---|---|
| Ubuntu 22.04 / 24.04 (64 bits) | `proxlaunch_0.5.0_amd64.deb` |
| Windows 10 / 11 (64 bits) | `proxlaunch-0.5.0-windows-x64-setup.exe` |
| Comprobación | `SHA256SUMS` (suma SHA-256 de cada instalador) |

Comprueba la descarga y luego instala:

```bash
# Ubuntu
sha256sum -c SHA256SUMS --ignore-missing
sudo apt install ./proxlaunch_0.5.0_amd64.deb
```

```powershell
# Windows (PowerShell): compara el Hash con la línea de SHA256SUMS y ejecuta el instalador
Get-FileHash -Algorithm SHA256 .\proxlaunch-0.5.0-windows-x64-setup.exe
```

Los instaladores incluyen su propio Python: no hace falta instalar nada más (en Ubuntu, `apt` instala las
bibliotecas del sistema). El instalador de Windows **no está firmado**: SmartScreen puede avisar y hay que elegir
«Más información → Ejecutar de todas formas». Desinstalar conserva tus datos; los pasos, la opción de borrarlos y
dónde quedan están en la [guía de usuario](docs/guia-usuario.md#instalar-y-desinstalar-proxlaunch). Para
construir y verificar los instaladores, ver [Empaquetado](docs/empaquetado.md).

## Instalación para desarrollo

Todos los comandos se escriben desde la raíz del repositorio.

### Ubuntu

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Si tu `python3` es anterior a 3.11, usa el ejecutable de la versión nueva
(por ejemplo `python3.11 -m venv .venv`).

### Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

En Windows, cambia `.venv/bin/` por `.venv\Scripts\` en todos los comandos de más abajo.

## Cómo ejecutar

Ubuntu:

```bash
.venv/bin/proxlaunch
# equivalente:
.venv/bin/python -m proxlaunch
```

Windows:

```powershell
.venv\Scripts\proxlaunch
# equivalente:
.venv\Scripts\python -m proxlaunch
```

El comando `proxlaunch` está definido en `pyproject.toml` (`proxlaunch.interfaz.app:main`).
Para ejecutar sin pantalla (por ejemplo, en un servidor de integración) antepón
`QT_QPA_PLATFORM=offscreen`.

Si en Ubuntu Qt no logra abrir la ventana y menciona el complemento «xcb», suele faltar
la biblioteca `libxcb-cursor0` (`sudo apt install libxcb-cursor0`). Esto es una pista
general de Qt, no se comprobó en este repositorio.

## Pruebas, lint y tipos

Ubuntu (en Windows, usa `.venv\Scripts\python`):

```bash
# Toda la suite
.venv/bin/python -m pytest

# Un archivo o un caso
.venv/bin/python -m pytest tests/test_humo.py
.venv/bin/python -m pytest tests/test_humo.py::test_paquete_importa_y_tiene_version

# Interfaz sin pantalla
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest

# Cobertura (mínimo: 85 % en el núcleo, 75 % global)
.venv/bin/python -m pytest --cov=proxlaunch --cov-report=term-missing
.venv/bin/python -m pytest --cov=proxlaunch.nucleo --cov-fail-under=85

# Lint y tipos
.venv/bin/ruff check src tests
.venv/bin/python -m mypy src
```

En PowerShell, la variable se define así: `$env:QT_QPA_PLATFORM = "offscreen"`.

Las pruebas **no usan la red**: `pytest-socket` la bloquea y las respuestas de Proxmox
son simuladas (`tests/datos/respuestas/`). Las pruebas de integración contra un
laboratorio (`tests/integracion/`) se saltan salvo que definas `PROXLAUNCH_LAB=1` y
permitas sockets:

```bash
PROXLAUNCH_LAB=1 .venv/bin/python -m pytest -m integracion --force-enable-socket
```

Nunca ejecutes pruebas que creen o borren MV contra un servidor de producción (D-15). Las
pruebas de lotes del laboratorio (`tests/integracion/test_lab_lotes.py`) crean y borran MV de
verdad: úsalas solo contra el laboratorio.
Más detalle en [`.claude/proyecto/pruebas.md`](.claude/proyecto/pruebas.md).

## Estructura del proyecto

```text
src/proxlaunch/
  nucleo/        Python puro, sin Qt: modelos, API de Proxmox, servicios,
                 validaciones, persistencia y registro
  interfaz/      PySide6: ventana principal, diálogos, vistas, tema y textos
  recursos/      Logos (SVG), fuentes con sus licencias y traducciones
tests/           nucleo/, interfaz/, integracion/ y datos/respuestas/
docs/            Decisiones, requisitos, arquitectura, investigación y guía de usuario
recursos/marca/  Logos originales y el generador (generador/generar_logo.py)
```

## Documentación

- [Guía de usuario](docs/guia-usuario.md): paso a paso, sin jerga (incluye los
  [lotes](docs/guia-usuario.md#crear-varias-máquinas-de-una-vez-lotes), los
  [perfiles de máquina](docs/guia-usuario.md#perfiles-de-máquina), los
  [lotes guardados](docs/guia-usuario.md#guardar-y-abrir-lotes), la
  [importación CSV](docs/guia-usuario.md#importar-máquinas-desde-un-csv) y el
  [lote por filas](docs/guia-usuario.md#lote-por-filas)).
- [Instalar y desinstalar](docs/guia-usuario.md#instalar-y-desinstalar-proxlaunch): `.deb` y
  `-setup.exe`, SmartScreen, datos y verificación de `SHA256SUMS`.
- [Empaquetado](docs/empaquetado.md): construcción y verificación de los instaladores
  (para desarrolladores); detalle de los scripts en [`empaquetado/LEEME.md`](empaquetado/LEEME.md).
- [Decisiones](docs/decisiones.md): decisiones del proyecto (D-01 a D-27).
- [Requisitos del MVP 1](docs/requisitos/mvp1.md), [del MVP 2](docs/requisitos/mvp2.md),
  [del MVP 3](docs/requisitos/mvp3.md) y [del MVP 5](docs/requisitos/mvp5.md): requisitos, reglas de
  validación y errores.
- [Arquitectura del MVP 1](docs/arquitectura/mvp1.md), [del MVP 2](docs/arquitectura/mvp2.md),
  [del MVP 3](docs/arquitectura/mvp3.md) y [del MVP 5](docs/arquitectura/mvp5.md): módulos,
  trazabilidad y firmas públicas.
- [Investigación de la API de Proxmox](docs/investigacion/f1-api-proxmox.md): permisos,
  2FA, parámetros de creación y hechos verificados en laboratorio.
- [Bitácora](docs/bitacora.md): historial y estado actual.

## Seguridad en resumen

- Los secretos (token, contraseña, ticket, códigos de segundo factor) no se escriben en
  archivos ni en el registro. Solo se guardan, si lo pides, en el llavero del sistema.
- Se verifica la huella SHA-256 del certificado del servidor. «Ignorar verificación SSL»
  existe solo en modo avanzado.
- La conexión es directa: se ignoran las variables de proxy del sistema y `.netrc` (D-18).
- Los archivos de terceros (perfiles, lotes y CSV) solo se leen, con límites de tamaño y
  contenido; no se ejecuta nada de lo que traen. Los que escribe ProxLaunch son atómicos y, en
  POSIX, 0600 (carpetas propias 0700).

Detalles para usuarios en la [guía](docs/guia-usuario.md#privacidad-y-seguridad).

## Licencias de fuentes y nota del logo

- Las fuentes **Open Sans** y **JetBrains Mono** van incluidas bajo la
  [SIL Open Font License (OFL)](https://openfontlicense.org). Sus textos están en
  `src/proxlaunch/recursos/fuentes/OpenSans-OFL.txt` y
  `src/proxlaunch/recursos/fuentes/JetBrainsMono-OFL.txt`, y también se muestran en
  *Ayuda > Acerca de ProxLaunch*.
- El generador del logo usa la fuente **Montserrat** (también OFL):
  `recursos/marca/generador/LICENCIA-Montserrat-OFL.txt`.
- El logo de ProxLaunch es un rediseño propio en SVG (`recursos/marca/`). No se debe
  cambiar sin consultar al responsable del proyecto (D-01). No se usan el nombre ni el logo
  de Proxmox como identidad de la aplicación.

## Licencia del proyecto

Uso interno, todos los derechos reservados (D-19). Ver [`LICENSE`](LICENSE).
Las bibliotecas y fuentes de terceros conservan sus licencias (PySide6/Qt bajo LGPL-3.0;
fuentes bajo OFL).
