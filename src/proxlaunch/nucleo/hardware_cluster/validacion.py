"""Validaciones del hardware del clúster (D3): V-D50..V-D64. Puras: no leen nada del servidor.

Los ``params`` con texto del servidor o del usuario se acotan y se limpian (sin control ni
caracteres invisibles) antes de salir. Los textos los pone la interfaz a partir de código y params.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.hardware_cluster.errores import tipo_cpu_efectivo
from proxlaunch.nucleo.hardware_cluster.modelos import (
    MAX_PCI,
    MAX_USB,
    RE_ID_MAPEO,
    InfoHardwareCluster,
    Mapeo,
    TipoMapeo,
)
from proxlaunch.nucleo.modelos.catalogo import DetallePlantilla, PermisosEfectivos
from proxlaunch.nucleo.modelos.cpu import RE_CPU_PERSONALIZADA
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.origen.permisos import PRIVILEGIO_MAPEO_USAR, estado_mapeo, ruta_mapeo
from proxlaunch.nucleo.validacion import Problema, Severidad

_MAX_TEXTO = 256
# Control, separadores de línea/párrafo y caracteres invisibles o de formato (RNF-D2).
_RE_NO_IMPRIMIBLE = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏ -‮⁠-⁯﻿<>&]")

CAMPO_HW = "hardware_cluster"


def _texto(valor: object, maximo: int = _MAX_TEXTO) -> str:
    """Texto acotado y sin caracteres de control ni invisibles (para ``params``)."""
    return _RE_NO_IMPRIMIBLE.sub(" ", str(valor)).strip()[:maximo]


def _ids(lista: Iterable[str]) -> str:
    return ", ".join(_texto(i, 64) for i in lista)


def _version(caps: Capacidades) -> str:
    return f"{caps.version[0]}.{caps.version[1]}"


# --- Locales -------------------------------------------------------------------------------


def validar_hardware_local(
    cfg: ConfiguracionVM,
    caps: Capacidades,
    arq: Arquitectura,
    *,
    info: InfoHardwareCluster | None = None,
) -> list[Problema]:
    """V-D54, V-D55, V-D55b, V-D57, V-D59, V-D60, V-D64 y V-D09 (``pcie`` en ARM) de una MV.

    ``info`` (opcional) afina V-D57: un mapeo PCI leído con ``live-migration-capable`` no la
    provoca; sin lectura, o con USB, se avisa. Sin hardware asignado devuelve ``[]``.
    """
    hw = cfg.hardware_cluster
    if hw is None or hw.vacio:
        return []
    problemas: list[Problema] = []

    def err(campo: str, codigo: str, **params: str) -> None:
        problemas.append(Problema(campo, codigo, Severidad.ERROR, params))

    def aviso(campo: str, codigo: str, **params: str) -> None:
        problemas.append(Problema(campo, codigo, Severidad.AVISO, params))

    if len(hw.pci) > MAX_PCI:
        err(f"{CAMPO_HW}.pci", "V-D59", tipo="pci", maximo=str(MAX_PCI), cantidad=str(len(hw.pci)))
    if len(hw.usb) > MAX_USB:
        err(f"{CAMPO_HW}.usb", "V-D59", tipo="usb", maximo=str(MAX_USB), cantidad=str(len(hw.usb)))

    vistos: set[str] = set()
    repetidos: set[str] = set()
    avisado_q35 = avisado_vga = False
    for i, a in enumerate(hw.pci):
        campo = f"{CAMPO_HW}.pci[{i}]"
        if RE_ID_MAPEO.fullmatch(a.mapeo) is None:
            # Un id así no puede existir en el servidor (se descartan al leer): es inexistente.
            err(f"{campo}.mapeo", "V-D51", mapeo=_texto(a.mapeo, 64), motivo="formato", tipo="pci")
        elif a.mapeo in vistos and a.mapeo not in repetidos:
            repetidos.add(a.mapeo)
            err(f"{campo}.mapeo", "V-D64", mapeo=a.mapeo)
        vistos.add(a.mapeo)
        if a.pcie and arq == Arquitectura.AARCH64:
            err(
                f"{campo}.pcie",
                "V-D09",
                opcion="pcie",
                motivo="pcie",
                alternativa="sin_pcie",  # quitar «PCIe» de la asignación (ARM no tiene q35)
                arquitectura=arq.value,
                mapeo=_texto(a.mapeo, 64),
            )
        elif a.pcie and not avisado_q35:
            avisado_q35 = True
            aviso(f"{campo}.pcie", "V-D54", maquina="q35")
        if a.x_vga and not a.pcie:
            err(f"{campo}.x_vga", "V-D55", mapeo=_texto(a.mapeo, 64))
        elif a.x_vga and not avisado_vga:
            avisado_vga = True
            aviso(f"{campo}.x_vga", "V-D55b", vga="none")
        if a.driver_keep and not caps.tiene(Funcion.MAPEO_DRIVER_KEEP):
            err(f"{campo}.driver_keep", "V-D60", version=_version(caps), mapeo=_texto(a.mapeo, 64))
    for i, u in enumerate(hw.usb):
        if RE_ID_MAPEO.fullmatch(u.mapeo) is None:
            err(
                f"{CAMPO_HW}.usb[{i}].mapeo",
                "V-D51",
                mapeo=_texto(u.mapeo, 64),
                motivo="formato",
                tipo="usb",
            )

    # V-D57: USB nunca migra; un PCI solo si se leyó y el mapeo lo declara.
    conocidos: dict[str, Mapeo] = {}
    if info is not None and info.mapeos is not None:
        conocidos = {m.id: m for m in info.mapeos if m.tipo == TipoMapeo.PCI}
    sin_migracion = [
        a.mapeo for a in hw.pci if (m := conocidos.get(a.mapeo)) is None or not m.migrable_en_vivo
    ] + [u.mapeo for u in hw.usb]
    if sin_migracion:
        aviso(CAMPO_HW, "V-D57", mapeos=_ids(dict.fromkeys(sin_migracion)))
    return problemas


# --- Contra el servidor ----------------------------------------------------------------------


def _usos(
    cfgs_por_nodo: Mapping[str, Sequence[ConfiguracionVM]],
) -> dict[tuple[TipoMapeo, str], dict[str, int]]:
    """``{(tipo, id): {nodo: MVs que lo usan}}`` (un mapeo repetido en una MV cuenta una vez)."""
    usos: dict[tuple[TipoMapeo, str], dict[str, int]] = {}
    for nodo, cfgs in cfgs_por_nodo.items():
        for cfg in cfgs:
            hw = cfg.hardware_cluster
            if hw is None:
                continue
            claves = {(TipoMapeo.PCI, a.mapeo) for a in hw.pci} | {
                (TipoMapeo.USB, u.mapeo) for u in hw.usb
            }
            for clave in claves:
                if RE_ID_MAPEO.fullmatch(clave[1]):
                    por_nodo = usos.setdefault(clave, {})
                    por_nodo[nodo] = por_nodo.get(nodo, 0) + 1
    return usos


def _tipos_fallidos(info: InfoHardwareCluster) -> frozenset[str]:
    if info.error_mapeos is None:
        return frozenset()
    return frozenset(info.error_mapeos.params.get("tipo", "pci,usb").split(","))


def _validar_mapeos(
    usos: Mapping[tuple[TipoMapeo, str], Mapping[str, int]],
    info: InfoHardwareCluster | None,
    permisos: PermisosEfectivos | None,
) -> list[Problema]:
    problemas: list[Problema] = []
    if not usos:
        return problemas
    if info is None or (info.mapeos is None and info.error_mapeos is None):
        return problemas  # sin lectura no se afirma nada (la disponibilidad ya avisa)
    if info.error_mapeos is not None or not info.mapeos:
        motivo = "no_leido" if info.error_mapeos is not None else "sin_mapeos"
        params = {"motivo": motivo}
        if info.error_mapeos is not None:
            params["tipo"] = _texto(info.error_mapeos.params.get("tipo", ""), 32)
            params["error"] = str(info.error_mapeos.codigo)
        problemas.append(Problema(CAMPO_HW, "V-D50", Severidad.AVISO, params))
    fallidos = _tipos_fallidos(info)
    por_clave = {(m.tipo, m.id): m for m in info.mapeos or ()}
    comprobados = {(c.tipo, c.mapeo, c.nodo): c for c in info.comprobaciones}
    sin_comprobar = set(info.errores_comprobacion)
    for (tipo, id_mapeo), por_nodo in sorted(
        usos.items(), key=lambda kv: (kv[0][0].value, kv[0][1])
    ):
        # V-D63: falta Mapping.Use en ese mapeo (CA-D5.1.3); None = desconocido, no se afirma.
        if estado_mapeo(permisos, tipo, id_mapeo) is False:
            problemas.append(
                Problema(
                    CAMPO_HW,
                    "V-D63",
                    Severidad.ERROR,
                    {
                        "privilegio": PRIVILEGIO_MAPEO_USAR,
                        "ruta": ruta_mapeo(tipo, id_mapeo),
                        "mapeo": id_mapeo,
                        "tipo": tipo.value,
                    },
                )
            )
        mapeo = por_clave.get((tipo, id_mapeo))
        if mapeo is None:
            if tipo.value not in fallidos:  # si esa lista no se pudo leer, V-D50 ya lo dice
                problemas.append(
                    Problema(
                        CAMPO_HW, "V-D51", Severidad.ERROR, {"mapeo": id_mapeo, "tipo": tipo.value}
                    )
                )
            continue
        faltan = sorted(n for n in por_nodo if n not in mapeo.nodos())
        if faltan:
            problemas.append(
                Problema(
                    CAMPO_HW,
                    "V-D52",
                    Severidad.ERROR,
                    {"mapeo": id_mapeo, "tipo": tipo.value, "nodos": _ids(faltan)},
                )
            )
        for nodo in sorted(por_nodo):
            if nodo in faltan:
                continue
            comp = comprobados.get((tipo, id_mapeo, nodo))
            if comp is not None and comp.errores:
                problemas.append(
                    Problema(
                        CAMPO_HW,
                        "V-D53",
                        Severidad.ERROR,
                        {
                            "mapeo": id_mapeo,
                            "nodo": _texto(nodo, 64),
                            "mensaje": _texto("; ".join(comp.errores)),
                        },
                    )
                )
            elif (tipo.value, id_mapeo, nodo) in sin_comprobar:
                problemas.append(
                    Problema(
                        CAMPO_HW,
                        "V-D53.sin_comprobar",
                        Severidad.AVISO,
                        {"mapeo": id_mapeo, "nodo": _texto(nodo, 64)},
                    )
                )
            # V-D56: cada dispositivo lo usa una sola MV encendida (mdev: sin tope; USB: uno).
            n = por_nodo[nodo]
            libres = 1 if tipo == TipoMapeo.USB else mapeo.dispositivos_en(nodo)
            if not (tipo == TipoMapeo.PCI and mapeo.mdev) and 0 < libres < n:
                problemas.append(
                    Problema(
                        CAMPO_HW,
                        "V-D56",
                        Severidad.AVISO,
                        {
                            "mapeo": id_mapeo,
                            "nodo": _texto(nodo, 64),
                            "k": str(libres),
                            "n": str(n),
                        },
                    )
                )
    return problemas


def _validar_cpus(
    cfgs_por_nodo: Mapping[str, Sequence[ConfiguracionVM]], info: InfoHardwareCluster | None
) -> list[Problema]:
    """V-D61 (la CPU no existe en un nodo leído) y V-D62 (no se pudo leer la lista)."""
    problemas: list[Problema] = []
    por_cpu: dict[str, set[str]] = {}
    for nodo, cfgs in cfgs_por_nodo.items():
        for cfg in cfgs:
            cpu = tipo_cpu_efectivo(cfg)
            if cpu is not None and RE_CPU_PERSONALIZADA.fullmatch(cpu):
                por_cpu.setdefault(cpu, set()).add(nodo)
    for cpu, nodos in sorted(por_cpu.items()):
        ausentes: list[str] = []
        sin_lista: list[str] = []
        for nodo in sorted(nodos):
            if info is not None and nodo in info.cpus:
                if not any(m.personalizado and m.nombre == cpu for m in info.cpus[nodo]):
                    ausentes.append(nodo)
            else:
                sin_lista.append(nodo)
        if ausentes:
            problemas.append(
                Problema(
                    "tipo_cpu", "V-D61", Severidad.ERROR, {"cpu": cpu, "nodos": _ids(ausentes)}
                )
            )
        if sin_lista:
            problemas.append(
                Problema(
                    "tipo_cpu", "V-D62", Severidad.AVISO, {"cpu": cpu, "nodos": _ids(sin_lista)}
                )
            )
    return problemas


def validar_hardware_servidor(
    cfgs_por_nodo: Mapping[str, Sequence[ConfiguracionVM]],
    info: InfoHardwareCluster | None,
    permisos: PermisosEfectivos | None,
) -> list[Problema]:
    """V-D50, V-D51, V-D52, V-D53, V-D56, V-D61, V-D62 y V-D63 del lote, agrupadas por nodo.

    ``cfgs_por_nodo``: las MVs del lote por nodo destino. Cada problema sale una vez por mapeo (o
    por mapeo y nodo), no por MV. V-D53 solo con ``check-node`` respondido; si la llamada falló
    queda un aviso ``V-D53.sin_comprobar`` (P-D11). Sin lecturas no se afirma nada de mapeos.
    """
    return _validar_mapeos(_usos(cfgs_por_nodo), info, permisos) + _validar_cpus(
        cfgs_por_nodo, info
    )


# --- Plantillas ------------------------------------------------------------------------------


def validar_plantilla_hardware(plantilla: DetallePlantilla, nombre: str) -> list[Problema]:
    """V-D58 (dispositivos sin mapear: solo root puede clonar) y V-D58b (mapeos: aviso).

    Sin hardware asignado en la plantilla devuelve ``[]`` (CA-D3.5.3).
    """
    problemas: list[Problema] = []
    campo = "detalle_origen.plantilla"
    if plantilla.pasarela_directa:
        problemas.append(
            Problema(campo, "V-D58", Severidad.ERROR, {"plantilla": _texto(nombre, 64)})
        )
    if plantilla.mapeos:
        problemas.append(
            Problema(
                campo,
                "V-D58b",
                Severidad.AVISO,
                {"plantilla": _texto(nombre, 64), "lista": _ids(plantilla.mapeos)},
            )
        )
    return problemas
