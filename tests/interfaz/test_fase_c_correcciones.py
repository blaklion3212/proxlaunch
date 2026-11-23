"""Correcciones de la fase C tras la revisión F5 (0.8.0): pruebas de regresión de la interfaz.

Derivadas de docs/investigacion/fase-c-errores-f5.md y docs/requisitos/fase-c.md:
BUG-C-P2-4 (CA-C2.1.3: si la lectura de las VNets de un nodo falla, la tabla de redes lo avisa
con el nodo y sigue mostrando los bridges; con lectura correcta y sin VNets sale V-C13, no el
aviso de fallo) y BUG-C-P4-1 (CA-C6.4.2: importar el CSV del inventario muestra un texto propio).
Todo sin red: solo widgets y datos del núcleo.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from proxlaunch.interfaz.textos import texto_error
from proxlaunch.interfaz.textos_c import texto_sdn_sin_leer, texto_sin_vnets
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.interfaz.vistas.tabla_redes import TablaRedes
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Bridge, RedVirtual
from proxlaunch.nucleo.modelos.vm import InterfazRed

from .apoyo_mvp4 import inv_origen

BRIDGES = (Bridge("vmbr0", "bridge", True), Bridge("vmbr1", "bridge", False))
TEXTO_FALLO = (
    "No se pudieron leer las redes virtuales (SDN) del nodo pve2; solo se muestran los bridges."
)


def textos(raiz) -> str:
    return "\n".join(
        lbl.text() for lbl in raiz.findChildren(QLabel) if lbl.isVisibleTo(raiz) and lbl.text()
    )


def _tabla(qtbot) -> TablaRedes:
    t = TablaRedes()
    qtbot.addWidget(t)
    t.show()
    return t


# --- BUG-C-P2-4: aviso cuando falla la lectura de las VNets de un nodo --------------------------


def test_bug_c_p2_4_el_texto_nombra_el_nodo_y_dice_que_solo_se_muestran_los_bridges():
    assert texto_sdn_sin_leer("pve2") == TEXTO_FALLO


def test_bug_c_p2_4_la_tabla_con_sdn_fallido_muestra_el_aviso_y_conserva_los_bridges(qtbot):
    t = _tabla(qtbot)
    t.establecer_bridges(BRIDGES, (), sdn_leido=False, sdn_fallido="pve2")
    t.establecer_redes([InterfazRed("vmbr0")])
    assert TEXTO_FALLO in textos(t)
    assert t.hay_bridges()
    assert t.redes()[0].bridge == "vmbr0"


def test_bug_c_p2_4_con_sdn_fallido_no_sale_el_texto_v_c13_de_sin_redes_virtuales(qtbot):
    t = _tabla(qtbot)
    t.establecer_bridges(BRIDGES, (), sdn_leido=False, sdn_fallido="pve2")
    visible = textos(t)
    assert "No ves ninguna red virtual" not in visible and "libpve" not in visible


def test_bug_c_p2_4_con_lectura_correcta_y_sin_vnets_sale_v_c13_y_no_el_aviso_de_fallo(qtbot):
    t = _tabla(qtbot)
    t.establecer_bridges(BRIDGES, (), sdn_leido=True, sdn_incluido=True)
    visible = textos(t)
    assert texto_sin_vnets(True) in visible
    assert "No se pudieron leer las redes virtuales" not in visible


def test_bug_c_p2_4_el_aviso_desaparece_cuando_la_lectura_siguiente_es_correcta(qtbot):
    t = _tabla(qtbot)
    t.establecer_bridges(BRIDGES, (), sdn_leido=False, sdn_fallido="pve2")
    t.establecer_bridges(BRIDGES, (RedVirtual("prod", None, False),), sdn_leido=True)
    assert "No se pudieron leer las redes virtuales" not in textos(t)


def test_bug_c_p2_4_el_formulario_con_el_fallo_de_lectura_de_un_nodo_muestra_el_aviso(qtbot):
    inv = inv_origen()
    nodo = "pve"  # el nodo de ``inv_origen``
    inv.redes_sdn = {}
    inv.errores_sdn = {nodo: ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {})}
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    visible = textos(f.tabla_redes)
    assert texto_sdn_sin_leer(nodo) in visible
    assert "No ves ninguna red virtual" not in visible
    assert f.tabla_redes.redes()[0].bridge == "vmbr0"


def test_bug_c_p2_4_el_formulario_con_lectura_correcta_sin_vnets_no_muestra_el_aviso_de_fallo(
    qtbot,
):
    inv = inv_origen()
    nodo = "pve"  # el nodo de ``inv_origen``
    inv.redes_sdn = {nodo: ()}
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    visible = textos(f.tabla_redes)
    assert "No se pudieron leer las redes virtuales" not in visible
    assert "No ves ninguna red virtual" in visible


# --- BUG-C-P4-1: texto del CSV exportado por el inventario --------------------------------------


def test_bug_c_p4_1_la_interfaz_explica_que_es_una_exportacion_de_lotes_en_el_servidor():
    texto = texto_error(ErrorProxLaunch(CodigoError.CSV_COLUMNAS, {"motivo": "inventario"}))
    assert "Este archivo es una exportación de «Lotes en el servidor»" in texto
    assert "Importar CSV" in texto
    assert "{" not in texto and "CSV_COLUMNAS" not in texto


def test_bug_c_p4_1_los_otros_motivos_de_csv_columnas_no_usan_el_texto_del_inventario():
    for motivo, params in (
        ("falta_nombre", {}),
        ("duplicada", {"columna": "vlan"}),
        ("", {"posiciones": "4"}),
    ):
        texto = texto_error(ErrorProxLaunch(CodigoError.CSV_COLUMNAS, {"motivo": motivo, **params}))
        assert "exportación de «Lotes en el servidor»" not in texto
