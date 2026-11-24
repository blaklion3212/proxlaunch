"""D3.1 (0.9.0): lectura de mapeos PCI/USB del clúster (RF-D3.1, RNF-D2, RNF-D4).

CA-D3.1.1–7. Dobles de ``/cluster/mapping/{pci,usb}``; los datos del servidor no son confiables:
solo ids con ``^[A-Za-z0-9._-]{1,64}$`` llegan a la interfaz y a una petición, los textos se
sanean y se acotan. Sin abrir la sección no se hace ninguna lectura nueva.
"""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import (
    MAX_PCI,
    MAX_USB,
    RE_ID_MAPEO,
    TipoMapeo,
)
from proxlaunch.nucleo.servicios.catalogo import ServicioCatalogo

from .apoyo_fase_d import V_84, V_92, banco_d
from .apoyo_lote import error_http, mapeo_api

PCI = r"/cluster/mapping/pci$"
USB = r"/cluster/mapping/usb$"


def _servicio(version=V_92, **api):
    banco = banco_d(nodos=("pve1", "pve2"), version=version)
    for tipo, valor in api.items():
        banco.cluster.mapeos_api[tipo] = valor
    return banco, ServicioCatalogo(banco.sesion, banco.reloj)


def _leer(banco, servicio, **kw):
    cat = servicio.leer_hardware_seccion(banco.inv, ("pve1", "pve2"), **kw)
    return cat.hardware


GPU = mapeo_api("gpu-a2", ("pve1", "/dev/gpu1"), ("pve2", "/dev/gpu1"), descripcion="GPU A2",
                mdev=False, migrable=False)  # fmt: skip
LLAVE = mapeo_api("llave-hasp", ("pve1", "/dev/bus/usb/001/005"), descripcion="Llave de licencias")


def test_ca_d3_1_1_se_listan_los_mapeos_pci_y_usb_con_su_descripcion_y_los_nodos():
    banco, srv = _servicio(pci=[GPU], usb=[LLAVE])
    hw = _leer(banco, srv)
    assert hw.error_mapeos is None
    por_id = {m.id: m for m in hw.mapeos}
    assert set(por_id) == {"gpu-a2", "llave-hasp"}
    gpu, llave = por_id["gpu-a2"], por_id["llave-hasp"]
    assert gpu.tipo == TipoMapeo.PCI and llave.tipo == TipoMapeo.USB
    assert gpu.descripcion == "GPU A2" and llave.descripcion == "Llave de licencias"
    assert gpu.nodos() == frozenset({"pve1", "pve2"}) and llave.nodos() == frozenset({"pve1"})
    assert gpu.mdev is False and gpu.migrable_en_vivo is False


def test_ca_d3_1_1_mdev_y_live_migration_capable_se_leen_como_booleanos():
    banco, srv = _servicio(
        pci=[mapeo_api("vgpu", ("pve1", "/x"), mdev=True, migrable=True)], usb=[]
    )
    (m,) = _leer(banco, srv).mapeos
    assert m.mdev is True and m.migrable_en_vivo is True


@pytest.mark.parametrize("valor", [1, True, "1", "true"])
def test_los_booleanos_de_proxmox_pueden_llegar_de_varias_formas(valor):
    fila = mapeo_api("g", ("pve1", "/x"))
    fila["mdev"] = valor
    banco, srv = _servicio(pci=[fila], usb=[])
    assert _leer(banco, srv).mapeos[0].mdev is True


def test_ca_d3_1_1_se_leen_solo_las_dos_listas_y_nada_mas_por_defecto():
    banco, srv = _servicio(pci=[GPU], usb=[LLAVE])
    _leer(banco, srv)
    assert len(banco.cluster.lecturas_d(PCI)) == 1 and len(banco.cluster.lecturas_d(USB)) == 1
    assert not [c for c in banco.cluster.llamadas_a("GET", "check-node")]  # sin check-node


def test_ca_d3_1_2_una_lista_vacia_es_un_resultado_valido_sin_error_de_lectura():
    banco, srv = _servicio(pci=[], usb=[])
    hw = _leer(banco, srv)
    assert hw.mapeos == () and hw.error_mapeos is None


@pytest.mark.parametrize(
    "fallo",
    [
        error_http(403, "Permission check failed (/mapping/pci, Mapping.Audit)"),
        error_http(404, "no such path"),
        error_http(500, "internal error"),
        error_http(501, "not implemented"),
        ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "tiempo agotado"),
        TimeoutError("t"),
    ],
    ids=["403", "404", "500", "501", "sin_respuesta", "excepcion"],
)
def test_ca_d3_1_3_un_fallo_en_pci_deja_la_lista_usb_y_registra_que_tipo_fallo(fallo):
    banco, srv = _servicio(pci=fallo, usb=[LLAVE])
    hw = _leer(banco, srv)
    assert [m.id for m in hw.mapeos] == ["llave-hasp"]
    assert hw.error_mapeos is not None and hw.error_mapeos.params["tipo"] == "pci"


def test_ca_d3_1_3_un_fallo_en_usb_deja_la_lista_pci():
    banco, srv = _servicio(pci=[GPU], usb=error_http(403, "Permission check failed"))
    hw = _leer(banco, srv)
    assert [m.id for m in hw.mapeos] == ["gpu-a2"]
    assert hw.error_mapeos.params["tipo"] == "usb"


def test_ca_d3_1_3_si_fallan_las_dos_no_hay_lista_y_el_error_nombra_ambos_tipos():
    err = error_http(501, "not implemented")
    banco, srv = _servicio(pci=err, usb=err)
    hw = _leer(banco, srv)
    assert hw.mapeos is None
    assert set(hw.error_mapeos.params["tipo"].split(",")) == {"pci", "usb"}


@pytest.mark.parametrize(
    "id_malo",
    [
        "con espacio",
        "a;b",
        "a=b",
        "x" * 65,
        "",
        "a/b",
        "a,b",
        "<b>x</b>",
        "ñandú",
        "a\nb",
        ".." + "\x00",
    ],
)
def test_ca_d3_1_4_un_id_invalido_no_se_ofrece_como_mapeo(id_malo):
    banco, srv = _servicio(pci=[mapeo_api(id_malo, ("pve1", "/x")), GPU], usb=[])
    hw = _leer(banco, srv)
    assert [m.id for m in hw.mapeos] == ["gpu-a2"]


@pytest.mark.parametrize("id_bueno", ["a", "gpu-a2", "A.b_c-1", "x" * 64, "0"])
def test_ca_d3_1_4_los_ids_validos_en_el_limite_se_ofrecen(id_bueno):
    banco, srv = _servicio(pci=[mapeo_api(id_bueno, ("pve1", "/x"))], usb=[])
    assert [m.id for m in _leer(banco, srv).mapeos] == [id_bueno]
    assert RE_ID_MAPEO.fullmatch(id_bueno)


@pytest.mark.parametrize("id_raro", [None, 5, ["gpu"], {"a": 1}, True])
def test_ca_d3_1_4_un_id_que_no_es_texto_se_descarta(id_raro):
    fila = mapeo_api("x", ("pve1", "/x"))
    fila["id"] = id_raro
    banco, srv = _servicio(pci=[fila], usb=[])
    assert _leer(banco, srv).mapeos == ()


def test_ca_d3_1_5_la_descripcion_con_html_saltos_o_5000_caracteres_se_sanea_y_se_acota():
    sucia = "<script>alert(1)</script>\nlinea\x00dos\x1b[31m&" + "x" * 5000
    banco, srv = _servicio(pci=[mapeo_api("gpu", ("pve1", "/x"), descripcion=sucia)], usb=[])
    (m,) = _leer(banco, srv).mapeos
    assert len(m.descripcion) <= 256
    assert not any(c in m.descripcion for c in "<>&\n\x00\x1b")


def test_ca_d3_1_5_la_ruta_y_el_id_de_hardware_de_cada_entrada_tambien_se_sanean():
    fila = mapeo_api("gpu", ("pve1", "/dev/<img src=x onerror=1>\n" + "y" * 1000))
    banco, srv = _servicio(pci=[fila], usb=[])
    (m,) = _leer(banco, srv).mapeos
    (e,) = m.entradas
    assert e.nodo == "pve1" and len(e.descripcion) <= 256
    assert not any(c in e.descripcion for c in "<>\n")


@pytest.mark.parametrize(
    "mapa",
    [
        ["path=/dev/x,id=10de:2236"],  # sin node=
        [["node=pve1,path=/x"]],  # lista anidada
        [None, 5, {"node": "pve1"}],
        "node=pve1,path=/x",  # una cadena en vez de lista
        [],
    ],
)
def test_ca_d3_1_6_un_map_con_formato_inesperado_ofrece_el_mapeo_sin_nodos_legibles(mapa):
    fila = mapeo_api("gpu", ("pve1", "/x"))
    fila["map"] = mapa
    banco, srv = _servicio(pci=[fila], usb=[])
    (m,) = _leer(banco, srv).mapeos
    assert m.id == "gpu" and m.nodos() == frozenset()


def test_ca_d3_1_6_un_nodo_no_legible_hace_que_la_validacion_diga_v_d52():
    """V-D52 aplica en la validación: el mapeo no tiene dispositivo en ningún nodo del lote."""
    from proxlaunch.nucleo.hardware_cluster.validacion import validar_hardware_servidor

    from .apoyo_fase_a import cfg_vm
    from .apoyo_fase_d import con_hardware, pci

    fila = mapeo_api("gpu", ("pve1", "/x"))
    fila["map"] = ["path=/dev/x"]
    banco, srv = _servicio(pci=[fila], usb=[])
    hw = _leer(banco, srv)
    cfg = con_hardware(cfg_vm(), pci("gpu"))
    problemas = validar_hardware_servidor({"pve1": [cfg]}, hw, None)
    assert [p.codigo for p in problemas if p.codigo == "V-D52"] == ["V-D52"]


def test_ca_d3_1_7_abrir_la_seccion_hace_exactamente_dos_lecturas_y_sin_abrirla_ninguna():
    banco, srv = _servicio(pci=[GPU], usb=[LLAVE])
    assert banco.cluster.lecturas_d(r"/cluster/mapping") == []  # nada hasta abrir la sección
    _leer(banco, srv)
    assert len(banco.cluster.lecturas_d(r"/cluster/mapping/")) == 2


def test_ca_d3_1_7_la_segunda_apertura_no_vuelve_a_leer_la_cache_hasta_releer():
    banco, srv = _servicio(pci=[GPU], usb=[LLAVE])
    banco.inv.catalogo = srv.leer_hardware_seccion(banco.inv, ("pve1",))
    antes = len(banco.cluster.lecturas_d(r"/cluster/mapping/"))
    banco.inv.catalogo = srv.leer_hardware_seccion(banco.inv, ("pve1",))
    assert len(banco.cluster.lecturas_d(r"/cluster/mapping/")) == antes == 2


def test_ca_d3_1_7_un_inventario_nuevo_tras_reconectar_vuelve_a_leer():
    """CL-D24: reconectar vacía la caché (el catálogo de la sesión nueva no trae hardware)."""
    banco, srv = _servicio(pci=[GPU], usb=[])
    banco.inv.catalogo = srv.leer_hardware_seccion(banco.inv, ("pve1",))
    nuevo = banco_d(nodos=("pve1", "pve2"), cluster=banco.cluster)
    srv2 = ServicioCatalogo(nuevo.sesion, nuevo.reloj)
    srv2.leer_hardware_seccion(nuevo.inv, ("pve1",))
    assert len(banco.cluster.lecturas_d(PCI)) == 2


def test_nunca_se_escribe_al_leer_mapeos_ni_en_el_cliente_de_solo_lectura():
    banco, srv = _servicio(pci=[GPU], usb=[LLAVE])
    _leer(banco, srv, cpus=True)
    assert banco.cluster.solo_lecturas


@pytest.mark.parametrize("version", [V_84, V_92], ids=["8.4", "9.2"])
def test_la_lectura_de_mapeos_es_igual_en_8_4_y_9_2(version):
    banco, srv = _servicio(version=version, pci=[GPU], usb=[LLAVE])
    assert {m.id for m in _leer(banco, srv).mapeos} == {"gpu-a2", "llave-hasp"}


def test_topes_defensivos_no_mas_de_512_mapeos_por_tipo_ni_64_entradas():
    muchos = [mapeo_api(f"m{i}", ("pve1", "/x")) for i in range(700)]
    banco, srv = _servicio(pci=muchos, usb=[])
    assert len(_leer(banco, srv).mapeos) <= 512
    ancho = mapeo_api("ancho", *[("pve1", f"/dev/{i}") for i in range(200)])
    banco, srv = _servicio(pci=[ancho], usb=[])
    assert len(_leer(banco, srv).mapeos[0].entradas) <= 64


def test_los_limites_de_dispositivos_por_maquina_son_16_pci_y_5_usb():
    assert (MAX_PCI, MAX_USB) == (16, 5)


def test_un_nombre_de_nodo_hostil_en_map_nunca_llega_a_una_peticion():
    """Solo se pide ``check-node`` para los nodos del lote que ya conocemos (RNF-D2)."""
    from proxlaunch.nucleo.hardware_cluster.lectura import leer_info_hardware
    from proxlaunch.nucleo.origen.resolucion import NecesidadesCatalogo

    fila = mapeo_api("gpu", ("pve1", "/x"), ("pve1;rm -rf /?x=1", "/y"))
    banco, srv = _servicio(pci=[fila], usb=[])
    info = leer_info_hardware(
        banco.sesion.cliente, None, banco.sesion.capacidades,
        NecesidadesCatalogo(mapeos=frozenset({("pci", "gpu")})), ("pve1", "pve2"), None, {},
    )  # fmt: skip
    pedidos = [
        c.params["check-node"]
        for c in banco.cluster.llamadas
        if c.params and "check-node" in c.params
    ]
    assert pedidos == ["pve1"] and info.mapeos is not None
