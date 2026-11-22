"""Planificación y simulación con las opciones de la fase A.

Requisitos: RF-A0.1 (CA-A0.1.2), RF-A0.7 (CA-A0.7.1, CA-A0.7.2), CA-A2.2.1, CA-A2.3.x (plan),
CA-A3.4.10, CA-A3.4.11, CA-A3.5.1, CA-A3.5.2, CL-A1, CL-A7, CL-A8, CL-A12, RNF-A7.
La fecha de las notas es siempre la del ``RelojCalendarioFijo``.
"""

from __future__ import annotations

import dataclasses

import pytest

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.lote.modelos import AccionPeticion, EstadoMV, Severidad
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.vm import InterfazRed, ModeloRed
from proxlaunch.nucleo.opciones.modelos import (
    OpcionesLote,
    OpcionesParciales,
    PoliticaEtiquetas,
)
from proxlaunch.nucleo.opciones.notas import LIMITE_DESCRIPCION, bloque_automatico
from proxlaunch.nucleo.opciones.preparacion import aplicar_opciones_lote

from .apoyo_fase_a import (
    FECHA_FIJA_ISO,
    ID_LOTE,
    ROL_BASE,
    ClusterA,
    RelojCalendarioFijo,
    banco_a,
    catalogo,
    cfg_vm,
    ctx_notas,
    def_filas,
    def_lote,
    fila_a,
    inv_con,
    permisos,
    plan_de,
)
from .apoyo_lote import ControlAutomatico


def _banco(*, cat=None, cluster=None):
    banco = banco_a(cluster=cluster, inv=None)
    banco.inv = inv_con(cat if cat is not None else catalogo())
    return banco


def _problemas(plan, regla):
    return [p for p in plan.problemas if p.regla == regla]


def _desc(plan, i=0):
    return plan.elementos[i].cfg.descripcion


# --- CA-A0.7.1: lote homogéneo --------------------------------------------------------------------


def test_ca_a0_7_1_las_n_mvs_llevan_el_mismo_valor_de_cada_opcion_de_lote():
    """CA-A0.7.1: encender, onboot, notas, etiquetas, pool y protección iguales en las N MVs."""
    cl = ClusterA()
    cl.pools = ["produccion"]
    banco = _banco(cluster=cl)
    base = cfg_vm(
        encender=True,
        arranque_auto=True,
        notas_origen=True,
        notas="texto libre",
        etiquetas_usuario=("web", "prod"),
        pool="produccion",
        proteger=True,
        arranque_orden=2,
        arranque_espera=30,
    )
    plan = plan_de(banco, def_lote(4, plantilla_vm=base))
    assert not plan.bloqueado, plan.problemas
    assert len(plan.elementos) == 4
    campos = (
        "encender", "arranque_auto", "notas_origen", "notas", "etiquetas_usuario", "pool",
        "proteger", "arranque_orden", "arranque_espera", "descripcion", "etiquetas",
    )  # fmt: skip
    primero = plan.elementos[0].cfg
    for e in plan.elementos[1:]:
        assert [getattr(e.cfg, c) for c in campos] == [getattr(primero, c) for c in campos]
    assert primero.etiquetas_usuario == ("web", "prod")
    # Las peticiones solo difieren en los datos propios de cada MV (vmid y nombre).
    posts = [construir_parametros(e.cfg, banco.inv, (9, 2)) for e in plan.elementos]
    for p in posts:
        assert {"onboot", "startup", "description", "pool", "protection", "tags"} <= set(p)
    sin_propios = [{k: v for k, v in p.items() if k not in ("vmid", "name")} for p in posts]
    assert all(s == sin_propios[0] for s in sin_propios)


def test_ca_a0_7_1_las_opciones_de_la_definicion_prevalecen_sobre_las_de_la_plantilla():
    """DT-A10: ``definicion.opciones`` (formulario) es la fuente de las opciones de lote."""
    banco = _banco()
    plan = plan_de(
        banco,
        def_lote(2, plantilla_vm=cfg_vm(proteger=False), opciones=OpcionesLote(proteger=True)),
    )
    assert [e.cfg.proteger for e in plan.elementos] == [True, True]


def test_a0_7_sin_opciones_de_lote_se_usan_las_de_la_plantilla():
    plan = plan_de(_banco(), def_lote(2, plantilla_vm=cfg_vm(arranque_auto=True)))
    assert [e.cfg.arranque_auto for e in plan.elementos] == [True, True]


def test_ca_a0_2_3_lote_sin_opciones_nuevas_planifica_como_0_5_1():
    """CA-A0.2.3/CA-A0.1.3: valores por defecto -> ninguna clave nueva en las peticiones."""
    banco = _banco()
    plan = plan_de(banco, def_lote(3))
    assert not plan.bloqueado
    for e in plan.elementos:
        p = construir_parametros(e.cfg, banco.inv, (9, 2))
        assert not {"onboot", "startup", "description", "pool", "protection"} & set(p)
        assert e.cfg.descripcion is None


# --- CA-A0.7.2: lote por filas --------------------------------------------------------------------


def test_ca_a0_7_2_el_valor_de_la_fila_prevalece_y_la_celda_vacia_hereda():
    """CA-A0.7.2: cada petición lleva el valor de su fila; ``None`` hereda el del formulario."""
    cl = ClusterA()
    cl.pools = ["a", "b"]
    banco = _banco(cluster=cl)
    base = OpcionesLote(encender=True, arranque_auto=False, proteger=True, pool="a", notas="base")
    filas = [
        fila_a("m-01"),  # hereda todo
        fila_a("m-02", opciones=OpcionesParciales(encender=False, arranque_auto=True)),
        fila_a("m-03", opciones=OpcionesParciales(pool="b", proteger=False, notas="propia")),
        fila_a("m-04", opciones=OpcionesParciales(pool="")),  # anula el pool del lote
        fila_a("m-05", opciones=OpcionesParciales(etiquetas_usuario=("x", "y"))),
    ]
    plan = plan_de(banco, dataclasses.replace(def_filas(filas), opciones=base))
    assert not plan.bloqueado, plan.problemas
    c = [e.cfg for e in plan.elementos]
    assert [(x.encender, x.arranque_auto, x.proteger, x.pool, x.notas) for x in c] == [
        (True, False, True, "a", "base"),
        (False, True, True, "a", "base"),
        (True, False, False, "b", "propia"),
        (True, False, True, None, "base"),
        (True, False, True, "a", "base"),
    ]
    assert c[4].etiquetas_usuario == ("x", "y")
    assert all(x.etiquetas_usuario == () for x in c[:4])


def test_ca_a0_7_2_la_etiqueta_del_usuario_de_la_fila_sustituye_a_la_del_lote():
    banco = _banco()
    base = OpcionesLote(etiquetas_usuario=("lote",))
    filas = [
        fila_a("m-01"),
        fila_a("m-02", opciones=OpcionesParciales(etiquetas_usuario=("fila",))),
        fila_a("m-03", opciones=OpcionesParciales(etiquetas_usuario=())),  # () = sin las del lote
    ]
    plan = plan_de(banco, dataclasses.replace(def_filas(filas), opciones=base))
    assert [e.cfg.etiquetas_usuario for e in plan.elementos] == [("lote",), ("fila",), ()]


def test_ca_a0_7_2_notas_origen_y_notas_usuario_solo_vienen_del_lote():
    """P-5: el CSV no fija por fila las casillas de notas; ``aplicar_opciones_lote`` las toma de la
    base.
    """
    cfg = cfg_vm(notas_origen=False, notas_usuario=False)
    out = aplicar_opciones_lote(
        cfg, OpcionesLote(notas_origen=True, notas_usuario=True), OpcionesParciales(notas="x")
    )
    assert out.notas_origen is True and out.notas_usuario is True and out.notas == "x"


def test_aplicar_opciones_lote_no_toca_orden_espera_ni_redes_y_no_muta_la_entrada():
    cfg = cfg_vm(arranque_orden=3, arranque_espera=9, redes=[InterfazRed("vmbr0", mtu=9000)])
    out = aplicar_opciones_lote(cfg, OpcionesLote(arranque_auto=True), None)
    assert (out.arranque_orden, out.arranque_espera) == (3, 9)
    assert out.redes[0].mtu == 9000 and out.arranque_auto is True
    assert cfg.arranque_auto is False  # la entrada no se modifica


def test_ca_a0_7_2_lote_por_filas_sin_opciones_parciales_ni_de_lote_usa_la_config_de_cada_fila():
    banco = _banco()
    filas = [fila_a("m-01", proteger=True), fila_a("m-02")]
    plan = plan_de(banco, def_filas(filas))
    assert [e.cfg.proteger for e in plan.elementos] == [True, False]


# --- A2 en el plan: contenido del bloque ----------------------------------------------------------


def test_ca_a2_2_1_el_bloque_del_plan_lleva_version_fecha_lote_y_perfil_sin_usuario():
    """CA-A2.2.1: versión de la app, fecha fija, código del lote del plan y perfil; sin usuario."""
    banco = _banco()
    plan = plan_de(
        banco,
        def_lote(2, plantilla_vm=cfg_vm(notas_origen=True)),
        contexto_notas=ctx_notas(id_lote=None, perfil="Servidor pequeño"),
    )
    d = _desc(plan)
    assert "ProxLaunch 0.6.0" in d and FECHA_FIJA_ISO in d
    assert f"- Lote: {plan.id_lote}" in d and plan.id_lote == ID_LOTE
    assert "- Perfil: Servidor pequeño" in d
    assert "Usuario" not in d and "ana" not in d
    assert _desc(plan, 1) == d  # misma descripción en las dos MVs del lote


def test_ca_a2_2_2_sin_perfil_la_linea_se_omite_en_el_plan():
    plan = plan_de(_banco(), def_lote(1, plantilla_vm=cfg_vm(notas_origen=True)))
    assert "Perfil" not in _desc(plan) and "None" not in _desc(plan)


def test_ca_a2_3_1_con_la_casilla_el_usuario_del_plan_es_usuario_realm_sin_token():
    """CA-A2.3.1: la sesión es ``ana@pve!lab``; solo ``ana@pve`` llega a la descripción."""
    plan = plan_de(
        _banco(), def_lote(1, plantilla_vm=cfg_vm(notas_origen=True, notas_usuario=True))
    )
    d = _desc(plan)
    assert "ana@pve" in d.replace("\\", "") and "lab" not in d and "11111111" not in d


def test_ca_a2_3_2_sin_la_casilla_no_hay_datos_del_usuario():
    plan = plan_de(_banco(), def_lote(1, plantilla_vm=cfg_vm(notas_origen=True)))
    assert "ana" not in _desc(plan) and "Usuario" not in _desc(plan)


def test_ca_a2_3_3_el_usuario_solo_tiene_efecto_con_las_notas_de_origen_marcadas():
    """CA-A2.3.3: con «Añadir notas de origen» desmarcada la casilla de usuario no añade nada."""
    plan = plan_de(
        _banco(),
        def_lote(1, plantilla_vm=cfg_vm(notas_origen=False, notas_usuario=True, notas="x")),
    )
    assert _desc(plan) == "x"
    sin_texto = plan_de(
        _banco(), def_lote(1, plantilla_vm=cfg_vm(notas_origen=False, notas_usuario=True))
    )
    assert _desc(sin_texto) is None


def test_ca_a2_2_5_el_plan_usa_el_reloj_de_calendario_inyectado_y_es_determinista():
    banco = _banco()
    d = def_lote(2, plantilla_vm=cfg_vm(notas_origen=True))
    assert _desc(plan_de(banco, d)) == _desc(plan_de(_banco(), d))


def test_a2_el_texto_libre_se_conserva_tal_cual_y_se_recorta_al_final_en_el_plan():
    plan = plan_de(
        _banco(), def_lote(1, plantilla_vm=cfg_vm(notas_origen=True, notas="# t *x*\r\nfin  \n\n"))
    )
    assert _desc(plan).endswith("\n\n# t *x*\nfin") and "\r" not in _desc(plan)


# --- Límites en el plan (CL-A7, CL-A8) ------------------------------------------------------------


def _total_base():
    """Longitud del bloque automático del plan + separador ``\\n\\n`` (el texto libre se suma)."""
    plan = plan_de(_banco(), def_lote(1, plantilla_vm=cfg_vm(notas_origen=True)))
    return len(_desc(plan)) + 2


@pytest.mark.parametrize(
    ("total", "aviso", "error"),
    [
        (7499, False, False),
        (7500, True, False),
        (7501, True, False),
        (8192, True, False),
        (8193, False, True),
    ],
)
def test_cl_a7_umbrales_exactos_con_el_bloque_real_del_plan(total, aviso, error):
    """CL-A7: 7500 -> aviso; 7501 y 8192 -> aviso (no bloquea, P-11); 8193 -> error."""
    libre = total - _total_base()
    plan = plan_de(_banco(), def_lote(1, plantilla_vm=cfg_vm(notas_origen=True, notas="n" * libre)))
    assert len(_desc(plan)) == total
    assert bool(_problemas(plan, "V-A08")) is aviso
    assert bool(_problemas(plan, "V-A07")) is error
    assert plan.bloqueado is error


def test_cl_a7_el_error_de_longitud_indica_total_limite_y_sobrantes():
    libre = LIMITE_DESCRIPCION + 10 - _total_base()
    plan = plan_de(_banco(), def_lote(1, plantilla_vm=cfg_vm(notas_origen=True, notas="n" * libre)))
    (p,) = _problemas(plan, "V-A07")
    assert p.severidad == Severidad.ERROR
    assert p.params == {
        "total": str(LIMITE_DESCRIPCION + 10), "limite": str(LIMITE_DESCRIPCION), "sobran": "10",
    }  # fmt: skip


def test_cl_a7_el_aviso_y_el_error_se_agrupan_en_un_lote_homogeneo():
    """Las N MVs tienen la misma descripción: el problema no se repite N veces."""
    libre = LIMITE_DESCRIPCION + 5 - _total_base()
    plan = plan_de(_banco(), def_lote(6, plantilla_vm=cfg_vm(notas_origen=True, notas="n" * libre)))
    assert len(_problemas(plan, "V-A07")) == 1


# --- A3 en el plan: política de etiquetas ---------------------------------------------------------


def _opciones_de(politica):
    """Cuerpo de ``GET /cluster/options`` equivalente a una ``PoliticaEtiquetas``."""
    return {
        "user-tag-access": {
            "user-allow": politica.permiso,
            "user-allow-list": list(politica.lista_usuario),
        },
        "registered-tags": list(politica.registradas),
        "allowed-tags": list(politica.existentes),
        "tag-style": {"case-sensitive": int(politica.distingue_mayusculas)},
    }


def _con_politica(politica, **kw):
    """Banco cuyo inventario y cuyo servidor tienen la MISMA política (el planificador relee
    ``/cluster/options`` cuando hay etiquetas del usuario)."""
    cl = ClusterA()
    cl.opciones = _opciones_de(politica)
    return _banco(cat=catalogo(politica=politica, **kw), cluster=cl)


def test_ca_a3_5_1_list_sin_proxlaunch_y_campo_vacio_bloquea_y_nombra_las_fijas():
    """CA-A3.5.1 (versión ≥ 9.2): el plan se bloquea y nombra ``proxlaunch`` y ``lote-<id>``."""
    banco = _con_politica(PoliticaEtiquetas("list", ("otra",)))
    plan = plan_de(banco, def_lote(3))
    assert plan.bloqueado
    nombradas = {p.params["etiqueta"] for p in _problemas(plan, "V-A03")}
    assert nombradas == {"proxlaunch", f"lote-{ID_LOTE}"}
    assert all(p.params["motivo"] == "no_permitida" for p in _problemas(plan, "V-A03"))


def test_ca_a3_4_11_el_mensaje_es_unico_por_etiqueta_en_un_lote_homogeneo():
    """CA-A3.4.11: 6 MVs y una etiqueta del usuario bloqueada -> un solo V-A03."""
    banco = _con_politica(PoliticaEtiquetas("list", ("proxlaunch", f"lote-{ID_LOTE}")))
    plan = plan_de(banco, def_lote(6, plantilla_vm=cfg_vm(etiquetas_usuario=("web",))))
    web = [p for p in _problemas(plan, "V-A03") if p.params["etiqueta"] == "web"]
    assert len(web) == 1
    assert len(_problemas(plan, "V-A03")) == 1


def test_ca_a3_4_11_el_mensaje_es_unico_por_etiqueta_en_un_lote_por_filas():
    banco = _con_politica(PoliticaEtiquetas("list", ("proxlaunch", f"lote-{ID_LOTE}")))
    filas = [fila_a(f"m-0{i}", etiquetas_usuario=("web",)) for i in range(1, 5)]
    plan = plan_de(banco, def_filas(filas))
    web = [p for p in _problemas(plan, "V-A03") if p.params["etiqueta"] == "web"]
    assert len(web) == 1


def test_ca_a3_4_10_con_la_politica_bloqueando_no_se_envia_ninguna_escritura():
    """CA-A3.4.10: el plan bloqueado no reserva VMID ni crea discos: solo hubo lecturas."""
    banco = _con_politica(PoliticaEtiquetas("none"))
    plan = plan_de(banco, def_lote(2))
    assert plan.bloqueado
    assert banco.cluster.solo_lecturas
    # Aunque se intente ejecutar, la validación local rechaza cada MV antes de enviar nada.
    libro = banco.ejecutar(plan, ControlAutomatico("suspender"))
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.ERROR] * 2
    assert banco.cluster.posts == {} and banco.cluster.rutas_de_escritura() == []


def test_ca_a3_5_2_sin_etiquetar_no_se_evalua_lote_x_ni_proxlaunch():
    """CA-A3.5.2: ``etiquetar=False`` -> ``lote-…`` y ``proxlaunch`` no se envían ni evalúan."""
    banco = _con_politica(PoliticaEtiquetas("list", ("otra",)))
    plan = plan_de(banco, def_lote(2, etiquetar=False))
    assert not plan.bloqueado, plan.problemas
    assert all(e.cfg.etiquetas == () for e in plan.elementos)
    assert "tags" not in construir_parametros(plan.elementos[0].cfg, banco.inv, (9, 2))


def test_ca_a3_5_2_sin_etiquetar_las_del_usuario_si_se_evaluan():
    banco = _con_politica(PoliticaEtiquetas("list", ("otra",)))
    plan = plan_de(
        banco, def_lote(2, etiquetar=False, plantilla_vm=cfg_vm(etiquetas_usuario=("web",)))
    )
    assert [p.params["etiqueta"] for p in _problemas(plan, "V-A03")] == ["web"]


def test_ca_a3_4_5_con_sys_modify_la_registrada_pasa_en_el_plan():
    admin = permisos((*ROL_BASE, "VM.PowerMgmt", "Pool.Audit", "Sys.Modify"))
    cl = ClusterA()
    cl.opciones = _opciones_de(PoliticaEtiquetas("free", registradas=("prod",)))
    banco = _banco(
        cat=catalogo(perm=admin, politica=PoliticaEtiquetas("free", registradas=("prod",))),
        cluster=cl,
    )
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_vm(etiquetas_usuario=("prod",))))
    assert not plan.bloqueado


def test_cl_a12_politica_ilegible_en_el_plan_solo_avisa_y_no_bloquea():
    """CA-A3.4.9 / CL-A12 / P-15: ``/cluster/options`` roto -> aviso V-A09, el plan sigue."""
    cl = ClusterA()
    cl.opciones = {"user-tag-access": {"user-allow": "raro"}}
    banco = _banco(cat=catalogo(politica=None, politica_fallida=True), cluster=cl)
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_vm(etiquetas_usuario=("web",))))
    assert not plan.bloqueado
    avisos = _problemas(plan, "V-A09")
    assert len(avisos) == 1 and avisos[0].severidad == Severidad.AVISO


def test_cl_a12_el_plan_relee_la_politica_si_hay_etiquetas_y_usa_la_vigente():
    """Con etiquetas del usuario el planificador relee ``/cluster/options`` (la política vigente
    manda).
    """
    cl = ClusterA()
    cl.opciones = {"user-tag-access": {"user-allow": "none"}}
    banco = _banco(
        cat=catalogo(politica=PoliticaEtiquetas("free")), cluster=cl
    )  # inventario viejo: free
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_vm(etiquetas_usuario=("web",))))
    assert plan.bloqueado and _problemas(plan, "V-A03")


# --- A4 en el plan: pool --------------------------------------------------------------------------


def test_ca_a4_4_1_pool_que_ya_no_existe_bloquea_el_plan_antes_de_enviar():
    cl = ClusterA()
    cl.pools = ["otro"]
    banco = _banco(cluster=cl)
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_vm(pool="borrado")))
    assert plan.bloqueado and _problemas(plan, "V-A10")
    assert banco.cluster.solo_lecturas


def test_ca_a4_4_3_pool_fijado_sin_poder_listar_pools_solo_avisa():
    """CA-A4.4.3 / P-16: sin ``Pool.Audit`` (lista vacía) el pool de un CSV no se verifica."""
    cl = ClusterA()
    cl.pools = []
    banco = _banco(cat=catalogo(perm=permisos(ROL_BASE)), cluster=cl)
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_vm(pool="produccion")))
    assert not plan.bloqueado, plan.problemas
    assert _problemas(plan, "V-A11") and not _problemas(plan, "V-A10")
    assert plan.elementos[0].cfg.pool == "produccion"


def test_ca_a4_3_2_sin_vm_allocate_el_plan_se_bloquea_con_v_a15():
    cl = ClusterA()
    cl.pools = ["produccion"]
    perm = permisos(ROL_BASE, quitar=("VM.Allocate",))
    plan = plan_de(
        _banco(cat=catalogo(perm=perm), cluster=cl),
        def_lote(2, plantilla_vm=cfg_vm(pool="produccion")),
    )
    assert plan.bloqueado and _problemas(plan, "V-A15")


# --- CL-A1: lote mixto por filas ------------------------------------------------------------------


def test_cl_a1_cada_fila_se_valida_con_su_propio_indice_y_las_demas_no_se_alteran():
    """CL-A1: la fila que enciende sin ``VM.PowerMgmt`` falla; las demás conservan sus valores."""
    banco = _banco(cat=catalogo(perm=permisos(ROL_BASE)))
    filas = [
        fila_a("m-01"),
        fila_a("m-02", opciones=OpcionesParciales(encender=True)),
        fila_a("m-03", opciones=OpcionesParciales(proteger=True)),
        fila_a("m-04", opciones=OpcionesParciales(encender=True)),
    ]
    plan = plan_de(banco, def_filas(filas))
    errores = _problemas(plan, "V-A12")
    assert sorted(p.indice for p in errores) == [1, 3]
    assert all(p.params["privilegio"] == "VM.PowerMgmt" for p in errores)
    assert plan.bloqueado
    assert [e.cfg.proteger for e in plan.elementos] == [False, False, True, False]
    assert banco.cluster.solo_lecturas  # nada se envía hasta resolver


def test_cl_a1_con_vm_powermgmt_las_mismas_filas_pasan():
    banco = _banco()
    filas = [fila_a("m-01"), fila_a("m-02", opciones=OpcionesParciales(encender=True))]
    assert not plan_de(banco, def_filas(filas)).bloqueado


def test_ca_a7_3_9_lote_con_encender_sin_vm_powermgmt_bloquea_con_el_privilegio_que_falta():
    banco = _banco(cat=catalogo(perm=permisos(ROL_BASE)))
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_vm(encender=True)))
    assert plan.bloqueado
    assert [p.params["privilegio"] for p in _problemas(plan, "V-A12")] == ["VM.PowerMgmt"]


# --- RF-A0.1: simulación --------------------------------------------------------------------------


def _simular(banco, definicion, *, ctx=None, **kw):
    """Simula con calendario fijo; ``ctx`` por defecto deja ``id_lote`` a ``None`` (lo completa el
    plan, como hace la ventana)."""
    return simular(
        banco.sesion,
        definicion,
        banco.inv,
        reloj=banco.reloj,
        contexto_notas=ctx if ctx is not None else ctx_notas(id_lote=None),
        reloj_calendario=RelojCalendarioFijo(),
        **kw,
    )


def _sin_id_de_lote(parametros):
    """El id del lote es aleatorio en cada planificación: se normaliza para comparar."""
    import re

    return {k: re.sub(r"\b(?<![0-9a-f])[0-9a-f]{8}\b", "<ID>", v) for k, v in parametros.items()}


def _opciones_completas(**kw):
    return cfg_vm(
        encender=True, arranque_auto=True, arranque_orden=2, arranque_espera=30,
        notas_origen=True, notas="hola", etiquetas_usuario=("web",), pool="produccion",
        proteger=True,
        redes=[
            InterfazRed("vmbr0", mtu=9000, limite_mb=100),
            InterfazRed("vmbr0", ModeloRed.E1000),
        ],
        **kw,
    )  # fmt: skip


def test_ca_a0_1_2_la_simulacion_incluye_todas_las_peticiones_y_encender_al_final_sin_escribir():
    """CA-A0.1.2: tags, pool, description, protection, mtu, rate y encender, sin escrituras."""
    cl = ClusterA()
    cl.pools = ["produccion"]
    banco = _banco(cluster=cl)
    res = _simular(
        banco, def_lote(2, plantilla_vm=_opciones_completas()), ctx=ctx_notas(id_lote=None)
    )
    assert not res.plan.bloqueado, res.plan.problemas
    assert cl.solo_lecturas and cl.posts == {} and cl.inicios == {}
    for e in res.plan.elementos:
        detalle = res.peticiones_detalle[e.vmid]
        assert [d.accion for d in detalle] == [AccionPeticion.CREAR, AccionPeticion.ENCENDER]
        assert detalle[-1].parametros == {} and detalle[-1].nodo == e.nodo
        post = res.peticiones[e.vmid]
        assert post["onboot"] == "1" and post["startup"] == "order=2,up=30"
        assert post["pool"] == "produccion" and post["protection"] == "1"
        assert post["tags"].endswith(";web") and post["description"].endswith("\n\nhola")
        assert post["net0"] == "virtio,bridge=vmbr0,mtu=9000,rate=100"
        assert post["net1"] == "e1000,bridge=vmbr0"
        assert "start" not in post
        assert detalle[0].parametros == post


def test_ca_a0_1_2_sin_encender_la_simulacion_no_lista_encender():
    banco = _banco()
    res = _simular(banco, def_lote(2, plantilla_vm=cfg_vm(encender=False)))
    assert all(
        AccionPeticion.ENCENDER not in [d.accion for d in det]
        for det in res.peticiones_detalle.values()
    )


def test_ca_a0_1_2_la_simulacion_es_exactamente_lo_que_se_envia():
    """INV-L5 / CL-L11.3: simulación y ejecución comparten planificador: mismas peticiones."""
    cl = ClusterA()
    cl.pools = ["produccion"]
    banco = _banco(cluster=cl)
    definicion = def_lote(2, plantilla_vm=_opciones_completas())
    res = _simular(banco, definicion)
    plan = plan_de(banco, definicion, contexto_notas=ctx_notas())
    banco.ejecutar(plan, ControlAutomatico("suspender"))
    for e in plan.elementos:
        enviado = _sin_id_de_lote(cl.cuerpos_post[e.vmid])
        simulado = _sin_id_de_lote(res.peticiones[e.vmid])
        assert enviado == simulado
        assert list(enviado) == list(simulado)  # y en el mismo orden


def test_ca_a0_1_2_simulacion_de_clon_clone_config_resize_y_encender_en_orden():
    """CA-A0.1.2 / CL-A2 (clon): CLONAR, CONFIGURAR, AMPLIAR y al final ENCENDER."""
    from proxlaunch.nucleo.modelos.origen import AjustesClon

    from .apoyo_mvp4 import cfg_clon

    cl = ClusterA()
    cl.agregar_plantilla(9000, "base", "pve1", description="Plantilla")
    cl.pools = ["produccion"]
    banco = _banco(cluster=cl)
    base = dataclasses.replace(
        cfg_clon("base", ajustes=AjustesClon(cores=4, disco_gib=64)),
        encender=True, arranque_auto=True, proteger=True, pool="produccion",
        notas_origen=True, etiquetas_usuario=("web",),
        discos=cfg_vm().discos, redes=cfg_vm().redes,
    )  # fmt: skip
    res = _simular(banco, def_lote(1, plantilla_vm=base, prefijo="", relleno=0))
    assert not res.plan.bloqueado, res.plan.problemas
    (e,) = res.plan.elementos
    detalle = res.peticiones_detalle[e.vmid]
    assert [d.accion for d in detalle] == [
        AccionPeticion.CLONAR,
        AccionPeticion.CONFIGURAR,
        AccionPeticion.AMPLIAR,
        AccionPeticion.ENCENDER,
    ]  # fmt: skip
    assert detalle[0].parametros["pool"] == "produccion"
    assert detalle[0].parametros["description"].startswith("Plantilla\n\nCreada con ProxLaunch")
    cfgput = detalle[1].parametros
    assert cfgput["onboot"] == "1" and cfgput["protection"] == "1" and "web" in cfgput["tags"]
    assert cl.solo_lecturas


def test_ca_a2_1_la_simulacion_de_un_lote_sin_notas_no_lleva_description():
    banco = _banco()
    res = _simular(banco, def_lote(1, plantilla_vm=cfg_vm(notas_origen=False)))
    assert "description" not in res.peticiones[res.plan.elementos[0].vmid]


def test_ca_a0_1_2_la_simulacion_conserva_el_bloqueo_de_la_politica_sin_peticiones():
    banco = _con_politica(PoliticaEtiquetas("none"))
    res = _simular(banco, def_lote(2))
    assert res.plan.bloqueado and _problemas(res.plan, "V-A03")
    assert banco.cluster.solo_lecturas  # la simulación nunca escribe, ni con el plan bloqueado


def test_rnf_a7_la_simulacion_de_un_lote_lee_pools_y_opciones_una_sola_vez():
    cl = ClusterA()
    cl.pools = ["produccion"]
    banco = _banco(cluster=cl)
    _simular(banco, def_lote(5, plantilla_vm=cfg_vm(pool="produccion")))
    assert len(cl.llamadas_a("GET", r"^/pools$")) == 1
    assert len(cl.llamadas_a("GET", r"^/cluster/options$")) == 1


def test_bloque_automatico_de_la_simulacion_coincide_con_el_de_las_funciones_puras():
    """El bloque simulado es el de ``bloque_automatico`` con el contexto del plan (sin perfil)."""
    banco = _banco()
    res = _simular(banco, def_lote(1, plantilla_vm=cfg_vm(notas_origen=True)))
    d = res.peticiones[res.plan.elementos[0].vmid]["description"]
    esperado = bloque_automatico(ctx_notas(id_lote=res.plan.id_lote))
    assert d == esperado


def test_cl_a9_lote_de_100_mvs_con_notas_largas_y_etiquetas_se_planifica_con_un_solo_aviso():
    """CL-A9: 100 MVs con notas de ~7500 caracteres: el aviso V-A08 sale una vez (con el recuento)
    y la planificación no repite trabajo por MV (una sola lectura de pools y de opciones)."""
    from proxlaunch.nucleo.modelos.vm import Disco

    cl = ClusterA()
    cl.pools = ["produccion"]
    banco = banco_a(cluster=cl, inv=None)
    banco.inv = inv_con(catalogo())
    base = cfg_vm(
        notas_origen=True,
        notas="n" * 7450,
        etiquetas_usuario=("web", "prod"),
        pool="produccion",
        discos=[Disco("datos", 1)],
    )
    plan = plan_de(banco, def_lote(100, plantilla_vm=base))
    assert len(plan.elementos) == 100 and not plan.bloqueado, plan.problemas
    avisos = _problemas(plan, "V-A08")
    assert len(avisos) == 1 and avisos[0].params["elementos"] == "100"
    assert len(cl.llamadas_a("GET", r"^/pools$")) == 1
    assert len(cl.llamadas_a("GET", r"^/cluster/options$")) == 1
