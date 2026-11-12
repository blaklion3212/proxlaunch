"""Autenticación: token, ticket, renovación y 2FA (RF-01 a RF-04, A-7).
Transporte falso en memoria y reloj simulado."""

import pytest

from proxlaunch.nucleo.api.autenticacion import (
    AutenticadorTicket,
    AutenticadorToken,
    DesafioTFA,
    TipoTFA,
    iniciar_sesion_ticket,
    normalizar_usuario,
    responder_tfa,
)
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken, Ticket
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo_api import TOKEN_ID, TOKEN_SECRETO, Secuencia, TransporteFalso, ticket_parcial

MIN = 60.0
RUTA = "/access/ticket"


def _login(t: TransporteFalso, respuesta, **kw):
    t.en("POST", RUTA, respuesta)
    return iniciar_sesion_ticket(t, "root", "pam", "contra-secreta", **kw)


def _data_tfa(desafio, usuario="ana@pve"):
    return {
        "ticket": ticket_parcial(desafio),
        "CSRFPreventionToken": "6535AB12:cGFyY2lhbA",
        "username": usuario,
        "NeedTFA": 1,
    }


def _desafio(totp=True, recuperacion=True, **otros):
    return DesafioTFA("ana@pve", ticket_parcial({}), totp, recuperacion, tuple(otros))


# --- RF-01 / RF-03.4: token -------------------------------------------------------------


def test_ca_01_1_autenticador_token_pone_la_cabecera():
    cab, cook = {}, {}
    AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO)).aplicar("GET", cab, cook)
    assert cab == {"Authorization": f"PVEAPIToken={TOKEN_ID}={TOKEN_SECRETO}"}
    assert cook == {}


def test_ca_03_4_el_token_nunca_renueva(reloj):
    auth = AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO))
    reloj.avanzar(10 * 3600)
    t = TransporteFalso()
    assert auth.necesita_renovar() is False
    auth.renovar(t)
    assert t.llamadas == []


def test_ca_03_4_cliente_con_token_no_renueva_tras_muchas_horas(reloj):
    t = TransporteFalso().en("GET", "/version", {"version": "9.2.1"})
    auth = AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO))
    cliente = ClienteProxmox(t, auth, reloj)
    reloj.avanzar(5 * 3600)
    cliente.version()
    assert t.metodos == ["GET"]  # ningún POST /access/ticket


# --- RF-02: ticket ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("usuario", "realm", "esperado"),
    [
        pytest.param("root@pam", "pam", "root@pam", id="CA-02.4-no-duplica"),
        pytest.param("root", "pam", "root@pam", id="CA-02.4-agrega-realm"),
        pytest.param("  root@pam  ", "pam", "root@pam", id="CA-02.4-con-espacios"),
        pytest.param("ana@pve", "pve", "ana@pve", id="CA-02.4-realm-pve"),
    ],
)
def test_ca_02_4_normalizar_usuario(usuario, realm, esperado):
    assert normalizar_usuario(usuario, realm) == esperado


def test_ca_02_4_login_envia_un_solo_realm(reloj):
    t = TransporteFalso()
    t.en("POST", RUTA, lambda c: {"ticket": "PVE:root@pam:AA::s", "CSRFPreventionToken": "AA:c"})
    iniciar_sesion_ticket(t, "root@pam", "pam", "contra", reloj=reloj)
    assert t.llamadas[0].datos["username"] == "root@pam"


def test_ca_02_1_login_devuelve_ticket_completo_en_memoria(reloj, respuesta):
    reloj.avanzar(7)
    ticket = _login(
        TransporteFalso(), respuesta("9.2", "ticket_completo.json")["data"], reloj=reloj
    )
    assert isinstance(ticket, Ticket)
    assert ticket.usuario == "root@pam"
    assert ticket.ticket.startswith("PVE:root@pam:")
    assert ticket.csrf
    assert ticket.emitido_en == 7


def test_ca_02_1_login_usa_usuario_y_contrasena_en_el_cuerpo():
    t = TransporteFalso()
    _login(t, {"ticket": "PVE:root@pam:AA::s", "CSRFPreventionToken": "AA:c"})
    llamada = t.llamadas[0]
    assert (llamada.metodo, llamada.ruta) == ("POST", RUTA)
    assert llamada.datos == {"username": "root@pam", "password": "contra-secreta"}


def test_ca_04_1_sin_2fa_no_hay_desafio(respuesta):
    resultado = _login(TransporteFalso(), respuesta("9.2", "ticket_completo.json")["data"])
    assert not isinstance(resultado, DesafioTFA)


@pytest.mark.parametrize("data", [None, [], "texto"])
def test_login_con_respuesta_que_no_es_objeto_es_desconocido(data):
    with pytest.raises(ErrorProxLaunch) as e:
        _login(TransporteFalso(), data)
    assert e.value.codigo == CodigoError.DESCONOCIDO


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"ticket": "PVE:root@pam:AA::s"}, id="sin-csrf"),
        pytest.param({"CSRFPreventionToken": "AA:c"}, id="sin-ticket"),
        pytest.param({}, id="vacia"),
    ],
)
def test_login_con_respuesta_incompleta_es_desconocido(data):
    with pytest.raises(ErrorProxLaunch) as e:
        _login(TransporteFalso(), data)
    assert e.value.codigo == CodigoError.DESCONOCIDO


# --- RF-03: renovación ------------------------------------------------------------------


def _auth_ticket(reloj: RelojSimulado, emitido=0.0, csrf="AAAA:csrf-viejo"):
    return AutenticadorTicket(Ticket("PVE:root@pam:VIEJO::s", csrf, "root@pam", emitido), reloj)


def test_ca_03_1_limite_exacto_de_105_minutos(reloj):
    auth = _auth_ticket(reloj)
    reloj.avanzar(105 * MIN - 1)
    assert auth.necesita_renovar() is False
    reloj.avanzar(1)
    assert auth.necesita_renovar() is True


def test_ca_03_1_renueva_antes_de_la_peticion_y_usa_el_ticket_nuevo(reloj, respuesta):
    t = TransporteFalso()
    nuevo = respuesta("9.2", "ticket_renovado.json")["data"]
    t.en("POST", RUTA, nuevo)
    t.en("GET", "/version", {"version": "9.2.1"})
    auth = _auth_ticket(reloj)
    cliente = ClienteProxmox(t, auth, reloj)
    reloj.avanzar(105 * MIN)
    cliente.version()
    assert t.metodos == ["POST", "GET"]  # primero la renovación, luego la petición
    renovacion, lectura = t.llamadas
    assert renovacion.datos == {"username": "root@pam", "password": "PVE:root@pam:VIEJO::s"}
    assert lectura.cookies["PVEAuthCookie"] == nuevo["ticket"]


def test_ca_03_1_la_renovacion_actualiza_ticket_y_csrf(reloj, respuesta):
    t = TransporteFalso().en("POST", RUTA, respuesta("9.2", "ticket_renovado.json")["data"])
    auth = _auth_ticket(reloj)
    reloj.avanzar(106 * MIN)
    auth.renovar(t)
    assert auth.ticket.ticket == "PVE:root@pam:6535CC99::cmVub3ZhZG8"
    assert auth.ticket.csrf == "6535CC99:Y3NyZnJlbm92YWRv"
    assert auth.ticket.emitido_en == reloj.ahora()
    assert auth.necesita_renovar() is False
    cab, cook = {}, {}
    auth.aplicar("POST", cab, cook)
    assert cab["CSRFPreventionToken"] == "6535CC99:Y3NyZnJlbm92YWRv"


def test_ca_03_1_renueva_una_sola_vez_en_peticiones_consecutivas(reloj, respuesta):
    t = TransporteFalso()
    t.en("POST", RUTA, respuesta("9.2", "ticket_renovado.json")["data"])
    t.en("GET", "/version", {"version": "9.2.1"})
    cliente = ClienteProxmox(t, _auth_ticket(reloj), reloj)
    reloj.avanzar(110 * MIN)
    cliente.version()
    cliente.version()
    assert t.metodos == ["POST", "GET", "GET"]


def test_ca_03_1_antes_del_margen_no_renueva(reloj):
    t = TransporteFalso().en("GET", "/version", {"version": "9.2.1"})
    cliente = ClienteProxmox(t, _auth_ticket(reloj), reloj)
    reloj.avanzar(60 * MIN)
    cliente.version()
    assert t.metodos == ["GET"]


@pytest.mark.parametrize(
    "codigo", [CodigoError.CREDENCIALES_INVALIDAS, CodigoError.SESION_EXPIRADA]
)
def test_ca_03_3_renovacion_rechazada_es_sesion_expirada(reloj, codigo):
    t = TransporteFalso()
    t.en("POST", RUTA, ErrorProxLaunch(codigo, {}, "401"))
    t.en("GET", "/version", {"version": "9.2.1"})
    cliente = ClienteProxmox(t, _auth_ticket(reloj), reloj)
    reloj.avanzar(119 * MIN)
    with pytest.raises(ErrorProxLaunch) as e:
        cliente.version()
    assert e.value.codigo == CodigoError.SESION_EXPIRADA
    assert t.metodos == ["POST"]  # la petición original no llega a enviarse


def test_ca_03_3_error_de_red_en_la_renovacion_no_se_disfraza(reloj):
    t = TransporteFalso()
    t.en("POST", RUTA, ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "timeout"))
    auth = _auth_ticket(reloj)
    reloj.avanzar(110 * MIN)
    with pytest.raises(ErrorProxLaunch) as e:
        auth.renovar(t)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE


def test_ca_03_3_renovacion_con_ticket_parcial_en_la_respuesta_falla(reloj):
    t = TransporteFalso().en(
        "POST", RUTA, {"ticket": ticket_parcial({"totp": True}), "CSRFPreventionToken": "x:y"}
    )
    auth = _auth_ticket(reloj)
    reloj.avanzar(110 * MIN)
    with pytest.raises(ErrorProxLaunch) as e:
        auth.renovar(t)
    assert e.value.codigo == CodigoError.DESCONOCIDO


# --- RF-04: 2FA -------------------------------------------------------------------------


def test_ca_04_2_desafio_ofrece_totp_y_recovery(respuesta):
    r = _login(TransporteFalso(), respuesta("9.2", "ticket_tfa_totp_recovery.json")["data"])
    assert isinstance(r, DesafioTFA)
    assert r.totp is True
    assert r.recuperacion is True
    assert r.soportado is True
    assert r.usuario == "ana@pve"
    assert r.no_soportados == ()


@pytest.mark.parametrize("version", ["9.2", "8.0"])
def test_ca_04_2_desafio_se_lee_igual_en_8_0_y_9_2(respuesta, version):
    r = _login(TransporteFalso(), respuesta(version, "ticket_tfa_totp_recovery.json")["data"])
    assert (r.totp, r.recuperacion) == (True, True)


def test_ca_04_2_el_desafio_solo_se_ofrece_si_el_servidor_lo_exige(respuesta):
    # NeedTFA y ticket parcial coinciden; sin ellos es un ticket completo (CA-04.1).
    parcial = respuesta("9.2", "ticket_tfa_totp_recovery.json")["data"]
    assert parcial["NeedTFA"] == 1
    assert parcial["ticket"].split(":")[1].startswith("!tfa!")


def test_a_7_solo_recovery_es_soportado(respuesta):
    r = _login(TransporteFalso(), respuesta("9.2", "ticket_tfa_solo_recovery.json")["data"])
    assert (r.totp, r.recuperacion, r.soportado) == (False, True, True)


def test_a_7_recovery_vacio_no_cuenta_como_soportado():
    with pytest.raises(ErrorProxLaunch) as e:
        _login(TransporteFalso(), _data_tfa({"recovery": []}))
    assert e.value.codigo == CodigoError.TFA_NO_SOPORTADO


@pytest.mark.parametrize(
    ("fichero", "tipo"),
    [
        pytest.param("ticket_tfa_solo_webauthn.json", "webauthn", id="CA-04.5-solo-webauthn"),
        pytest.param("ticket_tfa_solo_yubico.json", "yubico", id="CA-04.5-solo-yubico"),
    ],
)
def test_ca_04_5_solo_metodos_no_soportados(respuesta, fichero, tipo):
    t = TransporteFalso()
    with pytest.raises(ErrorProxLaunch) as e:
        _login(t, respuesta("9.2", fichero)["data"])
    assert e.value.codigo == CodigoError.TFA_NO_SOPORTADO
    assert e.value.params["tipos"] == tipo
    assert len(t.llamadas) == 1  # no se pide ningún código


@pytest.mark.parametrize(
    "desafio",
    [
        pytest.param({"webauthn": {"x": 1}, "yubico": True}, id="CA-04.5-webauthn-y-yubico"),
        pytest.param({"u2f": {"x": 1}}, id="CA-04.5-solo-u2f"),
        pytest.param({}, id="CA-04.5-desafio-vacio"),
    ],
)
def test_ca_04_5_otras_combinaciones_no_soportadas(desafio):
    with pytest.raises(ErrorProxLaunch) as e:
        _login(TransporteFalso(), _data_tfa(desafio))
    assert e.value.codigo == CodigoError.TFA_NO_SOPORTADO


def test_ca_04_6_totp_y_webauthn_ofrece_totp(respuesta):
    r = _login(TransporteFalso(), respuesta("9.2", "ticket_tfa_totp_webauthn.json")["data"])
    assert isinstance(r, DesafioTFA)
    assert r.totp is True
    assert r.soportado is True
    assert "webauthn" in r.no_soportados


def test_desafio_ilegible_es_tfa_no_soportado():
    data = {"ticket": "PVE:!tfa!%7Bno-es-json:AA::s", "CSRFPreventionToken": "x", "NeedTFA": 1}
    with pytest.raises(ErrorProxLaunch) as e:
        _login(TransporteFalso(), data)
    assert e.value.codigo == CodigoError.TFA_NO_SOPORTADO


def test_need_tfa_sin_ticket_parcial_legible_es_tfa_no_soportado():
    data = {"ticket": "PVE:ana@pve:AA::s", "CSRFPreventionToken": "x", "NeedTFA": 1}
    with pytest.raises(ErrorProxLaunch) as e:
        _login(TransporteFalso(), data)
    assert e.value.codigo == CodigoError.TFA_NO_SOPORTADO


def test_ca_04_7_el_repr_del_desafio_no_muestra_el_ticket_parcial(respuesta):
    r = _login(TransporteFalso(), respuesta("9.2", "ticket_tfa_totp_recovery.json")["data"])
    assert r.ticket_parcial not in repr(r)
    assert "tfa" not in repr(r).lower().replace("desafiotfa", "")


def _paso2(t: TransporteFalso, desafio, codigo, tipo, reloj=None):
    return responder_tfa(t, desafio, codigo, tipo, reloj=reloj)


def test_ca_04_3_totp_correcto_devuelve_ticket(reloj, respuesta):
    t = TransporteFalso().en("POST", RUTA, respuesta("9.2", "ticket_completo.json")["data"])
    desafio = _desafio()
    ticket = _paso2(t, desafio, "123456", TipoTFA.TOTP, reloj)
    assert isinstance(ticket, Ticket)
    datos = t.llamadas[0].datos
    assert datos == {
        "username": "ana@pve",
        "tfa-challenge": desafio.ticket_parcial,
        "password": "totp:123456",
    }


def test_ca_04_3_codigo_rechazado_es_tfa_codigo_incorrecto_y_se_puede_reintentar(reloj, respuesta):
    t = TransporteFalso()
    t.en(
        "POST",
        RUTA,
        Secuencia(
            ErrorProxLaunch(CodigoError.CREDENCIALES_INVALIDAS, {}, "401"),
            respuesta("9.2", "ticket_completo.json")["data"],
        ),
    )
    desafio = _desafio()
    with pytest.raises(ErrorProxLaunch) as e:
        _paso2(t, desafio, "000000", TipoTFA.TOTP, reloj)
    assert e.value.codigo == CodigoError.TFA_CODIGO_INCORRECTO
    # Mismo desafío, sin volver a escribir usuario y contraseña.
    assert isinstance(_paso2(t, desafio, "123456", TipoTFA.TOTP, reloj), Ticket)


def test_otro_error_en_el_paso_2_no_se_disfraza_de_codigo_incorrecto():
    t = TransporteFalso().en(
        "POST", RUTA, ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "timeout")
    )
    with pytest.raises(ErrorProxLaunch) as e:
        _paso2(t, _desafio(), "123456", TipoTFA.TOTP)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE


@pytest.mark.parametrize(
    ("ingresado", "enviado"),
    [
        pytest.param("ABCD-EF01-2345-6789", "recovery:abcd-ef01-2345-6789", id="A-7-minusculas"),
        pytest.param("  abcd-ef01-2345-6789 \n", "recovery:abcd-ef01-2345-6789", id="A-7-recorta"),
        pytest.param("ABCD EF01 2345 6789", "recovery:abcdef0123456789", id="A-7-sin-espacios"),
    ],
)
def test_a_7_clave_de_recuperacion_se_normaliza(respuesta, ingresado, enviado):
    t = TransporteFalso().en("POST", RUTA, respuesta("9.2", "ticket_completo.json")["data"])
    _paso2(t, _desafio(), ingresado, TipoTFA.RECUPERACION)
    assert t.llamadas[0].datos["password"] == enviado


def test_a_7_totp_se_envia_sin_espacios(respuesta):
    t = TransporteFalso().en("POST", RUTA, respuesta("9.2", "ticket_completo.json")["data"])
    _paso2(t, _desafio(), " 123 456 ", TipoTFA.TOTP)
    assert t.llamadas[0].datos["password"] == "totp:123456"


@pytest.mark.parametrize(
    ("desafio", "tipo"),
    [
        pytest.param(
            _desafio(totp=True, recuperacion=False), TipoTFA.RECUPERACION, id="sin-recovery"
        ),
        pytest.param(_desafio(totp=False, recuperacion=True), TipoTFA.TOTP, id="sin-totp"),
    ],
)
def test_responder_con_un_tipo_no_ofrecido_no_envia_nada(desafio, tipo):
    t = TransporteFalso()
    with pytest.raises(ErrorProxLaunch) as e:
        _paso2(t, desafio, "123456", tipo)
    assert e.value.codigo == CodigoError.TFA_NO_SOPORTADO
    assert t.llamadas == []


def test_el_paso_2_no_acepta_un_ticket_parcial_como_respuesta():
    t = TransporteFalso().en(
        "POST", RUTA, {"ticket": ticket_parcial({"totp": True}), "CSRFPreventionToken": "x:y"}
    )
    with pytest.raises(ErrorProxLaunch) as e:
        _paso2(t, _desafio(), "123456", TipoTFA.TOTP)
    assert e.value.codigo == CodigoError.DESCONOCIDO
