"""RF-G08 (cambios sin guardar) en la interfaz: cerrar, abrir otro lote, importar un CSV y cambiar
de servidor preguntan «¿Guardar el lote antes de continuar?» con el foco en «Cancelar».

El conftest de la carpeta sustituye la pregunta por «No guardar» para no bloquear otras pruebas;
aquí se restaura la real a propósito y se responde por el registro de diálogos modales.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.guardar_lote import DialogoGuardarLote
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv

from . import test_ventana_principal as _base
from .apoyo import CreacionPorVmid
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import (
    cierre_sin_preguntar_al_terminar,
    conectar3,
    csv_valido,
    definicion_homogenea,
    escribir,
    escribir_lote_guardado,
    importar_csv_por_menu,
    pulsar_boton,
)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_ventana_principal import esperar_validacion

entorno = _base.entorno  # fixture base de la ventana

# La pregunta real, capturada al importar (antes de que el conftest la sustituya en cada prueba).
_PREGUNTA_REAL = vp.VentanaPrincipal._preguntar_guardar_cambios
TEXTO_PREGUNTA = "¿Guardar el lote antes de continuar?"


@pytest.fixture
def pregunta_real(monkeypatch, _sin_pregunta_de_cambios_sin_guardar):
    """Devuelve la pregunta real a la ventana; al terminar vuelve a «No guardar» para que el
    cierre del entorno no pregunte."""
    monkeypatch.setattr(vp.VentanaPrincipal, "_preguntar_guardar_cambios", _PREGUNTA_REAL)
    yield
    monkeypatch.setattr(vp.VentanaPrincipal, "_preguntar_guardar_cambios", lambda self: "descartar")


@pytest.fixture
def conectado(request, qtbot, entorno3, pregunta_real):
    cliente = conectar3(qtbot, entorno3)
    cierre_sin_preguntar_al_terminar(request, entorno3.ventana)
    return entorno3.ventana, cliente


class Pregunta:
    """Responde a la pregunta de cambios sin guardar y recuerda cómo se presentó."""

    def __init__(self, modales, boton: str | None) -> None:
        self.veces = 0
        self.texto = ""
        self.informativo = ""
        self.botones: list[str] = []
        self.defecto = ""
        self.escape = ""
        self.boton = boton
        modales.responder(QMessageBox, self._ante)

    def _ante(self, caja: QMessageBox) -> None:
        self.veces += 1
        self.texto = caja.text()
        self.informativo = caja.informativeText()
        self.botones = [b.text() for b in caja.buttons()]
        self.defecto = caja.defaultButton().text()
        self.escape = caja.escapeButton().text()
        if self.boton is not None:
            pulsar_boton(caja, self.boton)


def editar_a_mano(qtbot, v) -> None:
    """Edición manual del hardware que sí forma parte del lote guardado (núcleos)."""
    escribir(v.formulario.cores, "4")
    esperar_validacion(qtbot, v)


# --- CA-G08.2: sin ediciones no se pregunta ----------------------------------------------------


def test_ca_g08_2_un_formulario_que_nunca_se_edito_se_cierra_sin_preguntar(
    qtbot, conectado, modales
):
    v, _ = conectado
    pregunta = Pregunta(modales, "Cancelar")
    assert not v._hay_cambios_sin_guardar()
    assert v.close() is True
    assert pregunta.veces == 0


# --- CA-G08.1: cerrar con una edición manual ---------------------------------------------------


def test_ca_g08_1_una_edicion_manual_sin_guardar_pregunta_al_cerrar_con_foco_en_cancelar(
    qtbot, conectado, modales
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    pregunta = Pregunta(modales, "Cancelar")
    v.close()
    assert pregunta.veces == 1
    assert pregunta.texto == TEXTO_PREGUNTA
    assert sorted(pregunta.botones) == ["Cancelar", "Guardar", "No guardar"]
    assert pregunta.defecto == "Cancelar" and pregunta.escape == "Cancelar"
    assert pregunta.informativo  # explica la consecuencia


def test_ca_g08_1_cancelar_no_cierra_la_ventana(qtbot, conectado, modales):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    Pregunta(modales, "Cancelar")
    assert v.close() is False
    assert v.isVisible()


def test_ca_g08_1_cerrar_el_dialogo_con_escape_equivale_a_cancelar(qtbot, conectado, modales):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    modales.responder(QMessageBox, lambda caja: caja.escapeButton().click())
    assert v.close() is False and v.isVisible()


def test_ca_g08_1_no_guardar_cierra_sin_escribir_nada(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    Pregunta(modales, "No guardar")
    assert v.close() is True
    assert archivos.pedidos_guardar == [] and list(tmp_path.glob("*.json")) == []


def test_ca_g08_1_guardar_guarda_el_lote_y_despues_cierra(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    Pregunta(modales, "Guardar")
    destino = tmp_path / "salida.proxlaunch-lote.json"
    archivos.guardar.append(destino)

    def _nombre(d: DialogoGuardarLote) -> None:
        d.campo_nombre.setText("antes de cerrar")
        d.boton_aceptar.click()

    modales.responder(DialogoGuardarLote, _nombre)
    v.close()
    qtbot.waitUntil(lambda: not v.isVisible(), timeout=4000)
    assert json.loads(destino.read_text(encoding="utf-8"))["nombre"] == "antes de cerrar"


def test_ca_g08_1_guardar_con_la_ruta_cancelada_no_cierra_ni_escribe(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    Pregunta(modales, "Guardar")
    archivos.guardar.append(None)
    modales.responder(
        DialogoGuardarLote, lambda d: (d.campo_nombre.setText("x"), d.boton_aceptar.click())
    )
    assert v.close() is False
    qtbot.wait(100)
    assert v.isVisible() and list(tmp_path.glob("*.json")) == []


def test_ca_g08_1_tras_guardar_ya_no_hay_nada_pendiente_y_cierra_sin_preguntar(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    destino = tmp_path / "s.proxlaunch-lote.json"
    archivos.guardar.append(destino)
    modales.responder(
        DialogoGuardarLote, lambda d: (d.campo_nombre.setText("x"), d.boton_aceptar.click())
    )
    v._accion_guardar_lote.trigger()
    qtbot.waitUntil(destino.exists, timeout=3000)
    qtbot.waitUntil(lambda: not v._hay_cambios_sin_guardar(), timeout=3000)
    pregunta = Pregunta(modales, "Cancelar")
    assert v.close() is True and pregunta.veces == 0


def test_ca_g08_1_un_cambio_posterior_al_guardado_vuelve_a_preguntar(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    destino = tmp_path / "s.proxlaunch-lote.json"
    archivos.guardar.append(destino)
    modales.responder(
        DialogoGuardarLote, lambda d: (d.campo_nombre.setText("x"), d.boton_aceptar.click())
    )
    v._accion_guardar_lote.trigger()
    qtbot.waitUntil(lambda: not v._hay_cambios_sin_guardar(), timeout=3000)
    escribir(v.bloque_lote.cantidad, "7")
    esperar_validacion(qtbot, v)
    pregunta = Pregunta(modales, "Cancelar")
    assert v.close() is False and pregunta.veces == 1


# --- Lote cargado y CSV importado --------------------------------------------------------------


def test_un_lote_recien_abierto_y_sin_tocar_se_cierra_sin_preguntar(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    ruta = escribir_lote_guardado(tmp_path / "a.proxlaunch-lote.json", definicion_homogenea())
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == ruta, timeout=3000)
    pregunta = Pregunta(modales, "Cancelar")
    assert v.close() is True and pregunta.veces == 0


def test_un_lote_cargado_y_editado_pregunta_al_cerrar(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    ruta = escribir_lote_guardado(tmp_path / "a.proxlaunch-lote.json", definicion_homogenea())
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == ruta, timeout=3000)
    escribir(v.bloque_lote.cantidad, "9")
    esperar_validacion(qtbot, v)
    pregunta = Pregunta(modales, "Cancelar")
    assert v.close() is False and pregunta.veces == 1


def test_ca_g08_1_un_csv_importado_sin_guardar_pregunta_al_cerrar(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    importar_csv_por_menu(
        qtbot, _EntornoDe(v), modales, archivos, csv_valido(tmp_path / "ejemplo.csv", 3)
    )
    pregunta = Pregunta(modales, "Cancelar")
    assert v.close() is False
    assert pregunta.veces == 1 and pregunta.texto == TEXTO_PREGUNTA
    assert pregunta.defecto == "Cancelar"


class _EntornoDe:
    """Adaptador mínimo: ``importar_csv_por_menu`` solo necesita ``.ventana``."""

    def __init__(self, ventana) -> None:
        self.ventana = ventana


def test_ca_g08_1_guardar_un_csv_importado_escribe_un_lote_por_filas_sin_la_ruta_del_csv(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    csv = csv_valido(tmp_path / "ejemplo.csv", 3)
    importar_csv_por_menu(qtbot, _EntornoDe(v), modales, archivos, csv)
    destino = tmp_path / "desde-csv.proxlaunch-lote.json"
    Pregunta(modales, "Guardar")
    archivos.guardar.append(destino)
    modales.responder(
        DialogoGuardarLote, lambda d: (d.campo_nombre.setText("desde csv"), d.boton_aceptar.click())
    )
    v.close()
    qtbot.waitUntil(lambda: not v.isVisible(), timeout=4000)
    contenido = destino.read_text(encoding="utf-8")
    datos = json.loads(contenido)
    assert datos["tipo"] == "por_filas" and len(datos["por_filas"]["filas"]) == 3
    assert [f["origen"] for f in datos["por_filas"]["filas"]] == [2, 3, 4]  # numeración de Excel
    assert str(tmp_path) not in contenido and "ejemplo.csv" not in contenido  # CA-G07.1


# --- Abrir otro lote, importar otro CSV y cambiar de servidor ----------------------------------


@pytest.fixture
def segundo_lote(tmp_path) -> Path:
    return escribir_lote_guardado(
        tmp_path / "otro.proxlaunch-lote.json", definicion_homogenea(2, "otro"), nombre="otro"
    )


def test_ca_g08_1_abrir_otro_lote_con_cambios_pregunta_y_cancelar_no_pide_archivo(
    qtbot, conectado, modales, archivos, segundo_lote
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    pregunta = Pregunta(modales, "Cancelar")
    archivos.abrir.append(segundo_lote)
    v._accion_abrir_lote.trigger()
    assert pregunta.veces == 1 and pregunta.defecto == "Cancelar"
    assert archivos.pedidos_abrir == []  # ni siquiera se llegó al selector de archivos
    assert v.formulario.cores.text() == "4"  # lo editado sigue ahí


def test_ca_g08_1_abrir_otro_lote_con_no_guardar_descarta_y_abre(
    qtbot, conectado, modales, archivos, segundo_lote
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    Pregunta(modales, "No guardar")
    archivos.abrir.append(segundo_lote)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == segundo_lote, timeout=3000)
    assert v.bloque_lote.patron().prefijo == "otro"


def test_ca_g08_1_abrir_otro_lote_con_guardar_guarda_primero_y_luego_abre(
    qtbot, conectado, modales, archivos, segundo_lote, tmp_path
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    Pregunta(modales, "Guardar")
    guardado = tmp_path / "primero.proxlaunch-lote.json"
    archivos.guardar.append(guardado)
    archivos.abrir.append(segundo_lote)
    modales.responder(
        DialogoGuardarLote, lambda d: (d.campo_nombre.setText("primero"), d.boton_aceptar.click())
    )
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == segundo_lote, timeout=4000)
    assert guardado.exists()


def test_ca_g08_1_importar_un_csv_con_cambios_pregunta_antes_de_abrir_el_asistente(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    pregunta = Pregunta(modales, "Cancelar")
    archivos.abrir.append(csv_valido(tmp_path / "e.csv"))
    v._accion_importar_csv.trigger()
    assert pregunta.veces == 1
    assert modales.de_clase(DialogoImportarCsv) == [] and archivos.pedidos_abrir == []
    assert not v.bloque_lote.es_por_filas


def test_ca_g08_1_cambiar_de_servidor_con_cambios_pregunta_y_cancelar_no_abre_la_conexion(
    qtbot, conectado, modales
):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    pregunta = Pregunta(modales, "Cancelar")
    v.abrir_conexion()
    assert pregunta.veces == 1 and v._dialogo_conexion is None


def test_ca_g08_1_cambiar_de_servidor_con_no_guardar_abre_la_conexion(qtbot, conectado, modales):
    v, _ = conectado
    editar_a_mano(qtbot, v)
    Pregunta(modales, "No guardar")
    v.abrir_conexion()
    assert v._dialogo_conexion is not None
    v._dialogo_conexion.reject()
    qtbot.waitUntil(lambda: v._dialogo_conexion is None, timeout=2000)


# --- CA-G08.3: con un lote en ejecución prevalece la confirmación de M2 ------------------------


def test_ca_g08_3_con_un_lote_en_ejecucion_solo_se_pregunta_lo_de_rf_l23(
    qtbot, entorno3, modales, archivos, pregunta_real, limpieza, confirmaciones
):
    import threading

    from .apoyo_ventana_lote import crear_lote, preparar_lote, ver_resumen

    preparar_lote(
        qtbot,
        entorno3,
        cantidad=3,
        creacion=CreacionPorVmid(puertas={101: threading.Event()}),
    )
    v = entorno3.ventana
    assert v._hay_cambios_sin_guardar()  # el lote del formulario nunca se guardó
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: v._lote_en_curso, timeout=4000)
    confirmaciones.respuesta = False  # «Seguir en ProxLaunch»
    v.close()
    assert len(confirmaciones.llamadas) == 1
    assert confirmaciones.llamadas[0][0] == "Hay un lote en curso"
    assert not [c for c in modales.vistos if isinstance(c, QMessageBox)]  # ni «Cambios sin guardar»
    assert v.isVisible()
