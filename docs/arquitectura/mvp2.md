# Arquitectura del MVP 2 — Lotes (ProxLaunch)

Versión 1.1 (2026-11-13) · Autor: orquestador · Estado: diseño original + diferencias del
código final (sección 11)

> **Nota de actualización.** Este documento recoge el diseño previo a la implementación. Donde el
> código final difiere, manda el código y lo anotado en la **sección 11** (D-21, sondeo de
> nodo, `puede_enviar`, `Libro` creado por la interfaz, reconciliación con `lock: create`,
> cliente de solo lectura, informe saneado, reintento de GET). Los hechos del laboratorio
> están en `docs/investigacion/f1-api-proxmox.md` §8.

Fuentes: `docs/requisitos/mvp2.md` (RF-L, CA-L, V-L, E-L, INV-L), `docs/decisiones.md`
(D-20), `docs/arquitectura/mvp1.md` (capas, servicios, trabajadores). Se mantiene la
separación de M1: **núcleo sin Qt** (devuelve códigos) e **interfaz PySide6** (traduce).

## 1. Hechos verificados que condicionan el diseño (PVE 9.2.26, laboratorio)

- `DELETE /nodes/{n}/qemu/{vmid}` exige solo `VM.Allocate` en `/vms/{vmid}`
  (`PVE/API2/Qemu.pm`, `destroy_vm`): **el rol de 10 privilegios no cambia**. Es
  `protected`; rechaza MVs con `protection=1`; `skiplock` solo para root; `purge` y
  `destroy-unreferenced-disks` son opcionales.
- `tags` al crear exige `VM.Config.Options` (en el rol) y la política
  `user-tag-access` del datacenter. Por defecto es `free` (cualquier etiqueta). Si un
  sitio la restringe, poner etiquetas nuevas exige `Sys.Modify` en `/` → 403
  "Sys.Modify for modifying tag" (`PVE/GuestHelpers.pm:341-359`). El diseño trata ese 403
  como E-L15 y ofrece crear el lote sin etiquetas (decisión explícita del usuario).
- ~~Pendientes de laboratorio~~ **Resueltos en F4** (ver `f1-api-proxmox.md` §8): LAB-L05
  (los parámetros del DELETE van en la consulta; en el cuerpo da 501), LAB-L06 (separadores y
  normalización de etiquetas), LAB-L07 (nombres duplicados permitidos), LAB-L11 (visibilidad
  de `/cluster/resources`).

## 2. Módulos nuevos y cambios

```
src/proxlaunch/nucleo/
  lote/                      (NUEVO, sin Qt)
    constantes.py            MAX_LOTE=100, MAX_SALTO_VMID=1000, FACTOR_THIN_MAX=3, ...
    modelos.py               DefinicionLote, PatronNombres, Destino, Plan, ElementoPlan,
                             Problema, EstadoMV, EntradaLibro, ResultadoRollback, ...
    nombres.py               generar_nombres(), validar_patron()        (puras)
    reparto.py               nodos_elegibles(), repartir()              (puras)
    presupuesto.py           uso_por_clave(), evaluar_espacio(), capacidad_maxima() (puras)
    planificador.py          Planificador: reserva de VMIDs (E/S) + construir_plan() (pura)
    politica_pausa.py        PoliticaPausa: errores globales y repetidos  (pura)
    libro.py                 Libro: registro del lote, seguro entre hilos
    motor.py                 MotorLote: ejecución con colas por nodo, pausa, cancelación
    reconciliacion.py        reconciliar_incierta(): existe_vm a t=0/+5/+15 s
    rollback.py              ServicioRollback: elegibles(), deshacer()
    simulacion.py            simular(): planificar + construir peticiones, solo lectura
    informe.py               construir_informe() → InformeLote (datos, sin textos)
  api/cliente.py             + vmid_libre(), eliminar_vm(), estado_actual_vm(), vms_visibles()
  api/solo_lectura.py        (NUEVO) TransporteSoloLectura: guardián de INV-L5
  modelos/vm.py              ConfiguracionVM + etiquetas: tuple[str, ...] = ()
  constructor_peticion.py    añade tags=";".join(etiquetas) si hay y la versión lo admite
  capacidades.py             + admite_etiquetas(version)
  errores.py                 + códigos E-L (sección 6)
  validacion.py              + V-L02..V-L04 vía lote/nombres; etiqueta con patrón PVE

src/proxlaunch/interfaz/
  vistas/bloque_lote.py      (NUEVO) cantidad, patrón, vista previa, destino, algoritmo, etiquetas
  vistas/resumen_lote.py     (NUEVO) tabla del plan (modelo), totales, avisos, casilla thin,
                             Simular / Crear N / Reducir a N / Copiar resumen
  vistas/progreso_lote.py    (NUEVO) tabla del libro (modelo), barra global, filtro, Cancelar,
                             Comprobar dudosas, Deshacer…, Reintentar pendientes, Informe
  modelos_tabla.py           (NUEVO) ModeloPlan, ModeloLibro (QAbstractTableModel)
  dialogos/deshacer.py       (NUEVO) lista con casillas, advertencia, foco en Cancelar
  dialogos/pausa_lote.py     (NUEVO) pausa por error global, repetido o conexión
  informe_lote.py            (NUEVO) texto del informe (una sola función) + guardar .txt
  trabajadores.py            + lanzar_planificacion/simulacion/lote/rollback
  ventana_principal.py       integra el bloque Lote y las vistas; cierre con lote (RF-L23)
  textos.py, ayuda.py        textos E-L, V-L, estados y ayudas del lote
```

## 3. Modelos del lote (`nucleo/lote/modelos.py`)

```python
class ModoDestino(StrEnum): AUTOMATICO, UN_NODO, NODOS_ELEGIDOS
class Algoritmo(StrEnum): EQUILIBRADO, POR_TURNOS
class PoliticaThin(StrEnum): BLOQUEAR, ADVERTIR, CONFIRMAR_CON_TOPE   # D-20: la 3.ª

@dataclass(frozen=True)
class PatronNombres: prefijo: str; separador: str = "-"; inicio: int = 1; relleno: int = 2

@dataclass(frozen=True)
class Destino: modo: ModoDestino; nodos: tuple[str, ...] = (); algoritmo: Algoritmo = EQUILIBRADO

@dataclass(frozen=True)
class DefinicionLote:
    plantilla: ConfiguracionVM        # vmid/nombre/nodo se ignoran: los fija el plan
    cantidad: int
    patron: PatronNombres
    destino: Destino
    vmid_inicial: int | None = None   # None = /cluster/nextid
    etiquetar: bool = True            # D-20 (3)
    politica_thin: PoliticaThin = PoliticaThin.CONFIRMAR_CON_TOPE

class Severidad(StrEnum): ERROR, AVISO, AVISO_CONFIRMABLE
@dataclass(frozen=True)
class Problema: regla: str; severidad: Severidad; campo: str | None; params: dict[str, str]

@dataclass(frozen=True)
class ElementoPlan: indice: int; nombre: str; vmid: int; nodo: str; cfg: ConfiguracionVM

@dataclass(frozen=True)
class ClavePresupuesto: ambito: str; storage: str   # ambito = nodo o "*compartido*"

@dataclass(frozen=True)
class Plan:
    id_lote: str                       # 8 hex aleatorios (CA-L20.3)
    definicion: DefinicionLote
    elementos: tuple[ElementoPlan, ...]
    vmids_saltados: tuple[int, ...]
    reparto: dict[str, tuple[int, str]] # nodo → (cantidad, motivo)
    uso: dict[ClavePresupuesto, tuple[int, int, bool]]  # pedido_bytes, libre_bytes, thin
    problemas: tuple[Problema, ...]
    capacidad_maxima: int | None       # para "Reducir a N" (CA-L07.7)
    generado_en: float                 # reloj inyectado (V-L14)
    version_validacion: tuple[int, int]  # forzada o detectada (CA-L11.6)
    bloqueado: bool                    # hay algún ERROR
    requiere_confirmacion_thin: bool

class EstadoMV(StrEnum):
    PENDIENTE, VALIDANDO, ENVIANDO, CREANDO, COMPROBANDO,         # en curso
    OK, CON_AVISOS, ERROR, PARCIAL, TIEMPO_AGOTADO, CONEXION_PERDIDA,  # = Desenlace M1
    NO_ENVIADA, NO_CREADA_SEGURA, EXISTE_SIN_CONFIRMAR_PROPIEDAD   # nuevos

@dataclass(frozen=True)
class EntradaLibro:                    # instantánea inmutable
    elemento: ElementoPlan; estado: EstadoMV; upid: str | None
    error: ErrorProxLaunch | None; motivo_no_enviada: str | None
    post_intentado: bool               # INV-L1: True en cuanto se llama al POST
    t_inicio: float | None; t_fin: float | None; log_tarea: tuple[str, ...]
```

## 4. Flujo y responsabilidades

### 4.1 Planificación (RF-L01..L09, L14 vigencia)
`Planificador(sesion, reloj).planificar(definicion, inv, *, version_forzada=None) -> Plan`

1. `validar_definicion()` (V-L01..V-L04, V-L07, V-L13): pura; errores → Plan bloqueado sin E/S.
2. `nombres = generar_nombres(patron, cantidad)` (relleno efectivo, CA-L02.2).
3. **Reserva de VMIDs** (`reservar_vmids`): desde `vmid_inicial` o `inv.proximo_vmid`,
   ventana deslizante con `ThreadPoolExecutor(MAX_CONSULTAS_SIMULTANEAS=8)` sobre
   `cliente.vmid_libre(n)`; conserva el orden; ocupados → `vmids_saltados`; ventana de
   `MAX_SALTO_VMID` agotada → E-L02; error de red → `ErrorProxLaunch` (sin plan parcial).
4. `asignacion = repartir(definicion, inv, cantidad)` (pura, CA-L05.2 Equilibrado
   determinista; Por turnos; elegibilidad RF-L06; memoria `None` → -1 con aviso).
5. `uso = uso_por_clave(...)`; `evaluar_espacio(uso, politica)` (V-L09/V-L10, efidisk
   `TAM_EFIDISK_MIB`); `capacidad_maxima()` por búsqueda binaria sobre `repartir` +
   `evaluar_espacio` (pura).
6. Validación M1 por elemento (`validar_vm(cfg_i, inv, version)`): V-01..V-23 en su nodo.
7. Avisos V-L06 (nombres existentes, `cliente.vms_visibles()`, aviso calificado), V-L12,
   V-L15, V-L16. Resultado: `Plan` inmutable.

Funciones puras 2, 4, 5 y 6 se agrupan en `construir_plan(definicion, inv, vmids, ...)`
para pruebas deterministas (RNF-L09) y para la equivalencia simulación/real (CA-L11.3).

### 4.2 Simulación (RF-L11, INV-L5)
`simular(sesion_ro, definicion, inv, version_forzada) -> ResultadoSimulacion(plan,
peticiones: dict[vmid, dict[str,str]])`. Usa **el mismo** `Planificador` sobre una sesión
cuyo transporte es `TransporteSoloLectura(transporte_real)`: cualquier método distinto de
GET/HEAD lanza `ErrorProxLaunch(ESCRITURA_EN_SIMULACION)` sin llegar a la red. Las
peticiones se obtienen con `construir_parametros(cfg_i, inv)` (sin enviarlas).

### 4.3 Ejecución (RF-L12..L17, INV-L1..L4)
`MotorLote(sesion, reloj, *, fabrica_creacion=ServicioCreacion,
max_nodos=4, umbral_pausa=3)`

- `ejecutar(plan, observador: Callable[[EntradaLibro], None], control: ControlLote) -> Libro`
- `ControlLote`: `cancelar()`, `dejar_de_esperar()`, `pausado` (Event), `reanudar()`,
  `motivo_pausa`. Seguro entre hilos.
- Colas: una por nodo en el orden del plan. `ThreadPoolExecutor(max_workers=min(4, k))`;
  cada trabajador toma **un nodo** y procesa su cola de forma secuencial (≤ 1 creación en
  curso por nodo, CA-L12.3). Peticiones simultáneas ≤ 4 creaciones + sondeos ≤ 8
  (CA-L12.4).
- Por elemento: comprobar cancelación/pausa → `libro.marcar_post_intentado(vmid)` →
  `ServicioCreacion.crear(cfg_i, inv, al_cambiar_etapa, cancelado, al_enviar=upid→libro)`.
  **Nunca** se llama dos veces a `crear` para un mismo `ElementoPlan` (INV-L1): el motor
  no reintenta; `Libro` lanza `AssertionError` si se intenta (defensa en profundidad).
- `ResultadoCreacion` → `EstadoMV`: igual al `Desenlace`; `CONEXION_PERDIDA` **sin UPID**
  → `reconciliar_incierta()` (existe_vm a 0/+5/+15 s con `reloj.dormir`, cancelable):
  existe con etiqueta del lote (o sin etiquetas activadas) → `OK` + aviso; existe sin la
  etiqueta → `EXISTE_SIN_CONFIRMAR_PROPIEDAD`; no existe ×3 → `NO_CREADA_SEGURA`;
  `None` → sigue `CONEXION_PERDIDA` (E-L06).
- `PoliticaPausa.registrar(error) -> MotivoPausa | None`: globales
  (`SESION_EXPIRADA`, `CREDENCIALES_INVALIDAS`, `HUELLA_CAMBIADA`, `PERMISO_INSUFICIENTE`
  sobre `VM.Allocate`, ningún nodo en línea, E-L15 etiqueta rechazada) → pausa inmediata;
  mismo `CodigoError` en 3 desenlaces consecutivos (orden de finalización) → pausa
  (E-L07). "Continuar" desactiva esa causa para el lote (CA-L14.4).
  `NODO_NO_DISPONIBLE` → solo se vacía la cola de ese nodo (`NO_ENVIADA`, CA-L14.5).
- Pérdida sostenida (> 60 s) en un sondeo → el motor pausa el envío (E-L09); "Comprobar y
  continuar" llama `comprobar_dudosas()` y luego reanuda solo `PENDIENTE` (CA-L17.3).
- `comprobar_dudosas(libro)`: con UPID → `comprobar_ahora`; sin UPID → `existe_vm`. Solo
  GET (CA-L15.7).
- Excepción inesperada en un elemento → `CONEXION_PERDIDA` si `post_intentado`, `ERROR` si
  no; el lote sigue (CA-L12.8).
- `Libro`: `threading.Lock`; `instantanea() -> tuple[EntradaLibro, ...]`; contadores; es la
  única fuente para rollback e informe (CA-L12.10).

### 4.4 Rollback (RF-L18, D-20 (1))
`ServicioRollback(sesion, reloj)`:
- `elegibles(libro, id_lote, servidor_actual) -> list[Candidato(entrada, elegible, motivo)]`
  (CA-L18.1/18.2; mismo perfil y sesión).
- `deshacer(candidatos, observador, control) -> list[ResultadoRollback]`: por nodo, ≤ 1
  DELETE a la vez; antes de cada DELETE: `config_vm` (existe, etiqueta `lote-<id>` si el
  lote etiquetó, sin `protection`, sin `lock`) y `estado_actual_vm` (no `running`);
  `cliente.eliminar_vm(nodo, vmid)` → UPID → sondeo con la misma máquina de estados;
  596/abortado → `config_vm` decide `ELIMINADA` / reintento manual / `INCIERTA` (E-L22).
  403 → pausa global (CA-L18.9). Nunca toca MVs fuera del libro (INV-L4).

### 4.5 Informe (RF-L19, RF-L20)
`construir_informe(plan, libro, resultados_rollback, metadatos) -> InformeLote` (datos con
códigos). La interfaz lo convierte en texto con **una** función `texto_informe(informe)`
(`interfaz/informe_lote.py`) usada por "Copiar" y "Guardar" (CA-L19.8). Sin host, IP ni
usuario (CA-L19.3). Al cerrar con lote en curso se guarda en
`platformdirs.user_data_dir/informes/` (RF-L23).

## 5. Cliente de la API (nuevos métodos)

| Método | Petición | Notas |
|---|---|---|
| `vmid_libre(vmid) -> bool` | `GET /cluster/nextid?vmid=` | 400 con `errors.vmid` → False; otros errores se propagan |
| `vms_visibles() -> list[VMRemota]` | `GET /cluster/resources?type=vm` | solo para el aviso V-L06 (LAB-L11) |
| `estado_actual_vm(nodo, vmid) -> dict` | `GET /nodes/{n}/qemu/{vmid}/status/current` | `VM.Audit`; `status`, `lock` |
| `eliminar_vm(nodo, vmid) -> str` | `DELETE /nodes/{n}/qemu/{vmid}` con `params={"destroy-unreferenced-disks": 0}` **en la consulta**, sin `purge` (**D-21**; el diseño decía `=1`) | UPID; método no seguro → sin failover (envío incierto si falla tras enviar) |
| `estado_nodo(nodo) -> dict` (**nuevo**) | `GET /nodes/{n}/status` | Sonda barata de que el nodo responde (ver 11.1) |
| `solo_lectura() -> ClienteProxmox` (**nuevo**) | — | Cliente para la simulación (ver 11.6) |

`TransporteSoloLectura`: implementa `Transporte`; delega GET/HEAD y rechaza el resto.

## 6. Códigos de error nuevos (`CodigoError`)

`LOTE_SIN_NODO_APTO`, `LOTE_VMIDS_INSUFICIENTES`, `LOTE_SIN_ESPACIO`, `LOTE_ENVIO_INCIERTO`,
`LOTE_EXISTENCIA_INDETERMINADA`, `LOTE_PAUSADO_REPETIDO`, `LOTE_PAUSADO_CONEXION`,
`LOTE_NO_ENVIADA`, `LOTE_PLAN_CAMBIO`, `LOTE_EN_CURSO`, `LOTE_CANTIDAD_INVALIDA`,
`VERSION_FORZADA_MAYOR`, `ETIQUETA_RECHAZADA`, `ROLLBACK_FALLO`, `ROLLBACK_NO_PROPIA`,
`ROLLBACK_ENCENDIDA`, `ROLLBACK_BLOQUEADA`, `ROLLBACK_DISCOS_SUELTOS`,
`ROLLBACK_INCIERTO`, `ESCRITURA_EN_SIMULACION`. Reutilizados: `VMID_OCUPADO`,
`SERVIDOR_NO_RESPONDE`, `PERMISO_INSUFICIENTE`. El traductor reconoce el 403
"Sys.Modify for modifying tag" → `ETIQUETA_RECHAZADA`.

## 7. Interfaz

- **Formulario:** el formulario de M1 es la plantilla; el bloque "Lote" va arriba.
  Cantidad = 1 → flujo de M1 (botón "Crear máquina", sin resumen obligatorio), pero
  ejecutado por `MotorLote` (un libro de 1 entrada) para tener etiqueta y "Deshacer"
  (CA-L18.13); la vista de progreso de M1 se alimenta de esa entrada.
- **Cantidad > 1:** "Ver resumen" → `ResumenLote` (planificación en hilo) → "Simular" o
  "Crear N máquinas" (doble confirmación si N > 10, foco en Cancelar) → `ProgresoLote`.
- **Coalescencia (CA-L13.5):** el motor llama al observador desde hilos; el trabajador
  emite una señal ligera que solo marca "sucio"; un `QTimer` de 100 ms en el hilo de la
  interfaz lee `libro.instantanea()` y refresca `ModeloLibro` (≤ 10 refrescos/s).
- **Pausa:** `DialogoPausaLote` con las acciones de E-L07/E-L09/globales.
- **Deshacer:** `DialogoDeshacer` (casillas, "Solo incompletas" / "Todo el lote",
  advertencia, botón con el número, foco en Cancelar).
- Accesibilidad (RNF-L04): estado con texto + símbolo; `accessibleName`; navegación por
  teclado en tablas.

## 8. Concurrencia y seguridad entre hilos

- `ClienteProxmox`/`TransporteHttp` ya se usan en paralelo en el descubrimiento (8 hilos):
  `_activo` es una asignación atómica; la renovación del ticket tiene cerrojo con nueva
  comprobación; el pool de urllib3 es seguro entre hilos. F7 no halló problemas. Se
  amplía el `pool_maxsize` del adaptador a ≥ 8 para evitar avisos de pool lleno.
- Una instancia de `ServicioCreacion` por trabajador de nodo (contexto por llamada ya
  separado en F7).
- El `Libro` es el único estado mutable compartido; la interfaz solo lee instantáneas.

## 9. Fases de implementación

| Fase | Responsable | Entregable |
|---|---|---|
| F3a Núcleo: modelos, nombres, reparto, presupuesto, planificador, simulación, cliente, errores, etiquetas | `implementador` A | `nucleo/lote/` (parte pura + planificación) |
| F3b Núcleo: libro, motor, política de pausa, reconciliación, rollback, informe | `implementador` A (tras F3a) o B en paralelo con interfaces de §3 | `nucleo/lote/` (ejecución) |
| F3c Interfaz: bloque, resumen, progreso, diálogos, informe, integración | `implementador` C (en paralelo, contra §3–§7) | `interfaz/` |
| F4 Pruebas unitarias (puras, inyección de fallos, contadores de métodos, rendimiento) e interfaz; LAB-L01..L13 | `probador` | `tests/nucleo/lote/`, `tests/interfaz/`, `tests/integracion/` |
| F5 Revisión | `revisor-qa` + `auditor-seguridad` | informes |
| F6 Documentación | `documentador` | guía (lotes, simulación, deshacer) |

## 10. Riesgos de diseño

1. **INV-L1** es la propiedad crítica: se garantiza por construcción (cada elemento se
   procesa una vez) y por pruebas de inyección de fallos en todos los puntos (CA-L12.1).
2. Etiquetas restringidas en algunos sitios → la primera MV falla con 403 y el lote se
   pausa (error global) ofreciendo continuar sin etiquetas; el rollback queda limitado a
   MVs con UPID propio en el libro.
3. Clúster multinodo solo con mocks (laboratorio de un nodo).
4. N=1 por el motor del lote: hay que conservar el comportamiento de M1 (CA-L04.1) —
   prueba de equivalencia de peticiones y de desenlaces.

## 11. Diferencias entre el diseño y el código final

Cambios surgidos de las pruebas de laboratorio (F4) y de la revisión QA y la auditoría de
seguridad (F5). Prevalecen sobre lo descrito en las secciones 3 a 8.

### 11.1 Sondeo de nodo antes de enviar (`motor.py`, §4.3)
El diseño solo vaciaba la cola de un nodo al recibir `NODO_NO_DISPONIBLE` de un POST. Ahora
`MotorLote._nodo_caido` sondea el nodo con `GET /nodes/{n}/status` (`cliente.estado_nodo`):
antes de la **primera** MV de cada nodo y tras cada fallo dudoso o de conexión en él. Solo un
595/596 (`NODO_NO_DISPONIBLE`) cuenta como nodo caído; cualquier otro error (por ejemplo falta
de `Sys.Audit`) no prueba nada y se sigue adelante. Las MV de un nodo caído quedan
`NO_ENVIADA` (`MotivoNoEnviada.NODO_CAIDO`).

### 11.2 `puede_enviar` antes del POST (§4.3)
`ServicioCreacion.crear` recibe el callback `puede_enviar`. Es la **última puerta antes del
POST**: si entre el inicio de la validación y el envío llegó una cancelación (`CANCELADO`) o
una pausa (`PAUSA`), la MV no se envía y queda `NO_ENVIADA` con ese motivo. Una suspensión
(`suspender()`, usada al reconectar o al «Comprobar y continuar») no la bloquea: deja
terminar lo ya iniciado. Además de `Libro`, el propio motor lleva un conjunto `intentados` y
lanza `AssertionError` ante un segundo intento del mismo VMID (INV-L1).

### 11.3 El `Libro` lo crea la interfaz
El diseño decía `ejecutar(...) -> Libro`. Ahora la interfaz crea `Libro(plan)` **antes** de
lanzar el motor y se lo pasa (`ejecutar(..., libro=libro)`), de modo que existe aunque el
motor falle y «Deshacer» y «Comprobar» siguen disponibles sobre lo ya creado. El motor
devuelve el mismo objeto. Con el mismo libro se reanuda (`continuar_lote`), se comprueban las
dudosas (`comprobar_dudosas_lote`) y se deshace (`deshacer_lotes`, que agrupa varios lotes
de la sesión con su id y su política de etiquetas).

### 11.4 Reconciliación con `lock: create` (`reconciliacion.py`, §4.3)
Tras el POST, la configuración de la MV solo contiene `lock: create` durante ~250 ms (hecho
de laboratorio). Leer entonces las etiquetas no demuestra nada. Por eso `reconciliar_incierta`
**no decide** la propiedad mientras `config_en_creacion` sea verdadero: relee en la siguiente
comprobación (t = 0, +5 s, +15 s) y, si tras todas sigue en creación, deja la MV
`CONEXION_PERDIDA` con `LOTE_EXISTENCIA_INDETERMINADA` (nunca `OK` sin la etiqueta propia).
Si `etiquetar` es falso, existe y la configuración ya no está en creación → `OK` con el aviso
`creada_tras_comprobar`. Si no se puede leer la configuración con etiquetas activas →
`EXISTE_SIN_CONFIRMAR_PROPIEDAD` (no elegible).

### 11.5 Deshacer sin discos sueltos (D-21, §4.4 y §5)
`eliminar_vm` envía `destroy-unreferenced-disks=0` y sin `purge`: borra la MV y los discos
que su configuración referencia, y nunca un volumen suelto. Antes de cada DELETE, el
rollback lee `config_vm` (existe; con etiquetas, lleva la del lote; sin etiquetas, el
**nombre** es el del plan; sin `protection` ni `lock`) y `estado_actual_vm` (no `running`,
sin `lock`). El 403 detiene el rollback tras el primer caso. `ROLLBACK_DISCOS_SUELTOS`
(E-L21) existe en `CodigoError` y en `textos.py`, pero el rollback **no lo emite** hoy:
D-21 prevé el aviso, y queda pendiente de implementar o de retirar de la decisión.

### 11.6 Cliente de solo lectura que renueva el ticket y sesión cerrada que no renueva
- `ClienteProxmox.solo_lectura()` devuelve un cliente cuyo transporte es
  `TransporteSoloLectura(transporte_real)` (rechaza todo lo que no sea GET/HEAD, INV-L5) pero
  que **renueva el ticket con el transporte real**: es el único POST permitido
  (`/access/ticket`, lo hace el autenticador). Sin esto, la simulación fallaría al intentar
  renovar un ticket por caducar.
  Su `cerrar()` no hace nada: no suelta la credencial compartida.
- Todos los clientes derivados comparten un `threading.Event` `_cerrada`. Tras `cerrar()`,
  `_llamar` lanza `SESION_EXPIRADA` **sin renovar**: ninguna petición tardía de otro hilo
  pide un ticket nuevo con una credencial ya olvidada (hallazgo B1 de F5). Por la misma razón,
  `closeEvent` no cierra la sesión si algún hilo sigue vivo tras la espera de 3 s.

### 11.7 Informe saneado con `ocultar` (§4.5)
`construir_informe(..., ocultar=[...])` recibe los valores literales a quitar (hosts del
perfil, host activo, usuario del perfil y usuario efectivo). Todo texto libre del informe
(parámetros y detalle técnico de errores, registro de tareas, avisos del plan y nombre del
perfil) pasa por `_sanear_texto`: quita los UPID (deja el campo del usuario como «…»), los
`usuario@realm[!token]`, los valores de `ocultar` (también codificados como URL y sin
distinguir mayúsculas) y las IPv4 e IPv6. Se descartan las claves de parámetros `host`, `ip`,
`usuario`, `user`, `servidor`, `direccion` y `url`. La interfaz construye los metadatos
(`_metadatos_informe`) solo con el nombre del perfil, la versión y la topología.

### 11.8 Reintento único de GET (`transporte.py`)
Pveproxy cierra las conexiones inactivas (~5 s) y una conexión reutilizada puede fallar al
usarla. Una **lectura** (GET/HEAD) que falla por desconexión de una conexión reutilizada se
reintenta **una vez** en el mismo host. No se reintenta una conexión rechazada, un timeout
de conexión ni un error SSL, y **nunca** se reintenta un método no seguro (POST, DELETE): su
fallo sigue siendo envío incierto (INV-L1).

### 11.9 Otras diferencias menores
- **Hechos de laboratorio incorporados al diseño:** los parámetros del DELETE van en la
  consulta (en el cuerpo da 501); el POST con etiquetas bajo `user-tag-access` restringido
  responde 200 y la tarea falla con 403 (E-L15 se detecta al terminar la tarea, no en el
  POST); `TAM_EFIDISK_MIB = 4` confirmado.
- **Reintento (RF-L21):** `armar_reintento` conserva nombres y VMIDs (no salta ocupados: un
  VMID ocupado es un error del plan), genera un id de lote nuevo y admite un nodo de
  destino único.
- **Confirmación doble:** se aplica cuando N **>** `UMBRAL_CONFIRMACION_DOBLE` (10), es decir, desde 11.
- **Una máquina (N = 1):** pasa por el motor con un libro de una entrada (`modo_uno`), con
  etiquetas y «Deshacer», y se muestra con el panel de progreso de M1. No tiene resumen ni
  simulación.
- **Menú:** *Archivo > Ver el último lote* reabre el progreso del último lote.
