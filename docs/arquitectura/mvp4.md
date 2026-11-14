# Arquitectura del MVP 4 — Origen del sistema operativo (ISO, importación, clon) (ProxLaunch)

Versión 0.1 (2026-11-14) · Autor: orquestador (borrador) · Estado: borrador para revisión; pendiente de
aprobación antes de F4

Fuentes: `docs/requisitos/mvp4.md` (RF-O01..O32, RNF-O01..O15, V-O01..O30, E-O01..E-O24, INV-O1..O12,
LAB-M4-01..14, §14 enmiendas, §15 DT-O1..O17, §16 riesgos); `docs/decisiones.md` (D-17, D-18, D-19, D-20,
D-21, D-22, D-23, **D-24** puntos 1–8 y **D-25**: clon automático, 3 perfiles de fábrica nuevos, hasta 3
clones enlazados por nodo sujeto a LAB-M4-10, DT-O1..O17 y enmiendas §14 aprobadas, aviso RHEL 10);
`docs/investigacion/mvp4-origen-so.md` (**I4**, base técnica: toda llamada a la API de este documento se
cita con su sección I4-§A..§H); `docs/arquitectura/mvp1.md`, `mvp2.md` y `mvp3.md` (estilo y su §11/Anexo B:
manda el código final); y el código de `src/proxlaunch` en `HEAD` (commit `4003478`). Se mantiene la
separación de los MVP anteriores: **núcleo sin Qt** que devuelve `CodigoError`/`Problema` e **interfaz
PySide6** que traduce; dependencias inyectadas (reloj, transporte, rutas); sin secretos en logs.

> Regla de lectura: las firmas exactas están en el **Anexo A**; el texto de cada sección explica
> responsabilidades y comportamiento. Si una firma del anexo y el texto difieren, manda el anexo y se
> corrige el texto. Python ≥ 3.11: alias de tipo con `typing.TypeAlias`, nunca la sentencia `type`
> (PEP 695).


> **Resoluciones del orquestador sobre el borrador (2026-11-14):**
> 1. **C4 (storage de discos con varios candidatos):** se aplica D-24.6 tal como la eligió el usuario: la
>    primera vez que hace falta un storage de un tipo (también `images` con disco vacío) y hay varios
>    candidatos, se pregunta **una vez por servidor** y se recuerda en el perfil de conexión. El diálogo
>    preselecciona el de mayor espacio libre (comportamiento del MVP 3) y se puede cerrar aceptando esa
>    propuesta; el POST con disco vacío no cambia (equivalencia M3).
> 2. **C2 (propiedad para deshacer clones):** aprobada la regla ampliada: etiqueta **o** (UPID propio + no
>    rescatada + nombre igual). Nunca se borra el VMID de la plantilla.
> 3. **C1 (INV-O5):** enmendado: además de la cabecera de 1 KiB se pueden leer los 5 bytes de la firma
>    `CD001` en 0x8001.
> 4. **C3, C5, C6, C7** y los ajustes de código de §1.1: se aceptan las propuestas del borrador.
> 5. **F4-0** (contratos) lo ejecuta un `implementador` bajo brief del orquestador, que revisa el resultado
>    antes de lanzar F4a–F4c.

## 1. Hechos del código que condicionan el diseño

1. **`descubrir_nodo` descarta los storages sin `images`** (`servicios/descubrimiento.py`, línea 34): hoy
   `Inventario.storages` nunca contiene un storage solo de `iso` o `import`. `ClienteProxmox.storages`
   ya devuelve **todos** con su `content`. → Se añade `Inventario.storages_todos` rellenado con la misma
   respuesta (cero GET nuevos) y `Inventario.storages` sigue igual (equivalencia M1–M3).
2. **`PERMISOS_POR_RUTA` bloquea el plan** (`servicios/conexion.py:53`, `planificador.py:527`): todo
   privilegio que se añada ahí genera `PERMISOS_INCOMPLETOS` y, para `VM.Allocate`, V-L16. Si se
   añadieran los 4 privilegios nuevos, el rol de 10 del MVP 3 recibiría avisos y la UI cambiaría
   (contradice CA-O24.4). → Los 4 nuevos van en una tabla aparte (`PERMISOS_ORIGEN`) evaluada **por vía**.
3. **El rollback exige la etiqueta del lote** cuando `etiquetado` (`rollback._motivo_omision`): un clon
   cuyo `PUT` de etiquetas falló (PARCIAL «clonada, sin etiqueta») se **omitiría** como `ROLLBACK_NO_PROPIA`,
   lo que contradice CA-O22.5. → Regla de propiedad ampliada para clones (§9, D-A6).
4. **La reconciliación solo reconoce `lock: create`** (`reconciliacion.config_en_creacion`); un clon en
   curso tiene `lock: clone` (I4-§D). → Se amplía a `{"create", "clone"}`.
5. **`ServicioCreacion` fija la espera máxima por instancia** (`max_espera_s`, 600 s) y sondea la tarea en
   `cfg.nodo`. Importar y clonar completo necesitan una espera proporcional al tamaño (CA-O17.4) y un clon
   con `target` corre en el **nodo de la plantilla**. → Espera por llamada y nodo de sondeo tomado del UPID.
6. **`ResultadoSimulacion.peticiones` es `{vmid: params del POST}`**: un clon envía hasta 3 peticiones
   (`clone`, `PUT config`, `PUT resize`). → Campo nuevo `peticiones_detalle` con valor por defecto.
7. **`construir_parametros` numera los discos por bus con un contador** (`ide0`, `ide1`…). Con ISO, `ide0` e
   `ide2` quedan reservados (DT-O2). → Tabla de ranuras IDE solo cuando el origen es `iso`.
8. **`crear_envoltura` siempre escribe `VERSION_FORMATO`** (`archivos/envoltura.py:93`) y
   `abrir_envoltura` usa la misma constante como versión soportada. → Se separan «versión que se lee»
   (pasa a 2) y «versión que se escribe» (1 o 2 según DT-O15, parámetro explícito).
9. **Choque de nombres: `origen` ya existe dos veces.** `FilaLote.origen` (y la clave `origen` de
   `por_filas.filas[i]` en el archivo de lote) es el **número de fila del CSV**; `PerfilMaquina.origen` es
   `fabrica`/`usuario`. El origen del SO vive en `ConfiguracionVM.origen` (y en la clave `config.origen` de
   los archivos). → No se renombra nada; los campos nuevos usan `detalle_origen` y la documentación lo
   advierte. Ningún campo nuevo se llama `origen`.
10. **`MAX_LONG_NOMBRE_ARCHIVO = 80` ya existe** en `archivos/texto.py` (nombres de archivos locales que la
    app escribe). La constante de requisitos §10 (100, nombres de volumen) se llama
    `MAX_LONG_NOMBRE_VOLUMEN` para no chocar.
11. **El transporte solo sabe enviar formularios** (`data=dict` codificado
    `x-www-form-urlencoded`, `transporte.py:_enviar`) y el protocolo `Transporte` tiene un único método
    `peticion`. → Protocolo **adicional** `TransporteSubida` (no se toca `Transporte`: los dobles de prueba
    existentes siguen valiendo).
12. **`requests` con un cuerpo iterable sin longitud usa `Transfer-Encoding: chunked`**, y Proxmox exige
    `Content-Length` (I4-§B «upload without content length header not supported»). Si el objeto del cuerpo
    define `__len__`, `requests` pone `Content-Length` y envía iterando. → Generador multipart propio con
    `__len__`: **sin dependencia nueva** (D-A2).
13. **`POOL_MAXSIZE = 8 + 4`** (`transporte.py:33`) dimensiona las conexiones por host para 1 creación por
    nodo. Con 3 clones enlazados por nodo en 4 nodos hacen falta más. → `POOL_MAXSIZE` se recalcula (§10).
14. **El motor procesa 1 MV por nodo** (`motor._procesar_cola`, una cola secuencial por nodo). CA-O21.6
    (3 enlazados por nodo) y CA-O17.10 (≤ 2 pesadas por storage destino) obligan a tocar el motor: es el
    único cambio de concurrencia; el resto del motor no cambia (D-A5).
15. **El camino de creación de una sola MV (M1) no pasa por el `Planificador`**
    (`ventana_principal._crear` → `ServicioCreacion.crear`). → La resolución del origen, la revalidación de
    la fuente (INV-O8) y las reglas V-O de capa 2 viven en el núcleo (`validar_vm` y `ServicioCreacion`),
    no solo en el planificador.
16. **`validar_vm` emite V-20 para todo origen ≠ `disco_vacio`** y `validar_sin_servidor` lo incluye en
    `CODIGOS_SIN_SERVIDOR`. → V-20 se retira (enmienda 14.1) y se sustituye por V-O01.
17. **`capacidades.TABLA` tiene `IMPORTAR_DISCO` en (8, 2) como ejemplo** (enmienda 14.6) → (8, 4).
18. **Los errores de `requests` y el cuerpo de un 400 pueden contener la URL completa** (p. ej. el
    `download-url` que repite el parámetro, o el log de la tarea `download`, que muestra la URL). `enmascarar`
    oculta secretos, no URLs. → Saneo específico de la URL antes de guardar `detalle_tecnico` o líneas de log
    (INV-O6, §9).
19. **`ventana_principal.py` tiene 3 352 líneas.** El MVP 4 añade mucho flujo de interfaz; se concentra en
    un controlador nuevo (`interfaz/controlador_origen.py`) para que la ventana solo lo enlace.
20. **El laboratorio no tiene salida a Internet** (solo 127.0.0.1, memoria del proyecto): LAB-M4-06/07
    necesitarán un servidor HTTP local en el nodo anidado o se documentan como no verificables.

### 1.1 Contradicciones encontradas entre requisitos, decisiones y código (con propuesta)

| # | Contradicción | Propuesta (ver §15) |
|---|---|---|
| C1 | INV-O5 limita la lectura del archivo local a la cabecera (≤ 1 KiB), pero V-O10 pide comprobar la firma ISO 9660 `CD001` en el desplazamiento 0x8001 (32 769). | Leer ≤ 1 KiB de cabecera **más** 5 bytes en 0x8001 solo para ISO (un `seek` + `read(5)`). Enmendar INV-O5: «cabecera (≤ 1 KiB) y, para ISO, la firma de 5 bytes en 0x8001». |
| C2 | CA-O22.5 dice que un clon sin etiqueta es elegible para rollback «por estar en el libro con su UPID», pero el rollback de M2 exige la etiqueta del lote cuando el lote etiqueta. | Para elementos de origen `clonar_plantilla`: propia = etiqueta del lote **o** (UPID propio de la tarea `qmclone`, no rescatada por reconciliación y `name` igual al del plan). Es la misma prueba que M2 ya acepta con «sin etiquetas» (D-A6). |
| C3 | CA-O20.4 cita `format` en «dir/nfs/cifs/btrfs según V-09», pero V-09 (`TIPOS_STORAGE_QCOW2`) y I4-§H dicen que btrfs solo admite `raw`. | Manda V-09 (+ `formatos` de la API cuando existan, CA-O04.6): en btrfs no se envía `format`. |
| C4 | CA-O05.2 (preguntar si hay varios candidatos) aplicado a `images` cambiaría el flujo de disco vacío de M1–M3 (hoy elige «mayor libre» sin preguntar) y CA-O03.1/O05.6 piden el comportamiento del MVP 3. | Ver **Pregunta 1** del reporte: preguntar por `storage_mv` solo cuando un origen nuevo lo necesita; con disco vacío seguir «mayor libre» y ofrecer «Recordar» sin diálogo modal. |
| C5 | CA-O10.7 distingue mayúsculas «solo si el storage es sensible». La app no puede saberlo con certeza. | Comparar **siempre** sin distinguir mayúsculas (lo permite «ante la duda»): nunca hay sobrescritura y el coste es pedir otro nombre. |
| C6 | RF-O12/RNF-O03 exigen cancelar una subida en ≤ 2 s; con un socket bloqueado en `sendall` (servidor que no lee) Python no interrumpe la escritura hasta el timeout. | Bloques de envío de 64 KiB, cancelación comprobada entre bloques y timeout de escritura; peor caso documentado como riesgo R3 y medido en LAB-M4-14 (D-A3). |
| C7 | CA-O13.8 permite cambiar `ostype` en avanzado como campo propio; el modelo deriva `ostype` de `tipo_so`. | `ostype` se deriva siempre de `tipo_so` (el avanzado elige `tipo_so`, incluido `otro` → `other`); evita combinaciones incoherentes (`win11` con «Linux»). |

## 2. Módulos nuevos y cambios

```
src/proxlaunch/nucleo/
  errores.py                  + códigos E-O (§8)                                             [F4-0]
  capacidades.py              + DESCARGAR_URL (8,2), IMPORTAR_DISCO → (8,4), SUBIR_IMAGEN_DISCO (8,4),
                              TPM_CLON_COMPLETO (8,4), CLAVES_MS_2023 (9,1); sin «EJEMPLO»       [F4-0]
  modelos/vm.py               OrigenSO con 4 valores; ConfiguracionVM + tipo_so, tpm, agente_qemu,
                              detalle_origen (al final, con valor por defecto)                  [F4-0]
  modelos/origen.py           (NUEVO) TipoSO, ModoClon, RefVolumen, RefPlantilla, AjustesClon,
                              DetalleIso, DetalleImportacion, DetalleClon, DetalleOrigen        [F4-0]
  modelos/catalogo.py         (NUEVO) Contenido, Volumen, DiscoPlantilla, DetallePlantilla,
                              Plantilla, ListadoStorage, PermisosEfectivos, CatalogoServidor    [F4-0]
  modelos/inventario.py       Storage + formatos; Inventario + storages_todos, catalogo         [F4-0]
  modelos/conexion.py         PerfilConexion + storage_mv, storage_iso, storage_import          [F4-0]
  modelos/tarea.py            Etapa.AJUSTANDO; ResultadoCreacion + avisos                       [F4-0]
  origen/                     (NUEVO) lógica PURA del origen (sin E/S ni Qt)
    __init__.py, constantes.py   constantes de §10 de los requisitos                            [F4-0]
    nombres.py                lista blanca de volids y nombres (V-O02, V-O03, V-O09, INV-O7)   [F4a]
    permisos.py               PERMISOS_ORIGEN, tiene_privilegio, privilegios por petición      [F4a]
    storages.py               clasificar por contenido, decidir/recordar storage (RF-O04..O06) [F4a]
    capacidades_origen.py     Via, EstadoVia, CapacidadesOrigen, calcular_capacidades (RF-O02) [F4a]
    asistente.py              TABLA_SO, aplicar_asistente (RF-O13), mínimos (V-O07)            [F4a]
    clon.py                   modo efectivo, petición de clon, ajustes tras clonar, parseo de
                              la config de la plantilla (RF-O20..O22)                         [F4a]
    resolucion.py             resolver_origen por nodo, elegibilidad V-O25, firma, espera,
                              necesidades de catálogo (RF-O07, O17, O19, O23)                  [F4a]
    validacion_origen.py      V-O01..V-O30 en capa 1 y capa 2                                   [F4a]
  constructor_peticion.py     + ide2/ide0/boot/ostype/tpmstate0/agent/import-from; ranuras IDE  [F4a]
  validacion.py               V-20 → V-O01; validar_vm llama a validar_origen*; códigos capa 1  [F4a]
  valores_defecto.py          + storage por defecto con recordado (CA-O05.5)                    [F4a]
  perfiles_maquina/           modelos (ConfigPerfil + campos de origen como pista), fabrica (+3),
                              aplicar (pistas de origen), compatibilidad (IMPORTAR_DISCO),
                              validacion, formato (v2 solo si hace falta)                      [F4a]
  archivos/constantes.py      VERSION_FORMATO = 2 (lectura) + VERSION_FORMATO_BASE = 1          [F4a]
  archivos/envoltura.py       crear_envoltura(version_formato=…), MIGRACIONES v1→v2 identidad  [F4a]
  archivos/esquema_config.py  lista blanca de tipo_so/tpm/agente_qemu/detalle_origen           [F4a]
  lotes_guardados/            formato (v2 solo si hace falta), revalidacion (+ISO, IMAGEN,
                              DRIVERS, PLANTILLA)                                               [F4a]
  csv_importacion/            columnas (+origen, fuente, so, virtio, modo_clon), unidades (enums),
                              interpretacion (origen por fila), plantilla (fila por origen)     [F4a]
  persistencia/perfiles.py    lee/escribe los 3 storages recordados (tipo str|None)            [F4a]
  api/multipart.py            (NUEVO) ParteArchivo, CuerpoMultipart (streaming, __len__)       [F4b]
  api/transporte.py           + TransporteSubida, TransporteHttp.subir, POOL_MAXSIZE            [F4b]
  api/solo_lectura.py         TransporteSoloLectura.subir → ESCRITURA_EN_SIMULACION             [F4b]
  api/cliente.py              + storages(con_formatos), contenido_storage, plantillas_visibles,
                              clonar_vm, configurar_vm, ampliar_disco, subir_archivo,
                              metadatos_url, descargar_url                                     [F4b]
  api/traductor_errores.py    + patrones de clone, import-from, upload, download-url (§8)      [F4b]
  transferencias/             (NUEVO) subir y descargar (RF-O09..O12, O16, O25)
    modelos.py                Destino, Comprobacion, Progreso, Resultado, Registro (sin URL)   [F4-0]
    archivo_local.py          apertura segura, inspección de cabecera, sha256 por bloques      [F4b]
    url.py                    validar_url (V-O11), validar_checksum (V-O12), ocultar_url        [F4b]
    progreso.py               MedidorProgreso (media móvil, reloj inyectado), progreso_de_log  [F4b]
    servicio.py               ServicioTransferencias: comprobar, subir, consultar, descargar,
                              verificar; una a la vez (V-O27)                                  [F4b]
  servicios/catalogo.py       (NUEVO) ServicioCatalogo: listados, plantillas, formatos, fuente
                              vigente (solo GET)                                               [F4b]
  servicios/conexion.py       permisos_faltantes_detalle(permisos=…), leer_permisos;
                              _tiene_privilegio delega en origen/permisos                     [F4b]
  servicios/descubrimiento.py descubrir rellena storages_todos y catalogo(permisos) sin GET extra [F4b]
  servicios/creacion.py       crear despacha POST/clon; revalida fuente (INV-O8); ajustes y
                              ampliación; espera proporcional; reintentar_ajustes               [F4c]
  lote/constantes.py          + CONCURRENCIA_ENLAZADO_POR_NODO, CONCURRENCIA_PESADA_POR_STORAGE  [F4-0]
  lote/modelos.py             EstadoMV.AJUSTANDO; Plan.catalogo; ResultadoSimulacion +
                              peticiones_detalle; PeticionSimulada; InformeLote + transferencias [F4-0]
  lote/cupos.py               (NUEVO) ClaseCarga, CuposEjecucion (≤1 normal/pesada por nodo,
                              ≤3 enlazados por nodo, ≤2 pesadas por storage destino)          [F4c]
  lote/motor.py               colas por nodo con carriles + cupos; inventario con catálogo;
                              avisos del resultado al libro                                    [F4c]
  lote/planificador.py        lee catálogo si hay origen; resuelve origen por elemento; V-O*  [F4c]
  lote/reparto.py             elegibilidad por origen (V-O25) y firma con origen               [F4c]
  lote/presupuesto.py         pedido por origen (T×N, X×N, clon completo, enlazado ≈ 0, TPM)   [F4c]
  lote/reconciliacion.py      lock clone; propiedad de clon                                    [F4c]
  lote/rollback.py            propiedad de clon (C2); nunca la plantilla                        [F4c]
  lote/simulacion.py          peticiones de clon/config/resize como texto                       [F4c]
  lote/informe.py             origen por MV; archivos transferidos en la sesión                 [F4c]
  lote/ajustes.py             (NUEVO, Debería) reintentar ajustes de MVs PARCIAL del libro      [F4c]
  lote/filas.py, libro.py, politica_pausa.py, nombres.py: SIN CAMBIOS

src/proxlaunch/interfaz/
  controlador_origen.py       (NUEVO) estado del origen de la sesión: catálogo, capacidades,
                              storages recordados, transferencias, registro de la sesión       [F5b]
  modelos_tabla_origen.py     (NUEVO) ModeloCatalogoVolumenes, ModeloPlantillas (filas
                              deshabilitadas con motivo)                                       [F5a]
  vistas/selector_origen.py   (NUEVO) «¿Cómo quieres crear la máquina?» + fuente + SO + drivers
                              + modo de clon + ajustes                                         [F5a]
  dialogos/catalogo.py        (NUEVO) elegir ISO, imagen o plantilla; «Subir…», «Descargar…»   [F5a]
  dialogos/transferencia.py   (NUEVO) DialogoSubida, DialogoDescarga (progreso, cancelar,
                              dejar de esperar)                                                [F5a]
  dialogos/transferencias_sesion.py (NUEVO) archivos subidos en la sesión (copiar/guardar)     [F5a]
  dialogos/elegir_storage.py  (NUEVO) «¿Cuál usar siempre en este servidor?» + Recordar         [F5a]
  dialogos/capacidades.py     (NUEVO) qué puedo hacer en este servidor + texto para el admin   [F5a]
  ventana_principal.py, trabajadores.py, vistas/formulario_vm.py, tabla_discos.py,
  vistas/resumen.py, resumen_lote.py, bloque_lote.py, dialogos/conexion.py                     [F5b]
  textos.py, ayuda.py, recursos/traducciones/*.ts, informe_lote.py, modelos_tabla.py,
  vistas/progreso.py, progreso_lote.py, lote_filas.py, dialogos/guia_token.py, guardar_perfil.py,
  importar_csv.py, lote_no_encaja.py, deshacer.py, informe.py                                  [F5c]
```

`pyproject.toml`: **sin cambios** (D-A2: ni `requests-toolbelt` ni otra dependencia).

## 3. Modelos

Los modelos nuevos son `@dataclass(frozen=True)`, salvo los campos nuevos de `ConfiguracionVM`,
`PerfilConexion` e `Inventario`, que conservan la mutabilidad de su clase (M1). Todo campo nuevo va **al
final y con valor por defecto**: los constructores actuales (posicionales o con nombre) siguen siendo
válidos y las pruebas de M1–M3 no cambian.

### 3.1 El origen dentro de `ConfiguracionVM` (`nucleo/modelos/vm.py`, `modelos/origen.py`)

```python
class OrigenSO(StrEnum):
    DISCO_VACIO = "disco_vacio"; ISO = "iso"
    IMPORTAR_DISCO = "importar_disco"; CLONAR_PLANTILLA = "clonar_plantilla"

class TipoSO(StrEnum):
    LINUX = "linux"; WINDOWS_11 = "windows_11"
    WINDOWS_SERVER_2022_2025 = "windows_server_2022_2025"; WINDOWS_10 = "windows_10"
    WINDOWS_SERVER_2016_2019 = "windows_server_2016_2019"; OTRO = "otro"

class ModoClon(StrEnum): AUTOMATICO = "automatico"; ENLAZADO = "enlazado"; COMPLETO = "completo"

@dataclass(frozen=True)
class RefVolumen:            # fuente de archivo del servidor
    nombre: str = ""          # nombre de archivo sin storage ("alpine.iso"); "" = sin elegir
    volid: str | None = None  # "local:iso/alpine.iso" cuando está resuelto o el usuario lo escribió

@dataclass(frozen=True)
class RefPlantilla:
    nombre: str = ""          # referencia en archivos y CSV (DT-O13)
    vmid: int | None = None   # pista (lote guardado) o resuelto (plan)
    nodo: str | None = None   # resuelto por el plan; nunca se guarda

@dataclass(frozen=True)
class AjustesClon:            # None = «igual que la plantilla» (CA-O22.1)
    sockets: int | None = None; cores: int | None = None; tipo_cpu: str | None = None
    memoria_mib: int | None = None; disco_gib: int | None = None   # tamaño ABSOLUTO del principal

@dataclass(frozen=True)
class DetalleIso:
    iso: RefVolumen = field(default_factory=RefVolumen)
    drivers: RefVolumen | None = None   # None = detectar virtio-win (solo Windows, CA-O14.1)
    sin_drivers: bool = False           # «Crear sin los drivers» confirmado (CA-O14.3)

@dataclass(frozen=True)
class DetalleImportacion:
    imagen: RefVolumen = field(default_factory=RefVolumen)
    ampliar_a_gib: int | None = None            # CA-O18.4; None = tamaño de la imagen
    tamano_virtual_bytes: int | None = None     # sesión o API; NUNCA se escribe en archivos

@dataclass(frozen=True)
class DetalleClon:
    plantilla: RefPlantilla = field(default_factory=RefPlantilla)
    modo: ModoClon = ModoClon.AUTOMATICO
    ajustes: AjustesClon = field(default_factory=AjustesClon)
    storage_destino: str | None = None          # solo completo (avanzado); None = el de la plantilla
    modo_efectivo: ModoClon | None = None       # ENLAZADO/COMPLETO, lo fija el plan; no se guarda

DetalleOrigen: TypeAlias = DetalleIso | DetalleImportacion | DetalleClon

@dataclass
class ConfiguracionVM:        # campos de M1–M3 sin cambios y en el mismo orden, y al final:
    ...
    origen: OrigenSO = OrigenSO.DISCO_VACIO
    etiquetas: tuple[str, ...] = ()
    tipo_so: TipoSO | None = None               # NUEVO: None = sin asistente (M1–M3)
    tpm: bool = False                           # NUEVO: tpmstate0 v2.0 (DT-O6, DT-O8)
    agente_qemu: bool = False                   # NUEVO: agent=1 (CA-O13.11)
    detalle_origen: DetalleOrigen | None = None # NUEVO: obligatorio si origen ≠ disco_vacio (V-O01)
```

Reglas del modelo:
- **Coherencia** (V-O01, capa 1): `origen = disco_vacio` ⇔ `detalle_origen is None`; `iso` ⇔ `DetalleIso`;
  `importar_disco` ⇔ `DetalleImportacion`; `clonar_plantilla` ⇔ `DetalleClon`. `tipo_so`, `tpm` y
  `agente_qemu` solo se envían con `iso` o `importar_disco` (en `disco_vacio` y clon se ignoran con aviso
  `V-O01.ajeno`; no se envían). Un origen desconocido sigue dando `PARAMETRO_INVALIDO` con `campo=origen`
  desde `__post_init__` (CA-O01.5).
- **Clon**: `discos`, `con_disco`, `firmware`, `storage_efi`, `controlador_scsi` y `redes` de la
  configuración **se ignoran** (los da la plantilla, V-O29); `sockets`, `cores`, `tipo_cpu` y
  `memoria_mib` los fija el **plan** con el valor efectivo (ajuste o plantilla) para que presupuesto,
  memoria (V-L12), informe y libro muestren lo real; lo que se envía sale **solo** de `AjustesClon`.
- **`a_dict`/`desde_dict`** (ida y vuelta, CA-O01.5): las claves nuevas (`tipo_so`, `tpm`, `agente_qemu`,
  `detalle_origen`) solo se escriben si no tienen su valor por defecto (igual que `etiquetas` en M2):
  el `a_dict` de una configuración del MVP 3 es idéntico al de hoy. `desde_dict` las lee con `.get`.

### 3.2 Catálogo, permisos e inventario (`modelos/catalogo.py`, `modelos/inventario.py`)

```python
class Contenido(StrEnum): IMAGENES = "images"; ISO = "iso"; IMPORT = "import"

@dataclass(frozen=True)
class Volumen:
    volid: str; storage: str; contenido: Contenido; nombre: str      # nombre = parte tras "iso/"
    tamano_bytes: int | None; creado: int | None                     # ctime (epoch) si viene
    admitido: bool                                                   # pasa la lista blanca (V-O02/O03)

@dataclass(frozen=True)
class ListadoStorage:                 # resultado de listar UN storage en UN nodo
    nodo: str; storage: str; contenido: Contenido
    volumenes: tuple[Volumen, ...] = (); error: ErrorProxLaunch | None = None   # E-O05 por storage

@dataclass(frozen=True)
class DiscoPlantilla: clave: str; storage: str; tamano_bytes: int | None; formato: str | None

@dataclass(frozen=True)
class DetallePlantilla:               # de GET …/qemu/{vmid}/config (texto no confiable, parseado)
    es_plantilla: bool; bloqueo: str | None
    discos: tuple[DiscoPlantilla, ...]            # sin CD-ROM (media=cdrom); incluye efidisk0/tpmstate0
    bridges: tuple[str, ...]
    sockets: int | None; cores: int | None; tipo_cpu: str | None; memoria_mib: int | None
    etiquetas: frozenset[str]

@dataclass(frozen=True)
class Plantilla:                      # de GET /cluster/resources?type=vm con template = 1
    vmid: int; nombre: str; nodo: str; bloqueo: str | None
    disco_total_bytes: int | None; detalle: DetallePlantilla | None = None

@dataclass(frozen=True)
class PermisosEfectivos:              # GET /access/permissions (privilegios efectivos del token)
    rutas: Mapping[str, Mapping[str, int]]
    def tiene(self, privilegio: str, ruta: str) -> bool: ...

@dataclass(frozen=True)
class CatalogoServidor:
    permisos: PermisosEfectivos | None = None     # None = desconocidos (CA-O02.6)
    listados: tuple[ListadoStorage, ...] = ()
    plantillas: tuple[Plantilla, ...] | None = None   # None = aún no leídas
    formatos: Mapping[str, frozenset[str]] = field(default_factory=dict)  # storage → formatos API
    leido_en: float = 0.0                         # reloj inyectado (vigencia V-L14)

@dataclass(frozen=True)
class Storage:                        # campos de M1 sin cambios, y al final:
    formatos: frozenset[str] | None = None        # de ?format=1 si se pidió (CA-O04.6)

@dataclass
class Inventario:                     # campos de M1 sin cambios, y al final:
    storages_todos: dict[str, tuple[Storage, ...]] = field(default_factory=dict)  # todo contenido
    catalogo: CatalogoServidor | None = None
```

- `Inventario.storages` sigue conteniendo **solo** los storages con `images` (M1–M3 intactos);
  `storages_todos` lleva todos los de la misma respuesta de `GET /nodes/{n}/storage` (cero GET nuevos).
- Al conectar, `descubrir` deja `catalogo = CatalogoServidor(permisos=…)` con los permisos que ya se leían
  para RF-12 (una sola llamada a `/access/permissions`). Listados, plantillas y formatos se leen **bajo
  demanda** (al abrir el catálogo, al planificar o al revalidar un lote) con `ServicioCatalogo`.
- `Plan.catalogo` (§3.4) conserva el catálogo leído al planificar; el motor lo usa en la ejecución.

### 3.3 Capacidades de origen y storages (`origen/capacidades_origen.py`, `origen/storages.py`)

```python
class Via(StrEnum):
    ISO = "iso"; SUBIR_ISO = "subir_iso"; DESCARGAR_URL = "descargar_url"
    IMPORTAR = "importar"; SUBIR_IMAGEN = "subir_imagen"; DESCARGAR_IMAGEN = "descargar_imagen"
    CLONAR = "clonar"; ORDEN_ARRANQUE = "orden_arranque"; AMPLIAR_DISCO = "ampliar_disco"

class Disponibilidad(StrEnum): SI = "si"; NO = "no"; CON_AVISO = "con_aviso"

@dataclass(frozen=True)
class EstadoVia:
    via: Via; disponibilidad: Disponibilidad
    codigo: CodigoError | None = None             # E-O01, E-O02, E-O03, E-O17, E-O20…
    params: dict[str, str] = field(default_factory=dict)   # version, privilegio, ruta, candidatos, nodo
    id_ayuda: str = ""                            # RNF-O07 / CA-O02.9

@dataclass(frozen=True)
class CapacidadesOrigen:
    version: tuple[int, int]; forzada: bool; nodo: str | None
    vias: Mapping[Via, EstadoVia]
```

`calcular_capacidades(caps, inv, nodo)` es **pura** (RNF-O13) y combina:
- **Versión** solo por `caps.tiene(Funcion.X)` (CA-09.6): `IMPORTAR`/`SUBIR_IMAGEN`/`DESCARGAR_IMAGEN` exigen
  `IMPORTAR_DISCO`/`SUBIR_IMAGEN_DISCO` (8.4); `DESCARGAR_URL` con `Sys.AccessNetwork` exige `DESCARGAR_URL`
  (8.2); en 8.0–8.1 solo con `Sys.Modify` en `/` (I4-§B, CA-O02.4/5).
- **Permisos** (`inv.catalogo.permisos`, tabla `PERMISOS_ORIGEN` de §9): falta → `NO` con E-O20 y el
  privilegio/ruta; desconocidos → `CON_AVISO` («No se pudieron comprobar tus permisos»), salvo
  `ORDEN_ARRANQUE` y `AMPLIAR_DISCO`, que pasan a `NO` (CA-O02.6, INV-O10).
- **Storages** (`inv.storages_todos`): `ISO`/`SUBIR_ISO` exigen un candidato `iso`; `IMPORTAR` uno `import`
  (si no: E-O02 con `candidatos` = storages de tipos que podrían admitirlo según I4-§H, CA-O02.3).
- **Plantillas**: `CLONAR` es `SI` mientras no se hayan leído; leídas y vacías → `NO` con E-O17.

`CapacidadesOrigen` se recalcula al conectar, al cambiar de servidor o de versión forzada (CA-O02.7) y al
recargar el catálogo; solo usa datos ya leídos (INV-M1).

**Storages por contenido** (RF-O04..O06):

```python
class TipoDecision(StrEnum):
    UNICO = "unico"; RECORDADO = "recordado"; PREGUNTAR = "preguntar"
    RECORDADO_NO_DISPONIBLE = "recordado_no_disponible"; SIN_CANDIDATOS = "sin_candidatos"

@dataclass(frozen=True)
class DecisionStorage:
    tipo: TipoDecision; storage: str | None
    candidatos: tuple[str, ...]; recordado: str | None
```

- `candidatos(inv, contenido, nodo)`: storages de `storages_todos[nodo]` con el contenido **configurado**,
  activos y habilitados (CA-O04.1..O04.5); nunca por nombre. `contenido` ausente → no candidato.
- `decidir_storage(inv, contenido, nodo, recordado)`: recordado vigente → `RECORDADO`; recordado que no
  existe, inactivo, sin el contenido o fuera del nodo → `RECORDADO_NO_DISPONIBLE` (E-O04; **nunca** se
  sustituye, INV-O11); un candidato → `UNICO` (no se guarda, CA-O05.1); varios → `PREGUNTAR`; ninguno →
  `SIN_CANDIDATOS`.
- Precedencia del storage de un disco (CA-O05.5, función `storage_disco_por_defecto` en
  `valores_defecto.py`): mayor libre (M1) → recordado del perfil de conexión → pista del perfil de MV →
  valor del lote guardado o del CSV. Se guarda por **nombre de storage** (único en el clúster, CA-O05.10).

### 3.4 Lote (`nucleo/lote/modelos.py`)

```python
class EstadoMV(StrEnum):   # + AJUSTANDO (en curso), entre COMPROBANDO y los finales
    ...; AJUSTANDO = "ajustando"

class AccionPeticion(StrEnum):
    CREAR = "crear"; CLONAR = "clonar"; CONFIGURAR = "configurar"; AMPLIAR = "ampliar"

@dataclass(frozen=True)
class PeticionSimulada: accion: AccionPeticion; nodo: str; parametros: dict[str, str]

@dataclass(frozen=True)
class Plan:                # campos de M2/M3 sin cambios, y al final:
    catalogo: CatalogoServidor | None = None

@dataclass(frozen=True)
class ResultadoSimulacion: # campos de M2 sin cambios, y al final:
    peticiones_detalle: dict[int, tuple[PeticionSimulada, ...]] = field(default_factory=dict)

@dataclass(frozen=True)
class InformeLote:         # campos de M2/M3 sin cambios, y al final:
    transferencias: tuple[RegistroTransferencia, ...] = ()   # archivos subidos/descargados en la sesión
```

`ESTADOS_EN_CURSO` incluye `AJUSTANDO`. `ElementoPlan`, `EntradaLibro`, `Libro` y `FilaLote` **no
cambian**: el origen, la fuente resuelta y el modo efectivo viajan en `ElementoPlan.cfg.detalle_origen`
(CA-O30.1: «el libro registra origen, fuente y modo»). Los ajustes pendientes se registran como códigos en
`EntradaLibro.avisos` (`ajuste_pendiente:etiquetas|cpu_memoria|disco`), que ya existe.

### 3.5 Transferencias (`nucleo/transferencias/modelos.py`)

```python
class TipoTransferencia(StrEnum): SUBIDA = "subida"; DESCARGA = "descarga"

class EstadoTransferencia(StrEnum):
    CALCULANDO_HUELLA = "calculando_huella"; COMPROBANDO = "comprobando"
    TRANSFIRIENDO = "transfiriendo"; ESPERANDO_SERVIDOR = "esperando_servidor"   # tarea imgcopy/download
    VERIFICANDO = "verificando"; TERMINADA = "terminada"; CANCELADA = "cancelada"
    FALLIDA = "fallida"; SIN_ESPERAR = "sin_esperar"                            # «Dejar de esperar»

@dataclass(frozen=True)
class DestinoTransferencia: nodo: str; storage: str; contenido: Contenido; nombre_archivo: str
    # volid esperado = f"{storage}:{contenido}/{nombre_archivo}"

@dataclass(frozen=True)
class ComprobacionPrevia:
    volid_existente: str | None            # V-O14 (bloquea; sin opción de sobrescribir)
    libre_storage_bytes: int | None        # V-O13 (bloquea)
    libre_raiz_bytes: int | None           # CA-O10.4 (aviso con casilla)
    permiso: bool | None                   # V-O15/V-O16 (None = desconocido)
    problemas: tuple[Problema, ...]        # de nucleo.validacion, con V-O13/O14/O15/O16

@dataclass(frozen=True)
class Progreso:
    estado: EstadoTransferencia; hechos_bytes: int; total_bytes: int | None
    velocidad_bps: float | None; restante_s: float | None; porcentaje_servidor: float | None

@dataclass(frozen=True)
class ResultadoTransferencia:
    estado: EstadoTransferencia; volid: str | None; error: ErrorProxLaunch | None
    quedo_archivo: bool | None             # tras cancelar o fallar (CA-O12.2); None = no se sabe
    duracion_s: float; upid: str | None

@dataclass(frozen=True)
class RegistroTransferencia:               # INV-O6: sin URL, ruta local ni checksum
    tipo: TipoTransferencia; nombre_archivo: str; storage: str; nodo: str
    tamano_bytes: int | None; hora_local: str; estado: EstadoTransferencia; volid: str | None
```

`UrlDescarga` (en `transferencias/url.py`) guarda la URL validada; su `__repr__` muestra solo
`host/archivo` (como `CredencialToken`) para que un volcado accidental no la filtre.

### 3.6 Perfiles de máquina, lotes guardados y CSV

**`ConfigPerfil`** (`perfiles_maquina/modelos.py`) añade al final, con valor por defecto:
`tipo_so: TipoSO | None = None`, `tpm: bool = False`, `agente_qemu: bool = False` y
`pista_origen: PistaOrigen | None = None`, con

```python
@dataclass(frozen=True)
class PistaOrigen:          # «origen sugerido» (RF-O26): solo nombres, nunca volids de otro servidor
    nombre_fuente: str = ""               # ISO, imagen o plantilla ("" = sin fuente)
    storage_preferido: str | None = None  # ISO/imagen: pista de storage (◐ de §4 de los requisitos)
    drivers: str | None = None            # nombre del ISO de virtio-win; None = detectar
    sin_drivers: bool = False
    modo_clon: ModoClon = ModoClon.AUTOMATICO
    ajustes: AjustesClon = field(default_factory=AjustesClon)
    ampliar_a_gib: int | None = None
```

El campo existente `ConfigPerfil.origen: OrigenSO` pasa a admitir los 4 valores. `aplicar_config`
resuelve la pista contra `inv.catalogo` del nodo efectivo: existe → `RefVolumen` con `volid`; no existe →
`RefVolumen(nombre=…)` sin volid y `AvisoPista` nuevo `FUENTE_NO_ENCONTRADA` (CA-O26.2; bloquea el resumen
por V-O01/V-O02 y **nunca** cambia a «Vacía»). Con origen `clonar_plantilla`, núcleos, memoria y disco
del perfil **no** pisan los de la plantilla salvo los `ajustes` guardados (CA-O26.5).

**Formato JSON del detalle** (clave `config.detalle_origen`; mismas claves en perfil y lote, distinto
contenido según §4 de los requisitos):

| Origen | Lote guardado / fila | Perfil (solo con casilla de pistas) |
|---|---|---|
| `iso` | `{"iso": {"nombre", "volid"}, "drivers": {"nombre","volid"}\|null, "sin_drivers"}` | `{"iso": {"nombre", "storage_preferido"}, "drivers": "nombre"\|null, "sin_drivers"}` |
| `importar_disco` | `{"imagen": {"nombre", "volid"}, "ampliar_a_gib"}` | `{"imagen": {"nombre", "storage_preferido"}, "ampliar_a_gib"}` |
| `clonar_plantilla` | `{"plantilla": {"nombre", "vmid"}, "modo", "ajustes": {…}, "storage_destino"}` | `{"plantilla": {"nombre"}, "modo", "ajustes": {…}}` |

Además `config.tipo_so`, `config.tpm`, `config.agente_qemu` (solo si no son el valor por defecto).
Nunca: URL, ruta local, checksum, `tamano_virtual_bytes`, `modo_efectivo`, `RefPlantilla.nodo` (INV-O6,
INV-M5). Los volids y nombres se leen con la lista blanca de `origen/nombres.py` (texto no válido →
`ErrorCampo` `TEXTO_NO_VALIDO`, nunca se interpreta como ruta).

**Versión de formato (DT-O15, CA-O26.8, CA-O27.5):** `requiere_version_2(cfg)` es verdadera si
`origen ≠ disco_vacio` o hay `tipo_so`/`tpm`/`agente_qemu`; el escritor pone `version_formato = 2` solo
entonces y `1` en otro caso. El lector acepta 1 y 2; `MIGRACIONES[formato][1]` es la identidad (añade
`origen = disco_vacio` si falta). Un MVP 3 que abra un archivo 2 da E-M03.

**CSV** (`csv_importacion/columnas.py`, RF-O28): `DefColumna("origen", ("source",))`,
`DefColumna("fuente", ("origen_archivo", "iso", "plantilla", "imagen"))`, `DefColumna("so", ("sistema",))`,
`DefColumna("virtio", ("drivers",))`, `DefColumna("modo_clon", ("clon",), avanzada=True)`. Valores
(`unidades.py`, sin distinguir mayúsculas ni acentos): `origen` ∈ {`vacio`, `disco_vacio`, `iso`,
`importar`, `imagen`, `clonar`, `plantilla`}; `so` ∈ {`linux`, `windows 11`, `windows server 2022/2025`,
`windows 10`, `windows server 2016/2019`, `otro`} con sus variantes normalizadas; `virtio` ∈ {`si`, `no`};
`modo_clon` ∈ {`auto`, `enlazado`, `completo`}. `fuente` con `:` → volid (V-O02/V-O03); sin `:` → nombre
(V-O09) que la capa 2 resuelve contra el catálogo; con aspecto de URL → E-O21; ruta absoluta → E-O14.
`cpu`, `memoria` y `disco` en filas de clon → `AjustesClon`; `disco` en filas de importación →
`ampliar_a_gib` (CA-O28 y enmienda 14.7).

## 4. Un solo camino en el núcleo para los cuatro orígenes

El principio de M3 (`filas_efectivas`) se mantiene: **todo lote es una lista de filas** y el origen va
dentro de `fila.cfg`. Planificador, reparto, presupuesto, simulación, motor, libro, rollback e informe
trabajan con el mismo `ElementoPlan`; el origen solo cambia (a) qué se lee del catálogo, (b) la
elegibilidad de nodo, (c) el pedido de espacio, (d) qué petición de creación construye `ServicioCreacion`
y (e) los ajustes posteriores.

### 4.1 Validación de la definición (capa 1, pura)
`validar_definicion` (sin cambio de firma) añade por fila `validar_origen_sin_servidor(cfg)`: V-O01, V-O05
(error si Windows 11 sin OVMF o sin TPM; aviso con SeaBIOS en otro Windows), V-O06 (≤ 2 discos IDE con
ISO), V-O07 (aviso de mínimos), V-O23/V-O24 (rangos de ajustes), V-O29 (import exige `con_disco`; ISO sin
disco es aviso). Los `Problema` V-O llevan `indice` de fila (E-M11 en el lote por filas, CA-O29.8).

### 4.2 Catálogo para el plan (E/S, solo GET)
`Planificador.planificar` (sin cambio de firma) calcula `necesidades_catalogo(filas)`. Si **ninguna**
fila tiene origen ≠ `disco_vacio`, no hace ninguna lectura nueva (equivalencia exacta de la secuencia de
GET de M2/M3; CA-O03.1). Si hay orígenes, `ServicioCatalogo.leer_para(inv, necesidades)` lee **fresco**
(CA-O29.5, INV-O8): `GET /nodes/{n}/storage/{s}/content?content=iso|import` de los storages implicados en
los nodos candidatos (I4-§A, §C), `GET /cluster/resources?type=vm` y
`GET /nodes/{n}/qemu/{vmid}/config` de cada plantilla usada (I4-§D), `GET /nodes/{n}/storage?format=1`
si hace falta el formato destino (I4-§H) y `GET /access/permissions` (ya se leía para RF-12: se reutiliza la
misma respuesta). Paralelismo ≤ `MAX_CONSULTAS_SIMULTANEAS` (8). El inventario de trabajo es
`replace(inv, catalogo=…)` y el plan lo guarda en `Plan.catalogo`.

### 4.3 Reparto y elegibilidad por origen (`reparto.py`)
`_motivos_nodo(cfg, inv, nodo)` añade `motivos_nodo_origen(cfg, inv, nodo)` (V-O25, problemas `V-L11`
con `motivo` nuevo):
- `iso`/drivers: el volumen debe existir en un storage `iso` **activo en ese nodo** (compartido o local;
  CA-O07.3, CA-O14.5) → motivo `fuente` (`fuente=<nombre>`).
- `importar_disco`: la imagen en un storage `import` activo en el nodo; el destino del disco con `images`
  (regla existente) → motivo `fuente`.
- `clonar_plantilla`: el nodo es el de la plantilla, o la plantilla tiene **todos** sus discos en storages
  compartidos activos en el nodo (CA-O23.1/O23.2); los bridges de la plantilla existen en el nodo (CA-O22.9
  rama «si no se implementa»); con varias plantillas del mismo nombre en nodos distintos con storage
  local, cada nodo usa la suya (réplica, DT-O13, CA-O23.4) → motivo `plantilla`.
- Clon: las reglas de discos/efidisk de M1 **no** se evalúan (los discos son los de la plantilla).

`_firma(cfg)` añade `firma_origen(cfg)` (origen, ref de fuente, drivers, plantilla, modo, storage
destino) para que la caché de elegibilidad de M3 no mezcle filas con fuentes distintas. Homogéneo: una
sola firma, mismo coste que M2.

### 4.4 Resolución del origen por elemento (`construir_plan`)
Tras el reparto, para cada elemento `cfg_i = resolver_origen(cfg_i, inv, nodo_i)` (pura) devuelve una copia
con: `RefVolumen.volid` resuelto por nombre en el nodo (único; si hay varios con el mismo nombre en storages
distintos → V-O02/V-O03 `ambiguo` con alternativas, CA-O28.3), drivers virtio-win detectados (nombre que
empieza por `virtio-win` y termina en `.iso`, CA-O14.1; ninguno y no `sin_drivers` → V-O02 `drivers`),
`DetalleImportacion.tamano_virtual_bytes` (sesión o API, CA-O16.6), `RefPlantilla.vmid/nodo` de la
plantilla de ese nodo y `DetalleClon.modo_efectivo` (D-25.1: `AUTOMATICO` → `ENLAZADO` si **todos** los
discos de la plantilla están en tipos con clon enlazado — `dir`/`nfs`/`cifs` con qcow2, `btrfs`,
`lvmthin`, `zfspool`, `rbd` — y no se pidió `storage_destino`; si no, `COMPLETO`; I4-§D). En clon, además,
`sockets/cores/tipo_cpu/memoria_mib` efectivos. Los problemas de resolución salen como `Problema` con
`indice` (no excepciones) y bloquean el plan. Las etiquetas del lote se añaden como hoy.

Después, igual que M2/M3: V-L05, presupuesto (§4.5), V-L06, V-L12 y `validar_vm` por elemento (que ahora
incluye `validar_origen` de capa 2: V-O02..V-O04, V-O08, V-O17, V-O18 aviso, V-O19, V-O21, V-O22, V-O23
contra el tamaño real, V-O26). Las vías no disponibles por versión forzada salen como error de capacidad
(CA-O29.7), nunca como excepción.

### 4.5 Presupuesto de espacio por origen (`presupuesto.pedido_vm`)
| Origen | Pedido por MV (clave = storage destino) | Notas |
|---|---|---|
| `disco_vacio` | discos + efidisk (M1) | sin cambios |
| `iso` | discos + efidisk + `TAM_TPM_MIB` (4) si `tpm` en el storage del efidisk (CA-O13.5) | el ISO no ocupa |
| `importar_disco` | 1.er disco: `ampliar_a_gib` o `T` = `tamano_virtual_bytes` (si se desconoce, tamaño del archivo + aviso CA-O18.2); resto como M1 | T × N / X × N (CA-O18.1, O18.4) |
| `clonar_plantilla` completo | Σ discos de la plantilla en `storage_destino` o en su storage | V-O20 |
| `clonar_plantilla` enlazado | 0 (aviso «dependen de la plantilla», CA-O20.5) | V-O20 aviso |

V-L09/V-L10 (thin, D-20.2), «Reducir a N» y «Quitar las filas que no caben» siguen igual (CA-O18.3,
V-O30).

### 4.6 Simulación (`simulacion.py`, INV-O12)
Mismo `Planificador` sobre la sesión de solo lectura. `peticiones[vmid]` = parámetros de la creación
(`POST /qemu` o `POST …/clone`); `peticiones_detalle[vmid]` = tupla de `PeticionSimulada` (CREAR o CLONAR,
CONFIGURAR, AMPLIAR) construidas con las **mismas** funciones puras que la ejecución (`construir_parametros`,
`construir_peticion_clon`, `construir_ajustes_clon`, `parametros_ampliacion`). Nada se sube, descarga ni
crea; una fuente que falta sale como error de fuente («Falta subir X», CA-O29.4).

### 4.7 Compatibilidad de firmas (resumen)
| Elemento | Cambio | Compatibilidad |
|---|---|---|
| `ConfiguracionVM`, `Inventario`, `Storage`, `PerfilConexion`, `Plan`, `ResultadoSimulacion`, `InformeLote`, `ConfigPerfil`, `ResultadoCreacion` | campos al final con valor por defecto | constructores actuales válidos |
| `construir_parametros`, `validar_vm`, `construir_plan`, `planificar`, `repartir_filas` | misma firma | `disco_vacio`: salida idéntica (prueba de equivalencia) |
| `ServicioCreacion.crear` | misma firma | despacha por origen |
| `MotorLote.__init__` | + `concurrencia_enlazado`, `concurrencia_pesada_storage` (con nombre, por defecto) | llamadas actuales válidas |
| `permisos_faltantes_detalle` | + `permisos: … = None` (con nombre) | igual sin el argumento |
| `crear_envoltura` | + `version_formato: int = VERSION_FORMATO_BASE` | igual sin el argumento |
| `ClienteProxmox.storages` | + `con_formatos: bool = False` | sin `format=1` por defecto |
| `Transporte` | sin cambios; protocolo nuevo `TransporteSubida` aparte | dobles de prueba válidos |

## 5. Creación por origen (`servicios/creacion.py`)

`ServicioCreacion.crear` conserva firma y contrato (≤ 1 envío de creación por llamada; nunca borra; nunca
reintenta un envío). Despacha: `CLONAR_PLANTILLA` → `_crear_por_clon`; el resto → `_crear_por_post`
(el camino actual con dos pasos nuevos).

### 5.1 POST (disco vacío, ISO, importación)
1. **VALIDANDO**: `validar_vm` (M1 + V-O capa 2). **Revalidación de la fuente** (INV-O8, CA-O07.6):
   `fuente_vigente(cliente, cfg)` relee el contenido del storage del ISO, de los drivers o de la imagen
   (`GET …/content?content=iso|import`) y comprueba que el volid sigue; si no → `ERROR` con E-O16
   `FUENTE_DESAPARECIO` **sin POST**. Para `disco_vacio` no hay lectura nueva. V-03 como hoy.
2. `construir_parametros(cfg, inv)` (§6.1). `puede_enviar` y **ENVIANDO** sin cambios: un único `POST
   /nodes/{n}/qemu`.
3. **CREANDO**: sondeo con espera máxima `espera_maxima_s(cfg, inv, base)` =
   `max(ESPERA_BASE_S, ESPERA_POR_GIB_S × GiB)` para importación (GiB del tamaño virtual o, si se
   desconoce, del archivo) y `max_espera_s` en el resto (CA-O17.4; enmienda 14.4). Al vencer:
   `TIEMPO_AGOTADO` («sigue en curso en el servidor»), nunca fallo.
4. **COMPROBANDO**: igual que M1.
5. **AJUSTANDO** (solo importación con `ampliar_a_gib` > tamaño): un `PUT …/resize` con tamaño
   **absoluto** `size=<X>G` (CA-O18.4, INV-O3) si `VM.Config.Disk` es seguro; si falla → `PARCIAL`
   («creada, falta ampliar el disco», CA-O18.7) con aviso `ajuste_pendiente:disco` y E-O24.

### 5.2 Clon (`_crear_por_clon`)
1. **VALIDANDO**: `validar_vm`; revalidación de la plantilla con `GET …/qemu/{vmid}/config` (existe,
   `template = 1`, sin `lock`; si no → E-O16/E-O18 sin POST, CA-O21.11); V-03 con
   `GET /cluster/nextid?vmid=` (CA-O21.3, INV-L2).
2. `peticion = construir_peticion_clon(cfg, inv)` → `PeticionClon(nodo_plantilla, vmid_plantilla,
   parametros)`: siempre `newid`, `name`; completo añade `full=1`, `storage` (si `storage_destino`) y
   `format` solo si V-09 lo permite; `target` solo si el nodo destino ≠ nodo de la plantilla (exige storage
   compartido, CA-O21.7). Enlazado: **nunca** `full`, `storage` ni `format` (CA-O20.1, I4-§D).
3. **ENVIANDO**: `cliente.clonar_vm(nodo_plantilla, vmid_plantilla, parametros)` = **el** envío de creación
   de esa MV (INV-L1/INV-O3). Mismo tratamiento de errores que `crear_vm`: 596/timeout/abortada →
   `CONEXION_PERDIDA` sin reenvío; 2xx sin UPID → envío incierto; errores conocidos → E-O18 `CLON_NO_POSIBLE`
   o E-O19 `CLON_ID_OCUPADO` (CA-O21.9).
4. **CREANDO**: sondeo de la tarea `qmclone` en el **nodo del UPID** (`nodo_de_upid`); espera máxima
   proporcional a Σ discos de la plantilla en clon completo, `max_espera_s` en enlazado.
5. **COMPROBANDO**: `config_vm(cfg.nodo, newid)` existe y ya no tiene `lock: clone` (CA-O21.4). Tarea
   fallida con config presente → `PARCIAL` (M1 CA-20.10).
6. **AJUSTANDO** (CA-O22.1..O22.7): `ajustes = construir_ajustes_clon(cfg, detalle_plantilla,
   etiquetas_lote)`:
   - Un `PUT …/config` con, solo si cambian respecto a la plantilla: `sockets`, `cores`, `cpu`, `memory`
     (`VM.Config.CPU`/`Memory`) y `tags` = unión de las de la plantilla y `proxlaunch;lote-<id>` (DT-O14,
     CA-O22.4). Sin cambios ni etiquetas → no hay `PUT` (CA-O22.7). Valores absolutos (INV-O3).
   - Un `PUT …/resize` `disk=<clave del disco principal>` (`scsi0`, si no `virtio0`, `sata0`, `ide0`;
     CA-O22.3) `size=<N>G` absoluto, solo si `N` > tamaño actual y `VM.Config.Disk` es seguro (INV-O10).
   - El orden es etiquetas+CPU/memoria primero (marca de propiedad cuanto antes) y luego el disco. Un
     fallo deja `PARCIAL` con `avisos=("ajuste_pendiente:<ajuste>", …)` y E-O24
     `AJUSTE_POST_CLON_FALLIDO`; **no** se reenvía el clon ni los `PUT` (CA-O22.6). Un 403 lleva el
     privilegio (E-O20) y el motor lo trata como error global (D-20.8, CA-O30.7).
   - `PUT config` es síncrono en la API de `qemu` (devuelve `null`); `PUT resize` puede devolver un UPID
     según versión (I4-§D [LAB]): `ampliar_disco` devuelve `str | None` y, si hay UPID, se sondea.

### 5.3 Reintentar ajustes (Debería, CA-O22.6)
`ServicioCreacion.reintentar_ajustes(cfg, inv, cancelado)` relee `config` de la MV, comprueba que es
propia (regla §9 C2) y envía **solo** los `PUT` cuyo valor aún no coincide (idempotentes). Lo invoca
`lote/ajustes.reintentar_ajustes(libro, vmids, …)`, que resuelve la entrada a `OK` o la deja `PARCIAL`
con `Libro.resolver`. Nunca toca una MV fuera del libro (INV-L4) ni envía un `POST`.

## 6. Peticiones (lista blanca e invariantes de parámetros)

### 6.1 `construir_parametros` (pura; INV-O7, CA-O08.x, CA-O13.x, CA-O17.x)
Orden de construcción (las claves nuevas solo aparecen con origen `iso`/`importar_disco`):
1. M1 sin cambios: `vmid`, `name`, OVMF (`bios`, `machine=q35`, `efidisk0` `4m` `pre-enrolled-keys=1`),
   `sockets`, `cores`, `cpu`, `memory`, `balloon`, `scsihw`.
2. `ostype` = `TABLA_SO[tipo_so].ostype` (`l26`, `win11`, `win10`, `other`), si `tipo_so`.
3. Discos. Con `iso`, las ranuras IDE de los discos salen de `RANURAS_IDE_CON_ISO = ("ide1", "ide3")`
   (V-O06); el resto de buses y los demás orígenes numeran como hoy (CA-O08.4). Con `importar_disco`, el
   primer disco es `"<storage>:0,import-from=<volid>[,discard=on][,ssd=1][,iothread=1][,format=…]"`
   (sintaxis obligatoria `:0`, I4-§C; `format` según V-09/P-06, CA-O17.2) y los demás se crean vacíos.
4. `tpmstate0 = "<storage_efi_efectivo>:1,version=v2.0"` si `tpm` (sin `format`, DT-O8; CA-O13.5).
5. CD: `ide2 = "<volid ISO>,media=cdrom"`; `ide0 = "<volid drivers>,media=cdrom"` si Windows con drivers
   resueltos. Nunca un ISO sin `media=cdrom` (I4-§A).
6. `boot = "order=" + ";".join(<primer disco>, "ide2", "net0")` según `ORDEN_ARRANQUE` (DT-O1; sin disco:
   `order=ide2[;net0]`; sin red, sin `net0`) **solo** si `inv.catalogo.permisos.tiene("VM.Config.Disk",
   f"/vms/{vmid}")` es `True`; con permisos ausentes o desconocidos se omite (INV-O10, CA-O08.3).
7. Redes (M1) y `agent=1` si `agente_qemu` (Windows y Linux, CA-O13.11). `tags` (M2).

**Defensa en profundidad (CA-O08.5, CA-O17.8):** antes de insertar un volid, `construir_parametros` vuelve
a pasarlo por `nombres.validar_volid(volid, contenido)` (`^[A-Za-z0-9._-]{1,64}:(iso|import)/
[A-Za-z0-9._-]{1,100}$` + extensión + sin `..` inicial) y lanza `ErrorProxLaunch(PARAMETRO_INVALIDO,
{"campo": "origen"})` si no cumple. Así `x.iso,media=disk`, `x.iso,ide0=…` o `x.qcow2,scsi1=…` nunca
llegan a la API aunque un archivo o el servidor los traigan.

**Equivalencia (CA-O03.1):** con `origen = disco_vacio`, `tipo_so = None`, `tpm = False` y
`agente_qemu = False` la salida es **byte a byte** la de hoy.

### 6.2 Clon y ajustes (`origen/clon.py`)
- `construir_peticion_clon(cfg, inv) -> PeticionClon` (§5.2). `name` pasa V-01; `newid` = `cfg.vmid`.
- `construir_ajustes_clon(cfg, detalle, etiquetas_lote) -> AjustesTrasClon(config: dict[str, str],
  disco: tuple[str, int] | None)`; `tags` = `";".join(sorted(unión))` con V-24.
- `parametros_ampliacion(clave, tamano_gib) -> dict[str, str]` = `{"disk": clave, "size": f"{n}G"}`
  (nunca `+`).
- `detalle_de_config(config: Mapping[str, object]) -> DetallePlantilla`: parseo defensivo de la config
  (texto no confiable): claves `(scsi|virtio|sata|ide)\d+`, `efidisk0`, `tpmstate0`; salta `media=cdrom`;
  storage = antes de `:`; `size=` con sufijos `K/M/G/T`; valores raros → `None`, nunca excepción.

### 6.3 Asistente de SO (`origen/asistente.py`, RF-O13, DT-O5/O6/O9)
`TABLA_SO: Mapping[TipoSO, PerfilSO]` con `PerfilSO(ostype, firmware, tpm, tpm_obligatorio, drivers,
agente, es_windows, minimos)` según la tabla de RF-O13. `aplicar_asistente(cfg, tipo_so) ->
ResultadoAsistente(cfg, cambios)`: **no** toca núcleos, memoria ni tamaños (CA-O13.9); fuerza firmware
(OVMF+q35 en Windows; el del perfil en Linux/otro), `tpm` (W11 y Server 2022/2025), `controlador_scsi =
virtio-scsi-single`, modelo de red `virtio`, bus `scsi` del primer disco (o `sata` si el avanzado elige
«Compatible», DT-O9) y `agente_qemu`; cada campo cambiado sale en `cambios` («El asistente cambió el
firmware a UEFI», CA-O13.9). `avisos_so(cfg)` devuelve V-O07 (mínimos) y el aviso RHEL 10 / x86-64-v3 para
`linux` (D-25.6, CA-O13.4, [A] hasta LAB-M4-05).

## 7. Transferencias (`nucleo/transferencias/`, RF-O09..O12, O16, O25)

### 7.1 Diseño general
- **Una sola a la vez** (V-O27, DT-O17): `ServicioTransferencias` tiene un cerrojo no bloqueante; `subir` o
  `descargar` con otra en curso → `ErrorProxLaunch(TRANSFERENCIA_EN_CURSO)` (E-O23). La interfaz además
  deshabilita «Subir»/«Descargar» durante un lote o simulación y no genera resúmenes con una transferencia
  activa (CA-O09.11, CA-O12.9).
- **Fuera del lote** (INV-O1): ningún módulo de `lote/`, `perfiles_maquina/`, `lotes_guardados/` ni
  `csv_importacion/` importa `transferencias` (prueba estática). Solo los diálogos de transferencia la
  invocan, tras confirmación.
- **Misma conexión** (CA-O09.10, D-10, D-18): la subida sale por la misma `requests.Session` de
  `TransporteHttp` (huella fija, `trust_env = False`, `AdaptadorBloqueado` para todo lo demás). La app
  **nunca** abre conexiones a la URL del usuario (RNF-O05): la descarga la hace el nodo.
- **Nodo de la subida** (DT-O4): el nodo conectado si el storage está activo en él; si no, otro nodo en
  línea con el storage activo (`elegir_nodo_transferencia(inv, storage, nodo_conectado)`).

### 7.2 Subir (RF-O09, RF-O10, RF-O12, RF-O16)
1. **Inspección local** (`archivo_local.inspeccionar(ruta, contenido)`, E/S mínima): `os.open` en solo
   lectura (`O_RDONLY`, `O_BINARY` en Windows), `fstat` sobre el descriptor (regular, tamaño > 0; evita
   TOCTOU), lectura de ≤ 1 KiB de cabecera y, para ISO, 5 bytes en 0x8001 (C1). `interpretar_cabecera`
   (pura, fuzz CA-RNF-O05): qcow2 `QFI\xfb` v2/v3, `backing_file_offset` (bytes 8–15) = 0,
   `crypt_method` (32–35) = 0, tamaño virtual en bytes 24–31 (BE); vmdk `KDMV` con capacidad en sectores
   (bytes 12–19, LE) y descriptor de texto `# Disk DescriptorFile` → multiarchivo (E-O15); raw = tamaño del
   archivo con aviso; `.ova`/`.ovf` → fuera de alcance (CA-O16.3); ISO sin `CD001` → aviso. Extensión
   corregida al contenido (DT-O12). Nunca se ejecuta `qemu-img` ni nada sobre el archivo (INV-O5).
2. **Nombre**: `sanear_nombre_archivo` propone uno de la lista blanca (CA-O09.12); V-O09 lo valida.
3. **Huella** (estado `CALCULANDO_HUELLA`, DT-O3): sha256 por bloques de `CHUNK_SUBIDA` (1 MiB) con
   progreso y cancelación entre bloques (CA-O12.3); se guarda la `HuellaArchivo` (tamaño, `mtime_ns`,
   inodo/índice).
4. **Comprobaciones** (`COMPROBANDO`, solo GET, CA-O10.6): `comprobar(destino, tamano, inv)` → nombre
   existente sin distinguir mayúsculas (V-O14/E-O10, C5), espacio `avail − RESERVA_STORAGE_MIB` (V-O13/E-O22),
   raíz del nodo `GET /nodes/{n}/status` `rootfs.avail` < tamaño + `RESERVA_RAIZ_MIB` → aviso con casilla
   (CA-O10.4; sin dato → sin aviso), permiso `Datastore.AllocateTemplate` en `/storage/{s}` (V-O15). El
   nombre se **vuelve a comprobar justo antes** del primer byte (CA-O10.2, INV-O2).
5. **Envío** (`TRANSFIRIENDO`): `cliente.subir_archivo(nodo, storage, contenido, nombre, parte,
   checksum_sha256, al_progresar=…, cancelado=…)` → `POST /nodes/{n}/storage/{s}/upload` (I4-§B) con un
   `CuerpoMultipart`: campos `content`, `checksum`, `checksum-algorithm=sha256` y, **al final**, la parte
   `filename` con `filename="<nombre>"` y `Content-Type: application/octet-stream`; `Content-Length`
   exacto (`__len__`); nunca `tmpfilename`. El cuerpo lee en bloques de 1 MiB y entrega a `http.client`
   trozos de `BLOQUE_ENVIO` (64 KiB), comprobando la cancelación entre trozos; recalcula el sha256 al
   vuelo y, al terminar, si difiere del previo o si `fstat` cambió → E-O09 `ARCHIVO_CAMBIO` (CA-O09.8).
   Timeout `(TIMEOUT_CONEXION, PARO_SIN_PROGRESO_S)`; sin reintento ni failover (método no seguro).
6. **Tarea `imgcopy`** (`ESPERANDO_SERVIDOR`): se sondea el UPID hasta `OK` o error (CA-O09.3); checksum
   rechazado → E-O07 y se comprueba que el volid no existe (CA-O09.5).
7. **Verificación** (`VERIFICANDO`, CA-O09.4): el volid aparece en el catálogo con el tamaño local; si no
   aparece pero hay uno «normalizado» nuevo, se muestra el real (CA-O09.12); si no coincide → E-O06 y no se
   selecciona. Éxito → `TERMINADA`, registro en `RegistroSesion` y el catálogo se recarga con el volumen
   seleccionado (CA-O12.8).
8. **Corte** (red, 5xx, sin progreso 120 s) → E-O08 sin reintento; el estado real se mira en el catálogo
   (CA-O09.7, RNF-O12). **Cancelar** → la petición se interrumpe, `TRANSFERENCIA_CANCELADA` y la app mira el
   catálogo para decir si quedó archivo (`quedo_archivo`, CA-O12.2).

### 7.3 Descargar en el servidor (RF-O11, RF-O14)
1. `validar_url(texto, permitir_http)` (V-O11): ≤ 2048, `https` (o `http` solo en avanzado con
   confirmación, DT-O7), host presente, sin `userinfo`, sin control ni espacios, nada de `file:`/`ftp:`.
   `validar_checksum` (V-O12) deduce el algoritmo por la longitud hexadecimal.
2. «Comprobar»: `cliente.metadatos_url(nodo, url, verificar_certificados)` → `GET
   /nodes/{n}/query-url-metadata` (I4-§B) → nombre, tamaño y tipo que ve el **servidor** (CA-O11.1).
3. Comprobaciones previas como en 7.2.4 (tamaño de los metadatos si existe) y permiso V-O16.
4. `cliente.descargar_url(nodo, storage, url=…, contenido=…, nombre=…, checksum=…,
   verificar_certificados=True)` → un `POST …/download-url` (CA-O11.2); `verify-certificates=0` solo en
   avanzado con confirmación y registro del hecho sin URL (CA-O11.4). Sin `compression` (§1.3 requisitos).
5. Tarea `download`: progreso con `progreso_de_log(lineas)` si el log trae porcentaje/bytes [LAB-M4-06];
   si no, tiempo transcurrido e indeterminado (CA-O11.5). «Dejar de esperar» → `SIN_ESPERAR` con el aviso
   de CA-O11.8 (no hay `Sys.Modify` para detenerla). Fin → verificación como 7.2.7; fallo → E-O11 con
   `host` y `archivo` (nunca la URL completa, CA-O11.7).
6. **virtio-win** (CA-O14.2, DT-O10): la vía «Descargarlo en el servidor» usa `URL_VIRTIO_WIN` y
   `SHA256_VIRTIO_WIN` (versión fija). **Ambas constantes quedan vacías hasta LAB-M4-07**; mientras estén
   vacías esa vía no se ofrece (la app no inventa una URL) y quedan «Ya lo tengo» (subida) y «Crear sin los
   drivers».

### 7.4 Registro de la sesión (RF-O25)
`RegistroSesion` (núcleo, en memoria, seguro entre hilos) guarda `RegistroTransferencia` (sin URL, ruta ni
hash). El informe del lote incluye los de la sesión (CA-O25.2, CA-O30.5) y el diálogo «Archivos subidos en
esta sesión» los copia o guarda en `.txt` (CA-O25.3). No se persiste solo.

## 8. Códigos nuevos (`CodigoError`) y textos

| E-O | `CodigoError` (valor) | Params | Lo lanza / emite |
|---|---|---|---|
| E-O01 | `IMPORTAR_VERSION_NO_SOPORTADA` (`importar_version_no_soportada`) | version | `calcular_capacidades`, V-O03 |
| E-O02 | `IMPORTAR_SIN_STORAGE_IMPORT` (`importar_sin_storage_import`) | candidatos | `calcular_capacidades` |
| E-O03 | `DESCARGA_URL_SIN_PERMISO` (`descarga_url_sin_permiso`) | version, nodo, privilegio? | `calcular_capacidades`, V-O16 |
| E-O04 | `STORAGE_RECORDADO_NO_DISPONIBLE` (`storage_recordado_no_disponible`) | storage, contenido | `decidir_storage`, V-O26 |
| E-O05 | `CATALOGO_SIN_PERMISO` (`catalogo_sin_permiso`) | storage | `ServicioCatalogo` (en `ListadoStorage.error`) |
| E-O06 | `TRANSFERENCIA_NO_VERIFICADA` (`transferencia_no_verificada`) | volid, esperado, real | `ServicioTransferencias.verificar` |
| E-O07 | `TRANSFERENCIA_HUELLA_INCORRECTA` (`transferencia_huella_incorrecta`) | algoritmo | tarea `imgcopy`/`download` con checksum fallido |
| E-O08 | `TRANSFERENCIA_CORTADA` (`transferencia_cortada`) | bytes, total | `subir` (red, 5xx, sin progreso) |
| E-O09 | `ARCHIVO_CAMBIO` (`archivo_cambio`) | — | `subir` |
| E-O10 | `NOMBRE_YA_EXISTE` (`nombre_ya_existe`) | storage, nombre | `comprobar`, V-O14 |
| E-O11 | `DESCARGA_URL_FALLIDA` (`descarga_url_fallida`) | host, archivo, motivo | `descargar` |
| E-O12 | `IMPORTAR_SIN_PERMISO` (`importar_sin_permiso`) | privilegio, ruta | `calcular_capacidades` |
| E-O13 | `IMPORTAR_DESTINO_SIN_PERMISO` (`importar_destino_sin_permiso`) | storage | V-O19 |
| E-O14 | `RUTA_ABSOLUTA_NO_PERMITIDA` (`ruta_absoluta_no_permitida`) | — | `nombres`, CSV, traductor («Only root can pass arbitrary filesystem paths») |
| E-O15 | `IMAGEN_NO_ADMITIDA` (`imagen_no_admitida`) | motivo (`backing`, `cifrado`, `multiarchivo`, `ova`, `version`, `truncado`) | `interpretar_cabecera`; traductor («backing file not allowed for untrusted image») |
| E-O16 | `FUENTE_DESAPARECIO` (`fuente_desaparecio`) | nombre, tipo | `fuente_vigente`, creación |
| E-O17 | `SIN_PLANTILLAS` (`sin_plantillas`) | — | `calcular_capacidades` |
| E-O18 | `CLON_NO_POSIBLE` (`clon_no_posible`) | motivo (`no_compartido`, `sin_images`, `parametro_enlazado`, `enlazado_no_soportado`, `bloqueada`, `no_plantilla`, `tpm_en_marcha`) | traductor, `_crear_por_clon` |
| E-O19 | `CLON_ID_OCUPADO` (`clon_id_ocupado`) | vmid | traductor («config file already exists») |
| E-O20 | `PERMISO_INSUFICIENTE` (existente) con `params["via"]` | privilegio, ruta, via | capacidades, 403 de acciones nuevas (extiende CA-L18.9) |
| E-O21 | `FUENTE_ES_URL` (`fuente_es_url`) | fila, columna | `csv_importacion` |
| E-O22 | `ESPACIO_INSUFICIENTE_TRANSFERENCIA` (`espacio_insuficiente_transferencia`) | storage, tamano, libre | `comprobar` |
| E-O23 | `TRANSFERENCIA_EN_CURSO` (`transferencia_en_curso`) | — | `ServicioTransferencias` |
| E-O24 | `AJUSTE_POST_CLON_FALLIDO` (`ajuste_post_clon_fallido`) | nombre, ajuste (`etiquetas`, `cpu_memoria`, `disco`) | `ServicioCreacion` |
| — | `TRANSFERENCIA_CANCELADA` (`transferencia_cancelada`, interno) | quedo_archivo (`si`/`no`/`desconocido`) | `subir`, `descargar` |

E-O20 reutiliza `PERMISO_INSUFICIENTE` (ya traducido y ya extraído del texto de Proxmox, M1 §7): solo
añade `via` para el texto «… para {acción}». Las reglas V-O* son códigos `Problema` (`"V-O02"`,
`"V-O02.ambiguo"`, `"V-O02.drivers"`, `"V-O25"`…), como V-01..V-24.

Patrones nuevos de `traductor_errores` (texto de I4, sin inventar): «can't clone to non-shared storage»,
«does not support vm images», «not allowed for linked clones», «Linked clone feature is not supported»,
«cannot clone TPM state while VM is running», «config file already exists», «Only root can pass arbitrary
filesystem paths», «backing file not allowed for untrusted image», «invalid filename or wrong extension»,
«does not support '…' content» / «is not configured for content-type», «explicit 'media=cdrom' is
required», «Shrinking disk size is not supported». Cualquier otro texto cae en los patrones de M1.

**Textos** (RNF-O07): `textos.py` traduce E-O01..E-O24, V-O01..V-O30, `Via`, `Disponibilidad`,
`EstadoTransferencia`, `TipoSO`, `ModoClon` («Rápido y ligero (recomendado)» / «Copia independiente» en
básico; «Enlazado»/«Completo» en avanzado, CA-O20.6), `TipoDecision`, los avisos `ajuste_pendiente:*`, los
cambios del asistente y los encabezados/alias CSV del idioma activo. `ayuda.py` añade los identificadores de
CA-O32.1 (origen, iso, subir, descargar_url, checksum, asistente_so, drivers_virtio, importar,
formatos_disco, copia_por_mv, plantilla, enlazado_completo, storage_recordado, permisos_rol_ampliado) y el
texto copiable «Qué pedirle a tu administrador» (CA-O32.2). Traducción literal: cada texto con `tr()` en
`textos.py`/`ayuda.py` o en `self.tr` de su diálogo; el núcleo no tiene textos (prueba de literales de M1).

## 9. Seguridad e invariantes

| Invariante | Garantía por construcción | Prueba |
|---|---|---|
| INV-O1 transferencia solo explícita | `ServicioTransferencias` solo lo crean `dialogos/transferencia.py` (vía `controlador_origen`) tras «Subir»/«Descargar»; ningún módulo de lote/perfiles/lotes guardados/CSV lo importa; simulación con transporte de solo lectura (`subir` → E-L23) | Estática de imports; transporte que falla ante POST al abrir, cargar, aplicar, importar y simular |
| INV-O2 nunca sobrescribir | `comprobar` antes y `_volid_libre` justo antes del primer byte; no existe parámetro «sobrescribir» en ninguna firma | Mock: volid existente → cero `POST upload`; aparición entre comprobaciones → bloqueo |
| INV-O3 ≤ 1 creación por VMID; ajustes idempotentes | `crear` llama a `crear_vm` **o** a `clonar_vm`, una vez; `motor.intentados` sin cambios; `PUT` con valores absolutos y `size=NG` | Inyección de fallos de CA-L12.1 por origen, contando `POST /qemu` + `POST …/clone`; `PUT` repetido = mismo estado |
| INV-O4 nunca borrar archivos/plantillas ni privilegios de admin | El cliente no tiene métodos para `DELETE …/content`, `POST …/template`, `PUT /storage`; `rollback` solo borra VMIDs del libro y comprueba `vmid ≠ vmid_plantilla` | Estática: rutas del cliente; rollback de clon deja la plantilla |
| INV-O5 archivo local de solo lectura | `archivo_local` abre `O_RDONLY`, `fstat` regular, cabecera ≤ 1 KiB (+5 bytes ISO, C1); sin `subprocess` en el núcleo | Hash y `mtime` antes/después; estática sin `subprocess`/`os.system` |
| INV-O6 sin URL, ruta, checksum | `RegistroTransferencia` no tiene esos campos; `UrlDescarga.__repr__` enmascarado; `ocultar_url` aplicado a `detalle_tecnico` y a líneas de log de tareas `download`; log con `host_y_archivo`; perfiles/lotes por lista blanca | Centinela extendido (URL con `user:pass@` y `?token=`, rutas, checksums) en archivos, logs, mensajes, informe y portapapeles |
| INV-O7 lista blanca de parámetros | `nombres.validar_volid` al leer (catálogo, archivos, CSV) **y** en `construir_parametros` | Inyección `x.iso,media=disk`, `x.qcow2,scsi1=…`, `;`, `=`, salto de línea, espacios, Unicode |
| INV-O8 fuente revalidada | `fuente_vigente` antes de cada POST/clon; catálogo fresco al planificar y en V-L14 | Fuente borrada entre resumen y POST → cero POST de esa MV |
| INV-O9 resumen y confirmación | El origen solo llega a la API desde `MotorLote` o `ServicioCreacion` con plan/resumen confirmados (INV-M6) | UI: tras cargar lote/CSV con origen, `puede_crear()` falso |
| INV-O10 parámetro opcional con certeza | `boot` y `resize` solo si `PermisosEfectivos.tiene(...) is True` | Permisos ausentes/desconocidos → sin `boot`, sin `resize`, aviso |
| INV-O11 storage recordado no se sustituye | `decidir_storage` devuelve `RECORDADO_NO_DISPONIBLE` sin alternativa elegida; el campo no se borra solo | Recordado desaparece → E-O04, sin cambio en `perfiles.json` |
| INV-O12 simulación solo lecturas | Igual que INV-L5 + `TransporteSoloLectura.subir` | Contador de métodos: solo GET con los tres orígenes |

**Permisos** (`origen/permisos.py`): `PERMISOS_ORIGEN` = `VM.Config.Disk` (`/vms/{vmid}`; `boot`,
`resize`), `VM.Clone` (`/vms/{plantilla}`), `Datastore.AllocateTemplate` (`/storage/{s}`; subir y
descargar), `Sys.AccessNetwork` (`/nodes/{n}`; ≥ 8.2) o `Sys.Modify` (`/`, administrador, solo para
reconocerlo; **nunca** se pide, CA-O11.9). `PERMISOS_POR_RUTA` de M1 **no cambia** (§1, hecho 2). `ROL_PROXLAUNCH`
(14 privilegios) es una constante usada por la guía de tokens y por la prueba de contrato CA-O24.8
(`privilegios_de_peticion(accion)` → privilegios que exige cada escritura: upload, download-url, create con
ISO/import, clone, config, resize; todos ⊆ `ROL_PROXLAUNCH`). Si LAB-M4-04 demuestra que `ide2` exige
`VM.Config.CDROM`, se añade a la constante y a la guía (CA-O24.6).

**Rollback** (C2, D-21): solo `DELETE …/qemu/{vmid}` con `destroy-unreferenced-disks=0`; para elementos
`clonar_plantilla` la propiedad es «etiqueta del lote **o** (UPID propio, no rescatada y `name` igual)»;
nunca se borra `vmid_plantilla` (aserción). Los archivos subidos no se tocan y el informe lo dice
(CA-O30.3). Una importación fallida que dejara un volumen suelto → aviso E-L21 en el informe (CA-O30.4),
sin buscar ni borrar discos.

**Texto no confiable del servidor** (CA-O07.7, CA-O19.8): nombres de volumen, notas y nombres de plantilla se
muestran con `textos.tooltip_plano` / escape en modelos de tabla; nunca como HTML.

## 10. Concurrencia y rendimiento

- **Motor (RNF-O04, CA-O17.10, CA-O21.6, D-25.3).** `lote/cupos.py` clasifica cada elemento:
  `NORMAL` (disco vacío, ISO), `PESADA` (importación, clon completo) y `LIGERA` (clon enlazado). Por nodo
  hay un cupo de `CONCURRENCIA_ENLAZADO_POR_NODO` (3) unidades: `LIGERA` consume 1; `NORMAL` y `PESADA`
  consumen el cupo entero (exclusivas, D-20.5). Por storage destino (`ClavePresupuesto`) hay un semáforo
  de `CONCURRENCIA_PESADA_POR_STORAGE` (2) para `PESADA`. Cada cola de nodo se atiende con hasta 3
  carriles que toman elementos **en el orden del plan** (una `deque` por nodo con cerrojo); un carril que no
  obtiene cupo espera en una `Condition` con tramos de 1 s que atienden pausa, cancelación y suspensión
  (`ControlLote`). Orden de adquisición fijo (nodo → storage) y liberación en `finally`: sin interbloqueo.
  Con `max_nodos == 1` (modo secuencial) se usa un único carril (orden global de M2). Si LAB-M4-10 rechaza
  P-O03, la constante vale 1 y el comportamiento es el de M2.
- **Hilos y conexiones.** `POOL_MAXSIZE = MAX_PETICIONES_SIMULTANEAS + MAX_NODOS_PARALELOS ×
  CONCURRENCIA_ENLAZADO_POR_NODO + 1` (8 + 12 + 1 transferencia = 21). El `ThreadPoolExecutor` del motor
  pasa de `≤ 4` a `≤ 4 × 3` trabajadores (solo se usan con clones enlazados).
- **Interfaz.** Catálogos, capacidades, comprobaciones, hash, subida y sondeos van en `Trabajador`; la
  subida usa un trabajador con señal `progreso` limitada a ≤ `ACTUALIZACIONES_POR_S` (10) y ≥ 1 por
  segundo (`MedidorProgreso`, media móvil de 5 s, reloj inyectado; RNF-O02). Contador de generación
  (`_si_vigente`) para descartar catálogos tardíos al cambiar de nodo o servidor.
- **Rendimiento (RNF-O13).** `clasificar`, `calcular_capacidades`, `validar_origen*`, `resolver_origen` y
  `construir_*` son puros (sin Qt ni E/S). Catálogo de 500 volúmenes: un GET por storage en paralelo y
  modelo de tabla (sin un widget por fila) → ≤ 2 s con mock. Memoria de subida: un búfer de 1 MiB y trozos
  de 64 KiB, sin acumular (≤ 64 MiB medido con `tracemalloc` y RSS para 8 GiB ficticios, RNF-O01).
- **Cancelación** (RNF-O03): hash y envío comprueban `cancelado` entre bloques (≤ 64 KiB en red). Peor caso
  con el servidor sin leer: riesgo R3 (§14).

## 11. Trazabilidad RF → módulo → flujo

Rutas relativas a `src/proxlaunch/nucleo/` (Núcleo) y `src/proxlaunch/interfaz/` (Interfaz). Flujos F-O1..F-O8
de los requisitos y secciones de este documento.

| RF | Núcleo | Interfaz | Flujo |
|---|---|---|---|
| RF-O01 | `modelos/vm.py` (`OrigenSO`, `ConfiguracionVM`), `modelos/origen.py`, `origen/validacion_origen.py` (V-O01), `validacion.py` | `vistas/selector_origen.py` (`SelectorOrigen`), `vistas/formulario_vm.py`, `controlador_origen.py` | §3.1, F-O1..O6 |
| RF-O02 | `origen/capacidades_origen.py` (`calcular_capacidades`), `capacidades.py` | `dialogos/capacidades.py`, `selector_origen.py` (opciones deshabilitadas con motivo), `controlador_origen.py` | §3.3, F-O8 |
| RF-O03 | `constructor_peticion.py` (equivalencia), `ConfiguracionVM.a_dict`, `archivos/envoltura.py` (v1), `persistencia/perfiles.py` | — | §4.7, §6.1 |
| RF-O04 | `origen/storages.py` (`candidatos`, `podria_admitir`), `servicios/descubrimiento.py` (`storages_todos`), `servicios/catalogo.py` (`formatos`) | — | §3.3, F-O8 |
| RF-O05 | `origen/storages.py` (`decidir_storage`, `con_recordado`), `modelos/conexion.py`, `persistencia/perfiles.py`, `valores_defecto.py` (`storage_disco_por_defecto`) | `dialogos/elegir_storage.py`, `dialogos/conexion.py` (3 listas), `controlador_origen.py` | §3.3, F-O8 |
| RF-O06 | `origen/storages.py` (`RECORDADO_NO_DISPONIBLE`), `origen/validacion_origen.py` (V-O26) | `controlador_origen.py` (E-O04, «Elegir otro…», «Dejar de recordar») | §3.3 |
| RF-O07 | `servicios/catalogo.py` (`listar`), `api/cliente.py` (`contenido_storage`), `origen/nombres.py`, `origen/resolucion.py` (V-O25) | `dialogos/catalogo.py`, `modelos_tabla_origen.py` (`ModeloCatalogoVolumenes`) | F-O1 |
| RF-O08 | `constructor_peticion.py` (`ide2`, `boot`, ranuras IDE), `origen/constantes.py` (`ORDEN_ARRANQUE`), `origen/permisos.py` | `vistas/resumen.py`, `resumen_lote.py` (CD y orden o su omisión) | §6.1, F-O1 |
| RF-O09 | `transferencias/servicio.py` (`subir`), `transferencias/archivo_local.py`, `api/multipart.py`, `api/transporte.py` (`subir`), `api/cliente.py` (`subir_archivo`) | `dialogos/transferencia.py` (`DialogoSubida`), `trabajadores.py` (`TrabajadorTransferencia`) | §7.2, F-O3 |
| RF-O10 | `transferencias/servicio.py` (`comprobar`, `_volid_libre`), `origen/nombres.py` (V-O09) | `dialogos/transferencia.py` (casilla raíz, «Usar el existente», «Cambiar el nombre») | §7.2.4 |
| RF-O11 | `transferencias/url.py`, `transferencias/servicio.py` (`consultar_url`, `descargar`), `api/cliente.py` (`metadatos_url`, `descargar_url`) | `dialogos/transferencia.py` (`DialogoDescarga`) | §7.3, F-O4 |
| RF-O12 | `transferencias/progreso.py` (`MedidorProgreso`, `progreso_de_log`), `transferencias/modelos.py` | `dialogos/transferencia.py`, `ventana_principal.py` (cierre con transferencia activa), `controlador_origen.py` | §7, §10 |
| RF-O13 | `origen/asistente.py` (`TABLA_SO`, `aplicar_asistente`, `avisos_so`), `constructor_peticion.py` (`ostype`, `tpmstate0`, `agent`) | `selector_origen.py` (SO), `formulario_vm.py` (avisos de cambio), `resumen.py` | §6.3, F-O2 |
| RF-O14 | `origen/resolucion.py` (detección virtio-win), `constructor_peticion.py` (`ide0`), `origen/constantes.py` (`URL_VIRTIO_WIN`, `SHA256_VIRTIO_WIN`) | `selector_origen.py` (tres caminos), `dialogos/transferencia.py` | §7.3.6, F-O2 |
| RF-O15 | `origen/capacidades_origen.py` (E-O01/O02/O12), `origen/validacion_origen.py` (V-O03, V-O19), `origen/nombres.py` (E-O14) | `selector_origen.py`, `dialogos/capacidades.py` (texto para el admin) | §3.3, F-O5 |
| RF-O16 | `transferencias/archivo_local.py` (`interpretar_cabecera`), `servicios/catalogo.py` (`content=import`) | `dialogos/catalogo.py`, `dialogos/transferencia.py` | §7.2.1, F-O5 |
| RF-O17 | `constructor_peticion.py` (`import-from`), `origen/resolucion.py` (`espera_maxima_s`), `servicios/creacion.py`, `lote/cupos.py` | `progreso_lote.py` (porcentaje si el log lo trae) | §5.1, §10 |
| RF-O18 | `lote/presupuesto.py` (`pedido_vm` por origen), `origen/clon.py` (`parametros_ampliacion`), `servicios/creacion.py` (AJUSTANDO) | `resumen_lote.py` («copia completa… T×N GiB») | §4.5, §5.1 |
| RF-O19 | `servicios/catalogo.py` (`plantillas`, `detalle_plantilla`), `api/cliente.py` (`plantillas_visibles`), `origen/clon.py` (`detalle_de_config`) | `dialogos/catalogo.py`, `modelos_tabla_origen.py` (`ModeloPlantillas`) | F-O6 |
| RF-O20 | `origen/clon.py` (`admite_enlazado`, `modo_efectivo`), `origen/validacion_origen.py` (V-O21, V-O22) | `selector_origen.py` (modo básico/avanzado) | §4.4 |
| RF-O21 | `servicios/creacion.py` (`_crear_por_clon`), `api/cliente.py` (`clonar_vm`), `lote/motor.py`, `lote/cupos.py`, `lote/reconciliacion.py` (`lock: clone`) | `progreso_lote.py` | §5.2, §10, F-O6 |
| RF-O22 | `origen/clon.py` (`construir_ajustes_clon`), `servicios/creacion.py` (AJUSTANDO, `reintentar_ajustes`), `lote/ajustes.py`, `api/cliente.py` (`configurar_vm`, `ampliar_disco`) | `selector_origen.py` («igual que la plantilla»), `informe_lote.py`, `progreso_lote.py` («Reintentar ajustes») | §5.2, §5.3 |
| RF-O23 | `origen/resolucion.py` (`motivos_nodo_origen`, réplica por nombre), `lote/reparto.py` | `resumen_lote.py` («plantilla «x» (en pve1 y pve2)») | §4.3 |
| RF-O24 | `origen/permisos.py` (`PERMISOS_ORIGEN`, `ROL_PROXLAUNCH`, `privilegios_de_peticion`), `servicios/conexion.py` (`leer_permisos`), `api/traductor_errores.py` | `dialogos/capacidades.py`, `dialogos/guia_token.py` (14 privilegios) | §9 |
| RF-O25 | `transferencias/modelos.py` (`RegistroTransferencia`), `transferencias/servicio.py` (`RegistroSesion`), `lote/informe.py` | `dialogos/transferencia.py` (aviso de no deshacer), `dialogos/transferencias_sesion.py`, `dialogos/deshacer.py` | §7.4 |
| RF-O26 | `perfiles_maquina/modelos.py` (`PistaOrigen`), `aplicar.py`, `formato.py`, `compatibilidad.py`, `archivos/esquema_config.py` | `dialogos/guardar_perfil.py`, `vistas/selector_perfil.py` (sin cambio de archivo: lee del núcleo) | §3.6 |
| RF-O27 | `lotes_guardados/formato.py`, `lotes_guardados/revalidacion.py` (+ISO/IMAGEN/DRIVERS/PLANTILLA), `archivos/envoltura.py` | `dialogos/lote_no_encaja.py`, `controlador_origen.py` (catálogo antes de desajustes) | §3.6 |
| RF-O28 | `csv_importacion/columnas.py`, `unidades.py`, `interpretacion.py`, `plantilla.py`, `errores_csv.py` | `dialogos/importar_csv.py`, `vistas/lote_filas.py` (columnas origen/fuente) | §3.6, F-O7 |
| RF-O29 | `lote/planificador.py`, `lote/reparto.py`, `lote/presupuesto.py`, `lote/simulacion.py` (`peticiones_detalle`) | `vistas/resumen_lote.py`, `resumen.py` | §4 |
| RF-O30 | `servicios/creacion.py`, `lote/motor.py`, `lote/rollback.py`, `lote/informe.py` | `informe_lote.py`, `dialogos/deshacer.py` | §5, §9 |
| RF-O31 | `perfiles_maquina/fabrica.py` (+3 ids `fabrica.windows-11`, `fabrica.windows-server`, `fabrica.linux-red-hat`) | `textos.py` (`textos_perfiles_fabrica`) | §12 |
| RF-O32 | — (identificadores en `ayuda.py`) | `ayuda.py`, `textos.py`, `dialogos/capacidades.py`; `docs/guia-usuario.md` (F8) | §8 |

## 12. Plan de fases y dueños de archivos (sin solapes)

`[Fase] -> [Responsable] -> [Subagentes] -> [Esfuerzo] -> [Entregable]`

- F3 Arquitectura -> orquestador -> — -> alto -> este documento aprobado
- F4-0 Contratos -> orquestador -> — -> bajo -> modelos y códigos compilables
- F4a Origen puro + petición + formatos -> implementador A -> `implementador` -> alto -> `origen/`, constructor, persistencia, CSV
- F4b API + transferencias + catálogo -> implementador B -> `implementador` -> alto -> cliente, multipart, transferencias, catálogo
- F4c Creación + lote -> implementador C -> `implementador` -> alto -> creación por origen, cupos, plan, rollback
- F5a Interfaz: piezas nuevas -> implementador D -> `implementador` -> alto -> selector, catálogo, diálogos
- F5b Interfaz: integración -> implementador E -> `implementador` -> alto -> ventana, controlador, formulario
- F5c Interfaz: textos y salidas -> implementador F -> `implementador` -> medio -> textos, ayuda, informe, progreso
- F6 Pruebas -> probador -> `probador` ×3 (núcleo / interfaz / laboratorio) -> alto -> suites verdes + LAB-M4
- F7 Revisión -> revisor y auditor -> `revisor-qa` + `auditor-seguridad` -> medio -> informes y correcciones
- F8 Documentación -> documentador -> `documentador` + `formateador` -> medio -> guía, §11/Anexo B

| Fase | Archivos (dueño exclusivo) | Depende de |
|---|---|---|
| F4-0 | `nucleo/errores.py`, `capacidades.py`, `modelos/vm.py`, `modelos/origen.py`, `modelos/catalogo.py`, `modelos/inventario.py`, `modelos/conexion.py`, `modelos/tarea.py`, `origen/__init__.py`, `origen/constantes.py`, `transferencias/__init__.py`, `transferencias/modelos.py`, `lote/constantes.py`, `lote/modelos.py` | — |
| F4a | `origen/nombres.py`, `permisos.py`, `storages.py`, `capacidades_origen.py`, `asistente.py`, `clon.py`, `resolucion.py`, `validacion_origen.py`; `constructor_peticion.py`, `validacion.py`, `valores_defecto.py`; `perfiles_maquina/*` (salvo `__init__.py` si no cambia); `archivos/constantes.py`, `envoltura.py`, `esquema_config.py`; `lotes_guardados/*`; `csv_importacion/*`; `persistencia/perfiles.py` | F4-0. Si se quiere un 4.º implementador: F4a-1 (`origen/*`, constructor, validación, valores) y F4a-2 (el resto), sin archivos comunes |
| F4b | `api/multipart.py`, `api/transporte.py`, `api/solo_lectura.py`, `api/cliente.py`, `api/traductor_errores.py`; `transferencias/archivo_local.py`, `url.py`, `progreso.py`, `servicio.py`; `servicios/catalogo.py`, `servicios/conexion.py`, `servicios/descubrimiento.py` | F4-0 (usa `origen/nombres.py` y `origen/permisos.py` de F4a por su firma del Anexo A) |
| F4c | `servicios/creacion.py`; `lote/cupos.py`, `motor.py`, `planificador.py`, `reparto.py`, `presupuesto.py`, `reconciliacion.py`, `rollback.py`, `simulacion.py`, `informe.py`, `ajustes.py` | F4-0; integra F4a y F4b al final (contra el Anexo A puede empezar antes) |
| F5a | `interfaz/modelos_tabla_origen.py`, `vistas/selector_origen.py`, `dialogos/catalogo.py`, `dialogos/transferencia.py`, `dialogos/transferencias_sesion.py`, `dialogos/elegir_storage.py`, `dialogos/capacidades.py` | F4 (contra el Anexo A con dobles) |
| F5b | `interfaz/controlador_origen.py`, `ventana_principal.py`, `trabajadores.py`, `vistas/formulario_vm.py`, `vistas/tabla_discos.py`, `vistas/resumen.py`, `vistas/resumen_lote.py`, `vistas/bloque_lote.py`, `dialogos/conexion.py` | F4; F5a para enlazar |
| F5c | `interfaz/textos.py`, `ayuda.py`, `recursos/traducciones/*.ts`, `informe_lote.py`, `modelos_tabla.py`, `vistas/progreso.py`, `vistas/progreso_lote.py`, `vistas/lote_filas.py`, `dialogos/guia_token.py`, `dialogos/guardar_perfil.py`, `dialogos/importar_csv.py`, `dialogos/lote_no_encaja.py`, `dialogos/deshacer.py`, `dialogos/informe.py` | F4 (empieza primero con los textos de §8 para que F5a/F5b los usen por nombre) |
| F6 | `tests/nucleo/test_mvp4_*.py`, `tests/interfaz/test_mvp4_*.py`, `tests/integracion/test_lab_mvp4.py`, `tests/datos/mvp4/` (mocks sintéticos 8.0–9.2 y cabeceras qcow2/vmdk/raw), y **las pruebas existentes que codifican comportamiento enmendado** (§14 de los requisitos: `test_capacidades.py`, `test_modelos.py`, `test_constructor_peticion.py`, `test_archivos_esquema.py`, `test_archivos_envoltura.py`, `test_perfiles_maquina_*.py`, `test_csv_columnas.py`, `test_lote_motor.py`, etc.) | F4 (núcleo), F5 (interfaz), laboratorio encendido |
| F7 | informes | F6 en verde |
| F8 | `docs/guia-usuario.md`, §11 y Anexo B de este documento | F7 |

Paralelismo: F4a, F4b y F4c en paralelo tras F4-0 (F4c integra al final); F5c empieza en cuanto haya
códigos; F5a contra el Anexo A con dobles; F5b al final. Ningún archivo tiene dos dueños: `textos.py` y
`ayuda.py` son solo de F5c (F5a/F5b usan `self.tr` en sus diálogos y las funciones de `textos` por nombre);
`pyproject.toml` no cambia. Quien implementa no escribe sus pruebas (regla 3): las pruebas existentes que
cambian por las enmiendas son de F6. Firmas públicas que surjan durante la implementación se anotan en un
Anexo B tras aprobarlas el orquestador.

**Laboratorio (F6, D-15):** PVE 9.2 de un nodo, storages `local` y `lab-lvmthin`, VMIDs 9000–9099, archivos
`proxlaunch-lab-*`, solo con `PROXLAUNCH_LAB=1`. Pasos de administrador (crear el rol de 14, activar
`import` en `local`, convertir CirrOS en plantilla, borrar archivos subidos, mirar `/var/tmp`) los hace el
`root` del laboratorio por SSH, **no la app**. Sin Internet en el nodo: LAB-M4-06 con un servidor HTTP
local accesible desde el nodo anidado; LAB-M4-07 (virtio-win) solo si se dispone de la ISO (si no, se
documenta y `URL_VIRTIO_WIN` queda vacía). Limpieza completa al terminar (requisitos §12).

## 13. Plan de pruebas (derivadas de los requisitos; las escribe el `probador`)

- **No regresión y equivalencia (RF-O03):** suites de M1–M3 en verde; `construir_parametros` con origen
  vacío idéntico sobre todos los casos de `test_constructor_peticion.py`; secuencia de GET del
  planificador idéntica sin orígenes (CA-O03.1); perfiles, lotes y CSV del MVP 3 cargan sin avisos
  (CA-O03.2); `perfiles.json` sin campos nuevos → `None` (CA-O03.3).
- **Modelo y capa 1:** ida y vuelta `a_dict`/`desde_dict` por origen (CA-O01.5); V-O01, V-O05, V-O06,
  V-O07, V-O23, V-O24, V-O29 por regla y por origen; origen desconocido → `PARAMETRO_INVALIDO`.
- **Capacidades (RF-O02):** test parametrizado fila a fila de la matriz §3 de los requisitos con mocks 8.0,
  8.1, 8.2, 8.3, 8.4, 9.0, 9.1, 9.2 (sintéticos los 8.x) y combinaciones de permisos (rol 10, rol 14, sin
  cada privilegio, administrador, `/access/permissions` fallido); versión forzada (CA-O02.7); ≤ 2 s con 3
  nodos/200 volúmenes (CA-O02.8); solo lecturas.
- **Storages (RF-O04..O06):** nombres engañosos (CA-O04.2); inactivo/deshabilitado/ausente; `content`
  ausente; formatos de la API vs tabla (CA-O04.6); un candidato no se guarda; varios → `PREGUNTAR`;
  recordado vigente/ausente/vuelve (CA-O06.5); dos perfiles de conexión (CA-O05.7); precedencia (propiedad,
  CA-O05.5); `perfiles.json` 0600 y sin centinela (CA-O05.8).
- **Petición (RF-O08, O13, O14, O17):** `ide2` con `media=cdrom`; `boot` con/sin/desconocido
  `VM.Config.Disk`; sin disco; sin red; ranuras IDE con ISO (1, 2, 3 discos IDE); cada `tipo_so`
  (`ostype`, OVMF+q35, `efidisk0` 4m, `tpmstate0 version=v2.0`, `agent`); drivers en `ide0`; `import-from`
  con `:0` y `format` por backend; inyección (`x.iso,media=disk`, `x.iso,ide0=…`, `x.qcow2,scsi1=…`).
- **Clon (RF-O19..O23):** `detalle_de_config` con configs reales y raras; modo automático por backend
  (lvmthin, zfspool, rbd, btrfs, dir qcow2, LVM grueso); enlazado forzado sin soporte (V-O21); completo con
  `storage`/`format`; `target` solo con compartido; ajustes solo si cambian; `tags` unión; `resize`
  absoluto; réplica por nombre; ambigüedad (V-O04).
- **INV-L1/INV-O3 (CA-O21.1, CA-O30.2):** la suite de `test_lote_inyeccion_fallos.py` parametrizada con
  planes de ISO, importación, clon enlazado, clon completo y por filas mixto: fallo inyectado en cada
  punto (timeout, 596/597, conexión abortada, 401, 403, 500, sin UPID, JSON inválido) → ≤ 1 `POST
  /qemu`+`POST …/clone` por VMID; `PUT` fallido → `PARCIAL` sin reenvío; reconciliación con `lock: clone`.
- **Concurrencia (RNF-O04):** mock con contador de peticiones simultáneas por nodo y por storage: ≤ 3
  enlazados por nodo, ≤ 1 normal/pesada por nodo, ≤ 2 pesadas por storage; pausa y cancelación con
  carriles; constante a 1 = comportamiento de M2.
- **Transferencias (RF-O09..O12, O16; RNF-O01..O03, O05, O12, O14):** cuerpo multipart exacto (orden de
  partes, `Content-Type` de la parte, `Content-Length` = bytes enviados); 8 GiB ficticios con
  `tracemalloc`/RSS ≤ 64 MiB; cancelación en hash y envío ≤ 2 s con transporte simulado; corte, 5xx, sin
  progreso, ticket caducado; archivo que cambia (E-O09); checksum erróneo (E-O07); verificación (E-O06);
  nombre existente y carrera (INV-O2); fuzz de `interpretar_cabecera` con 10 000 cabeceras (semilla fija);
  archivo 0 bytes, 4 GiB+1, symlink roto, directorio, tubería, `/dev/zero`; URLs y checksums de §11.6 de los
  requisitos; una sola transferencia (E-O23).
- **Persistencia y CSV (RF-O26..O28):** v1 se escribe sin origen; v2 solo con origen; v1→v2 identidad;
  MVP 3 abre v2 con E-M03 (simulado con `version_soportada=1`); lista blanca de claves (sin URL, ruta,
  checksum, `tamano_virtual_bytes`, `modo_efectivo`, nodo); CSV con los tres orígenes, `fuente` URL/ruta/
  fórmula/vacía/ambigua, `perfil`+`origen` (precedencia, CA-O28.5), plantilla CSV autovalidada.
- **Simulación (CA-O29.3):** contador de métodos: solo GET con todos los orígenes; `peticiones_detalle`
  coincide con lo que la ejecución envía.
- **Rollback (RF-O30, C2):** clon sin etiqueta con UPID propio → elegible; rescatado sin etiqueta → no;
  plantilla intacta; informe «Los archivos que subiste no se eliminan».
- **Privacidad (RNF-O06):** centinela extendido en archivos, logs (incluido log de tarea `download`),
  mensajes, informe y portapapeles.
- **Interfaz (pytest-qt):** opciones deshabilitadas con motivo (CA-O01.2); confirmación al cambiar de origen
  (CA-O01.3); básico/avanzado (CA-O01.4, O13.8, O20.6); diálogos irreversibles con foco en «Cancelar»
  (RNF-O08); barra con nombre accesible y texto; retraso del bucle < 200 ms en subida simulada de 8 GiB;
  cierre con transferencia activa (CA-O12.4); selector deshabilitado durante el lote (CA-O01.7); catálogo
  «[T]» de traducción; escalado 150/200 %.
- **Laboratorio (LAB-M4-01..14):** según la tabla §12 de los requisitos, en `tests/integracion/
  test_lab_mvp4.py`, cada una cerrando sus [LAB]: rol de 14 y negativos; detección y catálogo; subida con
  token y checksum; MV con ISO y `boot` (encendido por `root` del laboratorio); hardware de Windows sin
  Windows; descarga por URL (servidor local); virtio-win (opcional); importación y `import-from`; clon
  (3 enlazados en paralelo, decide P-O03); rollback; lote por filas mixto; capacidades; cortes.

## 14. Riesgos de diseño

1. **R1 · Cambio en el motor.** Los carriles por nodo son el primer cambio del motor desde M2. Mitigación:
   la clase `CuposEjecucion` es independiente y se prueba sola; con la constante a 1 el motor es
   equivalente a M2 (prueba); `intentados` (INV-L1) no cambia.
2. **R2 · Equivalencia M1–M3.** Campos nuevos con valores por defecto y ramas solo con origen ≠ vacío;
   pruebas de equivalencia byte a byte del POST y de la secuencia de GET.
3. **R3 · Cancelación ≤ 2 s (C6).** Con un servidor que deja de leer, `sendall` del trozo en curso
   (64 KiB) puede bloquear hasta el timeout de escritura. La interfaz pasa a «Cancelando…» de inmediato y
   libera el formulario; el hilo termina al vencer el timeout. Refuerzo opcional si LAB-M4-14 lo muestra
   lento: adaptador de subida que guarda la conexión de urllib3 y hace `shutdown(SHUT_RDWR)` al cancelar
   (usa API semiprivada de urllib3; por eso no es el diseño principal).
4. **R4 · Sobrescritura silenciosa** entre la última comprobación y el `POST` (riesgo residual, CA-O10.2).
5. **R5 · Parte multipart y token.** El orden de las partes y la subida con token no están verificados en
   9.2 (I4-§B [LAB]); LAB-M4-03 lo cierra. Si el servidor exigiera otra forma, solo cambia
   `api/multipart.py`.
6. **R6 · Tamaño virtual desconocido** de imágenes ya presentes (LAB-M4-08): el presupuesto es aviso, no
   bloqueo (CA-O18.2); la creación puede fallar por espacio con mensaje traducido.
7. **R7 · Clon con `target`** (plantilla en storage compartido, clúster) solo se prueba con mocks: el
   laboratorio es de un nodo. El nodo de sondeo sale del UPID.
8. **R8 · `PUT resize` síncrono o asíncrono** según versión (I4-§D [LAB]): el cliente acepta ambos.
9. **R9 · Etiquetas en `PUT config`** pueden exigir `Sys.Modify` según la configuración de etiquetas del
   datacenter (como en M2, `ETIQUETA_RECHAZADA`): se traduce y la MV queda `PARCIAL` elegible (C2).
10. **R10 · Tamaño de la interfaz.** `ventana_principal.py` ya tiene 3 352 líneas; F5b debe limitarse a
    enlazar `controlador_origen.py` (objetivo: < 300 líneas añadidas en la ventana).
11. **R11 · Datos del servidor no confiables** (nombres, configs de plantilla): parseo defensivo y lista
    blanca; fuzz sobre `detalle_de_config` además de `interpretar_cabecera`.
12. **R12 · virtio-win sin URL fija** hasta LAB-M4-07: sin esa constante la vía de descarga no existe; el
    resto del asistente de Windows funciona.
13. **R13 · Doble lectura del archivo** (hash + envío, DT-O3): para ISOs grandes duplica el tiempo; el
    sha256 al vuelo durante el envío no evita la primera pasada porque el `checksum` va en el formulario.

## 15. Decisiones técnicas y alternativas descartadas

- **D-A1 Detalle del origen dentro de `ConfiguracionVM`** (`detalle_origen` como unión de 3 dataclasses
  congeladas) y un solo camino (`filas_efectivas`, M3). Descartados: un `ConfiguracionVM` por origen
  (obligaba a uniones de tipos en planificador, motor, informe e interfaz) y campos sueltos `iso_volid`,
  `plantilla_vmid`… (datos ajenos posibles y validación dispersa).
- **D-A2 Multipart propio sin dependencias.** `CuerpoMultipart` con `__iter__` + `__len__` sobre
  `requests` (que entonces pone `Content-Length` y no usa `chunked`), en la misma sesión con huella y
  `trust_env = False`. Descartado `requests-toolbelt` (`MultipartEncoder`): dependencia nueva a auditar
  (D-19) para ~120 líneas propias, y su uso con la sesión es el mismo. Licencia sin cambios.
- **D-A3 Envío en trozos de 64 KiB con cancelación entre trozos** (C6) y sha256 recalculado al vuelo para
  detectar cambios. Descartado el cierre forzado del socket como diseño principal (API semiprivada de
  urllib3; queda como refuerzo, R3).
- **D-A4 Catálogo bajo demanda** con permisos y `storages_todos` obtenidos sin GET nuevos al conectar.
  Descartado leer catálogos y plantillas al conectar (más GET en cada conexión, cambia la secuencia de M1–M3
  y es inútil para quien solo crea MVs vacías).
- **D-A5 Cupos en el motor** (carriles por nodo + semáforo por storage) en lugar de un motor nuevo o de
  repartir el clon enlazado en «subnodos» ficticios (rompía informe y reparto).
- **D-A6 Propiedad de un clon para el rollback** (C2): etiqueta **o** UPID propio + nombre, como el caso
  «sin etiquetas» de M2. Descartado poner una marca en `description` del clon (CA-O21.8 pide conservar la
  de la plantilla) y exigir siempre la etiqueta (dejaría sin deshacer los clones cuyo `PUT` falló).
- **D-A7 Nuevos privilegios fuera de `PERMISOS_POR_RUTA`**, evaluados por vía (CA-O24.4).
- **D-A8 `ostype` derivado de `tipo_so`** (C7). Descartado un campo `ostype` libre.
- **D-A9 Comparación de nombres sin distinguir mayúsculas siempre** (C5).
- **D-A10 Lectura de la firma ISO en 0x8001** con enmienda de INV-O5 (C1). Descartado omitir el aviso de
  «no parece un ISO».
- **D-A11 `version_formato` de escritura explícito** en `crear_envoltura`; `VERSION_FORMATO` pasa a ser la
  versión máxima que se lee (2).
- **D-A12 Revalidación de la fuente en `ServicioCreacion`** (no solo en el planificador) para cubrir el
  camino de una sola MV de M1 (§1, hecho 15).
- **D-A13 Nodo de sondeo desde el UPID** (`nodo_de_upid`) para el clon con `target`.
- **D-A14 Perfiles de fábrica nuevos (RF-O31, Podría)** con valores propuestos por el orquestador a
  confirmar en F4a: «Windows 11 (escritorio)» 4 núcleos, 8 GiB, 64 GiB, OVMF+TPM (CA-O31.1); «Windows
  Server» 4 núcleos, 8 GiB, 80 GiB, OVMF+TPM, `windows_server_2022_2025`; «Linux (Red Hat y otros)» 2
  núcleos, 4 GiB, 40 GiB, SeaBIOS, `linux`; los tres con disco `scsi` + `virtio-scsi-single`, red `virtio`,
  origen `iso` sin fuente.

---

## Anexo A · Firmas públicas del núcleo (MVP 4)

Todas puras salvo las marcadas «E/S». Los errores son `ErrorProxLaunch` con los códigos de §8; las reglas
devuelven `nucleo.validacion.Problema` (capa formulario) o `nucleo.lote.modelos.Problema` (capa lote) como
en M1–M3. `Mapping`, `Sequence`, `Callable`, `Iterator`, `Collection` vienen de `collections.abc`;
`TypeAlias` de `typing`; `BinaryIO` de `typing`.

**`nucleo/modelos/vm.py`** — `OrigenSO` (4 valores, §3.1); `ConfiguracionVM` + `tipo_so: TipoSO | None =
None`, `tpm: bool = False`, `agente_qemu: bool = False`, `detalle_origen: DetalleOrigen | None = None`;
`ConfiguracionVM.a_dict(self) -> dict[str, Any]` y `ConfiguracionVM.desde_dict(cls, d: dict[str, Any]) ->
ConfiguracionVM` (claves nuevas opcionales).

**`nucleo/modelos/origen.py`** — `TipoSO`, `ModoClon`, `RefVolumen`, `RefPlantilla`, `AjustesClon`,
`DetalleIso`, `DetalleImportacion`, `DetalleClon` (§3.1); `DetalleOrigen: TypeAlias = DetalleIso |
DetalleImportacion | DetalleClon`. Sin funciones de serialización: viven en
`archivos/esquema_config.py` (ver abajo).

**`nucleo/modelos/catalogo.py`** — `Contenido`, `Volumen`, `ListadoStorage`, `DiscoPlantilla`,
`DetallePlantilla`, `Plantilla`, `PermisosEfectivos`, `CatalogoServidor` (§3.2);
`PermisosEfectivos.tiene(self, privilegio: str, ruta: str) -> bool`;
`CatalogoServidor.volumenes(self, nodo: str, contenido: Contenido) -> tuple[Volumen, ...]`;
`CatalogoServidor.buscar_volid(self, volid: str, nodo: str) -> Volumen | None`;
`CatalogoServidor.buscar_nombre(self, nombre: str, nodo: str, contenido: Contenido) -> tuple[Volumen, ...]`;
`CatalogoServidor.plantillas_por_nombre(self, nombre: str) -> tuple[Plantilla, ...]`.

**`nucleo/modelos/inventario.py`** — `Storage.formatos: frozenset[str] | None = None`;
`Inventario.storages_todos: dict[str, tuple[Storage, ...]] = field(default_factory=dict)`;
`Inventario.catalogo: CatalogoServidor | None = None`.

**`nucleo/modelos/conexion.py`** — `PerfilConexion.storage_mv: str | None = None`,
`storage_iso: str | None = None`, `storage_import: str | None = None`.

**`nucleo/modelos/tarea.py`** — `Etapa.AJUSTANDO = "ajustando"`; `ResultadoCreacion.avisos: tuple[str, ...] = ()`.

**`nucleo/capacidades.py`** — `Funcion.DESCARGAR_URL` (8, 2), `Funcion.IMPORTAR_DISCO` (8, 4),
`Funcion.SUBIR_IMAGEN_DISCO` (8, 4), `Funcion.TPM_CLON_COMPLETO` (8, 4), `Funcion.CLAVES_MS_2023` (9, 1);
`Funcion.ETIQUETAS` sin cambios.

**`nucleo/origen/constantes.py`** — `CHUNK_SUBIDA = 1 * 1024**2`; `BLOQUE_ENVIO = 64 * 1024`;
`PARO_SIN_PROGRESO_S = 120.0`; `MAX_LONG_URL = 2048`; `MAX_LONG_NOMBRE_VOLUMEN = 100`;
`RESERVA_STORAGE_MIB = 100`; `RESERVA_RAIZ_MIB = 512`; `ESPERA_BASE_S = 600.0`; `ESPERA_POR_GIB_S = 30.0`;
`MAX_CATALOGO = 500`; `URL_VIRTIO_WIN = ""`; `SHA256_VIRTIO_WIN = ""` (se fijan en LAB-M4-07);
`ORDEN_ARRANQUE: tuple[str, ...] = ("disco", "cd", "red")`; `RANURA_ISO = "ide2"`; `RANURA_DRIVERS = "ide0"`;
`RANURAS_IDE_CON_ISO: tuple[str, ...] = ("ide1", "ide3")`; `TAM_TPM_MIB = 4`; `VERSION_TPM = "v2.0"`;
`PREFIJO_VIRTIO_WIN = "virtio-win"`.

**`nucleo/lote/constantes.py`** — `CONCURRENCIA_ENLAZADO_POR_NODO = 3`; `CONCURRENCIA_PESADA_POR_STORAGE = 2`.

**`nucleo/origen/nombres.py`**
- `validar_volid(volid: str, contenido: Contenido) -> str | None` — motivo (`forma`, `caracteres`, `extension`, `ruta_absoluta`) o `None`
- `partes_volid(volid: str) -> tuple[str, Contenido, str] | None` — (storage, contenido, nombre)
- `validar_nombre_archivo(nombre: str, contenido: Contenido) -> str | None` — V-O09
- `sanear_nombre_archivo(nombre: str, contenido: Contenido) -> str`
- `es_ruta_absoluta(texto: str) -> bool`; `parece_url(texto: str) -> bool`; `es_virtio_win(nombre: str) -> bool`
- `EXTENSIONES: Mapping[Contenido, frozenset[str]]`

**`nucleo/origen/permisos.py`**
- `PERMISOS_ORIGEN: Mapping[str, tuple[str, str]]` — privilegio → (plantilla de ruta, vía)
- `ROL_PROXLAUNCH: tuple[str, ...]` (14)
- `tiene_privilegio(permisos: Mapping[str, Mapping[str, int]], ruta: str, privilegio: str) -> bool` (semántica de `_tiene_privilegio` de M1, movida aquí)
- `estado_privilegio(permisos: PermisosEfectivos | None, privilegio: str, ruta: str) -> bool | None` — `None` = desconocido
- `privilegios_de_peticion(accion: str) -> frozenset[str]` — `accion` ∈ {`upload`, `download-url`, `crear_iso`, `crear_import`, `clone`, `config`, `resize`}

**`nucleo/origen/storages.py`** — `TipoDecision`, `DecisionStorage` (§3.3);
- `candidatos(inv: Inventario, contenido: Contenido, nodo: str) -> tuple[Storage, ...]`
- `candidatos_servidor(inv: Inventario, contenido: Contenido) -> tuple[str, ...]`
- `podria_admitir(tipo_storage: str, contenido: Contenido) -> bool` (tabla I4-§H)
- `decidir_storage(inv: Inventario, contenido: Contenido, nodo: str, recordado: str | None) -> DecisionStorage`
- `recordado_de(perfil: PerfilConexion, contenido: Contenido) -> str | None`
- `con_recordado(perfil: PerfilConexion, contenido: Contenido, storage: str | None) -> PerfilConexion` (copia)
- `elegir_nodo_transferencia(inv: Inventario, storage: str, nodo_conectado: str | None) -> str | None` (DT-O4)

**`nucleo/origen/capacidades_origen.py`** — `Via`, `Disponibilidad`, `EstadoVia`, `CapacidadesOrigen` (§3.3);
- `calcular_capacidades(caps: Capacidades, inv: Inventario, nodo: str | None) -> CapacidadesOrigen`
- `CapacidadesOrigen.estado(self, via: Via) -> EstadoVia`; `CapacidadesOrigen.disponible(self, via: Via) -> bool`
- `vias_de_origen(origen: OrigenSO) -> tuple[Via, ...]`

**`nucleo/origen/asistente.py`**
- `@dataclass(frozen=True) class MinimosSO: cores: int; memoria_mib: int; disco_gib: int`
- `@dataclass(frozen=True) class PerfilSO: ostype: str; firmware: Firmware | None; tpm: bool; tpm_obligatorio: bool; drivers: bool; agente: bool; es_windows: bool; minimos: MinimosSO | None`
- `TABLA_SO: Mapping[TipoSO, PerfilSO]`
- `class CampoAsistente(StrEnum)`: `FIRMWARE`, `TPM`, `CONTROLADOR`, `MODELO_RED`, `BUS_DISCO`, `AGENTE`
- `@dataclass(frozen=True) class CambioAsistente: campo: CampoAsistente; antes: str; despues: str`
- `@dataclass(frozen=True) class ResultadoAsistente: cfg: ConfiguracionVM; cambios: tuple[CambioAsistente, ...]`
- `aplicar_asistente(cfg: ConfiguracionVM, tipo_so: TipoSO, *, disco_compatible: bool = False) -> ResultadoAsistente`
- `avisos_so(cfg: ConfiguracionVM) -> list[Problema]` — V-O07 y `V-O05.rhel10`

**`nucleo/origen/clon.py`**
- `TIPOS_CLON_ENLAZADO: frozenset[str]` = {`dir`, `nfs`, `cifs`, `btrfs`, `lvmthin`, `zfspool`, `rbd`}
- `admite_enlazado(tipo_storage: str, formatos: frozenset[str] | None) -> bool`
- `detalle_de_config(config: Mapping[str, object]) -> DetallePlantilla`
- `disco_principal(detalle: DetallePlantilla) -> DiscoPlantilla | None`
- `modo_efectivo(detalle_clon: DetalleClon, plantilla: DetallePlantilla, inv: Inventario, nodo_plantilla: str) -> tuple[ModoClon | None, Problema | None]`
- `@dataclass(frozen=True) class PeticionClon: nodo_plantilla: str; vmid_plantilla: int; parametros: dict[str, str]`
- `construir_peticion_clon(cfg: ConfiguracionVM, inv: Inventario) -> PeticionClon` — lanza `PARAMETRO_INVALIDO` si el detalle no está resuelto
- `@dataclass(frozen=True) class AjustesTrasClon: config: dict[str, str]; disco: tuple[str, int] | None`
- `construir_ajustes_clon(cfg: ConfiguracionVM, plantilla: DetallePlantilla, etiquetas_lote: Sequence[str]) -> AjustesTrasClon`
- `parametros_ampliacion(clave_disco: str, tamano_gib: int) -> dict[str, str]`
- `union_etiquetas(*grupos: Iterable[str]) -> str`

**`nucleo/origen/resolucion.py`**
- `@dataclass(frozen=True) class NecesidadesCatalogo: contenidos: frozenset[Contenido]; plantillas: frozenset[str]; formatos: bool` + `vacias` (propiedad)
- `necesidades_catalogo(filas: Sequence[FilaLote]) -> NecesidadesCatalogo`
- `resolver_origen(cfg: ConfiguracionVM, inv: Inventario, nodo: str) -> tuple[ConfiguracionVM, list[Problema]]` (problemas de `nucleo.validacion`)
- `motivos_nodo_origen(cfg: ConfiguracionVM, inv: Inventario, nodo: str) -> list[ProblemaLote]` (V-L11 con motivo `fuente`/`plantilla`; `ProblemaLote` = `nucleo.lote.modelos.Problema`)
- `firma_origen(cfg: ConfiguracionVM) -> tuple[object, ...]`
- `espera_maxima_s(cfg: ConfiguracionVM, inv: Inventario, base_s: float) -> float`
- `nodo_de_upid(upid: str) -> str | None`

**`nucleo/origen/validacion_origen.py`**
- `CODIGOS_ORIGEN_SIN_SERVIDOR: frozenset[str]` = {`V-O01`, `V-O05`, `V-O06`, `V-O07`, `V-O23`, `V-O24`, `V-O29`} (y subcódigos)
- `validar_origen_sin_servidor(cfg: ConfiguracionVM) -> list[Problema]`
- `validar_origen(cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades) -> list[Problema]`

**`nucleo/constructor_peticion.py`** — `construir_parametros(cfg: ConfiguracionVM, inv: Inventario, version: tuple[int, int] | None = None) -> dict[str, str]` (firma igual; §6.1).

**`nucleo/validacion.py`** — `validar_vm(cfg, inv, caps)` (firma igual; sin V-20; añade `validar_origen` si `origen ≠ disco_vacio`); `CODIGOS_SIN_SERVIDOR` sin `V-20` y con `CODIGOS_ORIGEN_SIN_SERVIDOR`.

**`nucleo/valores_defecto.py`** — `storage_disco_por_defecto(storages: Sequence[Storage], recordado: str | None) -> str | None`.

**`nucleo/perfiles_maquina/`** — `modelos.PistaOrigen` (§3.6); `ConfigPerfil` + `tipo_so`, `tpm`, `agente_qemu`, `pista_origen`; `aplicar.AvisoPista` admite `recurso = "fuente"`; `fabrica.CLAVES_FABRICA` + `windows-11`, `windows-server`, `linux-red-hat`; `compatibilidad.funciones_requeridas(config: ConfigPerfil) -> frozenset[Funcion]` (`IMPORTAR_DISCO` con origen importar); `formato.perfiles_a_bytes(...)` escribe `version_formato` según `requiere_version_2`.

**`nucleo/archivos/`**
- `constantes.VERSION_FORMATO = 2` (máxima que se lee); `constantes.VERSION_FORMATO_BASE = 1`
- `envoltura.crear_envoltura(formato: str, contenido: Mapping[str, object], *, app_version: str, version_formato: int = VERSION_FORMATO_BASE) -> dict[str, object]`
- `envoltura.MIGRACIONES[f][1]` = identidad para `proxlaunch.perfiles`, `proxlaunch.lote` y el almacén de perfiles
- `esquema_config.requiere_version_2(cfg: ConfiguracionVM | ConfigPerfil) -> bool`
- `esquema_config.detalle_origen_a_dict(cfg: ConfiguracionVM) -> dict[str, object] | None` (modo lote)
- `esquema_config.pista_origen_a_dict(config: ConfigPerfil, *, con_pistas: bool) -> dict[str, object] | None`
- `esquema_config.leer_detalle_origen(lector: LectorEsquema, valor: object, ruta: str, origen: OrigenSO) -> DetalleOrigen | None`
- `esquema_config.leer_pista_origen(lector: LectorEsquema, valor: object, ruta: str, origen: OrigenSO) -> PistaOrigen | None`
- `CLAVES_CONFIG_PERFIL`/`CLAVES_CONFIG_LOTE` + `tipo_so`, `tpm`, `agente_qemu`, `detalle_origen`

**`nucleo/lotes_guardados/revalidacion.py`** — `TipoDesajuste` + `ISO = "iso"`, `DRIVERS = "drivers"`, `IMAGEN = "imagen"`, `PLANTILLA = "plantilla"`; `desajustes(definicion: DefinicionLote, inv: Inventario) -> tuple[Desajuste, ...]` (firma igual; usa `inv.catalogo` si existe); `sustituir(...)` (firma igual).

**`nucleo/csv_importacion/`** — `columnas.COLUMNAS` + 5 (§3.6); `unidades.origen(texto: str) -> OrigenSO`; `unidades.tipo_so(texto: str) -> TipoSO`; `unidades.si_no(texto: str) -> bool`; `unidades.modo_clon(texto: str) -> ModoClon` (lanzan `ValorInvalido` con regla `E-M11.*`); `interpretar(...)` y `filas_lote(...)` con firma igual.

**`nucleo/persistencia/perfiles.py`** — `_desde_dict` valida `storage_mv`/`storage_iso`/`storage_import` como `str | None` (otro tipo → `None` con aviso en log, sin descartar el perfil).

**`nucleo/api/multipart.py`**
- `@dataclass(frozen=True) class ParteArchivo: nombre_archivo: str; tamano: int; flujo: BinaryIO; tipo: str = "application/octet-stream"`
- `class CuerpoMultipart`: `__init__(self, campos: Mapping[str, str], parte: ParteArchivo, *, frontera: str | None = None, tam_lectura: int = CHUNK_SUBIDA, tam_envio: int = BLOQUE_ENVIO, al_progresar: Callable[[int, int], None] | None = None, cancelado: threading.Event | None = None, al_leer: Callable[[bytes], None] | None = None) -> None`; `__len__(self) -> int`; `__iter__(self) -> Iterator[bytes]`; `tipo_contenido -> str` (propiedad, `multipart/form-data; boundary=…`); `enviados -> int` (propiedad)
- `class SubidaCancelada(Exception)` — la lanza el iterador al ver `cancelado`

**`nucleo/api/transporte.py`**
- `@runtime_checkable class TransporteSubida(Protocol)`: `subir(self, ruta: str, cuerpo: CuerpoMultipart, *, timeout_lectura: float) -> Any`
- `TransporteHttp.subir(self, ruta: str, cuerpo: CuerpoMultipart, *, timeout_lectura: float = PARO_SIN_PROGRESO_S) -> Any` — sin failover ni reintento; `SubidaCancelada` → `TRANSFERENCIA_CANCELADA`; fallo tras empezar → `SERVIDOR_NO_RESPONDE` con `incierto="1"`
- `POOL_MAXSIZE = MAX_PETICIONES_SIMULTANEAS + MAX_NODOS_PARALELOS * CONCURRENCIA_ENLAZADO_POR_NODO + 1`

**`nucleo/api/solo_lectura.py`** — `TransporteSoloLectura.subir(self, ruta: str, cuerpo: CuerpoMultipart, *, timeout_lectura: float = …) -> Any` → siempre `ESCRITURA_EN_SIMULACION`.

**`nucleo/api/cliente.py`** (E/S; único lugar que construye rutas)
- `storages(self, nodo: str, *, con_formatos: bool = False) -> list[Storage]` — `?format=1` solo con `con_formatos`
- `contenido_storage(self, nodo: str, storage: str, contenido: Contenido) -> list[Volumen]` — `GET /nodes/{n}/storage/{s}/content?content=…` (I4-§A, §C)
- `plantillas_visibles(self) -> list[Plantilla]` — `GET /cluster/resources?type=vm`, `template = 1` (I4-§D)
- `clonar_vm(self, nodo: str, vmid: int, parametros: dict[str, str]) -> str` — `POST /nodes/{n}/qemu/{vmid}/clone`; UPID (`UPID_INVALIDO` si no)
- `configurar_vm(self, nodo: str, vmid: int, parametros: dict[str, str]) -> None` — `PUT /nodes/{n}/qemu/{vmid}/config`
- `ampliar_disco(self, nodo: str, vmid: int, disco: str, tamano_gib: int) -> str | None` — `PUT …/resize` `size=<n>G`; UPID o `None`
- `subir_archivo(self, nodo: str, storage: str, contenido: Contenido, parte: ParteArchivo, checksum_sha256: str, *, al_progresar: Callable[[int, int], None] | None = None, cancelado: threading.Event | None = None, al_leer: Callable[[bytes], None] | None = None) -> str` — `POST /nodes/{n}/storage/{s}/upload` (I4-§B); `TypeError` si el transporte no es `TransporteSubida`
- `@dataclass(frozen=True) class MetadatosUrl: nombre: str | None; tamano: int | None; tipo_mime: str | None`
- `metadatos_url(self, nodo: str, url: UrlDescarga, *, verificar_certificados: bool = True) -> MetadatosUrl` — `GET /nodes/{n}/query-url-metadata`
- `descargar_url(self, nodo: str, storage: str, *, url: UrlDescarga, contenido: Contenido, nombre: str, checksum: ChecksumTransferencia | None, verificar_certificados: bool = True) -> str` — `POST …/download-url`; `detalle_tecnico` pasa por `ocultar_url`

**`nucleo/api/traductor_errores.py`** — patrones de §8; `traducir_http(...)` y `traducir_exitstatus(...)` con firma igual.

**`nucleo/transferencias/url.py`**
- `@dataclass(frozen=True, repr=False) class UrlDescarga: texto: str; host: str; archivo: str; es_http: bool` (`__repr__` solo `host/archivo`)
- `class AlgoritmoChecksum(StrEnum)`: `MD5`, `SHA1`, `SHA224`, `SHA256`, `SHA384`, `SHA512`
- `@dataclass(frozen=True) class ChecksumTransferencia: algoritmo: AlgoritmoChecksum; valor: str`
- `validar_url(texto: str, *, permitir_http: bool) -> tuple[UrlDescarga | None, str | None]` — motivo V-O11
- `validar_checksum(texto: str) -> tuple[ChecksumTransferencia | None, str | None]` — V-O12
- `ocultar_url(texto: str, url: UrlDescarga) -> str`
- `host_y_archivo(url: UrlDescarga) -> tuple[str, str]`

**`nucleo/transferencias/archivo_local.py`** (E/S salvo `interpretar_cabecera`)
- `class TipoArchivoLocal(StrEnum)`: `ISO`, `QCOW2`, `VMDK`, `RAW`, `OVA`, `DESCONOCIDO`
- `@dataclass(frozen=True) class HuellaArchivo: tamano: int; mtime_ns: int; identidad: tuple[int, int]`
- `@dataclass(frozen=True) class InspeccionArchivo: nombre_local: str; tamano_bytes: int; tipo: TipoArchivoLocal; tamano_virtual_bytes: int | None; extension_propuesta: str; motivo_rechazo: str | None; avisos: tuple[str, ...]`
- `TAM_CABECERA = 1024`; `DESPLAZAMIENTO_ISO9660 = 0x8001`
- `interpretar_cabecera(cabecera: bytes, firma_iso: bytes | None, tamano: int, contenido: Contenido) -> tuple[TipoArchivoLocal, int | None, str | None, tuple[str, ...]]`
- `inspeccionar(ruta: Path, contenido: Contenido) -> InspeccionArchivo` (E/S)
- `class ArchivoAbierto` (gestor de contexto): `flujo -> BinaryIO`; `huella -> HuellaArchivo`; `sigue_igual(self) -> bool`; `cerrar(self) -> None`
- `abrir_para_subir(ruta: Path) -> ArchivoAbierto` (E/S; `ARCHIVO_NO_ACCESIBLE`/`ARCHIVO_NO_PERMITIDO` de M3 si no es regular)
- `calcular_sha256(archivo: ArchivoAbierto, *, al_progresar: Callable[[int, int], None] | None = None, cancelado: threading.Event | None = None, tam_bloque: int = CHUNK_SUBIDA) -> str` (E/S)

**`nucleo/transferencias/progreso.py`**
- `class MedidorProgreso`: `__init__(self, reloj: Reloj, *, ventana_s: float = 5.0) -> None`; `registrar(self, hechos: int, total: int | None) -> tuple[float | None, float | None]` (velocidad, restante); `debe_emitir(self) -> bool` (≤ 10/s, ≥ 1/s)
- `progreso_de_log(lineas: Sequence[str]) -> tuple[int | None, int | None, float | None]` — (bytes, total, porcentaje); tolerante

**`nucleo/transferencias/servicio.py`** (E/S)
- `class RegistroSesion`: `agregar(self, registro: RegistroTransferencia) -> None`; `lista(self) -> tuple[RegistroTransferencia, ...]`; `vaciar(self) -> None`
- `class ServicioTransferencias`: `__init__(self, sesion: Sesion, reloj: Reloj, registro: RegistroSesion, *, intervalo_s: float = INTERVALO_SONDEO_S, paro_sin_progreso_s: float = PARO_SIN_PROGRESO_S, hora_local: Callable[[], str]) -> None`
  - `ocupado -> bool` (propiedad)
  - `comprobar(self, destino: DestinoTransferencia, tamano_bytes: int | None, inv: Inventario) -> ComprobacionPrevia`
  - `subir(self, ruta: Path, destino: DestinoTransferencia, inv: Inventario, *, al_progresar: Callable[[Progreso], None], cancelado: threading.Event, acepta_aviso_raiz: bool) -> ResultadoTransferencia`
  - `consultar_url(self, nodo: str, url: UrlDescarga, *, verificar_certificados: bool = True) -> MetadatosUrl`
  - `descargar(self, url: UrlDescarga, destino: DestinoTransferencia, inv: Inventario, *, checksum: ChecksumTransferencia | None, verificar_certificados: bool, al_progresar: Callable[[Progreso], None], dejar_de_esperar: threading.Event) -> ResultadoTransferencia`
  - `verificar(self, destino: DestinoTransferencia, tamano_esperado: int | None) -> ResultadoTransferencia`

**`nucleo/servicios/catalogo.py`** (E/S, solo GET)
- `class ServicioCatalogo`: `__init__(self, sesion: Sesion, reloj: Reloj, *, max_consultas: int = MAX_CONSULTAS_SIMULTANEAS) -> None`
  - `listar(self, inv: Inventario, nodo: str, contenido: Contenido) -> tuple[ListadoStorage, ...]`
  - `plantillas(self) -> tuple[Plantilla, ...]`
  - `detalle_plantilla(self, nodo: str, vmid: int) -> DetallePlantilla | None`
  - `formatos(self, inv: Inventario, nodos: Collection[str]) -> dict[str, frozenset[str]]`
  - `leer_para(self, inv: Inventario, necesidades: NecesidadesCatalogo, nodos: Collection[str]) -> CatalogoServidor`
- `fuente_vigente(cliente: ClienteProxmox, cfg: ConfiguracionVM) -> ErrorProxLaunch | None` (INV-O8)
- `con_catalogo(inv: Inventario, catalogo: CatalogoServidor | None) -> Inventario` (copia con `dataclasses.replace`)

**`nucleo/servicios/conexion.py`** — `permisos_faltantes_detalle(sesion: Sesion, *, permisos: dict[str, dict[str, int]] | None = None) -> list[tuple[str, str]] | None`; `leer_permisos(sesion: Sesion) -> PermisosEfectivos | None`; `PERMISOS_POR_RUTA` sin cambios.

**`nucleo/servicios/descubrimiento.py`** — `descubrir(sesion: Sesion) -> Inventario` (firma igual; rellena `storages_todos` y `catalogo=CatalogoServidor(permisos=…)` sin GET nuevos salvo el de permisos que ya hacía RF-12, que pasa a hacerse aquí una sola vez); `descubrir_nodo` sin cambios.

**`nucleo/servicios/creacion.py`** — `ServicioCreacion.crear(...)` (firma igual); `ServicioCreacion.reintentar_ajustes(self, cfg: ConfiguracionVM, inv: Inventario, cancelado: threading.Event) -> ResultadoCreacion`.

**`nucleo/lote/cupos.py`**
- `class ClaseCarga(StrEnum)`: `NORMAL`, `PESADA`, `LIGERA`
- `clase_de(cfg: ConfiguracionVM) -> ClaseCarga`
- `class CuposEjecucion`: `__init__(self, inv: Inventario, *, por_nodo: int = CONCURRENCIA_ENLAZADO_POR_NODO, pesadas_por_storage: int = CONCURRENCIA_PESADA_POR_STORAGE) -> None`; `adquirir(self, elemento: ElementoPlan, control: ControlLote) -> bool` (falso si se canceló/suspendió mientras esperaba); `liberar(self, elemento: ElementoPlan) -> None`

**`nucleo/lote/motor.py`** — `MotorLote.__init__(self, sesion: Sesion, reloj: Reloj, *, fabrica_creacion: FabricaCreacion = ServicioCreacion, max_nodos: int = MAX_NODOS_PARALELOS, umbral_pausa: int = UMBRAL_PAUSA_ERRORES, concurrencia_enlazado: int = CONCURRENCIA_ENLAZADO_POR_NODO, concurrencia_pesada_storage: int = CONCURRENCIA_PESADA_POR_STORAGE) -> None`; `ejecutar`, `ejecutar_pendientes`, `comprobar_dudosas` con firma igual (usan `con_catalogo(inv, plan.catalogo)`).

**`nucleo/lote/reconciliacion.py`** — `LOCKS_EN_CREACION = frozenset({"create", "clone"})`; `config_en_creacion(config)` usa la constante; `reconciliar_incierta(...)` firma igual.

**`nucleo/lote/rollback.py`** — `ServicioRollback.elegibles(...)` y `deshacer(...)` con firma igual; `es_propia(config: Mapping[str, Any], entrada: EntradaLibro, id_lote: str, etiquetado: bool) -> bool` (pública, regla C2).

**`nucleo/lote/simulacion.py`** — `simular(...)` firma igual; rellena `peticiones_detalle`.

**`nucleo/lote/informe.py`** — `construir_informe(...)` + parámetro con nombre `transferencias: Sequence[RegistroTransferencia] = ()`.

**`nucleo/lote/ajustes.py`** — `reintentar_ajustes(libro: Libro, vmids: Collection[int], sesion: Sesion, reloj: Reloj, inv: Inventario, observador: Observador, control: ControlLote, *, fabrica_creacion: FabricaCreacion = ServicioCreacion) -> None` (Debería).

**`nucleo/lote/modelos.py`** — `EstadoMV.AJUSTANDO`; `AccionPeticion`; `PeticionSimulada`; `Plan.catalogo`; `ResultadoSimulacion.peticiones_detalle`; `InformeLote.transferencias` (§3.4).

**Interfaz (contratos que F5a/F5b/F5c comparten; firmas mínimas)**
- `controlador_origen.ControladorOrigen(QObject)`: `__init__(self, lanzador: Lanzador, repositorio_perfiles: RepositorioPerfiles, reloj: Reloj, parent: QObject | None = None)`; `establecer_sesion(self, sesion: Sesion | None, inv: Inventario | None) -> None`; `capacidades(self, nodo: str | None) -> CapacidadesOrigen | None`; `cargar_catalogo(self, nodo: str, contenido: Contenido) -> None`; `cargar_plantillas(self) -> None`; `storage_para(self, contenido: Contenido, nodo: str, parent: QWidget) -> str | None`; `abrir_subida(self, contenido: Contenido, nodo: str, parent: QWidget) -> None`; `abrir_descarga(self, contenido: Contenido, nodo: str, parent: QWidget) -> None`; `transferencia_activa -> bool`; `cancelar_transferencia(self) -> None`; `registro -> RegistroSesion`; señales `catalogo_cargado(object)`, `plantillas_cargadas(object)`, `capacidades_cambiadas(object)`, `transferencia_terminada(object)`.
- `vistas/selector_origen.SelectorOrigen(QWidget)`: `establecer_capacidades(self, caps: CapacidadesOrigen | None) -> None`; `establecer_catalogo(self, volumenes: Sequence[Volumen], plantillas: Sequence[Plantilla] | None) -> None`; `establecer_modo(self, avanzado: bool) -> None`; `aplicar(self, cfg: ConfiguracionVM) -> None`; `completar(self, cfg: ConfiguracionVM) -> ConfiguracionVM`; `establecer_bloqueado(self, bloqueado: bool) -> None`; señales `origen_cambiado(object)`, `pedir_catalogo(object)`, `pedir_subida(object)`, `pedir_descarga(object)`.
- `dialogos/transferencia.DialogoSubida(QDialog)` / `DialogoDescarga(QDialog)`: `__init__(self, controlador: ControladorOrigen, contenido: Contenido, nodo: str, parent: QWidget | None = None)`; `resultado -> ResultadoTransferencia | None`.
- `trabajadores.TrabajadorTransferencia(Trabajador)`: señal adicional `progreso(object)` con `Progreso`.
- `textos.texto_via(estado: EstadoVia) -> str`; `textos.texto_estado_transferencia(estado: EstadoTransferencia) -> str`; `textos.texto_tipo_so(tipo: TipoSO) -> str`; `textos.texto_modo_clon(modo: ModoClon, *, avanzado: bool) -> str`; `textos.texto_cambio_asistente(cambio: CambioAsistente) -> str`; `textos.texto_texto_administrador() -> str` (CA-O32.2); `textos.texto_error` cubre los códigos de §8.
