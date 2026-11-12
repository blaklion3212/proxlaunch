"""Reglas V-18, V-19 y V-21 y normalización del host (CA-01.2, CA-07.8, CA-04.3)."""

import pytest

from proxlaunch.nucleo.modelos import PerfilConexion
from proxlaunch.nucleo.validacion import (
    normalizar_host,
    validar_codigo_totp,
    validar_perfil,
    validar_token,
)

# --- V-18 token ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("ana@pve!lab=11111111-2222-3333-4444-555555555555", id="CA-01.1-valido"),
        pytest.param("root@pam!t1=abc", id="V-18-valido-root"),
        pytest.param("a@b!c.d_e-f=x", id="V-18-valido-id-con-puntos-y-guiones"),
        pytest.param("ana@pve!lab=abc=def==", id="V-18-valido-el-secreto-lleva-iguales"),
    ],
)
def test_v18_token_valido(token):
    assert validar_token(token) == []


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("ana@pve!lab", id="CA-01.2-invalido-sin-secreto"),
        pytest.param("ana@pve=abc", id="CA-01.2-invalido-sin-signo-de-exclamacion"),
        pytest.param("", id="V-18-invalido-vacio"),
        pytest.param("ana@pve!lab=", id="V-18-invalido-secreto-vacio"),
        pytest.param("ana@pve!=abc", id="V-18-invalido-id-de-token-vacio"),
        pytest.param("@pve!lab=abc", id="V-18-invalido-usuario-vacio"),
        pytest.param("ana@!lab=abc", id="V-18-invalido-realm-vacio"),
        pytest.param("a@b@c!lab=abc", id="V-18-invalido-dos-arrobas"),
        pytest.param("ana@pve!la b=abc", id="V-18-invalido-espacio-en-id"),
        pytest.param("ana@pve!lab=ab cd", id="V-18-invalido-espacio-en-secreto"),
        pytest.param("ana@pve!l@b=abc", id="V-18-invalido-caracter-en-id"),
        pytest.param(" ana@pve!lab=abc", id="V-18-invalido-espacio-inicial"),
    ],
)
def test_v18_token_invalido(token):
    problemas = validar_token(token)
    assert [p.codigo for p in problemas] == ["V-18"]
    assert problemas[0].campo == "token"


def test_v18_token_con_salto_de_linea_final_es_invalido():
    assert validar_token("ana@pve!lab=abc\n")


def test_v18_el_problema_no_incluye_el_secreto():
    """RNF-06: el problema de validación no debe copiar el texto del token."""
    problemas = validar_token("ana@pve!lab-SECRETO-CENTINELA")
    assert "SECRETO-CENTINELA" not in repr(problemas)


# --- V-19 host y puerto -------------------------------------------------------------


def _perfil(hosts, puerto=8006):
    return PerfilConexion(id="p1", nombre="lab", hosts=list(hosts), puerto=puerto)


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("pve.lab.local", id="V-19-valido-dns"),
        pytest.param("pve1", id="V-19-valido-nombre-simple"),
        pytest.param("10.0.0.5", id="V-19-valido-ipv4"),
        pytest.param("::1", id="V-19-valido-ipv6-loopback"),
        pytest.param("2001:db8::10", id="V-19-valido-ipv6"),
    ],
)
def test_v19_host_valido(host):
    assert validar_perfil(_perfil([host])) == []


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("https://10.0.0.5", id="V-19-invalido-con-esquema"),
        pytest.param("10.0.0.5/api2", id="V-19-invalido-con-ruta"),
        pytest.param("10.0.0.5:8006", id="V-19-invalido-con-puerto"),
        pytest.param("mi servidor", id="V-19-invalido-con-espacio"),
        pytest.param("", id="V-19-invalido-vacio"),
        pytest.param("pve_1", id="V-19-invalido-guion-bajo"),
        pytest.param("-pve", id="V-19-invalido-guion-inicial"),
    ],
)
def test_v19_host_invalido(host):
    problemas = validar_perfil(_perfil([host]))
    assert [(p.codigo, p.campo) for p in problemas] == [("V-19", "hosts[0]")]


def test_v19_se_senala_el_host_incorrecto_dentro_de_la_lista():
    """CA-07.1: con varias IPs, el campo apunta a la posición del host malo."""
    problemas = validar_perfil(_perfil(["10.0.0.5", "no valido", "10.0.0.7"]))
    assert [p.campo for p in problemas] == ["hosts[1]"]


@pytest.mark.parametrize(
    "puerto",
    [
        pytest.param(1, id="V-19-puerto-1"),
        pytest.param(8006, id="V-19-puerto-8006"),
        pytest.param(65535, id="V-19-puerto-65535"),
    ],
)
def test_v19_puerto_valido(puerto):
    assert validar_perfil(_perfil(["pve1"], puerto)) == []


@pytest.mark.parametrize(
    "puerto",
    [
        pytest.param(0, id="V-19-puerto-0"),
        pytest.param(65536, id="V-19-puerto-65536"),
        pytest.param(-1, id="V-19-puerto-negativo"),
        pytest.param("8006", id="V-19-puerto-cadena"),
        pytest.param(80.5, id="V-19-puerto-decimal"),
    ],
)
def test_v19_puerto_invalido(puerto):
    problemas = validar_perfil(_perfil(["pve1"], puerto))
    assert [(p.codigo, p.campo) for p in problemas] == [("V-19", "puerto")]


# --- CA-07.8 normalización ----------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        pytest.param("https://10.0.0.5:8006/", ("10.0.0.5", 8006), id="CA-07.8-url-completa"),
        pytest.param("10.0.0.5", ("10.0.0.5", None), id="CA-07.8-ip-sola"),
        pytest.param("  pve.lab  ", ("pve.lab", None), id="CA-07.8-espacios-alrededor"),
        pytest.param("http://pve.lab/api2/json", ("pve.lab", None), id="CA-07.8-esquema-y-ruta"),
        pytest.param("pve.lab:9000", ("pve.lab", 9000), id="CA-07.8-host-y-puerto"),
        pytest.param("10.0.0.5/", ("10.0.0.5", None), id="CA-07.8-barra-final"),
        pytest.param("https://[::1]:8006/", ("::1", 8006), id="CA-07.8-ipv6-con-corchetes"),
        pytest.param("[2001:db8::1]", ("2001:db8::1", None), id="CA-07.8-ipv6-sin-puerto"),
    ],
)
def test_ca07_8_normalizar_host(entrada, esperado):
    assert normalizar_host(entrada) == esperado


def test_ca07_8_el_host_normalizado_pasa_la_validacion():
    host, puerto = normalizar_host("https://10.0.0.5:8006/")
    assert validar_perfil(_perfil([host], puerto)) == []


def test_ca07_8_host_con_espacios_internos_sigue_siendo_invalido():
    """§1.4: un host con espacios no se 'arregla' en silencio: V-19 lo rechaza."""
    host, _ = normalizar_host("mi servidor")
    assert validar_perfil(_perfil([host]))


# --- V-21 código TOTP ---------------------------------------------------------------


@pytest.mark.parametrize(
    "codigo",
    [pytest.param("123456", id="V-21-valido"), pytest.param("000000", id="V-21-valido-ceros")],
)
def test_v21_codigo_valido(codigo):
    assert validar_codigo_totp(codigo) == []


@pytest.mark.parametrize(
    "codigo",
    [
        pytest.param("12345", id="V-21-invalido-5-digitos"),
        pytest.param("1234567", id="V-21-invalido-7-digitos"),
        pytest.param("12345a", id="V-21-invalido-letra"),
        pytest.param("", id="V-21-invalido-vacio"),
        pytest.param(" 123456", id="V-21-invalido-espacio-inicial"),
        pytest.param("123 456", id="V-21-invalido-espacio-medio"),
        pytest.param("١٢٣٤٥٦", id="V-21-invalido-digitos-no-ascii"),
    ],
)
def test_v21_codigo_invalido(codigo):
    problemas = validar_codigo_totp(codigo)
    assert [p.codigo for p in problemas] == ["V-21"]


def test_v21_codigo_con_salto_de_linea_final_es_invalido():
    assert validar_codigo_totp("123456\n")
