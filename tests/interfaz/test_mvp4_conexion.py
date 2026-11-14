"""Diálogo de conexión: almacenamientos recordados por servidor (RF-O05, RF-O06; CA-O05.4, O05.8,
O05.9): se ven, se eligen en avanzado y se olvidan; el recordado ausente se marca."""

from __future__ import annotations

import dataclasses

import pytest

from proxlaunch.interfaz.dialogos.conexion import DialogoConexion
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.modelos.catalogo import Contenido

from .apoyo import perfil

CANDIDATOS = {
    Contenido.IMAGENES: ("local", "local-lvm"),
    Contenido.ISO: ("local", "nfs1"),
    Contenido.IMPORT: ("local",),
}


@pytest.fixture
def crear(qtbot, deps):
    lz = Lanzador()

    def _crear(avanzado=False, **kw):
        d = DialogoConexion(
            deps.servicio_conexion,
            deps.perfiles,
            deps.huellas,
            deps.secretos,
            lz,
            avanzado=avanzado,
            candidatos_storage=CANDIDATOS,
            **kw,
        )
        qtbot.addWidget(d)
        d.show()
        return d

    yield _crear
    lz.esperar(2000)


def _con_recordados(deps, **kw):
    deps.perfiles.guardar(dataclasses.replace(perfil("p1", "Lab"), **kw))


def test_ca_o05_4_el_dialogo_tiene_una_fila_por_contenido_con_su_boton_de_olvidar(crear, deps):
    _con_recordados(deps)
    d = crear(perfil_id="p1")
    assert set(d._filas_storage) == set(Contenido)
    for _valor, _combo, olvidar in d._filas_storage.values():
        assert olvidar.text() == "Dejar de recordar"
        assert not olvidar.isEnabled()  # no hay nada recordado


def test_ca_o05_4_en_basico_se_ve_el_nombre_recordado_o_detectar_automaticamente(crear, deps):
    _con_recordados(deps, storage_mv="local-lvm")
    d = crear(perfil_id="p1")
    valor_mv, combo_mv, _ = d._filas_storage[Contenido.IMAGENES]
    valor_iso, _, _ = d._filas_storage[Contenido.ISO]
    assert valor_mv.isVisible() and not combo_mv.isVisible()
    assert valor_mv.text() == "local-lvm"
    assert valor_iso.text() == "Detectar automáticamente"


def test_ca_o05_4_en_avanzado_son_listas_desplegables_con_los_candidatos(crear, deps):
    _con_recordados(deps, storage_iso="nfs1")
    d = crear(avanzado=True, perfil_id="p1")
    valor, combo, _ = d._filas_storage[Contenido.ISO]
    assert combo.isVisible() and not valor.isVisible()
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Detectar automáticamente",
        "local",
        "nfs1",
    ]
    assert combo.currentData() == "nfs1"


def test_dejar_de_recordar_vuelve_a_detectar_y_deshabilita_el_boton(crear, deps):
    _con_recordados(deps, storage_mv="local-lvm")
    d = crear(perfil_id="p1")
    valor, _combo, olvidar = d._filas_storage[Contenido.IMAGENES]
    assert olvidar.isEnabled()
    olvidar.click()
    assert valor.text() == "Detectar automáticamente"
    assert not olvidar.isEnabled()
    assert d._recordados[Contenido.IMAGENES] is None


def test_ca_o06_1_un_recordado_que_ya_no_existe_se_marca_como_no_disponible(crear, deps):
    _con_recordados(deps, storage_mv="fantasma")
    d = crear(perfil_id="p1")
    valor, _c, _o = d._filas_storage[Contenido.IMAGENES]
    assert valor.text() == "fantasma (no disponible)"


def test_elegir_en_la_lista_cambia_el_recordado_del_perfil_en_edicion(crear, deps):
    _con_recordados(deps)
    d = crear(avanzado=True, perfil_id="p1")
    _v, combo, olvidar = d._filas_storage[Contenido.IMAGENES]
    combo.setCurrentIndex(combo.findData("local"))
    assert d._recordados[Contenido.IMAGENES] == "local"
    assert olvidar.isEnabled()


def test_ca_o05_9_el_perfil_leido_lleva_los_tres_recordados_y_solo_nombres(crear, deps):
    _con_recordados(deps, storage_mv="local", storage_iso="nfs1", storage_import="local")
    d = crear(perfil_id="p1")
    d.nombre.setText("Lab")
    d.hosts.setPlainText("10.0.0.5")
    leido = d._leer_perfil(credenciales=False)
    assert leido is not None
    assert (leido.storage_mv, leido.storage_iso, leido.storage_import) == ("local", "nfs1", "local")
    d._olvidar_storage(Contenido.ISO)
    assert d._leer_perfil(credenciales=False).storage_iso is None


def test_ca_o05_7_un_perfil_nuevo_no_hereda_los_recordados_del_anterior(crear, deps):
    _con_recordados(deps, storage_mv="local")
    d = crear(perfil_id="p1")
    d._cargar_perfil(None)
    assert d._recordados == dict.fromkeys(Contenido)
    assert d._filas_storage[Contenido.IMAGENES][0].text() == "Detectar automáticamente"
