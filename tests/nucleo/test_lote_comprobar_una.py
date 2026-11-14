"""«Comprobar ahora» de una sola máquina dudosa (CA-L15.6, CA-L15.7): el motor acepta un
subconjunto de VMIDs, solo hace lecturas y no toca a las demás dudosas."""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote

from .apoyo_lote import NORMAL, definicion, envio_incierto, nodo_caido


@pytest.fixture
def banco():
    from .apoyo_lote import crear_banco

    return crear_banco(("pve1",))


@pytest.fixture
def lote_con_dos_dudosas(banco):
    """3 MVs: la 100 y la 102 con envío incierto y sin poder comprobar; la 101 normal."""

    def _post(llamada):
        if int(llamada.datos["vmid"]) in (100, 102):
            raise envio_incierto()
        return NORMAL

    banco.cluster.regla("POST", r"/qemu$", _post)
    bloqueo = banco.cluster.regla("GET", r"qemu/10[02]/config$", nodo_caido("pve1", 596))
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    libro = banco.ejecutar(plan)
    assert libro.entrada(100).estado == EstadoMV.CONEXION_PERDIDA
    assert libro.entrada(102).estado == EstadoMV.CONEXION_PERDIDA
    banco.cluster.reglas.remove(bloqueo)  # la red vuelve
    banco.cluster.reiniciar_llamadas()
    return libro


def _vmids_leidos(banco) -> set[int]:
    return {
        int(c.ruta.split("/qemu/")[1].split("/")[0])
        for c in banco.cluster.llamadas_a("GET", r"qemu/\d+/config$")
    }


def test_ca_l15_6_solo_se_comprueba_la_maquina_elegida(banco, lote_con_dos_dudosas):
    libro = lote_con_dos_dudosas
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote(), frozenset({100}))
    assert _vmids_leidos(banco) == {100}
    assert libro.entrada(100).estado == EstadoMV.NO_CREADA_SEGURA
    assert libro.entrada(102).estado == EstadoMV.CONEXION_PERDIDA  # intacta
    assert libro.entrada(101).estado == EstadoMV.OK


def test_ca_l15_7_comprobar_una_nunca_envia_un_post_ni_un_delete(banco, lote_con_dos_dudosas):
    banco.motor().comprobar_dudosas(
        lote_con_dos_dudosas, banco.observador, ControlLote(), frozenset({102})
    )
    assert banco.cluster.solo_lecturas
    assert banco.cluster.total("POST") == 0 and banco.cluster.total("DELETE") == 0
    assert banco.cluster.total("GET") >= 1


def test_ca_l15_6_sin_vmids_se_comprueban_todas_las_dudosas(banco, lote_con_dos_dudosas):
    banco.motor().comprobar_dudosas(lote_con_dos_dudosas, banco.observador, ControlLote())
    assert _vmids_leidos(banco) == {100, 102}
    assert banco.cluster.solo_lecturas


def test_ca_l15_6_un_vmid_que_no_es_dudoso_se_ignora_sin_tocar_el_servidor(
    banco, lote_con_dos_dudosas
):
    libro = lote_con_dos_dudosas
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote(), frozenset({101}))
    assert banco.cluster.llamadas == []  # la 101 ya está OK: nada que comprobar
    assert libro.entrada(101).estado == EstadoMV.OK


def test_ca_l15_6_un_vmid_inexistente_en_el_lote_no_rompe_ni_toca_a_otras(
    banco, lote_con_dos_dudosas
):
    libro = lote_con_dos_dudosas
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote(), frozenset({999}))
    assert banco.cluster.llamadas == []
    assert libro.entrada(100).estado == libro.entrada(102).estado == EstadoMV.CONEXION_PERDIDA


def test_ca_l15_6_comprobar_una_que_existe_con_la_etiqueta_la_da_por_creada_con_aviso(
    banco, lote_con_dos_dudosas
):
    libro = lote_con_dos_dudosas
    banco.cluster.agregar_vm(100, "pve1", "web-01", tags=f"proxlaunch;lote-{libro.id_lote}")
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote(), frozenset({100}))
    e = libro.entrada(100)
    assert e.estado == EstadoMV.OK and "creada_tras_comprobar" in e.avisos
    assert libro.entrada(102).estado == EstadoMV.CONEXION_PERDIDA


def test_ca_l15_6_comprobar_una_ajena_con_el_mismo_vmid_no_confirma_la_propiedad(
    banco, lote_con_dos_dudosas
):
    libro = lote_con_dos_dudosas
    banco.cluster.agregar_vm(100, "pve1", "otra-persona", tags="otra")
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote(), frozenset({100}))
    assert libro.entrada(100).estado == EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD
    assert banco.cluster.total("POST") == 0


def test_ca_l15_6_si_la_comprobacion_sigue_sin_poderse_la_maquina_queda_dudosa(
    banco, lote_con_dos_dudosas
):
    banco.cluster.regla("GET", r"qemu/100/config$", nodo_caido("pve1", 596))
    libro = lote_con_dos_dudosas
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote(), frozenset({100}))
    e = libro.entrada(100)
    assert e.estado == EstadoMV.CONEXION_PERDIDA
    assert e.error.codigo == CodigoError.LOTE_EXISTENCIA_INDETERMINADA
