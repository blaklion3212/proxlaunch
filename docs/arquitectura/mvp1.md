# Arquitectura del MVP 1 — ProxLaunch

Versión 1.0 (2026-11-11) · Autor: orquestador · Estado: propuesta para aprobación

Fuentes: `docs/decisiones.md` (D-xx, CT-n) y `docs/requisitos/mvp1.md` (RF, RNF, CA, V, P).
Este documento fija **módulos, modelos e interfaces**; los implementadores no deben cambiar
firmas públicas sin consultar al orquestador.

---

## 1. Principios

1. **Dos capas, una dependencia.** `proxlaunch.nucleo` (Python puro) ← `proxlaunch.interfaz`
   (PySide6). El núcleo **nunca** importa Qt (RNF-02, CA-18.4). Una prueba lo verifica.
2. **El núcleo habla en códigos, la interfaz en español.** El núcleo devuelve
   `CodigoError`/`CodigoProblema` con parámetros; la interfaz los traduce con `tr()` (RF-23,
   CA-23.4). El núcleo no contiene textos para el usuario.
3. **Síncrono en el núcleo, concurrente en la interfaz.** El núcleo usa llamadas bloqueantes
   (más fáciles de probar); la interfaz las ejecuta en hilos de trabajo (`QThreadPool`) y
   recibe resultados por señales (RNF-01). En el MVP 2 el motor de lotes reutilizará el
   mismo núcleo con un `ThreadPoolExecutor`.
4. **Inyección de dependencias.** Reloj, transporte HTTP, llavero y carpetas se inyectan,
   para probar con mocks sin red (RNF-08) y con tiempo simulado (CA-03.1).
5. **Un solo lugar para cada regla:** validaciones en `validacion.py`, versiones en
   `capacidades.py`, colores en `tema/paleta.py`, formato de parámetros en
   `constructor_peticion.py`.
6. **Secretos fuera de todo lo persistente.** Solo en memoria o en el llavero (RNF-06).

## 2. Estructura del repositorio

```
pyproject.toml                  # metadatos, dependencias, ruff, pytest
src/proxlaunch/
  __init__.py                   # __version__
  __main__.py                   # python -m proxlaunch → interfaz.app.main()
  nucleo/                       # SIN Qt
    errores.py                  # CodigoError, ErrorProxLaunch
    modelos/
      vm.py                     # ConfiguracionVM, Disco, InterfazRed, enums
      conexion.py               # PerfilConexion, Credencial*, MetodoAuth
      inventario.py             # Nodo, Storage, Bridge, Inventario, Topologia
      tarea.py                  # Etapa, EstadoTarea, ResultadoCreacion
    validacion.py               # V-01..V-21 → list[Problema]
    capacidades.py              # tabla de capacidades por versión (RF-09)
    valores_defecto.py          # sección 5 de requisitos
    constructor_peticion.py     # ConfiguracionVM → dict de parámetros API
    seleccion_nodo.py           # nodo "Automático" (P-07)
    api/
      transporte.py             # HTTP: TLS con huella, timeouts, failover de IPs
      autenticacion.py          # token, ticket, renovación, 2FA
      cliente.py                # ClienteProxmox: operaciones de alto nivel
      traductor_errores.py      # respuesta/excepción → CodigoError
      huella.py                 # obtener huella SHA-256 sin enviar credenciales
    servicios/
      conexion.py               # ServicioConexion: perfil → Sesion
      descubrimiento.py         # Sesion → Inventario
      creacion.py               # ServicioCreacion: validar → enviar → seguir
    persistencia/
      rutas.py                  # platformdirs (config, log, datos)
      almacen_json.py           # escritura atómica + copia de archivo corrupto
      perfiles.py               # RepositorioPerfiles
      huellas.py                # RepositorioHuellas (por host:puerto)
      preferencias.py           # tema, modo, versión forzada
      secretos.py               # AlmacenSecretos (keyring, con modo "no disponible")
    registro.py                 # logging rotativo + filtro de secretos
    reloj.py                    # Reloj (real / simulado)
  interfaz/                     # PySide6
    app.py                      # QApplication, fuentes, traducciones, tema
    ventana_principal.py
    trabajadores.py             # Trabajador(QRunnable) + señales; cancelación
    textos.py                   # CodigoError/CodigoProblema → tr()
    ayuda.py                    # textos de ayuda por campo (RF-25)
    tema/
      paleta.py                 # tokens de color por tema (único lugar de colores)
      plantilla.qss             # QSS con marcadores {{token}}
      gestor_tema.py            # Automático/Oscuro/Claro + detección y señal
    dialogos/
      conexion.py  huella.py  dos_factores.py  guia_token.py  acerca_de.py
    vistas/
      barra_superior.py  formulario_vm.py  tabla_discos.py  tabla_redes.py
      resumen.py  progreso.py  detalles_tecnicos.py
  recursos/
    marca/      (copias de recursos/marca/*.svg)
    fuentes/    (Open Sans, JetBrains Mono — OFL)
    traducciones/  proxlaunch_es.ts / .qm
tests/
  conftest.py                   # bloqueo de red, fixtures de respuestas
  datos/respuestas/{8.0,9.2}/   # respuestas reales capturadas y anonimizadas
  nucleo/  interfaz/  integracion/   # integracion: solo con PROXLAUNCH_LAB=1
```

## 3. Modelos de datos (núcleo, `dataclasses`)

Se usan `dataclasses` (no Pydantic): sin dependencia extra, y la validación depende del
inventario (contexto), por lo que vive en `validacion.py`.

```python
# nucleo/modelos/vm.py
class Firmware(StrEnum):    SEABIOS = "seabios"; OVMF = "ovmf"
class Bus(StrEnum):         SCSI = "scsi"; VIRTIO = "virtio"; SATA = "sata"; IDE = "ide"
class FormatoDisco(StrEnum): AUTO = "auto"; RAW = "raw"; QCOW2 = "qcow2"   # nunca subvol
class ModeloRed(StrEnum):   VIRTIO = "virtio"; E1000 = "e1000"
class ControladorScsi(StrEnum): VIRTIO_SINGLE = "virtio-scsi-single"; VIRTIO_PCI = "virtio-scsi-pci"
class OrigenSO(StrEnum):    DISCO_VACIO = "disco_vacio"            # MVP 4 añade más

@dataclass
class Disco:
    storage: str
    tamano_gib: int
    bus: Bus = Bus.SCSI
    formato: FormatoDisco = FormatoDisco.AUTO
    discard: bool = True
    ssd: bool = True
    iothread: bool = True

@dataclass
class InterfazRed:
    bridge: str
    modelo: ModeloRed = ModeloRed.VIRTIO
    vlan: int | None = None

@dataclass
class Ballooning:
    activo: bool
    minimo_mib: int

@dataclass
class ConfiguracionVM:
    vmid: int
    nombre: str
    nodo: str
    firmware: Firmware = Firmware.SEABIOS
    storage_efi: str | None = None          # None = el del primer disco (CA-14.2)
    sockets: int = 1
    cores: int = 2
    tipo_cpu: str = "x86-64-v2-AES"
    memoria_mib: int = 2048
    ballooning: Ballooning | None = None    # None = no enviar (modo básico, CA-15.5)
    con_disco: bool = True
    discos: list[Disco] = field(default_factory=list)
    controlador_scsi: ControladorScsi = ControladorScsi.VIRTIO_SINGLE
    redes: list[InterfazRed] = field(default_factory=list)
    origen: OrigenSO = OrigenSO.DISCO_VACIO
    def a_dict(self) -> dict: ...           # ida y vuelta (CA-18.3)
    @classmethod
    def desde_dict(cls, d: dict) -> "ConfiguracionVM": ...
```

```python
# nucleo/modelos/conexion.py
class MetodoAuth(StrEnum): TOKEN = "token"; CONTRASENA = "contrasena"

@dataclass
class PerfilConexion:           # persistible: NUNCA contiene secretos (RF-07)
    id: str                     # uuid
    nombre: str
    hosts: list[str]            # orden = prioridad de failover
    puerto: int = 8006
    metodo: MetodoAuth = MetodoAuth.TOKEN
    usuario: str = ""           # "root" o "ana"; con token: "ana@pve!lab" (sin secreto)
    realm: str = "pam"
    recordar_credenciales: bool = False
    ignorar_ssl: bool = False   # solo efectivo en modo avanzado (CA-06.3)

@dataclass(repr=False)          # repr enmascarado: nunca imprimir secretos
class CredencialToken:  token_id: str; secreto: str
@dataclass(repr=False)
class CredencialContrasena: usuario: str; realm: str; contrasena: str

@dataclass(repr=False)
class Ticket:                   # solo en memoria
    ticket: str; csrf: str; usuario: str; emitido_en: float
```

```python
# nucleo/modelos/inventario.py
@dataclass(frozen=True)
class Version:  texto: str; mayor: int; menor: int; parche: int
@dataclass(frozen=True)
class Nodo:     nombre: str; en_linea: bool; mem_libre_mib: int | None; cpus: int | None
@dataclass(frozen=True)
class Storage:  id: str; tipo: str; contenido: frozenset[str]; compartido: bool
                activo: bool; total_bytes: int; libre_bytes: int
                @property def es_thin(self) -> bool       # lvmthin, zfspool, rbd
                @property def libre_gib(self) -> float    # redondeo hacia abajo, 1 decimal
@dataclass(frozen=True)
class Bridge:   nombre: str; tipo: str; vlan_aware: bool
@dataclass(frozen=True)
class Topologia: es_cluster: bool; nombre_cluster: str | None; nodos: tuple[Nodo, ...]
@dataclass
class Inventario:
    version: Version; topologia: Topologia; proximo_vmid: int
    storages: dict[str, tuple[Storage, ...]]   # por nodo
    bridges: dict[str, tuple[Bridge, ...]]     # por nodo
    errores_por_nodo: dict[str, "ErrorProxLaunch"]
```

```python
# nucleo/modelos/tarea.py
class Etapa(StrEnum): VALIDANDO; ENVIANDO; CREANDO; COMPROBANDO; LISTO   # CA-20.2
class Desenlace(StrEnum): OK; CON_AVISOS; ERROR; TIEMPO_AGOTADO; CONEXION_PERDIDA; PARCIAL
@dataclass
class ResultadoCreacion:
    desenlace: Desenlace; vmid: int; nodo: str; upid: str | None
    error: "ErrorProxLaunch | None"; log_tarea: list[str]
```

## 4. Errores y problemas de validación

```python
# nucleo/errores.py
class CodigoError(StrEnum):
    CREDENCIALES_INVALIDAS, SESION_EXPIRADA, HUELLA_CAMBIADA, HUELLA_NO_CONFIADA,
    TFA_NO_SOPORTADO, TFA_CODIGO_INCORRECTO, SERVIDOR_NO_RESPONDE, NODO_NO_DISPONIBLE,
    PERMISO_INSUFICIENTE, VMID_OCUPADO, SIN_ESPACIO, TAREA_TIEMPO_AGOTADO,
    ERROR_FORMATO, PARAMETRO_INVALIDO, VERSION_NO_SOPORTADA, RECURSO_INEXISTENTE,
    UPID_INVALIDO, LLAVERO_NO_DISPONIBLE, DESCONOCIDO

class ErrorProxLaunch(Exception):
    codigo: CodigoError
    params: dict[str, str]      # p. ej. {"privilegio": "VM.Allocate", "ruta": "/vms/100"}
    detalle_tecnico: str        # texto original de Proxmox, YA sin secretos

# nucleo/validacion.py
class Severidad(StrEnum): ERROR = "error"; AVISO = "aviso"      # aviso: thin (P-01)
@dataclass(frozen=True)
class Problema:
    campo: str                  # ruta del campo: "nombre", "discos[1].ssd", "redes[0].vlan"
    codigo: str                 # "V-12" (regla) o subcódigo "V-14.thin"
    severidad: Severidad
    params: dict[str, str]
def validar_vm(cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades) -> list[Problema]
def validar_perfil(p: PerfilConexion) -> list[Problema]
def validar_token(texto: str) -> list[Problema]
def normalizar_host(texto: str) -> tuple[str, int | None]        # CA-07.8
def opciones_permitidas(disco: Disco, ctrl: ControladorScsi) -> OpcionesDisco  # CA-16.4
```

`opciones_permitidas` existe para que la interfaz **deshabilite** opciones inválidas en
lugar de mostrarlas y rechazarlas (CA-16.4).

## 5. Capa API

### 5.1 Transporte (`api/transporte.py`)
```python
class Transporte(Protocol):
    def peticion(self, metodo: str, ruta: str, *, params: dict | None = None,
                 datos: dict | None = None) -> Any        # devuelve el campo "data"
    @property
    def host_activo(self) -> str
```
Implementación `TransporteHttp` sobre `requests.Session`:
- **Huella fija:** adaptador HTTP con `assert_fingerprint` de urllib3 (SHA-256 guardada) y
  `cert_reqs=CERT_NONE`; si no coincide, `ErrorProxLaunch(HUELLA_CAMBIADA)`. Con
  `ignorar_ssl` no hay comprobación (RF-06).
- **Failover** por la lista de hosts solo ante errores de red (timeout, conexión rechazada,
  595/596), nunca ante 401/403 (CA-07.2/07.3/07.5).
- Timeouts: `TIMEOUT_CONEXION = 10`, `TIMEOUT_LECTURA = 30` (RNF-03).
- Cuerpo `application/x-www-form-urlencoded` codificado por `requests` (CT-9, RNF-16).
- Inyecta la autenticación mediante un objeto `Autenticador` (cabecera o cookie+CSRF).
- Registra petición/resultado **sin** cabeceras `Authorization`, `Cookie` ni `CSRFPreventionToken`.

`api/huella.py`: `obtener_huella(host, puerto, timeout) -> str` abre TLS **sin** enviar nada
y devuelve `AA:BB:...` (CA-05.1).

### 5.2 Autenticación (`api/autenticacion.py`)
```python
class Autenticador(Protocol):
    def aplicar(self, metodo: str, cabeceras: dict, cookies: dict) -> None
    def necesita_renovar(self) -> bool
    def renovar(self, transporte: Transporte) -> None

class AutenticadorToken(Autenticador)          # PVEAPIToken=...; nunca renueva (CA-03.4)
class AutenticadorTicket(Autenticador)         # cookie + CSRF en POST/PUT/DELETE (CA-02.3)
    # renueva con el ticket vigente como contraseña cuando quedan ≤ 15 min (CA-03.1)
    # NO guarda la contraseña (S-5, P-13)

def iniciar_sesion_ticket(transporte, usuario, realm, contrasena) -> Ticket | DesafioTFA
def responder_tfa(transporte, desafio: DesafioTFA, codigo: str, tipo: TipoTFA) -> Ticket
```
`DesafioTFA` describe los tipos ofrecidos; si no incluye TOTP ni recuperación →
`TFA_NO_SOPORTADO` (CA-04.5).

### 5.3 Cliente (`api/cliente.py`)
```python
class ClienteProxmox:
    def __init__(self, transporte: Transporte, auth: Autenticador, reloj: Reloj): ...
    def version(self) -> Version
    def estado_cluster(self) -> Topologia
    def nodos(self) -> list[Nodo]
    def storages(self, nodo: str) -> list[Storage]         # todos; el filtro "images" va en descubrimiento
    def bridges(self, nodo: str) -> list[Bridge]
    def proximo_vmid(self, sugerido: int | None = None) -> int   # /cluster/nextid[?vmid=]
    def permisos(self) -> dict[str, dict[str, int]]
    def crear_vm(self, nodo: str, parametros: dict[str, str]) -> str   # devuelve UPID
    def estado_tarea(self, nodo: str, upid: str) -> EstadoTarea
    def log_tarea(self, nodo: str, upid: str) -> list[str]
    def config_vm(self, nodo: str, vmid: int) -> dict | None
```
El resto del código solo usa `ClienteProxmox`; nadie más construye rutas de la API.

### 5.4 ADR-01 — RESUELTA: `requests` directo (D-17)

Ver `docs/decisiones.md` D-17 y `docs/investigacion/f1-api-proxmox.md`. Texto original:
D-05 eligió `proxmoxer`, pero el MVP 1 necesita control fino que podría no exponer:
huella fija (`assert_fingerprint`), 2FA en dos pasos interactivos, renovación sin guardar
la contraseña, failover de IPs y redacción de secretos en el registro. La interfaz
`Transporte`/`Autenticador` aísla esa elección: si `proxmoxer` permite inyectar la sesión y
la autenticación, se usa por debajo; si no, `TransporteHttp` usa `requests` directamente
(que ya es dependencia de `proxmoxer`). **Lo resuelve el `investigador` antes de implementar
la capa API** y se registra como D-17.

## 6. Constructor de la petición (`constructor_peticion.py`)
```python
def construir_parametros(cfg: ConfiguracionVM, inv: Inventario) -> dict[str, str]
```
- Índices consecutivos por bus (CA-16.2); `scsihw` solo si hay discos scsi (V-10).
- `format=` solo cuando el storage admite elegir y no es AUTO (V-09); con AUTO: qcow2 en
  dir/nfs/cifs, nada en backends raw (P-06).
- `ssd` omitido en virtio; `iothread` solo si V-11 lo permite.
- OVMF: `bios=ovmf`, `machine=q35`, `efidisk0=<st>:1,efitype=4m,pre-enrolled-keys=1` (P-10).
- `balloon` solo si `ballooning` no es `None` (CA-15.5).
- Devuelve **valores sin codificar**; la codificación del formulario la hace el transporte.
- Es una función pura: es el corazón de las pruebas del CA-19.3.

## 7. Servicios (orquestan el núcleo)

```python
class ServicioConexion:
    def __init__(self, transporte_fabrica, huellas: RepositorioHuellas,
                 secretos: AlmacenSecretos, reloj: Reloj): ...
    def preparar(self, perfil: PerfilConexion) -> EstadoHuella   # NUEVA | CONFIRMADA | CAMBIADA
    def confiar_huella(self, perfil, host, huella) -> None
    def conectar(self, perfil, credencial) -> Sesion | DesafioTFA
    def completar_tfa(self, desafio, codigo, tipo) -> Sesion

@dataclass
class Sesion:
    perfil: PerfilConexion; cliente: ClienteProxmox; version: Version
    capacidades: Capacidades; host_activo: str; usuario_efectivo: str

def descubrir(sesion: Sesion) -> Inventario             # nodos en paralelo (RNF-12)
def descubrir_nodo(sesion: Sesion, nodo: str) -> tuple[list[Storage], list[Bridge]]  # CA-11.7

class ServicioCreacion:
    def __init__(self, sesion: Sesion, reloj: Reloj, intervalo_s=1.5, max_espera_s=600): ...
    def crear(self, cfg: ConfiguracionVM, inv: Inventario,
              al_cambiar_etapa: Callable[[Etapa], None],
              cancelado: threading.Event) -> ResultadoCreacion
```
`ServicioCreacion.crear` implementa la máquina de etapas de RF-20: valida → envía → sondea
(con tolerancia a fallos de red de hasta 60 s, CA-20.7) → comprueba `config_vm` → resultado.
No borra nada al fallar (CA-20.10).

## 8. Capacidades por versión (`capacidades.py`)
```python
VERSION_MINIMA = (8, 0)
@dataclass(frozen=True)
class Capacidades:
    version: tuple[int, int]; forzada: bool
    def tiene(self, funcion: Funcion) -> bool
    def requisito(self, funcion: Funcion) -> tuple[int, int]      # para "Requiere 8.2..."
TABLA: dict[Funcion, tuple[int, int]] = { ... }    # único lugar (CA-09.6)
def capacidades_para(version: Version, forzada: tuple[int, int] | None) -> Capacidades
```
En el MVP 1 la tabla tiene pocas entradas; existe para que el MVP 4 (importaciones) añada
filas sin tocar otro código.

## 9. Persistencia
- Carpeta: `platformdirs.user_config_dir("ProxLaunch")`; log en `user_log_dir`.
- `perfiles.json`, `huellas.json` (`{"host:puerto": "AA:BB..."}`), `preferencias.json`.
- `AlmacenJson`: escritura atómica (temporal + `os.replace`); si el JSON está dañado,
  lo renombra a `*.danado-<fecha>` y empieza vacío (RNF-15).
- `AlmacenSecretos`: `keyring` con servicio `ProxLaunch` y clave `perfil:<id>`; detecta el
  backend nulo o fallido y devuelve `LLAVERO_NO_DISPONIBLE` (CA-08.4).

## 10. Interfaz (PySide6)

- **Hilos:** `Trabajador(QRunnable)` ejecuta una función del núcleo y emite
  `terminado(resultado)` o `fallo(ErrorProxLaunch)` por un `QObject` de señales. La
  cancelación usa `threading.Event`. Solo el hilo principal toca widgets.
- **Ventana principal:** barra superior (logo, perfil, versión, topología, indicador SSL),
  formulario de MV en secciones (General, Firmware, Cómputo, Discos, Red), panel de resumen y
  panel de progreso por etapas.
- **Modo básico/avanzado:** cada widget avanzado se registra en una lista; el cambio de modo
  solo cambia su visibilidad (CA-24.5: se ocultan, no se restablecen).
- **Tema:** `paleta.py` define `TOKENS_OSCURO` y `TOKENS_CLARO`; `plantilla.qss` usa
  `{{token}}`; `GestorTema` aplica la QSS, sigue `QStyleHints.colorSchemeChanged` en
  Automático y usa oscuro como respaldo (P-14). Una prueba calcula el contraste WCAG de los
  pares texto/fondo (CA-22.5).
- **Textos:** todo texto visible pasa por `self.tr()`/`QCoreApplication.translate`;
  `textos.py` traduce los códigos del núcleo. Fuentes incluidas con `QFontDatabase`.

## 11. Dependencias

| Paquete | Uso |
|---|---|
| PySide6-Essentials ≥ 6.11 | Interfaz |
| requests (+ urllib3) | HTTP con huella fija (D-17) |
| keyring | Llavero del sistema |
| platformdirs | Carpetas de usuario |
| **Desarrollo:** pytest, pytest-qt, responses, pytest-socket, ruff, mypy | Pruebas, mocks HTTP, bloqueo de red, estilo y tipos |

Python mínimo 3.11 (en el equipo de desarrollo hay 3.14; los instaladores del MVP 5 llevan
su propio intérprete, por eso Ubuntu 22.04 con Python 3.10 del sistema no es un problema).

## 12. Plan de implementación

| Fase | Responsable | Depende de | Entregable |
|---|---|---|---|
| F0 Entorno y esqueleto | `devops-ci` | — | `pyproject.toml`, venv, estructura vacía, ruff/pytest configurados, `.claude/proyecto/*.md` (solo local desde el 2026-11-21) |
| F1 ADR-01 proxmoxer | `investigador` | — | D-17 con fuentes |
| F2a Modelos, validación, constructor, capacidades, valores por defecto | `implementador` | F0 | `nucleo/modelos`, `validacion.py`, `constructor_peticion.py`, `capacidades.py` |
| F2b Persistencia, secretos, registro, reloj | `implementador` | F0 | `nucleo/persistencia`, `registro.py`, `reloj.py` |
| F2c Tema, paleta, QSS, recursos | `implementador` | F0 | `interfaz/tema`, `recursos/` |
| F3 Capa API y servicios | `implementador` | F1, F2a | `nucleo/api`, `nucleo/servicios` |
| F4 Interfaz y trabajadores | `implementador` | F2*, F3 | `interfaz/` |
| F5 Pruebas | `probador` | cada fase | pruebas derivadas de los CA; suite verde |
| F6 Laboratorio | `probador` + `investigador` | reinicio del equipo | respuestas reales capturadas; permisos verificados |
| F7 Revisión | `revisor-qa` + `auditor-seguridad` | F4, F5 | hallazgos corregidos |
| F8 Documentación | `documentador` + `formateador` | F7 | README, guía de usuario, bitácora |

F0 y F1 corren en paralelo; F2a, F2b y F2c también.

---

## Anexo A · Firmas añadidas durante F2 (aprobadas por el orquestador, 2026-11-11)

Firmas que la arquitectura no fijaba y que los implementadores definieron; son públicas
y estables desde ahora.

**Núcleo**
- `capacidades.interpretar_version(texto) -> tuple[Version, bool]`: el `bool` indica
  formato inesperado (CA-09.5). `Capacidades.es_soportada()` bloquea < 8.0 (CA-09.2).
- `seleccion_nodo.elegir_nodo(inv, espacio_requerido_gib) -> tuple[str, MotivoNodo]`;
  `MotivoNodo`: `UNICO_CANDIDATO`, `MAS_MEMORIA_LIBRE`, `DESEMPATE_ESPACIO_LIBRE`. Lanza
  `NODO_NO_DISPONIBLE` o `SIN_ESPACIO`.
- `modelos.tarea.EstadoTarea(estado, exitstatus)` con la propiedad `terminada`.
- `validacion`: `OpcionesDisco`, `formatos_permitidos(tipo)`, `storage_efi_efectivo`,
  `nombre_dns_valido`, `validar_codigo_totp`.
- Constantes "por verificar en laboratorio": `EFIDISK_*` en `constructor_peticion.py` y
  `BUSES_CON_DISCARD` (sin `ide`, criterio conservador) en `validacion.py`.
- Con SeaBIOS no se envía `bios` (CA-14.1).

**Persistencia**
- `Rutas(base=None)`; `AlmacenJson(ruta).leer() -> ResultadoLectura(datos, hubo_corrupcion, copia_danada)`.
- `RepositorioPerfiles`: `listar`, `obtener`, `guardar`, `duplicar(id, nombre)` (nombre
  obligatorio: lo pone la interfaz con `tr()`), `eliminar`, `huellas_huerfanas`,
  `eliminar_con_dependencias(id, secretos, huellas)`.
- `RepositorioHuellas.guardar` lanza `HUELLA_CAMBIADA` si ya hay otra; `reemplazar` es la
  vía de P-12.
- `registro`: `configurar_registro`, `registrar_secreto`, `olvidar_secretos` (las pruebas
  deben llamarla entre casos), `enmascarar`, `FiltroSecretos`.
- `RelojReal.ahora()` usa `time.monotonic()` (solo para diferencias, no es hora de pared).

**Interfaz / tema**
- `GestorTema(app, modo=ModoTema.AUTOMATICO)`: `modo`, `tema_actual`,
  `establecer_modo`, `aplicar`, señal `tema_cambiado(str)`.
- `generar_qss(plantilla, tokens)` (lanza `KeyError` ante un token inexistente),
  `leer_plantilla()`, `cargar_fuentes() -> (familia_interfaz, familia_mono)`.
- Propiedades QSS: `mono`, `primario`, `secundario`, `enlace`, `error`, `aviso`, `exito`,
  `invalido`; objeto `#BarraSuperior`. `app.py` debe llamar `QApplication.setFont` con la
  familia de interfaz.
- El texto deshabilitado queda fuera de la verificación de contraste (exención WCAG 1.4.3).

## Anexo B · Firmas añadidas durante F3 (aprobadas por el orquestador, 2026-11-11)

- `Transporte.usar_autenticador(auth)`; `crear_transporte_http` (fábrica de producción);
  `AdaptadorHuella`; `TransporteHttp.cerrar()`. Todas las peticiones usan `verify=False`
  porque la verificación real la hace la huella (con `verify=True` requests anularía
  `cert_reqs`). Un `ReadTimeout` en POST/PUT/DELETE **no** hace failover (evita duplicar).
- `iniciar_sesion_ticket(..., *, reloj=None)`, `responder_tfa(..., *, reloj=None)`;
  `DesafioTFA`, `TipoTFA` (`totp`, `recovery`); `normalizar_usuario`.
- Un 401 se traduce según el contexto: login o token → `CREDENCIALES_INVALIDAS`; sesión con
  ticket o renovación → `SESION_EXPIRADA`; paso 2 del 2FA → `TFA_CODIGO_INCORRECTO`.
- `ServicioConexion(..., obtener_huella_fn)`; `FabricaTransporte`;
  `conectar(..., *, version_forzada=None)`; `consultar_huellas(perfil) -> InformacionHuella`
  por host; `reemplazar_huella` (P-12); `EstadoHuella.IGNORADA`.
- `Sesion.avisos: list[Aviso]` con `CodigoAviso`: `LLAVERO_NO_DISPONIBLE`,
  `TOPOLOGIA_DEGRADADA` (A-6) y `PERMISOS_INCOMPLETOS`; `permisos_faltantes(sesion)` (RF-12).
- Durante el 2FA, la contraseña se conserva en memoria **solo** si el perfil tiene
  "Recordar credenciales" marcado, y se descarta al terminar.
- `Desenlace.CANCELADO` (añadido por el orquestador): cancelar no es un error y no borra nada.
- VMID ocupado: `error.params["siguiente"]` lleva el próximo VMID libre.
