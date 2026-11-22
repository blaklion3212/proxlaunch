"""Fase B (0.7.0): red de cloud-init y IP en serie (RF-B1.7, RF-B1.8, RF-B1.9).

Cubre CA-B1.7.1, CA-B1.7.2, CA-B1.7.4, CA-B1.8.1 a CA-B1.8.5, CA-B1.9.1 a CA-B1.9.7 y CA-B1.9.9,
CL-B6, CL-B7, CL-B8 y las reglas V-B26 a V-B33 y V-B38 en sus funciones puras (``red`` y
``serie``). La emisión de esas reglas como ``Problema`` de una MV está en
``test_fase_b_validaciones.py``; las tablas de la interfaz (CA-B1.7.3, CA-B1.7.6, CA-B1.9.8),
en ``tests/interfaz``.

Decisiones de la arquitectura §10 que se ejercitan aquí: ``normalizar_dns`` no admite ``;``,
``TarjetaCloudInit.serie_inicial`` (calculado, fuera de la igualdad), V-B30 una vez por serie y
V-B38 solo si todas las MVs comparten la IP.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import random

import pytest

from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit, ModoTarjeta, TarjetaCloudInit
from proxlaunch.nucleo.cloudinit.red import (
    PREFIJO_MAX,
    PREFIJO_MIN,
    MotivoRed,
    dominio_valido,
    ip_desplazada,
    motivo_cidr,
    motivo_puerta,
    normalizar_dns,
    valor_ipconfig,
)
from proxlaunch.nucleo.cloudinit.serie import expandir_serie, problemas_serie_lote
from proxlaunch.nucleo.lote.modelos import ElementoPlan, Severidad
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM

FIJA, DHCP, SIN = ModoTarjeta.FIJA, ModoTarjeta.DHCP, ModoTarjeta.SIN_CONFIGURAR
SEMILLA = 20261122


def tarjeta(indice=0, modo=FIJA, ip=None, serie=False, puerta=None) -> TarjetaCloudInit:
    return TarjetaCloudInit(indice=indice, modo=modo, ip=ip, serie=serie, puerta=puerta)


def ci(*tarjetas: TarjetaCloudInit) -> ConfigCloudInit:
    return ConfigCloudInit(tarjetas=tuple(tarjetas))


def plan(config: ConfigCloudInit | None, n: int, *, expandir: bool = True) -> list[ElementoPlan]:
    """``n`` elementos de plan «web-01».. con la configuración (expandida como hace el plan)."""
    elementos = []
    for i in range(n):
        cfg_ci = None if config is None else (expandir_serie(config, i) if expandir else config)
        nombre = f"web-{i + 1:02d}"
        cfg = ConfiguracionVM(vmid=100 + i, nombre=nombre, nodo="pve1", cloudinit=cfg_ci)
        elementos.append(ElementoPlan(i, nombre, 100 + i, "pve1", cfg))
    return elementos


def reglas(problemas) -> list[str]:
    return [p.regla for p in problemas]


# --- CA-B1.7.1 / CA-B1.7.2: valor de ``ipconfigN`` ------------------------------------------------


def test_ca_b1_7_1_dhcp_y_fija_con_puerta_dan_el_valor_de_proxmox():
    assert valor_ipconfig(tarjeta(0, DHCP)) == "ip=dhcp"
    t1 = tarjeta(1, FIJA, "192.168.10.5/24", puerta="192.168.10.1")
    assert valor_ipconfig(t1) == "ip=192.168.10.5/24,gw=192.168.10.1"


def test_ca_b1_7_1_fija_sin_puerta_no_lleva_gw():
    assert valor_ipconfig(tarjeta(0, FIJA, "10.0.0.5/24")) == "ip=10.0.0.5/24"


def test_ca_b1_7_2_sin_configurar_no_da_valor_y_fija_sin_ip_tampoco():
    assert valor_ipconfig(tarjeta(0, SIN)) is None
    assert valor_ipconfig(tarjeta(0, FIJA, None)) is None
    assert valor_ipconfig(tarjeta(0, FIJA, "")) is None


def test_ca_b1_8_3_con_dhcp_la_puerta_no_se_envia_nunca():
    assert valor_ipconfig(tarjeta(0, DHCP, puerta="10.0.0.1")) == "ip=dhcp"
    assert valor_ipconfig(tarjeta(0, SIN, puerta="10.0.0.1")) is None


# --- CA-B1.7.4 / V-B26 / V-B27: la IP con prefijo ------------------------------------------------


@pytest.mark.parametrize(
    "cidr", ["10.0.0.5/24", "192.168.1.1/25", "172.16.0.10/16", "10.1.2.3/8", "10.0.0.1/30"]
)
def test_ca_b1_7_4_ips_validas(cidr):
    assert motivo_cidr(cidr) is None


@pytest.mark.parametrize(
    ("cidr", "motivo"),
    [
        ("10.0.0.5", MotivoRed.SIN_PREFIJO),
        ("10.0.0.5/", MotivoRed.PREFIJO),
        ("10.0.0.5/7", MotivoRed.PREFIJO),
        ("10.0.0.5/31", MotivoRed.PREFIJO),
        ("10.0.0.5/32", MotivoRed.PREFIJO),
        ("10.0.0.5/0", MotivoRed.PREFIJO),
        ("10.0.0.5/024", MotivoRed.PREFIJO),
        ("10.0.0.5/ 24", MotivoRed.PREFIJO),
        ("10.0.0.5/-1", MotivoRed.PREFIJO),
        ("10.0.0.5/24 ", MotivoRed.PREFIJO),
        ("10.0.0.5/abc", MotivoRed.PREFIJO),
        ("10.0.0.256/24", MotivoRed.OCTETO),
        ("10.0.0/24", MotivoRed.OCTETO),
        ("10.0.0.5.6/24", MotivoRed.OCTETO),
        ("a.b.c.d/24", MotivoRed.OCTETO),
        ("٣.٣.٣.٣/24", MotivoRed.OCTETO),  # dígitos no ASCII
        ("010.0.0.1/24", MotivoRed.CEROS),
        ("10.00.0.1/24", MotivoRed.CEROS),
        ("10.0.0.05/24", MotivoRed.CEROS),
        ("0.0.0.0/24", MotivoRed.RESERVADA),
        ("0.1.2.3/24", MotivoRed.RESERVADA),
        ("127.0.0.1/8", MotivoRed.RESERVADA),
        ("224.0.0.1/24", MotivoRed.RESERVADA),
        ("239.255.255.250/24", MotivoRed.RESERVADA),
        ("169.254.1.1/16", MotivoRed.RESERVADA),
        ("255.255.255.255/24", MotivoRed.RESERVADA),
        ("", MotivoRed.NO_IP),
    ],
)
def test_ca_b1_7_4_ips_invalidas_con_su_motivo(cidr, motivo):
    assert motivo_cidr(cidr) == motivo


def test_ca_b1_7_4_los_limites_del_prefijo_son_8_y_30():
    assert (PREFIJO_MIN, PREFIJO_MAX) == (8, 30)
    assert motivo_cidr("10.0.0.5/8") is None
    assert motivo_cidr("10.0.0.5/30") is None
    assert motivo_cidr("10.0.0.5/7") == MotivoRed.PREFIJO
    assert motivo_cidr("10.0.0.5/31") == MotivoRed.PREFIJO


def test_ca_b1_7_4_un_valor_que_no_es_texto_no_lanza():
    for valor in (None, 5, b"10.0.0.5/24", ["10.0.0.5/24"]):
        assert motivo_cidr(valor) == MotivoRed.NO_IP  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "cidr",
    [
        "10.0.0.0/24",
        "10.0.0.255/24",
        "192.168.1.0/25",
        "192.168.1.127/25",
        "10.0.0.3/30",
        "10.0.0.0/8",
    ],
)
def test_v_b27_la_direccion_de_red_o_de_difusion_no_es_una_ip_de_maquina(cidr):
    assert motivo_cidr(cidr) == MotivoRed.RED_O_DIFUSION


# --- CA-B1.8.2 / V-B28: puerta de enlace --------------------------------------------------------


@pytest.mark.parametrize("puerta", ["10.0.0.1", "10.0.0.254", "10.0.0.100"])
def test_ca_b1_8_2_puertas_validas(puerta):
    assert motivo_puerta("10.0.0.5/24", puerta) is None


@pytest.mark.parametrize(
    ("puerta", "motivo"),
    [
        ("10.0.1.1", MotivoRed.FUERA_DE_RED),
        ("192.168.0.1", MotivoRed.FUERA_DE_RED),
        ("10.0.0.5", MotivoRed.IGUAL_A_IP),
        ("10.0.0.0", MotivoRed.RED_O_DIFUSION),
        ("10.0.0.255", MotivoRed.RED_O_DIFUSION),
        ("hola", MotivoRed.OCTETO),
        ("10.0.0", MotivoRed.OCTETO),
        ("010.0.0.1", MotivoRed.CEROS),
        ("", MotivoRed.OCTETO),
        ("fe80::1", MotivoRed.OCTETO),  # solo IPv4
    ],
)
def test_ca_b1_8_2_puertas_invalidas_con_su_motivo(puerta, motivo):
    assert motivo_puerta("10.0.0.5/24", puerta) == motivo


def test_ca_b1_8_2_si_la_ip_no_es_analizable_el_error_es_de_la_ip_no_de_la_puerta():
    assert motivo_puerta("10.0.0.5", "10.0.0.1") == MotivoRed.NO_IP
    assert motivo_puerta("basura", "10.0.0.1") == MotivoRed.NO_IP


def test_ca_b1_8_2_un_valor_que_no_es_texto_no_lanza():
    assert motivo_puerta("10.0.0.5/24", None) == MotivoRed.NO_IP  # type: ignore[arg-type]


def test_cl_b8_ip_inicial_y_puerta_con_otra_mascara_dan_fuera_de_red():
    # La IP 10.0.0.5/24 y una puerta que solo está en la misma red con /16.
    assert motivo_puerta("10.0.0.5/24", "10.0.5.1") == MotivoRed.FUERA_DE_RED
    assert motivo_puerta("10.0.0.5/16", "10.0.5.1") is None


# --- CA-B1.8.1 / CA-B1.8.4 / V-B32: DNS ---------------------------------------------------------


def test_ca_b1_8_1_dns_con_coma_y_espacio_se_normaliza_en_orden():
    assert normalizar_dns("8.8.8.8, 1.1.1.1") == (("8.8.8.8", "1.1.1.1"), None)
    assert normalizar_dns("8.8.8.8 1.1.1.1") == (("8.8.8.8", "1.1.1.1"), None)
    assert normalizar_dns("  8.8.8.8 ,\t 1.1.1.1  ") == (("8.8.8.8", "1.1.1.1"), None)
    assert normalizar_dns("8.8.8.8,,1.1.1.1") == (("8.8.8.8", "1.1.1.1"), None)


def test_ca_b1_8_1_dns_acepta_ipv6_y_la_deja_en_forma_canonica():
    assert normalizar_dns("2001:DB8::1") == (("2001:db8::1",), None)
    assert normalizar_dns("2001:4860:4860::8888, 8.8.4.4")[0] == ("2001:4860:4860::8888", "8.8.4.4")


def test_ca_b1_8_1_dns_quita_repetidos_conservando_el_orden():
    assert normalizar_dns("1.1.1.1 8.8.8.8 1.1.1.1")[0] == ("1.1.1.1", "8.8.8.8")


@pytest.mark.parametrize("texto", ["", "   ", "\t\n"])
def test_ca_b1_8_6_dns_vacio_es_sin_servidores_y_sin_error(texto):
    assert normalizar_dns(texto) == ((), None)


@pytest.mark.parametrize(
    "texto",
    [
        "8.8.8",
        "dns.local",
        "8.8.8.8;1.1.1.1",  # §10: sin «;»
        "8.8.8.8; 1.1.1.1",
        "8.8.8.8/24",
        "010.1.1.1",
        "fe80::1%eth0",
        "8.8.8.8 hola",
        "8.8.8.256",
    ],
)
def test_ca_b1_8_4_dns_no_validos_dan_no_ip_y_ninguna_direccion(texto):
    assert normalizar_dns(texto) == ((), MotivoRed.NO_IP)


def test_ca_b1_8_4_un_valor_que_no_es_texto_no_lanza():
    assert normalizar_dns(None) == ((), MotivoRed.NO_IP)  # type: ignore[arg-type]


# --- CA-B1.8.5 / V-B33: dominio de búsqueda ------------------------------------------------------


@pytest.mark.parametrize(
    "dominio", ["lab.local", "a", "a-b.c-d.example", "A.B", "1.2", "x" * 63, "ejemplo.com"]
)
def test_ca_b1_8_5_dominios_validos(dominio):
    assert dominio_valido(dominio)


@pytest.mark.parametrize(
    "dominio",
    [
        "",
        " ",
        "a b",
        "a..b",
        "_a.b",
        "a_b.c",
        "-a.b",
        "a-.b",
        "a.b.",
        ".",
        ".a",
        "ñ.es",
        "x" * 64,
        "a/b",
    ],
)
def test_ca_b1_8_5_dominios_invalidos(dominio):
    assert not dominio_valido(dominio)


def test_ca_b1_8_5_el_limite_total_es_253_caracteres():
    ok = ".".join(["a" * 63, "a" * 63, "a" * 63, "a" * 61])
    assert len(ok) == 253 and dominio_valido(ok)
    assert not dominio_valido(ok + "a")


def test_ca_b1_8_5_un_valor_que_no_es_texto_no_lanza():
    assert not dominio_valido(None)  # type: ignore[arg-type]
    assert not dominio_valido(5)  # type: ignore[arg-type]


# --- ip_desplazada --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cidr", "k", "esperado"),
    [
        ("10.0.0.50/24", 0, "10.0.0.50/24"),
        ("10.0.0.50/24", 2, "10.0.0.52/24"),
        ("10.0.0.250/24", 4, "10.0.0.254/24"),
        ("10.0.0.250/24", 5, None),  # 255 = difusión
        ("10.0.0.250/24", 6, None),  # otra red
        ("10.0.0.2/24", -1, "10.0.0.1/24"),
        ("10.0.0.2/24", -2, None),  # 0 = red
        ("10.0.0.1/30", 1, "10.0.0.2/30"),
        ("10.0.0.1/30", 2, None),
        ("10.0.0.5/16", 300, "10.0.1.49/16"),
        ("basura", 1, None),
        ("10.0.0.5", 1, None),
    ],
)
def test_ip_desplazada_solo_devuelve_hosts_utiles_con_el_mismo_prefijo(cidr, k, esperado):
    assert ip_desplazada(cidr, k) == esperado


def test_ip_desplazada_con_un_desplazamiento_absurdo_no_lanza():
    assert ip_desplazada("10.0.0.5/24", 10**12) is None
    assert ip_desplazada("10.0.0.5/24", -(10**12)) is None


# --- CA-B1.9.1 / CA-B1.9.7: la serie --------------------------------------------------------------


def test_ca_b1_9_1_tres_maquinas_reciben_50_51_y_52_por_orden():
    c = ci(tarjeta(0, FIJA, "10.0.0.50/24", serie=True, puerta="10.0.0.1"))
    ips = [expandir_serie(c, i).tarjetas[0].ip for i in range(3)]
    assert ips == ["10.0.0.50/24", "10.0.0.51/24", "10.0.0.52/24"]
    assert problemas_serie_lote(plan(c, 3)) == []


def test_ca_b1_9_1_la_puerta_es_unica_y_el_prefijo_se_conserva():
    c = ci(tarjeta(0, FIJA, "172.16.4.10/16", serie=True, puerta="172.16.0.1"))
    for i in range(3):
        t = expandir_serie(c, i).tarjetas[0]
        assert t.puerta == "172.16.0.1"
        assert t.ip == f"172.16.4.{10 + i}/16"


def test_ca_b1_9_1_la_expansion_deja_serie_falso_y_anota_la_inicial_sin_afectar_la_igualdad():
    c = ci(tarjeta(0, FIJA, "10.0.0.250/24", serie=True))
    t = expandir_serie(c, 2).tarjetas[0]
    assert t.serie is False
    assert t.serie_inicial == "10.0.0.250/24"
    assert t.ip == "10.0.0.252/24"
    # ``serie_inicial`` no cuenta en la igualdad (compare=False).
    assert t == dataclasses.replace(t, serie_inicial=None)


def test_ca_b1_9_1_expandir_dos_veces_es_igual_que_expandir_una():
    c = ci(tarjeta(0, FIJA, "10.0.0.50/24", serie=True, puerta="10.0.0.1"))
    una = expandir_serie(c, 2)
    assert expandir_serie(una, 5) == una


def test_ca_b1_9_1_una_configuracion_sin_serie_se_devuelve_tal_cual():
    c = ci(tarjeta(0, FIJA, "10.0.0.50/24"), tarjeta(1, DHCP))
    assert expandir_serie(c, 7) is c


def test_ca_b1_9_1_cada_tarjeta_tiene_su_propia_serie():
    c = ci(
        tarjeta(0, FIJA, "10.0.0.50/24", serie=True),
        tarjeta(1, FIJA, "10.1.0.100/24", serie=True),
        tarjeta(2, FIJA, "10.2.0.7/24"),  # sin serie: igual en todas (V-B38 si N > 1)
    )
    e = expandir_serie(c, 3)
    assert [t.ip for t in e.tarjetas] == ["10.0.0.53/24", "10.1.0.103/24", "10.2.0.7/24"]


def test_ca_b1_9_1_serie_en_tarjeta_dhcp_o_sin_ip_se_ignora_sin_romper():
    c = ci(tarjeta(0, DHCP, serie=True), tarjeta(1, FIJA, None, serie=True))
    e = expandir_serie(c, 4)
    assert all(t.serie is False for t in e.tarjetas)
    assert [t.ip for t in e.tarjetas] == [None, None]


def test_ca_b1_9_1_una_ip_inicial_ilegible_se_conserva_para_que_la_senale_v_b26():
    c = ci(tarjeta(0, FIJA, "basura", serie=True))
    t = expandir_serie(c, 3).tarjetas[0]
    assert t.ip == "basura" and t.serie is False


def test_ca_b1_9_1_una_ip_inicial_ilegible_no_genera_ruido_de_v_b31_en_el_lote():
    c = ci(tarjeta(0, FIJA, "basura", serie=True))
    # El error de esa IP es de V-B26; V-B30/V-B31/V-B38 solo hablan de direcciones válidas.
    assert problemas_serie_lote(plan(c, 3)) == []


def test_ca_b1_9_7_un_lote_de_una_sola_maquina_usa_la_ip_inicial():
    c = ci(tarjeta(0, FIJA, "10.0.0.50/24", serie=True))
    assert expandir_serie(c, 0).tarjetas[0].ip == "10.0.0.50/24"
    assert problemas_serie_lote(plan(c, 1)) == []


def test_ca_b1_9_7_un_lote_de_una_maquina_con_ip_fija_sin_serie_no_da_v_b38():
    assert problemas_serie_lote(plan(ci(tarjeta(0, FIJA, "10.0.0.5/24")), 1)) == []


# --- CA-B1.9.2 / CA-B1.9.3 / CA-B1.9.4 / CL-B6 / CL-B7: V-B30 -------------------------------------


def test_ca_b1_9_2_diez_maquinas_desde_250_desbordan_y_se_nombra_la_primera_afectada():
    c = ci(tarjeta(0, FIJA, "10.0.0.250/24", serie=True))
    (p,) = problemas_serie_lote(plan(c, 10))
    assert p.regla == "V-B30" and p.severidad == Severidad.ERROR
    assert p.indice == 5  # la sexta MV: 250 + 5 = 255 (difusión)
    assert p.params["nombre"] == "web-06"
    assert p.params["direccion"] == "10.0.0.255"
    assert p.params["afectadas"] == "5"  # web-06 .. web-10
    assert p.campo == "cloudinit.tarjetas[0].ip"


def test_ca_b1_9_2_una_serie_que_llega_justo_a_la_ultima_direccion_util_es_valida():
    c = ci(tarjeta(0, FIJA, "10.0.0.250/24", serie=True))
    assert problemas_serie_lote(plan(c, 5)) == []  # .250 a .254
    assert reglas(problemas_serie_lote(plan(c, 6))) == ["V-B30"]


def test_ca_b1_9_2_si_la_serie_sale_de_la_red_el_motivo_es_desborde():
    c = ci(tarjeta(0, FIJA, "10.0.0.254/24", serie=True))
    # Con 3 MVs: .254 (ok), .255 (difusión) y 10.0.1.0 (otra red). Se informa la primera.
    (p,) = problemas_serie_lote(plan(c, 3))
    assert p.params["motivo"] == "red_o_difusion" and p.indice == 1
    assert p.params["afectadas"] == "2"


def test_ca_b1_9_3_la_serie_que_pasa_por_la_puerta_nombra_la_mv_y_la_direccion():
    c = ci(tarjeta(0, FIJA, "10.0.0.1/24", serie=True, puerta="10.0.0.2"))
    (p,) = problemas_serie_lote(plan(c, 3))
    assert p.regla == "V-B30"
    assert p.params["motivo"] == "puerta"
    assert p.params["nombre"] == "web-02" and p.params["direccion"] == "10.0.0.2"
    assert p.indice == 1


def test_ca_b1_9_3_la_primera_ip_de_la_serie_igual_a_la_puerta_tambien_se_senala():
    c = ci(tarjeta(0, FIJA, "10.0.0.2/24", serie=True, puerta="10.0.0.2"))
    ps = problemas_serie_lote(plan(c, 2))
    assert [(p.regla, p.params["motivo"], p.indice) for p in ps] == [("V-B30", "puerta", 0)]


def test_ca_b1_9_3_una_puerta_fuera_de_la_serie_no_da_problema():
    c = ci(tarjeta(0, FIJA, "10.0.0.50/24", serie=True, puerta="10.0.0.1"))
    assert problemas_serie_lote(plan(c, 10)) == []


def test_ca_b1_9_4_la_serie_que_alcanza_la_direccion_de_difusion_es_error():
    c = ci(tarjeta(0, FIJA, "192.168.1.125/25", serie=True))  # difusión de la red: .127
    (p,) = problemas_serie_lote(plan(c, 4))
    assert (p.regla, p.params["motivo"], p.params["direccion"]) == (
        "V-B30",
        "red_o_difusion",
        "192.168.1.127",
    )


def test_cl_b6_serie_desde_254_con_una_maquina_es_valida_y_con_dos_desborda():
    c = ci(tarjeta(0, FIJA, "10.0.0.254/24", serie=True))
    assert problemas_serie_lote(plan(c, 1)) == []
    assert reglas(problemas_serie_lote(plan(c, 2))) == ["V-B30"]


def test_cl_b6_con_una_maquina_y_la_254_como_puerta_el_conflicto_es_de_v_b28_no_de_serie():
    c = ci(tarjeta(0, FIJA, "10.0.0.254/24", serie=True, puerta="10.0.0.254"))
    assert reglas(problemas_serie_lote(plan(c, 1))) == ["V-B30"]  # puerta == IP de la MV 0
    assert motivo_puerta("10.0.0.254/24", "10.0.0.254") == MotivoRed.IGUAL_A_IP


def test_cl_b7_prefijo_30_con_tres_maquinas_sale_de_la_red():
    c = ci(tarjeta(0, FIJA, "10.0.0.1/30", serie=True))  # hosts útiles: .1 y .2
    (p,) = problemas_serie_lote(plan(c, 3))
    assert p.regla == "V-B30" and p.indice == 2 and p.params["direccion"] == "10.0.0.3"
    assert problemas_serie_lote(plan(c, 2)) == []


def test_v_b30_se_notifica_una_vez_por_serie_aunque_desborden_varias_maquinas():
    c = ci(tarjeta(0, FIJA, "10.0.0.250/24", serie=True))
    ps = problemas_serie_lote(plan(c, 30))
    assert reglas(ps) == ["V-B30"]
    assert ps[0].params["afectadas"] == "25"


def test_v_b30_cada_tarjeta_con_serie_desbordada_da_su_propio_problema():
    c = ci(
        tarjeta(0, FIJA, "10.0.0.254/24", serie=True),
        tarjeta(1, FIJA, "10.0.1.254/24", serie=True),
    )
    ps = problemas_serie_lote(plan(c, 3))
    assert reglas(ps) == ["V-B30", "V-B30"]
    assert [p.campo for p in ps] == ["cloudinit.tarjetas[0].ip", "cloudinit.tarjetas[1].ip"]
    assert [p.params["tarjeta"] for p in ps] == ["0", "1"]


# --- CA-B1.9.5 / V-B38: la misma IP en un lote ----------------------------------------------------


def test_ca_b1_9_5_ip_fija_sin_serie_en_un_lote_de_tres_es_v_b38_y_es_del_lote():
    c = ci(tarjeta(0, FIJA, "10.0.0.5/24"))
    (p,) = problemas_serie_lote(plan(c, 3))
    assert p.regla == "V-B38" and p.severidad == Severidad.ERROR
    assert p.indice is None  # problema del lote, no de una MV
    assert p.params == {"tarjeta": "0", "cantidad": "3"}
    assert p.campo == "cloudinit.tarjetas[0].ip"


def test_ca_b1_9_5_con_dos_maquinas_ya_es_v_b38():
    assert reglas(problemas_serie_lote(plan(ci(tarjeta(0, FIJA, "10.0.0.5/24")), 2))) == ["V-B38"]


def test_ca_b1_9_5_v_b38_solo_si_todas_las_maquinas_comparten_la_ip():
    """§10: si solo algunas repiten, la regla es V-B31 (por repetida), no V-B38."""
    elementos = plan(ci(tarjeta(0, FIJA, "10.0.0.5/24")), 3)
    otra = dataclasses.replace(elementos[2].cfg, cloudinit=ci(tarjeta(0, FIJA, "10.0.0.9/24")))
    elementos[2] = dataclasses.replace(elementos[2], cfg=otra)
    ps = problemas_serie_lote(elementos)
    assert reglas(ps) == ["V-B31"]
    assert ps[0].params["direccion"] == "10.0.0.5" and ps[0].params["nombre"] == "web-02"


def test_ca_b1_9_5_ips_distintas_por_maquina_no_dan_problema():
    elementos = plan(ci(tarjeta(0, FIJA, "10.0.0.5/24")), 3)
    for i, e in enumerate(elementos):
        cfg = dataclasses.replace(e.cfg, cloudinit=ci(tarjeta(0, FIJA, f"10.0.0.{10 + i}/24")))
        elementos[i] = dataclasses.replace(e, cfg=cfg)
    assert problemas_serie_lote(elementos) == []


def test_ca_b1_9_5_dhcp_o_sin_configurar_repetido_no_es_ip_repetida():
    for t in (tarjeta(0, DHCP), tarjeta(0, SIN)):
        assert problemas_serie_lote(plan(ci(t), 4)) == []


def test_ca_b1_9_5_elementos_sin_cloudinit_o_lote_vacio_no_dan_problema():
    assert problemas_serie_lote(plan(None, 3)) == []
    assert problemas_serie_lote([]) == []


# --- CA-B1.9.6 / V-B31: solapes -------------------------------------------------------------------


def test_ca_b1_9_6_dos_series_de_tarjetas_distintas_que_se_solapan_dan_v_b31():
    c = ci(
        tarjeta(0, FIJA, "10.0.0.50/24", serie=True),
        tarjeta(1, FIJA, "10.0.0.51/24", serie=True),
    )
    ps = problemas_serie_lote(plan(c, 3))
    assert set(reglas(ps)) == {"V-B31"}
    assert [p.params["direccion"] for p in ps] == ["10.0.0.51", "10.0.0.52"]
    assert all(p.severidad == Severidad.ERROR for p in ps)


def test_ca_b1_9_6_dos_tarjetas_de_la_misma_maquina_con_la_misma_ip_dan_v_b31():
    c = ci(tarjeta(0, FIJA, "10.0.0.5/24"), tarjeta(1, FIJA, "10.0.0.5/24"))
    (p,) = problemas_serie_lote(plan(c, 1))
    assert p.regla == "V-B31" and p.indice == 0
    assert p.params["direccion"] == "10.0.0.5"
    assert p.params["nombre"] == p.params["con"] == "web-01"


def test_ca_b1_9_6_series_en_redes_distintas_no_se_solapan():
    c = ci(
        tarjeta(0, FIJA, "10.0.0.50/24", serie=True),
        tarjeta(1, FIJA, "10.0.1.50/24", serie=True),
    )
    assert problemas_serie_lote(plan(c, 5)) == []


def test_ca_b1_9_6_una_serie_que_choca_con_la_ip_fija_de_otra_maquina_da_v_b31():
    """CSV/filas: una fila con IP fija propia dentro del rango de la serie de las demás."""
    elementos = plan(ci(tarjeta(0, FIJA, "10.0.0.50/24", serie=True)), 3)  # .50 .51 .52
    fija = dataclasses.replace(elementos[2].cfg, cloudinit=ci(tarjeta(0, FIJA, "10.0.0.50/24")))
    elementos[2] = dataclasses.replace(elementos[2], cfg=fija)
    ps = problemas_serie_lote(elementos)
    assert reglas(ps) == ["V-B31"]
    assert ps[0].params == {
        "direccion": "10.0.0.50",
        "tarjeta": "0",
        "nombre": "web-03",
        "con": "web-01",
    }


def test_ca_b1_9_6_cada_direccion_repetida_se_notifica_una_sola_vez():
    c = ci(tarjeta(0, FIJA, "10.0.0.5/24"), tarjeta(1, FIJA, "10.0.0.5/24"))
    elementos = plan(c, 4)
    # Con N=4 y todas iguales: V-B38 para la tarjeta 0 y la 1; no se repite V-B31 de lo ya cubierto.
    ps = problemas_serie_lote(elementos)
    assert reglas(ps).count("V-B38") == 2
    assert "V-B31" not in reglas(ps)


# --- CA-B1.9.9: recalcular al cambiar el número de MVs --------------------------------------------


def test_ca_b1_9_9_al_cambiar_el_numero_de_maquinas_las_ips_y_las_validaciones_se_recalculan():
    c = ci(tarjeta(0, FIJA, "10.0.0.250/24", serie=True))
    assert problemas_serie_lote(plan(c, 5)) == []
    assert reglas(problemas_serie_lote(plan(c, 10))) == ["V-B30"]
    assert problemas_serie_lote(plan(c, 4)) == []
    ips5 = [e.cfg.cloudinit.tarjetas[0].ip for e in plan(c, 5)]
    ips3 = [e.cfg.cloudinit.tarjetas[0].ip for e in plan(c, 3)]
    assert ips3 == ips5[:3]  # recortar el lote no cambia las IPs de las que quedan


# --- Propiedad: la serie coincide con un oráculo independiente ------------------------------------


def _oraculo(inicial: str, puerta: str | None, n: int) -> bool:
    """¿La serie de ``n`` MVs desde ``inicial`` es válida? Calculado con ``ipaddress`` a pelo."""
    interfaz = ipaddress.ip_interface(inicial)
    hosts = list(interfaz.network.hosts())
    desde = hosts.index(interfaz.ip)
    if desde + n > len(hosts):
        return False
    usadas = hosts[desde : desde + n]
    return not (puerta is not None and ipaddress.ip_address(puerta) in usadas)


def test_propiedad_la_regla_de_serie_coincide_con_un_oraculo_independiente():
    rng = random.Random(SEMILLA)
    for _ in range(400):
        prefijo = rng.choice([24, 25, 26, 27, 28, 29, 30])
        red = ipaddress.ip_network(
            f"10.{rng.randint(0, 3)}.{rng.randint(0, 3)}.0/{prefijo}", strict=False
        )
        hosts = list(red.hosts())
        inicio = rng.choice(hosts)
        inicial = f"{inicio}/{prefijo}"
        puerta = str(rng.choice(hosts)) if rng.random() < 0.5 else None
        n = rng.randint(1, min(len(hosts) + 3, 12))
        c = ci(tarjeta(0, FIJA, inicial, serie=True, puerta=puerta))
        ps = [p for p in problemas_serie_lote(plan(c, n)) if p.regla == "V-B30"]
        assert (not ps) == _oraculo(inicial, puerta, n), (inicial, puerta, n)
        assert len(ps) <= 1  # una vez por serie
        # Una serie sin V-B30 nunca repite direcciones.
        if not ps:
            assert "V-B31" not in reglas(problemas_serie_lote(plan(c, n)))


def test_propiedad_motivo_cidr_acepta_exactamente_lo_que_acepta_un_oraculo():
    rng = random.Random(SEMILLA + 1)
    for _ in range(500):
        octetos = [
            str(rng.choice([0, 1, 9, 10, 100, 127, 169, 172, 192, 224, 254, 255])) for _ in range(4)
        ]
        prefijo = rng.choice([0, 7, 8, 16, 24, 30, 31, 32])
        texto = ".".join(octetos) + f"/{prefijo}"
        interfaz = ipaddress.ip_interface(texto) if prefijo <= 32 else None
        esperado_ok = (
            PREFIJO_MIN <= prefijo <= PREFIJO_MAX
            and interfaz is not None
            and not (
                interfaz.ip.is_loopback
                or interfaz.ip.is_multicast
                or interfaz.ip.is_link_local
                or interfaz.ip.is_reserved
                or int(octetos[0]) == 0
            )
            and interfaz.ip
            not in (interfaz.network.network_address, interfaz.network.broadcast_address)
        )
        assert (motivo_cidr(texto) is None) == esperado_ok, texto
