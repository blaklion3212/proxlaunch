"""Modelos de la configuración de la MV: ConfiguracionVM, Disco, InterfazRed y enumeraciones."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch


class Firmware(StrEnum):
    SEABIOS = "seabios"
    OVMF = "ovmf"


class Bus(StrEnum):
    SCSI = "scsi"
    VIRTIO = "virtio"
    SATA = "sata"
    IDE = "ide"


class FormatoDisco(StrEnum):
    """Formato de disco. Nunca ``subvol`` (es de contenedores, CT-1)."""

    AUTO = "auto"
    RAW = "raw"
    QCOW2 = "qcow2"


class ModeloRed(StrEnum):
    VIRTIO = "virtio"
    E1000 = "e1000"


class ControladorScsi(StrEnum):
    VIRTIO_SINGLE = "virtio-scsi-single"
    VIRTIO_PCI = "virtio-scsi-pci"


class OrigenSO(StrEnum):
    """Origen del sistema operativo. El MVP 4 añadirá más valores."""

    DISCO_VACIO = "disco_vacio"


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


def _enum(tipo: type[StrEnum], valor: Any, campo: str) -> Any:
    """Convierte ``valor`` al enum o lanza ``ErrorProxLaunch`` con el campo afectado."""
    try:
        return tipo(valor)
    except ValueError:
        raise ErrorProxLaunch(
            CodigoError.PARAMETRO_INVALIDO, {"campo": campo, "valor": str(valor)}
        ) from None


@dataclass
class ConfiguracionVM:
    vmid: int
    nombre: str
    nodo: str
    firmware: Firmware = Firmware.SEABIOS
    storage_efi: str | None = None  # None = el del primer disco (CA-14.2)
    sockets: int = 1
    cores: int = 2
    tipo_cpu: str = "x86-64-v2-AES"
    memoria_mib: int = 2048
    ballooning: Ballooning | None = None  # None = no enviar (modo básico, CA-15.5)
    con_disco: bool = True
    discos: list[Disco] = field(default_factory=list)
    controlador_scsi: ControladorScsi = ControladorScsi.VIRTIO_SINGLE
    redes: list[InterfazRed] = field(default_factory=list)
    origen: OrigenSO = OrigenSO.DISCO_VACIO
    etiquetas: tuple[str, ...] = ()  # MVP 2: marca de propiedad del lote (RF-L24)

    def __post_init__(self) -> None:
        # CA-18.2: cualquier origen distinto de "disco_vacio" es un error de validación.
        self.origen = _enum(OrigenSO, self.origen, "origen")

    def a_dict(self) -> dict[str, Any]:
        """Serializa a un diccionario JSON-compatible (ida y vuelta, CA-18.3)."""
        datos: dict[str, Any] = {
            "vmid": self.vmid,
            "nombre": self.nombre,
            "nodo": self.nodo,
            "firmware": str(self.firmware),
            "storage_efi": self.storage_efi,
            "sockets": self.sockets,
            "cores": self.cores,
            "tipo_cpu": self.tipo_cpu,
            "memoria_mib": self.memoria_mib,
            "ballooning": (
                None
                if self.ballooning is None
                else {
                    "activo": self.ballooning.activo,
                    "minimo_mib": self.ballooning.minimo_mib,
                }
            ),
            "con_disco": self.con_disco,
            "discos": [
                {
                    "storage": d.storage,
                    "tamano_gib": d.tamano_gib,
                    "bus": str(d.bus),
                    "formato": str(d.formato),
                    "discard": d.discard,
                    "ssd": d.ssd,
                    "iothread": d.iothread,
                }
                for d in self.discos
            ],
            "controlador_scsi": str(self.controlador_scsi),
            "redes": [
                {"bridge": r.bridge, "modelo": str(r.modelo), "vlan": r.vlan} for r in self.redes
            ],
            "origen": str(self.origen),
        }
        if self.etiquetas:  # solo si existen: el formato de M1 no cambia
            datos["etiquetas"] = list(self.etiquetas)
        return datos

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> "ConfiguracionVM":
        """Reconstruye la configuración desde ``a_dict``. Valida enums y origen."""
        bal = d["ballooning"]
        return cls(
            vmid=d["vmid"],
            nombre=d["nombre"],
            nodo=d["nodo"],
            firmware=_enum(Firmware, d["firmware"], "firmware"),
            storage_efi=d["storage_efi"],
            sockets=d["sockets"],
            cores=d["cores"],
            tipo_cpu=d["tipo_cpu"],
            memoria_mib=d["memoria_mib"],
            ballooning=None if bal is None else Ballooning(bal["activo"], bal["minimo_mib"]),
            con_disco=d["con_disco"],
            discos=[
                Disco(
                    storage=x["storage"],
                    tamano_gib=x["tamano_gib"],
                    bus=_enum(Bus, x["bus"], "discos.bus"),
                    formato=_enum(FormatoDisco, x["formato"], "discos.formato"),
                    discard=x["discard"],
                    ssd=x["ssd"],
                    iothread=x["iothread"],
                )
                for x in d["discos"]
            ],
            controlador_scsi=_enum(ControladorScsi, d["controlador_scsi"], "controlador_scsi"),
            redes=[
                InterfazRed(
                    bridge=x["bridge"],
                    modelo=_enum(ModeloRed, x["modelo"], "redes.modelo"),
                    vlan=x["vlan"],
                )
                for x in d["redes"]
            ],
            origen=d["origen"],
            etiquetas=tuple(str(e) for e in d.get("etiquetas", ())),
        )
