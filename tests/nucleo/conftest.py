"""Fixtures del núcleo: inventario de ejemplo basado en los mocks de los requisitos."""

import pytest

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos import (
    Bridge,
    ConfiguracionVM,
    Disco,
    InterfazRed,
    Inventario,
    Nodo,
    Storage,
    Topologia,
    Version,
)

GIB = 1024**3


def storage(id_, tipo, contenido, libre_gib, activo=True, compartido=False):
    """Atajo para crear un Storage con espacio libre en GiB."""
    return Storage(
        id=id_,
        tipo=tipo,
        contenido=frozenset(contenido.split(",")),
        compartido=compartido,
        activo=activo,
        total_bytes=int(libre_gib * 2 * GIB),
        libre_bytes=int(libre_gib * GIB),
    )


@pytest.fixture
def inv():
    """Inventario: pve1 (completo), pve2 (sin conexión), pve3 (solo storage sin images)."""
    pve1 = (
        storage("local", "dir", "iso,backup", 50),
        storage("local-lvm", "lvmthin", "images,rootdir", 150),
        storage("nfs1", "nfs", "images", 500, compartido=True),
        storage("dirimg", "dir", "images", 100),
        storage("zfs1", "zfspool", "images", 200),
        storage("cifs1", "cifs", "images", 100),
        storage("btrfs1", "btrfs", "images", 100),
        storage("lvm1", "lvm", "images", 40),
        storage("inactivo", "lvm", "images", 100, activo=False),
    )
    return Inventario(
        version=Version("9.2", 9, 2, 0),
        topologia=Topologia(
            es_cluster=True,
            nombre_cluster="lab",
            nodos=(
                Nodo("pve1", True, 8192, 8),
                Nodo("pve2", False, None, None),
                Nodo("pve3", True, 4096, 4),
            ),
        ),
        proximo_vmid=101,
        storages={
            "pve1": pve1,
            "pve2": (storage("local-lvm", "lvmthin", "images", 150),),
            "pve3": (storage("local", "dir", "iso,backup", 50),),
        },
        bridges={
            "pve1": (
                Bridge("vmbr0", "bridge", False),
                Bridge("vmbr1", "OVSBridge", True),
                Bridge("eno1", "eth", False),
                Bridge("vmbr,9", "bridge", False),
            ),
            "pve2": (Bridge("vmbr0", "bridge", False),),
            "pve3": (Bridge("vmbr0", "bridge", False),),
        },
        errores_por_nodo={},
    )


@pytest.fixture
def caps():
    return capacidades_para(Version("9.2", 9, 2, 0), None)


@pytest.fixture
def hacer_cfg():
    """Fábrica de configuraciones válidas sobre `inv`; los argumentos sobrescriben campos."""

    def _hacer(**cambios):
        base = {
            "vmid": 100,
            "nombre": "srv-web-01",
            "nodo": "pve1",
            "discos": [Disco("local-lvm", 32)],
            "redes": [InterfazRed("vmbr0")],
        }
        base.update(cambios)
        return ConfiguracionVM(**base)

    return _hacer


@pytest.fixture
def con_codigo():
    """Filtra una lista de Problema por código de regla (y opcionalmente por campo)."""

    def _filtrar(problemas, codigo, campo=None):
        return [p for p in problemas if p.codigo == codigo and (campo is None or p.campo == campo)]

    return _filtrar
