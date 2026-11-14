"""Interfaz del lote: respuesta, coalescencia, rendimiento y robustez (RNF-L01, RNF-L05, RNF-L11,
CA-L13.5, CA-L10.5)."""

from __future__ import annotations

import dataclasses
import threading
import time

import pytest

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, ProgresoLote
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import ACTUALIZACIONES_POR_S
from proxlaunch.nucleo.lote.modelos import EstadoMV

from . import test_ventana_principal as _base
from .apoyo import ClienteLoteFalso, CreacionPorVmid, inventario_individual
from .apoyo_lote import entradas_de
from .apoyo_ventana_lote import (
    crear_lote,
    esperar_fin,
    estados,
    preparar_lote,
    ver_resumen,
)
from .test_lote_progreso import plan_vacio

entorno = _base.entorno
EM = EstadoMV


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Todas las pruebas de este módulo cierran sin bloquear."""


class ClienteLento(ClienteLoteFalso):
    """Cliente cuya reserva de VMIDs queda retenida hasta liberarla (simula una red lenta)."""

    def __init__(self) -> None:
        super().__init__()
        self.liberar = threading.Event()
        self.entro = threading.Event()

    def vmid_libre(self, vmid):
        self.entro.set()
        self.liberar.wait(5)
        return super().vmid_libre(vmid)


# --- RNF-L01: la interfaz no se congela ------------------------------------------------------


def test_rnf_l01_planificar_con_un_servidor_lento_no_bloquea_el_hilo_de_la_interfaz(qtbot, entorno):
    cliente = ClienteLento()
    preparar_lote(qtbot, entorno, cantidad=3, cliente=cliente)
    v = entorno.ventana
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    inicio = time.perf_counter()
    v.resumen.boton_crear.click()
    assert cliente.entro.wait(5)
    # El clic vuelve de inmediato aunque cada consulta al servidor tarde (< 200 ms).
    assert time.perf_counter() - inicio < 0.2
    assert v._planificando and v.resumen_lote._titulo.text() == "Preparando el resumen…"
    assert not v.resumen_lote.boton_crear.isEnabled()
    # Mientras tanto la interfaz sigue atendiendo eventos.
    qtbot.wait(1)
    cliente.liberar.set()
    qtbot.waitUntil(lambda: not v._planificando, timeout=5000)
    assert v.resumen_lote.plan is not None


def test_rnf_l01_iniciar_un_lote_no_espera_a_que_las_maquinas_terminen(qtbot, entorno):
    puertas = {101: threading.Event()}
    creacion = CreacionPorVmid(puertas=puertas)
    preparar_lote(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    inicio = time.perf_counter()
    crear_lote(qtbot, v)
    assert time.perf_counter() - inicio < 0.2
    assert v._lote_en_curso
    puertas[101].set()
    esperar_fin(qtbot, v)


# --- CA-L13.5: coalescencia -----------------------------------------------------------------------


def test_ca_l13_5_el_temporizador_de_la_interfaz_refresca_como_mucho_diez_veces_por_segundo(
    qtbot, entorno
):
    assert ACTUALIZACIONES_POR_S == 10
    assert entorno.ventana._timer_lote.interval() == 1000 // ACTUALIZACIONES_POR_S == 100


def test_ca_l13_5_cientos_de_eventos_producen_un_solo_refresco_por_tick(
    qtbot, entorno, monkeypatch
):
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    preparar_lote(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)
    v._tick_lote()  # asimila lo pendiente
    llamadas = []
    original = v.progreso_lote.actualizar
    monkeypatch.setattr(v.progreso_lote, "actualizar", lambda e: (llamadas.append(1), original(e)))
    e0 = v._lote.puente.instantanea()[0]
    for _ in range(300):
        v._lote.puente.observar(e0)
    v._tick_lote()
    v._tick_lote()  # sin cambios nuevos: no repinta
    assert llamadas == [1]
    puerta.set()


def test_rnf_l05_actualizar_la_tabla_de_cien_filas_es_rapido(qtbot):
    p = ProgresoLote()
    qtbot.addWidget(p)
    p.show()
    p.iniciar(plan_vacio(100))
    inicio = time.perf_counter()
    for i in range(10):
        p.actualizar(entradas_de([EM.OK] * (i * 10) + [EM.CREANDO] * (100 - i * 10)))
    assert time.perf_counter() - inicio < 1.0
    assert p.texto_resumen_barra.startswith("90 de 100 terminadas")


def test_ca_l10_5_un_lote_de_cien_maquinas_de_punta_a_punta(qtbot, entorno, confirmaciones):
    inv = inventario_individual()
    grande = {
        "pve": tuple(
            dataclasses.replace(s, libre_bytes=s.libre_bytes * 100, total_bytes=s.total_bytes * 100)
            for s in inv.storages["pve"]
        )
    }
    entorno.inv = dataclasses.replace(inv, storages=grande, proximo_vmid=1000)
    creacion = CreacionPorVmid()
    preparar_lote(qtbot, entorno, cantidad=100, prefijo="vm", creacion=creacion, nodo=None)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    assert v.resumen_lote.modelo.rowCount() == 100
    assert v.resumen_lote.plan.bloqueado is False
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v, timeout=30000)
    assert len(confirmaciones.llamadas) == 1  # más de 10: doble confirmación
    assert "Se enviarán 100 máquinas a Proxmox" in confirmaciones.llamadas[0][1]
    assert estados(v) == ["ok"] * 100
    assert v.progreso_lote.texto_resumen_barra == "100 de 100 terminadas"
    assert v.progreso_lote.modelo.rowCount() == 100
    assert sorted(creacion.vmids_creados) == list(range(1000, 1100))


# --- RNF-L11: robustez ----------------------------------------------------------------------------


def test_rnf_l11_si_el_motor_falla_la_interfaz_no_se_queda_ocupada(qtbot, entorno, monkeypatch):
    preparar_lote(qtbot, entorno, cantidad=3)
    v = entorno.ventana
    ver_resumen(qtbot, v)

    def explota(*a, **k):
        raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom")

    monkeypatch.setattr(vp, "ejecutar_lote", explota)
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: v._lote.terminado, timeout=5000)
    assert not v._lote_en_curso and v.progreso_lote.fase == FaseLote.TERMINADO
    assert v.progreso_lote._error.text().startswith("El lote terminó de forma inesperada")
    assert v.boton_actualizar.isEnabled()  # los botones de red se liberan
    assert v.progreso_lote.boton_volver.isVisible()


def test_rnf_l11_una_excepcion_inesperada_del_motor_con_una_maquina_libera_la_interfaz(
    qtbot, entorno, monkeypatch
):
    from .test_ventana_principal import conectar, crear_y_esperar, poner_nombre

    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    monkeypatch.setattr(
        vp, "ejecutar_lote", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    crear_y_esperar(qtbot, v)
    assert not v._creando  # no se queda «creando» para siempre
    assert v.progreso._mensaje.isVisible()


def test_rnf_l11_una_excepcion_al_pintar_no_detiene_el_motor(qtbot, entorno, monkeypatch):
    puerta = threading.Event()
    creacion = CreacionPorVmid(puertas={101: puerta})
    preparar_lote(qtbot, entorno, cantidad=3, creacion=creacion)
    v = entorno.ventana
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: creacion.entro(101).is_set(), timeout=4000)

    original = v.progreso_lote.actualizar

    def falla(entradas):
        raise RuntimeError("fallo al pintar")

    monkeypatch.setattr(v.progreso_lote, "actualizar", falla)
    with qtbot.capture_exceptions() as excepciones:
        v._despertar_timer()
        v._lote.puente.observar(v._lote.puente.instantanea()[0])  # hay algo que pintar
        qtbot.waitUntil(lambda: bool(excepciones), timeout=3000)  # el tick real lanzó
    assert "fallo al pintar" in str(excepciones[0][1])
    monkeypatch.setattr(v.progreso_lote, "actualizar", original)
    puerta.set()
    esperar_fin(qtbot, v)
    assert estados(v) == ["ok", "ok", "ok"]  # el motor siguió y terminó
    assert sorted(creacion.vmids_creados) == [101, 102, 103]
