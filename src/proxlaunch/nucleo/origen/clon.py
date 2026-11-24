"""Clonado de plantillas: modo, petición, ajustes posteriores y lectura de la config (RF-O20..O22).

Todo es puro. ``detalle_de_config`` interpreta el texto de ``GET …/qemu/{vmid}/config`` como
**no confiable**: valores raros dan ``None`` y nunca una excepción.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from proxlaunch.nucleo.cloudinit.deteccion import es_windows, info_cloudinit
from proxlaunch.nucleo.cloudinit.modelos import INFO_DESCONOCIDA
from proxlaunch.nucleo.cloudinit.peticion import construir_put_cloudinit
from proxlaunch.nucleo.constructor_peticion import valor_startup
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import MAX_INDICE_USB, MAX_PCI, RE_ID_MAPEO
from proxlaunch.nucleo.hardware_cluster.peticion import parametros_hardware
from proxlaunch.nucleo.modelos.catalogo import DetallePlantilla, DiscoPlantilla
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage
from proxlaunch.nucleo.modelos.origen import DetalleClon, ModoClon
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, pool_valido
from proxlaunch.nucleo.red.tarjetas import tarjetas_de_config
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.validacion import (
    DISCO_MAX_GIB,
    DISCO_MIN_GIB,
    TIPOS_STORAGE_QCOW2,
    Problema,
    Severidad,
    etiqueta_valida,
    nombre_dns_valido,
    tipo_cpu_valido,
)

# Tipos con clonado enlazado sobre una base (I4-§D). dir/nfs/cifs exigen además qcow2.
TIPOS_CLON_ENLAZADO: frozenset[str] = frozenset(
    {"dir", "nfs", "cifs", "btrfs", "lvmthin", "zfspool", "rbd"}
)

_GIB = 1024**3
_RE_CLAVE_DISCO = re.compile(r"(?:scsi|virtio|sata|ide)\d+")
_RE_CLAVE_DISCO_PLANTILLA = re.compile(r"(?:(?:scsi|virtio|sata|ide)\d+|efidisk0|tpmstate0)")
_RE_NET = re.compile(r"net\d+")
_RE_HOSTPCI = re.compile(r"hostpci(\d{1,2})")
_RE_USB = re.compile(r"usb(\d{1,2})")
_RE_VIRTIOFS = re.compile(r"virtiofs\d+")
_RE_ARQUITECTURA = re.compile(r"[A-Za-z0-9_]{1,16}")
_RE_MAQUINA = re.compile(r"[A-Za-z0-9_.+=,-]{1,64}")
_RE_ID = re.compile(r"[A-Za-z0-9._-]+")
_RE_TAMANO = re.compile(r"(\d+)([KMGT]?)")
_FACTOR = {"": 1, "K": 1024, "M": 1024**2, "G": _GIB, "T": 1024**4}
_PRIORIDAD_PRINCIPAL = ("scsi0", "virtio0", "sata0", "ide0")


def admite_enlazado(tipo_storage: str, formatos: frozenset[str] | None) -> bool:
    """¿Un storage de ese tipo permite clonar enlazado? (``formatos`` de la API si se conocen).

    En dir/nfs/cifs el clon enlazado es un qcow2: el storage debe admitir ese formato
    (sin ``formatos`` se asume la tabla fija de V-09).
    """
    if tipo_storage not in TIPOS_CLON_ENLAZADO:
        return False
    if tipo_storage in TIPOS_STORAGE_QCOW2:
        return formatos is None or "qcow2" in formatos
    return True


# --- Lectura defensiva de la configuración de una plantilla -------------------------------


def _entero(valor: object) -> int | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def _tamano_bytes(texto: str) -> int | None:
    m = _RE_TAMANO.fullmatch(texto.strip())
    return None if m is None else int(m.group(1)) * _FACTOR[m.group(2)]


def _opciones(valor: str) -> tuple[str, dict[str, str]]:
    """(primer elemento, {opción: valor}) de ``<volumen>,k=v,k=v``."""
    partes = valor.split(",")
    opciones: dict[str, str] = {}
    for p in partes[1:]:
        clave, igual, resto = p.partition("=")
        if igual:
            opciones[clave.strip()] = resto.strip()
    return partes[0].strip(), opciones


def _formato_de_volumen(nombre: str, opciones: Mapping[str, str]) -> str | None:
    if opciones.get("format") in ("raw", "qcow2", "vmdk"):
        return opciones["format"]
    extension = nombre.rpartition(".")[2].lower() if "." in nombre else ""
    return extension if extension in ("raw", "qcow2", "vmdk") else None


def _clave_orden(clave: str) -> tuple[int, str, int]:
    base = clave.rstrip("0123456789")
    sufijo = clave[len(base) :]
    return (0 if clave not in ("efidisk0", "tpmstate0") else 1, base, int(sufijo or 0))


def _disco_de(clave: str, valor: object) -> DiscoPlantilla | None:
    if not isinstance(valor, str):
        return None
    volumen, opciones = _opciones(valor)
    if opciones.get("media") == "cdrom" or volumen in ("", "none", "cdrom"):
        return None
    storage, dos_puntos, nombre = volumen.partition(":")
    if not dos_puntos or _RE_ID.fullmatch(storage) is None:
        return None
    tamano = _tamano_bytes(opciones["size"]) if "size" in opciones else None
    return DiscoPlantilla(clave, storage, tamano, _formato_de_volumen(nombre, opciones))


def _etiquetas(valor: object) -> frozenset[str]:
    if not isinstance(valor, str):
        return frozenset()
    return frozenset(t.strip() for t in re.split(r"[;,]", valor) if t.strip())


def _hardware_de_config(
    config: Mapping[str, object],
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[str, ...], bool]:
    """``(hostpci, usb, mapeos, pasarela_directa)`` de la config de una plantilla (D3, RF-D3.5).

    Índices ocupados de ``hostpciN``/``usbN``; ids de ``mapping=<id>`` (solo los que cumplen
    ``RE_ID_MAPEO``); y si hay dispositivos sin mapeo (``hostpciN=<bdf>``, ``usbN=host=…``),
    ``virtiofsN`` o ``rng0`` físico: solo root puede clonar eso (V-D58).
    """
    hostpci: set[int] = set()
    usb: set[int] = set()
    mapeos: list[str] = []
    directa = False
    for clave, valor in config.items():
        if not isinstance(clave, str):
            continue
        m_pci = _RE_HOSTPCI.fullmatch(clave)
        m_usb = _RE_USB.fullmatch(clave)
        if m_pci is None and m_usb is None:
            if _RE_VIRTIOFS.fullmatch(clave) or (
                clave == "rng0" and isinstance(valor, str) and "/dev/hwrng" in valor
            ):
                directa = True
            continue
        if m_pci is not None and int(m_pci.group(1)) < MAX_PCI:
            hostpci.add(int(m_pci.group(1)))
        elif m_usb is not None and int(m_usb.group(1)) < MAX_INDICE_USB:
            usb.add(int(m_usb.group(1)))
        if not isinstance(valor, str):
            directa = True  # un valor ilegible no se afirma mapeado
            continue
        partes = [p.strip() for p in valor.split(",")]
        id_mapeo = next((p[len("mapping=") :] for p in partes if p.startswith("mapping=")), None)
        if id_mapeo is not None:
            if RE_ID_MAPEO.fullmatch(id_mapeo):
                if id_mapeo not in mapeos:
                    mapeos.append(id_mapeo)
            else:
                directa = True
        elif m_usb is not None and partes[0] == "host=spice":
            continue  # redirección SPICE: no es un dispositivo físico
        else:
            directa = True
    return tuple(sorted(hostpci)), tuple(sorted(usb)), tuple(mapeos), directa


def detalle_de_config(config: Mapping[str, object]) -> DetallePlantilla:
    """Interpreta la config de una plantilla (texto no confiable; nunca lanza).

    Discos: ``scsiN``, ``virtioN``, ``sataN``, ``ideN``, ``efidisk0`` y ``tpmstate0`` (sin CD-ROM);
    el storage es lo anterior a ``:``; ``size=`` admite los sufijos ``K/M/G/T``.
    """
    discos: list[DiscoPlantilla] = []
    for clave in sorted(
        (k for k in config if isinstance(k, str) and _RE_CLAVE_DISCO_PLANTILLA.fullmatch(k)),
        key=_clave_orden,
    ):
        disco = _disco_de(clave, config[clave])
        if disco is not None:
            discos.append(disco)
    bridges: list[str] = []
    for clave in sorted(k for k in config if isinstance(k, str) and _RE_NET.fullmatch(k)):
        valor = config[clave]
        if not isinstance(valor, str):
            continue
        # Formato ``modelo=MAC,bridge=…``: el bridge es una opción; las demás se descartan.
        puente = _opciones("," + valor)[1].get("bridge")
        if puente and _RE_ID.fullmatch(puente) and puente not in bridges:
            bridges.append(puente)
    cpu = config.get("cpu")
    tipo_cpu: str | None = None
    if isinstance(cpu, str):
        primero = cpu.split(",")[0].strip().removeprefix("cputype=")
        tipo_cpu = primero if tipo_cpu_valido(primero) else None
    bloqueo = config.get("lock")
    plantilla = config.get("template")
    descripcion = config.get("description")
    arquitectura = config.get("arch")
    maquina = config.get("machine")
    hostpci, usb, mapeos, directa = _hardware_de_config(config)
    return DetallePlantilla(
        es_plantilla=plantilla in (1, "1", True),
        bloqueo=bloqueo if isinstance(bloqueo, str) and bloqueo else None,
        discos=tuple(discos),
        bridges=tuple(bridges),
        sockets=_entero(config.get("sockets")),
        cores=_entero(config.get("cores")),
        tipo_cpu=tipo_cpu,
        memoria_mib=_entero(config.get("memory")),
        etiquetas=_etiquetas(config.get("tags")),
        balloon=_entero(config.get("balloon")),
        vcpus=_entero(config.get("vcpus")),
        # Fase A: sin clave ``description`` la plantilla no tiene notas (None); un valor que
        # no sea texto se ignora.
        descripcion=descripcion if isinstance(descripcion, str) else None,
        # Fase B: lo que la config dice de cloud-init, sin ninguna lectura nueva (DT-B2).
        cloudinit=info_cloudinit(config),
        # Fase C: ``net0..net31`` de la misma config, interpretadas (DT-C5; cero GET nuevos).
        tarjetas=tarjetas_de_config(config),
        # Fase D: arquitectura, máquina y hardware asignado de la misma config (cero GET nuevos).
        arquitectura=(
            arquitectura
            if isinstance(arquitectura, str) and _RE_ARQUITECTURA.fullmatch(arquitectura)
            else None
        ),
        maquina=maquina if isinstance(maquina, str) and _RE_MAQUINA.fullmatch(maquina) else None,
        hostpci=hostpci,
        usb=usb,
        mapeos=mapeos,
        pasarela_directa=directa,
    )


def disco_principal(detalle: DetallePlantilla) -> DiscoPlantilla | None:
    """Disco principal: ``scsi0``, si no ``virtio0``, ``sata0``, ``ide0`` (CA-O22.3).

    Sin ninguno de ellos, el primer disco de datos (no ``efidisk0`` ni ``tpmstate0``).
    """
    por_clave = {d.clave: d for d in detalle.discos}
    for clave in _PRIORIDAD_PRINCIPAL:
        if clave in por_clave:
            return por_clave[clave]
    return next((d for d in detalle.discos if _RE_CLAVE_DISCO.fullmatch(d.clave)), None)


# --- Modo efectivo -------------------------------------------------------------------------


def _storage_del_nodo(inv: Inventario, nodo: str, id_storage: str) -> Storage | None:
    for s in inv.storages_todos.get(nodo) or inv.storages.get(nodo, ()):
        if s.id == id_storage:
            return s
    return None


def _formatos_de(inv: Inventario, storage: Storage) -> frozenset[str] | None:
    if storage.formatos is not None:
        return storage.formatos
    if inv.catalogo is not None:
        return inv.catalogo.formatos.get(storage.id)
    return None


def _enlazable(plantilla: DetallePlantilla, inv: Inventario, nodo_plantilla: str) -> bool:
    """Todos los discos de la plantilla están en storages con clon enlazado."""
    # El estado TPM siempre se clona completo (CA-O20.7): no condiciona el modo.
    discos = [d for d in plantilla.discos if d.clave != "tpmstate0"]
    if not discos:
        return False
    for disco in discos:
        st = _storage_del_nodo(inv, nodo_plantilla, disco.storage)
        if st is None or not admite_enlazado(st.tipo, _formatos_de(inv, st)):
            return False
    return True


def modo_efectivo(
    detalle_clon: DetalleClon,
    plantilla: DetallePlantilla,
    inv: Inventario,
    nodo_plantilla: str,
) -> tuple[ModoClon | None, Problema | None]:
    """Modo con el que se clonará (D-25.1, V-O21).

    ``automatico`` → ``enlazado`` si todos los discos lo admiten y no se pidió ``storage_destino``;
    si no, ``completo``. ``enlazado`` forzado sin soporte (o con storage destino) → error V-O21.
    """
    pedido = detalle_clon.modo
    enlazable = _enlazable(plantilla, inv, nodo_plantilla)
    if pedido == ModoClon.COMPLETO:
        return ModoClon.COMPLETO, None
    if pedido == ModoClon.AUTOMATICO:
        if enlazable and not detalle_clon.storage_destino:
            return ModoClon.ENLAZADO, None
        return ModoClon.COMPLETO, None
    campo = "detalle_origen.modo"
    if detalle_clon.storage_destino:
        return None, Problema(campo, "V-O21", Severidad.ERROR, {"motivo": "storage_destino"})
    if not enlazable:
        storages = ",".join(sorted({d.storage for d in plantilla.discos}))
        return None, Problema(
            campo, "V-O21", Severidad.ERROR, {"motivo": "sin_soporte", "storages": storages}
        )
    return ModoClon.ENLAZADO, None


# --- Petición de clon ----------------------------------------------------------------------


@dataclass(frozen=True)
class PeticionClon:
    """``POST /nodes/{nodo_plantilla}/qemu/{vmid_plantilla}/clone`` con ``parametros``."""

    nodo_plantilla: str
    vmid_plantilla: int
    parametros: dict[str, str]


def _invalido(campo: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": campo})


def _id_seguro(valor: object, *, anidado: bool = False) -> bool:
    """Identificador sin caracteres peligrosos. Con ``anidado`` admite «/» como separador de
    pools anidados (formato ``pve-poolid``, SEG-A-04); node y storage no lo admiten."""
    if anidado:
        return pool_valido(valor)
    return isinstance(valor, str) and _RE_ID.fullmatch(valor) is not None


def _formato_clon_completo(inv: Inventario, nodo: str, id_storage: str) -> str | None:
    """``qcow2`` en dir/nfs/cifs (V-09, como el disco nuevo de M1); nada en el resto."""
    st = _storage_del_nodo(inv, nodo, id_storage)
    if st is None or st.tipo not in TIPOS_STORAGE_QCOW2:
        return None
    formatos = _formatos_de(inv, st)
    return "qcow2" if formatos is None or "qcow2" in formatos else None


def construir_peticion_clon(cfg: ConfiguracionVM, inv: Inventario) -> PeticionClon:
    """Petición de clon de una MV del plan (INV-O3: es **el** envío de creación de esa MV).

    Siempre ``newid`` y ``name``. Completo añade ``full=1``, ``storage`` (si hay storage destino)
    y ``format`` solo donde V-09 lo permite; enlazado nunca lleva ``full``, ``storage`` ni
    ``format``. ``target`` solo si el nodo destino no es el de la plantilla (CA-O21.7).
    Lanza ``PARAMETRO_INVALIDO`` si el detalle no está resuelto o un valor no es seguro.
    """
    detalle = cfg.detalle_origen
    if not isinstance(detalle, DetalleClon):
        raise _invalido("detalle_origen")
    plantilla = detalle.plantilla
    efectivo = detalle.modo_efectivo
    if plantilla.vmid is None or not plantilla.nodo or efectivo is None:
        raise _invalido("detalle_origen")
    if isinstance(cfg.vmid, bool) or not isinstance(cfg.vmid, int):
        raise _invalido("vmid")
    if not nombre_dns_valido(cfg.nombre):
        raise _invalido("nombre")
    if not _id_seguro(plantilla.nodo):
        raise _invalido("detalle_origen")
    parametros: dict[str, str] = {"newid": str(cfg.vmid), "name": cfg.nombre}
    if efectivo == ModoClon.COMPLETO:
        parametros["full"] = "1"
        destino = detalle.storage_destino
        if destino:
            if not _id_seguro(destino):
                raise _invalido("detalle_origen.storage_destino")
            parametros["storage"] = destino
            formato = _formato_clon_completo(inv, cfg.nodo, destino)
            if formato is not None:
                parametros["format"] = formato
    elif efectivo != ModoClon.ENLAZADO:
        raise _invalido("detalle_origen")
    if cfg.nodo and cfg.nodo != plantilla.nodo:
        if not _id_seguro(cfg.nodo):
            raise _invalido("nodo")
        parametros["target"] = cfg.nodo
    # Fase A (0.6): descripción ya calculada por el plan (plantilla + bloque + notas) y pool.
    if cfg.descripcion is not None:
        parametros["description"] = cfg.descripcion
    if cfg.pool:
        if not _id_seguro(cfg.pool, anidado=True):
            raise _invalido("pool")
        parametros["pool"] = cfg.pool
    return PeticionClon(plantilla.nodo, plantilla.vmid, parametros)


# --- Ajustes tras clonar -------------------------------------------------------------------


@dataclass(frozen=True)
class AjustesTrasClon:
    """``config``: cuerpo del ``PUT …/config`` (vacío = no hay PUT). ``disco``: ``(clave, GiB)``.

    Fase B: ``cloudinit`` es el cuerpo del ``PUT`` de cloud-init (sin contraseña; vacío = no hay
    PUT) y ``contrasena`` el ``Secreto`` que se envía en un ``PUT`` propio. Nunca entran en
    ``repr`` ni en la comparación.
    """

    config: dict[str, str]
    disco: tuple[str, int] | None
    cloudinit: dict[str, str] = field(default_factory=dict)
    contrasena: Secreto | None = field(default=None, repr=False, compare=False)


def union_etiquetas(*grupos: Iterable[str]) -> str:
    """Etiquetas de todos los grupos, sin repetir y ordenadas, separadas por ``;`` (DT-O14)."""
    return ";".join(sorted({e for g in grupos for e in g}))


def construir_ajustes_clon(
    cfg: ConfiguracionVM, plantilla: DetallePlantilla, etiquetas_lote: Sequence[str]
) -> AjustesTrasClon:
    """Lo que hay que escribir tras el clon, solo si difiere de la plantilla (CA-O22.1..O22.7).

    Valores **absolutos** (INV-O3). ``tags`` = unión de las de la plantilla y las del lote
    (``clone`` no admite ``tags``); sin etiquetas del lote ni cambios no hay ``PUT``.
    Fase A: ``onboot``, ``startup`` y ``protection`` (solo si difieren del defecto, pues el
    clon hereda lo de la plantilla); ``etiquetas_lote`` debe incluir las del usuario.
    El disco solo se amplía si el tamaño pedido supera el actual del disco principal.

    Fase B: con ``cfg.cloudinit`` no vacía y una plantilla que no se sabe sin unidad cloud-init,
    ``cloudinit`` lleva el cuerpo de su ``PUT`` (``construir_put_cloudinit`` sobre lo que la
    plantilla ya trae) y ``contrasena`` el secreto (nunca en una plantilla Windows). Sin
    cloud-init el resultado es el de 0.6.0.
    """
    detalle = cfg.detalle_origen
    if not isinstance(detalle, DetalleClon):
        raise _invalido("detalle_origen")
    a = detalle.ajustes
    config: dict[str, str] = {}
    if a.sockets is not None and a.sockets != plantilla.sockets:
        config["sockets"] = str(a.sockets)
    if a.cores is not None and a.cores != plantilla.cores:
        config["cores"] = str(a.cores)
    if a.tipo_cpu is not None and a.tipo_cpu != plantilla.tipo_cpu:
        if not tipo_cpu_valido(a.tipo_cpu):
            raise _invalido("detalle_origen.ajustes.tipo_cpu")
        config["cpu"] = a.tipo_cpu
    if a.memoria_mib is not None and a.memoria_mib != plantilla.memoria_mib:
        config["memory"] = str(a.memoria_mib)
        # QA-M4-07: Proxmox exige balloon <= memory. Si la memoria nueva queda por debajo del
        # balloon de la plantilla, se baja también (balloon = 0 es «desactivado»: no se toca).
        if plantilla.balloon is not None and plantilla.balloon > a.memoria_mib > 0:
            config["balloon"] = str(a.memoria_mib)
    if "sockets" in config or "cores" in config:
        # QA-M4-07: vcpus no puede superar sockets*cores; si los nuevos núcleos quedan por
        # debajo de los vcpus de la plantilla, vcpus = sockets*cores nuevos. DEFECTO-F7-01: PVE
        # omite los valores por defecto en la config, así que sockets o cores ausentes valen 1.
        sockets = a.sockets if a.sockets is not None else (plantilla.sockets or 1)
        cores = a.cores if a.cores is not None else (plantilla.cores or 1)
        if plantilla.vcpus is not None and sockets * cores < plantilla.vcpus:
            config["vcpus"] = str(sockets * cores)
    if etiquetas_lote:
        for etiqueta in etiquetas_lote:
            if not etiqueta_valida(etiqueta):
                raise _invalido("etiquetas")
        union = union_etiquetas(plantilla.etiquetas, etiquetas_lote)
        if union != union_etiquetas(plantilla.etiquetas):
            config["tags"] = union
    if cfg.arranque_auto:
        config["onboot"] = "1"
    inicio = valor_startup(cfg)
    if inicio is not None:
        config["startup"] = inicio
    if cfg.proteger:
        config["protection"] = "1"
    disco: tuple[str, int] | None = None
    if a.disco_gib is not None:
        principal = disco_principal(plantilla)
        if principal is not None and _RE_CLAVE_DISCO.fullmatch(principal.clave):
            if not DISCO_MIN_GIB <= a.disco_gib <= DISCO_MAX_GIB:
                raise _invalido("detalle_origen.ajustes.disco_gib")
            actual_gib = (
                None if principal.tamano_bytes is None else -(-principal.tamano_bytes // _GIB)
            )
            if actual_gib is None or a.disco_gib > actual_gib:
                disco = (principal.clave, a.disco_gib)
    cloudinit, contrasena = _ajustes_cloudinit(cfg, plantilla)
    return AjustesTrasClon(config, disco, cloudinit, contrasena)


def _ajustes_cloudinit(
    cfg: ConfiguracionVM, plantilla: DetallePlantilla
) -> tuple[dict[str, str], Secreto | None]:
    """``(cuerpo del PUT de cloud-init, contraseña)`` de una MV clonada (DT-B7).

    Sin unidad cloud-init en la plantilla (``unidad is False``) no se emite nada: quien envía
    lo detecta y marca ``CLOUDINIT_SIN_UNIDAD``. ``unidad is None`` (config ilegible) sí envía.
    """
    ci = cfg.cloudinit
    if ci is None or ci.sin_nada_que_aplicar:
        return {}, None
    info = plantilla.cloudinit if plantilla.cloudinit is not None else INFO_DESCONOCIDA
    if info.unidad is False:
        return {}, None
    contrasena = ci.contrasena
    # Un ``Secreto`` ya olvidado se conserva: quien envía lo marca pendiente (CONTRASENA_OLVIDADA).
    if contrasena is None or info.es_windows or es_windows(info.ostype):
        contrasena = None
    return construir_put_cloudinit(ci, info), contrasena


def parametros_hardware_clon(cfg: ConfiguracionVM, plantilla: DetallePlantilla) -> dict[str, str]:
    """Cuerpo del ``PUT …/config`` de hardware de un clon (DT-D11, RF-D3.2); ``{}`` sin D3.

    Las claves ``hostpciN``/``usbN`` usan los primeros índices libres de la plantilla (CA-D3.2.4);
    ``machine=q35`` solo con ``pcie`` y si la máquina de la plantilla aún no es q35; ``vga=none``
    con ``x_vga``. ``ValueError`` si un id no es válido o no quedan índices libres.
    """
    libres_pci = [i for i in range(MAX_PCI) if i not in plantilla.hostpci]
    libres_usb = [i for i in range(MAX_INDICE_USB) if i not in plantilla.usb]
    return parametros_hardware(
        cfg.hardware_cluster,
        (),
        libres_pci=libres_pci,
        libres_usb=libres_usb,
        maquina_actual=plantilla.maquina,
    )


def parametros_ampliacion(clave_disco: str, tamano_gib: int) -> dict[str, str]:
    """Cuerpo del ``PUT …/resize``: tamaño **absoluto**, nunca ``+N`` (INV-O3)."""
    if _RE_CLAVE_DISCO.fullmatch(clave_disco) is None:
        raise _invalido("disco")
    if isinstance(tamano_gib, bool) or not isinstance(tamano_gib, int) or tamano_gib < 1:
        raise _invalido("tamano_gib")
    return {"disk": clave_disco, "size": f"{tamano_gib}G"}
