"""ServicioCreacion: etapas, seguimiento de la tarea y desenlaces (RF-13, RF-19, RF-20, RNF-16,
A-8). Transporte falso con reloj simulado; un caso de extremo a extremo con HTTP simulado."""

import threading
from urllib.parse import parse_qs

import pytest

from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.transporte import TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken, Ticket
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa
from proxlaunch.nucleo.servicios.creacion import (
    INTERVALO_SONDEO_S,
    MAX_ESPERA_S,
    TOLERANCIA_RED_S,
    ServicioCreacion,
)

from .apoyo_api import (
    HUELLA_A,
    RUTA_CONFIG,
    RUTA_CREAR,
    RUTA_ESTADO,
    RUTA_LOG,
    TOKEN_ID,
    TOKEN_SECRETO,
    UPID,
    Secuencia,
    TransporteFalso,
    agregar_error,
    cargar,
    crear_sesion,
    dato,
    estado_tarea,
    rutas_creacion,
    url,
)

RED_CAIDA = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.1"}, "timeout")
ETAPAS_OK = [
    Etapa.VALIDANDO,
    Etapa.ENVIANDO,
    Etapa.CREANDO,
    Etapa.COMPROBANDO,
    Etapa.LISTO,
]
CONFIG = dato("9.2", "qemu_config.json")


def _ok(t=None, **kw):
    t = t or TransporteFalso()
    kw.setdefault("estado", estado_tarea("ok"))
    kw.setdefault("config", CONFIG)
    return rutas_creacion(t, **kw)


def _falla(nombre="error_generico", **kw):
    """Tarea que termina con error y la máquina NO existe a medias."""
    return rutas_creacion(TransporteFalso(), estado=estado_tarea(nombre), **kw)


# --- Camino feliz -----------------------------------------------------------------------


def test_ca_20_3_ok_confirma_con_la_configuracion_de_la_vm(ejecutar_creacion):
    t = _ok(estado=Secuencia(estado_tarea("running"), estado_tarea("running"), estado_tarea("ok")))
    resultado, etapas = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.OK
    assert (resultado.vmid, resultado.nodo, resultado.upid) == (100, "pve1", UPID)
    assert resultado.error is None
    assert len(t.llamadas_a("GET", RUTA_CONFIG)) == 1
    # La confirmación llega después de la última consulta de estado.
    ultimo_estado = max(i for i, c in enumerate(t.llamadas) if c.ruta == RUTA_ESTADO)
    config = next(i for i, c in enumerate(t.llamadas) if c.ruta == RUTA_CONFIG)
    assert config > ultimo_estado


def test_ca_20_2_las_etapas_se_notifican_en_orden(ejecutar_creacion):
    _, etapas = ejecutar_creacion(_ok())
    assert etapas == ETAPAS_OK


def test_ca_20_1_sondeo_cada_1_5_segundos_hasta_stopped(ejecutar_creacion, reloj):
    instantes = []

    def _estado(llamada):
        instantes.append(reloj.ahora())
        return estado_tarea("running") if len(instantes) < 4 else estado_tarea("ok")

    ejecutar_creacion(_ok(estado=_estado))
    assert instantes == [0.0, 1.5, 3.0, 4.5]
    assert 1 <= INTERVALO_SONDEO_S <= 2


def test_ca_19_3_la_peticion_lleva_los_parametros_de_la_configuracion(ejecutar_creacion):
    t = _ok()
    ejecutar_creacion(t)
    (envio,) = t.llamadas_a("POST", RUTA_CREAR)
    assert envio.datos["vmid"] == "100"
    assert envio.datos["name"] == "srv-web-01"
    assert envio.datos["net0"] == "virtio,bridge=vmbr0"
    assert envio.datos["scsi0"].startswith("local-lvm:32")


def test_ca_13_1_antes_de_enviar_se_comprueba_el_vmid(ejecutar_creacion):
    t = _ok()
    ejecutar_creacion(t)
    (nextid,) = t.llamadas_a("GET", "/cluster/nextid")
    assert nextid.params == {"vmid": 100}
    assert t.metodos.index("POST") > 0


def test_ca_20_5_warnings_es_creada_con_avisos_y_trae_el_log(ejecutar_creacion):
    t = _ok(estado=estado_tarea("warnings"))
    resultado, etapas = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.CON_AVISOS
    assert resultado.error is None
    assert "WARN: no se pudo aplicar el parametro X" in resultado.log_tarea
    assert len(t.llamadas_a("GET", RUTA_LOG)) == 1
    assert etapas[-1] == Etapa.LISTO


def test_ca_20_3_ok_no_pide_el_log(ejecutar_creacion):
    t = _ok()
    ejecutar_creacion(t)
    assert t.llamadas_a("GET", RUTA_LOG) == []


# --- Errores de la tarea ----------------------------------------------------------------


def test_ca_20_4_error_traducido_con_el_texto_original(ejecutar_creacion):
    t = _falla()
    resultado, etapas = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.upid == UPID
    assert resultado.error.codigo == CodigoError.DESCONOCIDO
    assert "unable to create VM 100 - algo salio mal" in resultado.error.detalle_tecnico
    assert Etapa.LISTO not in etapas
    assert etapas[-1] == Etapa.COMPROBANDO


def test_ca_20_4_sin_espacio_se_traduce(ejecutar_creacion):
    t = _falla("error_sin_espacio")
    resultado, _ = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.SIN_ESPACIO
    assert resultado.error.params["storage"] == "local-lvm"
    assert resultado.error.params["vg"] == "pve"


def test_ca_20_4_el_error_incluye_el_log_de_la_tarea(ejecutar_creacion):
    resultado, _ = ejecutar_creacion(_falla())
    assert resultado.log_tarea  # para "Ver detalles técnicos"


def test_ca_20_10_fallo_con_configuracion_presente_es_parcial(ejecutar_creacion):
    t = _ok(estado=estado_tarea("error_generico"))
    resultado, _ = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.PARCIAL
    assert resultado.error.codigo == CodigoError.DESCONOCIDO
    assert "DELETE" not in t.metodos


def test_ca_20_10_fallo_sin_configuracion_es_error_simple(ejecutar_creacion):
    resultado, _ = ejecutar_creacion(_falla())
    assert resultado.desenlace == Desenlace.ERROR


def test_ca_20_10_si_no_se_puede_leer_la_configuracion_se_informa_el_error(ejecutar_creacion):
    sin_permiso = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "VM.Audit"})
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("error_generico"), config=sin_permiso)
    resultado, _ = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.DESCONOCIDO


def test_ca_20_3_ok_pero_la_maquina_no_existe_es_error(ejecutar_creacion):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"))  # config inexistente
    resultado, etapas = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.RECURSO_INEXISTENTE
    assert Etapa.LISTO not in etapas


def test_ca_20_3_ok_sin_permiso_para_confirmar_es_con_avisos(ejecutar_creacion):
    sin_permiso = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "VM.Audit"})
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=sin_permiso)
    resultado, _ = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.CON_AVISOS
    assert resultado.error.codigo == CodigoError.PERMISO_INSUFICIENTE


def test_ca_20_4_un_error_ajeno_al_desenlace_durante_el_sondeo_es_conexion_perdida_con_upid(
    ejecutar_creacion,
):
    # F7: tras obtener el UPID, un error que no es el desenlace de la tarea (aquí sesión
    # expirada) ya no es ERROR definitivo: no se sabe el estado real, así que CONEXION_PERDIDA.
    expirada = ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "401")
    resultado, _ = ejecutar_creacion(_ok(estado=expirada))
    assert resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert resultado.upid == UPID
    assert resultado.error.codigo == CodigoError.SESION_EXPIRADA


# --- Tiempo máximo y red ----------------------------------------------------------------


def test_ca_20_6_mas_de_10_minutos_es_tiempo_agotado_sin_borrar(ejecutar_creacion, reloj):
    t = _ok(estado=estado_tarea("running"))
    resultado, etapas = ejecutar_creacion(t)
    assert MAX_ESPERA_S == 600
    assert resultado.desenlace == Desenlace.TIEMPO_AGOTADO
    assert resultado.error.codigo == CodigoError.TAREA_TIEMPO_AGOTADO
    assert resultado.error.params["upid"] == UPID
    assert resultado.upid == UPID
    assert 600 <= reloj.ahora() < 602
    assert len(t.llamadas_a("POST", RUTA_CREAR)) == 1  # no reintenta la creación
    assert "DELETE" not in t.metodos
    assert Etapa.LISTO not in etapas


def test_ca_20_6_justo_antes_del_limite_todavia_se_sigue_esperando(ejecutar_creacion, reloj):
    estados = Secuencia(*([estado_tarea("running")] * 399), estado_tarea("ok"))
    resultado, _ = ejecutar_creacion(_ok(estado=estados))
    assert resultado.desenlace == Desenlace.OK
    assert reloj.ahora() < 600


def test_ca_20_6_el_tiempo_maximo_es_configurable(ejecutar_creacion, reloj):
    resultado, _ = ejecutar_creacion(_ok(estado=estado_tarea("running")), max_espera_s=30.0)
    assert resultado.desenlace == Desenlace.TIEMPO_AGOTADO
    assert 30 <= reloj.ahora() < 32


def test_ca_20_7_red_caida_tres_veces_y_recuperada_no_da_error(ejecutar_creacion):
    estados = Secuencia(
        RED_CAIDA, RED_CAIDA, RED_CAIDA, estado_tarea("running"), estado_tarea("ok")
    )
    resultado, _ = ejecutar_creacion(_ok(estado=estados))
    assert resultado.desenlace == Desenlace.OK
    assert resultado.error is None


def test_ca_20_7_el_nodo_595_durante_el_sondeo_tambien_se_tolera(ejecutar_creacion):
    nodo = ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve1"}, "595")
    estados = Secuencia(nodo, nodo, estado_tarea("ok"))
    resultado, _ = ejecutar_creacion(_ok(estado=estados))
    assert resultado.desenlace == Desenlace.OK


def test_ca_20_7_caida_sostenida_de_mas_de_60_s_es_conexion_perdida(ejecutar_creacion, reloj):
    t = _ok(estado=RED_CAIDA)
    resultado, etapas = ejecutar_creacion(t)
    assert TOLERANCIA_RED_S == 60
    assert resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert resultado.upid == UPID
    assert resultado.error.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert 60 < reloj.ahora() <= 63
    assert "DELETE" not in t.metodos
    assert Etapa.LISTO not in etapas


def test_ca_20_7_las_caidas_cortas_repetidas_no_acumulan(ejecutar_creacion):
    # Cada caída dura 3 sondeos; entre ellas hay respuestas correctas: nunca supera 60 s seguidos.
    ciclo = [RED_CAIDA] * 3 + [estado_tarea("running")]
    estados = Secuencia(*(ciclo * 30), estado_tarea("ok"))
    resultado, _ = ejecutar_creacion(_ok(estado=estados), max_espera_s=10_000.0)
    assert resultado.desenlace == Desenlace.OK


def test_ca_20_7_red_caida_al_confirmar_el_resultado_es_conexion_perdida(ejecutar_creacion):
    resultado, _ = ejecutar_creacion(_ok(config=RED_CAIDA))
    assert resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert resultado.upid == UPID


def test_ca_20_7_red_caida_antes_de_enviar_no_envia_nada(ejecutar_creacion):
    t = _ok()
    t.en("GET", "/cluster/nextid", RED_CAIDA)
    resultado, etapas = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert t.llamadas_a("POST", RUTA_CREAR) == []
    assert etapas == [Etapa.VALIDANDO]


# --- RF-19: envío -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "respuesta",
    [None, "", "basura", {"upid": UPID}, "UPID:"],
    ids=["nulo", "vacio", "basura", "objeto", "prefijo-solo"],
)
def test_ca_19_5_respuesta_sin_upid_valido_no_inicia_el_sondeo(ejecutar_creacion, respuesta):
    t = _ok(crear=respuesta)
    resultado, etapas = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.UPID_INVALIDO
    assert resultado.upid is None
    assert t.llamadas_a("GET", RUTA_ESTADO) == []
    assert etapas == [Etapa.VALIDANDO, Etapa.ENVIANDO]


def test_ca_19_6_el_envio_es_un_solo_post_aunque_falle_la_red(ejecutar_creacion):
    t = _ok(crear=ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "ReadTimeout en POST"))
    resultado, _ = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert len(t.llamadas_a("POST", RUTA_CREAR)) == 1  # nunca se reintenta un POST


def test_ca_13_7_nodo_caido_antes_de_enviar_falla_sin_crear_nada(ejecutar_creacion):
    caido = ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve1"}, "595")
    t = _ok(crear=caido)
    resultado, _ = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.NODO_NO_DISPONIBLE
    assert t.llamadas_a("GET", RUTA_ESTADO) == []


def test_s7_permisos_al_crear_extrae_el_privilegio(ejecutar_creacion):
    sin_permiso = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "VM.Allocate", "ruta": "/vms/100"}
    )
    resultado, _ = ejecutar_creacion(_ok(crear=sin_permiso))
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.params["privilegio"] == "VM.Allocate"


# --- RF-13: VMID ------------------------------------------------------------------------


def test_ca_13_3_vmid_ocupado_al_crear_sugiere_el_siguiente(ejecutar_creacion):
    ocupado = ErrorProxLaunch(
        CodigoError.VMID_OCUPADO, {"vmid": "100", "nodo": "pve1"}, "VM 100 already exists"
    )
    t = _ok(crear=ocupado)
    resultado, etapas = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.VMID_OCUPADO
    assert resultado.error.params["vmid"] == "100"
    assert resultado.error.params["siguiente"] == "101"
    assert etapas == [Etapa.VALIDANDO, Etapa.ENVIANDO]
    assert t.llamadas_a("GET", RUTA_ESTADO) == []


def test_ca_13_3_si_no_se_puede_pedir_el_siguiente_el_error_se_mantiene(ejecutar_creacion):
    ocupado = ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "100"}, "ya existe")

    def _nextid(llamada):
        if llamada.params:
            return "100"
        raise RED_CAIDA

    t = _ok(crear=ocupado)
    t.en("GET", "/cluster/nextid", _nextid)
    resultado, _ = ejecutar_creacion(t)
    assert resultado.error.codigo == CodigoError.VMID_OCUPADO
    assert "siguiente" not in resultado.error.params


def test_v_03_nextid_con_vmid_ocupado_400_detiene_antes_del_post(ejecutar_creacion):
    ocupado = ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "100"}, "VM 100 already exists")

    def _nextid(llamada):
        if llamada.params:
            raise ocupado
        return "102"

    t = _ok()
    t.en("GET", "/cluster/nextid", _nextid)
    resultado, etapas = ejecutar_creacion(t)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.VMID_OCUPADO
    assert resultado.error.params["siguiente"] == "102"
    assert t.llamadas_a("POST", RUTA_CREAR) == []
    assert etapas == [Etapa.VALIDANDO]


def test_v_03_extremo_a_extremo_con_el_400_real_de_nextid(rsps, inv, hacer_cfg, reloj):
    host = "10.0.0.1"
    agregar_error(
        rsps,
        "GET",
        url(host, "/cluster/nextid") + "?vmid=100",
        400,
        "Parameter verification failed.",
        {
            "data": None,
            "errors": {"vmid": "VM 100 already exists"},
            "message": "Parameter verification failed.\n",
        },
    )
    rsps.get(url(host, "/cluster/nextid"), json={"data": "104"})
    resultado = _servicio_http(reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.VMID_OCUPADO
    assert resultado.error.params["siguiente"] == "104"
    assert all(c.request.method != "POST" for c in rsps.calls)


def test_ca_13_3_extremo_a_extremo_con_el_500_real_al_crear(rsps, inv, hacer_cfg, reloj):
    host = "10.0.0.1"
    rsps.get(url(host, "/cluster/nextid"), json={"data": "100"})
    agregar_error(
        rsps,
        "POST",
        url(host, RUTA_CREAR),
        500,
        "VM 100 already exists on node 'pve1'",
        dato_json("error_vmid_ocupado_crear_500.json"),
    )
    resultado = _servicio_http(reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert resultado.error.codigo == CodigoError.VMID_OCUPADO
    assert resultado.error.params["vmid"] == "100"
    assert resultado.error.params["nodo"] == "pve1"
    assert resultado.error.params["siguiente"] == "100"  # lo que devuelva /cluster/nextid


# --- Validación local -------------------------------------------------------------------


def test_la_validacion_local_falla_antes_de_cualquier_peticion(ejecutar_creacion, hacer_cfg):
    t = _ok()
    resultado, etapas = ejecutar_creacion(t, cfg=hacer_cfg(nombre="-nombre invalido"))
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.PARAMETRO_INVALIDO
    assert resultado.error.params["campo"] == "nombre"
    assert t.llamadas == []
    assert etapas == [Etapa.VALIDANDO]


# --- Cancelación ------------------------------------------------------------------------


def test_cancelar_antes_de_enviar_no_envia_ni_borra_nada(ejecutar_creacion):
    cancelado = threading.Event()
    cancelado.set()
    t = _ok()
    resultado, etapas = ejecutar_creacion(t, cancelado=cancelado)
    assert resultado.desenlace == Desenlace.CANCELADO
    assert resultado.error is None
    assert resultado.upid is None
    assert t.llamadas_a("POST", RUTA_CREAR) == []
    assert "DELETE" not in t.metodos
    assert Etapa.ENVIANDO not in etapas


def test_cancelar_durante_el_seguimiento_deja_de_esperar_sin_borrar(ejecutar_creacion):
    cancelado = threading.Event()
    consultas = []

    def _estado(llamada):
        consultas.append(1)
        if len(consultas) == 2:
            cancelado.set()
        return estado_tarea("running")

    t = _ok(estado=_estado)
    resultado, etapas = ejecutar_creacion(t, cancelado=cancelado)
    assert resultado.desenlace == Desenlace.CANCELADO
    assert resultado.error is None
    assert resultado.upid == UPID  # la tarea pudo seguir en Proxmox
    assert len(consultas) == 2
    assert "DELETE" not in t.metodos
    assert Etapa.LISTO not in etapas


def test_cancelar_con_la_red_caida_antes_de_enviar_devuelve_cancelado_sin_esperar(
    ejecutar_creacion, reloj
):
    cancelado = threading.Event()
    cancelado.set()
    t = _ok()
    t.en("GET", "/cluster/nextid", RED_CAIDA)
    resultado, _ = ejecutar_creacion(t, cancelado=cancelado)
    assert resultado.desenlace == Desenlace.CANCELADO
    assert reloj.ahora() < 5


# --- Renovación del ticket durante el seguimiento ---------------------------------------


def test_ca_03_2_el_ticket_se_renueva_en_pleno_seguimiento_sin_reiniciar_la_tarea(
    ejecutar_creacion, reloj, respuesta
):
    reloj.avanzar(105 * 60 - 5)  # a 5 s del margen de renovación
    auth = AutenticadorTicket(Ticket("PVE:root@pam:VIEJO::s", "A:viejo", "root@pam", 0.0), reloj)
    estados = Secuencia(*([estado_tarea("running")] * 6), estado_tarea("ok"))
    t = _ok(estado=estados)
    t.en("POST", "/access/ticket", respuesta("9.2", "ticket_renovado.json")["data"])
    resultado, _ = ejecutar_creacion(t, auth=auth)
    assert resultado.desenlace == Desenlace.OK
    assert len(t.llamadas_a("POST", "/access/ticket")) == 1  # renovó una vez
    assert len(t.llamadas_a("POST", RUTA_CREAR)) == 1  # sin reiniciar la creación
    # Las consultas posteriores a la renovación usan el ticket nuevo.
    cookies = [c.cookies["PVEAuthCookie"] for c in t.llamadas if c.ruta == RUTA_ESTADO]
    assert cookies[0] == "PVE:root@pam:VIEJO::s"
    assert cookies[-1] == "PVE:root@pam:6535CC99::cmVub3ZhZG8"


def test_ca_03_2_el_post_de_creacion_lleva_el_csrf_del_ticket(ejecutar_creacion, reloj):
    auth = AutenticadorTicket(Ticket("PVE:root@pam:T::s", "CSRF:abc", "root@pam", 0.0), reloj)
    t = _ok()
    ejecutar_creacion(t, auth=auth)
    (envio,) = t.llamadas_a("POST", RUTA_CREAR)
    assert envio.cabeceras["CSRFPreventionToken"] == "CSRF:abc"
    assert "CSRFPreventionToken" not in t.llamadas_a("GET", RUTA_ESTADO)[0].cabeceras


# --- Ninguna petición DELETE en ningún flujo --------------------------------------------


ESCENARIOS = {
    "ok": lambda: _ok(),
    "error": lambda: _falla(),
    "parcial": lambda: _ok(estado=estado_tarea("error_generico")),
    "sin_espacio": lambda: _falla("error_sin_espacio"),
    "timeout": lambda: _ok(estado=estado_tarea("running")),
    "red_perdida": lambda: _ok(estado=RED_CAIDA),
    "upid_invalido": lambda: _ok(crear="basura"),
    "vmid_ocupado": lambda: _ok(crear=ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "100"})),
    "con_avisos": lambda: _ok(estado=estado_tarea("warnings")),
}


@pytest.mark.parametrize("nombre", list(ESCENARIOS))
def test_ca_20_10_ningun_flujo_borra_nada(ejecutar_creacion, nombre):
    t = ESCENARIOS[nombre]()
    ejecutar_creacion(t)
    assert "DELETE" not in t.metodos


# --- Extremo a extremo con HTTP simulado ------------------------------------------------


def dato_json(nombre):
    return cargar("9.2", nombre)


def _servicio_http(reloj):
    host = "10.0.0.1"
    transporte = TransporteHttp([host], 8006, huellas={host: HUELLA_A})
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken

    auth = AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO))
    sesion = crear_sesion(TransporteFalso(), reloj=reloj)
    sesion.cliente = ClienteProxmox(transporte, auth, reloj)
    return ServicioCreacion(sesion, reloj)


def test_ca_17_2_extremo_a_extremo_el_post_va_codificado_como_formulario(
    rsps, inv, hacer_cfg, reloj
):
    host = "10.0.0.1"
    rsps.get(url(host, "/cluster/nextid"), json={"data": "100"})
    rsps.post(url(host, RUTA_CREAR), json=cargar("9.2", "crear_vm_upid.json"))
    rsps.get(url(host, RUTA_ESTADO), json={"data": estado_tarea("ok")})
    rsps.get(url(host, RUTA_CONFIG), json={"data": CONFIG})
    etapas = []
    resultado = _servicio_http(reloj).crear(hacer_cfg(), inv, etapas.append, threading.Event())
    assert resultado.desenlace == Desenlace.OK
    assert etapas == ETAPAS_OK
    envio = next(c.request for c in rsps.calls if c.request.method == "POST")
    assert envio.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert "net0=virtio%2Cbridge%3Dvmbr0" in envio.body
    campos = parse_qs(envio.body)
    assert campos["vmid"] == ["100"]
    assert campos["name"] == ["srv-web-01"]
    assert campos["scsi0"] == ["local-lvm:32,discard=on,ssd=1,iothread=1"]
    assert all(c.request.method != "DELETE" for c in rsps.calls)


def test_rnf_16_un_nombre_con_caracteres_peligrosos_no_llega_al_post(rsps, inv, hacer_cfg, reloj):
    # La validación (V-01) lo rechaza antes de enviar nada: ni una sola petición.
    resultado = _servicio_http(reloj).crear(
        hacer_cfg(nombre="a,bios=ovmf&x"), inv, lambda e: None, threading.Event()
    )
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.PARAMETRO_INVALIDO
    assert len(rsps.calls) == 0
