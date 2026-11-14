# Requisitos del MVP 3 — ProxLaunch (perfiles de MV, lotes guardados e importación CSV)

Versión del documento: 1.0 (2026-11-13) · Estado: borrador para revisión del orquestador

Fuentes, en orden de autoridad: `docs/decisiones.md` (D-01 a D-21 y "Correcciones técnicas",
abreviadas **CT-n**), `docs/requisitos/mvp1.md` (**M1**) y `docs/requisitos/mvp2.md` (**M2**),
ambos vigentes salvo las enmiendas de la sección 14; `docs/arquitectura/mvp2.md`;
`docs/investigacion/f1-api-proxmox.md` (**F1**); `docs/bitacora.md` (entradas 13 y 14) y el código
existente (`nucleo/modelos/vm.py`, `nucleo/validacion.py`, `nucleo/lote/`, `nucleo/persistencia/`,
`interfaz/vistas/formulario_vm.py`, `interfaz/vistas/bloque_lote.py`). Si se contradicen, manda
`decisiones.md`. Lo que depende de la API y no consta en F1 ni en `tests/datos/respuestas/9.2-lab/`
se marca **[LAB]** (hipótesis a verificar, sección 12) y no puede darse por cierto.

Convenciones (las de M2, con prefijos propios para no chocar):
- **Prioridad:** Debe / Debería / Podría.
- **IDs:** RF-Pnn (perfiles de MV), RF-Xnn (archivos: formato, lectura y escritura), RF-Gnn (lotes
  guardados), RF-Cnn (importación CSV), RNF-Mnn, CA-<RF>.y (criterio y del requisito), V-Mnn (regla
  de validación), E-Mnn (error), INV-Mn (invariante), LAB-M3-nn (prueba de laboratorio), P-Mnn
  (pregunta abierta).
- Los criterios usan "Dado / Cuando / Entonces". "Mock" = respuesta simulada basada en respuestas
  reales (D-15). "Laboratorio" = Proxmox VE 9.2 anidado de **un solo nodo** (D-15): lo multinodo y
  8.x se verifican solo con mocks.
- Unidades: las de M1 (discos en GiB enteros, memoria en MiB, CT-6) en el modelo y en los archivos
  JSON; en la interfaz y en el CSV el usuario ve GiB (ver RF-C04).

Términos (conviene no mezclarlos):
- **Perfil de MV** (en la interfaz, **«Perfil de máquina»**): conjunto de ajustes de hardware
  reutilizable (cómputo, firmware, discos, red). **No** es el **perfil de conexión** de D-09
  (servidor, usuario, realm). El código y los documentos dicen siempre "perfil de MV" o "perfil de
  conexión" (ver P-M12).
- **Lote guardado**: archivo con la *definición* de un lote (RF-G01). **No** es el plan ni el libro
  del MVP 2.
- **Lote por filas**: lote cuyas MVs tienen cada una su propia configuración y nombre explícito
  (RF-C08). Enmienda D-20 (11); ver P-M01.
- **Capa 1 / capa 2 de validación**: capa 1 = comprobaciones del contenido del archivo sin servidor
  (tipos, rangos, formato); capa 2 = comprobaciones contra el inventario del servidor conectado
  (nodo, storage, bridge, VMID, espacio) con el motor de M2.

---

## 1. Alcance

### 1.1 Dentro del MVP 3 (D-12)
1. **Perfiles de MV**: de fábrica (de solo lectura) y del usuario (crear, editar, renombrar,
   duplicar, eliminar); aplicarlos al formulario; compatibilidad con la versión de Proxmox y con el
   inventario del servidor conectado; importar y exportar para compartir entre equipos.
2. **Guardar y cargar lotes**: archivo con la definición del lote (homogéneo o por filas), cargado
   siempre con revalidación completa.
3. **Importación desde CSV** de una lista de MVs heterogéneas, con vista previa y errores por fila y
   columna; plantilla CSV descargable; exportación segura de CSV (anti inyección de fórmulas).
4. Formato de archivos versionado, lectura segura de archivos de terceros y escritura atómica sin
   secretos (RF-X01..X05).

### 1.2 Fuera del MVP 3
- Origen del SO distinto de "disco vacío" (ISO, OVA, VMware): MVP 4 (D-13). Los perfiles y lotes
  llevan el campo `origen` con el único valor `disco_vacio`; un archivo con otro valor se rechaza
  (V-20 de M1) y **no** se intenta descargar ni abrir nada.
- TPM, `ostype`, encendido automático (M1 P-04, P-09, P-15): no se guardan en perfiles. El campo
  `origen` es el único "reservado" para el MVP 4; el formato versionado (RF-X01) permite añadir los
  demás sin romper archivos antiguos.
- Biblioteca interna de lotes, historial de lotes ejecutados, retomar un libro (P-L04 de M2).
- Sincronización de perfiles entre equipos por red, firma digital de archivos, cifrado de archivos
  (ver sección 15, riesgos).
- Editar por MV dentro de la interfaz (CA-L04.5 de M2 sigue vigente): en un lote por filas se edita el
  archivo y se vuelve a importar.
- Preparar lotes sin conexión con inventario ficticio (P-M08; recomendado diferirlo).
- Dividir automáticamente un CSV de más de `MAX_LOTE` filas en varios lotes (P-M10).
- LXC, editar o borrar MVs existentes, monitoreo, HA.

### 1.3 Supuestos
- S-M1: la plantilla sigue siendo `ConfiguracionVM`; el formulario de M1/M2 es el único editor de
  perfiles y de lotes (no hay un editor aparte). Aplicar, editar y guardar un perfil usa el
  formulario (consistente con S-L1 de M2).
- S-M2: las MVs se siguen creando detenidas y sin iniciar (S-L2 de M2).
- S-M3: **nodo, almacenamiento (storage) y bridge son específicos del sitio.** El nodo nunca se
  guarda en un perfil; storage y bridge solo como *pistas* opcionales (RF-P06, P-M04). En un lote
  guardado sí se guardan tal como el usuario los definió (son parte de su decisión) y se revalidan al
  cargar (RF-G04).
- S-M4: el lote guardado es **autocontenido**: lleva una copia de la configuración, no una referencia a
  un perfil (P-M03). Editar o borrar un perfil no cambia lotes ya guardados.
- S-M5: en **modo básico** el usuario elige perfil, nombre y cantidad (D-14); puede "Guardar como perfil
  de máquina". Administrar (editar, renombrar, duplicar, eliminar, importar, exportar) está en modo
  avanzado.
- S-M6: los archivos del MVP 3 son JSON UTF-8 (perfiles y lotes) y CSV (importación y exportación). No se
  usa ningún formato que pueda ejecutar código (pickle, YAML con etiquetas, hojas con macros).
- S-M7: abrir, cargar o importar requiere sesión conectada para llegar al formulario, porque este depende
  del inventario; las operaciones puramente de archivo (administrar perfiles, exportar/importar perfiles,
  descargar la plantilla CSV, leer y revisar un CSV en capa 1) funcionan sin conexión (P-M08).
- S-M8: el nombre de un perfil de conexión **no** se guarda en los archivos (privacidad, RNF-M03).
- S-M9: el catálogo de modelos de CPU de un nodo puede consultarse con
  `GET /nodes/{n}/capabilities/qemu/cpu` **[LAB]** LAB-M3-04; mientras no se verifique, `tipo_cpu` solo se
  valida por formato (V-22 de M1).

### 1.4 Casos límite generales
- Archivo vacío, de 0 bytes, de varios GB, un directorio, un dispositivo o una tubería con nombre.
- JSON válido con la estructura equivocada, tipos erróneos (`"cores": "dos"`, `true` como número),
  `NaN`/`Infinity`, claves repetidas, anidamiento extremo, cadenas enormes, caracteres de control y de
  dirección de texto (RTL).
- Archivo creado por una versión **más nueva** de ProxLaunch; por una más antigua (migración).
- Perfil con almacenamiento o bridge que no existe en el servidor actual; nodo que no existe; servidor
  de otra versión de Proxmox.
- Lote cargado en un servidor distinto del que se guardó; con VMIDs fijos que ya están ocupados.
- CSV con `;` y Windows-1252 (Excel en español), con `,` y UTF-8 con BOM, con UTF-16, con líneas en
  blanco, con filas de más de 100, con comillas y saltos de línea dentro de celdas, con decimales con
  coma, con celdas que empiezan por `=`.
- Archivo abierto en Excel y bloqueado (Windows); ruta con espacios, acentos o más de 260 caracteres;
  carpeta sin permiso de escritura; disco lleno al guardar.
- Dos instancias de ProxLaunch escribiendo el mismo almacén de perfiles.

---

## 2. Qué guarda cada artefacto

Matriz de contenido (✔ guarda, ✘ no guarda, ◐ guarda como pista o con condición). **Nunca** hay
secretos, host, IP ni usuario en ningún archivo (INV-M2).

| Dato | Perfil de MV | Lote guardado (homogéneo) | Lote por filas / CSV |
|---|---|---|---|
| Nombre y descripción del perfil/lote | ✔ | ✔ (nombre del lote) | ✔ (nombre del lote) |
| firmware, sockets, cores, tipo de CPU, memoria, ballooning | ✔ | ✔ | ✔ por fila |
| con_disco, discos (tamaño, bus, formato, discard, ssd, iothread) | ✔ | ✔ | ✔ por fila |
| controlador SCSI, red (modelo, VLAN) | ✔ | ✔ | ✔ por fila |
| `origen` | ✔ (`disco_vacio`) | ✔ | ✔ |
| storage de cada disco y del efidisk | ◐ pista (`*_preferido`) | ✔ real | ✔ real por fila |
| bridge de cada red | ◐ pista | ✔ real | ✔ real por fila |
| nodo | ✘ | ◐ solo en destino "Un nodo"/"Nodos elegidos" | ◐ por fila (columna `nodo`) |
| cantidad, patrón de nombres | ✘ | ✔ | ✘ (nombre explícito por fila) |
| VMID | ✘ | ◐ solo `vmid_inicial` si lo fijó el usuario (avanzado) | ◐ por fila si hay columna `vmid` |
| algoritmo de reparto | ✘ | ✔ | ✔ |
| `etiquetar` (marca del lote) | ✘ | ✔ | ✔ |
| etiquetas `proxlaunch;lote-<id>` y id de lote | ✘ | ✘ (el id se genera en cada ejecución) | ✘ |
| política thin y casilla "Entiendo el riesgo" | ✘ (CA-L08.6 de M2) | ✘ | ✘ |
| plan (VMIDs reservados), libro, UPID, informe | ✘ (INV-M5) | ✘ | ✘ |
| nombre del perfil de conexión, host, IP, usuario, huellas | ✘ | ✘ | ✘ |

---

## 3. Requisitos funcionales

### A. Perfiles de MV

#### RF-P01 Modelo del perfil de MV — Debe — D-12, D-13, D-14
Un perfil tiene: `id` (único), `nombre` (1–`LONG_NOMBRE_PERFIL` = 60 caracteres tras recortar espacios),
`descripcion` (0–`LONG_DESCRIPCION` = 200), origen (`fabrica` o `usuario`) y una configuración con los
campos de la columna "Perfil de MV" de la sección 2. No tiene `vmid`, `nombre` de MV, `nodo` ni
`etiquetas`.
- CA-P01.1 Dado un perfil, entonces su serialización contiene exactamente los campos permitidos (lista
  blanca) y un test recorre todos los campos de `ConfiguracionVM` comprobando que `vmid`, `nombre`, `nodo`
  y `etiquetas` no se serializan.
- CA-P01.2 Dado un perfil con `origen = disco_vacio`, entonces es válido; con cualquier otro valor,
  entonces V-20 (M1) lo rechaza al leerlo y no se aplica.
- CA-P01.3 Dado el nombre de perfil, entonces V-M01 lo valida (recorte, longitud, sin caracteres de
  control, normalización Unicode NFC, único sin distinguir mayúsculas entre fábrica y usuario).
- CA-P01.4 Dado un perfil con `memoria_mib`, `cores`, `sockets`, `discos` y `redes`, entonces cada valor
  cumple las reglas V-05..V-15 de M1 *que no dependen del servidor* (capa 1): se comprueban al
  guardar y al leer.
- CA-P01.5 Dado un perfil con `con_disco = false`, entonces se admite sin discos (equivale a M1 "sin
  disco").
- CA-P01.6 Un perfil nunca contiene un secreto: un test con centinela comprueba que ninguna ruta de
  guardado, exportación o log lo incluye (RNF-M03).

#### RF-P02 Perfiles de fábrica — Debe — D-14
La aplicación incluye perfiles de fábrica, **de solo lectura**, con identificador estable
(`fabrica.<clave>`) y nombre y descripción traducibles (RNF-M04). La lista propuesta está en la sección 8
(P-M05).
- CA-P02.1 Dado el selector de perfiles, entonces los de fábrica aparecen primero, con un indicador de
  texto "De fábrica" (no solo icono ni color).
- CA-P02.2 Dado un perfil de fábrica, entonces "Editar", "Renombrar" y "Eliminar" están deshabilitados con
  la explicación "Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión.";
  "Duplicar" y "Exportar" están disponibles.
- CA-P02.3 Dado cada perfil de fábrica, entonces pasa la validación de capa 1 y, contra el inventario de
  los mocks de 8.0, 8.x y 9.x con un storage y un bridge normales, pasa la validación completa
  (`validar_vm`) sin errores (test parametrizado).
- CA-P02.4 Dado el perfil de fábrica predeterminado ("Servidor pequeño"), entonces su configuración es
  idéntica a `configuracion_por_defecto` de M1 (2 núcleos, 2 GiB, un disco de 32 GiB, `virtio-scsi-single`,
  una red `virtio`); test de equivalencia (RF-P12).
- CA-P02.5 Dado una nueva versión de la aplicación que cambia un perfil de fábrica, entonces los
  perfiles **del usuario** (incluidas las copias que hizo) no cambian.
- CA-P02.6 Los perfiles de fábrica describen solo hardware: ninguno nombra un sistema operativo como si
  lo instalara (el origen del SO es del MVP 4, D-13) y la descripción lo dice ("Sin sistema operativo:
  la máquina se crea con un disco vacío").
- CA-P02.7 Los identificadores `fabrica.*` están reservados: ningún perfil de usuario ni importado puede
  tenerlos (V-M02).

#### RF-P03 Crear perfiles del usuario desde el formulario — Debe — D-14
"Guardar como perfil de máquina…" toma la configuración actual del formulario (sin nombre de MV, VMID ni
nodo) y la guarda.
- CA-P03.1 Dado el formulario con una configuración válida, cuando el usuario escribe un nombre válido y
  acepta, entonces el perfil queda guardado y seleccionable en el selector sin reiniciar la aplicación.
- CA-P03.2 Dado el formulario con errores de capa 1 (por ejemplo, 0 núcleos), entonces "Guardar como
  perfil" indica qué corregir y no guarda nada. Errores de capa 2 (storage inexistente en otro nodo) **no**
  impiden guardar (son del sitio, RF-P06).
- CA-P03.3 Dado el diálogo de guardado, entonces muestra la casilla "Recordar los nombres de
  almacenamiento y red (solo sirven en servidores que los tengan)", **marcada por defecto** para
  perfiles propios (RF-P06); con ella desmarcada, el perfil no lleva pistas.
- CA-P03.4 Dado un nombre ya usado (fábrica o usuario, sin distinguir mayúsculas), entonces V-M01 bloquea
  con "Ya existe un perfil con ese nombre. Elige otro." y propone «<nombre> (2)».
- CA-P03.5 Dado que ya hay `MAX_PERFILES_USUARIO` (100) perfiles del usuario, entonces V-M03 bloquea con
  "Llegaste al máximo de 100 perfiles. Elimina alguno para crear otro."
- CA-P03.6 Dado un error de escritura (disco lleno, sin permisos), entonces se muestra E-M08, el perfil no
  queda a medias y el archivo anterior sigue intacto (escritura atómica, RF-X03).
- CA-P03.7 Dado el modo básico, entonces la acción "Guardar como perfil de máquina" está disponible; la
  descripción y las pistas se ven en modo avanzado y usan sus valores por defecto en básico.

#### RF-P04 Editar, renombrar, duplicar y eliminar perfiles del usuario — Debe — D-14
- CA-P04.1 **Editar**: dado un perfil del usuario aplicado al formulario y modificado, cuando el usuario
  pulsa "Guardar cambios en el perfil «X»", entonces se sobrescribe ese perfil (mismo `id`); con "Guardar
  como nuevo…", se crea otro. No existe un editor aparte (S-M1).
- CA-P04.2 **Renombrar**: cambia `nombre` (y opcionalmente `descripcion`) sin tocar la configuración; V-M01
  aplica igual; el `id` no cambia.
- CA-P04.3 **Duplicar**: crea un perfil nuevo (id nuevo) con nombre «Copia de <nombre>» (texto traducible,
  con sufijo " (2)", " (3)" si ya existe); sirve también para perfiles de fábrica.
- CA-P04.4 **Eliminar**: pide confirmación con el nombre ("¿Eliminar el perfil «X»? Los lotes que ya
  guardaste no cambian."), con foco inicial en "Cancelar"; tras eliminar, desaparece del selector. No
  afecta a lotes guardados (S-M4).
- CA-P04.5 Dado un perfil eliminado o cambiado mientras el formulario lo tenía aplicado, entonces el
  formulario conserva sus valores (el perfil es una plantilla de partida, no un vínculo) y el selector
  muestra "Personalizado".
- CA-P04.6 Dado el modo básico, entonces editar/renombrar/duplicar/eliminar no se muestran (S-M5); en
  avanzado, sí (menú "Administrar perfiles…").
- CA-P04.7 Dado cualquiera de las operaciones, entonces el resultado queda en disco antes de devolver el
  control (RF-X03) y un test relee el almacén y lo comprueba.
- CA-P04.8 Dado dos instancias de la aplicación, entonces la última escritura gana pero nunca produce un
  archivo ilegible (escritura atómica); no hay bloqueo entre instancias (se documenta).

#### RF-P05 Aplicar un perfil al formulario — Debe — D-14
- CA-P05.1 Dado un perfil elegido en el selector, entonces el formulario recibe firmware, cómputo,
  discos, controlador y redes del perfil; **no** cambia nombre/prefijo, cantidad, destino, VMID inicial ni
  nodo (los del lote).
- CA-P05.2 Dado que el formulario tiene cambios hechos a mano desde la última aplicación, cuando se elige
  otro perfil, entonces se pide confirmación ("Se reemplazarán los ajustes de hardware que cambiaste.")
  con "Cancelar" por defecto; si el formulario no tiene cambios manuales, se aplica sin preguntar.
- CA-P05.3 Dado el modo básico y un perfil con campos que básico oculta (bus, formato, IO Thread, tipo de
  CPU, ballooning, discard, ssd), entonces los valores del perfil **se aplican igualmente** y el resumen
  los muestra (M1 CA-24.5).
- CA-P05.4 Dado el formulario recién abierto, entonces el perfil seleccionado es el predeterminado (RF-P12).
- CA-P05.5 Dado que se aplica un perfil, entonces el resumen y la validación de M1/M2 se recalculan y el
  resumen previo queda invalidado (CA-L04.3 de M2).
- CA-P05.6 Dado un lote en ejecución, entonces el selector y las acciones de perfil están deshabilitados
  (M2 CA-L10.9).
- CA-P05.7 Dado "Aplicar perfil", entonces no se envía ninguna petición de escritura a Proxmox
  (INV-M1).
- CA-P05.8 Dado el perfil aplicado, entonces el formulario muestra el nombre del perfil de origen como
  texto informativo; al editar un campo cambia a "<perfil> (modificado)".

#### RF-P06 Tratamiento de nodo, almacenamiento y bridge — Debe — D-08, S-M3
Nodo, storage y bridge dependen del sitio. Regla: **el nodo nunca se guarda**; storage y bridge se guardan
solo como **pistas** (`storage_preferido` por disco, `storage_efi_preferido`, `bridge_preferido` por red),
y se resuelven contra el inventario al aplicar (P-M04).
- CA-P06.1 Dado un perfil con pista de storage que existe, está activo y admite `images` en el nodo
  efectivo del formulario (V-17 de M1), entonces se usa esa pista.
- CA-P06.2 Dado una pista que no existe o no sirve en el nodo, entonces se usa el storage por defecto
  (`storage_por_defecto`: el de mayor espacio libre) y se muestra un aviso no bloqueante: "El perfil pedía
  el almacenamiento «ssd-rapido», que no existe en «pve1». Se usó «local-lvm»."
- CA-P06.3 Dado una pista de bridge que no existe en el nodo, entonces se usa `bridge_por_defecto`
  (`vmbr0` si existe, si no el primero) con el aviso equivalente; sin bridges en el nodo, aplica el error
  V-16 de M1 (CA-17.1).
- CA-P06.4 Dado un perfil sin pistas (de fábrica o con la casilla desmarcada), entonces se usan los
  valores por defecto sin aviso.
- CA-P06.5 Dado un clúster con nodo "Automático", entonces las pistas se resuelven en el nodo efectivo
  del formulario y el motor de lotes de M2 sigue validando la elegibilidad por nodo (RF-L06 de M2): un
  nodo sin la pista no queda elegible por ese motivo.
- CA-P06.6 Dado el inventario aún no cargado (sin conexión), entonces el perfil se puede administrar pero
  no aplicarse (S-M7).
- CA-P06.7 Dado que ninguna regla encuentra storage con `images` ni bridge, entonces el formulario queda
  con los errores V-17/V-16 de M1 y los avisos lo explican; no se aplica un valor inventado.
- CA-P06.8 Un perfil guardado jamás incluye el nodo; un test comprueba la ausencia de `nodo` en toda
  serialización de perfil.

#### RF-P07 Compatibilidad con la versión de Proxmox y con el servidor — Debe — D-07
Al aplicar un perfil se evalúa su compatibilidad y se muestra un panel "Compatibilidad del perfil".
- CA-P07.1 Dado un perfil aplicado, entonces se ejecuta la validación existente (`validar_vm` con el
  `Capacidades` efectivo, real o forzado) y el panel lista cada problema con el campo afectado, sin
  reglas nuevas duplicadas.
- CA-P07.2 Dado un perfil que usa una función cuya versión mínima (tabla de capacidades, `Funcion`) es
  mayor que la detectada, entonces el panel indica "Requiere Proxmox <versión> o superior" y la función se
  omite o el perfil no se aplica según el caso (D-07). En el MVP 3 ningún campo de perfil exige versión
  superior a 8.0; el mecanismo existe y se prueba con una función de prueba inyectada.
- CA-P07.3 Dado `memoria_mib` mayor que la memoria libre del nodo, o `sockets × cores` mayor que sus CPUs,
  entonces aparecen los avisos no bloqueantes de M1 (RF-27) / M2 (V-L12), no errores.
- CA-P07.4 Dado `tipo_cpu` con valor `host`, entonces se muestra el aviso de que impide migrar entre
  nodos con CPUs distintas (D-14). Dado un `tipo_cpu` ausente del catálogo del nodo (si LAB-M3-04 confirma
  el endpoint), entonces aviso no bloqueante; si el endpoint falla o no se puede leer, no se avisa.
- CA-P07.5 Dado un servidor de la versión forzada (avanzado, M1 RF-26), entonces la compatibilidad se
  evalúa con las capacidades forzadas y se etiqueta como M2 CA-L11.6.
- CA-P07.6 El panel no bloquea: los errores de capa 2 se tratan como los de cualquier formulario (el
  botón de resumen se deshabilita hasta corregirlos).

#### RF-P08 Exportar perfiles — Debe — D-12
- CA-P08.1 Dado uno o varios perfiles seleccionados (fábrica o usuario), cuando se elige "Exportar…",
  entonces se escribe un archivo `.json` con la envoltura de RF-X01 (`formato = proxlaunch.perfiles`) en la
  ruta elegida por el usuario; nunca en una ruta fija.
- CA-P08.2 Dado el diálogo de exportación, entonces la casilla "Incluir los nombres de almacenamiento y
  red" está **desmarcada** por defecto (privacidad y portabilidad); marcada, incluye las pistas.
- CA-P08.3 Dado un perfil de fábrica exportado, entonces el archivo lo describe como perfil normal (no lo
  vuelve de fábrica al importarlo, RF-P09).
- CA-P08.4 Dado el archivo exportado, entonces pasa el test de centinela (sin secretos, host, IP ni
  usuario) y contiene solo campos de la lista blanca.
- CA-P08.5 Dado el nombre de archivo sugerido, entonces se sanea a partir del nombre del perfil (sin
  separadores de ruta, sin nombres reservados de Windows como `CON`, máximo 80 caracteres).
- CA-P08.6 Dado un archivo existente en la ruta elegida, entonces el diálogo del sistema pide confirmar la
  sobrescritura y la escritura es atómica (RF-X03).
- CA-P08.7 Dado exportar e importar el mismo archivo, entonces el perfil resultante es equivalente (ida y
  vuelta, salvo `id`).

#### RF-P09 Importar perfiles de terceros — Debe — D-12
- CA-P09.1 Dado un archivo de perfiles, cuando el usuario elige "Importar…", entonces se lee con las reglas
  de RF-X02, se valida cada perfil (capa 1) y se muestra una lista de revisión con nombre, resumen
  ("2 núcleos · 4 GiB · 1 disco de 40 GiB"), estado y casilla por perfil; **no se guarda nada** hasta
  confirmar.
- CA-P09.2 Dado un perfil inválido dentro del archivo, entonces aparece marcado con el motivo
  (V-M, campo) y no se puede seleccionar; los demás sí.
- CA-P09.3 Dado un nombre ya existente, entonces el valor por defecto es **conservar ambos** (el importado
  queda como «<nombre> (2)»); "Reemplazar" solo existe para perfiles del usuario (nunca de fábrica) y exige
  confirmación explícita.
- CA-P09.4 Dado un perfil importado, entonces recibe un `id` **nuevo** generado localmente (nunca el del
  archivo) y su origen es siempre `usuario`, aunque el archivo diga `fabrica`.
- CA-P09.5 Dado que la importación superaría `MAX_PERFILES_USUARIO`, entonces se bloquea con V-M03 y no se
  importa ninguno (todo o nada para el límite).
- CA-P09.6 Dado un archivo con más de `MAX_PERFILES_ARCHIVO` (100) perfiles o de más de `MAX_BYTES_PERFILES`
  (256 KiB), entonces se rechaza antes de interpretar el contenido (E-M01).
- CA-P09.7 Dado un archivo con claves que parecen credenciales (RF-X04), entonces se ignoran, nunca se
  guardan y se avisa.
- CA-P09.8 Dado un perfil importado que trae pistas de storage/bridge, entonces se conservan como pistas y
  se tratan igual que las propias (RF-P06).

#### RF-P10 Persistencia de los perfiles del usuario — Debe — D-06, RNF-15 de M1
- CA-P10.1 Los perfiles del usuario se guardan en `perfiles_maquina.json` dentro de `directorio_config`
  (`Rutas.perfiles_maquina`, mismo patrón que `perfiles.json`), mediante el almacén JSON existente
  (escritura atómica) y sin pasar por el llavero.
- CA-P10.2 Dado el archivo con `version_esquema` igual a la soportada, entonces se lee normalmente; con
  una **anterior**, se migra en memoria y se reescribe en la siguiente escritura (RF-X01); con una
  **posterior**, el almacén queda en modo **solo lectura**: se muestran los perfiles que se entiendan, se
  avisa "Tus perfiles se crearon con una versión más nueva de ProxLaunch" y **no se sobrescribe** el
  archivo (INV-M8).
- CA-P10.3 Dado un `perfiles_maquina.json` corrupto (JSON inválido, UTF-8 inválido, raíz que no es un
  objeto), entonces se aplica la política del almacén propio: se conserva una copia
  `perfiles_maquina.json.danado-<sello>` y se parte de vacío con aviso (RNF-15 de M1). Esta política es
  **solo** para el almacén propio de la aplicación, nunca para archivos abiertos por el usuario (INV-M3).
- CA-P10.4 Dado un perfil individual inválido dentro de un archivo por lo demás válido, entonces se
  descarta ese perfil (no todo el archivo) y se informa cuántos y por qué, sin borrar el archivo.
- CA-P10.5 Dado POSIX, entonces el archivo se crea con permisos `0600` y su carpeta con `0700`
  (`crear_carpeta_privada`); en Windows hereda la ACL de la carpeta de usuario (se documenta, RNF-M01).
- CA-P10.6 Dado un test de ida y vuelta, entonces escribir y releer N perfiles produce los mismos datos
  (orden de creación conservado).

#### RF-P11 Selector de perfil, ayuda y modo básico/avanzado — Debe — D-14, D-04
- CA-P11.1 En modo básico, el formulario muestra primero **Perfil** (selector), luego nombre/prefijo y
  cantidad (D-14); los campos técnicos siguen ocultos pero sus valores vienen del perfil.
- CA-P11.2 Cada opción del selector muestra nombre y, debajo o en la ayuda, un resumen en lenguaje llano
  ("2 núcleos, 4 GiB de memoria, disco de 40 GiB"). La descripción del perfil se muestra al elegirlo.
- CA-P11.3 Dado una lista fija de identificadores de ayuda (perfil, perfil de fábrica, pistas de
  almacenamiento/red, guardar como perfil, exportar/importar, compatibilidad, lote guardado, CSV, plantilla
  CSV, separador, codificación, unidades, vista previa), entonces cada uno tiene un texto no vacío de 1–3
  frases en español llano (test, M1 CA-25.2).
- CA-P11.4 Los textos nuevos usan "perfil de máquina" y nunca "plantilla" para el usuario (en Proxmox
  "template" es otra cosa); la guía de usuario aclara la diferencia con el perfil de conexión (P-M12).
- CA-P11.5 La guía (`docs/guia-usuario.md`) documenta los perfiles, lotes guardados y CSV (tarea del
  `documentador`; fuera de este documento).

#### RF-P12 Perfil predeterminado y compatibilidad hacia atrás — Debe — M1, M2
- CA-P12.1 Dado un usuario que no toca nada del MVP 3, entonces crear una MV o un lote funciona exactamente
  como en el MVP 2: misma petición `POST` por MV para la misma entrada (test de equivalencia sobre el
  conjunto de pruebas del MVP 2).
- CA-P12.2 Dado la aplicación sin perfiles del usuario y sin archivo `perfiles_maquina.json`, entonces
  arranca normalmente (el archivo se crea solo al guardar el primer perfil).
- CA-P12.3 Dado `perfiles_maquina.json` ilegible por permisos, entonces la aplicación arranca, usa solo los
  perfiles de fábrica, avisa y no pierde el archivo (M1 RNF-15).

### B. Archivos: formato, lectura y escritura seguras (perfiles, lotes y CSV)

#### RF-X01 Envoltura, versionado y migración — Debe — D-05
Todo archivo JSON del MVP 3 lleva `formato` (`proxlaunch.perfiles` o `proxlaunch.lote`), `version_formato`
(entero, 1 en el MVP 3) y `app_version` (informativa). Estructuras en la sección 9.
- CA-X01.1 Dado un archivo sin `formato` o con un valor distinto del esperado, entonces E-M02 ("Este archivo
  no es un archivo de ProxLaunch de este tipo") sin intentar interpretarlo. Un lote abierto como perfiles
  (o al revés) también cae aquí.
- CA-X01.2 Dado `version_formato` igual a la actual, entonces se lee tal cual.
- CA-X01.3 Dado `version_formato` menor, entonces una cadena de migraciones puras (v1→v2→…) lo lleva a la
  actual; cada migración tiene un archivo de ejemplo de esa versión en `tests/datos/` y una prueba que lo
  migra y valida. Sin migraciones registradas aún, la prueba comprueba que existe la cadena vacía y que el
  v1 se lee.
- CA-X01.4 Dado `version_formato` **mayor** que la soportada, entonces E-M03 ("Este archivo lo creó una
  versión más nueva de ProxLaunch. Actualiza la aplicación para abrirlo") y **no** se intenta una lectura
  parcial de lotes (podría omitir campos que cambian el significado). Para el almacén propio de perfiles,
  ver CA-P10.2.
- CA-X01.5 Dado `version_formato` ausente, no entero, booleano, negativo o cero, entonces E-M02.
- CA-X01.6 Dado campos desconocidos dentro de una versión conocida, entonces se ignoran, no se guardan al
  reescribir y se cuenta el número en un aviso informativo (no se muestran sus valores).
- CA-X01.7 Dado que se añade un campo nuevo en el futuro, entonces añadirlo no exige subir
  `version_formato` si es opcional con valor por defecto; cambiar el significado de uno existente, sí. La
  regla consta en el código del esquema.
- CA-X01.8 Las claves del JSON son identificadores técnicos en español sin acentos (`tamano_gib`,
  `memoria_mib`), no traducibles (como `ConfiguracionVM.a_dict`).

#### RF-X02 Lectura segura de archivos de terceros — Debe — D-09, RNF-16 de M1
Todo archivo abierto por el usuario (perfiles, lote, CSV) se trata como entrada **no confiable**.
- CA-X02.1 **Tipo de archivo:** dado una ruta que no es un archivo regular (directorio, dispositivo,
  tubería con nombre, `/dev/zero`), entonces E-M01 sin abrirla para lectura bloqueante (se comprueba con
  `fstat` sobre el descriptor abierto sin bloquear, o `stat` previo).
- CA-X02.2 **Tamaño:** dado un archivo mayor que `MAX_BYTES_PERFILES` (256 KiB), `MAX_BYTES_LOTE` (1 MiB)
  o `MAX_BYTES_CSV` (1 MiB), entonces se rechaza con E-M01 **sin leerlo entero**: se leen como máximo
  `límite + 1` bytes. Un test con un archivo de 2 GB simulado (flujo ficticio) comprueba que no se carga en
  memoria.
- CA-X02.3 **Parseo:** el JSON se lee con el módulo estándar, rechazando `NaN`/`Infinity`
  (`parse_constant`), claves repetidas (`object_pairs_hook`), profundidad > `PROFUNDIDAD_JSON_MAX` (8) y
  `RecursionError`; nunca se usan `pickle`, `eval`, `exec`, `yaml.load` ni carga dinámica de código.
- CA-X02.4 **Esquema estricto:** cada campo se valida por tipo **real** (un booleano no es entero; una
  cadena no es número), rango y longitud antes de construir `ConfiguracionVM`; no se usa
  `ConfiguracionVM.desde_dict` sobre datos no confiables (no valida tipos y falla con `KeyError`). Los
  errores se informan con la ruta del campo ("discos[1].tamano_gib") y E-M04.
- CA-X02.5 **Cadenas:** toda cadena se limita a `MAX_LONG_TEXTO` (256), se normaliza a NFC y se rechazan
  caracteres de control (salvo salto de línea en `descripcion`) y los de dirección de texto
  (U+202A–U+202E, U+2066–U+2069) que pueden engañar a quien lee (V-M04). Los valores que van a la API
  siguen las reglas de M1 (V-01, V-16, V-17, V-22, V-24), que impiden `, = : &` y espacios.
- CA-X02.6 **Rutas dentro del archivo:** ningún campo se interpreta como ruta, URL o comando; el programa
  nunca abre ni descarga nada que el archivo indique (con `origen ≠ disco_vacio` se rechaza, CA-P01.2).
- CA-X02.7 **No se modifica el archivo del usuario:** abrir un archivo no lo renombra, mueve, trunca ni
  borra, ni siquiera si está corrupto (INV-M3); en particular **no** se reutiliza
  `AlmacenJson._marcar_danado` para archivos de terceros.
- CA-X02.8 **Lectura en hilo de trabajo:** un archivo de hasta el máximo se lee y valida sin congelar la
  interfaz (RNF-M05); la cancelación del diálogo no deja estado a medias.
- CA-X02.9 **Errores de E/S:** archivo inexistente, sin permiso, bloqueado por otro programa (Excel en
  Windows) o ilegible dan E-M05 con mensaje llano ("El archivo está abierto en otro programa. Ciérralo o
  guarda una copia") y sin trazas.
- CA-X02.10 **Registro:** el log registra el nombre de archivo (no la ruta completa), el tamaño, el número
  de errores y su código; nunca el contenido ni valores de celdas (RNF-M03).
- CA-X02.11 Test de fuzz: 10 000 entradas aleatorias o mutadas de archivos válidos nunca producen una
  excepción no controlada, ni una lectura mayor que el límite, ni una petición de red.

#### RF-X03 Escritura segura — Debe — RNF-15 de M1
- CA-X03.1 Toda escritura (almacén de perfiles, perfiles exportados, lotes, CSV, informes CSV) es
  **atómica**: archivo temporal en la misma carpeta, `fsync` y `os.replace`; si falla, el destino anterior
  queda intacto y el temporal se borra.
- CA-X03.2 En POSIX, los archivos creados por la aplicación nacen con permisos `0600` y las carpetas que
  crea la aplicación con `0700` (`crear_carpeta_privada`). La carpeta que el usuario elige para exportar
  no se modifica. En Windows se heredan los permisos de la carpeta (documentado).
- CA-X03.3 La ruta de destino siempre la elige el usuario con un diálogo del sistema o es la del almacén de
  perfiles; nunca se construye a partir de contenido de un archivo.
- CA-X03.4 Los nombres de archivo sugeridos se sanean (CA-P08.5) y, en Windows, se respetan las rutas con
  espacios, acentos y hasta 260 caracteres (aviso si se excede, E-M08).
- CA-X03.5 La escritura no cambia la fecha ni el contenido de archivos que no son el destino.
- CA-X03.6 Los JSON se escriben en UTF-8 sin BOM, con `ensure_ascii=False`, sangría y claves ordenadas
  (diferencias legibles con control de versiones); los CSV según RF-C10/RF-C11.

#### RF-X04 Sin secretos y lista blanca — Debe — D-09, RNF-06 de M1
- CA-X04.1 Los serializadores escriben **solo** los campos de la lista blanca por construcción (como
  `_a_dict` de los perfiles de conexión); no existe un volcado genérico de objetos.
- CA-X04.2 Dado un perfil, lote o CSV con claves, o encabezados de columna, cuyo nombre normalizado
  contiene `token`, `password`, `contrasena`, `secreto`, `secret`, `ticket`, `csrf`, `apikey`, `api_key` o
  `credencial`, entonces esos datos se **ignoran** (no se leen sus valores ni se guardan ni se registran) y
  se avisa "El archivo traía datos que parecen una credencial. No se usaron. Si eran reales, cámbialas."
- CA-X04.3 Dado un campo de texto libre (`descripcion`, nombre de perfil o de lote) que contiene el patrón
  de un API Token (`usuario@realm!id=secreto`, regex de V-18 de M1) o una cabecera `PVEAPIToken=`, entonces
  V-M05 bloquea guardar o importar ese texto: "Parece un token de acceso. No lo escribas aquí."
- CA-X04.4 Test del centinela: con un secreto único en token, contraseña, ticket y CSRF de una sesión
  simulada, guardar/exportar/cargar perfiles y lotes, importar CSV y exportar CSV no deja el centinela en
  ningún archivo, log, mensaje de interfaz ni portapapeles (extiende M1 CA-RNF-06 y M2 CA-RNF-L06).
- CA-X04.5 Ningún archivo contiene host, IP, puerto, usuario, realm, huella ni el nombre o id del perfil de
  conexión (S-M8, RNF-M03). Un test busca el host y usuario de la sesión simulada en todos los archivos
  escritos.

#### RF-X05 Diálogos y compatibilidad de plataformas — Debe — D-06
- CA-X05.1 Los diálogos de abrir y guardar son los del sistema (Qt), con filtros "Perfiles de ProxLaunch
  (*.json)", "Lotes de ProxLaunch (*.json)", "CSV (*.csv *.txt)"; la extensión sugerida es
  `.proxlaunch-perfiles.json`, `.proxlaunch-lote.json` y `.csv`.
- CA-X05.2 Todas las rutas se manejan con `pathlib` y `platformdirs`; ninguna ruta, separador ni fin de
  línea fijo de un sistema operativo (M1 RNF-04). El CSV se lee con `newline=""`.
- CA-X05.3 La carpeta inicial de los diálogos es la última usada en la sesión o `user_documents_dir`; las
  rutas elegidas no se guardan en `preferencias.json` (privacidad).
- CA-X05.4 Dado Windows con un CSV abierto en Excel, entonces leerlo da E-M05 (bloqueado) y guardar encima
  da E-M08 sin perder datos.

### C. Guardar y cargar lotes

#### RF-G01 Qué es un lote guardado — Debe — D-12, D-20
Un **lote guardado** es la definición reutilizable del lote: `DefinicionLote` (plantilla + cantidad +
patrón + destino + `vmid_inicial` si lo fijó el usuario + `etiquetar`) o, en un lote por filas, la lista de
filas. Es **un archivo JSON** que elige el usuario. Nunca incluye el plan, VMIDs reservados, UPID, el libro
ni el informe (INV-M5), ni el `id_lote` (se genera en cada ejecución).
- CA-G01.1 Dado un lote guardado y cargado, entonces `DefinicionLote` resultante es igual al original
  salvo `plantilla.vmid`, `plantilla.nombre` y `plantilla.nodo` (que M2 ignora) y `politica_thin` (que no
  se guarda y toma el valor de la aplicación, CA-L08.7 de M2). Test de ida y vuelta.
- CA-G01.2 Dado el archivo, entonces no existen las claves `plan`, `elementos`, `libro`, `upid`, `id_lote`
  ni `vmids_saltados` (test sobre la lista blanca).
- CA-G01.3 Dado `vmid_inicial`, entonces se guarda **solo** si el usuario lo fijó a mano (avanzado) y al
  cargarlo se muestra como valor editable con el aviso "Este número inicial se guardó con el lote; se
  comprobará de nuevo contra el servidor"; si era automático (`None`), se guarda `null`.
- CA-G01.4 Dado `etiquetar`, entonces se guarda y se restaura; las etiquetas con el id del lote se
  generan nuevas al planificar (CA-L24.1 de M2).
- CA-G01.5 Dado un lote guardado que se comparte con otro equipo, entonces es **autocontenido** (S-M4): no
  depende de ningún perfil del usuario ni de otro archivo.

#### RF-G02 Guardar un lote — Debe — D-12
Acción "Guardar lote…" en el formulario con bloque de lote (también con cantidad 1).
- CA-G02.1 Dado el formulario con errores de validación (de capa 1 o 2), entonces **se puede guardar**
  igualmente (es un borrador), con el aviso "El lote tiene problemas; se comprobará otra vez al abrirlo".
  Los errores de capa 1 que impiden *serializar* con sentido (por ejemplo, un tamaño de disco no numérico)
  bloquean con el campo indicado.
- CA-G02.2 Dado el diálogo de guardado, entonces pide un **nombre del lote** (1–60 caracteres, V-M01 sin la
  unicidad) con el prefijo de nombres como propuesta, y la ruta mediante el diálogo del sistema; la
  carpeta sugerida es `lotes/` dentro de la carpeta de datos del usuario (`platformdirs.user_data_dir`),
  que se crea con `0700` solo al usarla.
- CA-G02.3 Dado el guardado, entonces el archivo cumple RF-X01 (envoltura), RF-X03 (atómico) y RF-X04
  (lista blanca, sin secretos ni sitio).
- CA-G02.4 Dado un lote en ejecución, entonces "Guardar lote" sigue disponible para el formulario ya
  bloqueado (guarda lo que muestra) y no afecta a la ejecución.
- CA-G02.5 Dado que se guarda un lote por filas (RF-G07), entonces las filas se guardan con la
  configuración efectiva de cada una.
- CA-G02.6 Dado un fallo de escritura, entonces E-M08 y el formulario no cambia.

#### RF-G03 Cargar un lote — Debe — D-12
- CA-G03.1 Dado "Abrir lote…" con sesión conectada (S-M7), cuando el usuario elige un archivo, entonces se
  lee con RF-X02, se valida con capa 1 y se **reemplaza el contenido del formulario** (plantilla y bloque de
  lote) con lo cargado; si el formulario tiene cambios sin guardar, antes se pide confirmación (Cancelar por
  defecto).
- CA-G03.2 Dado que se carga un lote, entonces **no se crea nada ni se envía ninguna petición de
  escritura** (INV-M1) y "Crear" queda deshabilitado hasta generar y confirmar el resumen de M2 (INV-M6).
  Cargar jamás inicia una ejecución.
- CA-G03.3 Dado un archivo con errores de capa 1, entonces no se carga nada y se muestra la lista de errores
  con ruta de campo (E-M04); el formulario queda como estaba.
- CA-G03.4 Dado un archivo válido con avisos (campos desconocidos ignorados, claves de credencial
  ignoradas), entonces se carga y los avisos se muestran en un panel cerrable.
- CA-G03.5 Dado el modo básico y un lote cuyos campos avanzados difieren de los valores por defecto,
  entonces se cargan y el resumen los muestra (M1 CA-24.5); el usuario no pierde datos al cambiar de modo.
- CA-G03.6 Dado un lote cargado y modificado, entonces "Guardar lote" ofrece sobrescribir el mismo archivo
  (con confirmación del sistema) o guardar como nuevo.
- CA-G03.7 Dado el archivo cargado, entonces la aplicación no vuelve a leerlo ni lo vigila: el formulario
  es la fuente hasta el siguiente guardado.

#### RF-G04 Revalidación completa y compatibilidad con el servidor actual — Debe — D-08, M2
- CA-G04.1 Dado un lote cargado con inventario disponible, entonces se ejecuta de inmediato la validación de
  capa 2 de los elementos del formulario (V-04, V-16, V-17, V-22, V-24 de M1; existencia del nodo en
  "Un nodo"/"Nodos elegidos") y los problemas se marcan en los campos (`aplicar_problemas`).
- CA-G04.2 Dado que el usuario pide el resumen, entonces el **planificador de M2 corre completo** con el
  inventario actual: reserva de VMIDs (RF-L03), reparto, espacio (V-L09, V-L10), memoria (V-L12), permisos
  (V-L16). Nada de lo guardado se da por bueno (INV-M6); los VMIDs se reservan en ese instante, no antes.
- CA-G04.3 Dado un storage o bridge del lote que no existe en el servidor actual, entonces el campo queda
  con error y el panel "Este lote no encaja en este servidor" ofrece, por cada problema, "Usar otro…" con los
  valores disponibles (nunca una sustitución silenciosa); mientras no se resuelva, el resumen no se genera.
- CA-G04.4 Dado un destino "Un nodo"/"Nodos elegidos" con un nodo que no existe, o está fuera de línea,
  entonces error V-04 con la opción de pasar a "Automático" (acción explícita del usuario).
- CA-G04.5 Dado que el lote no cabe (V-L09) o `vmid_inicial` guardado está ocupado, entonces se aplica la
  política de M2 (bloquear con "Reducir a N" / saltar VMIDs y avisar); no se modifica el lote cargado.
- CA-G04.6 Dado un lote guardado con una versión de Proxmox mayor que la detectada (`app_version`/dato
  informativo `version_proxmox_al_guardar`), entonces solo se muestra un aviso informativo; la
  compatibilidad real la deciden las capacidades (RF-P07).
- CA-G04.7 Dado el modo "versión forzada" (avanzado), entonces la revalidación usa las capacidades forzadas
  (M2 CA-L11.6/V-L15).
- CA-G04.8 Dado un lote cargado y un cambio de servidor (otro perfil de conexión) antes de generar el
  resumen, entonces la revalidación se hace contra el inventario nuevo y se descarta cualquier resultado
  anterior.

#### RF-G05 Lotes de otro servidor o de otro perfil de conexión — Debe — D-09
- CA-G05.1 Dado un lote guardado con un servidor y cargado con otro perfil de conexión, entonces se carga
  sin restricción por perfil (el archivo no sabe de perfiles de conexión, S-M8) y se aplica RF-G04: los
  desajustes (nodo, storage, bridge) salen como errores o avisos concretos.
- CA-G05.2 Dado el destino "Automático" y storage/bridge presentes en el nuevo servidor, entonces el lote
  se valida sin cambios (portabilidad entre sitios iguales).
- CA-G05.3 Dado el mismo lote cargado en un clúster y en un nodo suelto, entonces "Nodos elegidos" con
  nodos que no existen produce V-04 y no se reinterpreta.
- CA-G05.4 Dado un lote cargado y luego cambiado el servidor conectado, entonces el lote cargado **no
  sobrevive** al cambio sin pasar de nuevo por RF-G04 (M2 CA-L17.4: cambio de perfil cierra el lote en
  curso; aquí además se invalida el resumen).
- CA-G05.5 La aplicación no almacena ni compara identificadores del servidor en el archivo; el aviso "este
  lote parece de otro servidor" **no existe** (se deduce de los errores reales).

#### RF-G06 Archivos corruptos, de versión futura o inesperados — Debe — RNF-15 de M1
- CA-G06.1 Dado un lote con JSON inválido, UTF-8 inválido o truncado, entonces E-M04 ("El archivo está
  dañado o no se puede leer") sin modificarlo (INV-M3) y sin cambiar el formulario.
- CA-G06.2 Dado un lote con `version_formato` posterior, entonces E-M03 (CA-X01.4).
- CA-G06.3 Dado un lote con `version_formato` anterior, entonces se migra (CA-X01.3) y se carga; al
  guardar de nuevo se escribe en la versión actual (con confirmación si sobrescribe el mismo archivo).
- CA-G06.4 Dado un lote con `cantidad` mayor que `MAX_LOTE`, entonces V-L01 (M2) como error del campo, sin
  recortar; con una cantidad no entera o negativa, E-M04 por esquema.
- CA-G06.5 Dado un lote con más de `MAX_LOTE` filas (por filas), entonces E-M06 (límite) sin cargar ninguna.
- CA-G06.6 Dado un archivo de perfiles abierto como lote (o un lote como perfiles), entonces E-M02 con la
  pista "Parece un archivo de perfiles; usa «Importar perfiles»".
- CA-G06.7 Dado un archivo de gran tamaño, entonces CA-X02.2 (rechazo previo).

#### RF-G07 Lote por filas guardado — Debería — D-12, P-M01
Un lote por filas (origen CSV o guardado como tal) se puede guardar y recargar como archivo de tipo
`por_filas` (sección 9).
- CA-G07.1 Dado un lote por filas importado desde CSV, cuando el usuario elige "Guardar lote…", entonces
  se guarda el tipo `por_filas` con la configuración efectiva de cada fila (nombre, VMID/nodo si estaban,
  hardware); no guarda el archivo CSV de origen ni su ruta.
- CA-G07.2 Dado la carga de un lote `por_filas`, entonces entra directamente a la vista previa de filas
  (RF-C06) con la revalidación de RF-G04 por fila.
- CA-G07.3 Dado que no hay edición por fila en la interfaz (CA-L04.5 de M2), entonces para cambiar una fila
  se edita el CSV y se reimporta (o se edita el JSON a mano, sin garantía).
- CA-G07.4 Dado un lote por filas con una fila inválida, entonces se aplica RF-C07.

#### RF-G08 Cambios sin guardar — Debería — D-14
- CA-G08.1 Dado un formulario con un lote cargado o editado sin guardar, al abrir otro lote, importar un
  CSV, cambiar de servidor o cerrar la aplicación, entonces se pregunta "¿Guardar el lote antes de
  continuar?" con "Guardar", "No guardar" y "Cancelar" (foco inicial en "Cancelar").
- CA-G08.2 Dado un formulario que nunca se editó, entonces no se pregunta.
- CA-G08.3 Dado un lote en ejecución, la confirmación de cierre de M2 (RF-L23) prevalece y no se duplican
  diálogos.

### D. Importación desde CSV

#### RF-C01 Caso de uso y flujo — Debe — D-06, D-12
Caso de uso: una persona tiene en Excel o en un CSV una lista de MVs distintas (nombre, núcleos, memoria,
disco, red, nodo…) y quiere crearlas todas sin teclearlas. Flujo: **Importar CSV…** → elegir archivo →
detección de codificación y separador → vista previa con validación por fila → corregir (o reimportar) →
confirmar filas → resumen y confirmación de M2 → ejecución con el motor de M2.
- CA-C01.1 Dado el menú de lotes, entonces existe "Importar desde CSV…" y "Descargar plantilla CSV…" (RF-C10),
  accesibles en modo básico (D-14); las opciones técnicas (codificación, separador manuales, columnas
  avanzadas) solo en modo avanzado.
- CA-C01.2 Dado el flujo, entonces el CSV **solo alimenta** la definición del lote: el motor, la
  confirmación y el rollback son los de M2 (RF-C08, INV-M6); importar jamás crea MVs por sí mismo.
- CA-C01.3 Dado un CSV importado, entonces el formulario del lote pasa a modo "Lote por filas": se ocultan
  cantidad y patrón de nombres (no aplican) y se muestra "N máquinas desde el archivo «x.csv»" (nombre de
  archivo, no la ruta).
- CA-C01.4 Dado el modo básico, entonces el usuario básico puede importar con un perfil base elegido y un
  archivo con solo la columna `nombre`.

#### RF-C02 Lectura: codificación, separador y límites — Debe — D-06
- CA-C02.1 **Codificación:** el programa detecta en este orden: BOM UTF-8; BOM UTF-16 (LE/BE); UTF-8 estricto
  sin BOM; si falla, **Windows-1252**. Dado un archivo de Excel en español en Windows-1252 con «peña» y
  «Ñandú», entonces se leen correctamente y la vista previa indica "Codificación detectada: Windows-1252".
- CA-C02.2 Dado un archivo con bytes no definidos en Windows-1252 (0x81, 0x8D, 0x8F, 0x90, 0x9D), entonces
  E-M07 con la posición aproximada (fila) y la sugerencia de guardarlo como "CSV UTF-8" desde Excel; en
  avanzado se puede elegir la codificación a mano (UTF-8, Windows-1252, UTF-16, ISO-8859-1).
- CA-C02.3 Dado un UTF-8 que contenga caracteres de sustitución (U+FFFD) o nulos (`\x00`), entonces
  E-M07; un byte nulo nunca llega al análisis.
- CA-C02.4 **Separador:** se detecta entre `;`, `,` y tabulador analizando las primeras
  `LINEAS_DETECCION` (20) líneas, fuera de comillas: gana el separador con el mismo número de columnas
  (≥ 2) en más líneas; en empate, `;` si el número decimal con coma aparece, si no `,`. Si la primera línea
  es `sep=;` (convención de Excel), se usa ese y se omite la línea.
- CA-C02.5 Dado un archivo con una sola columna (solo `nombre`) sin separador detectable, entonces se
  acepta (una columna es válida, RF-C03).
- CA-C02.6 Dado un resultado de detección ambiguo (dos separadores igual de probables), entonces en
  modo básico se muestra "No se pudo saber cómo está separado el archivo" con los dos candidatos para
  elegir, y en avanzado el selector está siempre visible.
- CA-C02.7 Dado el CSV, entonces se acepta RFC 4180: comillas dobles, comillas escapadas (`""`), saltos de
  línea dentro de comillas, fin de línea `\r\n`, `\n` o `\r`.
- CA-C02.8 **Límites:** más de `MAX_BYTES_CSV` (1 MiB), `MAX_COLUMNAS_CSV` (40), `MAX_LONG_CELDA` (256) o
  más de `MAX_LOTE` filas de datos → E-M06 con el límite y el valor real; nunca se recorta en silencio.
  Las filas completamente vacías (solo separadores) se ignoran y no cuentan.
- CA-C02.9 Dado un archivo de 0 bytes o solo con encabezado, entonces E-M09 ("El archivo no tiene
  máquinas").
- CA-C02.10 Dado comillas sin cerrar, entonces E-M07 con la fila donde empieza el campo problemático.
- CA-C02.11 El análisis completo de un CSV de 1 MiB / 100 filas tarda ≤ 1 s de CPU y se ejecuta fuera del
  hilo de la interfaz (RNF-M05).
- CA-C02.12 El archivo del usuario se abre solo para lectura y no se modifica (INV-M3).

#### RF-C03 Columnas, encabezados y alias — Debe — D-14
La primera fila es el encabezado. Los nombres de columna no distinguen mayúsculas, acentos ni espacios
(`Memoria`, `MEMORIA`, `núcleos` = `nucleos`; espacio y guion = guion bajo). Cada columna tiene un nombre
canónico y alias (tabla única en el código, preparada para traducir, RNF-M04).

| Columna | Obligatoria | Alias aceptados | Significado | Validación |
|---|---|---|---|---|
| `nombre` | **Sí** | `name`, `hostname` | Nombre de la MV | V-01 |
| `perfil` | No (Debería) | `profile` | Nombre de un perfil de máquina (fábrica o usuario) para esa fila | V-M06 |
| `vmid` | No | `id` | Número de la MV | V-02 |
| `nodo` | No | `node` | Nodo destino | V-04 |
| `cpu` | No | `cores`, `nucleos` | Núcleos por socket | V-05 |
| `sockets` | No (avanzado) | `zocalos` | Sockets | V-05 |
| `memoria` | No | `ram`, `memoria_gib`, `memoria_mib` | Memoria (ver RF-C04) | V-06 |
| `disco` | No | `disco1`, `disco_gib`, `tamano_disco` | Tamaño del disco principal | V-08 |
| `almacenamiento` | No | `storage`, `almacenamiento1` | Storage del disco principal | V-17 |
| `disco2`…`disco8` | No (Podría) | — | Discos adicionales (misma regla) | V-07, V-08 |
| `almacenamiento2`…`almacenamiento8` | No (Podría) | `storage2`… | Storage de cada disco adicional | V-17 |
| `red` | No | `bridge`, `red1` | Bridge de la red principal | V-16 |
| `vlan` | No | `vlan1` | VLAN de la red principal | V-15 |
| `modelo_red` | No (avanzado) | `tarjeta_red` | `virtio` o `e1000` | V-16 |
| `firmware` | No | `bios` | `seabios` o `ovmf` (acepta "UEFI" = `ovmf`, "BIOS" = `seabios`) | enum |
| `tipo_cpu` | No (avanzado) | `cpu_tipo` | Modelo de CPU | V-22 |

- CA-C03.1 Dado un encabezado sin `nombre`, entonces E-M10 ("Falta la columna obligatoria «nombre»") y nada se
  importa; el mensaje lista las columnas que sí se reconocieron.
- CA-C03.2 Dado dos columnas que resuelven a la misma columna canónica (por ejemplo `cpu` y `cores`), entonces
  E-M10 de columna duplicada con las posiciones.
- CA-C03.3 Dado una columna no reconocida, entonces se ignora y se avisa "La columna «xyz» no se usa"
  (una sola vez, no por fila); los valores de esa columna no se leen ni se registran. Si su nombre coincide
  con CA-X04.2 (credenciales), el aviso es el de credenciales.
- CA-C03.4 Dado un encabezado vacío o repetido en celdas de nombre vacío entre columnas con datos, entonces
  E-M10 con la posición de la columna.
- CA-C03.5 Dado el encabezado con BOM o con espacios al inicio, entonces el BOM se descarta y los espacios se
  recortan.
- CA-C03.6 Dado una celda vacía en una columna opcional, entonces se usa el valor del perfil base (o el de
  la fila, si tiene `perfil`); una celda vacía en `nombre` es V-M07 (error de esa fila).
- CA-C03.7 Dado que hay una sola columna `disco` y una sola `almacenamiento`, entonces corresponden al
  primer disco del perfil base; si el perfil no tiene discos, se crea uno con los valores por defecto de
  disco para ese bus.
- CA-C03.8 Dado `disco` con valor `0` o `ninguno`/`sin disco`, entonces la fila se crea sin disco
  (`con_disco = false`); la lista de valores aceptados consta en la ayuda.
- CA-C03.9 La plantilla descargable (RF-C10) y la ayuda del diálogo muestran estas columnas con su
  significado (RNF-M04).

#### RF-C04 Valores numéricos, decimales y unidades — Debe — D-14, CT-6
- CA-C04.1 **Memoria:** un número sin unidad se interpreta en **GiB** (lo que ve el usuario en el
  formulario, P-M06); con unidad, se acepta `MiB`, `GiB`, `TiB`, `M`, `G`, `T`, `MB`, `GB`, `TB`, con o sin
  espacio (`4`, `4 GiB`, `4G`, `4096 MiB`, `1,5 GiB`). `MB`/`GB`/`TB` se tratan como MiB/GiB/TiB (Proxmox
  trabaja en binario, CT-6) y la ayuda lo dice.
- CA-C04.2 Dado una memoria con decimales (`1,5` o `1.5`), entonces el resultado en MiB debe ser **entero**
  (1,5 GiB = 1536 MiB); si no lo es (`0,3` GiB = 307,2 MiB), entonces error de fila y columna con el ejemplo
  de valor válido.
- CA-C04.3 **Disco:** un número sin unidad es **GiB**; se aceptan `GiB`, `G`, `GB`, `TiB`, `T`, `TB`, `MiB`;
  el resultado debe ser un **número entero de GiB** (V-08): `0,5` o `512 MiB` dan error "Los discos se
  miden en GiB enteros (mínimo 1)".
- CA-C04.4 **Decimal:** `,` y `.` se aceptan como marca decimal. Un valor con ambos (`1.024,5`) es ambiguo
  y da error "Escribe el número sin separador de miles". Un valor con el patrón de miles ambiguo (un solo
  punto o coma seguido de exactamente tres dígitos, como `1.000` o `1,000`, en columnas enteras) da error
  "¿Quisiste decir mil o uno? Escribe 1000 o 1" (V-M08); nunca se interpreta en silencio.
- CA-C04.5 Dado texto no numérico (`abc`, `dos`), entonces error con la celda y un ejemplo.
- CA-C04.6 Dado `cpu`, `sockets`, `vmid`, `vlan`: solo enteros (`2`, `2.0` aceptado como entero; `2.5` no).
- CA-C04.7 Dado un valor numérico con espacios, comillas, `+` inicial o notación científica (`1e3`),
  entonces `1e3`, `Infinity`, `NaN` y hexadecimal se rechazan; espacios y comillas se recortan.
- CA-C04.8 Dado un valor fuera de rango (por ejemplo `cpu` = 0 o 500, `memoria` de 4 MiB, `vlan` 5000),
  entonces el error de la regla correspondiente (V-05, V-06, V-15, V-08) en esa fila y columna.
- CA-C04.9 Dado un valor desmesurado pero válido para V-06 (por ejemplo, memoria 4096 sin unidad = 4096 GiB),
  entonces la fila lleva el aviso no bloqueante V-M09 "Pides 4096 GiB de memoria. ¿Querías MiB?" cuando la
  memoria resultante supera `MEMORIA_AVISO_GIB` (1024 GiB) o el mayor nodo conocido, para evitar el error
  típico de confundir MiB con GiB (V-06 no tiene máximo).
- CA-C04.10 **Booleanos y enumeraciones** (`firmware`, `modelo_red`): valores sin distinguir mayúsculas ni
  acentos; lista de valores válidos en el mensaje de error.

#### RF-C05 Validación fila a fila: capas y mensajes — Debe — D-04, D-14
- CA-C05.1 Cada problema se informa con **número de fila** (como lo vería el usuario en Excel: el
  encabezado es la fila 1), **columna** (nombre del encabezado) y el valor corto (recortado a 40
  caracteres, sin caracteres de control): "Fila 7, columna «memoria»: «abc» no es un número. Escribe, por
  ejemplo, 4 o 4 GiB."
- CA-C05.2 La **capa 1** (sin servidor) valida cada fila: V-M07 (nombre no vacío), V-01, V-02, V-05, V-06,
  V-08, V-15, V-07 (máximo de dispositivos), V-22, enums, tipos y unidades. La **capa 2** (con servidor)
  valida V-04, V-16, V-17, V-L06, V-L09..V-L12, VMIDs; se ejecuta al construir el plan (RF-C08).
- CA-C05.3 Dado un nombre duplicado dentro del archivo (sin distinguir mayúsculas), entonces V-M10 marca
  **todas** las filas implicadas ("Filas 3 y 9 tienen el mismo nombre «web-01»"); los nombres de Proxmox
  no necesitan ser únicos (S-L6 de M2), pero dentro del lote se exige para evitar errores del usuario.
- CA-C05.4 Dado un VMID repetido dentro del archivo, entonces V-M10 marca todas las filas implicadas; no se
  corrige solo.
- CA-C05.5 Dado un nombre que coincide con una MV existente del servidor, entonces el aviso V-L06 de M2 por
  fila (no bloqueante).
- CA-C05.6 Los mensajes distinguen **errores** (la fila no se puede crear) de **avisos** (se puede crear:
  decimal con coma, GiB sin unidad asumido, `GB` tratado como GiB, nombre existente, fila de ejemplo).
- CA-C05.7 Dado una fila con varios problemas, entonces se listan todos (hasta `MAX_PROBLEMAS_FILA` = 5 por
  fila; luego "y N más") y se ordenan por columna.
- CA-C05.8 El resultado de la validación es una función pura sobre `(texto del archivo, perfil base,
  perfiles disponibles, inventario o None)`: mismo archivo y entorno, mismos mensajes (RNF-M07).
- CA-C05.9 Todos los mensajes salen de códigos y parámetros traducibles; el núcleo no produce texto de
  interfaz (D-04, RNF-M04).
- CA-C05.10 Dado un CSV de 100 filas con el 100 % de las filas con error, entonces se muestran todos los
  errores sin congelar la interfaz y con "Copiar errores".

#### RF-C06 Vista previa — Debe — D-14, D-12
- CA-C06.1 Dado un CSV leído, entonces el diálogo muestra: nombre de archivo, codificación y separador
  detectados, número de filas, perfil base elegido y una **tabla** (modelo de datos, no un widget por fila)
  con columnas: fila, nombre, perfil, vmid, nodo, núcleos, memoria, disco, almacenamiento, red y estado.
- CA-C06.2 El **estado** de cada fila lleva texto y símbolo ("✔ Correcta", "⚠ Con aviso", "✖ Con error"),
  nunca solo color (RNF-M06); filtro "Mostrar solo problemas".
- CA-C06.3 Dado una fila con error, entonces al seleccionarla se muestra la lista de sus problemas con
  fila/columna (CA-C05.1) y la celda afectada se resalta (con texto, no solo color).
- CA-C06.4 La vista previa muestra los **valores ya interpretados** (memoria como "4 GiB", disco "40 GiB") y
  conserva el texto original en un detalle ("Valor del archivo: «4096»") para que el usuario vea cómo se
  entendió.
- CA-C06.5 Dado un perfil base (selector, por defecto el aplicado en el formulario o el predeterminado),
  cuando se cambia, entonces la vista previa se recalcula.
- CA-C06.6 El diálogo permite **Descargar plantilla**, **Elegir otro archivo**, **Cambiar separador/
  codificación** (avanzado) y **Descargar filas con error** (RF-C12).
- CA-C06.7 Navegación completa con teclado (Tab y flechas), `accessibleName` en tabla y botones, foco
  visible; las 100 filas se desplazan sin lentitud (RNF-M05/M06).
- CA-C06.8 El texto de la vista previa es copiable.
- CA-C06.9 Dado que el usuario no ha confirmado la vista previa, entonces no hay cambios en el formulario ni
  en el servidor (la vista previa es solo lectura).
- CA-C06.10 Dado sesión sin conexión (S-M7), entonces la vista previa muestra solo capa 1 con el aviso "Sin
  conexión: aún no se comprobó contra el servidor"; el botón de continuar exige conexión.

#### RF-C07 Filas con errores: qué se puede importar — Debe — P-M02
- CA-C07.1 Dado un CSV con al menos una fila con error, entonces el botón principal es "Corregir el archivo" y
  la acción secundaria es "Importar solo las N filas correctas" (con las M filas con error nombradas).
- CA-C07.2 Dado "Importar solo las correctas", entonces se pide confirmación explícita con las filas excluidas
  listadas por número y nombre, y el resumen de M2 indica "N de N+M filas del archivo" (nunca silencioso).
- CA-C07.3 Dado un CSV sin errores, entonces se continúa con el resumen.
- CA-C07.4 Dado que el usuario puede además **desmarcar filas** en la vista previa (excluir sin tocar el
  archivo), entonces las excluidas no entran al lote, constan en el resumen y la numeración de nombres no se
  rompe porque los nombres son explícitos (distinto de P-L12 de M2).
- CA-C07.5 Dado que se excluyen todas las filas, entonces no se puede continuar.
- CA-C07.6 Dado un error de capa 2 en una fila (storage inexistente), entonces sigue la misma regla (se
  informa, se puede excluir, no se corrige sola).

#### RF-C08 Relación con el motor del MVP 2: lote por filas — Debe — D-20 (11), P-M01
D-20 (11) fijó el lote **homogéneo**; el CSV exige filas **heterogéneas**. Diseño propuesto (P-M01
recomendación A): el CSV produce un **lote por filas**: la lista de `ElementoPlan` ya contiene su propia
configuración, el motor de M2 no depende de la plantilla única (verificado: `motor.py` no la referencia) y
cada fila es una MV del plan. Cambian la planificación, el reparto, el presupuesto y el informe, que hoy
suponen una plantilla (`reparto.py`, `presupuesto.py`, `planificador.py`, `informe.py`).
- CA-C08.1 Dado un lote por filas de N filas, entonces el plan tiene exactamente N elementos en el orden del
  archivo, cada uno con su propio `ConfiguracionVM` (hardware, nombre y VMID/nodo propios).
- CA-C08.2 Dado el lote por filas, entonces **todas** las garantías del MVP 2 se mantienen sin cambio:
  INV-L1..L5 (un solo POST por VMID, reconsulta antes de cada POST, simulación solo lectura), pausas,
  cancelación, rollback manual con propiedad demostrada, informe saneado, etiquetas `proxlaunch;lote-<id>`,
  concurrencia (1 por nodo, hasta 4 nodos), tope `MAX_LOTE` (100). La suite de INV-L1 se repite para el
  lote por filas (inyección de fallos en cada punto, ≤ 1 POST por VMID).
- CA-C08.3 **VMIDs:** filas con `vmid` explícito conservan ese VMID (si está libre; si está ocupado, error
  de esa fila: nunca se reasigna sola una decisión explícita); filas sin `vmid` reciben el siguiente libre
  desde `vmid_inicial` (o `nextid`), **saltando** los ocupados en el servidor y los VMIDs explícitos del
  archivo, con aviso como CA-L03.2 de M2.
- CA-C08.4 **Reparto:** filas con `nodo` explícito van a ese nodo (si no es elegible para esa fila, error de
  esa fila); las demás se reparten con el algoritmo elegido (Equilibrado por defecto) **descontando** lo ya
  asignado a nodos explícitos (memoria y espacio). Elegibilidad (RF-L06) se evalúa **por fila** con su propio
  storage/bridge.
- CA-C08.5 **Espacio:** el presupuesto por clave `(nodo, storage)` / compartido suma los discos de **cada
  fila** (heterogéneos); V-L09/V-L10 y el tope thin se aplican igual (3 × libre).
- CA-C08.6 **Reducir a N** no aplica al lote por filas; en su lugar, si no cabe, el resumen indica qué
  filas excederían y ofrece desmarcarlas (RF-C07 CA-C07.4); no se reorganiza el lote solo.
- CA-C08.7 **Resumen:** la tabla del resumen (CA-L10.1) muestra una fila por MV con su nombre, VMID, nodo,
  almacenamiento, tamaño de discos, **núcleos y memoria** de esa fila; los totales suman las filas.
- CA-C08.8 **Informe:** muestra la configuración por MV (núcleos, memoria, discos) en lugar de la plantilla
  única; el resto igual (CA-L19.1 de M2). Sin host, IP ni usuario.
- CA-C08.9 **Simulación (RF-L11):** funciona igual: mismo planificador, peticiones exactas por fila, solo
  lecturas (INV-L5).
- CA-C08.10 **Reintentar pendientes (RF-L21):** reconstruye un lote por filas con las filas no creadas, con
  sus configuraciones propias.
- CA-C08.11 Dado un lote por filas con una sola fila, entonces el `POST` es idéntico al de una MV de M1 con
  esa configuración (más etiquetas si aplican), como CA-L04.1 de M2.
- CA-C08.12 Dado un lote **homogéneo** (sin CSV), entonces nada cambia respecto de M2 (test de equivalencia
  sobre las pruebas de M2).
- CA-C08.13 La política de VMIDs ocupados (P-L06 de M2: saltar y avisar) y la de carrera (fallar esa MV y
  ofrecer reintentar) no cambian.

#### RF-C09 Nodo y VMID por fila — Debe — D-08
- CA-C09.1 Dado un servidor individual (un nodo), entonces la columna `nodo` es opcional: vacía = el único
  nodo; con el nombre correcto = ok; con otro = V-04 en esa fila.
- CA-C09.2 Dado un clúster y `nodo` vacío, entonces la fila entra en el reparto automático; con un nodo en
  línea = fijo; con un nodo sin conexión = V-04 con "Sin conexión".
- CA-C09.3 Dado `vmid` con un valor ya ocupado en el servidor (consulta `nextid?vmid=`), entonces error de
  esa fila "El número 105 ya lo usa otra máquina" y se ofrece (acción explícita) "Asignar automáticamente".
- CA-C09.4 Dado `vmid` fuera de 100–999999999, entonces V-02.
- CA-C09.5 Dado que el usuario con permiso solo sobre un rango de VMIDs (ACL) usa VMIDs fuera de él,
  entonces llega como 403 por MV (E-L16 de M2); la aplicación no lo anticipa (igual que M2).
- CA-C09.6 Dado el modo básico, entonces las columnas `vmid` y `nodo` se aceptan igual si existen en el
  archivo (el modo solo afecta a lo que se *muestra* en la interfaz, no a lo que se importa).

#### RF-C10 Plantilla CSV descargable — Debe — D-14
- CA-C10.1 Dado "Descargar plantilla CSV…", entonces se escribe un archivo con el encabezado de las columnas
  principales (`nombre`, `perfil`, `cpu`, `memoria`, `disco`, `almacenamiento`, `red`, `vlan`, `nodo`, `vmid`)
  y **dos filas de ejemplo** (`ejemplo-01`, `ejemplo-02`) con valores válidos que no empiezan por
  `= + - @`.
- CA-C10.2 Dado el diálogo de guardado de la plantilla, entonces se ofrece elegir el separador: "`;` (Excel en
  español)" por defecto y "`,` (Excel en inglés)"; la codificación es UTF-8 con BOM (se abre bien en Excel)
  y los saltos de línea `\r\n`.
- CA-C10.3 Dado una fila cuyo nombre empieza por `ejemplo-`, entonces la vista previa añade el aviso V-M11
  "Parece una fila de ejemplo de la plantilla" (no bloquea).
- CA-C10.4 Dado la plantilla importada sin cambios, entonces se lee sin errores (test: la plantilla pasa su
  propia validación de capa 1 con un perfil base de fábrica).
- CA-C10.5 La plantilla pasa por RF-C11 (escritura saneada) y RF-X03 (atómica).
- CA-C10.6 Los encabezados de la plantilla son los canónicos (RF-C03) y estables entre idiomas
  (RNF-M04).

#### RF-C11 Exportación segura de CSV (inyección de fórmulas) — Debe — D-09
Se exporta CSV en: plantilla (RF-C10), filas con error (RF-C12), informe CSV (RF-C14) y, si se implementa,
"Exportar lote como CSV" (Podría). Todo CSV escrito pasa por **un único escritor** que sanea las celdas.
- CA-C11.1 Dado una celda de **texto** cuyo primer carácter es `=`, `+`, `-`, `@`, tabulador o retorno de
  carro (`\t`, `\r`, `\n`), entonces el escritor antepone `'` a la celda (la apóstrofe hace que Excel/
  LibreOffice la traten como texto). Un test parametrizado cubre los seis disparadores y valores como
  `=HYPERLINK(...)`, `@SUM(1)`, `-2+3`, `+cmd|' /C calc'!A0` y `\t=1`.
- CA-C11.2 Dado una celda cuyo primer carácter es un espacio o comilla seguido de un disparador
  (`" =1+1"`), entonces también se antepone `'` (el saneo mira el primer carácter significativo tras
  espacios y comillas).
- CA-C11.3 Dado un valor **numérico** generado por la aplicación (enteros no negativos), entonces se escribe
  sin comilla; el escritor distingue tipos (no sanea números reales, sí cualquier cadena).
- CA-C11.4 Dado texto de origen no confiable (valores del CSV importado, nombres de perfil, mensajes con
  valores), entonces siempre se sanea al exportar, también cuando provenga de un archivo del propio usuario.
- CA-C11.5 Dado el CSV importado cuya celda empieza con `'` seguido de un disparador (de una exportación
  anterior), entonces se quita **una** apóstrofe inicial solo en ese caso (ida y vuelta); en cualquier otro
  caso el texto se deja tal cual (y suele fallar V-01 con un mensaje claro).
- CA-C11.6 Dado un valor con el separador, comillas o saltos de línea, entonces se entrecomilla según RFC 4180
  (`QUOTE_MINIMAL` con escapado correcto); un test de ida y vuelta con el módulo `csv` lo verifica.
- CA-C11.7 Dado un valor con caracteres de control o de dirección de texto, entonces se eliminan antes de
  escribir.
- CA-C11.8 Ningún CSV exportado contiene secretos, host, IP ni usuario (INV-M2, centinela).
- CA-C11.9 Dado un test de seguridad que abre el CSV exportado con `csv.reader` y comprueba que **ninguna
  celda de texto** empieza por un disparador sin la apóstrofe, sobre un conjunto generado de 10 000 valores
  aleatorios con disparadores.
- CA-C11.10 La importación **nunca evalúa** fórmulas ni abre enlaces; las celdas se tratan solo como texto
  (INV-M4).

#### RF-C12 CSV de filas con error — Debería — D-14
- CA-C12.1 Dado un CSV con errores, entonces "Descargar filas con error" escribe un CSV con las columnas
  originales de esas filas más `fila_original`, `columna` y `problema` (texto traducido), para corregir en
  Excel y reimportar.
- CA-C12.2 Dado el CSV de errores, entonces cumple RF-C11 (los valores originales y los mensajes se sanean) y
  RF-X03.
- CA-C12.3 Dado el CSV de errores reimportado, entonces `fila_original`, `columna` y `problema` se ignoran
  como columnas desconocidas (CA-C03.3), de modo que el ciclo corregir-y-reimportar funciona.

#### RF-C13 Perfil por fila y perfil base — Debería — D-14, P-M11
- CA-C13.1 Dado el diálogo de importación, entonces el **perfil base** (selector; por defecto el aplicado en
  el formulario o "Servidor pequeño") aporta todo lo que el CSV no diga.
- CA-C13.2 Dado la columna `perfil` con el nombre de un perfil (sin distinguir mayúsculas ni acentos), entonces
  esa fila usa ese perfil como base en lugar del perfil base del diálogo; las demás columnas de la fila
  sobrescriben.
- CA-C13.3 Dado un nombre de perfil que no existe, entonces V-M06 en esa fila con los nombres disponibles
  (hasta 5) y no se usa otro por su cuenta.
- CA-C13.4 Dado un nombre de perfil ambiguo (usuario y fábrica con el mismo nombre, imposible por V-M01; o
  duplicado tras un cambio de nombre importado), entonces V-M06 pide el nombre exacto.
- CA-C13.5 Orden de precedencia, de menor a mayor: valores por defecto de M1 → perfil base/perfil de la fila →
  columnas del CSV. Un test de propiedad comprueba que una columna presente siempre gana al perfil.
- CA-C13.6 Las pistas de storage/bridge del perfil se resuelven como en RF-P06 y, si no hay una columna
  `almacenamiento`/`red`, el aviso aparece una sola vez por fila.

#### RF-C14 Informe del lote en CSV — Podría — P-L11, P-M09
- CA-C14.1 Dado el informe de un lote terminado (real o simulación), entonces "Guardar informe como CSV…"
  escribe una fila por MV (nombre, VMID, nodo, desenlace, código de error, duración) con RF-C11.
- CA-C14.2 El CSV no incluye UPID completo ni texto original de Proxmox si estos pudieran contener datos
  sensibles; usa el mismo saneo que el informe de texto de M2 (CA-L19.3).
- CA-C14.3 El contenido es idéntico al informe de texto en datos (una sola función de generación).

#### RF-C15 Límite de filas y lotes grandes — Debe — D-20 (7)
- CA-C15.1 Dado un CSV con 100 filas de datos, entonces se acepta; con 101 o más, E-M06 "El archivo tiene 130
  filas; el máximo por lote es 100. Divide el archivo en partes." sin cargar nada (no se recorta).
- CA-C15.2 `MAX_LOTE` es la misma constante que M2 (CA-L01.4): cambiar su valor cambia el límite del CSV, del
  lote guardado y de la interfaz (test).
- CA-C15.3 Las filas vacías y el encabezado no cuentan para el límite.

---

## 4. Requisitos no funcionales

Siguen vigentes los RNF de M1 (RNF-01..16) y de M2 (RNF-L01..L11), en particular RNF-06 (secretos), RNF-08
(sin pruebas destructivas en reales) y RNF-16 (codificación de entradas).

| ID | Requisito | Prioridad | Criterio de aceptación (verificable) |
|---|---|---|---|
| RNF-M01 | Seguridad de archivos de terceros y escritura | Debe | CA-RNF-M01: RF-X02 y RF-X03 completos; fuzz de 10 000 entradas sin excepciones no controladas ni lecturas por encima de los límites (CA-X02.11); archivos que crea la aplicación en POSIX `0600` y carpetas propias `0700` (prueba con `stat`); en Windows se documenta la herencia de ACL y se verifica manualmente en la matriz de plataformas; ningún archivo del usuario se modifica al abrirlo (INV-M3, prueba de hash antes/después). |
| RNF-M02 | Límites de tamaño y recursos | Debe | CA-RNF-M02: constantes únicas (`MAX_BYTES_*`, `MAX_LOTE`, `MAX_PERFILES_USUARIO`, `PROFUNDIDAD_JSON_MAX`, `MAX_LONG_TEXTO`, `MAX_COLUMNAS_CSV`); un archivo de 2 GB simulado se rechaza sin leerlo entero; memoria máxima del análisis ≤ 5 × tamaño del archivo (prueba con `tracemalloc` sobre el máximo). |
| RNF-M03 | Privacidad y secretos | Debe | CA-RNF-M03: prueba del centinela (M1 CA-RNF-06) extendida a guardar/cargar perfiles y lotes, importar/exportar CSV, perfiles exportados, errores y logs; ningún archivo contiene host, IP, usuario, perfil de conexión, huella ni rutas absolutas de usuario; el log registra nombre de archivo, tamaño y códigos, nunca contenido (CA-X02.10). |
| RNF-M04 | Textos traducibles | Debe | CA-RNF-M04: análisis de literales y extracción (M1 CA-23.1/23.2) cubren los textos nuevos; plurales con formas de Qt ("1 fila", "12 filas"); nombres y descripciones de perfiles de fábrica y encabezados de plantilla vienen del catálogo (identificadores estables, textos traducibles); el catálogo de prueba "[T]" muestra todos los textos del MVP 3 marcados. Las claves JSON y los encabezados canónicos del CSV son identificadores, no se traducen; el parser acepta además los encabezados del idioma activo. |
| RNF-M05 | Rendimiento y no congelar la interfaz | Debe | CA-RNF-M05: lectura, análisis y validación de un CSV de 1 MiB / 100 filas ≤ 1 s de CPU; abrir/guardar un lote de 100 filas ≤ 500 ms; aplicar un perfil ≤ 100 ms; el retraso del bucle de eventos medido con un temporizador de 50 ms es < 200 ms con un mock lento (M2 CA-RNF-L01); lectura y análisis fuera del hilo de la interfaz. |
| RNF-M06 | Accesibilidad | Debe | CA-RNF-M06: contraste ≥ 4,5:1 en ambos temas para las tablas y diálogos nuevos (M1 CA-22.5); estados con texto + símbolo; navegación por Tab y flechas; foco visible; `accessibleName` en tablas, selector de perfil, botones y paneles de avisos; diálogos destructivos (eliminar perfil, reemplazar) con "Cancelar" como foco inicial; la vista previa se lee con lector de pantalla fila a fila. |
| RNF-M07 | Determinismo y funciones puras | Debería | CA-RNF-M07: lectura de CSV, validación de capa 1, conversión de unidades, migraciones y serialización son funciones puras (sin reloj ni E/S dentro); mismo archivo y entorno, mismo resultado y mismos mensajes; el reloj se inyecta (marcas de tiempo de copias `.danado`). |
| RNF-M08 | Núcleo sin Qt | Debe | CA-RNF-M08: en un entorno sin PySide6 se importan y prueban núcleo de perfiles, formato de archivos, lector/escritor CSV y lote por filas (M1 RNF-02, M2 RNF-L02). |
| RNF-M09 | Plataformas Ubuntu 22.04/24.04 y Windows 10/11 | Debe | CA-RNF-M09: matriz manual por entrega: abrir CSV de Excel en español (`;`, Windows-1252) en Windows y en Ubuntu, guardar con rutas con espacios y acentos, archivo bloqueado por Excel (E-M05), CRLF/LF, escalado 150 % y 200 % sin textos cortados en la vista previa (M1 RNF-11). `pathlib`/`platformdirs`; nada fijo de un SO. |
| RNF-M10 | Compatibilidad de versiones de Proxmox | Debe | CA-RNF-M10: la suite de perfiles, lotes guardados y CSV pasa contra respuestas de 8.0, 8.x y 9.x (M1 RNF-05); las funciones dependientes de la versión pasan solo por la tabla de capacidades. |
| RNF-M11 | Robustez ante errores | Debería | CA-RNF-M11: una excepción en la importación o carga nunca deja la interfaz "ocupada" ni el formulario a medias (carga atómica: o se aplica todo o nada); un archivo de perfiles dañado no impide arrancar (RNF-15 de M1). |
| RNF-M12 | Sin pruebas destructivas en producción | Debe | CA-RNF-M12: la suite normal no abre sockets; los LAB-M3 solo contra el laboratorio con la variable de entorno explícita y limpian lo que crean (M1 RNF-08, D-15). |

---

## 5. Reglas de validación

Se implementan en el núcleo (sin Qt) con test unitario por fila. Las V-01..V-24 de M1 y V-L01..V-L17 de M2
siguen vigentes y se **reutilizan** (no se duplican) para perfiles, lotes y filas.

| ID | Campo | Regla | Severidad | Mensaje (al usuario) |
|---|---|---|---|---|
| V-M01 | Nombre de perfil o de lote | Recortado, 1–60 caracteres, NFC, sin caracteres de control ni de dirección de texto; único sin distinguir mayúsculas entre fábrica y usuario (solo perfiles) | Error | "Escribe un nombre de 1 a 60 caracteres." / "Ya existe un perfil con ese nombre." |
| V-M02 | Identificador de perfil | No empieza por `fabrica.`; único; solo `[a-z0-9-]` (uuid) | Error (interno) | — |
| V-M03 | Número de perfiles del usuario | ≤ `MAX_PERFILES_USUARIO` (100) | Error | "Llegaste al máximo de 100 perfiles." |
| V-M04 | Cadenas de archivos | ≤ 256 caracteres; sin control ni dirección de texto; NFC | Error | "El texto de «campo» no es válido." |
| V-M05 | Texto libre con token | `descripcion`, nombres: no contienen el patrón de token ni `PVEAPIToken=` | Error | "Parece un token de acceso. No lo escribas aquí." |
| V-M06 | `perfil` de una fila | Existe un perfil con ese nombre (fábrica o usuario) | Error | "No existe el perfil «x». Perfiles disponibles: …" |
| V-M07 | `nombre` de una fila | No vacío (después V-01) | Error | "Falta el nombre." |
| V-M08 | Número con miles ambiguo | `1.000`, `1,000` en columna entera; o ambos separadores | Error | "¿Quisiste decir mil o uno? Escribe 1000 o 1." |
| V-M09 | Memoria desmesurada | Memoria > `MEMORIA_AVISO_GIB` (1024 GiB) | Aviso | "Pides …" — "Pides N GiB de memoria. ¿Querías MiB?" |
| V-M10 | Duplicados en el archivo | Nombres (sin distinguir mayúsculas) o VMIDs repetidos entre filas | Error (todas las filas) | "Las filas 3 y 9 tienen el mismo nombre «web-01»." |
| V-M11 | Fila de ejemplo | Nombre que empieza por `ejemplo-` | Aviso | "Parece una fila de ejemplo de la plantilla." |
| V-M12 | Límite de filas/tamaño | Filas de datos ≤ `MAX_LOTE`; bytes ≤ límite | Error | "El archivo tiene N filas; el máximo por lote es 100." |
| V-M13 | Tipo de archivo | Archivo regular, legible, de tamaño ≤ límite | Error | Ver E-M01 |
| V-M14 | Formato y versión | `formato` esperado; `version_formato` entero ≥ 1 y ≤ la soportada | Error | Ver E-M02, E-M03 |
| V-M15 | Esquema | Tipos reales, rangos y campos obligatorios de cada estructura | Error | Ver E-M04 |

---

## 6. Constantes y valores por defecto

Propuestos salvo indicación; únicos y nombrados (como `nucleo/lote/constantes.py`).

| Constante | Valor |
|---|---|
| `VERSION_FORMATO` | 1 |
| `LONG_NOMBRE_PERFIL` | 60 |
| `LONG_DESCRIPCION` | 200 |
| `MAX_LONG_TEXTO` / `MAX_LONG_CELDA` | 256 |
| `MAX_PERFILES_USUARIO` / `MAX_PERFILES_ARCHIVO` | 100 / 100 |
| `MAX_BYTES_PERFILES` | 256 KiB |
| `MAX_BYTES_LOTE` / `MAX_BYTES_CSV` | 1 MiB / 1 MiB |
| `MAX_LOTE` (la de M2) | 100 |
| `MAX_COLUMNAS_CSV` | 40 |
| `PROFUNDIDAD_JSON_MAX` | 8 |
| `LINEAS_DETECCION` | 20 |
| `MAX_PROBLEMAS_FILA` | 5 |
| `MEMORIA_AVISO_GIB` | 1024 |
| Unidad por defecto en CSV (memoria y disco) | GiB (P-M06) |
| Separador por defecto de la plantilla | `;` |
| Codificación de salida de CSV | UTF-8 con BOM |
| Codificación de entrada, orden | BOM UTF-8 → BOM UTF-16 → UTF-8 → Windows-1252 |
| Perfil predeterminado | `fabrica.servidor-pequeno` |
| Pistas de storage/bridge al guardar perfil propio | marcadas |
| Pistas al exportar | desmarcadas |
| Carpeta sugerida de lotes | `user_data_dir/lotes/` |
| Archivo de perfiles del usuario | `perfiles_maquina.json` en `directorio_config` |
| Conflicto de nombre al importar perfil | conservar ambos |

---

## 7. Errores y su traducción

Los códigos se añaden a `CodigoError` (el núcleo no tiene textos; la interfaz traduce, RNF-M04). Cada fila
es un test parametrizado.

| ID | Código propuesto | Disparador | Mensaje en lenguaje llano | Params |
|---|---|---|---|---|
| E-M01 | `archivo_no_permitido` | No es archivo regular, supera el límite de tamaño o tiene demasiadas entradas | "No se puede abrir este archivo: {motivo} (límite {limite})." | motivo, limite, tamano |
| E-M02 | `archivo_formato_ajeno` | Falta o no coincide `formato`; `version_formato` inválido | "Este archivo no es un archivo de ProxLaunch del tipo que buscas." | esperado |
| E-M03 | `archivo_version_futura` | `version_formato` mayor que la soportada | "Este archivo lo creó una versión más nueva de ProxLaunch. Actualiza la aplicación para abrirlo." | version_archivo, version_soportada |
| E-M04 | `archivo_dañado` | JSON/UTF-8 inválido o esquema incorrecto | "El archivo está dañado o tiene datos no válidos: {campo}." | campo, detalle |
| E-M05 | `archivo_no_accesible` | Inexistente, sin permiso, bloqueado | "No se pudo leer el archivo. Si está abierto en otro programa (como Excel), ciérralo o guarda una copia." | archivo |
| E-M06 | `archivo_demasiadas_filas` | Más de `MAX_LOTE` filas o de columnas | "El archivo tiene {filas} filas; el máximo por lote es {max}. Divide el archivo en partes." | filas, max |
| E-M07 | `csv_codificacion` | Codificación indecifrable, nulos, comillas sin cerrar | "No pude leer el archivo CSV (fila {fila}). Guárdalo como «CSV UTF-8» desde Excel." | fila, motivo |
| E-M08 | `archivo_no_guardable` | Fallo al escribir (disco lleno, sin permiso, ruta larga, bloqueado) | "No se pudo guardar el archivo: {motivo}. No se cambió nada." | motivo |
| E-M09 | `csv_vacio` | Sin filas de datos | "El archivo no tiene máquinas." | — |
| E-M10 | `csv_columnas` | Falta `nombre`, columnas duplicadas o encabezado vacío | "Falta la columna «nombre» / La columna «{col}» aparece dos veces." | columna, reconocidas |
| E-M11 | `csv_valor_invalido` | Error de fila y columna (capa 1 o 2) | "Fila {fila}, columna «{columna}»: {detalle}" | fila, columna, valor, ejemplo |
| E-M12 | `perfil_inexistente` | `perfil` de una fila o perfil aplicado inexistente | "No existe el perfil «{nombre}»." | nombre, disponibles |
| E-M13 | `perfil_no_modificable` | Intento de editar/borrar un perfil de fábrica | "Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión." | — |
| E-M14 | `perfiles_solo_lectura` | Almacén propio de versión futura | "Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden modificar." | — |
| E-M15 | `lote_no_encaja` | Lote cargado con storage/bridge/nodo inexistentes en el servidor | "Este lote no encaja en este servidor: {detalle}." | campo, valor, disponibles |
| E-M16 | `credencial_ignorada` | Claves o columnas con aspecto de credencial | "El archivo traía datos que parecen una credencial. No se usaron. Si eran reales, cámbialas." | n |

---

## 8. Perfiles de fábrica propuestos (P-M05)

Solo hardware, con disco vacío (D-13); sin TPM ni `ostype`. Valores dentro de los límites de M1; `tipo_cpu`
`x86-64-v2-AES` salvo indicación (D-14). Los nombres y descripciones son textos traducibles. Se confirman
con el usuario (P-M05).

| Id | Nombre | Para qué | sockets × cores | Memoria | Disco | Firmware | Bus / red |
|---|---|---|---|---|---|---|---|
| `fabrica.servidor-pequeno` (predeterminado) | Servidor pequeño | Pruebas, servicios ligeros | 1 × 2 | 2 GiB | 32 GiB | SeaBIOS | scsi / virtio |
| `fabrica.servidor-mediano` | Servidor mediano | Aplicaciones web | 1 × 4 | 4 GiB | 64 GiB | SeaBIOS | scsi / virtio |
| `fabrica.base-de-datos` | Base de datos | Bases de datos | 1 × 4 | 8 GiB | 100 GiB (discard, ssd) | SeaBIOS | scsi / virtio |
| `fabrica.servidor-grande` | Servidor grande | Cargas pesadas | 1 × 8 | 16 GiB | 128 GiB | SeaBIOS | scsi / virtio |
| `fabrica.escritorio-compatible` | Escritorio (hardware compatible) | Sistemas que aún no traen controladores virtio | 1 × 4 | 4 GiB | 80 GiB (sin iothread) | UEFI (OVMF) con `q35`: **pendiente de LAB-M3-01** | sata / e1000 |
| `fabrica.minimo` | Mínimo | Disco y red básicos de prueba | 1 × 1 | 512 MiB | 8 GiB | SeaBIOS | scsi / virtio |

Notas: (a) "Windows 11" **no** se ofrece: exige TPM (CT-7, M1 P-04), que queda para el MVP 4; (b) el perfil
"Escritorio (hardware compatible)" solo describe bus/red; instalar el SO es del MVP 4; (c) LAB-M3-01 confirma
que cada perfil se crea en 9.2.

---

## 9. Formatos de archivo

### 9.1 Perfiles (`formato = proxlaunch.perfiles`)
```json
{
  "formato": "proxlaunch.perfiles",
  "version_formato": 1,
  "app_version": "0.3.0",
  "perfiles": [
    {
      "nombre": "Servidor mediano",
      "descripcion": "Para aplicaciones web. Sin sistema operativo.",
      "config": {
        "firmware": "seabios",
        "sockets": 1,
        "cores": 4,
        "tipo_cpu": "x86-64-v2-AES",
        "memoria_mib": 4096,
        "ballooning": null,
        "con_disco": true,
        "discos": [
          {"tamano_gib": 64, "bus": "scsi", "formato": "auto",
           "discard": true, "ssd": true, "iothread": true,
           "storage_preferido": "local-lvm"}
        ],
        "storage_efi_preferido": null,
        "controlador_scsi": "virtio-scsi-single",
        "redes": [{"modelo": "virtio", "vlan": null, "bridge_preferido": "vmbr0"}],
        "origen": "disco_vacio"
      }
    }
  ]
}
```
Sin `vmid`, `nombre` de MV, `nodo`, `etiquetas` ni `id` (el `id` es local; en el almacén propio cada perfil
lleva su `id` uuid; al exportar no se incluye y al importar se genera de nuevo, CA-P09.4). Las pistas
(`*_preferido`) son opcionales.

### 9.2 Lote guardado (`formato = proxlaunch.lote`)
```json
{
  "formato": "proxlaunch.lote",
  "version_formato": 1,
  "app_version": "0.3.0",
  "nombre": "Aula 3",
  "tipo": "homogeneo",
  "homogeneo": {
    "config": { "...": "como en el perfil, con storage y bridge reales (campo `storage`, `bridge`)" },
    "cantidad": 20,
    "patron": {"prefijo": "aula3-pc", "separador": "-", "inicio": 1, "relleno": 2},
    "destino": {"modo": "automatico", "nodos": [], "algoritmo": "equilibrado"},
    "vmid_inicial": null,
    "etiquetar": true
  }
}
```
Para `tipo = por_filas`: la clave `por_filas` lleva `filas` (lista de `{nombre, vmid|null, nodo|null,
config}`), `destino.algoritmo`, `vmid_inicial` y `etiquetar`. **Nunca**: plan, VMIDs reservados, libro,
UPID, `id_lote`, política thin, perfil de conexión, host, usuario ni secretos.

### 9.3 CSV de importación (ejemplo)
```
nombre;perfil;cpu;memoria;disco;almacenamiento;red;vlan;nodo;vmid
ejemplo-01;Servidor mediano;;8;100;local-lvm;vmbr0;;;
ejemplo-02;;2;4 GiB;40;;vmbr1;20;pve2;250
```

---

## 10. Matriz de trazabilidad con el alcance

| Elemento del alcance (D-12 / pedido) | Requisitos |
|---|---|
| Perfiles de fábrica y del usuario | RF-P01..P04, RF-P10, RF-P12, V-M01..M03 |
| Aplicar al formulario | RF-P05, RF-P11, RF-P12 |
| Nodo/storage/bridge, compatibilidad con versión e inventario | RF-P06, RF-P07, RF-G04, RF-G05 |
| Importar/exportar perfiles | RF-P08, RF-P09, RF-X01..X05 |
| Formato, ubicación, versionado y migración | RF-X01, RF-P10, RF-G06, sección 9 |
| Guardar y cargar lotes | RF-G01..G08 |
| Revalidación y otro servidor | RF-G04, RF-G05, INV-M6 |
| Archivos corruptos, futuros y de terceros | RF-X02, RF-G06, INV-M3, E-M01..M05 |
| Importación CSV: lectura, columnas, unidades | RF-C02, RF-C03, RF-C04 |
| Validación fila a fila y vista previa | RF-C05, RF-C06, RF-C07, V-M06..M12 |
| Motor del MVP 2 y lote heterogéneo | RF-C08, RF-C09, RF-G07 (D-20 (11)) |
| Plantilla CSV y exportación segura | RF-C10, RF-C11, RF-C12, RF-C14 |
| Máximo de filas | RF-C15, RF-C02 |
| Sin secretos | RF-X04, INV-M2, RNF-M03 |
| Seguridad, rendimiento, traducción, accesibilidad, plataformas | RNF-M01..M12 |

### 10.1 RF → criterios → tipo de prueba

| RF | Criterios | Mock/unit | Prop./fuzz | UI | LAB |
|---|---|---|---|---|---|
| RF-P01 | CA-P01.1..6 | x | x (P01.1) | | |
| RF-P02 | CA-P02.1..7 | x | | x | LAB-M3-01 |
| RF-P03 | CA-P03.1..7 | x | | x | |
| RF-P04 | CA-P04.1..8 | x | | x | |
| RF-P05 | CA-P05.1..8 | x | | x | LAB-M3-01 |
| RF-P06 | CA-P06.1..8 | x (2 nodos) | | x | |
| RF-P07 | CA-P07.1..6 | x | | x | LAB-M3-04 |
| RF-P08 | CA-P08.1..7 | x | x (ida y vuelta) | x | |
| RF-P09 | CA-P09.1..8 | x | x | x | |
| RF-P10 | CA-P10.1..6 | x | | | |
| RF-P11 | CA-P11.1..5 | | | x | |
| RF-P12 | CA-P12.1..3 | x (equivalencia M2) | | | LAB-M3-01 |
| RF-X01 | CA-X01.1..8 | x | x | | |
| RF-X02 | CA-X02.1..11 | x | x (fuzz) | x | |
| RF-X03 | CA-X03.1..6 | x | | | |
| RF-X04 | CA-X04.1..5 | x | x (centinela) | | |
| RF-X05 | CA-X05.1..4 | | | x (matriz manual) | |
| RF-G01..G03 | CA-G01..G03 | x | x (ida y vuelta) | x | LAB-M3-02 |
| RF-G04, G05 | CA-G04, CA-G05 | x (3 nodos) | | x | LAB-M3-02 |
| RF-G06..G08 | CA-G06..G08 | x | x | x | |
| RF-C01 | CA-C01.1..4 | | | x | |
| RF-C02 | CA-C02.1..12 | x | x (fuzz) | | |
| RF-C03, C04 | CA-C03, CA-C04 | x | x (unidades) | | |
| RF-C05..C07 | CA-C05..C07 | x | x | x | |
| RF-C08 | CA-C08.1..13 | x | x (INV-L1) | x | LAB-M3-03 |
| RF-C09 | CA-C09.1..6 | x | | | LAB-M3-03 |
| RF-C10..C12 | CA-C10..C12 | x | x (10 000 valores) | x | |
| RF-C13 | CA-C13.1..6 | x | x (precedencia) | | |
| RF-C14, C15 | CA-C14, CA-C15 | x | | x | |
| RNF-M01..M12 | CA-RNF-M01..M12 | x | x | x | LAB-M3-01..03 |

---

## 11. Invariantes

- **INV-M1:** abrir, cargar, aplicar o importar un archivo no envía ninguna petición de escritura a Proxmox
  (solo lecturas de inventario, ya existentes). Prueba con transporte que falla ante cualquier método
  distinto de GET/HEAD.
- **INV-M2:** ningún archivo del MVP 3 (perfiles, lotes, CSV, informes CSV), log ni mensaje contiene secretos,
  host, IP, usuario ni perfil de conexión (centinela).
- **INV-M3:** un archivo abierto por el usuario nunca se modifica, renombra ni borra por la aplicación, ni aun
  estando dañado.
- **INV-M4:** ningún contenido de archivo se ejecuta ni evalúa (sin `pickle`, `eval`, `exec`; celdas solo como
  texto).
- **INV-M5:** el plan, los VMIDs reservados, el libro, los UPID y el `id_lote` nunca se serializan.
- **INV-M6:** nada cargado o importado llega a Proxmox sin pasar por validación completa, resumen y
  confirmación de M2; "Crear" nunca queda habilitado directamente tras cargar o importar.
- **INV-M7:** los perfiles de fábrica son inmutables (no se editan, renombran, eliminan ni sobrescriben desde
  importación).
- **INV-M8:** las escrituras son atómicas y un almacén propio de una versión de formato posterior no se
  sobrescribe.

---

## 12. Pruebas de laboratorio necesarias [LAB]

Laboratorio: PVE 9.2 de un nodo (D-15). Se ejecutan solo con la variable de entorno explícita (M1 RNF-08) y
limpian lo que crean; todo lo multinodo y 8.x es con mocks. Se aprovecha el almacenamiento LVM-thin del
laboratorio (la sobreasignación permite crear discos grandes) y se borra con el rollback de M2.

| ID | Verificar | Cierra |
|---|---|---|
| LAB-M3-01 | Cada **perfil de fábrica** aplicado a través del formulario y el motor crea una MV real en 9.2 (una a la vez) y su `config` coincide con el perfil (núcleos, memoria, discos, bus, `scsihw`, red, firmware; efidisk y `q35` si aplica al perfil de escritorio); la simulación previa solo emite GET; el perfil predeterminado produce el mismo `POST` que M2. Se borran después | CA-P02.3, CA-P05.7, CA-P12.1, RF-P02, sección 8 |
| LAB-M3-02 | **Lote guardado**: guardar un lote de 3 MVs, cargarlo, generar el resumen y crearlo: mismo plan que el lote directo. Cargar el mismo archivo con un storage inexistente da E-M15/V-17 y **cero POST** (contador de métodos). Se borran las MVs | CA-G01.1, CA-G03.2, CA-G04.1..3, INV-M1, INV-M6 |
| LAB-M3-03 | **CSV heterogéneo**: 4 filas con núcleos, memoria, disco y red distintos; una con `vmid` explícito libre, otra con `vmid` ocupado (MV de apoyo creada y borrada en el laboratorio) y una con `nodo` explícito: se creó lo válido, `config` coincide **por fila**, la fila con VMID ocupado no genera POST y las etiquetas son las del lote; rollback completo. Parte con Windows-1252 y `;` | RF-C08, RF-C09, CA-C08.1..5, CA-C09.3, INV-L1 sobre lote por filas |
| LAB-M3-04 | Catálogo de modelos de CPU `GET /nodes/{n}/capabilities/qemu/cpu` con el rol mínimo (formato, privilegio, si lista `x86-64-v2-AES` y `v3`) y creación con cada `tipo_cpu` de los perfiles de fábrica | S-M9, CA-P07.4 |

Mocks a preparar (sintéticos desde respuestas reales): inventario de 3 nodos con distintos storages y bridges
para RF-P06 y RF-G04; archivos de ejemplo de cada `version_formato`; CSV de Excel en Windows-1252/`;`, UTF-8
con BOM/`,`, UTF-16, con celdas con disparadores de fórmula; archivos corruptos y gigantes simulados.

---

## 13. Casos límite específicos (para el probador)

1. Perfil con 0 discos, 1 disco, 31 discos SCSI (límite V-07), 32 redes (V-23).
2. Perfil con nombre de 60 y 61 caracteres, con acentos, con NFD en lugar de NFC, con U+202E, con el mismo
   nombre en mayúsculas/minúsculas.
3. `perfiles_maquina.json` vacío, con `[]`, con la raíz `{}` sin `perfiles`, con un perfil bueno y uno malo,
   de versión futura, sin permiso de lectura.
4. Importar perfiles con `id = fabrica.servidor-pequeno`, con `origen = fabrica`, con 101 perfiles, de 300 KiB,
   con claves `token` y `password`.
5. Exportar un perfil con nombre `CON`, `a/b`, `..` y con 200 caracteres.
6. Aplicar perfil con pista de storage inexistente en un nodo y existente en otro (clúster, Automático).
7. Lote con `cantidad` 0, -1, 1.5, "10", `true`, 101; `vmid_inicial` 99, 1000000000; `nodos` con 0 nodos y modo
   `nodos_elegidos`.
8. Lote guardado en clúster de 3 nodos y cargado en nodo suelto; con `etiquetar = false`; con storage
   compartido.
9. JSON con `NaN`, claves repetidas, 500 niveles de anidamiento, cadena de 10 MB, `\u0000`, BOM al inicio.
10. CSV: UTF-8 con BOM, `;` con Windows-1252, `,` con decimales entre comillas (`"1,5"`), UTF-16 LE, `sep=;`
    en la primera línea, líneas en blanco intermedias y finales, `\r` solitario, comillas sin cerrar, saltos de
    línea dentro de comillas, 100 y 101 filas, solo encabezado, solo `nombre`, una columna con espacios en el
    nombre.
11. Valores: memoria `4`, `4 GiB`, `4G`, `4096 MiB`, `1,5`, `0,3`, `1.000`, `1.024,5`, `abc`, `-1`, `1e3`, `4096`
    (aviso MiB/GiB); disco `0,5`, `512 MiB`, `0`, `ninguno`; cpu `2.0`, `2.5`, `0`, `129`; vlan `0`, `4095`.
12. Nombres duplicados con distinta capitalización; VMID repetido; VMID de 3 dígitos; fila de ejemplo.
13. Celdas `=HYPERLINK("http://x","y")`, `@SUM(1)`, `+1`, `-1`, `\t=1`, `" =1"` en nombre, perfil y columna
    desconocida; exportar plantilla, errores e informe y reabrir con `csv.reader`.
14. Cargar lote con VMIDs fijos ocupados, con un nodo fuera de línea, con memoria que supera la del nodo, que no
    cabe en el storage (con y sin thin).
15. Cambiar de servidor entre cargar y resumir; cerrar con cambios sin guardar; doble clic en "Guardar".
16. Ruta de guardado con espacios, acentos, 261 caracteres (Windows), carpeta de solo lectura, disco lleno,
    CSV abierto en Excel, enlace simbólico, tubería con nombre.
17. Dos instancias guardando perfiles a la vez.
18. Catálogo de traducción "[T]" cargado con la vista previa abierta.

---

## 14. Enmiendas a M1 y M2

| Elemento | Enmienda en el MVP 3 |
|---|---|
| D-20 (11) y P-L12 de M2: lote homogéneo | Se mantiene para el formulario; se **amplía** con el lote por filas del CSV (RF-C08), sujeto a P-M01. Requiere actualizar `docs/decisiones.md` con una decisión nueva (D-22) tras aprobar P-M01. |
| CA-L04.2 y CA-L04.5 de M2 | Siguen vigentes para el lote homogéneo; en el lote por filas cada elemento tiene su propia configuración y no hay edición por fila en la interfaz. |
| CA-L07.7 ("Reducir a N") | No aplica al lote por filas (CA-C08.6). |
| CA-L10.1 (tabla del resumen) | Añade núcleos y memoria por fila en el lote por filas (CA-C08.7). |
| CA-L19.1 (informe) | La "plantilla" se sustituye por la configuración por MV en el lote por filas (CA-C08.8). |
| RF-L21 (reintentar pendientes) | Reconstruye un lote por filas (CA-C08.10). |
| P-L11 de M2 (informe) | El informe CSV se evalúa aquí como Podría (RF-C14, P-M09). |
| P-L10 de M2 (simulación sin conexión) | Sigue diferida (P-M08). |
| M1 RF-24 y D-14 | El modo básico muestra el selector de perfil, nombre y cantidad (RF-P11). |
| `AlmacenJson` | Su política de renombrar archivos dañados queda **solo** para el almacén propio (CA-P10.3, CA-X02.7). Hay que añadir un lector de solo lectura para archivos de terceros. |
| `RepositorioPerfiles` (conexión) | Hoy sobrescribe sin mirar `version_esquema`; el almacén de perfiles de MV sí aplica INV-M8. Se recomienda aplicar lo mismo al de conexión (mejora aparte). |
| M1 §7 (errores) | Se amplía con E-M01..E-M16. |

---

## 15. Riesgos y notas para la arquitectura

1. **Mayor riesgo técnico:** el lote por filas toca la planificación, el reparto, el presupuesto de espacio
   y el informe del MVP 2 (hoy parten de una plantilla única); el motor no (consume `ElementoPlan`).
   Conviene definir un tipo `DefinicionLote` alternativo o una fuente de elementos heterogéneos y repetir
   la suite de INV-L1.
2. `ConfiguracionVM.desde_dict` no valida tipos ni tolera claves ausentes (`KeyError`): no sirve para
   archivos de terceros; hace falta un lector estricto aparte (CA-X02.4).
3. `AlmacenJson.leer` renombra el archivo si está corrupto y `json.loads` acepta `NaN`: correcto para el
   almacén propio, inaceptable para archivos abiertos por el usuario (INV-M3).
4. V-06 no tiene máximo de memoria: la confusión MiB/GiB del CSV produce peticiones absurdas; se mitiga con
   V-M09 (y P-M06).
5. Los archivos no están firmados ni cifrados: un archivo malicioso puede pedir hardware excesivo, pero
   siempre pasa por validación, resumen y confirmación (INV-M6); el resumen debe mostrar totales para que lo
   note el usuario.
6. Dos instancias y almacenes en carpetas sincronizadas (OneDrive) pueden producir conflictos: se documenta,
   no se resuelve.
7. Texto libre `descripcion` podría usarse para esconder texto engañoso (RTL): se filtra (V-M04).
8. El selector "Perfil de máquina" y el "Perfil de conexión" son homónimos: riesgo de confusión de usuarios
   sin experiencia (P-M12).

---

## 16. Preguntas abiertas

Ordenadas por impacto. Cada una con opciones y recomendación.

**P-M01 — Cómo encaja el CSV heterogéneo con el motor del MVP 2 (enmienda a D-20 (11) / P-L12).**
- A) **Lote por filas**: un solo lote con N elementos, cada uno con su configuración; reusa el motor, la
  confirmación, el rollback y el informe; cambia planificación, reparto, presupuesto e informe.
- B) Agrupar filas idénticas y lanzar varios lotes homogéneos en cadena (menos cambios en el motor, pero
  varias confirmaciones, varios informes y orden de ejecución poco claro).
- C) El CSV solo rellena prefijo y cantidad (sigue homogéneo): no cubre el caso de uso.
- **Recomendación: A.** Es la única que cumple D-12 ("importación desde CSV") para listas heterogéneas con una
  sola confirmación y un solo informe. Afecta: RF-C08, RF-G07, sección 14. Requiere decisión nueva D-22.

**P-M02 — Filas inválidas en el CSV.**
- A) Todo o nada: ninguna fila se importa si hay algún error.
- B) Se puede importar solo lo correcto, con confirmación explícita y las filas excluidas visibles.
- C) Importar lo correcto automáticamente.
- **Recomendación: B** (el botón principal sigue siendo "Corregir el archivo"). Evita rehacer un archivo de
  100 filas por un error y no omite nada en silencio. Afecta: RF-C07.

**P-M03 — Lote guardado: copia o referencia al perfil.**
- A) Autocontenido (copia de la configuración).
- B) Referencia al perfil por id o nombre.
- **Recomendación: A.** Se puede compartir entre equipos y no se rompe al borrar o cambiar un perfil. Costo: no
  se actualiza solo si se cambia el perfil. Afecta: RF-G01, S-M4.

**P-M04 — Almacenamiento y bridge en los perfiles (nodo nunca).**
- A) Pistas opcionales: se usan si existen y, si no, se cambian por los valores por defecto con aviso;
  exportar sin pistas por defecto.
- B) Nunca guardarlos (siempre valores por defecto).
- C) Guardarlos y fallar si faltan.
- **Recomendación: A.** Funciona bien en el sitio propio y se adapta a otros sitios sin errores confusos.
  Afecta: RF-P06, RF-P08, CA-P03.3.

**P-M05 — Lista de perfiles de fábrica.**
- A) Los seis de la sección 8.
- B) Solo tres (pequeño, mediano, grande).
- C) Otra lista (indicar casos reales de uso; confirmar si hace falta un perfil de escritorio sin TPM).
- **Recomendación: A**, con LAB-M3-01 para verificar el perfil de escritorio; sin "Windows 11" (TPM, MVP 4).
  Afecta: sección 8, RF-P02.

**P-M06 — Unidad por defecto de memoria y disco en el CSV.**
- A) GiB sin unidad (como ve el usuario el formulario), con unidades opcionales y aviso si la memoria pasa de
  1024 GiB.
- B) MiB para memoria (como Proxmox) y GiB para disco.
- C) Unidad obligatoria en cada celda.
- **Recomendación: A.** Coherente con el formulario y con D-14; V-M09 atrapa el error típico. Afecta: RF-C04.

**P-M07 — Dónde viven los lotes guardados.**
- A) Archivos que elige el usuario (carpeta sugerida `lotes/`), sin biblioteca interna.
- B) Biblioteca interna con lista de lotes dentro de la aplicación.
- **Recomendación: A.** Más simple, se comparten por correo o carpeta y se versionan; una biblioteca interna
  puede ir después. Afecta: RF-G02, RF-G03.

**P-M08 — Preparar lotes sin conexión.**
- A) Cargar/aplicar requiere conexión; sin conexión solo se administran perfiles y se revisa un CSV (capa 1).
- B) Preparar todo sin conexión con un inventario guardado o ficticio (D-07 y P-L10 de M2).
- **Recomendación: A en el MVP 3**; B es un trabajo mayor (inventario ficticio) y se decide después. Afecta:
  S-M7, CA-C06.10.

**P-M09 — Informe del lote en CSV (P-L11 C de M2).**
- A) Sí, como Podría (RF-C14), con el escritor saneado.
- B) No por ahora.
- **Recomendación: A** porque reutiliza el escritor de RF-C11 sin coste añadido; si el tiempo aprieta, se
  difiere. Afecta: RF-C14.

**P-M10 — CSV de más de 100 filas.**
- A) Rechazar con mensaje claro (el usuario divide el archivo).
- B) Ofrecer dividir automáticamente en lotes de 100 que se ejecutan uno tras otro.
- **Recomendación: A** (D-20 (7): tope de 100). B añade confirmaciones múltiples y es candidato a un MVP
  posterior. Afecta: RF-C15.

**P-M11 — Columna `perfil` por fila en el CSV.**
- A) Incluirla (Debería): `nombre,perfil` basta para listas con varios tipos de máquina.
- B) Solo un perfil base para todo el archivo.
- **Recomendación: A**: une perfiles y CSV, el valor principal del MVP 3. Afecta: RF-C13.

**P-M12 — Nombre en la interfaz para "perfil de MV".**
- A) «Perfil de máquina» (perfil de conexión sigue siendo «Conexión guardada» en textos nuevos).
- B) «Plantilla» (choca con "template" de Proxmox).
- C) «Modelo».
- **Recomendación: A.** Aclara la diferencia con el perfil de conexión (D-09) y evita "plantilla". Si se
  aprueba, el texto actual «Perfiles» de la conexión se revisa. Afecta: RF-P11, términos.

---

## 17. Pendientes de verificación (resumen)

1. Perfil de fábrica "escritorio compatible" con OVMF/`q35` en 9.2 (LAB-M3-01).
2. Catálogo de modelos de CPU y privilegio (LAB-M3-04).
3. Heterogeneidad del plan: verificar con `revisor-qa` que reparto/presupuesto/informe pueden aceptar
   elementos distintos sin romper INV-L1 (antes de implementar RF-C08).
4. Todas las constantes de la sección 6 se confirman con las decisiones P-M04, P-M06, P-M10.
5. Comportamiento de Excel con CSV UTF-8 con BOM y `;` en Windows y Ubuntu (LibreOffice) (matriz manual,
   RNF-M09).
