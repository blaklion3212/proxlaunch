"""Fixtures de integración con el laboratorio (solo 127.0.0.1:8006, nodo pve-lab).

Las pruebas llevan ``pytestmark = pytest.mark.integracion`` y se saltan sin
PROXLAUNCH_LAB=1 (ver tests/conftest.py). Todo lo que se crea se limpia al terminar.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from . import apoyo_lab as lab


@dataclass(frozen=True)
class UsuarioPlc:
    userid: str
    contrasena: str = field(repr=False)
    token_id: str  # usuario!nombre
    token_secreto: str = field(repr=False)


@pytest.fixture(scope="session", autouse=True)
def _guarda_laboratorio() -> Iterator[None]:
    """Aborta si el destino no es el laboratorio local y limpia MVs huérfanas al final."""
    if os.environ.get("PROXLAUNCH_LAB") != "1":
        yield
        return
    lab.comprobar_destino(lab.HOST, lab.PUERTO, lab.NODO)
    nombre = lab.ssh("hostname").strip()
    if nombre != lab.NODO:
        pytest.exit(f"el nodo del laboratorio es {nombre!r}, no {lab.NODO!r}: se aborta", 2)
    yield
    for vmid in lab.vmids_de_prueba():
        lab.destruir_vm(vmid)


@pytest.fixture(scope="session")
def plc() -> Iterator[UsuarioPlc]:
    """Rol ProxLaunchCreador + usuario plc@pve (en ``/``, propagate) + token privsep=0."""
    lab.borrar_usuario(lab.USUARIO_PLC)  # restos de una ejecución abortada
    lab.borrar_rol()
    lab.crear_rol()
    contrasena = lab.nuevo_secreto()
    try:
        lab.crear_usuario(lab.USUARIO_PLC, contrasena)
        completo = lab.crear_token(lab.USUARIO_PLC, "t1", privsep=0)
        token_id, secreto = completo.rsplit("=", 1)
        yield UsuarioPlc(lab.USUARIO_PLC, contrasena, token_id, secreto)
    finally:
        lab.borrar_usuario(lab.USUARIO_PLC)  # borra también sus tokens y ACL
        lab.borrar_rol()


@pytest.fixture
def entorno(tmp_path: Path) -> lab.Entorno:
    return lab.crear_entorno(tmp_path)


@pytest.fixture
def vms() -> Iterator[Callable[[int], int]]:
    """Registra VMIDs de prueba (9000-9099); se destruyen al terminar la prueba."""
    creados: list[int] = []

    def registrar(vmid: int) -> int:
        if not lab.VMID_MIN <= vmid <= lab.VMID_MAX:
            raise ValueError("VMID fuera del rango de pruebas")
        creados.append(vmid)
        return vmid

    yield registrar
    for vmid in creados:
        lab.destruir_vm(vmid)


@pytest.fixture
def sesion_plc(entorno: lab.Entorno, plc: UsuarioPlc) -> Iterator[object]:
    """Sesión por token de plc@pve (rol ProxLaunchCreador), cerrada al terminar."""
    from proxlaunch.nucleo.modelos.conexion import CredencialToken, MetodoAuth

    p = lab.perfil(MetodoAuth.TOKEN, plc.token_id)
    lab.confiar_en_laboratorio(entorno, p)
    sesion = entorno.servicio.conectar(p, CredencialToken(plc.token_id, plc.token_secreto))
    yield sesion
    entorno.servicio.cerrar_sesion(sesion)  # type: ignore[arg-type]
