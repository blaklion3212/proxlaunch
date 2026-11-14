"""MVP 4: clonado de plantillas (modo, petición, ajustes) y su creación por el servicio.

Requisitos: RF-O19..O23 (CA-O20.1..O20.5, O21.1..O21.9, O22.1..O22.7, O23.1..O23.3), D-25.1
(modo automático), INV-L1/INV-O3 (≤ 1 POST de creación por VMID; PUT idempotentes), E-O16, E-O18,
E-O19, E-O24, CA-O17.4 (espera proporcional).
"""

import threading

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import AjustesClon, ModoClon
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa
from proxlaunch.nucleo.origen.clon import (
    admite_enlazado,
    construir_ajustes_clon,
    construir_peticion_clon,
    detalle_de_config,
    disco_principal,
    modo_efectivo,
    parametros_ampliacion,
    union_etiquetas,
)
from proxlaunch.nucleo.origen.resolucion import espera_maxima_s, nodo_de_upid, resolver_origen
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_lote import GIB, RelojSeguro, storage, upid_de
from .apoyo_mvp4 import (
    ClusterM4,
    cfg_clon,
    detalle_plantilla,
    disco_plantilla,
    inv_origen,
    plantilla_pve,
)

# --- detalle_de_config: texto no confiable --------------------------------------------------------


def test_detalle_de_config_lee_discos_red_cpu_memoria_y_etiquetas_de_una_config_real():
    config = {
        "template": 1,
        "scsi0": "local-lvm:base-9000-disk-0,discard=on,iothread=1,size=32G,ssd=1",
        "virtio1": "nfs1:9000/base-9000-disk-1.qcow2,size=512M",
        "efidisk0": "local-lvm:base-9000-disk-1,efitype=4m,size=4M",
        "tpmstate0": "local-lvm:base-9000-disk-2,size=4M,version=v2.0",
        "ide2": "local:iso/x.iso,media=cdrom,size=100M",
        "net0": "virtio=BC:24:11:AA:BB:CC,bridge=vmbr0,firewall=1,tag=5",
        "net1": "e1000=BC:24:11:AA:BB:DD,bridge=vmbr1",
        "cpu": "x86-64-v3,flags=+aes",
        "sockets": "2",
        "cores": 4,
        "memory": "8192",
        "tags": "web;proxlaunch",
    }
    d = detalle_de_config(config)
    assert d.es_plantilla and d.bloqueo is None
    por_clave = {x.clave: x for x in d.discos}
    assert set(por_clave) == {"scsi0", "virtio1", "efidisk0", "tpmstate0"}  # sin CD-ROM
    assert (por_clave["scsi0"].storage, por_clave["scsi0"].tamano_bytes) == ("local-lvm", 32 * GIB)
    assert (
        por_clave["virtio1"].tamano_bytes == 512 * 1024**2
        and por_clave["virtio1"].formato == "qcow2"
    )
    assert d.bridges == ("vmbr0", "vmbr1")
    assert (d.sockets, d.cores, d.memoria_mib, d.tipo_cpu) == (2, 4, 8192, "x86-64-v3")
    assert d.etiquetas == frozenset({"web", "proxlaunch"})


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"scsi0": 5, "net0": None, "cores": "abc", "memory": -3, "cpu": 7, "tags": ["a"]},
        {"scsi0": "none", "sata0": "cdrom", "ide0": ",media=cdrom"},
        {"scsi0": "sin_dos_puntos,size=8G", "scsi1": "mal storage:vol,size=8G"},
        {"scsi0": "local:vm,size=zzz", "net0": "virtio,bridge=vm br0,x"},
        {"cpu": "no valido;rm", "lock": "", "template": "0"},
        {"scsi99999999999": "local:v", "SCSI0": "local:v", "scsi0x": "local:v"},
        {"scsi0": "local:x,size=" + "9" * 400 + "G"},
    ],
)
def test_detalle_de_config_nunca_lanza_con_valores_raros(config):
    d = detalle_de_config(config)
    assert d.es_plantilla is False
    assert d.bloqueo is None
    assert all(isinstance(x.storage, str) and ":" not in x.storage for x in d.discos)
    assert all(" " not in b for b in d.bridges)


def test_detalle_de_config_interpreta_lock_y_template_y_tamano_desconocido():
    d = detalle_de_config({"template": "1", "lock": "clone", "scsi0": "local:vm-1-disk-0"})
    assert d.es_plantilla and d.bloqueo == "clone"
    assert d.discos[0].tamano_bytes is None


def test_disco_principal_es_scsi0_y_si_no_virtio0_sata0_ide0():
    def d(*claves):
        return detalle_plantilla([disco_plantilla(c) for c in claves])

    assert disco_principal(d("virtio0", "scsi0", "sata0")).clave == "scsi0"
    assert disco_principal(d("sata0", "ide0", "virtio0")).clave == "virtio0"
    assert disco_principal(d("ide0", "sata0")).clave == "sata0"
    assert disco_principal(d("ide0")).clave == "ide0"
    assert disco_principal(d("scsi3")).clave == "scsi3"  # primer disco de datos
    assert disco_principal(d("efidisk0", "tpmstate0")) is None
    assert disco_principal(d()) is None


# --- RF-O20: modo efectivo ------------------------------------------------------------------------


def _inv_con(tipo: str, *, formatos=None, compartido=False):
    s = storage("st", tipo, 100, contenido="images", compartido=compartido)
    if formatos is not None:
        s = type(s)(**{**s.__dict__, "formatos": frozenset(formatos)})
    inv = inv_origen(nodos=("pve1",))
    inv.storages_todos = {"pve1": (s,)}
    inv.storages = {"pve1": (s,)}
    return inv


def _modo(tipo, modo=ModoClon.AUTOMATICO, discos=None, storage_destino=None, **kw):
    inv = _inv_con(tipo, **kw)
    det = detalle_plantilla(discos if discos is not None else [disco_plantilla("scsi0", "st")])
    cfg = cfg_clon("base", 9000, "pve1", modo=modo, storage_destino=storage_destino)
    return modo_efectivo(cfg.detalle_origen, det, inv, "pve1")


@pytest.mark.parametrize("tipo", ["lvmthin", "zfspool", "rbd", "btrfs", "dir", "nfs", "cifs"])
def test_ca_o20_1_automatico_en_backends_con_clon_enlazado_elige_enlazado(tipo):
    assert _modo(tipo) == (ModoClon.ENLAZADO, None)


@pytest.mark.parametrize("tipo", ["lvm", "iscsi", "cephfs", "desconocido"])
def test_ca_o20_2_automatico_en_lvm_grueso_u_otros_elige_completo(tipo):
    assert _modo(tipo) == (ModoClon.COMPLETO, None)


@pytest.mark.parametrize("tipo", ["dir", "nfs", "cifs"])
def test_dir_nfs_cifs_exigen_qcow2_para_el_enlazado(tipo):
    assert _modo(tipo, formatos={"qcow2", "raw"}) == (ModoClon.ENLAZADO, None)
    assert _modo(tipo, formatos={"raw"}) == (ModoClon.COMPLETO, None)  # CA-O04.6


def test_ca_o20_enlazado_exige_que_todos_los_discos_lo_admitan():
    sts = (
        storage("a", "lvmthin", 10, contenido="images"),
        storage("b", "lvm", 10, contenido="images"),
    )
    inv = inv_origen(nodos=("pve1",))
    inv.storages_todos = {"pve1": sts}
    det = detalle_plantilla([disco_plantilla("scsi0", "a"), disco_plantilla("scsi1", "b")])
    cfg = cfg_clon("base", 9000, "pve1")
    assert modo_efectivo(cfg.detalle_origen, det, inv, "pve1")[0] == ModoClon.COMPLETO
    cfg2 = cfg_clon("base", 9000, "pve1", modo=ModoClon.ENLAZADO)
    modo, problema = modo_efectivo(cfg2.detalle_origen, det, inv, "pve1")
    assert modo is None and problema.codigo == "V-O21" and problema.params["storages"] == "a,b"


def test_ca_o20_7_el_estado_tpm_no_condiciona_el_modo_enlazado():
    det = detalle_plantilla(
        [disco_plantilla("scsi0", "st"), disco_plantilla("tpmstate0", "no_enlazable", 1)]
    )
    cfg = cfg_clon("base", 9000, "pve1")
    assert (
        modo_efectivo(cfg.detalle_origen, det, _inv_con("lvmthin"), "pve1")[0] == ModoClon.ENLAZADO
    )


def test_plantilla_sin_discos_o_con_storage_desconocido_clona_completo():
    cfg = cfg_clon("base", 9000, "pve1")
    inv = _inv_con("lvmthin")
    assert (
        modo_efectivo(cfg.detalle_origen, detalle_plantilla([]), inv, "pve1")[0]
        == ModoClon.COMPLETO
    )
    fuera = detalle_plantilla([disco_plantilla("scsi0", "no_existe")])
    assert modo_efectivo(cfg.detalle_origen, fuera, inv, "pve1")[0] == ModoClon.COMPLETO


def test_ca_o20_3_enlazado_forzado_sin_soporte_o_con_storage_destino_da_v_o21():
    modo, p = _modo("lvm", modo=ModoClon.ENLAZADO)
    assert modo is None and p.codigo == "V-O21" and p.params["motivo"] == "sin_soporte"
    modo, p = _modo("lvmthin", modo=ModoClon.ENLAZADO, storage_destino="otro")
    assert modo is None and p.params["motivo"] == "storage_destino"


def test_ca_o20_4_completo_forzado_siempre_es_completo_aunque_se_pudiera_enlazar():
    assert _modo("lvmthin", modo=ModoClon.COMPLETO) == (ModoClon.COMPLETO, None)


def test_automatico_con_storage_destino_clona_completo():
    assert _modo("lvmthin", storage_destino="otro") == (ModoClon.COMPLETO, None)


def test_admite_enlazado_por_tipo_y_formatos():
    assert admite_enlazado("lvmthin", None) and admite_enlazado("zfspool", frozenset({"raw"}))
    assert admite_enlazado("dir", None) and admite_enlazado("dir", frozenset({"qcow2"}))
    assert not admite_enlazado("dir", frozenset({"raw"})) and not admite_enlazado("lvm", None)


# --- RF-O21: petición de clon ---------------------------------------------------------------------


def _resuelta(**kw):
    inv = inv_origen(plantillas=(plantilla_pve(),))
    cfg, problemas = resolver_origen(cfg_clon("base", **kw), inv, "pve1")
    assert problemas == []
    return cfg, inv


def test_ca_o20_1_clon_enlazado_no_lleva_full_storage_ni_format():
    cfg, inv = _resuelta()
    assert cfg.detalle_origen.modo_efectivo == ModoClon.ENLAZADO  # local-lvm es lvmthin
    pet = construir_peticion_clon(cfg, inv)
    assert (pet.nodo_plantilla, pet.vmid_plantilla) == ("pve1", 9000)
    assert pet.parametros == {"newid": "100", "name": "srv-web-01"}


def test_ca_o20_4_clon_completo_lleva_full_1_storage_y_format_solo_donde_v_09_lo_permite():
    cfg, inv = _resuelta(modo=ModoClon.COMPLETO, storage_destino="local")
    pet = construir_peticion_clon(cfg, inv)
    assert pet.parametros == {
        "newid": "100", "name": "srv-web-01", "full": "1", "storage": "local", "format": "qcow2",
    }  # fmt: skip
    cfg, inv = _resuelta(modo=ModoClon.COMPLETO, storage_destino="local-lvm")
    assert "format" not in construir_peticion_clon(cfg, inv).parametros  # lvmthin: solo raw
    cfg, inv = _resuelta(modo=ModoClon.COMPLETO)
    assert construir_peticion_clon(cfg, inv).parametros["full"] == "1"
    assert "storage" not in construir_peticion_clon(cfg, inv).parametros


def test_ca_o21_7_target_solo_si_el_nodo_destino_no_es_el_de_la_plantilla():
    cfg, inv = _resuelta()
    cfg.nodo = "pve2"
    assert construir_peticion_clon(cfg, inv).parametros["target"] == "pve2"
    cfg.nodo = "pve1"
    assert "target" not in construir_peticion_clon(cfg, inv).parametros


@pytest.mark.parametrize(
    "cambio",
    [
        {"nombre": "con espacio"},
        {"nombre": "-x"},
        {"vmid": True},
        {"vmid": "100"},
    ],
)
def test_construir_peticion_clon_rechaza_valores_inseguros(cambio):
    cfg, inv = _resuelta()
    for k, v in cambio.items():
        setattr(cfg, k, v)
    with pytest.raises(ErrorProxLaunch) as e:
        construir_peticion_clon(cfg, inv)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO


def test_construir_peticion_clon_sin_resolver_o_sin_clon_lanza_parametro_invalido():
    inv = inv_origen()
    for cfg in (cfg_clon("base"), cfg_clon("base", 9000, "pve1"), cfg_clon("base", 9000)):
        with pytest.raises(ErrorProxLaunch):
            construir_peticion_clon(cfg, inv)
    from .apoyo_mvp4 import cfg_base

    with pytest.raises(ErrorProxLaunch):
        construir_peticion_clon(cfg_base(), inv)


def test_construir_peticion_clon_no_acepta_nodo_ni_storage_con_inyeccion():
    cfg, inv = _resuelta(modo=ModoClon.COMPLETO, storage_destino="local")
    cfg.detalle_origen = type(cfg.detalle_origen)(
        plantilla=cfg.detalle_origen.plantilla,
        modo=ModoClon.COMPLETO,
        storage_destino="a,format=raw",
        modo_efectivo=ModoClon.COMPLETO,
    )
    with pytest.raises(ErrorProxLaunch):
        construir_peticion_clon(cfg, inv)


# --- RF-O22: ajustes tras clonar ------------------------------------------------------------------


def _ajustes(ajustes=None, etiquetas=(), detalle=None):
    cfg = cfg_clon("base", 9000, "pve1", ajustes=ajustes or AjustesClon())
    return construir_ajustes_clon(cfg, detalle or detalle_plantilla(), list(etiquetas))


def test_ca_o22_7_sin_cambios_ni_etiquetas_no_hay_put():
    a = _ajustes()
    assert a.config == {} and a.disco is None


def test_ca_o22_7_los_valores_iguales_a_la_plantilla_no_se_envian():
    a = _ajustes(AjustesClon(sockets=1, cores=2, memoria_mib=2048, tipo_cpu="x86-64-v2-AES"))
    assert a.config == {}


def test_ca_o22_2_cpu_y_memoria_distintos_van_en_un_solo_put_con_valores_absolutos():
    a = _ajustes(AjustesClon(sockets=2, cores=4, tipo_cpu="x86-64-v3", memoria_mib=4096))
    assert a.config == {"sockets": "2", "cores": "4", "cpu": "x86-64-v3", "memory": "4096"}
    assert all(not v.startswith("+") for v in a.config.values())


def test_ca_o22_4_tags_es_la_union_de_plantilla_y_lote_ordenada_y_sin_repetir():
    det = detalle_plantilla(etiquetas={"base", "web"})
    a = _ajustes(etiquetas=("proxlaunch", "lote-ab12", "web"), detalle=det)
    assert a.config == {"tags": "base;lote-ab12;proxlaunch;web"}


def test_ca_o22_4_si_la_plantilla_ya_tiene_todas_las_etiquetas_no_se_reenvian():
    det = detalle_plantilla(etiquetas={"proxlaunch", "lote-ab12"})
    assert _ajustes(etiquetas=("proxlaunch", "lote-ab12"), detalle=det).config == {}


def test_etiquetas_invalidas_del_lote_lanzan_parametro_invalido():
    with pytest.raises(ErrorProxLaunch):
        _ajustes(etiquetas=("mal;puesta",))


def test_ca_o22_3_el_disco_solo_crece_y_se_envia_el_tamano_absoluto():
    assert _ajustes(AjustesClon(disco_gib=16)).disco == ("scsi0", 16)
    assert _ajustes(AjustesClon(disco_gib=8)).disco is None  # igual: nada
    assert _ajustes(AjustesClon(disco_gib=4)).disco is None  # menor: nunca reduce (V-O23)


def test_ca_o22_3_sin_tamano_conocido_se_envia_el_resize():
    det = detalle_plantilla([type(disco_plantilla())("scsi0", "local-lvm", None, None)])
    assert _ajustes(AjustesClon(disco_gib=16), detalle=det).disco == ("scsi0", 16)


def test_ajustes_fuera_de_rango_lanzan_parametro_invalido():
    for malo in (AjustesClon(disco_gib=0), AjustesClon(tipo_cpu="x;y")):
        with pytest.raises(ErrorProxLaunch):
            _ajustes(malo)


def test_parametros_ampliacion_son_absolutos_y_validan_la_clave():
    assert parametros_ampliacion("scsi0", 16) == {"disk": "scsi0", "size": "16G"}
    for clave, gib in (
        ("efidisk0", 4),
        ("scsi0;x", 4),
        ("scsi0", 0),
        ("scsi0", -5),
        ("scsi0", True),
    ):
        with pytest.raises(ErrorProxLaunch):
            parametros_ampliacion(clave, gib)  # type: ignore[arg-type]


def test_union_etiquetas():
    assert union_etiquetas(["b", "a"], ("a", "c"), []) == "a;b;c"
    assert union_etiquetas() == ""


def test_nodo_de_upid_y_espera_proporcional():
    assert nodo_de_upid(upid_de("pve7", 100, "qmclone")) == "pve7"
    for malo in ("", "no es upid", "UPID:corto", "UPID:../etc:1:2:3:4:5:6:", None):
        assert nodo_de_upid(malo) is None  # type: ignore[arg-type]


def test_ca_o17_4_espera_maxima_crece_con_el_tamano_en_importacion_y_clon_completo():
    from .apoyo_mvp4 import cfg_import, listado

    inv = inv_origen()
    assert espera_maxima_s(cfg_import(tamano_virtual_bytes=1 * GIB), inv, 600.0) == 600.0
    # 100 GiB × 30 s/GiB = 3000 s > 600
    assert espera_maxima_s(cfg_import(tamano_virtual_bytes=100 * GIB), inv, 600.0) == 3000.0
    inv.catalogo = type(inv.catalogo)(
        permisos=inv.catalogo.permisos,
        listados=(listado("pve1", "local", Contenido.IMPORT, "local:import/cirros.qcow2"),),
    )
    # sin tamaño virtual se usa el del archivo (100 MiB → mínimo de 600 s)
    assert espera_maxima_s(cfg_import(), inv, 600.0) == 600.0
    cfg, inv2 = _resuelta(modo=ModoClon.COMPLETO)
    assert espera_maxima_s(cfg, inv2, 600.0) == 600.0  # 8 GiB × 30 = 240 < 600
    grande = plantilla_pve(detalle=detalle_plantilla([disco_plantilla("scsi0", "local-lvm", 100)]))
    inv3 = inv_origen(plantillas=(grande,))
    cfg3, _ = resolver_origen(cfg_clon("base", modo=ModoClon.COMPLETO), inv3, "pve1")
    assert espera_maxima_s(cfg3, inv3, 600.0) == 3000.0
    enlazado, inv4 = _resuelta()
    assert espera_maxima_s(enlazado, inv4, 123.0) == 123.0  # el enlazado usa la base
    from .apoyo_mvp4 import cfg_base

    assert espera_maxima_s(cfg_base(), inv, 77.0) == 77.0


# --- Servicio de creación con clon (INV-L1, E-O24) ------------------------------------------------


class _Mundo:
    def __init__(self, *, tags_lote=("proxlaunch", "lote-ab12"), permisos_efectivos=True, **plant):
        self.cl = ClusterM4(("pve1", "pve2"))
        self.cl.agregar_plantilla(9000, "base", "pve1", **plant)
        self.reloj = RelojSeguro()
        from .apoyo_api import crear_sesion
        from .apoyo_lote import TransporteCluster

        self.sesion = crear_sesion(TransporteCluster(self.cl), reloj=self.reloj)
        det = detalle_de_config(self.cl.plantillas[9000]["config"])
        self.inv = inv_origen(
            plantillas=(plantilla_pve(9000, "base", "pve1", detalle=det),),
            permisos_efectivos=permisos_efectivos,
        )
        self.tags_lote = tuple(tags_lote)
        self.etapas: list[Etapa] = []

    def cfg(self, **kw):
        cfg, problemas = resolver_origen(
            cfg_clon("base", etiquetas=self.tags_lote, **kw), self.inv, "pve1"
        )
        assert problemas == []
        return cfg

    def crear(self, cfg):
        servicio = ServicioCreacion(self.sesion, self.reloj, intervalo_s=0.01)
        return servicio.crear(cfg, self.inv, self.etapas.append, threading.Event())

    def put(self, que=None):
        return [p for p in self.cl.puts if que is None or p[2] == que]


def test_ca_o21_el_clon_cuenta_como_la_creacion_un_post_clone_y_ningun_post_qemu():
    m = _Mundo()
    r = m.crear(m.cfg())
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r.error
    assert m.cl.clones == {100: 1}
    assert m.cl.posts == {} and m.cl.deletes == {}  # nada de POST /qemu ni de DELETE
    cuerpo = m.cl.cuerpos_clon[100]
    assert cuerpo == {"newid": "100", "name": "srv-web-01"}  # enlazado: sin full/storage/format
    assert r.upid and ":qmclone:" in r.upid


def test_ca_o21_4_el_ajuste_espera_a_que_termine_el_lock_clone():
    m = _Mundo()
    estados = iter([{"lock": "clone"}] * 3 + [{}] * 20)
    original = m.cl._get

    def con_lock(ll, ruta):
        valor = original(ll, ruta)
        if ruta == "/nodes/pve1/qemu/100/config" and isinstance(valor, dict):
            valor = {**valor, **next(estados)}
        return valor

    m.cl._get = con_lock  # type: ignore[method-assign]
    r = m.crear(m.cfg(ajustes=AjustesClon(cores=4)))
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    antes_de_put = [
        c for c in m.cl.llamadas if c.metodo == "GET" and c.ruta.endswith("/100/config")
    ]
    assert len(antes_de_put) >= 4  # esperó a que se liberara el lock antes del PUT
    assert m.put("config") == [
        ("pve1", 100, "config", {"cores": "4", "tags": "lote-ab12;proxlaunch"})
    ]


def test_ca_o22_2_cpu_memoria_y_etiquetas_van_en_un_solo_put_config_y_sin_resize():
    m = _Mundo()
    r = m.crear(m.cfg(ajustes=AjustesClon(cores=4, memoria_mib=4096)))
    assert r.desenlace == Desenlace.OK
    assert m.put() == [
        ("pve1", 100, "config", {"cores": "4", "memory": "4096", "tags": "lote-ab12;proxlaunch"})
    ]
    assert Etapa.AJUSTANDO in m.etapas and m.etapas[-1] == Etapa.LISTO


def test_ca_o22_4_las_etiquetas_se_unen_con_las_de_la_plantilla():
    m = _Mundo(tags="base;web")
    assert m.crear(m.cfg()).desenlace == Desenlace.OK
    assert m.put("config")[0][3] == {"tags": "base;lote-ab12;proxlaunch;web"}


def test_ca_o22_3_resize_absoluto_solo_si_el_disco_crece_y_con_vm_config_disk():
    m = _Mundo()
    assert m.crear(m.cfg(ajustes=AjustesClon(disco_gib=20))).desenlace == Desenlace.OK
    assert m.put("resize") == [("pve1", 100, "resize", {"disk": "scsi0", "size": "20G"})]
    # sin cambios de disco: ningún resize
    m2 = _Mundo()
    m2.crear(m2.cfg(ajustes=AjustesClon(disco_gib=8)))
    assert m2.put("resize") == []


def test_inv_o10_sin_vm_config_disk_el_resize_se_omite_con_aviso_y_el_clon_sigue_ok():
    from .apoyo_mvp4 import permisos

    m = _Mundo(permisos_efectivos=permisos(quitar=("VM.Config.Disk",)))
    r = m.crear(m.cfg(ajustes=AjustesClon(disco_gib=20)))
    assert m.put("resize") == []
    assert r.desenlace == Desenlace.CON_AVISOS and "ajuste_omitido:disco" in r.avisos


def test_inv_o10_con_permisos_desconocidos_tampoco_se_envia_el_resize():
    m = _Mundo(permisos_efectivos=None)
    r = m.crear(m.cfg(ajustes=AjustesClon(disco_gib=20)))
    assert m.put("resize") == [] and r.desenlace == Desenlace.CON_AVISOS


def test_ca_o22_6_e_o24_si_falla_el_put_config_la_mv_queda_parcial_sin_reenviar_el_clon():
    from .apoyo_lote import Http  # noqa: F401

    m = _Mundo()
    m.cl.regla("PUT", r"/config$", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"))
    r = m.crear(m.cfg(ajustes=AjustesClon(cores=4)))
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.AJUSTE_POST_CLON_FALLIDO  # E-O24
    assert r.error.params["nombre"] == "srv-web-01" and "etiquetas" in r.error.params["ajuste"]
    assert "ajuste_pendiente:etiquetas" in r.avisos and "ajuste_pendiente:cpu_memoria" in r.avisos
    assert m.cl.clones == {100: 1}  # INV-L1: no se reenvía el clon
    assert 100 in m.cl.vms  # la MV existe (elegible para rollback)


def test_ca_o22_6_si_falla_el_resize_queda_parcial_con_ajuste_disco_pendiente():
    m = _Mundo()
    m.cl.regla("PUT", r"/resize$", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"))
    r = m.crear(m.cfg(ajustes=AjustesClon(disco_gib=20)))
    assert r.desenlace == Desenlace.PARCIAL
    assert "ajuste_pendiente:disco" in r.avisos and "ajuste_pendiente:etiquetas" not in r.avisos
    assert r.error.codigo == CodigoError.AJUSTE_POST_CLON_FALLIDO
    assert len(m.put("config")) == 1 and m.cl.clones == {100: 1}


def test_ca_o22_6_un_403_en_el_put_conserva_el_permiso_faltante_e_o20():
    m = _Mundo()
    m.cl.regla("PUT", r"/config$", ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"))
    r = m.crear(m.cfg())  # solo el PUT de etiquetas: el privilegio exigido es inequívoco
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["privilegio"] == "VM.Config.Options"
    assert r.error.params["ruta"] == "/vms/100" and r.error.params["via"] == "config"


def test_ca_o22_6_reintentar_ajustes_envia_solo_los_put_pendientes_y_nunca_un_post():
    m = _Mundo()
    regla = m.cl.regla("PUT", r"/config$", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"))
    cfg = m.cfg(ajustes=AjustesClon(cores=4))
    assert m.crear(cfg).desenlace == Desenlace.PARCIAL
    regla.veces = 0  # el servidor se recupera
    servicio = ServicioCreacion(m.sesion, m.reloj, intervalo_s=0.01)
    r = servicio.reintentar_ajustes(cfg, m.inv, threading.Event())
    assert r.desenlace == Desenlace.OK, r.error
    assert m.cl.clones == {100: 1} and m.cl.posts == {}
    assert m.cl.vms[100]["config"]["cores"] == "4"
    # repetirlo es inocuo: ya no queda nada por enviar
    n = len(m.put())
    assert servicio.reintentar_ajustes(cfg, m.inv, threading.Event()).desenlace == Desenlace.OK
    assert len(m.put()) == n


def test_reintentar_ajustes_no_toca_una_mv_que_no_es_la_del_plan():
    m = _Mundo()
    cfg = m.cfg(ajustes=AjustesClon(cores=4))
    m.cl.agregar_vm(100, "pve1", "otra-maquina")  # el VMID lo ocupa otra MV
    r = ServicioCreacion(m.sesion, m.reloj).reintentar_ajustes(cfg, m.inv, threading.Event())
    assert r.desenlace == Desenlace.ERROR and r.error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert m.put() == []


def test_ca_o21_11_plantilla_desaparecida_o_bloqueada_falla_sin_enviar_el_clon():
    m = _Mundo()
    cfg = m.cfg()
    del m.cl.plantillas[9000]
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.ERROR and r.error.codigo == CodigoError.FUENTE_DESAPARECIO
    assert m.cl.clones == {}
    m2 = _Mundo()
    cfg2 = m2.cfg()
    m2.cl.plantillas[9000]["config"]["lock"] = "backup"
    r2 = m2.crear(cfg2)
    assert (
        r2.error.codigo == CodigoError.CLON_NO_POSIBLE and r2.error.params["motivo"] == "bloqueada"
    )
    assert m2.cl.clones == {}


def test_la_plantilla_que_dejo_de_serlo_no_se_clona():
    m = _Mundo()
    cfg = m.cfg()
    m.cl.plantillas[9000]["config"]["template"] = 0
    r = m.crear(cfg)
    assert (
        r.error.codigo == CodigoError.CLON_NO_POSIBLE and r.error.params["motivo"] == "no_plantilla"
    )
    assert m.cl.clones == {}


def test_ca_o21_2_un_post_clone_con_resultado_incierto_no_se_reenvia():
    m = _Mundo()
    from .apoyo_lote import envio_incierto

    m.cl.regla("POST", r"/clone$", envio_incierto())
    r = m.crear(m.cfg())
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert m.cl.clones == {} or m.cl.clones == {100: 1}
    assert sum(1 for c in m.cl.llamadas if c.metodo == "POST") == 1  # un solo intento


def test_ca_o21_9_los_errores_de_clone_se_traducen_y_no_se_reintentan():
    casos = [
        ("can't clone to non-shared storage 'local-lvm'", CodigoError.CLON_NO_POSIBLE),
        ("Linked clone feature is not supported for 'x'", CodigoError.CLON_NO_POSIBLE),
        ("parameter 'storage' not allowed for linked clones", CodigoError.CLON_NO_POSIBLE),
        ("unable to create VM 100: config file already exists", CodigoError.CLON_ID_OCUPADO),
    ]
    from proxlaunch.nucleo.api.traductor_errores import traducir_http

    for texto, codigo in casos:
        e = traducir_http(500, texto, "")
        assert e.codigo == codigo, texto
        m = _Mundo()
        m.cl.regla("POST", r"/clone$", e, veces=None)
        r = m.crear(m.cfg())
        assert r.desenlace == Desenlace.ERROR and r.error.codigo == codigo
        assert sum(1 for c in m.cl.llamadas if c.metodo == "POST") == 1, texto


def test_traduccion_de_e_o19_conserva_el_vmid_ocupado():
    from proxlaunch.nucleo.api.traductor_errores import traducir_http

    e = traducir_http(500, "unable to create VM 105: config file already exists", "")
    assert e.codigo == CodigoError.CLON_ID_OCUPADO and e.params == {"vmid": "105"}


def test_ca_o21_la_tarea_qmclone_fallida_no_deja_ajustes_ni_reenvios():
    m = _Mundo()
    m.cl.exitstatus[100] = "clone failed: no space left"
    r = m.crear(m.cfg(ajustes=AjustesClon(cores=4)))
    assert r.desenlace in (Desenlace.ERROR, Desenlace.PARCIAL)
    assert m.put() == [] and m.cl.clones == {100: 1}


def test_ca_o21_1_cancelar_antes_del_envio_no_clona():
    m = _Mundo()
    servicio = ServicioCreacion(m.sesion, m.reloj, intervalo_s=0.01)
    ev = threading.Event()
    r = servicio.crear(m.cfg(), m.inv, m.etapas.append, ev, puede_enviar=lambda: False)
    assert (
        r.desenlace == Desenlace.CANCELADO and m.cl.clones == {} and m.cl.llamadas_a("POST") == []
    )


def test_ca_o21_3_el_vmid_se_reconsulta_antes_de_clonar_y_uno_ocupado_no_se_clona():
    m = _Mundo()
    m.cl.agregar_vm(100, "pve1", "otra")
    r = m.crear(m.cfg())
    assert r.desenlace == Desenlace.ERROR and r.error.codigo == CodigoError.VMID_OCUPADO
    assert m.cl.clones == {}


def test_el_servicio_no_escribe_nada_en_la_plantilla():
    m = _Mundo()
    m.crear(m.cfg(ajustes=AjustesClon(cores=4, disco_gib=20)))
    assert all(vmid != 9000 for _, vmid, _, _ in m.cl.puts)
    assert m.cl.plantillas[9000]["config"]["cores"] == 2 and m.cl.deletes == {}
