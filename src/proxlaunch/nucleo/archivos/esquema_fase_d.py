"""Lista blanca de la fase D (0.9) en archivos de lote: mapeos PCI/USB, MAC conservada e imágenes.

Cubre ``hardware_cluster`` (en la configuración de una MV), ``mac_conservada`` (por tarjeta de red,
solo en lotes) e ``imagenes`` (en el detalle del origen «importar disco»: una entrada por disco
adicional). Todo se omite si vale su defecto: un lote sin nada de la fase D queda idéntico al de
0.8.0 (y con la misma versión). Solo se escribe la versión 6 si hay algo de D (P-D9, RF-D6.1).

La serialización de las asignaciones la hace este módulo (el modelo ya sabe escribir las suyas,
pero el archivo tiene sus propias claves y controles): el lector valida tipo y RANGO con la ruta
del campo (``…hardware_cluster.pci[0].mapeo``, CA-D6.1.6) y el escritor pasa lo que produce por
ese mismo lector (si lo rechazaría no se guarda: ``ARCHIVO_NO_GUARDABLE``) y rechaza textos con
aspecto de token (``exigir_sin_credencial``, CA-D6.1.9). Un perfil no guarda nada de D (RF-D6.2).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from proxlaunch.nucleo.archivos.esquema import LectorEsquema, MotivoCampo
from proxlaunch.nucleo.archivos.texto import exigir_sin_credencial
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import (
    MAX_PCI,
    MAX_USB,
    RE_ID_MAPEO,
    AsignacionPCI,
    AsignacionUSB,
    HardwareCluster,
)
from proxlaunch.nucleo.libvirt.validacion import conserva_mac, mac_valida
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, ImagenDisco
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil
from proxlaunch.nucleo.validacion import MAX_DISPOSITIVOS

CLAVES_HARDWARE = frozenset({"pci", "usb"})
CLAVES_PCI = frozenset({"mapeo", "pcie", "x_vga", "rombar", "driver_keep"})
CLAVES_USB = frozenset({"mapeo", "usb3"})
CLAVES_IMAGEN = frozenset({"disco", "imagen", "crear_vacio"})
_MAX_ID_MAPEO = 64  # largo máximo de ``RE_ID_MAPEO``
_MAX_DISCO_IMAGEN = sum(MAX_DISPOSITIVOS.values()) - 1  # el disco 0 usa ``imagen``, no ``imagenes``


def _no_guardable(campo: str) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "caracteres", "campo": campo}
    )


def _ruta(base: str, clave: str) -> str:
    return f"{base}.{clave}" if base else clave


# --- Qué versión de archivo hace falta ----------------------------------------------------------


def hardware_requiere_v6(hw: HardwareCluster | None) -> bool:
    """¿Hay mapeos PCI o USB que escribir? Un hardware vacío equivale a no tenerlo."""
    return hw is not None and not hw.vacio


def imagenes_requieren_v6(otras: Sequence[ImagenDisco]) -> bool:
    """¿Hay imágenes adicionales (discos 1 en adelante)? Cuentan también las pendientes: al
    reabrir el lote deben seguir pendientes (V-D27) y no convertirse en discos vacíos."""
    return bool(otras)


def requiere_version_6(cfg: ConfiguracionVM | ConfigPerfil) -> bool:
    """¿La configuración usa algo de la fase D? Entonces el lote se escribe como v6 (RF-D6.1).

    Cuenta los mapeos PCI/USB, la MAC conservada de alguna tarjeta y más de una imagen importada
    (alguna de los discos 1 en adelante). CPU ``custom-*`` y valores ARM no suben la versión. Un
    perfil nunca lo usa: no guarda nada de la fase D (RF-D6.2)."""
    if isinstance(cfg, ConfigPerfil):
        return False
    if hardware_requiere_v6(cfg.hardware_cluster):
        return True
    if conserva_mac(cfg) and any(r.mac_conservada is not None for r in cfg.redes):
        return True
    det = cfg.detalle_origen
    return isinstance(det, DetalleImportacion) and imagenes_requieren_v6(det.otras)


# --- Lectura ------------------------------------------------------------------------------------


def _leer_id_mapeo(lector: LectorEsquema, obj: dict[str, object], ruta: str) -> str | None:
    """Id del mapeo (``mapeo``): ``RE_ID_MAPEO`` y sin aspecto de token."""
    texto = lector.texto(obj, "mapeo", ruta, minimo=1, maximo=_MAX_ID_MAPEO, sin_token=True)
    if texto is not None and RE_ID_MAPEO.fullmatch(texto) is None:
        lector.error(_ruta(ruta, "mapeo"), MotivoCampo.TEXTO_NO_VALIDO)
        return None
    return texto


def _leer_pci(lector: LectorEsquema, valor: object, ruta: str) -> AsignacionPCI | None:
    obj = lector.objeto(valor, ruta, CLAVES_PCI)
    if obj is None:
        return None
    n0 = len(lector.errores)
    mapeo = _leer_id_mapeo(lector, obj, ruta)
    pcie = lector.booleano(obj, "pcie", ruta, requerido=False, defecto=False)
    x_vga = lector.booleano(obj, "x_vga", ruta, requerido=False, defecto=False)
    rombar = lector.booleano(obj, "rombar", ruta, requerido=False, defecto=True)
    driver_keep = lector.booleano(obj, "driver_keep", ruta, requerido=False, defecto=False)
    if (
        len(lector.errores) > n0
        or mapeo is None
        or pcie is None
        or x_vga is None
        or rombar is None
        or driver_keep is None
    ):
        return None
    return AsignacionPCI(
        mapeo=mapeo, pcie=pcie, x_vga=x_vga, rombar=rombar, driver_keep=driver_keep
    )


def _leer_usb(lector: LectorEsquema, valor: object, ruta: str) -> AsignacionUSB | None:
    obj = lector.objeto(valor, ruta, CLAVES_USB)
    if obj is None:
        return None
    n0 = len(lector.errores)
    mapeo = _leer_id_mapeo(lector, obj, ruta)
    usb3 = lector.booleano(obj, "usb3", ruta, requerido=False, defecto=False)
    if len(lector.errores) > n0 or mapeo is None or usb3 is None:
        return None
    return AsignacionUSB(mapeo=mapeo, usb3=usb3)


def leer_hardware(lector: LectorEsquema, valor: object, ruta: str) -> HardwareCluster | None:
    """Lee ``hardware_cluster`` {``pci``, ``usb``}. ``None`` ante un error (anotado en el lector).

    Un objeto sin asignaciones da un ``HardwareCluster`` vacío; quien lo recibe lo trata como
    «sin hardware de clúster»."""
    obj = lector.objeto(valor, ruta, CLAVES_HARDWARE)
    if obj is None:
        return None
    n0 = len(lector.errores)
    pci: list[AsignacionPCI] = []
    usb: list[AsignacionUSB] = []
    base_pci = _ruta(ruta, "pci")
    for i, item in enumerate(lector.lista(obj, "pci", ruta, maximo=MAX_PCI, requerido=False) or []):
        leida = _leer_pci(lector, item, f"{base_pci}[{i}]")
        if leida is not None:
            pci.append(leida)
    base_usb = _ruta(ruta, "usb")
    for i, item in enumerate(lector.lista(obj, "usb", ruta, maximo=MAX_USB, requerido=False) or []):
        leida_usb = _leer_usb(lector, item, f"{base_usb}[{i}]")
        if leida_usb is not None:
            usb.append(leida_usb)
    if len(lector.errores) > n0:
        return None
    return HardwareCluster(pci=tuple(pci), usb=tuple(usb))


def leer_imagenes(
    lector: LectorEsquema, valor: object, ruta: str, n_discos: int | None = None
) -> tuple[ImagenDisco, ...]:
    """Lee ``imagenes`` de un origen «importar disco»: [{``disco``, ``imagen``, ``crear_vacio``}].

    ``imagen`` es una referencia de volumen como la ``imagen`` de 0.8.0 (o ``null`` = pendiente).
    Con errores devuelve lo leído hasta ese punto y los deja anotados en el lector: quien llama
    comprueba ``len(lector.errores)``. Con ``n_discos`` una entrada de un disco que no existe
    (índice ≥ nº de discos, lote editado a mano) es un error de rango en su campo ``disco``."""
    # Importación perezosa: ``esquema_config`` importa este módulo (ciclo si fuera al cargarse).
    from proxlaunch.nucleo.archivos.esquema_config import _leer_ref_volumen

    if not isinstance(valor, list):
        lector.error(ruta, MotivoCampo.TIPO)
        return ()
    if len(valor) > _MAX_DISCO_IMAGEN:
        lector.error(ruta, MotivoCampo.DEMASIADOS, maximo=str(_MAX_DISCO_IMAGEN), n=str(len(valor)))
        return ()
    leidas: list[ImagenDisco] = []
    vistos: set[int] = set()
    for i, item in enumerate(valor):
        r = f"{ruta}[{i}]"
        obj = lector.objeto(item, r, CLAVES_IMAGEN)
        if obj is None:
            continue
        n0 = len(lector.errores)
        disco = lector.entero(obj, "disco", r, minimo=1, maximo=_MAX_DISCO_IMAGEN)
        crear_vacio = lector.booleano(obj, "crear_vacio", r, requerido=False, defecto=False)
        ref = None
        if obj.get("imagen") is not None:
            ref = _leer_ref_volumen(lector, obj["imagen"], _ruta(r, "imagen"), Contenido.IMPORT)
        if len(lector.errores) > n0 or disco is None or crear_vacio is None:
            continue
        if n_discos is not None and disco >= n_discos:
            lector.error(_ruta(r, "disco"), MotivoCampo.RANGO, minimo="1", maximo=str(n_discos - 1))
            continue
        if disco in vistos:
            lector.error(_ruta(r, "disco"), MotivoCampo.DUPLICADO)
            continue
        vistos.add(disco)
        leidas.append(ImagenDisco(indice=disco, imagen=ref, crear_vacio=crear_vacio))
    return tuple(leidas)


def leer_mac_conservada(lector: LectorEsquema, obj: dict[str, object], ruta: str) -> str | None:
    """``mac_conservada`` de una tarjeta (solo lotes): ausente o ``null`` = MAC nueva."""
    texto = lector.texto(
        obj, "mac_conservada", ruta, minimo=1, maximo=17, nulo=True, requerido=False, sin_token=True
    )
    if texto is not None and not mac_valida(texto):
        lector.error(_ruta(ruta, "mac_conservada"), MotivoCampo.TEXTO_NO_VALIDO)
        return None
    return texto


# --- Escritura ----------------------------------------------------------------------------------


def hardware_a_dict(hw: HardwareCluster) -> dict[str, object]:
    """``hardware_cluster`` con solo las claves que difieren del defecto (más ``mapeo``)."""
    datos: dict[str, object] = {}
    if hw.pci:
        pci: list[dict[str, object]] = []
        for a in hw.pci:
            x: dict[str, object] = {"mapeo": a.mapeo}
            if a.pcie:
                x["pcie"] = True
            if a.x_vga:
                x["x_vga"] = True
            if not a.rombar:
                x["rombar"] = False
            if a.driver_keep:
                x["driver_keep"] = True
            pci.append(x)
        datos["pci"] = pci
    if hw.usb:
        datos["usb"] = [
            {"mapeo": a.mapeo, "usb3": True} if a.usb3 else {"mapeo": a.mapeo} for a in hw.usb
        ]
    return datos


def hardware_para_escribir(
    hw: HardwareCluster, campo: str = "hardware_cluster"
) -> dict[str, object]:
    """``hardware_cluster`` listo para escribir (E-M08 si un id parece un token; no guardable si
    el lector lo rechazaría, p. ej. un id con caracteres no admitidos o más de 16 PCI)."""
    ids = [a.mapeo for a in hw.pci] + [a.mapeo for a in hw.usb]
    for mapeo in ids:
        exigir_sin_credencial(mapeo, f"{campo}.mapeo")
    datos = hardware_a_dict(hw)
    lector = LectorEsquema()
    leer_hardware(lector, datos, campo)
    if lector.errores:
        raise _no_guardable(campo)
    return datos


def imagenes_a_lista(otras: Sequence[ImagenDisco], campo: str) -> list[dict[str, object]]:
    """``imagenes`` listo para escribir. ``tamano_virtual_bytes`` es de sesión: nunca se escribe.

    La referencia pasa la lista blanca de nombres y volids (como la ``imagen`` de 0.8.0) o no se
    guarda; ``crear_vacio`` solo se escribe si es verdadero."""
    from proxlaunch.nucleo.archivos.esquema_config import _ref_a_dict  # ciclo: ver leer_imagenes

    lista: list[dict[str, object]] = []
    for i, o in enumerate(otras):
        c = f"{campo}[{i}]"
        item: dict[str, object] = {
            "disco": o.indice,
            "imagen": None if o.imagen is None else _ref_a_dict(o.imagen, Contenido.IMPORT, c),
        }
        if o.crear_vacio:
            item["crear_vacio"] = True
        lista.append(item)
    lector = LectorEsquema()
    leer_imagenes(lector, lista, campo)
    if lector.errores:
        raise _no_guardable(campo)
    return lista


def mac_para_escribir(mac: str, campo: str) -> str:
    """MAC conservada lista para escribir (sin aspecto de token y con formato válido)."""
    exigir_sin_credencial(mac, campo)
    if not mac_valida(mac):
        raise _no_guardable(campo)
    return mac


def claves_red_fase_d(mac_conservada: str | None, campo: str) -> Mapping[str, object]:
    """Clave de la fase D de una tarjeta de red de un lote (vacía si no conserva la MAC)."""
    if mac_conservada is None:
        return {}
    return {"mac_conservada": mac_para_escribir(mac_conservada, campo)}


__all__ = [
    "CLAVES_HARDWARE",
    "CLAVES_IMAGEN",
    "CLAVES_PCI",
    "CLAVES_USB",
    "claves_red_fase_d",
    "hardware_a_dict",
    "hardware_para_escribir",
    "hardware_requiere_v6",
    "imagenes_a_lista",
    "imagenes_requieren_v6",
    "leer_hardware",
    "leer_imagenes",
    "leer_mac_conservada",
    "mac_para_escribir",
    "requiere_version_6",
]
