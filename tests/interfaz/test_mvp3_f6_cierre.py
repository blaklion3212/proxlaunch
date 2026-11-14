"""Correcciones Q6 y Q7 del MVP 3 (fase 6): salir del lote por filas y cerrar con «Guardar»
(RF-G08, CA-G08.x).

Q6: «Salir del lote por filas» pregunta «¿Guardar el lote antes de continuar?» y, al salir, la base
de «cambios sin guardar» es la del formulario. Q7: con «Guardar y cerrar» la ventana se deshabilita
mientras se escribe, un segundo cierre se ignora (sin segunda pregunta ni segundo cierre), un fallo
rehabilita la ventana y un cierre que acaba ignorado no deja confirmada la salida.

La pregunta real se restaura con el fixture ``pregunta_real``; todo diálogo pasa por ``modales``.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from PySide6.QtWidgets import QMessageBox

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.guardar_lote import DialogoGuardarLote
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

from . import test_ventana_principal as _base
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import (
    cierre_sin_preguntar_al_terminar,
    conectar3,
    importar_csv_por_menu,
    textos_de_avisos,
)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_mvp3_cambios_sin_guardar import Pregunta, editar_a_mano
from .test_mvp3_cambios_sin_guardar import pregunta_real as pregunta_real  # noqa: F401  (fixture)
from .test_mvp3_filas_csv import csv_de, fila

entorno = _base.entorno  # fixture base de la ventana


@pytest.fixture
def conectado(request, qtbot, entorno3, pregunta_real):  # noqa: F811
    cliente = conectar3(qtbot, entorno3)
    cierre_sin_preguntar_al_terminar(request, entorno3.ventana)
    return entorno3.ventana, cliente


def aceptar_guardado(modales, nombre: str = "lote de prueba") -> None:
    """El diálogo «Guardar lote» se acepta con ese nombre."""

    def _aceptar(d: DialogoGuardarLote) -> None:
        d.campo_nombre.setText(nombre)
        d.boton_aceptar.click()

    modales.responder(DialogoGuardarLote, _aceptar)


# --- Q6: salir del lote por filas --------------------------------------------------------------


@pytest.fixture
def por_filas(qtbot, conectado, entorno3, modales, archivos, tmp_path):
    v, _ = conectado
    ruta = csv_de(
        tmp_path,
        fila("web-01", 4, "4 GiB"),
        fila("web-02", 4, "2 GiB", nodo="pve1"),
        fila("db-01", 8, "2 GiB", nodo="pve3"),
    )
    importar_csv_por_menu(qtbot, entorno3, modales, archivos, ruta)
    assert v.bloque_lote.es_por_filas and v._hay_cambios_sin_guardar()
    return v


def test_q6_salir_del_lote_por_filas_pregunta_con_las_tres_opciones(por_filas, modales):
    v = por_filas
    pregunta = Pregunta(modales, "Cancelar")
    v.panel_filas.boton_salir.click()
    assert pregunta.veces == 1
    assert pregunta.texto == "¿Guardar el lote antes de continuar?"
    assert sorted(pregunta.botones) == ["Cancelar", "Guardar", "No guardar"]
    assert pregunta.defecto == "Cancelar"


def test_q6_cancelar_se_queda_en_el_lote_por_filas_con_todo_intacto(por_filas, modales):
    v = por_filas
    huella = v._huella_guardada
    nombres = [f.nombre for f in v._definicion_actual().filas]
    Pregunta(modales, "Cancelar")
    v.panel_filas.boton_salir.click()
    assert v.bloque_lote.es_por_filas and v._origen_lote is not None
    assert [f.nombre for f in v._definicion_actual().filas] == nombres
    assert v._huella_guardada == huella and v._hay_cambios_sin_guardar()


def test_q6_no_guardar_sale_sin_escribir_y_deja_la_huella_del_formulario(
    por_filas, modales, archivos, tmp_path
):
    v = por_filas
    antes = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    Pregunta(modales, "No guardar")
    v.panel_filas.boton_salir.click()
    assert not v.bloque_lote.es_por_filas and v._origen_lote is None and v._ruta_lote is None
    assert not v._hay_cambios_sin_guardar()
    assert v._huella_guardada == v._huella_de(v._definicion_actual())
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == antes
    assert archivos.pedidos_guardar == []


def test_q6_guardar_escribe_el_lote_y_despues_sale(por_filas, qtbot, modales, archivos, tmp_path):
    v = por_filas
    destino = tmp_path / "filas.proxlaunch-lote.json"
    Pregunta(modales, "Guardar")
    aceptar_guardado(modales)
    archivos.guardar.append(destino)
    v.panel_filas.boton_salir.click()
    qtbot.waitUntil(lambda: not v.bloque_lote.es_por_filas, timeout=4000)
    assert destino.is_file()
    assert not v._hay_cambios_sin_guardar()
    assert v._huella_guardada == v._huella_de(v._definicion_actual())


def test_q6_guardar_cancelado_en_el_selector_de_ruta_no_sale(por_filas, qtbot, modales, archivos):
    v = por_filas
    Pregunta(modales, "Guardar")
    aceptar_guardado(modales)
    archivos.guardar.append(None)  # el usuario cancela la ruta
    v.panel_filas.boton_salir.click()
    qtbot.wait(100)
    assert v.bloque_lote.es_por_filas and v._hay_cambios_sin_guardar()


def test_q6_sin_cambios_pendientes_no_pregunta(por_filas, qtbot, modales, archivos, tmp_path):
    v = por_filas
    Pregunta(modales, "No guardar")
    v.panel_filas.boton_salir.click()  # primera salida: descarta
    assert not v.bloque_lote.es_por_filas
    pregunta = Pregunta(modales, "Cancelar")
    v.panel_filas.boton_salir.click()  # ya no está en filas: el botón no hace nada
    assert pregunta.veces == 0


# --- Q7: cierre con «Guardar» ------------------------------------------------------------------


class EscrituraControlada:
    """Sustituye el escritor de lotes: espera una compuerta y luego escribe de verdad o falla."""

    def __init__(self, monkeypatch) -> None:
        self.real = vp.guardar_lote_guardado
        self.entro = threading.Event()
        self.libre = threading.Event()
        self.error: ErrorProxLaunch | None = None
        self.llamadas = 0
        monkeypatch.setattr(vp, "guardar_lote_guardado", self._escribir)

    def _escribir(self, *args: Any, **kwargs: Any) -> Any:
        self.llamadas += 1
        self.entro.set()
        self.libre.wait(timeout=10)
        if self.error is not None:
            raise self.error
        return self.real(*args, **kwargs)

    def soltar(self, error: ErrorProxLaunch | None = None) -> None:
        self.error = error
        self.libre.set()


@pytest.fixture
def escritura(monkeypatch):
    e = EscrituraControlada(monkeypatch)
    yield e
    e.libre.set()


def cerrar_pidiendo_guardar(qtbot, v, modales, archivos, escritura, tmp_path):
    """Edición manual + cierre + «Guardar»: deja la escritura detenida en la compuerta."""
    editar_a_mano(qtbot, v)
    pregunta = Pregunta(modales, "Guardar")
    aceptar_guardado(modales)
    destino = tmp_path / "cierre.proxlaunch-lote.json"
    archivos.guardar.append(destino)
    assert v.close() is False  # el cierre espera a que termine el guardado
    qtbot.waitUntil(escritura.entro.is_set, timeout=4000)
    return pregunta, destino


def test_q7_mientras_se_escribe_la_ventana_esta_deshabilitada(
    qtbot, conectado, modales, archivos, escritura, tmp_path
):
    v, _ = conectado
    cerrar_pidiendo_guardar(qtbot, v, modales, archivos, escritura, tmp_path)
    assert v._guardando_para_cerrar and not v.isEnabled() and v.isVisible()
    escritura.soltar()
    qtbot.waitUntil(lambda: not v.isVisible(), timeout=4000)


def test_q7_un_segundo_cierre_durante_la_escritura_no_pregunta_ni_cierra_dos_veces(
    qtbot, conectado, modales, archivos, escritura, tmp_path, monkeypatch
):
    v, _ = conectado
    cierres: list[int] = []
    original = vp.VentanaPrincipal._cerrar_confirmado

    def _contar(self=None) -> None:
        cierres.append(1)
        original(v)

    monkeypatch.setattr(v, "_cerrar_confirmado", _contar)
    pregunta, destino = cerrar_pidiendo_guardar(qtbot, v, modales, archivos, escritura, tmp_path)
    assert pregunta.veces == 1
    assert v.close() is False and v.close() is False  # ignorados mientras se escribe
    assert pregunta.veces == 1 and escritura.llamadas == 1 and cierres == []
    assert v.isVisible()
    escritura.soltar()
    qtbot.waitUntil(lambda: not v.isVisible(), timeout=4000)
    assert cierres == [1]  # un único cierre
    assert escritura.llamadas == 1 and destino.is_file()
    assert pregunta.veces == 1


def test_q7_si_la_escritura_falla_la_ventana_se_rehabilita_y_sigue_abierta(
    qtbot, conectado, modales, archivos, escritura, tmp_path
):
    v, _ = conectado
    pregunta, destino = cerrar_pidiendo_guardar(qtbot, v, modales, archivos, escritura, tmp_path)
    escritura.soltar(ErrorProxLaunch(CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "sin_espacio"}))
    qtbot.waitUntil(lambda: v.isEnabled(), timeout=4000)
    assert v.isVisible() and not v._guardando_para_cerrar
    assert "No se pudo guardar el archivo" in textos_de_avisos(v)
    assert not destino.exists()
    assert v._hay_cambios_sin_guardar()  # el lote no se guardó: sigue pendiente
    # Cerrar de nuevo vuelve a preguntar (no quedó un cierre «confirmado» a medias).
    segunda = Pregunta(modales, "Cancelar")
    assert v.close() is False
    assert pregunta.veces == 1 and segunda.veces == 1


def test_q7_un_cierre_que_acaba_ignorado_no_deja_confirmada_la_salida(
    qtbot, conectado, modales, archivos, escritura, tmp_path, monkeypatch
):
    v, _ = conectado
    preguntas: list[str] = []

    def _no_cerrar(parent, titulo, *a, **k):
        preguntas.append(titulo)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", _no_cerrar)
    cerrar_pidiendo_guardar(qtbot, v, modales, archivos, escritura, tmp_path)
    v._creando = True  # una creación en curso: al terminar el guardado, cerrar pide confirmar
    escritura.soltar()
    qtbot.waitUntil(lambda: not v._guardando_para_cerrar, timeout=4000)
    qtbot.waitUntil(lambda: bool(preguntas), timeout=4000)  # el cierre se intentó y se rechazó
    assert preguntas == ["Hay una máquina en creación"]
    assert v.isVisible()
    assert v._cierre_confirmado is False
    v._creando = False


def test_q7_cancelar_la_pregunta_deja_el_cierre_sin_confirmar(qtbot, conectado, modales):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    Pregunta(modales, "Cancelar")
    assert v.close() is False
    assert v._cierre_confirmado is False and not v._guardando_para_cerrar and v.isEnabled()


def test_q7_cerrar_sin_cambios_pendientes_sigue_cerrando_a_la_primera(qtbot, conectado, modales):
    v, _ = conectado
    pregunta = Pregunta(modales, "Cancelar")
    assert v.close() is True and pregunta.veces == 0
