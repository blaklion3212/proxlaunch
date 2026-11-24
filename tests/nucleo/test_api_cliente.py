"""ClienteProxmox: lectura de los datos de la API, rutas y creación (RF-09 a RF-12, RF-19, RF-20).
Transporte falso con respuestas simuladas de ``tests/datos/respuestas``."""

import logging

import pytest

from proxlaunch.nucleo.api.cliente import LINEAS_LOG_TAREA, ClienteProxmox
from proxlaunch.nucleo.api.transporte import TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo_api import (
    HUELLA_A,
    TOKEN_ID,
    TOKEN_SECRETO,
    UPID,
    TransporteFalso,
    agregar_error,
    cargar,
    dato,
    url,
)

GIB = 1024**3


def _cliente(t: TransporteFalso) -> ClienteProxmox:
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken

    auth = AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO))
    return ClienteProxmox(t, auth, RelojSimulado())


# --- RF-09: versión ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "mayor", "menor", "parche"),
    [
        pytest.param("8.2.4", 8, 2, 4, id="CA-09.1-8.2.4"),
        pytest.param("7.4-17", 7, 4, 17, id="CA-09.2-7.4-17"),
        pytest.param("9.2", 9, 2, 0, id="9.2-sin-parche"),
        pytest.param("10.0", 10, 0, 0, id="CA-09.3-version-futura"),
    ],
)
def test_rf_09_version_se_interpreta(texto, mayor, menor, parche):
    v = _cliente(TransporteFalso().en("GET", "/version", {"version": texto})).version()
    assert (v.texto, v.mayor, v.menor, v.parche) == (texto, mayor, menor, parche)


@pytest.mark.parametrize("data", [{"version": "texto raro"}, {}, None, {"version": ""}])
def test_ca_09_5_formato_inesperado_usa_la_version_minima_y_avisa(data, registros):
    v = _cliente(TransporteFalso().en("GET", "/version", data)).version()
    assert (v.mayor, v.menor) == (8, 4)
    avisos = [r for r in registros if r.levelno == logging.WARNING]
    assert avisos, "debe registrarse una advertencia"


def test_ca_09_1_version_valida_no_registra_advertencias(registros):
    _cliente(TransporteFalso().en("GET", "/version", {"version": "8.2.4"})).version()
    assert not [r for r in registros if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("ver", ["9.2", "8.0"])
def test_rnf_05_version_con_respuestas_de_8_0_y_9_2(ver):
    t = TransporteFalso().en("GET", "/version", dato(ver, "version.json"))
    assert _cliente(t).version().mayor == int(ver.split(".")[0])


# --- RF-10: topología -------------------------------------------------------------------


def test_ca_10_1_cluster_de_tres_nodos():
    t = TransporteFalso().en("GET", "/cluster/status", dato("9.2", "cluster_status.json"))
    topologia = _cliente(t).estado_cluster()
    assert topologia.es_cluster is True
    assert topologia.nombre_cluster == "lab"
    assert [n.nombre for n in topologia.nodos] == ["pve1", "pve2", "pve3"]
    assert all(n.en_linea for n in topologia.nodos)


def test_ca_10_2_servidor_individual():
    t = TransporteFalso().en(
        "GET", "/cluster/status", dato("9.2", "cluster_status_individual.json")
    )
    topologia = _cliente(t).estado_cluster()
    assert topologia.es_cluster is False
    assert topologia.nombre_cluster is None
    assert len(topologia.nodos) == 1


def test_ca_10_3_nodo_con_online_0_queda_sin_conexion():
    t = TransporteFalso().en(
        "GET", "/cluster/status", dato("9.2", "cluster_status_nodo_offline.json")
    )
    estados = {n.nombre: n.en_linea for n in _cliente(t).estado_cluster().nodos}
    assert estados == {"pve1": True, "pve2": False, "pve3": True}


@pytest.mark.parametrize("ver", ["9.2", "8.0"])
def test_rnf_05_topologia_con_respuestas_de_8_0_y_9_2(ver):
    t = TransporteFalso().en("GET", "/cluster/status", dato(ver, "cluster_status.json"))
    assert len(_cliente(t).estado_cluster().nodos) == 3


@pytest.mark.parametrize("data", [None, "x", {}, []])
def test_cluster_status_inesperado_no_rompe(data):
    topologia = _cliente(TransporteFalso().en("GET", "/cluster/status", data)).estado_cluster()
    assert topologia.es_cluster is False
    assert topologia.nodos == ()


# --- RF-11: nodos, storages, bridges, nextid --------------------------------------------


def test_ca_11_1_nodos_con_estado_memoria_y_cpus():
    nodos = _cliente(TransporteFalso().en("GET", "/nodes", dato("9.2", "nodes.json"))).nodos()
    por_nombre = {n.nombre: n for n in nodos}
    assert set(por_nombre) == {"pve1", "pve2", "pve3"}
    assert por_nombre["pve1"].en_linea is True
    assert por_nombre["pve1"].mem_libre_mib == 12 * 1024  # 16 GiB - 4 GiB
    assert por_nombre["pve1"].cpus == 8


def test_ca_11_8_nodo_offline_y_sin_datos_de_memoria():
    t = TransporteFalso().en("GET", "/nodes", dato("9.2", "nodes_nodo_offline.json"))
    por_nombre = {n.nombre: n for n in _cliente(t).nodos()}
    assert por_nombre["pve2"].en_linea is False
    assert por_nombre["pve2"].mem_libre_mib is None
    assert por_nombre["pve2"].cpus is None


def test_sin_sys_audit_memoria_y_cpu_son_none():
    t = TransporteFalso().en("GET", "/nodes", dato("9.2", "nodes_sin_sys_audit.json"))
    (nodo,) = _cliente(t).nodos()
    assert nodo.en_linea is True
    assert (nodo.mem_libre_mib, nodo.cpus) == (None, None)


def test_nodos_ignora_entradas_invalidas():
    t = TransporteFalso().en("GET", "/nodes", [{"status": "online"}, "x", {"node": "ok"}])
    assert [n.nombre for n in _cliente(t).nodos()] == ["ok"]


def test_ca_11_2_storages_se_leen_todos_con_su_contenido():
    t = TransporteFalso().en("GET", "/nodes/pve1/storage", dato("9.2", "storage.json"))
    por_id = {s.id: s for s in _cliente(t).storages("pve1")}
    assert por_id["local"].contenido == {"iso", "backup", "vztmpl"}
    assert por_id["local-lvm"].tipo == "lvmthin"
    assert por_id["local-lvm"].contenido == {"images", "rootdir"}
    assert por_id["local-lvm"].libre_gib == 150.0
    assert por_id["local-lvm"].es_thin is True
    assert por_id["nfs1"].compartido is True
    assert por_id["nfs1"].libre_gib == 500.0


@pytest.mark.parametrize("storage_id", ["apagado", "deshabilitado"])
def test_ca_11_3_storage_inactivo_o_deshabilitado(storage_id):
    t = TransporteFalso().en("GET", "/nodes/pve1/storage", dato("9.2", "storage.json"))
    por_id = {s.id: s for s in _cliente(t).storages("pve1")}
    assert por_id[storage_id].activo is False
    assert por_id["local-lvm"].activo is True


def test_ca_11_4_avail_se_redondea_hacia_abajo_a_un_decimal():
    t = TransporteFalso().en("GET", "/nodes/pve1/storage", dato("9.2", "storage.json"))
    por_id = {s.id: s for s in _cliente(t).storages("pve1")}
    assert por_id["fraccion"].libre_gib == 10.9  # 10.99 GiB, nunca 11.0


def test_storage_sin_active_ni_enabled_se_considera_activo():
    t = TransporteFalso().en(
        "GET", "/nodes/pve1/storage", [{"storage": "x", "type": "dir", "content": "images"}]
    )
    assert _cliente(t).storages("pve1")[0].activo is True


def test_ca_11_5_bridges_se_leen_con_su_tipo():
    t = TransporteFalso().en("GET", "/nodes/pve1/network", dato("9.2", "network.json"))
    por_nombre = {b.nombre: b for b in _cliente(t).bridges("pve1")}
    assert por_nombre["vmbr0"].tipo == "bridge"
    assert por_nombre["vmbr0"].vlan_aware is True
    assert por_nombre["vmbr1"].tipo == "OVSBridge"
    assert por_nombre["eno1"].tipo == "eth"


@pytest.mark.parametrize(("valor", "esperado"), [("101", 101), (101, 101), ("9999999", 9999999)])
def test_ca_11_6_nextid_devuelve_entero(valor, esperado):
    t = TransporteFalso().en("GET", "/cluster/nextid", valor)
    assert _cliente(t).proximo_vmid() == esperado
    assert t.llamadas[0].params is None


@pytest.mark.parametrize("valor", [None, "abc", {}])
def test_nextid_inesperado_es_desconocido(valor):
    t = TransporteFalso().en("GET", "/cluster/nextid", valor)
    with pytest.raises(ErrorProxLaunch) as e:
        _cliente(t).proximo_vmid()
    assert e.value.codigo == CodigoError.DESCONOCIDO


def test_ca_13_2_nextid_con_vmid_sugerido_lo_envia_en_la_consulta():
    t = TransporteFalso().en("GET", "/cluster/nextid", "100")
    assert _cliente(t).proximo_vmid(100) == 100
    assert t.llamadas[0].params == {"vmid": 100}


def test_ca_13_2_vmid_ocupado_se_propaga_como_error():
    t = TransporteFalso().en(
        "GET", "/cluster/nextid", ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "100"})
    )
    with pytest.raises(ErrorProxLaunch) as e:
        _cliente(t).proximo_vmid(100)
    assert e.value.codigo == CodigoError.VMID_OCUPADO


def test_a_8_v_03_nextid_400_con_la_red_simulada(rsps):
    agregar_error(
        rsps,
        "GET",
        url("10.0.0.1", "/cluster/nextid") + "?vmid=100",
        400,
        "Parameter verification failed.",
        dato_completo("error_vmid_ocupado_nextid_400.json"),
    )
    cliente = _cliente_http()
    with pytest.raises(ErrorProxLaunch) as e:
        cliente.proximo_vmid(100)
    assert e.value.codigo == CodigoError.VMID_OCUPADO
    assert e.value.params["vmid"] == "100"


# --- RF-12: permisos --------------------------------------------------------------------


def test_permisos_devuelve_ruta_privilegio_valor():
    t = TransporteFalso().en(
        "GET", "/access/permissions", dato("9.2", "permisos_sin_vm_allocate.json")
    )
    permisos = _cliente(t).permisos()
    assert permisos["/"]["Sys.Audit"] == 1
    assert "VM.Allocate" not in permisos["/vms"]
    assert permisos["/storage"]["Datastore.AllocateSpace"] == 1


@pytest.mark.parametrize("data", [None, [], "x"])
def test_permisos_con_respuesta_inesperada_es_vacio(data):
    assert _cliente(TransporteFalso().en("GET", "/access/permissions", data)).permisos() == {}


# --- RF-19 / RF-20: creación y tarea ----------------------------------------------------


def test_crear_vm_devuelve_el_upid_y_envia_los_parametros():
    t = TransporteFalso().en("POST", "/nodes/pve1/qemu", UPID)
    assert _cliente(t).crear_vm("pve1", {"vmid": "100", "name": "a"}) == UPID
    llamada = t.llamadas[0]
    assert (llamada.metodo, llamada.ruta) == ("POST", "/nodes/pve1/qemu")
    assert llamada.datos == {"vmid": "100", "name": "a"}


@pytest.mark.parametrize(
    "respuesta",
    [None, "", "no-es-upid", "UPID:", {"upid": UPID}, 123, [UPID], "xUPID:pve1:1:2:3:q:100:r@pam:"],
)
def test_ca_19_5_respuesta_sin_upid_valido(respuesta):
    t = TransporteFalso().en("POST", "/nodes/pve1/qemu", respuesta)
    with pytest.raises(ErrorProxLaunch) as e:
        _cliente(t).crear_vm("pve1", {"vmid": "100"})
    assert e.value.codigo == CodigoError.UPID_INVALIDO


def test_ca_20_1_estado_de_tarea_en_curso_y_terminada():
    ruta = f"/nodes/pve1/tasks/{UPID}/status"
    t = TransporteFalso().en("GET", ruta, dato("9.2", "tarea_status_running.json"))
    en_curso = _cliente(t).estado_tarea("pve1", UPID)
    assert (en_curso.estado, en_curso.exitstatus, en_curso.terminada) == ("running", None, False)
    t.en("GET", ruta, dato("9.2", "tarea_status_ok.json"))
    fin = _cliente(t).estado_tarea("pve1", UPID)
    assert (fin.estado, fin.exitstatus, fin.terminada) == ("stopped", "OK", True)


def test_la_ruta_de_tarea_conserva_los_caracteres_del_upid():
    t = TransporteFalso().en("GET", f"/nodes/pve1/tasks/{UPID}/status", {"status": "running"})
    _cliente(t).estado_tarea("pve1", UPID)  # si la ruta cambiara, el transporte falso fallaría


@pytest.mark.parametrize("data", [None, {}, [], "x"])
def test_estado_de_tarea_inesperado_es_desconocido(data):
    t = TransporteFalso().en("GET", f"/nodes/pve1/tasks/{UPID}/status", data)
    with pytest.raises(ErrorProxLaunch) as e:
        _cliente(t).estado_tarea("pve1", UPID)
    assert e.value.codigo == CodigoError.DESCONOCIDO


def test_ca_20_5_log_de_la_tarea_son_lineas_de_texto():
    ruta = f"/nodes/pve1/tasks/{UPID}/log"
    t = TransporteFalso().en("GET", ruta, dato("9.2", "tarea_log.json"))
    lineas = _cliente(t).log_tarea("pve1", UPID)
    assert lineas == [
        "TASK WARNINGS: 1",
        "WARN: no se pudo aplicar el parametro X",
        "TASK WARNINGS: 1",
    ]
    assert t.llamadas[0].params == {"start": 0, "limit": LINEAS_LOG_TAREA}
    assert LINEAS_LOG_TAREA > 50  # la API devuelve solo 50 por defecto


def test_log_de_tarea_inesperado_es_lista_vacia():
    t = TransporteFalso().en("GET", f"/nodes/pve1/tasks/{UPID}/log", "x")
    assert _cliente(t).log_tarea("pve1", UPID) == []


def test_ca_20_3_config_de_la_vm_existente():
    t = TransporteFalso().en("GET", "/nodes/pve1/qemu/100/config", dato("9.2", "qemu_config.json"))
    config = _cliente(t).config_vm("pve1", 100)
    assert config["name"] == "srv-web-01"


def test_ca_20_3_config_de_vm_inexistente_es_none():
    t = TransporteFalso().en(
        "GET", "/nodes/pve1/qemu/100/config", ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE)
    )
    assert _cliente(t).config_vm("pve1", 100) is None


def test_ca_20_3_config_de_vm_inexistente_con_el_texto_real_de_proxmox(rsps):
    agregar_error(
        rsps,
        "GET",
        url("10.0.0.1", "/nodes/pve1/qemu/100/config"),
        500,
        "Configuration file 'nodes/pve1/qemu-server/100.conf' does not exist",
    )
    assert _cliente_http().config_vm("pve1", 100) is None


def test_config_sin_permiso_se_propaga():
    t = TransporteFalso().en(
        "GET",
        "/nodes/pve1/qemu/100/config",
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "VM.Audit"}),
    )
    with pytest.raises(ErrorProxLaunch) as e:
        _cliente(t).config_vm("pve1", 100)
    assert e.value.codigo == CodigoError.PERMISO_INSUFICIENTE


# --- RNF-16: rutas seguras ---------------------------------------------------------------


def test_rnf_16_un_nombre_de_nodo_no_altera_la_ruta():
    t = TransporteFalso().en("GET", "/nodes/a%2Fb%3Fx/storage", [])
    _cliente(t).storages("a/b?x")  # el transporte falso falla si la ruta no está codificada


def test_el_cliente_es_el_unico_que_fija_el_autenticador():
    t = TransporteFalso()
    cliente = _cliente(t)
    t.en("GET", "/version", {"version": "9.2.1"})
    cliente.version()
    assert t.llamadas[0].cabeceras["Authorization"].startswith("PVEAPIToken=")


# --- Apoyo local -------------------------------------------------------------------------


def dato_completo(nombre):
    return cargar("9.2", nombre)


def _cliente_http() -> ClienteProxmox:
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken

    transporte = TransporteHttp(["10.0.0.1"], 8006, huellas={"10.0.0.1": HUELLA_A})
    auth = AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO))
    return ClienteProxmox(transporte, auth, RelojSimulado())
