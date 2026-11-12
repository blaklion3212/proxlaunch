"""RelojReal (ronda F7): usa CLOCK_BOOTTIME cuando existe, sin depender del SO de la prueba."""

import time

from proxlaunch.nucleo.reloj import RelojReal


def test_ahora_usa_clock_boottime_si_esta_disponible(monkeypatch):
    llamadas = []

    def falso(reloj_id):
        llamadas.append(reloj_id)
        return 12345.5

    monkeypatch.setattr(time, "CLOCK_BOOTTIME", 77, raising=False)
    monkeypatch.setattr(time, "clock_gettime", falso, raising=False)
    assert RelojReal().ahora() == 12345.5
    assert llamadas == [77]


def test_ahora_sin_clock_boottime_usa_monotonic(monkeypatch):
    monkeypatch.delattr(time, "CLOCK_BOOTTIME", raising=False)
    monkeypatch.setattr(time, "monotonic", lambda: 42.0)
    assert RelojReal().ahora() == 42.0


def test_ahora_si_clock_gettime_falla_cae_a_monotonic(monkeypatch):
    def falla(_id):
        raise OSError("no soportado")

    monkeypatch.setattr(time, "CLOCK_BOOTTIME", 77, raising=False)
    monkeypatch.setattr(time, "clock_gettime", falla, raising=False)
    monkeypatch.setattr(time, "monotonic", lambda: 7.0)
    assert RelojReal().ahora() == 7.0


def test_ahora_es_no_decreciente():
    reloj = RelojReal()
    a = reloj.ahora()
    assert reloj.ahora() >= a
