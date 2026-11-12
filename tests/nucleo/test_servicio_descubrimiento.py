"""Descubrimiento del inventario (RF-10, RF-11, A-6, RNF-12). Transporte falso y, para los
códigos 403/595 reales, HTTP simulado con ``responses``."""

import time

import pytest

from proxlaunch.nucleo.api.transporte import TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.servicios.conexion import CodigoAviso
from proxlaunch.nucleo.servicios.descubrimiento import descubrir, descubrir_nodo

from .apoyo_api import (
    HUELLA_A,
    TransporteFalso,
    agregar_error,
    crear_sesion,
    dato,
    rutas_inventario,
    url,
)

NODOS = ("pve1", "pve2", "pve3")


def _inventario(nodos="nodes.json", ver="9.2", cambios=None):
    t = TransporteFalso()
    rutas_inventario(t, ver, nodos)
    for (metodo, ruta), valor in (cambios or {}).items():
        t.en(metodo, ruta, valor)
    return t


# --- RF-10: topología -------------------------------------------------------------------


def test_ca_10_1_cluster_de_tres_nodos():
    inv = descubrir(crear_sesion(_inventario()))
    assert inv.topologia.es_cluster is True
    assert inv.topologia.nombre_cluster == "lab"
    assert [n.nombre for n in inv.topologia.nodos] == list(NODOS)


def test_ca_10_2_servidor_individual():
    t = TransporteFalso()
    t.en("GET", "/cluster/status", dato("9.2", "cluster_status_individual.json"))
    t.en("GET", "/nodes", dato("9.2", "nodes_individual.json"))
    t.en("GET", "/cluster/nextid", "101")
    t.en("GET", "/nodes/pve1/storage", dato("9.2", "storage.json"))
    t.en("GET", "/nodes/pve1/network", dato("9.2", "network.json"))
    inv = descubrir(crear_sesion(t))
    assert inv.topologia.es_cluster is False
    assert inv.topologia.nombre_cluster is None
    assert [n.nombre for n in inv.topologia.nodos] == ["pve1"]


def test_ca_10_3_nodo_offline_aparece_sin_conexion_y_no_se_consulta():
    t = _inventario("nodes_nodo_offline.json")
    inv = descubrir(crear_sesion(t))
    estados = {n.nombre: n.en_linea for n in inv.topologia.nodos}
    assert estados == {"pve1": True, "pve2": False, "pve3": True}
    assert t.llamadas_a("GET", "/nodes/pve2/storage") == []
    assert t.llamadas_a("GET", "/nodes/pve2/network") == []
    assert inv.storages["pve2"] == ()
    assert inv.errores_por_nodo == {}


def test_a_6_403_en_cluster_status_degrada_la_topologia_con_aviso():
    permiso = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "Sys.Audit", "ruta": "/"}
    )
    sesion = crear_sesion(_inventario(cambios={("GET", "/cluster/status"): permiso}))
    inv = descubrir(sesion)
    assert inv.topologia.nombre_cluster is None
    assert [n.nombre for n in inv.topologia.nodos] == list(NODOS)
    assert [(a.codigo, a.params) for a in sesion.avisos] == [
        (CodigoAviso.TOPOLOGIA_DEGRADADA, {"nodos": "3"})
    ]
    assert len(inv.storages["pve1"]) > 0  # la conexión sigue siendo utilizable


def test_a_6_el_aviso_de_topologia_no_se_duplica_al_actualizar():
    permiso = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {})
    sesion = crear_sesion(_inventario(cambios={("GET", "/cluster/status"): permiso}))
    descubrir(sesion)
    descubrir(sesion)
    assert len(sesion.avisos) == 1


def test_a_6_403_real_sobre_http_degrada_la_topologia(rsps):
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
    from proxlaunch.nucleo.api.cliente import ClienteProxmox
    from proxlaunch.nucleo.modelos.conexion import CredencialToken
    from proxlaunch.nucleo.reloj import RelojSimulado

    host = "10.0.0.1"
    agregar_error(
        rsps,
        "GET",
        url(host, "/cluster/status"),
        403,
        "Permission check failed (/, Sys.Audit)",
    )
    rsps.get(url(host, "/nodes"), json={"data": dato("9.2", "nodes.json")})
    rsps.get(url(host, "/cluster/nextid"), json={"data": "101"})
    for n in NODOS:
        rsps.get(url(host, f"/nodes/{n}/storage"), json={"data": dato("9.2", "storage.json")})
        rsps.get(url(host, f"/nodes/{n}/network"), json={"data": dato("9.2", "network.json")})
    transporte = TransporteHttp([host], 8006, huellas={host: HUELLA_A})
    cliente = ClienteProxmox(
        transporte, AutenticadorToken(CredencialToken("ana@pve!lab", "s")), RelojSimulado()
    )
    sesion = crear_sesion(TransporteFalso())
    sesion.cliente = cliente
    inv = descubrir(sesion)
    assert sesion.avisos[0].codigo == CodigoAviso.TOPOLOGIA_DEGRADADA
    assert len(inv.topologia.nodos) == 3


def test_otro_error_en_cluster_status_no_se_oculta():
    caido = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "timeout")
    with pytest.raises(ErrorProxLaunch) as e:
        descubrir(crear_sesion(_inventario(cambios={("GET", "/cluster/status"): caido})))
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE


# --- RF-11: recursos --------------------------------------------------------------------


def test_ca_11_1_lista_de_nodos_con_su_estado():
    inv = descubrir(crear_sesion(_inventario()))
    assert {n.nombre: n.en_linea for n in inv.topologia.nodos} == dict.fromkeys(NODOS, True)
    assert set(inv.storages) == set(NODOS)
    assert set(inv.bridges) == set(NODOS)


def test_ca_11_2_solo_se_ofrecen_los_storages_con_images():
    inv = descubrir(crear_sesion(_inventario()))
    ids = {s.id for s in inv.storages["pve1"]}
    assert "local" not in ids  # iso,backup,vztmpl
    assert {"local-lvm", "nfs1"} <= ids
    por_id = {s.id: s for s in inv.storages["pve1"]}
    assert (por_id["local-lvm"].tipo, por_id["local-lvm"].libre_gib) == ("lvmthin", 150.0)
    assert (por_id["nfs1"].tipo, por_id["nfs1"].libre_gib) == ("nfs", 500.0)
    assert por_id["nfs1"].compartido is True


def test_ca_11_3_los_storages_inactivos_se_conservan_deshabilitados():
    inv = descubrir(crear_sesion(_inventario()))
    por_id = {s.id: s for s in inv.storages["pve1"]}
    assert por_id["apagado"].activo is False
    assert por_id["deshabilitado"].activo is False
    assert por_id["local-lvm"].activo is True


def test_ca_11_4_libre_en_gib_redondeado_hacia_abajo():
    inv = descubrir(crear_sesion(_inventario()))
    por_id = {s.id: s for s in inv.storages["pve1"]}
    assert por_id["fraccion"].libre_gib == 10.9


def test_ca_11_5_solo_bridge_y_ovsbridge_en_el_selector_de_red():
    inv = descubrir(crear_sesion(_inventario()))
    por_nombre = {b.nombre: b.tipo for b in inv.bridges["pve1"]}
    assert por_nombre == {"vmbr0": "bridge", "vmbr1": "OVSBridge"}


def test_ca_11_6_nextid_prellena_el_vmid():
    assert descubrir(crear_sesion(_inventario())).proximo_vmid == 101


def test_ca_11_7_descubrir_nodo_devuelve_los_recursos_de_ese_nodo():
    t = _inventario()
    t.en("GET", "/nodes/pve3/storage", [
        {"storage": "solo-pve3", "type": "dir", "content": "images", "avail": 1024**3}
    ])  # fmt: skip
    t.en("GET", "/nodes/pve3/network", [{"iface": "vmbr9", "type": "bridge"}])
    storages, bridges = descubrir_nodo(crear_sesion(t), "pve3")
    assert [s.id for s in storages] == ["solo-pve3"]
    assert [b.nombre for b in bridges] == ["vmbr9"]
    assert t.llamadas_a("GET", "/nodes/pve1/storage") == []  # solo se consultó ese nodo


def test_ca_11_8_un_nodo_con_595_queda_sin_conexion_y_el_resto_sigue_utilizable():
    caido = ErrorProxLaunch(
        CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve2", "estado_http": "595"}, "no route to host"
    )
    t = _inventario(cambios={("GET", "/nodes/pve2/storage"): caido})
    inv = descubrir(crear_sesion(t))
    assert set(inv.errores_por_nodo) == {"pve2"}
    assert inv.errores_por_nodo["pve2"].codigo == CodigoError.NODO_NO_DISPONIBLE
    estados = {n.nombre: n.en_linea for n in inv.topologia.nodos}
    assert estados == {"pve1": True, "pve2": False, "pve3": True}
    assert len(inv.storages["pve1"]) > 0
    assert len(inv.storages["pve3"]) > 0
    assert inv.storages["pve2"] == ()


def test_ca_11_8_595_real_sobre_http_marca_el_nodo(rsps):
    host = "10.0.0.1"
    rsps.get(url(host, "/cluster/status"), json={"data": dato("9.2", "cluster_status.json")})
    rsps.get(url(host, "/nodes"), json={"data": dato("9.2", "nodes.json")})
    rsps.get(url(host, "/cluster/nextid"), json={"data": "101"})
    for n in NODOS:
        rsps.get(url(host, f"/nodes/{n}/network"), json={"data": dato("9.2", "network.json")})
        if n == "pve2":
            agregar_error(rsps, "GET", url(host, f"/nodes/{n}/storage"), 595, "no route to host")
        else:
            rsps.get(url(host, f"/nodes/{n}/storage"), json={"data": dato("9.2", "storage.json")})
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
    from proxlaunch.nucleo.api.cliente import ClienteProxmox
    from proxlaunch.nucleo.modelos.conexion import CredencialToken
    from proxlaunch.nucleo.reloj import RelojSimulado

    transporte = TransporteHttp([host], 8006, huellas={host: HUELLA_A})
    sesion = crear_sesion(TransporteFalso())
    sesion.cliente = ClienteProxmox(
        transporte, AutenticadorToken(CredencialToken("ana@pve!lab", "s")), RelojSimulado()
    )
    inv = descubrir(sesion)
    assert inv.errores_por_nodo["pve2"].codigo == CodigoError.NODO_NO_DISPONIBLE
    assert inv.errores_por_nodo["pve2"].params["nodo"] == "pve2"
    assert [n.en_linea for n in inv.topologia.nodos] == [True, False, True]


def test_un_error_de_permisos_en_un_nodo_tambien_lo_deja_registrado():
    sin_permiso = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "SDN.Use"})
    t = _inventario(cambios={("GET", "/nodes/pve3/network"): sin_permiso})
    inv = descubrir(crear_sesion(t))
    assert inv.errores_por_nodo["pve3"].codigo == CodigoError.PERMISO_INSUFICIENTE


def test_ca_11_9_nodo_sin_storage_con_images_queda_vacio():
    t = _inventario(cambios={
        ("GET", "/nodes/pve1/storage"): [{"storage": "local", "type": "dir", "content": "iso"}]
    })  # fmt: skip
    inv = descubrir(crear_sesion(t))
    assert inv.storages["pve1"] == ()
    assert len(inv.bridges["pve1"]) == 2


def test_ca_11_10_actualizar_repite_el_descubrimiento_con_datos_frescos():
    t = _inventario()
    sesion = crear_sesion(t)
    primero = descubrir(sesion)
    t.en("GET", "/cluster/nextid", "150")
    segundo = descubrir(sesion)
    assert (primero.proximo_vmid, segundo.proximo_vmid) == (101, 150)
    assert len(t.llamadas_a("GET", "/nodes")) == 2


def test_la_version_de_la_sesion_va_en_el_inventario():
    sesion = crear_sesion(_inventario(), version=Version("8.0.4", 8, 0, 4))
    assert descubrir(sesion).version.texto == "8.0.4"


def test_sin_sys_audit_la_memoria_y_cpu_de_los_nodos_son_desconocidas():
    t = _inventario("nodes_sin_sys_audit.json")
    t.en("GET", "/cluster/status", dato("9.2", "cluster_status_individual.json"))
    t.en("GET", "/nodes/pve1/storage", dato("9.2", "storage.json"))
    t.en("GET", "/nodes/pve1/network", dato("9.2", "network.json"))
    (nodo,) = descubrir(crear_sesion(t)).topologia.nodos
    assert (nodo.mem_libre_mib, nodo.cpus) == (None, None)


def test_rnf_12_diez_nodos_y_cincuenta_storages_terminan_rapido_y_completos():
    nodos = [
        {"node": f"n{i}", "status": "online", "maxmem": 2 * 1024**3, "mem": 1024**3, "maxcpu": 4}
        for i in range(10)
    ]
    storages = [
        {"storage": f"st{i}", "type": "dir", "content": "images", "avail": 10 * 1024**3}
        for i in range(5)
    ]
    t = TransporteFalso()
    t.en("GET", "/nodes", nodos)
    t.en("GET", "/cluster/status", [{"type": "cluster", "name": "c"}])
    t.en("GET", "/cluster/nextid", "100")

    def _lento(valor):
        def _f(llamada):
            time.sleep(0.01)  # latencia mínima que prueba el paralelismo
            return valor

        return _f

    for i in range(10):
        t.en("GET", f"/nodes/n{i}/storage", _lento(storages))
        t.en("GET", f"/nodes/n{i}/network", _lento([{"iface": "vmbr0", "type": "bridge"}]))
    inicio = time.monotonic()
    inv = descubrir(crear_sesion(t))
    assert time.monotonic() - inicio < 5
    assert sum(len(v) for v in inv.storages.values()) == 50
    assert inv.errores_por_nodo == {}


@pytest.mark.parametrize(
    "codigo",
    [CodigoError.SESION_EXPIRADA, CodigoError.CREDENCIALES_INVALIDAS],
    ids=["CA-03.3-sesion-expirada", "CA-01.3-credenciales"],
)
def test_ca_03_3_un_error_de_sesion_en_los_nodos_no_se_disfraza_de_nodo_caido(codigo):
    error = ErrorProxLaunch(codigo, {}, "401")
    cambios = {("GET", f"/nodes/{n}/storage"): error for n in NODOS}
    with pytest.raises(ErrorProxLaunch) as e:
        descubrir(crear_sesion(_inventario(cambios=cambios)))
    assert e.value.codigo == codigo


def test_ca_03_1_con_el_ticket_en_margen_los_hilos_del_descubrimiento_renuevan_una_sola_vez(
    reloj, respuesta
):
    from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket
    from proxlaunch.nucleo.modelos.conexion import Ticket

    t = _inventario()
    t.en("POST", "/access/ticket", respuesta("9.2", "ticket_renovado.json")["data"])
    auth = AutenticadorTicket(Ticket("PVE:root@pam:VIEJO::s", "A:viejo", "root@pam", 0.0), reloj)
    reloj.avanzar(110 * 60)
    inv = descubrir(crear_sesion(t, auth=auth, reloj=reloj))
    assert len(t.llamadas_a("POST", "/access/ticket")) == 1
    assert inv.errores_por_nodo == {}
