"""Segunda pasada de pruebas del lote: funciones añadidas en la ronda de correcciones.

Cubre CA-L11.8, CA-L11.10, CA-L21.4, CA-L09.4, CA-L15.2, CA-L15.5, CA-L15.6, CA-L19.3,
CA-L24.5, la confirmación inmediata al cancelar y la diferencia lote / una máquina de
CA-L01.3, V-L01 y E-L03.
"""

from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton

from proxlaunch.interfaz import informe_lote as il
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.modelos.tarea import Desenlace

from . import test_ventana_principal as _base
from .apoyo import (
    ClienteLoteFalso,
    CreacionFalsa,
    CreacionPorVmid,
    perfil,
    resultado,
)
from .apoyo_lote import res_error, res_perdida
from .apoyo_ventana_lote import (
    crear_lote,
    esperar_fin,
    estados,
    preparar_lote,
    ver_resumen,
)
from .test_lote_robustez import ClienteLento
from .test_lote_ventana_acciones import dialogo, existen, lanzar, simular
from .test_ventana_principal import conectar, crear_y_esperar, poner_nombre

entorno = _base.entorno
EM = EstadoMV

HOST_DNS = "pve-prod.ejemplo.local"
USUARIO_PERFIL = "svc_centinela"


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Todas las pruebas de este módulo cierran sin bloquear."""


def _sin_eventos_pendientes(v, qtbot, ms: int = 30) -> None:
    """Deja correr el bucle de eventos un instante (sin esperas reales largas)."""
    qtbot.wait(ms)
    QApplication.processEvents()


# --- CA-L11.8: informe de la simulación ---------------------------------------------------------


def test_ca_l11_8_el_boton_del_informe_solo_aparece_en_una_simulacion(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    r = v.resumen_lote
    assert not r.boton_informe_simulacion.isVisible()  # un plan real no es una simulación
    simular(qtbot, v)
    assert r.boton_informe_simulacion.isVisible()
    assert "Informe de la simulación" in r.boton_informe_simulacion.text()


def test_ca_l11_8_el_informe_de_la_simulacion_se_titula_simulacion_y_lista_las_peticiones(
    qtbot, entorno
):
    cliente = preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    v.resumen_lote.boton_informe_simulacion.click()
    d = dialogo(v, DialogoInforme)
    assert d.windowTitle() == "Simulación del lote"
    primera = d.texto.splitlines()[0]
    assert primera.startswith("ProxLaunch — Simulación del lote ")
    assert "SIMULACIÓN — no se creó nada." in d.texto
    assert "Cómo encontrar estas máquinas" not in d.texto  # no hay nada que buscar en Proxmox
    for nombre in ("web-01", "web-02", "web-03"):
        assert nombre in d.texto
    # Exportar la simulación no crea nada ni deja un libro.
    assert v._lote is None and entorno.creacion.llamadas_crear == 0
    assert not any(ll[0] in ("crear_vm", "eliminar_vm") for ll in cliente.llamadas)


def test_ca_l11_8_copiar_y_guardar_la_simulacion_dan_el_mismo_texto_que_el_dialogo(
    qtbot, entorno, tmp_path, monkeypatch
):
    """«Copiar = guardar»: ambos usan la misma función de generación del informe real."""
    preparar_lote(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    v.resumen_lote.boton_informe_simulacion.click()
    d = dialogo(v, DialogoInforme)
    destino = tmp_path / "salida.txt"
    sugeridos: list[str] = []

    def elegir(parent, titulo, sugerido, filtro, *a, **k):
        sugeridos.append(sugerido)
        return str(destino), filtro

    monkeypatch.setattr(QFileDialog, "getSaveFileName", elegir)
    d.boton_copiar.click()
    d.boton_guardar.click()
    assert QApplication.clipboard().text() == d.texto == d.editor.toPlainText()
    assert destino.read_text(encoding="utf-8") == d.texto
    assert sugeridos and sugeridos[0].endswith(".txt") and "simulacion-" in sugeridos[0]


def test_ca_l11_8_el_informe_de_la_simulacion_usa_la_misma_funcion_que_el_informe_real(
    qtbot, entorno
):
    """El texto sale de ``texto_informe`` (única función) sobre el informe del plan simulado."""
    preparar_lote(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    v.resumen_lote.boton_informe_simulacion.click()
    d = dialogo(v, DialogoInforme)
    assert d.texto == il.texto_informe(d._informe)
    assert d._informe.es_simulacion and d._informe.pedidas == 2


# --- CA-L11.10: cancelar la preparación y la simulación -----------------------------------------


def test_ca_l11_10_cancelar_con_el_boton_de_la_preparacion_vuelve_al_formulario(qtbot, entorno):
    cliente = ClienteLento()
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    try:
        assert cliente.entro.wait(5) and v._planificando
        assert v.resumen_lote.boton_cancelar.isVisible()  # «Cancelar» mientras se prepara
        inicio = time.perf_counter()
        v.resumen_lote.boton_cancelar.click()
        assert time.perf_counter() - inicio < 0.2  # la interfaz no se bloquea
        assert not v._planificando and v._pila_derecha.currentIndex() == 0
    finally:
        cliente.liberar.set()


def test_ca_l11_10_el_resultado_tardio_de_la_preparacion_se_descarta(qtbot, entorno):
    cliente = ClienteLento()
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    assert cliente.entro.wait(5)
    v.resumen_lote.boton_cancelar.click()
    cliente.liberar.set()  # el trabajo en segundo plano termina DESPUÉS de cancelar
    v._lanzador.esperar(3000)
    _sin_eventos_pendientes(v, qtbot)
    assert v.resumen_lote.plan is None and v._plan_mostrado is None
    assert v._pila_derecha.currentIndex() == 0  # sigue en el formulario, no salta al resumen
    assert v._lote is None and entorno.creacion.llamadas_crear == 0
    assert not v._planificando


def test_ca_l11_10_tras_cancelar_se_puede_preparar_de_nuevo(qtbot, entorno):
    cliente = ClienteLento()
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    assert cliente.entro.wait(5)
    v.resumen_lote.boton_cancelar.click()
    cliente.liberar.set()
    v._lanzador.esperar(3000)
    _sin_eventos_pendientes(v, qtbot)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    ver_resumen(qtbot, v)
    assert v.resumen_lote.plan is not None and len(v.resumen_lote.plan.elementos) == 3


def test_ca_l11_10_cancelar_la_simulacion_descarta_su_resultado_tardio(qtbot, entorno):
    cliente = ClienteLento()
    cliente.liberar.set()  # la preparación normal no se retiene
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    plan_real = v.resumen_lote.plan
    cliente.liberar.clear()
    cliente.entro.clear()
    v.resumen_lote.boton_simular.click()  # la simulación vuelve a consultar al servidor
    try:
        assert cliente.entro.wait(5) and v._planificando
        inicio = time.perf_counter()
        v.resumen_lote.boton_cancelar.click()
        assert time.perf_counter() - inicio < 0.2
        assert v._pila_derecha.currentIndex() == 0
    finally:
        cliente.liberar.set()
    v._lanzador.esperar(3000)
    _sin_eventos_pendientes(v, qtbot)
    r = v.resumen_lote
    assert r.plan is None and not r.es_simulacion and plan_real is not None
    assert not r.boton_informe_simulacion.isVisible()
    assert v._pila_derecha.currentIndex() == 0 and v._lote is None
    assert entorno.creacion.llamadas_crear == 0


def test_ca_l11_10_cancelar_no_deja_nada_creado_ni_escrito_en_el_servidor(qtbot, entorno):
    cliente = ClienteLento()
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    assert cliente.entro.wait(5)
    v.resumen_lote.boton_cancelar.click()
    cliente.liberar.set()
    v._lanzador.esperar(3000)
    assert cliente.creados == [] and cliente.eliminados == []
    assert not any(ll[0] in ("crear_vm", "eliminar_vm") for ll in cliente.llamadas)


# --- CA-L21.4: deshacer tras un reintento -------------------------------------------------------


def _lote_y_reintento(qtbot, entorno, *, etiquetar_reintento: bool | None = None):
    """Primer lote de 5 con la 102 y la 104 falladas; luego se crea el lote de reintento."""
    creacion = CreacionPorVmid(
        {
            102: resultado(
                Desenlace.ERROR,
                error=ErrorProxLaunch(CodigoError.SIN_ESPACIO, {}, "texto original"),
                vmid=102,
            ),
            104: res_error(104, CodigoError.SIN_ESPACIO),
        }
    )
    cliente = lanzar(qtbot, entorno, cantidad=5, creacion=creacion)
    v = entorno.ventana
    id_primero = v._lote.plan.id_lote
    existen(cliente, v)  # 101, 103 y 105 existen con la etiqueta del primer lote
    viejo = v.resumen_lote.plan
    if etiquetar_reintento is None:
        v.progreso_lote.boton_reintentar.click()
    else:
        v._reintentar_pendientes(etiquetar=etiquetar_reintento)
    qtbot.waitUntil(
        lambda: (
            v.resumen_lote.plan is not None
            and v.resumen_lote.plan is not viejo
            and not v._planificando
        ),
        timeout=5000,
    )
    creacion.por_vmid.clear()
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert v._lote.plan.id_lote != id_primero
    return cliente, id_primero


def test_ca_l21_4_deshacer_tras_el_reintento_ofrece_las_de_ambos_lotes(qtbot, entorno):
    cliente, _ = _lote_y_reintento(qtbot, entorno)
    v = entorno.ventana
    existen(cliente, v)  # 102 y 104 existen con la etiqueta del lote de reintento
    assert v.progreso_lote.boton_deshacer.isEnabled()
    v.progreso_lote.boton_deshacer.click()
    d = dialogo(v, DialogoDeshacer)
    assert sorted(c.entrada.elemento.vmid for c in d.elegidos()) == [101, 102, 103, 104, 105]


def test_ca_l21_4_cada_lote_se_deshace_con_su_propio_id_de_etiqueta(qtbot, entorno):
    """Si se usara el id del lote nuevo para las del primero, la etiqueta no coincidiría y se
    omitirían («no podemos asegurar que la creó este lote»)."""
    cliente, _ = _lote_y_reintento(qtbot, entorno)
    v = entorno.ventana
    existen(cliente, v)
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert sorted(cliente.eliminados) == [101, 102, 103, 104, 105]


def test_ca_l21_4_cada_lote_conserva_su_politica_de_etiquetas(qtbot, entorno):
    """El primer lote lleva etiquetas (se exige la suya); el reintento se creó sin etiquetas."""
    cliente, _ = _lote_y_reintento(qtbot, entorno, etiquetar_reintento=False)
    v = entorno.ventana
    # Las del reintento no llevan etiquetas; una del primer lote cambió de dueño.
    cliente.configs[102] = {"name": "web-02", "tags": ""}
    cliente.configs[104] = {"name": "web-04", "tags": ""}
    cliente.configs[103]["tags"] = "lote-ffffffff"
    v.progreso_lote.boton_deshacer.click()
    d = dialogo(v, DialogoDeshacer)
    assert sorted(c.entrada.elemento.vmid for c in d.elegidos()) == [101, 102, 103, 104, 105]
    d.boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert sorted(cliente.eliminados) == [101, 102, 104, 105]  # la 103 ajena nunca se borra


def test_ca_l21_4_el_informe_del_deshacer_lista_las_de_ambos_lotes(qtbot, entorno):
    cliente, _ = _lote_y_reintento(qtbot, entorno)
    v = entorno.ventana
    existen(cliente, v)
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert {r.vmid for r in v._informe_actual().rollback} >= {102, 104}


# --- CA-L09.4: permisos que no se pudieron leer -------------------------------------------------


def test_ca_l09_4_el_resumen_avisa_que_los_permisos_no_se_verificaron_y_deja_crear(qtbot, entorno):
    cliente = ClienteLoteFalso()
    cliente.fallo_permisos = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    r = v.resumen_lote
    assert not r.plan.permisos_verificados and not r.plan.bloqueado
    assert "Permisos no verificados" in r._avisos.text()
    assert r.boton_crear.isEnabled()  # el aviso no bloquea (CA-L09.4)


def test_ca_l09_4_con_permisos_leidos_el_resumen_no_trae_el_aviso(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    assert v.resumen_lote.plan.permisos_verificados
    assert "Permisos no verificados" not in v.resumen_lote._avisos.text()


def test_ca_l09_4_el_informe_del_lote_y_el_de_la_simulacion_lo_dicen(qtbot, entorno):
    cliente = ClienteLoteFalso()
    cliente.fallo_permisos = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    preparar_lote(qtbot, entorno, cantidad=2, cliente=cliente)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    assert "Permisos no verificados" in v.resumen_lote._avisos.text()
    v.resumen_lote.boton_informe_simulacion.click()
    assert "Permisos no verificados" in dialogo(v, DialogoInforme).texto
    dialogo(v, DialogoInforme).boton_cerrar.click()
    v.resumen_lote.boton_volver.click()
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert estados(v) == ["ok", "ok"]  # no se bloqueó
    v.progreso_lote.boton_informe.click()
    assert "Permisos no verificados" in dialogo(v, DialogoInforme).texto


# --- CA-L15.6: «Comprobar ahora» por máquina dudosa ---------------------------------------------


def _lote_con_dos_dudosas(qtbot, entorno):
    creacion = CreacionPorVmid(
        {101: res_perdida(101, incierto=True), 103: res_perdida(103, incierto=True)}
    )
    creacion.respuesta_existe_vm = None  # no se puede saber: quedan dudosas
    cliente = lanzar(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    assert estados(v) == ["conexion_perdida", "ok", "conexion_perdida"]
    return creacion, cliente, v


def _lecturas_de_config(llamadas) -> set[int]:
    """VMIDs cuya configuración se leyó (GET /config) entre las llamadas del cliente."""
    return {ll[2] for ll in llamadas if ll[0] == "config_vm"}


def _esperar_comprobacion(qtbot, v):
    qtbot.waitUntil(lambda: v.progreso_lote.fase == FaseLote.TERMINADO, timeout=8000)
    qtbot.waitUntil(lambda: v._lote.terminado and not v._lote.deshaciendo, timeout=8000)


def test_ca_l15_6_comprobar_ahora_solo_aparece_con_una_dudosa_seleccionada(qtbot, entorno):
    creacion, cliente, v = _lote_con_dos_dudosas(qtbot, entorno)
    p = v.progreso_lote
    p.tabla.selectRow(0)
    assert p.boton_comprobar_una.isVisible()
    p.tabla.selectRow(1)  # una creada con éxito: no hay nada que comprobar
    assert not p.boton_comprobar_una.isVisible()
    p.tabla.selectRow(2)
    assert p.boton_comprobar_una.isVisible()
    assert "No sabemos si se creó" in p.modelo.data(p.modelo.index(2, 0))


def test_ca_l15_6_comprobar_una_dudosa_solo_lee_y_no_toca_a_las_demas(qtbot, entorno):
    creacion, cliente, v = _lote_con_dos_dudosas(qtbot, entorno)
    id_lote = v._lote.plan.id_lote
    cliente.configs[101] = {"name": "web-01", "tags": f"proxlaunch;lote-{id_lote}"}
    creadas_antes = list(creacion.vmids_creados)
    llamadas_cliente_antes = len(cliente.llamadas)
    p = v.progreso_lote
    p.tabla.selectRow(0)
    p.boton_comprobar_una.click()
    _esperar_comprobacion(qtbot, v)
    assert estados(v) == ["ok", "ok", "conexion_perdida"]  # solo la 101 cambió
    # Nunca un POST: ni el servicio de creación ni el cliente recibieron una escritura.
    assert creacion.vmids_creados == creadas_antes and creacion.llamadas_crear == 3
    assert cliente.creados == [] and cliente.eliminados == []
    nuevas = cliente.llamadas[llamadas_cliente_antes:]
    assert all(ll[0] not in ("crear_vm", "eliminar_vm") for ll in nuevas), nuevas
    # Y solo se leyó la configuración de la máquina elegida: ninguna lectura de la 103.
    assert _lecturas_de_config(nuevas) == {101}
    assert {ll[0] for ll in nuevas} <= {"config_vm", "estado_tarea", "log_tarea"}  # solo GET


def test_ca_l15_6_comprobar_ahora_que_no_existe_la_deja_como_no_creada_segura(qtbot, entorno):
    creacion, cliente, v = _lote_con_dos_dudosas(qtbot, entorno)
    antes = len(cliente.llamadas)
    cliente.configs.pop(103, None)  # no existe en el servidor
    p = v.progreso_lote
    p.tabla.selectRow(2)
    p.boton_comprobar_una.click()
    _esperar_comprobacion(qtbot, v)
    assert estados(v) == ["conexion_perdida", "ok", "no_creada_segura"]
    assert _lecturas_de_config(cliente.llamadas[antes:]) == {103}
    assert cliente.creados == [] and creacion.llamadas_crear == 3  # nunca se reenvía sola


def test_ca_l15_6_la_comprobacion_global_sigue_comprobando_todas_las_dudosas(qtbot, entorno):
    creacion, cliente, v = _lote_con_dos_dudosas(qtbot, entorno)
    antes = len(cliente.llamadas)
    v.progreso_lote.boton_comprobar.click()
    _esperar_comprobacion(qtbot, v)
    assert _lecturas_de_config(cliente.llamadas[antes:]) == {101, 103}
    assert creacion.llamadas_crear == 3 and cliente.creados == []


# --- CA-L24.5: «Acerca de» menciona la etiqueta -------------------------------------------------


@pytest.mark.parametrize("tema", ["claro", "oscuro"])
def test_ca_l24_5_acerca_de_explica_las_dos_etiquetas_y_para_que_sirven(qtbot, tema):
    from proxlaunch.interfaz.dialogos.acerca_de import DialogoAcercaDe

    d = DialogoAcercaDe(tema)
    qtbot.addWidget(d)
    texto = " ".join(w.text() for w in d.findChildren(QLabel))
    assert "«proxlaunch»" in texto and "«lote-…»" in texto
    assert "deshacer" in texto.lower()


# --- CA-L15.2 y CA-L15.5 con una sola máquina ---------------------------------------------------


def _una_dudosa(qtbot, entorno, *, existe):
    from .test_lote_ventana_uno import crear_incierto

    return crear_incierto(qtbot, entorno, existe=existe, cliente=ClienteLoteFalso())


def test_ca_l15_2_con_una_maquina_el_aviso_de_creada_tras_comprobar_se_ve_y_va_al_informe(
    qtbot, entorno
):
    from .test_lote_ventana_uno import existe_con_etiqueta_del_lote

    v = existe_con_etiqueta_del_lote(qtbot, entorno)
    assert "creada_tras_comprobar" in v._lote.libro.instantanea()[0].avisos
    assert "tardó en responder" in v.progreso.texto_mensaje
    assert "Se creó aunque Proxmox tardó en responder" in il.texto_informe(v._informe_actual())


@pytest.mark.parametrize(
    "etiquetas, esperado",
    [
        ("proxlaunch;lote-{id}", EM.OK),
        ("otra;lote-{id};proxlaunch", EM.OK),
        ("lote-{id}", EM.OK),
        ("proxlaunch", EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD),
        ("proxlaunch;lote-ffffffff", EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD),
        ("proxlaunch;lote-{id}x", EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD),  # solo un prefijo del id
        ("", EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD),
    ],
)
def test_ca_l15_5_comprobar_con_una_maquina_decide_la_propiedad_por_la_etiqueta_del_lote(
    qtbot, entorno, etiquetas, esperado
):
    from .test_ventana_principal_f7 import _comprobar_y_esperar

    v = _una_dudosa(qtbot, entorno, existe=None)
    unica = v._lote.libro.instantanea()[0]
    assert unica.estado == EM.CONEXION_PERDIDA
    id_lote = v._lote.plan.id_lote
    entorno.cliente.configs[101] = {
        "name": "srv-web-01",
        "tags": etiquetas.format(id=id_lote),
    }
    entorno.creacion.respuesta_existe_vm = True
    _comprobar_y_esperar(qtbot, v)
    assert v._lote.libro.instantanea()[0].estado == esperado
    assert entorno.creacion.llamadas_crear == 1  # comprobar nunca reenvía


def test_ca_l15_5_comprobar_con_la_config_ilegible_no_da_la_maquina_por_propia(qtbot, entorno):
    from .test_ventana_principal_f7 import _comprobar_y_esperar

    v = _una_dudosa(qtbot, entorno, existe=None)
    entorno.creacion.respuesta_existe_vm = True  # existe, pero GET config no devuelve nada
    entorno.cliente.configs[101] = None
    _comprobar_y_esperar(qtbot, v)
    assert v._lote.libro.instantanea()[0].estado == EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD
    assert not v.progreso.boton_deshacer.isVisible()


# --- CA-L19.3: ni host ni usuario en el informe, de punta a punta -------------------------------


def _sesion_con_centinelas():
    return {
        "perfil_": perfil(hosts=(HOST_DNS,), usuario=USUARIO_PERFIL),
    }


def _error_con_centinelas(vmid: int):
    return res_error(
        vmid,
        CodigoError.SERVIDOR_NO_RESPONDE,
        con_upid=False,
        detalle=(
            f"HTTPSConnectionPool(host='{HOST_DNS}', port=8006): Read timed out. "
            f"(usuario {USUARIO_PERFIL})"
        ),
        mensaje=f"sin respuesta de {HOST_DNS} para {USUARIO_PERFIL}",
        puerto="8006",
    )


def test_ca_l19_3_el_informe_copiado_desde_la_ventana_no_trae_el_host_dns_ni_el_usuario(
    qtbot, entorno
):
    creacion = CreacionPorVmid({102: _error_con_centinelas(102)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, **_sesion_con_centinelas())
    v = entorno.ventana
    assert estados(v) == ["ok", "error", "ok"]
    v.progreso_lote.boton_informe.click()
    d = dialogo(v, DialogoInforme)
    d.boton_copiar.click()
    copiado = QApplication.clipboard().text()
    assert "web-02" in copiado  # el error sí está...
    for texto in (d.texto, copiado, d.editor.toPlainText()):
        for prohibido in (HOST_DNS, "ejemplo.local", USUARIO_PERFIL, "ana@pve"):
            assert prohibido not in texto, prohibido


def test_ca_l19_3_el_informe_guardado_tampoco_trae_el_host_ni_el_usuario(
    qtbot, entorno, tmp_path, monkeypatch
):
    creacion = CreacionPorVmid({102: _error_con_centinelas(102)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, **_sesion_con_centinelas())
    v = entorno.ventana
    v.progreso_lote.boton_informe.click()
    destino = tmp_path / "informe.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
    dialogo(v, DialogoInforme).boton_guardar.click()
    guardado = destino.read_text(encoding="utf-8")
    for prohibido in (HOST_DNS, USUARIO_PERFIL, "ana@pve"):
        assert prohibido not in guardado, prohibido


def test_ca_l19_3_el_informe_de_la_simulacion_no_trae_el_host_ni_el_usuario(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=2, **_sesion_con_centinelas())
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    v.resumen_lote.boton_informe_simulacion.click()
    texto = dialogo(v, DialogoInforme).texto
    for prohibido in (HOST_DNS, USUARIO_PERFIL, "ana@pve"):
        assert prohibido not in texto, prohibido


def test_ca_l19_3_el_informe_del_deshacer_tampoco_filtra_el_host(qtbot, entorno):
    cliente = lanzar(qtbot, entorno, cantidad=2, **_sesion_con_centinelas())
    v = entorno.ventana
    existen(cliente, v)
    cliente.eliminar_falla[102] = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE,
        {"mensaje": f"sin respuesta de {HOST_DNS}"},
        f"HTTPSConnectionPool(host='{HOST_DNS}', port=8006) {USUARIO_PERFIL}",
    )
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    texto = il.texto_informe(v._informe_actual())
    assert "web-02" in texto and "Deshacer" in texto
    for prohibido in (HOST_DNS, USUARIO_PERFIL):
        assert prohibido not in texto, prohibido


# --- Cancelar: la confirmación no espera al refresco de 100 ms ----------------------------------


def test_cancelar_pide_confirmacion_en_cuanto_sale_el_primer_envio_sin_esperar_al_refresco(
    qtbot, entorno, confirmaciones, monkeypatch
):
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    preparar_lote(qtbot, entorno, cantidad=4, creacion=creacion)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    # El panel nunca llega a enterarse de lo enviado: equivale a cancelar antes del primer
    # refresco del temporizador (100 ms).
    monkeypatch.setattr(v.progreso_lote, "actualizar", lambda *_a, **_k: None)
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: v._lote.puente.instantanea()[0].post_intentado, timeout=4000)
    assert not v.progreso_lote.hay_enviadas()  # el panel sigue sin saber del envío
    v.progreso_lote.boton_cancelar.click()
    assert len(confirmaciones.llamadas) == 1, "no preguntó, aunque ya se había enviado una"
    assert "seguirán creándose en Proxmox" in confirmaciones.llamadas[0][1]
    assert v._lote.cancelando
    puerta.set()
    esperar_fin(qtbot, v)
    assert creacion.vmids_creados == [101]


# --- CA-L01.3, V-L01 y E-L03: una sola máquina frente a un lote ---------------------------------


@pytest.mark.parametrize(
    "cantidad, frase",
    [
        ("101", "El máximo por lote es 100 máquinas. Divide el trabajo en varios lotes."),
        ("0", "Elige entre 1 y 100 máquinas."),
        ("abc", "Elige entre 1 y 100 máquinas."),
    ],
)
def test_ca_l01_3_y_v_l01_la_cantidad_invalida_bloquea_el_resumen_desde_la_ventana(
    qtbot, entorno, cantidad, frase
):
    from .apoyo_ventana_lote import escribir

    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    b = v.bloque_lote
    escribir(b.cantidad, cantidad)
    from .test_ventana_principal import esperar_validacion

    esperar_validacion(qtbot, v)
    assert frase in b._filas["cantidad"]._error.text()
    assert not v.resumen.boton_crear.isEnabled()  # sin resumen con una cantidad inválida


def test_ca_l01_1_con_cantidad_uno_no_hay_bloque_de_error_y_se_crea_como_en_m1(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    assert not v.bloque_lote._filas["cantidad"].hay_error
    crear_y_esperar(qtbot, v)
    assert v._lote.modo_uno and entorno.creacion.llamadas_crear == 1


def test_e_l03_con_una_sola_maquina_usa_el_texto_de_m1_con_el_siguiente_libre(qtbot, entorno):
    v = entorno.ventana
    err = ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "101", "siguiente": "102"})
    entorno.creacion = CreacionFalsa(resultado(Desenlace.ERROR, err, upid=None))
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    texto = v.formulario.fila_vmid._error.text()
    assert "ya lo usa otra máquina" in texto and "102" in texto
    assert "lo usó otra persona" not in texto
    assert v.formulario.nombre.text() == "srv-web-01"  # conserva lo escrito (flujo de M1)


def test_e_l03_en_un_lote_se_marca_esa_maquina_y_el_lote_sigue(qtbot, entorno):
    from proxlaunch.interfaz.modelos_tabla import detalle_entrada

    creacion = CreacionPorVmid({102: res_error(102, CodigoError.VMID_OCUPADO, con_upid=False)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    assert estados(v) == ["ok", "error", "ok"]
    texto = detalle_entrada(v._lote.libro.instantanea()[1])
    assert "lo usó otra persona mientras tanto" in texto and "no se creó" in texto.lower()
    assert "ya lo usa otra máquina" not in texto  # no es el mensaje de la ficha de una máquina
    assert isinstance(v.progreso_lote.boton_reintentar, QPushButton)
    assert v.progreso_lote.boton_reintentar.isVisible()  # «Reintentar pendientes»
