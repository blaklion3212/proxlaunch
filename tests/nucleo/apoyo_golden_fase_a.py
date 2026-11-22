"""Escenarios de las instantáneas («golden») de la petición de 0.5.1 (CA-A0.2.1, CA-A0.2.2).

Este módulo SOLO usa campos y funciones que existen igual en 0.5.1 y en 0.6: así se ejecuta
contra el código de la etiqueta ``v0.5.1`` para generar ``tests/datos/fase_a/golden_v051.json``
y contra 0.6 para compararlo. Sin aserciones.

Regenerar (desde la raíz del repositorio, sin tocar el árbol de trabajo)::

    git archive v0.5.1 src | tar -x -C <carpeta_temporal>
    PYTHONPATH=<carpeta_temporal>/src:. .venv/bin/python -I -c \
        "from tests.nucleo.apoyo_golden_fase_a import generar; generar('<salida.json>')"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.modelos.origen import AjustesClon, ModoClon, TipoSO
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    Bus,
    Disco,
    Firmware,
    FormatoDisco,
    InterfazRed,
    ModeloRed,
)
from proxlaunch.nucleo.origen.clon import (
    construir_ajustes_clon,
    construir_peticion_clon,
    detalle_de_config,
)

from .apoyo_lote import storage
from .apoyo_mvp4 import (
    VOLID_IMAGEN,
    VOLID_ISO,
    VOLID_VIRTIO,
    ClusterM4,
    cfg_base,
    cfg_clon,
    cfg_import,
    cfg_iso,
    inv_origen,
)

RUTA_GOLDEN = Path(__file__).resolve().parents[1] / "datos" / "fase_a" / "golden_v051.json"
ETIQUETAS_LOTE = ("proxlaunch", "lote-ab12cd34")


def _post(cfg: Any, inv: Any, version: tuple[int, int] | None) -> dict[str, Any]:
    return {
        "version": None if version is None else list(version),
        "parametros": dict(construir_parametros(cfg, inv, version).items()),
    }


def _inv_base() -> Any:
    return inv_origen()


def _inv_mixto() -> Any:
    """Storages de varios tipos para que salgan ``format=`` y rutas distintas."""
    return inv_origen(
        extra_storages={
            "pve1": (
                storage("dirimg", "dir", 100, contenido="images"),
                storage("zfs1", "zfspool", 100, contenido="images"),
            )
        }
    )


def escenarios() -> dict[str, Any]:
    """``{nombre: {...petición...}}``. Las claves de los diccionarios conservan su orden."""
    res: dict[str, Any] = {}

    # --- Disco vacío (MVP 1-3) -------------------------------------------------------------
    inv = _inv_base()
    res["vacio_basico"] = _post(cfg_base(), inv, (9, 2))
    res["vacio_basico_sin_version"] = _post(cfg_base(), inv, None)
    res["vacio_etiquetado_9_2"] = _post(cfg_base(etiquetas=ETIQUETAS_LOTE), inv, (9, 2))
    res["vacio_etiquetado_8_0"] = _post(cfg_base(etiquetas=ETIQUETAS_LOTE), inv, (8, 0))
    inv_m = _inv_mixto()
    res["vacio_avanzado"] = _post(
        cfg_base(
            firmware=Firmware.OVMF,
            sockets=2,
            cores=4,
            memoria_mib=8192,
            ballooning=Ballooning(True, 2048),
            discos=[
                Disco("dirimg", 40, Bus.SCSI, FormatoDisco.QCOW2),
                Disco("zfs1", 100, Bus.VIRTIO, FormatoDisco.RAW, discard=False, ssd=False),
                Disco("local-lvm", 8, Bus.SATA, iothread=False),
            ],
            redes=[
                InterfazRed("vmbr0", ModeloRed.VIRTIO, 25),
                InterfazRed("vmbr0", ModeloRed.E1000),
            ],
            etiquetas=ETIQUETAS_LOTE,
        ),
        inv_m,
        (9, 2),
    )
    res["vacio_sin_disco_sin_red"] = _post(cfg_base(con_disco=False, redes=[]), inv, (9, 2))

    # --- ISO ---------------------------------------------------------------------------------
    res["iso_linux"] = _post(cfg_iso(etiquetas=ETIQUETAS_LOTE), inv, (9, 2))
    res["iso_windows_con_drivers"] = _post(
        cfg_iso(
            VOLID_ISO,
            TipoSO.WINDOWS_11,
            drivers=VOLID_VIRTIO,
            firmware=Firmware.OVMF,
            tpm=True,
            agente_qemu=True,
        ),
        inv,
        (9, 2),
    )
    res["iso_otro"] = _post(cfg_iso(tipo_so=TipoSO.OTRO), inv, (8, 4))

    # --- Importar disco ------------------------------------------------------------------------
    res["importar_basico"] = _post(cfg_import(), inv, (9, 2))
    res["importar_ampliado_etiquetado"] = _post(
        cfg_import(
            cfg={"etiquetas": ETIQUETAS_LOTE, "firmware": Firmware.OVMF, "agente_qemu": True},
            ampliar_a_gib=64,
        ),
        inv,
        (9, 2),
    )
    assert VOLID_IMAGEN  # uso explícito: el volid por defecto de cfg_import

    # --- Clonar ----------------------------------------------------------------------------------
    cl = ClusterM4(("pve1", "pve2"))
    cl.agregar_plantilla(9000, "base", "pve1", tags="plantilla", cores=2, memory=2048)
    detalle = detalle_de_config(cl.plantillas[9000]["config"])

    def clon(**kw: Any) -> dict[str, Any]:
        cfg = cfg_clon("base", 9000, "pve1", **kw)
        peticion = construir_peticion_clon(cfg, inv)
        ajustes = construir_ajustes_clon(cfg, detalle, cfg.etiquetas)
        return {
            "nodo_plantilla": peticion.nodo_plantilla,
            "vmid_plantilla": peticion.vmid_plantilla,
            "parametros": dict(peticion.parametros.items()),
            "ajustes_config": dict(ajustes.config.items()),
            "ajustes_disco": None if ajustes.disco is None else list(ajustes.disco),
        }

    res["clon_enlazado"] = clon(efectivo=ModoClon.ENLAZADO)
    res["clon_enlazado_etiquetado"] = clon(efectivo=ModoClon.ENLAZADO, etiquetas=ETIQUETAS_LOTE)
    res["clon_completo_storage_otro_nodo"] = clon(
        modo=ModoClon.COMPLETO,
        efectivo=ModoClon.COMPLETO,
        storage_destino="local-lvm",
        nodo="pve2",
        etiquetas=ETIQUETAS_LOTE,
    )
    res["clon_con_ajustes"] = clon(
        efectivo=ModoClon.ENLAZADO,
        ajustes=AjustesClon(cores=4, memoria_mib=4096, disco_gib=64),
        etiquetas=ETIQUETAS_LOTE,
    )
    return res


def generar(salida: str | Path = RUTA_GOLDEN) -> None:
    """Escribe los escenarios como JSON (claves en orden de inserción)."""
    import proxlaunch

    datos = {"version_codigo": proxlaunch.__version__, "escenarios": escenarios()}
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(
        json.dumps(datos, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )
