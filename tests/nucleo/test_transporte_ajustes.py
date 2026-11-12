"""Transporte: reglas de failover según método y momento del fallo (RF-07, CA-07.x).

GET: failover ante errores de red y 595/596, nunca ante 401/403. POST: solo si el fallo
fue anterior al envío; si pudo haber llegado al servidor no se reintenta (evita duplicar).
"""

import pytest
import requests
import urllib3

from proxlaunch.nucleo.api.transporte import TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

from .apoyo_api import HUELLA_A, agregar_error, url

A = "10.0.0.1"
B = "10.0.0.2"
RUTA_POST = "/nodes/pve1/qemu"
UPID_OK = {"data": "UPID:pve1:x"}


def _http():
    return TransporteHttp([A, B], 8006, huellas={A: HUELLA_A, B: HUELLA_A})


def _nueva_conexion():
    """ConnectionError tal como lo produce requests cuando no se pudo abrir el socket."""
    causa = urllib3.exceptions.NewConnectionError(None, "no route to host")
    return requests.exceptions.ConnectionError(causa)


def _conexion_cortada():
    """Conexión cortada DESPUÉS de enviar la petición (sin certeza de que no llegó)."""
    causa = urllib3.exceptions.ProtocolError("Connection aborted.", ConnectionResetError(104))
    return requests.exceptions.ConnectionError(causa)


# --- GET: failover --------------------------------------------------------------------


@pytest.mark.parametrize(
    "fallo",
    [
        pytest.param(_nueva_conexion(), id="conexion-rechazada"),
        pytest.param(_conexion_cortada(), id="conexion-cortada"),
        pytest.param(requests.exceptions.ReadTimeout("lento"), id="read-timeout"),
        pytest.param(requests.exceptions.ConnectTimeout("lento"), id="connect-timeout"),
    ],
)
def test_get_con_error_de_red_pasa_al_siguiente_host(rsps, fallo):
    rsps.get(url(A, "/version"), body=fallo)
    rsps.get(url(B, "/version"), json={"data": {"version": "9.2.1"}})
    t = _http()
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}
    assert t.host_activo == B


@pytest.mark.parametrize("estado", [595, 596])
def test_get_con_595_o_596_pasa_al_siguiente_host(rsps, estado):
    agregar_error(rsps, "GET", url(A, "/nodes/pve2/storage"), estado, "no route to host")
    rsps.get(url(B, "/nodes/pve2/storage"), json={"data": []})
    t = _http()
    assert t.peticion("GET", "/nodes/pve2/storage") == []
    assert t.host_activo == B


@pytest.mark.parametrize(
    ("estado", "codigo"),
    [
        (401, CodigoError.CREDENCIALES_INVALIDAS),
        (403, CodigoError.PERMISO_INSUFICIENTE),
    ],
)
def test_get_con_401_o_403_nunca_hace_failover(rsps, estado, codigo):
    agregar_error(rsps, "GET", url(A, "/nodes"), estado, "Permission check failed (/, Sys.Audit)")
    rsps.get(url(B, "/nodes"), json={"data": []})
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("GET", "/nodes")
    assert e.value.codigo in (codigo, CodigoError.SESION_EXPIRADA)
    assert [c.request.url for c in rsps.calls] == [url(A, "/nodes")]


# --- POST: solo si el fallo fue antes de enviar ------------------------------------------


@pytest.mark.parametrize(
    "fallo",
    [
        pytest.param(_nueva_conexion(), id="NewConnectionError"),
        pytest.param(requests.exceptions.ConnectTimeout("sin conexión"), id="ConnectTimeout"),
    ],
)
def test_post_con_fallo_previo_al_envio_pasa_al_siguiente_host(rsps, fallo):
    rsps.post(url(A, RUTA_POST), body=fallo)
    rsps.post(url(B, RUTA_POST), json=UPID_OK)
    t = _http()
    assert t.peticion("POST", RUTA_POST, datos={"vmid": 100}) == "UPID:pve1:x"
    assert t.host_activo == B
    assert len(rsps.calls) == 2


@pytest.mark.parametrize(
    "fallo",
    [
        pytest.param(requests.exceptions.ReadTimeout("sin respuesta"), id="ReadTimeout"),
        pytest.param(_conexion_cortada(), id="conexion-cortada-tras-enviar"),
    ],
)
def test_post_con_fallo_posterior_al_envio_no_reintenta_y_reporta_error(rsps, fallo):
    rsps.post(url(A, RUTA_POST), body=fallo)
    rsps.post(url(B, RUTA_POST), json=UPID_OK)
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("POST", RUTA_POST, datos={"vmid": 100})
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert e.value.params["host"] == A
    # Ninguna petición llegó al segundo host: no se duplica la creación.
    assert [c.request.url for c in rsps.calls] == [url(A, RUTA_POST)]


def test_post_con_todos_los_hosts_sin_conexion_reporta_el_motivo_de_cada_uno(rsps):
    rsps.post(url(A, RUTA_POST), body=_nueva_conexion())
    rsps.post(url(B, RUTA_POST), body=requests.exceptions.ConnectTimeout("x"))
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("POST", RUTA_POST, datos={})
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert A in e.value.params["motivos"]
    assert B in e.value.params["motivos"]
