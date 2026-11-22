"""Deshacer un lote con cloud-init y espera de IP (fase B, 0.7.0).

Requisitos: RF-B7.2 (CA-B7.2.1 a CA-B7.2.5), CA-B3.5.4 (el sondeo se cancela antes del
``DELETE``), CA-B7.2.3, CA-B0.2.1 (instantánea de Deshacer de 2 MVs de 0.6.0) y RD-B4. El
``rollback.py`` no cambia en la fase B: el ``DELETE`` de una MV con cloud-init es el de siempre
(``destroy-unreferenced-disks=0`` en la consulta, sin ``purge``) y no se intenta borrar snippets
ni archivos de imagen. El orden «cancelar el sondeo → inspección → deshacer» lo cablea la interfaz
(``tests/interfaz``); aquí se prueba su contrato en el núcleo.
"""

from __future__ import annotations

import json
import re
import threading

from proxlaunch.nucleo.agente.espera import EsperaIp
from proxlaunch.nucleo.agente.modelos import EstadoIp
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.informe import construir_informe
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import EstadoMV, EstadoRollback, MetadatosInforme
from proxlaunch.nucleo.lote.motor import ControlLote, enlazar_espera
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.secreto import Secreto

from . import apoyo_golden_fase_b as g
from .apoyo_fase_b_p1 import (
    CENTINELA,
    CLAVE,
    MundoB,
    ci,
    ci_completa,
    config_plantilla,
    fallar_put,
)
from .apoyo_lote import Http, error_http, respuesta_agente, volcar

DATOS_DE_CLOUDINIT = (
    "deploy",
    CLAVE.split()[1],
    "lab.local",
    "10.0.0.50",
    "agente.yaml",
    CENTINELA,
)


def _servicio(m):
    return ServicioRollback(m.sesion, m.reloj)


def _deshacer(m, libro, *, vmids=None):
    """Deshace las MVs del libro (confirmando apagar y desproteger, como el diálogo)."""
    servicio = _servicio(m)
    candidatos = servicio.elegibles(libro, etiquetado=True)
    if vmids is not None:
        candidatos = [c for c in candidatos if c.entrada.elemento.vmid in vmids]
    todas = frozenset(c.entrada.elemento.vmid for c in candidatos)
    res = servicio.deshacer(
        candidatos,
        lambda _r: None,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
        forzar_apagado=todas,
        forzar_desproteccion=todas,
        permisos=None,
    )
    return {r.vmid: r for r in res}


def _traza_delete(cl):
    """Peticiones de Deshacer como ``(método, ruta?consulta, cuerpo)``, agrupadas por MV."""
    filas = []
    for metodo, ruta, consulta, cuerpo in cl.trazas:
        mv = re.search(r"/qemu/(\d+)", ruta)
        filas.append((int(mv.group(1)) if mv else 0, metodo,
                      ruta + (f"?{consulta}" if consulta else ""),
                      cuerpo.decode("ascii")))  # fmt: skip
    return [f[1:] for f in sorted(filas, key=lambda f: f[0])]  # orden estable por MV


# --- CA-B0.2.1: instantánea de Deshacer -----------------------------------------------------------


def test_ca_b0_2_1_deshacer_2_mvs_es_identico_al_de_0_6_0():
    esperado = g.golden()["escenarios"]["deshacer_2"]
    assert json.loads(json.dumps(g.actuales()["deshacer_2"])) == esperado
    metodos = [m for m, _, _ in esperado]
    assert metodos.count("DELETE") == 2 and "PUT" not in metodos


# --- CA-B7.2.1: el DELETE es idéntico al de un lote sin cloud-init --------------------------------


def test_ca_b7_2_1_el_delete_de_un_lote_con_cloudinit_es_identico_al_de_uno_sin_el(rsps):
    """Mismas peticiones, en el mismo orden y con la misma consulta que sin cloud-init: no hay
    parámetros nuevos, ni ``purge``, ni peticiones sobre snippets o imágenes."""
    con = MundoB(rsps=rsps)
    _, libro_con = con.lote(2, ci_completa(Secreto(CENTINELA), serie=True))
    con.cl.trazas.clear()
    _deshacer(con, libro_con)
    solo_con = _traza_delete(con.cl)
    assert [m for m, _, _ in solo_con if m != "GET"] == ["DELETE", "DELETE"]
    assert all("purge" not in ruta for _, ruta, _ in solo_con)
    assert all("snippets" not in ruta and "import" not in ruta for _, ruta, _ in solo_con)
    deletes = [ruta for m, ruta, _ in solo_con if m == "DELETE"]
    assert deletes == [f"/nodes/pve1/qemu/{v}?destroy-unreferenced-disks=0" for v in (100, 101)]
    assert con.cl.params_delete == {100: {"destroy-unreferenced-disks": "0"},
                                    101: {"destroy-unreferenced-disks": "0"}}  # fmt: skip


def test_ca_b7_2_1_la_secuencia_de_deshacer_no_cambia_con_cloudinit(rsps_dos=None):
    """Compara dos mundos (sin y con cloud-init) petición a petición."""
    import responses

    secuencias = []
    for cloudinit in (None, ci_completa(Secreto(CENTINELA), serie=True)):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            m = MundoB(rsps=rsps)
            _, libro = m.lote(3, cloudinit, etiquetas=())
            m.cl.trazas.clear()
            _deshacer(m, libro)
            secuencias.append(_traza_delete(m.cl))
    assert secuencias[0] == secuencias[1] and secuencias[0]


def test_ca_b7_2_1_las_mvs_encendidas_se_apagan_y_borran_como_siempre():
    m = MundoB()
    _, libro = m.lote(2, ci(), encender=True)
    res = _deshacer(m, libro)
    assert {r.estado for r in res.values()} == {EstadoRollback.ELIMINADA}
    for v in (100, 101):
        assert m.escrituras(v)[-2:] == ["stop", "delete"]


def test_ca_b7_2_1_deshacer_nunca_llama_a_rutas_de_cloudinit_ni_de_plantilla():
    m = MundoB()
    _, libro = m.lote(2, ci_completa(Secreto(CENTINELA), serie=True))
    m.cl.reiniciar_llamadas()
    _deshacer(m, libro)
    assert all("cloudinit" not in c.ruta and "/template" not in c.ruta for c in m.cl.llamadas)
    assert m.cl.total("PUT") == 0 and m.cl.total("POST") == 0
    assert m.cl.llamadas_agente == []


# --- CA-B7.2.2: una MV PARCIAL por fallo de cloud-init es una MV propia ---------------------------


def test_ca_b7_2_2_una_mv_parcial_por_cloudinit_se_deshace_como_cualquier_mv_propia(rsps):
    m = MundoB(rsps=rsps)
    fallar_put(
        m.cl,
        "ciuser",
        Http(403, "Permission check failed (/vms/101, VM.Config.Cloudinit)"),
        vmid=101,
    )
    _, libro = m.lote(3, ci(), encender=True)
    assert m.estados(libro)[101] == EstadoMV.PARCIAL
    servicio = _servicio(m)
    candidatos = {c.entrada.elemento.vmid: c for c in servicio.elegibles(libro, etiquetado=True)}
    assert candidatos[101].elegible and candidatos[101].incompleta  # «Solo incompletas» la incluye
    res = _deshacer(m, libro)
    assert res[101].estado == EstadoRollback.ELIMINADA
    assert m.escrituras(101) == ["clone", "ajustes", "ci", "delete"]  # nunca se encendió
    assert 101 not in m.cl.vms


def test_ca_b7_2_2_una_mv_parcial_por_la_contrasena_tambien_se_deshace(rsps):
    m = MundoB(rsps=rsps)
    fallar_put(m.cl, "cipassword", Http(500, "fallo de prueba"), vmid=100)
    _, libro = m.lote(2, ci(contrasena=Secreto(CENTINELA)))
    assert m.estados(libro)[100] == EstadoMV.PARCIAL
    res = _deshacer(m, libro, vmids={100})
    assert res[100].estado == EstadoRollback.ELIMINADA and 100 not in m.cl.vms and 101 in m.cl.vms


def test_ca_b7_2_2_solo_se_toca_lo_que_esta_en_el_libro_una_mv_ajena_no_se_borra():
    m = MundoB()
    m.cl.agregar_vm(555, "pve1", "ajena", tags="otra")
    _, libro = m.lote(2, ci())
    _deshacer(m, libro)
    assert 555 in m.cl.vms and m.cl.deletes[555] == 0


# --- CA-B3.5.4 / CA-B7.2.3: Deshacer cancela primero el sondeo de IP ------------------------------


class _SondeoBloqueado:
    """Guion del agente: la primera petición avisa y espera (el sondeo «en vuelo»); luego, el
    agente aún no responde. Así la MV está ``esperando`` de forma determinista, sin ``sleep``."""

    def __init__(self) -> None:
        self.en_vuelo = threading.Event()
        self.liberar = threading.Event()

    def __call__(self, _ll):
        self.en_vuelo.set()
        self.liberar.wait(timeout=10)
        raise error_http(500, "QEMU guest agent is not running")


def _mundo_agente():
    """Plantilla con el agente invitado activado (si no, la espera termina en ``sin_agente``)."""
    return MundoB(plantillas={9000: ("base", config_plantilla(agente="1"))})


def _lote_con_espera(m, n=2, cloudinit=None):
    """Ejecuta un lote con IP esperada; devuelve ``(plan, libro, espera, hilo)`` con el hilo de la
    espera arrancado y bloqueado en el primer sondeo."""
    bloqueo = _SondeoBloqueado()
    for v in range(100, 100 + n):
        m.cl.guion_agente(v, bloqueo)
    plan = m.planificar(m.definicion(n, cloudinit, encender=True, esperar_ip=True))
    assert not plan.bloqueado, plan.problemas
    libro = Libro(plan)
    espera = EsperaIp(m.sesion, m.reloj, enlazar_espera(libro, m.banco.observador))
    hilo = threading.Thread(target=espera.ejecutar, daemon=True)
    hilo.start()
    m.ejecutar(plan, libro=libro, espera_ip=espera)
    assert bloqueo.en_vuelo.wait(timeout=10), "el sondeo no llegó a empezar"
    return plan, libro, espera, hilo, bloqueo


def test_ca_b3_5_4_el_sondeo_se_cancela_antes_del_delete_y_no_hay_peticiones_de_agente_despues():
    m = _mundo_agente()
    plan, libro, espera, hilo, bloqueo = _lote_con_espera(m)
    vmids = [e.vmid for e in plan.elementos]
    assert espera.estado(vmids[0]) == EstadoIp.ESPERANDO
    # El orden que cablea la interfaz: cancelar el sondeo (síncrono) y solo entonces deshacer.
    espera.cancelar(vmids)
    antes = list(m.cl.llamadas_agente)
    assert {espera.estado(v) for v in vmids} == {EstadoIp.CANCELADA}
    bloqueo.liberar.set()  # la petición que iba en vuelo vuelve y se descarta
    hilo.join(timeout=10)
    assert not hilo.is_alive()
    res = _deshacer(m, libro)
    assert {r.estado for r in res.values()} == {EstadoRollback.ELIMINADA}
    assert m.cl.llamadas_agente == antes  # ni un sondeo más, durante ni después del DELETE
    primer_delete = next(i for i, c in enumerate(m.cl.llamadas) if c.metodo == "DELETE")
    assert not [c for c in m.cl.llamadas[primer_delete:] if "/agent/" in c.ruta]


def test_ca_b7_2_3_el_resultado_de_ip_queda_cancelado_sin_aviso_de_ip_no_obtenida():
    m = _mundo_agente()
    plan, libro, espera, hilo, bloqueo = _lote_con_espera(m)
    vmids = [e.vmid for e in plan.elementos]
    espera.cancelar(vmids)
    bloqueo.liberar.set()
    hilo.join(timeout=10)
    for v in vmids:
        entrada = libro.entrada(v)
        assert entrada.ip is not None and entrada.ip.estado == EstadoIp.CANCELADA
        assert "ip_no_obtenida" not in entrada.avisos
        assert entrada.estado in (EstadoMV.OK, EstadoMV.CON_AVISOS)  # la MV conserva su estado


def test_ca_b7_2_3_cancelar_solo_las_mvs_que_se_deshacen_deja_seguir_a_las_demas():
    m = _mundo_agente()
    plan, libro, espera, hilo, bloqueo = _lote_con_espera(m, 3)
    a, b, c = (e.vmid for e in plan.elementos)
    espera.cancelar([a])
    assert espera.estado(a) == EstadoIp.CANCELADA
    assert espera.estado(b) != EstadoIp.CANCELADA and espera.estado(c) != EstadoIp.CANCELADA
    bloqueo.liberar.set()
    # las otras siguen sondeando hasta que se agota su plazo o se cancelan
    espera.cancelar(None)
    hilo.join(timeout=10)
    assert not hilo.is_alive()


def test_deshacer_con_la_espera_ya_resuelta_no_hace_falta_cancelar_nada():
    """Una MV con la IP ya obtenida se deshace igual; el resultado de IP queda en el libro."""
    m = _mundo_agente()
    for v in (100, 101):
        m.cl.guion_agente(v, respuesta_agente(("eth0", "AA:BB:CC:DD:EE:FF", ("10.0.0.5",))))
    plan = m.planificar(m.definicion(2, None, encender=True, esperar_ip=True))
    libro = Libro(plan)
    espera = EsperaIp(m.sesion, m.reloj, enlazar_espera(libro, m.banco.observador))
    hilo = threading.Thread(target=espera.ejecutar, daemon=True)
    hilo.start()
    m.ejecutar(plan, libro=libro, espera_ip=espera)
    hilo.join(timeout=10)
    assert {libro.entrada(v).ip.estado for v in (100, 101)} == {EstadoIp.OBTENIDA}
    res = _deshacer(m, libro)
    assert {r.estado for r in res.values()} == {EstadoRollback.ELIMINADA}


# --- CA-B7.2.4: el informe de Deshacer no lleva datos de cloud-init -------------------------------


def _informe(m, plan, libro, rollback):
    meta = MetadatosInforme("lab", "9.2.1", False, None, "2026-11-22T10:00:00+00:00")
    return construir_informe(plan, libro, meta, rollback=list(rollback), reloj=m.reloj)


def test_ca_b7_2_4_el_informe_con_deshacer_no_contiene_usuario_claves_ni_contrasena():
    m = MundoB()
    plan, libro = m.lote(2, ci_completa(Secreto(CENTINELA), serie=True), encender=True)
    res = _deshacer(m, libro)
    informe = _informe(m, plan, libro, res.values())
    assert len(informe.rollback) == 2
    texto = volcar(informe) + repr(informe)
    for valor in DATOS_DE_CLOUDINIT:
        assert valor not in texto, valor
    for entrada in informe.entradas:
        assert entrada.elemento.cfg.cloudinit is None


def test_ca_b7_2_4_los_errores_de_deshacer_tampoco_arrastran_datos_de_cloudinit():
    """Un fallo del DELETE cuyo texto repite la configuración sale sin la contraseña."""
    m = MundoB()
    plan, libro = m.lote(2, ci_completa(Secreto(CENTINELA), serie=True))
    m.cl.regla(
        "DELETE",
        r"/qemu/100$",
        error_http(500, f"no se pudo borrar: cipassword={CENTINELA}"),
        veces=1,
    )
    res = _deshacer(m, libro)
    informe = _informe(m, plan, libro, res.values())
    texto = volcar(informe) + repr(informe) + volcar(res)
    assert CENTINELA not in texto
    assert res[100].estado == EstadoRollback.FALLO


# --- CA-B7.2.5: el libro y sus salidas ------------------------------------------------------------


def test_ca_b7_2_5_las_salidas_del_libro_no_llevan_valores_de_cloudinit():
    """Lo que SALE del libro (informe, exportaciones) no lleva cloud-init (arquitectura §0)."""
    from proxlaunch.nucleo.agente.exportacion import filas_ips, lista_ips_texto

    m = MundoB()
    plan, libro = m.lote(
        2, ci_completa(Secreto(CENTINELA), serie=True), encender=True, esperar_ip=True
    )
    informe = _informe(m, plan, libro, ())
    exportado = repr(filas_ips(libro.instantanea())) + lista_ips_texto(libro.instantanea())
    for valor in DATOS_DE_CLOUDINIT:
        assert valor not in volcar(informe) + exportado, valor


def test_ca_b7_2_5_el_repr_de_una_entrada_del_libro_no_lleva_valores_de_cloudinit():
    m = MundoB()
    _, libro = m.lote(2, ci_completa(Secreto(CENTINELA), serie=True))
    texto = repr(libro.instantanea())
    for valor in DATOS_DE_CLOUDINIT:
        assert valor not in texto, valor


def test_ca_b7_2_5_el_libro_conserva_la_configuracion_en_memoria_solo_para_reintentar_ajustes():
    """Desviación aceptada (§0): en memoria sí, porque «Reintentar ajustes» la necesita."""
    m = MundoB()
    _, libro = m.lote(2, ci_completa(Secreto(CENTINELA), serie=True))
    assert all(e.elemento.cfg.cloudinit is not None for e in libro.instantanea())


def test_ca_b7_2_5_la_contrasena_nunca_esta_en_el_repr_del_libro():
    m = MundoB()
    _, libro = m.lote(2, ci(contrasena=Secreto(CENTINELA)))
    assert CENTINELA not in repr(libro.instantanea()) and CENTINELA not in volcar(
        libro.instantanea()
    )


def test_deshacer_un_error_de_codigo_conocido_no_se_confunde_con_los_de_la_fase_b():
    """Sanidad: un DELETE sobre una MV ya borrada es ``YA_NO_EXISTIA`` como en 0.6.0."""
    m = MundoB()
    _, libro = m.lote(2, ci())
    del m.cl.vms[100]
    res = _deshacer(m, libro)
    assert res[100].estado in (EstadoRollback.YA_NO_EXISTIA, EstadoRollback.OMITIDA)
    assert res[101].estado == EstadoRollback.ELIMINADA
    assert CodigoError.ROLLBACK_FALLO not in {r.error.codigo for r in res.values() if r.error}
