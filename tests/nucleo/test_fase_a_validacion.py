"""Reglas de validación V-A01..V-A15 de las opciones de la fase A («Comprobar»).

Requisitos: CA-A1.3.3, CA-A3.2.x, CA-A3.4.x, CA-A3.5.x, CA-A4.3.x, CA-A4.4.x, CA-A5.1.4, CA-A5.1.6,
CA-A5.2.x, CA-A0.3.3, CA-A0.4.3, CA-A1.1.6, CA-A7.3.9 (parte de núcleo), CA-A2.4.3, CL-A10..A12.
Las reglas se ejercitan con ``validar_vm`` (mismo camino para una MV individual y un lote).
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from proxlaunch.nucleo.capacidades import Capacidades, capacidades_para
from proxlaunch.nucleo.modelos.catalogo import Plantilla
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.origen import ModoClon
from proxlaunch.nucleo.modelos.vm import InterfazRed, ModeloRed
from proxlaunch.nucleo.opciones.modelos import EstadoPools, PoliticaEtiquetas, PoolsServidor
from proxlaunch.nucleo.validacion import Severidad, validar_sin_servidor, validar_vm

from .apoyo_fase_a import ROL_BASE, ROL_COMPLETO, catalogo, cfg_vm, inv_con, permisos
from .apoyo_mvp4 import cfg_clon, detalle_plantilla

CAPS = capacidades_para(Version("9.2.1", 9, 2, 1), None)
ERROR, AVISO = Severidad.ERROR, Severidad.AVISO


def _va(cfg, cat=None, caps=CAPS):
    """Problemas V-A de ``validar_vm`` (con catálogo ``cat`` o el completo por defecto)."""
    inv = inv_con(cat if cat is not None else catalogo())
    return [p for p in validar_vm(cfg, inv, caps) if p.codigo.startswith("V-A")]


def _cod(problemas, codigo):
    return [p for p in problemas if p.codigo == codigo]


def test_una_configuracion_sin_opciones_nuevas_no_produce_ningun_va():
    """Valores por defecto de 0.5.1: ninguna regla V-A se dispara (ni con catálogo sin permisos)."""
    assert _va(cfg_vm()) == []
    assert _va(cfg_vm(), catalogo(perm=permisos(ROL_BASE))) == []
    assert _va(cfg_vm(), catalogo(perm=None)) == []
    assert validar_vm(cfg_vm(), inv_con(None), CAPS) == []


# --- V-A01: orden y espera de arranque ------------------------------------------------------------


@pytest.mark.parametrize("campo", ["arranque_orden", "arranque_espera"])
@pytest.mark.parametrize("valor", [-1, -100, 2**31, 2**40, "a", "1", 1.5, True])
def test_ca_a1_3_3_orden_y_espera_invalidos_se_rechazan_nombrando_el_campo(campo, valor):
    """CA-A1.3.3 / V-A01: negativos, no numéricos o fuera de rango."""
    problemas = _cod(_va(cfg_vm(**{campo: valor})), "V-A01")
    assert len(problemas) == 1
    assert problemas[0].campo == campo and problemas[0].severidad == ERROR


@pytest.mark.parametrize("valor", [0, 1, 30, 2**31 - 1])
def test_ca_a1_3_orden_y_espera_validos_incluidos_los_limites(valor):
    assert not _cod(_va(cfg_vm(arranque_orden=valor, arranque_espera=valor)), "V-A01")


# --- V-A02: sintaxis de las etiquetas -------------------------------------------------------------


@pytest.mark.parametrize(
    "etiqueta", ["Web", "WEB", "a b", "a;b", "a,b", "#x", "-x", ".x", "+x", "a/b", "ñ", "", " "]
)
def test_ca_a3_2_1_y_a3_2_2_etiquetas_invalidas_se_rechazan_nombrandolas(etiqueta):
    """CA-A3.2.1/2: mayúsculas, espacios, ``;``, ``#``, ``-``/``.`` iniciales... nombran la
    etiqueta.
    """
    problemas = _cod(_va(cfg_vm(etiquetas_usuario=("ok", etiqueta))), "V-A02")
    assert len(problemas) == 1
    assert problemas[0].params["etiqueta"] == etiqueta
    assert problemas[0].campo == "etiquetas_usuario[1]" and problemas[0].severidad == ERROR


@pytest.mark.parametrize("etiqueta", ["web", "a", "_x", "0abc", "a-b", "a+b", "a.b", "a_b-c.d+e"])
def test_a3_2_etiquetas_validas_pasan(etiqueta):
    assert not _cod(_va(cfg_vm(etiquetas_usuario=(etiqueta,))), "V-A02")


def test_ca_a3_2_5_limite_de_longitud_de_una_etiqueta():
    """CA-A3.2.5 / arq. V-A02: 128 caracteres se aceptan; 129 se rechazan (P-14: sin tope de
    cantidad).
    """
    assert not _cod(_va(cfg_vm(etiquetas_usuario=("a" * 128,))), "V-A02")
    assert len(_cod(_va(cfg_vm(etiquetas_usuario=("a" * 129,))), "V-A02")) == 1
    muchas = tuple(f"t{i}" for i in range(200))
    assert not _cod(_va(cfg_vm(etiquetas_usuario=muchas)), "V-A02")


def test_ca_a3_2_etiquetas_no_texto_se_rechazan_sin_romper():
    problemas = _cod(_va(cfg_vm(etiquetas_usuario=(5,))), "V-A02")
    assert len(problemas) == 1


# --- V-A04 / V-A05 / V-A06: red -------------------------------------------------------------------


def _red(**kw):
    return cfg_vm(redes=[InterfazRed("vmbr0", **kw)])


@pytest.mark.parametrize("mtu", [0, -1, 2, 575, 65521, 100000, "1500", 1500.5, True])
def test_ca_a5_1_4_mtu_fuera_de_rango_o_no_numerico_se_rechaza_nombrando_la_tarjeta(mtu):
    """CA-A5.1.4 / V-A04: 575, 65521, 0, negativos y no numéricos; los parámetros nombran la
    tarjeta.
    """
    problemas = _cod(_va(_red(mtu=mtu)), "V-A04")
    assert len(problemas) == 1
    assert problemas[0].params["tarjeta"] == "1" and problemas[0].campo == "redes[0].mtu"


@pytest.mark.parametrize("mtu", [None, 1, 576, 1500, 9000, 65520])
def test_ca_a5_1_3_mtu_validos_incluidos_los_limites(mtu):
    assert not _cod(_va(_red(mtu=mtu)), "V-A04")


def test_ca_a5_1_4_el_error_nombra_la_tarjeta_correcta_en_una_mv_con_varias():
    cfg = cfg_vm(redes=[InterfazRed("vmbr0"), InterfazRed("vmbr0", mtu=575)])
    p = _cod(_va(cfg), "V-A04")
    assert [(x.campo, x.params["tarjeta"]) for x in p] == [("redes[1].mtu", "2")]


@pytest.mark.parametrize("mb", [0, -1, -0.5, math.nan, math.inf, -math.inf, "10", True])
def test_ca_a5_1_6_limite_no_positivo_o_no_finito_se_rechaza(mb):
    """CA-A5.1.6 / V-A06."""
    problemas = _cod(_va(_red(limite_mb=mb)), "V-A06")
    assert len(problemas) == 1 and problemas[0].params["tarjeta"] == "1"


@pytest.mark.parametrize("mb", [None, 1, 0.1, 12.5, 100, 10_000])
def test_ca_a5_1_6_y_p_17_limites_validos_incluidos_decimales(mb):
    assert not _cod(_va(_red(limite_mb=mb)), "V-A06")


@pytest.mark.parametrize("modelo", [ModeloRed.E1000])
def test_ca_a5_2_1_mtu_con_modelo_no_virtio_es_error_v_a05(modelo):
    """CA-A5.2.1 / CA-A5.2.4: MTU con un modelo distinto de VirtIO."""
    p = _cod(_va(_red(modelo=modelo, mtu=9000)), "V-A05")
    assert len(p) == 1 and p[0].severidad == ERROR and p[0].params["tarjeta"] == "1"


def test_ca_a5_2_virtio_con_mtu_y_e1000_sin_mtu_no_dan_v_a05():
    assert not _cod(_va(_red(mtu=9000)), "V-A05")
    assert not _cod(_va(_red(modelo=ModeloRed.E1000)), "V-A05")


def test_ca_a5_2_3_rate_con_e1000_es_valido():
    assert not _va(_red(modelo=ModeloRed.E1000, limite_mb=50))


def test_a5_un_clon_hereda_sus_redes_y_no_valida_mtu_ni_limite():
    """V-O29 (arq. §9): en un clon se saltan V-A04/05/06."""
    cfg = cfg_clon(
        "base", 9000, "pve1", efectivo=ModoClon.ENLAZADO,
        redes=[InterfazRed("vmbr0", ModeloRed.E1000, mtu=5, limite_mb=-1)],
    )  # fmt: skip
    problemas = _va(dataclasses.replace(cfg, nodo="pve1"))
    assert not {"V-A04", "V-A05", "V-A06"} & {p.codigo for p in problemas}


# --- V-A10 / V-A11 / V-A15: pool ------------------------------------------------------------------


POOLS = PoolsServidor(EstadoPools.OK, ("produccion", "pruebas"))


def test_ca_a4_4_1_pool_inexistente_bloquea_antes_de_enviar():
    """CA-A4.4.1 / V-A10: el pool de un CSV/perfil/lote que ya no existe en la lista bloquea."""
    p = _cod(_va(cfg_vm(pool="borrado"), catalogo(pools=POOLS)), "V-A10")
    assert len(p) == 1 and p[0].severidad == ERROR and p[0].params["pool"] == "borrado"
    assert p[0].campo == "pool"


def test_ca_a4_1_pool_existente_no_da_error():
    assert not _va(cfg_vm(pool="produccion"), catalogo(pools=POOLS))


@pytest.mark.parametrize(
    "estado",
    [EstadoPools.SIN_PERMISO, EstadoPools.DESCONOCIDO, EstadoPools.ERROR, EstadoPools.NO_LEIDO],
)
def test_ca_a4_4_3_pool_no_verificable_avisa_pero_no_bloquea(estado):
    """CA-A4.4.3 / P-16: sin poder validar su existencia, solo aviso V-A11 (con el estado)."""
    p = _va(cfg_vm(pool="produccion"), catalogo(pools=PoolsServidor(estado)))
    assert not _cod(p, "V-A10")
    aviso = _cod(p, "V-A11")
    assert len(aviso) == 1 and aviso[0].severidad == AVISO
    assert aviso[0].params["pool"] == "produccion" and aviso[0].params["estado"] == str(estado)


def test_ca_a4_4_3_pool_con_lista_ok_vacia_el_pool_fijado_no_existe():
    """Con ``Pool.Audit`` y sin pools (OK, ids vacío) un pool fijado sí se sabe inexistente."""
    assert (
        len(_cod(_va(cfg_vm(pool="x"), catalogo(pools=PoolsServidor(EstadoPools.OK, ()))), "V-A10"))
        == 1
    )


def test_ca_a4_3_1_con_vm_allocate_en_vms_y_sin_pool_audit_no_se_exige_nada_nuevo():
    """CA-A4.3.1: rol actual (VM.Allocate en /vms), sin Pool.Audit, pool conocido por otra vía."""
    cat = catalogo(perm=permisos(ROL_BASE), pools=PoolsServidor(EstadoPools.SIN_PERMISO))
    p = _va(cfg_vm(pool="produccion"), cat)
    assert not _cod(p, "V-A15") and not _cod(p, "V-A10")
    assert all(x.severidad == AVISO for x in p)  # solo el V-A11 de «no verificable»


def test_ca_a4_3_2_sin_vm_allocate_en_vms_ni_en_el_pool_bloquea_nombrando_las_dos_rutas():
    """CA-A4.3.2 / V-A15."""
    cat = catalogo(perm=permisos(ROL_BASE, quitar=("VM.Allocate",)), pools=POOLS)
    p = _cod(_va(cfg_vm(pool="produccion"), cat), "V-A15")
    assert len(p) == 1 and p[0].severidad == ERROR
    assert p[0].params == {"pool": "produccion", "ruta": "/vms", "ruta_pool": "/pool/produccion"}


def test_ca_a4_3_2_vm_allocate_solo_en_el_pool_basta():
    """RF-A4.3: ``VM.Allocate`` en ``/vms/<vmid>`` **o** en ``/pool/<id>``."""
    perm = permisos(
        ROL_BASE, quitar=("VM.Allocate",), extra={"/pool/produccion": {"VM.Allocate": 1}}
    )
    assert not _cod(_va(cfg_vm(pool="produccion"), catalogo(perm=perm, pools=POOLS)), "V-A15")
    assert _cod(_va(cfg_vm(pool="pruebas"), catalogo(perm=perm, pools=POOLS)), "V-A15")


def test_ca_a4_3_3_no_se_pide_pool_allocate_en_ninguna_comprobacion():
    """CA-A4.3.3: ningún problema ni parámetro menciona ``Pool.Allocate``."""
    cat = catalogo(perm=permisos(ROL_BASE, quitar=("VM.Allocate",)), pools=POOLS)
    texto = repr(_va(cfg_vm(pool="produccion", encender=True, proteger=True), cat))
    assert "Pool.Allocate" not in texto


def test_a4_sin_permisos_conocidos_el_pool_no_se_bloquea_por_privilegio():
    """CA-A0.3.2: permisos desconocidos -> no se bloquea por V-A15 (el 403 lo resolverá)."""
    assert not _cod(_va(cfg_vm(pool="produccion"), catalogo(perm=None, pools=POOLS)), "V-A15")


def test_a4_sin_pool_fijado_no_hay_reglas_de_pool():
    assert not [
        p for p in _va(cfg_vm(), catalogo(pools=POOLS)) if p.codigo in ("V-A10", "V-A11", "V-A15")
    ]


# --- V-A12: opción fijada sin privilegio o sin versión --------------------------------------------


def test_ca_a1_1_6_encender_sin_vm_powermgmt_bloquea_comprobar():
    """CA-A1.1.6 / V-A12: la opción fijada sin privilegio se bloquea nombrando privilegio y ruta."""
    cat = catalogo(perm=permisos(ROL_BASE))
    p = _cod(_va(cfg_vm(encender=True), cat), "V-A12")
    assert len(p) == 1 and p[0].severidad == ERROR and p[0].campo == "encender"
    assert p[0].params["privilegio"] == "VM.PowerMgmt"
    assert p[0].params["ruta"] == "/vms" and p[0].params["opcion"] == "encender"
    assert p[0].params["motivo"] == "opcion_sin_privilegio"


def test_ca_a0_3_3_una_opcion_no_fijada_no_bloquea_aunque_falte_su_privilegio():
    """RF-A8.1: la ausencia de ``VM.PowerMgmt`` nunca impide crear si no se pide encender."""
    cat = catalogo(perm=permisos(ROL_BASE))
    assert _cod(_va(cfg_vm(encender=False), cat), "V-A12") == []


@pytest.mark.parametrize(
    ("cambio", "opcion", "privilegio"),
    [
        ({"arranque_auto": True}, "arranque_auto", "VM.Config.Options"),
        ({"arranque_orden": 1}, "arranque_orden", "VM.Config.Options"),
        ({"arranque_espera": 5}, "arranque_orden", "VM.Config.Options"),
        ({"etiquetas_usuario": ("web",)}, "etiquetas", "VM.Config.Options"),
        ({"proteger": True}, "proteger", "VM.Config.Options"),
        ({"notas": "hola"}, "notas", "VM.Config.Options"),
        ({"notas_origen": True}, "notas", "VM.Config.Options"),
        ({"redes": [InterfazRed("vmbr0", mtu=9000)]}, "mtu", "VM.Config.Network"),
        ({"redes": [InterfazRed("vmbr0", limite_mb=5)]}, "limite_red", "VM.Config.Network"),
    ],
)
def test_ca_a0_3_3_cada_opcion_fijada_sin_su_privilegio_da_v_a12(cambio, opcion, privilegio):
    """CA-A0.3.3 / CA-A1.2.4 / CA-A5.1.8 / CA-A6.1.3: «Comprobar» no deja crear con ella."""
    cat = catalogo(perm=permisos(ROL_COMPLETO, quitar=(privilegio,)))
    p = _cod(_va(cfg_vm(**cambio), cat), "V-A12")
    assert [(x.campo, x.params["privilegio"]) for x in p] == [(opcion, privilegio)]
    assert p[0].severidad == ERROR


def test_ca_a0_3_2_con_permisos_desconocidos_no_hay_v_a12():
    """CA-A0.3.2: ``None`` -> se confía en el servidor."""
    cfg = cfg_vm(encender=True, proteger=True, arranque_auto=True, etiquetas_usuario=("a",))
    assert _cod(_va(cfg, catalogo(perm=None)), "V-A12") == []


def test_ca_a7_3_9_filas_mixtas_se_validan_por_fila():
    """CA-A7.3.9 / CL-A1: la fila que enciende falla y la que no, no."""
    cat = catalogo(perm=permisos(ROL_BASE))
    assert _cod(_va(cfg_vm(encender=True), cat), "V-A12")
    assert _cod(_va(cfg_vm(encender=False), cat), "V-A12") == []


def test_ca_a0_4_3_version_sin_soporte_de_etiquetas_bloquea_si_se_fijan():
    """CA-A0.4.3 / V-A12: etiquetas del usuario con una versión que no las admite."""
    caps = Capacidades(version=(7, 2), forzada=True)
    p = _cod(_va(cfg_vm(etiquetas_usuario=("web",)), caps=caps), "V-A12")
    assert len(p) == 1 and p[0].params["motivo"] == "opcion_sin_version"
    assert p[0].params["version"] == "7.3"


def test_a_clon_no_exige_vm_config_options_por_las_notas_ni_red():
    """RF-A2.1: en clonar la descripción va en el POST de clone, sin ``VM.Config.Options``;
    MTU/límite no aplican a un clon."""
    cat = catalogo(perm=permisos(ROL_COMPLETO, quitar=("VM.Config.Options", "VM.Config.Network")))
    cfg = dataclasses.replace(
        cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, notas="x", notas_origen=True),
        nodo="pve1",
    )
    assert _cod(_va(cfg, cat), "V-A12") == []


def test_a_clon_con_etiquetas_o_proteccion_si_exige_vm_config_options():
    """El PUT posterior al clon (tags, onboot, protection) sí exige ``VM.Config.Options``."""
    cat = catalogo(perm=permisos(ROL_COMPLETO, quitar=("VM.Config.Options",)))
    cfg = dataclasses.replace(
        cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, proteger=True), nodo="pve1"
    )
    assert [p.campo for p in _cod(_va(cfg, cat), "V-A12")] == ["proteger"]


# --- V-A03 / V-A09: política de etiquetas ---------------------------------------------------------


def _va03(cfg, politica, perm=True):
    cat = catalogo(perm=perm, politica=politica)
    return [(p.params["etiqueta"], p.params["motivo"]) for p in _cod(_va(cfg, cat), "V-A03")]


def test_ca_a3_4_1_none_bloquea_las_fijas_aunque_no_haya_etiquetas_propias():
    """CA-A3.4.1: ``user-allow=none`` y etiquetas propias vacías -> proxlaunch y lote-… bloquean."""
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"))
    assert _va03(cfg, PoliticaEtiquetas(permiso="none")) == [
        ("proxlaunch", "ninguna_permitida"),
        ("lote-x", "ninguna_permitida"),
    ]


def test_ca_a3_5_1_list_sin_proxlaunch_bloquea_con_el_campo_vacio_en_9_2():
    """CA-A3.5.1: ``list`` sin ``proxlaunch`` y sin etiquetas propias bloquea (versión ≥ 9.2)."""
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"))
    pol = PoliticaEtiquetas(permiso="list", lista_usuario=("otra",))
    assert _va03(cfg, pol) == [("proxlaunch", "no_permitida"), ("lote-x", "no_permitida")]


def test_ca_a3_4_2_list_solo_bloquea_la_propia_que_falta():
    """CA-A3.4.2: con ``[proxlaunch, lote-x]`` y propia ``web`` bloquea solo ``web``; con ``web``
    pasa.
    """
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"), etiquetas_usuario=("web",))
    assert _va03(cfg, PoliticaEtiquetas("list", ("proxlaunch", "lote-x"))) == [
        ("web", "no_permitida")
    ]
    assert _va03(cfg, PoliticaEtiquetas("list", ("proxlaunch", "lote-x", "web"))) == []


def test_ca_a3_4_2_el_campo_del_problema_apunta_a_la_etiqueta_del_usuario():
    cfg = cfg_vm(etiquetas=("proxlaunch",), etiquetas_usuario=("a", "web"))
    cat = catalogo(politica=PoliticaEtiquetas("list", ("proxlaunch", "a")))
    p = _cod(_va(cfg, cat), "V-A03")
    assert [(x.campo, x.severidad) for x in p] == [("etiquetas_usuario[1]", ERROR)]


def test_ca_a3_4_3_existing_bloquea_las_que_no_estan_en_allowed_tags():
    """CA-A3.4.3: ``existing`` con ``allowed-tags=[proxlaunch]``: lote-x y las propias bloquean."""
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"), etiquetas_usuario=("web",))
    pol = PoliticaEtiquetas("existing", existentes=("proxlaunch",))
    assert _va03(cfg, pol) == [("lote-x", "no_permitida"), ("web", "no_permitida")]


def test_ca_a3_4_4_free_sin_registradas_no_bloquea():
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"), etiquetas_usuario=("web",))
    assert _va03(cfg, PoliticaEtiquetas("free")) == []


def test_ca_a3_4_5_registrada_bloquea_sin_sys_modify_y_pasa_con_el():
    """CA-A3.4.5: ``registered-tags=[prod]`` y etiqueta ``prod``."""
    cfg = cfg_vm(etiquetas=("proxlaunch",), etiquetas_usuario=("prod",))
    pol = PoliticaEtiquetas("free", registradas=("prod",))
    assert _va03(cfg, pol) == [("prod", "registrada")]
    admin = permisos((*ROL_COMPLETO, "Sys.Modify"))
    assert _va03(cfg, pol, perm=admin) == []


def test_ca_a3_4_6_registrada_proxlaunch_bloquea_las_fijas_sin_sys_modify():
    """CA-A3.4.6: el administrador registró ``proxlaunch``: no se puede aplicar con este usuario."""
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"))
    pol = PoliticaEtiquetas("free", registradas=("proxlaunch",))
    assert _va03(cfg, pol) == [("proxlaunch", "registrada")]


@pytest.mark.parametrize("distingue", [False, True], ids=["ignora-mayusculas", "distingue"])
def test_ca_a3_4_7_case_sensitive_de_tag_style(distingue):
    """CA-A3.4.7 (cambiado por la decisión S-1, fase A §15): ``Web`` en la lista y etiqueta
    ``web``: la comparación es exacta, así que se bloquea con o sin ``case-sensitive``."""
    cfg = cfg_vm(etiquetas_usuario=("web",))
    pol = PoliticaEtiquetas("list", ("Web",), distingue_mayusculas=distingue)
    assert bool(_va03(cfg, pol)) is True


def test_ca_a3_4_8_politica_ausente_se_interpreta_como_free():
    """CA-A3.4.8: centro de datos sin ``user-tag-access`` = free."""
    assert PoliticaEtiquetas.desde_opciones({}).permiso == "free"
    assert (
        _va03(cfg_vm(etiquetas=("proxlaunch",), etiquetas_usuario=("web",)), PoliticaEtiquetas())
        == []
    )


def test_ca_a3_4_9_politica_no_legible_avisa_y_no_bloquea():
    """CA-A3.4.9 / CL-A12 / P-15: fallo de ``/cluster/options`` -> aviso V-A09, nunca error."""
    cat = catalogo(politica=None, politica_fallida=True)
    p = _va(cfg_vm(etiquetas=("proxlaunch",), etiquetas_usuario=("web",)), cat)
    assert [(x.codigo, x.severidad) for x in p] == [("V-A09", AVISO)]


def test_ca_a3_4_9_sin_etiquetas_que_enviar_no_se_avisa_de_la_politica():
    cat = catalogo(politica=None, politica_fallida=True)
    assert _cod(_va(cfg_vm(), cat), "V-A09") == []


def test_ca_a3_5_la_politica_aun_no_leida_no_avisa():
    """Un catálogo armado a mano (sin intento de lectura) no produce V-A09."""
    cat = catalogo(politica=None, politica_fallida=False)
    assert _cod(_va(cfg_vm(etiquetas=("proxlaunch",)), cat), "V-A09") == []


def test_ca_a3_4_10_el_bloqueo_es_un_error_que_impide_crear_antes_de_enviar():
    """CA-A3.4.10: V-A03 es ERROR; ``ServicioCreacion._validar_local`` lo trata como bloqueo."""
    cfg = cfg_vm(etiquetas=("proxlaunch",))
    p = _va(cfg, catalogo(politica=PoliticaEtiquetas("none")))
    assert any(x.severidad == ERROR for x in p)


def test_ca_a3_5_2_sin_etiquetar_no_se_evalua_lote_x():
    """CA-A3.5.2: si ``lote-…`` no está en la configuración (no se envía), no se evalúa."""
    cfg = cfg_vm(etiquetas=("proxlaunch",))  # sin lote-x
    pol = PoliticaEtiquetas("list", ("proxlaunch",))
    assert _va03(cfg, pol) == []


def test_ca_a3_4_la_politica_se_aplica_en_cualquier_version_p_2():
    """P-2: bloquea en cualquier versión (en un clon el PUT posterior sí la comprueba)."""
    cfg = cfg_vm(etiquetas=("proxlaunch",))
    cat = catalogo(politica=PoliticaEtiquetas("none"))
    for version in ((8, 0), (9, 1), (9, 2)):
        assert _cod(_va(cfg, cat, Capacidades(version=version, forzada=True)), "V-A03")


# --- V-A13: clon con notas y plantilla ilegible ---------------------------------------------------


def _cat_con_plantilla(**det):
    d = dataclasses.replace(detalle_plantilla(), **det)
    return catalogo(plantillas=(Plantilla(9000, "base", "pve1", None, None, d),))


def _clon_cfg(**kw):
    return dataclasses.replace(
        cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, **kw), nodo="pve1"
    )


def test_ca_a2_4_3_clon_con_notas_y_descripcion_ilegible_avisa_sin_bloquear():
    """CA-A2.4.3 / V-A13: aviso (no se envía ``description``)."""
    cat = _cat_con_plantilla(descripcion_legible=False)
    p = _va(_clon_cfg(notas_origen=True), cat)
    assert [(x.codigo, x.severidad) for x in _cod(p, "V-A13")] == [("V-A13", AVISO)]
    assert not any(x.severidad == ERROR for x in p)


def test_ca_a2_4_3_sin_notas_no_hay_v_a13():
    cat = _cat_con_plantilla(descripcion_legible=False)
    assert _cod(_va(_clon_cfg(notas_origen=False), cat), "V-A13") == []


def test_ca_a2_4_3_con_plantilla_legible_no_hay_v_a13():
    cat = _cat_con_plantilla(descripcion="algo")
    assert _cod(_va(_clon_cfg(notas_origen=True), cat), "V-A13") == []


# --- Capa 1 (sin servidor) ------------------------------------------------------------------------


def test_v_a_sin_servidor_las_reglas_puras_se_evaluan_en_csv_perfiles_y_lotes():
    """Arq. §9: V-A01, 02, 04, 05, 06, 07, 08 y 14 se evalúan sin servidor; las de catálogo no."""
    cfg = cfg_vm(
        arranque_orden=-1,
        etiquetas_usuario=("Web",),
        redes=[InterfazRed("vmbr0", ModeloRed.E1000, mtu=100, limite_mb=0)],
        notas="x\x00" + "y" * 8200,
        pool="no-verificable",
        encender=True,
    )
    codigos = {p.codigo for p in validar_sin_servidor(cfg)}
    assert {"V-A01", "V-A02", "V-A04", "V-A05", "V-A06", "V-A07", "V-A14"} <= codigos
    assert not {"V-A03", "V-A09", "V-A10", "V-A11", "V-A12", "V-A13", "V-A15"} & codigos


def test_v_a_sin_servidor_una_configuracion_por_defecto_no_da_problemas_va():
    assert [p for p in validar_sin_servidor(cfg_vm()) if p.codigo.startswith("V-A")] == []
