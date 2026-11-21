# Requisitos del MVP 2 — ProxLaunch (creación de MVs por lotes)

Versión del documento: 1.0 (2026-11-13) · Estado: borrador para revisión del orquestador

Fuentes, en orden de autoridad: `docs/decisiones.md` (D-01 a D-19 y "Correcciones
técnicas", abreviadas **CT-n**), `docs/requisitos/mvp1.md` (abreviado **M1**, sigue vigente
salvo las enmiendas de la sección 12), `docs/investigacion/f1-api-proxmox.md` (**F1**),
`docs/bitacora.md` (entradas 10 a 13, "lecciones") y `prompt.md` (retirado del repositorio el 2026-11-21; queda en el historial, commit `ab133c0`) (**P§n**). Si se
contradicen, manda `decisiones.md`. El comportamiento de la API que no consta en F1 ni en
las respuestas reales de `tests/datos/respuestas/9.2-lab/` se marca **[LAB]** (hipótesis a
verificar en el laboratorio, sección 10) y no puede darse por cierto.

Convenciones (las de M1, con prefijo propio para no chocar):
- **Prioridad:** Debe / Debería / Podría (igual que M1).
- **IDs:** RF-Lnn (funcional), RNF-Lnn (no funcional), CA-Lnn.y (criterio y del requisito
  nn), V-Lnn (regla de validación), E-Lnn (error), INV-Ln (invariante de seguridad),
  LAB-Lnn (prueba de laboratorio), P-Lnn (pregunta abierta).
- Los criterios usan "Dado / Cuando / Entonces". "Mock" = respuesta simulada de la API
  basada en respuestas reales (D-15). "Laboratorio" = Proxmox VE 9.2 anidado, **un solo
  nodo** (D-15): todo lo multinodo se verifica solo con mocks.
- Términos: **lote** = conjunto de N MVs que salen de una misma plantilla; **plan** = la
  lista concreta (nombre, VMID, nodo) que resulta de planificar el lote; **libro del lote**
  = registro en memoria de lo que el lote envió y de su desenlace (ver RF-L12).
- Unidades: igual que M1 (discos en GiB, RAM en MiB, CT-6).

---

## 1. Alcance

### 1.1 Dentro del MVP 2 (D-12)
1. Definir un lote: cantidad, patrón de nombres, VMID inicial.
2. Reserva de VMIDs a nivel de clúster (CT-8, D-08).
3. Reparto del lote entre nodos (D-08 "Repartir el lote"): un nodo, automático o nodos
   elegidos.
4. Validación previa de todo el lote: espacio acumulado por storage y por nodo, nombres y
   VMIDs, recursos del nodo, política de sobreasignación thin (CT-5).
5. Pantalla de resumen previa y confirmación.
6. Modo simulación (solo lecturas contra el servidor real).
7. Ejecución con seguimiento por MV y global; los errores de una MV no detienen al resto
   (P§6); cancelación; envío incierto; pérdida de conexión.
8. Rollback (limpieza) de lo que creó el lote.
9. Informe final y registro sin secretos.

### 1.2 Fuera del MVP 2
- Perfiles predefinidos, guardar y cargar lotes, importar CSV (MVP 3). **Un lote es
  homogéneo**: todas sus MVs comparten la plantilla; solo difieren nombre, VMID y nodo.
- Origen del SO distinto de "disco vacío" (MVP 4). El campo `origen` sigue siendo
  `disco_vacio`.
- Instaladores y CI (MVP 5).
- LXC, editar o borrar MVs que **no** creó el lote, iniciar las MVs, HA, monitoreo.
- Persistir el libro del lote en disco para retomarlo tras cerrar la aplicación (ver
  P-L04 y 1.4).
- Simulación sin conexión con inventario ficticio (ver P-L10).

### 1.3 Supuestos
- S-L1: la plantilla es la misma configuración de MV de M1 (`ConfiguracionVM`); el formulario
  de M1 se convierte en el editor de la plantilla y se le añade el bloque "Lote" (RF-L04).
- S-L2: las MVs se crean **detenidas** y no se inician (M1 S-1, P-15).
- S-L3: el núcleo del lote (planificación, reparto, validación, motor, rollback, informe) no
  depende de Qt (D-05) y se prueba con reloj simulado y mocks (RNF-L02).
- S-L4: el rol mínimo de M1 (10 privilegios, F1 §5, verificado en F6) cubre **crear** lotes
  sin ampliarse. Para **borrar** (rollback) se espera el mismo privilegio `VM.Allocate` en
  `/vms/{vmid}`, pero **no consta en F1**: [LAB] LAB-L05. Si el laboratorio exige otro
  privilegio, ver P-L03.
- S-L5: un ID de VM ocupado o libre solo es fiable en el instante de la consulta: Proxmox no
  ofrece reserva de VMID (CT-8). El motor reconsulta justo antes de cada POST (INV-L2).
- S-L6: el nombre de una MV no tiene que ser único en Proxmox (el VMID sí). **[LAB]** LAB-L07.

### 1.4 Casos límite generales
- Lote de 1 MV: debe comportarse como M1 (RF-L04).
- Lote donde todas las MVs fallan por la misma causa (permiso, sesión, huella, nodo caído).
- Lote que cruza un ticket por expirar (RF-03 de M1) o una pérdida de red de más de 60 s.
- Cierre inesperado de la aplicación (apagón, `kill`) con tareas ya enviadas: las MVs
  quedan en Proxmox sin libro. Mitigación: etiqueta (RF-L24) y el aviso del cierre normal
  (RF-L23). Lo no mitigable se documenta en la guía de usuario.
- Usuario con permiso solo sobre un rango de VMIDs (ACL por `/vms/{vmid}`): el plan puede
  caer fuera del rango permitido; llega como 403 por MV (E-L16).
- Dos usuarios (o dos ProxLaunch) planifican lotes con el mismo rango a la vez: el segundo
  POST recibe `VMID_OCUPADO` (RF-L03).
- Nodo que cae a mitad del lote; storage que se llena durante el lote por otros usuarios.
- Pantalla de alta resolución y lotes de 100 filas (RNF-L05, RNF-L07).

---

## 2. Requisitos funcionales

### A. Definición del lote

#### RF-L01 Cantidad y límites — Debe — D-12, P§5
El bloque "Lote" pide la cantidad de MVs a crear. Por defecto 1.
- CA-L01.1 Dado el formulario recién abierto, entonces cantidad = 1 y el flujo equivale al
  de M1 (RF-L04).
- CA-L01.2 Dado cantidad 0, -1, 1.5, "abc" o vacío, entonces V-L01 bloquea con mensaje junto
  al campo y el botón de resumen queda deshabilitado.
- CA-L01.3 Dado cantidad mayor que `MAX_LOTE` (100, propuesto, P-L07), entonces V-L01 bloquea
  con "El máximo por lote es 100 máquinas. Divide el trabajo en varios lotes." Nunca se
  recorta en silencio.
- CA-L01.4 Dado `MAX_LOTE` como constante nombrada única, entonces un test unitario comprueba
  que cambiar su valor cambia el límite en núcleo e interfaz.
- CA-L01.5 Dado cantidad N, el texto del resumen usa la forma plural correcta ("1 máquina",
  "12 máquinas") mediante el sistema de traducción (RNF-L03).

#### RF-L02 Patrón de nombres — Debe — D-12, D-14
Nombre = `prefijo` + `separador` + `número con relleno`. Campos: prefijo (obligatorio),
separador (`-` o vacío; avanzado), número inicial (por defecto 1; avanzado) y relleno (dígitos
mínimos; por defecto 2; avanzado). Sin sufijo (Podría futuro).
- CA-L02.1 Dado prefijo `web`, separador `-`, inicio 1, relleno 2, cantidad 3, entonces los
  nombres son `web-01`, `web-02`, `web-03`.
- CA-L02.2 Dado cantidad 120 y relleno 2, entonces el relleno efectivo es 3 para **todos** los
  nombres (`web-001` … `web-120`): `relleno_efectivo = max(relleno, dígitos del mayor
  número)`; los nombres tienen siempre la misma longitud.
- CA-L02.3 Dado inicio 10, cantidad 3, relleno 0, separador vacío, entonces `web10`, `web11`,
  `web12`.
- CA-L02.4 Dado un prefijo con espacio, guion bajo, acento o `/`, o un resultado que incumple
  V-01 (por ejemplo prefijo de 62 letras que supera 63 caracteres con el número), entonces
  V-L04 bloquea e indica el primer nombre inválido y la causa ("`web_01` tiene un guion
  bajo").
- CA-L02.5 Dado cualquier patrón válido, todos los nombres del plan son distintos entre sí
  (V-L05; test de propiedad sobre muchos patrones).
- CA-L02.6 Dado el patrón, la interfaz muestra en vivo una vista previa de los **tres
  primeros y el último** nombre ("web-01, web-02, web-03 … web-120").
- CA-L02.7 Dado un nombre del plan igual al de una MV existente en el servidor, entonces V-L06
  muestra un aviso **no bloqueante** ("Ya existe una máquina llamada «web-01» (VMID 105)") y
  el resumen lo repite. **[LAB]** LAB-L07 y LAB-L11 deciden si Proxmox lo permite y si la lista
  de MVs visibles para el rol mínimo es completa; mientras no se verifique, el aviso se
  califica "puede haber otras que no puedes ver".
- CA-L02.8 Dado inicio 999999 y cantidad 5, entonces se rechaza por V-L04 si el número sale
  del rango 0–999999 o el nombre supera V-01.

#### RF-L03 Reserva de VMIDs — Debe — D-08, CT-8, P§4
El plan asigna a cada MV un VMID, en orden, desde el VMID inicial (por defecto el de
`/cluster/nextid`; editable en avanzado), **saltando los ocupados** (política por defecto
sujeta a P-L06). "Ocupado" se decide en todo el clúster, incluidas MVs y contenedores que el
usuario no ve.
- CA-L03.1 Dado inicio 100, cantidad 3 y todos libres (mock), entonces el plan usa 100, 101, 102.
- CA-L03.2 Dado el mock donde 101 está ocupado (`GET /cluster/nextid?vmid=101` responde 400
  `errors.vmid = "VM 101 already exists"`, F1 §5), entonces el plan usa 100, 102, 103 y el
  resumen indica "Se saltó el número 101 (ya lo usa otra máquina)".
- CA-L03.3 Cada VMID del plan se confirma con `GET /cluster/nextid?vmid=<n>` (no con
  `/cluster/resources`, que solo lista lo que el usuario puede ver, **[LAB]** LAB-L11). Un
  fallo de red durante la consulta aborta la planificación con error de red (E-L08); **nunca**
  se da un VMID por libre sin confirmarlo.
- CA-L03.4 Dado el servicio de planificación llamado dos veces seguidas sin crear nada,
  entonces ambas producen el mismo plan (determinista); no se usa `nextid` sin parámetro para
  más de un VMID (CT-8).
- CA-L03.5 Dado un inicio manual (avanzado) fuera de 100–999999999, entonces V-L07 bloquea;
  dado que el último VMID del plan supera 999999999, entonces bloquea.
- CA-L03.6 Dado que no se encuentran N VMIDs libres en una ventana de `MAX_SALTO_VMID` (1000,
  propuesto) a partir del inicio, entonces falla con E-L02 (nunca bucle sin fin).
- CA-L03.7 Dado un mock con 100 VMIDs en la ventana, la reserva realiza como máximo
  `cantidad + saltos` consultas, con un máximo de `MAX_CONSULTAS_SIMULTANEAS` (8) a la vez, y
  termina en ≤ 3 s con latencia simulada de 100 ms (RNF-L05).
- CA-L03.8 Dado que un VMID del plan queda ocupado entre el resumen y su envío (carrera, otro
  usuario), entonces la reconsulta previa al POST (INV-L2) o el error `VMID_OCUPADO` del POST
  marcan **esa** MV con E-L03 y el lote continúa con las demás. Qué pasa después depende de
  P-L06 (por defecto: no se reasigna solo; se ofrece reintentar, RF-L21).
- CA-L03.9 El plan muestra los VMIDs agrupados en rangos ("100–104, 106–110").

#### RF-L04 Plantilla común y compatibilidad con M1 — Debe — D-14, M1 RF-13..RF-19
El formulario de M1 define la plantilla. Los campos nombre, VMID y nodo de M1 pasan a derivarse
del bloque "Lote" y del reparto.
- CA-L04.1 Dado cantidad 1, entonces la petición enviada es idéntica a la de M1 para la misma
  entrada (mismos parámetros y codificación, CT-9), salvo el parámetro `tags` si P-L04 se
  aprueba (RF-L24).
- CA-L04.2 Dado un lote de N, entonces todas las peticiones comparten los parámetros de la
  plantilla (firmware, cómputo, discos, red) y difieren solo en `vmid`, `name` y nodo de
  destino (y `tags`, que es común al lote).
- CA-L04.3 Dado que se edita la plantilla después de ver el resumen, entonces el resumen se
  invalida y hay que volver a generarlo (nunca se crea un plan viejo).
- CA-L04.4 La plantilla se valida con las mismas reglas V-01..V-23 de M1 en el nodo destino
  de **cada** MV (RF-L06).
- CA-L04.5 No existe edición por MV individual (fuera de alcance, P-L12): para cambiar una MV
  se edita el lote y se regenera.

### B. Reparto entre nodos

#### RF-L05 Destino y algoritmos de reparto — Debe — D-08
Destino (solo clúster; en servidor individual no hay selector, M1 CA-13.6):
**Automático** (predeterminado), **Un nodo** y **Nodos elegidos** (avanzado). Algoritmo (aplica
a Automático y Nodos elegidos): **Equilibrado** (predeterminado, por memoria y espacio libres) o
**Por turnos** (avanzado, P-L08).
- CA-L05.1 Dado "Un nodo", entonces las N MVs van a ese nodo; si no caben, falla V-L09/V-L11
  (no se reparten solas a otro).
- CA-L05.2 Algoritmo **Equilibrado**: para cada MV, en orden, entre los nodos elegibles
  (RF-L06) con espacio suficiente **tras descontar lo ya asignado en el plan**, se elige el
  de mayor memoria libre restante (`mem_libre_mib` menos la suma de `memoria_mib` ya
  asignada); desempate: mayor espacio libre del storage más amplio apto; desempate final:
  nombre del nodo ascendente. Es determinista.
- CA-L05.3 Dado cantidad 1, entonces el nodo que elige Automático coincide con el que
  `elegir_nodo` de M1 (P-07) para la misma entrada (test de equivalencia).
- CA-L05.4 Dado un mock de 3 nodos en línea con memoria libre 64, 32 y 32 GiB (`pve1`, `pve2`,
  `pve3`), el mismo storage con espacio idéntico y de sobra en los tres, plantilla de 8 GiB de
  memoria y cantidad 6, entonces el reparto Equilibrado es exactamente `pve1`, `pve1`, `pve1`,
  `pve1`, `pve1`, `pve2` (las cuatro primeras bajan `pve1` a 32 GiB; el empate de memoria se
  resuelve por espacio, igual aquí, y luego por nombre; la 6.ª pasa a `pve2` porque `pve1` quedó
  en 24 GiB frente a 32). El total por nodo nunca supera su capacidad de storage.
- CA-L05.5 Algoritmo **Por turnos**: nodos seleccionados en orden alfabético, MV i al nodo
  `i mod k`; un nodo que no puede alojar una MV se salta; si ninguno puede, falla ese
  elemento con E-L01.
- CA-L05.6 Dado `mem_libre_mib = None` en algún nodo (falta `Sys.Audit`), entonces ese nodo
  cuenta como memoria desconocida (-1, igual que M1), se avisa "No se pudo leer la memoria
  libre de <nodo>; el reparto usa el espacio" y se reparte por espacio y nombre.
- CA-L05.7 Dado un nodo fuera de línea, entonces no recibe MVs, aparece deshabilitado con
  "Sin conexión" (M1 CA-10.3) y no puede elegirse en "Nodos elegidos".
- CA-L05.8 Dado "Nodos elegidos" con 0 nodos, entonces V-L13 bloquea.
- CA-L05.9 El resumen muestra cuántas MVs recibe cada nodo y por qué ("Equilibrado: más
  memoria libre"), con texto traducido (M1 CA-13.5).
- CA-L05.10 Dado un nodo que cae **después** de la confirmación y antes de enviar sus MVs,
  entonces esas MVs no se reubican solas: quedan **No enviadas** (E-L10) y se ofrece
  "Reintentar pendientes" con un plan nuevo y confirmación (RF-L21). Un plan confirmado no
  cambia sin que el usuario lo vea.

#### RF-L06 Elegibilidad del nodo y almacenamiento — Debe — D-08, M1 V-16/V-17
Un nodo es elegible para la plantilla si está en línea y **en ese nodo** existen, activos, los
storages de todos los discos (y del efidisk si hay OVMF) con `images`, y los bridges de todas las
redes de la plantilla. Los storages **locales** se cuentan por nodo; los **compartidos**
(`shared=1`) una sola vez en todo el clúster (D-08).
- CA-L06.1 Dado un storage `local-lvm` presente en `pve1` y `pve2`, cada uno con su propio
  espacio, entonces el presupuesto es por clave `(nodo, storage)`: 150 GiB en `pve1` no se
  suman a los de `pve2`.
- CA-L06.2 Dado un storage `nfs1` con `shared=1` presente en todos los nodos con el mismo
  `avail`, entonces su presupuesto es una sola clave `(compartido, nfs1)`: 500 GiB una vez,
  aunque las MVs estén repartidas en 3 nodos.
- CA-L06.3 Dado un nodo donde falta el storage de la plantilla (o está inactivo), entonces ese
  nodo no es elegible en Automático/Nodos elegidos y se muestra el motivo ("`pve3`: no tiene
  el almacenamiento «local-lvm»"); en "Un nodo" se bloquea con V-17 de M1.
- CA-L06.4 Dado un nodo sin el bridge de la plantilla (V-16), entonces ídem CA-L06.3 con el
  motivo del bridge.
- CA-L06.5 Dado ningún nodo elegible, entonces E-L01 "Ningún nodo puede alojar esta plantilla".
- CA-L06.6 Dado un storage compartido listado como inactivo en un nodo y activo en otros,
  entonces ese nodo no es elegible para discos en él (V-17) pero su espacio sigue contándose
  una sola vez para los demás.
- CA-L06.7 Dado un storage compartido cuyo `avail` difiere entre nodos (lecturas en instantes
  distintos), entonces se usa el **menor** valor (conservador) y se registra en el log.
- CA-L06.8 El storage del efidisk (OVMF) participa en la elegibilidad y en el presupuesto; su
  tamaño contable es `TAM_EFIDISK_MIB` (4 MiB, propuesto, **[LAB]** LAB-L04 lo confirma).

### C. Validación previa del lote completo

#### RF-L07 Espacio acumulado por storage — Debe — D-08, P§6
Antes de crear nada, el núcleo suma, **por clave de presupuesto** (RF-L06), los GiB de todos los
discos de todas las MVs del plan y los compara con el espacio libre (`avail`).
- CA-L07.1 Dado una plantilla de 32 GiB, cantidad 5 y un storage no thin (`dir`) con 150 GiB
  libres en el nodo destino, entonces V-L09 **bloquea** (160 > 150) con "Las 5 máquinas
  necesitan 160 GiB en «local» y solo hay 150 GiB libres."
- CA-L07.2 Dado la misma plantilla y 4 máquinas (128 ≤ 150), entonces no hay error de espacio.
- CA-L07.3 Dado el valor exacto igual al libre (150 de 150), entonces pasa (la comparación es
  `≤`; en bytes, como V-14 de M1).
- CA-L07.4 Dado una plantilla con 2 discos en storages distintos, entonces cada storage se
  suma por separado.
- CA-L07.5 Dado un reparto en 2 nodos con storage local en cada uno, entonces la comprobación
  es por `(nodo, storage)` y el mensaje nombra el nodo.
- CA-L07.6 Dado un storage compartido y reparto en 3 nodos, entonces la suma de **todas** las
  MVs de **todos** los nodos se compara con el libre una sola vez (CA-L06.2).
- CA-L07.7 Dado que no cabe, el núcleo calcula `capacidad_maxima` (cuántas MVs de la plantilla
  caben con el algoritmo elegido) y la interfaz ofrece el botón "Reducir a N" (siempre
  ≥ 1; si 0, no se ofrece). Con P-L02 aprobada como recomendada, **no** se crea un lote
  parcial sin que el usuario reduzca la cantidad.
- CA-L07.8 Dado el espacio libre de un storage leído con más de `PLAN_MAX_EDAD_S` (300 s,
  propuesto) de antigüedad al confirmar, entonces se vuelve a leer y a validar antes de la
  confirmación (V-L14).
- CA-L07.9 Un test de propiedad: para cualquier plan que el validador acepta en storages no
  thin, la suma por clave nunca excede `avail`.

#### RF-L08 Política de sobreasignación en storages thin — Debe — CT-5, M1 P-01
Backends thin: `lvmthin`, `zfspool`, `rbd`. Política **propuesta** (decisión del usuario en
P-L01): aviso reforzado, con casilla de confirmación explícita y un tope duro.
- CA-L08.1 Dado un storage thin y suma ≤ libre, entonces no hay aviso.
- CA-L08.2 Dado un storage thin y libre < suma ≤ `FACTOR_THIN_MAX` × libre (3, propuesto),
  entonces V-L10 es un **aviso**: "Estás pidiendo 300 GiB y solo hay 150 GiB libres. Funciona
  mientras las máquinas no usen todo su disco; si se llena, todas las máquinas de ese
  almacenamiento pueden fallar." El resumen exige marcar "Entiendo el riesgo de sobreasignar
  espacio" para habilitar "Crear".
- CA-L08.3 Dado suma > `FACTOR_THIN_MAX` × libre (p. ej. 480 GiB pedidos con 150 libres), entonces
  V-L10 **bloquea**.
- CA-L08.4 Dado un lote con storages thin y no thin mezclados, entonces cada storage se evalúa
  con su regla (los no thin bloquean, CA-L07.1).
- CA-L08.5 Dado el modo básico, entonces el texto no usa "thin provisioning" sin explicarlo
  ("espacio prometido que no se reserva hasta usarlo", ayuda RF-L22).
- CA-L08.6 La casilla de confirmación no se recuerda entre lotes (se pide cada vez).
- CA-L08.7 Al cambiar P-L01 a "siempre bloquear" o "solo advertir", basta cambiar la
  política (enum `PoliticaThin`) sin tocar el resto (test que recorre las tres).

#### RF-L09 Recursos del nodo y permisos previos — Debería — M1 RF-12, RF-27
- CA-L09.1 Dado la suma de `memoria_mib` de las MVs asignadas a un nodo mayor que su memoria
  libre (`/nodes/{n}/status`, `Sys.Audit`), entonces V-L12 muestra un aviso no bloqueante por
  nodo ("En «pve2» pides 96 GiB de memoria y hay 64 GiB libres. Las máquinas se crean apagadas;
  el problema aparecerá al encenderlas."). Las MVs se crean detenidas (S-L2), por eso no
  bloquea.
- CA-L09.2 Dado `sockets × cores` de una MV mayor que los CPUs del nodo, aviso (M1 CA-27.1). La
  suma de vCPU del lote es solo informativa (la sobreasignación de CPU es normal).
- CA-L09.3 Dado que falta `VM.Allocate` (M1 CA-12.1), entonces "Simular" sigue disponible (la
  simulación es de solo lectura) pero "Crear" muestra el motivo y queda deshabilitado.
- CA-L09.4 Dado `GET /access/permissions` que falla, entonces no se bloquea (M1 CA-12.3) y el
  informe lo indica como "permisos no verificados".
- CA-L09.5 Dado un usuario con `VM.Allocate` solo en `/vms/<id>` concretos, entonces los
  VMIDs del plan fuera de ese conjunto producen 403 por MV (E-L16); **[LAB]** LAB-L05 mide si
  `GET /access/permissions?path=/vms/<id>` permite avisar antes (Podría).

### D. Resumen, confirmación y simulación

#### RF-L10 Pantalla de resumen y confirmación — Debe — D-12, P§6
Antes de crear, la interfaz muestra el plan completo y pide confirmación explícita.
- CA-L10.1 El resumen contiene: título "Vas a crear N máquinas"; tabla con una fila por MV
  (n.º, nombre, VMID, nodo, almacenamiento principal y tamaño total de discos); totales
  (MVs, procesadores virtuales, memoria total, espacio total por almacenamiento y nodo); reparto
  por nodo y motivo (CA-L05.9); VMIDs saltados (CA-L03.2); lista de avisos y de errores.
- CA-L10.2 Dado cualquier error bloqueante, entonces "Crear N máquinas" está deshabilitado,
  cada error indica qué campo corregir y "Simular" sigue activo.
- CA-L10.3 Dado un aviso no bloqueante (nombre repetido, memoria, memoria desconocida), entonces
  "Crear" sigue activo pero los avisos se muestran **antes** del botón y no se pueden ocultar;
  el aviso thin exige su casilla (CA-L08.2).
- CA-L10.4 Dado N > `UMBRAL_CONFIRMACION_DOBLE` (10, propuesto), entonces tras pulsar "Crear" se
  muestra un diálogo con "Se enviarán N máquinas a Proxmox. ¿Continuar?" con foco inicial en
  "Cancelar".
- CA-L10.5 La tabla de 100 filas se muestra con un modelo de datos (no 100 widgets), se
  desplaza con teclado y su contenido es copiable como texto.
- CA-L10.6 Dado que han pasado más de `PLAN_MAX_EDAD_S` desde que se generó el plan al pulsar
  "Crear", entonces se vuelve a leer el inventario y a validar; si el plan resultante difiere
  (nodo caído, espacio menor, VMID ocupado), se muestra la diferencia ("Cambió: el VMID 104 ya
  no está libre") y se exige confirmar de nuevo; no se envía nada hasta entonces (E-L11).
- CA-L10.7 Dado "Crear" pulsado dos veces seguidas, entonces se inicia **un** lote (la bandera se
  activa antes de lanzar nada, como M1 CA-19.6).
- CA-L10.8 El resumen es texto copiable ("Copiar resumen") y no contiene secretos (RNF-L06).
- CA-L10.9 Al confirmar, el plan queda congelado: ediciones posteriores del formulario no lo
  afectan (los campos se bloquean durante la ejecución como M1 CA-19.4).

#### RF-L11 Modo simulación — Debe — D-07, D-12
"Simular" ejecuta **todo menos las escrituras**: refresca el inventario, planifica, reserva VMIDs
(consultas), valida el lote completo y construye las peticiones exactas que se enviarían.
- CA-L11.1 Dado "Simular" con un mock de transporte que **falla la prueba si recibe cualquier
  método distinto de GET/HEAD**, entonces la simulación termina sin error de ese guardián
  (INV-L5). Una prueba de mutación lo comprueba: si el código de simulación intenta `POST` o
  `DELETE`, el test falla.
- CA-L11.2 La simulación muestra el mismo resumen de RF-L10 etiquetado "SIMULACIÓN — no se creó
  nada", más, por MV, el cuerpo de la petición `POST` que se enviaría (en detalles técnicos,
  copiable, sin cabeceras ni secretos).
- CA-L11.3 La simulación usa las mismas funciones de planificación y validación que la ejecución
  real (un solo camino de código; test que compara el plan de ambas con el mismo mock).
- CA-L11.4 La simulación consulta los VMIDs y la memoria/espacio **reales** del servidor
  conectado; no cambia nada en él (verificable en laboratorio, LAB-L12: el registro de acceso de
  `pveproxy` no muestra métodos distintos de GET durante la simulación).
- CA-L11.5 Dado un resultado de simulación sin errores, el botón "Crear" se habilita con "Crear
  de verdad estas N máquinas"; la creación real vuelve a ejecutar planificación y validación (el
  mundo pudo cambiar, CA-L10.6).
- CA-L11.6 Dado el selector de versión forzada de M1 (RF-26, solo avanzado), entonces la
  simulación valida contra la tabla de capacidades **forzada** y lo etiqueta "Simulado con
  compatibilidad de Proxmox <forzada> (el servidor es <detectada>)". Sirve para comprobar si el
  lote sería válido en otra versión; no cambia las lecturas, que siguen siendo del servidor real.
- CA-L11.7 Dado versión forzada **mayor** que la detectada, entonces la ejecución real queda
  bloqueada con "Has forzado una versión más nueva que la del servidor; solo puedes simular"
  (V-L15, E-L14). Forzada menor o igual: permitida (es más estricta). Sujeto a P-L10.
- CA-L11.8 La simulación puede exportarse como el informe (RF-L19) con el título "Simulación".
- CA-L11.9 Dada una simulación, ningún registro de lote queda como "libro" (no hay nada que
  deshacer) y no se escribe en disco más que el log.
- CA-L11.10 La simulación es cancelable y no bloquea la interfaz (RNF-L01).

### E. Ejecución

#### RF-L12 Ejecución, libro del lote e invariantes — Debe — P§6, M1 RF-19/RF-20
El motor recorre el plan y, por cada MV, reutiliza `ServicioCreacion.crear` (validar → reconsultar
VMID → POST → UPID → sondeo → comprobar `config`). El **libro del lote** (en memoria, sin
secretos) guarda por MV: nombre, VMID, nodo, estado, UPID, desenlace, error y marcas de tiempo.
- **INV-L1 (una sola vez):** el motor envía como máximo **un** `POST /nodes/{n}/qemu` por VMID y
  por ejecución. Nunca reenvía tras un fallo, un 596/597, un timeout o una conexión abortada
  (lección de M1: "envío incierto").
- **INV-L2:** antes de cada POST se reconsulta `GET /cluster/nextid?vmid=<n>` (ya lo hace
  `crear`).
- **INV-L3:** una MV que no consta como definitivamente no creada (E-L05/E-L06) no se vuelve a
  enviar ni se reutiliza su VMID dentro del mismo lote.
- **INV-L4:** el motor no escribe nada en Proxmox que no sea (a) `POST /nodes/{n}/qemu` de una MV del
  plan y (b) el rollback de RF-L18 sobre MVs del libro.
- **INV-L5:** en simulación no hay ninguna petición que no sea de lectura.
- CA-L12.1 Dado un mock que cuenta peticiones, cuando se inyecta un fallo en **cada** punto
  del flujo (timeout de lectura, conexión abortada, 595/596/597, 401, 403, 500, respuesta sin
  UPID, JSON inválido) y para cada MV del lote, entonces el número de `POST` por VMID es ≤ 1
  en todos los casos (prueba de inyección de fallos exhaustiva).
- CA-L12.2 Dado un lote en curso, "Crear" y "Simular" se deshabilitan; solo hay un lote activo
  por sesión.
- CA-L12.3 Concurrencia (por defecto, supuesto de P-L05): como máximo **1 creación en curso por
  nodo**, hasta `MAX_NODOS_PARALELOS` (4) nodos a la vez; las MVs de un mismo nodo se envían en el
  orden del plan. Con concurrencia 1 (modo secuencial) el orden global es el del plan.
- CA-L12.4 Dado un lote con k nodos, el total de peticiones simultáneas contra Proxmox nunca
  supera `MAX_PETICIONES_SIMULTANEAS` (8, igual que `MAX_HILOS` del descubrimiento); test con
  mock que cuenta la concurrencia máxima.
- CA-L12.5 Dado el sondeo de tareas, el intervalo es el de M1 (1,5 s) por tarea en curso; con k
  tareas en vuelo hay k sondeos por intervalo como máximo.
- CA-L12.6 La espera máxima por tarea y la tolerancia de red son las de M1 (10 min, 60 s) y se
  aplican **por MV**.
- CA-L12.7 Cada MV recorre los estados: `pendiente → validando → enviando → creando →
  comprobando` y termina en uno de: `ok`, `con_avisos`, `error`, `parcial`, `tiempo_agotado`,
  `conexion_perdida` (incierta; los seis son los `Desenlace` de M1), o en uno de los estados
  nuevos `no_enviada` (nunca se envió, E-L10, incluye la cancelación), `no_creada_segura`
  (CA-L15.2) y `existe_sin_confirmar_propiedad` (CA-L15.5).
- CA-L12.8 Un fallo inesperado en una MV (excepción) se registra, marca esa MV con
  `conexion_perdida` si el POST pudo salir, o `error` si no, y **no** aborta el lote.
- CA-L12.9 El motor corre en hilos de trabajo; los resultados llegan a la interfaz por señales
  en cola con coalescencia (RNF-L01, RNF-L05).
- CA-L12.10 El libro del lote es la única fuente de verdad del rollback (RF-L18) y del informe
  (RF-L19).

#### RF-L13 Progreso por MV y global — Debe — P§6, M1 RF-20, CT-2
- CA-L13.1 La interfaz muestra una tabla con una fila por MV: nombre, VMID, nodo, etapa
  (texto: "Validando datos", "Enviando a Proxmox", "Creando la máquina", "Comprobando el
  resultado", "Listo", o el desenlace) y, en fallo, el mensaje traducido.
- CA-L13.2 La barra global (naranja `#E57000`, D-02) refleja **MVs terminadas / N** con texto
  "7 de 20 terminadas · 1 con error · 2 en curso"; no hay porcentaje inventado dentro de una MV
  (CT-2). No se muestra tiempo estimado.
- CA-L13.3 El estado no depende solo del color: cada fila lleva texto y un símbolo (RNF-L04).
- CA-L13.4 Las filas con error o desenlace incierto se pueden filtrar ("Mostrar solo problemas")
  y seleccionar para ver "Detalles técnicos" (UPID, texto original, log de la tarea).
- CA-L13.5 La interfaz recibe como máximo `ACTUALIZACIONES_POR_S` (10) refrescos de tabla por
  segundo aunque lleguen cientos de eventos (coalescencia).
- CA-L13.6 El UPID de cada MV se muestra en monoespaciada y es copiable (M1 CA-20.9).
- CA-L13.7 Mientras corre el lote hay un botón "Cancelar lote" (RF-L16) visible.

#### RF-L14 Errores que no detienen el lote; pausa ante errores globales — Debe — P§6
- CA-L14.1 Dado un lote de 5 en el que la 2.ª MV falla (`exitstatus` con espacio insuficiente),
  entonces las MVs 1, 3, 4 y 5 se procesan; el informe da 4 creadas y 1 fallida con el error
  `SIN_ESPACIO` traducido.
- CA-L14.2 Dado un error **global** (`SESION_EXPIRADA`, `HUELLA_CAMBIADA`, `PERMISO_INSUFICIENTE`
  en `VM.Allocate`, sin ningún nodo en línea), entonces el lote **se pausa tras el primer
  caso** (el resto fallaría igual): no se envía ninguna MV más, las pendientes quedan "No
  enviadas" por pausa y se muestra el diálogo de acción (reconectar, reintentar, cancelar).
- CA-L14.3 Dado un error repetido no global (el mismo `CodigoError` en
  `UMBRAL_PAUSA_ERRORES` = 3 MVs consecutivas, propuesto, P-L09), entonces el lote se pausa con
  "Fallaron 3 máquinas seguidas por la misma causa: <mensaje>. ¿Continuar o detener?".
- CA-L14.4 Dado una pausa y la elección "Continuar", entonces se reanuda y no se vuelve a
  preguntar por esa causa en este lote. Dado "Detener", entonces se comporta como cancelación
  (RF-L16).
- CA-L14.5 Dado que un nodo concreto no responde (595/596 en GET, `NODO_NO_DISPONIBLE`),
  entonces solo se detienen las MVs de ese nodo (quedan "No enviadas", E-L10) y las de los demás
  nodos continúan.
- CA-L14.6 Cada error de MV muestra mensaje en lenguaje llano y acción sugerida (sección 7) y
  conserva el texto original en detalles técnicos (M1 RF-21).
- CA-L14.7 Dado un error de validación de una MV que el plan no previó (por ejemplo un bridge
  desaparecido, `RECURSO_INEXISTENTE`), entonces esa MV falla (`error`, nada creado) y las demás
  siguen.

#### RF-L15 Envío incierto y comprobación por MV — Debe — Bitácora 10-13
Una MV está en **envío incierto** si el POST pudo salir sin que se sepa el resultado: sin UPID y
con error de red (`SERVIDOR_NO_RESPONDE` con `incierto="1"`), HTTP 596/597, conexión abortada,
excepción inesperada tras enviar, o UPID recibido pero fallo de red sostenido en el sondeo
(`CONEXION_PERDIDA`, M1).
- CA-L15.1 Dado un 596 al enviar una MV (la bitácora 12 confirmó en vivo que la MV puede haberse
  creado), entonces esa MV queda `conexion_perdida` **sin reenvío** (INV-L1) y el lote continúa con
  las siguientes.
- CA-L15.2 Dado una MV incierta **sin UPID**, entonces el motor la reconcilia con
  `ServicioCreacion.existe_vm` mediante hasta 3 comprobaciones (`t = 0`, `+5 s`, `+15 s`,
  `COMPROBACIONES_EXISTENCIA`, propuesto) y concluye:
  existe → `ok` con aviso "se creó aunque Proxmox tardó en responder" (verificando etiqueta si
  RF-L24); no existe en las 3 → `no_creada_segura`; no se pudo saber (`None`) → sigue
  `conexion_perdida`.
- CA-L15.3 Dado una MV con UPID y fallo de red, entonces se usa `ServicioCreacion.seguir`/
  `comprobar_ahora` con el UPID (no `existe_vm`).
- CA-L15.4 `no_creada_segura` **no** hace que se reenvíe sola: solo la reintenta la acción
  explícita RF-L21 (con nueva reconsulta de VMID).
- CA-L15.5 Dado el resultado "existe" **sin** la etiqueta de este lote (con RF-L24 aprobada) y con
  la MV presente, entonces se marca `existe_sin_confirmar_propiedad` y **no** es elegible para
  rollback (RF-L18): podría ser de otro usuario que ganó la carrera por ese VMID.
- CA-L15.6 En el informe, toda MV incierta aparece con el texto "No sabemos si se creó" y un
  botón "Comprobar ahora" por MV y global ("Comprobar las N dudosas").
- CA-L15.7 El botón "Comprobar ahora" nunca envía un POST (test de contador de métodos).

#### RF-L16 Cancelación del lote — Debe — P§6
- CA-L16.1 Dado "Cancelar lote" durante la ejecución, entonces **no se envía ninguna MV más**; las
  pendientes quedan `no_enviada` (cancelado por el usuario) y se pide confirmación si hay MVs ya
  enviadas.
- CA-L16.2 Dado MVs ya enviadas (con UPID) al cancelar, entonces el motor **sigue esperando** su
  desenlace (hasta la espera máxima) para poder informar con certeza, salvo que el usuario elija
  "Dejar de esperar", que las deja `conexion_perdida` con su UPID. **No** se detiene ninguna tarea
  en Proxmox (se evita dejar MVs a medias; las tareas siguen).
- CA-L16.3 Dado "Cancelar lote", entonces se ofrece de inmediato "Deshacer lo creado" (RF-L18)
  sobre las MVs ya terminadas.
- CA-L16.4 Dado una MV a mitad del POST (aún sin respuesta) al cancelar, entonces se trata como
  incierta (RF-L15), nunca como "no enviada".
- CA-L16.5 Dado "Cancelar" tras el último envío, no tiene efecto sobre las tareas ya enviadas.
- CA-L16.6 La cancelación es efectiva en ≤ 2 s para las MVs no enviadas (el motor revisa el
  evento entre MVs y entre sondeos).

#### RF-L17 Pérdida de conexión, sesión expirada y reanudación — Debe — M1 RF-03, CA-20.7
- CA-L17.1 Dado una pérdida de red de hasta 60 s, entonces el sondeo y las comprobaciones se
  recuperan sin mensaje (M1 CA-20.7), por MV.
- CA-L17.2 Dado una pérdida sostenida > 60 s, entonces el lote entra en **pausa por conexión**:
  no se envía ninguna MV nueva; las MVs con UPID quedan `conexion_perdida`; se muestra "Se perdió la
  conexión. Hay N máquinas sin confirmar." con "Comprobar y continuar" y "Cancelar".
- CA-L17.3 "Comprobar y continuar": reconecta/reutiliza la sesión, comprueba cada MV con UPID
  (`comprobar_ahora`), cada incierta sin UPID (`existe_vm`), y luego envía **solo** las `pendiente`;
  nunca las ya enviadas (INV-L1/INV-L3).
- CA-L17.4 Dado `SESION_EXPIRADA`, entonces se abre el diálogo de conexión sin perder el lote (M1
  CA-03.3); tras reconectar al **mismo perfil** se ofrece continuar; si el perfil o servidor es otro,
  el lote queda cerrado con su informe y no se puede continuar ni deshacer contra el servidor nuevo
  (M1 `_al_conectar`: cambio de perfil).
- CA-L17.5 Dado que un nodo concreto vuelve a responder, "Reintentar pendientes" (RF-L21) lo
  incluye con un plan nuevo.
- CA-L17.6 Dado el ticket cerca de expirar (M1 CA-03.1/03.2) a mitad del lote, entonces el lote
  continúa sin pausa.

### F. Rollback

#### RF-L18 Rollback (deshacer lo creado por el lote) — Debe — P§6
Permite eliminar de Proxmox las MVs que **este lote creó en esta sesión**. Es una acción
**manual con confirmación** (P-L03). Requiere un cliente nuevo (`DELETE /nodes/{n}/qemu/{vmid}`,
**[LAB]** LAB-L05: permiso, parámetros, forma de enviarlos, comportamiento).
- CA-L18.1 **Elegibles** (propiedad demostrada): MVs del libro con desenlace `ok`, `con_avisos` o
  `parcial`, o `existe` confirmada con etiqueta del lote (RF-L24) y, en todos los casos, el VMID
  figura en el libro de **esta** sesión y del **mismo** servidor. Nunca otras MVs (INV-L4).
- CA-L18.2 **No elegibles**: MVs que no están en el libro; `existe_sin_confirmar_propiedad`
  (CA-L15.5), `no_creada_segura`, `no_enviada`, `error` sin MV presente; MVs de otro lote o de una
  sesión anterior. El motivo se muestra por fila.
- CA-L18.3 Dado el botón "Deshacer…", entonces se muestra una lista con casillas (todas las
  elegibles marcadas por defecto salvo las `ok` si el usuario eligió "Solo incompletas", P-L03) y
  un texto de advertencia: "Se eliminarán estas N máquinas y sus discos de Proxmox. Esta acción no
  se puede deshacer." El botón de confirmar lleva el número y el foco inicial va a "Cancelar".
- CA-L18.4 Antes de borrar **cada** MV, el motor lee su `config` (`GET …/qemu/{vmid}/config`) y
  verifica: existe; si hay etiqueta (RF-L24), contiene la del lote; no tiene `protection=1`; no
  está en ejecución. Si falla una condición, **no se envía el DELETE** y se informa (E-L18, E-L19,
  E-L20).
- CA-L18.5 El DELETE usa los parámetros definidos por LAB-L05 (propuestos:
  `destroy-unreferenced-disks=0`, sin `purge`; D-21) y devuelve un UPID que se sondea como
  cualquier tarea (M1 RF-20). El resultado por MV es `eliminada`, `ya_no_existia`,
  `fallo_al_eliminar` (E-L17) o `eliminacion_incierta`.
- CA-L18.6 Dado un 596/conexión abortada en un DELETE, entonces se verifica con `config_vm`: si ya
  no existe → `eliminada`; si existe → se puede **reintentar** el DELETE (idempotente en efecto,
  a diferencia del POST) solo tras comprobar existencia; no se reintenta a ciegas.
- CA-L18.7 Dado una MV `parcial` (tarea fallida con `config` presente, M1 CA-20.10), entonces es
  elegible; un `parcial` sin etiqueta propia se verifica por estar en el libro con ese VMID y
  UPID propio.
- CA-L18.8 Dado un error al eliminar una MV, entonces el rollback continúa con las demás (igual
  que RF-L14) y el informe lista las que quedaron sin borrar.
- CA-L18.9 Dado un permiso insuficiente para borrar (403), entonces el mensaje nombra el
  privilegio (extraído como M1 §7) y se detiene el rollback tras el primer caso (error global,
  RF-L14); las demás MVs quedan intactas.
- CA-L18.10 El rollback corre con las mismas reglas de concurrencia (≤ 1 DELETE por nodo) y
  cancelación que RF-L12/RF-L16.
- CA-L18.11 El rollback **no** elimina volúmenes huérfanos que no estén en la configuración de una
  MV del libro (no hay borrado de volúmenes sueltos en el MVP 2). Si una MV fallida deja
  volúmenes `vm-<vmid>-disk-N`, se informa "Pueden haber quedado discos sueltos; revísalos en
  Proxmox" (E-L21). **[LAB]** LAB-L04 comprueba si la creación fallida los deja.
- CA-L18.12 Tras el rollback se actualiza el informe (RF-L19) con una sección "Deshacer" y se
  refresca el inventario (VMIDs y espacio).
- CA-L18.13 Dado cantidad = 1 (M1), el rollback también se ofrece (enmienda a M1 CA-20.10).
- CA-L18.14 Dado que se cierra la aplicación o se cambia de servidor, el rollback ya no está
  disponible; el informe final indica cómo encontrar las MVs (etiqueta o rango de VMIDs) para
  borrarlas a mano.

### G. Informe y registro

#### RF-L19 Informe final — Debe — P§6
- CA-L19.1 Al terminar (o cancelar, o pausar), el informe muestra: título y fecha/hora local; tipo
  (real o simulación); nombre del perfil, versión de Proxmox, topología; resumen (N pedidas, N
  creadas, N con avisos, N fallidas, N inciertas, N no enviadas); tabla por MV (nombre, VMID, nodo,
  desenlace, UPID, error traducido y código, duración); parámetros de la plantilla (resumen);
  sección "Deshacer" si hubo.
- CA-L19.2 "Copiar informe" pone el texto plano (columnas alineadas con fuente monoespaciada) en
  el portapapeles; "Guardar informe…" lo escribe como `.txt` UTF-8 con la ruta que elige el usuario
  (`platformdirs` solo para la carpeta sugerida). Formato adicional según P-L11.
- CA-L19.3 El informe **no contiene** secretos: ni token, contraseña, ticket, CSRF, TOTP, ni
  cabeceras; tampoco el host/IP ni el usuario por defecto (solo el nombre del perfil), para poder
  compartirlo. (Prueba con centinela, RNF-L06.)
- CA-L19.4 Dado un informe con error, aparece el mensaje en lenguaje llano y, bajo "Detalles
  técnicos", el texto original (ya enmascarado).
- CA-L19.5 Dado un informe parcial por cierre de la aplicación, el texto de cierre (RF-L23)
  explica cómo ver qué se creó.
- CA-L19.6 Todos los textos del informe pasan por el sistema de traducción (RNF-L03); la plantilla
  del informe es parte del catálogo.
- CA-L19.7 El informe de un lote de 100 MVs se genera en < 1 s y no bloquea la interfaz.
- CA-L19.8 El informe es idéntico entre "copiar" y "guardar" (misma función de generación).

#### RF-L20 Registro (log) del lote — Debería — M1 RNF-13, RNF-06
- CA-L20.1 El log rotativo incluye, por MV: id de lote, VMID, nodo, UPID, etapa, desenlace, código
  de error y texto original de Proxmox, todo enmascarado con `enmascarar`.
- CA-L20.2 Con el centinela único como token, contraseña, ticket y CSRF, ninguna línea del log de
  un lote completo (con fallos inyectados) lo contiene.
- CA-L20.3 El id de lote (aleatorio, 8 hex) aparece en log, informe y etiqueta (RF-L24).
- CA-L20.4 El log no incluye cuerpos de respuesta completos, solo el texto de error acotado
  (`_MAX_DETALLE` de M1).

### H. Reintento, cierre y marca

#### RF-L21 Reintentar pendientes y fallidas — Podría — P§6
- CA-L21.1 Dado un lote terminado con MVs `no_enviada` o `error` (nada creado) o `no_creada_segura`,
  entonces "Reintentar pendientes" arma un **nuevo plan** con esos nombres y VMIDs, pasa por
  validación, resumen y confirmación (RF-L10) y permite cambiar el nodo.
- CA-L21.2 Nunca incluye MVs `ok`, `con_avisos`, `parcial`, `conexion_perdida` ni `existe_sin_...`
  (podrían existir).
- CA-L21.3 Antes de reintentar se reconsulta cada VMID (INV-L2); si ahora está ocupado, se aplica
  la política de P-L06.
- CA-L21.4 Es un lote nuevo con su propio id y su propio libro (el rollback del primero sigue
  accesible mientras dure la sesión).

#### RF-L22 Modo básico/avanzado y ayuda del lote — Debe — D-14
- CA-L22.1 En **modo básico** solo se ven: cantidad, prefijo, destino (Automático / Un nodo con
  selector), resumen, simular, crear, cancelar, informe, deshacer. El número inicial y el relleno
  usan los predeterminados.
- CA-L22.2 En **modo avanzado** además: separador, número inicial, relleno, VMID inicial, destino
  "Nodos elegidos", algoritmo, política de concurrencia (si P-L05 la expone), etiquetas
  (RF-L24).
- CA-L22.3 Cambiar de modo a mitad de la edición no pierde lo escrito (M1 CA-24.3); los valores
  ocultos se conservan y el resumen los muestra (M1 CA-24.5).
- CA-L22.4 Cada campo y concepto nuevo tiene ayuda en español llano (1–3 frases, sin jerga sin
  explicar): cantidad, prefijo, número inicial, relleno, VMID inicial, destino, reparto equilibrado,
  por turnos, sobreasignación ("thin"), simulación, deshacer, etiqueta, envío incierto. Un test
  comprueba que cada identificador de una lista fija tiene texto no vacío (M1 CA-25.2).
- CA-L22.5 La guía de usuario (`docs/guia-usuario.md`) documenta lotes, simulación y rollback
  (tarea de `documentador`, fuera de este documento) y la guía de token se actualiza si el
  rollback exige privilegios nuevos (LAB-L05).

#### RF-L23 Cierre de la aplicación durante un lote — Debe — M1 CA-20.8
- CA-L23.1 Dado un lote en ejecución o con rollback en curso al cerrar la ventana, entonces se pide
  confirmación: "Hay un lote en curso (X de N terminadas). Si cierras, las tareas ya enviadas
  seguirán en Proxmox, pero ProxLaunch no enviará el resto ni podrá deshacer lo creado."
  Opciones: "Seguir en ProxLaunch" (predeterminada) y "Cerrar de todos modos".
- CA-L23.2 Dado "Cerrar de todos modos", entonces se cancela el lote (RF-L16 sin esperar), se
  intenta guardar el informe parcial en la carpeta de usuario y se cierra la sesión. La espera
  tiene tope de 3 s (como M1).
- CA-L23.3 Dado que el informe parcial se guardó, el siguiente arranque muestra un aviso
  informativo "El último lote se cerró sin terminar. Informe: <ruta>" (no restaura el libro).

#### RF-L24 Marca de propiedad (etiqueta) — Debería (condicionada a P-L04) — D-12
Cada MV del lote se crea con `tags=proxlaunch;lote-<id>` (formato por confirmar **[LAB]** LAB-L06),
para demostrar propiedad ante envíos inciertos y tras cierres inesperados.
- CA-L24.1 Dado P-L04 aprobada, cada POST incluye `tags` con las dos etiquetas y el resto de la
  petición no cambia (CA-L04.2).
- CA-L24.2 Las etiquetas cumplen el formato de Proxmox (caracteres admitidos y separador);
  un test unitario genera ids y verifica el patrón. **[LAB]** LAB-L06 confirma el patrón en 9.2 y
  si el parámetro es aceptado en 8.0 (si no, se omite sin error según la tabla de capacidades,
  M1 RF-09).
- CA-L24.3 Dado P-L04 rechazada, no se envía `tags` y el rollback exige además que el VMID esté
  en el libro y que la MV venga de una respuesta con UPID propio (CA-L18.1).
- CA-L24.4 Dado que Proxmox rechaza `tags` (error de formato o de permiso `VM.Config.Options`), la
  MV falla con el error traducido (nada creado) y la causa se muestra; no se reintenta sin
  etiquetas sin consultar (no cambia el plan en silencio).
- CA-L24.5 La etiqueta se documenta en la guía y en *Acerca de* ("las máquinas creadas llevan la
  etiqueta «proxlaunch»").

---

## 3. Requisitos no funcionales

Siguen vigentes **todos** los RNF de M1 (RNF-01 a RNF-16) para el flujo de lotes; en particular
RNF-06 (secretos), RNF-07 (TLS), RNF-08 (sin pruebas destructivas en reales), RNF-09 (mocks de
respuestas reales), RNF-16 (codificación de entradas).

| ID | Requisito | Prioridad | Criterio de aceptación (verificable) |
|---|---|---|---|
| RNF-L01 | La interfaz no se congela durante planificar, simular, ejecutar ni deshacer | Debe | CA-RNF-L01: con un mock lento (10 s por petición) y un lote de 100 MVs, el retraso del bucle de eventos medido con un temporizador de 50 ms es < 200 ms (M1 CA-RNF-01). Todo el motor corre en hilos de trabajo; ningún `sleep` en el hilo de la interfaz. |
| RNF-L02 | El núcleo del lote no depende de Qt | Debe | CA-RNF-L02: en un entorno sin PySide6, la importación del núcleo del lote y su suite pasan; el reloj es el `Reloj` inyectable (esperas simuladas). |
| RNF-L03 | Todos los textos nuevos son traducibles | Debe | CA-RNF-L03: el análisis de literales (M1 CA-23.1) y la extracción (CA-23.2) cubren los textos nuevos; los plurales usan formas de Qt (`tr(…, n)`); el catálogo con prefijo "[T]" marca todos los textos del lote, del resumen y del informe. El núcleo devuelve códigos, la interfaz traduce. |
| RNF-L04 | Accesibilidad | Debe | CA-RNF-L04: contraste ≥ 4.5:1 en ambos temas para las tablas del lote (test sobre los pares definidos, M1 CA-22.5); estado de cada MV con texto + símbolo, nunca solo color; navegación por Tab y flechas en el resumen y en la tabla de progreso; foco visible; nombres accesibles (`accessibleName`) en tabla, barra y botones; los diálogos destructivos tienen "Cancelar" como foco inicial. |
| RNF-L05 | Rendimiento con lotes grandes | Debe | CA-RNF-L05 (mocks con latencia 100 ms): planificar 100 MVs (con reserva de VMIDs) ≤ 3 s; validar y generar resumen de 100 MVs ≤ 1 s de CPU; generar informe de 100 MVs < 1 s; 100 MVs completadas con mock instantáneo en ≤ 60 s de tiempo simulado. La interfaz refresca la tabla ≤ 10 veces/s (CA-L13.5); la tabla de 100 filas usa un modelo (no 100 widgets). Memoria del libro proporcional a N (sin conservar logs de tareas completos: ≤ `LINEAS_LOG_TAREA` por MV, y solo en MVs con avisos o error). |
| RNF-L06 | Secretos y privacidad | Debe | CA-RNF-L06: la prueba del centinela (M1 CA-RNF-06) se extiende a los flujos de lote: plan, simulación, ejecución con fallos inyectados, rollback, informe, resumen copiado, log y detalles técnicos. Cero coincidencias. El informe tampoco contiene host/IP ni nombre de usuario (CA-L19.3). |
| RNF-L07 | Carga razonable sobre Proxmox | Debe | CA-RNF-L07: ≤ 8 peticiones simultáneas (CA-L12.4); sondeo ≥ 1,5 s por tarea; la reserva de VMIDs usa el menor número posible de consultas (CA-L03.7). |
| RNF-L08 | Seguridad de las escrituras | Debe | CA-RNF-L08: INV-L1 a INV-L5 verificadas por pruebas de inyección de fallos y de contadores de métodos (CA-L12.1, CA-L11.1, CA-L15.7); los valores de usuario (prefijo, etiquetas) se codifican en el cuerpo del formulario (M1 RNF-16/CT-9); un prefijo con `,`, `=`, `&`, `;` o saltos de línea se rechaza por V-L02 antes de construir nada. |
| RNF-L09 | Determinismo | Debería | CA-RNF-L09: planificación, reparto y validación son funciones puras sobre `(plantilla, inventario, VMIDs libres)`; el mismo mock produce el mismo plan, resumen e informe (salvo marcas de tiempo, inyectadas con el reloj). |
| RNF-L10 | Compatibilidad de versiones | Debe | CA-RNF-L10: la suite de lotes pasa contra respuestas de 8.0, 8.x y 9.x (M1 RNF-05); las diferencias (p. ej. `tags`, DELETE) pasan por la tabla de capacidades (M1 CA-09.6). |
| RNF-L11 | Robustez del libro y de la interfaz | Debería | CA-RNF-L11: una excepción en la actualización de la interfaz no detiene el motor; una excepción del motor no deja la interfaz en estado "ocupado" para siempre (se libera con un desenlace explícito). |

---

## 4. Reglas de validación

Se implementan en el núcleo (sin Qt), con test unitario por fila, y se reflejan en la interfaz con el
mensaje indicado. Las reglas V-01 a V-23 de M1 siguen aplicándose a **cada MV del plan** con su
nodo y VMID; V-14 de M1 (espacio por MV) queda como condición necesaria y V-L09/V-L10 (espacio del
lote) es la autoritativa.

| ID | Campo | Regla | Severidad | Mensaje (al usuario) |
|---|---|---|---|---|
| V-L01 | Cantidad | Entero 1 ≤ N ≤ `MAX_LOTE` (100, propuesto) | Error | "Elige entre 1 y 100 máquinas." |
| V-L02 | Prefijo | No vacío; solo `A-Z a-z 0-9 . -`; sin `,` `=` `&` `;` espacios ni saltos de línea | Error | "El prefijo solo puede tener letras sin acentos, números y guiones." |
| V-L03 | Separador | Vacío o `-` | Error | "Elige un guion o ningún separador." |
| V-L04 | Nombres generados | Cada nombre cumple V-01 y número inicial en 0–999999; relleno 0–8 | Error | "El nombre «web_01» no es válido: …" (primer nombre inválido + causa) |
| V-L05 | Unicidad en el lote | Los nombres del plan son distintos | Error (interno, por construcción) | — |
| V-L06 | Nombre existente | Un nombre del plan coincide con una MV visible del servidor | Aviso | "Ya existe una máquina llamada «x» (VMID n)." |
| V-L07 | VMID inicial / rango | Entero 100–999999999; último VMID del plan ≤ 999999999 | Error | "El número inicial debe estar entre 100 y 999999999 y el lote debe caber." |
| V-L08 | VMIDs libres | Cada VMID confirmado con `/cluster/nextid?vmid=` ; ocupados se saltan en una ventana de `MAX_SALTO_VMID` (1000); sin ventana suficiente, error (E-L02) | Error / información "se saltó" | "No hay N números de máquina libres a partir de X." |
| V-L09 | Espacio (no thin) | Σ GiB por clave de presupuesto ≤ `avail` (bytes) | Error | "Las N máquinas necesitan X GiB en «s» y solo hay Y GiB libres." |
| V-L10 | Espacio (thin) | Σ > `avail` y ≤ `FACTOR_THIN_MAX` × `avail` (3): aviso con confirmación; superior: error | Aviso con casilla / Error | Ver CA-L08.2 |
| V-L11 | Elegibilidad por nodo | Nodo en línea; storages y bridges de la plantilla existen y están activos en ese nodo (V-04, V-16, V-17) | Error | "«pve3» no tiene el almacenamiento «local-lvm»." |
| V-L12 | Memoria del nodo | Σ `memoria_mib` asignada > memoria libre del nodo | Aviso | Ver CA-L09.1 |
| V-L13 | Destino | "Un nodo": 1 nodo en línea; "Nodos elegidos": ≥ 1 en línea | Error | "Elige al menos un nodo disponible." |
| V-L14 | Vigencia del plan | Inventario más viejo que `PLAN_MAX_EDAD_S` (300 s) → se relee y revalida antes de confirmar | Control interno | "Se actualizaron los datos del servidor." |
| V-L15 | Versión forzada | Forzada > detectada → ejecución real bloqueada (simulación permitida) | Error | Ver CA-L11.7 |
| V-L16 | Permiso de creación | Falta `VM.Allocate` (M1 RF-12) → "Crear" deshabilitado | Error | "Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate" |
| V-L17 | Un lote activo | No se puede iniciar otro lote ni descubrimiento mientras hay uno activo | Error | "Hay un lote en curso." |

---

## 5. Valores por defecto

Propuestos salvo indicación. Dirigidos a usuarios sin experiencia (D-14).

| Campo | Valor por defecto |
|---|---|
| Cantidad | 1 |
| Prefijo | vacío (obligatorio al pasar de 1; ejemplo de ayuda: `srv-web`) |
| Separador | `-` (avanzado) |
| Número inicial | 1 (avanzado) |
| Relleno | 2 dígitos, efectivo = máx(2, dígitos del mayor) (avanzado) |
| VMID inicial | `/cluster/nextid` (editable en avanzado) |
| Destino (clúster) | Automático (equilibrado) |
| Destino (servidor individual) | el único nodo, sin selector |
| Algoritmo | Equilibrado (avanzado: Por turnos) |
| Nodos elegidos (avanzado) | todos los elegibles |
| Política de VMIDs ocupados | saltar al siguiente libre (P-L06) |
| Política de sobreasignación thin | aviso con casilla de confirmación; error si > 3 × libre (P-L01) |
| `MAX_LOTE` | 100 (P-L07) |
| `MAX_SALTO_VMID` | 1000 |
| `UMBRAL_CONFIRMACION_DOBLE` | 10 máquinas |
| `UMBRAL_PAUSA_ERRORES` | 3 consecutivos, misma causa (P-L09) |
| Concurrencia | 1 creación en curso por nodo; hasta 4 nodos en paralelo (P-L05) |
| `MAX_PETICIONES_SIMULTANEAS` | 8 |
| `MAX_CONSULTAS_SIMULTANEAS` (VMIDs) | 8 |
| `COMPROBACIONES_EXISTENCIA` | 3 (t = 0, +5 s, +15 s) |
| `PLAN_MAX_EDAD_S` | 300 s |
| `TAM_EFIDISK_MIB` | 4 MiB (contable, LAB-L04) |
| `ACTUALIZACIONES_POR_S` (interfaz) | 10 |
| Sondeo, espera máxima de tarea, tolerancia de red | 1,5 s, 10 min, 60 s (M1) |
| Etiquetas | `proxlaunch;lote-<id>` si P-L04 aprobada |
| Rollback | manual, con confirmación; nada automático (P-L03) |
| Informe | texto plano UTF-8; copiar y guardar |
| Plantilla (cómputo, disco, red) | los de M1 (2 cores, 2 GiB, 32 GiB, `vmbr0`…) |

---

## 6. Permisos de Proxmox del lote

El lote **no añade** privilegios para crear: usa los de M1 (F1 §5, 10 privilegios del rol
`ProxLaunchCreador`). Por cada MV se consulta `…/qemu/{vmid}/config` (`VM.Audit`, ya en el rol).

| Acción nueva | Endpoint | Privilegio | Estado |
|---|---|---|---|
| Reserva de VMIDs | `GET /cluster/nextid?vmid=` | Todos (F1 §5) | Confirmado en F1/F6 |
| Comprobar existencia / etiqueta antes de borrar | `GET /nodes/{n}/qemu/{vmid}/config` | `VM.Audit` en `/vms/{vmid}` | Confirmado F1 |
| Nombres existentes (aviso) | `GET /cluster/resources?type=vm` | Solo lista lo que el usuario puede ver (`VM.Audit`) | **[LAB]** LAB-L11 |
| Etiquetar la MV al crear | `POST …/qemu` con `tags` | `VM.Config.Options` (ya en el rol) | **[LAB]** LAB-L06 |
| Borrar una MV (rollback) | `DELETE /nodes/{n}/qemu/{vmid}` | Esperado: `VM.Allocate` en `/vms/{vmid}`, ya en el rol | **[LAB]** LAB-L05 (no consta en F1) |
| Borrar discos al eliminar | ídem, parámetro `destroy-unreferenced-disks` | Posible requisito adicional sobre `/storage/{id}` | **[LAB]** LAB-L05 |
| Sondeo de la tarea de borrado | `GET …/tasks/{upid}/status` | Propietario de la tarea (F1 §5) | Confirmado F1 |

Efecto sobre el rol mínimo: **ninguno si LAB-L05 confirma `VM.Allocate`**; en otro caso, el rol
sube de 10 a 10 + k privilegios y se decide el texto de la guía de token (P-L03). Hasta
verificarlo, el rollback de la interfaz **no se habilita** para un usuario cuyos permisos
(`/access/permissions`) no incluyan `VM.Allocate` (V-L16) y registra la verificación pendiente.

Nota de transporte: `DELETE` no es un método seguro (`_METODOS_SEGUROS` solo tiene GET y HEAD),
así que no hay failover automático de host en él (correcto). Los parámetros de un `DELETE` en la
API de Proxmox suelen ir en la cadena de consulta, no en el cuerpo: **[LAB]** LAB-L05. El cliente
actual envía los datos de las peticiones no GET en el cuerpo del formulario; el método de borrado
necesitará decidir según el resultado de LAB-L05.

---

## 7. Errores nuevos y su traducción

Los códigos se añaden a `CodigoError` (núcleo, sin textos); la interfaz los traduce (RNF-L03).
Cada fila es un test parametrizado con un mock (como M1 §7). "Params" son los parámetros del error.

| ID | Código propuesto | Disparador (mock) | Mensaje en lenguaje llano | Params |
|---|---|---|---|---|
| E-L01 | `lote_sin_nodo_apto` | Ningún nodo elegible para la plantilla (RF-L06) o sin capacidad para una MV | "Ningún servidor puede alojar esta máquina. Revisa que el almacenamiento y la red existan en los nodos elegidos." | nodos, motivos por nodo |
| E-L02 | `lote_vmids_insuficientes` | No hay N VMIDs libres en la ventana / el rango se sale de 999999999 | "No encontré {n} números de máquina libres a partir del {inicio}. Prueba con otro número inicial o menos máquinas." | n, inicio |
| E-L03 | `vmid_ocupado` (existente) | Carrera: `already exists` en el POST o en la reconsulta | "El número {vmid} lo usó otra persona mientras tanto. Esta máquina no se creó." (acción: "Reintentar pendientes") | vmid, siguiente |
| E-L04 | `lote_sin_espacio` | V-L09/V-L10 bloqueante | "Las {n} máquinas necesitan {pedido} GiB en «{storage}» y solo hay {libre} GiB libres. Caben {max}." (botón "Reducir a {max}") | storage, pedido, libre, max, nodo |
| E-L05 | `lote_envio_incierto` | POST sin respuesta o 596/597 (RF-L15) | "No sabemos si «{nombre}» se creó. No se volverá a enviar: pulsa «Comprobar» para verlo." | nombre, vmid |
| E-L06 | `lote_existencia_indeterminada` | `existe_vm` devuelve `None` tras las comprobaciones | "No pudimos comprobar si «{nombre}» existe. Revisa la conexión y vuelve a comprobar antes de crearla otra vez." | nombre, vmid |
| E-L07 | `lote_pausado_repetido` | `UMBRAL_PAUSA_ERRORES` consecutivos con la misma causa | "Fallaron {n} máquinas seguidas por la misma causa: {mensaje}. ¿Continuar o detener?" | n, causa |
| E-L08 | `servidor_no_responde` (existente) | Fallo de red durante la planificación o reserva | "No se pudo consultar el servidor. No se creó nada." | host |
| E-L09 | `lote_pausado_conexion` | Pérdida > 60 s en el lote | "Se perdió la conexión. Hay {n} máquinas sin confirmar." (acción: "Comprobar y continuar") | n |
| E-L10 | `lote_no_enviada` | MV sin enviar por cancelación, pausa, error global o nodo caído | "«{nombre}» no se envió ({motivo}). No existe en Proxmox." | motivo |
| E-L11 | `lote_plan_cambio` | El plan al confirmar difiere del resumen (V-L14) | "Los datos del servidor cambiaron: {diferencia}. Revisa el resumen y confirma otra vez." | diferencia |
| E-L12 | `lote_en_curso` | V-L17 | "Hay un lote en curso. Espera a que termine o cancélalo." | — |
| E-L13 | `lote_cantidad_invalida` | V-L01 | "Elige entre 1 y {max} máquinas." | max |
| E-L14 | `version_forzada_mayor` | V-L15 | "Has forzado una versión más nueva que la del servidor ({detectada}); solo puedes simular." | forzada, detectada |
| E-L15 | `etiqueta_rechazada` | Proxmox rechaza `tags` (formato/permiso) | "Proxmox no aceptó la etiqueta de la máquina. No se creó." | detalle |
| E-L16 | `permiso_insuficiente` (existente) | 403 por MV sobre un VMID sin `VM.Allocate` | "No tienes permiso para crear la máquina {vmid}. Pide a tu administrador permiso sobre ese número." | privilegio, ruta |
| E-L17 | `rollback_fallo` | Tarea de borrado con `exitstatus` de error | "No se pudo eliminar «{nombre}»: {mensaje}. Elimínala desde Proxmox." | nombre, vmid |
| E-L18 | `rollback_no_propia` | Sin libro, etiqueta ajena o VMID distinto | "No eliminamos «{nombre}» porque no podemos asegurar que la creó este lote." | vmid |
| E-L19 | `rollback_encendida` | La MV está en ejecución (`status: running`) | "«{nombre}» está encendida. Apágala en Proxmox y vuelve a intentarlo." | nombre |
| E-L20 | `rollback_bloqueada` | `protection=1` o `lock` en la config / error de bloqueo | "«{nombre}» está protegida o bloqueada. Quita la protección en Proxmox." | nombre, motivo |
| E-L21 | `rollback_discos_sueltos` | MV fallida con volúmenes `vm-<id>-disk-N` (si LAB-L04 lo confirma) | "Pueden haber quedado discos sueltos de «{nombre}»; revísalos en Proxmox." | nombre |
| E-L22 | `rollback_incierto` | DELETE sin respuesta y existencia no determinable | "No sabemos si se eliminó «{nombre}». Comprueba antes de reintentar." | nombre |
| E-L23 | `escritura_en_simulacion` | Guardián de INV-L5 (error de programación) | "Error interno: se intentó escribir en modo simulación. No se creó nada." | — |

Los patrones de texto de Proxmox para E-L18…E-L22 (p. ej. "VM is locked", "VM is running",
"protected") son **[LAB]** LAB-L05; hasta verificarlos, los errores de borrado no reconocidos caen en
el genérico "Proxmox respondió con un error que no conocemos" (M1 CA-21.2) con el texto original.

---

## 8. Matriz de trazabilidad con el alcance

| Elemento del alcance (D-12 / pedido) | Requisitos |
|---|---|
| Cantidad y límites | RF-L01, V-L01 |
| Nombres secuenciales | RF-L02, V-L02..V-L06 |
| VMIDs secuenciales y reserva en el clúster | RF-L03, V-L07, V-L08, INV-L2 |
| Compatibilidad con M1 / plantilla | RF-L04 |
| Reparto entre nodos | RF-L05, RF-L06, V-L11, V-L13 |
| Storage local vs compartido | RF-L06, RF-L07 |
| Validación de espacio del lote | RF-L07, V-L09 |
| Política thin | RF-L08, V-L10 |
| RAM/CPU y permisos | RF-L09, V-L12, V-L16 |
| Resumen y confirmación | RF-L10, V-L14 |
| Modo simulación y versión forzada | RF-L11, V-L15, INV-L5 |
| Ejecución, concurrencia, una vez | RF-L12, INV-L1..L4, RNF-L07 |
| Progreso por MV y global | RF-L13 |
| Errores no detienen el lote | RF-L14 |
| Envío incierto / `existe_vm` | RF-L15, E-L05, E-L06 |
| Cancelación | RF-L16 |
| Conexión perdida / reanudar | RF-L17, E-L09 |
| Rollback | RF-L18, RF-L24, E-L17..E-L22 |
| Informe y registro | RF-L19, RF-L20, RNF-L06 |
| Reintentar | RF-L21 |
| Básico/avanzado y ayuda | RF-L22 |
| Cierre de la aplicación | RF-L23 |
| Etiqueta de propiedad | RF-L24 |

### 8.1 Trazabilidad RF → CA → tipo de prueba

"Mock" = prueba automática con mocks sin red; "Prop." = prueba de propiedad/inyección de fallos;
"UI" = prueba de interfaz (pytest-qt); "LAB" = integración contra el laboratorio (opcional,
RNF-08).

| RF | Criterios | Mock | Prop. | UI | LAB |
|---|---|---|---|---|---|
| RF-L01 | CA-L01.1..L01.5 | x | | x | |
| RF-L02 | CA-L02.1..L02.8 | x | x (L02.5) | x (L02.6) | LAB-L07 (L02.7) |
| RF-L03 | CA-L03.1..L03.9 | x | x (L03.4) | | LAB-L02, L03, L11 |
| RF-L04 | CA-L04.1..L04.5 | x | | x | LAB-L01 |
| RF-L05 | CA-L05.1..L05.10 | x (3 nodos) | x (determinismo) | x (L05.9) | solo 1 nodo real |
| RF-L06 | CA-L06.1..L06.8 | x (compartido, local) | | | LAB-L04 (L06.8) |
| RF-L07 | CA-L07.1..L07.9 | x | x (L07.9) | x (L07.7) | LAB-L04 |
| RF-L08 | CA-L08.1..L08.7 | x | | x | LAB-L04 |
| RF-L09 | CA-L09.1..L09.5 | x | | x | LAB-L05 |
| RF-L10 | CA-L10.1..L10.9 | x | | x | LAB-L01 |
| RF-L11 | CA-L11.1..L11.10 | x (guardián de métodos) | x (mutación) | x | LAB-L12 |
| RF-L12 | CA-L12.1..L12.10 | x | x (L12.1 inyección en cada punto) | | LAB-L01, L10, L13 |
| RF-L13 | CA-L13.1..L13.7 | x | | x | |
| RF-L14 | CA-L14.1..L14.7 | x | | x | LAB-L04 |
| RF-L15 | CA-L15.1..L15.7 | x (596 simulado) | x | x | LAB-L09 |
| RF-L16 | CA-L16.1..L16.6 | x | x | x | LAB-L08 |
| RF-L17 | CA-L17.1..L17.6 | x (reloj simulado) | | x | LAB-L09 |
| RF-L18 | CA-L18.1..L18.14 | x | x (propiedad) | x | LAB-L05, L06 |
| RF-L19 | CA-L19.1..L19.8 | x | | x | |
| RF-L20 | CA-L20.1..L20.4 | x | x (centinela) | | |
| RF-L21 | CA-L21.1..L21.4 | x | | x | |
| RF-L22 | CA-L22.1..L22.5 | | | x | |
| RF-L23 | CA-L23.1..L23.3 | | | x | |
| RF-L24 | CA-L24.1..L24.5 | x | | | LAB-L06 |
| RNF-L01..L11 | CA-RNF-L01..L11 | x | x | x | LAB-L13 (L05) |

---

## 9. Preguntas abiertas — RESUELTAS (D-20, 2026-11-13)

**El usuario aprobó las 12 recomendaciones** (D-20 en `docs/decisiones.md`). Los valores
marcados "propuesto" en §5 pasan a ser definitivos. Se conserva el texto original de cada
pregunta como referencia.

**P-L01 — Política de sobreasignación en storages thin (CT-5, M1 P-01).** Un lote multiplica el
riesgo: 50 MVs de 100 GiB caben "sobre el papel" en un pool thin de 500 GiB.
- A) Bloquear siempre que la suma supere el espacio libre (más seguro, impide usos legítimos).
- B) Solo advertir (lo de M1; fácil de ignorar con muchas MVs).
- C) Advertir con casilla de confirmación explícita y bloquear solo si la suma supera
  `FACTOR_THIN_MAX` × libre (3).
- **Recomendación: C.** Mantiene la decisión ya aprobada para una MV (advertir, M1 P-01), añade
  fricción proporcional al riesgo del lote y evita un lote absurdo; el factor es una constante
  fácil de cambiar. Afecta: RF-L08, V-L10.

**P-L02 — Si el lote no cabe, ¿qué hace la aplicación?**
- A) Bloquear el lote completo, mostrar cuántas caben y ofrecer "Reducir a N".
- B) Permitir crear solo las que caben (lote parcial) con confirmación.
- C) Bloquear sin sugerir.
- **Recomendación: A.** Un lote parcial entrega algo distinto de lo pedido (y numeración con
  huecos); el botón "Reducir a N" da el atajo sin decidir por el usuario. Afecta: CA-L07.7.

**P-L03 — Rollback: ¿manual o automático, y de qué alcance?** (D-12 pide rollback; P§6 dice
"ofrecer la opción de limpieza".)
- A) Solo manual, con lista y confirmación; el usuario elige entre "Solo incompletas" (parcial) y
  "Todo lo creado por el lote".
- B) Automático: si el lote falla, borrar lo creado sin preguntar.
- C) Automático solo de las MVs `parcial`, manual para el resto.
- **Recomendación: A.** Borrar es irreversible, el envío incierto no permite saber la propiedad
  con certeza y D-15 prohíbe pruebas destructivas en reales: ninguna eliminación sin un clic
  explícito. Dependencia: si LAB-L05 muestra que borrar exige más privilegios que los 10 del rol,
  hay que decidir si se **amplía el rol de la guía** (el rollback queda disponible solo para quien
  los tenga) o se retira el rollback del MVP. Afecta: RF-L18, sección 6.

**P-L04 — ¿Etiquetar en Proxmox las MVs del lote (`tags=proxlaunch;lote-<id>`)?**
- A) Sí, siempre (en lotes y en la MV única).
- B) Sí, pero opción en avanzado, activada por defecto.
- C) No etiquetar; la propiedad se demuestra solo con el libro en memoria.
- **Recomendación: B.** Sin etiqueta, tras un envío incierto o un cierre inesperado no se puede
  demostrar que una MV es del lote (podría ser de otro usuario con el mismo VMID); con ella, el
  rollback se vuelve verificable y el usuario puede filtrar en Proxmox lo que creó ProxLaunch. Es
  visible para todos los usuarios del servidor y cambia la petición de M1: por eso se permite
  desactivarla. **[LAB]** LAB-L06. Afecta: RF-L24, CA-L04.1, CA-L15.5, CA-L18.1.

**P-L05 — Concurrencia de la creación.**
- A) Secuencial (1 MV a la vez en todo el lote): más simple, más lento, el menor riesgo.
- B) 1 por nodo y hasta 4 nodos en paralelo (reparto real entre nodos).
- C) Hasta N en paralelo también dentro de un mismo nodo (rápido; riesgo de bloqueos de storage).
- **Recomendación: B** (con modo secuencial como opción si LAB-L10 muestra problemas). Las MVs de
  distinto nodo no compiten por el mismo storage local, y las de un nodo no se pisan; el costo es
  que el progreso llegue desordenado entre nodos. Requiere revisar que `ClienteProxmox` y el
  transporte sean seguros entre hilos (el descubrimiento ya los usa en paralelo). Afecta: CA-L12.3.

**P-L06 — VMIDs ocupados dentro del rango del lote.**
- A) Saltar los ocupados y asignar los siguientes libres (VMIDs no consecutivos, avisando).
- B) Exigir VMIDs consecutivos: buscar el primer bloque contiguo libre de N (puede saltar lejos).
- C) Bloquear y que el usuario elija otro inicio.
- Sub-decisión ante una **carrera** (el VMID se ocupa entre el resumen y el envío): (i) fallar esa
  MV y ofrecer reintentar; (ii) reasignarla sola al siguiente libre.
- **Recomendación: A + (i).** El prompt pide secuenciales, pero "consecutivo a toda costa" puede
  mover el lote cientos de números; mostrar los saltos mantiene el plan transparente. Reasignar
  sola cambiaría un plan ya confirmado. Afecta: RF-L03, CA-L03.8.

**P-L07 — Tamaño máximo de un lote.**
- A) 20. B) 50. C) 100. D) 250. E) Sin tope técnico.
- **Recomendación: C (100), como constante.** Cubre aulas y laboratorios habituales, mantiene la
  validación y el informe manejables y limita la carga contra Proxmox (RNF-L05, RNF-L07). Para
  más, varios lotes. Afecta: V-L01.

**P-L08 — Algoritmo de reparto predeterminado y qué ve el usuario básico.**
- A) Equilibrado (greedy con descuento de memoria y espacio) por defecto; "Por turnos" en avanzado.
- B) Por turnos por defecto.
- C) Llenar un nodo antes de pasar al siguiente.
- **Recomendación: A.** Es la generalización natural de P-07 (D-08 dice "más RAM y espacio libres") y
  con N = 1 coincide con M1. En básico solo se ve "Automático" y "Un nodo". Afecta: RF-L05.

**P-L09 — Qué hacer ante errores repetidos.** P§6 pide no detener el lote por una MV, pero un error
global lo haría fallar entero.
- A) No pausar nunca (puede enviar 100 peticiones destinadas a fallar).
- B) Pausar de inmediato ante errores globales (sesión, huella, permiso de `VM.Allocate`, sin nodos) y
  tras 3 fallos consecutivos con la misma causa en los demás.
- C) Detener el lote ante el primer error.
- **Recomendación: B** (umbral 3). Respeta P§6 y evita ruido en el servidor y en el informe.
  Afecta: RF-L14, `UMBRAL_PAUSA_ERRORES`.

**P-L10 — Simulación y versión forzada; simulación sin conexión.**
- A) Simulación solo conectada (lecturas reales). La versión forzada solo cambia la tabla de
  capacidades; la ejecución real con versión forzada **mayor** que la detectada se bloquea.
- B) Igual que A pero permitir la ejecución real con cualquier versión forzada (como M1).
- C) Además, "simulación sin conexión" sobre un inventario escrito a mano o importado.
- **Recomendación: A.** Es la forma de cumplir D-07 ("simular") sin inventar un inventario falso;
  bloquear forzada > detectada evita enviar parámetros que el servidor no conoce. La simulación sin
  conexión depende de guardar inventarios y lotes (MVP 3). Afecta: RF-L11, V-L15.

**P-L11 — Formato del informe exportable.**
- A) Solo copiar al portapapeles (texto).
- B) Copiar y guardar `.txt`.
- C) Además guardar `.csv` (una fila por MV) y `.json`.
- **Recomendación: B** en MVP 2; el CSV se evalúa con la importación del MVP 3. Mantiene el alcance
  y cubre "copiar/exportar texto". Afecta: RF-L19.

**P-L12 — Personalización del lote.**
- A) Lote homogéneo: una plantilla; solo difieren nombre, VMID y nodo. Sin edición por MV.
- B) Permitir en el resumen excluir MVs individuales o cambiar su nodo.
- C) Lote heterogéneo (cada MV con su plantilla).
- **Recomendación: A.** Es lo que D-12 describe y deja lo heterogéneo para CSV y perfiles (MVP 3).
  Excluir una MV rompería la numeración sin avisar. Afecta: CA-L04.5.

---

## 10. Pruebas de laboratorio necesarias [LAB]

El laboratorio es **un nodo PVE 9.2.26** (D-15). Todo lo multinodo (reparto, nodo caído, almacenamiento
compartido, ACL por rango) se prueba solo con mocks. Los LAB se ejecutan únicamente con la variable de
entorno explícita (M1 RNF-08) y limpian lo que crean; el laboratorio se elimina al terminar el
proyecto (D-15).

| ID | Verificar | Cierra |
|---|---|---|
| LAB-L01 | Lote de 5 MVs en el nodo: nombres, VMIDs consecutivos, `config` comprobada, tiempos; N=1 equivale a M1 | CA-L04.1, L10, L12 |
| LAB-L02 | Con una MV existente en el rango (p. ej. 101), el lote salta ese VMID | CA-L03.2 |
| LAB-L03 | `nextid` sin parámetro devuelve el mismo ID a peticiones simultáneas (CT-8) y desde cuándo `nextid?vmid=` marca ocupado un VMID tras el POST (ventana de carrera) | CA-L03.3, L03.8, S-L5 |
| LAB-L04 | Lote que no cabe en un LVM temporal pequeño (como F6): qué MVs fallan, el texto de `SIN_ESPACIO`, si quedan volúmenes huérfanos, tamaño real del efidisk, si el lote sigue con las demás | CA-L14.1, L18.11, L06.8, E-L21 |
| LAB-L05 | `DELETE /nodes/{n}/qemu/{vmid}`: privilegio mínimo (probar el rol de 10 privilegios), forma de enviar parámetros (consulta/cuerpo), `destroy-unreferenced-disks`, `purge`, UPID devuelto, comportamiento con MV encendida, `protection=1`, `lock`, MV `parcial`; textos de error; `GET /access/permissions?path=/vms/<id>` | RF-L18, sección 6, E-L17..L22 |
| LAB-L06 | `tags` aceptado en 8.x/9.2, patrón válido de etiquetas, privilegio exigido, visible en `config`, formato de `;` / `,` | RF-L24, P-L04 |
| LAB-L07 | ¿Proxmox permite dos MVs con el mismo nombre? | S-L6, CA-L02.7 |
| LAB-L08 | Cancelación a mitad: las tareas enviadas siguen y terminan; qué `config` queda | RF-L16 |
| LAB-L09 | Envío incierto real: un proxy TCP local que descarta la respuesta (o 596 provocado) tras el POST de una MV de un lote; la comprobación `existe_vm` a t = 0/+5/+15 s | RF-L15, RF-L17 |
| LAB-L10 | Concurrencia 1/2/4 en el mismo nodo (LVM-thin y directorio): éxito de todas las tareas, bloqueos, tiempos | P-L05 |
| LAB-L11 | `GET /cluster/resources?type=vm` con el rol mínimo: ¿lista todas las MVs o solo las visibles?; sirve para el aviso de nombres existentes | V-L06, CA-L03.3 |
| LAB-L12 | Simulación: el registro de acceso de `pveproxy` solo muestra GET durante una simulación | CA-L11.4 |
| LAB-L13 | Lote de 30–50 MVs de 1 GiB en `local-lvm` + rollback completo; tiempos y estabilidad de la interfaz | RNF-L05, RF-L18 |

Mocks multinodo a preparar (sintéticos, a partir de respuestas reales): 3 nodos con memorias
distintas; `local-lvm` en cada nodo con espacios distintos; un storage `shared=1`; un nodo sin el
bridge de la plantilla; un nodo que cae a mitad (595/596); ACL parcial (403 en ciertos VMIDs).

---

## 11. Casos límite específicos del lote (para el probador)

1. Cantidad 1, 2, 100 y 101 (límite de V-L01).
2. Relleno efectivo al cruzar 9→10, 99→100.
3. Prefijo de 60 y 63 caracteres.
4. VMID inicial 999999995 con cantidad 10 (rebasa el máximo).
5. VMID ocupado en medio, al principio, al final y en varios consecutivos.
6. `nextid?vmid` que falla por red en el 7.º VMID de 10 (abortar sin plan parcial).
7. Todos los nodos con espacio justo exacto (igualdad) y 1 GiB por debajo.
8. Storage compartido con `avail` distinto entre nodos; storage inactivo en un nodo.
9. Nodo con memoria `None`; todos los nodos con memoria `None`.
10. Un nodo cae justo antes de enviar su primera MV; cae durante una tarea ya enviada.
11. 596 en la 1.ª, en la última y en todas las MVs; 597 tras entrega real.
12. `SESION_EXPIRADA` a mitad del lote y reconexión al mismo perfil y a otro.
13. Cancelar antes del primer envío, con una MV a mitad de POST, y tras el último.
14. Rollback con una MV encendida, protegida, ya borrada por otro, de otro lote, sin etiqueta y con
    etiqueta ajena.
15. Cierre de la aplicación en cada estado del lote (planificando, ejecutando, pausado, deshaciendo).
16. Doble clic en "Crear", "Cancelar" y "Deshacer".
17. Cambio de tema y de modo básico/avanzado durante un lote; catálogo de prueba "[T]" cargado.
18. Informe con nombres con caracteres no ASCII en el nombre del perfil, ruta de guardado con
    espacios (Windows y Ubuntu).

---

## 12. Enmiendas a M1

| Elemento de M1 | Enmienda en MVP 2 |
|---|---|
| M1 §1.2 "Lotes, validación de lote, reparto, rollback, simulación (MVP 2)" | Se implementan aquí. |
| M1 CA-13.5 ("Repartir el lote" no aparece) | Aparece con cantidad > 1 como destino "Automático/Nodos elegidos" (RF-L05). Con cantidad 1 no hay diferencia. |
| M1 CA-19.3 (petición ejemplo) | Con P-L04 B aprobada incluye `tags` salvo que se desactive (CA-L04.1). |
| M1 CA-19.4/19.6 (bloqueo y doble clic) | Se extienden al lote (CA-L10.7, CA-L10.9). |
| M1 CA-20.10 ("elimínala desde Proxmox") | Sustituido por la oferta de rollback (CA-L18.13); sigue sin borrarse nada automáticamente. |
| M1 CA-20.8 (cierre con tarea en curso) | Se extiende al lote (RF-L23). |
| M1 V-14 (espacio por MV) | Se conserva; V-L09/V-L10 son autoritativas para el lote (sección 4). |
| M1 RF-26 (versión forzada, "Podría") | Se vuelve necesaria para la simulación (CA-L11.6, CA-L11.7). |
| M1 §6 permisos (rol de 10 privilegios) | Sin cambios al crear; el borrado queda por verificar (sección 6, LAB-L05). |
| M1 §7 (errores) | Se amplía con E-L01..E-L23. |

---

## 13. Pendientes de verificación (resumen)

1. Privilegios y parámetros del `DELETE` (LAB-L05); no consta en F1.
2. Formato y privilegio de `tags` (LAB-L06).
3. Visibilidad real de `/cluster/resources` con el rol mínimo (LAB-L11).
4. Nombres duplicados en Proxmox (LAB-L07).
5. Volúmenes huérfanos tras una creación fallida (LAB-L04).
6. Seguridad entre hilos del transporte con concurrencia > 1 (revisión del orquestador/`revisor-qa`
   antes de implementar RF-L12).
7. Todas las constantes marcadas "propuesto" se confirman con P-L01, P-L05, P-L07, P-L09.
