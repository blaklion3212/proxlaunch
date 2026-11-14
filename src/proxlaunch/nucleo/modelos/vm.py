"""Modelos de la configuración de la MV: ConfiguracionVM, Disco, InterfazRed y enumeraciones."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    DetalleOrigen,
    ModoClon,
    RefPlantilla,
    RefVolumen,
    TipoSO,
)


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
    """Origen del sistema operativo (MVP 4: cuatro valores)."""

    DISCO_VACIO = "disco_vacio"
    ISO = "iso"
    IMPORTAR_DISCO = "importar_disco"
    CLONAR_PLANTILLA = "clonar_plantilla"


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


def _ref_volumen_a_dict(r: RefVolumen) -> dict[str, Any]:
    return {"nombre": r.nombre, "volid": r.volid}


def _ref_volumen_desde_dict(d: dict[str, Any]) -> RefVolumen:
    return RefVolumen(nombre=d.get("nombre", ""), volid=d.get("volid"))


def _detalle_a_dict(detalle: DetalleOrigen) -> dict[str, Any]:
    """Serializa el detalle del origen (ida y vuelta de ``a_dict``, CA-O01.5)."""
    if isinstance(detalle, DetalleIso):
        return {
            "iso": _ref_volumen_a_dict(detalle.iso),
            "drivers": None if detalle.drivers is None else _ref_volumen_a_dict(detalle.drivers),
            "sin_drivers": detalle.sin_drivers,
        }
    if isinstance(detalle, DetalleImportacion):
        return {
            "imagen": _ref_volumen_a_dict(detalle.imagen),
            "ampliar_a_gib": detalle.ampliar_a_gib,
            "tamano_virtual_bytes": detalle.tamano_virtual_bytes,
        }
    a = detalle.ajustes
    return {
        "plantilla": {
            "nombre": detalle.plantilla.nombre,
            "vmid": detalle.plantilla.vmid,
            "nodo": detalle.plantilla.nodo,
        },
        "modo": str(detalle.modo),
        "ajustes": {
            "sockets": a.sockets,
            "cores": a.cores,
            "tipo_cpu": a.tipo_cpu,
            "memoria_mib": a.memoria_mib,
            "disco_gib": a.disco_gib,
        },
        "storage_destino": detalle.storage_destino,
        "modo_efectivo": None if detalle.modo_efectivo is None else str(detalle.modo_efectivo),
    }


def _detalle_desde_dict(origen: OrigenSO, d: dict[str, Any]) -> DetalleOrigen:
    """Reconstruye el detalle según el origen; valida enums."""
    if origen == OrigenSO.ISO:
        drivers = d.get("drivers")
        return DetalleIso(
            iso=_ref_volumen_desde_dict(d.get("iso", {})),
            drivers=None if drivers is None else _ref_volumen_desde_dict(drivers),
            sin_drivers=bool(d.get("sin_drivers", False)),
        )
    if origen == OrigenSO.IMPORTAR_DISCO:
        return DetalleImportacion(
            imagen=_ref_volumen_desde_dict(d.get("imagen", {})),
            ampliar_a_gib=d.get("ampliar_a_gib"),
            tamano_virtual_bytes=d.get("tamano_virtual_bytes"),
        )
    p = d.get("plantilla", {})
    a = d.get("ajustes", {})
    efectivo = d.get("modo_efectivo")
    return DetalleClon(
        plantilla=RefPlantilla(nombre=p.get("nombre", ""), vmid=p.get("vmid"), nodo=p.get("nodo")),
        modo=_enum(ModoClon, d.get("modo", ModoClon.AUTOMATICO), "detalle_origen.modo"),
        ajustes=AjustesClon(
            sockets=a.get("sockets"),
            cores=a.get("cores"),
            tipo_cpu=a.get("tipo_cpu"),
            memoria_mib=a.get("memoria_mib"),
            disco_gib=a.get("disco_gib"),
        ),
        storage_destino=d.get("storage_destino"),
        modo_efectivo=(
            None if efectivo is None else _enum(ModoClon, efectivo, "detalle_origen.modo_efectivo")
        ),
    )


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
    # --- MVP 4 (al final y con valor por defecto) ---
    tipo_so: TipoSO | None = None  # None = sin asistente (M1–M3)
    tpm: bool = False  # tpmstate0 v2.0 (DT-O6, DT-O8)
    agente_qemu: bool = False  # agent=1 (CA-O13.11)
    detalle_origen: DetalleOrigen | None = None  # obligatorio si origen ≠ disco_vacio (V-O01)

    def __post_init__(self) -> None:
        # CA-18.2: cualquier origen distinto de "disco_vacio" es un error de validación.
        self.origen = _enum(OrigenSO, self.origen, "origen")
        if self.tipo_so is not None:
            self.tipo_so = _enum(TipoSO, self.tipo_so, "tipo_so")

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
        # Claves del MVP 4: solo si no tienen su valor por defecto (a_dict de M3 idéntico).
        if self.tipo_so is not None:
            datos["tipo_so"] = str(self.tipo_so)
        if self.tpm:
            datos["tpm"] = True
        if self.agente_qemu:
            datos["agente_qemu"] = True
        if self.detalle_origen is not None:
            datos["detalle_origen"] = _detalle_a_dict(self.detalle_origen)
        return datos

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> "ConfiguracionVM":
        """Reconstruye la configuración desde ``a_dict``. Valida enums y origen."""
        bal = d["ballooning"]
        origen = _enum(OrigenSO, d["origen"], "origen")
        tipo_so = d.get("tipo_so")
        detalle = d.get("detalle_origen")
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
            origen=origen,
            etiquetas=tuple(str(e) for e in d.get("etiquetas", ())),
            tipo_so=None if tipo_so is None else _enum(TipoSO, tipo_so, "tipo_so"),
            tpm=bool(d.get("tpm", False)),
            agente_qemu=bool(d.get("agente_qemu", False)),
            detalle_origen=None if detalle is None else _detalle_desde_dict(origen, detalle),
        )
