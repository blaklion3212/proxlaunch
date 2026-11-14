"""Lotes de varias máquinas en la ventana principal: resumen, ejecución, pausa, cancelación,
deshacer, reintento, informe y cierre (RF-L10 a RF-L23, de punta a punta con dobles).

El motor, el planificador y el servicio de rollback son los reales del núcleo; solo el
cliente de Proxmox y el servicio de creación son dobles (``apoyo.py``).
"""

from __future__ import annotations

import dataclasses
from collections import Counter

import pytest

from proxlaunch.interfaz.vistas.progreso_lote import FaseLote
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.modelos.inventario import VMRemota
from proxlaunch.nucleo.modelos.tarea import Desenlace

from . import test_ventana_principal as _base
from .apoyo import ClienteLoteFalso, CreacionPorVmid, resultado, upid_de
from .apoyo_ventana_lote import (
    crear_lote,
    escribir,
    esperar_fin,
    estados,
    preparar_lote,
    ver_resumen,
)
from .test_ventana_principal import esperar_validacion

entorno = _base.entorno
EM = EstadoMV


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Todas las pruebas de este módulo cierran sin bloquear."""


def err(codigo, **params):
    return ErrorProxLaunch(codigo, {k: str(v) for k, v in params.items()}, "texto original")


def fallo(vmid, codigo=CodigoError.SIN_ESPACIO, **params):
    return resultado(Desenlace.ERROR, error=err(codigo, **params), upid=upid_de(vmid), vmid=vmid)


def lote_listo(qtbot, entorno, **kw):
    """Prepara, pide el resumen y lo deja a un clic de crear."""
    cliente = preparar_lote(qtbot, entorno, **kw)
    ver_resumen(qtbot, entorno.ventana)
    return cliente


def ejecutar(qtbot, entorno, **kw):
    cliente = lote_listo(qtbot, entorno, **kw)
    crear_lote(qtbot, entorno.ventana)
    esperar_fin(qtbot, entorno.ventana)
    return cliente


# --- Camino feliz y pantallas (RF-L10, RF-L13) ----------------------------------------------


def test_ca_l02_6_la_vista_previa_de_nombres_se_actualiza_en_vivo(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=3, prefijo="web")
    assert entorno.ventana.bloque_lote.texto_vista_previa == "Se llamarán: web-01, web-02, web-03"
    escribir(entorno.ventana.bloque_lote.prefijo, "db")
    esperar_validacion(qtbot, entorno.ventana)
    assert entorno.ventana.bloque_lote.texto_vista_previa == "Se llamarán: db-01, db-02, db-03"


def test_con_mas_de_una_maquina_el_boton_principal_lleva_al_resumen(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    assert v.resumen.boton_crear.text() == "Ver resumen"
    ver_resumen(qtbot, v)
    assert v._pila_derecha.currentIndex() == 1
    assert v.resumen_lote._titulo.text() == "Vas a crear 3 máquinas"
    assert entorno.creacion.llamadas_crear == 0  # ver el resumen no crea nada


def test_ca_l12_2_y_l10_9_mientras_corre_todo_queda_bloqueado(qtbot, entorno):
    puertas = {101: __import__("threading").Event()}
    entorno_creacion = CreacionPorVmid(puertas=puertas)
    lote_listo(qtbot, entorno, creacion=entorno_creacion)
    v = entorno.ventana
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: entorno_creacion.entro(101).is_set(), timeout=4000)
    assert v._pila_derecha.currentIndex() == 2
    assert not v.formulario.isEnabled() and not v.bloque_lote.isEnabled()
    assert not v.boton_actualizar.isEnabled() and not v.boton_reintentar.isEnabled()
    assert not v.resumen_lote.boton_crear.isEnabled()
    assert not v.resumen_lote.boton_simular.isEnabled()
    assert v.progreso_lote.fase == FaseLote.EJECUTANDO
    assert v.progreso_lote.boton_cancelar.isVisible()  # CA-L13.7
    # Solo hay un lote activo: otro intento de resumen no hace nada (V-L17).
    v._ver_resumen_lote()
    assert not v._planificando
    puertas[101].set()
    esperar_fin(qtbot, v)
    assert not v.formulario.isEnabled()  # sigue bloqueado hasta «Volver al formulario»


def test_lote_completo_termina_con_todas_listas_y_muestra_la_barra_final(qtbot, entorno):
    ejecutar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    assert estados(v) == ["ok", "ok", "ok"]
    p = v.progreso_lote
    assert p.fase == FaseLote.TERMINADO
    assert p.texto_resumen_barra == "3 de 3 terminadas"
    assert p._titulo.text() == "Lote terminado (3 máquinas)"
    assert v.statusBar().currentMessage() == "3 de 3 terminadas"
    assert p.boton_deshacer.isEnabled() and p.boton_informe.isVisible()
    assert v._accion_ultimo_lote.isEnabled()


def test_inv_l1_cada_maquina_se_envia_exactamente_una_vez(qtbot, entorno):
    ejecutar(qtbot, entorno, cantidad=5)
    assert Counter(entorno.creacion.vmids_creados) == {101: 1, 102: 1, 103: 1, 104: 1, 105: 1}


def test_ca_l04_2_todas_comparten_la_plantilla_y_difieren_en_nombre_vmid_y_etiqueta(qtbot, entorno):
    ejecutar(qtbot, entorno, cantidad=3)
    cfgs = sorted(entorno.creacion.cfgs_recibidas, key=lambda c: c.vmid)
    assert [c.nombre for c in cfgs] == ["web-01", "web-02", "web-03"]
    assert [c.vmid for c in cfgs] == [101, 102, 103]
    id_lote = entorno.ventana._lote.plan.id_lote
    for c in cfgs:
        assert c.etiquetas == ("proxlaunch", f"lote-{id_lote}")  # común a todo el lote
    neutras = [dataclasses.replace(c, vmid=0, nombre="").a_dict() for c in cfgs]
    assert neutras[0] == neutras[1] == neutras[2]


def test_ca_l24_5_sin_etiquetar_no_se_envia_ninguna_etiqueta(qtbot, entorno):
    lote_listo(qtbot, entorno, cantidad=2, avanzado=True)
    entorno.ventana.bloque_lote.chk_etiquetar.setChecked(False)
    esperar_validacion(qtbot, entorno.ventana)
    ver_resumen(qtbot, entorno.ventana)
    crear_lote(qtbot, entorno.ventana)
    esperar_fin(qtbot, entorno.ventana)
    assert all(c.etiquetas == () for c in entorno.creacion.cfgs_recibidas)


def test_ca_l10_7_doble_clic_en_crear_inicia_un_solo_lote(qtbot, entorno):
    lote_listo(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    v.resumen_lote.boton_crear.click()
    v.resumen_lote.boton_crear.click()
    esperar_fin(qtbot, v)
    assert entorno.creacion.llamadas_crear == 3
    assert Counter(entorno.creacion.vmids_creados).most_common(1)[0][1] == 1


def test_ca_l10_4_mas_de_diez_pide_doble_confirmacion_con_cancelar_como_alternativa(
    qtbot, entorno, confirmaciones
):
    lote_listo(qtbot, entorno, cantidad=11, prefijo="vm")
    v = entorno.ventana
    confirmaciones.respuesta = False
    crear_lote(qtbot, v)
    assert len(confirmaciones.llamadas) == 1
    titulo, texto, aceptar, cancelar = confirmaciones.llamadas[0]
    assert texto == "Se enviarán 11 máquinas a Proxmox. ¿Continuar?"
    assert (aceptar, cancelar) == ("Crear las máquinas", "Cancelar")
    # Cancelar no envía nada y deja volver a pulsar.
    assert v._lote is None and entorno.creacion.llamadas_crear == 0
    assert v.resumen_lote.boton_crear.isEnabled() and not v._iniciando_lote
    confirmaciones.respuesta = True
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert entorno.creacion.llamadas_crear == 11
    assert len(confirmaciones.llamadas) == 2


def test_ca_l10_4_con_diez_o_menos_no_hay_segunda_confirmacion(qtbot, entorno, confirmaciones):
    lote_listo(qtbot, entorno, cantidad=10, prefijo="vm")
    crear_lote(qtbot, entorno.ventana)
    esperar_fin(qtbot, entorno.ventana)
    assert confirmaciones.llamadas == []


def test_ca_l04_3_editar_la_plantilla_invalida_el_resumen(qtbot, entorno):
    lote_listo(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    assert v.resumen_lote.plan is not None
    escribir(v.bloque_lote.prefijo, "otro")
    assert v._pila_derecha.currentIndex() == 0
    assert v.resumen_lote.plan is None and v._plan_mostrado is None


def test_ca_l04_3_editar_un_campo_del_formulario_tambien_invalida_el_resumen(qtbot, entorno):
    lote_listo(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    v.formulario.cambiado.emit()
    assert v._pila_derecha.currentIndex() == 0 and v.resumen_lote.plan is None


def test_volver_del_resumen_regresa_al_formulario_sin_crear(qtbot, entorno):
    lote_listo(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    v.resumen_lote.boton_volver.click()
    assert v._pila_derecha.currentIndex() == 0 and v.resumen_lote.plan is None
    assert entorno.creacion.llamadas_crear == 0


def test_ca_l07_7_reducir_a_n_baja_la_cantidad_y_regenera_el_resumen(qtbot, entorno):
    # 15 × 32 GiB = 480 supera 3 × 150 GiB del almacenamiento thin: bloquea; caben 14.
    lote_listo(qtbot, entorno, cantidad=15)
    v = entorno.ventana
    r = v.resumen_lote
    assert r.plan.bloqueado and r.plan.capacidad_maxima == 14
    assert r.boton_reducir.isVisible() and r.boton_reducir.text() == "Reducir a 14"
    assert not r.boton_crear.isEnabled()
    r.boton_reducir.click()
    qtbot.waitUntil(lambda: r.plan is not None and len(r.plan.elementos) == 14, timeout=4000)
    assert v.bloque_lote.cantidad.text() == "14"
    assert r._titulo.text() == "Vas a crear 14 máquinas"
    assert not r.plan.bloqueado and r.casilla_thin.isVisible()  # ahora solo pide la casilla
    assert entorno.creacion.llamadas_crear == 0


def test_ca_l09_3_sin_vm_allocate_se_puede_simular_pero_no_crear(qtbot, entorno):
    cliente = ClienteLoteFalso()
    cliente.privilegios_que_faltan = {"VM.Allocate"}
    lote_listo(qtbot, entorno, cantidad=3, cliente=cliente)
    r = entorno.ventana.resumen_lote
    assert not r.boton_crear.isEnabled() and r.boton_simular.isEnabled()
    assert "VM.Allocate" in r._errores.text()


def test_ca_l02_7_un_nombre_existente_avisa_pero_no_bloquea(qtbot, entorno):
    cliente = ClienteLoteFalso()
    cliente.visibles = [VMRemota(105, "web-02", "pve1", "qemu")]
    lote_listo(qtbot, entorno, cantidad=3, cliente=cliente)
    r = entorno.ventana.resumen_lote
    assert "Ya existe una máquina llamada «web-02»" in r._avisos.text()
    assert r.boton_crear.isEnabled()


def test_ca_l03_2_un_vmid_ocupado_se_salta_y_el_resumen_lo_dice(qtbot, entorno):
    cliente = ClienteLoteFalso()
    cliente.vmids_ocupados = {102}
    lote_listo(qtbot, entorno, cantidad=3, cliente=cliente)
    r = entorno.ventana.resumen_lote
    assert [e.vmid for e in r.plan.elementos] == [101, 103, 104]
    assert "102" in r._saltados.text()
    crear_lote(qtbot, entorno.ventana)
    esperar_fin(qtbot, entorno.ventana)
    assert sorted(entorno.creacion.vmids_creados) == [101, 103, 104]


def test_ca_l03_3_un_fallo_de_red_al_reservar_vmids_no_crea_nada_y_lo_dice(qtbot, entorno):
    cliente = ClienteLoteFalso()
    cliente.fallo_vmid_libre = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.5"}
    )
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: not v._planificando, timeout=4000)
    r = v.resumen_lote
    assert r._titulo.text() == "No se pudo preparar el lote"
    assert r._errores.text() == "No se pudo consultar el servidor. No se creó nada."
    assert not r.boton_crear.isEnabled()
    assert entorno.creacion.llamadas_crear == 0 and v._lote is None


def test_sesion_expirada_al_planificar_pide_reconectar(qtbot, entorno, monkeypatch):
    cliente = ClienteLoteFalso()
    cliente.fallo_vmid_libre = ErrorProxLaunch(CodigoError.SESION_EXPIRADA)
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    motivos = []
    monkeypatch.setattr(v, "abrir_conexion", lambda motivo=None: motivos.append(motivo))
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: bool(motivos), timeout=4000)
    assert "sesión expiró" in motivos[0]


def test_ca_l05_reparto_en_un_cluster_muestra_los_nodos_y_el_motivo(qtbot, entorno):
    lote_listo(qtbot, entorno, cantidad=6, nodo=None)
    r = entorno.ventana.resumen_lote
    nodos = {e.nodo for e in r.plan.elementos}
    assert nodos <= {"pve1", "pve3"} and len(nodos) == 2  # el nodo caído no recibe nada
    assert "Equilibrado" in r._reparto.text()
    crear_lote(qtbot, entorno.ventana)
    esperar_fin(qtbot, entorno.ventana)
    assert Counter(c.nodo for c in entorno.creacion.cfgs_recibidas) == Counter(
        e.nodo for e in r.plan.elementos
    )
