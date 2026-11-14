"""Saneado del informe con ``ocultar`` (CA-L19.3, RNF-L06): ni el host DNS del perfil ni el
usuario aparecen en parámetros, detalle técnico, log, problemas del plan ni rollback.

Se prueba contra la interfaz pública (``construir_informe`` / ``informe_desde_entradas``) con
centinelas únicos: lo que importa es que el informe, que se comparte, no los contenga.
"""

from __future__ import annotations

import dataclasses

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.informe import construir_informe, informe_desde_entradas
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    EntradaLibro,
    EstadoMV,
    EstadoRollback,
    MetadatosInforme,
    Problema,
    ResultadoRollback,
    Severidad,
)

from .apoyo_lote import crear_banco, definicion, volcar

HOST_DNS = "pve-prod.ejemplo.local"
USUARIO_PERFIL = "svc_lote"  # sin forma usuario@realm: solo ``ocultar`` puede quitarlo
USUARIO_TOKEN = "ana@pve!centinela"
OCULTAR = [HOST_DNS, USUARIO_PERFIL, USUARIO_TOKEN]

METADATOS = MetadatosInforme(
    nombre_perfil="produccion",
    version_proxmox="9.2.1",
    es_cluster=False,
    nombre_cluster=None,
    fecha_hora_local="2026-11-13T10:00:00",
)


@pytest.fixture
def plan():
    return crear_banco().planificar(definicion(2, vmid_inicial=100))


def _error() -> ErrorProxLaunch:
    """Error de red con el host y el usuario repartidos por todos los campos de texto libre."""
    return ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE,
        {
            "mensaje": f"sin respuesta de {HOST_DNS}:8006 para {USUARIO_PERFIL}",
            "otro": f"token {USUARIO_TOKEN}",
            "puerto": "8006",
        },
        f"HTTPSConnectionPool(host='{HOST_DNS}', port=8006): Read timed out ({USUARIO_PERFIL})",
    )


def _informe(plan, **kw):
    primera, segunda = plan.elementos
    entradas = (
        EntradaLibro(
            primera,
            EstadoMV.ERROR,
            error=_error(),
            post_intentado=True,
            log_tarea=(
                f"conectando a {HOST_DNS}",
                f"usuario {USUARIO_PERFIL} autenticado",
                "línea neutra",
            ),
            upid=f"UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:100:{USUARIO_TOKEN}:",
        ),
        EntradaLibro(segunda, EstadoMV.OK, post_intentado=True),
    )
    return informe_desde_entradas(
        plan,
        entradas,
        METADATOS,
        kw.pop("rollback", ()),
        10.0,
        kw.pop("ocultar", OCULTAR),
    )


def test_ca_l19_3_el_hostname_dns_del_perfil_no_sale_en_parametros_detalle_ni_log(plan):
    informe = _informe(plan)
    assert HOST_DNS not in volcar(informe)
    e = informe.entradas[0]
    assert all(HOST_DNS not in v for v in e.error.params.values())
    assert HOST_DNS not in e.error.detalle_tecnico
    assert all(HOST_DNS not in linea for linea in e.log_tarea)


def test_ca_l19_3_el_usuario_del_perfil_no_sale_en_parametros_detalle_ni_log(plan):
    informe = _informe(plan)
    texto = volcar(informe)
    assert USUARIO_PERFIL not in texto
    assert USUARIO_TOKEN not in texto
    assert "ana@pve" not in texto


def test_ca_l19_3_ocultar_conserva_el_resto_del_contenido_util(plan):
    """Solo se quita lo sensible: el código, el puerto y las líneas neutras se mantienen."""
    informe = _informe(plan)
    e = informe.entradas[0]
    assert e.error.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert e.error.params["puerto"] == "8006"
    assert "línea neutra" in e.log_tarea
    assert informe.entradas[1].estado == EstadoMV.OK


def test_ca_l19_3_ocultar_tambien_limpia_los_problemas_del_plan(plan):
    problema = Problema(
        "V-L09",
        Severidad.AVISO,
        params={"detalle": f"{HOST_DNS} no respondió a {USUARIO_PERFIL}", "nodo": "pve1"},
    )
    plan2 = dataclasses.replace(plan, problemas=(problema,))
    informe = _informe(plan2)
    assert HOST_DNS not in volcar(informe.problemas_plan)
    assert USUARIO_PERFIL not in volcar(informe.problemas_plan)
    assert informe.problemas_plan[0].params["nodo"] == "pve1"


def test_ca_l19_3_ocultar_tambien_limpia_el_error_del_rollback(plan):
    rb = ResultadoRollback(
        100,
        "pve1",
        "web-01",
        EstadoRollback.FALLO,
        upid=f"UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmdestroy:100:{USUARIO_TOKEN}:",
        error=_error(),
    )
    informe = _informe(plan, rollback=(rb,))
    texto = volcar(informe.rollback)
    for prohibido in (HOST_DNS, USUARIO_PERFIL, USUARIO_TOKEN):
        assert prohibido not in texto, prohibido


def test_ca_l19_3_construir_informe_desde_el_libro_aplica_el_mismo_saneado(plan):
    """La ruta del libro (no solo la de instantáneas) acepta ``ocultar`` y lo aplica."""
    banco = crear_banco()
    plan2 = banco.planificar(definicion(1, vmid_inicial=100))
    libro = Libro(plan2)
    vmid = plan2.elementos[0].vmid
    libro.iniciar(vmid, 0.0)
    libro.marcar_post_intentado(vmid, 0.0)
    libro.finalizar(
        vmid,
        EstadoMV.ERROR,
        error=_error(),
        t_fin=1.0,
        log=[f"conectando a {HOST_DNS}", f"usuario {USUARIO_PERFIL}"],
    )
    informe = construir_informe(
        plan2, libro, METADATOS, reloj=banco.reloj, ocultar=[HOST_DNS, USUARIO_PERFIL]
    )
    texto = volcar(informe)
    assert HOST_DNS not in texto and USUARIO_PERFIL not in texto


def test_ca_l19_3_ocultar_ignora_valores_vacios_y_no_borra_todo(plan):
    informe = _informe(plan, ocultar=["", HOST_DNS])
    assert "línea neutra" in informe.entradas[0].log_tarea
    assert HOST_DNS not in volcar(informe)


def test_ca_l19_3_ocultar_un_valor_corto_y_otro_largo_que_lo_contiene_no_deja_restos(plan):
    """Se quitan primero los valores más largos: ``pve-prod`` no deja ``.ejemplo.local``."""
    informe = _informe(plan, ocultar=["pve-prod", HOST_DNS, USUARIO_PERFIL, USUARIO_TOKEN])
    texto = volcar(informe)
    assert ".ejemplo.local" not in texto and "pve-prod" not in texto


def test_ca_l19_3_el_hostname_se_oculta_aunque_cambie_la_capitalizacion(plan):
    """Los nombres DNS no distinguen mayúsculas: el mensaje de una librería HTTP puede traer
    el host normalizado o tal como lo escribió la persona."""
    entradas = (
        EntradaLibro(
            plan.elementos[0],
            EstadoMV.ERROR,
            post_intentado=True,
            error=ErrorProxLaunch(
                CodigoError.SERVIDOR_NO_RESPONDE,
                {"m": "PVE-PROD.Ejemplo.LOCAL"},
                "PVE-Prod.ejemplo.local",
            ),
        ),
    )
    informe = informe_desde_entradas(plan, entradas, METADATOS, (), 1.0, [HOST_DNS])
    assert "ejemplo.local" not in volcar(informe).lower()
