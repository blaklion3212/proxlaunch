"""Creación con las opciones de la fase A: encender al final, ajustes de clon, avisos y lotes.

Requisitos: RF-A1.1 (CA-A1.1.1..A1.1.7), CA-A1.2.3, CA-A6.1.4, CA-A6.1.5, CA-A1.2.1, CL-A2, CL-A13,
P-6 (el fallo de encendido es un aviso y no dispara rollback ni pausa). Dobles: ``ClusterA``.
"""

from __future__ import annotations

import dataclasses
import threading

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.modelos.origen import AjustesClon
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_api import crear_sesion
from .apoyo_fase_a import (
    ROL_BASE,
    ClusterA,
    banco_a,
    catalogo,
    cfg_vm,
    def_filas,
    def_lote,
    fila_a,
    inv_con,
    permisos,
    plan_de,
)
from .apoyo_lote import ControlAutomatico, RelojSeguro, TransporteCluster
from .apoyo_mvp4 import cfg_clon, detalle_plantilla, inv_origen, plantilla_pve

INICIO = "/status/start"


class Mundo:
    """Un clúster ``ClusterA`` con una plantilla (9000) y el servicio de creación real."""

    def __init__(self, *, perm=True, **plantilla):
        self.cl = ClusterA(("pve1",))
        self.cl.agregar_plantilla(9000, "base", "pve1", **plantilla)
        self.reloj = RelojSeguro()
        self.sesion = crear_sesion(TransporteCluster(self.cl), reloj=self.reloj)  # type: ignore[arg-type]
        det = detalle_de_config(self.cl.plantillas[9000]["config"])
        self.inv = inv_origen(
            plantillas=(plantilla_pve(9000, "base", "pve1", detalle=det),),
            permisos_efectivos=True if perm is True else perm,
        )
        if perm is True:
            previo = self.inv.catalogo
            assert previo is not None
            self.inv = dataclasses.replace(
                self.inv, catalogo=dataclasses.replace(previo, permisos=catalogo().permisos)
            )
        self.etapas: list[Etapa] = []

    def servicio(self):
        return ServicioCreacion(self.sesion, self.reloj, intervalo_s=0.01)

    def cfg_clon(self, **kw):
        cfg, problemas = resolver_origen(
            cfg_clon("base", etiquetas=("proxlaunch", "lote-ab12cd34"), **kw), self.inv, "pve1"
        )
        assert problemas == []
        return cfg

    def crear(self, cfg):
        return self.servicio().crear(cfg, self.inv, self.etapas.append, threading.Event())

    def escrituras(self):
        return self.cl.rutas_de_escritura()

    def inicios(self):
        return [r for m, r in self.escrituras() if m == "POST" and r.endswith(INICIO)]


def _servicio_post(cfg, *, perm=None, cluster=None):
    """Crea una MV de disco vacío sobre ``ClusterA``; devuelve ``(resultado, cluster, etapas)``."""
    cl = cluster or ClusterA(("pve1",))
    reloj = RelojSeguro()
    sesion = crear_sesion(TransporteCluster(cl), reloj=reloj)  # type: ignore[arg-type]
    inv = inv_con(catalogo(perm=perm if perm is not None else True))
    etapas: list[Etapa] = []
    r = ServicioCreacion(sesion, reloj, intervalo_s=0.01).crear(
        cfg, inv, etapas.append, threading.Event()
    )
    return r, cl, etapas


# --- RF-A1.1: encender al final -------------------------------------------------------------------


def test_ca_a1_1_1_la_ultima_escritura_es_status_start_y_la_creacion_no_lleva_start():
    """CA-A1.1.1: con la casilla marcada y ``VM.PowerMgmt``, la última escritura es el ``start``."""
    r, cl, etapas = _servicio_post(cfg_vm(encender=True))
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    escrituras = cl.rutas_de_escritura()
    assert escrituras[-1] == ("POST", "/nodes/pve1/qemu/100/status/start")
    assert escrituras[0] == ("POST", "/nodes/pve1/qemu")
    assert "start" not in cl.cuerpos_post[100]
    assert cl.inicios == {100: 1}
    assert cl.vms[100]["status"] == "running"
    assert etapas[-2:] == [Etapa.ENCENDIENDO, Etapa.LISTO]


def test_ca_a1_1_3_casilla_desmarcada_no_emite_status_start():
    """CA-A1.1.3 (valor por defecto): ninguna escritura de encendido."""
    r, cl, etapas = _servicio_post(cfg_vm(encender=False))
    assert r.desenlace == Desenlace.OK
    assert cl.inicios == {} and Etapa.ENCENDIENDO not in etapas
    assert cl.vms[100]["status"] == "stopped"


def test_ca_a1_1_1_encender_no_cambia_el_post_de_creacion():
    """El POST de creación es el mismo con o sin ``encender`` (el encendido es otra petición)."""
    _, con, _ = _servicio_post(cfg_vm(encender=True))
    _, sin, _ = _servicio_post(cfg_vm(encender=False))
    assert con.cuerpos_post[100] == sin.cuerpos_post[100]


def test_ca_a1_1_6_sin_vm_powermgmt_no_se_crea_ni_se_envia_nada():
    """CA-A1.1.6: «Comprobar»/creación bloquea una MV que pide encender sin el privilegio."""
    r, cl, _ = _servicio_post(cfg_vm(encender=True), perm=permisos(ROL_BASE))
    assert r.desenlace == Desenlace.ERROR
    assert cl.rutas_de_escritura() == []  # ningún POST, ni de creación ni de encendido


def test_a1_1_permisos_desconocidos_no_bloquean_y_se_intenta_encender():
    """CA-A0.3.2: permisos ``None`` -> se confía en el servidor."""
    r, cl, _ = _servicio_post(cfg_vm(encender=True), perm=None)
    # ``perm=None`` en el helper significa «completos»; se fuerza desconocidos explícitamente.
    assert r.desenlace == Desenlace.OK
    cl2 = ClusterA(("pve1",))
    reloj = RelojSeguro()
    sesion = crear_sesion(TransporteCluster(cl2), reloj=reloj)  # type: ignore[arg-type]
    inv = inv_con(catalogo(perm=None))
    r2 = ServicioCreacion(sesion, reloj, intervalo_s=0.01).crear(
        cfg_vm(encender=True), inv, lambda _e: None, threading.Event()
    )
    assert r2.desenlace == Desenlace.OK and cl2.inicios == {100: 1}


def test_ca_a1_1_5_fallo_de_la_tarea_de_encendido_deja_la_mv_creada_con_aviso():
    """CA-A1.1.5 / P-6: tarea con error -> CON_AVISOS ``encendido_fallido``; la MV existe y está
    apagada.
    """
    cl = ClusterA(("pve1",))
    cl.exitstatus_inicio[100] = "start failed: not enough memory"
    r, cl, etapas = _servicio_post(cfg_vm(encender=True), cluster=cl)
    assert r.desenlace == Desenlace.CON_AVISOS
    assert "encendido_fallido" in r.avisos
    assert r.error is not None  # explica la causa
    assert 100 in cl.vms and cl.vms[100]["status"] == "stopped"
    assert cl.deletes == {}  # nunca se borra (CA-20.10)
    assert Etapa.ENCENDIENDO in etapas


@pytest.mark.parametrize(
    "codigo",
    [CodigoError.PERMISO_INSUFICIENTE, CodigoError.DESCONOCIDO, CodigoError.NODO_NO_DISPONIBLE],
)
def test_ca_a1_1_5_fallo_http_al_encender_tambien_es_aviso_no_error(codigo):
    """DT-A5: un 403/5xx al encender (también un fallo HTTP) nunca es un error de creación."""
    cl = ClusterA(("pve1",))
    cl.regla("POST", r"/status/start$", ErrorProxLaunch(codigo, {}, "falla"))
    r, cl, _ = _servicio_post(cfg_vm(encender=True), cluster=cl)
    assert r.desenlace == Desenlace.CON_AVISOS and "encendido_fallido" in r.avisos
    assert 100 in cl.vms


def test_a1_1_el_403_al_encender_nombra_el_privilegio_vm_powermgmt():
    cl = ClusterA(("pve1",))
    cl.regla(
        "POST", r"/status/start$", ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    )
    r, _, _ = _servicio_post(cfg_vm(encender=True), cluster=cl)
    assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params.get("privilegio") == "VM.PowerMgmt"


def test_a1_1_el_encendido_no_se_reintenta_ni_repite():
    """Un solo POST ``start`` aunque falle (repetirlo podría chocar con «ya en marcha»)."""
    cl = ClusterA(("pve1",))
    cl.regla("POST", r"/status/start$", ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {}, "596"))
    r, cl, _ = _servicio_post(cfg_vm(encender=True), cluster=cl)
    assert len(cl.llamadas_a("POST", r"/status/start$")) == 1


def test_a1_1_no_se_enciende_si_la_creacion_falla():
    cl = ClusterA(("pve1",))
    cl.exitstatus[100] = "storage 'datos' is not available"
    r, cl, etapas = _servicio_post(cfg_vm(encender=True), cluster=cl)
    assert r.desenlace == Desenlace.ERROR
    assert cl.inicios == {} and Etapa.ENCENDIENDO not in etapas


# --- Clon: orden y ajustes ------------------------------------------------------------------------


def test_ca_a1_1_2_y_a1_1_7_start_va_despues_del_clon_y_de_todos_sus_ajustes():
    """CA-A1.1.2/A1.1.7: clone -> PUT config (cores, onboot…) -> PUT resize -> status/start."""
    m = Mundo()
    cfg = m.cfg_clon(
        encender=True,
        arranque_auto=True,
        ajustes=AjustesClon(cores=4, disco_gib=64),
    )
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    rutas = m.escrituras()
    assert rutas[0] == ("POST", "/nodes/pve1/qemu/9000/clone")
    assert rutas[-1] == ("POST", "/nodes/pve1/qemu/100/status/start")
    assert ("PUT", "/nodes/pve1/qemu/100/config") in rutas
    assert ("PUT", "/nodes/pve1/qemu/100/resize") in rutas
    indice_inicio = len(rutas) - 1
    assert all(i < indice_inicio for i, (m_, _) in enumerate(rutas) if m_ == "PUT")
    assert m.cl.clones == {100: 1} and m.cl.posts == {}
    assert m.etapas[-3:] == [Etapa.AJUSTANDO, Etapa.ENCENDIENDO, Etapa.LISTO]


def test_ca_a1_2_3_el_clon_aplica_onboot_en_el_put_posterior_y_no_en_el_clone():
    """CA-A1.2.3 (P-7)."""
    m = Mundo()
    r = m.crear(m.cfg_clon(arranque_auto=True))
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    assert "onboot" not in m.cl.cuerpos_clon[100]
    puts = [p for p in m.cl.puts if p[2] == "config"]
    assert len(puts) == 1 and puts[0][3]["onboot"] == "1"
    assert m.cl.vms[100]["config"]["onboot"] == "1"


def test_ca_a6_1_4_el_clon_aplica_protection_en_el_ajuste_posterior():
    """CA-A6.1.4."""
    m = Mundo()
    assert m.crear(m.cfg_clon(proteger=True)).desenlace == Desenlace.OK
    assert [p[3] for p in m.cl.puts if p[2] == "config"] == [
        {"protection": "1", "tags": "lote-ab12cd34;proxlaunch"}
    ]
    assert m.cl.vms[100]["config"]["protection"] == "1"


def test_ca_a6_1_5_encender_y_proteger_se_cumplen_y_la_proteccion_va_antes_del_encendido():
    """CA-A6.1.5: ambas se cumplen y el orden sigue RF-A1.1 (la protección no impide encender)."""
    m = Mundo()
    r = m.crear(m.cfg_clon(proteger=True, encender=True))
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    rutas = m.escrituras()
    assert rutas[-1][1].endswith(INICIO)
    assert m.cl.vms[100]["config"]["protection"] == "1" and m.cl.vms[100]["status"] == "running"


def test_ca_a6_1_5_encender_y_proteger_en_disco_vacio():
    cfg = cfg_vm(encender=True, proteger=True)
    r, cl, _ = _servicio_post(cfg)
    assert r.desenlace == Desenlace.OK
    assert cl.cuerpos_post[100]["protection"] == "1"
    assert cl.rutas_de_escritura()[-1][1].endswith(INICIO)


def test_cl_a13_clon_de_plantilla_con_onboot_y_casilla_desmarcada_no_lo_desactiva():
    """CL-A13 / P-21: no se envía ``onboot=0`` ni ``protection=0``."""
    m = Mundo(onboot=1, protection=1)
    assert m.crear(m.cfg_clon()).desenlace == Desenlace.OK
    todos = {k for p in m.cl.puts for k in p[3]}
    assert not {"onboot", "protection", "startup"} & todos
    assert m.cl.vms[100]["config"].get("onboot") == 1  # la herencia de la plantilla se respeta


def test_a1_1_clon_con_ajuste_pendiente_no_enciende_y_avisa_encendido_omitido():
    """DT-A5: si queda un ajuste pendiente (PARCIAL) no se enciende y se avisa."""
    m = Mundo()
    m.cl.regla("PUT", r"/config$", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"))
    r = m.crear(m.cfg_clon(arranque_auto=True, encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert "encendido_omitido" in r.avisos
    assert m.inicios() == [] and Etapa.ENCENDIENDO not in m.etapas


def test_a1_1_reintentar_ajustes_enciende_solo_cuando_los_ajustes_quedan_completos():
    """DT-A5: ``reintentar_ajustes`` enciende si la MV tenía ``encender`` y ya no queda nada
    pendiente.
    """
    m = Mundo()
    regla = m.cl.regla("PUT", r"/config$", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"))
    cfg = m.cfg_clon(arranque_auto=True, encender=True)
    assert m.crear(cfg).desenlace == Desenlace.PARCIAL
    # Mientras el PUT sigue fallando, el reintento tampoco enciende.
    r1 = m.servicio().reintentar_ajustes(cfg, m.inv, threading.Event())
    assert r1.desenlace == Desenlace.PARCIAL and m.inicios() == []
    regla.veces = 0  # el servidor se recupera
    r2 = m.servicio().reintentar_ajustes(cfg, m.inv, threading.Event())
    assert r2.desenlace == Desenlace.OK, (r2.desenlace, r2.error)
    assert len(m.inicios()) == 1 and m.cl.vms[100]["status"] == "running"


def test_a1_1_comprobar_ahora_nunca_enciende():
    """Arq. §3.3: ``comprobar_ahora`` solo lee; no enciende aunque la MV pida encenderse."""
    from .apoyo_lote import upid_de

    m = Mundo()
    cfg = m.cfg_clon(encender=True)
    m.cl.vms[100] = {
        "nodo": "pve1",
        "config": {"name": cfg.nombre, "digest": "d"},
        "status": "stopped",
    }
    r = m.servicio().comprobar_ahora(cfg, upid_de("pve1", 100, "qmclone"), inv=m.inv)
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS, Desenlace.PARCIAL), r.error
    assert m.inicios() == [] and m.cl.vms[100]["status"] == "stopped"
    assert all(met == "GET" for met in (c.metodo for c in m.cl.llamadas))


# --- Lote: el encendido fallido no pausa ni detiene el lote ---------------------------------------


def _ejecutar(banco, definicion):
    plan = plan_de(banco, definicion)
    assert not plan.bloqueado, plan.problemas
    from .apoyo_lote import ControlAutomatico

    control = ControlAutomatico("suspender")
    libro = banco.ejecutar(plan, control)
    return plan, libro, control


def test_ca_a1_1_5_lote_de_tres_con_un_encendido_que_falla_el_resto_continua():
    """CA-A1.1.5: la MV 101 se crea y queda apagada con aviso; el lote no se pausa y termina."""
    banco = banco_a(inv=None)
    inv = inv_con(catalogo())
    banco.inv = inv
    banco.cluster.exitstatus_inicio[101] = "start failed"
    plan, libro, control = _ejecutar(banco, def_lote(3, plantilla_vm=cfg_vm(encender=True)))
    assert [e.vmid for e in plan.elementos] == [100, 101, 102]
    estados = {e.elemento.vmid: e for e in libro.instantanea()}
    assert control.pausas == []  # no pausa el lote (P-6)
    assert estados[101].estado == EstadoMV.CON_AVISOS
    assert "encendido_fallido" in estados[101].avisos
    assert estados[100].estado == EstadoMV.OK and estados[102].estado == EstadoMV.OK
    cl = banco.cluster
    assert cl.vms[101]["status"] == "stopped"
    assert cl.vms[100]["status"] == "running" and cl.vms[102]["status"] == "running"
    assert cl.deletes == {}  # sin rollback automático
    assert all(cl.posts[v] == 1 for v in (100, 101, 102))  # INV-L1: un POST de creación por VMID


def test_ca_a1_1_5_un_403_al_encender_no_pausa_el_lote():
    banco = banco_a(inv=None)
    banco.inv = inv_con(catalogo())
    banco.cluster.regla(
        "POST", r"/status/start$", ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    )
    plan, libro, control = _ejecutar(banco, def_lote(3, plantilla_vm=cfg_vm(encender=True)))
    assert control.pausas == []
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.CON_AVISOS] * 3
    assert all(len(e.avisos) >= 1 for e in libro.instantanea())


def test_ca_a0_7_1_lote_homogeneo_solo_enciende_las_que_lo_piden():
    """Sin ``encender`` ninguna MV del lote recibe ``status/start``."""
    banco = banco_a(inv=None)
    banco.inv = inv_con(catalogo())
    _ejecutar(banco, def_lote(3, plantilla_vm=cfg_vm(encender=False)))
    assert banco.cluster.inicios == {}


def test_ca_a1_1_6_lote_con_encender_y_sin_vm_powermgmt_queda_bloqueado_antes_de_enviar():
    """CA-A1.1.6: el plan se bloquea (error) y no se escribe nada."""
    banco = banco_a(inv=None)
    banco.inv = inv_con(catalogo(perm=permisos(ROL_BASE)))
    plan = plan_de(banco, def_lote(3, plantilla_vm=cfg_vm(encender=True)))
    assert any(p.regla == "V-A12" and p.severidad.value == "error" for p in plan.problemas)
    assert banco.cluster.rutas_de_escritura() == []


# --- CL-A2: lote mixto (clon + disco vacío) -------------------------------------------------------


def test_cl_a2_lote_mixto_clon_y_disco_vacio_usan_cada_uno_su_via():
    """CL-A2: ``description``/``pool`` en el POST de clone; tags, onboot y protection por el PUT; el
    disco vacío lo lleva todo en su POST."""
    cl = ClusterA(("pve1",))
    cl.agregar_plantilla(9000, "base", "pve1")
    cl.pools = ["produccion"]
    banco = banco_a(cluster=cl, inv=None)
    banco.inv = inv_con(catalogo())
    vacio = fila_a("web-01")
    clon = dataclasses.replace(
        fila_a("web-02"),
        cfg=dataclasses.replace(
            cfg_clon("base", 9000, "pve1"), discos=vacio.cfg.discos, redes=vacio.cfg.redes
        ),
    )
    from proxlaunch.nucleo.opciones.modelos import OpcionesLote

    base = OpcionesLote(
        arranque_auto=True, proteger=True, pool="produccion", notas_origen=True,
        etiquetas_usuario=("web",),
    )  # fmt: skip
    definicion = dataclasses.replace(def_filas([vacio, clon]), opciones=base)
    plan, libro, _ = _ejecutar(banco, definicion)
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK, EstadoMV.OK]
    post = cl.cuerpos_post[plan.elementos[0].vmid]
    assert {"description", "pool", "protection", "onboot", "tags"} <= set(post)
    assert post["pool"] == "produccion" and post["tags"].endswith(";web")
    vmid_clon = plan.elementos[1].vmid
    cuerpo_clon = cl.cuerpos_clon[vmid_clon]
    assert cuerpo_clon["pool"] == "produccion" and "description" in cuerpo_clon
    assert not {"onboot", "protection", "tags"} & set(cuerpo_clon)
    put = next(p[3] for p in cl.puts if p[1] == vmid_clon and p[2] == "config")
    assert put["onboot"] == "1" and put["protection"] == "1" and "web" in put["tags"]
    assert cl.posts.get(vmid_clon, 0) == 0  # el clon no usa POST /qemu


def test_a2_inventario_con_plantilla_helper_sigue_valido():
    """Control: el ``detalle_plantilla`` de ``apoyo_mvp4`` es una plantilla legible por defecto."""
    assert detalle_plantilla().descripcion_legible is True


# --- RF-A4.5: Deshacer de una MV creada en un pool ------------------------------------------------


def test_ca_a4_5_2_deshacer_de_una_mv_en_un_pool_emite_el_mismo_delete_sin_leer_pools():
    """CA-A4.5.2: mismo ``DELETE`` que sin pool y ninguna llamada adicional a ``/pools``."""
    from proxlaunch.nucleo.lote.motor import ControlLote
    from proxlaunch.nucleo.lote.rollback import ServicioRollback

    def _crear_y_deshacer(pool):
        cl = ClusterA()
        cl.pools = ["produccion"]
        banco = banco_a(cluster=cl, inv=None)
        banco.inv = inv_con(catalogo())
        plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_vm(pool=pool)))
        libro = banco.ejecutar(plan, ControlAutomatico("suspender"))
        assert all(e.estado == EstadoMV.OK for e in libro.instantanea())
        cl.reiniciar_llamadas()
        servicio = ServicioRollback(banco.sesion, banco.reloj)
        candidatos = servicio.elegibles(libro, etiquetado=True)
        servicio.deshacer(
            candidatos, lambda _r: None, ControlLote(), id_lote=libro.id_lote, etiquetado=True
        )
        return cl

    con = _crear_y_deshacer("produccion")
    sin = _crear_y_deshacer(None)
    assert con.deletes == sin.deletes == {100: 1, 101: 1}
    assert con.params_delete == sin.params_delete
    assert con.llamadas_a("GET", r"^/pools") == [] and con.llamadas_a("GET", r"pools") == []
    assert [c.ruta for c in con.llamadas if c.metodo != "GET"] == [
        c.ruta for c in sin.llamadas if c.metodo != "GET"
    ]


# --- Errores del servidor traducidos de extremo a extremo (CA-A2.5.6, CA-A4.4.2, CA-A3.4.12) ------


def _crear_por_http(rsps, regla_post, cfg):
    """Crea una MV con el transporte HTTP real (``responses``) y el traductor real."""
    from .apoyo_lote import crear_banco_http

    banco = crear_banco_http(rsps)
    banco.cluster.regla("POST", r"/qemu$", regla_post)
    servicio = ServicioCreacion(banco.sesion, banco.reloj, intervalo_s=0.01)
    return servicio.crear(cfg, banco.inv, lambda _e: None, threading.Event()), banco


def test_ca_a2_5_6_el_400_de_8192_caracteres_llega_traducido_a_descripcion_larga(rsps):
    """CA-A2.5.6: el doble devuelve el 400 a pesar de la validación; el error nombra
    ``description``.
    """
    from .apoyo_lote import Http

    cuerpo = {"data": None, "errors": {"description": "value may only be 8192 characters long"}}
    r, banco = _crear_por_http(
        rsps,
        lambda _ll: Http(400, "Parameter verification failed.", cuerpo),
        cfg_vm(descripcion="x" * 10),
    )
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.DESCRIPCION_LARGA
    assert r.error.params["campo"] == "description"
    assert banco.cluster.posts == {100: 1}  # un solo intento: no se reintenta un 400


def test_ca_a4_4_2_el_403_de_pool_inexistente_llega_traducido_a_pool_inexistente(rsps):
    """CA-A4.4.2: se traduce a «el pool no existe», no a un permiso genérico."""
    from .apoyo_lote import Http

    r, _ = _crear_por_http(
        rsps,
        lambda _ll: Http(403, "pool 'borrado' does not exist"),
        cfg_vm(pool="borrado"),
    )
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.POOL_INEXISTENTE
    assert r.error.params["pool"] == "borrado"


def test_ca_a3_4_12_la_tarea_que_falla_por_politica_de_etiquetas_se_traduce():
    """CA-A3.4.12: el POST es 200 y la TAREA falla con «Sys.Modify for modifying tag»."""
    cl = ClusterA(("pve1",))
    cl.exitstatus[100] = "Permission check failed (/, Sys.Modify for modifying tag 'prod')"
    cl.crea_en_post = False
    r, cl, _ = _servicio_post(
        cfg_vm(etiquetas=("proxlaunch",), etiquetas_usuario=("prod",)), cluster=cl
    )
    assert r.error is not None and r.error.codigo == CodigoError.ETIQUETA_RECHAZADA
    assert r.error.params.get("tag") == "prod"
    assert cl.deletes == {}


def test_rd_a2_put_de_clon_que_falla_deja_parcial_con_los_ajustes_pendientes_nombrados():
    """RD-A2: si el PUT posterior falla, la MV queda PARCIAL con ``ajuste_pendiente:*`` y no se
    borra.
    """
    m = Mundo()
    m.cl.regla("PUT", r"/config$", ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"))
    r = m.crear(m.cfg_clon(proteger=True, arranque_auto=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert {"ajuste_pendiente:proteccion", "ajuste_pendiente:arranque"} <= set(r.avisos)
    assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["privilegio"] == "VM.Config.Options"
    assert m.cl.deletes == {} and 100 in m.cl.vms


def test_a1_2_3_ajustes_ya_aplicados_en_la_plantilla_no_se_reenvian():
    """Idempotencia (CA-O22.6): si la plantilla ya tiene ``onboot=1`` y se pide, no hay PUT de
    onboot.
    """
    m = Mundo(onboot=1)
    assert m.crear(m.cfg_clon(arranque_auto=True)).desenlace == Desenlace.OK
    assert all("onboot" not in p[3] for p in m.cl.puts)


def _crear_importando(**opciones):
    """Importar disco con ampliación (``PUT resize``) sobre ``ClusterA``; devuelve ``(r, cl)``."""
    from proxlaunch.nucleo.modelos.catalogo import Contenido

    from .apoyo_mvp4 import VOLID_IMAGEN, cfg_import, listado

    cl = ClusterA(("pve1",))
    cl.contenido[("pve1", "local")] = [VOLID_IMAGEN]
    reloj = RelojSeguro()
    sesion = crear_sesion(TransporteCluster(cl), reloj=reloj)  # type: ignore[arg-type]
    inv = inv_origen(
        listados=(listado("pve1", "local", Contenido.IMPORT, VOLID_IMAGEN),),
        permisos_efectivos=catalogo().permisos,
    )
    cfg = cfg_import(cfg=opciones, ampliar_a_gib=64)
    etapas: list[Etapa] = []
    r = ServicioCreacion(sesion, reloj, intervalo_s=0.01).crear(
        cfg, inv, etapas.append, threading.Event()
    )
    return r, cl, etapas


def test_ca_a1_1_2_importar_disco_el_start_va_despues_de_ampliar_el_disco():
    """CA-A1.1.2: con ajustes posteriores (ampliar disco) ``status/start`` es lo último."""
    r, cl, etapas = _crear_importando(encender=True, arranque_auto=True, proteger=True)
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    rutas = cl.rutas_de_escritura()
    assert rutas[0] == ("POST", "/nodes/pve1/qemu")
    assert ("PUT", "/nodes/pve1/qemu/100/resize") in rutas
    assert rutas[-1] == ("POST", "/nodes/pve1/qemu/100/status/start")
    assert rutas.index(("PUT", "/nodes/pve1/qemu/100/resize")) < len(rutas) - 1
    assert cl.cuerpos_post[100]["onboot"] == "1" and cl.cuerpos_post[100]["protection"] == "1"
    assert "start" not in cl.cuerpos_post[100]
    assert etapas[-3:] == [Etapa.AJUSTANDO, Etapa.ENCENDIENDO, Etapa.LISTO]


def test_ca_a1_1_3_importar_disco_sin_encender_no_emite_start():
    r, cl, _ = _crear_importando()
    assert r.desenlace == Desenlace.OK and cl.inicios == {}
