"""MVP 4: catálogo del servidor, resolución del origen, elegibilidad de nodo y presupuesto.

Requisitos: RF-O04 (CA-O04.6), RF-O07 (CA-O07.1..O07.8), RF-O14 (CA-O14.1/O14.4/O14.5), RF-O18
(CA-O18.1/O18.2/O18.4), RF-O19 (CA-O19.1..O19.4), RF-O20 (CA-O20.5), RF-O23 (CA-O23.1..O23.7),
V-O02..V-O04, V-O19, V-O20, V-O25, INV-M1 (solo lecturas), INV-O8 (fuente vigente), E-O05, E-O16.
"""

import time

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import FilaLote
from proxlaunch.nucleo.lote.presupuesto import claves_pesadas, pedido_vm
from proxlaunch.nucleo.modelos.catalogo import (
    CatalogoServidor,
    Contenido,
    ListadoStorage,
)
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    RefVolumen,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import Disco, Firmware
from proxlaunch.nucleo.origen.constantes import MAX_CATALOGO
from proxlaunch.nucleo.origen.resolucion import (
    NecesidadesCatalogo,
    motivos_nodo_origen,
    necesidades_catalogo,
    resolver_origen,
)
from proxlaunch.nucleo.servicios.catalogo import (
    ServicioCatalogo,
    con_catalogo,
    fuente_vigente,
)

from .apoyo_api import crear_sesion
from .apoyo_lote import GIB, RelojSeguro, TransporteCluster, storage
from .apoyo_mvp4 import (
    VOLID_IMAGEN,
    VOLID_ISO,
    VOLID_VIRTIO,
    ClusterM4,
    cfg_base,
    cfg_clon,
    cfg_import,
    cfg_iso,
    detalle_plantilla,
    disco_plantilla,
    inv_origen,
    listado,
    plantilla_pve,
    volumen,
)


def _mundo(nodos=("pve1", "pve2")):
    cl = ClusterM4(nodos)
    reloj = RelojSeguro()
    sesion = crear_sesion(TransporteCluster(cl), reloj=reloj)
    return cl, ServicioCatalogo(sesion, reloj), sesion


def _inv(nodos=("pve1", "pve2"), **kw):
    return inv_origen(nodos=nodos, **kw)


# --- ServicioCatalogo.listar (RF-O07) -------------------------------------------------------------


def test_ca_o07_1_lista_cada_storage_activo_con_el_contenido_ordenado_por_nombre():
    cl, svc, _ = _mundo(("pve1",))
    cl.contenido[("pve1", "local")] = [
        "local:iso/zeta.iso",
        "local:iso/Alfa.iso",
        "local:iso/beta.iso",
    ]
    cl.contenido[("pve1", "nfs1")] = ["nfs1:iso/otro.iso"]
    listados = svc.listar(_inv(("pve1",)), "pve1", Contenido.ISO)
    assert {(x.storage, x.nodo) for x in listados} == {("local", "pve1"), ("nfs1", "pve1")}
    local = next(x for x in listados if x.storage == "local")
    assert [v.nombre for v in local.volumenes] == ["Alfa.iso", "beta.iso", "zeta.iso"]
    assert all(v.admitido for v in local.volumenes) and all(x.error is None for x in listados)
    assert cl.solo_lecturas  # INV-M1 / CA-O07.7


def test_ca_o04_2_el_catalogo_clasifica_por_contenido_no_por_nombre_y_omite_inactivos():
    cl, svc, _ = _mundo(("pve1",))
    inv = _inv(("pve1",))
    inv.storages_todos["pve1"] = (
        storage("iso", "lvmthin", 10, contenido="images"),  # se llama «iso» pero no tiene iso
        storage("discos", "dir", 10, contenido="iso"),
        storage("viejo", "dir", 10, activo=False, contenido="iso"),
    )
    cl.contenido[("pve1", "discos")] = ["discos:iso/a.iso"]
    cl.contenido[("pve1", "iso")] = ["iso:iso/b.iso"]
    cl.contenido[("pve1", "viejo")] = ["viejo:iso/c.iso"]
    assert [x.storage for x in svc.listar(inv, "pve1", Contenido.ISO)] == ["discos"]
    assert not [c for c in cl.llamadas if "/storage/iso/" in c.ruta or "/viejo/" in c.ruta]


def test_ca_o07_2_los_nombres_no_admitidos_se_listan_pero_marcados():
    cl, svc, _ = _mundo(("pve1",))
    cl.contenido[("pve1", "local")] = [
        "local:iso/bien.iso", "local:iso/con espacio.iso", "local:iso/x.iso,media=disk",
        "local:iso/raro.exe", "local:iso/ñandú.iso",
    ]  # fmt: skip
    (lst,) = [x for x in svc.listar(_inv(("pve1",)), "pve1", Contenido.ISO) if x.storage == "local"]
    admitidos = {v.nombre: v.admitido for v in lst.volumenes}
    assert admitidos == {
        "bien.iso": True, "con espacio.iso": False, "x.iso,media=disk": False,
        "raro.exe": False, "ñandú.iso": False,
    }  # fmt: skip


def test_ca_o07_5_un_403_en_un_storage_se_anota_por_storage_y_los_demas_se_listan():
    cl, svc, _ = _mundo(("pve1",))
    cl.contenido[("pve1", "local")] = ["local:iso/a.iso"]
    cl.contenido[("pve1", "nfs1")] = ["nfs1:iso/b.iso"]
    cl.regla(
        "GET",
        r"/storage/nfs1/content$",
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"),
    )
    por = {x.storage: x for x in svc.listar(_inv(("pve1",)), "pve1", Contenido.ISO)}
    assert por["nfs1"].error.codigo == CodigoError.CATALOGO_SIN_PERMISO  # E-O05
    assert por["nfs1"].error.params["storage"] == "nfs1" and por["nfs1"].volumenes == ()
    assert [v.nombre for v in por["local"].volumenes] == ["a.iso"] and por["local"].error is None


@pytest.mark.parametrize(
    "codigo",
    [CodigoError.SESION_EXPIRADA, CodigoError.CREDENCIALES_INVALIDAS, CodigoError.HUELLA_CAMBIADA],
)
def test_un_error_de_sesion_al_listar_se_propaga_no_se_disfraza_de_storage(codigo):
    cl, svc, _ = _mundo(("pve1",))
    cl.regla("GET", r"/content$", ErrorProxLaunch(codigo, {}, "x"))
    with pytest.raises(ErrorProxLaunch) as e:
        svc.listar(_inv(("pve1",)), "pve1", Contenido.ISO)
    assert e.value.codigo == codigo


def test_ca_o07_4_un_catalogo_de_500_volumenes_se_lista_en_menos_de_2_s_y_se_recorta_a_max():
    cl, svc, _ = _mundo(("pve1",))
    cl.contenido[("pve1", "local")] = [
        f"local:iso/iso-{i:04d}.iso" for i in range(MAX_CATALOGO + 100)
    ]
    t0 = time.perf_counter()
    (lst,) = [x for x in svc.listar(_inv(("pve1",)), "pve1", Contenido.ISO) if x.storage == "local"]
    assert time.perf_counter() - t0 < 2.0
    assert len(lst.volumenes) == MAX_CATALOGO


def test_catalogos_de_0_y_1_volumen_y_el_mismo_nombre_en_dos_storages():
    cl, svc, _ = _mundo(("pve1",))
    por = {x.storage: x for x in svc.listar(_inv(("pve1",)), "pve1", Contenido.ISO)}
    assert por["local"].volumenes == () and por["nfs1"].volumenes == ()
    cl.contenido[("pve1", "local")] = ["local:iso/igual.iso"]
    cl.contenido[("pve1", "nfs1")] = ["nfs1:iso/igual.iso"]
    por = {x.storage: x for x in svc.listar(_inv(("pve1",)), "pve1", Contenido.ISO)}
    assert [v.volid for v in por["local"].volumenes + por["nfs1"].volumenes] == [
        "local:iso/igual.iso", "nfs1:iso/igual.iso",
    ]  # fmt: skip


# --- Plantillas, formatos y lectura para un plan --------------------------------------------------


def test_ca_o19_1_solo_las_plantillas_aparecen_y_no_las_mvs_normales():
    cl, svc, _ = _mundo()
    cl.agregar_plantilla(9000, "base", "pve1")
    cl.agregar_vm(120, "pve1", "una-mv-normal")
    ps = svc.plantillas()
    assert [(p.vmid, p.nombre, p.nodo) for p in ps] == [(9000, "base", "pve1")]
    assert ps[0].disco_total_bytes == 8 * GIB and ps[0].bloqueo is None


def test_ca_o19_4_ca_o19_3_plantillas_de_varios_nodos_y_con_el_mismo_nombre():
    cl, svc, _ = _mundo()
    cl.agregar_plantilla(9000, "base", "pve1")
    cl.agregar_plantilla(9001, "base", "pve2")
    assert sorted((p.vmid, p.nodo) for p in svc.plantillas()) == [(9000, "pve1"), (9001, "pve2")]


def test_detalle_de_plantilla_lee_la_config_y_devuelve_none_si_no_existe_o_no_hay_permiso():
    cl, svc, _ = _mundo()
    cl.agregar_plantilla(9000, "base", "pve1", tags="a;b", cores=6)
    d = svc.detalle_plantilla("pve1", 9000)
    assert (
        d.cores == 6 and d.etiquetas == frozenset({"a", "b"}) and d.discos[0].storage == "local-lvm"
    )
    assert svc.detalle_plantilla("pve1", 1234) is None
    cl.regla(
        "GET", r"/qemu/9000/config$", ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    )
    assert svc.detalle_plantilla("pve1", 9000) is None
    cl.regla(
        "GET", r"/qemu/9000/config$", ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "x")
    )
    cl.reglas[0].veces = 0
    with pytest.raises(ErrorProxLaunch):
        svc.detalle_plantilla("pve1", 9000)


def test_ca_o04_6_los_formatos_salen_de_la_respuesta_del_servidor_unidos_entre_nodos():
    cl, svc, _ = _mundo()
    cl.storages_api["pve1"] = [
        {"storage": "local", "type": "dir", "content": "images", "active": 1, "formats": [{"raw": 1, "qcow2": 1}, "raw"]},  # noqa: E501
        {"storage": "lvm1", "type": "lvm", "content": "images", "active": 1, "formats": [{"raw": 1}, "raw"]},  # noqa: E501
    ]  # fmt: skip
    cl.storages_api["pve2"] = [
        {"storage": "local", "type": "dir", "content": "images", "active": 1, "formats": {"vmdk": 1}},  # noqa: E501
        {"storage": "sin_formatos", "type": "dir", "content": "images", "active": 1},
    ]  # fmt: skip
    f = svc.formatos(_inv(), ["pve1", "pve2"])
    assert f == {"local": frozenset({"raw", "qcow2", "vmdk"}), "lvm1": frozenset({"raw"})}
    assert all(c.params == {"format": 1} for c in cl.llamadas_a("GET", "/storage$"))


def test_los_formatos_de_un_nodo_caido_se_omiten_sin_fallar():
    cl, svc, _ = _mundo()
    cl.regla(
        "GET",
        r"/nodes/pve2/storage$",
        ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve2"}, "596"),
    )
    assert "local" in svc.formatos(_inv(), ["pve1", "pve2"])


def test_ca_o03_1_leer_para_unas_necesidades_vacias_no_hace_ninguna_peticion():
    cl, svc, _ = _mundo()
    inv = _inv()
    cat = svc.leer_para(inv, NecesidadesCatalogo(), ["pve1", "pve2"])
    assert cl.llamadas == [] and cat.listados == () and cat.plantillas is None
    assert cat.permisos == inv.catalogo.permisos  # se reutilizan, sin GET /access/permissions


def test_leer_para_lee_solo_lo_que_se_necesita_y_solo_con_get():
    cl, svc, _ = _mundo()
    cl.agregar_plantilla(9000, "base", "pve1")
    cl.agregar_plantilla(9002, "otra", "pve1")
    cl.contenido[("pve1", "local")] = [VOLID_ISO]
    nec = NecesidadesCatalogo(frozenset({Contenido.ISO}), frozenset({"base"}), True)
    cat = svc.leer_para(_inv(), nec, ["pve1", "pve2"])
    assert {x.nodo for x in cat.listados} == {"pve1", "pve2"} and cl.solo_lecturas
    assert not [c for c in cl.llamadas if (c.params or {}).get("content") == "import"]
    por_nombre = {p.nombre: p for p in cat.plantillas}
    assert por_nombre["base"].detalle is not None and por_nombre["otra"].detalle is None
    assert "local" in cat.formatos and cat.leido_en == cl_reloj_ahora(svc)


def cl_reloj_ahora(svc: ServicioCatalogo) -> float:
    return svc._reloj.ahora()


def test_necesidades_catalogo_segun_los_origenes_de_las_filas():
    filas = [
        FilaLote("a", cfg_base()),
        FilaLote("b", cfg_iso()),
        FilaLote("c", cfg_import()),
        FilaLote("d", cfg_clon("base")),
        FilaLote("e", cfg_clon("")),
    ]
    assert necesidades_catalogo(filas[:1]).vacias
    n = necesidades_catalogo(filas)
    assert n.contenidos == frozenset({Contenido.ISO, Contenido.IMPORT})
    assert n.plantillas == frozenset({"base"}) and n.formatos is True
    assert necesidades_catalogo([filas[1]]) == NecesidadesCatalogo(frozenset({Contenido.ISO}))
    assert necesidades_catalogo([]).vacias


# --- INV-O8: fuente vigente -----------------------------------------------------------------------


def test_inv_o8_fuente_vigente_relee_el_storage_y_confirma_que_el_volid_sigue():
    cl, _, sesion = _mundo()
    cl.contenido[("pve1", "local")] = [VOLID_ISO]
    assert fuente_vigente(sesion.cliente, cfg_iso()) is None
    assert fuente_vigente(sesion.cliente, cfg_base()) is None
    assert fuente_vigente(sesion.cliente, cfg_clon("base", 9000, "pve1")) is None


def test_inv_o8_e_o16_si_el_iso_desaparecio_la_mv_no_se_envia():
    cl, _, sesion = _mundo()
    cl.contenido[("pve1", "local")] = ["local:iso/otra.iso"]
    e = fuente_vigente(sesion.cliente, cfg_iso())
    assert e.codigo == CodigoError.FUENTE_DESAPARECIO and e.params == {
        "nombre": "alpine.iso",
        "tipo": "iso",
    }


def test_inv_o8_los_drivers_tambien_se_revalidan():
    cl, _, sesion = _mundo()
    cl.contenido[("pve1", "local")] = [VOLID_ISO]
    cfg = cfg_iso(tipo_so=TipoSO.WINDOWS_10, drivers=VOLID_VIRTIO)
    e = fuente_vigente(sesion.cliente, cfg)
    assert e.codigo == CodigoError.FUENTE_DESAPARECIO and e.params["tipo"] == "drivers"
    cfg_sin = cfg_iso(tipo_so=TipoSO.WINDOWS_10, drivers=VOLID_VIRTIO, sin_drivers=True)
    assert fuente_vigente(sesion.cliente, cfg_sin) is None


def test_inv_o8_un_volid_sin_resolver_o_invalido_cuenta_como_desaparecido():
    _, _, sesion = _mundo()
    sin = cfg_iso(None)
    sin.detalle_origen = DetalleIso(iso=RefVolumen("alpine.iso"))
    assert fuente_vigente(sesion.cliente, sin).codigo == CodigoError.FUENTE_DESAPARECIO
    assert fuente_vigente(sesion.cliente, cfg_iso("local:iso/x.iso,ide0=a")).codigo == (
        CodigoError.FUENTE_DESAPARECIO
    )


def test_inv_o8_ante_un_error_de_lectura_no_se_da_la_fuente_por_buena():
    cl, _, sesion = _mundo()
    cl.regla(
        "GET",
        r"/content$",
        ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve1"}, "596"),
    )
    e = fuente_vigente(sesion.cliente, cfg_import())
    assert e is not None and e.codigo == CodigoError.NODO_NO_DISPONIBLE


def test_con_catalogo_devuelve_una_copia_y_no_toca_el_original():
    inv = _inv()
    nuevo = con_catalogo(inv, CatalogoServidor())
    assert (
        nuevo is not inv
        and nuevo.catalogo == CatalogoServidor()
        and inv.catalogo.permisos is not None
    )


# --- resolver_origen: ISO / drivers / imagen ------------------------------------------------------


def _iso_por_nombre(nombre="alpine.iso", tipo=TipoSO.LINUX, **kw):
    cfg = cfg_iso(None, tipo, **kw)
    cfg.detalle_origen = DetalleIso(
        iso=RefVolumen(nombre), sin_drivers=kw.get("sin_drivers", False)
    )
    return cfg


def test_el_nombre_del_iso_se_resuelve_al_volid_del_nodo():
    inv = _inv(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    cfg, problemas = resolver_origen(_iso_por_nombre(), inv, "pve1")
    assert problemas == [] and cfg.detalle_origen.iso == RefVolumen("alpine.iso", VOLID_ISO)


def test_ca_o28_3_iso_ambiguo_en_dos_storages_pide_el_volid_completo():
    inv = _inv(
        listados=(
            listado("pve1", "local", Contenido.ISO, "local:iso/igual.iso"),
            listado("pve1", "nfs1", Contenido.ISO, "nfs1:iso/igual.iso"),
        )
    )
    cfg, problemas = resolver_origen(_iso_por_nombre("igual.iso"), inv, "pve1")
    (p,) = problemas
    assert (
        p.codigo == "V-O02.ambiguo"
        and p.params["volids"] == "local:iso/igual.iso, nfs1:iso/igual.iso"
    )
    assert cfg.detalle_origen.iso.volid is None  # no se elige por su cuenta (D-23.2)


def test_ca_o28_3_iso_inexistente_lista_hasta_5_alternativas():
    nombres = [f"local:iso/d{i}.iso" for i in range(8)]
    inv = _inv(listados=(listado("pve1", "local", Contenido.ISO, *nombres),))
    _, problemas = resolver_origen(_iso_por_nombre("falta.iso"), inv, "pve1")
    (p,) = problemas
    assert p.params["motivo"] == "no_disponible"
    assert p.params["alternativas"].split(", ") == [f"d{i}.iso" for i in range(5)]


def test_resolver_sin_catalogo_en_absoluto_no_afirma_nada():
    inv = inv_origen()
    inv.catalogo = None
    cfg, problemas = resolver_origen(_iso_por_nombre(), inv, "pve1")
    assert problemas == [] and cfg.detalle_origen.iso.volid is None


def test_resolver_con_el_catalogo_sin_listar_no_afirma_que_falte_el_archivo():
    inv = (
        inv_origen()
    )  # catalogo = CatalogoServidor(permisos=…), sin listados (como tras descubrir)
    assert inv.catalogo.listados == ()
    for cfg in (_iso_por_nombre(), cfg_import(None)):
        if isinstance(cfg.detalle_origen, DetalleImportacion):
            cfg.detalle_origen = DetalleImportacion(imagen=RefVolumen("cirros.qcow2"))
        _, problemas = resolver_origen(cfg, inv, "pve1")
        assert problemas == []


def test_resolver_un_storage_inactivo_no_cuenta_como_disponible():
    inv = _inv(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    inv.storages_todos["pve1"] = tuple(
        storage(s.id, s.tipo, 1, activo=s.id != "local", contenido=",".join(s.contenido))
        for s in inv.storages_todos["pve1"]
    )
    _, problemas = resolver_origen(_iso_por_nombre(), inv, "pve1")
    assert problemas and problemas[0].params["motivo"] == "no_disponible"


def test_resolver_no_modifica_la_configuracion_original():
    inv = _inv(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    original = _iso_por_nombre()
    resolver_origen(original, inv, "pve1")
    assert original.detalle_origen.iso.volid is None


def test_ca_o14_1_detecta_virtio_win_el_mas_reciente_con_orden_natural():
    inv = _inv(
        listados=(
            listado(
                "pve1",
                "local",
                Contenido.ISO,
                VOLID_ISO,
                "local:iso/virtio-win-0.1.9.iso",
                "local:iso/virtio-win-0.1.271.iso",
                "local:iso/virtio-win-0.1.100.iso",
                "local:iso/otro.iso",
            ),
        )
    )
    cfg = _iso_por_nombre(tipo=TipoSO.WINDOWS_10)
    cfg.firmware = Firmware.OVMF
    res, problemas = resolver_origen(cfg, inv, "pve1")
    assert (
        problemas == [] and res.detalle_origen.drivers.volid == "local:iso/virtio-win-0.1.271.iso"
    )


def test_ca_o14_2_sin_virtio_win_hay_que_decidir_y_crear_sin_drivers_lo_acepta():
    inv = _inv(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    cfg = _iso_por_nombre(tipo=TipoSO.WINDOWS_10)
    _, problemas = resolver_origen(cfg, inv, "pve1")
    assert [p.codigo for p in problemas] == ["V-O02.drivers"]
    res, problemas = resolver_origen(
        _iso_por_nombre(tipo=TipoSO.WINDOWS_10, sin_drivers=True), inv, "pve1"
    )
    assert problemas == [] and res.detalle_origen.drivers is None


def test_ca_o14_1_linux_no_busca_drivers_y_un_driver_elegido_a_mano_se_valida():
    inv = _inv(
        listados=(
            listado("pve1", "local", Contenido.ISO, VOLID_ISO, "local:iso/virtio-win-0.1.271.iso"),
        )
    )
    res, problemas = resolver_origen(_iso_por_nombre(), inv, "pve1")
    assert problemas == [] and res.detalle_origen.drivers is None
    cfg = cfg_iso(VOLID_ISO, TipoSO.WINDOWS_10, drivers="local:iso/inexistente.iso")
    _, problemas = resolver_origen(cfg, inv, "pve1")
    assert any(p.campo == "detalle_origen.drivers" and p.codigo == "V-O02" for p in problemas)


def test_la_imagen_se_resuelve_por_nombre_en_el_contenido_import():
    inv = _inv(listados=(listado("pve1", "local", Contenido.IMPORT, VOLID_IMAGEN),))
    cfg = cfg_import(None)
    cfg.detalle_origen = DetalleImportacion(imagen=RefVolumen("cirros.qcow2"), ampliar_a_gib=40)
    res, problemas = resolver_origen(cfg, inv, "pve1")
    assert problemas == [] and res.detalle_origen.imagen.volid == VOLID_IMAGEN
    assert res.detalle_origen.ampliar_a_gib == 40
    malo = cfg_import(None)
    malo.detalle_origen = DetalleImportacion(imagen=RefVolumen("falta.qcow2"))
    assert resolver_origen(malo, inv, "pve1")[1][0].codigo == "V-O03"


# --- resolver_origen: plantillas ------------------------------------------------------------------


def _plantillas(*ps, **kw):
    return _inv(plantillas=tuple(ps), **kw)


def test_la_plantilla_se_resuelve_en_su_nodo_con_vmid_y_modo_efectivo_y_valores_de_la_plantilla():
    inv = _plantillas(plantilla_pve(9000, "base", "pve1", detalle_plantilla(cores=6, memoria=8192)))
    cfg, problemas = resolver_origen(cfg_clon("base"), inv, "pve1")
    assert problemas == []
    d = cfg.detalle_origen
    assert (d.plantilla.vmid, d.plantilla.nodo, d.modo_efectivo) == (
        9000,
        "pve1",
        ModoClon.ENLAZADO,
    )
    assert (cfg.cores, cfg.memoria_mib) == (6, 8192)  # CA-O22.1: «igual que la plantilla»


def test_ca_o22_1_los_ajustes_del_usuario_mandan_sobre_los_valores_de_la_plantilla():
    inv = _plantillas(plantilla_pve())
    cfg, _ = resolver_origen(
        cfg_clon("base", ajustes=AjustesClon(cores=8, memoria_mib=1024)), inv, "pve1"
    )
    assert (cfg.cores, cfg.memoria_mib) == (8, 1024)


def test_ca_o23_1_plantilla_en_storage_local_solo_sirve_en_su_nodo():
    inv = _plantillas(plantilla_pve(9000, "base", "pve1"))
    _, p1 = resolver_origen(cfg_clon("base"), inv, "pve1")
    res, p2 = resolver_origen(cfg_clon("base"), inv, "pve2")
    assert p1 == [] and [(p.codigo, p.params["motivo"]) for p in p2] == [("V-O04", "no_en_nodo")]
    assert res.detalle_origen.plantilla.vmid is None  # no se sustituye por otro nodo (D-23.2)


def test_ca_o23_2_plantilla_en_storage_compartido_se_clona_desde_su_nodo_a_los_demas():
    comp = detalle_plantilla([disco_plantilla("scsi0", "nfs1")])
    inv = _plantillas(plantilla_pve(9000, "base", "pve1", comp))
    cfg, problemas = resolver_origen(cfg_clon("base"), inv, "pve2")
    assert problemas == [] and cfg.detalle_origen.plantilla.nodo == "pve1"  # clona desde pve1
    from proxlaunch.nucleo.origen.clon import construir_peticion_clon

    cfg.nodo = "pve2"
    pet = construir_peticion_clon(cfg, inv)
    assert pet.nodo_plantilla == "pve1" and pet.parametros["target"] == "pve2"


def test_ca_o23_4_misma_plantilla_replicada_en_nodos_con_storage_local_cada_nodo_usa_la_suya():
    inv = _plantillas(plantilla_pve(9000, "base", "pve1"), plantilla_pve(9001, "base", "pve2"))
    for nodo, vmid in (("pve1", 9000), ("pve2", 9001)):
        cfg, problemas = resolver_origen(cfg_clon("base"), inv, nodo)
        assert problemas == [] and cfg.detalle_origen.plantilla.vmid == vmid


def test_ca_o23_5_mismo_nombre_en_nodos_con_storage_compartido_pide_elegir():
    comp = detalle_plantilla([disco_plantilla("scsi0", "nfs1")])
    inv = _plantillas(
        plantilla_pve(9000, "base", "pve1", comp), plantilla_pve(9001, "base", "pve2", comp)
    )
    _, problemas = resolver_origen(cfg_clon("base"), inv, "pve1")
    assert [p.codigo for p in problemas] == ["V-O04.ambiguo"]
    cfg, ok = resolver_origen(cfg_clon("base", 9001), inv, "pve1")  # el VMID de la pista desempata
    assert ok == [] and cfg.detalle_origen.plantilla.vmid == 9001


def test_ca_o23_5_dos_plantillas_con_el_mismo_nombre_en_el_mismo_nodo_pide_elegir():
    inv = _plantillas(plantilla_pve(9000, "base", "pve1"), plantilla_pve(9005, "base", "pve1"))
    _, problemas = resolver_origen(cfg_clon("base"), inv, "pve1")
    assert [p.codigo for p in problemas] == ["V-O04.ambiguo"]
    assert (
        "pve1:9000" in problemas[0].params["plantillas"]
        and "pve1:9005" in problemas[0].params["plantillas"]
    )


def test_ca_o27_3_se_re_resuelve_por_nombre_aunque_el_vmid_de_la_pista_no_coincida():
    inv = _plantillas(plantilla_pve(9000, "base", "pve1"))
    cfg, problemas = resolver_origen(cfg_clon("base", 777), inv, "pve1")
    assert problemas == [] and cfg.detalle_origen.plantilla.vmid == 9000


def test_plantilla_inexistente_bloqueada_o_sin_detalle():
    inv = _plantillas(plantilla_pve(9000, "base", "pve1"))
    _, p = resolver_origen(cfg_clon("falta"), inv, "pve1")
    assert p[0].params["motivo"] == "no_existe" and p[0].params["alternativas"] == "base"
    bloq = _plantillas(plantilla_pve(9000, "base", "pve1", bloqueo="backup"))
    assert resolver_origen(cfg_clon("base"), bloq, "pve1")[1][0].params["motivo"] == "bloqueada"
    sin_detalle = _plantillas(plantilla_pve(9000, "base", "pve1", detalle=None))
    sin_detalle.catalogo.plantillas[0].__class__  # noqa: B018
    pl = sin_detalle.catalogo.plantillas[0]
    from dataclasses import replace

    sin_detalle.catalogo = replace(sin_detalle.catalogo, plantillas=(replace(pl, detalle=None),))
    assert (
        resolver_origen(cfg_clon("base"), sin_detalle, "pve1")[1][0].params["motivo"]
        == "sin_detalle"
    )


def test_plantillas_sin_leer_no_se_afirma_nada():
    cfg, problemas = resolver_origen(cfg_clon("base"), _inv(plantillas=None), "pve1")
    assert problemas == [] and cfg.detalle_origen.plantilla.vmid is None


def test_resolver_un_origen_vacio_devuelve_la_misma_configuracion():
    cfg = cfg_base()
    res, problemas = resolver_origen(cfg, _inv(), "pve1")
    assert res is cfg and problemas == []


# --- V-O25: elegibilidad de nodo por origen -------------------------------------------------------


def test_ca_o07_3_ca_o08_6_un_iso_en_storage_local_excluye_a_los_nodos_que_no_lo_tienen():
    inv = _inv(listados=(
        listado("pve1", "local", Contenido.ISO, VOLID_ISO),
        listado("pve2", "local", Contenido.ISO, "local:iso/otro.iso"),
    ))  # fmt: skip
    assert motivos_nodo_origen(cfg_iso(), inv, "pve1") == []
    (m,) = motivos_nodo_origen(cfg_iso(), inv, "pve2")
    assert (
        m.regla == "V-L11" and m.params["motivo"] == "fuente" and m.params["fuente"] == "alpine.iso"
    )
    assert m.params["nodo"] == "pve2" and m.params["tipo"] == "iso"


def test_ca_o07_3_un_iso_en_storage_compartido_es_elegible_en_todos_los_nodos():
    inv = _inv(listados=(
        listado("pve1", "nfs1", Contenido.ISO, "nfs1:iso/alpine.iso"),
        listado("pve2", "nfs1", Contenido.ISO, "nfs1:iso/alpine.iso"),
    ))  # fmt: skip
    cfg = cfg_iso("nfs1:iso/alpine.iso")
    assert (
        motivos_nodo_origen(cfg, inv, "pve1") == [] and motivos_nodo_origen(cfg, inv, "pve2") == []
    )


def test_ca_o14_5_los_drivers_en_storage_local_de_un_nodo_excluyen_a_los_otros():
    inv = _inv(listados=(
        listado("pve1", "local", Contenido.ISO, VOLID_ISO, VOLID_VIRTIO),
        listado("pve2", "local", Contenido.ISO, VOLID_ISO),
    ))  # fmt: skip
    cfg = cfg_iso(tipo_so=TipoSO.WINDOWS_10, drivers=VOLID_VIRTIO)
    (m,) = motivos_nodo_origen(cfg, inv, "pve2")
    assert m.params["tipo"] == "drivers" and m.params["fuente"] == "virtio-win-0.1.271.iso"
    # con detección: el nodo sin virtio-win solo se excluye si otro nodo sí lo tiene
    detectando = _iso_por_nombre(tipo=TipoSO.WINDOWS_10)
    (m2,) = motivos_nodo_origen(detectando, inv, "pve2")
    assert m2.params["fuente"] == "virtio-win"
    assert motivos_nodo_origen(detectando, inv, "pve1") == []


def test_la_imagen_de_importacion_tambien_debe_estar_en_el_nodo():
    inv = _inv(listados=(
        listado("pve1", "local", Contenido.IMPORT, VOLID_IMAGEN),
        listado("pve2", "local", Contenido.IMPORT),
    ))  # fmt: skip
    assert motivos_nodo_origen(cfg_import(), inv, "pve1") == []
    assert motivos_nodo_origen(cfg_import(), inv, "pve2")[0].params["tipo"] == "imagen"


def test_ca_o23_3_el_nodo_sin_la_plantilla_ni_su_storage_explica_el_motivo():
    inv = _plantillas(plantilla_pve(9000, "base", "pve1"))
    assert motivos_nodo_origen(cfg_clon("base"), inv, "pve1") == []
    (m,) = motivos_nodo_origen(cfg_clon("base"), inv, "pve2")
    assert (m.params["motivo"], m.params["plantilla"]) == ("plantilla", "base")
    # pve2 sin el storage «local-lvm»: el mensaje nombra el almacenamiento que falta
    inv.storages_todos["pve2"] = tuple(s for s in inv.storages_todos["pve2"] if s.id != "local-lvm")
    (m,) = motivos_nodo_origen(cfg_clon("base"), inv, "pve2")
    assert m.params["storage"] == "local-lvm"


def test_ca_o22_9_los_bridges_de_la_plantilla_deben_existir_en_el_nodo():
    comp = detalle_plantilla([disco_plantilla("scsi0", "nfs1")], bridges=("vmbr9",))
    inv = _plantillas(plantilla_pve(9000, "base", "pve1", comp))
    (m,) = motivos_nodo_origen(cfg_clon("base"), inv, "pve2")
    assert m.params["motivo"] == "bridge" and m.params["bridge"] == "vmbr9"


def test_sin_catalogo_leido_ningun_nodo_se_descarta_y_el_disco_vacio_nunca_tiene_motivos():
    assert motivos_nodo_origen(cfg_iso(), inv_origen(), "pve2") == []
    assert motivos_nodo_origen(cfg_clon("base"), inv_origen(plantillas=None), "pve2") == []
    assert motivos_nodo_origen(cfg_base(), _inv(), "pve1") == []


def test_ca_o23_7_el_reparto_automatico_solo_usa_nodos_con_la_fuente_y_no_sustituye_en_silencio():
    from proxlaunch.nucleo.lote.modelos import Destino, ModoDestino
    from proxlaunch.nucleo.lote.reparto import repartir_filas

    inv = _inv(listados=(
        listado("pve1", "local", Contenido.ISO, VOLID_ISO),
        listado("pve2", "local", Contenido.ISO),
    ))  # fmt: skip
    cfg = cfg_iso()
    cfg.nodo = ""
    filas = [FilaLote(f"vm-{i}", cfg) for i in range(4)]
    nodos, _, problemas = repartir_filas(filas, Destino(), inv)
    assert nodos == ["pve1"] * 4
    assert any(
        p.params.get("nodo") == "pve2" and p.params.get("motivo") == "fuente" for p in problemas
    )
    # «Nodos elegidos» que incluye pve2: pve2 no es elegible (V-O25) y nada se sustituye
    nodos, _, problemas = repartir_filas(filas, Destino(ModoDestino.NODOS_ELEGIDOS, ("pve2",)), inv)
    assert nodos == [""] * 4 and any(p.severidad.value == "error" for p in problemas)


# --- Presupuesto de espacio por origen (V-O19, V-O20, CA-O18.x, CA-O20.5) -------------------------


def _pedido(cfg, inv=None):
    return {(k.ambito, k.storage): v for k, v in pedido_vm(cfg, inv or _inv()).items()}


def test_ca_o18_1_la_importacion_pide_el_tamano_virtual_en_el_primer_disco():
    cfg = cfg_import(tamano_virtual_bytes=5 * GIB)
    assert _pedido(cfg) == {("pve1", "local-lvm"): 5 * GIB}


def test_ca_o18_2_sin_tamano_virtual_se_usa_el_tamano_del_archivo_como_minimo():
    grande = volumen(VOLID_IMAGEN, Contenido.IMPORT, 3 * GIB)
    inv = _inv(listados=(ListadoStorage("pve1", "local", Contenido.IMPORT, (grande,)),))
    assert _pedido(cfg_import(), inv) == {("pve1", "local-lvm"): 3 * GIB}
    assert _pedido(cfg_import(), _inv()) == {}  # nada conocido: no se inventa un tamaño


def test_ca_o18_4_ampliar_a_x_presupuesta_x_y_nunca_menos_que_el_virtual():
    assert _pedido(cfg_import(tamano_virtual_bytes=2 * GIB, ampliar_a_gib=40)) == {
        ("pve1", "local-lvm"): 40 * GIB
    }
    assert _pedido(cfg_import(tamano_virtual_bytes=50 * GIB, ampliar_a_gib=40)) == {
        ("pve1", "local-lvm"): 50 * GIB
    }


def test_la_importacion_conserva_los_demas_discos_y_el_efidisk():
    cfg = cfg_import(
        tamano_virtual_bytes=5 * GIB,
        cfg={"firmware": Firmware.OVMF, "discos": [Disco("local-lvm", 32), Disco("local-lvm", 16)]},
    )
    assert _pedido(cfg) == {("pve1", "local-lvm"): 5 * GIB + 16 * GIB + 4 * 1024**2}


def test_con_tpm_se_suman_4_mib_en_el_storage_del_efidisk():
    base = _pedido(cfg_iso(firmware=Firmware.OVMF))
    con = _pedido(cfg_iso(firmware=Firmware.OVMF, tpm=True))
    assert con[("pve1", "local-lvm")] - base[("pve1", "local-lvm")] == 4 * 1024**2


def test_ca_o20_5_clon_enlazado_no_pide_espacio_y_clon_completo_pide_los_discos_de_la_plantilla():
    inv = _plantillas(plantilla_pve(9000, "base", "pve1", detalle_plantilla([
        disco_plantilla("scsi0", "local-lvm", 8), disco_plantilla("scsi1", "local-lvm", 20),
    ])))  # fmt: skip
    enl, _ = resolver_origen(cfg_clon("base"), inv, "pve1")
    comp, _ = resolver_origen(cfg_clon("base", modo=ModoClon.COMPLETO), inv, "pve1")
    assert _pedido(enl, inv) == {}
    assert _pedido(comp, inv) == {("pve1", "local-lvm"): 28 * GIB}  # V-O20
    ampl, _ = resolver_origen(
        cfg_clon("base", modo=ModoClon.COMPLETO, ajustes=AjustesClon(disco_gib=50)), inv, "pve1"
    )
    assert _pedido(ampl, inv) == {("pve1", "local-lvm"): 50 * GIB + 20 * GIB}  # el principal crece


def test_clon_completo_con_storage_destino_presupuesta_en_el_destino():
    inv = _plantillas(plantilla_pve())
    cfg, _ = resolver_origen(
        cfg_clon("base", modo=ModoClon.COMPLETO, storage_destino="local"), inv, "pve1"
    )
    assert _pedido(cfg, inv) == {("pve1", "local"): 8 * GIB}


def test_claves_pesadas_importacion_y_clon_completo_en_su_storage_destino_y_vacio_para_el_resto():
    inv = _plantillas(plantilla_pve())
    assert [c.storage for c in claves_pesadas(cfg_import(), inv)] == ["local-lvm"]
    comp, _ = resolver_origen(cfg_clon("base", modo=ModoClon.COMPLETO), inv, "pve1")
    assert [c.storage for c in claves_pesadas(comp, inv)] == ["local-lvm"]
    enl, _ = resolver_origen(cfg_clon("base"), inv, "pve1")
    assert claves_pesadas(enl, inv) == () and claves_pesadas(cfg_iso(), inv) == ()
    assert claves_pesadas(cfg_base(), inv) == ()


def test_ca_o18_3_ca_o29_1_un_lote_que_no_cabe_da_error_de_espacio_v_l09():
    """N importaciones de T GiB que exceden un storage de directorio destino."""
    from .apoyo_lote import crear_banco, definicion

    cl = ClusterM4(("pve1",))
    cl.contenido[("pve1", "local")] = [VOLID_IMAGEN]
    inv = _inv(("pve1",))
    inv.storages["pve1"] = tuple(
        storage(s.id, s.tipo, 20 if s.id == "local" else 500, contenido=",".join(s.contenido))
        for s in inv.storages["pve1"]
    )
    banco = crear_banco(("pve1",), inv=inv, cluster=cl)
    plant = cfg_import(
        None, cfg={"vmid": 0, "nombre": "plantilla", "nodo": "", "discos": [Disco("local", 8)]}
    )
    plant.detalle_origen = DetalleImportacion(
        imagen=RefVolumen("cirros.qcow2"), tamano_virtual_bytes=8 * GIB
    )
    plan = banco.planificar(definicion(5, plantilla_vm=plant))  # 5 × 8 GiB = 40 > 20 libres
    errores = {p.regla for p in plan.problemas if p.severidad.value == "error"}
    assert "V-L09" in errores
    ok = banco.planificar(definicion(2, plantilla_vm=plant))  # 2 × 8 = 16 ≤ 20
    assert not [p for p in ok.problemas if p.severidad.value == "error"]
