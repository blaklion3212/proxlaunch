"""RNF-06 / CA-08.5 / CA-04.7: ningún secreto en logs, errores, repr, archivos ni salida.

Se recorren los flujos de la capa API y de los servicios con valores centinela únicos
(token, contraseña, ticket, CSRF, TOTP, clave de recuperación) y se busca cada uno en todo
lo que el programa emite hacia fuera."""

import json
import logging
import threading
from urllib.parse import parse_qs

import pytest
import requests
import responses

from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket, DesafioTFA, TipoTFA
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.transporte import crear_transporte_http
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialContrasena, CredencialToken, Ticket
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.registro import configurar_registro
from proxlaunch.nucleo.servicios.conexion import ServicioConexion
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_api import (
    HUELLA_A,
    RUTA_CONFIG,
    RUTA_CREAR,
    RUTA_ESTADO,
    UPID,
    TransporteFalso,
    agregar_error,
    cargar,
    dato,
    perfil_basico,
    ticket_parcial,
    url,
)

A = "10.0.0.1"
SECRETO_TOKEN = "SENTINELA-token-9f3a1c"
CONTRASENA = "SENTINELA-clave-77b2"
TICKET = "PVE:root@pam:SENTINELATICKET::c2lnU0VOVElORUw"
CSRF = "SENTINELACSRF:Y3NyZlNFTlRJTkVMQQ"
TICKET_RENOVADO = "PVE:root@pam:SENTINELARENOV::cmVub3Y"
CSRF_RENOVADO = "SENTINELARENOV:Y3NyZnJlbm92"
TOTP = "918273"
RECOVERY = "dead-beef-cafe-f00d"
TODOS = {
    "token": SECRETO_TOKEN,
    "contraseña": CONTRASENA,
    "ticket": TICKET,
    "csrf": CSRF,
    "ticket renovado": TICKET_RENOVADO,
    "csrf renovado": CSRF_RENOVADO,
    "totp": TOTP,
    "recovery": RECOVERY,
}


class _LlaveroNulo:
    def set_password(self, *a):
        return None

    def get_password(self, *a):
        return None

    def delete_password(self, *a):
        return None


def _ticket_json(ticket=TICKET, csrf=CSRF):
    return {"data": {"ticket": ticket, "CSRFPreventionToken": csrf, "username": "root@pam"}}


def _cb_login(request):
    """Servidor simulado de /access/ticket con 2FA, renovación y rechazos que repiten secretos."""
    campos = {k: v[0] for k, v in parse_qs(request.body).items()}
    if campos.get("password", "").startswith("PVE:"):  # renovación con el ticket como contraseña
        return (200, {}, json.dumps(_ticket_json(TICKET_RENOVADO, CSRF_RENOVADO)))
    if "tfa-challenge" in campos:
        if campos["password"] in (f"totp:{TOTP}", f"recovery:{RECOVERY}"):
            return (200, {}, json.dumps(_ticket_json()))
        eco = {"data": None, "message": f"authentication failure password={campos['password']}"}
        return (401, {}, json.dumps(eco))
    if campos["password"] == CONTRASENA:
        desafio = cargar("9.2", "ticket_tfa_totp_recovery.json")["data"]
        if campos["username"] == "con2fa@pve":
            return (200, {}, json.dumps({"data": desafio}))
        return (200, {}, json.dumps(_ticket_json()))
    return (401, {}, json.dumps({"data": None, "message": f"password={campos['password']}"}))


@pytest.fixture
def entorno(rsps, tmp_path, reloj):
    """API simulada + servicios sobre HTTP simulado, con huella confiada."""
    rsps.add_callback(responses.POST, url(A, "/access/ticket"), callback=_cb_login)
    rsps.get(url(A, "/version"), json={"data": {"version": "9.2.1"}})
    huellas = RepositorioHuellas(tmp_path / "huellas.json")
    huellas.guardar(A, 8006, HUELLA_A)
    servicio = ServicioConexion(
        crear_transporte_http,
        huellas,
        AlmacenSecretos(backend=_LlaveroNulo()),
        reloj,
        obtener_huella_fn=lambda h, p, t: HUELLA_A,
    )
    return servicio


def _capturar(funcion, errores):
    try:
        return funcion()
    except ErrorProxLaunch as e:
        errores.append(e)
        return None


def _texto_de_registros(registros):
    formato = logging.Formatter()
    return "\n".join(formato.format(r) for r in registros)


def _salidas_de_error(errores):
    return "\n".join(f"{e!r}\n{e}\n{e.params}\n{e.detalle_tecnico}\n{e.codigo}" for e in errores)


def _ejecutar_todos_los_flujos(servicio, rsps, reloj, errores, objetos, inv, hacer_cfg):
    perfil = perfil_basico(recordar_credenciales=True)
    # Token: correcto e incorrecto (el servidor repite el secreto en el error).
    objetos.append(servicio.conectar(perfil, CredencialToken("ana@pve!lab", SECRETO_TOKEN)))
    agregar_error(
        rsps, "GET", url(A, "/version"), 401, f"No ticket PVEAPIToken=ana@pve!lab={SECRETO_TOKEN}"
    )
    _capturar(
        lambda: servicio.conectar(perfil, CredencialToken("ana@pve!lab", SECRETO_TOKEN)), errores
    )
    rsps.replace(responses.GET, url(A, "/version"), json={"data": {"version": "9.2.1"}})
    # Contraseña: correcta, incorrecta.
    sesion = servicio.conectar(perfil, CredencialContrasena("root", "pam", CONTRASENA))
    objetos.append(sesion)
    _capturar(
        lambda: servicio.conectar(perfil, CredencialContrasena("root", "pam", "otra")), errores
    )
    # 2FA: TOTP incorrecto, correcto y clave de recuperación.
    desafio = servicio.conectar(perfil, CredencialContrasena("con2fa", "pve", CONTRASENA))
    assert isinstance(desafio, DesafioTFA)
    objetos.append(desafio)
    _capturar(lambda: servicio.completar_tfa(desafio, "000000", TipoTFA.TOTP), errores)
    objetos.append(servicio.completar_tfa(desafio, TOTP, TipoTFA.TOTP))
    desafio2 = servicio.conectar(perfil, CredencialContrasena("con2fa", "pve", CONTRASENA))
    objetos.append(servicio.completar_tfa(desafio2, RECOVERY.upper(), TipoTFA.RECUPERACION))
    # Renovación del ticket (correcta) y renovación fallida.
    auth = sesion.cliente._auth
    assert isinstance(auth, AutenticadorTicket)
    reloj.avanzar(110 * 60)
    sesion.cliente.version()
    objetos.append(auth.ticket)
    reloj.avanzar(110 * 60)
    rsps.replace(responses.POST, url(A, "/access/ticket"), status=401, json={"data": None})
    _capturar(sesion.cliente.version, errores)
    # Creación: éxito y fallo con el texto del servidor repitiendo el token.
    rsps.get(url(A, "/cluster/nextid"), json={"data": "100"})
    rsps.post(url(A, RUTA_CREAR), json={"data": UPID})
    rsps.get(url(A, RUTA_ESTADO), json={"data": {
        "status": "stopped", "exitstatus": f"unable to create VM 100 - token {SECRETO_TOKEN} {CSRF}"
    }})  # fmt: skip
    rsps.get(url(A, RUTA_CONFIG), json={"data": None}, status=404)
    cliente = ClienteProxmox(
        crear_transporte_http(perfil, {A: HUELLA_A}),
        AutenticadorTicket(Ticket(TICKET, CSRF, "root@pam", reloj.ahora()), reloj),
        reloj,
    )
    from .apoyo_api import crear_sesion

    sesion_creacion = crear_sesion(TransporteFalso(), reloj=reloj)
    sesion_creacion.cliente = cliente
    resultado = ServicioCreacion(sesion_creacion, reloj).crear(
        hacer_cfg(), inv, lambda e: None, threading.Event()
    )
    if resultado.error:
        errores.append(resultado.error)
    objetos.append(resultado)


def test_rnf_06_ningun_secreto_en_logs_errores_repr_ni_salida(
    entorno, rsps, reloj, registros, capsys, tmp_path, inv, hacer_cfg
):
    errores, objetos = [], []
    _ejecutar_todos_los_flujos(entorno, rsps, reloj, errores, objetos, inv, hacer_cfg)

    assert len(errores) >= 5, "los flujos de error deben haberse ejecutado"
    texto_log = _texto_de_registros(registros)
    assert texto_log, "debe haberse registrado algo (DEBUG de peticiones)"
    hallazgos = {
        "registros": [n for n, v in TODOS.items() if v in texto_log],
        "errores": [n for n, v in TODOS.items() if v in _salidas_de_error(errores)],
        "repr": [n for n, v in TODOS.items() if v in "\n".join(repr(o) for o in objetos)],
        "salida": [n for n, v in TODOS.items() if v in "".join(capsys.readouterr())],
    }
    assert hallazgos == {"registros": [], "errores": [], "repr": [], "salida": []}


def test_rnf_06_ningun_secreto_en_el_archivo_de_log_de_produccion(
    entorno, rsps, reloj, tmp_path, inv, hacer_cfg
):
    logger = logging.getLogger("proxlaunch")
    nivel, propaga = logger.level, logger.propagate
    try:
        configurar_registro(tmp_path / "logs", nivel=logging.DEBUG)
        _ejecutar_todos_los_flujos(entorno, rsps, reloj, [], [], inv, hacer_cfg)
        for h in logger.handlers:
            h.flush()
        contenido = (tmp_path / "logs" / "proxlaunch.log").read_text(encoding="utf-8")
    finally:
        for h in list(logger.handlers):
            if getattr(h, "_proxlaunch", False):
                logger.removeHandler(h)
                h.close()
        logger.setLevel(nivel)
        logger.propagate = propaga
    assert contenido
    assert [n for n, v in TODOS.items() if v in contenido] == []


def test_rnf_06_ningun_secreto_en_los_archivos_de_usuario(
    entorno, rsps, reloj, tmp_path, inv, hacer_cfg
):
    _ejecutar_todos_los_flujos(entorno, rsps, reloj, [], [], inv, hacer_cfg)
    for archivo in tmp_path.rglob("*"):
        if archivo.is_file():
            texto = archivo.read_text(encoding="utf-8", errors="ignore")
            assert [n for n, v in TODOS.items() if v in texto] == [], archivo.name


def test_rnf_06_el_eco_del_servidor_en_un_error_http_se_enmascara(rsps):
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken

    transporte = crear_transporte_http(perfil_basico(), {A: HUELLA_A})
    transporte.usar_autenticador(AutenticadorToken(CredencialToken("ana@pve!lab", SECRETO_TOKEN)))
    agregar_error(
        rsps,
        "GET",
        url(A, "/version"),
        500,
        f"fallo Authorization: PVEAPIToken=ana@pve!lab={SECRETO_TOKEN}",
        {"data": None, "message": f"Cookie: PVEAuthCookie={TICKET}; password={CONTRASENA}"},
    )
    with pytest.raises(ErrorProxLaunch) as e:
        transporte.peticion("GET", "/version")
    salida = _salidas_de_error([e.value])
    assert SECRETO_TOKEN not in salida
    assert TICKET not in salida
    assert CONTRASENA not in salida


def test_rnf_06_error_de_conexion_no_filtra_credenciales(rsps):
    transporte = crear_transporte_http(perfil_basico(), {A: HUELLA_A})
    rsps.post(
        url(A, "/access/ticket"),
        body=requests.exceptions.ConnectionError(f"fallo con password={CONTRASENA}"),
    )
    with pytest.raises(ErrorProxLaunch) as e:
        transporte.peticion(
            "POST", "/access/ticket", datos={"username": "r", "password": CONTRASENA}
        )
    assert CONTRASENA not in _salidas_de_error([e.value])


def test_ca_04_7_el_desafio_no_expone_el_ticket_parcial_en_su_repr():
    parcial = ticket_parcial({"totp": True})
    d = DesafioTFA("ana@pve", parcial, True, False)
    assert parcial not in repr(d)


def test_ca_08_5_el_repr_de_las_credenciales_y_el_ticket_esta_enmascarado():
    objetos = [
        CredencialToken("ana@pve!lab", SECRETO_TOKEN),
        CredencialContrasena("root", "pam", CONTRASENA),
        Ticket(TICKET, CSRF, "root@pam", 0.0),
    ]
    texto = "\n".join(repr(o) + str(o) for o in objetos)
    for valor in (SECRETO_TOKEN, CONTRASENA, TICKET, CSRF):
        assert valor not in texto


def test_el_cuerpo_de_datos_de_respuesta_no_se_usa_en_los_registros(rsps, registros):
    rsps.get(url(A, "/version"), json={"data": {"version": "9.2.1", "oculto": SECRETO_TOKEN}})
    transporte = crear_transporte_http(perfil_basico(), {A: HUELLA_A})
    transporte.peticion("GET", "/version")
    assert SECRETO_TOKEN not in _texto_de_registros(registros)
    assert dato("9.2", "version.json")  # los datos simulados están disponibles
