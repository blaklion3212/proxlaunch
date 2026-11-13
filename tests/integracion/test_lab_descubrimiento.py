"""Descubrimiento real: versión, topología, nodos, storages y bridges de PVE 9.2.

Derivadas de RF-09, RF-11 y CA-11.x. Se contrastan con la verdad independiente que da
``pvesh``/``pvesm`` en el propio laboratorio.
"""

from __future__ import annotations

import json

import pytest

from proxlaunch.nucleo.modelos.conexion import CredencialContrasena, MetodoAuth
from proxlaunch.nucleo.servicios.conexion import permisos_faltantes_detalle
from proxlaunch.nucleo.servicios.descubrimiento import descubrir, descubrir_nodo

from . import apoyo_lab as lab

pytestmark = pytest.mark.integracion

GIB = 1024**3


def test_version_92_y_capacidades(sesion_plc):
    assert sesion_plc.version.texto.startswith("9.2.")
    assert (sesion_plc.version.mayor, sesion_plc.version.menor) == (9, 2)


def test_servidor_individual_no_es_cluster(sesion_plc):
    inv = descubrir(sesion_plc)
    assert inv.topologia.es_cluster is False
    assert inv.topologia.nombre_cluster is None
    assert [n.nombre for n in inv.topologia.nodos] == [lab.NODO]
    assert inv.topologia.nodos[0].en_linea is True
    assert inv.errores_por_nodo == {}


def test_nodo_trae_memoria_y_cpus_con_sys_audit(sesion_plc):
    nodo = descubrir(sesion_plc).topologia.nodos[0]
    assert nodo.cpus == 4
    assert nodo.mem_libre_mib is not None
    assert 0 < nodo.mem_libre_mib <= 6 * 1024  # el laboratorio tiene 6 GiB


def test_storages_con_images_y_sus_tipos(sesion_plc):
    inv = descubrir(sesion_plc)
    por_id = {s.id: s for s in inv.storages[lab.NODO]}
    assert set(por_id) == {"local", "lab-lvmthin"}
    local, thin = por_id["local"], por_id["lab-lvmthin"]
    assert (local.tipo, thin.tipo) == ("dir", "lvmthin")
    assert "images" in local.contenido and "images" in thin.contenido
    assert local.es_thin is False and thin.es_thin is True
    assert not local.compartido and not thin.compartido
    assert local.activo and thin.activo


def test_espacio_de_los_storages_coincide_con_pvesm(sesion_plc):
    inv = descubrir(sesion_plc)
    real = {e["storage"]: e for e in lab.pvesh_json("get", f"/nodes/{lab.NODO}/storage")}
    for s in inv.storages[lab.NODO]:
        assert s.total_bytes == int(real[s.id]["total"])
        # El libre de `local` cambia unos KiB entre lecturas: tolerancia de 64 MiB.
        assert abs(s.libre_bytes - int(real[s.id]["avail"])) < 64 * 1024 * 1024
    thin = next(s for s in inv.storages[lab.NODO] if s.id == "lab-lvmthin")
    assert 55 * GIB < thin.total_bytes < 64 * GIB


def test_bridges_solo_bridge_y_vlan_aware_correcto(sesion_plc):
    inv = descubrir(sesion_plc)
    bridges = {b.nombre: b for b in inv.bridges[lab.NODO]}
    assert set(bridges) == {"vmbr0", "vmbr1"}  # la NIC de gestión (eth) se filtra
    assert bridges["vmbr0"].tipo == "bridge" and bridges["vmbr1"].tipo == "bridge"
    assert bridges["vmbr0"].vlan_aware is False
    assert bridges["vmbr1"].vlan_aware is True


def test_la_interfaz_de_gestion_existe_pero_no_es_bridge(sesion_plc):
    todas = sesion_plc.cliente.bridges(lab.NODO)  # sin filtrar
    tipos = {b.nombre: b.tipo for b in todas}
    assert tipos["vmbr0"] == "bridge"
    assert any(t != "bridge" for t in tipos.values())


def test_proximo_vmid_coincide_con_cluster_nextid(sesion_plc):
    esperado = int(lab.pvesh_json("get", "/cluster/nextid"))
    assert descubrir(sesion_plc).proximo_vmid == esperado


def test_descubrir_nodo_individual(sesion_plc):
    storages, bridges = descubrir_nodo(sesion_plc, lab.NODO)
    assert {s.id for s in storages} == {"local", "lab-lvmthin"}
    assert {b.nombre for b in bridges} == {"vmbr0", "vmbr1"}


def test_rol_completo_no_genera_aviso_de_permisos(sesion_plc):
    assert permisos_faltantes_detalle(sesion_plc) == []
    assert sesion_plc.avisos == []


def test_permisos_reales_incluyen_las_rutas_que_el_codigo_comprueba(sesion_plc):
    permisos = sesion_plc.cliente.permisos()
    assert "/" in permisos
    assert set(lab.PRIVILEGIOS_ROL) <= set(permisos["/"])
    assert all(v == 1 for v in permisos["/"].values())  # propagate=1 en la ACL de `/`


def test_descubrir_como_root_pam_tambien_funciona(entorno):
    p = lab.perfil(MetodoAuth.CONTRASENA, "root", realm="pam")
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(
        p, CredencialContrasena("root", "pam", lab.secreto("root_pam.pass"))
    )
    try:
        inv = descubrir(s)
        assert inv.topologia.es_cluster is False
        assert {st.id for st in inv.storages[lab.NODO]} == {"local", "lab-lvmthin"}
        assert permisos_faltantes_detalle(s) == []
    finally:
        entorno.servicio.cerrar_sesion(s)


def test_cluster_status_real_de_un_nodo_individual_solo_trae_el_nodo(sesion_plc):
    # Verdad independiente (root por ssh): sin clúster no hay entrada type=cluster.
    real = lab.pvesh_json("get", "/cluster/status")
    assert [e["type"] for e in real] == ["node"]
    assert json.dumps(real)  # serializable
