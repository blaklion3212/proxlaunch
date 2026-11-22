"""Importación de CSV desde la interfaz con las columnas de la fase B (0.7.0).

Derivadas de docs/requisitos/fase-b.md: V-B60 con ``encender_base`` (arquitectura §12 y §14),
V-B39 (cloud-init con origen que no es clonar) y RF-B6.5 (la contraseña de una celda nunca se
muestra ni se registra). El centinela de contraseña es ``S3cr3t-Prueba!``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from proxlaunch.interfaz import textos
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv, leer_e_interpretar
from proxlaunch.interfaz.modelos_tabla_csv import ModeloVistaPreviaCsv
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila, OpcionesCsv
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO

from .apoyo import inventario_cluster
from .apoyo_fase_b import CENTINELA
from .apoyo_mvp3 import escribir_csv

BASE = ["nombre", "nucleos", "memoria", "disco", "almacenamiento", "red"]
FILA = ["web-01", 2, "2 GiB", "20 GiB", "local-lvm", "vmbr0"]


def perfiles():
    return perfiles_fabrica(textos.textos_perfiles_fabrica())


def csv_con(tmp_path: Path, columnas: list[str], valores: list) -> Path:
    return escribir_csv(tmp_path / "f.csv", [BASE + columnas, FILA + valores])


def interpretar(ruta: Path, encender_base: bool | None):
    todos = perfiles()
    base = next(p for p in todos if p.id == ID_PREDETERMINADO)
    return leer_e_interpretar(
        ruta,
        OpcionesCsv(),
        base,
        todos,
        inventario_cluster(),
        None,
        textos.alias_columnas_csv(),
        encender_base,
    )


def reglas(fila) -> list[str]:
    return [p.regla for p in fila.problemas]


# --- V-B60: esperar la IP exige encender ---


def test_v_b60_una_fila_con_esperar_ip_y_sin_encender_en_el_formulario_da_error(tmp_path):
    _, res = interpretar(csv_con(tmp_path, ["esperar_ip"], ["sí"]), encender_base=False)
    fila = res.filas[0]
    assert fila.estado == EstadoFila.CON_ERROR
    assert reglas(fila) == ["V-B60"]


def test_v_b60_con_encender_marcado_en_el_formulario_la_fila_es_correcta(tmp_path):
    _, res = interpretar(csv_con(tmp_path, ["esperar_ip"], ["sí"]), encender_base=True)
    assert res.filas[0].estado == EstadoFila.CORRECTA


def test_v_b60_si_se_desconoce_el_encendido_del_formulario_no_se_inventa_el_error(tmp_path):
    _, res = interpretar(csv_con(tmp_path, ["esperar_ip"], ["sí"]), encender_base=None)
    assert res.filas[0].estado == EstadoFila.CORRECTA


def test_v_b60_una_celda_encender_en_la_fila_manda_sobre_el_formulario(tmp_path):
    # El formulario enciende, pero la fila dice que no: no hay IP que esperar.
    _, no = interpretar(csv_con(tmp_path, ["encender", "esperar_ip"], ["no", "sí"]), True)
    assert reglas(no.filas[0]) == ["V-B60"]
    # El formulario no enciende, pero la fila sí: vale.
    _, si = interpretar(csv_con(tmp_path, ["encender", "esperar_ip"], ["sí", "sí"]), False)
    assert si.filas[0].estado == EstadoFila.CORRECTA


def test_v_b60_el_texto_del_error_en_la_vista_previa_explica_que_hay_que_encender(tmp_path, qtbot):
    tabla, res = interpretar(csv_con(tmp_path, ["esperar_ip"], ["sí"]), encender_base=False)
    m = ModeloVistaPreviaCsv()
    m.establecer_resultado(res)
    lineas = m.lineas_de_error()
    assert len(lineas) == 1
    assert "Encender al terminar" in lineas[0]
    assert "V-B60" not in lineas[0]
    assert lineas[0] != textos.texto_generico()


def test_v_b60_sin_esperar_ip_la_fila_no_se_ve_afectada_por_el_encendido(tmp_path):
    _, res = interpretar(csv_con(tmp_path, [], []), encender_base=False)
    assert res.filas[0].estado == EstadoFila.CORRECTA


# --- El diálogo pasa el «Encender al terminar» del formulario ---


def dialogo(qtbot, *, encender_base: bool | None) -> DialogoImportarCsv:
    d = DialogoImportarCsv(
        None,
        perfiles=perfiles(),
        perfil_base_id=ID_PREDETERMINADO,
        inv=inventario_cluster(),
        nodo_referencia=None,
        lanzador=Lanzador(),
        alias_extra=textos.alias_columnas_csv(),
        encender_base=encender_base,
    )
    qtbot.addWidget(d)
    d.show()
    return d


@pytest.mark.parametrize(
    ("encender_base", "estado"),
    [(False, EstadoFila.CON_ERROR), (True, EstadoFila.CORRECTA), (None, EstadoFila.CORRECTA)],
)
def test_el_dialogo_aplica_el_encender_base_al_leer_el_archivo(
    qtbot, tmp_path, encender_base, estado
):
    d = dialogo(qtbot, encender_base=encender_base)
    d.cargar_archivo(csv_con(tmp_path, ["esperar_ip"], ["sí"]))
    qtbot.waitUntil(lambda: d.resultado is not None and not d.ocupado, timeout=5000)
    assert d.resultado.filas[0].estado == estado
    assert d.hay_errores == (estado == EstadoFila.CON_ERROR)
    assert d.puede_continuar == (estado != EstadoFila.CON_ERROR)


# --- RF-B6.5: la contraseña de una celda nunca se muestra ---


def textos_del_dialogo(d: DialogoImportarCsv) -> list[str]:
    m = d.modelo
    roles = (
        Qt.ItemDataRole.DisplayRole,
        Qt.ItemDataRole.ToolTipRole,
        Qt.ItemDataRole.AccessibleTextRole,
        Qt.ItemDataRole.StatusTipRole,
        Qt.ItemDataRole.WhatsThisRole,
        Qt.ItemDataRole.EditRole,
    )
    salida = [
        str(m.data(m.index(r, c), rol))
        for r in range(m.rowCount())
        for c in range(m.columnCount())
        for rol in roles
    ]
    salida += [lbl.text() for lbl in d.findChildren(QLabel)]
    salida += m.lineas_de_error()
    for fila in range(m.rowCount()):
        salida += m.lineas_de_problema(fila)
    return salida


def test_rf_b6_5_la_contrasena_de_una_celda_no_aparece_en_ninguna_salida_del_dialogo(
    qtbot, tmp_path, caplog
):
    caplog.set_level(logging.DEBUG)
    # Origen distinto de clonar: la fila tiene error V-B39, pero la contraseña no se muestra.
    d = dialogo(qtbot, encender_base=True)
    d.cargar_archivo(csv_con(tmp_path, ["ci_usuario", "ci_contrasena"], ["deploy", CENTINELA]))
    qtbot.waitUntil(lambda: d.resultado is not None and not d.ocupado, timeout=5000)
    d.modelo.marcar_todas(True)
    d.tabla.selectRow(0)
    for texto in textos_del_dialogo(d):
        assert CENTINELA not in texto
    assert CENTINELA not in caplog.text
    QApplication.clipboard().setText("antes")
    d.boton_copiar.click()
    assert CENTINELA not in QApplication.clipboard().text()


def test_rf_b6_5_los_valores_originales_de_la_fila_enmascaran_la_columna_secreta(tmp_path):
    _, res = interpretar(
        csv_con(tmp_path, ["ci_usuario", "ci_contrasena"], ["deploy", CENTINELA]), True
    )
    fila = res.filas[0]
    assert fila.originales["ci_usuario"] == "deploy"
    assert fila.originales["ci_contrasena"] != CENTINELA
    assert CENTINELA not in repr(fila)
    assert CENTINELA not in repr(res)


def test_rf_b6_5_la_tabla_leida_no_expone_la_contrasena_en_su_repr(tmp_path):
    tabla, _ = interpretar(
        csv_con(tmp_path, ["ci_usuario", "ci_contrasena"], ["deploy", CENTINELA]), True
    )
    assert CENTINELA not in repr(tabla)
