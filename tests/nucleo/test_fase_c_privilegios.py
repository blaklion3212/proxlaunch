"""Fase C (0.8.0): privilegios por versión, capacidades y disponibilidad de las opciones.

Cubre RF-C0.3 (CA-C0.3.1 a CA-C0.3.3), RF-C0.4 (CA-C0.4.1), RF-C5.1 (CA-C5.1.1 a CA-C5.1.3),
RF-C5.2 (CA-C5.2.1 a CA-C5.2.3, filas de «Qué puedo hacer»), DC-1 (versión mínima 8.0) y DC-2
(rol sin cambios, ``SDN.Use`` y ``SDN.Audit`` opcionales y ``VM.Firewall`` nunca). Las pruebas de
los textos de esas filas están en ``tests/interfaz/test_fase_c_textos.py``.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from proxlaunch.nucleo.capacidades import (
    TABLA,
    Capacidades,
    Funcion,
    capacidades_para,
    interpretar_version,
)
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.firewall.modelos import FirewallMV, Politica
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.vm import Disco, OrigenSO
from proxlaunch.nucleo.opciones.disponibilidad_c import disponibilidad_fase_c
from proxlaunch.nucleo.opciones.modelos import OpcionC
from proxlaunch.nucleo.origen.capacidades_origen import (
    Disponibilidad,
    Via,
    calcular_capacidades,
    vias_de_origen,
)
from proxlaunch.nucleo.origen.permisos import (
    PRIVILEGIOS_OPCIONALES,
    PRIVILEGIOS_SDN_OPCIONALES,
    ROL_PROXLAUNCH,
    estado_privilegio,
    estado_sdn_fuera_de_local,
    privilegios_agente,
    privilegios_de_peticion,
    privilegios_opcionales,
    ruta_sdn,
)
from proxlaunch.nucleo.servicios.conexion import (
    PERMISOS_POR_RUTA,
    PRIVILEGIOS_REQUERIDOS,
    CodigoAviso,
    permisos_faltantes_detalle,
)

from .apoyo_api import TransporteFalso, crear_sesion
from .apoyo_lote import definicion, plantilla
from .apoyo_mvp4 import ROL_MVP4, inv_origen
from .apoyo_mvp4 import permisos as permisos_de

SRC = Path(__file__).resolve().parents[2] / "src" / "proxlaunch"
VERSIONES = [(8, 0), (8, 1), (8, 4), (9, 0), (9, 1), (9, 2)]
V_8 = [(8, 0), (8, 1), (8, 4)]
V_9 = [(9, 0), (9, 1), (9, 2)]


def caps(version: tuple[int, int], forzada: bool = False) -> Capacidades:
    return Capacidades(version=version, forzada=forzada)


def permisos_en(**rutas: dict[str, int]) -> PermisosEfectivos:
    """``permisos_en(vms={"VM.Audit": 1})`` -> ``{"/vms": {...}}`` (ruta con guion bajo = ``/``)."""
    return PermisosEfectivos(rutas={"/" + r.replace("__", "/"): p for r, p in rutas.items()})


def sin(*quitar: str) -> PermisosEfectivos:
    return permisos_de(quitar=quitar)


# --- RF-C5.1: lista de privilegios ---


def test_ca_c5_1_1_el_rol_sigue_con_14_privilegios_sin_repetidos():
    assert len(ROL_PROXLAUNCH) == 14
    assert len(set(ROL_PROXLAUNCH)) == 14


def test_dc_2_el_rol_no_pide_vm_firewall_ni_sdn_audit_y_si_sdn_use():
    assert "VM.Firewall" not in ROL_PROXLAUNCH
    assert "SDN.Audit" not in ROL_PROXLAUNCH  # solo opcional
    assert "SDN.Use" in ROL_PROXLAUNCH


def test_dc_2_ninguna_peticion_ni_ruta_del_codigo_pide_vm_firewall():
    for accion in (
        "upload",
        "download-url",
        "crear_iso",
        "crear_import",
        "clone",
        "config",
        "resize",
    ):
        assert "VM.Firewall" not in privilegios_de_peticion(accion)
    todos = {p for privs in PERMISOS_POR_RUTA.values() for p in privs}
    assert "VM.Firewall" not in todos and "SDN.Audit" not in todos
    for c in (caps(v) for v in VERSIONES):
        assert "VM.Firewall" not in {p.privilegio for p in privilegios_opcionales(c)}
        assert "VM.Firewall" not in privilegios_agente(c)


def test_dc_2_vm_firewall_no_aparece_como_privilegio_en_el_codigo_fuente():
    """Solo se nombra en comentarios o textos que dicen que NO existe; nunca como literal pedido."""
    pedidos = re.compile(r"""["']VM\.Firewall["']""")
    ofensores = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if pedidos.search(p.read_text(encoding="utf-8"))
    ]
    assert ofensores == []


def test_ca_c5_1_2_un_usuario_con_el_rol_de_070_no_recibe_aviso_nuevo_de_privilegios_minimos():
    permisos = {"/": {p: 1 for p in ROL_PROXLAUNCH}}
    sesion = crear_sesion(TransporteFalso().en("GET", "/access/permissions", permisos))
    assert permisos_faltantes_detalle(sesion) == []
    assert [a for a in sesion.avisos if a.codigo == CodigoAviso.PERMISOS_INCOMPLETOS] == []


def test_ca_c5_1_2_los_privilegios_requeridos_siguen_siendo_los_10_de_070():
    assert len(PRIVILEGIOS_REQUERIDOS) == 10
    assert set(PRIVILEGIOS_REQUERIDOS) <= set(ROL_PROXLAUNCH)
    assert PERMISOS_POR_RUTA["/sdn/zones/localnetwork"] == ("SDN.Use",)
    assert PERMISOS_POR_RUTA["/"] == ("Sys.Audit",)


def test_ca_c5_1_2_el_rol_de_070_puede_crear_como_antes_en_los_privilegios_de_peticion():
    for accion in ("clone", "crear_iso", "crear_import", "config", "resize", "upload"):
        assert privilegios_de_peticion(accion) <= set(ROL_PROXLAUNCH)


def test_rf_c5_1_privilegios_opcionales_de_la_fase_a_no_cambian_de_forma():
    assert PRIVILEGIOS_OPCIONALES == (("VM.PowerMgmt", "/vms"), ("Pool.Audit", "/pool"))
    sin_caps = privilegios_opcionales(None)
    assert [(p.privilegio, p.ruta) for p in sin_caps] == list(PRIVILEGIOS_OPCIONALES)


@pytest.mark.parametrize("version", VERSIONES)
def test_rf_c5_1_sdn_use_y_sdn_audit_son_opcionales_en_la_zona_con_marcador(version):
    opcionales = {(p.privilegio, p.ruta) for p in privilegios_opcionales(caps(version))}
    assert ("SDN.Use", "/sdn/zones/<zona>") in opcionales
    assert ("SDN.Audit", "/sdn/zones/<zona>") in opcionales
    for p in PRIVILEGIOS_SDN_OPCIONALES:
        assert p.no_verificado is True  # la zona no se conoce de antemano: sin promesas


@pytest.mark.parametrize("version", V_8)
def test_ca_c5_1_3_en_8x_los_opcionales_incluyen_vm_monitor_y_excluyen_guestagent_audit(version):
    nombres = {p.privilegio for p in privilegios_opcionales(caps(version))}
    assert "VM.Monitor" in nombres
    assert "VM.GuestAgent.Audit" not in nombres
    assert privilegios_agente(caps(version)) == ("VM.Monitor",)


@pytest.mark.parametrize("version", V_9)
def test_ca_c5_1_3_en_9x_los_opcionales_incluyen_guestagent_audit_y_excluyen_vm_monitor(version):
    nombres = {p.privilegio for p in privilegios_opcionales(caps(version))}
    assert "VM.GuestAgent.Audit" in nombres
    assert "VM.Monitor" not in nombres
    assert "VM.Monitor" not in privilegios_agente(caps(version))


@pytest.mark.parametrize("version", VERSIONES)
def test_rf_c5_1_nunca_se_pide_un_privilegio_que_no_existe_en_la_version(version):
    nombres = [p.privilegio for p in privilegios_opcionales(caps(version))]
    pares = [(p.privilegio, p.ruta) for p in privilegios_opcionales(caps(version))]
    assert len(pares) == len(set(pares))
    if version < (9, 0):
        assert not [n for n in nombres if n.startswith("VM.GuestAgent")]
    else:
        assert "VM.Monitor" not in nombres
    assert "VM.Firewall" not in nombres
    # Los de snippets de 8.x (Datastore.Allocate) solo antes de 9.0.
    assert ("Datastore.Allocate" in nombres) == (version < (9, 0))


def test_rf_c5_1_los_opcionales_no_cambian_el_rol_ni_lo_amplian():
    antes = tuple(ROL_PROXLAUNCH)
    for v in VERSIONES:
        privilegios_opcionales(caps(v))
    assert antes == ROL_PROXLAUNCH and len(ROL_PROXLAUNCH) == 14


def test_rf_c5_1_ruta_sdn_forma_la_ruta_de_acl_de_zona_red_y_vlan():
    assert ruta_sdn("dc1") == "/sdn/zones/dc1"
    assert ruta_sdn("dc1", "prod") == "/sdn/zones/dc1/prod"
    assert ruta_sdn("dc1", "prod", 20) == "/sdn/zones/dc1/prod/20"
    assert ruta_sdn("dc1", None, 20) == "/sdn/zones/dc1"  # la VLAN solo cuenta con red


# --- estado_sdn_fuera_de_local (DT-C19) ---


@pytest.mark.parametrize(
    ("rutas", "esperado"),
    [
        ({}, False),
        ({"/": {"VM.Audit": 1}}, False),
        ({"/sdn/zones/localnetwork": {"SDN.Use": 1}}, False),
        ({"/sdn/zones/localnetwork/vmbr0": {"SDN.Use": 1}}, False),
        ({"/sdn/zones/dc1": {"SDN.Use": 1}}, True),
        ({"/sdn/zones/dc1/prod": {"SDN.Use": 1}}, True),
        ({"/sdn/zones/dc1/prod/20": {"SDN.Use": 0}}, True),
        ({"/": {"SDN.Use": 1}}, True),
        ({"/sdn": {"SDN.Use": 1}}, True),
        ({"/sdn/zones": {"SDN.Use": 1}}, True),
        ({"/": {"SDN.Use": 0}}, False),  # sin propagate no llega a las zonas
        ({"/sdn/zones/dc1": {"SDN.Audit": 1}}, False),  # SDN.Audit no basta para usar
        ({"/sdn/zones/localnetwork": {"SDN.Use": 1}, "/sdn/zones/dc1": {"SDN.Use": 1}}, True),
    ],
)
def test_rf_c0_3_sdn_use_fuera_de_localnetwork_se_deduce_de_los_permisos(rutas, esperado):
    assert estado_sdn_fuera_de_local(PermisosEfectivos(rutas=rutas)) is esperado


def test_rf_c0_3_permisos_desconocidos_dan_none_en_sdn():
    assert estado_sdn_fuera_de_local(None) is None


# --- RF-C0.4: versión mínima 8.0 y tabla de funciones ---

FUNCIONES_C = (
    Funcion.INVENTARIO_LOTES,
    Funcion.VNETS_SDN,
    Funcion.FIREWALL_GRUPO,
    Funcion.REESCRIBIR_RED_CLON,
)


@pytest.mark.parametrize("funcion", FUNCIONES_C)
def test_dc_1_las_cuatro_funciones_de_c_se_piden_desde_8_0(funcion):
    assert TABLA[funcion] == (8, 0)


@pytest.mark.parametrize("version", [(8, 4), (9, 2)])
def test_ca_c0_4_1_con_8_4_forzada_y_9_2_las_cuatro_funciones_estan_disponibles(version):
    c = capacidades_para(interpretar_version("9.2.1")[0], version)
    assert c.forzada and c.version == version
    assert all(c.tiene(f) for f in FUNCIONES_C)
    assert c.es_soportada()


def test_ca_c0_4_1_con_8_0_y_9_2_la_disponibilidad_de_las_opciones_de_versionado_es_si():
    for v in [(8, 0), (9, 2)]:
        estados = disponibilidad_fase_c(permisos_de(), caps(v, True))
        for opcion in (OpcionC.INVENTARIO, OpcionC.VNETS, OpcionC.FIREWALL, OpcionC.RED_CLON):
            assert estados[opcion].disponibilidad == Disponibilidad.SI, (v, opcion)


def test_ca_c0_4_1_el_sdn_incluido_de_serie_ya_no_es_una_bandera():
    """DT-D3: con la mínima 8.4 el SDN viene siempre instalado; la bandera se retiró."""
    assert not hasattr(Funcion, "SDN_INCLUIDO")


def test_ca_c0_4_1_la_comparacion_de_versiones_de_la_fase_c_solo_vive_en_capacidades_py():
    """Ningún módulo nuevo de la fase C compara versiones a mano: pregunta a ``Capacidades``."""
    planos = [
        f for d in ("red", "firewall", "inventario") for f in (SRC / "nucleo" / d).rglob("*.py")
    ]
    planos += [
        SRC / "nucleo" / "opciones" / "disponibilidad_c.py",
        SRC / "interfaz" / "textos_c.py",
        SRC / "interfaz" / "vistas" / "seccion_firewall.py",
        SRC / "interfaz" / "vistas" / "seccion_red_clon.py",
    ]
    patron = re.compile(
        r"\.(mayor|menor)\b|version\s*(>=|<=|<|>)\s*\(|\(\s*\d+\s*,\s*\d+\s*\)\s*(>=|<=|<|>)"
    )
    ofensores = [
        f"{p.name}:{n}"
        for p in planos
        if p.exists()
        for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if patron.search(linea)
    ]
    assert ofensores == []


def test_rf_c0_4_una_version_sin_la_funcion_da_no_con_v_c50_y_la_version_minima():
    estados = disponibilidad_fase_c(permisos_de(), caps((7, 4), True))
    for opcion in (OpcionC.INVENTARIO, OpcionC.VNETS, OpcionC.FIREWALL, OpcionC.RED_CLON):
        e = estados[opcion]
        assert e.disponibilidad == Disponibilidad.NO
        assert e.codigo == CodigoError.OPCION_SIN_VERSION
        assert e.params["version"] == "8.0" and e.params["opcion"] == opcion.value


# --- RF-C0.3: privilegio ausente -> deshabilitada con explicación ---


def estado(permisos, version=(9, 2)):
    return disponibilidad_fase_c(permisos, caps(version))


@pytest.mark.parametrize("version", VERSIONES)
def test_ca_c0_3_1_sin_vm_config_network_el_firewall_y_la_red_del_clon_estan_deshabilitados(
    version,
):
    e = estado(sin("VM.Config.Network"), version)
    for opcion in (OpcionC.FIREWALL, OpcionC.RED_CLON):
        assert e[opcion].disponibilidad == Disponibilidad.NO
        assert e[opcion].codigo == CodigoError.OPCION_SIN_PRIVILEGIO
        assert e[opcion].params["privilegio"] == "VM.Config.Network"
        assert e[opcion].params["ruta"] == "/vms"
    # El resto de opciones sigue disponible: solo se deshabilita lo que falta.
    assert e[OpcionC.INVENTARIO].disponibilidad == Disponibilidad.SI
    assert e[OpcionC.VNETS].disponibilidad == Disponibilidad.SI


def test_ca_c0_3_1_con_el_privilegio_solo_en_una_subruta_de_una_mv_no_basta_para_vms():
    e = estado(PermisosEfectivos(rutas={"/vms/101": {"VM.Config.Network": 1}}))
    assert e[OpcionC.FIREWALL].disponibilidad == Disponibilidad.NO


def test_ca_c0_3_1_con_el_privilegio_en_vms_propagado_si_esta_disponible():
    e = estado(PermisosEfectivos(rutas={"/vms": {"VM.Config.Network": 1}}))
    assert e[OpcionC.FIREWALL].disponibilidad == Disponibilidad.SI
    assert e[OpcionC.RED_CLON].disponibilidad == Disponibilidad.SI


def test_ca_c0_3_1_sin_vm_audit_el_inventario_esta_deshabilitado_y_lo_demas_no():
    e = estado(sin("VM.Audit"))
    assert e[OpcionC.INVENTARIO].disponibilidad == Disponibilidad.NO
    assert e[OpcionC.INVENTARIO].params["privilegio"] == "VM.Audit"
    assert e[OpcionC.FIREWALL].disponibilidad == Disponibilidad.SI


def test_ca_c0_3_2_con_permisos_desconocidos_las_opciones_quedan_habilitadas_con_aviso():
    for version in VERSIONES:
        e = estado(None, version)
        for opcion in (OpcionC.INVENTARIO, OpcionC.VNETS, OpcionC.FIREWALL, OpcionC.RED_CLON):
            assert e[opcion].disponibilidad == Disponibilidad.CON_AVISO  # no bloquea
            assert e[opcion].codigo is None
            assert e[opcion].params["motivo"] == "permisos_desconocidos"


def test_ca_c0_3_2_estado_privilegio_none_es_desconocido_y_no_falso():
    assert estado_privilegio(None, "VM.Config.Network", "/vms") is None
    assert estado_privilegio(permisos_de(), "VM.Config.Network", "/vms") is True
    assert estado_privilegio(sin("VM.Config.Network"), "VM.Config.Network", "/vms") is False


def test_ca_c5_2_2_sin_sys_audit_el_firewall_general_nunca_bloquea_solo_avisa():
    for version in VERSIONES:
        e = estado(sin("Sys.Audit"), version)[OpcionC.FIREWALL_GENERAL]
        assert e.disponibilidad == Disponibilidad.CON_AVISO
        assert e.codigo == CodigoError.OPCION_SIN_PRIVILEGIO
        assert (e.params["privilegio"], e.params["ruta"]) == ("Sys.Audit", "/")


def test_ca_c5_2_firewall_general_con_sys_audit_esta_disponible():
    assert estado(permisos_de())[OpcionC.FIREWALL_GENERAL].disponibilidad == Disponibilidad.SI


@pytest.mark.parametrize(
    ("rutas", "esperado"),
    [
        ({"/sdn/zones/dc1": {"SDN.Use": 1}}, Disponibilidad.SI),
        ({"/sdn/zones/localnetwork": {"SDN.Use": 1}}, Disponibilidad.NO),
        ({"/": {"VM.Audit": 1}}, Disponibilidad.NO),
        ({"/sdn/zones/dc1": {"SDN.Audit": 1}}, Disponibilidad.NO),
    ],
)
def test_rf_c0_3_las_vnets_exigen_sdn_use_fuera_de_localnetwork(rutas, esperado):
    e = estado(PermisosEfectivos(rutas=rutas))[OpcionC.VNETS]
    assert e.disponibilidad == esperado
    if esperado == Disponibilidad.NO:
        assert e.codigo == CodigoError.OPCION_SIN_PRIVILEGIO
        assert e.params["privilegio"] == "SDN.Use" and e.params["ruta"] == "/sdn/zones/<zona>"


@pytest.mark.parametrize("version", V_8)
def test_rf_c5_1_la_ip_del_inventario_exige_vm_monitor_en_8x(version):
    ok = estado(permisos_en(vms={"VM.Monitor": 1}), version)[OpcionC.IP_INVENTARIO]
    ko = estado(permisos_en(vms={"VM.GuestAgent.Audit": 1}), version)[OpcionC.IP_INVENTARIO]
    assert ok.disponibilidad == Disponibilidad.SI
    assert ko.disponibilidad != Disponibilidad.SI
    assert "VM.Firewall" not in str(ko.params)


@pytest.mark.parametrize("version", V_9)
def test_rf_c5_1_la_ip_del_inventario_exige_guestagent_audit_en_9x(version):
    ok = estado(permisos_en(vms={"VM.GuestAgent.Audit": 1}), version)[OpcionC.IP_INVENTARIO]
    ko = estado(permisos_en(vms={"VM.Monitor": 1}), version)[OpcionC.IP_INVENTARIO]
    assert ok.disponibilidad == Disponibilidad.SI
    assert ko.disponibilidad != Disponibilidad.SI


def test_rf_c0_3_toda_opcion_de_c_tiene_estado_y_los_privilegios_citados_existen():
    existentes = set(ROL_PROXLAUNCH) | {"SDN.Audit", "VM.Monitor", "VM.GuestAgent.Audit"}
    for version in VERSIONES:
        for permisos in (None, permisos_de(), sin("VM.Config.Network"), sin("Sys.Audit")):
            e = estado(permisos, version)
            assert set(e) == set(OpcionC)
            for est in e.values():
                priv = est.params.get("privilegio")
                if priv:
                    assert priv in existentes, priv
                assert priv != "VM.Firewall"


# --- RF-C5.2: filas de «Qué puedo hacer» ---

VIAS_C = (
    Via.LOTES_SERVIDOR,
    Via.VNETS_SDN,
    Via.FIREWALL,
    Via.FIREWALL_GENERAL,
    Via.RED_CLON,
)


def vias(permisos, version=(9, 2), con_permisos=True):
    inv = inv_origen(permisos_efectivos=permisos if con_permisos else None)
    return calcular_capacidades(caps(version), inv, None).vias


@pytest.mark.parametrize("version", VERSIONES)
def test_ca_c5_2_1_con_el_doble_de_permisos_completo_las_5_filas_son_si(version):
    v = vias(permisos_de(), version)
    assert [v[via].disponibilidad for via in VIAS_C] == [Disponibilidad.SI] * 5


def test_ca_c5_2_1_las_cinco_filas_existen_con_su_orden_y_no_son_vias_de_origen():
    assert len(VIAS_C) == 5
    for origen in OrigenSO:
        assert not set(VIAS_C) & set(vias_de_origen(origen))


def test_ca_c5_2_2_sin_sys_audit_en_raiz_el_firewall_general_dice_no_con_motivo_sin_bloquear():
    v = vias(sin("Sys.Audit"))
    e = v[Via.FIREWALL_GENERAL]
    assert e.disponibilidad == Disponibilidad.CON_AVISO  # la interfaz lo dice «No» (textos)
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert (e.params["privilegio"], e.params["ruta"]) == ("Sys.Audit", "/")
    # Las demás filas no cambian y la creación (vías de origen) no se bloquea.
    assert all(
        v[via].disponibilidad == Disponibilidad.SI for via in VIAS_C if via != Via.FIREWALL_GENERAL
    )
    assert all(
        v[via].disponibilidad == Disponibilidad.SI for via in vias_de_origen(OrigenSO.DISCO_VACIO)
    )


def test_ca_c5_2_3_con_permisos_desconocidos_las_filas_son_con_aviso_sin_codigo():
    v = vias(None, con_permisos=False)
    for via in VIAS_C:
        assert v[via].disponibilidad == Disponibilidad.CON_AVISO, via
        assert v[via].codigo is None
        assert v[via].params["motivo"] == "permisos_desconocidos"


@pytest.mark.parametrize(
    ("quitar", "via", "privilegio", "ruta"),
    [
        (("VM.Config.Network",), Via.FIREWALL, "VM.Config.Network", "/vms"),
        (("VM.Config.Network",), Via.RED_CLON, "VM.Config.Network", "/vms"),
        (("VM.Audit",), Via.LOTES_SERVIDOR, "VM.Audit", "/vms"),
        (("VM.Allocate",), Via.LOTES_SERVIDOR, "VM.Allocate", "/vms"),
    ],
)
def test_ca_c5_2_cada_fila_sin_su_privilegio_dice_no_y_nombra_privilegio_y_ruta(
    quitar, via, privilegio, ruta
):
    e = vias(sin(*quitar))[via]
    assert e.disponibilidad == Disponibilidad.NO
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert (e.params["privilegio"], e.params["ruta"]) == (privilegio, ruta)


def test_ca_c5_2_vnets_sin_sdn_use_fuera_de_localnetwork_dice_no_con_la_ruta_generica():
    permisos = PermisosEfectivos(rutas={"/vms": {p: 1 for p in ROL_MVP4 if p != "SDN.Use"}})
    e = vias(permisos)[Via.VNETS_SDN]
    assert e.disponibilidad == Disponibilidad.NO
    assert (e.params["privilegio"], e.params["ruta"]) == ("SDN.Use", "/sdn/zones/<zona>")


@pytest.mark.parametrize("version", [(8, 0), (9, 2)])
def test_ca_c5_2_las_filas_estan_disponibles_en_la_version_minima_y_en_la_ultima(version):
    v = vias(permisos_de(), version)
    assert all(v[via].codigo is None for via in VIAS_C)


def test_ca_c5_2_una_version_anterior_a_8_0_da_no_por_version_en_las_filas_con_funcion():
    v = vias(permisos_de(), (7, 4))
    for via in (Via.LOTES_SERVIDOR, Via.VNETS_SDN, Via.FIREWALL, Via.RED_CLON):
        assert v[via].disponibilidad == Disponibilidad.NO
        assert v[via].codigo == CodigoError.OPCION_SIN_VERSION
        assert v[via].params["version"] == "8.0"


# --- CA-C0.3.3: un lote guardado o un CSV con la opción deshabilitada no se aplica en silencio ---


def _plan_con_firewall(permisos):
    inv = inv_origen(permisos_efectivos=permisos)
    d = definicion(
        2,
        plantilla_vm=plantilla(
            discos=[Disco("local-lvm", 32)],
            firewall=FirewallMV(activo=True, politica_entrada=Politica.PERMITIR),
        ),
    )
    return construir_plan(
        d, inv, [100, 101], [], id_lote="abcd1234", ahora=0.0, version_validacion=(9, 2),
        vms_visibles=None,
    )  # fmt: skip


def test_ca_c0_3_3_un_lote_con_firewall_sin_vm_config_network_se_bloquea_con_v_c40():
    plan = _plan_con_firewall(sin("VM.Config.Network"))
    v_c40 = [p for p in plan.problemas if p.regla == "V-C40"]
    assert v_c40 and plan.bloqueado
    assert v_c40[0].params["privilegio"] == "VM.Config.Network"
    assert v_c40[0].params["ruta"] == "/vms"


def test_ca_c0_3_2_con_permisos_desconocidos_el_plan_no_se_bloquea_por_el_firewall():
    plan = _plan_con_firewall(None)
    assert "V-C40" not in {p.regla for p in plan.problemas}
    assert not [
        p for p in plan.problemas if p.regla.startswith("V-C") and p.severidad.value == "error"
    ]


def test_ca_c0_3_3_con_el_privilegio_el_plan_no_trae_v_c40():
    plan = _plan_con_firewall(permisos_de())
    assert "V-C40" not in {p.regla for p in plan.problemas}


def test_ca_c0_3_3_la_version_forzada_sin_la_funcion_da_v_c50_al_planificar():
    inv = inv_origen(permisos_efectivos=permisos_de())
    d = definicion(
        1,
        plantilla_vm=plantilla(
            discos=[Disco("local-lvm", 32)],
            firewall=FirewallMV(activo=True, politica_entrada=Politica.PERMITIR),
        ),
    )
    plan = construir_plan(
        d, inv, [100], [], id_lote="abcd1234", ahora=0.0, version_validacion=(7, 4),
        vms_visibles=None,
    )  # fmt: skip
    v_c50 = [p for p in plan.problemas if p.regla == "V-C50"]
    assert v_c50 and v_c50[0].params["version"] == "8.0"


def test_dc_1_la_dataclass_de_estado_es_inmutable():
    e = estado(permisos_de())[OpcionC.FIREWALL]
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.disponibilidad = Disponibilidad.NO  # type: ignore[misc]
