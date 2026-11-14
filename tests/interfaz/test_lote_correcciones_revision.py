"""Correcciones de la revisión QA y la auditoría de seguridad del MVP 2 (interfaz).

Cada prueba cita el hallazgo que cubre (A2, M3, M4, M5, B1, B3, B5, B6, seguridad M1/B1).
Los dobles son los de los demás módulos de lotes: nada duerme de verdad ni toca la red.
"""

from __future__ import annotations

import os
import stat
import threading
from collections import Counter

import pytest
from PySide6.QtWidgets import QApplication

from proxlaunch.interfaz import informe_lote as il
from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.trabajadores import deshacer_lotes
from proxlaunch.interfaz.vistas.detalles_tecnicos import texto_detalles
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, texto_detalles_entrada
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    CandidatoRollback,
    EstadoMV,
    EstadoRollback,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.registro import olvidar_secretos, registrar_secreto
from proxlaunch.nucleo.reloj import RelojSimulado

from . import test_ventana_principal as _base
from .apoyo import (
    ClienteLoteFalso,
    CreacionFalsa,
    CreacionPorVmid,
    perfil,
    resultado,
    sesion_falsa,
    upid_de,
)
from .apoyo_lote import entrada, res_error, res_perdida
from .apoyo_ventana_lote import (
    crear_lote,
    esperar_fin,
    esperar_pausa,
    preparar_lote,
    ver_resumen,
)
from .test_lote_ventana_acciones import dialogo, existen, lanzar, simular
from .test_lote_ventana_uno import crear_incierto, entrada_unica
from .test_ventana_principal import conectar, crear_y_esperar, poner_nombre
from .test_ventana_principal_f7 import _comprobar_y_esperar, _incierto

entorno = _base.entorno
EM = EstadoMV
OTRO_PERFIL = ("otro", "Otro", ("10.0.0.9",))
HOST_DNS = "pve-prod.ejemplo.local"
IP = "10.0.0.5"


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Todas las pruebas de este módulo cierran sin bloquear."""


@pytest.fixture
def carpeta_informes(entorno, tmp_path):
    entorno.deps.directorio_informes = tmp_path / "informes"
    return entorno.deps.directorio_informes


class _CreacionRetenida(CreacionPorVmid):
    """Creación que, tras anunciar su UPID, no termina hasta ``soltar`` (ni aunque se cancele)."""

    def __init__(self) -> None:
        super().__init__()
        self.soltar = threading.Event()

    def crear(self, cfg, inv, al_cambiar_etapa, cancelado, **kw):
        r = super().crear(cfg, inv, al_cambiar_etapa, cancelado, **kw)
        self.soltar.wait(5)
        return r


class _ClienteConTareaRetenida(ClienteLoteFalso):
    """Cliente cuya consulta del estado de una tarea queda retenida hasta ``soltar``.

    «Comprobar» usa el servicio de creación real sobre el cliente de la sesión, así que retener
    aquí la lectura deja la comprobación «en curso» sin dormir de verdad.
    """

    def __init__(self) -> None:
        super().__init__()
        self.soltar = threading.Event()
        self.comprobando = threading.Event()

    def estado_tarea(self, nodo, upid):
        self.comprobando.set()
        self.soltar.wait(5)
        return super().estado_tarea(nodo, upid)


def _lote_con_una_dudosa_detenido(qtbot, entorno, creacion, cliente=None):
    from proxlaunch.interfaz.dialogos.pausa_lote import AccionPausa

    lanzar(qtbot, entorno, cantidad=2, creacion=creacion, cliente=cliente, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    v._lote.dialogo_pausa.botones[AccionPausa.DETENER].click()
    esperar_fin(qtbot, v)
    return v


# --- A2: «Ver el último lote» y resultados de un lote viejo ---------------------------------


def test_a2_ver_el_ultimo_lote_esta_desactivado_mientras_el_lote_corre(qtbot, entorno):
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)
    assert not v._accion_ultimo_lote.isEnabled()
    fase = v.progreso_lote.fase
    v._ver_ultimo_lote()  # aunque se invoque a mano, no reinicia la vista del lote vivo
    assert v.progreso_lote.fase == fase
    puerta.set()
    esperar_fin(qtbot, v)
    assert v._accion_ultimo_lote.isEnabled()


def test_a2_ver_el_ultimo_lote_esta_desactivado_durante_el_rollback(qtbot, entorno):
    import threading as th

    cliente = lanzar(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    existen(cliente, v)
    cliente.puerta_eliminar = th.Event()
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    qtbot.waitUntil(lambda: any(ll[0] == "eliminar_vm" for ll in cliente.llamadas), timeout=4000)
    assert v._lote.deshaciendo
    assert not v._accion_ultimo_lote.isEnabled()
    assert v.progreso_lote.fase == FaseLote.DESHACIENDO
    v._ver_ultimo_lote()
    assert v.progreso_lote.fase == FaseLote.DESHACIENDO  # la vista del rollback sigue intacta
    cliente.puerta_eliminar.set()
    esperar_fin(qtbot, v)
    assert v._accion_ultimo_lote.isEnabled()


def test_a2_ver_el_ultimo_lote_esta_desactivado_durante_la_comprobacion(qtbot, entorno):
    cliente = _ClienteConTareaRetenida()
    creacion = CreacionPorVmid({101: res_perdida(101)})
    v = _lote_con_una_dudosa_detenido(qtbot, entorno, creacion, cliente)
    assert v._accion_ultimo_lote.isEnabled()
    v.progreso_lote.boton_comprobar.click()
    assert cliente.comprobando.wait(5)
    try:
        assert not v._lote.terminado
        assert not v._accion_ultimo_lote.isEnabled()
        v._ver_ultimo_lote()
        assert v.progreso_lote.fase == FaseLote.COMPROBANDO
    finally:
        cliente.soltar.set()
    esperar_fin(qtbot, v)
    assert v._accion_ultimo_lote.isEnabled()


def test_a2_los_resultados_tardios_de_un_lote_viejo_no_tocan_el_lote_nuevo(qtbot, entorno):
    viejo_creacion = _CreacionRetenida()
    nueva_creacion = _CreacionRetenida()
    try:
        lanzar(qtbot, entorno, cantidad=2, creacion=viejo_creacion, esperar=False)
        v = entorno.ventana
        qtbot.waitUntil(lambda: viejo_creacion.entro(101).is_set(), timeout=4000)
        viejo = v._lote
        # Otro perfil: el lote viejo se cierra, pero su hilo sigue vivo y terminará más tarde.
        preparar_lote(
            qtbot,
            entorno,
            cantidad=2,
            cliente=ClienteLoteFalso(),
            creacion=nueva_creacion,
            perfil_=perfil(*OTRO_PERFIL),
        )
        assert viejo.cerrado and v._lote is None
        ver_resumen(qtbot, v)
        crear_lote(qtbot, v)
        qtbot.waitUntil(lambda: nueva_creacion.entro(101).is_set(), timeout=4000)
        nuevo = v._lote
        assert nuevo is not viejo and not nuevo.terminado
        fase = v.progreso_lote.fase
        # Termina el hilo del lote viejo: su resultado llega tarde a la interfaz.
        viejo_creacion.soltar.set()
        qtbot.waitUntil(
            lambda: all(e.estado != EM.PENDIENTE for e in viejo.libro.instantanea()), timeout=4000
        )
        QApplication.processEvents()
        qtbot.wait(50)
        assert v._lote is nuevo and not nuevo.terminado  # el lote nuevo sigue en marcha
        assert v.progreso_lote.fase == fase
        assert v._lote_en_curso
        assert nuevo.libro is not viejo.libro
    finally:
        viejo_creacion.soltar.set()
        nueva_creacion.soltar.set()
    esperar_fin(qtbot, v)
    assert v._lote is nuevo and nuevo.libro is not None


def test_a2_un_fallo_tardio_del_motor_viejo_se_descarta(qtbot, entorno):
    lanzar(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    viejo = v._lote
    preparar_lote(
        qtbot, entorno, cantidad=2, cliente=ClienteLoteFalso(), perfil_=perfil(*OTRO_PERFIL)
    )
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    nuevo = v._lote
    texto = v.progreso_lote._error.text()
    v._fallo_lote(viejo, ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "tardío"))
    v._al_lote_terminado(viejo, viejo.libro)
    v._tras_comprobar(viejo)
    v._tras_deshacer(viejo, [])
    v._fallo_deshacer(viejo, ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "tardío"))
    assert v._lote is nuevo and nuevo.terminado
    assert v.progreso_lote._error.text() == texto  # ningún mensaje del lote viejo
    assert v.progreso_lote.fase == FaseLote.TERMINADO


def test_a2_nunca_se_lanza_un_rollback_de_un_lote_contra_otro_perfil(qtbot, entorno):
    cliente = lanzar(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    existen(cliente, v)
    v.progreso_lote.boton_deshacer.click()
    d = dialogo(v, DialogoDeshacer)  # el diálogo queda abierto...
    otro = ClienteLoteFalso()
    conectar(qtbot, entorno, sesion_falsa(perfil(*OTRO_PERFIL), cliente=otro))  # ...y se cambia
    d.boton_eliminar.click()
    assert cliente.eliminados == [] and otro.eliminados == []
    assert not any(ll[0] == "eliminar_vm" for ll in [*cliente.llamadas, *otro.llamadas])
    assert v._lote is None or not v._lote.deshaciendo


def test_a2_comprobar_las_dudosas_no_se_lanza_contra_otro_perfil(qtbot, entorno):
    creacion = CreacionPorVmid({101: res_perdida(101)})
    v = _lote_con_una_dudosa_detenido(qtbot, entorno, creacion)
    viejo = v._lote
    conectar(qtbot, entorno, sesion_falsa(perfil(*OTRO_PERFIL), cliente=ClienteLoteFalso()))
    llamadas = len(creacion.llamadas_reanudar)
    v._lote = viejo  # un manejador tardío aún lo tiene a mano
    v._comprobar_dudosas()
    assert len(creacion.llamadas_reanudar) == llamadas  # no se comprobó nada
    v._lote = None


# --- M3: «Comprobar» con una sola máquina ---------------------------------------------------


def test_m3_una_maquina_rescatada_por_comprobar_lleva_el_aviso_creada_tras_comprobar(
    qtbot, entorno
):
    v = crear_incierto(qtbot, entorno, existe=None)
    entorno.cliente.configs[101] = {
        "name": "srv-web-01",
        "tags": f"proxlaunch;lote-{v._lote.plan.id_lote}",
    }
    entorno.creacion.respuesta_existe_vm = True
    _comprobar_y_esperar(qtbot, v)
    e = entrada_unica(v)
    assert e.estado == EM.OK and "creada_tras_comprobar" in e.avisos
    assert "creada_tras_comprobar" in v._informe_actual().entradas[0].avisos


def test_m3_sin_etiquetas_la_rescatada_por_comprobar_no_es_elegible_para_deshacer(qtbot, entorno):
    from proxlaunch.nucleo.persistencia.preferencias import Modo

    v = entorno.ventana
    cliente = ClienteLoteFalso()
    entorno.cliente = cliente
    entorno.creacion = CreacionFalsa(_incierto(), enviar_upid=False)
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente))
    v.establecer_modo(Modo.AVANZADO)
    v.bloque_lote.chk_etiquetar.setChecked(False)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    entorno.creacion.respuesta_existe_vm = True
    _comprobar_y_esperar(qtbot, v)
    e = entrada_unica(v)
    assert e.estado == EM.OK and "creada_tras_comprobar" in e.avisos
    assert not v._lote.plan.definicion.etiquetar
    (c,) = ServicioRollback(v._sesion, v._deps.reloj).elegibles(v._lote.libro, etiquetado=False)
    assert not c.elegible  # sin etiquetas no hay nada que ate la máquina al lote
    # El botón sigue visible (lo decide el desenlace), pero no ofrece nada que eliminar.
    v.progreso.boton_deshacer.click()
    assert dialogo(v, DialogoDeshacer).elegidos() == []
    assert cliente.eliminados == []


# --- B5: CANCELADO con UPID con una sola máquina --------------------------------------------


def test_b5_un_resultado_cancelado_con_upid_deja_la_maquina_como_conexion_perdida(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    entorno.creacion.respuestas_reanudar = [resultado(Desenlace.CANCELADO)]  # con UPID
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    v.progreso.boton_comprobar.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    # La tarea pudo seguir en Proxmox: es dudosa, no «no creada».
    assert entrada_unica(v).estado == EM.CONEXION_PERDIDA
    assert entrada_unica(v).upid is not None


# --- M4: si el motor falla, el libro sigue existiendo ----------------------------------------


def test_m4_si_el_motor_lanza_una_excepcion_el_libro_existe_y_deshacer_y_comprobar_siguen(
    qtbot, entorno, monkeypatch
):
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)

    def parcial_y_explota(sesion, reloj, plan, inv, observador, control, fabrica=None, libro=None):
        # Una máquina quedó creada y otra dudosa antes de que el motor fallara.
        libro.iniciar(101, 0.0)
        libro.marcar_post_intentado(101, 0.0)
        libro.registrar_upid(101, upid_de(101))
        libro.finalizar(101, EM.OK, t_fin=1.0)
        libro.iniciar(102, 0.0)
        libro.marcar_post_intentado(102, 0.0)
        libro.registrar_upid(102, upid_de(102))
        libro.finalizar(102, EM.CONEXION_PERDIDA, t_fin=1.0)
        raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom")

    monkeypatch.setattr(vp, "ejecutar_lote", parcial_y_explota)
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: v._lote.terminado, timeout=5000)
    assert v._lote.libro is not None
    p = v.progreso_lote
    assert p.boton_deshacer.isVisible() and p.boton_deshacer.isEnabled()
    assert p.boton_comprobar.isVisible()
    assert v._accion_ultimo_lote.isEnabled()
    assert v.progreso_lote._error.text().startswith("El lote terminó de forma inesperada")
    # Y «Deshacer» ofrece lo ya creado.
    existen(entorno.cliente, v)
    p.boton_deshacer.click()
    elegidos = dialogo(v, DialogoDeshacer).elegidos()
    assert [c.entrada.elemento.vmid for c in elegidos] == [101]


# --- M5: lo ya eliminado no se vuelve a ofrecer -----------------------------------------------


def test_m5_las_eliminadas_no_vuelven_a_ofrecerse_en_un_segundo_deshacer(qtbot, entorno):
    cliente = lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    existen(cliente, v)
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert sorted(cliente.eliminados) == [101, 102, 103]
    assert not v.progreso_lote.boton_deshacer.isEnabled()  # no queda nada elegible
    # Aunque alguien reutilice el VMID y el nombre, no se vuelve a ofrecer el mismo.
    existen(cliente, v)
    v._deshacer()
    assert dialogo(v, DialogoDeshacer).elegidos() == []


def test_m5_las_que_ya_no_existian_tampoco_vuelven_a_ofrecerse(qtbot, entorno):
    cliente = lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    existen(cliente, v)
    cliente.configs[102] = None  # desapareció por su cuenta: «ya no existía»
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert sorted(cliente.eliminados) == [101, 103]
    estados_rb = {r.vmid: r.estado for r in v._lote.resultados_rollback}
    assert estados_rb[102] == EstadoRollback.YA_NO_EXISTIA
    existen(cliente, v)
    v._deshacer()
    assert dialogo(v, DialogoDeshacer).elegidos() == []


def _lote_sin_etiquetas(qtbot, entorno, cliente):
    from proxlaunch.nucleo.persistencia.preferencias import Modo

    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente, avanzado=True)
    v = entorno.ventana
    v.establecer_modo(Modo.AVANZADO)
    v.bloque_lote.chk_etiquetar.setChecked(False)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert not v._lote.plan.definicion.etiquetar
    return v


def _existen_sin_etiquetas(cliente, v):
    for e in v._lote.libro.instantanea():
        cliente.configs[e.elemento.vmid] = {"name": e.elemento.nombre, "tags": ""}


def test_m5_deshacer_el_lote_a_sin_etiquetas_no_borra_la_maquina_del_lote_b(qtbot, entorno):
    cliente = ClienteLoteFalso()
    v = _lote_sin_etiquetas(qtbot, entorno, cliente)
    _existen_sin_etiquetas(cliente, v)
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert Counter(cliente.eliminados) == {101: 1, 102: 1, 103: 1}
    # El lote B reutiliza los mismos VMID y nombres (quedaron libres) y también existe.
    v.progreso_lote.boton_volver.click()
    qtbot.waitUntil(lambda: v.formulario.isEnabled(), timeout=2000)
    from proxlaunch.nucleo.persistencia.preferencias import Modo

    v.establecer_modo(Modo.AVANZADO)
    v.bloque_lote.chk_etiquetar.setChecked(False)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    _existen_sin_etiquetas(cliente, v)
    v.progreso_lote.boton_deshacer.click()
    d = dialogo(v, DialogoDeshacer)
    assert [c.entrada.elemento.vmid for c in d.elegidos()] == [101, 102, 103]  # solo las del B
    d.boton_eliminar.click()
    esperar_fin(qtbot, v)
    # Cada máquina se eliminó una vez por lote: la del lote A no se «deshizo» otra vez.
    assert Counter(cliente.eliminados) == {101: 2, 102: 2, 103: 2}


# --- B1: cerrar con un «Deshacer» en curso ----------------------------------------------------


def _rollback_retenido(qtbot, entorno, cantidad):
    cliente = lanzar(qtbot, entorno, cantidad=cantidad)
    v = entorno.ventana
    existen(cliente, v)
    cliente.puerta_eliminar = threading.Event()
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    qtbot.waitUntil(lambda: any(ll[0] == "eliminar_vm" for ll in cliente.llamadas), timeout=4000)
    assert v._lote.deshaciendo
    return cliente, v


def test_b1_cerrar_con_un_rollback_de_lote_en_curso_pide_confirmacion_y_lo_corta(
    qtbot, entorno, confirmaciones, carpeta_informes
):
    cliente, v = _rollback_retenido(qtbot, entorno, 3)

    def responder(parent, titulo, texto, aceptar, cancelar):
        confirmaciones.llamadas.append((titulo, texto, aceptar, cancelar))
        cliente.puerta_eliminar.set()
        return True

    vp.confirmar = responder  # restaurado por el monkeypatch de ``confirmaciones``
    control = v._lote.control_rollback
    assert v.close() is True
    assert len(confirmaciones.llamadas) == 1
    assert control.cancelado.is_set() and control.evento_abandono.is_set()
    assert len(cliente.eliminados) < 3  # el resto no se eliminó


def test_b1_cerrar_con_un_rollback_de_una_maquina_pide_confirmacion_y_lo_corta(
    qtbot, entorno, confirmaciones
):
    cliente = ClienteLoteFalso()
    v = entorno.ventana
    entorno.cliente = cliente
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente))
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert v._lote.modo_uno
    existen(cliente, v)
    cliente.puerta_eliminar = threading.Event()
    v.progreso.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    qtbot.waitUntil(lambda: any(ll[0] == "eliminar_vm" for ll in cliente.llamadas), timeout=4000)
    assert v._lote.deshaciendo
    control = v._lote.control_rollback

    def responder(parent, titulo, texto, aceptar, cancelar):
        confirmaciones.llamadas.append((titulo, texto, aceptar, cancelar))
        cliente.puerta_eliminar.set()
        return True

    vp.confirmar = responder
    assert v.close() is True
    assert len(confirmaciones.llamadas) == 1
    assert "Deshacer" in confirmaciones.llamadas[0][0]
    assert control.cancelado.is_set() and control.evento_abandono.is_set()


def test_b1_si_se_elige_seguir_el_rollback_no_se_toca(qtbot, entorno, confirmaciones):
    cliente, v = _rollback_retenido(qtbot, entorno, 2)
    confirmaciones.respuesta = False
    control = v._lote.control_rollback
    try:
        assert v.close() is False and v.isVisible()
        assert not control.cancelado.is_set()
    finally:
        cliente.puerta_eliminar.set()


def test_b1_si_un_hilo_sigue_vivo_al_cerrar_no_se_cierra_la_sesion(
    qtbot, entorno, confirmaciones, servicio_falso, monkeypatch
):
    # Cerrar la sesión suelta el autenticador: un hilo vivo podría renovar el ticket con una
    # credencial vacía (POST /access/ticket). Con hilos activos la sesión se deja como está.
    lanzar(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    sesion = v._sesion
    monkeypatch.setattr(v._lanzador, "esperar", lambda ms: False)
    assert v.close() is True
    assert ("cerrar_sesion", sesion) not in servicio_falso.llamadas


def test_b1_si_todos_los_hilos_terminaron_la_sesion_si_se_cierra(
    qtbot, entorno, confirmaciones, servicio_falso
):
    lanzar(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    sesion = v._sesion
    assert v.close() is True
    assert ("cerrar_sesion", sesion) in servicio_falso.llamadas


# --- B3: un error global del primer grupo detiene los demás grupos ---------------------------


def test_b3_un_error_global_en_un_grupo_de_deshacer_detiene_los_siguientes():
    cliente = ClienteLoteFalso()
    sesion = sesion_falsa(cliente=cliente)

    def grupo(vmids, id_lote):
        cands = []
        for i, vmid in enumerate(vmids):
            e = entrada(i, EM.OK, vmid=vmid, nombre=f"web-{vmid}", upid=upid_de(vmid))
            cliente.configs[vmid] = {
                "name": e.elemento.nombre,
                "tags": f"proxlaunch;lote-{id_lote}",
            }
            cands.append(CandidatoRollback(e, True, None, False))
        return cands, id_lote, True

    cliente.eliminar_falla[101] = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    observados = []
    control = ControlLote()
    resultados = deshacer_lotes(
        sesion,
        RelojSimulado(),
        [grupo([101, 102], "aaaa1111"), grupo([201, 202], "bbbb2222")],
        observados.append,
        control,
    )
    estados_por_vmid = {r.vmid: r.estado for r in resultados}
    assert estados_por_vmid[101] == EstadoRollback.FALLO
    assert estados_por_vmid[201] == estados_por_vmid[202] == EstadoRollback.NO_ENVIADA
    assert cliente.eliminados == []  # ni la 102 ni ninguna del segundo grupo
    assert not any(ll[0] == "eliminar_vm" and ll[2] in (201, 202) for ll in cliente.llamadas)


# --- B6: «Simular» con un reintento pendiente --------------------------------------------------


def test_b6_simular_con_un_reintento_pendiente_simula_el_plan_del_reintento(qtbot, entorno):
    creacion = CreacionPorVmid(
        {
            102: res_error(102, CodigoError.SIN_ESPACIO),
            104: res_error(104, CodigoError.SIN_ESPACIO),
        }
    )
    cliente = lanzar(qtbot, entorno, cantidad=5, creacion=creacion)
    v = entorno.ventana
    viejo = v.resumen_lote.plan
    v.progreso_lote.boton_reintentar.click()
    qtbot.waitUntil(
        lambda: (
            v.resumen_lote.plan is not None
            and v.resumen_lote.plan is not viejo
            and not v._planificando
        ),
        timeout=5000,
    )
    nombres_reintento = [e.nombre for e in v.resumen_lote.plan.elementos]
    assert nombres_reintento == ["web-02", "web-04"]
    solo_lectura = cliente.pidio_solo_lectura
    simular(qtbot, v)
    plan = v.resumen_lote.plan
    assert v.resumen_lote.es_simulacion and plan.es_simulacion
    # Es el plan del reintento (mismos nombres y VMIDs), no un lote nuevo de cinco.
    assert [(e.nombre, e.vmid) for e in plan.elementos] == [("web-02", 102), ("web-04", 104)]
    assert cliente.pidio_solo_lectura == solo_lectura + 1
    assert cliente.creados == [] and cliente.eliminados == []


# --- Seguridad M1: el nombre del perfil es el host o la IP ------------------------------------


def _perfil_con_nombre_de_red(nombre):
    return {"perfil_": perfil(nombre=nombre, hosts=(nombre,))}


@pytest.mark.parametrize("nombre", [IP, HOST_DNS])
def test_seg_m1_un_perfil_con_el_host_como_nombre_no_sale_en_el_informe_real(
    qtbot, entorno, nombre
):
    lanzar(qtbot, entorno, cantidad=2, **_perfil_con_nombre_de_red(nombre))
    v = entorno.ventana
    v.progreso_lote.boton_informe.click()
    d = dialogo(v, DialogoInforme)
    assert nombre not in d.texto and nombre not in d.editor.toPlainText()
    assert nombre not in il.texto_informe(v._informe_actual())


@pytest.mark.parametrize("nombre", [IP, HOST_DNS])
def test_seg_m1_un_perfil_con_el_host_como_nombre_no_sale_en_la_simulacion(qtbot, entorno, nombre):
    preparar_lote(qtbot, entorno, cantidad=2, **_perfil_con_nombre_de_red(nombre))
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    v.resumen_lote.boton_informe_simulacion.click()
    assert nombre not in dialogo(v, DialogoInforme).texto


@pytest.mark.parametrize("nombre", [IP, HOST_DNS])
def test_seg_m1_un_perfil_con_el_host_como_nombre_no_sale_en_el_informe_del_deshacer(
    qtbot, entorno, nombre
):
    cliente = lanzar(qtbot, entorno, cantidad=2, **_perfil_con_nombre_de_red(nombre))
    v = entorno.ventana
    existen(cliente, v)
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    texto = il.texto_informe(v._informe_actual())
    assert "Deshacer" in texto and nombre not in texto


@pytest.mark.parametrize("nombre", [IP, HOST_DNS])
def test_seg_m1_un_perfil_con_el_host_como_nombre_no_sale_en_el_informe_parcial(
    qtbot, entorno, confirmaciones, carpeta_informes, nombre
):
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    lanzar(
        qtbot,
        entorno,
        cantidad=3,
        creacion=creacion,
        esperar=False,
        **_perfil_con_nombre_de_red(nombre),
    )
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)
    qtbot.waitUntil(lambda: entorno.ventana.progreso_lote.hay_enviadas(), timeout=2000)
    v = entorno.ventana
    id_lote = v._lote.plan.id_lote
    assert v.close() is True
    parcial = carpeta_informes / f"parcial-{id_lote}.txt"
    assert parcial.is_file()
    assert nombre not in parcial.read_text(encoding="utf-8")


def test_seg_m1_con_un_nombre_de_perfil_normal_el_informe_si_lo_muestra(qtbot, entorno):
    lanzar(qtbot, entorno, cantidad=2, perfil_=perfil(nombre="Laboratorio", hosts=(IP,)))
    v = entorno.ventana
    assert "Laboratorio" in il.texto_informe(v._informe_actual())


# --- Seguridad B1: permisos de los informes -----------------------------------------------------

posix = pytest.mark.skipif(os.name != "posix", reason="los permisos 0o600/0o700 son de POSIX")


def _modo(ruta) -> int:
    return stat.S_IMODE(ruta.stat().st_mode)


def _informe_basico():
    from .apoyo_lote import informe_de

    return informe_de((entrada(0, EM.OK, upid=upid_de(101)),))


@posix
def test_seg_b1_el_informe_parcial_y_su_marca_se_guardan_con_permisos_privados(tmp_path):
    carpeta = tmp_path / "informes"
    ruta = il.guardar_informe_parcial(_informe_basico(), carpeta)
    assert ruta is not None and ruta.is_file()
    assert _modo(ruta) == 0o600
    assert _modo(carpeta) == 0o700
    marca = carpeta / "ultimo-informe-parcial.txt"
    assert marca.is_file() and _modo(marca) == 0o600


@posix
def test_seg_b1_una_carpeta_de_informes_ya_existente_con_permisos_amplios_se_restringe(tmp_path):
    carpeta = tmp_path / "informes"
    carpeta.mkdir(mode=0o755)
    os.chmod(carpeta, 0o755)
    il.guardar_informe_parcial(_informe_basico(), carpeta)
    assert _modo(carpeta) == 0o700


@posix
def test_seg_b1_el_informe_guardado_por_el_usuario_queda_con_permisos_0o600(tmp_path):
    ruta = tmp_path / "x" / "informe.txt"
    il.escribir_informe(ruta, "Máquina «ñ» ✓\n")
    assert _modo(ruta) == 0o600
    assert ruta.read_text(encoding="utf-8") == "Máquina «ñ» ✓\n"


@posix
def test_seg_b1_un_archivo_existente_con_permisos_amplios_se_restringe_al_sobrescribirlo(tmp_path):
    ruta = tmp_path / "informe.txt"
    ruta.write_text("viejo", encoding="utf-8")
    os.chmod(ruta, 0o644)
    il.escribir_informe(ruta, "nuevo")
    assert _modo(ruta) == 0o600
    assert ruta.read_text(encoding="utf-8") == "nuevo"


def test_seg_b1_el_informe_parcial_conserva_su_contenido_y_la_marca_apunta_a_el(tmp_path):
    informe = _informe_basico()
    ruta = il.guardar_informe_parcial(informe, tmp_path)
    assert ruta.name == f"parcial-{informe.id_lote}.txt"
    assert (tmp_path / "ultimo-informe-parcial.txt").read_text(encoding="utf-8") == str(ruta)
    assert il.tomar_aviso_informe_parcial(tmp_path) == ruta


# --- El log de la tarea mostrado en la interfaz pasa por ``enmascarar`` -------------------------

SENTINELA = "SENTINELA-log-7c1d-secreto"


@pytest.fixture
def secreto_registrado():
    registrar_secreto(SENTINELA)
    yield SENTINELA
    olvidar_secretos()


def test_el_log_de_la_tarea_de_una_entrada_del_lote_se_muestra_enmascarado(secreto_registrado):
    e = entrada(
        0,
        EM.ERROR,
        error=ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "x"),
        log_tarea=(f"autenticando con {SENTINELA}", "línea neutra"),
    )
    texto = texto_detalles_entrada(e)
    assert SENTINELA not in texto
    assert "línea neutra" in texto


def test_el_log_de_la_tarea_de_los_detalles_tecnicos_se_muestra_enmascarado(secreto_registrado):
    res = resultado(Desenlace.CON_AVISOS, log=[f"clave {SENTINELA}", "todo bien"])
    texto = texto_detalles(None, res)
    assert SENTINELA not in texto
    assert "todo bien" in texto
