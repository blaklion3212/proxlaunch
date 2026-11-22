"""Escenario ficticio común de las capturas de la guía (todo inventado).

Se construye con ``dataclasses.replace`` sobre los dobles de ``tests/interfaz`` sin modificarlos.
Direcciones del rango de documentación (RFC 5737); nada del laboratorio ni de un Proxmox real.

- Clúster ``demo``: ``pve1`` y ``pve2`` (64 GiB, 16 núcleos) y ``pve3``.
- Servidor individual: nodo ``pve``.
- Almacenamientos con discos: ``local-lvm`` (lvmthin, 500 GiB libres) y ``datos`` (dir, 1 TiB).
- ``local`` (dir): ISO, imágenes importables y copias, 120 GiB libres.
- Redes: ``vmbr0`` y ``vmbr1`` (con VLAN).
"""

from __future__ import annotations

from dataclasses import replace

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor, Contenido, ListadoStorage
from proxlaunch.nucleo.modelos.inventario import Bridge, Inventario, Nodo, Storage, Topologia
from proxlaunch.nucleo.modelos.tarea import Etapa
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed

from ..apoyo import GIB, CreacionPorVmid, storage
from ..apoyo_mvp4 import ROL_14, inv_origen, plantilla_pve, volumen

HOST = "192.0.2.10"
TOKEN = "proxlaunch@pve!lab=00000000-0000-0000-0000-000000000000"
USUARIO = "ana@pve"
# UPID con la forma real, pero del usuario ficticio y del nodo del escenario.
UPID = "UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:101:ana@pve!lab:"

ISOS = (
    ("local:iso/ubuntu-24.04-server.iso", int(2.6 * GIB)),
    ("local:iso/debian-12.iso", int(0.6 * GIB)),
    ("local:iso/windows-11-es.iso", 6 * GIB),
    ("local:iso/virtio-win-0.1.271.iso", 700 * 1024**2),
)
VOLID_UBUNTU = ISOS[0][0]
VOLID_WINDOWS = ISOS[2][0]
VOLID_VIRTIO = ISOS[3][0]
VOLID_DEBIAN_QCOW2 = "local:import/debian-12-generic.qcow2"
VOLID_UBUNTU_QCOW2 = "local:import/ubuntu-24.04-cloudimg.qcow2"


# 10 de marzo de 2025, 12:00 UTC (fecha fija y ficticia de los archivos del servidor).
FECHA_ARCHIVOS = 1741608000


def volumenes_iso():
    return [replace(volumen(v, Contenido.ISO, t), creado=FECHA_ARCHIVOS) for v, t in ISOS]


def _storages() -> tuple[Storage, ...]:
    """``local`` no admite imágenes de disco: solo ``local-lvm`` y ``datos``."""
    return (
        storage("local", "dir", "iso,import,backup", 120),
        storage("local-lvm", "lvmthin", "images,rootdir", 500),
        storage("datos", "dir", "images,rootdir", 1024),
    )


def _con_imagenes(todos: tuple[Storage, ...]) -> tuple[Storage, ...]:
    return tuple(s for s in todos if "images" in s.contenido)


def _plantillas(nodo: str):
    return (
        plantilla_pve(9000, "plantilla-debian12", nodo),
        plantilla_pve(9001, "plantilla-ubuntu", nodo),
    )


def plantillas_del_escenario(nodo: str):
    """Las plantillas ``plantilla-debian12`` (9000) y ``plantilla-ubuntu`` (9001) del escenario."""
    return _plantillas(nodo)


def imagenes_import():
    return [
        replace(volumen(v, Contenido.IMPORT, 2 * GIB), creado=FECHA_ARCHIVOS)
        for v in (VOLID_DEBIAN_QCOW2, VOLID_UBUNTU_QCOW2)
    ]


def _catalogo(base: CatalogoServidor, nodos: list[str]) -> CatalogoServidor:
    """Catálogo ya leído: ISOs e imágenes de ``local`` en cada nodo y las plantillas del clúster."""
    imagenes = imagenes_import()
    listados = []
    for nodo in nodos:
        listados.append(ListadoStorage(nodo, "local", Contenido.ISO, tuple(volumenes_iso())))
        listados.append(ListadoStorage(nodo, "local", Contenido.IMPORT, tuple(imagenes)))
    return replace(base, listados=tuple(listados), plantillas=_plantillas(nodos[0]))


# Rol de la guía más los privilegios del agente (9.x: VM.GuestAgent.Audit; 8.x: VM.Monitor),
# para que «Esperar la IP» no salga deshabilitada en las capturas que no tratan de eso.
PRIVILEGIOS_ESCENARIO = (*ROL_14, "VM.GuestAgent.Audit", "VM.Monitor")


def inventario_guia_individual(privilegios=PRIVILEGIOS_ESCENARIO) -> Inventario:
    """Servidor individual ``pve`` con el catálogo de ISOs, imágenes y plantillas de la guía."""
    base = inv_origen(
        privilegios=privilegios,
        volumenes=tuple(volumenes_iso()),
        plantillas=_plantillas("pve"),
    )
    todos = _storages()
    return replace(
        base,
        topologia=Topologia(False, None, (Nodo("pve", True, 51200, 16),)),
        storages={"pve": _con_imagenes(todos)},
        storages_todos={"pve": todos},
        bridges={"pve": (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "bridge", True))},
        proximo_vmid=101,
        catalogo=_catalogo(base.catalogo, ["pve"]),
    )


def inventario_guia_cluster(*, pve3_caido: bool = False) -> Inventario:
    """Clúster ``demo`` de tres nodos; con ``pve3_caido`` ese nodo no respondió."""
    base = inventario_guia_individual()
    todos = _storages()
    nodos = (
        Nodo("pve1", True, 61440, 16),
        Nodo("pve2", True, 49152, 16),
        Nodo("pve3", not pve3_caido, None if pve3_caido else 40960, None if pve3_caido else 16),
    )
    activos = [n.nombre for n in nodos if n.en_linea]
    redes = (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "bridge", True))
    return replace(
        base,
        topologia=Topologia(True, "demo", nodos),
        storages={n: _con_imagenes(todos) for n in activos},
        storages_todos={n: todos for n in activos},
        bridges={n: redes for n in activos},
        catalogo=_catalogo(base.catalogo, activos),
        errores_por_nodo=(
            {"pve3": ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE)} if pve3_caido else {}
        ),
    )


def configuracion_guia(**cambios) -> ConfiguracionVM:
    """Configuración con dos discos (VirtIO y SATA) y dos redes sobre el escenario."""
    base = {
        "vmid": 101,
        "nombre": "srv-web-01",
        "nodo": "pve1",
        "discos": [Disco("local-lvm", 32), Disco("datos", 100)],
        "redes": [InterfazRed("vmbr0"), InterfazRed("vmbr1", vlan=120)],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


# Clave pública ed25519 FALSA: base64 válido (tipo + 32 bytes con un patrón), sin clave privada
# detrás. Se usa en las capturas y en los ejemplos de cloud-init; nunca es una clave real.
CLAVE_SSH_FALSA = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAMKERgfJi00O0JJUFdeZWxzeoGIj5adpKuyucDHztXc ana@portatil"
)

# CSV de ejemplo de la guía (copia de ``docs/ejemplos``; se escribe con BOM, como lo haría Excel).
CSV_MIXTAS = """"nombre";"perfil";"cpu";"memoria";"disco";"almacenamiento";"red";"vlan";"nodo";"vmid";"origen";"fuente";"so";"virtio";"modo_clon"
"web-01";"fabrica.servidor-mediano";"";"";"";"local-lvm";"vmbr0";"";"";"";"vacio";"";"";"";""
"db-01";"fabrica.base-de-datos";"";"16 GiB";"200 GiB";"local-lvm";"vmbr1";"20";"pve1";"210";"vacio";"";"";"";""
"ubuntu-01";"";"2";"4 GiB";"40 GiB";"";"vmbr0";"";"";"";"iso";"ubuntu-24.04-server.iso";"linux";"";""
"win11-01";"fabrica.windows-11";"4";"8 GiB";"80 GiB";"";"vmbr0";"";"";"";"iso";"windows-11-es.iso";"windows 11";"si";""
"debian-img-01";"";"2";"2 GiB";"60 GiB";"";"vmbr0";"";"";"";"importar";"debian-12-generic.qcow2";"linux";"";""
"clon-01";"";"2";"4 GiB";"";"";"";"";"";"";"clonar";"plantilla-debian12";"";"";"enlazado"
"clon-02";"";"";"";"";"";"";"";"";"";"clonar";"plantilla-ubuntu";"";"";"auto"
"""  # noqa: E501

CSV_CON_ERRORES = """"nombre";"perfil";"cpu";"memoria";"disco";"vmid";"origen";"fuente";"so"
"ejemplo-web";"fabrica.servidor-mediano";"2";"4";"40";"";"vacio";"";""
"";"fabrica.servidor-mediano";"2";"4";"40";"";"vacio";"";""
"srv_malo";"fabrica.servidor-mediano";"2";"4";"40";"";"vacio";"";""
"web-dup";"fabrica.servidor-mediano";"2";"4";"40";"150";"vacio";"";""
"web-dup";"fabrica.servidor-mediano";"2";"4 GB";"40";"150";"vacio";"";""
"mem-mal";"fabrica.servidor-mediano";"2";"abc";"40";"";"vacio";"";""
"sin-perfil";"fabrica.no-existe";"2";"4";"40";"";"vacio";"";""
"iso-url";"";"2";"4";"40";"";"iso";"https://example.com/a.iso";"linux"
"""  # noqa: E501


def _csv_cloudinit() -> str:
    """CSV de la captura de cloud-init: ``docs/ejemplos/mvs-cloudinit.csv`` más la columna
    ``ci_contrasena`` (contraseña inventada; la aplicación la muestra siempre enmascarada)."""
    columnas = [
        *("nombre", "perfil", "origen", "fuente", "encender", "esperar_ip"),
        *("ci_usuario", "ci_claves", "ci_contrasena", "ci_ip", "ci_puerta", "ci_dns"),
    ]
    clave = CLAVE_SSH_FALSA
    filas = (
        ("app-01", "fabrica.servidor-mediano", "plantilla-debian12", "si", "ana", "dhcp", "", ""),
        (
            "app-02",
            "fabrica.servidor-mediano",
            "plantilla-debian12",
            "si",
            "ana",
            "192.0.2.51/24",
            "192.0.2.1",
            "192.0.2.2",
        ),
        (
            "app-03",
            "fabrica.servidor-mediano",
            "plantilla-debian12",
            "si",
            "ana",
            "192.0.2.52/24",
            "192.0.2.1",
            "192.0.2.2",
        ),
        (
            "bd-01",
            "fabrica.base-de-datos",
            "plantilla-ubuntu",
            "no",
            "ana",
            "192.0.2.60/24",
            "192.0.2.1",
            "192.0.2.2",
        ),
    )
    lineas = [";".join(f'"{c}"' for c in columnas)]
    for nombre, perfil, plantilla, espera, usuario, ip, puerta, dns in filas:
        celdas = (nombre, perfil, "clonar", plantilla, "si", espera, usuario, clave) + (
            "Ejemplo-1234",
            ip,
            puerta,
            dns,
        )
        lineas.append(";".join(f'"{c}"' for c in celdas))
    return "\n".join(lineas) + "\n"


CSV_CLOUDINIT = _csv_cloudinit()


def escribir_csv_guia(carpeta, nombre: str, texto: str):
    """Escribe un CSV UTF-8 con BOM en ``carpeta`` (su ruta no se muestra en ninguna captura)."""
    ruta = carpeta / nombre
    ruta.write_bytes(b"\xef\xbb\xbf" + texto.encode("utf-8"))
    return ruta


class CreacionConSecuenciaCompleta(CreacionPorVmid):
    """Doble de creación que, tras la espera en vuelo, emite también COMPROBANDO.

    El doble común solo llega hasta CREANDO; así la captura del progreso terminado muestra la
    secuencia real (VALIDANDO, ENVIANDO, CREANDO, COMPROBANDO y, al cerrar la ventana, LISTO).
    """

    def crear(self, cfg, inv, al_cambiar_etapa, cancelado, **kw):
        res = super().crear(cfg, inv, al_cambiar_etapa, cancelado, **kw)
        al_cambiar_etapa(Etapa.COMPROBANDO)
        return res
