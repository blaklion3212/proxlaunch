"""INV-O6 / RNF-O06: una URL con credenciales en la celda «fuente» del CSV no se muestra jamás.

La importación enseña la vista previa, los tooltips, el detalle de fila, los errores copiados, el
CSV de «filas con error» y el registro. Ninguno puede contener la clave ni el token de la URL.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv

from . import test_ventana_principal as _base
from .apoyo_mvp3 import ENCABEZADO_CSV, conectar3, escribir_csv
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_mvp3_filas_csv import _abrir_asistente

entorno = _base.entorno  # fixture base de la ventana

URL = "https://u:clave-secreta@x.org/a.iso?token=T0K3N"
SECRETOS = ("clave-secreta", "T0K3N")


def _todos_los_textos_del_modelo(d: DialogoImportarCsv) -> list[str]:
    m = d.modelo
    roles = (
        Qt.ItemDataRole.DisplayRole,
        Qt.ItemDataRole.ToolTipRole,
        Qt.ItemDataRole.AccessibleTextRole,
        Qt.ItemDataRole.StatusTipRole,
        Qt.ItemDataRole.WhatsThisRole,
    )
    textos = []
    for r in range(m.rowCount()):
        for c in range(m.columnCount()):
            for rol in roles:
                textos.append(str(m.data(m.index(r, c), rol)))
    return textos


def test_inv_o6_la_url_de_la_celda_fuente_no_aparece_en_ninguna_salida_de_la_importacion(
    qtbot, entorno3, modales, archivos, tmp_path, caplog
):
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    filas = [
        [*ENCABEZADO_CSV, "origen", "fuente"],
        ["web-01", 2, "2 GiB", "20 GiB", "local-lvm", "vmbr0", "", "", "iso", URL],
        ["web-02", 2, "2 GiB", "20 GiB", "local-lvm", "vmbr0", "", "", "iso", URL + "#frag"],
    ]
    ruta = escribir_csv(tmp_path / "con-url.csv", filas)
    salida = tmp_path / "errores.csv"
    archivos.guardar.append(salida)
    vistos: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        assert d.resultado is not None and d.resultado.filas
        textos = _todos_los_textos_del_modelo(d)
        for fila in range(d.modelo.rowCount()):
            textos.append(d._texto_detalle(fila))
        textos.extend(d.modelo.lineas_de_error())
        textos.extend(lbl.text() + "|" + lbl.toolTip() for lbl in d.findChildren(QLabel))
        d.boton_copiar.click()
        textos.append(QApplication.clipboard().text())
        if d.hay_errores:
            d.boton_errores.click()
            qtbot.waitUntil(salida.exists, timeout=3000)
            vistos["errores_csv"] = salida.read_text(encoding="utf-8-sig")
        vistos["textos"] = textos
        d.reject()

    with caplog.at_level(logging.DEBUG):
        _abrir_asistente(qtbot, v, modales, archivos, ruta, _ver)
    assert vistos["textos"], "la vista previa no mostró nada"
    assert "x.org/a.iso" in vistos["errores_csv"]  # el CSV de errores sí se generó
    unido = "\n".join(vistos["textos"]) + "\n" + vistos.get("errores_csv", "")  # type: ignore[arg-type]
    unido += "\n" + caplog.text
    for secreto in SECRETOS:
        assert secreto not in unido
    # La fuente sí se identifica por host/archivo (sin credenciales ni consulta).
    assert "x.org" in unido
