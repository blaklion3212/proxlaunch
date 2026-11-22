"""Disponibilidad de las opciones (privilegio, versión, pools) y privilegios opcionales.

Requisitos: RF-A0.3 (CA-A0.3.1, A0.3.2), RF-A0.4 (CA-A0.4.1, A0.4.2), CA-A1.1.4, CA-A1.2.4,
CA-A2.1.5, CA-A5.1.8, CA-A6.1.3, RF-A4.2 (CA-A4.2.1..A4.2.5), RF-A8.1 (CA-A8.1.1..A8.1.4),
CL-A5, CL-A6, P-3 (privilegios opcionales en una lista aparte).
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.capacidades import Capacidades, capacidades_para
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.opciones.disponibilidad import disponibilidad_opciones
from proxlaunch.nucleo.opciones.modelos import EstadoPools, OpcionA, PoolsServidor
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.origen.permisos import (
    PRIVILEGIOS_OPCIONALES,
    ROL_PROXLAUNCH,
    estado_privilegio,
)

from .apoyo_fase_a import ROL_BASE, ROL_COMPLETO, permisos, permisos_en_vms

CAPS_92 = capacidades_para(Version("9.2.1", 9, 2, 1), None)
CAPS_80 = capacidades_para(Version("8.0.4", 8, 0, 4), None)
POOLS_OK = PoolsServidor(EstadoPools.OK, ("a", "b", "c"))

# opción -> privilegio exigido en /vms (arquitectura §2.2)
PRIVILEGIO_DE = {
    OpcionA.ENCENDER: "VM.PowerMgmt",
    OpcionA.ARRANQUE_AUTO: "VM.Config.Options",
    OpcionA.ARRANQUE_ORDEN: "VM.Config.Options",
    OpcionA.NOTAS: "VM.Config.Options",
    OpcionA.ETIQUETAS: "VM.Config.Options",
    OpcionA.PROTEGER: "VM.Config.Options",
    OpcionA.MTU: "VM.Config.Network",
    OpcionA.LIMITE_RED: "VM.Config.Network",
}


def _est(perm, caps=CAPS_92, pools=POOLS_OK):
    return disponibilidad_opciones(perm, caps, pools)


# --- RF-A8.1: privilegios opcionales fuera del rol -----------------------------------------------


def test_ca_a8_1_los_privilegios_opcionales_son_una_lista_aparte_y_el_rol_sigue_con_14():
    """P-3 / RF-A8.1: ``VM.PowerMgmt`` y ``Pool.Audit`` no forman parte de ``ROL_PROXLAUNCH``."""
    assert len(ROL_PROXLAUNCH) == 14
    assert "VM.PowerMgmt" not in ROL_PROXLAUNCH and "Pool.Audit" not in ROL_PROXLAUNCH
    assert dict(PRIVILEGIOS_OPCIONALES) == {"VM.PowerMgmt": "/vms", "Pool.Audit": "/pool"}


def test_ca_a8_1_los_opcionales_no_estan_entre_los_minimos_que_avisa_la_conexion():
    """RF-A8.1: no se añaden a ``PERMISOS_POR_RUTA`` (ni el rol de 14 los exige al conectar)."""
    from proxlaunch.nucleo.servicios.conexion import PERMISOS_POR_RUTA

    todos = {p for privs in PERMISOS_POR_RUTA.values() for p in privs}
    assert "VM.PowerMgmt" not in todos and "Pool.Audit" not in todos


def test_ca_a8_1_1_con_el_rol_de_0_5_1_solo_encender_queda_deshabilitado():
    """CA-A8.1.1: con el rol de 14 privilegios todo está habilitado salvo encender; pools según
    lectura.
    """
    est = _est(permisos(ROL_BASE))
    deshabilitadas = {o for o, e in est.items() if e.disponibilidad == Disponibilidad.NO}
    assert deshabilitadas == {OpcionA.ENCENDER}
    assert est[OpcionA.POOL].disponibilidad == Disponibilidad.SI


def test_ca_a8_1_2_con_el_rol_mas_los_dos_opcionales_todo_habilitado():
    """CA-A8.1.2."""
    est = _est(permisos(ROL_COMPLETO))
    assert all(e.disponibilidad == Disponibilidad.SI for e in est.values())
    assert set(est) == set(OpcionA)


# --- RF-A0.3: privilegio ausente -> deshabilitada con explicación ---------------------------------


@pytest.mark.parametrize("opcion", sorted(PRIVILEGIO_DE, key=str))
def test_ca_a0_3_1_sin_el_privilegio_la_opcion_se_deshabilita_y_nombra_privilegio_y_ruta(opcion):
    """CA-A0.3.1 (y CA-A1.1.4, A1.2.4, A2.1.5, A5.1.8, A6.1.3): P y R en los parámetros."""
    privilegio = PRIVILEGIO_DE[opcion]
    est = _est(permisos(ROL_COMPLETO, quitar=(privilegio,)))[opcion]
    assert est.disponibilidad == Disponibilidad.NO
    assert est.codigo == CodigoError.OPCION_SIN_PRIVILEGIO
    assert est.params["privilegio"] == privilegio
    assert est.params["ruta"] == "/vms"
    assert est.params["opcion"] == opcion.value


@pytest.mark.parametrize("opcion", sorted(PRIVILEGIO_DE, key=str))
def test_a0_3_quitar_un_privilegio_solo_afecta_a_sus_opciones(opcion):
    """Quitar P deshabilita exactamente las opciones que lo exigen y no otras."""
    privilegio = PRIVILEGIO_DE[opcion]
    est = _est(permisos(ROL_COMPLETO, quitar=(privilegio,)))
    afectadas = {o for o, p in PRIVILEGIO_DE.items() if p == privilegio}
    assert {o for o, e in est.items() if e.disponibilidad == Disponibilidad.NO} == afectadas


def test_ca_a0_3_2_permisos_desconocidos_dejan_todo_habilitado():
    """CA-A0.3.2 / INV-O10: ``None`` = desconocido -> habilitado (lo resuelve el 403)."""
    est = _est(None, pools=POOLS_OK)
    assert all(e.disponibilidad == Disponibilidad.SI for e in est.values())


def test_ca_a1_1_4_la_casilla_encender_sin_vm_powermgmt_nombra_el_privilegio():
    est = _est(permisos(ROL_BASE))[OpcionA.ENCENDER]
    assert est.disponibilidad == Disponibilidad.NO
    assert est.params["privilegio"] == "VM.PowerMgmt"


# --- CL-A5 / CA-A8.1.3 / CA-A8.1.4: rutas heredadas y propagate -----------------------------------


def test_ca_a8_1_3_privilegio_en_la_raiz_con_propagate_se_reconoce():
    """CA-A8.1.3: ``/`` con propagate=1 cubre ``/vms`` y ``/vms/<id>``."""
    perm = PermisosEfectivos(rutas={"/": {"VM.PowerMgmt": 1}})
    assert estado_privilegio(perm, "VM.PowerMgmt", "/vms") is True
    assert estado_privilegio(perm, "VM.PowerMgmt", "/vms/105") is True
    assert _est(perm)[OpcionA.ENCENDER].disponibilidad == Disponibilidad.SI


def test_ca_a8_1_3_privilegio_en_una_vm_concreta_se_reconoce_solo_para_esa_vm():
    """CA-A8.1.3: ``VM.PowerMgmt`` en ``/vms/105`` vale para esa MV y no para otra."""
    perm = PermisosEfectivos(rutas={"/vms/105": {"VM.PowerMgmt": 1}})
    assert estado_privilegio(perm, "VM.PowerMgmt", "/vms/105") is True
    assert estado_privilegio(perm, "VM.PowerMgmt", "/vms/106") is False
    # El formulario evalúa /vms (todas las MVs): un permiso solo en una MV no lo habilita.
    assert _est(perm)[OpcionA.ENCENDER].disponibilidad == Disponibilidad.NO


def test_ca_a8_1_4_y_cl_a5_propagate_cero_en_vms_no_se_concede_a_vms_id():
    """CA-A8.1.4 / CL-A5: sin propagate el privilegio de ``/vms`` no llega a ``/vms/<id>``."""
    perm = permisos_en_vms(("VM.PowerMgmt",), propagate=0)
    assert estado_privilegio(perm, "VM.PowerMgmt", "/vms/100") is False
    assert estado_privilegio(perm, "VM.PowerMgmt", "/vms") is True


def test_cl_a5_un_privilegio_solo_en_un_pool_no_habilita_opciones_de_vms():
    """CL-A5: ``VM.PowerMgmt`` solo en ``/pool/x`` no se concede por error en ``/vms``."""
    perm = PermisosEfectivos(rutas={"/pool/x": {"VM.PowerMgmt": 1, "VM.Config.Options": 1}})
    est = _est(perm)
    assert est[OpcionA.ENCENDER].disponibilidad == Disponibilidad.NO
    assert est[OpcionA.NOTAS].disponibilidad == Disponibilidad.NO


def test_cl_a5_privilegio_heredado_de_un_ancestro_con_propagate_en_vms():
    perm = permisos_en_vms(("VM.PowerMgmt", "VM.Config.Options"), propagate=1)
    assert _est(perm)[OpcionA.ENCENDER].disponibilidad == Disponibilidad.SI


# --- RF-A0.4 / CL-A6: versión ---------------------------------------------------------------------


def test_cl_a6_versiones_8_0_y_9_2_habilitan_etiquetas():
    """P-1 / CL-A6: la versión mínima soportada (8.0) y la última (9.2) admiten etiquetas."""
    for caps in (CAPS_80, CAPS_92):
        assert (
            _est(permisos(ROL_COMPLETO), caps)[OpcionA.ETIQUETAS].disponibilidad
            == Disponibilidad.SI
        )


def test_ca_a0_4_1_version_menor_que_la_minima_deshabilita_con_la_version_requerida():
    """CA-A0.4.1 / CA-A0.4.2: una versión (real o forzada) por debajo de la mínima de la opción."""
    caps_vieja = Capacidades(version=(7, 2), forzada=True)
    est = _est(permisos(ROL_COMPLETO), caps_vieja)[OpcionA.ETIQUETAS]
    assert est.disponibilidad == Disponibilidad.NO
    assert est.codigo == CodigoError.OPCION_SIN_VERSION
    assert est.params["version"] == "7.3"
    assert est.params["opcion"] == "etiquetas"


def test_ca_a0_4_la_version_se_evalua_antes_que_el_privilegio():
    """Sin versión y sin privilegio: el motivo mostrado es la versión (arq. §9)."""
    caps_vieja = Capacidades(version=(7, 2), forzada=False)
    est = _est(permisos(ROL_COMPLETO, quitar=("VM.Config.Options",)), caps_vieja)
    assert est[OpcionA.ETIQUETAS].codigo == CodigoError.OPCION_SIN_VERSION


def test_ca_a0_4_la_version_solo_afecta_a_las_etiquetas():
    caps_vieja = Capacidades(version=(7, 2), forzada=True)
    est = _est(permisos(ROL_COMPLETO), caps_vieja)
    assert {o for o, e in est.items() if e.disponibilidad == Disponibilidad.NO} == {
        OpcionA.ETIQUETAS
    }


# --- RF-A4.2: pools -------------------------------------------------------------------------------


def test_ca_a4_2_1_sin_pool_audit_y_lista_vacia_se_deshabilita_nombrando_pool_audit():
    """CA-A4.2.1: ``SIN_PERMISO`` -> deshabilitada, distinta de «no hay pools»."""
    est = _est(permisos(ROL_BASE), pools=PoolsServidor(EstadoPools.SIN_PERMISO))[OpcionA.POOL]
    assert est.disponibilidad == Disponibilidad.NO
    assert est.codigo == CodigoError.POOLS_SIN_PERMISO
    assert est.params["privilegio"] == "Pool.Audit" and est.params["ruta"] == "/pool"


def test_ca_a4_2_2_con_pool_audit_y_lista_vacia_solo_ninguno_sin_deshabilitar():
    """CA-A4.2.2: «no hay pools en este servidor» no es «sin permiso»."""
    est = _est(permisos(ROL_COMPLETO), pools=PoolsServidor(EstadoPools.OK, ()))[OpcionA.POOL]
    assert est.disponibilidad == Disponibilidad.CON_AVISO
    assert est.codigo is None and est.params == {"motivo": "sin_pools"}
    assert est.codigo != CodigoError.POOLS_SIN_PERMISO


def test_ca_a4_1_1_con_tres_pools_la_lista_esta_habilitada_sin_avisos():
    """CA-A4.1.1."""
    est = _est(permisos(ROL_COMPLETO), pools=POOLS_OK)[OpcionA.POOL]
    assert est.disponibilidad == Disponibilidad.SI and est.codigo is None and est.params == {}


def test_ca_a4_2_3_un_usuario_con_pool_audit_parcial_ve_lo_que_devuelve_la_api():
    """CA-A4.2.3: ``OK`` con los ids filtrados por Proxmox; la app no intenta suplir otros."""
    est = _est(permisos(ROL_BASE), pools=PoolsServidor(EstadoPools.OK, ("a",)))[OpcionA.POOL]
    assert est.disponibilidad == Disponibilidad.SI


def test_ca_a4_2_4_permisos_desconocidos_y_lista_vacia_es_un_aviso_neutro():
    """CA-A4.2.4: ``DESCONOCIDO`` -> con aviso neutro, no deshabilitada."""
    est = _est(None, pools=PoolsServidor(EstadoPools.DESCONOCIDO))[OpcionA.POOL]
    assert est.disponibilidad == Disponibilidad.CON_AVISO
    assert est.codigo == CodigoError.POOLS_DESCONOCIDO


def test_ca_a4_2_5_fallo_de_lectura_deshabilita_la_lista_sin_tocar_el_resto():
    """CA-A4.2.5: ``ERROR`` -> pool deshabilitado; las demás opciones siguen disponibles."""
    est = _est(permisos(ROL_COMPLETO), pools=PoolsServidor(EstadoPools.ERROR))
    assert est[OpcionA.POOL].disponibilidad == Disponibilidad.NO
    assert est[OpcionA.POOL].codigo == CodigoError.POOLS_ERROR
    resto = {o: e for o, e in est.items() if o != OpcionA.POOL}
    assert all(e.disponibilidad == Disponibilidad.SI for e in resto.values())


def test_a4_2_pools_no_leidos_deshabilitan_con_motivo_no_leido():
    est = _est(permisos(ROL_COMPLETO), pools=PoolsServidor(EstadoPools.NO_LEIDO))[OpcionA.POOL]
    assert est.disponibilidad == Disponibilidad.NO and est.params == {"motivo": "no_leido"}


def test_ca_a4_3_1_el_pool_no_exige_privilegios_nuevos_para_crear():
    """CA-A4.3.1: ``Pool.Audit`` solo sirve para listar; el rol de 14 sigue creando en un pool
    conocido.
    """
    from proxlaunch.nucleo.origen.permisos import privilegios_de_peticion

    for accion in ("crear_iso", "crear_import", "clone", "config"):
        assert not {"Pool.Allocate", "Pool.Audit"} & privilegios_de_peticion(accion)
    assert "Pool.Allocate" not in ROL_PROXLAUNCH  # CA-A4.3.3


def test_a0_3_cada_opcion_tiene_su_estado_y_el_estado_lleva_su_opcion():
    est = _est(permisos(ROL_COMPLETO))
    assert set(est) == set(OpcionA)
    assert all(e.opcion == o for o, e in est.items())
