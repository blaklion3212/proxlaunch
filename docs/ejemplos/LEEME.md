# Archivos de ejemplo de ProxLaunch

Esta carpeta reúne archivos listos para abrir en ProxLaunch y usarlos como modelo (layout)
al crear tus propias máquinas virtuales (MVs): CSV de máquinas, lotes guardados y perfiles
de máquina.

Todos los datos son ficticios. El escenario común es un clúster «demo» con los nodos
`pve1`, `pve2` y `pve3`, los almacenamientos `local` (ISOs e imágenes), `local-lvm` y
`datos` (discos de MV) y las redes `vmbr0` y `vmbr1`. Los nombres de ISOs, imágenes y
plantillas (`ubuntu-24.04-server.iso`, `debian-12-generic.qcow2`, `plantilla-debian12`...)
están inventados: **sustitúyelos por los de tu servidor**. Si un nombre no existe en tu
servidor, la vista previa o la validación te lo dirá antes de crear nada.

Los archivos los generó ProxLaunch (exportar plantilla CSV, guardar lote, exportar perfiles)
y se comprobaron con sus propios lectores, así que el formato es exactamente el que la
aplicación escribe y acepta.

## Qué es cada archivo

| Archivo | Para qué sirve | Cómo abrirlo |
|---|---|---|
| `mvs-minimo.csv` | El CSV más sencillo: 3 MVs con disco vacío (nombre, núcleos, memoria y disco). Empieza por aquí. | **Lote > Importar desde CSV…** |
| `mvs-mixtas.csv` | 7 MVs con distintos orígenes: disco vacío, instalar desde ISO (Linux y Windows 11), importar un disco qcow2 y clonar plantillas. Muestra VMID, nodo, VLAN y perfil por fila. | **Lote > Importar desde CSV…** |
| `mvs-multidisco-cluster.csv` | 3 MVs en un clúster: dos discos (`disco2`, `almacenamiento2`), VLAN y nodo por fila. Necesita el almacenamiento `datos` y varios nodos. | **Lote > Importar desde CSV…** |
| `mvs-con-errores.csv` | Contiene errores a propósito para practicar la vista previa (qué se ve, cómo filtrar, importar solo las filas correctas). | **Lote > Importar desde CSV…** |
| `mvs-escrito-a-mano.csv` | Lo mismo que un CSV hecho en Excel, LibreOffice o un editor de texto: sin comillas, sin BOM y con saltos de línea simples. Demuestra que no hace falta usar la plantilla de la aplicación. | **Lote > Importar desde CSV…** |
| `lote-homogeneo.proxlaunch-lote.json` | Lote guardado de 3 MVs iguales (`srv-web-01`...`srv-web-03`; 2 núcleos, 2 GiB, disco de 32 GiB). | **Lote > Abrir lote…** (`Ctrl+O`) |
| `lote-por-filas.proxlaunch-lote.json` | Lote guardado de 3 MVs distintas (disco vacío con VMID y nodo fijos, instalación desde ISO y clon de plantilla). Es el resultado de importar filas de `mvs-mixtas.csv`. | **Lote > Abrir lote…** (`Ctrl+O`) |
| `perfiles-ejemplo.proxlaunch-perfiles.json` | Dos perfiles de máquina: un servidor web sencillo y un escritorio Windows 11 con ISO sugerido y nombres de almacenamiento y red como pistas. | **Perfiles > Administrar perfiles… > Importar…** |

Notas de uso:

- Para CSV y lotes hay que estar conectado a un servidor. Sin conexión puedes ver la vista
  previa, pero **Continuar** queda desactivado.
- **Perfiles > Administrar perfiles…** aparece en el modo **Avanzado** (menú
  **Ajustes > Modo**). Un perfil importado no crea nada por sí solo: aporta el hardware
  que luego eliges en el selector de perfil o en la columna `perfil` de un CSV.
- También puedes obtener una plantilla CSV propia con **Lote > Descargar plantilla CSV…**.
- Los lotes y perfiles son JSON de texto con clave `formato`; no los edites a mano salvo que
  sepas lo que haces. Lo habitual es abrirlos, ajustarlos y volver a guardarlos desde la aplicación.

## El archivo CSV

Reglas generales:

- Una fila = una MV. La primera fila no vacía es el encabezado.
- Separadores aceptados: `;`, `,`, tabulador y `|`. Se detecta solo; también vale una primera
  línea `sep=;`. Los CSV que ProxLaunch escribe usan `;` por defecto.
- Codificaciones: UTF-8 (con o sin BOM), UTF-16, Windows-1252 e ISO-8859-1.
- Los nombres de columna no distinguen mayúsculas ni acentos, y espacio, guion y guion bajo
  valen igual (`disco_2` = `disco2`). Las columnas desconocidas se ignoran con un aviso.
- Una celda vacía significa «usa el valor del perfil». Precedencia: valores por defecto,
  luego el perfil de la fila (columna `perfil`) o el **Perfil base** del diálogo, luego las
  columnas del CSV.
- Límites: hasta 100 filas, 40 columnas, 256 caracteres por celda y 1 MiB.
- Las filas se numeran como en Excel: el encabezado es la fila 1.
- Memoria en GiB si no pones unidad (admite `M`, `MiB`, `G`, `GiB`, `T`, `TiB`...). Disco en
  GiB. Si el número no lleva unidad, ProxLaunch lo avisa («se entendieron como GiB»): es
  solo un aviso, no un error. Se admite coma o punto decimal; un número como `1.000` es
  ambiguo y se rechaza.

### Columnas

Solo `nombre` es obligatoria. Las demás son opcionales.

| Columna (alias) | Obligatoria | Valores válidos | Ejemplo | Notas |
|---|---|---|---|---|
| `nombre` (`name`, `hostname`) | Sí | Nombre DNS: letras sin acentos, números y guiones; sin `_` ni guion al inicio o final | `web-01` | Un nombre que empieza por `ejemplo-` da un aviso (parece una fila de la plantilla). |
| `perfil` (`profile`) | No | Nombre visible del perfil o su id | `fabrica.servidor-mediano` | Con el id no depende del idioma. Si no existe o es ambiguo, error. Vacío = perfil base del diálogo. |
| `vmid` (`id`) | No | Entero 100 a 999 999 999 | `210` | Vacío = automático. No se puede repetir en el archivo. |
| `nodo` (`node`) | No | Nombre de un nodo en línea | `pve1` | Solo en clúster. Vacío = reparto automático. |
| `cpu` (`cores`, `nucleos`) | No | Entero 1 a 128 | `4` | Núcleos por socket. En un clon es un ajuste de núcleos. |
| `sockets` (`zocalos`) | No | Entero 1 a 4 | `1` | Uso avanzado. |
| `memoria` (`ram`, `memoria_gib`, `memoria_mib`) | No | Número con unidad opcional | `16 GiB`, `4096 MiB`, `4` | Sin unidad = GiB (o MiB si la columna se llama `memoria_mib`). Debe dar MiB enteros. |
| `disco` (`disco1`, `disco_gib`, `tamano_disco`) | No | GiB enteros desde 1; `0`, `ninguno` o `sin disco` = sin disco | `40`, `200 GiB` | Con `importar` significa «ampliar el disco a». Con `clonar`, tamaño del disco principal. |
| `almacenamiento` (`storage`, `almacenamiento1`) | No | Id de un almacenamiento con contenido de discos | `local-lvm` | Vacío = el del perfil o el de más espacio libre. |
| `disco2`...`disco8`, `almacenamiento2`...`almacenamiento8` | No | Igual que `disco` y `almacenamiento` | `500`, `datos` | Hasta 8 discos. Un almacenamiento sin tamaño en un disco que no existe es un error. |
| `red` (`bridge`, `red1`) | No | Nombre de un bridge | `vmbr0` | |
| `vlan` (`vlan1`) | No | Entero 1 a 4094 | `20` | |
| `modelo_red` (`tarjeta_red`) | No | `virtio` o `e1000` | `virtio` | Uso avanzado. |
| `firmware` (`bios`) | No | `seabios` (o `bios`), `ovmf` (o `uefi`) | `uefi` | |
| `tipo_cpu` (`cpu_tipo`) | No | Letras, números, `.`, `_` y `-` | `x86-64-v3` | Uso avanzado. |
| `origen` (`source`) | No | `vacio`, `iso`, `importar` (`imagen`), `clonar` (`plantilla`) | `iso` | Vacío = el origen del perfil. Conviene escribir `vacio` explícitamente si el perfil sugiere un ISO. |
| `fuente` (`origen_archivo`, `iso`, `plantilla`, `imagen`) | Sí, con `iso`, `importar` o `clonar` | Nombre del ISO (`.iso`, `.img`), de la imagen (`.qcow2`, `.raw`, `.vmdk`) o de la plantilla; también un volid `almacenamiento:iso/archivo.iso` | `ubuntu-24.04-server.iso` | **Nunca una URL ni una ruta del equipo.** Para descargar un archivo al servidor usa «Descargar en el servidor» dentro de la aplicación. |
| `so` (`sistema`) | No | `linux`, `windows 10`, `windows 11`, `windows server 2016/2019`, `windows server 2022/2025`, `otro` | `windows 11` | Solo con `iso` o `importar`. Aplica el asistente (UEFI, TPM, agente de QEMU, drivers). Es necesaria con `iso` si el perfil no define el sistema. |
| `virtio` (`drivers`) | No | `si` o `no` (también `yes`, `true`, `1`, `false`, `0`) | `si` | Solo Windows con `iso`. Vacío = detectar el ISO de virtio-win. |
| `modo_clon` (`clon`) | No | `auto`, `enlazado`, `completo` | `enlazado` | Solo con `clonar`. Vacío = `auto`. |

### Equivalencias que enseñan los ejemplos

- `origen=importar`: el `disco` de la fila es el tamaño al que se amplía el disco importado.
- `origen=clonar`: `cpu` y `memoria` son ajustes sobre la plantilla; si se dejan vacíos, la
  copia queda igual que la plantilla.
- `origen=iso` con `so=windows 11` y `virtio=si`: instala Windows 11 con el ISO de drivers
  virtio-win detectado en el servidor.

## `mvs-con-errores.csv`: lo que verás en la vista previa

El archivo tiene 8 filas de datos (filas 2 a 9 en la numeración de Excel). Al importarlo,
la vista previa indica **0 correctas, 1 con aviso** (la fila 2) **y 7 con error**. Usa
**Mostrar solo problemas** para filtrarlas y **Copiar errores** o **Descargar filas con error…**
para guardarlas.

Avisos de todo el archivo (no impiden importar):

- En la columna «memoria» había números sin unidad: se entendieron como GiB.
- En la columna «disco» había números sin unidad: se entendieron como GiB.
- En la columna «memoria», «GB» se tomó como GiB (1 GB = 1024 MiB).

Problemas por fila, con el texto exacto de la aplicación:

| Fila | Resultado | Texto |
|---|---|---|
| 2 | Aviso (se puede importar) | Fila 2, columna «nombre»: Parece una fila de ejemplo de la plantilla. |
| 3 | Error | Fila 3, columna «nombre»: Falta el nombre. |
| 4 | Error | Fila 4, columna «nombre»: El nombre solo puede tener letras sin acentos, números y guiones, y no puede empezar ni terminar con guion. |
| 5 | Error | Fila 5, columna «nombre»: Las filas 5, 6 tienen el mismo nombre «web-dup». |
| 5 | Error | Fila 5, columna «vmid»: Las filas 5, 6 tienen el mismo número de máquina «150». |
| 6 | Error | Fila 6, columna «nombre»: Las filas 5, 6 tienen el mismo nombre «web-dup». |
| 6 | Error | Fila 6, columna «vmid»: Las filas 5, 6 tienen el mismo número de máquina «150». |
| 7 | Error | Fila 7, columna «memoria»: «abc» no es un número. Escribe, por ejemplo, 4 GiB. |
| 8 | Error | Fila 8, columna «perfil»: No existe el perfil «fabrica.no-existe». Perfiles disponibles: Servidor pequeño, Servidor mediano, Base de datos, Servidor grande, Escritorio (hardware compatible). |
| 9 | Error | Fila 9, columna «fuente»: Aquí va el nombre de un archivo del servidor, no una dirección web. Para descargar usa «Descargar en el servidor». |
| 9 | Error | Fila 9, columna «fuente»: Elige un ISO. |

Qué practicar: corregir el archivo (botón **Corregir el archivo**), o importar solo las filas
correctas (**Importar solo las N filas correctas**).

La lista de «Perfiles disponibles» puede variar según la versión y los perfiles propios que tengas.

## Cómo adaptar los ejemplos

1. Copia el archivo que más se parezca a lo que necesitas.
2. Sustituye `almacenamiento`, `red`, `nodo` y los nombres de `fuente` por los de tu servidor.
3. Impórtalo y revisa la vista previa antes de continuar: ProxLaunch no crea nada hasta que
   confirmes en el resumen.
4. Si usas Excel o LibreOffice, guarda como «CSV (delimitado por comas / punto y coma)» en UTF-8.
