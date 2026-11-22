"""Modelos de seguimiento de la creación: etapas, desenlaces y resultado."""

from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.errores import ErrorProxLaunch


class Etapa(StrEnum):
    """Etapas de la barra de progreso (CA-20.2)."""

    VALIDANDO = "validando"
    ENVIANDO = "enviando"
    CREANDO = "creando"
    COMPROBANDO = "comprobando"
    AJUSTANDO = "ajustando"  # MVP 4: ajustes tras un clon (etiquetas, CPU, disco)
    ENCENDIENDO = "encendiendo"  # fase A: status/start tras los ajustes
    LISTO = "listo"


class Desenlace(StrEnum):
    """Resultado final de una creación."""

    OK = "ok"
    CON_AVISOS = "con_avisos"
    ERROR = "error"
    TIEMPO_AGOTADO = "tiempo_agotado"
    CONEXION_PERDIDA = "conexion_perdida"
    PARCIAL = "parcial"
    # El usuario canceló: antes del envío no se creó nada; durante el seguimiento la
    # tarea puede seguir en Proxmox (no se borra nada).
    CANCELADO = "cancelado"


@dataclass(frozen=True)
class EstadoTarea:
    """Estado de una tarea de Proxmox (``/tasks/{upid}/status``).

    ``estado`` es ``running`` o ``stopped``; ``exitstatus`` solo existe al terminar
    (``OK`` o el texto del error).
    """

    estado: str
    exitstatus: str | None = None

    @property
    def terminada(self) -> bool:
        return self.estado == "stopped"


@dataclass
class ResultadoCreacion:
    """Resultado de ``ServicioCreacion.crear``."""

    desenlace: Desenlace
    vmid: int
    nodo: str
    upid: str | None
    error: ErrorProxLaunch | None
    log_tarea: list[str] = field(default_factory=list)
    # MVP 4: códigos de aviso, p. ej. «ajuste_pendiente:etiquetas|cpu_memoria|disco».
    # Fase A: también "encendido_fallido", "encendido_omitido" y "notas_plantilla_ilegible".
    avisos: tuple[str, ...] = ()
