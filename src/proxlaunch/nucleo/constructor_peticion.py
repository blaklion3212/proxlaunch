"""Construcción de los parámetros de la API para crear una MV (RF-19, CA-19.3).

Función pura: devuelve valores SIN codificar; la codificación del formulario la hace
el transporte (CT-9).
"""

from proxlaunch.nucleo.capacidades import admite_etiquetas
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, DetalleIso, TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    Disco,
    Firmware,
    FormatoDisco,
    OrigenSO,
)
from proxlaunch.nucleo.origen.asistente import TABLA_SO
from proxlaunch.nucleo.origen.constantes import (
    ORDEN_ARRANQUE,
    RANURA_DRIVERS,
    RANURA_ISO,
    RANURAS_IDE_CON_ISO,
    VERSION_TPM,
)
from proxlaunch.nucleo.origen.nombres import validar_volid
from proxlaunch.nucleo.origen.permisos import estado_privilegio
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


def _valor_disco(
    cfg: ConfiguracionVM, inv: Inventario, d: Disco, import_from: str | None = None
) -> str:
    """Valor de ``scsi0=...``: ``<storage>:<GiB>,discard=on,ssd=1,iothread=1[,format=...]``.

    Con ``import_from`` (importación, I4-§C) el disco es ``<storage>:0,import-from=<volid>,…``:
    el tamaño sale de la imagen, no del formulario.
    """
    op = opciones_permitidas(d, cfg.controlador_scsi)
    if import_from is None:
        partes = [f"{d.storage}:{d.tamano_gib}"]
    else:
        partes = [f"{d.storage}:0", f"import-from={import_from}"]
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


def _volid_seguro(volid: str | None, contenido: Contenido) -> str:
    """Defensa en profundidad (INV-O7): el volid vuelve a pasar la lista blanca al construir."""
    if not volid or validar_volid(volid, contenido) is not None:
        raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "origen"})
    return volid


def _claves_discos(cfg: ConfiguracionVM, discos: list[Disco]) -> list[str]:
    """Clave de cada disco (``scsi0``…). Con ISO los IDE usan ``ide1`` e ``ide3`` (DT-O2)."""
    claves: list[str] = []
    contadores: dict[Bus, int] = {}
    for d in discos:
        indice = contadores.get(d.bus, 0)
        contadores[d.bus] = indice + 1
        if cfg.origen == OrigenSO.ISO and d.bus == Bus.IDE:
            if indice >= len(RANURAS_IDE_CON_ISO):  # V-O06 lo habría bloqueado
                raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "discos"})
            claves.append(RANURAS_IDE_CON_ISO[indice])
        else:
            claves.append(f"{d.bus.value}{indice}")
    return claves


def _orden_arranque(primer_disco: str | None, hay_red: bool) -> str:
    """``order=<primer disco>;ide2[;net0]`` según ``ORDEN_ARRANQUE`` (DT-O1)."""
    elementos = {"disco": primer_disco, "cd": RANURA_ISO, "red": "net0" if hay_red else None}
    return "order=" + ";".join(e for k in ORDEN_ARRANQUE if (e := elementos.get(k)))


def construir_parametros(
    cfg: ConfiguracionVM, inv: Inventario, version: tuple[int, int] | None = None
) -> dict[str, str]:
    """Convierte la configuración en los parámetros de ``POST /nodes/{nodo}/qemu``.

    ``version`` (opcional) es la versión contra la que se construye; sin ella se asume que
    admite etiquetas. Con origen ``disco_vacio`` y sin datos de SO la petición es idéntica a
    la del MVP 1–3 (CA-O03.1). Con ``iso`` e ``importar_disco`` (MVP 4) añade ``ostype``,
    ``ide2``/``ide0``, ``boot``, ``import-from``, ``tpmstate0`` y ``agent``. El clon tiene su
    propio constructor (``origen.clon.construir_peticion_clon``).
    """
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "origen"})
    con_origen = cfg.origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO)
    detalle = cfg.detalle_origen
    if con_origen and not isinstance(detalle, DetalleIso | DetalleImportacion):
        raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "origen"})
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
    if con_origen and cfg.tipo_so is not None:
        params["ostype"] = TABLA_SO[cfg.tipo_so].ostype

    claves = _claves_discos(cfg, discos)
    volid_imagen: str | None = None
    if isinstance(detalle, DetalleImportacion) and cfg.origen == OrigenSO.IMPORTAR_DISCO:
        if not discos:
            raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "discos"})
        volid_imagen = _volid_seguro(detalle.imagen.volid, Contenido.IMPORT)
    for i, (d, clave) in enumerate(zip(discos, claves, strict=True)):
        params[clave] = _valor_disco(cfg, inv, d, volid_imagen if i == 0 else None)

    if cfg.origen == OrigenSO.ISO and isinstance(detalle, DetalleIso):
        if cfg.tpm:
            params["tpmstate0"] = _valor_tpm(cfg, inv, discos)
        params[RANURA_ISO] = f"{_volid_seguro(detalle.iso.volid, Contenido.ISO)},media=cdrom"
        if (
            cfg.tipo_so is not None
            and TABLA_SO[cfg.tipo_so].drivers
            and not detalle.sin_drivers
            and detalle.drivers is not None
        ):
            volid = _volid_seguro(detalle.drivers.volid, Contenido.ISO)
            params[RANURA_DRIVERS] = f"{volid},media=cdrom"
        permisos = None if inv.catalogo is None else inv.catalogo.permisos
        # INV-O10: sin la certeza de VM.Config.Disk el POST entero podría fallar por un 403.
        if estado_privilegio(permisos, "VM.Config.Disk", f"/vms/{cfg.vmid}") is True:
            primer = claves[0] if claves else None
            params["boot"] = _orden_arranque(primer, bool(cfg.redes))
    elif cfg.origen == OrigenSO.IMPORTAR_DISCO and cfg.tpm:
        params["tpmstate0"] = _valor_tpm(cfg, inv, discos)

    for i, r in enumerate(cfg.redes):
        valor = f"{r.modelo.value},bridge={r.bridge}"
        if r.vlan is not None:
            valor += f",tag={r.vlan}"
        params[f"net{i}"] = valor
    if con_origen and cfg.agente_qemu and cfg.tipo_so != TipoSO.OTRO:
        params["agent"] = "1"
    if cfg.etiquetas and (version is None or admite_etiquetas(version)):
        params["tags"] = ";".join(cfg.etiquetas)
    return params


def _valor_tpm(cfg: ConfiguracionVM, inv: Inventario, discos: list[Disco]) -> str:
    """``tpmstate0=<storage del efidisk0>:1,version=v2.0`` (sin ``format``, DT-O6, DT-O8)."""
    id_tpm = storage_efi_efectivo(cfg, inv, discos)
    if id_tpm is None:
        raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "storage_efi"})
    return f"{id_tpm}:{EFIDISK_TAMANO},version={VERSION_TPM}"
