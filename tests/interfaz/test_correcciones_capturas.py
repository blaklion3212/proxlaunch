"""Regresión de los arreglos surgidos al preparar las capturas de la guía (MVP 5).

1) ``AreaInterna``: su ancho mínimo es el real de su contenido (+ marco + barra vertical visible).
2) Ventana principal a 1240 px en modo avanzado: ni el formulario ni la columna derecha se
   recortan con barra horizontal; con espacio escaso la ventana no supera el área útil y la barra
   horizontal es la del área EXTERNA, sin recortar el contenido de las zonas internas.
3) Progreso de una sola máquina: al terminar bien el panel marca todas las etapas con «✓» y la
   barra al máximo; con error, tiempo agotado o conexión perdida «Listo» no lleva «✓».

Las áreas útiles se inyectan, así que las pruebas no dependen de la pantalla offscreen.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QEvent, QSize
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QVBoxLayout, QWidget

from proxlaunch.interfaz.desplazable import AreaInterna
from proxlaunch.interfaz.vistas.progreso import PanelProgreso
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa
from proxlaunch.nucleo.persistencia.preferencias import Modo

from .apoyo import UPID, CreacionFalsa, perfil, resultado, sesion_falsa
from .test_ventana_principal import conectar, poner_nombre
from .test_ventana_principal import entorno as entorno  # noqa: F401  (fixture reutilizada)

ANCHO, ALTO = 1240, 820
AREA_HOLGADA = (1920, 1080)
AREA_ESCASA = (1024, 700)


# --- Ayudas -----------------------------------------------------------------------------------


def _asentar(qtbot) -> None:
    QApplication.processEvents()
    qtbot.wait(30)
    QApplication.processEvents()


def _area_externa(v) -> QScrollArea:
    """El área desplazable que envuelve las páginas de la ventana principal."""
    return v._paginas.parentWidget().parentWidget()


def _internas(v) -> list[QScrollArea]:
    """Todas las áreas desplazables bajo ``_paginas`` (formulario, columna derecha, lotes)."""
    return v._paginas.findChildren(QScrollArea)


def _barra_h_visible(zona: QScrollArea) -> bool:
    barra = zona.horizontalScrollBar()
    return barra.isVisible() or barra.maximum() > 0


def _preparar(qtbot, entorno, area, *, modo=Modo.AVANZADO, ancho=ANCHO, alto=ALTO):
    """Conecta con inventario individual, fija el área útil y muestra la ventana a 1240x820."""
    from .capturas_guia.escenario import inventario_guia_individual

    v = entorno.ventana
    aj = v.ajuste_pantalla
    aj.ancho_disponible, aj.alto_disponible = area
    aj.reajustar()
    entorno.inv = inventario_guia_individual()
    conectar(qtbot, entorno, sesion_falsa(perfil("p1", "Oficina", ("pve.lab",))))
    v.statusBar().setSizeGripEnabled(False)
    v.resize(ancho, alto)
    v.show()
    qtbot.waitExposed(v)
    v.establecer_modo(modo)
    qtbot.wait(300)
    _asentar(qtbot)
    return v


# --- 1. AreaInterna (unitario) ----------------------------------------------------------------


class _Contenido(QWidget):
    """Contenido con un ancho mínimo conocido y modificable."""

    def __init__(self, ancho: int, alto: int = 50) -> None:
        super().__init__()
        self._capa = QVBoxLayout(self)
        self._capa.setContentsMargins(0, 0, 0, 0)
        self.etiqueta = QLabel("x")
        self.etiqueta.setMinimumSize(ancho, alto)
        self._capa.addWidget(self.etiqueta)


def _area_con(ancho: int, alto: int = 50) -> tuple[AreaInterna, _Contenido]:
    contenido = _Contenido(ancho, alto)
    area = AreaInterna()
    area.setWidgetResizable(True)
    area.setWidget(contenido)
    return area, contenido


def test_area_interna_sin_widget_no_falla(qtbot):
    area = AreaInterna()
    qtbot.addWidget(area)
    assert area.minimumSizeHint().width() >= 0


def test_area_interna_el_minimo_sigue_al_contenido(qtbot):
    area, contenido = _area_con(500)
    qtbot.addWidget(area)
    esperado = contenido.minimumSizeHint().width() + 2 * area.frameWidth()
    assert esperado >= 500
    assert area.minimumSizeHint().width() == esperado


def test_area_interna_sin_marco_el_minimo_es_el_del_contenido(qtbot):
    from PySide6.QtWidgets import QFrame

    area, contenido = _area_con(321)
    qtbot.addWidget(area)
    area.setFrameShape(QFrame.Shape.NoFrame)
    assert area.minimumSizeHint().width() == contenido.minimumSizeHint().width()


def test_area_interna_incluye_la_barra_vertical_si_esta_visible(qtbot):
    area, contenido = _area_con(300, alto=2000)
    qtbot.addWidget(area)
    area.resize(600, 200)
    area.show()
    qtbot.waitExposed(area)
    _asentar(qtbot)
    barra = area.verticalScrollBar()
    assert barra.isVisible()
    extension = area.style().pixelMetric(area.style().PixelMetric.PM_ScrollBarExtent, None, barra)
    esperado = contenido.minimumSizeHint().width() + 2 * area.frameWidth() + extension
    assert area.minimumSizeHint().width() == esperado


def test_area_interna_sin_barra_vertical_no_suma_su_ancho(qtbot):
    area, contenido = _area_con(300, alto=40)
    qtbot.addWidget(area)
    area.resize(600, 400)
    area.show()
    qtbot.waitExposed(area)
    _asentar(qtbot)
    assert not area.verticalScrollBar().isVisible()
    assert (
        area.minimumSizeHint().width()
        == contenido.minimumSizeHint().width() + 2 * area.frameWidth()
    )


def test_area_interna_se_actualiza_cuando_el_contenido_crece(qtbot):
    area, contenido = _area_con(300)
    qtbot.addWidget(area)
    area.resize(800, 400)
    area.show()
    qtbot.waitExposed(area)
    _asentar(qtbot)
    antes = area.minimumSizeHint().width()
    contenido.etiqueta.setMinimumWidth(700)
    _asentar(qtbot)
    despues = area.minimumSizeHint().width()
    assert despues >= antes + 300
    assert despues == contenido.minimumSizeHint().width() + 2 * area.frameWidth()


def test_area_interna_avisa_a_su_layout_cuando_cambia_el_minimo(qtbot):
    """Dentro de un layout padre, el mínimo del padre sube al crecer el contenido."""
    area, contenido = _area_con(300)
    padre = QWidget()
    capa = QVBoxLayout(padre)
    capa.addWidget(area)
    qtbot.addWidget(padre)
    padre.show()
    qtbot.waitExposed(padre)
    _asentar(qtbot)
    antes = padre.minimumSizeHint().width()
    contenido.etiqueta.setMinimumWidth(900)
    _asentar(qtbot)
    assert padre.minimumSizeHint().width() >= antes + 500


def _padre_ajustado_al_minimo(qtbot, ancho_etiqueta=400, filas=40):
    """Padre con layout y un ``AreaInterna`` de contenido alto, ajustado a su ancho mínimo."""
    contenido = QWidget()
    capa_c = QVBoxLayout(contenido)
    for _ in range(filas):
        etiqueta = QLabel("x" * 10)
        etiqueta.setMinimumWidth(ancho_etiqueta)
        capa_c.addWidget(etiqueta)
    area = AreaInterna()
    area.setWidgetResizable(True)
    area.setWidget(contenido)
    padre = QWidget()
    capa = QVBoxLayout(padre)
    capa.setContentsMargins(0, 0, 0, 0)
    capa.addWidget(area)
    qtbot.addWidget(padre)
    return padre, area, contenido


def test_area_interna_al_perder_alto_aparece_la_barra_y_no_queda_barra_horizontal(qtbot):
    padre, area, _ = _padre_ajustado_al_minimo(qtbot)
    padre.resize(10, 2000)  # se ajusta al mínimo de ancho
    padre.show()
    qtbot.waitExposed(padre)
    qtbot.wait(100)
    _asentar(qtbot)
    assert not area.verticalScrollBar().isVisible()
    minimo_sin_barra = area.minimumSizeHint().width()
    assert area.width() >= minimo_sin_barra

    padre.resize(10, 300)
    qtbot.wait(200)
    _asentar(qtbot)
    assert area.verticalScrollBar().isVisible()
    assert area.minimumSizeHint().width() > minimo_sin_barra  # se suma el ancho de la barra
    assert area.width() >= area.minimumSizeHint().width()
    assert not _barra_h_visible(area)
    assert area.horizontalScrollBar().maximum() == 0


def test_area_interna_al_recuperar_alto_el_minimo_vuelve_a_bajar(qtbot):
    padre, area, _ = _padre_ajustado_al_minimo(qtbot)
    padre.resize(10, 2000)
    padre.show()
    qtbot.waitExposed(padre)
    qtbot.wait(100)
    _asentar(qtbot)
    minimo_sin_barra = area.minimumSizeHint().width()
    padre.resize(10, 300)
    qtbot.wait(200)
    _asentar(qtbot)
    assert area.minimumSizeHint().width() > minimo_sin_barra

    padre.resize(10, 2000)
    qtbot.wait(200)
    _asentar(qtbot)
    assert not area.verticalScrollBar().isVisible()
    assert area.minimumSizeHint().width() == minimo_sin_barra
    assert not _barra_h_visible(area)


def test_area_interna_en_reposo_no_repite_update_geometry(qtbot, monkeypatch):
    llamadas = []
    original = AreaInterna.updateGeometry

    def contar(self):
        llamadas.append(1)
        return original(self)

    monkeypatch.setattr(AreaInterna, "updateGeometry", contar)
    padre, area, _ = _padre_ajustado_al_minimo(qtbot)
    padre.resize(10, 300)
    padre.show()
    qtbot.waitExposed(padre)
    qtbot.wait(300)
    _asentar(qtbot)
    llamadas.clear()
    qtbot.wait(400)
    assert llamadas == []  # sin bucles de geometría en reposo


def test_area_interna_set_widget_none_no_lanza(qtbot):
    area, _ = _area_con(200)
    qtbot.addWidget(area)
    area.setWidget(None)  # Qt lo ignora: el contenido previo sigue ahí y el área sigue usable
    assert area.minimumSizeHint().width() >= 200
    nueva = AreaInterna()
    qtbot.addWidget(nueva)
    nueva.setWidget(None)  # también sobre un área que nunca tuvo contenido


def test_area_interna_take_widget_devuelve_el_widget_y_quita_el_filtro(qtbot, monkeypatch):
    area, contenido = _area_con(200)
    padre = QWidget()
    QVBoxLayout(padre).addWidget(area)
    qtbot.addWidget(padre)
    tomado = area.takeWidget()
    assert tomado is contenido
    assert area.widget() is None
    llamadas = []
    original = AreaInterna.updateGeometry
    monkeypatch.setattr(
        AreaInterna, "updateGeometry", lambda self: (llamadas.append(1), original(self))[1]
    )
    QApplication.sendEvent(tomado, QEvent(QEvent.Type.LayoutRequest))
    _asentar(qtbot)
    assert llamadas == []
    tomado.deleteLater()


def test_area_interna_take_widget_sin_contenido_devuelve_none(qtbot):
    area = AreaInterna()
    qtbot.addWidget(area)
    assert area.takeWidget() is None


# --- 2. Ventana principal: formulario y columna derecha sin recorte ---------------------------


def test_avanzado_con_area_holgada_ninguna_zona_muestra_barra_horizontal(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_HOLGADA)
    assert (v.width(), v.height()) == (ANCHO, ALTO)
    zonas = _internas(v)
    assert zonas, "no se encontraron zonas desplazables"
    for zona in zonas:
        if zona.isVisible():
            assert not _barra_h_visible(zona), f"barra horizontal en {zona.widget()!r}"
    assert not _barra_h_visible(_area_externa(v))


def test_avanzado_con_area_holgada_el_formulario_no_se_recorta(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_HOLGADA)
    zonas = [z for z in _internas(v) if z.isVisible() and z.widget() is not None]
    assert zonas
    for zona in zonas:
        minimo = zona.widget().minimumSizeHint().width()
        assert zona.viewport().width() >= minimo, (
            f"{zona.widget()!r}: viewport {zona.viewport().width()} < mínimo {minimo}"
        )


def test_avanzado_con_area_holgada_el_formulario_cabe_y_el_widget_no_excede_el_viewport(
    qtbot, entorno
):
    v = _preparar(qtbot, entorno, AREA_HOLGADA)
    izquierda = v.formulario.parentWidget()
    while izquierda is not None and not isinstance(
        izquierda.parentWidget().parentWidget(), AreaInterna
    ):
        izquierda = izquierda.parentWidget()
    assert izquierda is not None
    zona = izquierda.parentWidget().parentWidget()
    assert izquierda.width() <= zona.viewport().width()


def test_basico_con_area_holgada_tampoco_hay_barras_horizontales(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_HOLGADA, modo=Modo.BASICO)
    for zona in _internas(v):
        if zona.isVisible():
            assert not _barra_h_visible(zona)
    assert not _barra_h_visible(_area_externa(v))


# --- 3. Espacio escaso: acotada y con barra horizontal externa --------------------------------


def test_avanzado_con_area_escasa_no_supera_el_area_util(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_ESCASA)
    aj = v.ajuste_pantalla
    assert v.width() <= aj.limite_ancho()
    assert v.height() <= aj.limite_alto()


def test_avanzado_con_area_escasa_la_barra_horizontal_es_la_externa(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_ESCASA)
    externa = _area_externa(v)
    assert externa.horizontalScrollBar().isVisible()
    assert externa.horizontalScrollBar().maximum() > 0


def test_avanzado_con_area_escasa_las_zonas_internas_no_recortan(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_ESCASA)
    for zona in _internas(v):
        if zona.isVisible() and zona.widget() is not None:
            assert not _barra_h_visible(zona), f"barra interna en {zona.widget()!r}"
            assert zona.viewport().width() >= zona.widget().minimumSizeHint().width()


# --- 4. Panel «Tiempo agotado» a 1240 ---------------------------------------------------------


def _crear_hasta_terminar(qtbot, entorno, res, creacion=None):
    from .capturas_guia.escenario import inventario_guia_cluster

    entorno.creacion = creacion or CreacionFalsa(res)
    entorno.inv = inventario_guia_cluster()
    v = entorno.ventana
    v.ajuste_pantalla.ancho_disponible, v.ajuste_pantalla.alto_disponible = AREA_HOLGADA
    v.ajuste_pantalla.reajustar()
    conectar(qtbot, entorno, sesion_falsa(perfil("p1", "Oficina", ("pve.lab",))))
    v.statusBar().setSizeGripEnabled(False)
    v.resize(ANCHO, ALTO)
    v.show()
    qtbot.waitExposed(v)
    poner_nombre(qtbot, v, "srv-web-01")
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=8000)
    qtbot.wait(300)
    return v


def test_tiempo_agotado_los_botones_caben_y_no_hay_barra_horizontal(qtbot, entorno):
    v = _crear_hasta_terminar(qtbot, entorno, resultado(Desenlace.TIEMPO_AGOTADO))
    p = v.progreso
    botones = [p.boton_seguir, p.boton_comprobar, p.boton_volver]
    for boton in botones:
        assert boton.isVisible(), boton.text()
        assert boton.width() >= boton.sizeHint().width(), (
            f"{boton.text()!r}: {boton.width()} < {boton.sizeHint().width()}"
        )
    zona_derecha = v._pila_derecha.widget(0)
    assert isinstance(zona_derecha, AreaInterna)
    assert not _barra_h_visible(zona_derecha)
    assert zona_derecha.viewport().width() >= zona_derecha.widget().minimumSizeHint().width()
    assert (v.width(), v.height()) == (ANCHO, ALTO)


# --- 5. Etapas al terminar --------------------------------------------------------------------


class CreacionConEtapas(CreacionFalsa):
    """Emite la secuencia completa de etapas del servicio real, con pausa opcional entre ellas."""

    def __init__(self, res, pausa: float = 0.0, con_ajustes: bool = False, con_listo=True):
        super().__init__(res)
        self.pausa = pausa
        self.con_ajustes = con_ajustes
        self.con_listo = con_listo

    def _emitir(self, al_cambiar_etapa, etapa):
        al_cambiar_etapa(etapa)
        if self.pausa:
            time.sleep(self.pausa)

    def crear(self, cfg, inv, al_cambiar_etapa, cancelado, *, al_enviar=None, puede_enviar=None):
        self.llamadas_crear += 1
        self.cfgs_recibidas.append(cfg)
        self._emitir(al_cambiar_etapa, Etapa.VALIDANDO)
        self._emitir(al_cambiar_etapa, Etapa.ENVIANDO)
        if al_enviar is not None:
            al_enviar(UPID)
        self._emitir(al_cambiar_etapa, Etapa.CREANDO)
        self._emitir(al_cambiar_etapa, Etapa.COMPROBANDO)
        if self.con_ajustes:
            self._emitir(al_cambiar_etapa, Etapa.AJUSTANDO)
        if self.con_listo:
            self._emitir(al_cambiar_etapa, Etapa.LISTO)
        if isinstance(self.resultado, BaseException):
            raise self.resultado
        return self.resultado


def _etiquetas_visibles(panel: PanelProgreso) -> dict[Etapa, str]:
    return {e: lbl.text() for e, lbl in panel._lbl_etapas.items() if not lbl.isHidden()}


def _etapas_visibles(panel: PanelProgreso) -> list[Etapa]:
    return [e for e, lbl in panel._lbl_etapas.items() if not lbl.isHidden()]


@pytest.mark.parametrize("pausa", [0.0, 0.15], ids=["instantaneo", "con_pausas"])
@pytest.mark.parametrize("desenlace", [Desenlace.OK, Desenlace.CON_AVISOS])
@pytest.mark.parametrize("con_listo", [True, False], ids=["motor_emite_listo", "motor_sin_listo"])
def test_etapas_una_maquina_ok_todas_con_visto_y_barra_al_maximo(
    qtbot, entorno, desenlace, pausa, con_listo
):
    res = resultado(desenlace, upid=UPID, vmid=101, nodo="pve1")
    v = _crear_hasta_terminar(
        qtbot, entorno, res, CreacionConEtapas(res, pausa=pausa, con_listo=con_listo)
    )
    p = v.progreso
    etiquetas = _etiquetas_visibles(p)
    assert len(etiquetas) == 5
    assert Etapa.AJUSTANDO not in etiquetas
    for etapa, texto in etiquetas.items():
        assert texto.startswith("✓"), f"{etapa.name}: {texto!r}"
    assert p.barra.value() == p.barra.maximum()
    assert p.barra.maximum() == 5


def test_etapas_clon_instantaneo_todas_las_visibles_con_visto(qtbot, entorno):
    """Limitación aceptada: una sola máquina muestra las etapas por sondeo del estado; si el clon
    termina antes del primer sondeo, «Ajustando» no llega a mostrarse (5 etapas), pero todas las
    visibles acaban con «✓» y la barra completa. Un clon real siempre dura más que un sondeo."""
    res = resultado(Desenlace.OK, upid=UPID, vmid=101, nodo="pve1")
    v = _crear_hasta_terminar(
        qtbot, entorno, res, CreacionConEtapas(res, pausa=0.0, con_ajustes=True)
    )
    p = v.progreso
    etiquetas = _etiquetas_visibles(p)
    assert len(etiquetas) in (5, 6)
    for etapa, texto in etiquetas.items():
        assert texto.startswith("✓"), f"{etapa.name}: {texto!r}"
    assert p.barra.value() == p.barra.maximum()


def test_etapas_clon_ok_las_seis_con_visto(qtbot, entorno):
    pausa = 0.15
    res = resultado(Desenlace.OK, upid=UPID, vmid=101, nodo="pve1")
    v = _crear_hasta_terminar(
        qtbot, entorno, res, CreacionConEtapas(res, pausa=pausa, con_ajustes=True)
    )
    p = v.progreso
    etiquetas = _etiquetas_visibles(p)
    assert len(etiquetas) == 6
    assert Etapa.AJUSTANDO in etiquetas
    for etapa, texto in etiquetas.items():
        assert texto.startswith("✓"), f"{etapa.name}: {texto!r}"
    assert p.barra.value() == p.barra.maximum() == 6


def test_etapas_panel_clon_ajustando_y_listo_dan_seis_con_visto(qtbot):
    """Unitario del panel: en un clon, AJUSTANDO muestra la sexta etapa y LISTO marca las seis."""
    p = PanelProgreso()
    qtbot.addWidget(p)
    p.show()
    p.iniciar()
    p.establecer_etapa(Etapa.AJUSTANDO)
    assert len(_etapas_visibles(p)) == 6
    p.establecer_etapa(Etapa.LISTO)
    assert all(t.startswith("✓") for t in _etiquetas_visibles(p).values())
    assert p.barra.value() == p.barra.maximum() == 6


def test_etapas_doble_sin_etapas_intermedias_igual_marca_todo_al_terminar_bien(qtbot, entorno):
    """Con el doble común (que solo llega a CREANDO) el cierre exitoso completa el panel."""
    res = resultado(Desenlace.OK, upid=UPID, vmid=101, nodo="pve1")
    v = _crear_hasta_terminar(qtbot, entorno, res)
    p = v.progreso
    assert all(t.startswith("✓") for t in _etiquetas_visibles(p).values())
    assert p.barra.value() == p.barra.maximum()


@pytest.mark.parametrize("pausa", [0.0, 0.15], ids=["instantaneo", "con_pausas"])
@pytest.mark.parametrize(
    "desenlace", [Desenlace.TIEMPO_AGOTADO, Desenlace.CONEXION_PERDIDA, Desenlace.ERROR]
)
def test_etapas_sin_exito_listo_no_lleva_visto(qtbot, entorno, desenlace, pausa):
    error = ErrorProxLaunch(CodigoError.SIN_ESPACIO, {"storage": "local-lvm"}, "sin espacio")
    kw = {"error": error} if desenlace == Desenlace.ERROR else {}
    res = resultado(desenlace, upid=UPID, vmid=101, nodo="pve1", **kw)
    # Sin LISTO: el motor real no lo emite cuando la creación no terminó bien.
    v = _crear_hasta_terminar(
        qtbot, entorno, res, CreacionConEtapas(res, pausa=pausa, con_listo=False)
    )
    p = v.progreso
    listo = p._lbl_etapas[Etapa.LISTO].text()
    assert not listo.startswith("✓"), listo
    assert p.barra.value() < p.barra.maximum()


def test_etapas_panel_listo_marca_todo_y_reiniciar_lo_limpia(qtbot):
    """Unitario del panel: LISTO completa las etapas y ``reiniciar`` las deja sin marcas."""
    p = PanelProgreso()
    qtbot.addWidget(p)
    p.iniciar()
    p.establecer_etapa(Etapa.CREANDO)
    assert not p._lbl_etapas[Etapa.LISTO].text().startswith("✓")
    p.establecer_etapa(Etapa.LISTO)
    assert all(t.startswith("✓") for t in _etapas_con_texto(p))
    assert p.barra.value() == p.barra.maximum()
    p.reiniciar()
    assert not any(t.startswith("✓") for t in _etapas_con_texto(p))
    assert p.barra.value() == 0


def _etapas_con_texto(p: PanelProgreso) -> list[str]:
    return [lbl.text() for lbl in p._lbl_etapas.values() if not lbl.isHidden()]


def test_comprobar_sin_upid_con_maquina_creada_completa_las_etapas(qtbot, entorno):
    """Ruta «Comprobar» de un envío incierto: si la máquina existe, el panel queda completo."""
    from .test_ventana_principal_f7 import _comprobar_y_esperar, _crear_incierto_con_cliente

    v, cliente = _crear_incierto_con_cliente(qtbot, entorno)
    cfg = v._lote.plan.elementos[0].cfg
    cliente.configs[cfg.vmid] = {"name": cfg.nombre, "tags": ";".join(cfg.etiquetas)}
    entorno.creacion.respuesta_existe_vm = True
    _comprobar_y_esperar(qtbot, v)
    p = v.progreso
    assert v._ultimo_resultado.desenlace == Desenlace.OK
    etiquetas = _etiquetas_visibles(p)
    assert etiquetas
    for etapa, texto in etiquetas.items():
        assert texto.startswith("✓"), f"{etapa.name}: {texto!r}"
    assert p.barra.value() == p.barra.maximum()


def test_comprobar_sin_upid_con_maquina_inexistente_listo_no_lleva_visto(qtbot, entorno):
    from .test_ventana_principal_f7 import _comprobar_y_esperar, _crear_incierto

    v = _crear_incierto(qtbot, entorno)
    entorno.creacion.respuesta_existe_vm = False
    _comprobar_y_esperar(qtbot, v)
    p = v.progreso
    assert v._ultimo_resultado.desenlace == Desenlace.CANCELADO
    assert not p._lbl_etapas[Etapa.LISTO].text().startswith("✓")
    assert p.barra.value() < p.barra.maximum()


# --- 6. Sin crecimiento espurio ---------------------------------------------------------------


def test_cambiar_de_modo_varias_veces_no_ensancha_la_ventana(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_HOLGADA, modo=Modo.BASICO)
    base = v.size()
    tamanos = []
    for _ in range(3):
        for modo in (Modo.AVANZADO, Modo.BASICO):
            v.establecer_modo(modo)
            qtbot.wait(150)
            _asentar(qtbot)
            tamanos.append(v.size())
    assert all(t.width() == base.width() for t in tamanos), [t.width() for t in tamanos]
    assert all(t.height() <= max(base.height(), ALTO) for t in tamanos)


def test_cambiar_de_pagina_varias_veces_no_ensancha_la_ventana(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_HOLGADA)
    base = v.size()
    for _ in range(3):
        v._paginas.setCurrentIndex(0)
        _asentar(qtbot)
        v._paginas.setCurrentIndex(1)
        _asentar(qtbot)
        assert v.width() == base.width(), v.width()
    assert v.size() == base


def test_cambiar_de_pagina_de_la_columna_derecha_no_ensancha_la_ventana(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_HOLGADA)
    base = v.size()
    for _ in range(3):
        for indice in (1, 2, 0):
            v._pila_derecha.setCurrentIndex(indice)
            _asentar(qtbot)
            assert v.width() <= max(base.width(), v.minimumSizeHint().width())
    assert v.width() == base.width()


def test_con_area_escasa_el_cambio_de_modo_no_acumula_ancho(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_ESCASA, modo=Modo.BASICO)
    limite = v.ajuste_pantalla.limite_ancho()
    anchos = []
    for _ in range(3):
        for modo in (Modo.AVANZADO, Modo.BASICO):
            v.establecer_modo(modo)
            qtbot.wait(150)
            _asentar(qtbot)
            assert v.width() <= limite
            anchos.append(v.width())
    # Tras la primera vuelta el ancho se estabiliza: no crece de forma acumulativa.
    assert max(anchos[2:]) <= max(anchos[:2]), anchos


def test_el_ancho_no_depende_del_historial_de_modos(qtbot, entorno):
    """Tras alternar de modo y volver al avanzado, el ancho es el de entrar directo al avanzado."""
    v = _preparar(qtbot, entorno, AREA_HOLGADA, modo=Modo.AVANZADO)
    directo = v.width()
    for _ in range(3):
        v.establecer_modo(Modo.BASICO)
        qtbot.wait(100)
        v.establecer_modo(Modo.AVANZADO)
        qtbot.wait(100)
    _asentar(qtbot)
    assert v.width() == directo
    assert QSize(v.width(), v.height()) == QSize(ANCHO, ALTO)


def test_avanzado_al_reducir_el_alto_ninguna_zona_interna_muestra_barra_horizontal(qtbot, entorno):
    v = _preparar(qtbot, entorno, AREA_HOLGADA)
    v.resize(ANCHO, 700)
    qtbot.wait(300)
    _asentar(qtbot)
    for zona in _internas(v):
        assert not _barra_h_visible(zona), zona.objectName() or type(zona).__name__
