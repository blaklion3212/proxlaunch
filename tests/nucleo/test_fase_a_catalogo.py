"""Catálogo de la fase A: pools, política de etiquetas, descripción de la plantilla y coste en GET.

Requisitos: RF-A4.1/A4.2 (estados de la lista de pools, CA-A4.1.1, CA-A4.2.1..A4.2.5),
CA-A3.4.9/CL-A12 (``/cluster/options`` que falla), RF-A2.4 (lectura de ``description`` de la
plantilla), RNF-A7 (a lo sumo dos GET por lote, ninguno por MV) y CA-O03.1 (sin opciones nuevas
no hay lecturas nuevas).
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.opciones.modelos import EstadoPools, OpcionesLote, PoliticaEtiquetas
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.origen.resolucion import necesidades_catalogo
from proxlaunch.nucleo.servicios.catalogo import (
    ServicioCatalogo,
    leer_politica_etiquetas,
    leer_pools,
)
from proxlaunch.nucleo.servicios.descubrimiento import descubrir

from .apoyo_api import TransporteFalso, crear_sesion, rutas_inventario
from .apoyo_fase_a import (
    ROL_BASE,
    ROL_COMPLETO,
    ClusterA,
    banco_a,
    catalogo,
    cfg_vm,
    def_lote,
    inv_con,
    plan_de,
)
from .apoyo_mvp4 import cfg_clon


def _cliente(pools=None, opciones=None):
    t = TransporteFalso()
    if pools is not None:
        t.en("GET", "/pools", pools)
    if opciones is not None:
        t.en("GET", "/cluster/options", opciones)
    return crear_sesion(t).cliente, t


def _perm(*privilegios, ruta="/"):
    return PermisosEfectivos(rutas={ruta: {p: 1 for p in privilegios}})


# --- leer_pools ----------------------------------------------------------------------------------


def test_ca_a4_1_1_tres_pools_dan_ok_con_los_tres_ids():
    """CA-A4.1.1: la lista ofrece los tres pools (``GET /pools``, no ``/pools/{id}``)."""
    cliente, t = _cliente(pools=[{"poolid": "a"}, {"poolid": "b"}, {"poolid": "c"}])
    p = leer_pools(cliente, _perm(*ROL_COMPLETO))
    assert (p.estado, p.ids) == (EstadoPools.OK, ("a", "b", "c"))
    assert [c.ruta for c in t.llamadas] == ["/pools"]  # una sola lectura, sin /pools/{id}


def test_a4_1_ids_duplicados_o_sin_poolid_se_descartan():
    cliente, _ = _cliente(pools=[{"poolid": "a"}, {"poolid": "a"}, {"x": 1}, {"poolid": 5}])
    assert leer_pools(cliente, None).ids == ("a",)


def test_ca_a4_2_1_lista_vacia_sin_pool_audit_es_sin_permiso():
    """CA-A4.2.1: ``/pools`` vacío y sin ``Pool.Audit`` en ``/pool``."""
    cliente, _ = _cliente(pools=[])
    assert leer_pools(cliente, _perm(*ROL_BASE)) == leer_pools(cliente, _perm(*ROL_BASE))
    assert leer_pools(cliente, _perm(*ROL_BASE)).estado == EstadoPools.SIN_PERMISO


def test_ca_a4_2_2_lista_vacia_con_pool_audit_es_ok_sin_pools():
    """CA-A4.2.2."""
    cliente, _ = _cliente(pools=[])
    p = leer_pools(cliente, _perm(*ROL_COMPLETO))
    assert (p.estado, p.ids) == (EstadoPools.OK, ())


def test_ca_a4_2_2_pool_audit_solo_en_pool_a_con_propagate_cuenta_para_pool():
    """``Pool.Audit`` en ``/pool`` con propagate (heredado a ``/pool/<id>``)."""
    cliente, _ = _cliente(pools=[])
    assert leer_pools(cliente, _perm("Pool.Audit", ruta="/pool")).estado == EstadoPools.OK


def test_ca_a4_2_4_lista_vacia_con_permisos_desconocidos_es_desconocido():
    """CA-A4.2.4."""
    cliente, _ = _cliente(pools=[])
    assert leer_pools(cliente, None).estado == EstadoPools.DESCONOCIDO


def test_ca_a4_2_3_con_pool_audit_parcial_solo_se_ofrece_lo_que_devuelve_la_api():
    """CA-A4.2.3: ``Pool.Audit`` solo en ``/pool/a``: la API devuelve solo ``a``."""
    cliente, _ = _cliente(pools=[{"poolid": "a"}])
    p = leer_pools(cliente, _perm("Pool.Audit", ruta="/pool/a"))
    assert (p.estado, p.ids) == (EstadoPools.OK, ("a",))


@pytest.mark.parametrize(
    "error",
    [
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"),
        ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {}, "596"),
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500"),
        RuntimeError("inesperado"),
    ],
)
def test_ca_a4_2_5_fallo_de_lectura_es_error_y_no_lanza(error):
    """CA-A4.2.5: el fallo de ``GET /pools`` queda como estado ERROR (no bloquea el formulario)."""
    cliente, _ = _cliente(pools=error)
    assert leer_pools(cliente, _perm(*ROL_COMPLETO)) == leer_pools(cliente, None)
    assert leer_pools(cliente, None).estado == EstadoPools.ERROR


@pytest.mark.parametrize(
    "codigo", [CodigoError.SESION_EXPIRADA, CodigoError.CREDENCIALES_INVALIDAS]
)
def test_a4_los_errores_de_sesion_no_se_ocultan_como_un_estado_de_pools(codigo):
    cliente, _ = _cliente(pools=ErrorProxLaunch(codigo, {}, "401"))
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_pools(cliente, None)
    assert exc.value.codigo == codigo


def test_a4_cuerpo_de_pools_que_no_es_lista_se_trata_como_vacio():
    cliente, _ = _cliente(pools={"no": "lista"})
    assert leer_pools(cliente, _perm(*ROL_COMPLETO)).ids == ()


# --- leer_politica_etiquetas ----------------------------------------------------------------------


def test_ca_a3_4_leer_politica_devuelve_la_politica_y_no_fallida():
    cliente, t = _cliente(
        opciones={"user-tag-access": {"user-allow": "list", "user-allow-list": ["a"]}}
    )
    pol, fallida = leer_politica_etiquetas(cliente)
    assert pol == PoliticaEtiquetas("list", ("a",)) and fallida is False
    assert [c.ruta for c in t.llamadas] == ["/cluster/options"]


def test_ca_a3_4_8_sin_user_tag_access_es_free():
    cliente, _ = _cliente(opciones={})
    assert leer_politica_etiquetas(cliente) == (PoliticaEtiquetas(), False)


@pytest.mark.parametrize(
    "fallo",
    [
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"),
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500"),
        ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {}, "596"),
        RuntimeError("tiempo agotado"),
        {"user-tag-access": {"user-allow": "raro"}},  # cuerpo inesperado
    ],
)
def test_ca_a3_4_9_cl_a12_fallo_o_cuerpo_inesperado_da_none_y_fallida(fallo):
    """CA-A3.4.9 / CL-A12: 403/5xx/tiempo agotado/cuerpo inesperado -> ``(None, True)``."""
    cliente, _ = _cliente(opciones=fallo)
    assert leer_politica_etiquetas(cliente) == (None, True)


def test_a3_4_9_errores_de_sesion_se_propagan():
    cliente, _ = _cliente(opciones=ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "401"))
    with pytest.raises(ErrorProxLaunch):
        leer_politica_etiquetas(cliente)


# --- descubrir y ServicioCatalogo.leer_para -------------------------------------------------------


def _transporte_inventario(pools, opciones):
    t = TransporteFalso()
    rutas_inventario(t, "9.2")
    t.en("GET", "/pools", pools)
    t.en("GET", "/cluster/options", opciones)
    return t


def test_rnf_a7_descubrir_lee_pools_y_opciones_una_sola_vez():
    """RNF-A7: dos GET por conexión (``/cluster/options`` y ``/pools``)."""
    t = _transporte_inventario([{"poolid": "a"}], {})
    inv = descubrir(crear_sesion(t))
    assert len(t.llamadas_a("GET", "/pools")) == 1
    assert len(t.llamadas_a("GET", "/cluster/options")) == 1
    assert inv.catalogo is not None
    assert inv.catalogo.pools.estado == EstadoPools.OK and inv.catalogo.pools.ids == ("a",)
    assert inv.catalogo.politica_etiquetas == PoliticaEtiquetas()
    assert inv.catalogo.politica_etiquetas_fallida is False


def test_ca_a3_4_9_descubrir_con_cluster_options_caido_no_falla():
    """CL-A12: sin ``Sys.Audit`` no se puede leer la política; el descubrimiento sigue."""
    t = _transporte_inventario([], ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"))
    c = descubrir(crear_sesion(t)).catalogo
    assert c is not None
    assert c.politica_etiquetas is None and c.politica_etiquetas_fallida
    assert c.pools.estado in (EstadoPools.OK, EstadoPools.SIN_PERMISO)


def test_ca_a4_2_1_descubrir_sin_pool_audit_marca_sin_permiso():
    """CA-A4.2.1 de extremo a extremo: ``/access/permissions`` sin ``Pool.Audit`` y ``/pools``
    vacío.
    """
    t = _transporte_inventario([], {})
    t.en("GET", "/access/permissions", {"/": {p: 1 for p in ROL_BASE}})
    c = descubrir(crear_sesion(t)).catalogo
    assert c is not None and c.pools.estado == EstadoPools.SIN_PERMISO


def test_ca_a4_2_2_descubrir_con_pool_audit_y_sin_pools_es_ok_vacio():
    t = _transporte_inventario([], {})
    t.en("GET", "/access/permissions", {"/": {p: 1 for p in ROL_COMPLETO}})
    c = descubrir(crear_sesion(t)).catalogo
    assert c is not None
    assert (c.pools.estado, c.pools.ids) == (EstadoPools.OK, ())


def test_ca_a4_2_4_descubrir_con_permisos_ilegibles_y_sin_pools_es_desconocido():
    t = _transporte_inventario([], {})
    t.en("GET", "/access/permissions", ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"))
    c = descubrir(crear_sesion(t)).catalogo
    assert c is not None
    assert c.permisos is None and c.pools.estado == EstadoPools.DESCONOCIDO


def _servicio(cluster=None):
    banco = banco_a(cluster=cluster)
    return banco, ServicioCatalogo(banco.sesion, banco.reloj)


def test_ca_o03_1_leer_para_sin_opciones_no_hace_lecturas_nuevas_y_conserva_lo_previo():
    """CA-O03.1: ``opciones=False`` (por defecto) conserva pools y política del inventario."""
    banco, servicio = _servicio()
    previo = catalogo(
        pools=type(catalogo().pools)(EstadoPools.OK, ("a",)),
        politica=PoliticaEtiquetas("list", ("x",)),
    )
    inv = inv_con(previo)
    nuevo = servicio.leer_para(inv, necesidades_catalogo([]), ["pve1"])
    assert banco.cluster.llamadas == []  # ni una sola petición
    assert nuevo.pools == previo.pools and nuevo.politica_etiquetas == previo.politica_etiquetas
    assert nuevo.permisos == previo.permisos


def test_rnf_a7_leer_para_con_opciones_lee_exactamente_dos_get():
    """RNF-A7: ``opciones=True`` -> ``GET /pools`` y ``GET /cluster/options``, una vez cada uno."""
    cl = ClusterA()
    cl.pools = ["a", "b"]
    cl.opciones = {"user-tag-access": {"user-allow": "none"}}
    banco, servicio = _servicio(cl)
    nuevo = servicio.leer_para(
        inv_con(catalogo()), necesidades_catalogo([]), ["pve1"], opciones=True
    )
    rutas = sorted(c.ruta for c in cl.llamadas)
    assert rutas == ["/cluster/options", "/pools"]
    assert nuevo.pools.ids == ("a", "b") and nuevo.politica_etiquetas.permiso == "none"
    assert banco.cluster.metodos["GET"] == 2 and cl.solo_lecturas


def test_ca_a4_2_5_leer_para_con_pools_caido_no_bloquea_el_resto():
    cl = ClusterA()
    cl.pools = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    _, servicio = _servicio(cl)
    nuevo = servicio.leer_para(
        inv_con(catalogo()), necesidades_catalogo([]), ["pve1"], opciones=True
    )
    assert nuevo.pools.estado == EstadoPools.ERROR
    assert nuevo.politica_etiquetas == PoliticaEtiquetas()


# --- RF-A2.4: descripción de la plantilla ---------------------------------------------------------


@pytest.mark.parametrize(
    ("config", "esperada"),
    [
        ({"description": "Plantilla Ubuntu"}, "Plantilla Ubuntu"),
        ({"description": ""}, ""),
        ({}, None),  # sin la clave: la plantilla no tiene notas
        ({"description": 5}, None),  # texto no confiable: se ignora
        ({"description": None}, None),
        ({"description": ["a"]}, None),
    ],
)
def test_ca_a2_4_detalle_de_config_lee_la_descripcion(config, esperada):
    """CA-A2.4.1/A2.4.2: ``description`` de la plantilla (``None`` si falta o no es texto)."""
    detalle = detalle_de_config({"template": 1, **config})
    assert detalle.descripcion == esperada and detalle.descripcion_legible is True


def test_ca_a2_4_3_detalle_plantilla_403_devuelve_none_y_no_pisa_las_notas():
    """P-10: sin permiso para leer la plantilla ``detalle_plantilla`` da ``None``."""
    cl = ClusterA()
    cl.agregar_plantilla(9000, "base", "pve1", description="notas de la plantilla")
    cl.regla(
        "GET",
        r"/qemu/9000/config$",
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"),
    )
    _, servicio = _servicio(cl)
    assert servicio.detalle_plantilla("pve1", 9000) is None


def test_ca_a2_4_4_el_servicio_lee_la_descripcion_vigente_de_la_plantilla():
    cl = ClusterA()
    cl.agregar_plantilla(9000, "base", "pve1", description="v1")
    _, servicio = _servicio(cl)
    assert servicio.detalle_plantilla("pve1", 9000).descripcion == "v1"
    cl.plantillas[9000]["config"]["description"] = "v2"
    assert servicio.detalle_plantilla("pve1", 9000).descripcion == "v2"


# --- RNF-A7 en el planificador: ninguna lectura por MV --------------------------------------------


def _gets(banco, ruta):
    return len(banco.cluster.llamadas_a("GET", rf"^{ruta}$"))


def test_rnf_a7_un_lote_con_pool_y_etiquetas_lee_pools_y_opciones_una_vez_no_por_mv():
    """RNF-A7: lote de 8 MVs con pool y etiquetas -> 1 GET /pools y 1 GET /cluster/options."""
    cl = ClusterA()
    cl.pools = ["produccion"]
    banco = banco_a(cluster=cl)
    base = cfg_vm(pool="produccion", etiquetas_usuario=("web",))
    plan = plan_de(banco, def_lote(8, plantilla_vm=base))
    assert len(plan.elementos) == 8
    assert _gets(banco, "/pools") == 1 and _gets(banco, "/cluster/options") == 1


def test_ca_o03_1_un_lote_sin_pool_ni_etiquetas_no_lee_pools_ni_opciones():
    """CA-O03.1 / RNF-A7: sin opciones que lo pidan, el plan no añade ninguna lectura."""
    banco = banco_a()
    plan_de(banco, def_lote(4))
    assert _gets(banco, "/pools") == 0 and _gets(banco, "/cluster/options") == 0


def test_rnf_a7_las_opciones_de_lote_tambien_disparan_la_lectura():
    """El pool fijado en ``definicion.opciones`` (formulario) también lee pools y política."""
    cl = ClusterA()
    cl.pools = ["p"]
    banco = banco_a(cluster=cl)
    d = def_lote(3, opciones=OpcionesLote(pool="p"))
    plan_de(banco, d)
    assert _gets(banco, "/pools") == 1 and _gets(banco, "/cluster/options") == 1


def test_a_plan_de_una_mv_clon_lee_la_descripcion_de_la_plantilla_en_el_catalogo():
    """RF-A2.4: la descripción de la plantilla llega al plan por el catálogo (una lectura por
    plantilla).
    """
    cl = ClusterA()
    cl.agregar_plantilla(9000, "base", "pve1", description="Plantilla Ubuntu")
    banco = banco_a(cluster=cl, inv=None)
    cfg: ConfiguracionVM = cfg_clon("base", notas_origen=True, storage_destino=None)
    cfg = _con_hw(cfg)
    plan = plan_de(banco, def_lote(1, plantilla_vm=cfg, prefijo="", relleno=0))
    assert plan.elementos, plan.problemas
    desc = plan.elementos[0].cfg.descripcion
    assert desc is not None and desc.startswith("Plantilla Ubuntu\n\nCreada con ProxLaunch")


def _con_hw(cfg):
    """Un clon con la configuración de hardware mínima del lote (discos y redes los hereda)."""
    import dataclasses

    from proxlaunch.nucleo.modelos.vm import Disco, InterfazRed

    return dataclasses.replace(
        cfg, vmid=0, nombre="", nodo="", discos=[Disco("datos", 32)], redes=[InterfazRed("vmbr0")]
    )
