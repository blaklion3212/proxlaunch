"""Importación desde CSV y lote por filas en la interfaz (MVP 3): vista previa, modo por filas,
quitar filas, asignar VMID automático, «Revisar filas…», «Salir del lote por filas», plantilla e
informe CSV (RF-C01..C09, C13, C14, G07; D-22; INV-M6).

Derivadas de docs/requisitos/mvp3.md (CA-C01.x, CA-C05.x, CA-C06.x, CA-C07.x, CA-C08.x, CA-C09.3,
CA-C10.x, CA-C14.x) y docs/arquitectura/mvp3.md §6.6 y §13.
"""

from __future__ import annotations

import csv
import io
import time
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from proxlaunch.interfaz import archivos_ui
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila

from . import test_ventana_principal as _base
from .apoyo import CreacionPorVmid
from .apoyo_mvp3 import (
    ENCABEZADO_CSV,
    conectar3,
    csv_valido,
    escribir_csv,
    hubo_escritura,
    importar_csv_por_menu,
    pulsar_boton,
    todos_los_textos,
)
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .apoyo_ventana_lote import crear_lote, esperar_fin
from .test_ventana_principal import esperar_validacion

entorno = _base.entorno  # fixture base de la ventana


# --- Ayudas --------------------------------------------------------------------------------------


def fila(
    nombre,
    nucleos=2,
    memoria="2 GiB",
    disco="20 GiB",
    storage="local-lvm",
    red="vmbr0",
    vmid="",
    nodo="",
):
    return [nombre, nucleos, memoria, disco, storage, red, vmid, nodo]


def csv_de(tmp_path: Path, *filas: list, nombre: str = "ejemplo.csv") -> Path:
    return escribir_csv(tmp_path / nombre, [list(ENCABEZADO_CSV), *filas])


@pytest.fixture
def conectado(qtbot, entorno3):
    cliente = conectar3(qtbot, entorno3)
    return entorno3.ventana, cliente


def importar(qtbot, entorno3, modales, archivos, ruta: Path) -> None:
    importar_csv_por_menu(qtbot, entorno3, modales, archivos, ruta)


def ver_resumen_filas(qtbot, v) -> None:
    """Pulsa «Ver resumen» del panel de filas y espera a que el plan esté dibujado."""
    qtbot.waitUntil(lambda: v.panel_filas.boton_resumen.isEnabled(), timeout=3000)
    v.panel_filas.boton_resumen.click()
    qtbot.waitUntil(lambda: v.resumen_lote.plan is not None and not v._planificando, timeout=5000)


def seleccionar(panel, *posiciones: int) -> None:
    sel = panel.tabla.selectionModel()
    sel.clearSelection()
    for p in posiciones:
        sel.select(
            panel.modelo.index(p, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
        )


def numeros_de_fila(panel) -> list[str]:
    return [
        str(panel.modelo.data(panel.modelo.index(r, 0))) for r in range(panel.modelo.rowCount())
    ]


def textos_resumen(v) -> str:
    return todos_los_textos(v.resumen_lote)


@pytest.fixture
def lote_de_cuatro(qtbot, entorno3, conectado, modales, archivos, tmp_path):
    """Un CSV de cuatro máquinas ya importado (filas 2 a 5 del archivo)."""
    v, cliente = conectado
    ruta = csv_de(
        tmp_path,
        fila("web-01", 4, "4 GiB"),
        fila("web-02", 4, "2 GiB", vmid=250, nodo="pve1"),
        fila("db-01", 8, "2 GiB", nodo="pve3"),
        fila("ejemplo-01", 2),
    )
    importar(qtbot, entorno3, modales, archivos, ruta)
    return v, cliente, ruta


# --- CA-C01.3: modo «Lote por filas» -----------------------------------------------------------


def test_ca_c01_3_importar_pasa_al_modo_por_filas_con_el_nombre_del_archivo_no_la_ruta(
    lote_de_cuatro, tmp_path
):
    v, _, ruta = lote_de_cuatro
    assert v.bloque_lote.es_por_filas
    assert v.panel_filas.titulo == "4 máquinas desde el archivo «ejemplo.csv»"
    assert str(tmp_path) not in todos_los_textos(v)  # nunca la ruta (privacidad)
    assert v.panel_filas.isVisibleTo(v)
    for oculto in (v.formulario, v.selector_perfil, v.resumen):
        assert not oculto.isVisibleTo(v)
    # No aplican ni cantidad ni patrón de nombres.
    assert not v.bloque_lote.cantidad.isVisibleTo(v) and not v.bloque_lote.prefijo.isVisibleTo(v)
    assert v.statusBar().currentMessage() == "Se importaron 4 máquinas desde «ejemplo.csv»"


def test_ca_c05_1_la_tabla_numera_las_filas_como_excel_con_el_encabezado_en_la_fila_1(
    lote_de_cuatro,
):
    v, _, _ = lote_de_cuatro
    assert numeros_de_fila(v.panel_filas) == ["2", "3", "4", "5"]


def test_la_tabla_muestra_la_configuracion_propia_de_cada_fila(lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    m = v.panel_filas.modelo
    texto_fila = [
        " | ".join(str(m.data(m.index(r, c))) for c in range(m.columnCount()))
        for r in range(m.rowCount())
    ]
    assert "web-01" in texto_fila[0] and "250" in texto_fila[1] and "pve1" in texto_fila[1]
    assert "pve3" in texto_fila[2] and "Automático" in texto_fila[0]


def test_en_modo_por_filas_no_se_ofrece_guardar_como_perfil(lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    assert not v._accion_guardar_perfil.isEnabled()
    assert v.panel_filas.boton_guardar.isEnabled()
    assert v.panel_filas.boton_revisar.isVisibleTo(v)


# --- INV-M6: importar jamás crea ni habilita «Crear» --------------------------------------------


def test_inv_m6_importar_no_envia_ninguna_peticion_de_escritura_ni_reserva_vmids(lote_de_cuatro):
    v, cliente, _ = lote_de_cuatro
    assert not hubo_escritura(cliente)
    reservas = [ll for ll in cliente.llamadas if ll[0] in ("vmid_libre", "proximo_vmid")]
    assert reservas == []  # los VMID se reservan al pedir el resumen, no antes (CA-G04.2)


def test_inv_m6_tras_importar_no_hay_plan_y_crear_esta_deshabilitado(lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    r = v.resumen_lote
    assert r.plan is None
    assert r.puede_crear is False
    assert not r.boton_crear.isEnabled()
    assert v._lote is None and not v._creando and not v._planificando
    assert v.panel_filas.boton_resumen.isEnabled()  # el único camino es «Ver resumen»


def test_inv_m6_el_resumen_se_genera_solo_por_accion_explicita_y_aun_no_escribe(
    qtbot, lote_de_cuatro
):
    v, cliente, _ = lote_de_cuatro
    ver_resumen_filas(qtbot, v)
    assert v.resumen_lote.plan is not None
    assert not hubo_escritura(cliente)  # planificar solo lee (INV-M1)
    assert v._lote is None  # y no arranca nada: falta confirmar «Crear»


def test_inv_m6_end_to_end_cada_fila_se_crea_con_su_propia_configuracion(
    qtbot, entorno3, conectado, modales, archivos, tmp_path
):
    v, cliente = conectado
    creacion = CreacionPorVmid()
    entorno3.creacion = creacion
    ruta = csv_de(
        tmp_path,
        fila("web-01", 4, "4 GiB"),
        fila("web-02", 2, "2 GiB", vmid=250, nodo="pve1"),
        fila("db-01", 8, "2 GiB", nodo="pve3"),
    )
    importar(qtbot, entorno3, modales, archivos, ruta)
    ver_resumen_filas(qtbot, v)
    assert v.resumen_lote.puede_crear
    assert creacion.llamadas_crear == 0
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    recibidas = {c.nombre: c for c in creacion.cfgs_recibidas}
    assert set(recibidas) == {"web-01", "web-02", "db-01"}
    assert (recibidas["web-01"].cores, recibidas["web-02"].cores, recibidas["db-01"].cores) == (
        4,
        2,
        8,
    )
    assert recibidas["web-02"].vmid == 250 and recibidas["web-02"].nodo == "pve1"
    assert recibidas["db-01"].nodo == "pve3"
    assert recibidas["web-01"].memoria_mib == 4096


def test_inv_m6_cargar_un_lote_por_filas_guardado_tampoco_crea_nada(
    qtbot, conectado, archivos, tmp_path
):
    from .apoyo_mvp3 import definicion_filas, escribir_lote_guardado

    v, cliente = conectado
    ruta = escribir_lote_guardado(
        tmp_path / "f.proxlaunch-lote.json",
        definicion_filas([{"nombre": "a", "origen": 2}, {"nombre": "b", "origen": 3}]),
    )
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v.bloque_lote.es_por_filas, timeout=3000)
    assert v.resumen_lote.plan is None and not v.resumen_lote.puede_crear
    assert not hubo_escritura(cliente) and v._lote is None


# --- «Salir del lote por filas» ----------------------------------------------------------------


def test_salir_del_lote_por_filas_devuelve_el_formulario_normal(qtbot, lote_de_cuatro):
    v, cliente, _ = lote_de_cuatro
    v.panel_filas.boton_salir.click()
    esperar_validacion(qtbot, v)
    assert not v.bloque_lote.es_por_filas
    assert v.formulario.isVisibleTo(v) and v.selector_perfil.isVisibleTo(v)
    assert not v.panel_filas.isVisibleTo(v)
    assert v.bloque_lote.cantidad.isVisibleTo(v)
    assert v._origen_lote is None and v._ruta_lote is None
    assert v.resumen_lote.plan is None
    assert v._accion_guardar_perfil.isEnabled()
    assert not hubo_escritura(cliente)


def test_salir_del_lote_por_filas_no_deja_cambios_pendientes_que_preguntar(qtbot, lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    v.panel_filas.boton_salir.click()
    esperar_validacion(qtbot, v)
    assert not v._hay_cambios_sin_guardar()


# --- Quitar filas ------------------------------------------------------------------------------


def test_quitar_filas_actualiza_tabla_titulo_y_conserva_la_numeracion_de_origen(lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    p = v.panel_filas
    seleccionar(p, 1, 2)
    assert p.boton_quitar.isEnabled()
    p.boton_quitar.click()
    assert numeros_de_fila(p) == ["2", "5"]
    assert p.titulo == "2 máquinas desde el archivo «ejemplo.csv»"
    assert [f.nombre for f in v._definicion_actual().filas] == ["web-01", "ejemplo-01"]


def test_quitar_filas_invalida_el_resumen_anterior(qtbot, lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    ver_resumen_filas(qtbot, v)
    seleccionar(v.panel_filas, 0)
    v.panel_filas.boton_quitar.click()
    assert v.resumen_lote.plan is None and not v.resumen_lote.puede_crear


def test_no_se_pueden_quitar_todas_las_filas_para_eso_esta_salir(lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    seleccionar(v.panel_filas, 0, 1, 2, 3)
    assert not v.panel_filas.boton_quitar.isEnabled()
    assert v.panel_filas.boton_salir.isEnabled()


def test_sin_seleccion_el_boton_de_quitar_esta_deshabilitado(lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    seleccionar(v.panel_filas)
    assert not v.panel_filas.boton_quitar.isEnabled()


def test_ca_c07_2_el_resumen_dice_cuantas_filas_del_archivo_se_van_a_crear(qtbot, lote_de_cuatro):
    v, _, _ = lote_de_cuatro
    seleccionar(v.panel_filas, 3)
    v.panel_filas.boton_quitar.click()
    ver_resumen_filas(qtbot, v)
    assert "Se van a crear 3 de las 4 filas del archivo." in textos_resumen(v)


# --- Asignar VMID automático (CA-C09.3) ---------------------------------------------------------


def test_ca_c09_3_un_vmid_explicito_ocupado_bloquea_y_ofrece_asignar_uno_automatico(
    qtbot, lote_de_cuatro
):
    v, cliente, _ = lote_de_cuatro
    cliente.vmids_ocupados.add(250)
    ver_resumen_filas(qtbot, v)
    texto = textos_resumen(v)
    assert "Fila 3: el número 250 ya lo usa otra máquina." in texto
    assert not v.resumen_lote.puede_crear
    boton = next(
        b
        for b in v.resumen_lote.findChildren(QPushButton)
        if b.accessibleName() == "Asignar un número de máquina automático a la fila 3"
    )
    assert boton.isVisibleTo(v) and boton.text() == "Asignar automáticamente"
    assert not hubo_escritura(cliente)  # nada se corrige solo: hace falta pulsar


def test_ca_c09_3_asignar_automaticamente_replanifica_y_libera_el_crear(qtbot, lote_de_cuatro):
    v, cliente, _ = lote_de_cuatro
    cliente.vmids_ocupados.add(250)
    ver_resumen_filas(qtbot, v)
    boton = next(
        b
        for b in v.resumen_lote.findChildren(QPushButton)
        if b.accessibleName().startswith("Asignar un número de máquina automático")
    )
    boton.click()
    qtbot.waitUntil(lambda: v.resumen_lote.plan is not None and not v._planificando, timeout=5000)
    assert v._definicion_actual().filas[1].vmid is None
    vmids = [e.vmid for e in v.resumen_lote.plan.elementos]
    assert 250 not in vmids and len(set(vmids)) == 4
    assert "ya lo usa otra máquina" not in textos_resumen(v)
    assert v.resumen_lote.puede_crear
    assert not hubo_escritura(cliente)


def test_ca_c09_3_la_fila_se_nombra_con_su_numero_de_origen_aunque_se_quiten_filas_antes(
    qtbot, lote_de_cuatro
):
    v, cliente, _ = lote_de_cuatro
    cliente.vmids_ocupados.add(250)
    seleccionar(v.panel_filas, 0)  # se quita «web-01» (fila 2 del archivo)
    v.panel_filas.boton_quitar.click()
    ver_resumen_filas(qtbot, v)
    # «web-02» pasó a la posición 1 del lote, pero sigue siendo la fila 3 del archivo.
    assert "Fila 3: el número 250 ya lo usa otra máquina." in textos_resumen(v)
    assert "Fila 1:" not in textos_resumen(v) and "Fila 2: el número" not in textos_resumen(v)


# --- Hallazgo: avisos de clúster sin prefijo de fila -------------------------------------------


def test_un_aviso_de_cluster_no_lleva_prefijo_de_fila(qtbot, lote_de_cuatro):
    """«pve2» (caído) no pertenece a ninguna fila con nodo fijo: la fila 2 tiene nodo Automático.
    El aviso debe decir «pve2 está sin conexión» sin «Fila 2:» (CA-C05.1 numera los problemas de
    UNA fila; este es del clúster)."""
    v, _, _ = lote_de_cuatro
    assert v.panel_filas.modelo.data(v.panel_filas.modelo.index(0, 3)) in ("Automático", "—")
    ver_resumen_filas(qtbot, v)
    lineas = [x for x in textos_resumen(v).splitlines() if "«pve2» está sin conexión" in x]
    assert lineas, "se esperaba el aviso del nodo caído"
    assert all("Fila" not in x for x in lineas), lineas


def test_ca_c09_2_una_fila_que_pide_un_nodo_caido_se_senala_en_la_vista_previa_con_su_fila(
    qtbot, conectado, modales, archivos, tmp_path
):
    """Contraste del hallazgo: si la fila SÍ pide el nodo caído, el error es de esa fila."""
    v, _ = conectado
    ruta = csv_de(tmp_path, fila("a"), fila("b", nodo="pve2"))
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        d.tabla.selectRow(1)
        visto["detalle"] = d.detalle.toPlainText()
        visto["estados"] = [f.estado for f in d.resultado.filas]
        d.reject()

    _abrir_asistente(qtbot, v, modales, archivos, ruta, _ver)
    assert visto["estados"] == [EstadoFila.CORRECTA, EstadoFila.CON_ERROR]
    assert "Fila 3" in visto["detalle"] and "pve2" in visto["detalle"]


# --- «Revisar filas…» --------------------------------------------------------------------------


def test_revisar_filas_reinterpreta_contra_el_inventario_actual_sin_releer_el_archivo(
    qtbot, lote_de_cuatro, modales, archivos
):
    v, _, ruta = lote_de_cuatro
    assert v._origen_lote.resultado.deteccion is not None
    previo = [f.estado for f in v._origen_lote.resultado.filas]
    assert EstadoFila.CON_ERROR not in previo
    # El servidor cambió desde la importación: «local-lvm» ya no existe.
    inv = v._inv
    renombrado = {
        n: tuple(replace(s, id="otro-almacen") if s.id == "local-lvm" else s for s in ss)
        for n, ss in inv.storages.items()
    }
    v._inv = replace(inv, storages=renombrado)
    ruta.unlink()  # y el archivo ya no está: revisar no debe volver a leerlo
    pedidos_antes = len(archivos.pedidos_abrir)
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        visto["estados"] = [f.estado for f in d.resultado.filas]
        visto["nombre"] = d.nombre_archivo
        visto["resumen"] = d.etiqueta_resumen.text()
        pulsar_boton(d, "Corregir el archivo")

    modales.responder(DialogoImportarCsv, _ver)
    v.panel_filas.boton_revisar.click()
    assert visto["estados"] == [EstadoFila.CON_ERROR] * 4
    assert visto["nombre"] == "ejemplo.csv" and "4 con error" in visto["resumen"]
    assert len(archivos.pedidos_abrir) == pedidos_antes  # no se pidió ni se leyó otro archivo
    assert v.panel_filas.modelo.rowCount() == 4  # «Corregir» no cambia el lote vigente


def test_revisar_filas_sin_cambios_en_el_servidor_muestra_lo_mismo_y_continuar_no_duplica(
    qtbot, lote_de_cuatro, modales
):
    v, cliente, _ = lote_de_cuatro

    def _continuar(d: DialogoImportarCsv) -> None:
        d.boton_continuar.click()

    modales.responder(DialogoImportarCsv, _continuar)
    v.panel_filas.boton_revisar.click()
    assert v.panel_filas.modelo.rowCount() == 4 and numeros_de_fila(v.panel_filas)[0] == "2"
    assert not hubo_escritura(cliente) and v.resumen_lote.plan is None


def test_revisar_filas_no_esta_disponible_para_un_lote_por_filas_guardado(
    qtbot, conectado, archivos, tmp_path
):
    from .apoyo_mvp3 import definicion_filas, escribir_lote_guardado

    v, _ = conectado
    ruta = escribir_lote_guardado(
        tmp_path / "f.proxlaunch-lote.json", definicion_filas([{"nombre": "a"}, {"nombre": "b"}])
    )
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v.bloque_lote.es_por_filas, timeout=3000)
    assert not v.panel_filas.boton_revisar.isVisibleTo(v)  # no hay CSV que reabrir


# --- Vista previa del asistente (CA-C06, CA-C05.10, CA-C07) ------------------------------------


def _abrir_asistente(qtbot, v, modales, archivos, ruta: Path, accion) -> None:
    archivos.abrir.append(ruta)

    def _ante(d: DialogoImportarCsv) -> None:
        qtbot.waitUntil(
            lambda: not d.ocupado and (d.resultado is not None or bool(d.error_lectura.text())),
            timeout=8000,
        )
        accion(d)

    modales.responder(DialogoImportarCsv, _ante)
    v._accion_importar_csv.trigger()


def test_ca_c05_10_cien_filas_con_error_se_muestran_todas_sin_congelar_la_interfaz(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    filas = [fila(f"m-{i:03d}", nucleos="abc") for i in range(100)]
    ruta = csv_de(tmp_path, *filas, nombre="malo.csv")
    visto: dict[str, object] = {}

    def _medir(d: DialogoImportarCsv) -> None:
        pass

    archivos.abrir.append(ruta)
    retrasos: list[float] = []

    def _ante(d: DialogoImportarCsv) -> None:
        ultimo = [time.perf_counter()]

        def _latido() -> None:
            ahora = time.perf_counter()
            retrasos.append(ahora - ultimo[0])
            ultimo[0] = ahora

        reloj = QTimer()
        reloj.setInterval(5)
        reloj.timeout.connect(_latido)
        reloj.start()
        qtbot.waitUntil(lambda: not d.ocupado and d.resultado is not None, timeout=8000)
        d.boton_copiar.click()
        qtbot.wait(30)
        reloj.stop()
        visto["resumen"] = d.etiqueta_resumen.text()
        visto["filas"] = d.filtro.rowCount()
        visto["continuar"] = d.boton_continuar.isEnabled()
        visto["principal"] = d.boton_corregir.isVisibleTo(d)
        visto["lineas"] = QApplication.clipboard().text().count("\n") + 1
        d.reject()

    modales.responder(DialogoImportarCsv, _ante)
    v._accion_importar_csv.trigger()
    assert visto["resumen"].endswith("100 filas: 0 correctas, 0 con aviso, 100 con error")
    assert visto["filas"] == 100 and visto["lineas"] == 100
    assert visto["continuar"] is False and visto["principal"] is True
    assert max(retrasos) < 0.2, f"el bucle de eventos se detuvo {max(retrasos) * 1000:.0f} ms"


def test_ca_c06_2_el_estado_de_cada_fila_lleva_texto_y_simbolo_y_el_filtro_deja_los_problemas(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    ruta = csv_de(tmp_path, fila("ok-1"), fila("mala", nucleos="abc"), fila("ok-2"))
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        m = d.modelo
        ultima = m.columnCount() - 1
        visto["estados"] = [str(m.data(m.index(r, ultima))) for r in range(m.rowCount())]
        d.casilla_problemas.setChecked(True)
        visto["solo_problemas"] = d.filtro.rowCount()
        d.casilla_problemas.setChecked(False)
        d.tabla.selectRow(1)
        visto["detalle"] = d.detalle.toPlainText()
        d.reject()

    _abrir_asistente(qtbot, v, modales, archivos, ruta, _ver)
    assert visto["estados"] == ["✔ Correcta", "✖ Con error", "✔ Correcta"]
    assert visto["solo_problemas"] == 1
    assert "Fila 3, columna «nucleos»" in visto["detalle"]  # CA-C05.1 y CA-C06.3
    assert "Valor del archivo: «abc»" in visto["detalle"]  # CA-C06.4


def test_ca_c07_1_con_errores_el_principal_es_corregir_y_se_ofrece_importar_las_correctas(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    ruta = csv_de(tmp_path, fila("ok-1"), fila("mala", nucleos="abc"), fila("ok-2"))
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        visto["corregir"] = d.boton_corregir.isVisibleTo(d)
        visto["cancelar"] = d.boton_cancelar.isVisibleTo(d)
        visto["continuar"] = d.boton_continuar.text()
        visto["errores"] = d.boton_errores.isEnabled()
        d.reject()

    _abrir_asistente(qtbot, v, modales, archivos, ruta, _ver)
    assert visto == {
        "corregir": True,
        "cancelar": False,
        "continuar": "Importar solo las 2 filas correctas",
        "errores": True,
    }


def test_ca_c07_3_un_csv_sin_errores_ofrece_continuar_y_cancelar(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        visto["continuar"] = (d.boton_continuar.text(), d.boton_continuar.isEnabled())
        visto["corregir"] = d.boton_corregir.isVisibleTo(d)
        visto["errores"] = d.boton_errores.isEnabled()
        d.reject()

    _abrir_asistente(qtbot, v, modales, archivos, csv_valido(tmp_path / "ok.csv", 3), _ver)
    assert visto == {"continuar": ("Continuar", True), "corregir": False, "errores": False}


def test_ca_c07_2_importar_solo_las_correctas_pide_confirmar_con_foco_en_cancelar(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, cliente = conectado
    ruta = csv_de(tmp_path, fila("ok-1"), fila("mala", nucleos="abc"), fila("ok-2"))
    visto: dict[str, object] = {}

    def _caja(caja: QMessageBox) -> None:
        visto["texto"] = caja.text()
        visto["defecto"] = caja.defaultButton().text()
        visto["escape"] = caja.escapeButton().text()
        pulsar_boton(caja, "Cancelar")

    modales.responder(QMessageBox, _caja)
    _abrir_asistente(qtbot, v, modales, archivos, ruta, lambda d: d.boton_continuar.click())
    assert visto["defecto"] == "Cancelar" and visto["escape"] == "Cancelar"
    assert "Se importarán 2 de 3 filas del archivo." in visto["texto"]
    assert "Fila 3 · mala (tiene un error)" in visto["texto"]
    assert not v.bloque_lote.es_por_filas  # cancelar: no se importó nada
    assert not hubo_escritura(cliente)


def test_ca_c07_2_confirmar_importa_solo_las_correctas_y_no_reenumera(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    ruta = csv_de(tmp_path, fila("ok-1"), fila("mala", nucleos="abc"), fila("ok-2"))
    modales.pulsar(QMessageBox, "Importar esas filas")
    _abrir_asistente(qtbot, v, modales, archivos, ruta, lambda d: d.boton_continuar.click())
    qtbot.waitUntil(lambda: v.bloque_lote.es_por_filas, timeout=3000)
    assert [f.nombre for f in v._definicion_actual().filas] == ["ok-1", "ok-2"]
    assert numeros_de_fila(v.panel_filas) == ["2", "4"]
    assert v.panel_filas.titulo == "2 máquinas desde el archivo «ejemplo.csv»"
    ver_resumen_filas(qtbot, v)
    assert "Se van a crear 2 de las 3 filas del archivo." in textos_resumen(v)


def test_ca_c07_5_si_no_queda_ninguna_fila_no_se_puede_continuar(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    ruta = csv_de(tmp_path, fila("mala-1", nucleos="abc"), fila("mala-2", memoria="xx"))
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        visto["continuar"] = d.boton_continuar.isEnabled()
        visto["puede"] = d.puede_continuar
        d.boton_continuar.click()  # aunque se pulse, no debe aceptar
        visto["aceptado"] = d.result()
        d.reject()

    _abrir_asistente(qtbot, v, modales, archivos, ruta, _ver)
    assert visto == {"continuar": False, "puede": False, "aceptado": 0}
    assert not v.bloque_lote.es_por_filas


def test_ca_c06_10_sin_conexion_el_asistente_avisa_y_no_deja_continuar(
    qtbot, entorno3, modales, archivos, tmp_path
):
    v = entorno3.ventana  # sin conectar
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        visto["aviso"] = d.aviso_sin_conexion.text()
        visto["continuar"] = d.boton_continuar.isEnabled()
        d.reject()

    assert v._accion_importar_csv.isEnabled()
    _abrir_asistente(qtbot, v, modales, archivos, csv_valido(tmp_path / "ok.csv", 2), _ver)
    assert visto["aviso"].startswith("Sin conexión")
    assert visto["continuar"] is False


def test_un_csv_sin_la_columna_nombre_dice_cual_falta_y_no_cambia_el_formulario(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    ruta = escribir_csv(tmp_path / "sin-nombre.csv", [["nucleos", "memoria"], [2, "2 GiB"]])
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        visto["error"] = d.error_lectura.text()
        visto["continuar"] = d.boton_continuar.isEnabled()
        d.reject()

    antes = v.formulario.configuracion()
    _abrir_asistente(qtbot, v, modales, archivos, ruta, _ver)
    assert "Falta la columna «nombre»" in visto["error"] and visto["continuar"] is False
    assert v.formulario.configuracion() == antes and not v.bloque_lote.es_por_filas


def test_un_csv_vacio_se_dice_en_llano(qtbot, conectado, modales, archivos, tmp_path):
    v, _ = conectado
    ruta = escribir_csv(tmp_path / "vacio.csv", [list(ENCABEZADO_CSV)])
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        visto["error"] = d.error_lectura.text()
        d.reject()

    _abrir_asistente(qtbot, v, modales, archivos, ruta, _ver)
    assert "no tiene máquinas" in visto["error"]


def test_cancelar_el_selector_de_archivos_csv_no_abre_el_asistente(
    qtbot, conectado, modales, archivos
):
    v, _ = conectado
    archivos.abrir.append(None)
    v._accion_importar_csv.trigger()
    assert modales.de_clase(DialogoImportarCsv) == [] and not v.bloque_lote.es_por_filas


def test_el_asistente_en_basico_oculta_codificacion_y_en_avanzado_la_muestra(
    qtbot, conectado, modales, archivos, tmp_path
):
    from proxlaunch.nucleo.persistencia.preferencias import Modo

    v, _ = conectado
    ruta = csv_valido(tmp_path / "ok.csv", 2)
    visto: dict[str, bool] = {}
    _abrir_asistente(
        qtbot,
        v,
        modales,
        archivos,
        ruta,
        lambda d: (visto.update(basico=d.combo_codificacion.isVisibleTo(d)), d.reject()),
    )
    v.establecer_modo(Modo.AVANZADO)
    _abrir_asistente(
        qtbot,
        v,
        modales,
        archivos,
        ruta,
        lambda d: (visto.update(avanzado=d.combo_codificacion.isVisibleTo(d)), d.reject()),
    )
    assert visto == {"basico": False, "avanzado": True}  # CA-C01.1


def test_descargar_filas_con_error_escribe_un_csv_con_solo_esas_filas(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    ruta = csv_de(tmp_path, fila("ok-1"), fila("mala-uno", nucleos="abc"), fila("ok-2"))
    salida = tmp_path / "errores.csv"
    archivos.guardar.append(salida)

    def _ver(d: DialogoImportarCsv) -> None:
        d.boton_errores.click()
        qtbot.waitUntil(salida.exists, timeout=3000)
        qtbot.waitUntil(lambda: "Se guardó" in d.estado_operacion.text(), timeout=3000)
        d.reject()

    _abrir_asistente(qtbot, v, modales, archivos, ruta, _ver)
    texto = salida.read_text(encoding="utf-8-sig")
    assert "mala-uno" in texto and "ok-1" not in texto and "ok-2" not in texto


# --- Plantilla CSV (RF-C10) --------------------------------------------------------------------


@pytest.mark.parametrize("separador", [";", ","])
def test_ca_c10_descargar_la_plantilla_funciona_sin_conexion_y_respeta_el_separador(
    qtbot, entorno3, archivos, monkeypatch, tmp_path, separador
):
    v = entorno3.ventana  # sin conectar: P-M08
    monkeypatch.setattr(archivos_ui, "pedir_separador_plantilla", lambda parent: separador)
    destino = tmp_path / "plantilla.csv"
    archivos.guardar.append(destino)
    assert v._accion_plantilla_csv.isEnabled()
    v._accion_plantilla_csv.trigger()
    qtbot.waitUntil(destino.exists, timeout=3000)
    qtbot.waitUntil(
        lambda: v.statusBar().currentMessage().startswith("Plantilla guardada"), timeout=3000
    )
    # Todo el CSV va entre comillas (QUOTE_ALL): se lee con csv, respetando el separador elegido.
    texto = destino.read_text(encoding="utf-8-sig")
    primera = next(csv.reader(io.StringIO(texto), delimiter=separador))
    assert primera[0] == "nombre" and len(primera) > 3
    assert texto.splitlines()[0].startswith(f'"nombre"{separador}"')
    assert v.statusBar().currentMessage() == "Plantilla guardada en «plantilla.csv»"


def test_ca_c10_cancelar_el_separador_o_la_ruta_no_escribe_nada(
    qtbot, entorno3, archivos, monkeypatch, tmp_path
):
    v = entorno3.ventana
    monkeypatch.setattr(archivos_ui, "pedir_separador_plantilla", lambda parent: None)
    v._accion_plantilla_csv.trigger()
    assert archivos.pedidos_guardar == []  # ni siquiera se pidió la ruta
    monkeypatch.setattr(archivos_ui, "pedir_separador_plantilla", lambda parent: ";")
    archivos.guardar.append(None)
    v._accion_plantilla_csv.trigger()
    qtbot.wait(50)
    assert list(tmp_path.glob("*.csv")) == []


def test_ca_c10_la_plantilla_se_puede_reimportar_sin_errores_de_capa_1(
    qtbot, entorno3, modales, archivos, monkeypatch, tmp_path
):
    """Plantilla autovalidada (§13 de la arquitectura): lo que se descarga se lee sin errores
    de formato. Sin conexión solo corre la capa 1 (el nodo «pve2» del ejemplo es del servidor)."""
    v = entorno3.ventana
    monkeypatch.setattr(archivos_ui, "pedir_separador_plantilla", lambda parent: ";")
    destino = tmp_path / "plantilla.csv"
    archivos.guardar.append(destino)
    v._accion_plantilla_csv.trigger()
    qtbot.waitUntil(destino.exists, timeout=3000)
    qtbot.waitUntil(
        lambda: v.statusBar().currentMessage().startswith("Plantilla guardada"), timeout=3000
    )
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        visto["resumen"] = d.etiqueta_resumen.text()
        visto["con_error"] = d.hay_errores
        visto["filas"] = len(d.resultado.filas)
        d.reject()

    _abrir_asistente(qtbot, v, modales, archivos, destino, _ver)
    # Enmienda aprobada (MVP 4, RF-O28 / CA-O28): la plantilla ahora trae 5 filas de ejemplo y las
    # columnas origen, fuente, so, virtio y modo_clon; sigue reimportándose sin errores de capa 1.
    assert visto["filas"] == 5
    assert visto["con_error"] is False, visto["resumen"]


# --- Informe del lote como CSV (RF-C14) ----------------------------------------------------------


def test_ca_c14_1_el_informe_csv_se_habilita_con_un_lote_terminado_y_no_incluye_upid(
    qtbot, entorno3, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    entorno3.creacion = CreacionPorVmid()
    importar(qtbot, entorno3, modales, archivos, csv_valido(tmp_path / "ok.csv", 3))
    assert not v._accion_informe_csv.isEnabled()  # aún no hay lote
    ver_resumen_filas(qtbot, v)
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    assert v._accion_informe_csv.isEnabled()
    salida = tmp_path / "informe.csv"
    archivos.guardar.append(salida)
    v._accion_informe_csv.trigger()
    qtbot.waitUntil(salida.exists, timeout=3000)
    texto = salida.read_text(encoding="utf-8-sig")
    assert "web-01" in texto and "web-03" in texto
    assert "UPID:" not in texto  # CA-C14.2
    assert archivos.pedidos_guardar[0][1].endswith(".csv")
