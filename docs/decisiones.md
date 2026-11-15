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

## D-13 · Origen del sistema operativo — Resuelta por D-24 (2026-11-14)
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

## D-18 · Conexión directa, sin proxy del sistema ni `.netrc` — Aprobada (2026-11-11)
- El usuario confirma que sus equipos no usan proxy para llegar a Proxmox.
- La sesión HTTP usa `trust_env = False`: se ignoran `HTTPS_PROXY`/`HTTP_PROXY` y `.netrc`,
  que podía sustituir la cabecera del token (auditoría F7, M4).
- Si en el futuro hiciera falta un proxy, se añadirá como campo explícito por perfil,
  aplicado también a la sonda de huella.
- Decisión técnica asociada (orquestador, F7 B6): con "Ignorar verificación SSL" activo
  y método de contraseña, se pide confirmación en cada conexión.

## D-19 · Licencia del proyecto — Aprobada (2026-11-12)
- ProxLaunch es de uso interno, con todos los derechos reservados (`LICENSE`).
- Se puede abrir más adelante; las dependencias (PySide6/Qt LGPL-3.0, fuentes OFL) se
  usan sin modificar y sus licencias se incluyen.

## D-20 · Comportamiento de los lotes (MVP 2) — Aprobada (2026-11-13)
El usuario aprobó las 12 recomendaciones de `docs/requisitos/mvp2.md` §9:
1. **Rollback** manual: lista de lo creado por el lote y confirmación; "solo incompletas" o
   "todo el lote". Nunca automático (P-L03).
2. **Sobreasignación thin:** advertir con casilla de confirmación; bloquear si la suma supera
   3 × el espacio libre (P-L01).
3. **Etiquetas** `proxlaunch;lote-<id>` en las MVs: activadas por defecto, desactivables en
   modo avanzado (P-L04).
4. **Lote que no cabe:** bloquear y ofrecer "Reducir a N" (P-L02).
5. **Concurrencia:** 1 MV a la vez por nodo, hasta 4 nodos en paralelo (P-L05).
6. **VMIDs ocupados:** saltarlos y avisar; si se ocupa justo antes de enviar, esa MV falla y se
   ofrece reintentar (P-L06).
7. **Tamaño máximo:** 100 MVs por lote (P-L07).
8. **Errores repetidos:** pausa inmediata ante errores globales (sesión, huella, permisos, sin
   nodos) y tras 3 seguidos de la misma causa (P-L09).
9. **Reparto por defecto:** equilibrado por memoria y espacio; "por turnos" en avanzado (P-L08).
10. **Simulación** solo conectada; no se ejecuta de verdad si la versión forzada es mayor que la
    detectada (P-L10).
11. **Lote homogéneo**, sin edición por MV (P-L12).
12. **Informe final:** copiar y guardar `.txt` (P-L11).

## D-21 · Deshacer sin borrar discos sueltos — Aprobada (2026-11-13)
Al deshacer, el `DELETE` se envía con `destroy-unreferenced-disks=0` (sin `purge`): se
borra la MV con sus discos referenciados y nunca un volumen suelto, que podría ser de
otra MV antigua con el mismo VMID (hallazgo M2 de la auditoría F5). LAB-L05 comprobó que
las creaciones de ProxLaunch no dejan discos sueltos. Sustituye lo propuesto en
CA-L18.5. La app no busca discos sueltos tras borrar (E-L21 queda sin uso); la guía
indica revisarlos en Proxmox si se sospecha que quedó alguno.

## D-22 · MVP 3: lote por filas y decisiones de perfiles, lotes guardados y CSV — Aprobada (2026-11-14)
1. **Lote por filas (P-M01 A, decidida por el usuario):** un CSV con MVs distintas se crea como
   **un solo lote** en el que cada fila es una MV con su propia configuración: un resumen, una
   confirmación, un informe y un «Deshacer». Amplía D-20 (11) y P-L12: el lote homogéneo
   sigue existiendo; el lote por filas es una segunda forma de definir el mismo lote. Todas
   las garantías del MVP 2 (INV-L1..L5) se mantienen y se vuelven a probar.
2. Adoptadas con la recomendación del analista mientras el usuario estaba ausente y aprobadas
   como definitivas por el usuario (2026-11-14): P-M02 B (importar solo las filas válidas, con
   confirmación y las excluidas visibles), P-M03 A (lote guardado autocontenido), P-M04 A
   (storage y bridge como pistas opcionales con reemplazo avisado), P-M05 A (6 perfiles de
   fábrica, sin Windows 11), P-M06 A (GiB sin unidad), P-M07 A (archivos elegidos por el
   usuario), P-M08 A (cargar requiere conexión), P-M09 A (informe en CSV, Podría), P-M10 A
   (rechazar más de 100 filas), P-M11 A (columna `perfil` por fila), P-M12 A («Perfil de
   máquina»).

## D-23 · Decisiones técnicas del MVP 3 — Aprobada (2026-11-14)
Tomadas por el orquestador mientras el usuario estaba ausente; el usuario las aprobó como definitivas.
1. **Lote leído como borrador:** un lote guardado se abre aunque no cumpla las reglas del
   formulario (M1); el lector solo aplica topes anti-abuso (256 elementos, 1024 caracteres).
   Las reglas M1 se aplican al validar antes de crear. Los perfiles conservan los topes estrictos.
2. **Nada se sustituye en silencio:** un storage, bridge o nodo del lote que no existe en el
   servidor es un desajuste que el usuario resuelve. Un nodo elegido inexistente bloquea el
   resumen aunque queden otros válidos; «Nodos elegidos» se respeta también en modo básico.
3. **Cambios sin guardar (RF-G08) literal:** se pregunta también por ediciones manuales y en
   cerrar sesión y salir del lote por filas, además de cerrar, abrir, importar y cambiar de servidor.
4. **CSV exportados:** todas las celdas entre comillas (`QUOTE_ALL`) y neutralización de
   fórmulas también tras separadores internos (`, ; | tab`); el CSV de errores conserva el
   separador del archivo de origen para poder reimportarlo.
5. **Separador empatado:** se elige `,` (CA-C02.4) y se avisa de la ambigüedad.
6. **Credenciales:** ningún texto libre que parezca `usuario@realm!token` se guarda en lotes
   ni perfiles; se avisa qué campo, sin mostrar el valor.
7. **Permisos:** todo archivo que escribe la app queda 0600 (también al sobrescribir uno del
   usuario) y sus carpetas 0700 nivel a nivel.
8. **Menús:** «Lote» y «Perfiles» como menús de nivel superior (arquitectura §7).
9. **Avisos de clúster sin número de fila:** solo lleva «Fila N» el aviso de una fila que pidió
   ese nodo de forma fija. `filas_que_exceden` usa la variante voraz.

## D-24 · Alcance del MVP 4: origen del sistema operativo — Aprobada (2026-11-14)
Resuelve D-13. El usuario trabaja con ISOs (Windows y Red Hat) y discos qcow2; las OVA no le han
funcionado en Proxmox y quedan fuera.
1. **Instalar desde ISO:** catálogo de ISOs de los storages; subir desde el equipo o descargar
   desde URL al storage (si hay permisos). Asistente para Windows: segundo CD con drivers VirtIO
   y hardware adecuado (q35, UEFI, TPM cuando aplique). La instalación la termina el usuario;
   la instalación desatendida queda para después.
2. **Importar disco qcow2 (o vmdk/raw):** subirlo a un storage e importarlo al crear la MV; en
   lote, cada MV recibe su copia. Donde la API exija `root@pam` o SSH, la app lo explica y no lo hace.
3. **Clonar una plantilla** de Proxmox, pensado para lotes.
4. Se integra con perfiles (origen sugerido), lotes guardados y CSV (columna `origen`).
5. Datos de la API por versión y permisos: a confirmar por el investigador antes de los requisitos.
6. **Storage por servidor (detectar y recordar):** en cada sitio los storages para MVs, ISOs y
   discos importados tienen nombres sin convención. La app los detecta por su tipo de contenido
   (`images`, `iso`, `import`), nunca por el nombre; si hay varios candidatos pregunta una vez
   cuál usar y lo guarda en el perfil de conexión de ese servidor (editable). Si el storage
   recordado desaparece o deja de admitir ese contenido, avisa y no sustituye en silencio.
7. **Ajustes tras la investigación** (`docs/investigacion/mvp4-origen-so.md`, 2026-11-14):
   importar qcow2 solo en Proxmox ≥ 8.4 y con un storage de directorio/NFS/CIFS con el
   contenido «Import» activado por un administrador (el usuario lo activará donde haga falta;
   si no existe, la app explica cómo pedirlo); en 8.0–8.3 se explica la limitación y se ofrece
   ISO o clon. Descargar por URL en el servidor: desde 8.2 con `Sys.AccessNetwork`. virtio-win:
   descarga en el servidor si hay permiso, o ISO ya presente / subida por el usuario; la app no
   la redistribuye. Las subidas no se pueden deshacer desde la app y se comprueba antes que no
   exista un archivo con el mismo nombre.
8. **Rol `ProxLaunchCreador` ampliado** (decisión del usuario): `VM.Config.Disk`, `VM.Clone`,
   `Datastore.AllocateTemplate` y `Sys.AccessNetwork` sobre `/nodes`. Sin `Datastore.Allocate`.

## D-25 · Decisiones de los requisitos del MVP 4 — Aprobada (2026-11-14)
Requisitos en `docs/requisitos/mvp4.md`.
1. **P-O01 (usuario): clon automático.** Enlazado si el storage lo permite; si no, completo. Se avisa
   de que la plantilla queda atada a sus clones; en modo avanzado se puede forzar completo.
2. **P-O02 (usuario): 3 perfiles de fábrica nuevos** (Windows 11, Windows Server 2022/2025,
   Linux/Red Hat), solo con hardware y sin ISO. Pasan a ser 9 (modifica P-M05 de D-22).
3. **P-O03 (orquestador): hasta 3 clones enlazados simultáneos por nodo**, condicionado a la
   medición de LAB-M4-10; si hay problemas de bloqueo, 1 por nodo (D-20.5 en lo demás).
4. **Decisiones técnicas DT-O1 a DT-O17** del analista (§15 de los requisitos): aprobadas.
5. **Enmiendas** a M1, M2, M3 y al código según §14 de los requisitos (origen distinto de disco
   vacío en perfiles, lotes y CSV; escrituras del motor ampliadas con `clone`, `PUT config` y
   `resize`; `version_formato` 2 solo si hace falta; storages recordados en `PerfilConexion`;
   rol de 14 privilegios; `capacidades.py` con importación en 8.4).
6. **Aviso Red Hat 10:** RHEL/Rocky/Alma 10 exigen CPU x86-64-v3; la app avisa al elegir esas ISO
   (a confirmar en LAB-M4-05).

## D-26 · Decisiones técnicas del MVP 4 — Aprobada (2026-11-14)
Tomadas por el orquestador durante la implementación, el laboratorio (PVE 9.2) y la revisión del
MVP 4; el punto 5 fue una decisión explícita del usuario. Detalle en `docs/arquitectura/mvp4.md`
(Anexo B).
1. **Momento del diálogo de storages (desviación aceptada de C4):** la pregunta «¿Cuál usar siempre
   en este servidor?» sale al **elegir el origen ISO o disco existente** (cuando hay varios
   candidatos para los discos de las máquinas y ninguno recordado), y cuando una subida o descarga
   necesita un storage de ISO o de imágenes. **No sale al conectar ni con disco vacío**: con disco
   vacío se mantiene el comportamiento del MVP 3 (el storage con más espacio libre, sin preguntar),
   así que el flujo de M1–M3 no cambia. Sustituye lo escrito en la resolución C4 de la arquitectura.
2. **P-O03 confirmada (hasta 3 clones enlazados por nodo):** LAB-M4-10 midió 3 clones enlazados en
   paralelo en 1,1 s frente a 1,6–3,7 s en serie; el tope de 3 por nodo se mantiene. El cupo se cuenta en el **nodo de la plantilla** (donde corre la tarea `qmclone`), no
   en el nodo destino (`nodo_de_cupo`, QA-M4-08). Las copias completas y las importaciones siguen
   siendo exclusivas por nodo, con un máximo de 2 simultáneas hacia el mismo storage.
3. **`pre-enrolled-keys` del disco EFI según el SO:** `0` para Linux y «Otro» (Alpine no arranca
   con `1`, LAB-M4-04); `1` para Windows y cuando `tipo_so` no está fijado (equivale al
   comportamiento del MVP 3).
4. **virtio-win fijado a una versión con hash:** `URL_VIRTIO_WIN` apunta a la 0.1.302 (URL
   versionada, no la «stable») y `SHA256_VIRTIO_WIN` lleva su SHA-256, en `origen/constantes.py`.
   Si el ISO de drivers elegido no es esa versión, la app avisa (V-O31) y deja crear la máquina.
5. **Rol `ProxLaunchMaquinas` y guía acotada recomendada** (decisión del usuario: «Acotado + "/"
   simple»). La guía de permisos recomienda el alcance acotado: pool `plantillas-proxlaunch` con el
   rol completo y «Propagar», un segundo rol `ProxLaunchMaquinas` (los privilegios `VM.*` sin
   `VM.Clone`) en `/vms` con «Propagar», más `/storage/<almacenamiento>`, `/nodes/<nodo>`,
   `/sdn/zones/localnetwork` y `/` sin «Propagar». La alternativa simple (el rol en `/` con
   «Propagar») sigue explicada, con su riesgo. Límite conocido: `VM.Audit` no queda limitado al
   pool, así que las plantillas ajenas se ven (deshabilitadas) pero no se clonan (V-O17). SEG-M4-13
   (residuos `/var/tmp/pveupload-*` que el rol no puede borrar) queda documentado en la guía como
   limpieza periódica del administrador.
6. **Destino inválido en transferencias:** `ServicioTransferencias.subir` y `descargar` validan el
   destino (storage, nodo y nombre de archivo) **antes de tomar el cerrojo** de «una transferencia
   a la vez» y, si no es válido, lanzan `ErrorProxLaunch(PARAMETRO_INVALIDO)` sin tocar la red
   (SEG-M4-04). La interfaz recibe ese error y lo convierte en una transferencia `FALLIDA`.

## D-27 · Alcance y decisiones del MVP 5: instaladores y CI — Aprobada (2026-11-14)
Requisitos en `docs/requisitos/mvp5.md` (§14).
1. **P-E01 (usuario): solo scripts locales.** La CI queda como plantilla inactiva
   (GitHub Actions de referencia); los criterios se verifican con los scripts.
2. **P-E02 (usuario): Ubuntu solo `.deb`.** AppImage fuera del alcance.
3. **P-E03 (usuario): Windows sin firma** en este MVP; SHA-256 publicado, guía de SmartScreen
   y paso de firma preparado y desactivado (cierra el pendiente de D-06).
4. **P-E06 (usuario): al desinstalar se conservan los datos**; en Windows, casilla desmarcada
   «Borrar también mis datos». El llavero nunca se toca (borrar un perfil o desmarcar
   «Recordar credenciales» ya borra su secreto).
5. **P-E08 (usuario): iconos `.ico`/PNG generados del símbolo del logotipo aprobado**, sin
   texto ni cambios de diseño, con vista previa aprobada por el usuario antes de integrarlos.
6. **P-E09 (usuario): editor «ProxLaunch»**, sin correo real (`noreply@localhost` en el `.deb`).
7. **P-E14 (usuario): MV Windows 11 de evaluación en este equipo** (KVM/QEMU, `swtpm`, OVMF
   con Secure Boot) para construir y probar el `.exe`; se elimina sin rastro al final, como
   el laboratorio (D-15). Ubuntu 22.04/24.04 se prueban en MVs QEMU con imágenes cloud.
8. **Orquestador:** Inno Setup (ámbito elegido en el asistente, por usuario por defecto);
   artefactos en `dist/` con `SHA256SUMS`; solo amd64; SemVer, versión 0.5.0; presupuesto
   de tamaño inicial ≤ 90 MB comprimido y ≤ 250 MB instalado, a recalibrar; DT-E1 a DT-E14.

Decisiones añadidas durante la ejecución (cierre del MVP 5, 2026-11-15; detalle en
`docs/arquitectura/mvp5.md`, Anexo B):
9. **Ajuste del punto 7 (usuario): ISO de Windows 11 de consumo**, no de evaluación. La descargó el
   usuario, se verificó contra la lista «Verificar la descarga» de Microsoft y `mv.sh crear windows11`
   registra su SHA-256, URL y fecha. La MV de empaquetado corre en este equipo.
10. **Exclusión mutua con el laboratorio Proxmox (usuario).** Las MVs de empaquetado y el laboratorio no
    conviven: `mv.sh crear|arrancar` y `verificar-todo.sh` se niegan si algo escucha en
    `127.0.0.1:8006` o `:2222` o hay un proceso `aprovprox-lab` (solo lectura del estado). La exclusión
    inversa (que el laboratorio rechace arrancar con MVs de empaquetado) **no** está implementada.
11. **Instalación «para todos los usuarios» sin borrado de datos (usuario).** El desinstalador no
    pregunta «¿Borrar también mis datos?», no borra datos de ningún usuario e ignora `/BORRARDATOS=1`
    (lo anota en el registro de Inno). En la instalación por usuario se pregunta (Sí/No, predeterminado
    «No») o se usa `/BORRARDATOS=1`, y solo se borra la carpeta de ese usuario. El llavero nunca se toca.
12. **Prueba de actualización con una build que no se publica (usuario).** La actualización 0.5.0 → 0.5.1
    se prueba con una build de prueba cuya versión se cambia solo en la copia del árbol enviada a la MV;
    no va a `dist/` ni a `SHA256SUMS` y se borra al terminar.
13. **Icono, editor y firma (usuario).** Icono regenerado con revisión y aprobado (queda en
    `empaquetado/iconos/` con sumas); editor «ProxLaunch» sin correo; sin firma de código (paso
    preparado y desactivado con `PROXLAUNCH_FIRMA_CONFIG`). Se conserva el registro
    `build/registros/crear-windows11.txt`.
14. **Orquestador: las sumas solo tras verificar (INV-E6).** `SHA256SUMS` lo escribe únicamente
    `empaquetado/comun/sumas.py` en el anfitrión, con el sello `dist/.verificado-<artefacto>`; los
    scripts de construcción no lo escriben. `Categories=Network;` en el `.desktop` (nota de cambio en
    RF-E12).

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
