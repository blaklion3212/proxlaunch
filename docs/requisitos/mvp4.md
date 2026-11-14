# Requisitos del MVP 4 — ProxLaunch (origen del sistema operativo de cada MV)

Versión del documento: 1.0 (2026-11-14) · Estado: borrador para revisión del orquestador

Fuentes, en orden de autoridad: `docs/decisiones.md` (D-01 a D-24 y "Correcciones técnicas", abreviadas
**CT-n**; en especial D-14, D-15, D-20, D-21, D-22, D-23 y **D-24** puntos 1 a 8);
`docs/investigacion/mvp4-origen-so.md` (**I4**, base técnica; sus secciones se citan como I4-§A a I4-§H);
`docs/requisitos/mvp1.md` (**M1**), `mvp2.md` (**M2**) y `mvp3.md` (**M3**), vigentes salvo las enmiendas de
la sección 14; `docs/bitacora.md` («Estado actual»); y el código existente (`OrigenSO` y `ConfiguracionVM` en
`nucleo/modelos/vm.py`, `PerfilConexion` en `nucleo/modelos/conexion.py`, `nucleo/capacidades.py`,
`nucleo/constructor_peticion.py`). Si se contradicen, manda `decisiones.md`. Lo que depende de la API y no
consta en I4 ni en `tests/datos/respuestas/9.2-lab/` se marca **[LAB]** (hipótesis a verificar, sección 12) y no
puede darse por cierto; lo que es inferencia del analista y no de I4 se marca **[A]**.

Convenciones (las de M2/M3, con prefijos propios para no chocar):
- **Prioridad:** Debe / Debería / Podría.
- **IDs:** RF-Onn (requisito funcional del MVP 4), RNF-Onn, CA-Onn.y (criterio y del requisito), V-Onn (regla
  de validación), E-Onn (error), INV-On (invariante), DT-On (decisión técnica del analista, ver sección 15),
  LAB-M4-nn (prueba de laboratorio), P-Onn (pregunta abierta).
- Los criterios usan "Dado / Cuando / Entonces". "Mock" = respuesta simulada basada en respuestas reales
  (D-15); para 8.0 a 8.3 son **sintéticas** (no hay laboratorio de esas versiones). "Laboratorio" = Proxmox VE
  9.2 anidado de **un solo nodo**, storages `local` y `lab-lvmthin`, VMIDs 9000 a 9099 (D-15): lo multinodo y
  8.x se verifican solo con mocks.
- Unidades: las de M1 (discos en GiB enteros, memoria en MiB, CT-6) en el modelo y los JSON; la interfaz y el
  CSV muestran GiB.

Términos (conviene no mezclarlos):
- **Origen**: de dónde sale el sistema operativo de la MV. Valores: `disco_vacio` (M1), `iso`, `importar_disco`,
  `clonar_plantilla`. Es el campo `origen` de `ConfiguracionVM`, de los perfiles de MV, de los lotes guardados
  y de la columna `origen` del CSV.
- **Catálogo**: lista de archivos del servidor que sirven como fuente (ISOs, imágenes de disco `import`) o de
  plantillas. Se lee del servidor; nunca de un archivo local.
- **Transferencia**: subida desde el equipo o descarga por URL en el servidor de un archivo a un storage.
  Es una acción **explícita del usuario, fuera del lote** (INV-O1). No es parte de la ejecución de un lote.
- **Plantilla**: MV de Proxmox marcada como plantilla (`template: 1`). **No** es el "perfil de MV" de M3 (en la
  interfaz «Perfil de máquina», P-M12). Los textos nuevos usan «plantilla de Proxmox» y «perfil de máquina»
  de forma distinta y la guía lo aclara (RF-O32).
- **Volid**: identificador de volumen de Proxmox (`local:iso/alpine.iso`, `local:import/cirros.qcow2`).
- **Capa 1 / capa 2 de validación**: como en M3 (capa 1 sin servidor; capa 2 contra el inventario).

---

## 1. Objetivos y alcance

### 1.1 Objetivo
Que una persona sin experiencia en Proxmox cree una MV o un lote de MVs eligiendo **de dónde sale el sistema
operativo**, sin salir de ProxLaunch y sin ser administradora del servidor ni usar `root@pam` ni SSH (D-24),
con las garantías de seguridad y de deshacer que ya tienen los lotes del MVP 2 y 3.

### 1.2 Dentro del MVP 4 (D-24, puntos 1 a 8)
1. **Instalar desde ISO** (D-24.1): catálogo de ISOs de los storages; subir desde el equipo; descargar por URL
   en el servidor (≥ 8.2 con `Sys.AccessNetwork`); asistente de sistema operativo con hardware adecuado para
   Windows (CD de drivers virtio-win en `ide0`, `q35`, OVMF con `efidisk0` `4m` `pre-enrolled-keys`, TPM v2.0
   cuando aplique, `ostype`) y para Linux; orden de arranque. La instalación la termina el usuario.
2. **Importar qcow2, vmdk o raw** (D-24.2, D-24.7): solo en Proxmox ≥ 8.4 y con un storage con contenido
   «Import» activado por un administrador; una subida y N creaciones con `import-from`; una copia completa por
   MV; espacio = tamaño virtual × N; donde la API exija `root@pam`/SSH, la app lo explica y no lo hace.
3. **Clonar una plantilla** (D-24.3): enlazado o completo según storage; en paralelo; ajuste de CPU, memoria y
   disco tras clonar; plantilla por nodo si el storage es local.
4. **Integración** (D-24.4): perfiles (origen sugerido), lotes guardados, CSV (columna `origen`), simulación,
   confirmación, ejecución, rollback e informe del motor de lotes (INV-L1: ≤ 1 POST de creación por VMID; el
   clon cuenta como creación).
5. **Datos de API por versión y permisos** (D-24.5): matriz de capacidades de la sección 3 (de I4-§G).
6. **Storage por servidor** (D-24.6): detectar por contenido (`images`, `iso`, `import`), nunca por nombre;
   preguntar una vez si hay varios candidatos; recordar en el perfil de conexión (editable); si desaparece o
   deja de admitir el contenido, avisar sin sustituir.
7. **Ajustes de D-24.7**: ver RF-O09 a RF-O12 (subidas no deshacibles, nombre existente), RF-O14 (virtio-win).
8. **Rol `ProxLaunchCreador` ampliado** (D-24.8): `VM.Config.Disk`, `VM.Clone`, `Datastore.AllocateTemplate`,
   `Sys.AccessNetwork`; sin `Datastore.Allocate` (RF-O24, RF-O25).

### 1.3 Fuera del MVP 4
- OVA/OVF y migración desde VMware/ESXi (D-24); instalación desatendida (autounattend, cloud-init, kickstart).
- **Encender MVs**, abrir consola o expulsar el CD tras instalar (la guía lo explica; no hay `VM.PowerMgmt` ni
  `VM.Config.CDROM` en el rol).
- **Convertir una MV en plantilla** (`POST …/template`), **activar el contenido «Import»**, habilitar `iso` en
  un storage, **borrar** ISOs, imágenes o plantillas desde la app (INV-O4).
- Importar desde una **ruta absoluta del servidor** (exige `root@pam`, I4-§C) o desde un **storage `esxi`**.
- Clonar MVs que no son plantillas; clonar a otro nodo con storage local; clonar y migrar.
- Redistribuir la ISO de virtio-win o cualquier otro archivo dentro de la app (D-24.7).
- Compresión en la descarga por URL (`compression`); subir ISOs a todos los nodos de un clúster con una sola
  acción (DT-O11).
- Editar el CD de MVs existentes (no se pide `VM.Config.CDROM`, salvo que LAB-M4-04 demuestre lo contrario).
- LXC, HA, editar o borrar MVs existentes, monitoreo (M3 §1.2 sigue vigente).

### 1.4 Supuestos
- S-O1: la app se conecta con token o usuario/contraseña+TFA y **nunca** con `root@pam` ni SSH (D-24). Todo lo
  que exija esos medios se explica y no se intenta.
- S-O2: las MVs se siguen creando **detenidas y sin iniciar** (S-L2 de M2).
- S-O3: el contenido «Import» y los storages son decisión del administrador; la app solo los detecta (INV-O4).
- S-O4: un lote usa **un solo origen** en el modo homogéneo y **un origen por fila** en el lote por filas
  (D-22.1). Todas las MVs de un lote homogéneo comparten la misma fuente (misma ISO, misma imagen o misma
  plantilla).
- S-O5: el nodo conectado puede ser un nodo suelto o parte de un clúster; las ISOs, imágenes y plantillas pueden
  estar en storage **compartido** (visibles en todos los nodos) o **local** (solo en un nodo).
- S-O6: la subida llega al nodo que recibe la petición (I4-§B) y exige espacio libre en su sistema de ficheros
  raíz; la app no puede verlo con certeza (RF-O10).
- S-O7: la hora de cada tarea de Proxmox se sondea como en M1 RF-20; no hay porcentaje de tarea en la API
  (CT-2); los porcentajes salen del log de la tarea cuando existen [LAB].

### 1.5 Casos límite generales
- ISO de 0 bytes, de varios GiB, con nombre con espacios, acentos, mayúsculas o `,` `=`; `.img` que en realidad
  es qcow2; qcow2 con *backing file*, cifrado o truncado; vmdk de varios archivos; archivo que cambia mientras
  se sube; enlace simbólico, directorio, tubería o dispositivo en lugar de archivo.
- Volumen cuyo nombre contiene caracteres que no son `[A-Za-z0-9._-]` (puede inyectar parámetros en
  `ide2=…,media=cdrom`).
- Nombre de archivo ya existente en el storage (Proxmox sobrescribe sin avisar); creado por otro usuario justo
  entre la comprobación y la subida.
- Storage de ISOs local a un nodo y lote repartido entre varios nodos; storage de ISOs compartido NFS.
- Disco raíz del nodo lleno (`/var/tmp`): el servidor corta la conexión sin mensaje claro.
- Pérdida de red a mitad de una subida de 8 GiB; cierre de la aplicación a mitad; ticket que caduca.
- URL con usuario y contraseña (`https://u:p@…`), con `?token=…`, con redirecciones, con certificado inválido,
  sin Internet en el nodo, con `file://`, `ftp://` o IP interna.
- Plantilla con TPM, con *snapshots*, bloqueada (`lock`), en uso; dos plantillas con el mismo nombre; plantilla
  eliminada entre el catálogo y la creación; linked clones y borrado posterior de la plantilla.
- Storage recordado que cambia de contenido, de nodos o se elimina; dos candidatos con el mismo contenido.
- Lote por filas con ISO, importación y clon mezclados; fila con `origen` y `perfil` que sugieren cosas
  distintas.
- Versión forzada (avanzado) mayor que la detectada; permisos que se leen mal (`/access/permissions` falla).
- Windows con disco IDE; perfil con discos IDE y origen ISO (conflicto de ranuras `ide0`/`ide2`).

---

## 2. Usuarios y flujos

| Usuario | Qué necesita |
|---|---|
| **Usuario básico** (sin experiencia) | Elegir «cómo quiere crear la máquina» con palabras llanas, ver el catálogo, subir un ISO con barra de progreso, y que el asistente de Windows ponga el hardware correcto sin conocer q35, OVMF ni TPM. |
| **Usuario avanzado** | Control de formatos, modo de clon, bus del disco, URL con checksum, ver `ostype`, `boot` y la petición simulada. |
| **Administrador de Proxmox** | Preparar el rol ampliado, activar «Import» en un storage de directorio/NFS/CIFS y (opcional) crear plantillas. La app le explica qué hacer; no lo hace por él. |
| **Probador** | Mocks por versión (8.0 a 9.2) y laboratorio PVE 9.2 con VMIDs 9000 a 9099. |

Flujos (cada uno termina en el resumen, la confirmación y el motor de M2):
- **F-O1 ISO de Linux**: «Instalar desde un archivo ISO» → elegir ISO del catálogo → asistente de SO «Linux» →
  resumen → crear. Tras crear, el usuario enciende la MV en Proxmox e instala.
- **F-O2 Windows**: igual, con SO «Windows 11» (u otro): la app añade `ostype`, TPM, OVMF, el CD de drivers en
  `ide0` y el orden de arranque; si falta el CD de drivers, ofrece descargarlo en el servidor o subirlo.
- **F-O3 Subir ISO**: catálogo → «Subir desde mi equipo…» → archivo → nombre → comprobaciones (nombre, espacio,
  permisos) → confirmar → progreso → verificación en el catálogo.
- **F-O4 Descargar por URL**: catálogo → «Descargar en el servidor…» → URL (y checksum opcional) → metadatos
  (tamaño, nombre) → confirmar → espera (log de tarea) → verificación.
- **F-O5 Importar disco**: «Usar un disco existente» → imagen del catálogo `import` (o subirla) → N MVs → cada
  una recibe su copia → opcional ampliar disco.
- **F-O6 Clonar**: «Copiar una plantilla de Proxmox» → plantilla → modo (automático) → ajustes (CPU, memoria,
  disco) → N MVs en paralelo.
- **F-O7 CSV mixto**: columnas `origen`, `fuente`, `so` por fila → vista previa → un solo lote por filas con
  ISOs, imágenes y clones.
- **F-O8 Primer uso en un servidor**: la app detecta storages por contenido; si hay varios candidatos
  pregunta una vez y lo recuerda en el perfil de conexión.

---

## 3. Matriz de capacidades por versión (de I4-§G, ajustada a este documento)

Leyenda: Sí = disponible sin root ni SSH · Con permiso = Sí si se cumple la condición de la última columna ·
No = no hay vía por API sin root/SSH · Info = solo se muestra un mensaje.

| Capacidad (función) | 8.0 | 8.1 | 8.2 | 8.3 | 8.4 | 9.0 | 9.1 | 9.2 | Condición / permiso |
|---|---|---|---|---|---|---|---|---|---|
| Catálogo de ISOs y montar CD | Sí | Sí | Sí | Sí | Sí | Sí | Sí | Sí | `Datastore.Audit` o `AllocateSpace` en el storage del ISO |
| Subir ISO | Sí | Sí | Sí | Sí | Sí | Sí | Sí | Sí | `Datastore.AllocateTemplate`, storage con contenido `iso`, espacio en la raíz del nodo |
| Descargar ISO por URL | Con permiso | Con permiso | Con permiso | Con permiso | Con permiso | Con permiso | Con permiso | Con permiso | `AllocateTemplate` y, **desde 8.2**, `Sys.AccessNetwork` en `/nodes/{n}`; en 8.0 y 8.1 solo con `Sys.Audit`+`Sys.Modify` en `/` (la app **no** lo pide: ofrece subir; RF-O11) |
| Orden de arranque (`boot`) | Con permiso | (igual) | (igual) | (igual) | (igual) | (igual) | (igual) | (igual) | `VM.Config.Disk`; sin él se omite con aviso |
| Segundo CD en `ide0` (virtio-win) | Sí | Sí | Sí | Sí | Sí | Sí | Sí | Sí | mismo permiso que el ISO; 9.2 lo propone por defecto en su GUI |
| TPM v2.0, OVMF `4m` `pre-enrolled-keys` | Sí | Sí | Sí | Sí | Sí | Sí | Sí | Sí | `Datastore.AllocateSpace`; 9.1+ inscribe claves Microsoft 2023 (aviso informativo en versiones anteriores) |
| Importar qcow2/vmdk/raw (usar volumen `import` existente) | No (Info) | No (Info) | No (Info) | No (Info; solo si un admin coloca el archivo) | Con permiso | Con permiso | Con permiso | Con permiso | Storage `dir`/`nfs`/`cifs`/`btrfs`/`cephfs` con `import` activado por un admin; `Audit` o `AllocateSpace` en el origen y `AllocateSpace` en el destino |
| Subir imagen de disco al contenido `import` | No | No | No | No (solo OVA) | Con permiso | Con permiso | Con permiso | Con permiso | `Datastore.AllocateTemplate` |
| Descargar imagen de disco por URL a `import` | No | No | No | No | Con permiso | Con permiso | Con permiso | Con permiso | igual que descargar ISO |
| Clonar plantilla | Sí | Sí | Sí | Sí | Sí | Sí | Sí | Sí | `VM.Clone` (plantilla), `VM.Allocate` (nuevo), `Datastore.AllocateSpace`, `SDN.Use`; `VM.Audit` para listar |
| Clon enlazado | según storage | | | | | | | | `dir`/`nfs`/`cifs` con qcow2, `btrfs`, `lvmthin`, `zfspool`, `rbd`; **no** LVM grueso; mismo storage que la plantilla |
| TPM clonado | Info | Info | Info | Info | Sí (siempre completo) | Sí | Sí | Sí | a partir de 8.4 el estado TPM se clona siempre completo |
| Ajustar disco tras clonar/importar (`resize`) | Con permiso | | | | | | | | `VM.Config.Disk` + `AllocateSpace`; solo crecer |

Reglas derivadas:
- **Función de versión** (`nucleo/capacidades.py`, única tabla, CA-09.6 de M1): `Funcion.DESCARGAR_URL` desde
  (8, 2); `Funcion.IMPORTAR_DISCO` desde **(8, 4)** (la entrada de ejemplo actual (8, 2) se corrige: enmienda
  14.6); `Funcion.SUBIR_IMAGEN_DISCO` desde (8, 4). Ninguna otra parte del código compara versiones.
- **Función de permisos** (RF-O24): lo que depende de privilegios se decide con `GET /access/permissions` y
  se combina con la versión.
- 8.0–8.3 sin importación: **mensaje** (RF-O15), nunca un intento. La versión forzada (avanzado, M1 RF-26)
  cambia las capacidades efectivas; la ejecución real con versión forzada mayor que la detectada sigue
  bloqueada (V-L15).

---

## 4. Qué guarda cada artefacto sobre el origen

Se extiende la matriz de M3 §2. ✔ guarda, ✘ no guarda, ◐ guarda como pista o con condición. Nunca hay
secretos, URLs, rutas locales, host, IP ni usuario (INV-M2, INV-O6).

| Dato | Perfil de MV | Lote guardado | Lote por filas / CSV | Perfil de conexión |
|---|---|---|---|---|
| `origen` (4 valores) | ✔ (sugerido) | ✔ | ✔ por fila | ✘ |
| ISO: nombre de archivo del ISO | ◐ pista | ✔ (volid o nombre) | ✔ por fila (`fuente`) | ✘ |
| ISO: storage del ISO | ◐ pista | ✔ real | ◐ si se escribe volid | ✘ |
| `tipo_so` (asistente) | ✔ | ✔ | ✔ (`so`) | ✘ |
| CD virtio-win (sí/no, volid) | ◐ pista | ✔ | ✔ (`virtio`) | ✘ |
| Importación: nombre de la imagen / volid | ◐ pista | ✔ | ✔ (`fuente`) | ✘ |
| Importación: tamaño de ampliación | ✔ | ✔ | ✔ (`disco`) | ✘ |
| Clon: nombre de la plantilla | ◐ pista | ✔ | ✔ (`fuente`) | ✘ |
| Clon: VMID de la plantilla | ✘ | ◐ pista, se resuelve por nombre | ◐ | ✘ |
| Clon: modo (`auto`/`enlazado`/`completo`) y ajustes | ✔ | ✔ | ✔ (`modo_clon`, `cpu`, `memoria`, `disco`) | ✘ |
| URL de descarga, ruta del archivo local, checksum de transferencia | ✘ | ✘ | ✘ | ✘ |
| Storage recordado para MVs / ISOs / imágenes | ✘ | ✘ | ✘ | ✔ (3 campos opcionales) |
| Cola de transferencias, progreso, hashes calculados | ✘ | ✘ | ✘ | ✘ |

---

## 5. Requisitos funcionales

### A. El origen en el formulario

#### RF-O01 Selector de origen y modelo de datos — Debe — D-24.1 a D-24.4
`OrigenSO` pasa de un valor a cuatro: `disco_vacio`, `iso`, `importar_disco`, `clonar_plantilla`. Cada origen
distinto de `disco_vacio` lleva un **detalle** propio (qué ISO, qué imagen, qué plantilla, tipo de SO, ajustes);
la forma exacta de las clases la decide la arquitectura, pero los datos mínimos son los de la sección 4. En el
formulario, el campo se presenta como la pregunta **«¿Cómo quieres crear la máquina?»** con cuatro opciones en
lenguaje llano: «Vacía, sin sistema operativo», «Instalar desde un archivo ISO», «Usar un disco existente
(qcow2, vmdk, raw)» y «Copiar una plantilla de Proxmox».
- CA-O01.1 Dado el formulario recién abierto, entonces el origen es «Vacía» (igual que M1) y no se envía nada
  nuevo a Proxmox.
- CA-O01.2 Dado un origen no disponible (versión, permisos, falta de storage), entonces su opción aparece
  **deshabilitada con el motivo escrito debajo** (RF-O02), nunca oculta.
- CA-O01.3 Dado un cambio de origen con datos ya elegidos del anterior, entonces se pide confirmación si se
  perdería una elección (por ejemplo, la ISO) y no se pierde lo que es común (nombre, cantidad, destino,
  núcleos, memoria).
- CA-O01.4 Dado el modo básico, entonces se ve solo la pregunta, la fuente (catálogo) y, para ISO, el sistema
  operativo; bus, formato, modo de clon, `ostype` y orden de arranque quedan ocultos en básico (D-14) y su
  valor se muestra en el resumen.
- CA-O01.5 Dado cualquier origen, entonces `ConfiguracionVM.a_dict()` / `desde_dict()` hacen ida y vuelta
  (CA-18.3 de M1) y un `origen` desconocido sigue dando `PARAMETRO_INVALIDO` con el campo (CA-18.2).
- CA-O01.6 Dado el origen `iso`, `importar_disco` o `clonar_plantilla`, entonces la validación de capa 1 exige
  el detalle completo del origen (V-O01) y, si falta algo, nombra el campo.
- CA-O01.7 Dado un lote en ejecución, entonces el selector de origen está deshabilitado (M2 CA-L10.9).

#### RF-O02 Detección de capacidades y explicación de lo no disponible — Debe — D-24.5, D-24.7
Al conectar (y al cambiar de servidor o de versión forzada) la app calcula un objeto de capacidades de origen
(`CapacidadesOrigen`) con, por cada vía (ISO, subir ISO, descargar por URL, importar usar, importar subir,
clonar, orden de arranque, ampliar disco), el estado **disponible / no disponible + motivo** con un código
estable. Combina versión (tabla de la sección 3), permisos (RF-O24), storages (RF-O04) y plantillas.
- CA-O02.1 Dado un mock 9.2 con el rol ampliado y storages `iso` e `import`, entonces todas las vías están
  disponibles.
- CA-O02.2 Dado un mock 8.0, 8.1, 8.2 o 8.3, entonces «Importar disco» queda no disponible con E-O01 («Tu
  Proxmox 8.x no permite importar discos sin ser administrador del servidor. Opciones: instalar desde ISO o
  clonar una plantilla. Desde Proxmox 8.4 sí es posible.») y las otras vías no cambian.
- CA-O02.3 Dado un mock 8.4 o superior sin ningún storage visible con `import` en su contenido, entonces
  «Importar disco» queda no disponible con E-O02 («Para importar discos, pide al administrador que active el
  contenido "Import" en un almacenamiento de tipo directorio, NFS o CIFS.»), con un texto copiable para el
  administrador (RF-O32) y, si existe un storage de un tipo que sí lo admitiría (I4-§H: `dir`, `nfs`, `cifs`,
  `btrfs`, `cephfs`), el nombre del storage candidato.
- CA-O02.4 Dado un mock 8.0 o 8.1 y un usuario sin `Sys.Modify` en `/`, entonces «Descargar desde URL» no está
  disponible con E-O03 («Descargar desde una dirección web exige permisos de administrador en esta versión.
  Descarga el archivo en tu equipo y súbelo.») y «Subir desde mi equipo» sí lo está.
- CA-O02.5 Dado un mock 8.2 o superior con `Sys.AccessNetwork` en `/nodes/{n}`, o con `Sys.Modify` en `/`
  (administrador), entonces «Descargar desde URL» está disponible en ese nodo.
- CA-O02.6 Dado que `GET /access/permissions` falla, entonces los permisos quedan «desconocidos»: las vías que
  los necesitan se ofrecen con el aviso «No se pudieron comprobar tus permisos», con excepción de los
  parámetros opcionales (`boot`, `resize`), que se omiten (RF-O24).
- CA-O02.7 Dado un cambio de versión forzada (avanzado), entonces el objeto se recalcula con las capacidades
  forzadas y la interfaz lo etiqueta como en M2 CA-L11.6.
- CA-O02.8 Dado el cálculo de capacidades, entonces solo emite lecturas (INV-M1) y no tarda más de 2 s con el
  inventario mock de 3 nodos y 200 volúmenes (RNF-O13).
- CA-O02.9 Cada motivo de no disponibilidad tiene un código estable, un texto traducible y un identificador
  de ayuda (RNF-O07).

#### RF-O03 Compatibilidad hacia atrás — Debe — M1, M2, M3
- CA-O03.1 Dado el origen «Vacía» (valor por defecto), entonces el `POST` por MV es **idéntico** al del MVP 3
  para la misma entrada (test de equivalencia sobre las suites de M1, M2 y M3, como CA-P12.1).
- CA-O03.2 Dado un perfil, lote guardado o CSV de MVP 3 (todos con `origen = disco_vacio` o sin la columna), entonces
  se cargan sin cambios y sin avisos nuevos.
- CA-O03.3 Dado un `perfiles.json` del MVP 3 sin los campos de storage recordado, entonces carga y los campos
  valen `None`.
- CA-O03.4 Dado un lote cuya ejecución ya estaba en curso en la sesión, entonces cambiar de versión de
  `OrigenSO` no afecta al libro ni al informe (los datos del libro son los de MVP 2).

### B. Storages por servidor (detectar y recordar)

#### RF-O04 Detección de storages por contenido — Debe — D-24.6
La app clasifica los storages de cada nodo por su **contenido configurado**: candidatos para MVs (`images`), para
ISOs (`iso`) y para imágenes de disco (`import`). **Nunca por el nombre.** Un candidato debe estar activo y
habilitado en el nodo y visible para el usuario (`Datastore.Audit` o `AllocateSpace`). Para decidir qué tipos
podrían llevar un contenido que aún no está activado se usa la tabla por tipo de I4-§H (solo para el mensaje de
RF-O02; la lista de candidatos para usar sale solo del contenido configurado).
- CA-O04.1 Dado un storage con `content = "iso,backup"`, entonces es candidato para ISOs y no para MVs.
- CA-O04.2 Dado dos storages con nombres engañosos (`iso` con solo `images`; `discos` con solo `iso`), entonces
  se clasifican por su contenido, no por su nombre (test).
- CA-O04.3 Dado un storage inactivo (`active = 0`), deshabilitado o inexistente en un nodo, entonces no es
  candidato en ese nodo.
- CA-O04.4 Dado un clúster con storages compartidos y locales, entonces para cada candidato se registra en qué
  nodos está activo y si es compartido; la elegibilidad por nodo (V-O25) usa ese dato.
- CA-O04.5 Dado el campo `content` ausente en una respuesta antigua, entonces el storage no es candidato y no
  hay excepción.
- CA-O04.6 Dado `GET /nodes/{n}/storage?format=1`, entonces los formatos admitidos por storage se toman de la
  respuesta cuando existen y solo si no, de la tabla fija de V-09 (hallazgo de I4-§H para LVM grueso 9.0+).
- CA-O04.7 La clasificación es una función pura sobre el inventario (RNF-O13).

#### RF-O05 Elegir y recordar el storage por servidor — Debe — D-24.6
Tres elecciones opcionales por servidor: `storage_mv` (`images`), `storage_iso` (`iso`) y `storage_import`
(`import`). Se guardan en el **perfil de conexión** (`PerfilConexion`, `perfiles.json`) como campos opcionales
con valor `None` por defecto. Solo se guardan nombres de storage (no son secretos).
- CA-O05.1 Dado exactamente **un** candidato para un contenido, entonces se usa sin preguntar y **no** se guarda
  (se redetecta en cada conexión).
- CA-O05.2 Dado **varios** candidatos y ninguno recordado, entonces al necesitar ese contenido la app pregunta
  una vez («Hay varios almacenamientos para X. ¿Cuál usar siempre en este servidor?») con casilla «Recordar mi
  elección», marcada por defecto, y lo guarda en el perfil de conexión del servidor activo.
- CA-O05.3 Dado un storage recordado y vigente, entonces se usa sin preguntar y es el valor por defecto de los
  discos de la MV, del `efidisk0`/TPM y de la subida de ISO/imágenes.
- CA-O05.4 Dado el diálogo de edición del perfil de conexión, entonces muestra los tres campos como listas
  desplegables con los candidatos del servidor conectado, «Detectar automáticamente» (valor `None`) y el valor
  actual aunque ya no esté disponible (marcado «no disponible»); editable en modo avanzado y visible como texto
  en básico.
- CA-O05.5 Orden de precedencia del storage de un disco, de menor a mayor: mayor espacio libre (MVP 1) →
  recordado del perfil de conexión → pista del perfil de MV (RF-P06 de M3) → valor del lote guardado o columna
  del CSV. Un test de propiedad lo comprueba.
- CA-O05.6 Dado un usuario sin storages recordados y con un solo candidato de cada contenido, entonces el
  comportamiento es el del MVP 3 (CA-O03.1).
- CA-O05.7 Dado el cambio de servidor (otro perfil de conexión), entonces se usan los recordados de ese perfil;
  nunca se arrastran los de otro.
- CA-O05.8 Dado el archivo `perfiles.json`, entonces la escritura sigue siendo atómica y con permisos 0600/0700,
  sin secretos, y el centinela de RNF-O06 no aparece (RF-07 de M1).
- CA-O05.9 Eliminar un perfil de conexión elimina sus storages recordados (están dentro del perfil).
- CA-O05.10 Dado un clúster, el storage recordado se guarda por nombre de storage (único en el clúster), no por
  nodo.

#### RF-O06 Storage recordado que desaparece — Debe — D-24.6, D-23.2
- CA-O06.1 Dado un storage recordado que ya no existe, está inactivo, ya no tiene el contenido o no está en
  el nodo del lote, entonces la app **avisa** con E-O04 («El almacenamiento «X» que usabas en este servidor
  ya no está disponible o ya no admite {contenido}. Elige otro.») y **no** lo sustituye en silencio ni
  automáticamente.
- CA-O06.2 Dado el aviso, entonces ofrece «Elegir otro…» (lista de candidatos actuales) y «Dejar de recordar»;
  el valor recordado no se borra hasta que el usuario lo cambie.
- CA-O06.3 Mientras el recordado no está disponible, el resumen no se genera si el origen lo necesita
  (V-O26 bloquea) y el campo muestra el error; si el origen no lo necesita, solo hay aviso.
- CA-O06.4 Dado un lote guardado o fila CSV con un storage explícito inexistente, entonces vale M3 RF-G04
  (E-M15 y «Usar otro…»).
- CA-O06.5 Dado que el recordado vuelve a existir (el admin lo reactivó), entonces se vuelve a usar sin
  preguntar.

### C. Instalar desde ISO

#### RF-O07 Catálogo de ISOs — Debe — D-24.1
La app lista los ISOs de los storages candidatos (`GET /nodes/{n}/storage/{s}/content?content=iso`) y los
muestra con nombre, storage, tamaño legible y fecha. El usuario elige uno.
- CA-O07.1 Dado el catálogo, entonces se lista por cada storage con contenido `iso` visible en el nodo
  efectivo del formulario (o en cada nodo elegible del lote) y se ordena por nombre.
- CA-O07.2 Dado un volumen con extensión distinta de `.iso`/`.img` o cuyo nombre no cumple V-O02, entonces
  aparece **deshabilitado** con el motivo («Nombre no admitido: solo letras, números, punto, guion y guion
  bajo») y no se puede elegir.
- CA-O07.3 Dado un lote con destino «Automático» o varios nodos y un ISO en storage **local**, entonces la
  elegibilidad (V-O25) excluye con explicación a los nodos sin ese ISO; dado un ISO en storage compartido,
  entonces es elegible en todos.
- CA-O07.4 Dado un catálogo de hasta 500 volúmenes, entonces se lista en ≤ 2 s con mock de latencia normal y
  fuera del hilo de la interfaz (RNF-O13).
- CA-O07.5 Dado un error o 403 al listar un storage, entonces se muestra E-O05 por storage («No puedes ver
  los ISOs de «X»: falta el permiso Datastore.Audit o Datastore.AllocateSpace») y los demás storages se
  listan igual.
- CA-O07.6 Dado un ISO elegido que desaparece antes de crear, entonces la reconsulta previa del lote (INV-O8)
  da V-O02 y la MV no se envía.
- CA-O07.7 Dado el listado, entonces solo se hacen lecturas (INV-M1) y el nombre, volid y notas del volumen se
  tratan como texto no confiable (se escapan al mostrarlos, CA-C11.4 de M3).
- CA-O07.8 Dado el catálogo vacío, entonces el texto lleva a «Subir desde mi equipo…» y, si procede,
  «Descargar en el servidor…».

#### RF-O08 Montaje del ISO, bus y orden de arranque — Debe — D-24.1
El ISO se monta como CD en `ide2` con `media=cdrom` (obligatorio, I4-§A). Orden de arranque:
`boot=order=<primer disco>;ide2[;net0]` (DT-O1). Los CD usan `ide0` y `ide2`; los discos de la MV con bus IDE
usan solo las ranuras libres `ide1` e `ide3` (DT-O2).
- CA-O08.1 Dado origen `iso` con volid `local:iso/alpine.iso`, entonces la petición contiene
  `ide2=local:iso/alpine.iso,media=cdrom` y nunca un ISO sin `media=cdrom`.
- CA-O08.2 Dado origen `iso`, un disco `scsi0` y una red, entonces la petición contiene
  `boot=order=scsi0;ide2;net0`; sin red, `boot=order=scsi0;ide2`; sin disco (`con_disco = false`),
  `boot=order=ide2[;net0]` y un aviso «Sin disco no podrás instalar el sistema».
- CA-O08.3 Dado que el usuario **no** tiene `VM.Config.Disk` (o está desconocido), entonces el parámetro
  `boot` se **omite**, la MV se crea igualmente y el resumen avisa «Sin el permiso VM.Config.Disk no se puede
  fijar el orden de arranque: la máquina arrancará primero del CD. Tras instalar, ajusta el orden en Proxmox»
  (V-O18). Nunca se envía `boot` sin la certeza del permiso, porque un 403 en el `POST` fallaría la MV entera
  (INV-L1).
- CA-O08.4 Dado un perfil con discos IDE y origen `iso`, entonces el primer disco IDE usa `ide1` y el
  segundo `ide3`; con más de dos discos IDE, V-O06 da error. Con origen distinto de `iso` sin virtio-win, la
  numeración IDE no cambia (equivalencia con MVP 3).
- CA-O08.5 Dado el valor del volid, entonces solo se inserta en la petición si cumple la lista blanca de
  V-O02 (sin `,` `=` `;` espacios ni saltos de línea) y `construir_parametros` lo comprueba otra vez
  (defensa en profundidad; test de inyección con `x.iso,media=disk` y `x.iso,ide0=…`).
- CA-O08.6 Dado el origen `iso` y un nodo cuyo storage del ISO no está activo, entonces V-O25 lo excluye.
- CA-O08.7 Dado el origen `iso` con firmware OVMF (por defecto del asistente de Windows), entonces el comportamiento
  de arranque con disco vacío es el confirmado en LAB-M4-04; si LAB-M4-04 muestra que el instalador no arranca
  con `order=scsi0;ide2`, la constante pasa a `order=ide2;scsi0` (una sola constante, DT-O1).
- CA-O08.8 Dado el origen `iso`, entonces no se envía `VM.Config.CDROM` como exigencia (no está en el rol) y
  LAB-M4-04 comprueba que la creación funciona sin él.
- CA-O08.9 El resumen muestra «Montará el ISO «x.iso» como CD» y el orden de arranque, y dice que la app
  **no enciende** la MV.

#### RF-O09 Subir un ISO desde el equipo — Debe — D-24.1, D-24.7
Acción «Subir desde mi equipo…» del catálogo (RF-O07). Usa `POST /nodes/{n}/storage/{s}/upload` con
`content=iso`, `filename` (con `Content-Type`, I4-§B), `checksum` sha256 y `checksum-algorithm=sha256`
calculados localmente (DT-O3), por streaming (RNF-O01), en el nodo definido por DT-O4.
- CA-O09.1 Dado un archivo local válido (V-O10), un nombre válido (V-O09) y permisos (V-O15), cuando el usuario
  confirma, entonces se envía **una** petición `POST …/upload` con `content=iso`, el `checksum` y su
  algoritmo, y el archivo como parte multipart con `Content-Type: application/octet-stream`.
- CA-O09.2 Dado el diálogo de subida, entonces muestra antes de confirmar: nombre final, tamaño, storage y
  nodo destino, y el texto **«Esta subida no se puede deshacer desde ProxLaunch (requeriría un permiso de
  administrador). Si te equivocas, pídele al administrador que borre el archivo.»** (RF-O25), con botón
  "Subir" y "Cancelar" (foco inicial en Cancelar).
- CA-O09.3 Dado que el servidor devuelve un UPID, entonces la app sondea la tarea `imgcopy` hasta `OK` o
  error, y solo entonces considera la subida terminada.
- CA-O09.4 Dado el fin con éxito, entonces la app **verifica** que el volid aparece en el catálogo con el
  tamaño local; si no aparece o el tamaño difiere, es E-O06 («El servidor dice que terminó, pero el archivo no
  coincide. No lo uses.») y no se selecciona automáticamente.
- CA-O09.5 Dado un fallo de checksum del servidor (tarea fallida), entonces E-O07 («El archivo llegó dañado:
  la huella no coincide. No quedó guardado») y la app comprueba que el volid no existe; si existe, avisa.
- CA-O09.6 Dado el éxito, entonces el ISO queda seleccionado en el catálogo y el formulario conserva sus datos.
- CA-O09.7 Dado que se pierde la conexión durante la subida, entonces E-O08 («Se cortó la conexión mientras
  se subía el archivo.»), **sin reintento automático** y se ofrece "Reintentar" (tras comprobar de nuevo el
  nombre, RF-O10); el estado del servidor se verifica con el catálogo (no se asume).
- CA-O09.8 Dado un archivo que cambia de tamaño o fecha entre el cálculo del hash y el fin de la subida, entonces
  la subida se aborta con E-O09 («El archivo cambió mientras se subía») sin dar la subida por buena.
- CA-O09.9 Dado un token y una contraseña+ticket, entonces la subida funciona con ambos métodos de
  autenticación (en el ticket va la cabecera `CSRFPreventionToken`); LAB-M4-03 verifica con **token**.
- CA-O09.10 La subida usa la misma sesión HTTP, huella fija y sin proxy (D-10, D-18) y ninguna otra
  conexión.
- CA-O09.11 Dado un lote en ejecución o una simulación, entonces "Subir" está deshabilitado (V-O27).
- CA-O09.12 El nombre del archivo subido se propone a partir del nombre local, saneado a la lista blanca de
  V-O09; el usuario puede cambiarlo. El servidor "normaliza" el nombre: la app comprueba tras subir que el
  volid esperado existe y, si no, muestra el volid real devuelto por el catálogo.

#### RF-O10 Comprobaciones previas a subir o descargar — Debe — D-24.7
Antes de enviar bytes, la app comprueba tres cosas y bloquea o avisa:
- CA-O10.1 **Nombre existente (bloquea):** dado que el catálogo del storage destino ya tiene el volid, entonces
  V-O14 / E-O10 («Ya existe un archivo con ese nombre en «X». Proxmox lo sobrescribiría. Usa el que ya está o
  elige otro nombre.») y se ofrecen "Usar el existente" (por defecto) y "Cambiar el nombre". **Nunca** hay
  opción de sobrescribir (INV-O2).
- CA-O10.2 El nombre se vuelve a comprobar **justo antes** de enviar el primer byte (no solo al abrir el
  diálogo). Un volid que aparece entre la última comprobación y el `POST` es un riesgo residual
  documentado (sección 14), no un error de la app.
- CA-O10.3 **Espacio en el storage (bloquea):** dado un archivo mayor que `avail` del storage destino (o de
  `avail` − `RESERVA_STORAGE_MIB`), entonces V-O13 bloquea con «El archivo pesa X y «S» solo tiene Y libres».
- CA-O10.4 **Espacio en el nodo (avisa):** dado `GET /nodes/{n}/status` (`rootfs.avail`, `Sys.Audit` del rol)
  menor que el tamaño del archivo + `RESERVA_RAIZ_MIB`, entonces aviso con casilla «Entiendo que la subida puede
  fallar»; la comprobación es aviso y no bloqueo porque `/var/tmp` puede estar en otro sistema de
  ficheros [LAB]. Si el endpoint no devuelve el dato, no se avisa.
- CA-O10.5 **Permisos:** dado `AllocateTemplate` ausente en `/storage/{s}` (comprobado en
  `/access/permissions`), entonces la acción "Subir" ya está deshabilitada con motivo (RF-O24) y no se llega a
  enviar nada.
- CA-O10.6 Las tres comprobaciones usan solo lecturas (INV-M1).
- CA-O10.7 Dado un volid con mayúsculas/minúsculas distintas de uno existente, entonces se trata como
  distinto solo si el storage es sensible a mayúsculas; ante la duda (NFS/CIFS/Windows) se considera existente
  sin distinguir mayúsculas.
- CA-O10.8 Dado un nombre que el servidor "normalizaría" (caracteres fuera de la lista blanca), entonces la app
  nunca lo envía: V-O09 lo impide y propone el nombre saneado.

#### RF-O11 Descargar por URL en el servidor — Debe — D-24.1, D-24.7
Acción «Descargar en el servidor…» (`POST /nodes/{n}/storage/{s}/download-url`, `GET /nodes/{n}/query-url-metadata`).
Disponible según la matriz de la sección 3 (RF-O02, CA-O02.4/5). Aplica a ISOs y, con importación disponible, a
imágenes de disco (RF-O16).
- CA-O11.1 Dado una URL, cuando el usuario pulsa "Comprobar", entonces la app llama a
  `query-url-metadata` y muestra nombre de archivo, tamaño y tipo que **el servidor** ve; **la app no abre
  ninguna conexión a esa URL** (RNF-O05).
- CA-O11.2 Dado V-O11 (URL), V-O12 (checksum), V-O09 (nombre), V-O13/V-O14 (espacio y nombre existente) y
  permisos (V-O15, V-O16), cuando el usuario confirma, entonces se envía **una** petición `download-url` con
  `url`, `content`, `filename`, `verify-certificates=1` y, si se dio, `checksum` + `checksum-algorithm`.
- CA-O11.3 Dado el esquema `http://`, entonces en modo básico se rechaza («Usa una dirección https://») y
  en avanzado se permite con confirmación explícita y el aviso «No se puede garantizar que el archivo no fue
  alterado» (DT-O7); se recomienda checksum.
- CA-O11.4 Dado `verify-certificates`, entonces el valor por defecto es verificar; desmarcarlo solo existe en
  modo avanzado, con confirmación y registro del hecho (sin la URL) en el log.
- CA-O11.5 Dado que la tarea `download` está en curso, entonces la app muestra el progreso leyendo el log de
  la tarea si trae porcentaje/bytes [LAB-M4-06]; si no, muestra tiempo transcurrido y estado indeterminado.
- CA-O11.6 Dado el fin de la tarea, entonces se verifica el volid en el catálogo (CA-O09.4) y se aplica el
  mismo tratamiento de errores (E-O06, E-O07).
- CA-O11.7 Dado que la tarea falla (sin Internet en el nodo, 404, certificado inválido, checksum), entonces
  E-O11 muestra la causa sin la URL completa (host y archivo) y sugiere subir el archivo desde el equipo.
- CA-O11.8 Dado que el usuario pulsa "Dejar de esperar", entonces la app deja de sondear, avisa «La descarga
  sigue en el servidor y no se puede cancelar desde ProxLaunch», y al volver a abrir el catálogo se verá el
  resultado (no hay `Sys.Modify` en el rol para detener la tarea).
- CA-O11.9 Dado 8.0 o 8.1 sin permiso de administrador, entonces la acción no existe (CA-O02.4); la app **no**
  ofrece pedir `Sys.Modify` en `/`.
- CA-O11.10 La URL no se escribe en ningún archivo, log ni mensaje de error (INV-O6); el log guarda el host y el
  nombre de archivo.
- CA-O11.11 Dado un checksum con algoritmo no admitido, o una longitud que no corresponde a ninguno (V-O12),
  entonces error de campo antes de enviar.

#### RF-O12 Progreso, cancelación y verificación de transferencias — Debe — RNF-O02, RNF-O03
Una **cola de una sola transferencia a la vez** (V-O27) con estados: *calculando huella → comprobando →
subiendo/descargando → verificando → terminada | cancelada | fallida*.
- CA-O12.1 Dado una subida, entonces la barra muestra bytes enviados / total, velocidad y tiempo restante,
  actualizada ≥ 1 vez por segundo y sin congelar la interfaz (RNF-O02).
- CA-O12.2 Dado "Cancelar", entonces la subida se interrumpe en ≤ 2 s cerrando la conexión; la app
  **verifica en el catálogo** que no quedó el volid y avisa del resultado («Se canceló. No se guardó ningún
  archivo.» / «Se canceló, pero el archivo parcial quedó guardado: pide al administrador que lo borre»);
  lo anterior [LAB-M4-03] decide cuál se muestra.
- CA-O12.3 Dado la cancelación durante "calculando huella", entonces se detiene la lectura del archivo y no se
  envía nada.
- CA-O12.4 Dado el cierre de la aplicación con una transferencia activa, entonces se pide confirmación
  («Hay una subida en curso. Si cierras, se cancelará») y, si confirma, se cancela como en CA-O12.2.
- CA-O12.5 Dado el estado de cada barra de progreso, entonces tiene nombre accesible, valor numérico y texto
  de estado (no solo color) (RNF-O08).
- CA-O12.6 Dado una subida que no avanza durante `PARO_SIN_PROGRESO_S` (120 s), entonces se aborta con E-O08
  y no queda a la espera indefinida.
- CA-O12.7 Dado el resultado, entonces se registra en el log: nombre de archivo, tamaño, storage, nodo,
  duración y código; nunca la ruta local completa, la URL, el hash del contenido ni cabeceras (RNF-O06).
- CA-O12.8 Dado una transferencia terminada, entonces el catálogo se recarga y el elemento nuevo queda
  seleccionado; dado una fallida, el formulario no cambia.
- CA-O12.9 Dado una transferencia en curso y la generación del resumen de un lote, entonces el resumen exige que
  haya terminado o se haya cancelado (V-O27); no se mezclan.

### D. Asistente de sistema operativo (Linux y Windows)

#### RF-O13 Asistente de sistema operativo y hardware recomendado — Debe — D-24.1
Con origen `iso` el usuario elige el **sistema operativo** (`tipo_so`): `linux`, `windows_11`,
`windows_server_2022_2025`, `windows_10`, `windows_server_2016_2019`, `otro`. La elección fija el hardware
recomendado (I4-§E) y se muestra en el resumen. Valores de la tabla (DT-O5, DT-O6):

| `tipo_so` | `ostype` | Firmware / máquina | TPM v2.0 | CD virtio-win | Notas |
|---|---|---|---|---|---|
| `linux` | `l26` | el del perfil (SeaBIOS u OVMF) | no | no | `scsihw=virtio-scsi-single`, red `virtio` |
| `windows_11` | `win11` | OVMF + `q35` + `efidisk0` `4m` `pre-enrolled-keys=1` | **sí** (obligatorio) | sí | disco `scsi0` con `iothread`/`discard`, red `virtio`, `agent=1` |
| `windows_server_2022_2025` | `win11` | igual | sí (DT-O6) | sí | igual |
| `windows_10` | `win10` | OVMF + `q35` (DT-O5) | no | sí | igual |
| `windows_server_2016_2019` | `win10` | OVMF + `q35` | no | sí | igual |
| `otro` | `other` | el del perfil | no | no | sin cambios |

- CA-O13.1 Dado `windows_11`, entonces la petición contiene `ostype=win11`, `bios=ovmf`, `machine=q35`, un
  `efidisk0=<st>:1,efitype=4m,pre-enrolled-keys=1…` (ya generado por `construir_parametros`),
  `tpmstate0=<st>:1,version=v2.0` (siempre con `version=v2.0`: el valor por defecto de Proxmox es `v1.2`),
  `scsihw=virtio-scsi-single`, `net0=virtio,bridge=…` y `agent=1`.
- CA-O13.2 Dado `windows_10` o `windows_server_2016_2019`, entonces `ostype=win10` y no hay `tpmstate0`
  (el usuario avanzado puede añadirlo).
- CA-O13.3 Dado `linux`, entonces `ostype=l26`, sin TPM ni CD de drivers; el firmware lo decide el perfil.
- CA-O13.4 Dado `linux` y el texto de ayuda, entonces el asistente avisa «Si instalas Red Hat Enterprise Linux 10
  (o Rocky/AlmaLinux 10) elige el tipo de CPU x86-64-v3; con el valor por defecto x86-64-v2-AES no arrancará»
  **[A]: dato no verificado en I4; confirmar con LAB-M4-05 si hay ISO disponible** y ofrece el botón
  «Usar x86-64-v3» (avanzado: campo `tipo_cpu`, validado por formato V-22 y, si existe, por el catálogo de CPU de
  M3 S-M9).
- CA-O13.5 Dado el almacenamiento del `tpmstate0`, entonces es el storage del `efidisk0`
  (`storage_efi_efectivo`) y, si el storage no admite `images`, V-17 de M1 bloquea; el estado TPM no lleva
  `format` (DT-O8).
- CA-O13.6 Dado Windows 11 con SeaBIOS o sin TPM (usuario avanzado), entonces V-O05 da error («Windows 11 exige
  arranque UEFI y TPM 2.0»). Para los demás Windows, SeaBIOS es un aviso.
- CA-O13.7 Dado un Windows con mínimos de Microsoft por debajo de los del formulario (V-O07), entonces aviso no
  bloqueante («Windows 11 pide al menos 2 núcleos, 4 GiB de memoria y 64 GiB de disco»); no se cambian los
  valores del usuario.
- CA-O13.8 Dado el modo básico, entonces el usuario elige solo el sistema operativo; el resto se aplica y se
  lista en el resumen (M1 CA-24.5); en avanzado puede cambiar bus, firmware, `ostype`, TPM y `agent`.
- CA-O13.9 Dado el asistente aplicado sobre un perfil con valores propios (núcleos, memoria, discos), entonces
  **no** cambia núcleos, memoria ni tamaños; sí fuerza lo de la tabla (firmware, `ostype`, TPM, controlador
  SCSI, modelo de red, bus del primer disco SCSI) y avisa de cada campo que cambió («El asistente cambió el
  firmware a UEFI»).
- CA-O13.10 Dado un disco de Windows con bus `scsi` o `virtio`, entonces el resumen y la ayuda avisan
  que durante la instalación hay que cargar el controlador desde el CD de drivers (RF-O14); la opción
  «Compatible: disco SATA, no necesita controlador» existe en avanzado como alternativa (DT-O9).
- CA-O13.11 Dado `agent=1`, entonces se envía solo para Windows y Linux (no para `otro`) y requiere
  `VM.Config.Options` (en el rol).
- CA-O13.12 Dado el asistente, entonces la combinación se valida con las reglas V-05..V-17 de M1 existentes y
  V-O05..V-O08; no hay reglas duplicadas.
- CA-O13.13 Dado una versión de Proxmox antigua (8.0), entonces los parámetros usados (`ostype=win11`,
  `efitype=4m`, `tpmstate0 version=v2.0`) están todos en 8.0 (I4-§E); un mock sintético 8.0 los acepta.

#### RF-O14 Drivers virtio-win — Debe — D-24.1, D-24.7
Con `tipo_so` de Windows, el CD virtio-win se monta en `ide0` con `media=cdrom` (I4-§A). La app **no
redistribuye** la ISO (D-24.7).
- CA-O14.1 Dado un Windows y un ISO de virtio-win ya presente en un storage `iso` visible (nombre que empieza por
  `virtio-win` y termina en `.iso`), entonces se propone como CD de drivers (editable) y se monta en `ide0`.
- CA-O14.2 Dado ninguno presente, entonces el asistente ofrece **tres caminos**: (a) «Descargarlo en el
  servidor» si hay permiso (RF-O11) con la URL fija de la constante `URL_VIRTIO_WIN` y su checksum de la
  constante `SHA256_VIRTIO_WIN` (DT-O10); (b) «Ya lo tengo en mi equipo» (subida, RF-O09); (c) «Crear sin los
  drivers» con aviso («Sin los drivers, Windows no verá el disco VirtIO ni la red»).
- CA-O14.3 Dado «crear sin los drivers», entonces la MV se crea sin `ide0` y el resumen lo marca como aviso
  persistente (no bloquea).
- CA-O14.4 Dado el lote de N MVs Windows, entonces **todas** montan el mismo CD de drivers y es una sola
  descarga/subida (no una por MV).
- CA-O14.5 Dado que la ISO de drivers vive en un storage local de un nodo, entonces V-O25 excluye a los nodos
  sin ella (igual que RF-O07).
- CA-O14.6 La constante `URL_VIRTIO_WIN` apunta a una versión **fija** verificada (no a `latest`), con su
  checksum sha256; LAB-M4-07 obtiene el tamaño con `query-url-metadata`, descarga y fija el checksum
  (DT-O10). Si el checksum no coincide, E-O07.
- CA-O14.7 Dado el aviso de versiones con problemas conocidas de virtio-win (por ejemplo 0.1.285 con Server 2025
  y E/S intensa, I4-§E), la constante apunta a una versión sin problemas conocidos y la guía indica cómo
  cambiarla (el administrador puede subir otra).
- CA-O14.8 Dado el SO de Windows, entonces el resumen muestra la ruta de drivers que el usuario cargará
  (`vioscsi\w11\amd64` o `w10`, `NetKVM`, `Balloon`) en la ayuda, no como parámetro.
- CA-O14.9 Dado un volid virtio-win elegido a mano, entonces cumple V-O02 igual que el ISO del SO.

### E. Importar un disco existente

#### RF-O15 Requisitos y mensajes de la importación — Debe — D-24.2, D-24.7
La opción «Usar un disco existente» solo está disponible si se cumple RF-O02 (versión ≥ 8.4, storage con
`import`, permisos). Si no, se explica (E-O01, E-O02, E-O12).
- CA-O15.1 Dado 8.0 a 8.3, entonces se aplica CA-O02.2 y **no se intenta** ninguna petición de importación
  (ni siquiera con un truco de renombrar a `.img`, I4-§C).
- CA-O15.2 Dado ≥ 8.4 y storage `import` activo pero usuario sin `Datastore.AllocateSpace` en el storage
  destino de MVs, entonces V-O19 / E-O13 («Para guardar el disco importado necesitas el permiso
  Datastore.AllocateSpace en «S»»).
- CA-O15.3 Dado cualquier imagen del catálogo `import`, entonces solo se acepta como fuente un volid
  `storage:import/<archivo>` de la lista blanca (V-O03); **nunca** una ruta absoluta (exige `root@pam`,
  I4-§C): si el usuario la escribe, E-O14 («Importar desde una ruta del servidor exige ser administrador
  (root). Sube el archivo desde tu equipo.»).
- CA-O15.4 Dado el origen `importar_disco`, entonces `con_disco = true` es obligatorio: la imagen es el
  primer disco de la MV y no hay opción de "sin disco".
- CA-O15.5 Dado el origen `importar_disco`, entonces el firmware, la red y el cómputo son los del formulario;
  el asistente de SO de RF-O13 también puede aplicarse (el disco importado puede ser Windows) con las mismas
  reglas, pero **sin** ISO ni CD de instalación.
- CA-O15.6 Dado que el contenido `import` lo activa un administrador, entonces la app **no** ofrece activarlo
  (INV-O4) y el texto de E-O02 trae un párrafo copiable para el administrador (Datacenter → Almacenamiento →
  editar → Contenido → Import).

#### RF-O16 Catálogo y subida de imágenes de disco — Debe — D-24.2
Catálogo de `content=import` análogo al de ISOs (RF-O07) con extensiones `.qcow2`, `.raw`, `.vmdk`; subida
desde el equipo (RF-O09) y descarga por URL (RF-O11) con `content=import`. **Un solo archivo subido por
lote** (D-24.2).
- CA-O16.1 Dado un archivo local, entonces V-O10 comprueba la extensión **y el contenido**: qcow2 (firma `QFI\xfb`,
  versión 2 o 3), vmdk (firma `KDMV`, un solo archivo monolítico o *streamOptimized*), raw (cualquier otro
  contenido con extensión `.raw` o `.img` aceptada con aviso). La extensión del nombre que se sube
  se corrige a la del contenido detectado (un `.img` qcow2 se propone como `.qcow2`, DT-O12).
- CA-O16.2 Dado un qcow2 con *backing file* (`backing_file_offset ≠ 0`) o cifrado (`crypt_method ≠ 0`), o un
  vmdk de varios archivos (descriptor de texto), entonces V-O10 los rechaza con E-O15 («Este disco depende
  de otro archivo o está cifrado. Conviértelo a un solo archivo qcow2 sin dependencias antes de subirlo»)
  **antes de subir**; Proxmox los rechazaría también (`untrusted`, I4-§B).
- CA-O16.3 Dado `.ova`/`.ovf`, entonces el diálogo explica que las OVA están fuera del alcance (D-24) y no
  se sube.
- CA-O16.4 Dado un qcow2/vmdk, entonces la app lee de la **cabecera** su tamaño virtual (qcow2: bytes
  24 a 31; vmdk: capacidad en sectores) leyendo solo los primeros bytes (≤ 1 KiB), y lo guarda en la sesión
  como `tamano_virtual` del volumen subido (RF-O18).
- CA-O16.5 Dado un raw, entonces su tamaño virtual es el tamaño del archivo.
- CA-O16.6 Dado el listado del servidor, entonces la columna «Tamaño» muestra lo que devuelve la API y la
  columna «Tamaño del disco» solo si se conoce (sesión o API [LAB-M4-08]); si no, "desconocido".
- CA-O16.7 Dado el contenido `import` en un storage `dir`, `nfs`, `cifs`, `btrfs` o `cephfs`, entonces es
  candidato; un storage `esxi` **no** se ofrece (fuera de alcance).
- CA-O16.8 Todo lo demás de la subida (nombre existente, espacio, checksum, progreso, cancelación, no
  deshacer) es RF-O09 a RF-O12 sin cambios.
- CA-O16.9 Dado el archivo local, la app no lo interpreta más allá de la cabecera (INV-O5) y no ejecuta
  ninguna herramienta externa (`qemu-img`) sobre él.

#### RF-O17 Crear con `import-from` y copia por MV — Debe — D-24.2
Cada MV del lote crea su propio disco: `scsi0=<storage>:0,import-from=<volid>[,discard=on,ssd=1,iothread=1,format=…]`
(sintaxis obligatoria `:0`, I4-§C). N MVs = N copias completas.
- CA-O17.1 Dado origen `importar_disco` y la imagen `local:import/cirros.qcow2`, entonces la petición del primer
  disco contiene `import-from=local:import/cirros.qcow2` y el valor `<storage>:0` (nunca el tamaño del
  formulario); los demás discos del formulario se crean vacíos como hasta ahora.
- CA-O17.2 Dado el storage destino `dir`/`nfs`/`cifs`, entonces el formato (`format=`) sigue V-09/P-06;
  en `lvmthin`/`zfspool`/`rbd`/LVM grueso (solo `raw`), no se envía.
- CA-O17.3 Dado un lote de N MVs, entonces hay N peticiones `POST` independientes, **cada una** con su
  `import-from`, y ≤ 1 `POST` por VMID (INV-L1); no existe "importar una vez y compartir".
- CA-O17.4 Dado la espera de la tarea `qmcreate` de una importación, entonces el tiempo máximo es
  `max(ESPERA_BASE_S, ESPERA_POR_GIB_S × tamaño_GiB)` (enmienda a M1 P-05) y, al vencer, la MV queda
  «sigue en curso en el servidor», no «fallida» (M1 P-05, INV-L1).
- CA-O17.5 Dado el log de la tarea con progreso de copia, entonces la fila de la MV muestra el porcentaje
  [LAB-M4-09]; si no, indeterminado.
- CA-O17.6 Dado un volumen fuente eliminado durante el lote, entonces esa MV y las siguientes fallan con E-O16
  («La imagen «x» ya no está en el servidor») sin reenvío, y E-L (errores repetidos, D-20.8) pausa el lote tras
  3 iguales.
- CA-O17.7 Dado un 403 por permiso de lectura de la fuente (`Datastore.Audit`/`AllocateSpace` en el storage
  `import`), entonces error global (D-20.8) con el privilegio nombrado.
- CA-O17.8 Dado el valor `import-from`, entonces se inserta solo si cumple V-O03 (inyección: `x.qcow2,scsi1=…`).
- CA-O17.9 Dado `efidisk0` con OVMF y disco importado, entonces el `efidisk0` se crea vacío como ahora y
  `bios`/`machine` siguen la regla existente; no se mezclan con `import-from`.
- CA-O17.10 La concurrencia sigue D-20.5 (1 MV por nodo, 4 nodos) y además no más de
  `CONCURRENCIA_PESADA_POR_STORAGE` (2) importaciones o clones completos simultáneos hacia el mismo storage
  destino (RNF-O04, V-O28).

#### RF-O18 Espacio y ampliación del disco importado — Debe (espacio) / Debería (ampliar) — D-24.2
- CA-O18.1 Dado un lote de N MVs y una imagen de tamaño virtual `T` GiB conocido, entonces el presupuesto de
  espacio del storage destino suma `T × N` (reusa V-L09/V-L10 de M2 con `T` como tamaño del disco
  importado); en thin, el aviso y el límite de 3× son los de D-20.2.
- CA-O18.2 Dado `T` desconocido (RF-O16 CA-O16.6), entonces se usa el tamaño del archivo como mínimo y se muestra
  el aviso «No se puede saber el tamaño exacto del disco al importarlo; se comprobará al crear»; no bloquea.
- CA-O18.3 Dado que el lote no cabe, entonces E-L04 («Reducir a N») como en M2.
- CA-O18.4 Dado «Ampliar el disco a X GiB» (X ≥ T), entonces tras crear la MV se envía **una** petición
  `PUT …/resize` con tamaño **absoluto** (`size=XG`, nunca `+`) para que repetirla sea inocua (INV-O3); el
  espacio presupuestado es `X × N`.
- CA-O18.5 Dado X < T, entonces V-O23 da error («Los discos solo pueden crecer»); no hay reducción.
- CA-O18.6 Dado que falta `VM.Config.Disk`, entonces «Ampliar» no está disponible (motivo visible) y la
  creación sigue sin ampliar.
- CA-O18.7 Dado que la ampliación falla con la MV ya creada, entonces la MV queda `parcial` («creada, falta
  ampliar el disco»), es elegible para rollback (CA-L18.7) y el informe lo marca; no se reenvía el `POST`.
- CA-O18.8 Dado el resumen, entonces muestra «Cada máquina recibirá una copia completa del disco (T GiB).
  Total: T×N GiB en «S»».

### F. Clonar una plantilla

#### RF-O19 Plantillas disponibles — Debe — D-24.3
El catálogo de plantillas sale de `GET /cluster/resources?type=vm` filtrando `template = 1` (visibles con
`VM.Audit`). La app lee además la configuración de la plantilla elegida (`GET …/qemu/{vmid}/config`) para saber
sus discos, storages, red, CPU y memoria.
- CA-O19.1 Dado el catálogo, entonces lista nombre, VMID, nodo y tamaño total de discos; las MVs que no son
  plantilla **no** aparecen (V-O04).
- CA-O19.2 Dado una plantilla con `lock` activo, con *snapshots* que impidan clonar o en otro estado no
  clonable, entonces aparece deshabilitada con motivo.
- CA-O19.3 Dado dos o más plantillas con el mismo nombre, entonces se muestran distinguidas por nodo y VMID;
  la referencia de lotes guardados y CSV es por **nombre** (DT-O13) y la ambigüedad se resuelve en V-O04.
- CA-O19.4 Dado un clúster, entonces la lista incluye plantillas de todos los nodos visibles, y dado un nodo
  suelto, las del nodo.
- CA-O19.5 Dado un usuario sin `VM.Clone` en `/vms/{vmid}`, entonces la plantilla aparece deshabilitada con
  «Falta el permiso VM.Clone» (RF-O24).
- CA-O19.6 Dado `GET /cluster/resources` que no lista plantillas por falta de `VM.Audit`, entonces E-O17 («No
  veo ninguna plantilla con tu cuenta. Pide el permiso VM.Audit o crea la plantilla en Proxmox.»).
- CA-O19.7 Convertir en plantilla **no** se ofrece (INV-O4); E-O17 explica cómo hacerlo en Proxmox.
- CA-O19.8 Dado el nombre y las notas de la plantilla, se tratan como texto no confiable (CA-O07.7).

#### RF-O20 Modo enlazado o completo — Debe — D-24.3
Modo del clon: `automatico` (por defecto), `enlazado`, `completo` (avanzado). `automatico` elige `enlazado`
solo si **todos** los discos de la plantilla están en storages que admiten *clone* sobre una base (tabla
I4-§D) y se mantiene el storage de la plantilla; si no, `completo` (P-O01).
- CA-O20.1 Dado `automatico` y una plantilla en `lvmthin`, `zfspool`, `rbd`, `btrfs` o `dir/nfs/cifs`
  (qcow2/raw/vmdk con formato qcow2 admitido), entonces el clon es enlazado y la petición **no** lleva
  `full`, `storage` ni `format`.
- CA-O20.2 Dado `automatico` y una plantilla en LVM grueso, entonces el clon es completo (`full=1`).
- CA-O20.3 Dado `enlazado` forzado en un storage sin soporte, entonces V-O21 da error («Este almacenamiento no
  permite clonar de forma enlazada. Elige completo.»).
- CA-O20.4 Dado `completo`, entonces la petición lleva `full=1`, `storage` (destino, V-17) y `format` solo
  en dir/nfs/cifs/btrfs según V-09, y el espacio se presupuesta como disco aprovisionado × N (V-O20).
- CA-O20.5 Dado un clon enlazado, entonces no se permite elegir storage destino (Proxmox no lo permite) y el
  presupuesto de espacio es ~0 con el aviso «Las máquinas dependen de la plantilla; Proxmox no te dejará
  borrar la plantilla mientras existan».
- CA-O20.6 Dado el modo básico, entonces solo se ve «Rápido y ligero (recomendado)/Copia independiente», con
  una frase llana sobre la diferencia; los términos "enlazado" y "completo" aparecen en avanzado.
- CA-O20.7 Dado el modo `completo` o enlazado, el estado TPM de la plantilla se clona completo en ≥ 8.4 (nota
  informativa; sin acción).
- CA-O20.8 Dado un linked clone, entonces el rollback (D-21) elimina el clon y deja la plantilla intacta
  (LAB-M4-11).
- CA-O20.9 El modo elegido se muestra en el resumen y consta en el informe de cada MV.

#### RF-O21 Clonación en lote y paralelismo — Debe — D-24.3, D-20, INV-L1
El motor crea cada MV con `POST /nodes/{n}/qemu/{vmid-plantilla}/clone` (`newid`, `name`, `full`/`storage`/
`format`/`target` según el modo) en lugar de `POST /nodes/{n}/qemu`. El clon **cuenta como la creación**
(INV-L1).
- CA-O21.1 Dado un lote de N clones, entonces hay ≤ 1 `POST …/clone` por `newid` en cualquier fallo inyectado
  (timeout, 596/597, conexión abortada, 401, 403, 500, respuesta sin UPID, JSON inválido), igual que
  CA-L12.1; y ningún `POST …/qemu` de creación para esas MVs.
- CA-O21.2 Dado un `POST …/clone` con resultado incierto (596, timeout), entonces la MV queda
  `conexion_perdida`/`existe_sin_confirmar_propiedad` según M2 CA-L15 sin reenvío ni reutilizar el VMID;
  la verificación mira `config` de ese `newid` (una MV con `lock: clone` existe).
- CA-O21.3 Dado el VMID, entonces se reserva y reconsulta como en M2 (INV-L2: `GET /cluster/nextid?vmid=`).
- CA-O21.4 Dado el motor, entonces espera el fin de la tarea `qmclone` (`lock: clone` liberado) **antes** de
  los ajustes (RF-O22) y antes de dar la MV por creada.
- CA-O21.5 Dado la plantilla, entonces el motor no escribe nada en ella (solo la lee y la bloquea en modo
  compartido durante el clon); varios clones simultáneos de la misma plantilla son posibles (lock
  compartido, I4-§D) [LAB-M4-10].
- CA-O21.6 Dado un clon **enlazado** (operación ligera), entonces se admiten hasta
  `CONCURRENCIA_ENLAZADO_POR_NODO` (3) clones simultáneos por nodo (P-O03, enmienda a D-20.5); para clon
  completo e importación rige 1 por nodo y el tope por storage de CA-O17.10. Si P-O03 se rechaza, la
  constante vale 1.
- CA-O21.7 Dado el campo `target` (clon a otro nodo), entonces solo se usa si el storage de la plantilla es
  compartido y está activo en el nodo destino (RF-O23); nunca para storage local.
- CA-O21.8 Dado un nombre de MV, entonces se pasa como `name` (V-01) y la nueva MV conserva la
  descripción de la plantilla; no se heredan `vmid`/`template`.
- CA-O21.9 Dado un error `can't clone to non-shared storage`, `storage … does not support vm images`,
  `parameter 'storage' not allowed for linked clones`, `Linked clone feature is not supported`, `config file
  already exists`, entonces cada uno se traduce a su error E-O18..E-O19 con la causa y no se reintenta.
- CA-O21.10 Dado el informe y el log, entonces registran la plantilla (nombre, VMID), el modo y el newid; el
  VMID del clon enlazado consta (en 9.2 aparece también en el log de la tarea).
- CA-O21.11 Dado que la plantilla desaparece (o cambia a `lock`) entre el resumen y la ejecución, entonces
  esa y las demás MVs fallan con E-O16/E-O18 sin reenvío y el lote se pausa por la regla de 3 errores iguales.

#### RF-O22 Ajustes tras clonar — Debe (CPU, memoria, disco) / Debería (red, reintento) — D-24.3
Después de clonar, la app envía `PUT …/qemu/{newid}/config` con **solo** lo que el usuario cambió respecto a
la plantilla: `cores`/`sockets`/`cpu` (`VM.Config.CPU`), `memory`/`balloon` (`VM.Config.Memory`), `tags`
(`VM.Config.Options`), y `PUT …/resize` con tamaño absoluto (`VM.Config.Disk`).
- CA-O22.1 Dado el origen `clonar_plantilla`, entonces los campos de núcleos, memoria y disco del formulario se
  inicializan con los de la **plantilla** (leídos) y muestran «igual que la plantilla»; solo si el usuario los
  cambia se envían (CA-P05.1 de M3 no los pisa con los del perfil de MV).
- CA-O22.2 Dado un cambio de CPU y memoria, entonces se envían en **un** `PUT …/config` con los valores
  absolutos; un `PUT` repetido es inocuo (INV-O3).
- CA-O22.3 Dado un tamaño de disco mayor, entonces `PUT …/resize` con `disk=<clave del disco principal>` y
  `size=<N>G` absoluto; menor o igual, no se envía (V-O23); el disco principal es el primero de la
  plantilla (`scsi0`, si no `virtio0`, `sata0`, `ide0`).
- CA-O22.4 Dado el lote con etiqueta (D-20.3), entonces se envía `tags` con la unión de las etiquetas de la
  plantilla y las del lote (`proxlaunch;lote-<id>`); un clon no admite `tags` en `clone`, por lo que
  el `PUT` de etiquetas es la marca de propiedad (DT-O14).
- CA-O22.5 Dado que el `PUT` de etiquetas falla pero el clon existe, entonces la MV queda `parcial` («clonada,
  sin etiqueta») y es elegible para rollback por estar en el libro con su VMID y UPID (CA-L18.7).
- CA-O22.6 Dado que `PUT config` o `resize` falla (403, error), entonces la MV queda `parcial`, el informe dice
  qué ajuste falta, el lote continúa con las demás (RF-L14) y **no** se reenvía el clon (INV-L1). Opción
  "Reintentar ajustes" (Debería): reenvía solo los `PUT` (idempotentes, valores absolutos), previa
  comprobación de la config.
- CA-O22.7 Dado el estado de la plantilla con `cores`, `memory`, `net`, el app **no** envía lo que no cambió
  (no hay `PUT` si no hay cambios).
- CA-O22.8 Dado que falta `VM.Config.Disk`, entonces el campo de disco queda deshabilitado con motivo; las
  demás partes del clon siguen disponibles.
- CA-O22.9 Dado el cambio de red tras clonar (Podría), entonces se reescribe `net0` conservando el modelo y la
  MAC y reemplazando solo `bridge`/`tag`, con `VM.Config.Network` y `SDN.Use`; si no se implementa, V-O25 exige
  que los bridges de la plantilla existan en el nodo destino.
- CA-O22.10 Dado la MAC, entonces las MVs clonadas tienen MACs distintas entre sí y de la plantilla [LAB-M4-10].
- CA-O22.11 Los ajustes tras clonar son visibles en la simulación como las peticiones que se enviarían
  (solo texto; INV-L5).

#### RF-O23 Plantilla por nodo y storage local — Debe — D-24.3
- CA-O23.1 Dado una plantilla en storage **local** de un nodo, entonces el destino elegible es **solo ese
  nodo** (V-O25); el clon no usa `target`.
- CA-O23.2 Dado una plantilla en storage **compartido** activo en varios nodos, entonces el reparto de M2 puede
  incluir los demás nodos y el clon se envía al nodo de la plantilla con `target=<nodo>` (solo clon completo
  si el modo lo exige, I4-§D).
- CA-O23.3 Dado un destino «Automático» o «Nodos elegidos» que incluye nodos sin la plantilla o sin sus
  storages, entonces esos nodos no son elegibles (M2 V-L11 ampliada) con el texto «El nodo «pve2» no tiene la
  plantilla ni el almacenamiento «local-lvm»».
- CA-O23.4 Dado varias plantillas con el mismo nombre en nodos distintos con storage local, entonces se tratan
  como **una plantilla replicada** (la app clona la de cada nodo, DT-O13) y el resumen la lista como
  «plantilla «base-win» (en pve1 y pve2)»; los ajustes y el modo deben valer en todos.
- CA-O23.5 Dado el mismo nombre en un mismo nodo, o en nodos con storage compartido, entonces V-O04 pide al
  usuario elegir (no se adivina).
- CA-O23.6 Dado un nodo suelto, el requisito es sencillo (todo local).
- CA-O23.7 Dado un clúster con storage local y destino «Nodos elegidos» sin plantilla en alguno, entonces
  V-O25 lo bloquea; el usuario resuelve (crear la plantilla allí o quitar el nodo) y nada se sustituye en
  silencio (D-23.2).
- CA-O23.8 Dado un lote guardado cargado en otro servidor, entonces las plantillas se re-resuelven por
  nombre (CA-O27.3).

### G. Permisos y capacidades

#### RF-O24 Rol ampliado, detección de permisos y degradación — Debe — D-24.8
El rol `ProxLaunchCreador` pasa de 10 a 14 privilegios (sin `Datastore.Allocate`):

| Privilegio | Ruta | Para qué |
|---|---|---|
| `VM.Config.Disk` (nuevo) | `/vms` | `boot` (orden de arranque), `resize` |
| `VM.Clone` (nuevo) | `/vms/{plantilla}` | clonar |
| `Datastore.AllocateTemplate` (nuevo) | `/storage/{s}` | subir y descargar ISOs/imágenes |
| `Sys.AccessNetwork` (nuevo) | `/nodes/{n}` | `download-url`, `query-url-metadata` (≥ 8.2) |
| los 10 de M1 (`VM.Allocate`, `VM.Audit`, `VM.Config.Options`, `VM.Config.HWType`, `VM.Config.CPU`, `VM.Config.Memory`, `VM.Config.Network`, `Datastore.AllocateSpace`, `SDN.Use`, `Sys.Audit`) | `/` | como hasta ahora |

- CA-O24.1 Dado `GET /access/permissions`, entonces la app deriva para cada vía: `VM.Config.Disk` en
  `/vms/{vmid}` (o `/vms`), `VM.Clone` en `/vms/{plantilla}`, `AllocateTemplate` en `/storage/{s}`,
  `Sys.AccessNetwork` en `/nodes/{n}` (o `Sys.Modify` en `/`), y deshabilita con motivo lo que falta.
- CA-O24.2 Dado un 403 de Proxmox en una acción, entonces se extrae el privilegio del mensaje (M1 §7) y
  E-O20 lo nombra con el texto «Falta el permiso X en la ruta Y» (extensión de CA-L18.9).
- CA-O24.3 Dado el cambio del rol, entonces la guía de usuario, la ayuda «¿Cómo creo un API Token?» y el diálogo
  de permisos de M1 se actualizan con la lista de 14, indicando qué función se pierde sin cada privilegio
  nuevo (tarea del `documentador`; texto fijado aquí en RF-O32).
- CA-O24.4 Dado el rol de **MVP 3** (10 privilegios) en un servidor, entonces la app sigue creando MVs vacías
  como antes (CA-O03.1) y solo las vías nuevas aparecen deshabilitadas con el privilegio que falta (no hay
  error al conectar).
- CA-O24.5 Dado `Datastore.Allocate` en el usuario (administrador), entonces la app **no** lo usa para borrar
  nada (INV-O4); no hay botón de borrado de ISOs, imágenes ni plantillas.
- CA-O24.6 Dado `VM.Config.CDROM` y `VM.Config.Disk`, entonces si LAB-M4-04 demuestra que crear con `ide2` exige
  `VM.Config.CDROM`, el rol pasa a 15 privilegios y esta tabla, la guía y el chequeo de permisos se
  actualizan; hasta entonces no se pide.
- CA-O24.7 El token con *privilege separation*: la comprobación se hace con los permisos efectivos del token
  (el endpoint ya lo devuelve así); un 403 de ISO por falta de privilegio del token se explica con E-O20.
- CA-O24.8 Un test de contrato recorre cada petición de escritura del MVP 4 (upload, download-url, create con
  ISO/import, clone, config, resize) y verifica que los privilegios exigidos están en la lista de 14.

#### RF-O25 Las subidas no se pueden deshacer — Debe — D-24.7, D-24.8
Sin `Datastore.Allocate` el archivo subido no se puede borrar desde la app (I4-§B).
- CA-O25.1 Dado cualquier subida o descarga, entonces antes de confirmar se muestra el texto de CA-O09.2 con la
  consecuencia (el archivo queda hasta que un administrador lo borre).
- CA-O25.2 Dado el informe de un lote y el "Deshacer" de M2, entonces solo cubren MVs (D-21); las
  transferencias hechas antes **no** son parte del lote y no se deshacen. El informe lo indica si el lote
  usó una fuente subida en esta sesión (lista de archivos subidos con su volid, para que el administrador
  los limpie).
- CA-O25.3 Dado el cierre de sesión o de la app, entonces la lista de archivos subidos en la sesión (nombre,
  storage, tamaño, hora) puede copiarse/guardarse desde el diálogo de transferencias; no se persiste sola.
- CA-O25.4 Dado un usuario administrador, la app tampoco ofrece borrar (INV-O4); la guía explica cómo borrar en
  Proxmox.

### H. Integración con perfiles, lotes guardados, CSV, simulación y rollback

#### RF-O26 Perfiles de máquina con origen sugerido — Debe — D-24.4
Un perfil de MV (M3) puede llevar un **origen sugerido** y su detalle como *pista*: tipo de origen, `tipo_so`,
nombre de la ISO o de la imagen o de la plantilla, modo y ajustes de clon; nunca volids de otro servidor como
verdad (se resuelven al aplicar).
- CA-O26.1 Dado un perfil con origen `iso` y la ISO `alpine-virt-3.24.4-x86_64.iso`, cuando se aplica y existe
  en el catálogo, entonces el formulario queda con origen `iso` y esa ISO elegida.
- CA-O26.2 Dado que la fuente sugerida **no existe** en este servidor, entonces el origen queda elegido pero
  sin fuente, con aviso «El perfil pedía el ISO «x», que no está en este servidor. Elige otro o súbelo» y
  **bloquea** el resumen hasta elegir (V-O01); **no** cambia a "Vacía" en silencio.
- CA-O26.3 Dado un perfil de fábrica, entonces todos mantienen origen `disco_vacio` (CA-P02.6 de M3) salvo lo
  que decida P-O02.
- CA-O26.4 Dado "Guardar como perfil de máquina", entonces el origen y su detalle se guardan como pista
  (casilla existente de pistas, CA-P03.3) y, si se desmarca, el perfil se guarda con origen `disco_vacio`
  explícito; el diálogo lo dice.
- CA-O26.5 Dado un perfil con origen `clonar_plantilla` aplicado, entonces núcleos, memoria y disco del
  perfil **no** pisan los de la plantilla (CA-O22.1); sólo los del perfil con "ajustes de clon" guardados.
- CA-O26.6 Dado el archivo del perfil, entonces **nunca** contiene URL, ruta local, checksum de transferencia
  ni datos de conexión (INV-O6, INV-M2); un test recorre toda la serialización.
- CA-O26.7 Dado un perfil exportado/importado, entonces las pistas de origen siguen la regla de las demás pistas:
  exportación **sin** pistas por defecto (CA-P08.2) y, marcada la casilla, con ellas. Un perfil importado cuyo
  `origen` ≠ `disco_vacio` se acepta (ya no se rechaza por V-20 de M1) pero **no descarga ni abre nada**
  (CA-X02.6 de M3 se mantiene: la fuente es solo un nombre que se resuelve contra el servidor).
- CA-O26.8 Dado el formato (`version_formato`), entonces se escribe `2` **solo** si el perfil usa un origen
  distinto de `disco_vacio` o campos de origen; si no, se sigue escribiendo `1` (DT-O15); `1` se lee como
  hasta ahora y una app del MVP 3 abre un archivo `2` con E-M03 («versión más nueva»).
- CA-O26.9 Dado un perfil con origen sugerido, aplicar el perfil no envía ninguna petición de escritura
  (INV-M1, CA-P05.7).

#### RF-O27 Lotes guardados — Debe — D-24.4
El lote guardado homogéneo y el por filas incluyen el origen y su detalle (sección 4).
- CA-O27.1 Dado un lote guardado con origen `iso`, `importar_disco` o `clonar_plantilla`, entonces el archivo
  contiene el origen, el nombre o volid de la fuente, `tipo_so`, modo y ajustes; **no** contiene URL, ruta,
  checksum, VMID de MV, ni estado de transferencias (INV-M5, INV-O6).
- CA-O27.2 Dado cargar un lote con origen, entonces **no se transfiere ni se crea nada** (INV-M1, INV-O1) y se
  aplica RF-G04: la fuente se revalida contra el servidor actual (catálogo, plantillas) y los desajustes salen
  como errores concretos con «Usar otro…» (nunca sustitución silenciosa, D-23.2).
- CA-O27.3 Dado una plantilla guardada por nombre y VMID de pista, cuando se carga, entonces se re-resuelve por
  nombre; si el VMID de la pista no coincide pero el nombre sí, se usa el del nombre y se avisa; si hay varios,
  V-O04.
- CA-O27.4 Dado un lote guardado de MVP 3 (origen `disco_vacio`), entonces se lee sin cambios (CA-O03.2).
- CA-O27.5 Dado el guardado, entonces `version_formato = 2` solo si algún origen ≠ `disco_vacio` (CA-O26.8);
  la migración v1→v2 es la identidad con `origen = disco_vacio` y se prueba con archivos de ejemplo de ambas
  versiones (CA-X01.3).
- CA-O27.6 Dado un lote guardado con ISO de un storage que no existe en el servidor nuevo, entonces E-M15 con
  el storage y las alternativas (RF-G05).
- CA-O27.7 Dado un lote por filas guardado, entonces cada fila lleva su propio origen (CA-O28.4).
- CA-O27.8 Dado el modo "Cambios sin guardar" (RF-G08), el origen elegido cuenta como cambio.

#### RF-O28 CSV: columnas de origen — Debe — D-24.4
Se amplía la tabla de columnas de RF-C03 de M3:

| Columna | Obligatoria | Alias | Significado | Validación |
|---|---|---|---|---|
| `origen` | No | `source` | `vacio`/`disco_vacio`, `iso`, `importar`/`imagen`, `clonar`/`plantilla` (sin distinguir mayúsculas ni acentos) | V-O01 |
| `fuente` | Según origen | `origen_archivo`, `iso`, `plantilla`, `imagen` | Nombre del ISO, de la imagen o de la plantilla; admite volid completo `storage:iso/x.iso` | V-O02, V-O03, V-O04 |
| `so` | No | `sistema` | `tipo_so` (RF-O13): `linux`, `windows 11`, `windows server 2022/2025`, `windows 10`, `windows server 2016/2019`, `otro` | V-O05 |
| `virtio` | No | `drivers` | `si`/`no`: montar el CD virtio-win (por defecto `si` en Windows) | V-O02 |
| `modo_clon` | No (avanzado) | `clon` | `auto`, `enlazado`, `completo` | V-O21 |

Las columnas existentes `cpu`, `memoria` y `disco` se reutilizan: en un clon significan **ajustes sobre la
plantilla** (CA-O22.1); en una importación, `disco` significa **ampliar a** (CA-O18.4).
- CA-O28.1 Dado un CSV sin columna `origen`, entonces todas las filas son `disco_vacio` (o el del perfil
  de la fila, CA-C13.5) y el comportamiento es el de MVP 3.
- CA-O28.2 Dado `origen = iso` y `fuente` vacía, sin perfil que la sugiera, entonces error de fila y columna
  (E-M11) con ejemplo; con perfil que la sugiere, se usa la del perfil.
- CA-O28.3 Dado `fuente` que no existe en el catálogo del servidor, entonces error de fila con el nombre y
  hasta 5 alternativas; dado `fuente` ambigua (mismo nombre en dos storages), error que pide el volid
  completo.
- CA-O28.4 Dado un CSV con filas de ISO, importación y clon mezcladas, entonces forman **un solo lote por filas**
  (D-22.1): un resumen, una confirmación, un informe y un "Deshacer".
- CA-O28.5 Dado precedencia (CA-C13.5), entonces valores por defecto de M1 → perfil de la fila (incluido su
  origen sugerido) → columnas del CSV; una columna presente siempre gana (test de propiedad).
- CA-O28.6 Dado una celda `fuente` con aspecto de URL (`http://…`, `https://…`), entonces error E-O21 («Aquí va el
  nombre de un archivo del servidor, no una dirección web. Para descargar usa «Descargar en el servidor»»)
  y **nunca** se descarga nada desde el CSV (INV-O1).
- CA-O28.7 Dado una celda con ruta absoluta (`/var/…`, `C:\…`), entonces E-O14 y no se interpreta.
- CA-O28.8 Dado un valor de `fuente` con disparador de fórmula (`=`, `+`, `-`, `@`), entonces se trata como
  texto (CA-C11) y, al exportar CSV, se neutraliza.
- CA-O28.9 Dado la plantilla CSV descargable (RF-C10), entonces incluye las columnas nuevas con una fila de
  ejemplo por origen (`ejemplo-…`, V-M11) y la ayuda las explica.
- CA-O28.10 Dado el CSV de errores y el informe CSV (RF-C14), entonces incluyen origen y fuente con el mismo saneo.
- CA-O28.11 Dado un encabezado de credencial en el CSV, rige RF-X04 sin cambios.
- CA-O28.12 Dado el CSV, entonces las filas son ≤ `MAX_LOTE` (100) y los límites de M3 no cambian.

#### RF-O29 Validación, resumen y simulación — Debe — D-24.4, D-20.10
- CA-O29.1 Dado un lote con origen, entonces el planificador de M2 corre completo con V-O01..V-O28 además de
  las reglas existentes: reserva de VMIDs, reparto, espacio (V-L09/V-L10 con los tamaños de los orígenes),
  memoria, permisos.
- CA-O29.2 Dado el resumen, entonces lista por origen: la fuente y su storage, `tipo_so` y hardware
  resultante, el CD de drivers, el orden de arranque (o su omisión), espacio total por storage (T × N, X × N,
  aprovisionado de clones completos), modo de clon, ajustes y todos los avisos (RF-O13/O14/O18/O20), antes del
  botón de confirmar (INV-M6).
- CA-O29.3 Dado la **simulación**, entonces el contador de métodos del mock prueba que solo hay GET (INV-L5) y
  la salida incluye las peticiones que **se enviarían** (incluida la del `clone`, `PUT config` y `resize`) como
  texto; nada se descarga, sube ni crea.
- CA-O29.4 Dado la simulación de un lote con origen que requiere una fuente aún no subida, entonces la
  simulación no sube nada y señala «Falta subir X» como error de fuente.
- CA-O29.5 Dado un cambio en el inventario o en el catálogo entre el resumen y la confirmación, entonces
  V-L14 (vigencia, 300 s) relee catálogos, plantillas y storages y revalida (E-L11).
- CA-O29.6 Dado la **versión forzada** mayor que la detectada, entonces la simulación vale y la ejecución real
  se bloquea (V-L15 de M2) incluso para los orígenes nuevos.
- CA-O29.7 Dado un origen no disponible en una versión forzada, entonces la simulación lo muestra como error de
  capacidad, no como excepción.
- CA-O29.8 Dado el lote por filas, entonces la validación es por fila con fila/columna (E-M11) y las exclusiones
  de M3 RF-C07 aplican igual.
- CA-O29.9 Dado "Crear" tras cargar un lote o importar un CSV con origen, entonces sigue deshabilitado hasta
  generar el resumen y confirmar (INV-M6).

#### RF-O30 Ejecución, rollback e informe — Debe — D-24.4, D-20, D-21
- CA-O30.1 Dado el lote con origen `iso`, `importar_disco` o `clonar_plantilla`, entonces la ejecución usa
  `ServicioCreacion.crear` ampliado (validar → reconsultar VMID → POST de creación o `clone` → UPID → sondeo →
  ajustes → comprobar `config`) y el libro registra, además, origen, fuente y modo.
- CA-O30.2 INV-L1 se prueba (inyección de fallos exhaustiva, CA-L12.1) para **cada** origen: ≤ 1 `POST` de
  creación por VMID, contando `POST /qemu` y `POST …/clone` juntos.
- CA-O30.3 Dado el "Deshacer", entonces solo elimina MVs del libro con `DELETE …/qemu/{vmid}` y
  `destroy-unreferenced-disks=0` (D-21); no borra ISOs, imágenes subidas, plantillas ni volúmenes. El
  informe dice «Los archivos que subiste no se eliminan».
- CA-O30.4 Dado un clon enlazado o una importación fallida a la mitad, entonces el rollback se comporta como
  CA-L18.4 a CA-L18.14; para imports fallidos que dejen un volumen suelto, el informe usa E-L21 («Pueden haber
  quedado discos sueltos») [LAB-M4-09 comprueba si ocurre].
- CA-O30.5 Dado el informe final, entonces incluye por MV: origen, fuente, modo y ajustes; y al final la lista
  de archivos subidos/descargados en la sesión (RF-O25).
- CA-O30.6 Dado el informe de texto y CSV, entonces se aplica el saneo de M2 CA-L19.3 y nunca contiene URL ni
  rutas locales.
- CA-O30.7 Dado un permiso insuficiente a mitad del lote (403 con nombre de privilegio), entonces es error
  global y pausa inmediata (D-20.8).
- CA-O30.8 La concurrencia, la cancelación y la pausa por errores repetidos son las de M2, con las
  extensiones de RNF-O04.
- CA-O30.9 Dado un lote con ISO y N MVs repartidas en varios nodos con ISO compartido, entonces las N MVs
  montan el mismo volid y no hay N subidas.

#### RF-O31 Perfiles de fábrica nuevos — Podría — P-O02
Tres perfiles de fábrica de hardware (sin ISO ni fuente): «Windows 11 (escritorio)», «Windows Server»,
«Linux (Red Hat y otros)», que fijan `tipo_so`, firmware, TPM y valores de cómputo recomendados.
- CA-O31.1 Dado el perfil «Windows 11 (escritorio)», entonces: 4 núcleos, 8 GiB, disco de 64 GiB, OVMF + TPM,
  `tipo_so = windows_11`, origen `iso` sin fuente; pasa la validación completa con mocks (CA-P02.3).
- CA-O31.2 Los 6 perfiles de M3 (P-M05 A) no cambian; los nuevos son además de ellos.
- CA-O31.3 Dado un perfil de fábrica nuevo, entonces aplica todo lo de CA-P02.2/P02.5 (solo lectura,
  inmutable).
- CA-O31.4 Si P-O02 se rechaza, este requisito se omite sin afectar al resto.

#### RF-O32 Ayudas, textos y guía — Debe — D-14
- CA-O32.1 Dado la lista de identificadores de ayuda nuevos (origen, ISO, subir, descargar por URL, checksum,
  asistente de SO, drivers virtio-win, importar, formatos qcow2/vmdk/raw, copia por MV, plantilla,
  enlazado/completo, storage recordado, permisos del rol ampliado), entonces cada uno tiene un texto
  no vacío de 1 a 3 frases en español llano (test, M1 CA-25.2).
- CA-O32.2 Dado el administrador, entonces hay un texto copiable «Qué pedirle a tu administrador» con los 14
  privilegios, la activación de «Import» y la creación de plantillas.
- CA-O32.3 La guía `docs/guia-usuario.md` documenta cada flujo F-O1 a F-O8, el rol ampliado, la instalación
  del SO desde la consola (la app no enciende la MV), la carga del controlador VirtIO de Windows, la expulsión
  del CD y el borrado de archivos por el administrador (tarea del `documentador`, fuera de este documento).
- CA-O32.4 Los textos nuevos usan «plantilla de Proxmox» para clonar y «perfil de máquina» para M3; nunca
  se mezclan.

---

## 6. Requisitos no funcionales

Siguen vigentes los RNF de M1 (RNF-01..16), M2 (RNF-L01..L11) y M3 (RNF-M01..M12), en particular RNF-06
(secretos), RNF-08 (sin pruebas destructivas en reales) y RNF-16 (codificación de entradas).

| ID | Requisito | Prioridad | Criterio de aceptación (verificable) |
|---|---|---|---|
| RNF-O01 | Subida sin cargar el archivo en memoria | Debe | CA-RNF-O01: la subida lee el archivo en bloques de `CHUNK_SUBIDA` (1 MiB) y envía con `Content-Length` conocido; con un flujo ficticio de 8 GiB el aumento máximo de memoria medido (`tracemalloc` y RSS) es ≤ 64 MiB; el cálculo de checksum también es por bloques; ninguna estructura guarda el contenido. |
| RNF-O02 | Progreso útil y fluido | Debe | CA-RNF-O02: el callback de progreso entrega bytes enviados y total; la interfaz se actualiza ≥ 1 vez por segundo y ≤ 10 por segundo; el bucle de eventos no se retrasa más de 200 ms durante una subida simulada de 8 GiB (M2 CA-RNF-L01); velocidad y tiempo restante calculados con media móvil. |
| RNF-O03 | Cancelación | Debe | CA-RNF-O03: "Cancelar" interrumpe la subida o el cálculo del hash en ≤ 2 s; no deja hilos ni archivos temporales locales; la app no reintenta tras cancelar; el estado del servidor se verifica consultando el catálogo, no se asume. |
| RNF-O04 | Concurrencia limitada | Debe | CA-RNF-O04: una sola transferencia a la vez; en la ejecución, importaciones y clones completos ≤ 1 por nodo (D-20.5) y ≤ `CONCURRENCIA_PESADA_POR_STORAGE` (2) por storage destino; clones enlazados ≤ `CONCURRENCIA_ENLAZADO_POR_NODO` (3, P-O03); constantes únicas; prueba con mock que mide el máximo de peticiones simultáneas por nodo y por storage. |
| RNF-O05 | Seguridad de URLs y de archivos locales | Debe | CA-RNF-O05: la app **nunca** abre conexiones a la URL del usuario (solo el servidor lo hace); URL ≤ `MAX_LONG_URL` (2048), `http(s)` sin `userinfo` (usuario:clave@), sin caracteres de control; los nombres de archivo y los volids se validan con lista blanca antes de entrar a cualquier parámetro (V-O02, V-O03, V-O09); el archivo local se abre solo para lectura, tras comprobar con `fstat` que es regular (no directorio, tubería ni dispositivo), sin seguir lo que el archivo indica; solo se leen la cabecera y el contenido para subir/hash; fuzz de V-O10 con 10 000 cabeceras mutadas sin excepción no controlada. |
| RNF-O06 | Privacidad y secretos | Debe | CA-RNF-O06: prueba del centinela extendida a URL (con `user:pass@` y `?token=`), checksums, rutas locales, nombres de archivo y volids; ningún archivo, log, mensaje, informe ni portapapeles los contiene salvo el nombre de archivo y el volid; el log de transferencias guarda host y nombre de archivo, no la URL; los storages recordados en `perfiles.json` no incluyen secretos. |
| RNF-O07 | Textos traducibles | Debe | CA-RNF-O07: todos los textos nuevos (mensajes E-O, V-O, ayudas, estados de transferencia, nombres de tipos de SO, modos de clon, encabezados de columnas CSV con alias) pasan por el catálogo; plurales con formas de Qt ("1 máquina", "12 máquinas"); el catálogo de prueba "[T]" los marca todos; claves JSON y encabezados canónicos del CSV no se traducen. |
| RNF-O08 | Accesibilidad | Debe | CA-RNF-O08: barras de progreso con nombre accesible, valor y texto de estado; botones "Subir", "Cancelar" y "Dejar de esperar" accesibles con teclado y foco visible; diálogos destructivos o irreversibles (subir, sobrescribir no existe, cambiar origen con pérdida, cerrar con transferencia activa) con "Cancelar" como foco inicial; contraste ≥ 4,5:1 en ambos temas; estados con texto y símbolo; anuncio de fin de transferencia por texto; escalado 150 % y 200 % sin recortes (M1 RNF-11). |
| RNF-O09 | Compatibilidad de versiones de Proxmox | Debe | CA-RNF-O09: la suite de los tres orígenes pasa contra respuestas de 8.0, 8.1, 8.2, 8.3, 8.4 y 9.x (sintéticas las de 8.0 a 8.3 y 8.4), con la matriz de la sección 3 verificada por un test parametrizado fila a fila; la lógica por versión pasa solo por la tabla de capacidades (`Funcion.*`). |
| RNF-O10 | Sin pruebas destructivas en producción | Debe | CA-RNF-O10: la suite normal no abre sockets; los LAB-M4 solo contra el laboratorio con variable de entorno explícita, solo VMIDs 9000 a 9099 y archivos con prefijo `proxlaunch-lab-`; limpian lo que crean (D-15); 8.0 a 8.3 solo con respuestas sintéticas. |
| RNF-O11 | Plataformas Ubuntu y Windows | Debe | CA-RNF-O11: matriz manual por entrega: archivo ≥ 4 GiB en Windows, rutas con espacios, acentos y más de 260 caracteres, archivo bloqueado o en disco de red, `pathlib`/`platformdirs`, cálculo de checksum y subida idénticos en ambos sistemas (el mismo `sha256` para el mismo archivo). |
| RNF-O12 | Robustez | Debe | CA-RNF-O12: pérdida de red, 5xx, tiempo sin progreso, ticket caducado y cierre de la app en una subida no dejan la interfaz "ocupada" ni el formulario a medias; el estado final se verifica en el catálogo; no hay reintento automático de escrituras. |
| RNF-O13 | Rendimiento y núcleo sin Qt | Debe | CA-RNF-O13: clasificación de storages, cálculo de capacidades y validación de orígenes son funciones puras sin Qt ni E/S, ejecutables sin PySide6 (M1 RNF-02); catálogos de 500 volúmenes listados en ≤ 2 s con mock; el hilo de la interfaz nunca hace E/S de red ni de disco. |
| RNF-O14 | Integridad de la subida | Debe | CA-RNF-O14: toda subida lleva `checksum` sha256 calculado antes; el servidor lo comprueba; un test con checksum alterado debe fallar con E-O07; la verificación posterior compara tamaño. |
| RNF-O15 | Determinismo | Debería | CA-RNF-O15: la construcción de la petición (ISO, import, clon) es función pura de (configuración, inventario, versión); el reloj se inyecta; mismo dato, misma petición. |

---

## 7. Reglas de validación (V-O*)

Se implementan en el núcleo (sin Qt) con test unitario por regla y por origen. Las V-01..V-24 de M1,
V-L01..V-L17 de M2 y V-M01..V-M15 de M3 siguen vigentes y se **reutilizan**.

| ID | Campo | Regla | Severidad | Mensaje (al usuario) |
|---|---|---|---|---|
| V-O01 | Origen y detalle | `origen` ∈ 4 valores; cada origen tiene su detalle completo (ISO: volid y `tipo_so`; import: volid; clon: plantilla); sin detalle ajeno | Error | "Falta elegir de dónde sale el sistema operativo." / "Elige un ISO." |
| V-O02 | Volid de ISO / CD de drivers | Forma `storage:iso/archivo`; `storage` y `archivo` solo `[A-Za-z0-9._-]`; extensión `.iso` o `.img`; sin `,` `=` `;` espacios ni saltos; existe en el catálogo del nodo; storage activo | Error | "Este ISO no está disponible en «nodo»." / "Nombre no admitido." |
| V-O03 | Volid de imagen | Forma `storage:import/archivo`; mismos caracteres; extensión `.qcow2`, `.raw` o `.vmdk`; no es ruta absoluta; existe en el catálogo; versión ≥ 8.4 | Error | "Esta imagen no está disponible." / E-O14 para ruta |
| V-O04 | Plantilla | Existe, `template = 1`, sin `lock`, visible y clonable; el nombre resuelve a una sola plantilla por nodo; el VMID es de la lista | Error | "No encuentro la plantilla «x»." / "Hay dos plantillas «x»: elige una." |
| V-O05 | Tipo de SO coherente | `tipo_so` ∈ enum; Windows 11 exige OVMF + TPM; el resto, SeaBIOS en Windows es aviso; `otro` sin cambios | Error / Aviso | "Windows 11 exige arranque UEFI y TPM 2.0." |
| V-O06 | Ranuras IDE con ISO | Con origen `iso`, discos IDE ≤ 2 (usan `ide1` e `ide3`); `ide0` y `ide2` reservados a CD | Error | "Con un ISO solo caben 2 discos IDE; usa SCSI o SATA." |
| V-O07 | Mínimos de Windows | Win 11: ≥ 2 núcleos, ≥ 4096 MiB, disco ≥ 64 GiB; Win 10: ≥ 1 núcleo, ≥ 2048 MiB, ≥ 32 GiB; Server: ≥ 1 núcleo, ≥ 2048 MiB, ≥ 32 GiB | Aviso | "Windows 11 pide al menos 2 núcleos, 4 GiB de memoria y 64 GiB de disco." |
| V-O08 | TPM y EFI | TPM exige storage con `images` activo (storage del `efidisk0`) | Error | "No hay un almacenamiento válido para el TPM." |
| V-O09 | Nombre de archivo a subir/descargar | 1–100 caracteres `[A-Za-z0-9._-]`; no empieza por punto; extensión según contenido (ISO `.iso/.img`; import `.qcow2/.raw/.vmdk`); no reservado de Windows | Error | "Usa solo letras sin acentos, números, punto, guion y guion bajo." |
| V-O10 | Archivo local | Regular, legible, tamaño > 0; ISO: se acepta cualquier contenido (aviso si no es ISO 9660: firma "CD001" en 0x8001 ausente); qcow2 `QFI\xfb` v2/v3 sin *backing file* ni cifrado; vmdk `KDMV` monolítico; sin enlace roto; no cambia durante la subida | Error / Aviso | "Este archivo no se puede subir: {motivo}." |
| V-O11 | URL | ≤ 2048 caracteres; `https://` (o `http://` con confirmación en avanzado); host presente; sin `userinfo`; sin caracteres de control ni espacios; sin `file://`/`ftp://`/otro esquema | Error | "Escribe una dirección web completa que empiece por https://." |
| V-O12 | Checksum | Hexadecimal; longitud 32/40/56/64/96/128 ↔ md5/sha1/sha224/sha256/sha384/sha512; el algoritmo se deduce de la longitud | Error | "La huella no tiene un formato válido." |
| V-O13 | Espacio de transferencia | tamaño ≤ `avail` − `RESERVA_STORAGE_MIB` del storage destino (bloquea); `rootfs.avail` del nodo ≥ tamaño + `RESERVA_RAIZ_MIB` (aviso) | Error / Aviso | "El archivo pesa X y «S» solo tiene Y libres." |
| V-O14 | Nombre existente | El volid destino no existe en el storage; sin opción de sobrescribir | Error | "Ya existe un archivo con ese nombre." |
| V-O15 | Permiso de subida | `Datastore.AllocateTemplate` en `/storage/{s}` y storage con contenido destino | Error | "Falta el permiso Datastore.AllocateTemplate." |
| V-O16 | Permiso de descarga por URL | ≥ 8.2 y (`Sys.AccessNetwork` en `/nodes/{n}` o `Sys.Modify` en `/`); en < 8.2, solo `Sys.Modify` en `/` | Error | Ver E-O03 |
| V-O17 | Permiso de clon | `VM.Clone` en `/vms/{plantilla}` | Error | "Falta el permiso VM.Clone." |
| V-O18 | Permiso `VM.Config.Disk` | Necesario para `boot` y `resize`; ausente o desconocido: se omite el parámetro (ISO) o se deshabilita la ampliación | Aviso | "Sin el permiso VM.Config.Disk no se puede fijar el orden de arranque." |
| V-O19 | Espacio de importación | Σ tamaño virtual (o ampliado) por storage destino ≤ `avail` (no thin); thin: V-L10; destino con `AllocateSpace` | Error / Aviso | "Las N máquinas necesitan X GiB en «S»…" (E-L04) |
| V-O20 | Espacio de clon completo | Σ discos aprovisionados de la plantilla × N por storage destino ≤ `avail` (no thin); thin: V-L10; enlazado: aviso sin bloqueo | Error / Aviso | Ídem |
| V-O21 | Modo de clon | `auto`/`enlazado`/`completo`; `enlazado` solo si todos los discos admiten clon y el storage es el de la plantilla | Error | "Este almacenamiento no permite clonar de forma enlazada." |
| V-O22 | Formato del clon completo | V-09 del storage destino; `format` solo en clon completo | Error | "Este almacenamiento solo admite formato raw." |
| V-O23 | Ajuste de disco | Entero GiB ≥ tamaño actual (solo crecer), ≤ tope V-08 | Error | "Los discos solo pueden crecer." |
| V-O24 | Ajuste de CPU y memoria | V-05 y V-06 | Error | Los de M1 |
| V-O25 | Elegibilidad de nodo por origen | Nodo en línea y con la fuente: ISO/CD de drivers/imagen en storage compartido o presente en ese nodo; plantilla en ese nodo o en storage compartido activo; bridges y storages de la plantilla existen en el nodo | Error | "El nodo «pve2» no tiene la plantilla ni el almacenamiento «local-lvm»." |
| V-O26 | Storage recordado vigente | Existe, activo, con el contenido y en el nodo | Error / Aviso | Ver E-O04 |
| V-O27 | Una transferencia a la vez | Sin otra transferencia, sin lote ni simulación en curso; el resumen no se genera con una transferencia activa | Error | "Hay una transferencia en curso. Espera a que termine o cancélala." |
| V-O28 | Concurrencia de ejecución | Importaciones y clones completos ≤ 2 por storage destino; ≤ 1 por nodo (D-20.5); clones enlazados ≤ 3 por nodo | Control interno | — |
| V-O29 | Disco en cada origen | ISO: `con_disco` recomendado (aviso si no); import: `con_disco = true`; clon: los discos del formulario se ignoran (los de la plantilla) | Error / Aviso | "Para instalar necesitas un disco." |
| V-O30 | Cantidad por origen | N ≤ `MAX_LOTE`; para import y clon completo, además el presupuesto de espacio de V-O19/V-O20 | Error | E-L04 con "Reducir a N" |

---

## 8. Errores (E-O*)

El código técnico va en inglés/español del repositorio (`CodigoError`); el texto es traducible (RNF-O07). Los
textos no incluyen URL completa ni rutas locales.

| ID | Código | Cuándo | Mensaje al usuario | Datos |
|---|---|---|---|---|
| E-O01 | `importar_version_no_soportada` | Importar con versión < 8.4 | "Tu Proxmox {version} no permite importar discos sin ser administrador del servidor. Opciones: instalar desde ISO o clonar una plantilla. Desde Proxmox 8.4 sí es posible." | version |
| E-O02 | `importar_sin_storage_import` | ≥ 8.4 sin storage con `import` | "Para importar discos, pide al administrador que active el contenido «Import» en un almacenamiento de tipo directorio, NFS o CIFS." | candidatos |
| E-O03 | `descarga_url_sin_permiso` | < 8.2 sin `Sys.Modify` en `/`, o ≥ 8.2 sin `Sys.AccessNetwork` | "Descargar desde una dirección web exige permisos de administrador en esta versión. Descarga el archivo en tu equipo y súbelo." / "Falta el permiso Sys.AccessNetwork en el nodo «n»." | version, nodo |
| E-O04 | `storage_recordado_no_disponible` | RF-O06 | "El almacenamiento «{storage}» que usabas en este servidor ya no está disponible o ya no admite {contenido}. Elige otro." | storage, contenido |
| E-O05 | `catalogo_sin_permiso` | Listar contenido da 403 | "No puedes ver los archivos de «{storage}»: falta el permiso Datastore.Audit o Datastore.AllocateSpace." | storage |
| E-O06 | `transferencia_no_verificada` | Tras éxito, el volid o el tamaño no coinciden | "El servidor dice que terminó, pero el archivo no coincide. No lo uses." | volid, esperado, real |
| E-O07 | `transferencia_huella_incorrecta` | Falla el checksum | "El archivo llegó dañado: la huella no coincide. No quedó guardado." | algoritmo |
| E-O08 | `transferencia_cortada` | Red, 5xx o sin progreso en `PARO_SIN_PROGRESO_S` | "Se cortó la conexión mientras se subía el archivo." | bytes, total |
| E-O09 | `archivo_cambio` | El archivo local cambió | "El archivo cambió mientras se subía. Vuelve a intentarlo." | — |
| E-O10 | `nombre_ya_existe` | V-O14 | "Ya existe un archivo con ese nombre en «{storage}». Proxmox lo sobrescribiría. Usa el que ya está o elige otro nombre." | storage, nombre |
| E-O11 | `descarga_url_fallida` | Tarea `download` falla | "El servidor no pudo descargar {archivo} desde {host}: {motivo}. Prueba a descargarlo en tu equipo y subirlo." | host, archivo, motivo |
| E-O12 | `importar_sin_permiso` | Falta `AllocateTemplate`/`AllocateSpace` para la vía | "Falta el permiso {privilegio} en «{ruta}» para importar." | privilegio, ruta |
| E-O13 | `importar_destino_sin_espacio_permiso` | Falta `AllocateSpace` en el destino | "Para guardar el disco importado necesitas el permiso Datastore.AllocateSpace en «{storage}»." | storage |
| E-O14 | `ruta_absoluta_no_permitida` | Ruta del servidor como fuente | "Importar desde una ruta del servidor exige ser administrador (root). Sube el archivo desde tu equipo." | — |
| E-O15 | `imagen_no_admitida` | qcow2 con dependencia, cifrado o vmdk multiarchivo; OVA | "Este disco depende de otro archivo, está cifrado o no es un solo archivo. Conviértelo a un qcow2 independiente antes de subirlo." | motivo |
| E-O16 | `fuente_desaparecio` | Fuente ya no existe al crear | "La imagen/ISO/plantilla «{nombre}» ya no está en el servidor." | nombre |
| E-O17 | `sin_plantillas` | Sin plantillas visibles | "No veo ninguna plantilla con tu cuenta. Pide el permiso VM.Audit o crea la plantilla en Proxmox (clic derecho en la máquina → Convertir en plantilla)." | — |
| E-O18 | `clon_no_posible` | Errores de `clone` (storage no compartido, linked no soportado, parámetros no permitidos) | "No se puede clonar así: {motivo}." | motivo |
| E-O19 | `clon_id_ocupado` | `config file already exists` en clone | "El número de máquina {vmid} se ocupó justo antes de clonar." | vmid |
| E-O20 | `permiso_faltante` | 403 en cualquier acción nueva | "Falta el permiso {privilegio} en «{ruta}». Pídeselo a tu administrador." | privilegio, ruta |
| E-O21 | `fuente_es_url` | Celda `fuente` con URL | "Aquí va el nombre de un archivo del servidor, no una dirección web. Para descargar usa «Descargar en el servidor»." | fila, columna |
| E-O22 | `espacio_insuficiente_transferencia` | V-O13 bloqueante | "El archivo pesa {tamano} y «{storage}» solo tiene {libre} libres." | storage, tamano, libre |
| E-O23 | `transferencia_en_curso` | V-O27 | "Hay una transferencia en curso. Espera a que termine o cancélala." | — |
| E-O24 | `ajuste_post_clon_fallido` | `PUT config`/`resize` falla | "La máquina «{nombre}» se clonó, pero no se pudo {ajuste}. Puedes reintentar los ajustes o deshacer." | nombre, ajuste |

---

## 9. Invariantes (INV-O*)

- **INV-O1:** una transferencia (subida o descarga) solo ocurre por una acción **explícita** del usuario en el
  diálogo de transferencias, con confirmación. Abrir, cargar, aplicar o importar un perfil, lote o CSV, y
  simular, jamás sube, descarga ni crea nada (extiende INV-M1).
- **INV-O2:** la app **nunca sobrescribe** un archivo del servidor: antes de cada subida o descarga, el volid
  destino se comprueba inexistente, y justo antes del primer byte se vuelve a comprobar.
- **INV-O3:** el motor envía como máximo **un** `POST` de creación por VMID, sea `POST …/qemu` o `POST …/clone`
  (INV-L1 extendido). Las escrituras posteriores a la creación (`PUT config`, `PUT resize`) son
  **idempotentes** (valores absolutos, nunca relativos) y solo sobre MVs del libro; no hay otras escrituras
  sobre MVs.
- **INV-O4:** la app **nunca** borra ISOs, imágenes ni plantillas, no convierte MVs en plantilla, no activa
  contenidos de storage ni usa `Datastore.Allocate`, `Sys.Modify` ni `root@pam`.
- **INV-O5:** el archivo local elegido se abre solo para lectura; solo se lee su cabecera (≤ 1 KiB) para
  validarlo, y su contenido completo solo para el hash y la subida; no se ejecuta, interpreta ni modifica, ni
  se invoca ninguna herramienta externa sobre él.
- **INV-O6:** ninguna URL, ruta local absoluta ni checksum de transferencia se escribe en perfiles, lotes, CSV,
  informes ni logs (solo host/nombre de archivo en el log). Ningún secreto en ningún lugar (INV-M2).
- **INV-O7:** todo volid, nombre de archivo y valor de origen que entra en un parámetro de la API pasa por
  lista blanca; ningún valor del servidor o de un archivo del usuario se concatena sin validar (inyección de
  parámetros en `ide2=…`, `import-from=…`).
- **INV-O8:** la fuente (ISO, imagen, plantilla) se revalida contra el servidor antes de cada creación; si ya no
  existe, la MV no se envía.
- **INV-O9:** nada del origen llega a Proxmox sin validación completa, resumen y confirmación (extiende
  INV-M6).
- **INV-O10:** un parámetro opcional que exige un privilegio (`boot`, `resize`) solo se envía con certeza del
  permiso; con duda se omite con aviso.
- **INV-O11:** el storage recordado nunca sustituye a otro sin que el usuario lo vea; un recordado ausente no
  se cambia solo.
- **INV-O12:** en simulación solo hay lecturas (INV-L5), incluidos clon, importación y ajustes.

---

## 10. Constantes propuestas

`CHUNK_SUBIDA` = 1 MiB · `PARO_SIN_PROGRESO_S` = 120 · `MAX_LONG_URL` = 2048 · `MAX_LONG_NOMBRE_ARCHIVO` = 100 ·
`RESERVA_STORAGE_MIB` = 100 · `RESERVA_RAIZ_MIB` = 512 · `CONCURRENCIA_PESADA_POR_STORAGE` = 2 ·
`CONCURRENCIA_ENLAZADO_POR_NODO` = 3 (P-O03; 1 si se rechaza) · `ESPERA_BASE_S` = 600 (M1 P-05) ·
`ESPERA_POR_GIB_S` = 30 · `MAX_CATALOGO` = 500 · `URL_VIRTIO_WIN` y `SHA256_VIRTIO_WIN` (versión fija, DT-O10) ·
mínimos de Windows (V-O07) · constante del orden de arranque (DT-O1). Reutilizadas sin cambio: `MAX_LOTE`
(100), `LONG_NOMBRE_PERFIL`, `MAX_BYTES_*` de archivos de M3.

---

## 11. Casos límite para el probador

1. ISO: 0 bytes, 1 byte, 4 GiB + 1, nombre con espacios, `x.iso,media=disk`, `x.ISO`, doble extensión, sin extensión,
   `.img` qcow2, symlink roto, directorio, `/dev/zero`, tubería.
2. qcow2: versión 1, 2, 3; con *backing file*; cifrado; truncado en 20 bytes; tamaño virtual 0 o 2^62;
   vmdk de descriptor de texto; vmdk *streamOptimized*; raw de 1 MiB; `.ova` y `.ovf`.
3. Catálogo: 0, 1 y 500 volúmenes; 403 en un storage y 200 en otro; volúmenes con nombres inválidos; mismo
   nombre en dos storages; ISO desaparece entre el catálogo y el POST.
4. Nombre existente en el storage; creado por otro entre la comprobación y el POST (riesgo residual);
   mayúsculas/minúsculas.
5. Espacio: storage justo, storage thin, raíz del nodo sin dato, `avail` desconocido.
6. URL: `http`, `https`, `file`, `ftp`, con `user:pass@`, con espacios, 2049 caracteres, IDN, con redirección,
   IP interna; checksum de 63 y 64 caracteres, mayúsculas, con espacios.
7. Permisos: sin `AllocateTemplate`, sin `Sys.AccessNetwork`, sin `VM.Clone`, sin `VM.Config.Disk`, con permisos
   desconocidos, con token sin separación de privilegios.
8. Versiones: 8.0 a 9.2, y una versión forzada mayor.
9. Subida: corte a mitad, 5xx, ticket caducado, cancelación en el hash y en el envío, cierre de la app,
   archivo cambia, dos subidas seguidas, `Content-Length` ausente (no debe ocurrir).
10. Windows: cada `tipo_so` con perfil de 1 núcleo/512 MiB, con disco IDE, con SeaBIOS, sin storage para TPM,
    sin virtio-win, con virtio-win en storage local de otro nodo.
11. Clon: plantilla en LVM grueso, lvmthin, dir qcow2, ZFS; con TPM; con *snapshots*; con `lock`; dos plantillas con
    el mismo nombre; plantilla desaparece; ajustes iguales a la plantilla; disco menor; 100 clones; MACs.
12. Importación: N = 1, 3, 100; storage destino sin espacio; thin; `import` desactivado a mitad; destino `dir` con
    formato `qcow2`.
13. CSV: filas con los tres orígenes; `fuente` URL, ruta, fórmula, vacía; `perfil` + `origen`; separadores `;`
    y `,`; plantilla CSV.
14. Storage recordado: uno, varios, desaparece, cambia de contenido, vuelve; dos perfiles de conexión.
15. Lote en ejecución: intentar subir, cambiar origen, guardar.
16. Rollback de clon enlazado, importación y MV con ISO; informe con archivos subidos.

---

## 12. Pruebas de laboratorio necesarias [LAB]

Laboratorio: PVE 9.2 de un nodo (D-15), storages `local` (directorio) y `lab-lvmthin`, VMIDs 9000 a 9099,
archivos con prefijo `proxlaunch-lab-`. Se ejecutan solo con la variable de entorno explícita (RNF-O10) y
limpian lo que crean. Los pasos que exigen privilegios de administrador (crear el rol, activar `import`,
convertir en plantilla, borrar archivos, mirar `/var/tmp`) los hace el **administrador del laboratorio**
(`root` del laboratorio), no la app. Imágenes sugeridas (I4-§F): **Alpine Linux virt 3.24.4 x86_64**
(`alpine-virt-3.24.4-x86_64.iso`, ≈ 67 MB, con `.sha256`), **CirrOS 0.6.3** (`cirros-0.6.3-x86_64-disk.img`, ≈ 21 MB,
con `SHA256SUMS`, renombrado a `.qcow2`), y virtio-win solo para LAB-M4-07 (≈ 700 MB, opcional).

| ID | Verificar | Cierra |
|---|---|---|
| LAB-M4-01 | **Rol ampliado**: crear `ProxLaunchCreador` con los 14 privilegios y un token; negativos quitando uno a uno `VM.Config.Disk` (¿`boot` da 403?), `VM.Clone`, `Datastore.AllocateTemplate`, `Sys.AccessNetwork`; confirmar que el rol de 10 sigue creando MVs vacías; leer `/access/permissions` para las rutas `/`, `/nodes/pve`, `/storage/*`, `/vms/*` | RF-O24, CA-O08.3, CA-O24.1/4/8, I4-§A |
| LAB-M4-02 | **Detección y catálogo**: `GET /nodes/pve/storage` (campos `content`, `active`, `shared`, `formats`), `GET /storage` (campos con el rol), `?content=iso` y `?content=import` con el rol; storages con nombres engañosos; desactivar `import` (root) y reactivarlo y observar la detección | RF-O04..O06, CA-O04.6, I4-§H |
| LAB-M4-03 | **Subir Alpine con token** + `checksum` sha256: tamaño y sha256 del archivo en el nodo (root) iguales; volid; comprobar que sobrescribe sin aviso (y que la app lo evita); checksum erróneo → tarea falla y no hay archivo; **cancelar** a la mitad (¿queda archivo/temporal en `/var/tmp`?); espacio en `/var/tmp`; `Content-Type` de la parte; `rootfs` en `GET /nodes/pve/status` | RF-O09, O10, O12, CA-O09.9, CA-O12.2, CA-O10.4 |
| LAB-M4-04 | **MV con ISO**: crear con `q35`+OVMF+`efidisk0`+`ide2` (Alpine) + `boot=order=scsi0;ide2;net0`; el rol de 14 sin `VM.Config.CDROM`; negativo sin `VM.Config.Disk` con `boot`; **encender como root del laboratorio** y comprobar por consola que arranca el instalador con disco vacío (OVMF y SeaBIOS); probar `order=ide2;scsi0` si falla; `ide0` y `ide2` juntos | RF-O08, CA-O08.2/3/7/8, DT-O1 |
| LAB-M4-05 | **Hardware de Windows** (sin Windows real): crear con `ostype=win11`, `tpmstate0 version=v2.0`, `efitype=4m`, `agent=1`, segundo CD en `ide0` (Alpine como sustituto) y `scsi0` con `iothread`/`discard`; la config coincide; la lista de privilegios necesaria para `tpmstate0`/`ostype`/`machine`/`agent` es la del rol; formato del TPM en `local` y `lab-lvmthin`; si hay ISO de RHEL 10, comprobar `x86-64-v2-AES` vs `x86-64-v3` | RF-O13, CA-O13.1..5, CA-O13.4 |
| LAB-M4-06 | **Descarga por URL** de Alpine con `Datastore.AllocateTemplate`+`Sys.AccessNetwork` en `/nodes/pve`; `query-url-metadata`; negativo sin `Sys.AccessNetwork`; checksum erróneo; `verify-certificates`; URL inexistente; si el nodo anidado no tiene Internet, documentarlo y usar un servidor HTTP local; **¿trae el log de la tarea porcentaje?** | RF-O11, CA-O11.1..8 |
| LAB-M4-07 | **virtio-win** (opcional): `query-url-metadata` de la URL fija y tamaño real, descarga completa, sha256 real (para fijar `SHA256_VIRTIO_WIN`) | RF-O14, CA-O14.6 |
| LAB-M4-08 | **Importación**: activar `import` en `local` (root); subir `proxlaunch-lab-cirros.qcow2` con token; qcow2 con *backing file* creado a mano → el servidor lo rechaza igual que la app; `.ova` rechazada; **¿qué devuelve `size` en `content=import`: tamaño del archivo o virtual?**; negativo: ruta absoluta (esperado "Only root can pass arbitrary filesystem paths") | RF-O15, O16, CA-O16.2/4/6, CA-O15.3 |
| LAB-M4-09 | **Crear con `import-from`** en `lab-lvmthin` con el rol de 14 (+ variantes del permiso de lectura de la fuente); formato resultante (raw), tamaño virtual, tiempo; lote de 3; ¿log con progreso?; `resize` absoluto; fallo a mitad y ¿volumen suelto?; negativo sin `AllocateSpace` en destino; destino `local` con `format=qcow2` | RF-O17, O18, CA-O17.x, CA-O18.x, CA-O30.4 |
| LAB-M4-10 | **Clon**: convertir una MV CirrOS en plantilla (root); 3 clones enlazados en paralelo en `lab-lvmthin` (¿lock compartido?), tiempos con 1 y con 3 simultáneos (decide P-O03); clon completo a `local` con `format=qcow2`; `tags` por `PUT`; `config` y `resize`; MACs distintas; TPM; negativos sin `VM.Clone`, con `storage` en enlazado, linked en storage sin soporte; no se puede borrar la plantilla con clones enlazados | RF-O19..O23, CA-O21.x, CA-O22.x |
| LAB-M4-11 | **Rollback**: borrar con `destroy-unreferenced-disks=0` los clones enlazados, completos y las MVs de importación e ISO; plantilla, ISO e imagen intactas; los archivos subidos siguen (no se pueden borrar con el rol) | RF-O30, CA-O20.8, CA-O25.2 |
| LAB-M4-12 | **Lote por filas mixto** con CSV (3 orígenes) end-to-end: simulación solo GET (contador de métodos), creación, `config` por fila, rollback; INV-L1 con inyección de fallos sobre `clone` en el mock | RF-O28..O30, INV-O3 |
| LAB-M4-13 | **Capacidades**: `GET /version` y `/access/permissions` con rol de 10 y de 14, con administrador y sin `Sys.Audit`; el objeto `CapacidadesOrigen` coincide con lo observado | RF-O02, O24 |
| LAB-M4-14 | **Cancelación y cortes**: matar la conexión durante la subida (red), `Ctrl-C` a la app (cierre), ticket caducado simulado; el estado se verifica en el catálogo; sin reintento automático | RNF-O03, O12, CA-O09.7 |

Limpieza: eliminar MVs 9000–9099 (D-21), archivos `proxlaunch-lab-*` (root del lab), desactivar `import` en
`local`, eliminar el rol y tokens de prueba (D-15).

Mocks a preparar (sintéticos desde respuestas reales): matriz de versiones 8.0 a 9.2; inventario de 3 nodos
con storages `iso`/`import`/`images` compartidos y locales; catálogos de 0 a 500 volúmenes; `permissions` con
cada combinación del rol; respuestas de `upload`, `download-url` y `query-url-metadata`; respuestas de `clone` con
cada error de I4-§D; archivos de ejemplo de cabecera qcow2/vmdk/raw; versión 1 y 2 de lotes y perfiles.

---

## 13. Trazabilidad con D-24

| D-24 | Requisitos |
|---|---|
| 1. Instalar desde ISO: catálogo | RF-O07, RF-O08 |
| 1. Subir ISO | RF-O09, RF-O10, RF-O12, RF-O25 |
| 1. Descargar por URL (≥ 8.2, `Sys.AccessNetwork`) | RF-O11, RF-O02, RF-O24 |
| 1. Asistente Windows (virtio-win `ide0`, q35, OVMF+efidisk 4m, TPM, ostype) y orden de arranque | RF-O13, RF-O14, RF-O08 |
| 2. Importar qcow2/vmdk/raw (≥ 8.4, `import`, copia por MV, espacio = virtual × N) | RF-O15..O18 |
| 3. Clonar plantilla (enlazado/completo, paralelo, ajustes, plantilla por nodo) | RF-O19..O23 |
| 4. Perfiles, lotes guardados, CSV, motor, INV-L1, rollback | RF-O26..O30, INV-O3 |
| 5. Datos de API por versión y permisos | Sección 3, RF-O02, RF-O24 |
| 6. Storage por servidor (detectar, recordar, avisar) | RF-O04..O06 |
| 7. Ajustes (≥ 8.4, `Sys.AccessNetwork`, virtio-win, subidas no deshacibles, nombre existente) | RF-O02, O10, O11, O14, O25 |
| 8. Rol ampliado, sin `Datastore.Allocate` | RF-O24, INV-O4 |
| Fuera de alcance (OVA, VMware, desatendida, encender, convertir en plantilla, activar `import`) | Sección 1.3, INV-O4 |

Trazabilidad RF a criterio a prueba: cada `CA-Onn.y` se prueba con test unitario/mock (capa núcleo) salvo los
marcados [LAB], que se verifican en el laboratorio (LAB-M4-nn de la sección 12). Los RNF se prueban con
mediciones (`tracemalloc`, bucle de eventos), matriz manual (plataformas) y mocks.

---

## 14. Enmiendas a M1, M2, M3 y al código

1. **M1 V-20 (origen):** deja de ser «solo `disco_vacio`»; se sustituye por V-O01 (4 valores con detalle).
2. **M2 INV-L1/INV-L4:** las escrituras permitidas del motor ahora son (a) `POST …/qemu`, (b) `POST …/clone`,
   (c) `PUT …/config` y `PUT …/resize` sobre MVs del libro, (d) el rollback de RF-L18. Las **transferencias**
   (`upload`, `download-url`) no son del motor y solo ocurren por INV-O1.
3. **M2 D-20.5 (concurrencia):** se añade el tope por storage destino y, sujeto a P-O03, 3 clones enlazados
   por nodo.
4. **M1 P-05 (espera máxima de tarea):** para importación y clon completo la espera crece con el tamaño
   (`ESPERA_BASE_S`, `ESPERA_POR_GIB_S`); sigue sin declarar fallo al vencer.
5. **M3 CA-P01.2, CA-X02.6, CA-P02.6:** un `origen` distinto de `disco_vacio` ya no se rechaza en perfiles ni
   lotes; sigue siendo solo un nombre que se resuelve contra el servidor (nunca ruta ni URL). Los perfiles de fábrica
   existentes mantienen `disco_vacio`.
6. **Código `nucleo/capacidades.py`:** `Funcion.IMPORTAR_DISCO` está en (8, 2) como entrada de ejemplo; por I4-§C debe
   ser **(8, 4)**; añadir `DESCARGAR_URL` (8, 2) y `SUBIR_IMAGEN_DISCO` (8, 4). El comentario "Entrada de EJEMPLO"
   se retira. Es un cambio de implementación, no de este documento.
7. **M3 RF-C03 (columnas del CSV):** se añaden `origen`, `fuente`, `so`, `virtio`, `modo_clon`; `cpu`, `memoria`
   y `disco` cambian de significado solo en filas de clon (ajustes) y de importación (`disco` = ampliar).
8. **M3 RF-X01 (versionado):** `version_formato = 2` solo cuando hay origen ≠ `disco_vacio` (DT-O15); migración
   v1 a v2 es la identidad.
9. **M1 `PerfilConexion`:** tres campos opcionales (`storage_mv`, `storage_iso`, `storage_import`), `None` por defecto.
10. **M1 `construir_parametros`:** nuevas salidas (`ide0`, `ide2`, `boot`, `ostype`, `tpmstate0`, `agent`,
    `import-from`) y numeración de ranuras IDE con ISO; creación por `clone` en un constructor aparte.
11. **`docs/guia-usuario.md` y ayuda «¿Cómo creo un API Token?»:** lista de privilegios de 10 a 14 (RF-O24,
    RF-O32), tarea del `documentador`.
12. **`docs/decisiones.md`:** el orquestador debe registrar una **D-25** con las decisiones aprobadas de las
    preguntas P-O01 a P-O03 y las DT-O que apruebe.

---

## 15. Decisiones técnicas del analista (DT-O)

Resuelven puntos técnicos con recomendación justificada; el orquestador puede vetarlas.

- **DT-O1 Orden de arranque** `order=<primer disco>;ide2[;net0]` (I4-§A recomienda `scsi0;ide2;net0`): con el CD
  montado y el disco primero, tras instalar arranca del disco sin tocar nada; con disco vacío el firmware salta
  al CD. Si LAB-M4-04 muestra que OVMF no arranca el CD así, se invierte con una sola constante.
- **DT-O2 Ranuras IDE:** `ide2` = ISO del SO, `ide0` = virtio-win (guías oficiales, I4-§A); los discos IDE usan
  `ide1`/`ide3`. Evita colisiones sin impedir IDE.
- **DT-O3 Checksum siempre:** sha256 local en toda subida (un paso de lectura extra con barra "calculando
  huella"): garantiza integridad (el servidor lo verifica) a cambio de tiempo.
- **DT-O4 Nodo de la subida:** el nodo al que está conectada la sesión si el storage está activo en él; si no,
  otro nodo en línea con el storage activo (el storage local solo en su nodo).
- **DT-O5 Firmware Windows:** OVMF + `q35` en todos los Windows (D-24.1), no solo en 11. Windows 10/2016/2019
  funciona con UEFI y es lo que usan las guías de Proxmox.
- **DT-O6 TPM:** obligatorio en Windows 11; activado por defecto en Server 2022/2025 (I4-§G.4), desactivado en
  Windows 10 y Server 2016/2019.
- **DT-O7 `http://`:** solo avanzado y con confirmación; `https://` por defecto.
- **DT-O8 TPM sin `format`:** el estado TPM es raw fijo hasta 9.0 y qcow2 opcional en 9.1+; no se envía `format`.
- **DT-O9 Disco de Windows:** `scsi` + `virtio-scsi-single` por defecto (guías oficiales, requiere cargar el
  controlador); disco SATA como alternativa en avanzado.
- **DT-O10 virtio-win:** URL **fija** de una versión verificada (no `latest`/`stable`, que se mueven y pueden
  traer versiones con problemas, I4-§E) y checksum embebido; se fija en LAB-M4-07.
- **DT-O11 Clúster con ISO local:** solo elegibilidad por nodo y explicación; sin "subir a todos los nodos"
  (Podría posterior).
- **DT-O12 Extensión de la imagen:** se corrige a la del contenido detectado (un `.img` qcow2 se sube como
  `.qcow2`) porque la extensión manda en `content=import`.
- **DT-O13 Plantilla por nombre:** la referencia en lotes guardados y CSV es por nombre (el VMID es del
  sitio); varias plantillas con el mismo nombre en nodos con storage local se tratan como una réplica.
- **DT-O14 Etiquetas del clon:** `clone` no admite `tags`; se aplican con `PUT config` como unión de las de la
  plantilla y las del lote.
- **DT-O15 Versión de formato:** se escribe `2` solo si hace falta, para que un archivo sin origen nuevo siga
  abriéndose en un MVP 3.
- **DT-O16 Sin `boot` ante la duda:** con permisos desconocidos o ausentes se omite y se avisa (INV-O10).
- **DT-O17 Una sola transferencia a la vez** y nunca durante un lote o simulación (simplifica estados y evita
  saturar el nodo).

---

## 16. Riesgos y notas para la arquitectura

1. **Sobrescritura silenciosa de Proxmox** y carrera entre comprobar y subir: riesgo residual documentado
   (CA-O10.2); no hay forma de cerrarlo sin `Datastore.Allocate`.
2. **Espacio en `/var/tmp` del nodo**: sin un dato fiable, la comprobación es un aviso (CA-O10.4).
3. **Cancelar una subida** puede dejar un temporal en el servidor; su alcance se mide en LAB-M4-03.
4. **Cancelar una descarga en el servidor no es posible** sin `Sys.Modify`: solo "dejar de esperar".
5. **El tamaño virtual de una imagen ya existente** quizá no se pueda conocer por API; el cálculo de
   espacio queda como aviso (LAB-M4-08).
6. **Linked clones**: crean dependencia con la plantilla; el usuario no puede borrar la plantilla mientras
   existan (P-O01).
7. **Windows sin los drivers VirtIO** no ve el disco ni la red: es el principal punto de fallo para un usuario
   sin experiencia (RF-O14, DT-O9).
8. **RHEL 10 y derivados** exigen CPU x86-64-v3 (conocimiento del analista, no verificado en I4); con el tipo
   por defecto `x86-64-v2-AES` no arrancan (CA-O13.4, **[A]**). Importante para el flujo de Red Hat del usuario.
9. **Claves Secure Boot de Microsoft 2011** (`pre-enrolled-keys`) caducan en junio de 2026; 9.1+ inscribe las de
   2023; aviso informativo en 8.x–9.0, sin acción (I4-§E).
10. **`VM.Config.CDROM` y TPM**: si LAB-M4-04/05 muestran que el rol de 14 no basta, el rol y la guía crecen.
11. **Tamaño de `construir_parametros`** y del motor: el clon introduce un segundo tipo de creación; la
    arquitectura debe separar `crear_por_post` y `crear_por_clon` con el mismo contrato de libro/INV-L1.
12. **Dependencia nueva** posible para el *streaming* multipart (p. ej. `requests-toolbelt`): decisión de la
    arquitectura, con auditoría de licencia (D-19) y sin romper `trust_env = False` (D-18).
13. **Doble lectura del archivo** (hash y envío): para ISOs de decenas de GiB duplica el tiempo; aceptado por
    integridad (DT-O3).
14. **Secretos en URLs:** la app no las almacena, pero el usuario puede pegarlas en el diálogo (visibles en
    pantalla); no se registran (INV-O6).

---

## 17. Preguntas abiertas

Solo las que de verdad necesitan decisión del usuario. Cada una con opciones y recomendación.

**P-O01 — Modo de clon por defecto («Automático»).**
- A) **Automático → enlazado cuando el storage lo permite, completo si no.** Muy rápido y casi sin espacio
  (útil para lotes de decenas de MVs); costo: las MVs dependen de la plantilla y Proxmox impide borrarla
  mientras existan.
- B) Siempre completo por defecto (copia independiente); más lento y con más espacio (N × disco); enlazado
  solo en avanzado.
- C) Preguntar cada vez.
- **Recomendación: A**, con aviso de la dependencia y B en avanzado. Afecta: RF-O20, RF-O31, CA-O20.1/5.

**P-O02 — Perfiles de fábrica nuevos con el MVP 4 (Windows 11, Windows Server, Linux/Red Hat).**
- A) Añadir 3 perfiles de hardware de fábrica (sin ISO), además de los 6 de M3.
- B) No añadir; el usuario crea los suyos con «Guardar como perfil de máquina».
- **Recomendación: A** (Podría): ahorra pasos a quien instala Windows a menudo; no cambia P-M05 A. Afecta:
  RF-O31. Se implementa al final si hay tiempo.

**P-O03 — Concurrencia de clones enlazados dentro de un mismo nodo (enmienda a D-20.5: 1 MV por nodo).**
- A) Permitir hasta 3 clones **enlazados** simultáneos por nodo (son operaciones de metadatos de segundos;
  Proxmox permite varios por lock compartido); importación y clon completo siguen en 1 por nodo y 2 por
  storage.
- B) Mantener 1 por nodo para todo.
- **Recomendación: A**, condicionada a LAB-M4-10 (si la medición muestra errores de bloqueo o poca mejora, pasa a
  1 y la constante vale 1). Afecta: RF-O21, RNF-O04, V-O28.
