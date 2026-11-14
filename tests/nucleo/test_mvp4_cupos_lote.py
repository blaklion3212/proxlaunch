"""MVP 4: cupos de concurrencia y ejecución de lotes por origen con el motor real.

Requisitos: RNF-O04 / V-O28 (3 enlazados por nodo; importación y clon completo 1 por nodo y ≤ 2 por
storage destino), D-25.3, INV-L1/INV-O3 (≤ 1 POST de creación por VMID, `POST /qemu` y
`POST …/clone` juntos), CA-O21.1, CA-O30.2, CA-O30.3 (el rollback solo borra MVs), CA-O29.3
(simulación solo GET), CA-O30.9 (mismo volid para N MVs), CA-O17.3 (N importaciones, N POST).
"""

import dataclasses
import threading
import time

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.ajustes import reintentar_ajustes, tiene_ajustes_pendientes
from proxlaunch.nucleo.lote.constantes import (
    CONCURRENCIA_ENLAZADO_POR_NODO,
    CONCURRENCIA_PESADA_POR_STORAGE,
)
from proxlaunch.nucleo.lote.cupos import ClaseCarga, CuposEjecucion, clase_de
from proxlaunch.nucleo.lote.modelos import (
    AccionPeticion,
    ElementoPlan,
    EstadoMV,
    EstadoRollback,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback, es_propia
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    RefVolumen,
)
from proxlaunch.nucleo.modelos.vm import Disco

from .apoyo_lote import crear_banco, definicion, plantilla
from .apoyo_mvp4 import (
    VOLID_IMAGEN,
    VOLID_ISO,
    ClusterM4,
    cfg_base,
    cfg_clon,
    cfg_import,
    cfg_iso,
    inv_origen,
    permisos,
)


def _elem(vmid: int, nodo: str, cfg) -> ElementoPlan:
    return ElementoPlan(
        vmid - 100, f"vm-{vmid}", vmid, nodo, dataclasses.replace(cfg, nodo=nodo, vmid=vmid)
    )


def _en_hilo(cupos, elem, control):
    resultado: list[bool] = []
    hilo = threading.Thread(target=lambda: resultado.append(cupos.adquirir(elem, control)))
    hilo.start()
    return hilo, resultado


def _bloqueado(hilo, resultado, espera=0.25) -> bool:
    hilo.join(espera)
    return hilo.is_alive() and not resultado


# --- Clasificación de carga -----------------------------------------------------------------------


def test_las_constantes_de_concurrencia_son_las_aprobadas_en_d_25():
    assert CONCURRENCIA_ENLAZADO_POR_NODO == 3 and CONCURRENCIA_PESADA_POR_STORAGE == 2


def _clon(efectivo):
    return cfg_clon("base", 9000, "pve1", efectivo=efectivo)


@pytest.mark.parametrize(
    ("cfg", "clase"),
    [
        (cfg_base(), ClaseCarga.NORMAL),
        (cfg_iso(), ClaseCarga.NORMAL),
        (cfg_import(), ClaseCarga.PESADA),
        (_clon(ModoClon.ENLAZADO), ClaseCarga.LIGERA),
        (_clon(ModoClon.COMPLETO), ClaseCarga.PESADA),
        (_clon(None), ClaseCarga.PESADA),  # sin modo resuelto se asume la peor carga
    ],
    ids=["vacio", "iso", "importar", "clon-enlazado", "clon-completo", "clon-sin-resolver"],
)
def test_clase_de_carga_por_origen_y_modo_efectivo(cfg, clase):
    assert clase_de(cfg) == clase


# --- CuposEjecucion -------------------------------------------------------------------------------


def test_tres_clones_enlazados_por_nodo_a_la_vez_y_el_cuarto_espera():
    cupos = CuposEjecucion(inv_origen(), por_nodo=3)
    control = ControlLote()
    ligeros = [_elem(100 + i, "pve1", _clon(ModoClon.ENLAZADO)) for i in range(4)]
    assert all(cupos.adquirir(e, control) for e in ligeros[:3])
    hilo, res = _en_hilo(cupos, ligeros[3], control)
    assert _bloqueado(hilo, res)
    cupos.liberar(ligeros[0])
    hilo.join(3)
    assert res == [True]
    for e in ligeros[1:]:
        cupos.liberar(e)


def test_con_por_nodo_igual_a_1_el_enlazado_es_exclusivo_como_en_m2():
    cupos = CuposEjecucion(inv_origen(), por_nodo=1)
    control = ControlLote()
    a, b = (_elem(100 + i, "pve1", _clon(ModoClon.ENLAZADO)) for i in range(2))
    assert cupos.adquirir(a, control)
    hilo, res = _en_hilo(cupos, b, control)
    assert _bloqueado(hilo, res)
    cupos.liberar(a)
    hilo.join(3)
    assert res == [True]


@pytest.mark.parametrize(
    "exclusiva",
    [cfg_base(), cfg_iso(), cfg_import(), _clon(ModoClon.COMPLETO)],
    ids=["vacio", "iso", "importar", "clon-completo"],
)
def test_las_cargas_no_ligeras_son_exclusivas_por_nodo_y_bloquean_a_los_enlazados(exclusiva):
    cupos = CuposEjecucion(inv_origen(), por_nodo=3)
    control = ControlLote()
    uno = _elem(100, "pve1", exclusiva)
    assert cupos.adquirir(uno, control)
    for otro in (exclusiva, _clon(ModoClon.ENLAZADO)):
        e = _elem(101, "pve1", otro)
        hilo, res = _en_hilo(cupos, e, control)
        assert _bloqueado(hilo, res)
        cupos.liberar(uno)
        hilo.join(3)
        assert res == [True]
        cupos.liberar(e)
        assert cupos.adquirir(uno, control)
    cupos.liberar(uno)


def test_un_enlazado_en_curso_bloquea_a_una_carga_exclusiva_del_mismo_nodo():
    cupos = CuposEjecucion(inv_origen(), por_nodo=3)
    control = ControlLote()
    ligero = _elem(100, "pve1", _clon(ModoClon.ENLAZADO))
    assert cupos.adquirir(ligero, control)
    pesado = _elem(101, "pve1", cfg_import())
    hilo, res = _en_hilo(cupos, pesado, control)
    assert _bloqueado(hilo, res)
    cupos.liberar(ligero)
    hilo.join(3)
    assert res == [True]


def test_los_cupos_de_nodos_distintos_son_independientes():
    cupos = CuposEjecucion(inv_origen(), por_nodo=3)
    control = ControlLote()
    assert cupos.adquirir(_elem(100, "pve1", cfg_base()), control)
    assert cupos.adquirir(_elem(101, "pve2", cfg_base()), control)


def test_ca_o17_10_a_lo_sumo_dos_cargas_pesadas_por_storage_destino_entre_nodos():
    inv = inv_origen(nodos=("pve1", "pve2", "pve3"))
    cupos = CuposEjecucion(inv, pesadas_por_storage=2)
    control = ControlLote()
    # Importan hacia el MISMO storage compartido (nfs1) desde tres nodos.
    cfg = cfg_import(cfg={"discos": [Disco("nfs1", 8)]})
    es = [_elem(100 + i, f"pve{i + 1}", cfg) for i in range(3)]
    assert cupos.adquirir(es[0], control) and cupos.adquirir(es[1], control)
    hilo, res = _en_hilo(cupos, es[2], control)
    assert _bloqueado(hilo, res)
    cupos.liberar(es[0])
    hilo.join(3)
    assert res == [True]


def test_storages_locales_distintos_no_comparten_el_tope():
    inv = inv_origen(nodos=("pve1", "pve2", "pve3"))
    cupos = CuposEjecucion(inv, pesadas_por_storage=1)
    control = ControlLote()
    cfg = cfg_import()  # local-lvm es local a cada nodo
    assert all(cupos.adquirir(_elem(100 + i, f"pve{i + 1}", cfg), control) for i in range(3))


def test_adquirir_devuelve_false_si_se_cancela_o_se_pausa_mientras_espera():
    cupos = CuposEjecucion(inv_origen())
    control = ControlLote()
    a = _elem(100, "pve1", cfg_base())
    assert cupos.adquirir(a, control)
    b = _elem(101, "pve1", cfg_base())
    hilo, res = _en_hilo(cupos, b, control)
    assert _bloqueado(hilo, res, 0.1)
    control.cancelar()
    hilo.join(3)
    assert res == [False]
    # y si el control ya está cancelado, ni siquiera lo intenta
    assert cupos.adquirir(_elem(102, "pve2", cfg_base()), control) is False


def test_liberar_dos_veces_o_sin_haber_adquirido_es_inocuo():
    cupos = CuposEjecucion(inv_origen(), por_nodo=1)
    control = ControlLote()
    a = _elem(100, "pve1", cfg_base())
    cupos.liberar(a)
    assert cupos.adquirir(a, control)
    cupos.liberar(a)
    cupos.liberar(a)
    assert cupos.adquirir(_elem(101, "pve1", cfg_base()), control)


def test_el_orden_de_llegada_se_respeta_y_una_exclusiva_no_sufre_inanicion():
    cupos = CuposEjecucion(inv_origen(), por_nodo=3)
    control = ControlLote()
    l1 = _elem(100, "pve1", _clon(ModoClon.ENLAZADO))
    assert cupos.adquirir(l1, control)
    exclusiva = _elem(101, "pve1", cfg_import())
    cupos.encolar(exclusiva)  # llega antes que el siguiente enlazado
    l2 = _elem(102, "pve1", _clon(ModoClon.ENLAZADO))
    hilo, res = _en_hilo(cupos, l2, control)
    assert _bloqueado(hilo, res, 0.15)  # l2 espera su turno detrás de la exclusiva
    hilo_e, res_e = _en_hilo(cupos, exclusiva, control)
    cupos.liberar(l1)
    hilo_e.join(3)
    assert res_e == [True]
    cupos.liberar(exclusiva)
    hilo.join(3)
    assert res == [True]


# --- Motor real sobre el clúster simulado ---------------------------------------------------------


def _banco(nodos=("pve1",), plantillas=((9000, "base", "pve1"),), listados=()):
    cl = ClusterM4(nodos)
    for vmid, nombre, nodo in plantillas:
        cl.agregar_plantilla(vmid, nombre, nodo)
    inv = inv_origen(nodos=nodos)
    inv.catalogo = CatalogoServidor(permisos=permisos())
    for (nodo, st), volids in listados:
        cl.contenido[(nodo, st)] = list(volids)
    return crear_banco(nodos, inv=inv, cluster=cl), cl


def _clon_lote(n, **kw):
    plant = cfg_clon("base", vmid=0, nombre="plantilla", nodo="", discos=[], redes=[], **kw)
    return definicion(n, plantilla_vm=plant)


def test_rnf_o04_seis_clones_enlazados_en_un_nodo_nunca_superan_tres_a_la_vez():
    banco, cl = _banco()
    cl.barrera_clon = threading.Barrier(3)  # exige que haya 3 simultáneos para avanzar
    plan = banco.planificar(_clon_lote(6))
    assert not plan.problemas and len(plan.elementos) == 6
    libro = banco.ejecutar(plan)
    assert set(banco.estados(libro)) == {"ok"}
    assert cl.max_clon_por_nodo == 3  # alcanza el tope y no lo supera
    assert cl.clones == {100 + i: 1 for i in range(6)}  # INV-L1: un POST …/clone por VMID
    assert cl.posts == {}  # ningún POST /qemu para esas MVs (CA-O21.1)


def test_rnf_o04_clon_completo_es_uno_por_nodo():
    banco, cl = _banco()
    cl.storages_api["pve1"] = cl._storages_por_defecto()
    cl.plantillas[9000]["config"]["scsi0"] = "lvm1:vm-9000-disk-0,size=8G"
    cl.storages_api["pve1"].append(
        {"storage": "lvm1", "type": "lvm", "content": "images", "active": 1, "shared": 0,
         "total": 1000 * 1024**3, "avail": 500 * 1024**3, "formats": [{"raw": 1}, "raw"]}
    )  # fmt: skip
    from .apoyo_lote import storage

    banco.inv.storages_todos["pve1"] += (storage("lvm1", "lvm", 500, contenido="images"),)
    banco.inv.storages["pve1"] += (storage("lvm1", "lvm", 500, contenido="images"),)
    cl.retardo_clon = 0.05
    plan = banco.planificar(_clon_lote(4, modo=ModoClon.COMPLETO, storage_destino="local-lvm"))
    assert not plan.problemas, plan.problemas
    libro = banco.ejecutar(plan)
    assert set(banco.estados(libro)) == {"ok"}
    assert cl.max_clon_por_nodo == 1
    assert all(c["full"] == "1" and c["storage"] == "local-lvm" for c in cl.cuerpos_clon.values())


def test_ca_o17_10_importaciones_a_un_storage_compartido_desde_tres_nodos_max_dos_a_la_vez():
    nodos = ("pve1", "pve2", "pve3")
    banco, cl = _banco(nodos, plantillas=(), listados=((("pve1", "local"), [VOLID_IMAGEN]),))
    for n in nodos:  # el mismo storage compartido en todos los nodos con la imagen
        cl.contenido[(n, "nfs1")] = ["nfs1:import/cirros.qcow2"]
        cl.storages_api[n] = [
            {"storage": "nfs1", "type": "nfs", "content": "images,import", "active": 1, "shared": 1,
             "total": 10**12, "avail": 5 * 10**11, "formats": [{"raw": 1, "qcow2": 1}, "raw"]},
        ]  # fmt: skip
    from .apoyo_lote import storage

    for n in nodos:
        sts = (storage("nfs1", "nfs", 500, compartido=True, contenido="images,import"),)
        banco.inv.storages_todos[n] = sts
        banco.inv.storages[n] = sts
    cl.al_post = lambda vmid: time.sleep(0.15)
    plant = cfg_import(
        "nfs1:import/cirros.qcow2",
        cfg={"vmid": 0, "nombre": "plantilla", "nodo": "", "discos": [Disco("nfs1", 8)]},
    )
    plan = banco.planificar(definicion(6, plantilla_vm=plant))
    assert not plan.problemas, plan.problemas
    libro = banco.ejecutar(plan)
    assert set(banco.estados(libro)) == {"ok"}
    assert cl.max_post_por_nodo == 1  # D-20.5
    assert cl.max_post_total == 2  # llega a CONCURRENCIA_PESADA_POR_STORAGE y no lo supera
    assert sorted(cl.posts) == list(range(100, 106)) and set(cl.posts.values()) == {1}
    # CA-O17.3: cada MV lleva su propio import-from (no se comparte)
    assert all(
        "import-from=nfs1:import/cirros.qcow2" in c["scsi0"] for c in cl.cuerpos_post.values()
    )


def test_ca_o30_9_n_mvs_con_iso_montan_el_mismo_volid_y_no_hay_transferencias():
    banco, cl = _banco(("pve1", "pve2"), plantillas=())
    for n in ("pve1", "pve2"):
        cl.contenido[(n, "local")] = [VOLID_ISO]
    plant = cfg_iso(None, vmid=0, nombre="plantilla", nodo="", discos=[Disco("local-lvm", 8)])
    plant.detalle_origen = DetalleIso(iso=RefVolumen("alpine.iso"))  # solo el nombre
    plan = banco.planificar(definicion(4, plantilla_vm=plant))
    assert not plan.problemas, plan.problemas
    libro = banco.ejecutar(plan)
    assert set(banco.estados(libro)) == {"ok"}
    assert {c["ide2"] for c in cl.cuerpos_post.values()} == {f"{VOLID_ISO},media=cdrom"}
    assert not [c for c in cl.llamadas if c.ruta.endswith(("/upload", "/download-url"))]
    assert set(cl.posts.values()) == {1} and len(cl.posts) == 4  # INV-L1


def test_ca_o29_3_inv_o12_la_simulacion_de_un_lote_de_clones_solo_hace_get():
    banco, cl = _banco()
    cl.reiniciar_llamadas()
    d = _clon_lote(3, ajustes=AjustesClon(cores=4))
    resultado = simular(banco.sesion, d, banco.inv, reloj=banco.reloj)
    assert cl.solo_lecturas and cl.total("POST") == 0 and cl.total("PUT") == 0
    assert sorted(resultado.peticiones_detalle) == [100, 101, 102]
    acciones = [p.accion for p in resultado.peticiones_detalle[100]]
    assert acciones[0] == AccionPeticion.CLONAR and AccionPeticion.CONFIGURAR in acciones
    assert resultado.peticiones[100]["newid"] == "100"  # la petición principal es la del clon
    assert cl.clones == {} and not cl.vms


def test_inv_o12_la_simulacion_de_iso_e_importacion_tampoco_escribe():
    banco, cl = _banco(plantillas=(), listados=((("pve1", "local"), [VOLID_ISO, VOLID_IMAGEN]),))
    iso = cfg_iso(None, vmid=0, nombre="plantilla", nodo="", discos=[Disco("local-lvm", 8)])
    iso.detalle_origen = DetalleIso(iso=RefVolumen("alpine.iso"))
    imp = cfg_import(
        None, cfg={"vmid": 0, "nombre": "plantilla", "nodo": "", "discos": [Disco("local-lvm", 8)]}
    )
    imp.detalle_origen = DetalleImportacion(imagen=RefVolumen("cirros.qcow2"))
    cl.reiniciar_llamadas()
    for plant in (iso, imp):
        res = simular(banco.sesion, definicion(2, plantilla_vm=plant), banco.inv, reloj=banco.reloj)
        assert not res.plan.problemas, res.plan.problemas
        assert len(res.peticiones) == 2
    assert cl.solo_lecturas


def test_ca_o21_1_inyeccion_de_fallos_nunca_envia_dos_clones_para_el_mismo_vmid():
    from .apoyo_lote import envio_incierto, nodo_caido

    escenarios = [
        envio_incierto(),
        nodo_caido("pve1", 596),
        nodo_caido("pve1", 597),
        ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "401"),
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"),
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500"),
        ErrorProxLaunch(CodigoError.UPID_INVALIDO, {}, "sin upid"),
    ]
    for fallo in escenarios:
        banco, cl = _banco()
        cl.regla("POST", r"/clone$", fallo)
        plan = banco.planificar(_clon_lote(2))
        banco.ejecutar(plan)
        intentos: dict[str, int] = {}
        for c in cl.llamadas:
            if c.metodo == "POST":
                intentos[c.datos["newid"]] = intentos.get(c.datos["newid"], 0) + 1
        assert set(intentos.values()) <= {1}, (fallo.codigo, intentos)
        assert cl.posts == {}  # y ningún POST /qemu como sustituto


def test_ca_o30_2_inv_l1_tambien_para_iso_e_importacion_con_fallos_en_el_post():
    from .apoyo_lote import envio_incierto, nodo_caido

    for fallo in (
        envio_incierto(),
        nodo_caido("pve1", 596),
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500"),
    ):
        for origen in ("iso", "import"):
            banco, cl = _banco(
                plantillas=(), listados=((("pve1", "local"), [VOLID_ISO, VOLID_IMAGEN]),)
            )
            if origen == "iso":
                plant = cfg_iso(
                    None, vmid=0, nombre="plantilla", nodo="", discos=[Disco("local-lvm", 8)]
                )
                plant.detalle_origen = DetalleIso(iso=RefVolumen("alpine.iso"))
            else:
                plant = cfg_import(
                    None,
                    cfg={
                        "vmid": 0,
                        "nombre": "plantilla",
                        "nodo": "",
                        "discos": [Disco("local-lvm", 8)],
                    },
                )
                plant.detalle_origen = DetalleImportacion(imagen=RefVolumen("cirros.qcow2"))
            cl.regla("POST", r"/qemu$", fallo)
            banco.ejecutar(banco.planificar(definicion(2, plantilla_vm=plant)))
            assert set(cl.posts.values()) <= {1}, (origen, fallo.codigo, dict(cl.posts))


def test_ca_o22_6_un_put_fallido_del_clon_deja_parcial_y_el_lote_continua_sin_reenviar():
    banco, cl = _banco()
    cl.regla("PUT", r"/qemu/100/config$", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"))
    plan = banco.planificar(_clon_lote(3, ajustes=AjustesClon(cores=4)))
    libro = banco.ejecutar(plan)
    estados = {e.elemento.vmid: e.estado for e in libro.instantanea()}
    assert estados[100] == EstadoMV.PARCIAL
    assert estados[101] == estados[102] == EstadoMV.OK  # RF-L14: continúa con las demás
    assert cl.clones == {100: 1, 101: 1, 102: 1}
    entrada = next(e for e in libro.instantanea() if e.elemento.vmid == 100)
    assert any(a.startswith("ajuste_pendiente:") for a in entrada.avisos)
    assert entrada.upid is not None  # elegible para rollback por tener UPID propio


def test_ca_o22_6_reintentar_ajustes_del_lote_resuelve_la_mv_parcial_sin_nuevo_clon():
    banco, cl = _banco()
    regla = cl.regla(
        "PUT", r"/qemu/100/config$", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom")
    )
    plan = banco.planificar(_clon_lote(2, ajustes=AjustesClon(cores=4)))
    libro = banco.ejecutar(plan)
    entrada = next(e for e in libro.instantanea() if e.elemento.vmid == 100)
    assert tiene_ajustes_pendientes(entrada)
    regla.veces = 0  # el servidor se recupera
    reintentar_ajustes(
        libro, [100, 101], banco.sesion, banco.reloj, banco.inv, banco.observador, ControlLote()
    )
    final = {e.elemento.vmid: e.estado for e in libro.instantanea()}
    assert final == {100: EstadoMV.OK, 101: EstadoMV.OK}
    assert cl.clones == {100: 1, 101: 1} and cl.vms[100]["config"]["cores"] == "4"


def test_ca_o30_3_el_rollback_de_clones_borra_solo_las_mvs_y_deja_la_plantilla_intacta():
    banco, cl = _banco()
    plan = banco.planificar(_clon_lote(2))
    libro = banco.ejecutar(plan)
    rb = ServicioRollback(banco.sesion, banco.reloj, intervalo_s=0.01)
    candidatos = rb.elegibles(libro, etiquetado=True)
    assert [c.elegible for c in candidatos] == [True, True]
    resultados = rb.deshacer(
        candidatos, lambda r: None, ControlLote(), id_lote=plan.id_lote, etiquetado=True
    )
    assert [r.estado for r in resultados] == [EstadoRollback.ELIMINADA] * 2
    assert sorted(cl.deletes) == [100, 101] and 9000 in cl.plantillas and 9000 not in cl.deletes
    assert all(
        p == {"destroy-unreferenced-disks": 0} or p == {"destroy-unreferenced-disks": "0"}
        for p in cl.params_delete.values()
    )  # D-21


def test_es_propia_un_clon_sin_etiqueta_con_upid_propio_si_y_rescatado_no():
    from proxlaunch.nucleo.lote.modelos import EntradaLibro

    banco, cl = _banco()
    plan = banco.planificar(_clon_lote(1))
    libro = banco.ejecutar(plan)
    entrada = libro.instantanea()[0]
    sin_etiqueta = {"name": entrada.elemento.nombre}
    assert es_propia(sin_etiqueta, entrada, plan.id_lote, True) is True
    rescatada = EntradaLibro(**{**entrada.__dict__, "avisos": ("creada_tras_comprobar",)})
    assert es_propia(sin_etiqueta, rescatada, plan.id_lote, True) is False
    otro_nombre = {"name": "ajena"}
    assert es_propia(otro_nombre, entrada, plan.id_lote, True) is False
    # una MV de disco vacío sin etiqueta nunca es propia (regla de M2)
    vacio = EntradaLibro(
        entrada.elemento.__class__(0, "x", 100, "pve1", cfg_base(vmid=100, nombre="x")), upid="u"
    )
    assert es_propia({"name": "x"}, vacio, plan.id_lote, True) is False


def test_nunca_se_borra_el_vmid_de_la_plantilla_aunque_coincidiera_con_el_del_clon():
    from proxlaunch.nucleo.lote.modelos import EntradaLibro

    elem = ElementoPlan(0, "x", 9000, "pve1", _clon(ModoClon.ENLAZADO))
    elem = dataclasses.replace(elem, cfg=dataclasses.replace(elem.cfg, vmid=9000, nombre="x"))
    assert (
        es_propia(
            {"name": "x", "tags": "proxlaunch;lote-ab"}, EntradaLibro(elem, upid="u"), "ab", True
        )
        is False
    )


def test_ca_o03_1_un_lote_sin_origen_no_lee_catalogo_ni_hace_gets_nuevos():
    banco, cl = _banco(plantillas=())
    plan = banco.planificar(definicion(2, plantilla_vm=plantilla()))
    assert not [c for c in cl.llamadas if "/storage" in c.ruta]  # ni listados ni ?format=1
    assert plan.catalogo is None  # sin orígenes, el plan no arrastra catálogo
