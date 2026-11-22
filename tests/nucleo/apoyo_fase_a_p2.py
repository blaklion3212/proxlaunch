"""Apoyo de las pruebas de aceptación de la fase A (0.6.0): Deshacer, archivos, CSV y perfiles.

Solo dobles y constructores; sin aserciones. Los privilegios se construyen con ``permisos``.
"""

from __future__ import annotations

import copy
import random
import unicodedata
from typing import Any

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    DefinicionLote,
    Destino,
    EstadoMV,
    FilaLote,
    PatronNombres,
)
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed, ModeloRed
from proxlaunch.nucleo.opciones.modelos import OpcionesParciales

from .apoyo_lote import Banco, definicion


def permisos(*privilegios: str, ruta: str = "/vms") -> PermisosEfectivos:
    """Permisos efectivos sintéticos: los privilegios dados, con propagación, en ``ruta``."""
    return PermisosEfectivos({ruta: dict.fromkeys(privilegios, 1)})


PERMISOS_COMPLETOS = permisos("VM.PowerMgmt", "VM.Config.Options", "VM.Allocate")
SIN_POWERMGMT = permisos("VM.Config.Options", "VM.Allocate")
SIN_OPCIONES = permisos("VM.PowerMgmt", "VM.Allocate")
SIN_NINGUNO = permisos("VM.Allocate")


def lote_creado(banco: Banco, cantidad: int = 3, **kw: Any):
    """Crea un lote real con el motor (VMIDs desde 100) y devuelve ``(plan, libro)``."""
    plan = banco.planificar(definicion(cantidad, vmid_inicial=100, **kw))
    libro = banco.ejecutar(plan)
    assert all(e.estado == EstadoMV.OK for e in libro.instantanea())
    return plan, libro


def encender_en_servidor(banco: Banco, *vmids: int) -> None:
    for v in vmids:
        banco.cluster.vms[v]["status"] = "running"


def proteger_en_servidor(banco: Banco, *vmids: int) -> None:
    for v in vmids:
        banco.cluster.vms[v]["config"]["protection"] = "1"


def error_api(detalle: str, codigo: CodigoError = CodigoError.DESCONOCIDO) -> ErrorProxLaunch:
    return ErrorProxLaunch(codigo, {}, detalle)


def orden_de_llamadas(banco: Banco, vmid: int) -> list[str]:
    """Escrituras recibidas por una MV, en orden: ``stop``, ``put-config`` y ``delete``."""
    sal: list[str] = []
    for ll in banco.cluster.llamadas:
        if f"/{vmid}" not in ll.ruta:
            continue
        if ll.metodo == "POST" and ll.ruta.endswith("/status/stop"):
            sal.append("stop")
        elif ll.metodo == "PUT" and ll.ruta.endswith("/config"):
            sal.append("put-config")
        elif ll.metodo == "DELETE":
            sal.append("delete")
    return sal


# --- Generación pseudoaleatoria con semilla fija (``hypothesis`` no está instalado) -------------

SEMILLA = 20260621
_ALFABETO_NOTAS = "abcdefghijklmnopqrstuvwxyzÁÉÍÓÚñüß0123456789 .,;:-_/()[]#*%@!\n\t¿?¡áéíóú€"
_ALFABETO_ETIQUETA = "abcdefghijklmnopqrstuvwxyz0123456789"


def etiqueta_aleatoria(rng: random.Random) -> str:
    n = rng.randint(1, 12)
    cuerpo = "".join(rng.choice(_ALFABETO_ETIQUETA) for _ in range(n))
    return "e" + cuerpo  # empieza por letra: cumple ``_RE_ETIQUETA_PVE``


def notas_aleatorias(rng: random.Random, maximo: int = 400) -> str:
    n = rng.choice([0, 1, 5, 40, maximo])
    texto = "".join(rng.choice(_ALFABETO_NOTAS) for _ in range(n))
    return unicodedata.normalize("NFC", texto)


def cfg_aleatoria(rng: random.Random) -> ConfiguracionVM:
    """Configuración de lote válida con opciones de la fase A aleatorias."""
    redes: list[InterfazRed] = []
    for _ in range(rng.randint(1, 3)):
        virtio = rng.random() < 0.7
        mtu = rng.choice([None, None, 1, 576, 1500, 9000, 65520]) if virtio else None
        limite = rng.choice([None, None, 0.5, 12.5, 100.0, 1000.0])
        redes.append(
            InterfazRed(
                "vmbr0",
                ModeloRed.VIRTIO if virtio else ModeloRed.E1000,
                rng.choice([None, 10, 4094]),
                mtu,
                limite,
            )
        )
    return ConfiguracionVM(
        vmid=0,
        nombre="",
        nodo="",
        cores=rng.randint(1, 8),
        memoria_mib=rng.choice([512, 2048, 8192]),
        discos=[Disco("datos", rng.randint(1, 100))],
        redes=redes,
        encender=rng.random() < 0.5,
        arranque_auto=rng.random() < 0.5,
        arranque_orden=rng.choice([None, 0, 1, 99, 2**31 - 1]),
        arranque_espera=rng.choice([None, 0, 30, 2**31 - 1]),
        notas_origen=rng.random() < 0.5,
        notas_usuario=rng.random() < 0.5,
        notas=notas_aleatorias(rng),
        etiquetas_usuario=tuple(
            dict.fromkeys(etiqueta_aleatoria(rng) for _ in range(rng.randint(0, 4)))
        ),
        pool=rng.choice([None, None, "produccion", "lab-1", "p"]),
        proteger=rng.random() < 0.5,
    )


def parciales_aleatorias(rng: random.Random) -> OpcionesParciales | None:
    if rng.random() < 0.3:
        return None
    return OpcionesParciales(
        encender=rng.choice([None, True, False]),
        arranque_auto=rng.choice([None, True, False]),
        notas=rng.choice([None, "", "hola\nmundo", notas_aleatorias(rng, 200)]),
        etiquetas_usuario=rng.choice([None, (), ("a",), ("web", "prod")]),
        pool=rng.choice([None, "", "produccion"]),
        proteger=rng.choice([None, True, False]),
    )


def lote_aleatorio(rng: random.Random, filas: bool) -> DefinicionLote:
    if not filas:
        return DefinicionLote(
            cfg_aleatoria(rng), rng.randint(1, 5), PatronNombres("srv", "-", 1, 2), Destino()
        )
    n = rng.randint(1, 4)
    fs = tuple(
        FilaLote(f"vm-{i}", cfg_aleatoria(rng), None, None, None, parciales_aleatorias(rng))
        for i in range(n)
    )
    return DefinicionLote(copy.deepcopy(fs[0].cfg), n, PatronNombres(""), Destino(), filas=fs)
