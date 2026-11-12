"""Transporte HTTP: autenticación en cabeceras, failover, huella y codificación (RF-01, RF-02,
RF-05, RF-06, RF-07, RNF-03, RNF-07, RNF-16). HTTP simulado con ``responses``."""

import json
import ssl
from urllib.parse import parse_qs

import pytest
import requests

from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket, AutenticadorToken
from proxlaunch.nucleo.api.transporte import (
    TIMEOUT_CONEXION,
    TIMEOUT_LECTURA,
    AdaptadorHuella,
    TransporteHttp,
    crear_transporte_http,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken, Ticket

from .apoyo_api import (
    HUELLA_A,
    TOKEN_ID,
    TOKEN_SECRETO,
    agregar_error,
    perfil_basico,
    url,
)

A = "10.0.0.1"
B = "10.0.0.2"
OK_VERSION = {"data": {"version": "9.2.1"}}


def _http(hosts=(A,), auth=None, **kw):
    """Transporte con huella confiada en todos los hosts (salvo que se pase otra cosa)."""
    kw.setdefault("huellas", {h: HUELLA_A for h in hosts})
    t = TransporteHttp(list(hosts), 8006, **kw)
    t.usar_autenticador(auth)
    return t


def _token():
    return AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO))


def _ticket(ticket="PVE:root@pam:AAAA::sig", csrf="AAAA:csrf", emitido=0.0):
    return AutenticadorTicket(Ticket(ticket, csrf, "root@pam", emitido), reloj=_Reloj())


class _Reloj:
    def ahora(self):
        return 0.0

    def dormir(self, segundos):
        return None


# --- RF-01: token ---------------------------------------------------------------------


def test_ca_01_1_cabecera_authorization_exacta(rsps):
    rsps.get(url(A, "/version"), json=OK_VERSION)
    t = _http(auth=_token())
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}
    cab = rsps.calls[0].request.headers
    assert cab["Authorization"] == f"PVEAPIToken={TOKEN_ID}={TOKEN_SECRETO}"
    assert "Cookie" not in cab
    assert "CSRFPreventionToken" not in cab


def test_ca_01_1_token_tambien_en_post_sin_csrf(rsps):
    rsps.post(url(A, "/nodes/pve1/qemu"), json={"data": "UPID:x:y"})
    _http(auth=_token()).peticion("POST", "/nodes/pve1/qemu", datos={"vmid": 100})
    cab = rsps.calls[0].request.headers
    assert cab["Authorization"].startswith("PVEAPIToken=")
    assert "CSRFPreventionToken" not in cab


def test_ca_01_3_401_con_token_es_credenciales_invalidas(rsps):
    agregar_error(rsps, "GET", url(A, "/version"), 401, "No ticket")
    with pytest.raises(ErrorProxLaunch) as e:
        _http(auth=_token()).peticion("GET", "/version")
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS


def test_ca_02_2_401_en_login_es_credenciales_invalidas(rsps):
    agregar_error(rsps, "POST", url(A, "/access/ticket"), 401, "authentication failure")
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("POST", "/access/ticket", datos={"username": "root@pam", "password": "x"})
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS


def test_ca_03_3_401_con_ticket_es_sesion_expirada(rsps):
    agregar_error(rsps, "GET", url(A, "/version"), 401, "No ticket")
    with pytest.raises(ErrorProxLaunch) as e:
        _http(auth=_ticket()).peticion("GET", "/version")
    assert e.value.codigo == CodigoError.SESION_EXPIRADA


# --- RF-02: ticket (cookie y CSRF) -----------------------------------------------------


def test_ca_02_3_get_lleva_cookie_y_no_csrf(rsps):
    rsps.get(url(A, "/version"), json=OK_VERSION)
    _http(auth=_ticket()).peticion("GET", "/version")
    cab = rsps.calls[0].request.headers
    assert "PVEAuthCookie=" in cab["Cookie"]
    assert "CSRFPreventionToken" not in cab
    assert "Authorization" not in cab


@pytest.mark.parametrize("metodo", ["POST", "PUT"])
def test_ca_02_3_csrf_solo_en_metodos_que_no_son_get(rsps, metodo):
    rsps.add(metodo, url(A, "/nodes/pve1/qemu"), json={"data": "x"})
    _http(auth=_ticket(csrf="AAAA:csrf-1")).peticion(metodo, "/nodes/pve1/qemu", datos={"a": 1})
    cab = rsps.calls[0].request.headers
    assert cab["CSRFPreventionToken"] == "AAAA:csrf-1"
    assert "PVEAuthCookie=" in cab["Cookie"]


def test_ca_02_3_las_cookies_no_persisten_en_la_sesion(rsps):
    rsps.get(url(A, "/version"), json=OK_VERSION, headers={"Set-Cookie": "otra=1; Path=/"})
    t = _http()
    t.peticion("GET", "/version")
    t.peticion("GET", "/version")
    assert "Cookie" not in rsps.calls[1].request.headers


# --- RNF-16 y CT-9: formulario codificado -----------------------------------------------


def test_ca_17_2_net0_se_codifica_en_el_formulario(rsps):
    rsps.post(url(A, "/nodes/pve1/qemu"), json={"data": "UPID:x"})
    _http(auth=_token()).peticion(
        "POST", "/nodes/pve1/qemu", datos={"vmid": 100, "net0": "virtio,bridge=vmbr0"}
    )
    peticion = rsps.calls[0].request
    assert peticion.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert "net0=virtio%2Cbridge%3Dvmbr0" in peticion.body
    assert "vmid=100" in peticion.body


def test_rnf_16_valores_peligrosos_no_alteran_otros_parametros(rsps):
    rsps.post(url(A, "/nodes/pve1/qemu"), json={"data": "UPID:x"})
    nombre = "a,b=c&vmid=999 x\nbios=ovmf"
    _http(auth=_token()).peticion("POST", "/nodes/pve1/qemu", datos={"vmid": 100, "name": nombre})
    campos = parse_qs(rsps.calls[0].request.body, keep_blank_values=True)
    assert campos == {"vmid": ["100"], "name": [nombre]}


def test_los_params_de_consulta_se_envian_en_la_url(rsps):
    rsps.get(url(A, "/cluster/nextid"), json={"data": "101"})
    _http().peticion("GET", "/cluster/nextid", params={"vmid": 100})
    assert rsps.calls[0].request.url.endswith("/api2/json/cluster/nextid?vmid=100")


def test_host_ipv6_va_entre_corchetes(rsps):
    rsps.get("https://[fe80::1]:8006/api2/json/version", json=OK_VERSION)
    t = _http(hosts=("[fe80::1]",), huellas={"[fe80::1]": HUELLA_A})
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}


# --- RNF-03: tiempos de espera ---------------------------------------------------------


def test_rnf_03_constantes_de_timeout():
    assert TIMEOUT_CONEXION == 10
    assert TIMEOUT_LECTURA == 30


def test_rnf_03_la_peticion_usa_los_timeouts(rsps):
    rsps.get(url(A, "/version"), json=OK_VERSION)
    _http().peticion("GET", "/version")
    assert rsps.calls[0].request.req_kwargs["timeout"] == (10, 30)


# --- RF-07: failover ------------------------------------------------------------------


@pytest.mark.parametrize(
    "fallo",
    [
        pytest.param(requests.exceptions.ConnectTimeout("t"), id="CA-07.2-timeout"),
        pytest.param(requests.exceptions.ConnectionError("rechazada"), id="CA-07.2-rechazada"),
    ],
)
def test_ca_07_2_cae_a_y_responde_b(rsps, fallo):
    rsps.get(url(A, "/version"), body=fallo)
    rsps.get(url(B, "/version"), json=OK_VERSION)
    t = _http(hosts=(A, B))
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}
    assert t.host_activo == B


def test_ca_07_2_nodo_595_en_a_pasa_a_b(rsps):
    agregar_error(rsps, "GET", url(A, "/version"), 595, "no route to host")
    rsps.get(url(B, "/version"), json=OK_VERSION)
    t = _http(hosts=(A, B))
    t.peticion("GET", "/version")
    assert t.host_activo == B


def test_ca_07_5_sesion_activa_reintenta_con_b_si_a_deja_de_responder(rsps):
    rsps.get(url(A, "/version"), json=OK_VERSION)
    rsps.get(url(B, "/version"), json=OK_VERSION)
    t = _http(hosts=(A, B), auth=_ticket())
    t.peticion("GET", "/version")
    assert t.host_activo == A
    rsps.replace(rsps.GET, url(A, "/version"), body=requests.exceptions.ConnectTimeout())
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}
    assert t.host_activo == B
    # El mismo ticket vale en todo el clúster.
    assert rsps.calls[-1].request.headers["Cookie"] == rsps.calls[0].request.headers["Cookie"]


def test_ca_07_5_tras_el_failover_las_siguientes_van_directo_a_b(rsps):
    rsps.get(url(A, "/version"), body=requests.exceptions.ConnectTimeout())
    rsps.get(url(B, "/version"), json=OK_VERSION)
    t = _http(hosts=(A, B))
    t.peticion("GET", "/version")
    t.peticion("GET", "/version")
    llamadas_a = [c for c in rsps.calls if A in c.request.url]
    assert len(llamadas_a) == 1


@pytest.mark.parametrize("estado", [401, 403])
def test_ca_07_3_error_de_credenciales_o_permisos_no_prueba_b(rsps, estado):
    agregar_error(rsps, "GET", url(A, "/version"), estado, "denegado")
    rsps.get(url(B, "/version"), json=OK_VERSION)
    with pytest.raises(ErrorProxLaunch):
        _http(hosts=(A, B), auth=_token()).peticion("GET", "/version")
    assert all(B not in c.request.url for c in rsps.calls)


def test_ca_07_4_todas_caen_informa_el_motivo_por_host(rsps):
    rsps.get(url(A, "/version"), body=requests.exceptions.ConnectTimeout())
    rsps.get(url(B, "/version"), body=requests.exceptions.ConnectionError())
    with pytest.raises(ErrorProxLaunch) as e:
        _http(hosts=(A, B)).peticion("GET", "/version")
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert f"{A}=timeout" in e.value.params["motivos"]
    assert f"{B}=conexion" in e.value.params["motivos"]
    assert e.value.params["host"] == A
    assert e.value.params["hosts"] == f"{A},{B}"


def test_ca_07_6_un_solo_host_caido_es_servidor_no_responde(rsps):
    rsps.get(url(A, "/version"), body=requests.exceptions.ConnectTimeout())
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("GET", "/version")
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert e.value.params["host"] == A


def test_ca_11_8_todos_los_hosts_595_es_nodo_no_disponible(rsps):
    agregar_error(rsps, "GET", url(A, "/nodes/pve2/storage"), 595, "no route to host")
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("GET", "/nodes/pve2/storage")
    assert e.value.codigo == CodigoError.NODO_NO_DISPONIBLE
    assert e.value.params["nodo"] == "pve2"


def test_read_timeout_en_get_hace_failover(rsps):
    rsps.get(url(A, "/version"), body=requests.exceptions.ReadTimeout())
    rsps.get(url(B, "/version"), json=OK_VERSION)
    t = _http(hosts=(A, B))
    t.peticion("GET", "/version")
    assert t.host_activo == B


def test_read_timeout_en_post_no_hace_failover(rsps):
    rsps.post(url(A, "/nodes/pve1/qemu"), body=requests.exceptions.ReadTimeout())
    rsps.post(url(B, "/nodes/pve1/qemu"), json={"data": "UPID:x"})
    with pytest.raises(ErrorProxLaunch) as e:
        _http(hosts=(A, B), auth=_token()).peticion("POST", "/nodes/pve1/qemu", datos={"vmid": 1})
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert all(B not in c.request.url for c in rsps.calls)
    assert len(rsps.calls) == 1


def test_connect_timeout_en_post_si_hace_failover(rsps):
    # El POST nunca llegó al servidor: reintentar en otro host no duplica nada.
    rsps.post(url(A, "/nodes/pve1/qemu"), body=requests.exceptions.ConnectTimeout())
    rsps.post(url(B, "/nodes/pve1/qemu"), json={"data": "UPID:x"})
    t = _http(hosts=(A, B), auth=_token())
    assert t.peticion("POST", "/nodes/pve1/qemu", datos={"vmid": 1}) == "UPID:x"


def test_ninguna_peticion_usa_delete(rsps):
    rsps.get(url(A, "/version"), json=OK_VERSION)
    rsps.post(url(A, "/nodes/pve1/qemu"), json={"data": "UPID:x"})
    t = _http(auth=_token())
    t.peticion("GET", "/version")
    t.peticion("POST", "/nodes/pve1/qemu", datos={"vmid": 1})
    assert all(c.request.method != "DELETE" for c in rsps.calls)


# --- RF-05 / RNF-07: huella -----------------------------------------------------------


def test_ca_05_1_host_sin_huella_no_envia_ninguna_peticion(rsps):
    rsps.post(url(A, "/access/ticket"), json={"data": {}})
    t = TransporteHttp([A], 8006, huellas={})
    with pytest.raises(ErrorProxLaunch) as e:
        t.peticion("POST", "/access/ticket", datos={"username": "root@pam", "password": "x"})
    assert e.value.codigo == CodigoError.HUELLA_NO_CONFIADA
    assert len(rsps.calls) == 0


def test_rnf_07_solo_se_contactan_los_hosts_con_huella(rsps):
    rsps.get(url(B, "/version"), json=OK_VERSION)
    t = TransporteHttp([A, B], 8006, huellas={B: HUELLA_A})
    t.peticion("GET", "/version")
    assert [c.request.url for c in rsps.calls] == [url(B, "/version")]


def test_ca_05_4_huella_distinta_bloquea_sin_failover(rsps):
    rsps.post(
        url(A, "/access/ticket"),
        body=requests.exceptions.SSLError("Fingerprints did not match. Expected abab, got cdcd"),
    )
    rsps.post(url(B, "/access/ticket"), json={"data": {}})
    t = _http(hosts=(A, B))
    with pytest.raises(ErrorProxLaunch) as e:
        t.peticion("POST", "/access/ticket", datos={"username": "root@pam", "password": "x"})
    assert e.value.codigo == CodigoError.HUELLA_CAMBIADA
    assert e.value.params["host"] == A
    assert all(B not in c.request.url for c in rsps.calls)


def test_otro_error_tls_si_cae_al_siguiente_host(rsps):
    rsps.get(url(A, "/version"), body=requests.exceptions.SSLError("handshake failure"))
    rsps.get(url(B, "/version"), json=OK_VERSION)
    t = _http(hosts=(A, B))
    t.peticion("GET", "/version")
    assert t.host_activo == B


def test_adaptador_entrega_huella_y_cert_none_al_pool():
    adaptador = AdaptadorHuella(HUELLA_A)
    pool = adaptador.poolmanager.connection_from_host("10.0.0.1", 8006, scheme="https")
    assert pool.assert_fingerprint == HUELLA_A
    assert pool.cert_reqs in ("CERT_NONE", ssl.CERT_NONE)


def test_adaptador_sin_huella_no_fija_nada():
    adaptador = AdaptadorHuella(None)
    pool = adaptador.poolmanager.connection_from_host("10.0.0.1", 8006, scheme="https")
    assert not pool.assert_fingerprint


def test_adaptador_entrega_huella_tambien_al_pool_de_proxy():
    adaptador = AdaptadorHuella(HUELLA_A)
    proxy = adaptador.proxy_manager_for("http://proxy.local:3128")
    assert proxy.connection_pool_kw["assert_fingerprint"] == HUELLA_A
    assert proxy.connection_pool_kw["cert_reqs"] in ("CERT_NONE", ssl.CERT_NONE)


def test_transporte_monta_el_adaptador_con_huella_por_host():
    t = TransporteHttp([A, B], 8006, huellas={A: HUELLA_A})
    sesion = t._sesion  # única forma de comprobar el montaje sin red
    assert isinstance(sesion.get_adapter(f"https://{A}:8006/"), AdaptadorHuella)
    assert not isinstance(sesion.get_adapter(f"https://{B}:8006/"), AdaptadorHuella)


# --- RF-06: ignorar SSL -----------------------------------------------------------------


def test_ca_06_2_ignorar_ssl_no_exige_huella_y_acepta_cualquier_certificado(rsps):
    rsps.get(url(A, "/version"), json=OK_VERSION)
    t = TransporteHttp([A], 8006, huellas={}, ignorar_ssl=True)
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}
    assert rsps.calls[0].request.req_kwargs["verify"] is False


def test_ca_06_2_ignorar_ssl_monta_adaptador_sin_huella_con_cert_none():
    t = TransporteHttp([A], 8006, huellas={A: HUELLA_A}, ignorar_ssl=True)
    adaptador = t._sesion.get_adapter(f"https://{A}:8006/")
    pool = adaptador.poolmanager.connection_from_host(A, 8006, scheme="https")
    assert not pool.assert_fingerprint  # con ignorar_ssl la huella guardada no se usa


def test_con_huella_la_peticion_tambien_va_con_verify_false(rsps):
    # La verificación real la hace la huella; verify=True anularía cert_reqs del adaptador.
    rsps.get(url(A, "/version"), json=OK_VERSION)
    _http().peticion("GET", "/version")
    assert rsps.calls[0].request.req_kwargs["verify"] is False


# --- Respuestas ------------------------------------------------------------------------


def test_respuesta_200_que_no_es_json_es_desconocido(rsps):
    rsps.get(url(A, "/version"), body="<html>", content_type="text/html")
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("GET", "/version")
    assert e.value.codigo == CodigoError.DESCONOCIDO


def test_403_extrae_privilegio_y_ruta(rsps):
    agregar_error(
        rsps,
        "POST",
        url(A, "/nodes/pve1/qemu"),
        403,
        "Permission check failed (/vms/100, VM.Allocate)",
    )
    with pytest.raises(ErrorProxLaunch) as e:
        _http(auth=_token()).peticion("POST", "/nodes/pve1/qemu", datos={"vmid": 100})
    assert e.value.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert e.value.params == {"privilegio": "VM.Allocate", "ruta": "/vms/100"}


def test_error_http_conserva_el_detalle_tecnico_original(rsps):
    agregar_error(rsps, "GET", url(A, "/version"), 500, "boom interno", {"data": None})
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("GET", "/version")
    assert e.value.codigo == CodigoError.DESCONOCIDO
    assert "boom interno" in e.value.detalle_tecnico


def test_cuerpo_sin_campo_data_devuelve_none(rsps):
    rsps.get(url(A, "/version"), body=json.dumps({}), content_type="application/json")
    assert _http().peticion("GET", "/version") is None


def test_cerrar_cierra_la_sesion():
    t = _http()
    t.cerrar()  # no debe lanzar


def test_fabrica_por_defecto_usa_hosts_puerto_y_huellas(rsps):
    rsps.get(url(B, "/version"), json=OK_VERSION)
    perfil = perfil_basico(hosts=[A, B], puerto=8006)
    t = crear_transporte_http(perfil, {B: HUELLA_A})
    t.peticion("GET", "/version")
    assert t.host_activo == B


# --- Composición real con requests y urllib3 (sin red) ---------------------------------


def test_la_huella_sobrevive_a_verify_false_de_requests():
    """El pool que ``requests`` elige para una petición con ``verify=False`` conserva la
    huella fija y CERT_NONE (si no, la huella no protegería nada)."""
    adaptador = AdaptadorHuella(HUELLA_A)
    peticion = requests.Request("GET", f"https://{A}:8006/api2/json/version").prepare()
    pool = adaptador.get_connection_with_tls_context(peticion, verify=False)
    assert pool.assert_fingerprint == HUELLA_A
    assert pool.cert_reqs in ("CERT_NONE", ssl.CERT_NONE)


def test_el_error_de_huella_de_urllib3_se_reconoce_como_huella_cambiada(rsps):
    import urllib3

    pool = AdaptadorHuella(HUELLA_A).poolmanager.connection_from_host(A, 8006, scheme="https")
    real = requests.exceptions.SSLError(
        urllib3.exceptions.MaxRetryError(
            pool,
            "/api2/json/version",
            reason=urllib3.exceptions.SSLError(
                'Fingerprints did not match. Expected "ab", got "cd"'
            ),
        )
    )
    rsps.get(url(A, "/version"), body=real)
    with pytest.raises(ErrorProxLaunch) as e:
        _http().peticion("GET", "/version")
    assert e.value.codigo == CodigoError.HUELLA_CAMBIADA


def test_host_ipv6_sin_corchetes_tambien_funciona(rsps):
    rsps.get("https://[fe80::1]:8006/api2/json/version", json=OK_VERSION)
    t = _http(hosts=("fe80::1",), huellas={"fe80::1": HUELLA_A})
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_rnf_08_sin_simulacion_la_red_real_esta_bloqueada():
    from pytest_socket import SocketBlockedError

    with pytest.raises(SocketBlockedError):
        _http().peticion("GET", "/version")


def test_ca_19_6_post_con_conexion_abortada_tras_enviar_no_hace_failover(rsps):
    import http.client

    import urllib3

    abortada = requests.exceptions.ConnectionError(
        urllib3.exceptions.ProtocolError(
            "Connection aborted.",
            http.client.RemoteDisconnected("Remote end closed connection without response"),
        )
    )
    rsps.post(url(A, "/nodes/pve1/qemu"), body=abortada)
    rsps.post(url(B, "/nodes/pve1/qemu"), json={"data": "UPID:x"})
    with pytest.raises(ErrorProxLaunch):
        _http(hosts=(A, B), auth=_token()).peticion("POST", "/nodes/pve1/qemu", datos={"vmid": 1})
    assert all(B not in c.request.url for c in rsps.calls)
