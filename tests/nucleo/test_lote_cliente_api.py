"""Cambios de la capa API para lotes: vmid_libre, vms_visibles, estado_actual_vm, eliminar_vm
y el traductor (403 de etiquetas, 595/596/597). Mock con ``responses`` y transporte falso."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.traductor_errores import traducir_http
from proxlaunch.nucleo.api.transporte import TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo_api import HUELLA_A, HUELLA_B, TOKEN_ID, TOKEN_SECRETO, agregar_error, url
from .apoyo_lote import Cluster, Http, TransporteCluster, instalar_http, upid_de

A, B = "10.0.0.1", "10.0.0.2"


def _cliente_http(*hosts):
    transporte = TransporteHttp(
        list(hosts), 8006, huellas={h: HUELLA_A if h == A else HUELLA_B for h in hosts}
    )
    return ClienteProxmox(
        transporte, AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO)), RelojSimulado()
    )


def _cliente_directo():
    cluster = Cluster()
    t = TransporteCluster(cluster)
    return ClienteProxmox(
        t, AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO)), RelojSimulado()
    ), cluster


# --- vmid_libre -----------------------------------------------------------------------------


def test_vmid_libre_true_si_el_servidor_lo_confirma():
    cliente, cluster = _cliente_directo()
    assert cliente.vmid_libre(150) is True
    (llamada,) = cluster.llamadas
    assert (llamada.metodo, llamada.ruta, llamada.params) == (
        "GET",
        "/cluster/nextid",
        {"vmid": 150},
    )


def test_vmid_libre_false_si_esta_ocupado():
    cliente, cluster = _cliente_directo()
    cluster.ocupados = {101}
    assert cliente.vmid_libre(101) is False


def test_ca_l03_2_el_400_real_de_proxmox_por_vmid_ocupado_es_false(rsps):
    agregar_error(
        rsps,
        "GET",
        url(A, "/cluster/nextid") + "?vmid=101",
        400,
        "Parameter verification failed.",
        {
            "data": None,
            "errors": {"vmid": "VM 101 already exists"},
            "message": "Parameter verification failed.\n",
        },
    )
    assert _cliente_http(A).vmid_libre(101) is False


@pytest.mark.parametrize(
    "error",
    [
        ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE),
        ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE),
        ErrorProxLaunch(CodigoError.SESION_EXPIRADA),
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE),
        ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "otro"}),
        ErrorProxLaunch(CodigoError.DESCONOCIDO),
    ],
)
def test_ca_l03_3_vmid_libre_propaga_cualquier_otro_error_y_nunca_dice_libre(error):
    cliente, cluster = _cliente_directo()
    cluster.regla("GET", r"nextid", error)
    with pytest.raises(ErrorProxLaunch) as exc:
        cliente.vmid_libre(150)
    assert exc.value.codigo == error.codigo


# --- vms_visibles ---------------------------------------------------------------------------


def test_vms_visibles_lista_las_maquinas_con_nombre_vmid_y_nodo():
    cliente, cluster = _cliente_directo()
    cluster.agregar_vm(105, "pve2", "web-01")
    cluster.visibles_extra = [{"vmid": "200", "name": "ct", "node": "pve1", "type": "lxc"}]
    visibles = {v.vmid: v for v in cliente.vms_visibles()}
    assert (visibles[105].nombre, visibles[105].nodo, visibles[105].tipo) == (
        "web-01",
        "pve2",
        "qemu",
    )
    assert visibles[200].tipo == "lxc"
    (llamada,) = cluster.llamadas
    assert llamada.params == {"type": "vm"}


def test_vms_visibles_ignora_entradas_sin_vmid_y_respuestas_que_no_son_lista():
    cliente, cluster = _cliente_directo()
    cluster.regla("GET", r"resources", lambda ll: [{"name": "sin-id"}, "basura", {"vmid": "7"}])
    assert [v.vmid for v in cliente.vms_visibles()] == [7]
    cluster.reglas.clear()
    cluster.regla("GET", r"resources", lambda ll: {"no": "lista"})
    assert cliente.vms_visibles() == []


# --- estado_actual_vm -----------------------------------------------------------------------


def test_estado_actual_vm_devuelve_status_y_lock():
    cliente, cluster = _cliente_directo()
    cluster.agregar_vm(100, "pve1", "x", status="running", extra={"lock": "backup"})
    estado = cliente.estado_actual_vm("pve1", 100)
    assert estado["status"] == "running"
    assert estado["lock"] == "backup"
    assert cluster.llamadas[0].ruta == "/nodes/pve1/qemu/100/status/current"


def test_estado_actual_vm_con_respuesta_inesperada_es_error_desconocido():
    cliente, cluster = _cliente_directo()
    cluster.regla("GET", r"status/current", lambda ll: "no es un dict")
    with pytest.raises(ErrorProxLaunch) as exc:
        cliente.estado_actual_vm("pve1", 100)
    assert exc.value.codigo == CodigoError.DESCONOCIDO


def test_los_segmentos_de_ruta_se_codifican():
    cliente, cluster = _cliente_directo()
    cluster.agregar_vm(100, "pve1", "x")
    cliente.estado_actual_vm("pve1/../../x", 100)
    ruta = cluster.llamadas[0].ruta
    assert ruta == "/nodes/pve1%2F..%2F..%2Fx/qemu/100/status/current"  # no altera la ruta


# --- eliminar_vm ------------------------------------------------------------------------------


def test_ca_l18_5_eliminar_vm_envia_delete_con_los_parametros_en_la_consulta():
    cliente, cluster = _cliente_directo()
    cluster.agregar_vm(100, "pve1", "x")
    upid = cliente.eliminar_vm("pve1", 100)
    assert upid == upid_de("pve1", 100, "qmdestroy")
    (llamada,) = cluster.llamadas
    assert (llamada.metodo, llamada.ruta) == ("DELETE", "/nodes/pve1/qemu/100")
    assert llamada.params == {"destroy-unreferenced-disks": 1, "purge": 0}
    assert llamada.datos is None  # nada en el cuerpo (LAB-L05)


def test_ca_l18_5_extremo_a_extremo_los_parametros_viajan_en_la_url_y_el_cuerpo_va_vacio(rsps):
    rsps.delete(url(A, "/nodes/pve1/qemu/100"), json={"data": upid_de("pve1", 100, "qmdestroy")})
    _cliente_http(A).eliminar_vm("pve1", 100)
    (llamada,) = rsps.calls
    consulta = parse_qs(urlsplit(llamada.request.url).query)
    assert consulta == {"destroy-unreferenced-disks": ["1"], "purge": ["0"]}
    assert not llamada.request.body


@pytest.mark.parametrize("respuesta", [None, "", 5, "no-es-upid", {"upid": "x"}])
def test_eliminar_vm_exige_un_upid_valido(respuesta):
    cliente, cluster = _cliente_directo()
    cluster.regla("DELETE", r"qemu/100$", lambda ll: respuesta)
    with pytest.raises(ErrorProxLaunch) as exc:
        cliente.eliminar_vm("pve1", 100)
    assert exc.value.codigo == CodigoError.UPID_INVALIDO


def test_ca_l18_6_un_596_en_el_delete_no_prueba_otro_host_ni_reintenta(rsps):
    agregar_error(rsps, "DELETE", url(A, "/nodes/pve1/qemu/100"), 596, "timeout")
    rsps.delete(url(B, "/nodes/pve1/qemu/100"), json={"data": upid_de("pve1", 100, "qmdestroy")})
    with pytest.raises(ErrorProxLaunch) as exc:
        _cliente_http(A, B).eliminar_vm("pve1", 100)
    assert exc.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert exc.value.params.get("incierto") == "1"
    assert len(rsps.calls) == 1  # el segundo host no se contactó


def test_ca_l18_6_una_conexion_abortada_en_el_delete_tampoco_hace_failover(rsps):
    rsps.add(
        "DELETE",
        url(A, "/nodes/pve1/qemu/100"),
        body=requests.exceptions.ConnectionError("Connection aborted"),
    )
    with pytest.raises(ErrorProxLaunch) as exc:
        _cliente_http(A, B).eliminar_vm("pve1", 100)
    assert exc.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert len(rsps.calls) == 1


# --- Traductor ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Sys.Modify for modifying tag: proxlaunch",
        "Sys.Modify for modifying tags 'lote-abcd1234'",
        "Permission check failed (/, Sys.Modify for modifying tag 'proxlaunch')",
        "sys.modify for modifying tag",
    ],
)
def test_e_l15_el_403_de_etiquetas_se_traduce_a_etiqueta_rechazada(texto):
    error = traducir_http(403, texto, json.dumps({"data": None, "message": texto}))
    assert error.codigo == CodigoError.ETIQUETA_RECHAZADA


def test_e_l15_un_403_de_permiso_normal_sigue_siendo_permiso_insuficiente():
    texto = "Permission check failed (/vms/100, VM.Allocate)"
    error = traducir_http(403, texto, json.dumps({"data": None, "message": texto}))
    assert error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert error.params["privilegio"] == "VM.Allocate"


def test_el_texto_de_etiquetas_solo_cuenta_con_estado_403():
    error = traducir_http(500, "Sys.Modify for modifying tag", "")
    assert error.codigo != CodigoError.ETIQUETA_RECHAZADA


@pytest.mark.parametrize("estado", [595, 596, 597])
def test_los_estados_595_596_597_en_una_lectura_son_nodo_no_disponible(estado):
    error = traducir_http(estado, "x", "", nodo="pve2")
    assert error.codigo == CodigoError.NODO_NO_DISPONIBLE
    assert error.params == {"nodo": "pve2", "estado_http": str(estado)}


@pytest.mark.parametrize("estado", [595, 596, 597])
def test_ca_l15_1_un_post_con_595_596_597_es_envio_incierto_y_no_se_reenvia(rsps, estado):
    agregar_error(rsps, "POST", url(A, "/nodes/pve1/qemu"), estado, "error")
    rsps.post(url(B, "/nodes/pve1/qemu"), json={"data": "UPID:pve1:1:2:3:qmcreate:100:u@pam:"})
    with pytest.raises(ErrorProxLaunch) as exc:
        _cliente_http(A, B).crear_vm("pve1", {"vmid": "100", "name": "x"})
    assert exc.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert exc.value.params["incierto"] == "1"
    assert len(rsps.calls) == 1


def test_el_cluster_simulado_por_http_atiende_las_rutas_del_lote(rsps):
    cluster = Cluster()
    cluster.ocupados = {101}
    instalar_http(rsps, cluster, A)
    cliente = _cliente_http(A)
    assert cliente.vmid_libre(100) is True
    assert cliente.vmid_libre(101) is False
    assert Http(500).estado == 500
