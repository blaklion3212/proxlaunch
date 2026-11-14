"""Pantalla de resumen del lote y de su simulación (RF-L10, RF-L11, RF-L07/L08, CA-L03.2).

Los planes salen del ``Planificador`` real del núcleo sobre un cliente falso (sin red).
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QWidget

from proxlaunch.interfaz.informe_lote import texto_rangos
from proxlaunch.interfaz.modelos_tabla import ModeloPlan
from proxlaunch.interfaz.vistas.resumen_lote import (
    ResumenLote,
    texto_boton_crear,
    texto_boton_reducir,
    texto_peticiones,
)
from proxlaunch.nucleo.lote.modelos import Destino, ModoDestino
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.inventario import VMRemota
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo import ClienteLoteFalso, sesion_falsa
from .apoyo_lote import cfg_simple, definicion, planificar


@pytest.fixture
def resumen(qtbot):
    r = ResumenLote()
    qtbot.addWidget(r)
    r.show()
    return r


def plan_de(inv, n=3, *, cliente=None, gib=10, storage="local-lvm", **kw):
    cfg = cfg_simple(gib=gib)
    cfg.discos[0].storage = storage
    return planificar(inv, definicion(n, plantilla=cfg), cliente, **kw)


def simulacion_de(inv, n=3, cliente=None, **kw):
    sesion = sesion_falsa(cliente=cliente or ClienteLoteFalso(), **kw)
    # Igual que la ventana: la versión solo viaja si el usuario la forzó.
    forzada = sesion.capacidades.version if sesion.capacidades.forzada else None
    return simular(sesion, definicion(n), inv, version_forzada=forzada, reloj=RelojSimulado())


# --- Contenido (CA-L10.1) -----------------------------------------------------------------


def test_ca_l10_1_titulo_tabla_totales_y_reparto_con_motivo(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    assert resumen._titulo.text() == "Vas a crear 3 máquinas"
    assert resumen.modelo.rowCount() == 3
    cab = [resumen.modelo.headerData(c, Qt.Orientation.Horizontal) for c in range(6)]
    assert cab == ["N.º", "Nombre", "VMID", "Nodo", "Almacenamiento", "Discos (GiB)"]
    fila = [resumen.modelo.data(resumen.modelo.index(0, c)) for c in range(6)]
    assert fila == ["1", "web-01", "101", "pve1", "local-lvm", "10"]
    texto = resumen._totales.text()
    assert "3 máquinas" in texto and "6 procesadores virtuales" in texto
    assert "6 GiB de memoria" in texto
    assert "«local-lvm» en pve1: 30 GiB de 150 GiB libres" in texto
    assert "pve1: 3 máquinas (" in resumen._reparto.text()


def test_ca_l05_9_el_reparto_explica_por_que_cada_nodo(resumen, inv_cluster):
    plan = planificar(
        inv_cluster, definicion(6, destino=Destino(ModoDestino.AUTOMATICO), plantilla=cfg_simple())
    )
    resumen.mostrar_plan(plan)
    reparto = resumen._reparto.text()
    assert "pve1:" in reparto and "pve3:" in reparto
    assert "Equilibrado: más memoria libre" in reparto
    assert "pve2" not in reparto  # el nodo caído no recibe nada


def test_un_solo_nodo_explica_el_motivo(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 2))
    assert "(" in resumen._reparto.text() and ")" in resumen._reparto.text()


def test_ca_l03_2_vmids_saltados_se_muestran_en_el_resumen(resumen, inv_cluster):
    cliente = ClienteLoteFalso()
    cliente.vmids_ocupados = {102}
    plan = plan_de(inv_cluster, 3, cliente=cliente)
    assert [e.vmid for e in plan.elementos] == [101, 103, 104]
    resumen.mostrar_plan(plan)
    assert resumen._saltados.isVisible()
    assert (
        "102" in resumen._saltados.text() and "ya los usa otra máquina" in resumen._saltados.text()
    )


def test_sin_vmids_saltados_no_se_muestra_la_linea(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    assert not resumen._saltados.isVisible()


def test_ca_l03_9_los_vmids_se_agrupan_en_rangos():
    assert texto_rangos([100, 101, 102, 103, 104, 106, 107, 108, 109, 110]) == "100–104, 106–110"
    assert texto_rangos([5]) == "5"
    assert texto_rangos([]) == ""
    assert texto_rangos([3, 1, 2, 2]) == "1–3"


def test_ca_l03_9_varios_vmids_saltados_salen_agrupados(resumen, inv_cluster):
    cliente = ClienteLoteFalso()
    cliente.vmids_ocupados = {102, 103, 105}
    resumen.mostrar_plan(plan_de(inv_cluster, 3, cliente=cliente))
    assert "102–103, 105" in resumen._saltados.text()


# --- Errores, avisos y botones (CA-L10.2, CA-L10.3) ------------------------------------------


def test_ca_l10_2_con_un_error_bloqueante_crear_se_deshabilita_y_simular_sigue_activo(
    resumen, inv_cluster
):
    plan = plan_de(inv_cluster, 3, gib=20, storage="local")  # 60 GiB en un dir de 50
    assert plan.bloqueado
    resumen.mostrar_plan(plan)
    assert not resumen.boton_crear.isEnabled()
    assert resumen.boton_simular.isEnabled()
    assert "✕" in resumen._errores.text() and "«local»" in resumen._errores.text()
    assert resumen._motivo.isVisible()  # explica por qué no se puede crear


def test_ca_l07_1_el_mensaje_de_espacio_dice_cuanto_hace_falta_y_cuanto_hay(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3, gib=20, storage="local"))
    texto = resumen._errores.text()
    assert "Las 3 máquinas necesitan 60 GiB" in texto and "solo hay 50 GiB libres" in texto


def test_ca_l07_7_reducir_a_n_aparece_con_la_capacidad_y_emite_el_numero(
    qtbot, resumen, inv_cluster
):
    plan = plan_de(inv_cluster, 3, gib=20, storage="local")  # caben 2
    assert plan.capacidad_maxima == 2
    resumen.mostrar_plan(plan)
    assert resumen.boton_reducir.isVisible()
    assert resumen.boton_reducir.text() == "Reducir a 2"
    with qtbot.waitSignal(resumen.reducir_solicitado, timeout=1000) as senal:
        resumen.boton_reducir.click()
    assert senal.args == [2]


def test_ca_l07_7_si_no_cabe_ni_una_no_se_ofrece_reducir(resumen, inv_cluster):
    plan = plan_de(inv_cluster, 2, gib=60, storage="local")  # ni una de 60 GiB en 50
    assert plan.bloqueado and not plan.capacidad_maxima
    resumen.mostrar_plan(plan)
    assert not resumen.boton_reducir.isVisible()


def test_sin_error_de_espacio_no_hay_boton_reducir(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    assert not resumen.boton_reducir.isVisible()


def test_texto_del_boton_reducir_con_plural():
    assert texto_boton_reducir(1) == "Reducir a 1"
    assert texto_boton_reducir(5) == "Reducir a 5"


def test_ca_l10_3_un_aviso_no_bloqueante_deja_crear_activo_y_se_ve_antes_del_boton(
    qtbot, resumen, inv_cluster
):
    cliente = ClienteLoteFalso()
    cliente.visibles = [VMRemota(105, "web-01", "pve1", "qemu")]
    resumen.resize(700, 900)
    resumen.mostrar_plan(plan_de(inv_cluster, 3, cliente=cliente))
    QApplication.processEvents()
    assert resumen.boton_crear.isEnabled()
    assert resumen._avisos.isVisible()
    assert "Ya existe una máquina llamada «web-01»" in resumen._avisos.text()
    assert "105" in resumen._avisos.text()
    # El aviso del nombre se califica: puede haber otras que el usuario no ve (CA-L02.7).
    assert "no puedes ver" in resumen._nota_nombres.text()
    y_aviso = resumen._avisos.mapTo(resumen, QPoint(0, 0)).y()
    y_boton = resumen.boton_crear.mapTo(resumen, QPoint(0, 0)).y()
    assert y_aviso < y_boton


def test_los_avisos_del_plan_no_se_pueden_ocultar(resumen, inv_cluster):
    """CA-L10.3: sin control para ocultarlos; solo cambian con un plan nuevo."""
    cliente = ClienteLoteFalso()
    cliente.visibles = [VMRemota(105, "web-01", "pve1", "qemu")]
    resumen.mostrar_plan(plan_de(inv_cluster, 3, cliente=cliente))
    ocultadores = [
        b for b in resumen.findChildren(QWidget) if b.objectName() in ("ocultar", "cerrar_aviso")
    ]
    assert ocultadores == []


def test_aviso_de_memoria_del_nodo_no_bloquea(resumen, inv_cluster):
    cfg = cfg_simple(memoria_mib=6144)
    plan = planificar(inv_cluster, definicion(3, plantilla=cfg))  # 18 GiB > 8 GiB de pve1
    resumen.mostrar_plan(plan)
    assert not plan.bloqueado and resumen.boton_crear.isEnabled()
    assert "En «pve1» pides 18 GiB de memoria y hay 8 GiB libres" in resumen._avisos.text()
    assert "apagadas" in resumen._avisos.text()


# --- Sobreasignación thin (RF-L08) ---------------------------------------------------------


def test_ca_l08_1_thin_dentro_del_libre_no_avisa_ni_pide_casilla(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3, gib=40))  # 120 ≤ 150
    assert not resumen.casilla_thin.isVisible()
    assert resumen.boton_crear.isEnabled()


def test_ca_l08_2_thin_sobreasignado_exige_la_casilla_para_habilitar_crear(resumen, inv_cluster):
    plan = plan_de(inv_cluster, 3, gib=60)  # 180 GiB en un thin de 150
    assert plan.requiere_confirmacion_thin and not plan.bloqueado
    resumen.mostrar_plan(plan)
    assert resumen.casilla_thin.isVisible()
    assert resumen.casilla_thin.text() == "Entiendo el riesgo de sobreasignar espacio"
    assert not resumen.boton_crear.isEnabled()
    assert "casilla" in resumen._motivo.text()
    assert "pidiendo 180 GiB y solo hay 150 GiB libres" in resumen._avisos.text()
    resumen.casilla_thin.setChecked(True)
    assert resumen.boton_crear.isEnabled()
    resumen.casilla_thin.setChecked(False)
    assert not resumen.boton_crear.isEnabled()


def test_ca_l08_3_mas_de_tres_veces_lo_libre_bloquea_aunque_se_marque_la_casilla(
    resumen, inv_cluster
):
    plan = plan_de(inv_cluster, 8, gib=60)  # 480 > 3 × 150
    assert plan.bloqueado
    resumen.mostrar_plan(plan)
    resumen.casilla_thin.setChecked(True)
    assert not resumen.boton_crear.isEnabled()
    assert "más de 3 veces" in resumen._errores.text()


def test_ca_l08_6_la_casilla_no_se_recuerda_entre_planes(resumen, inv_cluster):
    plan = plan_de(inv_cluster, 3, gib=60)
    resumen.mostrar_plan(plan)
    resumen.casilla_thin.setChecked(True)
    resumen.mostrar_plan(plan)
    assert not resumen.casilla_thin.isChecked()
    assert not resumen.boton_crear.isEnabled()


def test_ca_l08_5_el_texto_thin_explica_sin_jerga(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3, gib=60))
    texto = resumen._avisos.text().lower()
    assert "thin" not in texto and "funciona mientras las máquinas no usen todo su disco" in texto


# --- Crear: un solo clic efectivo (CA-L10.7) y vigencia ---------------------------------------


def test_ca_l10_7_doble_clic_en_crear_emite_una_sola_solicitud(qtbot, resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    pedidos = []
    resumen.crear_solicitado.connect(lambda: pedidos.append(1))
    resumen.boton_crear.click()
    resumen.boton_crear.click()
    assert pedidos == [1]
    assert not resumen.boton_crear.isEnabled()


def test_liberar_permite_volver_a_pulsar_crear(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    resumen.boton_crear.click()
    resumen.liberar()
    assert resumen.boton_crear.isEnabled()


def test_sin_plan_no_hay_acciones(resumen):
    resumen.mostrar_vacio()
    assert not resumen.boton_crear.isEnabled() and not resumen.boton_simular.isEnabled()
    assert resumen.plan is None


def test_mientras_se_planifica_no_se_puede_crear_ni_simular(resumen):
    resumen.mostrar_planificando()
    assert "Preparando el resumen" in resumen._titulo.text()
    assert not resumen.boton_crear.isEnabled() and not resumen.boton_simular.isEnabled()


def test_ca_l09_3_sin_vm_allocate_crear_muestra_el_motivo_y_simular_sigue_disponible(
    resumen, inv_cluster
):
    cliente = ClienteLoteFalso()
    cliente.privilegios_que_faltan = {"VM.Allocate"}
    resumen.mostrar_plan(plan_de(inv_cluster, 3, cliente=cliente))
    assert not resumen.boton_crear.isEnabled() and resumen.boton_simular.isEnabled()
    assert "VM.Allocate" in resumen._errores.text()


def test_el_bloqueo_de_permisos_externo_deshabilita_crear_con_su_motivo(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3), bloqueo_crear="Falta el permiso X")
    assert not resumen.boton_crear.isEnabled()
    assert resumen._motivo.text() == "Falta el permiso X"
    assert resumen.boton_simular.isEnabled()


def test_ca_l10_6_una_diferencia_se_muestra_y_exige_confirmar_de_nuevo(resumen, inv_cluster):
    resumen.mostrar_plan(
        plan_de(inv_cluster, 3), diferencia="el número 102 ya no está libre (ahora se usa el 104)"
    )
    assert "Los datos del servidor cambiaron" in resumen._avisos.text()
    assert "el número 102 ya no está libre" in resumen._avisos.text()
    assert resumen.boton_crear.isEnabled()  # el usuario puede revisar y confirmar otra vez


def test_error_de_red_al_planificar_no_crea_nada_y_lo_dice(resumen):
    from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

    resumen.mostrar_error(ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.5"}))
    assert resumen._titulo.text() == "No se pudo preparar el lote"
    assert resumen._errores.text() == "No se pudo consultar el servidor. No se creó nada."
    assert "10.0.0.5" not in resumen._errores.text()
    assert not resumen.boton_crear.isEnabled()


# --- Tabla con modelo y copia (CA-L10.5, CA-L10.8) --------------------------------------------


def test_ca_l10_5_cien_filas_son_un_modelo_no_cien_widgets(resumen, inv_cluster):
    cfg = cfg_simple(con_disco=False, discos=[])
    plan = planificar(inv_cluster, definicion(100, plantilla=cfg))
    resumen.mostrar_plan(plan)
    assert isinstance(resumen.tabla.model(), ModeloPlan)
    assert resumen.modelo.rowCount() == 100
    assert (
        len(resumen.tabla.findChildren(QWidget, options=Qt.FindChildOption.FindChildrenRecursively))
        < 20
    )


def test_ca_l10_5_la_tabla_se_copia_como_texto_con_cabecera(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    resumen.tabla.selectAll()
    resumen.tabla.copiar()
    texto = QApplication.clipboard().text()
    lineas = texto.splitlines()
    assert lineas[0].split("\t")[:3] == ["N.º", "Nombre", "VMID"]
    assert len(lineas) == 4 and lineas[1].split("\t")[1] == "web-01"


def test_ca_l10_5_ctrl_c_copia_la_tabla(qtbot, resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 2))
    resumen.tabla.selectAll()
    qtbot.keyClick(resumen.tabla, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert "web-02" in QApplication.clipboard().text()


def test_ca_l10_5_la_tabla_se_recorre_con_el_teclado(qtbot, resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    resumen.tabla.setFocus()
    resumen.tabla.setCurrentIndex(resumen.modelo.index(0, 0))
    qtbot.keyClick(resumen.tabla, Qt.Key.Key_Down)
    qtbot.keyClick(resumen.tabla, Qt.Key.Key_Down)
    assert resumen.tabla.currentIndex().row() == 2


def test_ca_l10_8_copiar_resumen_pone_el_texto_en_el_portapapeles(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    resumen.boton_copiar.click()
    copiado = QApplication.clipboard().text()
    assert copiado == resumen.texto_resumen()
    for esperado in ("Vas a crear 3 máquinas", "web-03", "Totales:", "Reparto:"):
        assert esperado in copiado


def test_ca_l10_8_el_resumen_no_contiene_secretos_ni_el_host(resumen, inv_cluster):
    resumen.mostrar_plan(plan_de(inv_cluster, 3))
    texto = resumen.texto_resumen()
    for prohibido in ("10.0.0.5", "ana@pve", "PVEAPIToken", "ticket", "csrf"):
        assert prohibido.lower() not in texto.lower()


# --- Simulación (RF-L11) --------------------------------------------------------------------


def test_ca_l11_2_la_simulacion_se_etiqueta_y_muestra_cada_peticion(resumen, inv_cluster):
    sim = simulacion_de(inv_cluster, 3)
    resumen.mostrar_plan(sim.plan, simulacion=sim)
    assert resumen.es_simulacion
    assert resumen._simulacion_etiqueta.isVisible()
    assert resumen._simulacion_etiqueta.text().startswith("SIMULACIÓN — no se creó nada")
    texto = resumen.detalles_peticiones.texto
    for vmid in (101, 102, 103):
        assert f"VMID {vmid}" in texto
    assert texto.count("POST /nodes/pve1/qemu") == 3
    assert "name = web-01" in texto and "vmid = 101" in texto
    assert "tags = proxlaunch;lote-" in texto  # la etiqueta del lote va en la petición


def test_ca_l11_2_las_peticiones_no_llevan_cabeceras_ni_secretos():
    sim = simulacion_de_global()
    texto = texto_peticiones(sim)
    for prohibido in ("Authorization", "PVEAPIToken", "CSRF", "Cookie", "ticket", "password"):
        assert prohibido.lower() not in texto.lower()


def simulacion_de_global():
    from .apoyo import inventario_cluster

    return simulacion_de(inventario_cluster(), 2)


def test_ca_l11_5_tras_simular_el_boton_dice_crear_de_verdad(resumen, inv_cluster):
    sim = simulacion_de(inv_cluster, 3)
    resumen.mostrar_plan(sim.plan, simulacion=sim)
    assert resumen.boton_crear.text() == "Crear de verdad estas 3 máquinas"
    assert resumen.boton_crear.isEnabled()
    assert texto_boton_crear(1, simulado=True) == "Crear de verdad esta máquina"


def test_ca_l11_6_con_version_forzada_se_etiqueta_la_compatibilidad(resumen, inv_cluster):
    sim = simulacion_de(inv_cluster, 2, version=(8, 0), forzada=True)
    resumen.mostrar_plan(sim.plan, simulacion=sim)
    etiqueta = resumen._simulacion_etiqueta.text()
    assert "Simulado con compatibilidad de Proxmox 8.0 (el servidor es 9.2)" in etiqueta


def test_ca_l11_6_sin_version_forzada_no_hay_nota_de_compatibilidad(resumen, inv_cluster):
    sim = simulacion_de(inv_cluster, 2)
    resumen.mostrar_plan(sim.plan, simulacion=sim)
    assert "compatibilidad" not in resumen._simulacion_etiqueta.text()


def test_ca_l11_7_version_forzada_mayor_bloquea_crear_pero_no_simular(resumen, inv_cluster):
    plan = plan_de(inv_cluster, 3, version_forzada=(9, 9))
    assert plan.bloqueado
    resumen.mostrar_plan(plan)
    assert not resumen.boton_crear.isEnabled()
    assert resumen.boton_simular.isEnabled()
    assert "solo puedes simular" in resumen._errores.text()


def test_ca_l11_1_la_simulacion_solo_toco_el_cliente_de_solo_lectura(inv_cluster):
    cliente = ClienteLoteFalso()
    simulacion_de(inv_cluster, 3, cliente=cliente)
    assert cliente.pidio_solo_lectura == 1
    escrituras = {"eliminar_vm"}
    assert not [ll for ll in cliente.llamadas if ll[0] in escrituras]


def test_una_simulacion_tambien_pasa_por_la_copia_del_resumen(resumen, inv_cluster):
    sim = simulacion_de(inv_cluster, 3)
    resumen.mostrar_plan(sim.plan, simulacion=sim)
    assert "SIMULACIÓN — no se creó nada" in resumen.texto_resumen()


# --- Reintento: selector de nodo (RF-L21) ---------------------------------------------------


def test_ca_l21_1_el_selector_de_nodo_ofrece_los_mismos_nodos_y_los_demas(qtbot, resumen):
    resumen.mostrar_selector_nodo(["pve1", "pve3"], None)
    assert resumen.combo_nodo_reintento.isVisible()
    datos = [
        resumen.combo_nodo_reintento.itemData(i)
        for i in range(resumen.combo_nodo_reintento.count())
    ]
    assert datos == [None, "pve1", "pve3"]
    assert "mismos nodos" in resumen.combo_nodo_reintento.itemText(0)


def test_ca_l21_1_elegir_otro_nodo_emite_el_cambio(qtbot, resumen):
    resumen.mostrar_selector_nodo(["pve1", "pve3"], None)
    with qtbot.waitSignal(resumen.nodo_reintento_cambiado, timeout=1000) as senal:
        resumen.combo_nodo_reintento.setCurrentIndex(2)
    assert senal.args == ["pve3"]


def test_ca_l21_1_el_selector_se_oculta_al_limpiar(resumen):
    resumen.mostrar_selector_nodo(["pve1"], None)
    resumen.mostrar_vacio()
    assert not resumen.combo_nodo_reintento.isVisible()


def test_la_dataclass_del_plan_es_inmutable_para_la_interfaz(inv_cluster):
    plan = plan_de(inv_cluster, 2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.id_lote = "x"  # type: ignore[misc]


# --- Elegibilidad, memoria y CPU en el resumen (RF-L05, RF-L06, RF-L09) -------------------------


def test_ca_l06_3_con_un_nodo_sin_el_storage_de_la_plantilla_se_bloquea_con_v_17(
    resumen, inv_cluster
):
    cfg = cfg_simple()
    cfg.discos[0].storage = "local"  # pve3 solo tiene «local-lvm»
    plan = planificar(
        inv_cluster, definicion(2, plantilla=cfg, destino=Destino(ModoDestino.UN_NODO, ("pve3",)))
    )
    resumen.mostrar_plan(plan)
    assert plan.bloqueado and not resumen.boton_crear.isEnabled()
    assert "Ese almacenamiento no está disponible en el nodo" in resumen._errores.text()


def test_ca_l06_3_en_automatico_el_nodo_no_elegible_se_explica_y_no_recibe_maquinas(
    resumen, inv_cluster
):
    cfg = cfg_simple()
    cfg.discos[0].storage = "local"
    plan = planificar(
        inv_cluster, definicion(2, plantilla=cfg, destino=Destino(ModoDestino.AUTOMATICO))
    )
    resumen.mostrar_plan(plan)
    assert not plan.bloqueado and {e.nodo for e in plan.elementos} == {"pve1"}
    assert "«pve3» no tiene el almacenamiento «local»" in resumen._avisos.text()
    assert "«pve2» está sin conexión" in resumen._avisos.text()


def test_ca_l06_5_si_ningun_nodo_sirve_dice_que_ninguno_puede_alojar_la_plantilla(
    resumen, inv_cluster
):
    cfg = cfg_simple()
    cfg.discos[0].storage = "no-existe"
    plan = planificar(
        inv_cluster, definicion(2, plantilla=cfg, destino=Destino(ModoDestino.AUTOMATICO))
    )
    resumen.mostrar_plan(plan)
    assert plan.bloqueado
    assert "Ningún servidor puede alojar esta máquina" in resumen._errores.text()


def test_ca_l05_6_memoria_desconocida_de_un_nodo_se_avisa_sin_bloquear(resumen, inv_cluster):
    nodos = tuple(
        dataclasses.replace(n, mem_libre_mib=None) if n.nombre == "pve3" else n
        for n in inv_cluster.topologia.nodos
    )
    inv = dataclasses.replace(
        inv_cluster, topologia=dataclasses.replace(inv_cluster.topologia, nodos=nodos)
    )
    plan = planificar(inv, definicion(3, destino=Destino(ModoDestino.AUTOMATICO)))
    resumen.mostrar_plan(plan)
    assert not plan.bloqueado and resumen.boton_crear.isEnabled()
    assert "No se pudo leer la memoria libre de «pve3»; el reparto usa el espacio." in (
        resumen._avisos.text()
    )


def test_ca_l09_2_mas_procesadores_que_el_nodo_es_un_aviso_no_bloqueante(resumen, inv_cluster):
    cfg = cfg_simple(cores=16)  # pve1 tiene 8
    plan = planificar(inv_cluster, definicion(2, plantilla=cfg))
    resumen.mostrar_plan(plan)
    assert resumen.boton_crear.isEnabled()
    assert "Cada máquina pide 16 procesadores virtuales y «pve1» tiene 8." in resumen._avisos.text()


def test_ca_l10_3_el_aviso_se_repite_en_la_copia_del_resumen(resumen, inv_cluster):
    cfg = cfg_simple(cores=16)
    resumen.mostrar_plan(planificar(inv_cluster, definicion(2, plantilla=cfg)))
    resumen.boton_copiar.click()
    assert "procesadores virtuales" in QApplication.clipboard().text()
