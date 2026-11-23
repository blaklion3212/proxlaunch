"""Regenera los archivos de 0.7.0 de este directorio con el CÓDIGO de la versión 0.7.0.

Uso: extraer la versión 0.7.0 (``git archive <commit-0.7.0> src | tar -x -C <dir>``) y ejecutar
``python p4_generar_datos.py <dir>/src``. Cada ``p4_*.json`` lo escribe 0.7.0 y cada
``*.esperado.json`` es lo que 0.7.0 lee/produce de él. Las pruebas de la fase C (CA-C6.1.1,
CA-C6.1.2, CA-C6.1.3, CA-C6.3.1, CA-C6.3.11, CA-C6.4.1) comprueban que 0.8.0 lo lee igual, que lo
regraba sin cambios ni subir de versión y que un CSV de 0.7.0 da las mismas filas. No editar a mano.
"""

import json
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

import proxlaunch  # noqa: E402

assert "0.7.0" in proxlaunch.__version__, f"se esperaba 0.7.0, hay {proxlaunch.__version__}"

from proxlaunch.nucleo.archivos.esquema_opciones import opciones_parciales_a_dict  # noqa: E402
from proxlaunch.nucleo.cloudinit.modelos import (  # noqa: E402
    ConfigCloudInit,
    ModoTarjeta,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar  # noqa: E402
from proxlaunch.nucleo.csv_importacion.lectura import leer_tabla  # noqa: E402
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
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica  # noqa: E402
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO  # noqa: E402


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
    datos = lote_a_bytes(lg, app_version="0.7.0")
    escribir(archivo, datos)
    esperado = lote_a_dict(leer_lote(datos).lote)
    escribir(
        archivo.replace(".json", ".esperado.json"),
        json.dumps(esperado, indent=2, sort_keys=True).encode(),
    )
    return json.loads(datos)["version_formato"]


ci = ConfigCloudInit(
    usuario="deploy",
    tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, "10.0.0.50/24", puerta="10.0.0.1"),),
    dns=("1.1.1.1",),
    dominio="lab.local",
)
ops = OpcionesLote(encender=True, esperar_ip=True, plazo_ip_s=90, cloudinit=ci)

v1 = lote(
    "Simple v1",
    DefinicionLote(
        cfg(redes=[InterfazRed("vmbr0")]), 3, PatronNombres("web", "-", 1, 2), Destino()
    ),
    "p4_lote-homogeneo-070-v1.json",
)
v3 = lote(
    "Con A v3",
    DefinicionLote(
        cfg(proteger=True), 2, PatronNombres("aula", "-", 1, 2), Destino(),
        opciones=OpcionesLote(notas="0.7.0", etiquetas_usuario=("web",), pool="prod"),
    ),
    "p4_lote-homogeneo-070-v3.json",
)  # fmt: skip
v4 = lote(
    "Con B v4",
    DefinicionLote(
        cfg(cloudinit=ci, esperar_ip=True, plazo_ip_s=90, encender=True),
        3, PatronNombres("srv", "-", 1, 2), Destino(), opciones=ops,
    ),
    "p4_lote-homogeneo-070-v4.json",
)  # fmt: skip
filas = (
    FilaLote("a-01", cfg(), None, None, None),
    FilaLote(
        "a-02",
        cfg(cloudinit=ci, esperar_ip=True, encender=True),
        150,
        "pve2",
        None,
        OpcionesParciales(esperar_ip=True, encender=True, notas="solo esta"),
    ),
)
v4f = lote(
    "Por filas v4",
    DefinicionLote(cfg(), 2, PatronNombres(""), Destino(), filas=filas, opciones=ops),
    "p4_lote-por-filas-070-v4.json",
)
assert (v1, v3, v4, v4f) == (1, 3, 4, 4), (v1, v3, v4, v4f)

# --- CSV de 0.7.0: las filas que produce ---
CSV = (
    b"nombre;origen;fuente;cpu;memoria;red;vlan;modelo_red;mtu;encender;ci_usuario;ci_ip;esperar_ip\r\n"
    b"web-01;clonar;base;2;4;vmbr1;30;virtio;1500;si;deploy;10.0.0.5/24;si\r\n"
    b"web-02;clonar;base;4;8;;;;;no;;;\r\n"
    b"web-03;;;2;4;vmbr0;20;e1000;;;;;\r\n"
    b"web-04;clonar;base;2;4;vmbr0;5000;;;;;;\r\n"
)
escribir("p4_csv-070.csv", CSV)
fabrica = perfiles_fabrica()
base = next(p for p in fabrica if p.id == ID_PREDETERMINADO)
r = interpretar(
    leer_tabla(CSV), perfil_base=base, perfiles=tuple(fabrica), inv=None, nodo_referencia="pve1"
)
salida = []
for f in r.filas:
    salida.append(
        {
            "numero": f.numero,
            "nombre": f.nombre,
            "estado": str(f.estado),
            "cfg": None if f.cfg is None else f.cfg.a_dict(),
            "opciones": None if f.opciones is None else opciones_parciales_a_dict(f.opciones),
            "problemas": [[p.columna, p.regla, str(p.severidad)] for p in f.problemas],
        }
    )
escribir("p4_csv-070.esperado.json", json.dumps(salida, indent=2, sort_keys=True).encode())
print("hecho", file=sys.stderr)
