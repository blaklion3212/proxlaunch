"""Funciones puras de B2: nombre del archivo, parámetros de la creación y configuración (DT-B10).

La creación y la importación del disco las hace ``ServicioCreacion.crear`` con una
``ConfiguracionVM`` de origen ``IMPORTAR_DISCO``; lo propio de las imágenes cloud (unidad
cloud-init, consola serie, ``boot``) va en ``parametros_extra``, que se fusiona con los que ya
construye ``construir_parametros`` (ninguna clave se repite).
"""

from __future__ import annotations

import dataclasses
import re

from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, RefVolumen, TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    Disco,
    OrigenSO,
)
from proxlaunch.nucleo.origen.nombres import sanear_nombre_archivo
from proxlaunch.nucleo.plantilla_imagen.modelos import (
    EXTENSIONES_IMPORT,
    FijasPlantilla,
    SolicitudPlantillaImagen,
)

_GIB = 1024**3
TAMANO_FINAL_POR_DEFECTO_GIB = 10
_MAX_LONG_ETIQUETA_DNS = 63
_RE_NO_ALFANUM = re.compile(r"[^a-z0-9]+")


def _extension(nombre: str) -> str:
    punto = nombre.rfind(".")
    return nombre[punto:].lower() if punto > 0 else ""


def nombre_archivo_import(nombre: str, es_qcow2: bool | None) -> tuple[str | None, str | None]:
    """``(nombre final, motivo de rechazo)`` del archivo en el almacenamiento ``import``.

    Reglas (RF-B2.3): ``.qcow2``, ``.raw`` y ``.vmdk`` se conservan; ``.img`` con cabecera qcow2
    pasa a ``.qcow2``; ``.img`` crudo (``es_qcow2=False``) pasa a ``.raw``; ``.img`` de una URL
    (``es_qcow2=None``, no se puede leer) se pide como ``.qcow2`` y se avisa. Cualquier otra
    extensión se rechaza (motivo ``extension``). El nombre se sanea como en transferencias:
    solo el último componente y ``[A-Za-z0-9._-]``. El contenido del archivo no cambia nunca.
    """
    base = str(nombre).replace("\\", "/").rsplit("/", 1)[-1]
    extension = _extension(base)
    if extension == ".img":
        nueva = ".raw" if es_qcow2 is False else ".qcow2"
    elif extension in EXTENSIONES_IMPORT:
        nueva = extension
    else:
        return None, "extension"
    final = sanear_nombre_archivo(base[: -len(extension)] + nueva, Contenido.IMPORT)
    return final, None


def nombre_sugerido(nombre_archivo: str) -> str:
    """Nombre de MV derivado del archivo (CA-B2.6.2): ``plantilla-<archivo sin extensión>``,
    en minúsculas, solo ``a-z0-9`` y ``-``, de 63 caracteres como máximo (RFC 1123, V-B09)."""
    base = nombre_archivo.replace("\\", "/").rsplit("/", 1)[-1].lower()
    ext = _extension(base)
    raiz = base[: -len(ext)] if ext in (*EXTENSIONES_IMPORT, ".img") else base
    limpio = _RE_NO_ALFANUM.sub("-", raiz).strip("-")
    nombre = f"plantilla-{limpio}" if limpio else "plantilla-cloud"
    return nombre[:_MAX_LONG_ETIQUETA_DNS].rstrip("-")


def parametros_extra(fijas: FijasPlantilla, storage_destino: str) -> dict[str, str]:
    """Parámetros propios de las imágenes cloud para ``crear(parametros_extra=…)`` (RF-B2.7).

    En este orden y solo los de las casillas marcadas: ``ide2=<destino>:cloudinit``,
    ``serial0=socket`` y ``vga=serial0``; ``boot=order=scsi0`` va siempre. ``agent=1`` no va aquí:
    lo envía ``construir_parametros`` desde ``cfg.agente_qemu``. ``serial0`` es siempre ``socket``
    (nunca un dispositivo real, CA-B2.7.5).
    """
    extra: dict[str, str] = {}
    if fijas.unidad_cloudinit:
        extra["ide2"] = f"{storage_destino}:cloudinit"
    if fijas.consola_serie:
        extra["serial0"] = "socket"
        extra["vga"] = "serial0"
    extra["boot"] = "order=scsi0"
    return extra


def tamano_final_gib(sol: SolicitudPlantillaImagen) -> int:
    """Tamaño final del disco pedido en GiB (RF-B2.6)."""
    detalle = sol.cfg.detalle_origen
    if isinstance(detalle, DetalleImportacion) and detalle.ampliar_a_gib is not None:
        return detalle.ampliar_a_gib
    if sol.cfg.discos:
        return sol.cfg.discos[0].tamano_gib
    return TAMANO_FINAL_POR_DEFECTO_GIB


def tamano_virtual_gib(tamano_virtual_bytes: int | None) -> int | None:
    """Tamaño virtual de la imagen en GiB, redondeado hacia arriba (nunca se subestima)."""
    if tamano_virtual_bytes is None:
        return None
    return -(-tamano_virtual_bytes // _GIB)


def necesita_ampliar(sol: SolicitudPlantillaImagen) -> bool:
    """``False`` solo si se SABE que el tamaño final no supera el de la imagen (CA-B2.6.3).

    Con el tamaño virtual desconocido (URL) devuelve ``True``: lo decide ``crear`` al leer el
    tamaño real de la máquina (``ampliacion_importacion``, que solo crece).
    """
    virtual = tamano_virtual_gib(sol.tamano_virtual_bytes)
    return virtual is None or tamano_final_gib(sol) > virtual


def volid_de_imagen(sol: SolicitudPlantillaImagen) -> str:
    """Volid de la imagen en el almacenamiento ``import``: la ya importada o la que se va a
    subir/descargar (``<almacenamiento>:import/<archivo>``)."""
    if sol.volid_existente:
        return sol.volid_existente
    return f"{sol.storage_import}:{Contenido.IMPORT.value}/{sol.nombre_archivo}"


def cfg_de_creacion(sol: SolicitudPlantillaImagen, volid_imagen: str) -> ConfiguracionVM:
    """Configuración para ``ServicioCreacion.crear`` (origen ``IMPORTAR_DISCO``).

    Parte de ``sol.cfg`` (sin modificarla) y fija lo propio de B2: Linux (``ostype=l26``),
    controlador ``virtio-scsi-single``, disco ``scsi0`` en el destino, agente según la casilla,
    sin encender, sin cloud-init ni espera de IP (los valores de cloud-init se escriben después,
    paso 4) y ``ampliar_a_gib`` solo si el tamaño final supera el de la imagen.
    """
    base = sol.cfg
    final = tamano_final_gib(sol)
    disco_base = base.discos[0] if base.discos else Disco(sol.storage_destino, final)
    disco = dataclasses.replace(
        disco_base, storage=sol.storage_destino, tamano_gib=final, bus=Bus.SCSI
    )
    nombre = volid_imagen.partition("/")[2]
    detalle = DetalleImportacion(
        imagen=RefVolumen(nombre=nombre, volid=volid_imagen),
        ampliar_a_gib=final if necesita_ampliar(sol) else None,
        tamano_virtual_bytes=sol.tamano_virtual_bytes,
    )
    return dataclasses.replace(
        base,
        nodo=sol.nodo,
        con_disco=True,
        discos=[disco],
        controlador_scsi=ControladorScsi.VIRTIO_SINGLE,
        origen=OrigenSO.IMPORTAR_DISCO,
        tipo_so=TipoSO.LINUX,
        tpm=False,
        agente_qemu=sol.fijas.agente,
        detalle_origen=detalle,
        encender=False,
        cloudinit=None,
        esperar_ip=False,
        info_cloudinit=None,
    )
