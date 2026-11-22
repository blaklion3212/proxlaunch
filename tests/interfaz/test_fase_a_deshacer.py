"""Deshacer con confirmación expresa en la ventana (0.6.0): diálogo, cancelar, «sin forzar» e
informe por máquina (RF-A1.5, RF-A6.4).

Derivadas de docs/requisitos/fase-a.md: CA-A1.5.2, CA-A1.5.7, CA-A6.4.1, CA-A6.4.2, CA-A6.4.3 y,
de RF-A6.3, que las MVs que no son del lote nunca se tocan.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox

from proxlaunch.interfaz.dialogos.confirmar_deshacer import (
    DialogoConfirmarDeshacerForzado,
    EleccionDeshacer,
)
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.rollback import EstadoRollback, InspeccionRollback

from . import test_ventana_principal as _base
from .apoyo_fase_a import (
    ClienteDeshacerFalso,
    abrir_confirmacion_forzada,
    lote_creado,
)
from .apoyo_ventana_lote import esperar_fin

entorno = _base.entorno


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Cierra sin bloquear ni preguntar."""


@pytest.fixture
def cliente():
    return ClienteDeshacerFalso()


def esperar_deshecho(qtbot, v) -> None:
    qtbot.waitUntil(lambda: not v._lote.deshaciendo and not v._lote.inspeccionando, timeout=8000)
    esperar_fin(qtbot, v)


# --- El diálogo de confirmación expresa ---


@pytest.fixture
def dialogo(qtbot):
    d = DialogoConfirmarDeshacerForzado(
        InspeccionRollback((101, 102), (103,), nombres={101: "web-01", 102: "web-02", 103: "db"})
    )
    qtbot.addWidget(d)
    d.show()
    return d


def test_ca_a1_5_7_la_casilla_de_confirmacion_esta_desmarcada_por_defecto(dialogo):
    assert isinstance(dialogo.casilla, QCheckBox)
    assert not dialogo.casilla.isChecked()


def test_ca_a1_5_7_el_boton_que_fuerza_esta_deshabilitado_hasta_marcar_la_casilla(dialogo):
    assert not dialogo.boton_forzar.isEnabled()
    dialogo.casilla.setChecked(True)
    assert dialogo.boton_forzar.isEnabled()
    dialogo.casilla.setChecked(False)
    assert not dialogo.boton_forzar.isEnabled()


def test_ca_a1_5_7_cancelar_es_el_boton_predeterminado_y_tiene_el_foco(dialogo):
    assert dialogo.boton_cancelar.isDefault()
    assert not dialogo.boton_forzar.isDefault() and not dialogo.boton_sin_forzar.isDefault()
    assert dialogo.focusWidget() is dialogo.boton_cancelar


def test_ca_a1_5_7_el_texto_indica_cuantas_maquinas_se_apagaran_a_la_fuerza(dialogo):
    assert "web-01 (VMID 101)" in dialogo.aviso.text()
    assert "web-02 (VMID 102)" in dialogo.aviso.text()
    assert "apagar" in dialogo.aviso.text().lower()
    assert "datos que no estén guardados" in dialogo.aviso.text()


def test_ca_a6_4_2_el_dialogo_muestra_los_dos_recuentos(dialogo):
    texto = dialogo.aviso.text()
    assert "web-01 (VMID 101)" in texto and "web-02 (VMID 102)" in texto
    assert "db (VMID 103)" in texto and "protección" in texto


@pytest.mark.parametrize(
    ("encendidas", "protegidas", "esperado", "ausente"),
    [
        ((101,), (), "(VMID 101)", "protección contra borrado a"),
        ((), (101, 102, 103), "(VMID 103)", "apagarán"),
        ((101, 102, 103, 104), (), "(VMID 104)", "protección contra borrado a"),
    ],
)
def test_ca_a6_4_2_el_dialogo_solo_menciona_lo_que_hay(
    qtbot, encendidas, protegidas, esperado, ausente
):
    nombres = {v: f"m-{v}" for v in (*encendidas, *protegidas)}
    d = DialogoConfirmarDeshacerForzado(InspeccionRollback(encendidas, protegidas, nombres=nombres))
    qtbot.addWidget(d)
    assert esperado in d.aviso.text()
    assert ausente not in d.aviso.text()


def test_ca_a6_4_2_el_dialogo_avisa_que_no_se_puede_deshacer(dialogo):
    assert "no se puede deshacer" in dialogo.aviso.text()


def test_ca_a1_5_2_por_defecto_la_eleccion_es_cancelar(dialogo):
    assert dialogo.eleccion == EleccionDeshacer.CANCELAR


def test_ca_a1_5_2_el_boton_cancelar_rechaza_y_deja_la_eleccion_en_cancelar(dialogo):
    dialogo.boton_cancelar.click()
    assert dialogo.result() == dialogo.DialogCode.Rejected
    assert dialogo.eleccion == EleccionDeshacer.CANCELAR


def test_ca_a1_5_2_cerrar_con_escape_equivale_a_cancelar(qtbot, dialogo):
    qtbot.keyClick(dialogo, Qt.Key.Key_Escape)
    assert dialogo.result() == dialogo.DialogCode.Rejected
    assert dialogo.eleccion == EleccionDeshacer.CANCELAR


def test_ca_a1_5_2_intro_activa_cancelar_y_no_la_accion_destructiva(qtbot, dialogo):
    dialogo.casilla.setChecked(True)  # incluso con la casilla marcada, Intro es de «Cancelar»
    assert dialogo.boton_cancelar.isDefault()
    qtbot.keyClick(dialogo.boton_cancelar, Qt.Key.Key_Return)
    assert dialogo.eleccion == EleccionDeshacer.CANCELAR


def test_ca_a1_5_7_el_boton_forzar_con_la_casilla_marcada_elige_forzar(dialogo):
    dialogo.casilla.setChecked(True)
    dialogo.boton_forzar.click()
    assert dialogo.eleccion == EleccionDeshacer.FORZAR
    assert dialogo.result() == dialogo.DialogCode.Accepted


def test_ca_a1_5_7_el_boton_forzar_deshabilitado_no_hace_nada_aunque_se_pulse(dialogo):
    dialogo.boton_forzar.click()
    assert dialogo.eleccion == EleccionDeshacer.CANCELAR
    assert dialogo.result() != dialogo.DialogCode.Accepted


def test_ca_a6_4_2_la_opcion_sin_forzar_no_exige_casilla_y_elige_sin_forzar(dialogo):
    assert dialogo.boton_sin_forzar.isEnabled()
    dialogo.boton_sin_forzar.click()
    assert dialogo.eleccion == EleccionDeshacer.SIN_FORZAR
    assert dialogo.result() == dialogo.DialogCode.Accepted


def test_ca_a6_4_2_el_dialogo_explica_que_sin_forzar_se_omiten_y_quedan_en_proxmox(dialogo):
    assert "se omiten" in dialogo.nota_sin_forzar.text()
    assert "Proxmox" in dialogo.nota_sin_forzar.text()


def test_rnf_a8_los_botones_del_dialogo_tienen_texto_distinto_y_en_espanol(dialogo):
    textos = [
        b.text() for b in (dialogo.boton_forzar, dialogo.boton_sin_forzar, dialogo.boton_cancelar)
    ]
    assert len(set(textos)) == 3 and all(textos)
    assert dialogo.windowTitle()


# --- En la ventana: inspección, cancelar y las dos salidas ---


def test_ca_a6_4_1_sin_encendidas_ni_protegidas_no_hay_dialogo_extra_y_se_borra_todo(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente)
    v._deshacer()
    d = v.findChildren(DialogoDeshacer)[0]
    d.boton_eliminar.click()
    esperar_deshecho(qtbot, v)
    assert not v.findChildren(DialogoConfirmarDeshacerForzado)
    assert sorted(cliente.eliminados) == [101, 102, 103]
    assert cliente.detenidas == [] and cliente.desprotegidas == []  # flujo de 0.5.1


def test_ca_a6_4_2_con_encendidas_y_protegidas_el_dialogo_muestra_los_dos_recuentos(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101, 102), protegidas=(103,))
    d = abrir_confirmacion_forzada(qtbot, v)
    assert (d.inspeccion.encendidas, d.inspeccion.protegidas) == ((101, 102), (103,))
    assert "web-01 (VMID 101)" in d.aviso.text() and "web-03 (VMID 103)" in d.aviso.text()
    assert not d.casilla.isChecked() and not d.boton_forzar.isEnabled()
    assert d.boton_cancelar.isDefault()
    # Sigue abierto: hasta confirmar no se escribió nada.
    assert cliente.escrituras == []
    d.boton_cancelar.click()


def test_ca_a6_4_2_el_dialogo_cuenta_una_maquina_encendida_y_protegida_en_los_dos_recuentos(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,), protegidas=(101,))
    d = abrir_confirmacion_forzada(qtbot, v)
    assert (d.inspeccion.encendidas, d.inspeccion.protegidas) == ((101,), (101,))
    d.boton_cancelar.click()


def test_ca_a6_4_2_basta_con_una_protegida_apagada_para_pedir_confirmacion(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, protegidas=(102,))
    d = abrir_confirmacion_forzada(qtbot, v)
    assert (d.inspeccion.encendidas, d.inspeccion.protegidas) == ((), (102,))
    d.boton_cancelar.click()


def test_ca_a1_5_2_cancelar_la_confirmacion_no_emite_ninguna_escritura(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101, 102), protegidas=(103,))
    d = abrir_confirmacion_forzada(qtbot, v)
    d.boton_cancelar.click()
    qtbot.waitUntil(lambda: not v.findChildren(DialogoConfirmarDeshacerForzado), timeout=2000)
    assert cliente.escrituras == []
    assert cliente.eliminados == [] and cliente.detenidas == [] and cliente.desprotegidas == []
    assert not v._lote.deshaciendo and not v._lote.inspeccionando
    # El lote sigue pudiendo deshacerse más tarde.
    assert v.progreso_lote.boton_deshacer.isEnabled()


def test_ca_a1_5_2_cerrar_la_confirmacion_con_escape_tampoco_escribe(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,))
    d = abrir_confirmacion_forzada(qtbot, v)
    qtbot.keyClick(d, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not v.findChildren(DialogoConfirmarDeshacerForzado), timeout=2000)
    assert cliente.escrituras == []


def test_ca_a1_5_1_confirmar_apaga_las_encendidas_desprotege_las_protegidas_y_borra(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101, 102), protegidas=(103,))
    d = abrir_confirmacion_forzada(qtbot, v)
    d.casilla.setChecked(True)
    d.boton_forzar.click()
    esperar_deshecho(qtbot, v)
    assert sorted(cliente.detenidas) == [101, 102]
    assert cliente.desprotegidas == [103]
    assert sorted(cliente.eliminados) == [101, 102, 103]
    # Orden por MV: apagar antes de desproteger y antes de borrar (DT-A6).
    for vmid in (101, 102):
        orden = [e[0] for e in cliente.escrituras if e[1] == vmid]
        assert orden == ["stop", "delete"]
    assert [e[0] for e in cliente.escrituras if e[1] == 103] == ["config", "delete"]


def test_ca_a6_4_3_el_informe_de_deshacer_lista_por_maquina_las_acciones_realizadas(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,), protegidas=(101, 102))
    d = abrir_confirmacion_forzada(qtbot, v)
    d.casilla.setChecked(True)
    d.boton_forzar.click()
    esperar_deshecho(qtbot, v)
    por_vmid = {r.vmid: r for r in v._lote.resultados_rollback}
    assert por_vmid[101].acciones == ("apagada", "desprotegida", "borrada")
    assert por_vmid[102].acciones == ("desprotegida", "borrada")
    assert por_vmid[103].acciones == ("borrada",)
    # Y lo que ve el usuario en la tabla de Deshacer.
    modelo = v.progreso_lote.modelo_rollback
    detalles = {
        modelo.data(modelo.index(i, 2)): modelo.data(modelo.index(i, 4))
        for i in range(modelo.rowCount())
    }
    assert "apagada a la fuerza" in detalles["101"] and "desprotegida" in detalles["101"]
    assert "desprotegida" in detalles["102"] and "apagada" not in detalles["102"]


def test_ca_a6_4_3_el_informe_de_texto_incluye_las_acciones(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,))
    d = abrir_confirmacion_forzada(qtbot, v)
    d.casilla.setChecked(True)
    d.boton_forzar.click()
    esperar_deshecho(qtbot, v)
    informe = v._informe_actual()
    assert informe is not None
    por_vmid = {r.vmid: r for r in informe.rollback}
    assert "apagada" in por_vmid[101].acciones


def test_ca_a6_4_2_sin_forzar_omite_las_encendidas_y_protegidas_y_borra_el_resto(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,), protegidas=(102,))
    d = abrir_confirmacion_forzada(qtbot, v)
    d.boton_sin_forzar.click()
    esperar_deshecho(qtbot, v)
    assert cliente.detenidas == [] and cliente.desprotegidas == []  # nada se fuerza
    assert cliente.eliminados == [103]
    por_vmid = {r.vmid: r for r in v._lote.resultados_rollback}
    assert por_vmid[101].estado == EstadoRollback.OMITIDA
    assert por_vmid[102].estado == EstadoRollback.OMITIDA
    assert por_vmid[103].estado == EstadoRollback.ELIMINADA


def test_ca_a6_4_3_las_omitidas_sin_forzar_explican_el_motivo(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,), protegidas=(102,))
    d = abrir_confirmacion_forzada(qtbot, v)
    d.boton_sin_forzar.click()
    esperar_deshecho(qtbot, v)
    modelo = v.progreso_lote.modelo_rollback
    detalles = {
        modelo.data(modelo.index(i, 2)): modelo.data(modelo.index(i, 4))
        for i in range(modelo.rowCount())
    }
    assert "encendida" in detalles["101"].lower()
    assert "protegida" in detalles["102"].lower()
    assert detalles["101"] != detalles["102"]


def test_ca_a1_5_4_una_maquina_ajena_encendida_y_protegida_nunca_se_toca(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,), protegidas=(101,))
    # La 101 pierde la etiqueta del lote: ya no es «propia» (CA-A1.5.4, CA-A6.3.4).
    cliente.configs[101] = {"name": "web-01", "tags": "otra-persona", "protection": 1}
    v._deshacer()
    d = v.findChildren(DialogoDeshacer)[0]
    d.boton_eliminar.click()
    esperar_deshecho(qtbot, v)
    assert not v.findChildren(DialogoConfirmarDeshacerForzado)
    assert 101 not in cliente.detenidas + cliente.desprotegidas + cliente.eliminados


def test_ca_a6_4_1_la_inspeccion_solo_lee_y_corre_fuera_del_hilo_de_la_interfaz(
    qtbot, entorno, cliente
):
    import threading

    principal = threading.get_ident()
    hilos: list[int] = []
    original = cliente.estado_actual_vm

    def espia(nodo, vmid):
        hilos.append(threading.get_ident())
        return original(nodo, vmid)

    cliente.estado_actual_vm = espia  # type: ignore[method-assign]
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,))
    hilos.clear()
    d = abrir_confirmacion_forzada(qtbot, v)
    assert hilos, "la inspección debe leer el estado de las MVs"
    assert principal not in hilos  # RNF-A3: lecturas en un trabajador
    assert cliente.escrituras == []  # solo lectura
    d.boton_cancelar.click()


def test_ca_a1_5_2_si_no_se_puede_leer_el_estado_de_las_maquinas_nunca_se_fuerza_nada(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente, encendidas=(101,))

    def falla(*_a, **_k):
        raise RuntimeError("sin conexión")

    # Sin lectura del estado no se apaga a ciegas: la confirmación las lista como ilegibles y,
    # con «sin forzar», no se escribe nada salvo el borrado de las no encendidas.
    cliente.estado_actual_vm = falla  # type: ignore[method-assign]
    v._deshacer()
    d = v.findChildren(DialogoDeshacer)[0]
    d.boton_eliminar.click()
    qtbot.waitUntil(lambda: bool(v.findChildren(DialogoConfirmarDeshacerForzado)), timeout=4000)
    v.findChildren(DialogoConfirmarDeshacerForzado)[0].boton_sin_forzar.click()
    esperar_deshecho(qtbot, v)
    assert cliente.detenidas == [] and cliente.desprotegidas == []


def test_estados_de_las_mvs_del_lote_siguen_siendo_ok_antes_de_deshacer(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    assert [e.estado for e in v._lote.libro.instantanea()] == [EstadoMV.OK] * 3
