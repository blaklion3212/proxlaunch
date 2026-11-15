# -*- mode: python ; coding: utf-8 -*-
# Especificación de PyInstaller para ProxLaunch (AR-2, RF-E06/E08/E09/E19/E23).
#
# Modo --onedir (Qt como bibliotecas separadas y reemplazables, LGPL: CA-E23.2). La invoca
# construir-linux.sh; requiere haber compilado el .qm (compilar_qm.py) y generado
# build/THIRD-PARTY-NOTICES.txt (avisos.py) antes.
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

RAIZ = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH lo define PyInstaller
SRC = RAIZ / "src"
PAQUETE = SRC / "proxlaunch"
AVISOS = RAIZ / "build" / "THIRD-PARTY-NOTICES.txt"
ES_WINDOWS = sys.platform == "win32"


def recursos_del_paquete():
    """Archivos de datos según [tool.setuptools.package-data] más el .qm (sin .ts, CA-E19.2)."""
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text("utf-8"))
    patrones = pyproject["tool"]["setuptools"]["package-data"]["proxlaunch"]
    datos = []
    for patron in patrones:
        for ruta in sorted(PAQUETE.glob(patron)):
            if not ruta.is_file() or ruta.suffix == ".ts":
                continue
            destino = Path("proxlaunch") / ruta.parent.relative_to(PAQUETE)
            datos.append((str(ruta), destino.as_posix()))
    qm = PAQUETE / "recursos" / "traducciones" / "proxlaunch_es.qm"
    if not qm.is_file() or qm.stat().st_size == 0:
        raise SystemExit("falta proxlaunch_es.qm: ejecute empaquetado/comun/compilar_qm.py")
    datos.append((str(qm), "proxlaunch/recursos/traducciones"))
    return datos


if not AVISOS.is_file():
    raise SystemExit("falta build/THIRD-PARTY-NOTICES.txt: ejecute empaquetado/comun/avisos.py")

datas = recursos_del_paquete()
datas += [(str(RAIZ / "LICENSE"), "."), (str(AVISOS), ".")]

# keyring elige su backend por puntos de entrada de los metadatos (HV-E5): se copian los de
# keyring y los de los paquetes de cada backend.
paquetes_metadatos = ["keyring", "jaraco.classes", "jaraco.functools", "jaraco.context"]
paquetes_metadatos += ["pywin32-ctypes"] if ES_WINDOWS else ["secretstorage", "jeepney"]
for nombre in paquetes_metadatos:
    datas += copy_metadata(nombre)

hiddenimports = collect_submodules("keyring.backends")
hiddenimports += ["proxlaunch.interfaz.app"]

# Solo Core, Gui, Widgets y Svg (H3): fuera el resto de módulos de Qt y de la biblioteca estándar
# que la aplicación no usa.
excluir_qt = [
    "QtNetwork", "QtQml", "QtQuick", "QtQuickWidgets", "QtQuickControls2", "QtWebEngineCore",
    "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel", "QtWebSockets", "QtMultimedia",
    "QtMultimediaWidgets", "QtPdf", "QtPdfWidgets", "QtOpenGL", "QtOpenGLWidgets", "QtSql",
    "QtTest", "QtXml", "QtDBus", "QtConcurrent", "QtDesigner", "QtHelp", "QtPrintSupport",
    "QtStateMachine", "QtSvgWidgets", "QtUiTools", "QtBluetooth", "QtNfc", "QtPositioning",
    "QtSensors", "QtSerialPort", "QtCharts", "QtDataVisualization", "Qt3DCore", "QtRemoteObjects",
    "QtScxml", "QtTextToSpeech", "QtSpatialAudio", "QtHttpServer", "QtGraphs", "QtLocation",
]  # fmt: skip
excludes = [f"PySide6.{m}" for m in excluir_qt]
excludes += ["tkinter", "test", "tests", "pydoc_data", "lib2to3", "idlelib", "turtledemo"]
excludes += ["proxlaunch_tests", "pytest", "mypy", "ruff"]

# Plugins de plataforma que se conservan (RF-E08): xcb y offscreen en Linux; qwindows en Windows.
PLATAFORMAS_OK = ("libqxcb", "libqoffscreen") if not ES_WINDOWS else ("qwindows", "qoffscreen")
# Bibliotecas de Qt y plugins que se descartan aunque algún gancho los arrastre.
DESCARTAR_RUTAS = (
    "PySide6/Qt/translations",
    "PySide6/Qt/qml",
    "PySide6/Qt/metatypes",
    "PySide6/Qt/libexec",
    "PySide6/Qt/plugins/egldeviceintegrations",
    "PySide6/Qt/plugins/xcbglintegrations",
    "PySide6/Qt/plugins/wayland",
    "PySide6/Qt/plugins/platforminputcontexts",
    "PySide6/Qt/plugins/networkinformation",
    "PySide6/Qt/plugins/tls",
    "PySide6/Qt/plugins/sqldrivers",
    "PySide6/Qt/plugins/printsupport",
    "PySide6/Qt/plugins/multimedia",
    "PySide6/Qt/plugins/generic",
    "libqgtk3",  # tema GTK3: arrastra GTK, Cairo, Pango... (decenas de MB); basta el portal XDG
)
# Bibliotecas de sistema que solo arrastraba el tema GTK3 o Wayland/EGLFS (no usados).
DESCARTAR_BIBLIOTECAS = (
    "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libatk", "libatspi", "libcairo", "libpango",
    "libepoxy", "libcolord", "libcups", "libwayland", "libQt6Wayland", "libQt6WlShell",
    "libQt6EglFS", "libQt6EglFs", "libQt6OpenGL", "libQt6Network",
)  # fmt: skip


def _descartar(destino: str) -> bool:
    d = destino.replace("\\", "/")
    nombre = Path(d).name
    if any(r in d for r in DESCARTAR_RUTAS):
        return True
    if not ES_WINDOWS and nombre.startswith(DESCARTAR_BIBLIOTECAS):
        return True
    if "PySide6/Qt/plugins/platforms/" in d:
        return not nombre.startswith(PLATAFORMAS_OK)
    return d.endswith((".debug", ".pyi", ".qmltypes"))


a = Analysis(  # noqa: F821
    [str(RAIZ / "empaquetado" / "entrada.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
a.datas = [d for d in a.datas if not _descartar(d[0])]
a.binaries = [b for b in a.binaries if not _descartar(b[0])]
if not ES_WINDOWS:
    # Las bibliotecas del sistema no se copian: dependen del equipo de construcción y se declaran
    # como Depends del .deb (lo calcula y comprueba comun/dependencias_deb.py), de modo que el
    # contenido del congelado no cambia según lo que haya instalado en la máquina de build.
    PREFIJOS_SISTEMA = ("/lib/", "/lib64/", "/usr/lib/", "/usr/lib64/", "/usr/local/lib/")
    a.binaries = [b for b in a.binaries if not str(b[1]).startswith(PREFIJOS_SISTEMA)]

pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="proxlaunch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=not ES_WINDOWS,  # Windows: sin consola; --version escribe en PROXLAUNCH_HUMO_SALIDA
    icon=str(RAIZ / "build" / "iconos" / "proxlaunch.ico") if ES_WINDOWS else None,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="proxlaunch",
)
