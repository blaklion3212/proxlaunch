"""Acciones sobre un lote en la ventana: simulación, plan viejo, deshacer, reintento, informe,
menú «Ver el último lote» y cierre de la aplicación (RF-L11, RF-L18, RF-L19, RF-L21, RF-L23)."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.tema import ModoTema
from proxlaunch.interfaz.ventana_principal import VentanaPrincipal
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.persistencia.preferencias import Modo

from . import test_ventana_principal as _base
from .apoyo import ClienteLoteFalso, CreacionPorVmid, resultado, sesion_falsa, upid_de
from .apoyo_lote import res_error, res_perdida
from .apoyo_ventana_lote import (
    crear_lote,
    esperar_fin,
    estados,
    preparar_lote,
    ver_resumen,
)
from .test_ventana_principal import _textos_avisos, conectar

entorno = _base.entorno
EM = EstadoMV
IP = "10.0.0.5"


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Todas las pruebas de este módulo cierran sin bloquear."""


def fallo(vmid, codigo=CodigoError.SIN_ESPACIO):
    return resultado(
        Desenlace.ERROR,
        error=ErrorProxLaunch(codigo, {}, "texto original"),
        upid=upid_de(vmid),
        vmid=vmid,
    )


def lanzar(qtbot, entorno, *, esperar=True, **kw):
    cliente = preparar_lote(qtbot, entorno, **kw)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    if esperar:
        esperar_fin(qtbot, v)
    return cliente


def existen(cliente, v):
    """Las máquinas del lote existen en el servidor con la etiqueta de este lote."""
    id_lote = v._lote.plan.id_lote
    creadas = (EM.OK, EM.CON_AVISOS, EM.PARCIAL)
    for e in v._lote.libro.instantanea():
        if e.estado not in creadas:
            continue  # las que fallaron no existen en el servidor
        cliente.configs[e.elemento.vmid] = {
            "name": e.elemento.nombre,
            "tags": f"proxlaunch;lote-{id_lote}",
        }


def dialogo(v, tipo):
    cajas = v.findChildren(tipo)
    assert cajas, f"no hay un {tipo.__name__} abierto"
    return cajas[-1]


def fila_rollback(p, i):
    m = p.modelo_rollback
    return [m.data(m.index(i, c)) for c in range(5)]


# --- Simulación (RF-L11) ----------------------------------------------------------------------


def simular(qtbot, v):
    r = v.resumen_lote
    r.boton_simular.click()
    qtbot.waitUntil(lambda: r.es_simulacion and not v._planificando, timeout=4000)


def test_ca_l11_1_simular_solo_lee_no_crea_ni_borra_y_no_deja_libro(qtbot, entorno):
    cliente = preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    r = v.resumen_lote
    assert r._simulacion_etiqueta.text().startswith("SIMULACIÓN — no se creó nada")
    assert cliente.pidio_solo_lectura == 1  # la simulación usa el cliente de solo lectura
    assert (
        entorno.creacion.llamadas_crear == 0 and cliente.creados == [] and cliente.eliminados == []
    )
    assert v._lote is None and not v._accion_ultimo_lote.isEnabled()  # CA-L11.9: sin libro
    assert not any(ll[0] in ("crear_vm", "eliminar_vm") for ll in cliente.llamadas)


def test_ca_l11_2_la_simulacion_muestra_el_cuerpo_de_cada_post_en_detalles_tecnicos(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    texto = v.resumen_lote.detalles_peticiones.texto
    assert texto.count("POST /nodes/pve1/qemu") == 3
    for nombre in ("web-01", "web-02", "web-03"):
        assert f"name = {nombre}" in texto
    assert "Authorization" not in texto and "csrf" not in texto.lower()


def test_ca_l11_3_y_l11_5_crear_de_verdad_tras_simular_replanifica_y_crea_lo_mismo(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    real = [(e.nombre, e.vmid, e.nodo) for e in v.resumen_lote.plan.elementos]
    simular(qtbot, v)
    simulado = [(e.nombre, e.vmid, e.nodo) for e in v.resumen_lote.plan.elementos]
    assert simulado == real  # un solo camino de código para ambos
    r = v.resumen_lote
    assert r.boton_crear.text() == "Crear de verdad estas 3 máquinas" and r.boton_crear.isEnabled()
    r.boton_crear.click()
    esperar_fin(qtbot, v)
    creadas = sorted((c.nombre, c.vmid, c.nodo) for c in entorno.creacion.cfgs_recibidas)
    assert creadas == sorted(real)


def test_ca_l11_6_con_version_forzada_menor_se_etiqueta_y_crear_sigue_permitido(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=3, version=(8, 0), forzada=True)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    assert v.resumen_lote.boton_crear.isEnabled()  # forzada ≤ detectada: más estricta, permitida
    simular(qtbot, v)
    assert "Simulado con compatibilidad de Proxmox 8.0 (el servidor es 9.2)" in (
        v.resumen_lote._simulacion_etiqueta.text()
    )


def test_ca_l11_7_con_version_forzada_mayor_solo_se_puede_simular(qtbot, entorno):
    preparar_lote(qtbot, entorno, cantidad=3, version=(9, 9), forzada=True)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    r = v.resumen_lote
    assert not r.boton_crear.isEnabled() and r.boton_simular.isEnabled()
    assert "Has forzado una versión más nueva que la del servidor (9.2); solo puedes simular." in (
        r._errores.text()
    )
    simular(qtbot, v)
    assert "9.9" in r._simulacion_etiqueta.text()
    assert not r.boton_crear.isEnabled()  # sigue sin poder crear de verdad
    assert entorno.creacion.llamadas_crear == 0


def test_ca_l11_8_la_simulacion_se_puede_exportar_como_informe(qtbot, entorno):
    """CA-L11.8: «La simulación puede exportarse como el informe (RF-L19) con el título
    "Simulación"». Debe haber una acción para ello en el resumen de la simulación."""
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    simular(qtbot, v)
    textos = [b.text().lower() for b in v.resumen_lote.findChildren(QPushButton)]
    assert any("informe" in t or "exportar" in t or "guardar" in t for t in textos), textos


# --- Plan viejo o cambiado (CA-L10.6, E-L11) ----------------------------------------------------


def test_ca_l10_6_un_plan_de_mas_de_cinco_minutos_se_vuelve_a_validar_y_sigue_si_no_cambio(
    qtbot, entorno
):
    cliente = preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    entorno.deps.reloj.avanzar(301)
    antes = len([ll for ll in cliente.llamadas if ll[0] == "vmid_libre"])
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    despues = len([ll for ll in cliente.llamadas if ll[0] == "vmid_libre"])
    assert despues > antes  # se reconsultaron los VMIDs antes de enviar nada (V-L14)
    assert estados(v) == ["ok", "ok", "ok"]


def test_ca_l10_6_si_el_plan_cambia_se_muestra_la_diferencia_y_no_se_envia_nada(qtbot, entorno):
    cliente = preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    entorno.deps.reloj.avanzar(301)
    cliente.vmids_ocupados.add(102)  # otra persona tomó el 102 mientras mirabas el resumen
    antes = v.resumen_lote.plan
    crear_lote(qtbot, v)
    qtbot.waitUntil(
        lambda: v.resumen_lote.plan is not None and v.resumen_lote.plan is not antes, timeout=4000
    )
    r = v.resumen_lote
    assert entorno.creacion.llamadas_crear == 0 and v._lote is None
    assert "Los datos del servidor cambiaron" in r._avisos.text()
    assert "el número 102 ya no está libre" in r._avisos.text()
    assert [e.vmid for e in r.plan.elementos] == [101, 103, 104]
    assert r.boton_crear.isEnabled() and not v._iniciando_lote  # exige confirmar de nuevo
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert sorted(entorno.creacion.vmids_creados) == [101, 103, 104]


def test_ca_l03_8_un_vmid_ocupado_en_el_envio_falla_solo_esa_maquina(qtbot, entorno):
    creacion = CreacionPorVmid({102: res_error(102, CodigoError.VMID_OCUPADO, con_upid=False)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    assert estados(v) == ["ok", "error", "ok"]  # el lote sigue y no se reasigna sola
    assert creacion.vmids_creados == [101, 102, 103]
    assert v.progreso_lote.boton_reintentar.isVisible()


# --- Deshacer (RF-L18) ---------------------------------------------------------------------------


def test_ca_l18_3_deshacer_lista_solo_las_elegibles_y_elimina_las_elegidas(qtbot, entorno):
    creacion = CreacionPorVmid({102: fallo(102)})
    cliente = lanzar(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    existen(cliente, v)
    llamadas_antes = len([ll for ll in entorno.llamadas if ll[0] == "descubrir"])
    v.progreso_lote.boton_deshacer.click()
    d = dialogo(v, DialogoDeshacer)
    assert d.lista.count() == 3
    assert [c.entrada.elemento.vmid for c in d.elegidos()] == [101, 103]  # la 102 falló: no
    assert d.boton_eliminar.text() == "Eliminar 2 máquinas"
    assert d.boton_cancelar.isDefault()
    d.boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert sorted(cliente.eliminados) == [101, 103]
    p = v.progreso_lote
    assert p.tabla_rollback.isVisible()
    assert {fila_rollback(p, i)[0] for i in range(2)} == {"✓ Eliminada"}
    # CA-L18.12: se refresca el inventario y la sección «Deshacer» entra en el informe.
    qtbot.waitUntil(
        lambda: len([ll for ll in entorno.llamadas if ll[0] == "descubrir"]) > llamadas_antes,
        timeout=4000,
    )
    informe = v._informe_actual()
    assert {r.vmid for r in informe.rollback} == {101, 103}


def test_ca_l18_deshacer_cancelar_el_dialogo_no_elimina_nada(qtbot, entorno):
    cliente = lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    existen(cliente, v)
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_cancelar.click()
    assert cliente.eliminados == [] and not v._lote.deshaciendo
    assert not any(ll[0] == "eliminar_vm" for ll in cliente.llamadas)


def test_ca_l18_4_una_maquina_encendida_o_protegida_no_se_borra_y_se_explica(qtbot, entorno):
    cliente = lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    existen(cliente, v)
    cliente.estados_vm[102] = {"status": "running"}
    cliente.configs[103]["protection"] = 1
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert cliente.eliminados == [101]
    p = v.progreso_lote
    detalles = " ".join(" ".join(str(c) for c in fila_rollback(p, i)) for i in range(3))
    assert "«web-02» está encendida" in detalles
    assert "«web-03» está protegida o bloqueada" in detalles


def test_ca_l18_4_una_maquina_con_etiqueta_ajena_no_se_borra(qtbot, entorno):
    cliente = lanzar(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    existen(cliente, v)
    cliente.configs[102]["tags"] = "lote-ffffffff"
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert cliente.eliminados == [101]
    assert "no podemos asegurar que la creó este lote" in fila_rollback(v.progreso_lote, 1)[4]


def test_ca_l18_9_un_403_al_borrar_detiene_el_rollback_y_nombra_el_privilegio(qtbot, entorno):
    cliente = lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    existen(cliente, v)
    cliente.eliminar_falla[101] = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE)
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert cliente.eliminados == []  # las demás quedaron intactas
    assert "VM.Allocate" in v.progreso_lote._error.text()
    p = v.progreso_lote
    assert {fila_rollback(p, i)[0] for i in (1, 2)} == {"– No se procesó"}


def test_ca_l18_13_con_una_sola_maquina_tambien_se_ofrece_deshacer(qtbot, entorno):
    from .test_ventana_principal import crear_y_esperar, poner_nombre

    cliente = ClienteLoteFalso()
    entorno.cliente = cliente
    entorno.creacion = CreacionPorVmid()
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente))
    v = entorno.ventana
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert v.progreso.boton_deshacer.isVisible()
    existen(cliente, v)
    v.progreso.boton_deshacer.click()
    d = dialogo(v, DialogoDeshacer)
    assert [c.entrada.elemento.nombre for c in d.elegidos()] == ["srv-web-01"]
    d.boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert cliente.eliminados == [101]
    assert v._pila_derecha.currentIndex() == 2  # el avance se ve en la tabla del lote


# --- Reintentar pendientes (RF-L21) ---------------------------------------------------------------


def lote_con_fallos(qtbot, entorno, **kw):
    creacion = CreacionPorVmid({102: fallo(102), 104: fallo(104, CodigoError.PARAMETRO_INVALIDO)})
    cliente = lanzar(qtbot, entorno, cantidad=5, creacion=creacion, **kw)
    return creacion, cliente


def reintentar(qtbot, v):
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


def test_ca_l21_1_reintentar_arma_un_plan_nuevo_solo_con_lo_que_no_se_creo(qtbot, entorno):
    creacion, cliente = lote_con_fallos(qtbot, entorno)
    v = entorno.ventana
    id_viejo = v._lote.plan.id_lote
    assert v.progreso_lote.boton_reintentar.isVisible()
    reintentar(qtbot, v)
    plan = v.resumen_lote.plan
    # Conserva nombres y VMIDs de las fallidas; nunca incluye las que sí se crearon (CA-L21.2).
    assert [(e.nombre, e.vmid) for e in plan.elementos] == [("web-02", 102), ("web-04", 104)]
    assert plan.id_lote != id_viejo  # lote nuevo con su propio id (CA-L21.4)
    assert (
        v._pila_derecha.currentIndex() == 1
        and v.resumen_lote._titulo.text() == "Vas a crear 2 máquinas"
    )
    assert all(f"lote-{plan.id_lote}" in e.cfg.etiquetas for e in plan.elementos)
    assert v.resumen_lote.combo_nodo_reintento.isVisible()  # permite cambiar el nodo


def test_ca_l21_2_no_se_reintentan_las_dudosas_ni_las_que_existen_sin_confirmar(qtbot, entorno):
    creacion = CreacionPorVmid({102: res_perdida(102), 103: fallo(103)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    from .apoyo_ventana_lote import esperar_pausa

    esperar_pausa(qtbot, v)
    from proxlaunch.interfaz.dialogos.pausa_lote import AccionPausa

    v._lote.dialogo_pausa.botones[AccionPausa.DETENER].click()
    esperar_fin(qtbot, v)
    assert estados(v) == ["ok", "conexion_perdida", "no_enviada"]
    reintentar(qtbot, v)
    assert [e.vmid for e in v.resumen_lote.plan.elementos] == [103]  # solo la no enviada


def test_ca_l21_1_cambiar_el_nodo_lleva_todas_las_maquinas_al_nodo_elegido(qtbot, entorno):
    lote_con_fallos(qtbot, entorno)
    v = entorno.ventana
    reintentar(qtbot, v)
    combo = v.resumen_lote.combo_nodo_reintento
    datos = [combo.itemData(i) for i in range(combo.count())]
    assert datos[0] is None and "pve3" in datos and "pve2" not in datos  # el caído no se ofrece
    viejo = v.resumen_lote.plan
    combo.setCurrentIndex(datos.index("pve3"))
    qtbot.waitUntil(
        lambda: v.resumen_lote.plan is not None and v.resumen_lote.plan is not viejo, timeout=5000
    )
    plan = v.resumen_lote.plan
    assert {e.nodo for e in plan.elementos} == {"pve3"}
    assert {e.cfg.nodo for e in plan.elementos} == {"pve3"}
    assert [e.vmid for e in plan.elementos] == [102, 104]  # mismos números, otro nodo
    assert "pve3" in v.resumen_lote._reparto.text()


def test_ca_l21_1_el_reintento_con_otro_nodo_se_confirma_y_crea_alli(qtbot, entorno):
    creacion, cliente = lote_con_fallos(qtbot, entorno)
    v = entorno.ventana
    reintentar(qtbot, v)
    combo = v.resumen_lote.combo_nodo_reintento
    viejo = v.resumen_lote.plan
    combo.setCurrentIndex(combo.findData("pve3"))
    qtbot.waitUntil(
        lambda: v.resumen_lote.plan is not viejo and v.resumen_lote.plan is not None, timeout=5000
    )
    creacion.por_vmid.clear()  # ahora sí funcionan
    creacion.cfgs_recibidas.clear()
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert sorted((c.vmid, c.nodo) for c in creacion.cfgs_recibidas) == [
        (102, "pve3"),
        (104, "pve3"),
    ]
    assert estados(v) == ["ok", "ok"]


def test_ca_l21_3_un_vmid_ocupado_al_reintentar_bloquea_el_plan_y_no_se_reasigna(qtbot, entorno):
    creacion, cliente = lote_con_fallos(qtbot, entorno)
    v = entorno.ventana
    cliente.vmids_ocupados.add(104)  # otra persona lo tomó entre tanto
    reintentar(qtbot, v)
    r = v.resumen_lote
    assert r.plan.bloqueado and [e.vmid for e in r.plan.elementos] == [102, 104]  # no se reasigna
    assert not r.boton_crear.isEnabled() and "104" in r._errores.text()


def test_ca_l21_4_con_el_resumen_del_reintento_en_pantalla_el_lote_anterior_sigue_accesible(
    qtbot, entorno
):
    creacion, cliente = lote_con_fallos(qtbot, entorno)
    v = entorno.ventana
    existen(cliente, v)
    reintentar(qtbot, v)
    assert v._accion_ultimo_lote.isEnabled()
    v._accion_ultimo_lote.trigger()
    assert v._pila_derecha.currentIndex() == 2 and v.progreso_lote.boton_deshacer.isEnabled()
    v.progreso_lote.boton_deshacer.click()
    assert [c.entrada.elemento.vmid for c in dialogo(v, DialogoDeshacer).elegidos()] == [
        101,
        103,
        105,
    ]


def test_ca_l21_4_tras_crear_el_reintento_las_del_primer_lote_siguen_pudiendose_deshacer(
    qtbot, entorno
):
    """«Es un lote nuevo con su propio id y su propio libro (el rollback del primero sigue
    accesible mientras dure la sesión)»."""
    creacion, cliente = lote_con_fallos(qtbot, entorno)
    v = entorno.ventana
    existen(cliente, v)
    creadas_primer_lote = {101, 103, 105}
    reintentar(qtbot, v)
    creacion.por_vmid.clear()
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    v.progreso_lote.boton_deshacer.click()
    vmids = {c.entrada.elemento.vmid for c in dialogo(v, DialogoDeshacer).elegidos()}
    assert creadas_primer_lote <= vmids, vmids


# --- Informe (RF-L19) -----------------------------------------------------------------------------


def test_ca_l19_1_el_informe_del_lote_se_abre_con_el_resumen_y_la_tabla(qtbot, entorno):
    creacion = CreacionPorVmid({102: fallo(102)})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    v.progreso_lote.boton_informe.click()
    d = dialogo(v, DialogoInforme)
    t = d.texto
    assert "Perfil: Laboratorio" in t and "Pedidas: 3" in t
    assert "Creadas: 2" in t and "Con error: 1" in t
    assert "web-02" in t and "✕ Con error" in t


def test_ca_l19_3_el_informe_de_la_ventana_no_trae_host_ip_usuario_ni_el_usuario_del_upid(
    qtbot, entorno
):
    lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    v.progreso_lote.boton_informe.click()
    t = dialogo(v, DialogoInforme).texto
    for prohibido in (IP, "ana@pve!lab", "root@pam", "pveproxy"):
        assert prohibido not in t, prohibido
    assert "qmcreate:101:…:" in t


def test_ca_l19_3_un_error_de_red_del_lote_no_filtra_la_ip_ni_el_usuario_al_informe(qtbot, entorno):
    """El error de una máquina lleva el host entre sus parámetros y en el texto técnico de
    ``requests``; el informe se comparte, así que no puede repetirlos."""
    creacion = CreacionPorVmid(
        {
            102: res_error(
                102,
                CodigoError.SERVIDOR_NO_RESPONDE,
                con_upid=False,
                detalle=(
                    f"HTTPSConnectionPool(host='{IP}', port=8006): Read timed out. "
                    "usuario ana@pve!lab"
                ),
                host=IP,
                puerto="8006",
            )
        }
    )
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    v.progreso_lote.boton_informe.click()
    t = dialogo(v, DialogoInforme).texto
    assert "web-02" in t  # el error sí aparece en el informe...
    for prohibido in (IP, "ana@pve!lab", "root@pam"):
        assert prohibido not in t, prohibido  # ...pero sin identificar al servidor ni al usuario


def test_ca_l19_8_copiar_desde_la_ventana_da_el_mismo_texto_del_informe(qtbot, entorno):
    lanzar(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    v.progreso_lote.boton_informe.click()
    d = dialogo(v, DialogoInforme)
    d.boton_copiar.click()
    assert QApplication.clipboard().text() == d.texto


def test_el_informe_de_un_lote_cancelado_muestra_las_no_enviadas(qtbot, entorno, confirmaciones):
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    lanzar(qtbot, entorno, cantidad=4, creacion=creacion, esperar=False)
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.progreso_lote.hay_enviadas(), timeout=4000)
    v._cancelar_lote()
    puerta.set()
    esperar_fin(qtbot, v)
    t = v._informe_actual()
    from proxlaunch.interfaz.informe_lote import texto_informe

    texto = texto_informe(t)
    assert "No enviadas: 3" in texto and "Creadas: 1" in texto


# --- Menú «Ver el último lote» y volver (RF-L13, RF-L21) ------------------------------------------


def test_el_menu_ver_el_ultimo_lote_se_habilita_al_terminar_y_se_deshabilita_al_empezar_otro(
    qtbot, entorno
):
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    assert not v._accion_ultimo_lote.isEnabled()
    assert v._accion_ultimo_lote.text() == "Ver el último lote"
    ver_resumen(qtbot, v)
    puerta = threading.Event()
    entorno.creacion.puertas[101] = puerta
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: entorno.creacion.entro(101).is_set(), timeout=4000)
    assert not v._accion_ultimo_lote.isEnabled()  # en curso: no tiene sentido «verlo»
    puerta.set()
    esperar_fin(qtbot, v)
    assert v._accion_ultimo_lote.isEnabled()


def test_volver_al_formulario_desbloquea_y_el_menu_permite_ver_el_lote_otra_vez(qtbot, entorno):
    lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    v.progreso_lote.boton_volver.click()
    assert v._pila_derecha.currentIndex() == 0
    assert v.formulario.isEnabled() and v.bloque_lote.isEnabled()
    v._accion_ultimo_lote.trigger()
    assert v._pila_derecha.currentIndex() == 2 and v.progreso_lote.fase == FaseLote.TERMINADO
    assert not v.formulario.isEnabled()  # mientras se ve el lote el formulario está bloqueado


def test_volver_con_dudosas_pide_confirmar_antes_de_repetir_el_lote(qtbot, entorno, confirmaciones):
    confirmaciones.respuesta = False
    creacion = CreacionPorVmid({101: res_perdida(101)})
    from proxlaunch.interfaz.dialogos.pausa_lote import AccionPausa

    from .apoyo_ventana_lote import esperar_pausa

    lanzar(qtbot, entorno, cantidad=2, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    v._lote.dialogo_pausa.botones[AccionPausa.DETENER].click()
    esperar_fin(qtbot, v)
    v.progreso_lote.boton_volver.click()
    assert confirmaciones.llamadas[-1][0] == "Hay máquinas sin confirmar"
    assert "podrías duplicarlas" in confirmaciones.llamadas[-1][1]
    assert confirmaciones.llamadas[-1][3] == "Quedarme aquí"
    assert v._pila_derecha.currentIndex() == 2  # se queda
    confirmaciones.respuesta = True
    v.progreso_lote.boton_volver.click()
    assert v._pila_derecha.currentIndex() == 0


def test_cambiar_de_tema_y_de_modo_durante_el_lote_no_rompe_nada(qtbot, entorno):
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion, esperar=False)
    v = entorno.ventana
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)
    v.establecer_tema(ModoTema.CLARO)
    v.establecer_modo(Modo.AVANZADO)
    assert not v.formulario.isEnabled()  # el lote sigue bloqueando el formulario
    puerta.set()
    esperar_fin(qtbot, v)
    claro = v.progreso_lote.modelo.data(
        v.progreso_lote.modelo.index(0, 0),
        9,  # ForegroundRole
    )
    assert claro is not None


# --- Cierre de la aplicación (RF-L23) -------------------------------------------------------------


@pytest.fixture
def carpeta_informes(entorno, tmp_path):
    entorno.deps.directorio_informes = tmp_path / "informes"
    return entorno.deps.directorio_informes


def lote_colgado(qtbot, entorno, cantidad=3):
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    lanzar(qtbot, entorno, cantidad=cantidad, creacion=creacion, esperar=False)
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)
    qtbot.waitUntil(lambda: entorno.ventana.progreso_lote.hay_enviadas(), timeout=2000)
    return creacion, puerta


def test_ca_l23_1_cerrar_con_un_lote_en_curso_pregunta_con_seguir_como_opcion_segura(
    qtbot, entorno, confirmaciones, carpeta_informes
):
    confirmaciones.respuesta = False
    lote_colgado(qtbot, entorno)
    v = entorno.ventana
    assert v.close() is False and v.isVisible()
    titulo, texto, aceptar, cancelar = confirmaciones.llamadas[-1]
    assert texto == (
        "Hay un lote en curso (0 de 3 terminadas). Si cierras, las tareas ya enviadas seguirán "
        "en Proxmox, pero ProxLaunch no enviará el resto ni podrá deshacer lo creado."
    )
    assert (aceptar, cancelar) == ("Cerrar de todos modos", "Seguir en ProxLaunch")
    assert not carpeta_informes.exists()  # al seguir no se guarda nada
    assert not v._lote.control.cancelado.is_set()


def test_ca_l23_2_cerrar_de_todos_modos_cancela_guarda_el_informe_parcial_y_cierra_la_sesion(
    qtbot, entorno, confirmaciones, carpeta_informes, servicio_falso
):
    creacion, puerta = lote_colgado(qtbot, entorno)
    v = entorno.ventana
    sesion = v._sesion
    id_lote = v._lote.plan.id_lote
    assert v.close() is True
    assert ("cerrar_sesion", sesion) in servicio_falso.llamadas
    parcial = carpeta_informes / f"parcial-{id_lote}.txt"
    assert parcial.is_file()
    texto = parcial.read_text(encoding="utf-8")
    assert f"Informe del lote {id_lote}" in texto and "Cómo encontrar estas máquinas" in texto
    assert IP not in texto and "ana@pve!lab" not in texto
    assert (carpeta_informes / "ultimo-informe-parcial.txt").is_file()


def test_ca_l23_3_el_siguiente_arranque_avisa_con_la_ruta_del_informe(
    qtbot, entorno, confirmaciones, carpeta_informes
):
    lote_colgado(qtbot, entorno)
    v = entorno.ventana
    id_lote = v._lote.plan.id_lote
    v.close()
    v2 = VentanaPrincipal(entorno.deps)
    qtbot.addWidget(v2)
    conectar(qtbot, SimpleNamespace(ventana=v2), sesion_falsa(cliente=ClienteLoteFalso()))
    ruta = carpeta_informes / f"parcial-{id_lote}.txt"
    avisos = _textos_avisos(v2)
    assert f"El último lote se cerró sin terminar. Informe: {ruta}" in avisos
    # Solo se avisa una vez: un tercer arranque ya no lo menciona y no se restaura el libro.
    v3 = VentanaPrincipal(entorno.deps)
    qtbot.addWidget(v3)
    assert v3._aviso_informe_parcial is None and v3._lote is None


def test_ca_l23_cerrar_sin_lote_en_curso_no_pregunta(qtbot, entorno, confirmaciones):
    lanzar(qtbot, entorno, cantidad=2)
    assert entorno.ventana.close() is True
    assert confirmaciones.llamadas == []


def test_ca_l23_1_cerrar_durante_un_rollback_tambien_pregunta_y_lo_cancela(
    qtbot, entorno, confirmaciones, carpeta_informes
):
    cliente = lanzar(qtbot, entorno, cantidad=2)
    v = entorno.ventana
    existen(cliente, v)
    cliente.puerta_eliminar = threading.Event()
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    qtbot.waitUntil(lambda: any(ll[0] == "eliminar_vm" for ll in cliente.llamadas), timeout=4000)
    assert v._lote.deshaciendo

    def responder(parent, titulo, texto, aceptar, cancelar):
        confirmaciones.llamadas.append((titulo, texto, aceptar, cancelar))
        cliente.puerta_eliminar.set()  # que el DELETE retenido termine al cerrar
        return True

    vp.confirmar = responder  # restaurado por el monkeypatch de ``confirmaciones``
    assert v.close() is True
    assert "Hay un lote en curso" in confirmaciones.llamadas[-1][1]
    assert v._lote.control_rollback.cancelado.is_set()


# --- Complementos de la matriz (RF-L09, RF-L11, RF-L14, RF-L15, RF-L16, RF-L18, RF-L24) -----------


def test_ca_l09_4_si_no_se_pueden_leer_los_permisos_no_se_bloquea_y_el_informe_lo_dice(
    qtbot, entorno
):
    cliente = ClienteLoteFalso()
    cliente.fallo_permisos = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    lanzar(qtbot, entorno, cantidad=2, cliente=cliente)
    v = entorno.ventana
    assert v._lote.plan.bloqueado is False and estados(v) == ["ok", "ok"]  # no se bloqueó
    from proxlaunch.interfaz.informe_lote import texto_informe

    assert "permisos no verificados" in texto_informe(v._informe_actual()).lower()


def test_ca_l11_10_la_simulacion_se_puede_cancelar_mientras_consulta_al_servidor(qtbot, entorno):
    from .test_lote_robustez import ClienteLento

    cliente = ClienteLento()
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    try:
        assert cliente.entro.wait(5)
        assert v._planificando
        v.resumen_lote.boton_volver.click()  # el usuario se arrepiente mientras se prepara
        assert v._pila_derecha.currentIndex() == 0, "no hay forma de cancelar la preparación"
    finally:
        cliente.liberar.set()


def test_ca_l14_7_un_error_de_validacion_no_previsto_falla_solo_esa_maquina(qtbot, entorno):
    creacion = CreacionPorVmid(
        {102: res_error(102, CodigoError.RECURSO_INEXISTENTE, con_upid=False, recurso="vmbr9")}
    )
    lanzar(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    assert estados(v) == ["ok", "error", "ok"]
    p = v.progreso_lote
    assert p.modelo.data(p.modelo.index(1, 4))  # lleva su mensaje llano


def test_ca_l05_10_las_maquinas_de_un_nodo_caido_quedan_sin_enviar_y_se_ofrece_reintentar(
    qtbot, entorno
):
    def regla(cfg):
        if cfg.nodo == "pve3":
            return res_error(
                cfg.vmid, CodigoError.NODO_NO_DISPONIBLE, con_upid=False, nodo=cfg.nodo
            )
        return None

    creacion = CreacionPorVmid({vm: regla for vm in range(101, 107)})
    lanzar(qtbot, entorno, cantidad=6, nodo=None, creacion=creacion)
    v = entorno.ventana
    sin_enviar = [e for e in v._lote.libro.instantanea() if e.estado == EM.NO_ENVIADA]
    assert len(sin_enviar) >= 1 and all(e.elemento.nodo == "pve3" for e in sin_enviar)
    assert v.progreso_lote.boton_reintentar.isVisible()
    p = v.progreso_lote
    detalles = [p.modelo.data(p.modelo.index(e.elemento.indice, 4)) for e in sin_enviar]
    assert all("no se envió (el nodo no respondió)" in d for d in detalles)


def test_ca_l15_6_una_dudosa_de_un_lote_ofrece_comprobar_por_maquina_ademas_del_global(
    qtbot, entorno
):
    from proxlaunch.interfaz.dialogos.pausa_lote import AccionPausa

    from .apoyo_ventana_lote import esperar_pausa

    creacion = CreacionPorVmid({101: res_perdida(101)})
    lanzar(qtbot, entorno, cantidad=2, creacion=creacion, esperar=False)
    v = entorno.ventana
    esperar_pausa(qtbot, v)
    v._lote.dialogo_pausa.botones[AccionPausa.DETENER].click()
    esperar_fin(qtbot, v)
    p = v.progreso_lote
    p.tabla.selectRow(0)
    assert "No sabemos si se creó" in p.modelo.data(p.modelo.index(0, 0))
    por_maquina = [
        b
        for b in p.findChildren(QPushButton)
        if b is not p.boton_comprobar and b.isVisible() and "comprobar" in b.text().lower()
    ]
    assert por_maquina, "falta el botón «Comprobar ahora» por máquina (solo hay el global)"


def test_ca_l16_5_cancelar_tras_el_ultimo_envio_no_cambia_nada(qtbot, entorno, confirmaciones):
    lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    antes = estados(v)
    v._cancelar_lote()
    assert confirmaciones.llamadas == [] and estados(v) == antes
    assert v.progreso_lote.fase == FaseLote.TERMINADO


def test_ca_l18_8_un_fallo_al_eliminar_una_no_detiene_las_demas_y_el_informe_lo_lista(
    qtbot, entorno
):
    cliente = lanzar(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    existen(cliente, v)
    cliente.eliminar_falla[102] = ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom")
    v.progreso_lote.boton_deshacer.click()
    dialogo(v, DialogoDeshacer).boton_eliminar.click()
    esperar_fin(qtbot, v)
    assert sorted(cliente.eliminados) == [101, 103]
    from proxlaunch.interfaz.informe_lote import texto_informe

    informe = texto_informe(v._informe_actual())
    seccion = informe[informe.index("\nDeshacer\n") :]
    assert "web-02" in seccion and "No se pudo eliminar" in seccion


def test_ca_l24_5_acerca_de_dice_que_las_maquinas_creadas_llevan_la_etiqueta(qtbot):
    from PySide6.QtWidgets import QLabel

    from proxlaunch.interfaz.dialogos.acerca_de import DialogoAcercaDe

    d = DialogoAcercaDe("oscuro")
    qtbot.addWidget(d)
    texto = " ".join(w.text() for w in d.findChildren(QLabel))
    assert "etiqueta «proxlaunch»" in texto


def test_ca_l04_5_la_tabla_del_plan_es_de_solo_lectura(qtbot, entorno):
    from PySide6.QtWidgets import QAbstractItemView

    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    assert v.resumen_lote.tabla.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
