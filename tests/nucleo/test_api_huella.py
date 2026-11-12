"""Lectura de la huella del certificado sin enviar datos (RF-05, CA-05.1, RNF-07).
El socket y la capa TLS se sustituyen por dobles: no se abre ninguna conexión."""

import ssl

import pytest

from proxlaunch.nucleo.api import huella as modulo
from proxlaunch.nucleo.api.huella import formatear_huella, obtener_huella
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

# SHA-256 de b"abc" (vector de prueba estándar).
HUELLA_ABC = (
    "BA:78:16:BF:8F:01:CF:EA:41:41:40:DE:5D:AE:22:23:"
    "B0:03:61:A3:96:17:7A:9C:B4:10:FF:61:F2:00:15:AD"
)


class _Socket:
    def __init__(self):
        self.enviado = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send(self, datos, *a):
        self.enviado.append(datos)

    sendall = send


class _Tls(_Socket):
    def __init__(self, der):
        super().__init__()
        self._der = der

    def getpeercert(self, binary_form=False):
        assert binary_form is True
        return self._der


class _Contexto:
    ultimo = None

    def __init__(self, protocolo=None):
        self.protocolo = protocolo
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED
        self.sni = None
        self.tls = _Tls(b"abc")
        _Contexto.ultimo = self

    def wrap_socket(self, sock, server_hostname=None):
        self.sni = server_hostname
        return self.tls


@pytest.fixture
def red_falsa(monkeypatch):
    registro = {"destino": None, "timeout": None, "socket": _Socket()}

    def _conectar(destino, timeout=None):
        registro["destino"], registro["timeout"] = destino, timeout
        return registro["socket"]

    monkeypatch.setattr(modulo.socket, "create_connection", _conectar)
    monkeypatch.setattr(modulo.ssl, "SSLContext", _Contexto)
    return registro


def test_formato_de_la_huella_es_sha256_con_dos_puntos():
    assert formatear_huella(b"abc") == HUELLA_ABC


def test_ca_05_1_obtiene_la_huella_sin_enviar_ningun_dato(red_falsa):
    assert obtener_huella("10.0.0.1", 8006, 10) == HUELLA_ABC
    assert red_falsa["socket"].enviado == []
    assert _Contexto.ultimo.tls.enviado == []


def test_la_lectura_no_valida_la_cadena_para_poder_mostrar_la_huella(red_falsa):
    obtener_huella("10.0.0.1", 8006, 10)
    assert _Contexto.ultimo.check_hostname is False
    assert _Contexto.ultimo.verify_mode == ssl.CERT_NONE


def test_se_conecta_al_host_y_puerto_con_el_timeout_indicado(red_falsa):
    obtener_huella("pve1.local", 8007, 7)
    assert red_falsa["destino"] == ("pve1.local", 8007)
    assert red_falsa["timeout"] == 7
    assert _Contexto.ultimo.sni == "pve1.local"


def test_ipv6_se_conecta_sin_corchetes(red_falsa):
    obtener_huella("[fe80::1]", 8006, 10)
    assert red_falsa["destino"] == ("fe80::1", 8006)


@pytest.mark.parametrize(
    "fallo",
    [
        pytest.param(ConnectionRefusedError("rechazada"), id="rechazada"),
        pytest.param(TimeoutError("timeout"), id="timeout"),
        pytest.param(ssl.SSLError("handshake"), id="tls"),
    ],
)
def test_ca_01_5_servidor_inalcanzable_es_servidor_no_responde(monkeypatch, fallo):
    def _conectar(destino, timeout=None):
        raise fallo

    monkeypatch.setattr(modulo.socket, "create_connection", _conectar)
    with pytest.raises(ErrorProxLaunch) as e:
        obtener_huella("10.0.0.1", 8006, 10)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert e.value.params == {"host": "10.0.0.1", "puerto": "8006"}


def test_sin_certificado_es_servidor_no_responde(red_falsa, monkeypatch):
    class _SinCert(_Contexto):
        def __init__(self, protocolo=None):
            super().__init__(protocolo)
            self.tls = _Tls(None)

    monkeypatch.setattr(modulo.ssl, "SSLContext", _SinCert)
    with pytest.raises(ErrorProxLaunch) as e:
        obtener_huella("10.0.0.1", 8006, 10)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_rnf_08_la_suite_bloquea_los_sockets_reales():
    import socket

    with pytest.raises(RuntimeError, match="[Ss]ocket"):
        socket.create_connection(("192.0.2.1", 8006), timeout=0.01)
