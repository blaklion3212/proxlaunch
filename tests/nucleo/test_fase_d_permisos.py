"""D5 (0.9.0): privilegios opcionales de la fase D y «Qué puedo hacer en este servidor».

CA-D5.1.1–3 y CA-D5.2.1. El rol ``ProxLaunchCreador`` (14 privilegios) no cambia: los privilegios de
D son opcionales y se evalúan con tres estados (sí, no, desconocido). Parametrizado por versión.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from proxlaunch.nucleo.capacidades import Capacidades, Funcion
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.hardware_cluster.modelos import TipoMapeo
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, Via, calcular_capacidades
from proxlaunch.nucleo.origen.permisos import (
    PRIVILEGIOS_D_OPCIONALES,
    ROL_PROXLAUNCH,
    RUTA_MAPEO_CPU,
    RUTA_MAPEO_PCI,
    RUTA_MAPEO_USB,
    estado_algun_mapeo,
    estado_cpu_personalizada,
    estado_mapeo,
    privilegios_opcionales,
    ruta_mapeo,
)

from .apoyo_fase_d import V_84, V_90, V_91, V_92, caps_de, inv_arq, permisos_mapeo

VERSIONES = [V_84, V_90, V_91, V_92]
IDS = ["8.4", "9.0", "9.1", "9.2"]


def _perm(rutas: dict[str, dict[str, int]]) -> PermisosEfectivos:
    return PermisosEfectivos(rutas=rutas)


def _vias(version, permisos):
    inv = inv_arq(nodos=("pve1",), version=version, permisos_efectivos=permisos)
    c = calcular_capacidades(caps_de(version), inv, None)
    return c


# --- CA-D5.1.2: el rol no cambia ------------------------------------------------------------------


def test_ca_d5_1_2_el_rol_sigue_con_14_privilegios_exactos_y_sin_mapping():
    assert len(ROL_PROXLAUNCH) == 14 and len(set(ROL_PROXLAUNCH)) == 14
    assert not [p for p in ROL_PROXLAUNCH if p.startswith("Mapping.")]
    assert "Sys.Audit" in ROL_PROXLAUNCH and "VM.Config.HWType" in ROL_PROXLAUNCH
    assert "VM.Config.CPU" in ROL_PROXLAUNCH


def test_ca_d5_1_2_los_privilegios_de_d_son_opcionales_y_no_verificados():
    assert {(p.privilegio, p.ruta) for p in PRIVILEGIOS_D_OPCIONALES} == {
        ("Mapping.Use", RUTA_MAPEO_PCI),
        ("Mapping.Use", RUTA_MAPEO_USB),
        ("Mapping.Use", RUTA_MAPEO_CPU),
    }
    assert all(p.no_verificado for p in PRIVILEGIOS_D_OPCIONALES)


@pytest.mark.parametrize("version", VERSIONES, ids=IDS)
def test_ca_d5_1_1_los_opcionales_incluyen_mapeos_siempre_y_mapping_cpu_solo_en_9_2(version):
    rutas = {
        p.ruta for p in privilegios_opcionales(caps_de(version)) if p.privilegio == "Mapping.Use"
    }
    esperado = {RUTA_MAPEO_PCI, RUTA_MAPEO_USB} | ({RUTA_MAPEO_CPU} if version == V_92 else set())
    assert rutas == esperado


def test_ca_d5_1_1_sin_version_conocida_los_opcionales_no_incluyen_los_de_d():
    assert not [p for p in privilegios_opcionales(None) if p.privilegio == "Mapping.Use"]


# --- CA-D5.1.1: mapeos PCI/USB --------------------------------------------------------------------


def test_ruta_mapeo_une_el_tipo_y_el_id():
    assert ruta_mapeo(TipoMapeo.PCI, "gpu-a2") == "/mapping/pci/gpu-a2"
    assert ruta_mapeo(TipoMapeo.USB, "llave-hasp") == "/mapping/usb/llave-hasp"


@pytest.mark.parametrize("version", VERSIONES, ids=IDS)
@pytest.mark.parametrize(
    ("permisos", "esperado"),
    [
        (permisos_mapeo("/mapping/pci/gpu-a2"), True),
        (permisos_mapeo("/mapping/pci"), True),
        (permisos_mapeo("/mapping"), True),
        (permisos_mapeo("/mapping/usb/llave-hasp"), False),
        (permisos_mapeo(), False),
        (_perm({}), False),
        (None, None),
    ],
    ids=["id", "tipo", "todos", "otro_tipo", "solo_rol", "vacio", "desconocido"],
)
def test_ca_d5_1_1_mapping_use_en_el_mapeo_concreto_es_el_mismo_en_todas_las_versiones(
    version, permisos, esperado
):
    del version  # el mapeo PCI/USB existe sin bandera de versión
    assert estado_mapeo(permisos, TipoMapeo.PCI, "gpu-a2") is esperado


@pytest.mark.parametrize(
    ("permisos", "esperado"),
    [
        (permisos_mapeo("/mapping/pci/a"), True),
        (permisos_mapeo("/mapping/usb/b"), True),
        (permisos_mapeo("/mapping"), True),
        (permisos_mapeo("/mapping/cpu/x"), False),  # un mapeo de CPU no sirve para PCI/USB
        (permisos_mapeo(), False),
        (None, None),
    ],
)
def test_ca_d5_1_1_estado_algun_mapeo(permisos, esperado):
    assert estado_algun_mapeo(permisos) is esperado


def test_mapping_use_con_propagate_cero_no_cubre_los_mapeos_concretos():
    sin_propagar = _perm({"/": dict.fromkeys(ROL_PROXLAUNCH, 1), "/mapping": {"Mapping.Use": 0}})
    assert estado_mapeo(sin_propagar, TipoMapeo.PCI, "gpu-a2") is False


def test_otro_privilegio_en_la_ruta_del_mapeo_no_basta():
    solo_audit = permisos_mapeo("/mapping/pci/gpu-a2", privilegio="Mapping.Audit")
    assert estado_mapeo(solo_audit, TipoMapeo.PCI, "gpu-a2") is False


# --- CA-D5.1.1: CPU personalizadas por versión ----------------------------------------------------


@pytest.mark.parametrize("version", [V_84, V_90, V_91], ids=["8.4", "9.0", "9.1"])
@pytest.mark.parametrize(
    ("permisos", "esperado"),
    [
        (permisos_mapeo(), True),  # el rol trae VM.Config.CPU en /vms y Sys.Audit en /
        (_perm({"/": {"Sys.Audit": 1}}), False),  # falta VM.Config.CPU
        (_perm({"/vms": {"VM.Config.CPU": 1}}), False),  # falta Sys.Audit en /nodes
        (_perm({"/vms": {"VM.Config.CPU": 1}, "/nodes": {"Sys.Audit": 1}}), True),
        (permisos_mapeo("/mapping/cpu/gamer"), True),  # Mapping.Use no hace falta antes de 9.2
        (None, None),
    ],
    ids=["rol", "sin_cpu", "sin_audit", "justos", "con_mapping", "desconocido"],
)
def test_ca_d5_1_1_cpu_personalizada_en_8_4_a_9_1_pide_vm_config_cpu_y_sys_audit(
    version, permisos, esperado
):
    assert estado_cpu_personalizada(permisos, caps_de(version), "custom-gamer") is esperado
    assert estado_cpu_personalizada(permisos, caps_de(version)) is esperado


@pytest.mark.parametrize(
    ("permisos", "nombre", "esperado"),
    [
        (permisos_mapeo("/mapping/cpu/gamer"), "custom-gamer", True),
        (permisos_mapeo("/mapping/cpu/gamer"), "custom-otro", False),
        (permisos_mapeo("/mapping/cpu"), "custom-otro", True),
        (permisos_mapeo("/mapping"), "custom-x", True),
        (permisos_mapeo(), "custom-gamer", False),  # el rol de 14 no trae Mapping.Use
        (None, "custom-gamer", None),
        (permisos_mapeo("/mapping/cpu/gamer"), None, True),  # sin nombre: basta en cualquiera
        (permisos_mapeo(), None, False),
    ],
)
def test_ca_d5_1_1_en_9_2_la_cpu_personalizada_pide_mapping_use_en_su_ruta(
    permisos, nombre, esperado
):
    assert estado_cpu_personalizada(permisos, caps_de(V_92), nombre) is esperado


# --- CA-D5.2.1: filas de «Qué puedo hacer» --------------------------------------------------------


@pytest.mark.parametrize("version", VERSIONES, ids=IDS)
def test_ca_d5_2_1_las_tres_vias_de_d_se_calculan_siempre_y_no_son_vias_de_origen(version):
    from proxlaunch.nucleo.modelos.vm import OrigenSO
    from proxlaunch.nucleo.origen.capacidades_origen import vias_de_origen

    c = _vias(version, permisos_mapeo("/mapping"))
    for via in (Via.ARQUITECTURA, Via.MAPEOS, Via.CPU_PERSONALIZADA):
        assert via in c.vias
    todas = {v for o in OrigenSO for v in vias_de_origen(o)}
    assert not todas & {Via.ARQUITECTURA, Via.MAPEOS, Via.CPU_PERSONALIZADA}


@pytest.mark.parametrize("version", VERSIONES, ids=IDS)
def test_ca_d5_2_1_sin_mapping_use_las_filas_de_mapeos_dicen_no_con_privilegio_y_ruta(version):
    c = _vias(version, permisos_mapeo())
    e = c.estado(Via.MAPEOS)
    assert e.disponibilidad == Disponibilidad.NO and e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert e.params["privilegio"] == "Mapping.Use" and e.params["ruta"] == "/mapping/pci"


def test_ca_d5_2_1_cpu_personalizada_sin_permiso_nombra_la_ruta_de_cada_version():
    c92 = _vias(V_92, permisos_mapeo()).estado(Via.CPU_PERSONALIZADA)
    assert c92.disponibilidad == Disponibilidad.NO
    assert (c92.params["privilegio"], c92.params["ruta"]) == ("Mapping.Use", "/mapping/cpu")
    sin_cpu = _perm({"/": {"Sys.Audit": 1}})
    c84 = _vias(V_84, sin_cpu).estado(Via.CPU_PERSONALIZADA)
    assert (c84.params["privilegio"], c84.params["ruta"]) == ("VM.Config.CPU", "/vms")
    sin_audit = _perm({"/vms": {"VM.Config.CPU": 1}})
    c84b = _vias(V_84, sin_audit).estado(Via.CPU_PERSONALIZADA)
    assert (c84b.params["privilegio"], c84b.params["ruta"]) == ("Sys.Audit", "/nodes")


@pytest.mark.parametrize("version", VERSIONES, ids=IDS)
def test_ca_d5_2_1_con_permisos_desconocidos_las_filas_dicen_no_lo_se(version):
    c = _vias(version, None)
    for via in (Via.MAPEOS, Via.CPU_PERSONALIZADA):
        e = c.estado(via)
        assert e.disponibilidad == Disponibilidad.CON_AVISO
        assert e.params["motivo"] == "permisos_desconocidos"
    arq = c.estado(Via.ARQUITECTURA)
    if version == V_92:  # host-arch no necesita Sys.Audit
        assert arq.disponibilidad == Disponibilidad.SI
    else:
        assert arq.disponibilidad == Disponibilidad.CON_AVISO


def test_ca_d5_2_1_la_arquitectura_pide_sys_audit_en_8_4_a_9_1_y_en_9_2_siempre_es_si():
    sin_audit = _perm({})
    for version in (V_84, V_90, V_91):
        e = _vias(version, sin_audit).estado(Via.ARQUITECTURA)
        assert e.disponibilidad == Disponibilidad.NO
        assert (e.params["privilegio"], e.params["ruta"]) == ("Sys.Audit", "/nodes")
    assert _vias(V_92, sin_audit).estado(Via.ARQUITECTURA).disponibilidad == Disponibilidad.SI
    assert (
        _vias(V_84, permisos_mapeo()).estado(Via.ARQUITECTURA).disponibilidad == Disponibilidad.SI
    )


def test_ca_d5_2_1_con_el_rol_de_14_mapeos_y_cpu_de_9_2_salen_no_porque_no_trae_mapping_use():
    c = _vias(V_92, permisos_mapeo())
    assert c.estado(Via.MAPEOS).disponibilidad == Disponibilidad.NO
    assert c.estado(Via.CPU_PERSONALIZADA).disponibilidad == Disponibilidad.NO


def test_las_vias_de_d_usan_la_ayuda_de_permisos_del_rol_ampliado():
    c = _vias(V_92, permisos_mapeo())
    for via in (Via.ARQUITECTURA, Via.MAPEOS, Via.CPU_PERSONALIZADA):
        assert c.estado(via).id_ayuda == "permisos_rol_ampliado"


def test_la_version_forzada_decide_las_filas_aunque_el_servidor_sea_mas_nuevo():
    inv = inv_arq(nodos=("pve1",), version=V_92, permisos_efectivos=permisos_mapeo())
    c = calcular_capacidades(Capacidades((8, 4), True), inv, None)
    assert c.estado(Via.CPU_PERSONALIZADA).disponibilidad == Disponibilidad.SI  # regla 8.4
    assert Capacidades((8, 4), True).tiene(Funcion.CPU_PERSONALIZADA_POR_MAPPING) is False


# --- CA-D5.2.4: la guía publicada no menciona documentos internos ---------------------------------

RAIZ = Path(__file__).resolve().parents[2]
INTERNOS = re.compile(
    r"docs/(requisitos|arquitectura|investigacion)|fase-d-definicion|FD-DEF|INV-D|INV-COD|\bCA-D\d|"
    r"\bRF-D\d|\bP-D\d|prompt\.md|CLAUDE\.md|\.claude/",
)


@pytest.mark.parametrize(
    "ruta",
    [
        "README.md",
        "docs/guia-usuario.md",
        "docs/notas-version-0.9.0.md",
        "docs/notas-version-0.8.0.md",
    ],
)
def test_ca_d5_2_4_la_documentacion_publicada_no_menciona_documentos_internos_ni_decisiones(ruta):
    archivo = RAIZ / ruta
    if not archivo.exists():
        pytest.skip(f"{ruta} no existe todavía")
    hallazgos = [m.group(0) for m in INTERNOS.finditer(archivo.read_text(encoding="utf-8"))]
    assert hallazgos == []


def test_ca_d5_2_2_el_texto_para_el_administrador_usa_la_sintaxis_pveum_acl_modify():
    """Sintaxis de las órdenes de ejemplo (la lectura en llano es [MANUAL] y el efecto, [LAB])."""
    from proxlaunch.interfaz.textos_d import texto_admin_cpu, texto_admin_mapeo

    pci = texto_admin_mapeo(TipoMapeo.PCI, "gpu-a2", "usuario@pve")
    assert "pveum acl modify /mapping/pci/gpu-a2 --roles PVEMappingUser --users usuario@pve" in pci
    usb = texto_admin_mapeo(TipoMapeo.USB, "llave-hasp", "usuario@pve")
    assert "pveum acl modify /mapping/usb/llave-hasp --roles PVEMappingUser" in usb
    cpu = texto_admin_cpu("custom-gamer", "usuario@pve", por_mapeo=True)
    assert "pveum acl modify /mapping/cpu/gamer --roles PVEMappingUser --users usuario@pve" in cpu
    assert "Sys.Audit" in texto_admin_cpu("custom-gamer", "usuario@pve", por_mapeo=False)
