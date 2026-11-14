"""ServicioConexion: huella, token, ticket, 2FA, versión, llavero y permisos
(RF-01 a RF-09, RF-12, A-6, A-7). Mezcla transporte falso y HTTP simulado con ``responses``."""

import json
import logging
from urllib.parse import parse_qs

import keyring.backends.null
import pytest
import requests
import responses

from proxlaunch.nucleo.api.autenticacion import DesafioTFA, TipoTFA
from proxlaunch.nucleo.api.transporte import crear_transporte_http
from proxlaunch.nucleo.capacidades import Funcion
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialContrasena, CredencialToken
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.servicios.conexion import (
    PRIVILEGIOS_REQUERIDOS,
    CodigoAviso,
    EstadoHuella,
    ServicioConexion,
    permisos_faltantes,
)

from .apoyo_api import (
    HUELLA_A,
    HUELLA_B,
    TOKEN_ID,
    TOKEN_SECRETO,
    TransporteFalso,
    agregar_error,
    cargar,
    crear_sesion,
    dato,
    perfil_basico,
    url,
)

A = "10.0.0.1"
B = "10.0.0.2"
TOKEN = CredencialToken(TOKEN_ID, TOKEN_SECRETO)
CONTRASENA = CredencialContrasena("root", "pam", "contra-secreta")


class LlaveroFalso:
    """Backend de keyring en memoria."""

    def __init__(self):
        self.almacen = {}
        self.llamadas = []

    def set_password(self, servicio, clave, valor):
        self.llamadas.append("set")
        self.almacen[(servicio, clave)] = valor

    def get_password(self, servicio, clave):
        return self.almacen.get((servicio, clave))

    def delete_password(self, servicio, clave):
        self.llamadas.append("delete")
        self.almacen.pop((servicio, clave), None)


class LlaveroRoto(LlaveroFalso):
    def set_password(self, servicio, clave, valor):
        raise RuntimeError("el llavero está bloqueado")


@pytest.fixture
def huellas(tmp_path):
    return RepositorioHuellas(tmp_path / "huellas.json")


@pytest.fixture
def llavero():
    return LlaveroFalso()


@pytest.fixture
def hacer_servicio(huellas, llavero, reloj):
    """Servicio con fábrica de transporte HTTP real (la red la simula ``responses``)."""

    def _hacer(observadas=None, fabrica=None, almacen=None):
        observadas = observadas if observadas is not None else {}

        def obtener(host, puerto, timeout):
            valor = observadas.get(host)
            if isinstance(valor, ErrorProxLaunch):
                raise valor
            if valor is None:
                raise ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": host}, "caído")
            return valor

        return ServicioConexion(
            fabrica or crear_transporte_http,
            huellas,
            almacen if almacen is not None else AlmacenSecretos(backend=llavero),
            reloj,
            obtener_huella_fn=obtener,
        )

    return _hacer


def _confiar(huellas, *hosts, huella=HUELLA_A):
    for h in hosts:
        huellas.guardar(h, 8006, huella)


def _registrar_api_basica(rsps, host=A, ver="9.2", version=None):
    cuerpo = cargar(ver, "version.json")
    if version is not None:
        cuerpo = {"data": {"version": version}}
    rsps.get(url(host, "/version"), json=cuerpo)


# --- RF-05: huella ----------------------------------------------------------------------


def test_ca_05_1_huella_nueva_se_detecta_sin_ninguna_peticion_http(hacer_servicio, rsps):
    s = hacer_servicio({A: HUELLA_A})
    (info,) = s.consultar_huellas(perfil_basico())
    assert info.estado == EstadoHuella.NUEVA
    assert info.huella_observada == HUELLA_A
    assert info.huella_guardada is None
    assert (info.host, info.puerto) == (A, 8006)
    assert len(rsps.calls) == 0


def test_ca_05_1_no_se_envia_ninguna_credencial_antes_de_confiar(hacer_servicio, rsps):
    rsps.post(url(A, "/access/ticket"), json=cargar("9.2", "ticket_completo.json"))
    rsps.get(url(A, "/version"), json=cargar("9.2", "version.json"))
    s = hacer_servicio({A: HUELLA_A})
    perfil = perfil_basico()
    for credencial in (TOKEN, CONTRASENA):
        with pytest.raises(ErrorProxLaunch) as e:
            s.conectar(perfil, credencial)
        assert e.value.codigo == CodigoError.HUELLA_NO_CONFIADA
    assert len(rsps.calls) == 0  # ni token ni contraseña salieron


def test_ca_05_1_sin_huella_ni_siquiera_se_crea_el_transporte(hacer_servicio):
    creados = []
    s = hacer_servicio({A: HUELLA_A}, fabrica=lambda p, h: creados.append(1))
    with pytest.raises(ErrorProxLaunch):
        s.conectar(perfil_basico(), TOKEN)
    assert creados == []


def test_ca_05_2_confiar_guarda_la_huella_y_la_siguiente_conexion_no_pregunta(
    hacer_servicio, huellas, tmp_path
):
    s = hacer_servicio({A: HUELLA_A})
    perfil = perfil_basico()
    assert s.preparar(perfil) == EstadoHuella.NUEVA
    s.confiar_huella(perfil, A, HUELLA_A)
    assert RepositorioHuellas(tmp_path / "huellas.json").obtener(A, 8006) == HUELLA_A
    assert s.preparar(perfil) == EstadoHuella.CONFIRMADA


def test_ca_05_3_cancelar_no_guarda_nada(hacer_servicio, huellas):
    s = hacer_servicio({A: HUELLA_A})
    s.preparar(perfil_basico())  # el usuario ve el diálogo y cancela: no se llama a confiar
    assert huellas.obtener(A, 8006) is None


def test_ca_05_4_huella_cambiada_se_detecta_con_ambas_huellas(hacer_servicio, huellas, rsps):
    _confiar(huellas, A, huella=HUELLA_A)
    s = hacer_servicio({A: HUELLA_B})
    (info,) = s.consultar_huellas(perfil_basico())
    assert info.estado == EstadoHuella.CAMBIADA
    assert info.huella_guardada == HUELLA_A
    assert info.huella_observada == HUELLA_B
    assert s.preparar(perfil_basico()) == EstadoHuella.CAMBIADA
    assert len(rsps.calls) == 0


def test_ca_05_4_conectar_con_huella_cambiada_no_pasa_a_otro_host(hacer_servicio, huellas, rsps):
    _confiar(huellas, A, B)
    rsps.post(
        url(A, "/access/ticket"),
        body=requests.exceptions.SSLError("Fingerprints did not match. Expected aa, got bb"),
    )
    rsps.post(url(B, "/access/ticket"), json=cargar("9.2", "ticket_completo.json"))
    s = hacer_servicio()
    with pytest.raises(ErrorProxLaunch) as e:
        s.conectar(perfil_basico(hosts=[A, B]), CONTRASENA)
    assert e.value.codigo == CodigoError.HUELLA_CAMBIADA
    assert all(B not in c.request.url for c in rsps.calls)


def test_ca_05_5_confiar_otra_huella_distinta_exige_reemplazar(hacer_servicio, huellas):
    _confiar(huellas, A, huella=HUELLA_A)
    s = hacer_servicio()
    with pytest.raises(ErrorProxLaunch) as e:
        s.confiar_huella(perfil_basico(), A, HUELLA_B)
    assert e.value.codigo == CodigoError.HUELLA_CAMBIADA
    assert huellas.obtener(A, 8006) == HUELLA_A
    s.reemplazar_huella(perfil_basico(), A, HUELLA_B)
    assert huellas.obtener(A, 8006) == HUELLA_B


def test_huella_confirmada_se_compara_sin_distinguir_mayusculas(hacer_servicio, huellas):
    _confiar(huellas, A, huella=HUELLA_A.lower())
    s = hacer_servicio({A: HUELLA_A})
    assert s.preparar(perfil_basico()) == EstadoHuella.CONFIRMADA


def test_preparar_devuelve_el_peor_estado_de_los_hosts(hacer_servicio, huellas):
    _confiar(huellas, A, huella=HUELLA_A)
    s = hacer_servicio({A: HUELLA_A, B: HUELLA_B})
    assert s.preparar(perfil_basico(hosts=[A, B])) == EstadoHuella.NUEVA
    _confiar(huellas, B, huella=HUELLA_A)
    assert s.preparar(perfil_basico(hosts=[A, B])) == EstadoHuella.CAMBIADA


def test_consultar_huellas_omite_los_hosts_caidos(hacer_servicio):
    s = hacer_servicio({A: None, B: HUELLA_B})
    infos = s.consultar_huellas(perfil_basico(hosts=[A, B]))
    assert [i.host for i in infos] == [B]


def test_consultar_huellas_con_todos_caidos_informa_cada_motivo(hacer_servicio):
    s = hacer_servicio({})
    with pytest.raises(ErrorProxLaunch) as e:
        s.consultar_huellas(perfil_basico(hosts=[A, B]))
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert A in e.value.params["motivos"]
    assert B in e.value.params["motivos"]


def test_consultar_huellas_usa_el_timeout_de_conexion(huellas, llavero, reloj):
    tiempos = []

    def obtener(host, puerto, timeout):
        tiempos.append(timeout)
        return HUELLA_A

    ServicioConexion(
        crear_transporte_http, huellas, AlmacenSecretos(backend=llavero), reloj, obtener
    ).consultar_huellas(perfil_basico())
    assert tiempos == [10]


# --- RF-06: ignorar SSL -----------------------------------------------------------------


def test_ca_06_2_ignorar_ssl_no_consulta_ni_guarda_huella(hacer_servicio, huellas):
    llamadas = []
    s = hacer_servicio(fabrica=lambda p, h: llamadas.append(dict(h)) or TransporteFalso())
    perfil = perfil_basico(ignorar_ssl=True)
    (info,) = s.consultar_huellas(perfil)
    assert info.estado == EstadoHuella.IGNORADA
    assert info.huella_observada is None
    assert s.preparar(perfil) == EstadoHuella.IGNORADA
    assert huellas.obtener(A, 8006) is None


def test_ca_06_2_ignorar_ssl_conecta_sin_huella_confiada(hacer_servicio, huellas, rsps):
    _registrar_api_basica(rsps)
    s = hacer_servicio()
    sesion = s.conectar(perfil_basico(ignorar_ssl=True), TOKEN)
    assert sesion.version.mayor == 9
    assert huellas.obtener(A, 8006) is None


# --- RF-01: token -----------------------------------------------------------------------


def test_ca_01_1_conecta_con_token_y_expone_la_version(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    _registrar_api_basica(rsps)
    sesion = hacer_servicio().conectar(perfil_basico(), TOKEN)
    assert sesion.version.texto == "9.2.1"
    assert sesion.usuario_efectivo == TOKEN_ID
    assert sesion.host_activo == A
    assert rsps.calls[0].request.headers["Authorization"] == (
        f"PVEAPIToken={TOKEN_ID}={TOKEN_SECRETO}"
    )
    assert sesion.avisos == []


def test_ca_01_3_token_rechazado_es_credenciales_invalidas(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    agregar_error(rsps, "GET", url(A, "/version"), 401, "No ticket")
    with pytest.raises(ErrorProxLaunch) as e:
        hacer_servicio().conectar(perfil_basico(), TOKEN)
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS


def test_ca_01_4_el_token_no_pasa_por_ticket_ni_2fa(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    _registrar_api_basica(rsps)
    s = hacer_servicio()
    for _ in range(2):  # conectar, cerrar y volver a conectar
        assert not isinstance(s.conectar(perfil_basico(), TOKEN), DesafioTFA)
    assert all("/access/ticket" not in c.request.url for c in rsps.calls)


def test_ca_01_5_host_sin_respuesta_es_servidor_no_responde(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    rsps.get(url(A, "/version"), body=requests.exceptions.ConnectTimeout())
    with pytest.raises(ErrorProxLaunch) as e:
        hacer_servicio().conectar(perfil_basico(), TOKEN)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert e.value.params["host"] == A


# --- RF-02: ticket ----------------------------------------------------------------------


def test_ca_02_1_ticket_se_usa_como_cookie_en_version(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    rsps.post(url(A, "/access/ticket"), json=cargar("9.2", "ticket_completo.json"))
    _registrar_api_basica(rsps)
    sesion = hacer_servicio().conectar(perfil_basico(), CONTRASENA)
    assert sesion.usuario_efectivo == "root@pam"
    version = rsps.calls[1].request
    assert "PVEAuthCookie=" in version.headers["Cookie"]
    assert "CSRFPreventionToken" not in version.headers  # GET


def test_ca_02_2_contrasena_incorrecta_es_credenciales_invalidas(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    agregar_error(rsps, "POST", url(A, "/access/ticket"), 401, "authentication failure")
    with pytest.raises(ErrorProxLaunch) as e:
        hacer_servicio().conectar(perfil_basico(), CONTRASENA)
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS


def test_ca_02_4_el_login_envia_root_at_pam_una_sola_vez(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    rsps.post(url(A, "/access/ticket"), json=cargar("9.2", "ticket_completo.json"))
    _registrar_api_basica(rsps)
    hacer_servicio().conectar(perfil_basico(), CredencialContrasena("root@pam", "pam", "x"))
    campos = parse_qs(rsps.calls[0].request.body)
    assert campos["username"] == ["root@pam"]


# --- RF-04: 2FA a través del servicio ---------------------------------------------------


def _registrar_login_con_2fa(rsps, aceptados, host=A, desafio="ticket_tfa_totp_recovery.json"):
    """Paso 1 devuelve el desafío; el paso 2 acepta solo los ``password`` de ``aceptados``."""
    contador = {"intentos": 0}

    def _cb(request):
        campos = {k: v[0] for k, v in parse_qs(request.body).items()}
        if "tfa-challenge" not in campos:
            return (200, {}, json.dumps(cargar("9.2", desafio)))
        contador["intentos"] += 1
        if campos["password"] in aceptados:
            return (200, {}, json.dumps(cargar("9.2", "ticket_completo.json")))
        return (401, {}, json.dumps({"data": None}))

    rsps.add_callback(responses.POST, url(host, "/access/ticket"), callback=_cb)
    return contador


def test_ca_04_1_usuario_sin_2fa_conecta_sin_desafio(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    rsps.post(url(A, "/access/ticket"), json=cargar("9.2", "ticket_completo.json"))
    _registrar_api_basica(rsps)
    assert not isinstance(hacer_servicio().conectar(perfil_basico(), CONTRASENA), DesafioTFA)


def test_ca_04_2_con_2fa_conectar_devuelve_el_desafio_y_no_toca_version(
    hacer_servicio, huellas, rsps
):
    _confiar(huellas, A)
    _registrar_login_con_2fa(rsps, {"totp:123456"})
    resultado = hacer_servicio().conectar(perfil_basico(), CONTRASENA)
    assert isinstance(resultado, DesafioTFA)
    assert (resultado.totp, resultado.recuperacion) == (True, True)
    assert all("/version" not in c.request.url for c in rsps.calls)


def test_ca_04_3_totp_correcto_completa_la_sesion(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    _registrar_login_con_2fa(rsps, {"totp:123456"})
    _registrar_api_basica(rsps)
    s = hacer_servicio()
    desafio = s.conectar(perfil_basico(), CONTRASENA)
    sesion = s.completar_tfa(desafio, "123456", TipoTFA.TOTP)
    assert sesion.version.mayor == 9
    assert sesion.usuario_efectivo == "root@pam"


def test_ca_04_3_codigo_incorrecto_permite_reintentar_con_el_mismo_desafio(
    hacer_servicio, huellas, rsps
):
    _confiar(huellas, A)
    _registrar_login_con_2fa(rsps, {"totp:123456"})
    _registrar_api_basica(rsps)
    s = hacer_servicio()
    desafio = s.conectar(perfil_basico(), CONTRASENA)
    for _ in range(2):
        with pytest.raises(ErrorProxLaunch) as e:
            s.completar_tfa(desafio, "000000", TipoTFA.TOTP)
        assert e.value.codigo == CodigoError.TFA_CODIGO_INCORRECTO
    assert s.completar_tfa(desafio, "123456", TipoTFA.TOTP).version.mayor == 9


def test_ca_04_4_clave_de_recuperacion_normalizada(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    _registrar_login_con_2fa(rsps, {"recovery:abcd-ef01-2345-6789"})
    _registrar_api_basica(rsps)
    s = hacer_servicio()
    desafio = s.conectar(perfil_basico(), CONTRASENA)
    sesion = s.completar_tfa(desafio, " ABCD-EF01-2345-6789 ", TipoTFA.RECUPERACION)
    assert sesion.usuario_efectivo == "root@pam"


def test_ca_04_5_solo_webauthn_falla_sin_pedir_codigo(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    _registrar_login_con_2fa(rsps, set(), desafio="ticket_tfa_solo_webauthn.json")
    s = hacer_servicio()
    with pytest.raises(ErrorProxLaunch) as e:
        s.conectar(perfil_basico(), CONTRASENA)
    assert e.value.codigo == CodigoError.TFA_NO_SOPORTADO


def test_ca_04_6_totp_y_webauthn_ofrece_totp(hacer_servicio, huellas, rsps):
    _confiar(huellas, A)
    _registrar_login_con_2fa(rsps, {"totp:123456"}, desafio="ticket_tfa_totp_webauthn.json")
    _registrar_api_basica(rsps)
    s = hacer_servicio()
    desafio = s.conectar(perfil_basico(), CONTRASENA)
    assert isinstance(desafio, DesafioTFA)
    assert desafio.totp is True
    assert s.completar_tfa(desafio, "123456", TipoTFA.TOTP).version.mayor == 9


def test_completar_tfa_sin_desafio_pendiente_es_sesion_expirada(hacer_servicio):
    desafio = DesafioTFA("ana@pve", "PVE:!tfa!x", True, False)
    with pytest.raises(ErrorProxLaunch) as e:
        hacer_servicio().completar_tfa(desafio, "123456", TipoTFA.TOTP)
    assert e.value.codigo == CodigoError.SESION_EXPIRADA


def test_error_de_red_en_el_paso_2_se_propaga_como_servidor_no_responde(
    hacer_servicio, huellas, rsps
):
    _confiar(huellas, A)
    pasos = {"n": 0}

    def _cb(request):
        pasos["n"] += 1
        if pasos["n"] == 1:
            return (200, {}, json.dumps(cargar("9.2", "ticket_tfa_totp_recovery.json")))
        raise requests.exceptions.ConnectTimeout()

    rsps.add_callback(responses.POST, url(A, "/access/ticket"), callback=_cb)
    s = hacer_servicio()
    desafio = s.conectar(perfil_basico(), CONTRASENA)
    with pytest.raises(ErrorProxLaunch) as e:
        s.completar_tfa(desafio, "123456", TipoTFA.TOTP)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE


# --- RF-07: failover a través del servicio ----------------------------------------------


def test_ca_07_2_cae_a_y_conecta_a_b(hacer_servicio, huellas, rsps):
    _confiar(huellas, A, B)
    rsps.get(url(A, "/version"), body=requests.exceptions.ConnectTimeout())
    _registrar_api_basica(rsps, host=B)
    sesion = hacer_servicio().conectar(perfil_basico(hosts=[A, B]), TOKEN)
    assert sesion.host_activo == B


def test_ca_07_3_a_responde_401_no_prueba_b(hacer_servicio, huellas, rsps):
    _confiar(huellas, A, B)
    agregar_error(rsps, "GET", url(A, "/version"), 401, "No ticket")
    _registrar_api_basica(rsps, host=B)
    with pytest.raises(ErrorProxLaunch) as e:
        hacer_servicio().conectar(perfil_basico(hosts=[A, B]), TOKEN)
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS
    assert all(B not in c.request.url for c in rsps.calls)


def test_ca_07_4_todos_caen_lista_el_motivo_por_ip(hacer_servicio, huellas, rsps):
    _confiar(huellas, A, B)
    rsps.get(url(A, "/version"), body=requests.exceptions.ConnectTimeout())
    rsps.get(url(B, "/version"), body=requests.exceptions.ConnectionError())
    with pytest.raises(ErrorProxLaunch) as e:
        hacer_servicio().conectar(perfil_basico(hosts=[A, B]), TOKEN)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert "timeout" in e.value.params["motivos"]
    assert "conexion" in e.value.params["motivos"]


def test_la_fabrica_recibe_solo_las_huellas_de_los_hosts_confiados(hacer_servicio, huellas):
    _confiar(huellas, B)
    recibidas = []

    def fabrica(perfil, h):
        recibidas.append(dict(h))
        return TransporteFalso().en("GET", "/version", {"version": "9.2.1"})

    hacer_servicio(fabrica=fabrica).conectar(perfil_basico(hosts=[A, B]), TOKEN)
    assert recibidas == [{B: HUELLA_A}]


# --- RF-09: versión ---------------------------------------------------------------------


def _conectar_con_version(hacer_servicio, huellas, version, **kw):
    _confiar(huellas, A)
    t = TransporteFalso().en("GET", "/version", {"version": version})
    s = hacer_servicio(fabrica=lambda p, h: t)
    return s.conectar(perfil_basico(**kw), TOKEN)


@pytest.mark.parametrize(
    ("texto", "mayor", "menor"),
    [
        pytest.param("8.2.4", 8, 2, id="CA-09.1-8.2.4"),
        pytest.param("8.0.4", 8, 0, id="8.0.4"),
        pytest.param("9.2.1", 9, 2, id="9.2.1"),
    ],
)
def test_ca_09_1_versiones_soportadas(hacer_servicio, huellas, texto, mayor, menor):
    sesion = _conectar_con_version(hacer_servicio, huellas, texto)
    assert (sesion.version.mayor, sesion.version.menor) == (mayor, menor)
    assert sesion.capacidades.es_soportada()
    assert sesion.capacidades.forzada is False


def test_ca_09_2_version_7_se_bloquea(hacer_servicio, huellas):
    with pytest.raises(ErrorProxLaunch) as e:
        _conectar_con_version(hacer_servicio, huellas, "7.4-17")
    assert e.value.codigo == CodigoError.VERSION_NO_SOPORTADA
    assert e.value.params == {"version": "7.4-17", "minima": "8.0"}


def test_ca_09_3_version_mayor_que_la_conocida_se_permite(hacer_servicio, huellas):
    sesion = _conectar_con_version(hacer_servicio, huellas, "10.0")
    assert (sesion.version.mayor, sesion.version.menor) == (10, 0)
    assert sesion.capacidades.es_soportada()
    assert sesion.capacidades.tiene(Funcion.IMPORTAR_DISCO)


@pytest.mark.parametrize("texto", ["texto raro", "", "v?"])
def test_ca_09_5_formato_inesperado_conecta_con_la_capacidad_minima(
    hacer_servicio, huellas, registros, texto
):
    sesion = _conectar_con_version(hacer_servicio, huellas, texto)
    assert sesion.capacidades.version == (8, 0)
    assert not sesion.capacidades.tiene(Funcion.IMPORTAR_DISCO)
    assert any(r.levelno == logging.WARNING for r in registros)


def test_ca_09_4_funcion_desde_8_4_no_esta_en_8_0(hacer_servicio, huellas):
    # Enmienda 14.6 del MVP 4: IMPORTAR_DISCO requiere (8, 4), no (8, 2).
    sesion = _conectar_con_version(hacer_servicio, huellas, "8.0.4")
    assert not sesion.capacidades.tiene(Funcion.IMPORTAR_DISCO)
    assert sesion.capacidades.requisito(Funcion.IMPORTAR_DISCO) == (8, 4)


def test_rf_26_version_forzada(hacer_servicio, huellas):
    _confiar(huellas, A)
    t = TransporteFalso().en("GET", "/version", {"version": "8.0.4"})
    sesion = hacer_servicio(fabrica=lambda p, h: t).conectar(
        perfil_basico(), TOKEN, version_forzada=(8, 4)
    )
    assert sesion.capacidades.forzada is True
    assert sesion.capacidades.tiene(Funcion.IMPORTAR_DISCO)  # enmienda 14.6: desde (8, 4)


# --- RF-08: llavero ---------------------------------------------------------------------


def test_ca_08_2_casilla_desmarcada_no_toca_el_llavero(hacer_servicio, huellas, llavero):
    sesion = _conectar_con_version(hacer_servicio, huellas, "9.2.1", recordar_credenciales=False)
    assert sesion.avisos == []
    assert llavero.llamadas == []
    assert llavero.almacen == {}


def test_ca_08_3_casilla_marcada_y_exito_guarda_el_token_completo(hacer_servicio, huellas, llavero):
    _conectar_con_version(hacer_servicio, huellas, "9.2.1", recordar_credenciales=True)
    assert llavero.almacen == {("ProxLaunch", "perfil:perfil-1"): f"{TOKEN_ID}={TOKEN_SECRETO}"}


def test_ca_08_3_con_contrasena_guarda_la_contrasena(hacer_servicio, huellas, llavero, rsps):
    _confiar(huellas, A)
    rsps.post(url(A, "/access/ticket"), json=cargar("9.2", "ticket_completo.json"))
    _registrar_api_basica(rsps)
    hacer_servicio().conectar(perfil_basico(recordar_credenciales=True), CONTRASENA)
    assert list(llavero.almacen.values()) == ["contra-secreta"]


def test_ca_08_3_con_2fa_se_guarda_solo_tras_completar(hacer_servicio, huellas, llavero, rsps):
    _confiar(huellas, A)
    _registrar_login_con_2fa(rsps, {"totp:123456"})
    _registrar_api_basica(rsps)
    s = hacer_servicio()
    desafio = s.conectar(perfil_basico(recordar_credenciales=True), CONTRASENA)
    assert llavero.almacen == {}
    with pytest.raises(ErrorProxLaunch):
        s.completar_tfa(desafio, "000000", TipoTFA.TOTP)
    assert llavero.almacen == {}
    s.completar_tfa(desafio, "123456", TipoTFA.TOTP)
    assert list(llavero.almacen.values()) == ["contra-secreta"]


def test_ca_08_3_el_totp_y_la_clave_de_recuperacion_nunca_se_guardan(
    hacer_servicio, huellas, llavero, rsps
):
    _confiar(huellas, A)
    _registrar_login_con_2fa(rsps, {"totp:123456"})
    _registrar_api_basica(rsps)
    s = hacer_servicio()
    desafio = s.conectar(perfil_basico(recordar_credenciales=True), CONTRASENA)
    s.completar_tfa(desafio, "123456", TipoTFA.TOTP)
    assert "123456" not in " ".join(llavero.almacen.values())


def test_ca_08_3_si_la_conexion_falla_no_se_guarda_nada(hacer_servicio, huellas, llavero, rsps):
    _confiar(huellas, A)
    agregar_error(rsps, "GET", url(A, "/version"), 401, "No ticket")
    with pytest.raises(ErrorProxLaunch):
        hacer_servicio().conectar(perfil_basico(recordar_credenciales=True), TOKEN)
    assert llavero.almacen == {}


def test_ca_08_3_si_la_version_no_es_soportada_no_se_guarda_nada(hacer_servicio, huellas, llavero):
    with pytest.raises(ErrorProxLaunch):
        _conectar_con_version(hacer_servicio, huellas, "7.4-17", recordar_credenciales=True)
    assert llavero.almacen == {}


@pytest.mark.parametrize(
    "backend",
    [
        pytest.param(keyring.backends.null.Keyring(), id="CA-08.4-backend-nulo"),
        pytest.param(LlaveroRoto(), id="CA-08.4-el-llavero-falla"),
    ],
)
def test_ca_08_4_sin_llavero_hay_aviso_y_la_conexion_continua(
    hacer_servicio, huellas, tmp_path, backend
):
    _confiar(huellas, A)
    t = TransporteFalso().en("GET", "/version", {"version": "9.2.1"})
    s = hacer_servicio(fabrica=lambda p, h: t, almacen=AlmacenSecretos(backend=backend))
    sesion = s.conectar(perfil_basico(recordar_credenciales=True), TOKEN)
    assert [a.codigo for a in sesion.avisos] == [CodigoAviso.LLAVERO_NO_DISPONIBLE]
    assert sesion.version.mayor == 9
    # Nada de secretos en ningún archivo (solo existe el de huellas).
    for archivo in tmp_path.rglob("*"):
        if archivo.is_file():
            assert TOKEN_SECRETO not in archivo.read_text(encoding="utf-8")


def test_otro_error_del_llavero_no_se_silencia(hacer_servicio, huellas):
    class Alm:
        def guardar(self, perfil_id, secreto):
            raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "otro")

    _confiar(huellas, A)
    t = TransporteFalso().en("GET", "/version", {"version": "9.2.1"})
    s = hacer_servicio(fabrica=lambda p, h: t, almacen=Alm())
    with pytest.raises(ErrorProxLaunch) as e:
        s.conectar(perfil_basico(recordar_credenciales=True), TOKEN)
    assert e.value.codigo == CodigoError.DESCONOCIDO


# --- RF-12: permisos --------------------------------------------------------------------


def _sesion_con_permisos(permisos):
    t = TransporteFalso().en("GET", "/access/permissions", permisos)
    return crear_sesion(t)


def test_ca_12_2_permisos_completos_no_generan_aviso():
    sesion = _sesion_con_permisos(dato("9.2", "permisos_completos.json"))
    assert permisos_faltantes(sesion) == []
    assert sesion.avisos == []


def test_ca_12_1_falta_vm_allocate_avisa_sin_bloquear():
    sesion = _sesion_con_permisos(
        {"/": {p: 1 for p in PRIVILEGIOS_REQUERIDOS if p != "VM.Allocate"}}
    )
    assert permisos_faltantes(sesion) == ["VM.Allocate"]
    (aviso,) = sesion.avisos
    assert aviso.codigo == CodigoAviso.PERMISOS_INCOMPLETOS
    assert aviso.params == {"privilegios": "VM.Allocate", "rutas": "VM.Allocate@/vms"}


def test_rf_12_varios_privilegios_faltantes_se_listan_todos():
    sesion = _sesion_con_permisos({"/": {"VM.Audit": 1}})
    faltan = permisos_faltantes(sesion)
    assert "VM.Allocate" in faltan
    assert "SDN.Use" in faltan
    assert "VM.Audit" not in faltan
    assert sesion.avisos[0].params["privilegios"] == ",".join(faltan)


def test_ca_12_1_solo_falta_vm_allocate_cuando_el_resto_esta_repartido_por_rutas():
    sesion = _sesion_con_permisos(dato("9.2", "permisos_sin_vm_allocate.json"))
    faltan = permisos_faltantes(sesion)
    assert faltan == ["VM.Allocate"]


def test_ca_12_3_si_la_consulta_falla_se_omite_la_verificacion():
    t = TransporteFalso().en(
        "GET", "/access/permissions", ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    )
    sesion = crear_sesion(t)
    assert permisos_faltantes(sesion) is None
    assert sesion.avisos == []


def test_los_privilegios_requeridos_son_exactamente_el_rol_minimo_de_10():
    # Medido en el laboratorio (PVE 9.2): VM.Config.Disk y Datastore.Audit no se exigen.
    rol = {
        "VM.Allocate", "VM.Audit", "VM.Config.Options", "VM.Config.HWType", "VM.Config.CPU",
        "VM.Config.Memory", "VM.Config.Network", "Datastore.AllocateSpace",
        "SDN.Use", "Sys.Audit",
    }  # fmt: skip
    assert set(PRIVILEGIOS_REQUERIDOS) == rol
    assert len(PRIVILEGIOS_REQUERIDOS) == 10
