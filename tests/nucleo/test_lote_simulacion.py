"""Simulación de solo lectura y guardián de INV-L5 (RF-L11, CA-L11.*, RNF-L08).

Un contador de métodos HTTP en el servidor simulado demuestra que la simulación nunca escribe.
"""

import pytest

from proxlaunch.nucleo.api.solo_lectura import METODOS_LECTURA, TransporteSoloLectura
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote import planificador as modulo_planificador
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.simulacion import simular

from .apoyo_lote import (
    CENTINELA_TOKEN,
    Cluster,
    TransporteCluster,
    crear_banco,
    definicion,
    nodo_caido,
    volcar,
)


class _TransporteQueRegistra:
    """Transporte interno: cuenta lo que llega (lo que SÍ salió hacia la red)."""

    host_activo = "10.0.0.1"

    def __init__(self):
        self.llamadas = []

    def usar_autenticador(self, auth):
        pass

    def peticion(self, metodo, ruta, *, params=None, datos=None):
        self.llamadas.append((metodo, ruta, params, datos))
        return {"ok": 1}


# --- TransporteSoloLectura -----------------------------------------------------------------


@pytest.mark.parametrize("metodo", ["POST", "DELETE", "PUT", "PATCH", "post", "Delete", "OPTIONS"])
def test_inv_l5_el_guardian_rechaza_cualquier_escritura_antes_de_salir(metodo):
    interno = _TransporteQueRegistra()
    guardian = TransporteSoloLectura(interno)
    with pytest.raises(ErrorProxLaunch) as exc:
        guardian.peticion(metodo, "/nodes/pve1/qemu", datos={"vmid": "100", "name": "x"})
    assert exc.value.codigo == CodigoError.ESCRITURA_EN_SIMULACION
    assert interno.llamadas == []  # nada llegó a la red


@pytest.mark.parametrize("metodo", ["GET", "HEAD", "get", "head"])
def test_el_guardian_deja_pasar_las_lecturas(metodo):
    interno = _TransporteQueRegistra()
    assert TransporteSoloLectura(interno).peticion(metodo, "/version") == {"ok": 1}
    assert len(interno.llamadas) == 1


def test_el_guardian_no_lleva_el_cuerpo_ni_secretos_en_el_error():
    interno = _TransporteQueRegistra()
    with pytest.raises(ErrorProxLaunch) as exc:
        TransporteSoloLectura(interno).peticion(
            "POST", "/nodes/pve1/qemu", datos={"password": CENTINELA_TOKEN, "name": "x"}
        )
    assert CENTINELA_TOKEN not in volcar(exc.value)
    assert CENTINELA_TOKEN not in repr(exc.value)


def test_los_metodos_de_lectura_son_solo_get_y_head():
    assert set(METODOS_LECTURA) == {"GET", "HEAD"}


def test_el_guardian_delega_host_y_autenticador():
    interno = _TransporteQueRegistra()
    guardian = TransporteSoloLectura(interno)
    assert guardian.host_activo == "10.0.0.1"
    guardian.usar_autenticador(None)  # no debe fallar


def test_cliente_solo_lectura_no_puede_crear_ni_eliminar(banco):
    ro = banco.sesion.cliente.solo_lectura()
    with pytest.raises(ErrorProxLaunch) as e1:
        ro.crear_vm("pve1", {"vmid": "100", "name": "x"})
    with pytest.raises(ErrorProxLaunch) as e2:
        ro.eliminar_vm("pve1", 100)
    assert e1.value.codigo == e2.value.codigo == CodigoError.ESCRITURA_EN_SIMULACION
    assert banco.cluster.llamadas == []


def test_cliente_solo_lectura_si_puede_leer(banco):
    ro = banco.sesion.cliente.solo_lectura()
    assert ro.vmid_libre(150) is True
    assert banco.cluster.metodos == {"GET": 1}


# --- Simulación (CA-L11.1 a CA-L11.9) -------------------------------------------------------------


def _simular(banco, d, **kw):
    return simular(banco.sesion, d, banco.inv, reloj=banco.reloj, **kw)


def test_ca_l11_1_la_simulacion_solo_hace_get(banco):
    banco.cluster.ocupados = {101}
    res = _simular(banco, definicion(5, vmid_inicial=100))
    assert banco.cluster.solo_lecturas
    assert banco.cluster.total("POST") == banco.cluster.total("DELETE") == 0
    assert banco.cluster.total("GET") > 0
    assert res.plan.es_simulacion is True


def test_ca_l11_1_mutacion_si_el_codigo_de_simulacion_intenta_un_post_el_guardian_lo_corta(
    banco, monkeypatch
):
    """Prueba de mutación: se inyecta una escritura en la ruta de planificación."""

    def _planificar_con_escritura(self, definicion_, inv, *, version_forzada=None):
        self._sesion.cliente.crear_vm("pve1", {"vmid": "100", "name": "mutante"})

    monkeypatch.setattr(modulo_planificador.Planificador, "planificar", _planificar_con_escritura)
    with pytest.raises(ErrorProxLaunch) as exc:
        _simular(banco, definicion(2))
    assert exc.value.codigo == CodigoError.ESCRITURA_EN_SIMULACION
    assert banco.cluster.total("POST") == 0


def test_ca_l11_1_mutacion_un_delete_en_la_simulacion_tambien_se_corta(banco, monkeypatch):
    def _planificar_con_borrado(self, definicion_, inv, *, version_forzada=None):
        self._sesion.cliente.eliminar_vm("pve1", 100)

    monkeypatch.setattr(modulo_planificador.Planificador, "planificar", _planificar_con_borrado)
    with pytest.raises(ErrorProxLaunch) as exc:
        _simular(banco, definicion(2))
    assert exc.value.codigo == CodigoError.ESCRITURA_EN_SIMULACION
    assert banco.cluster.total("DELETE") == 0


def test_ca_l11_1_la_simulacion_no_cambia_la_sesion_original(banco):
    cliente = banco.sesion.cliente
    _simular(banco, definicion(2))
    assert banco.sesion.cliente is cliente  # no se sustituye el cliente de la sesión


def test_ca_l11_2_incluye_el_cuerpo_exacto_que_se_enviaria_por_cada_vmid(banco):
    res = _simular(banco, definicion(3, vmid_inicial=100))
    assert sorted(res.peticiones) == [100, 101, 102]
    for e in res.plan.elementos:
        esperado = construir_parametros(e.cfg, banco.inv, res.plan.version_validacion)
        assert res.peticiones[e.vmid] == esperado
        assert res.peticiones[e.vmid]["name"] == e.nombre
        assert res.peticiones[e.vmid]["tags"].endswith(f"lote-{res.plan.id_lote}")


def test_ca_l11_2_las_peticiones_simuladas_coinciden_con_las_reales(banco):
    d = definicion(3, vmid_inicial=100)
    res = _simular(banco, d)
    plan_real = banco.planificar(d)
    banco.ejecutar(plan_real)
    for vmid, cuerpo in res.peticiones.items():
        enviado = banco.cluster.cuerpos_post[vmid]
        sin_tags = lambda c: {k: v for k, v in c.items() if k != "tags"}  # noqa: E731
        assert sin_tags(enviado) == sin_tags(cuerpo)


def test_ca_l11_2_las_peticiones_no_llevan_secretos_ni_cabeceras(banco):
    res = _simular(banco, definicion(2))
    texto = volcar(res.peticiones).lower()
    for prohibido in (
        "authorization",
        "cookie",
        "csrf",
        "ticket",
        "password",
        CENTINELA_TOKEN.lower(),
    ):
        assert prohibido not in texto


def test_ca_l11_3_la_simulacion_y_la_ejecucion_real_planifican_igual(banco):
    banco.cluster.ocupados = {102}
    banco.cluster.agregar_vm(200, "pve1", "web-02")
    d = definicion(6, vmid_inicial=100)
    sim = _simular(banco, d).plan
    real = banco.planificar(d)

    def _contenido(p):
        return (p.elementos, p.vmids_saltados, p.reparto, p.uso, p.problemas, p.capacidad_maxima)

    # El id de lote aleatorio cambia las etiquetas; se compara con el id del real.
    from dataclasses import replace

    sim_igual_id = replace(
        sim,
        id_lote=real.id_lote,
        elementos=tuple(
            replace(e, cfg=replace(e.cfg, etiquetas=("proxlaunch", f"lote-{real.id_lote}")))
            for e in sim.elementos
        ),
    )
    assert _contenido(sim_igual_id) == _contenido(real)


def test_ca_l11_4_la_simulacion_lee_el_vmid_real_del_servidor(banco):
    banco.cluster.ocupados = {100}
    res = _simular(banco, definicion(2, vmid_inicial=100))
    assert [e.vmid for e in res.plan.elementos] == [101, 102]
    assert res.plan.vmids_saltados == (100,)


def test_ca_l11_6_version_forzada_menor_valida_con_la_forzada_y_la_registra(banco):
    res = _simular(banco, definicion(2), version_forzada=(8, 0))
    assert res.version_forzada == (8, 0)
    assert res.version_detectada == (9, 2)
    assert res.plan.version_validacion == (8, 0)
    assert not res.plan.bloqueado


def test_ca_l11_7_version_forzada_mayor_se_puede_simular_pero_el_plan_queda_bloqueado(banco):
    res = _simular(banco, definicion(2), version_forzada=(9, 9))
    assert res.plan.bloqueado
    assert [p.regla for p in res.plan.problemas if p.regla == "V-L15"]
    assert res.peticiones  # la simulación sigue construyendo las peticiones
    assert banco.cluster.solo_lecturas


def test_ca_l11_5_una_simulacion_sin_errores_deja_un_plan_ejecutable(banco):
    res = _simular(banco, definicion(3))
    assert not res.plan.bloqueado
    libro = banco.ejecutar(res.plan)  # "Crear de verdad": se vuelve a planificar en la interfaz
    assert all(e.estado.value == "ok" for e in libro.instantanea())


def test_una_definicion_invalida_se_simula_sin_peticiones_ni_escrituras(banco):
    res = _simular(banco, definicion(0))
    assert res.plan.bloqueado
    assert res.peticiones == {}
    assert banco.cluster.llamadas == []


def test_ca_l11_9_la_simulacion_no_deja_libro_ni_estado_en_el_servidor(banco):
    res = _simular(banco, definicion(3))
    assert not isinstance(res, Libro)
    assert banco.cluster.vms == {}
    assert dict(banco.cluster.posts) == {}


def test_un_error_de_red_en_la_simulacion_se_propaga_sin_escribir(banco):
    banco.cluster.regla("GET", r"^/cluster/nextid$", nodo_caido("pve1", 596))
    with pytest.raises(ErrorProxLaunch) as exc:
        _simular(banco, definicion(2, vmid_inicial=100))
    assert exc.value.codigo == CodigoError.NODO_NO_DISPONIBLE
    assert banco.cluster.solo_lecturas


def test_la_simulacion_usa_el_cliente_aunque_el_transporte_original_aceptara_escrituras():
    """El contador del servidor ve solo GET aunque el transporte de la sesión permita POST."""
    cluster = Cluster(("pve1",))
    banco = crear_banco(cluster=cluster)
    assert isinstance(banco.sesion.cliente._transporte, TransporteCluster)  # permite escribir
    _simular(banco, definicion(4))
    assert cluster.metodos.keys() == {"GET"}
