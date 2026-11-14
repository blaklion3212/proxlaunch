"""Progreso del lote: tabla del libro, barra global, filtro, UPID y acciones (RF-L13).

También los modelos de tabla (``ModeloLibro``, ``ModeloRollback``) y la coalescencia de los
puentes entre hilos (CA-L13.5). Todo con datos fabricados: sin motor ni red.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication, QWidget

from proxlaunch.interfaz import trabajadores as tr
from proxlaunch.interfaz.modelos_tabla import (
    _TOKEN_ESTADO,
    _TOKEN_ROLLBACK,
    ESTADOS_PROBLEMA,
    FiltroProblemas,
    ModeloLibro,
    ModeloRollback,
    detalle_entrada,
)
from proxlaunch.interfaz.tema.paleta import TOKENS_CLARO, TOKENS_OSCURO, contraste
from proxlaunch.interfaz.textos import (
    simbolo_estado_mv,
    simbolo_estado_rollback,
    texto_estado_mv,
    texto_estado_rollback,
)
from proxlaunch.interfaz.vistas.progreso_lote import (
    FaseLote,
    ProgresoLote,
    texto_barra,
    texto_detalles_entrada,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    EstadoMV,
    EstadoRollback,
    MotivoNoEnviada,
    Plan,
    ResultadoRollback,
)

from .apoyo import UPID
from .apoyo_lote import definicion, elemento, entrada, entradas_de, upid_con_usuario

EM = EstadoMV


@pytest.fixture
def progreso(qtbot):
    p = ProgresoLote()
    qtbot.addWidget(p)
    p.show()
    return p


def plan_vacio(n: int) -> Plan:
    return Plan(
        id_lote="ab12cd34",
        definicion=definicion(n),
        elementos=tuple(elemento(i) for i in range(n)),
        vmids_saltados=(),
        reparto={},
        uso={},
        problemas=(),
        capacidad_maxima=None,
        generado_en=0.0,
        version_validacion=(9, 2),
    )


def poner(progreso, estados, **kw):
    progreso.iniciar(plan_vacio(len(estados)))
    progreso.actualizar(entradas_de(estados, **kw))


# --- Barra global (CA-L13.2) --------------------------------------------------------------


def test_ca_l13_2_texto_de_la_barra_con_terminadas_error_y_en_curso():
    estados = [EM.OK] * 6 + [EM.ERROR] + [EM.CREANDO, EM.ENVIANDO] + [EM.PENDIENTE] * 11
    assert texto_barra(entradas_de(estados)) == "7 de 20 terminadas · 1 con error · 2 en curso"


def test_ca_l13_2_la_barra_refleja_terminadas_sobre_n_sin_porcentaje_inventado(progreso):
    poner(progreso, [EM.OK, EM.OK, EM.CREANDO, EM.PENDIENTE])
    assert progreso.barra.minimum() == 0 and progreso.barra.maximum() == 4
    assert progreso.barra.value() == 2
    assert progreso.texto_resumen_barra == "2 de 4 terminadas · 1 en curso"
    assert "%" not in progreso.texto_resumen_barra  # CT-2: sin porcentaje dentro de una MV


def test_ca_l13_2_no_se_muestra_tiempo_estimado(progreso):
    poner(progreso, [EM.OK, EM.CREANDO])
    for texto in (progreso.texto_resumen_barra, progreso._titulo.text()):
        for palabra in ("restante", "estimad", "minutos", "segundos"):
            assert palabra not in texto.lower()


def test_ca_l13_2_la_barra_cuenta_sin_confirmar_y_sin_enviar():
    estados = [EM.OK, EM.CONEXION_PERDIDA, EM.TIEMPO_AGOTADO, EM.NO_ENVIADA, EM.PARCIAL]
    assert texto_barra(entradas_de(estados)) == (
        "5 de 5 terminadas · 1 con error · 2 sin confirmar · 1 sin enviar"
    )


def test_un_lote_sin_novedad_dice_solo_las_terminadas():
    assert texto_barra(entradas_de([EM.OK] * 3)) == "3 de 3 terminadas"


def test_ca_l13_2_el_color_de_la_barra_naranja_viene_del_tema():
    """D-02: la barra global usa el acento naranja (``#E57000``) del tema."""
    assert TOKENS_OSCURO["acento"] == "#E57000" == TOKENS_CLARO["acento"]


def test_la_barra_tiene_descripcion_accesible_con_el_mismo_resumen(progreso):
    poner(progreso, [EM.OK, EM.ERROR])
    assert progreso.barra.accessibleName()
    assert progreso.barra.accessibleDescription() == progreso.texto_resumen_barra


# --- Tabla (CA-L13.1, CA-L13.3) ----------------------------------------------------------


def test_ca_l13_1_una_fila_por_maquina_con_estado_en_texto_y_mensaje(progreso):
    err = ErrorProxLaunch(CodigoError.SIN_ESPACIO, {"storage": "local-lvm"})
    estados = [EM.OK, EM.ERROR, EM.CREANDO, EM.PENDIENTE]
    progreso.iniciar(plan_vacio(4))
    progreso.actualizar(
        tuple(entrada(i, e, error=err if e == EM.ERROR else None) for i, e in enumerate(estados))
    )
    m = progreso.modelo
    assert m.rowCount() == 4
    cab = [m.headerData(c, Qt.Orientation.Horizontal) for c in range(5)]
    assert cab == ["Estado", "Nombre", "VMID", "Nodo", "Detalle"]
    filas = [[m.data(m.index(f, c)) for c in range(5)] for f in range(4)]
    assert filas[0][:4] == ["✓ Lista", "web-01", "101", "pve1"]
    assert filas[1][0] == "✕ Con error" and filas[1][4]  # el error trae mensaje traducido
    assert filas[2][0] == "● Creando la máquina"
    assert filas[3][0] == "○ Pendiente"


@pytest.mark.parametrize("estado", list(EM))
def test_ca_l13_3_todo_estado_lleva_texto_y_simbolo_no_solo_color(estado):
    assert texto_estado_mv(estado).strip() and texto_estado_mv(estado) != str(estado)
    assert simbolo_estado_mv(estado) not in ("", "·")
    fila = ModeloLibro.texto_estado(entrada(0, estado))
    assert fila.startswith(simbolo_estado_mv(estado)) and texto_estado_mv(estado) in fila


def test_ca_l13_3_estados_finales_distintos_se_distinguen_por_simbolo():
    simbolos = {e: simbolo_estado_mv(e) for e in (EM.OK, EM.ERROR, EM.CON_AVISOS, EM.PARCIAL)}
    assert len(set(simbolos.values())) == 4


@pytest.mark.parametrize("estado", list(EstadoRollback))
def test_ca_l13_3_cada_estado_de_deshacer_lleva_texto_y_simbolo(estado):
    assert texto_estado_rollback(estado).strip() and simbolo_estado_rollback(estado) != "·"


def test_etapas_del_requisito_tienen_el_texto_del_ca_l13_1():
    assert texto_estado_mv(EM.VALIDANDO) == "Validando datos"
    assert texto_estado_mv(EM.ENVIANDO) == "Enviando a Proxmox"
    assert texto_estado_mv(EM.CREANDO) == "Creando la máquina"
    assert texto_estado_mv(EM.COMPROBANDO) == "Comprobando el resultado"
    assert texto_estado_mv(EM.OK) == "Lista"


def test_ca_l14_6_los_mensajes_por_estado_son_llanos_y_traducidos():
    e = entrada(2, EM.NO_ENVIADA, motivo_no_enviada=MotivoNoEnviada.CANCELADO)
    assert detalle_entrada(e) == "«web-03» no se envió (cancelaste el lote). No existe en Proxmox."
    assert "No se creó" not in detalle_entrada(e)
    assert "Puedes reintentarla" in detalle_entrada(entrada(0, EM.NO_CREADA_SEGURA))
    assert "no podemos asegurar que la creó este lote" in detalle_entrada(
        entrada(0, EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD)
    )
    assert "No sabemos si «web-01» se creó" in detalle_entrada(entrada(0, EM.CONEXION_PERDIDA))
    assert detalle_entrada(entrada(0, EM.OK)) == ""
    assert detalle_entrada(entrada(0, EM.CREANDO)) == ""


def test_ca_l15_2_el_aviso_de_creada_tras_comprobar_se_muestra():
    e = entrada(0, EM.CON_AVISOS, avisos=("creada_tras_comprobar",))
    assert "Se creó aunque Proxmox tardó en responder" in detalle_entrada(e)


def test_ca_l12_7_cada_motivo_de_no_enviada_se_explica(progreso):
    for motivo, frase in (
        (MotivoNoEnviada.PAUSA, "el lote se detuvo"),
        (MotivoNoEnviada.ERROR_GLOBAL, "afectaba a todo el lote"),
        (MotivoNoEnviada.NODO_CAIDO, "el nodo no respondió"),
    ):
        assert frase in detalle_entrada(entrada(0, EM.NO_ENVIADA, motivo_no_enviada=motivo))


def test_ca_l13_3_el_modelo_expone_texto_accesible_por_fila(progreso):
    poner(progreso, [EM.OK, EM.ERROR])
    m = progreso.modelo
    t = m.data(m.index(0, 0), Qt.ItemDataRole.AccessibleTextRole)
    assert "web-01" in t and "101" in t and "Lista" in t


def test_ca_l13_4_el_color_de_estado_viene_de_los_tokens_del_tema(progreso):
    poner(progreso, [EM.OK, EM.ERROR])
    m = progreso.modelo
    claro = m.data(m.index(0, 0), Qt.ItemDataRole.ForegroundRole).name().upper()
    assert claro == TOKENS_OSCURO["exito"].upper()
    progreso.establecer_tema("claro")
    assert m.data(m.index(0, 0), Qt.ItemDataRole.ForegroundRole).name().upper() == (
        TOKENS_CLARO["exito"].upper()
    )


@pytest.mark.parametrize("tokens", [TOKENS_OSCURO, TOKENS_CLARO], ids=["oscuro", "claro"])
def test_rnf_l04_contraste_minimo_de_los_colores_de_estado_sobre_el_fondo_de_las_tablas(tokens):
    """El texto de estado supera 4.5:1 sobre el fondo, el panel y la fila alterna."""
    fondos = ("fondo", "fondo_panel", "fondo_alterno")
    for token in {*_TOKEN_ESTADO.values(), *_TOKEN_ROLLBACK.values()}:
        for f in fondos:
            assert contraste(tokens[token], tokens[f]) >= 4.5, (token, f)


# --- Filtro «Mostrar solo problemas» y detalles (CA-L13.4, CA-L13.6) -------------------------


def test_ca_l13_4_el_filtro_deja_solo_las_maquinas_con_problemas(progreso):
    poner(progreso, [EM.OK, EM.ERROR, EM.OK, EM.CONEXION_PERDIDA, EM.CREANDO, EM.NO_ENVIADA])
    assert progreso.filtro.rowCount() == 6
    progreso.chk_problemas.setChecked(True)
    nombres = [
        progreso.filtro.data(progreso.filtro.index(f, 1)) for f in range(progreso.filtro.rowCount())
    ]
    assert nombres == ["web-02", "web-04", "web-06"]
    progreso.chk_problemas.setChecked(False)
    assert progreso.filtro.rowCount() == 6


def test_ca_l13_4_el_filtro_se_reaplica_cuando_cambia_el_estado(progreso):
    poner(progreso, [EM.CREANDO, EM.OK])
    progreso.chk_problemas.setChecked(True)
    assert progreso.filtro.rowCount() == 0
    progreso.actualizar(entradas_de([EM.ERROR, EM.OK]))
    assert progreso.filtro.rowCount() == 1


@pytest.mark.parametrize("estado", sorted(ESTADOS_PROBLEMA, key=str))
def test_ca_l13_4_los_estados_con_problema_pasan_el_filtro(estado):
    f = FiltroProblemas()
    m = ModeloLibro()
    m.establecer_entradas(entradas_de([estado, EM.OK]))
    f.setSourceModel(m)
    f.establecer_solo_problemas(True)
    assert f.rowCount() == 1


def test_ca_l13_4_seleccionar_una_fila_muestra_sus_detalles_tecnicos(progreso):
    err = ErrorProxLaunch(CodigoError.SIN_ESPACIO, {"storage": "local-lvm"}, "no space left")
    progreso.iniciar(plan_vacio(2))
    progreso.actualizar(
        (
            entrada(0, EM.OK, upid=UPID),
            entrada(1, EM.ERROR, upid=UPID, error=err, log_tarea=("l1", "l2")),
        )
    )
    progreso.tabla.selectRow(1)
    texto = progreso.detalles.texto
    assert UPID in texto and "no space left" in texto and "sin_espacio" in texto
    assert "l1" in texto and "l2" in texto and "VMID: 102" in texto


def test_ca_l13_4_el_detalle_tecnico_con_el_filtro_activo_corresponde_a_la_fila_correcta(progreso):
    progreso.iniciar(plan_vacio(3))
    progreso.actualizar(
        (
            entrada(0, EM.OK),
            entrada(1, EM.OK),
            entrada(2, EM.ERROR, error=ErrorProxLaunch(CodigoError.SIN_ESPACIO)),
        )
    )
    progreso.chk_problemas.setChecked(True)
    progreso.tabla.selectRow(0)
    assert "VMID: 103" in progreso.detalles.texto


def test_ca_l13_6_el_upid_se_muestra_en_monoespaciada_y_se_copia(progreso):
    progreso.iniciar(plan_vacio(2))
    progreso.actualizar((entrada(0, EM.OK, upid=UPID), entrada(1, EM.PENDIENTE)))
    assert not progreso._upid.isVisible()  # sin selección no hay UPID
    progreso.tabla.selectRow(0)
    assert progreso._upid.isVisible() and progreso._upid.text() == UPID
    assert progreso._upid.property("mono") is True
    assert progreso._upid.isReadOnly()
    progreso._copiar_upid.click()
    assert QApplication.clipboard().text() == UPID


def test_una_fila_sin_upid_oculta_el_campo_del_upid(progreso):
    progreso.iniciar(plan_vacio(2))
    progreso.actualizar((entrada(0, EM.OK, upid=UPID), entrada(1, EM.NO_ENVIADA)))
    progreso.tabla.selectRow(0)
    progreso.tabla.selectRow(1)
    assert not progreso._upid.isVisible() and progreso._upid.text() == ""


def test_los_detalles_de_una_maquina_incluyen_motivo_y_avisos():
    e = entrada(
        0,
        EM.CON_AVISOS,
        upid=UPID,
        motivo_no_enviada=MotivoNoEnviada.PAUSA,
        avisos=("creada_tras_comprobar",),
    )
    texto = texto_detalles_entrada(e)
    assert "Motivo: pausa" in texto and "Avisos: creada_tras_comprobar" in texto
    assert f"UPID: {UPID}" in texto


# --- Botones por fase (CA-L13.7, CA-L16, CA-L15.6) -----------------------------------------


def visibles(p: ProgresoLote) -> set[str]:
    nombres = {
        "cancelar": p.boton_cancelar,
        "decidir": p.boton_decidir,
        "comprobar": p.boton_comprobar,
        "deshacer": p.boton_deshacer,
        "reintentar": p.boton_reintentar,
        "informe": p.boton_informe,
        "volver": p.boton_volver,
    }
    return {n for n, b in nombres.items() if b.isVisible()}


def test_ca_l13_7_mientras_corre_hay_cancelar_lote_visible(progreso):
    poner(progreso, [EM.CREANDO, EM.PENDIENTE])
    assert progreso.fase == FaseLote.EJECUTANDO
    assert visibles(progreso) == {"cancelar"}
    assert progreso.boton_cancelar.text() == "Cancelar lote"
    assert progreso._titulo.text() == "Creando 2 máquinas"


def test_titulo_en_singular_y_plural(progreso):
    poner(progreso, [EM.CREANDO])
    assert progreso._titulo.text() == "Creando 1 máquina"
    progreso.establecer_fase(FaseLote.TERMINADO)
    assert progreso._titulo.text() == "Lote terminado (1 máquina)"
    poner(progreso, [EM.OK] * 4)
    progreso.establecer_fase(FaseLote.TERMINADO)
    assert progreso._titulo.text() == "Lote terminado (4 máquinas)"


def test_ca_l16_cancelar_emite_la_solicitud_y_en_cancelando_ofrece_dejar_de_esperar(
    qtbot, progreso
):
    poner(progreso, [EM.CREANDO, EM.PENDIENTE])
    with qtbot.waitSignal(progreso.cancelar_solicitado, timeout=1000):
        progreso.boton_cancelar.click()
    progreso.establecer_fase(FaseLote.CANCELANDO)
    assert progreso.boton_cancelar.text() == "Dejar de esperar"
    with qtbot.waitSignal(progreso.dejar_de_esperar_solicitado, timeout=1000):
        progreso.boton_cancelar.click()


def test_ca_l16_1_hay_enviadas_solo_si_alguna_maquina_ya_salio(progreso):
    poner(progreso, [EM.PENDIENTE, EM.PENDIENTE], post_intentado=False)
    assert not progreso.hay_enviadas()
    progreso.actualizar((entrada(0, EM.CREANDO), entrada(1, EM.PENDIENTE)))
    assert progreso.hay_enviadas()


def test_ca_l14_2_en_pausa_aparece_decidir_que_hacer(qtbot, progreso):
    poner(progreso, [EM.ERROR, EM.PENDIENTE])
    progreso.establecer_fase(FaseLote.PAUSADO)
    assert visibles(progreso) == {"cancelar", "decidir"}
    with qtbot.waitSignal(progreso.decidir_pausa_solicitado, timeout=1000):
        progreso.boton_decidir.click()


def test_ca_l15_6_con_dudosas_se_ofrece_comprobar_con_el_conteo_en_plural(progreso):
    poner(progreso, [EM.OK, EM.CONEXION_PERDIDA, EM.TIEMPO_AGOTADO, EM.CONEXION_PERDIDA])
    progreso.establecer_fase(FaseLote.TERMINADO, dudosas=3)
    assert progreso.boton_comprobar.isVisible()
    assert progreso.boton_comprobar.text() == "Comprobar las 3 dudosas"
    progreso.establecer_fase(FaseLote.TERMINADO, dudosas=1)
    assert progreso.boton_comprobar.text() == "Comprobar la dudosa"
    progreso.establecer_fase(FaseLote.TERMINADO, dudosas=0)
    assert not progreso.boton_comprobar.isVisible()


def test_ca_l18_deshacer_solo_se_habilita_si_hay_elegibles(progreso):
    poner(progreso, [EM.OK, EM.ERROR])
    progreso.establecer_fase(FaseLote.TERMINADO, elegibles=0)
    assert progreso.boton_deshacer.isVisible() and not progreso.boton_deshacer.isEnabled()
    progreso.establecer_fase(FaseLote.TERMINADO, elegibles=1)
    assert progreso.boton_deshacer.isEnabled()


def test_ca_l21_reintentar_solo_aparece_si_hay_reintentables(progreso):
    poner(progreso, [EM.OK, EM.NO_ENVIADA])
    progreso.establecer_fase(FaseLote.TERMINADO, reintentables=0)
    assert not progreso.boton_reintentar.isVisible()
    progreso.establecer_fase(FaseLote.TERMINADO, reintentables=1)
    assert progreso.boton_reintentar.isVisible()
    assert progreso.boton_reintentar.text() == "Reintentar pendientes"


def test_lote_terminado_ofrece_informe_volver_y_deshacer(qtbot, progreso):
    poner(progreso, [EM.OK])
    progreso.establecer_fase(FaseLote.TERMINADO, elegibles=1)
    assert {"deshacer", "informe", "volver"} <= visibles(progreso)
    with qtbot.waitSignal(progreso.informe_solicitado, timeout=1000):
        progreso.boton_informe.click()
    with qtbot.waitSignal(progreso.volver_solicitado, timeout=1000):
        progreso.boton_volver.click()
    with qtbot.waitSignal(progreso.deshacer_solicitado, timeout=1000):
        progreso.boton_deshacer.click()


def test_mientras_se_comprueba_o_se_deshace_el_informe_no_esta_disponible(progreso):
    poner(progreso, [EM.OK])
    progreso.establecer_fase(FaseLote.DESHACIENDO)
    assert progreso.boton_cancelar.text() == "Detener lo que falta"
    assert progreso.boton_informe.isVisible() and not progreso.boton_informe.isEnabled()
    progreso.establecer_fase(FaseLote.COMPROBANDO)
    assert progreso._titulo.text() == "Comprobando las máquinas dudosas"


def test_iniciar_reinicia_filtro_detalles_y_mensajes(progreso):
    poner(progreso, [EM.ERROR])
    progreso.chk_problemas.setChecked(True)
    progreso.mostrar_aviso("aviso")
    progreso.mostrar_error("error")
    progreso.iniciar(plan_vacio(2))
    assert not progreso.chk_problemas.isChecked()
    assert not progreso._aviso.isVisible() and not progreso._error.isVisible()
    assert progreso.modelo.rowCount() == 2
    assert all(e.estado == EM.PENDIENTE for e in progreso.entradas)


def test_las_tablas_y_los_botones_tienen_nombre_accesible_o_texto(progreso):
    assert progreso.tabla.accessibleName() and progreso.tabla_rollback.accessibleName()
    for b in (
        progreso.boton_cancelar,
        progreso.boton_decidir,
        progreso.boton_deshacer,
        progreso.boton_reintentar,
        progreso.boton_informe,
        progreso.boton_volver,
    ):
        assert b.text().strip()


def test_ca_rnf_l04_la_tabla_se_recorre_con_flechas(qtbot, progreso):
    poner(progreso, [EM.OK, EM.OK, EM.OK])
    progreso.tabla.setFocus()
    progreso.tabla.setCurrentIndex(progreso.filtro.index(0, 0))
    qtbot.keyClick(progreso.tabla, Qt.Key.Key_Down)
    assert progreso.tabla.currentIndex().row() == 1
    assert progreso.tabla.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_ca_l10_5_cien_filas_son_un_modelo_no_cien_widgets(progreso):
    poner(progreso, [EM.OK] * 100)
    assert progreso.modelo.rowCount() == 100
    assert len(progreso.tabla.findChildren(QWidget)) < 20


def test_ca_l13_5_el_modelo_solo_notifica_las_filas_que_cambiaron(qtbot):
    m = ModeloLibro()
    base = entradas_de([EM.OK, EM.CREANDO, EM.PENDIENTE])
    m.establecer_entradas(base)
    cambios = []
    m.dataChanged.connect(lambda a, b: cambios.append((a.row(), b.row())))
    nuevas = (base[0], entrada(1, EM.OK), base[2])
    m.establecer_entradas(nuevas)
    assert cambios == [(1, 1)]


# --- Deshacer (tabla de avance) ---------------------------------------------------------------


def test_la_tabla_de_deshacer_empieza_pendiente_y_se_actualiza_por_vmid(progreso):
    progreso.iniciar_rollback([("web-01", 101, "pve1"), ("web-02", 102, "pve1")])
    assert progreso.tabla_rollback.isVisible()
    m = progreso.modelo_rollback
    assert [f.estado for f in m.filas] == [EstadoRollback.PENDIENTE] * 2
    progreso.actualizar_rollback(
        [ResultadoRollback(102, "pve1", "web-02", EstadoRollback.ELIMINADA)]
    )
    assert m.data(m.index(1, 0)) == "✓ Eliminada"
    assert m.data(m.index(0, 0)) == "○ Pendiente"


def test_un_fallo_al_eliminar_muestra_el_mensaje_del_error(progreso):
    err = ErrorProxLaunch(CodigoError.ROLLBACK_ENCENDIDA, {"nombre": "web-01"})
    m = ModeloRollback()
    m.iniciar([("web-01", 101, "pve1")])
    m.registrar(ResultadoRollback(101, "pve1", "web-01", EstadoRollback.OMITIDA, error=err))
    assert "está encendida" in m.data(m.index(0, 4))


# --- Puentes entre hilos: coalescencia (CA-L13.5) ----------------------------------------------


@pytest.fixture
def puente(qtbot):
    padre = QObject()
    p = tr.PuenteLote(tuple(elemento(i) for i in range(5)), padre)
    yield p
    padre.deleteLater()


def test_ca_l13_5_cientos_de_eventos_emiten_una_sola_senal_hasta_que_se_lee(qtbot, puente):
    puente.tomar_si_sucio()  # vacía la marca inicial
    avisos = []
    puente.sucio.connect(lambda: avisos.append(1), Qt.ConnectionType.DirectConnection)
    for i in range(300):
        puente.observar(entrada(i % 5, EM.CREANDO))
    assert avisos == [1]


def test_ca_l13_5_tomar_si_sucio_entrega_una_instantanea_y_luego_none(puente):
    puente.tomar_si_sucio()
    puente.observar(entrada(2, EM.OK))
    snap = puente.tomar_si_sucio()
    assert snap is not None and len(snap) == 5 and snap[2].estado == EM.OK
    assert puente.tomar_si_sucio() is None


def test_la_instantanea_conserva_el_orden_del_plan_y_la_ultima_entrada_de_cada_vmid(puente):
    puente.observar(entrada(1, EM.CREANDO))
    puente.observar(entrada(1, EM.OK))
    assert [e.elemento.vmid for e in puente.instantanea()] == [101, 102, 103, 104, 105]
    assert puente.instantanea()[1].estado == EM.OK


def test_puente_tras_leer_una_nueva_observacion_vuelve_a_avisar(puente):
    puente.tomar_si_sucio()
    avisos = []
    puente.sucio.connect(lambda: avisos.append(1), Qt.ConnectionType.DirectConnection)
    puente.observar(entrada(0, EM.CREANDO))
    puente.tomar_si_sucio()
    puente.observar(entrada(0, EM.OK))
    assert avisos == [1, 1]


def test_observar_no_falla_si_el_puente_ya_fue_destruido():
    p = tr.PuenteLote((elemento(0),))
    import shiboken6

    shiboken6.delete(p)
    # Un hilo rezagado del motor no debe lanzar (RNF-L11): la señal se descarta.
    p.observar(entrada(0, EM.OK))


def test_puente_de_rollback_coalesce_y_entrega_los_resultados(qtbot):
    padre = QObject()
    p = tr.PuenteRollback(padre)
    avisos = []
    p.sucio.connect(lambda: avisos.append(1), Qt.ConnectionType.DirectConnection)
    for _ in range(50):
        p.observar(ResultadoRollback(101, "pve1", "web-01", EstadoRollback.ELIMINANDO))
    p.observar(ResultadoRollback(102, "pve1", "web-02", EstadoRollback.ELIMINADA))
    assert avisos == [1]
    res = p.tomar_si_sucio()
    assert {r.vmid for r in res} == {101, 102}
    assert p.tomar_si_sucio() is None
    padre.deleteLater()


def test_los_upid_con_usuario_no_cambian_la_tabla_pero_si_los_detalles():
    """La tabla no muestra UPID; el detalle técnico sí (con su usuario, es local)."""
    e = entrada(0, EM.OK, upid=upid_con_usuario(101))
    assert "ana@pve" not in ModeloLibro.texto_estado(e)
    assert "ana@pve" in texto_detalles_entrada(e)
