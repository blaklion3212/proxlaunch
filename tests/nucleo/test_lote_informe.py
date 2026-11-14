"""Informe estructurado del lote (RF-L19, CA-L19.1, CA-L19.3, CA-L19.7, CA-L12.10, RNF-L09)."""

import time

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import LINEAS_LOG_TAREA
from proxlaunch.nucleo.lote.informe import construir_informe
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import (
    EstadoMV,
    EstadoRollback,
    MetadatosInforme,
    MotivoNoEnviada,
    ResultadoRollback,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback

from .apoyo_lote import (
    HOST,
    NORMAL,
    USUARIO,
    ControlAutomatico,
    crear_banco,
    definicion,
    envio_incierto,
    upid_de,
    volcar,
)

METADATOS = MetadatosInforme(
    nombre_perfil="laboratorio",
    version_proxmox="9.2.1",
    es_cluster=True,
    nombre_cluster="lab",
    fecha_hora_local="2026-11-13T10:00:00",
)


def _informe(banco, libro, **kw):
    return construir_informe(libro.plan, libro, METADATOS, reloj=banco.reloj, **kw)


def _lote_mixto(banco):
    """5 MVs: ok, error por espacio, incierta (596 sin existir), ok y no enviada."""
    plan = banco.planificar(definicion(5, vmid_inicial=100))
    banco.cluster.exitstatus[101] = "Volume group has insufficient free space"

    def _post_incierto(llamada):
        if int(llamada.datos["vmid"]) == 102:
            raise envio_incierto()
        return NORMAL

    banco.cluster.regla("POST", r"/qemu$", _post_incierto)
    banco.cluster.regla("GET", r"qemu/102/config$", ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE))
    control = ControlAutomatico("cancelar")
    banco.cluster.al_post = lambda vmid: control.cancelar() if vmid == 103 else None
    return banco.ejecutar(plan, control)


def test_ca_l19_1_el_informe_resume_pedidas_y_contadores_por_estado(banco):
    libro = _lote_mixto(banco)
    inf = _informe(banco, libro)
    assert inf.pedidas == 5
    assert set(inf.contadores) == {e.value for e in EstadoMV}  # todas las claves, también las en 0
    assert sum(inf.contadores.values()) == 5
    assert inf.contadores["ok"] == 2
    assert inf.contadores["error"] == 1
    assert inf.contadores["conexion_perdida"] == 1
    assert inf.contadores["no_enviada"] == 1


def test_ca_l19_1_las_entradas_van_en_el_orden_del_plan_con_vmid_nodo_y_error(banco):
    libro = _lote_mixto(banco)
    inf = _informe(banco, libro)
    assert [e.elemento.vmid for e in inf.entradas] == [100, 101, 102, 103, 104]
    assert inf.entradas[1].error.codigo == CodigoError.SIN_ESPACIO
    assert inf.entradas[0].upid and inf.entradas[1].upid
    assert inf.id_lote == libro.id_lote
    assert inf.plantilla == libro.plan.definicion.plantilla


def test_ca_l19_1_la_duracion_es_t_fin_menos_t_inicio_de_cada_maquina(banco):
    plan = banco.planificar(definicion(2, vmid_inicial=100))
    libro = Libro(plan)
    libro.iniciar(100, 10.0)
    libro.marcar_post_intentado(100, 10.0)
    libro.finalizar(100, EstadoMV.OK, t_fin=17.5)
    inf = _informe(banco, libro)
    assert inf.duraciones_s == {100: 7.5}  # la no iniciada no tiene duración


def test_un_informe_parcial_mide_las_que_siguen_en_curso_hasta_ahora(banco):
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    libro = Libro(plan)
    libro.iniciar(100, 10.0)
    banco.reloj.avanzar(25)
    assert _informe(banco, libro).duraciones_s == {100: 15.0}  # 25 - 10


def test_ca_l19_1_el_informe_incluye_la_seccion_deshacer_si_hubo(banco):
    plan = banco.planificar(definicion(2, vmid_inicial=100))
    libro = banco.ejecutar(plan)
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    resultados = servicio.deshacer(
        servicio.elegibles(libro, etiquetado=True),
        lambda r: None,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
    )
    inf = _informe(banco, libro, rollback=resultados)
    assert [r.estado for r in inf.rollback] == [EstadoRollback.ELIMINADA] * 2
    assert _informe(banco, libro).rollback == ()


def test_ca_l11_8_el_informe_de_una_simulacion_se_marca_como_tal(banco):
    from dataclasses import replace

    plan = replace(banco.planificar(definicion(2, vmid_inicial=100)), es_simulacion=True)
    inf = construir_informe(plan, Libro(plan), METADATOS, reloj=banco.reloj)
    assert inf.es_simulacion is True
    assert inf.contadores["pendiente"] == 2


def test_rnf_l05_el_log_de_la_tarea_solo_se_conserva_en_maquinas_con_avisos_o_error(banco):
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    libro = Libro(plan)
    largo = [f"linea {i}" for i in range(300)]
    for vmid, estado in ((100, EstadoMV.OK), (101, EstadoMV.CON_AVISOS), (102, EstadoMV.ERROR)):
        libro.iniciar(vmid, 0.0)
        libro.marcar_post_intentado(vmid, 0.0)
        libro.registrar_log(vmid, largo)
        libro.finalizar(vmid, estado, t_fin=1.0)
    inf = _informe(banco, libro)
    assert inf.entradas[0].log_tarea == ()
    assert len(inf.entradas[1].log_tarea) == len(inf.entradas[2].log_tarea) == LINEAS_LOG_TAREA
    assert inf.entradas[2].log_tarea[-1] == "linea 299"


def test_ca_l12_10_el_informe_sale_solo_del_libro_no_de_otra_fuente(banco):
    libro = _lote_mixto(banco)
    antes = libro.instantanea()
    inf = _informe(banco, libro)
    assert libro.instantanea() == antes  # construir el informe no modifica el libro
    assert [(e.elemento.vmid, e.estado, e.upid) for e in inf.entradas] == [
        (e.elemento.vmid, e.estado, e.upid) for e in antes
    ]


def test_rnf_l09_el_mismo_libro_da_el_mismo_informe(banco):
    libro = _lote_mixto(banco)
    assert _informe(banco, libro) == _informe(banco, libro)


def test_ca_l19_3_los_metadatos_solo_llevan_el_nombre_del_perfil_sin_host_ip_ni_usuario(banco):
    texto = volcar(METADATOS)
    assert "laboratorio" in texto
    for prohibido in (HOST, USUARIO, "root@pam", "10.0.0."):
        assert prohibido not in texto


def test_ca_l19_3_el_informe_no_contiene_host_ip_ni_usuario_ni_dentro_del_upid(banco):
    """RF-L19/CA-L19.3: el informe se puede compartir; ni el host, ni la IP, ni el usuario.

    La interfaz ya oculta el usuario del UPID al dar formato al texto; este caso exige además
    que los DATOS del informe del núcleo (UPID y parámetros del error incluidos) no los lleven.
    """
    libro = _lote_mixto(banco)
    texto = volcar(_informe(banco, libro))
    assert upid_de("pve1", 100) not in texto  # el UPID completo lleva el usuario
    for prohibido in (HOST, USUARIO, "root@pam"):
        assert prohibido not in texto, prohibido


def test_ca_l19_3_ni_la_ip_en_los_parametros_de_un_error_de_red(banco):
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    banco.cluster.regla("POST", r"/qemu$", envio_incierto())
    banco.cluster.regla(
        "GET",
        r"qemu/100/config$",
        ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": HOST}),
    )
    libro = banco.ejecutar(plan)
    texto = volcar(_informe(banco, libro))
    assert HOST not in texto


def test_ca_l19_7_el_informe_de_100_maquinas_se_genera_en_menos_de_1_s():
    banco = crear_banco(("pve1", "pve2", "pve3", "pve4"))
    plan = banco.planificar(definicion(100, vmid_inicial=1000))
    libro = banco.ejecutar(plan)
    inicio = time.perf_counter()
    inf = construir_informe(plan, libro, METADATOS, reloj=banco.reloj)
    assert time.perf_counter() - inicio < 1.0
    assert inf.pedidas == 100 and inf.contadores["ok"] == 100


def test_ca_l19_7_100_maquinas_con_error_y_log_largo_tambien_son_rapidas(banco):
    plan = banco.planificar(definicion(100, vmid_inicial=1000))
    libro = Libro(plan)
    for e in plan.elementos:
        libro.iniciar(e.vmid, 0.0)
        libro.marcar_post_intentado(e.vmid, 0.0)
        libro.registrar_log(e.vmid, [f"linea {i}" for i in range(500)])
        libro.finalizar(
            e.vmid, EstadoMV.ERROR, t_fin=2.0, error=ErrorProxLaunch(CodigoError.SIN_ESPACIO)
        )
    inicio = time.perf_counter()
    inf = construir_informe(plan, libro, METADATOS, reloj=banco.reloj)
    assert time.perf_counter() - inicio < 1.0
    assert all(len(e.log_tarea) == LINEAS_LOG_TAREA for e in inf.entradas)


def test_el_informe_cuenta_no_enviadas_con_su_motivo(banco):
    plan = banco.planificar(definicion(3, vmid_inicial=100))
    libro = Libro(plan)
    libro.marcar_no_enviada(100, MotivoNoEnviada.PAUSA)
    libro.marcar_no_enviada(101, MotivoNoEnviada.NODO_CAIDO)
    inf = _informe(banco, libro)
    assert inf.contadores["no_enviada"] == 2
    assert [e.motivo_no_enviada for e in inf.entradas[:2]] == [
        MotivoNoEnviada.PAUSA,
        MotivoNoEnviada.NODO_CAIDO,
    ]


def test_el_informe_incluye_los_problemas_del_plan(banco):
    plan = banco.planificar(definicion(2, vmid_inicial=100))
    libro = Libro(plan)
    assert _informe(banco, libro).problemas_plan == plan.problemas


def test_resultado_de_rollback_en_el_informe_conserva_el_orden_recibido(banco):
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    libro = Libro(plan)
    r = (
        ResultadoRollback(100, "pve1", "web-01", EstadoRollback.ELIMINADA),
        ResultadoRollback(101, "pve1", "web-02", EstadoRollback.FALLO),
    )
    assert _informe(banco, libro, rollback=r).rollback == r


@pytest.mark.parametrize("n", [1, 7])
def test_el_informe_acepta_lotes_pequenos(banco, n):
    plan = banco.planificar(definicion(n, vmid_inicial=100))
    libro = banco.ejecutar(plan)
    assert _informe(banco, libro).pedidas == n
