"""Reglas de arquitectura (D2): V-D04 a V-D06 y V-D09. Funciones puras, sin Qt ni E/S.

``validar_arquitectura`` devuelve ``validacion.Problema`` (lo usa ``validar_vm``);
``avisos_arquitectura`` y ``validar_mezcla`` trabajan sobre el lote y devuelven
``lote.modelos.Problema``. Los ``params`` llevan solo nombres de nodo (ya validados) y códigos
cortos, nunca texto del servidor; los textos los pone la interfaz.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping

from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    ArquitecturaNodo,
    FuenteArquitectura,
    arquitectura_de,
    arquitectura_efectiva,
)
from proxlaunch.nucleo.arquitectura.perfil import BUSES_SOLO_X86
from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.lote.modelos import Problema as ProblemaLote
from proxlaunch.nucleo.lote.modelos import Severidad as SeveridadLote
from proxlaunch.nucleo.modelos.cpu import es_cpu_solo_x86
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Firmware, ModeloRed, OrigenSO
from proxlaunch.nucleo.validacion import Problema, Severidad

MOTIVO_DESCONOCIDO = "no_responde"  # nodo sin entrada (p. ej. fuera de línea): no se leyó


def _v_d09(campo: str, opcion: str, motivo: str, alternativa: str, nodo: str) -> Problema:
    """V-D09: opción que no existe en ARM64. ``motivo`` y ``alternativa`` son códigos cortos."""
    return Problema(
        campo,
        "V-D09",
        Severidad.ERROR,
        {"opcion": opcion, "motivo": motivo, "alternativa": alternativa, "nodo": nodo},
    )


def validar_arquitectura(cfg: ConfiguracionVM, inv: Inventario) -> list[Problema]:
    """V-D09 (red de seguridad) y V-D05 para un nodo ARM; vacío en x86 o desconocida.

    Si el planificador ya adaptó la configuración (V-D08) no queda nada que rechazar; esto
    atrapa lo que llegó a un nodo ARM sin adaptar. Un clon hereda de la plantilla: solo
    recibe V-D05. ``hostpci … pcie=1`` en ARM lo valida ``hardware_cluster.validacion``.
    """
    if arquitectura_efectiva(inv, cfg.nodo) != Arquitectura.AARCH64:
        return []
    p: list[Problema] = [
        Problema("nodo", "V-D05", Severidad.AVISO, {"nodo": cfg.nodo}),
    ]
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA:
        return p
    nodo = cfg.nodo
    if cfg.firmware != Firmware.OVMF:
        p.append(_v_d09("firmware", cfg.firmware.value, "firmware_uefi", "ovmf", nodo))
    for i, d in enumerate(cfg.discos if cfg.con_disco else []):
        if d.bus in BUSES_SOLO_X86:
            p.append(_v_d09(f"discos[{i}].bus", d.bus.value, "sin_controlador", "scsi", nodo))
    if es_cpu_solo_x86(cfg.tipo_cpu):
        p.append(_v_d09("tipo_cpu", cfg.tipo_cpu, "cpu_x86", "host", nodo))
    for i, r in enumerate(cfg.redes):
        if r.modelo != ModeloRed.VIRTIO:
            p.append(_v_d09(f"redes[{i}].modelo", r.modelo.value, "solo_virtio", "virtio", nodo))
    return p


def _info(inv: Inventario, nodo: str) -> ArquitecturaNodo:
    return inv.arquitecturas.get(nodo, ArquitecturaNodo())


def avisos_arquitectura(
    inv: Inventario, nodos: Collection[str], caps: Capacidades
) -> list[ProblemaLote]:
    """V-D04 (arquitectura no legible) y V-D05 (ARM64) una vez por nodo, en orden alfabético.

    V-D04 lleva ``motivo`` (``sin_permiso`` | ``no_responde`` | ``formato``); un nodo que no
    consta (fuera de línea) cuenta como ``no_responde``. V-D05 lleva ``variante``: ``9_2``
    con ``NODO_ARM64`` (servidor 9.2 o posterior) o ``previa``, y ``forzada=1`` si la
    arquitectura se fijó a mano.
    """
    avisos: list[ProblemaLote] = []
    for nodo in sorted(set(nodos)):
        arq = arquitectura_de(inv, nodo)
        if arq == Arquitectura.DESCONOCIDA:
            motivo = _info(inv, nodo).motivo or MOTIVO_DESCONOCIDO
            avisos.append(
                ProblemaLote("V-D04", SeveridadLote.AVISO, "nodo", {"nodo": nodo, "motivo": motivo})
            )
        elif arq == Arquitectura.AARCH64:
            params = {
                "nodo": nodo,
                "variante": "9_2" if caps.tiene(Funcion.NODO_ARM64) else "previa",
            }
            if _info(inv, nodo).fuente == FuenteArquitectura.MANUAL:
                params["forzada"] = "1"
            avisos.append(ProblemaLote("V-D05", SeveridadLote.AVISO, "nodo", params))
    return avisos


def validar_mezcla(nodos_por_indice: Mapping[int, str], inv: Inventario) -> list[ProblemaLote]:
    """V-D06: un lote no mezcla arquitecturas. Error en cada elemento de la minoría.

    La arquitectura de cada nodo es la efectiva (``DESCONOCIDA`` cuenta como x86, así que un
    nodo desconocido con uno ARM sí es mezcla). Gana la mayoritaria (por elementos); en
    empate, la del primer elemento. ``params`` lleva ``nodos_x86`` y ``nodos_arm`` (nombres
    separados por coma) y el ``nodo`` del elemento.
    """
    if not nodos_por_indice:
        return []
    por_indice = {i: arquitectura_efectiva(inv, n) for i, n in nodos_por_indice.items()}
    if len(set(por_indice.values())) < 2:
        return []
    cuenta = Counter(por_indice.values())
    primero = por_indice[min(por_indice)]
    mayor = max(cuenta.values())
    ganadoras = {a for a, c in cuenta.items() if c == mayor}
    ganadora = primero if primero in ganadoras else sorted(ganadoras)[0]
    nodos_x86 = ", ".join(
        sorted({n for i, n in nodos_por_indice.items() if por_indice[i] == Arquitectura.X86_64})
    )
    nodos_arm = ", ".join(
        sorted({n for i, n in nodos_por_indice.items() if por_indice[i] == Arquitectura.AARCH64})
    )
    return [
        ProblemaLote(
            "V-D06",
            SeveridadLote.ERROR,
            "nodo",
            {"nodos_x86": nodos_x86, "nodos_arm": nodos_arm, "nodo": nodos_por_indice[i]},
            indice=i,
        )
        for i in sorted(por_indice)
        if por_indice[i] != ganadora
    ]
