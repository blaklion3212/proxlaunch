"""Apoyo de las pruebas de interfaz del MVP 3 (perfiles, lotes guardados, CSV y lote por filas).

Solo contiene piezas de los límites del sistema: diálogos modales y de archivo sustituidos, rutas
temporales y dobles del servidor. No contiene aserciones de las pruebas.

Regla de oro: ninguna prueba abre un diálogo modal real. ``Modales`` sustituye ``exec`` de todos
los diálogos y falla con un error claro si aparece uno que la prueba no previó.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QWidget,
)

from proxlaunch.interfaz import archivos_ui
from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos import importar_csv as dlg_csv
from proxlaunch.interfaz.dialogos import importar_perfiles as dlg_imp_perfiles
from proxlaunch.interfaz.dialogos import perfiles_maquina as dlg_perfiles

from .apoyo import ClienteLoteFalso, sesion_falsa
from .apoyo_ventana_lote import escribir  # noqa: F401  (se reexporta para las pruebas)
from .test_ventana_principal import conectar, esperar_validacion


class Modales:
    """Registro y control de todos los diálogos modales de una prueba.

    ``responder(Clase, función)`` programa qué hace la prueba cuando se intenta ejecutar un
    diálogo de esa clase (la función recibe el diálogo; puede pulsar botones o aceptar). Si la
    función no deja resultado, el diálogo se considera rechazado. Un diálogo sin regla hace
    fallar la prueba: nunca se abre uno real.
    """

    def __init__(self) -> None:
        self._reglas: list[tuple[type, Callable[[Any], Any]]] = []
        self.vistos: list[Any] = []
        self.textos_vistos: list[str] = []

    def responder(self, clase: type, funcion: Callable[[Any], Any]) -> None:
        self._reglas.append((clase, funcion))

    def pulsar(self, clase: type, texto: str) -> None:
        """Atajo: ante un diálogo de ``clase`` pulsa el botón cuyo texto es ``texto``."""
        self.responder(clase, lambda d: pulsar_boton(d, texto))

    def de_clase(self, clase: type) -> list[Any]:
        return [d for d in self.vistos if isinstance(d, clase)]

    def ejecutar(self, dialogo: Any) -> int:
        self.vistos.append(dialogo)
        if isinstance(dialogo, QMessageBox):
            self.textos_vistos.append(dialogo.text())
        for clase, funcion in reversed(self._reglas):
            if isinstance(dialogo, clase):
                funcion(dialogo)
                return int(dialogo.result())
        raise AssertionError(f"Diálogo modal sin previsión en la prueba: {type(dialogo).__name__}")


def botones_de(dialogo: QWidget) -> list[QAbstractButton]:
    return dialogo.findChildren(QAbstractButton)


def pulsar_boton(dialogo: QWidget, texto: str) -> None:
    """Pulsa el botón del diálogo cuyo texto (sin atajos «&») coincide exactamente."""
    for b in botones_de(dialogo):
        if b.text().replace("&", "") == texto:
            b.click()
            return
    textos = [b.text() for b in botones_de(dialogo)]
    raise AssertionError(f"No hay un botón «{texto}» en {type(dialogo).__name__}: {textos}")


class Archivos:
    """Sustituye los diálogos de archivo del sistema: devuelve rutas programadas por la prueba."""

    def __init__(self) -> None:
        self.abrir: list[Path | None] = []
        self.guardar: list[Path | None] = []
        self.pedidos_abrir: list[Any] = []
        self.pedidos_guardar: list[tuple[Any, ...]] = []

    def _abrir(self, parent: Any, tipo: Any) -> Path | None:
        self.pedidos_abrir.append(tipo)
        if not self.abrir:
            raise AssertionError("Se pidió abrir un archivo y la prueba no programó ninguno")
        return self.abrir.pop(0)

    def _guardar(self, parent: Any, tipo: Any, nombre: str, carpeta: Path | None = None) -> Any:
        self.pedidos_guardar.append((tipo, nombre, carpeta))
        if not self.guardar:
            raise AssertionError("Se pidió guardar un archivo y la prueba no programó ninguno")
        return self.guardar.pop(0)


@pytest.fixture
def modales(monkeypatch) -> Modales:
    """Ningún diálogo modal real: todo ``exec`` pasa por el registro de la prueba."""
    m = Modales()

    def _exec(self, *a: Any, **k: Any) -> int:
        return m.ejecutar(self)

    for clase in (QDialog, QMessageBox, QFileDialog, QInputDialog):
        monkeypatch.setattr(clase, "exec", _exec, raising=False)

    def _prohibido(*a: Any, **k: Any) -> Any:
        raise AssertionError("Diálogo estático del sistema sin previsión en la prueba")

    for clase, nombres in (
        (QFileDialog, ("getOpenFileName", "getSaveFileName", "getExistingDirectory")),
        (QInputDialog, ("getItem", "getText", "getInt")),
    ):
        for nombre in nombres:
            monkeypatch.setattr(clase, nombre, staticmethod(_prohibido))
    return m


@pytest.fixture
def archivos(monkeypatch) -> Archivos:
    """Diálogos de archivo sustituidos en todos los módulos que los importan por nombre."""
    a = Archivos()
    archivos_ui.olvidar_carpeta()
    for modulo in (archivos_ui, vp, dlg_csv, dlg_perfiles, dlg_imp_perfiles):
        if hasattr(modulo, "elegir_para_abrir"):
            monkeypatch.setattr(modulo, "elegir_para_abrir", a._abrir)
        if hasattr(modulo, "elegir_para_guardar"):
            monkeypatch.setattr(modulo, "elegir_para_guardar", a._guardar)
    yield a
    archivos_ui.olvidar_carpeta()


@pytest.fixture
def entorno3(entorno, modales, archivos, tmp_path):
    """El ``entorno`` de la ventana con carpeta de lotes temporal y diálogos controlados."""
    entorno.deps.directorio_lotes = tmp_path / "lotes"
    entorno.tmp = tmp_path
    return entorno


@pytest.fixture
def cliente_falso() -> ClienteLoteFalso:
    return ClienteLoteFalso()


def conectar3(
    qtbot, entorno, cliente: ClienteLoteFalso | None = None, **kw: Any
) -> ClienteLoteFalso:
    """Conecta con un cliente falso que anota cualquier escritura (``crear_vm``)."""
    cliente = cliente or ClienteLoteFalso()
    entorno.cliente = cliente
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente, **kw))
    esperar_validacion(qtbot, entorno.ventana)
    return cliente


def hubo_escritura(cliente: ClienteLoteFalso) -> bool:
    """¿Se envió alguna escritura (creación o eliminación) al servidor falso?"""
    return bool(cliente.creados or cliente.eliminados) or any(
        ll[0] in ("crear_vm", "eliminar_vm") for ll in cliente.llamadas
    )


def csv_texto(filas: Iterable[Iterable[Any]], *, sep: str = ";") -> str:
    """Texto CSV (CRLF, como Excel) a partir de filas de valores.

    Es la ENTRADA que simula un archivo de usuario (comillas solo donde hacen falta). La aplicación
    escribe sus propios CSV con ``QUOTE_ALL``: las pruebas de salida lo comprueban aparte.
    """
    salida = io.StringIO()
    csv.writer(salida, delimiter=sep, lineterminator="\r\n").writerows(filas)
    return salida.getvalue()


ENCABEZADO_CSV = ("nombre", "nucleos", "memoria", "disco", "almacenamiento", "red", "vmid", "nodo")


def escribir_csv(ruta: Path, filas: Iterable[Iterable[Any]], *, sep: str = ";") -> Path:
    """Escribe un CSV UTF-8 con BOM en ``ruta`` (el formato típico de Excel)."""
    ruta.write_bytes(b"\xef\xbb\xbf" + csv_texto(filas, sep=sep).encode("utf-8"))
    return ruta


def csv_valido(ruta: Path, n: int = 4, **extra: Any) -> Path:
    """CSV con ``n`` máquinas válidas sobre el inventario de clúster de las pruebas."""
    filas: list[list[Any]] = [list(ENCABEZADO_CSV)]
    for i in range(n):
        filas.append(
            [f"web-{i + 1:02d}", 2 + i % 3, "2 GiB", "20 GiB", "local-lvm", "vmbr0", "", ""]
        )
    return escribir_csv(ruta, filas, **extra)


def importar_csv_por_menu(qtbot, entorno, modales: Modales, archivos: Archivos, ruta: Path) -> None:
    """Hace lo que haría el usuario: «Lote > Importar desde CSV…», elegir el archivo y «Continuar».

    El diálogo modal se simula: se espera a que termine la lectura (hilo) y se pulsa «Continuar».
    """
    archivos.abrir.append(ruta)

    def _continuar(d: Any) -> None:
        qtbot.waitUntil(lambda: not d.ocupado and d.resultado is not None, timeout=5000)
        d.boton_continuar.click()

    modales.responder(dlg_csv.DialogoImportarCsv, _continuar)
    entorno.ventana._accion_importar_csv.trigger()
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.bloque_lote.es_por_filas, timeout=5000)
    esperar_validacion(qtbot, v)


# --- Archivos de lote guardado (construidos con el núcleo, no con la interfaz) ------------------


def escribir_lote_guardado(
    ruta: Path, definicion: Any, nombre: str = "lote de prueba", version_proxmox: str | None = "9.2"
) -> Path:
    """Escribe un lote guardado válido con el escritor del núcleo."""
    from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote
    from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado

    guardar_lote(ruta, LoteGuardado(nombre, definicion, version_proxmox), app_version="0.1.0")
    return ruta


def definicion_homogenea(
    cantidad: int = 3,
    prefijo: str = "web",
    *,
    storage: str = "local-lvm",
    bridge: str = "vmbr0",
    nodo: str | None = "pve1",
) -> Any:
    """Definición homogénea sobre el inventario de clúster (``nodo=None``: destino automático)."""
    from proxlaunch.nucleo.lote.modelos import Destino, ModoDestino
    from proxlaunch.nucleo.modelos.vm import Disco, InterfazRed

    from .apoyo_lote import cfg_simple, definicion

    plantilla = cfg_simple()
    plantilla.discos = [Disco(storage, 10)]
    plantilla.redes = [InterfazRed(bridge)]
    destino = (
        Destino(ModoDestino.UN_NODO, (nodo,))
        if nodo is not None
        else Destino(ModoDestino.AUTOMATICO, ())
    )
    return definicion(cantidad, prefijo, plantilla=plantilla, destino=destino)


def definicion_filas(filas: list[dict[str, Any]]) -> Any:
    """Lote por filas. Cada fila: ``nombre``, y opcionalmente ``origen``, ``vmid``, ``nodo``,
    ``storage``, ``bridge``, ``cores``, ``gib``."""
    from proxlaunch.nucleo.lote.filas import definicion_por_filas
    from proxlaunch.nucleo.lote.modelos import FilaLote
    from proxlaunch.nucleo.modelos.vm import Disco, InterfazRed

    from .apoyo_lote import cfg_simple

    lista = []
    for d in filas:
        cfg = cfg_simple(cores=d.get("cores", 2))
        cfg.discos = [Disco(d.get("storage", "local-lvm"), d.get("gib", 10))]
        cfg.redes = [InterfazRed(d.get("bridge", "vmbr0"))]
        lista.append(FilaLote(d["nombre"], cfg, d.get("vmid"), d.get("nodo"), d.get("origen")))
    return definicion_por_filas(lista, plantilla_base=cfg_simple())


def todos_los_textos(raiz: QWidget, *, solo_visibles: bool = True) -> str:
    """Texto de los widgets bajo ``raiz`` (etiquetas, botones, títulos, cuadros de texto)."""
    from PySide6.QtWidgets import QCheckBox, QGroupBox, QLabel, QPlainTextEdit, QPushButton

    partes: list[str] = []
    for w in raiz.findChildren(QWidget):
        if solo_visibles and not w.isVisibleTo(raiz):
            continue
        if isinstance(w, (QLabel, QPushButton, QCheckBox)):
            partes.append(w.text())
        elif isinstance(w, QGroupBox):
            partes.append(w.title())
        elif isinstance(w, QPlainTextEdit):
            partes.append(w.toPlainText())
    return "\n".join(p for p in partes if p)


def textos_de_avisos(v: Any) -> str:
    """Todo lo que la ventana muestra como aviso o error de sesión (banners y barra de estado)."""
    return todos_los_textos(v) + "\n" + v.statusBar().currentMessage()


def inventario_cluster_otros_nodos() -> Any:
    """Otro clúster con la misma forma que el de las pruebas pero nodos distintos (n1, n2, n3)."""
    from dataclasses import replace

    from .apoyo import inventario_cluster

    inv = inventario_cluster()
    nombres = {"pve1": "n1", "pve2": "n2", "pve3": "n3"}
    nodos = tuple(replace(n, nombre=nombres[n.nombre]) for n in inv.topologia.nodos)
    return replace(
        inv,
        topologia=replace(inv.topologia, nombre_cluster="otro", nodos=nodos),
        storages={nombres[k]: v for k, v in inv.storages.items()},
        bridges={nombres[k]: v for k, v in inv.bridges.items()},
    )


def cierre_sin_preguntar_al_terminar(request: pytest.FixtureRequest, ventana: QWidget) -> None:
    """Hace que pytest-qt cierre ``ventana`` sin la pregunta de cambios sin guardar.

    pytest-qt cierra los widgets registrados ANTES de desmontar los fixtures; si una prueba deja la
    ventana con cambios pendientes y sus respuestas programadas, ese cierre automático volvería a
    preguntar. Se sustituye la función previa de cierre de esa ventana por una que da por
    confirmado el cierre.
    """
    item = request.node
    registrados = getattr(item, "qt_widgets", [])

    def _confirmar(w: Any) -> None:
        w._cierre_confirmado = True

    item.qt_widgets = [
        (ref, _confirmar if ref() is ventana else antes) for ref, antes in registrados
    ]
