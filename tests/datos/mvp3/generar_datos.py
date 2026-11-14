"""Regenera los archivos de ejemplo del MVP 3 (ejecutar: ``python generar_datos.py``).

Los bytes exactos importan (codificación, BOM y separadores); no editar los archivos a mano.
"""

import json
from pathlib import Path

D = Path(__file__).resolve().parent


def w(nombre, datos):
    (D / nombre).write_bytes(datos)


# CSV de Excel en español (Windows-1252, «;», decimal con coma)
w(
    "excel-windows1252.csv",
    (
        "nombre;cpu;memoria;disco;almacenamiento;red;vlan;nodo;vmid;descripción\r\n"
        "pg-01;1;1 GiB;8;datos;vmbr0;;;;peña\r\n"
        "pg-02;4;8 GiB;64;datos;vmbr0;20;;150;Ñandú\r\n"
        "pg-03;2;4,5;32;datos;vmbr0;;pve2;;ración\r\n"
        "pg-04;8;16;128;datos;vmbr0;;;151;ñoño\r\n"
    ).encode("cp1252"),
)

# UTF-8 con BOM y «,» con decimales entre comillas
w(
    "utf8-bom-comas.csv",
    (
        "﻿nombre,perfil,cpu,memoria,disco\r\n"
        'web-01,Servidor mediano,,"1,5",20\r\n'
        "web-02,,2,4 GiB,40\r\n"
    ).encode(),
)

# UTF-16 LE con BOM
w(
    "utf16-le.csv",
    b"\xff\xfe" + ("nombre;cpu;memoria\r\nñandú-01;2;4\r\nñandú-02;4;8\r\n").encode("utf-16-le"),
)

# Primera línea «sep=;» de Excel
w("sep-linea.csv", b"sep=;\r\nnombre;cpu;memoria\r\nweb-01;2;4\r\nweb-02;4;8\r\n")

# Celdas con disparadores de fórmula (nombre, perfil y columna desconocida)
w(
    "formulas.csv",
    (
        "﻿nombre;perfil;cpu;comentario\r\n"
        '=HYPERLINK("http://x","y");servidor-pequeno;2;@SUM(1)\r\n'
        "web-ok;=cmd|' /C calc'!A0;2;+1\r\n"
        "web-ok2;;2;-1\r\n"
        '\t=1;;2;" =1"\r\n'
    ).encode(),
)

# JSON de la versión 1 de cada formato (CA-X01.3: archivo de ejemplo de cada versión)
cfg_perfil = {
    "firmware": "seabios",
    "sockets": 1,
    "cores": 4,
    "tipo_cpu": "x86-64-v2-AES",
    "memoria_mib": 4096,
    "ballooning": None,
    "con_disco": True,
    "discos": [
        {
            "tamano_gib": 64,
            "bus": "scsi",
            "formato": "auto",
            "discard": True,
            "ssd": True,
            "iothread": True,
            "storage_preferido": "local-lvm",
        }
    ],
    "storage_efi_preferido": None,
    "controlador_scsi": "virtio-scsi-single",
    "redes": [{"modelo": "virtio", "vlan": None, "bridge_preferido": "vmbr0"}],
    "origen": "disco_vacio",
}
perfiles = {
    "formato": "proxlaunch.perfiles",
    "version_formato": 1,
    "app_version": "0.3.0",
    "perfiles": [
        {
            "nombre": "Servidor mediano",
            "descripcion": "Para aplicaciones web. Sin sistema operativo.",
            "config": cfg_perfil,
        },
        {
            "nombre": "Mínimo",
            "descripcion": "",
            "config": {**cfg_perfil, "cores": 1, "memoria_mib": 512},
        },
    ],
}
w(
    "perfiles-v1.json",
    (json.dumps(perfiles, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
)

cfg_lote = {
    "firmware": "seabios",
    "sockets": 1,
    "cores": 2,
    "tipo_cpu": "x86-64-v2-AES",
    "memoria_mib": 2048,
    "ballooning": None,
    "con_disco": True,
    "discos": [
        {
            "storage": "datos",
            "tamano_gib": 32,
            "bus": "scsi",
            "formato": "auto",
            "discard": True,
            "ssd": True,
            "iothread": True,
        }
    ],
    "storage_efi": None,
    "controlador_scsi": "virtio-scsi-single",
    "redes": [{"bridge": "vmbr0", "modelo": "virtio", "vlan": None}],
    "origen": "disco_vacio",
}
homogeneo = {
    "formato": "proxlaunch.lote",
    "version_formato": 1,
    "app_version": "0.3.0",
    "nombre": "Aula 3",
    "tipo": "homogeneo",
    "homogeneo": {
        "config": cfg_lote,
        "cantidad": 20,
        "patron": {"prefijo": "aula3-pc", "separador": "-", "inicio": 1, "relleno": 2},
        "destino": {"modo": "automatico", "nodos": [], "algoritmo": "equilibrado"},
        "vmid_inicial": None,
        "etiquetar": True,
    },
}
w(
    "lote-homogeneo-v1.json",
    (json.dumps(homogeneo, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
)

por_filas = {
    "formato": "proxlaunch.lote",
    "version_formato": 1,
    "app_version": "0.3.0",
    "nombre": "Heterogéneo",
    "tipo": "por_filas",
    "por_filas": {
        "filas": [
            {"nombre": "pg-01", "vmid": None, "nodo": None, "config": cfg_lote},
            {
                "nombre": "pg-02",
                "vmid": 150,
                "nodo": "pve2",
                "origen": 3,
                "config": {**cfg_lote, "cores": 4, "memoria_mib": 8192},
            },
        ],
        "destino": {"algoritmo": "equilibrado"},
        "vmid_inicial": None,
        "etiquetar": True,
    },
}
w(
    "lote-por-filas-v1.json",
    (json.dumps(por_filas, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
)

# Corruptos
w("perfiles-truncado.json", (D / "perfiles-v1.json").read_bytes()[:200])
w("lote-utf8-invalido.json", b'{"formato": "proxlaunch.lote", "nombre": "\xff\xfe\x80"}')
w(
    "lote-version-futura.json",
    (
        json.dumps(
            {**homogeneo, "version_formato": 2, "campo_nuevo": {"x": 1}},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8"),
)
print(sorted(p.name for p in D.iterdir()))
