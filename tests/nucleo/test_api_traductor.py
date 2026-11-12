"""Traductor de errores: una fila de la sección 7 de los requisitos por caso (RF-21, CA-21.1,
CA-21.2, A-8). Los textos de error siguen f1 §5 (sintéticos hasta capturarlos en laboratorio)."""

import pytest
import requests

from proxlaunch.nucleo.api.autenticacion import (
    DesafioTFA,
    TipoTFA,
    iniciar_sesion_ticket,
    responder_tfa,
)
from proxlaunch.nucleo.api.traductor_errores import (
    limpiar_detalle,
    nodo_de_ruta,
    traducir_excepcion,
    traducir_exitstatus,
    traducir_http,
)
from proxlaunch.nucleo.errores import CodigoError as C
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace

from .apoyo_api import (
    RUTA_ESTADO,
    Secuencia,
    TransporteFalso,
    estado_tarea,
    rutas_creacion,
    ticket_parcial,
)


def _capturar(funcion):
    with pytest.raises(ErrorProxLaunch) as e:
        funcion()
    return e.value


# --- Sección 7: una fila por caso ---------------------------------------------------------
# Cada proveedor recibe el contexto de fixtures y devuelve el ErrorProxLaunch provocado.


def _credenciales(ctx):
    return traducir_http(401, "No ticket", '{"data":null}')


def _ticket_expirado(ctx):
    return traducir_http(401, "No ticket", '{"data":null}', sesion_ticket=True)


def _huella_cambiada(ctx):
    exc = requests.exceptions.SSLError("Fingerprints did not match. Expected aa, got bb")
    return traducir_excepcion(exc, host="10.0.0.1")


def _tfa_no_soportado(ctx):
    t = TransporteFalso().en(
        "POST",
        "/access/ticket",
        {
            "ticket": ticket_parcial({"webauthn": {"x": 1}}),
            "CSRFPreventionToken": "x",
            "NeedTFA": 1,
        },
    )
    return _capturar(lambda: iniciar_sesion_ticket(t, "ana", "pve", "pw"))


def _tfa_codigo_incorrecto(ctx):
    t = TransporteFalso().en("POST", "/access/ticket", ErrorProxLaunch(C.CREDENCIALES_INVALIDAS))
    desafio = DesafioTFA("ana@pve", ticket_parcial({"totp": True}), True, False)
    return _capturar(lambda: responder_tfa(t, desafio, "000000", TipoTFA.TOTP))


def _servidor_caido(ctx):
    return traducir_excepcion(requests.exceptions.ConnectTimeout("t"), host="10.0.0.1")


def _nodo_caido(ctx):
    return traducir_http(595, "no route to host", "", nodo="pve2")


def _permisos(ctx):
    motivo = "Permission check failed (/vms/100, VM.Allocate)"
    return traducir_http(403, motivo, '{"data":null}')


def _vmid_ocupado_crear(ctx):
    return traducir_http(500, "VM 100 already exists on node 'pve1'", '{"data":null}')


def _vmid_ocupado_nextid(ctx):
    cuerpo = (
        '{"data":null,"errors":{"vmid":"VM 100 already exists"},'
        '"message":"Parameter verification failed.\\n"}'
    )
    return traducir_http(400, "Parameter verification failed.", cuerpo)


def _sin_espacio(ctx):
    return traducir_exitstatus(
        "unable to create VM 100 - lvcreate 'pve/vm-100-disk-0' error:   Volume group \"pve\" "
        "has insufficient free space (1023 extents): 8192 required."
    )


def _timeout_tarea(ctx):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("running"))
    resultado, _ = ctx["ejecutar_creacion"](t)
    assert resultado.desenlace == Desenlace.TIEMPO_AGOTADO
    return resultado.error


def _error_formato(ctx):
    cuerpo = '{"data":null,"errors":{"net0":"invalid format - format error"}}'
    return traducir_http(400, "Parameter verification failed.", cuerpo)


def _parametro_invalido(ctx):
    cuerpo = '{"data":null,"errors":{"cores":"value must be at least 1"}}'
    return traducir_http(400, "Parameter verification failed.", cuerpo)


def _version_no_soportada(ctx):
    return ctx["error_version_7"]()


def _recurso_inexistente(ctx):
    return traducir_http(500, "storage 'nfs9' does not exist", '{"data":null}', nodo="pve1")


def _desconocido(ctx):
    return traducir_http(500, "algo muy raro", '{"data":null}')


FILAS = [
    pytest.param(_credenciales, C.CREDENCIALES_INVALIDAS, {}, id="S7-credenciales-invalidas"),
    pytest.param(_ticket_expirado, C.SESION_EXPIRADA, {}, id="S7-ticket-expirado"),
    pytest.param(
        _huella_cambiada, C.HUELLA_CAMBIADA, {"host": "10.0.0.1"}, id="S7-huella-cambiada"
    ),
    pytest.param(
        _tfa_no_soportado, C.TFA_NO_SOPORTADO, {"tipos": "webauthn"}, id="S7-2fa-no-soportado"
    ),
    pytest.param(
        _tfa_codigo_incorrecto, C.TFA_CODIGO_INCORRECTO, {}, id="S7-codigo-2fa-incorrecto"
    ),
    pytest.param(
        _servidor_caido, C.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.1"}, id="S7-servidor-caido"
    ),
    pytest.param(
        _nodo_caido,
        C.NODO_NO_DISPONIBLE,
        {"nodo": "pve2", "estado_http": "595"},
        id="S7-nodo-caido-595",
    ),
    pytest.param(
        _permisos,
        C.PERMISO_INSUFICIENTE,
        {"privilegio": "VM.Allocate", "ruta": "/vms/100"},
        id="S7-permisos-insuficientes",
    ),
    pytest.param(
        _vmid_ocupado_crear,
        C.VMID_OCUPADO,
        {"vmid": "100", "nodo": "pve1"},
        id="S7-A8-vmid-ocupado-500-al-crear",
    ),
    pytest.param(
        _vmid_ocupado_nextid, C.VMID_OCUPADO, {"vmid": "100"}, id="S7-A8-vmid-ocupado-400-nextid"
    ),
    pytest.param(_sin_espacio, C.SIN_ESPACIO, {"storage": "pve"}, id="S7-storage-sin-espacio"),
    pytest.param(_timeout_tarea, C.TAREA_TIEMPO_AGOTADO, {}, id="S7-timeout-de-tarea"),
    pytest.param(_error_formato, C.ERROR_FORMATO, {"campo": "net0"}, id="S7-error-de-formato"),
    pytest.param(
        _parametro_invalido,
        C.PARAMETRO_INVALIDO,
        {"campo": "cores"},
        id="S7-parametro-invalido-400",
    ),
    pytest.param(
        _version_no_soportada, C.VERSION_NO_SOPORTADA, {"minima": "8.0"}, id="S7-version-7"
    ),
    pytest.param(
        _recurso_inexistente,
        C.RECURSO_INEXISTENTE,
        {"recurso": "nfs9", "nodo": "pve1"},
        id="S7-recurso-inexistente",
    ),
    pytest.param(_desconocido, C.DESCONOCIDO, {"estado_http": "500"}, id="S7-error-desconocido"),
]


@pytest.fixture
def ctx(ejecutar_creacion, tmp_path):
    """Contexto de fixtures para los proveedores de errores."""
    from proxlaunch.nucleo.modelos.conexion import CredencialToken
    from proxlaunch.nucleo.servicios.conexion import ServicioConexion

    def _error_version_7():
        from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
        from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
        from proxlaunch.nucleo.reloj import RelojSimulado

        from .apoyo_api import HUELLA_A, TOKEN_ID, TOKEN_SECRETO, perfil_basico

        t = TransporteFalso().en("GET", "/version", {"version": "7.4-17"})
        servicio = ServicioConexion(
            lambda perfil, huellas: t,
            RepositorioHuellas(tmp_path / "huellas.json"),
            AlmacenSecretos(backend=object()),
            RelojSimulado(),
        )
        servicio._huellas.guardar("10.0.0.1", 8006, HUELLA_A)
        return _capturar(
            lambda: servicio.conectar(perfil_basico(), CredencialToken(TOKEN_ID, TOKEN_SECRETO))
        )

    return {"ejecutar_creacion": ejecutar_creacion, "error_version_7": _error_version_7}


@pytest.mark.parametrize(("proveedor", "codigo", "params"), FILAS)
def test_cada_fila_de_la_seccion_7_produce_su_codigo(ctx, proveedor, codigo, params):
    error = proveedor(ctx)
    assert isinstance(error, ErrorProxLaunch)
    assert error.codigo == codigo
    for clave, valor in params.items():
        assert error.params.get(clave) == valor


@pytest.mark.parametrize(("proveedor", "codigo", "params"), FILAS)
def test_ca_21_3_el_detalle_tecnico_no_lleva_trazas_de_python(ctx, proveedor, codigo, params):
    error = proveedor(ctx)
    assert "Traceback" not in error.detalle_tecnico
    assert "Traceback" not in str(error)


# --- Variantes de texto de cada patrón ----------------------------------------------------


@pytest.mark.parametrize(
    ("motivo", "privilegio", "ruta"),
    [
        pytest.param(
            "Permission check failed (/vms/100, VM.Allocate)", "VM.Allocate", "/vms/100", id="vm"
        ),
        pytest.param(
            "Permission check failed (/storage/local-lvm, Datastore.AllocateSpace)",
            "Datastore.AllocateSpace",
            "/storage/local-lvm",
            id="storage",
        ),
        pytest.param(
            "Permission check failed (/sdn/zones/localnetwork/vmbr0, SDN.Use)",
            "SDN.Use",
            "/sdn/zones/localnetwork/vmbr0",
            id="sdn",
        ),
        pytest.param(
            "Permission check failed (/vms/100, VM.Config.Disk|VM.Config.Options)",
            "VM.Config.Disk|VM.Config.Options",
            "/vms/100",
            id="alternativa",
        ),
    ],
)
def test_s7_permiso_extrae_privilegio_y_ruta(motivo, privilegio, ruta):
    error = traducir_http(403, motivo, "")
    assert error.codigo == C.PERMISO_INSUFICIENTE
    assert error.params == {"privilegio": privilegio, "ruta": ruta}


def test_s7_403_sin_texto_conocido_sigue_siendo_permiso_insuficiente():
    error = traducir_http(403, "Forbidden", "")
    assert error.codigo == C.PERMISO_INSUFICIENTE
    assert error.params == {}


@pytest.mark.parametrize(
    "texto",
    [
        "out of space",
        "Insufficient free space",
        "no space left on device",
        'volume group "vg0" has insufficient free space',
        "unable to create VM 100 - OUT OF SPACE",
    ],
)
def test_s7_sin_espacio_todas_las_variantes(texto):
    assert traducir_exitstatus(texto).codigo == C.SIN_ESPACIO


def test_s7_sin_espacio_extrae_el_storage_si_viene():
    error = traducir_exitstatus("storage 'local-lvm' out of space")
    assert error.params["storage"] == "local-lvm"


def test_s7_vmid_ocupado_400_sin_nodo():
    cuerpo = '{"errors":{"vmid":"VM 100 already exists"}}'
    error = traducir_http(400, "Parameter verification failed.", cuerpo)
    assert error.codigo == C.VMID_OCUPADO
    assert error.params == {"vmid": "100"}


def test_s7_error_de_formato_texto_plano_extrae_el_campo():
    error = traducir_http(400, "", "net0: invalid format - format error")
    assert error.codigo == C.ERROR_FORMATO
    assert error.params["campo"] == "net0"


def test_s7_400_con_errores_expone_campo_y_mensaje():
    cuerpo = '{"errors":{"memory":"value must be at least 16"}}'
    error = traducir_http(400, "Parameter verification failed.", cuerpo)
    assert error.codigo == C.PARAMETRO_INVALIDO
    assert error.params["campo"] == "memory"
    assert "at least 16" in error.params["mensaje"]


def test_s7_404_es_recurso_inexistente_con_nodo():
    error = traducir_http(404, "Not Found", "", nodo="pve3")
    assert error.codigo == C.RECURSO_INEXISTENTE
    assert error.params == {"nodo": "pve3"}


def test_s7_configuracion_inexistente_en_500():
    motivo = "Configuration file 'nodes/pve1/qemu-server/100.conf' does not exist"
    assert traducir_http(500, motivo, "").codigo == C.RECURSO_INEXISTENTE


@pytest.mark.parametrize("estado", [595, 596])
def test_s7_nodo_caido_595_y_596(estado):
    error = traducir_http(estado, "no route to host", "", nodo="pve2")
    assert error.codigo == C.NODO_NO_DISPONIBLE
    assert error.params["estado_http"] == str(estado)


def test_ca_21_2_error_desconocido_conserva_el_texto_original():
    error = traducir_http(502, "Bad Gateway", '{"data":null,"message":"proxy roto"}')
    assert error.codigo == C.DESCONOCIDO
    assert "Bad Gateway" in error.detalle_tecnico
    assert "proxy roto" in error.detalle_tecnico
    assert error.params["estado_http"] == "502"


def test_ca_21_2_exitstatus_desconocido_conserva_el_texto_original():
    error = traducir_exitstatus("unable to create VM 100 - algo raro")
    assert error.codigo == C.DESCONOCIDO
    assert "algo raro" in error.detalle_tecnico


def test_exitstatus_vacio_o_nulo_es_desconocido():
    assert traducir_exitstatus(None).codigo == C.DESCONOCIDO
    assert traducir_exitstatus("").codigo == C.DESCONOCIDO


def test_el_permiso_tiene_prioridad_sobre_otros_patrones():
    motivo = "Permission check failed (/storage/x, Datastore.AllocateSpace) does not exist"
    assert traducir_http(403, motivo, "").codigo == C.PERMISO_INSUFICIENTE


# --- Excepciones de requests ---------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ConnectTimeout("t"),
        requests.exceptions.ReadTimeout("t"),
        requests.exceptions.ConnectionError("rechazada"),
        requests.exceptions.SSLError("handshake"),
    ],
)
def test_excepciones_de_red_son_servidor_no_responde(exc):
    assert traducir_excepcion(exc, host="h").codigo == C.SERVIDOR_NO_RESPONDE


def test_excepcion_ya_traducida_se_devuelve_igual():
    original = ErrorProxLaunch(C.VMID_OCUPADO, {"vmid": "1"})
    assert traducir_excepcion(original) is original


def test_excepcion_cualquiera_es_desconocida():
    assert traducir_excepcion(ValueError("x")).codigo == C.DESCONOCIDO


# --- Secretos y límites --------------------------------------------------------------------


def test_rnf_06_el_detalle_enmascara_campos_con_secretos():
    cuerpo = '{"data":null,"message":"fallo password=hunter2 ticket=PVE:x:y::z"}'
    detalle = traducir_http(500, "error", cuerpo).detalle_tecnico
    assert "hunter2" not in detalle
    assert "PVE:x:y::z" not in detalle


def test_el_detalle_se_acota():
    assert len(limpiar_detalle("x" * 10_000)) <= 2003


@pytest.mark.parametrize(
    ("ruta", "nodo"),
    [("/nodes/pve1/qemu", "pve1"), ("/nodes/pve2/tasks/UPID:x/status", "pve2"), ("/version", None)],
)
def test_nodo_de_ruta(ruta, nodo):
    assert nodo_de_ruta(ruta) == nodo


def test_secuencia_de_apoyo_repite_el_ultimo_valor():
    s = Secuencia(1, 2)
    assert [s.siguiente() for _ in range(4)] == [1, 2, 2, 2]
    assert RUTA_ESTADO.endswith("/status")
