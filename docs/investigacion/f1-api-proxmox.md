# Investigación F1 — Transporte HTTP y API de Proxmox VE (2026-11-11)

Autor: subagente `investigador`; resumen del orquestador. Convención: **[H]** hecho con
fuente · **[I]** inferencia · **[LAB]** por verificar en laboratorio. Resultado: **D-17**.

## 1. proxmoxer 2.3.0 — por qué se descartó
- [H] La autenticación hace `requests.post()` a `/access/ticket` **fuera de la sesión**
  (`proxmoxer/backends/https.py`, `ProxmoxHTTPAuth._get_new_tokens`): un adaptador con
  huella montado en la sesión no protege la petición que lleva la contraseña.
- [H] No permite inyectar una `requests.Session` (`Backend.get_session()` crea una nueva;
  solo accesible por el atributo privado `_store["session"]`).
- [H] 2FA de un solo paso: el código debe conocerse al construir el objeto; sin él envía
  `totp:None`.
- [H] Registra a nivel INFO el `data` completo de cada petición (`core.py`, `_request`).
- [H] Sin failover de hosts.

## 2. Transporte con `requests` (D-17)
- Adaptador `HTTPAdapter` que pasa a urllib3 `assert_fingerprint=<sha256>` **y**
  `cert_reqs="CERT_NONE"` (con `assert_fingerprint` se omite el hostname, pero
  `cert_reqs` se sigue aplicando: urllib3 `connection.py`).
- urllib3 normaliza la huella (sin `:`, minúsculas). Si no coincide lanza
  `SSLError("Fingerprints did not match. Expected …, got …")`, que `requests` envuelve en
  `requests.exceptions.SSLError` → traducir a `HUELLA_CAMBIADA`.
- `requests` codifica el formulario con `urlencode(doseq=True)` / `quote_plus`:
  `,`→`%2C`, `=`→`%3D`, espacio→`+` (CT-9 resuelto).

## 3. 2FA en `POST /api2/json/access/ticket` (pve-access-control, 8.0–9.2)
- **Paso 1** (`username`, `password`, `realm` opcional): con 2FA configurada la respuesta es
  `data = {ticket, username, CSRFPreventionToken, NeedTFA: 1}`.
- El ticket parcial tiene la forma `PVE:!tfa!<desafío>:<HEX8>::<firma>`. El desafío es
  JSON con `%` y `:` escapados. Así lo extrae la interfaz oficial:
  `JSON.parse(decodeURIComponent(ticket.split(':')[1].slice('!tfa!'.length)))`.
- Claves del desafío (se omiten si no aplican): `totp: true`, `recovery: [índices
  disponibles]`, `webauthn: {…}`, `u2f: {…}`, `yubico: true`.
  **Soportado por ProxLaunch** = `totp` presente o `recovery` no vacío; si no → `TFA_NO_SOPORTADO`.
- **Paso 2:** `POST /access/ticket` con `username=<usuario@realm>`,
  `tfa-challenge=<ticket parcial>`, `password=totp:123456` o `password=recovery:xxxx-xxxx-xxxx-xxxx`.
  La respuesta trae ticket completo + `CSRFPreventionToken`.
- Claves de recuperación: 10 por conjunto, `xxxx-xxxx-xxxx-xxxx` (hex en minúsculas), un solo uso.
- [I] Un código incorrecto da HTTP 401, igual que una contraseña errónea: el traductor usa
  el estado (estamos en el paso 2) para devolver `TFA_CODIGO_INCORRECTO`.
- No usar el parámetro `otp` de un solo paso.
- [LAB] Captura real en 9.2; caducidad del ticket parcial; texto del 401.

## 4. Renovación del ticket
- [H] `password` admite un ticket válido; si `ticketuser == username` **no** se vuelve a
  pedir 2FA. Ticket parcial → `incomplete ticket`. Vida del ticket: 2 h; tolerancia de
  reloj: 300 s.
- La respuesta trae un **CSRF nuevo**: `renovar` actualiza ticket y CSRF.

## 5. Permisos reales por endpoint
| Endpoint | Permiso |
|---|---|
| `GET /version` | todos |
| `GET /cluster/nextid` | todos; `?vmid=` ocupado → HTTP 400 `errors.vmid = "VM <n> already exists"` |
| `GET /cluster/status` | `Sys.Audit` en `/` |
| `GET /nodes` | todos; RAM/CPU solo con `Sys.Audit` en `/nodes/{n}` |
| `GET /nodes/{n}/network` | todos, pero los bridges solo se listan con `SDN.Audit` o `SDN.Use` en `/sdn/zones/localnetwork/<bridge>` |
| `GET /nodes/{n}/storage` | filtra por `Datastore.Audit` o `Datastore.AllocateSpace` en `/storage/{id}` |
| `GET /nodes/{n}/status` | `Sys.Audit` en `/nodes/{n}` |
| `POST /nodes/{n}/qemu` | `VM.Allocate` en `/vms/{vmid}`; `name`, `bios` → `VM.Config.Options`; `machine`, `scsihw` → `VM.Config.HWType`; `cores`, `sockets`, `cpu` → `VM.Config.CPU`; `memory`, `balloon` → `VM.Config.Memory`; `netN` → `VM.Config.Network`; discos y efidisk → `Datastore.AllocateSpace` en `/storage/{id}`; bridge → `SDN.Use` en `/sdn/zones/localnetwork/<bridge>[/<vlan>]`. VMID ocupado → HTTP 500 `VM <n> already exists on node '<nodo>'` |
| `GET …/tasks/{upid}/status` y `/log` | propietario de la tarea (usuario o su token) o `Sys.Audit` en `/nodes/{n}` |
| `GET …/qemu/{vmid}/config` | `VM.Audit` en `/vms/{vmid}` |
| `GET /access/permissions` | todos (los propios) |

**Rol mínimo recomendado `ProxLaunchCreador`:** `VM.Allocate, VM.Audit, VM.Config.Options,
VM.Config.HWType, VM.Config.CPU, VM.Config.Memory, VM.Config.Network, VM.Config.Disk,
Datastore.Audit, Datastore.AllocateSpace, SDN.Use, Sys.Audit`, asignado en `/` con
propagación (lo más simple). **Verificado en laboratorio (F6, PVE 9.2.26):** `VM.Config.Disk`
y `Datastore.Audit` NO hacen falta para crear discos nuevos (`PVE/API2/Qemu.pm:194,1031`):
el rol mínimo del MVP 1 son 10 privilegios. Sin `VM.Audit` la creación termina con avisos;
sin `Sys.Audit` la topología se degrada. El 403 por falta de `VM.Allocate` llega sin ruta ni
privilegio (`Qemu.pm:1353`). [LAB, original] Si `VM.Config.Disk` hace falta al crear, y el contenido
de los roles integrados.

## 6. Parámetros de creación
- `efidisk0=<st>:1,efitype=4m,pre-enrolled-keys=1` (+ `format=` en storages de
  directorio). Los valores por defecto de la API son `2m` y `0`, así que hay que enviarlos.
  El tamaño `1` se ignora (lo fija la plantilla OVMF).
- Sin `format`, los storages de directorio, NFS y LVM crean **raw**. Con AUTO hay que
  enviar `format=qcow2` en directorio y NFS, y nada en lvmthin, zfspool y rbd.
- `discard` lo admiten los **cuatro** buses (incluido ide). `ssd` no existe en virtio.
  `iothread` solo en scsi y virtio. Máximos por bus: ide 4, sata 6, scsi 31, virtio 16.

## 7. PySide6 / Qt
- PySide6 ≥ 6.11 admite Python 3.14; 6.12 publica wheels abi3 (glibc ≥ 2.34; Ubuntu
  22.04 tiene 2.35).
- `QStyleHints.colorScheme` y `colorSchemeChanged` existen desde Qt 6.5. En GNOME, la
  detección vía xdg-desktop-portal con cambio en vivo llegó en Qt 6.8. Sin portal → `Unknown`
  → respaldo oscuro (P-14). En Windows se lee `AppsUseLightTheme` y se escucha
  `WM_SETTINGCHANGE`.

## 8. Verificado en laboratorio (MVP 2)

Entorno: Proxmox VE **9.2.26** anidado, un solo nodo (`127.0.0.1`), pruebas
`tests/integracion/test_lab_lotes.py` (LAB-L01 a LAB-L13). Los hechos se observaron en el
laboratorio; las inferencias se derivan de ellos y **no** se comprobaron. Todo lo multinodo y
lo de Proxmox 8.x sigue siendo **[LAB] pendiente**: no hay laboratorio para ello.

### 8.1 Hechos [H] (observados en PVE 9.2.26)

**Borrar una MV (`DELETE /nodes/{n}/qemu/{vmid}`)**
- [H] Los parámetros (`destroy-unreferenced-disks`, `purge`) deben ir en la **cadena de
  consulta**. En el cuerpo del formulario la API responde **501**.
- [H] Solo exige `VM.Allocate` en `/vms/{vmid}`: el rol de 10 privilegios no cambia. Sin ese
  privilegio, el 403 nombra privilegio y ruta.
- [H] Con `protection=1` responde **500** «protection mode enabled».
- [H] Con la MV encendida responde **500** «is running - destroy failed».
- [H] Con la MV bloqueada (`lock`) la petición se acepta y la **tarea** falla: «VM is locked».
- [H] **Sin** `destroy-unreferenced-disks` se borran los discos referenciados en la
  configuración, pero un volumen suelto (`vm-<vmid>-disk-N` que la MV no tiene asignado)
  **sobrevive**. Es la razón de D-21: ProxLaunch envía `destroy-unreferenced-disks=0` y sin
  `purge`, así que nunca borra un volumen suelto.
- [H] Las creaciones de ProxLaunch no dejaron discos sueltos (LAB-L05, D-21).

**Etiquetas (`tags`)**
- [H] Se aceptan como separadores `;`, `,` y espacio. Proxmox las **normaliza**: minúsculas,
  ordenadas, y las devuelve separadas por `;`.
- [H] Los caracteres `/`, `@`, `ñ` o un `-` inicial dan **400**.
- [H] Con `user-tag-access` del datacenter **restringido**, el `POST` responde **200** y la
  **tarea** falla con **403** «Sys.Modify for modifying tag».
- [H] Crear con `tags` sin `VM.Config.Options` también falla **en la tarea**, no en el `POST`.
- [H] La app pausa el lote ante ese error y ofrece «Seguir sin etiquetas».

**Números de MV (VMID) y nombres**
- [H] `GET /cluster/nextid` (sin parámetro) devuelve **el mismo número** a peticiones
  simultáneas.
- [H] `GET /cluster/nextid?vmid=<n>` marca el número como ocupado **desde el primer GET
  posterior al `POST`**, no desde que el `POST` responde (ventana de carrera real, LAB-L03).
- [H] Proxmox **permite nombres duplicados** (el VMID es lo único que no se repite).
- [H] Justo tras el `POST`, durante ~**250 ms**, la configuración de la MV solo contiene
  `lock: create`. Mientras tanto no se puede leer su etiqueta: la app no decide la propiedad
  hasta que la configuración termina de crearse.
- [H] Una MV recién creada aparece **sin nombre ~4 s** en `GET /cluster/resources`.

**Visibilidad (`/cluster/resources?type=vm`)**
- [H] Con `VM.Audit` en `/` lista **todas** las MV. Con una ACL parcial lista **solo las
  visibles** para ese usuario (LAB-L11).

**Espacio y simulación**
- [H] El `efidisk` (OVMF) ocupa **4 MiB** tanto en LVM como en lvmthin (LAB-L04). Es el valor
  de `TAM_EFIDISK_MIB`.
- [H] Durante la simulación, el registro de acceso de `pveproxy` solo muestra `GET` (LAB-L12,
  con un control positivo que sí muestra un `POST` real).

**Rendimiento**
- [H] Lote de **30 MV**: creación **46,5 s** y deshacer **46,7 s** (≈ 1,6 s por MV) (LAB-L13).

### 8.2 Inferencias [I] (derivadas, sin comprobar)

- [I] El aviso de nombre duplicado (V-L06) puede **no saltar** con MV creadas hace pocos
  segundos, porque `/cluster/resources` las devuelve sin nombre durante ~4 s. Es una
  limitación del aviso, no un fallo: Proxmox acepta el duplicado igualmente.
- [I] Como `nextid?vmid=` solo marca el número tras el primer GET posterior, dos lotes que
  planifican a la vez el mismo rango pueden ver libre un número que ya se envió. Por eso la
  app reconsulta antes de cada `POST` y trata un `already exists` del `POST` como «lo usó otra
  persona».
- [I] Que la `lock: create` inicial exista en **8.x** y con el mismo ritmo no se ha probado;
  la app no asume una duración (relee en cada comprobación).
- [I] Que una restricción de etiquetas dé el mismo 403 en **8.0 a 8.x** se infiere del código
  (`PVE/GuestHelpers.pm`), no de un servidor 8.x.
- [I] Que el reparto entre nodos, el almacenamiento compartido y la concurrencia de varios
  nodos funcionen igual que en un solo nodo no está verificado: solo hay pruebas con
  respuestas simuladas.
- [I] Los ~1,6 s por MV dependen del almacenamiento y de la máquina del laboratorio; no son
  una garantía de rendimiento.

Fuentes completas: informe del investigador en la bitácora (entrada F1); código de
proxmoxer, pve-access-control, pve-common, proxmox-tfa, qemu-server, pve-manager,
pve-storage, urllib3, requests y Qt, todas leídas el 2026-11-11.
