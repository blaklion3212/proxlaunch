"""Pruebas de cierre del MVP 1: RF-21 (mensajes), RF-23 (traducción) y RF-27 (recursos).

CA-21.4, CA-23.1, CA-23.2, CA-23.3 y CA-27.1 de docs/requisitos/mvp1.md.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator

from proxlaunch.interfaz import textos
from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Nodo

from .test_textos import PARAMS_ERROR
from .test_vistas_simples import _actualizar

RAIZ = Path(__file__).resolve().parents[2] / "src" / "proxlaunch"
DIR_INTERFAZ = RAIZ / "interfaz"
CATALOGO = RAIZ / "recursos" / "traducciones" / "proxlaunch_es.ts"

# Métodos y constructores que muestran texto al usuario.
_METODOS_TEXTO = {
    "setText", "setToolTip", "setWindowTitle", "setPlaceholderText", "setTitle", "addItem",
    "setStatusTip", "setWhatsThis", "setInformativeText", "setLabelText", "setFormat",
    "setAccessibleName", "setAccessibleDescription", "addTab", "setHtml", "setPlainText",
    "QLabel", "QPushButton", "QCheckBox", "QGroupBox", "QRadioButton", "QAction",
}  # fmt: skip
# Literales que NO son texto traducible: sintaxis de ejemplo y nombres técnicos de Proxmox.
_TECNICOS = {
    "usuario@realm!nombre=secreto",
    "virtio-scsi-single",
    "virtio-scsi-pci",
    "VirtIO",
    "Intel E1000",
    "raw",
    "qcow2",
}


def _nombre_llamada(n: ast.Call) -> str | None:
    f = n.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)


def _literal(n: ast.expr) -> str | None:
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None


# --- CA-23.1 ---------------------------------------------------------------------------


def test_ca_23_1_no_hay_literales_visibles_fuera_de_la_traduccion():
    """CA-23.1: análisis estático de la interfaz (los literales van dentro de translate/tr)."""
    infractores = []
    for f in DIR_INTERFAZ.rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call) or _nombre_llamada(n) not in _METODOS_TEXTO:
                continue
            texto = _literal(n.args[0]) if n.args else None
            if texto and re.search("[A-Za-zÁ-ú]{2,}", texto) and texto not in _TECNICOS:
                infractores.append(f"{f.relative_to(RAIZ)}:{n.lineno} {texto[:40]!r}")
    assert infractores == []


def test_ca_23_1_el_nucleo_no_contiene_textos_de_usuario_solo_codigos():
    """CA-23.1: el núcleo informa con códigos y parámetros (``CodigoError``), no con prosa."""
    e = ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "1"})
    assert str(e) == "vmid_ocupado"
    assert all(re.fullmatch(r"[a-z0-9_]+", c.value) for c in CodigoError)


# --- CA-23.2 ---------------------------------------------------------------------------


def _pares_en_codigo() -> set[tuple[str, str]]:
    pares = set()
    for f in DIR_INTERFAZ.rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (
                isinstance(n, ast.Call)
                and _nombre_llamada(n) in ("translate", "tr")
                and len(n.args) >= 2
                and _literal(n.args[0])
                and _literal(n.args[1])
            ):
                pares.add((_literal(n.args[0]), _literal(n.args[1])))
    return pares


def _pares_en_catalogo() -> set[tuple[str | None, str | None]]:
    raiz = ET.parse(CATALOGO).getroot()
    return {
        (c.findtext("name"), m.findtext("source"))
        for c in raiz.findall("context")
        for m in c.findall("message")
    }


def test_ca_23_2_el_catalogo_es_xml_valido_y_tiene_cientos_de_mensajes():
    """CA-23.2: el catálogo .ts existe y se puede leer."""
    assert len(_pares_en_catalogo()) > 200


@pytest.mark.parametrize(
    "texto",
    [
        "Crear máquina",
        "Ignorar verificación SSL",
        "UEFI necesita un almacenamiento para guardar su configuración",
        "¿Cómo creo un API Token?",
    ],
)
def test_ca_23_2_textos_citados_en_los_requisitos_estan_en_el_catalogo(texto):
    """CA-23.2: textos entre comillas del documento de requisitos presentes como fuente."""
    fuentes = {s for _, s in _pares_en_catalogo()}
    assert any(texto in (s or "") for s in fuentes)


def test_ca_23_2_el_catalogo_contiene_todos_los_textos_traducibles_del_codigo():
    """CA-23.2: cada translate(contexto, texto) del código está en el catálogo."""
    faltan = sorted(_pares_en_codigo() - _pares_en_catalogo())
    assert faltan == []


# --- CA-21.4 y CA-23.3 -----------------------------------------------------------------


class _TraductorPrefijo(QTranslator):
    """Catálogo de prueba: antepone «[T]» a todo lo que se traduce (CA-23.3)."""

    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: ANN001
        return "[T]" + source_text


@pytest.fixture
def traductor_prefijo(qapp):
    t = _TraductorPrefijo()
    QCoreApplication.installTranslator(t)
    yield t
    QCoreApplication.removeTranslator(t)


@pytest.mark.parametrize("codigo", [c for c in CodigoError if c != CodigoError.DESCONOCIDO])
def test_ca_21_4_y_23_3_cada_mensaje_de_error_sale_del_sistema_de_traduccion(
    codigo, traductor_prefijo
):
    """CA-21.4 / CA-23.3: con un catálogo "[T]" todo mensaje de error lleva el prefijo."""
    texto = textos.texto_error(ErrorProxLaunch(codigo, PARAMS_ERROR.get(codigo)))
    assert "[T]" in texto


def test_ca_23_3_el_mensaje_generico_tambien_se_traduce(traductor_prefijo):
    """CA-23.3: incluso el texto genérico (CA-21.2)."""
    assert textos.texto_generico().startswith("[T]")


def test_ca_23_3_el_resumen_y_sus_avisos_se_traducen(resumen, hacer_cfg_ui, traductor_prefijo):
    """CA-23.3: el resumen de la máquina y el aviso de recursos llevan el prefijo."""
    nodo = Nodo("pve1", True, 512, 1)
    _actualizar(resumen, hacer_cfg_ui(), nodo=nodo)
    assert "[T]" in resumen.texto_html and "[T]" in _avisos(resumen)


@pytest.fixture
def resumen(qtbot):
    r = ResumenVM()
    qtbot.addWidget(r)
    r.show()
    return r


# --- CA-27.1 ---------------------------------------------------------------------------


def _avisos(resumen) -> str:
    return resumen._avisos.text()


def test_ca_27_1_avisa_si_pide_mas_nucleos_que_el_nodo(resumen, hacer_cfg_ui):
    """CA-27.1: cores totales mayores que los del nodo (aviso no bloqueante)."""
    cfg = hacer_cfg_ui()  # 8 procesadores
    _actualizar(resumen, cfg, nodo=Nodo("pve1", True, 1 << 20, 4))
    assert "más núcleos de los que tiene el servidor" in _avisos(resumen)
    assert resumen.boton_crear.isEnabled()  # no bloquea


def test_ca_27_1_avisa_si_pide_mas_memoria_que_la_libre(resumen, hacer_cfg_ui):
    """CA-27.1: memoria mayor que la libre del nodo (aviso no bloqueante)."""
    cfg = hacer_cfg_ui()  # 4 GiB
    _actualizar(resumen, cfg, nodo=Nodo("pve1", True, 1024, 64))
    assert "más memoria de la que tiene libre el servidor" in _avisos(resumen)
    assert resumen.boton_crear.isEnabled()


def test_ca_27_1_sin_exceso_no_hay_aviso(resumen, hacer_cfg_ui):
    """CA-27.1: dentro de los límites del nodo no se avisa."""
    _actualizar(resumen, hacer_cfg_ui(), nodo=Nodo("pve1", True, 1 << 20, 64))
    assert "más núcleos" not in _avisos(resumen) and "más memoria" not in _avisos(resumen)


def test_ca_27_1_sin_datos_del_nodo_no_se_avisa(resumen, hacer_cfg_ui):
    """CA-27.1: sin ``Sys.Audit`` el nodo no trae memoria ni CPU: no hay con qué comparar."""
    _actualizar(resumen, hacer_cfg_ui(), nodo=Nodo("pve1", True, None, None))
    assert "más núcleos" not in _avisos(resumen) and "más memoria" not in _avisos(resumen)
