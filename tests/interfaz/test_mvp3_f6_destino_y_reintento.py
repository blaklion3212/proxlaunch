"""Correcciones Q1 y Q2 del MVP 3 (fase 6), probadas por la interfaz pública.

Q1 (CA-G03.5): un lote cargado con «Nodos elegidos» se respeta también en modo básico: el destino,
el reparto y el guardado conservan los nodos, se avisa con una nota y los checks quedan en solo
lectura. Q2: el plan de un reintento no es el lote del formulario, así que no ofrece «Asignar
automáticamente» ni «Quitar las filas que no caben» y las acciones directas no hacen nada.

Ningún diálogo modal real; los archivos viven en ``tmp_path``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox, QPushButton

from proxlaunch.interfaz.vistas.resumen_lote import ResumenLote
from proxlaunch.nucleo.lote.modelos import Destino, ModoDestino
from proxlaunch.nucleo.lotes_guardados.formato import leer_archivo_lote
from proxlaunch.nucleo.lotes_guardados.revalidacion import TipoDesajuste
from proxlaunch.nucleo.persistencia.preferencias import Modo

from . import test_ventana_principal as _base
from .apoyo import ClienteLoteFalso, CreacionPorVmid, inventario_cluster
from .apoyo_lote import planificar
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import (
    conectar3,
    definicion_filas,
    definicion_homogenea,
    escribir_lote_guardado,
    importar_csv_por_menu,
    todos_los_textos,
)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .apoyo_ventana_lote import crear_lote, esperar_fin, ver_resumen
from .test_mvp3_filas_csv import csv_de, fila, ver_resumen_filas
from .test_mvp3_lotes import abrir_lote, guardar_lote_por_menu

entorno = _base.entorno  # fixture base de la ventana

NOTA_ELEGIDOS = "Este lote usa nodos elegidos; cámbialo en modo avanzado."


# --- Q1: nodos elegidos respetados en modo básico ----------------------------------------------


def lote_con_nodos(ruta: Path, nodos: tuple[str, ...], cantidad: int = 6) -> Path:
    """Lote guardado homogéneo con destino «Nodos elegidos»."""
    base = definicion_homogenea(cantidad)
    definicion = dataclasses.replace(base, destino=Destino(ModoDestino.NODOS_ELEGIDOS, nodos))
    return escribir_lote_guardado(ruta, definicion)


@pytest.fixture
def conectado(qtbot, entorno3):
    cliente = conectar3(qtbot, entorno3)
    return entorno3.ventana, cliente


@pytest.fixture
def lote_elegidos(tmp_path) -> Path:
    return lote_con_nodos(tmp_path / "elegidos.proxlaunch-lote.json", ("pve1", "pve3"))


def test_ca_g03_5_cargar_en_basico_respeta_los_nodos_elegidos_en_el_destino(
    qtbot, conectado, archivos, lote_elegidos
):
    v, _ = conectado
    assert not v.avanzado  # el entorno arranca en modo básico
    abrir_lote(qtbot, v, archivos, lote_elegidos)
    destino = v.bloque_lote.destino()
    assert destino.modo == ModoDestino.NODOS_ELEGIDOS
    assert sorted(destino.nodos) == ["pve1", "pve3"]
    assert v._definicion_actual().destino.modo == ModoDestino.NODOS_ELEGIDOS


def test_ca_g03_5_el_reparto_en_basico_no_usa_los_nodos_excluidos(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    # Solo pve3: pve1 está en línea y quedaría elegible si el destino se tratara como automático.
    ruta = lote_con_nodos(tmp_path / "solo-pve3.proxlaunch-lote.json", ("pve3",))
    abrir_lote(qtbot, v, archivos, ruta)
    ver_resumen(qtbot, v)
    nodos_del_plan = {e.nodo for e in v.resumen_lote.plan.elementos}
    assert nodos_del_plan == {"pve3"}


def test_ca_g03_5_sobrescribir_en_basico_conserva_los_nodos_elegidos(
    qtbot, conectado, modales, archivos, lote_elegidos
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_elegidos)
    modales.pulsar(QMessageBox, "Sobrescribir")
    guardar_lote_por_menu(qtbot, v, modales, archivos, None, sobrescribir=True)
    qtbot.waitUntil(
        lambda: v.statusBar().currentMessage().startswith("Lote guardado"), timeout=4000
    )
    destino = leer_archivo_lote(lote_elegidos).lote.definicion.destino
    assert destino.modo == ModoDestino.NODOS_ELEGIDOS
    assert sorted(destino.nodos) == ["pve1", "pve3"]


def test_ca_g03_5_la_nota_se_ve_en_basico_y_se_oculta_en_avanzado(
    qtbot, conectado, archivos, lote_elegidos
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_elegidos)
    assert NOTA_ELEGIDOS in todos_los_textos(v.bloque_lote)  # solo cuenta lo visible
    v.establecer_modo(Modo.AVANZADO)
    assert NOTA_ELEGIDOS not in todos_los_textos(v.bloque_lote)
    v.establecer_modo(Modo.BASICO)
    assert NOTA_ELEGIDOS in todos_los_textos(v.bloque_lote)


def test_ca_g03_5_la_nota_no_aparece_con_otro_destino(qtbot, conectado, archivos, tmp_path):
    v, _ = conectado
    ruta = escribir_lote_guardado(tmp_path / "uno.proxlaunch-lote.json", definicion_homogenea(3))
    abrir_lote(qtbot, v, archivos, ruta)
    assert NOTA_ELEGIDOS not in todos_los_textos(v.bloque_lote)


def test_ca_g03_5_los_checks_de_nodos_son_de_solo_lectura_en_basico_y_editables_en_avanzado(
    qtbot, conectado, archivos, lote_elegidos
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_elegidos)
    checks = list(v.bloque_lote._checks_nodos.values())
    en_linea = [c for c in checks if c.text() in ("pve1", "pve3")]
    assert len(checks) == 3 and len(en_linea) == 2  # pve2 está caído: nunca editable
    assert all(c.isVisibleTo(v) and not c.isEnabled() for c in checks)
    # Sin pérdida de datos al cambiar de modo (CA-G03.5): marcados igual y ahora editables.
    marcados = {c.text() for c in checks if c.isChecked()}
    v.establecer_modo(Modo.AVANZADO)
    assert all(c.isEnabled() for c in en_linea)
    assert {c.text() for c in checks if c.isChecked()} == marcados == {"pve1", "pve3"}


def test_ca_g03_5_un_check_deshabilitado_no_cambia_el_destino_en_basico(
    qtbot, conectado, archivos, lote_elegidos
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_elegidos)
    checks = list(v.bloque_lote._checks_nodos.values())
    pve1 = next(c for c in checks if c.text() == "pve1")
    assert pve1.isChecked()
    pve1.click()  # un botón deshabilitado ignora el clic
    assert pve1.isChecked()
    assert sorted(v.bloque_lote.destino().nodos) == ["pve1", "pve3"]


def test_ca_g04_1_un_nodo_elegido_inexistente_se_informa_como_desajuste_en_basico(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    ruta = lote_con_nodos(tmp_path / "ausente.proxlaunch-lote.json", ("pve1", "pveX"))
    abrir_lote(qtbot, v, archivos, ruta)
    nodos = [d for d in v.panel_no_encaja.desajustes() if d.tipo == TipoDesajuste.NODO]
    assert [d.valor for d in nodos] == ["pveX"]
    # Se muestra (marcado y deshabilitado), no se sustituye en silencio.
    texto = " ".join(c.text() for c in list(v.bloque_lote._checks_nodos.values()))
    assert "pveX (no existe)" in texto
    assert "pveX" in v.bloque_lote.destino().nodos


# --- Q2: el reintento no ofrece reasignar ni quitar filas --------------------------------------


def _inv_y_plan_con_excedentes():
    """Plan por filas bloqueado: tres filas no caben en ``local`` y una usa un VMID ocupado."""
    inv = inventario_cluster()
    cliente = ClienteLoteFalso()
    cliente.vmids_ocupados.add(250)
    filas = [
        {"nombre": "a", "gib": 30, "nodo": "pve1", "storage": "local"},
        {"nombre": "b", "gib": 30, "nodo": "pve1", "storage": "local", "vmid": 250},
        {"nombre": "c", "gib": 30, "nodo": "pve1", "storage": "local"},
        {"nombre": "d", "gib": 30, "nodo": "pve1", "storage": "local"},
    ]
    plan = planificar(inv, definicion_filas(filas), cliente)
    assert plan.filas_excedentes and plan.bloqueado  # precondición del escenario
    return plan


def _botones(resumen: ResumenLote, texto: str) -> list[QPushButton]:
    return [
        b
        for b in resumen.findChildren(QPushButton)
        if b.text().startswith(texto) and b.isVisibleTo(resumen)
    ]


def test_q2_sin_reintento_el_resumen_ofrece_asignar_y_quitar(qapp):
    r = ResumenLote()
    r.show()
    r.establecer_reintento(False)
    r.mostrar_plan(_inv_y_plan_con_excedentes())
    assert r.boton_quitar_excedentes.isVisibleTo(r)
    assert _botones(r, "Asignar automáticamente")


def test_q2_con_reintento_los_botones_de_reasignar_y_quitar_se_ocultan(qapp):
    r = ResumenLote()
    r.show()
    r.establecer_reintento(True)
    r.mostrar_plan(_inv_y_plan_con_excedentes())
    assert not r.boton_quitar_excedentes.isVisibleTo(r)
    assert _botones(r, "Asignar automáticamente") == []


def test_q2_al_quitar_el_reintento_los_botones_vuelven(qapp):
    r = ResumenLote()
    r.show()
    plan = _inv_y_plan_con_excedentes()
    r.establecer_reintento(True)
    r.mostrar_plan(plan)
    r.establecer_reintento(False)
    r.mostrar_plan(plan)
    assert r.boton_quitar_excedentes.isVisibleTo(r)
    assert _botones(r, "Asignar automáticamente")


@pytest.fixture
def reintento_por_filas(qtbot, entorno3, modales, archivos, tmp_path, descubrimiento_falso):
    """CSV de cuatro filas cuya fila con VMID 250 falla; luego se reintenta con el 250 ocupado."""
    from .test_lote_ventana_acciones import fallo, reintentar

    entorno3.creacion = CreacionPorVmid({250: fallo(250)})
    cliente = conectar3(qtbot, entorno3)
    v = entorno3.ventana
    ruta = csv_de(
        tmp_path,
        fila("web-01", 4, "4 GiB"),
        fila("web-02", 4, "2 GiB", vmid=250, nodo="pve1"),
        fila("db-01", 8, "2 GiB", nodo="pve3"),
        fila("ejemplo-01", 2),
    )
    importar_csv_por_menu(qtbot, entorno3, modales, archivos, ruta)
    ver_resumen_filas(qtbot, v)
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    cliente.vmids_ocupados.add(250)  # otra persona lo tomó entre tanto
    reintentar(qtbot, v)
    return v, cliente


def test_q2_en_el_reintento_por_filas_no_se_ofrece_asignar_automaticamente(reintento_por_filas):
    v, _ = reintento_por_filas
    assert v._reintento is not None and v.resumen_lote.plan.bloqueado
    assert "250" in todos_los_textos(v.resumen_lote)  # el aviso de VMID ocupado sigue
    assert _botones(v.resumen_lote, "Asignar automáticamente") == []


def test_q2_las_llamadas_directas_durante_el_reintento_no_cambian_bloque_ni_huella(
    reintento_por_filas,
):
    v, _ = reintento_por_filas
    antes = (v._definicion_actual(), v._huella_guardada, v.bloque_lote.es_por_filas)
    plan_antes = v.resumen_lote.plan
    v._asignar_automaticamente((0,))
    v._quitar_filas_que_no_caben((0, 1))
    assert (v._definicion_actual(), v._huella_guardada, v.bloque_lote.es_por_filas) == antes
    assert v.resumen_lote.plan is plan_antes and not v._planificando


def test_q2_un_lote_por_filas_normal_sigue_asignando_y_quitando(
    qtbot, conectado, modales, archivos, entorno3, tmp_path
):
    v, cliente = conectado
    cliente.vmids_ocupados.add(250)
    ruta = csv_de(
        tmp_path,
        fila("web-01", 4, "4 GiB"),
        fila("web-02", 4, "2 GiB", vmid=250, nodo="pve1"),
        fila("db-01", 8, "2 GiB", nodo="pve3"),
        fila("ejemplo-01", 2),
    )
    importar_csv_por_menu(qtbot, entorno3, modales, archivos, ruta)
    ver_resumen_filas(qtbot, v)
    assert v._reintento is None
    botones = _botones(v.resumen_lote, "Asignar automáticamente")
    assert botones
    botones[0].click()
    qtbot.waitUntil(lambda: v.resumen_lote.plan is not None and not v._planificando, timeout=5000)
    assert v._definicion_actual().filas[1].vmid is None
    assert v.resumen_lote.puede_crear
