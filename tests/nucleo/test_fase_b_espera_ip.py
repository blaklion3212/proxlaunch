"""B3: espera de la IP de cada máquina con el agente invitado (RF-B3.1..B3.5, RF-B3.7).

Requisitos: CA-B3.1.4, CA-B3.2.1..5, CA-B3.3.1..6, CA-B3.4.1..6, CA-B3.5.1..4, CA-B3.7.1..2,
CL-B15..B17 y R-B22 (clasificación de errores por texto y por código).

Se prueba por la interfaz pública: ``EsperaIp`` (con un reloj simulado, sin ``sleep`` ni red),
``MotorLote.ejecutar(..., espera_ip=)``, ``enlazar_espera`` y ``Libro.registrar_ip``. El servidor
es un ``ClusterAgente`` (doble) y los errores salen del traductor real de Proxmox.
"""

from __future__ import annotations

import dataclasses
import threading
from typing import Any

import pytest

from proxlaunch.nucleo.agente.calendario import (
    INTERVALO_S,
    MAX_POR_SEGUNDO,
    CalendarioSondeo,
    intervalo_para,
)
from proxlaunch.nucleo.agente.clasificacion import Clase, clasificar_error
from proxlaunch.nucleo.agente.espera import EsperaIp
from proxlaunch.nucleo.agente.modelos import (
    SIN_IP_UTIL,
    TERMINALES,
    EstadoIp,
    ResultadoIp,
)
from proxlaunch.nucleo.agente.seleccion import elegir_ip, interpretar_interfaces
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.libro import (
    AVISO_IP_NO_COINCIDE,
    AVISO_IP_NO_OBTENIDA,
    AVISO_IP_PARCIAL,
    Libro,
)
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.motor import enlazar_espera

from .apoyo_fase_b_agente import (
    MAC_NET0,
    MAC_OTRA,
    ClusterAgente,
    cargar_respuestas_agente,
    correr,
    crear_mundo_agente,
    ejecutar_espera,
    err_mv_apagada,
    err_no_en_ejecucion,
    err_no_existe,
    err_sesion_caducada,
    err_sin_agente,
    err_sin_permiso,
    error_http,
    interfaz,
    lote,
    mac_de,
    mundo_con_mvs,
    respuesta,
    respuesta_con_ip,
    vmids,
)
from .apoyo_lote import ControlAutomatico

DATOS = cargar_respuestas_agente()
IP = "192.168.1.50"


def interfaces_de(cuerpo: Any):
    return interpretar_interfaces(cuerpo)


# --- Selección de la IP (RF-B3.4): función pura --------------------------------------------------


def test_ca_b3_4_1_la_principal_es_la_ipv4_de_la_interfaz_con_la_mac_de_net0():
    """CA-B3.4.1: ``lo``, ``ens18`` (MAC de net0) y ``docker0``: gana ``192.168.1.50``."""
    eleccion = elegir_ip(interfaces_de(DATOS["tipica"]), MAC_NET0, final=False)
    assert eleccion is not None
    assert eleccion.principal == IP and eleccion.parcial is False
    assert "172.17.0.1" not in (eleccion.principal, *eleccion.otras)
    assert {"lo", "docker0"} <= set(eleccion.descartadas)


def test_ca_b3_4_1_las_otras_ips_validas_se_guardan_aparte():
    cuerpo = respuesta(
        interfaz("ens18", MAC_NET0, IP, "2001:db8::50"),
        interfaz("ens19", MAC_OTRA, "10.20.30.40"),
        interfaz("docker0", "02:42:ac:11:00:01", "172.17.0.1"),
    )
    eleccion = elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=False)
    assert eleccion is not None and eleccion.principal == IP
    assert set(eleccion.otras) == {"2001:db8::50", "10.20.30.40"}
    assert IP not in eleccion.otras


@pytest.mark.parametrize("nombre", ["docker0", "docker_gwbridge", "br-1a2b3c", "veth9", "virbr0"])
def test_ca_b3_4_6_las_interfaces_de_contenedores_y_puentes_se_descartan(nombre):
    """CA-B3.4.6: ``br-*``, ``veth*``, ``virbr*`` y ``docker*`` con IPv4 válida no valen."""
    cuerpo = respuesta(interfaz(nombre, MAC_NET0, "10.9.8.7"))
    for final in (False, True):
        assert elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=final) is None


def test_ca_b3_4_6_un_nombre_que_solo_se_parece_a_un_prefijo_no_se_descarta():
    """``bridge0`` o ``eth-docker`` no empiezan por ``br-`` ni ``docker``: son válidas."""
    for nombre in ("bridge0", "eth-docker", "ens18"):
        cuerpo = respuesta(interfaz(nombre, MAC_NET0, IP))
        eleccion = elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=False)
        assert eleccion is not None and eleccion.principal == IP, nombre


@pytest.mark.parametrize("mac", [None, "00:00:00:00:00:00", "no-es-una-mac", "bc:24:11"])
def test_ca_b3_4_3_sin_mac_valida_o_con_mac_nula_la_interfaz_se_descarta(mac):
    cuerpo = respuesta(interfaz("ens18", mac, IP))
    for final in (False, True):
        assert elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=final) is None


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "127.8.9.10", "::1", "fe80::1", "169.254.7.7", "0.0.0.0"]
)
def test_ca_b3_3_6_direcciones_de_loopback_y_enlace_local_nunca_valen(ip):
    cuerpo = respuesta(interfaz("ens18", MAC_NET0, ip))
    for final in (False, True):
        assert elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=final) is None


@pytest.mark.parametrize(
    "mac_agente",
    ["BC:24:11:AA:BB:01", "bc:24:11:aa:bb:01", "BC-24-11-AA-BB-01", "bc2411aabb01"],
)
@pytest.mark.parametrize(
    "mac_net0", ["BC:24:11:AA:BB:01", "bc:24:11:aa:bb:01", "bc-24-11-aa-bb-01"]
)
def test_ca_b3_4_la_mac_se_compara_sin_distinguir_mayusculas_ni_separadores(mac_agente, mac_net0):
    cuerpo = respuesta(interfaz("ens18", mac_agente, IP))
    eleccion = elegir_ip(interfaces_de(cuerpo), mac_net0, final=False)
    assert eleccion is not None and eleccion.principal == IP and eleccion.parcial is False


def test_ca_b3_4_2_una_ipv4_de_otra_interfaz_solo_se_elige_al_agotar_el_plazo():
    cuerpo = respuesta(interfaz("ens19", MAC_OTRA, "10.20.30.40"))
    assert elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=False) is None
    final = elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=True)
    assert final is not None and final.principal == "10.20.30.40" and final.parcial is True


def test_prioridad_la_ipv4_de_net0_gana_a_la_de_otra_interfaz_y_esta_a_la_ipv6():
    cuerpo = respuesta(
        interfaz("ens19", MAC_OTRA, "10.20.30.40", "2001:db8::9"),
        interfaz("ens18", MAC_NET0, IP),
    )
    eleccion = elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=True)
    assert eleccion is not None and eleccion.principal == IP and eleccion.parcial is False
    solo_otras = respuesta(interfaz("ens19", MAC_OTRA, "2001:db8::9", "10.20.30.40"))
    ultima = elegir_ip(interfaces_de(solo_otras), MAC_NET0, final=True)
    assert ultima is not None and ultima.principal == "10.20.30.40" and ultima.parcial is True


def test_solo_ipv6_global_es_parcial_y_solo_al_agotar_el_plazo():
    cuerpo = respuesta(interfaz("ens18", MAC_NET0, "2001:db8::50", "fe80::1"))
    assert elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=False) is None
    final = elegir_ip(interfaces_de(cuerpo), MAC_NET0, final=True)
    assert final is not None and final.principal == "2001:db8::50" and final.parcial is True


def test_sin_mac_conocida_de_net0_no_hay_principal_antes_del_fin_del_plazo():
    cuerpo = respuesta(interfaz("ens18", MAC_NET0, IP))
    assert elegir_ip(interfaces_de(cuerpo), None, final=False) is None
    final = elegir_ip(interfaces_de(cuerpo), None, final=True)
    assert final is not None and final.principal == IP and final.parcial is True


@pytest.mark.parametrize("cuerpo", DATOS["inesperadas"])
def test_ca_b3_4_4_texto_no_confiable_nunca_lanza_y_no_da_ip(cuerpo):
    """CA-B3.4.4: ``ip-addresses: "x"``, ``result: null``, tipos raros… sin excepción."""
    interfaces = interpretar_interfaces(cuerpo)
    for final in (False, True):
        assert elegir_ip(interfaces, MAC_NET0, final=final) is None


def test_una_respuesta_enorme_se_acota_sin_fallar():
    cuerpo = respuesta(
        *(interfaz(f"if{i}", MAC_OTRA, f"10.0.{i % 250}.{i % 200 + 1}") for i in range(5000))
    )
    interfaces = interpretar_interfaces(cuerpo)
    assert len(interfaces) <= 64


# --- Clasificación de errores (R-B22): por código Y por texto ------------------------------------


@pytest.mark.parametrize(
    ("error", "clase"),
    [
        (err_no_en_ejecucion(), Clase.TODAVIA_NO),
        (err_mv_apagada(), Clase.TODAVIA_NO),
        (err_sin_agente(), Clase.SIN_AGENTE),
        (err_sin_permiso(), Clase.SIN_PERMISO),
        (error_http(596, ""), Clase.TODAVIA_NO),
        (error_http(500, "algo que no esperábamos"), Clase.TODAVIA_NO),
        (error_http(502, "Bad Gateway"), Clase.TODAVIA_NO),
        (err_sesion_caducada(), Clase.FATAL),
        (error_http(401, "invalid credentials"), Clase.FATAL),
        (err_no_existe(), Clase.MV_NO_EXISTE),
        (ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {}, "no such VM"), Clase.MV_NO_EXISTE),
        # Solo el código, sin texto útil
        (ErrorProxLaunch(CodigoError.AGENTE_NO_CONFIGURADO), Clase.SIN_AGENTE),
        (ErrorProxLaunch(CodigoError.AGENTE_NO_RESPONDE), Clase.TODAVIA_NO),
        (ErrorProxLaunch(CodigoError.MV_NO_EN_MARCHA), Clase.TODAVIA_NO),
        (ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE), Clase.SIN_PERMISO),
        (ErrorProxLaunch(CodigoError.SESION_EXPIRADA), Clase.FATAL),
        # Solo el texto, con un código genérico
        (
            ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "No QEMU guest agent configured"),
            Clase.SIN_AGENTE,
        ),
        (
            ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "QEMU guest agent is not running"),
            Clase.TODAVIA_NO,
        ),
    ],
)
def test_r_b22_clasificacion_de_los_errores_del_sondeo(error, clase):
    assert clasificar_error(error) == clase


# --- Calendario (RF-B3.7): puro y determinista ---------------------------------------------------


@pytest.mark.parametrize(
    ("en_espera", "esperado"),
    [(0, 5.0), (1, 5.0), (25, 5.0), (26, 5.2), (50, 10.0), (100, 20.0), (250, 50.0)],
)
def test_ca_b3_7_el_intervalo_crece_para_no_superar_5_peticiones_por_segundo(en_espera, esperado):
    assert intervalo_para(en_espera) == pytest.approx(esperado)
    assert en_espera / intervalo_para(en_espera) <= MAX_POR_SEGUNDO + 1e-9


def test_ca_b3_7_2_una_sola_mv_se_sondea_cada_5_segundos_exactos():
    cal = CalendarioSondeo()
    cal.anadir(100, 0.0, 120.0)
    assert INTERVALO_S == 5.0
    assert cal.siguiente(0.0) == (100, 0.0)
    cal.registrar_sondeo(100, 0.0)
    vmid, espera = cal.siguiente(0.0)
    assert vmid is None and espera == pytest.approx(5.0)
    assert cal.siguiente(4.99)[0] is None
    assert cal.siguiente(5.0) == (100, 0.0)


def test_el_calendario_separa_dos_sondeos_cualesquiera_al_menos_0_2_s():
    cal = CalendarioSondeo()
    cal.anadir(1, 0.0, 60.0)
    cal.anadir(2, 0.0, 60.0)
    assert cal.siguiente(0.0)[0] == 1
    cal.registrar_sondeo(1, 0.0)
    vmid, espera = cal.siguiente(0.0)
    assert vmid is None and espera >= 0.2
    assert cal.siguiente(0.2 + 1e-3)[0] == 2


def test_el_calendario_vence_el_plazo_y_se_vacia_al_quitar():
    cal = CalendarioSondeo()
    assert cal.vacio()
    cal.anadir(7, 10.0, 30.0)
    assert not cal.vacio()
    assert cal.vencidas(39.99) == [] and cal.vencidas(40.0) == [7]
    cal.quitar(7)
    cal.quitar(7)  # idempotente
    assert cal.vacio() and cal.vencidas(100.0) == []


# --- EsperaIp: flujo con una MV ------------------------------------------------------------------


def una_mv(
    *guion: Any, plazo: int = 120, mac: str = MAC_NET0, ip_configurada: str | None = None, **kw
):
    """Mundo con la MV 100 encendida, el guion dado y la espera ya corrida → (mundo, resultado)."""
    m = mundo_con_mvs(100, mac=mac, **kw)
    m.cluster.guion[100] = list(guion)
    espera = m.espera()
    espera.anadir(100, "pve1", plazo, ip_configurada)
    resultados = ejecutar_espera(m, espera)
    return m, resultados[100]


def test_ca_b3_2_1_ip_en_el_tercer_ciclo_emite_exactamente_3_sondeos_y_queda_obtenida():
    m, r = una_mv(err_no_en_ejecucion(), err_no_en_ejecucion(), respuesta_con_ip())
    assert r.estado == EstadoIp.OBTENIDA and r.principal == IP
    assert len(m.cluster.sondeos) == 3 and r.sondeos == 3


def test_ca_b3_2_3_y_b3_7_2_los_5_segundos_se_miden_con_el_reloj_inyectado():
    m, _ = una_mv(err_no_en_ejecucion(), err_no_en_ejecucion(), respuesta_con_ip())
    t = m.cluster.sondeos_de(100)
    assert t == pytest.approx([0.0, 5.0, 10.0])
    assert m.reloj.ahora() == pytest.approx(10.0)  # nada más que lo que el reloj simulado avanzó


def test_ca_b3_3_1_los_estados_son_esperando_esperando_obtenida():
    m = mundo_con_mvs(100)
    espera = m.espera()
    vistos: list[EstadoIp] = []

    def sondeo(_n: int):
        vistos.append(espera.estado(100))
        if len(vistos) < 3:
            raise err_no_en_ejecucion()
        return respuesta_con_ip()

    m.cluster.guion[100] = [sondeo]
    espera.anadir(100, "pve1", 120)
    assert espera.estado(100) == EstadoIp.PENDIENTE  # aún no se ha sondeado
    ejecutar_espera(m, espera)
    assert vistos == [EstadoIp.ESPERANDO, EstadoIp.ESPERANDO, EstadoIp.ESPERANDO]
    assert espera.estado(100) == EstadoIp.OBTENIDA


def test_ca_b3_3_2_sin_agente_en_el_primer_sondeo_no_hay_mas_peticiones():
    m, r = una_mv(err_sin_agente(), respuesta_con_ip())
    assert r.estado == EstadoIp.SIN_AGENTE
    assert len(m.cluster.sondeos) == 1


@pytest.mark.parametrize("agent", [None, "0", "enabled=0"])
def test_rf_b3_3_una_mv_sin_agent_habilitado_en_su_config_no_se_sondea(agent):
    m, r = una_mv(respuesta_con_ip(), agent=agent)
    assert r.estado == EstadoIp.SIN_AGENTE
    assert m.cluster.sondeos == []


def test_ca_b3_3_3_un_403_es_sin_permiso_y_no_hay_mas_peticiones():
    m, r = una_mv(err_sin_permiso(), respuesta_con_ip())
    assert r.estado == EstadoIp.SIN_PERMISO and len(m.cluster.sondeos) == 1
    assert r.error is not None and r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.principal is None


def test_ca_b3_3_4_el_plazo_agotado_con_el_agente_mudo_es_agente_no_responde():
    m, r = una_mv(err_no_en_ejecucion(), plazo=60)
    assert r.estado == EstadoIp.AGENTE_NO_RESPONDE and r.principal is None
    assert r.error is not None and r.error.codigo == CodigoError.AGENTE_NO_RESPONDE
    assert 60.0 <= m.reloj.ahora() <= 60.0 + 5.0  # como mucho el plazo más un ciclo
    assert 11 <= len(m.cluster.sondeos) <= 13  # uno cada 5 s dentro del plazo


def test_cl_b17_la_mv_que_responde_y_luego_se_apaga_acaba_con_lo_ultimo_que_dijo_el_agente():
    """Primero solo una IP de otra interfaz (no concluyente); luego «VM is not running»: sin
    errores, al agotar el plazo se informa la IP parcial que se llegó a ver."""
    cuerpo = respuesta(interfaz("ens19", MAC_OTRA, "10.20.30.40"))
    _, r = una_mv(cuerpo, err_mv_apagada(100), plazo=30)
    assert r.estado == EstadoIp.OBTENIDA_PARCIAL and r.principal == "10.20.30.40"
    assert r.error is None


def test_cl_b17_con_vm_is_not_running_todo_el_plazo_es_agente_no_responde():
    m, r = una_mv(err_mv_apagada(100), plazo=30)
    assert r.estado == EstadoIp.AGENTE_NO_RESPONDE
    assert r.error is not None and r.error.codigo == CodigoError.AGENTE_NO_RESPONDE


def test_ca_b3_3_5_respuestas_200_sin_ip_valida_dan_sin_ip_al_agotar_el_plazo():
    m, r = una_mv(respuesta(interfaz("ens18", MAC_NET0)), plazo=30)
    assert r.estado == EstadoIp.SIN_IP and r.principal is None and r.error is None
    assert m.reloj.ahora() >= 30.0


def test_ca_b3_3_6_solo_direcciones_descartables_es_sin_ip():
    m, r = una_mv(DATOS["solo_descartables"], plazo=30)
    assert r.estado == EstadoIp.SIN_IP and r.principal is None and r.otras == ()
    assert {"lo", "docker0"} <= set(r.descartadas)


def test_un_5xx_o_un_timeout_desconocido_cuenta_como_intento_fallido_y_se_sigue():
    m, r = una_mv(error_http(500, "algo raro"), error_http(596, ""), respuesta_con_ip())
    assert r.estado == EstadoIp.OBTENIDA and len(m.cluster.sondeos) == 3


def test_una_sesion_caducada_es_error_terminal_sin_mas_peticiones():
    m, r = una_mv(err_sesion_caducada(), respuesta_con_ip())
    assert r.estado == EstadoIp.ERROR and len(m.cluster.sondeos) == 1
    assert r.error is not None and r.error.codigo == CodigoError.SESION_EXPIRADA


def test_las_respuestas_de_error_no_se_reintentan_fuera_del_ciclo():
    """RF-B3.7: tras un error el siguiente sondeo llega a su turno (5 s), no antes."""
    m, _ = una_mv(error_http(500, "algo raro"), error_http(500, "algo raro"), respuesta_con_ip())
    t = m.cluster.sondeos_de(100)
    assert [round(b - a, 6) for a, b in zip(t, t[1:], strict=False)] == [5.0, 5.0]


def test_ca_b3_4_2_ip_de_otra_interfaz_se_espera_hasta_el_fin_del_plazo_y_es_parcial():
    cuerpo = respuesta(interfaz("ens19", MAC_OTRA, "10.20.30.40"))
    m, r = una_mv(cuerpo, plazo=60)
    assert r.estado == EstadoIp.OBTENIDA_PARCIAL and r.principal == "10.20.30.40"
    assert m.reloj.ahora() >= 60.0  # no se dio por buena antes de tiempo
    assert len(m.cluster.sondeos) >= 11


def test_cl_b16_ip_solo_en_una_interfaz_secundaria_es_obtenida_parcial():
    cuerpo = respuesta(
        interfaz("ens18", MAC_NET0),
        interfaz("ens19", MAC_OTRA, "10.20.30.40"),
    )
    _, r = una_mv(cuerpo, plazo=30)
    assert r.estado == EstadoIp.OBTENIDA_PARCIAL and r.principal == "10.20.30.40"


def test_solo_ipv6_global_al_agotar_el_plazo_es_obtenida_parcial():
    _, r = una_mv(respuesta(interfaz("ens18", MAC_NET0, "2001:db8::50")), plazo=20)
    assert r.estado == EstadoIp.OBTENIDA_PARCIAL and r.principal == "2001:db8::50"


def test_ca_b3_4_1_con_la_mac_de_net0_en_mayusculas_y_otra_en_minusculas_se_acierta():
    cuerpo = respuesta(
        interfaz("ens19", "bc:24:11:cc:dd:02", "10.20.30.40"),
        interfaz("ens18", "bc-24-11-aa-bb-01", IP),
    )
    m, r = una_mv(cuerpo)
    assert r.estado == EstadoIp.OBTENIDA and r.principal == IP and r.otras == ("10.20.30.40",)
    assert len(m.cluster.sondeos) == 1


def test_ca_b3_4_3_una_interfaz_sin_mac_o_con_mac_nula_no_da_ip():
    _, r = una_mv(
        respuesta(interfaz("ens18", None, IP), interfaz("ens19", "00:00:00:00:00:00", IP)), plazo=20
    )
    assert r.estado == EstadoIp.SIN_IP


@pytest.mark.parametrize("cuerpo", DATOS["inesperadas"])
def test_ca_b3_4_4_una_respuesta_inesperada_es_sin_ip_todavia_y_nunca_error(cuerpo):
    m, r = una_mv(cuerpo, plazo=20)
    assert r.estado == EstadoIp.SIN_IP
    assert r.error is None and len(m.cluster.sondeos) >= 3  # siguió sondeando


def test_ca_b3_4_4_el_cuerpo_del_error_de_un_sondeo_inesperado_no_se_pierde_en_el_resto():
    """Una MV con respuesta rara no impide que otra obtenga su IP."""
    m = mundo_con_mvs(100, 101)
    m.cluster.guion[100] = [DATOS["inesperadas"][2]]
    m.cluster.guion[101] = [respuesta_con_ip()]
    espera = m.espera()
    espera.anadir(100, "pve1", 20)
    espera.anadir(101, "pve1", 20)
    r = ejecutar_espera(m, espera)
    assert r[100].estado == EstadoIp.SIN_IP and r[101].estado == EstadoIp.OBTENIDA


@pytest.mark.parametrize(
    ("fija", "obtenida", "no_coincide"),
    [
        ("10.0.0.5/24", IP, True),
        ("192.168.1.50/24", IP, False),
        (None, IP, False),  # DHCP: no hay nada con qué comparar
        ("dhcp", IP, False),
    ],
)
def test_ca_b3_4_5_ip_fija_distinta_de_la_obtenida_se_senala(fija, obtenida, no_coincide):
    _, r = una_mv(respuesta_con_ip(obtenida), ip_configurada=fija)
    assert r.estado == EstadoIp.OBTENIDA and r.principal == obtenida
    assert r.no_coincide is no_coincide


def test_ca_b3_2_4_un_501_prueba_post_una_sola_vez_y_lo_recuerda():
    """GET→501; POST responde 200 (sin IP aún): desde entonces se usa POST directamente."""
    m = mundo_con_mvs(100)
    m.cluster.metodos_agente = {"POST"}
    m.cluster.guion[100] = [
        respuesta(interfaz("ens18", MAC_NET0)),
        respuesta(interfaz("ens18", MAC_NET0)),
        respuesta_con_ip(),
    ]
    espera = m.espera()
    espera.anadir(100, "pve1", 120)
    r = ejecutar_espera(m, espera)[100]
    assert r.estado == EstadoIp.OBTENIDA
    assert m.cluster.metodos_de(100) == [
        "GET",
        "POST",
        "POST",
        "POST",
    ]  # GET→501, luego POST recordado


def test_ca_b3_2_4_el_metodo_alternativo_se_recuerda_aunque_su_primera_respuesta_sea_error():
    m = mundo_con_mvs(100)
    m.cluster.metodos_agente = {"POST"}
    m.cluster.guion[100] = [err_no_en_ejecucion(), err_no_en_ejecucion(), respuesta_con_ip()]
    espera = m.espera()
    espera.anadir(100, "pve1", 120)
    r = ejecutar_espera(m, espera)[100]
    assert r.estado == EstadoIp.OBTENIDA
    assert m.cluster.metodos_de(100) == ["GET", "POST", "POST", "POST"]


def test_ca_b3_2_4_sin_501_el_metodo_inicial_es_get_y_no_se_alterna():
    m, _ = una_mv(err_no_en_ejecucion(), err_no_en_ejecucion(), respuesta_con_ip())
    assert set(m.cluster.metodos_de(100)) == {"GET"}


def test_ca_b3_2_4_si_ningun_metodo_esta_implementado_solo_se_prueba_el_otro_una_vez():
    m = mundo_con_mvs(100)
    m.cluster.metodos_agente = set()
    espera = m.espera()
    espera.anadir(100, "pve1", 30)
    r = ejecutar_espera(m, espera)[100]
    assert m.cluster.metodos_de(100).count("POST") == 1
    assert r.estado == EstadoIp.AGENTE_NO_RESPONDE


def test_ca_b3_2_5_si_la_mv_ya_no_existe_se_cancela_sin_error_ni_sondeos():
    m = crear_mundo_agente()  # la MV 100 no existe (borrada por Deshacer)
    espera = m.espera()
    espera.anadir(100, "pve1", 120)
    r = ejecutar_espera(m, espera)[100]
    assert r.estado == EstadoIp.CANCELADA and r.error is None
    assert m.cluster.sondeos == []


def test_ca_b3_2_5_si_la_mv_desaparece_a_mitad_de_la_espera_se_cancela_sin_error():
    m = mundo_con_mvs(100)

    def desaparece(_n: int):
        m.cluster.vms.pop(100)
        raise err_no_existe(100)

    m.cluster.guion[100] = [err_no_en_ejecucion(), desaparece]
    espera = m.espera()
    espera.anadir(100, "pve1", 120)
    r = ejecutar_espera(m, espera)[100]
    assert r.estado == EstadoIp.CANCELADA and r.error is None
    assert len(m.cluster.sondeos) == 2


# --- EsperaIp: alta, baja, cancelación y observadores --------------------------------------------


def test_omitir_deja_la_mv_omitida_sin_ninguna_peticion_y_es_idempotente():
    m = mundo_con_mvs(100)
    espera = m.espera()
    espera.omitir(100)
    espera.omitir(100)
    r = ejecutar_espera(m, espera)
    assert r[100].estado == EstadoIp.OMITIDA
    assert [v for v, _ in m.resultados] == [100]  # el observador solo se entera una vez
    assert m.cluster.llamadas == []


def test_anadir_una_mv_repetida_se_ignora():
    m = mundo_con_mvs(100)
    m.cluster.guion[100] = [respuesta_con_ip()]
    espera = m.espera()
    espera.anadir(100, "pve1", 60)
    espera.anadir(100, "pve1", 60)
    ejecutar_espera(m, espera)
    assert [v for v, _ in m.resultados] == [100] and len(m.cluster.sondeos) == 1


def test_ejecutar_vuelve_sin_objetivos_cuando_el_motor_ya_terminó():
    m = crear_mundo_agente()
    espera = m.espera()
    assert ejecutar_espera(m, espera) == {} and m.cluster.llamadas == []


def test_ca_b3_5_3_dejar_de_esperar_pasa_las_mvs_esperando_a_cancelada_sin_tocar_el_servidor():
    m = mundo_con_mvs(100, 101)
    espera = m.espera()

    def corta(_n: int):
        espera.cancelar()  # «Dejar de esperar» en mitad del sondeo
        return respuesta_con_ip()  # una respuesta que llega con la petición ya en vuelo

    m.cluster.guion[100] = [err_no_en_ejecucion(), corta]
    m.cluster.guion[101] = [err_no_en_ejecucion()]
    espera.anadir(100, "pve1", 120)
    espera.anadir(101, "pve1", 120)
    r = ejecutar_espera(m, espera)
    assert r[100].estado == EstadoIp.CANCELADA and r[101].estado == EstadoIp.CANCELADA
    assert r[100].principal is None  # la respuesta en vuelo se descartó
    assert m.cluster.escrituras_de() == [] and m.cluster.deletes == {}
    antes = len(m.cluster.sondeos)
    assert antes <= 4  # no siguió sondeando tras cancelar


def test_cancelar_es_sincrono_y_descarta_la_respuesta_de_una_peticion_en_vuelo():
    """CA-B3.5.4: al volver de ``cancelar([vmid])`` la MV ya está cancelada, aunque su petición
    siga en vuelo; así Deshacer puede lanzar el DELETE justo después."""
    m = mundo_con_mvs(100)
    en_vuelo, soltar = threading.Event(), threading.Event()

    def lenta(_n: int):
        en_vuelo.set()
        assert soltar.wait(10)
        return respuesta_con_ip()

    m.cluster.guion[100] = [lenta]
    espera = m.espera()
    espera.anadir(100, "pve1", 120)
    espera.sin_mas_objetivos()
    salida: dict[str, Any] = {}
    hilo = threading.Thread(target=lambda: salida.update(r=espera.ejecutar()), daemon=True)
    hilo.start()
    try:
        assert en_vuelo.wait(10)
        espera.cancelar([100])
        assert espera.estado(100) == EstadoIp.CANCELADA  # ya al volver
        sondeos_al_cancelar = len(m.cluster.sondeos)
    finally:
        soltar.set()
    hilo.join(10)
    assert not hilo.is_alive()
    assert salida["r"][100].estado == EstadoIp.CANCELADA and salida["r"][100].principal is None
    assert len(m.cluster.sondeos) == sondeos_al_cancelar  # ninguna petición posterior
    assert [e.estado for v, e in m.resultados if v == 100] == [EstadoIp.CANCELADA]


def test_cancelar_unas_mvs_no_toca_a_las_demas():
    m = mundo_con_mvs(100, 101)
    espera = m.espera()
    m.cluster.guion[101] = [respuesta_con_ip()]
    espera.anadir(100, "pve1", 120)
    espera.anadir(101, "pve1", 120)
    espera.cancelar([100])
    assert espera.estado(100) == EstadoIp.CANCELADA
    r = ejecutar_espera(m, espera)
    assert r[100].estado == EstadoIp.CANCELADA and r[101].estado == EstadoIp.OBTENIDA
    assert m.cluster.sondeos_de(100) == []


def test_una_mv_que_llega_despues_de_cancelar_todo_queda_cancelada_sin_sondear():
    m = mundo_con_mvs(100)
    espera = m.espera()
    espera.cancelar()
    espera.anadir(100, "pve1", 120)
    assert espera.estado(100) == EstadoIp.CANCELADA
    r = ejecutar_espera(m, espera)
    assert r[100].estado == EstadoIp.CANCELADA and m.cluster.sondeos == []


def test_los_observadores_se_avisan_una_vez_por_resultado_y_un_fallo_suyo_no_detiene_la_espera():
    m = mundo_con_mvs(100, 101)
    m.cluster.guion[100] = [respuesta_con_ip()]
    m.cluster.guion[101] = [respuesta_con_ip("192.168.1.51", "BC:24:11:AA:BB:01")]
    avisos: list[int] = []

    def roto(vmid: int, _r: ResultadoIp) -> None:
        avisos.append(vmid)
        raise RuntimeError("observador roto")

    estados: list[tuple[int, EstadoIp]] = []
    espera = EsperaIp(m.sesion, m.reloj, roto, al_estado=lambda v, e: estados.append((v, e)))
    espera.anadir(100, "pve1", 60)
    espera.anadir(101, "pve1", 60)
    r = ejecutar_espera(m, espera)
    assert sorted(avisos) == [100, 101]
    assert r[100].estado == EstadoIp.OBTENIDA and r[101].estado == EstadoIp.OBTENIDA
    assert sorted(estados) == [(100, EstadoIp.ESPERANDO), (101, EstadoIp.ESPERANDO)]


def test_todos_los_estados_terminales_son_los_que_la_tabla_de_rf_b3_3_dice():
    assert set(EstadoIp) - {EstadoIp.PENDIENTE, EstadoIp.ESPERANDO} == TERMINALES
    assert {
        EstadoIp.SIN_AGENTE,
        EstadoIp.AGENTE_NO_RESPONDE,
        EstadoIp.SIN_IP,
        EstadoIp.SIN_PERMISO,
        EstadoIp.ERROR,
    } == SIN_IP_UTIL


# --- Carga sobre el servidor (RF-B3.7, CL-B15) ---------------------------------------------------


def maximo_en_ventana(tiempos: list[float], ancho: float = 1.0) -> int:
    ts = sorted(tiempos)
    mejor = 0
    for i, t in enumerate(ts):
        mejor = max(mejor, sum(1 for u in ts[i:] if u < t + ancho))
    return mejor


def test_ca_b3_7_1_cien_mvs_en_espera_no_superan_5_sondeos_por_segundo_y_reciben_al_menos_3():
    m = mundo_con_mvs(*range(100, 200))
    espera = m.espera()
    for v in range(100, 200):
        espera.anadir(v, "pve1", 60)
    r = ejecutar_espera(m, espera, limite_s=60.0)
    assert len(r) == 100
    tiempos = [t for _, _, t in m.cluster.sondeos]
    assert maximo_en_ventana(tiempos) <= MAX_POR_SEGUNDO
    for v in range(100, 200):
        assert len(m.cluster.sondeos_de(v)) >= 3, v
    assert all(x.estado == EstadoIp.AGENTE_NO_RESPONDE for x in r.values())  # el plazo no se amplió
    assert m.reloj.ahora() <= 60.0 + 20.0 + 1e-6  # plazo más un ciclo (que con 100 MVs es 20 s)


def test_rf_b3_7_una_sola_lectura_de_config_por_mv_aparte_del_limite_de_sondeos():
    # Decisión de diseño (arquitectura §0 y §16, BUG-B-P3-1 aceptado): la lectura de config de la
    # primera visita no cuenta para el límite; los sondeos sí respetan 5/s y no hay más lecturas.
    m = mundo_con_mvs(*range(100, 200))
    espera = m.espera()
    for v in range(100, 200):
        espera.anadir(v, "pve1", 60)
    ejecutar_espera(m, espera, limite_s=60.0)
    lecturas = [c for c in m.cluster.llamadas if c.ruta.endswith("/config")]
    assert len(lecturas) == 100
    assert maximo_en_ventana([t for _, _, t in m.cluster.sondeos]) <= MAX_POR_SEGUNDO


def test_rf_b3_7_cada_mv_se_sondea_a_lo_sumo_cada_5_segundos():
    m = mundo_con_mvs(100, 101, 102)
    espera = m.espera()
    for v in (100, 101, 102):
        espera.anadir(v, "pve1", 60)
    ejecutar_espera(m, espera)
    for v in (100, 101, 102):
        t = m.cluster.sondeos_de(v)
        assert all(b - a >= 5.0 - 1e-6 for a, b in zip(t, t[1:], strict=False)), v


def test_ca_b3_5_1_veinte_mvs_sin_ip_con_plazo_60_duran_un_plazo_y_no_veinte():
    m = mundo_con_mvs(*range(100, 120))
    espera = m.espera()
    for v in range(100, 120):
        espera.anadir(v, "pve1", 60)
    r = ejecutar_espera(m, espera, limite_s=60.0)
    assert len(r) == 20
    assert all(x.estado == EstadoIp.AGENTE_NO_RESPONDE for x in r.values())
    assert 60.0 <= m.reloj.ahora() <= 65.0  # ≤ 65 s simulados, no 20 × 60


# --- Integración con el motor del lote (RF-B3.2, RF-B3.5) ----------------------------------------


def test_ca_b3_1_4_sin_la_casilla_no_hay_peticiones_de_agente_y_la_secuencia_es_la_de_060():
    b1, plan1 = lote(esperar_ip=False)
    libro1, espera1, _ = correr(b1, plan1, con_espera=True)
    b2, plan2 = lote(esperar_ip=False)
    correr(b2, plan2, con_espera=False)

    def secuencia(cl: ClusterAgente):
        return [(c.metodo, c.ruta, c.datos) for c in cl.llamadas]

    assert b1.cluster.sondeos == [] and not any("/agent/" in c.ruta for c in b1.cluster.llamadas)
    assert secuencia(b1.cluster) == secuencia(b2.cluster)
    assert espera1.resultados() == {}
    assert all(e.ip is None for e in libro1.instantanea())


def test_rf_b3_5_el_motor_termina_sin_esperar_a_ninguna_ip():
    """La creación y el encendido de todas las MVs terminan antes de que se sondee nada."""
    b, plan = lote(3)
    libro, espera, control = correr(b, plan)
    assert b.cluster.sondeos == []  # ningún sondeo: el motor no esperó
    assert sorted(b.cluster.inicios) == vmids(plan) and set(b.cluster.inicios.values()) == {1}
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK] * 3
    assert all(espera.estado(v) in (EstadoIp.PENDIENTE, EstadoIp.ESPERANDO) for v in vmids(plan))


def test_ca_b3_2_1_el_motor_entrega_cada_mv_encendida_y_la_ip_se_anota_en_el_libro():
    b, plan = lote(2)
    for v in vmids(plan):
        b.cluster.guion[v] = [respuesta_con_ip(f"192.168.1.{v % 200}", mac_de(v))]
    libro, espera, _ = correr(b, plan)
    resultados = ejecutar_espera(b, espera)
    assert {v: r.estado for v, r in resultados.items()} == {
        v: EstadoIp.OBTENIDA for v in vmids(plan)
    }
    for e in libro.instantanea():
        assert e.ip is not None and e.ip.principal == f"192.168.1.{e.elemento.vmid % 200}"
        assert e.estado == EstadoMV.OK and e.avisos == ()  # con IP no hay aviso


def test_ca_b3_2_2_un_encendido_fallido_no_se_sondea_y_su_ip_queda_omitida():
    b, plan = lote(3)
    malo = vmids(plan)[1]
    b.cluster.exitstatus_inicio[malo] = "start failed: error"
    for v in vmids(plan):
        b.cluster.guion[v] = [respuesta_con_ip(mac=mac_de(v))]
    libro, espera, _ = correr(b, plan)
    r = ejecutar_espera(b, espera)
    assert r[malo].estado == EstadoIp.OMITIDA
    assert b.cluster.sondeos_de(malo) == []
    otros = [v for v in vmids(plan) if v != malo]
    assert all(r[v].estado == EstadoIp.OBTENIDA for v in otros)
    entrada = {e.elemento.vmid: e for e in libro.instantanea()}[malo]
    assert entrada.ip is not None and entrada.ip.estado == EstadoIp.OMITIDA
    assert AVISO_IP_NO_OBTENIDA not in entrada.avisos  # «no aplicable», no «sin IP»


def test_una_mv_sin_encender_con_espera_pedida_queda_omitida():
    b, plan = lote(2, encender=False)
    libro, espera, _ = correr(b, plan)
    r = ejecutar_espera(b, espera)
    assert {x.estado for x in r.values()} == {EstadoIp.OMITIDA}
    assert b.cluster.sondeos == []


def test_ca_b3_5_2_tres_mvs_cuya_ip_se_agota_no_fallan_ni_pausan_el_lote():
    b, plan = lote(3, plazo=30)
    libro, espera, control = correr(b, plan)
    ejecutar_espera(b, espera)
    assert control.pausas == [] and not control.cancelado.is_set() and not control.suspendido
    assert sorted(b.cluster.posts) == vmids(plan)
    for e in libro.instantanea():
        assert e.estado == EstadoMV.CON_AVISOS and e.error is None
        assert AVISO_IP_NO_OBTENIDA in e.avisos
        assert e.ip is not None and e.ip.estado == EstadoIp.AGENTE_NO_RESPONDE
    assert b.cluster.deletes == {}  # el lote no se deshace


def test_ca_b3_5_2_los_resultados_malos_no_cuentan_para_la_politica_de_pausa():
    """Con 8 MVs sin IP (más que cualquier umbral de fallos seguidos) el lote no se pausa."""
    b, plan = lote(8, plazo=20)
    libro, espera, control = correr(b, plan)
    ejecutar_espera(b, espera)
    assert control.pausas == []
    assert {e.estado for e in libro.instantanea()} == {EstadoMV.CON_AVISOS}


def test_ca_b3_5_3_dejar_de_esperar_conserva_las_mvs_creadas():
    b, plan = lote(3, plazo=120)
    libro, espera, _ = correr(b, plan)
    espera.cancelar()
    ejecutar_espera(b, espera)
    for e in libro.instantanea():
        assert e.estado == EstadoMV.OK  # «cancelada» no añade aviso ni cambia el estado
        assert e.ip is not None and e.ip.estado == EstadoIp.CANCELADA
    assert b.cluster.sondeos == [] and b.cluster.deletes == {}
    assert sorted(b.cluster.vms) == vmids(plan)


def test_ca_b3_5_4_cancelar_una_mv_en_espera_antes_de_su_delete_deja_de_sondearla():
    b, plan = lote(2, plazo=120)
    libro, espera, _ = correr(b, plan)
    a, otra = vmids(plan)
    b.cluster.guion[otra] = [respuesta_con_ip("192.168.1.77", mac_de(otra))]
    espera.cancelar([a])  # lo que hace Deshacer justo antes del DELETE
    b.cluster.vms.pop(a)  # …y el DELETE ya borró la MV
    r = ejecutar_espera(b, espera)
    assert r[a].estado == EstadoIp.CANCELADA and r[otra].estado == EstadoIp.OBTENIDA
    assert b.cluster.sondeos_de(a) == []
    entrada = {e.elemento.vmid: e for e in libro.instantanea()}[a]
    assert entrada.ip is not None and entrada.ip.estado == EstadoIp.CANCELADA


def test_el_motor_y_la_espera_pueden_correr_a_la_vez_en_hilos_distintos():
    """La espera corre en su propio hilo mientras el motor crea: ninguno aguarda al otro."""
    b, plan = lote(3, plazo=30)
    libro = Libro(plan)
    espera = EsperaIp(b.sesion, b.reloj, enlazar_espera(libro, b.observador))
    salida: dict[str, Any] = {}
    hilo = threading.Thread(target=lambda: salida.update(r=espera.ejecutar()), daemon=True)
    hilo.start()
    b.motor().ejecutar(
        plan, b.inv, b.observador, ControlAutomatico("suspender"), libro=libro, espera_ip=espera
    )
    hilo.join(30)
    assert not hilo.is_alive(), "la espera debía terminar al avisar el motor de que no hay más MVs"
    assert set(salida["r"]) == set(vmids(plan))
    assert {e.estado for e in libro.instantanea()} == {EstadoMV.CON_AVISOS}


# --- Libro.registrar_ip: avisos por resultado (RF-B3.5) ------------------------------------------


def libro_con_mv_ok():
    b, plan = lote(1)
    libro, _, _ = correr(b, plan)
    return libro, vmids(plan)[0]


@pytest.mark.parametrize("estado", sorted(SIN_IP_UTIL))
def test_registrar_ip_sin_ip_util_pone_ip_no_obtenida_y_con_avisos(estado):
    libro, v = libro_con_mv_ok()
    entrada = libro.registrar_ip(v, ResultadoIp(estado))
    assert entrada is not None
    assert entrada.estado == EstadoMV.CON_AVISOS and entrada.avisos == (AVISO_IP_NO_OBTENIDA,)
    assert entrada.ip is not None and entrada.ip.estado == estado


@pytest.mark.parametrize("estado", [EstadoIp.OMITIDA, EstadoIp.CANCELADA, EstadoIp.OBTENIDA])
def test_registrar_ip_omitida_cancelada_u_obtenida_no_añade_avisos(estado):
    libro, v = libro_con_mv_ok()
    principal = IP if estado == EstadoIp.OBTENIDA else None
    entrada = libro.registrar_ip(v, ResultadoIp(estado, principal=principal))
    assert entrada is not None and entrada.estado == EstadoMV.OK and entrada.avisos == ()


def test_registrar_ip_parcial_y_no_coincide_añaden_su_aviso_sin_duplicarlo():
    libro, v = libro_con_mv_ok()
    r = ResultadoIp(EstadoIp.OBTENIDA_PARCIAL, principal="10.1.1.1", no_coincide=True)
    libro.registrar_ip(v, r)
    entrada = libro.registrar_ip(v, r)
    assert entrada is not None
    assert entrada.avisos == (AVISO_IP_PARCIAL, AVISO_IP_NO_COINCIDE)
    assert entrada.estado == EstadoMV.CON_AVISOS


def test_registrar_ip_desconocida_devuelve_none_y_no_cambia_nada():
    libro, v = libro_con_mv_ok()
    assert libro.registrar_ip(99999, ResultadoIp(EstadoIp.SIN_IP)) is None
    assert libro.instantanea()[0].ip is None and libro.instantanea()[0].elemento.vmid == v


def test_registrar_ip_no_cambia_el_estado_de_una_mv_fallida():
    b, plan = lote(1, plazo=20)
    v = vmids(plan)[0]
    b.cluster.exitstatus[v] = "TASK ERROR: boom"
    libro, _, _ = correr(b, plan)
    antes = libro.instantanea()[0]
    assert antes.estado not in (EstadoMV.OK, EstadoMV.CON_AVISOS)
    despues = libro.registrar_ip(v, ResultadoIp(EstadoIp.SIN_IP))
    assert despues is not None and despues.estado == antes.estado


def test_el_resultado_de_ip_nunca_lleva_datos_de_cloudinit_ni_credenciales():
    m, r = una_mv(respuesta_con_ip())
    assert dataclasses.is_dataclass(r)
    campos = {f.name for f in dataclasses.fields(r)}
    assert not campos & {"cloudinit", "usuario", "claves", "contrasena", "password"}
