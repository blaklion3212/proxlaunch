# Guía de usuario de ProxLaunch (MVP 1)

ProxLaunch te ayuda a crear una máquina virtual en un servidor Proxmox sin tener que
conocer todos sus detalles. Esta guía te lleva paso a paso. No necesitas saber de
Proxmox: cada término se explica la primera vez que aparece.

Los nombres de botones, menús y mensajes de esta guía son los que ves en la aplicación.

> **Pendiente de verificar en laboratorio:** todavía no se ha probado ProxLaunch contra un
> Proxmox real. Los permisos mínimos y los textos exactos de algunos errores de Proxmox
> están marcados así, porque pueden variar un poco.

## Contenido

1. [Palabras que conviene conocer](#palabras-que-conviene-conocer)
2. [Antes de empezar](#antes-de-empezar)
3. [Primera conexión y la huella del servidor](#primera-conexión-y-la-huella-del-servidor)
4. [Crear una máquina en modo básico](#crear-una-máquina-en-modo-básico)
5. [Modo avanzado](#modo-avanzado)
6. [Entender el progreso y los resultados](#entender-el-progreso-y-los-resultados)
7. [Mensajes de error frecuentes](#mensajes-de-error-frecuentes)
8. [Privacidad y seguridad](#privacidad-y-seguridad)
9. [Preguntas frecuentes](#preguntas-frecuentes)

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
VM.Config.Disk
Datastore.Audit
Datastore.AllocateSpace
SDN.Use
Sys.Audit
```

> **Pendiente de verificar en laboratorio:** esta lista sale de la documentación de
> Proxmox y de la investigación del proyecto, pero aún no se ha comprobado que sea el
> mínimo exacto (por ejemplo, si `VM.Config.Disk` es imprescindible). Si Proxmox rechaza
> la creación por falta de un permiso, ProxLaunch te dirá cuál.

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

## Mensajes de error frecuentes

> **Pendiente de verificar en laboratorio:** los textos de la columna «Mensaje» son los
> que muestra ProxLaunch. Los mensajes originales de Proxmox, que ves en «Ver detalles
> técnicos», no se han comparado todavía con un servidor real y podrían diferir.

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
Todavía no. En esta versión se crea una por vez. Después de crear una, **Crear otra** te
prepara el formulario para la siguiente. Los lotes llegan en una versión futura.

**¿Puedo editar o borrar máquinas existentes?**
No. ProxLaunch solo crea. Tampoco gestiona contenedores (LXC) ni alta disponibilidad.

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

> **Pendiente de verificar en laboratorio:** el uso con otros realms (LDAP, AD) no se ha
> probado.

**No puedo guardar mis credenciales.**
Revisa que tu sistema tenga un llavero (en Ubuntu, el servicio de secretos del escritorio).
Si no lo tiene, verás un aviso y tendrás que escribir el secreto cada vez.

**La ventana no abre en Ubuntu.**
Revisa el [README](../README.md): puede faltar alguna biblioteca del sistema.
