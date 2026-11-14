"""Modelos de datos del núcleo (dataclasses, sin Qt)."""

from proxlaunch.nucleo.modelos.conexion import (
    CredencialContrasena,
    CredencialToken,
    MetodoAuth,
    PerfilConexion,
    Ticket,
)
from proxlaunch.nucleo.modelos.inventario import (
    Bridge,
    Inventario,
    Nodo,
    Storage,
    Topologia,
    Version,
    VMRemota,
)
from proxlaunch.nucleo.modelos.tarea import Desenlace, EstadoTarea, Etapa, ResultadoCreacion
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

__all__ = [
    "Ballooning",
    "Bridge",
    "Bus",
    "ConfiguracionVM",
    "ControladorScsi",
    "CredencialContrasena",
    "CredencialToken",
    "Desenlace",
    "Disco",
    "EstadoTarea",
    "Etapa",
    "Firmware",
    "FormatoDisco",
    "InterfazRed",
    "Inventario",
    "MetodoAuth",
    "ModeloRed",
    "Nodo",
    "OrigenSO",
    "PerfilConexion",
    "ResultadoCreacion",
    "Storage",
    "Ticket",
    "Topologia",
    "VMRemota",
    "Version",
]
