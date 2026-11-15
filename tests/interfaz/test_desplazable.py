"""Ventanas y diálogos acotados al área útil de la pantalla (M-E3 / RNF de escalado, MVP 5).

Contrato: con escala del 125 al 175 % en pantallas pequeñas ninguna ventana queda más grande que
el área útil; el contenido se desplaza y los botones de acción quedan siempre visibles. Con
pantalla holgada nada cambia. Las áreas útiles se inyectan (``ancho_disponible`` /
``alto_disponible``), así que las pruebas no dependen de la pantalla offscreen.

Los tamaños que dependen de las fuentes de la plataforma se comparan con el ``sizeHint`` o el
``minimumSizeHint`` medidos en la propia prueba y no con constantes: en Windows y en Linux las
métricas de texto difieren. Además, un bloque de pruebas repite los contratos clave con una
fuente de aplicación ancha (JetBrains Mono, incluida en el repo) para reproducir en cualquier
plataforma las condiciones de Windows.

Contrato de tamaño: con espacio holgado no hay barras y la ventana crece lo necesario para el
contenido (aunque supere el ``resize()`` previo o el mínimo explícito); si cabe, se respeta el
``resize()``. Con espacio escaso se acota al área útil y la barra sale solo en el eje que no cabe.
El tamaño no depende del historial.
"""

from __future__ import annotations

import gc
from collections.abc import Callable

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from proxlaunch.interfaz.desplazable import (
    AjusteDesplazable,
    crear_area_desplazable,
    hacer_desplazable,
    limitar_a_pantalla,
)
from proxlaunch.interfaz.dialogos.acerca_de import DialogoAcercaDe
from proxlaunch.interfaz.dialogos.capacidades import DialogoCapacidades
from proxlaunch.interfaz.dialogos.catalogo import DialogoCatalogo, FuenteCatalogo
from proxlaunch.interfaz.dialogos.conexion import DialogoConexion
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv
from proxlaunch.interfaz.dialogos.importar_perfiles import DialogoImportarPerfiles
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.dialogos.perfiles_maquina import DialogoPerfilesMaquina
from proxlaunch.interfaz.dialogos.transferencia import DialogoDescarga, DialogoSubida
from proxlaunch.interfaz.dialogos.transferencias_sesion import DialogoTransferenciasSesion
from proxlaunch.interfaz.fuentes import cargar_fuentes
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.interfaz.ventana_principal import VentanaPrincipal
from proxlaunch.nucleo.lote.modelos import CandidatoRollback
from proxlaunch.nucleo.lote.modelos import EstadoMV as EM
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.origen.capacidades_origen import Via
from proxlaunch.nucleo.perfiles_maquina.formato import ArchivoPerfiles
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion

from . import apoyo, apoyo_lote, apoyo_mvp4
from .test_mvp3_textos_accesibilidad import ID_PREDETERMINADO, almacen_en, perfiles_de_fabrica
from .test_mvp3_textos_accesibilidad import resultado_csv as _resultado_csv

# Áreas útiles (ancho, alto) en px lógicos: 125-175 % de escala en pantallas pequeñas y holgada.
AREA_585 = (585, 410)
AREA_1097 = (1097, 590)
AREA_1024 = (1024, 540)
AREA_HOLGADA = (4000, 4000)
AREAS = [AREA_585, AREA_1097, AREA_1024, AREA_HOLGADA]
AREAS_PEQUENAS = [AREA_585, AREA_1097, AREA_1024]


# --- Ayudas -----------------------------------------------------------------------------------


def _ajuste_de(ventana: QWidget) -> AjusteDesplazable:
    """El ``AjusteDesplazable`` instalado en la ventana (se publica como hijo de la ventana)."""
    ajustes = ventana.findChildren(AjusteDesplazable)
    assert ajustes, "la ventana no tiene AjusteDesplazable"
    return ajustes[0]


def _asentar(qtbot) -> None:
    """Deja correr los reajustes diferidos (``QTimer.singleShot(0)``) y los eventos de layout."""
    QApplication.processEvents()
    qtbot.wait(30)
    QApplication.processEvents()


def _fijar_area(ventana: QWidget, area: tuple[int, int]) -> AjusteDesplazable:
    aj = _ajuste_de(ventana)
    aj.ancho_disponible, aj.alto_disponible = area
    aj.reajustar()
    return aj


def _mostrar(qtbot, ventana: QWidget, area: tuple[int, int]) -> AjusteDesplazable:
    """Inyecta el área útil, muestra la ventana y espera a que se asiente."""
    qtbot.addWidget(ventana)
    aj = _fijar_area(ventana, area)
    ventana.show()
    _asentar(qtbot)
    return aj


def _area_scroll(dialogo: QWidget) -> QScrollArea:
    """El área desplazable que envuelve el contenido (la primera del diálogo)."""
    areas = dialogo.findChildren(QScrollArea)
    assert areas
    return areas[0]


def _botones_del_pie(dialogo: QWidget) -> list[QAbstractButton]:
    """Botones del diálogo que NO están dentro del contenido desplazable."""
    contenido = _area_scroll(dialogo).widget()
    return [b for b in dialogo.findChildren(QAbstractButton) if not contenido.isAncestorOf(b)]


def _dentro(dialogo: QWidget, w: QWidget) -> bool:
    """La geometría completa de ``w`` queda dentro del ``rect()`` del diálogo."""
    esq_sup = w.mapTo(dialogo, w.rect().topLeft())
    esq_inf = w.mapTo(dialogo, w.rect().bottomRight())
    return dialogo.rect().contains(esq_sup) and dialogo.rect().contains(esq_inf)


def _barra_v(dialogo: QWidget) -> bool:
    return _area_scroll(dialogo).verticalScrollBar().maximum() > 0


def _barra_h(dialogo: QWidget) -> bool:
    return _area_scroll(dialogo).horizontalScrollBar().maximum() > 0


def _acotada(ventana: QWidget, aj: AjusteDesplazable) -> bool:
    return ventana.width() <= aj.limite_ancho() and ventana.height() <= aj.limite_alto()


# --- Fábricas de diálogos (reciben tmp_path y las fixtures de interfaz) -----------------------


@pytest.fixture
def lanzador(qtbot):
    lz = Lanzador()
    yield lz
    lz.esperar(2000)


@pytest.fixture
def conexion(deps, lanzador):
    """Fábrica de DialogoConexion sin mostrar."""

    def _crear(avanzado: bool = False, motivo: str | None = None) -> DialogoConexion:
        return DialogoConexion(
            deps.servicio_conexion,
            deps.perfiles,
            deps.huellas,
            deps.secretos,
            lanzador,
            avanzado=avanzado,
            motivo=motivo,
        )

    return _crear


MOTIVO_LARGO = "La sesión caducó. " * 6


def _fabricas(tmp_path, lanzador) -> dict[str, Callable[[], QDialog]]:
    """Diálogos envueltos con ``hacer_desplazable`` (muestra representativa), sin mostrar."""
    caps = apoyo_mvp4.caps_origen()
    ctrl = apoyo_mvp4.ControladorFalso(apoyo_mvp4.inv_origen())
    iso = tmp_path / "a.iso"
    iso.write_bytes(b"x" * 10)
    almacen = almacen_en(tmp_path)

    def csv() -> DialogoImportarCsv:
        tabla, res = _resultado_csv(tmp_path)
        d = DialogoImportarCsv(
            None,
            perfiles=perfiles_de_fabrica(),
            perfil_base_id=ID_PREDETERMINADO,
            inv=apoyo.inventario_cluster(),
            nodo_referencia=None,
            lanzador=lanzador,
            avanzado=True,
        )
        d.mostrar_resultado(tabla, res, "ejemplo.csv")
        return d

    informe = apoyo_lote.informe_de(apoyo_lote.entradas_de([EM.OK, EM.ERROR]))
    candidatos = [
        CandidatoRollback(apoyo_lote.entrada(i, EM.OK), True, None, False) for i in range(6)
    ]
    return {
        "AcercaDe": lambda: DialogoAcercaDe("oscuro"),
        "Capacidades": lambda: DialogoCapacidades(caps),
        "Catalogo": lambda: DialogoCatalogo(
            FuenteCatalogo.ISO,
            estado_subir=caps.estado(Via.SUBIR_ISO),
            estado_descargar=caps.estado(Via.DESCARGAR_URL),
        ),
        "Deshacer": lambda: DialogoDeshacer(candidatos),
        "ImportarCsv": csv,
        "ImportarPerfiles": lambda: DialogoImportarPerfiles(ArchivoPerfiles((), (), ()), []),
        "Informe": lambda: DialogoInforme(informe, tmp_path),
        "PerfilesMaquina": lambda: DialogoPerfilesMaquina(almacen, lanzador, app_version="0.1.0"),
        "Subida": lambda: DialogoSubida(ctrl, Contenido.ISO, "pve", ruta=iso),
        "Descarga": lambda: DialogoDescarga(ctrl, Contenido.ISO, "pve"),
        "TransferenciasSesion": lambda: DialogoTransferenciasSesion(RegistroSesion()),
    }


@pytest.fixture
def fabricas(tmp_path, lanzador):
    return _fabricas(tmp_path, lanzador)


NOMBRES = [
    "AcercaDe",
    "Capacidades",
    "Catalogo",
    "Deshacer",
    "ImportarCsv",
    "ImportarPerfiles",
    "Informe",
    "PerfilesMaquina",
    "Subida",
    "Descarga",
    "TransferenciasSesion",
]

# Mínimos explícitos grandes que el diálogo pide con setMinimumSize.
MINIMOS = {"Capacidades": (1000, 640), "Catalogo": (900, 460)}
# Tamaños pedidos con resize() antes de envolver el diálogo.
RESIZE_PREVIO = {
    "ImportarCsv": (980, 640),
    "Informe": (760, 520),
    "PerfilesMaquina": (820, 560),
    "ImportarPerfiles": (780, 520),
}


# --- Contrato 1: nunca más grande que el área útil --------------------------------------------


@pytest.mark.parametrize("area", AREAS, ids=lambda a: f"{a[0]}x{a[1]}")
@pytest.mark.parametrize(
    ("avanzado", "motivo"),
    [(False, None), (True, None), (False, MOTIVO_LARGO), (True, MOTIVO_LARGO)],
    ids=["basico", "avanzado", "basico_con_motivo", "avanzado_con_motivo"],
)
def test_c1_conexion_no_supera_el_area_util(qtbot, conexion, area, avanzado, motivo):
    d = conexion(avanzado, motivo)
    aj = _mostrar(qtbot, d, area)
    assert d.width() <= aj.limite_ancho()
    assert d.height() <= aj.limite_alto()
    # El marco (barra de título y bordes) también cabe en el área útil.
    assert d.height() <= area[1] and d.width() <= area[0]


@pytest.mark.parametrize("area", AREAS, ids=lambda a: f"{a[0]}x{a[1]}")
@pytest.mark.parametrize("nombre", NOMBRES)
def test_c1_dialogos_envueltos_no_superan_el_area_util(qtbot, fabricas, nombre, area):
    d = fabricas[nombre]()
    aj = _mostrar(qtbot, d, area)
    assert d.width() <= aj.limite_ancho(), f"{nombre} {d.size()} en {area}"
    assert d.height() <= aj.limite_alto(), f"{nombre} {d.size()} en {area}"


@pytest.mark.parametrize("area", AREAS_PEQUENAS, ids=lambda a: f"{a[0]}x{a[1]}")
@pytest.mark.parametrize("nombre", ["Capacidades", "ImportarCsv", "Catalogo"])
def test_c1_los_de_minimo_grande_se_acotan_en_pantalla_pequena(qtbot, fabricas, nombre, area):
    d = fabricas[nombre]()
    aj = _mostrar(qtbot, d, area)
    assert d.width() <= aj.limite_ancho()
    assert d.height() <= aj.limite_alto()
    # El mínimo que pedía el diálogo no impide encoger: queda acotado también.
    assert d.minimumWidth() <= aj.limite_ancho()
    assert d.minimumHeight() <= aj.limite_alto()


def test_c1_area_diminuta_no_lanza_ni_da_limites_negativos(qtbot, conexion):
    d = conexion()
    aj = _mostrar(qtbot, d, (10, 10))
    assert aj.limite_ancho() >= 0 and aj.limite_alto() >= 0
    assert d.width() <= max(aj.limite_ancho(), d.minimumWidth())


# --- Contrato 2: con pantalla holgada nada cambia ---------------------------------------------


def test_c2_conexion_basico_holgado_toma_su_tamano_natural_sin_barras(qtbot, conexion):
    d = conexion(False)
    # Tamaño natural medido en la propia prueba: en la referencia (600x554) depende de las
    # fuentes de la plataforma, así que se compara con el sizeHint del diálogo y no con una
    # constante.
    _mostrar(qtbot, d, AREA_HOLGADA)
    # El sizeHint varía con las etiquetas de ajuste de línea: solo se exige que la ventana sea al
    # menos tan grande como el sizeHint y el mínimo explícito (600), y que no haya barras.
    hint = d.sizeHint()
    assert d.minimumWidth() == 600
    assert d.width() >= max(hint.width(), d.minimumWidth())
    assert not _barra_v(d) and not _barra_h(d)


@pytest.mark.parametrize("nombre", sorted(RESIZE_PREVIO))
def test_c2_dialogos_con_resize_previo_conservan_su_tamano(qtbot, fabricas, nombre):
    d = fabricas[nombre]()
    _mostrar(qtbot, d, AREA_HOLGADA)
    ancho, alto = RESIZE_PREVIO[nombre]
    # Si el contenido cabe se respeta el resize(); si no, la ventana crece hasta su mínimo.
    minimo = d.minimumSizeHint()
    assert d.width() == max(ancho, minimo.width())
    assert d.height() == max(alto, minimo.height())
    assert not _barra_v(d) and not _barra_h(d)


@pytest.mark.parametrize("nombre", sorted(MINIMOS))
def test_c2_dialogos_con_minimo_explicito_lo_conservan_holgado(qtbot, fabricas, nombre):
    d = fabricas[nombre]()
    _mostrar(qtbot, d, AREA_HOLGADA)
    ancho, alto = MINIMOS[nombre]
    assert (d.minimumWidth(), d.minimumHeight()) == (ancho, alto)
    assert d.width() >= ancho and d.height() >= alto


def test_c2_ventana_principal_holgada_1240x820_con_minimo_1000x640(qtbot, deps):
    v = VentanaPrincipal(deps)
    _mostrar(qtbot, v, AREA_HOLGADA)
    assert (v.width(), v.height()) == (1240, 820)
    assert (v.minimumWidth(), v.minimumHeight()) == (1000, 640)


# --- Contrato 3: pie fuera del desplazamiento y siempre visible -------------------------------


@pytest.mark.parametrize("area", AREAS, ids=lambda a: f"{a[0]}x{a[1]}")
@pytest.mark.parametrize("avanzado", [False, True], ids=["basico", "avanzado"])
def test_c3_botones_de_conexion_fuera_del_area_y_dentro_del_dialogo(
    qtbot, conexion, area, avanzado
):
    d = conexion(avanzado, MOTIVO_LARGO)
    _mostrar(qtbot, d, area)
    contenido = _area_scroll(d).widget()
    for boton in (d.btn_guardar, d.btn_cancelar, d.btn_conectar):
        assert not contenido.isAncestorOf(boton)
        assert boton.isVisible()
        assert _dentro(d, boton), f"{boton.text()} fuera de {d.rect()} con área {area}"


@pytest.mark.parametrize("area", AREAS_PEQUENAS, ids=lambda a: f"{a[0]}x{a[1]}")
@pytest.mark.parametrize("nombre", NOMBRES)
def test_c3_botones_de_los_demas_dialogos_visibles_con_area_pequena(qtbot, fabricas, nombre, area):
    d = fabricas[nombre]()
    _mostrar(qtbot, d, area)
    botones = [b for b in _botones_del_pie(d) if b.isVisible()]
    assert botones, f"{nombre} no tiene botones de pie visibles"
    for boton in botones:
        assert _dentro(d, boton), f"{nombre}: {boton.text()!r} fuera del diálogo con área {area}"


def test_c3_el_error_del_pie_de_conexion_se_ve_sin_desplazar(qtbot, conexion):
    d = conexion(True, MOTIVO_LARGO)
    _mostrar(qtbot, d, AREA_585)
    d._estado.setText("No se pudo conectar con el servidor. " * 3)
    d._estado.show()
    _asentar(qtbot)
    contenido = _area_scroll(d).widget()
    assert not contenido.isAncestorOf(d._estado)
    assert d._estado.isVisible()
    assert _dentro(d, d._estado)
    assert d.height() <= _ajuste_de(d).limite_alto()


# --- Contrato 4: barras solo cuando el contenido no cabe --------------------------------------


def test_c4_sin_barras_si_todo_cabe(qtbot, conexion):
    d = conexion(False)
    _mostrar(qtbot, d, AREA_HOLGADA)
    assert not _barra_v(d)
    assert not _barra_h(d)


def test_c4_barra_vertical_aparece_si_no_cabe_a_lo_alto(qtbot, conexion):
    d = conexion(True, MOTIVO_LARGO)
    _mostrar(qtbot, d, (4000, 400))
    assert _barra_v(d)
    # Con ancho de sobra no hace falta la horizontal.
    assert not _barra_h(d)


def test_c4_barra_vertical_desaparece_al_subir_el_alto(qtbot, conexion):
    d = conexion(True, MOTIVO_LARGO)
    aj = _mostrar(qtbot, d, (4000, 400))
    assert _barra_v(d)
    aj.alto_disponible = 4000
    aj.reajustar()
    _asentar(qtbot)
    assert not _barra_v(d)


def test_c4_barra_horizontal_en_importar_csv_a_585_de_ancho(qtbot, fabricas):
    d = fabricas["ImportarCsv"]()
    _mostrar(qtbot, d, AREA_585)
    assert _barra_h(d)


def test_c4_conexion_a_4000_de_ancho_no_tiene_barra_horizontal(qtbot, conexion):
    d = conexion(True)
    _mostrar(qtbot, d, (4000, 400))
    assert not _barra_h(d)


# --- Contrato 5: mínimos acotados y recuperables ----------------------------------------------


@pytest.mark.parametrize("nombre", sorted(MINIMOS))
def test_c5_minimo_explicito_acotado_al_limite_y_recuperado_al_subir(qtbot, fabricas, nombre):
    d = fabricas[nombre]()
    aj = _mostrar(qtbot, d, AREA_585)
    assert d.minimumWidth() <= aj.limite_ancho()
    assert d.minimumHeight() <= aj.limite_alto()
    aj.ancho_disponible, aj.alto_disponible = AREA_HOLGADA
    aj.reajustar()
    _asentar(qtbot)
    ancho, alto = MINIMOS[nombre]
    assert (d.minimumWidth(), d.minimumHeight()) == (ancho, alto)
    assert d.width() >= ancho and d.height() >= alto


def test_c5_importar_csv_recupera_980x640_al_subir_el_area(qtbot, fabricas):
    d = fabricas["ImportarCsv"]()
    aj = _mostrar(qtbot, d, AREA_585)
    assert d.width() < 980
    aj.ancho_disponible, aj.alto_disponible = AREA_HOLGADA
    aj.reajustar()
    _asentar(qtbot)
    assert d.width() == max(980, d.minimumSizeHint().width())
    assert d.height() == 640
    assert not _barra_h(d)


def test_c5_ventana_principal_recupera_1240x820_al_subir_el_area(qtbot, deps):
    v = VentanaPrincipal(deps)
    aj = _mostrar(qtbot, v, AREA_1024)
    assert _acotada(v, aj)
    assert v.minimumWidth() <= aj.limite_ancho()
    assert v.minimumHeight() <= aj.limite_alto()
    aj.ancho_disponible, aj.alto_disponible = AREA_HOLGADA
    aj.reajustar()
    _asentar(qtbot)
    assert (v.width(), v.height()) == (1240, 820)
    assert (v.minimumWidth(), v.minimumHeight()) == (1000, 640)


def test_c5_set_minimum_size_posterior_se_respeta_acotado_y_se_recupera(qtbot, conexion):
    d = conexion(False)
    aj = _mostrar(qtbot, d, AREA_585)
    d.setMinimumSize(900, 700)  # más grande que el límite del área pequeña
    aj.reajustar()
    assert d.minimumWidth() == aj.limite_ancho()
    assert d.minimumHeight() == aj.limite_alto()
    assert d.width() <= aj.limite_ancho() and d.height() <= aj.limite_alto()
    aj.ancho_disponible, aj.alto_disponible = AREA_HOLGADA
    aj.reajustar()
    _asentar(qtbot)
    assert (d.minimumWidth(), d.minimumHeight()) == (900, 700)
    assert d.width() >= 900 and d.height() >= 700


def test_c5_set_minimum_size_posterior_menor_que_el_limite_se_respeta_tal_cual(qtbot, conexion):
    d = conexion(False)
    aj = _mostrar(qtbot, d, AREA_HOLGADA)
    d.setMinimumSize(300, 200)
    aj.reajustar()
    assert (d.minimumWidth(), d.minimumHeight()) == (300, 200)


# --- Contrato 6: crecer al mostrar partes, sin pasar del límite -------------------------------


class _DialogoPrueba(QDialog):
    """Diálogo mínimo hecho solo con la API pública: etiqueta en el contenido y otra en el pie."""

    def __init__(self) -> None:
        super().__init__()
        capa, capa_pie, self.ajuste = hacer_desplazable(self)
        self.titulo = QLabel("Contenido fijo")
        self.etiqueta_contenido = QLabel("Parte opcional del contenido. " * 8)
        self.etiqueta_contenido.setWordWrap(True)
        # Alto mínimo fijo: el crecimiento al mostrarla no depende de las métricas de la fuente.
        self.etiqueta_contenido.setMinimumHeight(200)
        self.etiqueta_contenido.hide()
        capa.addWidget(self.titulo)
        capa.addWidget(self.etiqueta_contenido)
        capa.addStretch(1)
        self.etiqueta_pie = QLabel("Mensaje del pie. " * 12)
        self.etiqueta_pie.setWordWrap(True)
        self.etiqueta_pie.setMinimumHeight(100)
        self.etiqueta_pie.hide()
        self.boton = QPushButton("Aceptar")
        capa_pie.addWidget(self.etiqueta_pie)
        capa_pie.addWidget(self.boton)


def _prueba_visible(qtbot, area: tuple[int, int]) -> _DialogoPrueba:
    d = _DialogoPrueba()
    _mostrar(qtbot, d, area)
    return d


@pytest.mark.parametrize("parte", ["etiqueta_contenido", "etiqueta_pie"])
def test_c6_mostrar_una_parte_hace_crecer_la_ventana_con_area_holgada(qtbot, parte):
    d = _prueba_visible(qtbot, AREA_HOLGADA)
    antes = d.height()
    getattr(d, parte).show()
    _asentar(qtbot)
    assert d.height() > antes
    assert d.height() <= d.ajuste.limite_alto()


@pytest.mark.parametrize("parte", ["etiqueta_contenido", "etiqueta_pie"])
def test_c6_con_area_justa_crece_pero_no_pasa_del_limite(qtbot, parte):
    # Área algo mayor que el diálogo vacío pero menor que con la parte visible.
    d = _prueba_visible(qtbot, (800, 4000))
    base = d.height()
    d.hide()
    d.ajuste.alto_disponible = base + 60
    d.ajuste.reajustar()
    d.show()
    _asentar(qtbot)
    getattr(d, parte).setText("texto largo " * 400)
    getattr(d, parte).show()
    _asentar(qtbot)
    assert d.height() <= d.ajuste.limite_alto()
    assert d.height() >= base  # no encoge por mostrar algo


@pytest.mark.parametrize("parte", ["etiqueta_contenido", "etiqueta_pie"])
def test_c6_ocultar_y_volver_a_mostrar_no_crece_de_mas(qtbot, parte):
    d = _prueba_visible(qtbot, AREA_HOLGADA)
    etiqueta = getattr(d, parte)
    etiqueta.show()
    _asentar(qtbot)
    con_parte = d.height()
    etiqueta.hide()
    _asentar(qtbot)
    etiqueta.show()
    _asentar(qtbot)
    assert d.height() == con_parte


def test_c6_hide_y_show_del_dialogo_no_produce_crecimiento_espurio(qtbot):
    d = _prueba_visible(qtbot, AREA_HOLGADA)
    d.etiqueta_pie.show()
    _asentar(qtbot)
    tam = d.size()
    for _ in range(3):
        d.hide()
        d.show()
        _asentar(qtbot)
    assert d.size() == tam


def test_c6_hide_y_show_con_area_pequena_se_mantiene_acotado(qtbot):
    d = _prueba_visible(qtbot, AREA_585)
    d.etiqueta_contenido.setText("texto largo " * 400)
    d.etiqueta_contenido.show()
    _asentar(qtbot)
    for _ in range(3):
        d.hide()
        d.show()
        _asentar(qtbot)
        assert _acotada(d, d.ajuste)


def test_c6_conexion_mostrar_el_error_del_pie_hace_crecer_sin_pasar_del_limite(qtbot, conexion):
    d = conexion(False)
    aj = _mostrar(qtbot, d, AREA_HOLGADA)
    antes = d.height()
    d._estado.setText("Error de conexión largo. " * 10)
    d._estado.show()
    _asentar(qtbot)
    assert d.height() >= antes
    aj.alto_disponible = 450
    aj.reajustar()
    d._estado.setText("otro error " * 200)
    _asentar(qtbot)
    assert d.height() <= aj.limite_alto()


# --- Contrato 7: destruir con filtros instalados no lanza (regresión de AttributeError) -------


def test_c7_deleteLater_con_filtros_instalados_no_lanza(qtbot):
    d = _DialogoPrueba()
    d.ajuste.alto_disponible = AREA_585[1]
    d.show()
    _asentar(qtbot)
    d.etiqueta_pie.show()  # fuerza eventos de layout sobre ventana y contenido
    d.deleteLater()
    # Sin la guarda del filtro, aquí saltaba AttributeError (pytest-qt lo convierte en fallo).
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()
    gc.collect()
    QApplication.processEvents()


def test_c7_cierre_normal_y_destruccion_de_conexion_no_lanza(qtbot, conexion):
    d = conexion(True, MOTIVO_LARGO)
    _fijar_area(d, AREA_585)
    d.show()
    _asentar(qtbot)
    d.close()
    d.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()
    gc.collect()
    QApplication.processEvents()


@pytest.mark.parametrize("nombre", ["AcercaDe", "Capacidades", "Deshacer", "TransferenciasSesion"])
def test_c7_destruir_otros_dialogos_envueltos_no_lanza(qtbot, fabricas, nombre):
    d = fabricas[nombre]()
    _fijar_area(d, AREA_1024)
    d.show()
    _asentar(qtbot)
    d.close()
    d.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()
    gc.collect()
    QApplication.processEvents()


def test_c7_destruir_con_reajuste_diferido_pendiente_no_lanza(qtbot):
    d = _DialogoPrueba()
    d.show()
    d.etiqueta_pie.show()  # deja un reajuste diferido en cola
    d.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()
    qtbot.wait(30)
    assert not isValid(d) or not d.isVisible()


# --- Contrato 8: limitar_a_pantalla sobre un diálogo con scroll propio ------------------------


def test_c8_guia_token_se_acota_sin_sustituir_su_scroll(qtbot):
    d = DialogoGuiaToken()
    areas_antes = d.findChildren(QScrollArea)
    aj = _mostrar(qtbot, d, AREA_585)
    assert _acotada(d, aj)
    assert d.minimumWidth() <= aj.limite_ancho()
    assert d.minimumHeight() <= aj.limite_alto()
    areas_despues = d.findChildren(QScrollArea)
    # Mismas áreas y todas son QScrollArea puros (no la envoltura de hacer_desplazable).
    assert len(areas_despues) == len(areas_antes) >= 1
    assert all(type(a) is QScrollArea for a in areas_despues)


def test_c8_guia_token_holgado_conserva_su_minimo(qtbot):
    d = DialogoGuiaToken()
    _mostrar(qtbot, d, AREA_HOLGADA)
    assert (d.minimumWidth(), d.minimumHeight()) == (560, 480)


def test_c8_limitar_a_pantalla_devuelve_el_ajuste_y_acota_un_dialogo_propio(qtbot):
    d = QDialog()
    capa = QVBoxLayout(d)
    capa.addWidget(crear_area_desplazable(QLabel("x\n" * 200)))
    d.setMinimumSize(800, 700)
    aj = limitar_a_pantalla(d, alto_disponible=410, ancho_disponible=585)
    assert isinstance(aj, AjusteDesplazable)
    qtbot.addWidget(d)
    d.show()
    _asentar(qtbot)
    assert _acotada(d, aj)


# --- Contrato 9: ventana principal ------------------------------------------------------------


def test_c9_ventana_principal_estructura_y_acotado(qtbot, deps):
    v = VentanaPrincipal(deps)
    central = v.centralWidget()
    assert type(central) is QWidget  # sigue siendo un QWidget simple, no el QScrollArea
    # La barra superior queda fuera de cualquier QScrollArea.
    assert v.barra.parentWidget() is central
    # Las páginas van dentro del QScrollArea, que cuelga del mismo central.
    area = next(a for a in central.findChildren(QScrollArea) if a.isAncestorOf(v._paginas))
    assert area.parentWidget() is central
    assert area.widget().isAncestorOf(v._paginas) or area.widget() is v._paginas
    assert not area.isAncestorOf(v.barra)
    aj = _mostrar(qtbot, v, AREA_585)
    assert _acotada(v, aj)
    assert v.centralWidget() is central


@pytest.mark.parametrize("area", AREAS_PEQUENAS, ids=lambda a: f"{a[0]}x{a[1]}")
def test_c9_ventana_principal_no_supera_el_area_util(qtbot, deps, area):
    v = VentanaPrincipal(deps)
    qtbot.addWidget(v)
    aj = v.ajuste_pantalla
    aj.ancho_disponible, aj.alto_disponible = area
    aj.reajustar()
    v.show()
    _asentar(qtbot)
    assert v.width() <= aj.limite_ancho()
    assert v.height() <= aj.limite_alto()
    # La barra superior sigue visible y arriba aunque el contenido se desplace.
    assert v.barra.isVisible()
    assert v.barra.mapTo(v, v.barra.rect().topLeft()).y() >= 0


# --- Contrato 10: sin inyección, el límite sale de availableGeometry --------------------------


def test_c10_sin_inyeccion_el_limite_no_supera_la_geometria_disponible(qtbot, conexion):
    d = conexion(False)
    qtbot.addWidget(d)
    aj = _ajuste_de(d)
    assert aj.ancho_disponible is None and aj.alto_disponible is None
    d.show()
    _asentar(qtbot)
    pantalla = d.screen() or QApplication.primaryScreen()
    geom = pantalla.availableGeometry()
    lim = aj.limite_tamano()
    assert lim is not None
    assert 0 <= lim.width() <= geom.width()
    assert 0 <= lim.height() <= geom.height()
    assert aj.limite_ancho() == lim.width() and aj.limite_alto() == lim.height()
    assert d.width() <= geom.width() and d.height() <= geom.height()


def test_c10_inyeccion_parcial_completa_el_otro_eje_con_la_pantalla(qtbot, conexion):
    d = conexion(False)
    qtbot.addWidget(d)
    aj = _ajuste_de(d)
    geom = (d.screen() or QApplication.primaryScreen()).availableGeometry()
    aj.alto_disponible = 300
    aj.reajustar()
    lim = aj.limite_tamano()
    assert lim.height() <= 300
    assert lim.width() <= geom.width()
    aj.alto_disponible = None
    aj.ancho_disponible = 500
    aj.reajustar()
    lim = aj.limite_tamano()
    assert lim.width() <= 500
    assert lim.height() <= geom.height()


def test_c10_ventana_principal_sin_inyeccion_cabe_en_la_pantalla(qtbot, deps):
    v = VentanaPrincipal(deps)
    qtbot.addWidget(v)
    v.show()
    _asentar(qtbot)
    geom = (v.screen() or QApplication.primaryScreen()).availableGeometry()
    lim = v.ajuste_pantalla.limite_tamano()
    assert lim.width() <= geom.width() and lim.height() <= geom.height()
    assert v.width() <= geom.width() and v.height() <= geom.height()


# --- Contrato 11: fuente de aplicación ancha (reproduce las métricas de Windows) --------------


@pytest.fixture(params=[12.0, 13.0], ids=lambda pt: f"mono{pt:g}pt")
def fuente_ancha(qtbot, request):
    """Fija una fuente de aplicación ancha (JetBrains Mono incluida en el repo) y la restaura."""
    original = QFont(QApplication.font())
    familia_interfaz, familia_mono = cargar_fuentes()
    fuente = QFont(QApplication.font())
    fuente.setFamily(familia_mono)
    fuente.setPointSizeF(request.param)
    QApplication.setFont(fuente)
    yield fuente
    QApplication.setFont(original)


@pytest.mark.parametrize("avanzado", [False, True], ids=["basico", "avanzado"])
def test_c11_conexion_holgado_con_fuente_ancha_sin_barras(qtbot, fuente_ancha, conexion, avanzado):
    d = conexion(avanzado)
    _mostrar(qtbot, d, AREA_HOLGADA)
    assert d.width() >= max(d.minimumSizeHint().width(), d.minimumWidth())
    assert not _barra_v(d) and not _barra_h(d)


@pytest.mark.parametrize("nombre", ["ImportarCsv", "PerfilesMaquina"])
def test_c11_dialogos_holgados_con_fuente_ancha_sin_barras(qtbot, fuente_ancha, fabricas, nombre):
    d = fabricas[nombre]()
    _mostrar(qtbot, d, AREA_HOLGADA)
    ancho, alto = RESIZE_PREVIO[nombre]
    assert d.width() == max(ancho, d.minimumSizeHint().width())
    # El alto crece lo necesario para el contenido (con letra ancha el texto se parte más).
    assert d.height() >= alto
    assert not _barra_v(d) and not _barra_h(d)


@pytest.mark.parametrize("avanzado", [False, True], ids=["basico", "avanzado"])
def test_c11_conexion_acotada_y_con_botones_visibles_en_585x410(
    qtbot, fuente_ancha, conexion, avanzado
):
    d = conexion(avanzado, MOTIVO_LARGO)
    aj = _mostrar(qtbot, d, AREA_585)
    assert _acotada(d, aj)
    for boton in (d.btn_guardar, d.btn_cancelar, d.btn_conectar):
        assert boton.isVisible()
        assert _dentro(d, boton), f"{boton.text()} fuera de {d.rect()}"


@pytest.mark.parametrize("nombre", ["ImportarCsv", "PerfilesMaquina"])
def test_c11_dialogos_acotados_y_con_botones_visibles_en_585x410(
    qtbot, fuente_ancha, fabricas, nombre
):
    d = fabricas[nombre]()
    aj = _mostrar(qtbot, d, AREA_585)
    assert _acotada(d, aj)
    botones = [b for b in _botones_del_pie(d) if b.isVisible()]
    assert botones
    for boton in botones:
        assert _dentro(d, boton), f"{nombre}: {boton.text()!r} fuera del diálogo"


def test_c11_importar_csv_no_depende_del_historial_con_fuente_ancha(qtbot, fuente_ancha, fabricas):
    # Abrir directamente en holgado...
    directo = fabricas["ImportarCsv"]()
    _mostrar(qtbot, directo, AREA_HOLGADA)
    # ...o venir de un área pequeña debe dar el mismo tamaño y sin barras.
    con_historia = fabricas["ImportarCsv"]()
    aj = _mostrar(qtbot, con_historia, AREA_585)
    aj.ancho_disponible, aj.alto_disponible = AREA_HOLGADA
    aj.reajustar()
    _asentar(qtbot)
    assert con_historia.size() == directo.size()
    assert not _barra_v(con_historia) and not _barra_h(con_historia)
