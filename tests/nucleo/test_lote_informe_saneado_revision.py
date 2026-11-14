"""Saneado del informe tras la auditoría de seguridad (M1, B2): nombre del perfil sin host ni IP,
IPv6 en todas sus formas, usuarios con caracteres raros y formas codificadas como URL.

Se prueba contra la interfaz pública (``informe_desde_entradas``) y con ``volcar``, que recorre
todo el informe: lo que importa es que el texto que se comparte no contenga el dato sensible.
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.informe import informe_desde_entradas
from proxlaunch.nucleo.lote.modelos import EntradaLibro, EstadoMV, MetadatosInforme

from .apoyo_lote import crear_banco, definicion, volcar

HOST_DNS = "pve-prod.ejemplo.local"
IP4 = "192.168.77.10"
USUARIO_MAS = "john+ci@pve!ci"


def _metadatos(nombre: str) -> MetadatosInforme:
    return MetadatosInforme(
        nombre_perfil=nombre,
        version_proxmox="9.2.1",
        es_cluster=False,
        nombre_cluster=None,
        fecha_hora_local="2026-11-13T10:00:00",
    )


def _informe(nombre="produccion", *, mensaje="", detalle="", log=(), ocultar=()):
    plan = crear_banco().planificar(definicion(1, vmid_inicial=100))
    error = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"mensaje": mensaje}, detalle)
    entrada = EntradaLibro(
        plan.elementos[0], EstadoMV.ERROR, error=error, post_intentado=True, log_tarea=tuple(log)
    )
    return informe_desde_entradas(plan, (entrada,), _metadatos(nombre), (), 10.0, list(ocultar))


# --- M1: el nombre del perfil puede ser el host o la IP ----------------------------------------


@pytest.mark.parametrize("nombre", [IP4, HOST_DNS, HOST_DNS.upper(), f"  {IP4} "])
def test_m1_un_perfil_cuyo_nombre_es_la_ip_o_el_host_no_aparece_en_el_informe(nombre):
    informe = _informe(nombre, ocultar=[IP4, HOST_DNS])
    volcado = volcar(informe)
    assert IP4 not in volcado
    assert HOST_DNS.lower() not in volcado.lower()
    assert informe.metadatos.nombre_perfil.strip("… ") in ("—", "")


def test_m1_un_perfil_cuyo_nombre_es_el_usuario_tampoco_aparece():
    informe = _informe("svc_lote", ocultar=["svc_lote"])
    assert "svc_lote" not in volcar(informe)
    assert informe.metadatos.nombre_perfil == "—"


def test_m1_un_nombre_legitimo_se_conserva_y_solo_se_quita_lo_sensible():
    assert _informe("Producción", ocultar=[IP4]).metadatos.nombre_perfil == "Producción"
    mixto = _informe(f"Lab {IP4}", ocultar=[IP4]).metadatos.nombre_perfil
    assert IP4 not in mixto and mixto.startswith("Lab")


def test_m1_un_nombre_con_ip_se_oculta_aunque_no_se_pase_en_ocultar():
    # El saneado por patrón (IPv4) también se aplica al nombre del perfil.
    assert IP4 not in _informe(f"Lab {IP4}").metadatos.nombre_perfil


# --- B2: IPv6 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "direccion",
    [
        "2001:db8::1",
        "[2001:db8::1]",
        "[2001:db8::1]:8006",
        "2001:db8:85a3:0:0:8a2e:370:7334",
        "fe80::1%eth0",
        "fe80::a00:27ff:fe4e:66a1%enp0s3",
        "::1",
        "::ffff:192.0.2.1",
    ],
)
def test_b2_las_direcciones_ipv6_no_dejan_restos_en_error_detalle_ni_log(direccion):
    nucleo = direccion.strip("[]").split("]")[0].split("%")[0]
    informe = _informe(
        mensaje=f"sin respuesta de {direccion} tras 10 s",
        detalle=f"HTTPSConnectionPool(host='{direccion}', port=8006): timed out",
        log=(f"conectando a {direccion}", "línea neutra"),
    )
    volcado = volcar(informe)
    assert direccion not in volcado
    assert nucleo not in volcado
    assert "línea neutra" in volcado


def test_b2_una_url_con_ipv6_entre_corchetes_y_puerto_se_oculta_completa():
    informe = _informe(detalle="GET https://[2001:db8::1]:8006/api2/json/version falló")
    volcado = volcar(informe)
    assert "2001:db8" not in volcado
    assert "falló" in volcado


@pytest.mark.parametrize("texto", ["a las 12:30:45 del servidor", "ruta ::", "relación 3:1"])
def test_b2_lo_que_no_es_una_direccion_ipv6_se_conserva(texto):
    informe = _informe(mensaje=texto, detalle=texto, log=(texto,))
    assert texto in informe.entradas[0].error.params["mensaje"]
    assert texto in informe.entradas[0].error.detalle_tecnico
    assert texto in informe.entradas[0].log_tarea


# --- B2: usuarios y formas codificadas ---------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        f"autenticando a {USUARIO_MAS} ahora",
        f"usuario='{USUARIO_MAS}'",
        f"https://pve/api2/json?user={USUARIO_MAS}",
    ],
)
def test_b2_un_usuario_con_mas_y_token_no_deja_restos(texto):
    informe = _informe(mensaje=texto, detalle=texto, log=(texto,))
    volcado = volcar(informe)
    for resto in ("john", "+ci", "!ci", "@pve"):
        assert resto not in volcado, resto


@pytest.mark.parametrize("usuario", ["ana@pve!lab", "john+ci@pve!ci", "root@pam"])
def test_b2_la_forma_codificada_como_url_del_usuario_del_perfil_se_oculta(usuario):
    from urllib.parse import quote

    codificado = quote(usuario, safe="")
    informe = _informe(
        mensaje=f"GET /api2/json/access?userid={codificado}",
        detalle=f"url=https://pve/x?u={codificado}&otro=1",
        ocultar=[usuario],
    )
    volcado = volcar(informe)
    assert codificado not in volcado
    assert usuario not in volcado
    assert "otro=1" in volcado


def test_b2_el_token_suelto_tras_el_signo_de_exclamacion_no_queda():
    informe = _informe(detalle="token ana@pve!lab-ci expiró", ocultar=["ana@pve!lab-ci"])
    volcado = volcar(informe)
    assert "lab-ci" not in volcado and "ana" not in volcado
    assert "expiró" in volcado


def test_b2_la_ip_v4_y_v6_juntas_se_ocultan_y_el_resto_del_texto_sobrevive():
    informe = _informe(detalle=f"fallo {IP4} y 2001:db8::7 y {HOST_DNS}", ocultar=[HOST_DNS])
    detalle = informe.entradas[0].error.detalle_tecnico
    assert IP4 not in detalle and "2001:db8" not in detalle and HOST_DNS not in detalle
    assert detalle.startswith("fallo") and " y " in detalle
