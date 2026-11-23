# Archivos de ejemplo de ProxLaunch

Esta carpeta reúne archivos listos para abrir en ProxLaunch y usarlos como modelo (estructura)
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
| `mvs-opciones.csv` | 4 MVs que usan las columnas de opciones de la versión 0.6: `encender`, `arranque_auto`, `notas`, `etiquetas`, `pool`, `proteger`, `mtu` y `limite_red`. Una fila lo fija todo, otra no fija nada (hereda lo del formulario) y las demás mezclan valores. | **Lote > Importar desde CSV…** |
| `mvs-cloudinit.csv` | 4 MVs que **clonan una plantilla** y la configuran en su primer arranque con las columnas de la versión 0.7: `ci_usuario`, `ci_claves`, `ci_ip` (`dhcp` o una IP fija), `ci_puerta`, `ci_dns` y `esperar_ip`. No lleva la columna `ci_contrasena` a propósito. | **Lote > Importar desde CSV…** |
| `mvs-red-firewall.csv` | 4 MVs con las columnas de la versión 0.8: `reescribir_red`, `cortafuegos`, `grupo_seguridad`, `politica_entrada` y `politica_salida`. Dos filas clonan una plantilla y cambian la red de la primera tarjeta, una clona sin cambiar la red y otra (disco vacío) deja el firewall apagado. | **Lote > Importar desde CSV…** |
| `lote-red-firewall.proxlaunch-lote.json` | Lote guardado de 4 MVs que clonan `plantilla-debian12`: cambian `net0` a `vmbr1` con VLAN 20, añaden una tarjeta `net1` en `vmbr0` (VirtIO) y activan el firewall con el grupo `web` (entrada Bloquear, salida Permitir). Es un archivo de **formato 5**: ProxLaunch 0.7.0 y anteriores no lo abren. | **Lote > Abrir lote…** (`Ctrl+O`) |
| `lote-homogeneo.proxlaunch-lote.json` | Lote guardado de 3 MVs iguales (`srv-web-01`...`srv-web-03`; 2 núcleos, 2 GiB, disco de 32 GiB). | **Lote > Abrir lote…** (`Ctrl+O`) |
| `lote-con-opciones.proxlaunch-lote.json` | El mismo lote de 3 servidores web, pero con las opciones de la versión 0.6 (encender, arrancar con el servidor con orden y espera, notas, etiquetas, pool, protección, MTU y límite de red). Es un archivo de **formato 3**: ProxLaunch 0.5.1 no lo abre. | **Lote > Abrir lote…** (`Ctrl+O`) |
| `lote-cloudinit.proxlaunch-lote.json` | Lote guardado de 4 MVs iguales (`srv-web-01`...`srv-web-04`) que clonan `plantilla-debian12` con cloud-init: usuario, una clave SSH, IP fija **en serie** (`192.0.2.50/24` sumando 1 a cada máquina), puerta de enlace, DNS y dominio; se enciende al terminar y espera la IP de cada máquina (plazo de 120 s). Es un archivo de **formato 4**: ProxLaunch 0.6.0 y anteriores no lo abren. | **Lote > Abrir lote…** (`Ctrl+O`) |
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
- Límites: hasta 100 filas, 70 columnas, 256 caracteres por celda (la columna `notas` admite
  hasta 8192) y 1 MiB.
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
| `encender` (`start`) | No | `si` o `no` (también `yes`, `true`, `1`, `false`, `0`) | `si` | Enciende la MV al terminar de crearla. Vacío = lo que marque el formulario. |
| `arranque_auto` (`onboot`) | No | `si` o `no` | `si` | La MV arranca con el servidor Proxmox. Vacío = lo que marque el formulario. |
| `notas` (`notes`) | No | Texto libre, hasta 8192 caracteres | `Servidor web de la oficina` | Va a las notas de la MV, tras el bloque automático si está activado. Vacío = lo del formulario. |
| `etiquetas` (`tags`) | No | Etiquetas separadas por `,` o `;` | `web,produccion` | Se suman a `proxlaunch` y `lote-…`. Vacío = las del formulario. |
| `pool` | No | Nombre de un pool existente (admite `padre/hijo`); `ninguno` = sin pool | `produccion` | Vacío = el pool del formulario. |
| `proteger` (`protection`) | No | `si` o `no` | `si` | Protege la MV contra borrado. Vacío = lo que marque el formulario. |
| `mtu` | No | `heredar`, `igual` (igual al bridge) o un número de 576 a 65520 | `1500` | Solo con tarjeta VirtIO. Se aplica a la **primera** tarjeta. Uso avanzado. |
| `limite_red` (`rate`) | No | Número mayor que 0, en MB/s (admite decimales con punto) | `100` | Se aplica a la **primera** tarjeta. Vacío = sin límite. Uso avanzado. |
| `ci_usuario` (`ciuser`, `ci_user`) | No | Nombre de usuario de Linux | `ana` | Usuario que crea cloud-init en el primer arranque. Solo con `clonar`. Vacío = el de la plantilla. |
| `ci_claves` (`sshkeys`, `ssh_keys`, `claves_ssh`) | No | Claves **públicas** SSH separadas por `;` (o salto de línea) | `ssh-ed25519 AAAA… ana@portatil` | Una clave privada se rechaza y no se copia en ningún informe. Vacío = las de la plantilla. |
| `ci_contrasena` (`cipassword`, `ci_password`) | No | Al menos 8 caracteres | | La única columna con un secreto. **No va en la plantilla CSV ni en estos ejemplos**: si la usas, el CSV queda con contraseñas en texto claro, la vista previa las muestra como `••••••`, ProxLaunch avisa y no las guarda en ningún archivo. Bórrala al terminar. Preferible: claves SSH. |
| `ci_ip` (`ipconfig0`) | No | `dhcp`, una IP con máscara (`192.0.2.51/24`) o `heredar` | `dhcp` | Tarjeta 1 (`net0`). Cada fila lleva su propia IP: la «IP en serie» solo existe en un lote del formulario. |
| `ci_puerta` (`puerta_enlace`) | No | Una dirección IPv4 | `192.0.2.1` | Solo con IP fija. |
| `ci_dns` (`nameserver`) | No | Direcciones separadas por espacio, coma o `;` | `192.0.2.2 192.0.2.3` | Uso avanzado. |
| `ci_dominio` (`searchdomain`, `dominio_busqueda`) | No | Dominio de búsqueda | `demo.example.com` | Uso avanzado. |
| `ci_actualizar` (`ciupgrade`) | No | `si` o `no` | `no` | Actualizar paquetes en el primer arranque. Uso avanzado. |
| `ci_snippet_usuario`, `ci_snippet_vendor`, `ci_snippet_red`, `ci_snippet_meta` | No | Un volid `almacenamiento:snippets/archivo.yaml` o `ninguno` | `local:snippets/agente.yaml` | Scripts de configuración ya guardados en el servidor. Uso avanzado. |
| `esperar_ip` (`wait_ip`, `wait_for_ip`) | No | `si` o `no` | `si` | Tras encender la MV, espera su IP por el agente invitado. Necesita `encender` en `si` (en la fila o en el formulario); si no, la fila da error. |
| `reescribir_red` (`rewrite_net`, `red_clon`) | No | `si` o `no` | `si` | Solo con `clonar`. `si` aplica `red`, `vlan`, `modelo_red`, `mtu` y `limite_red` a la primera tarjeta de la copia conservando su MAC; `no` la deja como la plantilla. Vacío = lo del formulario. Uso avanzado. |
| `cortafuegos` (`firewall`) | No | `si` o `no` | `si` | Activa el firewall de la MV. Vacío = lo del formulario. |
| `grupo_seguridad` (`security_group`, `firewall_group`) | No | Nombre de un grupo de seguridad (2 a 18 caracteres, empieza por letra; letras, números, `-` y `_`) | `web` | Debe existir en el servidor. Solo con `cortafuegos` en `si`. |
| `politica_entrada` (`policy_in`) | No | `bloquear` (`drop`) o `permitir` (`accept`) | `bloquear` | Qué pasa con la entrada que ninguna regla menciona. Uso avanzado. |
| `politica_salida` (`policy_out`) | No | `bloquear` (`drop`) o `permitir` (`accept`) | `permitir` | Igual, para la salida. Uso avanzado. |

### Equivalencias que enseñan los ejemplos

- `origen=importar`: el `disco` de la fila es el tamaño al que se amplía el disco importado.
- `origen=clonar`: `cpu` y `memoria` son ajustes sobre la plantilla; si se dejan vacíos, la
  copia queda igual que la plantilla.
- `origen=iso` con `so=windows 11` y `virtio=si`: instala Windows 11 con el ISO de drivers
  virtio-win detectado en el servidor.

## `mvs-opciones.csv`: las columnas de opciones

```text
"nombre";"perfil";"cpu";"memoria";"disco";"almacenamiento";"red";"encender";"arranque_auto";"notas";"etiquetas";"pool";"proteger";"mtu";"limite_red"
"web-01";"fabrica.servidor-mediano";"";"";"";"local-lvm";"vmbr0";"si";"si";"Servidor web de la oficina";"web,produccion";"produccion";"si";"1500";"100"
"web-02";"fabrica.servidor-mediano";"";"";"";"local-lvm";"vmbr0";"";"";"";"";"";"";"";""
"bd-01";"fabrica.base-de-datos";"";"";"";"local-lvm";"vmbr0";"no";"si";"Base de datos principal";"bd;produccion";"ninguno";"si";"igual";""
"lab-01";"fabrica.minimo";"";"";"";"local-lvm";"vmbr0";"no";"no";"";"laboratorio";"";"no";"heredar";"12.5"
```

Qué enseña cada fila:

- `web-01` lo fija todo: se enciende al terminar, arranca con el servidor, lleva notas, las etiquetas `web` y
  `produccion`, va al pool `produccion`, queda protegida contra borrado, con MTU 1500 y un límite de 100 MB/s.
- `web-02` deja vacías todas las columnas de opciones: usa lo que tengas marcado en el formulario al importar.
- `bd-01` separa las etiquetas con `;`, escribe `ninguno` en `pool` (sin pool aunque el formulario tenga uno) y
  pone el MTU «igual al bridge».
- `lab-01` escribe `no` donde otras filas escriben `si` (no se enciende, no arranca con el servidor, sin protección),
  `heredar` en `mtu` (anula el MTU del perfil) y un límite de 12.5 MB/s.

El pool `produccion` y los nombres de almacenamiento y red son inventados: para importar y crear de verdad,
sustitúyelos por los de tu servidor. Si tu usuario no tiene el privilegio que pide una opción (por ejemplo
`VM.PowerMgmt` para `encender`), la validación previa bloquea esas filas y dice cuál falta (ver la
[guía de usuario](../guia-usuario.md#privilegios-opcionales-no-forman-parte-del-rol)).

## `lote-con-opciones.proxlaunch-lote.json`: un lote guardado de formato 3

Es el lote `lote-homogeneo` con las opciones nuevas. Fíjate en tres cosas:

- `"version_formato": 3`. Un archivo que usa alguna opción nueva se escribe en formato 3; uno que no usa ninguna
  sigue escribiéndose en formato 1 o 2, que ProxLaunch 0.5.1 sí abre.
- Las opciones van dentro de `config` (`encender`, `arranque_auto`, `arranque_orden`, `arranque_espera`,
  `notas_origen`, `notas_usuario`, `notas`, `etiquetas_usuario`, `pool` y `proteger`) y, por tarjeta, en `redes` (`mtu` y
  `limite_mb`). Solo se escriben las que difieren de su valor por defecto.
- El bloque `opciones` repite las que valen para todo el lote; en un lote por filas, cada fila puede llevar su propio
  bloque `opciones` con lo que sobrescribe.

## `mvs-cloudinit.csv`: cloud-init y espera de la IP

```text
"nombre";"perfil";"origen";"fuente";"encender";"esperar_ip";"ci_usuario";"ci_claves";"ci_ip";"ci_puerta";"ci_dns"
"app-01";"fabrica.servidor-mediano";"clonar";"plantilla-debian12";"si";"si";"ana";"ssh-ed25519 AAAA… ana@portatil";"dhcp";"";""
"app-02";"fabrica.servidor-mediano";"clonar";"plantilla-debian12";"si";"si";"ana";"ssh-ed25519 AAAA… ana@portatil";"192.0.2.51/24";"192.0.2.1";"192.0.2.2"
"app-03";"fabrica.servidor-mediano";"clonar";"plantilla-debian12";"si";"si";"ana";"ssh-ed25519 AAAA… ana@portatil";"192.0.2.52/24";"192.0.2.1";"192.0.2.2"
"bd-01";"fabrica.base-de-datos";"clonar";"plantilla-ubuntu";"si";"no";"ana";"ssh-ed25519 AAAA… ana@portatil";"192.0.2.60/24";"192.0.2.1";"192.0.2.2"
```

(En el archivo la clave va completa; aquí se abrevia.) Qué enseña cada fila:

- `app-01` pide su IP por DHCP (`dhcp`): no necesita puerta de enlace ni DNS.
- `app-02` y `app-03` llevan IP fija, cada una con la suya, la misma puerta de enlace y los mismos DNS.
- `bd-01` clona otra plantilla, también con IP fija, y **no** espera su IP (`esperar_ip` en `no`).
- Todas llevan `encender` en `si`: sin encender la máquina no hay IP que esperar.

La clave SSH es **falsa** (tiene el formato de una clave pública, pero no hay clave privada detrás): sustitúyela
por la tuya. Los nombres de plantilla, las IPs (rango de documentación `192.0.2.0/24`) y los DNS son inventados.
Para usar cloud-init, la plantilla debe tener una unidad cloud-init; si no la tiene, ProxLaunch lo avisa en
la validación (en la vista previa y en el resumen).

El archivo **no** trae la columna `ci_contrasena`: una contraseña en un CSV queda en texto claro. Si la añades,
ProxLaunch lo avisa y la muestra enmascarada.

## `lote-cloudinit.proxlaunch-lote.json`: un lote guardado de formato 4

Es el lote `lote-homogeneo` con cloud-init y la espera de IP, escrito por el propio ProxLaunch. Fíjate en:

- `"version_formato": 4`: un archivo que usa cloud-init o la espera de IP se escribe en formato 4.
- `origen` vale `clonar_plantilla` y `detalle_origen.plantilla` nombra la plantilla (`plantilla-debian12`), no su
  número: así el lote vale en otro servidor que tenga una plantilla con ese nombre.
- El bloque `cloudinit` guarda usuario, claves públicas, DNS, dominio y las tarjetas. La tarjeta 0 es de IP fija
  con `"serie": true`: la IP de `ip` es la de la primera máquina y cada una de las demás suma 1.
- `esperar_ip` (`activo` y `plazo_s`) y `encender` también van en `config`.
- **Nunca se guarda una contraseña** de cloud-init: si la habías escrito en el formulario, al abrir el lote
  habrá que volver a escribirla.

Las IPs, la clave y los nombres son inventados; sustitúyelos por los de tu red.

## `mvs-red-firewall.csv`: red del clon y firewall

```text
"nombre";"origen";"fuente";"reescribir_red";"red";"vlan";"cortafuegos";"grupo_seguridad";"politica_entrada";"politica_salida"
"web-01";"clonar";"plantilla-debian12";"si";"vmbr1";"20";"si";"web";"bloquear";"permitir"
"web-02";"clonar";"plantilla-debian12";"no";"";"";"si";"ssh";"bloquear";"permitir"
"bd-01";"clonar";"plantilla-ubuntu";"si";"prod";"";"si";"bd";"bloquear";"bloquear"
"lab-01";"vacio";"";"";"vmbr0";"";"no";"";"";""
```

Qué enseña cada fila:

- `web-01` cambia `net0` a `vmbr1` con VLAN 20 (conserva la MAC) y activa el firewall con el grupo `web`.
- `web-02` deja la red **como la plantilla** (`reescribir_red` = `no`: las columnas de red de un clon no se aplican) y activa
  el firewall con el grupo `ssh`.
- `bd-01` mueve `net0` a la red virtual `prod` y bloquea también el tráfico de salida.
- `lab-01` no clona (disco vacío), usa `vmbr0` como siempre y deja el firewall apagado.

Los grupos `web`, `ssh` y `bd`, la red virtual `prod` y las plantillas son inventados: los grupos de seguridad los crea tu
administrador en Proxmox y deben existir en tu servidor (la validación avisa si no). Una fila con firewall activo, **sin
grupo** y con la entrada en Bloquear deja la máquina sin acceso por la red y da error: elige siempre un grupo o pon
`politica_entrada` en `permitir`.

## `lote-red-firewall.proxlaunch-lote.json`: un lote guardado de formato 5

Es un lote de cuatro servidores que clonan `plantilla-debian12`. Fíjate en:

- `"version_formato": 5`: un archivo que usa la red del clon personalizada o el firewall se escribe en formato 5.
- `red_clon`: `modo` `personalizar` y una lista de `tarjetas`. La tarjeta 0 es de acción `cambiar`: solo las claves presentes
  (`bridge`, `vlan`) se cambian y lo demás se conserva, MAC incluida. La tarjeta 1 es de acción `añadir` y lleva todos sus
  valores.
- `firewall`: `activo`, `grupo`, `politica_entrada`, `politica_salida` y `dhcp` (`auto`: se permite el DHCP si alguna tarjeta
  usa DHCP en cloud-init). **Nunca se guarda** la confirmación «Entiendo que la máquina no aceptará conexiones por la red».

Los nombres de red, de grupo y de plantilla son inventados; sustitúyelos por los de tu servidor.

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
