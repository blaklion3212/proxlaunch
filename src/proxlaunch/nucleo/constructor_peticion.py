"""Construcción de los parámetros de la API para crear una MV (RF-19, CA-19.3).

Función pura: devuelve valores SIN codificar; la codificación del formulario la hace
el transporte (CT-9).
"""

from proxlaunch.nucleo.capacidades import admite_etiquetas
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    Disco,
    Firmware,
    FormatoDisco,
)
from proxlaunch.nucleo.validacion import (
    TIPOS_STORAGE_QCOW2,
    formatos_permitidos,
    opciones_permitidas,
    storage_efi_efectivo,
)

# Forma del efidisk0 (P-10, CT-7). Valores por verificar en laboratorio.
EFIDISK_TAMANO = "1"  # por verificar en laboratorio
EFIDISK_TIPO = "4m"  # por verificar en laboratorio
EFIDISK_CLAVES_PRECARGADAS = "1"  # por verificar en laboratorio
# Si el efidisk también lleva ``format=`` en dir/nfs/cifs (CA-14.3).
EFIDISK_CON_FORMATO = True  # por verificar en laboratorio
MAQUINA_OVMF = "q35"


def _formato_a_enviar(
    inv: Inventario, nodo: str, id_storage: str, formato: FormatoDisco
) -> str | None:
    """Valor de ``format=`` según V-09 y P-06, o ``None`` si no se envía."""
    tipo = next((s.tipo for s in inv.storages.get(nodo, ()) if s.id == id_storage), None)
    if tipo is None:
        return None  # storage desconocido: la validación lo marca; no se envía formato
    permitidos = formatos_permitidos(tipo)
    if len(permitidos) == 1:
        return None  # backends raw: no se envía format
    if formato == FormatoDisco.AUTO:
        return FormatoDisco.QCOW2.value if tipo in TIPOS_STORAGE_QCOW2 else None
    return formato.value if formato in permitidos else None


def _valor_disco(cfg: ConfiguracionVM, inv: Inventario, d: Disco) -> str:
    """Valor de ``scsi0=...``: ``<storage>:<GiB>,discard=on,ssd=1,iothread=1[,format=...]``."""
    op = opciones_permitidas(d, cfg.controlador_scsi)
    partes = [f"{d.storage}:{d.tamano_gib}"]
    if d.discard and op.discard:
        partes.append("discard=on")
    if d.ssd and op.ssd:
        partes.append("ssd=1")
    if d.iothread and op.iothread:
        partes.append("iothread=1")
    formato = _formato_a_enviar(inv, cfg.nodo, d.storage, d.formato)
    if formato is not None:
        partes.append(f"format={formato}")
    return ",".join(partes)


def construir_parametros(
    cfg: ConfiguracionVM, inv: Inventario, version: tuple[int, int] | None = None
) -> dict[str, str]:
    """Convierte la configuración en los parámetros de ``POST /nodes/{nodo}/qemu``.

    ``version`` (opcional) es la versión contra la que se construye; sin ella se asume que
    admite etiquetas. Sin etiquetas la petición es idéntica a la del MVP 1.
    """
    discos = cfg.discos if cfg.con_disco else []
    params: dict[str, str] = {"vmid": str(cfg.vmid), "name": cfg.nombre}

    if cfg.firmware == Firmware.OVMF:
        params["bios"] = "ovmf"
        params["machine"] = MAQUINA_OVMF
        id_efi = storage_efi_efectivo(cfg, inv, discos)
        if id_efi is None:
            raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "storage_efi"})
        efi = (
            f"{id_efi}:{EFIDISK_TAMANO},efitype={EFIDISK_TIPO},"
            f"pre-enrolled-keys={EFIDISK_CLAVES_PRECARGADAS}"
        )
        if EFIDISK_CON_FORMATO:
            formato = _formato_a_enviar(inv, cfg.nodo, id_efi, FormatoDisco.AUTO)
            if formato is not None:
                efi += f",format={formato}"
        params["efidisk0"] = efi

    params["sockets"] = str(cfg.sockets)
    params["cores"] = str(cfg.cores)
    params["cpu"] = cfg.tipo_cpu
    params["memory"] = str(cfg.memoria_mib)
    if cfg.ballooning is not None:
        params["balloon"] = str(cfg.ballooning.minimo_mib) if cfg.ballooning.activo else "0"

    if any(d.bus == Bus.SCSI for d in discos):
        params["scsihw"] = cfg.controlador_scsi.value
    contadores: dict[Bus, int] = {}
    for d in discos:
        indice = contadores.get(d.bus, 0)
        contadores[d.bus] = indice + 1
        params[f"{d.bus.value}{indice}"] = _valor_disco(cfg, inv, d)

    for i, r in enumerate(cfg.redes):
        valor = f"{r.modelo.value},bridge={r.bridge}"
        if r.vlan is not None:
            valor += f",tag={r.vlan}"
        params[f"net{i}"] = valor
    if cfg.etiquetas and (version is None or admite_etiquetas(version)):
        params["tags"] = ";".join(cfg.etiquetas)
    return params
