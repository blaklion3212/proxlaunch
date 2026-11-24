"""Lista blanca de la configuración de hardware en archivos (RF-X04, CA-X01.8).

Dos modos con las mismas claves de hardware (la fase B, ``cloudinit`` y ``esperar_ip``, solo
existe en el modo lote; un perfil no guarda nada de ella, RF-B6.2):

- **perfil**: sin storage/bridge reales; solo pistas opcionales (``storage_preferido`` por
  disco, ``storage_efi_preferido``, ``bridge_preferido`` por red). Los rangos de capa 1 de M1
  se comprueban en el esquema (importando las constantes de ``validacion.py``).
- **lote**: con ``storage``, ``storage_efi`` y ``bridge`` reales. Solo se exige el tipo
  correcto y un tope de cordura: las reglas de rango (V-05, V-08...) las muestra el formulario
  tras cargar (un lote guardado puede ser un borrador, CA-G02.1).

Los serializadores escriben campo a campo (sin volcado genérico) y nunca incluyen ``vmid``,
``nombre``, ``nodo`` ni ``etiquetas``.

MVP 4: ``tipo_so``, ``tpm``, ``agente_qemu`` y ``detalle_origen`` se escriben SOLO si no tienen su
valor por defecto (un archivo del MVP 3 queda idéntico). Los volids y nombres de fuentes se
leen y escriben con la lista blanca de ``origen.nombres`` (texto no válido → ``TEXTO_NO_VALIDO``;
nunca se interpreta como ruta). Nunca se guardan URL, rutas locales, checksums, tamaños virtuales
ni el modo efectivo del clon (INV-O6, INV-M5).
"""

from __future__ import annotations

from dataclasses import dataclass

from proxlaunch.nucleo.archivos.constantes import MAX_LONG_TEXTO
from proxlaunch.nucleo.archivos.esquema import LectorEsquema, MotivoCampo
from proxlaunch.nucleo.archivos.esquema_cloudinit import (
    cloudinit_requiere_v4,
    espera_ip_requiere_v4,
)
from proxlaunch.nucleo.archivos.esquema_fase_c import firewall_requiere_v5, red_clon_requiere_v5
from proxlaunch.nucleo.archivos.esquema_fase_d import (
    claves_red_fase_d,
    imagenes_a_lista,
    imagenes_requieren_v6,
    leer_imagenes,
    leer_mac_conservada,
)
from proxlaunch.nucleo.archivos.esquema_opciones import (
    CLAVES_OPCIONES_CFG,
    leer_limite,
    leer_mtu,
    leer_opciones_cfg,
    limite_para_escribir,
    mtu_para_escribir,
    opciones_cfg_a_dict,
)
from proxlaunch.nucleo.archivos.texto import exigir_sin_credencial
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.libvirt.validacion import conserva_mac
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.cpu import PREFIJO_CPU_PERSONALIZADA
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
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.origen.nombres import (
    MAX_LONG_STORAGE,
    partes_volid,
    validar_nombre_archivo,
    validar_volid,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    BallooningPerfil,
    ConfigPerfil,
    DiscoPerfil,
    PistaOrigen,
    RedPerfil,
)
from proxlaunch.nucleo.validacion import (
    CORES_MAX,
    CORES_MIN,
    DISCO_MAX_GIB,
    DISCO_MIN_GIB,
    MAX_DISPOSITIVOS,
    MAX_INTERFACES_RED,
    MEMORIA_MIN_MIB,
    SOCKETS_MAX,
    SOCKETS_MIN,
    VLAN_MAX,
    VLAN_MIN,
)

_TOPE_CORDURA = 10**9  # en modo lote: valores absurdos se rechazan por tipo/rango, no por regla
MAX_DISCOS = sum(MAX_DISPOSITIVOS.values())
# Un modelo personalizado (``custom-<nombre>``, nombre de hasta 64 caracteres) cabe en un perfil.
MAX_LONG_TIPO_CPU = len(PREFIJO_CPU_PERSONALIZADA) + 64
# Topes del lector de lotes guardados: un lote se lee como borrador (sin reglas de M1) y el
# lector debe aceptar todo lo que el escritor guarda; solo frenan abusos.
_MAX_LISTA_LOTE = 256
_MAX_TEXTO_LOTE = 1024

_CLAVES_BASE = frozenset(
    {
        "firmware",
        "sockets",
        "cores",
        "tipo_cpu",
        "memoria_mib",
        "ballooning",
        "con_disco",
        "discos",
        "controlador_scsi",
        "redes",
        "origen",
        "tipo_so",
        "tpm",
        "agente_qemu",
        "detalle_origen",
    }
)
# Fase A: un perfil solo guarda «Arrancar con el servidor» (RF-A1.4); el lote guarda todas.
CLAVES_CONFIG_PERFIL = _CLAVES_BASE | {"storage_efi_preferido", "arranque_auto"}
CLAVES_CONFIG_LOTE = _CLAVES_BASE | {"storage_efi"} | CLAVES_OPCIONES_CFG
_CLAVES_DISCO = frozenset({"tamano_gib", "bus", "formato", "discard", "ssd", "iothread"})
CLAVES_DISCO_PERFIL = _CLAVES_DISCO | {"storage_preferido"}
CLAVES_DISCO_LOTE = _CLAVES_DISCO | {"storage"}
_CLAVES_RED = frozenset({"modelo", "vlan", "mtu", "limite_mb"})
CLAVES_RED_PERFIL = _CLAVES_RED | {"bridge_preferido"}
CLAVES_RED_LOTE = _CLAVES_RED | {"bridge", "mac_conservada"}  # la MAC solo viaja en lotes (D)
_CLAVES_BALLOONING = frozenset({"activo", "minimo_mib"})
_CLAVES_AJUSTES = frozenset({"sockets", "cores", "tipo_cpu", "memoria_mib", "disco_gib"})
_CLAVES_REF_LOTE = frozenset({"nombre", "volid"})
_CLAVES_REF_PERFIL = frozenset({"nombre", "storage_preferido"})
_CLAVES_PLANTILLA_LOTE = frozenset({"nombre", "vmid"})
_CLAVES_PLANTILLA_PERFIL = frozenset({"nombre"})
_MAX_LONG_NOMBRE_PLANTILLA = 253


# --- Origen del SO (MVP 4) ------------------------------------------------------------------


def requiere_version_2(cfg: ConfiguracionVM | ConfigPerfil) -> bool:
    """¿La configuración usa algo del MVP 4? Entonces el archivo se escribe como v2 (DT-O15)."""
    if cfg.origen != OrigenSO.DISCO_VACIO or cfg.tipo_so is not None or cfg.tpm or cfg.agente_qemu:
        return True
    return isinstance(cfg, ConfigPerfil) and cfg.pista_origen is not None


def requiere_version_3(cfg: ConfiguracionVM | ConfigPerfil) -> bool:
    """¿La configuración usa algo de la fase A? Entonces el archivo se escribe como v3 (DT-A9).

    Cuenta cualquier campo nuevo distinto de su valor por defecto SALVO ``notas_origen``: esa
    casilla se escribe como clave aunque el archivo siga siendo v1/v2 (P-4; 0.5.1 la ignora con
    aviso).
    """
    if any(r.mtu is not None or r.limite_mb is not None for r in cfg.redes):
        return True
    if isinstance(cfg, ConfigPerfil):
        return cfg.arranque_auto
    return bool(
        cfg.encender
        or cfg.arranque_auto
        or cfg.arranque_orden is not None
        or cfg.arranque_espera is not None
        or cfg.notas_usuario
        or cfg.notas
        or cfg.etiquetas_usuario
        or cfg.pool is not None
        or cfg.proteger
    )


def requiere_version_4(cfg: ConfiguracionVM | ConfigPerfil) -> bool:
    """¿La configuración usa algo de la fase B? Entonces el lote se escribe como v4 (DT-B12).

    Cuenta cloud-init con algo que enviar y la espera de IP (activa o con plazo distinto del
    defecto). Un perfil nunca la usa: no guarda nada de la fase B (RF-B6.2).
    """
    if isinstance(cfg, ConfigPerfil):
        return False
    return cloudinit_requiere_v4(cfg.cloudinit) or espera_ip_requiere_v4(
        cfg.esperar_ip, cfg.plazo_ip_s
    )


def requiere_version_5(cfg: ConfiguracionVM | ConfigPerfil) -> bool:
    """¿La configuración usa algo de la fase C? Entonces el lote se escribe como v5 (RF-C6.1).

    Cuenta la red del clon personalizada y el firewall distinto del defecto. Un perfil nunca lo
    usa: no guarda nada de la fase C (RF-C6.2).
    """
    if isinstance(cfg, ConfigPerfil):
        return False
    return red_clon_requiere_v5(cfg.red_clon) or firewall_requiere_v5(cfg.firewall)


def _no_guardable(campo: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "caracteres", "campo": campo}
    )


def _nombre_para_escribir(nombre: str, contenido: Contenido, campo: str) -> str:
    """Nombre de archivo del servidor listo para escribir (lista blanca; vacío = sin elegir)."""
    exigir_sin_credencial(nombre, campo)
    if nombre and validar_nombre_archivo(nombre, contenido) is not None:
        raise _no_guardable(campo)
    return nombre


def _ref_a_dict(ref: RefVolumen, contenido: Contenido, campo: str) -> dict[str, object]:
    """Modo lote: ``{"nombre", "volid"}`` (el volid pasa la lista blanca o no se guarda)."""
    nombre = _nombre_para_escribir(ref.nombre, contenido, f"{campo}.nombre")
    if ref.volid is not None:
        exigir_sin_credencial(ref.volid, f"{campo}.volid")
        if validar_volid(ref.volid, contenido) is not None:
            raise _no_guardable(f"{campo}.volid")
    return {"nombre": nombre, "volid": ref.volid}


def _storage_para_escribir(storage: str | None, campo: str) -> str | None:
    if storage is None:
        return None
    exigir_sin_credencial(storage, campo)
    if not _storage_valido(storage):
        raise _no_guardable(campo)
    return storage


def _storage_valido(texto: str) -> bool:
    return 0 < len(texto) <= MAX_LONG_STORAGE and all(
        c.isascii() and (c.isalnum() or c in "._-") for c in texto
    )


def _ajustes_a_dict(a: AjustesClon) -> dict[str, object]:
    if a.tipo_cpu is not None:
        exigir_sin_credencial(a.tipo_cpu, "ajustes.tipo_cpu")
    return {
        "sockets": a.sockets,
        "cores": a.cores,
        "tipo_cpu": a.tipo_cpu,
        "memoria_mib": a.memoria_mib,
        "disco_gib": a.disco_gib,
    }


def detalle_origen_a_dict(cfg: ConfiguracionVM) -> dict[str, object] | None:
    """Detalle del origen de un lote (modo lote): con volids y VMID de pista, ``None`` si no hay.

    Nunca: URL, ruta, checksum, ``tamano_virtual_bytes``, ``modo_efectivo`` ni el nodo de la
    plantilla.
    """
    det = cfg.detalle_origen
    if isinstance(det, DetalleIso):
        return {
            "iso": _ref_a_dict(det.iso, Contenido.ISO, "iso"),
            "drivers": None
            if det.drivers is None
            else _ref_a_dict(det.drivers, Contenido.ISO, "drivers"),
            "sin_drivers": det.sin_drivers,
        }
    if isinstance(det, DetalleImportacion):
        importar: dict[str, object] = {
            "imagen": _ref_a_dict(det.imagen, Contenido.IMPORT, "imagen"),
            "ampliar_a_gib": det.ampliar_a_gib,
        }
        # Fase D: las imágenes de los discos 1.. se escriben (también las pendientes; v6, P-D9).
        if imagenes_requieren_v6(det.otras):
            importar["imagenes"] = imagenes_a_lista(det.otras, "imagenes")
        return importar
    if isinstance(det, DetalleClon):
        exigir_sin_credencial(det.plantilla.nombre, "plantilla")
        return {
            "plantilla": {"nombre": det.plantilla.nombre, "vmid": det.plantilla.vmid},
            "modo": str(det.modo),
            "ajustes": _ajustes_a_dict(det.ajustes),
            "storage_destino": _storage_para_escribir(det.storage_destino, "storage_destino"),
        }
    return None


def _pista_ref_a_dict(
    nombre: str, storage: str | None, contenido: Contenido, campo: str
) -> dict[str, object]:
    return {
        "nombre": _nombre_para_escribir(nombre, contenido, f"{campo}.nombre"),
        "storage_preferido": _storage_para_escribir(storage, f"{campo}.storage_preferido"),
    }


def pista_origen_a_dict(config: ConfigPerfil, *, con_pistas: bool) -> dict[str, object] | None:
    """``detalle_origen`` de un perfil. Sin ``con_pistas`` se omiten los nombres de fuente.

    Los ajustes, el modo de clon y «ampliar a» son parte del perfil (no pistas): se escriben
    siempre. ISO sin pistas no deja nada que escribir.
    """
    pista = config.pista_origen
    if pista is None:
        return None
    if config.origen == OrigenSO.ISO:
        if not con_pistas:
            return None
        if pista.drivers is not None:
            exigir_sin_credencial(pista.drivers, "drivers")
            if validar_nombre_archivo(pista.drivers, Contenido.ISO) is not None:
                raise _no_guardable("drivers")
        return {
            "iso": _pista_ref_a_dict(
                pista.nombre_fuente, pista.storage_preferido, Contenido.ISO, "iso"
            ),
            "drivers": pista.drivers,
            "sin_drivers": pista.sin_drivers,
        }
    if config.origen == OrigenSO.IMPORTAR_DISCO:
        datos: dict[str, object] = {"ampliar_a_gib": pista.ampliar_a_gib}
        if con_pistas:
            datos["imagen"] = _pista_ref_a_dict(
                pista.nombre_fuente, pista.storage_preferido, Contenido.IMPORT, "imagen"
            )
        elif pista.ampliar_a_gib is None:
            return None
        return datos
    if config.origen == OrigenSO.CLONAR_PLANTILLA:
        clon: dict[str, object] = {
            "modo": str(pista.modo_clon),
            "ajustes": _ajustes_a_dict(pista.ajustes),
        }
        if con_pistas:
            exigir_sin_credencial(pista.nombre_fuente, "plantilla")
            clon["plantilla"] = {"nombre": pista.nombre_fuente}
        return clon
    return None


def _claves_origen_a_dict(
    tipo_so: TipoSO | None, tpm: bool, agente_qemu: bool, detalle: dict[str, object] | None
) -> dict[str, object]:
    """Claves del MVP 4 de una config: solo las que no valen su valor por defecto."""
    extra: dict[str, object] = {}
    if tipo_so is not None:
        extra["tipo_so"] = str(tipo_so)
    if tpm:
        extra["tpm"] = True
    if agente_qemu:
        extra["agente_qemu"] = True
    if detalle is not None:
        extra["detalle_origen"] = detalle
    return extra


# --- Serializadores (lista blanca por construcción) ---------------------------------------


def _claves_red_fase_a(mtu: int | None, limite_mb: float | None) -> dict[str, object]:
    """``mtu`` y ``limite_mb`` de una tarjeta, solo si no son ``None``."""
    extra: dict[str, object] = {}
    if mtu is not None:
        extra["mtu"] = mtu_para_escribir(mtu, "redes.mtu")
    if limite_mb is not None:
        extra["limite_mb"] = limite_para_escribir(limite_mb, "redes.limite_mb")
    return extra


def _ballooning_a_dict(activo: bool, minimo_mib: int) -> dict[str, object]:
    return {"activo": activo, "minimo_mib": minimo_mib}


def config_perfil_a_dict(config: ConfigPerfil, *, con_pistas: bool) -> dict[str, object]:
    """Configuración de un perfil. Sin ``con_pistas`` se omiten TODAS las claves ``*_preferido``."""
    # INV-M2: ningún texto libre lleva un token (solo se serializan las pistas si se piden).
    exigir_sin_credencial(config.tipo_cpu, "tipo_cpu")
    if con_pistas and config.storage_efi_preferido is not None:
        exigir_sin_credencial(config.storage_efi_preferido, "storage_efi_preferido")
    discos: list[dict[str, object]] = []
    for d in config.discos:
        if con_pistas and d.storage_preferido is not None:
            exigir_sin_credencial(d.storage_preferido, "storage_preferido")
        disco: dict[str, object] = {
            "tamano_gib": d.tamano_gib,
            "bus": str(d.bus),
            "formato": str(d.formato),
            "discard": d.discard,
            "ssd": d.ssd,
            "iothread": d.iothread,
        }
        if con_pistas:
            disco["storage_preferido"] = d.storage_preferido
        discos.append(disco)
    redes: list[dict[str, object]] = []
    for r in config.redes:
        if con_pistas and r.bridge_preferido is not None:
            exigir_sin_credencial(r.bridge_preferido, "bridge_preferido")
        red: dict[str, object] = {"modelo": str(r.modelo), "vlan": r.vlan}
        red.update(_claves_red_fase_a(r.mtu, r.limite_mb))
        if con_pistas:
            red["bridge_preferido"] = r.bridge_preferido
        redes.append(red)
    datos: dict[str, object] = {
        "firmware": str(config.firmware),
        "sockets": config.sockets,
        "cores": config.cores,
        "tipo_cpu": config.tipo_cpu,
        "memoria_mib": config.memoria_mib,
        "ballooning": (
            None
            if config.ballooning is None
            else _ballooning_a_dict(config.ballooning.activo, config.ballooning.minimo_mib)
        ),
        "con_disco": config.con_disco,
        "discos": discos,
        "controlador_scsi": str(config.controlador_scsi),
        "redes": redes,
        "origen": str(config.origen),
    }
    if con_pistas:
        datos["storage_efi_preferido"] = config.storage_efi_preferido
    if config.arranque_auto:
        datos["arranque_auto"] = True  # fase A: el único campo nuevo que guarda un perfil
    datos.update(
        _claves_origen_a_dict(
            config.tipo_so,
            config.tpm,
            config.agente_qemu,
            pista_origen_a_dict(config, con_pistas=con_pistas),
        )
    )
    return datos


def configuracion_a_dict(cfg: ConfiguracionVM) -> dict[str, object]:
    """Configuración de un lote, con storage y bridge reales. Sin vmid/nombre/nodo/etiquetas.

    INV-M2: si algún texto libre parece un token lanza E-M08 (motivo ``credencial``).
    """
    exigir_sin_credencial(cfg.tipo_cpu, "tipo_cpu")
    if cfg.storage_efi is not None:
        exigir_sin_credencial(cfg.storage_efi, "storage_efi")
    for d in cfg.discos:
        exigir_sin_credencial(d.storage, "storage")
    for r in cfg.redes:
        exigir_sin_credencial(r.bridge, "bridge")
    datos: dict[str, object] = {
        "firmware": str(cfg.firmware),
        "sockets": cfg.sockets,
        "cores": cfg.cores,
        "tipo_cpu": cfg.tipo_cpu,
        "memoria_mib": cfg.memoria_mib,
        "ballooning": (
            None
            if cfg.ballooning is None
            else _ballooning_a_dict(cfg.ballooning.activo, cfg.ballooning.minimo_mib)
        ),
        "con_disco": cfg.con_disco,
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
            for d in cfg.discos
        ],
        "storage_efi": cfg.storage_efi,
        "controlador_scsi": str(cfg.controlador_scsi),
        "redes": [
            {
                "bridge": r.bridge,
                "modelo": str(r.modelo),
                "vlan": r.vlan,
                **_claves_red_fase_a(r.mtu, r.limite_mb),
                **claves_red_fase_d(
                    # Solo con «Importar disco» cuenta la MAC (QA-7): otra, residual, no se escribe.
                    r.mac_conservada if conserva_mac(cfg) else None,
                    f"redes[{i}].mac_conservada",
                ),
            }
            for i, r in enumerate(cfg.redes)
        ],
        "origen": str(cfg.origen),
    }
    datos.update(
        _claves_origen_a_dict(cfg.tipo_so, cfg.tpm, cfg.agente_qemu, detalle_origen_a_dict(cfg))
    )
    datos.update(opciones_cfg_a_dict(cfg))
    return datos


# --- Lectura estricta ---------------------------------------------------------------------


@dataclass
class _Hardware:
    """Campos escalares comunes a perfil y lote, ya validados."""

    firmware: Firmware
    sockets: int
    cores: int
    tipo_cpu: str
    memoria_mib: int
    ballooning: tuple[bool, int] | None
    con_disco: bool
    controlador_scsi: ControladorScsi
    origen: OrigenSO
    tipo_so: TipoSO | None = None
    tpm: bool = False
    agente_qemu: bool = False


def _limites(perfil: bool, minimo: int, maximo: int) -> tuple[int, int]:
    """Rango de M1 en modo perfil; solo un tope de cordura en modo lote."""
    return (minimo, maximo) if perfil else (0, _TOPE_CORDURA)


def _entero(
    lector: LectorEsquema,
    obj: dict[str, object],
    clave: str,
    ruta: str,
    limites: tuple[int, int],
    *,
    nulo: bool = False,
    requerido: bool = True,
) -> int | None:
    return lector.entero(
        obj, clave, ruta, minimo=limites[0], maximo=limites[1], nulo=nulo, requerido=requerido
    )


def _leer_hardware(
    lector: LectorEsquema, obj: dict[str, object], ruta: str, *, perfil: bool
) -> _Hardware | None:
    n0 = len(lector.errores)
    firmware = lector.enumerado(
        obj, "firmware", ruta, Firmware, requerido=False, defecto=Firmware.SEABIOS
    )
    sockets = _entero(lector, obj, "sockets", ruta, _limites(perfil, SOCKETS_MIN, SOCKETS_MAX))
    cores = _entero(lector, obj, "cores", ruta, _limites(perfil, CORES_MIN, CORES_MAX))
    tipo_cpu = lector.texto(
        obj, "tipo_cpu", ruta, minimo=1 if perfil else 0,
        maximo=MAX_LONG_TIPO_CPU if perfil else _MAX_TEXTO_LOTE, requerido=False,
        defecto=ConfigPerfil.tipo_cpu, sin_token=True,
    )  # fmt: skip
    memoria = _entero(
        lector, obj, "memoria_mib", ruta, _limites(perfil, MEMORIA_MIN_MIB, _TOPE_CORDURA)
    )
    ballooning: tuple[bool, int] | None = None
    if obj.get("ballooning") is not None:
        ruta_b = f"{ruta}.ballooning" if ruta else "ballooning"
        sub = lector.objeto(obj["ballooning"], ruta_b, _CLAVES_BALLOONING)
        if sub is not None:
            activo = lector.booleano(sub, "activo", ruta_b)
            minimo = _entero(
                lector, sub, "minimo_mib", ruta_b, _limites(perfil, MEMORIA_MIN_MIB, _TOPE_CORDURA)
            )
            if activo is not None and minimo is not None:
                ballooning = (activo, minimo)
    con_disco = lector.booleano(obj, "con_disco", ruta)
    controlador = lector.enumerado(
        obj, "controlador_scsi", ruta, ControladorScsi, requerido=False,
        defecto=ControladorScsi.VIRTIO_SINGLE,
    )  # fmt: skip
    origen = lector.enumerado(
        obj, "origen", ruta, OrigenSO, requerido=False, defecto=OrigenSO.DISCO_VACIO
    )
    tipo_so = lector.enumerado(obj, "tipo_so", ruta, TipoSO, requerido=False)
    tpm = lector.booleano(obj, "tpm", ruta, requerido=False, defecto=False)
    agente_qemu = lector.booleano(obj, "agente_qemu", ruta, requerido=False, defecto=False)
    if (
        len(lector.errores) > n0
        or firmware is None
        or sockets is None
        or cores is None
        or tipo_cpu is None
        or memoria is None
        or con_disco is None
        or controlador is None
        or origen is None
        or tpm is None
        or agente_qemu is None
    ):
        return None
    return _Hardware(
        firmware,
        sockets,
        cores,
        tipo_cpu,
        memoria,
        ballooning,
        con_disco,
        controlador,
        origen,
        tipo_so,
        tpm,
        agente_qemu,
    )


def _campos_disco(
    lector: LectorEsquema, d: dict[str, object], ruta: str, *, perfil: bool
) -> tuple[int, Bus, FormatoDisco, bool, bool, bool] | None:
    n0 = len(lector.errores)
    tamano = _entero(lector, d, "tamano_gib", ruta, _limites(perfil, DISCO_MIN_GIB, DISCO_MAX_GIB))
    bus = lector.enumerado(d, "bus", ruta, Bus, requerido=False, defecto=Bus.SCSI)
    formato = lector.enumerado(
        d, "formato", ruta, FormatoDisco, requerido=False, defecto=FormatoDisco.AUTO
    )
    discard = lector.booleano(d, "discard", ruta, requerido=False, defecto=True)
    ssd = lector.booleano(d, "ssd", ruta, requerido=False, defecto=True)
    iothread = lector.booleano(d, "iothread", ruta, requerido=False, defecto=True)
    if (
        len(lector.errores) > n0
        or tamano is None
        or bus is None
        or formato is None
        or discard is None
        or ssd is None
        or iothread is None
    ):
        return None
    return tamano, bus, formato, discard, ssd, iothread


def _campos_red(
    lector: LectorEsquema, r: dict[str, object], ruta: str, *, perfil: bool
) -> tuple[ModeloRed, int | None, int | None, float | None] | None:
    n0 = len(lector.errores)
    modelo = lector.enumerado(
        r, "modelo", ruta, ModeloRed, requerido=False, defecto=ModeloRed.VIRTIO
    )
    vlan = _entero(
        lector, r, "vlan", ruta, _limites(perfil, VLAN_MIN, VLAN_MAX), nulo=True, requerido=False
    )
    _, mtu = leer_mtu(lector, r, ruta)
    _, limite = leer_limite(lector, r, ruta)
    if len(lector.errores) > n0 or modelo is None:
        return None
    return modelo, vlan, mtu, limite


def _pista(lector: LectorEsquema, obj: dict[str, object], clave: str, ruta: str) -> str | None:
    """Texto opcional (pista o storage/bridge efi): ausente o ``null`` → ``None``."""
    return lector.texto(
        obj,
        clave,
        ruta,
        minimo=1,
        maximo=MAX_LONG_TEXTO,
        nulo=True,
        requerido=False,
        sin_token=True,
    )


# --- Lectura del origen del SO (MVP 4) -----------------------------------------------------


def _nombre_archivo(
    lector: LectorEsquema, obj: dict[str, object], clave: str, ruta: str, contenido: Contenido
) -> str | None:
    """Nombre de archivo del servidor (lista blanca). ``""`` = sin elegir; inválido → error."""
    nombre = lector.texto(
        obj, clave, ruta, maximo=MAX_LONG_TEXTO,
        requerido=False, defecto="", sin_token=True,
    )  # fmt: skip
    if nombre and validar_nombre_archivo(nombre, contenido) is not None:
        lector.error(f"{ruta}.{clave}" if ruta else clave, MotivoCampo.TEXTO_NO_VALIDO)
        return None
    return nombre


def _volid(
    lector: LectorEsquema, obj: dict[str, object], ruta: str, contenido: Contenido
) -> str | None:
    """``volid`` opcional: ausente, ``null`` o ``""`` → ``None``; no admitido → error."""
    volid = lector.texto(
        obj, "volid", ruta, maximo=MAX_LONG_TEXTO, nulo=True, requerido=False, sin_token=True
    )
    if volid and validar_volid(volid, contenido) is not None:
        lector.error(f"{ruta}.volid" if ruta else "volid", MotivoCampo.TEXTO_NO_VALIDO)
        return None
    return volid or None


def _storage_texto(
    lector: LectorEsquema, obj: dict[str, object], clave: str, ruta: str
) -> str | None:
    """Nombre de storage (pista o destino): ``[A-Za-z0-9._-]``, hasta 64; ``null`` → ``None``."""
    valor = lector.texto(
        obj, clave, ruta, maximo=MAX_LONG_TEXTO, nulo=True, requerido=False, sin_token=True
    )
    if valor is not None and not _storage_valido(valor):
        lector.error(f"{ruta}.{clave}" if ruta else clave, MotivoCampo.TEXTO_NO_VALIDO)
        return None
    return valor


def _leer_ref_volumen(
    lector: LectorEsquema, valor: object, ruta: str, contenido: Contenido
) -> RefVolumen | None:
    obj = lector.objeto(valor, ruta, _CLAVES_REF_LOTE)
    if obj is None:
        return None
    n0 = len(lector.errores)
    nombre = _nombre_archivo(lector, obj, "nombre", ruta, contenido)
    volid = _volid(lector, obj, ruta, contenido)
    if len(lector.errores) > n0 or nombre is None:
        return None
    if volid is not None and not nombre:
        partes = partes_volid(volid)
        nombre = partes[2] if partes is not None else ""
    return RefVolumen(nombre=nombre, volid=volid)


def _leer_ajustes(
    lector: LectorEsquema, valor: object, ruta: str, *, perfil: bool
) -> AjustesClon | None:
    if valor is None:
        return AjustesClon()
    obj = lector.objeto(valor, ruta, _CLAVES_AJUSTES)
    if obj is None:
        return None
    n0 = len(lector.errores)
    sockets = _entero(
        lector, obj, "sockets", ruta, _limites(perfil, SOCKETS_MIN, SOCKETS_MAX),
        nulo=True, requerido=False,
    )  # fmt: skip
    cores = _entero(
        lector, obj, "cores", ruta, _limites(perfil, CORES_MIN, CORES_MAX),
        nulo=True, requerido=False,
    )  # fmt: skip
    memoria = _entero(
        lector, obj, "memoria_mib", ruta, _limites(perfil, MEMORIA_MIN_MIB, _TOPE_CORDURA),
        nulo=True, requerido=False,
    )  # fmt: skip
    disco = _entero(
        lector, obj, "disco_gib", ruta, _limites(perfil, DISCO_MIN_GIB, DISCO_MAX_GIB),
        nulo=True, requerido=False,
    )  # fmt: skip
    tipo_cpu = lector.texto(
        obj, "tipo_cpu", ruta, minimo=1 if perfil else 0,
        maximo=MAX_LONG_TIPO_CPU if perfil else _MAX_TEXTO_LOTE,
        nulo=True, requerido=False, sin_token=True,
    )  # fmt: skip
    if len(lector.errores) > n0:
        return None
    return AjustesClon(sockets, cores, tipo_cpu, memoria, disco)


def _ruta_hija(ruta: str, clave: str) -> str:
    return f"{ruta}.{clave}" if ruta else clave


def _leer_plantilla(
    lector: LectorEsquema, valor: object, ruta: str, *, perfil: bool
) -> RefPlantilla | None:
    obj = lector.objeto(valor, ruta, _CLAVES_PLANTILLA_PERFIL if perfil else _CLAVES_PLANTILLA_LOTE)
    if obj is None:
        return None
    n0 = len(lector.errores)
    nombre = lector.texto(
        obj, "nombre", ruta, maximo=_MAX_LONG_NOMBRE_PLANTILLA, requerido=False, defecto="",
        sin_token=True,
    )  # fmt: skip
    vmid = (
        None
        if perfil
        else lector.entero(
            obj, "vmid", ruta, minimo=0, maximo=_TOPE_CORDURA, nulo=True, requerido=False
        )
    )
    if len(lector.errores) > n0 or nombre is None:
        return None
    return RefPlantilla(nombre=nombre, vmid=vmid)


def leer_detalle_origen(
    lector: LectorEsquema,
    valor: object,
    ruta: str,
    origen: OrigenSO,
    n_discos: int | None = None,
) -> DetalleOrigen | None:
    """Lee ``detalle_origen`` de un lote (modo lote) según el ``origen`` de su config.

    ``None`` con errores anotados en ``lector``. Un detalle con ``origen = disco_vacio`` es ajeno
    y se rechaza. Los volids pasan la lista blanca; nunca se leen URL, rutas ni checksums.
    Con ``n_discos`` se rechaza una imagen adicional de un disco que no existe.
    """
    if origen == OrigenSO.DISCO_VACIO:
        lector.error(ruta, MotivoCampo.TIPO)
        return None
    if origen == OrigenSO.ISO:
        obj = lector.objeto(valor, ruta, frozenset({"iso", "drivers", "sin_drivers"}))
        if obj is None:
            return None
        n0 = len(lector.errores)
        iso = (
            _leer_ref_volumen(lector, obj["iso"], _ruta_hija(ruta, "iso"), Contenido.ISO)
            if "iso" in obj
            else RefVolumen()
        )
        drivers = (
            None
            if obj.get("drivers") is None
            else _leer_ref_volumen(
                lector, obj["drivers"], _ruta_hija(ruta, "drivers"), Contenido.ISO
            )
        )
        sin_drivers = lector.booleano(obj, "sin_drivers", ruta, requerido=False, defecto=False)
        if len(lector.errores) > n0 or iso is None or sin_drivers is None:
            return None
        return DetalleIso(iso=iso, drivers=drivers, sin_drivers=sin_drivers)
    if origen == OrigenSO.IMPORTAR_DISCO:
        obj = lector.objeto(valor, ruta, frozenset({"imagen", "ampliar_a_gib", "imagenes"}))
        if obj is None:
            return None
        n0 = len(lector.errores)
        imagen = (
            _leer_ref_volumen(lector, obj["imagen"], _ruta_hija(ruta, "imagen"), Contenido.IMPORT)
            if "imagen" in obj
            else RefVolumen()
        )
        ampliar = _entero(
            lector, obj, "ampliar_a_gib", ruta, (0, _TOPE_CORDURA), nulo=True, requerido=False
        )
        otras = (
            leer_imagenes(lector, obj["imagenes"], _ruta_hija(ruta, "imagenes"), n_discos)
            if obj.get("imagenes") is not None
            else ()
        )
        if len(lector.errores) > n0 or imagen is None:
            return None
        return DetalleImportacion(imagen=imagen, ampliar_a_gib=ampliar, otras=otras)
    obj = lector.objeto(valor, ruta, frozenset({"plantilla", "modo", "ajustes", "storage_destino"}))
    if obj is None:
        return None
    n0 = len(lector.errores)
    plantilla = (
        _leer_plantilla(lector, obj["plantilla"], _ruta_hija(ruta, "plantilla"), perfil=False)
        if "plantilla" in obj
        else RefPlantilla()
    )
    modo = lector.enumerado(
        obj, "modo", ruta, ModoClon, requerido=False, defecto=ModoClon.AUTOMATICO
    )
    ajustes = _leer_ajustes(lector, obj.get("ajustes"), _ruta_hija(ruta, "ajustes"), perfil=False)
    destino = _storage_texto(lector, obj, "storage_destino", ruta)
    if len(lector.errores) > n0 or plantilla is None or modo is None or ajustes is None:
        return None
    return DetalleClon(plantilla=plantilla, modo=modo, ajustes=ajustes, storage_destino=destino)


def _leer_pista_ref(
    lector: LectorEsquema, valor: object, ruta: str, contenido: Contenido
) -> tuple[str, str | None] | None:
    obj = lector.objeto(valor, ruta, _CLAVES_REF_PERFIL)
    if obj is None:
        return None
    n0 = len(lector.errores)
    nombre = _nombre_archivo(lector, obj, "nombre", ruta, contenido)
    storage = _storage_texto(lector, obj, "storage_preferido", ruta)
    if len(lector.errores) > n0 or nombre is None:
        return None
    return nombre, storage


def leer_pista_origen(
    lector: LectorEsquema, valor: object, ruta: str, origen: OrigenSO
) -> PistaOrigen | None:
    """Lee el ``detalle_origen`` de un perfil (pista) según el ``origen`` de su config."""
    if origen == OrigenSO.DISCO_VACIO:
        lector.error(ruta, MotivoCampo.TIPO)
        return None
    n0 = len(lector.errores)
    if origen == OrigenSO.ISO:
        obj = lector.objeto(valor, ruta, frozenset({"iso", "drivers", "sin_drivers"}))
        if obj is None:
            return None
        ref = (
            _leer_pista_ref(lector, obj["iso"], _ruta_hija(ruta, "iso"), Contenido.ISO)
            if "iso" in obj
            else ("", None)
        )
        drivers = lector.texto(
            obj, "drivers", ruta, maximo=MAX_LONG_TEXTO, nulo=True, requerido=False, sin_token=True
        )
        if drivers and validar_nombre_archivo(drivers, Contenido.ISO) is not None:
            lector.error(_ruta_hija(ruta, "drivers"), MotivoCampo.TEXTO_NO_VALIDO)
        sin_drivers = lector.booleano(obj, "sin_drivers", ruta, requerido=False, defecto=False)
        if len(lector.errores) > n0 or ref is None or sin_drivers is None:
            return None
        return PistaOrigen(
            nombre_fuente=ref[0],
            storage_preferido=ref[1],
            drivers=drivers or None,
            sin_drivers=sin_drivers,
        )
    if origen == OrigenSO.IMPORTAR_DISCO:
        obj = lector.objeto(valor, ruta, frozenset({"imagen", "ampliar_a_gib"}))
        if obj is None:
            return None
        ref = (
            _leer_pista_ref(lector, obj["imagen"], _ruta_hija(ruta, "imagen"), Contenido.IMPORT)
            if "imagen" in obj
            else ("", None)
        )
        ampliar = _entero(
            lector, obj, "ampliar_a_gib", ruta, (DISCO_MIN_GIB, DISCO_MAX_GIB),
            nulo=True, requerido=False,
        )  # fmt: skip
        if len(lector.errores) > n0 or ref is None:
            return None
        return PistaOrigen(nombre_fuente=ref[0], storage_preferido=ref[1], ampliar_a_gib=ampliar)
    obj = lector.objeto(valor, ruta, frozenset({"plantilla", "modo", "ajustes"}))
    if obj is None:
        return None
    plantilla = (
        _leer_plantilla(lector, obj["plantilla"], _ruta_hija(ruta, "plantilla"), perfil=True)
        if "plantilla" in obj
        else RefPlantilla()
    )
    modo = lector.enumerado(
        obj, "modo", ruta, ModoClon, requerido=False, defecto=ModoClon.AUTOMATICO
    )
    ajustes = _leer_ajustes(lector, obj.get("ajustes"), _ruta_hija(ruta, "ajustes"), perfil=True)
    if len(lector.errores) > n0 or plantilla is None or modo is None or ajustes is None:
        return None
    return PistaOrigen(nombre_fuente=plantilla.nombre, modo_clon=modo, ajustes=ajustes)


def leer_config_perfil(lector: LectorEsquema, valor: object, ruta: str) -> ConfigPerfil | None:
    """Lee y valida la configuración de un perfil (modo perfil). ``None`` si hay errores."""
    obj = lector.objeto(valor, ruta, CLAVES_CONFIG_PERFIL)
    if obj is None:
        return None
    n0 = len(lector.errores)
    hw = _leer_hardware(lector, obj, ruta, perfil=True)
    pista_efi = _pista(lector, obj, "storage_efi_preferido", ruta)
    ruta_d = f"{ruta}.discos" if ruta else "discos"
    ruta_r = f"{ruta}.redes" if ruta else "redes"
    discos: list[DiscoPerfil] = []
    for i, item in enumerate(lector.lista(obj, "discos", ruta, maximo=MAX_DISCOS) or []):
        r = f"{ruta_d}[{i}]"
        d = lector.objeto(item, r, CLAVES_DISCO_PERFIL)
        if d is None:
            continue
        campos = _campos_disco(lector, d, r, perfil=True)
        pista = _pista(lector, d, "storage_preferido", r)
        if campos is not None:
            discos.append(DiscoPerfil(*campos, storage_preferido=pista))
    redes: list[RedPerfil] = []
    for i, item in enumerate(lector.lista(obj, "redes", ruta, maximo=MAX_INTERFACES_RED) or []):
        r = f"{ruta_r}[{i}]"
        red = lector.objeto(item, r, CLAVES_RED_PERFIL)
        if red is None:
            continue
        campos_r = _campos_red(lector, red, r, perfil=True)
        pista = _pista(lector, red, "bridge_preferido", r)
        if campos_r is not None:
            redes.append(RedPerfil(campos_r[0], campos_r[1], pista, campos_r[2], campos_r[3]))
    arranque_auto = lector.booleano(obj, "arranque_auto", ruta, requerido=False, defecto=False)
    pista_org: PistaOrigen | None = None
    if "detalle_origen" in obj and hw is not None:
        pista_org = leer_pista_origen(
            lector, obj["detalle_origen"], _ruta_hija(ruta, "detalle_origen"), hw.origen
        )
    if len(lector.errores) > n0 or hw is None or arranque_auto is None:
        return None
    return ConfigPerfil(
        firmware=hw.firmware,
        sockets=hw.sockets,
        cores=hw.cores,
        tipo_cpu=hw.tipo_cpu,
        memoria_mib=hw.memoria_mib,
        ballooning=None if hw.ballooning is None else BallooningPerfil(*hw.ballooning),
        con_disco=hw.con_disco,
        discos=tuple(discos),
        storage_efi_preferido=pista_efi,
        controlador_scsi=hw.controlador_scsi,
        redes=tuple(redes),
        origen=hw.origen,
        tipo_so=hw.tipo_so,
        tpm=hw.tpm,
        agente_qemu=hw.agente_qemu,
        pista_origen=pista_org,
        arranque_auto=arranque_auto,
    )


def leer_configuracion(lector: LectorEsquema, valor: object, ruta: str) -> ConfiguracionVM | None:
    """Lee la configuración de un lote (modo lote). ``vmid=0``, ``nombre=""``, ``nodo=""``.

    No usa ``ConfiguracionVM.desde_dict`` (no valida tipos). Las reglas de rango se
    revalidan en el formulario; aquí solo se exige el tipo correcto.
    """
    obj = lector.objeto(valor, ruta, CLAVES_CONFIG_LOTE)
    if obj is None:
        return None
    n0 = len(lector.errores)
    hw = _leer_hardware(lector, obj, ruta, perfil=False)
    storage_efi = _pista(lector, obj, "storage_efi", ruta)
    ruta_d = f"{ruta}.discos" if ruta else "discos"
    ruta_r = f"{ruta}.redes" if ruta else "redes"
    discos: list[Disco] = []
    for i, item in enumerate(lector.lista(obj, "discos", ruta, maximo=_MAX_LISTA_LOTE) or []):
        r = f"{ruta_d}[{i}]"
        d = lector.objeto(item, r, CLAVES_DISCO_LOTE)
        if d is None:
            continue
        campos = _campos_disco(lector, d, r, perfil=False)
        storage = lector.texto(d, "storage", r, minimo=0, maximo=MAX_LONG_TEXTO, sin_token=True)
        if campos is not None and storage is not None:
            tamano, bus, formato, discard, ssd, iothread = campos
            discos.append(Disco(storage, tamano, bus, formato, discard, ssd, iothread))
    redes: list[InterfazRed] = []
    for i, item in enumerate(lector.lista(obj, "redes", ruta, maximo=_MAX_LISTA_LOTE) or []):
        r = f"{ruta_r}[{i}]"
        red = lector.objeto(item, r, CLAVES_RED_LOTE)
        if red is None:
            continue
        campos_r = _campos_red(lector, red, r, perfil=False)
        bridge = lector.texto(red, "bridge", r, minimo=0, maximo=MAX_LONG_TEXTO, sin_token=True)
        mac = leer_mac_conservada(lector, red, r)
        if campos_r is not None and bridge is not None:
            redes.append(
                InterfazRed(
                    bridge, campos_r[0], campos_r[1], campos_r[2], campos_r[3], mac_conservada=mac
                )
            )
    detalle: DetalleOrigen | None = None
    if "detalle_origen" in obj and hw is not None:
        detalle = leer_detalle_origen(
            lector,
            obj["detalle_origen"],
            _ruta_hija(ruta, "detalle_origen"),
            hw.origen,
            len(discos),
        )
    opciones = leer_opciones_cfg(lector, obj, ruta)
    if len(lector.errores) > n0 or hw is None or opciones is None:
        return None
    return ConfiguracionVM(
        vmid=0,
        nombre="",
        nodo="",
        firmware=hw.firmware,
        storage_efi=storage_efi,
        sockets=hw.sockets,
        cores=hw.cores,
        tipo_cpu=hw.tipo_cpu,
        memoria_mib=hw.memoria_mib,
        ballooning=None if hw.ballooning is None else Ballooning(*hw.ballooning),
        con_disco=hw.con_disco,
        discos=discos,
        controlador_scsi=hw.controlador_scsi,
        redes=redes,
        origen=hw.origen,
        tipo_so=hw.tipo_so,
        tpm=hw.tpm,
        agente_qemu=hw.agente_qemu,
        detalle_origen=detalle,
        encender=opciones.encender,
        arranque_auto=opciones.arranque_auto,
        arranque_orden=opciones.arranque_orden,
        arranque_espera=opciones.arranque_espera,
        notas_origen=opciones.notas_origen,
        notas_usuario=opciones.notas_usuario,
        notas=opciones.notas,
        etiquetas_usuario=opciones.etiquetas_usuario,
        pool=opciones.pool,
        proteger=opciones.proteger,
        cloudinit=opciones.cloudinit,
        esperar_ip=opciones.esperar_ip,
        plazo_ip_s=opciones.plazo_ip_s,
        red_clon=opciones.red_clon,
        firewall=opciones.firewall,
        hardware_cluster=opciones.hardware_cluster,
    )
