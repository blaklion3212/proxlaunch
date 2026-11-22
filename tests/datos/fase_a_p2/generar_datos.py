"""Regenera los archivos de 0.5.1 de este directorio con el CÓDIGO de la versión 0.5.1.

Uso: extraer la etiqueta ``v0.5.1`` (``git archive v0.5.1 src | tar -x -C <dir>``) y ejecutar
``PYTHONPATH=<dir>/src python generar_datos.py``. Cada ``*.json`` lo escribe 0.5.1 y cada
``*.esperado.json`` es lo que 0.5.1 lee de él (``lote_a_dict``/``perfil_a_dict``). Las pruebas de la
fase A (RNF-A4, CA-A7.1.1, CA-A7.2.1) comprueban que 0.6 lo lee igual. No editar a mano.
"""

import json
import sys
from pathlib import Path

D = Path(__file__).resolve().parent

import proxlaunch  # noqa: E402

assert "0.5.1" in proxlaunch.__version__, f"se esperaba 0.5.1, hay {proxlaunch.__version__}"

from proxlaunch.nucleo.lote.modelos import (  # noqa: E402
    DefinicionLote,
    Destino,
    FilaLote,
    PatronNombres,
)
from proxlaunch.nucleo.lotes_guardados.formato import (  # noqa: E402
    leer_lote,
    lote_a_bytes,
    lote_a_dict,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado  # noqa: E402
from proxlaunch.nucleo.modelos.vm import (  # noqa: E402
    ConfiguracionVM,
    Disco,
    InterfazRed,
    ModeloRed,
    TipoSO,
)
from proxlaunch.nucleo.perfiles_maquina.formato import (  # noqa: E402
    leer_perfiles,
    perfil_a_dict,
    perfiles_a_bytes,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import (  # noqa: E402
    BallooningPerfil,
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)


def cfg(**cambios):
    base = {
        "vmid": 0,
        "nombre": "",
        "nodo": "",
        "memoria_mib": 4096,
        "cores": 2,
        "discos": [Disco("datos", 32)],
        "redes": [InterfazRed("vmbr0")],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def escribir(nombre, datos):
    (D / nombre).write_bytes(datos)


def lote(nombre, definicion, archivo):
    lg = LoteGuardado(nombre, definicion, "9.2")
    datos = lote_a_bytes(lg, app_version="0.5.1")
    escribir(archivo, datos)
    leido = leer_lote(datos).lote
    esperado = lote_a_dict(leido)
    escribir(
        archivo.replace(".json", ".esperado.json"),
        json.dumps(esperado, indent=2, sort_keys=True).encode(),
    )
    return json.loads(datos)["version_formato"]


v1 = lote(
    "Aula v1",
    DefinicionLote(cfg(), 5, PatronNombres("aula", "-", 1, 2), Destino()),
    "lote-homogeneo-051-v1.json",
)
v2 = lote(
    "Servidores v2",
    DefinicionLote(
        cfg(tipo_so=TipoSO.LINUX, agente_qemu=True, tpm=True),
        3,
        PatronNombres("srv", "-", 1, 2),
        Destino(),
    ),
    "lote-homogeneo-051-v2.json",
)
filas = (
    FilaLote("a-01", cfg(), None, None, None),
    FilaLote("a-02", cfg(agente_qemu=True, memoria_mib=8192), 150, "pve2", None),
)
v2f = lote(
    "Por filas v2",
    DefinicionLote(cfg(), 2, PatronNombres(""), Destino(), filas=filas),
    "lote-por-filas-051-v2.json",
)
assert (v1, v2, v2f) == (1, 2, 2), (v1, v2, v2f)

cp = ConfigPerfil(
    memoria_mib=4096,
    cores=4,
    discos=(DiscoPerfil(64, storage_preferido="local-lvm"),),
    redes=(RedPerfil(ModeloRed.VIRTIO, 20, "vmbr0"),),
    ballooning=BallooningPerfil(True, 1024),
)
perfil = PerfilMaquina("x", "Perfil 051", "Hecho con 0.5.1", OrigenPerfil.USUARIO, cp)
datos = perfiles_a_bytes([perfil], con_pistas=True, app_version="0.5.1")
escribir("perfiles-051-v1.json", datos)
leido = leer_perfiles(datos).validos[0]
esperado = perfil_a_dict(
    PerfilMaquina("x", leido.nombre, leido.descripcion, OrigenPerfil.USUARIO, leido.config),
    con_pistas=True,
)
escribir("perfiles-051-v1.esperado.json", json.dumps(esperado, indent=2, sort_keys=True).encode())
perfil2 = PerfilMaquina(
    "y",
    "Perfil 051 SO",
    "con SO",
    OrigenPerfil.USUARIO,
    ConfigPerfil(
        tipo_so=TipoSO.LINUX, agente_qemu=True, discos=(DiscoPerfil(32),), redes=(RedPerfil(),)
    ),
)
escribir("perfiles-051-v2.json", perfiles_a_bytes([perfil2], con_pistas=True, app_version="0.5.1"))
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica  # noqa: E402

escribir(
    "perfiles-fabrica-051.json",
    perfiles_a_bytes(perfiles_fabrica(), con_pistas=True, app_version="0.5.1"),
)
print("hecho", file=sys.stderr)
