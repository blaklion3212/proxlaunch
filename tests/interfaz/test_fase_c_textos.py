"""Catálogo de textos de la fase C (0.8.0): cada regla V-C y cada error nuevo tiene su mensaje en
español llano, sin códigos crudos ni marcadores sin sustituir, y todo es traducible.

Derivadas de docs/requisitos/fase-c.md: CA-C0.6.1 y CA-C7.1.1 (existen los textos de cada V-C y
concepto del glosario), CA-C0.6.2 (el motivo de un control deshabilitado es visible), CA-C7.1.3
(los textos viven en ``textos*.py``/``ayuda.py`` con parámetros nombrados, sin concatenar),
CA-C5.2.1 a CA-C5.2.3 (filas «Qué puedo hacer»), CA-C6.3.4 (errores de celda del CSV con fila y
columna) y §12 (V-C01 a V-C52).
"""

from __future__ import annotations

import ast
import itertools
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator

from proxlaunch.interfaz import textos_c, textos_inventario
from proxlaunch.interfaz.ayuda import (
    CAMPOS_AYUDA_FASE_C,
    ayuda,
    texto_pedir_al_administrador,
)
from proxlaunch.interfaz.textos import (
    texto_aviso_origen,
    texto_error,
    texto_estado_opcion,
    texto_generico,
    texto_linea_problema,
    texto_problema,
)
from proxlaunch.interfaz.textos_c import (
    VIAS_FASE_C,
    texto_aviso_c,
    texto_error_c,
    texto_estado_fila_c,
    texto_explicacion_fila_c,
    texto_problema_c,
    texto_via_c,
)
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.csv_importacion.modelos import ProblemaCelda
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import Politica
from proxlaunch.nucleo.inventario.modelos import MotivoNoDeshacible
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.disponibilidad_c import disponibilidad_fase_c
from proxlaunch.nucleo.opciones.modelos import OpcionC
from proxlaunch.nucleo.origen.capacidades_origen import (
    Disponibilidad,
    EstadoVia,
    Via,
    calcular_capacidades,
)
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_fase_a import caps_de

RAIZ = Path(__file__).resolve().parents[2] / "src" / "proxlaunch"
CATALOGO = RAIZ / "recursos" / "traducciones" / "proxlaunch_es.ts"
GENERICO_ESTADO = "No disponible."
VERSIONES = [(8, 0), (8, 1), (8, 4), (9, 0), (9, 1), (9, 2)]
TARJETA = {"tarjeta": "net1"}

# Un caso por rama de texto de cada regla V-C (con los parámetros que pone el núcleo).
CASOS_V_C: list[tuple[str, dict[str, str], Severidad]] = [
    ("V-C10", {"vnet": "prod", **TARJETA}, Severidad.ERROR),
    ("V-C11", {"vnet": "prod", "nodo": "pve2", **TARJETA}, Severidad.ERROR),
    ("V-C14", {"mtu": "9000", "mtu_red": "1500", "red": "vmbr0", **TARJETA}, Severidad.AVISO),
    ("V-C15", TARJETA, Severidad.ERROR),
    ("V-C16", {"tarjeta": "1"}, Severidad.ERROR),
    ("V-C17", {"maximo": "32"}, Severidad.ERROR),
    ("V-C18", {}, Severidad.AVISO),
    ("V-C19", {"red": "prod", "plantilla": "base"}, Severidad.AVISO),
    ("V-C20", TARJETA, Severidad.AVISO),
    ("V-C21", {}, Severidad.ERROR),
    ("V-C30", {"grupo": "web-01"}, Severidad.ERROR),
    ("V-C31", {}, Severidad.ERROR),
    ("V-C32", {}, Severidad.ERROR),
    ("V-C33", {}, Severidad.AVISO),
    ("V-C34", {}, Severidad.AVISO),
    ("V-C35", {"plantilla": "base", "motivo": "heredado"}, Severidad.AVISO),
    ("V-C35", {"plantilla": "base", "motivo": "no_comprobable"}, Severidad.AVISO),
    ("V-C35", {"plantilla": "base", "motivo": "tarjeta_ilegible", **TARJETA}, Severidad.AVISO),
    ("V-C36", {}, Severidad.ERROR),
    ("V-C36", {}, Severidad.AVISO),
    ("V-C37", {}, Severidad.AVISO),
    ("V-C38", {"grupo": "web-01"}, Severidad.AVISO),
    ("V-C39", {"validos": "bloquear, permitir", "ejemplo": "bloquear"}, Severidad.ERROR),
    ("V-C40", {"privilegio": "VM.Config.Network", "ruta": "/vms"}, Severidad.ERROR),
    ("V-C50", {"version": "8.0"}, Severidad.ERROR),
    ("V-C51", {}, Severidad.ERROR),
    ("V-C52", {}, Severidad.ERROR),
]


def problema(codigo: str, params: dict[str, str], severidad=Severidad.ERROR) -> Problema:
    return Problema("campo", codigo, severidad, dict(params))


def id_caso(caso) -> str:
    return caso[0] + ":" + ",".join(f"{k}={v}" for k, v in caso[1].items()) + f":{caso[2].value}"


def limpio(texto: str, codigo: str = "") -> None:
    """Sin códigos crudos, sin marcadores sin sustituir y sin «?» suelto de dato ausente."""
    assert texto
    if codigo:
        assert codigo not in texto, codigo
    assert "{" not in texto and "}" not in texto, texto
    assert re.search(r"\bV-C\d\d\b|\bE-C\d\d\b", texto) is None, texto
    assert "?" not in re.sub(r"[¿][^?]*\?", "", texto), texto


# --- CA-C0.6.1 / §12: un mensaje para cada regla V-C ---


@pytest.mark.parametrize("caso", CASOS_V_C, ids=id_caso)
def test_ca_c0_6_1_cada_regla_v_c_tiene_su_mensaje_y_no_cae_al_texto_generico(caso):
    codigo, params, severidad = caso
    p = problema(codigo, params, severidad)
    texto = texto_problema_c(p)
    assert texto is not None
    assert texto != texto_generico(), codigo
    limpio(texto, codigo)


@pytest.mark.parametrize("caso", CASOS_V_C, ids=id_caso)
def test_ca_c0_6_1_textos_py_delega_en_textos_c_y_da_el_mismo_mensaje(caso):
    codigo, params, severidad = caso
    p = problema(codigo, params, severidad)
    assert texto_problema(p) == texto_problema_c(p)


CASOS_SIN_PARAMETROS = [pytest.param(c, id=id_caso(c)) for c in CASOS_V_C]


@pytest.mark.parametrize("caso", CASOS_SIN_PARAMETROS)
def test_ca_c0_6_1_sin_parametros_el_mensaje_nunca_deja_un_marcador_ni_lanza(caso):
    """Un dato ausente se sustituye por un texto neutro (``_Seguro``), nunca por ``{x}``."""
    codigo, _, severidad = caso
    texto = texto_problema_c(problema(codigo, {}, severidad))
    assert texto is not None
    limpio(texto, codigo)


def test_ca_c0_6_1_las_v_c_que_no_son_de_c_o_son_de_inventario_no_las_traduce_textos_c():
    for codigo in ("V-C01", "V-C02", "V-C06", "V-C09", "V-05", "V-L11"):
        assert texto_problema_c(problema(codigo, {})) is None


def test_ca_c0_6_1_las_reglas_que_pueden_dar_error_y_aviso_cambian_de_texto_con_la_severidad():
    error = texto_problema_c(problema("V-C36", {}, Severidad.ERROR))
    aviso = texto_problema_c(problema("V-C36", {}, Severidad.AVISO))
    assert error != aviso and "Podrás usar la consola" in aviso


def test_ca_c0_6_1_v_c15_nombra_el_rango_y_da_un_ejemplo():
    texto = texto_problema_c(problema("V-C15", TARJETA))
    assert "1" in texto and "4094" in texto and "20" in texto


def test_ca_c0_6_1_v_c11_v_c10_nombran_la_red_y_v_c40_el_privilegio_y_la_ruta():
    assert "prod" in texto_problema_c(problema("V-C10", {"vnet": "prod"}))
    assert "pve2" in texto_problema_c(problema("V-C11", {"vnet": "prod", "nodo": "pve2"}))
    v40 = texto_problema_c(problema("V-C40", {"privilegio": "VM.Config.Network", "ruta": "/vms"}))
    assert "VM.Config.Network" in v40 and "/vms" in v40


def test_ca_c0_6_1_v_c30_nombra_el_grupo_y_v_c50_la_version():
    assert "web-01" in texto_problema_c(problema("V-C30", {"grupo": "web-01"}))
    assert "8.0" in texto_problema_c(problema("V-C50", {"version": "8.0"}))


def test_ca_c0_6_1_un_nombre_del_servidor_con_marcadores_no_rompe_el_mensaje():
    """Los nombres vienen del servidor (no confiables): un ``{x}`` literal no es un marcador."""
    for nombre in ("{0}", "{grupo}", "a{b", "}}"):
        texto = texto_problema_c(problema("V-C30", {"grupo": nombre}))
        assert nombre in texto  # el nombre del servidor se muestra tal cual


def test_ca_c0_6_1_v_c13_sin_vnets_tiene_un_texto_por_version():
    antes = textos_c.texto_sin_vnets(False)
    desde = textos_c.texto_sin_vnets(True)
    assert antes and desde and antes != desde
    limpio(antes)
    limpio(desde)


# --- V-C01 a V-C09 (inventario): sus textos, sin códigos crudos ---


@pytest.mark.parametrize("motivo", list(MotivoNoDeshacible), ids=lambda m: m.value)
def test_ca_c0_6_1_cada_motivo_de_no_deshacible_tiene_texto_llano(motivo):
    params = {
        "falta": "proxlaunch",
        "otro": "ab12cd34",
        "bloqueo": "backup",
        "nodo": "pve2",
        "vmid": "101",
    }
    texto = textos_inventario.texto_motivo(motivo, params, "xyz")
    limpio(texto)
    assert "_" not in texto  # nunca el valor interno («falta_etiqueta»)


@pytest.mark.parametrize("motivo", list(MotivoNoDeshacible), ids=lambda m: m.value)
def test_ca_c0_6_1_los_motivos_sin_parametros_tampoco_dejan_marcadores(motivo):
    limpio(textos_inventario.texto_motivo(motivo, {}, ""))


def test_ca_c0_6_1_los_textos_v_c01_v_c02_v_c06_v_c07_v_c09_existen_y_nombran_su_dato():
    assert (
        "VM.Audit" in textos_inventario.texto_sin_lotes_visibles()
        or textos_inventario.texto_sin_lotes_visibles()
    )
    v02 = textos_inventario.texto_codigo_invalido("zz")
    assert "zz" in v02 and "ab12cd34" in v02
    v06 = textos_inventario.texto_pedir_codigo("ab12cd34")
    assert "ab12cd34" in v06
    assert textos_inventario.texto_lote_abierto_en_sesion()
    v09 = textos_inventario.texto_demasiadas_marcadas()
    assert "100" in v09 and "%n" not in v09
    for t in (
        textos_inventario.texto_sin_lotes_visibles(),
        v02,
        v06,
        textos_inventario.texto_lote_abierto_en_sesion(),
        v09,
        textos_inventario.texto_ninguna_deshacible(),
    ):
        limpio(t)


def test_v_c04_con_nota_de_otro_lote_nombra_el_otro_lote():
    texto = textos_inventario.texto_motivo(
        MotivoNoDeshacible.NOTA_OTRO_LOTE, {"otro": "ff00ff00"}, "x"
    )
    assert "ff00ff00" in texto


# --- CA-C0.6.1: un mensaje para cada error nuevo de la fase C ---

CODIGOS_ERROR_C = [
    (CodigoError.RED_CONFIG_ILEGIBLE, {}),
    (CodigoError.RED_PLANTILLA_CAMBIADA, {}),
    (CodigoError.RED_CONFIG_CAMBIADA, {}),
    (CodigoError.RED_SIN_DIRECCIONES, {}),
    (CodigoError.RED_SIN_DIRECCIONES, {"zona": "dc1"}),
    (CodigoError.FIREWALL_GRUPO_INEXISTENTE, {"grupo": "web-01"}),
    (CodigoError.FIREWALL_GRUPO_INEXISTENTE, {}),
    *[
        (
            CodigoError.PERMISO_INSUFICIENTE,
            {"ajuste": a, "privilegio": "VM.Config.Network", "ruta": "/vms/101"},
        )
        for a in ("red", "firewall_opciones", "firewall_regla")
    ],
    *[
        (CodigoError.PERMISO_INSUFICIENTE, {"ajuste": a})
        for a in ("red", "firewall_opciones", "firewall_regla")
    ],
    (CodigoError.PERMISO_INSUFICIENTE, {"zona": "dc1", "red": "prod"}),
    (CodigoError.PERMISO_INSUFICIENTE, {"zona": "dc1", "red": "prod", "tarjeta": "net1"}),
    (CodigoError.PERMISO_INSUFICIENTE, {"zona": "dc1", "red": "prod", "lado": "plantilla"}),
    (
        CodigoError.PERMISO_INSUFICIENTE,
        {"zona": "dc1", "red": "prod", "lado": "antigua", "tarjeta": "net1"},
    ),
    *[
        (
            CodigoError.OPCION_SIN_PRIVILEGIO,
            {"opcion": o.value, "privilegio": "VM.Config.Network", "ruta": "/vms"},
        )
        for o in OpcionC
    ],
    *[(CodigoError.OPCION_SIN_VERSION, {"opcion": o.value, "version": "8.0"}) for o in OpcionC],
]


def id_error(caso) -> str:
    return f"{caso[0].value}:{','.join(caso[1])}"


@pytest.mark.parametrize("caso", CODIGOS_ERROR_C, ids=id_error)
def test_ca_c0_6_1_cada_error_de_la_fase_c_tiene_mensaje_propio(caso):
    codigo, params = caso
    texto = texto_error(ErrorProxLaunch(codigo, dict(params)))
    assert texto and texto != texto_generico(), codigo
    limpio(texto)
    assert codigo.value not in texto  # nunca el código crudo («red_config_ilegible»)


def test_ca_c0_6_1_todo_codigo_de_error_nuevo_de_la_fase_c_esta_en_la_prueba():
    nuevos = {
        CodigoError.RED_CONFIG_ILEGIBLE,
        CodigoError.RED_PLANTILLA_CAMBIADA,
        CodigoError.RED_CONFIG_CAMBIADA,
        CodigoError.RED_SIN_DIRECCIONES,
        CodigoError.FIREWALL_GRUPO_INEXISTENTE,
    }
    assert nuevos <= {c for c, _ in CODIGOS_ERROR_C}


def test_ca_c0_3_2_un_403_de_sdn_nombra_el_privilegio_la_zona_y_la_red():
    e = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE, {"zona": "dc1", "red": "prod", "tarjeta": "net1"}
    )
    texto = texto_error(e)
    assert "SDN.Use" in texto and "/sdn/zones/dc1/prod" in texto and "prod" in texto


def test_ca_c0_3_2_un_403_de_un_paso_c_dice_que_la_maquina_se_creo_y_nombra_el_permiso():
    e = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE,
        {"ajuste": "firewall_regla", "privilegio": "VM.Config.Network", "ruta": "/vms/101"},
    )
    texto = texto_error(e)
    assert "Se creó" in texto and "VM.Config.Network" in texto and "/vms/101" in texto
    assert "no se encendió" in texto
    # Sin la marca de paso C, el 403 sigue siendo el de siempre.
    assert "Se creó" not in texto_error(ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}))


def test_los_errores_que_no_son_de_c_no_los_traduce_texto_error_c():
    for codigo in (CodigoError.CREDENCIALES_INVALIDAS, CodigoError.SESION_EXPIRADA):
        assert texto_error_c(ErrorProxLaunch(codigo, {})) is None
    assert texto_error_c(ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {})) is None


@pytest.mark.parametrize("codigo", list(CodigoError), ids=lambda c: c.value)
def test_ca_c0_6_1_ningun_codigo_de_error_muestra_su_valor_crudo_ni_marcadores(codigo):
    texto = texto_error(ErrorProxLaunch(codigo, {}))
    assert texto
    assert "{" not in texto and "}" not in texto, texto
    if "_" in codigo.value:
        assert codigo.value not in texto, texto


# --- Avisos de máquina de la fase C ---

AVISOS_C = [
    "ajuste_pendiente:red",
    "ajuste_pendiente:firewall_opciones",
    "ajuste_pendiente:firewall_regla",
    "firewall_grupo_ya_estaba:web-01",
    "firewall_heredado",
    "red_mac_nueva:net1",
    "red_mtu_ignorada:net1",
    "red_tarjeta_ilegible:net1",
]


@pytest.mark.parametrize("codigo", AVISOS_C)
def test_ca_c0_6_1_los_avisos_a_nivel_de_maquina_de_la_fase_c_tienen_texto(codigo):
    texto = texto_aviso_origen(codigo)
    assert texto
    limpio(texto)
    assert codigo not in texto
    assert textos_c.texto_aviso_simulacion(codigo) == texto_aviso_c(codigo) or codigo.startswith(
        "ajuste_pendiente"
    )


def test_ca_c0_6_1_un_codigo_de_aviso_desconocido_no_se_inventa_texto():
    assert texto_aviso_c("no_es_de_c") == ""
    assert texto_aviso_c("ajuste_pendiente:otro") == ""


@pytest.mark.parametrize("ajuste", ["red", "firewall_opciones", "firewall_regla"])
def test_ca_c0_6_1_los_ajustes_de_c_tienen_verbo_y_sustantivo(ajuste):
    assert textos_c.texto_ajuste_verbo_c(ajuste) and textos_c.texto_ajuste_sustantivo_c(ajuste)
    assert textos_c.texto_ajuste_verbo_c("otro") == ""


# --- RF-C0.3 / CA-C0.6.2: estados de las opciones, con su motivo ---


def test_ca_c0_6_2_cada_estado_de_opcion_no_disponible_de_la_fase_c_tiene_motivo_propio():
    """Ningún estado deshabilitado o con reservas cae a «No disponible.»."""
    estados = []
    privilegios = [
        None,
        [],
        ["VM.Config.Network"],
        ["VM.Audit", "VM.Allocate"],
        ["VM.GuestAgent.Audit", "Sys.Audit"],
        list(ROL_PROXLAUNCH),
    ]
    for version, privs in itertools.product([(7, 4), *VERSIONES], privilegios):
        permisos = (
            None if privs is None else PermisosEfectivos(rutas={"/": dict.fromkeys(privs, 1)})
        )
        estados.extend(disponibilidad_fase_c(permisos, caps_de(version)).values())
    assert {e.opcion for e in estados} == set(OpcionC)
    no_libres = [e for e in estados if e.disponibilidad != Disponibilidad.SI]
    assert no_libres
    for e in no_libres:
        texto = texto_estado_opcion(e)
        assert texto and texto != GENERICO_ESTADO, (e.opcion, e.codigo, e.params)
        limpio(texto)


def test_ca_c0_6_2_el_motivo_sin_privilegio_nombra_el_privilegio_y_la_ruta():
    permisos = PermisosEfectivos(rutas={"/": {"VM.Audit": 1}})
    e = disponibilidad_fase_c(permisos, caps_de((9, 2)))[OpcionC.FIREWALL]
    texto = texto_estado_opcion(e)
    assert "VM.Config.Network" in texto and "/vms" in texto


def test_ca_c0_4_el_motivo_de_una_opcion_sin_version_nombra_la_version_minima():
    e = disponibilidad_fase_c(None, Capacidades((7, 4), True))[OpcionC.RED_CLON]
    texto = texto_estado_opcion(e)
    assert "8.0" in texto
    assert "Proxmox" in texto or "versión" in texto


@pytest.mark.parametrize("opcion", list(OpcionC), ids=lambda o: o.value)
def test_ca_c0_6_1_cada_opcion_de_c_tiene_nombre_llano(opcion):
    nombre = textos_c.texto_nombre_opcion_c(opcion.value)
    assert nombre and "_" not in nombre
    assert textos_c.texto_nombre_opcion_c("otra") == ""


# --- RF-C5.2: filas de «Qué puedo hacer» ---


def _vias(permisos, version=(9, 2)):
    from .apoyo_mvp4 import inv_origen

    inv = inv_origen(permisos_efectivos=permisos)
    return calcular_capacidades(Capacidades(version, False), inv, None).vias


def _permisos_sin(*quitar):
    return PermisosEfectivos(rutas={"/": {p: 1 for p in ROL_PROXLAUNCH if p not in quitar}})


@pytest.mark.parametrize("via", VIAS_FASE_C, ids=lambda v: v.value)
def test_ca_c5_2_1_con_el_doble_completo_cada_fila_dice_si_y_sin_motivo(via):
    estado = _vias(_permisos_sin())[via]
    assert texto_estado_fila_c(estado) == "Sí"
    assert texto_explicacion_fila_c(via, estado) == ""
    assert texto_via_c(via)


def test_ca_c5_2_1_los_nombres_de_las_cinco_filas_son_los_del_requisito():
    assert [texto_via_c(v) for v in VIAS_FASE_C] == [
        "Ver y deshacer mis lotes en el servidor",
        "Usar redes virtuales (SDN)",
        "Activar el firewall de las máquinas",
        "Saber si el firewall general está encendido",
        "Cambiar la red de las copias",
    ]
    assert texto_via_c("otra") == ""


def test_ca_c5_2_2_sin_sys_audit_el_firewall_general_dice_no_con_el_motivo_y_sin_bloquear():
    estado = _vias(_permisos_sin("Sys.Audit"))[Via.FIREWALL_GENERAL]
    assert texto_estado_fila_c(estado) == "No"
    motivo = texto_explicacion_fila_c(Via.FIREWALL_GENERAL, estado)
    assert "Sys.Audit" in motivo and "no se bloquea" in motivo
    limpio(motivo)


def test_ca_c5_2_3_con_permisos_desconocidos_las_filas_dicen_no_se_pudo_comprobar():
    vias = _vias(None)
    for via in VIAS_FASE_C:
        assert texto_estado_fila_c(vias[via]) == "No se pudo comprobar", via
        motivo = texto_explicacion_fila_c(via, vias[via])
        assert motivo and "No se pudieron comprobar" in motivo
        limpio(motivo)


def test_ca_c5_2_sin_vm_config_network_la_fila_del_firewall_dice_no():
    estado = _vias(_permisos_sin("VM.Config.Network"))[Via.FIREWALL]
    assert texto_estado_fila_c(estado) == "No"


def test_ca_c5_2_la_explicacion_de_sdn_trae_un_comando_con_marcadores_sin_datos_reales():
    estado = EstadoVia(
        Via.VNETS_SDN,
        Disponibilidad.NO,
        CodigoError.PERMISO_INSUFICIENTE,
        {"privilegio": "SDN.Use", "ruta": "/sdn/zones/<zona>"},
        "permisos_rol_ampliado",
    )
    texto = texto_explicacion_fila_c(Via.VNETS_SDN, estado)
    assert "pveum acl modify /sdn/zones/<zona>/<red>" in texto
    assert "--roles PVESDNUser" in texto and "--users <usuario>" in texto
    assert "VM.Firewall" not in texto
    assert not re.search(r"@pam|@pve|root", texto)


# --- Guía de permisos por versión (RF-C5.2, DC-2) ---


@pytest.mark.parametrize("version", VERSIONES)
def test_rf_c5_2_la_guia_de_permisos_nombra_sdn_use_y_sdn_audit_y_nunca_vm_firewall(version):
    guia = texto_pedir_al_administrador(Capacidades(version, False))
    assert "SDN.Use" in guia and "SDN.Audit" in guia
    assert "VM.Firewall" not in guia
    assert "/sdn/zones/" in guia
    assert ("VM.Monitor" in guia) == (version < (9, 0))
    assert ("VM.GuestAgent.Audit" in guia) == (version >= (9, 0))
    assert "{" not in guia and "}" not in guia


def test_rf_c5_2_la_guia_dice_que_sdn_use_no_esta_verificado_en_todas_las_versiones():
    guia = texto_pedir_al_administrador(Capacidades((9, 2), False))
    assert "No está verificado" in guia


# --- CA-C0.6.1 / CA-C7.1.1: glosario ---


@pytest.mark.parametrize("clave", CAMPOS_AYUDA_FASE_C)
def test_ca_c7_1_1_cada_ayuda_de_la_fase_c_existe_y_es_llana(clave):
    texto = ayuda(clave)
    assert texto and len(texto) > 40
    limpio(texto)


def test_ca_c7_1_1_el_glosario_de_c_tiene_los_conceptos_del_requisito():
    assert set(CAMPOS_AYUDA_FASE_C) == {
        "etiqueta", "lote_codigo", "vnet", "vlan_sdn", "firewall", "grupo_seguridad",
        "politica_entrada", "politica_salida", "mac", "dhcp_firewall", "red_clon",
    }  # fmt: skip


def test_ca_c7_1_1_cada_concepto_lleva_su_ejemplo_concreto():
    esperado = {
        "etiqueta": ("lote-ab12cd34", "pegatina"),
        "lote_codigo": ("ab12cd34",),
        "vnet": ("prod", "dc1", "bridge"),
        "vlan_sdn": ("1–4094", "20"),
        "firewall": ("Centro de datos",),
        "grupo_seguridad": ("web", "80"),
        "politica_entrada": ("Bloquear", "Permitir"),
        "politica_salida": ("Permitir", "Bloquear"),
        "mac": ("matrícula",),
        "dhcp_firewall": ("DHCP", "IP"),
        "red_clon": ("Personalizar", "MAC"),
    }
    for clave, palabras in esperado.items():
        texto = ayuda(clave)
        for palabra in palabras:
            assert palabra.lower() in texto.lower(), (clave, palabra)


# --- CA-C6.3.4: errores de celda del CSV con fila y columna, sin códigos crudos ---

CELDAS = [
    ("V-C31", "grupo_seguridad", {}),
    ("V-C39", "politica_entrada", {"validos": "bloquear, permitir", "ejemplo": "bloquear"}),
    ("V-C51", "reescribir_red", {}),
    ("E-M11.valor_no_admitido", "cortafuegos", {"validos": "si, no", "ejemplo": "si"}),
    ("E-M11.valor_no_admitido", "reescribir_red", {"validos": "si, no", "ejemplo": "si"}),
]


@pytest.mark.parametrize("celda", CELDAS, ids=lambda c: f"{c[0]}:{c[1]}")
def test_ca_c6_3_4_el_error_de_celda_dice_fila_y_columna_y_no_muestra_el_codigo(celda):
    regla, columna, params = celda
    p = ProblemaCelda(7, columna, regla, Severidad.ERROR, dict(params), "xx")
    texto = texto_linea_problema(p)
    assert texto.startswith(f"Fila 7, columna «{columna}»:")
    limpio(texto, regla)
    assert "E-M11" not in texto


def test_ca_c6_3_8_v_c51_en_csv_nombra_la_columna_reescribir_red():
    p = ProblemaCelda(3, "reescribir_red", "V-C51", Severidad.ERROR, {}, "si")
    assert "reescribir_red" in texto_linea_problema(p)


# --- CA-C7.1.3: textos en textos*.py con parámetros nombrados, sin concatenar ---


def _llamadas_translate(ruta: Path) -> list[ast.Call]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return [
        n
        for n in ast.walk(arbol)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "translate"
        and len(n.args) >= 2
    ]


@pytest.mark.parametrize("modulo", ["textos_c.py", "textos_inventario.py"])
def test_ca_c7_1_3_todo_texto_nuevo_es_un_literal_con_contexto_sin_concatenar(modulo):
    ruta = RAIZ / "interfaz" / modulo
    llamadas = _llamadas_translate(ruta)
    assert llamadas
    for c in llamadas:
        contexto, fuente = c.args[0], c.args[1]
        assert isinstance(contexto, ast.Constant) and isinstance(contexto.value, str), c.lineno
        assert isinstance(fuente, ast.Constant) and isinstance(fuente.value, str), (
            f"{modulo}:{c.lineno}: el texto debe ser un literal (sin +, f-string ni variable)"
        )


def test_ca_c7_1_3_ningun_texto_de_c_usa_alias_que_lupdate_no_detecte():
    patron = re.compile(r"\b(_tr|tr_)\s*\(")
    for relativa in (
        "interfaz/textos_c.py",
        "interfaz/textos_inventario.py",
        "interfaz/vistas/seccion_firewall.py",
        "interfaz/vistas/seccion_red_clon.py",
        "interfaz/dialogos/inventario_lotes.py",
    ):
        assert not patron.search((RAIZ / relativa).read_text(encoding="utf-8")), relativa


# --- Todos los textos de la fase C están en el catálogo .ts ---


def _catalogo() -> dict[str, set[str]]:
    por_contexto: dict[str, set[str]] = {}
    for c in ET.fromstring(CATALOGO.read_text(encoding="utf-8")).findall("context"):
        nombre = c.findtext("name") or ""
        por_contexto[nombre] = {m.findtext("source") or "" for m in c.findall("message")}
    return por_contexto


def test_los_textos_de_textos_c_estan_en_el_catalogo_en_el_contexto_textosc():
    catalogo = _catalogo()
    assert "TextosC" in catalogo
    faltan = sorted(
        {
            c.args[1].value
            for c in _llamadas_translate(RAIZ / "interfaz" / "textos_c.py")
            if c.args[0].value == "TextosC"
        }
        - catalogo["TextosC"]
    )
    assert faltan == [], faltan[:3]


def test_los_textos_de_textos_inventario_estan_en_el_catalogo():
    catalogo = _catalogo()
    fuentes = {
        (c.args[0].value, c.args[1].value)
        for c in _llamadas_translate(RAIZ / "interfaz" / "textos_inventario.py")
    }
    faltan = sorted(t for ctx, t in fuentes if t not in catalogo.get(ctx, set()))
    assert faltan == [], faltan[:3]


def test_ningun_mensaje_de_textos_c_del_catalogo_quedo_sin_literal_en_el_codigo():
    """El catálogo no arrastra textos obsoletos de ``TextosC`` que ya no existen en el código."""
    en_codigo = {
        c.args[1].value
        for c in _llamadas_translate(RAIZ / "interfaz" / "textos_c.py")
        if c.args[0].value == "TextosC"
    }
    assert _catalogo()["TextosC"] - en_codigo == set()


def test_las_ayudas_de_la_fase_c_estan_en_el_catalogo_en_el_contexto_ayuda():
    catalogo = _catalogo()
    assert "Ayuda" in catalogo
    for clave in CAMPOS_AYUDA_FASE_C:
        assert ayuda(clave) in catalogo["Ayuda"], clave


def test_lupdate_sobre_el_codigo_actual_no_encuentra_textos_de_c_que_falten_en_el_catalogo(
    tmp_path,
):
    import subprocess

    import PySide6

    lupdate = Path(next(iter(PySide6.__path__))) / "lupdate"
    if not lupdate.exists():
        pytest.skip("pyside6-lupdate no está disponible")
    salida = tmp_path / "n.ts"
    fuentes = [
        RAIZ / "interfaz" / "textos_c.py",
        RAIZ / "interfaz" / "textos_inventario.py",
        RAIZ / "interfaz" / "ayuda.py",
        RAIZ / "interfaz" / "vistas" / "seccion_firewall.py",
        RAIZ / "interfaz" / "vistas" / "seccion_red_clon.py",
        RAIZ / "interfaz" / "dialogos" / "inventario_lotes.py",
        RAIZ / "interfaz" / "dialogos" / "capacidades.py",
        RAIZ / "interfaz" / "dialogos" / "importar_csv.py",
    ]
    r = subprocess.run(  # noqa: S603
        [str(lupdate), "-extensions", "py", *map(str, fuentes), "-no-obsolete", "-ts", str(salida)],
        capture_output=True,
        text=True,
        timeout=100,
        check=False,
    )
    assert salida.exists(), r.stderr
    nuevo = ET.fromstring(salida.read_text(encoding="utf-8"))
    catalogo = _catalogo()
    faltan = sorted(
        f"{c.findtext('name')}: {(m.findtext('source') or '')[:60]}"
        for c in nuevo.findall("context")
        for m in c.findall("message")
        if (m.findtext("source") or "") not in catalogo.get(c.findtext("name") or "", set())
    )
    assert faltan == [], faltan[:5]


# --- CA-C7.1.3 / RNF: todo pasa por la traducción ---


class _TraductorMarca(QTranslator):
    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: ANN001
        return "[T]" + source_text


@pytest.fixture
def traductor(qapp):
    t = _TraductorMarca()
    QCoreApplication.installTranslator(t)
    yield t
    QCoreApplication.removeTranslator(t)


@pytest.mark.parametrize("caso", CASOS_V_C, ids=id_caso)
def test_el_mensaje_de_cada_regla_v_c_pasa_por_la_traduccion(traductor, caso):
    codigo, params, severidad = caso
    assert "[T]" in texto_problema_c(problema(codigo, params, severidad))


@pytest.mark.parametrize(
    "caso",
    [
        c
        for c in CODIGOS_ERROR_C
        if c[0] not in (CodigoError.OPCION_SIN_PRIVILEGIO, CodigoError.OPCION_SIN_VERSION)
    ],
    ids=id_error,
)
def test_el_mensaje_de_cada_error_de_c_pasa_por_la_traduccion(traductor, caso):
    codigo, params = caso
    assert "[T]" in texto_error(ErrorProxLaunch(codigo, dict(params)))


@pytest.mark.parametrize("clave", CAMPOS_AYUDA_FASE_C)
def test_las_ayudas_de_la_fase_c_pasan_por_la_traduccion(traductor, clave):
    assert "[T]" in ayuda(clave)


@pytest.mark.parametrize("codigo", AVISOS_C)
def test_los_avisos_de_c_pasan_por_la_traduccion(traductor, codigo):
    assert "[T]" in texto_aviso_c(codigo)


@pytest.mark.parametrize("via", VIAS_FASE_C, ids=lambda v: v.value)
def test_los_nombres_de_las_filas_de_que_puedo_hacer_pasan_por_la_traduccion(traductor, via):
    assert "[T]" in texto_via_c(via)


def test_la_politica_se_traduce_y_no_muestra_el_valor_interno():
    assert textos_c.texto_politica(Politica.BLOQUEAR) == "Bloquear"
    assert textos_c.texto_politica(Politica.PERMITIR) == "Permitir"
