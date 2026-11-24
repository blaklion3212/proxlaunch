"""Apoyo de las pruebas de D1 (migración desde libvirt, 0.9.0). Solo constructores y dobles; sin
aserciones.

Los XML sintéticos viven en ``tests/datos/fase_d/libvirt/``; los grandes (límites de tamaño,
profundidad y elementos) se generan en cada prueba para no inflar el repositorio.
"""

from __future__ import annotations

import dataclasses
import struct
from pathlib import Path
from typing import Any

from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    ArquitecturaNodo,
    FuenteArquitectura,
)
from proxlaunch.nucleo.libvirt.correspondencias import PropuestaLibvirt, proponer
from proxlaunch.nucleo.libvirt.lectura_xml import leer_xml
from proxlaunch.nucleo.libvirt.modelos import DominioLibvirt, interpretar_dominio
from proxlaunch.nucleo.modelos.inventario import Bridge, Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed

from .apoyo_mvp4 import inv_origen

DATOS = Path(__file__).resolve().parent.parent / "datos" / "fase_d" / "libvirt"

CABECERA_XML = "<?xml version='1.0'?>\n"


def ruta_xml(nombre: str) -> Path:
    return DATOS / nombre


def bytes_xml(nombre: str) -> bytes:
    return ruta_xml(nombre).read_bytes()


def dominio_de(nombre_o_bytes: str | bytes) -> DominioLibvirt:
    """Interpreta un XML de ``tests/datos/fase_d/libvirt`` (por nombre) o unos bytes."""
    datos = bytes_xml(nombre_o_bytes) if isinstance(nombre_o_bytes, str) else nombre_o_bytes
    return interpretar_dominio(leer_xml(datos))


def dominio_desde_texto(texto: str) -> DominioLibvirt:
    return dominio_de(texto.encode("utf-8"))


def xml_minimo(
    devices: str = "", *, tipo: str = "kvm", extra: str = "", arch: str = "x86_64"
) -> str:
    """Un ``<domain>`` mínimo y válido con los ``devices`` dados."""
    return (
        f"<domain type='{tipo}'><name>m</name><memory unit='MiB'>1024</memory><vcpu>1</vcpu>"
        f"{extra}<os><type arch='{arch}'>hvm</type></os><devices>{devices}</devices></domain>"
    )


def disco_xml(
    dev: str = "vda", bus: str = "virtio", archivo: str = "/i/a.qcow2", extra: str = ""
) -> str:
    return (
        f"<disk type='file' device='disk'><driver name='qemu' type='qcow2'/>"
        f"<source file='{archivo}'/><target dev='{dev}' bus='{bus}'/>{extra}</disk>"
    )


def inventario_d(
    arquitecturas: dict[str, Arquitectura] | None = None,
    bridges: tuple[str, ...] = ("vmbr0", "vmbr1"),
    nodos: tuple[str, ...] = ("pve1", "pve2"),
) -> Inventario:
    """Inventario del MVP 4 con las arquitecturas dadas por nodo y los bridges indicados."""
    inv = inv_origen(nodos=nodos)
    inv.bridges = {n: tuple(Bridge(b, "bridge", False) for b in bridges) for n in nodos}
    inv.arquitecturas = {
        n: ArquitecturaNodo(a, FuenteArquitectura.MANUAL) for n, a in (arquitecturas or {}).items()
    }
    return inv


def cfg_formulario(**cambios: Any) -> ConfiguracionVM:
    """Configuración del formulario antes de rellenar (la «base» de ``proponer``)."""
    base: dict[str, Any] = {
        "vmid": 100,
        "nombre": "",
        "nodo": "pve1",
        "discos": [Disco("local-lvm", 32)],
        "redes": [InterfazRed("vmbr0")],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def proponer_de(
    origen: str | bytes | DominioLibvirt,
    *,
    inv: Inventario | None = None,
    nodo: str | None = "pve1",
    conservar_mac: bool = False,
    base: ConfiguracionVM | None = None,
) -> PropuestaLibvirt:
    dominio = origen if isinstance(origen, DominioLibvirt) else dominio_de(origen)
    return proponer(
        dominio,
        base if base is not None else cfg_formulario(),
        inv if inv is not None else inventario_d(),
        nodo,
        conservar_mac=conservar_mac,
    )


def fila(propuesta: PropuestaLibvirt, campo: str):
    """La fila de la vista previa con esa clave (``None`` si no existe)."""
    return next((f for f in propuesta.filas if f.campo == campo), None)


def codigos(propuesta: PropuestaLibvirt) -> set[str]:
    return {f.problema.codigo for f in propuesta.filas if f.problema is not None}


def con_arquitectura(inv: Inventario, nodo: str, arq: Arquitectura) -> Inventario:
    return dataclasses.replace(
        inv,
        arquitecturas={
            **inv.arquitecturas,
            nodo: ArquitecturaNodo(arq, FuenteArquitectura.MANUAL),
        },
    )


# --- Cabeceras qcow2 sintéticas (RF-D1.8) ------------------------------------------------------


def cabecera_qcow2(
    *,
    version: int = 3,
    backing_offset: int = 0,
    nb_snapshots: int = 0,
    incompatibles: int = 0,
    tamano_virtual: int = 10 * 1024**3,
    longitud: int = 104,
) -> bytes:
    """Cabecera qcow2 (big endian): magia, versión, backing (8..15), tamaño (24..31),
    ``nb_snapshots`` (60..63) y características incompatibles (72..79, solo v3)."""
    c = bytearray(max(longitud, 0))
    campos = [
        (0, b"QFI\xfb"),
        (4, struct.pack(">I", version)),
        (8, struct.pack(">Q", backing_offset)),
        (16, struct.pack(">I", 0)),
        (20, struct.pack(">I", 16)),  # cluster_bits
        (24, struct.pack(">Q", tamano_virtual)),
        (32, struct.pack(">I", 0)),
        (36, struct.pack(">I", 0)),
        (60, struct.pack(">I", nb_snapshots)),
        (72, struct.pack(">Q", incompatibles)),
    ]
    for pos, valor in campos:
        fin = pos + len(valor)
        if fin <= len(c):
            c[pos:fin] = valor
    return bytes(c)
