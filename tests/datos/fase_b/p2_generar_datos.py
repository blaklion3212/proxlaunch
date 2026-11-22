"""Regenera los archivos de 0.6.0 de este directorio con el CÓDIGO de la versión 0.6.0.

Uso: extraer la etiqueta ``v0.6.0`` (``git archive v0.6.0 src | tar -x -C <dir>``) y ejecutar
``python p2_generar_datos.py <dir>/src``. Cada ``p2_*.json`` lo escribe 0.6.0 y cada
``p2_*.esperado.json`` es lo que 0.6.0 lee de él (``lote_a_dict``/``perfil_a_dict``). Las pruebas
de la fase B (CA-B6.1.1, CA-B6.1.2, CA-B6.4.1, CA-B6.2.2) comprueban que 0.7.0 lo lee igual y que
al regrabarlo no cambia ni sube de versión. No editar a mano.
"""

import json
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

import proxlaunch  # noqa: E402

assert "0.6.0" in proxlaunch.__version__, f"se esperaba 0.6.0, hay {proxlaunch.__version__}"

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
)
from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales  # noqa: E402
from proxlaunch.nucleo.perfiles_maquina.formato import (  # noqa: E402
    leer_perfiles,
    perfil_a_dict,
    perfiles_a_bytes,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import (  # noqa: E402
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
        "redes": [InterfazRed("vmbr0", ModeloRed.VIRTIO, 20, 1500, 100.0)],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def escribir(nombre, datos):
    (D / nombre).write_bytes(datos)


def lote(nombre, definicion, archivo):
    lg = LoteGuardado(nombre, definicion, "9.2")
    datos = lote_a_bytes(lg, app_version="0.6.0")
    escribir(archivo, datos)
    esperado = lote_a_dict(leer_lote(datos).lote)
    escribir(
        archivo.replace(".json", ".esperado.json"),
        json.dumps(esperado, indent=2, sort_keys=True).encode(),
    )
    return json.loads(datos)["version_formato"]


opciones = OpcionesLote(
    encender=True,
    arranque_auto=True,
    notas="Lote de 0.6.0",
    etiquetas_usuario=("web", "prod"),
    pool="produccion",
    proteger=True,
)
v3 = lote(
    "Aula v3",
    DefinicionLote(
        cfg(encender=True, arranque_auto=True, proteger=True),
        4,
        PatronNombres("aula", "-", 1, 2),
        Destino(),
        opciones=opciones,
    ),
    "p2_lote-homogeneo-060-v3.json",
)
filas = (
    FilaLote("a-01", cfg(), None, None, None),
    FilaLote(
        "a-02",
        cfg(memoria_mib=8192),
        150,
        "pve2",
        None,
        OpcionesParciales(
            encender=True, notas="solo esta", etiquetas_usuario=("db",), proteger=True
        ),
    ),
)
v3f = lote(
    "Por filas v3",
    DefinicionLote(cfg(), 2, PatronNombres(""), Destino(), filas=filas, opciones=opciones),
    "p2_lote-por-filas-060-v3.json",
)
assert (v3, v3f) == (3, 3), (v3, v3f)

perfil = PerfilMaquina(
    "x",
    "Perfil 060",
    "Hecho con 0.6.0",
    OrigenPerfil.USUARIO,
    ConfigPerfil(
        memoria_mib=4096,
        discos=(DiscoPerfil(64, storage_preferido="local-lvm"),),
        redes=(RedPerfil(ModeloRed.VIRTIO, 20, "vmbr0", 1500, 50.0),),
        arranque_auto=True,
    ),
)
datos = perfiles_a_bytes([perfil], con_pistas=True, app_version="0.6.0")
assert json.loads(datos)["version_formato"] == 3
escribir("p2_perfiles-060-v3.json", datos)
leido = leer_perfiles(datos).validos[0]
esperado = perfil_a_dict(
    PerfilMaquina("x", leido.nombre, leido.descripcion, OrigenPerfil.USUARIO, leido.config),
    con_pistas=True,
)
escribir(
    "p2_perfiles-060-v3.esperado.json", json.dumps(esperado, indent=2, sort_keys=True).encode()
)
print("hecho", file=sys.stderr)
