"""Escenarios de las instantáneas («golden») de 0.8.0 para la fase D (CA-D0.2.1 a CA-D0.2.4,
CA-D2.4.3, CA-D2.6.6, CA-D6.1.2). Sin aserciones.

Cada escenario ejecuta el código REAL (servicio de creación, motor, Deshacer, simulación) sobre el
transporte HTTP real contra el clúster simulado (``responses``) y recoge la secuencia COMPLETA de
ESCRITURAS recibidas (método, ruta, consulta y cuerpo del formulario en bytes). Con las opciones de
la fase D por defecto y el nodo x86_64, 0.9.0 debe producir exactamente lo mismo que 0.8.0 sobre un
servidor 8.4 y sobre uno 9.2. Las lecturas quedan fuera: el descubrimiento de 0.9.0 lee más.

Este módulo SOLO usa API que existe igual en 0.8.0 y en 0.9.0: así se ejecuta contra el código de
la etiqueta ``v0.8.0`` para generar ``tests/datos/fase_d/golden_v080.json`` y contra 0.9.0 para
compararlo. ``escenarios(version)`` recibe ``"8.4"`` o ``"9.2"``; ``generar`` escribe ambos.

Regenerar (desde la raíz del repositorio, sin tocar el árbol de trabajo)::

    git archive v0.8.0 src | tar -x -C <carpeta_temporal>
    .venv/bin/python -c "import sys; sys.path[:0] = ['<carpeta_temporal>/src', '.']; \\
        from tests.nucleo.apoyo_golden_fase_d import generar; generar('<salida.json>')"

(``generar`` comprueba que ``proxlaunch`` sale de la carpeta temporal y no del árbol de trabajo).
"""

from __future__ import annotations

import dataclasses
import functools
import json
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import responses

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.lote.modelos import AccionPeticion
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.lotes_guardados.formato import leer_archivo_lote
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.origen import AjustesClon, TipoSO
from proxlaunch.nucleo.modelos.vm import Disco, Firmware
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_fase_a import ClusterA, catalogo, cfg_vm, def_lote, inv_con, plan_de
from .apoyo_fase_b_p1 import MundoB, ci
from .apoyo_fase_c_firewall import MundoC as MundoFirewall
from .apoyo_fase_c_firewall import fw_defecto
from .apoyo_fase_c_red import MundoC as MundoRed
from .apoyo_fase_c_red import cambiar, cfg_con_red, red_clon
from .apoyo_lote import Http, crear_banco_http
from .apoyo_mvp4 import (
    VOLID_IMAGEN,
    VOLID_ISO,
    VOLID_VIRTIO,
    cfg_clon,
    cfg_import,
    cfg_iso,
    inv_origen,
    plantilla_pve,
)

_RAIZ = Path(__file__).resolve().parents[1] / "datos"
RUTA_GOLDEN = _RAIZ / "fase_d" / "golden_v080.json"
VERSIONES = {"8.4": Version("8.4.1", 8, 4, 1), "9.2": Version("9.2.1", 9, 2, 1)}
ETIQUETAS_LOTE = ("proxlaunch", "lote-ab12cd34")
# Lotes guardados de 0.5.1 a 0.8.0 que ya están en el repositorio de pruebas (formatos 1 a 5).
LOTES_GUARDADOS = (
    "fase_a_p2/lote-homogeneo-051-v1.json",
    "fase_a_p2/lote-homogeneo-051-v2.json",
    "fase_a_p2/lote-por-filas-051-v2.json",
    "fase_b/p2_lote-homogeneo-060-v3.json",
    "fase_b/p2_lote-por-filas-060-v3.json",
    "fase_c/p4_lote-homogeneo-070-v1.json",
    "fase_c/p4_lote-homogeneo-070-v4.json",
    "fase_c/p4_lote-por-filas-070-v4.json",
)

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


def _escrituras(cl: ClusterA, *, por_mv: bool = False) -> list[list[str]]:
    """ESCRITURAS recibidas como ``[método, ruta?consulta, cuerpo]`` (no los ``GET``)."""
    trazas = [t for t in cl.trazas if t[0] != "GET"]
    filas = [
        [m, ruta + (f"?{q}" if q else ""), cuerpo.decode("ascii")] for m, ruta, q, cuerpo in trazas
    ]
    if not por_mv:
        return filas
    claves = [_grupo(m, ruta, q, c.decode("ascii")) for m, ruta, q, c in trazas]
    orden = sorted(range(len(filas)), key=lambda i: (claves[i], i))
    return [filas[i] for i in orden]


# Gancho de las pruebas de 0.9.0: recibe cada inventario y le fija la arquitectura de los nodos
# (en 0.8.0 no existe, así que el generador no lo usa). ``None`` = el inventario tal cual.
GANCHO_INVENTARIO: Callable[[Any], None] | None = None


def _poner_version(sesion: Any, inv: Any, version: Version) -> None:
    sesion.version = version
    sesion.capacidades = capacidades_para(version, None)
    inv.version = version
    if GANCHO_INVENTARIO is not None:
        GANCHO_INVENTARIO(inv)


class _Mundo:
    """Clúster ``ClusterA`` servido por HTTP real, con una plantilla (9000) y un servicio."""

    def __init__(self, rsps: Any, version: Version, **inv_kw: Any) -> None:
        self.version = version
        self.cl = ClusterA(("pve1",))
        self.cl.agregar_plantilla(9000, "base", "pve1", tags="plantilla", cores=2, memory=2048)
        self.cl.contenido[("pve1", "local")] = [VOLID_ISO, VOLID_IMAGEN, VOLID_VIRTIO]
        self.banco = crear_banco_http(rsps, ("pve1",), cluster=self.cl)
        det = detalle_de_config(self.cl.plantillas[9000]["config"])
        inv_kw.setdefault("nodos", ("pve1",))
        inv_kw.setdefault("privilegios", (*ROL_PROXLAUNCH, "VM.PowerMgmt", "Pool.Audit"))
        self.inv = inv_origen(
            plantillas=(plantilla_pve(9000, "base", "pve1", detalle=det),),
            version=version,
            **inv_kw,
        )
        self.banco.inv = self.inv
        _poner_version(self.banco.sesion, self.inv, version)

    def crear(self, cfg: Any) -> Any:
        servicio = ServicioCreacion(self.banco.sesion, self.banco.reloj, intervalo_s=0.01)
        return servicio.crear(cfg, self.inv, lambda _e: None, threading.Event())

    def clon(self, **kw: Any) -> Any:
        kw.setdefault("etiquetas", ETIQUETAS_LOTE)
        cfg, problemas = resolver_origen(cfg_clon("base", **kw), self.inv, "pve1")
        assert problemas == [], problemas
        return cfg


Escenario = Callable[[Any, Version], Any]


def _en_http(escenario: Escenario, version: Version) -> Any:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        return escenario(rsps, version)


# --- Escenarios ---------------------------------------------------------------------------------


def _vacio(rsps: Any, version: Version, **cambios: Any) -> list[list[str]]:
    m = _Mundo(rsps, version)
    m.banco.inv = m.inv = inv_con(catalogo(), version=version)
    _poner_version(m.banco.sesion, m.inv, version)
    m.crear(cfg_vm(**cambios))
    return _escrituras(m.cl)


def _iso(rsps: Any, version: Version, **cambios: Any) -> list[list[str]]:
    m = _Mundo(rsps, version)
    m.crear(cfg_iso(etiquetas=ETIQUETAS_LOTE, **cambios))
    return _escrituras(m.cl)


def _iso_windows_tpm(rsps: Any, version: Version) -> list[list[str]]:
    return _iso(
        rsps,
        version,
        tipo_so=TipoSO.WINDOWS_11,
        firmware=Firmware.OVMF,
        tpm=True,
        memoria_mib=8192,
        drivers=VOLID_VIRTIO,
    )


def _importar(rsps: Any, version: Version, **det: Any) -> list[list[str]]:
    m = _Mundo(rsps, version)
    m.crear(cfg_import(cfg={"etiquetas": ETIQUETAS_LOTE}, **det))
    return _escrituras(m.cl)


def _importar_dos_discos(rsps: Any, version: Version) -> list[list[str]]:
    m = _Mundo(rsps, version)
    cfg = cfg_import(cfg={"etiquetas": ETIQUETAS_LOTE})
    cfg = dataclasses.replace(cfg, discos=[Disco("local-lvm", 32), Disco("local-lvm", 16)])
    m.crear(cfg)
    return _escrituras(m.cl)


def _clon(rsps: Any, version: Version, **kw: Any) -> list[list[str]]:
    m = _Mundo(rsps, version)
    m.crear(m.clon(**kw))
    return _escrituras(m.cl)


def _clon_cloudinit(rsps: Any, version: Version) -> list[list[str]]:
    m = MundoB(rsps=rsps, version=version)
    _poner_version(m.sesion, m.inv, version)
    m.crear(m.cfg(ci(), etiquetas=ETIQUETAS_LOTE))
    return _escrituras(m.cl)


def _clon_red(rsps: Any, version: Version) -> list[list[str]]:
    m = MundoRed(rsps=rsps, version=version)
    _poner_version(m.sesion, m.inv, version)
    m.crear(cfg_con_red(m, red_clon(cambiar(0, bridge="vmbr0", vlan=30)), etiquetas=ETIQUETAS_LOTE))
    return _escrituras(m.cl)


def _clon_firewall(rsps: Any, version: Version) -> list[list[str]]:
    m = MundoFirewall(rsps=rsps, version=version)
    _poner_version(m.sesion, m.inv, version)
    m.crear(dataclasses.replace(m.cfg(etiquetas=ETIQUETAS_LOTE), firewall=fw_defecto()))
    return _escrituras(m.cl)


def _asistente_imagen(rsps: Any, version: Version) -> list[list[str]]:
    """Creación de la plantilla del asistente de imagen cloud (``cfg_de_creacion`` + extras)."""
    from proxlaunch.nucleo.plantilla_imagen.modelos import OrigenImagen
    from proxlaunch.nucleo.plantilla_imagen.peticion import cfg_de_creacion, parametros_extra

    from .apoyo_fase_b_agente import solicitud

    m = _Mundo(rsps, version)
    sol = solicitud(
        None,
        origen=OrigenImagen.YA_IMPORTADA,
        volid_existente=VOLID_IMAGEN,
        nombre_archivo=VOLID_IMAGEN.partition("/")[2],
        tamano_virtual_bytes=2 * 1024**3,
    )
    cfg = cfg_de_creacion(sol, VOLID_IMAGEN)
    servicio = ServicioCreacion(m.banco.sesion, m.banco.reloj, intervalo_s=0.01)
    servicio.crear(
        cfg,
        m.inv,
        lambda _e: None,
        threading.Event(),
        parametros_extra=parametros_extra(sol.fijas, sol.storage_destino),
    )
    return _escrituras(m.cl)


def _lote_encender(rsps: Any, version: Version) -> list[list[str]]:
    cl = ClusterA(("pve1",))
    banco = crear_banco_http(rsps, ("pve1",), cluster=cl)
    banco.inv = inv_con(catalogo(), version=version)
    _poner_version(banco.sesion, banco.inv, version)
    plan = plan_de(banco, def_lote(3, plantilla_vm=cfg_vm(encender=True)))
    cl.trazas.clear()
    banco.ejecutar(plan)
    return _escrituras(cl, por_mv=True)


def _reintento(rsps: Any, version: Version) -> list[list[str]]:
    m = _Mundo(rsps, version)
    m.cl.regla("PUT", r"/qemu/100/config$", lambda _ll: Http(500, "fallo de prueba"), veces=1)
    cfg = m.clon(ajustes=AjustesClon(cores=4, memoria_mib=4096), encender=True)
    m.crear(cfg)
    servicio = ServicioCreacion(m.banco.sesion, m.banco.reloj, intervalo_s=0.01)
    servicio.reintentar_ajustes(cfg, m.inv, threading.Event())
    return _escrituras(m.cl)


def _deshacer(rsps: Any, version: Version) -> list[list[str]]:
    cl = ClusterA(("pve1",))
    banco = crear_banco_http(rsps, ("pve1",), cluster=cl)
    banco.inv = inv_con(catalogo(), version=version)
    _poner_version(banco.sesion, banco.inv, version)
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
    return _escrituras(cl, por_mv=True)


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


def _simulacion_vacio(rsps: Any, version: Version) -> list[Any]:
    cl = ClusterA(("pve1",))
    banco = crear_banco_http(rsps, ("pve1",), cluster=cl)
    banco.inv = inv_con(catalogo(), version=version)
    _poner_version(banco.sesion, banco.inv, version)
    res = simular(
        banco.sesion,
        def_lote(2, plantilla_vm=cfg_vm(encender=True)),
        banco.inv,
        reloj=banco.reloj,
    )
    assert not res.plan.bloqueado, res.plan.problemas
    assert cl.solo_lecturas
    return _sim(res)


def _simulacion_clon(rsps: Any, version: Version) -> list[Any]:
    m = _Mundo(rsps, version)
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


def _simulacion_lote_guardado(rsps: Any, version: Version, ruta: str) -> list[Any]:
    cl = ClusterA(("pve1",))
    banco = crear_banco_http(rsps, ("pve1",), cluster=cl)
    banco.inv = inv_con(catalogo(), version=version)
    _poner_version(banco.sesion, banco.inv, version)
    definicion = leer_archivo_lote(_RAIZ / ruta).lote.definicion
    res = simular(banco.sesion, definicion, banco.inv, reloj=banco.reloj)
    return _sim(res)


def escenarios(version: str) -> dict[str, Any]:
    """``{nombre: secuencia}`` para la versión ``"8.4"`` o ``"9.2"``. Conservan el orden."""
    v = VERSIONES[version]
    nombres: dict[str, Escenario] = {
        "vacio": _vacio,
        "vacio_encender": lambda r, ver: _vacio(r, ver, encender=True),
        "iso": _iso,
        "iso_windows_tpm_ovmf": _iso_windows_tpm,
        "importar_con_resize": lambda r, ver: _importar(r, ver, ampliar_a_gib=64),
        "importar_sin_resize": lambda r, ver: _importar(r, ver),
        "importar_dos_discos_sin_imagen": _importar_dos_discos,
        "clon_sin_ajustes": lambda r, ver: _clon(r, ver),
        "clon_con_ajustes": lambda r, ver: _clon(
            r,
            ver,
            ajustes=AjustesClon(cores=4, memoria_mib=4096, disco_gib=64),
            encender=True,
            arranque_auto=True,
        ),
        "clon_cloudinit": _clon_cloudinit,
        "clon_red_del_clon": _clon_red,
        "clon_firewall": _clon_firewall,
        "asistente_imagen_cloud": _asistente_imagen,
        "lote_3_encender": _lote_encender,
        "reintento_de_ajustes": _reintento,
        "deshacer_2": _deshacer,
        "simulacion_lote_vacio": _simulacion_vacio,
        "simulacion_lote_clon": _simulacion_clon,
    }
    for ruta in LOTES_GUARDADOS:
        nombres[f"simulacion_guardado_{Path(ruta).stem}"] = functools.partial(
            lambda r, ver, ruta_: _simulacion_lote_guardado(r, ver, ruta_), ruta_=ruta
        )  # type: ignore[assignment]
    return {nombre: _en_http(esc, v) for nombre, esc in nombres.items()}


@functools.cache
def actuales(version: str) -> dict[str, Any]:
    """Los escenarios ejecutados con el código actual (una sola vez por sesión de pruebas)."""
    return escenarios(version)


def golden() -> dict[str, Any]:
    """Las instantáneas generadas con el código de la etiqueta ``v0.8.0``."""
    return json.loads(RUTA_GOLDEN.read_text(encoding="utf-8"))


def generar(salida: str | Path = RUTA_GOLDEN) -> None:
    """Escribe los escenarios de 8.4 y 9.2 como JSON (claves en orden de inserción)."""
    import proxlaunch

    if proxlaunch.__version__ != "0.8.0":
        raise RuntimeError("las instantáneas se generan con el código de la etiqueta v0.8.0")

    datos = {
        "version_codigo": proxlaunch.__version__,
        "versiones": {v: escenarios(v) for v in VERSIONES},
    }
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(
        json.dumps(datos, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )
