# ProxLaunch

Asistente de escritorio para crear máquinas virtuales (MV) en Proxmox VE a través
de su API. Está pensado para personas que no son expertas en Proxmox: usa valores
seguros por defecto, ayuda en lenguaje llano y un modo básico y otro avanzado.

ProxLaunch es un proyecto independiente. Proxmox es una marca de Proxmox Server
Solutions GmbH. La aplicación solo se presenta como «Compatible con Proxmox VE».

## Estado del proyecto

**MVP 1** (versión `0.1.0`). Por ahora se ejecuta desde el código fuente. Los
instaladores llegan en el MVP 5.

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

Fuera del MVP 1: lotes, perfiles predefinidos de MV, ISO/OVA/migración desde VMware,
contenedores LXC, alta disponibilidad, editar o borrar MV existentes, instaladores,
interfaz en otros idiomas y macOS. El plan completo está en
[`docs/decisiones.md`](docs/decisiones.md) (D-12).

> **Pendiente de verificar en laboratorio:** el rol mínimo de permisos, los formatos
> exactos de algunos parámetros (por ejemplo `efidisk0`) y los textos reales de varios
> errores de Proxmox se validaron solo con respuestas simuladas. Ver
> [`docs/bitacora.md`](docs/bitacora.md), sección «Pendientes y riesgos abiertos».

## Requisitos

| Componente | Requisito |
|---|---|
| Python | 3.11 o superior |
| Sistemas | Ubuntu 22.04 / 24.04 y Windows 10 / 11 (64 bits) |
| Proxmox VE | 8.0 hasta 9.2 (una versión mayor se admite con un aviso) |
| Llavero (opcional) | Servicio de secretos del sistema, para «Recordar credenciales» |

Notas:

- Ubuntu 22.04 trae Python 3.10 por defecto. Necesitas instalar Python 3.11 o superior
  por tu cuenta antes de crear el entorno virtual.
- En Ubuntu necesitas el paquete `python3-venv` (o el equivalente de tu versión de Python).
- En Ubuntu, el llavero lo da el servicio de secretos del escritorio (por ejemplo GNOME
  Keyring). Si no hay ninguno, ProxLaunch funciona igual, pero no podrá recordar
  credenciales.
- En Windows se usa el Administrador de credenciales.

Dependencias de ejecución (se instalan solas): `PySide6-Essentials`, `requests`,
`urllib3`, `keyring` y `platformdirs`. Las de desarrollo están en el extra `dev` de
[`pyproject.toml`](pyproject.toml): `pytest`, `pytest-qt`, `pytest-cov`, `responses`,
`pytest-socket`, `ruff` y `mypy`.

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

Nunca ejecutes pruebas que creen o borren MV contra un servidor de producción (D-15).
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

- [Guía de usuario](docs/guia-usuario.md): paso a paso, sin jerga.
- [Decisiones](docs/decisiones.md): decisiones del proyecto (D-01 a D-18).
- [Requisitos del MVP 1](docs/requisitos/mvp1.md): requisitos, reglas de validación y errores.
- [Arquitectura del MVP 1](docs/arquitectura/mvp1.md): módulos e interfaces.
- [Investigación de la API de Proxmox](docs/investigacion/f1-api-proxmox.md): permisos,
  2FA y parámetros de creación.
- [Bitácora](docs/bitacora.md): historial y estado actual.

## Seguridad en resumen

- Los secretos (token, contraseña, ticket, códigos de segundo factor) no se escriben en
  archivos ni en el registro. Solo se guardan, si lo pides, en el llavero del sistema.
- Se verifica la huella SHA-256 del certificado del servidor. «Ignorar verificación SSL»
  existe solo en modo avanzado.
- La conexión es directa: se ignoran las variables de proxy del sistema y `.netrc` (D-18).

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
