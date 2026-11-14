"""Revalidación de un lote cargado contra el servidor actual (RF-G03, RF-G04, RF-G05;
CA-G01.1, CA-G03.2, CA-G04.1..G04.5, CA-G05.1..G05.3; INV-M1, INV-M6; §13 caso 8 y 14;
LAB-M3-02 con mocks).

``desajustes`` es puro y NUNCA sustituye en silencio; ``sustituir`` es la acción explícita del
usuario. Un lote cargado pasa por el planificador completo de M2 con el inventario del momento.
"""

import copy
import dataclasses

import pytest

from proxlaunch.nucleo.lote.modelos import Algoritmo, Destino, ModoDestino
from proxlaunch.nucleo.lotes_guardados.formato import leer_lote, lote_a_bytes
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.lotes_guardados.revalidacion import (
    Desajuste,
    TipoDesajuste,
    desajustes,
    sustituir,
)
from proxlaunch.nucleo.modelos.inventario import Bridge
from proxlaunch.nucleo.modelos.vm import Disco, Firmware, InterfazRed

from .apoyo_lote import (
    Cluster,
    crear_banco,
    definicion,
    inventario,
    nodo,
    plantilla,
    storage,
)
from .apoyo_mvp3 import definicion_filas, fila


def _inv():
    """Tres nodos: pve1 (datos, rapido; vmbr0, vmbr1), pve2 (datos; vmbr0), pve3 en línea sin 'images'."""  # noqa: E501
    return inventario(
        (nodo("pve1"), nodo("pve2"), nodo("pve3", en_linea=False)),
        storages={
            "pve1": (storage("datos"), storage("rapido", "lvmthin", 100), storage("solo-iso", contenido="iso"), storage("apagado", activo=False)),  # noqa: E501
            "pve2": (storage("datos"), storage("nfs-compartido", "nfs", 300, compartido=True)),
            "pve3": (storage("datos"),),
        },
        bridges={
            "pve1": (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "OVSBridge", True), Bridge("eno1", "eth", False)),  # noqa: E501
            "pve2": (Bridge("vmbr0", "bridge", False),),
            "pve3": (Bridge("vmbr0", "bridge", False),),
        },
    )  # fmt: skip


def _por_tipo(ds, tipo):
    return [d for d in ds if d.tipo == tipo]


# --- Homogéneo ------------------------------------------------------------------------------------


def test_un_lote_que_encaja_no_tiene_desajustes():
    assert desajustes(definicion(3), _inv()) == ()


def test_un_storage_inexistente_se_senala_con_los_disponibles():
    """CA-G04.3: «Usar otro…» ofrece los valores disponibles (nunca sustitución silenciosa)."""
    d = definicion(3, plantilla_vm=plantilla(discos=[Disco("nube", 10), Disco("datos", 5)]))
    (desajuste,) = desajustes(d, _inv())
    assert desajuste == Desajuste(
        TipoDesajuste.STORAGE,
        "nube",
        (),
        ("discos[0].storage",),
        ("datos", "nfs-compartido", "rapido"),
    )  # activos con «images» de los nodos del lote; sin «solo-iso» ni «apagado»


def test_inactivo_o_sin_images_no_son_validos_para_el_lote():
    d = definicion(2, plantilla_vm=plantilla(discos=[Disco("apagado", 10), Disco("solo-iso", 10)]))
    valores = {x.valor for x in desajustes(d, _inv())}
    assert valores == {"apagado", "solo-iso"}


def test_un_bridge_inexistente_o_que_no_es_bridge_se_senala():
    d = definicion(
        2,
        plantilla_vm=plantilla(
            redes=[InterfazRed("vmbr9"), InterfazRed("eno1"), InterfazRed("vmbr1")]
        ),
    )
    ds = _por_tipo(desajustes(d, _inv()), TipoDesajuste.BRIDGE)
    assert {x.valor for x in ds} == {"vmbr9", "eno1"}
    assert all(x.disponibles == ("vmbr0", "vmbr1") for x in ds)
    assert {c for x in ds for c in x.campos} == {"redes[0].bridge", "redes[1].bridge"}


def test_el_storage_efi_solo_cuenta_con_ovmf():
    base = plantilla(storage_efi="inexistente")
    assert desajustes(definicion(2, plantilla_vm=base), _inv()) == ()
    d = definicion(2, plantilla_vm=plantilla(firmware=Firmware.OVMF, storage_efi="inexistente"))
    (x,) = desajustes(d, _inv())
    assert (x.tipo, x.valor, x.campos) == (
        TipoDesajuste.STORAGE_EFI,
        "inexistente",
        ("storage_efi",),
    )


def test_sin_disco_no_hay_desajuste_de_storage():
    d = definicion(2, plantilla_vm=plantilla(con_disco=False, discos=[Disco("nube", 1)]))
    assert desajustes(d, _inv()) == ()


def test_el_universo_de_un_nodo_elegido_es_solo_ese_nodo():
    """«rapido» existe en pve1 pero no en pve2."""
    d = definicion(
        2,
        modo=ModoDestino.UN_NODO,
        nodos=("pve2",),
        plantilla_vm=plantilla(discos=[Disco("rapido", 5)]),
    )
    (x,) = desajustes(d, _inv())
    assert (x.tipo, x.valor) == (TipoDesajuste.STORAGE, "rapido")
    assert "rapido" not in x.disponibles and "nfs-compartido" in x.disponibles


def test_nodos_inexistentes_o_sin_conexion_en_un_destino_no_automatico():
    """CA-G04.4 / CA-G05.3."""
    d = definicion(2, modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve1", "pve3", "fantasma"))
    ds = _por_tipo(desajustes(d, _inv()), TipoDesajuste.NODO)
    assert [(x.valor, x.campos) for x in ds] == [
        ("pve3", ("destino.nodos[1]",)),
        ("fantasma", ("destino.nodos[2]",)),
    ]
    assert all(x.disponibles == ("pve1", "pve2") for x in ds)  # los que están en línea


def test_un_destino_automatico_no_produce_desajuste_de_nodo():
    assert not _por_tipo(desajustes(definicion(3), _inv()), TipoDesajuste.NODO)


def test_desajustes_no_modifica_la_definicion_ni_el_inventario():
    d = definicion(
        3, plantilla_vm=plantilla(discos=[Disco("nube", 10)], redes=[InterfazRed("vmbr9")])
    )
    copia_d, inv = copy.deepcopy(d), _inv()
    copia_inv = copy.deepcopy(inv)
    desajustes(d, inv)
    assert d == copia_d and inv == copia_inv


def test_leer_un_lote_no_sustituye_nada_en_silencio():
    """CA-G04.3: el storage inexistente sigue siendo el que dice el archivo."""
    d = definicion(2, plantilla_vm=plantilla(discos=[Disco("storage-de-otro-servidor", 10)]))
    cargado = leer_lote(lote_a_bytes(LoteGuardado("L", d), app_version="1")).lote.definicion
    assert cargado.plantilla.discos[0].storage == "storage-de-otro-servidor"
    assert [x.valor for x in desajustes(cargado, _inv())] == ["storage-de-otro-servidor"]


# --- sustituir (acción explícita) -----------------------------------------------------------------


def test_sustituir_storage_cambia_todos_los_discos_con_ese_valor_y_no_toca_el_original():
    d = definicion(
        2, plantilla_vm=plantilla(discos=[Disco("nube", 10), Disco("nube", 5), Disco("datos", 1)])
    )
    original = copy.deepcopy(d)
    (x,) = desajustes(d, _inv())
    nueva = sustituir(d, x, "rapido")
    assert [s.storage for s in nueva.plantilla.discos] == ["rapido", "rapido", "datos"]
    assert d == original  # inmutable: la definición anterior no cambia
    assert desajustes(nueva, _inv()) == ()


def test_sustituir_bridge_y_storage_efi():
    d = definicion(
        2,
        plantilla_vm=plantilla(
            firmware=Firmware.OVMF, storage_efi="x", redes=[InterfazRed("vmbr9")]
        ),
    )
    for x in desajustes(d, _inv()):
        d = sustituir(d, x, "datos" if x.tipo == TipoDesajuste.STORAGE_EFI else "vmbr1")
    assert (d.plantilla.storage_efi, d.plantilla.redes[0].bridge) == ("datos", "vmbr1")
    assert desajustes(d, _inv()) == ()


def test_pasar_a_automatico_un_destino_con_nodos_inexistentes_conserva_el_algoritmo():
    """CA-G04.4."""
    d = definicion(2, modo=ModoDestino.UN_NODO, nodos=("fantasma",), algoritmo=Algoritmo.POR_TURNOS)
    (x,) = desajustes(d, _inv())
    nueva = sustituir(d, x, None)
    assert nueva.destino == Destino(ModoDestino.AUTOMATICO, (), Algoritmo.POR_TURNOS)
    assert desajustes(nueva, _inv()) == ()


def test_sustituir_un_nodo_por_otro_no_repite_nodos():
    d = definicion(2, modo=ModoDestino.NODOS_ELEGIDOS, nodos=("fantasma", "pve1"))
    (x,) = desajustes(d, _inv())
    assert sustituir(d, x, "pve1").destino.nodos == ("pve1",)
    assert sustituir(d, x, "pve2").destino.nodos == ("pve2", "pve1")


def test_solo_el_nodo_puede_pasar_a_automatico():
    d = definicion(2, plantilla_vm=plantilla(discos=[Disco("nube", 10)]))
    (x,) = desajustes(d, _inv())
    with pytest.raises(ValueError):
        sustituir(d, x, None)


# --- Por filas ------------------------------------------------------------------------------------


def test_por_filas_agrupa_el_mismo_valor_con_los_indices_y_campos_de_cada_fila():
    d = definicion_filas([
        fila("a-01", discos=[Disco("nube", 10)]),
        fila("a-02"),
        fila("a-03", discos=[Disco("datos", 5), Disco("nube", 5)], redes=[InterfazRed("vmbr9")]),
    ])  # fmt: skip
    ds = desajustes(d, _inv())
    nube = _por_tipo(ds, TipoDesajuste.STORAGE)
    assert len(nube) == 1
    assert nube[0].indices == (0, 2)
    assert nube[0].campos == ("filas[0].discos[0].storage", "filas[2].discos[1].storage")
    (bridge,) = _por_tipo(ds, TipoDesajuste.BRIDGE)
    assert (bridge.valor, bridge.indices, bridge.campos) == (
        "vmbr9",
        (2,),
        ("filas[2].redes[0].bridge",),
    )


def test_por_filas_los_nodos_fijos_sin_conexion_o_inexistentes_se_senalan():
    d = definicion_filas(
        [fila("a", nodo="pve1"), fila("b", nodo="pve3"), fila("c", nodo="fantasma"), fila("d")]
    )
    ds = _por_tipo(desajustes(d, _inv()), TipoDesajuste.NODO)
    assert [(x.valor, x.indices) for x in ds] == [("pve3", (1,)), ("fantasma", (2,))]


def test_por_filas_sustituir_solo_cambia_las_filas_afectadas_y_pasar_a_automatico_limpia_el_nodo():
    d = definicion_filas(
        [
            fila("a", discos=[Disco("nube", 1)], nodo="fantasma"),
            fila("b"),
            fila("c", discos=[Disco("nube", 1)], nodo="pve1"),
        ]
    )
    original = copy.deepcopy(d)
    ds = desajustes(d, _inv())
    storage_x = _por_tipo(ds, TipoDesajuste.STORAGE)[0]
    d2 = sustituir(d, storage_x, "datos")
    assert [f.cfg.discos[0].storage for f in d2.filas] == ["datos", "datos", "datos"]
    nodo_x = _por_tipo(ds, TipoDesajuste.NODO)[0]
    d3 = sustituir(d2, nodo_x, None)
    assert [f.nodo for f in d3.filas] == [
        None,
        None,
        "pve1",
    ]  # solo la fila con el nodo inexistente
    assert desajustes(d3, _inv()) == ()
    assert d == original and d3.es_por_filas and d3.cantidad == 3


def test_por_filas_el_nodo_se_puede_sustituir_por_otro():
    d = definicion_filas([fila("a", nodo="fantasma"), fila("b", nodo="fantasma")])
    (x,) = desajustes(d, _inv())
    assert [f.nodo for f in sustituir(d, x, "pve2").filas] == ["pve2", "pve2"]


# --- Revalidación con el planificador completo de M2 (INV-M1, INV-M6, LAB-M3-02) ------------------


def _plan_sin_ruido(plan):
    """Todo el plan salvo ``definicion`` (la plantilla difiere solo en vmid/nombre/nodo)."""
    return dataclasses.replace(plan, definicion=None)  # type: ignore[arg-type]


def test_lote_guardado_y_cargado_da_el_mismo_plan_que_el_lote_directo():
    """LAB-M3-02 (mock) / CA-G01.1: «mismo plan que el lote directo»."""
    directo = definicion(3, prefijo="aula", vmid_inicial=200, etiquetar=True)
    cargado = leer_lote(
        lote_a_bytes(LoteGuardado("Aula", directo), app_version="1")
    ).lote.definicion
    banco = crear_banco(("pve1", "pve2"))
    plan_directo = banco.planificar(directo)
    banco2 = crear_banco(("pve1", "pve2"))
    plan_cargado = banco2.planificar(cargado)
    assert not plan_directo.bloqueado
    assert _plan_sin_ruido(plan_cargado) == _plan_sin_ruido(plan_directo)
    assert [(e.nombre, e.vmid, e.nodo) for e in plan_cargado.elementos] == [
        (e.nombre, e.vmid, e.nodo) for e in plan_directo.elementos
    ]


def test_lote_por_filas_guardado_y_cargado_da_el_mismo_plan():
    directo = definicion_filas(
        [fila("a-01", vmid=210), fila("a-02", cores=4), fila("a-03", nodo="pve2")], vmid_inicial=300
    )
    cargado = leer_lote(lote_a_bytes(LoteGuardado("L", directo), app_version="1")).lote.definicion
    plan_a = crear_banco(("pve1", "pve2")).planificar(directo)
    plan_b = crear_banco(("pve1", "pve2")).planificar(cargado)
    assert not plan_a.bloqueado
    assert _plan_sin_ruido(plan_b) == _plan_sin_ruido(plan_a)


def test_etiquetar_falso_se_conserva_y_el_plan_no_lleva_etiquetas():
    cargado = leer_lote(
        lote_a_bytes(LoteGuardado("L", definicion(2, etiquetar=False)), app_version="1")
    ).lote.definicion
    plan = crear_banco(("pve1",)).planificar(cargado)
    assert all(e.cfg.etiquetas == () for e in plan.elementos)


def test_cargar_y_revalidar_solo_hace_lecturas_y_un_storage_inexistente_da_cero_post():
    """INV-M1 / INV-M6 / LAB-M3-02: contador de métodos; los VMIDs se reservan al planificar."""
    d = definicion(3, plantilla_vm=plantilla(discos=[Disco("storage-ajeno", 10)]))
    cargado = leer_lote(lote_a_bytes(LoteGuardado("L", d), app_version="1")).lote.definicion
    banco = crear_banco(("pve1",))
    assert [x.valor for x in desajustes(cargado, banco.inv)] == ["storage-ajeno"]
    plan = banco.planificar(cargado)
    assert plan.bloqueado
    assert any(p.params.get("storage") == "storage-ajeno" for p in plan.problemas)  # V-L11/V-17
    assert banco.cluster.total("POST") == 0 and banco.cluster.total("DELETE") == 0
    assert banco.cluster.solo_lecturas
    assert dict(banco.cluster.posts) == {}


def test_un_transporte_que_falla_ante_cualquier_metodo_distinto_de_get_no_se_dispara_al_cargar():
    """INV-M1: ``leer_lote``, ``desajustes`` y ``planificar`` nunca escriben."""
    cluster = Cluster(("pve1",))

    def _prohibido(ll):
        raise AssertionError(f"escritura prohibida: {ll.metodo} {ll.ruta}")

    for metodo in ("POST", "PUT", "DELETE", "PATCH"):
        cluster.regla(metodo, r".*", _prohibido)
    banco = crear_banco(("pve1",), cluster=cluster)
    cargado = leer_lote(
        lote_a_bytes(LoteGuardado("L", definicion(3)), app_version="1")
    ).lote.definicion
    desajustes(cargado, banco.inv)
    plan = banco.planificar(cargado)
    assert not plan.bloqueado and cluster.solo_lecturas


def test_un_vmid_inicial_guardado_y_ocupado_se_salta_y_el_lote_cargado_no_se_modifica():
    """CA-G04.5: política de M2 (saltar y avisar); no se modifica lo cargado."""
    cargado = leer_lote(
        lote_a_bytes(LoteGuardado("L", definicion(3, vmid_inicial=200)), app_version="1")
    ).lote.definicion
    antes = copy.deepcopy(cargado)
    banco = crear_banco(("pve1",))
    banco.cluster.ocupados.update({200, 201})
    plan = banco.planificar(cargado)
    assert [e.vmid for e in plan.elementos] == [202, 203, 204]
    assert plan.vmids_saltados == (200, 201)
    assert cargado == antes and cargado.vmid_inicial == 200


def test_lote_guardado_en_cluster_de_3_nodos_y_cargado_en_un_nodo_suelto():
    """§13.8 / CA-G05.2: destino Automático con storage y bridge presentes → sin cambios."""
    en_cluster = definicion(6, prefijo="web")
    cargado = leer_lote(
        lote_a_bytes(LoteGuardado("L", en_cluster), app_version="1")
    ).lote.definicion
    suelto = crear_banco(("pve1",), inv=inventario((nodo("pve1"),), es_cluster=False))
    assert desajustes(cargado, suelto.inv) == ()
    plan = suelto.planificar(cargado)
    assert not plan.bloqueado and {e.nodo for e in plan.elementos} == {"pve1"}


def test_nodos_elegidos_que_no_existen_en_el_servidor_nuevo_dan_v_l13_y_no_se_reinterpretan():
    """CA-G05.3."""
    d = definicion(2, modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve2", "pve3"))
    cargado = leer_lote(lote_a_bytes(LoteGuardado("L", d), app_version="1")).lote.definicion
    suelto = crear_banco(("pve1",), inv=inventario((nodo("pve1"),), es_cluster=False))
    assert [x.tipo for x in desajustes(cargado, suelto.inv)] == [TipoDesajuste.NODO] * 2
    plan = suelto.planificar(cargado)
    assert plan.bloqueado and any(p.regla == "V-L13" for p in plan.problemas)
    assert cargado.destino.nodos == ("pve2", "pve3")  # no se reasignó a pve1


def test_lote_con_storage_compartido_en_el_clusters_se_planifica_y_no_hay_desajuste():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={n: (storage("nfs", "nfs", 500, compartido=True),) for n in ("pve1", "pve2")},
    )
    d = definicion(4, plantilla_vm=plantilla(discos=[Disco("nfs", 50)]))
    cargado = leer_lote(lote_a_bytes(LoteGuardado("L", d), app_version="1")).lote.definicion
    assert desajustes(cargado, inv) == ()
    assert not crear_banco(("pve1", "pve2"), inv=inv).planificar(cargado).bloqueado


def test_un_servidor_distinto_con_otro_inventario_recalcula_los_desajustes_sin_arrastrar_lo_anterior():  # noqa: E501
    """CA-G04.8 / CA-G05.4: el resultado depende solo del inventario recibido."""
    d = definicion(2, plantilla_vm=plantilla(discos=[Disco("rapido", 5)]))
    assert desajustes(d, _inv()) == ()
    otro = inventario((nodo("pve9"),), storages={"pve9": (storage("local"),)}, es_cluster=False)
    assert [x.valor for x in desajustes(d, otro)] == ["rapido"]
    assert desajustes(d, _inv()) == ()


def test_memoria_que_supera_la_del_nodo_se_avisa_en_el_plan_sin_modificar_el_lote():
    """§13.14: V-L12 (aviso no bloqueante)."""
    d = definicion(2, plantilla_vm=plantilla(memoria_mib=900_000))
    plan = crear_banco(("pve1",)).planificar(d)
    assert any(p.regla == "V-L12" for p in plan.problemas)
