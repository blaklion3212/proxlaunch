"""Corrección Q5 del MVP 3 (fase 6): si el diálogo se cierra mientras se escribe un archivo
(exportar perfiles, descargar la plantilla CSV, descargar las filas con error), el resultado no
toca los widgets del diálogo y llega a la ventana principal por ``al_resultado_tardio``: barra de
estado y, si es un error, banner.

La escritura se sustituye por una función que espera una compuerta: así la prueba decide si el
diálogo se cierra antes de que termine el trabajo. Ningún diálogo modal real.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

from proxlaunch.interfaz import archivos_ui
from proxlaunch.interfaz.dialogos import importar_csv as dlg_csv
from proxlaunch.interfaz.dialogos import perfiles_maquina as dlg_perfiles
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv
from proxlaunch.interfaz.dialogos.perfiles_maquina import DialogoPerfilesMaquina, _DialogoExportar
from proxlaunch.interfaz.textos import textos_perfiles_fabrica
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.persistencia.preferencias import Modo

from . import test_ventana_principal as _base
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import conectar3, textos_de_avisos
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_mvp3_filas_csv import csv_de, fila
from .test_mvp3_perfiles_gestor import config_propia

entorno = _base.entorno  # fixture base de la ventana


class Compuerta:
    """Escritura falsa: avisa de que entró y espera a que la prueba la libere."""

    def __init__(self) -> None:
        self.entro = threading.Event()
        self.libre = threading.Event()
        self.error: ErrorProxLaunch | None = None
        self.llamadas = 0

    def funcion(self) -> Callable[..., Any]:
        def _escribir(*_a: Any, **_k: Any) -> Any:
            self.llamadas += 1
            self.entro.set()
            self.libre.wait(timeout=10)
            if self.error is not None:
                raise self.error
            return None

        return _escribir

    def soltar(self, error: ErrorProxLaunch | None = None) -> None:
        self.error = error
        self.libre.set()


@pytest.fixture
def compuerta():
    c = Compuerta()
    yield c
    c.libre.set()  # nunca deja un hilo colgado


def esperar_entrada(qtbot, c: Compuerta) -> None:
    qtbot.waitUntil(c.entro.is_set, timeout=4000)


ERROR_DISCO = ErrorProxLaunch(CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "sin_espacio"})
TEXTO_ERROR_DISCO = "No se pudo guardar el archivo: no hay espacio en el disco."


# --- Gestor de perfiles de máquina, solo (parámetro al_resultado_tardio) -----------------------


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenPerfilesMaquina(
        tmp_path / "perfiles_maquina.json",
        fabrica=perfiles_fabrica(textos_perfiles_fabrica()),
        app_version="0.1.0",
    )
    a.cargar()
    return a


@pytest.fixture
def gestor_con_aviso(qtbot, almacen, modales, archivos, monkeypatch, compuerta, tmp_path):
    """Gestor con un perfil seleccionado, la exportación en la compuerta y un registro de avisos."""
    avisos: list[tuple[str, bool]] = []
    d = DialogoPerfilesMaquina(
        almacen,
        Lanzador(),
        app_version="0.1.0",
        al_resultado_tardio=lambda texto, es_error: avisos.append((texto, es_error)),
    )
    qtbot.addWidget(d)
    d.show()
    perfil = almacen.crear("Propio", "", config_propia())
    d.recargar(perfil.id)
    monkeypatch.setattr(dlg_perfiles, "exportar_perfiles", compuerta.funcion())
    archivos.guardar.append(tmp_path / "salida.proxlaunch-perfiles.json")
    modales.responder(_DialogoExportar, lambda x: x.boton_exportar.click())
    return d, avisos


def test_q5_exportar_con_el_dialogo_abierto_muestra_el_resultado_en_el_dialogo(
    qtbot, gestor_con_aviso, compuerta
):
    d, avisos = gestor_con_aviso
    d.boton_exportar.click()
    esperar_entrada(qtbot, compuerta)
    compuerta.soltar()
    qtbot.waitUntil(lambda: d.estado.text() == "Se exportó 1 perfil.", timeout=4000)
    assert avisos == []  # el aviso a la ventana es solo para el diálogo ya cerrado


def test_q5_exportar_y_cerrar_el_dialogo_entrega_el_exito_a_la_ventana_sin_tocar_widgets(
    qtbot, gestor_con_aviso, compuerta
):
    d, avisos = gestor_con_aviso
    d.boton_exportar.click()
    esperar_entrada(qtbot, compuerta)
    estado_antes = d.estado.text()
    d.reject()
    compuerta.soltar()
    qtbot.waitUntil(lambda: bool(avisos), timeout=4000)
    assert avisos == [("Se exportó 1 perfil.", False)]
    assert d.estado.text() == estado_antes  # los widgets del diálogo cerrado no se tocan


def test_q5_exportar_con_error_y_dialogo_cerrado_entrega_el_error(
    qtbot, gestor_con_aviso, compuerta
):
    d, avisos = gestor_con_aviso
    d.boton_exportar.click()
    esperar_entrada(qtbot, compuerta)
    d.reject()
    compuerta.soltar(ERROR_DISCO)
    qtbot.waitUntil(lambda: bool(avisos), timeout=4000)
    texto, es_error = avisos[0]
    assert es_error and texto.startswith(TEXTO_ERROR_DISCO)


def test_q5_cerrado_sin_callback_el_resultado_se_descarta_sin_excepciones(
    qtbot, almacen, modales, archivos, monkeypatch, compuerta, tmp_path
):
    d = DialogoPerfilesMaquina(almacen, Lanzador(), app_version="0.1.0")
    qtbot.addWidget(d)
    d.show()
    perfil = almacen.crear("Propio", "", config_propia())
    d.recargar(perfil.id)
    monkeypatch.setattr(dlg_perfiles, "exportar_perfiles", compuerta.funcion())
    archivos.guardar.append(tmp_path / "s.proxlaunch-perfiles.json")
    modales.responder(_DialogoExportar, lambda x: x.boton_exportar.click())
    d.boton_exportar.click()
    esperar_entrada(qtbot, compuerta)
    d.reject()
    compuerta.soltar(ERROR_DISCO)
    qtbot.wait(150)  # pytest-qt falla la prueba si el slot lanzó una excepción


def test_q5_al_reabrir_el_dialogo_los_resultados_vuelven_a_sus_widgets(
    qtbot, gestor_con_aviso, compuerta
):
    d, avisos = gestor_con_aviso
    d.reject()
    d.show()  # se reabre: ya no está cerrado
    d.boton_exportar.click()
    esperar_entrada(qtbot, compuerta)
    compuerta.soltar()
    qtbot.waitUntil(lambda: d.estado.text() == "Se exportó 1 perfil.", timeout=4000)
    assert avisos == []


# --- Desde la ventana principal ----------------------------------------------------------------


@pytest.fixture
def conectado(qtbot, entorno3):
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    v.establecer_modo(Modo.AVANZADO)
    return v


def test_q5_ventana_exportar_perfiles_y_cerrar_muestra_el_resultado_en_la_barra_de_estado(
    qtbot, conectado, modales, archivos, monkeypatch, compuerta, tmp_path
):
    v = conectado
    perfil = v._almacen_perfiles.crear("Propio", "", config_propia())
    monkeypatch.setattr(dlg_perfiles, "exportar_perfiles", compuerta.funcion())
    archivos.guardar.append(tmp_path / "salida.proxlaunch-perfiles.json")
    modales.responder(_DialogoExportar, lambda x: x.boton_exportar.click())

    def _exportar_y_cerrar(d: DialogoPerfilesMaquina) -> None:
        d.seleccionar(perfil.id)
        d.boton_exportar.click()
        esperar_entrada(qtbot, compuerta)
        d.reject()

    modales.responder(DialogoPerfilesMaquina, _exportar_y_cerrar)
    v._accion_administrar_perfiles.trigger()
    compuerta.soltar()
    qtbot.waitUntil(lambda: v.statusBar().currentMessage() == "Se exportó 1 perfil.", timeout=4000)
    assert v._errores_sesion == []


def test_q5_ventana_exportar_perfiles_con_error_y_cerrar_muestra_un_banner(
    qtbot, conectado, modales, archivos, monkeypatch, compuerta, tmp_path
):
    v = conectado
    perfil = v._almacen_perfiles.crear("Propio", "", config_propia())
    monkeypatch.setattr(dlg_perfiles, "exportar_perfiles", compuerta.funcion())
    archivos.guardar.append(tmp_path / "salida.proxlaunch-perfiles.json")
    modales.responder(_DialogoExportar, lambda x: x.boton_exportar.click())

    def _exportar_y_cerrar(d: DialogoPerfilesMaquina) -> None:
        d.seleccionar(perfil.id)
        d.boton_exportar.click()
        esperar_entrada(qtbot, compuerta)
        d.reject()

    modales.responder(DialogoPerfilesMaquina, _exportar_y_cerrar)
    v._accion_administrar_perfiles.trigger()
    compuerta.soltar(ERROR_DISCO)
    qtbot.waitUntil(lambda: bool(v._errores_sesion), timeout=4000)
    assert TEXTO_ERROR_DISCO in textos_de_avisos(v)
    assert v.statusBar().currentMessage().startswith(TEXTO_ERROR_DISCO)


# --- Diálogo de importación CSV: plantilla y filas con error ------------------------------------


def abrir_importacion(
    qtbot, v, archivos, modales, ruta, accion: Callable[[DialogoImportarCsv], None]
):
    """«Importar desde CSV…»: espera la lectura, ejecuta ``accion`` y rechaza el diálogo."""
    archivos.abrir.append(ruta)

    def _ante(d: DialogoImportarCsv) -> None:
        qtbot.waitUntil(lambda: not d.ocupado and d.resultado is not None, timeout=5000)
        accion(d)
        d.reject()

    modales.responder(DialogoImportarCsv, _ante)
    v._accion_importar_csv.trigger()


def csv_con_error(tmp_path):
    return csv_de(tmp_path, fila("web-01"), fila("web-02", nucleos="abc"))


def test_q5_plantilla_con_el_dialogo_abierto_se_informa_en_el_dialogo(
    qtbot, entorno3, modales, archivos, monkeypatch, compuerta, tmp_path
):
    v = entorno3.ventana
    monkeypatch.setattr(archivos_ui, "pedir_separador_plantilla", lambda parent: ";")
    monkeypatch.setattr(archivos_ui, "escribir_plantilla", compuerta.funcion())
    archivos.guardar.append(tmp_path / "plantilla.csv")
    visto: dict[str, str] = {}

    def _plantilla_y_esperar(d: DialogoImportarCsv) -> None:
        d.boton_plantilla.click()
        esperar_entrada(qtbot, compuerta)
        compuerta.soltar()
        qtbot.waitUntil(lambda: d.estado_operacion.text() != "", timeout=4000)
        visto["estado"] = d.estado_operacion.text()

    abrir_importacion(
        qtbot, v, archivos, modales, csv_de(tmp_path, fila("web-01")), _plantilla_y_esperar
    )
    assert visto["estado"] == "Se guardó la plantilla."
    assert v.statusBar().currentMessage() == "Sin conexión"  # nada llegó a la ventana


def test_q5_plantilla_y_cerrar_el_dialogo_se_informa_en_la_ventana(
    qtbot, entorno3, modales, archivos, monkeypatch, compuerta, tmp_path
):
    v = entorno3.ventana
    monkeypatch.setattr(archivos_ui, "pedir_separador_plantilla", lambda parent: ";")
    monkeypatch.setattr(archivos_ui, "escribir_plantilla", compuerta.funcion())
    archivos.guardar.append(tmp_path / "plantilla.csv")

    def _lanzar(d: DialogoImportarCsv) -> None:
        d.boton_plantilla.click()
        esperar_entrada(qtbot, compuerta)

    abrir_importacion(qtbot, v, archivos, modales, csv_de(tmp_path, fila("web-01")), _lanzar)
    compuerta.soltar()
    qtbot.waitUntil(
        lambda: v.statusBar().currentMessage() == "Se guardó la plantilla.", timeout=4000
    )
    assert v._errores_sesion == []


def test_q5_plantilla_con_error_y_dialogo_cerrado_muestra_un_banner(
    qtbot, entorno3, modales, archivos, monkeypatch, compuerta, tmp_path
):
    v = entorno3.ventana
    monkeypatch.setattr(archivos_ui, "pedir_separador_plantilla", lambda parent: ";")
    monkeypatch.setattr(archivos_ui, "escribir_plantilla", compuerta.funcion())
    archivos.guardar.append(tmp_path / "plantilla.csv")

    def _lanzar(d: DialogoImportarCsv) -> None:
        d.boton_plantilla.click()
        esperar_entrada(qtbot, compuerta)

    abrir_importacion(qtbot, v, archivos, modales, csv_de(tmp_path, fila("web-01")), _lanzar)
    compuerta.soltar(ERROR_DISCO)
    qtbot.waitUntil(lambda: bool(v._errores_sesion), timeout=4000)
    assert TEXTO_ERROR_DISCO in textos_de_avisos(v)


def test_q5_filas_con_error_y_cerrar_el_dialogo_se_informa_en_la_ventana(
    qtbot, entorno3, modales, archivos, monkeypatch, compuerta, tmp_path
):
    v = entorno3.ventana
    monkeypatch.setattr(dlg_csv, "escribir_filas_con_error", compuerta.funcion())
    archivos.guardar.append(tmp_path / "errores.csv")

    def _lanzar(d: DialogoImportarCsv) -> None:
        assert d.hay_errores and d.boton_errores.isEnabled()
        d.boton_errores.click()
        esperar_entrada(qtbot, compuerta)

    abrir_importacion(qtbot, v, archivos, modales, csv_con_error(tmp_path), _lanzar)
    compuerta.soltar()
    qtbot.waitUntil(
        lambda: v.statusBar().currentMessage() == "Se guardó el archivo con las filas con error.",
        timeout=4000,
    )
    assert v._errores_sesion == []


def test_q5_filas_con_error_fallo_y_dialogo_cerrado_muestra_un_banner(
    qtbot, entorno3, modales, archivos, monkeypatch, compuerta, tmp_path
):
    v = entorno3.ventana
    monkeypatch.setattr(dlg_csv, "escribir_filas_con_error", compuerta.funcion())
    archivos.guardar.append(tmp_path / "errores.csv")

    def _lanzar(d: DialogoImportarCsv) -> None:
        d.boton_errores.click()
        esperar_entrada(qtbot, compuerta)

    abrir_importacion(qtbot, v, archivos, modales, csv_con_error(tmp_path), _lanzar)
    compuerta.soltar(ERROR_DISCO)
    qtbot.waitUntil(lambda: bool(v._errores_sesion), timeout=4000)
    assert TEXTO_ERROR_DISCO in textos_de_avisos(v)
    assert v.statusBar().currentMessage().startswith(TEXTO_ERROR_DISCO)
