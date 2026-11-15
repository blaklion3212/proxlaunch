"""Archivo local a subir: apertura segura, inspección de cabecera y sha256 por bloques.

INV-O5: el archivo se abre solo para lectura, se comprueba con ``fstat`` sobre el descriptor
(evita TOCTOU) que es regular, y solo se leen la cabecera (≤ ``TAM_CABECERA``), para ISO 5
bytes en 0x8001 (enmienda C1) y el contenido al subir o calcular el hash. Nunca se ejecuta
nada sobre el archivo ni se sigue lo que su contenido indique (ver ``interpretar_cabecera``).
"""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import stat
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.origen.constantes import CHUNK_SUBIDA

_log = logging.getLogger("proxlaunch.transferencias.archivo_local")

TAM_CABECERA = 1024
DESPLAZAMIENTO_ISO9660 = 0x8001
_FIRMA_ISO = b"CD001"
_FIRMA_QCOW2 = b"QFI\xfb"
_FIRMA_VMDK = b"KDMV"
_DESCRIPTOR_VMDK = b"# Disk DescriptorFile"
_TAM_SECTOR = 512
_WINERROR_BLOQUEADO = (32, 33)

# Motivos de rechazo (E-O15, ``IMAGEN_NO_ADMITIDA``); ``vacio`` es V-O10 (tamaño > 0).
MOTIVO_BACKING = "backing"
MOTIVO_CIFRADO = "cifrado"
MOTIVO_MULTIARCHIVO = "multiarchivo"
MOTIVO_OVA = "ova"
MOTIVO_VERSION = "version"
MOTIVO_TRUNCADO = "truncado"
MOTIVO_VACIO = "vacio"

# Avisos (códigos; los textos los pone la interfaz).
AVISO_NO_ISO9660 = "no_iso9660"
AVISO_RAW_SIN_VERIFICAR = "raw_sin_verificar"


class TipoArchivoLocal(StrEnum):
    ISO = "iso"
    QCOW2 = "qcow2"
    VMDK = "vmdk"
    RAW = "raw"
    OVA = "ova"
    DESCONOCIDO = "desconocido"


@dataclass(frozen=True)
class HuellaArchivo:
    """Identidad del archivo al abrirlo; si cambia, la subida no es de fiar (E-O09)."""

    tamano: int
    mtime_ns: int
    identidad: tuple[int, int]  # (dispositivo, inodo) o índice de archivo en Windows


@dataclass(frozen=True)
class InspeccionArchivo:
    nombre_local: str
    tamano_bytes: int
    tipo: TipoArchivoLocal
    tamano_virtual_bytes: int | None
    extension_propuesta: str
    motivo_rechazo: str | None
    avisos: tuple[str, ...]


_EXTENSION_POR_TIPO: dict[TipoArchivoLocal, str] = {
    TipoArchivoLocal.ISO: ".iso",
    TipoArchivoLocal.QCOW2: ".qcow2",
    TipoArchivoLocal.VMDK: ".vmdk",
    TipoArchivoLocal.RAW: ".raw",
    TipoArchivoLocal.OVA: ".ova",
    TipoArchivoLocal.DESCONOCIDO: "",
}


def _u32_be(datos: bytes, desde: int) -> int:
    return int(struct.unpack_from(">I", datos, desde)[0])


def _u64_be(datos: bytes, desde: int) -> int:
    return int(struct.unpack_from(">Q", datos, desde)[0])


def _interpretar_qcow2(
    cabecera: bytes,
) -> tuple[TipoArchivoLocal, int | None, str | None, tuple[str, ...]]:
    tipo = TipoArchivoLocal.QCOW2
    if len(cabecera) < 36:
        return tipo, None, MOTIVO_TRUNCADO, ()
    version = _u32_be(cabecera, 4)
    if version not in (2, 3):
        return tipo, None, MOTIVO_VERSION, ()
    if _u64_be(cabecera, 8) != 0:  # backing_file_offset
        return tipo, None, MOTIVO_BACKING, ()
    if _u32_be(cabecera, 32) != 0:  # crypt_method
        return tipo, None, MOTIVO_CIFRADO, ()
    if version == 3 and len(cabecera) >= 80 and _u64_be(cabecera, 72) & 0x4:
        # incompatible_features, bit 2: el servidor rechaza los discos con archivo de datos externo.
        return tipo, None, MOTIVO_MULTIARCHIVO, ()
    virtual = _u64_be(cabecera, 24)
    if virtual == 0:
        return tipo, None, MOTIVO_TRUNCADO, ()
    return tipo, virtual, None, ()


def _interpretar_vmdk(
    cabecera: bytes,
) -> tuple[TipoArchivoLocal, int | None, str | None, tuple[str, ...]]:
    tipo = TipoArchivoLocal.VMDK
    if len(cabecera) < 20:
        return tipo, None, MOTIVO_TRUNCADO, ()
    capacidad = int(struct.unpack_from("<Q", cabecera, 12)[0])  # sectores de 512 bytes
    if capacidad == 0:
        return tipo, None, MOTIVO_TRUNCADO, ()
    return tipo, capacidad * _TAM_SECTOR, None, ()


def interpretar_cabecera(
    cabecera: bytes, firma_iso: bytes | None, tamano: int, contenido: Contenido
) -> tuple[TipoArchivoLocal, int | None, str | None, tuple[str, ...]]:
    """Clasifica un archivo por su cabecera. Pura y tolerante: nunca lanza con bytes arbitrarios.

    Args:
        cabecera: los primeros bytes del archivo (≤ ``TAM_CABECERA``).
        firma_iso: los 5 bytes en 0x8001 (solo se leen para ISO), o ``None``.
        tamano: tamaño del archivo en bytes.
        contenido: destino (``ISO`` o ``IMPORT``).

    Returns:
        ``(tipo, tamano_virtual_bytes, motivo_rechazo, avisos)``. Para ``ISO`` se acepta
        cualquier contenido (V-O10) y, sin la firma ``CD001``, se avisa.
    """
    cabecera = bytes(cabecera[:TAM_CABECERA])
    if contenido == Contenido.ISO:
        if firma_iso == _FIRMA_ISO:
            return TipoArchivoLocal.ISO, None, None, ()
        return TipoArchivoLocal.DESCONOCIDO, None, None, (AVISO_NO_ISO9660,)
    # Discos a importar (qcow2 / vmdk / raw).
    if cabecera.startswith(_FIRMA_QCOW2):
        return _interpretar_qcow2(cabecera)
    if cabecera.startswith(_FIRMA_VMDK):
        return _interpretar_vmdk(cabecera)
    if cabecera.startswith(_DESCRIPTOR_VMDK):
        # Descriptor de texto: el disco son varios archivos que aquí no viajan (E-O15).
        return TipoArchivoLocal.VMDK, None, MOTIVO_MULTIARCHIVO, ()
    if cabecera[257:262] == b"ustar":
        # tar: un .ova (paquete OVF) queda fuera de alcance (CA-O16.3).
        return TipoArchivoLocal.OVA, None, MOTIVO_OVA, ()
    if tamano <= 0:
        return TipoArchivoLocal.DESCONOCIDO, None, MOTIVO_VACIO, ()
    return TipoArchivoLocal.RAW, tamano, None, (AVISO_RAW_SIN_VERIFICAR,)


# --- Apertura segura -------------------------------------------------------------------


def _no_accesible(ruta: Path, exc: OSError) -> ErrorProxLaunch:
    if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
        motivo = "no_existe"
    elif getattr(exc, "winerror", None) in _WINERROR_BLOQUEADO:
        motivo = "bloqueado"
    elif isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM):
        motivo = "sin_permiso"
    else:
        motivo = "otro"
    # Solo el nombre del archivo, nunca la ruta completa (INV-O6).
    return ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_ACCESIBLE, {"archivo": ruta.name, "motivo": motivo}
    )


def _no_regular(ruta: Path) -> ErrorProxLaunch:
    return ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_PERMITIDO, {"motivo": "no_regular", "archivo": ruta.name}
    )


def _abrir_descriptor(ruta: Path) -> tuple[int, os.stat_result]:
    """``os.open`` de solo lectura sin bloquear ni adoptar terminal, y ``fstat`` regular."""
    ruta = Path(ruta)
    banderas = os.O_RDONLY
    banderas |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    banderas |= getattr(os, "O_NOCTTY", 0)
    try:
        fd = os.open(ruta, banderas)
    except OSError as exc:
        if os.name == "nt" and ruta.is_dir():
            raise _no_regular(ruta) from None
        raise _no_accesible(ruta, exc) from None
    try:
        info = os.fstat(fd)
    except OSError as exc:
        os.close(fd)
        raise _no_accesible(ruta, exc) from None
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise _no_regular(ruta)
    return fd, info


def _huella_de(info: os.stat_result) -> HuellaArchivo:
    return HuellaArchivo(
        tamano=info.st_size, mtime_ns=info.st_mtime_ns, identidad=(info.st_dev, info.st_ino)
    )


class ArchivoAbierto:
    """Archivo regular abierto para lectura (gestor de contexto).

    ``huella`` es la identidad medida al abrir; ``sigue_igual`` la compara con una nueva
    medida sobre el mismo descriptor.
    """

    def __init__(self, fd: int, info: os.stat_result, nombre: str) -> None:
        self._fd = fd
        self._nombre = nombre
        self._huella = _huella_de(info)
        self._flujo: BinaryIO | None = os.fdopen(fd, "rb")  # toma posesión del descriptor

    @property
    def flujo(self) -> BinaryIO:
        if self._flujo is None:
            raise ValueError("archivo cerrado")
        return self._flujo

    @property
    def huella(self) -> HuellaArchivo:
        return self._huella

    @property
    def nombre(self) -> str:
        """Nombre del archivo (sin carpeta)."""
        return self._nombre

    def sigue_igual(self) -> bool:
        """``True`` si tamaño, ``mtime_ns`` e identidad no cambiaron desde que se abrió."""
        if self._flujo is None:
            return False
        try:
            return _huella_de(os.fstat(self._flujo.fileno())) == self._huella
        except OSError:
            return False

    def cerrar(self) -> None:
        flujo, self._flujo = self._flujo, None
        if flujo is not None:
            flujo.close()

    def __enter__(self) -> ArchivoAbierto:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        valor: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        self.cerrar()


def abrir_para_subir(ruta: Path) -> ArchivoAbierto:
    """Abre el archivo para subirlo (E/S).

    Raises:
        ErrorProxLaunch: ``ARCHIVO_NO_ACCESIBLE`` (no existe, sin permiso, bloqueado) o
            ``ARCHIVO_NO_PERMITIDO`` (no regular o vacío).
    """
    ruta = Path(ruta)
    fd, info = _abrir_descriptor(ruta)
    if info.st_size <= 0:
        os.close(fd)
        raise ErrorProxLaunch(
            CodigoError.ARCHIVO_NO_PERMITIDO, {"motivo": MOTIVO_VACIO, "archivo": ruta.name}
        )
    return ArchivoAbierto(fd, info, ruta.name)


def _extension_propuesta(ruta: Path, tipo: TipoArchivoLocal, contenido: Contenido) -> str:
    """Extensión según el CONTENIDO (DT-O12); si no se reconoce, la del nombre."""
    if tipo == TipoArchivoLocal.DESCONOCIDO and contenido == Contenido.ISO:
        # Un .img es válido como ISO en Proxmox; cualquier otra cosa se propone como .iso.
        return ".img" if ruta.suffix.lower() == ".img" else ".iso"
    return _EXTENSION_POR_TIPO[tipo] or ruta.suffix.lower()


def inspeccionar(ruta: Path, contenido: Contenido) -> InspeccionArchivo:
    """Abre, comprueba y lee la cabecera del archivo local (E/S mínima, solo lectura).

    Un archivo vacío o rechazado por contenido no lanza: devuelve ``motivo_rechazo``.
    """
    ruta = Path(ruta)
    fd, info = _abrir_descriptor(ruta)
    with ArchivoAbierto(fd, info, ruta.name) as archivo:
        tamano = info.st_size
        flujo = archivo.flujo
        try:
            cabecera = flujo.read(TAM_CABECERA)
            firma: bytes | None = None
            if contenido == Contenido.ISO and tamano >= DESPLAZAMIENTO_ISO9660 + len(_FIRMA_ISO):
                flujo.seek(DESPLAZAMIENTO_ISO9660)
                firma = flujo.read(len(_FIRMA_ISO))
        except OSError as exc:
            raise _no_accesible(ruta, exc) from None
    nombre = ruta.name
    sufijo = ruta.suffix.lower()
    if tamano <= 0:
        return InspeccionArchivo(
            nombre, 0, TipoArchivoLocal.DESCONOCIDO, None, sufijo, MOTIVO_VACIO, ()
        )
    if contenido != Contenido.ISO and sufijo in (".ova", ".ovf"):
        return InspeccionArchivo(nombre, tamano, TipoArchivoLocal.OVA, None, sufijo, MOTIVO_OVA, ())
    tipo, virtual, motivo, avisos = interpretar_cabecera(cabecera, firma, tamano, contenido)
    return InspeccionArchivo(
        nombre_local=nombre,
        tamano_bytes=tamano,
        tipo=tipo,
        tamano_virtual_bytes=virtual,
        extension_propuesta=_extension_propuesta(ruta, tipo, contenido),
        motivo_rechazo=motivo,
        avisos=avisos,
    )


def comprobar_cabecera_abierto(archivo: ArchivoAbierto, contenido: Contenido) -> None:
    """Vuelve a interpretar la cabecera sobre el descriptor que se va a enviar (SEG-M4-10).

    Cierra la ventana entre la inspección inicial y la subida: si el archivo cambió y ya no es
    admisible, lanza ``IMAGEN_NO_ADMITIDA`` (o ``ARCHIVO_NO_PERMITIDO`` si quedó vacío). Deja
    el flujo en 0.

    Raises:
        ErrorProxLaunch: ``IMAGEN_NO_ADMITIDA``, ``ARCHIVO_NO_PERMITIDO`` o
            ``ARCHIVO_NO_ACCESIBLE`` (fallo de lectura).
    """
    flujo = archivo.flujo
    tamano = archivo.huella.tamano
    try:
        flujo.seek(0)
        cabecera = flujo.read(TAM_CABECERA)
        firma: bytes | None = None
        if contenido == Contenido.ISO and tamano >= DESPLAZAMIENTO_ISO9660 + len(_FIRMA_ISO):
            flujo.seek(DESPLAZAMIENTO_ISO9660)
            firma = flujo.read(len(_FIRMA_ISO))
        flujo.seek(0)
    except OSError as exc:
        raise _no_accesible(Path(archivo.nombre), exc) from None
    sufijo = Path(archivo.nombre).suffix.lower()
    if contenido != Contenido.ISO and sufijo in (".ova", ".ovf"):
        motivo: str | None = MOTIVO_OVA
    else:
        motivo = interpretar_cabecera(cabecera, firma, tamano, contenido)[2]
    if motivo == MOTIVO_VACIO:
        raise ErrorProxLaunch(
            CodigoError.ARCHIVO_NO_PERMITIDO, {"motivo": MOTIVO_VACIO, "archivo": archivo.nombre}
        )
    if motivo is not None:
        raise ErrorProxLaunch(
            CodigoError.IMAGEN_NO_ADMITIDA, {"motivo": motivo, "archivo": archivo.nombre}
        )


def calcular_sha256(
    archivo: ArchivoAbierto,
    *,
    al_progresar: Callable[[int, int], None] | None = None,
    cancelado: threading.Event | None = None,
    tam_bloque: int = CHUNK_SUBIDA,
) -> str:
    """sha256 hexadecimal del archivo por bloques (E/S), con progreso y cancelación.

    Lee exactamente ``huella.tamano`` bytes desde el principio y deja el flujo en 0. Si el
    archivo es más corto que al abrirlo lanza ``ARCHIVO_CAMBIO``; si se cancela entre bloques,
    ``TRANSFERENCIA_CANCELADA`` (CA-O12.3: no se envía nada).
    """
    flujo = archivo.flujo
    total = archivo.huella.tamano
    flujo.seek(0)
    resumen = hashlib.sha256()
    hechos = 0
    while hechos < total:
        if cancelado is not None and cancelado.is_set():
            raise ErrorProxLaunch(CodigoError.TRANSFERENCIA_CANCELADA, {"quedo_archivo": "no"})
        try:
            bloque = flujo.read(min(tam_bloque, total - hechos))
        except OSError as exc:
            # Lectura fallida del disco: no es un corte de red (QA-M4-10 / SEG-M4-06).
            raise _no_accesible(Path(archivo.nombre), exc) from None
        if not bloque:
            raise ErrorProxLaunch(CodigoError.ARCHIVO_CAMBIO, {}, "el archivo se acortó")
        resumen.update(bloque)
        hechos += len(bloque)
        if al_progresar is not None:
            al_progresar(hechos, total)
    flujo.seek(0)
    return resumen.hexdigest()
