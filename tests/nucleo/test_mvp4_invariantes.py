"""MVP 4: invariantes de seguridad del núcleo (INV-O1, INV-O3, INV-O4, INV-O12) y no regresión.

Requisitos: INV-O3 (PUT idempotentes, solo sobre MVs del libro), INV-O4 (el núcleo no borra ISOs,
imágenes ni plantillas, no usa Datastore.Allocate ni Sys.Modify), INV-O12 (simulación solo con
lecturas), CA-O30.3 (rollback solo borra MVs), CA-O03.1 (equivalencia con M3), RNF-O10 (sin red).
"""

import io

import pytest

from proxlaunch.nucleo.api.multipart import ParteArchivo
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoRollback
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.modelos.origen import DetalleIso, RefVolumen
from proxlaunch.nucleo.modelos.vm import Disco
from proxlaunch.nucleo.transferencias.url import validar_url
from proxlaunch.nucleo.validacion import CODIGOS_SIN_SERVIDOR

from .apoyo_api import TransporteFalso, crear_sesion
from .apoyo_lote import crear_banco, definicion
from .apoyo_mvp4 import (
    VOLID_ISO,
    ClusterM4,
    cfg_clon,
    cfg_iso,
    inv_origen,
)


def test_inv_o12_el_cliente_de_solo_lectura_rechaza_cada_escritura_nueva_antes_de_la_red():
    t = TransporteFalso()
    ro = crear_sesion(t).cliente.solo_lectura()
    url, _ = validar_url("https://dl.example.org/a.iso", permitir_http=False)
    from proxlaunch.nucleo.modelos.catalogo import Contenido

    escrituras = [
        lambda: ro.clonar_vm("pve1", 9000, {"newid": "100", "name": "x"}),
        lambda: ro.configurar_vm("pve1", 100, {"cores": "4"}),
        lambda: ro.ampliar_disco("pve1", 100, "scsi0", 20),
        lambda: ro.descargar_url(
            "pve1", "local", url=url, contenido=Contenido.ISO, nombre="a.iso", checksum=None
        ),
        lambda: ro.crear_vm("pve1", {"vmid": "100"}),
    ]
    for escribir in escrituras:
        with pytest.raises(ErrorProxLaunch) as e:
            escribir()
        assert e.value.codigo == CodigoError.ESCRITURA_EN_SIMULACION
    assert t.llamadas == []  # nada llegó al transporte


def test_inv_o12_la_subida_en_simulacion_se_rechaza_sin_leer_un_byte_del_archivo():
    leidos = []

    class Flujo(io.BytesIO):
        def read(self, n=-1):
            leidos.append(n)
            return super().read(n)

    class Transporte(TransporteFalso):
        def subir(self, ruta, cuerpo, *, timeout_lectura):  # pragma: no cover - no debe llamarse
            raise AssertionError("no debe llegar al transporte real")

    ro = crear_sesion(Transporte()).cliente.solo_lectura()
    from proxlaunch.nucleo.modelos.catalogo import Contenido

    with pytest.raises(ErrorProxLaunch) as e:
        ro.subir_archivo(
            "pve1", "local", Contenido.ISO, ParteArchivo("a.iso", 5, Flujo(b"datos")), "ab" * 32
        )
    assert e.value.codigo == CodigoError.ESCRITURA_EN_SIMULACION and leidos == []


def test_inv_o4_los_codigos_de_capa_1_incluyen_los_del_origen_y_ya_no_v_20():
    assert "V-20" not in CODIGOS_SIN_SERVIDOR
    for codigo in ("V-O01", "V-O05", "V-O06", "V-O07", "V-O23", "V-O24", "V-O29"):
        assert codigo in CODIGOS_SIN_SERVIDOR, codigo


def test_inv_o4_ninguna_clase_del_cliente_expone_borrado_de_archivos_o_plantillas():
    from proxlaunch.nucleo.api.cliente import ClienteProxmox

    publicos = {n for n in dir(ClienteProxmox) if not n.startswith("_")}
    borrados = {n for n in publicos if "borrar" in n or "eliminar" in n or "delete" in n}
    assert borrados == {"eliminar_vm"}  # solo el rollback de MVs (D-21)
    for prohibido in (
        "convertir_en_plantilla",
        "activar_contenido",
        "borrar_iso",
        "borrar_volumen",
    ):
        assert prohibido not in publicos


def test_ca_o30_3_el_rollback_de_isos_solo_borra_mvs_y_deja_los_archivos_intactos():
    cl = ClusterM4(("pve1",))
    cl.contenido[("pve1", "local")] = [VOLID_ISO]
    banco = crear_banco(("pve1",), inv=inv_origen(nodos=("pve1",)), cluster=cl)
    plant = cfg_iso(None, vmid=0, nombre="plantilla", nodo="", discos=[Disco("local-lvm", 8)])
    plant.detalle_origen = DetalleIso(iso=RefVolumen("alpine.iso"))
    plan = banco.planificar(definicion(2, plantilla_vm=plant))
    libro = banco.ejecutar(plan)
    rb = ServicioRollback(banco.sesion, banco.reloj, intervalo_s=0.01)
    candidatos = rb.elegibles(libro, etiquetado=True)
    resultados = rb.deshacer(
        candidatos, lambda r: None, ControlLote(), id_lote=plan.id_lote, etiquetado=True
    )
    assert [r.estado for r in resultados] == [EstadoRollback.ELIMINADA] * 2
    borrados = [c for c in cl.llamadas if c.metodo == "DELETE"]
    assert len(borrados) == 2 and all(c.ruta.endswith(("/100", "/101")) for c in borrados)
    assert cl.contenido[("pve1", "local")] == [VOLID_ISO]  # el ISO sigue en el storage
    assert not any("/storage/" in c.ruta and c.metodo != "GET" for c in cl.llamadas)


def test_inv_o3_un_clon_reintentado_con_put_no_repite_valores_relativos():
    """Los PUT son idempotentes: tamaño absoluto («20G»), nunca «+10G»."""
    cl = ClusterM4(("pve1",))
    cl.agregar_plantilla(9000, "base", "pve1")
    banco = crear_banco(("pve1",), inv=inv_origen(nodos=("pve1",)), cluster=cl)
    from proxlaunch.nucleo.modelos.origen import AjustesClon

    plant = cfg_clon("base", vmid=0, nombre="plantilla", nodo="", discos=[], redes=[],
                     ajustes=AjustesClon(disco_gib=20))  # fmt: skip
    libro = banco.ejecutar(banco.planificar(definicion(2, plantilla_vm=plant)))
    resizes = [p for p in cl.puts if p[2] == "resize"]
    assert len(resizes) == 2 and all(p[3]["size"] == "20G" for p in resizes)
    assert all(not str(v).startswith("+") for p in cl.puts for v in p[3].values())
    assert {e.estado.value for e in libro.instantanea()} == {"ok"}


def test_inv_o3_las_escrituras_posteriores_solo_van_a_mvs_del_libro():
    cl = ClusterM4(("pve1",))
    cl.agregar_plantilla(9000, "base", "pve1")
    cl.agregar_vm(555, "pve1", "ajena")
    banco = crear_banco(("pve1",), inv=inv_origen(nodos=("pve1",)), cluster=cl)
    plant = cfg_clon("base", vmid=0, nombre="plantilla", nodo="", discos=[], redes=[])
    libro = banco.ejecutar(banco.planificar(definicion(3, plantilla_vm=plant)))
    del_libro = {e.elemento.vmid for e in libro.instantanea()}
    assert {vmid for _, vmid, _, _ in cl.puts} <= del_libro
    assert 555 not in {vmid for _, vmid, _, _ in cl.puts}


def test_rnf_o10_la_suite_normal_no_abre_sockets():
    import socket

    from pytest_socket import SocketBlockedError

    with pytest.warns(UserWarning), pytest.raises(SocketBlockedError):
        socket.create_connection(("192.0.2.1", 8006), timeout=0.1)
