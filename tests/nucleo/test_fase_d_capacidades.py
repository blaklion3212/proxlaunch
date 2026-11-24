"""D0.3 (0.9.0): privilegio ausente → opción deshabilitada con explicación (disponibilidad de D).

CA-D0.3.1 (núcleo), CA-D0.3.2, CA-D0.3.3 (núcleo). ``disponibilidad_fase_d`` es pura: con permisos
desconocidos (``None``) no deshabilita nada (queda «con aviso») y confía en el 403 traducido.
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.opciones.disponibilidad_d import disponibilidad_fase_d
from proxlaunch.nucleo.opciones.modelos import OpcionD
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad

from .apoyo_fase_d import V_84, V_90, V_91, V_92, caps_de, permisos_mapeo

VERSIONES = [V_84, V_90, V_91, V_92]
IDS = ["8.4", "9.0", "9.1", "9.2"]


def _estado(version, permisos, opcion):
    return disponibilidad_fase_d(caps_de(version), permisos, None)[opcion]


def test_las_tres_opciones_de_d_siempre_tienen_estado():
    est = disponibilidad_fase_d(caps_de(V_92), permisos_mapeo(), None)
    assert set(est) == {OpcionD.MAPEOS, OpcionD.CPU_PERSONALIZADA, OpcionD.CONSERVAR_MAC}
    assert [e.opcion for e in est.values()] == list(est)


@pytest.mark.parametrize("version", VERSIONES, ids=IDS)
@pytest.mark.parametrize("permisos", [None, permisos_mapeo(), permisos_mapeo("/mapping")])
def test_conservar_la_mac_siempre_esta_disponible_es_una_validacion_local(version, permisos):
    e = _estado(version, permisos, OpcionD.CONSERVAR_MAC)
    assert e.disponibilidad == Disponibilidad.SI and e.params == {}


@pytest.mark.parametrize("version", VERSIONES, ids=IDS)
def test_ca_d0_3_1_sin_mapping_use_en_ninguna_ruta_los_mapeos_quedan_deshabilitados_con_v_d63(
    version,
):
    e = _estado(version, permisos_mapeo(), OpcionD.MAPEOS)
    assert e.disponibilidad == Disponibilidad.NO
    assert e.codigo == CodigoError.OPCION_SIN_PRIVILEGIO
    assert e.params == {
        "opcion": "mapeos",
        "privilegio": "Mapping.Use",
        "ruta": "/mapping/pci",
    }


@pytest.mark.parametrize("ruta", ["/mapping/pci/gpu-a2", "/mapping/usb/llave", "/mapping"])
def test_con_mapping_use_en_cualquier_mapeo_la_seccion_se_habilita(ruta):
    e = _estado(V_92, permisos_mapeo(ruta), OpcionD.MAPEOS)
    assert e.disponibilidad == Disponibilidad.SI and e.codigo is None


@pytest.mark.parametrize("version", VERSIONES, ids=IDS)
def test_ca_d0_3_2_con_permisos_desconocidos_nada_se_deshabilita(version):
    for opcion in (OpcionD.MAPEOS, OpcionD.CPU_PERSONALIZADA):
        e = _estado(version, None, opcion)
        assert e.disponibilidad == Disponibilidad.CON_AVISO
        assert e.params == {"opcion": opcion.value, "motivo": "permisos_desconocidos"}
        assert e.codigo is None


def test_cpu_personalizada_en_9_2_pide_mapping_use_en_mapping_cpu():
    e = _estado(V_92, permisos_mapeo(), OpcionD.CPU_PERSONALIZADA)
    assert e.disponibilidad == Disponibilidad.NO and e.codigo == CodigoError.OPCION_SIN_PRIVILEGIO
    assert e.params["privilegio"] == "Mapping.Use" and e.params["ruta"] == "/mapping/cpu"
    ok = _estado(V_92, permisos_mapeo("/mapping/cpu/gamer"), OpcionD.CPU_PERSONALIZADA)
    assert ok.disponibilidad == Disponibilidad.SI


@pytest.mark.parametrize("version", [V_84, V_90, V_91], ids=["8.4", "9.0", "9.1"])
def test_cpu_personalizada_antes_de_9_2_exige_sys_audit_en_nodes_y_vm_config_cpu(version):
    from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos

    assert _estado(version, permisos_mapeo(), OpcionD.CPU_PERSONALIZADA).disponibilidad == (
        Disponibilidad.SI  # el rol de 14 trae ambos
    )
    sin_audit = PermisosEfectivos(rutas={"/vms": {"VM.Config.CPU": 1}})
    e = _estado(version, sin_audit, OpcionD.CPU_PERSONALIZADA)
    assert e.disponibilidad == Disponibilidad.NO
    assert (e.params["privilegio"], e.params["ruta"]) == ("Sys.Audit", "/nodes")
    sin_cpu = PermisosEfectivos(rutas={"/": {"Sys.Audit": 1}})
    e = _estado(version, sin_cpu, OpcionD.CPU_PERSONALIZADA)
    assert (e.params["privilegio"], e.params["ruta"]) == ("VM.Config.CPU", "/vms")


def test_cl_d19_en_9_2_el_modelo_existe_pero_sin_mapping_use_la_opcion_sale_deshabilitada():
    e = _estado(V_92, permisos_mapeo("/mapping/cpu/otro"), OpcionD.CPU_PERSONALIZADA)
    assert e.disponibilidad == Disponibilidad.SI  # genérico: basta uno; el 403 explica el resto
    from proxlaunch.nucleo.origen.permisos import estado_cpu_personalizada

    assert (
        estado_cpu_personalizada(permisos_mapeo("/mapping/cpu/otro"), caps_de(V_92), "custom-x")
        is False
    )


def test_sin_caps_se_aplica_la_regla_de_8_4_a_9_1_para_la_cpu():
    est = disponibilidad_fase_d(None, permisos_mapeo(), None)
    assert est[OpcionD.CPU_PERSONALIZADA].disponibilidad == Disponibilidad.SI


def test_la_version_forzada_8_4_sobre_un_servidor_9_2_usa_la_regla_8_4():
    est = disponibilidad_fase_d(Capacidades((8, 4), True), permisos_mapeo(), None)
    assert est[OpcionD.CPU_PERSONALIZADA].disponibilidad == Disponibilidad.SI


def test_la_disponibilidad_no_depende_del_inventario_ni_lo_modifica():
    from .apoyo_fase_d import inv_arq

    inv = inv_arq(nodos=("pve1",))
    antes = repr(inv)
    a = disponibilidad_fase_d(caps_de(V_92), permisos_mapeo(), inv)
    b = disponibilidad_fase_d(caps_de(V_92), permisos_mapeo(), None)
    assert a == b and repr(inv) == antes
