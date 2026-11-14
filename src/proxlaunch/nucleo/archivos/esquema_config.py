"""Lista blanca de la configuración de hardware en archivos (RF-X04, CA-X01.8).

Dos modos con las mismas claves de hardware:

- **perfil**: sin storage/bridge reales; solo pistas opcionales (``storage_preferido`` por
  disco, ``storage_efi_preferido``, ``bridge_preferido`` por red). Los rangos de capa 1 de M1
  se comprueban en el esquema (importando las constantes de ``validacion.py``).
- **lote**: con ``storage``, ``storage_efi`` y ``bridge`` reales. Solo se exige el tipo
  correcto y un tope de cordura: las reglas de rango (V-05, V-08...) las muestra el formulario
  tras cargar (un lote guardado puede ser un borrador, CA-G02.1).

Los serializadores escriben campo a campo (sin volcado genérico) y nunca incluyen ``vmid``,
``nombre``, ``nodo`` ni ``etiquetas``.
"""

from __future__ import annotations

from dataclasses import dataclass

from proxlaunch.nucleo.archivos.constantes import MAX_LONG_TEXTO
from proxlaunch.nucleo.archivos.esquema import LectorEsquema
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
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    BallooningPerfil,
    ConfigPerfil,
    DiscoPerfil,
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
MAX_LONG_TIPO_CPU = 64

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
    }
)
CLAVES_CONFIG_PERFIL = _CLAVES_BASE | {"storage_efi_preferido"}
CLAVES_CONFIG_LOTE = _CLAVES_BASE | {"storage_efi"}
_CLAVES_DISCO = frozenset({"tamano_gib", "bus", "formato", "discard", "ssd", "iothread"})
CLAVES_DISCO_PERFIL = _CLAVES_DISCO | {"storage_preferido"}
CLAVES_DISCO_LOTE = _CLAVES_DISCO | {"storage"}
_CLAVES_RED = frozenset({"modelo", "vlan"})
CLAVES_RED_PERFIL = _CLAVES_RED | {"bridge_preferido"}
CLAVES_RED_LOTE = _CLAVES_RED | {"bridge"}
_CLAVES_BALLOONING = frozenset({"activo", "minimo_mib"})


# --- Serializadores (lista blanca por construcción) ---------------------------------------


def _ballooning_a_dict(activo: bool, minimo_mib: int) -> dict[str, object]:
    return {"activo": activo, "minimo_mib": minimo_mib}


def config_perfil_a_dict(config: ConfigPerfil, *, con_pistas: bool) -> dict[str, object]:
    """Configuración de un perfil. Sin ``con_pistas`` se omiten TODAS las claves ``*_preferido``."""
    discos: list[dict[str, object]] = []
    for d in config.discos:
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
        red: dict[str, object] = {"modelo": str(r.modelo), "vlan": r.vlan}
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
    return datos


def configuracion_a_dict(cfg: ConfiguracionVM) -> dict[str, object]:
    """Configuración de un lote, con storage y bridge reales. Sin vmid/nombre/nodo/etiquetas."""
    return {
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
        "redes": [{"bridge": r.bridge, "modelo": str(r.modelo), "vlan": r.vlan} for r in cfg.redes],
        "origen": str(cfg.origen),
    }


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
        obj, "tipo_cpu", ruta, minimo=1, maximo=MAX_LONG_TIPO_CPU, requerido=False,
        defecto=ConfigPerfil.tipo_cpu,
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
    ):
        return None
    return _Hardware(
        firmware, sockets, cores, tipo_cpu, memoria, ballooning, con_disco, controlador, origen
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
) -> tuple[ModeloRed, int | None] | None:
    n0 = len(lector.errores)
    modelo = lector.enumerado(
        r, "modelo", ruta, ModeloRed, requerido=False, defecto=ModeloRed.VIRTIO
    )
    vlan = _entero(
        lector, r, "vlan", ruta, _limites(perfil, VLAN_MIN, VLAN_MAX), nulo=True, requerido=False
    )
    if len(lector.errores) > n0 or modelo is None:
        return None
    return modelo, vlan


def _pista(lector: LectorEsquema, obj: dict[str, object], clave: str, ruta: str) -> str | None:
    """Texto opcional (pista o storage/bridge efi): ausente o ``null`` → ``None``."""
    return lector.texto(
        obj, clave, ruta, minimo=1, maximo=MAX_LONG_TEXTO, nulo=True, requerido=False
    )


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
            redes.append(RedPerfil(campos_r[0], campos_r[1], pista))
    if len(lector.errores) > n0 or hw is None:
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
    for i, item in enumerate(lector.lista(obj, "discos", ruta, maximo=MAX_DISCOS) or []):
        r = f"{ruta_d}[{i}]"
        d = lector.objeto(item, r, CLAVES_DISCO_LOTE)
        if d is None:
            continue
        campos = _campos_disco(lector, d, r, perfil=False)
        storage = lector.texto(d, "storage", r, minimo=0, maximo=MAX_LONG_TEXTO)
        if campos is not None and storage is not None:
            tamano, bus, formato, discard, ssd, iothread = campos
            discos.append(Disco(storage, tamano, bus, formato, discard, ssd, iothread))
    redes: list[InterfazRed] = []
    for i, item in enumerate(lector.lista(obj, "redes", ruta, maximo=MAX_INTERFACES_RED) or []):
        r = f"{ruta_r}[{i}]"
        red = lector.objeto(item, r, CLAVES_RED_LOTE)
        if red is None:
            continue
        campos_r = _campos_red(lector, red, r, perfil=False)
        bridge = lector.texto(red, "bridge", r, minimo=0, maximo=MAX_LONG_TEXTO)
        if campos_r is not None and bridge is not None:
            redes.append(InterfazRed(bridge, campos_r[0], campos_r[1]))
    if len(lector.errores) > n0 or hw is None:
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
    )
