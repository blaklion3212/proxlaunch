"""MVP 4: pruebas que cierran la trazabilidad de requisitos del núcleo (RF/V/E/INV-O).

Cada prueba cita el requisito; los textos y la accesibilidad son de la interfaz.
"""

import threading

import pytest

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.constantes import MAX_LOTE
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.origen import DetalleIso, RefVolumen
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.modelos.vm import Disco, Firmware
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, Via, calcular_capacidades
from proxlaunch.nucleo.origen.storages import TipoDecision, decidir_storage
from proxlaunch.nucleo.origen.validacion_origen import validar_origen
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_lote import RelojSeguro, TransporteCluster, crear_banco, definicion, storage
from .apoyo_mvp4 import (
    VOLID_ISO,
    ClusterM4,
    cfg_import,
    cfg_iso,
    inv_origen,
    listado,
    permisos,
)

CAPS = capacidades_para(Version("9.2", 9, 2, 0), None)


def test_v_o08_el_tpm_exige_un_storage_con_images_activo_para_el_estado():
    """Con SeaBIOS (V-17 no aplica) y un storage de efidisk sin `images`, V-O08 bloquea."""
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    cfg = cfg_iso(
        firmware=Firmware.SEABIOS, tpm=True, storage_efi="local"
    )  # «local» no tiene images
    inv.storages["pve1"] = tuple(s for s in inv.storages["pve1"] if s.id != "local")
    problemas = validar_origen(cfg, inv, CAPS)
    p = [x for x in problemas if x.codigo == "V-O08"]
    assert p and p[0].severidad == Severidad.ERROR and p[0].campo == "storage_efi"
    ok = cfg_iso(firmware=Firmware.SEABIOS, tpm=True, storage_efi="local-lvm")
    assert not [x for x in validar_origen(ok, inv_origen(), CAPS) if x.codigo == "V-O08"]


def test_v_o26_un_storage_recordado_ausente_bloquea_si_el_origen_lo_necesita():
    """CA-O06.3: la decisión no elige otro y deja `storage=None`; quien la use no genera resumen."""
    inv = inv_origen()
    d = decidir_storage(inv, Contenido.ISO, "pve1", "borrado")
    assert d.tipo == TipoDecision.RECORDADO_NO_DISPONIBLE and d.storage is None  # E-O04


def test_v_o30_n_mayor_que_max_lote_se_rechaza_tambien_con_origen():
    banco = crear_banco(("pve1",), inv=inv_origen(nodos=("pve1",)), cluster=_cluster_con_iso())
    plan = banco.planificar(_lote_iso(MAX_LOTE + 1))
    assert plan.elementos == () and any(p.severidad == Severidad.ERROR for p in plan.problemas)
    ok = banco.planificar(_lote_iso(2))
    assert len(ok.elementos) == 2


def _cluster_con_iso():
    cl = ClusterM4(("pve1",))
    cl.contenido[("pve1", "local")] = [VOLID_ISO]
    return cl


def _lote_iso(n):
    plant = cfg_iso(None, vmid=0, nombre="plantilla", nodo="", discos=[Disco("local-lvm", 8)])
    plant.detalle_origen = DetalleIso(iso=RefVolumen("alpine.iso"))
    return definicion(n, plantilla_vm=plant)


def test_inv_o9_nada_del_origen_llega_a_proxmox_sin_validacion_completa():
    """Un ISO sin volid resuelto o un tipo de SO ausente no llega al POST."""
    cl = ClusterM4(("pve1",))
    reloj = RelojSeguro()
    from .apoyo_api import crear_sesion

    sesion = crear_sesion(TransporteCluster(cl), reloj=reloj)
    inv = inv_origen(nodos=("pve1",))
    servicio = ServicioCreacion(sesion, reloj, intervalo_s=0.01)
    for cfg in (cfg_iso(None), cfg_iso(tipo_so=None), cfg_import(None)):
        r = servicio.crear(cfg, inv, lambda e: None, threading.Event())
        assert r.desenlace == Desenlace.ERROR and r.error.codigo == CodigoError.PARAMETRO_INVALIDO
    assert cl.posts == {} and cl.metodos.get("POST", 0) == 0


def test_rf_o15_importar_no_se_intenta_sin_storage_import_ni_sin_permiso():
    """RF-O15 (E-O02/E-O12): la importación solo se ofrece cuando se cumplen ambas.

    E-O01 (versión) quedó sin productor con la mínima 8.4 de 0.9.0 (DT-D3)."""
    sin_import = inv_origen()
    sin_import.storages_todos = {
        n: tuple(s for s in sts if "import" not in s.contenido) or (storage("x", "dir", 1),)
        for n, sts in sin_import.storages_todos.items()
    }
    minima = calcular_capacidades(
        capacidades_para(Version("8.4", 8, 4, 0), None), inv_origen(), None
    )
    assert minima.estado(Via.IMPORTAR).disponibilidad == Disponibilidad.SI
    nuevo = calcular_capacidades(CAPS, sin_import, None)
    assert nuevo.estado(Via.IMPORTAR).codigo == CodigoError.IMPORTAR_SIN_STORAGE_IMPORT
    sin_permiso = inv_origen(permisos_efectivos=permisos(privilegios=("VM.Audit",)))
    assert calcular_capacidades(CAPS, sin_permiso, None).estado(Via.IMPORTAR).codigo == (
        CodigoError.IMPORTAR_SIN_PERMISO
    )
    assert calcular_capacidades(CAPS, inv_origen(), None).estado(Via.IMPORTAR).disponibilidad == (
        Disponibilidad.SI
    )


def test_rf_o29_v_o22_la_validacion_de_un_lote_con_origen_reutiliza_las_reglas_de_m1_a_m3():
    """RF-O29/V-O22: un lote con ISO pasa por el planificador de M2 completo (VMIDs, reparto)."""
    banco = crear_banco(("pve1",), inv=inv_origen(nodos=("pve1",)), cluster=_cluster_con_iso())
    plan = banco.planificar(_lote_iso(3))
    assert [e.vmid for e in plan.elementos] == [100, 101, 102]
    assert {e.cfg.detalle_origen.iso.volid for e in plan.elementos} == {VOLID_ISO}
    assert plan.catalogo is not None and plan.catalogo.listados  # catálogo del plan (V-L14)


def test_rnf_o14_la_verificacion_posterior_compara_el_tamano_y_el_checksum_va_antes(tmp_path):
    """RNF-O14: el sha256 se calcula antes de enviar y el tamaño se verifica después (E-O06)."""
    from .test_mvp4_transferencias import DESTINO, _Mundo

    m = _Mundo(tmp_path)
    m.subir()
    posiciones = [i for i, c in enumerate(m.srv.llamadas) if c.metodo == "POST"]
    assert posiciones and all(c.metodo == "GET" for c in m.srv.llamadas[: posiciones[0]])
    assert any("/content" in c.ruta for c in m.srv.llamadas[posiciones[0] :])  # verificación
    assert DESTINO.nombre_archivo in m.srv.contenido[("pve1", "local")]


@pytest.mark.parametrize(
    ("destino", "formato"), [("local", "qcow2"), ("local-lvm", None), (None, None)]
)
def test_v_o22_el_formato_del_clon_completo_solo_va_donde_v_09_lo_permite(destino, formato):
    """V-O22: `format` solo en clon completo y según el storage destino."""
    from proxlaunch.nucleo.modelos.origen import ModoClon
    from proxlaunch.nucleo.origen.clon import construir_peticion_clon
    from proxlaunch.nucleo.origen.resolucion import resolver_origen

    from .apoyo_mvp4 import cfg_clon, plantilla_pve

    inv = inv_origen(plantillas=(plantilla_pve(),))
    cfg, _ = resolver_origen(
        cfg_clon("base", modo=ModoClon.COMPLETO, storage_destino=destino), inv, "pve1"
    )
    assert construir_peticion_clon(cfg, inv).parametros.get("format") == formato
    enlazado, _ = resolver_origen(cfg_clon("base"), inv, "pve1")
    assert "format" not in construir_peticion_clon(enlazado, inv).parametros
