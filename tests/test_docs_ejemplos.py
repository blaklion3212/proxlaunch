"""Pruebas de los archivos de ejemplo de la guía de usuario (``docs/ejemplos/``).

Garantizan que cada ejemplo es válido según los lectores reales de la aplicación (CSV, lotes
guardados y perfiles exportados), que ``mvs-con-errores.csv`` produce exactamente los problemas
que documenta su LEEME, que no hay datos reales (IPs, correos, secretos), que el generador de
capturas lleva copias embebidas idénticas a los ejemplos y que ese generador queda fuera de la
suite por defecto. Solo lee ``docs/ejemplos``; no ejecuta el generador ni usa red.
"""

from __future__ import annotations

import ast
import ipaddress
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila, ResultadoImportacion
from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote, leer_archivo_lote
from proxlaunch.nucleo.modelos.origen import DetalleImportacion
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import (
    exportar_perfiles,
    leer_archivo_perfiles,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ID_PREDETERMINADO,
    OrigenPerfil,
    PerfilMaquina,
)

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLOS = RAIZ / "docs" / "ejemplos"
ESCENARIO = RAIZ / "tests" / "interfaz" / "capturas_guia" / "escenario.py"
CAPTURAS = RAIZ / "tests" / "interfaz" / "capturas_guia"

# Filas de datos esperadas por cada CSV válido.
CSV_VALIDOS = {
    "mvs-minimo.csv": 3,
    "mvs-mixtas.csv": 7,
    "mvs-multidisco-cluster.csv": 3,
    "mvs-escrito-a-mano.csv": 3,
    "mvs-opciones.csv": 4,
    "mvs-cloudinit.csv": 4,
    "mvs-red-firewall.csv": 4,
    "mvs-hardware-cluster.csv": 4,
}
LOTES = (
    "lote-homogeneo.proxlaunch-lote.json",
    "lote-por-filas.proxlaunch-lote.json",
    "lote-con-opciones.proxlaunch-lote.json",
    "lote-cloudinit.proxlaunch-lote.json",
    "lote-red-firewall.proxlaunch-lote.json",
    "lote-libvirt.proxlaunch-lote.json",
)
PERFILES = "perfiles-ejemplo.proxlaunch-perfiles.json"

REDES_DOCUMENTACION = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
)


def _importar(nombre: str) -> ResultadoImportacion:
    """Lee e interpreta un CSV de ejemplo con los lectores reales (solo capa 1, sin servidor)."""
    fabrica = perfiles_fabrica()
    base = next(p for p in fabrica if p.id == ID_PREDETERMINADO)
    return interpretar(
        leer_archivo_csv(EJEMPLOS / nombre),
        perfil_base=base,
        perfiles=fabrica,
        inv=None,
        nodo_referencia=None,
    )


def _problemas(res: ResultadoImportacion) -> list[tuple[int, str | None, str, str]]:
    """(fila, columna, regla, severidad) de todos los problemas, ordenados."""
    return sorted(
        (f.numero, p.columna, p.regla, p.severidad.name) for f in res.filas for p in f.problemas
    )


# --- 1. CSV válidos -------------------------------------------------------------------------


@pytest.mark.parametrize(("nombre", "filas"), sorted(CSV_VALIDOS.items()))
def test_csv_valido_se_lee_sin_problemas_de_fila(nombre: str, filas: int) -> None:
    res = _importar(nombre)
    assert len(res.filas) == filas
    assert [f.numero for f in res.filas] == list(range(2, filas + 2))  # numeración de Excel
    assert _problemas(res) == []
    assert all(f.estado == EstadoFila.CORRECTA for f in res.filas)
    assert res.numeros_validos == tuple(f.numero for f in res.filas)


def test_csv_mixtas_cubre_los_cinco_origenes_y_nombres_esperados() -> None:
    res = _importar("mvs-mixtas.csv")
    assert [f.nombre for f in res.filas] == [
        "web-01",
        "db-01",
        "ubuntu-01",
        "win11-01",
        "debian-img-01",
        "clon-01",
        "clon-02",
    ]


def test_csv_escrito_a_mano_no_tiene_bom_ni_comillas_ni_crlf() -> None:
    crudo = (EJEMPLOS / "mvs-escrito-a-mano.csv").read_bytes()
    assert not crudo.startswith(b"\xef\xbb\xbf")
    assert b'"' not in crudo
    assert b"\r" not in crudo


# --- 2. CSV con errores: coincide con el LEEME ----------------------------------------------

# (fila, columna, regla, severidad) según el LEEME; la regla es la que emite la aplicación.
PROBLEMAS_DOCUMENTADOS = [
    (2, "nombre", "V-M11", "AVISO"),  # parece una fila de ejemplo
    (3, "nombre", "V-M07", "ERROR"),  # falta el nombre
    (4, "nombre", "V-01", "ERROR"),  # nombre con guion bajo
    (5, "nombre", "V-M10", "ERROR"),  # nombre duplicado
    (5, "vmid", "V-M10", "ERROR"),  # vmid duplicado
    (6, "nombre", "V-M10", "ERROR"),
    (6, "vmid", "V-M10", "ERROR"),
    (7, "memoria", "E-M11.no_numero", "ERROR"),  # «abc»
    (8, "perfil", "V-M06", "ERROR"),  # perfil inexistente
    (9, "fuente", "E-O21", "ERROR"),  # URL en lugar de nombre de archivo
    (9, "fuente", "V-O01", "ERROR"),  # falta elegir un ISO
]


def test_con_errores_produce_exactamente_los_problemas_del_leeme() -> None:
    res = _importar("mvs-con-errores.csv")
    assert len(res.filas) == 8
    assert _problemas(res) == sorted(PROBLEMAS_DOCUMENTADOS)


def test_con_errores_una_fila_correcta_con_aviso_y_siete_con_error() -> None:
    res = _importar("mvs-con-errores.csv")
    estados = {f.numero: f.estado for f in res.filas}
    assert estados.pop(2) == EstadoFila.CON_AVISO
    assert set(estados.values()) == {EstadoFila.CON_ERROR}
    assert len(estados) == 7
    assert res.numeros_validos == (2,)


def test_con_errores_parametros_de_duplicados_y_perfil_coinciden_con_el_leeme() -> None:
    res = _importar("mvs-con-errores.csv")
    por_clave = {(f.numero, p.columna, p.regla): p.params for f in res.filas for p in f.problemas}
    assert por_clave[(5, "nombre", "V-M10")] == {"filas": "5, 6", "nombre": "web-dup"}
    assert por_clave[(6, "vmid", "V-M10")] == {"filas": "5, 6", "vmid": "150"}
    assert por_clave[(8, "perfil", "V-M06")]["nombre"] == "fabrica.no-existe"


def test_con_errores_avisos_de_archivo_son_los_tres_del_leeme() -> None:
    res = _importar("mvs-con-errores.csv")
    avisos = sorted((a.codigo.value, a.params["columna"]) for a in res.avisos)
    assert avisos == [
        ("gb_como_gib", "memoria"),
        ("gib_asumido", "disco"),
        ("gib_asumido", "memoria"),
    ]


# --- 3. Lotes y perfiles --------------------------------------------------------------------


@pytest.mark.parametrize("nombre", LOTES)
def test_lote_de_ejemplo_se_lee_y_hace_ida_y_vuelta(nombre: str, tmp_path: Path) -> None:
    leido = leer_archivo_lote(EJEMPLOS / nombre)
    assert leido.lote.nombre
    copia = tmp_path / nombre
    guardar_lote(copia, leido.lote, app_version="0.0.0")
    assert leer_archivo_lote(copia).lote == leido.lote


def test_lote_homogeneo_son_tres_mvs_srv_web() -> None:
    lote = leer_archivo_lote(EJEMPLOS / LOTES[0]).lote
    assert lote.definicion.cantidad == 3


def test_lote_cloudinit_es_formato_4_con_ip_en_serie_y_espera_de_ip() -> None:
    leido = leer_archivo_lote(EJEMPLOS / "lote-cloudinit.proxlaunch-lote.json")
    assert leido.avisos == ()
    cfg = leido.lote.definicion.plantilla
    assert leido.lote.definicion.cantidad == 4
    assert cfg.cloudinit is not None
    (tarjeta,) = cfg.cloudinit.tarjetas
    assert (tarjeta.ip, tarjeta.serie) == ("192.0.2.50/24", True)
    assert cfg.cloudinit.contrasena is None
    assert (cfg.encender, cfg.esperar_ip, cfg.plazo_ip_s) == (True, True, 120)
    datos = json.loads((EJEMPLOS / "lote-cloudinit.proxlaunch-lote.json").read_text("utf-8"))
    assert datos["version_formato"] == 4


def test_csv_cloudinit_no_trae_contrasenas_y_usa_las_columnas_de_la_fase_b() -> None:
    res = _importar("mvs-cloudinit.csv")
    assert [a.codigo.value for a in res.avisos] == []  # sin «csv_con_contrasenas» ni otros avisos
    assert "ci_contrasena" not in res.columnas.posiciones
    for columna in ("ci_usuario", "ci_claves", "ci_ip", "ci_puerta", "ci_dns", "esperar_ip"):
        assert columna in res.columnas.posiciones, columna
    parciales = {f.nombre: f.opciones.cloudinit for f in res.filas}
    assert parciales["app-01"].tarjeta0.modo.value == "dhcp"
    assert parciales["app-02"].tarjeta0.ip == "192.0.2.51/24"
    assert all(c.usuario == "ana" and c.contrasena is None for c in parciales.values())
    esperas = {f.nombre: f.opciones.esperar_ip for f in res.filas}
    assert esperas == {"app-01": True, "app-02": True, "app-03": True, "bd-01": False}


def test_lote_por_filas_son_tres_filas() -> None:
    lote = leer_archivo_lote(EJEMPLOS / LOTES[1]).lote
    assert len(lote.definicion.filas) == 3


def test_perfiles_de_ejemplo_se_leen_sin_invalidos() -> None:
    leido = leer_archivo_perfiles(EJEMPLOS / PERFILES)
    assert len(leido.validos) == 2
    assert leido.invalidos == ()
    assert [p.nombre for p in leido.validos][0] == "Servidor web de la oficina"


def test_perfiles_de_ejemplo_hacen_ida_y_vuelta(tmp_path: Path) -> None:
    leido = leer_archivo_perfiles(EJEMPLOS / PERFILES)
    perfiles = [
        PerfilMaquina(
            id=f"usuario.{p.indice}",
            nombre=p.nombre,
            descripcion=p.descripcion,
            origen=OrigenPerfil.USUARIO,
            config=p.config,
        )
        for p in leido.validos
    ]
    copia = tmp_path / "copia.proxlaunch-perfiles.json"
    exportar_perfiles(copia, perfiles, con_pistas=True, app_version="0.0.0")
    otra = leer_archivo_perfiles(copia)
    assert otra.invalidos == ()
    assert [(p.nombre, p.descripcion, p.config) for p in otra.validos] == [
        (p.nombre, p.descripcion, p.config) for p in leido.validos
    ]


# --- 4. Privacidad --------------------------------------------------------------------------

_RE_IP = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_RE_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")  # ``usuario@pve`` (sin punto) no cuenta
_RE_URL = re.compile(r"https?://([^/\s\"']+)")
_RE_SECRETO = re.compile(
    r"(PVEAPIToken|PVEAuthCookie|CSRFPreventionToken|ticket|api[_-]?token|secret|password"
    r"|contrase[nñ]a|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def _archivos_ejemplo() -> list[Path]:
    return sorted(p for p in EJEMPLOS.iterdir() if p.is_file())


def test_hay_los_diecisiete_archivos_esperados() -> None:
    nombres = {p.name for p in _archivos_ejemplo()}
    assert nombres == {"LEEME.md", "mvs-con-errores.csv", *CSV_VALIDOS, *LOTES, PERFILES}


@pytest.mark.parametrize("ruta", _archivos_ejemplo(), ids=lambda p: p.name)
def test_ejemplo_solo_usa_ips_de_documentacion(ruta: Path) -> None:
    texto = ruta.read_text(encoding="utf-8-sig")
    for candidata in _RE_IP.findall(texto):
        ip = ipaddress.ip_address(candidata)
        assert any(ip in red for red in REDES_DOCUMENTACION), candidata


@pytest.mark.parametrize("ruta", _archivos_ejemplo(), ids=lambda p: p.name)
def test_ejemplo_sin_correos_reales_ni_secretos(ruta: Path) -> None:
    texto = ruta.read_text(encoding="utf-8-sig")
    assert _RE_CORREO.findall(texto) == []
    # El LEEME nombra conceptos («contraseña»); en los datos no debe haber secretos.
    if ruta.suffix != ".md":
        assert _RE_SECRETO.findall(texto) == []


@pytest.mark.parametrize("ruta", _archivos_ejemplo(), ids=lambda p: p.name)
def test_ejemplo_solo_usa_dominios_reservados(ruta: Path) -> None:
    texto = ruta.read_text(encoding="utf-8-sig")
    for host in _RE_URL.findall(texto):
        assert host.split(":")[0].lower() in {"example.com", "example.org", "example.net"}, host


# --- 5. Sincronía con el generador de capturas ----------------------------------------------


def _constante_del_escenario(nombre: str) -> str:
    """Valor literal de ``nombre`` en escenario.py, sin importar el módulo (evita Qt)."""
    arbol = ast.parse(ESCENARIO.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == nombre for t in nodo.targets
        ):
            valor = ast.literal_eval(nodo.value)
            assert isinstance(valor, str)
            return valor
    raise AssertionError(f"{nombre} no está definido en escenario.py")


def _normalizar(texto: str) -> str:
    """Sin BOM y con fin de línea LF: el generador escribe LF y el ejemplo lleva CRLF."""
    return texto.removeprefix("﻿").replace("\r\n", "\n")


@pytest.mark.parametrize(
    ("constante", "archivo"),
    [("CSV_MIXTAS", "mvs-mixtas.csv"), ("CSV_CON_ERRORES", "mvs-con-errores.csv")],
)
def test_copia_embebida_del_generador_coincide_con_el_ejemplo(constante: str, archivo: str) -> None:
    ejemplo = _normalizar((EJEMPLOS / archivo).read_bytes().decode("utf-8"))
    assert _constante_del_escenario(constante) == ejemplo


# --- 6. El generador queda fuera de la suite por defecto ------------------------------------


def _pytest_recolectar(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_pyproject_declara_la_marca_y_la_excluye_por_defecto() -> None:
    cfg = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    opciones = cfg["tool"]["pytest"]["ini_options"]
    assert any(m.split(":")[0].strip() == "capturas" for m in opciones["markers"])
    assert '-m "not capturas"' in opciones["addopts"]


def test_las_pruebas_del_generador_llevan_la_marca() -> None:
    fuente = (CAPTURAS / "test_capturas_guia.py").read_text(encoding="utf-8")
    assert re.search(r"^pytestmark\s*=\s*pytest\.mark\.capturas\s*$", fuente, re.MULTILINE)


def test_recoleccion_por_defecto_deselecciona_todo_el_generador() -> None:
    marcadas = _pytest_recolectar("-m", "capturas", str(CAPTURAS))
    assert marcadas.returncode == 0, marcadas.stdout + marcadas.stderr
    total = len(re.findall(r"test_capturas_guia\.py::", marcadas.stdout))
    assert total > 0
    por_defecto = _pytest_recolectar(str(CAPTURAS))
    assert "test_capturas_guia.py::" not in por_defecto.stdout
    assert f"no tests collected ({total} deselected)" in por_defecto.stdout


def test_lote_red_firewall_es_formato_5_con_firewall_y_red_del_clon() -> None:
    leido = leer_archivo_lote(EJEMPLOS / "lote-red-firewall.proxlaunch-lote.json")
    assert leido.avisos == ()
    cfg = leido.lote.definicion.plantilla
    assert cfg.firewall is not None and cfg.firewall.activo
    assert cfg.red_clon is not None
    datos = json.loads((EJEMPLOS / "lote-red-firewall.proxlaunch-lote.json").read_text("utf-8"))
    assert datos["version_formato"] == 5


def test_csv_red_firewall_usa_las_columnas_de_la_fase_c() -> None:
    res = _importar("mvs-red-firewall.csv")
    assert [f.nombre for f in res.filas if f.estado.value == "con_error"] == []
    fw = {f.nombre: f.opciones.firewall for f in res.filas if f.opciones is not None}
    assert fw["lab-01"] is not None and fw["lab-01"].activo is False
    assert fw["web-01"] is not None and fw["web-01"].grupo == "web"


def test_lote_libvirt_es_formato_6_con_dos_discos_y_mac_conservada() -> None:
    leido = leer_archivo_lote(EJEMPLOS / "lote-libvirt.proxlaunch-lote.json")
    assert leido.avisos == ()
    cfg = leido.lote.definicion.plantilla
    assert leido.lote.definicion.cantidad == 1
    assert len(cfg.discos) == 2
    detalle = cfg.detalle_origen
    assert isinstance(detalle, DetalleImportacion)
    assert [o.indice for o in detalle.otras] == [1]  # imagen del segundo disco
    assert cfg.redes[0].mac_conservada == "52:54:00:12:34:56"
    datos = json.loads((EJEMPLOS / "lote-libvirt.proxlaunch-lote.json").read_text("utf-8"))
    assert datos["version_formato"] == 6


def test_csv_hardware_cluster_usa_las_columnas_de_la_fase_d() -> None:
    res = _importar("mvs-hardware-cluster.csv")
    for columna in ("mapeo_pci", "mapeo_usb"):
        assert columna in res.columnas.posiciones, columna
    hw = {f.nombre: f.cfg.hardware_cluster for f in res.filas if f.cfg is not None}
    assert hw["grafico-01"] is not None
    assert [a.mapeo for a in hw["grafico-01"].pci] == ["gpu-ejemplo"]
    assert [a.mapeo for a in hw["grafico-01"].usb] == ["llave-ejemplo"]
    assert hw["licencias-01"] is not None and hw["licencias-01"].pci == ()
    assert hw["doble-gpu-01"] is not None
    assert [a.mapeo for a in hw["doble-gpu-01"].pci] == ["gpu-ejemplo", "gpu-secundaria"]
    cpus = {f.nombre: f.cfg.tipo_cpu for f in res.filas if f.cfg is not None}
    assert cpus["grafico-01"] == "custom-ejemplo"
