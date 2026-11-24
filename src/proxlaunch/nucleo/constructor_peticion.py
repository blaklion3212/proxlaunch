"""Construcción de los parámetros de la API para crear una MV (RF-19, CA-19.3).

Función pura: devuelve valores SIN codificar; la codificación del formulario la hace
el transporte (CT-9).
"""

from collections.abc import Collection
from decimal import Decimal

from proxlaunch.nucleo.arquitectura.modelos import Arquitectura, arquitectura_efectiva
from proxlaunch.nucleo.arquitectura.perfil import BUSES_SOLO_X86, ranura_cdrom_aarch64
from proxlaunch.nucleo.capacidades import admite_etiquetas
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import usa_firewall
from proxlaunch.nucleo.libvirt.validacion import mac_valida, normalizar_mac
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, DetalleIso, TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.opciones.etiquetas import etiquetas_finales
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
    tipo_cpu_valido,
)

# Forma del efidisk0 (P-10, CT-7). Valores por verificar en laboratorio.
EFIDISK_TAMANO = "1"  # por verificar en laboratorio
EFIDISK_TIPO = "4m"  # por verificar en laboratorio
# Claves de Secure Boot precargadas (LAB-M4-04): un ISO Linux sin firmar (p. ej. Alpine) no
# arranca con ``pre-enrolled-keys=1``, así que Linux y «Otro» usan ``0``. Windows y la
# configuración sin datos de SO (disco vacío, comportamiento del MVP 3) conservan ``1``.
EFIDISK_CLAVES_PRECARGADAS = "1"
EFIDISK_SIN_CLAVES = "0"
# Si el efidisk también lleva ``format=`` en dir/nfs/cifs (CA-14.3).
EFIDISK_CON_FORMATO = True  # por verificar en laboratorio
MAQUINA_OVMF = "q35"
VGA_ARM = "virtio"  # ARM64 no tiene VGA estándar (DT-D7)


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


def _orden_arranque(primer_disco: str | None, hay_red: bool, *, ranura_cd: str = RANURA_ISO) -> str:
    """``order=<primer disco>;ide2[;net0]`` según ``ORDEN_ARRANQUE`` (DT-O1).

    ``ranura_cd`` es la unidad del ISO: ``ide2`` en x86 y la ``scsiN`` elegida en aarch64.
    """
    elementos = {"disco": primer_disco, "cd": ranura_cd, "red": "net0" if hay_red else None}
    return "order=" + ";".join(e for k in ORDEN_ARRANQUE if (e := elementos.get(k)))


def _volids_importados(
    cfg: ConfiguracionVM, detalle: DetalleImportacion, n_discos: int
) -> dict[int, str]:
    """Volid de la imagen de cada disco del origen «importar disco» (DT-D14).

    El disco 0 usa ``detalle.imagen``; los demás, ``detalle.otras``. Un disco sin entrada o
    con ``crear_vacio`` se crea vacío (como en 0.8.0); una entrada sin imagen ni
    ``crear_vacio`` está pendiente (V-D27) y no debería llegar aquí.
    """
    volids = {0: _volid_seguro(detalle.imagen.volid, Contenido.IMPORT)}
    for otra in detalle.otras:
        if not 1 <= otra.indice < n_discos:
            continue
        volid = None if otra.imagen is None else otra.imagen.volid
        if volid:
            volids[otra.indice] = _volid_seguro(volid, Contenido.IMPORT)
        elif not otra.crear_vacio:
            raise ErrorProxLaunch(
                CodigoError.PARAMETRO_INVALIDO, {"campo": f"discos[{otra.indice}]"}
            )
    return volids


def _cpu_valida(tipo_cpu: str) -> str:
    """Tipo de CPU que va a la API; se vuelve a comprobar con la regla de V-22 (como hostpci)."""
    if not tipo_cpu_valido(tipo_cpu):
        raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "tipo_cpu"})
    return tipo_cpu


def _hardware_cluster(cfg: ConfiguracionVM, claves_presentes: Collection[str]) -> dict[str, str]:
    """Claves ``machine``/``vga``/``hostpciN``/``usbN`` de D3 (vacío sin hardware; golden)."""
    hw = cfg.hardware_cluster
    if hw is None or hw.vacio:
        return {}
    from proxlaunch.nucleo.hardware_cluster.peticion import parametros_hardware

    return parametros_hardware(hw, claves_presentes)


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
    if arquitectura_efectiva(inv, cfg.nodo) == Arquitectura.AARCH64:
        return _parametros_aarch64(cfg, inv, version)  # D2: perfil ARM, aparte del camino x86
    params: dict[str, str] = {"vmid": str(cfg.vmid), "name": cfg.nombre}

    if cfg.firmware == Firmware.OVMF:
        params["bios"] = "ovmf"
        params["machine"] = MAQUINA_OVMF
        id_efi = storage_efi_efectivo(cfg, inv, discos)
        if id_efi is None:
            raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "storage_efi"})
        pre_claves = (
            EFIDISK_SIN_CLAVES
            if cfg.tipo_so in (TipoSO.LINUX, TipoSO.OTRO)
            else EFIDISK_CLAVES_PRECARGADAS
        )
        efi = f"{id_efi}:{EFIDISK_TAMANO},efitype={EFIDISK_TIPO},pre-enrolled-keys={pre_claves}"
        if EFIDISK_CON_FORMATO:
            formato = _formato_a_enviar(inv, cfg.nodo, id_efi, FormatoDisco.AUTO)
            if formato is not None:
                efi += f",format={formato}"
        params["efidisk0"] = efi

    params["sockets"] = str(cfg.sockets)
    params["cores"] = str(cfg.cores)
    params["cpu"] = _cpu_valida(cfg.tipo_cpu)
    params["memory"] = str(cfg.memoria_mib)
    if cfg.ballooning is not None:
        params["balloon"] = str(cfg.ballooning.minimo_mib) if cfg.ballooning.activo else "0"

    if any(d.bus == Bus.SCSI for d in discos):
        params["scsihw"] = cfg.controlador_scsi.value
    if con_origen and cfg.tipo_so is not None:
        params["ostype"] = TABLA_SO[cfg.tipo_so].ostype

    claves = _claves_discos(cfg, discos)
    volids: dict[int, str] = {}
    if isinstance(detalle, DetalleImportacion) and cfg.origen == OrigenSO.IMPORTAR_DISCO:
        if not discos:
            raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "discos"})
        volids = _volids_importados(cfg, detalle, len(discos))
    for i, (d, clave) in enumerate(zip(discos, claves, strict=True)):
        params[clave] = _valor_disco(cfg, inv, d, volids.get(i))

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

    con_firewall = usa_firewall(cfg.firewall)
    for i, r in enumerate(cfg.redes):
        params[f"net{i}"] = valor_red(
            r, firewall=con_firewall, con_mac=cfg.origen == OrigenSO.IMPORTAR_DISCO
        )
    if con_origen and cfg.agente_qemu and cfg.tipo_so != TipoSO.OTRO:
        params["agent"] = "1"
    etiquetas = etiquetas_finales(cfg)
    if etiquetas and (version is None or admite_etiquetas(version)):
        params["tags"] = ";".join(etiquetas)
    # Fase A (0.6): solo si difieren del valor por defecto y en este orden (arq. §3.1), de modo
    # que con las opciones por defecto la petición es idéntica a la de 0.5.1.
    if cfg.arranque_auto:
        params["onboot"] = "1"
    valor_inicio = valor_startup(cfg)
    if valor_inicio is not None:
        params["startup"] = valor_inicio
    if cfg.descripcion is not None:
        params["description"] = cfg.descripcion
    if cfg.pool:
        params["pool"] = cfg.pool
    if cfg.proteger:
        params["protection"] = "1"
    params.update(_hardware_cluster(cfg, params.keys()))
    return params


def _parametros_aarch64(
    cfg: ConfiguracionVM, inv: Inventario, version: tuple[int, int] | None
) -> dict[str, str]:
    """Parámetros de ``POST qemu`` para un nodo aarch64 (RF-D2.6, DT-D7). Experimental.

    Función hermana de ``construir_parametros``: el camino x86 no pasa por aquí. UEFI siempre,
    ``efidisk0`` sin ``efitype``, sin ``machine`` (Proxmox usa ``virt``), discos solo
    ``scsiN``/``virtioN``, CD-ROM como ``scsiN,media=cdrom`` en la primera ranura libre,
    ``vga=virtio`` y tarjetas ``virtio``. La configuración llega ya adaptada por
    ``adaptar_a_arquitectura``: lo que no cabe se rechaza con ``ValueError``.

    Raises:
        ValueError: bus IDE/SATA o modelo de red distinto de ``virtio`` (defensa).
    """
    con_origen = cfg.origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO)
    detalle = cfg.detalle_origen
    discos = cfg.discos if cfg.con_disco else []
    for d in discos:
        if d.bus in BUSES_SOLO_X86:
            raise ValueError("aarch64 no admite discos IDE ni SATA")
    for r in cfg.redes:
        if r.modelo != ModeloRed.VIRTIO:
            raise ValueError("aarch64 solo admite tarjetas de red virtio")
    params: dict[str, str] = {"vmid": str(cfg.vmid), "name": cfg.nombre, "bios": "ovmf"}

    id_efi = storage_efi_efectivo(cfg, inv, discos)
    if id_efi is None:
        raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "storage_efi"})
    pre_claves = (
        EFIDISK_SIN_CLAVES
        if cfg.tipo_so in (TipoSO.LINUX, TipoSO.OTRO)
        else EFIDISK_CLAVES_PRECARGADAS
    )
    efi = f"{id_efi}:{EFIDISK_TAMANO}"
    if EFIDISK_CON_FORMATO:
        formato = _formato_a_enviar(inv, cfg.nodo, id_efi, FormatoDisco.AUTO)
        if formato is not None:
            efi += f",format={formato}"
    params["efidisk0"] = f"{efi},pre-enrolled-keys={pre_claves}"

    params["sockets"] = str(cfg.sockets)
    params["cores"] = str(cfg.cores)
    params["cpu"] = _cpu_valida(cfg.tipo_cpu)
    params["memory"] = str(cfg.memoria_mib)
    if cfg.ballooning is not None:
        params["balloon"] = str(cfg.ballooning.minimo_mib) if cfg.ballooning.activo else "0"

    claves = _claves_discos(cfg, discos)
    con_iso = cfg.origen == OrigenSO.ISO and isinstance(detalle, DetalleIso)
    # El CD-ROM va por SCSI: sin ``scsihw`` Proxmox usaría ``lsi``, que no es de ARM.
    if con_iso or any(d.bus == Bus.SCSI for d in discos):
        params["scsihw"] = cfg.controlador_scsi.value
    if con_origen and cfg.tipo_so is not None:
        params["ostype"] = TABLA_SO[cfg.tipo_so].ostype

    volids: dict[int, str] = {}
    if isinstance(detalle, DetalleImportacion) and cfg.origen == OrigenSO.IMPORTAR_DISCO:
        if not discos:
            raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "discos"})
        volids = _volids_importados(cfg, detalle, len(discos))
    for i, (d, clave) in enumerate(zip(discos, claves, strict=True)):
        params[clave] = _valor_disco(cfg, inv, d, volids.get(i))

    if isinstance(detalle, DetalleIso) and cfg.origen == OrigenSO.ISO:
        if cfg.tpm:
            params["tpmstate0"] = _valor_tpm(cfg, inv, discos)
        ocupadas = set(claves)
        ranura_iso = ranura_cdrom_aarch64(cfg, ocupadas)
        ocupadas.add(ranura_iso)
        params[ranura_iso] = f"{_volid_seguro(detalle.iso.volid, Contenido.ISO)},media=cdrom"
        if (
            cfg.tipo_so is not None
            and TABLA_SO[cfg.tipo_so].drivers
            and not detalle.sin_drivers
            and detalle.drivers is not None
        ):
            volid = _volid_seguro(detalle.drivers.volid, Contenido.ISO)
            params[ranura_cdrom_aarch64(cfg, ocupadas)] = f"{volid},media=cdrom"
        permisos = None if inv.catalogo is None else inv.catalogo.permisos
        if estado_privilegio(permisos, "VM.Config.Disk", f"/vms/{cfg.vmid}") is True:
            primer = claves[0] if claves else None
            params["boot"] = _orden_arranque(primer, bool(cfg.redes), ranura_cd=ranura_iso)
    elif cfg.origen == OrigenSO.IMPORTAR_DISCO and cfg.tpm:
        params["tpmstate0"] = _valor_tpm(cfg, inv, discos)

    params["vga"] = VGA_ARM
    con_firewall = usa_firewall(cfg.firewall)
    for i, r in enumerate(cfg.redes):
        params[f"net{i}"] = valor_red(
            r, firewall=con_firewall, con_mac=cfg.origen == OrigenSO.IMPORTAR_DISCO
        )
    if con_origen and cfg.agente_qemu and cfg.tipo_so != TipoSO.OTRO:
        params["agent"] = "1"
    etiquetas = etiquetas_finales(cfg)
    if etiquetas and (version is None or admite_etiquetas(version)):
        params["tags"] = ";".join(etiquetas)
    if cfg.arranque_auto:
        params["onboot"] = "1"
    valor_inicio = valor_startup(cfg)
    if valor_inicio is not None:
        params["startup"] = valor_inicio
    if cfg.descripcion is not None:
        params["description"] = cfg.descripcion
    if cfg.pool:
        params["pool"] = cfg.pool
    if cfg.proteger:
        params["protection"] = "1"
    # ``machine`` presente a propósito: en ``virt`` no hay q35 y ``pcie`` ya lo rechaza V-D09.
    params.update(_hardware_cluster(cfg, [*params, "machine"]))
    return params


def formato_limite(mb: float) -> str:
    """``rate=`` en notación decimal fija sin ceros sobrantes: ``100``, ``12.5``, ``0.00001``."""
    if mb == int(mb):
        return str(int(mb))
    return format(Decimal(repr(mb)), "f").rstrip("0").rstrip(".")


def valor_red(r: InterfazRed, *, firewall: bool = False, con_mac: bool = True) -> str:
    """Valor de ``netN``: ``<modelo>,bridge=…[,tag=…][,mtu=…][,rate=…][,firewall=1]``.

    ``mtu`` solo se envía con VirtIO (el resto de modelos no lo admite). ``firewall=1`` va al
    final y solo si ``firewall`` es ``True`` (C3); por defecto el texto es el de 0.7.0. Con
    ``mac_conservada`` (D1) y ``con_mac`` (origen «Importar disco») el modelo lleva la MAC en
    mayúsculas: ``virtio=52:54:00:AB:CD:EF``.
    """
    if r.mac_conservada is None or not con_mac:
        valor = f"{r.modelo.value},bridge={r.bridge}"
    else:
        # Defensa (DT-D15): V-D34 ya lo habría bloqueado; misma regla que la validación.
        mac = normalizar_mac(r.mac_conservada)
        if mac is None or len(r.mac_conservada) != 17 or not mac_valida(mac):
            raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "redes.mac_conservada"})
        valor = f"{r.modelo.value}={mac.upper()},bridge={r.bridge}"
    if r.vlan is not None:
        valor += f",tag={r.vlan}"
    if r.mtu is not None and r.modelo == ModeloRed.VIRTIO:
        valor += f",mtu={r.mtu}"
    if r.limite_mb is not None:
        valor += f",rate={formato_limite(r.limite_mb)}"
    if firewall:
        valor += ",firewall=1"
    return valor


def valor_startup(cfg: ConfiguracionVM) -> str | None:
    """``order=N,up=S`` con las partes fijadas, o ``None`` si no hay ninguna."""
    partes = []
    if cfg.arranque_orden is not None:
        partes.append(f"order={cfg.arranque_orden}")
    if cfg.arranque_espera is not None:
        partes.append(f"up={cfg.arranque_espera}")
    return ",".join(partes) or None


def _valor_tpm(cfg: ConfiguracionVM, inv: Inventario, discos: list[Disco]) -> str:
    """``tpmstate0=<storage del efidisk0>:1,version=v2.0`` (sin ``format``, DT-O6, DT-O8)."""
    id_tpm = storage_efi_efectivo(cfg, inv, discos)
    if id_tpm is None:
        raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "storage_efi"})
    return f"{id_tpm}:{EFIDISK_TAMANO},version={VERSION_TPM}"
