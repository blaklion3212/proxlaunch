"""Escenarios de las instantáneas («golden») de 0.6.0 para la fase B (CA-B0.2.1, CA-B0.2.2,
CA-B3.1.4, CA-B7.2.1). Sin aserciones.

Cada escenario ejecuta el código REAL (servicio de creación, motor, Deshacer, simulación) sobre el
transporte HTTP real contra el clúster simulado (``responses``) y recoge la secuencia COMPLETA de
peticiones recibidas: método, ruta, consulta y cuerpo del formulario en bytes. Con las opciones de
la fase B por defecto, 0.7.0 debe producir exactamente lo mismo que 0.6.0.

Este módulo SOLO usa API que existe igual en 0.6.0 y en 0.7.0: así se ejecuta contra el código de
la etiqueta ``v0.6.0`` para generar ``tests/datos/fase_b/golden_v060.json`` y contra 0.7.0 para
compararlo.

Regenerar (desde la raíz del repositorio, sin tocar el árbol de trabajo)::

    git archive v0.6.0 src | tar -x -C <carpeta_temporal>
    .venv/bin/python -c "import sys; sys.path[:0] = ['<carpeta_temporal>/src', '.']; \\
        from tests.nucleo.apoyo_golden_fase_b import generar; generar('<salida.json>')"

(``generar`` comprueba que ``proxlaunch`` sale de la carpeta temporal y no del árbol de trabajo).
"""

from __future__ import annotations

import dataclasses
import functools
import json
import re
import threading
from pathlib import Path
from typing import Any

import responses

from proxlaunch.nucleo.lote.modelos import AccionPeticion
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.origen import AjustesClon
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_fase_a import ClusterA, catalogo, cfg_vm, def_lote, inv_con, plan_de
from .apoyo_lote import Http, crear_banco_http
from .apoyo_mvp4 import (
    VOLID_IMAGEN,
    VOLID_ISO,
    cfg_clon,
    cfg_import,
    cfg_iso,
    inv_origen,
    plantilla_pve,
)

RUTA_GOLDEN = Path(__file__).resolve().parents[1] / "datos" / "fase_b" / "golden_v060.json"
ETIQUETAS_LOTE = ("proxlaunch", "lote-ab12cd34")

_RE_VMID_RUTA = re.compile(r"/qemu/(\d+)")
_RE_VMID_CUERPO = re.compile(r"(?:^|&)(?:vmid|newid)=(\d+)")
_RE_VMID_CONSULTA = re.compile(r"(?:^|&)vmid=(\d+)")


def _grupo(metodo: str, ruta: str, consulta: str, cuerpo: str) -> int:
    """VMID al que pertenece una petición (0 = ninguno): sirve para ordenar un lote en paralelo."""
    for patron, texto in (
        (_RE_VMID_RUTA, ruta),
        (_RE_VMID_CUERPO, cuerpo),
        (_RE_VMID_CONSULTA, consulta),
    ):
        if m := patron.search(texto):
            return int(m.group(1))
    return 0


def _traza(cl: ClusterA, *, por_mv: bool = False) -> list[list[str]]:
    """Peticiones recibidas como ``[método, ruta?consulta, cuerpo]``. ``por_mv`` agrupa por VMID
    (conserva el orden de cada MV): para lotes, cuyas MVs se crean en paralelo."""
    filas = [
        [m, ruta + (f"?{q}" if q else ""), cuerpo.decode("ascii")]
        for m, ruta, q, cuerpo in cl.trazas
    ]
    if not por_mv:
        return filas
    claves = [_grupo(m, ruta, q, c.decode("ascii")) for m, ruta, q, c in cl.trazas]
    orden = sorted(range(len(filas)), key=lambda i: (claves[i], i))
    return [filas[i] for i in orden]


class _Mundo:
    """Clúster ``ClusterA`` servido por HTTP real, con una plantilla (9000) y un servicio."""

    def __init__(self, rsps: Any, **inv_kw: Any) -> None:
        self.cl = ClusterA(("pve1",))
        self.cl.agregar_plantilla(9000, "base", "pve1", tags="plantilla", cores=2, memory=2048)
        self.cl.contenido[("pve1", "local")] = [VOLID_ISO, VOLID_IMAGEN]
        self.banco = crear_banco_http(rsps, ("pve1",), cluster=self.cl)
        det = detalle_de_config(self.cl.plantillas[9000]["config"])
        inv_kw.setdefault("nodos", ("pve1",))
        inv_kw.setdefault("privilegios", (*ROL_PROXLAUNCH, "VM.PowerMgmt", "Pool.Audit"))
        self.inv = inv_origen(
            plantillas=(plantilla_pve(9000, "base", "pve1", detalle=det),), **inv_kw
        )
        self.banco.inv = self.inv

    def crear(self, cfg: Any) -> Any:
        servicio = ServicioCreacion(self.banco.sesion, self.banco.reloj, intervalo_s=0.01)
        return servicio.crear(cfg, self.inv, lambda _e: None, threading.Event())

    def clon(self, **kw: Any) -> Any:
        kw.setdefault("etiquetas", ETIQUETAS_LOTE)
        cfg, problemas = resolver_origen(cfg_clon("base", **kw), self.inv, "pve1")
        assert problemas == [], problemas
        return cfg


def _en_http(escenario: Any) -> Any:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        return escenario(rsps)


# --- Escenarios ---------------------------------------------------------------------------------


def _vacio(rsps: Any, **cambios: Any) -> list[list[str]]:
    m = _Mundo(rsps)
    m.banco.inv = m.inv = inv_con(catalogo())
    m.crear(cfg_vm(**cambios))
    return _traza(m.cl)


def _iso(rsps: Any) -> list[list[str]]:
    m = _Mundo(rsps)
    m.crear(cfg_iso(etiquetas=ETIQUETAS_LOTE))
    return _traza(m.cl)


def _importar(rsps: Any) -> list[list[str]]:
    m = _Mundo(rsps)
    m.crear(cfg_import(cfg={"etiquetas": ETIQUETAS_LOTE}, ampliar_a_gib=64))
    return _traza(m.cl)


def _clon(rsps: Any, **kw: Any) -> list[list[str]]:
    m = _Mundo(rsps)
    m.crear(m.clon(**kw))
    return _traza(m.cl)


def _lote_encender(rsps: Any) -> list[list[str]]:
    cl = ClusterA(("pve1",))
    banco = crear_banco_http(rsps, ("pve1",), cluster=cl)
    banco.inv = inv_con(catalogo())
    plan = plan_de(banco, def_lote(3, plantilla_vm=cfg_vm(encender=True)))
    cl.trazas.clear()
    banco.ejecutar(plan)
    return _traza(cl, por_mv=True)


def _reintento(rsps: Any) -> list[list[str]]:
    m = _Mundo(rsps)
    m.cl.regla("PUT", r"/qemu/100/config$", lambda _ll: Http(500, "fallo de prueba"), veces=1)
    cfg = m.clon(ajustes=AjustesClon(cores=4, memoria_mib=4096), encender=True)
    m.crear(cfg)
    servicio = ServicioCreacion(m.banco.sesion, m.banco.reloj, intervalo_s=0.01)
    servicio.reintentar_ajustes(cfg, m.inv, threading.Event())
    return _traza(m.cl)


def _deshacer(rsps: Any) -> list[list[str]]:
    cl = ClusterA(("pve1",))
    banco = crear_banco_http(rsps, ("pve1",), cluster=cl)
    banco.inv = inv_con(catalogo())
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_vm(), vmid_inicial=100))
    libro = banco.ejecutar(plan)
    cl.trazas.clear()
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    candidatos = servicio.elegibles(libro, etiquetado=True)
    todas = frozenset(c.entrada.elemento.vmid for c in candidatos)
    servicio.deshacer(
        candidatos,
        lambda _r: None,
        ControlLote(),
        id_lote=libro.id_lote,
        etiquetado=True,
        forzar_apagado=todas,
        forzar_desproteccion=todas,
        permisos=None,
    )
    return _traza(cl, por_mv=True)


def _sim(res: Any) -> list[Any]:
    """Simulación: ``peticiones`` y ``peticiones_detalle`` por VMID, con el orden de las claves.

    ``simular`` genera un id de lote aleatorio (no admite inyectarlo): se normaliza en la etiqueta.
    """
    datos = [
        {str(v): p for v, p in res.peticiones.items()},
        {
            str(v): [[d.accion.value, d.nodo, dict(d.parametros)] for d in ds]
            for v, ds in res.peticiones_detalle.items()
        },
    ]
    texto = re.sub(r"lote-[0-9a-f]{8}", "lote-XXXXXXXX", json.dumps(datos))
    return json.loads(texto)


def _simulacion_vacio(rsps: Any) -> list[Any]:
    cl = ClusterA(("pve1",))
    banco = crear_banco_http(rsps, ("pve1",), cluster=cl)
    banco.inv = inv_con(catalogo())
    res = simular(
        banco.sesion,
        def_lote(2, plantilla_vm=cfg_vm(encender=True)),
        banco.inv,
        reloj=banco.reloj,
    )
    assert not res.plan.bloqueado, res.plan.problemas
    assert cl.solo_lecturas
    return _sim(res)


def _simulacion_clon(rsps: Any) -> list[Any]:
    m = _Mundo(rsps)
    base = dataclasses.replace(
        cfg_clon("base", ajustes=AjustesClon(cores=4, disco_gib=64)),
        encender=True,
        arranque_auto=True,
        discos=cfg_vm().discos,
        redes=cfg_vm().redes,
    )
    res = simular(m.banco.sesion, def_lote(2, plantilla_vm=base), m.inv, reloj=m.banco.reloj)
    assert not res.plan.bloqueado, res.plan.problemas
    assert m.cl.solo_lecturas
    assert AccionPeticion.CLONAR in {d.accion for ds in res.peticiones_detalle.values() for d in ds}
    return _sim(res)


def escenarios() -> dict[str, Any]:
    """``{nombre: secuencia}``. Las claves y listas conservan el orden de las peticiones."""
    return {
        "vacio": _en_http(_vacio),
        "vacio_encender": _en_http(lambda r: _vacio(r, encender=True)),
        "iso": _en_http(_iso),
        "importar_con_resize": _en_http(_importar),
        "clon_sin_ajustes": _en_http(_clon),
        "clon_con_ajustes": _en_http(
            lambda r: _clon(
                r,
                ajustes=AjustesClon(cores=4, memoria_mib=4096, disco_gib=64),
                encender=True,
                arranque_auto=True,
            )
        ),
        "lote_3_encender": _en_http(_lote_encender),
        "reintento_de_ajustes": _en_http(_reintento),
        "deshacer_2": _en_http(_deshacer),
        "simulacion_lote_vacio": _en_http(_simulacion_vacio),
        "simulacion_lote_clon": _en_http(_simulacion_clon),
    }


@functools.cache
def actuales() -> dict[str, Any]:
    """Los escenarios ejecutados con el código actual (una sola vez por sesión de pruebas)."""
    return escenarios()


def golden() -> dict[str, Any]:
    """Las instantáneas generadas con el código de la etiqueta ``v0.6.0``."""
    return json.loads(RUTA_GOLDEN.read_text(encoding="utf-8"))


def generar(salida: str | Path = RUTA_GOLDEN) -> None:
    """Escribe los escenarios como JSON (claves en orden de inserción)."""
    import proxlaunch

    datos = {"version_codigo": proxlaunch.__version__, "escenarios": escenarios()}
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(
        json.dumps(datos, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )
