# Arquitectura del MVP 3 — Perfiles de máquina, lotes guardados e importación CSV (ProxLaunch)

Versión 0.1 (2026-11-14) · Autor: orquestador (borrador) · Estado: borrador para revisión antes de
implementar

Fuentes: `docs/requisitos/mvp3.md` (RF-P, RF-X, RF-G, RF-C, RNF-M, V-M, E-M, INV-M, LAB-M3; §9
formatos, §14 enmiendas, §15 riesgos), `docs/decisiones.md` (D-20, D-21 y **D-22**: lote por filas),
`docs/arquitectura/mvp1.md` y `mvp2.md` (incluida su §11: manda el código final) y el código de
`src/proxlaunch` a 2026-11-14 (commit `5d069ad`). Se mantiene la separación de M1/M2: **núcleo sin
Qt** que devuelve códigos e **interfaz PySide6** que traduce.

> Regla de lectura: las firmas exactas están en el **Anexo A**; el texto de cada sección explica
> responsabilidades y comportamiento. Si una firma del anexo y el texto difieren, manda el anexo y
> se corrige el texto.

## 1. Hechos del código que condicionan el diseño

1. `motor.py` **no lee la plantilla**: consume `Plan.elementos` (cada `ElementoPlan` lleva su
   `cfg`) y solo usa `plan.definicion.etiquetar` (líneas 485 y 590). `libro.py`, `rollback.py`,
   `reconciliacion.py` y `simulacion.py` tampoco la leen. → El lote por filas puede ejecutarse sin
   tocar el motor si `DefinicionLote` conserva `etiquetar`.
2. La plantilla única se usa en: `planificador.py` (`usa_nombre_de_plantilla`,
   `_etiquetas_del_lote`, `construir_plan`: nombres, copia de la plantilla, `uso_de_nodos`),
   `reparto.py` (`repartir`: elegibilidad, pedido y memoria de **una** plantilla),
   `presupuesto.py` (`uso_de_nodos`, `capacidad_maxima`) e `informe.py`
   (`plantilla=plan.definicion.plantilla`). En la interfaz: `ventana_principal._reintentar_pendientes`
   (`replace(definicion, cantidad=…)`), `resumen_lote.py` (`plan.definicion.cantidad`) e
   `informe_lote._lineas_plantilla`.
3. `trabajadores.armar_reintento` ya trabaja **por elemento** (copia `e.cfg` de cada uno): sirve
   tal cual para un lote por filas (CA-C08.10).
4. `ConfiguracionVM` es un `dataclass` **mutable**; `desde_dict` no valida tipos y lanza
   `KeyError` ante claves ausentes (riesgo 2 de los requisitos). No se usará con datos de terceros.
5. `AlmacenJson.leer` renombra a `.danado-<sello>` los archivos corruptos y usa `json.loads`
   (acepta `NaN`/`Infinity` y claves repetidas). `AlmacenJson.escribir` ya es atómica
   (`mkstemp` → 0600, `fsync`, `os.replace`) y crea la carpeta con `crear_carpeta_privada` (0700).
6. `validar_vm(cfg, inv, caps)` mezcla reglas sin servidor (V-05..V-08, V-10..V-13, V-15, V-20,
   V-22..V-24) y con servidor (V-04, V-09, V-14, V-16, V-17). Sus códigos son estables.
7. `constructor_peticion.py` ya envía `machine=q35` con OVMF (`MAQUINA_OVMF`): el perfil de fábrica
   «Escritorio (hardware compatible)» no necesita campos nuevos en `ConfiguracionVM`.
8. `valores_defecto.py` ya tiene `storage_por_defecto` (mayor libre con `images`),
   `bridge_por_defecto` (`vmbr0` o el primero) y `configuracion_por_defecto` (base de CA-P02.4).
9. El formulario aplica una configuración completa con `aplicar_configuracion(cfg)` (cambia nombre,
   VMID y nodo); no existe un método que cambie **solo** el hardware.
10. `proxlaunch.__version__` vale hoy `"0.1.0"`: `app_version` de los archivos sale de ahí.

## 2. Módulos nuevos y cambios

```
src/proxlaunch/nucleo/
  errores.py                 + códigos E-M (sección 8)                                  [F3-0]
  validacion.py              + validar_sin_servidor() (capa 1, filtra validar_vm)        [F3-0]
  persistencia/rutas.py      + perfiles_maquina, directorio_datos, lotes                [F3a]
  archivos/                  (NUEVO) lectura y escritura seguras, comunes a todo el MVP 3
    constantes.py            límites y formatos (§6 de los requisitos; MAX_LOTE se importa de lote)
    lector.py                leer_archivo_limitado(): solo archivos regulares, ≤ límite+1 bytes
    json_estricto.py         cargar_json_estricto(): UTF-8 estricto, sin NaN/Infinity, sin claves
                             repetidas, profundidad ≤ 8
    esquema.py               LectorEsquema (tipos reales, rangos, longitudes, rutas de campo),
                             ErrorCampo, ErrorArchivo, AvisoArchivo, es_clave_credencial()
    texto.py                 texto_seguro() (V-M04), contiene_token() (V-M05), validar_nombre()
                             (V-M01 sin unicidad), nombre_archivo_seguro(), clave_comparacion()
    envoltura.py             formato/version_formato/app_version, cadena de migraciones (RF-X01)
    esquema_config.py        lista blanca y lector estricto de la configuración de hardware
                             (perfil: con pistas; lote: con storage/bridge reales)
    escritura.py             escribir_atomico() (temporal + fsync + os.replace, 0600)
    csv_seguro.py            ÚNICO escritor de CSV: sanear_celda(), texto_csv(), escribir_csv()
  perfiles_maquina/          (NUEVO) perfiles de MV                                     [F3a]
    modelos.py               ConfigPerfil, DiscoPerfil, RedPerfil, BallooningPerfil, PerfilMaquina
    fabrica.py               6 perfiles de fábrica de solo lectura (ids fabrica.*)
    validacion.py            V-M01..V-M03 y capa 1 de la configuración
    aplicar.py               aplicar_perfil() con resolución de pistas (RF-P05/P06),
                             config_desde_configuracion(), hardware_igual(), resumen_perfil()
    compatibilidad.py        evaluar_compatibilidad() (RF-P07) sobre validar_vm + Funcion
    formato.py               exportar/leer archivos proxlaunch.perfiles (RF-P08/P09)
    almacen.py               AlmacenPerfilesMaquina: perfiles_maquina.json (RF-P10, INV-M7/M8)
  lotes_guardados/           (NUEVO) lote guardado (RF-G)                               [F3a]
    modelos.py               LoteGuardado, ArchivoLote
    formato.py               lote_a_bytes(), leer_lote(), guardar_lote(), leer_archivo_lote()
    revalidacion.py          desajustes() y sustituir() para «Este lote no encaja» (RF-G04)
  csv_importacion/           (NUEVO) importación CSV (RF-C)                             [F3b]
    decodificacion.py        BOM UTF-8 → BOM UTF-16 → UTF-8 → Windows-1252; forzada en avanzado
    separador.py             detección de ; , \t y «sep=»
    lectura.py               leer_tabla(): RFC 4180, límites, numeración de filas como Excel
    columnas.py              tabla única de columnas y alias; resolver_columnas()
    unidades.py              memoria, disco, enteros, decimales con coma, enums
    interpretacion.py        interpretar(): capa 1 (+ capa 2 de vista previa si hay inventario),
                             filas_lote(): FilaCsv → FilaLote
    plantilla.py             plantilla descargable (RF-C10)
    errores_csv.py           CSV de filas con error (RF-C12)
  lote/                                                                                  
    modelos.py               + FilaLote; DefinicionLote.filas; Plan.filas_excedentes;
                             InformeLote.por_filas                                     [F3-0]
    filas.py                 (NUEVO) filas_efectivas() = camino único; validar_filas();
                             definicion_por_filas(); sin_filas(); reemplazar_fila();
                             definicion_para_reintento()                               [F3c]
    planificador.py          construir_plan sobre filas_efectivas; VMIDs fijos; excluir    [F3c]
    reparto.py               + repartir_filas() (nodo fijo por fila, elegibilidad por fila) [F3c]
    presupuesto.py           + uso_de_filas(), filas_que_exceden()                          [F3c]
    informe.py               InformeLote.por_filas                                          [F3c]
    motor.py, libro.py, rollback.py, reconciliacion.py, simulacion.py, politica_pausa.py:
                             SIN CAMBIOS (prueba de no regresión: diff vacío)

src/proxlaunch/interfaz/
  archivos_ui.py             (NUEVO) diálogos del sistema, filtros, carpeta inicial de la sesión [F4a]
  modelos_tabla_csv.py       (NUEVO) ModeloVistaPreviaCsv, ModeloPerfilesImportados          [F4a]
  dialogos/perfiles_maquina.py (NUEVO) «Administrar perfiles…» (lista, renombrar, duplicar,
                             eliminar, importar, exportar)                                    [F4a]
  dialogos/guardar_perfil.py (NUEVO) nombre, descripción, casilla de pistas                   [F4a]
  dialogos/importar_perfiles.py (NUEVO) revisión con casillas y conflictos (CA-P09.1..3)       [F4a]
  dialogos/guardar_lote.py   (NUEVO) nombre del lote + diálogo del sistema                    [F4a]
  dialogos/importar_csv.py   (NUEVO) asistente: archivo → vista previa → confirmar filas      [F4a]
  dialogos/lote_no_encaja.py (NUEVO) panel de desajustes con «Usar otro…»                     [F4a]
  vistas/selector_perfil.py  (NUEVO) selector «Perfil de máquina» + estado «(modificado)»     [F4b]
  vistas/lote_filas.py       (NUEVO) panel del lote por filas (tabla de solo lectura)         [F4b]
  vistas/formulario_vm.py    + aplicar_hardware(cfg) (sin tocar nombre, VMID ni nodo)          [F4b]
  vistas/tabla_discos.py, vistas/tabla_redes.py
                             muestran un storage/bridge inexistente como «x (no existe)» con
                             error, nunca lo sustituyen en silencio (CA-G04.3)                 [F4b]
  vistas/bloque_lote.py      + establecer_definicion(); modo «por filas» oculta cantidad/patrón [F4b]
  vistas/resumen_lote.py     columnas núcleos/memoria por fila; «Quitar las filas que no caben»
                             en lugar de «Reducir a N» en el lote por filas; «N de N+M filas» [F4b]
  modelos_tabla.py           ModeloPlan con columnas de hardware por fila                     [F4b]
  informe_lote.py            configuración por MV si por_filas; datos_maquinas() común a texto
                             y CSV; «Guardar informe como CSV…» (RF-C14)                       [F4b]
  trabajadores.py            + lectores de archivo e interpretación CSV en hilo               [F4b]
  ventana_principal.py       menú «Lote» y «Perfiles», flujos de §6, cambios sin guardar     [F4b]
  textos.py, ayuda.py        textos E-M, V-M, avisos y ayudas (CA-P11.3)                      [F4b]
```

## 3. Modelos

Todos los modelos nuevos son `@dataclass(frozen=True)`. Los campos de tipo `ConfiguracionVM`
(mutable, M1) **no se mutan nunca** una vez dentro de un modelo congelado: quien necesite cambiarlos
usa `copy.deepcopy` o `dataclasses.replace` (igual que `ElementoPlan.cfg` en M2).

### 3.1 Lote por filas (`nucleo/lote/modelos.py`)

```python
@dataclass(frozen=True)
class FilaLote:
    """Una MV de un lote por filas (D-22). El hardware y storage/bridge son los de ``cfg``;
    ``cfg.vmid``, ``cfg.nombre``, ``cfg.nodo`` y ``cfg.etiquetas`` se ignoran (los fija el plan)."""
    nombre: str
    cfg: ConfiguracionVM
    vmid: int | None = None     # explícito (CA-C08.3); None = siguiente libre
    nodo: str | None = None     # explícito (CA-C08.4); None = reparto automático
    origen: int | None = None   # nº de fila del CSV (Excel) o posición en el archivo; solo para mostrar

@dataclass(frozen=True)
class DefinicionLote:            # campos de M2 sin cambios, en el mismo orden
    plantilla: ConfiguracionVM   # homogéneo: la plantilla. Por filas: informativa (perfil base);
                                 # NINGÚN cálculo la lee (prueba con plantilla absurda, §13)
    cantidad: int                # por filas: == len(filas) (V-L01 si no)
    patron: PatronNombres        # por filas: PatronNombres(prefijo="") e ignorado
    destino: Destino = field(default_factory=Destino)  # por filas: siempre AUTOMATICO (V-L13)
    vmid_inicial: int | None = None
    etiquetar: bool = True
    politica_thin: PoliticaThin = PoliticaThin.CONFIRMAR_CON_TOPE
    filas: tuple[FilaLote, ...] = ()   # NUEVO: vacío = homogéneo; no vacío = por filas

    @property
    def es_por_filas(self) -> bool: return bool(self.filas)

@dataclass(frozen=True)
class Plan:                      # campos de M2 sin cambios
    ...
    filas_excedentes: tuple[int, ...] = ()  # NUEVO: índices que no caben (CA-C08.6), solo por filas

@dataclass(frozen=True)
class InformeLote:               # campos de M2 sin cambios
    ...
    por_filas: bool = False      # NUEVO: la interfaz muestra la configuración de cada MV (CA-C08.8)
```

**Por qué así (cambio mínimo y seguro):** se añade un campo con valor por defecto al final de tres
dataclasses; todo constructor existente (posicional o con nombre) sigue siendo válido, las pruebas
de M2 no cambian y el motor no se toca. La alternativa de hacer `plantilla` opcional obligaba a
cambiar el orden de campos y ~15 llamadas (§15, D-T1).

**Camino único:** `filas_efectivas(definicion) -> tuple[FilaLote, ...]` (en `lote/filas.py`)
convierte **cualquier** definición en filas: en homogéneo genera `cantidad` filas
`FilaLote(nombre_i, plantilla)` con los nombres de `generar_nombres` (o el de la plantilla si
`usa_nombre_de_plantilla`), sin VMID ni nodo fijos; en por filas devuelve `definicion.filas`.
Planificador, reparto, presupuesto e informe trabajan sobre filas; el homogéneo es el caso
particular «todas las filas comparten `cfg` y nada es fijo» (CA-C08.12).

`usa_nombre_de_plantilla(definicion)` devuelve **falso** si `es_por_filas` (si no, un lote por filas
de una fila tomaría el nombre de la plantilla).

### 3.2 Perfiles de máquina (`nucleo/perfiles_maquina/modelos.py`)

```python
class OrigenPerfil(StrEnum): FABRICA = "fabrica"; USUARIO = "usuario"
PREFIJO_FABRICA = "fabrica."
ID_PREDETERMINADO = "fabrica.servidor-pequeno"

@dataclass(frozen=True)
class DiscoPerfil:
    tamano_gib: int; bus: Bus = Bus.SCSI; formato: FormatoDisco = FormatoDisco.AUTO
    discard: bool = True; ssd: bool = True; iothread: bool = True
    storage_preferido: str | None = None          # pista (RF-P06)

@dataclass(frozen=True)
class RedPerfil:
    modelo: ModeloRed = ModeloRed.VIRTIO; vlan: int | None = None
    bridge_preferido: str | None = None           # pista

@dataclass(frozen=True)
class BallooningPerfil: activo: bool; minimo_mib: int

@dataclass(frozen=True)
class ConfigPerfil:               # lista blanca de la columna «Perfil de MV» (§2 de los requisitos)
    firmware: Firmware = Firmware.SEABIOS
    sockets: int = 1; cores: int = 2; tipo_cpu: str = "x86-64-v2-AES"
    memoria_mib: int = 2048; ballooning: BallooningPerfil | None = None
    con_disco: bool = True; discos: tuple[DiscoPerfil, ...] = ()
    storage_efi_preferido: str | None = None
    controlador_scsi: ControladorScsi = ControladorScsi.VIRTIO_SINGLE
    redes: tuple[RedPerfil, ...] = ()
    origen: OrigenSO = OrigenSO.DISCO_VACIO
    # Sin vmid, nombre de MV, nodo ni etiquetas: no existen como campos (CA-P01.1, CA-P06.8).

@dataclass(frozen=True)
class PerfilMaquina:
    id: str                       # uuid4().hex (usuario) o "fabrica.<clave>"
    nombre: str                   # fábrica: el traducido que pasa la interfaz (núcleo sin textos)
    descripcion: str
    origen: OrigenPerfil
    config: ConfigPerfil
```

Los perfiles de fábrica se construyen con `perfiles_fabrica(textos)`: el núcleo fija ids y hardware
(§8 de los requisitos) y la interfaz aporta `{id: (nombre, descripción)}` traducidos con `tr()`;
sin textos (pruebas sin Qt) el nombre es la clave (`servidor-pequeno`). Así todo el código trata
fábrica y usuario con el mismo tipo y la unicidad de V-M01 compara nombres visibles.

Almacén: `AlmacenPerfilesMaquina` (Anexo A) guarda solo los del usuario, en orden de creación, en
`Rutas.perfiles_maquina`. `EstadoAlmacen` informa `solo_lectura` (versión futura, INV-M8),
`hubo_corrupcion`/`copia_danada`/`error_lectura` (política de `AlmacenJson`, CA-P10.3, CA-P12.3) y
`descartados` (perfiles individuales inválidos, CA-P10.4).

### 3.3 Archivos (`nucleo/archivos/`)

```python
class MotivoCampo(StrEnum):
    REQUERIDO, TIPO, RANGO, LONGITUD, ENUM, TEXTO_NO_VALIDO, TOKEN, DEMASIADOS, DUPLICADO

@dataclass(frozen=True)
class ErrorCampo: ruta: str; motivo: MotivoCampo; params: dict[str, str]  # "discos[1].tamano_gib"

class ErrorArchivo(ErrorProxLaunch):      # E-M04 con la lista completa (CA-G03.3)
    errores: tuple[ErrorCampo, ...]       # params["campo"] = errores[0].ruta, params["n"] = total

class CodigoAvisoArchivo(StrEnum):
    CAMPOS_DESCONOCIDOS   # CA-X01.6: params n (nunca los valores)
    CREDENCIAL_IGNORADA   # E-M16 / CA-X04.2: params n
    MIGRADO               # CA-X01.3: params desde, hasta
    COLUMNA_NO_USADA      # CA-C03.3: params columna (el encabezado saneado y recortado)
    GIB_ASUMIDO, DECIMAL_COMA, GB_COMO_GIB   # CA-C05.6, una vez por columna y archivo

@dataclass(frozen=True)
class AvisoArchivo: codigo: CodigoAvisoArchivo; params: dict[str, str]

@dataclass(frozen=True)
class Envoltura:
    formato: str; version_original: int; contenido: dict[str, object]
    avisos: tuple[AvisoArchivo, ...]
```

### 3.4 Lotes guardados (`nucleo/lotes_guardados/modelos.py`)

```python
@dataclass(frozen=True)
class LoteGuardado:
    nombre: str                      # V-M01 sin unicidad
    definicion: DefinicionLote       # politica_thin NO se guarda: al leer, valor por defecto
    version_proxmox: str | None = None  # informativo (CA-G04.6); nunca host ni perfil

@dataclass(frozen=True)
class ArchivoLote:
    lote: LoteGuardado; version_original: int; avisos: tuple[AvisoArchivo, ...]
```

Al leer, la plantilla del homogéneo sale con `vmid=0`, `nombre=""`, `nodo=""` (M2 los ignora,
CA-G01.1), salvo el caso N=1 con prefijo vacío (`usa_nombre_de_plantilla`), en el que el archivo
lleva `nombre_maquina` y se restaura en `plantilla.nombre` (si no, se perdería el nombre). En por
filas, `plantilla` = copia de `filas[0].cfg` (informativa).

### 3.5 Importación CSV (`nucleo/csv_importacion/`)

```python
class Codificacion(StrEnum):
    UTF8_BOM = "utf-8-sig"; UTF16 = "utf-16"; UTF8 = "utf-8"
    WINDOWS_1252 = "cp1252"; ISO_8859_1 = "iso-8859-1"

@dataclass(frozen=True)
class OpcionesCsv: codificacion: Codificacion | None = None; separador: str | None = None

@dataclass(frozen=True)
class DeteccionSeparador:
    separador: str; ambiguo: bool; candidatos: tuple[str, ...]; linea_sep: bool  # «sep=;»

@dataclass(frozen=True)
class FilaCsv: numero: int; celdas: tuple[str, ...]   # numero como en Excel: encabezado = 1

@dataclass(frozen=True)
class TablaCsv:
    codificacion: Codificacion; deteccion: DeteccionSeparador
    encabezado: tuple[str, ...]; filas: tuple[FilaCsv, ...]   # sin filas vacías

@dataclass(frozen=True)
class DefColumna:
    canonica: str; alias: tuple[str, ...]; obligatoria: bool = False; avanzada: bool = False

@dataclass(frozen=True)
class MapaColumnas:
    posiciones: dict[str, int]          # canónica → índice de columna
    encabezados: dict[str, str]         # canónica → texto del encabezado (para mensajes)
    ignoradas: tuple[int, ...]          # desconocidas (aviso una vez)
    credenciales: tuple[int, ...]       # parecen credencial: nunca se leen ni se exportan

class EstadoFila(StrEnum): CORRECTA = "correcta"; CON_AVISO = "con_aviso"; CON_ERROR = "con_error"

@dataclass(frozen=True)
class ProblemaCelda:
    fila: int; columna: str | None      # encabezado tal como está en el archivo
    regla: str                          # "V-05", "V-M08", "E-M11.no_numero"…
    severidad: Severidad                # la de nucleo.validacion (ERROR/AVISO)
    params: dict[str, str]
    valor: str                          # recortado a 40, sin control ni bidi (CA-C05.1)

@dataclass(frozen=True)
class FilaInterpretada:
    numero: int; nombre: str; perfil: str | None; vmid: int | None; nodo: str | None
    cfg: ConfiguracionVM | None         # None si un error impide construirla
    problemas: tuple[ProblemaCelda, ...]   # ordenados por columna; ≤ 5 + "y N más" (CA-C05.7)
    problemas_omitidos: int
    originales: dict[str, str]          # canónica → texto original («Valor del archivo», CA-C06.4)
    @property
    def estado(self) -> EstadoFila: ...

@dataclass(frozen=True)
class ResultadoImportacion:
    codificacion: Codificacion; deteccion: DeteccionSeparador; columnas: MapaColumnas
    filas: tuple[FilaInterpretada, ...]; avisos: tuple[AvisoArchivo, ...]
    perfil_base_id: str; con_inventario: bool       # False → solo capa 1 (CA-C06.10)
    @property
    def numeros_validos(self) -> tuple[int, ...]: ...
```

Errores de **todo el archivo** (no de una fila) salen como `ErrorProxLaunch`: E-M01, E-M05, E-M06,
E-M07, E-M09, E-M10. Errores de fila/columna son `ProblemaCelda` y nunca excepciones.

## 4. Lote por filas: un solo camino en el núcleo (RF-C08, RF-C09, D-22)

### 4.1 Validación de la definición (`planificador.validar_definicion`, pura)
- Homogéneo: igual que M2 (V-L01..V-L04, V-L07, V-L13, V-L15).
- Por filas: `validar_filas(definicion)` → V-L01 (1 ≤ N ≤ `MAX_LOTE` y `cantidad == len(filas)`),
  V-M07 (nombre vacío), V-M10 (nombres repetidos sin distinguir mayúsculas; VMIDs explícitos
  repetidos: **todas** las filas implicadas, `Problema.indice` de cada una), V-02 del VMID explícito;
  V-L07 sobre `vmid_inicial` y el último VMID automático (`primero + k − 1`, k = filas sin VMID);
  V-L13 si `destino.modo != AUTOMATICO`; V-L15 igual. Patrón (V-L02..V-L04): no se evalúa.

### 4.2 Reserva de VMIDs (`Planificador.planificar`, E/S solo GET)
1. VMIDs explícitos: `comprobar_vmids(fijos)` en paralelo (`MAX_CONSULTAS_SIMULTANEAS`) con
   `cliente.vmid_libre`. Ocupado → `Problema("V-03", ERROR, "vmid", {"vmid"}, indice)`; **nunca** se
   reasigna (CA-C08.3, CA-C09.3). La interfaz ofrece «Asignar automáticamente» (acción explícita:
   `reemplazar_fila(…, vmid=None)` y se vuelve a planificar).
2. Automáticos: `reservar_vmids(inicio, k, excluir=frozenset(fijos))`. Los excluidos no se consultan
   ni cuentan como saltados; el resto igual que M2 (ventana `MAX_SALTO_VMID`, sin plan parcial).
3. Se combinan en el orden de las filas y se pasan a `construir_plan` (sin cambio de firma); los V-03
   de (1) viajan en `problemas_extra`, como V-L16 hoy.

### 4.3 Construcción del plan (`construir_plan`, pura, firma de M2 sin cambios)
`filas = filas_efectivas(definicion)` → `nodos, reparto, p = repartir_filas(filas, destino, inv,
por_filas=…)` → elementos `ElementoPlan(i, fila.nombre, vmids[i], nodos[i], cfg_i)` con
`cfg_i = deepcopy(fila.cfg)` y `vmid/nombre/nodo/etiquetas` fijados; etiquetas =
`fila.cfg.etiquetas + (proxlaunch, lote-<id>)` si `etiquetar` (función `_etiquetas(base, …)`).
Después, igual que M2: V-L05, `uso_por_clave(elementos)` (ya suma por elemento, CA-C08.5),
`evaluar_espacio`, V-L06, V-L12 (suma `e.cfg.memoria_mib` por nodo: ya heterogéneo) y `validar_vm`
por elemento en su nodo (V-01 del nombre de cada fila incluido). Diferencias por filas:
- Sin espacio: `capacidad_maxima = None` y `Plan.filas_excedentes = filas_que_exceden(...)`
  (CA-C08.6). El homogéneo sigue con «Reducir a N».
- Fila sin nodo posible: E-L01 **por fila** (`indice`), en lugar de uno agregado. El plan sale
  bloqueado y sin elementos, como en M2, y la interfaz ofrece quitar esas filas.

### 4.4 Reparto (`repartir_filas`, pura)
1. **Filas con nodo fijo** (primera pasada, en orden): el nodo debe existir, estar en línea y ser
   elegible **para esa fila** (`_motivos_nodo(fila.cfg, …)`, sin cambios). Si no: V-L11 ERROR con
   `indice`. Si sí: se descuentan su pedido (`pedido_vm`) y su memoria del presupuesto vivo.
2. **Filas automáticas** (segunda pasada, en orden): candidatos = nodos elegibles **para esa fila**
   (caché por firma de recursos: storages de discos, efidisk y bridges; en homogéneo hay una sola
   firma → mismo coste y resultado que M2). Equilibrado y Por turnos con las mismas reglas de M2,
   pero el pedido y la memoria que se descuentan son los de la fila.
3. `reparto[nodo] = (cuántas, motivo)`; motivo `ELEGIDO_POR_USUARIO` si todas las filas del nodo
   eran fijas; si no, el del algoritmo.
`repartir(definicion, inv, cantidad)` conserva su firma: construye `[FilaLote("", plantilla)] *
cantidad` y delega (lo usa `capacidad_maxima`). `UN_NODO` del homogéneo conserva su rama actual.

### 4.5 Presupuesto, informe, simulación, reintento
- `uso_de_nodos(plantilla, nodos, inv)` queda como envoltorio de `uso_de_filas(filas, nodos, inv)`.
- `filas_que_exceden(elementos, inv, politica)`: recorre en orden del plan con totales acumulados
  por clave; un elemento excede si en alguna de sus claves el acumulado supera `libre` (no thin o
  `BLOQUEAR`) o `FACTOR_THIN_MAX × libre` (thin con tope); con `ADVERTIR`, nunca.
- `informe.py`: `por_filas=plan.definicion.es_por_filas`; `plantilla` se sigue rellenando (compat).
- `simulacion.py`: sin cambios (mismo `Planificador`, peticiones por `e.cfg`; CA-C08.9, INV-L5).
- Reintento (CA-C08.10): `ventana_principal._reintentar_pendientes` usa
  `definicion_para_reintento(definicion, elementos)` (homogéneo: `replace(cantidad=…,
  vmid_inicial=None)` como hoy; por filas: filas = una `FilaLote` por elemento con su `cfg`, nombre,
  VMID y nodo). `armar_reintento` no cambia.
- `motor.py`: sin cambios; INV-L1..L5 se conservan por construcción porque el motor solo ve
  `ElementoPlan` (y se vuelven a probar, §13).

### 4.6 Compatibilidad de firmas (resumen)

| Función | Cambio | Compatibilidad |
|---|---|---|
| `DefinicionLote`, `Plan`, `InformeLote` | + campo con valor por defecto al final | Constructores actuales válidos |
| `validar_definicion`, `construir_plan` | Misma firma; ramifican por `es_por_filas` | Pruebas M2 sin cambio |
| `usa_nombre_de_plantilla` | Falso en por filas | Idéntico en homogéneo |
| `Planificador.reservar_vmids` | + `excluir: frozenset[int] = frozenset()` (solo nombre) | Llamadas actuales válidas |
| `Planificador.comprobar_vmids` | Nueva | — |
| `repartir` | Misma firma; delega en `repartir_filas` | Equivalencia probada |
| `uso_de_nodos`, `capacidad_maxima` | Misma firma | Igual |
| `motor`, `libro`, `rollback`, `simulacion` | Ninguno | diff vacío |

## 5. Formato, lectura y escritura seguras (RF-X01..X05)

### 5.1 Lectura de archivos de terceros (perfiles importados, lotes, CSV)
`leer_archivo_limitado(ruta, limite)`:
1. `os.open(ruta, O_RDONLY | O_NONBLOCK (POSIX) | O_BINARY (Windows))`: abrir una tubería con nombre
   no bloquea. `fstat` sobre el descriptor: si no es `S_ISREG` → E-M01 (`motivo=no_regular`); si
   `st_size > limite` → E-M01 (`demasiado_grande`, `limite`, `tamano`) sin leer.
2. Lectura en bloques hasta `limite + 1` bytes como máximo (un archivo que crece o miente en
   `st_size` tampoco se lee entero); si llega a `limite + 1` → E-M01.
3. Errores de E/S → E-M05 (`motivo`: `no_existe`, `sin_permiso`, `bloqueado` —`PermissionError`
   con `winerror` 32/33 en Windows—, `otro`); `params["archivo"]` = **solo el nombre**, nunca la ruta.
4. Solo lectura: no existe en `nucleo/archivos/` ninguna función que renombre, trunque o borre un
   archivo de entrada (INV-M3). `AlmacenJson` **no** se usa con archivos de terceros.
5. Registro (CA-X02.10): `logging` con nombre de archivo, tamaño y códigos de error/aviso; nunca
   contenido ni valores.

### 5.2 JSON estricto
`cargar_json_estricto(datos)`: quita un BOM UTF-8 inicial (lo añade el Bloc de notas; decisión D-T7)
→ `decode("utf-8", "strict")` → **pre-escaneo lineal** de profundidad de `[`/`{` fuera de cadenas
(> `PROFUNDIDAD_JSON_MAX` → E-M04 `profundidad`, sin llegar al parser: imposible un
`RecursionError`) → `json.loads` con `parse_constant` (NaN/Infinity → error), `parse_float` que
rechaza no finitos (`1e999`), `object_pairs_hook` que rechaza claves repetidas. `ValueError` (incluido
el límite de dígitos de `int`) y `RecursionError` → E-M04. Profundidades reales: lote por filas 7,
perfiles 6.

### 5.3 Esquema estricto y lista blanca (CA-X02.4, RF-X04)
`LectorEsquema` acumula `ErrorCampo` con ruta (`"filas[3].config.discos[0].tamano_gib"`):
- Tipos **reales**: `bool` no es `int`; `float` no es `int` (`2.0` en JSON es error de tipo); cadena
  no es número. Enums por valor exacto. Rangos de M1 donde son de capa 1 (los de `validacion.py`
  se reutilizan importando sus constantes, no se copian).
- Cadenas: `texto_seguro` (NFC, ≤ `MAX_LONG_TEXTO`, sin `Cc` salvo `\n` en `descripcion`, sin
  U+202A–U+202E, U+2066–U+2069, U+200E/U+200F, U+061C) y `contiene_token` (V-M05) en nombres y
  descripciones.
- Claves: primero `es_clave_credencial(clave)` (normalizada: minúsculas, sin acentos ni
  separadores; contiene `token`, `password`, `contrasena`, `secreto`, `secret`, `ticket`, `csrf`,
  `apikey`, `api_key`, `credencial`) → se descarta **sin leer el valor** y se cuenta para
  E-M16; después, desconocidas → se descartan y se cuentan (CA-X01.6). Ninguna de las dos se
  conserva al reescribir.
- `esquema_config.py` define la lista blanca de la configuración en **dos modos**: perfil (pistas
  `storage_preferido`, `storage_efi_preferido`, `bridge_preferido`, opcionales) y lote (`storage`,
  `storage_efi`, `bridge` reales). Serializadores por construcción campo a campo (como
  `persistencia/perfiles._a_dict`), sin volcado genérico; sin `vmid`, `nombre`, `nodo` ni
  `etiquetas` en la configuración (los de la fila van fuera, en `filas[i]`).
- Tras el esquema, `validar_sin_servidor(cfg)` (capa 1, §6.2) se aplica a perfiles al guardar e
  importar; en lotes, sus problemas se muestran en el formulario tras cargar (§6.5).

### 5.4 Envoltura y migraciones (RF-X01)
`abrir_envoltura(dato, formato_esperado)`: raíz objeto con `formato` exacto → si no, E-M02 con
`esperado` y, **solo** si el valor es otro formato conocido de ProxLaunch, `encontrado` (pista
«Parece un archivo de perfiles», CA-G06.6). `version_formato` entero no booleano ≥ 1 (si no, E-M02);
mayor que `VERSION_FORMATO` → E-M03; menor → aplica `MIGRACIONES[formato][v]` (funciones puras
`dict → dict`, v → v+1) hasta la actual y añade el aviso `MIGRADO`. En el MVP 3 la cadena está vacía
(prueba CA-X01.3). Regla escrita en `envoltura.py`: añadir un campo opcional con valor por defecto no
sube `version_formato`; cambiar el significado de uno existente, sí (CA-X01.7).

Almacén propio `perfiles_maquina.json`: usa la **misma** envoltura (`formato = proxlaunch.perfiles`;
el `version_esquema` de CA-P10.2 es `version_formato`) con `id` en cada perfil. Versión futura →
`solo_lectura` (se cargan los perfiles que pasen el esquema v1, se avisa E-M14 y toda escritura
lanza `PERFILES_SOLO_LECTURA`, INV-M8). Corrupto → `AlmacenJson.leer` (renombra a `.danado-*`, solo
el almacén propio, CA-P10.3).

### 5.5 Escritura (RF-X03)
`escribir_atomico(ruta, datos)`: `mkstemp` en la carpeta de destino (nace 0600 en POSIX) →
`write` → `flush` + `fsync` → `os.replace`; ante cualquier error borra el temporal y lanza
`ARCHIVO_NO_GUARDABLE` (`motivo`: `sin_espacio` (ENOSPC), `sin_permiso`, `bloqueado`
(Windows, archivo abierto en Excel), `ruta_larga` (ENAMETOOLONG o > 260 en Windows sin rutas
largas), `otro`). No crea la carpeta elegida por el usuario ni cambia sus permisos (CA-X03.2); las
carpetas propias (`lotes/`, configuración) se crean con `crear_carpeta_privada`. JSON:
`json.dumps(ensure_ascii=False, indent=2, sort_keys=True)` en UTF-8 sin BOM. El almacén propio
escribe con `AlmacenJson.escribir` (ya atómico) envuelto para traducir `OSError` a E-M08.

### 5.6 Escritor único de CSV (RF-C11)
`texto_csv(encabezado, filas, *, separador)` (pura) y `escribir_csv` (= `texto_csv` +
`escribir_atomico`): `csv.writer(QUOTE_MINIMAL, lineterminator="\r\n")`, UTF-8 **con BOM**. Cada
celda:
- `int` no booleano y ≥ 0 → tal cual (CA-C11.3). Cualquier otro tipo que no sea `str` → `TypeError`
  (fallo de programación, no de datos).
- `str` → `sanear_celda`: elimina `Cc`/bidi (CA-C11.7; `\t\r\n` incluidos, así `"\t=1"` → `"=1"`) y,
  si el primer carácter tras espacios y comillas es `= + - @` (o era un `\t`/`\r`/`\n` eliminado),
  antepone `'` (CA-C11.1/C11.2). Los enteros negativos se escriben como texto saneado (`'-1`).
Lo usan la plantilla, las filas con error y el informe CSV; ningún otro módulo escribe CSV (prueba
estática: `csv.writer` solo aparece en `csv_seguro.py`). Al importar, una `'` inicial seguida de un
disparador se quita **una** vez (CA-C11.5).

## 6. Flujos

### 6.1 Aplicar un perfil al formulario (RF-P05, RF-P06, RF-P07)
1. El usuario elige en `SelectorPerfil`. Si `hardware_igual(cfg_formulario, cfg_ultima_aplicada)`
   es falso (hubo cambios manuales) → confirmación «Se reemplazarán…» con foco en «Cancelar»
   (CA-P05.2); si no, sin preguntar. Con lote en ejecución, el selector está deshabilitado.
2. `aplicar_perfil(perfil, actual=formulario.configuracion(), inv)` (pura, ≤ 100 ms): conserva
   `vmid`, `nombre` y `nodo` de `actual`; copia el hardware; resuelve pistas **en el nodo efectivo**
   `actual.nodo`:
   - disco: pista apta (existe, activa, `images`) → se usa; si no → `storage_por_defecto` y
     `AvisoPista(recurso="storage", pedido, usado, nodo)` (uno por pista distinta); sin pista → por
     defecto sin aviso (CA-P06.4); sin ningún storage apto → `storage=""` y que V-17 lo señale
     (CA-P06.7, nada inventado).
   - efidisk: `storage_efi_preferido` apto → `storage_efi`; si no → `None` (= el del primer disco) con
     aviso si había pista.
   - red: pista en los bridges del nodo (`TIPOS_BRIDGE`) → se usa; si no → `bridge_por_defecto` con
     aviso; sin bridges → V-16.sinredes de M1.
3. `formulario.aplicar_hardware(resultado.cfg)` (no toca nombre, VMID, nodo ni sus marcas de
   «tocado») y el bloque de lote no cambia (CA-P05.1). Se guarda `cfg_ultima_aplicada` y el selector
   muestra «<perfil>» y, tras cualquier edición, «<perfil> (modificado)» (CA-P05.8); si el perfil se
   elimina o cambia, «Personalizado» (CA-P04.5).
4. Avisos de pistas en un panel cerrable; `evaluar_compatibilidad(cfg, perfil.config, inv, caps)`
   (= `validar_vm` con las capacidades efectivas + `funciones_requeridas`, vacía en el MVP 3 y
   probada con una función inyectada) alimenta el panel «Compatibilidad del perfil» (CA-P07.1..7).
   Se recalcula la validación y se invalida el resumen (CA-P05.5; ya lo hace `cambiado` del formulario).
5. No hay E/S de red (INV-M1): `aplicar_perfil` no recibe sesión ni cliente.
Clúster con «Automático»: si el formulario cambia luego de nodo efectivo, **no** se re-resuelven
pistas (el formulario ya tiene valores concretos); en lote, la elegibilidad por nodo la decide el
reparto de M2 (CA-P06.5).

### 6.2 Guardar y administrar perfiles (RF-P03, RF-P04, RF-P10)
- «Guardar como perfil de máquina…» (básico y avanzado): `config_desde_configuracion(cfg,
  con_pistas=casilla)` (casilla marcada por defecto, CA-P03.3) → `validar_config_perfil` (capa 1:
  `validar_sin_servidor` sobre la configuración con storage/bridge ficticios; los de capa 2 no
  bloquean, CA-P03.2) → `almacen.crear(nombre, descripcion, config)` (V-M01 con unicidad entre
  todos los visibles, V-M03, V-M05). `nombre_libre(base, existentes)` propone «X (2)».
- «Guardar cambios en el perfil «X»» → `almacen.actualizar(id, config)`; «Guardar como nuevo…» →
  `crear`. Renombrar, duplicar («Copia de X» lo pone la interfaz) y eliminar desde
  `DialogoPerfilesMaquina` (avanzado). Fábrica → `PERFIL_NO_MODIFICABLE` (INV-M7); la interfaz
  deshabilita además los botones con la explicación (CA-P02.2).
- Cada operación escribe a disco **antes** de cambiar la lista en memoria y antes de devolver
  (CA-P04.7); si la escritura falla, la memoria no cambia (E-M08, CA-P03.6). Sin bloqueo entre
  instancias: última escritura gana, nunca un archivo ilegible (CA-P04.8, documentado).
- Arranque: `AlmacenPerfilesMaquina.cargar()` en el hilo de la interfaz (archivo propio ≤ 100
  perfiles); ilegible por permisos → solo fábrica y aviso (CA-P12.3); inexistente → vacío, sin crear
  archivo (CA-P12.2).

### 6.3 Exportar e importar perfiles (RF-P08, RF-P09)
- Exportar: selección (fábrica o usuario) → diálogo con «Incluir los nombres de almacenamiento y
  red» **desmarcada** (CA-P08.2) → nombre sugerido `nombre_archivo_seguro(nombre,
  ".proxlaunch-perfiles.json")` → diálogo del sistema (confirma sobrescritura) →
  `exportar_perfiles(ruta, perfiles, con_pistas, app_version)` en hilo. Sin `id` ni `origen` en el
  archivo (§9.1 de los requisitos).
- Importar: diálogo del sistema → hilo: `leer_archivo_perfiles(ruta)` (≤ 256 KiB, ≤ 100 perfiles
  antes de interpretar los perfiles: E-M01) → `ArchivoPerfiles(validos, invalidos, avisos)` →
  `DialogoImportarPerfiles`: casillas, inválidos marcados y no seleccionables, conflicto de nombre
  «Conservar ambos» por defecto, «Reemplazar» solo contra perfiles del usuario y con confirmación →
  `almacen.importar(entradas)`: todo o nada frente a V-M03, `id` nuevo y origen `usuario` siempre
  (CA-P09.4). Nada se guarda antes de confirmar.

### 6.4 Guardar un lote (RF-G01, RF-G02, RF-G07)
1. «Guardar lote…» (también con cantidad 1 y durante la ejecución, CA-G02.4): la definición actual
   (`bloque_lote.definicion(formulario.configuracion())` o la del lote por filas).
2. Errores de reglas (capa 1 o 2) **no** impiden guardar (borrador, aviso CA-G02.1). Solo bloquea lo
   que no se puede serializar con sentido: un campo no numérico del formulario (la interfaz lo
   detecta antes de construir la definición; p. ej. `gib_a_mib` inválido) con el campo indicado.
3. `DialogoGuardarLote`: nombre (V-M01 sin unicidad; propuesta = prefijo) → diálogo del sistema con
   carpeta sugerida `Rutas.lotes` (creada 0700 al usarla) y extensión `.proxlaunch-lote.json`; si el
   lote vino de un archivo, ofrece sobrescribir ese archivo o «Guardar como…» (CA-G03.6).
4. `guardar_lote(ruta, LoteGuardado(nombre, definicion, version_proxmox), app_version)` en hilo:
   `lote_a_bytes` escribe solo la lista blanca (§9.2 de los requisitos): `tipo` `homogeneo` (config,
   cantidad, patrón, destino, `vmid_inicial` solo si el usuario lo fijó —si no, `null`—, `etiquetar`,
   `nombre_maquina` si aplica) o `por_filas` (`filas[{nombre, vmid, nodo, config}]`,
   `destino.algoritmo`, `vmid_inicial`, `etiquetar`). Nunca plan, VMIDs reservados, libro, UPID,
   `id_lote`, `politica_thin`, perfil de conexión, host ni usuario (INV-M5, INV-M2): la función recibe
   un `LoteGuardado`, no un `Plan`.
5. Se actualiza la «huella guardada» (`lote_a_dict` de lo guardado) para RF-G08.

### 6.5 Abrir un lote guardado (RF-G03..G06)
1. Requiere sesión conectada (S-M7). Si hay cambios sin guardar → «¿Guardar el lote antes de
   continuar?» (RF-G08).
2. Hilo: `leer_archivo_lote(ruta)` → lector limitado (1 MiB) → JSON estricto → envoltura → esquema →
   filas ≤ `MAX_LOTE` (si no, E-M06 sin cargar ninguna, CA-G06.5). Cualquier error → mensaje con la
   lista de campos (E-M02/03/04/06) y **el formulario no cambia** (carga atómica, RNF-M11).
3. En el hilo de la interfaz, de una vez:
   - Homogéneo: `formulario.aplicar_hardware(plantilla)` + `bloque_lote.establecer_definicion(def)`;
     nombre/VMID del formulario quedan como ejemplo del lote (como hoy).
   - Por filas: se entra en modo lote por filas (§6.6 paso 7) y se abre la vista previa de filas
     (CA-G07.2) con `filas_efectivas` revalidadas.
   - Avisos (desconocidos, credenciales, migrado, versión de Proxmox mayor que la detectada) en un
     panel cerrable (CA-G03.4, CA-G04.6).
4. Revalidación inmediata (CA-G04.1): la validación normal del formulario (`_validar`: `validar_vm`
   + problemas del bloque) marca los campos, y `desajustes(definicion, inv)` alimenta
   `PanelLoteNoEncaja`: por cada storage/bridge/nodo inexistente, los valores disponibles y
   «Usar otro…» (`sustituir(definicion, desajuste, nuevo)` + volver a aplicar) o «Pasar a
   Automático» para el nodo. **Nunca** hay sustitución silenciosa: las tablas de discos y redes
   muestran el valor inexistente como «x (no existe)» con error (CA-G04.3).
5. «Crear» **no** se habilita: solo existe «Ver resumen», que ejecuta el planificador completo con el
   inventario del momento (VMIDs, reparto, espacio, memoria, permisos; CA-G04.2, INV-M6). Las
   políticas de M2 (bloquear con «Reducir a N», saltar VMIDs) se aplican sin modificar lo cargado.
6. Cambio de servidor antes del resumen: el lote cargado se mantiene en el formulario pero se
   descartan resumen y desajustes y se recalculan con el inventario nuevo (CA-G04.8, CA-G05.4).
7. La aplicación no vuelve a leer ni vigila el archivo (CA-G03.7).

### 6.6 Importar CSV (RF-C01..C09, C13, C15)
1. «Importar desde CSV…» (menú Lote; básico y avanzado). Cambios sin guardar → RF-G08.
2. Diálogo del sistema → **hilo** (cancelable): `leer_archivo_csv(ruta, opciones)`:
   lector limitado (1 MiB) → `decodificar` (orden BOM UTF-8, BOM UTF-16, UTF-8 estricto,
   Windows-1252 estricto —el códec de Python ya rechaza 0x81/0x8D/0x8F/0x90/0x9D—; error → E-M07
   con la fila aproximada = saltos de línea antes del byte + 1; U+FFFD o `\x00` → E-M07) →
   `detectar_separador` (primeras 20 líneas con `csv.reader` por candidato; gana el que da el mismo
   número de columnas ≥ 2 en más líneas; empate → `;` si aparece un decimal con coma, si no
   `ambiguo=True`; `sep=X` en la primera línea manda y se omite) → `leer_tabla` (`csv.reader` en modo
   estricto sobre `io.StringIO(texto, newline="")`, `\r\n`/`\n`/`\r`; comillas sin cerrar → E-M07 con
   la fila donde empezó el registro; > 40 columnas, celda > 256 o > `MAX_LOTE` filas no vacías → E-M06
   con valor real, contando todas las filas sin guardarlas; 0 filas de datos → E-M09).
3. Mismo hilo: `interpretar(tabla, perfil_base, perfiles, inv, nodo_referencia)` (pura):
   - `resolver_columnas` (E-M10: falta `nombre`, duplicadas por alias, encabezado vacío entre
     columnas con datos; desconocidas y credenciales → avisos, sus celdas no se leen).
   - Por fila, precedencia (CA-C13.5): `ConfigPerfil` del perfil de la fila (`perfil`, V-M06 si no
     existe o es ambiguo: nombres visibles o id, sin mayúsculas ni acentos) o del perfil base →
     `aplicar_perfil` con pistas resueltas en `nodo` de la fila o `nodo_referencia` (aviso de pista
     una vez por fila; sin inventario, la pista queda como valor y la capa 2 se hace al continuar) →
     columnas del CSV (unidades de §6.6.1; `disco`/`almacenamiento` = disco 1, creado con los valores
     por defecto si el perfil no tiene; `disco2..8`; `red`/`vlan` = red 1).
   - Capa 1 por fila: V-M07, `validar_sin_servidor(cfg, incluir_nombre=True)` (V-01, V-05..V-08,
     V-15, V-22…), V-02, V-M09 (memoria > 1024 GiB o > mayor nodo conocido), V-M11 (`ejemplo-`);
     V-M10 entre filas (todas las implicadas).
   - Capa 2 de vista previa (solo con `inv`): nodo fijo → `validar_vm` en ese nodo (V-04 «Sin
     conexión», V-16, V-17, V-09); automático → `nodos_elegibles(cfg, inv, Destino())` vacío → error de
     fila con los motivos; V-L06 (nombre existente) se deja al plan (necesita GET). Ocupación de VMID
     explícito: al plan (CA-C09.3).
4. Vista previa (`DialogoImportarCsv`, `ModeloVistaPreviaCsv`): archivo (nombre, no ruta),
   codificación y separador (selector siempre visible en avanzado; en básico, solo si `ambiguo`),
   perfil base (por defecto el aplicado o el predeterminado; cambiarlo relanza `interpretar` en hilo
   con contador de generación), tabla con estado texto+símbolo, filtro «Mostrar solo problemas»,
   detalle por fila con valor original, «Copiar errores», casillas para excluir filas (CA-C07.4).
5. Confirmación (P-M02 B, D-22): sin errores → «Continuar». Con errores → botón principal «Corregir
   el archivo» (cierra; el formulario no cambia) y secundario «Importar solo las N filas correctas»
   con confirmación que lista las excluidas por número y nombre (CA-C07.1/C07.2). Sin conexión, el
   botón de continuar está deshabilitado (CA-C06.10). Todas excluidas → no se puede continuar.
6. `filas = filas_lote(resultado, numeros_elegidos)` → `definicion_por_filas(filas,
   plantilla_base=…, algoritmo=…, vmid_inicial=None, etiquetar=…)`. Si el inventario cambió desde la
   vista previa, se reinterpreta antes (las filas llevan storage/bridge reales del inventario actual).
7. Modo lote por filas en la ventana: `PanelLoteFilas` sustituye al formulario (tabla de solo
   lectura: nombre, VMID, nodo, hardware; «N máquinas desde el archivo «x.csv»», CA-C01.3); el
   bloque de lote oculta cantidad y patrón y deja algoritmo (avanzado), VMID inicial y etiquetas.
   Acciones: «Ver resumen», «Revisar filas…» (reabre la vista previa con el mismo resultado),
   «Guardar lote…», «Salir del lote por filas». Sin edición por fila (CA-G07.3).
8. «Ver resumen» → `Planificador.planificar` (mismo camino que M2, §4) → `ResumenLote` con una fila
   por MV (núcleos y memoria incluidos, CA-C08.7), «N de N+M filas del archivo» (CA-C07.2), problemas
   por fila con su número de origen, y en lugar de «Reducir a N» «Quitar las filas que no caben»
   (`sin_filas(definicion, plan.filas_excedentes)` + replanificar; CA-C08.6). VMID explícito ocupado →
   «Asignar automáticamente» por fila. → «Simular» / «Crear N máquinas» (confirmación de M2) →
   `MotorLote` sin cambios.

#### 6.6.1 Unidades y números (`unidades.py`, CA-C04)
Recorte de espacios y comillas; número = `[0-9]+([.,][0-9]+)?`; se rechazan signo, exponente, hex,
`NaN`/`Infinity`. Ambos separadores, o un único separador seguido de exactamente 3 dígitos en
`cpu`, `sockets`, `vmid`, `vlan`, `disco*` **y `memoria`** → V-M08 (decisión D-T8: en memoria `1.000`
es tan ambiguo como en disco). Aritmética exacta con `fractions.Fraction`. Memoria sin unidad = GiB;
`M/MiB/MB`, `G/GiB/GB`, `T/TiB/TB` (MB/GB/TB como binarias); el resultado en MiB debe ser entero.
Disco sin unidad = GiB; resultado en GiB entero ≥ 1; `0`, `ninguno`, `sin disco` → sin disco
(`con_disco = False`). Enteros: `2` y `2.0` válidos, `2.5` no. Enums sin mayúsculas ni acentos
(`firmware`: `seabios`/`bios`, `ovmf`/`uefi`; `modelo_red`: `virtio`/`e1000`). Los avisos
«GiB asumido», «decimal con coma» y «GB como GiB» se emiten **una vez por columna y archivo**
(D-T9), no por fila. Códigos de celda: `E-M11.no_numero`, `E-M11.no_entero`, `E-M11.mib_no_entero`,
`E-M11.gib_no_entero`, `E-M11.unidad`, `E-M11.valor_no_admitido` (con `ejemplo`/`validos`).

### 6.7 Exportaciones CSV (RF-C10, RF-C12, RF-C14)
- Plantilla: `escribir_plantilla(ruta, separador)`: encabezado canónico (CA-C10.1) y filas
  `ejemplo-01`/`ejemplo-02` válidas; separador `;` por defecto o `,`; BOM y CRLF (CA-C10.2). Prueba:
  la plantilla pasa su propia capa 1 con el perfil predeterminado (CA-C10.4).
- Filas con error: `escribir_filas_con_error(ruta, tabla, resultado, traducir, separador)`: columnas
  originales **excepto las de credenciales** + `fila_original`, `columna`, `problema` (texto que
  aporta la interfaz con `traducir`); al reimportar, esas tres son desconocidas (CA-C12.3).
- Informe CSV: `informe_lote.datos_maquinas(informe)` es la única fuente de las filas del informe
  (texto y CSV, CA-C14.3); `guardar_informe_csv` usa `escribir_csv` (nombre, VMID, nodo, desenlace,
  código de error, duración; UPID nunca).
Todas en hilo de trabajo y por el escritor único (§5.6).

### 6.8 Cambios sin guardar y cambio de servidor (RF-G08, CA-G05.4)
La ventana guarda `huella_guardada = lote_a_dict(LoteGuardado(...))` al cargar o guardar (o `None`
si nunca se editó el formulario). Antes de abrir otro lote, importar un CSV, cambiar de servidor o
cerrar: si `lote_a_dict(actual) != huella_guardada` y el formulario fue editado → «Guardar / No
guardar / Cancelar» (foco en Cancelar). Con lote en ejecución, prevalece la confirmación de RF-L23
(un solo diálogo).

## 7. Interfaz

- **Menús.** *Lote*: Abrir lote…, Guardar lote…, Guardar lote como…, Importar desde CSV…,
  Descargar plantilla CSV…. *Perfiles*: Guardar como perfil de máquina…, Administrar perfiles…
  (avanzado; dentro: Importar…, Exportar…). Filtros y extensiones de CA-X05.1 en `archivos_ui.py`;
  carpeta inicial = última de la sesión o `platformdirs.user_documents_dir()`; las rutas no se
  guardan en `preferencias.json` (CA-X05.3).
- **Modo básico** (D-14, CA-P11.1): arriba el selector «Perfil de máquina», luego nombre/prefijo y
  cantidad; «Guardar como perfil» e «Importar desde CSV» disponibles; administrar, separador,
  codificación y columnas avanzadas solo en avanzado.
- **Selector**: fábrica primero con el texto «De fábrica» (CA-P02.1), resumen en lenguaje llano
  (`resumen_perfil`) y descripción al elegir (CA-P11.2).
- **Accesibilidad** (RNF-M06): tablas con modelo (`QAbstractTableModel`), estados con texto y
  símbolo, `accessibleName` en selector, tablas, botones y paneles; diálogos destructivos con foco en
  «Cancelar».
- **Textos** (RNF-M04): `textos.py` traduce los códigos E-M, V-M, `E-M11.*`, `AvisoPista`,
  `CodigoAvisoArchivo` y `MotivoCampo`; plurales con `tr(…, n)`; `ayuda.py` añade los identificadores
  de CA-P11.3 (perfil, perfil de fábrica, pistas, guardar como perfil, exportar/importar,
  compatibilidad, lote guardado, CSV, plantilla CSV, separador, codificación, unidades, vista previa).
  Los alias de encabezado del idioma activo los pasa la interfaz a `resolver_columnas(alias_extra=…)`.

## 8. Códigos nuevos (`CodigoError`) y textos

| E-M | `CodigoError` (valor) | Params | Lo lanza |
|---|---|---|---|
| E-M01 | `ARCHIVO_NO_PERMITIDO` (`archivo_no_permitido`) | motivo (`no_regular`, `demasiado_grande`, `demasiadas_entradas`), limite, tamano | `leer_archivo_limitado`, lectores de perfiles |
| E-M02 | `ARCHIVO_FORMATO_AJENO` (`archivo_formato_ajeno`) | esperado, encontrado? | `abrir_envoltura` |
| E-M03 | `ARCHIVO_VERSION_FUTURA` (`archivo_version_futura`) | version_archivo, version_soportada | `abrir_envoltura` |
| E-M04 | `ARCHIVO_DANADO` (`archivo_danado`, sin «ñ» en el identificador) | campo, detalle, n | `cargar_json_estricto`, `LectorEsquema` (`ErrorArchivo`) |
| E-M05 | `ARCHIVO_NO_ACCESIBLE` (`archivo_no_accesible`) | archivo (solo nombre), motivo | `leer_archivo_limitado` |
| E-M06 | `ARCHIVO_DEMASIADAS_FILAS` (`archivo_demasiadas_filas`) | tipo (`filas`, `columnas`, `celda`), filas/columnas, max | `leer_tabla`, `leer_lote` |
| E-M07 | `CSV_CODIFICACION` (`csv_codificacion`) | fila, motivo (`codificacion`, `nulo`, `sustitucion`, `comillas`) | `decodificar`, `leer_tabla` |
| E-M08 | `ARCHIVO_NO_GUARDABLE` (`archivo_no_guardable`) | motivo | `escribir_atomico`, almacén |
| E-M09 | `CSV_VACIO` (`csv_vacio`) | — | `leer_tabla` |
| E-M10 | `CSV_COLUMNAS` (`csv_columnas`) | motivo (`falta_nombre`, `duplicada`, `vacia`), columna, posiciones, reconocidas | `resolver_columnas` |
| E-M11 | `CSV_VALOR_INVALIDO` (`csv_valor_invalido`) | fila, columna, valor, ejemplo | Solo para textos/CSV de errores: las filas usan `ProblemaCelda` |
| E-M12 | `PERFIL_INEXISTENTE` (`perfil_inexistente`) | nombre, disponibles (≤ 5) | `almacen.obtener`; V-M06 en filas |
| E-M13 | `PERFIL_NO_MODIFICABLE` (`perfil_no_modificable`) | — | almacén |
| E-M14 | `PERFILES_SOLO_LECTURA` (`perfiles_solo_lectura`) | — | almacén |
| E-M15 | `LOTE_NO_ENCAJA` (`lote_no_encaja`) | campo, valor, disponibles | `PanelLoteNoEncaja` (los `Desajuste` lo parametrizan) |
| E-M16 | `CodigoAvisoArchivo.CREDENCIAL_IGNORADA` (aviso, no error) | n | lectores de JSON y CSV |
| — | `PERFIL_RECHAZADO` (`perfil_rechazado`, interno) | regla (V-M01/V-M03/V-M05), campo | almacén (la interfaz muestra el texto de la regla) |

Textos de usuario: los de la sección 7 de los requisitos para E-M01..E-M16 y los de la tabla §5
para V-M01..V-M15, más: motivos de E-M01/E-M05/E-M07/E-M08, `MotivoCampo` («falta», «tipo de dato
incorrecto», «fuera de rango»…), `E-M11.*` con ejemplo, `AvisoPista` («El perfil pedía el
almacenamiento «{pedido}», que no existe en «{nodo}». Se usó «{usado}».»), avisos de archivo
(desconocidos, migrado, «GiB asumido», «decimal con coma», «GB como GiB», columna no usada), panel de
compatibilidad («Requiere Proxmox {version} o superior»), estados de fila, «N de N+M filas»,
«Quitar las filas que no caben», «Asignar automáticamente», «Pasar a Automático», «Usar otro…».
Todos en `textos.py`/`ayuda.py` o en `self.tr` del diálogo correspondiente; el núcleo no tiene
textos (prueba de literales de M1 extendida).

## 9. Seguridad e invariantes (cómo se garantiza cada INV-M)

| Invariante | Garantía por construcción | Prueba |
|---|---|---|
| INV-M1 sin escrituras al abrir/aplicar/importar | Ninguna función de `archivos/`, `perfiles_maquina/`, `lotes_guardados/` ni `csv_importacion/` recibe `Sesion` ni cliente (solo bytes, rutas e `Inventario`); el único acceso a red del flujo es el `Planificador` (solo GET) al pedir el resumen | Transporte que falla ante cualquier método ≠ GET/HEAD durante abrir, cargar, aplicar, importar y resumir |
| INV-M2 sin secretos ni sitio | Serializadores de lista blanca campo a campo; `LoteGuardado` no tiene campos de sesión; `ProblemaCelda.valor` recortado y saneado; log solo nombre/tamaño/códigos; claves de credencial descartadas sin leer su valor | Centinela (token, contraseña, ticket, CSRF, host, usuario) en todos los archivos, logs, mensajes y portapapeles |
| INV-M3 archivo del usuario intacto | `leer_archivo_limitado` abre `O_RDONLY` y es la única puerta de entrada; `AlmacenJson` solo para el almacén propio | Hash y `mtime` antes/después, también con archivos corruptos |
| INV-M4 nada se ejecuta | Solo `json.loads` y `csv.reader`; celdas como texto | Prueba estática: sin `pickle`, `eval`, `exec`, `yaml`, `importlib`, `__import__` en el núcleo nuevo |
| INV-M5 sin plan/libro/UPID/id_lote | `lote_a_bytes(LoteGuardado)` no recibe `Plan`; claves prohibidas no existen en el serializador | Lista de claves del JSON escrito ⊆ lista blanca |
| INV-M6 todo pasa por resumen y confirmación | Cargar/importar solo rellena formulario o panel; `MotorLote` solo se lanza desde `ResumenLote` con un `Plan` recién generado; cualquier cambio invalida el plan (contadores de generación de M2) | UI: tras cargar/importar, `resumen_lote.puede_crear()` es falso y no existe plan |
| INV-M7 fábrica inmutable | Tupla de perfiles congelados fuera del almacén; ids `fabrica.*` rechazados (V-M02) en crear/importar; almacén lanza `PERFIL_NO_MODIFICABLE` | Intentos de editar/renombrar/eliminar/reemplazar |
| INV-M8 atómico y sin pisar versión futura | `escribir_atomico`/`AlmacenJson.escribir`; `solo_lectura` bloquea toda escritura | Fallo inyectado en `os.replace`; almacén v2 intacto tras operar |

Otros: `nombre_archivo_seguro` (sin separadores, sin `.`/`..`, sin reservados de Windows `CON`,
`PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`, ≤ 80); ninguna ruta se construye con contenido de un
archivo (CA-X03.3); `origen ≠ disco_vacio` se rechaza en el esquema (CA-P01.2); los valores que van
a la API siguen pasando por V-01/V-16/V-17/V-22/V-24 y por el constructor de M1.

## 10. Concurrencia y rendimiento

- **Hilos.** Lectura, decodificación, análisis e interpretación de CSV, lectura de lotes y perfiles
  de terceros, y escritura de archivos elegidos por el usuario se ejecutan con `Trabajador` en el
  `QThreadPool` (funciones nuevas en `trabajadores.py`, envoltorios finos del núcleo). El almacén
  propio se usa solo desde el hilo de la interfaz (sin cerrojo).
- **Cancelación.** El diálogo de importación lleva un contador de generación (patrón `_si_vigente`
  de M2): cerrar o reintentar descarta resultados tardíos; las funciones del núcleo son puras y
  rápidas, por lo que no necesitan interrupción a mitad (CA-X02.8). La aplicación del resultado al
  formulario ocurre en un solo paso en el hilo de la interfaz (carga atómica).
- **Rendimiento (RNF-M05).** CSV de 1 MiB/100 filas: lectura limitada O(n), un `csv.reader` por
  candidato sobre 20 líneas, análisis completo O(n) (≤ 100 × 40 celdas); `interpretar` hace por fila
  `aplicar_perfil` + `validar_sin_servidor` + (con inventario) `validar_vm`/`nodos_elegibles`:
  orden de milisegundos (objetivo ≤ 1 s de CPU). Plan por filas de 100: elegibilidad cacheada por
  firma de recursos, reparto O(N·k); comprobación de VMIDs fijos en paralelo (≤ 8 GET simultáneos),
  como la reserva de M2. Memoria del análisis ≤ 5 × tamaño (sin copias intermedias del texto;
  conteo de filas sobrantes sin guardarlas; `tracemalloc` en la prueba). La vista previa de 100 filas
  usa modelo de tabla (sin un widget por fila).

## 11. Trazabilidad RF → módulo → flujo

| RF | Núcleo | Interfaz | Flujo |
|---|---|---|---|
| RF-P01 | `perfiles_maquina/modelos`, `validacion`, `archivos/esquema_config` | — | §6.2 |
| RF-P02 | `perfiles_maquina/fabrica` | `selector_perfil`, `dialogos/perfiles_maquina` | §6.1 |
| RF-P03, P04 | `perfiles_maquina/almacen`, `validacion`, `aplicar` | `dialogos/guardar_perfil`, `dialogos/perfiles_maquina` | §6.2 |
| RF-P05, P06 | `perfiles_maquina/aplicar` | `selector_perfil`, `formulario_vm.aplicar_hardware` | §6.1 |
| RF-P07 | `perfiles_maquina/compatibilidad` | panel de compatibilidad (`ventana_principal`) | §6.1 |
| RF-P08, P09 | `perfiles_maquina/formato`, `almacen.importar` | `dialogos/perfiles_maquina`, `dialogos/importar_perfiles` | §6.3 |
| RF-P10, P12 | `perfiles_maquina/almacen`, `persistencia/rutas` | arranque en `ventana_principal` | §6.2 |
| RF-P11 | `perfiles_maquina/aplicar.resumen_perfil` | `selector_perfil`, `ayuda.py` | §7 |
| RF-X01 | `archivos/envoltura` | — | §5.4 |
| RF-X02 | `archivos/lector`, `json_estricto`, `esquema`, `texto` | `trabajadores` | §5.1–5.3 |
| RF-X03 | `archivos/escritura`, `csv_seguro` | — | §5.5 |
| RF-X04 | `archivos/esquema`, `texto`, serializadores | — | §5.3, §9 |
| RF-X05 | — | `archivos_ui` | §7 |
| RF-G01, G02, G07 | `lotes_guardados/formato`, `modelos` | `dialogos/guardar_lote` | §6.4 |
| RF-G03, G06 | `lotes_guardados/formato` | `ventana_principal`, `bloque_lote.establecer_definicion` | §6.5 |
| RF-G04, G05 | `lotes_guardados/revalidacion`, `lote/planificador` | `dialogos/lote_no_encaja`, `tabla_discos`, `tabla_redes` | §6.5 |
| RF-G08 | `lotes_guardados/formato.lote_a_dict` | `ventana_principal` | §6.8 |
| RF-C01 | `csv_importacion/*` | `dialogos/importar_csv`, `lote_filas` | §6.6 |
| RF-C02 | `decodificacion`, `separador`, `lectura` | `dialogos/importar_csv` | §6.6 (2) |
| RF-C03, C04 | `columnas`, `unidades` | — | §6.6 (3), §6.6.1 |
| RF-C05..C07 | `interpretacion` | `dialogos/importar_csv`, `modelos_tabla_csv` | §6.6 (3–5) |
| RF-C08, C09 | `lote/filas`, `planificador`, `reparto`, `presupuesto`, `informe` | `lote_filas`, `resumen_lote`, `modelos_tabla` | §4, §6.6 (6–8) |
| RF-C10, C11 | `plantilla`, `archivos/csv_seguro` | menú Lote | §6.7, §5.6 |
| RF-C12 | `errores_csv` | `dialogos/importar_csv` | §6.7 |
| RF-C13 | `interpretacion` (+ `aplicar_perfil`) | selector de perfil base | §6.6 (3) |
| RF-C14 | — (datos de `InformeLote`) | `informe_lote` | §6.7 |
| RF-C15 | `lectura`, `lote/filas.validar_filas` (MAX_LOTE de M2) | — | §6.6 (2) |

## 12. Plan de fases y dueños de archivos (sin solapes)

| Fase | Responsable | Archivos (dueño exclusivo) | Depende de | Esfuerzo |
|---|---|---|---|---|
| F3-0 Contratos | orquestador | `nucleo/errores.py` (códigos §8), `nucleo/lote/modelos.py` (FilaLote y campos §3.1), `nucleo/validacion.py` (`validar_sin_servidor`), `nucleo/archivos/__init__.py` y `constantes.py`, `nucleo/archivos/esquema.py` (solo tipos: `ErrorCampo`, `ErrorArchivo`, `AvisoArchivo`, enums), `nucleo/perfiles_maquina/modelos.py` | — | bajo |
| F3a Núcleo archivos + perfiles + lotes guardados | `implementador` A | resto de `nucleo/archivos/` (incl. completar `esquema.py`), resto de `nucleo/perfiles_maquina/`, `nucleo/lotes_guardados/`, `nucleo/persistencia/rutas.py` | F3-0 | alto |
| F3b Núcleo CSV | `implementador` B | `nucleo/csv_importacion/` | F3-0; `interpretacion.py`, `plantilla.py` y `errores_csv.py` se cierran tras F3a (usan `aplicar_perfil`, `texto_seguro`, `csv_seguro`) | alto |
| F3c Lote por filas | `implementador` C | `nucleo/lote/filas.py`, `planificador.py`, `reparto.py`, `presupuesto.py`, `informe.py` | F3-0 | medio-alto |
| F4a Interfaz: diálogos nuevos | `implementador` D | `interfaz/archivos_ui.py`, `modelos_tabla_csv.py`, `dialogos/perfiles_maquina.py`, `guardar_perfil.py`, `importar_perfiles.py`, `guardar_lote.py`, `importar_csv.py`, `lote_no_encaja.py` | F3a, F3b (contra Anexo A puede empezar antes) | alto |
| F4b Interfaz: integración | `implementador` E | `ventana_principal.py`, `trabajadores.py`, `vistas/formulario_vm.py`, `selector_perfil.py`, `lote_filas.py`, `bloque_lote.py`, `resumen_lote.py`, `tabla_discos.py`, `tabla_redes.py`, `modelos_tabla.py`, `informe_lote.py`, `textos.py`, `ayuda.py`, `recursos/traducciones/*.ts` | F3a–F3c; F4a para enlazar diálogos | alto |
| F5 Pruebas | `probador` (1–2 en paralelo: núcleo / interfaz) | `tests/nucleo/test_archivos_*.py`, `test_perfiles_maquina_*.py`, `test_lotes_guardados_*.py`, `test_csv_*.py`, `test_lote_filas_*.py`; `tests/interfaz/test_mvp3_*.py`; `tests/integracion/test_lab_mvp3.py`; `tests/datos/mvp3/` | F3 (núcleo), F4 (interfaz) | alto |
| F6 Revisión | `revisor-qa` + `auditor-seguridad` (paralelo) | informes | F5 en verde | medio |
| F7 Documentación | `documentador` + `formateador` | `docs/guia-usuario.md`, §11 de este documento | F6 | medio |

Paralelismo: F3a, F3b (parte pura) y F3c en paralelo tras F3-0; F4a puede empezar contra el Anexo A
con dobles de prueba; F4b al final. Ningún archivo tiene dos dueños: `textos.py`/`ayuda.py` son solo
de F4b (F4a usa `self.tr` en sus diálogos y `textos.texto_error` para los códigos). Firmas públicas
que surjan durante la implementación se anotan en un Anexo B tras aprobarlas el orquestador.

## 13. Plan de pruebas (derivadas de los requisitos; las escribe el `probador`)

- **No regresión M2 (CA-C08.12, CA-P12.1):** la suite actual sin cambios; además, equivalencia
  de `construir_plan`/`repartir` homogéneos antes/después sobre los casos de `tests/nucleo/test_lote_*`
  y `POST` idéntico con el perfil predeterminado.
- **Lote por filas:** plan de N filas en orden (CA-C08.1); VMID fijo libre/ocupado/repetido y salto de
  explícitos (CA-C08.3); nodo fijo elegible/no elegible/fuera de línea y descuento de lo asignado
  (CA-C08.4); espacio heterogéneo por clave y compartido (CA-C08.5); `filas_excedentes` (CA-C08.6);
  una fila = `POST` de M1 (CA-C08.11); `plantilla` absurda sin efecto; reintento por filas
  (CA-C08.10); simulación solo GET (CA-C08.9). **INV-L1 repetida sobre lote por filas**: la suite de
  inyección de fallos de `test_lote_inyeccion_fallos.py` parametrizada con un plan por filas
  heterogéneo (fallo en cada punto, ≤ 1 POST por VMID), más pausa, cancelación y rollback.
- **Archivos:** límites (archivo disperso de 2 GB creado con `truncate`, sin ocupar disco), tubería
  con nombre, directorio, enlace simbólico, sin permiso; JSON con NaN, `1e999`, claves repetidas, 500
  niveles, cadena de 10 MB, `\u0000`, BOM; esquema con cada tipo erróneo de §13.7 de los requisitos;
  envoltura (formato ajeno, versión 0/negativa/bool/futura, cadena de migraciones); escritura atómica
  con fallo inyectado en `write`, `fsync` y `os.replace`; permisos 0600/0700 con `stat`; hash
  antes/después (INV-M3).
- **Fuzz (CA-X02.11):** 10 000 entradas mutadas (semilla fija, sin dependencias nuevas) sobre
  `leer_perfiles`, `leer_lote` y `leer_tabla`+`interpretar`: solo `ErrorProxLaunch` o resultado; sin
  lecturas sobre el límite (lector espiado) ni sockets (pytest-socket).
- **CSV:** cada caso de §13.10–13.13 de los requisitos; separador y codificación; numeración de filas
  como Excel; unidades (tabla parametrizada de §13.11); precedencia perfil/columna (propiedad,
  CA-C13.5); 10 000 valores con disparadores releídos con `csv.reader` (CA-C11.9); plantilla
  autovalidada; CSV de errores reimportable y sin columnas de credenciales.
- **Perfiles:** lista blanca y ausencia de `vmid/nombre/nodo/etiquetas` (CA-P01.1, CA-P06.8);
  fábrica válidos contra mocks 8.0/8.x/9.x (CA-P02.3); predeterminado = `configuracion_por_defecto`
  (CA-P02.4); pistas en 2–3 nodos (RF-P06); almacén: corrupto, vacío, `[]`, versión futura, sin
  permiso, perfil malo entre buenos, ida y vuelta, dos instancias.
- **Centinela y privacidad (RNF-M03):** todo archivo escrito, log y mensaje.
- **Interfaz (pytest-qt):** INV-M6 tras cargar/importar; confirmaciones con foco en Cancelar;
  «(modificado)»; panel «no encaja» y «Usar otro…»; vista previa con 100 filas con error sin
  congelar (retraso del bucle < 200 ms); catálogo «[T]»; `accessibleName`.
- **Rendimiento:** CSV 1 MiB/100 filas ≤ 1 s de CPU; abrir/guardar lote de 100 filas ≤ 500 ms;
  aplicar perfil ≤ 100 ms; `tracemalloc` ≤ 5 × tamaño.
- **Laboratorio (solo con `PROXLAUNCH_LAB=1`, limpian lo que crean):** LAB-M3-01 (cada perfil de
  fábrica, incluido OVMF+q35), LAB-M3-02 (lote guardado: mismo plan; storage inexistente → cero
  POST), LAB-M3-03 (CSV heterogéneo Windows-1252 con `;`, VMID explícito libre y ocupado, nodo
  explícito, `config` por fila, etiquetas y rollback completo), LAB-M3-04 (catálogo de CPU; si no se
  confirma, `tipo_cpu` solo por formato).

## 14. Riesgos de diseño

1. **INV-L1 en por filas.** El motor no cambia, pero el planificador sí: un error en `repartir_filas`
   o en la combinación de VMIDs fijos/automáticos podría producir VMIDs repetidos en el plan. Defensa:
   V-M10 en capa 1, V-L05 y una comprobación nueva en `construir_plan` (VMIDs únicos o
   `ValueError`), más la suite de inyección repetida.
2. **Equivalencia del homogéneo.** Generalizar `repartir` puede alterar desempates. Mitigación: el
   homogéneo pasa por las mismas funciones con una sola firma de recursos y se compara contra las
   salidas actuales en toda la suite M2.
3. **`plantilla` informativa en por filas.** Un uso futuro descuidado de `definicion.plantilla`
   produciría resultados erróneos en silencio. Mitigación: prueba con plantilla absurda y regla
   documentada en el docstring de `DefinicionLote`.
4. **Sustitución silenciosa en el formulario.** Los combos de Qt pueden elegir el primer valor si el
   storage cargado no existe; violaría CA-G04.3. Requiere el cambio de `tabla_discos`/`tabla_redes`
   y una prueba de UI específica.
5. **Detección de separador/codificación.** Heurística; un CSV de una columna con comas en nombres o
   un UTF-16 sin BOM puede detectarse mal. Mitigación: aviso «ambiguo», selector manual en avanzado y
   E-M07 ante nulos.
6. **Nombres de perfiles de fábrica traducidos.** Al cambiar de idioma, un nombre de fábrica puede
   coincidir con uno del usuario; V-M06 pide entonces el nombre exacto o el id (CA-C13.4).
7. **Dos instancias / carpetas sincronizadas.** Última escritura gana; puede perderse un perfil
   creado en la otra instancia. Se documenta (requisitos §15.6).
8. **Tamaño de `ventana_principal.py` (2 322 líneas).** F4b concentra mucho cambio en un archivo; se
   mitiga sacando la lógica a `lote_filas.py`, `selector_perfil.py` y los diálogos de F4a.
9. **`version_proxmox` en el lote.** Es informativo; si un revisor lo considera dato del sitio, se
   puede retirar sin cambiar `version_formato` (campo opcional).

## 15. Decisiones técnicas y alternativas descartadas

- **D-T1 `DefinicionLote` + `filas` con valor por defecto** y `filas_efectivas` como camino único.
  Descartadas: un tipo `DefinicionLotePorFilas` aparte (obligaba a uniones de tipos en planificador,
  simulación, trabajadores e interfaz) y `plantilla: ConfiguracionVM | None` (cambia el orden de
  campos y ~15 llamadas).
- **D-T2 Motor intacto.** Toda la heterogeneidad se resuelve antes del `Plan`. Descartado: pasar
  filas al motor.
- **D-T3 VMIDs fijos comprobados aparte** y excluidos de la reserva automática; ocupado = error de
  fila, nunca reasignación. Descartado: meterlos en `reservar_vmids` (mezclaba semánticas de salto).
- **D-T4 Por filas solo con destino Automático** (+ nodo por fila), como fija §9.2 de los requisitos.
  Descartado: «Nodos elegidos» como filtro (no pedido, más casos de prueba).
- **D-T5 Capa 1 = `validar_vm` filtrado** contra un inventario vacío (`validar_sin_servidor`), sin
  reglas duplicadas (CA-P07.1). Descartado: refactorizar `validar_vm` en dos (riesgo de cambiar el
  orden de problemas de M1).
- **D-T6 Perfil con modelo propio (`ConfigPerfil`)** en lugar de `ConfiguracionVM` con campos
  vacíos: el tipo impide guardar `vmid`, `nombre`, `nodo` o `etiquetas`.
- **D-T7 BOM UTF-8 tolerado al leer JSON** (Bloc de notas); se escribe sin BOM.
- **D-T8 V-M08 también en `memoria`** (`1.000` GiB es ambiguo).
- **D-T9 Avisos de unidad y decimal una vez por columna y archivo**, no por fila (evita 100 avisos
  iguales).
- **D-T10 Almacén propio con la misma envoltura** que los archivos exportados (`version_formato`
  hace de `version_esquema`): un solo lector y una sola cadena de migraciones.
- **D-T11 Sin dependencias nuevas**: `json`, `csv`, `fractions`, `unicodedata` de la biblioteca
  estándar; fuzz con `random` y semilla fija. Descartados `chardet`/`charset-normalizer` (detección
  no determinista y peso) y `hypothesis` (dependencia nueva).
- **D-T12 Lote homogéneo N=1 con prefijo vacío** guarda `nombre_maquina` para no perder el nombre.

---

## Anexo A · Firmas públicas del núcleo (MVP 3)

Todas puras salvo las marcadas «E/S». Los errores son `ErrorProxLaunch` con los códigos de §8.

**`nucleo/validacion.py`**
- `validar_sin_servidor(cfg: ConfiguracionVM, *, incluir_nombre: bool = False, incluir_vmid: bool = False) -> list[Problema]` — `validar_vm` contra inventario vacío filtrado a `CODIGOS_SIN_SERVIDOR` (V-05, V-06, V-07, V-07.sindisco, V-08, V-10..V-13, V-15, V-20, V-22, V-23, V-24; + V-01/V-02 si se piden).

**`nucleo/persistencia/rutas.py`** — `Rutas.perfiles_maquina -> Path` (`directorio_config/perfiles_maquina.json`); `Rutas.directorio_datos -> Path` (`user_data_dir`, o `base/datos`); `Rutas.lotes -> Path` (`directorio_datos/lotes`).

**`nucleo/archivos/`**
- `lector.leer_archivo_limitado(ruta: Path, limite: int) -> bytes` (E/S)
- `json_estricto.cargar_json_estricto(datos: bytes, *, profundidad_max: int = PROFUNDIDAD_JSON_MAX) -> object`
- `esquema.es_clave_credencial(nombre: str) -> bool`
- `esquema.LectorEsquema()`: `errores: list[ErrorCampo]`, `avisos() -> tuple[AvisoArchivo, ...]`,
  `objeto(valor: object, ruta: str, claves: frozenset[str]) -> dict[str, object] | None`,
  `entero(obj: Mapping[str, object], clave: str, ruta: str, *, minimo: int | None = None, maximo: int | None = None, nulo: bool = False, requerido: bool = True, defecto: int | None = None) -> int | None`,
  `booleano(obj, clave, ruta, *, requerido: bool = True, defecto: bool | None = None) -> bool | None`,
  `texto(obj, clave, ruta, *, minimo: int = 0, maximo: int = MAX_LONG_TEXTO, multilinea: bool = False, nulo: bool = False, requerido: bool = True, sin_token: bool = False) -> str | None`,
  `enumerado(obj, clave, ruta, tipo: type[E], *, requerido: bool = True, defecto: E | None = None) -> E | None`,
  `lista(obj, clave, ruta, *, maximo: int, requerido: bool = True) -> list[object] | None`,
  `fallar_si_errores() -> None` (lanza `ErrorArchivo(ARCHIVO_DANADO)`)
- `texto.texto_seguro(valor: str, *, maximo: int, multilinea: bool = False) -> str | None`
- `texto.contiene_token(texto: str) -> bool`
- `texto.validar_nombre(texto: str, *, maximo: int = LONG_NOMBRE_PERFIL) -> tuple[str, str | None]` — (normalizado, regla V-M01/V-M04/V-M05 o None)
- `texto.clave_comparacion(texto: str, *, sin_acentos: bool = False) -> str`
- `texto.nombre_archivo_seguro(base: str, extension: str) -> str`
- `envoltura.abrir_envoltura(dato: object, formato: str, *, version_soportada: int = VERSION_FORMATO, migraciones: Mapping[int, Migracion] | None = None) -> Envoltura`
- `envoltura.crear_envoltura(formato: str, contenido: Mapping[str, object], *, app_version: str) -> dict[str, object]`
- `envoltura.a_bytes_json(obj: Mapping[str, object]) -> bytes`
- `envoltura.MIGRACIONES: dict[str, dict[int, Migracion]]`; `Migracion = Callable[[dict[str, object]], dict[str, object]]`
- `esquema_config.config_perfil_a_dict(config: ConfigPerfil, *, con_pistas: bool) -> dict[str, object]`
- `esquema_config.leer_config_perfil(lector: LectorEsquema, valor: object, ruta: str) -> ConfigPerfil | None`
- `esquema_config.configuracion_a_dict(cfg: ConfiguracionVM) -> dict[str, object]` — sin vmid/nombre/nodo/etiquetas
- `esquema_config.leer_configuracion(lector: LectorEsquema, valor: object, ruta: str) -> ConfiguracionVM | None` — `vmid=0`, `nombre=""`, `nodo=""`
- `escritura.escribir_atomico(ruta: Path, datos: bytes) -> None` (E/S)
- `csv_seguro.DISPARADORES: frozenset[str]`; `sanear_celda(valor: str) -> str`;
  `texto_csv(encabezado: Sequence[str], filas: Iterable[Sequence[str | int]], *, separador: str = ";") -> bytes`;
  `escribir_csv(ruta: Path, encabezado: Sequence[str], filas: Iterable[Sequence[str | int]], *, separador: str = ";") -> None` (E/S)

**`nucleo/perfiles_maquina/`**
- `fabrica.CLAVES_FABRICA: tuple[str, ...]`; `perfiles_fabrica(textos: Mapping[str, tuple[str, str]] | None = None) -> tuple[PerfilMaquina, ...]`
- `validacion.validar_nombre_perfil(nombre: str, existentes: Iterable[PerfilMaquina], *, excluir_id: str | None = None) -> tuple[str, list[Problema]]`
- `validacion.validar_config_perfil(config: ConfigPerfil) -> list[Problema]`
- `validacion.nombre_libre(base: str, existentes: Iterable[PerfilMaquina]) -> str`
- `validacion.id_valido(id_perfil: str, *, permitir_fabrica: bool = False) -> bool` (V-M02)
- `aplicar.AvisoPista(recurso: str, pedido: str, usado: str | None, nodo: str)`; `aplicar.ResultadoAplicacion(cfg: ConfiguracionVM, avisos: tuple[AvisoPista, ...])`
- `aplicar.aplicar_perfil(perfil: PerfilMaquina, actual: ConfiguracionVM, inv: Inventario) -> ResultadoAplicacion`
- `aplicar.aplicar_config(config: ConfigPerfil, actual: ConfiguracionVM, inv: Inventario | None) -> ResultadoAplicacion` — base de la anterior; sin inventario deja las pistas como valor (CSV sin conexión)
- `aplicar.config_desde_configuracion(cfg: ConfiguracionVM, *, con_pistas: bool) -> ConfigPerfil`
- `aplicar.hardware_igual(a: ConfiguracionVM, b: ConfiguracionVM) -> bool`
- `aplicar.ResumenPerfil(vcpus: int, memoria_mib: int, discos_gib: tuple[int, ...], redes: int)`; `aplicar.resumen_perfil(config: ConfigPerfil) -> ResumenPerfil`
- `compatibilidad.funciones_requeridas(config: ConfigPerfil) -> frozenset[Funcion]`
- `compatibilidad.evaluar_compatibilidad(cfg: ConfiguracionVM, config: ConfigPerfil, inv: Inventario, caps: Capacidades, *, requeridas: Callable[[ConfigPerfil], frozenset[Funcion]] = funciones_requeridas) -> list[Problema]`
- `formato.PerfilLeido(indice: int, nombre: str, descripcion: str, config: ConfigPerfil)`; `PerfilInvalido(indice: int, nombre: str | None, errores: tuple[ErrorCampo, ...])`; `ArchivoPerfiles(validos, invalidos, avisos)`
- `formato.perfiles_a_bytes(perfiles: Sequence[PerfilMaquina], *, con_pistas: bool, app_version: str) -> bytes`
- `formato.leer_perfiles(datos: bytes) -> ArchivoPerfiles`
- `formato.leer_archivo_perfiles(ruta: Path) -> ArchivoPerfiles` (E/S)
- `formato.exportar_perfiles(ruta: Path, perfiles: Sequence[PerfilMaquina], *, con_pistas: bool, app_version: str) -> None` (E/S)
- `almacen.AccionImportar(StrEnum)`: `CONSERVAR_AMBOS`, `REEMPLAZAR`; `almacen.EntradaImportacion(perfil: PerfilLeido, accion: AccionImportar = CONSERVAR_AMBOS, reemplaza_id: str | None = None)`
- `almacen.EstadoAlmacen(solo_lectura: bool, hubo_corrupcion: bool, copia_danada: Path | None, error_lectura: bool, descartados: tuple[ErrorCampo, ...], avisos: tuple[AvisoArchivo, ...])`
- `almacen.AlmacenPerfilesMaquina(ruta: Path, *, fabrica: Sequence[PerfilMaquina], generador_id: Callable[[], str] = <uuid4().hex>, ahora: Callable[[], datetime] = datetime.now, app_version: str = proxlaunch.__version__)`:
  `cargar() -> EstadoAlmacen` (E/S), `estado -> EstadoAlmacen`, `todos() -> tuple[PerfilMaquina, ...]`,
  `usuario() -> tuple[PerfilMaquina, ...]`, `obtener(id_perfil: str) -> PerfilMaquina`,
  `buscar_por_nombre(nombre: str) -> list[PerfilMaquina]`,
  `crear(nombre: str, descripcion: str, config: ConfigPerfil) -> PerfilMaquina` (E/S),
  `actualizar(id_perfil: str, config: ConfigPerfil) -> PerfilMaquina` (E/S),
  `renombrar(id_perfil: str, nombre: str, descripcion: str | None = None) -> PerfilMaquina` (E/S),
  `duplicar(id_perfil: str, nombre: str) -> PerfilMaquina` (E/S),
  `eliminar(id_perfil: str) -> None` (E/S),
  `importar(entradas: Sequence[EntradaImportacion]) -> tuple[PerfilMaquina, ...]` (E/S, todo o nada)

**`nucleo/lotes_guardados/`**
- `formato.lote_a_dict(lote: LoteGuardado) -> dict[str, object]`
- `formato.lote_a_bytes(lote: LoteGuardado, *, app_version: str) -> bytes`
- `formato.leer_lote(datos: bytes) -> ArchivoLote`
- `formato.leer_archivo_lote(ruta: Path) -> ArchivoLote` (E/S)
- `formato.guardar_lote(ruta: Path, lote: LoteGuardado, *, app_version: str) -> None` (E/S)
- `revalidacion.TipoDesajuste(StrEnum)`: `STORAGE`, `STORAGE_EFI`, `BRIDGE`, `NODO`
- `revalidacion.Desajuste(tipo: TipoDesajuste, valor: str, indices: tuple[int, ...], campos: tuple[str, ...], disponibles: tuple[str, ...])` — `indices` vacío en homogéneo
- `revalidacion.desajustes(definicion: DefinicionLote, inv: Inventario) -> tuple[Desajuste, ...]`
- `revalidacion.sustituir(definicion: DefinicionLote, desajuste: Desajuste, nuevo: str | None) -> DefinicionLote` — `None` en `NODO` = Automático / nodo de fila vacío

**`nucleo/csv_importacion/`**
- `decodificacion.decodificar(datos: bytes, forzada: Codificacion | None = None) -> tuple[str, Codificacion]`
- `separador.detectar_separador(texto: str) -> DeteccionSeparador`
- `lectura.leer_tabla(datos: bytes, opciones: OpcionesCsv = OpcionesCsv()) -> TablaCsv`
- `lectura.leer_archivo_csv(ruta: Path, opciones: OpcionesCsv = OpcionesCsv()) -> TablaCsv` (E/S)
- `columnas.COLUMNAS: tuple[DefColumna, ...]`; `normalizar_encabezado(texto: str) -> str`;
  `resolver_columnas(encabezado: Sequence[str], *, alias_extra: Mapping[str, str] | None = None) -> tuple[MapaColumnas, tuple[AvisoArchivo, ...]]`
- `unidades.ValorInvalido(ValueError)` con `regla: str`, `params: dict[str, str]`;
  `memoria_mib(texto: str) -> tuple[int, frozenset[CodigoAvisoArchivo]]`;
  `disco_gib(texto: str) -> tuple[int | None, frozenset[CodigoAvisoArchivo]]` (`None` = sin disco);
  `entero(texto: str) -> int`; `firmware(texto: str) -> Firmware`; `modelo_red(texto: str) -> ModeloRed`
- `interpretacion.interpretar(tabla: TablaCsv, *, perfil_base: PerfilMaquina, perfiles: Sequence[PerfilMaquina], inv: Inventario | None, nodo_referencia: str | None, alias_extra: Mapping[str, str] | None = None) -> ResultadoImportacion`
- `interpretacion.filas_lote(resultado: ResultadoImportacion, numeros: Collection[int]) -> tuple[FilaLote, ...]` — `ValueError` si algún número tiene error o no existe
- `plantilla.ENCABEZADO_PLANTILLA: tuple[str, ...]`; `filas_plantilla() -> list[list[str | int]]`; `escribir_plantilla(ruta: Path, *, separador: str = ";") -> None` (E/S)
- `errores_csv.filas_con_error(tabla: TablaCsv, resultado: ResultadoImportacion, traducir: Callable[[ProblemaCelda], str]) -> tuple[list[str], list[list[str | int]]]`;
  `escribir_filas_con_error(ruta: Path, tabla: TablaCsv, resultado: ResultadoImportacion, traducir: Callable[[ProblemaCelda], str], *, separador: str = ";") -> None` (E/S)

**`nucleo/lote/`**
- `filas.filas_efectivas(definicion: DefinicionLote) -> tuple[FilaLote, ...]`
- `filas.validar_filas(definicion: DefinicionLote) -> list[Problema]` (V-L01, V-M07, V-M10, V-02, V-L13)
- `filas.definicion_por_filas(filas: Sequence[FilaLote], *, plantilla_base: ConfiguracionVM, algoritmo: Algoritmo = Algoritmo.EQUILIBRADO, vmid_inicial: int | None = None, etiquetar: bool = True, politica_thin: PoliticaThin = PoliticaThin.CONFIRMAR_CON_TOPE) -> DefinicionLote`
- `filas.sin_filas(definicion: DefinicionLote, indices: Collection[int]) -> DefinicionLote`
- `filas.reemplazar_fila(definicion: DefinicionLote, indice: int, fila: FilaLote) -> DefinicionLote`
- `filas.definicion_para_reintento(definicion: DefinicionLote, elementos: Sequence[ElementoPlan]) -> DefinicionLote`
- `planificador.usa_nombre_de_plantilla(definicion)` — falso en por filas (firma de M2)
- `planificador.validar_definicion(definicion, inv, version_validacion)` / `construir_plan(...)` — firmas de M2 sin cambios
- `Planificador.reservar_vmids(inicio: int, cantidad: int, *, excluir: frozenset[int] = frozenset()) -> tuple[list[int], list[int]]` (E/S)
- `Planificador.comprobar_vmids(vmids: Sequence[int]) -> dict[int, bool]` (E/S, solo GET)
- `reparto.repartir_filas(filas: Sequence[FilaLote], destino: Destino, inv: Inventario, *, por_filas: bool = False) -> tuple[list[str], dict[str, tuple[int, MotivoReparto]], list[Problema]]`
- `reparto.repartir(definicion, inv, cantidad)` — firma de M2 sin cambios
- `presupuesto.uso_de_filas(filas: Sequence[FilaLote], nodos: Sequence[str], inv: Inventario) -> dict[ClavePresupuesto, UsoStorage]`
- `presupuesto.filas_que_exceden(elementos: Sequence[ElementoPlan], inv: Inventario, politica: PoliticaThin) -> tuple[int, ...]`

**Interfaz (públicas usadas entre F4a y F4b)**
- `archivos_ui.elegir_para_abrir(parent: QWidget, tipo: TipoArchivo) -> Path | None`; `elegir_para_guardar(parent: QWidget, tipo: TipoArchivo, nombre_sugerido: str, carpeta: Path | None = None) -> Path | None`; `TipoArchivo(StrEnum)`: `PERFILES`, `LOTE`, `CSV`
- `formulario_vm.FormularioVM.aplicar_hardware(cfg: ConfiguracionVM) -> None`
- `bloque_lote.BloqueLote.establecer_definicion(definicion: DefinicionLote) -> None`
- `informe_lote.datos_maquinas(informe: InformeLote) -> list[DatosMaquina]`; `guardar_informe_csv(ruta: Path, informe: InformeLote) -> None`
- `dialogos.importar_csv.DialogoImportarCsv(parent, *, perfiles: Sequence[PerfilMaquina], perfil_base_id: str, inv: Inventario | None, nodo_referencia: str | None, lanzador: Lanzador)`: `ejecutar() -> tuple[ResultadoImportacion, tuple[int, ...]] | None`
- `dialogos.lote_no_encaja.PanelLoteNoEncaja`: señal `sustitucion_pedida(object, object)` (`Desajuste`, `str | None`)
