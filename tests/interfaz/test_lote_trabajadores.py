"""Funciones de trabajo del lote (``trabajadores.py``): planificar, simular, ejecutar, continuar,
comprobar, deshacer y armar el reintento (RF-L03, RF-L11, RF-L12, RF-L15, RF-L18, RF-L21).

Se ejecutan directamente (sin hilos de Qt) con un cliente falso y el reloj simulado.
"""

from __future__ import annotations

import pytest

from proxlaunch.interfaz import trabajadores as tr
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.lote.modelos import (
    EstadoMV,
    EstadoRollback,
    Severidad,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo import ClienteLoteFalso, CreacionPorVmid, sesion_falsa
from .apoyo_lote import cfg_simple, definicion, elemento, res_error, res_perdida

EM = EstadoMV


@pytest.fixture
def cliente():
    return ClienteLoteFalso()


@pytest.fixture
def sesion(cliente):
    return sesion_falsa(cliente=cliente)


@pytest.fixture
def reloj():
    return RelojSimulado()


@pytest.fixture(autouse=True)
def _descubrir_falso(monkeypatch, inv_cluster):
    monkeypatch.setattr(tr, "descubrir", lambda sesion: inv_cluster)


# --- Planificar y replanificar -------------------------------------------------------------


def test_planificar_lote_reserva_vmids_y_devuelve_el_plan(sesion, reloj, inv_cluster, cliente):
    plan = tr.planificar_lote(sesion, reloj, definicion(3), inv_cluster, None)
    assert [e.vmid for e in plan.elementos] == [101, 102, 103]
    assert [e.nombre for e in plan.elementos] == ["web-01", "web-02", "web-03"]
    assert not any(ll[0] in ("crear_vm", "eliminar_vm") for ll in cliente.llamadas)


def test_planificar_lote_con_vmid_ocupado_lo_salta(sesion, reloj, inv_cluster, cliente):
    cliente.vmids_ocupados = {102}
    plan = tr.planificar_lote(sesion, reloj, definicion(3), inv_cluster, None)
    assert [e.vmid for e in plan.elementos] == [101, 103, 104] and plan.vmids_saltados == (102,)


def test_ca_l03_3_un_fallo_de_red_al_reservar_se_propaga_sin_plan_parcial(
    sesion, reloj, inv_cluster, cliente
):
    cliente.fallo_vmid_libre = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    with pytest.raises(ErrorProxLaunch) as e:
        tr.planificar_lote(sesion, reloj, definicion(3), inv_cluster, None)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE


def test_replanificar_lote_relee_el_inventario_y_devuelve_ambos(sesion, reloj, inv_cluster):
    inv, plan = tr.replanificar_lote(sesion, reloj, definicion(2), None)
    assert inv is inv_cluster and len(plan.elementos) == 2


def test_la_version_forzada_mayor_bloquea_el_plan_pero_se_calcula(sesion, reloj, inv_cluster):
    plan = tr.planificar_lote(sesion, reloj, definicion(2), inv_cluster, (9, 9))
    assert plan.bloqueado and plan.version_validacion == (9, 9)


# --- Simular (INV-L5) ---------------------------------------------------------------------------


def test_simular_lote_usa_el_cliente_de_solo_lectura_y_no_escribe(
    sesion, reloj, inv_cluster, cliente
):
    sim = tr.simular_lote(sesion, reloj, definicion(3), inv_cluster, None)
    assert cliente.pidio_solo_lectura == 1
    assert sim.plan.es_simulacion and sorted(sim.peticiones) == [101, 102, 103]
    assert sim.version_forzada is None and sim.version_detectada == (9, 2)
    assert cliente.creados == [] and cliente.eliminados == []


def test_inv_l5_si_la_simulacion_intentara_escribir_el_guardian_lo_detiene(
    sesion, reloj, inv_cluster, cliente
):
    vista = cliente.solo_lectura()
    with pytest.raises(AssertionError):
        vista.crear_vm("pve1", {})
    with pytest.raises(AssertionError):
        vista.eliminar_vm("pve1", 101)


def test_simular_con_version_forzada_la_registra(sesion, reloj, inv_cluster):
    sim = tr.simular_lote(sesion, reloj, definicion(2), inv_cluster, (8, 0))
    assert sim.version_forzada == (8, 0) and sim.plan.version_validacion == (8, 0)


# --- Ejecutar, continuar y comprobar --------------------------------------------------------------


def ejecutar(sesion, reloj, inv, plan, creacion, observados=None):
    control = ControlLote()
    observados = observados if observados is not None else []
    libro = tr.ejecutar_lote(
        sesion, reloj, plan, inv, observados.append, control, lambda s, r: creacion
    )
    return libro, control, observados


def test_ejecutar_lote_devuelve_el_libro_y_avisa_al_observador(sesion, reloj, inv_cluster):
    plan = tr.planificar_lote(sesion, reloj, definicion(3), inv_cluster, None)
    creacion = CreacionPorVmid()
    libro, _, vistos = ejecutar(sesion, reloj, inv_cluster, plan, creacion)
    assert [e.estado for e in libro.instantanea()] == [EM.OK] * 3
    assert len(vistos) >= 3 * 3  # cada máquina avisa varias veces (etapas)
    assert sorted(creacion.vmids_creados) == [101, 102, 103]


def test_rnf_l11_un_observador_que_falla_no_detiene_el_lote(sesion, reloj, inv_cluster):
    plan = tr.planificar_lote(sesion, reloj, definicion(3), inv_cluster, None)

    def observador(entrada):
        raise RuntimeError("la interfaz falló al pintar")

    libro = tr.ejecutar_lote(
        sesion, reloj, plan, inv_cluster, observador, ControlLote(), lambda s, r: CreacionPorVmid()
    )
    assert [e.estado for e in libro.instantanea()] == [EM.OK] * 3


def test_inv_l1_ejecutar_pendientes_nunca_reenvia_las_ya_intentadas(
    sesion, reloj, inv_cluster, cliente
):
    plan = tr.planificar_lote(sesion, reloj, definicion(3), inv_cluster, None)
    creacion = CreacionPorVmid({101: res_error(101, CodigoError.SIN_ESPACIO)})
    control = ControlLote()
    # Se «suspende» tras la primera: el resto queda pendiente para continuar luego.
    suspendido = ControlLote()
    suspendido.suspender()
    libro = tr.ejecutar_lote(
        sesion, reloj, plan, inv_cluster, lambda e: None, suspendido, lambda s, r: creacion
    )
    assert all(e.estado == EM.PENDIENTE for e in libro.instantanea())
    tr.continuar_lote(sesion, reloj, libro, inv_cluster, lambda e: None, control, False)
    # Continuar usa el servicio real de creación sobre el cliente falso: crea las tres una vez.
    assert sorted(int(p["vmid"]) for _, p in cliente.creados) == [101, 102, 103]
    assert [e.estado for e in libro.instantanea()] == [EM.OK] * 3
    tr.continuar_lote(sesion, reloj, libro, inv_cluster, lambda e: None, ControlLote(), False)
    assert len(cliente.creados) == 3  # una segunda continuación no vuelve a enviar nada


def test_comprobar_dudosas_lote_solo_lee(sesion, reloj, inv_cluster, cliente):
    # Una sola máquina: con más, la pérdida de conexión pausaría el lote esperando una decisión.
    plan = tr.planificar_lote(sesion, reloj, definicion(1), inv_cluster, None)
    creacion = CreacionPorVmid({101: res_perdida(101)})
    libro, _, _ = ejecutar(sesion, reloj, inv_cluster, plan, creacion)
    cliente.configs[101] = {"name": "web-01", "tags": ""}
    tr.comprobar_dudosas_lote(sesion, reloj, libro, lambda e: None, ControlLote())
    assert libro.instantanea()[0].estado == EM.OK
    assert cliente.creados == [] and cliente.eliminados == []


# --- Deshacer -------------------------------------------------------------------------------------


def test_deshacer_lote_elimina_las_elegidas_y_devuelve_resultados(
    sesion, reloj, inv_cluster, cliente
):
    plan = tr.planificar_lote(sesion, reloj, definicion(2), inv_cluster, None)
    libro, _, _ = ejecutar(sesion, reloj, inv_cluster, plan, CreacionPorVmid())
    for e in libro.instantanea():
        cliente.configs[e.elemento.vmid] = {
            "name": e.elemento.nombre,
            "tags": f"proxlaunch;lote-{plan.id_lote}",
        }
    candidatos = ServicioRollback(sesion, reloj).elegibles(libro, etiquetado=True)
    vistos = []
    resultados = tr.deshacer_lote(
        sesion, reloj, candidatos, vistos.append, ControlLote(), plan.id_lote, True
    )
    assert [r.estado for r in resultados] == [EstadoRollback.ELIMINADA] * 2
    assert sorted(cliente.eliminados) == [101, 102]
    assert vistos  # el observador recibió el avance


def test_deshacer_lote_no_toca_una_maquina_ajena(sesion, reloj, inv_cluster, cliente):
    plan = tr.planificar_lote(sesion, reloj, definicion(1), inv_cluster, None)
    libro, _, _ = ejecutar(sesion, reloj, inv_cluster, plan, CreacionPorVmid())
    cliente.configs[101] = {"name": "web-01", "tags": "lote-otro"}
    candidatos = ServicioRollback(sesion, reloj).elegibles(libro, etiquetado=True)
    resultados = tr.deshacer_lote(
        sesion, reloj, candidatos, lambda r: None, ControlLote(), plan.id_lote, True
    )
    assert resultados[0].estado == EstadoRollback.OMITIDA and cliente.eliminados == []


# --- Armar el reintento (RF-L21, CA-L21.1..4) -----------------------------------------------------


def a_reintentar(*vmids, nodo="pve1", etiquetas=()):
    elementos = []
    for i, vmid in enumerate(vmids):
        e = elemento(i, f"web-{vmid - 100:02d}", vmid, nodo)
        e.cfg.etiquetas = etiquetas
        elementos.append(e)
    return tuple(elementos)


def test_ca_l21_1_conserva_nombres_y_vmids_y_genera_un_id_nuevo(sesion, reloj):
    elementos = a_reintentar(102, 104, etiquetas=("proxlaunch", "lote-viejo"))
    inv, plan = tr.armar_reintento(sesion, reloj, elementos, definicion(2), None)
    assert [(e.indice, e.nombre, e.vmid, e.nodo) for e in plan.elementos] == [
        (0, "web-02", 102, "pve1"),
        (1, "web-04", 104, "pve1"),
    ]
    assert plan.id_lote not in ("viejo", "") and len(plan.id_lote) == 8
    assert not plan.bloqueado and plan.vmids_saltados == ()
    assert plan.reparto == {"pve1": (2, "elegido_por_usuario")}


def test_ca_l21_4_las_etiquetas_viejas_se_sustituyen_por_las_del_lote_nuevo(sesion, reloj):
    elementos = a_reintentar(102, 104, etiquetas=("proxlaunch", "lote-viejo", "mia"))
    _, plan = tr.armar_reintento(sesion, reloj, elementos, definicion(2), None)
    for e in plan.elementos:
        assert e.cfg.etiquetas == ("mia", ETIQUETA_APP, f"{PREFIJO_ETIQUETA_LOTE}{plan.id_lote}")
    # El libro anterior no se toca: los elementos originales conservan sus etiquetas.
    assert elementos[0].cfg.etiquetas == ("proxlaunch", "lote-viejo", "mia")


def test_sin_etiquetar_el_reintento_no_lleva_etiquetas_propias(sesion, reloj):
    elementos = a_reintentar(102, etiquetas=("proxlaunch", "lote-viejo"))
    _, plan = tr.armar_reintento(sesion, reloj, elementos, definicion(1, etiquetar=False), None)
    assert plan.elementos[0].cfg.etiquetas == ()


def test_ca_l21_1_nodo_destino_lleva_todas_las_maquinas_a_ese_nodo(sesion, reloj):
    elementos = a_reintentar(102, 104)
    _, plan = tr.armar_reintento(sesion, reloj, elementos, definicion(2), None, "pve3")
    assert {e.nodo for e in plan.elementos} == {"pve3"} == {e.cfg.nodo for e in plan.elementos}
    assert plan.reparto == {"pve3": (2, "elegido_por_usuario")}
    assert not plan.bloqueado
    assert {e.nodo for e in elementos} == {"pve1"}  # los elementos de origen no cambian


def test_ca_l21_1_un_nodo_destino_que_no_puede_alojarlas_se_valida_y_bloquea(sesion, reloj):
    elementos = a_reintentar(102)
    elementos[0].cfg.redes[0].bridge = "vmbr1"  # vmbr1 solo existe en pve1 del inventario falso
    _, plan = tr.armar_reintento(sesion, reloj, elementos, definicion(1), None, "pve3")
    assert plan.bloqueado
    assert any(p.severidad == Severidad.ERROR and p.indice == 0 for p in plan.problemas)


def test_ca_l21_3_un_vmid_ocupado_se_marca_en_su_indice_y_no_se_reasigna(sesion, reloj, cliente):
    cliente.vmids_ocupados = {104}
    elementos = a_reintentar(102, 104, 105)
    _, plan = tr.armar_reintento(sesion, reloj, elementos, definicion(3), None)
    errores = [p for p in plan.problemas if p.severidad == Severidad.ERROR]
    assert [(p.regla, p.indice, p.params["vmid"]) for p in errores] == [("V-03", 1, "104")]
    assert [e.vmid for e in plan.elementos] == [102, 104, 105]  # el plan no cambia solo
    assert plan.bloqueado


def test_ca_l21_3_se_reconsulta_cada_vmid_antes_de_confirmar(sesion, reloj, cliente):
    tr.armar_reintento(sesion, reloj, a_reintentar(102, 104), definicion(2), None)
    consultados = [ll[1] for ll in cliente.llamadas if ll[0] == "vmid_libre"]
    assert sorted(consultados) == [102, 104]


def test_el_reintento_valida_el_espacio_del_nodo_destino(sesion, reloj):
    elementos = []
    for i, vmid in enumerate(range(102, 112)):
        e = elemento(i, f"web-{vmid - 100:02d}", vmid, "pve1")
        e.cfg.discos[0].tamano_gib = 20  # 200 GiB en un thin de 100 GiB libres en pve3: sobre-
        elementos.append(e)  # asignado, no bloqueante (≤ 3×); con 40 GiB sí bloquearía
    _, plan = tr.armar_reintento(sesion, reloj, tuple(elementos), definicion(10), None, "pve3")
    assert any(p.regla == "V-L10" for p in plan.problemas) and plan.requiere_confirmacion_thin


def test_el_reintento_usa_la_version_forzada_si_hay(sesion, reloj):
    _, plan = tr.armar_reintento(sesion, reloj, a_reintentar(102), definicion(1), (8, 0))
    assert plan.version_validacion == (8, 0)


def test_el_reintento_relee_el_inventario(sesion, reloj, inv_cluster):
    inv, _ = tr.armar_reintento(sesion, reloj, a_reintentar(102), definicion(1), None)
    assert inv is inv_cluster


def test_una_plantilla_con_otra_cfg_no_afecta_a_los_elementos(sesion, reloj):
    elementos = a_reintentar(102)
    elementos[0].cfg.memoria_mib = 4096
    _, plan = tr.armar_reintento(
        sesion, reloj, elementos, definicion(1, plantilla=cfg_simple()), None
    )
    assert plan.elementos[0].cfg.memoria_mib == 4096  # conserva lo de cada máquina
