"""Correcciones de seguridad S-a, S-b y S-c del MVP 3 (fase 6), por la interfaz pública.

S-a: los tooltips con texto de terceros (descripción de un perfil, errores de un archivo, celdas de
un CSV) se escapan: Qt los muestra como texto, nunca como HTML. S-b: el informe del lote se
escribe de forma atómica con permisos 0600, sin temporales, y los errores salen como E-M08
legibles. S-c: el motivo «credencial» de E-M08 nombra el campo con palabras llanas y nunca
repite el valor.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QFileDialog

from proxlaunch.interfaz import informe_lote as il
from proxlaunch.interfaz.dialogos.guardar_lote import DialogoGuardarLote
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv
from proxlaunch.interfaz.dialogos.importar_perfiles import DialogoImportarPerfiles
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.textos import texto_error, texto_fallo, textos_perfiles_fabrica
from proxlaunch.interfaz.vistas.selector_perfil import SelectorPerfil
from proxlaunch.nucleo.archivos.esquema import ErrorCampo, MotivoCampo
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import ArchivoPerfiles, PerfilInvalido

from . import test_ventana_principal as _base
from .apoyo import upid_de
from .apoyo_lote import entrada, informe_de
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import cierre_sin_preguntar_al_terminar, conectar3, escribir
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_mvp3_filas_csv import csv_de, fila
from .test_mvp3_perfiles_gestor import config_propia
from .test_ventana_principal import esperar_validacion

entorno = _base.entorno  # fixture base de la ventana

HTML_HOSTIL = "<b>x</b><img src=x>"
ESCAPADO = "&lt;b&gt;x&lt;/b&gt;&lt;img src=x&gt;"
posix = pytest.mark.skipif(os.name != "posix", reason="los permisos 0o600/0o700 son de POSIX")


def texto_que_mostraria_qt(tooltip: str) -> str:
    """El texto que Qt dibujaría para ese tooltip (interpretado como HTML si lo es)."""
    doc = QTextDocument()
    doc.setHtml(tooltip)
    return doc.toPlainText()


def es_seguro(tooltip: object) -> bool:
    return (
        isinstance(tooltip, str)
        and "<img" not in tooltip
        and "<b>" not in tooltip
        and ESCAPADO in tooltip
        and HTML_HOSTIL in texto_que_mostraria_qt(tooltip)  # se ve literal, no se interpreta
    )


# --- S-a: tooltips con texto de terceros ------------------------------------------------------


def test_s_a_el_tooltip_del_selector_de_perfiles_escapa_la_descripcion(qapp, tmp_path):
    almacen = AlmacenPerfilesMaquina(
        tmp_path / "perfiles_maquina.json",
        fabrica=perfiles_fabrica(textos_perfiles_fabrica()),
        app_version="0.1.0",
    )
    almacen.cargar()
    perfil = almacen.crear("Importado", HTML_HOSTIL, config_propia())
    selector = SelectorPerfil()
    selector.establecer_perfiles(almacen.todos(), None)
    i = selector.combo.findData(perfil.id)
    tooltip = selector.combo.itemData(i, Qt.ItemDataRole.ToolTipRole)
    assert es_seguro(tooltip)
    assert tooltip.startswith("<qt>")  # fuerza texto enriquecido, ya escapado
    assert "3" in texto_que_mostraria_qt(tooltip)  # el resumen del perfil no se perdió


def test_s_a_una_descripcion_de_varias_lineas_conserva_los_saltos(qapp, tmp_path):
    almacen = AlmacenPerfilesMaquina(
        tmp_path / "p.json",
        fabrica=perfiles_fabrica(textos_perfiles_fabrica()),
        app_version="0.1.0",
    )
    almacen.cargar()
    perfil = almacen.crear("Dos líneas", "uno\ndos & tres", config_propia())
    selector = SelectorPerfil()
    selector.establecer_perfiles(almacen.todos(), None)
    tooltip = selector.combo.itemData(
        selector.combo.findData(perfil.id), Qt.ItemDataRole.ToolTipRole
    )
    visto = texto_que_mostraria_qt(tooltip)
    assert "uno\ndos & tres" in visto and "&amp;" in tooltip


def test_s_a_el_tooltip_de_un_perfil_invalido_al_importar_escapa_el_texto_del_archivo(qtbot):
    invalido = PerfilInvalido(
        0,
        None,
        (ErrorCampo(HTML_HOSTIL, MotivoCampo.TIPO),),  # ruta con texto del archivo
    )
    d = DialogoImportarPerfiles(ArchivoPerfiles((), (invalido,), ()), [])
    qtbot.addWidget(d)
    columna_estado = 3
    tooltip = d.modelo.data(d.modelo.index(0, columna_estado), Qt.ItemDataRole.ToolTipRole)
    assert es_seguro(tooltip)


def test_s_a_los_tooltips_de_la_vista_previa_csv_escapan_el_valor_de_la_celda(
    qtbot, entorno3, modales, archivos, tmp_path
):
    v = entorno3.ventana
    ruta = csv_de(tmp_path, fila("web-01", nucleos=HTML_HOSTIL))
    archivos.abrir.append(ruta)
    vistos: dict[str, list[str]] = {"celdas": [], "estado": []}

    def _ver(d: DialogoImportarCsv) -> None:
        qtbot.waitUntil(lambda: not d.ocupado and d.resultado is not None, timeout=5000)
        m = d.modelo
        for col in range(m.columnCount()):
            tip = m.data(m.index(0, col), Qt.ItemDataRole.ToolTipRole)
            if isinstance(tip, str) and "x" in tip and "src=x" in texto_que_mostraria_qt(tip):
                vistos["celdas"].append(tip)
        d.reject()

    modales.responder(DialogoImportarCsv, _ver)
    v._accion_importar_csv.trigger()
    # Tanto la celda con error como la columna de estado repiten el valor en su tooltip.
    assert len(vistos["celdas"]) >= 2
    assert all(es_seguro(t) for t in vistos["celdas"])


# --- S-b: informe del lote ---------------------------------------------------------------------


def _informe():
    from proxlaunch.nucleo.lote.modelos import EstadoMV

    return informe_de((entrada(0, EstadoMV.OK, upid=upid_de(101)),))


def _modo(ruta: Path) -> int:
    return stat.S_IMODE(ruta.stat().st_mode)


@posix
def test_s_b_el_informe_se_escribe_con_permisos_0600_y_sin_temporales(tmp_path):
    ruta = tmp_path / "informe.txt"
    il.escribir_informe(ruta, "Máquina «ñ» ✓\n")
    assert _modo(ruta) == 0o600
    assert ruta.read_text(encoding="utf-8") == "Máquina «ñ» ✓\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["informe.txt"]  # ni *.tmp ni restos


@posix
def test_s_b_sobrescribir_un_informe_amplio_lo_deja_en_0600_sin_temporales(tmp_path):
    ruta = tmp_path / "informe.txt"
    ruta.write_text("viejo", encoding="utf-8")
    os.chmod(ruta, 0o644)
    il.escribir_informe(ruta, "nuevo")
    assert _modo(ruta) == 0o600 and ruta.read_text(encoding="utf-8") == "nuevo"
    assert list(tmp_path.glob("*.tmp")) == [] and len(list(tmp_path.iterdir())) == 1


@posix
def test_s_b_una_carpeta_nueva_se_crea_privada(tmp_path):
    ruta = tmp_path / "nueva" / "informe.txt"
    il.escribir_informe(ruta, "x")
    assert _modo(ruta.parent) == 0o700 and _modo(ruta) == 0o600


@posix
def test_s_b_una_carpeta_existente_elegida_por_el_usuario_no_cambia_de_permisos(tmp_path):
    carpeta = tmp_path / "compartida"
    carpeta.mkdir()
    os.chmod(carpeta, 0o755)
    ruta = carpeta / "informe.txt"
    il.escribir_informe(ruta, "x")
    assert _modo(carpeta) == 0o755  # no se toca lo que el usuario eligió
    assert _modo(ruta) == 0o600


def test_s_b_un_destino_imposible_lanza_un_error_de_la_aplicacion_y_no_deja_restos(tmp_path):
    carpeta = tmp_path / "destino"
    carpeta.mkdir()  # un directorio donde debería ir el archivo
    with pytest.raises(ErrorProxLaunch) as e:
        il.escribir_informe(carpeta, "x")
    assert e.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE  # E-M08
    assert list(carpeta.iterdir()) == [] and list(tmp_path.glob("*.tmp")) == []


def test_s_b_la_carpeta_nueva_que_no_se_puede_crear_da_error_de_la_aplicacion(tmp_path):
    archivo = tmp_path / "es-un-archivo"
    archivo.write_text("x", encoding="utf-8")
    with pytest.raises(ErrorProxLaunch) as e:
        il.escribir_informe(archivo / "informe.txt", "x")
    assert e.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


def test_s_b_el_dialogo_del_informe_muestra_el_error_e_m08_en_lugar_de_lanzarlo(
    qtbot, monkeypatch, tmp_path
):
    archivo = tmp_path / "es-un-archivo"
    archivo.write_text("x", encoding="utf-8")
    destino = archivo / "informe.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
    d = DialogoInforme(_informe(), tmp_path)
    qtbot.addWidget(d)
    d.boton_guardar.click()  # una excepción aquí fallaría la prueba (pytest-qt)
    assert "No se pudo guardar el archivo" in d._estado.text()
    assert "No se cambió nada" in d._estado.text()


def test_s_b_el_dialogo_del_informe_guarda_bien_y_lo_dice(qtbot, monkeypatch, tmp_path):
    destino = tmp_path / "ok.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
    d = DialogoInforme(_informe(), tmp_path)
    qtbot.addWidget(d)
    d.boton_guardar.click()
    assert destino.read_text(encoding="utf-8") == d.texto
    assert d._estado.text() == f"Guardado en {destino}"


def test_s_b_cancelar_el_selector_no_escribe_nada(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    d = DialogoInforme(_informe(), tmp_path)
    qtbot.addWidget(d)
    d.boton_guardar.click()
    assert list(tmp_path.iterdir()) == [] and d._estado.text() == ""


def test_s_b_el_informe_parcial_devuelve_none_si_el_escritor_falla_con_error_de_la_aplicacion(
    tmp_path, monkeypatch
):
    def _falla(*_a, **_k):
        raise ErrorProxLaunch(CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "sin_espacio"})

    monkeypatch.setattr(il, "escribir_atomico", _falla)
    assert il.guardar_informe_parcial(_informe(), tmp_path / "informes") is None


def test_s_b_el_informe_parcial_devuelve_none_si_la_carpeta_no_se_puede_crear(tmp_path):
    bloqueo = tmp_path / "bloqueo"
    bloqueo.write_text("x", encoding="utf-8")
    assert il.guardar_informe_parcial(_informe(), bloqueo / "informes") is None


@posix
def test_s_b_el_informe_parcial_correcto_sigue_siendo_0600_y_sin_temporales(tmp_path):
    carpeta = tmp_path / "informes"
    ruta = il.guardar_informe_parcial(_informe(), carpeta)
    assert ruta is not None and _modo(ruta) == 0o600
    assert not [p for p in carpeta.iterdir() if p.suffix == ".tmp"]


# --- S-c: E-M08 «credencial» con el nombre del campo, nunca el valor ----------------------------

CAMPOS = [
    ("tipo_cpu", "tipo de CPU"),
    ("storage_efi", "almacenamiento del disco EFI"),
    ("storage", "almacenamiento"),
    ("bridge", "puente de red"),
    ("nombre_fila", "nombre de la máquina"),
    ("nodo", "nodo"),
    ("nombre", "nombre"),
]
SECRETO = "ana@pve!lab=0123456789abcdef-SECRETO"


@pytest.mark.parametrize(("tecnico", "legible"), CAMPOS)
def test_s_c_el_mensaje_nombra_el_campo_en_lenguaje_llano_y_no_repite_el_valor(tecnico, legible):
    error = ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_GUARDABLE,
        {"motivo": "credencial", "campo": tecnico, "valor": SECRETO},
    )
    for texto in (texto_error(error), texto_fallo(error)):
        assert f"«{legible}»" in texto
        assert "credencial" in texto
        assert SECRETO not in texto and "SECRETO" not in texto
        assert f"«{tecnico}»" not in texto or tecnico == legible  # no se muestra el identificador


def test_s_c_un_campo_desconocido_se_muestra_con_su_nombre_tecnico():
    error = ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_GUARDABLE,
        {"motivo": "credencial", "campo": "campo_raro", "valor": SECRETO},
    )
    texto = texto_error(error)
    assert "«campo_raro»" in texto and SECRETO not in texto


def test_s_c_los_otros_motivos_de_e_m08_no_cambian():
    texto = texto_error(
        ErrorProxLaunch(CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "sin_espacio"})
    )
    assert texto == "No se pudo guardar el archivo: no hay espacio en el disco. No se cambió nada."
    assert "credencial" not in texto


def test_s_c_guardar_un_lote_con_una_credencial_en_el_prefijo_avisa_sin_repetir_el_valor(
    request, qtbot, entorno3, modales, archivos, tmp_path
):
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    cierre_sin_preguntar_al_terminar(request, v)  # aislado del defecto de la prueba siguiente
    escribir(v.bloque_lote.cantidad, "2")
    escribir(v.bloque_lote.prefijo, SECRETO)
    esperar_validacion(qtbot, v)

    def _aceptar(d: DialogoGuardarLote) -> None:
        d.campo_nombre.setText("lote de prueba")
        d.boton_aceptar.click()

    modales.responder(DialogoGuardarLote, _aceptar)
    destino = tmp_path / "con-credencial.proxlaunch-lote.json"
    archivos.guardar.append(destino)
    v._accion_guardar_lote.trigger()
    qtbot.waitUntil(lambda: bool(v._errores_sesion), timeout=4000)
    texto = " ".join(v._errores_sesion) + v.statusBar().currentMessage()
    assert "credencial" in texto and "No se guardó" in texto
    assert SECRETO not in texto and "SECRETO" not in texto and "0123456789" not in texto
    assert not destino.exists()  # nada se escribió con la credencial


def test_s_c_el_dialogo_de_guardar_lote_no_deja_aceptar_un_nombre_con_credencial(
    qtbot, entorno3, modales, archivos
):
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    estado: dict[str, bool] = {}

    def _probar(d: DialogoGuardarLote) -> None:
        d.campo_nombre.setText(SECRETO)
        estado["acepta"] = d.boton_aceptar.isEnabled()

    modales.responder(DialogoGuardarLote, _probar)
    v._accion_guardar_lote.trigger()
    assert estado == {"acepta": False}
    assert archivos.pedidos_guardar == []


def test_s_c_un_texto_con_forma_de_credencial_no_rompe_la_comprobacion_de_cambios_sin_guardar(
    request, qtbot, entorno3
):
    """El formulario puede contener cualquier texto: la pregunta «¿Guardar el lote?» no debe fallar
    (y, por tanto, el cierre de la ventana tampoco) solo porque el prefijo parezca un token."""
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    cierre_sin_preguntar_al_terminar(request, v)  # que el cierre automático no repita el fallo
    escribir(v.bloque_lote.cantidad, "2")
    escribir(v.bloque_lote.prefijo, SECRETO)
    esperar_validacion(qtbot, v)
    assert v._hay_cambios_sin_guardar() is True  # no debe lanzar ErrorProxLaunch
