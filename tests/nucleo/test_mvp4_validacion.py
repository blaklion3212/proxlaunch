"""MVP 4: listas blancas de volids/nombres, permisos y reglas V-O01..V-O29 (capas 1 y 2).

Requisitos: V-O01..V-O09, V-O17..V-O24, V-O29; INV-O7 (lista blanca), INV-O10 (permisos dudosos),
CA-O08.5 (inyección), CA-O15.3 (ruta absoluta), RF-O24 (14 privilegios).
"""

import pytest

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos.catalogo import Contenido, ListadoStorage, PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.origen import AjustesClon, DetalleIso, ModoClon, RefVolumen, TipoSO
from proxlaunch.nucleo.modelos.vm import Bus, Disco, Firmware, OrigenSO
from proxlaunch.nucleo.origen.nombres import (
    es_ruta_absoluta,
    es_virtio_win,
    parece_url,
    partes_volid,
    sanear_nombre_archivo,
    validar_nombre_archivo,
    validar_volid,
)
from proxlaunch.nucleo.origen.permisos import (
    ROL_PROXLAUNCH,
    estado_privilegio,
    privilegios_de_peticion,
    tiene_privilegio,
)
from proxlaunch.nucleo.origen.validacion_origen import (
    validar_origen,
    validar_origen_sin_servidor,
)
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_mvp4 import (
    ROL_MVP3,
    VOLID_IMAGEN,
    VOLID_ISO,
    VOLID_VIRTIO,
    cfg_base,
    cfg_clon,
    cfg_import,
    cfg_iso,
    detalle_plantilla,
    disco_plantilla,
    inv_origen,
    listado,
    permisos,
    plantilla_pve,
    volumen,
)

CAPS = capacidades_para(Version("9.2", 9, 2, 0), None)


def _cods(problemas, severidad=None):
    return [p.codigo for p in problemas if severidad is None or p.severidad == severidad]


def _motivos(problemas, codigo):
    return [p.params.get("motivo") for p in problemas if p.codigo == codigo]


# --- INV-O7 / V-O02 / V-O03: lista blanca de volids ----------------------------------------------


@pytest.mark.parametrize(
    ("volid", "contenido"),
    [
        ("local:iso/alpine.iso", Contenido.ISO),
        ("local:iso/x.IMG", Contenido.ISO),
        ("nfs-1.a_b:iso/a-b_c.1.iso", Contenido.ISO),
        ("local:import/cirros.qcow2", Contenido.IMPORT),
        ("local:import/d.raw", Contenido.IMPORT),
        ("local:import/d.vmdk", Contenido.IMPORT),
    ],
)
def test_v_o02_v_o03_volids_validos(volid, contenido):
    assert validar_volid(volid, contenido) is None


@pytest.mark.parametrize(
    ("volid", "contenido", "motivo"),
    [
        ("local:iso/x.iso,media=disk", Contenido.ISO, "caracteres"),  # CA-O08.5
        ("local:iso/x.iso,ide0=a", Contenido.ISO, "caracteres"),
        ("local:import/x.qcow2,scsi1=a", Contenido.IMPORT, "caracteres"),  # CA-O17.8
        ("local:iso/x.iso;ide0=a", Contenido.ISO, "caracteres"),
        ("local:iso/a b.iso", Contenido.ISO, "caracteres"),
        ("local:iso/a\nb.iso", Contenido.ISO, "caracteres"),
        ("local:iso/a\x00.iso", Contenido.ISO, "caracteres"),
        ("local:iso/" + "a" * 101 + ".iso", Contenido.ISO, "caracteres"),
        ("local:iso/acentó.iso", Contenido.ISO, "caracteres"),
        ("local:iso/x.exe", Contenido.ISO, "extension"),
        ("local:iso/sin_extension", Contenido.ISO, "extension"),
        ("local:import/x.iso", Contenido.IMPORT, "extension"),  # extensión de otro contenido
        ("local:iso/x.iso", Contenido.IMPORT, "forma"),  # tipo de volumen ajeno
        ("local:iso/x.qcow2", Contenido.ISO, "extension"),
        ("local:import/x.ova", Contenido.IMPORT, "extension"),
        ("/var/lib/vz/template/iso/x.iso", Contenido.ISO, "ruta_absoluta"),  # E-O14
        ("/mnt/x.qcow2", Contenido.IMPORT, "ruta_absoluta"),
        ("C:\\discos\\x.qcow2", Contenido.IMPORT, "ruta_absoluta"),
        ("\\\\srv\\x\\a.qcow2", Contenido.IMPORT, "ruta_absoluta"),
        ("x.iso", Contenido.ISO, "forma"),
        ("local:iso/", Contenido.ISO, "forma"),
        ("local:iso/a/b.iso", Contenido.ISO, "forma"),
        ("local:iso/..x.iso", Contenido.ISO, "forma"),
        (":iso/x.iso", Contenido.ISO, "forma"),
        ("", Contenido.ISO, "forma"),
        ("local:images/x.iso", Contenido.ISO, "forma"),
        ("local:iso/x.iso", Contenido.IMAGENES, "forma"),  # contenido sin extensiones
    ],
)
def test_v_o02_v_o03_volids_rechazados(volid, contenido, motivo):
    assert validar_volid(volid, contenido) == motivo


def test_validar_volid_no_lanza_con_tipos_raros():
    for raro in (None, 5, b"local:iso/x.iso", ["a"], 3.5):
        assert validar_volid(raro, Contenido.ISO) == "forma"  # type: ignore[arg-type]


def test_partes_volid_devuelve_storage_contenido_y_nombre_o_none():
    assert partes_volid("local:iso/a.iso") == ("local", Contenido.ISO, "a.iso")
    assert partes_volid("s1:import/a.raw") == ("s1", Contenido.IMPORT, "a.raw")
    for malo in ("local:iso/a.iso,x=1", "local:images/a.iso", "x", None, "/a/b.iso"):
        assert partes_volid(malo) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("nombre", "contenido", "motivo"),
    [
        ("alpine.iso", Contenido.ISO, None),
        ("Mi-ISO_1.2.IMG", Contenido.ISO, None),
        ("disco.qcow2", Contenido.IMPORT, None),
        ("con espacio.iso", Contenido.ISO, "caracteres"),
        ("acentó.iso", Contenido.ISO, "caracteres"),
        (".oculto.iso", Contenido.ISO, "caracteres"),
        ("a,b.iso", Contenido.ISO, "caracteres"),
        ("a=b.iso", Contenido.ISO, "caracteres"),
        ("x.txt", Contenido.ISO, "extension"),
        ("x.iso", Contenido.IMPORT, "extension"),
        ("CON.iso", Contenido.ISO, "reservado"),
        ("nul.qcow2", Contenido.IMPORT, "reservado"),
        ("com1.iso", Contenido.ISO, "reservado"),
        ("a" * 101 + ".iso", Contenido.ISO, "forma"),
        ("", Contenido.ISO, "forma"),
        ("/etc/x.iso", Contenido.ISO, "ruta_absoluta"),
    ],
)
def test_v_o09_nombre_de_archivo_a_subir(nombre, contenido, motivo):
    assert validar_nombre_archivo(nombre, contenido) == motivo


def test_v_o09_nombre_de_100_caracteres_es_el_limite_valido():
    assert validar_nombre_archivo("a" * 96 + ".iso", Contenido.ISO) is None  # 100
    assert validar_nombre_archivo("a" * 97 + ".iso", Contenido.ISO) == "forma"  # 101


@pytest.mark.parametrize(
    "crudo",
    [
        "Mi ISO ñandú.ISO",
        "../../etc/passwd",
        "C:\\Users\\ana\\Descargas\\ubuntu 24.04 (1).iso",
        "x.iso,media=disk",
        "con.iso",
        "...",
        ".oculto",
        "a" * 300 + ".iso",
        "日本語.iso",
        "",
        "sin_extension",
        "disco.img",
    ],
)
@pytest.mark.parametrize("contenido", [Contenido.ISO, Contenido.IMPORT])
def test_v_o09_el_nombre_saneado_siempre_cumple_la_lista_blanca(crudo, contenido):
    saneado = sanear_nombre_archivo(crudo, contenido)
    assert validar_nombre_archivo(saneado, contenido) is None, saneado


def test_sanear_nombre_conserva_lo_razonable():
    assert sanear_nombre_archivo("Mi ISO ñandú.ISO", Contenido.ISO) == "Mi_ISO_nandu.iso"
    assert sanear_nombre_archivo("ubuntu.iso", Contenido.ISO) == "ubuntu.iso"
    with pytest.raises(ValueError):
        sanear_nombre_archivo("x.iso", Contenido.IMAGENES)


def test_ruta_absoluta_url_y_virtio():
    for ruta in ("/var/x", "\\x", "C:\\x", "c:/x", " /x"):
        assert es_ruta_absoluta(ruta)
    for no in ("local:iso/x.iso", "alpine.iso", "", "a/b"):
        assert not es_ruta_absoluta(no)
    for url in ("http://x/a.iso", "HTTPS://x", "ftp://x", "file:///x", "www.ejemplo.com/a.iso"):
        assert parece_url(url)
    for no in ("alpine.iso", "local:iso/x.iso", "wwwx.iso"):
        assert not parece_url(no)
    assert es_virtio_win("virtio-win-0.1.271.iso") and es_virtio_win("VIRTIO-WIN.ISO")
    assert not es_virtio_win("virtio-win.qcow2") and not es_virtio_win("ubuntu.iso")


# --- RF-O24: permisos --------------------------------------------------------------------------


def test_el_rol_ampliado_tiene_14_privilegios_sin_datastore_allocate():
    assert len(ROL_PROXLAUNCH) == 14 and len(set(ROL_PROXLAUNCH)) == 14
    for nuevo in ("VM.Config.Disk", "VM.Clone", "Datastore.AllocateTemplate", "Sys.AccessNetwork"):
        assert nuevo in ROL_PROXLAUNCH
    for prohibido in ("Datastore.Allocate", "Sys.Modify", "VM.PowerMgmt", "VM.Config.CDROM"):
        assert prohibido not in ROL_PROXLAUNCH  # INV-O4 y CA-O24.6


@pytest.mark.parametrize(
    "accion",
    ["upload", "download-url", "crear_iso", "crear_import", "clone", "config", "resize"],
)
def test_ca_o24_8_cada_escritura_del_mvp4_exige_solo_privilegios_del_rol(accion):
    exigidos = privilegios_de_peticion(accion)
    assert exigidos and exigidos <= set(ROL_PROXLAUNCH)


def test_privilegios_de_peticion_rechaza_acciones_desconocidas():
    with pytest.raises(ValueError):
        privilegios_de_peticion("delete")


def test_tiene_privilegio_respeta_propagate():
    p = {"/": {"VM.Audit": 1}, "/vms/100": {"VM.Clone": 0}, "/storage/local": {"X": 1}}
    assert tiene_privilegio(p, "/vms/55", "VM.Audit")  # heredado de «/»
    assert tiene_privilegio(p, "/vms/100", "VM.Clone")
    assert not tiene_privilegio(p, "/vms/100/algo", "VM.Clone")  # propagate=0
    assert not tiene_privilegio(p, "/vms/101", "VM.Clone")
    assert tiene_privilegio(p, "/storage", "X")  # un /storage/<id> concreto vale para /storage
    assert not tiene_privilegio({}, "/", "VM.Audit")


def test_estado_privilegio_distingue_desconocido_de_ausente():
    assert estado_privilegio(None, "VM.Clone", "/vms/1") is None
    assert estado_privilegio(permisos(), "VM.Clone", "/vms/1") is True
    assert estado_privilegio(permisos(quitar=("VM.Clone",)), "VM.Clone", "/vms/1") is False


# --- Capa 1: V-O01 -----------------------------------------------------------------------------


def test_una_mv_de_m1_a_m3_no_produce_problemas_de_origen():
    assert validar_origen_sin_servidor(cfg_base()) == []


def test_v_o01_iso_sin_detalle_falta():
    cfg = cfg_base(origen=OrigenSO.ISO, tipo_so=TipoSO.LINUX)
    (p,) = [p for p in validar_origen_sin_servidor(cfg) if p.codigo == "V-O01"]
    assert (p.campo, p.severidad, p.params["motivo"]) == (
        "detalle_origen",
        Severidad.ERROR,
        "falta",
    )


def test_v_o01_iso_sin_fuente_ni_so():
    cfg = cfg_iso(None, None)
    problemas = validar_origen_sin_servidor(cfg)
    assert ("detalle_origen.iso", "falta_fuente") in {
        (p.campo, p.params.get("motivo")) for p in problemas if p.codigo == "V-O01"
    }
    assert ("tipo_so", "falta_so") in {
        (p.campo, p.params.get("motivo")) for p in problemas if p.codigo == "V-O01"
    }


def test_v_o01_detalle_de_otro_origen_es_incoherente():
    iso_con_detalle_de_import = cfg_import(cfg={})
    iso_con_detalle_de_import.origen = OrigenSO.ISO
    assert "incoherente" in _motivos(
        validar_origen_sin_servidor(iso_con_detalle_de_import), "V-O01"
    )
    vacio_con_detalle = cfg_base(detalle_origen=DetalleIso(iso=RefVolumen("a.iso")))
    assert "incoherente" in _motivos(validar_origen_sin_servidor(vacio_con_detalle), "V-O01")


def test_v_o01_import_y_clon_exigen_su_fuente():
    imp = cfg_import(None)
    assert "falta_fuente" in _motivos(validar_origen_sin_servidor(imp), "V-O01")
    clon = cfg_clon("")
    assert "falta_fuente" in _motivos(validar_origen_sin_servidor(clon), "V-O01")
    assert "falta_fuente" not in _motivos(validar_origen_sin_servidor(cfg_clon("", 9000)), "V-O01")


def test_v_o01_datos_de_so_ajenos_al_origen_son_solo_un_aviso():
    problemas = validar_origen_sin_servidor(cfg_base(tipo_so=TipoSO.LINUX, tpm=True))
    assert set(_cods(problemas)) == {"V-O01.ajeno"}
    assert all(p.severidad == Severidad.AVISO for p in problemas)


# --- Capa 1: V-O05, V-O06, V-O07, V-O23, V-O24, V-O29 ---------------------------------------------


def test_v_o05_windows_11_exige_uefi_y_tpm():
    cfg = cfg_iso(tipo_so=TipoSO.WINDOWS_11, drivers=VOLID_VIRTIO)
    errores = [p for p in validar_origen_sin_servidor(cfg) if p.codigo == "V-O05"]
    assert {(p.campo, p.params["motivo"]) for p in errores} == {
        ("firmware", "uefi"),
        ("tpm", "tpm"),
    }
    assert all(p.severidad == Severidad.ERROR for p in errores)
    ok = cfg_iso(tipo_so=TipoSO.WINDOWS_11, drivers=VOLID_VIRTIO, firmware=Firmware.OVMF, tpm=True)
    assert "V-O05" not in _cods(validar_origen_sin_servidor(ok))


@pytest.mark.parametrize("tipo", [TipoSO.WINDOWS_10, TipoSO.WINDOWS_SERVER_2016_2019])
def test_v_o05_otros_windows_con_seabios_es_aviso(tipo):
    problemas = validar_origen_sin_servidor(cfg_iso(tipo_so=tipo, drivers=VOLID_VIRTIO))
    (p,) = [p for p in problemas if p.codigo == "V-O05.seabios"]
    assert p.severidad == Severidad.AVISO
    assert "V-O05" not in _cods(problemas)


def test_v_o05_linux_y_otro_no_exigen_firmware_ni_tpm():
    for tipo in (TipoSO.LINUX, TipoSO.OTRO):
        assert not [
            p for p in validar_origen_sin_servidor(cfg_iso(tipo_so=tipo)) if p.codigo == "V-O05"
        ]


def _ide(n: int):
    return [Disco("local-lvm", 8, bus=Bus.IDE) for _ in range(n)]


def test_v_o06_con_iso_caben_dos_discos_ide():
    assert "V-O06" not in _cods(validar_origen_sin_servidor(cfg_iso(discos=_ide(2))))
    (p,) = [p for p in validar_origen_sin_servidor(cfg_iso(discos=_ide(3))) if p.codigo == "V-O06"]
    assert (p.severidad, p.params["maximo"], p.params["n"]) == (Severidad.ERROR, "2", "3")


def test_v_o06_sin_iso_no_se_limitan_los_discos_ide():
    assert validar_origen_sin_servidor(cfg_base(discos=_ide(4))) == []


@pytest.mark.parametrize(
    ("tipo", "cores", "mem", "disco", "campos"),
    [
        (TipoSO.WINDOWS_11, 1, 2048, 32, {"cores", "memoria_mib", "discos[0].tamano_gib"}),
        (TipoSO.WINDOWS_11, 2, 4096, 64, set()),
        (TipoSO.WINDOWS_11, 2, 4095, 64, {"memoria_mib"}),
        (TipoSO.WINDOWS_10, 1, 2048, 32, set()),
        (TipoSO.WINDOWS_10, 1, 2047, 31, {"memoria_mib", "discos[0].tamano_gib"}),
        (TipoSO.WINDOWS_SERVER_2022_2025, 1, 2048, 32, set()),
        (TipoSO.LINUX, 1, 512, 1, set()),
    ],
)
def test_v_o07_minimos_de_windows_son_avisos(tipo, cores, mem, disco, campos):
    cfg = cfg_iso(
        tipo_so=tipo,
        drivers=VOLID_VIRTIO,
        cores=cores,
        memoria_mib=mem,
        discos=[Disco("local-lvm", disco)],
        firmware=Firmware.OVMF,
        tpm=tipo in (TipoSO.WINDOWS_11, TipoSO.WINDOWS_SERVER_2022_2025),
    )
    avisos = [p for p in validar_origen_sin_servidor(cfg) if p.codigo == "V-O07"]
    assert {p.campo for p in avisos} == campos
    assert all(p.severidad == Severidad.AVISO for p in avisos)


def test_v_o07_los_sockets_suman_a_los_nucleos():
    cfg = cfg_iso(
        tipo_so=TipoSO.WINDOWS_11, sockets=2, cores=1, firmware=Firmware.OVMF, tpm=True,
        drivers=VOLID_VIRTIO, memoria_mib=8192, discos=[Disco("local-lvm", 64)],
    )  # fmt: skip
    assert "V-O07" not in _cods(validar_origen_sin_servidor(cfg))


@pytest.mark.parametrize(
    ("ajustes", "campo", "codigo"),
    [
        (AjustesClon(disco_gib=0), "detalle_origen.ajustes.disco_gib", "V-O23"),
        (AjustesClon(disco_gib=10**9), "detalle_origen.ajustes.disco_gib", "V-O23"),
        (AjustesClon(cores=0), "detalle_origen.ajustes.cores", "V-O24"),
        (AjustesClon(sockets=99), "detalle_origen.ajustes.sockets", "V-O24"),
        (AjustesClon(memoria_mib=1), "detalle_origen.ajustes.memoria_mib", "V-O24"),
        (AjustesClon(tipo_cpu="x;y"), "detalle_origen.ajustes.tipo_cpu", "V-O24"),
    ],
)
def test_v_o23_v_o24_ajustes_del_clon(ajustes, campo, codigo):
    problemas = validar_origen_sin_servidor(cfg_clon("base", 9000, "pve1", ajustes=ajustes))
    assert (campo, codigo) in {(p.campo, p.codigo) for p in problemas}


def test_v_o23_ajustes_validos_y_vacios_no_dan_problemas():
    ok = AjustesClon(1, 4, "x86-64-v3", 4096, 64)
    assert validar_origen_sin_servidor(cfg_clon("base", 9000, "pve1", ajustes=ok)) == []
    assert validar_origen_sin_servidor(cfg_clon("base", 9000, "pve1")) == []


def test_v_o23_ampliar_a_de_la_importacion_se_valida():
    assert "V-O23" in _cods(validar_origen_sin_servidor(cfg_import(ampliar_a_gib=0)))
    assert validar_origen_sin_servidor(cfg_import(ampliar_a_gib=40)) == []


def test_v_o29_importar_exige_disco_e_iso_sin_disco_avisa():
    sin_disco = cfg_import(cfg={"con_disco": False, "discos": []})
    assert "V-O29" in _cods(validar_origen_sin_servidor(sin_disco), Severidad.ERROR)
    iso_sin_disco = cfg_iso(con_disco=False, discos=[])
    problemas = validar_origen_sin_servidor(iso_sin_disco)
    (aviso,) = [p for p in problemas if p.codigo == "V-O29.sindisco"]
    assert aviso.severidad == Severidad.AVISO


# --- validar_vm integra el origen (V-20 retirada) -------------------------------------------------


def test_validar_vm_ya_no_emite_v_20_y_valida_un_iso_completo():
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    problemas = validar_vm(cfg_iso(), inv, CAPS)
    assert "V-20" not in _cods(problemas)
    assert _cods(problemas, Severidad.ERROR) == []


def test_validar_vm_sigue_aplicando_las_reglas_de_m1_a_un_iso():
    inv = inv_origen()
    problemas = validar_vm(cfg_iso(nombre="-x", cores=0), inv, CAPS)
    assert {"V-01", "V-05"} <= set(_cods(problemas, Severidad.ERROR))


# --- Capa 2: V-O02 / V-O03 ----------------------------------------------------------------------


def test_v_o02_iso_presente_en_el_catalogo_del_nodo_no_da_error():
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    assert _cods(validar_origen(cfg_iso(), inv, CAPS), Severidad.ERROR) == []


def test_v_o02_iso_que_ya_no_esta_en_el_catalogo_da_no_disponible():
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.ISO, "local:iso/otra.iso"),))
    problemas = validar_origen(cfg_iso(), inv, CAPS)
    assert "no_disponible" in _motivos(problemas, "V-O02")


def test_v_o02_sin_catalogo_leido_no_se_afirma_que_falte():
    assert "V-O02" not in _cods(validar_origen(cfg_iso(), inv_origen(), CAPS))


def test_v_o02_iso_sin_resolver_o_con_volid_inyectado():
    sin_resolver = cfg_iso(None)
    sin_resolver.detalle_origen = DetalleIso(iso=RefVolumen("alpine.iso", None))
    assert "sin_resolver" in _motivos(validar_origen(sin_resolver, inv_origen(), CAPS), "V-O02")
    inyectado = cfg_iso("local:iso/x.iso,media=disk")
    assert "caracteres" in _motivos(validar_origen(inyectado, inv_origen(), CAPS), "V-O02")


def test_v_o02_storage_inactivo_del_iso():
    from .apoyo_lote import storage

    inv = inv_origen(
        listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),),
        extra_storages={"pve1": ()},
    )
    inv.storages_todos["pve1"] = tuple(
        storage("local", "dir", 10, activo=False, contenido="iso") if s.id == "local" else s
        for s in inv.storages_todos["pve1"]
    )
    assert "storage_inactivo" in _motivos(validar_origen(cfg_iso(), inv, CAPS), "V-O02")


def test_v_o02_nombre_no_admitido_del_catalogo():
    """CA-O07.2: un volumen marcado como no admitido por el catálogo no se puede elegir."""
    from dataclasses import replace

    no_admitido = replace(volumen(VOLID_ISO), admitido=False)
    inv = inv_origen()
    inv.catalogo = replace(
        inv.catalogo,
        listados=(ListadoStorage("pve1", "local", Contenido.ISO, (no_admitido,)),),
    )
    assert "nombre_no_admitido" in _motivos(validar_origen(cfg_iso(), inv, CAPS), "V-O02")


def test_v_o02_windows_sin_drivers_resueltos_pide_drivers_o_confirmar_sin_ellos():
    cfg = cfg_iso(tipo_so=TipoSO.WINDOWS_10, firmware=Firmware.OVMF)
    assert "V-O02.drivers" in _cods(validar_origen(cfg, inv_origen(), CAPS))
    sin = cfg_iso(tipo_so=TipoSO.WINDOWS_10, firmware=Firmware.OVMF, sin_drivers=True)
    assert "V-O02.drivers" not in _cods(validar_origen(sin, inv_origen(), CAPS))


def test_v_o03_importar_en_la_version_minima_no_da_error_de_version():
    """DT-D3: con la mínima 8.4 ya no existe el motivo ``version`` de V-O03."""
    inv = inv_origen(version=Version("8.4.1", 8, 4, 1))
    caps = capacidades_para(Version("8.4.1", 8, 4, 1), None)
    problemas = validar_origen(cfg_import(), inv, caps)
    assert not [p for p in problemas if p.codigo == "V-O03" and p.params.get("motivo") == "version"]


def test_v_o03_volid_de_imagen_con_ruta_absoluta_o_inyeccion():
    for malo, motivo in (
        ("/mnt/x.qcow2", "ruta_absoluta"),
        ("local:import/x.qcow2,scsi1=a", "caracteres"),
    ):
        assert motivo in _motivos(validar_origen(cfg_import(malo), inv_origen(), CAPS), "V-O03")


def test_v_o03_imagen_inexistente_en_el_catalogo():
    inv = inv_origen(
        listados=(listado("pve1", "local", Contenido.IMPORT, "local:import/otra.raw"),)
    )
    assert "no_disponible" in _motivos(validar_origen(cfg_import(), inv, CAPS), "V-O03")


def test_v_o23_tamano_ampliar_a_no_puede_ser_menor_que_el_disco_importado():
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.IMPORT, VOLID_IMAGEN),))
    cfg = cfg_import(ampliar_a_gib=1, tamano_virtual_bytes=5 * 1024**3)
    assert "V-O23.tamano" in _cods(validar_origen(cfg, inv, CAPS), Severidad.ERROR)
    ok = cfg_import(ampliar_a_gib=5, tamano_virtual_bytes=5 * 1024**3)
    assert "V-O23.tamano" not in _cods(validar_origen(ok, inv, CAPS))


def test_v_o19_destino_sin_allocate_space_bloquea_la_importacion():
    sin = PermisosEfectivos(rutas={"/": {p: 1 for p in ROL_MVP3 if p != "Datastore.AllocateSpace"}})
    inv = inv_origen(
        permisos_efectivos=sin, listados=(listado("pve1", "local", Contenido.IMPORT, VOLID_IMAGEN),)
    )
    problemas = validar_origen(cfg_import(), inv, CAPS)
    (p,) = [p for p in problemas if p.codigo == "V-O19"]
    assert p.params["storage"] == "local-lvm" and p.severidad == Severidad.ERROR


# --- Capa 2: clon (V-O04, V-O17, V-O21, V-O23) ----------------------------------------------------


def _inv_clon(detalle=None, **kw):
    pl = plantilla_pve(9000, "base", "pve1", detalle=detalle)
    return inv_origen(plantillas=(pl,), **kw)


def test_v_o04_plantilla_sin_resolver_o_inexistente():
    assert "sin_resolver" in _motivos(validar_origen(cfg_clon("base"), _inv_clon(), CAPS), "V-O04")
    fantasma = cfg_clon("base", 9999, "pve1")
    assert "no_existe" in _motivos(validar_origen(fantasma, _inv_clon(), CAPS), "V-O04")


def test_v_o04_plantilla_bloqueada():
    inv = inv_origen(plantillas=(plantilla_pve(bloqueo="clone"),))
    problemas = validar_origen(cfg_clon("base", 9000, "pve1"), inv, CAPS)
    assert "bloqueada" in _motivos(problemas, "V-O04")


def test_v_o17_sin_vm_clone_no_se_puede_clonar():
    inv = _inv_clon(privilegios=ROL_MVP3)
    inv.catalogo = inv.catalogo.__class__(
        permisos=permisos(quitar=("VM.Clone",)), plantillas=inv.catalogo.plantillas
    )
    (p,) = [
        p for p in validar_origen(cfg_clon("base", 9000, "pve1"), inv, CAPS) if p.codigo == "V-O17"
    ]
    assert p.params["privilegio"] == "VM.Clone" and p.params["ruta"] == "/vms/9000"


def test_v_o21_enlazado_forzado_sin_soporte_es_error_y_con_soporte_no():
    grueso = detalle_plantilla([disco_plantilla("scsi0", "local-lvm")])
    inv_lvm = _inv_clon(grueso)
    # `local-lvm` es lvmthin: admite enlazado.
    cfg = cfg_clon("base", 9000, "pve1", modo=ModoClon.ENLAZADO)
    assert "V-O21" not in _cods(validar_origen(cfg, inv_lvm, CAPS))
    from .apoyo_lote import storage

    inv_grueso = _inv_clon(
        detalle_plantilla([disco_plantilla("scsi0", "lvm1")]),
        extra_storages={"pve1": (storage("lvm1", "lvm", 100, contenido="images"),)},
    )
    assert "V-O21" in _cods(validar_origen(cfg, inv_grueso, CAPS), Severidad.ERROR)


def test_v_o21_enlazado_con_storage_destino_es_error():
    cfg = cfg_clon("base", 9000, "pve1", modo=ModoClon.ENLAZADO, storage_destino="local-lvm")
    assert "V-O21" in _cods(validar_origen(cfg, _inv_clon(), CAPS), Severidad.ERROR)


def test_v_o23_clon_no_puede_reducir_el_disco_de_la_plantilla():
    cfg = cfg_clon("base", 9000, "pve1", ajustes=AjustesClon(disco_gib=4))  # plantilla: 8 GiB
    assert "V-O23.tamano" in _cods(validar_origen(cfg, _inv_clon(), CAPS), Severidad.ERROR)
    ok = cfg_clon("base", 9000, "pve1", ajustes=AjustesClon(disco_gib=16))
    assert "V-O23.tamano" not in _cods(validar_origen(ok, _inv_clon(), CAPS))


def test_v_17_storage_destino_del_clon_completo_debe_admitir_images():
    cfg = cfg_clon(
        "base", 9000, "pve1", modo=ModoClon.COMPLETO, efectivo=ModoClon.COMPLETO,
        storage_destino="inexistente",
    )  # fmt: skip
    assert "V-17" in _cods(validar_origen(cfg, _inv_clon(), CAPS), Severidad.ERROR)


# --- V-O18 / INV-O10: permisos dudosos ------------------------------------------------------------


def test_v_o18_iso_sin_vm_config_disk_avisa_que_no_hay_orden_de_arranque():
    inv = inv_origen(permisos_efectivos=permisos(quitar=("VM.Config.Disk",)))
    (p,) = [p for p in validar_origen(cfg_iso(), inv, CAPS) if p.codigo == "V-O18"]
    assert (p.severidad, p.params["efecto"], p.params["desconocido"]) == (
        Severidad.AVISO,
        "orden_arranque",
        "0",
    )


def test_v_o18_con_permisos_desconocidos_tambien_avisa_y_lo_marca_desconocido():
    inv = inv_origen(permisos_efectivos=None)
    (p,) = [p for p in validar_origen(cfg_iso(), inv, CAPS) if p.codigo == "V-O18"]
    assert p.params["desconocido"] == "1"


def test_v_o18_con_el_permiso_no_hay_aviso_y_ampliar_avisa_sin_el():
    assert "V-O18" not in _cods(validar_origen(cfg_iso(), inv_origen(), CAPS))
    inv = inv_origen(permisos_efectivos=permisos(quitar=("VM.Config.Disk",)))
    cfg = cfg_import(ampliar_a_gib=40)
    (p,) = [p for p in validar_origen(cfg, inv, CAPS) if p.codigo == "V-O18"]
    assert p.params["efecto"] == "ampliar"
