"""Correcciones derivadas de la validación en el laboratorio (PVE 9.2): 597, D-1 y D-2."""

from __future__ import annotations

import threading

import pytest

from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
from proxlaunch.nucleo.api.transporte import TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_api import (
    HUELLA_A,
    RUTA_CREAR,
    TransporteFalso,
    agregar_error,
    crear_sesion,
    rutas_creacion,
    url,
)
from .test_respuestas_reales_lab import traducir

A, B = "10.0.0.1", "10.0.0.2"


def _http(hosts=(A,)):
    t = TransporteHttp(list(hosts), 8006, huellas={h: HUELLA_A for h in hosts})
    t.usar_autenticador(AutenticadorToken(CredencialToken("ana@pve!lab", "s" * 12)))
    return t


# --- 597 (fallo al recibir el cuerpo) -------------------------------------------------


def test_get_con_597_hace_failover_al_siguiente_host(rsps):
    agregar_error(rsps, "GET", url(A, "/version"), 597, "Unexpected end-of-file")
    rsps.get(url(B, "/version"), json={"data": {"version": "9.2.1"}})
    t = _http((A, B))
    assert t.peticion("GET", "/version") == {"version": "9.2.1"}
    assert t.host_activo == B


def test_get_con_597_en_todos_los_hosts_es_nodo_no_disponible(rsps):
    agregar_error(rsps, "GET", url(A, "/nodes/pve-lab/storage"), 597, "eof")
    agregar_error(rsps, "GET", url(B, "/nodes/pve-lab/storage"), 597, "eof")
    with pytest.raises(ErrorProxLaunch) as e:
        _http((A, B)).peticion("GET", "/nodes/pve-lab/storage")
    assert e.value.codigo == CodigoError.NODO_NO_DISPONIBLE


def test_post_con_597_es_incierto_y_no_prueba_otro_host(rsps):
    agregar_error(rsps, "POST", url(A, "/nodes/pve-lab/qemu"), 597, "eof")
    rsps.post(url(B, "/nodes/pve-lab/qemu"), json={"data": "UPID:x:y"})
    with pytest.raises(ErrorProxLaunch) as e:
        _http((A, B)).peticion("POST", "/nodes/pve-lab/qemu", datos={"vmid": "100"})
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE
    assert e.value.params["incierto"] == "1"
    assert not any(c.request.url.startswith(f"https://{B}") for c in rsps.calls)


def test_creacion_con_post_597_es_conexion_perdida_sin_upid(inv, hacer_cfg, reloj):
    incierto = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE, {"host": A, "incierto": "1", "motivos": f"{A}=597"}
    )
    t = rutas_creacion(TransporteFalso(), estado=None, crear=incierto)
    sesion = crear_sesion(t, reloj=reloj)
    r = ServicioCreacion(sesion, reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert r.upid is None


# --- D-1: detalle sin repetir ---------------------------------------------------------


def test_detalle_de_un_403_real_no_repite_el_mensaje():
    e = traducir("error_permiso_403", nodo="pve-lab")
    assert e.detalle_tecnico.count("Permission check failed (/vms/9044, VM.Config.Memory)") == 1


# --- D-2: 403 de creación sin privilegio ----------------------------------------------


def _crear_con_error(error, inv, hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=None, crear=error)
    sesion = crear_sesion(t, reloj=reloj)
    cfg = hacer_cfg()
    r = ServicioCreacion(sesion, reloj).crear(cfg, inv, lambda e: None, threading.Event())
    return r, cfg


def test_403_real_de_vm_allocate_se_completa_con_privilegio_inferido(inv, hacer_cfg, reloj):
    real = traducir("error_permiso_403_vm_allocate")
    assert real.params == {}
    r, cfg = _crear_con_error(real, inv, hacer_cfg, reloj)
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params == {
        "privilegio": "VM.Allocate",
        "ruta": f"/vms/{cfg.vmid}",
        "inferido": "1",
    }


def test_403_real_con_privilegio_no_se_modifica(inv, hacer_cfg, reloj):
    real = traducir("error_permiso_403", nodo="pve-lab")
    r, _ = _crear_con_error(real, inv, hacer_cfg, reloj)
    assert r.error.params == {"privilegio": "VM.Config.Memory", "ruta": "/vms/9044"}
    assert "inferido" not in r.error.params


def test_post_directo_no_alcanzado_por_ruta_crear(inv, hacer_cfg, reloj):
    # La ruta de creación sigue siendo un único POST (sin reintentos).
    real = traducir("error_permiso_403_vm_allocate")
    t = rutas_creacion(TransporteFalso(), estado=None, crear=real)
    ServicioCreacion(crear_sesion(t, reloj=reloj), reloj).crear(
        hacer_cfg(), inv, lambda e: None, threading.Event()
    )
    assert len(t.llamadas_a("POST", RUTA_CREAR)) == 1
