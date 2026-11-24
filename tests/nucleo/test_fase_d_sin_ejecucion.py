"""D1.13: la app no ejecuta nada en el equipo (RF-D1.13; RNF-D2.2 y RNF-D2.4).

Derivadas de docs/requisitos/fase-d.md: CA-D1.13.1 a CA-D1.13.3 y CA-D1.2.5. Dos vías: análisis
estático (AST) de los módulos de ``src/`` y ejecución completa del recorrido con dobles de
``subprocess``, ``os.system``, ``socket`` y de la apertura de archivos. La parte de interfaz del
asistente (botón «Copiar» y diálogo abierto) está en
``tests/interfaz/test_fase_d_libvirt_dialogo.py``.
"""

from __future__ import annotations

import ast
import builtins
import os
import socket
import subprocess
from pathlib import Path

import pytest

import proxlaunch
from proxlaunch.nucleo.errores import ErrorProxLaunch

from .apoyo_fase_d_libvirt import (
    bytes_xml,
    inventario_d,
    proponer_de,
)

RAIZ = Path(proxlaunch.__file__).parent
MODULOS_DEL_ASISTENTE = sorted(
    [
        *(RAIZ / "nucleo" / "libvirt").glob("*.py"),
        RAIZ / "interfaz" / "dialogos" / "importar_libvirt.py",
    ]
)
PROHIBIDOS = {
    "subprocess",
    "shlex",
    "socket",
    "ctypes",
    "pty",
    "multiprocessing",
    "webbrowser",
    "urllib",
    "http",
}
LLAMADAS_PROHIBIDAS = {
    "os.system", "os.popen", "os.exec", "os.execv", "os.execve", "os.execvp", "os.spawnv",
    "os.posix_spawn", "os.fork", "eval", "exec", "compile", "__import__", "input",
}  # fmt: skip


def _arbol(ruta: Path) -> ast.AST:
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def _importados(arbol: ast.AST) -> set[str]:
    nombres: set[str] = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            nombres.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            nombres.add(n.module.split(".")[0])
            nombres.update(f"{n.module}.{a.name}" for a in n.names)
    return nombres


def _nombre_llamada(nodo: ast.Call) -> str:
    f = nodo.func
    partes: list[str] = []
    while isinstance(f, ast.Attribute):
        partes.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        partes.append(f.id)
    return ".".join(reversed(partes))


# --- CA-D1.13.3: análisis estático -----------------------------------------------------------


def test_los_modulos_del_asistente_existen():
    assert len(MODULOS_DEL_ASISTENTE) >= 5
    assert all(m.is_file() for m in MODULOS_DEL_ASISTENTE)


@pytest.mark.parametrize("ruta", MODULOS_DEL_ASISTENTE, ids=lambda r: r.name)
def test_ca_d1_13_3_el_modulo_no_importa_subprocess_shlex_socket_ni_os_system(ruta):
    importados = _importados(_arbol(ruta))
    assert not {i for i in importados if i.split(".")[0] in PROHIBIDOS}, ruta.name
    assert "os.system" not in importados and "os.popen" not in importados


@pytest.mark.parametrize("ruta", MODULOS_DEL_ASISTENTE, ids=lambda r: r.name)
def test_ca_d1_13_3_el_modulo_no_llama_a_nada_que_ejecute_o_evalue(ruta):
    llamadas = {_nombre_llamada(n) for n in ast.walk(_arbol(ruta)) if isinstance(n, ast.Call)}
    assert not llamadas & LLAMADAS_PROHIBIDAS, (ruta.name, llamadas & LLAMADAS_PROHIBIDAS)


@pytest.mark.parametrize(
    "ruta",
    [m for m in MODULOS_DEL_ASISTENTE if m.parent.name == "libvirt" and m.name != "lectura_xml.py"],
    ids=lambda r: r.name,
)
def test_ca_d1_13_2_el_nucleo_de_libvirt_no_abre_archivos_salvo_lectura_xml(ruta):
    """Solo ``lectura_xml.leer_archivo`` abre el archivo elegido; el resto trabaja en memoria."""
    llamadas = {_nombre_llamada(n) for n in ast.walk(_arbol(ruta)) if isinstance(n, ast.Call)}
    abridores = {"open", "os.open", "Path.open", "io.open", "read_bytes", "read_text"}
    assert not {
        c for c in llamadas if c in abridores or c.endswith((".read_bytes", ".read_text", ".open"))
    }


def test_ca_d1_13_3_el_xml_no_se_analiza_con_otro_analizador_que_etree():
    for ruta in (RAIZ / "nucleo" / "libvirt").glob("*.py"):
        importados = _importados(_arbol(ruta))
        for malo in ("xml.dom", "xml.sax", "lxml", "defusedxml", "xml.parsers"):
            assert not {i for i in importados if i.startswith(malo)}, (ruta.name, malo)


def test_ca_d1_13_3_en_todo_src_solo_la_huella_tls_usa_socket_y_nadie_usa_subprocess():
    con_socket: list[str] = []
    for ruta in RAIZ.rglob("*.py"):
        importados = _importados(_arbol(ruta))
        if {"subprocess", "shlex"} & importados:
            pytest.fail(f"{ruta.relative_to(RAIZ)} importa subprocess/shlex")
        if "socket" in importados:
            con_socket.append(ruta.relative_to(RAIZ).as_posix())
        llamadas = {_nombre_llamada(n) for n in ast.walk(_arbol(ruta)) if isinstance(n, ast.Call)}
        assert not llamadas & {"os.system", "os.popen"}, ruta
    assert set(con_socket) <= {"nucleo/api/huella.py"}


# --- Doble dinámico ------------------------------------------------------------------------------


@pytest.fixture
def dobles(monkeypatch):
    """Dobles que registran (y prohíben) lanzar procesos, abrir sockets o abrir archivos."""

    class Registro:
        procesos: list[str] = []
        redes: list[str] = []
        abiertos: list[str] = []
        permitidos: set[str] = set()

    reg = Registro()
    reg.procesos, reg.redes, reg.abiertos, reg.permitidos = [], [], [], set()

    def prohibir(lista, nombre):
        def f(*a, **k):
            lista.append(nombre)
            raise AssertionError(f"llamada prohibida: {nombre}")

        return f

    for nombre in (
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
        "getoutput",
        "getstatusoutput",
    ):
        monkeypatch.setattr(subprocess, nombre, prohibir(reg.procesos, f"subprocess.{nombre}"))
    for nombre in ("system", "popen", "execv", "execve", "execvp", "spawnv", "posix_spawn", "fork"):
        if hasattr(os, nombre):
            monkeypatch.setattr(os, nombre, prohibir(reg.procesos, f"os.{nombre}"))
    for nombre in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "socketpair"):
        monkeypatch.setattr(socket, nombre, prohibir(reg.redes, f"socket.{nombre}"))

    real_open, real_os_open = builtins.open, os.open

    def espia_open(archivo, *a, **k):
        reg.abiertos.append(
            os.fspath(archivo) if isinstance(archivo, (str, bytes, os.PathLike)) else "fd"
        )
        return real_open(archivo, *a, **k)

    def espia_os_open(ruta, *a, **k):
        reg.abiertos.append(os.fspath(ruta))
        return real_os_open(ruta, *a, **k)

    monkeypatch.setattr(builtins, "open", espia_open)
    monkeypatch.setattr(os, "open", espia_os_open)
    return reg


XML_RUTAS = """<domain type='kvm'><name>m</name><memory unit='GiB'>1</memory><vcpu>1</vcpu>
<os firmware='efi'><type arch='x86_64'>hvm</type><nvram>/etc/shadow</nvram>
<loader type='pflash'>/etc/hostname</loader></os>
<devices>
<disk type='file' device='disk'><driver name='qemu' type='qcow2'/><source file='/etc/passwd'/>
  <backingStore type='file'><source file='/etc/group'/></backingStore>
  <target dev='vda' bus='virtio'/></disk>
<disk type='block' device='disk'><source dev='/dev/sda'/><target dev='vdb' bus='virtio'/></disk>
<disk type='file' device='cdrom'><source file='/root/.ssh/id_rsa'/>
  <target dev='sda' bus='sata'/></disk>
<interface type='bridge'><source bridge='../../etc/passwd'/><model type='virtio'/></interface>
<channel type='unix'><source mode='bind' path='/var/lib/libvirt/qemu/channel/target/x.agent'/>
  <target type='virtio' name='org.qemu.guest_agent.0'/></channel>
<graphics type='vnc' passwd='x'/>
</devices></domain>"""


def test_ca_d1_13_1_y_13_2_el_recorrido_completo_no_ejecuta_nada_ni_abre_rutas_del_xml(
    dobles, tmp_path
):
    from proxlaunch.interfaz.textos import texto_problema
    from proxlaunch.interfaz.trabajadores import leer_xml_libvirt

    elegido = tmp_path / "maquina.xml"
    elegido.write_text(XML_RUTAS, encoding="utf-8")
    dobles.abiertos.clear()
    dominio = leer_xml_libvirt(elegido)
    for conservar in (False, True):
        p = proponer_de(dominio, inv=inventario_d(), conservar_mac=conservar)
        for f in p.filas:
            if f.problema is not None:
                texto_problema(f.problema)
    assert dobles.procesos == [] and dobles.redes == []
    assert dobles.abiertos, "debería haberse abierto el archivo elegido"
    assert {Path(a).resolve() for a in dobles.abiertos} == {elegido.resolve()}


def test_ca_d1_13_2_el_archivo_original_se_muestra_como_texto_y_nunca_se_abre(dobles, tmp_path):
    from proxlaunch.interfaz.trabajadores import leer_xml_libvirt

    elegido = tmp_path / "m.xml"
    elegido.write_text(XML_RUTAS, encoding="utf-8")
    dominio = leer_xml_libvirt(elegido)
    p = proponer_de(dominio, inv=inventario_d())
    texto = " ".join(f"{f.origen} {f.destino}" for f in p.filas)
    assert "passwd" in texto  # solo se muestra el nombre
    assert not any("/etc/" in a or "/root/" in a or "/dev/" in a for a in dobles.abiertos)


def test_ca_d1_2_5_el_unico_archivo_abierto_es_el_elegido_en_el_selector(dobles, tmp_path):
    from proxlaunch.interfaz.trabajadores import leer_xml_libvirt

    elegido = tmp_path / "linux.xml"
    elegido.write_bytes(bytes_xml("linux_bios.xml"))
    dobles.abiertos.clear()
    leer_xml_libvirt(elegido)
    assert [Path(a).resolve() for a in dobles.abiertos] == [elegido.resolve()]


def test_ca_d1_2_5_un_xml_con_doctype_tampoco_abre_nada_mas(dobles, tmp_path):
    from proxlaunch.interfaz.trabajadores import leer_xml_libvirt

    elegido = tmp_path / "ataque.xml"
    elegido.write_bytes(bytes_xml("entidad_externa.xml"))
    dobles.abiertos.clear()
    with pytest.raises(ErrorProxLaunch) as e:
        leer_xml_libvirt(elegido)
    assert e.value.params["motivo"] == "doctype"
    assert [Path(a).resolve() for a in dobles.abiertos] == [elegido.resolve()]
    assert dobles.redes == [] and dobles.procesos == []


def test_ca_d1_2_5_solo_se_lee_el_archivo_elegido_aunque_haya_un_enlace_a_otro(dobles, tmp_path):
    """Un enlace simbólico elegido en el selector se abre sin seguirlo a ciegas (O_NOFOLLOW)."""
    from proxlaunch.interfaz.trabajadores import leer_xml_libvirt

    real = tmp_path / "real.xml"
    real.write_bytes(bytes_xml("linux_bios.xml"))
    enlace = tmp_path / "enlace.xml"
    enlace.symlink_to(real)
    try:
        leer_xml_libvirt(enlace)
    except ErrorProxLaunch as e:
        assert e.codigo.value.startswith("archivo")  # rechazado: no sigue enlaces
    assert dobles.procesos == [] and dobles.redes == []


def test_el_trabajador_no_guarda_la_ruta_elegida_ni_el_xml(dobles, tmp_path, monkeypatch):
    from proxlaunch.interfaz.trabajadores import leer_xml_libvirt

    escritos: list[str] = []
    real_open = builtins.open

    def espia(archivo, modo="r", *a, **k):
        if any(c in str(modo) for c in "wax+"):
            escritos.append(str(archivo))
        return real_open(archivo, modo, *a, **k)

    monkeypatch.setattr(builtins, "open", espia)
    elegido = tmp_path / "m.xml"
    elegido.write_bytes(bytes_xml("linux_bios.xml"))
    leer_xml_libvirt(elegido)
    assert escritos == []
