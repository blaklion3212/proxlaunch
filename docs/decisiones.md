# Registro de decisiones — ProxLaunch

Fuente de verdad de las decisiones de producto y técnicas. La especificación
original está en `prompt.md`; donde este documento la contradiga, **manda este
documento**. Cada decisión indica su fecha y su estado.

Estados: **Aprobada** (confirmada por el usuario) | **Propuesta** (pendiente de
confirmar) | **Pospuesta** (se decidirá más adelante).

---

## D-01 · Nombre e identidad visual — Aprobada (2026-11-11)
- La app se llama **ProxLaunch**. No se usan el nombre ni el logo de Proxmox (son
  marcas registradas de Proxmox Server Solutions GmbH). Se puede indicar
  "Compatible con Proxmox VE" en *Acerca de*.
- El logo se redibujó como SVG limpio a partir de los diseños del usuario
  (`logotipo.png`, `boton-icono-favicon.png`, `referencia general.png`).
  Los archivos finales están en `recursos/marca/`:
  - `proxlaunch-logotipo-claro.svg` / `-oscuro.svg`: logo completo según el tema.
  - `proxlaunch-simbolo-claro.svg` / `-oscuro.svg`: solo el símbolo.
  - `proxlaunch-icono.svg`: icono de app con texto (96 px o más).
  - `proxlaunch-icono-sin-texto.svg`: icono para 16–64 px.
  - `generador/generar_logo.py`: regenera todas las variantes (requiere la
    tipografía Montserrat, licencia OFL).
- En el icono, la flama y la nariz van en tonos cálidos y la "P" en azul medio,
  para dar contraste. **No cambiar el logo sin consultar al usuario.**

## D-02 · Paleta de colores — Aprobada (2026-11-11)
- **Naranja `#E57000`**: acciones principales, selección activa, barra de progreso.
- **Turquesa del logo (≈ `#3FA6C5`)**: secundario (enlaces, información, iconos
  de estado, detalles de encabezado).
- **Grises pizarra** del `prompt.md`: fondos, paneles y bordes.
- Cada color tiene un solo valor definitivo (el prompt daba alternativas con "o").
- Contraste mínimo legible (WCAG AA): el texto blanco sobre `#E57000` no llega a
  4.5:1. En los botones naranjas usar texto oscuro, negrita o un tono más oscuro.

## D-03 · Temas — Aprobada (2026-11-11)
- Tema **oscuro y claro**, que sigue automáticamente el tema del sistema
  operativo y cambia en vivo.
- Selector **Automático / Oscuro / Claro** en la configuración, por si la
  detección falla (frecuente en Linux). Por defecto: Automático.
- Colores definidos una sola vez como variables por tema.

## D-04 · Idioma — Aprobada (2026-11-11)
- Interfaz **solo en español**, pero con todos los textos pasando por el sistema
  de traducción de Qt desde el MVP 1 (sin cadenas fijas en el código).
- Los errores de la API de Proxmox (en inglés) se traducen a mensajes claros.

## D-05 · Stack tecnológico — Aprobada (2026-11-11)
- **Python 3.11+**, **PySide6 (Qt 6)** y ~~proxmoxer~~ **`requests`** (ver D-17). Se
  descartó Rust + Tauri.
- El núcleo (modelos, cliente de la API, validaciones, motor de lotes) **no
  depende de Qt**, para probarlo sin interfaz y poder usarlo desde la terminal
  más adelante.
- Llamadas de red y seguimiento de tareas en hilos de trabajo: la interfaz nunca
  se congela.

## D-06 · Plataformas y distribución — Aprobada (2026-11-11)
- **Ubuntu 22.04 y 24.04 LTS**: AppImage o .deb.
- **Windows 10 y 11 de 64 bits**: instalador .exe con asistente.
- **macOS queda fuera del alcance.**
- Implicaciones: `keyring` para secretos, `platformdirs` para rutas, fuentes
  incluidas en la app, escalado de alta resolución en Windows, compilación por
  sistema operativo en CI, y detectar separador y codificación al importar CSV.
- Firma de código en Windows: **Pospuesta** (MVP 5).

## D-07 · Versiones de Proxmox VE — Aprobada (2026-11-11)
- Versión mínima **8.0**. Objetivo: **la última versión publicada**.
- La versión se **detecta al conectar** (`/api2/json/version`) y se muestra en la
  barra superior.
- Las funciones se activan según una **tabla de capacidades por versión**. Si
  algo no está disponible, se oculta o se deshabilita con un aviso ("Requiere
  Proxmox 8.2 o superior").
- **Selector manual de versión solo en modo avanzado**: para preparar lotes sin
  conexión, forzar compatibilidad o simular.

## D-08 · Topología — Aprobada (2026-11-11)
- Soporta **nodos sueltos y clústeres**, con detección automática.
- Nodo destino en clúster: **Automático** (más RAM y espacio libres; predeterminado),
  **Manual** o **Repartir el lote** entre nodos. Los nodos sin conexión se
  muestran deshabilitados.
- Storage **compartido** (`shared=1`): su espacio se cuenta una sola vez. Storage
  **local**: se cuenta por nodo.
- Bridges, ISOs e imágenes se validan **en el nodo destino**.
- VMID único en todo el clúster; la reserva de VMIDs del lote se hace a ese nivel.

## D-09 · Conexión y credenciales — Aprobada (2026-11-11)
- Dos métodos: **API Token** (`USER@REALM!TOKENID=SECRETO`) y **usuario/contraseña**
  (ticket `PVEAuthCookie` + `CSRFPreventionToken`, renovado antes de expirar a las 2 h).
- **Perfiles guardados**: host, puerto (8006), usuario y realm.
- **Varias IPs por perfil** para clústeres, con reintento automático en la
  siguiente si una no responde.
- Casilla **"Recordar credenciales" desmarcada por defecto**. Si se marca, el
  secreto va al llavero del sistema (Administrador de credenciales en Windows,
  Secret Service en Ubuntu). Si no hay llavero: avisar y no guardar. **Nunca en
  texto plano.**
- Los secretos nunca se escriben en logs.
- Se recomienda en la app (con una guía breve) usar **API Tokens** con permisos
  mínimos en lugar de `root@pam`.

## D-10 · Certificados SSL — Aprobada (2026-11-11)
- En la **primera conexión** se muestra la huella del certificado; si el usuario
  confía, se guarda.
- En conexiones siguientes, si la huella **cambia**, se bloquea y se avisa.
- "Ignorar verificación SSL" existe **solo en modo avanzado**.

## D-11 · Segundo factor (2FA) — Aprobada (2026-11-11)
- Los sitios del usuario normalmente **no usan 2FA**.
- Se soporta **TOTP + claves de recuperación**; la pantalla aparece solo si el
  servidor lo pide.
- **WebAuthn y Yubico OTP quedan fuera**: si un servidor los exige, la app lo
  explica y sugiere usar un API Token.

## D-12 · Plan de entregas — Aprobada (2026-11-11)
| Entrega | Contenido |
|---|---|
| **MVP 1** | Conexión (token y usuario/contraseña con 2FA), descubrimiento de nodos, storages y redes, crear **una** MV con disco vacío. |
| **MVP 2** | Lotes (nombres y VMIDs secuenciales, reparto entre nodos), validación de espacio, pantalla de resumen, modo simulación, rollback. |
| **MVP 3** | Perfiles predefinidos de MV, guardar y cargar lotes, importación desde CSV. |
| **MVP 4** | Origen del sistema operativo (ver D-13). |
| **MVP 5** | Instaladores para Ubuntu y Windows, pipeline de CI. |

**Fuera del alcance por ahora:** contenedores LXC, editar o borrar MVs que ya
existían, monitoreo, alta disponibilidad (HA).

## D-13 · Origen del sistema operativo — Pospuesta (2026-11-11)
- Los casos reales del usuario son variados: **ISO**, **OVA** (convertir o
  extraer el disco qcow2/vmdk) y **migración desde VMware**.
- Se diseña desde el MVP 1 como **pieza intercambiable** ("Origen del SO"); el
  modelo de datos de la MV incluye un campo de origen, que en el MVP 1 solo
  admite "Disco vacío".
- A investigar en el MVP 4: algunas importaciones exigen `root@pam` o SSH y
  dependen de la versión de Proxmox.

## D-14 · Usabilidad para usuarios sin experiencia — Aprobada (2026-11-11)
- **Valores seguros por defecto**: el usuario básico solo llena nombre, perfil y
  cantidad.
- **Modo básico / avanzado**: en el básico se ocultan bus, formato, IO Thread,
  tipo de CPU y ballooning.
- **Textos de ayuda en lenguaje llano** en cada campo técnico.
- Tipo de CPU por defecto `x86-64-v2-AES` (no `host`, que impide migrar entre
  nodos con CPUs distintas).
- En modo básico se ocultan también `discard` y `ssd` (P-03 de los requisitos).

## D-15 · Pruebas — Aprobada (2026-11-11)
- No existe un Proxmox de pruebas en los sitios. **Nunca** se ejecutan pruebas
  que creen o borren MVs contra producción.
- Suite automática con **mocks** basados en respuestas reales de la API.
- **Laboratorio local**: Proxmox VE 9.2 anidado en QEMU dentro del equipo de
  desarrollo (`~/aprovprox-lab/`, fuera del repositorio). El usuario pidió
  **eliminarlo sin dejar rastro** al terminar todas las pruebas: borrar la
  carpeta y quitar al usuario del grupo `kvm`.

## D-16 · Detalles del MVP 1 — Aprobada (2026-11-11)
El usuario aprobó "por ahora" las 15 recomendaciones P-01 a P-15 de
`docs/requisitos/mvp1.md` (sección 9). Las más relevantes:
- Espacio insuficiente: bloquear en storages normales, solo advertir en thin (P-01).
- Valores por defecto: 2 núcleos, 2 GiB de RAM, disco de 32 GiB (P-02).
- TPM, `ostype` y encendido automático quedan fuera del MVP 1 (P-04, P-09, P-15).
- Espera máxima de tarea: 10 min, sin declarar fallo al vencer (P-05).
- Nodo "Automático": el de mayor RAM libre con espacio suficiente (P-07).
- Huella SSL por host:puerto; la contraseña no se conserva en memoria (P-12, P-13).
- Tema de respaldo si falla la detección: oscuro (P-14).

## D-17 · Conexión HTTP con `requests` directo, sin `proxmoxer` — Aprobada (2026-11-11)
- Sustituye la parte de D-05 que elegía `proxmoxer`.
- Motivo (investigación F1, `docs/investigacion/f1-api-proxmox.md`): `proxmoxer` envía la
  contraseña fuera de la sesión, sin la verificación de huella (rompería D-10). Además no
  admite 2FA interactiva en dos pasos, registra los datos completos de cada petición y no
  tiene failover de IPs.
- La conexión se implementa sobre `requests.Session` con huella fija (urllib3
  `assert_fingerprint`). Autenticación por token y ticket, 2FA en dos pasos, renovación y
  failover son código propio en `nucleo/api/`.
- Decisiones técnicas asociadas (orquestador): PySide6 ≥ 6.11; si falta `Sys.Audit`
  para ver el clúster, la app sigue con un aviso (no bloquea); el rol recomendado en la
  guía de tokens incluye `Sys.Audit`.

## Correcciones técnicas a `prompt.md`
Errores o imprecisiones de la especificación original que los requisitos deben
respetar:
1. `subvol` es un formato de **contenedores LXC**, no de MVs. LVM-thin, ZFS y Ceph
   solo admiten `raw`; los storages de tipo directorio y NFS admiten `raw` o
   `qcow2`. La app elige el formato según el backend.
2. El estado de tarea (`/tasks/{upid}/status`) no da porcentaje: la barra de
   progreso es **por etapas** (o leyendo el log de la tarea).
3. El controlador SCSI (`scsihw`) se configura **por MV**, no por disco. IO Thread
   requiere `virtio-scsi-single` o el bus `virtio`.
4. `discard` y `ssd` son opciones distintas; `ssd=1` no se admite en el bus `virtio`.
5. En pools *thin* el espacio se puede sobreasignar: la política de validación
   (bloquear o advertir) se define en el MVP 2.
6. Proxmox trabaja en **GiB**.
7. UEFI: además de `efidisk0`, conviene el tipo de máquina `q35`; Windows 11 exige
   TPM (`tpmstate0`).
8. `/cluster/nextid` devuelve el mismo ID a peticiones simultáneas: en lote, los
   VMIDs se reservan de forma controlada.
9. Hallazgo del laboratorio: los parámetros como `net0=virtio,bridge=vmbr0` deben
   ir correctamente codificados en el formulario; si no, la API responde
   "format error".
