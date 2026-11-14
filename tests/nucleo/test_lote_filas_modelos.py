"""Modelos y utilidades del lote por filas (D-22; RF-C08, RF-C09, RF-G07; CA-C08.1, CA-C08.6,
CA-C08.10, CA-C08.12, CA-C09.3, CA-C07.4; arquitectura §3.1, §4.1, §4.6).

Camino único ``filas_efectivas``: el lote homogéneo es el caso particular «todas las filas
comparten ``cfg`` y nada es fijo». Las utilidades (``sin_filas``, ``reemplazar_fila``,
``definicion_para_reintento``) son puras y nunca mutan la definición recibida.
"""

import copy
import dataclasses

import pytest

from proxlaunch.nucleo.lote import planificador
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, MAX_LOTE, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.lote.filas import (
    definicion_para_reintento,
    definicion_por_filas,
    filas_efectivas,
    reemplazar_fila,
    sin_filas,
    usa_nombre_de_plantilla,
    validar_filas,
)
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    DefinicionLote,
    Destino,
    ElementoPlan,
    FilaLote,
    InformeLote,
    MetadatosInforme,
    ModoDestino,
    PatronNombres,
    Plan,
    PoliticaThin,
    Severidad,
)
from proxlaunch.nucleo.lote.nombres import generar_nombres
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco

from .apoyo_lote import definicion, inventario, plantilla
from .apoyo_mvp3 import cfg_hw, definicion_filas, fila, filas_heterogeneas


def _por(problemas, regla):
    return [p for p in problemas if p.regla == regla]


# --- Compatibilidad de firmas (arquitectura §4.6, CA-C08.12) --------------------------------------


def test_los_constructores_de_m2_siguen_siendo_validos_y_el_modo_es_homogeneo():
    d = DefinicionLote(plantilla(), 3, PatronNombres("web"))
    assert d.filas == () and d.es_por_filas is False
    assert d.destino == Destino() and d.vmid_inicial is None and d.etiquetar is True
    assert (
        DefinicionLote(
            plantilla(), 3, PatronNombres("web"), Destino(), 150, False, PoliticaThin.BLOQUEAR
        ).vmid_inicial
        == 150
    )


def test_plan_e_informe_de_m2_se_construyen_sin_los_campos_nuevos():
    campos_plan = [f.name for f in dataclasses.fields(Plan)]
    campos_informe = [f.name for f in dataclasses.fields(InformeLote)]
    # MVP 4 añade `catalogo` (Plan) y `transferencias` (InformeLote) AL FINAL, con defecto.
    assert campos_plan[-2:] == ["filas_excedentes", "catalogo"]
    assert campos_informe[-2:] == ["por_filas", "transferencias"]
    por_nombre_plan = {f.name: f for f in dataclasses.fields(Plan)}
    por_nombre_inf = {f.name: f for f in dataclasses.fields(InformeLote)}
    assert por_nombre_plan["filas_excedentes"].default == ()
    assert por_nombre_plan["catalogo"].default is None
    assert por_nombre_inf["por_filas"].default is False
    assert por_nombre_inf["transferencias"].default == ()
    # El orden de los campos de M2 no cambió: los nuevos van al final.
    assert campos_plan[:3] == ["id_lote", "definicion", "elementos"]


def test_filalote_solo_exige_nombre_y_cfg():
    f = FilaLote("a", cfg_hw())
    assert (f.vmid, f.nodo, f.origen) == (None, None, None)


def test_es_por_filas_depende_solo_de_que_haya_filas():
    assert definicion_filas([fila("a")]).es_por_filas
    assert not dataclasses.replace(definicion_filas([fila("a")]), filas=()).es_por_filas


def test_los_modelos_nuevos_son_inmutables():
    f = fila("a")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.nombre = "b"  # type: ignore[misc]
    d = definicion_filas([f])
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.filas = ()  # type: ignore[misc]


# --- filas_efectivas: camino único ----------------------------------------------------------------


def test_homogeneo_genera_cantidad_filas_con_los_nombres_del_patron_sin_vmid_ni_nodo():
    d = definicion(4, prefijo="aula", separador="_", inicio=7, relleno=3)
    filas = filas_efectivas(d)
    assert (
        [f.nombre for f in filas]
        == generar_nombres(d.patron, 4)
        == ["aula_007", "aula_008", "aula_009", "aula_010"]
    )
    assert all(f.vmid is None and f.nodo is None and f.origen is None for f in filas)
    assert all(f.cfg is d.plantilla for f in filas)  # se comparte; quien la use debe copiarla


def test_homogeneo_de_una_maquina_con_prefijo_vacio_usa_el_nombre_de_la_plantilla():
    d = definicion(1, prefijo="", plantilla_vm=plantilla(nombre="mi-servidor"))
    assert [f.nombre for f in filas_efectivas(d)] == ["mi-servidor"]
    assert usa_nombre_de_plantilla(d) and planificador.usa_nombre_de_plantilla(d)


def test_por_filas_devuelve_las_filas_tal_cual():
    d = definicion_filas(filas_heterogeneas())
    assert filas_efectivas(d) is d.filas


def test_usa_nombre_de_plantilla_es_falso_en_por_filas_aunque_sea_una_fila_con_prefijo_vacio():
    """Si no, un lote por filas de una fila tomaría el nombre de la plantilla (§3.1)."""
    d = definicion_filas([fila("la-fila")], plantilla_base=cfg_hw(nombre="NO-USAR"))
    assert d.cantidad == 1 and d.patron.prefijo == ""
    assert usa_nombre_de_plantilla(d) is False and planificador.usa_nombre_de_plantilla(d) is False
    assert [f.nombre for f in filas_efectivas(d)] == ["la-fila"]


@pytest.mark.parametrize("cantidad", [1, 2, 5, 10])
def test_homogeneo_con_cantidad_cero_o_negativa_no_genera_filas(cantidad):
    assert len(filas_efectivas(definicion(cantidad))) == cantidad
    assert filas_efectivas(definicion(0)) == () and filas_efectivas(definicion(-3)) == ()


# --- definicion_por_filas -------------------------------------------------------------------------


def test_definicion_por_filas_fija_cantidad_destino_automatico_y_patron_vacio():
    filas = filas_heterogeneas()
    d = definicion_por_filas(
        filas,
        plantilla_base=cfg_hw(),
        algoritmo=Algoritmo.POR_TURNOS,
        vmid_inicial=300,
        etiquetar=False,
        politica_thin=PoliticaThin.BLOQUEAR,
    )
    assert d.cantidad == 4 and d.filas == tuple(filas) and d.es_por_filas
    assert d.destino == Destino(ModoDestino.AUTOMATICO, (), Algoritmo.POR_TURNOS)
    assert d.patron == PatronNombres(prefijo="")
    assert (d.vmid_inicial, d.etiquetar, d.politica_thin) == (300, False, PoliticaThin.BLOQUEAR)


def test_definicion_por_filas_valores_por_defecto():
    d = definicion_por_filas([fila("a")], plantilla_base=cfg_hw())
    assert (d.destino.algoritmo, d.vmid_inicial, d.etiquetar, d.politica_thin) == (
        Algoritmo.EQUILIBRADO, None, True, PoliticaThin.CONFIRMAR_CON_TOPE,
    )  # fmt: skip


def test_definicion_por_filas_acepta_cualquier_secuencia_y_la_congela():
    lista = [fila("a"), fila("b")]
    d = definicion_por_filas(lista, plantilla_base=cfg_hw())
    lista.append(fila("c"))
    assert isinstance(d.filas, tuple) and len(d.filas) == 2


def test_sin_filas_la_definicion_no_es_por_filas_y_se_rechaza_con_v_l01():
    d = definicion_por_filas([], plantilla_base=cfg_hw())
    assert not d.es_por_filas and d.cantidad == 0
    assert _por(planificador.validar_definicion(d, inventario(), (9, 2)), "V-L01")


# --- validar_filas (V-L01, V-M07, V-M10, V-02, V-L13) ---------------------------------------------


def test_en_un_lote_homogeneo_validar_filas_no_valida_nada():
    assert validar_filas(definicion(0)) == []


def test_un_lote_por_filas_correcto_no_tiene_problemas():
    assert validar_filas(definicion_filas(filas_heterogeneas())) == []


def test_v_l01_si_la_cantidad_no_coincide_o_se_sale_de_1_a_max_lote():
    filas = [fila(f"m-{i}") for i in range(3)]
    for cantidad in (2, 4, 0, -1, True):
        d = dataclasses.replace(definicion_filas(filas), cantidad=cantidad)
        assert [p.campo for p in _por(validar_filas(d), "V-L01")] == ["cantidad"], cantidad
    d101 = definicion_filas([fila(f"m-{i}") for i in range(MAX_LOTE + 1)])
    assert _por(validar_filas(d101), "V-L01")
    assert not _por(
        validar_filas(definicion_filas([fila(f"m-{i}") for i in range(MAX_LOTE)])), "V-L01"
    )


@pytest.mark.parametrize("nombre", ["", "   ", "\t"])
def test_v_m07_nombre_vacio_por_fila_con_su_indice(nombre):
    d = definicion_filas([fila("bien-01"), fila(nombre), fila("bien-03"), fila(nombre or "x")])
    indices = [p.indice for p in _por(validar_filas(d), "V-M07")]
    assert indices[0] == 1 and all(
        p.severidad == Severidad.ERROR for p in _por(validar_filas(d), "V-M07")
    )


def test_v_m10_nombres_repetidos_sin_distinguir_mayusculas_marca_todas_las_filas_implicadas():
    d = definicion_filas(
        [fila("Web-01"), fila("otro"), fila("web-01"), fila("WEB-01"), fila("otro-2")]
    )
    problemas = _por(validar_filas(d), "V-M10")
    assert sorted(p.indice for p in problemas) == [0, 2, 3]
    assert all(p.campo == "nombre" and p.severidad == Severidad.ERROR for p in problemas)
    assert {p.params["filas"] for p in problemas} == {"1,3,4"}  # posiciones 1-based sin `origen`


def test_v_m10_usa_el_numero_de_origen_del_csv_en_el_mensaje_si_lo_hay():
    d = definicion_filas([fila("a", origen=3), fila("b", origen=4), fila("A", origen=9)])
    (p, q) = _por(validar_filas(d), "V-M10")
    assert p.params["filas"] == q.params["filas"] == "3,9"
    assert sorted([p.indice, q.indice]) == [0, 2]


def test_v_m10_vmids_explicitos_repetidos_marcan_todas_las_filas():
    d = definicion_filas(
        [
            fila("a", vmid=150),
            fila("b", vmid=151),
            fila("c", vmid=150),
            fila("d"),
            fila("e", vmid=150),
        ]
    )
    problemas = _por(validar_filas(d), "V-M10")
    assert sorted(p.indice for p in problemas) == [0, 2, 4]
    assert all(p.campo == "vmid" and p.params["vmid"] == "150" for p in problemas)


def test_filas_sin_vmid_no_chocan_entre_si():
    assert not _por(validar_filas(definicion_filas([fila("a"), fila("b"), fila("c")])), "V-M10")


@pytest.mark.parametrize("vmid", [99, 0, -5, 1_000_000_000, True])
def test_v_02_vmid_explicito_fuera_de_100_a_999999999(vmid):
    d = definicion_filas([fila("a"), fila("b", vmid=vmid)])
    (p,) = _por(validar_filas(d), "V-02")
    assert p.indice == 1 and p.campo == "vmid"


@pytest.mark.parametrize("vmid", [100, 999_999_999])
def test_vmid_explicito_en_los_extremos_es_valido(vmid):
    assert validar_filas(definicion_filas([fila("a", vmid=vmid)])) == []


@pytest.mark.parametrize(
    "destino",
    [
        Destino(ModoDestino.UN_NODO, ("pve1",)),
        Destino(ModoDestino.NODOS_ELEGIDOS, ("pve1", "pve2")),
    ],
)
def test_v_l13_el_destino_de_un_lote_por_filas_es_siempre_automatico(destino):
    d = dataclasses.replace(definicion_filas([fila("a")]), destino=destino)
    (p,) = _por(validar_filas(d), "V-L13")
    assert p.campo == "destino"


def test_el_patron_no_se_evalua_en_por_filas():
    """§4.1: ``Patrón (V-L02..V-L04): no se evalúa``."""
    d = dataclasses.replace(
        definicion_filas([fila("a")]), patron=PatronNombres("ñ ñ", "??", -5, 99)
    )
    assert not [
        p
        for p in planificador.validar_definicion(d, inventario(), (9, 2))
        if p.regla in {"V-L02", "V-L03", "V-L04"}
    ]


def test_validar_definicion_de_por_filas_reutiliza_validar_filas_y_valida_v_l07():
    d = definicion_filas([fila("a"), fila("A")], vmid_inicial=50)
    reglas = {p.regla for p in planificador.validar_definicion(d, inventario(), (9, 2))}
    assert {"V-M10", "V-L07"} <= reglas


def test_v_l07_cuenta_solo_las_filas_sin_vmid_para_el_ultimo_vmid_automatico():
    base = [fila(f"m-{i}") for i in range(3)]
    d = definicion_filas(base, vmid_inicial=999_999_998)
    assert any(
        p.regla == "V-L07" for p in planificador.validar_definicion(d, inventario(), (9, 2))
    )  # 3 autos: 998, 999, 1000
    con_fijas = definicion_filas(
        [fila("a"), fila("b", vmid=150), fila("c", vmid=151)], vmid_inicial=999_999_999
    )
    assert not any(
        p.regla == "V-L07" for p in planificador.validar_definicion(con_fijas, inventario(), (9, 2))
    )  # 1 auto


# --- sin_filas / reemplazar_fila (CA-C08.6, CA-C09.3) ---------------------------------------------


def test_sin_filas_quita_las_indicadas_y_ajusta_la_cantidad_sin_mutar_la_original():
    d = definicion_filas(filas_heterogeneas(), vmid_inicial=300)
    original = copy.deepcopy(d)
    nueva = sin_filas(d, {0, 2})
    assert [f.nombre for f in nueva.filas] == ["pg-02", "pg-04"] and nueva.cantidad == 2
    assert (nueva.vmid_inicial, nueva.destino, nueva.etiquetar) == (300, d.destino, d.etiquetar)
    assert d == original


@pytest.mark.parametrize("indices", [[4], [-1], [100], [True], [1.0], ["1"]])
def test_sin_filas_con_indice_inexistente_es_value_error(indices):
    with pytest.raises(ValueError):
        sin_filas(definicion_filas(filas_heterogeneas()), indices)


def test_sin_filas_acepta_cualquier_coleccion_y_repetidos_y_lista_vacia():
    d = definicion_filas(filas_heterogeneas())
    assert sin_filas(d, []) == d
    assert sin_filas(d, (1, 1, 1)).cantidad == 3
    assert sin_filas(d, frozenset({3})).cantidad == 3 and sin_filas(d, range(2)).cantidad == 2


def test_sin_filas_de_todas_deja_un_lote_vacio_que_se_rechaza():
    """CA-C07.5: si se excluyen todas las filas no se puede continuar."""
    nueva = sin_filas(definicion_filas(filas_heterogeneas()), range(4))
    assert nueva.cantidad == 0 and not nueva.es_por_filas
    assert _por(planificador.validar_definicion(nueva, inventario(), (9, 2)), "V-L01")


def test_sin_filas_en_un_lote_homogeneo_es_value_error():
    with pytest.raises(ValueError):
        sin_filas(definicion(3), [0])


def test_reemplazar_fila_cambia_solo_esa_fila_y_conserva_el_resto():
    """CA-C09.3: «Asignar automáticamente» = ``vmid=None`` en esa fila."""
    d = definicion_filas([fila("a", vmid=150), fila("b", vmid=151), fila("c")])
    original = copy.deepcopy(d)
    nueva = reemplazar_fila(d, 1, dataclasses.replace(d.filas[1], vmid=None))
    assert [f.vmid for f in nueva.filas] == [150, None, None] and nueva.cantidad == 3
    assert nueva.filas[0] is d.filas[0] and nueva.filas[2] is d.filas[2]
    assert d == original


@pytest.mark.parametrize("indice", [4, -1, 99, True, 1.0])
def test_reemplazar_fila_con_indice_invalido_es_value_error(indice):
    with pytest.raises(ValueError):
        reemplazar_fila(definicion_filas(filas_heterogeneas()), indice, fila("x"))


def test_reemplazar_fila_en_homogeneo_es_value_error():
    with pytest.raises(ValueError):
        reemplazar_fila(definicion(3), 0, fila("x"))


# --- definicion_para_reintento (CA-C08.10) --------------------------------------------------------


def _elementos(d, vmids, nodos, etiquetas=(ETIQUETA_APP, f"{PREFIJO_ETIQUETA_LOTE}viejo123")):
    salida = []
    for i, f in enumerate(d.filas):
        cfg = copy.deepcopy(f.cfg)
        cfg.vmid, cfg.nombre, cfg.nodo = vmids[i], f.nombre, nodos[i]
        cfg.etiquetas = (*f.cfg.etiquetas, *etiquetas)
        salida.append(ElementoPlan(i, f.nombre, vmids[i], nodos[i], cfg))
    return salida


def test_el_reintento_de_un_lote_homogeneo_es_como_en_m2():
    d = definicion(5, vmid_inicial=200)
    nueva = definicion_para_reintento(d, [object(), object()])  # type: ignore[list-item]
    assert nueva == dataclasses.replace(d, cantidad=2, vmid_inicial=None)


def test_el_reintento_por_filas_conserva_nombre_vmid_nodo_origen_y_la_configuracion_de_cada_fila():
    d = definicion_filas(
        [fila("a-01", origen=2, cores=1), fila("a-02", origen=3, vmid=150, cores=4), fila("a-03", origen=4, cores=8, etiquetas=("propia",))],  # noqa: E501
        algoritmo=Algoritmo.POR_TURNOS, vmid_inicial=300, etiquetar=False, politica_thin=PoliticaThin.ADVERTIR,  # noqa: E501
    )  # fmt: skip
    elementos = _elementos(d, [300, 150, 301], ["pve1", "pve2", "pve1"])
    pendientes = [elementos[0], elementos[2]]  # la fila a-02 se creó
    nueva = definicion_para_reintento(d, pendientes)
    assert nueva.es_por_filas and nueva.cantidad == 2 and nueva.vmid_inicial is None
    assert [(f.nombre, f.vmid, f.nodo, f.origen) for f in nueva.filas] == [
        ("a-01", 300, "pve1", 2), ("a-03", 301, "pve1", 4),
    ]  # fmt: skip
    assert [f.cfg.cores for f in nueva.filas] == [1, 8]  # su propia configuración
    assert (nueva.destino, nueva.etiquetar, nueva.politica_thin) == (
        d.destino,
        False,
        PoliticaThin.ADVERTIR,
    )


def test_el_reintento_quita_las_etiquetas_del_lote_anterior_pero_no_las_propias():
    d = definicion_filas([fila("a", etiquetas=("propia",))])
    (el,) = _elementos(d, [150], ["pve1"])
    assert el.cfg.etiquetas == ("propia", ETIQUETA_APP, "lote-viejo123")
    (f,) = definicion_para_reintento(d, [el]).filas
    assert f.cfg.etiquetas == ("propia",)


def test_el_reintento_entrega_copias_independientes_de_las_configuraciones():
    d = definicion_filas([fila("a")])
    (el,) = _elementos(d, [150], ["pve1"])
    (f,) = definicion_para_reintento(d, [el]).filas
    f.cfg.cores = 99
    f.cfg.discos[0].tamano_gib = 99
    assert el.cfg.cores != 99 and el.cfg.discos[0].tamano_gib != 99


def test_el_reintento_sin_pendientes_da_una_definicion_sin_filas():
    nueva = definicion_para_reintento(definicion_filas([fila("a")]), [])
    assert nueva.cantidad == 0 and nueva.filas == ()


def test_el_reintento_ignora_un_indice_fuera_de_las_filas_sin_perder_la_fila():
    d = definicion_filas([fila("a", origen=2)])
    (el,) = _elementos(d, [150], ["pve1"])
    el_raro = dataclasses.replace(el, indice=77)
    (f,) = definicion_para_reintento(d, [el_raro]).filas
    assert f.origen is None and f.nombre == "a"


def test_los_metadatos_de_informe_siguen_siendo_los_de_m2():
    assert [f.name for f in dataclasses.fields(MetadatosInforme)] == [
        "nombre_perfil", "version_proxmox", "es_cluster", "nombre_cluster", "fecha_hora_local",
    ]  # fmt: skip


def test_una_configuracion_de_fila_no_se_comparte_con_otra_aunque_el_csv_repita_valores():
    c = cfg_hw()
    d = definicion_filas([FilaLote("a", c), FilaLote("b", c)])
    assert isinstance(d.filas[0].cfg, ConfiguracionVM) and isinstance(
        d.filas[0].cfg.discos[0], Disco
    )
