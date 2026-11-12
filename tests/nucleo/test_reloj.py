"""Reloj real y simulado (inyectable; CA-03.1, CA-20.x usan RelojSimulado)."""

import time

from proxlaunch.nucleo import reloj as modulo_reloj
from proxlaunch.nucleo.reloj import RelojReal, RelojSimulado


def test_simulado_empieza_en_el_instante_indicado():
    assert RelojSimulado().ahora() == 0.0
    assert RelojSimulado(inicio=100).ahora() == 100.0


def test_simulado_dormir_avanza_sin_esperar():
    reloj = RelojSimulado()
    inicio = time.monotonic()
    reloj.dormir(3600)
    assert reloj.ahora() == 3600.0
    assert time.monotonic() - inicio < 1


def test_simulado_ca03_1_ticket_de_105_minutos():
    reloj = RelojSimulado()
    reloj.avanzar(105 * 60)
    assert reloj.ahora() == 6300.0


def test_simulado_ignora_avances_negativos_o_nulos():
    reloj = RelojSimulado(10)
    reloj.avanzar(-5)
    reloj.dormir(0)
    reloj.dormir(-1)
    assert reloj.ahora() == 10.0


def test_simulado_acumula_varios_avances():
    reloj = RelojSimulado()
    for _ in range(4):
        reloj.dormir(1.5)
    assert reloj.ahora() == 6.0


def test_real_es_monotonico():
    reloj = RelojReal()
    a = reloj.ahora()
    b = reloj.ahora()
    assert b >= a


def test_real_dormir_delega_en_sleep_solo_si_hay_tiempo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(modulo_reloj.time, "sleep", llamadas.append)
    reloj = RelojReal()
    reloj.dormir(0)
    reloj.dormir(-2)
    reloj.dormir(0.5)
    assert llamadas == [0.5]
