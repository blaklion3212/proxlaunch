"""Permisos que no se pudieron leer (CA-L09.4): el plan se marca, no se bloquea y el aviso
llega al informe. Con permisos leídos (suficientes o no) el plan sí está verificado."""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.informe import construir_informe
from proxlaunch.nucleo.lote.modelos import MetadatosInforme
from proxlaunch.nucleo.lote.simulacion import simular

from .apoyo_lote import definicion, nodo_caido

METADATOS = MetadatosInforme("lab", "9.2.1", False, None, "2026-11-13T10:00:00")
_PERMISOS = r"^/access/permissions$"


@pytest.fixture
def banco():
    from .apoyo_lote import crear_banco

    return crear_banco(("pve1",))


def _reglas(plan, regla):
    return [p for p in plan.problemas if p.regla == regla]


@pytest.mark.parametrize(
    "fallo",
    [
        nodo_caido("pve1", 596),
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE),
        ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE),
    ],
    ids=["596", "403", "sin_respuesta"],
)
def test_ca_l09_4_si_falla_la_lectura_de_permisos_el_plan_queda_marcado_y_no_se_bloquea(
    banco, fallo
):
    banco.cluster.regla("GET", _PERMISOS, fallo)
    plan = banco.planificar(definicion(2))
    assert plan.permisos_verificados is False
    assert not plan.bloqueado and not _reglas(plan, "V-L16")
    assert len(plan.elementos) == 2  # el plan sigue siendo completo


def test_ca_l09_4_con_permisos_leidos_el_plan_esta_verificado(banco):
    plan = banco.planificar(definicion(2))
    assert plan.permisos_verificados is True


def test_ca_l09_4_con_permisos_insuficientes_leidos_esta_verificado_y_bloquea(banco):
    """Leer los permisos y ver que falta VM.Allocate NO es «no verificado»: es un error."""
    banco.cluster.permisos = {"/": {"VM.Audit": 1, "Sys.Audit": 1}}
    plan = banco.planificar(definicion(2))
    assert plan.permisos_verificados is True
    assert plan.bloqueado and _reglas(plan, "V-L16")


def test_ca_l09_4_el_informe_arrastra_que_los_permisos_no_se_verificaron(banco):
    banco.cluster.regla("GET", _PERMISOS, nodo_caido("pve1", 596))
    plan = banco.planificar(definicion(2))
    libro = banco.ejecutar(plan)
    informe = construir_informe(plan, libro, METADATOS, reloj=banco.reloj)
    assert informe.permisos_verificados is False
    # El lote se ejecuta con normalidad pese al aviso.
    assert banco.estados(libro) == ["ok", "ok"]


def test_ca_l09_4_el_informe_de_un_plan_verificado_lo_indica(banco):
    plan = banco.planificar(definicion(1))
    libro = banco.ejecutar(plan)
    assert construir_informe(plan, libro, METADATOS, reloj=banco.reloj).permisos_verificados


def test_ca_l09_4_la_simulacion_tambien_marca_los_permisos_no_verificados(banco):
    banco.cluster.regla("GET", _PERMISOS, nodo_caido("pve1", 596))
    resultado = simular(banco.sesion, definicion(2), banco.inv, reloj=banco.reloj)
    assert resultado.plan.permisos_verificados is False
    assert resultado.plan.es_simulacion and not resultado.plan.bloqueado
    assert banco.cluster.solo_lecturas  # y aun así no escribió nada
