"""Trabajador y Lanzador: trabajo fuera del hilo de la interfaz, señales y errores (RNF-01)."""

from __future__ import annotations

import threading

import pytest

from proxlaunch.interfaz import trabajadores as tr
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa

from .apoyo import UPID, CreacionFalsa, resultado, sesion_falsa


@pytest.fixture
def lanzador(qtbot):
    from PySide6.QtCore import QObject

    padre = QObject()
    lz = tr.Lanzador(padre)
    yield lz
    lz.esperar(2000)
    padre.deleteLater()


def _esperar_fin(qtbot, lanzador):
    qtbot.waitUntil(lambda: not lanzador.hay_activos, timeout=3000)


def test_resultado_llega_por_la_senal_terminado(qtbot):
    t = tr.Trabajador(lambda a, b: a + b, 2, 3)
    with qtbot.waitSignal(t.senales.terminado, timeout=2000) as senal:
        t.run()
    assert senal.args == [5]


def test_error_del_nucleo_llega_por_fallo_sin_cambios(qtbot):
    error = ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "100"})

    def falla():
        raise error

    t = tr.Trabajador(falla)
    with qtbot.waitSignal(t.senales.fallo, timeout=2000) as senal:
        t.run()
    assert senal.args[0] is error


def test_excepcion_inesperada_se_convierte_en_desconocido_sin_romper_el_hilo(qtbot):
    def falla():
        raise ValueError("secreto-123 falló")

    t = tr.Trabajador(falla)
    with qtbot.waitSignal(t.senales.fallo, timeout=2000) as senal:
        t.run()
    e = senal.args[0]
    assert e.codigo == CodigoError.DESCONOCIDO


def test_con_contexto_recibe_etapa_upid_y_cancelado(qtbot):
    vistos = {}

    def trabajo(*, al_cambiar_etapa, al_enviar, cancelado):
        vistos["cancelado"] = cancelado
        al_cambiar_etapa(Etapa.ENVIANDO)
        al_enviar(UPID)
        return "listo"

    t = tr.Trabajador(trabajo, con_contexto=True)
    etapas, upids = [], []
    t.senales.etapa.connect(etapas.append)
    t.senales.upid.connect(upids.append)
    with qtbot.waitSignal(t.senales.terminado, timeout=2000):
        t.run()
    assert etapas == [Etapa.ENVIANDO] and upids == [UPID]
    assert isinstance(vistos["cancelado"], threading.Event)


def test_cancelar_activa_el_evento_del_trabajador():
    t = tr.Trabajador(lambda: None)
    assert not t.cancelado.is_set()
    t.cancelar()
    assert t.cancelado.is_set()


def test_lanzador_ejecuta_en_otro_hilo_y_entrega_en_el_principal(qtbot, lanzador):
    hilo_trabajo = {}
    hilo_entrega = {}

    def trabajo():
        hilo_trabajo["id"] = threading.get_ident()
        return 7

    def entrega(valor):
        hilo_entrega["id"] = threading.get_ident()
        hilo_entrega["valor"] = valor

    lanzador.lanzar(trabajo, al_terminar=entrega)
    assert lanzador.hay_activos or hilo_entrega  # puede terminar rápido
    _esperar_fin(qtbot, lanzador)
    qtbot.waitUntil(lambda: "valor" in hilo_entrega, timeout=3000)
    assert hilo_entrega["valor"] == 7
    assert hilo_trabajo["id"] != threading.get_ident()
    assert hilo_entrega["id"] == threading.get_ident()


def test_lanzador_entrega_el_error_y_libera_el_trabajador(qtbot, lanzador):
    errores = []

    def falla():
        raise ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)

    lanzador.lanzar(falla, al_fallar=errores.append)
    qtbot.waitUntil(lambda: bool(errores), timeout=3000)
    assert errores[0].codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert not lanzador.hay_activos


def test_lanzador_sin_destinos_no_revienta(qtbot, lanzador):
    lanzador.lanzar(lambda: 1)
    lanzador.lanzar(lambda: (_ for _ in ()).throw(ErrorProxLaunch(CodigoError.DESCONOCIDO)))
    _esperar_fin(qtbot, lanzador)


def test_lanzador_entrega_etapas_y_upid_de_un_trabajo_con_contexto(qtbot, lanzador):
    servicio = CreacionFalsa(resultado(Desenlace.OK))
    etapas, upids, fin = [], [], []
    lanzador.lanzar(
        servicio.crear,
        object(),
        object(),
        con_contexto=True,
        al_etapa=etapas.append,
        al_upid=upids.append,
        al_terminar=fin.append,
    )
    qtbot.waitUntil(lambda: bool(fin), timeout=3000)
    assert etapas == [Etapa.VALIDANDO, Etapa.ENVIANDO, Etapa.CREANDO]
    assert upids == [UPID]
    assert fin[0].desenlace == Desenlace.OK


def test_cancelar_todos_activa_la_cancelacion_de_cada_trabajo(qtbot, lanzador):
    arrancado = threading.Event()
    visto = {}

    def espera(*, al_cambiar_etapa, al_enviar, cancelado):
        arrancado.set()
        visto["cancelado"] = cancelado.wait(5)  # espera real acotada, la despierta la prueba
        return None

    t = lanzador.lanzar(espera, con_contexto=True)
    assert arrancado.wait(3)
    lanzador.cancelar_todos()
    _esperar_fin(qtbot, lanzador)
    assert t.cancelado.is_set() and visto["cancelado"] is True


def test_esperar_devuelve_verdadero_con_el_pool_vacio(lanzador):
    assert lanzador.esperar(1000) is True


# --- Funciones de trabajo ------------------------------------------------------------------


def test_descubrir_y_comprobar_permisos_combina_ambos(monkeypatch, inv_cluster):
    monkeypatch.setattr(tr, "descubrir", lambda s: inv_cluster)
    monkeypatch.setattr(tr, "permisos_faltantes", lambda s: ["Sys.Audit"])
    inv, faltan = tr.descubrir_y_comprobar_permisos(sesion_falsa())
    assert inv is inv_cluster and faltan == ["Sys.Audit"]


def test_recargar_nodo_devuelve_nodo_storages_y_bridges(monkeypatch):
    monkeypatch.setattr(tr, "descubrir_nodo", lambda s, n: (["s"], ["b"]))
    assert tr.recargar_nodo(sesion_falsa(), "pve1") == ("pve1", ["s"], ["b"])


def test_reintentar_nodos_separa_recuperados_y_fallidos(monkeypatch):
    def descubrir_nodo(sesion, nodo):
        if nodo == "pve2":
            raise ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": nodo})
        return (["s"], ["b"])

    monkeypatch.setattr(tr, "descubrir_nodo", descubrir_nodo)
    recuperados, fallidos = tr.reintentar_nodos(sesion_falsa(), ["pve1", "pve2"])
    assert recuperados == {"pve1": (["s"], ["b"])}
    assert list(fallidos) == ["pve2"]


class _ClienteVmid:
    def __init__(self, ocupados, siguiente=200):
        self.ocupados = ocupados
        self.siguiente = siguiente

    def proximo_vmid(self, vmid=None):
        if vmid is not None and vmid in self.ocupados:
            raise ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": str(vmid)})
        return vmid if vmid is not None else self.siguiente


def _sesion_con_cliente(cliente):
    s = sesion_falsa()
    s.cliente = cliente
    return s


def test_comprobar_vmid_libre_devuelve_none():
    assert tr.comprobar_vmid(_sesion_con_cliente(_ClienteVmid({100})), 150) == (150, None)


def test_comprobar_vmid_ocupado_devuelve_el_siguiente():
    assert tr.comprobar_vmid(_sesion_con_cliente(_ClienteVmid({100})), 100) == (100, "200")


def test_comprobar_vmid_propaga_otros_errores():
    class Cliente:
        def proximo_vmid(self, vmid=None):
            raise ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)

    with pytest.raises(ErrorProxLaunch) as e:
        tr.comprobar_vmid(_sesion_con_cliente(Cliente()), 100)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE


def test_reanudar_comprobar_una_vez_marca_listo_si_termino():
    servicio = CreacionFalsa(resultado())
    servicio.respuestas_reanudar = [resultado(Desenlace.OK)]
    etapas = []
    res = tr.reanudar_seguimiento(
        servicio, object(), UPID, True, al_cambiar_etapa=etapas.append, cancelado=threading.Event()
    )
    assert res.desenlace == Desenlace.OK
    assert etapas == [Etapa.CREANDO, Etapa.LISTO]
    assert servicio.llamadas_reanudar == ["comprobar"]


def test_reanudar_comprobar_una_vez_sin_terminar_no_marca_listo():
    servicio = CreacionFalsa(resultado())
    servicio.respuestas_reanudar = [resultado(Desenlace.TIEMPO_AGOTADO)]
    etapas = []
    tr.reanudar_seguimiento(
        servicio, object(), UPID, True, al_cambiar_etapa=etapas.append, cancelado=threading.Event()
    )
    assert etapas == [Etapa.CREANDO]


def test_reanudar_seguir_esperando_usa_seguir_y_no_vuelve_a_crear():
    servicio = CreacionFalsa(resultado())
    servicio.respuestas_reanudar = [resultado(Desenlace.CON_AVISOS)]
    res = tr.reanudar_seguimiento(
        servicio,
        object(),
        UPID,
        False,
        al_cambiar_etapa=lambda e: None,
        cancelado=threading.Event(),
        al_enviar=lambda u: None,
    )
    assert res.desenlace == Desenlace.CON_AVISOS
    assert servicio.llamadas_reanudar == ["seguir"]
    assert servicio.llamadas_crear == 0  # CA-20.6: nunca se vuelve a crear
