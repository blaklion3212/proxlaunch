"""Modelos del asistente «Crear plantilla desde imagen cloud» (B2, DT-B10). Solo datos, sin E/S.

B2 es una operación propia, no un lote: no usa el libro ni Deshacer (RF-B7.1). Tiene cinco pasos
que se pueden reanudar; el estado (``EstadoPlantillaImagen``) lo conserva quien llama (la
interfaz) entre ejecuciones. La contraseña de cloud-init NUNCA forma parte de B2 (PB-1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path

from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.transferencias.url import ChecksumTransferencia, UrlDescarga

# Extensiones que admite el contenido ``import`` (RF-B2.2) más ``.img`` (se renombra, RF-B2.3).
EXTENSIONES_IMAGEN = (".qcow2", ".img", ".raw", ".vmdk")
EXTENSIONES_IMPORT = (".qcow2", ".raw", ".vmdk")

# Avisos que deja el asistente en ``EstadoPlantillaImagen.avisos`` (códigos; los textos, la UI).
AVISO_SIN_AMPLIAR = "sin_ampliar"  # el tamaño final no supera el de la imagen: no hay ``resize``
AVISO_AJUSTE_DISCO_OMITIDO = "ajuste_omitido:disco"  # sin certeza de ``VM.Config.Disk``
AVISO_SE_ASUME_QCOW2 = "se_asume_qcow2"  # URL ``.img``: se pide ``.qcow2`` (R-B2)
AVISO_SIN_AGENTE_IMAGEN = "imagen_sin_agente"  # Ubuntu/Debian: la imagen no trae el agente
AVISO_CONSOLA_SERIE = "consola_serie"  # con ``vga=serial0`` noVNC queda en negro
AVISO_SOLO_CLON_COMPLETO = "solo_clon_completo"  # destino LVM grueso (DB-6)


class OrigenImagen(StrEnum):
    ARCHIVO_LOCAL = "archivo_local"
    URL = "url"
    YA_IMPORTADA = "ya_importada"


class AccionExistente(StrEnum):
    """Elección cuando ya hay un archivo con ese nombre en el almacenamiento ``import``."""

    USAR = "usar"
    REEMPLAZAR = "reemplazar"


class PasoB2(IntEnum):
    IMAGEN = 1
    CREAR = 2
    AMPLIAR = 3
    CLOUDINIT = 4
    CONVERTIR = 5


class EstadoPaso(StrEnum):
    PENDIENTE = "pendiente"
    EN_CURSO = "en_curso"
    HECHO = "hecho"
    FALLIDO = "fallido"
    OMITIDO = "omitido"
    INCIERTO = "incierto"


# Pasos ya resueltos: ``ejecutar`` nunca los repite.
PASOS_RESUELTOS = frozenset({EstadoPaso.HECHO, EstadoPaso.OMITIDO})


@dataclass(frozen=True)
class FijasPlantilla:
    """Casillas de «Opciones fijas para imágenes cloud» (RF-B2.7), todas marcadas por defecto."""

    unidad_cloudinit: bool = True  # ide2=<destino>:cloudinit
    consola_serie: bool = True  # serial0=socket y vga=serial0
    agente: bool = True  # agent=1 (va por ``cfg.agente_qemu``)


@dataclass(frozen=True)
class SolicitudPlantillaImagen:
    """Todo lo que pide el asistente. Inmutable; la contraseña no existe en B2.

    ``cfg`` lleva nombre, VMID, CPU, memoria, firmware/EFI y red; el tamaño final del disco va en
    ``cfg.detalle_origen.ampliar_a_gib`` (si no, en ``cfg.discos[0].tamano_gib``). ``cfg.nodo``
    se ignora: manda ``nodo``. ``nombre_archivo`` es el nombre FINAL (``.img`` ya renombrado).
    Los tres últimos campos son de la sesión y tienen valor por defecto.
    """

    origen: OrigenImagen
    ruta_local: Path | None
    url: UrlDescarga | None
    volid_existente: str | None
    suma: ChecksumTransferencia | None
    nodo: str
    storage_import: str
    nombre_archivo: str
    accion_existente: AccionExistente | None
    storage_destino: str
    cfg: ConfiguracionVM
    fijas: FijasPlantilla
    cloudinit: ConfigCloudInit | None  # ``contrasena`` siempre ``None``
    confirmada: bool  # casilla de irreversibilidad (RF-B2.9)
    # --- Datos de la sesión (la interfaz los obtiene al inspeccionar la imagen) ---
    tamano_virtual_bytes: int | None = None  # cabecera qcow2 de un archivo local; URL: ``None``
    acepta_aviso_raiz: bool = False  # casilla «la subida puede fallar» (CA-O10.4)
    verificar_certificados: bool = True  # solo URL


@dataclass
class EstadoPlantillaImagen:
    """Estado reanudable del asistente. Lo mutan ``ServicioPlantillaImagen`` y nadie más.

    ``vmid_reservado_aqui`` se activa en cuanto hay UPID de creación (o, tras una conexión
    perdida, cuando «Comprobar ahora» halla la máquina con el nombre pedido); ``vmid_reservado``
    y ``nombre_reservado`` guardan el VMID y el nombre con los que se creó.
    """

    pasos: dict[PasoB2, EstadoPaso] = field(
        default_factory=lambda: {p: EstadoPaso.PENDIENTE for p in PasoB2}
    )
    volid_imagen: str | None = None
    vmid_reservado_aqui: bool = False
    upid: str | None = None  # tarea del paso en curso o dudoso (descarga, creación, conversión)
    error: ErrorProxLaunch | None = None
    avisos: list[str] = field(default_factory=list)
    # --- Datos de la máquina creada (los fija el servicio) ---
    vmid_reservado: int | None = None
    nombre_reservado: str | None = None
    nodo_reservado: str | None = None

    @property
    def completo(self) -> bool:
        """Los cinco pasos están resueltos (hechos u omitidos)."""
        return all(e in PASOS_RESUELTOS for e in self.pasos.values())

    @property
    def paso_pendiente(self) -> PasoB2 | None:
        """Primer paso sin resolver, o ``None`` si ya terminó."""
        return next((p for p in PasoB2 if self.pasos[p] not in PASOS_RESUELTOS), None)

    @property
    def es_plantilla(self) -> bool:
        """La conversión (paso 5) se hizo."""
        return self.pasos[PasoB2.CONVERTIR] == EstadoPaso.HECHO

    def copia(self) -> EstadoPlantillaImagen:
        """Copia independiente (los avisos y los pasos no se comparten) para entregar a la
        interfaz desde otro hilo."""
        return EstadoPlantillaImagen(
            pasos=dict(self.pasos),
            volid_imagen=self.volid_imagen,
            vmid_reservado_aqui=self.vmid_reservado_aqui,
            upid=self.upid,
            error=self.error,
            avisos=list(self.avisos),
            vmid_reservado=self.vmid_reservado,
            nombre_reservado=self.nombre_reservado,
            nodo_reservado=self.nodo_reservado,
        )


@dataclass(frozen=True)
class CondicionesBorrado:
    """Resultado de comprobar si se puede ofrecer «Borrar la máquina a medio crear» (RF-B2.10).

    ``ok`` solo es ``True`` si se cumplen TODAS las condiciones. Si no, ``error`` dice cuál
    falla (``ROLLBACK_NO_PROPIA``, ``ROLLBACK_ENCENDIDA``, ``ROLLBACK_BLOQUEADA``,
    ``ROLLBACK_PROTEGIDA`` o ``PERMISO_INSUFICIENTE``) y ``sin_certeza`` indica que alguna
    lectura falló (no se ofrece, por prudencia).
    """

    ok: bool
    error: ErrorProxLaunch | None = None
    sin_certeza: bool = False
