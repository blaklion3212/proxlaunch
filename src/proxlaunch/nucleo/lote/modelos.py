"""Modelos del lote: definición, plan, libro y rollback (docs/arquitectura/mvp2.md §3).

Contrato común entre planificación, motor, rollback, informe e interfaz. Todos los
modelos son inmutables salvo el ``Libro`` (en ``libro.py``), que guarda instantáneas.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.transferencias.modelos import RegistroTransferencia


class ModoDestino(StrEnum):
    AUTOMATICO = "automatico"
    UN_NODO = "un_nodo"
    NODOS_ELEGIDOS = "nodos_elegidos"


class Algoritmo(StrEnum):
    EQUILIBRADO = "equilibrado"
    POR_TURNOS = "por_turnos"


class PoliticaThin(StrEnum):
    """Política de sobreasignación en storages thin (D-20: CONFIRMAR_CON_TOPE)."""

    BLOQUEAR = "bloquear"
    ADVERTIR = "advertir"
    CONFIRMAR_CON_TOPE = "confirmar_con_tope"


class Severidad(StrEnum):
    ERROR = "error"
    AVISO = "aviso"
    AVISO_CONFIRMABLE = "aviso_confirmable"  # exige casilla (CA-L08.2)


@dataclass(frozen=True)
class PatronNombres:
    prefijo: str
    separador: str = "-"
    inicio: int = 1
    relleno: int = 2


@dataclass(frozen=True)
class Destino:
    modo: ModoDestino = ModoDestino.AUTOMATICO
    nodos: tuple[str, ...] = ()  # UN_NODO: 1 nodo; NODOS_ELEGIDOS: ≥ 1
    algoritmo: Algoritmo = Algoritmo.EQUILIBRADO


@dataclass(frozen=True)
class FilaLote:
    """Una MV de un lote por filas (D-22).

    El hardware, storage y bridge son los de ``cfg``; ``cfg.vmid``, ``cfg.nombre``
    y ``cfg.nodo`` se ignoran (los fija el plan); ``cfg.etiquetas`` se conserva y el plan
    le suma las del lote. ``cfg`` es mutable
    (M1): no se muta nunca dentro de este modelo; se copia con ``copy.deepcopy``.
    """

    nombre: str
    cfg: ConfiguracionVM
    vmid: int | None = None  # explícito (CA-C08.3); None = siguiente libre
    nodo: str | None = None  # explícito (CA-C08.4); None = reparto automático
    origen: int | None = None  # nº de fila del CSV (Excel) o posición en el archivo; solo mostrar


@dataclass(frozen=True)
class DefinicionLote:
    """Lo que el usuario pide. ``plantilla.vmid/nombre/nodo`` se ignoran.

    Homogéneo (``filas`` vacío): ``plantilla`` es la configuración de todas las MVs.
    Por filas (``filas`` no vacío, D-22): ``plantilla`` es solo informativa (perfil base) y
    ningún cálculo la lee; ``cantidad`` debe ser ``len(filas)`` (V-L01), ``patron`` se ignora
    y ``destino`` es siempre automático (V-L13).
    """

    plantilla: ConfiguracionVM
    cantidad: int
    patron: PatronNombres
    destino: Destino = field(default_factory=Destino)
    vmid_inicial: int | None = None  # None = /cluster/nextid
    etiquetar: bool = True  # D-20 (3)
    politica_thin: PoliticaThin = PoliticaThin.CONFIRMAR_CON_TOPE
    filas: tuple[FilaLote, ...] = ()  # vacío = homogéneo; no vacío = por filas (D-22)

    @property
    def es_por_filas(self) -> bool:
        return bool(self.filas)


@dataclass(frozen=True)
class Problema:
    """Resultado de una regla V-L (o V-xx de M1 aplicada a un elemento).

    ``regla``: id estable ("V-L09", "V-14"...); ``campo``: campo del formulario a
    señalar o None; ``indice``: elemento del plan afectado o None si es del lote.
    """

    regla: str
    severidad: Severidad
    campo: str | None = None
    params: dict[str, str] = field(default_factory=dict)
    indice: int | None = None


@dataclass(frozen=True)
class ElementoPlan:
    indice: int  # 0..N-1, orden del plan
    nombre: str
    vmid: int
    nodo: str
    cfg: ConfiguracionVM  # plantilla con vmid, nombre, nodo y etiquetas ya fijados


COMPARTIDO = "*compartido*"


@dataclass(frozen=True)
class ClavePresupuesto:
    """Clave de presupuesto de espacio: storage local por nodo o compartido (D-08)."""

    ambito: str  # nombre del nodo, o COMPARTIDO
    storage: str


@dataclass(frozen=True)
class UsoStorage:
    pedido_bytes: int
    libre_bytes: int
    thin: bool


@dataclass(frozen=True)
class Plan:
    id_lote: str  # 8 hex (CA-L20.3)
    definicion: DefinicionLote
    elementos: tuple[ElementoPlan, ...]
    vmids_saltados: tuple[int, ...]
    reparto: dict[str, tuple[int, str]]  # nodo -> (cantidad, motivo: valor de MotivoReparto)
    uso: dict[ClavePresupuesto, UsoStorage]
    problemas: tuple[Problema, ...]
    capacidad_maxima: int | None  # "Reducir a N" (CA-L07.7); None si no aplica
    generado_en: float  # reloj inyectado (V-L14)
    version_validacion: tuple[int, int]  # forzada o detectada (CA-L11.6)
    es_simulacion: bool = False
    permisos_verificados: bool = True  # falso si GET /access/permissions falló (CA-L09.4)
    filas_excedentes: tuple[int, ...] = ()  # índices que no caben (CA-C08.6), solo por filas
    catalogo: CatalogoServidor | None = None  # MVP 4: catálogo leído al planificar

    @property
    def bloqueado(self) -> bool:
        return any(p.severidad == Severidad.ERROR for p in self.problemas)

    @property
    def requiere_confirmacion_thin(self) -> bool:
        return any(p.severidad == Severidad.AVISO_CONFIRMABLE for p in self.problemas)


class MotivoReparto(StrEnum):
    UNICO_NODO = "unico_nodo"
    ELEGIDO_POR_USUARIO = "elegido_por_usuario"
    MAS_MEMORIA = "mas_memoria"  # Equilibrado
    MAS_ESPACIO = "mas_espacio"  # Equilibrado con memoria desconocida
    POR_TURNOS = "por_turnos"


class EstadoMV(StrEnum):
    # En curso
    PENDIENTE = "pendiente"
    VALIDANDO = "validando"
    ENVIANDO = "enviando"
    CREANDO = "creando"
    COMPROBANDO = "comprobando"
    AJUSTANDO = "ajustando"  # MVP 4: ajustes tras un clon
    # Finales = Desenlace de M1
    OK = "ok"
    CON_AVISOS = "con_avisos"
    ERROR = "error"
    PARCIAL = "parcial"
    TIEMPO_AGOTADO = "tiempo_agotado"
    CONEXION_PERDIDA = "conexion_perdida"
    # Finales nuevos
    NO_ENVIADA = "no_enviada"
    NO_CREADA_SEGURA = "no_creada_segura"
    EXISTE_SIN_CONFIRMAR_PROPIEDAD = "existe_sin_confirmar_propiedad"


ESTADOS_EN_CURSO = frozenset(
    {
        EstadoMV.PENDIENTE,
        EstadoMV.VALIDANDO,
        EstadoMV.ENVIANDO,
        EstadoMV.CREANDO,
        EstadoMV.COMPROBANDO,
        EstadoMV.AJUSTANDO,
    }
)
ESTADOS_DUDOSOS = frozenset({EstadoMV.CONEXION_PERDIDA, EstadoMV.TIEMPO_AGOTADO})


class MotivoNoEnviada(StrEnum):
    CANCELADO = "cancelado"
    PAUSA = "pausa"
    ERROR_GLOBAL = "error_global"
    NODO_CAIDO = "nodo_caido"


@dataclass(frozen=True)
class EntradaLibro:
    """Instantánea inmutable del estado de una MV del lote."""

    elemento: ElementoPlan
    estado: EstadoMV = EstadoMV.PENDIENTE
    upid: str | None = None
    error: ErrorProxLaunch | None = None
    motivo_no_enviada: MotivoNoEnviada | None = None
    post_intentado: bool = False  # INV-L1: True en cuanto se llama al POST
    t_inicio: float | None = None
    t_fin: float | None = None
    log_tarea: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()  # códigos de aviso (p. ej. "creada_tras_comprobar")


class MotivoPausa(StrEnum):
    ERROR_GLOBAL = "error_global"
    REPETIDO = "repetido"  # E-L07
    CONEXION = "conexion"  # E-L09


class EstadoRollback(StrEnum):
    PENDIENTE = "pendiente"
    COMPROBANDO = "comprobando"
    ELIMINANDO = "eliminando"
    ELIMINADA = "eliminada"
    YA_NO_EXISTIA = "ya_no_existia"
    FALLO = "fallo"  # E-L17
    OMITIDA = "omitida"  # no propia, encendida o bloqueada (E-L18..E-L20)
    INCIERTA = "incierta"  # E-L22
    NO_ENVIADA = "no_enviada"  # cancelado antes de procesarla


@dataclass(frozen=True)
class CandidatoRollback:
    entrada: EntradaLibro
    elegible: bool
    motivo: str | None  # código del motivo si no es elegible
    incompleta: bool  # para "Solo incompletas" (D-20 (1))


@dataclass(frozen=True)
class ResultadoRollback:
    vmid: int
    nodo: str
    nombre: str
    estado: EstadoRollback
    upid: str | None = None
    error: ErrorProxLaunch | None = None


class AccionPeticion(StrEnum):
    """Acción de una petición simulada (MVP 4: un clon implica varias peticiones)."""

    CREAR = "crear"
    CLONAR = "clonar"
    CONFIGURAR = "configurar"
    AMPLIAR = "ampliar"


@dataclass(frozen=True)
class PeticionSimulada:
    accion: AccionPeticion
    nodo: str
    parametros: dict[str, str]


@dataclass(frozen=True)
class ResultadoSimulacion:
    """Simulación (RF-L11): el plan y la petición exacta que se enviaría por VMID."""

    plan: Plan
    peticiones: dict[int, dict[str, str]]  # vmid -> parámetros del POST (sin secretos)
    version_detectada: tuple[int, int]
    version_forzada: tuple[int, int] | None
    # MVP 4: todas las peticiones por VMID (clon + ajustes); ``peticiones`` conserva la principal
    peticiones_detalle: dict[int, tuple[PeticionSimulada, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class MetadatosInforme:
    """Datos de contexto del informe; nunca host, IP ni usuario (CA-L19.3)."""

    nombre_perfil: str
    version_proxmox: str
    es_cluster: bool
    nombre_cluster: str | None
    fecha_hora_local: str  # ISO 8601, inyectada (determinismo)


@dataclass(frozen=True)
class InformeLote:
    """Informe estructurado (códigos, sin textos); la interfaz lo convierte en texto.

    En un lote por filas (``por_filas``) ``plantilla`` es solo informativa: la configuración
    real de cada MV está en ``entradas[i].elemento.cfg``.
    """

    metadatos: MetadatosInforme
    id_lote: str
    es_simulacion: bool
    pedidas: int
    contadores: dict[str, int]  # valor de EstadoMV -> cantidad
    entradas: tuple[EntradaLibro, ...]  # en orden del plan
    duraciones_s: dict[int, float]  # vmid -> segundos (si terminó)
    plantilla: ConfiguracionVM
    rollback: tuple[ResultadoRollback, ...] = ()
    problemas_plan: tuple[Problema, ...] = ()
    permisos_verificados: bool = True
    por_filas: bool = False  # la interfaz muestra la configuración de cada MV (CA-C08.8)
    # MVP 4: archivos subidos/descargados en la sesión
    transferencias: tuple[RegistroTransferencia, ...] = ()
