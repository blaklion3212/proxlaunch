"""Compatibilidad de un perfil con la versión de Proxmox y el servidor (RF-P07).

No duplica reglas: reutiliza ``validar_vm`` y la tabla de capacidades.
"""

from __future__ import annotations

from collections.abc import Callable

from proxlaunch.nucleo.capacidades import TABLA, Capacidades, Funcion
from proxlaunch.nucleo.modelos.cpu import TIPO_CPU_HOST
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil
from proxlaunch.nucleo.validacion import Problema, Severidad, validar_vm


def funciones_requeridas(config: ConfigPerfil) -> frozenset[Funcion]:
    """Funciones dependientes de versión que usa el perfil (CA-P07.2).

    Con la mínima 8.4 ninguna función de los perfiles depende ya de la versión (DT-D3); se
    conserva el punto de extensión para futuras funciones.
    """
    return frozenset()


def evaluar_compatibilidad(
    cfg: ConfiguracionVM,
    config: ConfigPerfil,
    inv: Inventario,
    caps: Capacidades,
    *,
    requeridas: Callable[[ConfigPerfil], frozenset[Funcion]] = funciones_requeridas,
) -> list[Problema]:
    """Problemas de ``validar_vm`` + funciones que la versión efectiva no tiene.

    Códigos propios: ``V-P07.version`` (error; params ``funcion``, ``version``) y
    ``V-P07.cpu_host`` (aviso: ``host`` impide migrar entre CPUs distintas, CA-P07.4).
    """
    problemas = validar_vm(cfg, inv, caps)
    for funcion in sorted(requeridas(config)):
        if not caps.tiene(funcion):
            mayor, menor = TABLA[funcion]
            problemas.append(
                Problema(
                    "perfil",
                    "V-P07.version",
                    Severidad.ERROR,
                    {"funcion": str(funcion), "version": f"{mayor}.{menor}"},
                )
            )
    if config.tipo_cpu == TIPO_CPU_HOST:
        problemas.append(Problema("tipo_cpu", "V-P07.cpu_host", Severidad.AVISO, {}))
    return problemas
