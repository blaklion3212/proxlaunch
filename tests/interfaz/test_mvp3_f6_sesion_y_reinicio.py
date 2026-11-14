"""Correcciones Q3 y Q4 del MVP 3 (fase 6): «Cerrar sesión» con un lote sin guardar y reinicio del
estado del lote (RF-G08, CA-G08.x, CA-G04.8).

Q3: «Cerrar sesión» pasa por la pregunta «¿Guardar el lote antes de continuar?» y un lote importado
o cargado sobrevive a la reconexión, con su huella intacta. Q4: al reiniciar el formulario el
lote vuelve al estado inicial; un lote guardado a mano cuenta como lote de archivo y un cambio de
servidor no lo reinicia.

El conftest de la carpeta sustituye la pregunta real por «No guardar»; aquí se restaura (fixture
``pregunta_real``) y se responde por el registro de diálogos modales.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QAction

from proxlaunch.nucleo.lote.modelos import Algoritmo, ModoDestino

from . import test_ventana_principal as _base
from .apoyo import perfil, sesion_falsa
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import (
    cierre_sin_preguntar_al_terminar,
    conectar3,
    definicion_homogenea,
    escribir,
    escribir_lote_guardado,
    importar_csv_por_menu,
    inventario_cluster_otros_nodos,
)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_mvp3_cambios_sin_guardar import Pregunta
from .test_mvp3_cambios_sin_guardar import pregunta_real as pregunta_real  # noqa: F401  (fixture)
from .test_mvp3_filas_csv import csv_de, fila
from .test_mvp3_lotes import abrir_lote, guardar_lote_por_menu
from .test_ventana_principal import conectar, esperar_validacion

entorno = _base.entorno  # fixture base de la ventana


@pytest.fixture
def conectado(request, qtbot, entorno3, pregunta_real):  # noqa: F811
    cliente = conectar3(qtbot, entorno3)
    cierre_sin_preguntar_al_terminar(request, entorno3.ventana)
    return entorno3.ventana, cliente


def cerrar_sesion(v) -> None:
    """«Archivo > Cerrar sesión» como lo haría el usuario."""
    accion = next(a for a in v.findChildren(QAction) if a.text() == "Cerrar sesión")
    accion.trigger()


def reconectar(qtbot, entorno3, v, cliente) -> None:
    conectar(qtbot, entorno3, sesion_falsa(cliente=cliente))
    esperar_validacion(qtbot, v)


def importar_cuatro(qtbot, entorno3, modales, archivos, tmp_path) -> Path:
    ruta = csv_de(
        tmp_path,
        fila("web-01", 4, "4 GiB"),
        fila("web-02", 4, "2 GiB", nodo="pve1"),
        fila("db-01", 8, "2 GiB", nodo="pve3"),
        fila("ejemplo-01", 2),
    )
    importar_csv_por_menu(qtbot, entorno3, modales, archivos, ruta)
    return ruta


# --- Q3: Cerrar sesión pasa por la pregunta de cambios sin guardar ------------------------------


def test_q3_cerrar_sesion_con_un_csv_importado_pregunta(
    qtbot, conectado, entorno3, modales, archivos, tmp_path
):
    v, _ = conectado
    importar_cuatro(qtbot, entorno3, modales, archivos, tmp_path)
    pregunta = Pregunta(modales, "Cancelar")
    cerrar_sesion(v)
    assert pregunta.veces == 1
    assert pregunta.texto == "¿Guardar el lote antes de continuar?"


def test_q3_cancelar_mantiene_la_sesion_y_el_lote(
    qtbot, conectado, entorno3, modales, archivos, tmp_path
):
    v, _ = conectado
    importar_cuatro(qtbot, entorno3, modales, archivos, tmp_path)
    huella = v._huella_guardada
    Pregunta(modales, "Cancelar")
    cerrar_sesion(v)
    assert v._sesion is not None and v._paginas.currentIndex() == 1
    assert v.bloque_lote.es_por_filas and v._huella_guardada == huella


def test_q3_no_guardar_cierra_la_sesion_sin_escribir_nada(
    qtbot, conectado, entorno3, modales, archivos, tmp_path
):
    v, _ = conectado
    importar_cuatro(qtbot, entorno3, modales, archivos, tmp_path)
    antes = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    pregunta = Pregunta(modales, "No guardar")
    cerrar_sesion(v)
    assert pregunta.veces == 1
    assert v._sesion is None and v._paginas.currentIndex() == 0
    assert v.statusBar().currentMessage() == "Sin conexión"
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == antes
    assert archivos.pedidos_guardar == []


def test_q3_al_reconectar_el_lote_importado_sigue_y_la_huella_queda_intacta(
    qtbot, conectado, entorno3, modales, archivos, tmp_path
):
    v, cliente = conectado
    importar_cuatro(qtbot, entorno3, modales, archivos, tmp_path)
    huella = v._huella_guardada
    nombres = [f.nombre for f in v._definicion_actual().filas]
    Pregunta(modales, "No guardar")
    cerrar_sesion(v)
    reconectar(qtbot, entorno3, v, cliente)
    assert v._sesion is not None and v._paginas.currentIndex() == 1
    assert v.bloque_lote.es_por_filas and v._origen_lote is not None
    assert [f.nombre for f in v._definicion_actual().filas] == nombres
    assert v._huella_guardada == huella and huella is not None


def test_q3_un_lote_cargado_de_archivo_y_editado_tambien_pregunta_y_sobrevive(
    qtbot, conectado, entorno3, modales, archivos, tmp_path
):
    v, cliente = conectado
    ruta = escribir_lote_guardado(tmp_path / "l.proxlaunch-lote.json", definicion_homogenea(3))
    abrir_lote(qtbot, v, archivos, ruta)
    escribir(v.formulario.cores, "4")  # un cambio que sí forma parte del lote
    esperar_validacion(qtbot, v)
    assert v._hay_cambios_sin_guardar()
    huella = v._huella_guardada
    pregunta = Pregunta(modales, "No guardar")
    cerrar_sesion(v)
    assert pregunta.veces == 1 and v._sesion is None
    reconectar(qtbot, entorno3, v, cliente)
    assert v._ruta_lote == ruta and v._huella_guardada == huella
    assert v.bloque_lote.cantidad.text() == "3"


def test_q3_sin_lote_ni_ediciones_cerrar_sesion_no_pregunta(qtbot, conectado, modales):
    v, _ = conectado
    pregunta = Pregunta(modales, "Cancelar")
    cerrar_sesion(v)
    assert pregunta.veces == 0 and v._sesion is None and v._paginas.currentIndex() == 0


def test_q3_sin_lote_de_archivo_reconectar_reinicia_el_formulario_como_antes(
    qtbot, conectado, entorno3, modales
):
    v, cliente = conectado
    escribir(v.bloque_lote.cantidad, "3")
    escribir(v.bloque_lote.prefijo, "web")
    esperar_validacion(qtbot, v)
    pregunta = Pregunta(modales, "No guardar")
    cerrar_sesion(v)  # una edición manual sí es un cambio sin guardar (CA-G08.1)
    assert pregunta.veces == 1 and v._sesion is None
    reconectar(qtbot, entorno3, v, cliente)
    assert v.bloque_lote.cantidad.text() == "1" and v.bloque_lote.prefijo.text() == ""
    assert v._origen_lote is None and not v._hay_cambios_sin_guardar()


# --- Q4: reinicio del estado del lote ----------------------------------------------------------


def test_q4_cambiar_de_servidor_con_un_lote_armado_a_mano_lo_reinicia_por_completo(
    qtbot, conectado, entorno3
):
    v, cliente = conectado
    b = v.bloque_lote
    escribir(b.cantidad, "3")
    escribir(b.prefijo, "web")
    b._radio_un_nodo.setChecked(True)
    esperar_validacion(qtbot, v)
    entorno3.inv = inventario_cluster_otros_nodos()
    conectar(qtbot, entorno3, sesion_falsa(perfil(id_="p2", nombre="Otro"), cliente=cliente))
    esperar_validacion(qtbot, v)
    assert b.cantidad.text() == "1" and b.prefijo.text() == ""
    assert b.destino().modo == ModoDestino.AUTOMATICO
    assert v._ruta_lote is None and v._origen_lote is None
    # La base de «cambios sin guardar» es la del formulario recién abierto, no la del lote viejo.
    assert not v._hay_cambios_sin_guardar()
    assert not b._destino_de_archivo and b._nodos_ausentes == []
    assert not b.es_por_filas


def test_q4_reiniciar_el_formulario_olvida_el_archivo_de_origen_y_el_lote_por_filas(
    qtbot, conectado, entorno3, modales, archivos, tmp_path
):
    v, _ = conectado
    importar_cuatro(qtbot, entorno3, modales, archivos, tmp_path)
    v._ruta_lote = tmp_path / "x.proxlaunch-lote.json"
    v._reiniciar_lote()
    assert v._ruta_lote is None and v._origen_lote is None and v._huella_guardada is None
    assert not v.bloque_lote.es_por_filas and v.bloque_lote.cantidad.text() == "1"
    assert not v._hay_cambios_sin_guardar()


def test_q4_reiniciar_el_bloque_limpia_ausentes_destino_de_archivo_y_valores(
    qtbot, conectado, archivos, tmp_path
):
    import dataclasses

    from proxlaunch.nucleo.lote.modelos import Destino

    v, _ = conectado
    base = definicion_homogenea(5, "db")
    definicion = dataclasses.replace(
        base,
        destino=Destino(ModoDestino.NODOS_ELEGIDOS, ("pve1", "pveX"), Algoritmo.POR_TURNOS),
        vmid_inicial=300,
        etiquetar=False,
    )
    b = v.bloque_lote
    b.establecer_definicion(definicion)
    assert b._destino_de_archivo and b._nodos_ausentes == ["pveX"]
    b.reiniciar()
    assert b._nodos_ausentes == [] and not b._destino_de_archivo
    assert b.cantidad.text() == "1" and b.prefijo.text() == ""
    assert b.vmid_inicial.text() == "" and b.chk_etiquetar.isChecked()
    destino = b.destino()
    assert destino.modo == ModoDestino.AUTOMATICO and destino.algoritmo == Algoritmo.EQUILIBRADO
    assert not any("pveX" in t for t in b._checks_nodos)  # el nodo ausente ya no se lista


def test_q4_reiniciar_el_bloque_sale_del_modo_por_filas(
    qtbot, conectado, entorno3, modales, archivos, tmp_path
):
    v, _ = conectado
    importar_cuatro(qtbot, entorno3, modales, archivos, tmp_path)
    assert v.bloque_lote.es_por_filas
    v.bloque_lote.reiniciar()
    assert not v.bloque_lote.es_por_filas and v.bloque_lote.cantidad_valor() == 1


def test_q4_un_lote_guardado_a_mano_cuenta_como_lote_de_archivo(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    escribir(v.bloque_lote.cantidad, "3")
    escribir(v.bloque_lote.prefijo, "web")
    esperar_validacion(qtbot, v)
    destino = tmp_path / "a-mano.proxlaunch-lote.json"
    guardar_lote_por_menu(qtbot, v, modales, archivos, destino)
    qtbot.waitUntil(lambda: v._ruta_lote == destino, timeout=4000)
    assert v._origen_lote is not None and v._origen_lote.tipo == "guardado"
    assert v._huella_guardada is not None and not v._hay_cambios_sin_guardar()


def test_q4_guardado_a_mano_y_cambio_de_servidor_no_reinicia_el_lote(
    qtbot, conectado, entorno3, modales, archivos, tmp_path
):
    v, cliente = conectado
    escribir(v.bloque_lote.cantidad, "3")
    escribir(v.bloque_lote.prefijo, "web")
    esperar_validacion(qtbot, v)
    destino = tmp_path / "a-mano.proxlaunch-lote.json"
    guardar_lote_por_menu(qtbot, v, modales, archivos, destino)
    qtbot.waitUntil(lambda: v._ruta_lote == destino, timeout=4000)
    huella = v._huella_guardada
    entorno3.inv = inventario_cluster_otros_nodos()
    conectar(qtbot, entorno3, sesion_falsa(perfil(id_="p2", nombre="Otro"), cliente=cliente))
    esperar_validacion(qtbot, v)
    assert v.bloque_lote.cantidad.text() == "3" and v.bloque_lote.prefijo.text() == "web"
    assert v._ruta_lote == destino and v._huella_guardada == huella
    assert v._origen_lote is not None and v._origen_lote.tipo == "guardado"
