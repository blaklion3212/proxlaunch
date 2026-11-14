"""Planificador del lote: reserva de VMIDs, compatibilidad con M1, etiquetas y reglas V-L
(RF-L01, RF-L03, RF-L04, RF-L09, RF-L24, V-L06, V-L07, V-L08, V-L12, V-L15, V-L16).

La reserva usa el cliente real sobre un clúster simulado; las demás comprobaciones son sobre
funciones puras. Sin red y con reloj simulado.
"""

import re
import time

import pytest

from proxlaunch.nucleo.capacidades import Capacidades, Funcion, admite_etiquetas
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import (
    MAX_CONSULTAS_SIMULTANEAS,
    MAX_SALTO_VMID,
    VMID_MAXIMO,
)
from proxlaunch.nucleo.lote.modelos import ModoDestino, Severidad
from proxlaunch.nucleo.lote.planificador import (
    Planificador,
    construir_plan,
    usa_nombre_de_plantilla,
    validar_definicion,
)
from proxlaunch.nucleo.modelos import Disco
from proxlaunch.nucleo.seleccion_nodo import elegir_nodo
from proxlaunch.nucleo.validacion import validar_vm

from .apoyo_lote import (
    Cluster,
    crear_banco,
    definicion,
    inventario,
    nodo,
    nodo_caido,
    plantilla,
    storage,
)

VERSION = (9, 2)
ID = "abcd1234"


def _reglas(problemas, regla):
    return [p for p in problemas if p.regla == regla]


def _consultas_nextid(cluster):
    return [c for c in cluster.llamadas_a("GET", r"^/cluster/nextid$") if c.params]


# --- Reserva de VMIDs (RF-L03) --------------------------------------------------------------------


def test_ca_l03_1_tres_vmids_libres_desde_100(banco):
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    assert [e.vmid for e in plan.elementos] == [100, 101, 102]
    assert plan.vmids_saltados == ()


def test_ca_l03_2_un_vmid_ocupado_se_salta_y_se_informa(banco):
    banco.cluster.ocupados = {101}
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    assert [e.vmid for e in plan.elementos] == [100, 102, 103]
    assert plan.vmids_saltados == (101,)


@pytest.mark.parametrize(
    ("ocupados", "esperados", "saltados"),
    [
        ({100}, [101, 102, 103], (100,)),  # ocupado al principio
        ({102}, [100, 101, 103], (102,)),  # en medio (entre el último y el anterior)
        ({101, 102}, [100, 103, 104], (101, 102)),  # varios consecutivos
        ({103, 150}, [100, 101, 102], ()),  # fuera del rango usado: no se informan
        ({100, 101, 102}, [103, 104, 105], (100, 101, 102)),  # el rango entero
    ],
)
def test_caso_limite_vmids_ocupados_en_cada_posicion(banco, ocupados, esperados, saltados):
    banco.cluster.ocupados = ocupados
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    assert [e.vmid for e in plan.elementos] == esperados
    assert plan.vmids_saltados == saltados


def test_los_vmids_del_plan_son_crecientes_y_sin_repetir(banco):
    banco.cluster.ocupados = {103, 107, 108, 120}
    plan = banco.planificar(definicion(20, vmid_inicial=100))
    vmids = [e.vmid for e in plan.elementos]
    assert vmids == sorted(set(vmids))
    assert not set(vmids) & banco.cluster.ocupados


def test_ca_l03_3_cada_vmid_se_confirma_con_nextid_y_no_con_cluster_resources(banco):
    banco.cluster.ocupados = {101}
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    consultados = {int(c.params["vmid"]) for c in _consultas_nextid(banco.cluster)}
    assert {e.vmid for e in plan.elementos} <= consultados
    # Las MVs existentes no se descubren con /cluster/resources (que solo sirve al aviso V-L06).
    banco.cluster.vms[100] = {"nodo": "pve1", "config": {"name": "x"}, "status": "stopped"}
    plan2 = banco.planificar(definicion(2, vmid_inicial=100))
    assert 100 not in [e.vmid for e in plan2.elementos]


def test_ca_l03_3_error_de_red_en_el_septimo_vmid_aborta_sin_plan_parcial(banco):
    def _falla_en_el_107(llamada):
        if llamada.params and llamada.params.get("vmid") == 107:
            raise nodo_caido("pve1", 595)
        from .apoyo_lote import NORMAL

        return NORMAL

    banco.cluster.regla("GET", r"^/cluster/nextid$", _falla_en_el_107)
    with pytest.raises(ErrorProxLaunch) as exc:
        banco.planificar(definicion(10, vmid_inicial=101))
    assert exc.value.codigo == CodigoError.NODO_NO_DISPONIBLE
    assert banco.cluster.total("POST") == 0


def test_ca_l03_3_un_error_de_servidor_en_la_consulta_nunca_da_el_vmid_por_libre(banco):
    banco.cluster.regla(
        "GET",
        r"^/cluster/nextid$",
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"),
    )
    with pytest.raises(ErrorProxLaunch):
        banco.planificar(definicion(2, vmid_inicial=100))


def test_ca_l03_4_planificar_dos_veces_da_el_mismo_plan(banco):
    banco.cluster.ocupados = {102}
    d = definicion(5, vmid_inicial=100)
    a, b = banco.planificar(d), banco.planificar(d)
    assert a == b


def test_ca_l03_4_no_se_usa_nextid_sin_parametro_para_varios_vmids(banco):
    banco.planificar(definicion(5))  # sin vmid_inicial: sale de inv.proximo_vmid
    sin_parametro = [
        c for c in banco.cluster.llamadas_a("GET", r"^/cluster/nextid$") if not c.params
    ]
    assert sin_parametro == []


def test_el_vmid_inicial_por_defecto_es_el_proximo_del_inventario():
    b = crear_banco(inv=inventario((nodo("pve1"),), proximo_vmid=250))
    plan = b.planificar(definicion(2))
    assert [e.vmid for e in plan.elementos] == [250, 251]


@pytest.mark.parametrize("inicio", [99, 0, -5, 1_000_000_000, 1.5, "100", True])
def test_ca_l03_5_inicio_manual_fuera_de_100_999999999_bloquea_sin_consultar(banco, inicio):
    plan = banco.planificar(definicion(2, vmid_inicial=inicio))
    assert plan.bloqueado
    assert _reglas(plan.problemas, "V-L07")
    assert banco.cluster.llamadas == []  # una definición inválida no toca el servidor


@pytest.mark.parametrize(
    ("inicio", "cantidad", "valido"),
    [
        (100, 1, True),
        (VMID_MAXIMO, 1, True),
        (VMID_MAXIMO - 9, 10, True),  # el último es justo 999999999
        (VMID_MAXIMO - 8, 10, False),  # el último pasaría de 999999999
        (999_999_995, 10, False),  # caso límite del probador
    ],
)
def test_ca_l03_5_el_ultimo_vmid_del_plan_no_puede_pasar_de_999999999(inicio, cantidad, valido):
    problemas = validar_definicion(definicion(cantidad, vmid_inicial=inicio), inventario(), VERSION)
    assert (not _reglas(problemas, "V-L07")) is valido


def test_ca_l03_6_sin_ventana_suficiente_falla_con_e_l02_y_no_hay_bucle(banco):
    banco.cluster.ocupados = set(range(100, 100 + MAX_SALTO_VMID))
    with pytest.raises(ErrorProxLaunch) as exc:
        banco.planificar(definicion(3, vmid_inicial=100))
    assert exc.value.codigo == CodigoError.LOTE_VMIDS_INSUFICIENTES
    assert exc.value.params == {"n": "3", "inicio": "100"}
    assert len(_consultas_nextid(banco.cluster)) <= MAX_SALTO_VMID


def test_ca_l03_6_si_solo_caben_menos_de_los_pedidos_tambien_falla(banco):
    ocupados = set(range(100, 100 + MAX_SALTO_VMID - 2))  # quedan 2 libres en la ventana
    banco.cluster.ocupados = ocupados
    with pytest.raises(ErrorProxLaunch) as exc:
        banco.planificar(definicion(3, vmid_inicial=100))
    assert exc.value.codigo == CodigoError.LOTE_VMIDS_INSUFICIENTES


def test_ca_l03_6_la_ventana_se_corta_en_el_maximo_de_vmid(banco):
    banco.cluster.ocupados = {VMID_MAXIMO}
    with pytest.raises(ErrorProxLaunch) as exc:
        banco.planificar(definicion(2, vmid_inicial=VMID_MAXIMO - 1))
    assert exc.value.codigo == CodigoError.LOTE_VMIDS_INSUFICIENTES


def test_ca_l03_7_consultas_acotadas_y_como_mucho_8_a_la_vez(banco):
    import threading

    saltos = set(range(100, 130))  # 30 ocupados al principio
    banco.cluster.ocupados = saltos
    # Las primeras 8 consultas esperan a las demás: si la reserva fuera secuencial, la barrera
    # se rompería; si pasara de 8 a la vez, ``max_peticiones`` lo delataría.
    barrera = threading.Barrier(MAX_CONSULTAS_SIMULTANEAS, timeout=5)
    usadas = []

    def _espera(llamada):
        from .apoyo_lote import NORMAL

        if len(usadas) < MAX_CONSULTAS_SIMULTANEAS:
            usadas.append(1)
            barrera.wait()
        return NORMAL

    banco.cluster.regla("GET", r"^/cluster/nextid$", _espera)
    plan = banco.planificar(definicion(20, vmid_inicial=100))
    n_consultas = len(_consultas_nextid(banco.cluster))
    assert n_consultas <= 20 + len(plan.vmids_saltados)
    assert banco.cluster.max_peticiones <= MAX_CONSULTAS_SIMULTANEAS
    assert banco.cluster.max_peticiones == MAX_CONSULTAS_SIMULTANEAS  # se paraleliza de verdad


def test_ca_l03_7_el_orden_de_los_vmids_no_depende_del_orden_de_llegada_de_las_respuestas(banco):
    banco.cluster.ocupados = {103, 105}
    plan = banco.planificar(definicion(10, vmid_inicial=100))
    assert [e.vmid for e in plan.elementos] == [100, 101, 102, 104, 106, 107, 108, 109, 110, 111]
    assert [e.nombre for e in plan.elementos][:2] == ["web-01", "web-02"]


# --- N = 1 y compatibilidad con M1 (RF-L04, CA-L04.1) ---------------------------------------------


def test_n1_sin_prefijo_usa_el_nombre_de_la_plantilla_y_no_valida_el_patron():
    d = definicion(1, prefijo="", plantilla_vm=plantilla(nombre="mi-servidor"))
    assert usa_nombre_de_plantilla(d)
    assert not validar_definicion(d, inventario(), VERSION)
    plan = construir_plan(
        d,
        inventario(),
        [100],
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )
    assert [e.nombre for e in plan.elementos] == ["mi-servidor"]


def test_n1_con_prefijo_si_aplica_el_patron():
    d = definicion(1, prefijo="web")
    assert not usa_nombre_de_plantilla(d)
    plan = construir_plan(
        d,
        inventario(),
        [100],
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )
    assert plan.elementos[0].nombre == "web-01"


@pytest.mark.parametrize("cantidad", [2, 5])
def test_con_mas_de_una_maquina_el_prefijo_vacio_es_error(cantidad):
    problemas = validar_definicion(definicion(cantidad, prefijo=""), inventario(), VERSION)
    assert _reglas(problemas, "V-L02")


def test_n1_sin_prefijo_con_nombre_de_plantilla_invalido_falla_por_v_01_de_m1():
    d = definicion(1, prefijo="", plantilla_vm=plantilla(nombre="nombre_malo"))
    plan = construir_plan(
        d,
        inventario(),
        [100],
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )
    assert plan.bloqueado
    assert _reglas(plan.problemas, "V-01")
    assert not _reglas(plan.problemas, "V-L02")


def test_ca_l04_1_con_n1_la_peticion_es_la_de_m1_salvo_tags():
    inv = inventario()
    base = plantilla(nombre="srv-unico")
    nodo_m1, _ = elegir_nodo(inv, 32)
    cfg_m1 = plantilla(nombre="srv-unico", vmid=100, nodo=nodo_m1)
    esperado = construir_parametros(cfg_m1, inv)

    d = definicion(1, prefijo="", plantilla_vm=base)
    plan = construir_plan(
        d, inv, [100], [], id_lote=ID, ahora=0.0, version_validacion=VERSION, vms_visibles=None
    )
    (e,) = plan.elementos
    assert e.nodo == nodo_m1
    real = construir_parametros(e.cfg, inv, plan.version_validacion)
    sin_tags = {k: v for k, v in real.items() if k != "tags"}
    assert sin_tags == esperado
    assert real["tags"] == f"proxlaunch;lote-{ID}"


def test_ca_l04_1_sin_etiquetar_la_peticion_es_identica_a_la_de_m1():
    inv = inventario()
    nodo_m1, _ = elegir_nodo(inv, 32)
    esperado = construir_parametros(plantilla(nombre="srv", vmid=100, nodo=nodo_m1), inv)
    d = definicion(1, prefijo="", plantilla_vm=plantilla(nombre="srv"), etiquetar=False)
    plan = construir_plan(
        d, inv, [100], [], id_lote=ID, ahora=0.0, version_validacion=VERSION, vms_visibles=None
    )
    assert construir_parametros(plan.elementos[0].cfg, inv, plan.version_validacion) == esperado


def test_ca_l04_1_el_post_real_de_n1_lleva_los_mismos_parametros_que_m1(banco):
    inv = banco.inv
    esperado = construir_parametros(plantilla(nombre="srv", vmid=100, nodo="pve1"), inv)
    plan = banco.planificar(definicion(1, prefijo="", plantilla_vm=plantilla(nombre="srv")))
    banco.ejecutar(plan)
    enviado = banco.cluster.cuerpos_post[100]
    assert {k: v for k, v in enviado.items() if k != "tags"} == esperado


def test_ca_l04_2_las_peticiones_del_lote_solo_difieren_en_vmid_name_y_nodo():
    inv = inventario()
    plan = construir_plan(
        definicion(6),
        inv,
        list(range(100, 106)),
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )
    cuerpos = [construir_parametros(e.cfg, inv, plan.version_validacion) for e in plan.elementos]
    comunes = [{k: v for k, v in c.items() if k not in ("vmid", "name")} for c in cuerpos]
    assert all(c == comunes[0] for c in comunes)
    assert len({c["vmid"] for c in cuerpos}) == 6
    assert len({c["name"] for c in cuerpos}) == 6
    assert len({c["tags"] for c in cuerpos}) == 1  # las etiquetas son comunes al lote


def test_ca_l04_4_la_plantilla_se_valida_con_m1_en_el_nodo_de_cada_elemento():
    """Un bridge que falta en el nodo de destino bloquea (V-16 de M1), no el de otros."""
    from proxlaunch.nucleo.modelos import Bridge

    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        bridges={"pve1": (Bridge("vmbr0", "bridge", False),), "pve2": ()},
    )
    d = definicion(2, modo=ModoDestino.UN_NODO, nodos=("pve2",))
    plan = construir_plan(
        d, inv, [100, 101], [], id_lote=ID, ahora=0.0, version_validacion=VERSION, vms_visibles=None
    )
    assert plan.bloqueado
    assert _reglas(plan.problemas, "V-16")


def test_ca_l06_3_en_un_nodo_sin_el_storage_bloquea_con_v_17_de_m1():
    inv = inventario(
        (nodo("pve1"), nodo("pve2")),
        storages={"pve1": (storage("datos", "dir", 500),), "pve2": ()},
    )
    d = definicion(2, modo=ModoDestino.UN_NODO, nodos=("pve2",))
    plan = construir_plan(
        d, inv, [100, 101], [], id_lote=ID, ahora=0.0, version_validacion=VERSION, vms_visibles=None
    )
    assert plan.bloqueado
    assert _reglas(plan.problemas, "V-17")


def test_el_plan_no_modifica_la_plantilla_original():
    d = definicion(3)
    antes = repr(d.plantilla)
    construir_plan(
        d,
        inventario(),
        [100, 101, 102],
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )
    assert repr(d.plantilla) == antes


def test_construir_plan_exige_un_vmid_por_maquina():
    with pytest.raises(ValueError):
        construir_plan(
            definicion(3),
            inventario(),
            [100],
            [],
            id_lote=ID,
            ahora=0.0,
            version_validacion=VERSION,
            vms_visibles=None,
        )


def test_el_plan_lleva_id_de_8_hex_y_la_hora_del_reloj_inyectado(banco):
    banco.reloj.avanzar(42)
    p = Planificador(banco.sesion, banco.reloj).planificar(definicion(2), banco.inv)
    assert re.fullmatch(r"[0-9a-f]{8}", p.id_lote)
    assert p.generado_en == 42.0
    assert p.es_simulacion is False


def test_ca_l20_3_los_ids_de_lote_son_distintos_entre_planes(banco):
    ids = {
        Planificador(banco.sesion, banco.reloj).planificar(definicion(1), banco.inv).id_lote
        for _ in range(30)
    }
    assert len(ids) == 30


# --- Etiquetas (RF-L24) ---------------------------------------------------------------------------


def test_ca_l24_1_cada_elemento_lleva_las_dos_etiquetas_del_lote():
    plan = construir_plan(
        definicion(3),
        inventario(),
        [100, 101, 102],
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )
    assert all(e.cfg.etiquetas == ("proxlaunch", f"lote-{ID}") for e in plan.elementos)


def test_ca_l24_1_se_conservan_las_etiquetas_de_la_plantilla_sin_duplicar():
    d = definicion(1, plantilla_vm=plantilla(etiquetas=("mia", "proxlaunch")))
    plan = construir_plan(
        d,
        inventario(),
        [100],
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )
    assert plan.elementos[0].cfg.etiquetas == ("mia", "proxlaunch", f"lote-{ID}")


def test_ca_l24_3_sin_etiquetar_no_se_envia_tags():
    d = definicion(2, etiquetar=False)
    inv = inventario()
    plan = construir_plan(
        d, inv, [100, 101], [], id_lote=ID, ahora=0.0, version_validacion=VERSION, vms_visibles=None
    )
    assert all("tags" not in construir_parametros(e.cfg, inv, VERSION) for e in plan.elementos)


def test_ca_l24_2_las_etiquetas_generadas_cumplen_el_patron_de_proxmox():
    """Con muchos ids aleatorios, la etiqueta pasa V-24 y el id son 8 hex en minúsculas."""
    inv = inventario()
    d = definicion(1)
    patron_id = re.compile(r"^[0-9a-f]{8}$")
    banco = crear_banco(inv=inv)
    for _ in range(100):
        plan = Planificador(banco.sesion, banco.reloj).planificar(d, inv)
        assert patron_id.match(plan.id_lote)
        cfg = plan.elementos[0].cfg
        assert not [
            p for p in validar_vm(cfg, inv, Capacidades(VERSION, False)) if p.codigo == "V-24"
        ]
        assert cfg.etiquetas[1] == f"lote-{plan.id_lote}"


@pytest.mark.parametrize("etiqueta", ["Mayusc", "con espacio", "a;b", "ñ", "", "-inicial", "a,b"])
def test_regla_v_24_etiquetas_invalidas(etiqueta, hacer_cfg, inv, caps, con_codigo):
    problemas = validar_vm(hacer_cfg(etiquetas=(etiqueta,)), inv, caps)
    assert con_codigo(problemas, "V-24")


@pytest.mark.parametrize("etiqueta", ["proxlaunch", "lote-abcd1234", "a1", "_x", "a.b-c+d_e"])
def test_regla_v_24_etiquetas_validas(etiqueta, hacer_cfg, inv, caps, con_codigo):
    assert not con_codigo(validar_vm(hacer_cfg(etiquetas=(etiqueta,)), inv, caps), "V-24")


def test_ca_l24_2_la_tabla_de_capacidades_decide_si_se_envian_tags(hacer_cfg, inv):
    assert Capacidades((8, 0), False).tiene(Funcion.ETIQUETAS)  # toda versión soportada
    assert admite_etiquetas((9, 2))
    assert not admite_etiquetas((7, 2))
    cfg = hacer_cfg(etiquetas=("proxlaunch", "lote-abcd1234"))
    assert construir_parametros(cfg, inv, (9, 2))["tags"] == "proxlaunch;lote-abcd1234"
    assert "tags" not in construir_parametros(cfg, inv, (7, 2))  # se omite sin error


def test_los_valores_con_etiquetas_se_codifican_en_el_formulario_no_en_la_ruta():
    """La etiqueta viaja en el cuerpo (``datos``) del POST, nunca en la ruta (CT-9, RNF-L08)."""
    b = crear_banco()
    plan = b.planificar(definicion(1))
    b.ejecutar(plan)
    (post,) = b.cluster.llamadas_a("POST", r"/qemu$")
    assert post.ruta == "/nodes/pve1/qemu"
    assert post.datos["tags"] == f"proxlaunch;lote-{plan.id_lote}"


# --- Avisos y permisos (V-L06, V-L12, V-L15, V-L16) -----------------------------------------------


def test_ca_l02_7_v_l06_un_nombre_existente_avisa_pero_no_bloquea(banco):
    banco.cluster.agregar_vm(105, "pve1", "web-01")
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    (aviso,) = _reglas(plan.problemas, "V-L06")
    assert aviso.severidad == Severidad.AVISO
    assert aviso.params["nombre"] == "web-01"
    assert aviso.params["vmid"] == "105"
    assert aviso.params["calificado"] == "1"  # "puede haber otras que no puedes ver"
    assert not plan.bloqueado


def test_v_l06_la_comparacion_no_distingue_mayusculas(banco):
    banco.cluster.agregar_vm(105, "pve1", "WEB-02")
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    assert [p.params["nombre"] for p in _reglas(plan.problemas, "V-L06")] == ["web-02"]


def test_v_l06_si_no_se_pueden_listar_las_maquinas_no_hay_aviso_ni_bloqueo(banco):
    banco.cluster.regla(
        "GET", r"^/cluster/resources$", ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE)
    )
    plan = banco.planificar(definicion(2, vmid_inicial=100))
    assert not _reglas(plan.problemas, "V-L06")
    assert not plan.bloqueado


def test_ca_l09_1_v_l12_la_memoria_pedida_sobre_la_libre_avisa_por_nodo(banco):
    # pve1 tiene 64 GiB: 9 MVs de 8 GiB = 72 GiB.
    d = definicion(9, modo=ModoDestino.UN_NODO, nodos=("pve1",))
    plan = banco.planificar(d)
    (aviso,) = _reglas(plan.problemas, "V-L12")
    assert aviso.severidad == Severidad.AVISO
    assert aviso.params["nodo"] == "pve1"
    assert aviso.params["pedido_mib"] == str(9 * 8192)
    assert aviso.params["libre_mib"] == str(64 * 1024)
    assert not plan.bloqueado  # las MVs se crean apagadas


def test_ca_l09_1_la_memoria_justa_no_avisa(banco):
    d = definicion(8, modo=ModoDestino.UN_NODO, nodos=("pve1",))
    assert not _reglas(banco.planificar(d).problemas, "V-L12")


def test_ca_l09_2_mas_vcpus_que_los_cpus_del_nodo_avisa(banco):
    d = definicion(
        1, plantilla_vm=plantilla(sockets=2, cores=16), modo=ModoDestino.UN_NODO, nodos=("pve1",)
    )
    plan = banco.planificar(d)
    assert _reglas(plan.problemas, "V-L12.cpu")
    assert not plan.bloqueado


def test_ca_l11_7_v_l15_version_forzada_mayor_bloquea_la_creacion_real(banco):
    plan = banco.planificar(definicion(2), version_forzada=(9, 9))
    (v,) = _reglas(plan.problemas, "V-L15")
    assert v.severidad == Severidad.ERROR
    assert v.params["codigo"] == CodigoError.VERSION_FORZADA_MAYOR.value
    assert plan.bloqueado
    assert plan.elementos  # el plan existe: se puede simular
    assert plan.version_validacion == (9, 9)


@pytest.mark.parametrize("forzada", [(8, 0), (9, 1), (9, 2)])
def test_ca_l11_7_forzada_menor_o_igual_no_bloquea(banco, forzada):
    plan = banco.planificar(definicion(2), version_forzada=forzada)
    assert not _reglas(plan.problemas, "V-L15")
    assert plan.version_validacion == forzada
    assert not plan.bloqueado


def test_ca_l09_3_v_l16_sin_vm_allocate_bloquea_y_nombra_el_privilegio(banco):
    privs = {
        p: 1
        for p in [
            "VM.Audit",
            "VM.Config.Options",
            "VM.Config.HWType",
            "VM.Config.CPU",
            "VM.Config.Memory",
            "VM.Config.Network",
            "Datastore.AllocateSpace",
            "SDN.Use",
            "Sys.Audit",
        ]
    }
    banco.cluster.permisos = {"/": privs}
    plan = banco.planificar(definicion(2))
    (v,) = _reglas(plan.problemas, "V-L16")
    assert v.params["privilegio"] == "VM.Allocate"
    assert plan.bloqueado


def test_ca_l09_4_si_falla_la_consulta_de_permisos_no_se_bloquea(banco):
    banco.cluster.regla("GET", r"^/access/permissions$", nodo_caido("pve1", 596))
    plan = banco.planificar(definicion(2))
    assert not _reglas(plan.problemas, "V-L16")
    assert not plan.bloqueado


def test_v_l16_sin_otros_privilegios_no_se_marca_como_falta_de_vm_allocate(banco):
    privs = {
        p: 1
        for p in [
            "VM.Allocate",
            "VM.Audit",
            "VM.Config.Options",
            "VM.Config.HWType",
            "VM.Config.CPU",
            "VM.Config.Memory",
            "VM.Config.Network",
            "Datastore.AllocateSpace",
            "SDN.Use",
        ]
    }
    banco.cluster.permisos = {"/": privs}  # falta Sys.Audit, que no es de creación
    assert not _reglas(banco.planificar(definicion(2)).problemas, "V-L16")


# --- Determinismo y rendimiento (RNF-L05, RNF-L09) ------------------------------------------------


def test_rnf_l09_el_mismo_mock_da_el_mismo_plan_con_vmids_saltados(banco):
    banco.cluster.ocupados = {101, 105}
    d = definicion(8, vmid_inicial=100)
    assert banco.planificar(d) == banco.planificar(d)


def test_ca_rnf_l05_planificar_100_maquinas_con_reserva_de_vmids_tarda_menos_de_3_s(banco):
    banco.cluster.ocupados = set(range(110, 140))
    inicio = time.perf_counter()
    plan = banco.planificar(definicion(100, vmid_inicial=100))
    assert time.perf_counter() - inicio < 3.0
    assert len(plan.elementos) == 100
    assert len({e.vmid for e in plan.elementos}) == 100


def test_ca_rnf_l05_validar_100_maquinas_y_armar_el_plan_tarda_menos_de_1_s_de_cpu():
    inv = inventario(libre_gib=100_000)
    d = definicion(100, plantilla_vm=plantilla(discos=[Disco("datos", 8)]))
    inicio = time.process_time()
    plan = construir_plan(
        d,
        inv,
        list(range(100, 200)),
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=[],
    )
    assert time.process_time() - inicio < 1.0
    assert len(plan.elementos) == 100


def test_v_l05_los_nombres_de_un_plan_de_100_son_distintos():
    plan = construir_plan(
        definicion(100),
        inventario(libre_gib=100_000),
        list(range(100, 200)),
        [],
        id_lote=ID,
        ahora=0.0,
        version_validacion=VERSION,
        vms_visibles=None,
    )
    assert len({e.nombre for e in plan.elementos}) == 100
    assert not _reglas(plan.problemas, "V-L05")


def test_un_cluster_sin_nodos_en_linea_no_deja_elementos(banco):
    inv = inventario((nodo("pve1", en_linea=False),))
    b = crear_banco(inv=inv, cluster=Cluster(("pve1",)))
    plan = b.planificar(definicion(2))
    assert plan.bloqueado
    assert plan.elementos == ()
