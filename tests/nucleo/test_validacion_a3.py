"""A-3 (V-19): cuatro grupos numéricos separados por puntos se tratan como IPv4 y deben ser
una IPv4 válida; el resto de hosts sigue la regla de nombre DNS, IPv4 o IPv6."""

import pytest

from proxlaunch.nucleo.modelos import PerfilConexion
from proxlaunch.nucleo.validacion import validar_perfil


def _problemas(*hosts):
    perfil = PerfilConexion(id="p", nombre="lab", hosts=list(hosts))
    return validar_perfil(perfil)


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("10.0.0.5", id="A-3-ipv4-valida"),
        pytest.param("pve1.local", id="A-3-nombre-dns"),
        pytest.param("192.168.1.1", id="A-3-ipv4-privada"),
        pytest.param("255.255.255.255", id="A-3-ipv4-maxima"),
        pytest.param("0.0.0.0", id="A-3-ipv4-ceros"),
        pytest.param("1.2.3.4", id="A-3-ipv4-minima"),
        pytest.param("::1", id="V-19-ipv6"),
        pytest.param("pve1", id="V-19-nombre-corto"),
        pytest.param("a.b.c.d", id="A-3-cuatro-etiquetas-no-numericas-son-dns"),
    ],
)
def test_a3_hosts_validos(host):
    assert _problemas(host) == []


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("999.1.1.1", id="A-3-octeto-999"),
        pytest.param("256.0.0.1", id="A-3-octeto-256"),
        pytest.param("1.2.3.256", id="A-3-ultimo-octeto-256"),
        pytest.param("10.0.0.300", id="A-3-ultimo-octeto-300"),
        pytest.param("9999999999999.1.1.1", id="A-3-octeto-enorme"),
    ],
)
def test_a3_cuatro_grupos_numericos_invalidos(host):
    problemas = _problemas(host)
    assert [(p.campo, p.codigo) for p in problemas] == [("hosts[0]", "V-19")]


def test_a3_el_error_apunta_al_host_concreto_de_la_lista():
    problemas = _problemas("10.0.0.5", "999.1.1.1", "pve1.local")
    assert [p.campo for p in problemas] == ["hosts[1]"]
