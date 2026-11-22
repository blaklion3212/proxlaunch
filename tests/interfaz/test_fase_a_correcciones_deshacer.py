"""Correcciones de revisión de Deshacer forzado en la interfaz (SEG-A-01, QA-A-01, 06 y 08).

La confirmación lista cada máquina por nombre y VMID, separa las omitidas por falta de
privilegio y las ilegibles, avisa de que sin desproteger queda apagada, no ofrece forzar si
no hay nada forzable y la ventana fuerza exactamente lo que el usuario vio.
"""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.dialogos.confirmar_deshacer import (
    DialogoConfirmarDeshacerForzado,
    EleccionDeshacer,
)
from proxlaunch.nucleo.lote.modelos import EstadoRollback
from proxlaunch.nucleo.lote.rollback import InspeccionRollback
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos

from . import test_ventana_principal as _base
from .apoyo_fase_a import (
    ClienteDeshacerFalso,
    abrir_confirmacion_forzada,
    inventario_con,
    lote_creado,
)
from .apoyo_ventana_lote import esperar_fin

entorno = _base.entorno

NOMBRES = {101: "web-01", 102: "web-02", 103: "web-03", 104: "web-04"}


@pytest.fixture
def cliente() -> ClienteDeshacerFalso:
    return ClienteDeshacerFalso()


def _esperar_deshecho(qtbot, v) -> None:
    qtbot.waitUntil(lambda: not v._lote.deshaciendo and not v._lote.inspeccionando, timeout=8000)
    esperar_fin(qtbot, v)


def _dialogo(qtbot, **kw) -> DialogoConfirmarDeshacerForzado:
    d = DialogoConfirmarDeshacerForzado(InspeccionRollback(nombres=NOMBRES, **kw))
    qtbot.addWidget(d)
    d.show()
    return d


# --- Diálogo ----------------------------------------------------------------------------------


def test_qa_a_08_el_dialogo_lista_nombre_y_vmid_de_cada_una(qtbot):
    d = _dialogo(qtbot, encendidas=(101, 102), protegidas=(102, 103))
    texto = d.aviso.text()
    for vmid in (101, 102, 103):
        assert f"{NOMBRES[vmid]} (VMID {vmid})" in texto
    assert "(VMID 104)" not in texto


def test_qa_a_08_avisa_que_sin_poder_desproteger_queda_apagada_sin_borrar(qtbot):
    d = _dialogo(qtbot, encendidas=(101,), protegidas=(101,))
    texto = d.aviso.text()
    assert "no se puede quitar la protección" in texto
    assert "apagada" in texto and "no se eliminará" in texto


def test_qa_a_08_sin_protegidas_no_hay_aviso_de_desproteccion(qtbot):
    d = _dialogo(qtbot, encendidas=(101,))
    assert "no se eliminará" not in d.aviso.text()


def test_qa_a_06_las_omitidas_por_privilegio_se_indican_por_separado(qtbot):
    d = _dialogo(
        qtbot,
        encendidas=(101,),
        encendidas_sin_privilegio=(102,),
        protegidas_sin_privilegio=(103,),
    )
    texto = d.aviso.text()
    assert "VM.PowerMgmt" in texto and "VM.Config.Options" in texto
    antes, _, despues = texto.partition("VM.PowerMgmt")
    assert "(VMID 101)" in antes and "(VMID 102)" in despues and "(VMID 103)" in despues


def test_qa_a_01_las_ilegibles_se_indican_por_separado(qtbot):
    d = _dialogo(qtbot, encendidas=(101,), ilegibles=(104,))
    texto = d.aviso.text()
    assert "No se pudo comprobar" in texto and "web-04 (VMID 104)" in texto


def test_qa_a_08_sin_ninguna_forzable_no_se_ofrece_forzar(qtbot):
    d = _dialogo(qtbot, encendidas_sin_privilegio=(101,), protegidas_sin_privilegio=(102,))
    assert not d.boton_forzar.isVisible() and not d.casilla.isVisible()
    assert d.boton_sin_forzar.isVisible() and d.boton_sin_forzar.isEnabled()
    assert d.boton_cancelar.isDefault()
    d.boton_sin_forzar.click()
    assert d.eleccion == EleccionDeshacer.SIN_FORZAR


def test_qa_a_08_con_forzables_se_mantiene_casilla_desmarcada_y_boton_deshabilitado(qtbot):
    d = _dialogo(qtbot, encendidas=(101,))
    assert d.boton_forzar.isVisible() and d.casilla.isVisible()
    assert not d.casilla.isChecked() and not d.boton_forzar.isEnabled()
    assert d.boton_cancelar.isDefault() and d.boton_sin_forzar.isVisible()


# --- Ventana ----------------------------------------------------------------------------------


def test_seg_a_01_la_ventana_fuerza_solo_lo_que_vio_el_usuario(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,))
    d = abrir_confirmacion_forzada(qtbot, v)
    assert d.inspeccion.encendidas == (101,)
    # Con el diálogo abierto se enciende la 102 y se protege la 103.
    cliente.marcar(102, encendida=True)
    cliente.marcar(103, protegida=True)
    d.casilla.setChecked(True)
    d.boton_forzar.click()
    _esperar_deshecho(qtbot, v)
    assert cliente.detenidas == [101]
    assert cliente.desprotegidas == []
    assert sorted(cliente.eliminados) == [101]
    por_vmid = {r.vmid: r for r in v._lote.resultados_rollback}
    assert por_vmid[102].estado == EstadoRollback.OMITIDA
    assert por_vmid[103].estado == EstadoRollback.OMITIDA


def test_qa_a_08_el_dialogo_de_la_ventana_trae_los_nombres(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,), protegidas=(102,))
    d = abrir_confirmacion_forzada(qtbot, v)
    assert "web-01 (VMID 101)" in d.aviso.text()
    assert "web-02 (VMID 102)" in d.aviso.text()
    d.boton_cancelar.click()


def test_qa_a_06_sin_privilegios_la_ventana_no_ofrece_forzar_y_omite(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,), protegidas=(102,))
    v._inv = inventario_con(v._inv, PermisosEfectivos({"/vms": {"VM.Allocate": 1}}))
    d = abrir_confirmacion_forzada(qtbot, v)
    assert d.inspeccion.encendidas_sin_privilegio == (101,)
    assert d.inspeccion.protegidas_sin_privilegio == (102,)
    assert not d.boton_forzar.isVisible()
    d.boton_sin_forzar.click()
    _esperar_deshecho(qtbot, v)
    assert cliente.detenidas == [] and cliente.desprotegidas == []
    assert cliente.eliminados == [103]


def test_qa_a_01_una_ilegible_aparece_en_el_dialogo_de_la_ventana(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    original = cliente.estado_actual_vm

    def falla_la_102(nodo, vmid):
        if vmid == 102:
            raise RuntimeError("sin conexión")
        return original(nodo, vmid)

    cliente.estado_actual_vm = falla_la_102  # type: ignore[method-assign]
    d = abrir_confirmacion_forzada(qtbot, v)
    assert d.inspeccion.ilegibles == (102,)
    assert "web-02 (VMID 102)" in d.aviso.text()
    assert not d.boton_forzar.isVisible()
    d.boton_cancelar.click()
