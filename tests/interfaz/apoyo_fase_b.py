"""Apoyo de las pruebas de interfaz de la fase B (0.7.0). Sin aserciones.

Solo construye datos con el núcleo público (información de plantilla, disponibilidad, entradas del
libro con IP) y ayudas para leer lo que la interfaz muestra. Nunca hay red real ni diálogos modales.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QWidget

from proxlaunch.nucleo.agente.modelos import EstadoIp, ResultadoIp
from proxlaunch.nucleo.cloudinit.disponibilidad import OpcionB, disponibilidad_fase_b
from proxlaunch.nucleo.cloudinit.modelos import (
    CicustomHeredado,
    InfoCloudInitPlantilla,
)
from proxlaunch.nucleo.lote.modelos import ElementoPlan, EntradaLibro, EstadoMV
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion

from .apoyo_fase_a import caps_de
from .apoyo_lote import cfg_simple

CENTINELA = "S3cr3t-Prueba!"
CLAVE_ED25519 = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SzG0UpIxpKXqkAeGkBd9Wq0ESD3XsT3b ana@portatil"
)
CLAVE_RSA = (
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQChG5Jz/qcHJN8zQaNRAJNaz/fPk7a2uT"
    "845awasWtuWvxMoKuCqwfGIycbPZvczkF0QqHYp1CrMjaKIc1Ivz3iqG9iVUwwlunsJiia"
    "q1WnJ37Ze5Ogb+mkE4pVATSLVun4XTm6nlZVE4S3qlFknjGO5aXQFU4/D1BVVt3oYhMFz5"
    "ATos1fhv3YkRpKDXDsdtz4WdNENwDL8hZSfbKvkeiozlRUOfxDpE0JNFZUs85dC+8/1PnA"
    "8lMli19jdmgBIqZZe3DIfWmf/SMteAmtbCNCEvXMJ0lsGfA/nrPeoccKNmWocUyxiCbb+H"
    "MgicyR+2Jb3djYRWT86VOkhWfWPHV1 bea@oficina"
)
CLAVE_PRIVADA = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


def info_plantilla(**cambios: Any) -> InfoCloudInitPlantilla:
    """Plantilla con unidad cloud-init, una tarjeta y sin valores heredados."""
    base: dict[str, Any] = {"unidad": True, "clave_unidad": "ide2", "tarjetas": (0,)}
    base.update(cambios)
    return InfoCloudInitPlantilla(**base)


def disponibilidad(
    info: InfoCloudInitPlantilla | None = None,
    *,
    version: tuple[int, int] = (9, 2),
    permisos: PermisosEfectivos | None = None,
    snippets: bool = True,
) -> dict[OpcionB, EstadoOpcion]:
    """Estado de las opciones de la fase B con la función pura del núcleo.

    ``permisos=None`` = permisos desconocidos (todo habilitado).
    """
    return disponibilidad_fase_b(
        permisos, caps_de(version), info if info is not None else info_plantilla(), snippets
    )


def heredado(**valores: str) -> InfoCloudInitPlantilla:
    """Plantilla con los valores heredados dados (``ciuser``, ``ipconfig0``…)."""
    return info_plantilla(heredados=valores)


def con_cicustom(**tipos: str) -> InfoCloudInitPlantilla:
    return info_plantilla(cicustom=CicustomHeredado(tipos, True))


def textos_visibles(raiz: QWidget) -> str:
    """Texto de las etiquetas visibles bajo ``raiz``."""
    return "\n".join(
        lbl.text() for lbl in raiz.findChildren(QLabel) if lbl.isVisibleTo(raiz) and lbl.text()
    )


def entrada_ip(
    i: int,
    estado: EstadoMV = EstadoMV.OK,
    *,
    esperar: bool = True,
    ip: ResultadoIp | None = None,
    nombre: str | None = None,
    plazo_s: int = 120,
) -> EntradaLibro:
    """Entrada del libro de una máquina que (opcionalmente) pidió esperar su IP."""
    nombre = nombre or f"web-{i + 1:02d}"
    vmid = 101 + i
    cfg = cfg_simple(vmid, nombre, "pve1", encender=True, esperar_ip=esperar, plazo_ip_s=plazo_s)
    return EntradaLibro(
        ElementoPlan(i, nombre, vmid, "pve1", cfg), estado, post_intentado=True, ip=ip
    )


def con_ip(principal: str, estado: EstadoIp = EstadoIp.OBTENIDA) -> ResultadoIp:
    return ResultadoIp(estado, principal=principal)
