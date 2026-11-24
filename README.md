# ProxLaunch

Asistente de escritorio para crear máquinas virtuales (MV) en Proxmox VE a través
de su API. Está pensado para personas que no son expertas en Proxmox: usa valores
seguros por defecto, ayuda en lenguaje llano y un modo básico y otro avanzado.

ProxLaunch es un proyecto independiente. Proxmox es una marca de Proxmox Server
Solutions GmbH. La aplicación solo se presenta como «Compatible con Proxmox VE».

## Estado del proyecto

**Versión `0.9.0`.** Hay instaladores para Ubuntu (`.deb`) y Windows
(`-setup.exe`), además de poder ejecutarse desde el código fuente. Se apoya en el MVP 5 (instaladores), el MVP 4 (origen del
sistema operativo), el MVP 3 (perfiles de máquina, lotes guardados e importación CSV), el MVP 2
(creación por lotes) y el MVP 1. Las secciones «Qué hace/añade» de más abajo describen cada
etapa; la del MVP 4 está en la [guía de usuario](docs/guia-usuario.md#elegir-el-origen-del-sistema-operativo).
Las novedades de cada versión están en las [releases](https://github.com/blaklion3212/proxlaunch/releases).

Novedades de la versión 0.9.0 (**Proxmox 8.4 a 9.2, migrar desde libvirt, hardware del clúster y ARM64 experimental**):

- **Versión mínima de Proxmox: 8.4.** Las versiones 8.0 a 8.3 ya no se admiten (ProxLaunch lo dice al conectar). Con la rama 8
  verás un aviso de que ya no recibe actualizaciones de seguridad. En servidores x86, el tipo de CPU por defecto es
  `x86-64-v2-AES` (en ARM64, `host`).
- **Migrar desde libvirt/KVM** (**Archivo > Importar desde libvirt…** o el botón **Rellenar desde un XML de libvirt…** del
  origen «Usar un disco existente»): lee el XML de `virsh dumpxml`, enseña una **vista previa** fila por fila (**Migrado**,
  **Aproximado**, **No se migra**, **Bloquea**) y rellena el formulario. **Una imagen por disco** (o **Crear vacío**), varios
  discos, **MAC de origen** opcional (desmarcada por defecto y solo con una copia), avisos de backing file, instantáneas y
  NVRAM/TPM. ProxLaunch **nunca ejecuta** `virsh` ni `qemu-img`: te da las órdenes con un botón **Copiar**. La contraseña de
  consola que pueda traer el XML no se lee. Ver la [guía](docs/guia-usuario.md#migrar-una-máquina-desde-libvirt).
- **Hardware del clúster:** dar a la máquina **tarjetas PCI y dispositivos USB** que el administrador mapeó (opciones PCIe,
  gráfica principal, ROM y USB 3; hasta 16 PCI y 5 USB; se comprueba en cada nodo y se avisa de que una tarjeta solo la usa una
  máquina encendida), y elegir **CPU personalizadas** (`custom-…`). Necesita el permiso opcional `Mapping.Use`. En clones
  hay un paso de ajuste «hardware» con **Reintentar ajustes**. Ver la
  [guía](docs/guia-usuario.md#hardware-del-clúster-y-cpu-personalizadas).
- **Servidores ARM64 (experimental, sin probar en un servidor ARM64 real):** detecta el tipo de cada servidor (o lo eliges en
  **Arquitectura de este servidor**), adapta el hardware (UEFI, CPU `host`, discos SCSI o VirtIO), no mezcla servidores x86 y
  ARM64 en un lote y no clona plantillas de otro tipo. Ver la [guía](docs/guia-usuario.md#servidores-arm64-experimental).
- **CSV:** columnas nuevas `mapeo_pci` y `mapeo_usb` (la plantilla tiene ahora 42 columnas).
- **Formato de archivo 6** solo para los lotes que usan mapeos, MAC conservada o varias imágenes de disco; si no, se escriben
  como en 0.8.0. 0.9.0 abre los archivos de 0.5 a 0.8; **0.8.0 no abre los de formato 6** (ver
  [compatibilidad](docs/guia-usuario.md#compatibilidad-con-versiones-anteriores)).
- El rol no cambia. `Mapping.Use` (por mapeo, o `/mapping/cpu/<modelo>` en Proxmox 9.2) es opcional y `Sys.Audit` permite
  detectar la arquitectura en Proxmox 8.4 a 9.1 (en 9.2 la indica el clúster). **Qué puedo hacer en este servidor** tiene tres filas nuevas.

Novedades de la versión 0.8.0 (**lotes en el servidor, redes virtuales, firewall y red del clon**):

- **Lotes en el servidor** (**Archivo > Lotes en el servidor…**): vuelve a encontrar los lotes que ProxLaunch creó (por sus
  etiquetas `proxlaunch` y `lote-<código>`), ver su detalle, **exportarlos a CSV** (con la IP si quieres) y **deshacerlos**
  con doble control: etiquetas y nota del mismo lote, lista desmarcable y escribir el código del lote. Borra sin «purge».
  Ver la [guía](docs/guia-usuario.md#lotes-en-el-servidor-inventario).
- **Redes virtuales (SDN):** las VNets aparecen en la lista **Red** junto a los bridges (necesitan `SDN.Use` en su zona; rol
  `PVESDNUser`). Ver la [guía](docs/guia-usuario.md#redes-virtuales-sdn).
- **Firewall de la máquina:** activarlo con un **grupo de seguridad**, política de entrada (Bloquear por defecto) y de salida
  (Permitir por defecto) y DHCP; avisa si el firewall general está apagado y no enciende una máquina con una tarjeta sin
  firewall. Ver la [guía](docs/guia-usuario.md#firewall-de-la-máquina).
- **Red del clon:** cambiar la red, VLAN, tarjeta, MTU y límite de las copias de una plantilla, y añadir o quitar tarjetas,
  conservando la MAC (o pidiendo una nueva). Ver la [guía](docs/guia-usuario.md#red-del-clon).
- **CSV:** 5 columnas nuevas (`reescribir_red`, `cortafuegos`, `grupo_seguridad`, `politica_entrada` y `politica_salida`).
- **Formato de archivo 5** para los lotes que usan la red del clon o el firewall. 0.8.0 abre los archivos de 0.5 a 0.7;
  **0.7.0 no abre los de formato 5** (ver [compatibilidad](docs/guia-usuario.md#compatibilidad-con-versiones-anteriores)).
- El rol no cambia. Para usar VNets fuera de la zona local hace falta `SDN.Use` en la zona o la red (opcional con la
  asignación acotada).

Novedades de la versión 0.7.0 (**configuración inicial de las máquinas y plantillas desde imágenes cloud**):

- **Configuración inicial con cloud-init** al clonar una plantilla: usuario, **claves SSH públicas** (pegadas o desde un
  archivo `.pub`; se rechazan las privadas), contraseña opcional (mínimo 8 caracteres, nunca se guarda en archivos ni
  registros), red por tarjeta (DHCP, IP fija o **IP en serie** en un lote, con puerta de enlace), DNS, dominio de búsqueda,
  actualizar paquetes y **scripts** (*snippets*) con un ejemplo para instalar el agente invitado. Ver la
  [guía](docs/guia-usuario.md#configuración-inicial-con-cloud-init).
- **Esperar la IP de cada máquina** (con el agente invitado): columna **IP** en el progreso, **Dejar de esperar la IP**,
  **Copiar lista de IPs** y **Exportar IPs…**. Ver la [guía](docs/guia-usuario.md#esperar-la-ip).
- **Crear plantilla desde imagen cloud** (menú Archivo, Proxmox 8.4 o superior): sube o descarga una imagen (`.qcow2`,
  `.img`, `.raw` o `.vmdk`), crea la máquina, amplía el disco, guarda valores de cloud-init y la convierte en plantilla, con
  suma SHA-256, reintentos y «Borrar la máquina a medio crear». Ver la
  [guía](docs/guia-usuario.md#crear-una-plantilla-desde-una-imagen-cloud).
- **CSV:** 13 columnas nuevas (`ci_usuario`, `ci_claves`, `ci_contrasena`, `ci_ip`, `ci_puerta`, `ci_dns`, `ci_dominio`,
  `ci_actualizar`, `ci_snippet_usuario`, `ci_snippet_vendor`, `ci_snippet_red`, `ci_snippet_meta` y `esperar_ip`). La
  contraseña se enmascara y no está en la plantilla CSV.
- **Formato de archivo 4** para los lotes que usan cloud-init o esperar la IP. 0.7.0 abre los archivos de 0.5 y 0.6; **0.6.0
  no abre los de formato 4** (ver [compatibilidad](docs/guia-usuario.md#compatibilidad-con-versiones-anteriores)).
- Privilegios opcionales nuevos (el rol no cambia): `VM.Config.Cloudinit`, `VM.Monitor` (Proxmox 8) o
  `VM.GuestAgent.Audit` (Proxmox 9) y los de los scripts.

Novedades de la versión 0.6.0 (**opciones de la máquina**, todas explicadas en la
[guía de usuario](docs/guia-usuario.md#opciones-de-la-máquina)):

- **Encender al terminar** (con `VM.PowerMgmt`, opcional) y **Arrancar con el servidor**, con orden y espera de arranque
  en modo avanzado.
- **Notas de origen** automáticas (fecha, versión, perfil, lote y, si lo marcas, tu usuario) y **notas propias**, con aviso
  a partir de 7500 caracteres y bloqueo por encima de 8192.
- **Etiquetas propias**, comprobadas contra la **política de etiquetas** del centro de datos antes de crear.
- **Pool** de recursos (incluidos los anidados `padre/hijo`), **Proteger contra borrado**, y **MTU** y **límite de
  velocidad** por tarjeta de red (modo avanzado).
- **Deshacer** puede apagar a la fuerza y desproteger las máquinas del lote que elijas, con una confirmación expresa que
  lista cada máquina por nombre y número.
- Columnas nuevas en el CSV (`encender`, `arranque_auto`, `notas`, `etiquetas`, `pool`, `proteger`, `mtu`, `limite_red`) y
  **formato de archivo 3** para lotes y perfiles que usan las opciones nuevas. 0.6.0 lee los formatos 1 y 2; 0.5.1 no abre
  los de formato 3 (ver [compatibilidad](docs/guia-usuario.md#compatibilidad-con-versiones-anteriores)).

Qué hace el MVP 1:

- Conecta con un servidor Proxmox VE 8.4 a 9.2, con **API Token** o con **usuario y
  contraseña** (con segundo factor TOTP o clave de recuperación si el servidor lo pide).
- Guarda **perfiles de conexión** con varias IP o nombres de servidor (si el primero no
  responde, prueba el siguiente).
- Comprueba la **huella del certificado** del servidor la primera vez (confianza en el primer
  uso) y bloquea la conexión si después cambia.
- Descubre nodos, almacenamientos y redes, y distingue un servidor individual de un clúster.
- Crea **una** MV con disco vacío (sin instalar sistema operativo), con seguimiento de la
  tarea por etapas.
- Modo básico y avanzado. Tema claro y oscuro, según el sistema o a elección.
- La MV se crea **detenida** (desde la versión 0.6.0 puedes pedir **Encender al terminar**).

Qué añade el MVP 2 (**creación por lotes**):

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
  ajenas o bloqueadas, ni discos sueltos. Las protegidas o encendidas solo se tocan con la
  confirmación expresa de la versión 0.6.0 (ver más abajo).
- **Informe** del lote en texto plano (copiar o guardar `.txt`), sin host, IP, usuario ni
  secretos, e informe parcial si se cierra la aplicación con un lote en curso.

Qué añade el MVP 3 (**perfiles, lotes guardados y CSV**):

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

> Validado contra Proxmox VE 9.2 real en laboratorio (rol mínimo, parámetros, 2FA, mensajes
> de error, y en el MVP 2 lotes de hasta 30 MV con deshacer; ver `tests/integracion/`).
> Clústeres multinodo (incluido el reparto entre nodos) y Proxmox 8.x solo con respuestas
> simuladas. Pendiente en el MVP 3: verificar en un Windows real los mensajes de «archivo
> bloqueado» y de rutas largas.

### Permisos de Proxmox

El **rol mínimo no cambia** en la versión 0.9.0: son los mismos 10 privilegios del MVP 1 (`VM.Allocate`, `VM.Audit`,
`VM.Config.Options`, `VM.Config.HWType`, `VM.Config.CPU`, `VM.Config.Memory`,
`VM.Config.Network`, `Datastore.AllocateSpace`, `SDN.Use` y `Sys.Audit`) más los 4 de orígenes del MVP 4 (`VM.Config.Disk`,
`VM.Clone`, `Datastore.AllocateTemplate` y `Sys.AccessNetwork`); lista y pasos en la
[guía de usuario](docs/guia-usuario.md#permisos-que-hacen-falta). Crear lotes, etiquetar y
deshacer no piden ninguno más:

- Borrar una MV (`DELETE /nodes/{n}/qemu/{vmid}`) solo exige `VM.Allocate` (verificado en PVE 9.2).
- Las etiquetas (las fijas y las propias) usan `VM.Config.Options`; la protección, el arranque con el servidor, las notas
  y quitar la protección en Deshacer también. El MTU y el límite de red usan `VM.Config.Network`. Todos ya están en el rol.
- Crear en un **pool** no necesita ningún privilegio nuevo: basta `VM.Allocate` en la máquina o en el pool.
- Si el administrador restringió la política de etiquetas del centro de datos (`user-tag-access`,
  `registered-tags`), ProxLaunch la lee antes de crear (con `Sys.Audit` en `/`) y **bloquea** si alguna etiqueta no
  está permitida, nombrándola. Sin `Sys.Audit` en `/` la política se ve incompleta y solo avisa. Si no pudo comprobarla y Proxmox falla dentro de la tarea, pausa el lote y ofrece
  «Seguir sin etiquetas».

**Privilegios opcionales (no forman parte del rol).** Sin ellos ProxLaunch funciona igual y solo desactiva la
opción afectada, explicando qué falta:

| Privilegio | Ruta | Habilita |
|---|---|---|
| `VM.PowerMgmt` | `/vms` | **Encender al terminar**, y que **Deshacer** apague a la fuerza las máquinas encendidas del lote. |
| `Pool.Audit` | `/pool` | Ver la lista de pools para elegir uno. |
| `VM.Config.Cloudinit` | `/vms` | La sección de cloud-init (en Proxmox 8.x basta `VM.Config.Network`, que ya está en el rol). |
| `VM.Monitor` (Proxmox 8.x) o `VM.GuestAgent.Audit` (Proxmox 9.x) | `/vms` | **Esperar la IP** de cada máquina. |
| `Datastore.AllocateSpace` (Proxmox 8.x) | `/storage/<almacén de snippets>` | Elegir scripts (*snippets*); ya está en el rol, pero hay que tenerlo también sobre ese almacén. |
| `SDN.Use` | `/sdn/zones/<zona>` o `/sdn/zones/<zona>/<red>` | Usar redes virtuales (VNets) de esa zona; con la asignación acotada solo cubre `localnetwork`. `SDN.Audit` (opcional) muestra su alias y estado. |
| `Mapping.Use` | `/mapping/pci/<mapeo>`, `/mapping/usb/<mapeo>` (o `/mapping`) | Dar a una máquina tarjetas PCI o dispositivos USB mapeados por el administrador (rol `PVEMappingUser`); también clonar una plantilla que ya los usa. |
| `Mapping.Use` | `/mapping/cpu/<modelo>` | Solo Proxmox 9.2: usar una CPU personalizada. En Proxmox 8.4 a 9.1 basta `Sys.Audit` en `/nodes`, que ya está en el rol. |

`Sys.Modify` y `Pool.Allocate` nunca se piden. El asistente **Crear plantilla desde imagen cloud** usa solo privilegios que
ya están en el rol; detalles por versión en la
[guía](docs/guia-usuario.md#privilegios-opcionales-no-forman-parte-del-rol).

## Requisitos

| Componente | Requisito |
|---|---|
| Python | 3.11 o superior |
| Sistemas | Ubuntu 22.04 / 24.04 y Windows 10 / 11 (64 bits) |
| Proxmox VE | 8.4 hasta 9.2 (una versión mayor se admite con un aviso) |
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
| Ubuntu 22.04 / 24.04 (64 bits) | `proxlaunch_0.9.0_amd64.deb` |
| Windows 10 / 11 (64 bits) | `proxlaunch-0.9.0-windows-x64-setup.exe` |
| Comprobación | `SHA256SUMS` (suma SHA-256 de cada instalador) |

Comprueba la descarga y luego instala:

```bash
# Ubuntu
sha256sum -c SHA256SUMS --ignore-missing
sudo apt install ./proxlaunch_0.9.0_amd64.deb
```

```powershell
# Windows (PowerShell): compara el Hash con la línea de SHA256SUMS y ejecuta el instalador
Get-FileHash -Algorithm SHA256 .\proxlaunch-0.9.0-windows-x64-setup.exe
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

Nunca ejecutes pruebas que creen o borren MV contra un servidor de producción. Las
pruebas de lotes del laboratorio (`tests/integracion/test_lab_lotes.py`) crean y borran MV de
verdad: úsalas solo contra el laboratorio.
Cobertura mínima: núcleo 85 % y global 75 % (`.venv/bin/python -m pytest --cov=proxlaunch --cov-report=term-missing`).

## Estructura del proyecto

```text
src/proxlaunch/
  nucleo/        Python puro, sin Qt: modelos, API de Proxmox, servicios,
                 validaciones, persistencia y registro
  interfaz/      PySide6: ventana principal, diálogos, vistas, tema y textos
  recursos/      Logos (SVG), fuentes con sus licencias y traducciones
tests/           nucleo/, interfaz/, integracion/ y datos/respuestas/
docs/            Guía de usuario, archivos de ejemplo, capturas y empaquetado
recursos/marca/  Logos originales y el generador (generador/generar_logo.py)
```

## Documentación

- [Guía de usuario](docs/guia-usuario.md): paso a paso, sin jerga (incluye los
  [lotes](docs/guia-usuario.md#crear-varias-máquinas-de-una-vez-lotes), los
  [perfiles de máquina](docs/guia-usuario.md#perfiles-de-máquina), los
  [lotes guardados](docs/guia-usuario.md#guardar-y-abrir-lotes), la
  [importación CSV](docs/guia-usuario.md#importar-máquinas-desde-un-csv), el
  [lote por filas](docs/guia-usuario.md#lote-por-filas), las
  [opciones de la máquina](docs/guia-usuario.md#opciones-de-la-máquina), la
  [configuración inicial con cloud-init](docs/guia-usuario.md#configuración-inicial-con-cloud-init), la
  [espera de la IP](docs/guia-usuario.md#esperar-la-ip) y el
  [asistente de plantillas desde imágenes cloud](docs/guia-usuario.md#crear-una-plantilla-desde-una-imagen-cloud), la
  [migración desde libvirt](docs/guia-usuario.md#migrar-una-máquina-desde-libvirt), el
  [hardware del clúster y las CPU personalizadas](docs/guia-usuario.md#hardware-del-clúster-y-cpu-personalizadas) y los
  [servidores ARM64 (experimental)](docs/guia-usuario.md#servidores-arm64-experimental)).
- [Archivos de ejemplo](docs/ejemplos/LEEME.md): CSV, lotes y perfiles listos para abrir (incluidos `mvs-opciones.csv` y
  `lote-con-opciones.proxlaunch-lote.json`, con las opciones de la versión 0.6.0, y `mvs-cloudinit.csv` y
  `lote-cloudinit.proxlaunch-lote.json`, con cloud-init y esperar la IP de la versión 0.7.0, y `mvs-red-firewall.csv` y
  `lote-red-firewall.proxlaunch-lote.json`, con la red del clon y el firewall de la versión 0.8.0, y `mvs-hardware-cluster.csv` y
  `lote-libvirt.proxlaunch-lote.json`, con el hardware del clúster y una máquina traída de libvirt de la versión 0.9.0).
- [Instalar y desinstalar](docs/guia-usuario.md#instalar-y-desinstalar-proxlaunch): `.deb` y
  `-setup.exe`, SmartScreen, datos y verificación de `SHA256SUMS`.
- [Empaquetado](docs/empaquetado.md): construcción y verificación de los instaladores
  (para desarrolladores); detalle de los scripts en [`empaquetado/LEEME.md`](empaquetado/LEEME.md).

## Seguridad en resumen

- Los secretos (token, contraseña, ticket, códigos de segundo factor) no se escriben en
  archivos ni en el registro. Solo se guardan, si lo pides, en el llavero del sistema.
- Se verifica la huella SHA-256 del certificado del servidor. «Ignorar verificación SSL»
  existe solo en modo avanzado.
- La conexión es directa: se ignoran las variables de proxy del sistema y `.netrc`.
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
  cambiar sin consultar al responsable del proyecto. No se usan el nombre ni el logo
  de Proxmox como identidad de la aplicación.

## Licencia del proyecto

ProxLaunch es software libre bajo la [licencia MIT](LICENSE) (en español, con el original en
inglés, que es el que tiene validez legal): puedes usarlo, modificarlo y
redistribuirlo, también con fines comerciales, siempre que conserves el aviso de copyright.
Se entrega sin garantía.

Las bibliotecas y fuentes de terceros conservan sus licencias (PySide6/Qt bajo LGPL-3.0;
fuentes bajo OFL).
