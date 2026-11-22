"""Ventana principal con la fase B (0.7.0): asistente B2 desde 8.4, espera de IP al cerrar y al
deshacer, «Dejar de esperar la IP» y entrega de la contraseña al lote.

Derivadas de docs/requisitos/fase-b.md y de docs/arquitectura/fase-b.md §14 y §15: RF-B0.4,
CA-B3.5.3, CA-B3.5.4 (Deshacer cancela la espera ANTES del borrado), CA-B3.5.5 (cerrar con la
espera en marcha avisa y no escribe nada en el servidor) y la cesión del ``Secreto`` al lote.
"""

from __future__ import annotations

import threading

import pytest

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer

from . import test_ventana_principal as _base
from .apoyo import sesion_falsa
from .apoyo_fase_a import ClienteDeshacerFalso, lote_creado
from .apoyo_ventana_lote import Confirmaciones, conectar, esperar_fin, esperar_validacion

entorno = _base.entorno


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Cierra sin bloquear ni preguntar (cada prueba cambia ``confirmar`` si lo necesita)."""


@pytest.fixture
def cliente():
    return ClienteDeshacerFalso()


class EsperaFalsa:
    """Doble de ``EsperaIp``: anota cada ``cancelar`` en el registro común de eventos.

    ``cancelar`` bloquea en la real (hasta el timeout HTTP): la interfaz nunca lo llama desde su
    hilo. Aquí se anota el hilo que lo llamó para comprobarlo.
    """

    def __init__(self, eventos: list[tuple]) -> None:
        self.eventos = eventos
        self.hilos: list[int] = []
        self.sin_mas = 0

    def cancelar(self, vmids=None) -> None:
        self.hilos.append(threading.get_ident())
        self.eventos.append(("cancelar", None if vmids is None else frozenset(vmids)))

    def sin_mas_objetivos(self) -> None:
        self.sin_mas += 1


def con_espera_viva(v, eventos: list[tuple]) -> EsperaFalsa:
    """Deja el lote terminado como si aún se estuviera esperando la IP de sus máquinas."""
    espera = EsperaFalsa(eventos)
    v._lote.esperas.append(espera)
    v._lote.esperas_vivas = 1
    return espera


def registrar_borrados(cliente: ClienteDeshacerFalso, eventos: list[tuple]) -> None:
    """Cada ``DELETE`` del cliente falso pasa por el mismo registro que las cancelaciones."""
    original = cliente.eliminar_vm

    def eliminar(nodo, vmid):
        eventos.append(("delete", vmid))
        return original(nodo, vmid)

    cliente.eliminar_vm = eliminar  # type: ignore[method-assign]


def esperar_deshecho(qtbot, v) -> None:
    qtbot.waitUntil(lambda: not v._lote.deshaciendo and not v._lote.inspeccionando, timeout=8000)
    esperar_fin(qtbot, v)


# --- CA-B3.5.4: Deshacer corta la espera ANTES de borrar ---


def test_ca_b3_5_4_deshacer_cancela_la_espera_de_ip_antes_del_primer_borrado(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente)
    eventos: list[tuple] = []
    registrar_borrados(cliente, eventos)
    espera = con_espera_viva(v, eventos)

    v._deshacer()
    dialogo = v.findChildren(DialogoDeshacer)[0]
    dialogo.boton_eliminar.click()
    esperar_deshecho(qtbot, v)

    assert [e[0] for e in eventos if e[0] == "delete"] == ["delete"] * 3
    primero_borrado = next(i for i, e in enumerate(eventos) if e[0] == "delete")
    cancelaciones = [i for i, e in enumerate(eventos) if e[0] == "cancelar"]
    assert cancelaciones, "Deshacer debe cancelar la espera de IP"
    assert all(i < primero_borrado for i in cancelaciones), eventos
    assert eventos[cancelaciones[0]] == ("cancelar", frozenset({101, 102, 103}))
    # Bloquea hasta terminar la petición en vuelo: lo hace el trabajador, no el hilo de la interfaz.
    assert espera.hilos and threading.get_ident() not in espera.hilos


def test_ca_b3_5_4_deshacer_solo_algunas_cancela_la_espera_solo_de_esas(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    eventos: list[tuple] = []
    registrar_borrados(cliente, eventos)
    con_espera_viva(v, eventos)

    v._deshacer()
    dialogo = v.findChildren(DialogoDeshacer)[0]
    from PySide6.QtCore import Qt

    dialogo.lista.item(0).setCheckState(Qt.CheckState.Unchecked)  # no se elimina web-01
    dialogo.boton_eliminar.click()
    esperar_deshecho(qtbot, v)

    cancelaciones = [e for e in eventos if e[0] == "cancelar"]
    assert cancelaciones and all(e[1] == frozenset({102, 103}) for e in cancelaciones)
    assert sorted(cliente.eliminados) == [102, 103]


def test_ca_b3_5_4_cancelar_el_dialogo_de_deshacer_no_corta_la_espera_ni_borra(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente)
    eventos: list[tuple] = []
    registrar_borrados(cliente, eventos)
    con_espera_viva(v, eventos)

    v._deshacer()
    dialogo = v.findChildren(DialogoDeshacer)[0]
    dialogo.boton_cancelar.click()
    qtbot.waitUntil(lambda: not v.findChildren(DialogoDeshacer), timeout=2000)

    assert eventos == []
    assert cliente.eliminados == []


def test_el_dialogo_de_deshacer_avisa_de_que_dejara_de_esperar_la_ip_solo_si_alguien_espera(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente)
    v._deshacer()
    sin_espera = v.findChildren(DialogoDeshacer)[0]
    assert not sin_espera._nota_espera_ip.isVisibleTo(sin_espera)
    sin_espera.boton_cancelar.click()
    qtbot.waitUntil(lambda: not v.findChildren(DialogoDeshacer), timeout=2000)

    con_espera_viva(v, [])
    v._deshacer()
    con_espera = v.findChildren(DialogoDeshacer)[0]
    assert con_espera._nota_espera_ip.isVisibleTo(con_espera)
    assert "se dejará de esperar antes de borrarlas" in con_espera._nota_espera_ip.text()
    con_espera.boton_cancelar.click()


# --- CA-B3.5.3: «Dejar de esperar la IP» no deshace el lote ---


def test_ca_b3_5_3_dejar_de_esperar_la_ip_cancela_las_esperas_sin_tocar_el_servidor(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente)
    eventos: list[tuple] = []
    registrar_borrados(cliente, eventos)
    espera = con_espera_viva(v, eventos)
    llamadas_antes = len(cliente.llamadas)

    v.progreso_lote.dejar_de_esperar_ip_solicitado.emit()

    # En un hilo de fondo (``cancelar`` bloquea): se espera a que llegue.
    qtbot.waitUntil(lambda: eventos == [("cancelar", None)], timeout=3000)  # todo el lote
    assert threading.get_ident() not in espera.hilos
    assert cliente.eliminados == [] and cliente.escrituras == []
    assert len(cliente.llamadas) == llamadas_antes
    assert not v._lote.deshaciendo
    assert v.progreso_lote.boton_deshacer.isEnabled()  # las máquinas creadas se conservan


def test_ca_b3_5_3_dejar_de_esperar_la_ip_de_una_sola_maquina_tambien_cancela(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente)
    eventos: list[tuple] = []
    con_espera_viva(v, eventos)
    v.progreso.dejar_de_esperar_ip_solicitado.emit()
    qtbot.waitUntil(lambda: eventos == [("cancelar", None)], timeout=3000)


# --- CA-B3.5.5: cerrar la aplicación con la espera en marcha ---


def test_ca_b3_5_5_cerrar_con_la_espera_en_marcha_avisa_y_no_escribe_nada_en_el_servidor(
    qtbot, entorno, cliente, monkeypatch
):
    v = lote_creado(qtbot, entorno, cliente)
    eventos: list[tuple] = []
    registrar_borrados(cliente, eventos)
    con_espera_viva(v, eventos)
    confirmaciones = Confirmaciones(True)
    monkeypatch.setattr(vp, "confirmar", confirmaciones)
    llamadas_antes = len(cliente.llamadas)

    assert v.close() is True

    assert len(confirmaciones.llamadas) == 1
    titulo, texto, aceptar, cancelar = confirmaciones.llamadas[0]
    assert titulo == "Se está esperando la IP de las máquinas"
    assert "dejará de esperar" in texto
    assert "no pasa nada en el servidor" in texto
    assert (aceptar, cancelar) == ("Cerrar de todos modos", "Seguir en ProxLaunch")
    # La espera se corta (en un hilo de fondo) y el servidor no recibe ninguna escritura.
    qtbot.waitUntil(lambda: ("cancelar", None) in eventos, timeout=3000)
    assert cliente.escrituras == [] and cliente.eliminados == []
    nuevas = cliente.llamadas[llamadas_antes:]
    assert not [ll for ll in nuevas if ll[0] in ("eliminar_vm", "detener_vm", "configurar_vm")]


def test_ca_b3_5_5_si_se_elige_seguir_la_ventana_no_se_cierra_y_la_espera_continua(
    qtbot, entorno, cliente, monkeypatch
):
    v = lote_creado(qtbot, entorno, cliente)
    eventos: list[tuple] = []
    con_espera_viva(v, eventos)
    confirmaciones = Confirmaciones(False)
    monkeypatch.setattr(vp, "confirmar", confirmaciones)

    assert v.close() is False
    assert v.isVisible()
    assert len(confirmaciones.llamadas) == 1
    assert eventos == []  # no se cortó nada


def test_ca_b3_5_5_sin_espera_en_marcha_cerrar_no_pregunta(qtbot, entorno, cliente, monkeypatch):
    v = lote_creado(qtbot, entorno, cliente)
    confirmaciones = Confirmaciones(True)
    monkeypatch.setattr(vp, "confirmar", confirmaciones)
    assert v.close() is True
    assert confirmaciones.llamadas == []


# --- Contraseña: se cede al lote y los campos se vacían ---


def test_al_lanzar_el_lote_el_formulario_cede_el_secreto_y_despues_lo_limpia(
    qtbot, entorno, cliente, monkeypatch
):
    from .apoyo_ventana_lote import crear_lote, preparar_lote, ver_resumen

    preparar_lote(qtbot, entorno, cantidad=2, cliente=cliente)
    v = entorno.ventana
    orden: list[str] = []
    ceder, limpiar = v.formulario.ceder_secreto, v.formulario.limpiar_secretos
    monkeypatch.setattr(v.formulario, "ceder_secreto", lambda: (orden.append("ceder"), ceder()))
    monkeypatch.setattr(
        v.formulario, "limpiar_secretos", lambda: (orden.append("limpiar"), limpiar())
    )
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert orden == ["ceder", "limpiar"]


# --- RF-B0.4: el asistente B2 desde Proxmox 8.4 ---


def accion_b2(v):
    return v._accion_plantilla_imagen


def conectar_con(qtbot, entorno, version, *, forzada=False) -> None:
    conectar(qtbot, entorno, sesion_falsa(version=version, forzada=forzada))
    esperar_validacion(qtbot, entorno.ventana)
    entorno.ventana._actualizar_acciones()


@pytest.mark.parametrize(
    ("version", "disponible"),
    [((8, 0), False), ((8, 3), False), ((8, 4), True), ((9, 0), True), ((9, 2), True)],
)
def test_rf_b0_4_el_asistente_de_plantillas_solo_esta_disponible_desde_proxmox_8_4(
    qtbot, entorno, version, disponible
):
    conectar_con(qtbot, entorno, version)
    accion = accion_b2(entorno.ventana)
    assert accion.isEnabled() is disponible
    if not disponible:
        assert "8.4" in accion.toolTip()
    else:
        assert "8.4" not in accion.toolTip()  # sin aviso de versión (Qt devuelve el texto)


def test_rf_b0_4_el_asistente_esta_en_el_menu_archivo_con_su_nombre(qtbot, entorno):
    v = entorno.ventana
    menu = next(a.menu() for a in v.menuBar().actions() if a.menu() and "Archivo" in a.text())
    assert accion_b2(v) in menu.actions()
    assert accion_b2(v).text() == "Crear plantilla desde imagen cloud…"


def test_rf_b0_4_sin_conexion_el_asistente_esta_deshabilitado(qtbot, entorno):
    assert not accion_b2(entorno.ventana).isEnabled()


def test_rf_b0_4_una_version_forzada_8_4_habilita_el_asistente_en_un_servidor_viejo(qtbot, entorno):
    conectar_con(qtbot, entorno, (8, 4), forzada=True)
    assert accion_b2(entorno.ventana).isEnabled()
