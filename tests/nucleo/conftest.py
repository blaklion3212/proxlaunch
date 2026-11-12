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


# --- Fixtures de la capa API y los servicios (F3) --------------------------------------


@pytest.fixture
def rsps():
    """Simula HTTP con ``responses``; no exige que se usen todas las rutas registradas."""
    import responses

    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        yield r


@pytest.fixture
def reloj():
    """Reloj simulado: ninguna prueba duerme de verdad."""
    from proxlaunch.nucleo.reloj import RelojSimulado

    return RelojSimulado()


@pytest.fixture
def respuesta():
    """Carga una respuesta simulada: ``respuesta("9.2", "version.json")`` -> cuerpo completo."""
    from .apoyo_api import cargar

    return cargar


@pytest.fixture
def transporte_falso():
    from .apoyo_api import TransporteFalso

    return TransporteFalso()


@pytest.fixture
def ejecutar_creacion(inv, hacer_cfg, reloj):
    """Ejecuta ``ServicioCreacion.crear`` sobre un transporte falso.

    Devuelve ``(resultado, etapas, servicio_reloj)``; las etapas son las notificadas en orden.
    """
    import threading

    from .apoyo_api import crear_sesion

    def _ejecutar(transporte, *, cfg=None, cancelado=None, auth=None, **opciones):
        from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

        sesion = crear_sesion(transporte, auth=auth, reloj=reloj)
        etapas = []
        servicio = ServicioCreacion(sesion, reloj, **opciones)
        resultado = servicio.crear(
            cfg or hacer_cfg(), inv, etapas.append, cancelado or threading.Event()
        )
        return resultado, etapas

    return _ejecutar


@pytest.fixture
def registros():
    """Registros emitidos por ``proxlaunch.*`` (sin depender de la propagación al logger raíz)."""
    import logging

    class _Lista(logging.Handler):
        def __init__(self):
            super().__init__(logging.DEBUG)
            self.registros = []

        def emit(self, record):
            self.registros.append(record)

    logger = logging.getLogger("proxlaunch")
    manejador = _Lista()
    nivel = logger.level
    logger.addHandler(manejador)
    logger.setLevel(logging.DEBUG)
    yield manejador.registros
    logger.removeHandler(manejador)
    logger.setLevel(nivel)
