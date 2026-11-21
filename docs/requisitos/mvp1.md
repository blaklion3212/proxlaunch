# Requisitos del MVP 1 — ProxLaunch

Versión del documento: 1.0 (2026-11-11) · Estado: borrador para revisión del orquestador

Fuentes, en orden de autoridad: `docs/decisiones.md` (D-01 a D-15 y "Correcciones
técnicas", abreviadas **CT-n**) y `prompt.md` (retirado del repositorio el 2026-11-21; queda en el historial, commit `ab133c0`) (abreviado **P§n**, sección n). Si se
contradicen, manda `decisiones.md`.

Convenciones:
- **Prioridad:** Debe (sin esto el MVP no se entrega) / Debería (importante, se puede
  diferir con justificación) / Podría (deseable).
- **IDs:** RF-xx (funcional), RNF-xx (no funcional), CA-xx.y (criterio y del requisito xx),
  V-xx (regla de validación), P-xx (pregunta abierta).
- Los criterios usan "Dado / Cuando / Entonces". "Mock" = respuesta simulada de la API
  basada en respuestas reales (D-15). "Laboratorio" = Proxmox VE 9.2 anidado (D-15).
- Unidades: los discos se expresan en **GiB**, la RAM en **MiB** en la API (CT-6). La
  interfaz puede mostrar GB/GiB pero debe aclarar la unidad y enviar el valor correcto.

---

## 1. Alcance

### 1.1 Dentro del MVP 1 (D-12)
1. Conexión: API Token; usuario/contraseña con ticket y renovación; 2FA (TOTP y claves
   de recuperación); huella SSL; perfiles con varias IPs; llavero opcional.
2. Detección de versión de Proxmox VE y de topología (nodo suelto o clúster).
3. Descubrimiento: nodos, storages con contenido `images` y su espacio, bridges,
   próximo VMID.
4. Crear **una** MV con disco(s) vacío(s): datos generales, firmware SeaBIOS/OVMF (con
   `efidisk0` automático), cómputo, discos, red.
5. Seguimiento de la tarea (UPID) con progreso por etapas y errores claros.
6. Base de interfaz: temas claro/oscuro automáticos con selector, textos traducibles,
   modo básico/avanzado, ayuda en lenguaje llano.

### 1.2 Fuera del MVP 1
- Lotes, validación de espacio de lote, reparto del lote entre nodos, rollback, modo
  simulación (MVP 2).
- Perfiles predefinidos de MV, guardar/cargar lotes, CSV (MVP 3).
- Origen del SO distinto de "disco vacío": ISO, OVA, VMware (MVP 4). El modelo de datos
  sí incluye el campo (RF-18).
- Instaladores, CI, firma de código (MVP 5).
- LXC, HA, monitoreo, editar o borrar MVs existentes, iniciar la MV tras crearla.
- WebAuthn y Yubico OTP (D-11); macOS (D-06); interfaz en otros idiomas (D-04).

### 1.3 Supuestos
- S-1: la MV se crea **detenida** y no se inicia (no está pedido).
- S-2: el núcleo (modelos, cliente API, validaciones) no depende de Qt (D-05); los
  criterios de este documento se verifican contra el núcleo con mocks siempre que sea
  posible.
- S-3: los datos de perfiles y preferencias se guardan en la carpeta de usuario que da
  `platformdirs` (D-06), en un archivo sin secretos.
- S-4: una versión de Proxmox mayor que la última conocida se trata con las
  capacidades de la última conocida y se muestra un aviso informativo.
- S-5: la contraseña no se conserva en memoria tras iniciar sesión; si el ticket expira
  sin haberse renovado, se vuelve a pedir (ver P-13).
- S-6: el campo "Realm" es editable con `pam` y `pve` como sugerencias (P-11).
- S-7: la huella SSL se guarda por combinación host:puerto, porque cada nodo de un
  clúster puede tener su propio certificado (P-12).

### 1.4 Casos límite generales
- Nombre de perfil duplicado; host con espacios o con esquema (`https://`) pegado.
- Reloj del equipo desfasado (afecta a la expiración del ticket y al TOTP).
- Pérdida de red a mitad de una tarea: el polling reintenta y no declara éxito ni fallo
  sin evidencia.
- Cierre de la app con una tarea en curso: se advierte; la tarea sigue en Proxmox.
- Pantalla de alta resolución en Windows (escalado 125–200 %).

---

## 2. Requisitos funcionales

### A. Conexión y sesión

#### RF-01 Conexión con API Token — Debe — D-09, P§3
El usuario introduce host/IP, puerto (8006 por defecto) y un token en formato
`USER@REALM!TOKENID=SECRETO`. "Probar y conectar" llama a `/api2/json/version`.
- CA-01.1 Dado un mock que acepta el token `ana@pve!lab=11111111-2222-3333-4444-555555555555`,
  cuando se pulsa "Probar y conectar", entonces la app envía la cabecera
  `Authorization: PVEAPIToken=ana@pve!lab=<secreto>` a `/api2/json/version`, muestra
  "Conectado" y la versión en la barra superior.
- CA-01.2 Dado el texto `ana@pve!lab` (sin `=SECRETO`) o `ana@pve=abc` (sin `!`), cuando se
  intenta conectar, entonces se muestra un error de formato en el campo y no se realiza
  ninguna petición de red.
- CA-01.3 Dado un mock que responde 401, cuando se conecta, entonces se muestra
  "Las credenciales no son válidas. Revisa el usuario, el token o la contraseña." y la
  sesión queda sin conectar.
- CA-01.4 Dado un token válido, cuando se cierra la sesión y se vuelve a conectar, entonces
  no se usa ningún ticket ni se pide 2FA (los tokens no pasan por 2FA).
- CA-01.5 Dado host sin respuesta (mock con timeout), cuando se conecta, entonces tras el
  tiempo de espera de conexión (RNF-03) se muestra "No se pudo contactar con el servidor
  (host:puerto)" y el botón se rehabilita.

#### RF-02 Conexión con usuario y contraseña (ticket) — Debe — D-09, P§3
Campos: host/IP, puerto, realm, usuario, contraseña. Se obtiene el ticket con
`POST /api2/json/access/ticket`; las peticiones de lectura usan la cookie `PVEAuthCookie` y
las de escritura añaden `CSRFPreventionToken`.
- CA-02.1 Dado un mock con usuario `root`, realm `pam` y contraseña correcta, cuando se
  conecta, entonces se guarda en memoria el ticket y el CSRF, se llama a `/version` con la
  cookie y se muestra "Conectado".
- CA-02.2 Dado una contraseña incorrecta (mock 401), cuando se conecta, entonces se muestra
  el mensaje de credenciales inválidas (CA-01.3), no se revela si falló usuario o
  contraseña, y el campo contraseña se limpia.
- CA-02.3 Dado una petición `POST` posterior (por ejemplo, crear MV), entonces incluye la
  cabecera `CSRFPreventionToken`; una petición `GET` no la requiere.
- CA-02.4 Dado el usuario escrito como `root@pam` en el campo usuario y realm `pam`, entonces
  la app lo normaliza a un solo `root@pam` (no `root@pam@pam`).

#### RF-03 Renovación del ticket — Debe — D-09, P§3
El ticket vive 2 horas. La app lo renueva antes de que expire, sin que el usuario lo note.
- CA-03.1 Dado un ticket emitido hace 105 minutos (reloj simulado) cuando se hace cualquier
  petición, entonces antes de enviarla la app renueva el ticket (margen: quedan ≤ 15 min,
  supuesto) y la petición usa el ticket nuevo.
- CA-03.2 Dado que una tarea de creación está en seguimiento y el ticket entra en el margen
  de renovación, entonces el seguimiento continúa sin error y sin reiniciar la tarea.
- CA-03.3 Dado un ticket ya expirado (mock responde 401 a la petición, por ejemplo tras
  suspender el equipo), cuando falla la renovación, entonces se muestra "Tu sesión expiró.
  Vuelve a iniciar sesión" y se abre el diálogo de conexión **sin perder** los datos que el
  usuario había llenado en el formulario de MV.
- CA-03.4 Dado conexión por API Token, entonces nunca se intenta renovar nada.

#### RF-04 Segundo factor (TOTP y claves de recuperación) — Debe — D-11
La pantalla de 2FA solo aparece si el servidor lo exige tras validar usuario y contraseña.
- CA-04.1 Dado un mock de usuario sin 2FA, cuando se conecta, entonces no aparece la pantalla
  de 2FA.
- CA-04.2 Dado un mock que exige TOTP, cuando se envían usuario y contraseña correctos,
  entonces aparece la pantalla "Código de verificación" con un campo de 6 dígitos y la opción
  "Usar una clave de recuperación".
- CA-04.3 Dado el código `123456` aceptado por el mock, cuando se envía, entonces la sesión
  queda conectada; dado un código rechazado, entonces se muestra "El código no es correcto o
  ya venció. Espera al siguiente código e inténtalo de nuevo." y se permite reintentar sin
  reescribir usuario y contraseña.
- CA-04.4 Dado el modo clave de recuperación, cuando se envía una clave aceptada por el mock,
  entonces conecta y se avisa "Esa clave de recuperación ya no se puede volver a usar".
- CA-04.5 Dado un mock cuyo desafío ofrece **solo** WebAuthn y/o Yubico OTP, cuando se
  conecta, entonces no se pide código y se muestra "Este usuario exige un método de segundo
  factor que ProxLaunch no admite. Usa un API Token." con enlace a la guía de token (RF-25).
- CA-04.6 Dado un desafío que ofrece TOTP y WebAuthn, entonces se ofrece TOTP.
- CA-04.7 Ni el código TOTP ni las claves de recuperación se guardan en disco, llavero o log.

#### RF-05 Verificación de huella SSL — Debe — D-10
Se usa la huella SHA-256 del certificado presentado.
- CA-05.1 Dado un host sin huella guardada, cuando se conecta por primera vez, entonces se
  muestra un diálogo con host, puerto y huella SHA-256 en formato `AA:BB:...`, con botones
  "Confiar y continuar" y "Cancelar", y no se envía ninguna credencial antes de la decisión.
- CA-05.2 Dado "Confiar y continuar", entonces la huella se guarda asociada al host:puerto y
  la siguiente conexión no pregunta.
- CA-05.3 Dado "Cancelar", entonces no se conecta y no se guarda nada.
- CA-05.4 Dado una huella guardada y un servidor que ahora presenta otra, cuando se conecta,
  entonces se **bloquea** la conexión, no se envía ninguna credencial y se muestra
  "El certificado del servidor cambió. Podría ser un cambio legítimo (renovación) o un
  intento de suplantación. Verifica con tu administrador." mostrando huella guardada y
  nueva.
- CA-05.5 Dado el bloqueo anterior, entonces en modo básico no hay forma de continuar; en
  modo avanzado solo se permite continuar mediante una acción explícita de "Reemplazar la
  huella guardada" con confirmación (ver P-12).

#### RF-06 Ignorar verificación SSL (solo modo avanzado) — Debe — D-10, P§3
- CA-06.1 Dado el modo básico, entonces la opción "Ignorar verificación SSL" no está visible
  ni activable.
- CA-06.2 Dado el modo avanzado y la opción activada, cuando se conecta, entonces se acepta
  cualquier certificado, no se pide ni se guarda huella, y la barra superior muestra un
  indicador permanente "Conexión sin verificar".
- CA-06.3 Dado que se cambia de avanzado a básico con un perfil que tenía la opción activa,
  entonces ese perfil vuelve a verificar por huella (CA-05.1).

#### RF-07 Perfiles de conexión con varias IPs — Debe — D-09
Un perfil guarda nombre, lista ordenada de hosts/IPs, puerto (8006), usuario, realm,
método (token o contraseña) y huellas. **Nunca** contiene secretos (ver RF-08).
- CA-07.1 Dado un perfil nuevo con 2 IPs, cuando se guarda y se reinicia la app, entonces el
  perfil reaparece con ambas IPs en el mismo orden y sin ningún secreto en el archivo.
- CA-07.2 Dado un perfil con IPs A (caída) y B (viva), cuando se conecta, entonces tras el
  fallo de A por red (timeout o conexión rechazada) se intenta B automáticamente y se informa
  "Conectado a B (A no respondió)".
- CA-07.3 Dado que A responde 401, entonces **no** se prueba B (error de credenciales es
  definitivo) y se muestra el error de credenciales.
- CA-07.4 Dado que todas las IPs fallan, entonces se muestra una lista con el motivo por IP.
- CA-07.5 Dado una sesión activa conectada a A que deja de responder en la siguiente
  petición, cuando el perfil tiene B, entonces la petición se reintenta contra B (con el
  mismo ticket, que vale en todo el clúster, o el mismo token) y la sesión continúa.
- CA-07.6 Dado un perfil con una sola IP caída (nodo suelto caído), entonces se muestra
  "El servidor no responde" y no se pierde el formulario.
- CA-07.7 Se pueden editar, duplicar y eliminar perfiles; eliminar un perfil también elimina
  su secreto del llavero y sus huellas.
- CA-07.8 Dado el host escrito como `https://10.0.0.5:8006/`, entonces se normaliza a
  `10.0.0.5` y puerto `8006` o se rechaza con mensaje claro.

#### RF-08 Recordar credenciales en el llavero — Debe — D-09
- CA-08.1 Dado un perfil nuevo, entonces la casilla "Recordar credenciales" está **desmarcada**.
- CA-08.2 Dado la casilla desmarcada, cuando se conecta y se cierra la app, entonces ningún
  secreto queda en disco ni en el llavero y al volver a abrir se pide de nuevo.
- CA-08.3 Dado la casilla marcada y un llavero disponible (mock de `keyring`), cuando se
  conecta con éxito, entonces el secreto (token completo o contraseña) se guarda en el
  llavero bajo un nombre de servicio de ProxLaunch y el perfil lo reutiliza al reabrir.
- CA-08.4 Dado la casilla marcada y **sin** llavero (backend `keyring` nulo o fallo), entonces
  se avisa "No hay un llavero disponible en este equipo; las credenciales no se guardarán",
  no se guarda nada en ningún archivo y la conexión continúa.
- CA-08.5 Dado cualquier flujo, entonces buscar el secreto, la contraseña, el ticket o el CSRF
  en el archivo de perfiles, en los logs y en la salida estándar no produce coincidencias
  (prueba con un secreto centinela único).
- CA-08.6 Dado que se desmarca la casilla en un perfil que ya tenía secreto guardado, entonces
  el secreto se borra del llavero.

#### RF-09 Detección de versión y capacidades — Debe — D-07
- CA-09.1 Dado un mock de `/version` con `version: "8.2.4"`, entonces la barra superior muestra
  "Proxmox VE 8.2.4".
- CA-09.2 Dado `version: "7.4-17"`, entonces se bloquea con "ProxLaunch requiere Proxmox VE 8.0
  o superior (el servidor tiene 7.4)" y no se ofrece crear MVs.
- CA-09.3 Dado una versión mayor que la última conocida (p. ej. `10.0`), entonces se permite con
  aviso informativo (S-4).
- CA-09.4 Dado una tabla de capacidades con una función marcada "desde 8.2" y un servidor 8.0,
  entonces esa función aparece oculta o deshabilitada con el texto "Requiere Proxmox 8.2 o
  superior".
- CA-09.5 Dado `/version` con un formato inesperado, entonces se conecta con la capacidad mínima
  (8.0) y se registra una advertencia en el log, sin fallar.
- CA-09.6 La tabla de capacidades es un único lugar consultable (no condicionales de versión
  dispersos); un test unitario la recorre para versiones 8.0, 8.1, 8.4, 9.0 y 9.2.

#### RF-10 Detección de nodo suelto o clúster — Debe — D-08
- CA-10.1 Dado un mock de `/cluster/status` con una entrada `type: "cluster"` y 3 nodos,
  entonces la app muestra "Clúster «nombre» — 3 nodos".
- CA-10.2 Dado un mock sin entrada `cluster` (solo un `type: "node"`), entonces la app muestra
  "Servidor individual" y no muestra el selector de nodo con opción Automático.
- CA-10.3 Dado un nodo con `online: 0`, entonces aparece en la lista deshabilitado y con la
  etiqueta "Sin conexión", y no puede elegirse.

#### RF-11 Descubrimiento de recursos — Debe — D-08, P§4
Tras conectar, en segundo plano (RNF-01), se consultan nodos, storages, bridges y próximo VMID.
- CA-11.1 Dado un mock con nodos `pve1`, `pve2`, cuando termina el descubrimiento, entonces la
  lista de nodos tiene ambos con su estado.
- CA-11.2 Dado un mock de storages del nodo con `local` (content `iso,backup`), `local-lvm`
  (content `images,rootdir`, tipo `lvmthin`, avail 150 GiB) y `nfs1` (content `images`,
  `shared=1`, avail 500 GiB), entonces el selector de storages de disco ofrece solo `local-lvm`
  y `nfs1`, mostrando "local-lvm (lvmthin, 150 GiB libres)" y "nfs1 (nfs, 500 GiB libres)".
- CA-11.3 Un storage con `enabled: 0` o `active: 0` aparece deshabilitado con motivo "Inactivo".
- CA-11.4 Dado `avail` en bytes, la conversión a GiB se redondea hacia abajo a 1 decimal y es
  coherente con lo que valida V-14.
- CA-11.5 Dado mock de red con `vmbr0` (bridge), `vmbr1` (bridge), `eno1` (eth), entonces solo
  los bridges (incluyendo `OVSBridge`) aparecen en el selector de red; `eno1` no.
- CA-11.6 Dado `/cluster/nextid` devolviendo `"101"`, entonces el VMID prellenado es 101.
- CA-11.7 Dado que se cambia el nodo destino, entonces storages y bridges se recargan **para ese
  nodo** y cualquier selección previa que no exista en el nuevo nodo se vacía con un aviso
  (D-08: validación en el nodo destino).
- CA-11.8 Dado que falla el descubrimiento de un nodo (mock 595 "no route to host"), entonces
  ese nodo se marca "Sin conexión", el resto sigue utilizable y hay un botón "Reintentar".
- CA-11.9 Dado ningún storage con `images` en el nodo, entonces se muestra "Este servidor no
  tiene almacenamiento para discos de máquinas virtuales" y se permite crear MV solo si
  la opción "sin disco" está marcada (RF-16) y el firmware es SeaBIOS.
- CA-11.10 Existe un botón "Actualizar" que repite el descubrimiento.

#### RF-12 Verificación de permisos tras conectar — Debería — D-09 (recomendación de mínimos)
Consulta `/access/permissions` y avisa de privilegios que faltan según la sección 5.
- CA-12.1 Dado un mock de permisos sin `VM.Allocate` en `/vms`, entonces tras conectar se
  muestra un aviso no bloqueante "Con este usuario no podrás crear máquinas: falta el permiso
  VM.Allocate" (sección 5, por verificar) y el botón Crear queda deshabilitado con ese motivo.
- CA-12.2 Dado permisos completos, no aparece aviso.
- CA-12.3 Si la consulta de permisos falla, la conexión no falla; solo se omite la verificación.

### B. Creación de una MV

#### RF-13 Datos generales y nodo destino — Debe — D-08, P§5
Campos: VMID, nombre, nodo destino.
- CA-13.1 Dado el descubrimiento completo, entonces el VMID aparece prellenado con el valor de
  `/cluster/nextid` y se puede cambiar (override).
- CA-13.2 Dado un VMID escrito a mano, cuando se valida, entonces se comprueba con
  `/cluster/nextid?vmid=<n>`; si Proxmox responde que existe, se marca el campo con "El número
  <n> ya lo usa otra máquina. Prueba con <siguiente libre>".
- CA-13.3 Dado que el VMID estaba libre al validar pero la creación responde "already exists"
  (carrera), entonces se muestra el mismo mensaje del CA-13.2, el formulario conserva todos
  los datos y se sugiere el nuevo próximo VMID.
- CA-13.4 Dado un nombre inválido, entonces V-01 impide continuar con mensaje junto al campo.
- CA-13.5 Dado un clúster, entonces el nodo destino ofrece **Automático** (predeterminado) y
  **Manual**; en Automático se muestra qué nodo se eligió y por qué ("más memoria y espacio
  libres", ver P-07); "Repartir el lote" no aparece (MVP 2).
- CA-13.6 Dado un servidor individual, el nodo se asigna sin mostrar selector.
- CA-13.7 Dado que el nodo elegido cae antes de enviar, entonces la creación falla con
  "El nodo <n> no está disponible" sin crear nada, y se ofrece volver a elegir.

#### RF-14 Firmware SeaBIOS / OVMF — Debe — D-12, CT-7, P§5
- CA-14.1 Dado SeaBIOS (predeterminado), entonces la petición contiene `bios=seabios` (o lo
  omite) y no contiene `efidisk0`.
- CA-14.2 Dado OVMF (UEFI), entonces la petición contiene `bios=ovmf`, `machine=q35` y
  `efidisk0=<storage>:1,efitype=4m,...`, con storage por defecto igual al del primer disco, o,
  si no hay disco, el primer storage con `images` del nodo.
- CA-14.3 Dado OVMF, entonces el usuario puede cambiar el storage de `efidisk0` solo en modo
  avanzado y el formato del efidisk sigue V-09.
- CA-14.4 Dado OVMF y ningún storage con `images`, entonces se bloquea con "UEFI necesita un
  almacenamiento para guardar su configuración".
- CA-14.5 Dado que se vuelve de OVMF a SeaBIOS, entonces `efidisk0` y `machine=q35` dejan de
  incluirse.
- CA-14.6 Windows 11 / TPM (`tpmstate0`) no se genera en el MVP 1 (ver P-04).

#### RF-15 Cómputo — Debe — P§5, D-14
Sockets, cores, tipo de CPU, memoria, ballooning.
- CA-15.1 Dado el formulario recién abierto, entonces sockets=1, tipo de CPU `x86-64-v2-AES` (D-14) y
  los demás valores por defecto de la sección 4.
- CA-15.2 Dado sockets=2 y cores=4, entonces la interfaz muestra "8 procesadores virtuales en
  total" y la petición lleva `sockets=2` y `cores=4` (cores es por socket).
- CA-15.3 Dado cores=0 o sockets=5, entonces V-05 bloquea con mensaje.
- CA-15.4 Dado memoria 4 GiB en la interfaz, entonces la petición lleva `memory=4096` (MiB).
- CA-15.5 Dado el modo avanzado y ballooning activado con mínimo 1024 MiB y memoria 4096, entonces
  la petición lleva `balloon=1024`; con ballooning desactivado lleva `balloon=0`; en modo
  básico no se envía `balloon` (se deja el comportamiento por defecto de Proxmox).
- CA-15.6 Dado un mínimo de ballooning mayor que la memoria, entonces V-06 bloquea.
- CA-15.7 Dado que el tipo de CPU se cambia a `host` en modo avanzado, entonces se muestra la
  ayuda "Rinde más pero impide mover la máquina entre nodos con procesadores distintos".

#### RF-16 Discos vacíos — Debe — D-12, CT-1, CT-3, CT-4, P§5
Tabla de 1 o más discos; cada uno con storage, bus, tamaño, formato, discard, ssd, iothread.
- CA-16.1 Dado el formulario por defecto, entonces hay un disco: `scsi0`, 32 GiB, storage
  predeterminado según la sección 4, y la petición contiene
  `scsihw=virtio-scsi-single` y `scsi0=<storage>:32,discard=on,ssd=1,iothread=1`
  (más `format=` solo si V-09 lo exige).
- CA-16.2 Dado que se agregan dos discos al bus scsi y uno al virtio, entonces los índices se
  asignan consecutivos por bus (`scsi0`, `scsi1`, `virtio0`).
- CA-16.3 Dado que se marca "Sin disco", entonces la tabla se oculta, la petición no contiene
  ningún `scsiN/virtioN/sataN/ideN` y no contiene `scsihw`.
- CA-16.4 Cada disco aplica las reglas V-07 a V-13; ante una combinación inválida
  (por ejemplo `virtio` + `ssd`) la interfaz **deshabilita** o desmarca la opción y explica el
  motivo, en lugar de dejar que Proxmox la rechace.
- CA-16.5 Dado el cambio de storage de un disco de LVM-thin a un storage de directorio, entonces
  el formato pasa de "(automático, raw)" a elegible raw/qcow2 (V-09).
- CA-16.6 Dado el tamaño 0, -5, 1.5 o "abc", entonces V-08 bloquea.
- CA-16.7 Dado más de un disco en el mismo storage, entonces la validación de espacio (V-14)
  suma los tamaños de ese storage.
- CA-16.8 La interfaz no permite elegir `subvol` en ningún caso (CT-1).
- CA-16.9 Dado el origen "Disco vacío", los discos se crean sin contenido; no se solicita ISO.

#### RF-17 Interfaces de red — Debe — P§5, CT-9
- CA-17.1 Dado el formulario recién abierto, hay una interfaz VirtIO conectada a `vmbr0` si
  existe en el nodo; si no existe, al primer bridge del nodo; si no hay bridges, se bloquea
  con "El nodo no tiene redes (bridges) disponibles".
- CA-17.2 Dado la interfaz por defecto, la petición contiene `net0=virtio,bridge=vmbr0`
  **codificado correctamente en el cuerpo del formulario** (la coma y el signo `=` del valor
  van en porcentaje: `net0=virtio%2Cbridge%3Dvmbr0`) y el laboratorio no responde
  "format error".
- CA-17.3 Dado una segunda interfaz en `vmbr1` con VLAN 120, entonces la petición contiene
  `net1=virtio,bridge=vmbr1,tag=120`.
- CA-17.4 Dado VLAN 0, 4095 o "abc", entonces V-15 bloquea; VLAN vacío significa sin etiqueta.
- CA-17.5 Dado que un bridge elegido no existe en el nodo destino, entonces V-16 bloquea.
- CA-17.6 El modelo de la tarjeta es `virtio` salvo cambio en modo avanzado (opciones: `virtio`,
  `e1000`, `rtl8139`; P-02 decide si se ofrecen).
- CA-17.7 La MAC no se envía (la asigna Proxmox).

#### RF-18 Modelo de datos y campo "origen" — Debe — D-13, D-05
- CA-18.1 El modelo de la MV (núcleo, sin Qt) contiene los campos: VMID, nombre, nodo, firmware,
  sockets, cores, tipo de CPU, memoria, ballooning, lista de discos, lista de interfaces, y
  **origen**. El campo origen solo admite el valor `disco_vacio` (etiqueta "Disco vacío").
- CA-18.2 Dado cualquier otro valor de origen al construir el modelo, entonces el núcleo lanza un
  error de validación.
- CA-18.3 Dado que el modelo se serializa a diccionario/JSON, el origen aparece explícito y se
  puede reconstruir idéntico (ida y vuelta).
- CA-18.4 El modelo no depende de PySide6: importarlo sin PySide6 instalado funciona.

#### RF-19 Resumen y envío — Debe — P§6, D-12
- CA-19.1 Antes de enviar, un resumen en lenguaje llano muestra: nombre, VMID, nodo, firmware,
  procesadores, memoria, discos (storage, tamaño), redes. Incluye el botón "Crear máquina".
- CA-19.2 Dado un formulario con errores de validación, el botón "Crear máquina" está
  deshabilitado y cada error visible junto a su campo.
- CA-19.3 Dado el formulario del ejemplo siguiente, la petición es `POST
  /api2/json/nodes/pve1/qemu` con cuerpo `application/x-www-form-urlencoded` equivalente a:
  `vmid=100, name=srv-web-01, bios=ovmf, machine=q35, efidisk0=local-lvm:1,efitype=4m,pre-enrolled-keys=1,
  sockets=1, cores=2, cpu=x86-64-v2-AES, memory=2048, scsihw=virtio-scsi-single,
  scsi0=local-lvm:32,discard=on,ssd=1,iothread=1, net0=virtio,bridge=vmbr0`.
  (Valores exactos de efidisk0 por confirmar en laboratorio.)
- CA-19.4 Al enviar, la interfaz queda sin congelarse (RNF-01) y los campos se bloquean hasta
  terminar la tarea.
- CA-19.5 Dado una respuesta sin UPID válido (`UPID:<nodo>:...`), entonces se muestra error
  "Proxmox no devolvió el identificador de la tarea" y no se hace polling.
- CA-19.6 No se envía un segundo `POST` si el usuario pulsa dos veces "Crear máquina" (doble clic).

#### RF-20 Seguimiento de la tarea (UPID) con progreso por etapas — Debe — CT-2, P§6
- CA-20.1 Dado un UPID, la app consulta `/nodes/{nodo}/tasks/{upid}/status` a intervalos de 1–2
  s (configurable internamente) hasta `status: "stopped"`.
- CA-20.2 La barra de progreso muestra etapas, no un porcentaje falso. Etapas: "Validando
  datos" → "Enviando a Proxmox" → "Creando la máquina" → "Comprobando el resultado" →
  "Listo". La barra es naranja `#E57000` (D-02); cada etapa tiene texto.
- CA-20.3 Dado `exitstatus: "OK"`, entonces se confirma con una consulta a
  `/nodes/{nodo}/qemu/{vmid}/config` que la MV existe y se muestra "Máquina <nombre> (VMID)
  creada en <nodo>" con botón "Crear otra".
- CA-20.4 Dado `exitstatus` con texto de error (p. ej. `unable to create VM 100 - ...`),
  entonces se muestra un mensaje traducido (RF-21) y el texto original disponible en
  "Ver detalles técnicos".
- CA-20.5 Dado `exitstatus: "WARNINGS: 1"`, entonces se informa "Creada con avisos" y se
  muestra el log de la tarea (`/tasks/{upid}/log`).
- CA-20.6 Dado que la tarea no termina en el tiempo máximo (por defecto 10 min, P-05), entonces
  se detiene el polling y se muestra "La tarea sigue en marcha en Proxmox, no sabemos si
  terminó", con "Seguir esperando" y "Comprobar ahora"; **no** se borra ni se reintenta la
  creación sola.
- CA-20.7 Dado una pérdida de red durante el polling (mock falla 3 veces y luego responde),
  entonces el polling se recupera sin mostrar error; si falla sostenidamente más de 60 s se
  muestra "Se perdió la conexión mientras se creaba la máquina; la tarea puede haber
  terminado" y "Comprobar ahora".
- CA-20.8 Dado el cierre de la ventana con tarea en curso, se pide confirmación con aviso de
  que la tarea sigue en el servidor.
- CA-20.9 El UPID se muestra en fuente monoespaciada y es copiable.
- CA-20.10 En fallo, la app **no** borra nada (el rollback es MVP 2) y, si la MV existe a medias
  (config presente), lo informa: "La máquina quedó parcialmente creada; elimínala desde
  Proxmox".

#### RF-21 Errores claros en español — Debe — D-04, P§6
Los errores de red, HTTP y de Proxmox se traducen a mensajes comprensibles con acción
sugerida. El texto original se conserva en "detalles técnicos" y en el log (sin secretos).
- CA-21.1 Cada caso de la tabla de la sección 7 produce el mensaje indicado (un test
  parametrizado con un mock por caso).
- CA-21.2 Dado un error no reconocido, entonces se muestra "Proxmox respondió con un error que
  no conocemos" más el texto original en detalles técnicos.
- CA-21.3 Ningún mensaje contiene trazas de Python ni nombres de clases.
- CA-21.4 Los mensajes salen del sistema de traducción (RF-23), no de cadenas fijas.

### C. Base de interfaz

#### RF-22 Temas claro, oscuro y automático — Debe — D-03, D-02
- CA-22.1 Dado el sistema en oscuro y selector en Automático, la app arranca oscura; dado el
  sistema en claro, arranca clara.
- CA-22.2 Dado Automático y un cambio del tema del sistema con la app abierta, la app cambia
  en vivo sin reiniciar (verificable en laboratorio manual; el módulo de detección se prueba
  con una señal simulada).
- CA-22.3 Dado el selector en Oscuro o Claro, entonces ignora el tema del sistema y la elección
  se conserva tras reiniciar. Valor inicial: Automático.
- CA-22.4 Los colores están definidos una sola vez como variables por tema (no hay códigos de
  color repetidos en estilos de widgets individuales).
- CA-22.5 Contraste mínimo WCAG AA (4.5:1) para el texto en ambos temas, incluido el texto de los
  botones naranja `#E57000` (que usa texto oscuro o negrita según D-02); un test calcula el
  contraste de los pares texto/fondo definidos.
- CA-22.6 Si la detección del tema falla, se usa el tema de respaldo definido en P-14
  (recomendado: oscuro), se informa en el registro y el selector sigue funcionando.

#### RF-23 Textos traducibles — Debe — D-04
- CA-23.1 Un análisis automático del código de interfaz y de los mensajes de usuario del núcleo
  no encuentra literales de texto visibles fuera de las llamadas de traducción de Qt
  (`tr`/equivalente).
- CA-23.2 La extracción de cadenas (`pyside6-lupdate`) genera un catálogo con todos los textos de
  este documento citados entre comillas.
- CA-23.3 La app está completa en español; no hay otros idiomas (D-04). Cargar un catálogo de
  prueba con cadenas marcadas (p. ej. prefijo "[T]") muestra el prefijo en todos los textos
  visibles, demostrando que ninguno está fijo.
- CA-23.4 El núcleo (sin Qt) devuelve códigos/identificadores de error y la capa de interfaz los
  traduce; el núcleo no importa Qt.

#### RF-24 Modo básico / avanzado — Debe — D-14 (Propuesta; ver P-03)
- CA-24.1 Primera ejecución: modo básico.
- CA-24.2 En modo básico no son visibles: bus, formato, IO Thread, tipo de CPU, ballooning,
  "Ignorar verificación SSL", selector manual de versión, storage del efidisk, discard y ssd
  (los dos últimos por P-03). La MV se crea con los valores por defecto de la sección 4.
- CA-24.3 Dado el cambio a avanzado, aparecen esos campos sin perder lo ya escrito.
- CA-24.4 La preferencia se guarda y se restaura al reiniciar.
- CA-24.5 Dado el cambio a básico con valores no predeterminados en campos que se ocultan,
  entonces se conservan esos valores (se ocultan, no se restablecen) y el resumen (RF-19) los
  muestra para no ocultar lo que se enviará.

#### RF-25 Ayuda en lenguaje llano y guía de token — Debe — D-14, D-09
- CA-25.1 Cada campo técnico (VMID, nodo, firmware, tipo de CPU, sockets, cores, ballooning,
  bus, formato, discard, ssd, IO Thread, bridge, VLAN, huella SSL, 2FA) tiene un icono "?" o
  tooltip con ayuda en español de 1–3 frases, sin jerga sin explicar (p. ej. no usar "thin
  provisioning" sin definirlo).
- CA-25.2 Un test comprueba que cada identificador de campo técnico de una lista fija tiene
  texto de ayuda no vacío en el catálogo.
- CA-25.3 La pantalla de conexión incluye "¿Cómo creo un API Token?" con una guía breve: pasos
  en Proxmox (Datacenter → Permisos → Tokens de API), recomendación de usar token con permisos
  mínimos en lugar de `root@pam` (sección 5) y desmarcar "separación de privilegios" solo si
  se asignan los permisos al usuario.
- CA-25.4 Si se conecta con `root@pam`, se muestra un aviso no bloqueante recomendando un token
  con permisos mínimos.

#### RF-26 Selector manual de versión (solo avanzado) — Podría — D-07 (ver P-08)
- CA-26.1 Dado modo avanzado, entonces existe un selector "Forzar compatibilidad con la versión..."
  (8.0 … última). Por defecto: "Detectada".
- CA-26.2 Dado un valor forzado, la tabla de capacidades (CA-09.6) usa ese valor y la barra
  superior lo marca "(forzada)".
- CA-26.3 En modo básico no existe.

#### RF-27 Avisos de recursos del nodo — Podría — P§5
- CA-27.1 Dado cores totales o memoria mayores que los del nodo destino (`/nodes/{n}/status`),
  se muestra un aviso no bloqueante "Esta máquina pide más ... de los que tiene el servidor".

---

## 3. Requisitos no funcionales

| ID | Requisito | Prioridad | Origen | Criterio de aceptación (verificable) |
|---|---|---|---|---|
| RNF-01 | La interfaz nunca se congela por red ni por polling | Debe | D-05, P§1 | CA-RNF-01: con un mock que tarda 10 s en responder, el bucle de eventos procesa eventos con retraso < 200 ms (test que mide un temporizador de 50 ms durante la espera). Todas las llamadas de red corren en hilos de trabajo. |
| RNF-02 | El núcleo no depende de Qt | Debe | D-05 | CA-RNF-02: en un entorno virtual **sin** PySide6, `import` del núcleo y su suite de pruebas pasan. |
| RNF-03 | Tiempos de espera de red definidos | Debe | D-09 | CA-RNF-03: conexión: 10 s por IP (supuesto); lectura por petición: 30 s; ambos con constantes nombradas. Con IP caída el fallo se informa en ≤ 12 s. |
| RNF-04 | Plataformas: Ubuntu 22.04/24.04 y Windows 10/11 x64 | Debe | D-06 | CA-RNF-04: la app arranca y completa conexión + creación contra el laboratorio en Ubuntu 22.04, 24.04, Windows 10 y 11 (matriz manual por entrega). Python 3.11+. Sin rutas ni separadores fijos de un SO (`platformdirs`, `pathlib`). |
| RNF-05 | Versiones de Proxmox 8.0 a la última | Debe | D-07 | CA-RNF-05: suite de mocks con respuestas reales de 8.0, 8.x y 9.x pasa; integración contra laboratorio 9.2 pasa. |
| RNF-06 | Secretos nunca en texto plano ni en logs | Debe | D-09 | CA-RNF-06: prueba con secreto centinela (token, contraseña, ticket, CSRF, TOTP, clave de recuperación) en todos los flujos y en excepciones: ninguna coincidencia en logs, archivos de usuario, ni mensajes de interfaz. Los logs reemplazan la cabecera `Authorization` y cookies por `***`. |
| RNF-07 | Comunicación segura | Debe | D-10 | CA-RNF-07: no hay conexión HTTP sin TLS; la verificación solo se omite con RF-06; no se envían credenciales antes de resolver la huella. |
| RNF-08 | Sin pruebas destructivas contra servidores reales | Debe | D-15 | CA-RNF-08: la suite por defecto no abre sockets a hosts reales (se bloquea la red en los tests). Las pruebas de integración solo se ejecutan con una variable de entorno explícita que apunta al laboratorio, y son opcionales. |
| RNF-09 | Pruebas con mocks basados en respuestas reales | Debe | D-15 | CA-RNF-09: existe un directorio de respuestas capturadas del laboratorio (versión, nodos, storages, red, nextid, ticket, tarea OK/error) y cada RF de la sección 2 tiene al menos un test automático. |
| RNF-10 | Accesibilidad visual y contraste | Debe | D-02 | CA-RNF-10: ver CA-22.5. Foco de teclado visible; navegación completa por Tab en formularios de conexión y de MV. |
| RNF-11 | Alta resolución y fuentes | Debería | D-06 | CA-RNF-11: a escalado 150 % y 200 % en Windows no hay textos cortados en los diálogos de conexión y creación; las fuentes van incluidas, no se depende de las del sistema. |
| RNF-12 | Rendimiento de arranque y descubrimiento | Debería | — | CA-RNF-12: arranque hasta ventana visible ≤ 5 s en un equipo de referencia (supuesto); descubrimiento con mock de 10 nodos y 50 storages termina ≤ 5 s en paralelo. |
| RNF-13 | Registro (log) útil | Debería | D-09, vitácora | CA-RNF-13: log rotativo en la carpeta de usuario con nivel configurable; incluye UPID, VMID, nodo y errores originales de Proxmox. |
| RNF-14 | Marca | Debe | D-01 | CA-RNF-14: la interfaz no usa el nombre ni el logo de Proxmox como identidad; solo "Compatible con Proxmox VE" en *Acerca de*. |
| RNF-15 | Persistencia robusta | Debería | S-3 | CA-RNF-15: un archivo de perfiles corrupto no impide arrancar; se informa y se crea uno nuevo conservando copia del dañado. |
| RNF-16 | Seguridad de entrada | Debe | D-09 | CA-RNF-16: los valores del usuario se codifican en el cuerpo del formulario (CT-9); un nombre o bridge con `,`, `=`, `&`, espacios o saltos de línea no altera otros parámetros (se rechaza por validación o se codifica). |

---

## 4. Reglas de validación

Toda regla se implementa en el núcleo (sin Qt), con test unitario por fila, y se refleja en
la interfaz con el mensaje indicado.

| ID | Campo | Regla | Mensaje (al usuario) |
|---|---|---|---|
| V-01 | Nombre | Nombre DNS válido (RFC 1123): 1–63 caracteres por etiqueta separada por puntos, longitud total ≤ 253; solo letras ASCII, dígitos y guion; no empieza ni termina en guion; no puede estar vacío; sin punto al final; sin guion bajo ni espacios. Válidos: `srv-web-01`, `db.lab.local`, `A1`. Inválidos: `srv_web`, `-web`, `web-`, `mi máquina`, ``, `a..b`, 64 letras. | "El nombre solo puede tener letras sin acentos, números y guiones, y no puede empezar ni terminar con guion." |
| V-02 | VMID | Entero entre 100 y 999999999. Inválidos: 99, 0, -1, 1000000000, `10a`, `1.5`. | "El número de máquina debe estar entre 100 y 999999999." |
| V-03 | VMID libre | Debe estar libre en todo el clúster (`/cluster/nextid?vmid=`) | ver CA-13.2 |
| V-04 | Nodo | Debe existir y estar en línea | "El nodo no está disponible." |
| V-05 | Sockets / cores | Sockets entero 1–4; cores entero 1–128 (por socket) | "Elige entre 1 y 4 sockets / 1 y 128 núcleos." |
| V-06 | Memoria / balloon | Memoria entero ≥ 16 MiB (la interfaz sugiere ≥ 512 MiB). Con ballooning, 16 ≤ mínimo ≤ memoria | "La memoria mínima no puede superar a la memoria total." |
| V-07 | Bus | Solo `scsi`, `virtio`, `sata`, `ide`. Máximos de dispositivos por bus: scsi 31 (0–30), virtio 16 (0–15), sata 6 (0–5), ide 4 (0–3) | "Ese tipo de conexión admite como máximo N discos." |
| V-08 | Tamaño de disco | Entero ≥ 1 GiB y ≤ 65536 GiB (tope de interfaz, supuesto). Se envía en GiB (CT-6). | "El tamaño debe ser un número entero de GiB, mínimo 1." |
| V-09 | Formato | Según backend del storage (CT-1): `lvmthin`, `lvm`, `zfspool`, `rbd` → solo raw (no se envía `format`). `dir`, `nfs` → raw o qcow2 (por defecto qcow2, P-06). Otros tipos (cifs, btrfs, etc.) → ver P-06. `subvol` nunca. Al cambiar de storage se revalida y se corrige el formato. | "Este almacenamiento solo admite formato raw." |
| V-10 | `scsihw` | Por MV, no por disco (CT-3). Solo se envía si hay ≥ 1 disco `scsi`. Valor por defecto `virtio-scsi-single`. Valores admitidos: `virtio-scsi-single`, `virtio-scsi-pci`, `lsi`, `lsi53c810`, `megasas`, `pvscsi` (los tres últimos y `pvscsi` solo en avanzado; P-02) | — |
| V-11 | IO Thread | Permitido solo si bus = `virtio`, o bus = `scsi` y `scsihw = virtio-scsi-single`. En `sata` e `ide` no. Si el usuario cambia `scsihw` a otro, `iothread` se desmarca en discos scsi. | "IO Thread necesita el bus VirtIO o SCSI con controlador virtio-scsi-single." |
| V-12 | SSD | `ssd=1` permitido en `scsi`, `sata`, `ide`; **no** en `virtio` (CT-4). Independiente de `discard`. | "La emulación SSD no está disponible en el bus VirtIO." |
| V-13 | Discard | `discard=on` permitido en `scsi`, `sata`, `virtio`; para `ide`, por verificar en laboratorio. Independiente de `ssd` (CT-4). Es una casilla propia. | — |
| V-14 | Espacio | Suma de tamaños de discos por storage ≤ espacio libre (`avail`) del storage en el nodo. En backends thin (`lvmthin`, `zfspool`, `rbd`) solo advertencia no bloqueante (CT-5, P-01). Al superar en no-thin: bloquear. | "El disco pide N GiB y «storage» solo tiene M GiB libres." |
| V-15 | VLAN | Entero 1–4094 o vacío | "La VLAN debe estar entre 1 y 4094." |
| V-16 | Bridge | Debe existir en el nodo destino (tipo bridge u OVSBridge) (D-08). Caracteres de nombre sin `,` ni `=` | "La red «x» no existe en el nodo «y»." |
| V-17 | Storage | Debe tener `images`, estar activo y existir en el nodo destino | "Ese almacenamiento no está disponible en el nodo." |
| V-18 | Token | Regex `^[^@!=\s]+@[^@!=\s]+![A-Za-z0-9._-]+=\S+$` (el secreto es todo lo que sigue al primer `=`) | "El token debe tener el formato usuario@realm!nombre=secreto." |
| V-19 | Host/puerto | Host: nombre DNS válido, IPv4 o IPv6; sin esquema ni ruta; puerto entero 1–65535 | "Escribe solo el nombre o la IP del servidor." |
| V-20 | Origen | Solo `disco_vacio` en MVP 1 | — |
| V-21 | Código TOTP | Exactamente 6 dígitos (la clave de recuperación se valida solo por no estar vacía) | "El código tiene 6 números." |

---

## 5. Valores por defecto

Dirigidos a usuarios sin experiencia (D-14). Salvo el tipo de CPU y los explícitos en el
prompt, son **propuestos**; ver P-02.

| Campo | Valor por defecto | Origen |
|---|---|---|
| Modo de interfaz | Básico | D-14 |
| Tema | Automático | D-03 |
| Puerto | 8006 | P§3 |
| Realm | `pam` | P§3 |
| Método de conexión | API Token | D-09 (recomendado) |
| Recordar credenciales | Desmarcada | D-09 |
| Ignorar SSL | Desactivado (y oculto en básico) | D-10 |
| VMID | `/cluster/nextid` | P§4 |
| Nodo destino | Automático (clúster) / único (suelto) | D-08 |
| Firmware | SeaBIOS | P§5 |
| Con OVMF | `machine=q35`, efidisk0 en el storage del primer disco | CT-7, P§5 |
| Sockets | 1 | P§5 |
| Cores | 2 (propuesto) | — |
| Tipo de CPU | `x86-64-v2-AES` | D-14 |
| Memoria | 2048 MiB (2 GiB) (propuesto) | — |
| Ballooning | no se envía (comportamiento de Proxmox) | — |
| Con disco | Sí; 1 disco | P§5 |
| Disco: bus | `scsi` | P§5 |
| Disco: controlador `scsihw` | `virtio-scsi-single` | P§5 |
| Disco: tamaño | 32 GiB (propuesto; ejemplo del prompt) | P§6 |
| Disco: storage | El de mayor espacio libre con `images` en el nodo (propuesto) | — |
| Disco: formato | automático: raw en LVM/ZFS/Ceph; qcow2 en dir/NFS (propuesto) | CT-1 |
| Disco: discard / ssd | Activados (ssd solo si el bus lo admite) (propuesto) | P§6 |
| Disco: IO Thread | Activado si V-11 lo permite (propuesto) | — |
| Red | 1 interfaz `virtio` en `vmbr0` (o primer bridge), sin VLAN | P§5 |
| Origen | Disco vacío | D-13 |
| Timeout de tarea | 10 min (propuesto) | P-05 |
| Intervalo de polling | 1–2 s | — |

---

## 6. Permisos mínimos de Proxmox

**Estado: corregida por la investigación F1 (ver `docs/investigacion/f1-api-proxmox.md`, sección 5, que manda sobre esta tabla); queda pendiente de confirmar en laboratorio.** La lista sale de la documentación y
la experiencia general de la API; ningún privilegio se ha comprobado aún contra el
laboratorio 9.2 ni contra 8.0. Los marcados con (?) son los más dudosos.

| Acción de ProxLaunch | Endpoint | Privilegio y ruta |
|---|---|---|
| Versión | `GET /version` | Cualquier usuario autenticado |
| Próximo VMID / validar VMID | `GET /cluster/nextid` | Cualquier usuario autenticado (?) |
| Topología | `GET /cluster/status` | Cualquier usuario autenticado (?) |
| Listar nodos | `GET /nodes` | `Sys.Audit` en `/nodes/{nodo}` (?) |
| Listar bridges | `GET /nodes/{n}/network` | `Sys.Audit` en `/nodes/{n}` |
| Listar storages y espacio | `GET /nodes/{n}/storage` | `Datastore.Audit` (o `Datastore.AllocateSpace`) en `/storage/{id}` |
| Crear la MV | `POST /nodes/{n}/qemu` | `VM.Allocate` en `/vms/{vmid}` (o `/vms`) |
| Crear discos | ídem | `Datastore.AllocateSpace` en `/storage/{id}` (verificado F6: `VM.Config.Disk` no hace falta para discos nuevos) |
| Cómputo | ídem | `VM.Config.CPU`, `VM.Config.Memory` en `/vms/{vmid}` |
| Red | ídem | `VM.Config.Network` en `/vms/{vmid}` y `SDN.Use` en `/sdn/zones/localnetwork/{bridge}` (PVE 8+) (?) |
| BIOS, machine, scsihw | ídem | `VM.Config.HWType` y/o `VM.Config.Options` en `/vms/{vmid}` (?) |
| Seguimiento de tarea y log | `GET /nodes/{n}/tasks/{upid}/status` y `/log` | Tareas propias: usuario que la inició; las ajenas requieren `Sys.Audit` (?) |
| Confirmar existencia | `GET /nodes/{n}/qemu/{vmid}/config` | `VM.Audit` en `/vms/{vmid}` (?) |
| Verificar permisos (RF-12) | `GET /access/permissions` | Cualquier usuario autenticado |

Observaciones:
- Rol sugerido: uno personalizado con los privilegios anteriores, asignado a `/vms`,
  `/storage` y `/sdn/zones/localnetwork` (o a `/` con propagación). El rol integrado
  `PVEVMAdmin` probablemente cubre la parte de VM pero **no** `Sys.Audit` ni `SDN.Use` (?).
- Un API Token con "Separación de privilegios" activa necesita sus permisos propios; los
  efectivos son la intersección con los del usuario.
- La guía de RF-25 debe actualizarse con el resultado de la verificación.
- Criterio de verificación: en el laboratorio, un token con solo estos privilegios completa
  CA-19.3 y CA-20.3; quitar cada privilegio de uno en uno produce el error de permisos de
  la sección 7 y permite confirmar cuáles son realmente necesarios.

---

## 7. Casos de error (trazabilidad de mensajes)

Cada fila es un test parametrizado de RF-21 con un mock.

| Caso | Disparador (mock) | Mensaje esperado | Requisitos |
|---|---|---|---|
| Credenciales inválidas | `POST /access/ticket` 401 o `/version` 401 con token | "Las credenciales no son válidas..." | CA-01.3, CA-02.2 |
| Ticket expirado | 401 en petición con ticket y renovación fallida | "Tu sesión expiró. Vuelve a iniciar sesión." | CA-03.3 |
| Huella SSL cambiada | Certificado con huella distinta de la guardada | Bloqueo con aviso (CA-05.4) | CA-05.4 |
| 2FA no soportado | Desafío solo WebAuthn/Yubico | Sugerir API Token | CA-04.5 |
| Código 2FA incorrecto | Rechazo del código | "El código no es correcto o ya venció..." | CA-04.3 |
| Servidor/nodo caído | Timeout, conexión rechazada, HTTP 595/596 | "El servidor/nodo <x> no responde..." y reintento por otra IP si hay | CA-01.5, CA-07.2, CA-07.5, CA-11.8, CA-13.7 |
| Permisos insuficientes | HTTP 403 `Permission check failed (/vms/100, VM.Allocate)` | "Tu usuario no tiene permiso para <acción>. Falta VM.Allocate en /vms/100. Pide a tu administrador este permiso o usa un token con permisos suficientes." (extrae privilegio y ruta) | CA-12.1 |
| VMID ocupado | 500 `... already exists` | CA-13.2 / CA-13.3 | CA-13.3 |
| Storage sin espacio | Tarea con `exitstatus` que contiene `out of space`, `Insufficient free space`, `no space left` o `volume group ... has insufficient free space` | "No hay espacio suficiente en «storage» para crear el disco. Libera espacio o elige otro almacenamiento." | V-14, CA-20.4 |
| Timeout de tarea | Tarea `running` más allá del tiempo máximo | CA-20.6 | CA-20.6 |
| Error de formato (CT-9) | 400 `format error` / `invalid format` en un parámetro | "Proxmox no entendió el valor de <campo>." con el parámetro del error | CA-17.2 |
| Parámetro inválido (400) | `errors: {campo: ...}` | Muestra el mensaje junto al campo correspondiente cuando se pueda mapear | RF-21 |
| Versión no soportada | `/version` 7.x | CA-09.2 | CA-09.2 |
| Nombre de recurso inexistente | Storage o bridge desaparecido entre validar y enviar | "«x» ya no existe en el nodo. Actualiza y elige de nuevo." | CA-11.7 |
| Error desconocido | Cualquier otro | CA-21.2 | CA-21.2 |

---

## 8. Matriz de trazabilidad con el alcance

| Elemento del alcance (1.1) | Requisitos |
|---|---|
| API Token | RF-01 |
| Usuario/contraseña con ticket | RF-02 |
| Renovación del ticket | RF-03 |
| 2FA TOTP + claves de recuperación | RF-04 |
| Huella SSL | RF-05, RF-06 |
| Perfiles con varias IPs | RF-07 |
| Llavero, casilla desmarcada por defecto | RF-08 |
| Versión de Proxmox | RF-09, RF-26 |
| Nodo suelto / clúster | RF-10, RF-13 |
| Descubrimiento (nodos, storages, bridges, nextid) | RF-11 |
| Datos generales | RF-13 |
| Firmware y efidisk0 | RF-14 |
| Cómputo | RF-15 |
| Discos vacíos | RF-16, RF-18 |
| Red | RF-17 |
| Seguimiento UPID por etapas y errores | RF-19, RF-20, RF-21 |
| Temas | RF-22 |
| Textos traducibles | RF-23 |
| Modo básico/avanzado | RF-24 |
| Ayuda en lenguaje llano | RF-25 |
| Campo origen | RF-18 |

---

## 9. Preguntas resueltas

**Estado: todas APROBADAS por el usuario el 2026-11-11** con la recomendación indicada
("por ahora": pueden revisarse en MVPs posteriores). La recomendación ya está aplicada en el
documento.

| ID | Pregunta | Decisión aprobada | Afecta |
|---|---|---|---|
| P-01 | La validación de espacio es del MVP 2 (D-12, CT-5), pero el caso "storage sin espacio" debe cubrirse. ¿Qué hace el MVP 1 con una MV? | Bloquear si la suma excede el espacio libre en storages no thin; solo advertir en thin (`lvmthin`, `zfspool`, `rbd`); traducir siempre el error de Proxmox si aun así falla. | V-14, RF-16 |
| P-02 | ¿Se confirman los valores por defecto propuestos (2 cores, 2 GiB de RAM, 32 GiB de disco, discard+ssd+iothread activados) y se ofrecen en avanzado otros controladores `scsihw` y tarjetas de red? | Confirmar los valores; en avanzado ofrecer solo `virtio-scsi-single`/`virtio-scsi-pci` y las tarjetas `virtio`/`e1000`. | Sección 5, V-10, CA-17.6 |
| P-03 | D-14 está "Propuesta", no aprobada. ¿Se aprueba, y se ocultan también discard y ssd en básico? | Aprobar D-14 y ocultar discard/ssd en básico (se aplican con los valores por defecto). | RF-24 |
| P-04 | Windows 11 exige TPM (`tpmstate0`, CT-7) y no está en la lista del MVP 1. ¿Se incluye? | No en MVP 1; añadir casilla "TPM 2.0" en avanzado junto con el origen del SO (MVP 4). | RF-14 |
| P-05 | Tiempo máximo de seguimiento de una tarea. | 10 min configurables internamente; al vencer, no declarar fallo (CA-20.6). | RF-20 |
| P-06 | ¿Formato por defecto en dir/NFS y qué hacer con tipos no listados (cifs, btrfs, glusterfs, etc.)? | qcow2 por defecto en dir/NFS/cifs; para tipos no confirmados en laboratorio, solo raw. | V-09 |
| P-07 | ¿Cómo se decide el nodo "Automático" (D-08: más RAM y espacio libres)? | Nodo en línea con un storage con espacio suficiente y la mayor RAM libre; desempata el mayor espacio libre. | CA-13.5 |
| P-08 | ¿El selector manual de versión (D-07) entra en el MVP 1 o espera al modo simulación del MVP 2? | Podría en MVP 1 (solo forzar compatibilidad), simulación en MVP 2. | RF-26 |
| P-09 | `ostype` (tipo de SO invitado) no está en el alcance. | No enviarlo en MVP 1; considerarlo en MVP 4 junto al origen del SO. | RF-19 |
| P-10 | `pre-enrolled-keys` del efidisk (necesario para Secure Boot con Windows). | Enviar `pre-enrolled-keys=1` (valor de la interfaz web de Proxmox); confirmar en laboratorio. | RF-14 |
| P-11 | ¿Otros realms (LDAP, AD) además de `pam` y `pve`? | Campo editable con `pam`/`pve` sugeridos; no probar LDAP en laboratorio. | RF-02 |
| P-12 | Huellas SSL por host:puerto vs. por perfil, y reemplazo de una huella cambiada en avanzado. | Por host:puerto; reemplazo solo en avanzado con confirmación. | RF-05, S-7 |
| P-13 | Ticket expirado sin renovar: ¿conservar la contraseña en memoria para reconectar sola? | No; pedirla de nuevo (más seguro, y con 2FA sería necesario igual). | RF-03, S-5 |
| P-14 | Tema por defecto cuando la detección del sistema falla (frecuente en Linux, D-03). | Oscuro (acorde a la consola de Proxmox); selector disponible. | RF-22 |
| P-15 | ¿Se inicia la MV al terminar la creación? | No (S-1); evaluarlo en un MVP posterior. | S-1 |

---

## 10. Pendientes de verificación en laboratorio (para el probador/investigador)

1. Privilegios exactos de la sección 6.
2. Forma exacta de `efidisk0` (`efitype`, `pre-enrolled-keys`, `format`) en LVM-thin, ZFS y directorio.
3. Respuesta de `/access/ticket` con 2FA (campos del desafío) y comportamiento de la
   renovación con ticket.
4. Textos exactos de los errores (VMID existente, sin espacio, permisos) en 8.x y 9.2, para
   ajustar la tabla de la sección 7.
5. Soporte de `discard` en bus `ide`.
6. Formato `net0` y codificación (CT-9) en 8.0 y 9.2.

---

## 11. Aclaraciones posteriores (orquestador, 2026-11-11)

Surgidas de las pruebas de F2; los requisitos anteriores no cambian de ID.

- **A-1 (V-01, V-18, V-19, V-21):** las validaciones comprueban el texto **completo**. Un
  salto de línea final (por ejemplo, al pegar un token) es inválido. Corregido en F2.
- **A-2 (V-13), revisada tras F1:** la API admite `discard` en los cuatro buses, incluido
  `ide`. Se permite.
- **A-3 (V-19):** un host formado solo por 4 grupos numéricos separados por puntos se
  trata como IPv4 y debe ser una IPv4 válida (`999.1.1.1` es inválido). Pendiente de
  implementar en F3.
- **A-4 (§1.4, perfiles duplicados):** se permiten dos perfiles con el mismo nombre, pero
  la interfaz avisa de forma no bloqueante al guardar (F4).
- **A-5 (sección 6):** la tabla de permisos válida es la de
  `docs/investigacion/f1-api-proxmox.md` §5, con el rol `ProxLaunchCreador`.
- **A-6 (RF-10):** si `/cluster/status` responde 403 (falta `Sys.Audit` en `/`), no se
  bloquea la conexión: se muestra "topología desconocida (N nodos)" con un aviso de permiso.
- **A-7 (RF-04, CA-04.5):** el desafío 2FA se obtiene del ticket parcial (`PVE:!tfa!…`). Se
  admite si trae `totp` o `recovery` no vacío; `webauthn`, `u2f` y `yubico` no se admiten.
  La clave de recuperación se normaliza (minúsculas, sin espacios).
- **A-8 (sección 7, CA-13.2/13.3):** patrones de VMID ocupado: HTTP 500
  `VM <n> already exists on node '<nodo>'` al crear; HTTP 400 con
  `errors.vmid = "VM <n> already exists"` en `/cluster/nextid?vmid=`.
- **A-9 (V-09, P-06):** sin `format`, Proxmox crea raw en storages de directorio. Por eso,
  con AUTO se envía `format=qcow2` explícito en directorio y NFS (ya implementado).
