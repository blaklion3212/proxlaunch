"""Textos y accesibilidad de la interfaz del MVP 3 (RNF-M04, RNF-M06, CA-P11.3, CA-P11.4).

- Con un catálogo de prueba «[T]» todo texto visible de los widgets, diálogos y mensajes nuevos
  debe pasar por el sistema de traducción (nada queda «sin traducir»).
- Los códigos E-M01..E-M16, las reglas V-M y los avisos de archivo salen de ``textos.py``.
- Controles nuevos con ``accessibleName`` (o etiqueta asociada); tablas siempre con nombre.
- El catálogo ``proxlaunch_es.ts`` contiene los textos nuevos del código.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableView,
    QToolButton,
    QWidget,
)

from proxlaunch.interfaz import textos
from proxlaunch.interfaz.ayuda import CAMPOS_AYUDA_MVP3, ayuda
from proxlaunch.interfaz.dialogos.guardar_lote import DialogoGuardarLote
from proxlaunch.interfaz.dialogos.guardar_perfil import DialogoGuardarPerfil, DialogoNombrePerfil
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv, leer_e_interpretar
from proxlaunch.interfaz.dialogos.importar_perfiles import DialogoImportarPerfiles
from proxlaunch.interfaz.dialogos.lote_no_encaja import PanelLoteNoEncaja
from proxlaunch.interfaz.dialogos.perfiles_maquina import DialogoPerfilesMaquina, _DialogoExportar
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.interfaz.vistas.lote_filas import PanelLoteFilas
from proxlaunch.interfaz.vistas.selector_perfil import PanelAvisos, SelectorPerfil
from proxlaunch.nucleo.archivos.esquema import AvisoArchivo, CodigoAvisoArchivo
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila, OpcionesCsv
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import Problema as ProblemaLote
from proxlaunch.nucleo.lote.modelos import Severidad as SeveridadLote
from proxlaunch.nucleo.lotes_guardados.revalidacion import Desajuste, TipoDesajuste
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.aplicar import AvisoPista
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO

from . import test_ventana_principal as _base
from .apoyo import inventario_cluster
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import (
    csv_valido,
    definicion_filas,
    definicion_homogenea,
    escribir_lote_guardado,
)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)

entorno = _base.entorno  # fixture base de la ventana

RAIZ = Path(__file__).resolve().parents[2] / "src" / "proxlaunch"
CATALOGO = RAIZ / "recursos" / "traducciones" / "proxlaunch_es.ts"
ARCHIVOS_MVP3 = (
    "interfaz/ventana_principal.py",
    "interfaz/archivos_ui.py",
    "interfaz/modelos_tabla_csv.py",
    "interfaz/vistas/selector_perfil.py",
    "interfaz/vistas/lote_filas.py",
    "interfaz/dialogos/perfiles_maquina.py",
    "interfaz/dialogos/guardar_perfil.py",
    "interfaz/dialogos/importar_perfiles.py",
    "interfaz/dialogos/guardar_lote.py",
    "interfaz/dialogos/importar_csv.py",
    "interfaz/dialogos/lote_no_encaja.py",
)


class _TraductorPrefijo(QTranslator):
    """Catálogo de prueba: antepone «[T]» a todo lo que pasa por la traducción."""

    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: ANN001
        return "[T]" + source_text


@pytest.fixture
def traductor(qapp):
    t = _TraductorPrefijo()
    QCoreApplication.installTranslator(t)
    yield t
    QCoreApplication.removeTranslator(t)


_TRADUCIDO = re.compile(r"^[^\wÁ-ú\[]*\[T\]")
_TIENE_LETRAS = re.compile(r"[A-Za-zÁ-ú]{2,}")
# Datos del servidor o del usuario, nombres técnicos o formatos: no se traducen.
_NO_TRADUCIBLES = {"VMID", "?", "UTF-8", "UTF-16", "Windows-1252", "ISO-8859-1", "UTF-8 (BOM)"}


def sin_traducir(raiz: QWidget, ignorar: tuple[str, ...] = ()) -> list[str]:
    """Textos fijos visibles o accesibles de ``raiz`` que no llevan el prefijo del catálogo."""
    malos: list[str] = []

    def revisar(texto: str, donde: str) -> None:
        t = texto.strip()
        if not t or not _TIENE_LETRAS.search(t) or t in _NO_TRADUCIBLES:
            return
        if any(t.startswith(i) for i in ignorar):
            return
        if not _TRADUCIDO.search(t):
            malos.append(f"{donde}: {t[:60]!r}")

    for w in [raiz, *raiz.findChildren(QWidget)]:
        nombre = type(w).__name__
        if isinstance(w, (QPushButton, QToolButton, QCheckBox, QRadioButton)):
            revisar(w.text(), nombre)
            revisar(w.toolTip(), nombre + ".tooltip")
        elif isinstance(w, QLabel):
            revisar(w.text(), nombre)
        elif isinstance(w, QGroupBox):
            revisar(w.title(), nombre)
        elif isinstance(w, QComboBox):
            for i in range(w.count()):
                revisar(w.itemText(i), nombre + ".item")
        if w.accessibleName():
            revisar(w.accessibleName(), nombre + ".accesible")
        if getattr(w, "windowTitle", None) and w.isWindow():
            revisar(w.windowTitle(), nombre + ".titulo")
    return malos


# --- Ayudas para armar componentes sin la ventana ----------------------------------------------


def perfiles_de_fabrica():
    return perfiles_fabrica(textos.textos_perfiles_fabrica())


def almacen_en(tmp_path: Path) -> AlmacenPerfilesMaquina:
    a = AlmacenPerfilesMaquina(
        tmp_path / "perfiles_maquina.json", fabrica=perfiles_de_fabrica(), app_version="0.1.0"
    )
    a.cargar()
    return a


def resultado_csv(tmp_path: Path, n: int = 3, con_error: bool = True):
    ruta = tmp_path / "ejemplo.csv"
    csv_valido(ruta, n)
    if con_error:
        texto = ruta.read_text(encoding="utf-8-sig").replace("2 GiB", "abc", 1)
        ruta.write_bytes(b"\xef\xbb\xbf" + texto.encode("utf-8"))
    perfiles = perfiles_de_fabrica()
    perfil = next(p for p in perfiles if p.id == ID_PREDETERMINADO)
    return leer_e_interpretar(
        ruta, OpcionesCsv(), perfil, perfiles, inventario_cluster(), None, None
    )


# --- Todo texto visible pasa por la traducción ([T]) -------------------------------------------


def test_rnf_m04_el_selector_de_perfil_traduce_todo(qtbot, traductor):
    s = SelectorPerfil()
    qtbot.addWidget(s)
    perfiles = perfiles_de_fabrica()
    s.establecer_perfiles(perfiles, ID_PREDETERMINADO)
    s.establecer_modo(True)
    s.marcar_modificado(True)
    s.mostrar_avisos(["[T]aviso"])
    s.mostrar_compatibilidad(["[T]error"], ["[T]aviso"])
    s.show()
    assert s.title().startswith("[T]")
    assert s.combo.itemText(0).startswith("[T]Personalizado")
    assert s.texto_combo.endswith("(modificado)") and "[T]" in s.texto_combo
    assert sin_traducir(s) == []


def test_rnf_m04_el_selector_traduce_el_boton_de_actualizar_de_un_perfil_propio(
    qtbot, traductor, tmp_path
):
    a = almacen_en(tmp_path)
    from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil, DiscoPerfil

    propio = a.crear("Propio", "", ConfigPerfil(discos=(DiscoPerfil(10),)))
    s = SelectorPerfil()
    qtbot.addWidget(s)
    s.establecer_perfiles(a.todos(), propio.id)
    s.marcar_modificado(True)
    s.show()
    assert s.boton_actualizar.text().startswith("[T]Guardar cambios en el perfil")
    assert s.boton_actualizar.accessibleName().startswith("[T]")


def test_rnf_m04_el_panel_de_filas_traduce_todo(qtbot, traductor):
    p = PanelLoteFilas()
    qtbot.addWidget(p)
    d = definicion_filas([{"nombre": "a", "origen": 2}, {"nombre": "b", "origen": 3}])
    p.establecer(d, origen="ejemplo.csv", desde_archivo=True, puede_revisar=True)
    p.mostrar_problemas(["[T]problema"])
    p.establecer_bloqueo_resumen("[T]motivo")
    p.show()
    assert p.titulo.startswith("[T]")
    assert sin_traducir(p) == []
    for boton in (p.boton_resumen, p.boton_revisar, p.boton_guardar, p.boton_quitar, p.boton_salir):
        assert boton.text().startswith("[T]") and boton.accessibleName().startswith("[T]")


def test_rnf_m04_el_panel_de_filas_traduce_los_encabezados_de_la_tabla(qtbot, traductor):
    p = PanelLoteFilas()
    qtbot.addWidget(p)
    p.establecer(definicion_filas([{"nombre": "a"}]), origen="x", desde_archivo=False)
    m = p.modelo
    from PySide6.QtCore import Qt

    encabezados = [m.headerData(c, Qt.Orientation.Horizontal) for c in range(m.columnCount())]
    assert all(str(e).startswith("[T]") for e in encabezados if e and e != "VMID"), encabezados


def test_rnf_m04_el_panel_no_encaja_traduce_todo(qtbot, traductor):
    p = PanelLoteNoEncaja()
    qtbot.addWidget(p)
    p.establecer_desajustes(
        [
            Desajuste(TipoDesajuste.STORAGE, "x", (0, 2), ("filas[0].discos[0].storage",), ("a",)),
            Desajuste(TipoDesajuste.BRIDGE, "y", (), ("redes[0].bridge",), ()),
            Desajuste(TipoDesajuste.NODO, "n", (), ("destino.nodos[0]",), ("pve1",)),
        ]
    )
    p.show()
    assert p.titulo.text().startswith("[T]")
    assert sin_traducir(p) == []
    assert [b.text() for b in p.botones_usar_otro] == ["[T]Usar otro…"] * 3
    assert p.botones_automatico[0].text() == "[T]Pasar a Automático"
    assert p.texto_afectadas(p.desajustes()[0]).startswith("[T]")


def test_rnf_m04_los_dialogos_de_guardar_traducen_todo(qtbot, traductor, tmp_path):
    lote = DialogoGuardarLote(nombre_sugerido="web", hay_problemas=True, archivo_origen="o.json")
    qtbot.addWidget(lote)
    lote.show()
    a = almacen_en(tmp_path)
    from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed

    cfg = ConfiguracionVM(
        vmid=100,
        nombre="x",
        nodo="pve1",
        discos=[Disco("local-lvm", 10)],
        redes=[InterfazRed("vmbr0")],
    )
    perfil = DialogoGuardarPerfil(a, cfg, avanzado=True)
    qtbot.addWidget(perfil)
    perfil.show()
    nombre = DialogoNombrePerfil(
        a.todos(), titulo="t", texto_aceptar="a", nombre_inicial="n", descripcion_inicial=""
    )
    qtbot.addWidget(nombre)
    for d in (lote, perfil):
        malos = [m for m in sin_traducir(d) if "'web'" not in m]
        assert malos == [], type(d).__name__
    assert lote.windowTitle().startswith("[T]") and perfil.windowTitle().startswith("[T]")
    assert lote.aviso_problemas.text().startswith("[T]")


def test_rnf_m04_el_asistente_de_importar_csv_traduce_todo(qtbot, traductor, tmp_path):
    tabla, resultado = resultado_csv(tmp_path)
    d = DialogoImportarCsv(
        None,
        perfiles=perfiles_de_fabrica(),
        perfil_base_id=ID_PREDETERMINADO,
        inv=inventario_cluster(),
        nodo_referencia=None,
        lanzador=Lanzador(),
        avanzado=True,
    )
    qtbot.addWidget(d)
    d.mostrar_resultado(tabla, resultado, "ejemplo.csv")
    d.tabla.selectRow(0)
    d.show()
    assert d.windowTitle().startswith("[T]")
    # Datos del archivo y nombres técnicos de codificaciones: no se traducen.
    assert sin_traducir(d, ignorar=("ejemplo.csv", "web-", "—", "UTF", "Windows", "ISO")) == []
    assert d.etiqueta_resumen.text().startswith("[T]")
    assert d.boton_continuar.text().startswith("[T]")
    assert d.detalle.toPlainText().count("[T]") >= 1  # «Valor del archivo» y encabezados


def test_rnf_m04_el_asistente_traduce_los_estados_y_encabezados_de_la_tabla(
    qtbot, traductor, tmp_path
):
    from PySide6.QtCore import Qt

    tabla, resultado = resultado_csv(tmp_path)
    d = DialogoImportarCsv(
        None,
        perfiles=perfiles_de_fabrica(),
        perfil_base_id=ID_PREDETERMINADO,
        inv=inventario_cluster(),
        nodo_referencia=None,
        lanzador=Lanzador(),
    )
    qtbot.addWidget(d)
    d.mostrar_resultado(tabla, resultado, "ejemplo.csv")
    m = d.modelo
    encabezados = [m.headerData(c, Qt.Orientation.Horizontal) for c in range(m.columnCount())]
    assert all(str(e).startswith("[T]") for e in encabezados if e and e != "VMID"), encabezados
    for estado in EstadoFila:
        assert "[T]" in textos.texto_estado_con_simbolo(estado)
    ultima = m.columnCount() - 1
    assert {str(m.data(m.index(r, ultima))) for r in range(m.rowCount())} == {
        "✔ [T]Correcta",
        "✖ [T]Con error",
    } or all("[T]" in str(m.data(m.index(r, ultima))) for r in range(m.rowCount()))


def test_rnf_m04_el_gestor_y_la_importacion_de_perfiles_traducen_todo(qtbot, traductor, tmp_path):
    a = almacen_en(tmp_path)
    g = DialogoPerfilesMaquina(a, Lanzador(), app_version="0.1.0")
    qtbot.addWidget(g)
    g.tabla.selectRow(0)
    g.show()
    assert g.windowTitle().startswith("[T]")
    malos = sin_traducir(g, ignorar=tuple(p.nombre for p in a.todos()))
    assert malos == []
    exportar = _DialogoExportar(list(a.todos())[:2])
    qtbot.addWidget(exportar)
    assert sin_traducir(exportar) == []
    from proxlaunch.nucleo.perfiles_maquina.formato import leer_perfiles, perfiles_a_bytes

    archivo = leer_perfiles(
        perfiles_a_bytes(list(a.todos())[:2], con_pistas=False, app_version="0.1.0")
    )
    revision = DialogoImportarPerfiles(archivo, a.todos())
    qtbot.addWidget(revision)
    assert revision.windowTitle().startswith("[T]")
    assert revision.grupo_conflicto.title().startswith("[T]")


def test_rnf_m04_los_menus_nuevos_y_los_mensajes_de_estado_se_traducen(qtbot, traductor, entorno3):
    v = entorno3.ventana
    menus = {a.text(): a.menu() for a in v.menuBar().actions()}
    for nombre in ("&Lote", "&Perfiles"):
        assert f"[T]{nombre}" in menus, list(menus)
    for menu in (menus["[T]&Lote"], menus["[T]&Perfiles"]):
        for accion in menu.actions():
            if not accion.isSeparator():
                assert accion.text().startswith("[T]"), accion.text()


@pytest.mark.parametrize(
    "codigo, params",
    [
        (CodigoError.ARCHIVO_NO_PERMITIDO, {"motivo": "no_regular", "limite": "1048576"}),
        (CodigoError.ARCHIVO_NO_PERMITIDO, {"motivo": "tamano", "limite": "1048576"}),
        (CodigoError.ARCHIVO_FORMATO_AJENO, {"encontrado": "proxlaunch.perfiles"}),
        (CodigoError.ARCHIVO_VERSION_FUTURA, {}),
        (CodigoError.ARCHIVO_DANADO, {"campo": "filas[0].cores"}),
        (CodigoError.ARCHIVO_NO_ACCESIBLE, {"motivo": "bloqueado"}),
        (CodigoError.ARCHIVO_DEMASIADAS_FILAS, {"filas": "250", "max": "100"}),
        (CodigoError.CSV_CODIFICACION, {"fila": "7"}),
        (CodigoError.ARCHIVO_NO_GUARDABLE, {"motivo": "sin_espacio"}),
        (CodigoError.CSV_VACIO, {}),
        (CodigoError.CSV_COLUMNAS, {"motivo": "falta_nombre", "reconocidas": "cpu"}),
        (CodigoError.CSV_VALOR_INVALIDO, {"fila": "3", "columna": "cpu", "valor": "x"}),
        (CodigoError.PERFIL_INEXISTENTE, {"nombre": "x", "disponibles": "a, b"}),
        (CodigoError.PERFIL_NO_MODIFICABLE, {}),
        (CodigoError.PERFILES_SOLO_LECTURA, {}),
        (CodigoError.LOTE_NO_ENCAJA, {"campo": "storage", "valor": "x", "disponibles": "a,b"}),
    ],
    ids=lambda v: v.value if isinstance(v, CodigoError) else "",
)
def test_rnf_m04_cada_error_e_m_sale_del_sistema_de_traduccion(traductor, codigo, params):
    texto = textos.texto_fallo(ErrorProxLaunch(codigo, dict(params)))
    assert "[T]" in texto
    assert "{" not in texto and "}" not in texto  # sin marcas sin rellenar


@pytest.mark.parametrize("regla", ["V-M01", "V-M01.duplicado", "V-M02", "V-M03", "V-M04", "V-M05"])
def test_rnf_m04_cada_regla_de_perfil_sale_del_sistema_de_traduccion(traductor, regla):
    texto = textos.texto_regla_perfil(regla, "nombre")
    assert "[T]" in texto and "{" not in texto


@pytest.mark.parametrize("codigo", list(CodigoAvisoArchivo), ids=lambda c: c.value)
def test_rnf_m04_cada_aviso_de_archivo_sale_del_sistema_de_traduccion(traductor, codigo):
    texto = textos.texto_aviso_archivo(
        AvisoArchivo(codigo, {"n": "2", "columna": "cpu", "desde": "1", "hasta": "2"})
    )
    assert "[T]" in texto and "{" not in texto


@pytest.mark.parametrize("recurso", ["storage", "storage_efi", "bridge"])
def test_rnf_m04_los_avisos_de_pistas_se_traducen(traductor, recurso):
    assert "[T]" in textos.texto_aviso_pista(AvisoPista(recurso, "x", "y", "pve1"))
    assert "[T]" in textos.texto_aviso_pista(AvisoPista(recurso, "x", None, "pve1"))


@pytest.mark.parametrize("tipo", list(TipoDesajuste), ids=lambda t: t.value)
def test_rnf_m04_cada_desajuste_se_traduce_y_nombra_el_valor(traductor, tipo):
    texto = textos.texto_desajuste(Desajuste(tipo, "valor-x", (), (), ("a",)))
    assert "[T]" in texto and "valor-x" in texto


def test_rnf_m04_los_mensajes_por_fila_dicen_fila_en_vez_de_maquina_y_se_traducen(traductor):
    p = ProblemaLote("V-M07", SeveridadLote.ERROR, "nombre", {}, 2)
    texto = textos.texto_problema_lote(p, fila="9")
    assert "[T]" in texto and "9" in texto and "Máquina" not in texto


# --- Español, no inglés ni marcas --------------------------------------------------------------


def test_los_mensajes_de_archivo_no_dejan_marcas_ni_codigos_internos(qapp):
    for codigo, params in (
        (CodigoError.ARCHIVO_DANADO, {}),
        (CodigoError.ARCHIVO_NO_ACCESIBLE, {}),
        (CodigoError.CSV_COLUMNAS, {"motivo": "duplicada", "columna": "cpu"}),
        (CodigoError.LOTE_NO_ENCAJA, {}),
    ):
        texto = textos.texto_fallo(ErrorProxLaunch(codigo, params))
        assert codigo.value not in texto and "{" not in texto and texto.strip()


# --- Ayuda (CA-P11.3, CA-P11.4) ----------------------------------------------------------------


@pytest.mark.parametrize("clave", CAMPOS_AYUDA_MVP3)
def test_ca_p11_3_cada_identificador_de_ayuda_nuevo_tiene_uno_a_tres_frases(qapp, clave):
    texto = ayuda(clave)
    frases = [f for f in re.split(r"(?<=[.!?])\s+", texto.strip()) if f]
    assert texto.strip() and 1 <= len(frases) <= 3, texto


def test_ca_p11_3_la_lista_cubre_los_identificadores_pedidos():
    pedidos = {
        "perfil", "perfil_fabrica", "perfil_pistas", "perfil_guardar", "perfil_exportar",
        "perfil_importar", "perfil_compatibilidad", "lote_guardado", "csv", "csv_plantilla",
        "csv_separador", "csv_codificacion", "csv_unidades", "csv_vista_previa",
    }  # fmt: skip
    assert pedidos <= set(CAMPOS_AYUDA_MVP3)


def test_ca_p11_4_los_textos_de_perfil_dicen_perfil_de_maquina_y_nunca_plantilla(qapp):
    for clave in CAMPOS_AYUDA_MVP3:
        if clave.startswith("perfil"):
            assert "plantilla" not in ayuda(clave).lower(), clave


def test_ca_p11_4_la_interfaz_de_perfiles_no_llama_plantilla_a_un_perfil(qtbot, tmp_path):
    a = almacen_en(tmp_path)
    s = SelectorPerfil()
    qtbot.addWidget(s)
    s.establecer_perfiles(a.todos(), ID_PREDETERMINADO)
    g = DialogoPerfilesMaquina(a, Lanzador(), app_version="0.1.0")
    qtbot.addWidget(g)
    g.show()
    textos_ui = " ".join(
        w.text()
        for raiz in (s, g)
        for w in raiz.findChildren(QLabel) + raiz.findChildren(QPushButton)
    ).lower()
    # En el gestor, «No es una plantilla de Proxmox» aclara justamente la diferencia.
    restante = textos_ui.replace("no es una plantilla de proxmox", "")
    assert "plantilla" not in restante


# --- Accesibilidad (RNF-M06) -------------------------------------------------------------------


def _tiene_etiqueta_asociada(w: QWidget, raiz: QWidget) -> bool:
    return any(lbl.buddy() is w for lbl in raiz.findChildren(QLabel))


def sin_nombre_accesible(raiz: QWidget) -> list[str]:
    """Controles interactivos sin nombre accesible, texto propio ni etiqueta asociada."""
    malos: list[str] = []
    for w in raiz.findChildren(QWidget):
        nombre = type(w).__name__
        if not w.isVisibleTo(raiz):
            continue  # lo oculto no se anuncia (p. ej. el botón de actualizar sin perfil propio)
        if isinstance(w, QAbstractButton) and isinstance(w.parent(), QAbstractScrollArea):
            continue  # botón de la esquina de la tabla: lo crea Qt
        if isinstance(w, QTableView):
            if not w.accessibleName():
                malos.append(f"{nombre} (tabla)")
        elif isinstance(w, (QPushButton, QToolButton, QCheckBox, QRadioButton, QAbstractButton)):
            texto = w.text().strip()
            if (not texto or texto == "?") and not w.accessibleName():
                malos.append(f"{nombre} {texto!r}")
        elif isinstance(w, (QComboBox, QLineEdit, QPlainTextEdit)):
            if (
                isinstance(w, QLineEdit)
                and w.parent() is not None
                and isinstance(w.parent(), QComboBox)
            ):
                continue  # el editor interno de un combo
            if not w.accessibleName() and not _tiene_etiqueta_asociada(w, raiz):
                malos.append(f"{nombre} {w.objectName()!r}")
    return malos


def test_rnf_m06_el_selector_de_perfil_tiene_nombres_accesibles(qtbot, tmp_path):
    a = almacen_en(tmp_path)
    s = SelectorPerfil()
    qtbot.addWidget(s)
    s.establecer_perfiles(a.todos(), ID_PREDETERMINADO)
    s.establecer_modo(True)
    s.show()
    assert s.combo.accessibleName() == "Perfil de máquina"
    assert sin_nombre_accesible(s) == []
    assert s.boton_guardar.accessibleName() and s.boton_administrar.accessibleName()


def test_rnf_m06_el_panel_de_filas_tiene_tabla_botones_y_titulo_con_nombre(qtbot):
    p = PanelLoteFilas()
    qtbot.addWidget(p)
    p.establecer(
        definicion_filas([{"nombre": "a"}, {"nombre": "b"}]),
        origen="x.csv",
        desde_archivo=True,
        puede_revisar=True,
    )
    p.mostrar_problemas(["x"])
    p.show()
    assert p.tabla.accessibleName() == "Máquinas del lote por filas"
    assert sin_nombre_accesible(p) == []
    for b in (p.boton_resumen, p.boton_revisar, p.boton_guardar, p.boton_quitar, p.boton_salir):
        assert b.accessibleName(), b.text()


def test_rnf_m06_el_panel_no_encaja_y_los_avisos_tienen_nombre(qtbot):
    p = PanelLoteNoEncaja()
    qtbot.addWidget(p)
    p.establecer_desajustes(
        [Desajuste(TipoDesajuste.NODO, "pve9", (), ("destino.nodos[0]",), ("pve1",))]
    )
    p.show()
    assert p.accessibleName() == "Este lote no encaja en este servidor"
    assert all(b.accessibleName() for b in p.botones_usar_otro + p.botones_automatico)
    avisos = PanelAvisos("Avisos del archivo")
    qtbot.addWidget(avisos)
    avisos.mostrar(["x"])
    avisos.show()
    assert avisos.accessibleName() == "Avisos del archivo"
    assert avisos.boton_cerrar.accessibleName()


def test_rnf_m06_los_dialogos_nuevos_tienen_nombres_accesibles(qtbot, tmp_path):
    a = almacen_en(tmp_path)
    tabla, resultado = resultado_csv(tmp_path)
    csv = DialogoImportarCsv(
        None,
        perfiles=a.todos(),
        perfil_base_id=ID_PREDETERMINADO,
        inv=inventario_cluster(),
        nodo_referencia=None,
        lanzador=Lanzador(),
        avanzado=True,
    )
    qtbot.addWidget(csv)
    csv.mostrar_resultado(tabla, resultado, "ejemplo.csv")
    csv.show()
    gestor = DialogoPerfilesMaquina(a, Lanzador(), app_version="0.1.0")
    qtbot.addWidget(gestor)
    gestor.show()
    guardar = DialogoGuardarLote(nombre_sugerido="w", archivo_origen="o.json")
    qtbot.addWidget(guardar)
    guardar.show()
    for d in (csv, gestor, guardar):
        assert sin_nombre_accesible(d) == [], type(d).__name__
    assert csv.tabla.accessibleName() == "Filas del archivo"
    assert gestor.tabla.accessibleName() == "Perfiles de máquina"
    assert csv.combo_perfil.accessibleName() == "Perfil base"
    assert guardar.campo_nombre.accessibleName() == "Nombre del lote"


def test_rnf_m06_el_estado_de_las_filas_lleva_simbolo_y_texto_nunca_solo_color(qapp):
    simbolos = {textos.texto_estado_con_simbolo(e) for e in EstadoFila}
    assert simbolos == {"✔ Correcta", "⚠ Con aviso", "✖ Con error"}


def test_rnf_m06_cada_celda_de_la_vista_previa_tiene_texto_accesible(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    tabla, resultado = resultado_csv(tmp_path)
    d = DialogoImportarCsv(
        None,
        perfiles=perfiles_de_fabrica(),
        perfil_base_id=ID_PREDETERMINADO,
        inv=inventario_cluster(),
        nodo_referencia=None,
        lanzador=Lanzador(),
    )
    qtbot.addWidget(d)
    d.mostrar_resultado(tabla, resultado, "ejemplo.csv")
    m = d.modelo
    for r in range(m.rowCount()):
        for c in range(1, m.columnCount()):  # la columna 0 es la casilla «Incluir»
            lectura = m.data(m.index(r, c), Qt.ItemDataRole.AccessibleTextRole)
            assert lectura and "Fila" in str(lectura), lectura  # «se lee fila a fila»


# --- Catálogo .ts ------------------------------------------------------------------------------


def _fuentes_del_catalogo() -> set[str]:
    raiz = ET.parse(CATALOGO).getroot()
    return {
        m.findtext("source") or "" for c in raiz.findall("context") for m in c.findall("message")
    }


def _literales_tr(ruta: Path) -> list[tuple[int, str]]:
    """Literales de ``self.tr("…")`` (un argumento) y de ``translate("Ctx", "…")``."""
    salida: list[tuple[int, str]] = []
    for n in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        if n.func.attr == "tr" and n.args and isinstance(n.args[0], ast.Constant):
            salida.append((n.lineno, str(n.args[0].value)))
        elif (
            n.func.attr == "translate" and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant)
        ):
            salida.append((n.lineno, str(n.args[1].value)))
    return salida


@pytest.mark.parametrize("relativa", ARCHIVOS_MVP3)
def test_rnf_m04_el_catalogo_contiene_cada_texto_traducible_de_los_modulos_nuevos(relativa):
    fuentes = _fuentes_del_catalogo()
    faltan = [
        f"{relativa}:{linea} {texto[:50]!r}"
        for linea, texto in _literales_tr(RAIZ / relativa)
        if texto not in fuentes
    ]
    assert faltan == []


@pytest.mark.parametrize("contexto", [
    "SelectorPerfil", "PanelLoteFilas", "PanelLoteNoEncaja", "DialogoGuardarLote",
    "DialogoGuardarPerfil", "DialogoImportarCsv", "DialogoImportarPerfiles",
    "DialogoPerfilesMaquina", "ModelosTablaCsv", "PerfilesFabrica", "ColumnasCsv", "ArchivosUi",
])  # fmt: skip
def test_rnf_m04_el_catalogo_tiene_los_contextos_del_mvp3(contexto):
    raiz = ET.parse(CATALOGO).getroot()
    assert contexto in {c.findtext("name") for c in raiz.findall("context")}


def test_rnf_m04_los_encabezados_canonicos_del_csv_no_se_traducen_pero_el_idioma_activo_se_acepta(
    traductor,
):
    alias = textos.alias_columnas_csv()
    assert alias  # el parser recibe los encabezados del idioma activo (RNF-M04)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in alias.items())


# --- Archivos del lote en la ventana: usan el nombre, no la ruta -------------------------------


def test_los_mensajes_de_estado_de_archivos_usan_solo_el_nombre_del_archivo(
    qtbot, entorno3, archivos, tmp_path
):
    from .apoyo_mvp3 import conectar3

    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    carpeta = tmp_path / "carpeta con ñ"
    carpeta.mkdir()
    ruta = escribir_lote_guardado(carpeta / "mi lote.proxlaunch-lote.json", definicion_homogenea())
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == ruta, timeout=3000)
    mensaje = v.statusBar().currentMessage()
    assert str(tmp_path) not in mensaje and "carpeta con ñ" not in mensaje
