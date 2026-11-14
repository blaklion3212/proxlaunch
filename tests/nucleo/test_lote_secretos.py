"""Centinela de secretos en los flujos del lote (RNF-L06, CA-L20.1, CA-L20.2, CA-L19.3).

Valores centinela únicos (token, ticket, CSRF, contraseña) se registran como lo haría el inicio
de sesión y el servidor simulado los REPITE en sus errores. Se recorren plan, simulación,
ejecución con fallos inyectados, comprobación, rollback e informe, y se busca cada centinela en
todo lo que el núcleo produce: datos, errores y el archivo de log real (con su filtro).
"""

import logging

import pytest
import requests

from proxlaunch.nucleo.lote.informe import construir_informe
from proxlaunch.nucleo.lote.modelos import MetadatosInforme
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.registro import configurar_registro, registrar_secreto

from .apoyo_api import TOKEN_ID
from .apoyo_lote import (
    CENTINELA_CLAVE,
    CENTINELA_CSRF,
    CENTINELA_TICKET,
    CENTINELA_TOKEN,
    TODOS_LOS_CENTINELAS,
    ControlAutomatico,
    Http,
    crear_banco_http,
    definicion,
    upid_de,
    volcar,
)

ECO_TOKEN = f"PVEAPIToken={TOKEN_ID}={CENTINELA_TOKEN}"
ECO_PLANO = f"fallo con {CENTINELA_CLAVE} y {CENTINELA_TICKET} y csrf {CENTINELA_CSRF}"
METADATOS = MetadatosInforme("laboratorio", "9.2.1", True, "lab", "2026-11-13T10:00:00")


@pytest.fixture
def log_real(tmp_path):
    """Registro real de la aplicación (archivo con filtro de secretos) y sus líneas."""
    logger = configurar_registro(tmp_path, logging.DEBUG)
    for s in TODOS_LOS_CENTINELAS:
        registrar_secreto(s)
    yield tmp_path / "proxlaunch.log"
    for h in list(logger.handlers):
        if getattr(h, "_proxlaunch", False):
            logger.removeHandler(h)
            h.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def _leer(ruta):
    for h in logging.getLogger("proxlaunch").handlers:
        h.flush()
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


def _sin_centinelas(texto, donde):
    for secreto in TODOS_LOS_CENTINELAS:
        assert secreto not in texto, f"{secreto} aparece en {donde}"


def _http_5xx(texto):
    return lambda ll: Http(500, "internal error", {"data": None, "message": texto})


def _por_vmid(banco, metodo, patron, ayuda):
    """Regla que aplica ``ayuda(vmid)`` (una Respuesta/excepción o ``None``) por VMID."""

    def _accion(llamada):
        vmid = int((llamada.datos or {}).get("vmid") or llamada.ruta.rstrip("/").split("/")[-1])
        que = ayuda(vmid)
        if que is None:
            from .apoyo_lote import NORMAL

            return NORMAL
        if isinstance(que, BaseException):
            raise que
        return que(llamada) if callable(que) else que

    banco.cluster.regla(metodo, patron, _accion)


def test_el_servidor_simulado_realmente_repite_los_secretos_en_sus_errores(rsps):
    """Control del montaje: sin esto las demás pruebas serían vacías."""
    banco = crear_banco_http(rsps)
    banco.cluster.regla("POST", r"/qemu$", _http_5xx(ECO_TOKEN + ECO_PLANO))
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    banco.ejecutar(plan, ControlAutomatico("continuar"))
    cuerpos = [c.response.text for c in rsps.calls if c.request.method == "POST"]
    assert any(CENTINELA_TOKEN in c and CENTINELA_CLAVE in c for c in cuerpos)


def test_ca_rnf_l06_ningun_flujo_del_lote_filtra_un_secreto(rsps, log_real):
    banco = crear_banco_http(rsps)
    cl = banco.cluster
    salidas = {}

    # 1. Plan.
    d = definicion(7, vmid_inicial=100)
    plan = banco.planificar(d)
    salidas["plan"] = volcar(plan)

    # 2. Simulación (solo lecturas).
    sim = simular(banco.sesion, d, banco.inv, reloj=banco.reloj)
    salidas["simulacion"] = volcar(sim)
    assert cl.solo_lecturas

    # 3. Ejecución con fallos inyectados que repiten los secretos en el texto de error.
    cl.exitstatus[101] = f"unable to create VM: {ECO_PLANO}"
    _por_vmid(
        banco,
        "POST",
        r"/qemu$",
        lambda v: {
            100: _http_5xx(ECO_TOKEN),
            102: requests.exceptions.ConnectionError(
                f"Connection aborted Authorization: {ECO_TOKEN}"
            ),
            103: requests.exceptions.ReadTimeout(ECO_PLANO),
            104: RuntimeError(ECO_PLANO),
            105: Http(
                403, "denied", {"data": None, "message": f"Permission check failed {ECO_TOKEN}"}
            ),
        }.get(v),
    )
    control = ControlAutomatico("continuar")
    libro = banco.ejecutar(plan, control)
    salidas["libro"] = volcar(libro.instantanea())
    salidas["pausas"] = volcar(control.pausas)

    # 4. Comprobación de las dudosas (lecturas) con más errores que repiten secretos.
    _por_vmid(banco, "GET", r"qemu/\d+/config$", lambda v: Http(500, "x", {"message": ECO_PLANO}))
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote())
    salidas["tras_comprobar"] = volcar(libro.instantanea())

    # 5. Rollback con fallos que repiten secretos (el servidor ya no responde bien).
    cl.reglas.clear()
    _por_vmid(
        banco,
        "DELETE",
        r"qemu/\d+$",
        lambda v: _http_5xx(ECO_TOKEN + ECO_PLANO) if v == 106 else None,
    )
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    candidatos = servicio.elegibles(libro, etiquetado=True)
    resultados = servicio.deshacer(
        candidatos, lambda r: None, ControlLote(), id_lote=libro.id_lote, etiquetado=True
    )
    salidas["rollback"] = volcar(resultados) + volcar(candidatos)

    # 6. Informe (con la sección "deshacer").
    informe = construir_informe(plan, libro, METADATOS, rollback=resultados, reloj=banco.reloj)
    salidas["informe"] = volcar(informe)

    # Los errores reales de la ejecución quedaron registrados (la prueba no es vacía).
    assert sum(1 for e in libro.instantanea() if e.error is not None) >= 3

    for nombre, texto in salidas.items():
        _sin_centinelas(texto, nombre)
    # 7. Log real: ni una línea con un centinela (CA-L20.2).
    log = _leer(log_real)
    assert "Lote " in log  # se escribió el registro por MV (CA-L20.1)
    _sin_centinelas(log, "el log")


def test_ca_l20_1_el_log_incluye_por_maquina_id_vmid_nodo_upid_estado_y_codigo(rsps, log_real):
    banco = crear_banco_http(rsps)
    banco.cluster.exitstatus[101] = "unable to create VM: Volume group has insufficient free space"
    plan = banco.planificar(definicion(2, vmid_inicial=100))
    banco.ejecutar(plan)
    log = _leer(log_real)
    lineas = [ln for ln in log.splitlines() if f"Lote {plan.id_lote}" in ln]
    assert len(lineas) == 2
    por_vmid = {v: next(ln for ln in lineas if f"vmid={v} " in ln) for v in (100, 101)}
    assert "nodo=pve1" in por_vmid[100] and ":qmcreate:100:" in por_vmid[100]
    assert "estado=ok" in por_vmid[100] and "codigo=-" in por_vmid[100]
    assert "estado=error" in por_vmid[101] and "codigo=sin_espacio" in por_vmid[101]
    assert "insufficient free space" in por_vmid[101]  # texto original de Proxmox


def test_ca_l20_4_el_log_no_incluye_cuerpos_de_respuesta_completos(rsps, log_real):
    banco = crear_banco_http(rsps)
    enorme = "x" * 50_000
    banco.cluster.exitstatus[100] = f"unable to create VM: {enorme}"
    plan = banco.planificar(definicion(1, vmid_inicial=100))
    banco.ejecutar(plan)
    assert enorme not in _leer(log_real)
    assert max(len(ln) for ln in _leer(log_real).splitlines()) < 5_000


def test_ca_l20_2_un_secreto_en_el_texto_de_una_excepcion_inesperada_no_llega_al_log(
    rsps, log_real
):
    banco = crear_banco_http(rsps)
    from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

    class _Servicio(ServicioCreacion):
        def crear(self, *a, **kw):
            raise RuntimeError(f"fallo interno con {CENTINELA_TOKEN} y {CENTINELA_CLAVE}")

    plan = banco.planificar(definicion(2, vmid_inicial=100))
    libro = banco.ejecutar(plan, motor=banco.motor(fabrica_creacion=_Servicio))
    _sin_centinelas(_leer(log_real), "el log")
    _sin_centinelas(volcar(libro.instantanea()), "el libro")


def test_ca_rnf_l06_la_simulacion_y_el_resumen_no_llevan_credenciales(rsps):
    banco = crear_banco_http(rsps)
    sim = simular(banco.sesion, definicion(3, vmid_inicial=100), banco.inv, reloj=banco.reloj)
    for secreto in (*TODOS_LOS_CENTINELAS, "PVEAPIToken", "Authorization", TOKEN_ID):
        assert secreto not in volcar(sim)


def test_upid_helper_no_filtra_secretos():
    assert not any(s in upid_de("pve1", 1) for s in TODOS_LOS_CENTINELAS)
