# Guía de usuario de ProxLaunch (MVP 1 y MVP 2)

ProxLaunch te ayuda a crear una o varias máquinas virtuales en un servidor Proxmox sin
tener que conocer todos sus detalles. Esta guía te lleva paso a paso. No necesitas saber
de Proxmox: cada término se explica la primera vez que aparece.

Los nombres de botones, menús y mensajes de esta guía son los que ves en la aplicación.

> ProxLaunch se probó contra un Proxmox VE 9.2 real (servidor individual). Los clústeres
> de varios nodos y Proxmox 8.x se han probado solo con respuestas simuladas. Eso incluye
> el reparto de un lote entre varios nodos.

## Contenido

1. [Palabras que conviene conocer](#palabras-que-conviene-conocer)
2. [Antes de empezar](#antes-de-empezar)
3. [Primera conexión y la huella del servidor](#primera-conexión-y-la-huella-del-servidor)
4. [Crear una máquina en modo básico](#crear-una-máquina-en-modo-básico)
5. [Modo avanzado](#modo-avanzado)
6. [Entender el progreso y los resultados](#entender-el-progreso-y-los-resultados)
7. [Crear varias máquinas de una vez (lotes)](#crear-varias-máquinas-de-una-vez-lotes)
8. [Mensajes de error frecuentes](#mensajes-de-error-frecuentes)
9. [Privacidad y seguridad](#privacidad-y-seguridad)
10. [Preguntas frecuentes](#preguntas-frecuentes)

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
| **Lote** | Un grupo de máquinas iguales que se crean de una vez. Solo cambian el nombre, el número y, si hay clúster, el nodo. |
| **Etiqueta** | Una marca de texto que Proxmox muestra junto a la máquina. ProxLaunch usa dos para reconocer lo que creó. |

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
```

Esta lista se comprobó en un Proxmox real: son los 10 privilegios mínimos. **Crear lotes,
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
   **Propagar**.
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
- El disco se crea **vacío**: ProxLaunch **no instala ningún sistema operativo**. Eso lo
  haces tú después, desde Proxmox.

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
ProxLaunch, las máquinas se crean **detenidas** y con el disco **vacío**.

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
| `perfiles.json` | Tus perfiles: nombre, servidores, puerto, método, usuario, realm y si recuerdas credenciales. **Nunca** contiene token, contraseña ni tickets. |
| `huellas.json` | Las huellas de los servidores en los que confiaste, por servidor y puerto. |
| `preferencias.json` | Tema, modo (básico o avanzado) y versión forzada. |
| `proxlaunch.log` (carpeta de registro) | Registro de lo que hace la aplicación. Se rota solo (hasta 5 copias de 1 MB). |
| `informes/` (carpeta de datos del usuario) | Carpeta que **sugiere** ProxLaunch al guardar un informe de lote (puedes elegir otra) y donde deja el informe parcial (`parcial-<código>.txt`) si cierras con un lote en curso. No llevan host, IP, usuario ni secretos, pero sí nombres de máquinas y nodos. |

En Linux y otros sistemas tipo Unix, el registro se crea con permisos solo para tu usuario.

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
No. En esta versión el disco se crea vacío. Instalar un sistema (por ISO, OVA o migración
desde VMware) se tratará en una versión futura. Mientras tanto, hazlo desde Proxmox.

**¿ProxLaunch enciende la máquina?**
No. Se crea detenida.

**¿Puedo crear varias máquinas a la vez?**
Sí, hasta 100 por lote. Ver [Crear varias máquinas de una vez (lotes)](#crear-varias-máquinas-de-una-vez-lotes).
Todas comparten la configuración y solo cambian el nombre, el número y el nodo. No se puede
editar una máquina suelta dentro del lote: si necesitas otra configuración, haz otro lote.

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
De la 8.0 a la 9.2. Una versión más nueva se admite con un aviso.

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
