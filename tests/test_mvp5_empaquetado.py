"""Pruebas del MVP 5 sobre ``empaquetado/comun`` (version, sumas, iconos, lock, qm, presupuesto,
revisión estática).

Se derivan de ``docs/requisitos/mvp5.md`` (CA-E07.3, E10.1, E10.3, E11.2, E20.1 a E20.3, E21.2,
E30.1, E21.3, E33.1, E35.1, E19.1) y de la interfaz pública de cada script. Los módulos no forman
un paquete instalado, así que se cargan con ``importlib`` desde su ruta. Los archivos reales de
``empaquetado/`` solo se leen: toda alteración se hace en copias temporales.
"""

from __future__ import annotations

import getpass
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

import proxlaunch

RAIZ = Path(__file__).resolve().parents[1]
COMUN = RAIZ / "empaquetado" / "comun"
VARIABLE_LAB = "PROXLAUNCH" + "_LAB"  # se parte para no activar búsquedas textuales ajenas
OPCION_SOCKET = "force-enable" + "-socket"


def _cargar(nombre: str) -> ModuleType:
    """Carga ``empaquetado/comun/<nombre>.py`` como un módulo nuevo (aislado por prueba)."""
    ruta = COMUN / f"{nombre}.py"
    spec = importlib.util.spec_from_file_location(f"mvp5_{nombre}", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def version():
    return _cargar("version")


@pytest.fixture
def sumas():
    return _cargar("sumas")


@pytest.fixture
def iconos():
    return _cargar("iconos")


@pytest.fixture
def lock():
    return _cargar("comprobar_lock")


@pytest.fixture
def qm():
    return _cargar("compilar_qm")


@pytest.fixture
def presupuesto():
    return _cargar("presupuesto")


@pytest.fixture
def estatico():
    return _cargar("revisar_estatico")


# =============================================================================================
# version.py  (RF-E10: CA-E10.1, CA-E10.3)
# =============================================================================================


@pytest.mark.parametrize("v", ["0.5.0", "1.2.3", "10.20.30", "0.0.0", "100.0.1"])
def test_semver_valido_se_acepta(version, v):
    assert version.validar_semver(v) == v


@pytest.mark.parametrize(
    "v",
    ["", "0.5", "1", "1.2.3.4", "1.2.3-rc1", "1.2.3+meta", "01.2.3", "v1.2.3", " 1.2.3", "1.2.x",
     "1..3", "-1.2.3", "a.b.c"],
)  # fmt: skip
def test_semver_invalido_se_rechaza(version, v):
    with pytest.raises(version.ErrorVersion, match="SemVer"):
        version.validar_semver(v)


def test_semver_con_salto_de_linea_final_se_rechaza(version):
    with pytest.raises(version.ErrorVersion):
        version.validar_semver("1.2.3\n")


def _arbol_version(tmp_path, *, init: str, pyproject: str) -> tuple[Path, Path]:
    ini = tmp_path / "__init__.py"
    ini.write_text(init, encoding="utf-8")
    pp = tmp_path / "pyproject.toml"
    pp.write_text(pyproject, encoding="utf-8")
    return ini, pp


PYPROJECT_DINAMICO = (
    '[project]\nname = "x"\ndynamic = ["version"]\n'
    '[tool.setuptools.dynamic]\nversion = {attr = "proxlaunch.__version__"}\n'
)


@pytest.fixture
def version_simulada(version, tmp_path, monkeypatch):
    """Devuelve una función que apunta el módulo a un ``__init__``/pyproject temporales."""

    def preparar(init, pyproject, etiqueta=None):
        ini, pp = _arbol_version(tmp_path, init=init, pyproject=pyproject)
        monkeypatch.setattr(version, "INIT", ini)
        monkeypatch.setattr(version, "PYPROJECT", pp)
        monkeypatch.setattr(version, "etiqueta_de_head", lambda: etiqueta)
        return version

    return preparar


def test_version_del_codigo_coincide_con_el_paquete(version):
    import proxlaunch

    assert version.version_del_codigo() == proxlaunch.__version__ == "0.8.0"


def test_comprobar_acepta_pyproject_dinamico_sin_etiqueta(version_simulada):
    v = version_simulada('__version__ = "0.5.0"\n', PYPROJECT_DINAMICO)
    assert v.comprobar() == "0.5.0"


def test_comprobar_acepta_etiqueta_coincidente(version_simulada):
    v = version_simulada('__version__ = "0.5.0"\n', PYPROJECT_DINAMICO, etiqueta="v0.5.0")
    assert v.comprobar() == "0.5.0"


def test_comprobar_rechaza_etiqueta_distinta(version_simulada):
    v = version_simulada('__version__ = "0.5.0"\n', PYPROJECT_DINAMICO, etiqueta="v0.4.0")
    with pytest.raises(v.ErrorVersion, match="etiquetado como v0.4.0"):
        v.comprobar()


def test_comprobar_rechaza_pyproject_estatico_distinto(version_simulada):
    pp = '[project]\nname = "x"\nversion = "0.4.9"\n'
    v = version_simulada('__version__ = "0.5.0"\n', pp)
    with pytest.raises(v.ErrorVersion, match="0.4.9"):
        v.comprobar()


def test_comprobar_acepta_pyproject_estatico_igual(version_simulada):
    pp = '[project]\nname = "x"\nversion = "0.5.0"\n'
    assert version_simulada('__version__ = "0.5.0"\n', pp).comprobar() == "0.5.0"


def test_comprobar_rechaza_pyproject_sin_version_ni_dinamica(version_simulada):
    v = version_simulada('__version__ = "0.5.0"\n', '[project]\nname = "x"\n')
    with pytest.raises(v.ErrorVersion, match="no fija la versión"):
        v.comprobar()


def test_comprobar_rechaza_version_del_codigo_invalida(version_simulada):
    v = version_simulada('__version__ = "0.5.0-rc1"\n', PYPROJECT_DINAMICO)
    with pytest.raises(v.ErrorVersion, match="SemVer"):
        v.comprobar()


def test_version_sin_dunder_version_falla(version_simulada):
    v = version_simulada("x = 1\n", PYPROJECT_DINAMICO)
    with pytest.raises(v.ErrorVersion, match="no se encontró"):
        v.version_del_codigo()


def test_cli_version_invalida_sale_1_antes_de_construir(version_simulada, capsys):
    """CA-E10.3: una versión no X.Y.Z hace fallar el script (el build lo invoca primero)."""
    v = version_simulada('__version__ = "1.0"\n', PYPROJECT_DINAMICO)
    assert v.main([]) == 1
    assert v.main(["--comprobar"]) == 1
    assert "VERSIÓN:" in capsys.readouterr().err


def test_cli_incoherencia_con_etiqueta_sale_1(version_simulada, capsys):
    v = version_simulada('__version__ = "0.5.0"\n', PYPROJECT_DINAMICO, etiqueta="v9.9.9")
    assert v.main(["--comprobar"]) == 1
    assert "v9.9.9" in capsys.readouterr().err


def test_cli_imprime_version_y_formato_windows(version_simulada, capsys):
    v = version_simulada('__version__ = "0.5.0"\n', PYPROJECT_DINAMICO)
    assert v.main(["--comprobar"]) == 0
    assert capsys.readouterr().out.strip() == "0.5.0"
    assert v.main(["--windows"]) == 0
    assert capsys.readouterr().out.strip() == "0.5.0.0"


def test_repositorio_real_es_coherente(version, monkeypatch):
    """CA-E10.1 sobre el repo real (sin depender de si HEAD está etiquetado)."""
    monkeypatch.setattr(version, "etiqueta_de_head", lambda: None)
    assert version.comprobar() == "0.8.0"


# =============================================================================================
# sumas.py  (RF-E20: CA-E20.1, CA-E20.2, CA-E20.3)
# =============================================================================================


def _artefacto(dist: Path, nombre: str, contenido: bytes) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    ruta = dist / nombre
    ruta.write_bytes(contenido)
    return ruta


def test_publicar_solo_incluye_artefactos_sellados(sumas, tmp_path, capsys):
    dist = tmp_path / "dist"
    deb = _artefacto(dist, f"proxlaunch_{proxlaunch.__version__}_amd64.deb", b"deb-contenido")
    _artefacto(
        dist, f"proxlaunch-{proxlaunch.__version__}-windows-x64-setup.exe", b"exe-sin-verificar"
    )
    sumas.sellar(deb)
    assert sumas.publicar(dist) == 1  # hay uno sin sello
    texto = (dist / "SHA256SUMS").read_text("utf-8")
    assert f"proxlaunch_{proxlaunch.__version__}_amd64.deb" in texto
    assert "setup.exe" not in texto
    assert "sin verificación vigente" in capsys.readouterr().err


def test_publicar_todos_sellados_devuelve_0(sumas, tmp_path):
    dist = tmp_path / "dist"
    for nombre in ("a.deb", "b-setup.exe"):
        sumas.sellar(_artefacto(dist, nombre, nombre.encode()))
    assert sumas.publicar(dist) == 0
    lineas = (dist / "SHA256SUMS").read_text("utf-8").splitlines()
    assert len(lineas) == 2


def test_un_byte_alterado_tras_sellar_no_se_publica(sumas, tmp_path):
    """CA-E20.2: si el artefacto cambia después de verificarse, su suma no se publica."""
    dist = tmp_path / "dist"
    deb = _artefacto(dist, "a.deb", b"contenido-original")
    sumas.sellar(deb)
    deb.write_bytes(b"contenido-originaL")  # un byte distinto
    assert sumas.publicar(dist) == 1
    assert not (dist / "SHA256SUMS").exists()


def test_comprobar_rechaza_un_byte_alterado_tras_publicar(sumas, tmp_path):
    dist = tmp_path / "dist"
    deb = _artefacto(dist, "a.deb", b"\x00" * 1000)
    sumas.sellar(deb)
    assert sumas.publicar(dist) == 0
    assert sumas.comprobar(dist) == 0
    datos = bytearray(deb.read_bytes())
    datos[500] ^= 0x01
    deb.write_bytes(bytes(datos))
    assert sumas.comprobar(dist) == 1


def test_comprobar_falla_si_el_artefacto_desaparece(sumas, tmp_path):
    dist = tmp_path / "dist"
    deb = _artefacto(dist, "a.deb", b"x")
    sumas.sellar(deb)
    sumas.publicar(dist)
    deb.unlink()
    assert sumas.comprobar(dist) == 1


def test_comprobar_sin_sha256sums_falla(sumas, tmp_path, capsys):
    assert sumas.comprobar(tmp_path) == 1
    assert "no hay SHA256SUMS" in capsys.readouterr().err


def test_comprobar_rechaza_nombres_con_ruta(sumas, tmp_path, capsys):
    (tmp_path / "SHA256SUMS").write_text(f"{'0' * 64}  dist/a.deb\n", encoding="utf-8")
    assert sumas.comprobar(tmp_path) == 1
    assert "nombre con ruta" in capsys.readouterr().err


def test_sello_corrupto_no_habilita_la_publicacion(sumas, tmp_path):
    dist = tmp_path / "dist"
    deb = _artefacto(dist, "a.deb", b"x")
    sumas.ruta_sello(deb).write_text("no-es-una-suma  a.deb\n", encoding="utf-8")
    assert sumas.publicar(dist) == 1
    assert not (dist / "SHA256SUMS").exists()


def test_los_provisionales_no_se_sellan_ni_se_publican(sumas, tmp_path):
    dist = tmp_path / "dist"
    prov = _artefacto(dist / "provisional", "a.deb", b"x")
    with pytest.raises(SystemExit, match="provisionales"):
        sumas.sellar(prov)
    assert sumas.publicar(dist) == 0
    assert not (dist / "SHA256SUMS").exists()


def test_sellar_artefacto_inexistente_falla(sumas, tmp_path):
    with pytest.raises(SystemExit, match="no existe"):
        sumas.sellar(tmp_path / "no-existe.deb")


def test_publicar_borra_un_sha256sums_obsoleto_si_no_queda_nada(sumas, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "SHA256SUMS").write_text("viejo\n", encoding="utf-8")
    assert sumas.publicar(dist) == 0
    assert not (dist / "SHA256SUMS").exists()


def test_archivos_ocultos_y_otras_extensiones_no_son_artefactos(sumas, tmp_path):
    dist = tmp_path / "dist"
    _artefacto(dist, ".oculto.deb", b"x")
    _artefacto(dist, "notas.txt", b"x")
    _artefacto(dist, "a.deb", b"x")
    assert [p.name for p in sumas.artefactos(dist)] == ["a.deb"]


def test_sha256_coincide_con_hashlib(sumas, tmp_path):
    ruta = tmp_path / "f.bin"
    contenido = bytes(range(256)) * 5000  # más de un bloque de lectura
    ruta.write_bytes(contenido)
    assert sumas.sha256(ruta) == hashlib.sha256(contenido).hexdigest()


def test_sha256sums_sin_rutas_ni_usuario_y_formato_estricto(sumas, tmp_path):
    """CA-E20.3: solo «suma␠␠nombre», sin separadores de ruta ni nombre de usuario."""
    dist = tmp_path / "dist"
    for nombre in (
        f"proxlaunch_{proxlaunch.__version__}_amd64.deb",
        f"proxlaunch-{proxlaunch.__version__}-windows-x64-setup.exe",
    ):
        sumas.sellar(_artefacto(dist, nombre, nombre.encode()))
    sumas.publicar(dist)
    # Se leen los bytes: read_text() traduciría CRLF a LF y ocultaría el fallo en Windows.
    texto = (dist / "SHA256SUMS").read_bytes().decode("utf-8")
    for linea in texto.splitlines():
        assert re.fullmatch(r"[0-9a-f]{64}  [^/\\\s]+", linea), linea
    assert getpass.getuser() not in texto
    assert str(tmp_path) not in texto
    assert "/home/" not in texto and "\\Users\\" not in texto
    assert "\r" not in texto and texto.endswith("\n")


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="requiere sha256sum de coreutils")
def test_sha256sums_es_verificable_con_sha256sum(sumas, tmp_path):
    """CA-E20.1: ``sha256sum -c SHA256SUMS`` da OK; con un byte alterado, falla."""
    dist = tmp_path / "dist"
    deb = _artefacto(dist, "a.deb", b"abc" * 100)
    sumas.sellar(deb)
    sumas.publicar(dist)
    ok = subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"], cwd=dist, capture_output=True, text=True, check=False
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "a.deb: OK" in ok.stdout
    deb.write_bytes(b"abc" * 99 + b"abd")
    mal = subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"], cwd=dist, capture_output=True, text=True, check=False
    )
    assert mal.returncode != 0


def test_cli_sellar_publicar_comprobar(sumas, tmp_path, capsys):
    dist = tmp_path / "dist"
    deb = _artefacto(dist, "a.deb", b"x")
    assert sumas.main(["sellar", str(deb)]) == 0
    assert sumas.main(["publicar", "--dist", str(dist)]) == 0
    assert sumas.main(["comprobar", "--dist", str(dist)]) == 0
    assert "a.deb: OK" in capsys.readouterr().out


# =============================================================================================
# iconos.py  (RF-E11: CA-E11.2; copiar / verificar / aprobar)
# =============================================================================================


@pytest.fixture
def iconos_copia(iconos, tmp_path, monkeypatch):
    """``iconos`` apuntando a COPIAS temporales de empaquetado/iconos y del JSON de aprobación."""
    versionados = tmp_path / "versionados"
    shutil.copytree(iconos.VERSIONADOS, versionados)
    aprobados = tmp_path / "iconos-aprobados.json"
    shutil.copyfile(iconos.APROBADOS, aprobados)
    monkeypatch.setattr(iconos, "VERSIONADOS", versionados)
    monkeypatch.setattr(iconos, "APROBADOS", aprobados)
    return iconos


def _alterar_un_byte(ruta: Path, posicion: int = -10) -> None:
    datos = bytearray(ruta.read_bytes())
    datos[posicion] ^= 0x01
    ruta.write_bytes(bytes(datos))


def test_iconos_reales_estan_aprobados_y_completos(iconos):
    sumas = iconos.comprobar_versionados()
    assert set(sumas) == set(iconos.NOMBRES)
    assert len(iconos.NOMBRES) == 8


def test_ico_contiene_16_32_48_y_256(iconos):
    """CA-E11.2."""
    lados = iconos.leer_tamanos_ico(iconos.VERSIONADOS / "proxlaunch.ico")
    assert {16, 32, 48, 256} <= set(lados)


def test_cada_png_mide_lo_que_dice_su_nombre(iconos):
    for lado in iconos.TAMANOS_PNG:
        datos = (iconos.VERSIONADOS / f"proxlaunch-{lado}.png").read_bytes()
        assert iconos._lado_png(datos) == lado


def test_leer_tamanos_ico_rechaza_un_archivo_que_no_es_ico(iconos, tmp_path):
    falso = tmp_path / "falso.ico"
    falso.write_bytes(b"\x00\x00\x02\x00\x01\x00" + b"\x00" * 20)  # tipo 2 = cursor
    with pytest.raises(ValueError, match="no es un .ico"):
        iconos.leer_tamanos_ico(falso)


def test_escribir_ico_y_leerlo_conserva_los_tamanos(iconos, tmp_path):
    destino = tmp_path / "x.ico"
    iconos.escribir_ico([(16, b"a"), (48, b"bb"), (256, b"ccc")], destino)
    assert iconos.leer_tamanos_ico(destino) == [16, 48, 256]


def test_copiar_deja_los_archivos_aprobados_identicos(iconos_copia, tmp_path, capsys):
    salida = tmp_path / "build" / "iconos"
    assert iconos_copia.copiar(salida) == 0
    for nombre in iconos_copia.NOMBRES:
        assert (salida / nombre).read_bytes() == (iconos_copia.VERSIONADOS / nombre).read_bytes()
    assert "verificados y copiados" in capsys.readouterr().out


def test_verificar_acepta_lo_copiado(iconos_copia, tmp_path):
    salida = tmp_path / "salida"
    iconos_copia.copiar(salida)
    assert iconos_copia.verificar(salida, provisional=False) == 0


def test_verificar_rechaza_un_byte_alterado_en_la_salida(iconos_copia, tmp_path, capsys):
    salida = tmp_path / "salida"
    iconos_copia.copiar(salida)
    _alterar_un_byte(salida / "proxlaunch-48.png")
    assert iconos_copia.verificar(salida, provisional=False) == 1
    assert "no coincide" in capsys.readouterr().err


def test_verificar_rechaza_una_salida_incompleta(iconos_copia, tmp_path):
    salida = tmp_path / "salida"
    iconos_copia.copiar(salida)
    (salida / "proxlaunch.ico").unlink()
    assert iconos_copia.verificar(salida, provisional=False) == 1


def test_copiar_falla_si_se_altera_un_png_versionado(iconos_copia, tmp_path):
    _alterar_un_byte(iconos_copia.VERSIONADOS / "proxlaunch-32.png")
    with pytest.raises(RuntimeError, match=r"proxlaunch-32\.png.*no coincide"):
        iconos_copia.copiar(tmp_path / "salida")
    assert not (tmp_path / "salida" / "proxlaunch-32.png").exists()


def test_cli_copiar_con_png_alterado_sale_1_con_mensaje(iconos_copia, tmp_path, capsys):
    _alterar_un_byte(iconos_copia.VERSIONADOS / "proxlaunch-256.png")
    assert iconos_copia.main(["copiar", "--salida", str(tmp_path / "s")]) == 1
    assert "ICONOS:" in capsys.readouterr().err


def test_falla_si_falta_un_icono_aprobado(iconos_copia):
    (iconos_copia.VERSIONADOS / "proxlaunch-24.png").unlink()
    with pytest.raises(RuntimeError, match="falta el icono aprobado"):
        iconos_copia.comprobar_versionados()


def test_falla_si_sha256sums_no_lista_exactamente_los_esperados(iconos_copia):
    ruta = iconos_copia.VERSIONADOS / "SHA256SUMS"
    lineas = ruta.read_text("utf-8").splitlines()
    ruta.write_text("\n".join(lineas[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="debe listar exactamente"):
        iconos_copia.comprobar_versionados()


def test_falla_si_el_ico_pierde_tamanos(iconos_copia):
    ruta = iconos_copia.VERSIONADOS / "proxlaunch.ico"
    iconos_copia.escribir_ico([(16, b"a"), (32, b"b")], ruta)
    # El SHA256SUMS ya no coincide con el .ico nuevo: se detecta de todos modos.
    with pytest.raises(RuntimeError):
        iconos_copia.comprobar_versionados()


def test_sin_aprobacion_copiar_falla_y_verificar_provisional_avisa(iconos_copia, capsys):
    registro = json.loads(iconos_copia.APROBADOS.read_text("utf-8"))
    registro["estado"] = "pendiente"
    iconos_copia.APROBADOS.write_text(json.dumps(registro), encoding="utf-8")
    with pytest.raises(RuntimeError, match="aún no están aprobados"):
        iconos_copia.comprobar_versionados()
    assert iconos_copia.verificar(Path("no-importa"), provisional=True) == 0
    assert "PROVISIONAL" in capsys.readouterr().out
    with pytest.raises(RuntimeError):
        iconos_copia.verificar(Path("no-importa"), provisional=False)


def test_falla_si_el_json_de_aprobacion_no_refleja_las_sumas(iconos_copia):
    registro = json.loads(iconos_copia.APROBADOS.read_text("utf-8"))
    registro["archivos_sha256"]["proxlaunch-16.png"] = "0" * 64
    iconos_copia.APROBADOS.write_text(json.dumps(registro), encoding="utf-8")
    with pytest.raises(RuntimeError, match="no refleja"):
        iconos_copia.comprobar_versionados()


def test_falla_si_el_svg_fuente_cambio_desde_la_aprobacion(iconos_copia):
    registro = json.loads(iconos_copia.APROBADOS.read_text("utf-8"))
    registro["svg_sha256"] = "f" * 64
    iconos_copia.APROBADOS.write_text(json.dumps(registro), encoding="utf-8")
    with pytest.raises(RuntimeError, match="SVG fuente cambió"):
        iconos_copia.comprobar_versionados()


def test_aprobar_registra_en_las_copias_y_no_toca_los_reales(iconos_copia, iconos, tmp_path):
    reales_antes = {
        n: hashlib.sha256((RAIZ / "empaquetado" / "iconos" / n).read_bytes()).hexdigest()
        for n in iconos.NOMBRES
    }
    json_real = (COMUN / "iconos-aprobados.json").read_bytes()
    # Una propuesta nueva con un PNG distinto (mismo tamaño de cabecera) en una carpeta temporal.
    propuesta = tmp_path / "propuesta"
    shutil.copytree(iconos_copia.VERSIONADOS, propuesta)
    _alterar_un_byte(propuesta / "proxlaunch-64.png")
    assert iconos_copia.aprobar(propuesta) == 0
    nuevas = json.loads(iconos_copia.APROBADOS.read_text("utf-8"))["archivos_sha256"]
    assert (
        nuevas["proxlaunch-64.png"]
        == hashlib.sha256((propuesta / "proxlaunch-64.png").read_bytes()).hexdigest()
    )
    assert iconos_copia.comprobar_versionados()  # la copia queda coherente
    # Los archivos reales siguen intactos.
    for n, suma in reales_antes.items():
        real = RAIZ / "empaquetado" / "iconos" / n
        assert hashlib.sha256(real.read_bytes()).hexdigest() == suma
    assert (COMUN / "iconos-aprobados.json").read_bytes() == json_real


def test_aprobar_desde_una_propuesta_incompleta_falla(iconos_copia, tmp_path):
    propuesta = tmp_path / "propuesta"
    propuesta.mkdir()
    with pytest.raises(RuntimeError, match="falta"):
        iconos_copia.aprobar(propuesta)


def test_leer_sumas_rechaza_lineas_con_ruta(iconos, tmp_path):
    (tmp_path / "SHA256SUMS").write_text(f"{'a' * 64}  sub/x.png\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no válida"):
        iconos.leer_sumas(tmp_path)


# =============================================================================================
# comprobar_lock.py  (RF-E21: CA-E21.2)
# =============================================================================================


@pytest.fixture
def lock_copia(lock, tmp_path, monkeypatch):
    requisitos = tmp_path / "requisitos"
    shutil.copytree(lock.REQUISITOS, requisitos)
    pyproject = tmp_path / "pyproject.toml"
    shutil.copyfile(lock.PYPROJECT, pyproject)
    monkeypatch.setattr(lock, "REQUISITOS", requisitos)
    monkeypatch.setattr(lock, "PYPROJECT", pyproject)
    return lock


def test_lock_real_es_coherente(lock):
    assert lock.comprobar() == []


def test_lock_copia_sin_cambios_es_coherente(lock_copia):
    assert lock_copia.comprobar() == []
    assert lock_copia.main([]) == 0


def test_dependencia_nueva_en_pyproject_sin_regenerar_falla(lock_copia, capsys):
    """CA-E21.2."""
    texto = lock_copia.PYPROJECT.read_text("utf-8")
    nuevo = re.sub(r"(dependencies\s*=\s*\[)", r'\1\n  "paquete-nuevo>=1.0",', texto, count=1)
    assert nuevo != texto
    lock_copia.PYPROJECT.write_text(nuevo, encoding="utf-8")
    problemas = lock_copia.comprobar()
    assert any("ejecucion.in no coincide" in p and "paquete-nuevo" in p for p in problemas)
    assert lock_copia.main([]) == 1
    assert "LOCK:" in capsys.readouterr().err


def test_cambio_en_el_in_sin_regenerar_el_lock_falla(lock_copia):
    ruta = lock_copia.REQUISITOS / "ejecucion.in"
    ruta.write_text(ruta.read_text("utf-8") + "otro-paquete>=2\n", encoding="utf-8")
    problemas = lock_copia.comprobar()
    assert any("desactualizado" in p for p in problemas)
    assert any("linux-ejecucion.txt" in p for p in problemas)
    assert any("windows-ejecucion.txt" in p for p in problemas)


def test_dependencia_de_desarrollo_cambiada_falla(lock_copia):
    texto = lock_copia.PYPROJECT.read_text("utf-8")
    nuevo = re.sub(r"(dev\s*=\s*\[)", r'\1\n  "herramienta-nueva",', texto, count=1)
    assert nuevo != texto
    lock_copia.PYPROJECT.write_text(nuevo, encoding="utf-8")
    assert any("calidad.in no coincide" in p for p in lock_copia.comprobar())


def test_lockfile_ausente_se_reporta(lock_copia):
    (lock_copia.REQUISITOS / "linux-calidad.txt").unlink()
    assert any("falta linux-calidad.txt" in p for p in lock_copia.comprobar())


def test_paquete_sin_hash_se_reporta(lock_copia):
    ruta = lock_copia.REQUISITOS / "linux-ejecucion.txt"
    texto = ruta.read_text("utf-8")
    sin_hashes = re.sub(r"\s*--hash=sha256:[0-9a-f]+\s*\\?", " ", texto)
    assert sin_hashes != texto
    ruta.write_text(sin_hashes, encoding="utf-8")
    assert any("no tiene hash" in p for p in lock_copia.comprobar())


def test_cambio_de_comentarios_en_el_in_no_invalida_el_lock(lock_copia):
    ruta = lock_copia.REQUISITOS / "ejecucion.in"
    ruta.write_text("# comentario nuevo\n" + ruta.read_text("utf-8"), encoding="utf-8")
    assert lock_copia.comprobar() == []


# =============================================================================================
# compilar_qm.py  (RF-E07: CA-E07.3)
# =============================================================================================

TS_VALIDO = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="es_ES">
<context>
    <name>Prueba</name>
    <message><source>Hello</source><translation>Hola</translation></message>
    <message><source>Bye</source><translation type="unfinished"></translation></message>
</context>
</TS>
"""


def test_ts_con_xml_invalido_falla_con_mensaje_claro(qm, tmp_path, capsys):
    """CA-E07.3."""
    ts = tmp_path / "roto.ts"
    ts.write_text("<TS><context><message></TS>", encoding="utf-8")
    destino = tmp_path / "roto.qm"
    with pytest.raises(RuntimeError, match=r"roto\.ts no es XML válido"):
        qm.compilar(ts, destino)
    assert qm.main(["--ts", str(ts), "--qm", str(destino)]) == 1
    err = capsys.readouterr().err
    assert "TRADUCCIONES:" in err and "XML" in err
    assert not destino.exists()


def test_ts_inexistente_falla(qm, tmp_path):
    with pytest.raises(RuntimeError, match="no existe el catálogo"):
        qm.compilar(tmp_path / "nada.ts", tmp_path / "nada.qm")


def test_ts_vacio_falla(qm, tmp_path):
    ts = tmp_path / "vacio.ts"
    ts.write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="XML válido"):
        qm.compilar(ts, tmp_path / "vacio.qm")


def test_ts_invalido_borra_nada_previo_pero_no_deja_un_qm_nuevo(qm, tmp_path):
    ts = tmp_path / "roto.ts"
    ts.write_text("no es xml", encoding="utf-8")
    with pytest.raises(RuntimeError):
        qm.compilar(ts, tmp_path / "sub" / "roto.qm")
    assert not (tmp_path / "sub" / "roto.qm").exists()


def test_contar_mensajes_ignora_los_no_terminados(qm, tmp_path):
    ts = tmp_path / "ok.ts"
    ts.write_text(TS_VALIDO, encoding="utf-8")
    assert qm.contar_mensajes(ts) == (2, 1)


def test_ts_valido_compila_a_un_qm_no_vacio_y_cargable(qm, tmp_path, capsys):
    from PySide6.QtCore import QTranslator

    ts = tmp_path / "ok.ts"
    ts.write_text(TS_VALIDO, encoding="utf-8")
    destino = tmp_path / "ok.qm"
    assert qm.main(["--ts", str(ts), "--qm", str(destino)]) == 0
    assert destino.stat().st_size > 0
    traductor = QTranslator()
    assert traductor.load(str(destino))
    assert traductor.translate("Prueba", "Hello") == "Hola"
    assert "1 de 2 mensajes traducidos" in capsys.readouterr().out


def test_catalogo_real_compila_en_una_carpeta_temporal(qm, tmp_path):
    destino = tmp_path / "proxlaunch_es.qm"
    assert qm.main(["--qm", str(destino)]) == 0
    assert destino.stat().st_size > 0


def test_catalogo_sin_traducciones_avisa(qm, tmp_path, capsys):
    ts = tmp_path / "sin.ts"
    ts.write_text(TS_VALIDO.replace("Hola", ""), encoding="utf-8")
    assert qm.main(["--ts", str(ts), "--qm", str(tmp_path / "sin.qm")]) == 0
    assert "AVISO" in capsys.readouterr().out


# =============================================================================================
# presupuesto.py  (RF-E19: tolerancia del 10 %)
# =============================================================================================

MB = 1024 * 1024


@pytest.fixture
def limites():
    return tomllib.loads((COMUN / "presupuesto.toml").read_text("utf-8"))


def _hueco(ruta: Path, mb: float) -> Path:
    """Archivo disperso (sparse) con el tamaño dado, sin gastar disco."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("wb") as f:
        f.truncate(int(mb * MB))
    return ruta


def _ejecutar(presupuesto, plataforma, tmp_path, artefacto_mb, instalado_mb):
    art = _hueco(tmp_path / "artefacto.bin", artefacto_mb)
    arbol = tmp_path / "instalado"
    _hueco(arbol / "bin" / "a.bin", instalado_mb / 2)
    _hueco(arbol / "lib" / "b.bin", instalado_mb / 2)
    return presupuesto.main([plataforma, str(art), str(arbol)])


@pytest.mark.parametrize("plataforma", ["linux", "windows"])
def test_dentro_del_presupuesto_pasa(presupuesto, limites, tmp_path, capsys, plataforma):
    lim = limites[plataforma]
    rc = _ejecutar(
        presupuesto, plataforma, tmp_path, lim["artefacto_mb"] * 0.5, lim["instalado_mb"] * 0.5
    )
    assert rc == 0
    assert "EXCEDE" not in capsys.readouterr().out


@pytest.mark.parametrize("plataforma", ["linux", "windows"])
def test_hasta_un_10_por_ciento_por_encima_pasa_con_aviso(
    presupuesto, limites, tmp_path, capsys, plataforma
):
    lim = limites[plataforma]
    tol = 1 + limites["tolerancia_porcentaje"] / 100
    rc = _ejecutar(
        presupuesto, plataforma, tmp_path, lim["artefacto_mb"] * (tol - 0.02), lim["instalado_mb"]
    )
    assert rc == 0
    assert "DENTRO DE LA TOLERANCIA" in capsys.readouterr().out


@pytest.mark.parametrize("plataforma", ["linux", "windows"])
def test_artefacto_mas_de_10_por_ciento_por_encima_falla(
    presupuesto, limites, tmp_path, capsys, plataforma
):
    lim = limites[plataforma]
    tol = 1 + limites["tolerancia_porcentaje"] / 100
    rc = _ejecutar(
        presupuesto,
        plataforma,
        tmp_path,
        lim["artefacto_mb"] * (tol + 0.02),
        lim["instalado_mb"] * 0.5,
    )
    assert rc == 1
    assert "EXCEDE" in capsys.readouterr().out


@pytest.mark.parametrize("plataforma", ["linux", "windows"])
def test_instalado_mas_de_10_por_ciento_por_encima_falla(
    presupuesto, limites, tmp_path, capsys, plataforma
):
    lim = limites[plataforma]
    tol = 1 + limites["tolerancia_porcentaje"] / 100
    rc = _ejecutar(
        presupuesto,
        plataforma,
        tmp_path,
        lim["artefacto_mb"] * 0.5,
        lim["instalado_mb"] * (tol + 0.02),
    )
    assert rc == 1
    assert "EXCEDE" in capsys.readouterr().out


def test_exactamente_en_el_limite_de_tolerancia_pasa(presupuesto, limites, tmp_path):
    lim = limites["linux"]
    tol = 1 + limites["tolerancia_porcentaje"] / 100
    rc = _ejecutar(
        presupuesto, "linux", tmp_path, lim["artefacto_mb"] * tol, lim["instalado_mb"] * 0.5
    )
    assert rc == 0


def test_argumentos_incorrectos_devuelven_2(presupuesto, tmp_path):
    assert presupuesto.main([]) == 2
    assert presupuesto.main(["macos", str(tmp_path), str(tmp_path)]) == 2
    assert presupuesto.main(["linux", str(tmp_path)]) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="enlaces simbólicos: requiere POSIX")
def test_tamano_arbol_no_sigue_enlaces(presupuesto, tmp_path):
    arbol = tmp_path / "arbol"
    _hueco(arbol / "a.bin", 3)
    (arbol / "enlace").symlink_to(_hueco(tmp_path / "fuera.bin", 100))
    assert presupuesto.tamano_arbol(arbol) == 3 * MB


# =============================================================================================
# revisar_estatico.py  (RF-E30, RF-E33, RF-E35; CA-E30.1, E21.3, E33.1, E35.1)
# =============================================================================================


@pytest.fixture
def repo_copia(estatico, tmp_path):
    """Copia mínima del repo (``empaquetado/`` y ``.github/``) para introducir defectos."""
    raiz = tmp_path / "repo"
    shutil.copytree(
        RAIZ / "empaquetado", raiz / "empaquetado", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(RAIZ / ".github", raiz / ".github")
    return raiz


def _problemas(estatico, raiz):
    return estatico.revisar(raiz)


def test_el_repositorio_real_pasa_la_revision(estatico):
    assert estatico.revisar(RAIZ) == []


def test_la_copia_sin_defectos_pasa(estatico, repo_copia):
    assert _problemas(estatico, repo_copia) == []


def test_main_sale_0_sobre_el_repo_y_1_con_defecto(estatico, repo_copia, capsys):
    assert estatico.main(["--raiz", str(repo_copia)]) == 0
    (repo_copia / "empaquetado" / "malo.sh").write_text("#!/bin/sh\nset -x\n", encoding="utf-8")
    assert estatico.main(["--raiz", str(repo_copia)]) == 1
    err = capsys.readouterr().err
    assert "malo.sh:2" in err and "incumplimiento" in err


def test_detecta_set_x(estatico, repo_copia):
    (repo_copia / "empaquetado" / "malo.sh").write_text("#!/bin/sh\nset -x\n", encoding="utf-8")
    p = _problemas(estatico, repo_copia)
    assert any("CA-E35.1" in x and "malo.sh:2" in x and "set -x" in x for x in p), p


@pytest.mark.parametrize("linea", ["set -ex", "set -o xtrace", "bash -x script.sh"])
def test_detecta_otras_variantes_de_traza_del_shell(estatico, repo_copia, linea):
    (repo_copia / "empaquetado" / "malo.sh").write_text(f"#!/bin/sh\n{linea}\n", encoding="utf-8")
    assert any("CA-E35.1" in x for x in _problemas(estatico, repo_copia))


def test_detecta_set_psdebug_trace(estatico, repo_copia):
    (repo_copia / "empaquetado" / "malo.ps1").write_text("Set-PSDebug -Trace 1\n", encoding="utf-8")
    p = _problemas(estatico, repo_copia)
    assert any("CA-E35.1" in x and "malo.ps1:1" in x and "PowerShell" in x for x in p), p


def test_un_comentario_con_set_x_no_es_defecto(estatico, repo_copia):
    (repo_copia / "empaquetado" / "ok.sh").write_text(
        "#!/bin/sh\n# no usar set -x aquí\n", encoding="utf-8"
    )
    assert _problemas(estatico, repo_copia) == []


@pytest.mark.parametrize("linea", ["printenv", "env | sort", "export -p"])
def test_detecta_volcados_del_entorno(estatico, repo_copia, linea):
    (repo_copia / "empaquetado" / "malo.sh").write_text(f"#!/bin/sh\n{linea}\n", encoding="utf-8")
    assert any("volcado del entorno" in x for x in _problemas(estatico, repo_copia))


def test_detecta_get_childitem_env(estatico, repo_copia):
    (repo_copia / "empaquetado" / "malo.ps1").write_text("Get-ChildItem Env:\n", encoding="utf-8")
    assert any("volcado Env" in x for x in _problemas(estatico, repo_copia))


def test_detecta_variable_de_laboratorio_fuera_de_la_guarda(estatico, repo_copia):
    """CA-E33.1."""
    (repo_copia / "empaquetado" / "malo.sh").write_text(
        f"#!/bin/sh\nexport {VARIABLE_LAB}=1\n", encoding="utf-8"
    )
    p = _problemas(estatico, repo_copia)
    assert any("CA-E33.1" in x and "malo.sh:2" in x for x in p), p


def test_detecta_variable_de_laboratorio_en_powershell(estatico, repo_copia):
    (repo_copia / "empaquetado" / "malo.ps1").write_text(
        f"$env:{VARIABLE_LAB} = '1'\n", encoding="utf-8"
    )
    assert any("CA-E33.1" in x for x in _problemas(estatico, repo_copia))


def test_la_guarda_que_prohibe_la_variable_no_es_defecto(estatico, repo_copia):
    (repo_copia / "empaquetado" / "guarda.sh").write_text(
        "#!/bin/sh\n"
        f'if [ -n "${{{VARIABLE_LAB}:-}}" ]; then echo "{VARIABLE_LAB} definida" >&2; fi\n',
        encoding="utf-8",
    )
    assert _problemas(estatico, repo_copia) == []


def test_detecta_la_opcion_que_habilita_sockets(estatico, repo_copia):
    (repo_copia / "empaquetado" / "malo.sh").write_text(
        f"#!/bin/sh\npytest --{OPCION_SOCKET}\n", encoding="utf-8"
    )
    assert any("CA-E33.1" in x and "sockets" in x for x in _problemas(estatico, repo_copia))


def test_calidad_sin_el_filtro_not_integracion_se_detecta(estatico, repo_copia):
    ruta = repo_copia / "empaquetado" / "calidad.sh"
    ruta.write_text(ruta.read_text("utf-8").replace("not integracion", "todas"), encoding="utf-8")
    assert any("not integracion" in x for x in _problemas(estatico, repo_copia))


def test_detecta_un_archivo_de_ci_activo(estatico, repo_copia):
    """CA-E30.1: solo se permite .github/workflows/empaquetado.yml."""
    flujo = repo_copia / ".github" / "workflows" / "x.yml"
    flujo.write_text("name: x\n", encoding="utf-8")
    p = _problemas(estatico, repo_copia)
    assert any("CA-E30.1" in x and ".github/workflows/x.yml" in x for x in p), p


@pytest.mark.parametrize("nombre", [".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"])
def test_detecta_otros_proveedores_de_ci(estatico, repo_copia, nombre):
    (repo_copia / nombre).write_text("x\n", encoding="utf-8")
    assert any("CA-E30.1" in x for x in _problemas(estatico, repo_copia))


def _editar_plantilla(repo, buscar, reemplazo):
    ruta = repo / ".github" / "workflows" / "empaquetado.yml"
    texto = ruta.read_text("utf-8")
    assert buscar in texto
    ruta.write_text(texto.replace(buscar, reemplazo, 1), encoding="utf-8")


def test_detecta_una_accion_con_main(estatico, repo_copia):
    """CA-E21.3."""
    _editar_plantilla(
        repo_copia,
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/checkout@main",
    )
    p = _problemas(estatico, repo_copia)
    assert any("CA-E21.3" in x and "etiqueta móvil" in x for x in p), p


def test_detecta_una_accion_sin_sha(estatico, repo_copia):
    _editar_plantilla(
        repo_copia,
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/checkout@abc123",
    )
    assert any("sin fijar por SHA" in x for x in _problemas(estatico, repo_copia))


def test_detecta_permiso_de_escritura_en_la_plantilla(estatico, repo_copia):
    _editar_plantilla(repo_copia, "contents: read", "contents: write")
    assert any("CA-E35.1" in x for x in _problemas(estatico, repo_copia))


def test_detecta_secretos_en_la_plantilla(estatico, repo_copia):
    _editar_plantilla(
        repo_copia, "persist-credentials: false", "persist-credentials: ${{ secrets.TOKEN }}"
    )
    assert any("no debe usar secretos" in x for x in _problemas(estatico, repo_copia))


def test_detecta_paso_que_no_invoca_empaquetado(estatico, repo_copia):
    _editar_plantilla(repo_copia, "run: bash empaquetado/construir-linux.sh", "run: pytest -q")
    assert any("solo invoca empaquetado/" in x for x in _problemas(estatico, repo_copia))


def test_falta_del_flujo_se_reporta(estatico, repo_copia):
    (repo_copia / ".github" / "workflows" / "empaquetado.yml").unlink()
    assert any("falta el flujo" in x for x in _problemas(estatico, repo_copia))


def test_detecta_disparo_por_pull_request(estatico, repo_copia):
    _editar_plantilla(
        repo_copia, "  workflow_dispatch:\n", "  workflow_dispatch:\n  pull_request:\n"
    )
    assert any("CA-E30.2" in x and "pull_request" in x for x in _problemas(estatico, repo_copia))


def test_detecta_disparo_por_ramas(estatico, repo_copia):
    _editar_plantilla(repo_copia, "    tags: ['v*']\n", "    branches: [main]\n    tags: ['v*']\n")
    assert any("por ramas" in x for x in _problemas(estatico, repo_copia))


def test_detecta_falta_de_disparo_manual(estatico, repo_copia):
    _editar_plantilla(repo_copia, "  workflow_dispatch:\n", "")
    assert any("workflow_dispatch" in x for x in _problemas(estatico, repo_copia))


def test_detecta_secreto_literal(estatico, repo_copia):
    (repo_copia / "empaquetado" / "malo.sh").write_text(
        '#!/bin/sh\nPASSWORD="hunter2hunter2"\n', encoding="utf-8"
    )
    assert any("secreto literal" in x for x in _problemas(estatico, repo_copia))


def test_detecta_certificado_en_el_repo(estatico, repo_copia):
    (repo_copia / "empaquetado" / "firma.pfx").write_bytes(b"x")
    assert any("CA-E24.2" in x for x in _problemas(estatico, repo_copia))


def test_detecta_publicacion_externa(estatico, repo_copia):
    (repo_copia / "empaquetado" / "malo.sh").write_text(
        "#!/bin/sh\ngh release create v1\n", encoding="utf-8"
    )
    assert any("CA-E23.4" in x for x in _problemas(estatico, repo_copia))


def test_detecta_ps1_con_acentos_sin_bom(estatico, repo_copia):
    (repo_copia / "empaquetado" / "acento.ps1").write_bytes("# acción\nWrite-Host 'x'\n".encode())
    assert any("BOM" in x for x in _problemas(estatico, repo_copia))


def test_herramientas_con_url_http_se_rechazan(estatico, repo_copia):
    ruta = repo_copia / "empaquetado" / "entornos" / "windows" / "herramientas.json"
    if not ruta.is_file():
        pytest.skip("el repositorio no trae herramientas.json")
    datos = json.loads(ruta.read_text("utf-8"))
    primera = next(iter(datos["herramientas"].values()))
    primera["url"] = "http://ejemplo.invalid/x.zip"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    assert any("la URL debe ser HTTPS" in x for x in _problemas(estatico, repo_copia))


# =============================================================================================
# Correcciones de la revisión: SemVer ASCII, publicar (versión y atomicidad), lib.sh, exclusión
# =============================================================================================


@pytest.mark.parametrize("v", ["１.２.３", "1.2.٣", "1.².3", "१.२.३"])
def test_semver_rechaza_digitos_no_ascii(version, v):
    with pytest.raises(version.ErrorVersion):
        version.validar_semver(v)


@pytest.mark.parametrize("v", ["1.2.3\n", "1.2.3\r\n", "1.2.3 ", "\n1.2.3"])
def test_semver_rechaza_espacios_y_saltos_alrededor(version, v):
    with pytest.raises(version.ErrorVersion):
        version.validar_semver(v)


def test_publicar_omite_los_artefactos_de_otra_version(sumas, tmp_path, capsys):
    dist = tmp_path / "dist"
    vieja = _artefacto(dist, "proxlaunch_0.4.0_amd64.deb", b"viejo")
    vieja_exe = _artefacto(dist, "proxlaunch-0.4.0-windows-x64-setup.exe", b"viejo-exe")
    vigente = _artefacto(dist, "proxlaunch_0.5.0_amd64.deb", b"vigente")
    for art in (vieja, vieja_exe, vigente):
        sumas.sellar(art)
    assert sumas.publicar(dist, "0.5.0") == 0
    texto = (dist / "SHA256SUMS").read_text("utf-8")
    assert "proxlaunch_0.5.0_amd64.deb" in texto
    assert "0.4.0" not in texto
    assert "0.4.0" in capsys.readouterr().err  # se avisa de la omisión


def test_publicar_un_artefacto_de_otra_version_sin_sello_no_hace_fallar(sumas, tmp_path):
    dist = tmp_path / "dist"
    _artefacto(dist, "proxlaunch_0.4.0_amd64.deb", b"viejo sin sellar")
    sumas.sellar(_artefacto(dist, "proxlaunch_0.5.0_amd64.deb", b"vigente"))
    assert sumas.publicar(dist, "0.5.0") == 0


def test_publicar_si_la_vigente_no_esta_sellada_sigue_fallando(sumas, tmp_path):
    dist = tmp_path / "dist"
    _artefacto(dist, "proxlaunch_0.5.0_amd64.deb", b"sin sello")
    assert sumas.publicar(dist, "0.5.0") == 1


def test_publicar_incluye_los_artefactos_sin_version_en_el_nombre(sumas, tmp_path):
    dist = tmp_path / "dist"
    for nombre in ("sin-version.deb", "otro-setup.exe"):
        sumas.sellar(_artefacto(dist, nombre, nombre.encode()))
    assert sumas.publicar(dist, "9.9.9") == 0
    texto = (dist / "SHA256SUMS").read_text("utf-8")
    assert "sin-version.deb" in texto and "otro-setup.exe" in texto


def test_publicar_sin_version_explicita_usa_la_del_codigo(sumas, tmp_path):
    dist = tmp_path / "dist"
    vigente = sumas.version_vigente()
    propio = _artefacto(dist, f"proxlaunch_{vigente}_amd64.deb", b"a")
    ajeno = _artefacto(dist, "proxlaunch_99.99.99_amd64.deb", b"b")
    sumas.sellar(propio)
    sumas.sellar(ajeno)
    assert sumas.publicar(dist) == 0
    texto = (dist / "SHA256SUMS").read_text("utf-8")
    assert propio.name in texto and ajeno.name not in texto


def test_publicar_no_deja_temporales(sumas, tmp_path):
    dist = tmp_path / "dist"
    sumas.sellar(_artefacto(dist, "a.deb", b"a"))
    sumas.publicar(dist)
    assert [p.name for p in dist.iterdir() if p.name.endswith(".tmp")] == []


def test_publicar_con_fallo_al_reemplazar_conserva_el_sha256sums_previo(
    sumas, tmp_path, monkeypatch
):
    dist = tmp_path / "dist"
    sumas.sellar(_artefacto(dist, "a.deb", b"a"))
    (dist / "SHA256SUMS").write_text("previo completo\n", encoding="utf-8")

    def falla(origen, destino):
        raise OSError("disco lleno")

    monkeypatch.setattr(sumas.os, "replace", falla)
    with pytest.raises(OSError):
        sumas.publicar(dist)
    assert (dist / "SHA256SUMS").read_text("utf-8") == "previo completo\n"
    assert [p.name for p in dist.iterdir() if p.name.endswith(".tmp")] == []


def test_publicar_con_fallo_a_mitad_de_escritura_no_deja_un_sha256sums_truncado(
    sumas, tmp_path, monkeypatch
):
    dist = tmp_path / "dist"
    sumas.sellar(_artefacto(dist, "a.deb", b"a"))
    original = Path.write_text

    def escribe_a_medias(self, datos, *a, **k):
        if self.name.endswith(".tmp"):
            original(self, datos[:5], *a, **k)  # contenido parcial en el temporal
            raise OSError("se cortó la escritura")
        return original(self, datos, *a, **k)

    monkeypatch.setattr(Path, "write_text", escribe_a_medias)
    with pytest.raises(OSError):
        sumas.publicar(dist)
    assert not (dist / "SHA256SUMS").exists()
    assert [p.name for p in dist.iterdir() if p.name.endswith(".tmp")] == []


# --- lib.sh y su autotest (requieren bash de POSIX) ---------------------------------------------

BASH = shutil.which("bash")
requiere_bash = pytest.mark.skipif(
    sys.platform == "win32" or BASH is None, reason="requiere bash de POSIX"
)


def _entorno_sh(tmp_path: Path) -> dict[str, str]:
    """Entorno mínimo del subproceso: todo lo que escriba cae bajo ``tmp_path``."""
    import os

    base = tmp_path / "entorno"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C.UTF-8"}
    for nombre, sub in {
        "HOME": "home",
        "XDG_DATA_HOME": "xdg/data",
        "XDG_CONFIG_HOME": "xdg/config",
        "XDG_STATE_HOME": "xdg/state",
        "XDG_CACHE_HOME": "xdg/cache",
        "TMPDIR": "tmp",
    }.items():
        (base / sub).mkdir(parents=True, exist_ok=True)
        env[nombre] = str(base / sub)
    return env


def _correr_sh(args: list[str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH or "bash", *args],
        env=_entorno_sh(tmp_path),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@requiere_bash
def test_autotest_lib_sale_0(tmp_path):
    res = _correr_sh([str(COMUN / "autotest-lib.sh")], tmp_path)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "autotest de lib.sh correcto" in res.stdout
    assert "FALLÓ" not in res.stdout


def _script_con_paso(tmp_path: Path, cuerpo: str) -> Path:
    script = tmp_path / "caso.sh"
    script.write_text(
        "set -euo pipefail\n"
        "NOMBRE_SCRIPT=caso\n"
        f". '{COMUN / 'lib.sh'}'\n"
        f"{cuerpo}\n"
        'echo "llegó al final"\n',
        encoding="utf-8",
    )
    return script


@requiere_bash
def test_paso_falla_si_un_comando_intermedio_falla_y_no_sigue(tmp_path):
    script = _script_con_paso(tmp_path, 'f() { false; echo sigue; }\npaso "caso" f')
    res = _correr_sh([str(script)], tmp_path)
    assert res.returncode != 0, (res.stdout, res.stderr)
    assert "sigue" not in res.stdout
    assert "llegó al final" not in res.stdout
    assert "falló el paso: caso" in res.stderr


@requiere_bash
def test_paso_correcto_si_ejecuta_toda_la_funcion(tmp_path):
    """Control de la prueba anterior: sin fallo, la función llega a su última orden."""
    script = _script_con_paso(tmp_path, 'f() { true; echo sigue; }\npaso "caso" f')
    res = _correr_sh([str(script)], tmp_path)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "sigue" in res.stdout and "llegó al final" in res.stdout


# --- revisar_estatico: reglas de lib.sh ----------------------------------------------------------

LINEA_PASO = '( set -e; "$@" )'


def test_la_revision_detecta_que_paso_pierda_el_set_e(estatico, repo_copia):
    lib = repo_copia / "empaquetado" / "comun" / "lib.sh"
    texto = lib.read_text("utf-8")
    assert LINEA_PASO in texto
    lib.write_text(texto.replace(LINEA_PASO, '"$@"'), encoding="utf-8")
    p = _problemas(estatico, repo_copia)
    assert any("QA-M5-01" in x and "set -e" in x for x in p), p


def test_la_revision_detecta_if_negado_alrededor_de_la_orden(estatico, repo_copia):
    lib = repo_copia / "empaquetado" / "comun" / "lib.sh"
    lib.write_text(lib.read_text("utf-8") + '\notro() { if ! "$@"; then return 1; fi; }\n', "utf-8")
    p = _problemas(estatico, repo_copia)
    assert any("QA-M5-01" in x and "if !" in x for x in p), p


def test_la_revision_ignora_el_if_negado_en_un_comentario(estatico, repo_copia):
    lib = repo_copia / "empaquetado" / "comun" / "lib.sh"
    lib.write_text(lib.read_text("utf-8") + '\n# antes: if ! "$@"; then ...\n', "utf-8")
    assert _problemas(estatico, repo_copia) == []


# --- exclusion-laboratorio.sh con un puerto sustituible ------------------------------------------

EXCLUSION = COMUN / "exclusion-laboratorio.sh"


def _comprobar_exclusion(tmp_path: Path, puerto: int) -> subprocess.CompletedProcess[str]:
    """Carga la guarda con el puerto prohibido sustituido y una marca de proceso inexistente.

    Nunca se usan 8006 ni 2222: el puerto es el de un oyente efímero de esta prueba.
    """
    script = tmp_path / "exclusion.sh"
    script.write_text(
        "set -euo pipefail\n"
        "NOMBRE_SCRIPT=exclusion\n"
        'die() { echo "ERROR: $*" >&2; exit 1; }\n'
        f". '{EXCLUSION}'\n"
        f'LAB_PUERTOS_PROHIBIDOS="{puerto}"\n'
        'LAB_MARCA_PROCESO="marca-que-no-existe-en-ningun-proceso-7f3a9c"\n'
        "comprobar_exclusion_laboratorio\n"
        'echo "sin conflicto"\n',
        encoding="utf-8",
    )
    return _correr_sh([str(script)], tmp_path)


@pytest.fixture
def oyente_local(tmp_path):
    """Proceso aparte con un puerto efímero en escucha en 127.0.0.1 (solo bucle local).

    Se lanza en un subproceso porque pytest-socket bloquea los sockets del propio proceso.
    """
    codigo = (
        "import socket, sys\n"
        "s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(1)\n"
        "print(s.getsockname()[1], flush=True)\n"
        "sys.stdin.read()\n"
    )
    proceso = subprocess.Popen(
        [sys.executable, "-I", "-c", codigo],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        cwd=tmp_path,
    )
    assert proceso.stdout is not None and proceso.stdin is not None
    puerto = int(proceso.stdout.readline())
    assert puerto not in (8006, 2222)
    try:
        yield puerto
    finally:
        proceso.stdin.close()
        proceso.wait(timeout=10)


@requiere_bash
@pytest.mark.skipif(not Path("/proc/net/tcp").exists(), reason="requiere /proc/net/tcp (Linux)")
def test_exclusion_detecta_un_puerto_en_escucha_en_127_0_0_1(tmp_path, oyente_local):
    res = _comprobar_exclusion(tmp_path, oyente_local)
    assert res.returncode != 0, (res.stdout, res.stderr)
    assert str(oyente_local) in res.stderr
    assert "sin conflicto" not in res.stdout


@requiere_bash
@pytest.mark.skipif(not Path("/proc/net/tcp").exists(), reason="requiere /proc/net/tcp (Linux)")
def test_exclusion_no_se_queja_si_el_puerto_prohibido_esta_libre(tmp_path, oyente_local):
    # Un puerto distinto del que escucha el oyente (y nunca 8006 ni 2222).
    libre = oyente_local + 1 if oyente_local < 65000 else oyente_local - 1
    assert libre not in (8006, 2222)
    res = _comprobar_exclusion(tmp_path, libre)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "sin conflicto" in res.stdout


# --- verificar-deb.sh: poda del listado de $HOME solo en GitHub Actions --------------------------


def _listado_home(tmp_path: Path, **entorno: str) -> tuple[list[str], str]:
    """Ejecuta el bloque PODAS_CI + listado_home de verificar-deb.sh sobre un $HOME falso."""
    texto = (RAIZ / "empaquetado" / "verificar-deb.sh").read_text(encoding="utf-8")
    inicio = texto.index("PODAS_CI=()")
    fin = texto.index("# --- Pasos")
    home = tmp_path / "home"
    for d in ("actions-runner/_diag", "work/_temp", "work/proxlaunch/proxlaunch", "otro"):
        (home / d).mkdir(parents=True, exist_ok=True)
        (home / d / "f.log").write_text("x", encoding="utf-8")
    raiz = f"{home}/work/proxlaunch/proxlaunch"
    script = f'msg() {{ echo "MSG: $*" >&2; }}\nRAIZ="{raiz}"\n{texto[inicio:fin]}\nlistado_home\n'
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), **entorno}
    r = subprocess.run(
        ["bash", "-eu", "-c", script], capture_output=True, text=True, env=env, check=True
    )
    return [linea.split(" ")[0] for linea in r.stdout.splitlines()], r.stderr


@requiere_bash
def test_verificar_deb_no_poda_de_la_ci_en_local(tmp_path):
    rutas, err = _listado_home(tmp_path, RUNNER_WORKSPACE=f"{tmp_path}/home/work/proxlaunch")
    assert "actions-runner/_diag/f.log" in rutas
    assert "work/_temp/f.log" in rutas
    assert "otro/f.log" in rutas
    assert "MSG" not in err


@requiere_bash
def test_verificar_deb_poda_de_la_ci_solo_con_github_actions(tmp_path):
    rutas, err = _listado_home(
        tmp_path, GITHUB_ACTIONS="true", RUNNER_WORKSPACE=f"{tmp_path}/home/work/proxlaunch"
    )
    assert not any(r.startswith(("actions-runner", "work")) for r in rutas)
    assert "otro/f.log" in rutas
    assert "actions-runner" in err


@requiere_bash
def test_verificar_deb_sin_runner_workspace_no_poda_aunque_sea_la_ci(tmp_path):
    rutas, _ = _listado_home(tmp_path, GITHUB_ACTIONS="true")
    assert "actions-runner/_diag/f.log" in rutas
