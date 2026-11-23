"""Diálogo «Lotes en el servidor» (fase C, C1) con un clúster simulado y el núcleo real.

Requisitos: RF-C1.1 (CA-C1.1.2, CA-C1.1.3), RF-C1.2, RF-C1.3, RF-C1.4, RF-C1.5, RF-C1.6, RF-C1.7,
RF-C1.8 (PC-1 doble control: etiquetas + nota + código escrito), RF-C1.9 (CA-C1.9.2, CA-C1.9.3),
RF-C1.10 (CA-C1.10.1, CA-C1.10.3), RF-C1.12 (CA-C1.12.2, CA-C1.12.3), RF-C1.13 (CA-C1.13.1),
V-C01, V-C02, V-C06, V-C07, V-C09 y CL-C23. Doble: ``ClusterInventario`` (nunca un servidor real);
los trabajadores son los reales y se esperan con ``qtbot``.
"""

from __future__ import annotations

import threading

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from nucleo.apoyo_fase_c_inventario import (
    CODIGO,
    OTRO_CODIGO,
    Mundo,
    etiquetas_lote,
    nota_origen,
)
from nucleo.apoyo_lote import NORMAL, error_http
from proxlaunch.interfaz.dialogos.confirmar_deshacer import DialogoConfirmarDeshacerForzado
from proxlaunch.interfaz.dialogos.inventario_lotes import (
    DialogoConfirmarCodigoLote,
    DialogoInventarioLotes,
)
from proxlaunch.interfaz.textos_inventario import (
    texto_abierto_en_sesion,
    texto_demasiadas_marcadas,
    texto_lote_abierto_en_sesion,
    texto_ninguna_deshacible,
    texto_sin_lotes_visibles,
)
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.opciones.disponibilidad_c import disponibilidad_fase_c
from proxlaunch.nucleo.opciones.modelos import OpcionC

from nucleo.apoyo_fase_c_inventario import permisos as hacer_permisos  # isort: skip

MAC = "AA:BB:CC:DD:EE:01"
COL_NOMBRE, COL_VMID, COL_NODO, COL_ESTADO, COL_BLOQUEO = 0, 1, 2, 3, 4
COL_NOTA, COL_IP, COL_MOTIVO = 7, 8, 9
COL_L_CODIGO, COL_L_MAQUINAS, COL_L_DESHACIBLES, COL_L_FECHA, COL_L_AVISO = 0, 1, 2, 3, 4


class Banco:
    """Diálogo + mundo + lanzador, con ayudas para esperar y leer lo que la interfaz muestra."""

    def __init__(self, qtbot, m: Mundo, *, en_sesion=None, estado_ip=None, permisos=None):
        self.qtbot = qtbot
        self.m = m
        self.en_sesion: set[str] = set(en_sesion or ())
        self.lanzador = Lanzador()
        self.dialogo = DialogoInventarioLotes(
            sesion=m.sesion,
            reloj=m.reloj,
            lanzador=self.lanzador,
            permisos=permisos,
            lotes_de_sesion=lambda: frozenset(self.en_sesion),
            estado_ip=estado_ip,
        )
        qtbot.addWidget(self.dialogo)
        self.dialogo.show()
        self.empezados: list[str] = []
        self.terminados: list[str] = []
        self.dialogo.deshacer_empezado.connect(self.empezados.append)
        self.dialogo.deshacer_terminado.connect(self.terminados.append)
        # Peticiones recibidas hasta el fin del borrado (antes de que la lista se relea).
        self.hasta_borrado: list = []
        self.dialogo.deshacer_terminado.connect(
            lambda _c: self.hasta_borrado.extend(self.m.cluster.llamadas)
        )

    @property
    def d(self) -> DialogoInventarioLotes:
        return self.dialogo

    def abrir(self) -> Banco:
        self.d.iniciar()
        self.esperar()
        return self

    def esperar(self) -> None:
        """Espera a que no haya lecturas ni borrado en curso."""
        self.qtbot.waitUntil(
            lambda: (
                not self.d.boton_cancelar_lectura.isVisibleTo(self.d)
                and not self.d.hay_trabajo
                and not self.lanzador.hay_activos
            ),
            timeout=8000,
        )

    def elegir(self, codigo: str = CODIGO) -> Banco:
        tabla = self.d.tabla_lotes
        fila = next(
            f for f in range(tabla.rowCount()) if tabla.item(f, COL_L_CODIGO).text() == codigo
        )
        tabla.selectRow(fila)
        self.esperar()
        return self

    def comprobar(self) -> None:
        self.d.comprobar()
        self.esperar()

    def celda(self, fila: int, col: int) -> str:
        return self.d.tabla_detalle.item(fila, col).text()

    def fila_de(self, vmid: int) -> int:
        tabla = self.d.tabla_detalle
        return next(
            f for f in range(tabla.rowCount()) if tabla.item(f, COL_VMID).text() == str(vmid)
        )

    def marcada(self, vmid: int) -> bool:
        item = self.d.tabla_detalle.item(self.fila_de(vmid), COL_NOMBRE)
        return bool(item.flags() & Qt.ItemFlag.ItemIsUserCheckable) and (
            item.checkState() == Qt.CheckState.Checked
        )

    def marcar(self, vmid: int, valor: bool) -> None:
        item = self.d.tabla_detalle.item(self.fila_de(vmid), COL_NOMBRE)
        item.setCheckState(Qt.CheckState.Checked if valor else Qt.CheckState.Unchecked)

    def esperar_dialogo(self, tipo):
        self.qtbot.waitUntil(lambda: bool(self.d.findChildren(tipo)), timeout=8000)
        return self.d.findChildren(tipo)[-1]

    def deshacer_hasta_codigo(self) -> DialogoConfirmarCodigoLote:
        self.d.boton_deshacer.click()
        return self.esperar_dialogo(DialogoConfirmarCodigoLote)

    def confirmar_y_esperar(self, codigo_escrito: str = CODIGO.upper()) -> None:
        dialogo = self.deshacer_hasta_codigo()
        dialogo.campo.setText(codigo_escrito)
        assert dialogo.boton_borrar.isEnabled()
        dialogo.boton_borrar.click()
        self.qtbot.waitUntil(lambda: bool(self.terminados), timeout=8000)
        self.esperar()


def _mundo(*vmids: int, **kw) -> Mundo:
    m = Mundo(kw.pop("nodos", ("pve1",)))
    for vmid in vmids:
        m.cluster.agregar_mv(vmid, **kw)
    return m


@pytest.fixture
def banco(qtbot):
    def _crear(m: Mundo, **kw) -> Banco:
        return Banco(qtbot, m, **kw)

    return _crear


# --- RF-C1.1: apertura --------------------------------------------------------------------------


def test_ca_c1_1_2_sin_maquinas_visibles_el_dialogo_abre_y_muestra_v_c01(banco):
    b = banco(Mundo()).abrir()
    assert b.d.estado.text() == texto_sin_lotes_visibles()
    assert "VM.Audit" in b.d.estado.text()
    assert b.d.tabla_lotes.rowCount() == 0
    assert not b.d.boton_deshacer.isEnabled() and not b.d.boton_exportar.isEnabled()


def test_ca_c1_1_2_con_maquinas_pero_sin_lotes_no_dice_que_no_ve_nada(banco):
    b = banco(_mundo(101, lote=None, nota=False)).abrir()
    assert "VM.Audit" not in b.d.estado.text() and "1" in b.d.estado.text()
    assert b.d.tabla_lotes.rowCount() == 0


def test_ca_c1_1_3_durante_la_lectura_hay_cancelar_y_el_resultado_tardio_se_descarta(banco):
    m = _mundo(101)
    puerta = threading.Event()
    m.cluster.regla("GET", r"^/cluster/resources$", lambda _ll: puerta.wait(5) and NORMAL)
    b = banco(m)
    b.d.iniciar()
    try:
        assert b.d.boton_cancelar_lectura.isVisibleTo(b.d)  # el hilo de la interfaz sigue libre
        assert not b.d.boton_comprobar.isEnabled()
        b.d.boton_cancelar_lectura.click()
        assert not b.d.boton_cancelar_lectura.isVisibleTo(b.d)
        assert b.d.boton_comprobar.isEnabled()
    finally:
        puerta.set()
    b.qtbot.waitUntil(lambda: not b.lanzador.hay_activos, timeout=8000)
    assert b.d.tabla_lotes.rowCount() == 0  # el resultado llegó tarde y se ignoró


def test_ca_c1_1_3_un_error_de_lectura_se_muestra_y_se_puede_reintentar(banco):
    m = _mundo(101)
    m.cluster.regla("GET", r"^/cluster/resources$", error_http(500, "fallo"), veces=1)
    b = banco(m).abrir()
    assert b.d.estado.property("aviso") is True and b.d.tabla_lotes.rowCount() == 0
    b.comprobar()
    assert b.d.tabla_lotes.rowCount() == 1


# --- RF-C1.2: lista de lotes --------------------------------------------------------------------


def test_ca_c1_2_1_la_lista_muestra_codigo_numero_de_maquinas_y_el_resto_sin_leer(banco):
    m = _mundo(101, 102, 103)
    m.cluster.agregar_mv(104, etiquetas=f"lote-{CODIGO}")
    m.cluster.agregar_mv(105, lote=None, nota=False)
    b = banco(m).abrir()
    t = b.d.tabla_lotes
    assert t.rowCount() == 1
    assert t.item(0, COL_L_CODIGO).text() == CODIGO and t.item(0, COL_L_MAQUINAS).text() == "4"
    assert t.item(0, COL_L_DESHACIBLES).text() == "sin leer"  # no se lee el detalle al listar
    assert t.item(0, COL_L_FECHA).text() == "sin leer"
    assert m.cluster.lecturas_config == []


def test_ca_c1_2_4_un_codigo_no_valido_se_avisa_con_v_c02_y_sus_maquinas_no_se_borran(banco):
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas="proxlaunch;lote-prueba", nota=nota_origen("prueba"))
    b = banco(m).abrir()
    assert "prueba" in b.d.tabla_lotes.item(0, COL_L_AVISO).text()
    assert "8 caracteres" in b.d.tabla_lotes.item(0, COL_L_AVISO).text()
    b.elegir("prueba")
    assert "No se puede deshacer desde aquí" in b.celda(0, COL_MOTIVO)
    assert not b.marcada(101) and not b.d.boton_deshacer.isEnabled()
    assert b.d.boton_deshacer.toolTip() == texto_ninguna_deshacible()


def test_ca_c1_2_un_lote_sin_proxlaunch_en_sus_etiquetas_se_avisa_como_no_parece_de_proxlaunch(
    banco,
):
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas=f"lote-{CODIGO}", nota=False)
    b = banco(m).abrir()
    assert "No parece creado por ProxLaunch" in b.d.tabla_lotes.item(0, COL_L_AVISO).text()


def test_ca_c1_2_6_la_busqueda_filtra_la_lista_por_nombre_de_maquina_o_codigo(banco):
    m = Mundo()
    m.cluster.agregar_mv(101, "web-01", lote="aaaaaaaa")
    m.cluster.agregar_mv(102, "db-01", lote="bbbbbbbb")
    b = banco(m).abrir()
    assert b.d.tabla_lotes.rowCount() == 2
    b.d.busqueda.setText("web")
    assert [b.d.tabla_lotes.item(f, 0).text() for f in range(b.d.tabla_lotes.rowCount())] == [
        "aaaaaaaa"
    ]
    b.d.busqueda.setText("bbbb")
    assert b.d.tabla_lotes.item(0, 0).text() == "bbbbbbbb"
    b.d.busqueda.setText("nada-de-nada")
    assert b.d.tabla_lotes.rowCount() == 0 and "coincide" in b.d.estado.text()
    b.d.busqueda.setText("")
    assert b.d.tabla_lotes.rowCount() == 2
    assert m.cluster.escrituras == []


def test_ca_c1_9_3_el_texto_de_limitacion_es_visible_sin_pasar_el_raton(banco):
    b = banco(Mundo()).abrir()
    assert b.d.texto_limitacion.isVisibleTo(b.d)
    assert "Seguir sin etiquetas" in b.d.texto_limitacion.text()
    assert b.d.texto_limitacion.textFormat() == Qt.TextFormat.PlainText


# --- RF-C1.3 / RF-C1.4: detalle -----------------------------------------------------------------


def test_ca_c1_3_1_elegir_un_lote_lee_una_config_por_maquina_y_rellena_la_tabla(banco):
    m = _mundo(101, 102, 103)
    m.cluster.agregar_mv(201, lote=OTRO_CODIGO)
    b = banco(m).abrir().elegir()
    assert sorted(m.cluster.lecturas_config) == [("pve1", 101), ("pve1", 102), ("pve1", 103)]
    assert b.d.tabla_detalle.rowCount() == 3
    assert b.celda(0, COL_NOTA) == "coincide" and b.celda(0, COL_NODO) == "pve1"
    assert b.celda(0, COL_MOTIVO) == "Sí"
    assert b.d.tabla_lotes.item(0, COL_L_DESHACIBLES).text() == "3"
    assert b.d.tabla_lotes.item(0, COL_L_FECHA).text().startswith("2026-11-")


def test_ca_c1_3_2_una_mv_con_lock_backup_muestra_el_bloqueo_en_llano_y_no_se_puede_marcar(banco):
    m = _mundo(101)
    m.cluster.agregar_mv(102, lock="backup")
    b = banco(m).abrir().elegir()
    fila = b.fila_de(102)
    assert "copia de seguridad" in b.celda(fila, COL_BLOQUEO)
    assert "Está ocupada" in b.celda(fila, COL_MOTIVO)
    assert not b.marcada(102) and b.marcada(101)


def test_ca_c1_3_4_una_lectura_fallida_dice_no_se_pudo_leer_y_el_resto_sigue(banco):
    m = _mundo(101, 102)
    m.cluster.regla("GET", r"/qemu/102/config$", error_http(500, "boom"))
    b = banco(m).abrir().elegir()
    assert "No se pudo leer" in b.celda(b.fila_de(102), COL_MOTIVO)
    assert b.marcada(101) and not b.marcada(102)


def test_ca_c1_3_5_el_texto_del_servidor_se_muestra_como_texto_plano(banco):
    m = _mundo(101)
    m.cluster.fila_lista[101] = {"name": "<img src=x onerror=alert(1)>&amp;"}
    b = banco(m).abrir().elegir()
    # El núcleo sanea el nombre (BUG-C-P1-4: sin «<», «>» ni «&»); lo que queda se pinta como
    # texto plano, sin widget enriquecido.
    celda = b.celda(0, COL_NOMBRE)
    assert "img src=x" in celda and not any(c in celda for c in "<>&")
    assert b.d.tabla_detalle.cellWidget(0, COL_NOMBRE) is None


def test_ca_c1_4_1_una_mv_sin_nombre_y_con_estado_unknown_se_muestra_y_no_se_marca(banco):
    m = _mundo(101)
    m.cluster.agregar_mv(102)
    m.cluster.lista_cruda = [
        {
            "vmid": 101,
            "node": "pve1",
            "type": "qemu",
            "status": "stopped",
            "tags": etiquetas_lote(),
        },
        {
            "vmid": 102,
            "node": "pve1",
            "type": "qemu",
            "status": "unknown",
            "tags": etiquetas_lote(),
        },
    ]
    b = banco(m).abrir().elegir()
    fila = b.fila_de(102)
    assert b.celda(fila, COL_NOMBRE) == "(sin nombre todavía)"
    assert "desconocido (Proxmox aún no lo informa)" in b.celda(fila, COL_ESTADO)
    assert "Comprobar" in b.celda(fila, COL_MOTIVO)
    assert not b.marcada(102)


def test_ca_c1_4_3_comprobar_con_el_estado_ya_conocido_hace_la_mv_deshacible(banco):
    m = _mundo(101)
    m.cluster.agregar_mv(102, status="unknown")
    m.cluster.fila_lista[102] = {"status": "unknown"}
    b = banco(m).abrir().elegir()
    assert not b.marcada(102)
    m.cluster.vms[102]["status"] = "stopped"
    m.cluster.fila_lista.clear()
    b.comprobar()
    assert b.celda(b.fila_de(102), COL_MOTIVO) == "Sí"
    item = b.d.tabla_detalle.item(b.fila_de(102), COL_NOMBRE)
    assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable  # ya se puede marcar


# --- RF-C1.5 / RF-C1.12: Comprobar y caché ------------------------------------------------------


def test_ca_c1_12_2_cambiar_entre_lotes_ya_leidos_no_repite_lecturas_hasta_comprobar(banco):
    m = Mundo()
    m.cluster.agregar_mv(101, lote="aaaaaaaa")
    m.cluster.agregar_mv(102, lote="bbbbbbbb")
    b = banco(m).abrir().elegir("aaaaaaaa").elegir("bbbbbbbb")
    assert sorted(m.cluster.lecturas_config) == [("pve1", 101), ("pve1", 102)]
    b.elegir("aaaaaaaa")
    b.elegir("bbbbbbbb")
    assert len(m.cluster.lecturas_config) == 2 and m.cluster.consultas_lista == 1
    b.comprobar()
    assert m.cluster.consultas_lista == 2 and len(m.cluster.lecturas_config) == 3
    assert b.d.codigo_seleccionado == "bbbbbbbb"  # se conserva la selección


def test_ca_c1_5_1_una_mv_que_desaparece_se_marca_ya_no_existe_y_se_desmarca(banco):
    m = _mundo(101, 102, 103)
    b = banco(m).abrir().elegir()
    del m.cluster.vms[102]
    b.comprobar()
    assert b.d.tabla_detalle.rowCount() == 3
    fila = b.fila_de(102)
    assert "Ya no existe" in b.celda(fila, COL_MOTIVO) and not b.marcada(102)
    assert b.marcada(101) and b.marcada(103)
    assert b.d.marcadas() == frozenset({101, 103})


def test_ca_c1_5_conserva_lo_que_el_usuario_desmarco_al_comprobar(banco):
    m = _mundo(101, 102, 103)
    b = banco(m).abrir().elegir()
    b.marcar(102, False)
    b.comprobar()
    assert b.marcada(101) and not b.marcada(102) and b.marcada(103)


def test_ca_c1_5_3_las_mvs_nuevas_con_la_misma_etiqueta_aparecen_desmarcadas(banco):
    m = _mundo(101, 102)
    b = banco(m).abrir().elegir()
    m.cluster.agregar_mv(103)
    b.comprobar()
    assert b.d.tabla_detalle.rowCount() == 3
    assert b.celda(b.fila_de(103), COL_MOTIVO) == "Sí"  # es deshacible…
    assert not b.marcada(103)  # …pero no se marca sola
    assert b.marcada(101) and b.marcada(102)
    assert b.d.tabla_lotes.item(0, COL_L_MAQUINAS).text() == "3"


def test_ca_c1_5_2_comprobar_no_emite_escrituras(banco):
    m = _mundo(101, 102)
    b = banco(m).abrir().elegir()
    b.comprobar()
    b.comprobar()
    assert m.cluster.solo_lecturas and m.cluster.escrituras == []


# --- RF-C1.12: cancelar y cerrar durante la lectura ---------------------------------------------


def test_ca_c1_12_3_cerrar_el_dialogo_durante_la_lectura_cancela_las_pendientes(banco):
    m = Mundo()
    for vmid in range(1000, 1040):
        m.cluster.agregar_mv(vmid)
    b = banco(m).abrir()
    puerta, dentro = threading.Event(), threading.Event()
    m.cluster.regla(
        "GET", r"/qemu/\d+/config$", lambda _ll: (dentro.set(), puerta.wait(5), NORMAL)[2]
    )
    b.d.tabla_lotes.selectRow(0)
    b.qtbot.waitUntil(dentro.is_set, timeout=4000)
    b.d.reject()  # cierra mientras se lee
    puerta.set()
    b.qtbot.waitUntil(lambda: not b.lanzador.hay_activos, timeout=8000)
    assert len(m.cluster.lecturas_config) < 40
    assert m.cluster.escrituras == []


def test_ca_c1_12_3_cancelar_la_lectura_del_detalle_deja_el_dialogo_usable(banco):
    m = Mundo()
    for vmid in range(1000, 1030):
        m.cluster.agregar_mv(vmid)
    b = banco(m).abrir()
    puerta, dentro = threading.Event(), threading.Event()
    m.cluster.regla(
        "GET", r"/qemu/\d+/config$", lambda _ll: (dentro.set(), puerta.wait(5), NORMAL)[2]
    )
    b.d.tabla_lotes.selectRow(0)
    b.qtbot.waitUntil(dentro.is_set, timeout=4000)
    b.d.boton_cancelar_lectura.click()
    puerta.set()
    b.qtbot.waitUntil(lambda: not b.lanzador.hay_activos, timeout=8000)
    assert "cancelada" in b.d.estado.text() and b.d.boton_comprobar.isEnabled()
    assert not b.d.boton_deshacer.isEnabled()  # sin detalle completo no se borra nada
    assert m.cluster.escrituras == []


# --- RF-C1.13: solo lectura ---------------------------------------------------------------------


def test_ca_c1_13_1_un_recorrido_completo_sin_borrar_solo_emite_get(banco, tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101, "a", status="running", agent=1, net0=f"virtio={MAC},bridge=vmbr0")
    m.cluster.agregar_mv(102, "b", protection=1)
    m.cluster.agregar_mv(103, "c", lote=OTRO_CODIGO)
    m.cluster.guion_agente(101, {"result": []})
    b = banco(m).abrir().elegir()
    b.comprobar()
    b.d.chk_ip.setChecked(True)
    ruta = tmp_path / "x.csv"
    b.d._elegir_ruta_csv = lambda _sugerido: ruta  # type: ignore[method-assign]
    b.d.chk_todos.setChecked(True)
    b.d.boton_exportar.click()
    b.esperar()
    b.d.boton_ip.click()
    b.esperar()
    b.d.boton_deshacer.click()  # solo inspecciona; no se confirma nada
    b.esperar_dialogo(DialogoConfirmarDeshacerForzado)
    assert ruta.exists()
    assert set(m.cluster.metodos) == {"GET"} and m.cluster.escrituras == []


# --- RF-C1.6: exportar --------------------------------------------------------------------------


def test_ca_c1_6_4_sin_elegir_ruta_no_se_crea_ningun_archivo_ni_se_hace_nada(banco, tmp_path):
    m = _mundo(101)
    b = banco(m).abrir().elegir()
    antes = m.cluster.metodos.total()
    b.d._elegir_ruta_csv = lambda _sugerido: None  # type: ignore[method-assign]
    b.d.boton_exportar.click()
    assert list(tmp_path.iterdir()) == [] and m.cluster.metodos.total() == antes
    assert b.d.boton_exportar.isEnabled()


def test_ca_c1_6_4_tras_elegir_ruta_se_escribe_el_csv_y_se_avisa(banco, tmp_path):
    m = _mundo(101, 102)
    b = banco(m).abrir().elegir()
    ruta = tmp_path / "salida.csv"
    nombres: list[str] = []
    b.d._elegir_ruta_csv = lambda s: (nombres.append(s), ruta)[1]  # type: ignore[method-assign]
    b.d.boton_exportar.click()
    b.esperar()
    assert nombres == [f"lote-{CODIGO}.csv"] and ruta.exists()
    assert "salida.csv" in b.d.estado.text()
    texto = ruta.read_bytes().decode("utf-8-sig")
    assert texto.count("\r\n") == 3  # encabezado + 2 filas
    assert m.cluster.escrituras == []


def test_ca_c1_6_exportar_todos_los_lotes_lee_los_que_faltan_y_los_incluye(banco, tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101, lote="aaaaaaaa")
    m.cluster.agregar_mv(102, lote="bbbbbbbb")
    b = banco(m).abrir()
    assert not b.d.boton_exportar.isEnabled()  # sin lote elegido ni «todos»
    b.d.chk_todos.setChecked(True)
    b.d._refrescar_botones()
    assert b.d.boton_exportar.isEnabled()
    ruta = tmp_path / "todos.csv"
    sugeridos: list[str] = []
    b.d._elegir_ruta_csv = lambda s: (sugeridos.append(s), ruta)[1]  # type: ignore[method-assign]
    b.d.boton_exportar.click()
    b.esperar()
    assert sugeridos == ["lotes-servidor.csv"]
    texto = ruta.read_bytes().decode("utf-8-sig")
    assert "aaaaaaaa" in texto and "bbbbbbbb" in texto
    assert m.cluster.solo_lecturas


# --- RF-C1.7: IP --------------------------------------------------------------------------------


def test_ca_c1_7_3_sin_el_privilegio_del_agente_la_casilla_y_el_boton_quedan_deshabilitados(banco):
    caps = capacidades_para(Version("8.4", 8, 4, 0), None)
    estado = disponibilidad_fase_c(hacer_permisos({"/": {"VM.Audit": 1}}), caps)[
        OpcionC.IP_INVENTARIO
    ]
    b = banco(_mundo(101), estado_ip=estado).abrir().elegir()
    assert not b.d.chk_ip.isEnabled() and not b.d.boton_ip.isEnabled()
    assert "VM.Monitor" in b.d.chk_ip.toolTip() and "VM.Monitor" in b.d.boton_ip.toolTip()
    assert b.d.boton_exportar.isEnabled()  # exportar sin IP sigue disponible


def test_ca_c1_7_3_con_9_2_el_privilegio_que_se_nombra_es_guestagent_audit(banco):
    caps = capacidades_para(Version("9.2", 9, 2, 0), None)
    estado = disponibilidad_fase_c(hacer_permisos({"/": {"VM.Audit": 1}}), caps)[
        OpcionC.IP_INVENTARIO
    ]
    b = banco(_mundo(101), estado_ip=estado).abrir().elegir()
    assert "VM.GuestAgent.Audit" in b.d.boton_ip.toolTip()


def test_ca_c1_7_1_obtener_ip_rellena_la_columna_ip_solo_en_lectura(banco):
    from nucleo.apoyo_lote import respuesta_agente

    m = Mundo()
    m.cluster.agregar_mv(101, "enc", status="running", agent=1, net0=f"virtio={MAC},bridge=vmbr0")
    m.cluster.agregar_mv(102, "apagada", status="stopped", agent=1)
    m.cluster.guion_agente(101, respuesta_agente(("eth0", MAC, ("10.0.0.5",))))
    b = banco(m).abrir().elegir()
    b.d.boton_ip.click()
    b.esperar()
    assert b.celda(b.fila_de(101), COL_IP) == "10.0.0.5"
    assert b.celda(b.fila_de(102), COL_IP) == "apagada"
    assert m.cluster.solo_lecturas


# --- RF-C1.8: lista desmarcable y botón Deshacer ------------------------------------------------


def test_ca_c1_8_1_las_borrables_salen_marcadas_y_la_sin_nota_dice_por_que_no(banco):
    m = _mundo(101, 102, 103)
    m.cluster.agregar_mv(104, nota=False)
    b = banco(m).abrir().elegir()
    assert [b.marcada(v) for v in (101, 102, 103, 104)] == [True, True, True, False]
    assert b.d.marcadas() == frozenset({101, 102, 103})
    motivo = b.celda(b.fila_de(104), COL_MOTIVO)
    assert motivo.startswith("No se puede deshacer desde aquí:") and "nota" in motivo
    assert b.d.boton_deshacer.isEnabled()
    assert not (
        b.d.tabla_detalle.item(b.fila_de(104), COL_NOMBRE).flags() & Qt.ItemFlag.ItemIsUserCheckable
    )


def test_ca_c1_8_2_una_mv_con_nota_de_otro_lote_no_es_marcable(banco):
    m = _mundo(101)
    m.cluster.agregar_mv(102, etiquetas=etiquetas_lote(), nota=nota_origen(OTRO_CODIGO))
    b = banco(m).abrir().elegir()
    assert not b.marcada(102) and OTRO_CODIGO in b.celda(b.fila_de(102), COL_MOTIVO)
    assert b.celda(b.fila_de(102), COL_NOTA) == "de otro lote"


def test_ca_c1_8_10_con_mas_de_100_marcadas_borrar_queda_deshabilitado_con_v_c09(banco):
    m = Mundo()
    for vmid in range(1000, 1101):
        m.cluster.agregar_mv(vmid)
    b = banco(m).abrir().elegir()
    assert len(b.d.marcadas()) == 101
    assert not b.d.boton_deshacer.isEnabled()
    assert b.d.boton_deshacer.toolTip() == texto_demasiadas_marcadas()
    assert b.d.motivo_deshacer.text() == texto_demasiadas_marcadas()
    b.marcar(1000, False)  # 100: ya se puede
    assert b.d.boton_deshacer.isEnabled() and b.d.motivo_deshacer.text() == ""
    b.d.boton_deshacer.click()  # solo inspecciona
    b.esperar_dialogo(DialogoConfirmarCodigoLote)
    assert m.cluster.escrituras == []


def test_ca_c1_8_10_sin_ninguna_marcada_borrar_queda_deshabilitado(banco):
    b = banco(_mundo(101)).abrir().elegir()
    b.marcar(101, False)
    assert not b.d.boton_deshacer.isEnabled() and b.d.marcadas() == frozenset()
    assert "Marca al menos una" in b.d.boton_deshacer.toolTip()


def test_ca_c1_9_2_un_lote_sin_ninguna_deshacible_deshabilita_deshacer_con_el_motivo(banco):
    m = Mundo()
    m.cluster.agregar_mv(101, nota=False)
    m.cluster.agregar_mv(102, lock="backup")
    b = banco(m).abrir().elegir()
    assert not b.d.boton_deshacer.isEnabled()
    assert b.d.boton_deshacer.toolTip() == texto_ninguna_deshacible()
    assert b.d.motivo_deshacer.text() == texto_ninguna_deshacible()
    assert b.d.boton_exportar.isEnabled() and b.d.boton_comprobar.isEnabled()


def test_ca_c1_9_1_ninguna_fila_no_deshacible_deja_el_motivo_vacio(banco):
    m = Mundo()
    m.cluster.agregar_mv(101, nota=False)
    m.cluster.agregar_mv(102, template=1)
    m.cluster.agregar_mv(103, etiquetas=f"lote-{CODIGO}")
    m.cluster.agregar_mv(104, nota=nota_origen(OTRO_CODIGO))
    m.cluster.agregar_mv(105, lock="clone")
    b = banco(m).abrir().elegir()
    for fila in range(b.d.tabla_detalle.rowCount()):
        assert b.celda(fila, COL_MOTIVO).startswith("No se puede deshacer desde aquí:")
        assert len(b.celda(fila, COL_MOTIVO)) > 40


# --- RF-C1.10: convivencia con la sesión --------------------------------------------------------


def test_ca_c1_10_1_un_lote_abierto_en_la_sesion_se_avisa_y_deshacer_queda_deshabilitado(banco):
    b = banco(_mundo(101, 102), en_sesion={CODIGO}).abrir().elegir()
    assert texto_abierto_en_sesion() in b.d.tabla_lotes.item(0, COL_L_AVISO).text()
    assert not b.d.boton_deshacer.isEnabled()
    assert b.d.boton_deshacer.toolTip() == texto_lote_abierto_en_sesion()
    assert "Lote > Deshacer" in b.d.motivo_deshacer.text()
    assert b.d.boton_exportar.isEnabled() and b.d.boton_comprobar.isEnabled()


def test_ca_c1_10_3_si_el_libro_se_cerro_el_inventario_permite_deshacer(banco):
    b = banco(_mundo(101, 102), en_sesion={CODIGO}).abrir().elegir()
    assert not b.d.boton_deshacer.isEnabled()
    b.en_sesion.clear()  # el lote de la sesión se cerró
    b.comprobar()
    assert b.d.boton_deshacer.isEnabled()
    assert texto_abierto_en_sesion() not in b.d.tabla_lotes.item(0, COL_L_AVISO).text()


def test_ca_c1_10_1_otro_lote_de_la_sesion_no_bloquea_a_este(banco):
    b = banco(_mundo(101), en_sesion={OTRO_CODIGO}).abrir().elegir()
    assert b.d.boton_deshacer.isEnabled()


def test_v_c07_si_el_lote_se_abre_en_la_sesion_mientras_se_confirma_no_se_borra(banco):
    m = _mundo(101, 102)
    b = banco(m).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    b.en_sesion.add(CODIGO)  # mientras escribe el código, el lote se abre en la sesión
    dialogo.campo.setText(CODIGO)
    dialogo.boton_borrar.click()
    b.esperar()
    assert m.cluster.deletes.total() == 0 and m.cluster.escrituras == []
    assert b.empezados == []
    assert not b.d.boton_deshacer.isEnabled()


# --- RF-C1.8 / PC-1: el doble control -----------------------------------------------------------


def test_pc1_hasta_escribir_el_codigo_solo_hay_lecturas(banco):
    m = _mundo(101, 102)
    b = banco(m).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    assert m.cluster.solo_lecturas  # la inspección es de solo lectura
    assert not dialogo.boton_borrar.isEnabled()
    dialogo.reject()
    b.esperar()
    assert m.cluster.escrituras == [] and b.empezados == []


def test_ca_c1_8_3_con_un_codigo_incorrecto_o_vacio_borrar_esta_deshabilitado_y_no_hay_delete(
    banco,
):
    m = _mundo(101, 102)
    b = banco(m).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    for escrito in ("", " ", "ab12cd3", "ab12cd35", "lote-ab12cd34", "ab12cd34x", OTRO_CODIGO):
        dialogo.campo.setText(escrito)
        assert not dialogo.boton_borrar.isEnabled(), escrito
    dialogo.boton_borrar.click()  # un clic en un botón deshabilitado no hace nada
    dialogo.accept()  # ni siquiera llamando a accept() directamente
    assert dialogo.result() != DialogoConfirmarCodigoLote.DialogCode.Accepted
    QTest.keyClick(dialogo.campo, Qt.Key.Key_Return)  # Intro es «Cancelar», no «Borrar»
    b.qtbot.wait(50)
    assert m.cluster.deletes.total() == 0 and m.cluster.escrituras == []
    assert b.empezados == []


def test_ca_c1_8_3_el_codigo_en_mayusculas_habilita_borrar_y_el_defecto_es_cancelar(
    banco,
):
    b = banco(_mundo(101)).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    assert dialogo.boton_cancelar.isDefault() and not dialogo.boton_borrar.isDefault()
    assert not dialogo.campo.text()  # el código no se rellena solo
    dialogo.campo.setText("AB12CD34")
    assert dialogo.boton_borrar.isEnabled()
    assert CODIGO in dialogo.pista.text() and CODIGO in dialogo.aviso.text()
    assert "1" in dialogo.aviso.text() and "No se puede deshacer" in dialogo.aviso.text()
    dialogo.reject()
    b.esperar()


def test_pc1_con_el_codigo_correcto_se_borran_solo_las_marcadas_y_se_informa_cada_una(banco):
    m = _mundo(101, 102, 103)
    m.cluster.agregar_mv(104, nota=False)
    b = banco(m).abrir().elegir()
    b.marcar(102, False)
    m.cluster.llamadas.clear()
    b.confirmar_y_esperar()
    assert sorted(m.cluster.deletes.elements()) == [101, 103]
    assert 102 in m.cluster.vms and 104 in m.cluster.vms
    assert not [c for c in b.hasta_borrado if "/qemu/102" in c.ruta]  # CA-C1.8.4
    assert not [c for c in b.hasta_borrado if "/qemu/104" in c.ruta]
    assert b.empezados == [CODIGO] and b.terminados == [CODIGO]
    assert b.d.resumen_resultado.text() == "2 eliminada(s)."
    assert b.d.tabla_resultado.model().rowCount() == 2
    assert not b.d.hay_trabajo and b.d.boton_cerrar.isEnabled()
    # Se relee el servidor: lo borrado desaparece de la lista.
    filas = b.d.tabla_detalle.rowCount()
    assert sorted(int(b.celda(f, COL_VMID)) for f in range(filas)) == [102, 104]
    assert b.d.tabla_lotes.item(0, COL_L_MAQUINAS).text() == "2"


def test_pc1_el_delete_del_inventario_no_lleva_purge_y_si_destroy_unreferenced_disks_0(banco):
    m = _mundo(101)
    b = banco(m).abrir().elegir()
    b.confirmar_y_esperar()
    assert m.cluster.params_delete[101] == {"destroy-unreferenced-disks": 0}


def test_cl_c23_el_doble_clic_en_borrar_definitivamente_ejecuta_una_sola_vez(banco):
    m = _mundo(101, 102)
    b = banco(m).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    dialogo.campo.setText(CODIGO)
    dialogo.boton_borrar.click()
    dialogo.boton_borrar.click()
    dialogo.boton_borrar.click()
    b.qtbot.waitUntil(lambda: bool(b.terminados), timeout=8000)
    b.esperar()
    assert b.empezados == [CODIGO]
    assert set(m.cluster.deletes.values()) == {1} and m.cluster.deletes.total() == 2


def test_cl_c23_el_doble_clic_en_deshacer_abre_una_sola_confirmacion(banco):
    b = banco(_mundo(101)).abrir().elegir()
    b.d.boton_deshacer.click()
    b.d.boton_deshacer.click()
    b.esperar_dialogo(DialogoConfirmarCodigoLote)
    b.qtbot.wait(50)
    assert len(b.d.findChildren(DialogoConfirmarCodigoLote)) == 1


def test_ca_c1_8_4_una_mv_desmarcada_no_recibe_ninguna_peticion_tras_confirmar(banco):
    m = _mundo(101, 102, 103)
    b = banco(m).abrir().elegir()
    b.marcar(103, False)
    m.cluster.llamadas.clear()
    b.confirmar_y_esperar()
    assert not [c for c in b.hasta_borrado if "103" in c.ruta]
    assert 103 in m.cluster.vms


# --- RF-C1.8: encendidas y protegidas -----------------------------------------------------------


def test_ca_c1_8_5_con_encendida_y_protegida_aparece_el_dialogo_de_la_fase_a_y_cancelar_no_escribe(
    banco,
):
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    m.cluster.agregar_mv(102, protection=1)
    m.cluster.agregar_mv(103)
    b = banco(m).abrir().elegir()
    b.d.boton_deshacer.click()
    forzado = b.esperar_dialogo(DialogoConfirmarDeshacerForzado)
    assert not b.d.findChildren(DialogoConfirmarCodigoLote)  # el código viene después
    assert "101" in forzado.aviso.text() or "web-101" in forzado.aviso.text()
    forzado.boton_cancelar.click()
    b.qtbot.wait(100)
    assert not b.d.findChildren(DialogoConfirmarCodigoLote)
    assert m.cluster.escrituras == [] and b.empezados == []


def test_ca_c1_8_5_forzar_exige_la_casilla_y_despues_pide_el_codigo_y_solo_fuerza_lo_visto(banco):
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    m.cluster.agregar_mv(102, protection=1)
    m.cluster.agregar_mv(103)
    b = banco(m).abrir().elegir()
    b.d.boton_deshacer.click()
    forzado = b.esperar_dialogo(DialogoConfirmarDeshacerForzado)
    assert not forzado.boton_forzar.isEnabled()  # sin la casilla no se puede forzar
    forzado.casilla.setChecked(True)
    assert forzado.boton_forzar.isEnabled()
    forzado.boton_forzar.click()
    codigo = b.esperar_dialogo(DialogoConfirmarCodigoLote)
    assert m.cluster.escrituras == []  # aún no se ha escrito nada
    m.cluster.vms[103]["status"] = "running"  # se enciende mientras escribe el código
    codigo.campo.setText(CODIGO)
    codigo.boton_borrar.click()
    b.qtbot.waitUntil(lambda: bool(b.terminados), timeout=8000)
    b.esperar()
    escrituras = m.cluster.escrituras
    assert ("POST", "/nodes/pve1/qemu/101/status/stop") in escrituras
    assert ("PUT", "/nodes/pve1/qemu/102/config") in escrituras
    assert not [e for e in escrituras if "/103" in e[1]]  # la que no vio, intacta
    assert sorted(m.cluster.deletes.elements()) == [101, 102]
    assert 103 in m.cluster.vms
    assert b.d.resumen_resultado.text() == "2 eliminada(s), 1 sin tocar."


def test_ca_c1_8_5_sin_forzar_las_encendidas_y_protegidas_se_omiten_y_el_resto_se_borra(banco):
    m = Mundo()
    m.cluster.agregar_mv(101, status="running")
    m.cluster.agregar_mv(102, protection=1)
    m.cluster.agregar_mv(103)
    b = banco(m).abrir().elegir()
    b.d.boton_deshacer.click()
    forzado = b.esperar_dialogo(DialogoConfirmarDeshacerForzado)
    forzado.boton_sin_forzar.click()
    codigo = b.esperar_dialogo(DialogoConfirmarCodigoLote)
    codigo.campo.setText(CODIGO)
    codigo.boton_borrar.click()
    b.qtbot.waitUntil(lambda: bool(b.terminados), timeout=8000)
    b.esperar()
    assert sorted(m.cluster.deletes.elements()) == [103]
    assert [e for e in m.cluster.escrituras if e[0] != "DELETE"] == []
    assert "2 sin tocar" in b.d.resumen_resultado.text()


def test_ca_c1_8_9_una_mv_con_lock_no_se_ofrece_para_forzar(banco):
    m = Mundo()
    m.cluster.agregar_mv(101, status="running", lock="backup")
    m.cluster.agregar_mv(102)
    b = banco(m).abrir().elegir()
    b.d.boton_deshacer.click()
    b.esperar_dialogo(DialogoConfirmarCodigoLote)  # no hay nada forzable: va directo al código
    assert not b.d.findChildren(DialogoConfirmarDeshacerForzado)


# --- CA-C1.8.6 y CA-C1.8.8 desde la interfaz ----------------------------------------------------


def test_ca_c1_8_6_una_mv_que_pasa_a_plantilla_entre_la_lista_y_el_borrado_no_se_borra(banco):
    m = _mundo(101, 102)
    b = banco(m).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    m.cluster.vms[101]["config"]["template"] = 1  # mientras lee la confirmación
    dialogo.campo.setText(CODIGO)
    dialogo.boton_borrar.click()
    b.qtbot.waitUntil(lambda: bool(b.terminados), timeout=8000)
    b.esperar()
    assert sorted(m.cluster.deletes.elements()) == [102] and 101 in m.cluster.vms
    assert "1 eliminada(s), 1 sin tocar" in b.d.resumen_resultado.text()


def test_ca_c1_8_8_un_403_en_el_primer_delete_deja_las_demas_sin_enviar_y_se_dice(banco):
    m = _mundo(101, 102, 103)
    m.cluster.regla(
        "DELETE", r"/qemu/\d+$", error_http(403, "Permission check failed (/vms/101, VM.Allocate)")
    )
    b = banco(m).abrir().elegir()
    b.confirmar_y_esperar()
    assert m.cluster.deletes.total() == 1
    assert b.d.resumen_resultado.text() == "0 eliminada(s), 2 sin tocar, 1 con error."


# --- Cierre con borrado en curso ----------------------------------------------------------------


def test_cerrar_el_dialogo_con_un_borrado_en_curso_no_lo_cierra_y_avisa(banco):
    m = _mundo(101, 102)
    puerta = threading.Event()
    m.cluster.regla("DELETE", r"/qemu/101$", lambda _ll: puerta.wait(5) and NORMAL, veces=1)
    b = banco(m).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    dialogo.campo.setText(CODIGO)
    dialogo.boton_borrar.click()
    try:
        b.qtbot.waitUntil(lambda: b.d.hay_trabajo, timeout=4000)
        assert not b.d.boton_cerrar.isEnabled()
        b.d.reject()
        assert b.d.isVisible() and "Detén el borrado" in b.d.estado.text()
        b.d.detener_borrado()
    finally:
        puerta.set()
    b.qtbot.waitUntil(lambda: bool(b.terminados), timeout=8000)
    assert m.cluster.deletes.total() <= 2


def test_detener_el_borrado_no_envia_mas_delete_a_las_pendientes(banco):
    m = _mundo(101, 102, 103)
    puerta = threading.Event()
    m.cluster.regla("DELETE", r"/qemu/101$", lambda _ll: puerta.wait(5) and NORMAL, veces=1)
    b = banco(m).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    dialogo.campo.setText(CODIGO)
    dialogo.boton_borrar.click()
    b.qtbot.waitUntil(lambda: m.cluster.deletes[101] == 1, timeout=4000)
    b.d.detener_borrado()
    puerta.set()
    b.qtbot.waitUntil(lambda: bool(b.terminados), timeout=8000)
    assert sorted(m.cluster.deletes.elements()) == [101]
    assert {102, 103} <= set(m.cluster.vms)


def test_cerrar_por_cambio_de_servidor_corta_todo_y_no_envia_mas_delete_ca_c1_14_1(banco):
    m = _mundo(101, 102, 103)
    puerta = threading.Event()
    m.cluster.regla("DELETE", r"/qemu/101$", lambda _ll: puerta.wait(5) and NORMAL, veces=1)
    b = banco(m).abrir().elegir()
    dialogo = b.deshacer_hasta_codigo()
    dialogo.campo.setText(CODIGO)
    dialogo.boton_borrar.click()
    b.qtbot.waitUntil(lambda: m.cluster.deletes[101] == 1, timeout=4000)
    b.d.cerrar_por_cambio_de_servidor()
    puerta.set()
    b.qtbot.waitUntil(lambda: bool(b.terminados), timeout=8000)
    assert sorted(m.cluster.deletes.elements()) == [101]
    assert not b.d.isVisible()


# --- V-C08, sesión caducada y texto no confiable ------------------------------------------------


def test_v_c08_sin_vm_allocate_conocido_no_se_marca_ni_se_puede_deshacer(banco):
    b = banco(_mundo(101, 102), permisos=hacer_permisos({"/": {"VM.Audit": 1}})).abrir().elegir()
    motivo = b.celda(0, COL_MOTIVO)
    assert "VM.Allocate" in motivo and "/vms/101" in motivo
    assert not b.marcada(101) and not b.d.boton_deshacer.isEnabled()
    assert b.d.boton_exportar.isEnabled()


def test_una_sesion_caducada_durante_la_lectura_avisa_a_la_ventana(banco):
    from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

    m = _mundo(101)
    m.cluster.regla("GET", r"^/cluster/resources$", ErrorProxLaunch(CodigoError.SESION_EXPIRADA))
    b = banco(m)
    with b.qtbot.waitSignal(b.d.sesion_expirada, timeout=8000) as senal:
        b.d.iniciar()
    assert senal.args[0].codigo == CodigoError.SESION_EXPIRADA
    b.esperar()
    assert b.d.estado.property("aviso") is True


def test_ca_c1_13_1_un_nodo_sin_respuesta_en_la_lista_no_deja_el_dialogo_bloqueado(banco):
    from nucleo.apoyo_lote import nodo_caido

    m = Mundo(("pve1", "pve2"))
    m.cluster.agregar_mv(101, nodo="pve1")
    m.cluster.agregar_mv(102, nodo="pve2")
    m.cluster.regla("GET", r"/nodes/pve2/", nodo_caido("pve2"))
    b = banco(m).abrir().elegir()
    assert "El servidor de pve2 no responde" in b.celda(b.fila_de(102), COL_MOTIVO)
    assert b.marcada(101) and not b.marcada(102)
    assert b.d.boton_deshacer.isEnabled() and b.d.boton_comprobar.isEnabled()


def test_rnf_c6_2_la_tabla_no_muestra_controles_ni_marcas_bidi_del_nombre(banco):
    m = _mundo(101)
    m.cluster.fila_lista[101] = {"name": "web‮10-bak\x07"}
    b = banco(m).abrir().elegir()
    texto = b.celda(0, COL_NOMBRE)
    assert "‮" not in texto and "\x07" not in texto


def test_ca_c1_8_el_borrado_no_se_decide_por_el_nombre_que_ve_el_usuario(banco):
    """Dos MVs con el mismo nombre: solo se borra la marcada, por VMID."""
    m = Mundo()
    m.cluster.agregar_mv(101, "gemela")
    m.cluster.agregar_mv(102, "gemela")
    b = banco(m).abrir().elegir()
    b.marcar(102, False)
    b.confirmar_y_esperar()
    assert sorted(m.cluster.deletes.elements()) == [101] and 102 in m.cluster.vms


def test_ca_c1_5_tras_borrar_una_mv_que_el_usuario_desmarco_sigue_desmarcada(banco):
    m = _mundo(101, 102, 103)
    b = banco(m).abrir().elegir()
    b.marcar(102, False)
    b.confirmar_y_esperar()
    assert sorted(m.cluster.deletes.elements()) == [101, 103]
    assert 102 in m.cluster.vms and not b.marcada(102)
