# Guía de usuario de ProxLaunch (MVP 1, MVP 2, MVP 3 y MVP 4)

ProxLaunch te ayuda a crear una o varias máquinas virtuales en un servidor Proxmox sin
tener que conocer todos sus detalles. Esta guía te lleva paso a paso. No necesitas saber
de Proxmox: cada término se explica la primera vez que aparece.

Desde el MVP 3 también puedes **reutilizar configuraciones** (perfiles de máquina), **guardar
y abrir lotes** como archivos, **importar máquinas desde una hoja de cálculo (CSV)** y crear
un **lote por filas** en el que cada máquina tiene su propia configuración.

Desde el MVP 4 también puedes **elegir de dónde sale el sistema operativo** de la máquina:
instalar desde un **ISO** (con un asistente para Windows y Linux), **usar un disco existente**
(qcow2, vmdk o raw) o **copiar una plantilla** de Proxmox. Además puedes subir un ISO desde tu
equipo o hacer que el servidor lo descargue. Mira [Elegir el origen del sistema operativo](#elegir-el-origen-del-sistema-operativo).

Los nombres de botones, menús y mensajes de esta guía son los que ves en la aplicación.

> ProxLaunch se probó contra un Proxmox VE 9.2 real (servidor individual). Los clústeres
> de varios nodos y Proxmox 8.x se han probado solo con respuestas simuladas. Eso incluye
> el reparto de un lote entre varios nodos y la importación de discos en Proxmox 8.4 o
> superior. Tampoco se ha probado con un ISO de Windows real: las pruebas del laboratorio
> usaron Linux (Alpine).

## Contenido

1. [Palabras que conviene conocer](#palabras-que-conviene-conocer)
2. [Antes de empezar](#antes-de-empezar)
3. [Primera conexión y la huella del servidor](#primera-conexión-y-la-huella-del-servidor)
4. [Crear una máquina en modo básico](#crear-una-máquina-en-modo-básico)
5. [Modo avanzado](#modo-avanzado)
6. [Elegir el origen del sistema operativo](#elegir-el-origen-del-sistema-operativo)
   - [Permisos para el administrador: alcance acotado](#permisos-para-el-administrador-alcance-acotado)
7. [Entender el progreso y los resultados](#entender-el-progreso-y-los-resultados)
8. [Crear varias máquinas de una vez (lotes)](#crear-varias-máquinas-de-una-vez-lotes)
9. [Perfiles de máquina](#perfiles-de-máquina)
10. [Guardar y abrir lotes](#guardar-y-abrir-lotes)
11. [Importar máquinas desde un CSV](#importar-máquinas-desde-un-csv)
12. [Lote por filas](#lote-por-filas)
13. [Cambios sin guardar](#cambios-sin-guardar)
14. [Mensajes de error frecuentes](#mensajes-de-error-frecuentes)
    - [Mensajes del origen del sistema operativo](#mensajes-del-origen-del-sistema-operativo)
15. [Privacidad y seguridad](#privacidad-y-seguridad)
16. [Preguntas frecuentes](#preguntas-frecuentes)

---

## Palabras que conviene conocer

| Palabra | Qué significa |
|---|---|
| **Proxmox VE** | El programa instalado en tus servidores que permite crear y gestionar máquinas virtuales. |
| **Máquina virtual (MV)** | Un «ordenador dentro del servidor». Tiene su propio procesador, memoria, disco y red, pero son virtuales. |
| **Nodo** | Cada servidor físico de Proxmox. |
| **Clúster** | Varios nodos que trabajan juntos. Si tienes un solo servidor, ProxLaunch lo llama «Servidor individual». |
| **Almacenamiento (storage)** | El lugar del servidor donde se guardan los discos de las máquinas. |
| **Bridge (red)** | El «conmutador virtual» que conecta la máquina a tu red. Lo habitual es `vmbr0`. |
| **VMID (número de máquina)** | El número que identifica a la máquina en todo el servidor (desde 100). No se puede repetir. |
| **API Token** | Una «llave» que un administrador crea para que una aplicación entre a Proxmox sin usar una contraseña personal. Se escribe `usuario@realm!nombre=secreto`. |
| **Realm** | De dónde viene la cuenta de usuario. Los más comunes son `pam` (usuarios del sistema) y `pve` (usuarios propios de Proxmox). |
| **Huella (del certificado)** | La «firma» del servidor, una cadena de letras y números. Sirve para comprobar que hablas con el servidor correcto y no con uno falso. |
| **2FA (segundo factor)** | Un segundo paso de seguridad al iniciar sesión: normalmente un código de 6 números que muestra una aplicación en tu teléfono. |
| **Tarea (UPID)** | Cuando pides crear una máquina, Proxmox abre una «tarea». El UPID es el identificador de esa tarea. |
| **Firmware (tipo de arranque)** | El programa con el que arranca la máquina: SeaBIOS (clásico) o UEFI (moderno). |
| **Lote** | Un grupo de máquinas que se crean de una vez. Normalmente son iguales y solo cambian el nombre, el número y, si hay clúster, el nodo (ver también «Lote por filas»). |
| **Etiqueta** | Una marca de texto que Proxmox muestra junto a la máquina. ProxLaunch usa dos para reconocer lo que creó. |
| **Perfil de máquina** | Una configuración de hardware ya preparada (procesadores, memoria, discos y red) que rellena el formulario de un clic. No es una plantilla de Proxmox ni un perfil de conexión. |
| **Lote guardado** | Un archivo `.json` con la definición de un lote, para repetirlo otro día. No guarda datos de conexión. |
| **CSV** | Un archivo de texto con una tabla, que puedes crear y editar con Excel o LibreOffice Calc. Cada fila es una máquina. |
| **Lote por filas** | Un lote en el que cada máquina trae su propia configuración (el caso de un CSV con máquinas distintas). |
| **ISO** | Un archivo que es la imagen del disco de instalación de un sistema operativo, como el CD con el que se instalaría. |
| **Origen del sistema operativo** | De dónde sale el sistema de la máquina: un disco vacío, un ISO, un disco ya hecho que se importa o la copia de una plantilla. |
| **Plantilla (de Proxmox)** | Una máquina ya instalada que se marcó como modelo. Al clonarla obtienes máquinas nuevas con su mismo sistema. No es un perfil de máquina. |
| **Clon enlazado y completo** | Un clon enlazado comparte el disco base con la plantilla (rápido y casi sin espacio, pero depende de ella). Un clon completo copia todo el disco y es independiente. |
| **virtio-win** | Un CD de controladores (drivers) que Windows necesita para ver el disco y la red virtuales de Proxmox. |
| **Huella de un archivo (SHA-256)** | Un código que identifica un archivo. Si dos copias tienen la misma huella, son idénticas. |
| **Contenido de un almacenamiento** | Lo que un almacenamiento admite guardar: discos de máquinas (`images`), ISOs (`iso`) o discos para importar (`import`). |

---

## Antes de empezar

Necesitas tres cosas de tu administrador de Proxmox:

1. **La dirección del servidor:** una IP (por ejemplo `192.0.2.10`) o un nombre (por
   ejemplo `pve1`). El puerto casi siempre es `8006`.
2. **Una forma de entrar:** un **API Token** (recomendado) o un usuario y contraseña.
3. **La huella del certificado del servidor**, para compararla la primera vez que te
   conectes.

### Permisos que hacen falta

Para crear máquinas, la cuenta necesita ciertos permisos. Lo más cómodo es que el
administrador cree un **rol** llamado `ProxLaunchCreador` con estos privilegios:

```text
VM.Allocate
VM.Audit
VM.Config.Options
VM.Config.HWType
VM.Config.CPU
VM.Config.Memory
VM.Config.Network
Datastore.AllocateSpace
SDN.Use
Sys.Audit
VM.Config.Disk
VM.Clone
Datastore.AllocateTemplate
Sys.AccessNetwork
```

Los **10 primeros** se comprobaron en un Proxmox real: son los mínimos para crear máquinas con
disco vacío. Los **4 últimos** (desde el MVP 4) sirven para instalar desde un ISO, subir o
descargar archivos, importar discos y clonar plantillas:

| Privilegio | Para qué sirve |
|---|---|
| `VM.Config.Disk` | Fijar el orden de arranque con un ISO y ampliar discos. |
| `VM.Clone` | Clonar plantillas. |
| `Datastore.AllocateTemplate` | Subir y descargar ISOs e imágenes de disco. |
| `Sys.AccessNetwork` | Que el servidor descargue archivos desde una dirección web. |

Si no los das, crear máquinas vacías sigue funcionando y ProxLaunch solo desactiva esas
opciones, indicando qué permiso falta. Donde asignar estos permisos (en todo el servidor o solo
donde hacen falta) se explica en
[Permisos para el administrador: alcance acotado](#permisos-para-el-administrador-alcance-acotado).

**Crear lotes,
etiquetar las máquinas y deshacer un lote no piden ningún permiso más**: borrar una máquina
solo exige `VM.Allocate`, que ya está en la lista. Hay una excepción, que depende de cómo
configuró tu administrador Proxmox (ver [Etiquetas](#etiquetas-qué-son-y-para-qué-sirven)).
- Sin `VM.Audit`, la máquina se crea, pero ProxLaunch no puede confirmar cómo quedó y lo
  verás como «creada con avisos».
- Sin `Sys.Audit`, la máquina se crea, pero no verás la memoria y los procesadores libres de
  cada nodo ni el estado del clúster.
- Sin cualquiera de los demás, Proxmox rechaza la creación. ProxLaunch te avisa al conectar
  de los permisos que faltan.

### Cómo se prepara (pasos para el administrador)

ProxLaunch trae estos mismos pasos en el menú **Ayuda > ¿Cómo creo un API Token?**
y también en el enlace «¿Cómo creo un API Token?» de la pantalla de conexión.

1. En la página web de Proxmox, ve a **Datacenter → Permisos → Roles → Crear**. Llama al
   rol `ProxLaunchCreador` y marca los privilegios de la lista de arriba.
2. Ve a **Datacenter → Permisos → Usuarios** y crea un usuario para ProxLaunch (por
   ejemplo `proxlaunch@pve`), o usa uno que ya tengas.
3. Ve a **Datacenter → Permisos → Tokens de API → Añadir**. Elige el usuario, escribe un
   nombre para el token (por ejemplo `lab`) y pulsa **Añadir**. **Copia el secreto que se
   muestra: solo aparece una vez.**
4. Ve a **Datacenter → Permisos → Añadir → Permiso de usuario** (o **de token**). Pon la
   ruta `/`, elige el usuario o el token, el rol `ProxLaunchCreador` y deja marcado
   **Propagar**. Esta es la **alternativa simple**: es cómoda, pero da el permiso sobre todo el
   servidor. Si vas a usar ISOs, importar discos o clonar plantillas, lo recomendado es el
   [alcance acotado](#permisos-para-el-administrador-alcance-acotado).
5. En ProxLaunch, pega el token completo con el formato `usuario@realm!nombre=secreto`.
   Por ejemplo: `proxlaunch@pve!lab=11111111-2222-3333-4444-555555555555`.

Recomendaciones de la propia aplicación:

- Usa siempre un token con los permisos mínimos en lugar de `root@pam`. Si el token se
  filtra, el daño es mucho menor y puedes revocarlo sin cambiar contraseñas.
- Al crear el token puedes desmarcar **Separación de privilegios** solo si ya asignaste los
  permisos al usuario. Si la dejas marcada, el token necesita sus propios permisos
  (paso 4, eligiendo el token).

Un token **no pasa por el segundo factor (2FA)**. Si tu usuario exige un método de 2FA que
ProxLaunch no admite, el token es la salida.

---

## Primera conexión y la huella del servidor

### Abrir la ventana de conexión

Al abrir ProxLaunch ves el mensaje «Conecta con tu servidor Proxmox para empezar».
Pulsa **Conectar...** (o usa el menú **Archivo > Conectar...**, atajo `Ctrl+K`).

### Rellenar los datos

En la ventana **Conectar con Proxmox**:

| Campo | Qué poner |
|---|---|
| **Perfil guardado** | Elige un perfil que ya guardaste, o deja «(Perfil nuevo)». |
| **Nombre del perfil** | Un nombre que te ayude a reconocerlo (por ejemplo `Oficina`). |
| **Servidores (IP o nombre)** | Un servidor por línea (por ejemplo `192.0.2.10`). Si pones varios, ProxLaunch prueba el primero y, si no responde, el siguiente. |
| **Puerto** | `8006`, salvo que tu administrador diga otro. |
| **Método** | **API Token (recomendado)** o **Usuario y contraseña**. |
| **Token** | Con el método token: `usuario@realm!nombre=secreto`. |
| **Usuario / Realm / Contraseña** | Con el método usuario y contraseña. El realm por defecto es `pam`. |
| **Recordar credenciales** | Guarda el token o la contraseña en el llavero de tu sistema. Viene **desmarcada**. Déjala así en equipos compartidos. |

Puedes pegar la dirección con `https://` y el puerto; ProxLaunch lo interpreta. Tampoco
tienes que escribir `root@pam` dos veces: si escribes el usuario completo, se normaliza.

Botones de la ventana:

- **Probar y conectar:** intenta conectar.
- **Guardar perfil:** guarda los datos (sin el secreto, salvo que hayas marcado
  «Recordar credenciales»).
- **Duplicar** y **Eliminar:** copian o borran el perfil elegido. Al eliminar, también se
  borran sus credenciales del llavero y las huellas que solo usaba ese perfil.
- **Cancelar:** cierra la ventana sin conectar.

Si usas `root@pam`, ves el aviso «Estás usando root@pam. Es más seguro usar un API Token con
permisos mínimos.» No te bloquea, solo te lo recomienda.

### La huella del servidor

La primera vez que te conectas a un servidor, ProxLaunch **no envía tu token ni tu
contraseña todavía**. Antes te muestra la ventana **Confiar en este servidor**, con el
servidor, el puerto y la **Huella SHA-256**.

1. Pide a tu administrador la huella del certificado del servidor.
2. Compara las dos. Deben ser idénticas.
3. Si coinciden, pulsa **Confiar y continuar**. Si no coinciden o tienes dudas, pulsa
   **Cancelar**: no se conecta y no se guarda nada.

ProxLaunch guarda la huella de ese servidor y puerto. Las siguientes veces no pregunta.

> Si aparece este texto: «No tenemos registro de este servidor porque el archivo de
> huellas se dañó…», significa que ProxLaunch perdió su lista de servidores conocidos.
> Compara la huella con la de tu administrador antes de confiar, como si fuera la primera vez.

### Si aparece «El certificado del servidor cambió»

Se abre la ventana **El certificado del servidor cambió**. Muestra la **huella guardada**
y la **huella nueva**, con este aviso: «El certificado del servidor cambió. Podría ser un
cambio legítimo (renovación) o un intento de suplantación. Verifica con tu administrador.»

No se envía ninguna credencial. Qué hacer:

1. Pulsa **Cerrar**. No se conecta.
2. Pregunta a tu administrador si renovó el certificado del servidor. Si lo hizo, te dará
   la huella nueva.
3. Si la huella nueva coincide con la que te dio y confías, tienes dos opciones:
   - En **modo básico** no hay botón para continuar. Cambia a **Ajustes > Modo > Avanzado**
     y vuelve a intentarlo.
   - En **modo avanzado** aparece **Reemplazar la huella guardada**. ProxLaunch te pide
     confirmación antes de reemplazarla.
4. Si el administrador **no** cambió nada, no te conectes: podría ser un intento de
   suplantación. Avísale.

### Si el servidor pide un código (2FA)

Si tu cuenta tiene segundo factor, tras escribir el usuario y la contraseña aparece la
ventana **Código de verificación**:

- Escribe los 6 números que muestra tu aplicación de autenticación y pulsa **Verificar**.
- Si no puedes acceder a la aplicación, pulsa **Usar una clave de recuperación** y escribe
  una de tus claves. Cada clave solo sirve **una vez**; ProxLaunch te lo recuerda al conectar.
- Con **Usar el código de la aplicación** vuelves al código de 6 números.
- Si el código falla, el mensaje es «El código no es correcto o ya venció. Espera al
  siguiente código e inténtalo de nuevo.» Puedes reintentar sin escribir otra vez el
  usuario y la contraseña.

ProxLaunch **no guarda** el código ni las claves de recuperación.

Si el servidor exige otro método de 2FA distinto (como llaves de seguridad), verás: «Este
usuario exige un método de segundo factor que ProxLaunch no admite. Usa un API Token.»

### Cuando se conecta

Entras a la ventana de trabajo. La barra superior muestra el nombre del perfil, la versión
(por ejemplo «Proxmox VE 9.2») y «Servidor individual» o «Clúster «nombre» — 3 nodos».
Debajo, la barra de estado dice «Conectado».

Si usaste varios servidores y el primero no respondía, verás «Conectado a 192.0.2.11
(192.0.2.10 no respondió)». Es normal.

ProxLaunch lee entonces los nodos, almacenamientos y redes ("Buscando nodos,
almacenamientos y redes..."). El botón **Actualizar** repite esa lectura.

Avisos que pueden aparecer arriba:

- «Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate». El botón
  **Crear máquina** quedará desactivado. Pide el permiso a tu administrador.
- «A tu usuario le faltan permisos recomendados (…). Algunas acciones podrían fallar.»
- «Topología desconocida (N nodos): a tu usuario le falta el permiso Sys.Audit en «/» para
  ver el clúster. Puedes seguir trabajando.»
- Un aviso si el servidor es más nuevo que la última versión que ProxLaunch ha probado.
  Puedes continuar.
- Si el servidor tiene Proxmox VE 7 o anterior, ProxLaunch no puede usarse: «ProxLaunch
  requiere Proxmox VE 8.0 o superior».

---

## Crear una máquina en modo básico

El **modo básico** es el que ves la primera vez. Muestra lo imprescindible y usa valores
seguros para el resto. Pasa el ratón por encima de un campo o de los títulos de las
columnas para leer una ayuda corta.

El formulario tiene cinco secciones. Con los valores por defecto, normalmente solo
necesitas escribir el **nombre**.

### General

- **Número de máquina (VMID):** ProxLaunch propone el siguiente libre. Cámbialo solo si
  necesitas uno concreto (entre 100 y 999999999). Si el número ya existe, verás: «El número
  N ya lo usa otra máquina. Prueba con M».
- **Nombre:** por ejemplo `srv-web-01`. Solo letras sin acentos, números y guiones; no
  puede empezar ni terminar con guion.
- **Nodo destino:** solo aparece si hay un clúster. En **Automático** ProxLaunch elige el
  nodo con más memoria y espacio libres y te dice cuál y por qué (por ejemplo, «Nodo
  elegido: pve1 (más memoria y espacio libres)»). En **Manual** eliges tú. Los nodos
  caídos aparecen como «Sin conexión» y no se pueden elegir. En un servidor individual no
  hay selector.

### Firmware

- **Tipo de arranque:** **SeaBIOS (clásico)** sirve para casi todo. **UEFI (OVMF)** lo piden
  algunos sistemas, como Windows 11.

### Cómputo

- **Sockets:** un socket es un procesador físico virtual. Deja 1.
- **Núcleos por socket:** por defecto 2. ProxLaunch te muestra el total («2 procesadores
  virtuales en total»).
- **Memoria (GiB):** por defecto 2. Puedes usar decimales (por ejemplo `0,5`).

### Discos

- Por defecto hay un disco de **32 GiB** en el almacenamiento con más espacio libre. Cada
  almacenamiento se muestra con su tipo y espacio, por ejemplo «local-lvm (lvmthin,
  150 GiB libres)».
- Puedes cambiar el **Almacenamiento** y el **Tamaño (GiB)** (número entero, mínimo 1).
- **Agregar disco** añade otro. **Quitar** elimina uno (siempre queda al menos uno).
- **Sin disco** crea la máquina sin ningún disco. Es útil si lo añadirás o importarás
  después.
- Con el origen **Vacía, sin sistema operativo** (el predeterminado), el disco se crea
  **vacío**: ProxLaunch **no instala ningún sistema operativo**. Eso lo haces tú después, desde
  Proxmox. Si prefieres instalar desde un ISO, usar un disco que ya tienes o copiar una
  plantilla, mira [Elegir el origen del sistema operativo](#elegir-el-origen-del-sistema-operativo).

### Red

- Por defecto hay una interfaz conectada a **`vmbr0`** (o, si no existe, a la primera red
  del nodo).
- Puedes cambiar la **Red (bridge)** y poner una **VLAN** (entre 1 y 4094; vacío si tu red
  no usa VLAN). **Agregar interfaz** añade otra.
- Si el nodo no tiene redes, verás: «El nodo no tiene redes (bridges) disponibles», y no
  podrás crear la máquina.

### Resumen y crear

A la derecha, el panel **Resumen** muestra en lenguaje llano lo que se va a crear: nombre,
número, nodo, arranque, procesadores, memoria, discos y redes.

- Si algo está mal, el panel lo lista bajo «Para crear la máquina hay que corregir:» y el
  botón **Crear máquina** queda desactivado. Cada error también aparece junto a su campo.
- Si un valor oculto del modo avanzado no es el predeterminado, el resumen lo muestra bajo
  «Opciones avanzadas que se aplicarán (ocultas en modo básico)». Nada se aplica a escondidas.
- Pueden aparecer avisos que **no** bloquean. Por ejemplo, si pides más núcleos o memoria
  de los que tiene el nodo, o si un almacenamiento «solo ocupa el espacio a medida que se
  usa» y los discos suman más de lo libre.
- Cuando todo esté bien, pulsa **Crear máquina**.

La máquina se crea **detenida**. ProxLaunch no la enciende.

---

## Modo avanzado

Cámbialo en **Ajustes > Modo > Avanzado**. Al cambiar, no pierdes lo que ya escribiste, y
ProxLaunch recuerda tu elección. Al volver a **Básico**, las opciones que cambiaste se
**conservan** (solo se ocultan) y el resumen te las sigue mostrando.

| Opción | Dónde | Qué significa |
|---|---|---|
| **Almacenamiento de UEFI** | Firmware (solo si eliges UEFI) | Dónde se guarda la configuración de UEFI. «Automático (el del primer disco)» suele ser lo correcto. |
| **Tipo de CPU** | Cómputo | Qué procesador «ve» la máquina. El predeterminado, `x86-64-v2-AES`, funciona entre servidores distintos. `host` rinde más pero impide mover la máquina entre nodos con procesadores diferentes. También están `x86-64-v2`, `x86-64-v3`, `x86-64-v4` y `kvm64`. |
| **Ballooning** | Cómputo | Permite que el servidor recupere memoria que la máquina no usa. «Predeterminado de Proxmox» deja que Proxmox decida; **Activado** te pide la **Memoria mínima (GiB)** (no puede superar la memoria total); **Desactivado** lo apaga. |
| **Controlador SCSI** | Discos | El controlador que gestiona los discos SCSI. `virtio-scsi-single` (predeterminado) es el mejor y el único que permite IO Thread; también está `virtio-scsi-pci`. |
| **Conexión (bus)** | Discos | El tipo de conexión del disco virtual: SCSI (recomendado), VirtIO (muy rápido, pero necesita controladores en algunos sistemas), SATA e IDE (los más compatibles y los más lentos). |
| **Formato** | Discos | Cómo se guarda el disco. **raw** ocupa todo el espacio y es el más rápido. **qcow2** crece según se usa y permite instantáneas. En algunos almacenamientos solo se admite raw y el campo aparece desactivado como «(automático, raw)». |
| **Discard** | Discos | Avisa al almacenamiento de qué espacio ya no se usa para que lo recupere. Conviene dejarlo activado. |
| **SSD** | Discos | Hace que el sistema vea el disco como una unidad de estado sólido. No está disponible con el bus VirtIO. |
| **IO Thread** | Discos | Dedica un hilo propio a atender el disco, lo que mejora el rendimiento con mucha actividad. Necesita el bus VirtIO, o SCSI con `virtio-scsi-single`. |
| **Tarjeta** | Red | El tipo de tarjeta de red: **VirtIO** (la más rápida) o **Intel E1000** (más compatible con sistemas antiguos). |

Las casillas que no se pueden usar en una combinación (por ejemplo SSD con VirtIO) se
desactivan, y al pasar el ratón por encima ves el motivo.

En la ventana de conexión, el modo avanzado añade dos opciones:

- **Ignorar verificación SSL:** acepta cualquier certificado sin comprobarlo. **Es
  inseguro.** Úsalo solo en redes de prueba que controles. Con esta opción activa, la barra
  superior muestra «⚠ Conexión sin verificar». Si además usas contraseña, ProxLaunch te pide
  confirmar en cada conexión.
- **Forzar compatibilidad con la versión...:** hace que ProxLaunch se comporte como si el
  servidor tuviera otra versión de Proxmox. «Detectada» es lo normal. Solo para casos
  especiales; la barra superior lo marca como «(forzada)».

Si vuelves a modo básico, ProxLaunch vuelve a verificar siempre por huella, aunque el
perfil tuviera «Ignorar verificación SSL» activo.

### Cambiar el tema

**Ajustes > Tema** ofrece **Automático** (sigue el tema claro u oscuro de tu sistema, en
vivo), **Oscuro** y **Claro**. Si la detección falla (es frecuente en Linux), se usa el
oscuro. Elige a mano si lo necesitas.

---

## Elegir el origen del sistema operativo

Hasta ahora la máquina se creaba con un disco vacío. Desde el MVP 4, arriba del formulario
aparece la pregunta **¿Cómo quieres crear la máquina?** con cuatro opciones. ProxLaunch **no
enciende** la máquina en ninguna de ellas: la crea detenida y, si instalas desde un ISO, tú
terminas la instalación desde la consola de Proxmox.

### Las cuatro opciones

| Opción | Cuándo usarla |
|---|---|
| **Vacía, sin sistema operativo** | Es la de siempre: «La máquina se crea con un disco vacío y sin sistema operativo. Instálalo después desde la consola de Proxmox.» |
| **Instalar desde un archivo ISO** | Quieres instalar un sistema desde cero. La máquina arranca desde el ISO. |
| **Usar un disco existente (qcow2, vmdk, raw)** | Ya tienes un disco con el sistema instalado y quieres que la máquina nueva lo use. |
| **Copiar una plantilla de Proxmox** | Tu administrador dejó una máquina ya instalada como modelo y quieres copias de ella. |

Si no sabes cuál elegir, la ayuda del campo lo resume: usa un ISO para instalar desde cero o una
plantilla para empezar con algo ya instalado.

- Una opción que no se puede usar en tu servidor **no se oculta**: aparece desactivada con el
  motivo escrito debajo (por ejemplo, que falta un permiso o que el servidor no tiene un
  almacenamiento con el contenido necesario). Sin conexión, las tres últimas dicen «Conéctate a un
  servidor para ver si esta opción está disponible.»
- El enlace **¿Por qué no puedo usar alguna opción?** (también en **Ayuda > Qué puedo hacer en este
  servidor…**) abre **Qué puedo hacer en este servidor**: una tabla con **Qué quieres hacer**,
  **Estado** y **Por qué**, y un texto **Qué pedirle a tu administrador** que puedes copiar con
  **Copiar texto para el administrador** y enviarle.
- Si ya elegiste un archivo o una plantilla y cambias de opción, ProxLaunch pregunta (**Cambiar la
  forma de crear la máquina**): «Si cambias, se pierde lo que elegiste: …». Elige **Cambiar** o
  **Cancelar**.
- Mientras corre un lote, el selector queda bloqueado.

### Instalar desde un archivo ISO

Un **ISO** es la imagen del disco de instalación de un sistema operativo, como el CD con el que se
instalaría. Al elegir esta opción:

1. Pulsa **Elegir ISO…**. Se abre **Elegir un archivo ISO**: «Estos son los archivos ISO que hay en
   el servidor. Si el tuyo no está, súbelo desde tu equipo o haz que el servidor lo descargue.»
2. Escribe en **Filtrar por nombre** para encontrar el tuyo. Las filas que no se pueden elegir
   quedan desactivadas con el motivo escrito. Con **Actualizar** vuelves a leer el servidor.
3. Si el ISO no está, usa **Subir desde mi equipo…** o **Descargar en el servidor…** (ver más
   abajo). Al terminar, el archivo nuevo queda elegido.
4. Elige el ISO y pulsa **Elegir**. Debajo del botón verás su nombre.
5. Elige el **Sistema operativo** (ver [El asistente de sistema operativo](#el-asistente-de-sistema-operativo)).
6. Pulsa **Crear máquina** como siempre.

La máquina se crea con el ISO puesto como CD y con el orden de arranque disco, CD y red. Fijar ese
orden necesita el permiso `VM.Config.Disk`: si no hay certeza de que lo tienes, ProxLaunch crea la
máquina sin fijar el orden. En ese caso pide a tu administrador que, en Proxmox, ponga el CD
en el orden de arranque de la máquina (pestaña «Opciones» → «Orden de arranque»).

### El asistente de sistema operativo

En el grupo **Sistema operativo** eliges qué vas a instalar (**Elige el sistema operativo…**):
**Linux**, **Windows 11**, **Windows Server 2022 / 2025**, **Windows 10**,
**Windows Server 2016 / 2019** u **Otro sistema**. El asistente ajusta la máquina a ese sistema:
tipo de arranque, TPM, controlador de discos y tarjeta de red. **No toca** los núcleos, la
memoria ni el tamaño del disco.

Antes de crear nada ves exactamente qué cambió, con el aviso «Para Windows 11 el asistente va a
cambiar:» y una lista de líneas «antes → después» (o «Para … no hace falta cambiar nada más.»).

| Sistema | Qué ajusta el asistente |
|---|---|
| **Linux** | Controlador `virtio-scsi-single` y tarjeta de red VirtIO. Respeta el tipo de arranque que tengas. |
| **Windows 11** | Arranque UEFI (OVMF) con tipo de máquina q35, **TPM** (obligatorio), agente de QEMU, controlador `virtio-scsi-single`, red VirtIO y el segundo CD de drivers. |
| **Windows Server 2022 / 2025** | Igual que Windows 11, pero el TPM no es obligatorio. |
| **Windows 10** y **Windows Server 2016 / 2019** | Arranque UEFI, agente de QEMU, controlador, red VirtIO y CD de drivers; sin TPM. |
| **Otro sistema** | No cambia nada más. |

Avisos que no bloquean (aparecen en el formulario):

- **Mínimos de Windows.** ProxLaunch avisa si el hardware queda por debajo de lo que pide
  Microsoft: Windows 11, 2 núcleos, 4 GiB de memoria y 64 GiB de disco; los demás Windows, 1 núcleo,
  2 GiB y 32 GiB.
- **Red Hat 10.** «Si vas a instalar RHEL 10 (o Rocky, Alma, CentOS Stream 10), necesita un
  procesador x86-64-v3. Elige ese tipo de CPU o «host».» Si el nombre del ISO parece de esa familia,
  el aviso lo dice: «Este ISO parece de la familia RHEL 10 (Red Hat, Rocky, Alma), que necesita un
  procesador x86-64-v3. Con el tipo de CPU actual puede no arrancar: elige x86-64-v3 o «host».»
- **Windows 11** sin UEFI o sin TPM: «Windows 11 exige arranque UEFI (OVMF).» / «Windows 11 exige un
  TPM 2.0.»

En **modo avanzado**, con un Windows, aparece la casilla **Disco compatible (SATA): no hace falta
cargar un controlador al instalar**: pone el primer disco en SATA para que Windows lo vea sin
drivers (es más lento que SCSI).

> Los perfiles de fábrica **Windows 11 (escritorio)**, **Windows Server** y **Linux (Red Hat y
> otros)** dejan el hardware y el sistema operativo ya elegidos. Solo te queda elegir el ISO.

### Windows y los drivers virtio-win

Windows no trae los controladores de los discos y la red virtuales de Proxmox. Por eso, al elegir
un Windows, ProxLaunch añade un **segundo CD** llamado **virtio-win** para cargarlos durante la
instalación. En el grupo **Drivers de Windows (virtio-win)** hay tres caminos:

1. **Ya está en el servidor.** Si hay un ISO que empieza por `virtio-win`, ProxLaunch lo usa: «Se
   usará el CD de drivers «virtio-win-0.1.302.iso», que ya está en el servidor.» (el nombre será el
   del archivo que tengas). Con **Elegir otro ISO de drivers…** puedes elegir otro.
2. **Descargarlo en el servidor.** Si no hay ninguno, el texto dice «No hay ningún ISO de virtio-win
   en el servidor. Elige cómo conseguirlo.» El botón **Descargarlo en el servidor** hace que Proxmox
   lo descargue de una dirección fija, y comprueba su huella SHA-256. En el laboratorio tardó unos 76
   segundos.
3. **Ya lo tengo en mi equipo.** Si lo descargaste antes, **Ya lo tengo en mi equipo** lo sube.

Si no quieres los drivers, marca **Crear sin los drivers**: «La máquina se creará sin el CD de
drivers.» y se muestra el aviso «Sin los drivers, Windows no verá el disco VirtIO ni la red.»

ProxLaunch conoce la versión **0.1.302** de virtio-win. Si eliges otro ISO de drivers, puedes
crear la máquina igualmente, pero antes verás el aviso: «Se usará el CD de drivers «…», que no es
la versión que conoce ProxLaunch. Comprueba que es de confianza antes de crear la máquina.»

### Subir un ISO desde tu equipo

En **Elegir un archivo ISO**, pulsa **Subir desde mi equipo…**. Se abre **Subir un ISO desde mi
equipo**:

1. Pulsa **Elegir archivo…** y elige un archivo `.iso` (o `.img`). ProxLaunch lo revisa (que de
   verdad parezca un ISO) y muestra su nombre y tamaño.
2. En **Nombre en el servidor** puedes cambiar cómo se llamará allí. ProxLaunch propone un nombre
   válido y **nunca sobrescribe**: si ya existe uno igual, lo dice («Ya existe un archivo llamado
   «x» en «y». ProxLaunch no lo sobrescribe: usa el que ya está o elige otro nombre.») y ofrece
   **Usar el existente** o **Cambiar el nombre**.
3. ProxLaunch comprueba el destino: que quepa en el almacenamiento y que tengas permiso. Si el nodo
   tiene poco espacio temporal, avisa («El nodo «pve1» tiene poco espacio temporal (… libres) para
   recibir un archivo de …. La subida podría fallar.») y tienes que marcar **Entiendo que la subida
   puede fallar** para seguir. Lee el aviso: «Esta subida no se puede deshacer desde ProxLaunch
   (requeriría un permiso de administrador). Si te equivocas, pídele al administrador que borre el
   archivo.»
4. Pulsa **Subir**. Verás las etapas **Calculando la huella del archivo**, **Enviando**,
   **Esperando al servidor** y **Verificando**, con la velocidad y el tiempo restante cuando se
   conocen (nunca inventa porcentajes).
5. Al terminar: «Listo. El archivo «…» está en el servidor.» y queda elegido.

**Verificación SHA-256.** Antes de enviar, ProxLaunch calcula la huella SHA-256 del archivo y la
manda con él: el servidor comprueba que lo recibido coincide con ella. Al final, ProxLaunch
verifica además que el archivo del servidor es el que enviaste. Si algo no coincide, verás «El
archivo llegó dañado: la huella no coincide. No quedó guardado.» o «El servidor dice que terminó,
pero el archivo no coincide con el que enviaste. No lo uses.»

**Cancelar.** Mientras se envía, el botón dice **Cancelar subida**. Si cancelas, el resultado es «Se
canceló. No se guardó ningún archivo.», o, si quedó algo a medias, «Se canceló, pero el archivo
parcial quedó guardado: pídele al administrador que lo borre.» La cancelación **no siempre es
inmediata**: puede tardar unos segundos mientras se conecta y mucho más si el servidor está
terminando de copiar el archivo (hasta unos 2 minutos); cerrar ProxLaunch en ese momento también
puede tardar unos 6 segundos.

**Una transferencia a la vez.** Si ya hay una en curso: «Hay una transferencia en curso. Espera a
que termine o cancélala.»

### Dejar de esperar

Cuando ProxLaunch ya envió todo el archivo y el servidor lo está copiando, el botón cambia de
**Cancelar subida** a **Dejar de esperar**. Pulsarlo no detiene nada en el servidor; solo hace que
ProxLaunch deje de esperar: «Dejaste de esperar. El archivo ya se envió y el servidor sigue
copiándolo: no se puede cancelar desde ProxLaunch y puede aparecer en el catálogo cuando termine.
Revísalo allí más tarde.»

Lo mismo ocurre con una descarga: «La descarga sigue en el servidor y no se puede cancelar desde
ProxLaunch. Cuando termine, abre el catálogo para ver el resultado.»

### Descargar un ISO en el servidor

En **Elegir un archivo ISO**, **Descargar en el servidor…** abre **Descargar un ISO en el
servidor**. Aquí el propio servidor de Proxmox descarga el archivo, sin pasar por tu equipo.

1. Escribe la **Dirección web** y pulsa **Comprobar**. El servidor dice qué ve («El servidor ve:
   «host/archivo»») con su nombre, tamaño y tipo.
2. (Recomendado) Escribe la **Huella** del archivo (el campo dice «Opcional: huella (sha256,
   sha512…)»). Si la escribes, Proxmox comprueba al terminar que lo descargado coincide y, si no,
   descarta el archivo. Se admiten md5, sha1, sha224, sha256, sha384 y sha512; si usas un algoritmo
   antiguo, ProxLaunch avisa que ya no protege de un archivo manipulado a propósito y sugiere
   SHA-256 o SHA-512.
3. Revisa el **Nombre en el servidor** y pulsa **Descargar**.

Cosas que conviene saber:

- Lo normal es una dirección `https://`. Si usas `http://`, ProxLaunch avisa («no se puede garantizar
  que el archivo no fue alterado por el camino») y te pide confirmar. También avisa si apunta a un
  equipo de la red interna del servidor o usa un puerto que no es el 80 ni el 443.
- En **modo avanzado** aparece la casilla **Comprobar el certificado del servidor web
  (recomendado)**; desmarcarla también pide confirmación.
- «La descarga la hace el servidor: una vez empezada, no se puede cancelar desde ProxLaunch. Solo
  puedes dejar de esperar.» Y «La dirección quedará en el registro de tareas del servidor.»
- Descargar desde una dirección web necesita Proxmox **8.2 o superior** y el permiso
  `Sys.AccessNetwork` en el nodo. En 8.0 y 8.1 exige permisos de administrador y ProxLaunch te lo
  explica: «Descargar desde una dirección web exige permisos de administrador en esta versión de
  Proxmox. Descarga el archivo en tu equipo y súbelo.»

### Archivos subidos en esta sesión

**Archivo > Archivos subidos en esta sesión…** muestra la lista de lo que subiste o descargaste
desde que abriste ProxLaunch (hora, tipo, archivo, almacenamiento, nodo, tamaño y estado). Puedes
usar **Copiar lista** o **Guardar como .txt…**. Esa lista solo existe mientras la aplicación está
abierta y no se guarda sola. Estos archivos **quedan en el servidor hasta que un administrador los
borre**: ProxLaunch no puede borrarlos, ni siquiera con un usuario administrador. Si ya no los
necesitas, pide que los borren desde Proxmox (en el almacenamiento, sección «ISO Images» o
«Import»).

### Usar un disco existente (importar)

Esta opción crea la máquina con un disco que ya tiene un sistema instalado (qcow2, vmdk o raw), en
lugar de empezar vacía.

**Qué necesita tu servidor:**

- Proxmox **8.4 o superior**. En 8.0 a 8.3 verás: «Tu Proxmox … no permite importar discos sin ser
  administrador del servidor. Puedes instalar desde un ISO o clonar una plantilla. Desde la versión
  8.4 sí se puede importar.»
- Un almacenamiento de tipo **directorio, NFS o CIFS** con el contenido **«Import»** activado. Lo
  activa un administrador (**Datacenter → Almacenamiento → Editar → Contenido**). Si no hay
  ninguno: «Para importar discos, pide a tu administrador que active el contenido «Import» en un
  almacenamiento de tipo directorio, NFS o CIFS.» (y, si puede, te dice en cuáles podría activarse).

**Paso a paso:**

1. Pulsa **Elegir disco…**. Se abre **Elegir un disco existente**: «Estos son los discos (qcow2,
   vmdk, raw) que hay en el servidor para importar.»
2. Si no está, **Subir desde mi equipo…** abre **Subir un disco desde mi equipo** (acepta `.qcow2`,
   `.vmdk`, `.raw` y `.img`) y funciona como la subida de un ISO, con las mismas comprobaciones de
   nombre, espacio y huella. **Descargar en el servidor…** abre **Descargar un disco en el
   servidor**.
3. Opcionalmente, **Ampliar el disco a** un tamaño mayor en GiB (por defecto, **Tamaño del disco
   importado**).
4. Elige el sistema operativo si quieres que el asistente ajuste la máquina, y crea.

**Qué discos no se pueden importar.** ProxLaunch revisa el archivo antes de subirlo y te dice por
qué no sirve: depende de otro archivo (un disco base), está cifrado, está formado por varios
archivos, es una **OVA** («Un archivo OVA no se puede importar tal cual. Extrae el disco que lleva
dentro y súbelo.»), tiene una versión no compatible o parece incompleto. Las OVA y la migración
desde VMware no están soportadas.

**En un lote**, cada máquina recibe su propia copia del disco, así que ocupa espacio propio. Con
muchas máquinas el espacio necesario se multiplica. Las importaciones se hacen de una en una por
nodo y, como mucho, dos a la vez hacia el mismo almacenamiento.

### El diálogo «¿Cuál usar siempre?» (almacenamientos)

En cada sitio los almacenamientos tienen nombres distintos. ProxLaunch **no se fija en el nombre**:
mira qué contenido admite cada uno (discos de máquinas, ISOs o discos para importar) y, si hay uno
solo, lo usa sin preguntar. Si hay **varios**, te pregunta **una vez por servidor** y lo recuerda.

El diálogo se llama **Elegir almacenamiento** y dice: «Hay varios almacenamientos para discos de
máquinas. ¿Cuál usar siempre en este servidor?» (en lugar de «discos de máquinas» puede decir
«imágenes ISO» o «imágenes de disco para importar»). Muestra una tabla con **Almacenamiento**,
**Tipo**, **Espacio libre**, **Compartido** y **Nota** (el de más espacio libre viene marcado «Más
espacio libre» y elegido de antemano). Pulsa **Usar este** para aceptar, o **Cancelar**. La casilla
**Recordar mi elección** viene marcada y guarda solo el nombre del almacenamiento, en el perfil de
conexión de este servidor.

**Cuándo sale:**

- Cuando eliges el origen **Instalar desde un archivo ISO** o **Usar un disco existente**, si hay
  varios almacenamientos para los discos de las máquinas y todavía no recordaste ninguno.
- Cuando subes o descargas un archivo y hay varios almacenamientos para ese contenido (ISOs o
  discos para importar).

**Cuándo NO sale:** al conectar, ni con el origen **Vacía, sin sistema operativo**. Con un disco
vacío todo funciona como antes: ProxLaunch propone el almacenamiento con más espacio libre.

**Si el que recordabas desaparece.** Si el almacenamiento recordado ya no existe, está inactivo o ya
no admite ese contenido, ProxLaunch no lo sustituye en silencio: «El almacenamiento «x» que usabas
en este servidor ya no está disponible o ya no admite imágenes ISO. Elige otro.» Entonces el
diálogo ofrece **Elegir otro** o **Dejar de recordar**. Puedes revisarlos cuando quieras en
**Ajustes > Almacenamientos recordados…**, y también en la ventana de conexión, en el grupo
**Almacenamientos recordados de este servidor** (**Discos de las máquinas**, **Archivos ISO** y
**Discos para importar**, con **Dejar de recordar**).

### Copiar una plantilla (clonar)

Una **plantilla de Proxmox** es una máquina ya instalada que se marcó como modelo. Al clonarla
obtienes máquinas nuevas con su mismo sistema, sin instalar nada. Los discos, la red y el tipo de
arranque los da la plantilla: lo que tengas en esas secciones del formulario se ignora.

1. Pulsa **Elegir plantilla…**. Se abre **Elegir una plantilla de Proxmox**: «Estas son las
   plantillas de Proxmox que tu cuenta puede ver. La nueva máquina será una copia de la que elijas.»
2. Las plantillas que no se pueden usar aparecen desactivadas con el motivo, por ejemplo «Falta el
   permiso VM.Clone» o «Bloqueada (…): espera a que termine lo que Proxmox está haciendo con ella».
   Si no ves ninguna: «No veo ninguna plantilla con tu cuenta. Pide el permiso VM.Audit o crea la
   plantilla en Proxmox (clic derecho en la máquina → Convertir en plantilla).»
3. Elige una y pulsa **Elegir**.

**Tipo de copia: enlazada o completa.**

- **Rápido y ligero** (clon *enlazado*): la copia comparte el disco con la plantilla, se crea en
  segundos y casi no ocupa espacio, pero depende de ella. **No borres la plantilla mientras existan
  sus copias.** (En el laboratorio, un almacenamiento de tipo `lvmthin` dejó borrar una plantilla con
  clones enlazados: ProxLaunch no promete ninguna protección, así que ten cuidado.)
- **Copia independiente** (clon *completo*): duplica todo el disco. Tarda más y ocupa más, pero la
  máquina no depende de nada.

En **modo básico** no eliges: se usa **Rápido y ligero (recomendado)** y, si el almacenamiento no lo
permite, Proxmox hace una copia independiente. Antes de crear, ProxLaunch te dice cuál será: «Se hará
una copia rápida y ligera. Las máquinas comparten el disco base con la plantilla: no borres la
plantilla mientras existan.» o «Se hará una copia independiente: tarda más y ocupa el espacio completo
del disco.» En **modo avanzado** aparece **Tipo de copia** (**Automático**, **Enlazado** o
**Completo**) y, con la copia completa, **Guardar la copia en** otro almacenamiento («El de la
plantilla» por defecto).

**Cuántas a la vez.** En un lote, ProxLaunch crea como máximo **3 clones enlazados a la vez por
nodo**, y ese tope se cuenta en el **nodo de la plantilla**, aunque las máquinas nuevas vayan a
otros nodos. Las copias completas se hacen de una en una por nodo y, como mucho, dos a la vez hacia el
mismo almacenamiento. (En el laboratorio, 3 clones enlazados en paralelo tardaron 1,1 s frente a
1,6–3,7 s uno tras otro.)

**Ajustes de la copia (opcional).** El grupo **Ajustes de la copia (opcional)** deja cambiar
**Núcleos**, **Memoria (MiB)** y **Disco principal (GiB)** (y, en modo avanzado, **Procesadores
(sockets)** y **Tipo de CPU**). Cada campo dice «Igual que la plantilla» con su valor si no lo
tocas. Si la memoria nueva queda por debajo de la memoria mínima (ballooning) de la plantilla,
ProxLaunch baja también ese mínimo para que Proxmox lo acepte. Si un ajuste falla después de
clonar: «La máquina «x» se clonó, pero no se pudo …. Puedes reintentar los ajustes o deshacer.»

**Deshacer** una copia borra la máquina nueva, **nunca la plantilla**.

### Orígenes en lotes, perfiles y CSV

- **Lotes.** En un lote normal, todas las máquinas usan el mismo origen (la misma ISO, el mismo
  disco o la misma plantilla). Ver [Crear varias máquinas de una vez (lotes)](#crear-varias-máquinas-de-una-vez-lotes).
- **Perfiles.** Los perfiles de fábrica **Windows 11 (escritorio)**, **Windows Server** y **Linux
  (Red Hat y otros)** traen el hardware y el sistema operativo para instalar desde un ISO
  (ver [Perfiles de fábrica](#perfiles-de-fábrica)).
- **Lotes guardados.** Un lote guardado recuerda el origen y el **nombre** del ISO, del disco o de
  la plantilla (nunca direcciones web, rutas de tu equipo ni huellas). Al abrirlo, ProxLaunch
  comprueba que ese archivo o plantilla exista en este servidor; si no, aparece **Este lote no
  encaja en este servidor** y eliges otro (ver [Si el lote «no encaja»](#si-el-lote-no-encaja-en-este-servidor)).
- **CSV.** Cada fila puede tener su propio origen con las columnas `origen`, `fuente`, `so`,
  `virtio` y `modo_clon`:

| Columna | Valores |
|---|---|
| `origen` | `vacio` (o `disco vacio`), `iso`, `importar` (o `imagen`, `importar disco`), `clonar` (o `plantilla`, `clonar plantilla`). |
| `fuente` | El **nombre** del ISO, del disco o de la plantilla (no una dirección web ni una ruta). |
| `so` | `linux`, `windows 11`, `windows server 2022/2025`, `windows 10`, `windows server 2016/2019` u `otro`. |
| `virtio` | `si` o `no`: con o sin el CD de drivers (solo Windows con `iso`). |
| `modo_clon` | `auto`, `enlazado` o `completo` (solo con `clonar`). |

En una fila con origen `importar`, la columna `disco` significa «ampliar el disco a» (GiB). En una
fila con origen `clonar`, `cpu`, `memoria` y `disco` son **ajustes** sobre la plantilla. Si una fila
nombra un archivo o plantilla que no existe en el servidor, la vista previa la marca con error. Pon `vacio` en `origen` si la fila no debe heredar el origen de su perfil.
Si escribes una dirección web en `fuente`, ProxLaunch te dice: «Aquí va el nombre de un archivo del
servidor, no una dirección web. Para descargar usa «Descargar en el servidor».»

### Permisos para el administrador: alcance acotado

Esta parte es para quien administra Proxmox. Para usar ISOs, importar discos y clonar plantillas,
el rol `ProxLaunchCreador` lleva los 14 privilegios de [Permisos que hacen falta](#permisos-que-hacen-falta).
Dónde se asignan importa mucho, porque `VM.Clone` permite copiar el contenido de una máquina.

**Recomendado: asignación acotada.** La guía de ProxLaunch (**Ayuda > ¿Cómo creo un API Token?**)
propone estas asignaciones, en **Datacenter → Permisos**:

| Ruta | Rol | Propagar | Para qué |
|---|---|---|---|
| `/pool/plantillas-proxlaunch` | `ProxLaunchCreador` | Sí | Que `VM.Clone` valga **solo** para las plantillas de ese pool. |
| `/vms` | `ProxLaunchMaquinas` | Sí | Crear máquinas (el segundo rol, sin `VM.Clone`). |
| `/storage/<almacenamiento>` | `ProxLaunchCreador` | — | Solo en los que se usarán para ISOs, imágenes importadas y discos (`Datastore.AllocateTemplate` y `Datastore.AllocateSpace`). |
| `/nodes/<nodo>` | `ProxLaunchCreador` | — | Solo en los nodos que descargarán archivos desde una dirección web (`Sys.AccessNetwork`). |
| `/sdn/zones/localnetwork` | `ProxLaunchCreador` | — | Usar la red (`SDN.Use`). |
| `/` | `ProxLaunchCreador` | **No** | Solo para ver el estado de los nodos (`Sys.Audit`). |

En las filas con «—», la guía de ProxLaunch no indica nada especial sobre **Propagar**.

Pasos:

1. En **Datacenter → Permisos → Pools** crea el pool `plantillas-proxlaunch` y añade **solo las
   plantillas que ProxLaunch podrá clonar**.
2. Crea el rol `ProxLaunchCreador` con los 14 privilegios y asígnalo en la ruta
   `/pool/plantillas-proxlaunch` con **Propagar**.
3. Crea un segundo rol, `ProxLaunchMaquinas`, con los privilegios de máquina del rol anterior **sin
   `VM.Clone`**, y asígnalo en `/vms` con **Propagar**:

   ```text
   VM.Allocate
   VM.Audit
   VM.Config.Options
   VM.Config.HWType
   VM.Config.CPU
   VM.Config.Memory
   VM.Config.Network
   VM.Config.Disk
   ```

4. Asigna `ProxLaunchCreador` en `/storage/<almacenamiento>`, `/nodes/<nodo>` y
   `/sdn/zones/localnetwork`, y en `/` **sin** marcar **Propagar**.

Con esto, `VM.Clone` solo vale dentro del pool. Se verificó en el laboratorio: con el pool se
clona y, fuera del pool, Proxmox responde 403.

**Alternativa simple.** Asignar el rol `ProxLaunchCreador` una sola vez en la ruta `/` con
**Propagar**. Es más cómodo, pero el permiso alcanza a todo el servidor: quien consiga el token
podría **clonar cualquier máquina y leer sus discos**, subir archivos a cualquier almacenamiento y
hacer que los nodos descarguen direcciones web. Úsala solo en un laboratorio o si confías
plenamente en quien guarde el token.

**Lo que la asignación acotada no limita.** `VM.Audit` **no queda limitado al pool**: el token ve
todas las máquinas y plantillas del servidor. Por eso las demás plantillas **pueden verse en la
lista** (aparecen desactivadas con «Falta el permiso VM.Clone»), pero ProxLaunch **no las clonará**:
la planificación lo bloquea con «Falta el permiso VM.Clone en «/vms/…» para clonar la plantilla.»
(regla V-O17).

**Limpieza periódica (importante).** Algunos rechazos de una subida dejan archivos
`/var/tmp/pveupload-*` en el nodo. El rol **no puede borrarlos**, a propósito: no tiene
`Datastore.Allocate`. Si se repiten subidas fallidas, esos archivos pueden **llenar el sistema de
archivos raíz** del nodo. ProxLaunch avisa cuando queda poco espacio en la raíz antes de subir
(«…tiene poco espacio temporal…»), pero **el administrador debe borrar esos archivos de vez en
cuando**, por ejemplo revisando `/var/tmp` en cada nodo.

Para el resto, **Copiar texto para el administrador** (en **Qué puedo hacer en este servidor**)
genera un mensaje listo para enviar con los privilegios, las asignaciones y los pasos de «Import» y
plantillas.

---

## Entender el progreso y los resultados

Al pulsar **Crear máquina**, los campos se bloquean y el panel **Progreso** muestra las
etapas, sin porcentajes inventados:

1. Validando datos
2. Enviando a Proxmox
3. Creando la máquina
4. Comprobando el resultado
5. Listo

Cuando Proxmox acepta la orden, aparece el **Identificador de la tarea (UPID)** con el
botón **Copiar UPID**. Es útil si tienes que hablar con tu administrador.

Debajo hay un botón **Ver detalles técnicos** (y **Ocultar detalles técnicos**): muestra
el texto original que dio Proxmox, el código del error y el registro de la tarea. Úsalo
para pedir ayuda; no hace falta para el día a día.

### Los resultados posibles

| Resultado | Qué verás | Qué significa y qué hacer |
|---|---|---|
| **OK** | «Máquina srv-web-01 (100) creada en pve1». Botón **Crear otra**. | La máquina existe (ProxLaunch lo comprueba al terminar). Pulsa **Crear otra** para otra: conserva la configuración, vacía el nombre y busca un número libre. |
| **Con avisos** | «Creada con avisos» y el registro de la tarea desplegado. Botón **Crear otra**. | La máquina se creó, pero Proxmox dejó algún aviso. Léelo en los detalles técnicos. |
| **Error** | Un mensaje en español (ver la [tabla de errores](#mensajes-de-error-frecuentes)) y el botón **Volver al formulario**. | No se creó. Corrige el problema y vuelve a intentarlo. Tus datos siguen en el formulario. |
| **Parcial** | «La máquina quedó parcialmente creada; elimínala desde Proxmox». | Falló, pero quedó algo creado. ProxLaunch no borra nada: elimina la máquina desde Proxmox. |
| **Tiempo agotado** | «La tarea sigue en marcha en Proxmox, no sabemos si terminó». Botones **Seguir esperando**, **Comprobar ahora** y **Volver al formulario**. | ProxLaunch esperó 10 minutos. No es un fallo. Pulsa **Comprobar ahora** para preguntar una vez, o **Seguir esperando** para esperar más. |
| **Conexión perdida** | «Se perdió la conexión mientras se creaba la máquina; la tarea puede haber terminado». Botones **Comprobar ahora** y **Volver al formulario**. | Se cortó la comunicación más de 60 segundos. Pulsa **Comprobar ahora**. Cortes breves se recuperan solos y no ves nada. |
| **Envío incierto** | «No sabemos si Proxmox recibió la orden de crear la máquina. Pulsa «Comprobar» antes de intentarlo de nuevo.» Botones **Comprobar** y **Volver al formulario**. | La conexión falló justo al enviar la orden. No sabemos si llegó. **No vuelvas a crear la máquina todavía.** Pulsa **Comprobar**. |
| **Cancelado** | «No se creó; puedes intentarlo de nuevo.» y **Volver al formulario**. | Es el resultado de **Comprobar** cuando la máquina no existe. Ya puedes crearla de nuevo con seguridad. |

### El botón «Comprobar»

Existe para evitar que crees la **misma máquina dos veces** cuando no sabes si la primera
orden llegó.

- Sin identificador de tarea (envío incierto), **Comprobar** pregunta a Proxmox si la
  máquina ya existe y **no envía nada nuevo**. Tres respuestas posibles:
  - «La máquina sí se creó. Verifica en Proxmox que quedó como esperabas.»
  - «No se creó; puedes intentarlo de nuevo.»
  - «No se pudo comprobar si la máquina existe. Revisa la conexión e inténtalo de nuevo
    antes de volver a crearla.»
- Con identificador (tiempo agotado o conexión perdida), el botón se llama **Comprobar
  ahora** y consulta el estado de esa tarea.

Si pulsas **Volver al formulario** sin saber si la máquina se creó, ProxLaunch avisa:
«Todavía no sabemos si se creó… Si vuelves al formulario y la creas otra vez, podrías
duplicarla. ¿Volver de todos modos?»

### Si cierras ProxLaunch mientras se crea

Te pregunta: «Se está creando una máquina. Si cierras ProxLaunch, la tarea sigue
ejecutándose en el servidor Proxmox, pero ya no verás su resultado. ¿Cerrar de todos
modos?» La tarea **no se detiene**. Al volver, revisa en Proxmox si la máquina existe.

---

## Crear varias máquinas de una vez (lotes)

Un **lote** crea de 1 a 100 máquinas iguales con un solo clic. Todas comparten la
configuración del formulario (procesadores, memoria, discos, red...) y solo cambian el
**nombre**, el **número** y, si tienes un clúster, el **nodo**. Como en el resto de
ProxLaunch, las máquinas se crean **detenidas**, y con el disco **vacío** salvo que elijas otro
[origen del sistema operativo](#elegir-el-origen-del-sistema-operativo) (en un lote normal, todas las
máquinas usan el mismo origen; en un lote por filas, cada fila puede tener el suyo).

Si lo que necesitas son máquinas **distintas entre sí**, mira [Importar máquinas desde un CSV](#importar-máquinas-desde-un-csv)
y [Lote por filas](#lote-por-filas). Para repetir un lote otro día, mira
[Guardar y abrir lotes](#guardar-y-abrir-lotes).

Un lote es de verdad más delicado que crear una sola máquina, así que ProxLaunch te enseña
un resumen antes de enviar nada, te deja **simular** primero y te permite **deshacer** lo que
crea. Si algo no sale bien en una máquina, las demás siguen.

> **En el laboratorio** (Proxmox VE 9.2, un solo nodo) un lote de 30 máquinas se creó en
> unos 47 segundos y se deshizo en otros 47 (algo más de un segundo y medio por máquina).
> Tu servidor puede ir más rápido o más lento.

### Paso a paso, en resumen

1. En el bloque **Lote**, escribe la **Cantidad de máquinas** (2 o más) y el **Prefijo**.
2. Rellena el resto del formulario como siempre: es la configuración de **todas** las
   máquinas.
3. Pulsa **Ver resumen** y revisa la lista.
4. (Opcional, recomendado la primera vez) Pulsa **Simular**.
5. Pulsa **Crear N máquinas** y sigue el progreso.
6. Al terminar, mira el estado de cada una. Si hace falta, usa **Comprobar**, **Reintentar
   pendientes**, **Deshacer…** o **Informe**.

### Cantidad y nombres

El bloque **Lote** está encima del formulario. Con **Cantidad de máquinas** en `1` (el valor
inicial) no ves nada más: el formulario funciona como siempre, con su botón **Crear máquina**.
En cuanto escribes **2 o más**, el bloque muestra el resto de los campos, el formulario deja
de pedir el nombre, el número y el nodo de una máquina (los fija el lote) y el botón
**Crear máquina** pasa a llamarse **Ver resumen**.

- **Cantidad de máquinas:** de 1 a 100. Si pasas de 100 verás: «El máximo por lote es 100
  máquinas. Divide el trabajo en varios lotes.» ProxLaunch nunca recorta la cantidad por su
  cuenta.
- **Prefijo:** el principio del nombre de todas las máquinas. Con `srv-web` se crean
  `srv-web-01`, `srv-web-02`, `srv-web-03`... Solo letras sin acentos, números y guiones. Es
  obligatorio: si lo dejas vacío, verás «Escribe un prefijo para los nombres.»
- **Vista previa:** debajo del prefijo, ProxLaunch escribe cómo se llamarán las máquinas, por
  ejemplo «Se llamarán: srv-web-01, srv-web-02, srv-web-03 … srv-web-12». Muestra los tres
  primeros y el último (si son cuatro o menos, los muestra todos). Si algo no es válido, en
  lugar de la vista previa ves el motivo junto al campo, por ejemplo «El nombre «web_01» no
  es válido: tiene el carácter «_», que no se admite.»

**Relleno de ceros.** El número del nombre lleva ceros a la izquierda: con relleno 2 es `01`,
`02`... `10`. Si hacen falta más dígitos, **todos** los nombres usan los mismos para que se
ordenen bien: un lote de 120 con relleno 2 se llama `srv-web-001` ... `srv-web-120`, no
`srv-web-01` ... `srv-web-120`.

**Modo avanzado** (**Ajustes > Modo > Avanzado**): añade estos campos al bloque.

| Campo | Para qué sirve |
|---|---|
| **Separador** | Lo que va entre el prefijo y el número: **Guion (-)** (`srv-01`) o **Ninguno** (`srv01`). |
| **Número inicial** | Con qué número empieza la numeración de los nombres (por defecto 1). Con 5, las máquinas se llaman `srv-05`, `srv-06`... |
| **Relleno (dígitos)** | Cuántos dígitos mínimos lleva el número (por defecto 2, de 0 a 8). |
| **Número de máquina inicial (VMID)** | Ver [Números de máquina](#números-de-máquina-vmid). |
| **Nodos elegidos** y **Reparto** | Ver [Dónde se crean](#dónde-se-crean). |
| **Etiquetar las máquinas** | Ver [Etiquetas](#etiquetas-qué-son-y-para-qué-sirven). |

### Números de máquina (VMID)

Cada máquina necesita un **número** propio en todo el servidor (VMID). En el lote:

- **Automático:** si dejas **Número de máquina inicial (VMID)** vacío (dice «automático»),
  ProxLaunch toma el siguiente número libre del servidor y asigna los siguientes en orden.
- **Saltos:** si alguno de esos números ya lo usa otra máquina (aunque tú no puedas verla),
  ProxLaunch **lo salta** y te lo dice en el resumen: «Se saltaron los números 101 (ya los
  usa otra máquina).» Los números se agrupan en rangos (`101–103, 110`).
- **Manual** (solo modo avanzado): escribe un número inicial entre 100 y 999999999. Si ya
  está ocupado, el lote empieza en el siguiente libre. Si no encuentra suficientes números
  libres, avisa: «No encontré N números de máquina libres a partir del X. Prueba con otro
  número inicial o con menos máquinas.»
- **Si alguien se te adelanta:** otra persona puede usar uno de tus números entre el resumen
  y el envío. Esa máquina **no se crea** («El número N lo usó otra persona mientras tanto.
  Esta máquina no se creó.») y el lote sigue con las demás. Luego puedes usar
  [Reintentar pendientes](#reintentar-pendientes).

### Dónde se crean

En un **servidor individual** no hay nada que elegir: todas van al único nodo.

En un **clúster**, el campo **Dónde crearlas** ofrece:

| Opción | Qué hace |
|---|---|
| **Automático** | ProxLaunch reparte las máquinas entre los nodos que pueden alojarlas (que estén encendidos y tengan el almacenamiento y la red que pides). Es lo normal. |
| **Un nodo** | Todas van al nodo que elijas en la lista. Si no caben ahí, ProxLaunch avisa; no las manda a otro por su cuenta. |
| **Nodos elegidos** (modo avanzado) | Marcas los nodos entre los que se reparte. |

Los nodos apagados aparecen como «Sin conexión» y no se pueden elegir.

En modo avanzado, con **Automático** o **Nodos elegidos**, aparece **Reparto**:

- **Equilibrado** (el normal): cada máquina va al nodo que en ese momento tiene más memoria
  libre, contando las que ya le tocaron, para que ninguno se llene antes que los demás.
- **Por turnos:** una a cada nodo, en orden alfabético, y vuelta a empezar. Es predecible,
  pero no mira cuánta memoria le queda a cada nodo.

El resumen te dice cuántas máquinas recibe cada nodo y por qué («Equilibrado: más memoria
libre», «lo elegiste tú», «es el único nodo disponible»...). En ProxLaunch el reparto entre
varios nodos solo se ha probado con respuestas simuladas.

### Etiquetas: qué son y para qué sirven

Una **etiqueta** es una marca de texto que Proxmox muestra junto a la máquina. Por defecto,
ProxLaunch pone dos a cada máquina que crea:

- `proxlaunch`: indica que la creó ProxLaunch. Es la misma en todos tus lotes.
- `lote-` seguido de un código (por ejemplo `lote-3fa9c21b`): identifica **este** lote. El
  mismo código aparece en el informe.

Sirven para tres cosas:

1. **Encontrar** en Proxmox lo que creó un lote (filtrando por etiqueta o por número).
2. **Demostrar que una máquina es del lote** cuando hubo un corte de conexión y no se sabe si
   se creó (ver [«No sabemos si se creó»](#estados-de-cada-máquina)).
3. **Deshacer con seguridad:** ProxLaunch comprueba la etiqueta antes de borrar, para no
   tocar nunca una máquina que no sea suya.

Proxmox guarda las etiquetas en minúsculas, ordenadas y separadas por `;`. No tienes que
hacer nada: el nombre de la etiqueta lo pone ProxLaunch.

**Cómo desactivarlas.** En **modo avanzado**, la casilla **Etiquetar las máquinas** (dentro
del bloque **Lote**, que solo se ve con cantidad 2 o más) viene marcada. Si la desmarcas, las
máquinas se crean sin etiquetas. El valor se conserva si bajas la cantidad a 1.

**Qué se pierde sin etiquetas:**

- ProxLaunch ya no puede demostrar de quién es una máquina que apareció tras un corte. En
  ese caso la deja como «Existe, sin confirmar de quién es» y no la ofrece para deshacer.
- «Deshacer…» solo borra las máquinas que ProxLaunch confirmó que creó él mismo, con el
  nombre y el número del lote.
- Te costará más encontrar el lote en Proxmox (tendrás que buscar por nombre o por número).

**Cuándo conviene desactivarlas.** Si tu administrador restringió en Proxmox quién puede
crear etiquetas nuevas, Proxmox acepta la orden pero la tarea falla con un error de permiso
(«Sys.Modify for modifying tag»). ProxLaunch lo detecta: **pausa el lote** y te ofrece
**Seguir sin etiquetas** (ver [Pausas](#pausas-el-lote-se-detiene-y-te-pregunta)). Esta
restricción es poco habitual: por defecto Proxmox permite cualquier etiqueta.

### El resumen y la confirmación

Al pulsar **Ver resumen**, ProxLaunch consulta el servidor (no crea nada) y muestra:

- El título «Vas a crear N máquinas».
- Una tabla con una fila por máquina: **N.º**, **Nombre**, **VMID**, **Nodo**,
  **Almacenamiento** y **Discos (GiB)**.
- Los totales («Totales: 12 máquinas, 24 procesadores virtuales, 24 GiB de memoria»), el
  espacio que pide cada almacenamiento («Espacio en «local-lvm» en pve1: 96 GiB de 150 GiB
  libres»), el **Reparto** por nodo y los números saltados.
- Los **errores** (con ✕) y los **avisos** (con ⚠), siempre **antes** de los botones.

Los **errores** impiden crear. Mientras haya alguno, **Crear N máquinas** está desactivado y
debajo ves «Corrige los errores marcados para poder crear las máquinas.» El error más
habitual es que no quepan los discos: «Las 5 máquinas necesitan 160 GiB en «local» y solo hay
150 GiB libres. Caben 4.» En ese caso aparece el botón **Reducir a 4**, que baja la cantidad
y vuelve a generar el resumen. ProxLaunch nunca crea un lote a medias por su cuenta.

Los **avisos** no bloquean. Los más frecuentes:

- **Nombre repetido:** «Ya existe una máquina llamada «srv-web-01» (número 105).» Proxmox
  permite dos máquinas con el mismo nombre, pero luego cuesta distinguirlas. Junto al aviso
  ves: «Puede haber otras máquinas con esos nombres que tú no puedes ver.» Además, una
  máquina creada hace pocos segundos puede tardar unos 4 segundos en aparecer con su nombre,
  y en ese intervalo el aviso no salta.
- **Memoria:** «En «pve2» pides 96 GiB de memoria y hay 64 GiB libres. Las máquinas se crean
  apagadas; el problema aparecerá al encenderlas.»
- **Memoria de un nodo desconocida:** «No se pudo leer la memoria libre de «pve2»; el reparto
  usa el espacio.» (falta el permiso `Sys.Audit`).
- **Permisos sin verificar:** «Permisos no verificados: no se pudieron leer los permisos del
  usuario, así que Proxmox pudo rechazar alguna máquina.»
- **Espacio sobreasignado.** Algunos almacenamientos «solo ocupan el espacio a medida que se
  usa». Con ellos puedes pedir más discos de los que caben: «Estás pidiendo 300 GiB y solo
  hay 150 GiB libres en «local-lvm». Funciona mientras las máquinas no usen todo su disco; si
  se llena, todas las máquinas de ese almacenamiento pueden fallar.» Para continuar debes
  marcar la casilla **Entiendo el riesgo de sobreasignar espacio** (no se recuerda: se pide
  cada vez). Si pides **más de 3 veces** lo que hay libre, ya es un error.

El resumen se puede copiar con **Copiar resumen**. Con **Volver al formulario** vuelves a
editar; cualquier cambio en el formulario invalida el resumen y hay que generarlo otra vez.

**Confirmar.** Pulsa **Crear N máquinas**. Si el lote tiene **más de 10 máquinas**, ProxLaunch
te pregunta una vez más (**Confirmar el envío**): «Se enviarán N máquinas a Proxmox.
¿Continuar?», con **Crear las máquinas** o **Cancelar**.

Si desde que generaste el resumen pasaron **más de 5 minutos**, ProxLaunch vuelve a leer el
servidor antes de enviar. Si algo cambió (un número ya no está libre, un nodo cayó, hay menos
espacio) no envía nada: te enseña el resumen nuevo con «Los datos del servidor cambiaron: ...
Revisa el resumen y confirma otra vez.»

### Simulación

**Simular** hace **todo lo que haría el lote de verdad, menos crear**:

- Vuelve a leer el servidor (nodos, almacenamientos, redes y números ocupados).
- Planifica el lote y comprueba todo (espacio, nombres, nodos, memoria, permisos...).
- Muestra el mismo resumen, marcado como «SIMULACIÓN — no se creó nada», y en detalles
  técnicos la orden exacta (`POST /nodes/<nodo>/qemu` con sus parámetros) que se enviaría
  por cada máquina. No lleva claves ni cabeceras.
- **Informe de la simulación…** lo exporta como informe (ver [Informe](#informe)).

**Qué garantiza:** durante la simulación ProxLaunch solo **lee** del servidor. Se verificó en
el laboratorio: en el registro de acceso de Proxmox solo quedan consultas de lectura (`GET`).
Puedes simularlas todas las veces que quieras, también con un usuario sin permiso para crear.

**Qué no puede garantizar.** Simular no prueba que Proxmox vaya a aceptar cada máquina. Por
ejemplo, no detecta que otra persona use un número entre la simulación y el envío, que el
espacio cambie, que falten permisos sobre un número concreto o que Proxmox rechace las
etiquetas (ese fallo solo aparece al crear). Por eso, al pulsar **Crear de verdad estas N
máquinas**, ProxLaunch vuelve a planificar y a validar todo antes de enviar.

**Simulación con otra versión de Proxmox.** En modo avanzado puedes forzar una versión de
compatibilidad. La simulación valida contra esa versión y lo indica: «Simulado con
compatibilidad de Proxmox 9.2 (el servidor es 9.0)». Si forzaste una versión **más nueva**
que la del servidor, no podrás crear de verdad: «Has forzado una versión más nueva que la del
servidor (9.0); solo puedes simular.»

**Cantidad 1.** Con una sola máquina no hay resumen ni simulación: el botón **Crear máquina**
funciona como en la sección [Crear una máquina en modo básico](#crear-una-máquina-en-modo-básico).
La máquina sí lleva etiquetas y puedes deshacerla.

### Mientras se crea: el progreso

Al confirmar, el formulario se bloquea y aparece el progreso del lote, con el título
«Creando N máquinas»:

- Una **barra** con el texto «7 de 20 terminadas · 1 con error · 2 en curso». Solo cuenta
  máquinas terminadas: no inventa porcentajes ni tiempos estimados. Si hay máquinas sin
  confirmar o sin enviar, el texto añade «N sin confirmar» y «N sin enviar».
- Una **tabla** con una fila por máquina: **Estado**, **Nombre**, **VMID**, **Nodo** y
  **Detalle**. El estado lleva siempre un símbolo y un texto, para que no dependa solo del
  color.
- **Mostrar solo problemas** filtra la tabla.
- Al seleccionar una fila aparece su **Identificador de la tarea (UPID)** con **Copiar UPID**
  y sus detalles técnicos (texto original de Proxmox y registro de la tarea).

ProxLaunch crea **una máquina a la vez por nodo** y hasta **4 nodos en paralelo**, para no
cargar el servidor. No cierres la ventana mientras tanto (ver
[Cerrar ProxLaunch con un lote en curso](#cerrar-proxlaunch-con-un-lote-en-curso)).

### Estados de cada máquina

| Símbolo y estado | Qué significa | Qué hacer |
|---|---|---|
| ○ **Pendiente** | Está en la cola. Todavía no se envió. | Esperar. |
| ● **Validando datos**, **Enviando a Proxmox**, **Creando la máquina**, **Comprobando el resultado** | Las etapas de una máquina, igual que al crear una sola. | Esperar. |
| ✓ **Lista** | Se creó y ProxLaunch lo comprobó. | Nada. Si el detalle dice «Se creó aunque Proxmox tardó en responder.», hubo un corte, pero la máquina existe. |
| ⚠ **Lista, con avisos** | Se creó, pero Proxmox dejó algún aviso. «Se creó, pero hay avisos.» | Lee los detalles técnicos. |
| ✕ **Con error** | No se creó (el detalle dice por qué, con el mismo lenguaje de la [tabla de errores](#mensajes-de-error-frecuentes)). | Corrige la causa y usa **Reintentar pendientes**. |
| ◐ **Quedó a medias** | Falló, pero quedó algo creado. «Quedó a medias; elimínala con «Deshacer…» o desde Proxmox.» | Usa **Deshacer…** o bórrala en Proxmox. |
| ? **Sin confirmar (sigue en Proxmox)** | ProxLaunch esperó 10 minutos y la tarea sigue en marcha. No es un fallo. | Pulsa **Comprobar ahora** más tarde. |
| ? **No sabemos si se creó** | Se cortó la conexión justo al enviar o mientras se esperaba, y no se sabe si Proxmox la creó. «No sabemos si «srv-01» se creó. No se volverá a enviar: pulsa «Comprobar» para verlo.» | **No la crees otra vez.** Pulsa **Comprobar ahora** (ver más abajo). |
| – **No enviada** | Nunca salió hacia Proxmox, así que **no existe**. El detalle dice el motivo: «cancelaste el lote», «el lote se detuvo», «hubo un error que afectaba a todo el lote» o «el nodo no respondió». | Puedes usar **Reintentar pendientes**. |
| – **No se creó** | Hubo un corte, pero ProxLaunch comprobó tres veces que no existe. «Se comprobó y no existe en Proxmox. Puedes reintentarla.» | Puedes usar **Reintentar pendientes**. |
| ? **Existe, sin confirmar de quién es** | La máquina existe, pero no hay prueba de que la creara este lote (no tiene su etiqueta). Podría ser de otra persona con el mismo número. | Verifícala en Proxmox. ProxLaunch no la borrará ni la ofrece en «Deshacer…». |

**«No sabemos si se creó» y «Comprobar ahora».** ProxLaunch **nunca vuelve a enviar** una
máquina que pudo haberse creado: podría duplicarla. Antes de rendirse, ya comprueba por su
cuenta hasta tres veces (al instante, a los 5 y a los 15 segundos). Si sigue sin saberlo, la
deja así. Cuando el lote termina:

- Selecciona la fila dudosa y pulsa **Comprobar ahora**, o
- pulsa **Comprobar la dudosa** / **Comprobar las N dudosas** para revisarlas todas.

La comprobación **solo lee**: pregunta a Proxmox y nunca envía nada nuevo. Según el resultado,
la máquina pasa a «Lista» o a «No se creó».

### Pausas: el lote se detiene y te pregunta

A veces seguir enviando sería inútil o peligroso. ProxLaunch **pausa el lote** (no envía
ninguna máquina más) y abre un diálogo. Si lo cierras sin decidir, el lote sigue pausado y el
botón **Decidir qué hacer…** vuelve a abrirlo. Hay tres tipos:

| Título | Cuándo | Botones |
|---|---|---|
| **El lote se detuvo por un problema general** | Un error que afectaría a todas las máquinas: la sesión caducó, las credenciales dejaron de valer, cambió la huella del servidor, falta el permiso `VM.Allocate` o Proxmox no aceptó la etiqueta. Se detiene al **primer** caso. | **Reconectar…** (errores de sesión), **Seguir sin etiquetas** (etiqueta rechazada), **Reintentar**, **Cancelar lote**. |
| **El lote se detuvo: el mismo error se repite** | Fallaron **3 máquinas seguidas por la misma causa**. «Fallaron 3 máquinas seguidas por la misma causa: ... ¿Continuar o detener?» | **Continuar** (y no vuelve a preguntar por esa causa en este lote), **Detener el lote**. |
| **El lote se detuvo: se perdió la conexión** | La conexión estuvo cortada más de 60 segundos. «Se perdió la conexión. Hay N máquinas sin confirmar.» | **Comprobar y continuar**, **Cancelar lote**. |

El botón seguro (**Cancelar lote** o **Detener el lote**) es el que tiene el foco al abrirse.

- **Comprobar y continuar:** mira qué pasó con las máquinas sin confirmar y después envía
  **solo las que faltaban**. Nunca vuelve a enviar una máquina que ya salió.
- **Reconectar…:** abre la ventana de conexión. Si vuelves a entrar al **mismo perfil**, el
  lote continúa con las máquinas que faltan. Si eliges otro servidor, el lote anterior queda
  cerrado: ya no se puede continuar ni deshacer contra el servidor nuevo.
- **Seguir sin etiquetas:** te pide confirmar («Se detendrá este lote y se armará uno nuevo
  con las máquinas que faltan, sin etiquetas...»). Si aceptas con **Preparar el lote sin
  etiquetas**, se cancela este lote, se arma uno nuevo con lo que faltaba y ves su resumen
  antes de crear nada. Recuerda lo que se pierde ([Etiquetas](#etiquetas-qué-son-y-para-qué-sirven)).
- **Si un solo nodo deja de responder**, no se pausa todo el lote: sus máquinas quedan «No
  enviada» («el nodo no respondió») y los demás nodos siguen.

### Cancelar y «Dejar de esperar»

**Cancelar lote** detiene los envíos:

1. Si ya salió alguna máquina, ProxLaunch pregunta (**Cancelar el lote**): «Las máquinas que
   ya se enviaron seguirán creándose en Proxmox y se esperará su resultado. Las demás no se
   enviarán.» Elige **Cancelar el lote** o **Seguir creando**.
2. Las máquinas pendientes pasan a «No enviada» («cancelaste el lote»).
3. ProxLaunch **sigue esperando** el resultado de las que ya estaban en marcha, para decirte
   con certeza qué pasó. **No detiene ninguna tarea en Proxmox.** Mientras espera, el botón
   pasa a llamarse **Dejar de esperar**.
4. Si no quieres esperar, pulsa **Dejar de esperar**: esas máquinas quedan como «No sabemos
   si se creó» y la tarea sigue en Proxmox. Más tarde puedes usar **Comprobar ahora**.

Al terminar, **Deshacer…** te permite borrar lo que ya se había creado.

### Al terminar el lote

Cuando todas las máquinas tienen un resultado, el título pasa a «Lote terminado (N
máquinas)» y aparecen los botones que tienen sentido:

| Botón | Cuándo aparece |
|---|---|
| **Comprobar la dudosa** / **Comprobar las N dudosas**, **Comprobar ahora** | Hay máquinas «No sabemos si se creó» o «Sin confirmar». |
| **Deshacer…** | Siempre; se activa si hay algo que ProxLaunch pueda borrar. |
| **Reintentar pendientes** | Hay máquinas «No enviada», «No se creó» o «Con error». |
| **Informe** | Siempre. |
| **Volver al formulario** | Siempre. Si hay máquinas sin confirmar te avisa: «No sabemos si algunas máquinas se crearon. Si vuelves y repites el lote, podrías duplicarlas. ¿Volver de todos modos?» |

En **Archivo > Ver el último lote** puedes volver a ver el último lote mientras no abras otro.

### Reintentar pendientes

**Reintentar pendientes** arma un **lote nuevo** con las máquinas que **no se crearon** («No
enviada», «No se creó» y «Con error»). Conserva sus nombres y sus números, y pasa por el
resumen y la confirmación como cualquier lote (también puedes **Simular**). Es un lote
distinto, con su propio código de etiqueta.

- **Con cambio de nodo:** en el resumen aparece **Nodo de destino para el reintento**.
  **Los mismos nodos de antes** conserva el reparto; elegir un nodo lleva todas las máquinas
  a ese. Es útil si un nodo cayó o no tenía sitio.
- **Nunca** incluye máquinas «Lista», «Lista, con avisos», «Quedó a medias», «No sabemos si
  se creó», «Sin confirmar» ni «Existe, sin confirmar de quién es»: podrían existir.
  Compruébalas primero.
- Antes de enviar se vuelve a comprobar que cada número siga libre. Si otra persona lo
  ocupó, ves el error en el resumen y debes resolverlo antes de crear.
- El **Deshacer…** del lote anterior sigue disponible mientras no cambies de servidor.

### Deshacer

**Deshacer…** elimina de Proxmox las máquinas que creó **este lote** en **esta sesión**.
Nunca ocurre solo y siempre pide confirmación.

1. Pulsa **Deshacer…**. Se abre **Deshacer lo creado por el lote**.
2. Elige el alcance: **Todo lo que creó el lote** o **Solo las incompletas** (las que
   quedaron «a medias», las «Lista, con avisos» y las que se rescataron tras un corte de
   conexión).
3. Revisa la lista de máquinas marcadas. Las que ProxLaunch no puede borrar aparecen
   desactivadas con el motivo, por ejemplo «No se envió: no existe en Proxmox.», «Falló y no
   se creó nada.» o «Existe, pero no podemos asegurar que la creó este lote.»
4. Lee la advertencia: «Se eliminarán estas N máquinas y sus discos de Proxmox. Esta acción
   no se puede deshacer.»
5. Pulsa **Eliminar N máquinas** (o **Cancelar**, que tiene el foco al abrirse).

Mientras borra ves el título «Deshaciendo el lote» y una tabla con el estado de cada
máquina: **Pendiente**, **Comprobando**, **Eliminando**, **Eliminada**, **Ya no existía**,
**No se pudo eliminar**, **No se tocó**, **No sabemos si se eliminó** y **No se procesó**. El
botón **Detener lo que falta** interrumpe el resto. Al terminar, ProxLaunch actualiza los
datos del servidor (números libres y espacio) y el informe incluye la sección «Deshacer».

**Qué borra:** la máquina y los discos que tiene asignados (incluido el de UEFI).

**Qué NO borra nunca:**

- **Máquinas ajenas.** Solo las del lote, con su nombre y su número, y con la etiqueta del lote
  si usaste etiquetas. Si no puede demostrar que son suyas, no las toca: «No eliminamos «x»
  porque no podemos asegurar que la creó este lote.»
- **Máquinas protegidas o bloqueadas.** ««x» está protegida o bloqueada. Quita la protección
  en Proxmox.»
- **Máquinas encendidas.** ««x» está encendida. Apágala en Proxmox y vuelve a intentarlo.»
- **Discos sueltos.** Solo se borran los discos que la máquina tiene asignados. Un disco
  suelto en el almacenamiento (por ejemplo, de una máquina antigua que tuvo el mismo número)
  **no se toca**, porque podría ser de otra persona. Si crees que quedó alguno, revísalo en
  Proxmox.
- **Lo que no está en el lote:** máquinas «No enviada», «No se creó», «Con error» sin máquina
  creada, ni las «Existe, sin confirmar de quién es».

Si una eliminación falla, sigue con las demás y el informe lista las que quedaron: «No se
pudo eliminar «x»: ... Elimínala desde Proxmox.» Si Proxmox no deja borrar por falta de
permiso, se detiene tras el primer caso y no toca el resto. Si se corta la conexión al
borrar: «No sabemos si se eliminó «x». Comprueba antes de reintentar.»

**Hasta cuándo se puede deshacer.** Solo mientras ProxLaunch siga abierto y conectado al
**mismo servidor**. Si lo cierras o cambias de perfil, ya no podrás deshacer desde aquí. El
informe te dice cómo encontrar las máquinas en Proxmox para borrarlas a mano.

### Informe

**Informe** abre una ventana con el resultado completo del lote, en texto plano:

- **Copiar informe** lo pone en el portapapeles.
- **Guardar informe…** lo guarda como archivo `.txt` (UTF-8) donde elijas. El nombre sugerido
  es `informe-lote-<código>.txt` (`simulacion-<código>.txt` para una simulación).

Copiar y guardar dan **exactamente el mismo texto**. Contiene: el código del lote, la fecha,
el nombre del perfil, la versión de Proxmox y si es servidor individual o clúster; un
**Resumen** (Pedidas, Creadas, Creadas con avisos, Con error, Sin confirmar, No enviadas); la
tabla de **Máquinas** (N.º, Nombre, VMID, Nodo, Resultado, Duración, UPID); el **Detalle de
las máquinas con problemas** (mensaje, código y detalles técnicos); la **Configuración de las
máquinas**; los avisos del plan; la sección **Deshacer**, si la hubo; y al final **Cómo
encontrar estas máquinas en Proxmox**, con las etiquetas y el rango de números.

**Qué no contiene,** para que puedas compartirlo con tu administrador: ni la dirección ni la
IP del servidor, ni tu nombre de usuario, ni claves, tokens, contraseñas o tickets. Del UPID
se oculta el campo del usuario, y si algún texto de Proxmox los menciona se sustituyen por
«…». El informe sí contiene los nombres de las máquinas y de los nodos y el nombre de tu
perfil. Revísalo antes de enviarlo fuera de tu organización.

Un informe de **simulación** lleva el título «ProxLaunch — Simulación del lote ...» y la
línea «SIMULACIÓN — no se creó nada.»

### Cerrar ProxLaunch con un lote en curso

Si cierras la ventana con un lote en marcha (o deshaciendo), ProxLaunch pregunta (**Hay un lote
en curso**): «Hay un lote en curso (X de N terminadas). Si cierras, las tareas ya enviadas
seguirán en Proxmox, pero ProxLaunch no enviará el resto ni podrá deshacer lo creado.» Las
opciones son **Seguir en ProxLaunch** y **Cerrar de todos modos**.

Si cierras de todos modos:

- No se envía ninguna máquina más y ProxLaunch deja de esperar a las que están en marcha.
  **Las tareas ya enviadas no se detienen:** siguen en Proxmox.
- Se guarda un **informe parcial** en la carpeta de datos de tu usuario, en `informes/`, con
  el nombre `parcial-<código>.txt`. Para ver la ruta exacta, ejecuta desde la carpeta del
  repositorio:

  ```bash
  .venv/bin/python -c "import platformdirs; print(platformdirs.user_data_dir('ProxLaunch'))"
  ```

  (En Windows, cambia `.venv/bin/python` por `.venv\Scripts\python`.)
- La próxima vez que abras ProxLaunch verás: «El último lote se cerró sin terminar. Informe:
  <ruta>». El lote **no se restaura** y ya no puedes deshacerlo desde ProxLaunch: revisa en
  Proxmox qué se creó (por la etiqueta `lote-<código>` o por el rango de números).

---

## Perfiles de máquina

Un **perfil de máquina** es una configuración de **hardware** ya preparada: procesadores,
memoria, tipo de arranque, discos y red. Al elegirlo, ProxLaunch rellena el formulario por ti.
Sirve para no volver a escribir lo mismo cada vez.

Lo que un perfil **sí** aplica: el tipo de arranque, los sockets y núcleos, el tipo de CPU, la
memoria, el ballooning, los discos (tamaño, conexión, formato y opciones) y las redes.

Lo que un perfil **nunca** toca: el **nombre** de la máquina, su **número (VMID)**, el **nodo** y
el bloque **Lote**. Un perfil tampoco elige el archivo ISO ni instala nada por sí solo: los tres
perfiles de fábrica para instalar un sistema (ver abajo) solo **sugieren** instalar desde un ISO y
tú eliges el archivo después.

El grupo **Perfil de máquina** está arriba del formulario, en modo básico y en avanzado. Con un
lote en marcha queda desactivado.

### Perfiles de fábrica

ProxLaunch trae nueve perfiles. **No se pueden modificar ni borrar**; si quieres una variante,
duplícala (ver [Administrar perfiles](#administrar-perfiles-modo-avanzado)). En la lista aparecen
como «Servidor pequeño — De fábrica».

| Perfil | Para qué | Núcleos | Memoria | Disco |
|---|---|---|---|---|
| **Servidor pequeño** (el que se aplica al abrir) | Para pruebas y servicios ligeros. | 2 | 2 GiB | 32 GiB |
| **Servidor mediano** | Para aplicaciones web. | 4 | 4 GiB | 64 GiB |
| **Base de datos** | Para bases de datos. | 4 | 8 GiB | 100 GiB |
| **Servidor grande** | Para cargas pesadas. | 8 | 16 GiB | 128 GiB |
| **Escritorio (hardware compatible)** | Para sistemas que aún no traen controladores virtio: disco SATA, tarjeta de red Intel E1000 y arranque UEFI. | 4 | 4 GiB | 80 GiB |
| **Mínimo** | Disco y red básicos, para probar. | 1 | 512 MiB | 8 GiB |
| **Windows 11 (escritorio)** | Para instalar Windows 11: arranque UEFI, TPM y agente de QEMU. El ISO se elige después. | 4 | 8 GiB | 64 GiB |
| **Windows Server** | Para instalar Windows Server 2022 o 2025: arranque UEFI, TPM y agente de QEMU. El ISO se elige después. | 4 | 8 GiB | 80 GiB |
| **Linux (Red Hat y otros)** | Para instalar Linux, en especial Red Hat, Rocky o Alma. El ISO se elige después. | 2 | 4 GiB | 40 GiB |

Todos usan un solo socket y una interfaz de red. Los seis primeros crean un disco vacío; los tres
últimos (**Windows 11 (escritorio)**, **Windows Server** y **Linux (Red Hat y otros)**) traen solo
el hardware y dejan marcado el origen «Instalar desde un archivo ISO» **sin archivo**: tú lo eliges
(ver [Elegir el origen del sistema operativo](#elegir-el-origen-del-sistema-operativo)).

### Usar un perfil

1. En **Perfil de máquina**, abre la lista y elige uno. Debajo verás un resumen («4 núcleos · 4 GiB ·
   1 disco de 64 GiB») y su descripción.
2. El formulario se rellena con el hardware del perfil. En la barra de estado aparece «Perfil
   «Servidor mediano» aplicado». Tu nombre, número y nodo siguen como estaban.
3. Sigue como siempre: **Crear máquina**, o **Ver resumen** si es un lote.

**«(modificado)» y «Personalizado».** Si cambias cualquier dato de hardware después de elegir un
perfil, la lista pasa a decir, por ejemplo, «Servidor mediano — De fábrica (modificado)». No
pasa nada: el perfil guardado no cambia. Si abres un lote guardado, o el perfil que usabas se
elimina o se cambia, la lista muestra «Personalizado» (el formulario tal como está, sin perfil).
«Personalizado» es solo un estado: no se puede elegir para aplicar nada.

**Si ya cambiaste cosas y eliges otro perfil,** ProxLaunch pregunta antes (**Cambiar de perfil**:
«Se reemplazarán los ajustes de hardware que cambiaste.»). **Reemplazar** aplica el perfil;
**Cancelar** deja todo como estaba.

**Almacenamiento y red del perfil (pistas).** Un perfil puede recordar en qué almacenamiento y
en qué red (bridge) estaba cada disco y cada interfaz. Esos nombres son **pistas**: si existen en
el nodo, se usan. Si no existen, ProxLaunch usa los predeterminados del nodo y te avisa en un
panel que puedes cerrar, por ejemplo: «El perfil pedía el almacenamiento «datos», que no existe
en «pve1». Se usó «local-lvm».» Si el nodo no tiene ninguno apto, el aviso termina en «Elige uno
antes de crear.» ProxLaunch nunca inventa un almacenamiento. Con la misma casilla de pistas, un
perfil que guardaste con origen ISO, disco existente o plantilla recuerda también ese origen y el
nombre del archivo o de la plantilla (como pista, igual que el almacenamiento). Si desmarcas la
casilla, el perfil se guarda con el origen «disco vacío».

**Compatibilidad del perfil.** Debajo del selector puede aparecer este panel: con ✕ lo que
impide crear la máquina con este servidor y esta versión de Proxmox, y con ⚠ lo que solo
conviene saber (por ejemplo, que el tipo de CPU «host» impide mover la máquina entre nodos con
procesadores distintos). Los avisos no impiden crear; los errores sí.

### Guardar tu propio perfil

1. Deja el formulario como quieres el hardware.
2. Pulsa **Guardar como perfil…** (en el grupo **Perfil de máquina**) o abre el menú **Perfiles >
   Guardar como perfil de máquina…**.
3. Escribe un **Nombre del perfil** (de 1 a 60 caracteres; no puede repetir el de otro perfil,
   sea de fábrica o tuyo). En modo avanzado puedes añadir una **Descripción (opcional)**.
4. La casilla **Recordar los nombres de almacenamiento y red (solo sirven en servidores que los
   tengan)** viene marcada. Desmárcala si quieres un perfil que no dependa de tu servidor.
5. Pulsa **Guardar perfil**. Verás «Perfil «X» guardado».

El diálogo te recuerda qué se guarda: «el hardware actual del formulario: procesador, memoria,
discos y redes. No se guarda el nombre de la máquina, su número ni el nodo.» Puedes tener hasta
100 perfiles propios. Si el formulario tiene errores, el diálogo los lista («Corrige esto en el
formulario antes de guardar el perfil») y no te deja guardar. **Guardar como perfil…** no está
disponible en un [lote por filas](#lote-por-filas).

**Guardar cambios en un perfil tuyo.** Si el perfil aplicado es **tuyo** y lo modificaste,
aparece el botón **Guardar cambios en el perfil «X»**. Te pide confirmar («Se reemplazará el
hardware guardado en el perfil «X».») con **Guardar cambios** o **Cancelar**. En un perfil de
fábrica ese botón no aparece: usa **Guardar como perfil…** para crear el tuyo.

### Administrar perfiles (modo avanzado)

En **Ajustes > Modo > Avanzado**, el menú **Perfiles > Administrar perfiles…** (y un botón en el
grupo **Perfil de máquina**) abre **Administrar perfiles de máquina**: una lista con **Nombre**,
**Tipo** («De fábrica» o «Propio») y **Resumen**. Los botones son:

| Botón | Qué hace |
|---|---|
| **Usar en el formulario** | Aplica el perfil elegido (igual que elegirlo en la lista). |
| **Guardar el formulario como perfil…** | Lo mismo que **Guardar como perfil…**. |
| **Duplicar…** | Hace una copia editable. Propone el nombre «Copia de X». Sirve para partir de un perfil de fábrica. |
| **Renombrar…** | Cambia el nombre (y la descripción) de un perfil tuyo. |
| **Eliminar…** | Pide confirmar («¿Eliminar el perfil «X»? Los lotes que ya guardaste no cambian.»). |
| **Importar…** / **Exportar…** | Ver más abajo. |

Con un perfil de fábrica, **Renombrar…** y **Eliminar…** están desactivados y la ventana explica:
«Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión.»

### Compartir perfiles: exportar e importar

**Exportar.** Elige uno o varios perfiles y pulsa **Exportar…**. Aparece **Exportar perfiles**
con la casilla **Incluir los nombres de almacenamiento y red**, **desmarcada** (esos nombres son de
tu servidor y casi nunca existen en el de otra persona). Pulsa **Elegir dónde guardar…**. El
archivo se llama, por ejemplo, `servidor-web.proxlaunch-perfiles.json` y nunca incluye
contraseñas, tokens, direcciones ni nombres de usuario.

**Importar.** Pulsa **Importar…** y elige un archivo de perfiles. Se abre **Importar perfiles de
máquina** con una lista de lo que trae el archivo. **Todavía no se guardó nada.** Marca los que
quieres (columna **Importar**) y mira la columna **Estado**:

- «✔ Nuevo»: se importará tal cual.
- «⚠ Nombre repetido: se conservan ambos»: ya tienes uno con ese nombre. En **Este nombre ya
  existe** eliges **Conservar ambos (el importado se renombra)** (lo normal), **Reemplazar el
  perfil que ya tengo** (solo con perfiles tuyos y con una confirmación más) u **Omitir este
  perfil**. Un perfil de fábrica nunca se reemplaza.
- «✖ No válido»: el archivo tiene ese perfil dañado; no se puede marcar.

Pulsa **Importar N perfiles**. Los importados son siempre perfiles **tuyos**, aunque el archivo
dijera otra cosa.

### Dónde se guardan

Tus perfiles van en `perfiles_maquina.json`, en la misma carpeta de configuración que
`perfiles.json` (ver [Qué se guarda y dónde](#qué-se-guarda-y-dónde)). Si el archivo se dañó,
ProxLaunch guarda una copia y empieza con la lista vacía: «Tu archivo de perfiles estaba dañado.
Se guardó una copia («…») y se empezó con la lista vacía.» Si lo creó una versión más nueva de
ProxLaunch, tus perfiles se muestran pero no se pueden modificar.

---

## Guardar y abrir lotes

Un **lote guardado** es un archivo que recuerda cómo preparaste un lote, para repetirlo otro día
o en otro servidor. Se guarda como `.proxlaunch-lote.json`. El menú es **Lote**:

| Opción | Atajo | Qué hace |
|---|---|---|
| **Abrir lote…** | Ctrl+O | Carga un lote guardado. **Necesita estar conectado.** |
| **Guardar lote…** | Ctrl+S | Guarda el lote actual. |
| **Guardar lote como…** | Ctrl+Mayús+S | Guarda con otro nombre o en otro sitio. |

### Qué se guarda

El lote es **autocontenido**: lleva la configuración de hardware (con los nombres de
almacenamiento y red que usaste), la cantidad, el patrón de nombres, el número de máquina
inicial **solo si lo escribiste tú**, dónde crearlas, el reparto, si etiquetar, el nombre del lote
y la versión de Proxmox con la que lo guardaste. En un [lote por filas](#lote-por-filas) guarda
además cada fila: nombre, número, nodo y configuración.

**No se guarda nunca:** datos de conexión (servidor, usuario, token, contraseña), el resumen, los
números ya reservados, el código del lote ni la casilla de sobreasignar espacio (esa se vuelve a
pedir). Si algún texto que escribiste parece una credencial (`usuario@realm!token=...`), ProxLaunch
**no guarda** y te dice en qué campo: «No se guardó: el campo «nombre de la máquina» parece
contener una credencial (usuario@realm!token). Bórrala y vuelve a guardar.» (el valor no se
muestra).

### Guardar

1. Prepara el lote (también vale con **1** máquina).
2. **Lote > Guardar lote…**. En **Guardar lote**, escribe el **Nombre del lote** (por ejemplo,
   «Servidores web de pruebas»).
3. Pulsa **Elegir dónde guardar…** y elige la carpeta. ProxLaunch sugiere la carpeta `lotes` de
   tus datos de usuario.
4. Verás «Lote guardado en «archivo.json»».

Si el lote viene de un archivo que abriste o guardaste, el diálogo ofrece **Sobrescribir el
archivo «x»** (con confirmación) o **Guardar como un archivo nuevo…**.

**Puedes guardar un lote con errores.** Se guarda como borrador: el diálogo avisa «El lote tiene
problemas; se comprobará otra vez al abrirlo.» La única excepción es un campo numérico con texto
que no es un número: «No se puede guardar el lote: «Núcleos por socket» no es un número.
Corrígelo e inténtalo de nuevo.» También puedes guardar mientras hay un lote en marcha.

### Abrir

1. Conéctate a un servidor. **Lote > Abrir lote…** y elige el archivo (si hay
   [cambios sin guardar](#cambios-sin-guardar), antes te pregunta).
2. ProxLaunch lee y comprueba **todo el archivo** antes de tocar nada. Si algo falla, el
   formulario **no cambia** y ves el motivo con la lista de campos. Si va bien: «Lote «X» cargado».
3. El formulario y el bloque **Lote** quedan rellenados. **No se crea nada**: revisa y pulsa
   **Ver resumen** (o **Crear máquina** si el lote es de una sola máquina).

El selector **Perfil de máquina** queda en «Personalizado». ProxLaunch **no vigila ni vuelve a
leer** el archivo: si lo cambias después con otro programa, ábrelo de nuevo.

**Avisos del archivo.** Un panel que puedes cerrar con **Cerrar** te cuenta lo que no se usó:
campos que ProxLaunch no conoce, datos que parecen una credencial («El archivo traía datos que
parecen una credencial. No se usaron. Si eran reales, cámbialas.»), o que el lote se guardó con
una versión de Proxmox más nueva («El lote se guardó con Proxmox 9.2; este servidor tiene 8.4.
Algunas opciones podrían no estar disponibles.»).

### Si el lote «no encaja» en este servidor

Un lote guardado en otro servidor puede nombrar un almacenamiento, una red o un nodo que **este**
servidor no tiene. ProxLaunch **nunca los cambia por su cuenta**. Aparece el panel **Este lote no
encaja en este servidor**: «Algunos valores guardados en el lote no existen aquí. Elige otros
para poder continuar: ProxLaunch no cambia nada por su cuenta.» Cada línea dice qué falta («El
almacenamiento «datos» no existe en este servidor o no admite discos.»). En un
[lote por filas](#lote-por-filas) añade a cuántas máquinas afecta («Afecta a 3 máquinas (n.º 2,
5, 7).»). Para cada una:

- **Usar otro…** abre **Usar otro valor** con lo que sí hay en el servidor («Almacenamiento que
  reemplaza a «datos»:»). Eliges y se cambia en todo el lote.
- **Pasar a Automático** (solo para nodos): deja que ProxLaunch elija el nodo.

Mientras tanto, en las tablas de discos y de red el valor aparece como «datos (no existe)» con un
error, y no puedes seguir. Si el lote usa **Nodos elegidos** y alguno no existe, ProxLaunch lo dice
(«Este servidor no tiene uno de los nodos del lote. Quítalo de la lista o pasa a Automático para
continuar.») y no avanza hasta que lo resuelvas: desmarca ese nodo en la lista (en modo avanzado)
o usa **Pasar a Automático**. Con **Nodos elegidos** en modo básico, la lista se ve pero no se
cambia: «Este lote usa nodos elegidos; cámbialo en modo avanzado.»

Si cambias de servidor con un lote abierto, el lote se queda en pantalla y todo se vuelve a
comprobar con el servidor nuevo.

---

## Importar máquinas desde un CSV

Con **Importar desde CSV…** creas un lote con **una máquina por cada fila** de una hoja de
cálculo. Cada fila puede tener su propia configuración; el resultado es un
[lote por filas](#lote-por-filas). **Nada se crea** al importar: después hay un resumen que debes
confirmar, como en cualquier lote.

### Paso a paso

1. **Lote > Descargar plantilla CSV…** Elige el separador (**; (Excel en español)** o **, (Excel
   en inglés)**) y dónde guardarla (`plantilla-proxlaunch.csv`).
2. Ábrela en Excel o LibreOffice Calc, cambia los datos y guarda como **CSV UTF-8**.
3. **Lote > Importar desde CSV…** y elige tu archivo. Si tienes
   [cambios sin guardar](#cambios-sin-guardar), antes te pregunta.
4. Revisa la **vista previa** (ver más abajo) y pulsa **Continuar**.
5. Aparece el [lote por filas](#lote-por-filas): pulsa **Ver resumen**.

### La plantilla

La plantilla trae las columnas más usadas y cinco filas de ejemplo: dos con disco vacío y una por
cada origen del sistema operativo (ISO, disco existente y plantilla). Los nombres de las filas
empiezan por `ejemplo-`; si las importas tal cual, ProxLaunch avisa «Parece una fila de ejemplo
de la plantilla.» Abierta en una hoja de cálculo se ve así:

| nombre | perfil | cpu | memoria | disco | almacenamiento | red | vlan | nodo | vmid | origen | fuente | so | virtio | modo_clon |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ejemplo-01 | fabrica.servidor-mediano | | 8 | 100 | local-lvm | vmbr0 | | | | vacio | | | | |
| ejemplo-02 | | 2 | 4 GiB | 40 | | vmbr1 | 20 | pve2 | 250 | vacio | | | | |
| ejemplo-03 | | 2 | 4 | 32 | | | | | | iso | ejemplo-instalador.iso | linux | | |
| ejemplo-04 | | 2 | 4 | 40 | | | | | | importar | ejemplo-disco.qcow2 | | | |
| ejemplo-05 | | 4 | 8 | 80 | | | | | | clonar | ejemplo-plantilla | | | auto |

Y así es el texto del archivo (separador `;`; ProxLaunch escribe **todas las celdas entre
comillas**):

```text
"nombre";"perfil";"cpu";"memoria";"disco";"almacenamiento";"red";"vlan";"nodo";"vmid";"origen";"fuente";"so";"virtio";"modo_clon"
"ejemplo-01";"fabrica.servidor-mediano";"";"8";"100";"local-lvm";"vmbr0";"";"";"";"vacio";"";"";"";""
"ejemplo-02";"";"2";"4 GiB";"40";"";"vmbr1";"20";"pve2";"250";"vacio";"";"";"";""
"ejemplo-03";"";"2";"4";"32";"";"";"";"";"";"iso";"ejemplo-instalador.iso";"linux";"";""
"ejemplo-04";"";"2";"4";"40";"";"";"";"";"";"importar";"ejemplo-disco.qcow2";"";"";""
"ejemplo-05";"";"4";"8";"80";"";"";"";"";"";"clonar";"ejemplo-plantilla";"";"";"auto"
```

Cámbialo por **tus** datos: `local-lvm`, `vmbr0`, `vmbr1`, `pve2`, `ejemplo-instalador.iso`,
`ejemplo-disco.qcow2` y `ejemplo-plantilla` son ejemplos y quizá tu servidor no los tenga. Una celda
vacía significa «usa lo del perfil» (o, en `nodo` y `vmid`, «elige ProxLaunch»). Las columnas de
origen (`origen`, `fuente`, `so`, `virtio` y `modo_clon`) se explican en
[Orígenes en lotes, perfiles y CSV](#orígenes-en-lotes-perfiles-y-csv). En las filas que
importan o clonan (`ejemplo-04`, `ejemplo-05`), `disco`, `cpu` y `memoria` tienen otro significado:
ver esa sección.

### Columnas

Solo **`nombre`** es obligatoria. Los nombres de columna no distinguen mayúsculas ni acentos, y
espacio y guion valen como guion bajo (`Tipo CPU`, `tipo-cpu` y `tipo_cpu` son lo mismo). También se
aceptan estos alias:

| Columna | Alias aceptados | Qué es | Si está vacía |
|---|---|---|---|
| `nombre` (obligatoria) | `name`, `hostname` | Nombre de la máquina. | Error: «Falta el nombre.» |
| `perfil` | `profile` | Perfil de la fila: su nombre (como en la lista, sin importar mayúsculas ni acentos) o su identificador, por ejemplo `fabrica.servidor-mediano`. | El **perfil base**. |
| `vmid` | `id` | Número de máquina. | Automático. |
| `nodo` | `node` | Nodo donde crearla. | Automático. |
| `cpu` | `cores`, `nucleos` | **Núcleos por socket**. | Lo del perfil. |
| `sockets` | `zocalos` | Sockets. | Lo del perfil. |
| `memoria` | `ram`, `memoria_gib`, `memoria_mib` | Memoria (ver unidades). | Lo del perfil. |
| `disco` | `disco1`, `disco_gib`, `tamano_disco` | Tamaño del primer disco (ver unidades). | Lo del perfil. |
| `almacenamiento` | `storage`, `almacenamiento1` | Almacenamiento del primer disco. | Lo del perfil, o el de más espacio libre. |
| `disco2` … `disco8` | | Tamaño de los discos 2 a 8. | No hay ese disco (o el del perfil). |
| `almacenamiento2` … `almacenamiento8` | `storage2` … `storage8` | Almacenamiento de los discos 2 a 8. | El del primer disco. |
| `red` | `bridge`, `red1` | Red (bridge) de la primera interfaz. | Lo del perfil. |
| `vlan` | `vlan1` | VLAN de la primera interfaz (1 a 4094). | Lo del perfil. |
| `modelo_red` | `tarjeta_red` | Tarjeta de red: `virtio` o `e1000`. | Lo del perfil. |
| `firmware` | `bios` | Arranque: `seabios` o `bios`; `ovmf` o `uefi`. | Lo del perfil. |
| `tipo_cpu` | `cpu_tipo` | Tipo de CPU (por ejemplo `x86-64-v2-AES`). | Lo del perfil. |
| `origen` | `source` | De dónde sale el sistema operativo: `vacio`, `iso`, `importar` o `clonar` (ver [Orígenes en lotes, perfiles y CSV](#orígenes-en-lotes-perfiles-y-csv)). | Lo del perfil. |
| `fuente` | `origen_archivo`, `iso`, `plantilla`, `imagen` | Nombre del ISO, del disco o de la plantilla. | Sin fuente. |
| `so` | `sistema` | Sistema operativo del asistente (con `iso` o `importar`). | Sin asistente. |
| `virtio` | `drivers` | `si` o `no`: con o sin el CD de drivers virtio-win (solo Windows con `iso`). | Detectar el CD de drivers. |
| `modo_clon` | `clon` | `auto`, `enlazado` o `completo` (solo con `clonar`). | `auto`. |

Reglas de lectura:

- Una columna que ProxLaunch no conoce se **ignora** y se avisa («La columna «notas» no se usa y
  se ignoró.»).
- Una columna cuyo nombre parece una credencial (contiene `token`, `password`, `contraseña`,
  `secreto`, `ticket`, `csrf`, `apikey` o `credencial`) se ignora **sin leer sus celdas**.
- Una columna repetida («La columna «cpu» aparece dos veces.»), o datos en una columna sin
  encabezado, o la falta de `nombre`, impiden leer el archivo.
- Tu archivo se **lee y nunca se modifica**.

**Qué manda cuando hay varios valores.** De menor a mayor: los valores normales de ProxLaunch,
luego el **perfil** (el de la columna `perfil`, o el **Perfil base** si la celda está vacía), y por
último las **columnas del archivo**. Si una fila dice `memoria` = 8 y su perfil trae 4 GiB, se
crea con 8 GiB.

### Unidades y números

| Dato | Qué puedes escribir | Notas |
|---|---|---|
| `memoria` | `8` (se entiende **GiB**), `4 GiB`, `512 MiB`, `1 TiB`; también `M`, `G`, `T`, `MB`, `GB`, `TB` | `MB`, `GB` y `TB` se toman como `MiB`, `GiB` y `TiB` (1 GB = 1024 MiB) y ProxLaunch lo avisa. Debe dar una cantidad entera de MiB (`0,5` = 512 MiB vale; `0,3` no). |
| `disco`, `disco2`… | `100` (se entiende **GiB**), `500 GiB`, `1 TiB`, `2048 MiB` | Debe dar un número entero de GiB, de 1 en adelante. `0`, `ninguno`, `ninguna`, `sin disco` o `sin_disco` = **sin disco**. |
| `cpu`, `sockets`, `vmid`, `vlan` | `2` o `2.0` | `2.5` no vale. |
| decimales | `0,5` o `0.5` | Con coma se avisa («se usó la coma como separador decimal»). |
| miles | **no los uses** | `1.000` o `1,000` es ambiguo: «¿Quisiste decir mil o uno? Escribe 1000 o 1.» |

Si la columna se llama `memoria_mib`, un número sin unidad se entiende como **MiB** (y con
`memoria_gib` o `disco_gib`, como GiB). Una unidad escrita en la celda manda sobre el nombre de la
columna. No se admiten signos, exponentes, hexadecimales ni `NaN`. Si una memoria pasa de
1024 GiB (o de la memoria libre del nodo que más tiene) ProxLaunch avisa «Pides 4096 GiB de
memoria. ¿Querías MiB?» pero no lo bloquea.

### La vista previa

Al elegir el archivo se abre **Importar desde CSV**. Arriba ves el archivo, el **Perfil base:** (por
defecto el que tengas aplicado, o «Servidor pequeño»; si lo cambias, todo se revisa de nuevo), y
una línea de resumen: «Codificación UTF-8 · separador «;» · 10 filas: 7 correctas, 1 con aviso, 2
con error».

La tabla tiene una fila por fila del archivo, con **Incluir**, **Fila**, **Nombre**, **Perfil**,
**VMID**, **Nodo**, **Núcleos**, **Memoria**, **Disco**, **Almacenamiento**, **Red** y **Estado**:
«✔ Correcta», «⚠ Con aviso» o «✖ Con error». El número de **Fila** es el que ves en Excel (el
encabezado es la fila 1, así que tu primera máquina es la fila 2). Al seleccionar una fila, el
detalle muestra sus problemas («Fila 7, columna «memoria»: «abc» no es un número. Escribe, por
ejemplo, 4 GiB.») y el **Valor del archivo** de cada celda. Si una fila tiene muchos problemas, se
muestran los primeros cinco y «y N más».

Herramientas:

- **Mostrar solo problemas**: oculta las filas correctas.
- **Copiar errores**: copia al portapapeles la lista de errores.
- **Descargar filas con error…**: guarda un CSV (`tu-archivo-errores.csv`) con **solo** las filas con
  error, tus mismas columnas más `fila_original`, `columna` y `problema`. Corrígelo y vuélvelo a
  importar: esas tres columnas se ignoran al leerlo.
- **Elegir otro archivo…** y **Descargar plantilla…**.
- La casilla **Incluir** de cada fila deja fuera las que no quieras. Las filas con error no se
  pueden marcar.

**Codificación y separador.** ProxLaunch los detecta solo. La **codificación** es cómo el archivo
guarda los acentos (prueba UTF-8 con y sin marca, UTF-16 y Windows-1252). El **separador** es el
carácter entre columnas (`;`, `,` o tabulador, o la línea `sep=;` que escribe Excel). Si no puede
decidir entre dos, usa `,` y avisa: «No se pudo saber qué separador usa el archivo. Elige uno en la
lista «Separador».» Las listas **Codificación:** y **Separador:** se ven siempre en modo avanzado;
en modo básico, el separador solo aparece cuando hay duda. Si ves símbolos raros, guarda el archivo
como **CSV UTF-8** desde Excel.

**Límites.** Hasta **100 filas** (sin contar la de encabezados ni las vacías), 40 columnas, 256
caracteres por celda y 1 MiB por archivo. Si te pasas, ProxLaunch no recorta: te pide dividir el
archivo («El archivo tiene 130 filas; el máximo por lote es 100. Divide el archivo en partes.»).

**Sin conexión.** Puedes abrir la vista previa sin conexión, pero se comprueba solo lo que no
depende del servidor, aparece «Sin conexión: aún no se comprobó contra el servidor. Conéctate a
un servidor para poder continuar.» y **Continuar** queda desactivado.

### Confirmar la importación

- **Todo correcto** (sin errores): pulsa **Continuar**. Los avisos no impiden continuar.
- **Hay errores**: el botón principal es **Corregir el archivo**; cierra la vista previa sin
  cambiar nada, para que arregles el CSV y lo importes otra vez. La alternativa es **Importar
  solo las N filas correctas**: ProxLaunch lista las filas que se quedarían fuera («Se importarán 8
  de 10 filas del archivo. No se importarán estas filas: …») y te pide confirmar con **Importar
  esas filas** o **Cancelar**.

Al terminar verás «Se importaron N máquinas desde «archivo.csv»» y el [lote por filas](#lote-por-filas).

### Seguridad de los archivos CSV

- ProxLaunch **solo lee** tu CSV; nunca lo modifica.
- Las celdas se tratan como texto: nunca se ejecuta una fórmula ni se abre un enlace.
- Los CSV que **escribe** ProxLaunch (plantilla, filas con error, informe) llevan todas las
  celdas entre comillas, en UTF-8 con marca (BOM), y si una celda empieza por `=`, `+`, `-` o
  `@` se le antepone un apóstrofo (`'`) para que Excel no la tome por una fórmula. Al reimportar
  un archivo así, ese apóstrofo se quita una vez.

---

## Lote por filas

Un **lote por filas** es un lote en el que **cada máquina tiene su propia configuración**. Nace al
[importar un CSV](#importar-máquinas-desde-un-csv) o al abrir un lote que se guardó así. Es un
solo lote: un resumen, una confirmación, un informe y un **Deshacer…**.

### Cómo se ve

El formulario y el selector de perfil desaparecen y en su lugar hay una tabla de solo lectura.
Arriba dice, por ejemplo, «8 máquinas desde el archivo «servidores.csv»» (o «del lote «Aula 3»»),
con la nota «Cada máquina trae su propia configuración. Para cambiar algo, corrige el archivo e
impórtalo de nuevo, o quita las filas que no quieras.» La tabla tiene **Fila**, **Nombre**,
**VMID**, **Nodo**, **Procesadores**, **Memoria (GiB)**, **Discos (GiB)**, **Almacenamiento** y
**Red**.

El bloque **Lote** oculta la cantidad, el prefijo y el destino (cada fila trae lo suyo) y deja el
reparto (modo avanzado), el número de máquina inicial para las filas sin número (modo avanzado)
y **Etiquetar las máquinas** (modo avanzado).

### Botones

| Botón | Qué hace |
|---|---|
| **Ver resumen** | Prepara el resumen del lote. Si hay errores en las filas, queda desactivado y aparece «Corrige los errores marcados para poder ver el resumen.» |
| **Revisar filas…** | Solo si viene de un CSV: reabre la vista previa. Se vuelve a comprobar contra el servidor actual. |
| **Guardar lote…** | Guarda el lote por filas (ver [Guardar y abrir lotes](#guardar-y-abrir-lotes)). |
| **Quitar las filas seleccionadas** | Saca del lote las filas que marques en la tabla. Tu CSV no cambia. Si quitas todas, vuelves al formulario. |
| **Salir del lote por filas** | Vuelve al formulario normal. Si hay [cambios sin guardar](#cambios-sin-guardar), pregunta antes. |

No hay forma de editar una fila dentro de la aplicación: corrige el CSV e impórtalo otra vez.

### El resumen de un lote por filas

Es el resumen de siempre ([El resumen y la confirmación](#el-resumen-y-la-confirmación)), con
estas diferencias:

- La tabla muestra **Fila** (el número de tu archivo), **Procesadores** y **Memoria (GiB)** de
  cada máquina, y los errores dicen «Fila 4: …».
- Si importaste solo una parte del archivo, lo recuerda: «Se van a crear 8 de las 10 filas del
  archivo.»
- **No caben todas.** En lugar de **Reducir a N**, el resumen dice qué filas sobran («No caben las
  filas: 3, 7.») y ofrece **Quitar las filas que no caben**, que las saca y vuelve a calcular. Si
  prefieres otra solución, no lo pulses: libera espacio o cambia el CSV.
- **Un número de máquina ocupado.** Si una fila pide un `vmid` que otra máquina ya usa, ves
  «Fila 4: el número 150 ya lo usa otra máquina.» ProxLaunch **no lo cambia solo**. Pulsa
  **Asignar automáticamente** (por fila, o **Asignar automáticamente a las N filas**) para que
  tome el siguiente libre.
- **Un nodo que no sirve.** Si una fila nombra un nodo apagado o que no tiene el almacenamiento o la
  red que pide, ves por qué («Fila 3: «pve2» está sin conexión.»).

Después, como siempre: **Simular** (opcional) y **Crear N máquinas**. El
[informe](#informe) incluye la configuración de cada máquina. **Reintentar pendientes** conserva
la configuración, el nombre, el número y el nodo de cada fila. Con **Lote > Guardar el informe del
lote como CSV…** guardas el resultado en una hoja de cálculo (`numero`, `nombre`, `vmid`, `nodo`,
`desenlace`, `resultado`, `codigo_error`, `duracion_s`; sin direcciones ni identificadores de tarea).

---

## Cambios sin guardar

ProxLaunch no quiere que pierdas un lote por descuido. Si hay un lote **cargado, importado o
editado** y todavía no lo guardaste (o cambiaste algo desde que lo guardaste), antes de continuar
te pregunta:

> **Cambios sin guardar**: ¿Guardar el lote antes de continuar? Si no lo guardas, se perderán los
> cambios del lote.

Con tres botones: **Guardar**, **No guardar** y **Cancelar**. El foco está en **Cancelar**, así que
pulsar Intro sin mirar no pierde nada.

- **Guardar**: abre **Guardar lote**; cuando termina de guardar, sigue con lo que ibas a hacer.
- **No guardar**: sigue y descarta los cambios.
- **Cancelar**: no hace nada; sigues donde estabas.

Pregunta en estos momentos: **cerrar ProxLaunch**, **Archivo > Cerrar sesión**, **Lote > Abrir
lote…**, **Lote > Importar desde CSV…**, **cambiar de servidor** (**Archivo > Conectar...**) y **Salir
del lote por filas**. También cuenta si lo único que hiciste fue cambiar el formulario o el bloque
**Lote** a mano.

Si cierras con un lote **en marcha**, solo ves el aviso de siempre
([Cerrar ProxLaunch con un lote en curso](#cerrar-proxlaunch-con-un-lote-en-curso)).

---

## Mensajes de error frecuentes

Los textos de la columna «Mensaje» son los que muestra ProxLaunch. El mensaje original de
Proxmox está en «Ver detalles técnicos»; se comprobó con Proxmox VE 9.2.

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| Las credenciales no son válidas. Revisa el usuario, el token o la contraseña. | Proxmox rechazó la entrada. Por seguridad no dice si falló el usuario o la contraseña. | Revisa mayúsculas, el realm y que el token esté completo. Si el token se creó con otro realm, escríbelo igual. |
| No se pudo contactar con el servidor (192.0.2.10:8006) | No hubo respuesta a tiempo (10 s por servidor). | Revisa la IP, el puerto, tu red o VPN. Prueba con otro servidor del perfil. |
| No se pudo contactar con ninguno de los servidores del perfil: … | Ninguno de los servidores del perfil responde. Cada línea dice el motivo: «no respondió a tiempo», «conexión rechazada» o «no respondió». | Revisa red y VPN; pregunta si el servidor está encendido. |
| El certificado del servidor cambió… | La huella ya no coincide con la guardada. | Ver [Si aparece «El certificado del servidor cambió»](#si-aparece-el-certificado-del-servidor-cambió). |
| Primero hay que confiar en el certificado del servidor (…). | Intentaste conectar sin aceptar la huella. | Vuelve a **Probar y conectar** y acepta la huella si coincide. |
| El token debe tener el formato usuario@realm!nombre=secreto. | El token está incompleto o tiene espacios. | Pégalo completo, sin espacios ni saltos de línea. |
| Escribe solo el nombre o la IP del servidor. | El servidor tiene un formato no válido. | Usa solo una IP o un nombre. |
| El código no es correcto o ya venció. … | Código de 2FA incorrecto o caducado. | Espera al siguiente código; revisa que la hora de tu equipo sea correcta. |
| Este usuario exige un método de segundo factor que ProxLaunch no admite. Usa un API Token. | El usuario usa llaves de seguridad u otro método no admitido. | Conecta con un API Token. |
| Tu sesión expiró. Vuelve a iniciar sesión. | La sesión caducó (por ejemplo, tras suspender el equipo). | Se abre la ventana de conexión; entra de nuevo. **No pierdes lo escrito en el formulario.** |
| ProxLaunch requiere Proxmox VE 8.0 o superior (el servidor tiene 7.4) | Versión no compatible. | Pide actualizar Proxmox o usa otro servidor. |
| Tu usuario no tiene permiso para realizar esta acción. Falta VM.Allocate en /vms/100. … | Falta un permiso. El mensaje dice cuál y en qué ruta. | Pide ese permiso a tu administrador (ver [Permisos que hacen falta](#permisos-que-hacen-falta)). |
| El número 100 ya lo usa otra máquina. Prueba con 101 | El VMID está ocupado (por ejemplo, alguien lo usó mientras rellenabas el formulario). | Usa el sugerido o escribe otro. El formulario conserva tus datos. |
| No hay espacio suficiente en «local-lvm» para crear el disco. Libera espacio o elige otro almacenamiento. | El almacenamiento se llenó. | Reduce el tamaño, elige otro almacenamiento o libera espacio. |
| El disco pide 200 GiB y «local-lvm» solo tiene 150 GiB libres. | Antes de enviar, ProxLaunch ve que no cabe. | Reduce el tamaño o cambia de almacenamiento. |
| Ningún nodo tiene N GiB libres en un almacenamiento para discos… | En modo Automático ningún nodo tiene sitio. | Reduce los discos o libera espacio. |
| El nodo pve2 no está disponible | El nodo elegido cayó antes de enviar. No se creó nada. | Elige otro nodo (ProxLaunch vuelve a leer el estado) o pulsa **Actualizar**. |
| «x» ya no existe en el nodo. Actualiza y elige de nuevo. | Un almacenamiento o red desapareció. | Pulsa **Actualizar** y vuelve a elegir. |
| Este servidor no tiene almacenamiento para discos de máquinas virtuales | No hay dónde guardar discos. | Marca **Sin disco** o pide a tu administrador que habilite un almacenamiento. |
| Proxmox no entendió el valor de … / Proxmox rechazó el valor de … | Proxmox no aceptó un parámetro. | Corrige el campo indicado. Si no puedes, copia los **detalles técnicos** y avisa al administrador. |
| Proxmox no devolvió el identificador de la tarea | La respuesta llegó sin UPID. | Pulsa **Actualizar** y comprueba en Proxmox si la máquina existe antes de repetir. |
| Proxmox dijo que la tarea terminó, pero la máquina N no aparece en el nodo X. | Raro: la tarea terminó, pero la máquina no se ve. | Revisa en Proxmox y en los detalles técnicos. |
| Proxmox respondió con un error que no conocemos | Un error que ProxLaunch no sabe traducir. | Abre **Ver detalles técnicos**, copia el texto y compártelo con tu administrador. |
| No se pudo leer el nodo X: aparece como «Sin conexión». | Falló la lectura de un nodo. Los demás siguen disponibles. | Pulsa **Reintentar** (junto a **Actualizar**). |
| No hay un llavero disponible en este equipo; las credenciales no se guardarán | Marcaste «Recordar credenciales», pero tu sistema no tiene llavero. | La conexión continúa; tendrás que escribir el secreto cada vez. |

### Mensajes de archivos, perfiles y CSV

Estos mensajes aparecen al guardar, abrir o importar archivos (perfiles, lotes y CSV). En todos,
**tu archivo original no se modifica** y, si falla al abrir o importar, el formulario queda como
estaba.

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| No se pudo leer el archivo. Si está abierto en otro programa (como Excel), ciérralo o guarda una copia. (puede empezar por «El archivo no existe.» o «No tienes permiso para leer ese archivo.») | El archivo no existe, no tienes permiso o otro programa lo tiene bloqueado. | Cierra Excel u otro programa que lo tenga abierto, o trabaja con una copia. Revisa la ruta y los permisos. |
| No se puede abrir este archivo: es demasiado grande (límite 1 MiB). / …no es un archivo normal. / …tiene demasiados elementos (máximo 100). | Superó el tamaño permitido (1 MiB para lotes y CSV, 256 KiB para perfiles), es una carpeta u otro tipo de elemento, o trae más de 100 perfiles. | Elige un archivo normal y más pequeño. Divide el contenido en varios archivos. |
| Este archivo no es un archivo de ProxLaunch del tipo que buscas. (a veces sigue «Parece un archivo de perfiles de máquina…» o «Parece un archivo de lote guardado.») | Elegiste un archivo de otro tipo (por ejemplo, un lote donde se esperaban perfiles). | Usa la opción que corresponde: perfiles en **Administrar perfiles… > Importar…**, lotes en **Lote > Abrir lote…**, CSV en **Lote > Importar desde CSV…**. |
| Este archivo lo creó una versión más nueva de ProxLaunch. Actualiza la aplicación para abrirlo. | El formato del archivo es más nuevo que esta versión. | Actualiza ProxLaunch. |
| El archivo está dañado o tiene datos no válidos: … (seguido de la lista de campos, por ejemplo «por_filas.filas[2].config.memoria_mib: fuera de rango») | Falta un dato, tiene un tipo o un valor que no corresponde, o el texto no es JSON válido. Se muestran hasta 10 campos y «y N más». | Corrige esos campos con un editor de texto, o vuelve a guardar el archivo desde ProxLaunch. |
| El archivo tiene 130 filas; el máximo por lote es 100. Divide el archivo en partes. (también para columnas y celdas demasiado grandes) | El CSV supera los límites. | Divide el CSV en archivos de hasta 100 filas, 40 columnas y 256 caracteres por celda. |
| No pude leer el archivo CSV (fila 12). Guárdalo como «CSV UTF-8» desde Excel. / Hay unas comillas sin cerrar en la fila 12… | El archivo tiene caracteres que no se pueden leer o unas comillas sin cerrar. | En Excel: **Guardar como > CSV UTF-8**. Revisa la fila que indica el mensaje (numerada como en Excel). |
| El archivo no tiene máquinas. | El CSV tiene encabezado pero ninguna fila de datos. | Añade filas. |
| Falta la columna «nombre». Columnas reconocidas: … / La columna «cpu» aparece dos veces. / Hay datos en columnas que no tienen encabezado (columnas 7). | El encabezado del CSV no sirve. | Añade o renombra la columna `nombre`, quita las repetidas o ponle encabezado a la columna que tiene datos. Ver [Columnas](#columnas). |
| «abc» no es un número. Escribe, por ejemplo, 4 GiB. (y variantes: «…no es un número entero», «…no da una cantidad entera de GiB/MiB», ««xx» no es una unidad válida. Usa MiB, GiB, TiB…») | Una celda no se puede leer como número o unidad. | Corrige la celda. Ver [Unidades y números](#unidades-y-números). |
| ¿Quisiste decir mil o uno? Escribe 1000 o 1. | Un número con punto o coma de miles (`1.000`) es ambiguo. | Escríbelo sin separador de miles. |
| No existe el perfil «x». Perfiles disponibles: … / Hay más de un perfil llamado «x». Escribe el nombre exacto. | La columna `perfil` nombra un perfil que no existe o que está repetido. | Escribe el nombre tal como está en la lista, o su identificador (por ejemplo `fabrica.servidor-mediano`). |
| Las filas 3, 9 tienen el mismo nombre «web-01». / …el mismo número de máquina «150». | Hay nombres o números repetidos entre filas del archivo. | Cambia uno de los dos; ambas filas quedan marcadas con error hasta entonces. |
| Fila 5: «pve2» está sin conexión. / El nodo no existe en este servidor. / Ningún nodo del servidor puede alojar esta máquina. | La fila nombra un nodo (o un almacenamiento o red) que este servidor no tiene o no puede usar. | Corrige la celda, o déjala vacía para que ProxLaunch elija. |
| No se pudo guardar el archivo: … No se cambió nada. (el motivo puede ser «no hay espacio en el disco», «no tienes permiso para escribir ahí», «el archivo está abierto en otro programa», «la ruta es demasiado larga» u «ocurrió un error al escribir») | No se pudo escribir el archivo. El anterior sigue intacto. | Libera espacio, elige otra carpeta, cierra el programa que lo tiene abierto o usa una ruta más corta. |
| No se guardó: el campo «…» parece contener una credencial (usuario@realm!token). Bórrala y vuelve a guardar. | Un nombre, prefijo u otro texto tiene la forma de un API Token. ProxLaunch nunca guarda eso en archivos. | Borra el texto de ese campo y guarda de nuevo. |
| Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión. | Intentaste modificar, renombrar o borrar un perfil de fábrica. | Usa **Duplicar…** y trabaja con la copia. |
| Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden modificar. | Tu `perfiles_maquina.json` es de una versión más nueva. | Actualiza ProxLaunch. Mientras tanto puedes usarlos, no cambiarlos. |
| Este lote no encaja en este servidor: … | El lote nombra un almacenamiento, red o nodo que este servidor no tiene. | Ver [Si el lote «no encaja»](#si-el-lote-no-encaja-en-este-servidor). |
| Escribe un nombre de 1 a 60 caracteres. / Ya existe un perfil con ese nombre. / Llegaste al máximo de 100 perfiles. Elimina alguno para crear otro. / Parece un token de acceso. No lo escribas aquí. | El nombre del perfil o del lote no es válido. | Elige otro nombre, o elimina un perfil que ya no uses. |

Además verás avisos (⚠) que no impiden seguir: «Se ignoró 1 campo que ProxLaunch no conoce.» (el
archivo tenía datos que esta versión no usa), «El archivo traía datos que parecen una credencial.
No se usaron. Si eran reales, cámbialas.», «En la columna «memoria» había números sin unidad: se
entendieron como GiB.» y «En la columna «disco», «GB» se tomó como GiB (1 GB = 1024 MiB).»

### Mensajes del origen del sistema operativo

Aparecen al elegir un ISO, un disco o una plantilla, al subir o descargar archivos y al crear con
esos orígenes (ver [Elegir el origen del sistema operativo](#elegir-el-origen-del-sistema-operativo)).
Los puntos suspensivos (…) son datos que cambian en cada caso.

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| Tu Proxmox … no permite importar discos sin ser administrador del servidor. Puedes instalar desde un ISO o clonar una plantilla. Desde la versión 8.4 sí se puede importar. | El servidor es Proxmox 8.0 a 8.3. | Instala desde un ISO, clona una plantilla o actualiza Proxmox a 8.4 o superior. |
| Para importar discos, pide a tu administrador que active el contenido «Import» en un almacenamiento de tipo directorio, NFS o CIFS. | No hay un almacenamiento con el contenido «Import». | Pide al administrador que lo active (**Datacenter → Almacenamiento → Editar → Contenido**). Puedes copiar el texto desde **Qué puedo hacer en este servidor**. |
| Falta el permiso Sys.AccessNetwork en el nodo «…» para descargar desde una dirección web. Pídeselo a tu administrador o descarga el archivo en tu equipo y súbelo. | Tu cuenta no puede hacer que el servidor descargue de Internet. | Pide el permiso o usa **Subir desde mi equipo…**. |
| Descargar desde una dirección web exige permisos de administrador en esta versión de Proxmox. Descarga el archivo en tu equipo y súbelo. | Proxmox 8.0 o 8.1. | Sube el archivo desde tu equipo. |
| Falta el permiso … en «…» para …. | Falta un privilegio del rol en esa ruta (por ejemplo `VM.Clone` o `Datastore.AllocateTemplate`). | Ver [Permisos que hacen falta](#permisos-que-hacen-falta) y [Permisos para el administrador](#permisos-para-el-administrador-alcance-acotado). |
| Para guardar el disco importado necesitas el permiso Datastore.AllocateSpace en «…». | La cuenta no puede crear discos en ese almacenamiento. | Pide el permiso en esa ruta, o elige otro almacenamiento. |
| No puedes ver los archivos de «…»: falta el permiso Datastore.Audit o Datastore.AllocateSpace. | El catálogo de ese almacenamiento no se puede leer. Los demás se muestran. | Pide el permiso o elige otro almacenamiento. |
| El almacenamiento «…» que usabas en este servidor ya no está disponible o ya no admite …. Elige otro. | El que recordabas desapareció, está inactivo o ya no admite ese contenido. ProxLaunch no lo sustituye en silencio. | Usa **Elegir otro** o **Dejar de recordar** (ver [el diálogo «¿Cuál usar siempre?»](#el-diálogo-cuál-usar-siempre-almacenamientos)). |
| Ningún almacenamiento activo de este servidor guarda …. Pide a tu administrador que lo active en uno. | No hay donde guardar ese contenido. | Pide al administrador que active el contenido en un almacenamiento. |
| Ya existe un archivo llamado «…» en «…». ProxLaunch no lo sobrescribe: usa el que ya está o elige otro nombre. | Ya hay un archivo con ese nombre. | Pulsa **Usar el existente** o **Cambiar el nombre**. |
| El archivo pesa … y «…» solo tiene … libres. | No cabe en el almacenamiento. | Libera espacio o elige otro almacenamiento. |
| El nodo «…» tiene poco espacio temporal (… libres) para recibir un archivo de …. La subida podría fallar. | Poco espacio en la raíz del nodo (donde Proxmox deja el archivo mientras lo recibe). | Marca **Entiendo que la subida puede fallar** solo si aceptas el riesgo; mejor pide al administrador que libere espacio (ver [Limpieza periódica](#permisos-para-el-administrador-alcance-acotado)). |
| Hay una transferencia en curso. Espera a que termine o cancélala. | Solo se hace una subida o descarga a la vez. | Espera, o cancela la actual. |
| El archivo cambió mientras se subía. Vuelve a intentarlo. | El archivo de tu equipo se modificó durante el envío. | Vuelve a subirlo sin tocarlo. |
| Se cortó la conexión mientras se subía el archivo. (puede seguir «Se habían enviado … de ….») | La subida se interrumpió. | Pulsa **Reintentar** y comprueba en el catálogo que no quedó un archivo a medias. |
| El archivo llegó dañado: la huella no coincide. No quedó guardado. | La huella SHA-256 del servidor no es la del archivo. | Vuelve a subirlo. Si se repite, revisa el archivo original. |
| El servidor dice que terminó, pero el archivo no coincide con el que enviaste. No lo uses. | La verificación final falló. | No uses ese archivo: pide al administrador que lo borre y súbelo otra vez. |
| El servidor no pudo descargar … desde …: …. Prueba a descargarlo en tu equipo y subirlo. | La descarga en el servidor falló (red, dirección, huella…). | Revisa la dirección y la huella, o súbelo desde tu equipo. |
| Transferencia cancelada. (con la frase de si quedó o no un archivo) | Cancelaste. | Si quedó un archivo parcial, pide al administrador que lo borre. |
| Este disco depende de otro archivo (un disco base). Conviértelo a un qcow2 independiente antes de subirlo. (también: cifrado, varios archivos, OVA, versión no compatible, incompleto o dañado) | El disco no se puede importar tal cual. | Convierte el disco como dice el mensaje y vuelve a subirlo. |
| Importar desde una ruta del servidor exige ser administrador (root). Sube el archivo desde tu equipo. | Escribiste una ruta del servidor como fuente. | Usa **Subir desde mi equipo…** o elige el disco del catálogo. |
| Aquí va el nombre de un archivo del servidor, no una dirección web. Para descargar usa «Descargar en el servidor». | Escribiste una dirección web en `fuente`. | Usa el botón de descarga o escribe solo el nombre del archivo. |
| … «…» ya no está en el servidor. Elige otra. | El ISO, disco o plantilla desapareció entre el resumen y la creación. | Elige otra fuente y vuelve a intentarlo. |
| No encuentro «…» en «…». Disponibles: …. | La fuente nombrada no está en ese nodo. | Elige una de las disponibles. |
| No veo ninguna plantilla con tu cuenta. Pide el permiso VM.Audit o crea la plantilla en Proxmox (clic derecho en la máquina → Convertir en plantilla). | No hay plantillas visibles. | Pide el permiso o crea una plantilla. |
| No se puede clonar así: …. | Proxmox no permite esa copia (plantilla bloqueada u ocupada, ya no es plantilla, almacenamiento sin soporte, TPM con la plantilla encendida…). | Lee el motivo y corrígelo; por ejemplo, usa «Copia independiente». |
| El número de máquina … se ocupó justo antes de clonar. Vuelve a intentarlo. | Otra persona usó ese número. | Vuelve a intentarlo. |
| La máquina «…» se clonó, pero no se pudo …. Puedes reintentar los ajustes o deshacer. | La copia existe, pero un ajuste (etiquetas, procesadores, memoria o disco) falló. | Reintenta los ajustes, o usa **Deshacer…**. |
| Se usará el CD de drivers «…», que no es la versión que conoce ProxLaunch. Comprueba que es de confianza antes de crear la máquina. | Aviso: el CD de drivers no es el virtio-win 0.1.302. No impide crear. | Comprueba el origen del ISO. |

---

## Privacidad y seguridad

### Qué se guarda y dónde

ProxLaunch guarda sus datos en la carpeta de configuración de tu usuario, que elige tu
sistema operativo. Para saber cuál es exactamente, ejecuta esto desde la carpeta del
repositorio:

```bash
.venv/bin/python -c "import platformdirs; print(platformdirs.user_config_dir('ProxLaunch')); print(platformdirs.user_log_dir('ProxLaunch'))"
```

(En Windows, cambia `.venv/bin/python` por `.venv\Scripts\python`.) La primera línea es la
carpeta de datos; la segunda, la del registro.

| Archivo | Qué contiene |
|---|---|
| `perfiles.json` | Tus perfiles de conexión: nombre, servidores, puerto, método, usuario, realm, si recuerdas credenciales y, desde el MVP 4, el **nombre** de los almacenamientos que pediste recordar (discos de las máquinas, ISOs y discos para importar). **Nunca** contiene token, contraseña ni tickets. |
| `huellas.json` | Las huellas de los servidores en los que confiaste, por servidor y puerto. |
| `preferencias.json` | Tema, modo (básico o avanzado) y versión forzada. |
| `perfiles_maquina.json` | Tus [perfiles de máquina](#perfiles-de-máquina): solo hardware, y los nombres de almacenamiento y red si lo dejaste marcado. Nunca nombres de máquina, números, nodos, servidores, usuarios ni secretos. |
| `proxlaunch.log` (carpeta de registro) | Registro de lo que hace la aplicación. Se rota solo (hasta 5 copias de 1 MB). |
| `informes/` (carpeta de datos del usuario) | Carpeta que **sugiere** ProxLaunch al guardar un informe de lote (puedes elegir otra) y donde deja el informe parcial (`parcial-<código>.txt`) si cierras con un lote en curso. No llevan host, IP, usuario ni secretos, pero sí nombres de máquinas y nodos. |
| `lotes/` (carpeta de datos del usuario) | Carpeta que **sugiere** ProxLaunch al guardar un [lote](#guardar-y-abrir-lotes) (puedes elegir otra). Se crea la primera vez que abres el diálogo de guardado. Los lotes llevan la configuración y los nombres de las máquinas y de almacenamientos, redes y nodos, pero **no** servidor, usuario ni secretos. |

En Linux y otros sistemas tipo Unix, el registro y todos los archivos que escribe ProxLaunch (perfiles,
lotes, CSV e informes) se crean con permisos solo para tu usuario (0600), y sus carpetas propias
(`lotes/`, `informes/`, la de configuración) también (0700). Si compartes un archivo guardado con
otra persona, ella tendrá que poder leerlo: cópialo con sus permisos.

**Archivos de otras personas.** Los perfiles, lotes y CSV que abres o importas se **leen y nunca
se modifican**. ProxLaunch comprueba su tamaño y su contenido antes de usarlos y no ejecuta nada
de lo que traen. Nada que parezca una credencial (`usuario@realm!token=...`) se guarda en un lote,
un perfil ni un CSV; si lo encuentra, te avisa **qué campo** lo tiene, sin mostrar el valor. Los
CSV que genera ProxLaunch neutralizan las fórmulas para que Excel no las ejecute.

### Tu token o contraseña

- **No se guardan** por defecto. «Recordar credenciales» viene **desmarcada**: al cerrar
  ProxLaunch, el secreto desaparece y se te pedirá de nuevo.
- Si marcas «Recordar credenciales», el secreto va al **llavero del sistema** (en Windows, el
  Administrador de credenciales; en Ubuntu, el servicio de secretos del escritorio), bajo el
  nombre `ProxLaunch`. Nunca va a un archivo.
- Si desmarcas la casilla en un perfil que tenía secreto guardado, se borra del llavero al
  guardar o conectar. Al eliminar un perfil, también se borra su secreto.
- La contraseña no se conserva en memoria tras iniciar sesión. ProxLaunch usa un «ticket»
  temporal de Proxmox (dura 2 horas y se renueva solo antes de vencer). Los tokens no se renuevan.
- El código de 2FA y las claves de recuperación **nunca** se guardan.

### Los registros no llevan secretos

El registro enmascara (`***`) tokens, contraseñas, tickets, cabeceras de autorización,
cookies y códigos de segundo factor. Sí registra datos técnicos como el UPID, el número de
máquina, el nodo y los errores de Proxmox, que puedes compartir con tu administrador.

### Conexión

- La comunicación es siempre cifrada (HTTPS) y se verifica la huella del servidor. Las
  credenciales **no se envían** antes de que resuelvas la huella.
- ProxLaunch se conecta de forma directa: ignora las variables de proxy del sistema y el
  archivo `.netrc`.
- ProxLaunch no usa el nombre ni el logo de Proxmox como identidad propia.

---

## Preguntas frecuentes

**¿ProxLaunch instala el sistema operativo en la máquina?**
No lo instala por ti: prepara la máquina y la deja detenida. Con el origen **Instalar desde un
archivo ISO**, la máquina queda con el ISO puesto (y, en Windows, con el CD de drivers virtio-win) y
tú terminas la instalación desde la consola de Proxmox. Con **Usar un disco existente** o **Copiar
una plantilla**, la máquina ya trae su sistema. Con **Vacía, sin sistema operativo**, el disco queda
vacío. La instalación desatendida, las OVA y la migración desde VMware no están soportadas. Ver
[Elegir el origen del sistema operativo](#elegir-el-origen-del-sistema-operativo).

**No veo las opciones ISO, disco existente o plantilla (están desactivadas).**
Cada una dice debajo por qué. Lo más habitual es que falte un permiso del rol (`VM.Config.Disk`,
`VM.Clone`, `Datastore.AllocateTemplate`, `Sys.AccessNetwork`), que el servidor no tenga un
almacenamiento con ese contenido (ISO o «Import»), que no haya plantillas, o que tu Proxmox sea
anterior a 8.4 (para importar discos). Abre **Ayuda > Qué puedo hacer en este servidor…** y usa
**Copiar texto para el administrador**.

**¿Por qué me pregunta qué almacenamiento usar, y por qué a veces no?**
Solo pregunta cuando hay **varios** almacenamientos candidatos para lo que necesitas, y lo hace al
elegir **Instalar desde un archivo ISO** o **Usar un disco existente**, o al subir o descargar un
archivo. No pregunta al conectar ni con un disco vacío. Lo que eliges se recuerda por servidor; lo
puedes cambiar en **Ajustes > Almacenamientos recordados…**.

**Subí un ISO por error, ¿cómo lo borro?**
ProxLaunch no puede borrar lo que sube, ni siquiera con un administrador. Pide al administrador que lo
borre desde Proxmox (en el almacenamiento, «ISO Images» o «Import»). **Archivo > Archivos subidos en
esta sesión…** te da la lista para enviársela.

**Pulsé «Cancelar subida» y tarda en parar.**
Es normal que no sea inmediato: puede tardar unos segundos al conectar y más si el servidor ya estaba
terminando de copiar el archivo. Si ya se envió todo, el botón pasa a **Dejar de esperar**: el
servidor termina la copia por su cuenta y el archivo puede aparecer después en el catálogo.

**¿Puedo clonar cualquier plantilla?**
Solo las que tu cuenta tenga permiso de clonar (`VM.Clone`). Con la asignación acotada de permisos,
ese permiso vale solo para las plantillas del pool del administrador. Las demás pueden verse en la
lista, pero aparecen desactivadas y ProxLaunch no las clonará. Ver
[Permisos para el administrador](#permisos-para-el-administrador-alcance-acotado).

**Borré una plantilla y mis máquinas dejaron de funcionar.**
Un clon «rápido y ligero» comparte el disco con la plantilla y depende de ella. En algunos
almacenamientos (por ejemplo `lvmthin`) Proxmox deja borrar la plantilla aunque tenga copias
enlazadas. Si necesitas máquinas independientes, elige **Copia independiente** (modo avanzado:
**Completo**).

**¿Cuántas copias se crean a la vez?**
Hasta 3 clones enlazados a la vez por nodo (se cuenta en el nodo de la plantilla). Las copias
completas y las importaciones se hacen de una en una por nodo.

**Una subida falló varias veces y el nodo se quedó sin espacio.**
Algunos rechazos de subida dejan archivos `/var/tmp/pveupload-*` en el nodo que ProxLaunch no puede
borrar. Avisa al administrador para que los borre. Ver
[Permisos para el administrador](#permisos-para-el-administrador-alcance-acotado), «Limpieza periódica».

**¿ProxLaunch enciende la máquina?**
No. Se crea detenida.

**¿Puedo crear varias máquinas a la vez?**
Sí, hasta 100 por lote. Ver [Crear varias máquinas de una vez (lotes)](#crear-varias-máquinas-de-una-vez-lotes).
En un lote normal todas comparten la configuración y solo cambian el nombre, el número y el
nodo. Si necesitas máquinas **distintas** en el mismo lote, usa un
[lote por filas](#lote-por-filas) (se crea [importando un CSV](#importar-máquinas-desde-un-csv)).
En ningún caso se edita una máquina suelta dentro del lote: corrige el archivo e impórtalo otra
vez, o quita esa fila.

**¿Puedo editar o borrar máquinas existentes?**
No, salvo una cosa: **Deshacer…** borra las máquinas que **creó el lote que acabas de
hacer** (y solo mientras ProxLaunch siga abierto). Editar o borrar cualquier otra máquina se
hace desde Proxmox. ProxLaunch tampoco gestiona contenedores (LXC) ni alta disponibilidad.

**¿Qué pasa si se corta la luz o se cierra ProxLaunch en mitad de un lote?**
Las tareas que ya se enviaron siguen en Proxmox y terminan solas. ProxLaunch no puede
retomar el lote ni deshacerlo después. Busca en Proxmox las máquinas por la etiqueta
`proxlaunch` (o `lote-<código>`) o por el rango de números. Si cerraste con el aviso normal,
guardó un informe parcial (ver [Cerrar ProxLaunch con un lote en curso](#cerrar-proxlaunch-con-un-lote-en-curso)).

**¿Puedo probar un lote sin crear nada?**
Sí: con **Simular**. Solo lee del servidor. Ver [Simulación](#simulación).

**¿Qué versiones de Proxmox funcionan?**
De la 8.0 a la 9.2. Una versión más nueva se admite con un aviso. Algunas funciones del origen del
sistema operativo piden una versión mínima: descargar un ISO desde una dirección web, 8.2; importar
un disco existente, 8.4.

**¿Qué diferencia hay entre un perfil de máquina y un lote guardado?**
Un perfil guarda **solo el hardware** de una máquina y se aplica al formulario; no guarda el
nombre, el número ni el nodo. Un lote guardado recuerda **todo el lote**: hardware, cantidad,
nombres, números y dónde crearlas. Los perfiles se gestionan en el menú **Perfiles**; los lotes, en
el menú **Lote**.

**Usé un perfil, ¿se cambió mi nombre o mi número de máquina?**
No. Un perfil nunca cambia el nombre, el VMID, el nodo ni el bloque **Lote**.

**Elegí un perfil y me dijo que el almacenamiento «x» no existe.**
Es normal si el perfil recordaba nombres de otro servidor (son solo pistas). ProxLaunch usó el
almacenamiento o la red predeterminados de este nodo y te lo dijo. Revisa que te sirvan, o cámbialos.

**¿Puedo modificar o borrar un perfil de fábrica?**
No. Duplícalo (**Perfiles > Administrar perfiles… > Duplicar…**, en modo avanzado) y modifica tu copia.

**Abrí un lote guardado y no me deja avanzar.**
Mira el panel **Este lote no encaja en este servidor**: nombra un almacenamiento, red o nodo que
este servidor no tiene. Elige otros con **Usar otro…** o, para un nodo, **Pasar a Automático**.
ProxLaunch nunca cambia esos valores solo.

**¿Por qué «Abrir lote…» está desactivado?**
Porque hace falta estar conectado: el lote se comprueba contra el servidor al abrirlo.
**Importar desde CSV…** sí te deja ver la vista previa sin conexión, pero no continuar.

**Mi CSV sale con letras raras o todo en una sola columna.**
En Excel, **Guardar como > CSV UTF-8**. En modo avanzado puedes elegir a mano la **Codificación** y el
**Separador** en la vista previa.

**Los números de fila no coinciden con mi lista.**
La numeración es la de Excel: el encabezado es la fila 1, así que tu primera máquina es la fila 2.

**¿Qué pasa con las filas de ejemplo de la plantilla?**
Se importan, pero con un aviso («Parece una fila de ejemplo de la plantilla.»). Cámbialas o
desmárcalas en la columna **Incluir** de la vista previa.

**Importé 10 filas y solo se crean 8.**
Hubo filas con error y elegiste **Importar solo las N filas correctas**, o las desmarcaste. El resumen
lo dice («Se van a crear 8 de las 10 filas del archivo.»). Usa **Revisar filas…** para volver a la
vista previa.

**¿ProxLaunch cambia mi CSV?**
No. Los archivos que abres se leen y nunca se modifican. Para corregir errores, usa **Descargar
filas con error…** y trabaja con ese archivo nuevo.

**Me avisó de «credencial» pero yo no puse ninguna.**
ProxLaunch ignora (sin leer) las columnas cuyo nombre contiene `token`, `password`, `contraseña`,
`secreto`, `ticket`, `csrf`, `apikey` o `credencial`, y rechaza al guardar textos con forma de
`usuario@realm!token=...`. Renombra la columna o cambia el texto.

**Cerré ProxLaunch y me preguntó si quería guardar, ¿por qué?**
Había un lote cargado, importado o editado sin guardar. Ver [Cambios sin guardar](#cambios-sin-guardar).

> **Pendiente de verificar:** en Windows, los mensajes «el archivo está abierto en otro programa»
> (por ejemplo, un CSV abierto en Excel) y «la ruta es demasiado larga» (más de 260 caracteres)
> no se han verificado todavía en un Windows real.

**¿Por qué no hay botón para saltarme el aviso de huella en modo básico?**
Por seguridad. Solo el modo avanzado permite reemplazar una huella, y siempre con
confirmación.

**Me equivoqué de modo, ¿pierdo lo que escribí?**
No. Cambiar entre básico y avanzado solo muestra u oculta campos; los valores se conservan.

**¿Hay más idiomas?**
Por ahora, solo español.

**¿Puedo usar ProxLaunch en macOS?**
No está previsto.

**¿Funciona con usuarios de LDAP o Active Directory?**
El campo **Realm** es editable y puedes escribir el realm de tu servidor, pero solo se han
previsto `pam` y `pve`.

> **Pendiente de verificar:** el uso con otros realms (LDAP, AD) no se ha probado.

**No puedo guardar mis credenciales.**
Revisa que tu sistema tenga un llavero (en Ubuntu, el servicio de secretos del escritorio).
Si no lo tiene, verás un aviso y tendrás que escribir el secreto cada vez.

**La ventana no abre en Ubuntu.**
Revisa el [README](../README.md): puede faltar alguna biblioteca del sistema.
