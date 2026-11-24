"""D1.7: varios discos, una imagen por disco (RF-D1.7, CL-D6, DT-D14).

Derivadas de docs/requisitos/fase-d.md: CA-D1.7.1 a CA-D1.7.9 y RF-D0.2 (CA-D0.2.4: un solo
disco = petición de 0.8.0). La petición se construye con ``construir_parametros`` y el espacio con
``pedido_vm``/``construir_plan``; no se mira cómo lo hacen por dentro.
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import PoliticaThin
from proxlaunch.nucleo.lote.presupuesto import evaluar_espacio, pedido_vm, uso_de_nodos
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, ImagenDisco, RefVolumen
from proxlaunch.nucleo.modelos.vm import Bus, Disco
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_fase_d_libvirt import (
    disco_xml,
    dominio_desde_texto,
    fila,
    inventario_d,
    proponer_de,
    xml_minimo,
)
from .apoyo_lote import definicion
from .apoyo_mvp4 import VOLID_IMAGEN, cfg_import, inv_origen
from .test_lote_presupuesto import _plan

GIB = 1024**3
CAPS = capacidades_para(Version("9.2", 9, 2, 0), None)
INV = inv_origen()


def _ref(nombre: str) -> RefVolumen:
    return RefVolumen(nombre, f"local:import/{nombre}")


def _cfg(n: int = 3, *, vacios: tuple[int, ...] = (), pendientes: tuple[int, ...] = (), **kw):
    """``n`` discos scsi; el 0 y los demás con imagen ``d<i>.qcow2`` salvo los pendientes/vacíos."""
    otras = []
    for i in range(1, n):
        if i in vacios:
            otras.append(ImagenDisco(i, None, crear_vacio=True))
        elif i in pendientes:
            otras.append(ImagenDisco(i))
        else:
            otras.append(ImagenDisco(i, _ref(f"d{i}.qcow2"), tamano_virtual_bytes=(10 + i) * GIB))
    discos = [Disco("local-lvm", 8 + i) for i in range(n)]
    return cfg_import(
        "local:import/d0.qcow2",
        cfg={"discos": discos},
        tamano_virtual_bytes=10 * GIB,
        otras=tuple(otras),
        **kw,
    )


def _errores(cfg) -> list[tuple[str, dict[str, str]]]:
    return [
        (p.codigo, p.params)
        for p in validar_vm(cfg, INV, CAPS)
        if p.severidad == Severidad.ERROR and p.codigo.startswith("V-D")
    ]


def _import_from(valor: str) -> str | None:
    for parte in valor.split(","):
        if parte.startswith("import-from="):
            return parte.removeprefix("import-from=")
    return None


# --- CA-D1.7.1: una clave import-from por disco ----------------------------------------------


def test_ca_d1_7_1_tres_discos_con_tres_imagenes_llevan_tres_import_from_sin_repetir():
    p = construir_parametros(_cfg(3), INV)
    volids = [_import_from(p[f"scsi{i}"]) for i in range(3)]
    assert volids == ["local:import/d0.qcow2", "local:import/d1.qcow2", "local:import/d2.qcow2"]
    assert len(set(volids)) == 3


def test_ca_d1_7_1_los_discos_importados_se_crean_con_tamano_cero_y_nunca_el_del_formulario():
    p = construir_parametros(_cfg(3), INV)
    for i in range(3):
        assert p[f"scsi{i}"].startswith("local-lvm:0,import-from=")


def test_ca_d1_7_1_un_disco_marcado_crear_vacio_no_lleva_import_from_y_conserva_su_tamano():
    p = construir_parametros(_cfg(3, vacios=(2,)), INV)
    assert _import_from(p["scsi0"]) and _import_from(p["scsi1"])
    assert "import-from" not in p["scsi2"] and p["scsi2"].startswith("local-lvm:10,")


def test_ca_d1_7_1_el_orden_de_las_claves_sigue_el_de_los_discos_del_formulario():
    p = construir_parametros(_cfg(4), INV)
    claves = [k for k in p if k.startswith("scsi") and k != "scsihw"]
    assert claves == ["scsi0", "scsi1", "scsi2", "scsi3"]


def test_las_imagenes_valen_para_cada_bus():
    cfg = _cfg(2)
    cfg.discos[0].bus, cfg.discos[1].bus = Bus.VIRTIO, Bus.SATA
    p = construir_parametros(cfg, INV)
    assert _import_from(p["virtio0"]) == "local:import/d0.qcow2"
    assert _import_from(p["sata0"]) == "local:import/d1.qcow2"


def test_si_hay_imagen_y_crear_vacio_a_la_vez_manda_la_imagen_en_peticion_y_espacio():
    cfg = _cfg(2)
    cfg.detalle_origen = DetalleImportacion(
        imagen=_ref("d0.qcow2"),
        tamano_virtual_bytes=10 * GIB,
        otras=(ImagenDisco(1, _ref("d1.qcow2"), crear_vacio=True, tamano_virtual_bytes=11 * GIB),),
    )
    p = construir_parametros(cfg, INV)
    assert _import_from(p["scsi1"]) == "local:import/d1.qcow2"
    assert list(pedido_vm(cfg, INV).values()) == [21 * GIB]


@pytest.mark.parametrize(
    "volid",
    ["local:import/../../etc/passwd", "local:import/a.qcow2,scsi9=x", "/etc/passwd",
     "local:iso/a.iso", "local:import/a b.qcow2;rm", "local:import/"],
)  # fmt: skip
def test_ca_d1_7_1_un_volid_malo_en_un_disco_adicional_se_rechaza_al_construir(volid):
    cfg = _cfg(2)
    cfg.detalle_origen = DetalleImportacion(
        imagen=_ref("d0.qcow2"), otras=(ImagenDisco(1, RefVolumen("x", volid)),)
    )
    with pytest.raises(ErrorProxLaunch) as e:
        construir_parametros(cfg, INV)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO


def test_un_disco_pendiente_nunca_llega_a_la_peticion():
    with pytest.raises(ErrorProxLaunch) as e:
        construir_parametros(_cfg(3, pendientes=(2,)), INV)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO
    assert e.value.params["campo"] == "discos[2]"


def test_una_entrada_de_imagen_fuera_de_rango_se_ignora():
    cfg = _cfg(2)
    cfg.detalle_origen = DetalleImportacion(
        imagen=_ref("d0.qcow2"),
        otras=(ImagenDisco(1, _ref("d1.qcow2")), ImagenDisco(7, _ref("fantasma.qcow2"))),
    )
    p = construir_parametros(cfg, INV)
    assert "fantasma" not in "".join(p.values())


# --- CA-D1.7.2 y CA-D1.7.3: discos sin imagen -------------------------------------------------


def test_ca_d1_7_2_un_disco_sin_imagen_ni_crear_vacio_es_v_d27_error():
    errores = _errores(_cfg(3, pendientes=(2,)))
    assert ("V-D27", {"disco": "2"}) in errores


def test_ca_d1_7_2_con_crear_vacio_o_con_imagen_no_hay_v_d27():
    assert not [e for e in _errores(_cfg(3, vacios=(1, 2))) if e[0] == "V-D27"]
    assert not [e for e in _errores(_cfg(3)) if e[0] == "V-D27"]


def test_ca_d1_7_2_cada_disco_pendiente_da_su_propio_v_d27():
    errores = _errores(_cfg(4, pendientes=(1, 3)))
    assert [e[1]["disco"] for e in errores if e[0] == "V-D27"] == ["1", "3"]


def test_ca_d1_7_2_comprobar_impide_crear_porque_es_severidad_error():
    problemas = validar_vm(_cfg(3, pendientes=(2,)), INV, CAPS)
    v = next(p for p in problemas if p.codigo == "V-D27")
    assert v.severidad == Severidad.ERROR and v.campo == "detalle_origen.otras[1]"


def test_ca_d1_7_3_el_disco_del_sistema_sin_imagen_es_error_y_no_se_puede_excluir():
    cfg = _cfg(3)
    cfg.detalle_origen = DetalleImportacion(imagen=RefVolumen(), otras=cfg.detalle_origen.otras)
    errores = _errores(cfg)
    assert ("V-D27", {"disco": "0", "sistema": "si"}) in errores


def test_ca_d1_7_3_con_un_solo_disco_sin_imagen_sigue_siendo_error_de_0_8_0():
    cfg = cfg_import(None)
    cfg.detalle_origen = DetalleImportacion(imagen=RefVolumen())
    codigos = [p.codigo for p in validar_vm(cfg, INV, CAPS) if p.severidad == Severidad.ERROR]
    assert codigos and any(c.startswith(("V-O", "V-D27")) for c in codigos)


# --- CA-D1.7.4: espacio -----------------------------------------------------------------------


def test_ca_d1_7_4_el_espacio_es_la_suma_de_los_tamanos_virtuales():
    cfg = _cfg(3)
    assert list(pedido_vm(cfg, INV).values()) == [(10 + 11 + 12) * GIB]


def test_ca_d1_7_4_un_disco_vacio_aporta_su_tamano_del_formulario():
    cfg = _cfg(3, vacios=(2,))
    assert list(pedido_vm(cfg, INV).values()) == [(10 + 11 + 10) * GIB]


def test_ca_d1_7_4_sin_tamano_virtual_se_usa_el_del_archivo_del_catalogo():
    cfg = _cfg(2)
    cfg.detalle_origen = DetalleImportacion(
        imagen=_ref("d0.qcow2"),
        tamano_virtual_bytes=1 * GIB,
        otras=(ImagenDisco(1, _ref("d1.qcow2")),),
    )
    # Sin catálogo con ese archivo, el disco sin tamaño conocido no suma (0): no inventa tamaños.
    assert list(pedido_vm(cfg, INV).values()) == [1 * GIB]


def test_ca_d1_7_4_si_la_suma_no_cabe_el_error_nombra_tamanos_y_storage():
    cfg = _cfg(3)
    cfg.detalle_origen = DetalleImportacion(
        imagen=_ref("d0.qcow2"),
        tamano_virtual_bytes=200 * GIB,
        otras=(
            ImagenDisco(1, _ref("d1.qcow2"), tamano_virtual_bytes=200 * GIB),
            ImagenDisco(2, _ref("d2.qcow2"), tamano_virtual_bytes=10 * GIB),
        ),
    )
    inv = inv_origen()
    uso = uso_de_nodos(cfg, ["pve1"], inv)
    # local-lvm es thin: con la política «bloquear» es un error; con «advertir», aviso.
    problemas = evaluar_espacio(uso, PoliticaThin.BLOQUEAR)
    assert len(problemas) == 1
    p = problemas[0]
    assert p.severidad == Severidad.ERROR
    assert p.params["storage"] == "local-lvm"
    assert p.params["pedido_gib"] == "410" and p.params["libre_gib"] == "300"


def test_ca_d1_7_4_el_espacio_cabe_cuando_la_suma_es_menor_que_lo_libre():
    uso = uso_de_nodos(_cfg(3), ["pve1"], INV)
    assert evaluar_espacio(uso, PoliticaThin.BLOQUEAR) == []


# --- CA-D1.7.5: archivo ya subido con el mismo nombre -------------------------------------------


def test_ca_d1_7_5_un_archivo_ya_subido_con_el_mismo_nombre_se_propone():
    from .apoyo_mvp4 import listado

    inv = inv_origen(
        listados=(
            listado(
                "pve1",
                "local",
                Contenido.IMPORT,
                "local:import/sistema.qcow2",
                "local:import/datos.qcow2",
            ),
        )
    )
    inv.arquitecturas = {}
    p = proponer_de("varios_discos_nic.xml", inv=inv)
    det = p.cfg.detalle_origen
    nombres = {det.imagen.nombre, *(o.imagen.nombre for o in det.otras if o.imagen)}
    assert "sistema.qcow2" in nombres and "datos.qcow2" in nombres


def test_ca_d1_7_5_proponer_nunca_elige_una_imagen_por_su_cuenta_sin_coincidencia():
    p = proponer_de("varios_discos_nic.xml", inv=inventario_d())
    assert p.cfg.detalle_origen.imagen == RefVolumen()
    assert all(o.imagen is None and not o.crear_vacio for o in p.cfg.detalle_origen.otras)


# --- CA-D1.7.6: lote de copias ------------------------------------------------------------------


def test_ca_d1_7_6_cinco_copias_con_dos_discos_llevan_las_mismas_dos_imagenes():
    cfg = _cfg(2)
    plan = _plan(definicion(5, plantilla_vm=cfg), INV)
    assert len(plan.elementos) == 5
    imagenes = set()
    for e in plan.elementos:
        p = construir_parametros(e.cfg, INV)
        imagenes.add((_import_from(p["scsi0"]), _import_from(p["scsi1"])))
    assert imagenes == {("local:import/d0.qcow2", "local:import/d1.qcow2")}


def test_ca_d1_7_6_el_espacio_del_lote_multiplica_por_el_numero_de_copias():
    cfg = _cfg(2)
    por_vm = sum(pedido_vm(cfg, INV).values())
    assert por_vm == (10 + 11) * GIB
    plan = _plan(definicion(5, plantilla_vm=cfg), INV)
    assert sum(u.pedido_bytes for u in plan.uso.values()) == 5 * por_vm


# --- CA-D1.7.7: límites por bus --------------------------------------------------------------


def _xml_con_discos(n: int, bus: str) -> str:
    return xml_minimo(
        "".join(disco_xml(dev=f"d{i:02d}", bus=bus, archivo=f"/i/{i}.qcow2") for i in range(n))
    )


@pytest.mark.parametrize(("bus", "maximo"), [("virtio", 16), ("scsi", 31), ("sata", 6), ("ide", 4)])
def test_ca_d1_7_7_el_limite_de_cada_bus_es_v_d28_un_disco_mas(bus, maximo):
    ok = proponer_de(dominio_desde_texto(_xml_con_discos(maximo, bus)), inv=inventario_d())
    assert not ok.bloquea()
    exceso = proponer_de(dominio_desde_texto(_xml_con_discos(maximo + 1, bus)), inv=inventario_d())
    f = fila(exceso, f"discos.{bus}")
    assert f.problema.codigo == "V-D28" and exceso.bloquea()
    assert f.problema.params["n"] == str(maximo + 1) and f.problema.params["maximo"] == str(maximo)


def test_ca_d1_7_7_diecisiete_discos_virtio_son_v_d28():
    p = proponer_de(dominio_desde_texto(_xml_con_discos(17, "virtio")), inv=inventario_d())
    assert fila(p, "discos.virtio").problema.codigo == "V-D28"


def test_ca_d1_7_7_los_discos_de_buses_distintos_no_se_suman():
    xml = xml_minimo(
        "".join(disco_xml(dev=f"vd{i}", bus="virtio") for i in range(10))
        + "".join(disco_xml(dev=f"sd{i}", bus="scsi") for i in range(10))
    )
    assert not proponer_de(dominio_desde_texto(xml), inv=inventario_d()).bloquea()


def test_ca_d1_7_7_la_propuesta_trae_un_disco_del_formulario_por_cada_disco_migrable():
    p = proponer_de("varios_discos_nic.xml", inv=inventario_d())
    assert len(p.cfg.discos) == 3  # el de red no se migra
    assert [d.bus for d in p.cfg.discos] == [Bus.VIRTIO, Bus.VIRTIO, Bus.SATA]
    assert [o.indice for o in p.cfg.detalle_origen.otras] == [1, 2]


def test_el_disco_del_sistema_es_el_del_arranque_aunque_no_sea_el_primero_del_xml():
    p = proponer_de("varios_discos_nic.xml", inv=inventario_d())
    assert fila(p, "disco[0]").origen.startswith("vda sistema.qcow2")
    assert fila(p, "disco[1]").origen.startswith("vdb datos.qcow2")


def test_sin_orden_de_arranque_el_primer_disco_del_xml_es_el_del_sistema():
    xml = xml_minimo(
        disco_xml(dev="vda", archivo="/i/uno.qcow2") + disco_xml(dev="vdb", archivo="/i/dos.qcow2")
    )
    assert fila(
        proponer_de(dominio_desde_texto(xml), inv=inventario_d()), "disco[0]"
    ).origen.startswith("vda uno")


def test_con_orden_de_arranque_gana_el_menor_numero():
    xml = xml_minimo(
        disco_xml(dev="vda", archivo="/i/a.qcow2", extra="<boot order='3'/>")
        + disco_xml(dev="vdb", archivo="/i/b.qcow2", extra="<boot order='2'/>")
    )
    assert fila(
        proponer_de(dominio_desde_texto(xml), inv=inventario_d()), "disco[0]"
    ).origen.startswith("vdb b")


# --- CA-D1.7.8: un solo disco = 0.8.0 ---------------------------------------------------------


def test_ca_d1_7_8_un_solo_disco_con_imagen_es_la_peticion_de_0_8_0():
    p = construir_parametros(cfg_import(), INV)
    assert p["scsi0"] == f"local-lvm:0,import-from={VOLID_IMAGEN},discard=on,ssd=1,iothread=1"
    assert not any("import-from" in v for k, v in p.items() if k != "scsi0")


def test_ca_d1_7_8_sin_otras_el_segundo_disco_se_crea_vacio_como_en_0_8_0():
    cfg = cfg_import(cfg={"discos": [Disco("local-lvm", 32), Disco("local-lvm", 16)]})
    assert cfg.detalle_origen.otras == ()
    p = construir_parametros(cfg, INV)
    assert "import-from" in p["scsi0"] and p["scsi1"].startswith("local-lvm:16,")
    assert "import-from" not in p["scsi1"]


def test_ca_d1_7_8_con_otras_vacio_y_un_disco_la_peticion_no_cambia():
    base = construir_parametros(cfg_import(), INV)
    cfg = cfg_import()
    cfg.detalle_origen = DetalleImportacion(imagen=cfg.detalle_origen.imagen, otras=())
    assert construir_parametros(cfg, INV) == base


# --- CA-D1.7.9: discos que no se pueden traer -------------------------------------------------


@pytest.mark.parametrize(
    "disco",
    [
        "<disk type='network' device='disk'><source protocol='rbd' name='a/b'/><target dev='vda' bus='virtio'/></disk>",  # noqa: E501
        "<disk type='dir' device='disk'><source dir='/srv/x'/><target dev='vda' bus='virtio'/></disk>",  # noqa: E501
        "<disk type='nvme' device='disk'><source type='pci'/><target dev='vda' bus='virtio'/></disk>",  # noqa: E501
    ],
    ids=["network", "dir", "nvme"],
)
def test_ca_d1_7_9_el_disco_de_sistema_no_migrable_es_v_d29_error_y_bloquea(disco):
    p = proponer_de(dominio_desde_texto(xml_minimo(disco)), inv=inventario_d())
    f = fila(p, "disco[0]")
    assert f.problema.codigo == "V-D29" and f.problema.severidad == Severidad.ERROR
    assert f.problema.params["sistema"] == "si" and p.bloquea()


@pytest.mark.parametrize(
    "disco",
    [
        "<disk type='network' device='disk'><source protocol='rbd' name='a/b'/><target dev='vdb' bus='virtio'/></disk>",  # noqa: E501
        "<disk type='dir' device='disk'><source dir='/srv/x'/><target dev='vdb' bus='virtio'/></disk>",  # noqa: E501
        "<disk type='nvme' device='disk'><source type='pci'/><target dev='vdb' bus='virtio'/></disk>",  # noqa: E501
        "<disk type='block' device='lun'><source dev='/dev/sdb'/><target dev='sdb' bus='scsi'/></disk>",  # noqa: E501
    ],
    ids=["network", "dir", "nvme", "lun"],
)
def test_ca_d1_7_9_un_disco_secundario_no_migrable_es_aviso_y_queda_fuera_del_formulario(disco):
    p = proponer_de(dominio_desde_texto(xml_minimo(disco_xml() + disco)), inv=inventario_d())
    f = fila(p, "disco_origen[1]")
    assert f.problema.codigo == "V-D29" and f.problema.severidad == Severidad.AVISO
    assert f.estado.value == "no_se_migra" and not p.bloquea()
    assert len(p.cfg.discos) == 1 and p.discos_no_migrables == (1,)
    assert p.cfg.detalle_origen.otras == ()


def test_ca_d1_7_9_un_lun_como_unico_disco_bloquea_aunque_sea_con_v_d27_y_v_d29_como_aviso():
    lun = "<disk type='block' device='lun'><source dev='/dev/sdb'/><target dev='sda' bus='scsi'/></disk>"  # noqa: E501
    p = proponer_de(dominio_desde_texto(xml_minimo(lun)), inv=inventario_d())
    assert p.bloquea()
    assert fila(p, "disco_origen[0]").problema.codigo == "V-D29"
    assert fila(p, "disco[0]").problema.codigo == "V-D27"


def test_ca_d1_7_9_un_disco_de_sistema_no_migrable_con_otro_disco_valido_sigue_bloqueando():
    red = "<disk type='network' device='disk'><source protocol='rbd' name='a/b'/><target dev='vda' bus='virtio'/><boot order='1'/></disk>"  # noqa: E501
    p = proponer_de(dominio_desde_texto(xml_minimo(red + disco_xml(dev="vdb"))), inv=inventario_d())
    assert p.bloquea() and fila(p, "disco[0]").problema.codigo == "V-D29"


def test_el_archivo_original_solo_es_texto_para_mostrar_y_va_saneado_al_nombre_base():
    p = proponer_de(
        dominio_desde_texto(xml_minimo(disco_xml(archivo="/etc/passwd"))), inv=inventario_d()
    )
    assert "passwd" in fila(p, "disco[0]").origen and "/" not in fila(p, "disco[0]").origen
    assert "passwd" not in repr(p.cfg)  # nunca entra en la configuración que viajará
