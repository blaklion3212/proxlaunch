"""Pruebas del MVP 5 sobre ``--version`` y la prueba de humo (RF-E06, RF-E07, RF-E10, RF-E14,
RF-E17; ``docs/requisitos/mvp5.md`` y ``docs/arquitectura/mvp5.md`` §3).

Estrategia (decisión justificada):

- Las variantes de fallo y los contratos finos (JSON, problemas, llavero, carpeta temporal) corren
  EN PROCESO con ``QT_QPA_PLATFORM=offscreen`` y la ``QApplication`` compartida de pytest-qt:
  son rápidas y permiten sustituir los límites del sistema (recursos, llavero, fuentes, red).
  Un fixture restaura lo que el humo toca de la ``QApplication`` compartida (traductor, fuente,
  logger ``proxlaunch``).
- Lo que no puede ejecutarse en proceso se hace en SUBPROCESO con ``python -m proxlaunch``: el
  camino completo (CA-E17.3), ``sys.stdout=None``-equivalente real, el tiempo (CA-E17.1) y el
  vigilante, porque ``os._exit`` terminaría el proceso de pytest.
- Nada usa red ni las carpetas reales: HOME/XDG/TMPDIR de los subprocesos cuelgan de ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import keyring
import keyring.backends.fail
import keyring.backends.null
import platformdirs
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import proxlaunch
from proxlaunch.interfaz import app as app_mod
from proxlaunch.interfaz import humo
from proxlaunch.nucleo.persistencia import rutas as rutas_mod
from proxlaunch.nucleo.persistencia import secretos as secretos_mod
from proxlaunch.nucleo.persistencia.rutas import Rutas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos

RAIZ = Path(__file__).resolve().parents[2]
PAQUETE = Path(proxlaunch.__file__).resolve().parent
QM = PAQUETE / "recursos" / "traducciones" / "proxlaunch_es.qm"
TS = PAQUETE / "recursos" / "traducciones" / "proxlaunch_es.ts"
VERSION_ESPERADA = "0.5.0"
SALIDA = humo.VARIABLE_SALIDA


# ---------------------------------------------------------------------------------------------
# Apoyo
# ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalogo_qm():
    """Garantiza que exista el ``.qm`` (producto del build, ignorado por git).

    Si no existe se compila desde el ``.ts`` con ``compilar_qm.py`` y se borra al terminar el
    módulo; si ya existía no se toca.
    """
    existia = QM.is_file()
    if not existia:
        spec = importlib.util.spec_from_file_location(
            "mvp5_compilar_qm_humo", RAIZ / "empaquetado" / "comun" / "compilar_qm.py"
        )
        assert spec is not None and spec.loader is not None
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.compilar(TS, QM)
    yield QM
    if not existia:
        QM.unlink(missing_ok=True)


class _LlaveroValido:
    """Backend de llavero distinto de fail/null; ninguna operación sobre secretos es válida."""

    priority = 1

    def get_password(self, *a, **k):
        raise AssertionError("el humo no debe leer secretos")

    set_password = delete_password = get_password


@pytest.fixture
def llavero(monkeypatch):
    """Sustituye el llavero: registra las llamadas y prohíbe leer/escribir/borrar secretos."""

    class Espia:
        def __init__(self) -> None:
            self.backend: object = _LlaveroValido()
            self.get_keyring = 0
            self.prohibidas: list[str] = []

    espia = Espia()

    def get_keyring():
        espia.get_keyring += 1
        return espia.backend

    def prohibida(nombre):
        def _f(*a, **k):
            espia.prohibidas.append(nombre)
            raise AssertionError(f"keyring.{nombre} no debe llamarse en el humo")

        return _f

    monkeypatch.setattr(keyring, "get_keyring", get_keyring)
    for nombre in ("get_password", "set_password", "delete_password", "get_credential"):
        monkeypatch.setattr(keyring, nombre, prohibida(nombre))
    return espia


@pytest.fixture
def entorno_humo(qapp, monkeypatch, tmp_path, llavero):
    """Aísla una ejecución en proceso del humo y restaura el estado compartido al terminar."""
    monkeypatch.delenv(SALIDA, raising=False)
    # Sin red: crear_dependencias recibe esta fábrica; si alguien la invoca, la prueba falla.
    monkeypatch.setattr(
        app_mod,
        "crear_transporte_http",
        lambda *a, **k: pytest.fail("el humo no debe crear un transporte HTTP"),
    )
    # Las carpetas temporales del humo caen dentro de tmp_path y quedan registradas.
    temporales = tmp_path / "tmp-humo"
    temporales.mkdir()
    creadas: list[Path] = []
    mkdtemp_real = humo.tempfile.mkdtemp

    def mkdtemp(*, prefix=None, **k):
        ruta = Path(mkdtemp_real(prefix=prefix, dir=temporales))
        creadas.append(ruta)
        return str(ruta)

    monkeypatch.setattr(humo.tempfile, "mkdtemp", mkdtemp)
    # Traductores instalados por el humo: se retiran después.
    traductores: list[object] = []
    cargar_real = humo.cargar_traductor

    def cargar(app):
        t = cargar_real(app)
        if t is not None:
            traductores.append(t)
        return t

    monkeypatch.setattr(humo, "cargar_traductor", cargar)
    logger = logging.getLogger("proxlaunch")
    estado_log = (list(logger.handlers), logger.propagate, logger.level)
    fuente, nombre, org = qapp.font(), qapp.applicationName(), qapp.organizationName()
    estilo = qapp.styleSheet()

    class Entorno:
        carpetas = creadas

    yield Entorno

    for t in traductores:
        qapp.removeTranslator(t)  # type: ignore[arg-type]
    for h in list(logger.handlers):
        if h not in estado_log[0]:
            logger.removeHandler(h)
            h.close()
    logger.propagate = estado_log[1]
    logger.setLevel(estado_log[2])
    qapp.setFont(fuente)
    qapp.setApplicationName(nombre)
    qapp.setOrganizationName(org)
    qapp.setStyleSheet(estilo)
    qapp.setWindowIcon(QIcon())
    # ``ventana.close()`` tras el bucle llama a ``quit()`` sin bucle activo y deja el indicador
    # «quitNow» de Qt levantado, con lo que el siguiente ``QEventLoop.exec`` (qtbot.waitSignal,
    # etc.) saldría al instante. Un bucle vacío (``exec`` lo baja al empezar y al acabar) lo limpia.
    QTimer.singleShot(0, qapp.quit)
    qapp.exec()


def ejecutar(capsys, *, permitir_sin_llavero=False):
    rc = humo.ejecutar_prueba_de_humo(
        ["proxlaunch"], permitir_sin_llavero=permitir_sin_llavero, espera_ms=50
    )
    salida = capsys.readouterr()
    return rc, salida.out, salida.err


def informe_de(salida: str) -> dict:
    lineas = [ln for ln in salida.splitlines() if ln.strip()]
    assert len(lineas) == 1, f"se esperaba una única línea JSON y hubo: {lineas!r}"
    return json.loads(lineas[0])


def entorno_hijo(tmp_path: Path, **extra: str) -> dict[str, str]:
    """Entorno del subproceso: carpetas del usuario y temporales dentro de ``tmp_path``."""
    env = dict(os.environ)
    base = tmp_path / "hijo"
    destinos = {
        "HOME": base / "home",
        "USERPROFILE": base / "home",
        "XDG_DATA_HOME": base / "xdg" / "data",
        "XDG_CONFIG_HOME": base / "xdg" / "config",
        "XDG_STATE_HOME": base / "xdg" / "state",
        "XDG_CACHE_HOME": base / "xdg" / "cache",
        "LOCALAPPDATA": base / "local",
        "APPDATA": base / "roaming",
        "TMPDIR": base / "tmp",
        "TEMP": base / "tmp",
        "TMP": base / "tmp",
    }
    for nombre, ruta in destinos.items():
        ruta.mkdir(parents=True, exist_ok=True)
        env[nombre] = str(ruta)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.pop(SALIDA, None)
    env.pop("PYTHON_KEYRING_BACKEND", None)
    env.update(extra)
    return env


def lanzar(args: list[str], env: dict[str, str], *, timeout: float = 60):
    return subprocess.run(
        [sys.executable, "-m", "proxlaunch", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# ---------------------------------------------------------------------------------------------
# --version  (RF-E10, contrato de arquitectura §3)
# ---------------------------------------------------------------------------------------------


def test_version_imprime_nombre_y_version_y_devuelve_0(capsys):
    assert app_mod.main(["proxlaunch", "--version"]) == 0
    assert capsys.readouterr().out == f"ProxLaunch {VERSION_ESPERADA}\n"
    assert proxlaunch.__version__ == VERSION_ESPERADA


def test_version_no_crea_qapplication(monkeypatch, capsys):
    class QApplicationProhibida:
        def __new__(cls, *a, **k):
            pytest.fail("--version no debe crear QApplication")

        @staticmethod
        def instance():
            pytest.fail("--version no debe consultar QApplication")

    monkeypatch.setattr(app_mod, "QApplication", QApplicationProhibida)
    monkeypatch.setattr(
        humo, "ejecutar_prueba_de_humo", lambda *a, **k: pytest.fail("no es el modo de humo")
    )
    assert app_mod.main(["proxlaunch", "--version"]) == 0
    assert "ProxLaunch" in capsys.readouterr().out


def test_version_sin_stdout_escribe_el_archivo_de_salida(monkeypatch, tmp_path):
    """Windows sin consola: ``sys.stdout`` es ``None`` y la salida va al archivo."""
    destino = tmp_path / "salida.txt"
    monkeypatch.setenv(SALIDA, str(destino))
    monkeypatch.setattr(sys, "stdout", None)
    assert app_mod.main(["proxlaunch", "--version"]) == 0
    assert destino.read_text("utf-8") == f"ProxLaunch {VERSION_ESPERADA}\n"


def test_version_con_stdout_y_archivo_escribe_en_ambos(monkeypatch, tmp_path, capsys):
    destino = tmp_path / "salida.txt"
    monkeypatch.setenv(SALIDA, str(destino))
    assert app_mod.main(["proxlaunch", "--version"]) == 0
    assert capsys.readouterr().out == destino.read_text("utf-8")


def test_version_sin_stdout_ni_variable_no_falla(monkeypatch):
    monkeypatch.delenv(SALIDA, raising=False)
    monkeypatch.setattr(sys, "stdout", None)
    assert app_mod.main(["proxlaunch", "--version"]) == 0


def test_version_con_archivo_de_salida_inaccesible_no_falla(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(SALIDA, str(tmp_path / "no-existe" / "sub" / "salida.txt"))
    assert app_mod.main(["proxlaunch", "--version"]) == 0
    assert "ProxLaunch" in capsys.readouterr().out


def test_las_opciones_largas_no_se_abrevian():
    for abreviada in ("--v", "--ver", "--prueba", "--prueba-de", "--permitir"):
        propios, resto = app_mod._analizar_argumentos(["proxlaunch", abreviada])
        assert not (propios.version or propios.prueba_de_humo or propios.permitir_sin_llavero), (
            abreviada
        )
        assert abreviada in resto


def test_las_opciones_de_qt_pasan_intactas_y_argv0_se_conserva():
    propios, resto = app_mod._analizar_argumentos(
        ["prog", "-platform", "offscreen", "--prueba-de-humo", "-style", "fusion"]
    )
    assert propios.prueba_de_humo and not propios.version
    assert resto == ["prog", "-platform", "offscreen", "-style", "fusion"]


def test_sin_opciones_propias_no_se_activa_ningun_modo():
    propios, resto = app_mod._analizar_argumentos(["proxlaunch"])
    assert not (propios.version or propios.prueba_de_humo or propios.permitir_sin_llavero)
    assert resto == ["proxlaunch"]


# ---------------------------------------------------------------------------------------------
# Enrutado de main()
# ---------------------------------------------------------------------------------------------


def test_main_enruta_al_humo_con_las_opciones_y_devuelve_su_codigo(monkeypatch):
    llamadas = []

    def falso(argv_qt, *, permitir_sin_llavero=False, espera_ms=1500):
        llamadas.append((argv_qt, permitir_sin_llavero))
        return 7

    monkeypatch.setattr(humo, "ejecutar_prueba_de_humo", falso)
    rc = app_mod.main(
        ["proxlaunch", "--prueba-de-humo", "--permitir-sin-llavero", "-platform", "offscreen"]
    )
    assert rc == 7
    assert llamadas == [(["proxlaunch", "-platform", "offscreen"], True)]


def test_main_no_permite_sin_llavero_por_defecto(monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        humo,
        "ejecutar_prueba_de_humo",
        lambda argv_qt, *, permitir_sin_llavero=False, espera_ms=1500: (
            llamadas.append(permitir_sin_llavero) or 0
        ),
    )
    assert app_mod.main(["proxlaunch", "--prueba-de-humo"]) == 0
    assert llamadas == [False]


class _GestorFalso:
    def __init__(self, app, modo):
        self.app, self.modo, self.aplicado = app, modo, False

    def aplicar(self):
        self.aplicado = True


def test_modo_normal_sigue_el_camino_de_siempre(entorno_humo, monkeypatch, tmp_path, qapp):
    """CA-E17.5: sin opciones, ``main`` usa ``Rutas()`` real y ``VentanaPrincipal`` con las
    dependencias de ``crear_dependencias``; no entra en el humo ni escribe el archivo de salida."""
    destino = tmp_path / "no-debe-existir.json"
    monkeypatch.setenv(SALIDA, str(destino))
    monkeypatch.setattr(
        humo, "ejecutar_prueba_de_humo", lambda *a, **k: pytest.fail("no es el modo de humo")
    )
    visto: dict = {}
    centinela = object()

    def crear_deps(rutas, gestor):
        visto["rutas"], visto["gestor"] = rutas, gestor
        return centinela

    class VentanaFalsa:
        def __init__(self, deps):
            visto["deps"] = deps

        def show(self):
            visto["mostrada"] = True

    monkeypatch.setattr(app_mod, "crear_dependencias", crear_deps)
    monkeypatch.setattr(app_mod, "VentanaPrincipal", VentanaFalsa)
    monkeypatch.setattr(app_mod, "GestorTema", _GestorFalso)
    monkeypatch.setattr(app_mod, "cargar_traductor", lambda app: None)
    monkeypatch.setattr(
        app_mod, "configurar_registro", lambda carpeta: visto.setdefault("log", carpeta)
    )
    monkeypatch.setattr(QApplication, "exec", lambda *a, **k: 42)

    assert app_mod.main([]) == 42

    assert visto["deps"] is centinela and visto["mostrada"] is True
    assert isinstance(visto["rutas"], Rutas)
    assert visto["rutas"].directorio_config == Path(platformdirs.user_config_dir("ProxLaunch"))
    assert visto["log"] == visto["rutas"].directorio_log
    assert isinstance(visto["gestor"], _GestorFalso) and visto["gestor"].aplicado
    assert not destino.exists()
    assert not any(Path(c).exists() for c in entorno_humo.carpetas)


# ---------------------------------------------------------------------------------------------
# Prueba de humo en proceso  (RF-E17, RF-E06, RF-E07)
# ---------------------------------------------------------------------------------------------


def test_humo_camino_feliz(entorno_humo, catalogo_qm, llavero, capsys):
    rc, out, err = ejecutar(capsys)
    informe = informe_de(out)
    assert rc == 0, (out, err)
    assert informe["problemas"] == []
    assert informe["version"] == VERSION_ESPERADA
    assert informe["plataforma_qt"] == "offscreen"
    assert informe["traductor"] is True
    assert informe["icono_ok"] is True
    assert informe["ventana_mostrada"] is True
    assert informe["recursos_faltantes"] == []
    assert informe["backend_llavero"].endswith("_LlaveroValido")
    assert len(informe["fuentes"]) == 2 and all(informe["fuentes"])
    assert "PROBLEMA" not in err


def test_humo_el_informe_contiene_todas_las_claves_del_contrato(entorno_humo, catalogo_qm, capsys):
    _, out, _ = ejecutar(capsys)
    assert set(informe_de(out)) == set(humo.InformeHumo.__dataclass_fields__)


def test_humo_la_espera_por_defecto_cumple_el_limite_de_5_segundos():
    espera = inspect.signature(humo.ejecutar_prueba_de_humo).parameters["espera_ms"].default
    assert 0 < espera <= 5000


def test_humo_el_limite_del_vigilante_es_de_15_segundos_y_su_codigo_el_3():
    assert humo.LIMITE_VIGILANTE_S <= 15.0
    assert humo.CODIGO_VIGILANTE == 3


def test_humo_solo_consulta_get_keyring_y_nunca_los_secretos(
    entorno_humo, catalogo_qm, llavero, capsys
):
    rc, out, _ = ejecutar(capsys)
    assert rc == 0, out
    assert llavero.get_keyring >= 1
    assert llavero.prohibidas == []


@pytest.mark.parametrize("clase", [keyring.backends.fail.Keyring, keyring.backends.null.Keyring])
def test_humo_con_llavero_fail_o_null_falla_y_lo_nombra(
    entorno_humo, catalogo_qm, llavero, capsys, clase
):
    llavero.backend = clase()
    rc, out, err = ejecutar(capsys)
    informe = informe_de(out)
    assert rc != 0
    assert any("llavero" in p.lower() and clase.__module__ in p for p in informe["problemas"])
    assert "PROBLEMA:" in err and "llavero" in err.lower()
    assert llavero.prohibidas == []


@pytest.mark.parametrize("clase", [keyring.backends.fail.Keyring, keyring.backends.null.Keyring])
def test_humo_con_llavero_inutil_pasa_con_permitir_sin_llavero(
    entorno_humo, catalogo_qm, llavero, capsys, clase
):
    llavero.backend = clase()
    rc, out, _ = ejecutar(capsys, permitir_sin_llavero=True)
    assert rc == 0, out
    assert informe_de(out)["problemas"] == []
    assert llavero.prohibidas == []


class _RecursoSinQm:
    """Envuelve un ``Traversable`` y hace que ``proxlaunch_es.qm`` parezca ausente."""

    def __init__(self, real, oculto=("proxlaunch_es.qm",)):
        self._real, self._oculto = real, oculto

    def joinpath(self, *partes):
        destino = self._real.joinpath(*partes)
        if partes and partes[-1] in self._oculto:
            return _Ausente(destino)
        return _RecursoSinQm(destino, self._oculto)

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)

    def __truediv__(self, otro):
        return self.joinpath(otro)


class _Ausente:
    def __init__(self, real):
        self._real = real

    def is_file(self):
        return False

    def __str__(self):
        return str(self._real)


def _ocultar_qm(monkeypatch):
    original = humo.resources.files
    monkeypatch.setattr(humo.resources, "files", lambda paquete: _RecursoSinQm(original(paquete)))


def test_humo_sin_qm_falla_y_nombra_el_archivo(entorno_humo, catalogo_qm, monkeypatch, capsys):
    """CA-E07.1 y CA-E17.4."""
    _ocultar_qm(monkeypatch)
    rc, out, err = ejecutar(capsys)
    informe = informe_de(out)
    assert rc != 0
    assert informe["traductor"] is False
    assert any("proxlaunch_es.qm" in p for p in informe["problemas"])
    assert "recursos/traducciones/proxlaunch_es.qm" in informe["recursos_faltantes"]
    assert "proxlaunch_es.qm" in err


def test_humo_con_qm_corrupto_falla_pero_no_se_cuelga(
    entorno_humo, catalogo_qm, monkeypatch, tmp_path, capsys
):
    """Un ``.qm`` que existe pero no carga también es un fallo del humo (traductor)."""
    falso = tmp_path / "recursos" / "traducciones"
    falso.mkdir(parents=True)
    (falso / "proxlaunch_es.qm").write_bytes(b"esto no es un catalogo")
    corrupto = falso / "proxlaunch_es.qm"
    original = app_mod.resources.files

    class RaizConQmCorrupto:
        def __init__(self, real):
            self._real = real

        def joinpath(self, *partes):
            if partes and partes[-1] == "proxlaunch_es.qm":
                return corrupto
            return self._real.joinpath(*partes)

    def files(paquete):
        real = original(paquete)
        return RaizConQmCorrupto(real) if paquete == "proxlaunch.recursos" else real

    monkeypatch.setattr(app_mod.resources, "files", files)
    rc, out, _ = ejecutar(capsys)
    informe = informe_de(out)
    assert rc != 0 and informe["traductor"] is False
    assert any("proxlaunch_es.qm" in p for p in informe["problemas"])


def test_humo_con_un_recurso_faltante_lo_nombra(entorno_humo, catalogo_qm, monkeypatch, capsys):
    """CA-E06.2 y CA-E17.4."""
    extra = "recursos/fuentes/Fuente-Inexistente.ttf"
    esperados = humo.recursos_esperados()
    monkeypatch.setattr(humo, "recursos_esperados", lambda: (*esperados, extra))
    rc, out, err = ejecutar(capsys)
    informe = informe_de(out)
    assert rc != 0
    assert informe["recursos_faltantes"] == [extra]
    assert any(extra in p for p in informe["problemas"])
    assert extra in err


def test_humo_con_varios_recursos_faltantes_los_nombra_todos(
    entorno_humo, catalogo_qm, monkeypatch, capsys
):
    lista = ("recursos/marca/a.svg", "interfaz/tema/b.qss")
    monkeypatch.setattr(humo, "recursos_esperados", lambda: lista)
    rc, out, _ = ejecutar(capsys)
    assert rc != 0
    assert informe_de(out)["recursos_faltantes"] == list(lista)


def test_humo_con_icono_nulo_registra_el_problema(entorno_humo, catalogo_qm, monkeypatch, capsys):
    monkeypatch.setattr(humo, "crear_icono", lambda: QIcon())
    rc, out, err = ejecutar(capsys)
    informe = informe_de(out)
    assert rc != 0
    assert informe["icono_ok"] is False
    assert any("icono" in p.lower() for p in informe["problemas"])
    assert "icono" in err.lower()


def test_humo_con_fuentes_de_respaldo_registra_el_problema(
    entorno_humo, catalogo_qm, monkeypatch, capsys
):
    monkeypatch.setattr(
        humo,
        "cargar_fuentes",
        lambda: (humo.FAMILIA_INTERFAZ_RESPALDO, humo.FAMILIA_MONO_RESPALDO),
    )
    rc, out, _ = ejecutar(capsys)
    problemas = informe_de(out)["problemas"]
    assert rc != 0
    assert any(humo.FAMILIA_INTERFAZ_RESPALDO in p for p in problemas)
    assert any(humo.FAMILIA_MONO_RESPALDO in p for p in problemas)


def test_humo_con_una_sola_fuente_de_respaldo_tambien_falla(
    entorno_humo, catalogo_qm, monkeypatch, capsys
):
    monkeypatch.setattr(humo, "cargar_fuentes", lambda: ("Open Sans", humo.FAMILIA_MONO_RESPALDO))
    rc, out, _ = ejecutar(capsys)
    problemas = informe_de(out)["problemas"]
    assert rc != 0 and len(problemas) == 1 and humo.FAMILIA_MONO_RESPALDO in problemas[0]


def test_humo_una_excepcion_se_convierte_en_problema_y_en_codigo_distinto_de_0(
    entorno_humo, catalogo_qm, monkeypatch, capsys
):
    def explota():
        raise RuntimeError("fallo simulado de fuentes")

    monkeypatch.setattr(humo, "cargar_fuentes", explota)
    rc, out, err = ejecutar(capsys)
    informe = informe_de(out)
    assert rc != 0
    assert any("RuntimeError" in p and "fallo simulado" in p for p in informe["problemas"])
    assert "PROBLEMA:" in err


def test_humo_si_la_ventana_no_queda_visible_falla(entorno_humo, catalogo_qm, monkeypatch, capsys):
    class VentanaOculta:
        def __init__(self, deps):
            pass

        def show(self):
            pass

        def isVisible(self):  # noqa: N802 - API de Qt
            return False

        def close(self):
            pass

    monkeypatch.setattr(humo, "VentanaPrincipal", VentanaOculta)
    rc, out, _ = ejecutar(capsys)
    informe = informe_de(out)
    assert rc != 0 and informe["ventana_mostrada"] is False
    assert any("ventana" in p.lower() for p in informe["problemas"])


def test_humo_la_carpeta_temporal_se_borra_en_exito(entorno_humo, catalogo_qm, capsys):
    rc, out, _ = ejecutar(capsys)
    assert rc == 0, out
    assert len(entorno_humo.carpetas) == 1
    carpeta = entorno_humo.carpetas[0]
    assert carpeta.name.startswith("proxlaunch-humo-")
    assert not carpeta.exists()


def test_humo_la_carpeta_temporal_se_borra_en_fallo(entorno_humo, catalogo_qm, monkeypatch, capsys):
    monkeypatch.setattr(humo, "recursos_esperados", lambda: ("recursos/marca/falta.svg",))
    rc, _, _ = ejecutar(capsys)
    assert rc != 0
    assert len(entorno_humo.carpetas) == 1 and not entorno_humo.carpetas[0].exists()


def test_humo_la_carpeta_temporal_se_borra_si_hay_excepcion(
    entorno_humo, catalogo_qm, monkeypatch, capsys
):
    monkeypatch.setattr(humo, "cargar_fuentes", lambda: 1 / 0)
    rc, _, _ = ejecutar(capsys)
    assert rc != 0 and not entorno_humo.carpetas[0].exists()


def test_humo_usa_rutas_con_base_temporal_y_no_las_carpetas_reales(
    entorno_humo, catalogo_qm, monkeypatch, capsys
):
    """CA-E17.2: el humo trabaja en ``Rutas(base)`` con base temporal, nunca en ``Rutas()``."""
    bases = []
    rutas_original = humo.Rutas

    def rutas(base=None):
        bases.append(base)
        return rutas_original(base)

    monkeypatch.setattr(humo, "Rutas", rutas)
    rc, _, _ = ejecutar(capsys)
    assert rc == 0
    assert len(bases) == 1 and bases[0] is not None
    assert Path(bases[0]) == entorno_humo.carpetas[0]
    assert not Path(platformdirs.user_config_dir("ProxLaunch")).exists()
    assert not Path(platformdirs.user_data_dir("ProxLaunch")).exists()


def test_humo_no_crea_transporte_http(entorno_humo, catalogo_qm, capsys):
    """El doble de ``crear_transporte_http`` hace fallar la prueba si alguien lo invoca."""
    llamadas = []
    original = app_mod.crear_transporte_http

    def espia(*a, **k):
        llamadas.append(1)
        return original(*a, **k)

    app_mod.crear_transporte_http = espia  # restaurado por monkeypatch de entorno_humo
    rc, out, _ = ejecutar(capsys)
    assert rc == 0, out
    assert llamadas == []


def test_humo_con_variable_de_salida_copia_el_informe_al_archivo(
    entorno_humo, catalogo_qm, monkeypatch, tmp_path, capsys
):
    destino = tmp_path / "informe.json"
    monkeypatch.setenv(SALIDA, str(destino))
    rc, out, _ = ejecutar(capsys)
    assert rc == 0
    assert json.loads(destino.read_text("utf-8")) == informe_de(out)


def test_humo_con_variable_de_salida_y_sin_stdout_solo_escribe_el_archivo(
    entorno_humo, catalogo_qm, monkeypatch, tmp_path
):
    destino = tmp_path / "informe.json"
    monkeypatch.setenv(SALIDA, str(destino))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    rc = humo.ejecutar_prueba_de_humo(["proxlaunch"], permitir_sin_llavero=True, espera_ms=50)
    assert rc == 0
    assert json.loads(destino.read_text("utf-8"))["problemas"] == []


@pytest.mark.xfail(
    strict=True,
    reason="DEFECTO: tras el humo el logger 'proxlaunch' conserva el manejador de archivo "
    "abierto sobre la carpeta temporal ya borrada (configurar_registro no se deshace). En "
    "Windows ese archivo abierto impide que rmtree borre la carpeta (CA-E17.2: no deja "
    "archivos) y en Linux los registros posteriores van a un archivo desvinculado.",
)
def test_humo_no_deja_un_manejador_de_registro_sobre_la_carpeta_temporal(
    entorno_humo, catalogo_qm, capsys
):
    previos = list(logging.getLogger("proxlaunch").handlers)
    rc, _, _ = ejecutar(capsys)
    assert rc == 0
    nuevos = [h for h in logging.getLogger("proxlaunch").handlers if h not in previos]
    assert nuevos == []


# ---------------------------------------------------------------------------------------------
# Recursos (RF-E06: CA-E06.1, CA-E06.2 en la parte local)
# ---------------------------------------------------------------------------------------------


def test_todos_los_recursos_esperados_existen(catalogo_qm):
    assert humo._faltantes() == ()


def test_recursos_esperados_cubre_el_package_data_y_el_qm():
    esperados = set(humo.recursos_esperados())
    for carpeta in ("marca", "fuentes"):
        reales = {
            f"recursos/{carpeta}/{p.name}"
            for p in (PAQUETE / "recursos" / carpeta).iterdir()
            if p.is_file() and not p.name.startswith(".")
        }
        assert reales <= esperados, f"recursos reales sin vigilar: {sorted(reales - esperados)}"
        assert {e for e in esperados if e.startswith(f"recursos/{carpeta}/")} <= reales
    assert "recursos/traducciones/proxlaunch_es.qm" in esperados
    assert "interfaz/tema/plantilla.qss" in esperados


def test_recursos_esperados_no_tiene_duplicados_ni_rutas_absolutas():
    lista = humo.recursos_esperados()
    assert len(lista) == len(set(lista))
    assert all(not r.startswith("/") and "\\" not in r and ".." not in r for r in lista)


# ---------------------------------------------------------------------------------------------
# Vigilante  (CA-E17.1: ≤ 15 s; sin colgarse)
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def salida_exit(monkeypatch):
    """Sustituye ``os._exit`` por un doble que registra el código y avisa con un evento."""
    evento = threading.Event()
    codigos: list[int] = []

    def falso(codigo):
        codigos.append(codigo)
        evento.set()

    monkeypatch.setattr(humo.os, "_exit", falso)
    return evento, codigos


def test_vigilante_aborta_con_el_codigo_3_informa_el_paso_y_borra_la_carpeta(
    monkeypatch, tmp_path, salida_exit, capsys
):
    evento, codigos = salida_exit
    destino = tmp_path / "informe.json"
    monkeypatch.setenv(SALIDA, str(destino))
    monkeypatch.setattr(humo, "LIMITE_VIGILANTE_S", 0.05)
    carpeta = tmp_path / "proxlaunch-humo-x"
    (carpeta / "datos").mkdir(parents=True)
    (carpeta / "datos" / "f.txt").write_text("x", encoding="utf-8")
    progreso = humo._Progreso()
    progreso.paso = "fuentes"
    humo._arrancar_vigilante(carpeta, progreso)
    assert evento.wait(10), "el vigilante no se disparó"
    assert codigos == [3]
    assert not carpeta.exists()
    contenido = json.loads(destino.read_text("utf-8"))
    assert contenido["version"] == VERSION_ESPERADA
    assert len(contenido["problemas"]) == 1
    assert "«fuentes»" in contenido["problemas"][0]
    assert "superó" in contenido["problemas"][0]
    salida = capsys.readouterr()
    assert "PROBLEMA:" in salida.err and "fuentes" in salida.err
    assert json.loads(salida.out)["problemas"] == contenido["problemas"]


def test_vigilante_sin_progreso_tambien_aborta_con_motivo(
    monkeypatch, tmp_path, salida_exit, capsys
):
    evento, codigos = salida_exit
    monkeypatch.setattr(humo, "LIMITE_VIGILANTE_S", 0.05)
    carpeta = tmp_path / "proxlaunch-humo-y"
    carpeta.mkdir()
    humo._arrancar_vigilante(carpeta)
    assert evento.wait(10)
    assert codigos == [3] and not carpeta.exists()
    assert "superó" in capsys.readouterr().err


def test_vigilante_cancelado_no_dispara_ni_borra(monkeypatch, tmp_path, salida_exit):
    evento, codigos = salida_exit
    monkeypatch.setattr(humo, "LIMITE_VIGILANTE_S", 0.1)
    carpeta = tmp_path / "proxlaunch-humo-z"
    carpeta.mkdir()
    vigilante = humo._arrancar_vigilante(carpeta, humo._Progreso())
    vigilante.cancel()
    assert not evento.wait(0.4)
    assert codigos == [] and carpeta.exists()


def test_vigilante_es_un_hilo_demonio(monkeypatch, tmp_path, salida_exit):
    monkeypatch.setattr(humo, "LIMITE_VIGILANTE_S", 60)
    vigilante = humo._arrancar_vigilante(tmp_path, humo._Progreso())
    try:
        assert vigilante.daemon is True
    finally:
        vigilante.cancel()


def test_humo_cancela_el_vigilante_al_terminar(entorno_humo, catalogo_qm, monkeypatch, capsys):
    temporizadores = []
    original = humo._arrancar_vigilante

    def espia(carpeta, progreso=None):
        t = original(carpeta, progreso)
        temporizadores.append(t)
        return t

    monkeypatch.setattr(humo, "_arrancar_vigilante", espia)
    rc, _, _ = ejecutar(capsys)
    assert rc == 0 and len(temporizadores) == 1
    temporizadores[0].join(2)
    assert not temporizadores[0].is_alive(), "el vigilante siguió activo tras terminar el humo"
    assert temporizadores[0].finished.is_set()


def test_progreso_empieza_en_inicio_y_mide_el_tiempo():
    antes = time.monotonic()
    p = humo._Progreso()
    assert p.paso == "inicio" and antes <= p.inicio <= time.monotonic()


SCRIPT_BLOQUEADO = """
import sys, time
from proxlaunch.interfaz import humo
humo.LIMITE_VIGILANTE_S = 0.8
humo.cargar_fuentes = lambda: time.sleep(120)   # el paso «fuentes» no termina nunca
sys.exit(humo.ejecutar_prueba_de_humo(["proxlaunch"], permitir_sin_llavero=True))
"""


def test_vigilante_en_subproceso_sale_con_3_escribe_la_salida_y_no_deja_carpeta(tmp_path):
    env = entorno_hijo(tmp_path, **{SALIDA: str(tmp_path / "informe.json")})
    inicio = time.monotonic()
    res = subprocess.run(
        [sys.executable, "-c", SCRIPT_BLOQUEADO],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == 3, (res.stdout, res.stderr)
    assert time.monotonic() - inicio < 30
    informe = json.loads((tmp_path / "informe.json").read_text("utf-8"))
    assert len(informe["problemas"]) == 1
    assert "«fuentes»" in informe["problemas"][0]
    assert "PROBLEMA:" in res.stderr and "fuentes" in res.stderr
    assert not list((tmp_path / "hijo" / "tmp").glob("proxlaunch-humo-*"))


# ---------------------------------------------------------------------------------------------
# Subprocesos con ``python -m proxlaunch`` (CA-E17.1, CA-E17.3, CA-E10.2 en el árbol de fuentes)
# ---------------------------------------------------------------------------------------------


def test_subproceso_version(tmp_path):
    res = lanzar(["--version"], entorno_hijo(tmp_path))
    assert res.returncode == 0, res.stderr
    assert res.stdout == f"ProxLaunch {VERSION_ESPERADA}\n"


def test_subproceso_version_escribe_tambien_el_archivo_de_salida(tmp_path):
    destino = tmp_path / "version.txt"
    res = lanzar(["--version"], entorno_hijo(tmp_path, **{SALIDA: str(destino)}))
    assert res.returncode == 0
    assert destino.read_text("utf-8") == f"ProxLaunch {VERSION_ESPERADA}\n"


def test_subproceso_humo_en_el_arbol_de_fuentes_pasa_en_menos_de_15_s(catalogo_qm, tmp_path):
    """CA-E17.3 (y la parte de tiempo de CA-E17.1 sin aislamiento de red)."""
    env = entorno_hijo(tmp_path, **{SALIDA: str(tmp_path / "informe.json")})
    inicio = time.monotonic()
    res = lanzar(["--prueba-de-humo", "--permitir-sin-llavero"], env)
    transcurrido = time.monotonic() - inicio
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert transcurrido <= 15
    informe = informe_de(res.stdout)
    assert informe["problemas"] == [] and informe["ventana_mostrada"] is True
    assert informe["plataforma_qt"] == "offscreen"
    assert json.loads((tmp_path / "informe.json").read_text("utf-8")) == informe


def test_subproceso_humo_no_toca_las_carpetas_del_usuario_ni_deja_temporales(catalogo_qm, tmp_path):
    """CA-E17.2: datos/config/estado del usuario intactos y sin ``proxlaunch-humo-*`` residuales."""
    env = entorno_hijo(tmp_path)
    res = lanzar(["--prueba-de-humo", "--permitir-sin-llavero"], env)
    assert res.returncode == 0, res.stderr
    base = tmp_path / "hijo"
    for sub in ("data", "config", "state"):
        assert not list((base / "xdg" / sub).glob("**/ProxLaunch*")), sub
    assert not list((base / "tmp").glob("proxlaunch-humo-*"))


@pytest.mark.parametrize(
    ("permitir", "esperado"), [(False, "!=0"), (True, "0")], ids=["sin-opcion", "con-opcion"]
)
def test_subproceso_humo_con_backend_fail(catalogo_qm, tmp_path, permitir, esperado):
    env = entorno_hijo(tmp_path, PYTHON_KEYRING_BACKEND="keyring.backends.fail.Keyring")
    args = ["--prueba-de-humo", *(["--permitir-sin-llavero"] if permitir else [])]
    res = lanzar(args, env)
    if permitir:
        assert res.returncode == 0, res.stderr
    else:
        assert res.returncode != 0
        assert "llavero" in res.stderr.lower() and "PROBLEMA:" in res.stderr


def _sin_red_disponible() -> bool:
    if sys.platform != "linux" or shutil.which("unshare") is None:
        return False
    try:
        return (
            subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(
    not _sin_red_disponible(),
    reason="requiere Linux con 'unshare -rn' (espacio de nombres de red sin privilegios)",
)
def test_subproceso_humo_sin_red_con_unshare(catalogo_qm, tmp_path):
    """CA-E17.1: sin red (``unshare -rn``) el humo sale con 0 en ≤ 15 s."""
    env = entorno_hijo(tmp_path)
    inicio = time.monotonic()
    res = subprocess.run(
        ["unshare", "-rn", sys.executable, "-m", "proxlaunch", "--prueba-de-humo",
         "--permitir-sin-llavero"],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert time.monotonic() - inicio <= 15
    assert informe_de(res.stdout)["problemas"] == []


# ---------------------------------------------------------------------------------------------
# CA-E14.4: constantes estables entre versiones (INV-E3)
# ---------------------------------------------------------------------------------------------


def test_servicio_del_llavero_es_proxlaunch():
    assert secretos_mod.SERVICIO == "ProxLaunch"
    assert AlmacenSecretos().servicio == "ProxLaunch"


def test_nombre_de_las_carpetas_de_platformdirs_es_proxlaunch():
    assert rutas_mod.NOMBRE_APP == "ProxLaunch"
    assert app_mod.NOMBRE_APP == "ProxLaunch"
    rutas = Rutas()
    assert rutas.directorio_config == Path(platformdirs.user_config_dir("ProxLaunch"))
    assert rutas.directorio_datos == Path(platformdirs.user_data_dir("ProxLaunch"))
    assert rutas.directorio_log == Path(platformdirs.user_log_dir("ProxLaunch"))
    for carpeta in (rutas.directorio_config, rutas.directorio_datos, rutas.directorio_log):
        assert "ProxLaunch" in carpeta.parts


@pytest.mark.skipif(sys.platform == "win32", reason="las rutas de Linux difieren de las de Windows")
def test_carpetas_en_linux_cuelgan_de_proxlaunch_bajo_xdg():
    rutas = Rutas()
    assert rutas.directorio_config.name == "ProxLaunch"
    assert rutas.directorio_datos.name == "ProxLaunch"
    assert rutas.directorio_log.parent.name == "ProxLaunch"


def test_con_base_explicita_todo_cuelga_de_ella(tmp_path):
    rutas = Rutas(tmp_path)
    for ruta in (rutas.perfiles, rutas.huellas, rutas.preferencias, rutas.informes, rutas.lotes):
        assert tmp_path in ruta.parents
    assert rutas.directorio_log == tmp_path / "log"


def test_el_humo_usa_la_misma_fuente_de_nombre_que_el_modo_normal():
    assert humo.NOMBRE_APP == app_mod.NOMBRE_APP == "ProxLaunch"
