"""Transporte (ronda F7): sin failover en métodos no GET tras el envío, sin proxy del entorno
(D-18) y bloqueo de destinos sin adaptador de huella."""

import pytest
import requests

from proxlaunch.nucleo.api.transporte import AdaptadorBloqueado, AdaptadorHuella, TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

from .apoyo_api import HUELLA_A, agregar_error, url

A = "10.0.0.1"
B = "10.0.0.2"
RUTA_POST = "/nodes/pve1/qemu"
UPID_OK = {"data": "UPID:pve1:x"}


def _http(**kw):
    return TransporteHttp([A, B], 8006, huellas={A: HUELLA_A, B: HUELLA_A}, **kw)


def _solo_primer_host(rsps):
    return [c.request.url for c in rsps.calls] == [url(A, RUTA_POST)]


@pytest.mark.parametrize("estado", [595, 596])
@pytest.mark.parametrize("metodo", ["POST", "PUT"])
def test_595_o_596_en_metodo_no_get_es_incierto_y_no_prueba_otro_host(rsps, estado, metodo):
    agregar_error(rsps, metodo, url(A, RUTA_POST), estado, "no route to host")
    rsps.add(metodo, url(B, RUTA_POST), json=UPID_OK)
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion(metodo, RUTA_POST, datos={"vmid": 100})
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert e.value.params["incierto"] == "1"
    assert [c.request.url for c in rsps.calls] == [url(A, RUTA_POST)]


def test_ssl_que_no_es_de_huella_en_post_es_incierto_y_no_prueba_otro_host(rsps):
    rsps.post(url(A, RUTA_POST), body=requests.exceptions.SSLError("handshake failure"))
    rsps.post(url(B, RUTA_POST), json=UPID_OK)
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("POST", RUTA_POST, datos={})
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert e.value.params["incierto"] == "1"
    assert _solo_primer_host(rsps)


def test_read_timeout_en_post_es_servidor_no_responde_sin_otro_host(rsps):
    rsps.post(url(A, RUTA_POST), body=requests.exceptions.ReadTimeout("lento"))
    rsps.post(url(B, RUTA_POST), json=UPID_OK)
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("POST", RUTA_POST, datos={})
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert _solo_primer_host(rsps)


def test_connection_error_tras_enviar_en_post_no_hace_failover(rsps):
    rsps.post(url(A, RUTA_POST), body=requests.exceptions.ConnectionError("Connection aborted."))
    rsps.post(url(B, RUTA_POST), json=UPID_OK)
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("POST", RUTA_POST, datos={})
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert _solo_primer_host(rsps)


@pytest.mark.parametrize("estado", [595, 596])
def test_get_con_595_o_596_si_hace_failover(rsps, estado):
    agregar_error(rsps, "GET", url(A, "/nodes"), estado, "no route to host")
    rsps.get(url(B, "/nodes"), json={"data": ["ok"]})
    t = _http()
    assert t.peticion("GET", "/nodes") == ["ok"]
    assert t.host_activo == B


def test_la_sesion_no_confia_en_el_entorno_ni_siquiera_si_se_inyecta_una_que_si():
    sesion = requests.Session()
    assert sesion.trust_env is True
    TransporteHttp([A], 8006, huellas={A: HUELLA_A}, sesion=sesion)
    assert sesion.trust_env is False


def test_con_proxy_en_el_entorno_la_sesion_no_lo_usa(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalido:3128")
    monkeypatch.setenv("https_proxy", "http://proxy.invalido:3128")
    sesion = requests.Session()
    TransporteHttp([A], 8006, huellas={A: HUELLA_A}, sesion=sesion)
    ajustes = sesion.merge_environment_settings(url(A, "/version"), {}, None, None, None)
    assert not ajustes["proxies"]


def test_destino_sin_adaptador_de_huella_se_bloquea_y_no_sale(rsps):
    sesion = requests.Session()
    TransporteHttp([A], 8006, huellas={A: HUELLA_A}, sesion=sesion)
    ajeno = "https://10.9.9.9:8006/api2/json/version"
    assert isinstance(sesion.get_adapter(ajeno), AdaptadorBloqueado)
    assert isinstance(sesion.get_adapter(url(A, "/version")), AdaptadorHuella)
    with pytest.raises(requests.exceptions.InvalidURL):
        sesion.get(ajeno)
    assert len(rsps.calls) == 0


def test_host_sin_huella_con_ignorar_ssl_si_tiene_adaptador_y_sale(rsps):
    rsps.get(url(A, "/version"), json={"data": {"version": "9.2.1"}})
    t = TransporteHttp([A], 8006, huellas={}, ignorar_ssl=True)
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}
    assert len(rsps.calls) == 1


def test_host_sin_huella_sin_ignorar_ssl_no_sale_ninguna_peticion(rsps):
    rsps.get(url(A, "/version"), json={"data": {}})
    t = TransporteHttp([A], 8006, huellas={})
    with pytest.raises(ErrorProxLaunch) as e:
        t.peticion("GET", "/version")
    assert e.value.codigo == CodigoError.HUELLA_NO_CONFIADA
    assert len(rsps.calls) == 0
