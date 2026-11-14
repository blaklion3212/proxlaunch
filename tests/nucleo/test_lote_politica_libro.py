"""Política de pausa (RF-L14, P-L09) y libro del lote (RF-L12, INV-L1, CA-L12.10)."""

import threading

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import LINEAS_LOG_TAREA, UMBRAL_PAUSA_ERRORES
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import EstadoMV, MotivoNoEnviada, MotivoPausa
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.lote.politica_pausa import PoliticaPausa, es_error_global

from .apoyo_lote import definicion, inventario


def _e(codigo, **params):
    return ErrorProxLaunch(codigo, {k: str(v) for k, v in params.items()})


# --- Política de pausa ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "codigo",
    [
        CodigoError.SESION_EXPIRADA,
        CodigoError.CREDENCIALES_INVALIDAS,
        CodigoError.HUELLA_CAMBIADA,
        CodigoError.ETIQUETA_RECHAZADA,
        CodigoError.LOTE_SIN_NODO_APTO,
    ],
)
def test_ca_l14_2_los_errores_globales_pausan_tras_el_primer_caso(codigo):
    assert es_error_global(_e(codigo))
    assert PoliticaPausa().registrar(_e(codigo)) == MotivoPausa.ERROR_GLOBAL


@pytest.mark.parametrize("privilegio", ["VM.Allocate", ""])
def test_ca_l14_2_permiso_insuficiente_sobre_vm_allocate_es_global(privilegio):
    error = _e(CodigoError.PERMISO_INSUFICIENTE, privilegio=privilegio)
    assert PoliticaPausa().registrar(error) == MotivoPausa.ERROR_GLOBAL


def test_ca_l14_2_permiso_insuficiente_sin_el_dato_del_privilegio_tambien_es_global():
    assert (
        PoliticaPausa().registrar(_e(CodigoError.PERMISO_INSUFICIENTE)) == MotivoPausa.ERROR_GLOBAL
    )


@pytest.mark.parametrize("privilegio", ["VM.Audit", "Datastore.AllocateSpace", "Sys.Audit"])
def test_un_permiso_de_otro_privilegio_no_es_global(privilegio):
    assert not es_error_global(_e(CodigoError.PERMISO_INSUFICIENTE, privilegio=privilegio))


@pytest.mark.parametrize(
    "codigo",
    [
        CodigoError.SIN_ESPACIO,
        CodigoError.VMID_OCUPADO,
        CodigoError.DESCONOCIDO,
        CodigoError.PARAMETRO_INVALIDO,
        CodigoError.RECURSO_INEXISTENTE,
        CodigoError.SERVIDOR_NO_RESPONDE,
        CodigoError.NODO_NO_DISPONIBLE,
    ],
)
def test_los_errores_por_maquina_no_pausan_al_primer_caso(codigo):
    assert not es_error_global(_e(codigo))
    assert PoliticaPausa().registrar(_e(codigo)) is None


def test_ca_l14_3_tres_errores_seguidos_con_la_misma_causa_pausan_en_el_tercero():
    p = PoliticaPausa()
    assert UMBRAL_PAUSA_ERRORES == 3
    assert p.registrar(_e(CodigoError.SIN_ESPACIO)) is None
    assert p.registrar(_e(CodigoError.SIN_ESPACIO)) is None
    assert p.registrar(_e(CodigoError.SIN_ESPACIO)) == MotivoPausa.REPETIDO


def test_ca_l14_3_causas_distintas_reinician_la_racha():
    p = PoliticaPausa()
    for codigo in (CodigoError.SIN_ESPACIO, CodigoError.SIN_ESPACIO, CodigoError.DESCONOCIDO):
        assert p.registrar(_e(codigo)) is None
    assert p.registrar(_e(CodigoError.DESCONOCIDO)) is None
    assert p.registrar(_e(CodigoError.DESCONOCIDO)) == MotivoPausa.REPETIDO


def test_ca_l14_3_un_exito_en_medio_reinicia_la_racha():
    p = PoliticaPausa()
    p.registrar(_e(CodigoError.SIN_ESPACIO))
    p.registrar(_e(CodigoError.SIN_ESPACIO))
    assert p.registrar(None) is None
    assert p.registrar(_e(CodigoError.SIN_ESPACIO)) is None
    assert p.registrar(_e(CodigoError.SIN_ESPACIO)) is None
    assert p.registrar(_e(CodigoError.SIN_ESPACIO)) == MotivoPausa.REPETIDO


def test_ca_l14_3_tras_pausar_la_cuenta_vuelve_a_empezar():
    p = PoliticaPausa()
    motivos = [p.registrar(_e(CodigoError.SIN_ESPACIO)) for _ in range(6)]
    assert motivos == [None, None, MotivoPausa.REPETIDO, None, None, MotivoPausa.REPETIDO]


@pytest.mark.parametrize("umbral", [1, 2, 5])
def test_el_umbral_es_configurable(umbral):
    p = PoliticaPausa(umbral)
    resultados = [p.registrar(_e(CodigoError.SIN_ESPACIO)) for _ in range(umbral)]
    assert resultados[:-1] == [None] * (umbral - 1)
    assert resultados[-1] == MotivoPausa.REPETIDO


def test_ca_l14_4_continuar_no_vuelve_a_preguntar_por_esa_causa():
    p = PoliticaPausa()
    p.ignorar(CodigoError.SIN_ESPACIO)
    assert all(p.registrar(_e(CodigoError.SIN_ESPACIO)) is None for _ in range(10))


def test_ca_l14_4_ignorar_una_causa_no_silencia_las_demas():
    p = PoliticaPausa()
    p.ignorar(CodigoError.SIN_ESPACIO)
    assert p.registrar(_e(CodigoError.SESION_EXPIRADA)) == MotivoPausa.ERROR_GLOBAL


def test_ca_l14_4_ignorar_una_causa_global_tambien_la_silencia():
    p = PoliticaPausa()
    p.ignorar(CodigoError.ETIQUETA_RECHAZADA)  # "continuar sin etiquetas"
    assert p.registrar(_e(CodigoError.ETIQUETA_RECHAZADA)) is None


def test_la_politica_es_segura_entre_hilos():
    p = PoliticaPausa(umbral=10**9)  # nunca pausa: solo se prueba que no se rompe
    errores = []

    def _trabajar():
        try:
            for i in range(500):
                p.registrar(_e(CodigoError.SIN_ESPACIO) if i % 3 else None)
        except Exception as exc:  # pragma: no cover
            errores.append(exc)

    hilos = [threading.Thread(target=_trabajar) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []


# --- Libro ----------------------------------------------------------------------------------------


def _libro(cantidad=3):
    inv = inventario()
    plan = construir_plan(
        definicion(cantidad),
        inv,
        list(range(100, 100 + cantidad)),
        [],
        id_lote="abcd1234",
        ahora=0.0,
        version_validacion=(9, 2),
        vms_visibles=None,
    )
    return Libro(plan)


def test_el_libro_nace_con_una_entrada_pendiente_por_elemento_en_el_orden_del_plan():
    libro = _libro(4)
    ent = libro.instantanea()
    assert [e.elemento.vmid for e in ent] == [100, 101, 102, 103]
    assert all(e.estado == EstadoMV.PENDIENTE and not e.post_intentado for e in ent)
    assert libro.contadores() == {EstadoMV.PENDIENTE: 4}
    assert not libro.terminado()  # pendiente cuenta como en curso


def test_inv_l1_marcar_el_post_dos_veces_para_el_mismo_vmid_lanza_assertionerror():
    libro = _libro()
    libro.marcar_post_intentado(100, 1.0)
    with pytest.raises(AssertionError):
        libro.marcar_post_intentado(100, 2.0)


def test_inv_l1_una_maquina_con_post_intentado_no_se_puede_marcar_no_enviada():
    libro = _libro()
    libro.marcar_post_intentado(100, 1.0)
    with pytest.raises(AssertionError):
        libro.marcar_no_enviada(100, MotivoNoEnviada.CANCELADO)


def test_ca_l17_3_pendientes_excluye_las_ya_intentadas():
    libro = _libro(3)
    libro.iniciar(100, 0.0)
    libro.marcar_post_intentado(100, 0.0)
    libro.finalizar(100, EstadoMV.CONEXION_PERDIDA)
    libro.marcar_no_enviada(102, MotivoNoEnviada.PAUSA)
    assert [e.elemento.vmid for e in libro.pendientes()] == [101]


def test_un_estado_final_no_se_pisa_con_finalizar():
    libro = _libro()
    libro.iniciar(100, 0.0)
    libro.finalizar(100, EstadoMV.OK, t_fin=5.0)
    libro.finalizar(100, EstadoMV.ERROR, t_fin=9.0)
    e = libro.entrada(100)
    assert (e.estado, e.t_fin) == (EstadoMV.OK, 5.0)


def test_finalizar_exige_un_estado_final():
    libro = _libro()
    with pytest.raises(AssertionError):
        libro.finalizar(100, EstadoMV.CREANDO)


def test_resolver_sobre_una_maquina_que_nunca_se_intento_no_esta_permitido():
    libro = _libro()
    with pytest.raises(AssertionError):
        libro.resolver(100, EstadoMV.OK)


def test_resolver_conserva_el_upid_y_reemplaza_el_estado_dudoso():
    libro = _libro()
    libro.iniciar(100, 0.0)
    libro.marcar_post_intentado(100, 0.0)
    libro.registrar_upid(100, "UPID:pve1:1:2:3:qmcreate:100:u@pam:")
    libro.finalizar(100, EstadoMV.CONEXION_PERDIDA)
    libro.resolver(100, EstadoMV.OK, t_fin=7.0)
    e = libro.entrada(100)
    assert e.estado == EstadoMV.OK
    assert e.upid == "UPID:pve1:1:2:3:qmcreate:100:u@pam:"
    assert e.error is None


def test_actualizar_estado_solo_mueve_entre_estados_en_curso():
    libro = _libro()
    libro.iniciar(100, 0.0)
    libro.actualizar_estado(100, EstadoMV.ENVIANDO)
    assert libro.entrada(100).estado == EstadoMV.ENVIANDO
    libro.finalizar(100, EstadoMV.OK)
    libro.actualizar_estado(100, EstadoMV.CREANDO)
    assert libro.entrada(100).estado == EstadoMV.OK


def test_marcar_no_enviada_sobre_una_entrada_ya_final_no_la_cambia():
    libro = _libro()
    libro.iniciar(100, 0.0)
    libro.finalizar(100, EstadoMV.ERROR)
    libro.marcar_no_enviada(100, MotivoNoEnviada.CANCELADO)
    assert libro.entrada(100).estado == EstadoMV.ERROR


def test_no_enviada_guarda_el_motivo():
    libro = _libro()
    libro.marcar_no_enviada(101, MotivoNoEnviada.NODO_CAIDO, 3.0)
    e = libro.entrada(101)
    assert (e.estado, e.motivo_no_enviada, e.t_fin) == (
        EstadoMV.NO_ENVIADA,
        MotivoNoEnviada.NODO_CAIDO,
        3.0,
    )


def test_rnf_l05_el_log_de_la_tarea_se_acota():
    libro = _libro()
    libro.registrar_log(100, [f"linea {i}" for i in range(500)])
    log = libro.entrada(100).log_tarea
    assert len(log) == LINEAS_LOG_TAREA
    assert log[-1] == "linea 499"


def test_las_instantaneas_son_inmutables_y_no_cambian_con_el_libro():
    libro = _libro()
    antes = libro.instantanea()
    libro.iniciar(100, 0.0)
    assert antes[0].estado == EstadoMV.PENDIENTE
    with pytest.raises(AttributeError):
        antes[0].estado = EstadoMV.OK  # type: ignore[misc]


def test_el_libro_es_seguro_entre_hilos():
    libro = _libro(50)
    plan_vmids = [e.elemento.vmid for e in libro.instantanea()]

    def _trabajar(vmid):
        libro.iniciar(vmid, 0.0)
        libro.marcar_post_intentado(vmid, 0.0)
        libro.registrar_upid(vmid, f"UPID:pve1:1:2:3:qmcreate:{vmid}:u@pam:")
        libro.finalizar(vmid, EstadoMV.OK, t_fin=1.0)

    hilos = [threading.Thread(target=_trabajar, args=(v,)) for v in plan_vmids]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert libro.terminado()
    assert libro.contadores() == {EstadoMV.OK: 50}
    assert all(e.post_intentado and e.upid for e in libro.instantanea())
